import argparse
import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Any

import annofabapi
from annofabapi.models import DefaultAnnotationType
from annofabapi.plugin import ThreeDimensionAnnotationType
from litellm import completion
from loguru import logger
from pydantic import BaseModel, Field, field_validator

import acl.common.cli
from acl.common.cli import read_at_file
from acl.common.utils import print_json
from acl.common.xdg_util import create_command_temp_dir

COMMAND_NAME = "parse_label"
HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
"""カラーコードの書式です。"""


class ProjectType(StrEnum):
    """
    parse_labelコマンドで扱うプロジェクト種別です。
    """

    IMAGE = "image"
    """画像プロジェクト"""

    VIDEO = "video"
    """動画プロジェクト"""

    THREE_DIMENSION = "3d"
    """3次元プロジェクト"""


class AnnotationType(StrEnum):
    """
    ラベルに指定できるアノテーション種類です。
    """

    BOUNDING_BOX = DefaultAnnotationType.BOUNDING_BOX.value
    SEGMENTATION = DefaultAnnotationType.SEGMENTATION.value
    SEGMENTATION_V2 = DefaultAnnotationType.SEGMENTATION_V2.value
    POLYGON = DefaultAnnotationType.POLYGON.value
    POLYLINE = DefaultAnnotationType.POLYLINE.value
    POINT = DefaultAnnotationType.POINT.value
    CLASSIFICATION = DefaultAnnotationType.CLASSIFICATION.value
    RANGE = DefaultAnnotationType.RANGE.value
    CUSTOM = DefaultAnnotationType.CUSTOM.value
    USER_BOUNDING_BOX = ThreeDimensionAnnotationType.BOUNDING_BOX.value
    USER_INSTANCE_SEGMENT = ThreeDimensionAnnotationType.INSTANCE_SEGMENT.value
    USER_SEMANTIC_SEGMENT = ThreeDimensionAnnotationType.SEMANTIC_SEGMENT.value


PROJECT_TYPE_TO_ANNOTATION_TYPES: dict[ProjectType, tuple[AnnotationType, ...]] = {
    ProjectType.IMAGE: (
        AnnotationType.BOUNDING_BOX,
        AnnotationType.SEGMENTATION,
        AnnotationType.SEGMENTATION_V2,
        AnnotationType.POLYGON,
        AnnotationType.POLYLINE,
        AnnotationType.POINT,
        AnnotationType.CLASSIFICATION,
    ),
    ProjectType.VIDEO: (
        AnnotationType.CLASSIFICATION,
        AnnotationType.RANGE,
    ),
    ProjectType.THREE_DIMENSION: (
        AnnotationType.USER_BOUNDING_BOX,
        AnnotationType.USER_INSTANCE_SEGMENT,
        AnnotationType.USER_SEMANTIC_SEGMENT,
    ),
}
"""プロジェクト種別ごとに指定可能なアノテーション種類です。"""

ANNOTATION_TYPE_DESCRIPTIONS: dict[AnnotationType, str] = {
    AnnotationType.BOUNDING_BOX: "矩形",
    AnnotationType.SEGMENTATION: "塗りつぶし（インスタンスセグメンテーション用）",
    AnnotationType.SEGMENTATION_V2: "塗りつぶしv2（セマンティックセグメンテーション用）",
    AnnotationType.POLYGON: "ポリゴン（閉じた頂点集合）",
    AnnotationType.POLYLINE: "ポリライン（開いた頂点集合）",
    AnnotationType.POINT: "点",
    AnnotationType.CLASSIFICATION: "全体分類",
    AnnotationType.RANGE: "動画の区間",
    AnnotationType.CUSTOM: "カスタム",
    AnnotationType.USER_BOUNDING_BOX: "3次元のバウンディングボックス",
    AnnotationType.USER_INSTANCE_SEGMENT: "3次元のインスタンスセグメント",
    AnnotationType.USER_SEMANTIC_SEGMENT: "3次元のセマンティックセグメント",
}
"""annotation_type の説明です。"""


def get_project_type_help() -> str:
    """
    ``--project_type`` のヘルプ文字列を生成します。

    Returns:
        ヘルプ文字列
    """
    return "プロジェクト種別。取り得る annotation_type を限定するために使用します。\n\n * image : 画像プロジェクト\n * video : 動画プロジェクト\n * 3d : 3次元プロジェクト"


def get_allowed_annotation_types(project_type: ProjectType) -> tuple[AnnotationType, ...]:
    """
    指定したプロジェクト種別で利用可能な annotation_type 一覧を返します。

    Args:
        project_type: プロジェクト種別

    Returns:
        利用可能な annotation_type 一覧
    """
    return PROJECT_TYPE_TO_ANNOTATION_TYPES[project_type]


def get_allowed_annotation_type_details(project_type: ProjectType) -> list[dict[str, str]]:
    """
    指定したプロジェクト種別で利用可能な annotation_type と説明を返します。

    Args:
        project_type: プロジェクト種別

    Returns:
        annotation_type と説明の一覧
    """
    return [{"value": annotation_type.value, "description": ANNOTATION_TYPE_DESCRIPTIONS[annotation_type]} for annotation_type in get_allowed_annotation_types(project_type)]


class LabelCandidate(BaseModel):
    """
    追加候補のラベル情報です。
    """

    label_name_en: str = Field(description="追加するラベル名（英語）です。")
    """ラベル名（英語）です。"""

    annotation_type: AnnotationType = Field(description="追加するラベルのアノテーション種類です。")
    """アノテーション種類です。"""

    label_name_ja: str | None = Field(default=None, description="追加するラベル名（日本語）です。特定できない場合はnullにしてください。")
    """ラベル名（日本語）です。"""

    color: str | None = Field(default=None, description="ラベル色です。指定する場合は `#RRGGBB` 形式にしてください。")
    """ラベル色です。 ``#RRGGBB`` 形式です。"""

    @field_validator("label_name_en")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        """
        必須文字列を検証します。

        Args:
            value: 検証対象の文字列

        Returns:
            前後空白を除去した文字列

        Raises:
            ValueError: 空文字列の場合
        """
        normalized = value.strip()
        if normalized == "":
            raise ValueError("空文字列は指定できません。")
        return normalized

    @field_validator("label_name_ja")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        """
        任意文字列を検証します。

        Args:
            value: 検証対象の文字列

        Returns:
            前後空白を除去した文字列。空文字列ならNone
        """
        if value is None:
            return None
        normalized = value.strip()
        if normalized == "":
            return None
        return normalized

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        """
        カラーコードを検証します。

        Args:
            value: 検証対象のカラーコード

        Returns:
            正規化済みのカラーコード。未指定ならNone

        Raises:
            ValueError: ``#RRGGBB`` 形式でない場合
        """
        if value is None:
            return None
        normalized = value.strip()
        if normalized == "":
            return None
        if HEX_COLOR_PATTERN.fullmatch(normalized) is None:
            raise ValueError("`color` には `#RRGGBB` 形式のカラーコードを指定してください。")
        return normalized.upper()


class LabelParseResult(BaseModel):
    """
    ラベルの自然言語解析結果です。
    """

    labels: list[LabelCandidate] = Field(description="解析できた追加対象ラベルの一覧です。")
    """解析できたラベル候補の一覧です。"""

    warnings: list[str] = Field(default_factory=list, description="解析時の注意事項です。解析結果に含めたが補足したい内容を入れてください。")
    """解析時の注意事項です。"""

    unresolved_texts: list[str] = Field(default_factory=list, description="ラベル追加ルールとして解釈できなかった原文の断片です。曖昧、情報不足、対象外の内容を入れてください。")
    """ラベル追加ルールとして解釈できなかった原文の断片です。"""


def get_message(annotation_text: dict[str, Any], *, lang: str) -> str | None:
    """
    多言語メッセージから指定言語の文字列を取得します。

    Args:
        annotation_text: Annofab APIの多言語メッセージ
        lang: 取得対象の言語コード

    Returns:
        見つかった文字列。存在しない場合はNone
    """
    messages = annotation_text.get("messages", [])
    for message in messages:
        if message.get("lang") == lang:
            return message.get("message")
    return None


def get_label_catalog(annotation_specs: dict[str, Any]) -> list[dict[str, Any]]:
    """
    LLMへ渡すための既存ラベル一覧を生成します。

    Args:
        annotation_specs: アノテーション仕様(v3)

    Returns:
        既存ラベル一覧
    """
    catalog = []
    for label in annotation_specs.get("labels", []):
        label_name = label.get("label_name", {})
        catalog.append(
            {
                "label_name_en": get_message(label_name, lang="en-US"),
                "label_name_ja": get_message(label_name, lang="ja-JP"),
                "annotation_type": label.get("annotation_type"),
            }
        )
    return catalog


def parse_labels_from_text(
    *,
    text: str,
    annotation_specs: dict[str, Any],
    project_type: ProjectType,
    llm_model: str,
    temp_dir: Path | None = None,
) -> LabelParseResult:
    """
    自然言語のテキストからラベル候補を抽出します。

    Args:
        text: ラベル追加ルールが記載された自然言語
        annotation_specs: アノテーション仕様(v3)
        llm_model: 使用するLLMのモデル
        temp_dir: 任意の一時ディレクトリ

    Returns:
        ラベルの解析結果
    """
    label_catalog = get_label_catalog(annotation_specs)
    allowed_annotation_type_details = get_allowed_annotation_type_details(project_type)
    messages = [
        {
            "role": "developer",
            "content": """
あなたは、自然言語で書かれたアノテーションルールから、Annofabに追加するラベルを抽出するAIです。
抽出した結果は、必ずLabelParseResult形式で返してください。
追加対象のラベルだけを labels に入れてください。
既存のannotation specsに存在するラベル名（英語）は出力してはいけません。
label_name_en はアノテーションJSONに出力される値なので、英語小文字のスネークケースで出力してください。
指定されたプロジェクト種別で利用可能な annotation_type だけを使用してください。
color を出力する場合は、必ず #RRGGBB 形式にしてください。
label_name_en と annotation_type を特定できない場合は、labelsに入れず unresolved_texts に入れてください。
曖昧な条件やラベル追加ルールではない文も unresolved_texts に入れてください。
""".strip(),
        },
        {
            "role": "user",
            "content": f"""
以下の自然言語テキストから、Annofabに追加するラベルを抽出してください。

## 入力テキスト
{text}

## プロジェクト種別
{project_type.value}

## 利用可能な annotation_type と説明
{json.dumps(allowed_annotation_type_details, ensure_ascii=False, indent=2)}

## 既存ラベル一覧
{json.dumps(label_catalog, ensure_ascii=False, indent=2)}
""".strip(),
        },
    ]

    if temp_dir is not None:
        print_json(messages, temp_dir / "llm_prompt.json")

    response = completion(
        model=llm_model,
        messages=messages,
        response_format=LabelParseResult,
    )
    content = response.choices[0].message.content

    if temp_dir is not None:
        (temp_dir / "llm_raw_response.txt").write_text(content, encoding="utf-8")

    result = LabelParseResult.model_validate_json(content)
    logger.info(
        f"[LLM] ラベルを解析しました。 :: label_count={len(result.labels)}, warnings={len(result.warnings)}, "
        f"unresolved_texts={len(result.unresolved_texts)}, total_tokens={response.usage.total_tokens}, "
        f"prompt_tokens={response.usage.prompt_tokens}, completion_tokens={response.usage.completion_tokens}"
    )

    if temp_dir is not None:
        print_json(label_catalog, temp_dir / "label_catalog.json")
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
        logger.info("`annotation_specs_json_file`と`project_id`が未指定のため、既存ラベル一覧なしでラベルを解析します。")
        return {"labels": [], "additionals": []}

    logger.info(f"Annofabからアノテーション仕様を取得します。 :: project_id='{project_id}'")
    service = annofabapi.build(pat=annofab_pat)
    annotation_specs, _ = service.api.get_annotation_specs(project_id, query_params={"v": "3"})
    return annotation_specs


def collect_supplements_interactively(unresolved_texts: list[str]) -> list[str]:
    """
    未解決テキストに対してユーザーから補足情報をインタラクティブに収集します。

    Args:
        unresolved_texts: ラベル追加ルールとして解釈できなかった原文の断片一覧

    Returns:
        ユーザーが入力した補足情報の一覧
    """
    supplements: list[str] = []
    for _i, _unresolved_text in enumerate(unresolved_texts, start=1):
        supplement = input("補足情報を入力してください（スキップする場合は空Enterを押してください）: ").strip()
        if supplement != "":
            supplements.append(supplement)
    return supplements


def normalize_parsed_labels(result: LabelParseResult, annotation_specs: dict[str, Any], *, project_type: ProjectType) -> LabelParseResult:
    """
    解析済みラベル候補を正規化します。

    Args:
        result: LLMの解析結果
        annotation_specs: アノテーション仕様(v3)

    Returns:
        正規化済みの解析結果
    """
    existing_label_name_ens = {e["label_name_en"] for e in get_label_catalog(annotation_specs) if e["label_name_en"] is not None}
    allowed_annotation_types = set(get_allowed_annotation_types(project_type))
    label_name_en_set: set[str] = set()
    normalized_labels: list[LabelCandidate] = []
    warnings = list(result.warnings)

    for label in result.labels:
        if label.annotation_type not in allowed_annotation_types:
            warnings.append(f"ラベル'{label.label_name_en}'の annotation_type='{label.annotation_type.value}' は project_type='{project_type.value}' では使用できないため、出力から除外しました。")
            continue
        if label.label_name_en in existing_label_name_ens:
            warnings.append(f"既存ラベル'{label.label_name_en}'は追加対象ではないため、出力から除外しました。")
            continue
        if label.label_name_en in label_name_en_set:
            warnings.append(f"ラベル'{label.label_name_en}'が重複していたため、先頭の1件だけを採用しました。")
            continue
        label_name_en_set.add(label.label_name_en)
        normalized_labels.append(label)

    return LabelParseResult(
        labels=normalized_labels,
        warnings=warnings,
        unresolved_texts=result.unresolved_texts,
    )


def to_annofab_labels(result: LabelParseResult) -> list[dict[str, Any]]:
    """
    解析結果を ``annotation_specs add_labels --label_json`` に渡せるJSONへ変換します。

    Args:
        result: ラベルの解析結果

    Returns:
        add_labels向けのJSON配列
    """
    return [label.model_dump(mode="json", exclude_none=True) for label in result.labels]


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
    result = parse_labels_from_text(
        text=current_text,
        annotation_specs=annotation_specs,
        project_type=args.project_type,
        llm_model=args.model,
        temp_dir=temp_dir,
    )
    result = normalize_parsed_labels(result, annotation_specs, project_type=args.project_type)
    print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")

    for warning in result.warnings:
        logger.warning(f"ラベル解析時に注意事項がありました。 :: {warning}")
    for unresolved_text in result.unresolved_texts:
        logger.warning(f"ラベル追加ルールとして解釈できないテキストがありました。 :: {unresolved_text}")

    interactive = not args.no_interactive and not args.yes
    while result.unresolved_texts and interactive:
        supplements = collect_supplements_interactively(result.unresolved_texts)
        if len(supplements) == 0:
            break

        logger.info(f"{len(supplements)}件の補足情報をもとに再解析します。")
        supplement_text = "\n".join(supplements)
        current_text = f"{current_text}\n\n## 補足情報\n{supplement_text}"
        result = parse_labels_from_text(
            text=current_text,
            annotation_specs=annotation_specs,
            project_type=args.project_type,
            llm_model=args.model,
            temp_dir=temp_dir,
        )
        result = normalize_parsed_labels(result, annotation_specs, project_type=args.project_type)
        print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")

        for warning in result.warnings:
            logger.warning(f"ラベル解析時に注意事項がありました。 :: {warning}")
        for unresolved_text in result.unresolved_texts:
            logger.warning(f"ラベル追加ルールとして解釈できないテキストがありました。 :: {unresolved_text}")

    annofab_labels = to_annofab_labels(result)
    if len(annofab_labels) == 0:
        raise ValueError("アノテーション仕様に追加可能なラベルを抽出できませんでした。")

    print_json(annofab_labels, output=args.output)
    print_json(annofab_labels, temp_dir / "annofab_labels.json")
    logger.info("ラベルの自然言語解析が完了しました。")


def add_argument_to_parser(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=False)
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
        "--project_type",
        type=ProjectType,
        choices=list(ProjectType),
        required=True,
        help=get_project_type_help(),
    )
    parser.add_argument(
        "--annotation_rule",
        type=str,
        required=True,
        help="ラベル追加に関するアノテーションルールやアノテーション仕様の自然言語。先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
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
    parser = acl.common.cli.add_parser(subparsers, COMMAND_NAME, "自然言語から追加対象のラベルを解析します。")
    add_argument_to_parser(parser)
    parser.set_defaults(func=main)
    return parser
