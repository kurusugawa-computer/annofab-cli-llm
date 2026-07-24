import json
from types import SimpleNamespace

from acl.command import validate_annotation_specs
from acl.command.validate_annotation_specs import (
    DEFAULT_REVIEW_POINT,
    AnnotationSpecsReviewResult,
    AttributeRestrictionSpec,
    AttributeSpec,
    LabelSpec,
    get_review_point,
    get_specs_json_schema,
    parse_specs,
    review_annotation_specs_with_llm,
    run_annofabcli_annotation_specs_list,
)


def test_get_review_point_uses_default():
    assert get_review_point(None) == DEFAULT_REVIEW_POINT


def test_get_review_point_reads_file(tmp_path):
    review_point_file = tmp_path / "review_points.md"
    review_point_file.write_text("属性制約だけレビューしてください。", encoding="utf-8")

    actual = get_review_point([f"@{review_point_file}"])

    assert actual == "属性制約だけレビューしてください。"


def test_get_review_point_joins_multiple_values(tmp_path):
    review_point_file = tmp_path / "review_points.md"
    review_point_file.write_text("属性制約をレビューしてください。", encoding="utf-8")

    actual = get_review_point(["名前をレビューしてください。", f"@{review_point_file}"])

    assert actual == "名前をレビューしてください。\n\n属性制約をレビューしてください。"


def test_run_annofabcli_annotation_specs_list(monkeypatch):
    def mock_run(command, check, capture_output, text):  # noqa: ANN001, ANN202
        assert command == [
            "annofabcli",
            "annotation_specs",
            "list_label",
            "--project_id",
            "prj",
            "--format",
            "json",
        ]
        assert check
        assert capture_output
        assert text
        return SimpleNamespace(stdout=json.dumps([{"label_name_en": "car"}]))

    monkeypatch.setattr(validate_annotation_specs.subprocess, "run", mock_run)

    actual = run_annofabcli_annotation_specs_list(project_id="prj", subcommand_name="list_label")

    assert actual == [{"label_name_en": "car"}]


def test_parse_specs_keeps_unknown_fields():
    actual = parse_specs(
        [
            {
                "label_name_en": "car",
                "label_name_ja": "車",
                "annotation_type": "bounding_box",
                "unknown_field": "kept",
            }
        ],
        LabelSpec,
    )

    assert actual[0].label_name_en == "car"
    assert actual[0].model_dump(mode="json")["unknown_field"] == "kept"


def test_get_specs_json_schema_has_descriptions():
    actual = get_specs_json_schema()

    assert actual["labels"]["properties"]["label_name_en"]["description"] == "既存ラベル名（英語）です。"
    assert actual["attributes"]["properties"]["attribute_name_en"]["description"] == "既存属性名（英語）です。"
    assert actual["attribute_restrictions"]["properties"]["attribute_name_en"]["description"] == "属性制約の対象属性名（英語）です。"


def test_review_annotation_specs_with_llm_for_markdown(monkeypatch):
    captured_messages = []

    def mock_completion(model, messages):  # noqa: ANN001, ANN202
        assert model == "openai/test"
        captured_messages.extend(messages)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="問題ありません。"))],
            usage=SimpleNamespace(total_tokens=10, prompt_tokens=8, completion_tokens=2),
        )

    monkeypatch.setattr(validate_annotation_specs, "call_llm_completion", mock_completion)

    actual = review_annotation_specs_with_llm(
        annotation_rule="車を囲ってください。",
        review_point="名前をレビューしてください。",
        labels=[LabelSpec(label_name_en="car", label_name_ja="車")],
        attributes=[],
        attribute_restrictions=[],
        llm_model="openai/test",
        output_format="markdown",
    )

    assert actual == "問題ありません。"
    user_content = captured_messages[1]["content"]
    assert "車を囲ってください。" in user_content
    assert "名前をレビューしてください。" in user_content
    assert "アノテーション仕様JSON Schema" in user_content
    assert "既存ラベル名（英語）です。" in user_content
    assert '"label_name_en": "car"' in user_content


def test_review_annotation_specs_with_llm_for_json(monkeypatch):
    def mock_completion(model, messages, response_format):  # noqa: ANN001, ANN202
        assert model == "openai/test"
        assert response_format == AnnotationSpecsReviewResult
        assert "属性制約一覧" in messages[1]["content"]
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "summary": "1件の指摘があります。",
                                "findings": [
                                    {
                                        "severity": "warning",
                                        "category": "attribute_restriction",
                                        "target_type": "attribute",
                                        "target_name": "truncated",
                                        "message": "見切れ属性の制約が不足しています。",
                                        "recommendation": "車ラベルに制約を追加してください。",
                                    }
                                ],
                            }
                        )
                    )
                )
            ],
            usage=SimpleNamespace(total_tokens=10, prompt_tokens=8, completion_tokens=2),
        )

    monkeypatch.setattr(validate_annotation_specs, "call_llm_completion", mock_completion)

    actual = review_annotation_specs_with_llm(
        annotation_rule="車を囲ってください。",
        review_point="属性制約をレビューしてください。",
        labels=[],
        attributes=[AttributeSpec(attribute_name_en="truncated", attribute_name_ja="見切れ")],
        attribute_restrictions=[AttributeRestrictionSpec(attribute_name_en="truncated")],
        llm_model="openai/test",
        output_format="json",
    )

    assert isinstance(actual, AnnotationSpecsReviewResult)
    assert actual.summary == "1件の指摘があります。"
    assert actual.findings[0].severity == "warning"
