import argparse
import json
from pathlib import Path
from typing import Any, Literal

from litellm import completion
from loguru import logger
from pydantic import BaseModel, Field, model_validator

import acl.common.cli
from acl.command.generate_add_labels_json import (
    STRUCTURED_OUTPUT_MODEL_CONFIG,
    FieldValues,
    KeybindCandidate,
    UnresolvedText,
    dump_label_catalog,
    format_unresolved_text,
    get_annotation_specs,
    get_catalog_keybind,
    get_required_message,
)
from acl.common.cli import read_at_file
from acl.common.utils import print_json
from acl.common.xdg_util import create_command_temp_dir

COMMAND_NAME = "generate_update_labels_json"
OUTPUT_USAGE_MESSAGE = "出力されるJSONは、annofabcli annotation_specs update_labels コマンドの --label_json 引数にそのまま指定できます。"
"""出力JSONの利用方法に関するメッセージです。"""


class LabelUpdateCatalogItem(BaseModel):
    """
    LLMへ渡すための既存ラベル情報です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    label_id: str = Field(description="既存ラベルのIDです。")
    """既存ラベルのIDです。"""

    label_name_en: str = Field(description="既存ラベル名（英語）です。")
    """既存ラベル名（英語）です。"""

    label_name_ja: str = Field(description="既存ラベル名（日本語）です。")
    """既存ラベル名（日本語）です。"""

    annotation_type: str = Field(description="既存ラベルのアノテーション種類です。")
    """既存ラベルのアノテーション種類です。"""

    color: str | None = Field(description="既存ラベルの色です。")
    """既存ラベルの色です。"""

    keybind: KeybindCandidate | None = Field(description="既存ラベルに設定されたキーボードショートカットです。")
    """既存ラベルに設定されたキーボードショートカットです。"""

    field_values: dict[str, Any] = Field(description="既存ラベルごとの制約、表示設定、許容誤差などです。")
    """既存ラベルごとの制約、表示設定、許容誤差などです。"""


class LabelUpdateCandidate(BaseModel):
    """
    更新候補のラベル情報です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    label_id: str = Field(description="更新対象ラベルのIDです。既存ラベル一覧に存在するIDを指定してください。")
    """更新対象ラベルのIDです。"""

    label_name_ja: str | None = Field(default=None, description="更新後のラベル名（日本語）です。")
    """更新後のラベル名（日本語）です。"""

    color: str | None = Field(default=None, description="更新後のラベル色です。指定する場合は `#RRGGBB` 形式にしてください。")
    """更新後のラベル色です。"""

    keybind: KeybindCandidate | None = Field(default=None, description="更新後のキーボードショートカットです。")
    """更新後のキーボードショートカットです。"""

    field_values: FieldValues | None = Field(default=None, description="更新後のラベルごとの制約、表示設定、許容誤差などの field_values です。")
    """更新後の field_values です。"""

    field_values_operation: Literal["merge", "replace"] | None = Field(default=None, description="field_values の更新方法です。")
    """field_values の更新方法です。"""

    @model_validator(mode="after")
    def validate_update_content(self) -> "LabelUpdateCandidate":
        if self.label_id.strip() == "":
            raise ValueError("`label_id` には空でない文字列を指定してください。")
        return self


class LabelUpdateParseResult(BaseModel):
    """
    ラベル更新の自然言語解析結果です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    labels: list[LabelUpdateCandidate] = Field(description="解析できた更新対象ラベルの一覧です。")
    """解析できたラベル更新候補の一覧です。"""

    warnings: list[str] = Field(default_factory=list, description="解析時の注意事項です。")
    """解析時の注意事項です。"""

    unresolved_texts: list[UnresolvedText] = Field(default_factory=list, description="ラベル更新ルールとして解釈できなかった原文、理由、必要な補足情報です。")
    """ラベル更新ルールとして解釈できなかった原文、理由、必要な補足情報です。"""


def get_label_update_catalog(annotation_specs: dict[str, Any]) -> list[LabelUpdateCatalogItem]:
    """
    LLMへ渡すための既存ラベル一覧を生成します。

    Args:
        annotation_specs: アノテーション仕様(v3)

    Returns:
        既存ラベル一覧
    """
    return [
        LabelUpdateCatalogItem(
            label_id=label["label_id"],
            label_name_en=get_required_message(label["label_name"], lang="en-US"),
            label_name_ja=get_required_message(label["label_name"], lang="ja-JP"),
            annotation_type=label["annotation_type"],
            color=label["color"],
            keybind=get_catalog_keybind(label["keybind"]),
            field_values=label["field_values"],
        )
        for label in annotation_specs["labels"]
    ]


def parse_update_labels_from_text(
    *,
    text: str,
    annotation_specs: dict[str, Any],
    llm_model: str,
    temp_dir: Path | None = None,
) -> LabelUpdateParseResult:
    """
    自然言語のテキストからラベル更新候補を抽出します。
    """
    label_catalog = get_label_update_catalog(annotation_specs)
    messages = [
        {
            "role": "developer",
            "content": """
あなたは、自然言語で書かれたアノテーション仕様の変更内容から、Annofabの既存ラベル更新情報を抽出するAIです。
抽出した結果は、必ずLabelUpdateParseResult形式で返してください。

既存ラベルを更新する内容だけを labels に入れてください。
新規ラベルの追加、属性の追加・更新、属性制約、作業手順、品質基準は labels に入れず無視してください。
更新対象は必ず既存ラベル一覧の label_id で指定してください。
label_id、label_name_en、annotation_type は更新できません。
変更が必要な項目だけを出力してください。
既存値と同じ値だけの更新は出力しないでください。
更新対象ラベルを特定できない場合や、更新内容が曖昧な場合は unresolved_texts に入れてください。
unresolved_texts には、解釈できなかった原文を text、解釈できなかった理由を reason、解釈に必要な補足情報を required_information に出力してください。
""".strip(),
        },
        {
            "role": "user",
            "content": f"""
以下の自然言語テキストから、Annofabの既存ラベル更新情報を抽出してください。

## 入力テキスト
{text}

## 既存ラベル一覧
{json.dumps(dump_label_catalog(label_catalog), ensure_ascii=False, indent=2)}
""".strip(),
        },
    ]

    if temp_dir is not None:
        print_json(messages, temp_dir / "llm_prompt.json")

    response = completion(
        model=llm_model,
        messages=messages,
        response_format=LabelUpdateParseResult,
    )
    content = response.choices[0].message.content

    if temp_dir is not None:
        (temp_dir / "llm_raw_response.txt").write_text(content, encoding="utf-8")

    result = LabelUpdateParseResult.model_validate_json(content)
    logger.info(
        f"[LLM] ラベル更新情報を解析しました。 :: label_count={len(result.labels)}, warnings={len(result.warnings)}, "
        f"unresolved_texts={len(result.unresolved_texts)}, total_tokens={response.usage.total_tokens}, "
        f"prompt_tokens={response.usage.prompt_tokens}, completion_tokens={response.usage.completion_tokens}"
    )

    if temp_dir is not None:
        print_json(dump_label_catalog(label_catalog), temp_dir / "label_catalog.json")
        print_json(result.model_dump(mode="json"), temp_dir / "llm_completion.json")

    return result


def dump_label_update_for_annofab(label: LabelUpdateCandidate) -> dict[str, Any]:
    dumped = label.model_dump(mode="json", exclude_none=True)
    field_values = dumped.get("field_values")
    if isinstance(field_values, dict):
        dumped["field_values"] = {key: value for key, value in field_values.items() if value is not None}
        if len(dumped["field_values"]) == 0:
            dumped.pop("field_values")
    return dumped


def normalize_parsed_update_labels(result: LabelUpdateParseResult, annotation_specs: dict[str, Any]) -> LabelUpdateParseResult:
    """
    解析済みラベル更新候補を正規化します。
    """
    existing_label_ids = {label.label_id for label in get_label_update_catalog(annotation_specs)}
    seen_label_ids: set[str] = set()
    normalized_labels: list[LabelUpdateCandidate] = []
    warnings = list(result.warnings)

    for label in result.labels:
        if label.label_id not in existing_label_ids:
            warnings.append(f"存在しないラベルID'{label.label_id}'は update_labels の更新対象ではないため、出力から除外しました。")
            continue
        if label.label_id in seen_label_ids:
            warnings.append(f"ラベルID'{label.label_id}'が重複していたため、先頭の1件だけを採用しました。")
            continue
        if set(dump_label_update_for_annofab(label)) == {"label_id"}:
            warnings.append(f"ラベルID'{label.label_id}'には更新項目がないため、出力から除外しました。")
            continue
        seen_label_ids.add(label.label_id)
        normalized_labels.append(label)

    return LabelUpdateParseResult(labels=normalized_labels, warnings=warnings, unresolved_texts=result.unresolved_texts)


def to_annofab_update_labels(result: LabelUpdateParseResult) -> list[dict[str, Any]]:
    """
    解析結果を ``annotation_specs update_labels --label_json`` に渡せるJSONへ変換します。
    """
    return [dump_label_update_for_annofab(label) for label in result.labels]


def log_parse_warnings(result: LabelUpdateParseResult) -> None:
    for warning in result.warnings:
        logger.warning(f"ラベル更新情報の解析時に注意事項がありました。 :: {warning}")
    for unresolved_text in result.unresolved_texts:
        logger.warning(f"ラベル更新ルールとして解釈できないテキストがありました。 :: {format_unresolved_text(unresolved_text)}")


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
    result = parse_update_labels_from_text(text=current_text, annotation_specs=annotation_specs, llm_model=args.model, temp_dir=temp_dir)
    result = normalize_parsed_update_labels(result, annotation_specs)
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
        result = parse_update_labels_from_text(text=current_text, annotation_specs=annotation_specs, llm_model=args.model, temp_dir=temp_dir)
        result = normalize_parsed_update_labels(result, annotation_specs)
        print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")
        log_parse_warnings(result)

    annofab_labels = to_annofab_update_labels(result)
    if len(annofab_labels) == 0:
        raise ValueError("アノテーション仕様で更新可能なラベルを抽出できませんでした。")

    print_json(annofab_labels, output=args.output)
    logger.info(OUTPUT_USAGE_MESSAGE)
    print_json(annofab_labels, temp_dir / "annofab_labels.json")
    logger.info("ラベル更新情報の自然言語解析が完了しました。")


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
        help="ラベル更新に関するアノテーションルールやアノテーション仕様の自然言語。先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
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
        "自然言語から既存ラベル更新用JSONを生成します。",
        description=f"自然言語から既存ラベル更新用JSONを生成します。\n{OUTPUT_USAGE_MESSAGE}",
    )
    add_argument_to_parser(parser)
    parser.set_defaults(func=main)
    return parser
