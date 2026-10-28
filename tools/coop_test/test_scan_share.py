"""R5-U6 S-C rows SC1, SC2 (boot CC, classic co-op: the client commands soldiers 8 and 9, the host the other five): a
motion-scanner mark reaches the co-op partner (orchestrator R5-V5; QU6-4 (a): an untracked `bt_scan_mark` to a mapped
same-side seat, once per newly marked unit; the partner marks its own copy of the unit for the current turn). Today a scan
marks units on the scanning machine only.

Spec: docs repo rewrite/prompts/r5u6_pvp_options.md section (d) Stage S-C and (f) test_scan_share.py, AMENDMENT U6-1
(U6-1.4, U6-1.7). Constants: rewrite/r5u6-task0/sc/CONSTANTS.md (TASK 0 boots CCa = CCb on the probe build).
Probes (TEST-ONLY, TC1 / TC2): battle_state.units[].scannedTurn (vanilla's machine-local mark, -1 until a scan marks the
unit; never saved or hashed) and battle_set_unit_state {motionPoints} (the absolute setter the delta applier uses; applied
to both machines, client first). Vanilla's ScannerView marks a unit near the scanner whose motionPoints > 0 as it draws.

Boot CC (key 49063): test_reaction_prox's bring-up (roster seed 1, map seed 1, seat_count 2, pin_ai_neutral, every
player unit's reactions 0), copied with the key as a parameter.
  SC1  the client's scan marks the host's copy: C (8) on SC1_C_TILE facing A; the scanner into C's right hand by lever
       (both, ids equal); set_tu_both(C); A motionPoints 30 (both, client first); the client's real-UI USE SCANNER (TAB C,
       the right-hand box, key 49); its ScannerState; 1.0 s; KEY_CANCEL.
       SC1-own    the client's ScannerState up and its units[A].scannedTurn == 1 (precondition)
       SC1-share  the host's units[A].scannedTurn == 1 within 3 s
  SC2  the host's scan marks the client's copy: the END TURN cycle -> side 0 turn 2; A motionPoints 30 again (both; the
       value the cycle left is EVIDENCE); H (10) on SC2_H_TILE facing A with a scanner; set_tu_both(H); the host's real-UI
       USE SCANNER; its ScannerState; 1.0 s; KEY_CANCEL.
       SC2-own    the host's ScannerState up and its units[A].scannedTurn == 2 (precondition)
       SC2-share  the client's units[A].scannedTurn == 2 within 3 s
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane
crash folder. EVIDENCE only: the scanner unit and A on both machines, the screens, the new host contexts, the client's
intents.

RED on the probe build (commit C1): SC1-share, SC2-share; every other cell PASS. One EVIDENCE line per row, one PASS/FAIL
line per cell, then the row verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line
and fails every row "boot"; a staging step that fails fails its row's cells. run in the foreground to completion.
ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.
test_scan_share_pvp.py imports this file's helpers.

Run:  python tools/coop_test/test_scan_share.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_reaction_prox as RPX  # noqa: E402
from test_seat_pacing import tab_select  # noqa: E402
from test_turn_baton import RHAND_NTH, click_nth  # noqa: E402
from test_client_shoot import new_contexts, set_tu_both, place, RHAND_CENTRE, TU_MAX  # noqa: E402
from test_ai_origins import end_turn_cycle, bring_up_lobby_roster_pinned  # noqa: E402
from test_delta_core import both  # noqa: E402

KEY = "49063"
A_ID, C_ID, H_ID = RPX.A_ID, RPX.C_ID, 10     # the only alien (pinned, (27,12,0)); the client's scanner; the host's
SC1_C_TILE, SC1_C_DIR = (19, 19, 0), 1        # TASK 0 (U6-1.7 rule): Chebyshev 8 from A, 5 from C's start (14,19,1)
SC2_H_TILE, SC2_H_DIR = (19, 18, 0), 1        # the same rule for H (start (14,20,1)); C stands on (19,19,0)
MP = 30                                       # A's motion points by TC2 (ScannerView marks a unit with any > 0)
KEY_USE, KEY_CANCEL = 49, 27                  # the scanner menu's USE SCANNER row (keyBattleActionItem1); keyCancel
SCANNER_ROWS = 2                              # the scanner's action menu rows (TASK 0, CBT ROWS["scanner"])
SCREEN_S, DWELL_S, SHARE_S, STEP_S = 5, 1.0, 3, 30
CURSOR_TARGETING = (2, 3, 4, 5)
UK = ("x", "y", "z", "direction", "tu", "motionPoints", "scannedTurn", "isOut")
ROWS = (("SC1", ("SC1-own", "SC1-share", "SC1-common")), ("SC2", ("SC2-own", "SC2-share", "SC2-common")))


# ===================== shared helpers (test_scan_share_pvp imports them) =====================


def es(gc, key):
    return event_state(gc).get(key)


def uview(gc, uid):
    u = G3F.units(gc).get(uid) or {}
    return {k: u.get(k) for k in UK}


def mark(gc):
    """units[A].scannedTurn on `gc` (TC1)."""
    return (G3F.units(gc).get(A_ID) or {}).get("scannedTurn")


def staged(what, fn):
    """A staging step: its failure fails the row's cells with `staging: ...`."""
    try:
        return fn()
    except Exception as e:
        raise RuntimeError(f"staging ({what}): {type(e).__name__}: {str(e)[:400]}")


def mp_both(host, client, value):
    """TC2 on BOTH machines (client first, F607); units[A].motionPoints must read `value` on both."""
    both(host, client, {"cmd": "battle_set_unit_state", "unit": A_ID, "motionPoints": value}, ("unit",))
    got = [uview(host, A_ID)["motionPoints"], uview(client, A_ID)["motionPoints"]]
    assert got == [value, value], f"A motionPoints host/client {got} after the lever (want {value} on both)"
    return got


def stage_scanner(host, client, uid, tile, d, ev):
    """`uid` on `tile` facing `d` (S2: kept when already there), the scanner into its right hand (both, ids equal), its
    TU refilled, A's motion points MP (both). Fills `ev`."""
    ev["place"] = place(host, client, uid, tile, d)
    g = both(host, client, {"cmd": "battle_give", "unit": uid, "item": "STR_MOTION_SCANNER", "clear_hands": True},
             ("weaponId", "ammoId"))
    ev["scannerId"] = g.get("weaponId")
    ev["tu"] = set_tu_both(host, client, uid, TU_MAX)
    ev["mp"] = mp_both(host, client, MP)
    ev["staged"] = {"scanner": [uview(host, uid), uview(client, uid)], "A": [uview(host, A_ID), uview(client, A_ID)],
                    "turnSide": [(battle_state(gc).get("turn"), battle_state(gc).get("side")) for gc in (host, client)]}


def scan_press(gc, uid, ev):
    """`gc`'s real-UI USE SCANNER for its unit `uid` (CBT C24's order): TAB onto it (asserted), cancel a leftover aim,
    the right-hand box (self-verified), the menu's rows, key 49. Never retried."""
    ev["tab"] = tab_select(gc, uid)
    assert ev["tab"], f"TAB never selected {uid} on {gc.name} (selectedId {battle_state(gc).get('selectedId')})"
    if battle_state(gc).get("cursorType") in CURSOR_TARGETING:
        click_nth(gc, RHAND_NTH)
    r = click_nth(gc, RHAND_NTH)
    ev["rhand"] = (r.get("baseX"), r.get("baseY"))
    assert ev["rhand"] == RHAND_CENTRE, f"right-hand click on {gc.name} landed off the box: {r}"
    ok, _s = RM.wait_until(lambda: G3F.top(gc) == "ActionMenuState", SCREEN_S, 0.1)
    assert ok, f"no ActionMenuState on {gc.name} (stack {G3F.stack(gc)})"
    ev["rows"] = len([w for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", [])
                      if w.get("visible") and "ActionMenuItem" in w.get("type", "")])
    assert ev["rows"] == SCANNER_ROWS, f"scanner menu rows {ev['rows']} on {gc.name} (want {SCANNER_ROWS})"
    gc.ok({"cmd": "inject_input", "kind": "key", "key": KEY_USE})


def scan(host, client, gc, uid, ev):
    """The scan of `gc`'s unit `uid`: the press, `gc`'s ScannerState (bounded), DWELL_S, the marks on both machines, then
    KEY_CANCEL back to the battlescape and the host idle. Returns (screen up, `gc`'s own mark at the dwell's end)."""
    ctx0, sent0 = RM.ctxs(host), dict(es(client, "coopIntentsSent") or {})
    ev["press"] = {}
    staged("the real-UI USE SCANNER", lambda: scan_press(gc, uid, ev["press"]))
    up, ev["screenS"] = RM.wait_until(lambda: G3F.top(gc) == "ScannerState", SCREEN_S, 0.1)
    if up:
        time.sleep(DWELL_S)
    own = mark(gc)
    ev["screen"] = {"up": up, "stack": G3F.stack(gc)}
    ev["marksAtDwell"] = {"host": mark(host), "client": mark(client)}
    if G3F.top(gc) != "BattlescapeState":
        gc.ok({"cmd": "inject_input", "kind": "key", "key": KEY_CANCEL})
    ok, s = RM.wait_until(lambda: G3F.top(gc) == "BattlescapeState", SCREEN_S, 0.1)
    ev["afterCancel"] = {"top": G3F.top(gc), "s": s}
    RM.settle(host, client, ev)
    sent1 = es(client, "coopIntentsSent") or {}
    ev.update(newCtx=[RM.cv(c) for c in new_contexts(ctx0, RM.ctxs(host))],
              intentsSent={k: v - sent0.get(k, 0) for k, v in sent1.items() if v != sent0.get(k, 0)},
              scanner=[uview(host, uid), uview(client, uid)], A=[uview(host, A_ID), uview(client, A_ID)])
    return up, own


def own_cell(up, own, ev, who, turn):
    return (up and own == turn, f"{who} ScannerState up {up} in {ev['screenS']} s (want within {SCREEN_S} s); {who} "
                                f"units[A].scannedTurn {own} after {DWELL_S} s (want {turn})")


def share_cell(gc, turn, ev):
    ok, ev["shareS"] = RM.wait_until(lambda: mark(gc) == turn, SHARE_S, 0.1)
    got = mark(gc)
    return (ok, f"{gc.name} units[A].scannedTurn {got} {ev['shareS']} s after the cancel (want {turn} within {SHARE_S} s)")


# ===================== rows =====================


def row_sc1(host, client, crash0):
    ev = {}
    staged("C and the scanner", lambda: stage_scanner(host, client, C_ID, SC1_C_TILE, SC1_C_DIR, ev))
    up, own = scan(host, client, client, C_ID, ev)
    cells = {"SC1-own": own_cell(up, own, ev, "client", 1),
             "SC1-share": share_cell(host, 1, ev),
             "SC1-common": G3F.common(host, client, crash0)}
    return cells, ev


def row_sc2(host, client, crash0):
    ev = {}
    notes = []
    ev["turn0"] = end_turn_cycle(host, client, None, notes)
    ev["turnSide"] = [(battle_state(gc).get("turn"), battle_state(gc).get("side")) for gc in (host, client)]
    if notes or ev["turnSide"] != [(2, RPX.FACTION_PLAYER)] * 2:
        raise RuntimeError(f"staging (END TURN cycle): notes {notes}, (turn, side) {ev['turnSide']} (want (2, 0))")
    ev["afterCycle"] = {"A": [uview(host, A_ID), uview(client, A_ID)]}
    staged("H and the scanner", lambda: stage_scanner(host, client, H_ID, SC2_H_TILE, SC2_H_DIR, ev))
    up, own = scan(host, client, host, H_ID, ev)
    cells = {"SC2-own": own_cell(up, own, ev, "host", 2),
             "SC2-share": share_cell(client, 2, ev),
             "SC2-common": G3F.common(host, client, crash0)}
    return cells, ev


# ===================== boot CC =====================


def bring_up(host, client, key):
    """test_reaction_prox.boot, copied with the lobby key as a parameter."""
    bring_up_lobby_roster_pinned(host, client, key)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": RPX.SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == RPX.MAP_FP and cs.get("mapFingerprint") == RPX.MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r} (want {RPX.MAP_FP!r})")
    assert seated.get("soldierIds") == RPX.SEATED, f"seated {seated.get('soldierIds')} (want {RPX.SEATED})"
    pinned = pin_ai_neutral(host, client, tag="r5u6-cc")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (want [{A_ID}])"
    uh = session.units_by_id(hs)
    assert (uh.get(A_ID) or {}).get("type") == RPX.A_TYPE, f"A type {(uh.get(A_ID) or {}).get('type')}"
    for uid, u in sorted(uh.items()):
        if u.get("faction") == RPX.FACTION_PLAYER and not u.get("isOut"):
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
    session.wait_host_idle(host, client, timeout=STEP_S)
    assert_hash_clean(host, client, full=True, what="bring-up")
    return {"pinned": pinned, "A": [uview(host, A_ID), uview(client, A_ID)], "scannedTurn": scanned_all(host, client)}


def scanned_all(host, client):
    return {gc.name: {u["id"]: u.get("scannedTurn") for u in battle_state(gc).get("units", [])} for gc in (host, client)}


def boot_cc():
    host = GameClient("host", None, make_user_dir("r5u6_cc_host"))
    client = GameClient("client", None, make_user_dir("r5u6_cc_client"))
    m = (host, client)
    try:
        try:
            info = G3F.guarded("CC", lambda: bring_up(host, client, KEY), m)
            crash0 = session._crash_log_snapshot()
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE CC line)")
        print(f"EVIDENCE boot: {info}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("SC1", rows["SC1"], lambda: row_sc1(host, client, crash0))
        fails += G3F.run_row("SC2", rows["SC2"], lambda: row_sc2(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_cc()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_scan_share: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
