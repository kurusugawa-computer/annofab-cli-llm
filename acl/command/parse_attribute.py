import argparse
import json
from pathlib import Path
from typing import Any

import annofabapi
from annofabapi.models import AdditionalDataDefinitionType
from annofabapi.util.annotation_specs import AnnotationSpecsAccessor, get_english_message, get_message_with_lang
from litellm import completion
from loguru import logger
from pydantic import BaseModel, Field, field_validator, model_validator

import acl.common.cli
from acl.common.cli import read_at_file
from acl.common.utils import print_json
from acl.common.xdg_util import create_command_temp_dir

COMMAND_NAME = "parse_attribute"
OUTPUT_USAGE_MESSAGE = (
    "出力されるJSONは、 [annofabcli annotation_specs add_attributes]"
    "(https://annofab-cli.readthedocs.io/ja/latest/command_reference/annotation_specs/add_attributes.html) コマンドの --attribute_json 引数にそのまま指定できます。"
)
"""出力JSONの利用方法に関するメッセージです。"""

CHOICE_ATTRIBUTE_TYPES = {
    AdditionalDataDefinitionType.CHOICE,
    AdditionalDataDefinitionType.SELECT,
}
"""選択肢を持つ属性種類です。"""

ATTRIBUTE_TYPE_DESCRIPTIONS: dict[AdditionalDataDefinitionType, str] = {
    AdditionalDataDefinitionType.FLAG: "チェックボックス",
    AdditionalDataDefinitionType.INTEGER: "整数",
    AdditionalDataDefinitionType.TEXT: "自由記述（1行）",
    AdditionalDataDefinitionType.COMMENT: "自由記述（複数行）",
    AdditionalDataDefinitionType.CHOICE: "ラジオボタン（排他選択）",
    AdditionalDataDefinitionType.SELECT: "ドロップダウン（排他選択）",
    AdditionalDataDefinitionType.TRACKING: "トラッキングID",
    AdditionalDataDefinitionType.LINK: "アノテーションリンク",
}
"""attribute_type の説明です。"""


class ChoiceCandidate(BaseModel):
    """
    追加候補の選択肢情報です。
    """

    choice_name_en: str = Field(description="追加する選択肢名（英語）です。")
    """選択肢名（英語）です。"""

    choice_name_ja: str | None = Field(default=None, description="追加する選択肢名（日本語）です。特定できない場合はnullにしてください。")
    """選択肢名（日本語）です。"""

    is_default: bool = Field(default=False, description="その選択肢をデフォルト値にする場合はtrueです。")
    """デフォルト値かどうかです。"""

    @field_validator("choice_name_en")
    @classmethod
    def validate_choice_name_en(cls, value: str) -> str:
        normalized = value.strip()
        if normalized == "":
            raise ValueError("空文字列は指定できません。")
        return normalized

    @field_validator("choice_name_ja")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if normalized == "":
            return None
        return normalized


class AttributeCandidate(BaseModel):
    """
    追加候補の属性情報です。
    """

    attribute_type: AdditionalDataDefinitionType = Field(description="追加する属性の種類です。")
    """属性種類です。"""

    attribute_name_en: str = Field(description="追加する属性名（英語）です。")
    """属性名（英語）です。"""

    label_name_ens: list[str] = Field(description="属性を追加する対象ラベル名（英語）の一覧です。")
    """属性を追加する対象ラベル名（英語）の一覧です。"""

    attribute_name_ja: str | None = Field(default=None, description="追加する属性名（日本語）です。特定できない場合はnullにしてください。")
    """属性名（日本語）です。"""

    read_only: bool = Field(default=False, description="読み込み専用の属性にする場合はtrueです。")
    """読み込み専用の属性かどうかです。"""

    choices: list[ChoiceCandidate] | None = Field(default=None, description="`attribute_type` が `choice` または `select` のときだけ指定する選択肢一覧です。")
    """選択肢一覧です。"""

    @field_validator("attribute_name_en")
    @classmethod
    def validate_attribute_name_en(cls, value: str) -> str:
        normalized = value.strip()
        if normalized == "":
            raise ValueError("空文字列は指定できません。")
        return normalized

    @field_validator("attribute_name_ja")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if normalized == "":
            return None
        return normalized

    @field_validator("label_name_ens")
    @classmethod
    def validate_label_name_ens(cls, value: list[str]) -> list[str]:
        if len(value) == 0:
            raise ValueError("1件以上指定してください。")

        normalized_values: list[str] = []
        seen: set[str] = set()
        duplicated_values: set[str] = set()
        for label_name_en in value:
            normalized = label_name_en.strip()
            if normalized == "":
                raise ValueError("空文字列は指定できません。")
            normalized_values.append(normalized)
            if normalized in seen:
                duplicated_values.add(normalized)
            seen.add(normalized)

        if duplicated_values:
            duplicated_text = ", ".join(sorted(duplicated_values))
            raise ValueError(f"`label_name_ens` に重複があります。 :: {duplicated_text}")

        return normalized_values

    @model_validator(mode="after")
    def validate_choices(self) -> "AttributeCandidate":
        if self.attribute_type in CHOICE_ATTRIBUTE_TYPES:
            if self.choices is None:
                raise ValueError("属性種類が `choice` または `select` の場合は `choices` を指定してください。")
            if len(self.choices) < 2:
                raise ValueError("`choice` または `select` の場合は、選択肢を2件以上指定してください。")

            default_count = len([choice for choice in self.choices if choice.is_default])
            if default_count > 1:
                raise ValueError("`is_default=true` を指定できる選択肢は0件または1件です。")
        elif self.choices is not None:
            raise ValueError("`choices` は `choice` または `select` の場合のみ指定できます。")

        return self


class AttributeParseResult(BaseModel):
    """
    属性の自然言語解析結果です。
    """

    attributes: list[AttributeCandidate] = Field(description="解析できた追加対象属性の一覧です。")
    """解析できた属性候補の一覧です。"""

    warnings: list[str] = Field(default_factory=list, description="解析時の注意事項です。解析結果に含めたが補足したい内容を入れてください。")
    """解析時の注意事項です。"""

    unresolved_texts: list[str] = Field(default_factory=list, description="属性追加ルールとして解釈できなかった原文の断片です。曖昧、情報不足、対象外の内容を入れてください。")
    """属性追加ルールとして解釈できなかった原文の断片です。"""


def get_attribute_type_details() -> list[dict[str, str]]:
    """
    利用可能な attribute_type と説明を返します。

    Returns:
        attribute_type と説明の一覧
    """
    return [{"value": attribute_type.value, "description": description} for attribute_type, description in ATTRIBUTE_TYPE_DESCRIPTIONS.items()]


def get_label_catalog(annotation_specs: dict[str, Any]) -> list[dict[str, Any]]:
    """
    LLMへ渡すための既存ラベル一覧を生成します。

    Args:
        annotation_specs: アノテーション仕様(v3)

    Returns:
        既存ラベル一覧
    """
    return [
        {
            "label_name_en": get_english_message(label["label_name"]),
            "label_name_ja": get_message_with_lang(label["label_name"], "ja-JP"),
        }
        for label in annotation_specs.get("labels", [])
    ]


def get_attribute_catalog(annotation_specs: dict[str, Any]) -> list[dict[str, Any]]:
    """
    LLMへ渡すための既存属性一覧を生成します。

    Args:
        annotation_specs: アノテーション仕様(v3)

    Returns:
        既存属性一覧
    """
    annotation_specs_accessor = AnnotationSpecsAccessor(annotation_specs)

    label_names_by_attribute_id: dict[str, list[str]] = {}
    for label in annotation_specs_accessor.labels:
        label_name_en = get_english_message(label["label_name"])
        for additional_data_definition_id in label.get("additional_data_definitions", []):
            label_names_by_attribute_id.setdefault(additional_data_definition_id, []).append(label_name_en)

    catalog = []
    for additional in annotation_specs_accessor.additionals:
        choices = additional.get("choices") or []
        catalog.append(
            {
                "attribute_name_en": get_english_message(additional["name"]),
                "attribute_name_ja": get_message_with_lang(additional["name"], "ja-JP"),
                "attribute_type": additional.get("type"),
                "label_name_ens": sorted(label_names_by_attribute_id.get(additional.get("additional_data_definition_id"), [])),
                "choice_name_ens": [get_english_message(choice["name"]) for choice in choices],
            }
        )
    return catalog


def parse_attributes_from_text(
    *,
    text: str,
    annotation_specs: dict[str, Any],
    llm_model: str,
    temp_dir: Path | None = None,
) -> AttributeParseResult:
    """
    自然言語のテキストから属性候補を抽出します。

    Args:
        text: 属性追加ルールが記載された自然言語
        annotation_specs: アノテーション仕様(v3)
        llm_model: 使用するLLMのモデル
        temp_dir: 任意の一時ディレクトリ

    Returns:
        属性の解析結果
    """
    label_catalog = get_label_catalog(annotation_specs)
    attribute_catalog = get_attribute_catalog(annotation_specs)
    attribute_type_details = get_attribute_type_details()
    messages = [
        {
            "role": "developer",
            "content": """
あなたは、自然言語で書かれたアノテーションルールから、Annofabに追加する属性を抽出するAIです。
抽出した結果は、必ずAttributeParseResult形式で返してください。
追加対象の新規属性だけを attributes に入れてください。
既存のannotation specsに存在するラベル名（英語）だけを label_name_ens に入れてください。
既存のannotation specsに既に存在する属性名（英語）は出力してはいけません。
attribute_name_en と label_name_ens に含める label_name_en は、アノテーションJSONに出力される値なので、英語小文字のスネークケースで出力してください。
`choice` または `select` の choices に含める choice_name_en も、アノテーションJSONに出力される値なので、英語小文字のスネークケースで出力してください。
読み込み専用の属性にする指定がある場合は read_only を true にしてください。指定がない場合は false にしてください。
対象ラベルを特定できない場合は、attributes に入れず unresolved_texts に入れてください。
attribute_type を特定できない場合は、attributes に入れず unresolved_texts に入れてください。
`choice` または `select` の場合は、choices を2件以上出力してください。
`choice` または `select` 以外では choices を出力してはいけません。
曖昧な条件や属性追加ルールではない文も unresolved_texts に入れてください。
""".strip(),
        },
        {
            "role": "user",
            "content": f"""
以下の自然言語テキストから、Annofabに追加する属性を抽出してください。

## 入力テキスト
{text}

## 利用可能な attribute_type と説明
{json.dumps(attribute_type_details, ensure_ascii=False, indent=2)}

## 既存ラベル一覧
{json.dumps(label_catalog, ensure_ascii=False, indent=2)}

## 既存属性一覧
{json.dumps(attribute_catalog, ensure_ascii=False, indent=2)}
""".strip(),
        },
    ]

    if temp_dir is not None:
        print_json(messages, temp_dir / "llm_prompt.json")

    response = completion(
        model=llm_model,
        messages=messages,
        response_format=AttributeParseResult,
    )
    content = response.choices[0].message.content

    if temp_dir is not None:
        (temp_dir / "llm_raw_response.txt").write_text(content, encoding="utf-8")

    result = AttributeParseResult.model_validate_json(content)
    logger.info(
        f"[LLM] 属性を解析しました。 :: attribute_count={len(result.attributes)}, warnings={len(result.warnings)}, "
        f"unresolved_texts={len(result.unresolved_texts)}, total_tokens={response.usage.total_tokens}, "
        f"prompt_tokens={response.usage.prompt_tokens}, completion_tokens={response.usage.completion_tokens}"
    )

    if temp_dir is not None:
        print_json(label_catalog, temp_dir / "label_catalog.json")
        print_json(attribute_catalog, temp_dir / "attribute_catalog.json")
        print_json(result.model_dump(mode="json"), temp_dir / "llm_completion.json")

    return result


def get_annotation_specs(
    *,
    annotation_specs_json_file: Path | None,
    project_id: str | None,
    annofab_pat: str | None,
) -> dict[str, Any]:
    """
    ファイルまたはAnnofab APIからannotation specsを取得します。

    Args:
        annotation_specs_json_file: annotation specs JSONファイル
        project_id: AnnofabのプロジェクトID
        annofab_pat: AnnofabのPAT

    Returns:
        annotation specs(v3)
    """
    if annotation_specs_json_file is not None:
        logger.info(f"annotation specs JSONファイルを読み込みます。 :: path='{annotation_specs_json_file}'")
        return json.loads(annotation_specs_json_file.read_text(encoding="utf-8"))

    if project_id is None:
        raise ValueError("`annotation_specs_json_file`または`project_id`のいずれかを指定してください。")

    logger.info(f"Annofabからアノテーション仕様を取得します。 :: project_id='{project_id}'")
    service = annofabapi.build(pat=annofab_pat)
    annotation_specs, _ = service.api.get_annotation_specs(project_id, query_params={"v": "3"})
    return annotation_specs


def collect_supplements_interactively(unresolved_texts: list[str]) -> list[str]:
    """
    未解決テキストに対してユーザーから補足情報をインタラクティブに収集します。

    Args:
        unresolved_texts: 属性追加ルールとして解釈できなかった原文の断片一覧

    Returns:
        ユーザーが入力した補足情報の一覧
    """
    supplements: list[str] = []
    for _i, _unresolved_text in enumerate(unresolved_texts, start=1):
        supplement = input("補足情報を入力してください（スキップする場合は空Enterを押してください）: ").strip()
        if supplement != "":
            supplements.append(supplement)
    return supplements


def normalize_parsed_attributes(result: AttributeParseResult, annotation_specs: dict[str, Any]) -> AttributeParseResult:
    """
    解析済み属性候補を正規化します。

    Args:
        result: LLMの解析結果
        annotation_specs: アノテーション仕様(v3)

    Returns:
        正規化済みの解析結果
    """
    label_catalog = get_label_catalog(annotation_specs)
    attribute_catalog = get_attribute_catalog(annotation_specs)
    existing_label_name_ens = {label["label_name_en"] for label in label_catalog if label["label_name_en"] is not None}
    existing_attribute_labels_by_name: dict[str, list[set[str]]] = {}
    for existing_attribute in attribute_catalog:
        attribute_name_en = existing_attribute["attribute_name_en"]
        if attribute_name_en is None:
            continue
        existing_attribute_labels_by_name.setdefault(attribute_name_en, []).append(set(existing_attribute["label_name_ens"]))

    parsed_attribute_labels_by_name: dict[str, list[set[str]]] = {}
    normalized_attributes: list[AttributeCandidate] = []
    warnings = list(result.warnings)

    for parsed_attribute in result.attributes:
        unknown_label_names = [label_name_en for label_name_en in parsed_attribute.label_name_ens if label_name_en not in existing_label_name_ens]
        if unknown_label_names:
            warnings.append(f"属性'{parsed_attribute.attribute_name_en}'には存在しないラベルが含まれていたため、出力から除外しました。 :: label_name_ens={sorted(unknown_label_names)}")
            continue

        label_name_en_set = set(parsed_attribute.label_name_ens)
        existing_label_sets = existing_attribute_labels_by_name.get(parsed_attribute.attribute_name_en, [])
        overlapped_existing_labels = sorted({label_name_en for existing_label_set in existing_label_sets for label_name_en in (existing_label_set & label_name_en_set)})
        if overlapped_existing_labels:
            warnings.append(
                f"既存属性'{parsed_attribute.attribute_name_en}'と同じラベルに属する属性は add_attributes の追加対象ではないため、出力から除外しました。 :: label_name_ens={overlapped_existing_labels}"
            )
            continue

        parsed_label_sets = parsed_attribute_labels_by_name.get(parsed_attribute.attribute_name_en, [])
        overlapped_parsed_labels = sorted({label_name_en for parsed_label_set in parsed_label_sets for label_name_en in (parsed_label_set & label_name_en_set)})
        if overlapped_parsed_labels:
            warnings.append(f"属性'{parsed_attribute.attribute_name_en}'が同じラベルに対して重複していたため、先頭の1件だけを採用しました。 :: label_name_ens={overlapped_parsed_labels}")
            continue

        parsed_attribute_labels_by_name.setdefault(parsed_attribute.attribute_name_en, []).append(label_name_en_set)
        normalized_attributes.append(parsed_attribute)

    return AttributeParseResult(
        attributes=normalized_attributes,
        warnings=warnings,
        unresolved_texts=result.unresolved_texts,
    )


def to_annofab_attributes(result: AttributeParseResult) -> list[dict[str, Any]]:
    """
    解析結果を ``annotation_specs add_attributes --attribute_json`` に渡せるJSONへ変換します。

    Args:
        result: 属性の解析結果

    Returns:
        add_attributes向けのJSON配列
    """
    return [attribute.model_dump(mode="json", exclude_none=True) for attribute in result.attributes]


def main(args: argparse.Namespace) -> None:
    annotation_rule = read_at_file(args.annotation_rule)

    temp_dir = create_command_temp_dir(COMMAND_NAME)
    logger.info(f"一時ディレクトリ'{temp_dir}'を作成しました。このディレクトリにLLMの入出力情報などを出力します。")
    temp_dir.mkdir(exist_ok=True)

    annotation_specs = get_annotation_specs(
        annotation_specs_json_file=args.annotation_specs_json_file,
        project_id=args.project_id,
        annofab_pat=args.annofab_pat,
    )
    print_json(annotation_specs, temp_dir / "annotation_specs.json")

    current_text = annotation_rule
    result = parse_attributes_from_text(
        text=current_text,
        annotation_specs=annotation_specs,
        llm_model=args.model,
        temp_dir=temp_dir,
    )
    result = normalize_parsed_attributes(result, annotation_specs)
    print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")

    for warning in result.warnings:
        logger.warning(f"属性解析時に注意事項がありました。 :: {warning}")
    for unresolved_text in result.unresolved_texts:
        logger.warning(f"属性追加ルールとして解釈できないテキストがありました。 :: {unresolved_text}")

    interactive = not args.no_interactive and not args.yes
    while result.unresolved_texts and interactive:
        supplements = collect_supplements_interactively(result.unresolved_texts)
        if len(supplements) == 0:
            break

        logger.info(f"{len(supplements)}件の補足情報をもとに再解析します。")
        supplement_text = "\n".join(supplements)
        current_text = f"{current_text}\n\n## 補足情報\n{supplement_text}"
        result = parse_attributes_from_text(
            text=current_text,
            annotation_specs=annotation_specs,
            llm_model=args.model,
            temp_dir=temp_dir,
        )
        result = normalize_parsed_attributes(result, annotation_specs)
        print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")

        for warning in result.warnings:
            logger.warning(f"属性解析時に注意事項がありました。 :: {warning}")
        for unresolved_text in result.unresolved_texts:
            logger.warning(f"属性追加ルールとして解釈できないテキストがありました。 :: {unresolved_text}")

    annofab_attributes = to_annofab_attributes(result)
    if len(annofab_attributes) == 0:
        raise ValueError("アノテーション仕様に追加可能な属性を抽出できませんでした。")

    print_json(annofab_attributes, output=args.output)
    logger.info(OUTPUT_USAGE_MESSAGE)
    print_json(annofab_attributes, temp_dir / "annofab_attributes.json")
    logger.info("属性の自然言語解析が完了しました。")


def add_argument_to_parser(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--annotation_specs_json_file",
        type=Path,
        help="annotation specs v3 のJSONファイルのパス",
    )
    group.add_argument(
        "-p",
        "--project_id",
        type=str,
        help="AnnofabのプロジェクトID",
    )

    parser.add_argument(
        "--annotation_rule",
        type=str,
        required=True,
        help="属性追加に関するアノテーションルールやアノテーション仕様の自然言語。先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="出力先のファイルパス。指定しない場合は、標準出力に出力されます。",
    )
    parser.add_argument(
        "--no_interactive",
        action="store_true",
        dest="no_interactive",
        help="未解決テキストが存在しても、補足情報の入力を求めずに終了します。",
    )


def add_parser(subparsers: argparse._SubParsersAction | None = None) -> argparse.ArgumentParser:
    parser = acl.common.cli.add_parser(
        subparsers,
        COMMAND_NAME,
        "自然言語から追加対象の属性を解析します。",
        description=f"自然言語から追加対象の属性を解析します。\n{OUTPUT_USAGE_MESSAGE}",
    )
    add_argument_to_parser(parser)
    parser.set_defaults(func=main)
    return parser
