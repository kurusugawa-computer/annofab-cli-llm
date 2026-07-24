============================================================
annotation_specs validate
============================================================

Description
=================================

Annofabプロジェクトのアノテーション仕様を、レビュー観点に基づいてLLMでレビューします。
アノテーションルールを指定した場合は、アノテーションルールに対してアノテーション仕様をレビューします。

このコマンドは内部で以下のコマンド相当の情報を取得し、LLMに渡します。

* ``annofabcli annotation_specs list_label --format json``
* ``annofabcli annotation_specs list_attribute --format json``
* ``annofabcli annotation_specs list_attribute_restriction --format json``


Examples
=================================

基本的な使い方
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    $ annofabcli-llm annotation_specs validate \
     --project_id ${PROJECT_ID} \
     --output review.md


アノテーションルールを指定する
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::
    :caption: annotation_rule.md

    車と歩行者を矩形で囲ってください。
    車には見切れ属性を付与してください。


.. code-block:: bash

    $ annofabcli-llm annotation_specs validate \
     --project_id ${PROJECT_ID} \
     --annotation_rule @annotation_rule.md \
     --output review.md


レビュー観点を指定する
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::
    :caption: review_point.md

    以下の観点でレビューしてください。

    - ラベル名と属性名がアノテーションルールに沿っているか
    - 属性制約が不足していないか

    以下は評価しないでください。

    - 軽微な日本語表現の違い


.. code-block:: bash

    $ annofabcli-llm annotation_specs validate \
     --project_id ${PROJECT_ID} \
     --annotation_rule @annotation_rule.md \
     --review_point @review_point.md \
     --output review.md


JSONで出力する
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    $ annofabcli-llm annotation_specs validate \
     --project_id ${PROJECT_ID} \
     --annotation_rule @annotation_rule.md \
     --output_format json \
     --output review.json


.. note::

    レビュー結果の途中経過は ``$HOME/.cache/annofab-cli-llm/temp/validate_*`` に出力されます。



Usage Details
=================================

.. argparse::
   :ref: acl.command.validate_annotation_specs.add_parser
   :prog: annofabcli-llm annotation_specs validate
   :nosubcommands:
   :nodefaultconst:
