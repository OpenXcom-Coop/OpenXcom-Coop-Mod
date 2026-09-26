"""W2-P4 S-E4 - test_w2_client_pvp.py (C25): in a PvP battle (gm2, the second
player on the Alien team) the second player orders its own alien on its own
(hostile) side, and the host checks and runs the order (spec
rewrite/prompts/w2p4_client_combat_intents.md section (f)
"test_w2_client_pvp.py (S-E; gm2)", Q8 (a), as amended by AMENDMENT C1 (PR-Q8:
a gm2 client-ordered alien action does not end the alien side, so C25 asserts
the side stays HOSTILE and no side_transition follows the shot; PR-Q9: the F487
spectator notice is printed, not asserted; N26 = F1093: the gm2 hostile-side
turn / kneel / walk intents are admitted too; N30 = F1097: pin_ai_neutral skips
the seat-0 soldiers, so every X-COM soldier's reactions are set to 0 on both
machines) and AMENDMENT C4 (F1170: the client's hand box on the hostile side,
fixed by W2-H6, now reaches the intercept).

Before S-E4 the host denies every order the second player gives on its own side
`turn_over`: onIntent's turn check compares the side with the HOST's own seat
faction (mySideActive, seat 0 -> FACTION_PLAYER), while a gm2 seat 1 commands
FACTION_HOSTILE (N1 = F1068, captured by TASK 0 T0-12). After S-E4 the check
compares the side with the INTENT seat's faction (factionOf(seat)), and the
host's popState no longer ends the alien side after an action a human seat
ordered (PR-Q8).

ONE boot, one scenario with two legs, in this order:

  C25  staging on the player side (T0-12, both machines, client first): X-COM
       reactions 0 for every live seat-0 soldier, soldier S -> S_TILE facing
       S_DIR, the client's alien A -> A_TILE facing A_DIR (open ground, S three
       tiles south of A). The host presses END TURN; both machines reach the
       hostile side (the client's). S is in A's spottedThisTurn on both.
    leg W  the negative control (T0-12, N26): a client `battle_intent walk` for
       A to WALK_DEST (one tile behind A). RED: the host denies it `turn_over`
       (client lastDeny; the banner "The turn has already ended"), nothing
       executed. GREEN: host closedContexts gains exactly one {origin intent,
       kind walk, actorId A}; A on WALK_DEST on both; the side still HOSTILE on
       both and no side_transition since the order (PR-Q8).
    leg S  the client's alien snaps at S through its REAL UI: TAB-selection of
       A, the right-hand box (the plasma pistol's menu, PISTOL_ROWS rows), key
       50 (SNAP), HOME, host set_seed SEED_C25 (determinism only: the shot's
       outcome is not asserted), one self-verified left click on S's tile.
       RED: the order is sent and the host denies it `turn_over`, nothing
       executed. GREEN: host closedContexts gains exactly one {origin intent,
       kind shoot, actorId A}; S's state equal on both; the side still HOSTILE
       on both; no side_transition on the host since the press (so none after
       the shot's bt_action_end, PR-Q8).
  The client's entry notice (F487, "You command no soldiers - spectator mode"
  at T0-12) and the host's selectedId on the hostile side (ST7, -1 at T0-12)
  are printed in the EVIDENCE line only (PR-Q9 / Q9 (b)).

Common asserts (spec (f), after each leg settles): hash_now {full:true} - every
bucket EQUAL; desyncSeen false on both; client coopClientBStatePushes unchanged
and host 0; the W2-P2 delta must-be-0 counters on both. For an admitted order:
host closedContexts gains exactly one {origin intent, kind K, actorId A}; every
host ev of that actionId is in the client's log with the same seq, kind and
actionId; exactly one bt_action_end; client coopIntentsSent[K] +1; client
inFlight null at the end; client intentTimeouts unchanged.

Probes: all exist before this file (no host-side deny record exists, T0b F1136:
the client's lastDeny and the host's intentsReceived are the evidence of a
deny).

FIXTURE (TASK 0 T0-12, T0b; test_w2_client_selection.py H6a's gm2 bring-up):
set_seed SEED_ROSTER on the HOST right before its open_new_battle (the roster
pin), the client on the Alien team (gamemode 2),
repro_pvp_side_relative.drive_to_gm2_battlescape (STR_SMALL_SCOUT, set_seed 1
right before newbattle_ok), MAP_FP asserted on both, pin_ai_neutral (0 is
legal in gm2). The alien's items are read at run time by owner + slot (F1107).
Every lever pair goes to the CLIENT first (F607).

RED-THEN-GREEN (spec (d) row S-E, the orchestrator's S-E4). Commit S-E4.1 (this
file) is run ONCE and C25 must FAIL with both legs denied `turn_over`, nothing
executed and every bucket equal. Commit S-E4.2 is run ONCE and C25 must PASS.
The scenario prints ONE "EVIDENCE C25:" line with both machines' fields BEFORE
its green conditions are checked, then "PASS C25" or "FAIL C25: <message>".
Every wait is bounded; a wait that times out is recorded in the EVIDENCE line
and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when C25 passes, 2 otherwise (a bring-up
failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_client_pvp.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from repro_atom_side_begin import row_for as gm2_row_for, drive_side_change
from repro_pvp_side_relative import drive_to_gm2_battlescape
from test_rw_turn_baton import RHAND_NTH, click_nth
from test_rw_seat_pacing import tab_select, SDLK_HOME
from test_w2_delta_core import diff_buckets, short, both
from test_w2_delta_items import items_by_id, unit_view
from test_w2_host_combat import ev_tuples
from test_w2_client_shoot import (top, snap, ubrief, press, menu_rows, send_intent, await_press, collect, ctx_view,
                                  chain_of, forwarded_fails, common_fails, finish, press_view, ui_view, shot_payloads,
                                  shot_brief, RHAND_CENTRE, CURSOR_AIM, ORDER_TIMEOUT_S)
from test_w2_client_grenade import admitted_fails, cancel_client_targeting, settle

# ----- bring-up (TASK 0 T0-12: gm2 + the roster pin) -----
PORT = "48717"
SEED_ROSTER = 1                   # set_seed on the HOST right before its open_new_battle
MAP_FP = -4.48310638993e+18       # host battle_state.mapFingerprint (STR_SMALL_SCOUT, map seed 1; T0-12, every boot)
GAMEMODE_PVP = 2
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
COOP_SEAT_0, COOP_SEAT_1 = 0, 1
XCOM_IDS = [8, 9, 10, 11, 12, 13, 14]   # the seven live seat-0 soldiers (T0-12)
S_ID = 10                         # the X-COM soldier the alien shoots
A_ID = 1000000                    # the client's alien (seat 1)
A_TYPE = "STR_SECTOID_SOLDIER"
PISTOL = "STR_PLASMA_PISTOL"      # in A's right hand (ids read at run time by owner + slot, F1107)

# ----- staging (T0-12) -----
S_TILE, S_DIR = (17, 11, 0), 0    # S faces north, towards A
A_TILE, A_DIR = (17, 8, 0), 4     # A faces south, towards S (open ground)
WALK_DEST = (17, 7, 0)            # one tile behind A (T0-12's walk)
SEED_C25 = 1                      # host set_seed right before the shot click (no hunt: the outcome is not asserted)

# ----- UI -----
KEY_SNAP = 50                     # keyBattleActionItem2
PISTOL_ROWS = 4                   # THROW, AUTO, SNAP, AIMED (W2-H6 H6a on this boot)
SIDE_SETTLE_S = 3.0               # after an order: time for a side_transition the order would cause to land


# ===================== small probes =====================


def units(gc):
    return session.units_by_id(battle_state(gc))


def jt(t):
    return {"x": t[0], "y": t[1], "z": t[2]}


def upos(u):
    return (u.get("x"), u.get("y"), u.get("z")) if u else None


def right_hand(gc, uid):
    """(item id, type) of `uid`'s right-hand item on this machine, or None."""
    for i, it in sorted(items_by_id(gc).items()):
        if it.get("owner") == uid and it.get("slot") == "STR_RIGHT_HAND":
            return i, it.get("type")
    return None


def side_view(gc):
    """This machine's side, turn, selection, action actor, banner and turn mode."""
    bs = battle_state(gc)
    es = event_state(gc)
    return {"side": bs.get("side"), "turn": bs.get("turn"), "selectedId": bs.get("selectedId"),
            "actorId": bs.get("currentActionActorId"), "banner": bs.get("coopWaitText"),
            "turnMode": es.get("turnMode"), "activeSeat": es.get("coopActiveSeat"), "top": top(gc)}


def sides(host, client):
    return {"host": side_view(host), "client": side_view(client)}


def spotted(gc, uid):
    return (units(gc).get(uid) or {}).get("spottedThisTurn")


def side_transitions(rec):
    """The host's side_transition evs since the record's seq0, as seqs."""
    return [e["seq"] for e in rec["hev"] if e["kind"] == "side_transition"]


def denied(before, rec):
    """The client's lastDeny when it changed during the order, else None."""
    ld0, ld1 = before["client"]["lastDeny"], rec["client"]["lastDeny"]
    return ld1 if ld1 and ld1 != ld0 else None


def hostile_fails(after, st, what):
    """PR-Q8: the side still HOSTILE on both and no side_transition on the host
    since the order."""
    fails = []
    got = (after["host"]["side"], after["client"]["side"])
    if got != (FACTION_HOSTILE, FACTION_HOSTILE):
        fails.append(f"{what}: side host/client {got} after the order (want {FACTION_HOSTILE} on both: a client-ordered "
                     f"alien action does not end the alien side, PR-Q8)")
    if st:
        fails.append(f"{what}: host side_transition evs since the order at seqs {st} (want none, PR-Q8)")
    return fails


# ===================== staging (client first, F607) =====================


def tele_both(host, client, uid, t, d):
    return both(host, client, {"cmd": "battle_teleport_unit", "unit": uid, "x": t[0], "y": t[1], "z": t[2],
                               "dir": d}, ("to", "dir"))


def set_stat_both(host, client, uid, stat, value):
    return both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": stat,
                               "value": value}, ("tu",))


# ===================== the client's real-UI order =====================


def alien_snap(client, ev, before_click):
    """The client's REAL-UI snap for its alien A (spec (f)): TAB-selection of A,
    a leftover targeting cancelled (F503), the right-hand box (ActionMenuState),
    key 50 (the menu closes and targeting starts), HOME, one self-verified left
    click on S's tile. `before_click` runs right before the click (the host's
    set_seed). Fills `ev`."""
    ev["tab"] = tab_select(client, A_ID)
    assert ev["tab"], f"TAB never selected A on the client (selectedId {battle_state(client).get('selectedId')})"
    ev["targetingCancel"] = cancel_client_targeting(client)
    r = click_nth(client, RHAND_NTH)
    ev["handClick"] = (r.get("baseX"), r.get("baseY"))
    assert ev["handClick"] == RHAND_CENTRE, f"right-hand click landed off the box: {r}"
    client.wait_for("client ActionMenuState on top", lambda: top(client) == "ActionMenuState" or None, timeout=5)
    ev["rows"] = menu_rows(client)
    ev["actorInMenu"] = battle_state(client).get("currentActionActorId")
    press(client, KEY_SNAP)
    client.wait_for("client BattlescapeState on top after the SNAP key",
                    lambda: top(client) == "BattlescapeState" or None, timeout=5)
    ev["cursorAfterKey"] = battle_state(client).get("cursorType")
    assert ev["cursorAfterKey"] == CURSOR_AIM, (
        f"key {KEY_SNAP} did not start targeting on the client (cursorType {ev['cursorAfterKey']}, want {CURSOR_AIM})")
    press(client, SDLK_HOME)
    time.sleep(0.15)
    pr = client.cmd({"cmd": "map_tile_click_pos", "x": S_TILE[0], "y": S_TILE[1], "z": S_TILE[2]})
    ev["clickPos"] = {k: pr.get(k) for k in ("verified", "winX", "winY", "centered")}
    assert pr.get("verified"), f"precondition: map_tile_click_pos did not verify {S_TILE} on the client: {pr}"
    before_click()
    client.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})


# ===================== the scenario =====================


def stage_and_cross(host, client, ctx, notes):
    """T0-12's staging on the player side, then the host's END TURN to the
    hostile side. Returns the evidence."""
    ev = {}
    try:
        ev["S"] = tele_both(host, client, S_ID, S_TILE, S_DIR).get("to")
        ev["A"] = tele_both(host, client, A_ID, A_TILE, A_DIR).get("to")
        ev["stagedDiff"] = diff_buckets(host, client)
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        drive_side_change(host, client, FACTION_HOSTILE, timeout=60)
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"precondition: the staging or the hostile side failed: {short(e, 600)}")
    ev["sides"] = sides(host, client)
    ev["spotted"] = {"host": spotted(host, A_ID), "client": spotted(client, A_ID)}
    ev["alien"] = {"host": ubrief(units(host).get(A_ID)), "client": ubrief(units(client).get(A_ID))}
    ev["soldier"] = {"host": ubrief(units(host).get(S_ID)), "client": ubrief(units(client).get(S_ID))}
    return ev


def stage_fails(ev):
    fails = []
    if ev.get("stagedDiff"):
        fails.append(f"buckets differ after the staging: {ev['stagedDiff']} (want none)")
    sv = ev["sides"]
    if (sv["host"]["side"], sv["client"]["side"]) != (FACTION_HOSTILE, FACTION_HOSTILE):
        fails.append(f"precondition: side host/client {sv['host']['side']}/{sv['client']['side']} after END TURN "
                     f"(want {FACTION_HOSTILE} on both)")
    for n in ("host", "client"):
        a = ev["alien"][n] or {}
        if (a.get("faction"), a.get("isOut"), upos(a), a.get("direction")) != (FACTION_HOSTILE, False, A_TILE, A_DIR):
            fails.append(f"precondition: {n} alien {a} (want live FACTION_HOSTILE on {A_TILE} facing {A_DIR})")
        if S_ID not in (ev["spotted"][n] or []):
            fails.append(f"precondition: {n} alien spottedThisTurn {ev['spotted'][n]} (want {S_ID} in view)")
    return fails


def leg_walk(host, client, notes):
    """Leg W: the client's battle_intent walk for A to WALK_DEST."""
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    req = {"cmd": "battle_intent", "kind": "walk", "actor": A_ID, "dest": jt(WALK_DEST)}
    si = send_intent(host, client, req, notes, timeout=ORDER_TIMEOUT_S)
    settle(host, client, notes)
    time.sleep(SIDE_SETTLE_S)
    settle(host, client, notes)
    rec = collect(host, client, seq0)
    after = sides(host, client)
    common = common_fails(host, client, before, "C25 leg W")
    return {"before": before, "rec": rec, "req": req, "intent": {k: si.get(k) for k in ("sent", "iseq", "answer")},
            "resp": {k: (si.get("resp") or {}).get(k) for k in ("ok", "iseq", "error")}, "after": after,
            "st": side_transitions(rec), "common": common}


def leg_shot(host, client, notes):
    """Leg S: the client's real-UI snap of A at S."""
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv = {}
    out = {}
    try:
        alien_snap(client, pv, lambda: host.ok({"cmd": "set_seed", "seed": SEED_C25}))
        out = await_press(host, client, before, notes)
    except Exception as e:
        notes.append(f"real-UI snap: {short(e, 600)}")
    settle(host, client, notes)
    time.sleep(SIDE_SETTLE_S)
    settle(host, client, notes)
    rec = collect(host, client, seq0)
    after = sides(host, client)
    common = common_fails(host, client, before, "C25 leg S")
    return {"before": before, "rec": rec, "press": pv, "outcome": out, "after": after, "st": side_transitions(rec),
            "common": common}


def c25_pvp(host, client, ctx):
    notes = []
    stage = stage_and_cross(host, client, ctx, notes)
    fails = list(notes) + stage_fails(stage)
    if fails:
        print(f"EVIDENCE C25: entry={ctx['entry']} stage={stage} notes={notes}", flush=True)
        finish(fails)
    # ---- leg W: the negative control ----
    notes_w = []
    w = leg_walk(host, client, notes_w)
    rw = w["rec"]
    new_w = ctx_view(w["before"], rw)
    # ---- leg S: the real-UI snap ----
    notes_s = []
    s = leg_shot(host, client, notes_s)
    rs = s["rec"]
    new_s = ctx_view(s["before"], rs)
    hits = [c for c in new_s if c.get("origin") == "intent" and c.get("kind") == "shoot" and c.get("actorId") == A_ID]
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rs, aid)
    shots = shot_brief(shot_payloads(host, chain)) if chain else []
    print(f"EVIDENCE C25: entry={ctx['entry']} stage={stage} | "
          f"LEG W request={w['req']} resp={w['resp']} intent={w['intent']} lastDeny={rw['client']['lastDeny']} "
          f"banner={(w['before']['clientUi']['banner'], rw['clientUi']['banner'])}; {press_view(w['before'], rw)}; "
          f"newContexts={new_w}; host evs={ev_tuples(rw['hev'])} client evs={ev_tuples(rw['cev'])}; "
          f"alien host={ubrief(rw['uh'].get(A_ID))} client={ubrief(rw['uc'].get(A_ID))}; after={w['after']} "
          f"sideTransitions={w['st']}; diff={rw['diff']} desync={rw['dsc']}; notes={notes_w} | "
          f"LEG S press={s['press']} outcome={s['outcome']}; {press_view(s['before'], rs)}; "
          f"ui={ui_view(s['before'], rs)}; newContexts={new_s}; action={aid} "
          f"chain={[(e['seq'], e['kind']) for e in chain]} shots={shots}; host evs={ev_tuples(rs['hev'])} "
          f"client evs={ev_tuples(rs['cev'])}; alien host={ubrief(rs['uh'].get(A_ID))} "
          f"client={ubrief(rs['uc'].get(A_ID))}; soldier host={ubrief(rs['uh'].get(S_ID))} "
          f"client={ubrief(rs['uc'].get(S_ID))}; after={s['after']} sideTransitions={s['st']}; diff={rs['diff']} "
          f"desync={rs['dsc']}; notes={notes_s}", flush=True)
    fails = []
    # leg W: admitted, A on WALK_DEST on both, the side still hostile (N26, PR-Q8)
    fails += [f"leg W: {m}" for m in notes_w]
    if not w["intent"]["sent"]:
        fails.append(f"leg W: battle_intent walk answered {w['resp']} (want sent: an iseq)")
    dw = denied(w["before"], rw)
    if dw:
        fails.append(f"leg W: the host denied the walk: client lastDeny {dw} (want admitted: the side is the intent "
                     f"seat's, Q8)")
    f, _ = admitted_fails(w["before"], rw, "walk", "walk", A_ID)
    fails += [f"leg W: {m}" for m in f]
    ah, ac = rw["uh"].get(A_ID), rw["uc"].get(A_ID)
    if upos(ah) != WALK_DEST or upos(ac) != WALK_DEST:
        fails.append(f"leg W: alien on host={upos(ah)} client={upos(ac)} (want {WALK_DEST} on both)")
    fails += hostile_fails(w["after"], w["st"], "leg W")
    fails += [f"leg W: {m}" for m in w["common"]]
    # leg S: the real-UI snap admitted and executed, the side still hostile (Q8, PR-Q8)
    fails += [f"leg S: {m}" for m in notes_s]
    pv = s["press"]
    if pv.get("rows") != PISTOL_ROWS:
        fails.append(f"leg S: precondition: client menu rows {pv.get('rows')} (want {PISTOL_ROWS})")
    fails += [f"leg S: {m}" for m in forwarded_fails(s["before"], rs)]
    ds = denied(s["before"], rs)
    if ds:
        fails.append(f"leg S: the host denied the shot: client lastDeny {ds} (want admitted: the side is the intent "
                     f"seat's, Q8)")
    f, _ = admitted_fails(s["before"], rs, "shoot", "shoot", A_ID)
    fails += [f"leg S: {m}" for m in f]
    sh, sc = unit_view(rs["uh"].get(S_ID)), unit_view(rs["uc"].get(S_ID))
    if sh is None or sh != sc:
        fails.append(f"leg S: soldier {S_ID} host={sh} client={sc} (want equal on both)")
    fails += hostile_fails(s["after"], s["st"], "leg S")
    fails += [f"leg S: {m}" for m in s["common"]]
    finish(fails)


SCENARIOS = (("C25", c25_pvp),)


# ===================== bring-up =====================


def boot(host, client):
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    host.ok({"cmd": "set_seed", "seed": SEED_ROSTER})
    raw.skirmish_host(host, PORT)
    raw.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": PORT, "player": raw.CLIENT_PLAYER})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: raw.lobby(host).get("buttonVisible") or None)
    r = host.ok({"cmd": "lobby_set_team", "row": gm2_row_for(host, raw.CLIENT_PLAYER), "team": "Alien"})
    assert r.get("gamemode") == GAMEMODE_PVP, (
        f"lobby_set_team Alien answered gamemode {r.get('gamemode')} (want {GAMEMODE_PVP})")
    time.sleep(1)   # the change_team broadcast settles on the client (repro_pvp_side_relative PHASE 0)
    drive_to_gm2_battlescape(host, client)
    hs, cs = battle_state(host), battle_state(client)
    # F487 (PR-Q9): the client's entry notice, read before anything is pressed; printed only
    entry = {"client": {"banner": cs.get("coopWaitText"), "selectedId": cs.get("selectedId")},
             "host": {"banner": hs.get("coopWaitText"), "selectedId": hs.get("selectedId")}}
    assert hs.get("coopGamemode") == GAMEMODE_PVP and cs.get("coopGamemode") == GAMEMODE_PVP, (
        f"coopGamemode host={hs.get('coopGamemode')} client={cs.get('coopGamemode')} (want {GAMEMODE_PVP} on both)")
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} (STR_SMALL_SCOUT, map seed 1)")
    pinned = pin_ai_neutral(host, client, tag="w2p4-se4")
    xcom = sorted(u["id"] for u in hs["units"] if u.get("faction") == FACTION_PLAYER
                  and u.get("coop") == COOP_SEAT_0 and not u.get("isOut"))
    assert xcom == XCOM_IDS, f"live seat-0 soldiers {xcom} (baked {XCOM_IDS})"
    for uid in xcom:   # N30 = F1097: pin_ai_neutral skips seat-0 soldiers
        set_stat_both(host, client, uid, "reactions", 0)
    react = {uid: ((units(host).get(uid) or {}).get("reactions"), (units(client).get(uid) or {}).get("reactions"))
             for uid in xcom}
    assert all(v == (0, 0) for v in react.values()), f"X-COM reactions host/client {react} (want 0 on both)"
    ub = session.units_by_id(hs)
    a = ub.get(A_ID) or {}
    assert (a.get("type"), a.get("faction"), a.get("coop"), a.get("isOut")) == (A_TYPE, FACTION_HOSTILE,
                                                                                  COOP_SEAT_1, False), (
        f"alien {A_ID} at bring-up: {ubrief(a)} type {a.get('type')} (want a live {A_TYPE}, FACTION_HOSTILE, seat 1)")
    rh = {gc.name: right_hand(gc, A_ID) for gc in (host, client)}
    assert rh["host"] == rh["client"] and rh["host"] and rh["host"][1] == PISTOL, (
        f"alien {A_ID} right hand host={rh['host']} client={rh['client']} (want the same {PISTOL} on both)")
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("coopIntentsSent"), dict) and isinstance(es.get("intentsReceived"), dict)
                and "lastDeny" in es), (
            f"{gc.name} event_state lacks the W2-P4 probes: coopIntentsSent={es.get('coopIntentsSent')!r} "
            f"intentsReceived={es.get('intentsReceived')!r}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="gm2 bring-up")
    print(f"[w2p4-se4] boot ok: gm2 STR_SMALL_SCOUT MAP_FP={MAP_FP!r} turn={hs.get('turn')} pinned={len(pinned)} "
          f"xcom reactions 0={xcom} alien={ubrief(a)} rightHand={rh['host']} entry={entry} "
          f"sides={sides(host, client)}", flush=True)
    return {"entry": entry}


def main():
    t0 = time.time()
    host = GameClient("host", 49884, make_user_dir("w2p4_client_pvp_host"))
    client = GameClient("client", 49885, make_user_dir("w2p4_client_pvp_client"))
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
                print(f"[w2p4-se4] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_client_pvp: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
