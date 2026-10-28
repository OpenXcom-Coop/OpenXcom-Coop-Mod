"""R5-U6 S-C row SC3 (boot CP, gm2: the client plays the aliens, seat 1; the host the seven X-COM soldiers, seat 0): the
X-COM host's motion-scanner mark never reaches the alien player (orchestrator R5-V5; QU6-4 (a): `bt_scan_mark` goes to a
mapped seat of the scanning seat's side only; the release line sent `motion_scan` in PvP too, F14107). A guard: it passes
on the red build (the mark stays on the scanning machine) and must keep passing on the green.

Spec: docs repo rewrite/prompts/r5u6_pvp_options.md section (d) Stage S-C and (f) test_scan_share_pvp.py, AMENDMENT
U6-1 (U6-1.4, U6-1.7). Constants: rewrite/r5u6-task0/sc/CONSTANTS.md (TASK 0 boots CPa = CPb on the probe build). Probes
(TEST-ONLY, TC1 / TC2) and the scan's real-UI order: see test_scan_share.py (its helpers are imported).

Boot CP (key 49064): test_battle_end_rules.boot_e6 (STR_SMALL_SCOUT, map seed 1, gamemode 2), every live unit's
reactions 0; turn 1, the X-COM side.
  SC3  S (8) on SC3_S_TILE facing A; the scanner into S's right hand by lever (both, ids equal); set_tu_both(S); A
       motionPoints 30 (both, client first); the host's real-UI USE SCANNER (TAB S, the right-hand box, key 49); its
       ScannerState; 1.0 s; KEY_CANCEL; a 3 s window.
       SC3-own    the host's ScannerState up and its units[A].scannedTurn == 1 (precondition)
       SC3-none   the client's units[A].scannedTurn == -1 at every sample of the window and after it
Common cell (SC3-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane crash folder.
EVIDENCE only: S and A on both machines, the screen, the new host contexts.

RED on the probe build (commit C1): none (SC3 is a guard on both builds); every cell PASS. One EVIDENCE line, one PASS/FAIL
line per cell, then the row verdict. A boot step past its bound prints ONE CAPTURE line and fails the row "boot"; a
staging step that fails fails the row's cells. run in the foreground to completion. ONE run is
the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_scan_share_pvp.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_scan_share as SS  # noqa: E402

KEY = "49064"
S_ID = 8                                      # the host's first soldier (start (14,19,1))
SC3_S_TILE, SC3_S_DIR = (19, 19, 0), 1        # TASK 0 (U6-1.7 rule): Chebyshev 8 from A (27,12,0), 5 from S's start
WINDOW_S, SAMPLE_S = 3.0, 0.25
ROWS = (("SC3", ("SC3-own", "SC3-none", "SC3-common")),)


def row_sc3(host, client, crash0):
    ev = {"turnSide": [(battle_state(gc).get("turn"), battle_state(gc).get("side")) for gc in (host, client)]}
    SS.staged("S and the scanner", lambda: SS.stage_scanner(host, client, S_ID, SC3_S_TILE, SC3_S_DIR, ev))
    up, own = SS.scan(host, client, host, S_ID, ev)
    samples, t0 = [], time.time()
    while time.time() - t0 < WINDOW_S:
        samples.append((round(time.time() - t0, 2), SS.mark(client)))
        time.sleep(SAMPLE_S)
    final = SS.mark(client)
    ev["window"] = samples
    cells = {"SC3-own": SS.own_cell(up, own, ev, "host", 1),
             "SC3-none": (final == -1 and all(v == -1 for _t, v in samples),
                          f"client units[A].scannedTurn {final} after the {WINDOW_S} s window, samples "
                          f"{[v for _t, v in samples]} (want -1 throughout: the PvP opponent never gets the mark)"),
             "SC3-common": G3F.common(host, client, crash0)}
    return cells, ev


def boot_cp():
    host = GameClient("host", None, make_user_dir("r5u6_cp_host"))
    client = GameClient("client", None, make_user_dir("r5u6_cp_client"))
    m = (host, client)
    try:
        try:
            G3F.guarded("CP", lambda: BER.boot_e6(host, client, KEY), m)
            G3F.guarded("CP", lambda: G3F.reactions_zero(host, client), m)
            crash0 = session._crash_log_snapshot()
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE CP line)")
        print(f"EVIDENCE boot: A {[SS.uview(gc, SS.A_ID) for gc in m]}; scannedTurn {SS.scanned_all(host, client)}",
              flush=True)
        return G3F.run_row("SC3", ROWS[0][1], lambda: row_sc3(host, client, crash0))
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_cp()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_scan_share_pvp: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
