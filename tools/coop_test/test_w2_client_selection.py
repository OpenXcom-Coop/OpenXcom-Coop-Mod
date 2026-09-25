"""W2-H6 - test_w2_client_selection.py: the client's selected unit and the
actor of its current battle action (spec rewrite/prompts/w2h6_client_selection_actor.md
section (d); F1170, F1200-F1208).

Vanilla pairs every player-driven selection change with the action actor and
the cursor (BattlescapeState::selectNextPlayerUnit: cancelAllActions(), the
actor = the new unit, setupCursor()). The client's co-op selection writers do
not: the side_begin re-select (connectionTCP.cpp, `save->selectNextPlayerUnit()`
under mySideActive) moves the selection and leaves the actor where it was (null
in a gm2 battle, the previous unit in ordinary co-op), and nothing on the client
clears a selected unit that dies. The action menu is built from the selected
unit's right-hand item with whatever the actor is, so a gm2 client dies on the
THROW row (getFiringAccuracy with a null attacker, F1170) and an ordinary
client's order carries the stale actor (F1205).

Probe: battle_state.currentActionActorId (this machine's
BattlescapeGame::_currentAction.actor id, -1 for null) beside selectedId.

Five scenarios, THREE boots, in this order. The client acts only through its
real UI: the right-hand box (click_widget nth RHAND_NTH, the box at RHAND_RECT),
the action key, HOME + one self-verified tile click, TAB. No scenario selects
anything for the client before its press.

 Boot 1 - gm2 (repro_pvp_side_relative.drive_to_gm2_battlescape: STR_SMALL_SCOUT,
 set_seed 1 before open_new_battle and before newbattle_ok, the client on the
 Alien team), pin_ai_neutral (0 is legal in gm2), every X-COM soldier's
 reactions 0 on both.
  H6a  the host presses END TURN and the battle crosses to the hostile side
       (the client's). The client presses the right-hand box of its selected
       alien. RED (at 282551690): the client process dies (rc 3) with a crash
       report; the test records the rc and the report as the evidence, fails
       the scenario and goes on with the other boots. GREEN: the client is
       alive, ActionMenuState is on top, currentActionActorId == selectedId
       (the alien) before the press and with the menu open; ESC.

 Boot 2 - traditional (test_rw_turn_baton.pre_ok_traditional; the roster pin
 of test_w2_host_combat.py; STR_TERROR_MISSION map seed 1, MAP_FP on both,
 pin_ai_neutral, the client's seated units SEATED).
  H6b  the capture's C2 steps: the host's END TURN passes the baton to seat 1,
       the client's END TURN closes the side, the full cycle to turn 2, the
       host's END TURN passes the baton again. Staging for H6b2 (neither lever
       touches the selection or the action): the client's selected unit S gets
       a rifle + clip and stands on H6B_TILE facing east (both machines). The
       client presses the right-hand box and the menu stays open for H6b2.
       RED: currentActionActorId != selectedId (8 vs 9). GREEN: equal before
       the press and with the menu open; the menu's rows are the rows of S's
       right-hand weapon (WEAPON_ROWS).
  H6b2 F1205: from that open menu, the SNAP key, HOME, host set_seed
       SEED_SHOT, one left click on the floor tile H6B_TARGET. RED: whatever
       this build does, printed in the EVIDENCE line (by reading: the order
       carries the stale actor and the host answers deny weapon_missing).
       GREEN: host closedContexts gains exactly one {origin intent, kind
       shoot, actorId S}.

 Boot 3 - parallel (the same terror boot, parallel mode).
  H6c  one END TURN cycle (the client presses first, the host once it paints
       END TURN 1/2, the full cycle), then the step the capture's B2 lacked
       (F1207): each next-turn screen on top is dismissed the way a player
       does it (one Enter key through inject_input, NextTurnState::handle)
       until both machines show the battlescape and the client has caught up.
       The client presses the right-hand box, then ESC. RED / GREEN as H6b.
  H6d  the host kills the client's selected soldier V (capD staging: shooter
       H_ID with a rifle + clip on SHOOTER_TILE, TU max, firing 120; V on
       VICTIM_TILE with health 1; host set_seed SEED_SHOT; battle_fire snap at
       V). One construction: V not DEAD on both = the precondition failed, no
       press. RED: the client's selectedId stays V (dead) and V stays the
       actor; the press does nothing. GREEN: selectedId -1 and
       currentActionActorId -1 on the player side; the press does nothing (the
       client alive, the battlescape on top, the selection unchanged); then ONE
       TAB selects a live soldier of the client's seat with
       currentActionActorId == selectedId.

Common asserts after every scenario (spec (d)): after wait_host_idle, hash_now
{full:true} with every bucket EQUAL (never a hard-coded count);
coopClientBStatePushes 0 on both; desyncSeen false on both. Each scenario
prints ONE "EVIDENCE <id>:" line with both machines' fields BEFORE its green
conditions are checked, then "PASS <id>" or "FAIL <id>: <message>". Every wait
is bounded; a wait that times out is recorded and fails the scenario. A boot
that does not come up fails its own scenarios and the next boot still runs.

Item ids vary per boot (F1107): they are read at run time. Every lever pair
goes to the CLIENT first (F607). WV-D99 / WV-D100: one run is the result; no
second boot, no alternative map or actor. Exit 0 only when all five scenarios
pass, 2 otherwise. WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_client_selection.py
"""

import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, EXE
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from repro_atom_side_begin import row_for as gm2_row_for, drive_side_change
from repro_pvp_side_relative import drive_to_gm2_battlescape
from test_rw_turn_baton import RHAND_NTH, pre_ok_traditional, drive_full_cycle, dismiss_next_turn_if_present
from test_rw_seat_pacing import SDLK_TAB, SDLK_HOME
from test_w2_delta_core import diff_buckets, desync_record, short, both
from test_w2_delta_items import items_by_id
from test_w2_host_combat import bring_up_lobby_roster_pinned
from test_w2_client_shoot import (snap, await_press, new_contexts, mine, press_view, ui_view, menu_rows,
                                  KEY_SNAP, CURSOR_AIM, RHAND_CENTRE)

# ----- boot 1: gm2 (W2-P4 T0c C25 / the W2-H6 capture A) -----
GM2_PORT = "48191"
GM2_SEED = 1                       # set_seed on the HOST before open_new_battle (the roster)

# ----- boots 2 and 3: the roster-pinned terror boot (test_w2_host_combat.py) -----
MISSION = "STR_TERROR_MISSION"
SEED_MAP = 1
MAP_FP = -3.451266327757785e+18   # host battle_state.mapFingerprint on SEED_MAP 1 (T0a, every boot)
SEATED = [8, 9]                   # the client's seated units
H_ID = 10                         # first host-seat soldier
TRAD_PORT = "48192"
PAR_PORT = "48193"

FACTION_PLAYER, FACTION_HOSTILE = 0, 1
COOP_SEAT_0, COOP_SEAT_1 = 0, 1
STATUS_DEAD = 6                   # src/Mod/Unit.h enum UnitStatus
TU_MAX = 255                      # battle_set_unit_state tu: clamped to the unit's max TU
FIRING_120 = 120
SEED_SHOT = 1

# ----- H6b / H6b2 -----
H6B_TILE, H6B_DIR = (12, 26, 0), 2   # open road (test_w2_client_shoot C_TILE), facing east
H6B_TARGET = (16, 26, 0)             # floor tile due east: no pre-shot turn (test_w2_client_shoot C17P_SNAP_TARGET)
# ActionMenuState rows per right-hand weapon (the W2-H6 capture: STR_RIFLE THROW/AUTO/SNAP/AIMED,
# STR_ROCKET_LAUNCHER THROW/SNAP/AIMED).
WEAPON_ROWS = {"STR_RIFLE": 4, "STR_ROCKET_LAUNCHER": 3}

# ----- H6d (the capture's capD staging) -----
SHOOTER_TILE, SHOOTER_DIR = (12, 26, 0), 1
VICTIM_TILE, VICTIM_DIR = (12, 23, 0), 0

# ----- UI -----
KEY_ESC = 27
KEY_OK = 13                       # SDLK_RETURN, Options::keyOk default: closes a NextTurnState (NextTurnState::handle)
MENU_STATE = "ActionMenuState"
BS_STATE = "BattlescapeState"
NEXT_TURN_STATE = "NextTurnState"
MENU_WAIT_S = 4.0
CRASH_WAIT_S = 10.0
CRASHLOGS = os.path.join(os.path.dirname(EXE), "crashlogs")


# ===================== small probes =====================


def top(gc):
    return session.top_state(gc)


def alive(gc):
    return gc.proc is not None and gc.proc.poll() is None


def units(gc):
    return session.units_by_id(battle_state(gc))


def right_hand(gc, uid):
    """(item id, type) of `uid`'s right-hand item on this machine, or None."""
    for i, it in sorted(items_by_id(gc).items()):
        if it.get("owner") == uid and it.get("slot") == "STR_RIGHT_HAND":
            return i, it.get("type")
    return None


def sel_view(gc):
    """This machine's selection, action actor, top state and turn fields."""
    bs = battle_state(gc)
    es = event_state(gc)
    return {"selectedId": bs.get("selectedId"), "actorId": bs.get("currentActionActorId"), "top": top(gc),
            "side": bs.get("side"), "turn": bs.get("turn"), "activeSeat": es.get("coopActiveSeat"),
            "cursor": bs.get("cursorType"), "banner": bs.get("coopWaitText")}


def dump(host, client):
    """Both machines' selection fields; a dead machine reads as its rc."""
    out = {}
    for gc in (host, client):
        if not alive(gc):
            out[gc.name] = {"rc": gc.proc.poll() if gc.proc else None}
            continue
        try:
            out[gc.name] = sel_view(gc)
        except Exception as e:
            out[gc.name] = {"probe": short(e)}
    return out


def ubrief(u):
    if not u:
        return None
    return {k: u.get(k) for k in ("faction", "coop", "status", "isOut", "x", "y", "z", "direction", "tu",
                                  "health", "weapon")}


def press(gc, key):
    gc.ok({"cmd": "inject_input", "kind": "key", "key": key})


def crash_files():
    return set(glob.glob(os.path.join(CRASHLOGS, "*")))


def new_crash_files(before, wait_s=CRASH_WAIT_S):
    """The crash report files written since `before` (bounded wait for a .log)."""
    deadline = time.time() + wait_s
    new = []
    while time.time() < deadline:
        new = sorted(crash_files() - before)
        if any(f.endswith(".log") for f in new):
            break
        time.sleep(0.25)
    return new


def crash_head(files, n=6):
    for f in files:
        if f.endswith(".log"):
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    return fh.read().splitlines()[:n]
            except OSError as e:
                return [short(e)]
    return []


# ===================== staging (client first, F607) =====================


def give_both(host, client, uid, item, ammo):
    g = both(host, client, {"cmd": "battle_give", "unit": uid, "item": item, "ammo": ammo, "clear_hands": True},
             ("weaponId", "ammoId"))
    return g["weaponId"], g["ammoId"]


def tele_both(host, client, uid, t, d):
    return both(host, client, {"cmd": "battle_teleport_unit", "unit": uid, "x": t[0], "y": t[1], "z": t[2],
                               "dir": d}, ("to", "dir"))


def set_stat_both(host, client, uid, stat, value):
    return both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": stat,
                               "value": value}, ("tu",))


def wait_baton(host, client, seat, label, timeout=30):
    def ok():
        return (event_state(host).get("coopActiveSeat") == seat
                and event_state(client).get("coopActiveSeat") == seat) or None
    host.wait_for(f"{label}: coopActiveSeat == {seat} on both", ok, timeout=timeout, interval=0.1)


def settle_tops_close(host, client, label, timeout=15):
    """The capture's settle step (caplib.settle_tops): close any NextTurnState
    on top of either machine through close_nextturn until both tops are the
    battlescape."""
    def ok():
        for gc in (host, client):
            dismiss_next_turn_if_present(gc)
        return (top(host) == BS_STATE and top(client) == BS_STATE) or None
    host.wait_for(f"{label}: both tops {BS_STATE}", ok, timeout=timeout, interval=0.2)


def caught_up(host, client):
    eh, ec = event_state(host), event_state(client)
    return (eh.get("busyOwnerSeat") == -1 and ec.get("lastSeqApplied", 0) == eh.get("lastSeqEmitted", 0)
            and ec.get("queueDepth") == 0 and eh.get("queueDepth") == 0)


def settle_tops_player(host, client, timeout=30):
    """F1207: every next-turn screen on top of either machine is dismissed the
    way a player does it - ONE Enter key through inject_input (a real SDL key
    event into NextTurnState::handle -> close()), then a bounded wait for that
    screen to leave the stack - until both machines show the battlescape, the
    host is idle and the client has caught up. Returns the keys sent per
    machine."""
    keys = {host.name: 0, client.name: 0}
    deadline = time.time() + timeout
    while time.time() < deadline:
        for gc in (client, host):
            st = session.states_stripped(gc)
            if st and st[-1] == NEXT_TURN_STATE:
                n0 = len(st)
                press(gc, KEY_OK)
                keys[gc.name] += 1
                gc.wait_for("the next-turn screen leaves the stack",
                            lambda: len(session.states_stripped(gc)) < n0 or None, timeout=5, interval=0.1)
        if top(host) == BS_STATE and top(client) == BS_STATE and caught_up(host, client):
            return keys
        time.sleep(0.2)
    raise TimeoutError(f"the battlescape never came back on top of both machines in {timeout} s "
                       f"(keys sent {keys}; {dump(host, client)})")


# ===================== the client's real-UI press =====================


def rhand_press(client, want_menu):
    """ONE real press of the client's right-hand box (click_widget nth
    RHAND_NTH), no TAB or click selection first. Waits (bounded) for the
    ActionMenuState when `want_menu`, else MENU_WAIT_S; a process death ends
    the wait. Returns the evidence."""
    ev = {}
    try:
        r = client.cmd({"cmd": "click_widget", "nth": RHAND_NTH, "button": "left"})
        ev["click"] = {k: r.get(k) for k in ("ok", "baseX", "baseY", "error")}
    except Exception as e:
        ev["click"] = short(e)
    t0 = time.time()
    while time.time() - t0 < MENU_WAIT_S:
        if not alive(client):
            break
        try:
            last = top(client)
        except Exception as e:
            ev["probe"] = short(e)
            try:
                client.proc.wait(timeout=CRASH_WAIT_S)
            except Exception:
                pass
            break
        if want_menu and last == MENU_STATE:
            break
        time.sleep(0.1)
    ev["t"] = round(time.time() - t0, 2)
    ev["top"] = None
    if alive(client):
        try:
            ev["top"] = top(client)
            if ev["top"] == MENU_STATE:
                ev["rows"] = menu_rows(client)
                ev["actorInMenu"] = battle_state(client).get("currentActionActorId")
                ev["selectedInMenu"] = battle_state(client).get("selectedId")
        except Exception as e:
            ev["probe"] = short(e)
            try:
                client.proc.wait(timeout=CRASH_WAIT_S)
            except Exception:
                pass
    ev["alive"] = alive(client)
    ev["rc"] = client.proc.poll() if client.proc else None
    if not ev["alive"]:
        ev["top"] = None
    return ev


def click_fails(ev):
    c = ev.get("click")
    if not isinstance(c, dict) or not c.get("ok") or (c.get("baseX"), c.get("baseY")) != RHAND_CENTRE:
        return [f"precondition: the right-hand box click {c} (want ok at base {RHAND_CENTRE})"]
    return []


def close_menu(client):
    """ESC on the open ActionMenuState; returns the top afterwards (bounded)."""
    press(client, KEY_ESC)
    try:
        client.wait_for(f"client {BS_STATE} on top after ESC", lambda: top(client) == BS_STATE or None, timeout=5)
    except Exception:
        pass
    return top(client)


# ===================== common asserts =====================


def common_fails(host, client, what):
    """Spec (d) common: buckets equal, coopClientBStatePushes 0, no desync."""
    fails = []
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        fails.append(f"wait_host_idle: {short(e)}")
    try:
        assert_hash_clean(host, client, full=True, what=what)
    except AssertionError as e:
        fails.append(f"hash_now full not clean: {short(e, 600)}")
    for gc in (host, client):
        es = event_state(gc)
        if es.get("coopClientBStatePushes") != 0:
            fails.append(f"{gc.name} coopClientBStatePushes={es.get('coopClientBStatePushes')} (want 0)")
        if es.get("desyncSeen"):
            fails.append(f"{gc.name} desyncSeen true {desync_record(gc, True)} (want false)")
    return fails


def finish(fails):
    if fails:
        raise AssertionError("; ".join(fails))


def own_live(u):
    return bool(u) and u.get("coop") == COOP_SEAT_1 and not u.get("isOut")


# ===================== boot 1: gm2 =====================


def boot_gm2(host, client):
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    host.ok({"cmd": "set_seed", "seed": GM2_SEED})
    raw.skirmish_host(host, GM2_PORT)
    raw.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": GM2_PORT, "player": raw.CLIENT_PLAYER})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: raw.lobby(host).get("buttonVisible") or None)
    r = host.ok({"cmd": "lobby_set_team", "row": gm2_row_for(host, raw.CLIENT_PLAYER), "team": "Alien"})
    assert r.get("gamemode") == 2, f"lobby_set_team Alien answered gamemode {r.get('gamemode')} (want 2)"
    time.sleep(1)   # the change_team broadcast settles on the client (repro_pvp_side_relative PHASE 0)
    drive_to_gm2_battlescape(host, client)
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("coopGamemode") == 2 and cs.get("coopGamemode") == 2, (
        f"coopGamemode host={hs.get('coopGamemode')} client={cs.get('coopGamemode')} (want 2 on both)")
    pinned = pin_ai_neutral(host, client, tag="w2h6-gm2")
    xcom = sorted(u["id"] for u in hs["units"] if u.get("faction") == FACTION_PLAYER
                  and u.get("coop") == COOP_SEAT_0 and not u.get("isOut"))
    assert xcom, "no live X-COM soldier on the host"
    for uid in xcom:
        set_stat_both(host, client, uid, "reactions", 0)
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="gm2 bring-up")
    print(f"[w2h6] gm2 boot ok: mapFP={hs.get('mapFingerprint')} side={hs.get('side')}/{cs.get('side')} "
          f"pinned={len(pinned)} xcom reactions 0={xcom} selection={dump(host, client)}", flush=True)
    return {}


def h6a_gm2_press(host, client, ctx):
    notes = []
    crash0 = crash_files()
    try:
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        drive_side_change(host, client, FACTION_HOSTILE, timeout=60)
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"precondition: the hostile side was not reached: {short(e)}; {dump(host, client)}")
    pre = dump(host, client)
    cv = pre.get("client", {})
    sel = cv.get("selectedId")
    su = units(client).get(sel) if alive(client) else None
    rh = right_hand(client, sel) if (alive(client) and sel not in (None, -1)) else None
    ev = {}
    crash = []
    esc_top = None
    if not notes:
        ev = rhand_press(client, want_menu=True)
        if not ev["alive"]:
            crash = new_crash_files(crash0)
        elif ev["top"] == MENU_STATE:
            esc_top = close_menu(client)
    diff = diff_buckets(host, client) if alive(client) else None
    print(f"EVIDENCE H6a: pre={pre} selectedUnit={ubrief(su)} rightHand={rh} press={ev} crashFiles={crash} "
          f"crashHead={crash_head(crash)} afterEsc={esc_top} diff={diff} notes={notes}", flush=True)
    fails = list(notes)
    if notes:
        finish(fails)
    if cv.get("side") != FACTION_HOSTILE or cv.get("top") != BS_STATE:
        fails.append(f"precondition: client side={cv.get('side')} top={cv.get('top')} (want {FACTION_HOSTILE}, "
                     f"{BS_STATE})")
    if not (own_live(su) and su.get("faction") == FACTION_HOSTILE and rh):
        fails.append(f"precondition: the client's selected unit {sel} {ubrief(su)} right hand {rh} (want a live "
                     f"seat-1 alien holding an item)")
    if cv.get("actorId") != sel:
        fails.append(f"client currentActionActorId {cv.get('actorId')} != selectedId {sel} before the press "
                     f"(want the alien)")
    fails += click_fails(ev) if ev else []
    if ev and not ev["alive"]:
        fails.append(f"the client process died after the press: rc={ev['rc']} crash report={crash}")
        finish(fails)
    if ev.get("top") != MENU_STATE:
        fails.append(f"client top after the press {ev.get('top')} (want {MENU_STATE})")
    elif ev.get("actorInMenu") != sel:
        fails.append(f"client currentActionActorId {ev.get('actorInMenu')} with the menu open (want selectedId {sel})")
    if ev.get("top") == MENU_STATE and esc_top != BS_STATE:
        fails.append(f"client top after ESC {esc_top} (want {BS_STATE})")
    fails += common_fails(host, client, "H6a")
    finish(fails)


# ===================== boots 2 and 3: the terror boot =====================


def boot_terror(host, client, port, pre_ok, mode):
    bring_up_lobby_roster_pinned(host, client, port)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2, pre_ok=pre_ok)
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} ({MISSION}, SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag=f"w2h6-{mode}")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hs["units"] if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == SEATED, f"seated client units {seated_uids} (baked {SEATED})"
    modes = (event_state(host).get("turnMode"), event_state(client).get("turnMode"))
    assert modes == (mode, mode), f"turnMode host/client={modes} (want {mode} on both)"
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what=f"{mode} bring-up")
    print(f"[w2h6] {mode} boot ok: {MISSION} MAP_FP={MAP_FP!r} seated={seated_uids} pinned={len(pinned)} "
          f"selection={dump(host, client)}", flush=True)
    return {}


def boot_trad(host, client):
    return boot_terror(host, client, TRAD_PORT, pre_ok_traditional, "traditional")


def boot_par(host, client):
    return boot_terror(host, client, PAR_PORT, lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}), "parallel")


def menu_checks(pre_c, sel, rh, ev):
    """H6b / H6c green: actor == selected before the press and with the menu
    open; the menu's rows are the selected unit's right-hand weapon's."""
    fails = []
    if pre_c.get("actorId") != sel:
        fails.append(f"client currentActionActorId {pre_c.get('actorId')} != selectedId {sel} before the press")
    if not ev.get("alive"):
        fails.append(f"the client process died after the press: rc={ev.get('rc')}")
        return fails
    if ev.get("top") != MENU_STATE:
        fails.append(f"client top after the press {ev.get('top')} (want {MENU_STATE})")
        return fails
    if ev.get("actorInMenu") != sel:
        fails.append(f"client currentActionActorId {ev.get('actorInMenu')} with the menu open (want selectedId {sel})")
    want = WEAPON_ROWS.get(rh[1]) if rh else None
    if want is None or ev.get("rows") != want:
        fails.append(f"menu rows {ev.get('rows')} (want {want}: the rows of the selected unit's right-hand "
                     f"{rh[1] if rh else None})")
    return fails


def h6b_trad_menu(host, client, ctx):
    notes = []
    ctx["h6bMenu"] = False
    staged = {}
    try:
        wait_baton(host, client, COOP_SEAT_0, "entry")
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        wait_baton(host, client, COOP_SEAT_1, "turn 1 pass")
        turn0 = battle_state(host).get("turn")
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        drive_full_cycle(host, client, turn0, timeout=90)
        session.wait_host_idle(host, client, timeout=30)
        settle_tops_close(host, client, "cycle")
        wait_baton(host, client, COOP_SEAT_0, "turn 2 entry")
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        wait_baton(host, client, COOP_SEAT_1, "turn 2 pass")
        settle_tops_close(host, client, "turn 2 pass")
        session.wait_host_idle(host, client, timeout=30)
        sel0 = battle_state(client).get("selectedId")
        staged["unit"] = sel0
        staged["rifle"] = give_both(host, client, sel0, "STR_RIFLE", "STR_RIFLE_CLIP")
        staged["tele"] = tele_both(host, client, sel0, H6B_TILE, H6B_DIR).get("to")
        staged["diff"] = diff_buckets(host, client)
    except Exception as e:
        notes.append(f"precondition: the client's turn-2 baton was not reached: {short(e)}; {dump(host, client)}")
    pre = dump(host, client)
    pc = pre["client"]
    sel = pc.get("selectedId")
    su = units(client).get(sel)
    rh = right_hand(client, sel) if sel not in (None, -1) else None
    ev = rhand_press(client, want_menu=True) if not notes else {}
    ctx["h6bMenu"] = bool(ev.get("alive") and ev.get("top") == MENU_STATE)
    ctx["h6bSel"] = sel
    ctx["h6bWeapon"] = rh
    print(f"EVIDENCE H6b: staged={staged} pre={pre} selectedUnit={ubrief(su)} rightHand={rh} press={ev} "
          f"notes={notes}", flush=True)
    fails = list(notes)
    if notes:
        finish(fails)
    if (pc.get("turn") or 0) < 2 or pc.get("side") != FACTION_PLAYER or pc.get("activeSeat") != COOP_SEAT_1 \
            or pc.get("top") != BS_STATE:
        fails.append(f"precondition: client turn={pc.get('turn')} side={pc.get('side')} baton={pc.get('activeSeat')} "
                     f"top={pc.get('top')} (want turn >= 2, side {FACTION_PLAYER}, baton {COOP_SEAT_1}, {BS_STATE})")
    if not (own_live(su) and sel in SEATED):
        fails.append(f"precondition: the client's selected unit {sel} {ubrief(su)} (want a live seated unit)")
    if staged.get("diff"):
        fails.append(f"buckets differ after the staging: {staged['diff']} (want none)")
    fails += click_fails(ev)
    fails += menu_checks(pc, sel, rh, ev)
    fails += common_fails(host, client, "H6b")
    finish(fails)


def h6b2_trad_snap(host, client, ctx):
    notes = []
    sel = ctx.get("h6bSel")
    if not ctx.get("h6bMenu"):
        raise AssertionError(f"H6b left no open action menu on the client ({dump(host, client)}): the snap "
                             f"from that menu cannot run")
    before = snap(host, client)
    aim = {}
    pr = {}
    out = {}
    try:
        press(client, KEY_SNAP)
        client.wait_for(f"client {BS_STATE} on top after the SNAP key", lambda: top(client) == BS_STATE or None,
                        timeout=5)
        cs = battle_state(client)
        aim = {"cursor": cs.get("cursorType"), "actorId": cs.get("currentActionActorId"),
               "selectedId": cs.get("selectedId")}
        if aim["cursor"] != CURSOR_AIM:
            notes.append(f"precondition: the SNAP key did not start targeting (cursorType {aim['cursor']}, want "
                         f"{CURSOR_AIM})")
        else:
            press(client, SDLK_HOME)
            time.sleep(0.15)
            r = client.cmd({"cmd": "map_tile_click_pos", "x": H6B_TARGET[0], "y": H6B_TARGET[1], "z": H6B_TARGET[2]})
            pr = {k: r.get(k) for k in ("verified", "winX", "winY", "centered")}
            if not r.get("verified"):
                notes.append(f"precondition: map_tile_click_pos did not verify {H6B_TARGET}: {r}")
            else:
                host.ok({"cmd": "set_seed", "seed": SEED_SHOT})
                client.ok({"cmd": "inject_input", "kind": "click", "x": r["winX"], "y": r["winY"], "button": "left"})
                out = await_press(host, client, before, notes)
    except Exception as e:
        notes.append(f"real-UI snap: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    rec = snap(host, client)
    new = new_contexts(before["host"]["closedContexts"], rec["host"]["closedContexts"])
    hits = mine(new, "intent", "shoot", sel)
    print(f"EVIDENCE H6b2: selected={sel} weapon={ctx.get('h6bWeapon')} target={H6B_TARGET} aim={aim} clickPos={pr} "
          f"outcome={out}; {press_view(before, rec)}; ui={ui_view(before, rec)}; newContexts={new}; "
          f"lastDeny={rec['client']['lastDeny']}; intentsReceived host={rec['host']['intentsReceived']}; "
          f"after={dump(host, client)} diff={diff_buckets(host, client)}; notes={notes}", flush=True)
    fails = list(notes)
    if len(hits) != 1:
        fails.append(f"host closedContexts gained {len(hits)} {{origin intent, kind shoot, actorId {sel}}} (want "
                     f"exactly 1; new contexts={new}; client lastDeny={rec['client']['lastDeny']})")
    fails += common_fails(host, client, "H6b2")
    finish(fails)


def h6c_par_menu(host, client, ctx):
    notes = []
    keys = {}
    turn0 = None
    try:
        turn0 = battle_state(host).get("turn")
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        host.wait_for("host paints END TURN 1/2 after the client's press",
                      lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2" or None, timeout=20)
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        drive_full_cycle(host, client, turn0, timeout=90)
        session.wait_host_idle(host, client, timeout=30)
        keys = settle_tops_player(host, client)
    except Exception as e:
        notes.append(f"precondition: the battlescape was not back on top after the cycle: {short(e)}; "
                     f"{dump(host, client)}")
    pre = dump(host, client)
    pc = pre["client"]
    sel = pc.get("selectedId")
    su = units(client).get(sel)
    rh = right_hand(client, sel) if sel not in (None, -1) else None
    ev = rhand_press(client, want_menu=True) if not notes else {}
    esc_top = close_menu(client) if ev.get("top") == MENU_STATE else None
    print(f"EVIDENCE H6c: turn0={turn0} nextTurnKeys={keys} pre={pre} selectedUnit={ubrief(su)} rightHand={rh} "
          f"press={ev} afterEsc={esc_top} notes={notes}", flush=True)
    fails = list(notes)
    if notes:
        finish(fails)
    if (pc.get("turn") or 0) < (turn0 or 0) + 1 or pc.get("side") != FACTION_PLAYER or pc.get("top") != BS_STATE:
        fails.append(f"precondition: client turn={pc.get('turn')} side={pc.get('side')} top={pc.get('top')} (want "
                     f"turn >= {(turn0 or 0) + 1}, side {FACTION_PLAYER}, {BS_STATE})")
    if not (own_live(su) and sel in SEATED):
        fails.append(f"precondition: the client's selected unit {sel} {ubrief(su)} (want a live seated unit)")
    fails += click_fails(ev)
    fails += menu_checks(pc, sel, rh, ev)
    if ev.get("top") == MENU_STATE and esc_top != BS_STATE:
        fails.append(f"client top after ESC {esc_top} (want {BS_STATE})")
    fails += common_fails(host, client, "H6c")
    finish(fails)


def h6d_par_death(host, client, ctx):
    notes = []
    if not alive(client) or not alive(host):
        raise AssertionError(f"a machine is not running: {dump(host, client)}")
    v = battle_state(client).get("selectedId")
    v0 = units(client).get(v)
    staged = {}
    vh = vc = None
    try:
        assert own_live(v0) and v0.get("faction") == FACTION_PLAYER, (
            f"precondition: the client's selected unit {v} {ubrief(v0)} (want a live soldier of seat 1)")
        staged["shooterGun"] = give_both(host, client, H_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
        staged["shooter"] = tele_both(host, client, H_ID, SHOOTER_TILE, SHOOTER_DIR).get("to")
        both(host, client, {"cmd": "battle_set_unit_state", "unit": H_ID, "tu": TU_MAX}, ("tu",))
        set_stat_both(host, client, H_ID, "firing", FIRING_120)
        staged["victim"] = tele_both(host, client, v, VICTIM_TILE, VICTIM_DIR).get("to")
        both(host, client, {"cmd": "battle_set_unit_state", "unit": v, "health": 1}, ("health", "stun", "status"))
        staged["diff"] = diff_buckets(host, client)
        host.ok({"cmd": "set_seed", "seed": SEED_SHOT})
        staged["fire"] = {k: host.cmd({"cmd": "battle_fire", "unit": H_ID, "mode": "snap", "target": v}).get(k)
                          for k in ("ok", "tuCost", "tuHave", "error")}
        host.wait_for("the victim DEAD on the host",
                      lambda: (units(host).get(v) or {}).get("status") == STATUS_DEAD or None, timeout=30)
        session.wait_host_idle(host, client, timeout=30)
        time.sleep(1.5)
    except Exception as e:
        notes.append(f"kill: {short(e)}")
    vh, vc = units(host).get(v), units(client).get(v)
    dead = (vh or {}).get("status") == STATUS_DEAD and (vc or {}).get("status") == STATUS_DEAD
    after = dump(host, client)
    ev = {}
    tab = {}
    if dead:
        ev = rhand_press(client, want_menu=False)
        ev["selectedAfter"] = battle_state(client).get("selectedId") if ev.get("alive") else None
        if ev.get("alive") and ev.get("top") == MENU_STATE:
            ev["afterEsc"] = close_menu(client)
        if ev.get("alive"):
            s0 = battle_state(client).get("selectedId")
            press(client, SDLK_TAB)
            try:
                client.wait_for("the TAB selection lands", lambda: battle_state(client).get("selectedId") != s0 or None,
                                timeout=3)
            except Exception as e:
                tab["wait"] = short(e)
            cs = battle_state(client)
            tab.update({"selectedId": cs.get("selectedId"), "actorId": cs.get("currentActionActorId"),
                        "unit": ubrief(units(client).get(cs.get("selectedId")))})
    print(f"EVIDENCE H6d: victim={v} {ubrief(v0)} staged={staged} victim host={ubrief(vh)} client={ubrief(vc)} "
          f"dead={dead} afterKill={after} press={ev} tab={tab} notes={notes}", flush=True)
    fails = list(notes)
    if not dead:
        fails.append(f"precondition: victim {v} not DEAD on both after the one construction (host "
                     f"{(vh or {}).get('status')}, client {(vc or {}).get('status')}); no press ({after})")
        finish(fails)
    ac = after["client"]
    if ac.get("side") == FACTION_PLAYER and (ac.get("selectedId") != -1 or ac.get("actorId") != -1):
        fails.append(f"client selectedId {ac.get('selectedId')} actor {ac.get('actorId')} after its selected unit {v} "
                     f"died (want -1 and -1 on the player side)")
    if ac.get("side") != FACTION_PLAYER:
        fails.append(f"precondition: client side {ac.get('side')} after the kill (want {FACTION_PLAYER})")
    if not ev.get("alive"):
        fails.append(f"the client process died after the press: rc={ev.get('rc')}")
        finish(fails)
    if ev.get("top") != BS_STATE or ev.get("selectedAfter") != ac.get("selectedId"):
        fails.append(f"the press was not a no-op: top {ev.get('top')} selectedId {ac.get('selectedId')} -> "
                     f"{ev.get('selectedAfter')} (want {BS_STATE}, unchanged)")
    tu = units(client).get(tab.get("selectedId"))
    if not (own_live(tu) and tu.get("faction") == FACTION_PLAYER and tab.get("selectedId") != v):
        fails.append(f"TAB selected {tab.get('selectedId')} {ubrief(tu)} (want a live soldier of seat 1 other than {v})")
    if tab.get("actorId") != tab.get("selectedId"):
        fails.append(f"after TAB currentActionActorId {tab.get('actorId')} != selectedId {tab.get('selectedId')}")
    fails += common_fails(host, client, "H6d")
    finish(fails)


BOOTS = (
    ("gm2", boot_gm2, (("H6a", h6a_gm2_press),)),
    ("traditional", boot_trad, (("H6b", h6b_trad_menu), ("H6b2", h6b2_trad_snap))),
    ("parallel", boot_par, (("H6c", h6c_par_menu), ("H6d", h6d_par_death))),
)


def shutdown(gc):
    rc = gc.proc.poll() if gc.proc else None
    try:
        gc.shutdown()
    except Exception as e:
        print(f"[w2h6] shutdown {gc.name} (rc before shutdown {rc}): {short(e)}", flush=True)


def main():
    t0 = time.time()
    results = {}
    order = [sid for _, _, scs in BOOTS for sid, _ in scs]
    for bname, boot, scenarios in BOOTS:
        host = GameClient("host", 49880, make_user_dir(f"w2h6_sel_{bname}_host"))
        client = GameClient("client", 49881, make_user_dir(f"w2h6_sel_{bname}_client"))
        try:
            try:
                ctx = boot(host, client)
            except Exception as e:
                for sid, _ in scenarios:
                    results[sid] = False
                    print(f"FAIL {sid}: boot {bname}: {type(e).__name__}: {e}", flush=True)
                continue
            for sid, fn in scenarios:
                try:
                    fn(host, client, ctx)
                    results[sid] = True
                    print(f"PASS {sid}", flush=True)
                except Exception as e:
                    results[sid] = False
                    kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
                    print(f"FAIL {sid}: {kind}{e}", flush=True)
        finally:
            for gc in (host, client):
                shutdown(gc)
    passed = [s for s in order if results.get(s)]
    failed = [s for s in order if not results.get(s)]
    print(f"\ntest_w2_client_selection: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
