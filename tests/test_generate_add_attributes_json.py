import json
from types import SimpleNamespace

import pytest
from annofabapi.models import AdditionalDataDefinitionType

from acl.command.generate_add_attributes_json import (
    AttributeCandidate,
    AttributeParseResult,
    ChoiceCandidate,
    generate_add_attributes_from_text,
    get_annotation_specs,
    get_attribute_catalog,
    get_label_catalog,
    is_default_choice,
    normalize_parsed_attributes,
    to_annofab_attributes,
)
from acl.command.generate_add_labels_json import KeybindCandidate, UnresolvedText


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
                "keybind": [
                    {
                        "alt": False,
                        "code": "Digit1",
                        "ctrl": True,
                        "shift": False,
                    }
                ],
                "additional_data_definitions": ["attr_occluded", "attr_vehicle_type"],
            },
            {
                "label_id": "label_pedestrian",
                "label_name": {
                    "messages": [
                        {"lang": "en-US", "message": "pedestrian"},
                        {"lang": "ja-JP", "message": "歩行者"},
                    ]
                },
                "annotation_type": "polygon",
                "keybind": None,
                "additional_data_definitions": [],
            },
        ],
        "additionals": [
            {
                "additional_data_definition_id": "attr_occluded",
                "name": {
                    "messages": [
                        {"lang": "en-US", "message": "occluded"},
                        {"lang": "ja-JP", "message": "隠れ"},
                    ]
                },
                "type": "flag",
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
                "default": "choice_general_car",
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
                        "keybind": [
                            {
                                "alt": False,
                                "code": "KeyE",
                                "ctrl": False,
                                "shift": False,
                            }
                        ],
                    },
                ],
            },
        ],
    }


def test_generate_add_attributes_from_text(monkeypatch, annotation_specs):
    result = AttributeParseResult(
        attributes=[
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.FLAG,
                attribute_name_en="truncated",
                attribute_name_ja="見切れ",
                label_name_ens=["car", "pedestrian"],
                read_only=True,
            ),
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.SELECT,
                attribute_name_en="weather",
                label_name_ens=["car"],
                choices=[
                    ChoiceCandidate(choice_name_en="sunny", choice_name_ja="晴れ", is_default=True),
                    ChoiceCandidate(choice_name_en="rainy", choice_name_ja="雨"),
                ],
            ),
        ],
        warnings=["weather の attribute_type は文脈から補いました。"],
        unresolved_texts=[
            UnresolvedText(
                text="注記の扱いが不明でした。",
                reason="対象ラベルと attribute_type を特定できませんでした。",
                required_information=["label_name_ens", "attribute_type"],
            )
        ],
    )
    actual_messages = []

    def fake_completion(**kwargs):
        assert kwargs["response_format"] is AttributeParseResult
        actual_messages.extend(kwargs["messages"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=result.model_dump_json()))],
            usage=SimpleNamespace(total_tokens=14, prompt_tokens=10, completion_tokens=4),
        )

    monkeypatch.setattr("acl.command.generate_add_attributes_json.completion", fake_completion)

    actual = generate_add_attributes_from_text(
        text="car と pedestrian に truncated 属性を追加し、car には weather をドロップダウンで追加してください。",
        annotation_specs=annotation_specs,
        llm_model="openai/gpt-5.4-nano",
    )

    assert actual == result
    developer_content = actual_messages[0]["content"]
    user_content = actual_messages[1]["content"]
    assert "## 利用可能な attribute_type と説明" in user_content
    assert "## 既存ラベル一覧" in user_content
    assert "## 既存属性一覧" in user_content
    assert '"value": "select"' in user_content
    assert '"description": "チェックボックス"' in user_content
    assert '"annotation_type": "bounding_box"' in user_content
    assert '"attribute_name_en": "occluded"' in user_content
    assert '"choices": [' in user_content
    assert '"choice_name_en": "general_car"' in user_content
    assert '"keybind": {' in user_content
    assert '"code": "Digit1"' in user_content
    assert '"code": "KeyQ"' in user_content
    assert '"code": "KeyW"' in user_content
    assert "warnings" in developer_content
    assert "`choice` または `select` の場合は、choices を2件以上出力してください。" in developer_content
    assert "解釈できなかった原文を text、解釈できなかった理由を reason、解釈に必要な補足情報を required_information" in developer_content


def test_get_label_catalog_includes_annotation_type_and_keybind(annotation_specs):
    actual = get_label_catalog(annotation_specs)

    assert actual[0].model_dump(mode="json") == {
        "label_name_en": "car",
        "label_name_ja": "車",
        "annotation_type": "bounding_box",
        "keybind": {
            "alt": False,
            "code": "Digit1",
            "ctrl": True,
            "shift": False,
        },
    }


def test_get_attribute_catalog_includes_keybind_and_choice_details(annotation_specs):
    actual = get_attribute_catalog(annotation_specs)

    assert actual[0].model_dump(mode="json") == {
        "attribute_name_en": "occluded",
        "attribute_name_ja": "隠れ",
        "attribute_type": "flag",
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


def test_get_attribute_catalog_allows_unrestricted_existing_keybind(annotation_specs):
    annotation_specs["additionals"][0]["keybind"][0]["code"] = "Numpad1"

    actual = get_attribute_catalog(annotation_specs)

    assert actual[0].keybind is not None
    assert actual[0].keybind.code == "Numpad1"
    assert actual[1].choices[0].model_dump(mode="json") == {
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


def test_is_default_choice():
    additional = {"default": "choice_general_car"}

    assert is_default_choice(additional=additional, choice={"choice_id": "choice_general_car"})
    assert not is_default_choice(additional=additional, choice={"choice_id": "choice_truck"})
    assert not is_default_choice(additional={"default": ""}, choice={"choice_id": "choice_general_car"})


def test_normalize_parsed_attributes(annotation_specs):
    result = AttributeParseResult(
        attributes=[
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.FLAG,
                attribute_name_en="truncated",
                label_name_ens=["car"],
            ),
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.FLAG,
                attribute_name_en="occluded",
                label_name_ens=["pedestrian"],
            ),
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.FLAG,
                attribute_name_en="occluded",
                label_name_ens=["car"],
            ),
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.FLAG,
                attribute_name_en="truncated",
                label_name_ens=["pedestrian"],
            ),
        ]
    )

    actual = normalize_parsed_attributes(result, annotation_specs)

    assert actual.attributes == [
        AttributeCandidate(
            attribute_type=AdditionalDataDefinitionType.FLAG,
            attribute_name_en="truncated",
            label_name_ens=["car"],
        ),
        AttributeCandidate(
            attribute_type=AdditionalDataDefinitionType.FLAG,
            attribute_name_en="occluded",
            label_name_ens=["pedestrian"],
        ),
        AttributeCandidate(
            attribute_type=AdditionalDataDefinitionType.FLAG,
            attribute_name_en="truncated",
            label_name_ens=["pedestrian"],
        ),
    ]
    assert len(actual.warnings) == 1


def test_normalize_parsed_attributes_for_overlapped_labels(annotation_specs):
    result = AttributeParseResult(
        attributes=[
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.FLAG,
                attribute_name_en="truncated",
                label_name_ens=["car"],
            ),
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.FLAG,
                attribute_name_en="truncated",
                label_name_ens=["car", "pedestrian"],
            ),
        ]
    )

    actual = normalize_parsed_attributes(result, annotation_specs)

    assert actual.attributes == [
        AttributeCandidate(
            attribute_type=AdditionalDataDefinitionType.FLAG,
            attribute_name_en="truncated",
            label_name_ens=["car"],
        )
    ]
    assert len(actual.warnings) == 1


def test_normalize_parsed_attributes_for_unknown_label(annotation_specs):
    result = AttributeParseResult(
        attributes=[
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.FLAG,
                attribute_name_en="blurred",
                label_name_ens=["unknown_label"],
            ),
        ]
    )

    actual = normalize_parsed_attributes(result, annotation_specs)

    assert actual.attributes == []
    assert len(actual.warnings) == 1


def test_normalize_parsed_attributes_removes_keybind_equivalent_to_existing_numpad_keybind(annotation_specs):
    annotation_specs["labels"][0]["keybind"][0]["code"] = "Numpad1"
    result = AttributeParseResult(
        attributes=[
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.TEXT,
                attribute_name_en="note",
                label_name_ens=["pedestrian"],
                keybind=KeybindCandidate(code="Digit1", ctrl=True),
            )
        ]
    )

    actual = normalize_parsed_attributes(result, annotation_specs)

    assert actual.attributes[0].keybind is None
    assert len(actual.warnings) == 1


def test_normalize_parsed_attributes_removes_duplicate_choice_keybind(annotation_specs):
    result = AttributeParseResult(
        attributes=[
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.CHOICE,
                attribute_name_en="weather",
                label_name_ens=["pedestrian"],
                choices=[
                    ChoiceCandidate(choice_name_en="sunny", keybind=KeybindCandidate(code="Digit2")),
                    ChoiceCandidate(choice_name_en="rainy", keybind=KeybindCandidate(code="Digit2")),
                ],
            )
        ]
    )

    actual = normalize_parsed_attributes(result, annotation_specs)

    assert actual.attributes[0].choices is not None
    assert actual.attributes[0].choices[0].keybind is not None
    assert actual.attributes[0].choices[1].keybind is None
    assert len(actual.warnings) == 1


def test_to_annofab_attributes():
    result = AttributeParseResult(
        attributes=[
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.FLAG,
                attribute_name_en="truncated",
                label_name_ens=["pedestrian"],
                keybind=KeybindCandidate(code="Digit1", ctrl=True),
            ),
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.SELECT,
                attribute_name_en="weather",
                attribute_name_ja="天気",
                label_name_ens=["car"],
                read_only=True,
                choices=[
                    ChoiceCandidate(choice_name_en="sunny", choice_name_ja="晴れ", is_default=True, keybind=KeybindCandidate(code="KeyQ")),
                    ChoiceCandidate(choice_name_en="rainy", choice_name_ja="雨", keybind=KeybindCandidate(code="KeyW")),
                ],
            ),
        ]
    )

    actual = to_annofab_attributes(result)

    assert actual == [
        {
            "attribute_type": "flag",
            "attribute_name_en": "truncated",
            "label_name_ens": ["pedestrian"],
            "read_only": False,
            "keybind": {
                "alt": False,
                "code": "Digit1",
                "ctrl": True,
                "shift": False,
            },
        },
        {
            "attribute_type": "select",
            "attribute_name_en": "weather",
            "attribute_name_ja": "天気",
            "label_name_ens": ["car"],
            "read_only": True,
            "choices": [
                {
                    "choice_name_en": "sunny",
                    "choice_name_ja": "晴れ",
                    "is_default": True,
                    "keybind": {
                        "alt": False,
                        "code": "KeyQ",
                        "ctrl": False,
                        "shift": False,
                    },
                },
                {
                    "choice_name_en": "rainy",
                    "choice_name_ja": "雨",
                    "is_default": False,
                    "keybind": {
                        "alt": False,
                        "code": "KeyW",
                        "ctrl": False,
                        "shift": False,
                    },
                },
            ],
        },
    ]


def test_get_annotation_specs_from_file(tmp_path, annotation_specs):
    json_file = tmp_path / "annotation_specs.json"
    json_file.write_text(json.dumps(annotation_specs), encoding="utf-8")

    actual = get_annotation_specs(
        annotation_specs_json_file=json_file,
        project_id=None,
        annofab_pat=None,
    )

    assert actual == annotation_specs


def test_get_annotation_specs_from_project_id(monkeypatch, annotation_specs):
    called = {}

    def fake_build(*, pat):
        called["pat"] = pat
        return SimpleNamespace(api=SimpleNamespace(get_annotation_specs=lambda project_id, query_params: (annotation_specs, {"project_id": project_id, "query_params": query_params})))

    monkeypatch.setattr("acl.command.generate_add_attributes_json.annofabapi.build", fake_build)

    actual = get_annotation_specs(
        annotation_specs_json_file=None,
        project_id="prj1",
        annofab_pat="pat1",
    )

    assert actual == annotation_specs
    assert called["pat"] == "pat1"
