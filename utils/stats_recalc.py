# Handles recalculating total PP, accuracy and max combo for a user using
# USSR's new formulas.
from cli_utils import get_loop
from cli_utils import perform_split_async
from cli_utils import perform_startup_requirements
from scores.constants.c_modes import CustomModes
from scores.constants.modes import Mode
from state.connection import sql
from user.helper import fetch_user_country
from user.helper import update_country_lb_pos
from user.helper import update_lb_pos
from user.stats import Stats

from logger import error
from logger import info


async def perform_stats_update(uid_tup: tuple[int, int]):
    """Performs the recalculation and saving of a singular user from stats."""

    user_id, privs = uid_tup
    # Fetch country only once.
    country = await fetch_user_country(user_id)

    for mode in (Mode.STANDARD, Mode.TAIKO, Mode.MANIA, Mode.CATCH):
        for c_mode in (CustomModes.VANILLA, CustomModes.RELAX, CustomModes.AUTOPILOT):

            # Some of these modes are mutually exclusive. Don't allow them.
            if c_mode is CustomModes.AUTOPILOT and mode is not Mode.STANDARD:
                continue
            if c_mode is CustomModes.RELAX and mode is Mode.MANIA:
                continue

            st = await Stats.from_sql(user_id, mode, c_mode)
            if not st:
                error(f"Failed to load {mode!r} {c_mode!r} stats for {user_id}!")
                continue

            # Logging purposes.
            old_pp = st.pp
            old_acc = st.accuracy
            old_max_combo = st.max_combo

            # Recalc.
            await st.calc_max_combo()
            await st.recalc_pp_acc_full()

            # Save.
            await st.save()

            # Only add unres players
            if privs & 1:
                await update_lb_pos(user_id, st.pp, mode, c_mode)
                await update_country_lb_pos(user_id, st.pp, mode, c_mode, country)

            info(
                f"Recalculated stats for user {st.user_id}!\n"
                f"| {old_pp:.2f}pp -> {st.pp:.2f} | {old_acc:.2f}% -> {st.accuracy:2f}% | {old_max_combo}x -> {st.max_combo}x",
            )


async def recalc_chk(l: list[int]):
    """Recalculates a chunk of user_id stats."""

    for uid in l:
        await perform_stats_update(uid)
    info("Chunk of recalculation completed!")


async def main():
    """The root of the server wide recalculator."""

    info("Fetching a list of all users.")

    users_db = await sql.fetchall("SELECT id, privileges FROM users")

    info("Starting the stars recalculation of the whole server...")

    await perform_split_async(recalc_chk, users_db, 16)


if __name__ == "__main__":
    loop = get_loop()
    perform_startup_requirements()
    loop.run_until_complete(main())
