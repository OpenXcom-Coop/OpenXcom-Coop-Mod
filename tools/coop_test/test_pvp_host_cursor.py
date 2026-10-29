"""PvP host cursor: in gm3 (the host plays the aliens) the host's own real-screen alien orders give back the map cursor
and the mouse pointer, as an X-COM player's do (vanilla's player-side popState aftermath for the side this seat
commands).

Boot (key 48698, dirs pvp_host_cursor_host / _client): G3F.bring_up (gm3, STR_SMALL_SCOUT, map seed 1); reactions 0
for every live unit; a plasma pistol for the alien A (test command, both machines, client first); A on STAGE_A facing
A_DIR; every bucket EQUAL; the partner's END TURN hands the turn to the host's aliens. The ids and tiles were measured
equal on two boots.
  side_start  the host's own side starts with the cursor and the pointer (GUARD): side_start-side, side_start-cursor,
     side_start-common.
  snap_keeps_aim  a real-screen snap keeps the aim; the next map click fires again: snap_keeps_aim-pre,
     snap_keeps_aim-shot, snap_keeps_aim-cursor, snap_keeps_aim-pointer, snap_keeps_aim-again, snap_keeps_aim-common.
  throw_cursor  a real-screen throw returns to the normal cursor: throw_cursor-pre, throw_cursor-throw,
     throw_cursor-cursor, throw_cursor-pointer, throw_cursor-common.
  walk_cursor  a real-screen walk gives the cursor back; the next map click walks: walk_cursor-pre, walk_cursor-walk,
     walk_cursor-cursor, walk_cursor-pointer, walk_cursor-again, walk_cursor-common.
  no_tu_walk  a walk that fails for time units shows vanilla's warning and gives the cursor back: no_tu_walk-pre,
     no_tu_walk-halt, no_tu_walk-warn, no_tu_walk-cursor, no_tu_walk-pointer, no_tu_walk-common.
Reset before each of snap_keeps_aim, throw_cursor, walk_cursor, no_tu_walk: ONE right click on NEXT-SOLDIER
(btnPrevSoldierClick: the one input the hidden pointer lets through, BattlescapeState::handle), then ONE TAB and
tab_select(A); `-pre` is a GUARD cell (it passes with and without the fix). Nothing touches the selection or the
targeting between an order and its cursor probe; the follow-up clicks (snap_keeps_aim-again, walk_cursor-again) are
plain left clicks after HOME. Every click: HOME, then the one-pass map_tile_click.
Common cell: every hash bucket EQUAL, desyncSeen false on both, no new file in this harness slot's crash folder.
Without the fix, snap_keeps_aim-cursor, snap_keeps_aim-pointer, snap_keeps_aim-again, throw_cursor-cursor,
throw_cursor-pointer, walk_cursor-cursor, walk_cursor-pointer, walk_cursor-again, no_tu_walk-warn, no_tu_walk-cursor
and no_tu_walk-pointer FAIL.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure. A boot
step past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails every row
"staging". ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_host_cursor.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
from repro_atom_side_begin import drive_side_change  # noqa: E402
from test_seat_pacing import tab_select, SDLK_TAB, SDLK_HOME  # noqa: E402
from test_turn_baton import RHAND_NTH, click_nth  # noqa: E402
from test_client_shoot import new_contexts, menu_rows, RHAND_CENTRE, set_tu_both  # noqa: E402
from test_delta_core import both  # noqa: E402
from test_delta_items import items_by_id  # noqa: E402
from test_host_combat import evs_since  # noqa: E402

KEY = "48698"
A_ID = 1000000                    # the host's alien (gm3 seat 0, FACTION_HOSTILE)
PISTOL, CLIP = "STR_PLASMA_PISTOL", "STR_PLASMA_PISTOL_CLIP"
STAGE_A, A_DIR = (20, 19, 0), 4   # open ground
FLOOR_TARGET = (24, 19, 0)             # floor target 4 tiles east of STAGE_A
WALK_DEST = (20, 18, 0)              # distance-1 walk (path_probe steps 1, tuCost 4, both machines)
A_TU = 54                         # A's TU at the start of the host's side
SIDE_HOSTILE = 1
KEY_SNAP, KEY_THROW = 50, 53      # keyBattleActionItem2 / keyBattleActionItem5 (ActionMenuState.cpp :84, :134)
MENU_ROWS = 4                     # THROW, AUTO, SNAP, AIMED
CT_NORMAL, CT_AIM, CT_THROW = 1, 2, 5
SNAP_SEED, AGAIN_SEED, THROW_SEED = 1, 2, 3
SNAP_KINDS = ["turn", "shot", "hit", "bt_action_end"]
THROW_KINDS = ["shot", "bt_action_end"]
TEXT_NO_TU = "Not Enough Time Units!"   # xcom1 STR_NOT_ENOUGH_TIME_UNITS (en-US)
AGAIN_S = 5.0                     # the only fixed window: no second order without the fix (ends early with it)
STEP_S = 30
ROWS = (("side_start", ("side_start-side", "side_start-cursor", "side_start-common")),
        ("snap_keeps_aim", ("snap_keeps_aim-pre", "snap_keeps_aim-shot", "snap_keeps_aim-cursor",
                            "snap_keeps_aim-pointer", "snap_keeps_aim-again", "snap_keeps_aim-common")),
        ("throw_cursor", ("throw_cursor-pre", "throw_cursor-throw", "throw_cursor-cursor", "throw_cursor-pointer",
                          "throw_cursor-common")),
        ("walk_cursor", ("walk_cursor-pre", "walk_cursor-walk", "walk_cursor-cursor", "walk_cursor-pointer",
                         "walk_cursor-again", "walk_cursor-common")),
        ("no_tu_walk", ("no_tu_walk-pre", "no_tu_walk-halt", "no_tu_walk-warn", "no_tu_walk-cursor",
                        "no_tu_walk-pointer", "no_tu_walk-common")))


def es(gc, key):
    return event_state(gc).get(key)


def probe(gc):
    """The "cursor" probe: this machine's cursorType, cursorVisible, selectedId, warningText."""
    b = battle_state(gc)
    return {k: b.get(k) for k in ("cursorType", "cursorVisible", "selectedId", "warningText")}


def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while True:
        if pred():
            return True, round(time.time() - t0, 2)
        if time.time() - t0 >= timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)


def idle(host, client, ev):
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]


def icon_nth(gc, col_i, row_i):
    """click_widget nth of the icon in column `col_i`, row `row_i` (0 upper) of the seven 32x16 columns
    (test_input_gating's geometric rule; NEXT-SOLDIER = (4, 0), BattlescapeState.cpp :164)."""
    ws = gc.cmd({"cmd": "list_widgets"}).get("widgets", [])
    cands = [w for w in ws if w.get("w") == 32 and w.get("h") == 16 and w.get("interactive") and w.get("visible")]
    xs = sorted({w["x"] for w in cands})
    assert len(xs) == 7, f"icon columns {xs} (want 7)"
    col = sorted([w for w in cands if w["x"] == xs[col_i]], key=lambda w: w["y"])
    assert len(col) == 2, f"icon column {col_i}: {col}"
    nth = 0
    for w in ws:
        if w["idx"] == col[row_i]["idx"]:
            return nth
        if w.get("visible") and w.get("interactive"):
            nth += 1
    raise AssertionError("icon vanished")


def reset(host, ev):
    """ONE right click on NEXT-SOLDIER, ONE TAB, tab_select(A). EVIDENCE: the probe before / after."""
    ev["resetBefore"] = probe(host)
    click_nth(host, icon_nth(host, 4, 0), "right")
    ev["resetAfterRight"] = probe(host)
    host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
    time.sleep(0.15)
    tab_select(host, A_ID)
    ev["resetAfter"] = p = probe(host)
    return (p["selectedId"] == A_ID and p["cursorType"] == CT_NORMAL and p["cursorVisible"] is True,
            f"after the reset host {p} (want selectedId {A_ID}, cursorType {CT_NORMAL}, cursorVisible true)")


def click(gc, tile, before=None):
    """HOME, `before` (the host's set_seed, right before the click it governs), ONE map_tile_click."""
    gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
    time.sleep(0.15)
    if before:
        before()
    r = gc.cmd({"cmd": "map_tile_click", "x": tile[0], "y": tile[1], "z": tile[2]})
    assert r.get("verified") and r.get("clicked"), f"map_tile_click {tile} on {gc.name}: {r}"


def seed(gc, s):
    return lambda: gc.ok({"cmd": "set_seed", "seed": s})


def hand_menu(host, key, want_cursor, ev):
    """The host's right-hand box -> ActionMenuState (MENU_ROWS rows), `key` -> BattlescapeState, cursor `want_cursor`
    (HC open_hand_menu_host's pattern with the actor as a parameter; no aim-cancel click: the reset did it)."""
    r = click_nth(host, RHAND_NTH)
    assert (r.get("baseX"), r.get("baseY")) == RHAND_CENTRE, f"right-hand click landed off the box: {r}"
    ok, _ = wait_until(lambda: G3F.top(host) == "ActionMenuState", 5)
    assert ok, f"host ActionMenuState not on top after the hand click (stack {G3F.stack(host)})"
    ev["menuRows"] = rows = menu_rows(host)
    assert rows == MENU_ROWS, f"action menu rows {rows} (want {MENU_ROWS})"
    host.ok({"cmd": "inject_input", "kind": "key", "key": key})
    ok, _ = wait_until(lambda: G3F.top(host) == "BattlescapeState", 5)
    assert ok, f"host BattlescapeState not on top after key {key} (stack {G3F.stack(host)})"
    ev["cursorAfterKey"] = c = probe(host)
    assert c["cursorType"] == want_cursor, f"key {key}: host cursorType {c['cursorType']} (want {want_cursor})"


def order(host, client, fire, ev, timeout=STEP_S):
    """Run `fire()` (one click), wait (bounded) for one new host closedContexts entry, then host idle. Returns the new
    contexts as (origin, kind, actorId) and both machines' ev (seq, kind) lists since the click."""
    b_ctx, seq0 = es(host, "closedContexts") or [], es(host, "lastSeqEmitted") or 0
    fire()
    _, ev["ctxS"] = wait_until(lambda: new_contexts(b_ctx, es(host, "closedContexts")), timeout)
    idle(host, client, ev)
    new = [(c.get("origin"), c.get("kind"), c.get("actorId")) for c in new_contexts(b_ctx, es(host, "closedContexts"))]
    kinds = [[(e["seq"], e["kind"]) for e in evs_since(gc, seq0)] for gc in (host, client)]
    ev["newCtx"], ev["kinds"] = new, kinds
    return new, kinds


def evidence(host, client, ev):
    ev["partner"] = probe(client)
    ev["camera"] = (es(host, "camera") or {}).get("offset")
    ev["aTu"] = [(G3F.units(gc).get(A_ID) or {}).get("tu") for gc in (host, client)]


def order_cell(new, kinds, want_kind, want_kinds):
    names = [k for _, k in kinds[0]]
    return (new == [("host", want_kind, A_ID)] and names == want_kinds and kinds[1] == kinds[0],
            f"new host contexts {new} (want exactly [('host', '{want_kind}', {A_ID})]); ev kinds host {kinds[0]} (want "
            f"{want_kinds}), partner {kinds[1]} (want the host's)")


def cursor_cells(row, p, want):
    return {f"{row}-cursor": (p["cursorType"] == want, f"host cursorType {p['cursorType']} after the order (want {want})"),
            f"{row}-pointer": (p["cursorVisible"] is True,
                               f"host cursorVisible {p['cursorVisible']} after the order (want true)")}


def again(host, client, kind, ev):
    """The follow-up click is already fired; the AGAIN_S window for one new host context of `kind` (ends early)."""
    b_ctx = ev.pop("bAgain")
    ok, ev["againS"] = wait_until(lambda: new_contexts(b_ctx, es(host, "closedContexts")), AGAIN_S, 0.2)
    if ok:
        idle(host, client, ev)
    new = [(c.get("origin"), c.get("kind"), c.get("actorId")) for c in new_contexts(b_ctx, es(host, "closedContexts"))]
    ev["againCtx"] = new
    return new == [("host", kind, A_ID)], new


# ===================== rows =====================


def row_side_start(host, client, crash0, cells, ev):
    st = [(battle_state(gc).get("side"), battle_state(gc).get("turn")) for gc in (host, client)]
    p = ev["host"] = probe(host)
    cells["side_start-side"] = (st == [(1, 1), (1, 1)], f"(side, turn) host/partner {st} (want (1, 1) on both)")
    cells["side_start-cursor"] = ((p["cursorType"], p["cursorVisible"], p["selectedId"]) == (CT_NORMAL, True, A_ID),
                                  f"host {p} at its side start (want cursorType 1, cursorVisible true, selectedId "
                                  f"{A_ID})")
    cells["side_start-common"] = G3F.common(host, client, crash0)


def row_snap_keeps_aim(host, client, crash0, cells, ev):
    cells["snap_keeps_aim-pre"] = reset(host, ev)
    ev["tu"] = set_tu_both(host, client, A_ID, A_TU)
    hand_menu(host, KEY_SNAP, CT_AIM, ev)
    new, kinds = order(host, client, lambda: click(host, FLOOR_TARGET, seed(host, SNAP_SEED)), ev)
    p = ev["afterOrder"] = probe(host)
    evidence(host, client, ev)
    cells["snap_keeps_aim-shot"] = order_cell(new, kinds, "shoot", SNAP_KINDS)
    cells.update(cursor_cells("snap_keeps_aim", p, CT_AIM))
    set_tu_both(host, client, A_ID, A_TU)
    ev["bAgain"] = es(host, "closedContexts") or []
    click(host, FLOOR_TARGET, seed(host, AGAIN_SEED))
    ok, new2 = again(host, client, "shoot", ev)
    cells["snap_keeps_aim-again"] = (ok, f"after one left click on {FLOOR_TARGET} (no TAB) new host contexts {new2} "
                                         f"within {AGAIN_S} s (want exactly [('host', 'shoot', {A_ID})])")
    cells["snap_keeps_aim-common"] = G3F.common(host, client, crash0)


def row_throw_cursor(host, client, crash0, cells, ev):
    cells["throw_cursor-pre"] = reset(host, ev)
    g = both(host, client, {"cmd": "battle_give", "unit": A_ID, "item": PISTOL, "ammo": CLIP, "slot": "right",
                            "clear_hands": True}, ("weaponId", "ammoId"))
    wid = ev["pistol"] = g["weaponId"]
    ev["tu"] = set_tu_both(host, client, A_ID, A_TU)
    hand_menu(host, KEY_THROW, CT_THROW, ev)
    new, kinds = order(host, client, lambda: click(host, FLOOR_TARGET, seed(host, THROW_SEED)), ev)
    p = ev["afterOrder"] = probe(host)
    evidence(host, client, ev)
    it = [items_by_id(gc).get(wid) or {} for gc in (host, client)]
    ground = [(i.get("owner"), i.get("onTile"), (i.get("tx"), i.get("ty"), i.get("tz"))) for i in it]
    ev["thrown"] = ground
    ok, detail = order_cell(new, kinds, "throw", THROW_KINDS)
    item_ok = all(o in (-1, None) and on is True for o, on, _ in ground) and ground[0][2] == ground[1][2]
    cells["throw_cursor-throw"] = (ok and item_ok, f"{detail}; pistol {wid} (owner, onTile, tile) host/partner "
                                                   f"{ground} (want no owner, on a tile, the same tile on both)")
    cells.update(cursor_cells("throw_cursor", p, CT_NORMAL))
    cells["throw_cursor-common"] = G3F.common(host, client, crash0)


def row_walk_cursor(host, client, crash0, cells, ev):
    cells["walk_cursor-pre"] = reset(host, ev)
    ev["tu"] = set_tu_both(host, client, A_ID, A_TU)
    new, kinds = order(host, client, lambda: click(host, WALK_DEST), ev)
    done = G3F.walk_done(host, client, A_ID, WALK_DEST, ev)
    p = ev["afterOrder"] = probe(host)
    evidence(host, client, ev)
    pa = [G3F.pos(gc, A_ID) for gc in (host, client)]
    cells["walk_cursor-walk"] = (new == [("host", "walk", A_ID)] and done and pa == [WALK_DEST, WALK_DEST],
                                 f"new host contexts {new} (want exactly [('host', 'walk', {A_ID})]); A host/partner "
                                 f"{pa} (want {WALK_DEST} on both; {ev.get('walkS')} s)")
    cells.update(cursor_cells("walk_cursor", p, CT_NORMAL))
    ev["bAgain"] = es(host, "closedContexts") or []
    click(host, STAGE_A)
    ok, new2 = again(host, client, "walk", ev)
    back = G3F.walk_done(host, client, A_ID, STAGE_A, {}) if ok else False
    pa2 = [G3F.pos(gc, A_ID) for gc in (host, client)]
    cells["walk_cursor-again"] = (ok and back and pa2 == [STAGE_A, STAGE_A],
                                  f"after one left click on {STAGE_A} (no TAB) new host contexts {new2} within "
                                  f"{AGAIN_S} s (want exactly [('host', 'walk', {A_ID})]); A host/partner {pa2} (want "
                                  f"{STAGE_A} on both)")
    cells["walk_cursor-common"] = G3F.common(host, client, crash0)


def row_no_tu_walk(host, client, crash0, cells, ev):
    pre_ok, pre = reset(host, ev)
    ev["clear"] = host.cmd({"cmd": "clear_warning"}).get("warningText")
    w0 = battle_state(host).get("warningText")
    cells["no_tu_walk-pre"] = (pre_ok and w0 == "", f"{pre}; warningText {w0!r} after clear_warning (want '')")
    ev["tu"] = set_tu_both(host, client, A_ID, 0)
    a_at = G3F.pos(host, A_ID)
    # the tile of {STAGE_A, WALK_DEST} A is not on (it differs with and without the fix)
    f_dest = WALK_DEST if a_at == STAGE_A else STAGE_A
    ev["from"], ev["to"] = a_at, f_dest
    new, kinds = order(host, client, lambda: click(host, f_dest), ev)
    p = ev["afterOrder"] = probe(host)
    evidence(host, client, ev)
    pa = [G3F.pos(gc, A_ID) for gc in (host, client)]
    lw = es(host, "lastWalk") or {}
    ev["lastWalk"] = {k: lw.get(k) for k in ("actionId", "origin", "halted", "reason", "steps")}
    cells["no_tu_walk-halt"] = (new == [("host", "walk", A_ID)] and a_at in (STAGE_A, WALK_DEST) and pa == [a_at, a_at]
                                and lw.get("halted") is True and lw.get("reason") == "no_tu",
                                f"new host contexts {new} (want exactly [('host', 'walk', {A_ID})]); A host/partner "
                                f"{pa} (want unchanged {a_at}); host lastWalk halted {lw.get('halted')} reason "
                                f"{lw.get('reason')!r} (want true, 'no_tu')")
    cells["no_tu_walk-warn"] = (p["warningText"] == TEXT_NO_TU,
                                f"host warningText {p['warningText']!r} (want {TEXT_NO_TU!r})")
    cells.update(cursor_cells("no_tu_walk", p, CT_NORMAL))
    cells["no_tu_walk-common"] = G3F.common(host, client, crash0)


def run_row(row, order_, fn):
    """One row: `fn(cells, ev)` fills the cells it reaches; an exception fails every cell it did not reach."""
    cells, ev = {}, {}
    try:
        fn(cells, ev)
    except Exception as e:
        ev["error"] = f"{type(e).__name__}: {str(e)[:600]}"
    return G3F.verdict(row, order_, cells, ev)


# ===================== boot =====================


def stage(host, client):
    """Reactions 0, the pistol, A on STAGE_A (never onto its own tile), every bucket EQUAL, the side change."""
    G3F.reactions_zero(host, client)
    both(host, client, {"cmd": "battle_give", "unit": A_ID, "item": PISTOL, "ammo": CLIP, "slot": "right",
                        "clear_hands": True}, ("weaponId", "ammoId"))
    if [G3F.pos(gc, A_ID) for gc in (host, client)] != [STAGE_A, STAGE_A]:
        G3F.tele_both(host, client, A_ID, STAGE_A, A_DIR)
    session.wait_host_idle(host, client, timeout=STEP_S)
    h = G3F.hash_now(host, client)
    assert h == "all buckets EQUAL", f"staged: {h}"
    client.ok({"cmd": "battle_action", "action": "end_turn_button"})
    drive_side_change(host, client, SIDE_HOSTILE, timeout=STEP_S)
    session.wait_host_idle(host, client, timeout=STEP_S)


def run_boot():
    host = GameClient("host", None, make_user_dir("pvp_host_cursor_host"))
    client = GameClient("client", None, make_user_dir("pvp_host_cursor_client"))
    try:
        try:
            _boot, crash0 = G3F.bring_up(host, client, KEY, "boot")
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        try:
            G3F.guarded("boot staging", lambda: stage(host, client), (host, client))
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE boot staging line)")
        rows = dict(ROWS)
        fails = 0
        for name, fn in (("side_start", row_side_start), ("snap_keeps_aim", row_snap_keeps_aim),
                         ("throw_cursor", row_throw_cursor), ("walk_cursor", row_walk_cursor),
                         ("no_tu_walk", row_no_tu_walk)):
            fails += run_row(name, rows[name], lambda cells, ev, fn=fn: fn(host, client, crash0, cells, ev))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_host_cursor: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
