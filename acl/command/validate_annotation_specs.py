import argparse
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

import acl.common.cli
from acl.common.annofab.annotation_type import get_annotation_type_details
from acl.common.annofab.attribute_type import get_attribute_type_details
from acl.common.cli import read_at_file
from acl.common.utils import output_string, print_json
from acl.common.xdg_util import create_command_temp_dir

COMMAND_NAME = "validate"
DEFAULT_REVIEW_POINT = """
- 英語名/日本語名の誤字脱字
- 英語名と日本語名が対応しているか。ただし英語名に日本語、日本語名に英語が混ざっている場合は指摘しないでください。簡略のためそうすることがあるからです。
- 必要な属性制約が設けられているか
""".strip()
"""デフォルトのレビュー観点です。"""
SPEC_MODEL_CONFIG = ConfigDict(extra="ignore")
"""LLMのレビュー対象にしない未知フィールドを無視するためのPydantic設定です。"""


class KeybindSpec(BaseModel):
    """
    キーボードショートカットです。
    """

    model_config = SPEC_MODEL_CONFIG

    alt: bool = Field(default=False, description="Altキーを使う場合はtrueです。")
    """Altキーを使うかどうかです。"""
    code: str = Field(description="KeyboardEvent.code の値です。例: Digit1, KeyQ")
    """KeyboardEvent.code の値です。"""
    ctrl: bool = Field(default=False, description="Ctrlキーを使う場合はtrueです。")
    """Ctrlキーを使うかどうかです。"""
    shift: bool = Field(default=False, description="Shiftキーを使う場合はtrueです。")
    """Shiftキーを使うかどうかです。"""


class LabelSpec(BaseModel):
    """
    既存ラベルの仕様です。
    """

    model_config = SPEC_MODEL_CONFIG

    label_id: str = Field(description="既存ラベルのIDです。レビュー指摘で対象ラベルを特定するために使用します。")
    """既存ラベルのIDです。"""
    label_name_en: str = Field(description="既存ラベル名（英語）です。")
    """既存ラベル名（英語）です。"""
    label_name_ja: str = Field(description="既存ラベル名（日本語）です。")
    """既存ラベル名（日本語）です。"""
    annotation_type: str = Field(description="既存ラベルのアノテーション種類です。例: bounding_box, polygon, segmentation")
    """既存ラベルのアノテーション種類です。"""
    color: str | None = Field(default=None, description="ラベル色です。例: #FF0000")
    """ラベル色です。"""
    keybind: KeybindSpec | None = Field(default=None, description="ラベルに設定されたキーボードショートカットです。")
    """ラベルに設定されたキーボードショートカットです。"""
    field_values: dict[str, object] | None = Field(default=None, description="ラベルごとの制約、表示設定、許容誤差などです。")
    """ラベルごとの制約、表示設定、許容誤差などです。"""


class ChoiceSpec(BaseModel):
    """
    既存属性の選択肢仕様です。
    """

    model_config = SPEC_MODEL_CONFIG

    choice_id: str = Field(description="既存選択肢のIDです。レビュー指摘で対象選択肢を特定するために使用します。")
    """既存選択肢のIDです。"""
    choice_name_en: str = Field(description="既存選択肢名（英語）です。")
    """既存選択肢名（英語）です。"""
    choice_name_ja: str = Field(description="既存選択肢名（日本語）です。")
    """既存選択肢名（日本語）です。"""
    is_default: bool = Field(default=False, description="デフォルト値の選択肢の場合はtrueです。")
    """デフォルト値かどうかです。"""
    keybind: KeybindSpec | None = Field(default=None, description="選択肢に設定されたキーボードショートカットです。")
    """選択肢に設定されたキーボードショートカットです。"""


class AttributeSpec(BaseModel):
    """
    既存属性の仕様です。
    """

    model_config = SPEC_MODEL_CONFIG

    attribute_id: str = Field(description="既存属性のIDです。レビュー指摘で対象属性を特定するために使用します。")
    """既存属性のIDです。"""
    attribute_type: str = Field(description="既存属性の種類です。例: flag, integer, text, comment, choice, select")
    """既存属性の種類です。"""
    attribute_name_en: str = Field(description="既存属性名（英語）です。")
    """既存属性名（英語）です。"""
    attribute_name_ja: str = Field(description="既存属性名（日本語）です。")
    """既存属性名（日本語）です。"""
    label_name_ens: list[str] = Field(description="この属性が付与されるラベル名（英語）の一覧です。")
    """この属性が付与されるラベル名（英語）の一覧です。"""
    read_only: bool = Field(default=False, description="読み込み専用属性の場合はtrueです。")
    """読み込み専用属性かどうかです。"""
    default_value: str | int | bool | None = Field(default=None, description="属性の初期値です。")
    """属性の初期値です。"""
    choices: list[ChoiceSpec] = Field(default_factory=list, description="属性種類がchoiceまたはselectの場合の選択肢一覧です。")
    """選択肢一覧です。"""
    keybind: KeybindSpec | None = Field(default=None, description="属性に設定されたキーボードショートカットです。")
    """属性に設定されたキーボードショートカットです。"""


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


def run_annofabcli_annotation_specs_text(*, project_id: str, subcommand_name: str, output_format: str) -> str:
    """
    annofabcliでアノテーション仕様の情報をテキスト形式で取得します。

    Args:
        project_id: AnnofabのプロジェクトID
        subcommand_name: 実行するannotation_specs配下のサブコマンド名
        output_format: annofabcliの --format に指定する値

    Returns:
        annofabcliが出力したテキスト
    """
    command = [
        "annofabcli",
        "annotation_specs",
        subcommand_name,
        "--project_id",
        project_id,
        "--format",
        output_format,
    ]
    logger.info(f"annofabcliコマンドを実行します。 :: command={command}")
    completed_process = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed_process.stdout


def parse_specs[SpecModel: BaseModel](raw_items: list[dict[str, object]], model_class: type[SpecModel]) -> list[SpecModel]:
    """
    annofabcliのJSON出力をレビュー用Specモデルへ変換します。

    Args:
        raw_items: annofabcliのJSON出力
        model_class: 変換先のSpecモデル

    Returns:
        変換後のSpecモデル一覧
    """
    return [model_class.model_validate(item) for item in raw_items]


def dump_specs(specs: Sequence[BaseModel]) -> list[dict[str, Any]]:
    """
    レビュー用SpecモデルをLLMへ渡すJSONへ変換します。

    Args:
        specs: レビュー用Specモデル一覧

    Returns:
        JSONへ変換したSpecモデル一覧
    """
    return [spec.model_dump(mode="json") for spec in specs]


def get_specs_json_schema() -> dict[str, dict[str, Any]]:
    """
    レビュー用SpecモデルのJSON Schemaを取得します。

    Returns:
        レビュー用SpecモデルのJSON Schema
    """
    return {
        "labels": LabelSpec.model_json_schema(),
        "attributes": AttributeSpec.model_json_schema(),
    }


def get_review_point(review_point: str | None) -> str:
    """
    レビュー観点を取得します。

    Args:
        review_point: CLI引数で指定されたレビュー観点

    Returns:
        LLMに渡すレビュー観点
    """
    if review_point is None:
        return DEFAULT_REVIEW_POINT

    return f"{DEFAULT_REVIEW_POINT}\n\n## 追加レビュー観点\n{read_at_file(review_point)}"


def review_annotation_specs_with_llm(
    *,
    annotation_rule: str | None,
    review_point: str,
    labels: list[LabelSpec],
    attributes: list[AttributeSpec],
    attribute_restrictions_text: str,
    llm_model: str,
    output_format: Literal["markdown", "json"],
    temp_dir: Path | None = None,
) -> str | AnnotationSpecsReviewResult:
    """
    LLMでアノテーション仕様をレビューします。

    Args:
        annotation_rule: アノテーションルール。未指定の場合はNone
        review_point: レビュー観点
        labels: ラベル一覧
        attributes: 属性一覧
        attribute_restrictions_text: 属性制約一覧のテキスト
        llm_model: 使用するLLMのモデル
        output_format: 出力形式
        temp_dir: 任意の一時ディレクトリ

    Returns:
        レビュー結果
    """
    specs_json_schema = get_specs_json_schema()
    annotation_type_details = get_annotation_type_details()
    attribute_type_details = get_attribute_type_details()
    dumped_labels = dump_specs(labels)
    dumped_attributes = dump_specs(attributes)
    annotation_rule_section = annotation_rule if annotation_rule is not None else "指定されていません。アノテーション仕様単体で判断できる範囲だけレビューしてください。"
    user_content = f"""
以下のアノテーション仕様を、アノテーションルールとレビュー観点に基づいてレビューしてください。
ただし、アノテーションルールに記載されていないラベルや属性が存在することは問題ないので、それについては指摘しないでください。
## アノテーションルール
{annotation_rule_section}

## レビュー観点
{review_point}

## アノテーション仕様JSON Schema
以下のアノテーション仕様JSONは、このJSON Schemaに従います。
{json.dumps(specs_json_schema, ensure_ascii=False, indent=2)}

## ラベル一覧
{json.dumps(dumped_labels, ensure_ascii=False, indent=2)}

## 利用可能な annotation_type と説明
{json.dumps(annotation_type_details, ensure_ascii=False, indent=2)}

## 属性一覧
{json.dumps(dumped_attributes, ensure_ascii=False, indent=2)}

## 利用可能な attribute_type と説明
{json.dumps(attribute_type_details, ensure_ascii=False, indent=2)}

## 属性制約一覧
以下は `annofabcli annotation_specs list_attribute_restriction --format text_with_ids` の出力です。
IDはレビュー指摘で対象の属性制約を特定するために使用してください。
{attribute_restrictions_text}
""".strip()

    messages = [
        {
            "role": "developer",
            "content": """
あなたはAnnofabのアノテーション仕様をレビューするAIです。
アノテーションルールに対して、ラベル、属性、属性制約に問題がないかをレビューしてください。
アノテーションルールが指定されていない場合は、アノテーション仕様単体で判断できる範囲だけレビューしてください。
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
    annotation_rule = read_at_file(args.annotation_rule) if args.annotation_rule is not None else None
    review_point = get_review_point(args.review_point)

    temp_dir = create_command_temp_dir(COMMAND_NAME)
    logger.info(f"一時ディレクトリ'{temp_dir}'を作成しました。このディレクトリにLLMの入出力情報などを出力します。")
    temp_dir.mkdir(exist_ok=True)

    raw_labels = run_annofabcli_annotation_specs_list(project_id=args.project_id, subcommand_name="list_label")
    raw_attributes = run_annofabcli_annotation_specs_list(project_id=args.project_id, subcommand_name="list_attribute")
    attribute_restrictions_text = run_annofabcli_annotation_specs_text(project_id=args.project_id, subcommand_name="list_attribute_restriction", output_format="text_with_ids")
    labels = parse_specs(raw_labels, LabelSpec)
    attributes = parse_specs(raw_attributes, AttributeSpec)
    print_json(dump_specs(labels), temp_dir / "labels.json")
    print_json(dump_specs(attributes), temp_dir / "attributes.json")
    (temp_dir / "attribute_restrictions.txt").write_text(attribute_restrictions_text, encoding="utf-8")
    print_json(get_specs_json_schema(), temp_dir / "annotation_specs_json_schema.json")

    result = review_annotation_specs_with_llm(
        annotation_rule=annotation_rule,
        review_point=review_point,
        labels=labels,
        attributes=attributes,
        attribute_restrictions_text=attribute_restrictions_text,
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
        help="アノテーションルール。指定しない場合は、アノテーション仕様単体で判断できる範囲をレビューします。先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
    )
    parser.add_argument(
        "--review_point",
        type=str,
        help="追加のレビュー観点。デフォルトのレビュー観点に加えて、この値も使用します。先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
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
