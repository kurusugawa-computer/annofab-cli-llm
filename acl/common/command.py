def mask_command_options(command: list[str], masked_options: set[str]) -> list[str]:
    """
    コマンド引数に含まれるセンシティブな値をマスクします。

    Args:
        command: コマンド引数
        masked_options: 値をマスクするオプション名の集合

    Returns:
        センシティブな値をマスクしたコマンド引数
    """
    masked_command = command.copy()
    for index, value in enumerate(command[:-1]):
        if value in masked_options:
            masked_command[index + 1] = "***"
    return masked_command
