# import os
# from config import config
# import traceback
# import uvicorn
# # Uvloop is a significantly faster loop.
# try:
#     __import__("uvloop").install()
# except ImportError:
#     pass
# from starlette.applications import Starlette
# from starlette.routing import Route
# from db.redis.pubsub import pubsub_executor
# from pp.main import build_oppai, verify_oppai
# # Initialise globals.
# from state.connection import (
#     connect_sql,
#     connect_redis
# )
# from state.cache import initialise_cache
# from logger import (
#     error,
#     info,
#     warning,
#     DEBUG,
#     ensure_log_file,
#     check_log_file,
#     write_log_file,
# )
# # Load web handlers.
# from web.handlers.direct import direct_get_handler, download_map, get_set_handler
# from web.handlers.leaderboards import leaderboard_get_handler
# from web.handlers.replays import get_replay_web_handler, get_full_replay_handler
# from web.handlers.screenshot import upload_image_handler
# from web.handlers.score_sub import score_submit_handler
# from web.handlers.rippleapi import status_handler, pp_handler
# from web.handlers.misc import (
#     lastfm_handler,
#     getfriends_handler,
#     osu_error_handler,
#     beatmap_rate_handler,
#     get_seasonals_handler,
#     bancho_connect,
#     difficulty_rating
# )
# # Load redis handlers.
# from db.redis.handlers.ripple import (
#     username_change_pubsub,
#     update_cached_privileges_pubsub,
#     change_pass_pubsub,
#     ban_reload_pubsub,
# )
# from db.redis.handlers.rosu import (
#     clan_update_pubsub,
# )
# from db.redis.handlers.ussr import (
#     drop_bmap_cache_pubsub,
#     refresh_leaderboard_pubsub,
# )
# # Must return True for success or else server wont start.
# STARTUP_TASKS = (
#     connect_sql,
#     connect_redis,
#     initialise_cache,
# )
# # tuples of checker and fixer functions.
# DEPENDENCIES = (
#     (verify_oppai, build_oppai),
#     (check_log_file, ensure_log_file),
# )
# PUBSUB_REGISTER = (
#     # Ripple ones.
#     (username_change_pubsub, "peppy:change_username"),
#     (update_cached_privileges_pubsub, "peppy:update_cached_stats"),
#     (change_pass_pubsub, "peppy:change_pass"),
#     (ban_reload_pubsub, "peppy:ban"),
#     # RealistikOsu.
#     (clan_update_pubsub, "rosu:clan_update"),
#     # USSR
#     (drop_bmap_cache_pubsub, "ussr:bmap_decache"),
#     (refresh_leaderboard_pubsub, "ussr:lb_refresh"),
# )
# def ensure_dependencies():
#     """Checks if all dependencies are met, and if not, attempts to fix them."""
#     for checker, fixer in DEPENDENCIES:
#         if checker():
#             continue
#         warning(f"Dependency {checker.__name__} not met! Attempting to fix...")
#         try:
#             fixer()
#             info("Dependency fixed!")
#         except Exception:
#             error("Error fixing dependency!" + traceback.format_exc())
#             raise SystemExit(1)
# async def perform_startup(redis: bool = True):
#     """Runs all of the startup tasks, checking if they all succeed. If not,
#     `SystemExit` will be raised."""
#     os.system("clear")
#     info("Running startup tasks...")
#     try:
#         if not all([await coro() for coro in STARTUP_TASKS]):
#             error("Not all startup tasks succeeded! Check logs above.")
#             raise SystemExit(1)
#     except Exception:
#         error("Error running startup task!" + traceback.format_exc())
#         raise SystemExit(1)
#     if redis:
#         try:
#             for coro, name in PUBSUB_REGISTER:
#                 await pubsub_executor(name, coro)
#             info(f"Created {len(PUBSUB_REGISTER)} Redis PubSub listeners!")
#         except Exception:
#             error("Error creating Redis PubSub listeners! " + traceback.format_exc())
#             raise SystemExit(1)
#         info("Finished startup tasks!")
# if __name__ == "__main__":
#     ensure_dependencies()
#     server_start()
# Load web handlers.
# from server.web.handlers.direct import direct_get_handler, download_map, get_set_handler
# from server.web.handlers.leaderboards import leaderboard_get_handler
# from server.web.handlers.replays import get_replay_web_handler, get_full_replay_handler
# from server.web.handlers.screenshot import upload_image_handler
# from server.web.handlers.score_sub import score_submit_handler
# from server.web.handlers.rippleapi import status_handler, pp_handler
# from server.web.handlers.misc import (
#     lastfm_handler,
#     getfriends_handler,
#     osu_error_handler,
#     beatmap_rate_handler,
#     get_seasonals_handler,
#     bancho_connect,
#     difficulty_rating
# )
import os
import traceback

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route

import logger

# Uvloop is a significantly faster loop.
try:
    __import__("uvloop").install()
except ImportError:
    pass

# # tuples of checker and fixer functions.
# DEPENDENCIES = (
#     (verify_oppai, build_oppai),
#     (check_log_file, ensure_log_file),
# )
# def ensure_dependencies() -> int:
#     """Checks if all dependencies are met, and if not, attempts to fix them."""

#     for check_def, fix_def in DEPENDENCIES:
#         if check_def():
#             continue

#         logger.warning(f"Dependency {check_def.__name__} not met! Attempting to fix...")
#         try:
#             fix_def()
#             logger.info(f"Dependency {check_def.__name__} fixed!")
#         except Exception:
#             logger.error(f"Error fixing {check_def.__name__} dependency!" + traceback.format_exc())
#             return 1

#     return 0

# def server_start():
#     """Handles a regular start of the server."""

#     app = Starlette(
#         debug= DEBUG,
#         on_startup= [
#             perform_startup
#         ],
#         routes= [
#             # osu web Routes
#             Route("/web/osu-osz2-getscores.php", leaderboard_get_handler),
#             Route("/web/osu-search.php", direct_get_handler),
#             Route("/web/osu-search-set.php", get_set_handler),
#             Route("/d/{map_id:int}", download_map),
#             Route("/web/osu-getreplay.php", get_replay_web_handler),
#             Route("/web/osu-screenshot.php", upload_image_handler, methods= ["POST"]),
#             Route(
#                 "/web/osu-submit-modular-selector.php", score_submit_handler, methods= ["POST"]
#             ),
#             Route("/web/lastfm.php", lastfm_handler),
#             Route("/web/osu-getfriends.php", getfriends_handler),
#             Route("/web/osu-error.php", osu_error_handler, methods= ["POST"]),
#             Route("/web/osu-rate.php", beatmap_rate_handler),
#             Route("/web/osu-getseasonal.php", get_seasonals_handler),
#             Route("/web/bancho_connect.php", bancho_connect),
#             Route("/difficulty-rating", difficulty_rating, methods= ["POST"]),
#             # Ripple API Routes
#             Route("/api/v1/status", status_handler),
#             Route("/api/v1/pp", pp_handler),
#             # Frontend Routes
#             Route("/web/replays/{score_id:int}", get_full_replay_handler),
#         ]
#     )

#     #write_log_file("Server started!")
#     uvicorn.run(app, host= "127.0.0.1", port= config.PORT, access_log= False, log_level= "warning")


def main() -> int:
    # Change path to cwd.
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    # if code is not 0, then it errored.
    logger.info("Checking dependencies...")
    # if (code := ensure_dependencies()) != 0:
    #     return code

    logger.info("Starting a server...")
    # server_start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
