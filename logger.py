import sys
import time
from enum import IntEnum
from functools import cache

from server import config

__all__ = (
    "Ansi",
    "info",
    "error",
    "warning",
    "debug",
    "check_log_file",
    "ensure_log_file",
    "write_log_file",
)

# https://github.com/cmyui/cmyui_pkg/blob/master/cmyui/logging.py#L20-L45
class Ansi(IntEnum):
    BLACK = 30
    RED = 31
    GREEN = 32
    YELLOW = 33
    BLUE = 34
    MAGENTA = 35
    CYAN = 36
    WHITE = 37

    GRAY = 90
    LRED = 91
    LGREEN = 92
    LYELLOW = 93
    LBLUE = 94
    LMAGENTA = 95
    LCYAN = 96
    LWHITE = 97

    RESET = 0

    @cache
    def __repr__(self) -> str:
        return f"\x1b[{self.value}m"


def get_timestamp() -> int:
    """Returns the current fromatted date in the format."""

    # D/MM/YYYY HH:MM:SS, 04/05/2021 04:20:01

    return time.strftime("%d-%m-%Y %H:%M:%S", time.localtime())


def _log(content: str, action: str, colour: Ansi = Ansi.WHITE):
    sys.stdout.write(  # This is mess but it forms in really cool log.
        f"\x1b[90m[{get_timestamp()} - {colour!r}\033[1"
        f"m{action}\033[0m\x1b[90m]: \x1b[94m{content}\x1b[0m\n",
    )


def info(text: str):
    _log(text, "INFO", Ansi.GREEN)


def error(text: str):
    _log(text, "ERROR", Ansi.RED)


def warning(text: str):
    _log(text, "WARNING", Ansi.BLUE)


def debug(text: str):
    if config.DEBUG:
        _log(text, "DEBUG", Ansi.WHITE)


def write_log_file(msg: str, timestamp: bool = True):
    """Appends a message to the log file."""
    text = ""

    with open(f"{config.SERVER_DATA_DIR}/err.log", "a+") as f:
        if timestamp:
            text += f"[{get_timestamp()}] "
        text += msg + "\n"
        f.write(text)
