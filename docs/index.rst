==================================================
annofab-cli-llm
==================================================

annofab-cli-llmは、annofab-cliとLLMを組み合わせたツールです。

Requirements
=================================
* Python 3.12+

Install
=================================

.. code-block:: bash
   
   $ pip install annofab-cli-llm


Configurations
=================================

1. annofabcliの認証情報を設定します。 https://annofab-cli.readthedocs.io/ja/latest/user_guide/configurations.html#id1 を参照してください。
2. 使用するLLMのトークンを環境変数に設定します。

   * OpenAIならば、``OPENAI_API_KEY`` にAPIキーを設定します。
   * その他のLLMのトークンについては、 https://github.com/BerriAI/litellm を参照してください。なお、このツールでは `litellm <https://github.com/BerriAI/litellm>`_ を使用してLLMにアクセスしています。





Table of Contents
==================================================

.. toctree::
   :maxdepth: 2

   command_reference/index


