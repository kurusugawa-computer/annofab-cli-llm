import datetime
import os
import uuid
from pathlib import Path

from acl.common.constants import APPLICATION_NAME


def get_xdg_cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))


def get_xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def get_cache_dir() -> Path:
    return get_xdg_cache_home() / APPLICATION_NAME


def get_config_dir() -> Path:
    return get_xdg_config_home() / APPLICATION_NAME


def get_temp_root_dir() -> Path:
    return get_cache_dir() / "temp"


def get_logs_root_dir() -> Path:
    return get_cache_dir() / "logs"


def create_command_temp_dir(command_name: str) -> Path:
    """
    コマンド名と現在の日時を含む一時ディレクトリを作成して、そのパスを返します。
    """
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")  # noqa: DTZ005
    short_id = uuid.uuid4().hex[:6]
    dir_name = f"{command_name}_{now_str}_{short_id}"

    temp_dir = get_temp_root_dir() / dir_name
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir
