import traceback

import aiohttp
import aioredis
import databases
import orjson

import logger
from server import config
from server.api.osuapi import OsuApiManager

__slots__ = ("sql", "redis", "oapi")

sql = databases.Database(str(config.MYSQL_DSN))
redis = aioredis.Redis(None)
oapi = OsuApiManager()
web: aiohttp.ClientSession


async def create_connections() -> bool:
    """Connects the Redis pool and mysql to the server.

    Returns bool corresponding to whether it was successful.
    """
    global web

    web = aiohttp.ClientSession(json_serialize=orjson.dumps)
    try:
        await sql.connect()
    except Exception:
        logger.error(
            f"There has been an exception connecting to the MySQL database!\n"
            + traceback.format_exc(),
        )
        return False

    try:
        redis._pool_or_conn = await aioredis.create_pool("redis://localhost")
        return True
    except Exception:
        logger.error(
            f"There has been an exception connecting to the Redis database!\n"
            + traceback.format_exc(),
        )
        return False
