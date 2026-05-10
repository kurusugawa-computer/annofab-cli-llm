import json
from types import SimpleNamespace

import pytest
from annofabapi.util.attribute_restrictions import RestrictionAst, RestrictionAstType

from acl.command.parse_attribute_restriction import (
    RestrictionAstParseResult,
    get_annotation_specs,
    parse_restrictions_from_text,
    to_annofab_restrictions,
    to_human_readable_text,
)


@pytest.fixture
def annotation_specs() -> dict:
    return {
        "labels": [
            {
                "label_id": "label_car",
                "label_name": {"messages": [{"lang": "en-US", "message": "car"}]},
                "additional_data_definitions": ["attr_occluded", "attr_note", "attr_vehicle_type"],
            },
        ],
        "additionals": [
            {
                "additional_data_definition_id": "attr_occluded",
                "name": {"messages": [{"lang": "en-US", "message": "occluded"}]},
                "type": "flag",
            },
            {
                "additional_data_definition_id": "attr_note",
                "name": {"messages": [{"lang": "en-US", "message": "note"}]},
                "type": "text",
            },
            {
                "additional_data_definition_id": "attr_vehicle_type",
                "name": {"messages": [{"lang": "en-US", "message": "vehicle_type"}]},
                "type": "select",
                "choices": [
                    {
                        "choice_id": "choice_general_car",
                        "name": {"messages": [{"lang": "en-US", "message": "general_car"}]},
                    },
                    {
                        "choice_id": "choice_bike",
                        "name": {"messages": [{"lang": "en-US", "message": "bike"}]},
                    },
                ],
            },
        ],
    }


def test_parse_restrictions_from_text(monkeypatch, annotation_specs):
    result = RestrictionAstParseResult(
        asts=[
            RestrictionAst(
                type=RestrictionAstType.IMPLY,
                premise=RestrictionAst(type=RestrictionAstType.CHECKED, attribute_name="occluded"),
                conclusion=RestrictionAst(type=RestrictionAstType.IS_NOT_EMPTY, attribute_name="note"),
            ),
            RestrictionAst(type=RestrictionAstType.HAS_CHOICE, attribute_name="vehicle_type", choice_name="general_car"),
        ],
        warnings=["文末の補足は制約として解釈しませんでした。"],
        unresolved_texts=["このルールは推奨です。"],
    )
    actual_messages = []

    def fake_completion(**kwargs):
        assert kwargs["response_format"] is RestrictionAstParseResult
        actual_messages.extend(kwargs["messages"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=result.model_dump_json()))],
            usage=SimpleNamespace(total_tokens=10, prompt_tokens=7, completion_tokens=3),
        )

    monkeypatch.setattr("acl.command.parse_attribute_restriction.completion", fake_completion)

    actual = parse_restrictions_from_text(
        text="occludedならnoteを必須にしてください。",
        annotation_specs=annotation_specs,
        llm_model="openai/gpt-5.4-nano",
    )

    assert actual == result
    user_content = actual_messages[1]["content"]
    assert "## 属性制約カタログ" in user_content
    assert "\"allowed_ast_types\"" in user_content
    assert "\"attribute_name\": \"vehicle_type\"" in user_content


def test_to_human_readable_text():
    result = RestrictionAstParseResult(
        asts=[
            RestrictionAst(
                type=RestrictionAstType.IMPLY,
                premise=RestrictionAst(type=RestrictionAstType.CHECKED, attribute_name="occluded"),
                conclusion=RestrictionAst(type=RestrictionAstType.IS_NOT_EMPTY, attribute_name="note"),
            )
        ],
        warnings=["warning1"],
        unresolved_texts=["text1"],
    )

    actual = to_human_readable_text(result)

    assert "[restrictions]" in actual
    assert "If 'occluded' is checked, 'note' is not empty." in actual
    assert "[warnings]" in actual
    assert "warning1" in actual
    assert "[unresolved_texts]" in actual
    assert "text1" in actual


def test_to_annofab_restrictions(annotation_specs):
    result = RestrictionAstParseResult(
        asts=[
            RestrictionAst(
                type=RestrictionAstType.IMPLY,
                premise=RestrictionAst(type=RestrictionAstType.CHECKED, attribute_name="occluded"),
                conclusion=RestrictionAst(type=RestrictionAstType.IS_NOT_EMPTY, attribute_name="note"),
            ),
        ]
    )

    actual = to_annofab_restrictions(result, annotation_specs)

    assert actual == [
        {
            "additional_data_definition_id": "attr_note",
            "condition": {
                "_type": "Imply",
                "premise": {
                    "additional_data_definition_id": "attr_occluded",
                    "condition": {"_type": "Equals", "value": "true"},
                },
                "condition": {"_type": "NotEquals", "value": ""},
            },
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
        return SimpleNamespace(
            api=SimpleNamespace(
                get_annotation_specs=lambda project_id, query_params: (annotation_specs, {"project_id": project_id, "query_params": query_params})
            )
        )

    monkeypatch.setattr("acl.command.parse_attribute_restriction.annofabapi.build", fake_build)

    actual = get_annotation_specs(
        annotation_specs_json_file=None,
        project_id="prj1",
        annofab_pat="pat1",
    )

    assert actual == annotation_specs
    assert called["pat"] == "pat1"
