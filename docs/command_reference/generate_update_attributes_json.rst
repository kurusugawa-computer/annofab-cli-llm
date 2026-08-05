============================================================
annotation_specs generate_update_attributes_json
============================================================

Description
=================================

自然言語で書かれた属性更新ルールやアノテーション仕様の文章から、Annofabの既存属性を更新するJSONを生成します。
出力されるJSONは、 `annofabcli annotation_specs update_attributes <https://annofab-cli.readthedocs.io/ja/latest/command_reference/annotation_specs/update_attributes.html>`_ コマンドの ``--attribute_json`` 引数にそのまま指定できます。

このコマンドを実行するには、更新対象の属性や選択肢がアノテーション仕様に存在している必要があります。


Examples
=================================

基本的な使い方
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::
    :caption: rule.md

    note属性の日本語名を「コメント」に変更してください。
    note属性を読み込み専用にしてください。
    vehicle_type属性のtruck選択肢の日本語名を「貨物車」に変更してください。


.. code-block::

    $ annofabcli-llm annotation_specs generate_update_attributes_json \
     --project_id ${PROJECT_ID} \
     --annotation_rule @rule.md \
     --output attributes.json


.. code-block:: json
    :caption: attributes.json

    [
      {
        "attribute_id": "attr_note",
        "attribute_name_ja": "コメント",
        "read_only": true
      },
      {
        "attribute_id": "attr_vehicle_type",
        "choice_updates": [
          {
            "choice_id": "choice_truck",
            "choice_name_ja": "貨物車"
          }
        ]
      }
    ]


生成された ``attributes.json`` は、以下のコマンドでAnnofabのアノテーション仕様に反映できます。

.. code-block::

    $ annofabcli annotation_specs update_attributes \
     --project_id ${PROJECT_ID} \
     --attribute_json file://attributes.json


.. note::

    解析結果の途中経過は ``$HOME/.cache/annofab-cli-llm/temp/generate_update_attributes_json_*`` に出力されます。


Usage Details
=================================

.. argparse::
   :ref: acl.command.generate_update_attributes_json.add_parser
   :prog: annofabcli-llm annotation_specs generate_update_attributes_json
   :nosubcommands:
   :nodefaultconst:
