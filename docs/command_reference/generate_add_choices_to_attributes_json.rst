===================================================================
annotation_specs generate_add_choices_to_attributes_json
===================================================================

Description
=================================

自然言語で書かれた選択肢追加ルールやアノテーション仕様の文章から、既存の選択肢系属性に追加する選択肢のJSONを生成します。
出力されるJSONは、 `annofabcli annotation_specs add_choices_to_attributes <https://annofab-cli.readthedocs.io/ja/latest/command_reference/annotation_specs/add_choices_to_attributes.html>`_ コマンドの ``--attribute_json`` 引数にそのまま指定できます。

対象属性は ``--attribute_id`` で明示的に指定します。対象は ``choice`` または ``select`` 型の既存属性である必要があります。


Examples
=================================

.. code-block::
    :caption: rule.md

    車種に「トラック」と「バス」を追加してください。


.. code-block::

    $ annofabcli-llm annotation_specs generate_add_choices_to_attributes_json \
     --project_id ${PROJECT_ID} \
     --attribute_id ${ATTRIBUTE_ID} \
     --annotation_rule @rule.md \
     --output choices.json


.. code-block:: json
    :caption: choices.json

    [
      {
        "attribute_id": "${ATTRIBUTE_ID}",
        "choices": [
          {
        "choice_name_en": "truck",
        "choice_name_ja": "トラック"
          },
          {
        "choice_name_en": "bus",
        "choice_name_ja": "バス"
          }
        ]
      }
    ]


生成された ``choices.json`` は、以下のコマンドでAnnofabのアノテーション仕様に反映できます。

.. code-block::

    $ annofabcli annotation_specs add_choices_to_attributes \
     --project_id ${PROJECT_ID} \
     --attribute_json file://choices.json


.. note::

    解析結果の途中経過は ``$HOME/.cache/annofab-cli-llm/temp/generate_add_choices_to_attributes_json_*`` に出力されます。


Usage Details
=================================

.. argparse::
   :ref: acl.command.generate_add_choices_to_attributes_json.add_parser
   :prog: annofabcli-llm annotation_specs generate_add_choices_to_attributes_json
   :nosubcommands:
   :nodefaultconst:
