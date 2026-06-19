import json
from types import SimpleNamespace

import pytest
from annofabapi.models import AdditionalDataDefinitionType

from acl.command.parse_attribute import (
    AttributeCandidate,
    AttributeParseResult,
    ChoiceCandidate,
    get_annotation_specs,
    normalize_parsed_attributes,
    parse_attributes_from_text,
    to_annofab_attributes,
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
                "choices": [
                    {
                        "choice_id": "choice_general_car",
                        "name": {
                            "messages": [
                                {"lang": "en-US", "message": "general_car"},
                                {"lang": "ja-JP", "message": "乗用車"},
                            ]
                        },
                    },
                    {
                        "choice_id": "choice_truck",
                        "name": {
                            "messages": [
                                {"lang": "en-US", "message": "truck"},
                                {"lang": "ja-JP", "message": "トラック"},
                            ]
                        },
                    },
                ],
            },
        ],
    }


def test_parse_attributes_from_text(monkeypatch, annotation_specs):
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
        unresolved_texts=["注記の扱いが不明でした。"],
    )
    actual_messages = []

    def fake_completion(**kwargs):
        assert kwargs["response_format"] is AttributeParseResult
        actual_messages.extend(kwargs["messages"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=result.model_dump_json()))],
            usage=SimpleNamespace(total_tokens=14, prompt_tokens=10, completion_tokens=4),
        )

    monkeypatch.setattr("acl.command.parse_attribute.completion", fake_completion)

    actual = parse_attributes_from_text(
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
    assert '"attribute_name_en": "occluded"' in user_content
    assert '"choice_name_ens": [' in user_content
    assert "attribute_name_en と label_name_ens に含める label_name_en は、アノテーションJSONに出力される値なので、英語小文字のスネークケースで出力してください。" in developer_content
    assert "`choice` または `select` の choices に含める choice_name_en も、アノテーションJSONに出力される値なので、英語小文字のスネークケースで出力してください。" in developer_content
    assert "読み込み専用の属性にする指定がある場合は read_only を true にしてください。" in developer_content
    assert "`choice` または `select` の場合は、choices を2件以上出力してください。" in developer_content


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


def test_to_annofab_attributes():
    result = AttributeParseResult(
        attributes=[
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.FLAG,
                attribute_name_en="truncated",
                label_name_ens=["pedestrian"],
            ),
            AttributeCandidate(
                attribute_type=AdditionalDataDefinitionType.SELECT,
                attribute_name_en="weather",
                attribute_name_ja="天気",
                label_name_ens=["car"],
                read_only=True,
                choices=[
                    ChoiceCandidate(choice_name_en="sunny", choice_name_ja="晴れ", is_default=True),
                    ChoiceCandidate(choice_name_en="rainy", choice_name_ja="雨"),
                ],
            )
        ]
    )

    actual = to_annofab_attributes(result)

    assert actual == [
        {
            "attribute_type": "flag",
            "attribute_name_en": "truncated",
            "label_name_ens": ["pedestrian"],
            "read_only": False,
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
                },
                {
                    "choice_name_en": "rainy",
                    "choice_name_ja": "雨",
                    "is_default": False,
                },
            ],
        }
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

    monkeypatch.setattr("acl.command.parse_attribute.annofabapi.build", fake_build)

    actual = get_annotation_specs(
        annotation_specs_json_file=None,
        project_id="prj1",
        annofab_pat="pat1",
    )

    assert actual == annotation_specs
    assert called["pat"] == "pat1"
