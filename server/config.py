import sys

from starlette.config import Config
from starlette.datastructures import CommaSeparatedStrings
from starlette.datastructures import Secret

config = Config("ussr.env")

DEBUG = "debug" in map(str.lower, sys.argv)
MYSQL_DSN: Secret = config("MYSQL_DSN", cast=Secret)
REDIS_DSN: Secret = config("REDIS_DSN", default="redis://localhost", cast=Secret)

SERVER_PORT: int = config("SERVER_PORT", default=2137, cast=int)
SERVER_DATA_DIR: str = config("SERVER_DATA_DIR")
SERVER_DOMAIN: str = config("SERVER_DOMAIN")
SERVER_NAME: str = config("SERVER_NAME")
SERVER_VERIFIED_BADGE: int = config("SERVER_VERIFIED_BADGE", cast=int)

BANCHO_API_KEYS_POOL: list[str] = config(
    "BANCHO_API_KEYS_POOL",
    cast=CommaSeparatedStrings,
)
DIRECT_URL: str = config("DIRECT_URL")
CUSTOM_CLIENTS: bool = config("CUSTOM_CLIENTS", cast=bool)

DISCORD_FIRST_PLACE_WEBHOOK: str = config("DISCORD_FIRST_PLACE_WEBHOOK")
DISCORD_ADMIN_HOOK_WEBHOOK: str = config("DISCORD_ADMIN_HOOK_WEBHOOK")

# for pp caps in all modes.
PP_CAP_VN: list[int] = [
    int(pp_val)
    for pp_val in config(
        "PP_CAP_VN",
        cast=CommaSeparatedStrings,
    )
]
assert (
    len(PP_CAP_VN) == 4
), f"Not enough values in 'PP_CAP_VN' field in config, expected 4, got {len(PP_CAP_VN)}"

PP_CAP_RX: list[int] = [
    int(pp_val)
    for pp_val in config(
        "PP_CAP_RX",
        cast=CommaSeparatedStrings,
    )
]
assert (
    len(PP_CAP_RX) == 3
), f"Not enough values in 'PP_CAP_RX' field in config, expected 3, got {len(PP_CAP_VN)}"

PP_CAP_AP: list[int] = [config("PP_CAP_AP", cast=int)]
assert (
    len(PP_CAP_AP) == 1
), f"Not enough values in 'PP_CAP_AP' field in config, expected 1, got {len(PP_CAP_VN)}"
