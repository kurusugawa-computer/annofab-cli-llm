import pytest

from acl.command import validate_attribute_value
from acl.command.validate_attribute_value import split_by_json_length, validate_annotation_attribute_with_llm, write_annotation_attribute_json


def test_split_by_json_length():
    # 1要素ごとに長さが大きく異なるリスト
    attribute_list = [
        {"status": "a" * 10},  # 10文字
        {"status": "b" * 1000},  # 1000文字
        {"status": "c" * 500},  # 500文字
        {"status": "d" * 2000},  # 2000文字
    ]
    # max_chunk_lengthを1100にすると、[0,1]で1チャンク、[2]で1チャンク、[3]で1チャンクになるはず
    chunks = split_by_json_length(attribute_list, max_chunk_length=1100)
    # 期待: 3チャンク
    assert len(chunks) == 3
    # 1チャンク目: index 0,1
    assert chunks[0][1] == [0, 1]
    # 2チャンク目: index 2
    assert chunks[1][1] == [2]
    # 3チャンク目: index 3
    assert chunks[2][1] == [3]
    # 各チャンクの内容も確認
    assert chunks[0][0][0]["status"] == "a" * 10
    assert chunks[0][0][1]["status"] == "b" * 1000
    assert chunks[1][0][0]["status"] == "c" * 500
    assert chunks[2][0][0]["status"] == "d" * 2000


def test_write_annotation_attribute_json_masks_annofab_pat(monkeypatch, tmp_path):
    captured_commands = []
    captured_logs = []

    def mock_run(cmd, check):  # noqa: ANN001, ANN202
        captured_commands.append(cmd)
        assert check

    def mock_info(message):  # noqa: ANN001, ANN202
        captured_logs.append(message)

    monkeypatch.setattr(validate_attribute_value.subprocess, "run", mock_run)
    monkeypatch.setattr(validate_attribute_value.logger, "info", mock_info)

    write_annotation_attribute_json("prj", tmp_path / "attribute.json", annotation_path=None, temp_dir=None, annofab_pat="pat1")

    assert captured_commands == [
        [
            "annofabcli",
            "statistics",
            "list_annotation_attribute",
            "--format",
            "json",
            "--output",
            str(tmp_path / "attribute.json"),
            "--project_id",
            "prj",
            "--annofab_pat",
            "pat1",
        ]
    ]
    assert len(captured_logs) == 1
    assert "pat1" not in captured_logs[0]
    assert "'--annofab_pat', '***'" in captured_logs[0]


@pytest.mark.access_webapi
def test_validate_annotation_attribute_with_llm():
    attribute_list = [
        {"status": "自動車が走っています。"},
        {"status": "歩高者が歩いています。"},
    ]
    validation_prompt = "属性`status`の値に、明らかな誤字脱字がないかをチェックしてください。意味の言い換え、表現の揺れ、語尾の違い、文法的な改善提案、句点忘れなどは対象にしないでください。"
    attribute_description = "`status`は画像に映っている状態を表します。"

    actual = validate_annotation_attribute_with_llm(attribute_list, validation_prompt, llm_model="openai/gpt-5.4-nano", attribute_description=attribute_description, annotation_overview=None)
    assert len(actual.results) == 1
    elm = actual.results[0]
    assert elm.index == 1
    assert elm.attribute_name == "status"
    assert elm.suggested_attribute_value == "歩行者が歩いています。"
