from __future__ import annotations

import logger
from server.caches.bcrypt import BCryptCache
from server.caches.clan import ClanCache
from server.caches.lru_cache import Cache
from server.caches.priv import PrivilegeCache
from server.caches.username import UsernameCache
from server.constants.statuses import Status
from server.scores.achievement import Achievement
from server.state import services

# Specialised Caches
name = UsernameCache()
priv = PrivilegeCache()
clan = ClanCache()
password = BCryptCache()
achievements: list[Achievement] = []

# General Caches.
beatmaps = Cache(cache_length=120, cache_limit=1000)
leaderboards = Cache(cache_length=240, cache_limit=100_000)

# Cache for statuses that require an api call to get. md5: status
no_check_md5s: dict[str, Status] = {}

# Stats cache. Key = tuple[CustomModes, Mode, user_id]
stats_cache = Cache(cache_length=240, cache_limit=300)


def add_nocheck_md5(md5: str, st: "Status") -> None:
    """Adds a md5 to the no_check_md5s cache.

    Args:
        md5 (str): The md5 to add to the cache.
    """

    no_check_md5s[md5] = st


async def initialise_cache() -> bool:
    """Initialises all caches, efficiently bulk pre-loading them."""

    # Doing this way for cool logging.
    await name.full_load()
    logger.info(f"Successfully cached {len(name)} usernames!")

    await priv.full_load()
    logger.info(f"Successfully cached {len(priv)} privileges!")

    await clan.full_load()
    logger.info(f"Successfully cached {len(clan)} clans!")

    await achievements_load()
    logger.info(f"Successfully cached {len(achievements)} achievements!")

    return True


async def achievements_load() -> bool:
    """Initialises all achievements into the cache."""

    achs = await services.sql.fetch_all("SELECT * FROM ussr_achievements")
    for ach in achs:
        condition = eval(f"lambda score, mode_vn, stats: {ach[4]}")
        achievements.append(
            Achievement(
                id=ach[0],
                file=ach[1],
                name=ach[2],
                desc=ach[3],
                cond=condition,
            ),
        )

    return True


# Before this, auth required a LOT of boilerplate code.
async def check_auth(n: str, pw_md5: str) -> bool:
    """Handles authentication for a name + pass md5 auth."""

    s_name = n.rstrip().lower().replace(" ", "_")

    # Get user_id from cache.
    user_id = await name.id_from_safe(s_name)
    return await password.check_password(user_id, pw_md5)
