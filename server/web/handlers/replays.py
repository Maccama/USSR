from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.responses import Response

import logger
from server.constants.c_modes import CustomModes
from server.constants.modes import Mode
from server.scores.replays.helper import build_full_replay
from server.scores.replays.helper import read_replay
from server.scores.score import Score
from server.state import services
from server.user.helper import incr_replays_watched

BASE_QUERY = "SELECT play_mode, userid FROM {} WHERE id = :id LIMIT 1"
ERR_NOT_FOUND = "error: no"


async def get_replay_web_handler(req: Request) -> Response:
    """Handles the in-game replay downloads, incrementing replays watched
    appropeately.
    URL: `/web/osu-getreplay.php`
    """

    # Grab our data. TODO: Maybe auth?
    score_id = int(req.query_params["c"])
    c_mode = CustomModes.from_score_id(score_id)

    score_data_db = await services.sql.fetch_one(
        BASE_QUERY.format(c_mode.db_table),
        {"id": score_id},
    )

    # Handle replay not found.
    if not score_data_db:
        logger.error(f"Requested non-existent replay score {score_id}")
        return PlainTextResponse(ERR_NOT_FOUND)

    play_mode, user_id = score_data_db
    mode = Mode(play_mode)

    rp = await read_replay(score_id, c_mode)
    if not rp:
        logger.error(f"Requested non-existent replay file {score_id}.osr")
        return PlainTextResponse(ERR_NOT_FOUND)

    # Increment their stats.
    await incr_replays_watched(user_id, mode)

    logger.info(f"Successfully served replay {score_id}.osr")
    return Response(rp)


async def get_full_replay_handler(req: Request) -> Response:
    """Retuns a fully built replay with headers. Used for web."""

    score_id = req.path_params["score_id"]
    c_mode = CustomModes.from_score_id(score_id)
    score = await Score.from_db(score_id, c_mode)

    if not score:
        return PlainTextResponse("Score not found!", status_code=404)

    rp = await build_full_replay(score)
    if not rp:
        return PlainTextResponse("Replay not found!", status_code=404)

    filename = f"{score.username} - {score.bmap.song_name} ({score.id}).osr"

    logger.info(f"Served compiled replay {score_id}!")

    return Response(
        bytes(rp.buffer),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
