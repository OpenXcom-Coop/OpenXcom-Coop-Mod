"""D246-U stage S-A row RH: a SHARED co-op campaign saved mid-battle by an OLDER version (the release line, `main`
651ae44ba) with parallel turns on loads on the rewrite's host without the FW-7 refusal and resumes PARALLEL for both
players (owner D246 (b); FW-7 narrowed; D-22 / QD246-3 (a): the played mode, from the campaign block's
coop_parallel_turns; D99, D235-VL2).

Spec: docs repo rewrite/prompts/d246u_midbattle_save_convert.md section (f) test_d246u_old_battle_resume_shared.py
(QD246-1 .. QD246-9 (a), orchestrator rulings 2026-10-12). Constants: rewrite/d246u-task0/sa/CONSTANTS.md (TASK 0 T0-4,
T0-5, T0-6). Fixture: tools/coop_test/fixtures/d246u_shared_battle.sav, made by the release build's own
test_shared_resume_battle_control.py on the main-check worktree (T0-4), committed unedited; this file writes the
host's copy with its ONE "coop_parallel_turns: false" line changed to "true" (line endings kept, asserted). The cell
helpers are test_d246u_old_battle_resume.py's (the rc precedent).

Boot RH (key 46611, dirs d246u_rh_*): the host gets the derived copy, the client an EMPTY dir.
  RH-load    host load_save_menu -> HostMenu within 60 s, no ErrorMessageState (red: ErrorMessageState and the refusal
             text "different version of the mod" in the host log, in EVIDENCE)
  RH-log     exactly one "[coop-convert] D246: an older version's mid-battle co-op save converted" line: partner worlds
             0 / 0, seats RH_SEATS, unseated RH_UNSEATED, turnMode parallel, deployment DEP_RH
  RH-resume  as RS-resume (key 46611)
  RH-hash    the host log has "battle_ready saveBlob EQUAL" and no MISMATCH; desyncSeen false on both
  RH-seats   the (name, seat) set == RH_EXPECT on both; every non-player original faction has coop -1 on both
  RH-mode    turnMode "parallel" on both; coopEndTurnTally == the reset default on both (RBC's RESET_TALLY)
  RH-deploy  deployment / strTarget / strCraftOrBase == DEP_RH / TGT_RH / COB_RH on both
  RH-click   the host's RESUME (CoopState 60 / 62); both tops BattlescapeState; no HostMenu / LobbyMenu
  RH-cmd     session.assert_t_cmd(RH_C1, RH_H0, host_check=False)
  RH-common  every hash bucket EQUAL, desyncSeen false on both, no new lane crash file, the client wrote no save

One EVIDENCE line, then one PASS/FAIL line per cell, then the row verdict; a cell whose precondition failed FAILs "not
reached". A boot step past its bound prints ONE CAPTURE line and fails the row "boot". WV-D95: run in the foreground to
completion. WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_d246u_old_battle_resume_shared.py
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import test_d246u_old_battle_resume as rs  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "d246u_shared_battle.sav")
RH_KEY = "46611"
RH_EXPECT = {"Asbjoorn Solvig": 0, "Dobroslav Janecek": 1}
RH_SEATS = (1, 1)                 # seated 0 / seated 1 by E4 (1)'s rule (T0-5)
RH_UNSEATED = 18                  # 9 aliens + 9 civilians, each saved with coop 0 (T0-5)
DEP_RH = "STR_TERROR_MISSION"
TGT_RH, COB_RH = "TERROR SITE-1", "BASE> HostBase"
RH_C1, RH_H0 = 2, 1               # the client-owned soldier's battle unit / the host-owned one's
RESET_TALLY = {"turn": 0, "side": "", "count": 0, "needed": 0, "ready": [], "activeSeat": -1}
RH_CELLS = ("RH-load", "RH-log", "RH-resume", "RH-hash", "RH-seats", "RH-mode", "RH-deploy", "RH-click", "RH-cmd",
            "RH-common")


def row_rh(host, client, crash0, changed, cells, ev):
    ev["rhChanged"] = changed.decode("ascii", errors="replace").rstrip("\r")
    cells["RH-load"] = rs.load_cell(host, os.path.basename(FIXTURE), ev, "rh")
    rs.need(cells, "RH-load")
    cells["RH-log"] = rs.log_cell(host, ev, "rh", (0, 0, RH_SEATS[0], RH_SEATS[1], RH_UNSEATED, "parallel", DEP_RH))
    rs.attempt(cells, "RH-resume", lambda: rs.resume_loaded(host, client, RH_KEY, ev, "rh"), (host, client))
    rs.need(cells, "RH-resume")
    cells["RH-hash"] = rs.hash_cell(host, client, ev, "rh")
    cells["RH-seats"] = rs.seats_cell(host, client, ev, "RH", RH_EXPECT)

    def mode():
        return ([rs.es(gc, "turnMode") for gc in (host, client)] == ["parallel"] * 2
                and [rs.es(gc, "coopEndTurnTally") for gc in (host, client)] == [RESET_TALLY] * 2)
    rs.wait_until(mode, rs.MODE_S)
    got = {gc.name: (rs.es(gc, "turnMode"), rs.es(gc, "coopEndTurnTally")) for gc in (host, client)}
    ev["rhMode"] = got
    cells["RH-mode"] = (mode(), f"(turnMode, coopEndTurnTally) {got} (want parallel, {RESET_TALLY} on both)")
    cells["RH-deploy"] = rs.deploy_cell(host, client, ev, "rh", (DEP_RH, TGT_RH, COB_RH))
    rs.attempt(cells, "RH-click", lambda: rs.click_cell(host, client, ev, "rh"), (host, client))
    rs.need(cells, "RH-click")

    def cmd():
        rs.quiet(lambda: session.assert_t_cmd(host, client, RH_C1, RH_H0, host_check=False, what="RH"), ev, "rhCmd")
        return True, f"client admitted on its soldier {RH_C1}, not_your_unit on host soldier {RH_H0}, hash clean"
    rs.attempt(cells, "RH-cmd", cmd, (host, client))
    cells["RH-common"] = rs.common_cell(host, client, crash0, ev, "rh")


def boot_rh():
    d = make_user_dir("d246u_rh_host")
    changed = rs.derive(FIXTURE, os.path.join(d, "xcom1", os.path.basename(FIXTURE)), b"coop_parallel_turns: false",
                        b"coop_parallel_turns: true")
    host = GameClient("host", None, d)
    client = GameClient("client", None, make_user_dir("d246u_rh_client"))
    crash0 = session._crash_log_snapshot()
    try:
        try:
            rs.boot("RH", (host, client))
        except rs.Miss:
            return rs.fail_all((("RH", RH_CELLS),), "boot (FIXTURE-STOP, see the CAPTURE RH line)")
        return rs.run_row("RH", RH_CELLS, lambda cells, ev: row_rh(host, client, crash0, changed, cells, ev))
    finally:
        rs.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_rh()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_d246u_old_battle_resume_shared: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s",
          flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
