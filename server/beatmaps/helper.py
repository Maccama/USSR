from typing import Optional

from aiopath import AsyncPath as Path

import logger
from server import config
from server.state import services

DIR_MAPS = Path(config.SERVER_DATA_DIR) / "maps"


async def bmap_md5_from_id(bmap_id: int) -> Optional[str]:
    """Attempts to fetch the beatmap MD5 hash for a map stored in the database.

    Note:
        If the beatmap is not stored in the database, `None` is returned.
        No osu!API calls are performed here, just an SQL query.

    Args:
        bmap_id (int): The beatmap ID for the map.

    Returns:
        The MD5 hash for the beatmap `.osu` file if found in the MySQL
            database.
        Else `None`.
    """

    return await services.sql.fetch_val(
        "SELECT beatmap_md5 FROM beatmaps WHERE beatmap_id = :bid LIMIT 1",
        {"bid": bmap_id},
    )


async def bmap_get_set_md5s(set_id: int) -> tuple[str]:
    """Fetches all available MD5 hashes for an osu beatmap set in the
    database.

    Note:
        No osu!API calls are performed here, just an SQL query.
        Can return empty tuple if none are found.

    Args:
        set_id (int): The osu! beatmap set ID.

    Returns:
        `tuple` of MD5 hashes.
    """

    return await services.sql.fetch_all(
        "SELECT beatmap_md5 FROM beatmaps WHERE beatmapset_id = :bsetid",
        {"bsetid": set_id},
    )


OSU_DL_DIR = "http://old.ppy.sh/osu/"


async def fetch_osu_file(bmap_id: int) -> str:
    """Downloads the `.osu` beatmap file to the beatmap storage directory.
    If the file already exists in the given location, nothing is done.

    Returns path to the osu file.
    """

    path = DIR_MAPS / f"{bmap_id}.osu"
    if await path.exists():
        logger.debug(f"osu beatmap file for beatmap {bmap_id} is already cached!")
        return path

    logger.debug(f"Downloading `.osu` file for beatmap {bmap_id} to {path} ...")
    async with services.web.get(OSU_DL_DIR + str(bmap_id)) as resp:
        m_str = await resp.read()

    if not m_str:
        return logger.error(f"Invalid beatmap .osu response! PP calculation will fail!")

    # Write to file.
    await path.write_text(m_str)
    logger.debug(f"Beatmap cached to {path}!")
    return path


async def delete_osu_file(bmap_id: int):
    """Ensures an `.osu` beatmap file is completely deleted from cache."""

    path = DIR_MAPS / f"{bmap_id}.osu"

    try:
        await path.unlink()
    except Exception:
        pass


async def user_rated_bmap(user_id: int, bmap_md5: str) -> bool:
    """Check if a user has already submitted a rating for a beatmap.

    Args:
        user_id (int): The user ID.
        bmap_md5 (str): The beatmap MD5 hash.

    Returns:
        `True` if the user has already submitted a rating for the beatmap.
        `False` otherwise.
    """

    exists_db = await services.sql.fetch_val(
        "SELECT 1 FROM beatmaps_rating WHERE user_id = :id AND beatmap_md5 = :md5",
        {"id": user_id, "md5": bmap_md5},
    )

    return bool(exists_db)


async def add_bmap_rating(user_id: int, bmap_md5: str, rating: int) -> float:
    """Adds a new beatmap rating from a user and recalculates the new average
    rating, returning it.

    Note:
        This function does not update the rating values of any of the cached
        beatmap objects.

    Args:
        user_id (int): The user ID.
        rating (int): The rating to add.

    Returns:
        The new average rating as float.
    """

    await services.sql.execute(
        "INSERT INTO beatmaps_rating (user_id, rating, beatmap_md5) VALUES (:id, :rating, :md5)",
        {"id": user_id, "rating": rating, "md5": bmap_md5},
    )

    new_rating = await services.sql.fetch_val(
        "SELECT AVG(rating) FROM beatmaps_rating WHERE user_id = :user_id AND beatmap_md5 = :md5",
        {"user_id": user_id, "md5": bmap_md5},
    )

    # Set new value in the beatmaps table.
    await services.sql.execute(
        "UPDATE beatmaps SET rating = :rating WHERE beatmap_md5 = :md5 LIMIT 1",
        {"rating": new_rating, "md5": bmap_md5},
    )

    return new_rating
