import argparse
import subprocess
from pathlib import Path

import pytest

from acl.command.generate_script import generate_readme, generate_script, main


def test_generate_script_includes_steps_in_dependency_order():
    actual = generate_script(project_id="prj1", annotation_rule_path=Path("annotation_rule.md"), model="openai/gpt-5.6-terra")

    assert actual.index("generate_add_labels_json") < actual.index("add_labels")
    assert actual.index("generate_update_labels_json") < actual.index("update_labels")
    assert actual.index("generate_add_attributes_json") < actual.index("add_attributes")
    assert actual.index("generate_add_existing_attribute_to_labels_script") < actual.index("add_existing_attribute_to_labels")
    assert actual.index("generate_update_attributes_json") < actual.index("update_attributes")
    assert actual.index("generate_add_choices_to_attributes_json") < actual.index("add_choices_to_attributes")
    assert actual.index("generate_add_attribute_restriction_json") < actual.index("add_attribute_restriction")
    assert actual.index("add_labels") < actual.index("generate_update_labels_json") < actual.index("generate_add_attributes_json")
    assert actual.index("add_attributes") < actual.index("generate_add_existing_attribute_to_labels_script") < actual.index("generate_update_attributes_json")
    assert actual.index("add_choices_to_attributes") < actual.index("generate_add_attribute_restriction_json")
    assert "set -euo pipefail" in actual
    assert "--allow_empty" in actual
    assert "--annofab_pat" not in actual


def test_generate_readme_describes_scope():
    actual = generate_readme()

    assert "ラベルと属性の追加・更新" in actual
    assert "既存属性への選択肢追加" in actual
    assert "既存属性のラベルへの紐付け" in actual
    assert "属性型変更" in actual


def test_main_generates_executable_artifacts(tmp_path):
    rule_path = tmp_path / "rule.md"
    rule_path.write_text("自動車を矩形で囲ってください。", encoding="utf-8")
    output_dir = tmp_path / "generated"

    main(
        argparse.Namespace(
            annotation_rule=f"@{rule_path}",
            output_dir=output_dir,
            project_id="prj1",
            model="openai/gpt-5.6-terra",
        )
    )

    assert (output_dir / "annotation_rule.md").read_text(encoding="utf-8") == "自動車を矩形で囲ってください。"
    assert (output_dir / "README.md").is_file()
    assert (output_dir / "work").is_dir()
    subprocess.run(["bash", "-n", output_dir / "apply.sh"], check=True)


def test_main_rejects_non_empty_output_dir(tmp_path):
    rule_path = tmp_path / "rule.md"
    rule_path.write_text("自動車を矩形で囲ってください。", encoding="utf-8")
    output_dir = tmp_path / "generated"
    output_dir.mkdir()
    (output_dir / "existing.txt").write_text("既存ファイル", encoding="utf-8")

    with pytest.raises(ValueError):
        main(
            argparse.Namespace(
                annotation_rule=f"@{rule_path}",
                output_dir=output_dir,
                project_id="prj1",
                model="openai/gpt-5.6-terra",
            )
        )
