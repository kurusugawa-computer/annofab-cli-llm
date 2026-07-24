from annofabapi.models import AdditionalDataDefinitionType

ATTRIBUTE_TYPE_DESCRIPTIONS: dict[AdditionalDataDefinitionType, str] = {
    AdditionalDataDefinitionType.FLAG: "チェックボックス",
    AdditionalDataDefinitionType.INTEGER: "整数",
    AdditionalDataDefinitionType.TEXT: "自由記述（1行）",
    AdditionalDataDefinitionType.COMMENT: "自由記述（複数行）",
    AdditionalDataDefinitionType.CHOICE: "ラジオボタン（排他選択）",
    AdditionalDataDefinitionType.SELECT: "ドロップダウン（排他選択）",
    AdditionalDataDefinitionType.TRACKING: "トラッキングID",
    AdditionalDataDefinitionType.LINK: "アノテーションリンク",
}
"""attribute_type の説明です。"""


def get_attribute_type_details() -> list[dict[str, str]]:
    """
    利用可能な attribute_type と説明を返します。

    Returns:
        attribute_type と説明の一覧
    """
    return [{"value": attribute_type.value, "description": description} for attribute_type, description in ATTRIBUTE_TYPE_DESCRIPTIONS.items()]
