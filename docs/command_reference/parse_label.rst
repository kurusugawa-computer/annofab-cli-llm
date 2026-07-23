============================================================
annotation_specs parse_label
============================================================

Description
=================================

自然言語で書かれたアノテーションルールやアノテーション仕様の文章から、Annofabに追加するラベルを解析します。
出力されるJSONは、 `annofabcli annotation_specs add_labels <https://annofab-cli.readthedocs.io/ja/latest/command_reference/annotation_specs/add_labels.html>`_ コマンドの ``--label_json`` 引数にそのまま指定できます。

このコマンドは、新規でアノテーション仕様を作成する場合に最初に実行します。


Examples
=================================

基本的な使い方
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


.. code-block::
    :caption: rule.md

    歩行者と自動車を矩形で囲ってください。
    歩行者の最小矩形サイズは100x200、自動車の最小矩形サイズは300x300です。
    すべてのラベルの許容誤差は5pxです。
    隠れている場合は、「隠れ」チェックボックスをONにしてください。



.. code-block::

    $ annofabcli-llm annotation_specs parse_label \
     --project_type image \
     --annotation_rule @rule.md \
     --output labels.json
     


.. code-block:: json    
    :caption: labels.json

  [
    {
      "label_name_en": "pedestrian",
      "annotation_type": "bounding_box",
      "label_name_ja": "歩行者",
      "keybind": {
        "alt": false,
        "code": "KeyQ",
        "ctrl": false,
        "shift": false
      },
      "field_values": {
        "minimum_size_2d_with_default_insert_position": {
          "min_warn_rule": {
            "_type": "Or"
          },
          "min_width": 100,
          "min_height": 200,
          "position_for_minimum_bounding_box_insertion": null,
          "_type": "MinimumSize2dWithDefaultInsertPosition"
        },
        "margin_of_error_tolerance": {
          "_type": "MarginOfErrorTolerance",
          "max_pixel": 5
        }
      }
    },
    {
      "label_name_en": "car",
      "annotation_type": "bounding_box",
      "label_name_ja": "自動車",
      "keybind": {
        "alt": false,
        "code": "KeyW",
        "ctrl": false,
        "shift": false
      },
      "field_values": {
        "minimum_size_2d_with_default_insert_position": {
          "min_warn_rule": {
            "_type": "Or"
          },
          "min_width": 300,
          "min_height": 300,
          "position_for_minimum_bounding_box_insertion": null,
          "_type": "MinimumSize2dWithDefaultInsertPosition"
        },
        "margin_of_error_tolerance": {
          "_type": "MarginOfErrorTolerance",
          "max_pixel": 5
        }
      }
    }
  ]


``parse_label`` コマンドで出力された ``labels.json`` は、以下のコマンドでAnnofabのアノテーション仕様にラベルを追加できます。


.. code-block::
  
    $ annofabcli annotation_specs add_labels \
     --project_id ${PROJECT_ID} \
     --label_json file://labels.json


.. note::

    解析結果の途中経過は ``$HOME/.cache/annofab-cli-llm/temp/parse_label_*`` に出力されます。



既存のアノテーション仕様を参照する
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``--project_id`` オプションを指定すると、Annofabの既存のアノテーション仕様を参照して、現在存在しないラベルのみ出力されます。

.. code-block::

    $ annofabcli-llm annotation_specs parse_label \
     --project_id ${PROJECT_ID} \
     --project_type image \
     --annotation_rule @rule.md \
     --output labels.json



Usage Details
=================================

.. argparse::
   :ref: acl.command.parse_label.add_parser
   :prog: annofabcli-llm annotation_specs parse_label
   :nosubcommands:
   :nodefaultconst:
