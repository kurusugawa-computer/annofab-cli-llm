============================================================
annotation_specs generate_script
============================================================

Description
=================================

自然言語で書かれたアノテーションルールから、Annofabのアノテーション仕様を追加するBashスクリプト一式を生成します。生成時にAnnofabのアノテーション仕様は変更しません。

生成された ``apply.sh`` は、ラベル追加、属性追加、属性制約追加、アノテーション仕様のレビューを順に実行します。属性を追加する際は、選択肢も同時に追加できます。

Examples
=================================

.. code-block::

    $ annofabcli-llm annotation_specs generate_script \
     --project_id ${PROJECT_ID} \
     --annotation_rule @rule.md \
     --output_dir annotation-specs-script


``annotation-specs-script`` には、以下のファイルが出力されます。

* ``apply.sh``: Annofabのアノテーション仕様を追加するスクリプト
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
