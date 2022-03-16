from enum import IntEnum

from logger import Ansi


class LeaderboardTypes(IntEnum):
    """osu! in-game leaderboards types. Taken from osu! `RankingType` enum at
    `SongSelection.cs` line 3180."""

    LOCAL: int = 0  # Not used online.
    GLOBAL: int = 1  # Regular top leaderboards.
    MOD: int = 2  # Leaderboards for a specific mod combo.
    FRIENDS: int = 3  # Leaderboard containing only the user's friends.
    COUNTRY: int = 4  # Leaderboards containing only people from the user's nation.


FETCH_TEXT = ("No Result", "Cache", "MySQL", "API", "Local")

FETCH_COL = (
    Ansi.RED,  # None
    Ansi.GREEN,  # Cache
    Ansi.BLUE,  # MySQL
    Ansi.YELLOW,  # API
    Ansi.MAGENTA,  # Local
)


class FetchStatus(IntEnum):
    """Statuses representing how information was fetched. Mostly meant for
    logging purposes."""

    NONE = 0  # No information was fetched.
    CACHE = 1  # Information was fetched from cache.
    MYSQL = 2  # Information was fetched from MySQL.
    API = 3  # Information was fetched from the API.
    LOCAL = 4  # Information deduced from other information.

    @property
    def result_exists(self) -> bool:
        """Whether the fetch result value means there is a valid result present."""

        return self.value > 0

    @property
    def colour(self) -> str:
        """Returns the colorama colour that should be used for the status."""

        return FETCH_COL[self.value]

    @property
    def console_text(self) -> str:
        """Returns the text string to be used in loggign."""

        return f"{self.colour!r}{FETCH_TEXT[self.value]!r}{Ansi.LBLUE!r}"
