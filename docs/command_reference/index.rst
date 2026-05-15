==================================================
Command Reference
==================================================


Available Commands
=================================

.. toctree::
   :maxdepth: 1
   :titlesonly:

   parse_attribute
   parse_attribute_restriction
   parse_label
   validate_attribute_value




Global Options
=================================

すべてのコマンドで共通して使用できるオプションです。

--model
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

使用するLLMのモデルを指定します。デフォルトは ``openai/gpt-5.4-mini`` です。

LiteLLMに対応している様々なプロバイダーのモデルを使用できます。
詳細は `LiteLLM Providers <https://docs.litellm.ai/docs/providers>`_ を参照してください。

**使用例:**

.. code-block:: bash

    # OpenAI GPT-5.4 miniを使用
    $ annofabcli-llm validate_annotation_attribute --model openai/gpt-5.4-mini ...




Usage Details
=================================

.. argparse::
   :filename: ../acl/__main__.py
   :func: create_parser
   :prog: annofabcli-llm
   :nosubcommands:
