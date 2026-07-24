import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field

import acl.common.cli
from acl.common.cli import read_at_file
from acl.common.utils import output_string, print_json
from acl.common.xdg_util import create_command_temp_dir

COMMAND_NAME = "validate"
DEFAULT_REVIEW_POINT = """
- 英語名/日本語名の誤字脱字
- 英語名と日本語名が対応しているか
- 必要な属性制約が設けられているか
""".strip()
"""デフォルトのレビュー観点です。"""


class AnnotationSpecsReviewFinding(BaseModel):
    """
    アノテーション仕様レビューの指摘です。
    """

    severity: Literal["error", "warning", "notice"]
    """指摘の重要度です。"""
    category: str
    """指摘の分類です。"""
    target_type: str
    """指摘対象の種類です。例: label, attribute, attribute_restriction"""
    target_name: str | None = None
    """指摘対象の名前です。"""
    message: str
    """指摘内容です。"""
    recommendation: str | None = None
    """推奨する対応です。"""


class AnnotationSpecsReviewResult(BaseModel):
    """
    アノテーション仕様レビュー結果です。
    """

    summary: str
    """レビュー結果の概要です。"""
    findings: list[AnnotationSpecsReviewFinding] = Field(default_factory=list)
    """レビューの指摘一覧です。"""


def call_llm_completion(**kwargs: object) -> Any:  # noqa: ANN401
    """
    LiteLLMのcompletionを呼び出します。

    Args:
        kwargs: LiteLLM completionに渡す引数
    """
    from litellm import completion  # noqa: PLC0415

    return completion(**kwargs)


def run_annofabcli_annotation_specs_list(*, project_id: str, subcommand_name: str) -> list[dict[str, object]]:
    """
    annofabcliでアノテーション仕様の一覧をJSON形式で取得します。

    Args:
        project_id: AnnofabのプロジェクトID
        subcommand_name: 実行するannotation_specs配下のサブコマンド名

    Returns:
        annofabcliが出力したJSON
    """
    command = [
        "annofabcli",
        "annotation_specs",
        subcommand_name,
        "--project_id",
        project_id,
        "--format",
        "json",
    ]
    logger.info(f"annofabcliコマンドを実行します。 :: command={command}")
    completed_process = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(completed_process.stdout)


def get_review_point(review_points: list[str] | None) -> str:
    """
    レビュー観点を取得します。

    Args:
        review_points: CLI引数で指定されたレビュー観点

    Returns:
        LLMに渡すレビュー観点
    """
    if review_points is None:
        return DEFAULT_REVIEW_POINT

    return "\n\n".join(read_at_file(review_point) for review_point in review_points)


def review_annotation_specs_with_llm(
    *,
    annotation_rule: str,
    review_point: str,
    labels: list[dict[str, object]],
    attributes: list[dict[str, object]],
    attribute_restrictions: list[dict[str, object]],
    llm_model: str,
    output_format: Literal["markdown", "json"],
    temp_dir: Path | None = None,
) -> str | AnnotationSpecsReviewResult:
    """
    LLMでアノテーション仕様をレビューします。

    Args:
        annotation_rule: アノテーションルール
        review_point: レビュー観点
        labels: ラベル一覧
        attributes: 属性一覧
        attribute_restrictions: 属性制約一覧
        llm_model: 使用するLLMのモデル
        output_format: 出力形式
        temp_dir: 任意の一時ディレクトリ

    Returns:
        レビュー結果
    """
    user_content = f"""
以下のアノテーション仕様を、アノテーションルールとレビュー観点に基づいてレビューしてください。

## アノテーションルール
{annotation_rule}

## レビュー観点
{review_point}

## ラベル一覧
{json.dumps(labels, ensure_ascii=False, indent=2)}

## 属性一覧
{json.dumps(attributes, ensure_ascii=False, indent=2)}

## 属性制約一覧
{json.dumps(attribute_restrictions, ensure_ascii=False, indent=2)}
""".strip()

    messages = [
        {
            "role": "developer",
            "content": """
あなたはAnnofabのアノテーション仕様をレビューするAIです。
アノテーションルールに対して、ラベル、属性、属性制約に問題がないかをレビューしてください。
推測だけで断定せず、根拠が弱い場合はその旨を明記してください。
問題がない場合は、問題が見つからなかったことを簡潔に述べてください。
""".strip(),
        },
        {
            "role": "user",
            "content": user_content,
        },
    ]

    if temp_dir is not None:
        print_json(messages, temp_dir / "llm_prompt.json")

    if output_format == "json":
        response = call_llm_completion(model=llm_model, messages=messages, response_format=AnnotationSpecsReviewResult)
        content = response.choices[0].message.content
        result = AnnotationSpecsReviewResult.model_validate_json(content)
        if temp_dir is not None:
            (temp_dir / "llm_raw_response.txt").write_text(content, encoding="utf-8")
            print_json(result.model_dump(mode="json"), temp_dir / "llm_completion.json")
        logger.info(
            f"[LLM] アノテーション仕様をレビューしました。 :: finding_count={len(result.findings)}, total_tokens={response.usage.total_tokens}, "
            f"prompt_tokens={response.usage.prompt_tokens}, completion_tokens={response.usage.completion_tokens}"
        )
        return result

    response = call_llm_completion(model=llm_model, messages=messages)
    content = response.choices[0].message.content
    if temp_dir is not None:
        (temp_dir / "llm_raw_response.md").write_text(content, encoding="utf-8")
    logger.info(
        f"[LLM] アノテーション仕様をレビューしました。 :: total_tokens={response.usage.total_tokens}, "
        f"prompt_tokens={response.usage.prompt_tokens}, completion_tokens={response.usage.completion_tokens}"
    )
    return content


def main(args: argparse.Namespace) -> None:
    annotation_rule = read_at_file(args.annotation_rule)
    review_point = get_review_point(args.review_point)

    temp_dir = create_command_temp_dir(COMMAND_NAME)
    logger.info(f"一時ディレクトリ'{temp_dir}'を作成しました。このディレクトリにLLMの入出力情報などを出力します。")
    temp_dir.mkdir(exist_ok=True)

    labels = run_annofabcli_annotation_specs_list(project_id=args.project_id, subcommand_name="list_label")
    attributes = run_annofabcli_annotation_specs_list(project_id=args.project_id, subcommand_name="list_attribute")
    attribute_restrictions = run_annofabcli_annotation_specs_list(project_id=args.project_id, subcommand_name="list_attribute_restriction")
    print_json(labels, temp_dir / "labels.json")
    print_json(attributes, temp_dir / "attributes.json")
    print_json(attribute_restrictions, temp_dir / "attribute_restrictions.json")

    result = review_annotation_specs_with_llm(
        annotation_rule=annotation_rule,
        review_point=review_point,
        labels=labels,
        attributes=attributes,
        attribute_restrictions=attribute_restrictions,
        llm_model=args.model,
        output_format=args.output_format,
        temp_dir=temp_dir,
    )

    if args.output_format == "json":
        assert isinstance(result, AnnotationSpecsReviewResult)
        print_json(result.model_dump(mode="json"), output=args.output)
    else:
        assert isinstance(result, str)
        output_string(result, output=args.output)

    logger.info("アノテーション仕様のレビューが完了しました。")


def add_argument_to_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-p",
        "--project_id",
        type=str,
        required=True,
        help="AnnofabのプロジェクトID",
    )
    parser.add_argument(
        "--annotation_rule",
        type=str,
        required=True,
        help="アノテーションルール。先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
    )
    parser.add_argument(
        "--review_point",
        type=str,
        action="append",
        help="レビュー観点。先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。複数回指定できます。指定しない場合はデフォルトのレビュー観点を使用します。",
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
        choices=["markdown", "json"],
        default="markdown",
        help="出力形式",
    )


def add_parser(subparsers: argparse._SubParsersAction | None = None) -> argparse.ArgumentParser:
    parser = acl.common.cli.add_parser(subparsers, COMMAND_NAME, "アノテーション仕様をレビューします。")
    add_argument_to_parser(parser)
    parser.set_defaults(func=main)
    return parser
