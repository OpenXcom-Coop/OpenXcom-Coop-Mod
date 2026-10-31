"""test_pvp_controls.py: the alien player's battle controls in a gm2 PvP battle (the client plays the aliens, seat 1;
the host the seven X-COM soldiers, seat 0). On its own turn the alien player gets X-COM's own-turn controls for its
aliens (the selection arrow, the Alt markers, map level up / down, Ctrl-F; Alt-C marks its own alien), and during
X-COM's turn its level buttons and Ctrl-F do nothing, as on vanilla's alien turn.

The constants below were measured on two boots with the draw probe and agreed.

The boot (key 48874, dirs pvp_controls_host / _client): BER.boot_pvp (STR_SMALL_SCOUT, map seed 1, gamemode 2), every
live unit's reactions 0, RM.stage_tiles(RM.TILES) (A (15,2,0) facing 4), the host's END TURN -> side 1 turn 1.
  own_arrow  the alien player's selection arrow on its own turn (side 1 turn 1, the client idle)
      own_arrow-pre    the client's selectedId A, cursorType != 0 (precondition)
      own_arrow-draw   DP(client).arrowUnit == A drawn now
  own_levels  map level up / down on its own turn (the client's camera viewLevel 0 first)
      own_levels-up    after the level-up key (280) the client's camera.viewLevel 1
      own_levels-down  after the level-down key (281) it is 0
  fatal_box  Ctrl+F on the client
      fatal_box-box    the client's top InfoboxState within 3 s, first line TEXT_FATAL; closed after (dismiss_popup)
  own_marker  Alt-C marks its own alien, not an X-COM soldier: HC.stage_camera(client, A tile), map_tile_click_pos {A
      tile} verified, Alt+C; then the same on 9's tile
      own_marker-own   the client's units[A].customMarker 1
      own_marker-opp   the client's units[9].customMarker 0 (EVIDENCE: the host's two values, 0 / 0, machine-local)
  marker_overlay  the Alt overlay shows its own marked alien: set_touch_modifiers {alt true} on the client, then {alt
      false}
      marker_overlay-mark  DP(client).marks holds {unit A, kind custom} drawn now
  xcom_turn_inert  levels and Ctrl-F do nothing during X-COM's turn: the client's END TURN -> side 0 turn 2 (A stays
      selected)
      xcom_turn_inert-level  the client's level-up key leaves camera.viewLevel unchanged (restored by level-down if it
          moved)
      xcom_turn_inert-ctrlf  Ctrl+F opens no InfoboxState within 2 s (closed if it opens)
  xcom_controls  the X-COM host's controls are unchanged (guard; side 0 turn 2, the host's own turn)
      xcom_controls-ctl  the host's selectedId HOST_SELECTED_ID; DP(host).arrowUnit == HOST_SELECTED_ID drawn now; the
          host's level up -> +1 and back; Ctrl+F -> the box (closed); Alt+C on HOST_SELECTED_ID's tile -> the host's
          units[HOST_SELECTED_ID].customMarker 1
      xcom_controls is the last row.
DP(gc) = event_state(gc).drawProbe (the test-only draw probe); "drawn now" = the record's frame equals DP.frame within
DRAWN_S of polling. Off its own side a PvP machine shows HIDDEN MOVEMENT and its frame stands still: every DP cell reads
the machine whose side plays. Key chords: inject_input {key K, mod M}, then {kind modstate, mod none}. Common cell after
each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane crash folder.

Without the fix, own_arrow-draw, own_levels-up, fatal_box-box, own_marker-own, own_marker-opp, marker_overlay-mark,
xcom_turn_inert-level and xcom_turn_inert-ctrlf FAIL; every other cell PASSes. One EVIDENCE line per row, one PASS/FAIL
line per cell, then the row verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line
and fails every row "boot"; a staging step past its bound fails the rows that need it "staging". Run in the foreground
to completion. ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_controls.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import session  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_host_combat as HC  # noqa: E402

KEY = "48874"
A_ID, S9_ID = RM.A_ID, 9          # the client's alien (seat 1); the X-COM soldier own_marker's second Alt+C lands on
A_TILE, S9_TILE = RM.TILES[A_ID][0], RM.TILES[S9_ID][0]   # (15,2,0), (18,6,0) (both verified clickable)
HOST_SELECTED_ID = 8              # the host's selectedId at side 0 turn 2 (the same on two boots), on (15,9,0)
KEY_LEVEL_UP, KEY_LEVEL_DOWN = 280, 281   # keyBattleLevelUp / Down in both options.cfg
KEY_F, KEY_C = 102, 99            # Ctrl+F (fatal wounds), Alt+C (custom marker)
TEXT_FATAL = "FATAL WOUNDS"       # the box's first line (STR_FATAL_WOUNDS, en-US)
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
DRAWN_S, BOX_S, NOBOX_S, LEVEL_S, SETTLE_S = 3, 3, 2, 1.0, 2
POLL = 0.1
ROWS = (("own_arrow", ("own_arrow-pre", "own_arrow-draw", "own_arrow-common")),
        ("own_levels", ("own_levels-up", "own_levels-down", "own_levels-common")),
        ("fatal_box", ("fatal_box-box", "fatal_box-common")),
        ("own_marker", ("own_marker-own", "own_marker-opp", "own_marker-common")),
        ("marker_overlay", ("marker_overlay-mark", "marker_overlay-common")),
        ("xcom_turn_inert", ("xcom_turn_inert-level", "xcom_turn_inert-ctrlf", "xcom_turn_inert-common")),
        ("xcom_controls", ("xcom_controls-ctl", "xcom_controls-common")))


# ===================== shared helpers (test_pvp_controls_gm3 imports them) =====================


def dp(gc):
    return event_state(gc).get("drawProbe") or {}


def bsv(gc):
    b = battle_state(gc)
    return {k: b.get(k) for k in ("side", "turn", "selectedId", "cursorType", "cursorVisible", "hiddenMovementShown")}


def view_level(gc):
    return (event_state(gc).get("camera") or {}).get("viewLevel")


def marker(gc, uid):
    return (G3F.units(gc).get(uid) or {}).get("customMarker")


def poll(pred, timeout, interval=POLL):
    """Bounded: (True, secs, last value) once pred() is truthy, else (False, timeout, last value)."""
    t0, last = time.time(), None
    while True:
        last = pred()
        if last:
            return True, round(time.time() - t0, 2), last
        if time.time() - t0 >= timeout:
            return False, round(time.time() - t0, 2), last
        time.sleep(interval)


def arrow_now(gc, uid):
    """DP(gc).arrowUnit == uid drawn in the latest frame, polled up to DRAWN_S; returns (ok, secs, record)."""
    rec = {}

    def drawn():
        rec.update(dp(gc))
        return rec.get("arrowUnit") == uid and rec.get("arrowFrame") == rec.get("frame")
    ok, secs, _ = poll(drawn, DRAWN_S)
    return ok, secs, dict(rec)


def mark_now(gc, uid, kind):
    """DP(gc).marks holds {unit uid, kind} drawn in the latest frame, polled up to DRAWN_S."""
    rec = {}

    def drawn():
        rec.update(dp(gc))
        return any(m.get("unit") == uid and m.get("kind") == kind and m.get("frame") == rec.get("frame")
                   for m in rec.get("marks") or [])
    ok, secs, _ = poll(drawn, DRAWN_S)
    latest = [m for m in rec.get("marks") or [] if m.get("frame") == rec.get("frame")]
    return ok, secs, {"frame": rec.get("frame"), "latestMarks": latest, "marks": rec.get("marks")}


def frames_after(gc, n=3):
    """The machine whose side plays: wait for n more drawTerrain frames (its event loop ran past a pushed key)."""
    f0 = dp(gc).get("frame") or 0
    return poll(lambda: (dp(gc).get("frame") or 0) >= f0 + n, SETTLE_S)[:2]


def chord(gc, key, mod):
    """inject_input {key, mod}, then {kind modstate, mod none} (the latch cleared at once)."""
    r1 = gc.cmd({"cmd": "inject_input", "kind": "key", "key": key, "mod": mod})
    r2 = gc.cmd({"cmd": "inject_input", "kind": "modstate", "mod": "none"})
    assert r1.get("ok") and r2.get("ok"), f"{gc.name} chord {key}+{mod}: {r1} / {r2}"


def level_key(gc, key, want=None):
    """One level key on gc; polls camera.viewLevel up to LEVEL_S for `want` (None: for any change). Returns
    (before, after, secs)."""
    v0 = view_level(gc)
    assert gc.cmd({"cmd": "inject_input", "kind": "key", "key": key}).get("ok"), f"{gc.name} key {key}"
    _ok, secs, _ = poll(lambda: view_level(gc) == want if want is not None else view_level(gc) != v0, LEVEL_S)
    return v0, view_level(gc), secs


def box_texts(gc):
    return [w.get("text") for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]


def ctrl_f(gc, timeout):
    """Ctrl+F on gc; polls up to `timeout` for an InfoboxState on top. Returns {box, s, texts, top, closed}: a box is
    closed by dismiss_popup and gc's BattlescapeState waited back on top (bounded)."""
    chord(gc, KEY_F, "ctrl")
    ok, secs, _ = poll(lambda: G3F.top(gc) == "InfoboxState", timeout)
    r = {"box": ok, "s": secs, "top": G3F.top(gc)}
    if ok:
        r["texts"] = box_texts(gc)
        r["closed"] = gc.cmd({"cmd": "dismiss_popup"}).get("handled")
        r["back"] = poll(lambda: G3F.top(gc) == "BattlescapeState", BOX_S)[:2]
    return r


def first_line(texts):
    return (texts[0].split("\n")[0] if texts else None)


def alt_c(gc, tile):
    """HC.stage_camera on tile, map_tile_click_pos verified on it (the selector left there), Alt+C, then n frames."""
    cam = HC.stage_camera(gc, tile)
    pr = gc.cmd({"cmd": "map_tile_click_pos", "x": tile[0], "y": tile[1], "z": tile[2]})
    assert pr.get("verified"), f"map_tile_click_pos {tile} on {gc.name} not verified: {pr}"
    chord(gc, KEY_C, "alt")
    return {"offset": HC.cam_offset(cam), "settle": frames_after(gc)}


# ===================== rows (the alien seat `me` on its own side; `other` the X-COM machine) =====================


def row_own_arrow(me, other, host, client, crash0, sfx, mine=A_ID):
    ev = {"me": bsv(me), "other": bsv(other)}
    m = ev["me"]
    cells = {f"own_arrow{sfx}-pre": (m["selectedId"] == mine and m["cursorType"] not in (None, 0),
                                     f"{me.name} selectedId {m['selectedId']} (want {mine}), "
                                     f"cursorType {m['cursorType']} (want != 0)")}
    ok, secs, rec = arrow_now(me, mine)
    ev["dp"], ev["dpOther"] = rec, dp(other)
    cells[f"own_arrow{sfx}-draw"] = (ok, f"DP({me.name}) arrowUnit {rec.get('arrowUnit')} "
                                         f"arrowFrame {rec.get('arrowFrame')} "
                                         f"frame {rec.get('frame')} after {secs} s (want arrowUnit {mine} drawn now)")
    cells[f"own_arrow{sfx}-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_own_levels(me, other, host, client, crash0, sfx):
    ev = {"v0": view_level(me)}
    up = level_key(me, KEY_LEVEL_UP, 1)
    down = level_key(me, KEY_LEVEL_DOWN, 0)
    ev.update(up=up, down=down, otherLevel=view_level(other))
    return {f"own_levels{sfx}-up": (up[0] == 0 and up[1] == 1,
                                    f"{me.name} viewLevel {up[0]} -> {up[1]} after the level-up key "
                                    f"{KEY_LEVEL_UP} ({up[2]} s; want 0 -> 1)"),
            f"own_levels{sfx}-down": (down[1] == 0,
                                      f"{me.name} viewLevel {down[0]} -> {down[1]} after the level-down key "
                                      f"{KEY_LEVEL_DOWN} ({down[2]} s; want 0)"),
            f"own_levels{sfx}-common": G3F.common(host, client, crash0)}, ev


def row_fatal_box(me, other, host, client, crash0, sfx):
    r = ctrl_f(me, BOX_S)
    ev = {"ctrlF": r, "me": bsv(me)}
    fl = first_line(r.get("texts"))
    return {f"fatal_box{sfx}-box": (r["box"] and fl == TEXT_FATAL and (r.get("back") or [False])[0],
                                    f"{me.name} top {'InfoboxState' if r['box'] else r['top']} within {r['s']} s "
                                    f"(want InfoboxState in {BOX_S} s), first line {fl!r} (want {TEXT_FATAL!r}), "
                                    f"closed {r.get('closed')}, map back {r.get('back')}"),
            f"fatal_box{sfx}-common": G3F.common(host, client, crash0)}, ev


def row_own_marker(me, other, host, client, crash0, sfx, mine=A_ID, opp=S9_ID, tiles=(A_TILE, S9_TILE)):
    ev = {"before": {me.name: [marker(me, mine), marker(me, opp)], other.name: [marker(other, mine), marker(other, opp)]}}
    ev["onMine"] = alt_c(me, tiles[0])
    ev["onOpp"] = alt_c(me, tiles[1])
    got = [marker(me, mine), marker(me, opp)]
    ev["after"] = {me.name: got, other.name: [marker(other, mine), marker(other, opp)]}
    return {f"own_marker{sfx}-own": (got[0] == 1, f"{me.name} units[{mine}].customMarker {got[0]} (want 1)"),
            f"own_marker{sfx}-opp": (got[1] == 0,
                                     f"{me.name} units[{opp}].customMarker {got[1]} (want 0); {other.name} "
                                     f"{ev['after'][other.name]} (EVIDENCE, machine-local)"),
            f"own_marker{sfx}-common": G3F.common(host, client, crash0)}, ev


def row_marker_overlay(me, other, host, client, crash0, sfx, mine=A_ID):
    ev = {"altOn": me.cmd({"cmd": "set_touch_modifiers", "alt": True}).get("alt")}
    try:
        ok, secs, rec = mark_now(me, mine, "custom")
    finally:
        ev["altOff"] = me.cmd({"cmd": "set_touch_modifiers", "alt": False}).get("alt")
    ev["dp"] = rec
    return {f"marker_overlay{sfx}-mark": (ok and ev["altOn"] is True,
                                          f"DP({me.name}) latest frame {rec.get('frame')} marks "
                                          f"{rec.get('latestMarks')} after {secs} s (want {{unit {mine}, "
                                          f"kind custom}} drawn now; alt on {ev['altOn']})"),
            f"marker_overlay{sfx}-common": G3F.common(host, client, crash0)}, ev


def row_xcom_turn_inert(me, other, host, client, crash0, sfx, ev, guard=""):
    """The alien seat during X-COM's turn (`ev` holds the side change): the level-up key must not move its view
    (restored by level-down if it did); Ctrl+F must open no box (closed if one opens). `guard` names a guard cell."""
    ev["me"], ev["other"] = bsv(me), bsv(other)
    lv = level_key(me, KEY_LEVEL_UP, None)
    ev["levelUp"] = lv
    if lv[1] != lv[0]:
        ev["restore"] = level_key(me, KEY_LEVEL_DOWN, lv[0])
    cf = ctrl_f(me, NOBOX_S)
    ev["ctrlF"] = cf
    return {f"xcom_turn_inert{sfx}-level": (lv[1] == lv[0],
                                            f"{me.name} viewLevel {lv[0]} -> {lv[1]} after the level-up key on "
                                            f"X-COM's turn ({lv[2]} s; want unchanged)"),
            f"xcom_turn_inert{sfx}-ctrlf": (not cf["box"],
                                            f"{me.name} Ctrl+F: InfoboxState {cf['box']} in {cf['s']} s (want none in "
                                            f"{NOBOX_S} s), texts {cf.get('texts')}, closed {cf.get('closed')}{guard}"),
            f"xcom_turn_inert{sfx}-common": G3F.common(host, client, crash0)}, ev


def xcom_ctl(gc, uid=None):
    """The X-COM machine on its own turn: (with `uid`) its selectedId uid and its arrow over uid drawn now; level up ->
    +1 and back; Ctrl+F -> the box (closed). Returns (bad list, evidence)."""
    bad, ev = [], {"me": bsv(gc)}
    if uid is not None:
        if ev["me"]["selectedId"] != uid:
            bad.append(f"{gc.name} selectedId {ev['me']['selectedId']} (want {uid})")
        ok, secs, rec = arrow_now(gc, uid)
        ev["arrow"] = rec
        if not ok:
            bad.append(f"DP({gc.name}) arrowUnit {rec.get('arrowUnit')} not drawn now in {secs} s (want {uid})")
    v0 = view_level(gc)
    up = level_key(gc, KEY_LEVEL_UP, (v0 or 0) + 1)
    down = level_key(gc, KEY_LEVEL_DOWN, v0)
    ev.update(up=up, down=down)
    if up[1] != (v0 or 0) + 1 or down[1] != v0:
        bad.append(f"{gc.name} level up {up[0]} -> {up[1]}, down -> {down[1]} (want +1 and back)")
    cf = ctrl_f(gc, BOX_S)
    ev["ctrlF"] = cf
    if not cf["box"] or first_line(cf.get("texts")) != TEXT_FATAL or not (cf.get("back") or [False])[0]:
        bad.append(f"{gc.name} Ctrl+F box {cf['box']} texts {cf.get('texts')} back {cf.get('back')} (want "
                   f"{TEXT_FATAL!r}, closed)")
    return bad, ev


def row_xcom_controls(host, client, crash0, side_ok):
    if not side_ok:
        return {"xcom_controls-ctl": (False,
                                      "staging (the client's END TURN -> side 0 turn 2 failed in xcom_turn_inert)"),
                "xcom_controls-common": G3F.common(host, client, crash0)}, {}
    bad, ev = xcom_ctl(host, HOST_SELECTED_ID)
    ev["altc"] = alt_c(host, G3F.pos(host, HOST_SELECTED_ID))
    mk = [marker(host, HOST_SELECTED_ID), marker(client, HOST_SELECTED_ID)]
    ev["marker"] = mk
    if mk[0] != 1:
        bad.append(f"host units[{HOST_SELECTED_ID}].customMarker {mk[0]} after Alt+C (want 1)")
    return {"xcom_controls-ctl": (not bad, "; ".join(bad) or f"arrow over {HOST_SELECTED_ID}, level +1 and back, "
                                                              f"the box closed, marker 1"),
            "xcom_controls-common": G3F.common(host, client, crash0)}, ev


# ===================== the boot =====================


def stage(host, client, presser):
    """RM.TILES on both (open ground checked), then presser's END TURN -> side 1 turn 1 (the alien seat's own turn)."""
    ev = {"placed": RM.stage_tiles(host, client, RM.TILES, ())}
    side = {}
    G3F.guarded("staging", lambda: RM.side_change(host, client, presser, FACTION_HOSTILE, 1, side), (host, client))
    ev.update(side=side, hash=G3F.hash_now(host, client))
    return ev


def side2(host, client, presser, ev):
    """presser's END TURN -> side 0 turn 2; returns True when both machines got there (else the error in ev)."""
    try:
        RM.side_change(host, client, presser, FACTION_PLAYER, 2, ev)
        return True
    except Exception as e:
        ev["sideError"] = f"{type(e).__name__}: {str(e)[:300]}"
        return False


def run_boot():
    host = GameClient("host", None, make_user_dir("pvp_controls_host"))
    client = GameClient("client", None, make_user_dir("pvp_controls_client"))
    m = (host, client)
    try:
        try:
            G3F.guarded("boot", lambda: BER.boot_pvp(host, client, KEY), m)
            G3F.guarded("boot", lambda: G3F.reactions_zero(host, client), m)
            crash0 = session._crash_log_snapshot()
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        try:
            st = stage(host, client, host)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        print(f"EVIDENCE staging: {st}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("own_arrow", rows["own_arrow"],
                            lambda: row_own_arrow(client, host, host, client, crash0, ""))
        fails += G3F.run_row("own_levels", rows["own_levels"],
                             lambda: row_own_levels(client, host, host, client, crash0, ""))
        fails += G3F.run_row("fatal_box", rows["fatal_box"],
                             lambda: row_fatal_box(client, host, host, client, crash0, ""))
        fails += G3F.run_row("own_marker", rows["own_marker"],
                             lambda: row_own_marker(client, host, host, client, crash0, ""))
        fails += G3F.run_row("marker_overlay", rows["marker_overlay"],
                             lambda: row_marker_overlay(client, host, host, client, crash0, ""))
        inert_ev = {}
        side_ok = side2(host, client, client, inert_ev)
        if side_ok:
            fails += G3F.run_row("xcom_turn_inert", rows["xcom_turn_inert"],
                                 lambda: row_xcom_turn_inert(client, host, host, client, crash0, "", inert_ev))
        else:
            fails += G3F.verdict("xcom_turn_inert", rows["xcom_turn_inert"],
                                 {n: (False, f"staging (side change: {inert_ev.get('sideError')})")
                                  for n in rows["xcom_turn_inert"]}, inert_ev)
        fails += G3F.run_row("xcom_controls", rows["xcom_controls"],
                             lambda: row_xcom_controls(host, client, crash0, side_ok))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_controls: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
