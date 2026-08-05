from types import SimpleNamespace

import pytest

from acl.command.generate_add_labels_json import KeybindCandidate, UnresolvedText
from acl.command.generate_update_attributes_json import (
    AttributeUpdateCandidate,
    AttributeUpdateParseResult,
    ChoiceUpdateCandidate,
    get_attribute_update_catalog,
    normalize_parsed_update_attributes,
    parse_update_attributes_from_text,
    to_annofab_update_attributes,
)


@pytest.fixture
def annotation_specs() -> dict:
    return {
        "labels": [
            {
                "label_id": "label_car",
                "label_name": {
                    "messages": [
                        {"lang": "en-US", "message": "car"},
                        {"lang": "ja-JP", "message": "車"},
                    ]
                },
                "annotation_type": "bounding_box",
                "keybind": None,
                "additional_data_definitions": ["attr_note", "attr_vehicle_type"],
            }
        ],
        "additionals": [
            {
                "additional_data_definition_id": "attr_note",
                "name": {
                    "messages": [
                        {"lang": "en-US", "message": "note"},
                        {"lang": "ja-JP", "message": "メモ"},
                        {"lang": "vi-VN", "message": "ghi chú"},
                    ]
                },
                "type": "text",
                "read_only": False,
                "default": None,
                "keybind": [
                    {
                        "alt": False,
                        "code": "KeyQ",
                        "ctrl": False,
                        "shift": False,
                    }
                ],
                "choices": [],
            },
            {
                "additional_data_definition_id": "attr_vehicle_type",
                "name": {
                    "messages": [
                        {"lang": "en-US", "message": "vehicle_type"},
                        {"lang": "ja-JP", "message": "車種"},
                    ]
                },
                "type": "select",
                "read_only": True,
                "default": None,
                "keybind": None,
                "choices": [
                    {
                        "choice_id": "choice_general_car",
                        "name": {
                            "messages": [
                                {"lang": "en-US", "message": "general_car"},
                                {"lang": "ja-JP", "message": "乗用車"},
                            ]
                        },
                        "is_default": True,
                        "keybind": [
                            {
                                "alt": False,
                                "code": "KeyW",
                                "ctrl": False,
                                "shift": False,
                            }
                        ],
                    },
                    {
                        "choice_id": "choice_truck",
                        "name": {
                            "messages": [
                                {"lang": "en-US", "message": "truck"},
                                {"lang": "ja-JP", "message": "トラック"},
                            ]
                        },
                        "is_default": False,
                        "keybind": None,
                    },
                ],
            },
        ],
    }


def test_parse_update_attributes_from_text(monkeypatch, annotation_specs):
    result = AttributeUpdateParseResult(
        attributes=[
            AttributeUpdateCandidate(
                attribute_id="attr_note",
                attribute_name_ja="コメント",
                read_only=True,
                keybind=KeybindCandidate(code="Digit2", ctrl=True),
            ),
            AttributeUpdateCandidate(
                attribute_id="attr_vehicle_type",
                choice_updates=[
                    ChoiceUpdateCandidate(choice_id="choice_truck", choice_name_ja="貨物車"),
                ],
            ),
        ],
        warnings=["choiceの英語名は変更しませんでした。"],
        unresolved_texts=[
            UnresolvedText(
                text="車種にバスを追加してください。",
                reason="選択肢の追加は update_attributes では実行できません。",
                required_information=["command"],
            )
        ],
    )
    actual_messages = []

    def fake_completion(**kwargs):
        assert kwargs["response_format"] is AttributeUpdateParseResult
        actual_messages.extend(kwargs["messages"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=result.model_dump_json()))],
            usage=SimpleNamespace(total_tokens=14, prompt_tokens=10, completion_tokens=4),
        )

    monkeypatch.setattr("acl.command.generate_update_attributes_json.completion", fake_completion)

    actual = parse_update_attributes_from_text(
        text="note属性の日本語名をコメントに変更し、vehicle_typeのtruckを貨物車にしてください。",
        annotation_specs=annotation_specs,
        llm_model="openai/gpt-5.4-nano",
    )

    assert actual == result
    developer_content = actual_messages[0]["content"]
    user_content = actual_messages[1]["content"]
    assert "既存属性を更新する内容だけを attributes に入れてください。" in developer_content
    assert "更新対象は必ず既存属性一覧の attribute_id で指定してください。" in developer_content
    assert "選択肢の追加・削除は update_attributes では実行できない" in developer_content
    assert "## 既存属性一覧" in user_content
    assert '"attribute_id": "attr_vehicle_type"' in user_content
    assert '"choice_id": "choice_truck"' in user_content


def test_get_attribute_update_catalog(annotation_specs):
    actual = get_attribute_update_catalog(annotation_specs)

    assert actual[0].model_dump(mode="json") == {
        "attribute_id": "attr_note",
        "attribute_name_en": "note",
        "attribute_name_ja": "メモ",
        "attribute_name_vi": "ghi chú",
        "attribute_type": "text",
        "label_name_ens": ["car"],
        "read_only": False,
        "default": None,
        "keybind": {
            "alt": False,
            "code": "KeyQ",
            "ctrl": False,
            "shift": False,
        },
        "choices": [],
    }
    assert actual[1].choices[0].model_dump(mode="json") == {
        "choice_id": "choice_general_car",
        "choice_name_en": "general_car",
        "choice_name_ja": "乗用車",
        "is_default": True,
        "keybind": {
            "alt": False,
            "code": "KeyW",
            "ctrl": False,
            "shift": False,
        },
    }


def test_normalize_parsed_update_attributes(annotation_specs):
    result = AttributeUpdateParseResult(
        attributes=[
            AttributeUpdateCandidate(attribute_id="attr_note", attribute_name_ja="コメント"),
            AttributeUpdateCandidate(attribute_id="unknown_attribute", attribute_name_ja="不明"),
            AttributeUpdateCandidate(attribute_id="attr_note", read_only=True),
            AttributeUpdateCandidate(
                attribute_id="attr_vehicle_type",
                choice_updates=[
                    ChoiceUpdateCandidate(choice_id="unknown_choice", choice_name_ja="不明"),
                    ChoiceUpdateCandidate(choice_id="choice_truck", choice_name_ja="貨物車"),
                    ChoiceUpdateCandidate(choice_id="choice_truck", choice_name_en="truck2"),
                ],
            ),
            AttributeUpdateCandidate(
                attribute_id="attr_note",
                choice_updates=[
                    ChoiceUpdateCandidate(choice_id="choice_truck", choice_name_ja="貨物車"),
                ],
            ),
        ]
    )

    actual = normalize_parsed_update_attributes(result, annotation_specs)

    assert actual.attributes == [
        AttributeUpdateCandidate(attribute_id="attr_note", attribute_name_ja="コメント"),
        AttributeUpdateCandidate(
            attribute_id="attr_vehicle_type",
            choice_updates=[
                ChoiceUpdateCandidate(choice_id="choice_truck", choice_name_ja="貨物車"),
            ],
        ),
    ]
    assert len(actual.warnings) == 5


def test_to_annofab_update_attributes():
    result = AttributeUpdateParseResult(
        attributes=[
            AttributeUpdateCandidate(
                attribute_id="attr_note",
                attribute_name_ja="コメント",
                read_only=True,
                default_value="確認済み",
            ),
            AttributeUpdateCandidate(
                attribute_id="attr_vehicle_type",
                choice_updates=[
                    ChoiceUpdateCandidate(choice_id="choice_general_car", choice_name_ja="乗用車"),
                    ChoiceUpdateCandidate(choice_id="choice_truck", keybind=None),
                ],
            ),
        ]
    )

    actual = to_annofab_update_attributes(result)

    assert actual == [
        {
            "attribute_id": "attr_note",
            "attribute_name_ja": "コメント",
            "read_only": True,
            "default_value": "確認済み",
        },
        {
            "attribute_id": "attr_vehicle_type",
            "choice_updates": [
                {
                    "choice_id": "choice_general_car",
                    "choice_name_ja": "乗用車",
                },
                {
                    "choice_id": "choice_truck",
                    "keybind": None,
                },
            ],
        },
    ]
