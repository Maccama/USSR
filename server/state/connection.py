# Globals related to db connections etc.
import traceback

import aioredis
from api.osuapi import OsuApiManager
from db.mysql.mysql import MySQLPool

from config import config
from logger import error

__slots__ = ("sql", "redis", "oapi")

sql = MySQLPool()
redis = aioredis.Redis(None)
oapi = OsuApiManager()

# Startup tasks.
async def connect_sql() -> bool:
    """Connects the MySQL pool to the server.

    Returns bool corresponding to whether it was successful.
    """

    try:
        await sql.connect(
            host=config.SQL_HOST,
            user=config.SQL_USER,
            database=config.SQL_DB,
            password=config.SQL_PASS,
        )
        return True
    except Exception:
        error(
            f"There has been an exception connecting to the MySQL server!\n"
            + traceback.format_exc(),
        )
        return False


async def connect_redis() -> bool:
    """Connects the Redis pool to the server.

    Returns bool corresponding to whether it was successful.
    """

    try:
        redis._pool_or_conn = await aioredis.create_pool("redis://localhost")
        return True
    except Exception:
        error(
            f"There has been an exception connecting to the Redis database!\n"
            + traceback.format_exc(),
        )
        return False
