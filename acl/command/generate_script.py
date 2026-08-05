import argparse
import shlex
from pathlib import Path

from loguru import logger

import acl.common.cli
from acl.common.cli import read_at_file
from acl.common.utils import output_string

COMMAND_NAME = "generate_script"
"""コマンド名です。"""
SCRIPT_FILE_NAME = "apply.sh"
"""生成するBashスクリプトのファイル名です。"""
RULE_FILE_NAME = "annotation_rule.md"
"""生成先に保存するアノテーションルールのファイル名です。"""
README_FILE_NAME = "README.md"
"""生成先に保存する説明ファイルのファイル名です。"""


def generate_script(*, project_id: str, annotation_rule_path: Path, model: str) -> str:
    """
    アノテーション仕様を追加するBashスクリプトを生成します。

    Args:
        project_id: AnnofabのプロジェクトID
        annotation_rule_path: 生成先ディレクトリ内のアノテーションルールファイル
        model: 使用するLLMのモデル

    Returns:
        Bashスクリプト
    """
    quoted_project_id = shlex.quote(project_id)
    quoted_model = shlex.quote(model)
    quoted_rule_file_name = shlex.quote(annotation_rule_path.name)

    return f"""#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
PROJECT_ID={quoted_project_id}
MODEL={quoted_model}
RULE_FILE="$SCRIPT_DIR/{quoted_rule_file_name}"
WORK_DIR="$SCRIPT_DIR/work"

if [[ "${{1:-}}" != "--yes" ]]; then
  read -r -p "プロジェクト '$PROJECT_ID' のアノテーション仕様を追加します。続行しますか？ [y/N] " answer
  if [[ "$answer" != "y" ]]; then
    echo "中止しました。"
    exit 0
  fi
fi

mkdir -p "$WORK_DIR"

apply_if_not_empty() {{
  local json_file="$1"
  local resource_name="$2"
  shift 2

  if [[ "$(tr -d '[:space:]' < "$json_file")" == "[]" ]]; then
    echo "$resource_name の追加対象はありません。"
    return
  fi

  "$@"
}}

echo "ラベルを解析します。"
annofabcli-llm annotation_specs generate_add_labels_json \\
  --project_id "$PROJECT_ID" \\
  --annotation_rule "@$RULE_FILE" \\
  --model "$MODEL" \\
  --allow_empty \\
  --output "$WORK_DIR/labels.json"
apply_if_not_empty "$WORK_DIR/labels.json" "ラベル" \\
  annofabcli annotation_specs add_labels \\
    --project_id "$PROJECT_ID" \\
    --label_json "file://$WORK_DIR/labels.json"

echo "属性を解析します。"
annofabcli-llm annotation_specs generate_add_attributes_json \\
  --project_id "$PROJECT_ID" \\
  --annotation_rule "@$RULE_FILE" \\
  --model "$MODEL" \\
  --allow_empty \\
  --output "$WORK_DIR/attributes.json"
apply_if_not_empty "$WORK_DIR/attributes.json" "属性" \\
  annofabcli annotation_specs add_attributes \\
    --project_id "$PROJECT_ID" \\
    --attribute_json "file://$WORK_DIR/attributes.json"

echo "属性制約を解析します。"
annofabcli-llm annotation_specs generate_add_attribute_restriction_json \\
  --project_id "$PROJECT_ID" \\
  --restriction_text "@$RULE_FILE" \\
  --model "$MODEL" \\
  --output_format annofab_json \\
  --output "$WORK_DIR/attribute_restrictions.json"
apply_if_not_empty "$WORK_DIR/attribute_restrictions.json" "属性制約" \\
  annofabcli annotation_specs add_attribute_restriction \\
    --project_id "$PROJECT_ID" \\
    --restriction_json "file://$WORK_DIR/attribute_restrictions.json"

echo "アノテーション仕様をレビューします。"
annofabcli-llm annotation_specs validate \\
  --project_id "$PROJECT_ID" \\
  --annotation_rule "@$RULE_FILE" \\
  --model "$MODEL" \\
  --output "$WORK_DIR/validation.md"

echo "アノテーション仕様の追加が完了しました。"
echo "レビュー結果: $WORK_DIR/validation.md"
"""


def generate_readme() -> str:
    """
    生成物を説明するREADMEを生成します。

    Returns:
        READMEの内容
    """
    return """# アノテーション仕様の追加

`apply.sh` は、ラベル、属性、属性制約をこの順にAnnofabへ追加し、最後にアノテーション仕様をレビューします。

## 実行方法

内容を確認してから、以下を実行してください。

```bash
bash apply.sh
```

確認を省略する場合は、以下を実行してください。

```bash
bash apply.sh --yes
```

`work/` には各工程で生成したJSONとレビュー結果が保存されます。途中で失敗した場合は、内容を確認してから再実行してください。

既存の選択式属性への選択肢追加や、既存のラベル・属性の更新はこのスクリプトの対象外です。
"""


def main(args: argparse.Namespace) -> None:
    annotation_rule = read_at_file(args.annotation_rule)
    output_dir = args.output_dir
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"出力先ディレクトリが空ではありません。 :: output_dir='{output_dir}'")
    output_dir.mkdir(parents=True, exist_ok=True)

    rule_path = output_dir / RULE_FILE_NAME
    script_path = output_dir / SCRIPT_FILE_NAME
    readme_path = output_dir / README_FILE_NAME
    work_dir = output_dir / "work"

    output_string(annotation_rule, rule_path)
    output_string(generate_script(project_id=args.project_id, annotation_rule_path=rule_path, model=args.model), script_path)
    output_string(generate_readme(), readme_path)
    work_dir.mkdir(exist_ok=True)

    logger.info(f"アノテーション仕様追加用スクリプトを出力しました。 :: output_dir='{output_dir}'")
    logger.info(f"スクリプトを確認後、`bash {script_path} --yes` を実行してください。")


def add_argument_to_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-p", "--project_id", type=str, required=True, help="AnnofabのプロジェクトID")
    parser.add_argument(
        "--annotation_rule",
        type=str,
        required=True,
        help="追加するラベル、属性、属性制約が記載された自然言語。先頭に`@`を指定すると、`@`以降をファイルパスとみなしてファイルの中身を読み込みます。",
    )
    parser.add_argument("-o", "--output_dir", type=Path, required=True, help="スクリプト一式を出力するディレクトリのパス")


def add_parser(subparsers: argparse._SubParsersAction | None = None) -> argparse.ArgumentParser:
    parser = acl.common.cli.add_parser(
        subparsers,
        COMMAND_NAME,
        "アノテーション仕様追加用のBashスクリプトを生成します。",
        description="アノテーション仕様追加用のBashスクリプトを生成します。生成時にAnnofabのアノテーション仕様は変更しません。",
    )
    add_argument_to_parser(parser)
    parser.set_defaults(func=main)
    return parser
