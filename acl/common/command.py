DEFAULT_MASKED_COMMAND_OPTIONS = {"--annofab_pat"}
"""デフォルトで値をマスクするコマンドラインオプションです。"""


def mask_command_options(command: list[str], masked_options: set[str] | None = None) -> list[str]:
    """
    コマンド引数に含まれるセンシティブな値をマスクします。

    Args:
        command: コマンド引数
        masked_options: 値をマスクするオプション名の集合。未指定の場合はデフォルトのマスク対象を使用します。

    Returns:
        センシティブな値をマスクしたコマンド引数
    """
    actual_masked_options = DEFAULT_MASKED_COMMAND_OPTIONS if masked_options is None else masked_options
    masked_command = command.copy()
    for index, value in enumerate(command[:-1]):
        if value in actual_masked_options:
            masked_command[index + 1] = "***"
    return masked_command
