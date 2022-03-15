# These are the pubsub events from the RealistikOsu stack. It is recommended
# to implement these into yours as they do control pretty core functionality.
# This is just to ensure compatibility with the popular variants.
from server.state import cache


async def clan_update_pubsub(msg: bytes) -> None:
    """Handles the pubsub handler for `rosu:clan_update`.

    Refreshes the state of a user's clan in the cache.
    """

    await cache.clan.cache_individual(int(msg.decode()))
