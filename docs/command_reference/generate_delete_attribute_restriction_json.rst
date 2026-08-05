=============================================================
annotation_specs generate_delete_attribute_restriction_json
=============================================================

Description
=================================

自然言語で書かれた変更内容から、既存の属性制約を選択して削除用JSONを生成します。
出力したJSONは、 `annofabcli annotation_specs delete_attribute_restriction <https://annofab-cli.readthedocs.io/ja/latest/command_reference/annotation_specs/delete_attribute_restriction.html>`_ コマンドの ``--restriction_json`` 引数に指定できます。

このコマンドは既存の属性制約から削除対象を選択します。属性制約の条件をLLMが再作成するものではありません。削除対象を一意に特定できない場合は、対話的に補足情報を入力できます。


Examples
=================================

削除用JSONを生成する
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::
    :caption: delete_restriction.md

    車種がトラックの場合は天候を必須にする制約を削除してください。


.. code-block::

    $ annofabcli-llm annotation_specs generate_delete_attribute_restriction_json \
     --project_id ${PROJECT_ID} \
     --restriction_text @delete_restriction.md \
     --output restriction.json


生成された ``restriction.json`` を指定して削除します。実際の削除前には、 ``annofabcli`` 側で対象制約と確認メッセージが表示されます。

.. code-block::

    $ annofabcli annotation_specs delete_attribute_restriction \
     --project_id ${PROJECT_ID} \
     --restriction_json file://restriction.json


.. note::

    解析結果の途中経過は ``$HOME/.cache/annofab-cli-llm/temp/generate_delete_attribute_restriction_json_*`` に出力されます。


Usage Details
=================================

.. argparse::
   :ref: acl.command.generate_delete_attribute_restriction_json.add_parser
   :prog: annofabcli-llm annotation_specs generate_delete_attribute_restriction_json
   :nosubcommands:
   :nodefaultconst:
