"""R5-U2 S-A rows AR3, LV3, CF3, AC3, AM3, LX3, GP3 (boot A3, gm3: the HOST plays the aliens, seat 0; the partner the
seven X-COM soldiers, seat 1): on its own turn the alien host gets X-COM's own-turn controls for its aliens (the selection
arrow, the Alt markers, map level up / down, Ctrl-F; Alt-C marks its own alien), and during the partner's turn its level
buttons do nothing, as vanilla's alien turn; the partner's controls are unchanged (design-D5, F12881; VL-U2-1).

Spec: docs repo rewrite/prompts/r5u2_pvp_presentation.md section (f) test_pvp_controls_gm3.py, with AMENDMENT U2-1
(U2-1.3 item 2: LX3-ctrlf is a guard, F14366) and the orchestrator rulings. Constants: rewrite/r5u2-task0/sa/CONSTANTS.md
(TASK 0 boots Ac, Ad on the A1 probe build; every pin equal). Helpers: test_pvp_controls.py (boot A2's file).

Boot A3 (key 48875, dirs r5u2_a3_host / _client): G3F.bring_up (gm3, STR_SMALL_SCOUT, map seed 1), every live unit's
reactions 0, RM.stage_tiles(RM.TILES), the partner's END TURN -> side 1 turn 1 (the host's A selected; one TAB +
tab_select first only if not, R-H27-A-1; TASK 0: selected at once).
  AR3, LV3, CF3, AC3, AM3   = boot A2's AR, LV, CF, AC, AM on the HOST (same cells, the host's probes; AC3-opp's
                              EVIDENCE: the partner's two values, machine-local)
  then the host's END TURN -> side 0 turn 2:
  LX3  the alien host's levels and Ctrl-F do nothing during the partner's turn
      LX3-level  the host's level-up key leaves camera.viewLevel unchanged (restored by level-down if it moved)
      LX3-ctrlf  Ctrl+F opens no InfoboxState within 2 s (guard: the host holds no unit, W2-H36 H3-off2)
  GP3  the X-COM partner's controls are unchanged (guard; the partner on its own turn)
      GP3-ctl    the partner's level up -> +1 and back; Ctrl+F -> the box, first line TEXT_FATAL (closed)
      GP3 is the last row.
DP(gc) = event_state(gc).drawProbe; "drawn now" = the record's frame equals DP.frame within DRAWN_S of polling (the host's
frame advances only on its own side, U2-1.3 item 1). Key chords: inject_input {key K, mod M}, then {kind modstate, mod
none}. Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the
lane crash folder.

RED on the unchanged product (commit A1): AR3-draw, LV3-up, CF3-box, AC3-own, AC3-opp, AM3-mark, LX3-level; every other
cell PASS (LX3-ctrlf and GP3-ctl are guards). One EVIDENCE line per row, one PASS/FAIL line per cell, then the row
verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails every row "boot"; a
staging step past its bound fails the rows that need it "staging". WV-D95: run in the foreground to completion. WV-D99 /
WV-D100: ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_controls_gm3.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
from session import battle_state  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
from test_seat_pacing import tab_select, SDLK_TAB  # noqa: E402
import test_pvp_controls as PC  # noqa: E402

KEY = "48875"
A_ID = PC.A_ID                    # the host's alien (gm3 seat 0, FACTION_HOSTILE)
GP3_SEL = 9                       # the partner's selectedId at side 0 turn 2 (TASK 0 Ac = Ad; EVIDENCE)
ROWS = (("AR3", ("AR3-pre", "AR3-draw", "AR3-common")), ("LV3", ("LV3-up", "LV3-down", "LV3-common")),
        ("CF3", ("CF3-box", "CF3-common")), ("AC3", ("AC3-own", "AC3-opp", "AC3-common")),
        ("AM3", ("AM3-mark", "AM3-common")), ("LX3", ("LX3-level", "LX3-ctrlf", "LX3-common")),
        ("GP3", ("GP3-ctl", "GP3-common")))


def select_a(host):
    """The host holds A at side 1 turn 1 (W2-H36); else ONE TAB + tab_select(A) (R-H27-A-1). Returns evidence."""
    ev = {"sel0": battle_state(host).get("selectedId")}
    if ev["sel0"] != A_ID:
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.15)
        ev["tab"] = tab_select(host, A_ID)
    ev["sel"] = battle_state(host).get("selectedId")
    return ev


def row_gp3(host, client, crash0, side_ok):
    if not side_ok:
        return {"GP3-ctl": (False, "staging (the host's END TURN -> side 0 turn 2 failed in LX3)"),
                "GP3-common": G3F.common(host, client, crash0)}, {}
    bad, ev = PC.xcom_ctl(client)
    ev["dp"] = PC.dp(client)
    ev["selEvidence"] = (ev["me"]["selectedId"], GP3_SEL)
    return {"GP3-ctl": (not bad, "; ".join(bad) or "the partner's level +1 and back, the box closed"),
            "GP3-common": G3F.common(host, client, crash0)}, ev


def boot_a3():
    host = GameClient("host", None, make_user_dir("r5u2_a3_host"))
    client = GameClient("client", None, make_user_dir("r5u2_a3_client"))
    m = (host, client)
    try:
        try:
            _boot, crash0 = G3F.bring_up(host, client, KEY, "A3")
            G3F.guarded("A3", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE A3 line)")
        try:
            st = PC.stage(host, client, client)
            st["select"] = G3F.guarded("staging", lambda: select_a(host), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        print(f"EVIDENCE staging: {st}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("AR3", rows["AR3"], lambda: PC.row_ar(host, client, host, client, crash0, "3"))
        fails += G3F.run_row("LV3", rows["LV3"], lambda: PC.row_lv(host, client, host, client, crash0, "3"))
        fails += G3F.run_row("CF3", rows["CF3"], lambda: PC.row_cf(host, client, host, client, crash0, "3"))
        fails += G3F.run_row("AC3", rows["AC3"], lambda: PC.row_ac(host, client, host, client, crash0, "3"))
        fails += G3F.run_row("AM3", rows["AM3"], lambda: PC.row_am(host, client, host, client, crash0, "3"))
        lx_ev = {}
        side_ok = PC.side2(host, client, host, lx_ev)
        if side_ok:
            fails += G3F.run_row("LX3", rows["LX3"], lambda: PC.row_lx(host, client, host, client, crash0, "3", lx_ev,
                                                                     " (guard: the host holds no unit)"))
        else:
            fails += G3F.verdict("LX3", rows["LX3"], {n: (False, f"staging (side change: {lx_ev.get('sideError')})")
                                                      for n in rows["LX3"]}, lx_ev)
        fails += G3F.run_row("GP3", rows["GP3"], lambda: row_gp3(host, client, crash0, side_ok))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_a3()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_controls_gm3: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
