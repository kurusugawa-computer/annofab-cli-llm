=================================================================================
annotation_specs generate_add_existing_attribute_to_labels_script
=================================================================================

Description
=================================

自然言語で書かれたアノテーションルールから、既存属性をラベルへ紐付けるためのBashスクリプトを生成します。生成時にAnnofabのアノテーション仕様は変更しません。

出力されたスクリプトには、 `annofabcli annotation_specs add_existing_attribute_to_labels <https://annofab-cli.readthedocs.io/ja/latest/command_reference/annotation_specs/add_existing_attribute_to_labels.html>`_ コマンドが含まれます。内容を確認してから実行してください。

紐付ける属性は、対象プロジェクトのアノテーション仕様に既に存在している必要があります。紐付け先のラベルは、同じルールに新規ラベルを追加する指示がある場合も指定できます。この場合は、ラベル追加後に生成したスクリプトを実行してください。


Examples
=================================

基本的な使い方
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::
    :caption: rule.md

    既存の属性「occluded」を car ラベルと pedestrian ラベルに紐付けてください。


.. code-block::

    $ annofabcli-llm annotation_specs generate_add_existing_attribute_to_labels_script \
     --project_id ${PROJECT_ID} \
     --annotation_rule @rule.md \
     --output add_existing_attribute_to_labels.sh


生成された ``add_existing_attribute_to_labels.sh`` には、次のようなコマンドが出力されます。

.. code-block:: bash
    :caption: add_existing_attribute_to_labels.sh

    annofabcli annotation_specs add_existing_attribute_to_labels \
      --project_id '${PROJECT_ID}' \
      --attribute_id '${ATTRIBUTE_ID}' \
      --label_name_en car pedestrian


内容を確認してから、以下のコマンドでAnnofabのアノテーション仕様に反映できます。

.. code-block::

    $ bash add_existing_attribute_to_labels.sh


.. note::

    解析結果の途中経過は ``$HOME/.cache/annofab-cli-llm/temp/generate_add_existing_attribute_to_labels_script_*`` に出力されます。


Usage Details
=================================

.. argparse::
   :ref: acl.command.generate_add_existing_attribute_to_labels_script.add_parser
   :prog: annofabcli-llm annotation_specs generate_add_existing_attribute_to_labels_script
   :nosubcommands:
   :nodefaultconst:
