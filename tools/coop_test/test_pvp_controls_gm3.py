"""test_pvp_controls_gm3.py: the alien host's battle controls in a gm3 PvP battle (the HOST plays the aliens, seat 0;
the partner the seven X-COM soldiers, seat 1). On its own turn the alien host gets X-COM's own-turn controls for its
aliens (the selection arrow, the Alt markers, map level up / down, Ctrl-F; Alt-C marks its own alien), and during the
partner's turn its level buttons do nothing, as on vanilla's alien turn; the partner's controls are unchanged.

xcom_turn_inert_gm3-ctrlf is a guard. The constants below were measured on two boots with the draw probe and agreed.
Helpers: test_pvp_controls.py.

The boot (key 48875, dirs pvp_controls_gm3_host / _client): G3F.bring_up (gm3, STR_SMALL_SCOUT, map seed 1), every live
unit's reactions 0, RM.stage_tiles(RM.TILES), the partner's END TURN -> side 1 turn 1 (the host's A selected; one TAB +
tab_select first only if not; on both measured boots A was selected at once).
  own_arrow_gm3, own_levels_gm3, fatal_box_gm3, own_marker_gm3, marker_overlay_gm3 = test_pvp_controls' own_arrow,
      own_levels, fatal_box, own_marker, marker_overlay on the HOST (same cells, the host's probes; own_marker_gm3-opp's
      EVIDENCE: the partner's two values, machine-local)
  then the host's END TURN -> side 0 turn 2:
  xcom_turn_inert_gm3  the alien host's levels and Ctrl-F do nothing during the partner's turn
      xcom_turn_inert_gm3-level  the host's level-up key leaves camera.viewLevel unchanged (restored by level-down if it
          moved)
      xcom_turn_inert_gm3-ctrlf  Ctrl+F opens no InfoboxState within 2 s (guard: the host holds no unit)
  partner_controls  the X-COM partner's controls are unchanged (guard; the partner on its own turn)
      partner_controls-ctl  the partner's level up -> +1 and back; Ctrl+F -> the box, first line TEXT_FATAL (closed)
      partner_controls is the last row.
DP(gc) = event_state(gc).drawProbe; "drawn now" = the record's frame equals DP.frame within DRAWN_S of polling (the
host's frame advances only on its own side). Key chords: inject_input {key K, mod M}, then {kind modstate, mod none}.
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane
crash folder.

Without the fix, own_arrow_gm3-draw, own_levels_gm3-up, fatal_box_gm3-box, own_marker_gm3-own, own_marker_gm3-opp,
marker_overlay_gm3-mark and xcom_turn_inert_gm3-level FAIL; every other cell PASSes (xcom_turn_inert_gm3-ctrlf and
partner_controls-ctl are guards). One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every
row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step
past its bound fails the rows that need it "staging". Run in the foreground to completion. ONE run is the result, no
skip path; exit 0 only when every cell passes, else 2.

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
PARTNER_SELECTED_ID = 9           # the partner's selectedId at side 0 turn 2 (the same on two boots; EVIDENCE)
ROWS = (("own_arrow_gm3", ("own_arrow_gm3-pre", "own_arrow_gm3-draw", "own_arrow_gm3-common")),
        ("own_levels_gm3", ("own_levels_gm3-up", "own_levels_gm3-down", "own_levels_gm3-common")),
        ("fatal_box_gm3", ("fatal_box_gm3-box", "fatal_box_gm3-common")),
        ("own_marker_gm3", ("own_marker_gm3-own", "own_marker_gm3-opp", "own_marker_gm3-common")),
        ("marker_overlay_gm3", ("marker_overlay_gm3-mark", "marker_overlay_gm3-common")),
        ("xcom_turn_inert_gm3", ("xcom_turn_inert_gm3-level", "xcom_turn_inert_gm3-ctrlf",
                                 "xcom_turn_inert_gm3-common")),
        ("partner_controls", ("partner_controls-ctl", "partner_controls-common")))


def select_a(host):
    """The host holds A at side 1 turn 1; else ONE TAB + tab_select(A). Returns evidence."""
    ev = {"sel0": battle_state(host).get("selectedId")}
    if ev["sel0"] != A_ID:
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.15)
        ev["tab"] = tab_select(host, A_ID)
    ev["sel"] = battle_state(host).get("selectedId")
    return ev


def row_partner_controls(host, client, crash0, side_ok):
    if not side_ok:
        return {"partner_controls-ctl": (False, "staging (the host's END TURN -> side 0 turn 2 failed in "
                                                "xcom_turn_inert_gm3)"),
                "partner_controls-common": G3F.common(host, client, crash0)}, {}
    bad, ev = PC.xcom_ctl(client)
    ev["dp"] = PC.dp(client)
    ev["selEvidence"] = (ev["me"]["selectedId"], PARTNER_SELECTED_ID)
    return {"partner_controls-ctl": (not bad, "; ".join(bad) or "the partner's level +1 and back, the box closed"),
            "partner_controls-common": G3F.common(host, client, crash0)}, ev


def run_boot():
    host = GameClient("host", None, make_user_dir("pvp_controls_gm3_host"))
    client = GameClient("client", None, make_user_dir("pvp_controls_gm3_client"))
    m = (host, client)
    try:
        try:
            _boot, crash0 = G3F.bring_up(host, client, KEY, "boot")
            G3F.guarded("boot", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        try:
            st = PC.stage(host, client, client)
            st["select"] = G3F.guarded("staging", lambda: select_a(host), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        print(f"EVIDENCE staging: {st}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("own_arrow_gm3", rows["own_arrow_gm3"],
                            lambda: PC.row_own_arrow(host, client, host, client, crash0, "_gm3"))
        fails += G3F.run_row("own_levels_gm3", rows["own_levels_gm3"],
                             lambda: PC.row_own_levels(host, client, host, client, crash0, "_gm3"))
        fails += G3F.run_row("fatal_box_gm3", rows["fatal_box_gm3"],
                             lambda: PC.row_fatal_box(host, client, host, client, crash0, "_gm3"))
        fails += G3F.run_row("own_marker_gm3", rows["own_marker_gm3"],
                             lambda: PC.row_own_marker(host, client, host, client, crash0, "_gm3"))
        fails += G3F.run_row("marker_overlay_gm3", rows["marker_overlay_gm3"],
                             lambda: PC.row_marker_overlay(host, client, host, client, crash0, "_gm3"))
        inert_ev = {}
        side_ok = PC.side2(host, client, host, inert_ev)
        if side_ok:
            fails += G3F.run_row("xcom_turn_inert_gm3", rows["xcom_turn_inert_gm3"],
                                 lambda: PC.row_xcom_turn_inert(host, client, host, client, crash0, "_gm3", inert_ev,
                                                                " (guard: the host holds no unit)"))
        else:
            fails += G3F.verdict("xcom_turn_inert_gm3", rows["xcom_turn_inert_gm3"],
                                 {n: (False, f"staging (side change: {inert_ev.get('sideError')})")
                                  for n in rows["xcom_turn_inert_gm3"]}, inert_ev)
        fails += G3F.run_row("partner_controls", rows["partner_controls"],
                             lambda: row_partner_controls(host, client, crash0, side_ok))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_controls_gm3: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
