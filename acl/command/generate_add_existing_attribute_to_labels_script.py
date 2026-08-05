import argparse
import json
import shlex
from pathlib import Path
from typing import Any

from litellm import completion
from loguru import logger
from pydantic import BaseModel, Field, field_validator

import acl.common.cli
from acl.command.generate_add_attributes_json import get_annotation_specs, get_required_japanese_message
from acl.command.generate_add_labels_json import STRUCTURED_OUTPUT_MODEL_CONFIG, UnresolvedText, format_unresolved_text
from acl.command.generate_update_attributes_json import collect_supplements_interactively
from acl.common.cli import read_at_file
from acl.common.utils import output_string, print_json
from acl.common.xdg_util import create_command_temp_dir

COMMAND_NAME = "generate_add_existing_attribute_to_labels_script"
"""コマンド名です。"""


class ExistingAttributeCatalogItem(BaseModel):
    """LLMへ渡す既存属性情報です。"""

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    attribute_id: str = Field(description="既存属性のIDです。")
    """既存属性のIDです。"""

    attribute_name_en: str = Field(description="既存属性名（英語）です。")
    """既存属性名（英語）です。"""

    attribute_name_ja: str = Field(description="既存属性名（日本語）です。")
    """既存属性名（日本語）です。"""


class ExistingAttributeLabelAssignment(BaseModel):
    """既存属性をラベルへ紐付ける候補です。"""

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    attribute_id: str = Field(description="紐付ける既存属性のIDです。")
    """紐付ける既存属性のIDです。"""

    label_name_ens: list[str] = Field(description="属性を紐付けるラベル名（英語）の一覧です。")
    """属性を紐付けるラベル名（英語）の一覧です。"""

    @field_validator("label_name_ens")
    @classmethod
    def validate_label_name_ens(cls, value: list[str]) -> list[str]:
        """ラベル名一覧を検証します。"""
        normalized_values = [label_name_en.strip() for label_name_en in value if label_name_en.strip()]
        if len(normalized_values) == 0:
            raise ValueError("`label_name_ens` には1件以上のラベル名を指定してください。")
        return list(dict.fromkeys(normalized_values))


class ExistingAttributeLabelAssignmentParseResult(BaseModel):
    """既存属性をラベルへ紐付ける自然言語解析結果です。"""

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    assignments: list[ExistingAttributeLabelAssignment] = Field(description="解析できた既存属性とラベルの紐付け一覧です。")
    """解析できた既存属性とラベルの紐付け一覧です。"""

    warnings: list[str] = Field(default_factory=list, description="解析時の注意事項です。")
    """解析時の注意事項です。"""

    unresolved_texts: list[UnresolvedText] = Field(default_factory=list, description="解釈できなかった原文、理由、必要な補足情報です。")
    """解釈できなかった原文、理由、必要な補足情報です。"""


def get_existing_attribute_catalog(annotation_specs: dict[str, Any]) -> list[ExistingAttributeCatalogItem]:
    """
    LLMへ渡す既存属性一覧を生成します。

    Args:
        annotation_specs: アノテーション仕様(v3)

    Returns:
        既存属性一覧
    """
    return [
        ExistingAttributeCatalogItem(
            attribute_id=attribute["additional_data_definition_id"],
            attribute_name_en=next(message["message"] for message in attribute["name"]["messages"] if message["lang"] == "en-US"),
            attribute_name_ja=get_required_japanese_message(attribute["name"]),
        )
        for attribute in annotation_specs["additionals"]
    ]


def parse_existing_attribute_label_assignments_from_text(
    *,
    text: str,
    existing_attributes: list[ExistingAttributeCatalogItem],
    llm_model: str,
    temp_dir: Path | None = None,
) -> ExistingAttributeLabelAssignmentParseResult:
    """
    自然言語のテキストから既存属性とラベルの紐付け候補を抽出します。

    Args:
        text: アノテーションルールが記載された自然言語
        existing_attributes: 既存属性一覧
        llm_model: 使用するLLMのモデル
        temp_dir: 任意の一時ディレクトリ

    Returns:
        解析結果
    """
    messages = [
        {
            "role": "developer",
            "content": """
あなたは、自然言語で書かれたアノテーション仕様の変更内容から、既存属性をラベルへ追加する情報を抽出するAIです。
抽出した結果は、必ずExistingAttributeLabelAssignmentParseResult形式で返してください。

既存属性を既存または新規のラベルへ紐付ける指示だけを assignments に入れてください。
新規属性の追加、既存属性の設定更新、選択肢の追加・更新、ラベルの追加・更新、属性制約、削除、並べ替えは assignments に入れず無視してください。
attribute_id には必ず既存属性一覧にあるIDを指定してください。
label_name_ens には紐付け先ラベルの英語名を指定してください。新規ラベルを先に追加する指示がある場合も、その英語名を指定できます。
属性またはラベルを特定できない場合は assignments に入れず unresolved_texts に入れてください。
unresolved_texts には、解釈できなかった原文を text、理由を reason、解釈に必要な補足情報を required_information に出力してください。
""".strip(),
        },
        {
            "role": "user",
            "content": f"""
以下の自然言語テキストから、既存属性をラベルへ追加する情報を抽出してください。

## 入力テキスト
{text}

## 既存属性一覧
{json.dumps([attribute.model_dump(mode="json") for attribute in existing_attributes], ensure_ascii=False, indent=2)}
""".strip(),
        },
    ]
    if temp_dir is not None:
        print_json(messages, temp_dir / "llm_prompt.json")

    response = completion(model=llm_model, messages=messages, response_format=ExistingAttributeLabelAssignmentParseResult)
    content = response.choices[0].message.content
    if temp_dir is not None:
        (temp_dir / "llm_raw_response.txt").write_text(content, encoding="utf-8")

    result = ExistingAttributeLabelAssignmentParseResult.model_validate_json(content)
    logger.info(
        f"[LLM] 既存属性をラベルへ紐付ける情報を解析しました。 :: assignment_count={len(result.assignments)}, "
        f"warnings={len(result.warnings)}, unresolved_texts={len(result.unresolved_texts)}, total_tokens={response.usage.total_tokens}, "
        f"prompt_tokens={response.usage.prompt_tokens}, completion_tokens={response.usage.completion_tokens}"
    )
    if temp_dir is not None:
        print_json(result.model_dump(mode="json"), temp_dir / "llm_completion.json")
    return result


def normalize_assignments(
    result: ExistingAttributeLabelAssignmentParseResult,
    existing_attributes: list[ExistingAttributeCatalogItem],
) -> ExistingAttributeLabelAssignmentParseResult:
    """
    既存属性とラベルの紐付け候補を正規化します。

    Args:
        result: 解析結果
        existing_attributes: 既存属性一覧

    Returns:
        正規化済み解析結果
    """
    existing_attribute_ids = {attribute.attribute_id for attribute in existing_attributes}
    assignments_by_attribute_id: dict[str, list[str]] = {}
    warnings = list(result.warnings)
    for assignment in result.assignments:
        if assignment.attribute_id not in existing_attribute_ids:
            warnings.append(f"属性ID'{assignment.attribute_id}'はアノテーション仕様に存在しないため、出力から除外しました。")
            continue
        label_name_ens = assignments_by_attribute_id.setdefault(assignment.attribute_id, [])
        for label_name_en in assignment.label_name_ens:
            if label_name_en not in label_name_ens:
                label_name_ens.append(label_name_en)

    return ExistingAttributeLabelAssignmentParseResult(
        assignments=[ExistingAttributeLabelAssignment(attribute_id=attribute_id, label_name_ens=label_name_ens) for attribute_id, label_name_ens in assignments_by_attribute_id.items()],
        warnings=warnings,
        unresolved_texts=result.unresolved_texts,
    )


def generate_bash_script(*, project_id: str, assignments: list[ExistingAttributeLabelAssignment]) -> str:
    """
    既存属性をラベルへ追加するBashスクリプトを生成します。

    Args:
        project_id: AnnofabのプロジェクトID
        assignments: 属性とラベルの紐付け一覧

    Returns:
        Bashスクリプト
    """
    lines: list[str] = []
    for assignment in assignments:
        command = [
            "annofabcli",
            "annotation_specs",
            "add_existing_attribute_to_labels",
            "--project_id",
            project_id,
            "--attribute_id",
            assignment.attribute_id,
            "--label_name_en",
            *assignment.label_name_ens,
        ]
        lines.append(" ".join(shlex.quote(value) for value in command))
    return "\n".join(lines) + ("\n" if lines else "")


def log_parse_warnings(result: ExistingAttributeLabelAssignmentParseResult) -> None:
    """解析時の注意事項と未解決テキストをログに出力します。"""
    for warning in result.warnings:
        logger.warning(f"既存属性のラベル紐付け解析時に注意事項がありました。 :: {warning}")
    for unresolved_text in result.unresolved_texts:
        logger.warning(f"既存属性のラベル紐付けとして解釈できないテキストがありました。 :: {format_unresolved_text(unresolved_text)}")


def main(args: argparse.Namespace) -> None:
    annotation_rule = read_at_file(args.annotation_rule)
    temp_dir = create_command_temp_dir(COMMAND_NAME)
    temp_dir.mkdir(exist_ok=True)
    annotation_specs = get_annotation_specs(annotation_specs_json_file=None, project_id=args.project_id, annofab_pat=args.annofab_pat)
    existing_attributes = get_existing_attribute_catalog(annotation_specs)
    if len(existing_attributes) == 0:
        output_string("", args.output)
        logger.info("既存属性がないため、属性をラベルへ紐付けるスクリプトは出力しません。")
        return

    current_text = annotation_rule
    result = normalize_assignments(
        parse_existing_attribute_label_assignments_from_text(text=current_text, existing_attributes=existing_attributes, llm_model=args.model, temp_dir=temp_dir),
        existing_attributes,
    )
    print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")
    log_parse_warnings(result)
    interactive = not args.no_interactive and not args.yes
    while result.unresolved_texts and interactive:
        supplements = collect_supplements_interactively(result.unresolved_texts)
        if len(supplements) == 0:
            break
        supplement_text = "\n".join(supplements)
        current_text = f"{current_text}\n\n## 補足情報\n{supplement_text}"
        result = normalize_assignments(
            parse_existing_attribute_label_assignments_from_text(text=current_text, existing_attributes=existing_attributes, llm_model=args.model, temp_dir=temp_dir),
            existing_attributes,
        )
        print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")
        log_parse_warnings(result)

    output_string(generate_bash_script(project_id=args.project_id, assignments=result.assignments), args.output)
    logger.info(f"既存属性をラベルへ紐付けるスクリプトを出力しました。 :: assignment_count={len(result.assignments)}, output='{args.output}'")


def add_argument_to_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-p", "--project_id", type=str, required=True, help="AnnofabのプロジェクトID")
    parser.add_argument(
        "--annotation_rule",
        type=str,
        required=True,
        help="既存属性をラベルへ紐付ける情報が記載された自然言語。先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
    )
    parser.add_argument("-o", "--output", type=Path, required=True, help="出力先のBashスクリプトファイルパス")
    parser.add_argument("--no_interactive", action="store_true", dest="no_interactive", help="未解決テキストが存在しても、補足情報の入力を求めずに終了します。")


def add_parser(subparsers: argparse._SubParsersAction | None = None) -> argparse.ArgumentParser:
    parser = acl.common.cli.add_parser(
        subparsers,
        COMMAND_NAME,
        argparse.SUPPRESS,
        description="generate_scriptが内部で利用するコマンドです。",
    )
    add_argument_to_parser(parser)
    parser.set_defaults(func=main)
    return parser
