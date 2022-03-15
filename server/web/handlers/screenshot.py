# The screenshot related handlers.
import os

from aiopath import AsyncPath as Path
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.responses import Response

import logger
from server import config
from server.db.redis.handlers.pep import check_online
from server.libs.crypt import gen_rand_str
from server.state import cache
from server.state import services
from server.user.helper import safe_name

SS_DELAY = 10  # Seconds per screenshot.
FS_LIMIT = 500_000  # Rosu screenshots don't exceed this.
ERR_RESP = "https://c.ussr.pl/"  # We do a lil trolley.
SS_NAME_LEN = 8

SS_PATH = Path(config.SERVER_DATA_DIR) / "screenshots"


async def is_ratelimit(ip: str) -> bool:
    """Checks if an IP is ratelimited from taking screenshots. If not,
    it establises the limit in Redis."""

    rl_key = "ussr:ss_limit:" + ip
    if await services.redis.get(rl_key):
        return True
    await services.aioredisredis.set(rl_key, 1, expire=SS_DELAY)
    return False


async def upload_image_handler(req: Request) -> Response:
    """Handles screenshot uploads (POST /web/osu-screenshot.php)."""

    post_args = await req.form()

    username = post_args["u"]
    password = post_args["p"]
    if not await cache.check_auth(username, password):
        return PlainTextResponse("no")

    # This is a particularly dangerous endpoint.
    user_id = await cache.name.id_from_safe(safe_name(username))
    if not await check_online(user_id):
        logger.error(
            f"User {username} ({user_id}) tried to upload a screenshot while offline.",
        )
        return PlainTextResponse(ERR_RESP)

    if req.headers.get("user-agent") != "osu!":
        logger.error(
            f"User {username} ({user_id}) tried to upload a screenshot using a bot.",
        )
        return PlainTextResponse(ERR_RESP)

    # LETS style ratelimit.
    if await is_ratelimit(req.headers["x-real-ip"]):
        logger.error(
            f"User {username} ({user_id}) tried to upload a screenshot while ratelimited.",
        )
        return PlainTextResponse(ERR_RESP)

    content = await post_args["ss"].read()

    if content.__sizeof__() > FS_LIMIT:
        return PlainTextResponse(ERR_RESP)

    if content[6:10] in (b"JFIF", b"Exif"):
        ext = "jpeg"
    elif content.startswith(b"\211PNG\r\n\032\n"):
        ext = "png"
    else:
        logger.error(
            f"User {username} ({user_id}) tried to upload unknown extention file.",
        )
        return PlainTextResponse(ERR_RESP)

    # Get a random name for the file that does not overlap.
    while True:
        path = SS_PATH / (f_name := f"{gen_rand_str(SS_NAME_LEN)}.{ext}")
        if not await path.exists():
            break

    # Write file.
    await path.write_bytes(content)

    logger.info(f"User {username} ({user_id}) has uploaded the screenshot {f_name}")
    return PlainTextResponse(f_name)
