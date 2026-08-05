from types import SimpleNamespace

import pytest

from acl.command.generate_add_choices_to_attributes_json import (
    ChoiceCandidate,
    ChoiceParseResult,
    get_target_attribute,
    normalize_parsed_choices,
    parse_add_choices_from_text,
    to_annofab_attributes,
)
from acl.command.generate_add_labels_json import UnresolvedText


@pytest.fixture
def annotation_specs() -> dict:
    return {
        "additionals": [
            {
                "additional_data_definition_id": "attr_vehicle_type",
                "name": {
                    "messages": [
                        {"lang": "en-US", "message": "vehicle_type"},
                        {"lang": "ja-JP", "message": "車種"},
                    ]
                },
                "type": "select",
                "choices": [
                    {
                        "choice_id": "choice_car",
                        "name": {
                            "messages": [
                                {"lang": "en-US", "message": "car"},
                                {"lang": "ja-JP", "message": "乗用車"},
                            ]
                        },
                    }
                ],
            },
            {
                "additional_data_definition_id": "attr_note",
                "name": {
                    "messages": [
                        {"lang": "en-US", "message": "note"},
                        {"lang": "ja-JP", "message": "メモ"},
                    ]
                },
                "type": "text",
                "choices": [],
            },
        ]
    }


def test_parse_add_choices_from_text(monkeypatch, annotation_specs):
    result = ChoiceParseResult(
        choices=[ChoiceCandidate(choice_name_en="truck", choice_name_ja="トラック")],
        unresolved_texts=[
            UnresolvedText(text="色も追加", reason="対象属性が異なります。", required_information=["attribute_id"]),
        ],
    )
    actual_messages = []

    def fake_completion(**kwargs):
        assert kwargs["response_format"] is ChoiceParseResult
        actual_messages.extend(kwargs["messages"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=result.model_dump_json()))],
            usage=SimpleNamespace(total_tokens=14, prompt_tokens=10, completion_tokens=4),
        )

    monkeypatch.setattr("acl.command.generate_add_choices_to_attributes_json.completion", fake_completion)
    attribute = get_target_attribute(annotation_specs, "attr_vehicle_type")

    actual = parse_add_choices_from_text(text="車種にトラックを追加してください。", attribute=attribute, llm_model="openai/gpt-5.6-terra")

    assert actual == result
    assert "指定された属性に追加する選択肢だけを choices に入れてください。" in actual_messages[0]["content"]
    assert '"attribute_id": "attr_vehicle_type"' in actual_messages[1]["content"]
    assert '"choice_name_en": "car"' in actual_messages[1]["content"]


def test_normalize_parsed_choices_removes_existing_and_duplicate_choices(annotation_specs):
    attribute = get_target_attribute(annotation_specs, "attr_vehicle_type")
    result = ChoiceParseResult(
        choices=[
            ChoiceCandidate(choice_name_en="car", choice_name_ja="自動車"),
            ChoiceCandidate(choice_name_en="truck", choice_name_ja="トラック"),
            ChoiceCandidate(choice_name_en="truck", choice_name_ja="貨物車"),
        ]
    )

    actual = normalize_parsed_choices(result, attribute)

    assert actual.choices == [ChoiceCandidate(choice_name_en="truck", choice_name_ja="トラック")]
    assert len(actual.warnings) == 2


def test_to_annofab_attributes_excludes_empty_optional_values():
    result = ChoiceParseResult(
        choices=[
            ChoiceCandidate(choice_name_en="truck", choice_name_ja="トラック"),
            ChoiceCandidate(choice_id="choice_bus", choice_name_en="bus"),
        ]
    )

    assert to_annofab_attributes(result, attribute_id="attr_vehicle_type") == [
        {
            "attribute_id": "attr_vehicle_type",
            "choices": [
                {"choice_name_en": "truck", "choice_name_ja": "トラック"},
                {"choice_id": "choice_bus", "choice_name_en": "bus"},
            ],
        },
    ]


def test_get_target_attribute_rejects_unknown_attribute(annotation_specs):
    with pytest.raises(ValueError, match="存在しません"):
        get_target_attribute(annotation_specs, "unknown")
