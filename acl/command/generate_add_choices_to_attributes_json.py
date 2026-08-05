import argparse
import json
from pathlib import Path
from typing import Any

from annofabapi.models import AdditionalDataDefinitionType
from annofabapi.util.annotation_specs import get_english_message
from litellm import completion
from loguru import logger
from pydantic import BaseModel, Field, model_validator

import acl.common.cli
from acl.command.generate_add_attributes_json import get_annotation_specs, get_required_japanese_message
from acl.command.generate_add_labels_json import STRUCTURED_OUTPUT_MODEL_CONFIG, UnresolvedText, format_unresolved_text
from acl.command.generate_update_attributes_json import collect_supplements_interactively
from acl.common.cli import read_at_file
from acl.common.utils import print_json
from acl.common.xdg_util import create_command_temp_dir

COMMAND_NAME = "generate_add_choices_to_attributes_json"
OUTPUT_USAGE_MESSAGE = "出力されるJSONは、annofabcli annotation_specs add_choices_to_attributes コマンドの --attribute_json 引数にそのまま指定できます。"
"""出力JSONの利用方法に関するメッセージです。"""


class ExistingChoice(BaseModel):
    """LLMへ渡すための既存選択肢情報です。"""

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    choice_id: str = Field(description="既存選択肢のIDです。")
    choice_name_en: str = Field(description="既存選択肢名（英語）です。")
    choice_name_ja: str = Field(description="既存選択肢名（日本語）です。")


class ChoiceCandidate(BaseModel):
    """追加候補の選択肢情報です。"""

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    choice_name_en: str = Field(description="追加する選択肢名（英語）です。")
    choice_name_ja: str | None = Field(default=None, description="追加する選択肢名（日本語）です。")
    choice_id: str | None = Field(default=None, description="追加する選択肢IDです。指定がない場合は省略してください。")

    @model_validator(mode="after")
    def validate_choice_name_en(self) -> "ChoiceCandidate":
        if self.choice_name_en.strip() == "":
            raise ValueError("`choice_name_en` には空でない文字列を指定してください。")
        return self


class ChoiceParseResult(BaseModel):
    """選択肢追加の自然言語解析結果です。"""

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    choices: list[ChoiceCandidate] = Field(description="解析できた追加対象選択肢の一覧です。")
    warnings: list[str] = Field(default_factory=list, description="解析時の注意事項です。")
    unresolved_texts: list[UnresolvedText] = Field(default_factory=list, description="選択肢追加ルールとして解釈できなかった原文、理由、必要な補足情報です。")


def get_target_attribute(annotation_specs: dict[str, Any], attribute_id: str) -> dict[str, Any]:
    """選択肢追加対象の属性を取得します。"""
    for additional in annotation_specs["additionals"]:
        if additional["additional_data_definition_id"] == attribute_id:
            return additional
    raise ValueError(f"属性ID'{attribute_id}'はアノテーション仕様に存在しません。")


def get_existing_choices(attribute: dict[str, Any]) -> list[ExistingChoice]:
    """LLMへ渡す既存選択肢一覧を生成します。"""
    return [
        ExistingChoice(
            choice_id=choice["choice_id"],
            choice_name_en=get_english_message(choice["name"]),
            choice_name_ja=get_required_japanese_message(choice["name"]),
        )
        for choice in attribute["choices"]
    ]


def parse_add_choices_from_text(
    *,
    text: str,
    attribute: dict[str, Any],
    llm_model: str,
    temp_dir: Path | None = None,
) -> ChoiceParseResult:
    """自然言語のテキストから追加する選択肢候補を抽出します。"""
    existing_choices = get_existing_choices(attribute)
    target_attribute = {
        "attribute_id": attribute["additional_data_definition_id"],
        "attribute_name_en": get_english_message(attribute["name"]),
        "attribute_name_ja": get_required_japanese_message(attribute["name"]),
        "attribute_type": attribute["type"],
    }
    messages = [
        {
            "role": "developer",
            "content": """
あなたは、自然言語で書かれたアノテーション仕様の変更内容から、既存の選択肢系属性へ追加する選択肢情報を抽出するAIです。
抽出した結果は、必ずChoiceParseResult形式で返してください。

指定された属性に追加する選択肢だけを choices に入れてください。
既存選択肢の更新・削除・並べ替え、新規属性やラベルの追加・更新、属性制約、作業手順、品質基準は choices に入れず無視してください。
choice_name_en は必須です。choice_name_ja と choice_id は、入力テキストに明示される場合だけ指定してください。
既存選択肢と同じ choice_name_en の選択肢は追加しないでください。
追加対象かどうか、または選択肢名が曖昧な場合は unresolved_texts に入れてください。
unresolved_texts には、解釈できなかった原文を text、理由を reason、必要な補足情報を required_information に出力してください。
""".strip(),
        },
        {
            "role": "user",
            "content": f"""
以下の自然言語テキストから、指定属性へ追加する選択肢情報を抽出してください。

## 入力テキスト
{text}

## 対象属性
{json.dumps(target_attribute, ensure_ascii=False, indent=2)}

## 既存選択肢一覧
{json.dumps([choice.model_dump(mode="json") for choice in existing_choices], ensure_ascii=False, indent=2)}
""".strip(),
        },
    ]

    if temp_dir is not None:
        print_json(messages, temp_dir / "llm_prompt.json")

    response = completion(model=llm_model, messages=messages, response_format=ChoiceParseResult)
    content = response.choices[0].message.content
    if temp_dir is not None:
        (temp_dir / "llm_raw_response.txt").write_text(content, encoding="utf-8")

    result = ChoiceParseResult.model_validate_json(content)
    logger.info(
        f"[LLM] 選択肢追加情報を解析しました。 :: choice_count={len(result.choices)}, warnings={len(result.warnings)}, "
        f"unresolved_texts={len(result.unresolved_texts)}, total_tokens={response.usage.total_tokens}, "
        f"prompt_tokens={response.usage.prompt_tokens}, completion_tokens={response.usage.completion_tokens}"
    )
    if temp_dir is not None:
        print_json([choice.model_dump(mode="json") for choice in existing_choices], temp_dir / "existing_choices.json")
        print_json(result.model_dump(mode="json"), temp_dir / "llm_completion.json")
    return result


def normalize_parsed_choices(result: ChoiceParseResult, attribute: dict[str, Any]) -> ChoiceParseResult:
    """解析済み選択肢候補を正規化します。"""
    existing_choice_names = {choice.choice_name_en for choice in get_existing_choices(attribute)}
    seen_choice_names: set[str] = set()
    normalized_choices: list[ChoiceCandidate] = []
    warnings = list(result.warnings)
    for choice in result.choices:
        if choice.choice_name_en in existing_choice_names:
            warnings.append(f"選択肢名（英語）'{choice.choice_name_en}'はすでに存在するため、出力から除外しました。")
            continue
        if choice.choice_name_en in seen_choice_names:
            warnings.append(f"選択肢名（英語）'{choice.choice_name_en}'が重複していたため、先頭の1件だけを採用しました。")
            continue
        seen_choice_names.add(choice.choice_name_en)
        normalized_choices.append(choice)
    return ChoiceParseResult(choices=normalized_choices, warnings=warnings, unresolved_texts=result.unresolved_texts)


def to_annofab_attributes(result: ChoiceParseResult, *, attribute_id: str) -> list[dict[str, Any]]:
    """解析結果を ``add_choices_to_attributes --attribute_json`` に渡せるJSONへ変換します。"""
    return [
        {
            "attribute_id": attribute_id,
            "choices": [choice.model_dump(mode="json", exclude_none=True) for choice in result.choices],
        }
    ]


def log_parse_warnings(result: ChoiceParseResult) -> None:
    for warning in result.warnings:
        logger.warning(f"選択肢追加情報の解析時に注意事項がありました。 :: {warning}")
    for unresolved_text in result.unresolved_texts:
        logger.warning(f"選択肢追加ルールとして解釈できないテキストがありました。 :: {format_unresolved_text(unresolved_text)}")


def main(args: argparse.Namespace) -> None:
    annotation_rule = read_at_file(args.annotation_rule)
    temp_dir = create_command_temp_dir(COMMAND_NAME)
    logger.info(f"一時ディレクトリ'{temp_dir}'を作成しました。このディレクトリにLLMの入出力情報などを出力します。")
    temp_dir.mkdir(exist_ok=True)
    annotation_specs = get_annotation_specs(annotation_specs_json_file=args.annotation_specs_json_file, project_id=args.project_id, annofab_pat=args.annofab_pat)
    print_json(annotation_specs, temp_dir / "annotation_specs.json")
    attribute = get_target_attribute(annotation_specs, args.attribute_id)
    if attribute["type"] not in {AdditionalDataDefinitionType.CHOICE.value, AdditionalDataDefinitionType.SELECT.value}:
        raise ValueError(f"属性ID'{args.attribute_id}'は選択肢系属性ではありません。 :: attribute_type='{attribute['type']}'")

    current_text = annotation_rule
    result = normalize_parsed_choices(parse_add_choices_from_text(text=current_text, attribute=attribute, llm_model=args.model, temp_dir=temp_dir), attribute)
    print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")
    log_parse_warnings(result)
    interactive = not args.no_interactive and not args.yes
    while result.unresolved_texts and interactive:
        supplements = collect_supplements_interactively(result.unresolved_texts)
        if len(supplements) == 0:
            break
        supplement_text = "\n".join(supplements)
        current_text = f"{current_text}\n\n## 補足情報\n{supplement_text}"
        result = normalize_parsed_choices(parse_add_choices_from_text(text=current_text, attribute=attribute, llm_model=args.model, temp_dir=temp_dir), attribute)
        print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")
        log_parse_warnings(result)

    if len(result.choices) == 0:
        raise ValueError("アノテーション仕様に追加可能な選択肢を抽出できませんでした。")
    annofab_attributes = to_annofab_attributes(result, attribute_id=args.attribute_id)
    print_json(annofab_attributes, output=args.output)
    logger.info("選択肢を追加する属性のJSONを標準出力に出力しました。" if args.output is None else f"選択肢を追加する属性のJSONをファイルに出力しました。 :: output='{args.output}'")
    logger.info(OUTPUT_USAGE_MESSAGE)
    print_json(annofab_attributes, temp_dir / "annofab_attributes.json")
    logger.info("選択肢追加情報の自然言語解析が完了しました。")


def add_argument_to_parser(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--annotation_specs_json_file", type=Path, help="annotation specs v3 のJSONファイルのパス")
    group.add_argument("-p", "--project_id", type=str, help="AnnofabのプロジェクトID")
    parser.add_argument("--attribute_id", type=str, required=True, help="選択肢を追加する対象属性のID")
    parser.add_argument(
        "--annotation_rule",
        type=str,
        required=True,
        help="選択肢追加に関するアノテーションルールやアノテーション仕様の自然言語。先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
    )
    parser.add_argument("-o", "--output", type=Path, help="出力先のファイルパス。指定しない場合は、標準出力に出力されます。")
    parser.add_argument("--no_interactive", action="store_true", dest="no_interactive", help="未解決テキストが存在しても、補足情報の入力を求めずに終了します。")


def add_parser(subparsers: argparse._SubParsersAction | None = None) -> argparse.ArgumentParser:
    parser = acl.common.cli.add_parser(subparsers, COMMAND_NAME, "自然言語から選択肢追加用JSONを生成します。", description=f"自然言語から選択肢追加用JSONを生成します。\n{OUTPUT_USAGE_MESSAGE}")
    add_argument_to_parser(parser)
    parser.set_defaults(func=main)
    return parser
