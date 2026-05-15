==========================================
parse_label
==========================================

Description
=================================

自然言語で書かれたアノテーションルールやアノテーション仕様の文章から、Annofabに追加するラベルを解析します。
出力されるJSONは、 `annofabcli annotation_specs add_labels <https://annofab-cli.readthedocs.io/ja/latest/command_reference/annotation_specs/add_labels.html>`_ コマンドの ``--label_json`` 引数にそのまま指定できます。


Examples
=================================

基本的な使い方
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::
    :caption: rule.md

    歩行者と自転車のラベルを追加してください。
    どちらも bounding_box です。


.. code-block::

    $ annofabcli-llm parse_label \
     --annotation_specs_json_file annotation_specs.json \
     --project_type image \
     --annotation_rule @rule.md


.. code-block:: json
    :caption: 標準出力

    [
      {
        "label_name_en": "pedestrian",
        "label_name_ja": "歩行者",
        "annotation_type": "bounding_box"
      },
      {
        "label_name_en": "bicycle",
        "annotation_type": "bounding_box"
      }
    ]


Annofabへラベルを追加する
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::

    $ annofabcli-llm parse_label \
     --project_id ${PROJECT_ID} \
     --project_type image \
     --annotation_rule @rule.md \
     --output labels.json

    $ annofabcli annotation_specs add_labels \
     --project_id ${PROJECT_ID} \
     --label_json file://labels.json


.. note::

    解析結果の途中経過は ``$HOME/.cache/annofab-cli-llm/temp/parse_label_*`` に出力されます。


Usage Details
=================================

.. argparse::
   :ref: acl.command.parse_label.add_parser
   :prog: annofabcli-llm parse_label
   :nosubcommands:
   :nodefaultconst:
