from typing import Any


def normalize_label_color(color: Any) -> str | None:  # noqa: ANN401
    """
    Annofab APIのラベル色を ``#RRGGBB`` 形式に正規化します。

    Args:
        color: Annofab APIのラベル色

    Returns:
        ``#RRGGBB`` 形式の色。色が未設定または未対応形式の場合はNone
    """
    if color is None:
        return None
    if isinstance(color, str):
        return color
    if not isinstance(color, dict):
        return None

    red = color["red"]
    green = color["green"]
    blue = color["blue"]
    if isinstance(red, int) and isinstance(green, int) and isinstance(blue, int):
        return f"#{red:02X}{green:02X}{blue:02X}"
    return None


def keybind_to_text(keybind: list[dict[str, Any]]) -> str:
    """
    以下の構造を持つkeybindを、人が読める形式に変換します。
    {"alt": False, "code": "Numpad1", "ctrl": False, "shift": False}
    """

    def to_str(one_keybind: dict[str, Any]) -> str:
        keys = []
        if one_keybind.get("ctrl", False):
            keys.append("Ctrl")
        if one_keybind.get("alt", False):
            keys.append("Alt")
        if one_keybind.get("shift", False):
            keys.append("Shift")
        code = one_keybind.get("code", "")
        assert code is not None

        keys.append(f"{code}")
        return "+".join(keys)

    tmp_list = [to_str(elm) for elm in keybind]
    return ",".join(tmp_list)
