# annofab-cli-llm
annofab-cliとLLMを組み合わせたツールです。

# Requirements
* Python 3.12+

# Intall

```
$ pip install annofab-cli-llm
```

# 設定
1. annofabcliの認証情報を設定する。 https://annofab-cli.readthedocs.io/ja/latest/user_guide/configurations.html#id1
2. 使用するLLMのトークンを環境変数に設定する
    * OpenAIならば、`OPENAI_API_KEY`。
    * その他のLLMのトークンについては、https://github.com/BerriAI/litellm を参照してください。内部で litellm を使用しています。
    
    
# Usage

```
$ annofabcli-llm --help
```

