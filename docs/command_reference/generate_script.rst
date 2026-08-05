============================================================
annotation_specs generate_script
============================================================

Description
=================================

自然言語で書かれたアノテーションルールから、Annofabのアノテーション仕様を追加・更新するBashスクリプト一式を生成します。生成時にAnnofabのアノテーション仕様は変更しません。

生成された ``apply.sh`` は、ラベル追加・更新、属性追加・更新、既存属性をラベルへ紐付け、既存選択式属性への選択肢追加、属性制約追加、アノテーション仕様のレビューを順に実行します。各工程で対象がない場合はスキップします。

ラベル・属性・選択肢・属性制約の削除、並べ替え、属性型変更は対象外です。

Examples
=================================

.. code-block::

    $ annofabcli-llm annotation_specs generate_script \
     --project_id ${PROJECT_ID} \
     --annotation_rule @rule.md \
     --output_dir annotation-specs-script


``annotation-specs-script`` には、以下のファイルが出力されます。

* ``apply.sh``: Annofabのアノテーション仕様を追加・更新するスクリプト
* ``annotation_rule.md``: 入力したアノテーションルールのコピー
* ``README.md``: スクリプトの実行方法
* ``work/``: 実行時に生成するJSONとレビュー結果の保存先

内容を確認してから、以下のコマンドで実行してください。

.. code-block::

    $ bash annotation-specs-script/apply.sh


Usage Details
=================================

.. argparse::
   :ref: acl.command.generate_script.add_parser
   :prog: annofabcli-llm annotation_specs generate_script
   :nosubcommands:
   :nodefaultconst:
