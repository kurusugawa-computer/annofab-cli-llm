import argparse
import json
import subprocess
from collections.abc import Collection
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas
from litellm import completion
from loguru import logger
from pydantic import BaseModel, Field

import acl
from acl.common.cli import prompt_yesno, read_at_file
from acl.common.utils import print_csv, print_json
from acl.common.xdg_util import create_command_temp_dir



COMMAND_NAME = "validate_annotation_attribute"


class ValidationResult(BaseModel):
    index: int = Field(description="LLMに渡したリストの何番目の要素かを示すインデックス(0始まり)")
    """LLMに渡したリストの何番目の要素かを示すインデックス(0始まり)"""
    attribute_name: str = Field(description="属性の名前")
    """属性名"""
    validation_message: str = Field(description="LLMによる検証結果の内容")
    """LLMによる検証結果の内容"""
    suggested_attribute_value: str = Field(description="LLMによって提案された属性値。提案すべき属性値がない場合は`[NO_SUGGESTION]`になります。")
    """LLMによって提案された属性値。提案すべき属性値がない場合は`[NO_SUGGESTION]`になります。"""


class ValidationResults(BaseModel):
    """
    `completion`関数の`response_format`引数に渡すために作成したクラス
    """

    results: list[ValidationResult]


def split_by_json_length(attribute_list: list[dict[str, Any]], max_chunk_length: int) -> list[tuple[list[dict[str, Any]], list[int]]]:
    """
    attribute_listを、json.dumpsしたときの長さがmax_chunk_lengthを超えないように分割する

    Returns:
        List of tuples. Each tuple is (chunk, indices), where
        - chunk: List[dict[str, Any]] ... チャンク化された属性リスト
        - indices: List[int] ... 元リストでのグローバルindex
    """
    chunks: list[tuple[list[dict[str, Any]], list[int]]] = []
    current_chunk: list[dict[str, Any]] = []
    current_indices: list[int] = []
    for idx, attr in enumerate(attribute_list):
        test_chunk = [*current_chunk, attr]
        if len(json.dumps(test_chunk, ensure_ascii=False)) > max_chunk_length:
            if not current_chunk:
                # 1要素だけで超える場合
                chunks.append(([attr], [idx]))
                current_chunk = []
                current_indices = []
            else:
                chunks.append((current_chunk, current_indices))
                current_chunk = [attr]
                current_indices = [idx]
        else:
            current_chunk = test_chunk
            current_indices = [*current_indices, idx]
    if current_chunk:
        chunks.append((current_chunk, current_indices))
    return chunks


def validate_annotation_attribute_with_llm(
    attribute_list: list[dict[str, Any]],
    validation_prompt: str,
    llm_model: str,
    *,
    attribute_description: str | None,
    annotation_overview: str | None = None,
    max_chunk_length: int = 100_000,
    temp_dir: Path | None = None,
) -> ValidationResults:
    """
    LLMを使用して、アノテーションの属性値を検証します。
    attribute_listが大きい場合は、json.dumpsした長さでチャンク分割して複数回APIを呼び出します。

    Args:
        attribute_list: List[dict[str, Any]] ... 検証対象の属性リスト
        validation_prompt: str ... 検証プロンプト
        attribute_description: Optional[str] ... 属性の説明
        annotation_overview: Optional[str] ... アノテーションの概要
        max_chunk_length: int ... チャンク分割時のjson長さ上限

    Returns:
        ValidationResults ... 検証結果
    """
    all_results: list[ValidationResult] = []
    total_tokens = 0
    prompt_tokens = 0
    completion_tokens = 0

    # チャンク分割
    chunks = split_by_json_length(attribute_list, max_chunk_length=max_chunk_length)
    logger.info(f"[LLM] {len(attribute_list)}件のアノテーションの属性値を{len(chunks)}個のチャンクに分けてLLMに情報を渡します。")

    for chunk_index, (chunk, indices) in enumerate(chunks):
        messages = [
            {
                "role": "system",
                "content": "あなたは、アノテーションの属性値を検証するAIです。",
            },
            {
                "role": "user",
                "content": f"""
「アノテーションの属性の説明」と「アノテーションの概要」を理解した上で、「あなたに検証して欲しいこと」に従い、与えられたアノテーション属性の値を検証してください。

## あなたに検証して欲しいこと
{validation_prompt}

## アノテーションの属性の説明（任意）
{attribute_description}

## アノテーションの概要（任意）
{annotation_overview}

## 出力形式
* 検証の結果、問題のない属性値は出力しないでください。
* 問題があった場合は以下を出力してください。
  * `index` : 何番目か(0始まり)
  * `attribute_name`
  * `validation_message`
  * `suggested_attribute_value`
* 提案すべき候補がない場合は、`suggested_attribute_value`に`[NO_SUGGESTION]`と出力してください。
---

<annotation_attribute_value>
{json.dumps(chunk, ensure_ascii=False)}
</annotation_attribute_value>
""",
            },
        ]
        chunk_file_prefix = f"chunk--no{chunk_index}--anno_index-from{indices[0]}-to{indices[-1]}"
        if temp_dir is not None:
            print_json(messages, (temp_dir / f"{chunk_file_prefix}--llm_prompt.json"))

        response = completion(
            model=llm_model,
            messages=messages,
            response_format=ValidationResults,
        )
        content = response.choices[0].message.content
        results = ValidationResults.model_validate_json(content).results
        logger.info(
            f"[LLM] chunk {chunk_index + 1}/{len(chunks)}: {len(chunk)} 件のアノテーションに含まれる属性値をLLMに渡しました。"
            f"{len(results)}件の属性値が指摘を受けました。 :: "
            f"total_tokens={response.usage.total_tokens}, prompt_tokens={response.usage.prompt_tokens}, completion_tokens={response.usage.completion_tokens}"
        )
        total_tokens += response.usage.total_tokens
        prompt_tokens += response.usage.prompt_tokens
        completion_tokens += response.usage.completion_tokens

        for result in results:
            if 0 <= result.index < len(indices):
                result.index = indices[result.index]
        if temp_dir:
            print_json(messages, (temp_dir / f"{chunk_file_prefix}--llm_completion.json"))
        all_results.extend(results)

    logger.info(
        f"[LLM] {len(chunks)}回LLMにアクセスして、{len(attribute_list)}件のアノテーションに含まれる属性値を検証しました。"
        f"{len(all_results)}件の属性値が指摘を受けました。 :: "
        f"使用したトークン数: total tokens used: total_tokens={total_tokens}, prompt_tokens={prompt_tokens}, completion_tokens={completion_tokens}"
    )
    return ValidationResults(results=all_results)


def write_annotation_attribute_json(project_id: str, output_json: Path, *, annotation_path: Path | None, temp_dir: Path | None, annofab_pat: str | None) -> None:
    cmd = [
        "annofabcli",
        "statistics",
        "list_annotation_attribute",
        "--format",
        "json",
        "--output",
        str(output_json),
    ]
    if annotation_path is not None:
        cmd.extend(["--annotation", str(annotation_path)])
    else:
        # `--annotation`と`--project_id`は同時に指定できないため
        cmd.extend(["--project_id", project_id])

    if temp_dir is not None:
        cmd.extend(["--temp_dir", str(temp_dir)])
    if annofab_pat is not None:
        cmd.extend(["--annofab_pat", annofab_pat])
    logger.info(f"annofabcliを実行します。 :: {cmd}")
    subprocess.run(cmd, check=True)


def filter_attribute_list(  # noqa: PLR0912
    attribute_list: list[dict[str, Any]],
    *,
    label_name: str,
    target_attribute_names: list[str],
    task_status: str | None = None,
    task_phase: str | None = None,
    task_ids: Collection[str] | None = None,
    updated_datetime_after: str | None = None,
    updated_datetime_before: str | None = None,
    allow_empty_attribute_value: bool = False,
) -> list[dict[str, Any]]:
    """
    attribute_list から指定のラベル・属性を抽出し、
    updated_datetime_after/before で絞り込みます。

    Args:
        attribute_list: アノテーション属性リスト
        label_name: ラベル名（英語）
        target_attribute_names: 検証対象属性名リスト（英語）
        task_status: タスクステータスでフィルタ
        updated_datetime_after: この日以降に更新された要素のみ (YYYY-MM-DD or ISO)
        updated_datetime_before: この日以前に更新された要素のみ (YYYY-MM-DD or ISO)
    """
    if updated_datetime_after is not None:
        after_date = datetime.fromisoformat(updated_datetime_after)
        if after_date.tzinfo is None:
            # タイムゾーンが指定されていない場合は、JTCとみなす
            after_date = after_date.replace(tzinfo=ZoneInfo("Asia/Tokyo"))
    else:
        after_date = None

    if updated_datetime_before is not None:
        before_date = datetime.fromisoformat(updated_datetime_before)
        if before_date.tzinfo is None:
            # タイムゾーンが指定されていない場合は、JTCとみなす
            before_date = before_date.replace(tzinfo=ZoneInfo("Asia/Tokyo"))
    else:
        before_date = None

    result_list: list[dict[str, Any]] = []
    for elm in attribute_list:
        if task_status is not None and elm["task_status"] != task_status:
            continue
        if task_phase is not None and elm["task_phase"] != task_phase:
            continue
        if task_ids is not None and elm["task_id"] not in task_ids:
            continue
        if elm["label"] != label_name:
            continue
        # updated_datetime filter
        dt = elm["updated_datetime"]
        elm_date = datetime.fromisoformat(dt)
        if after_date and elm_date <= after_date:
            continue
        if before_date and elm_date >= before_date:
            continue

        attrs = elm["attributes"]
        filtered_attrs = {k: attrs[k] for k in target_attribute_names if k in attrs}
        if not allow_empty_attribute_value:
            # 空文字やnullを除外
            filtered_attrs = {k: v for k, v in filtered_attrs.items() if v not in (None, "")}

        if len(filtered_attrs) == 0:
            continue

        elm["attributes"] = filtered_attrs
        result_list.append(elm)
    return result_list


def to_attribute_list_for_llm_input(attribute_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e["attributes"] for e in attribute_list]


def to_output_attribute_list(attribute_list: list[dict[str, Any]], validation_results: ValidationResults) -> list[dict[str, Any]]:
    for r in validation_results.results:
        idx = r.index
        orig = attribute_list[idx]
        orig.setdefault("validation_messages", {})[r.attribute_name] = r.validation_message
        orig.setdefault("suggested_attributes", {})[r.attribute_name] = r.suggested_attribute_value

    # 指定された属性のみ出力する
    output_attribute_list = [e for e in attribute_list if "suggested_attributes" in e]
    return output_attribute_list


def main(args: argparse.Namespace) -> None:
    validation_prompt = read_at_file(args.prompt)
    attribute_description = read_at_file(args.attribute_description) if args.attribute_description else None
    annotation_overview = read_at_file(args.annotation_overview) if args.annotation_overview else None

    temp_dir = create_command_temp_dir(COMMAND_NAME)
    logger.info(f"一時ディレクトリ'{temp_dir}'を作成しました。このディレクトリにLLMの入出力情報などを出力します。")
    project_id = args.project_id
    target_attribute_names = args.attribute_name
    temp_dir.mkdir(exist_ok=True)

    if args.list_annotation_attribute_json_file:
        annotation_attribute_json = args.list_annotation_attribute_json_file
    else:
        annotation_attribute_json = temp_dir / f"{project_id}--annotation_attribute.json"
        write_annotation_attribute_json(project_id, annotation_attribute_json, annotation_path=args.annotation, temp_dir=temp_dir, annofab_pat=args.annofab_pat)

    attribute_list = json.loads(annotation_attribute_json.read_text())
    filtered_attribute_list = filter_attribute_list(
        attribute_list,
        label_name=args.label_name,
        target_attribute_names=target_attribute_names,
        task_status=args.task_status,
        task_phase=args.task_phase,
        updated_datetime_after=args.updated_datetime_after,
        updated_datetime_before=args.updated_datetime_before,
        allow_empty_attribute_value=args.allow_empty_attribute_value,
    )
    llm_input = to_attribute_list_for_llm_input(filtered_attribute_list)
    print_json(filtered_attribute_list, (temp_dir / "target_annotation_attribute.json"))
    print_json(llm_input, (temp_dir / "target_annotation_attribute_for_llm_input.json"))

    assert len(filtered_attribute_list) == len(llm_input)
    logger.info(f"{len(filtered_attribute_list)}件のアノテーションに含まれる属性値が検証対象です。 :: LLMに渡すJSONの長さ: {len(json.dumps(llm_input))}")

    if len(filtered_attribute_list) == 0:
        logger.info("検証対象のアノテーションが0件でした。終了します。")
        return

    if not args.yes:
        if not prompt_yesno(f"アノテーション{len(filtered_attribute_list)}件の属性値を検証しますか？"):
            logger.info("終了します。")
            return

    results = validate_annotation_attribute_with_llm(
        llm_input,
        validation_prompt,
        llm_model=args.model,
        attribute_description=attribute_description,
        annotation_overview=annotation_overview,
        temp_dir=temp_dir,
        max_chunk_length=args.max_chunk_length,
    )
    logger.info(f"{len(filtered_attribute_list)}件のアノテーションの属性値に対して、{len(results.results)}件の指摘がありました。")
    if not results.results:
        logger.info("問題のある属性値はなかったので、終了します。")
        return

    output_attribute_list = to_output_attribute_list(filtered_attribute_list, results)

    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.output_format == "json":
        print_json(output_attribute_list, out)
    else:
        cols = [
            "project_id",
            "task_id",
            "task_status",
            "task_phase",
            "task_phase_stage",
            "input_data_id",
            "input_data_name",
            "updated_datetime",
            "annotation_id",
            "label",
            "attributes",
            "validation_messages",
            "suggested_attributes",
        ]
        df = pandas.DataFrame(output_attribute_list, columns=cols)
        # `annofabcli annotation change_attributes_per_annotation`コマンドの`--csv`に渡せるようにするため、JSONに変換する。
        for col in ["attributes", "validation_messages", "suggested_attributes"]:
            df[col] = df[col].map(lambda e: json.dumps(e))

        print_csv(pandas.DataFrame(output_attribute_list, columns=cols), output=out)

    logger.info("アノテーションの属性値の検証が完了しました。")


def add_argument_to_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-p",
        "--project_id",
        type=str,
        help="AnnofabのプロジェクトID",
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--annotation",
        type=Path,
        help="AnnofabからダウンロードしたアノテーションZIP、またはそれを展開したディレクトリのパス",
    )
    group.add_argument(
        "--list_annotation_attribute_json_file",
        type=Path,
        help="`annofabcli statistics list_annotation_attribute --format json`コマンドで出力したJSONファイルのパス。",
    )

    parser.add_argument(
        "--label_name",
        type=str,
        help="検証対象のアノテーションが所属するラベルの名前（英語）",
    )

    parser.add_argument(
        "--task_id", type=str, nargs="+", help="検証対象のアノテーションが属するタスクのIDで絞り込みます。先頭に`@`を指定すると、`@`以降をファイルパスとみなして、ファイルを読み込みます。"
    )
    parser.add_argument("--task_status", type=str, help="検証対象のアノテーションが属するタスクのステータスで絞り込みます。")
    parser.add_argument("--task_phase", type=str, help="検証対象のアノテーションが属するタスクのフェーズで絞り込みます。")
    parser.add_argument(
        "--updated_datetime_after", type=str, help="指定した日時以降に更新されたアノテーションを検証対象にします。ISO8601形式で指定してください。日付のみ指定した場合は、0時として解釈されます。"
    )
    parser.add_argument(
        "--updated_datetime_before", type=str, help="指定した日時以前に更新されたアノテーションを検証対象にします。ISO8601形式で指定してください。日付のみ指定した場合は、0時として解釈されます。"
    )

    parser.add_argument(
        "--attribute_name",
        type=str,
        required=True,
        nargs="+",
        help="検証対象のアノテーション属性の名前（英語）",
    )

    parser.add_argument(
        "--prompt",
        type=str,
        required=True,
        help="アノテーション属性値をどのように検証するかを記述したプロンプト。\n例: 明らかな誤字脱字がないかをチェックしてください。\n"
        "先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
    )

    parser.add_argument(
        "--annotation_overview",
        type=str,
        required=False,
        help="検証対象の属性の説明。\n例: 属性`status`は画像に映っている状態を表します。\n先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
    )

    parser.add_argument(
        "--attribute_description",
        type=str,
        required=False,
        help="アノテーションの概要。\n例: 画像の状況を説明するアノテーションです。\n先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
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
        choices=["csv", "json"],
        required=True,
        default="csv",
        help="検証結果を出力するファイルの形式",
    )

    parser.add_argument(
        "--allow_empty_attribute_value",
        action="store_true",
        help="空の属性値もLLMに渡します（デフォルトは除外）",
    )

    parser.add_argument(
        "--max_chunk_length",
        type=int,
        default=5000,
        help="LLMに渡す属性値情報に関して、1チャンクあたりの最大JSON文字数",
    )


def add_parser(subparsers: argparse._SubParsersAction|None=None) -> argparse.ArgumentParser:
    parser = acl.common.cli.add_parser(subparsers, COMMAND_NAME, "アノテーションの属性値を検証します。")
    add_argument_to_parser(parser)
    parser.set_defaults(func=main)
    return parser
