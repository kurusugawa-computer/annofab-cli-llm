import json
from types import SimpleNamespace
from typing import Any

from acl.command import validate_annotation_specs
from acl.command.validate_annotation_specs import (
    DEFAULT_REVIEW_POINT,
    AttributeSpec,
    LabelSpec,
    add_parser,
    get_review_point,
    get_specs_json_schema,
    parse_specs,
    review_annotation_specs_with_llm,
    run_annofabcli_annotation_specs_list,
    run_annofabcli_annotation_specs_text,
)
from acl.common.command import mask_command_options


def test_get_review_point_uses_default():
    assert get_review_point(None) == DEFAULT_REVIEW_POINT


def test_get_review_point_reads_file(tmp_path):
    review_point_file = tmp_path / "review_points.md"
    review_point_file.write_text("属性制約だけレビューしてください。", encoding="utf-8")

    actual = get_review_point(f"@{review_point_file}")

    assert DEFAULT_REVIEW_POINT in actual
    assert "## 追加レビュー観点" in actual
    assert "属性制約だけレビューしてください。" in actual


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

    actual = run_annofabcli_annotation_specs_list(project_id="prj", subcommand_name="list_label", annofab_pat=None)

    assert actual == [{"label_name_en": "car"}]


def test_run_annofabcli_annotation_specs_list_with_annofab_pat(monkeypatch):
    def mock_run(command, check, capture_output, text):  # noqa: ANN001, ANN202
        assert command == [
            "annofabcli",
            "annotation_specs",
            "list_attribute",
            "--project_id",
            "prj",
            "--format",
            "json",
            "--annofab_pat",
            "pat1",
        ]
        assert check
        assert capture_output
        assert text
        return SimpleNamespace(stdout=json.dumps([{"attribute_name_en": "truncated"}]))

    monkeypatch.setattr(validate_annotation_specs.subprocess, "run", mock_run)

    actual = run_annofabcli_annotation_specs_list(project_id="prj", subcommand_name="list_attribute", annofab_pat="pat1")

    assert actual == [{"attribute_name_en": "truncated"}]


def test_run_annofabcli_annotation_specs_text(monkeypatch):
    def mock_run(command, check, capture_output, text):  # noqa: ANN001, ANN202
        assert command == [
            "annofabcli",
            "annotation_specs",
            "list_attribute_restriction",
            "--project_id",
            "prj",
            "--format",
            "text_with_ids",
        ]
        assert check
        assert capture_output
        assert text
        return SimpleNamespace(stdout="[restriction_id: r1] car.truncated is required")

    monkeypatch.setattr(validate_annotation_specs.subprocess, "run", mock_run)

    actual = run_annofabcli_annotation_specs_text(project_id="prj", subcommand_name="list_attribute_restriction", output_format="text_with_ids", annofab_pat=None)

    assert actual == "[restriction_id: r1] car.truncated is required"


def test_run_annofabcli_annotation_specs_text_with_annofab_pat(monkeypatch):
    def mock_run(command, check, capture_output, text):  # noqa: ANN001, ANN202
        assert command == [
            "annofabcli",
            "annotation_specs",
            "list_attribute_restriction",
            "--project_id",
            "prj",
            "--format",
            "text_with_ids",
            "--annofab_pat",
            "pat1",
        ]
        assert check
        assert capture_output
        assert text
        return SimpleNamespace(stdout="[restriction_id: r1] car.truncated is required")

    monkeypatch.setattr(validate_annotation_specs.subprocess, "run", mock_run)

    actual = run_annofabcli_annotation_specs_text(project_id="prj", subcommand_name="list_attribute_restriction", output_format="text_with_ids", annofab_pat="pat1")

    assert actual == "[restriction_id: r1] car.truncated is required"


def test_mask_command_options():
    command = ["annofabcli", "annotation_specs", "list_label", "--annofab_pat", "pat1"]

    actual = mask_command_options(command)

    assert actual == ["annofabcli", "annotation_specs", "list_label", "--annofab_pat", "***"]
    assert command == ["annofabcli", "annotation_specs", "list_label", "--annofab_pat", "pat1"]


def test_parse_specs_ignores_unknown_fields():
    actual = parse_specs(
        [
            {
                "label_id": "label-1",
                "label_name_en": "car",
                "label_name_ja": "車",
                "annotation_type": "bounding_box",
                "unknown_field": "kept",
            }
        ],
        LabelSpec,
    )

    assert actual[0].label_name_en == "car"
    assert actual[0].label_id == "label-1"
    assert "unknown_field" not in actual[0].model_dump(mode="json")


def test_get_specs_json_schema_has_descriptions():
    actual: dict[str, Any] = get_specs_json_schema()

    assert actual["labels"]["properties"]["label_name_en"]["description"] == "既存ラベル名（英語）です。"
    assert actual["attributes"]["properties"]["attribute_name_en"]["description"] == "既存属性名（英語）です。"
    assert actual["attributes"]["properties"]["default"]["description"] == "属性の初期値です。"
    assert actual["labels"]["properties"]["label_id"]["description"] == "既存ラベルのIDです。レビュー指摘で対象ラベルを特定するために使用します。"
    assert actual["attributes"]["properties"]["attribute_id"]["description"] == "既存属性のIDです。レビュー指摘で対象属性を特定するために使用します。"
    assert actual["attributes"]["properties"]["label_ids"]["description"] == "この属性が付与されるラベルIDの一覧です。"
    assert actual["attributes"]["$defs"]["ChoiceSpec"]["properties"]["choice_id"]["description"] == "既存選択肢のIDです。レビュー指摘で対象選択肢を特定するために使用します。"
    assert "default_value" not in actual["attributes"]["properties"]
    assert "attribute_restrictions" not in actual


def test_add_parser_does_not_have_output_format():
    parser = add_parser()

    option_strings = {option_string for action in parser._actions for option_string in action.option_strings}

    assert "--output_format" not in option_strings


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
        labels=[LabelSpec(label_id="label-1", label_name_en="car", label_name_ja="車", annotation_type="bounding_box")],
        attributes=[],
        attribute_restrictions_text="",
        llm_model="openai/test",
    )

    assert actual == "問題ありません。"
    user_content = captured_messages[1]["content"]
    assert "車を囲ってください。" in user_content
    assert "名前をレビューしてください。" in user_content
    assert "アノテーション仕様JSON Schema" in user_content
    assert "既存ラベル名（英語）です。" in user_content
    assert '"label_name_en": "car"' in user_content
    assert "利用可能な annotation_type と説明" in user_content
    assert '"value": "bounding_box"' in user_content
    assert '"description": "矩形"' in user_content
    assert "利用可能な attribute_type と説明" in user_content
    assert '"value": "flag"' in user_content
    assert '"description": "チェックボックス"' in user_content


def test_review_annotation_specs_with_llm_includes_attribute_default(monkeypatch):
    captured_messages = []

    def mock_completion(model, messages):  # noqa: ANN001, ANN202
        assert model == "openai/test"
        captured_messages.extend(messages)
        assert "属性制約一覧" in messages[1]["content"]
        assert "text_with_ids" in messages[1]["content"]
        assert "restriction_id: r1" in messages[1]["content"]
        assert '"value": "segmentation_v2"' in messages[1]["content"]
        assert '"description": "塗りつぶしv2（セマンティックセグメンテーション用）"' in messages[1]["content"]
        assert '"value": "choice"' in messages[1]["content"]
        assert '"description": "ラジオボタン（排他選択）"' in messages[1]["content"]
        assert '"default": false' in messages[1]["content"]
        assert '"label_ids": [' in messages[1]["content"]
        assert '"label-1"' in messages[1]["content"]
        assert "default_value" not in messages[1]["content"]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="見切れ属性の制約が不足しています。"))],
            usage=SimpleNamespace(total_tokens=10, prompt_tokens=8, completion_tokens=2),
        )

    monkeypatch.setattr(validate_annotation_specs, "call_llm_completion", mock_completion)

    actual = review_annotation_specs_with_llm(
        annotation_rule="車を囲ってください。",
        review_point="属性制約をレビューしてください。",
        labels=[],
        attributes=[
            AttributeSpec(
                attribute_id="attribute-1",
                attribute_type="flag",
                attribute_name_en="truncated",
                attribute_name_ja="見切れ",
                label_ids=["label-1"],
                label_name_ens=["car"],
                read_only=True,
                default=False,
            )
        ],
        attribute_restrictions_text="[restriction_id: r1] car.truncated is required",
        llm_model="openai/test",
    )

    assert actual == "見切れ属性の制約が不足しています。"
    assert captured_messages


def test_review_annotation_specs_with_llm_without_annotation_rule(monkeypatch):
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
        annotation_rule=None,
        review_point="名前をレビューしてください。",
        labels=[LabelSpec(label_id="label-1", label_name_en="car", label_name_ja="車", annotation_type="bounding_box")],
        attributes=[],
        attribute_restrictions_text="",
        llm_model="openai/test",
    )

    assert actual == "問題ありません。"
    developer_content = captured_messages[0]["content"]
    user_content = captured_messages[1]["content"]
    assert "アノテーションルールが指定されていない場合" in developer_content
    assert "指定されていません" in user_content
    assert "アノテーション仕様単体で判断できる範囲だけレビューしてください。" in user_content
