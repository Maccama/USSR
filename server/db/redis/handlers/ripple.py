# Support for ripple's pubsub handlers. These are featured in **all** ripple
# based servers.
import orjson

import logger
from server.state import cache


async def _update_singular(md5: str) -> None:
    """Updates a singular map using data from the osu API."""
    ...


async def beatmap_update_pubsub(data: bytes) -> None:
    """Handler for the pubsub event `lets:beatmap_updates`.

    Forces a beatmap to be updated straight form the osu!api.

    Message:
        Takes JSON formatted data of either of these structures.
        For single map updates:
        ```json
        {
            "id": int,
        }
        ```
        For entire set updates:
        ```json
        {
            "set_id": int
        }
        ```
    """

    # Parse JSON formatted data.
    j_data = orjson.loads(data)
    ...


async def username_change_pubsub(data: bytes):
    """
    Handles the Redis pubsub event `peppy:change_username`.
    It handles the update of the username cache.
    """

    # Parse JSON formatted data.
    j_data = orjson.loads(data)

    user_id = int(j_data["userID"])
    new_username = j_data["newUsername"]

    await cache.name.load_from_id(user_id)

    for leaderboard in cache.leaderboards.get_all_items():
        if leaderboard.user_has_score(user_id):
            leaderboard.change_username(user_id, new_username)

    logger.info(f"Handled username change for user ID {user_id} -> {new_username}")


async def update_cached_privileges_pubsub(data: bytes):
    """
    Handles the Redis pubsub event `peppy:update_cached_stats`.
    It refreshes the cached privileges for a user.
    """

    user_id = int(data.decode())
    await cache.priv.load_singular(user_id)


async def change_pass_pubsub(data: bytes):
    """
    Handles the Redis pubsub event `peppy:change_pass`.
    It refreshes the cached password for the user.
    """

    j_data = orjson.loads(data)
    user_id = int(j_data["user_id"])

    cache.password.drop_cache_individual(user_id)


async def ban_reload_pubsub(data: bytes):
    """
    Handles the Redis pubsub event `peppy:ban`.
    It reloads the privileges stored in the cache.
    """

    user_id = int(data.decode())
    await cache.priv.load_singular(user_id)

    # If they have been restricted, we clear all leaderboard with them in.
    if (await cache.priv.get_privilege(user_id)).is_not_allowed:
        for leaderboard in cache.leaderboards.get_all_items():
            await leaderboard.refresh()
