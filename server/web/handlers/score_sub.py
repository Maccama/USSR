from __future__ import annotations

from copy import copy
from datetime import datetime

from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.responses import Response

import logger
from server import config
from server.anticheat.anticheat import surpassed_cap_restrict
from server.api.discord import log_first_place
from server.constants.actions import Actions
from server.constants.complete import Completed
from server.constants.privileges import Privileges
from server.constants.statuses import Status
from server.db.redis.handlers.pep import check_online
from server.db.redis.handlers.pep import notify_new_score
from server.db.redis.handlers.pep import stats_refresh
from server.scores.leaderboards.leaderboard import GlobalLeaderboard
from server.scores.replays.helper import write_replay
from server.scores.score import Score
from server.state import cache
from server.state import services
from server.user.helper import edit_user
from server.user.helper import get_achievements
from server.user.helper import unlock_achievement
from server.user.helper import update_country_lb_pos
from server.user.helper import update_lb_pos
from server.user.stats import Stats


def _pair_panel(name: str, b: str, a: str) -> str:
    """Creates a pair panel string used in score submit ranking panel.

    Args:
        name (str): The name of the panel.
        b (str): The before value displayed.
        a (str): The after value displayed.
    """

    return f"{name}Before:{b}|{name}After:{a}"


async def score_submit_handler(req: Request) -> Response:
    """Handles the score submit endpoint for osu!"""

    post_args = await req.form()

    # TODO: ALLOW ALL SCORES TO SUBMIT BUT NOT SCOREV2
    s = await Score.from_score_sub(post_args)

    # Check if theyre online, if not, force the client to wait to log in.
    if not await check_online(s.user_id):
        return PlainTextResponse("")

    privs = await cache.priv.get_privilege(s.user_id)
    if not s:
        logger.error("Could not perform score sub! Check messages above!")
        return PlainTextResponse("error: no")

    if not s.bmap:
        logger.error("Score sub failed due to no beatmap being attached.")
        return PlainTextResponse("error: no")

    if not s.mods.rankable():
        logger.info("Score not submitted due to unrankable mod combo.")
        return PlainTextResponse("error: no")

    if not await cache.password.check_password(s.user_id, post_args["pass"]):
        return PlainTextResponse("error: pass")

    # Anticheat checks.
    if not req.headers.get("Token") and not config.CUSTOM_CLIENTS:
        await edit_user(Actions.RESTRICT, s.user_id, "Tampering with osu!auth")
        # return PlainTextResponse("error: ban")

    if req.headers.get("User-Agent") != "osu!":
        await edit_user(Actions.RESTRICT, s.user_id, "Score submitter.")
        # return PlainTextResponse("error: ban")

    if s.mods.conflict():
        await edit_user(
            Actions.RESTRICT,
            s.user_id,
            "Illegal mod combo (score submitter).",
        )
        # return PlainTextResponse("error: ban")

    # TODO: version check.
    dupe_check = (
        await services.sql.fetchcol(  # Try to fetch as much similar score as we can.
            f"SELECT 1 FROM {s.c_mode.db_table} WHERE "
            "userid = :id AND beatmap_md5 = :md5 AND score = :score "
            "AND play_mode = :mode AND mods = :mods LIMIT 1",
            {
                "id": s.user_id,
                "md5": s.bmap.md5,
                "score": s.score,
                "mode": s.mode.value,
                "mods": s.mods.value,
            },
        )
    )

    if dupe_check:
        # Duplicate, just return error: no.
        logger.warning("Duplicate score has been spotted and handled!")
        return PlainTextResponse("error: no")

    # Stats stuff
    stats = await Stats.from_id(s.user_id, s.mode, s.c_mode)
    old_stats = copy(stats)

    # Fetch old score to compare.
    prev_score = None

    if s.passed:
        logger.debug("Fetching previous best to compare.")
        prev_id = await services.sql.fetch_val(
            f"SELECT id FROM {stats.c_mode.db_table} WHERE userid = :id AND "
            "beatmap_md5 = :md5 AND completed = 3 AND play_mode = :mode LIMIT 1",
            {"id": s.user_id, "md5": s.bmap.md5, "mode": s.mode.value},
        )

        prev_score = await Score.from_db(prev_id, s.c_mode) if prev_id else None

    logger.debug("Submitting score...")
    await s.submit(restricted=privs.is_not_allowed)

    if (
        s.completed is Completed.BEST
        and s.bmap.has_leaderboard
        and not privs.is_not_allowed
    ):
        lb = GlobalLeaderboard.from_cache(s.bmap.md5, s.c_mode, s.mode)
        if lb is not None:
            lb.insert_user_score(s)

    logger.debug("Incrementing bmap playcount.")
    await s.bmap.increment_playcount(s.passed)

    # Stat updates
    logger.debug("Updating stats.")
    stats.playcount += 1
    stats.total_score += s.score
    stats.total_hits += s.count_300 + s.count_100 + s.count_50

    add_score = s.score
    if prev_score and s.completed == Completed.BEST:
        add_score -= prev_score.score

    if s.passed and s.bmap.has_leaderboard:
        if s.bmap.status == Status.RANKED:
            stats.ranked_score += add_score
        if stats.max_combo < s.max_combo:
            stats.max_combo = s.max_combo
        if s.completed == Completed.BEST and s.pp:
            logger.debug("Performing PP recalculation.")
            await stats.recalc_pp_acc_full(s.pp)
    logger.debug("Saving stats")
    await stats.save()

    # Write replay + anticheat.
    replay = await post_args.getlist("score")[1].read()
    if replay and replay != b"\r\n" and not s.passed:
        await edit_user(
            Actions.RESTRICT,
            s.user_id,
            "Score submit without replay " "(always should contain it).",
        )

    if s.passed:
        logger.debug("Writing replay.")
        await write_replay(s.id, replay, s.c_mode)

    logger.info(
        f"User {s.username} has submitted a #{s.placement} place"
        f" on {s.bmap.song_name} +{s.mods.readable} ({round(s.pp, 2)}pp)",
    )

    # Update our position on the global lbs.
    if (
        s.completed is Completed.BEST
        and privs & Privileges.USER_PUBLIC
        and old_stats.pp != stats.pp
    ):
        logger.debug("Updating user's global and country lb positions.")
        args = (s.user_id, round(stats.pp), s.mode, s.c_mode)
        await update_lb_pos(*args)
        await update_country_lb_pos(*args)
        await stats.update_rank()

    # Trigger peppy stats update.
    await stats_refresh(s.user_id)
    panels = []

    # Send webhook to discord.
    if s.placement == 1 and not privs.is_not_allowed:
        await log_first_place(s, old_stats, stats)

    # At the end, check achievements.
    new_achievements = []
    if s.passed and s.bmap.has_leaderboard:
        db_achievements = await get_achievements(s.user_id)
        for ach in cache.achievements:
            if ach.id in db_achievements:
                continue
            if ach.cond(s, s.mode.value, stats):
                await unlock_achievement(s.user_id, ach.id)
                new_achievements.append(ach.full_name)

    # More anticheat checks.
    if s.completed == Completed.BEST and await surpassed_cap_restrict(s):
        await edit_user(
            Actions.RESTRICT,
            s.user_id,
            f"Surpassing PP cap as unverified! ({s.pp:.2f}pp)",
        )

    await notify_new_score(s.id)

    # Create beatmap info panel.
    panels.append(
        f"beatmapId:{s.bmap.id}|"
        f"beatmapSetId:{s.bmap.set_id}|"
        f"beatmapPlaycount:{s.bmap.playcount}|"
        f"beatmapPasscount:{s.bmap.passcount}|"
        f"approvedDate:{datetime.utcfromtimestamp(s.bmap.last_update).strftime('%Y-%m-%d %H:%M:%S')}",
    )

    failed_not_prev_panel = (
        (
            _pair_panel("rank", "0", s.placement),
            _pair_panel("maxCombo", "", s.max_combo),
            _pair_panel("accuracy", "", round(s.accuracy, 2)),
            _pair_panel("rankedScore", "", s.score),
            _pair_panel("pp", "", s.pp),
        )
        if s.passed
        else (  # TL;DR for those of you who dont know, client requires failed panels.
            _pair_panel("rank", "0", "0"),
            _pair_panel("maxCombo", "", s.max_combo),
            _pair_panel("accuracy", "", ""),
            _pair_panel("rankedScore", "", s.score),
            _pair_panel("pp", "", ""),
        )
    )

    if s.bmap.has_leaderboard:
        # Beatmap ranking panel.
        panels.append(
            "|".join(
                (
                    "chartId:beatmap",
                    f"chartUrl:{config.SERVER_DOMAIN}/b/{s.bmap.id}",
                    "chartName:Beatmap Ranking",
                    *(
                        failed_not_prev_panel
                        if not prev_score or not s.passed
                        else (
                            _pair_panel("rank", prev_score.placement, s.placement),
                            _pair_panel("maxCombo", prev_score.max_combo, s.max_combo),
                            _pair_panel(
                                "accuracy",
                                round(prev_score.accuracy, 2),
                                round(s.accuracy, 2),
                            ),
                            _pair_panel("rankedScore", prev_score.score, s.score),
                            _pair_panel("pp", round(prev_score.pp), round(s.pp)),
                        )
                    ),
                    f"onlineScoreId:{s.id}",
                ),
            ),
        )

    # Overall ranking panel. XXX: Apparently unranked maps gets overall charts.
    panels.append(
        "|".join(
            (
                "chartId:overall",
                f"chartUrl:{config.SERVER_DOMAIN}/u/{s.user_id}",
                "chartName:Global Ranking",
                *(
                    (
                        _pair_panel("rank", old_stats.rank, stats.rank),
                        _pair_panel(
                            "rankedScore",
                            old_stats.ranked_score,
                            stats.ranked_score,
                        ),
                        _pair_panel(
                            "totalScore",
                            old_stats.total_score,
                            stats.total_score,
                        ),
                        _pair_panel("maxCombo", old_stats.max_combo, stats.max_combo),
                        _pair_panel(
                            "accuracy",
                            round(old_stats.accuracy, 2),
                            round(stats.accuracy, 2),
                        ),
                        _pair_panel("pp", round(old_stats.pp), round(stats.pp)),
                    )
                ),
                f"achievements-new:{'/'.join(new_achievements)}",
                f"onlineScoreId:{s.id}",
            ),
        ),
    )

    return PlainTextResponse("\n".join(i for i in panels))
