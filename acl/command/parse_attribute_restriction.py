import argparse
import json
from pathlib import Path
from typing import Any

import annofabapi
from annofabapi.util.attribute_restrictions import Restriction, RestrictionAst, get_attribute_restriction_catalog
from litellm import completion
from loguru import logger
from pydantic import BaseModel, Field

import acl.common.cli
from acl.common.cli import read_at_file
from acl.common.utils import output_string, print_json
from acl.common.xdg_util import create_command_temp_dir

COMMAND_NAME = "parse_attribute_restriction"
OUTPUT_USAGE_MESSAGE = (
    "`--output_format annofab_json` で出力されるJSONは、 [annofabcli annotation_specs add_attribute_restriction]"
    "(https://annofab-cli.readthedocs.io/ja/latest/command_reference/annotation_specs/add_attribute_restriction.html) コマンドでAnnofabに登録できます。"
)
"""出力JSONの利用方法に関するメッセージです。"""


class RestrictionAstParseResult(BaseModel):
    """
    属性制約の自然言語解析結果です。
    """

    asts: list[RestrictionAst]
    """解析できた属性制約ASTの一覧です。"""
    warnings: list[str] = Field(default_factory=list)
    """解析時の注意事項です。"""
    unresolved_texts: list[str] = Field(default_factory=list)
    """属性制約として解釈できなかった原文の断片です。"""


def parse_restrictions_from_text(
    *,
    text: str,
    annotation_specs: dict[str, Any],
    llm_model: str,
    temp_dir: Path | None = None,
) -> RestrictionAstParseResult:
    """
    自然言語のテキストから属性制約ASTを抽出します。

    Args:
        text: 属性制約の情報が記載された自然言語
        annotation_specs: アノテーション仕様(v3)の情報
        llm_model: 使用するLLMのモデル
        temp_dir: 任意の一時ディレクトリ

    Returns:
        属性制約の解析結果
    """
    restriction_catalog = [item.model_dump(mode="json") for item in get_attribute_restriction_catalog(annotation_specs)]
    messages = [
        {
            "role": "developer",
            "content": """
あなたは、自然言語で書かれたアノテーションルールから、Annofabの属性制約を抽出するAIです。
抽出した制約は、必ずRestrictionAstParseResult形式で返してください。
推測で属性名・選択肢名・ラベル名を補完してはいけません。
annotation specsに存在しない属性名・選択肢名・ラベル名は出力してはいけません。
表現できない条件、曖昧な条件、属性制約ではない文は unresolved_texts に入れてください。
""".strip(),
        },
        {
            "role": "user",
            "content": f"""
以下の自然言語テキストから、表現可能な属性制約を抽出してください。

## 入力テキスト
{text}

## 属性制約カタログ
{json.dumps(restriction_catalog, ensure_ascii=False, indent=2)}
""".strip(),
        },
    ]

    if temp_dir is not None:
        print_json(messages, temp_dir / "llm_prompt.json")

    response = completion(
        model=llm_model,
        messages=messages,
        response_format=RestrictionAstParseResult,
    )
    content = response.choices[0].message.content

    if temp_dir is not None:
        (temp_dir / "llm_raw_response.txt").write_text(content, encoding="utf-8")

    result = RestrictionAstParseResult.model_validate_json(content)
    logger.info(
        f"[LLM] 属性制約を解析しました。 :: ast_count={len(result.asts)}, warnings={len(result.warnings)}, "
        f"unresolved_texts={len(result.unresolved_texts)}, total_tokens={response.usage.total_tokens}, "
        f"prompt_tokens={response.usage.prompt_tokens}, completion_tokens={response.usage.completion_tokens}"
    )

    if temp_dir is not None:
        print_json(restriction_catalog, temp_dir / "attribute_restriction_catalog.json")
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


def to_human_readable_text(result: RestrictionAstParseResult) -> str:
    """
    解析結果を人が読みやすいテキストへ変換します。

    Args:
        result: 解析結果

    Returns:
        人が読みやすいテキスト
    """
    lines: list[str] = []

    if result.asts:
        lines.append("[restrictions]")
        lines.extend(f"- {ast.to_human_readable()}" for ast in result.asts)
    else:
        lines.extend(("[restrictions]", "(none)"))

    if result.warnings:
        lines.extend(("", "[warnings]"))
        lines.extend(f"- {warning}" for warning in result.warnings)

    if result.unresolved_texts:
        lines.extend(("", "[unresolved_texts]"))
        lines.extend(f"- {text}" for text in result.unresolved_texts)

    return "\n".join(lines)


def to_annofab_restrictions(result: RestrictionAstParseResult, annotation_specs: dict[str, Any]) -> list[dict[str, Any]]:
    """
    解析結果をAnnofabへ登録可能な属性制約JSONへ変換します。

    Args:
        result: 解析結果
        annotation_specs: アノテーション仕様(v3)の情報

    Returns:
        Annofabに登録可能な属性制約JSON
    """
    return [Restriction.from_ast(ast, annotation_specs).to_dict() for ast in result.asts]


def collect_supplements_interactively(unresolved_texts: list[str]) -> list[str]:
    """
    未解決テキストに対してユーザーから補足情報をインタラクティブに収集します。

    Args:
        unresolved_texts: 属性制約として解釈できなかった原文の断片の一覧

    Returns:
        ユーザーが入力した補足情報の一覧（スキップされた場合は含まない）
    """
    supplements: list[str] = []
    len(unresolved_texts)
    for _i, _unresolved_text in enumerate(unresolved_texts, start=1):
        supplement = input("補足情報を入力してください（スキップする場合は空Enterを押してください）: ").strip()
        if supplement != "":
            supplements.append(supplement)
    return supplements


def main(args: argparse.Namespace) -> None:
    restriction_text = read_at_file(args.restriction_text)

    temp_dir = create_command_temp_dir(COMMAND_NAME)
    logger.info(f"一時ディレクトリ'{temp_dir}'を作成しました。このディレクトリにLLMの入出力情報などを出力します。")
    temp_dir.mkdir(exist_ok=True)

    annotation_specs = get_annotation_specs(
        annotation_specs_json_file=args.annotation_specs_json_file,
        project_id=args.project_id,
        annofab_pat=args.annofab_pat,
    )
    print_json(annotation_specs, temp_dir / "annotation_specs.json")
    output_path = args.output

    current_text = restriction_text
    result = parse_restrictions_from_text(
        text=current_text,
        annotation_specs=annotation_specs,
        llm_model=args.model,
        temp_dir=temp_dir,
    )
    print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")

    for warning in result.warnings:
        logger.warning(f"属性制約の解析時に注意事項がありました。 :: {warning}")
    for unresolved_text in result.unresolved_texts:
        logger.warning(f"属性制約として解釈できないテキストがありました。 :: {unresolved_text}")

    interactive = not args.no_interactive and not args.yes
    while result.unresolved_texts and interactive:
        supplements = collect_supplements_interactively(result.unresolved_texts)
        if len(supplements) == 0:
            break

        logger.info(f"{len(supplements)}件の補足情報をもとに再解析します。")
        supplement_text = "\n".join(supplements)
        current_text = f"{current_text}\n\n## 補足情報\n{supplement_text}"
        result = parse_restrictions_from_text(
            text=current_text,
            annotation_specs=annotation_specs,
            llm_model=args.model,
            temp_dir=temp_dir,
        )
        print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")

        for warning in result.warnings:
            logger.warning(f"属性制約の解析時に注意事項がありました。 :: {warning}")
        for unresolved_text in result.unresolved_texts:
            logger.warning(f"属性制約として解釈できないテキストがありました。 :: {unresolved_text}")

    if args.output_format == "human_readable":
        output_string(to_human_readable_text(result), output=output_path)
    elif args.output_format == "ast_json":
        print_json(result.model_dump(mode="json"), output=output_path)
    else:
        annofab_restrictions = to_annofab_restrictions(result, annotation_specs)
        print_json(annofab_restrictions, output=output_path)
        logger.info(OUTPUT_USAGE_MESSAGE)
        print_json(annofab_restrictions, temp_dir / "annofab_restrictions.json")

    logger.info("属性制約の自然言語解析が完了しました。")


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
        "--restriction_text",
        type=str,
        required=True,
        help="属性制約の情報が記載された自然言語。先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="出力先のファイルパス。指定しない場合は、標準出力に出力されます。",
    )
    parser.add_argument(
        "--output_format",
        type=str,
        choices=["human_readable", "ast_json", "annofab_json"],
        default="human_readable",
        help="出力形式",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        dest="no_interactive",
        help="未解決テキストが存在しても、補足情報の入力を求めずに終了します。",
    )


def add_parser(subparsers: argparse._SubParsersAction | None = None) -> argparse.ArgumentParser:
    parser = acl.common.cli.add_parser(
        subparsers,
        COMMAND_NAME,
        "自然言語から属性制約を解析します。",
        description=f"自然言語から属性制約を解析します。\n{OUTPUT_USAGE_MESSAGE}",
    )
    add_argument_to_parser(parser)
    parser.set_defaults(func=main)
    return parser
