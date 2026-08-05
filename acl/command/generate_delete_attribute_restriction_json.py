import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from annofabcli.annotation_specs.attribute_restriction import AttributeRestrictionMessage
from litellm import completion
from loguru import logger
from pydantic import BaseModel, Field

import acl.common.cli
from acl.command.generate_add_attributes_json import get_annotation_specs
from acl.command.generate_add_labels_json import STRUCTURED_OUTPUT_MODEL_CONFIG, UnresolvedText, format_unresolved_text
from acl.command.generate_update_attributes_json import collect_supplements_interactively
from acl.common.cli import read_at_file
from acl.common.utils import output_string, print_json
from acl.common.xdg_util import create_command_temp_dir

COMMAND_NAME = "generate_delete_attribute_restriction_json"
"""コマンド名です。"""

OUTPUT_USAGE_MESSAGE = "出力されるJSONは、annofabcli annotation_specs delete_attribute_restriction コマンドの --restriction_json 引数にそのまま指定できます。"
"""出力JSONの利用方法に関するメッセージです。"""


class ExistingRestriction(BaseModel):
    """LLMへ渡す既存属性制約の情報です。"""

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    index: int = Field(description="この実行中だけ有効な既存属性制約の番号です。")
    restriction_text: str = Field(description="既存属性制約の人間向け表示です。")


class DeleteRestrictionParseResult(BaseModel):
    """属性制約削除の自然言語解析結果です。"""

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    selected_indexes: list[int] = Field(description="削除対象として選択した既存属性制約の番号一覧です。")
    warnings: list[str] = Field(default_factory=list, description="解析時の注意事項です。")
    unresolved_texts: list[UnresolvedText] = Field(default_factory=list, description="削除対象として特定できなかった原文、理由、必要な補足情報です。")


@dataclass(frozen=True)
class ResolvedRestrictionsForDelete:
    """削除対象の属性制約を解決した結果です。"""

    restrictions: list[dict[str, Any]]
    """削除対象として解決した属性制約です。"""

    restriction_texts: list[str]
    """削除対象として解決した属性制約の人間向け表示です。"""

    warnings: list[str]
    """解決時に発生した注意事項です。"""


def get_existing_restrictions(annotation_specs: dict[str, Any]) -> tuple[list[ExistingRestriction], list[dict[str, Any]]]:
    """LLMへ渡す既存属性制約と、その元のJSONを取得します。"""
    restrictions = annotation_specs["restrictions"]
    message_obj = AttributeRestrictionMessage(
        labels=annotation_specs["labels"],
        additionals=annotation_specs["additionals"],
        raise_if_not_found=True,
    )
    existing_restrictions = [
        ExistingRestriction(
            index=index,
            restriction_text=message_obj.get_restriction_text(restriction["additional_data_definition_id"], restriction["condition"]),
        )
        for index, restriction in enumerate(restrictions, start=1)
    ]
    return existing_restrictions, restrictions


def parse_delete_restrictions_from_text(
    *,
    text: str,
    existing_restrictions: list[ExistingRestriction],
    llm_model: str,
    temp_dir: Path | None = None,
) -> DeleteRestrictionParseResult:
    """自然言語のテキストから削除対象の既存属性制約を選択します。"""
    messages = [
        {
            "role": "developer",
            "content": """
あなたは、自然言語で書かれたアノテーション仕様の変更内容から、削除する既存のAnnofab属性制約を選択するAIです。
抽出した結果は、必ずDeleteRestrictionParseResult形式で返してください。

selected_indexes には、既存属性制約一覧に含まれる番号だけを入れてください。番号は変更・新規作成しないでください。
削除対象を一意に特定できる場合だけ selected_indexes に入れてください。
複数の既存属性制約に一致する、または既存属性制約に存在しない場合は selected_indexes に入れず、unresolved_texts に入れてください。
unresolved_texts には、解釈できなかった原文を text、理由を reason、必要な補足情報を required_information に出力してください。
追加・更新・並べ替え、作業手順、品質基準は削除対象に含めないでください。
""".strip(),
        },
        {
            "role": "user",
            "content": f"""
以下の自然言語テキストから、削除する既存属性制約を選択してください。

## 入力テキスト
{text}

## 既存属性制約一覧
{json.dumps([restriction.model_dump(mode="json") for restriction in existing_restrictions], ensure_ascii=False, indent=2)}
""".strip(),
        },
    ]
    if temp_dir is not None:
        print_json(messages, temp_dir / "llm_prompt.json")

    response = completion(model=llm_model, messages=messages, response_format=DeleteRestrictionParseResult)
    content = response.choices[0].message.content
    if temp_dir is not None:
        (temp_dir / "llm_raw_response.txt").write_text(content, encoding="utf-8")

    result = DeleteRestrictionParseResult.model_validate_json(content)
    logger.info(
        f"[LLM] 削除対象の属性制約を解析しました。 :: selected_count={len(result.selected_indexes)}, warnings={len(result.warnings)}, "
        f"unresolved_texts={len(result.unresolved_texts)}, total_tokens={response.usage.total_tokens}, "
        f"prompt_tokens={response.usage.prompt_tokens}, completion_tokens={response.usage.completion_tokens}"
    )
    if temp_dir is not None:
        print_json([restriction.model_dump(mode="json") for restriction in existing_restrictions], temp_dir / "existing_restrictions.json")
        print_json(result.model_dump(mode="json"), temp_dir / "llm_completion.json")
    return result


def resolve_selected_restrictions(
    result: DeleteRestrictionParseResult,
    *,
    existing_restrictions: list[ExistingRestriction],
    restrictions: list[dict[str, Any]],
) -> ResolvedRestrictionsForDelete:
    """LLMが選択した番号を既存の完全な属性制約JSONへ解決します。"""
    restriction_by_index = {restriction.index: (restriction.restriction_text, restrictions[restriction.index - 1]) for restriction in existing_restrictions}
    selected_indexes: set[int] = set()
    resolved_restrictions: list[dict[str, Any]] = []
    restriction_texts: list[str] = []
    warnings = list(result.warnings)

    for index in result.selected_indexes:
        if index not in restriction_by_index:
            warnings.append(f"属性制約番号'{index}'は既存属性制約一覧に存在しないため、出力から除外しました。")
            continue
        if index in selected_indexes:
            warnings.append(f"属性制約番号'{index}'が重複していたため、先頭の1件だけを採用しました。")
            continue
        selected_indexes.add(index)
        restriction_text, restriction = restriction_by_index[index]
        restriction_texts.append(restriction_text)
        resolved_restrictions.append(restriction)

    return ResolvedRestrictionsForDelete(restrictions=resolved_restrictions, restriction_texts=restriction_texts, warnings=warnings)


def to_human_readable_text(resolved: ResolvedRestrictionsForDelete, result: DeleteRestrictionParseResult) -> str:
    """解析・解決結果を人が読みやすいテキストへ変換します。"""
    lines = ["[restrictions]"]
    lines.extend(f"- {restriction_text}" for restriction_text in resolved.restriction_texts)
    if len(resolved.restriction_texts) == 0:
        lines.append("(none)")
    if len(resolved.warnings) > 0:
        lines.extend(("", "[warnings]"))
        lines.extend(f"- {warning}" for warning in resolved.warnings)
    if len(result.unresolved_texts) > 0:
        lines.extend(("", "[unresolved_texts]"))
        lines.extend(f"- {format_unresolved_text(unresolved_text)}" for unresolved_text in result.unresolved_texts)
    return "\n".join(lines)


def log_parse_warnings(resolved: ResolvedRestrictionsForDelete, result: DeleteRestrictionParseResult) -> None:
    """解析・解決時の注意事項をログに出力します。"""
    for warning in resolved.warnings:
        logger.warning(f"属性制約削除の解析時に注意事項がありました。 :: {warning}")
    for unresolved_text in result.unresolved_texts:
        logger.warning(f"削除対象の属性制約として解釈できないテキストがありました。 :: {format_unresolved_text(unresolved_text)}")


def main(args: argparse.Namespace) -> None:
    """コマンドのメイン処理を実行します。"""
    restriction_text = read_at_file(args.restriction_text)
    temp_dir = create_command_temp_dir(COMMAND_NAME)
    logger.info(f"一時ディレクトリ'{temp_dir}'を作成しました。このディレクトリにLLMの入出力情報などを出力します。")
    temp_dir.mkdir(exist_ok=True)
    annotation_specs = get_annotation_specs(annotation_specs_json_file=args.annotation_specs_json_file, project_id=args.project_id, annofab_pat=args.annofab_pat)
    print_json(annotation_specs, temp_dir / "annotation_specs.json")
    existing_restrictions, restrictions = get_existing_restrictions(annotation_specs)
    if not existing_restrictions:
        raise ValueError("アノテーション仕様に属性制約が存在しません。")

    current_text = restriction_text
    result = parse_delete_restrictions_from_text(text=current_text, existing_restrictions=existing_restrictions, llm_model=args.model, temp_dir=temp_dir)
    resolved = resolve_selected_restrictions(result, existing_restrictions=existing_restrictions, restrictions=restrictions)
    print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")
    log_parse_warnings(resolved, result)

    interactive = not args.no_interactive and not args.yes
    while result.unresolved_texts and interactive:
        supplements = collect_supplements_interactively(result.unresolved_texts)
        if not supplements:
            break
        supplement_text = "\n".join(supplements)
        current_text = f"{current_text}\n\n## 補足情報\n{supplement_text}"
        result = parse_delete_restrictions_from_text(text=current_text, existing_restrictions=existing_restrictions, llm_model=args.model, temp_dir=temp_dir)
        resolved = resolve_selected_restrictions(result, existing_restrictions=existing_restrictions, restrictions=restrictions)
        print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")
        log_parse_warnings(resolved, result)

    if args.output_format == "human_readable":
        output_string(to_human_readable_text(resolved, result), output=args.output)
    else:
        print_json(resolved.restrictions, output=args.output)
        logger.info(OUTPUT_USAGE_MESSAGE)
        print_json(resolved.restrictions, temp_dir / "annofab_restrictions.json")
    logger.info("削除対象の属性制約の自然言語解析が完了しました。")


def add_argument_to_parser(parser: argparse.ArgumentParser) -> None:
    """コマンド固有の引数を追加します。"""
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--annotation_specs_json_file", type=Path, help="annotation specs v3 のJSONファイルのパス")
    group.add_argument("-p", "--project_id", type=str, help="AnnofabのプロジェクトID")
    parser.add_argument(
        "--restriction_text",
        type=str,
        required=True,
        help="削除する属性制約が記載された自然言語。先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
    )
    parser.add_argument("-o", "--output", type=Path, help="出力先のファイルパス。指定しない場合は、標準出力に出力されます。")
    parser.add_argument("--output_format", choices=["annofab_json", "human_readable"], default="annofab_json", help="出力形式")
    parser.add_argument("--no-interactive", action="store_true", dest="no_interactive", help="未解決テキストが存在しても、補足情報の入力を求めずに終了します。")


def add_parser(subparsers: argparse._SubParsersAction | None = None) -> argparse.ArgumentParser:
    """コマンドのパーサーを生成します。"""
    parser = acl.common.cli.add_parser(subparsers, COMMAND_NAME, "自然言語から属性制約削除用JSONを生成します。", description=f"自然言語から属性制約削除用JSONを生成します。\n{OUTPUT_USAGE_MESSAGE}")
    add_argument_to_parser(parser)
    parser.set_defaults(func=main)
    return parser
