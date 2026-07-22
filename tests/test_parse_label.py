import json
from types import SimpleNamespace

import pytest

from acl.command.parse_label import (
    AnnotationType,
    FieldValues,
    KeybindCandidate,
    LabelCandidate,
    LabelParseResult,
    MinimumSize2dWithDefaultInsertPositionFieldValue,
    ProjectType,
    VertexCountMinMaxFieldValue,
    get_annotation_specs,
    normalize_parsed_labels,
    parse_labels_from_text,
    to_annofab_labels,
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
                "keybind": [
                    {
                        "alt": False,
                        "code": "Digit1",
                        "ctrl": True,
                        "shift": False,
                    }
                ],
                "additional_data_definitions": [],
            },
        ],
        "additionals": [],
    }


def test_parse_labels_from_text(monkeypatch, annotation_specs):
    result = LabelParseResult(
        labels=[
            LabelCandidate(label_name_en="pedestrian", label_name_ja="歩行者", annotation_type=AnnotationType.BOUNDING_BOX, color="#FF0000"),
            LabelCandidate(label_name_en="bicycle", annotation_type=AnnotationType.BOUNDING_BOX),
        ],
        warnings=["annotation_typeは文脈から補いました。"],
        unresolved_texts=["色の指定は解釈しませんでした。"],
    )
    actual_messages = []

    def fake_completion(**kwargs):
        assert kwargs["response_format"] is LabelParseResult
        actual_messages.extend(kwargs["messages"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=result.model_dump_json()))],
            usage=SimpleNamespace(total_tokens=12, prompt_tokens=8, completion_tokens=4),
        )

    monkeypatch.setattr("acl.command.parse_label.completion", fake_completion)

    actual = parse_labels_from_text(
        text="歩行者と自転車のラベルを追加してください。どちらも bounding_box です。",
        annotation_specs=annotation_specs,
        project_type=ProjectType.IMAGE,
        llm_model="openai/gpt-5.4-nano",
    )

    assert actual == result
    developer_content = actual_messages[0]["content"]
    user_content = actual_messages[1]["content"]
    assert "## 既存ラベル一覧" in user_content
    assert "## プロジェクト種別" in user_content
    assert "## 利用可能な annotation_type と説明" in user_content
    assert '"value": "segmentation_v2"' in user_content
    assert '"description": "矩形"' in user_content
    assert "keybind" in developer_content
    assert "field_values" in developer_content
    assert "minimum_size_2d_with_default_insert_position" in developer_content
    assert "vertex_count_min_max" in developer_content
    assert "属性定義、属性制約、作業手順、品質基準など、明らかにラベル定義ではない文は warnings や unresolved_texts に入れず無視してください。" in developer_content
    assert "ラベル定義として解釈できる可能性があるが、label_name_en または annotation_type を特定できない文は labels に入れず unresolved_texts に入れてください。" in developer_content
    assert '"label_name_en": "car"' in user_content
    assert '"annotation_type": "bounding_box"' in user_content
    assert '"keybind": [' in user_content
    assert '"code": "Digit1"' in user_content
    assert '"ctrl": true' in user_content


def test_normalize_parsed_labels(annotation_specs):
    result = LabelParseResult(
        labels=[
            LabelCandidate(label_name_en="pedestrian", annotation_type=AnnotationType.BOUNDING_BOX),
            LabelCandidate(label_name_en="car", annotation_type=AnnotationType.BOUNDING_BOX),
            LabelCandidate(label_name_en="pedestrian", annotation_type=AnnotationType.POLYGON),
        ]
    )

    actual = normalize_parsed_labels(result, annotation_specs, project_type=ProjectType.IMAGE)

    assert actual.labels == [LabelCandidate(label_name_en="pedestrian", annotation_type=AnnotationType.BOUNDING_BOX)]
    assert len(actual.warnings) == 2


def test_normalize_parsed_labels_for_invalid_project_type(annotation_specs):
    result = LabelParseResult(
        labels=[
            LabelCandidate(label_name_en="pedestrian", annotation_type=AnnotationType.RANGE),
        ]
    )

    actual = normalize_parsed_labels(result, annotation_specs, project_type=ProjectType.IMAGE)

    assert actual.labels == []
    assert len(actual.warnings) == 1


def test_to_annofab_labels():
    result = LabelParseResult(
        labels=[
            LabelCandidate(
                label_name_en="pedestrian",
                label_name_ja="歩行者",
                annotation_type=AnnotationType.BOUNDING_BOX,
                color="#FF0000",
                keybind=KeybindCandidate(code="Digit1", ctrl=True),
            ),
        ]
    )

    actual = to_annofab_labels(result)

    assert actual == [
        {
            "label_name_en": "pedestrian",
            "label_name_ja": "歩行者",
            "annotation_type": "bounding_box",
            "color": "#FF0000",
            "keybind": {
                "alt": False,
                "code": "Digit1",
                "ctrl": True,
                "shift": False,
            },
            "field_values": {},
        }
    ]


def test_to_annofab_labels_with_minimum_size_field_value():
    result = LabelParseResult(
        labels=[
            LabelCandidate(
                label_name_en="pedestrian",
                annotation_type=AnnotationType.BOUNDING_BOX,
                field_values=FieldValues(
                    minimum_size_2d_with_default_insert_position=MinimumSize2dWithDefaultInsertPositionFieldValue(
                        min_warn_rule="and",
                        min_width=20,
                        min_height=20,
                        position_for_minimum_bounding_box_insertion=None,
                        _type="MinimumSize2dWithDefaultInsertPosition",
                    )
                ),
            ),
        ]
    )

    actual = to_annofab_labels(result)

    assert actual == [
        {
            "label_name_en": "pedestrian",
            "annotation_type": "bounding_box",
            "field_values": {
                "minimum_size_2d_with_default_insert_position": {
                    "min_warn_rule": "and",
                    "min_width": 20,
                    "min_height": 20,
                    "position_for_minimum_bounding_box_insertion": None,
                    "_type": "MinimumSize2dWithDefaultInsertPosition",
                }
            },
        }
    ]


def test_to_annofab_labels_with_vertex_count_min_max_field_value():
    result = LabelParseResult(
        labels=[
            LabelCandidate(
                label_name_en="traffic_lane",
                annotation_type=AnnotationType.POLYLINE,
                field_values=FieldValues(
                    vertex_count_min_max=VertexCountMinMaxFieldValue(
                        min=3,
                        max=6,
                        _type="VertexCountMinMax",
                    )
                ),
            ),
        ]
    )

    actual = to_annofab_labels(result)

    assert actual == [
        {
            "label_name_en": "traffic_lane",
            "annotation_type": "polyline",
            "field_values": {
                "vertex_count_min_max": {
                    "min": 3,
                    "max": 6,
                    "_type": "VertexCountMinMax",
                }
            },
        }
    ]


def test_label_candidate_rejects_unknown_field_value():
    with pytest.raises(ValueError):
        LabelCandidate.model_validate(
            {
                "label_name_en": "pedestrian",
                "annotation_type": AnnotationType.BOUNDING_BOX,
                "field_values": {
                    "future_field_value": {
                        "_type": "FutureFieldValue",
                        "enabled": True,
                        "nested": {"threshold": 0.5},
                    }
                },
            }
        )


def test_label_candidate_rejects_mismatched_field_value():
    with pytest.raises(ValueError):
        LabelCandidate.model_validate(
            {
                "label_name_en": "pedestrian",
                "annotation_type": AnnotationType.BOUNDING_BOX,
                "field_values": {
                    "minimum_size_2d_with_default_insert_position": {
                        "_type": "MarginOfErrorTolerance",
                    }
                },
            }
        )


def test_label_parse_result_schema_can_be_used_for_openai_structured_outputs():
    schema = LabelParseResult.model_json_schema()

    def collect_object_schemas_without_additional_properties_false(target, path="#"):
        if isinstance(target, dict):
            results = []
            if target.get("type") == "object" and target.get("additionalProperties") is not False:
                results.append(path)
            for key, value in target.items():
                results.extend(collect_object_schemas_without_additional_properties_false(value, f"{path}/{key}"))
            return results
        if isinstance(target, list):
            results = []
            for index, value in enumerate(target):
                results.extend(collect_object_schemas_without_additional_properties_false(value, f"{path}/{index}"))
            return results
        return []

    assert collect_object_schemas_without_additional_properties_false(schema) == []


def test_keybind_candidate():
    actual = KeybindCandidate(code=" Digit1 ")

    assert actual.code == "Digit1"
    assert actual.alt is False
    assert actual.ctrl is False
    assert actual.shift is False


def test_keybind_candidate_for_empty_code():
    with pytest.raises(ValueError):
        KeybindCandidate(code="")


def test_keybind_candidate_for_not_allowed_code():
    with pytest.raises(ValueError):
        KeybindCandidate(code="Escape")


def test_label_candidate_color():
    actual = LabelCandidate(label_name_en="pedestrian", annotation_type=AnnotationType.BOUNDING_BOX, color="#ff00aa")

    assert actual.color == "#FF00AA"


def test_get_annotation_specs_from_file(tmp_path, annotation_specs):
    json_file = tmp_path / "annotation_specs.json"
    json_file.write_text(json.dumps(annotation_specs), encoding="utf-8")

    actual = get_annotation_specs(
        annotation_specs_json_file=json_file,
        project_id=None,
        annofab_pat=None,
    )

    assert actual == annotation_specs


def test_get_annotation_specs_without_project_and_file():
    actual = get_annotation_specs(
        annotation_specs_json_file=None,
        project_id=None,
        annofab_pat=None,
    )

    assert actual == {"labels": [], "additionals": []}


def test_get_annotation_specs_from_project_id(monkeypatch, annotation_specs):
    called = {}

    def fake_build(*, pat):
        called["pat"] = pat
        return SimpleNamespace(api=SimpleNamespace(get_annotation_specs=lambda project_id, query_params: (annotation_specs, {"project_id": project_id, "query_params": query_params})))

    monkeypatch.setattr("acl.command.parse_label.annofabapi.build", fake_build)

    actual = get_annotation_specs(
        annotation_specs_json_file=None,
        project_id="prj1",
        annofab_pat="pat1",
    )

    assert actual == annotation_specs
    assert called["pat"] == "pat1"
