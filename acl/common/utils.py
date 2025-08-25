import copy
import json
import logging
import logging.config
import re
import sys
from pathlib import Path
from typing import Any, TypeVar

import pandas

logger = logging.getLogger(__name__)

T = TypeVar("T")  # Can be anything


DEFAULT_CSV_FORMAT = {"encoding": "utf_8_sig", "index": False}


def read_lines(filepath: Path) -> list[str]:
    """ファイルを行単位で読み込む。改行コードを除く"""
    # BOM付きUTF-8のファイルも読み込めるようにする
    # annofabcliが出力するCSVはデフォルトでBOM付きUTF-8。これを加工してannofabcliに読み込ませる場合もあるので、BOM付きUTF-8に対応させた
    with filepath.open(encoding="utf-8-sig") as f:
        lines = f.readlines()
    return [e.rstrip("\r\n") for e in lines]


def read_lines_except_blank_line(filepath: Path) -> list[str]:
    """ファイルを行単位で読み込む。ただし、改行コード、空行を除く"""
    lines = read_lines(filepath)
    return [line for line in lines if line != ""]


def output_string(target: str, output: str | Path | None = None) -> None:
    """
    文字列を出力する。

    Args:
        target: 出力対象の文字列
        output: 出力先。Noneなら標準出力に出力する。
    """
    if output is None:
        print(target)  # noqa: T201
    else:
        p_output = output if isinstance(output, Path) else Path(output)
        p_output.parent.mkdir(parents=True, exist_ok=True)
        with p_output.open(mode="w", encoding="utf_8") as f:
            f.write(target)
            logger.debug(f"'{output}'を出力しました。")


def print_json(target: Any, output: str | Path | None = None) -> None:  # noqa: ANN401
    """
    JSONを出力する。

    Args:
        target: 出力対象のJSON
        output: 出力先。Noneなら標準出力に出力する。

    """
    output_string(json.dumps(target, indent=2, ensure_ascii=False), output)


def print_csv(df: pandas.DataFrame, output: str | Path | None = None, to_csv_kwargs: dict[str, Any] | None = None) -> None:
    if output is not None:
        Path(output).parent.mkdir(parents=True, exist_ok=True)

    path_or_buf = sys.stdout if output is None else str(output)

    kwargs = copy.deepcopy(DEFAULT_CSV_FORMAT)
    if to_csv_kwargs is None:
        df.to_csv(path_or_buf, **kwargs)
    else:
        kwargs.update(to_csv_kwargs)
        df.to_csv(path_or_buf, **kwargs)

    if output is not None:
        logger.debug(f"'{output}'を出力しました。")


def to_filename(s: str) -> str:
    """
    文字列をファイル名に使えるよう変換する。ファイル名に使えない文字は"__"に変換する。
    Args:
        s:

    Returns:
        ファイル名用の文字列

    """
    return re.sub(r'[\\|/|:|?|.|"|<|>|\|]', "__", s)
