import base64
import traceback
from dataclasses import dataclass
from typing import Optional

from py3rijndael import RijndaelCbc
from py3rijndael import ZeroPadding

import logger
from pp.main import select_calculator
from server import config
from server.beatmaps.beatmap import Beatmap
from server.constants.c_modes import CustomModes
from server.constants.complete import Completed
from server.constants.modes import Mode
from server.constants.mods import Mods
from server.constants.privileges import Privileges
from server.db.redis.handlers.pep import announce
from server.libs.crypt import validate_md5
from server.libs.time import get_timestamp
from server.state import cache
from server.state import services
from server.user.helper import safe_name

# PP Calculators

FETCH_SCORE = """
SELECT
    s.id,
    s.beatmap_md5,
    s.userid,
    s.score,
    s.max_combo,
    s.full_combo,
    s.mods,
    s.300_count,
    s.100_count,
    s.50_count,
    s.katus_count,
    s.gekis_count,
    s.misses_count,
    s.time,
    s.play_mode,
    s.completed,
    s.accuracy,
    s.pp,
    s.playtime,
    a.username
FROM {table} s
INNER JOIN users a ON s.userid = a.id
WHERE {cond}
LIMIT {limit}
"""


@dataclass
class Score:
    """A class representing a singular score set on a beatmap."""

    id: int
    bmap: Beatmap
    user_id: int
    score: int
    max_combo: int
    full_combo: bool
    passed: bool
    quit: bool
    mods: Mods
    c_mode: CustomModes
    count_300: int
    count_100: int
    count_50: int
    count_katu: int
    count_geki: int
    count_miss: int
    timestamp: int
    mode: Mode
    completed: Completed
    accuracy: float
    pp: float
    play_time: int
    placement: int
    grade: str
    sr: float
    username: str

    @property
    def is_submitted(self) -> bool:
        """Bool corresponding to whether the score has been submitted."""

        return self.id != 0

    @classmethod
    async def from_score_sub(self, post_args: dict) -> Optional["Score"]:
        """Creates an instance of `Score` from data provided in a score
        submit request."""

        aes = RijndaelCbc(
            key="osu!-scoreburgr---------" + post_args["osuver"],
            iv=base64.b64decode(post_args["iv"]).decode("latin_1"),
            padding=ZeroPadding(32),
            block_size=32,
        )

        score_data = (
            aes.decrypt(
                base64.b64decode(post_args.getlist("score")[0]).decode("latin_1"),
            )
            .decode()
            .split(":")
        )

        # Set data from the score sub.
        map_md5 = score_data[0]

        # Verify map.
        if not validate_md5(map_md5):
            logger.warning(
                f"Score submit provided invalid beatmap md5 ({map_md5})! " "Giving up.",
            )
            return

        # Verify score data sent is correct.
        if len(score_data) != 18:  # Not sure if we restrict for this
            logger.warning(f"Someone sent over incorrect score data.... Giving up.")
            return

        username = score_data[1].rstrip()
        user_id = await cache.name.id_from_safe(safe_name(username))
        bmap = await Beatmap.from_md5(map_md5)
        mods = Mods(int(score_data[13]))
        mode = Mode(int(score_data[15]))

        s = Score(
            0,
            bmap,
            user_id,
            int(score_data[9]),
            int(score_data[10]),
            score_data[11] == "True",
            score_data[14] == "True",
            post_args.get("x") == "1",
            mods,
            CustomModes.from_mods(mods, mode),
            int(score_data[3]),
            int(score_data[4]),
            int(score_data[5]),
            int(score_data[7]),
            int(score_data[6]),
            int(score_data[8]),
            get_timestamp(),
            mode,
            None,
            0.0,
            0.0,
            0,  # TODO: Playtime
            0,
            score_data[12],
            0.0,
            username,
        )

        s.calc_accuracy()

        return s

    async def calc_completed(self) -> Completed:
        """Calculated the `complete` attribute for scores.

        Note:
            This DOES update the data for other scores. Only perform this
                function IF you are absolutely certain that this score is
                going to be added to the database.
            Running first place first is recommended for a potential perf
                save.
        """

        logger.debug("Calculating completed.")

        # Get the simple ones out the way.
        if self.placement == 1:
            self.completed = Completed.BEST
            return self.completed
        elif self.quit:
            self.completed = Completed.QUIT
            return self.completed
        elif not self.passed:
            self.completed = Completed.FAILED
            return self.completed

        # Don't bother for non-lb things.
        if not self.bmap.has_leaderboard:
            self.completed = Completed.COMPLETE
            return self.completed

        table = self.c_mode.db_table
        scoring = "pp"
        val = self.pp

        logger.debug("Using MySQL to calculate Completed.")

        query = (
            f"userid = :id AND completed = {Completed.BEST.value} AND beatmap_md5 = :md5 "
            f"AND play_mode = {self.mode.value}"
        )
        args = {
            "id": self.user_id,
            "md5": self.bmap.md5,
        }

        # TODO: Set old best to mod best etc
        await services.sql.execute(
            f"UPDATE {table} SET completed = {Completed.COMPLETE.value} WHERE "
            + query
            + f" AND {scoring} < {val} LIMIT 1",
            args,
        )

        # Check if it remains.
        ex_db = await services.sql.fetch_val(
            f"SELECT 1 FROM {table} WHERE " + query + " LIMIT 1",
            args,
        )

        if not ex_db:
            self.completed = Completed.BEST
            return self.completed

        self.completed = Completed.COMPLETE
        return self.completed
        # TODO: Mod bests

    async def calc_placement(self) -> int:
        """Calculates the placement of the score on the leaderboards.

        Note:
            Performs a generally costly query.
            Returns 0 if bmap ranked status doesnt have lbs.
            Returns 0 if completed doesnt allow.
        """

        if (not self.passed) or (not self.bmap.has_leaderboard):
            logger.debug("Not bothering calculating placement.")
            self.placement = 0
            return 0

        logger.debug("Calculating score placement based on MySQL.")

        table = self.c_mode.db_table
        scoring = "pp" if self.c_mode.uses_ppboard else "score"
        val = self.pp if self.c_mode.uses_ppboard else self.score

        self.placement = (
            await services.sql.fetch_val(
                f"SELECT COUNT(*) FROM {table} s INNER JOIN users u ON s.userid = "
                f"u.id WHERE u.privileges & {Privileges.USER_PUBLIC.value} AND "
                f"s.play_mode = {self.mode.value} AND s.completed = {Completed.BEST.value} "
                f"AND {scoring} > :score_val AND s.beatmap_md5 = :md5",
                {"score_val": val, "md5": self.bmap.md5},
            )
        ) + 1

        return self.placement

    async def calc_pp(self) -> float:
        """Calculates the PP given for the score."""

        if not self.bmap.has_leaderboard:  # or (not self.passed):
            logger.debug("Not bothering to calculate PP.")
            self.pp = 0.0
            return self.pp
        logger.debug("Calculating PP...")  # We calc for failed scores!

        # TODO: More calculators (custom for standard.)
        calc = select_calculator(self.mode, self.c_mode).from_score(self)
        try:
            self.pp, self.sr = await calc.calculate()
        except Exception:
            logger.error(
                "Could not calculate PP for score! Setting to 0. Error: "
                + traceback.format_exc(),
            )
        return self.pp

    # This gives me aids looking at it LOL. Copied from old Kisumi
    def calc_accuracy(self) -> float:
        """Calculates the accuracy of the score. Credits to Ripple for this as
        osu! wiki is not working :woozy_face:"""

        acc = 0.0
        # osu!std
        if self.mode == Mode.STANDARD:
            acc = (self.count_50 * 50 + self.count_100 * 100 + self.count_300 * 300) / (
                (self.count_300 + self.count_100 + self.count_50 + self.count_miss)
                * 300
            )
        # These may be slightly inaccurate but its the best we have without some next gen calculations.
        # Taiko
        elif self.mode == Mode.TAIKO:
            acc = ((self.count_100 * 50) + (self.count_300 * 100)) / (
                (self.count_300 + self.count_100 + self.count_miss) * 100
            )
        # Catch the beat
        elif self.mode == Mode.CATCH:
            acc = (self.count_300 + self.count_100 + self.count_50) / (
                self.count_300
                + self.count_100
                + self.count_50
                + self.count_miss
                + self.count_katu
            )
        # Mania
        elif self.mode == Mode.MANIA:
            acc = (
                self.count_50 * 50
                + self.count_100 * 100
                + self.count_katu * 200
                + self.count_300 * 300
                + self.count_geki * 300
            ) / (
                (
                    self.count_miss
                    + self.count_50
                    + self.count_100
                    + self.count_300
                    + self.count_geki
                    + self.count_katu
                )
                * 300
            )

        # I prefer having it as a percentage.
        self.accuracy = acc * 100
        return self.accuracy

    async def on_first_place(self) -> None:
        """Adds the score to the first_places table."""

        # Why did I design this system when i was stupid...

        # Delete previous first place.
        await services.sql.execute(
            "DELETE FROM first_places WHERE beatmap_md5 = :md5 AND mode = :mode AND "
            "relax = :relax LIMIT 1",
            {"md5": self.bmap.md5, "mode": self.mode.value, "relax": self.c_mode.value},
        )

        # And now we insert the new one.
        await services.sql.execute(
            "INSERT INTO first_places (score_id, user_id, score, max_combo, full_combo,"
            "mods, 300_count, 100_count, 50_count, miss_count, timestamp, mode, completed,"
            "accuracy, pp, play_time, beatmap_md5, relax) VALUES "
            "(:id, :uid, :score, :max_combo, :fc, :mods, :c300, :c100, :c50, :cmiss, :time, :mode,"
            ":completed, :acc, :pp, :play_time, :md5, :relax)",
            {
                "id": self.id,
                "uid": self.user_id,
                "score": self.score,
                "max_combo": self.max_combo,
                "fc": self.full_combo,
                "mods": self.mods.value,
                "c300": self.count_300,
                "c100": self.count_100,
                "c50": self.count_50,
                "cmiss": self.count_miss,
                "time": self.timestamp,
                "mode": self.mode.value,
                "completed": self.completed.value,
                "acc": self.accuracy,
                "pp": self.pp,
                "play_time": self.play_time,
                "md5": self.bmap.md5,
                "relax": self.c_mode.value,
            },
        )
        logger.debug("First place added.")

        # TODO: Move somewhere else.
        msg = (
            f"[{self.c_mode.acronym}] User [{config.SRV_URL}/u/{self.user_id} "
            f"{self.username}] has submitted a #1 place on "
            f"[{config.SRV_URL}/beatmaps/{self.bmap.id} {self.bmap.song_name}]"
            f" +{self.mods.readable} ({round(self.pp, 2)}pp)"
        )
        # Announce it.
        await announce(msg)
        # await log_first_place(self, old_stats, new_stats)

    async def submit(
        self,
        clear_lbs: bool = True,
        calc_completed: bool = True,
        calc_place: bool = True,
        calc_pp: bool = True,
        restricted: bool = False,
    ) -> None:

        """Inserts the score into the database, performing other necessary
        calculations.

        Args:
            clear_lbs (bool): If true, the leaderboard and personal best
                cache for this beatmap + c_mode + mode combo.
            calc_completed (bool): Whether the `completed` attribute should
                be calculated (MUST NOT BE RAN BEFORE, ELSE SCORES WILL BE
                WEIRD IN THE DB)
            calc_place (bool): Whether the placement of the score should be
                calculated (may not be calculated if `completed` does not
                allow so).
            calc_pp (bool): Whether the PP for the score should be recalculated
                from scratch.
            restricted (bool): Whether the user is restricted or not. If true,
                `on_first_place` and `insert_into_lb_cache` will NOT be called
        """

        if calc_pp:
            await self.calc_pp()  # We need this for the rest.
        if calc_completed:
            await self.calc_completed()
        if calc_place:
            await self.calc_placement()

        await self.__insert()

        # Handle first place.
        if self.placement == 1 and not restricted:
            await self.on_first_place()

        # Insert to cache after score ID is assigned.
        if (
            clear_lbs
            and self.completed is Completed.BEST
            and self.bmap.has_leaderboard
            and not restricted
        ):
            self.insert_into_lb_cache()

    async def __insert(self) -> None:
        """Inserts the score directly into the database. Also assigns the
        `id` attribute to the score ID."""

        table = self.c_mode.db_table
        ts = get_timestamp()

        logger.debug("Inserting score into the MySQL database.")

        self.id = await services.sql.execute(
            f"INSERT INTO {table} (beatmap_md5, userid, score, max_combo, full_combo, mods, "
            "300_count, 100_count, 50_count, katus_count, gekis_count, misses_count, time, "
            "play_mode, completed, accuracy, pp) VALUES (:md5, :uid, :score, :combo, :fc, :mods, :c300, :c100, "
            ":c50, :ckatus, :cgekis, :cmiss, :time, :mode, :completed, :accuracy, :pp)",
            {
                "md5": self.bmap.md5,
                "uid": self.user_id,
                "score": self.score,
                "combo": self.max_combo,
                "fc": int(self.full_combo),
                "mods": self.mods.value,
                "c300": self.count_300,
                "c100": self.count_100,
                "c50": self.count_50,
                "ckatus": self.count_katu,
                "cgekis": self.count_geki,
                "cmiss": self.count_miss,
                "time": ts,
                "mode": self.mode.value,
                "completed": self.completed.value,
                "accuracy": self.accuracy,
                "pp": self.pp,
            },
        )

    async def save_pp(self) -> None:
        """Saves the score PP attribute to the scores table.

        Note:
            This does NOT raise an exception if score is not submitted.
        """

        await services.sql.execute(
            f"UPDATE {self.c_mode.db_table} SET pp = :pp WHERE id = :id LIMIT 1",
            {"pp": self.pp, "id": self.id},
        )

    @classmethod
    def from_lb_data(
        cls,
        tup: tuple,
        mode: Mode,
        c_mode: CustomModes,
        bmap: Beatmap,
    ) -> "Score":
        """ "Sets leaderboard data to Score object."""

        return Score(
            id=tup[0],
            bmap=bmap,
            user_id=tup[13],
            score=tup[1],
            max_combo=tup[2],
            full_combo=bool(tup[9]),
            mods=Mods(tup[10]),
            count_300=tup[5],
            count_100=tup[4],
            count_50=tup[3],
            count_katu=tup[7],
            count_geki=tup[8],
            count_miss=tup[6],
            timestamp=int(tup[11]),
            mode=mode,
            completed=Completed.BEST,
            accuracy=0.0,
            pp=tup[14],
            play_time=0,
            username=tup[12],
            passed=True,
            quit=False,
            c_mode=c_mode,
            placement=0,
            sr=0.0,
            grade="X",
        )

    @classmethod
    async def from_tuple(cls, tup: tuple, bmap: Optional[Beatmap] = None) -> "Score":
        """Creates an instance of `Score` form a tuple straight from MySQL.

        Format:
            The tuple must feature the following arguments in the specific order:
            id, beatmap_md5, userid, score, max_combo, full_combo, mods, 300_count,
            100_count, 50_count, katus_count, gekis_count, misses_count, timestamp,
            play_mode, completed, accuracy, pp, playtime, username.

        Args:
            tup (tuple): The tuple to create the score from.
            bmap (Beatmap, optional): The beatmap to use. If not provided, will be
                manually fetched.

        Returns:
            Score: The score object.
        """

        completed = Completed(tup[15])
        passed = completed.completed
        quit = completed == Completed.QUIT
        bmap = bmap or await Beatmap.from_md5(tup[1])
        mods = Mods(tup[6])
        mode = Mode(tup[14])
        c_mode = CustomModes.from_mods(mods, mode)

        return Score(
            id=tup[0],
            bmap=bmap,
            user_id=tup[2],
            score=tup[3],
            max_combo=tup[4],
            full_combo=bool(tup[5]),
            mods=mods,
            count_300=tup[7],
            count_100=tup[8],
            count_50=tup[9],
            count_katu=tup[10],
            count_geki=tup[11],
            count_miss=tup[12],
            timestamp=int(tup[13]),
            mode=mode,
            completed=completed,
            accuracy=tup[16],
            pp=tup[17],
            play_time=tup[18],
            username=tup[19],
            passed=passed,
            quit=quit,
            c_mode=c_mode,
            placement=0,
            sr=0.0,
            grade="X",
        )

    @classmethod
    async def from_db(
        cls,
        score_id: int,
        c_mode: CustomModes,
        calc_placement: bool = True,
    ) -> Optional["Score"]:
        """Creates an instance of `Score` using data fetched from the
        database.

        Args:
            score_id (int): The ID of the score within the database.
            table (str): The table the score should be loacted within
                (directly formatted into the query).
            calc_placement (bool): Whether the placement of the score should be
                calculated.
        """

        table = c_mode.db_table
        s_db = await services.sql.fetch_one(
            FETCH_SCORE.format(
                table=table,
                cond="s.id = :score_id",
                limit="1",
            ),
            {"score_id": score_id},
        )

        if not s_db:
            return
        s = await cls.from_tuple(s_db)

        if calc_placement:
            await s.calc_placement()

        return s
