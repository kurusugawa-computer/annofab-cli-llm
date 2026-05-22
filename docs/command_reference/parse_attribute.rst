============================================================
annotation_specs parse_attribute
============================================================

Description
=================================

自然言語で書かれた属性追加ルールやアノテーション仕様の文章から、Annofabに追加する属性を解析します。
出力されるJSONは、 `annofabcli annotation_specs add_attributes <https://annofab-cli.readthedocs.io/ja/latest/command_reference/annotation_specs/add_attributes.html>`_ コマンドの ``--attribute_json`` 引数にそのまま指定できます。



Examples
=================================

基本的な使い方
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::
    :caption: rule.md

    車と歩行者には見切れ属性を追加してください。
    車には天気属性をドロップダウンで追加し、晴れと雨を選べるようにしてください。


.. code-block::

    $ annofabcli-llm annotation_specs parse_attribute \
     --annotation_specs_json_file annotation_specs.json \
     --annotation_rule @rule.md


.. code-block:: json
    :caption: 標準出力

    [
      {
        "attribute_type": "flag",
        "attribute_name_en": "truncated",
        "label_name_ens": [
          "car",
          "pedestrian"
        ],
        "attribute_name_ja": "見切れ"
      },
      {
        "attribute_type": "select",
        "attribute_name_en": "weather",
        "label_name_ens": [
          "car"
        ],
        "attribute_name_ja": "天気",
        "choices": [
          {
            "choice_name_en": "sunny",
            "choice_name_ja": "晴れ",
            "is_default": true
          },
          {
            "choice_name_en": "rainy",
            "choice_name_ja": "雨",
            "is_default": false
          }
        ]
      }
    ]


Annofabへ属性を追加する
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::

    $ annofabcli-llm annotation_specs parse_attribute \
     --project_id ${PROJECT_ID} \
     --annotation_rule @rule.md \
     --output attributes.json

    $ annofabcli annotation_specs add_attributes \
     --project_id ${PROJECT_ID} \
     --attribute_json file://attributes.json


.. note::

    解析結果の途中経過は ``$HOME/.cache/annofab-cli-llm/temp/parse_attribute_*`` に出力されます。


Usage Details
=================================

.. argparse::
   :ref: acl.command.parse_attribute.add_parser
   :prog: annofabcli-llm annotation_specs parse_attribute
   :nosubcommands:
   :nodefaultconst:
