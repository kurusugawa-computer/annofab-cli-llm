==========================================
parse_attribute_restriction
==========================================

Description
=================================

自然言語で書かれた属性制約の情報から、Annofabの属性制約を解析します。
アノテーションルールや運用ルールの文章から、属性制約ASTやAnnofabに登録可能なJSONを生成したいときに利用できます。


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


Annofabに登録可能なJSONを出力する
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::

    $ annofabcli-llm parse_attribute_restriction \
     --project_id ${PROJECT_ID} \
     --restriction_text @restriction.md \
     --output restriction.json \
     --output_format annofab_json


ASTのJSONを出力する
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::

    $ annofabcli-llm parse_attribute_restriction \
     --annotation_specs_json_file annotation_specs.json \
     --restriction_text @restriction.md \
     --output restriction_ast.json \
     --output_format ast_json


.. note::

    解析結果の途中経過は ``$HOME/.cache/annofab-cli-llm/temp/parse_attribute_restriction_*`` に出力されます。


Usage Details
=================================

.. argparse::
   :ref: acl.command.parse_attribute_restriction.add_parser
   :prog: annofabcli-llm parse_attribute_restriction
   :nosubcommands:
   :nodefaultconst:
