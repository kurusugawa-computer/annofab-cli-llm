import json
from types import SimpleNamespace

import pytest

from acl.command.parse_label import (
    AnnotationType,
    LabelCandidate,
    LabelParseResult,
    ProjectType,
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
    assert "#RRGGBB" in developer_content
    assert '"label_name_en": "car"' in user_content
    assert '"annotation_type": "bounding_box"' in user_content


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
            LabelCandidate(label_name_en="pedestrian", label_name_ja="歩行者", annotation_type=AnnotationType.BOUNDING_BOX, color="#FF0000"),
        ]
    )

    actual = to_annofab_labels(result)

    assert actual == [
        {
            "label_name_en": "pedestrian",
            "label_name_ja": "歩行者",
            "annotation_type": "bounding_box",
            "color": "#FF0000",
        }
    ]


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
