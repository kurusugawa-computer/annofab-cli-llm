"""
Command Line Interfaceの共通部分
"""

import argparse
import logging
from pathlib import Path

from more_itertools import first_true

from acl.common.utils import read_lines_except_blank_line

logger = logging.getLogger(__name__)

DEFAULT_LLM_MODEL = "openai/o4-mini"


class ExitCode:
    """
    BashのExit Codes
    https://tldp.org/LDP/abs/html/exitcodes.html
    """

    GENERAL_ERROR = 1
    """一般的なエラー全般"""
    MISUSE_OF_COMMAND = 2
    """コマンドの誤用"""


def add_parser(
    subparsers: argparse._SubParsersAction | None,
    command_name: str,
    command_help: str,
    description: str | None = None,
    epilog: str | None = None,
) -> argparse.ArgumentParser:
    """
    サブコマンド用にparserを追加する

    Args:
        subparsers:
        command_name:
        command_help: 1階層上のコマンドヘルプに表示される コマンドの説明（簡易的な説明）
        description: ヘルプ出力に表示される説明（詳細な説明）。未指定の場合は command_help と同じ値です。
        is_subcommand: サブコマンドかどうか. `annofabcli project`はコマンド、`annofabcli project list`はサブコマンドとみなす。
        epilog: ヘルプ出力後に表示される内容。デフォルトはNoneです。

    Returns:
        サブコマンドのparser

    """
    GLOBAL_OPTIONAL_ARGUMENTS_TITLE = "global optional arguments"  # noqa: N806

    def create_parent_parser() -> argparse.ArgumentParser:
        """
        共通の引数セットを生成する。
        """
        parent_parser = argparse.ArgumentParser(add_help=False, formatter_class=PrettyHelpFormatter)
        group = parent_parser.add_argument_group(GLOBAL_OPTIONAL_ARGUMENTS_TITLE)

        group.add_argument(
            "-m", "--model", default=DEFAULT_LLM_MODEL, help="使用するLLMのモデルです。デフォルトは'openai/o4-mini'です。使用できるモデルは https://docs.litellm.ai/docs/providers を参照してください。"
        )
        group.add_argument("--verbose", action="store_true", help="詳細なログを出力します。")
        group.add_argument("--yes", action="store_true", help="確認メッセージに対して常に'yes'と回答したとみなします。確認メッセージを表示されません。")
        group.add_argument("--annofab_pat", type=str, help="AnnofabのPersonal Access Token")

        return parent_parser

    if subparsers is None:
        subparsers = argparse.ArgumentParser(formatter_class=PrettyHelpFormatter).add_subparsers()

    parents = [create_parent_parser()]
    parser = subparsers.add_parser(
        command_name,
        parents=parents,
        description=description if description is not None else command_help,
        help=command_help,
        epilog=epilog,
        formatter_class=PrettyHelpFormatter,
    )
    parser.set_defaults(command_help=parser.print_help)

    # 引数グループに"global optional group"がある場合は、"--help"オプションをデフォルトの"optional"グループから、"global optional arguments"グループに移動する
    # https://ja.stackoverflow.com/a/57313/19524
    global_optional_argument_group = first_true(parser._action_groups, pred=lambda e: e.title == GLOBAL_OPTIONAL_ARGUMENTS_TITLE)  # noqa: SLF001
    if global_optional_argument_group is not None:
        # optional グループの 0番目が help なので取り出す
        help_action = parser._optionals._group_actions.pop(0)  # noqa: SLF001
        assert help_action.dest == "help"
        # global optional group の 先頭にhelpを追加
        global_optional_argument_group._group_actions.insert(0, help_action)  # noqa: SLF001
    return parser


def prompt_yesno(msg: str) -> bool:
    """
    標準入力で yes, noを選択できるようにする。
    Args:
        msg: 確認メッセージ

    Returns:
        True: Yes, False: No

    """
    while True:
        choice = input(f"{msg} [y/N] : ")
        if choice == "y":
            return True

        elif choice == "N":
            return False


def prompt_yesnoall(msg: str) -> tuple[bool, bool]:
    """
    標準入力で yes, no, all(すべてyes)を選択できるようにする。
    Args:
        msg: 確認メッセージ

    Returns:
        Tuple[yesno, all_flag]. yesno:Trueならyes. all_flag: Trueならall.

    """
    while True:
        choice = input(f"{msg} [y/N/ALL] : ")
        if choice == "y":  # noqa: SIM116
            return True, False

        elif choice == "N":
            return False, False

        elif choice == "ALL":
            return True, True


class PrettyHelpFormatter(argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
    def _format_action(self, action: argparse.Action) -> str:
        # ヘルプメッセージを見やすくするために、引数と引数の説明の間に空行を入れる
        # https://qiita.com/yuji38kwmt/items/c7c4d487e3188afd781e 参照
        return super()._format_action(action) + "\n"

    def _get_help_string(self, action):  # noqa: ANN001, ANN202
        # 必須な引数には、引数の説明の後ろに"(required)"を付ける
        help = action.help  # noqa: A001 # pylint: disable=redefined-builtin
        if action.required:
            help += " (required)"  # noqa: A001

        # 不要なデフォルト値（--debug や オプショナルな引数）を表示させないようにする
        # super()._get_help_string の中身を、そのまま持ってきた。
        # https://qiita.com/yuji38kwmt/items/c7c4d487e3188afd781e 参照
        if "%(default)" not in action.help:
            if action.default is not argparse.SUPPRESS:
                defaulting_nargs = [argparse.OPTIONAL, argparse.ZERO_OR_MORE]
                if action.option_strings or action.nargs in defaulting_nargs:
                    # 以下の条件だけ、annofabcli独自の設定
                    if action.default is not None and not action.const:
                        help += " (default: %(default)s)"  # noqa: A001
        return help


def read_at_file(value: str) -> str:
    """
    引数の値が`@`で始まる場合、ファイルパスとして解釈し、そのファイルの内容を文字列として返す。
    """
    if value.startswith("@"):
        file_path = Path(value[1:])
        return file_path.read_text(encoding="utf-8")
    return value


def read_lines_at_file(value_list: list[str]) -> list[str]:
    """
    引数`value_list`のlengthが1で、`@`から始まる場合はファイルパスと解釈して、行のlistを返します。
    そうでなければ、`value_list`をそのまま返します。

    """
    if len(value_list) == 1:
        value = value_list[0]
        if value.startswith("@"):
            file_path = Path(value[1:])
            return read_lines_except_blank_line(file_path)
        else:
            return [value]
    else:
        return value_list
