# Rather small endpoints that don't deserve their own file.
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.responses import PlainTextResponse
from starlette.responses import Response

import logger
from server.anticheat.anticheat import get_flag_explanation
from server.anticheat.anticheat import log_lastfm_flag
from server.beatmaps.beatmap import Beatmap
from server.beatmaps.helper import add_bmap_rating
from server.beatmaps.helper import user_rated_bmap
from server.constants.lastfm import LastFMFlags
from server.db.redis.handlers.pep import check_online
from server.state import cache
from server.state import services
from server.user.helper import fetch_user_country
from server.user.helper import get_friends
from server.user.helper import log_user_error
from server.user.helper import safe_name
from server.user.helper import update_last_active


RES = "-3"  # This is returned pretty much always.
ERR_PASS = "error: pass"
ERR_MISC = "error: no"


async def lastfm_handler(req: Request) -> Response:
    """Handles the LastFM osu!anticheat endpoint and handles the appropriate action
    based on the result.
    `/web/lastfm.php`
    """

    # Handle authentication.
    username = req.query_params["us"]
    user_id = await cache.name.id_from_safe(safe_name(username))
    if not username:
        return PlainTextResponse(ERR_PASS)

    if not await cache.check_auth(username, req.query_params["ha"]):
        return PlainTextResponse(ERR_PASS)

    if not await check_online(user_id):
        return PlainTextResponse(ERR_MISC)

    # If the first char of this arg is the char "a", a cheat has been flagged.
    bmap_arg: str = req.query_params["b"]
    if bmap_arg.startswith("a"):
        # Now we check the exact cheats they have been flagged for.
        flags = LastFMFlags(int(bmap_arg.removeprefix("a")))
        expl_str = "\n".join(get_flag_explanation(flags))

        logger.info(
            f"User {username} ({user_id}) has been flagged with {flags!r}!\n"
            + expl_str,
        )

        # TODO: Some of these may be frequently false. Look which ones are and autorestrict.
        # For now we just log them.
        await log_lastfm_flag(user_id, flags.value, expl_str)

    # Response is the same to get the client to shut up.
    return PlainTextResponse(RES)


async def getfriends_handler(req: Request) -> Response:
    """Gives the client all of the user IDs of friends.
    Handles `/web/osu-getfriends.php`
    """

    username = req.query_params["u"]
    user_id = await cache.name.id_from_safe(safe_name(username))
    if not username:
        return PlainTextResponse(ERR_PASS)

    if not await cache.check_auth(username, req.query_params["h"]):
        return PlainTextResponse(ERR_PASS)

    friend_id = await get_friends(user_id)
    logger.info(f"Served friends list to {username} ({user_id})")
    return PlainTextResponse("\n".join(map(str, friend_id)))


async def osu_error_handler(req: Request) -> Response:
    """The endpoint to which the client reports any errors that the client
    encounters. Implementing it for potential anticheat use later on.
    DONT TAKE THE DATA FROM THIS ENDPOINT AS COMPLETE TRUTH.
    Handles `/web/osu-error.php`
    """
    post_args = await req.form()

    # Do not take anonymous logs as they are rather useless to us.
    if not (user_id := post_args.get("i")):
        return PlainTextResponse("")

    user_id = int(user_id)
    username = post_args["u"]

    logger.info(
        f"{username} ({user_id}) has experienced a client exception! Logging to the database.",
    )
    await log_user_error(
        user_id,
        post_args.get("traceback", ""),
        post_args["config"],
        post_args["version"],
        post_args["exehash"],
    )

    # TODO: Scan config for malicious entries (maybe cheat client config options) and password auth.
    return PlainTextResponse("")


async def beatmap_rate_handler(req: Request) -> str:
    """Handles the beatmap rating procedure.
    Handles `/web/osu-rate.php`
    """

    bmap_md5 = req.query_params["c"]
    username = req.query_params["u"]
    password = req.query_params["p"]
    rating = req.query_params.get("v")  # Optional

    # Handle user authentication.
    user_id = await cache.name.id_from_safe(safe_name(username))
    if not await cache.password.check_password(user_id, password):
        return PlainTextResponse(ERR_PASS)

    bmap = await Beatmap.from_md5(bmap_md5)
    if not bmap or not bmap.has_leaderboard:
        return PlainTextResponse("not ranked")

    if await user_rated_bmap(user_id, bmap_md5):
        return PlainTextResponse(f"alreadyvoted\n{bmap.rating}")

    # They are casting a new vote.
    if rating:
        rating = int(rating)
        # Check if vote is within the 1-10 range to stop exploits.
        if not 1 <= rating <= 10:
            return PlainTextResponse(ERR_MISC)

        # Add the vote to the database and recalculate the rating.
        new_rating = await add_bmap_rating(user_id, bmap_md5, rating)
        bmap.rating = new_rating

        logger.info(
            f"User {username} ({user_id}) has rated {bmap.song_name} with {rating} "
            f"stars (current average {new_rating}).",
        )
        return PlainTextResponse(f"{new_rating:.2f}")

    return PlainTextResponse("ok")


async def get_seasonals_handler(req: Request) -> Response:
    """Handles `/web/osu-getseasonal.php`, returning a JSON list of seasonal
    images links."""

    logger.info("Serving seasonal backgrounds!")
    seasonal_db = await services.sql.fetch_all(
        "SELECT url FROM seasonal_bg WHERE enabled = 1",
    )

    return JSONResponse([s[0] for s in seasonal_db])


async def bancho_connect(req: Request) -> Response:
    """Handles `/web/bancho_connect.php` as a basic form of login."""

    # TODO: Be able to detect when the bancho is down and make sure the user
    # is treated as online during online checks. Right now i just use this to
    # update the last_active for the user.
    username = req.query_params["u"]
    password = req.query_params["h"]
    user_id = await cache.name.id_from_safe(safe_name(username))

    if not await cache.password.check_password(user_id, password):
        return PlainTextResponse("error: pass")

    # TODO: Maybe some cache refreshes?
    logger.info(f"{username} ({user_id}) has logged in!")
    await update_last_active(user_id)

    # Endpoint responds with the country of the user for cases where
    # bancho is offline and it cannot fetch it from there.
    return PlainTextResponse(await fetch_user_country(user_id))


async def difficulty_rating(req: Request) -> Response:
    """Handles `/difficulty-rating`for accurate bancho SR"""

    # Tell bancho to handle the mess they made.
    return Response(
        "",
        307,
        headers={"Location": "https://osu.ppy.sh/difficulty-rating"},
    )
