"""A SHARED co-op campaign saved mid-battle by an older version with parallel turns on loads on the host without the
"different version" refusal and resumes PARALLEL for both players: the converted save keeps the mode that was played,
read from the campaign block's coop_parallel_turns.

Fixture: tools/coop_test/fixtures/shared_battle.sav, made by the released game's own
test_shared_resume_battle_control.py, committed unedited; this file writes the host's copy with its ONE
"coop_parallel_turns: false" line changed to "true" (line endings kept, asserted). The cell helpers are
test_old_battle_resume.py's.

Boot shared_parallel_resumes (key 46611, dirs old_battle_resume_shared_*): the host gets the derived copy, the client
an EMPTY dir.
  host_load        host load_save_menu -> HostMenu within 60 s, no ErrorMessageState (without the fix:
                   ErrorMessageState and the refusal text "different version of the mod" in the host log, in EVIDENCE)
  conversion_line  exactly one "[coop-convert] an older version's mid-battle co-op save converted" line: partner
                   worlds 0 / 0, seats SEATED, unseated UNSEATED, turnMode parallel, deployment DEPLOYMENT
  both_in_battle   as test_old_battle_resume.py's both_in_battle (key 46611)
  ready_hash       the host log has "battle_ready saveBlob EQUAL" and no MISMATCH; desyncSeen false on both
  seat_split       the (name, seat) set == SEATS_BY_NAME on both; every non-player original faction has coop -1 on
                   both
  parallel_mode    turnMode "parallel" on both; coopEndTurnTally == the reset default on both (RESET_TALLY)
  deploy_strings   deployment / strTarget / strCraftOrBase == DEPLOYMENT / TARGET / CRAFT_OR_BASE on both
  resume_click     the host's RESUME (CoopState 60 / 62); both tops BattlescapeState; no HostMenu / LobbyMenu
  seat_commands    session.assert_seat_commands(CLIENT_UNIT, HOST_UNIT, host_check=False)
  common_checks    every hash bucket EQUAL, desyncSeen false on both, no new lane crash file, the client wrote no save

One EVIDENCE line, then one PASS/FAIL line per cell, then the row verdict; a cell whose precondition failed FAILs "not
reached". A boot step past its bound prints ONE CAPTURE line and fails the row "boot". ONE run is the result, no skip
path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_old_battle_resume_shared.py
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import test_old_battle_resume as OBR  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "shared_battle.sav")
KEY = "46611"
SEATS_BY_NAME = {"Asbjoorn Solvig": 0, "Dobroslav Janecek": 1}
SEATED = (1, 1)                   # seated 0 / seated 1, from each unit's saved coop tag
UNSEATED = 18                     # 9 aliens + 9 civilians, each saved with coop 0
DEPLOYMENT = "STR_TERROR_MISSION"
TARGET, CRAFT_OR_BASE = "TERROR SITE-1", "BASE> HostBase"
CLIENT_UNIT, HOST_UNIT = 2, 1     # the client-owned soldier's battle unit / the host-owned one's
RESET_TALLY = {"turn": 0, "side": "", "count": 0, "needed": 0, "ready": [], "activeSeat": -1}
CELLS = ("host_load", "conversion_line", "both_in_battle", "ready_hash", "seat_split", "parallel_mode",
         "deploy_strings", "resume_click", "seat_commands", "common_checks")


def row_shared_parallel_resumes(host, client, crash0, changed, cells, ev):
    ev["sharedChanged"] = changed.decode("ascii", errors="replace").rstrip("\r")
    cells["host_load"] = OBR.load_cell(host, os.path.basename(FIXTURE), ev, "shared")
    OBR.need(cells, "host_load")
    cells["conversion_line"] = OBR.log_cell(host, ev, "shared",
                                            (0, 0, SEATED[0], SEATED[1], UNSEATED, "parallel", DEPLOYMENT))
    OBR.attempt(cells, "both_in_battle", lambda: OBR.resume_loaded(host, client, KEY, ev, "shared"), (host, client))
    OBR.need(cells, "both_in_battle")
    cells["ready_hash"] = OBR.hash_cell(host, client, ev, "shared")
    cells["seat_split"] = OBR.seats_cell(host, client, ev, "shared_parallel_resumes", SEATS_BY_NAME)

    def mode():
        return ([OBR.es(gc, "turnMode") for gc in (host, client)] == ["parallel"] * 2
                and [OBR.es(gc, "coopEndTurnTally") for gc in (host, client)] == [RESET_TALLY] * 2)
    OBR.wait_until(mode, OBR.MODE_S)
    got = {gc.name: (OBR.es(gc, "turnMode"), OBR.es(gc, "coopEndTurnTally")) for gc in (host, client)}
    ev["sharedMode"] = got
    cells["parallel_mode"] = (mode(), f"(turnMode, coopEndTurnTally) {got} (want parallel, {RESET_TALLY} on both)")
    cells["deploy_strings"] = OBR.deploy_cell(host, client, ev, "shared", (DEPLOYMENT, TARGET, CRAFT_OR_BASE))
    OBR.attempt(cells, "resume_click", lambda: OBR.click_cell(host, client, ev, "shared"), (host, client))
    OBR.need(cells, "resume_click")

    def cmd():
        OBR.quiet(lambda: session.assert_seat_commands(host, client, CLIENT_UNIT, HOST_UNIT, host_check=False,
                                                       what="shared_parallel_resumes"), ev, "sharedCmd")
        return True, (f"client admitted on its soldier {CLIENT_UNIT}, not_your_unit on host soldier {HOST_UNIT}, "
                      "hash clean")
    OBR.attempt(cells, "seat_commands", cmd, (host, client))
    cells["common_checks"] = OBR.common_cell(host, client, crash0, ev, "shared")


def boot_shared_parallel_resumes():
    d = make_user_dir("old_battle_resume_shared_host")
    changed = OBR.derive(FIXTURE, os.path.join(d, "xcom1", os.path.basename(FIXTURE)), b"coop_parallel_turns: false",
                         b"coop_parallel_turns: true")
    host = GameClient("host", None, d)
    client = GameClient("client", None, make_user_dir("old_battle_resume_shared_client"))
    crash0 = session._crash_log_snapshot()
    try:
        try:
            OBR.boot("shared_parallel_resumes", (host, client))
        except OBR.Miss:
            return OBR.fail_all((("shared_parallel_resumes", CELLS),),
                                "boot (setup failure, see the CAPTURE shared_parallel_resumes line)")
        return OBR.run_row("shared_parallel_resumes", CELLS,
                           lambda cells, ev: row_shared_parallel_resumes(host, client, crash0, changed, cells, ev))
    finally:
        OBR.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_shared_parallel_resumes()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_old_battle_resume_shared: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s",
          flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
