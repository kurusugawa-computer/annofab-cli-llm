from importlib.metadata import PackageNotFoundError, version

PACKAGE_NAME = "annofabcli-llm"
"""配布パッケージ名。"""

try:
    __version__ = version(PACKAGE_NAME)
except PackageNotFoundError:
    # パッケージメタデータを取得できない環境向けにfallbackしたバージョンを設定する。
    __version__ = "0.0.0"
