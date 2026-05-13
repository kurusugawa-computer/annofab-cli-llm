==========================================
parse_attribute_restriction
==========================================

Description
=================================

自然言語で書かれた属性制約の情報から、Annofabの属性制約を解析します。
アノテーションルールや運用ルールの文章から、属性制約ASTやAnnofabに登録可能なJSONを生成したいときに利用できます。
``annofab_json`` 形式で出力したJSONは、 `annofabcli annotation_specs add_attribute_restriction <https://annofab-cli.readthedocs.io/ja/latest/command_reference/annotation_specs/add_attribute_restriction.html>`_ コマンドでAnnofabに登録できます。


Examples
=================================

基本的な使い方
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::
    :caption: restriction.md

    属性`occluded`がチェックされているときは、属性`note`を必須にしてください。
    属性`vehicle_type`には`general_car`を選択してください。


.. code-block::

    $ annofabcli-llm parse_attribute_restriction \
     --annotation_specs_json_file annotation_specs.json \
     --restriction_text @restriction.md \
     --output_format human_readable


.. code-block::
    :caption: 標準出力

    [restrictions]
    - If 'occluded' is checked, 'note' is not empty.
    - 'vehicle_type' is 'general_car'


Annofabに登録可能なJSONを出力する
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::

    $ annofabcli-llm parse_attribute_restriction \
     --project_id ${PROJECT_ID} \
     --restriction_text @restriction.md \
     --output restriction.json \
     --output_format annofab_json


生成された ``restriction.json`` は、 `annofabcli annotation_specs add_attribute_restriction <https://annofab-cli.readthedocs.io/ja/latest/command_reference/annotation_specs/add_attribute_restriction.html>`_ コマンドの入力として利用できます。
以下は ``restriction.json`` の出力例です。 ``additional_data_definition_id`` や選択肢のIDは、プロジェクトのアノテーション仕様によって異なります。


.. code-block:: json
    :caption: restriction.json

    [
      {
        "additional_data_definition_id": "attr_note",
        "condition": {
          "_type": "Imply",
          "premise": {
            "additional_data_definition_id": "attr_occluded",
            "condition": {
              "_type": "Equals",
              "value": "true"
            }
          },
          "condition": {
            "_type": "NotEquals",
            "value": ""
          }
        }
      },
      {
        "additional_data_definition_id": "attr_vehicle_type",
        "condition": {
          "_type": "Equals",
          "value": "choice_general_car"
        }
      }
    ]


ASTのJSONを出力する
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::

    $ annofabcli-llm parse_attribute_restriction \
     --annotation_specs_json_file annotation_specs.json \
     --restriction_text @restriction.md \
     --output restriction_ast.json \
     --output_format ast_json


.. code-block:: json
    :caption: restriction_ast.json

    {
      "asts": [
        {
          "type": "imply",
          "premise": {
            "type": "checked",
            "attribute_name": "occluded"
          },
          "conclusion": {
            "type": "is_not_empty",
            "attribute_name": "note"
          }
        },
        {
          "type": "has_choice",
          "attribute_name": "vehicle_type",
          "choice_name": "general_car"
        }
      ],
      "warnings": [],
      "unresolved_texts": []
    }


.. note::

    解析結果の途中経過は ``$HOME/.cache/annofab-cli-llm/temp/parse_attribute_restriction_*`` に出力されます。


Usage Details
=================================

.. argparse::
   :ref: acl.command.parse_attribute_restriction.add_parser
   :prog: annofabcli-llm parse_attribute_restriction
   :nosubcommands:
   :nodefaultconst:
