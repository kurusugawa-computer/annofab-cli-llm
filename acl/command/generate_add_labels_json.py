import argparse
import json
import re
from pathlib import Path
from typing import Any, Literal

import annofabapi
from litellm import completion
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator

import acl.common.cli
from acl.common.annofab.annotation_type import AnnotationType, ProjectType, get_allowed_annotation_type_details, get_allowed_annotation_types, get_project_type_help
from acl.common.cli import read_at_file
from acl.common.utils import print_json
from acl.common.xdg_util import create_command_temp_dir

COMMAND_NAME = "generate_add_labels_json"
OUTPUT_USAGE_MESSAGE = "出力されるJSONは、annofabcli annotation_specs add_labels コマンドの --label_json 引数にそのまま指定できます。"
"""出力JSONの利用方法に関するメッセージです。"""
HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
"""カラーコードの書式です。"""
ALLOWED_KEYBIND_CODES = {
    "Digit0",
    "Digit1",
    "Digit2",
    "Digit3",
    "Digit4",
    "Digit5",
    "Digit6",
    "Digit7",
    "Digit8",
    "Digit9",
    "KeyQ",
    "KeyW",
    "KeyE",
    "KeyR",
    "KeyT",
    "KeyY",
    "KeyU",
    "KeyI",
    "KeyO",
    "KeyP",
}
"""keybind.code に指定できる KeyboardEvent.code の値です。"""
STRUCTURED_OUTPUT_MODEL_CONFIG = ConfigDict(extra="forbid", serialize_by_alias=True)
"""OpenAIのStructured Outputsで利用できるJSON SchemaにするためのPydantic設定です。"""


class KeybindCandidate(BaseModel):
    """
    ラベルに設定するキーボードショートカットです。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    alt: bool = Field(default=False, description="Altキーを使用する場合はtrueです。")
    """Altキーを使用するかどうかです。"""

    code: str = Field(description="KeyboardEvent.code の値です。ただし既存のショートカットと衝突しないようにするため、キーボード上部2段の数字キーと`Q`~`P`に限定してください。")
    """KeyboardEvent.code の値です。"""

    ctrl: bool = Field(default=False, description="Ctrlキーを使用する場合はtrueです。")
    """Ctrlキーを使用するかどうかです。"""

    shift: bool = Field(default=False, description="Shiftキーを使用する場合はtrueです。")
    """Shiftキーを使用するかどうかです。"""

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        """
        キーコードを検証します。

        Args:
            value: 検証対象のキーコード

        Returns:
            前後空白を除去したキーコード

        Raises:
            ValueError: 空文字列の場合
        """
        normalized = value.strip()
        if normalized == "":
            raise ValueError("`keybind.code` には空でない文字列を指定してください。")
        if normalized not in ALLOWED_KEYBIND_CODES:
            raise ValueError("`keybind.code` にはキーボード上部2段の数字キーと`Q`~`P`の KeyboardEvent.code を指定してください。")
        return normalized


class MarginOfErrorToleranceFieldValue(BaseModel):
    """
    許容誤差に関する field_values です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    type_: Literal["MarginOfErrorTolerance"] = Field(alias="_type", description="field_values の種類です。")
    """field_values の種類です。"""

    max_pixel: int = Field(description="許容誤差の最大ピクセル数です。")
    """許容誤差の最大ピクセル数です。"""


class DisplayLineDirectionFieldValue(BaseModel):
    """
    ポリラインの方向の表示に関する field_values です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    type_: Literal["DisplayLineDirection"] = Field(alias="_type", description="field_values の種類です。")
    """field_values の種類です。"""

    has_direction: bool = Field(default=False, description="ポリラインに向きがある場合はtrueです。")
    """ポリラインに向きがある場合はtrueです。"""


class MinWarnRule(BaseModel):
    """
    最小サイズ制約の幅と高さの判定ルールです。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    type_: Literal["Or", "And"] = Field(
        alias="_type",
        description=(
            "min_width と min_height に関して警告を出す条件です。"
            "「幅が100px以上 AND 高さ200px以上」という制約の場合は`Or`、"
            "「幅が100px以上 OR 高さ200px以上」という制約の場合は`And`を指定する必要があります。"
        ),
    )
    """min_width と min_height の制約条件です。"""


class MinimumSize2dWithDefaultInsertPositionFieldValue(BaseModel):
    """
    2次元図形の最小サイズ制約に関する field_values です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    min_warn_rule: MinWarnRule = Field(description="min_width と min_height に関して警告を出す条件です。")
    """min_width と min_height に関して警告を出す条件です。"""

    min_width: int = Field(description="最小幅(ピクセル)です。")
    """最小幅です。"""

    min_height: int = Field(description="最小高さ(ピクセル)です。")
    """最小高さです。"""

    position_for_minimum_bounding_box_insertion: list[int] | None = Field(default=None, description="最小矩形を挿入するときの位置です。")
    """最小矩形を挿入するときの位置です。"""

    type_: Literal["MinimumSize2dWithDefaultInsertPosition"] = Field(alias="_type", description="field_values の種類です。")
    """field_values の種類です。"""


class MinimumSize2dFieldValue(BaseModel):
    """
    2次元図形の最小サイズ制約に関する field_values です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    min_warn_rule: MinWarnRule = Field(description="min_width と min_height の制約条件です。")
    """min_width と min_height の制約条件です。"""

    min_width: int = Field(description="最小幅(ピクセル)です。")
    """最小幅です。"""

    min_height: int = Field(description="最小高さ(ピクセル)です。")
    """最小高さです。"""

    type_: Literal["MinimumSize2d"] = Field(alias="_type", description="field_values の種類です。")
    """field_values の種類です。"""


class MinimumArea2dFieldValue(BaseModel):
    """
    ポリゴンの最小面積制約に関する field_values です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    min_area: int = Field(description="最小面積(平方ピクセル)です。")
    """最小面積です。"""

    type_: Literal["MinimumArea2d"] = Field(alias="_type", description="field_values の種類です。")
    """field_values の種類です。"""


class VertexCountMinMaxFieldValue(BaseModel):
    """
    ポリラインまたはポリゴンの頂点数制約に関する field_values です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    min: int | None = Field(default=None, description="頂点数の最小値です。")
    """頂点数の最小値です。"""

    max: int | None = Field(default=None, description="頂点数の最大値です。")
    """頂点数の最大値です。"""

    type_: Literal["VertexCountMinMax"] = Field(alias="_type", description="field_values の種類です。")
    """field_values の種類です。"""


class FieldValues(BaseModel):
    """
    ラベルごとの制約、表示設定、許容誤差などの field_values です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    minimum_size_2d_with_default_insert_position: MinimumSize2dWithDefaultInsertPositionFieldValue | None = Field(
        default=None,
        description="アノテーションの種類が「矩形」の場合の最小サイズ制約です。",
    )
    """アノテーションの種類が「矩形」の場合の最小サイズ制約です。"""

    minimum_size_2d: MinimumSize2dFieldValue | None = Field(
        default=None,
        description="アノテーションの種類が「ポリゴン」「ポリライン」「塗りつぶし」「塗りつぶしv2」の場合の最小サイズ制約です。",
    )
    """アノテーションの種類が「ポリゴン」「ポリライン」「塗りつぶし」「塗りつぶしv2」の場合の最小サイズ制約です。"""

    minimum_area_2d: MinimumArea2dFieldValue | None = Field(
        default=None,
        description="アノテーションの種類が「ポリゴン」の場合の最小面積制約です。",
    )
    """アノテーションの種類が「ポリゴン」の場合の最小面積制約です。"""

    margin_of_error_tolerance: MarginOfErrorToleranceFieldValue | None = Field(default=None, description="許容誤差に関する設定です。")
    """許容誤差に関する設定です。"""

    display_line_direction: DisplayLineDirectionFieldValue | None = Field(default=None, description="アノテーションの種類が「ポリライン」の場合の線分方向の表示に関する設定です。")
    """アノテーションの種類が「ポリライン」の場合の線分方向の表示に関する設定です。"""

    vertex_count_min_max: VertexCountMinMaxFieldValue | None = Field(default=None, description="アノテーションの種類が「ポリライン」または「ポリゴン」の場合の頂点数制約です。")
    """アノテーションの種類が「ポリライン」または「ポリゴン」の場合の頂点数制約です。"""


class LabelCandidate(BaseModel):
    """
    追加候補のラベル情報です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    label_name_en: str = Field(description="追加するラベル名（英語）です。特に指定がない限り、英語小文字のスネークケースで記述してください。")
    """ラベル名（英語）です。"""

    annotation_type: AnnotationType = Field(description="追加するラベルのアノテーション種類です。")
    """アノテーション種類です。"""

    label_name_ja: str | None = Field(default=None, description="追加するラベル名（日本語）です。")
    """ラベル名（日本語）です。"""

    color: str | None = Field(default=None, description="ラベル色です。指定する場合は `#RRGGBB` 形式にしてください。")
    """ラベル色です。 ``#RRGGBB`` 形式です。"""

    keybind: KeybindCandidate | None = Field(default=None, description="ラベルに設定するキーボードショートカットです。")
    """ラベルに設定するキーボードショートカットです。"""

    field_values: FieldValues = Field(default_factory=FieldValues, description="ラベルごとの制約、表示設定、許容誤差などの field_values です。")
    """ラベルごとの制約、表示設定、許容誤差などの field_values です。"""

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


class UnresolvedText(BaseModel):
    """
    ラベル追加ルールとして解釈できなかった原文と理由です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    text: str = Field(description="ラベル追加ルールとして解釈できなかった原文の断片です。")
    """ラベル追加ルールとして解釈できなかった原文の断片です。"""

    reason: str = Field(description="解釈できなかった理由です。")
    """解釈できなかった理由です。"""

    required_information: list[str] = Field(default_factory=list, description="解釈するために必要な補足情報の一覧です。")
    """解釈するために必要な補足情報の一覧です。"""


class LabelParseResult(BaseModel):
    """
    ラベルの自然言語解析結果です。
    """

    model_config = STRUCTURED_OUTPUT_MODEL_CONFIG

    labels: list[LabelCandidate] = Field(description="解析できた追加対象ラベルの一覧です。")
    """解析できたラベル候補の一覧です。"""

    warnings: list[str] = Field(default_factory=list, description="解析時の注意事項です。解析結果に含めたが補足したい内容を入れてください。")
    """解析時の注意事項です。"""

    unresolved_texts: list[UnresolvedText] = Field(default_factory=list, description="ラベル追加ルールとして解釈できなかった原文、理由、必要な補足情報です。")
    """ラベル追加ルールとして解釈できなかった原文、理由、必要な補足情報です。"""


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


class LabelCatalogItem(BaseModel):
    """
    LLMへ渡すための既存ラベル情報です。
    """

    label_name_en: str = Field(description="既存ラベル名（英語）です。")
    """既存ラベル名（英語）です。"""

    label_name_ja: str = Field(description="既存ラベル名（日本語）です。")
    """既存ラベル名（日本語）です。"""

    annotation_type: str = Field(description="既存ラベルのアノテーション種類です。例: bounding_box, polygon")
    """既存ラベルのアノテーション種類です。"""

    color: str | None = Field(description="既存ラベルの色です。例: #FF0000")
    """既存ラベルの色です。"""

    keybind: KeybindCandidate | None = Field(description="既存ラベルに設定されたキーボードショートカットです。")
    """既存ラベルに設定されたキーボードショートカットです。"""

    field_values: dict[str, Any] = Field(description="既存ラベルごとの制約、表示設定、許容誤差などです。")
    """既存ラベルごとの制約、表示設定、許容誤差などです。"""


def dump_label_catalog(label_catalog: list[LabelCatalogItem]) -> list[dict[str, Any]]:
    """
    ラベルCatalogモデルをLLMへ渡すJSON互換のdictへ変換します。

    Args:
        label_catalog: ラベルCatalogモデル一覧

    Returns:
        JSON互換のdict一覧
    """
    return [item.model_dump(mode="json") for item in label_catalog]


def get_required_message(annotation_text: dict[str, Any], *, lang: str) -> str:
    """
    多言語メッセージから指定言語の必須文字列を取得します。

    Args:
        annotation_text: Annofab APIの多言語メッセージ
        lang: 取得対象の言語コード

    Returns:
        見つかった文字列

    Raises:
        ValueError: 指定言語の文字列が存在しない場合
    """
    message = get_message(annotation_text, lang=lang)
    if message is None:
        raise ValueError(f"annotation specs に必須メッセージが存在しません。 :: lang='{lang}'")
    return message


def get_catalog_keybind(keybinds: list[dict[str, Any]] | None) -> KeybindCandidate | None:
    """
    Annofab APIのkeybind配列からCatalog用の単一keybindを取得します。

    Args:
        keybinds: Annofab APIのkeybind配列

    Returns:
        Catalog用の単一keybind。未設定の場合はNone
    """
    if keybinds is None or len(keybinds) == 0:
        return None
    return KeybindCandidate.model_validate(keybinds[0])


def get_label_catalog(annotation_specs: dict[str, Any]) -> list[LabelCatalogItem]:
    """
    LLMへ渡すための既存ラベル一覧を生成します。

    Args:
        annotation_specs: アノテーション仕様(v3)

    Returns:
        既存ラベル一覧
    """
    catalog = []
    for label in annotation_specs["labels"]:
        label_name = label["label_name"]
        catalog.append(
            LabelCatalogItem(
                label_name_en=get_required_message(label_name, lang="en-US"),
                label_name_ja=get_required_message(label_name, lang="ja-JP"),
                annotation_type=label["annotation_type"],
                color=label["color"],
                keybind=get_catalog_keybind(label["keybind"]),
                field_values=label["field_values"],
            )
        )
    return catalog


def generate_add_labels_from_text(
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

指定されたプロジェクト種別で利用可能な annotation_type だけを使用してください。


できるだけラベルにキーボードショートカットを設定するため、 keybind を出力してください。
できるだけ、ラベルの順番とキーの順番が対応するようにしてください。
ただし、既存のラベルのショートカットと重複しないようにしてください。既存のショートカットと重複する場合は、warnings に入れてください。

ラベル定義として解釈できる文だけを解析対象にしてください。
属性定義、属性制約、作業手順、品質基準など、明らかにラベル定義ではない文は warnings や unresolved_texts に入れず無視してください。
ラベル定義として解釈できる可能性があるが、label_name_en または annotation_type を特定できない文は labels に入れず unresolved_texts に入れてください。
ラベル定義として解釈できる可能性があるが曖昧な文も unresolved_texts に入れてください。
unresolved_texts には、解釈できなかった原文を text、解釈できなかった理由を reason、解釈に必要な補足情報を required_information に出力してください。
たとえば annotation_type が不明な場合は、required_information に「annotation_type」を含めてください。
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
{json.dumps(dump_label_catalog(label_catalog), ensure_ascii=False, indent=2)}
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
        print_json(dump_label_catalog(label_catalog), temp_dir / "label_catalog.json")
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


def format_unresolved_text(unresolved_text: UnresolvedText) -> str:
    """
    未解決テキストをログや対話入力用の文字列に変換します。

    Args:
        unresolved_text: 未解決テキスト

    Returns:
        未解決テキストの説明
    """
    required_information = ", ".join(unresolved_text.required_information) if unresolved_text.required_information else "(none)"
    return f"text='{unresolved_text.text}', reason='{unresolved_text.reason}', required_information=[{required_information}]"


def log_parse_warnings(result: LabelParseResult) -> None:
    """
    ラベル解析結果の注意事項と未解決テキストをログに出力します。

    Args:
        result: ラベル解析結果
    """
    for warning in result.warnings:
        logger.warning(f"ラベル解析時に注意事項がありました。 :: {warning}")
    for unresolved_text in result.unresolved_texts:
        logger.warning(f"ラベル追加ルールとして解釈できないテキストがありました。 :: {format_unresolved_text(unresolved_text)}")


def collect_supplements_interactively(unresolved_texts: list[UnresolvedText]) -> list[str]:
    """
    未解決テキストに対してユーザーから補足情報をインタラクティブに収集します。

    Args:
        unresolved_texts: ラベル追加ルールとして解釈できなかった原文、理由、必要な補足情報の一覧

    Returns:
        ユーザーが入力した補足情報の一覧
    """
    supplements: list[str] = []
    for _i, unresolved_text in enumerate(unresolved_texts, start=1):
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


def normalize_parsed_labels(result: LabelParseResult, annotation_specs: dict[str, Any], *, project_type: ProjectType) -> LabelParseResult:
    """
    解析済みラベル候補を正規化します。

    Args:
        result: LLMの解析結果
        annotation_specs: アノテーション仕様(v3)

    Returns:
        正規化済みの解析結果
    """
    existing_label_name_ens = {label.label_name_en for label in get_label_catalog(annotation_specs)}
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


def dump_label_for_annofab(label: LabelCandidate) -> dict[str, Any]:
    """
    ラベル候補をAnnofab CLIへ渡すための辞書に変換します。

    Args:
        label: ラベル候補

    Returns:
        Annofab CLIに渡すラベル辞書
    """
    dumped = label.model_dump(mode="json")
    field_values = dumped.get("field_values")
    if isinstance(field_values, dict):
        dumped["field_values"] = {key: value for key, value in field_values.items() if value is not None}
    return {key: value for key, value in dumped.items() if value is not None}


def to_annofab_labels(result: LabelParseResult) -> list[dict[str, Any]]:
    """
    解析結果を ``annotation_specs add_labels --label_json`` に渡せるJSONへ変換します。

    Args:
        result: ラベルの解析結果

    Returns:
        add_labels向けのJSON配列
    """
    return [dump_label_for_annofab(label) for label in result.labels]


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
    result = generate_add_labels_from_text(
        text=current_text,
        annotation_specs=annotation_specs,
        project_type=args.project_type,
        llm_model=args.model,
        temp_dir=temp_dir,
    )
    result = normalize_parsed_labels(result, annotation_specs, project_type=args.project_type)
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
        result = generate_add_labels_from_text(
            text=current_text,
            annotation_specs=annotation_specs,
            project_type=args.project_type,
            llm_model=args.model,
            temp_dir=temp_dir,
        )
        result = normalize_parsed_labels(result, annotation_specs, project_type=args.project_type)
        print_json(result.model_dump(mode="json"), temp_dir / "parse_result.json")

        log_parse_warnings(result)

    annofab_labels = to_annofab_labels(result)
    if len(annofab_labels) == 0:
        raise ValueError("アノテーション仕様に追加可能なラベルを抽出できませんでした。")

    print_json(annofab_labels, output=args.output)
    if args.output is None:
        logger.info("追加対象ラベルのJSONを標準出力に出力しました。")
    else:
        logger.info(f"追加対象ラベルのJSONをファイルに出力しました。 :: output='{args.output}'")
    logger.info(OUTPUT_USAGE_MESSAGE)
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
    parser = acl.common.cli.add_parser(
        subparsers,
        COMMAND_NAME,
        "自然言語からラベル追加用JSONを生成します。",
        description=f"自然言語からラベル追加用JSONを生成します。\n{OUTPUT_USAGE_MESSAGE}",
    )
    add_argument_to_parser(parser)
    parser.set_defaults(func=main)
    return parser
