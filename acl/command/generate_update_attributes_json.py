import argparse
import json
from pathlib import Path
from typing import Any

from annofabapi.models import AdditionalDataDefinitionType
from annofabapi.util.annotation_specs import get_english_message, get_message_with_lang
from litellm import completion
from loguru import logger
from pydantic import BaseModel, Field, model_validator

import acl.common.cli
from acl.command.generate_add_attributes_json import get_annotation_specs, get_catalog_keybind, get_required_japanese_message, is_default_choice
from acl.command.generate_add_labels_json import STRUCTURED_OUTPUT_MODEL_CONFIG, KeybindCandidate, UnresolvedText, format_unresolved_text
from acl.common.cli import read_at_file
from acl.common.utils import print_json
from acl.common.xdg_util import create_command_temp_dir

COMMAND_NAME = "generate_update_attributes_json"
OUTPUT_USAGE_MESSAGE = "出力されるJSONは、annofabcli annotation_specs update_attributes コマンドの --attribute_json 引数にそのまま指定できます。"
"""出力JSONの利用方法に関するメッセージです。"""


class ChoiceUpdateCatalogItem(BaseModel):
    """
    LLMへ渡すための既存選択肢情報です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    choice_id: str = Field(description="既存選択肢のIDです。")
    """既存選択肢のIDです。"""

    choice_name_en: str = Field(description="既存選択肢名（英語）です。")
    """既存選択肢名（英語）です。"""

    choice_name_ja: str = Field(description="既存選択肢名（日本語）です。")
    """既存選択肢名（日本語）です。"""

    is_default: bool = Field(description="デフォルト値の選択肢の場合はtrueです。")
    """デフォルト値かどうかです。"""

    keybind: KeybindCandidate | None = Field(description="既存選択肢に設定されたキーボードショートカットです。")
    """既存選択肢に設定されたキーボードショートカットです。"""


class AttributeUpdateCatalogItem(BaseModel):
    """
    LLMへ渡すための既存属性情報です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    attribute_id: str = Field(description="既存属性のIDです。")
    """既存属性のIDです。"""

    attribute_name_en: str = Field(description="既存属性名（英語）です。")
    """既存属性名（英語）です。"""

    attribute_name_ja: str = Field(description="既存属性名（日本語）です。")
    """既存属性名（日本語）です。"""

    attribute_name_vi: str | None = Field(description="既存属性名（ベトナム語）です。")
    """既存属性名（ベトナム語）です。"""

    attribute_type: str = Field(description="既存属性の種類です。")
    """既存属性の種類です。"""

    label_name_ens: list[str] = Field(description="この属性が付与されるラベル名（英語）の一覧です。")
    """この属性が付与されるラベル名（英語）の一覧です。"""

    read_only: bool = Field(description="読み込み専用属性の場合はtrueです。")
    """読み込み専用属性かどうかです。"""

    default: str | int | bool | None = Field(description="属性の初期値です。")
    """属性の初期値です。"""

    keybind: KeybindCandidate | None = Field(description="既存属性に設定されたキーボードショートカットです。")
    """既存属性に設定されたキーボードショートカットです。"""

    choices: list[ChoiceUpdateCatalogItem] = Field(description="属性種類がchoiceまたはselectの場合の選択肢一覧です。")
    """選択肢一覧です。"""


class ChoiceUpdateCandidate(BaseModel):
    """
    更新候補の選択肢情報です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    choice_id: str = Field(description="更新対象選択肢のIDです。")
    """更新対象選択肢のIDです。"""

    choice_name_en: str | None = Field(default=None, description="更新後の選択肢名（英語）です。")
    """更新後の選択肢名（英語）です。"""

    choice_name_ja: str | None = Field(default=None, description="更新後の選択肢名（日本語）です。")
    """更新後の選択肢名（日本語）です。"""

    choice_name_vi: str | None = Field(default=None, description="更新後の選択肢名（ベトナム語）です。")
    """更新後の選択肢名（ベトナム語）です。"""

    keybind: KeybindCandidate | None = Field(default=None, description="更新後のキーボードショートカットです。nullを指定すると解除します。")
    """更新後のキーボードショートカットです。"""

    @model_validator(mode="after")
    def validate_choice_id(self) -> "ChoiceUpdateCandidate":
        if self.choice_id.strip() == "":
            raise ValueError("`choice_id` には空でない文字列を指定してください。")
        return self


class AttributeUpdateCandidate(BaseModel):
    """
    更新候補の属性情報です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    attribute_id: str = Field(description="更新対象属性のIDです。既存属性一覧に存在するIDを指定してください。")
    """更新対象属性のIDです。"""

    attribute_name_en: str | None = Field(default=None, description="更新後の属性名（英語）です。")
    """更新後の属性名（英語）です。"""

    attribute_name_ja: str | None = Field(default=None, description="更新後の属性名（日本語）です。")
    """更新後の属性名（日本語）です。"""

    attribute_name_vi: str | None = Field(default=None, description="更新後の属性名（ベトナム語）です。")
    """更新後の属性名（ベトナム語）です。"""

    keybind: KeybindCandidate | None = Field(default=None, description="更新後のキーボードショートカットです。")
    """更新後のキーボードショートカットです。"""

    read_only: bool | None = Field(default=None, description="更新後の読み込み専用設定です。")
    """更新後の読み込み専用設定です。"""

    default_value: str | int | bool | None = Field(default=None, description="更新後の初期値です。")
    """更新後の初期値です。"""

    choice_updates: list[ChoiceUpdateCandidate] | None = Field(default=None, description="既存選択肢の更新情報です。")
    """既存選択肢の更新情報です。"""

    @model_validator(mode="after")
    def validate_attribute_id(self) -> "AttributeUpdateCandidate":
        if self.attribute_id.strip() == "":
            raise ValueError("`attribute_id` には空でない文字列を指定してください。")
        return self


class AttributeUpdateParseResult(BaseModel):
    """
    属性更新の自然言語解析結果です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    attributes: list[AttributeUpdateCandidate] = Field(description="解析できた更新対象属性の一覧です。")
    """解析できた属性更新候補の一覧です。"""

    warnings: list[str] = Field(default_factory=list, description="解析時の注意事項です。")
    """解析時の注意事項です。"""

    unresolved_texts: list[UnresolvedText] = Field(default_factory=list, description="属性更新ルールとして解釈できなかった原文、理由、必要な補足情報です。")
    """属性更新ルールとして解釈できなかった原文、理由、必要な補足情報です。"""


def get_optional_message(annotation_text: Any, *, lang: str) -> str | None:  # noqa: ANN401
    return get_message_with_lang(annotation_text, lang)


def get_attribute_update_catalog(annotation_specs: dict[str, Any]) -> list[AttributeUpdateCatalogItem]:
    """
    LLMへ渡すための既存属性一覧を生成します。
    """
    label_names_by_attribute_id: dict[str, list[str]] = {}
    for label in annotation_specs["labels"]:
        label_name_en = get_english_message(label["label_name"])
        for additional_data_definition_id in label["additional_data_definitions"]:
            label_names_by_attribute_id.setdefault(additional_data_definition_id, []).append(label_name_en)

    return [
        (
            AttributeUpdateCatalogItem(
                attribute_id=additional["additional_data_definition_id"],
                attribute_name_en=get_english_message(additional["name"]),
                attribute_name_ja=get_required_japanese_message(additional["name"]),
                attribute_name_vi=get_optional_message(additional["name"], lang="vi-VN"),
                attribute_type=additional["type"],
                label_name_ens=sorted(label_names_by_attribute_id.get(additional["additional_data_definition_id"], [])),
                read_only=additional["read_only"],
                default=additional["default"],
                keybind=get_catalog_keybind(additional["keybind"]),
                choices=[
                    ChoiceUpdateCatalogItem(
                        choice_id=choice["choice_id"],
                        choice_name_en=get_english_message(choice["name"]),
                        choice_name_ja=get_required_japanese_message(choice["name"]),
                        is_default=is_default_choice(additional=additional, choice=choice),
                        keybind=get_catalog_keybind(choice["keybind"]),
                    )
                    for choice in additional["choices"]
                ],
            )
        )
        for additional in annotation_specs["additionals"]
    ]


def dump_catalog(catalog: list[BaseModel]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in catalog]


def parse_update_attributes_from_text(
    *,
    text: str,
    annotation_specs: dict[str, Any],
    llm_model: str,
    temp_dir: Path | None = None,
) -> AttributeUpdateParseResult:
    """
    自然言語のテキストから属性更新候補を抽出します。
    """
    attribute_catalog = get_attribute_update_catalog(annotation_specs)
    messages = [
        {
            "role": "developer",
            "content": """
あなたは、自然言語で書かれたアノテーション仕様の変更内容から、Annofabの既存属性更新情報を抽出するAIです。
抽出した結果は、必ずAttributeUpdateParseResult形式で返してください。

既存属性を更新する内容だけを attributes に入れてください。
新規属性の追加、ラベルの追加・更新、属性制約、作業手順、品質基準は attributes に入れず無視してください。
更新対象は必ず既存属性一覧の attribute_id で指定してください。
既存選択肢を更新する場合は、必ず既存選択肢一覧の choice_id で指定してください。
attribute_type は更新できません。
変更が必要な項目だけを出力してください。
既存値と同じ値だけの更新は出力しないでください。
選択肢の追加・削除は update_attributes では実行できないため、unresolved_texts に入れてください。
更新対象属性や選択肢を特定できない場合や、更新内容が曖昧な場合は unresolved_texts に入れてください。
unresolved_texts には、解釈できなかった原文を text、解釈できなかった理由を reason、解釈に必要な補足情報を required_information に出力してください。
""".strip(),
        },
        {
            "role": "user",
            "content": f"""
以下の自然言語テキストから、Annofabの既存属性更新情報を抽出してください。

## 入力テキスト
{text}

## 既存属性一覧
{json.dumps(dump_catalog(attribute_catalog), ensure_ascii=False, indent=2)}
""".strip(),
        },
    ]

    if temp_dir is not None:
        print_json(messages, temp_dir / "llm_prompt.json")

    response = completion(
        model=llm_model,
        messages=messages,
        response_format=AttributeUpdateParseResult,
    )
    content = response.choices[0].message.content

    if temp_dir is not None:
        (temp_dir / "llm_raw_response.txt").write_text(content, encoding="utf-8")

    result = AttributeUpdateParseResult.model_validate_json(content)
    logger.info(
        f"[LLM] 属性更新情報を解析しました。 :: attribute_count={len(result.attributes)}, warnings={len(result.warnings)}, "
        f"unresolved_texts={len(result.unresolved_texts)}, total_tokens={response.usage.total_tokens}, "
        f"prompt_tokens={response.usage.prompt_tokens}, completion_tokens={response.usage.completion_tokens}"
    )

    if temp_dir is not None:
        print_json(dump_catalog(attribute_catalog), temp_dir / "attribute_catalog.json")
        print_json(result.model_dump(mode="json"), temp_dir / "llm_completion.json")

    return result


def dump_choice_update_for_annofab(choice: ChoiceUpdateCandidate) -> dict[str, Any]:
    dumped = choice.model_dump(mode="json", exclude_none=True)
    if "keybind" in choice.model_fields_set and choice.keybind is None:
        dumped["keybind"] = None
    return dumped


def dump_attribute_update_for_annofab(attribute: AttributeUpdateCandidate) -> dict[str, Any]:
    dumped = attribute.model_dump(mode="json", exclude_none=True)
    if "choice_updates" in dumped:
        dumped["choice_updates"] = [dump_choice_update_for_annofab(choice) for choice in attribute.choice_updates or []]
    return dumped


def normalize_parsed_update_attributes(result: AttributeUpdateParseResult, annotation_specs: dict[str, Any]) -> AttributeUpdateParseResult:
    """
    解析済み属性更新候補を正規化します。
    """
    attribute_catalog = get_attribute_update_catalog(annotation_specs)
    attributes_by_id = {attribute.attribute_id: attribute for attribute in attribute_catalog}
    seen_attribute_ids: set[str] = set()
    normalized_attributes: list[AttributeUpdateCandidate] = []
    warnings = list(result.warnings)

    for attribute in result.attributes:
        existing_attribute = attributes_by_id.get(attribute.attribute_id)
        if existing_attribute is None:
            warnings.append(f"存在しない属性ID'{attribute.attribute_id}'は update_attributes の更新対象ではないため、出力から除外しました。")
            continue
        if attribute.attribute_id in seen_attribute_ids:
            warnings.append(f"属性ID'{attribute.attribute_id}'が重複していたため、先頭の1件だけを採用しました。")
            continue

        normalized_choice_updates = normalize_choice_updates(attribute, existing_attribute, warnings)
        normalized_attribute = attribute.model_copy(update={"choice_updates": normalized_choice_updates})
        if set(dump_attribute_update_for_annofab(normalized_attribute)) == {"attribute_id"}:
            warnings.append(f"属性ID'{attribute.attribute_id}'には更新項目がないため、出力から除外しました。")
            continue

        seen_attribute_ids.add(attribute.attribute_id)
        normalized_attributes.append(normalized_attribute)

    return AttributeUpdateParseResult(attributes=normalized_attributes, warnings=warnings, unresolved_texts=result.unresolved_texts)


def normalize_choice_updates(
    attribute: AttributeUpdateCandidate,
    existing_attribute: AttributeUpdateCatalogItem,
    warnings: list[str],
) -> list[ChoiceUpdateCandidate] | None:
    if attribute.choice_updates is None:
        return None

    if existing_attribute.attribute_type not in {AdditionalDataDefinitionType.CHOICE.value, AdditionalDataDefinitionType.SELECT.value}:
        warnings.append(f"属性ID'{attribute.attribute_id}'は選択肢系属性ではないため、choice_updates を出力から除外しました。")
        return None

    existing_choice_ids = {choice.choice_id for choice in existing_attribute.choices}
    seen_choice_ids: set[str] = set()
    normalized_choice_updates: list[ChoiceUpdateCandidate] = []
    for choice_update in attribute.choice_updates:
        if choice_update.choice_id not in existing_choice_ids:
            warnings.append(f"存在しない選択肢ID'{choice_update.choice_id}'は update_attributes の更新対象ではないため、出力から除外しました。")
            continue
        if choice_update.choice_id in seen_choice_ids:
            warnings.append(f"選択肢ID'{choice_update.choice_id}'が重複していたため、先頭の1件だけを採用しました。")
            continue
        if set(dump_choice_update_for_annofab(choice_update)) == {"choice_id"}:
            warnings.append(f"選択肢ID'{choice_update.choice_id}'には更新項目がないため、出力から除外しました。")
            continue
        seen_choice_ids.add(choice_update.choice_id)
        normalized_choice_updates.append(choice_update)

    return normalized_choice_updates or None


def to_annofab_update_attributes(result: AttributeUpdateParseResult) -> list[dict[str, Any]]:
    """
    解析結果を ``annotation_specs update_attributes --attribute_json`` に渡せるJSONへ変換します。
    """
    return [dump_attribute_update_for_annofab(attribute) for attribute in result.attributes]


def log_parse_warnings(result: AttributeUpdateParseResult) -> None:
    for warning in result.warnings:
        logger.warning(f"属性更新情報の解析時に注意事項がありました。 :: {warning}")
    for unresolved_text in result.unresolved_texts:
        logger.warning(f"属性更新ルールとして解釈できないテキストがありました。 :: {format_unresolved_text(unresolved_text)}")


def collect_supplements_interactively(unresolved_texts: list[UnresolvedText]) -> list[str]:
    supplements: list[str] = []
    for unresolved_text in unresolved_texts:
        prompt_lines = [
            f"解釈できないテキスト: {unresolved_text.text}",
            f"理由: {unresolved_text.reason}",
        ]
        if unresolved_text.required_information:
            prompt_lines.append(f"必要な補足情報: {', '.join(unresolved_text.required_information)}")
        prompt_lines.append("補足情報を入力してください（スキップする場合は空Enterを押してください）: ")
        supplement = input("\n".join(prompt_lines)).strip()
        if supplement != "":
            supplements.append(supplement)
    return supplements


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
    result = parse_update_attributes_from_text(text=current_text, annotation_specs=annotation_specs, llm_model=args.model, temp_dir=temp_dir)
    result = normalize_parsed_update_attributes(result, annotation_specs)
    print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")
    log_parse_warnings(result)

    interactive = not args.no_interactive and not args.yes
    while result.unresolved_texts and interactive:
        supplements = collect_supplements_interactively(result.unresolved_texts)
        if len(supplements) == 0:
            break
        logger.info(f"{len(supplements)}件の補足情報をもとに再解析します。")
        supplement_text = "\n".join(supplements)
        current_text = f"{current_text}\n\n## 補足情報\n{supplement_text}"
        result = parse_update_attributes_from_text(text=current_text, annotation_specs=annotation_specs, llm_model=args.model, temp_dir=temp_dir)
        result = normalize_parsed_update_attributes(result, annotation_specs)
        print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")
        log_parse_warnings(result)

    annofab_attributes = to_annofab_update_attributes(result)
    if len(annofab_attributes) == 0:
        raise ValueError("アノテーション仕様で更新可能な属性を抽出できませんでした。")

    print_json(annofab_attributes, output=args.output)
    if args.output is None:
        logger.info("更新対象属性のJSONを標準出力に出力しました。")
    else:
        logger.info(f"更新対象属性のJSONをファイルに出力しました。 :: output='{args.output}'")
    logger.info(OUTPUT_USAGE_MESSAGE)
    print_json(annofab_attributes, temp_dir / "annofab_attributes.json")
    logger.info("属性更新情報の自然言語解析が完了しました。")


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
        help="属性更新に関するアノテーションルールやアノテーション仕様の自然言語。先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
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
        "自然言語から既存属性更新用JSONを生成します。",
        description=f"自然言語から既存属性更新用JSONを生成します。\n{OUTPUT_USAGE_MESSAGE}",
    )
    add_argument_to_parser(parser)
    parser.set_defaults(func=main)
    return parser
