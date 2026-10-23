# annofab-cli-llm
annofab-cliとLLMを組み合わせたツールです。

[![PyPI version](https://badge.fury.io/py/annofabcli-llm.svg)](https://badge.fury.io/py/annofabcli-llm)
[![Python Versions](https://img.shields.io/pypi/pyversions/annofabcli-llm.svg)](https://pypi.org/project/annofabcli-llm/)



# Requirements
* Python 3.12+

# Install

```
$ pip install annofabcli-llm
```

# Configurations

https://annofab-cli-llm.readthedocs.io/ja/latest/index.html#configurations を参照してください。

    
# Usage

```
$ annofabcli-llm --help
```

詳細は https://annofab-cli-llm.readthedocs.io/ja/latest/command_reference/index.html を参照してください。

## Python 3.15 の開発環境

依存先の `fastuuid` 0.14 は Python 3.15 用の wheel がないため、Rust ツールチェーンをインストールし、PyO3 の安定 ABI 互換モードでビルドします。CI の Python 3.15 ジョブでも同じ設定を利用します。

```sh
export UV_PYTHON=3.15
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
uv sync --locked
make lint
uv run pytest tests/ -m "not access_webapi"
```

lint・整形には Ruff、型検査には mypy を利用します。`make format` で整形し、`make lint` でチェックしてください。

## シークレット検査

`make gitleaks` で現在のブランチの Git 履歴（マージ時の変更を含む）を検査します。gitleaks をインストール済みならそのコマンドを使い、未インストールなら Docker で v8.30.1 を実行します。検出値はログでマスクします。CI でも同じ検査を実行します。

DevContainer には gitleaks v8.30.1 を同梱しています。既存のコンテナは再ビルドしてください。

コミット前の差分検査には pre-commit フックを利用できます。

```sh
uv sync --locked
uv run pre-commit install
```

Docker の接続先・認証設定は、通常利用している設定を引き継ぎます。設定ディレクトリを明示的に切り替える場合のみ、`GITLEAKS_DOCKER_CONFIG=/tmp/gitleaks-docker-config make gitleaks` のように指定してください。
