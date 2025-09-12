==========================================
validate_attribute_value
==========================================

Description
=================================

アノテーションの属性値を検証します。
自然言語で記載された属性値の検証などに利用できます。
たとえば、以下のようなケースで利用できます。

* 属性値の誤字脱字の検出
* 属性値がmarkdownの文法に準拠しているかの検証
* 属性値Aと属性値Bの関係が矛盾していないかの検証


Examples
=================================

基本的な使い方
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::
    :caption: prompt.md

    明かな誤字脱字がないかを検出してください。
    ただし以下のケースは問題ないので、検出しないでください。
    * 長音の有無などの表現の揺れ
    * 文法的な改善提案
    * 文末の句点忘れ
    * 読点が多すぎる
    * 文末の不要な空白
    * 文の途中の改行文字
    * 口語的な表現


ラベル名が ``car`` 、属性名が ``status`` である属性値を、 ``prompt.md`` の内容で検証します。

.. code-block::

    $ annofabcli-llm validate_annotation_attribute --project_id ${PROJECT_ID} \
     --output validate_result.csv \
     --output_format csv \
     --label_name car \
     --attribute_name status \
     --prompt @prompt.md


異なるLLMモデルを使用する場合
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

より高性能なモデルを使用したい場合や、特定の用途に適したモデルを選択できます。

.. code-block::

    # GPT-4を使用（より高精度だが処理時間が長い）
    $ annofabcli-llm validate_annotation_attribute --model openai/gpt-4 \
     --project_id ${PROJECT_ID} \
     --output validate_result.csv \
     --output_format csv \
     --label_name car \
     --attribute_name status \
     --prompt @prompt.md

    # Claude-3.5 Sonnetを使用（テキスト処理に優秀）
    $ annofabcli-llm validate_annotation_attribute --model anthropic/claude-3-5-sonnet-20241022 \
     --project_id ${PROJECT_ID} \
     --output validate_result.csv \
     --output_format csv \
     --label_name car \
     --attribute_name status \
     --prompt @prompt.md


.. csv-table:: validate_result.csv 
    :header-rows: 1
    :file: validate_attribute_value/validate_result.csv


以下は、列の説明です。

* ``attributes`` : LLMが検証した属性値（keyが属性名、valueが属性値であるdict）
* ``validation_messages`` : LLMの検証結果のメッセージ（keyが属性名、valueが検証結果のメッセージであるdict）
* ``suggested_attributes`` : LLMの提案する属性値（keyが属性名、valueが属性値であるdict）


``validate_result.csv`` の ``suggested_attributes`` 列を ``attributes`` に変更することで、
`annofabcli annotation change_attributes_per_annotation <https://annofab-cli.readthedocs.io/ja/latest/command_reference/annotation/change_attributes_per_annotation.html>`_ コマンドの ``--csv`` に渡して、属性値を一括で変更できます。



.. note::

    検証結果の途中経過は ``$HOME/.cache/annofab-cli-llm/temp/validate_annotation_attribute_*`` に出力されます。




属性やアノテーションルールのコンテキストを追加する
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


.. code-block::
    :caption: attribute_description.md

    属性`status`は画像に映っている状態を表します。


.. code-block::
    :caption: annotation_overview.md

    画像の状況を説明するアノテーションです。


.. code-block::

    $ annofabcli-llm validate_annotation_attribute --project_id ${PROJECT_ID} \
     --output validate_result.csv \
     --output_format csv
     --label_name car \
     --attribute_name status
     --prompt @prompt.md \
     --attribute_description @attribute_description.md \
     --annotation_overview @annotation_overview.md





Usage Details
=================================

.. argparse::
   :ref: acl.command.validate_attribute_value.add_parser
   :prog: annofabcli-llm validate_attribute_value
   :nosubcommands:
   :nodefaultconst:


