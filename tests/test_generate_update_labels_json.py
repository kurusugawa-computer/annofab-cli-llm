from types import SimpleNamespace

import pytest

from acl.command.generate_add_labels_json import FieldValues, KeybindCandidate, MarginOfErrorToleranceFieldValue, UnresolvedText
from acl.command.generate_update_labels_json import (
    LabelUpdateCandidate,
    LabelUpdateParseResult,
    get_label_update_catalog,
    normalize_label_color,
    normalize_parsed_update_labels,
    parse_update_labels_from_text,
    to_annofab_update_labels,
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
                "color": {"red": 255, "green": 0, "blue": 0},
                "keybind": [
                    {
                        "alt": False,
                        "code": "Digit1",
                        "ctrl": True,
                        "shift": False,
                    }
                ],
                "field_values": {
                    "margin_of_error_tolerance": {
                        "_type": "MarginOfErrorTolerance",
                        "max_pixel": 5,
                    }
                },
                "additional_data_definitions": [],
            }
        ],
        "additionals": [],
    }


def test_parse_update_labels_from_text(monkeypatch, annotation_specs):
    result = LabelUpdateParseResult(
        labels=[
            LabelUpdateCandidate(
                label_id="label_car",
                label_name_ja="自動車",
                color="#00AAFF",
                keybind=KeybindCandidate(code="Digit2", ctrl=True),
            )
        ],
        warnings=["色は文脈から補いました。"],
        unresolved_texts=[
            UnresolvedText(
                text="車の判定条件も見直してください。",
                reason="ラベル更新情報ではありません。",
                required_information=[],
            )
        ],
    )
    actual_messages = []

    def fake_completion(**kwargs):
        assert kwargs["response_format"] is LabelUpdateParseResult
        actual_messages.extend(kwargs["messages"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=result.model_dump_json()))],
            usage=SimpleNamespace(total_tokens=12, prompt_tokens=8, completion_tokens=4),
        )

    monkeypatch.setattr("acl.command.generate_update_labels_json.completion", fake_completion)

    actual = parse_update_labels_from_text(
        text="carラベルの日本語名を自動車に変更し、色を #00AAFF にしてください。",
        annotation_specs=annotation_specs,
        llm_model="openai/gpt-5.4-nano",
    )

    assert actual == result
    developer_content = actual_messages[0]["content"]
    user_content = actual_messages[1]["content"]
    assert "既存ラベルを更新する内容だけを labels に入れてください。" in developer_content
    assert "更新対象は必ず既存ラベル一覧の label_id で指定してください。" in developer_content
    assert "## 既存ラベル一覧" in user_content
    assert '"label_id": "label_car"' in user_content
    assert '"field_values": {' in user_content


def test_get_label_update_catalog(annotation_specs):
    actual = get_label_update_catalog(annotation_specs)

    assert actual[0].model_dump(mode="json") == {
        "label_id": "label_car",
        "label_name_en": "car",
        "label_name_ja": "車",
        "annotation_type": "bounding_box",
        "color": "#FF0000",
        "keybind": {
            "alt": False,
            "code": "Digit1",
            "ctrl": True,
            "shift": False,
        },
        "field_values": {
            "margin_of_error_tolerance": {
                "_type": "MarginOfErrorTolerance",
                "max_pixel": 5,
            }
        },
    }


def test_normalize_label_color():
    assert normalize_label_color({"red": 255, "green": 0, "blue": 170}) == "#FF00AA"
    assert normalize_label_color("#00AAFF") == "#00AAFF"
    assert normalize_label_color(None) is None
    assert normalize_label_color({"red": 255, "green": "0", "blue": 170}) is None


def test_normalize_parsed_update_labels(annotation_specs):
    result = LabelUpdateParseResult(
        labels=[
            LabelUpdateCandidate(label_id="label_car", label_name_ja="自動車"),
            LabelUpdateCandidate(label_id="unknown_label", label_name_ja="不明"),
            LabelUpdateCandidate(label_id="label_car", color="#00AAFF"),
            LabelUpdateCandidate(label_id="label_car"),
        ]
    )

    actual = normalize_parsed_update_labels(result, annotation_specs)

    assert actual.labels == [LabelUpdateCandidate(label_id="label_car", label_name_ja="自動車")]
    assert len(actual.warnings) == 3


def test_to_annofab_update_labels():
    result = LabelUpdateParseResult(
        labels=[
            LabelUpdateCandidate(
                label_id="label_car",
                label_name_ja="自動車",
                field_values=FieldValues(
                    margin_of_error_tolerance=MarginOfErrorToleranceFieldValue(
                        _type="MarginOfErrorTolerance",
                        max_pixel=10,
                    )
                ),
            )
        ]
    )

    actual = to_annofab_update_labels(result)

    assert actual == [
        {
            "label_id": "label_car",
            "label_name_ja": "自動車",
            "field_values": {
                "margin_of_error_tolerance": {
                    "_type": "MarginOfErrorTolerance",
                    "max_pixel": 10,
                }
            },
            "field_values_operation": "replace",
        }
    ]
