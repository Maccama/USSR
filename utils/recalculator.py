# The USSR Recalculator Utils. This one will be quite slow ngl......
# But it can reuse code and utils efficiently. You win some you lose some.
import asyncio
import traceback
from typing import Generator

from cli_utils import perform_startup_requirements

import logger
from server.constants.c_modes import CustomModes
from server.scores.score import Score
from server.state import services

TASK_COUNT = 4
BASE_QUERY = "SELECT id FROM {table} WHERE {cond}"


async def recalc_pp(s: Score) -> None:
    """Recalculates PP for a score and saves it."""

    await s.calc_pp()
    await s.save_pp()


class ScorePool:
    """A pool holding large quantities of scores for recalculation."""

    def __init__(self, c_mode: CustomModes) -> None:
        """Creates an empty instance of"""
        self.scores: list = []
        self.score_ids: list[int] = []
        self.lock = asyncio.Lock()
        self.c_mode = c_mode

    async def fetch_scores(self, cond: str, args: tuple = ()) -> None:
        """Fetches a list of score IDs to the pool."""

        self.scores = [
            s[0]
            for s in await services.sql.fetch_all(
                BASE_QUERY.format(table=self.c_mode.db_table, cond=cond),
            )
        ]

        logger.info(f"ScorePool fetched a total of {len(self.scores)} scores!")

    async def fetch_loved_scores(self) -> None:
        """Adds all completed scores on loved beatmaps."""

        table = self.c_mode.db_table
        scores_db = await services.sql.fetch_all(
            f"SELECT s.id FROM {table} s INNER JOIN beatmaps b ON b.beatmap_md5 = s.beatmap_md5 "
            "WHERE s.completed >= 2 AND b.ranked = 5",
        )

        for score in scores_db:
            self.score_ids.append(score[0])

        logger.info(f"ScorePool fetched a total of {len(scores_db)} scores!")

    async def get_scores(self) -> Generator[Score, None, None]:
        """Generates score objects from score IDs in the object."""

        for score_id in self.score_ids:
            score = await Score.from_db(score_id, self.c_mode)
            if not score:
                continue
            yield score

    async def perform_sequential(self) -> None:
        """Performs a sequential recalculation of all scores."""

        count = 0
        failed = 0
        total = len(self.score_ids)
        async for score in self.get_scores():
            count += 1
            try:
                old_score_pp = score.pp
                await recalc_pp(score)
                new_score_pp = score.pp

                logger.info(
                    f"Score on {score.bmap.song_name} by {score.username} {old_score_pp:.2f}pp -> {new_score_pp:.2f}pp",
                )

                if count % 10 == 0:
                    logger.info(f"Calculated {count}/{total} scores ({failed} failed).")
            except Exception:
                failed += 1
                err = traceback.format_exc()
                logger.error(
                    f"Failed recalculating score {score.id} with err {err}.\n"
                    f"Total failed: {failed}",
                )


def main() -> int:
    logger.info("Starting USSR PP Recalculator...")
    loop = asyncio.get_event_loop()
    perform_startup_requirements()
    loop.run_until_complete(async_main())
    return 0


async def async_main():
    # Hardcoding loved PP recalc lmfao.
    calc = ScorePool(CustomModes.RELAX)

    logger.info("Loading scores...")
    await calc.fetch_loved_scores()

    logger.info("Starting recalculation!")
    await calc.perform_sequential()


if __name__ == "__main__":
    raise SystemExit(main())
