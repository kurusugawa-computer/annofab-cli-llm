from types import SimpleNamespace

from acl.command.generate_add_labels_json import UnresolvedText
from acl.command.generate_delete_attribute_restriction_json import (
    DeleteRestrictionParseResult,
    ExistingRestriction,
    get_existing_restrictions,
    parse_delete_restrictions_from_text,
    resolve_selected_restrictions,
    to_human_readable_text,
)


def test_get_existing_restrictions():
    annotation_specs = {
        "labels": [],
        "additionals": [
            {
                "additional_data_definition_id": "attr_occluded",
                "name": {"messages": [{"lang": "en-US", "message": "occluded"}]},
                "type": "flag",
            },
        ],
        "restrictions": [
            {
                "additional_data_definition_id": "attr_occluded",
                "condition": {"_type": "Equals", "value": "true"},
            }
        ],
    }

    existing_restrictions, restrictions = get_existing_restrictions(annotation_specs)

    assert existing_restrictions == [ExistingRestriction(index=1, restriction_text="'occluded' EQUALS 'true'")]
    assert restrictions == annotation_specs["restrictions"]


def test_parse_delete_restrictions_from_text(monkeypatch):
    result = DeleteRestrictionParseResult(
        selected_indexes=[2],
        unresolved_texts=[
            UnresolvedText(
                text="もう一つの制約も消してください。",
                reason="削除対象を特定できませんでした。",
                required_information=["restriction"],
            )
        ],
    )
    actual_messages = []

    def fake_completion(**kwargs):
        assert kwargs["response_format"] is DeleteRestrictionParseResult
        actual_messages.extend(kwargs["messages"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=result.model_dump_json()))],
            usage=SimpleNamespace(total_tokens=10, prompt_tokens=7, completion_tokens=3),
        )

    monkeypatch.setattr("acl.command.generate_delete_attribute_restriction_json.completion", fake_completion)

    actual = parse_delete_restrictions_from_text(
        text="天候を必須にする制約を削除してください。",
        existing_restrictions=[
            ExistingRestriction(index=1, restriction_text="'occluded' is checked"),
            ExistingRestriction(index=2, restriction_text="'weather' is not empty"),
        ],
        llm_model="openai/gpt-5.4-nano",
    )

    assert actual == result
    assert '"index": 2' in actual_messages[1]["content"]
    assert "既存属性制約一覧に含まれる番号だけを入れてください" in actual_messages[0]["content"]


def test_resolve_selected_restrictions_excludes_unknown_and_duplicate_indexes():
    result = DeleteRestrictionParseResult(selected_indexes=[2, 3, 2], warnings=["LLMからの注意事項"])
    restrictions = [
        {"additional_data_definition_id": "attr_a", "condition": {"_type": "Equals", "value": "true"}},
        {"additional_data_definition_id": "attr_b", "condition": {"_type": "NotEquals", "value": ""}},
    ]

    actual = resolve_selected_restrictions(
        result,
        existing_restrictions=[
            ExistingRestriction(index=1, restriction_text="'a' is checked"),
            ExistingRestriction(index=2, restriction_text="'b' is not empty"),
        ],
        restrictions=restrictions,
    )

    assert actual.restrictions == [restrictions[1]]
    assert actual.restriction_texts == ["'b' is not empty"]
    assert actual.warnings == [
        "LLMからの注意事項",
        "属性制約番号'3'は既存属性制約一覧に存在しないため、出力から除外しました。",
        "属性制約番号'2'が重複していたため、先頭の1件だけを採用しました。",
    ]


def test_to_human_readable_text_includes_unresolved_texts():
    result = DeleteRestrictionParseResult(
        selected_indexes=[],
        unresolved_texts=[UnresolvedText(text="削除してください。", reason="対象を特定できませんでした。", required_information=["restriction"])],
    )
    resolved = resolve_selected_restrictions(result, existing_restrictions=[], restrictions=[])

    actual = to_human_readable_text(resolved, result)

    assert "[restrictions]\n(none)" in actual
    assert "[unresolved_texts]" in actual
    assert "削除してください。" in actual
