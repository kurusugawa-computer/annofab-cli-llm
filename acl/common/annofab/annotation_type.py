from enum import StrEnum

from annofabapi.models import DefaultAnnotationType
from annofabapi.plugin import ThreeDimensionAnnotationType


class ProjectType(StrEnum):
    """
    generate_add_labels_jsonコマンドで扱うプロジェクト種別です。
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


def get_annotation_type_details() -> list[dict[str, str]]:
    """
    利用可能な annotation_type と説明を返します。

    Returns:
        annotation_type と説明の一覧
    """
    return [{"value": annotation_type.value, "description": description} for annotation_type, description in ANNOTATION_TYPE_DESCRIPTIONS.items()]


def get_allowed_annotation_type_details(project_type: ProjectType) -> list[dict[str, str]]:
    """
    指定したプロジェクト種別で利用可能な annotation_type と説明を返します。

    Args:
        project_type: プロジェクト種別

    Returns:
        annotation_type と説明の一覧
    """
    return [{"value": annotation_type.value, "description": ANNOTATION_TYPE_DESCRIPTIONS[annotation_type]} for annotation_type in get_allowed_annotation_types(project_type)]
