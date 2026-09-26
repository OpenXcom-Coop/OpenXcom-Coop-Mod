"""W2-P4 S-B - test_w2_client_grenade.py: the second player primes, unprimes and
throws its own grenades and fires its own blaster launcher; the host checks and
runs every one of them (spec rewrite/prompts/w2p4_client_combat_intents.md
section (f) "test_w2_client_grenade.py (S-B)", sections (b)1-6, as amended by
AMENDMENT C1 (PR-Q2: K1 keeps refusing throw and launch until S-B; PR-Q3: the
K8 action-menu refusal narrows for prime/unprime in S-B), AMENDMENT C2 (PR-Q16:
C20 is vanilla's dive and its explosion is asserted; PR-Q17: the test mod gives
the stock grenade an UNPRIME row) and AMENDMENT C4 (PR-Q19: the Coop_Spray_Test
mod lands with this file and is loaded on BOTH machines).

Before S-B the second player cannot do any of this. PRIME and UNPRIME are
refused in the action menu (K8, ActionMenuState::handleAction) with "Only the
host can use this item" and coopLocalExecBlocked +0 (F1171). The throw click and
the first launcher waypoint click are refused at K1 (BattlescapeGame::
primaryAction's targeting arm; client coopLocalExecBlocked +1, nothing sent).
After S-B each press becomes an intent (wire kinds of spec (b)1: `prime` for
BA_PRIME and BA_UNPRIME, `throw`, and `shoot` with action `launch`). The host
admits it with vanilla's own checks and runs vanilla's own code under an
`intent` action context (context kinds of spec (b)3: `prime`, `unprime`,
`throw`, `launch`) that ends in one bt_action_end; the ordering client runs
vanilla's aftermath for its own action.
Three scenarios, ONE boot (the Coop_Spray_Test mod on both machines), in this
order:

  C23a   prime, then unprime. Leg P: a grenade on C (lever, both, clear hands),
         C -> C23A_C_TILE facing C23A_C_DIR, C TU max (both). Client: TAB-select
         C, the right-hand box, key 49 (PRIME), fuse key 48 on
         PrimeGrenadeState (fuse 0). Leg U: a PRIMED grenade on C (lever fuse 0,
         both, clear hands: the same state vanilla's prime leaves, T0b), C TU
         max (both). Client: TAB, the right-hand box, key 50 (UNPRIME, the
         mod's row). RED: both presses refused at K8 with "Only the host can
         use this item", coopLocalExecBlocked +0, nothing sent. GREEN: leg P =
         {origin intent, kind prime, actorId C} whose evs are exactly prime ->
         bt_action_end, the `prime` cue {item, fuse 0, unprime false}; the
         grenade fuse 0 / fuseEnabled true on both; C TU C_TU_FULL - PRIME_TU on
         both; the client shows vanilla's "Grenade is Activated!" at its own
         end (warningText; lastAftermath.actionId = the order's). Leg U =
         {origin intent, kind unprime, actorId C}, evs prime -> bt_action_end,
         the `prime` cue {item, fuse -1, unprime true}; fuse -1 / fuseEnabled
         false on both; C TU C_TU_FULL - UNPRIME_TU on both; the client shows
         "Grenade De-activated!" at its own end. Both legs are sent as the wire
         kind `prime` (coopIntentsSent.prime +1 each).
  C19    throw a primed grenade, then END TURN. A primed grenade on C (lever
         fuse 0, both), C -> C19_C_TILE facing east (dir 2), TU max. The throw
         tile C19_TILE is due north: C does not face it (F490), and no unit
         stands within 5 tiles (the grenade's blast radius). Client: TAB, the
         right-hand box, key 53 (THROW), HOME, host set_seed SEED_C19, one left
         click on C19_TILE. Then both machines press END TURN (client first)
         and the full side cycle runs. RED: the click refused at K1 (+1),
         nothing sent. GREEN: {origin intent, kind throw, actorId C} whose evs
         are exactly shot -> bt_action_end; the `shot` cue has action throw
         with an `arc`; the grenade on C19_TILE (owner -1, fuse 0) on both; C
         TU C19_TU_AFTER on both. At END TURN the first ev of the cycle is the
         grenade's explosion centred on C19_TILE, carrying an `endturn`
         context's id (W2-P3), its one bt_action_end before the cycle's
         side_transition; the grenade gone on both; no unit's health, stun or
         status changed on either machine; the tile equal on both; turn + 1
         on both.
  C20    the blaster launcher, vanilla's dive (PR-Q16). A launcher + bomb on C
         (lever, both), C -> C20_C_TILE facing west (dir 6, away from the
         waypoints: F1125), TU max. Client: TAB, the right-hand box, key 49
         (LAUNCH), the client camera on C20_CAMERA, one left click on C20_W
         (waypoint 1, local display: the launch button appears), a second left
         click on C20_W (waypoint 2), host set_seed SEED_C20, then the launch
         button found by its rect (F1127: its click nth shifts). RED: the first
         waypoint click refused at K1 (+1): no waypoint, the launch button
         stays hidden, nothing sent. GREEN: {origin intent, kind launch,
         actorId C} whose evs are exactly shot -> shot -> explosion ->
         bt_action_end (both legs, the explosion and the end on one actionId);
         leg 1 {action launch, shotIndex 1, waypointsLeft 2} ends on C20_W,
         leg 2 {shotIndex 2, waypointsLeft 1} starts on leg 1's impact tile and
         ends on C20_W; the explosion {power 200, radius 10} is centred on
         C20_W; the census box changes C20_TILES_CHANGED tiles on the host and
         is identical on both; the terrain bucket changes and is equal on both;
         the bomb is gone and no item is added on both; no unit's health, stun
         or status changed; C TU C20_TU_AFTER on both.

The order is TASK 0 T0-6's file order (T0b: C23a, C19 + END TURN, C20). C20
runs last: its blast leaves smoke and fire, and no END TURN follows it. C20's
constants (T0c) were measured on the untouched map, so this file asserts the
tile census and terrain equality on both, not T0c's terrain hash values (C19's
END TURN detonation changes the terrain first); the census box (T0c's x/y box,
z 0-1: all 285 changed tiles lay at z 0-1) lies outside C19's blast.
place() teleports only a unit that is not already on the tile (CLAUDE.local.md
S2). A hand click while the client targets only cancels the targeting (F503).

Common asserts (spec (f), after wait_host_idle): hash_now {full:true} - every
bucket EQUAL; desyncSeen false on both; client coopClientBStatePushes unchanged
and host 0; the W2-P2 delta must-be-0 counters on both; every lever item
created on both machines with equal ids (both()). For an admitted order: host
closedContexts gains exactly one {origin intent, kind K, actorId C}; every host
ev of that actionId is in the client's log with the same seq, kind and
actionId; exactly one bt_action_end; client coopIntentsSent[wire kind] +1;
client inFlight null at the end; client intentTimeouts unchanged (no
STR_COOP_ACTION_TIMEOUT).

Probes: all exist before this file (S-A.1 added coopIntentsSent,
intentsReceived, lastActionHalt, lastAftermath). The cue payloads are read from
the HOST's own openxcom.log `[coop-cue]` lines.

FIXTURE (TASK 0 T0-6 = T0b, the C20 redo and the mod = T0c; the roster-pinned
terror boot of test_w2_host_combat.py): set_seed SEED_ROSTER on the HOST right
before its open_new_battle, mission STR_TERROR_MISSION, set_seed SEED_MAP right
before newbattle_ok, seat_count 2, MAP_FP asserted on both, the seated unit ids
asserted (SEATED), pin_ai_neutral, the mod active on both (F1164). Every lever
pair goes to the CLIENT first (F607). Item ids are read at run time from the
lever replies (F1107), never baked. The seeds were found with the HOST stand-in
(battle_fire for C): S-B's executor build proves them again (N18 = F1085).

RED-THEN-GREEN (spec (d) row S-B). Commit S-B.1 (this file and the mod) is run
ONCE and every scenario must FAIL with its RED evidence. Commit S-B.2 is run
ONCE and every scenario must PASS. Each scenario prints ONE "EVIDENCE <id>:"
line with both machines' fields BEFORE its green conditions are checked;
main() runs every scenario even after an earlier one failed and prints
"PASS <id>" / "FAIL <id>: <message>". Every wait is bounded; a wait that times
out is recorded in the EVIDENCE line and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all three scenarios pass, 2
otherwise (a bring-up failure is also 2). WV-D95: run in the foreground to
completion.

Run:  python tools/coop_test/test_w2_client_grenade.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_rw_turn_baton import RHAND_NTH, click_nth
from test_rw_seat_pacing import tab_select, SDLK_HOME
from test_w2_delta_core import diff_buckets, short, both, end_turn_cycle
from test_w2_delta_items import items_by_id, tile_of
from test_w2_host_combat import bring_up_lobby_roster_pinned, evs_since, ev_tuples
from test_w2_ai_origins import host_payloads, voxel_tile
from test_w2_client_shoot import (top, snap, ubrief, press, menu_rows, count_of, mine, place, set_tu_both,
                                  await_press, collect, ctx_view, chain_of, forwarded_fails, tu_fails,
                                  common_fails, finish, press_view, ui_view, shot_payloads, RHAND_CENTRE, TU_MAX,
                                  C_TU_FULL)

# ----- bring-up (TASK 0: the roster-pinned terror boot, the mod on both) -----
MISSION = "STR_TERROR_MISSION"
SEED_MAP = 1
MAP_FP = -3.451266327757785e+18   # host battle_state.mapFingerprint on SEED_MAP 1, unmodded and modded (F1164)
SEATED = [8, 9]                   # the client's seated units: C and C2
C_ID = 8
H_ID = 10                         # first host-seat soldier
A_ID, A2_ID = 1000000, 1000001    # Sectoid Soldiers
PORT = "48712"
COOP_SEAT_0 = 0
FACTION_PLAYER = 0
MOD_NAME = "Coop_Spray_Test"
MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", MOD_NAME)
MOD_ACTIVE_LINE = "- Coop_Spray_Test v1.0"
GRENADE = "STR_GRENADE"

# ----- C23a (T0-6 = T0b, T0-10 = T0c: F1123, F1166) -----
C23A_C_TILE, C23A_C_DIR = (12, 26, 0), 2
PRIME_TU = 32                     # 50 % of C's max TU 64 (costPrime; measured 29 on H with TU 58)
UNPRIME_TU = 16                   # 25 % of 64, rounded down (measured 14 on H with TU 58)
C23A_ROWS = 2                     # unprimed: THROW + PRIME; primed with the mod: THROW + UNPRIME
TEXT_PRIMED = "Grenade is Activated!"        # xcom1 STR_GRENADE_IS_ACTIVATED (en-US)
TEXT_UNPRIMED = "Grenade De-activated!"      # xcom1 STR_GRENADE_IS_DEACTIVATED (en-US)
TEXT_ITEM_ACTION = "Only the host can use this item"   # STR_COOP_ITEM_ACTION_HOST_ONLY (the RED text)

# ----- C19 (T0-6 = T0b: F1124) -----
C19_C_TILE, C19_C_DIR = (12, 27, 0), 2       # faces east; the throw tile is due north (F490)
C19_TILE = (12, 20, 0)            # open road, 7 tiles north
C19_ROWS = 2                      # primed with the mod: THROW + UNPRIME
SEED_C19 = 2                      # seed 1 landed on (11,21,0)
BLAST_BOX_C19 = 5                 # the grenade's blast radius (tiles): no unit may stand this close
C19_TU_AFTER = 46                 # 64 - 16 throw - 2 (two octants of pre-throw turn)
C19_CHAIN = ["turn", "shot", "bt_action_end"]   # W2-P5 S-T (D151, E3): the pre-throw turn

# ----- C20 (T0c, the C20 redo: F1169) -----
C20_C_TILE, C20_C_DIR = (28, 25, 0), 6       # faces west, away from the waypoints (F1125)
C20_W = (46, 25, 0)               # both waypoints (vanilla's dive, PR-Q16)
C20_CAMERA = (41, 24, 0)          # client camera before the waypoint clicks
SEED_C20 = 1
C20_TU_AFTER = 18                 # 64 - 42 launch - 4 (four octants of pre-launch turn)
C20_CHAIN = ["turn", "shot", "shot", "explosion", "bt_action_end"]   # W2-P5 S-T (D151, E3): the pre-launch turn
C20_POWER, C20_RADIUS = 200, 10
C20_BOX = (range(34, 50), range(13, 38), range(0, 2))   # T0c's census box (x, y), z 0-1
C20_TILES_CHANGED = 285
LAUNCH_RECT = (288, 0, 32, 24)    # the launch button (F1127)
LAUNCH_CENTRE = (LAUNCH_RECT[0] + LAUNCH_RECT[2] // 2, LAUNCH_RECT[1] + LAUNCH_RECT[3] // 2)

# ----- UI -----
KEY_ITEM1, KEY_ITEM2, KEY_ITEM5 = 49, 50, 53  # keyBattleActionItem1/2/5
KEY_PRIME, KEY_LAUNCH, KEY_UNPRIME, KEY_THROW = KEY_ITEM1, KEY_ITEM1, KEY_ITEM2, KEY_ITEM5
KEY_FUSE_0 = 48                   # PrimeGrenadeState button 0 (SDLK_0)
CURSOR_TARGETING = (2, 3, 4, 5)   # CT_AIM, CT_PSI, CT_WAYPOINT, CT_THROW (Map.h)
CURSOR_WAYPOINT, CURSOR_THROW = 4, 5
BANNER_CLEAR_S = 12               # the refusal banner's Terminal dwell is 6 s (CoopBattleUi.h)
PARTS = ("floor", "westwall", "northwall", "object")


# ===================== small probes =====================


def mod_log(gc):
    """This machine's openxcom.log: the active-mods lines naming the test mod,
    and every line reporting an invalid mod."""
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError as e:
        return {"error": short(e)}
    return {"active": [ln.split("\t")[-1] for ln in lines if MOD_NAME in ln and "- " in ln and "Invalid" not in ln],
            "invalid": [ln.split("\t")[-1] for ln in lines if "Invalid" in ln and "mod" in ln]}


def hurt_map(gc):
    return {u["id"]: (u.get("health"), u.get("stun"), u.get("status")) for u in battle_state(gc)["units"]}


def hurt_delta(m0, m1):
    return {u: (m0.get(u), m1.get(u)) for u in set(m0) | set(m1) if m0.get(u) != m1.get(u)}


def terrain(gc):
    r = gc.cmd({"cmd": "hash_now", "full": True})
    return (r.get("h") or {}).get("terrain") if r.get("ok") else None


def tile(gc, t):
    r = gc.cmd({"cmd": "tile_info", "x": t[0], "y": t[1], "z": t[2]})
    if not r.get("ok"):
        return None
    return {"parts": {p: (r["parts"][p]["mapDataSetID"], r["parts"][p]["mapDataID"]) for p in PARTS},
            "fire": r.get("fire"), "smoke": r.get("smoke"), "unit": r.get("unit")}


def census(gc, box):
    """{tile: (4 parts, fire, smoke)} over `box` (ONE tile_census reply, F1362:
    tile_info's census fields for every tile, z-, y-, x-major, null = no tile)."""
    r = gc.ok({"cmd": "tile_census", "x0": box[0][0], "x1": box[0][-1], "y0": box[1][0], "y1": box[1][-1],
               "z0": box[2][0], "z1": box[2][-1]})
    rows = iter(r["tiles"])
    out = {}
    for z in box[2]:
        for y in box[1]:
            for x in box[0]:
                t = next(rows)
                out[(x, y, z)] = ((tuple((t["parts"][p]["mapDataSetID"], t["parts"][p]["mapDataID"]) for p in PARTS),
                                   t.get("fire"), t.get("smoke")) if t else None)
    return out


def item_view(it):
    return {k: (it or {}).get(k) for k in ("type", "owner", "slot", "fuse", "fuseEnabled", "onTile", "tx", "ty",
                                           "tz")} if it else None


def launch_button_nth(gc):
    """The launch button's click nth: its index among the top state's VISIBLE
    interactive surfaces (click_widget's order), found by its rect (F1127).
    None while it is hidden."""
    vis = [w for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", []) if w.get("visible") and w.get("interactive")]
    for n, w in enumerate(vis):
        if (w.get("x"), w.get("y"), w.get("w"), w.get("h")) == LAUNCH_RECT:
            return n
    return None


def near_units(gc, t, r):
    """Live units within `r` tiles of `t` (Chebyshev, one level up or down)."""
    return [u["id"] for u in battle_state(gc)["units"] if not u.get("isOut") and u.get("x") is not None
            and max(abs(u["x"] - t[0]), abs(u["y"] - t[1])) <= r and abs(u["z"] - t[2]) <= 1]


def cue_of(pl, seq):
    return (pl.get(seq) or {}).get("payload") or {}


# ===================== staging (client first, F607) =====================


def give_grenade(host, client, primed):
    req = {"cmd": "battle_give", "unit": C_ID, "item": GRENADE, "clear_hands": True}
    if primed:
        req["fuse"] = 0
    return both(host, client, req, ("weaponId", "ammoId"))["weaponId"]


def give_launcher(host, client):
    g = both(host, client, {"cmd": "battle_give", "unit": C_ID, "item": "STR_BLASTER_LAUNCHER",
                            "ammo": "STR_BLASTER_BOMB", "clear_hands": True}, ("weaponId", "ammoId"))
    return g["weaponId"], g["ammoId"]


def cancel_client_targeting(client):
    """F503: while the client targets, a hand click only cancels the targeting.
    One such click when an earlier scenario left the client targeting. Returns
    [cursor before(, after)]."""
    c0 = battle_state(client).get("cursorType")
    if c0 not in CURSOR_TARGETING:
        return [c0]
    click_nth(client, RHAND_NTH)
    return [c0, battle_state(client).get("cursorType")]


def wait_banner_not(client, text, notes):
    try:
        client.wait_for(f"client banner not {text!r}", lambda: battle_state(client).get("coopWaitText") != text or None,
                        timeout=BANNER_CLEAR_S, interval=0.2)
    except Exception as e:
        notes.append(f"banner still {text!r}: {short(e)}")


# ===================== the client's real-UI presses =====================


def open_hand_menu(client, ev):
    """TAB-select C, cancel a leftover targeting, the right-hand box: the action
    menu opens. Fills `ev`."""
    ev["tab"] = tab_select(client, C_ID)
    assert ev["tab"], f"TAB never selected C on the client (selectedId {battle_state(client).get('selectedId')})"
    ev["targetingCancel"] = cancel_client_targeting(client)
    r = click_nth(client, RHAND_NTH)
    assert (r.get("baseX"), r.get("baseY")) == RHAND_CENTRE, f"right-hand click landed off the box: {r}"
    client.wait_for("client ActionMenuState on top", lambda: top(client) == "ActionMenuState" or None, timeout=5)
    ev["rows"] = menu_rows(client)


def menu_order(client, ev, key, fuse_key=None):
    """The action-menu press: the row's key; for a prime, the fuse key on the
    fuse screen when it opens (vanilla: PrimeGrenadeState over the menu).
    Fills `ev`."""
    open_hand_menu(client, ev)
    press(client, key)
    client.wait_for("client left the action menu", lambda: top(client) != "ActionMenuState" or None, timeout=5)
    ev["topAfterKey"] = top(client)
    if fuse_key is not None:
        assert ev["topAfterKey"] == "PrimeGrenadeState", (
            f"no fuse screen after key {key} on the client (top {ev['topAfterKey']})")
        press(client, fuse_key)
        client.wait_for("client left the fuse screen", lambda: top(client) == "BattlescapeState" or None,
                        timeout=5)
        ev["topAfterFuse"] = top(client)


def target_order(client, ev, key, want_cursor, tile_, before_click=None):
    """The targeted press: the row's key (targeting starts), HOME, one
    self-verified left click on `tile_`. `before_click` runs right before the
    click (the host's set_seed). Fills `ev`."""
    open_hand_menu(client, ev)
    press(client, key)
    client.wait_for("client BattlescapeState on top after the row key",
                    lambda: top(client) == "BattlescapeState" or None, timeout=5)
    ev["cursorAfterKey"] = battle_state(client).get("cursorType")
    assert ev["cursorAfterKey"] == want_cursor, (
        f"row key {key} did not start targeting on the client (cursorType {ev['cursorAfterKey']}, want {want_cursor})")
    press(client, SDLK_HOME)
    time.sleep(0.15)
    pr = client.cmd({"cmd": "map_tile_click_pos", "x": tile_[0], "y": tile_[1], "z": tile_[2]})
    ev["clickPos"] = {k: pr.get(k) for k in ("verified", "winX", "winY", "centered")}
    assert pr.get("verified"), f"precondition: map_tile_click_pos did not verify {tile_} on the client: {pr}"
    if before_click:
        before_click()
    client.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
    ev["clickAt"] = time.time()


def launch_order(client, ev, before_launch=None):
    """The launcher press: key 49 (waypoint targeting), the client camera on
    C20_CAMERA, two self-verified left clicks on C20_W (vanilla shows the
    launch button after the first waypoint), `before_launch` (the host's
    set_seed), then the launch button by its rect. Fills `ev`."""
    open_hand_menu(client, ev)
    press(client, KEY_LAUNCH)
    client.wait_for("client BattlescapeState on top after the row key",
                    lambda: top(client) == "BattlescapeState" or None, timeout=5)
    ev["cursorAfterKey"] = battle_state(client).get("cursorType")
    assert ev["cursorAfterKey"] == CURSOR_WAYPOINT, (
        f"key {KEY_LAUNCH} did not start waypoint targeting on the client (cursorType {ev['cursorAfterKey']}, want "
        f"{CURSOR_WAYPOINT})")
    cam = client.cmd({"cmd": "battle_camera_center", "x": C20_CAMERA[0], "y": C20_CAMERA[1], "z": C20_CAMERA[2]})
    ev["camera"] = cam.get("ok")
    time.sleep(0.4)
    ev["buttonBefore"] = launch_button_nth(client)
    for n in (1, 2):
        pr = client.cmd({"cmd": "map_tile_click_pos", "x": C20_W[0], "y": C20_W[1], "z": C20_W[2]})
        ev[f"clickPos{n}"] = {k: pr.get(k) for k in ("verified", "winX", "winY", "centered")}
        assert pr.get("verified"), f"precondition: map_tile_click_pos did not verify {C20_W} on the client: {pr}"
        client.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
        ev[f"click{n}At"] = time.time()
        if n == 1:
            try:
                client.wait_for("the launch button shown after the first waypoint",
                                lambda: launch_button_nth(client) is not None or None, timeout=2.0, interval=0.1)
            except Exception:
                raise AssertionError("the launch button never appeared after the first waypoint click (no waypoint "
                                     f"placed; cursorType {battle_state(client).get('cursorType')})")
        time.sleep(0.3)
    nth = launch_button_nth(client)
    ev["buttonNth"] = nth
    assert nth is not None, "the launch button is hidden after the second waypoint click"
    if before_launch:
        before_launch()
    r = click_nth(client, nth)
    ev["launchClick"] = (r.get("baseX"), r.get("baseY"))
    assert ev["launchClick"] == LAUNCH_CENTRE, f"the launch click landed off the button {LAUNCH_RECT}: {r}"
    ev["launchAt"] = time.time()


def settle(host, client, notes):
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")


# ===================== checks =====================


def admitted_fails(before, rec, ctx_kind, wire_kind, actor):
    """Spec (f) common asserts for an ADMITTED order. The context is keyed by
    the spec (b)3 context kind, coopIntentsSent by the spec (b)1 wire kind.
    Returns (fails, ctx)."""
    fails = []
    new = ctx_view(before, rec)
    hits = mine(new, "intent", ctx_kind, actor)
    ctx = hits[0] if len(hits) == 1 else None
    if len(hits) != 1:
        fails.append(f"host closedContexts gained {len(hits)} {{origin intent, kind {ctx_kind}, actorId {actor}}} "
                     f"(want exactly 1; new contexts={new})")
    if ctx:
        aid = ctx.get("actionId")
        chain = chain_of(rec, aid)
        cmap = {e["seq"]: e for e in rec["cev"]}
        bad = [(e["seq"], e["kind"], cmap.get(e["seq"])) for e in chain
               if not cmap.get(e["seq"]) or cmap[e["seq"]]["kind"] != e["kind"] or cmap[e["seq"]]["actionId"] != aid]
        if bad:
            fails.append(f"client event_log does not hold the host's evs of actionId {aid}: "
                         f"(seq, host kind, client entry)={bad}")
        ends = [e["seq"] for e in chain if e["kind"] == "bt_action_end"]
        if len(ends) != 1:
            fails.append(f"host bt_action_end evs of actionId {aid}: {ends} (want exactly 1)")
    d = count_of(rec["client"]["coopIntentsSent"], wire_kind) - count_of(before["client"]["coopIntentsSent"],
                                                                         wire_kind)
    if d != 1:
        fails.append(f"client coopIntentsSent.{wire_kind} +{d} (want +1; before={before['client']['coopIntentsSent']} "
                     f"after={rec['client']['coopIntentsSent']})")
    if rec["client"]["inFlight"] is not None:
        fails.append(f"client inFlight at the end {rec['client']['inFlight']} (want null)")
    if rec["client"]["intentTimeouts"] != before["client"]["intentTimeouts"]:
        fails.append(f"client intentTimeouts {before['client']['intentTimeouts']}->{rec['client']['intentTimeouts']} "
                     f"(want unchanged: no STR_COOP_ACTION_TIMEOUT)")
    return fails, ctx


def fuse_fails(rec, iid, fuse, enabled, what):
    ih, ic = rec["ih"].get(iid) or {}, rec["ic"].get(iid) or {}
    got = ((ih.get("fuse"), ih.get("fuseEnabled")), (ic.get("fuse"), ic.get("fuseEnabled")))
    if got != ((fuse, enabled), (fuse, enabled)):
        return [f"{what} {iid} (fuse, fuseEnabled) host={got[0]} client={got[1]} (want ({fuse}, {enabled}) on both)"]
    return []


def aftermath_fails(rec, aid, text, what):
    fails = []
    if rec["clientUi"]["warning"] != text:
        fails.append(f"{what}: client warningText {rec['clientUi']['warning']!r} (want vanilla's {text!r})")
    la = rec["client"]["lastAftermath"] or {}
    if aid is None or la.get("actionId") != aid:
        fails.append(f"{what}: client lastAftermath={rec['client']['lastAftermath']} (want actionId {aid}: the "
                     f"message is shown at the order's own end)")
    return fails


def prime_leg_fails(host, before, rec, ev, ctx_kind, gid, fuse, unprime, what):
    """One C23a leg: the context, its evs, the `prime` cue payload."""
    fails = []
    if ev.get("rows") != C23A_ROWS:
        fails.append(f"{what}: precondition: client menu rows {ev.get('rows')} (want {C23A_ROWS})")
    fails += forwarded_fails(before, rec)
    f, cx = admitted_fails(before, rec, ctx_kind, "prime", C_ID)
    fails += [f"{what}: {m}" for m in f]
    aid = cx.get("actionId") if cx else None
    chain = chain_of(rec, aid)
    kinds = [e["kind"] for e in chain]
    if cx and kinds != ["prime", "bt_action_end"]:
        fails.append(f"{what}: host evs of actionId {aid} = {kinds} (want exactly ['prime', 'bt_action_end'])")
    if cx:
        pl = host_payloads_of(host, chain, "prime")
        want = {"actor": C_ID, "item": gid, "fuse": fuse, "unprime": unprime}
        got = {k: (pl[0] if pl else {}).get(k) for k in want}
        if len(pl) != 1 or got != want:
            fails.append(f"{what}: `prime` cue payload(s) {pl} (want one with {want})")
    return fails, aid


def host_payloads_of(host, chain, kind):
    seqs = [e["seq"] for e in chain if e["kind"] == kind]
    pl = host_payloads(host, seqs) if seqs else {}
    return [cue_of(pl, s) for s in seqs]


# ===================== scenarios =====================


def c23a_prime_unprime(host, client, ctx):
    notes = []
    # ---- leg P: prime (key 49, fuse key 48) ----
    gid = give_grenade(host, client, primed=False)
    pc_ = place(host, client, C_ID, C23A_C_TILE, C23A_C_DIR)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv = {}
    try:
        menu_order(client, pv, KEY_PRIME, fuse_key=KEY_FUSE_0)
    except Exception as e:
        notes.append(f"leg P real-UI prime: {short(e)}")
    out = await_press(host, client, before, notes)
    settle(host, client, notes)
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    common_p = common_fails(host, client, before, "C23a leg P")   # leg P's end state, before leg U
    # ---- leg U: unprime (key 50, the mod's row) on a primed grenade ----
    notes_u = []
    wait_banner_not(client, TEXT_ITEM_ACTION, notes_u)
    gu = give_grenade(host, client, primed=True)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged_u = diff_buckets(host, client)
    before_u = snap(host, client)
    seq_u = before_u["host"]["lastSeqEmitted"] or 0
    pv_u = {}
    try:
        menu_order(client, pv_u, KEY_UNPRIME)
    except Exception as e:
        notes_u.append(f"leg U real-UI unprime: {short(e)}")
    out_u = await_press(host, client, before_u, notes_u)
    settle(host, client, notes_u)
    rec_u = collect(host, client, seq_u)
    new_u = ctx_view(before_u, rec_u)
    common_u = common_fails(host, client, before_u, "C23a leg U")
    fp, aid_p = prime_leg_fails(host, before, rec, pv, "prime", gid, 0, False, "leg P")
    fu, aid_u = prime_leg_fails(host, before_u, rec_u, pv_u, "unprime", gu, -1, True, "leg U")
    print(f"EVIDENCE C23a: LEG P staged grenade={gid} C={pc_} stagedDiff={staged} press={pv} outcome={out}; "
          f"{press_view(before, rec)}; ui={ui_view(before, rec)}; newContexts={new}; action={aid_p} "
          f"chain={[(e['seq'], e['kind']) for e in chain_of(rec, aid_p)]}; host evs={ev_tuples(rec['hev'])} "
          f"client evs={ev_tuples(rec['cev'])}; grenade host={item_view(rec['ih'].get(gid))} "
          f"client={item_view(rec['ic'].get(gid))}; C host={ubrief(rec['uh'].get(C_ID))} "
          f"client={ubrief(rec['uc'].get(C_ID))}; diff={rec['diff']} desync={rec['dsc']}; notes={notes} | "
          f"LEG U staged primed grenade={gu} stagedDiff={staged_u} press={pv_u} outcome={out_u}; "
          f"{press_view(before_u, rec_u)}; ui={ui_view(before_u, rec_u)}; newContexts={new_u}; action={aid_u} "
          f"chain={[(e['seq'], e['kind']) for e in chain_of(rec_u, aid_u)]}; host evs={ev_tuples(rec_u['hev'])} "
          f"client evs={ev_tuples(rec_u['cev'])}; grenade host={item_view(rec_u['ih'].get(gu))} "
          f"client={item_view(rec_u['ic'].get(gu))}; C host={ubrief(rec_u['uh'].get(C_ID))} "
          f"client={ubrief(rec_u['uc'].get(C_ID))}; diff={rec_u['diff']} desync={rec_u['dsc']}; notes={notes_u}",
          flush=True)
    fails = list(notes) + list(notes_u)
    if staged:
        fails.append(f"leg P: buckets differ after the staging: {staged} (want none)")
    fails += fp
    fails += fuse_fails(rec, gid, 0, True, "leg P: grenade")
    fails += [f"leg P: {m}" for m in tu_fails(rec, C_ID, C_TU_FULL - PRIME_TU)]
    fails += aftermath_fails(rec, aid_p, TEXT_PRIMED, "leg P")
    fails += [f"leg P: {m}" for m in common_p]
    if staged_u:
        fails.append(f"leg U: buckets differ after the staging: {staged_u} (want none)")
    fails += fu
    fails += fuse_fails(rec_u, gu, -1, False, "leg U: grenade")
    fails += [f"leg U: {m}" for m in tu_fails(rec_u, C_ID, C_TU_FULL - UNPRIME_TU)]
    fails += aftermath_fails(rec_u, aid_u, TEXT_UNPRIMED, "leg U")
    fails += [f"leg U: {m}" for m in common_u]
    finish(fails)


def c19_throw(host, client, ctx):
    notes = []
    gid = give_grenade(host, client, primed=True)
    pc_ = place(host, client, C_ID, C19_C_TILE, C19_C_DIR)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    near = {"host": near_units(host, C19_TILE, BLAST_BOX_C19), "client": near_units(client, C19_TILE, BLAST_BOX_C19)}
    hurt0 = {"host": hurt_map(host), "client": hurt_map(client)}
    tile0 = {"host": tile(host, C19_TILE), "client": tile(client, C19_TILE)}
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv = {}
    try:
        target_order(client, pv, KEY_THROW, CURSOR_THROW, C19_TILE,
                     lambda: host.ok({"cmd": "set_seed", "seed": SEED_C19}))
    except Exception as e:
        notes.append(f"real-UI throw: {short(e)}")
    out = await_press(host, client, before, notes)
    settle(host, client, notes)
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    hits = mine(new, "intent", "throw", C_ID)
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    shots = shot_payloads(host, chain)
    g_t = {"host": rec["ih"].get(gid), "client": rec["ic"].get(gid)}
    # ---- END TURN: both machines press (client first), the full side cycle ----
    cycle_notes = []
    seq1 = event_state(host).get("lastSeqEmitted") or 0
    terr0 = (terrain(host), terrain(client))
    turn0 = end_turn_cycle(host, client, cycle_notes)
    hs, cs = battle_state(host), battle_state(client)
    hev_c, cev_c = evs_since(host, seq1), evs_since(client, seq1)
    expl = [e for e in hev_c if e["kind"] == "explosion"]
    epl = host_payloads(host, [e["seq"] for e in expl]) if expl else {}
    closed = event_state(host).get("closedContexts") or []
    ectx = {c.get("actionId"): c for c in closed if c.get("origin") == "endturn"}
    ih1, ic1 = items_by_id(host), items_by_id(client)
    hurt1 = {"host": hurt_map(host), "client": hurt_map(client)}
    hurt = {n: hurt_delta(hurt0[n], hurt1[n]) for n in ("host", "client")}
    tile1 = {"host": tile(host, C19_TILE), "client": tile(client, C19_TILE)}
    terr1 = (terrain(host), terrain(client))
    diff_c = diff_buckets(host, client)
    print(f"EVIDENCE C19: staged primed grenade={gid} C={pc_} stagedDiff={staged} unitsNearThrowTile={near} "
          f"press={pv} outcome={out}; {press_view(before, rec)}; ui={ui_view(before, rec)}; newContexts={new}; "
          f"action={aid} chain={[(e['seq'], e['kind']) for e in chain]}; shots={shots}; host evs="
          f"{ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; grenade after the throw host="
          f"{item_view(g_t['host'])} client={item_view(g_t['client'])}; C host={ubrief(rec['uh'].get(C_ID))} "
          f"client={ubrief(rec['uc'].get(C_ID))}; diffAfterThrow={rec['diff']} desync={rec['dsc']}; notes={notes} | "
          f"END TURN: turn {turn0} -> host=({hs.get('turn')},{hs.get('side')}) client=({cs.get('turn')},"
          f"{cs.get('side')}); host evs since seq {seq1}={[(e['seq'], e['kind'], e['actionId']) for e in hev_c]} "
          f"client evs={[(e['seq'], e['kind'], e['actionId']) for e in cev_c]}; explosions="
          f"{[(e['seq'], e['actionId'], cue_of(epl, e['seq'])) for e in expl]}; endturn contexts="
          f"{[c for a, c in ectx.items() if any(e['actionId'] == a for e in hev_c)]}; grenade present host="
          f"{gid in ih1} client={gid in ic1}; units changed={hurt}; tile {C19_TILE} before={tile0} after={tile1}; "
          f"terrain {terr0}->{terr1}; diffAfterCycle={diff_c}; cycleNotes={cycle_notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if near["host"] or near["client"]:
        fails.append(f"precondition: units within {BLAST_BOX_C19} tiles of {C19_TILE}: {near} (want none)")
    if pv.get("rows") != C19_ROWS:
        fails.append(f"precondition: client menu rows {pv.get('rows')} (want {C19_ROWS})")
    # the throw
    fails += forwarded_fails(before, rec)
    f, cx = admitted_fails(before, rec, "throw", "throw", C_ID)
    fails += f
    kinds = [e["kind"] for e in chain]
    if cx and kinds != C19_CHAIN:
        fails.append(f"host evs of actionId {aid} = {kinds} (want exactly {C19_CHAIN})")
    spl = shots[0][1] if len(shots) == 1 else None
    if cx and ((spl or {}).get("action") != "throw" or not isinstance((spl or {}).get("arc"), dict)
               or not (spl or {}).get("arc")):
        fails.append(f"`shot` cue(s) of actionId {aid}: {shots} (want one with action throw and an arc)")
    for n, it in g_t.items():
        if not it or tile_of(it) != C19_TILE or it.get("owner") != -1 or it.get("fuse") != 0:
            fails.append(f"{n} grenade {gid} after the throw {item_view(it)} (want on {C19_TILE}, owner -1, fuse 0)")
    fails += tu_fails(rec, C_ID, C19_TU_AFTER)
    if rec["diff"]:
        fails.append(f"buckets differ after the throw: {rec['diff']} (want none)")
    # END TURN: the grenade's explosion, first ev of the cycle, in an `endturn` context
    fails += [f"END TURN: {m}" for m in cycle_notes]
    first = hev_c[0] if hev_c else None
    fe = first if first and first["kind"] == "explosion" else None
    if not fe:
        fails.append(f"the END TURN cycle's first host ev {first and (first['seq'], first['kind'])} (want the "
                     f"grenade's explosion)")
    else:
        centre = voxel_tile(cue_of(epl, fe["seq"]).get("centreVoxel"))
        ec = ectx.get(fe["actionId"])
        if centre != C19_TILE:
            fails.append(f"the cycle's first explosion is centred on {centre} (want {C19_TILE}): "
                         f"{cue_of(epl, fe['seq'])}")
        if fe["actionId"] == 0 or not ec:
            fails.append(f"the cycle's first explosion (seq {fe['seq']}) carries actionId {fe['actionId']} (want an "
                         f"`endturn` context's id; endturn contexts {list(ectx.values())})")
        else:
            ends = [e["seq"] for e in hev_c if e["actionId"] == fe["actionId"] and e["kind"] == "bt_action_end"]
            sts = [e["seq"] for e in hev_c if e["kind"] == "side_transition"]
            if len(ends) != 1 or not sts or not fe["seq"] < ends[0] < sts[0]:
                fails.append(f"endturn context {ec} ends {ends} (want exactly one bt_action_end after the explosion "
                             f"and before the cycle's side_transition {sts[:1]})")
        cmap = {e["seq"]: e for e in cev_c}
        ce = cmap.get(fe["seq"])
        if not ce or ce["kind"] != "explosion" or ce["actionId"] != fe["actionId"]:
            fails.append(f"client event_log at explosion seq {fe['seq']}: {ce} (want kind explosion, actionId "
                         f"{fe['actionId']})")
    if gid in ih1 or gid in ic1:
        fails.append(f"grenade {gid} present after the cycle host={gid in ih1} client={gid in ic1} (want gone on both)")
    if hurt["host"] or hurt["client"]:
        fails.append(f"units changed (health, stun, status) across the throw and the cycle: {hurt} (want none)")
    if tile1["host"] != tile1["client"]:
        fails.append(f"tile {C19_TILE} after the cycle host={tile1['host']} client={tile1['client']} (want equal)")
    if (hs.get("turn"), hs.get("side"), cs.get("turn"), cs.get("side")) != ((turn0 or 0) + 1, FACTION_PLAYER,
                                                                             (turn0 or 0) + 1, FACTION_PLAYER):
        fails.append(f"not on player turn {(turn0 or 0) + 1} on both: host=({hs.get('turn')},{hs.get('side')}) "
                     f"client=({cs.get('turn')},{cs.get('side')})")
    fails += common_fails(host, client, before, "C19")
    finish(fails)


def c20_launch(host, client, ctx):
    notes = []
    launcher, bomb = give_launcher(host, client)
    pc_ = place(host, client, C_ID, C20_C_TILE, C20_C_DIR)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    cen0 = census(host, C20_BOX)
    hurt0 = {"host": hurt_map(host), "client": hurt_map(client)}
    ids0 = {"host": set(items_by_id(host)), "client": set(items_by_id(client))}
    terr0 = (terrain(host), terrain(client))
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv = {}
    try:
        launch_order(client, pv, lambda: host.ok({"cmd": "set_seed", "seed": SEED_C20}))
    except Exception as e:
        notes.append(f"real-UI launch: {short(e)}")
    out = await_press(host, client, before, notes)
    settle(host, client, notes)
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    hits = mine(new, "intent", "launch", C_ID)
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    pl = host_payloads(host, [e["seq"] for e in chain]) if chain else {}
    legs = [cue_of(pl, e["seq"]) for e in chain if e["kind"] == "shot"]
    expl = [cue_of(pl, e["seq"]) for e in chain if e["kind"] == "explosion"]
    cen1h, cen1c = census(host, C20_BOX), census(client, C20_BOX)
    changed = sorted(t for t in cen1h if cen0.get(t) != cen1h[t])
    cen_diff = sorted(t for t in set(cen1h) | set(cen1c) if cen1h.get(t) != cen1c.get(t))
    hurt1 = {"host": hurt_map(host), "client": hurt_map(client)}
    hurt = {n: hurt_delta(hurt0[n], hurt1[n]) for n in ("host", "client")}
    ids1 = {"host": set(rec["ih"]), "client": set(rec["ic"])}
    gone = {n: sorted(ids0[n] - ids1[n]) for n in ids0}
    added = {n: sorted(ids1[n] - ids0[n]) for n in ids0}
    terr1 = (terrain(host), terrain(client))
    print(f"EVIDENCE C20: staged launcher={launcher} bomb={bomb} C={pc_} stagedDiff={staged} press={pv} "
          f"outcome={out}; {press_view(before, rec)}; ui={ui_view(before, rec)}; launchButtonNow="
          f"{launch_button_nth(client)}; newContexts={new}; action={aid} chain={[(e['seq'], e['kind']) for e in chain]}; "
          f"legs={legs}; explosions={expl}; host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; "
          f"census {len(cen0)} tiles: changed on the host {len(changed)} host-vs-client differ {len(cen_diff)} "
          f"{cen_diff[:8]}; terrain {terr0}->{terr1}; units changed={hurt}; items gone={gone} added={added}; "
          f"C host={ubrief(rec['uh'].get(C_ID))} client={ubrief(rec['uc'].get(C_ID))}; diff={rec['diff']} "
          f"desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    fails += forwarded_fails(before, rec)
    f, cx = admitted_fails(before, rec, "launch", "shoot", C_ID)
    fails += f
    kinds = [e["kind"] for e in chain]
    if cx and kinds != C20_CHAIN:
        fails.append(f"host evs of actionId {aid} = {kinds} (want exactly {C20_CHAIN})")
    if cx and len(legs) == 2:
        l1, l2 = legs
        w1 = (l1.get("action"), l1.get("shotIndex"), l1.get("waypointsLeft"), voxel_tile(l1.get("impactVoxel")))
        w2 = (l2.get("action"), l2.get("shotIndex"), l2.get("waypointsLeft"), voxel_tile(l2.get("originVoxel")),
              voxel_tile(l2.get("impactVoxel")))
        if w1 != ("launch", 1, 2, C20_W):
            fails.append(f"leg 1 (action, shotIndex, waypointsLeft, impact tile)={w1} (want ('launch', 1, 2, {C20_W}))")
        if w2 != ("launch", 2, 1, voxel_tile(l1.get("impactVoxel")), C20_W):
            fails.append(f"leg 2 (action, shotIndex, waypointsLeft, origin tile, impact tile)={w2} (want ('launch', 2, "
                         f"1, leg 1's impact tile {voxel_tile(l1.get('impactVoxel'))}, {C20_W}))")
    elif cx:
        fails.append(f"`shot` legs of actionId {aid}: {legs} (want exactly 2)")
    if cx:
        ex = expl[0] if len(expl) == 1 else {}
        wx = (ex.get("power"), ex.get("radius"), voxel_tile(ex.get("centreVoxel")))
        if len(expl) != 1 or wx != (C20_POWER, C20_RADIUS, C20_W):
            fails.append(f"explosion(s) of actionId {aid}: {expl} (want one with power {C20_POWER}, radius "
                         f"{C20_RADIUS}, centred on {C20_W})")
    if len(changed) != C20_TILES_CHANGED or cen_diff:
        fails.append(f"census box: {len(changed)} tiles changed on the host, {len(cen_diff)} differ host vs client "
                     f"{cen_diff[:8]} (want {C20_TILES_CHANGED} changed, identical on both)")
    if terr1[0] == terr0[0] or terr1[0] != terr1[1]:
        fails.append(f"terrain bucket {terr0}->{terr1} (want changed and equal on both)")
    if hurt["host"] or hurt["client"]:
        fails.append(f"units changed (health, stun, status): {hurt} (want none)")
    for n in ("host", "client"):
        if gone[n] != [bomb] or added[n]:
            fails.append(f"{n} items gone={gone[n]} added={added[n]} (want exactly the bomb {bomb} gone, none added)")
    fails += tu_fails(rec, C_ID, C20_TU_AFTER)
    fails += common_fails(host, client, before, "C20")
    finish(fails)


SCENARIOS = (("C23a", c23a_prime_unprime), ("C19", c19_throw), ("C20", c20_launch))


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    ml = {gc.name: mod_log(gc) for gc in (host, client)}
    for name, m in ml.items():
        assert MOD_ACTIVE_LINE in (m.get("active") or []) and not m.get("invalid"), (
            f"{name}: {MOD_NAME} not active (active lines {m.get('active')}, invalid {m.get('invalid')}, "
            f"error {m.get('error')})")
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} ({MISSION}, SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p4-sb")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hs["units"] if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == SEATED, f"seated client units {seated_uids} (baked {SEATED})"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    ub = session.units_by_id(hs)
    assert (ub.get(C_ID) or {}).get("tu") == C_TU_FULL, f"C at bring-up {ubrief(ub.get(C_ID))} (baked TU {C_TU_FULL})"
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("coopIntentsSent"), dict) and isinstance(es.get("intentsReceived"), dict)
                and "lastActionHalt" in es and "lastAftermath" in es), (
            f"{gc.name} event_state lacks the W2-P4 probes: coopIntentsSent={es.get('coopIntentsSent')!r} "
            f"intentsReceived={es.get('intentsReceived')!r}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2p4-sb] boot ok: {MISSION} MAP_FP={MAP_FP!r} mod={ml} turn={hs['turn']} seated={seated_uids} "
          f"H={H_ID} pinned={len(pinned)} C={ubrief(ub.get(C_ID))} A={ubrief(ub.get(A_ID))} "
          f"A2={ubrief(ub.get(A2_ID))}", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49872, make_user_dir("w2p4_client_grenade_host", mods=[MOD_DIR]))
    client = GameClient("client", 49873, make_user_dir("w2p4_client_grenade_client", mods=[MOD_DIR]))
    results = {}
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:  # a bring-up failure fails the whole run
            print(f"FAIL boot: {type(e).__name__}: {e}", flush=True)
            return 2
        for name, fn in SCENARIOS:
            try:
                fn(host, client, ctx)
                results[name] = True
                print(f"PASS {name}", flush=True)
            except Exception as e:
                results[name] = False
                kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
                print(f"FAIL {name}: {kind}{e}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p4-sb] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_client_grenade: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
