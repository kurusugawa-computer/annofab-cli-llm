from __future__ import annotations

import argparse
import copy
import inspect
import logging
import sys

from loguru import logger

import acl
import acl.common.cli
from acl.command.validate_attribute_value import add_parser as add_parser_for_validate_attribute_value
from acl.common.xdg_util import get_logs_root_dir


class InterceptHandler(logging.Handler):
    """
    標準のloggingメッセージをloguruに流すためのクラス
    以下のコードをそのまま流用しました。
    https://github.com/Delgan/loguru?tab=readme-ov-file#entirely-compatible-with-standard-logging
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists.
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_loguru(*, is_verbose: bool) -> None:
    """
    loguruの設定を行います。

    Args:
        is_verbose: 詳細なログを出力するか
    """

    logger.remove()
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO, force=True)

    if is_verbose:
        # aclモジュール用: DEBUG以上
        level_per_module = {
            "": "INFO",
            "acl": "DEBUG",
        }
    else:
        level_per_module = {
            "": "INFO",
        }

    logger.add(sys.stderr, diagnose=False, filter=level_per_module)  # type: ignore[arg-type]
    logger.add(get_logs_root_dir() / "annofab-cli-llm.log", rotation="1 day", diagnose=False, filter=level_per_module)  # type: ignore[arg-type]


def mask_argv(argv: list[str]) -> list[str]:
    """
    `argv`にセンシティブな情報が含まれている場合は、`***`に置き換える。
    """
    tmp_argv = copy.deepcopy(argv)
    for masked_option in ["--annofab_password", "--annofab_pat"]:
        try:
            index = tmp_argv.index(masked_option)
            tmp_argv[index + 1] = "***"
        except ValueError:
            continue
    return tmp_argv


def main(arguments: list[str] | None = None) -> None:
    """
    annofabcliコマンドのメイン処理
    注意： `deprecated`なツールは、サブコマンド化しない。

    Args:
        arguments: コマンドライン引数。テストコード用

    """
    parser = create_parser()

    if arguments is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(arguments)

    if hasattr(args, "func"):
        try:
            configure_loguru(is_verbose=args.verbose)
            argv = sys.argv
            if arguments is not None:
                argv = ["annofabcli", *list(arguments)]
            logger.info(f"annofabcli-llmを実行します。 :: argv={mask_argv(argv)}")
            args.func(args)
        except Exception as e:
            logger.exception(e)
            raise e  # noqa: TRY201

    else:
        # 未知のサブコマンドの場合はヘルプを表示
        args.command_help()


def create_parser(subparsers: argparse._SubParsersAction|None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLMとannofab-cliを組み合わせたツールです。", formatter_class=acl.common.cli.PrettyHelpFormatter)
    parser.add_argument("--version", action="version", version=f"annofabcli-llm {acl.__version__}")
    parser.set_defaults(command_help=parser.print_help)

    subparsers = parser.add_subparsers(dest="command_name")

    add_parser_for_validate_attribute_value(subparsers)

    return parser


if __name__ == "__main__":
    main()
