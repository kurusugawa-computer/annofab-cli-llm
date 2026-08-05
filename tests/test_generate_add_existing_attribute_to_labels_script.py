from types import SimpleNamespace

from acl.command.generate_add_existing_attribute_to_labels_script import (
    ExistingAttributeCatalogItem,
    ExistingAttributeLabelAssignment,
    ExistingAttributeLabelAssignmentParseResult,
    generate_bash_script,
    normalize_assignments,
    parse_existing_attribute_label_assignments_from_text,
)


def test_parse_existing_attribute_label_assignments_from_text(monkeypatch):
    result = ExistingAttributeLabelAssignmentParseResult(
        assignments=[ExistingAttributeLabelAssignment(attribute_id="attr_occluded", label_name_ens=["pedestrian"])],
    )
    messages: list[dict[str, str]] = []

    def fake_completion(**kwargs):
        messages.extend(kwargs["messages"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=result.model_dump_json()))],
            usage=SimpleNamespace(total_tokens=12, prompt_tokens=8, completion_tokens=4),
        )

    monkeypatch.setattr("acl.command.generate_add_existing_attribute_to_labels_script.completion", fake_completion)
    attributes = [ExistingAttributeCatalogItem(attribute_id="attr_occluded", attribute_name_en="occluded", attribute_name_ja="隠れ")]

    actual = parse_existing_attribute_label_assignments_from_text(
        text="既存の隠れ属性を歩行者ラベルにも追加してください。",
        existing_attributes=attributes,
        llm_model="openai/gpt-5.6-terra",
    )

    assert actual == result
    assert "既存属性を既存または新規のラベルへ紐付ける指示だけを assignments に入れてください。" in messages[0]["content"]
    assert '"attribute_id": "attr_occluded"' in messages[1]["content"]


def test_normalize_assignments_merges_labels_and_removes_unknown_attributes():
    attributes = [ExistingAttributeCatalogItem(attribute_id="attr_occluded", attribute_name_en="occluded", attribute_name_ja="隠れ")]
    result = ExistingAttributeLabelAssignmentParseResult(
        assignments=[
            ExistingAttributeLabelAssignment(attribute_id="attr_occluded", label_name_ens=["car"]),
            ExistingAttributeLabelAssignment(attribute_id="attr_occluded", label_name_ens=["pedestrian", "car"]),
            ExistingAttributeLabelAssignment(attribute_id="unknown", label_name_ens=["car"]),
        ]
    )

    actual = normalize_assignments(result, attributes)

    assert actual.assignments == [ExistingAttributeLabelAssignment(attribute_id="attr_occluded", label_name_ens=["car", "pedestrian"])]
    assert len(actual.warnings) == 1


def test_generate_bash_script_quotes_values():
    assignments = [ExistingAttributeLabelAssignment(attribute_id="attr occluded", label_name_ens=["car", "person's head"])]

    actual = generate_bash_script(project_id="prj 1", assignments=assignments)

    assert actual == "annofabcli annotation_specs add_existing_attribute_to_labels --project_id 'prj 1' --attribute_id 'attr occluded' --label_name_en car 'person'\"'\"'s head'\n"
