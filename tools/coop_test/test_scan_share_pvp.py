"""Row pvp_scan (boot pvp, gm2: the client plays the aliens, seat 1; the host the seven X-COM soldiers, seat 0): the
X-COM host's motion-scanner mark never reaches the alien player (`bt_scan_mark` goes only to a mapped seat on the
scanning seat's side; the released game sent `motion_scan` in PvP too). A guard: without the fix the mark also stays on
the scanning machine, so the row passes with or without it.

Probes (test-only: battle_state.units[].scannedTurn and battle_set_unit_state {motionPoints}) and the scan's real-UI
order: see test_scan_share.py (its helpers are imported).

Boot pvp (key 49064): test_battle_end_rules.boot_pvp (STR_SMALL_SCOUT, map seed 1, gamemode 2), every live unit's
reactions 0; turn 1, the X-COM side.
  pvp_scan  S (8) on SCANNER_TILE facing A; the scanner into S's right hand by test command (both, ids equal);
       set_tu_both(S); A motionPoints 30 (both, client first); the host's real-UI USE SCANNER (TAB S, the right-hand
       box, key 49); its ScannerState; 1.0 s; KEY_CANCEL; a 3 s window.
       pvp_scan_marks_own    the host's ScannerState up and its units[A].scannedTurn == 1 (precondition)
       pvp_scan_not_shared   the client's units[A].scannedTurn == -1 at every sample of the window and after it
Common cell (pvp_scan_common): every hash bucket EQUAL, desyncSeen false on both, no new file in this harness slot's
crash folder.
EVIDENCE only: S and A on both machines, the screen, the new host contexts.

Without the fix: every cell passes (the row is a guard). One EVIDENCE line, one PASS/FAIL line per cell, then the row
verdict. A boot step past its bound prints ONE CAPTURE line and fails the row "boot"; a staging step that fails fails
the row's cells. Run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when every cell
passes, else 2.

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
SCANNER_TILE, SCANNER_DIR = (19, 19, 0), 1    # Chebyshev 8 from A (27,12,0), 5 from S's start
WINDOW_S, SAMPLE_S = 3.0, 0.25
ROWS = (("pvp_scan", ("pvp_scan_marks_own", "pvp_scan_not_shared", "pvp_scan_common")),)


def row_pvp_scan(host, client, crash0):
    ev = {"turnSide": [(battle_state(gc).get("turn"), battle_state(gc).get("side")) for gc in (host, client)]}
    SS.staged("S and the scanner", lambda: SS.stage_scanner(host, client, S_ID, SCANNER_TILE, SCANNER_DIR, ev))
    up, own = SS.scan(host, client, host, S_ID, ev)
    samples, t0 = [], time.time()
    while time.time() - t0 < WINDOW_S:
        samples.append((round(time.time() - t0, 2), SS.mark(client)))
        time.sleep(SAMPLE_S)
    final = SS.mark(client)
    ev["window"] = samples
    cells = {"pvp_scan_marks_own": SS.own_cell(up, own, ev, "host", 1),
             "pvp_scan_not_shared": (
                 final == -1 and all(v == -1 for _t, v in samples),
                 f"client units[A].scannedTurn {final} after the {WINDOW_S} s window, samples "
                 f"{[v for _t, v in samples]} (want -1 throughout: the PvP opponent never gets the mark)"),
             "pvp_scan_common": G3F.common(host, client, crash0)}
    return cells, ev


def boot_pvp_battle():
    host = GameClient("host", None, make_user_dir("scan_share_pvp_host"))
    client = GameClient("client", None, make_user_dir("scan_share_pvp_client"))
    m = (host, client)
    try:
        try:
            G3F.guarded("pvp", lambda: BER.boot_pvp(host, client, KEY), m)
            G3F.guarded("pvp", lambda: G3F.reactions_zero(host, client), m)
            crash0 = session._crash_log_snapshot()
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE pvp line)")
        print(f"EVIDENCE boot: A {[SS.uview(gc, SS.A_ID) for gc in m]}; scannedTurn {SS.scanned_all(host, client)}",
              flush=True)
        return G3F.run_row("pvp_scan", ROWS[0][1], lambda: row_pvp_scan(host, client, crash0))
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_pvp_battle()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_scan_share_pvp: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
