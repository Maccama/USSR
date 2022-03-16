import traceback

from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.responses import RedirectResponse

import logger
from server import config
from server.constants.statuses import Status
from server.state import cache
from server.state import services
from server.user.helper import safe_name


# Constants.
PASS_ERR = "error: pass"
URI_SEARCH = f"{config.DIRECT_URL}/search"
BASE_HEADER = (
    "{{SetID}}.osz|{{Artist}}|{{Title}}|{{Creator}}|{{RankedStatus}}|10.0|"
    "{{LastUpdate}}|{{SetID}}|0|{{Video}}|0|0|0|"
)
CHILD_HEADER = "[{DiffName} ⭐{DifficultyRating:.2f}] {{CS: {CS} / OD: {OD} / AR: {AR} / HP: {HP}}}@{Mode}"


def _format_search_response(diffs: dict, bmap: dict):
    """Formats the beatmapset dictionary to full direct response."""
    base_str = BASE_HEADER.format(**bmap, Video=int(bmap["HasVideo"]))
    return base_str + ",".join(CHILD_HEADER.format(**diff) for diff in diffs)


async def download_map(req: Request):
    """Handles osu!direct map download route"""
    map_id = req.path_params["map_id"]

    beatmap_id = int(map_id.removesuffix("n"))
    no_vid = "?n" if "n" == map_id[-1] else ""
    return RedirectResponse(
        f"{config.DIRECT_URL}/d/{beatmap_id}{no_vid}",
        status_code=302,
    )


async def get_set_handler(req: Request) -> None:
    """Handles a osu!direct pop-up link response."""
    nick = req.query_params.get("u", "")
    password = req.query_params.get("h", "")
    user_id = await cache.name.id_from_safe(safe_name(nick))

    # Handle Auth..
    if not await cache.password.check_password(user_id, password) or not nick:
        return PlainTextResponse(PASS_ERR)

    if "b" in req.query_params:
        bmap_id = req.query_params.get("b")
        async with services.web.get(f"{config.DIRECT_URL}/b/{bmap_id}") as resp:
            res = await resp.json()

        if (not res) or resp.status == 404:
            return PlainTextResponse("0")

        bmap_set = res["ParentSetID"]
    elif "s" in req.query_params:
        bmap_set = req.query_params.get("s")

    async with services.web.get(f"{config.DIRECT_URL}/s/{bmap_set}") as resp:
        res = await resp.json()

    if (not res) or resp.status == 404:
        return PlainTextResponse("0")

    return PlainTextResponse(_format_search_response({}, res))


async def direct_get_handler(req: Request) -> None:
    """Handles osu!direct panels response."""
    # Get all keys.
    nickname = req.query_params.get("u", "")
    password = req.query_params.get("h", "")
    status = Status.from_direct(int(req.query_params.get("r", "0")))
    query = req.query_params.get("q", "").replace("+", " ")
    offset = int(req.query_params.get("p", "0")) * 100
    mode = int(req.query_params.get("m", "-1"))
    user_id = await cache.name.id_from_safe(safe_name(nickname))

    # Handle Auth..
    if not await cache.password.check_password(user_id, password) or not nickname:
        return PlainTextResponse(PASS_ERR)

    mirror_params = {"amount": 100, "offset": offset}
    if status is not None:
        mirror_params["status"] = status.to_direct()
    if query not in ("Newest", "Top Rated", "Most Played"):
        mirror_params["query"] = query
    if mode != -1:
        mirror_params["mode"] = mode

    logger.info(f"{nickname} requested osu!direct search with query: {query or 'None'}")

    try:
        async with services.web.get(URI_SEARCH, mirror_params) as resp:
            res = await resp.json()
    except Exception:
        logger.error(f"Error with direct search: {traceback.format_exc()}")
        return PlainTextResponse(
            "-1\nAn error has occured when fetching direct listing!",
        )

    if (not res) or resp.status == 404:
        return PlainTextResponse("0")

    response = [f"{'101' if len(res) == 100 else len(res)}"]
    for bmap in res:
        if "ChildrenBeatmaps" not in bmap:
            continue

        sorted_diffs = sorted(
            bmap["ChildrenBeatmaps"],
            key=lambda b: b["DifficultyRating"],
        )
        response.append(_format_search_response(sorted_diffs, bmap))

    return PlainTextResponse("\n".join(response))
