============================================================
annotation_specs generate_update_labels_json
============================================================

Description
=================================

自然言語で書かれたラベル更新ルールやアノテーション仕様の文章から、Annofabの既存ラベルを更新するJSONを生成します。
出力されるJSONは、 `annofabcli annotation_specs update_labels <https://annofab-cli.readthedocs.io/ja/latest/command_reference/annotation_specs/update_labels.html>`_ コマンドの ``--label_json`` 引数にそのまま指定できます。

このコマンドを実行するには、更新対象のラベルがアノテーション仕様に存在している必要があります。
``field_values`` を更新する場合、出力JSONには ``field_values_operation`` として ``replace`` が自動で設定されます。
そのため、残したい既存の ``field_values`` も含めた更新後の値が出力されます。


Examples
=================================

基本的な使い方
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::
    :caption: rule.md

    carラベルの英語名をvehicle、日本語名を「自動車」に変更してください。
    carラベルの色を #00AAFF にしてください。


.. code-block::

    $ annofabcli-llm annotation_specs generate_update_labels_json \
     --project_id ${PROJECT_ID} \
     --annotation_rule @rule.md \
     --output labels.json


.. code-block:: json
    :caption: labels.json

    [
      {
        "label_id": "label_car",
        "label_name_en": "vehicle",
        "label_name_ja": "自動車",
        "color": "#00AAFF"
      }
    ]


生成された ``labels.json`` は、以下のコマンドでAnnofabのアノテーション仕様に反映できます。

.. code-block::

    $ annofabcli annotation_specs update_labels \
     --project_id ${PROJECT_ID} \
     --label_json file://labels.json


.. note::

    解析結果の途中経過は ``$HOME/.cache/annofab-cli-llm/temp/generate_update_labels_json_*`` に出力されます。


Usage Details
=================================

.. argparse::
   :ref: acl.command.generate_update_labels_json.add_parser
   :prog: annofabcli-llm annotation_specs generate_update_labels_json
   :nosubcommands:
   :nodefaultconst:
