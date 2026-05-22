==================================================
Command Reference
==================================================


Available Commands
=================================

annotation_specs
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. toctree::
   :maxdepth: 1
   :titlesonly:

   parse_attribute
   parse_attribute_restriction
   parse_label

annotation_zip
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. toctree::
   :maxdepth: 1
   :titlesonly:

   validate_attribute_value




Global Options
=================================

すべてのコマンドで共通して使用できるオプションです。

--model
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

使用するLLMのモデルを指定します。デフォルトは ``openai/gpt-5.4-mini`` です。

より高性能なモデルを使用したい場合や、特定の用途に適したモデルを選択したい場合に指定します。
LiteLLMに対応している様々なプロバイダーのモデルを使用できます。
詳細は `LiteLLM Providers <https://docs.litellm.ai/docs/providers>`_ を参照してください。

**使用例:**

.. code-block:: bash

    # OpenAI GPT-5.4 miniを使用
    $ annofabcli-llm annotation_zip validate_attribute_value --model openai/gpt-5.4-mini \
     --project_id ${PROJECT_ID} \
     --output validate_result.csv \
     --output_format csv \
     --label_name car \
     --attribute_name status \
     --prompt @prompt.md

    # Claude 3.5 Sonnetを使用
    $ annofabcli-llm annotation_zip validate_attribute_value --model anthropic/claude-3-5-sonnet-20241022 \
     --project_id ${PROJECT_ID} \
     --output validate_result.csv \
     --output_format csv \
     --label_name car \
     --attribute_name status \
     --prompt @prompt.md




Usage Details
=================================

.. argparse::
   :filename: ../acl/__main__.py
   :func: create_parser
   :prog: annofabcli-llm
   :nosubcommands:
