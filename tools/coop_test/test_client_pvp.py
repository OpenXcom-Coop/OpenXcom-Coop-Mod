"""test_client_pvp.py: in a PvP battle (gm2, the second player on the Alien
team) the second player orders its own alien on its own (hostile) side, and
the host checks and runs the order. A gm2 client-ordered alien action does
not end the alien side, so the scenario asserts the side stays HOSTILE and no
side_transition follows the order. The gm2 hostile-side turn / kneel / walk
intents are admitted too. pin_ai_neutral skips the seat-0 soldiers, so every
X-COM soldier's reactions are set to 0 on both machines. The client's
right-hand box on the hostile side reaches the order intercept.

The host's onIntent turn check compares the side with the INTENT seat's
faction (factionOf(seat)). A check against the HOST's own seat faction
(mySideActive, seat 0 -> FACTION_PLAYER) would deny every order the second
player gives on its own side `turn_over`, since a gm2 seat 1 commands
FACTION_HOSTILE. The host's popState does not end the alien side after an
action a human seat ordered.

ONE boot, one scenario with two legs, in this order:

  pvp_alien_orders  staging on the player side (both machines, client
       first): X-COM reactions 0 for every live seat-0 soldier, soldier S ->
       S_TILE facing S_DIR, the client's alien A -> A_TILE facing A_DIR (open
       ground, S three tiles south of A). The host presses END TURN; both
       machines reach the hostile side (the client's). S is in A's
       spottedThisTurn on both.
    walk leg  the command-level control: a client `battle_intent walk` for A
       to WALK_DEST (one tile behind A). Host closedContexts gains exactly one
       {origin intent, kind walk, actorId A}; A on WALK_DEST on both; the side
       still HOSTILE on both and no side_transition since the order. With the
       host-seat check, the host denies it `turn_over` (client lastDeny; the
       banner "The turn has already ended") and nothing runs.
    shot leg  the client's alien snaps at S through its REAL UI: TAB-selection
       of A, the right-hand box (the plasma pistol's menu, PISTOL_ROWS rows),
       key 50 (SNAP), HOME, host set_seed SEED_SHOT (determinism only: the
       shot's outcome is not asserted), one self-verified left click on S's
       tile. Host closedContexts gains exactly one {origin intent, kind shoot,
       actorId A}; S's state equal on both; the side still HOSTILE on both; no
       side_transition on the host since the press (so none after the shot's
       bt_action_end). With the host-seat check, the order is sent, the host
       denies it `turn_over` and nothing runs.
  The client's entry notice (measured: "You command no soldiers - spectator
  mode") and the host's selectedId on the hostile side (measured: -1) are
  printed in the EVIDENCE line only.
  entry_notice_cleared: once the client's own side has begun and its seat
  commands a selected unit (A), the entry notice is gone - after the staging
  and the crossing the client's coopWaitText == "". Without that clear, only
  this row fails (the client still shows TEXT_SPECTATOR: a Notice is never
  dwell-cleared); the walk and shot legs pass.
  host_camera_follows: in PvP every order the second player gives is the
  OPPONENT's, so the watching host's camera follows its visible actions as
  vanilla follows an enemy turn.
  host_camera_walk (walk leg): the host camera.suppressed delta over the walk
  is all +0.
  host_camera_shot (shot leg): A goes back on A_TILE facing A_DIR first (the
  snap then needs no turn, so no popState lands while the projectile flies
  and ProjectileFlyBState::cancel never skips it and centres the host on the
  impact), then the host camera is staged on HOST_FAR_TILE (view level 1)
  before the press; after the shot the host's suppressed delta is all +0, its
  view level 0 and its offset moved off the staged one.
  A build that suppresses the host camera for every `intent` base shows
  host_camera_walk walkLevel +8 exactly, host_camera_shot follow +1 exactly,
  every other counter +0, the offset still the staged one, view level 1. The
  client's camera is printed only. One "EVIDENCE host_camera_follows:" line.

Common asserts (after each leg settles): hash_now {full:true} - every bucket
EQUAL; desyncSeen false on both; client coopClientBStatePushes unchanged and
host 0; the delta must-be-0 counters on both. For an admitted order: host
closedContexts gains exactly one {origin intent, kind K, actorId A}; every
host ev of that actionId is in the client's log with the same seq, kind and
actionId; exactly one bt_action_end; client coopIntentsSent[K] +1; client
inFlight null at the end; client intentTimeouts unchanged.

Probes: no host-side deny record exists; the client's lastDeny and the host's
intentsReceived are the evidence of a deny.

FIXTURE (the gm2 bring-up of test_client_selection.py): set_seed SEED_ROSTER
on the HOST right before its open_new_battle (the roster pin), the client on
the Alien team (gamemode 2), repro_pvp_side_relative.drive_to_gm2_battlescape
(STR_SMALL_SCOUT, set_seed 1 right before newbattle_ok), MAP_FP asserted on
both, pin_ai_neutral (0 is legal in gm2). The alien's items are read at run
time by owner + slot. Every paired test command goes to the CLIENT first.

With the host-seat check, the scenario fails with both legs denied
`turn_over`, nothing run and every bucket equal. The scenario prints ONE
"EVIDENCE pvp_alien_orders:" line with both machines' fields BEFORE its
conditions are checked, then "PASS pvp_alien_orders" or "FAIL
pvp_alien_orders: <message>". Every wait is bounded; a wait that times out is
recorded in the EVIDENCE line and fails the scenario.

No skip path, no second boot, no alternative map or actor. Exit 0 only when
pvp_alien_orders passes, 2 otherwise (a bring-up failure is also 2).

Run:  python tools/coop_test/test_client_pvp.py
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
from test_turn_baton import RHAND_NTH, click_nth
from test_seat_pacing import tab_select, SDLK_HOME
from test_delta_core import diff_buckets, short, both
from test_delta_items import items_by_id, unit_view
from test_host_combat import ev_tuples
from test_host_combat import camera_of, cam_snap, cam_offset, stage_camera, cam_suppressed_delta, cam_view
from test_client_shoot import (top, snap, ubrief, press, menu_rows, send_intent, await_press, collect, ctx_view,
                                  chain_of, forwarded_fails, common_fails, finish, press_view, ui_view, shot_payloads,
                                  shot_brief, RHAND_CENTRE, CURSOR_AIM, ORDER_TIMEOUT_S)
from test_client_grenade import admitted_fails, cancel_client_targeting, settle

# ----- bring-up (gm2 + the roster pin) -----
PORT = "48717"
SEED_ROSTER = 1                   # set_seed on the HOST right before its open_new_battle
MAP_FP = -4.48310638993e+18       # host battle_state.mapFingerprint (STR_SMALL_SCOUT, map seed 1; the same every boot)
GAMEMODE_PVP = 2
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
COOP_SEAT_0, COOP_SEAT_1 = 0, 1
XCOM_IDS = [8, 9, 10, 11, 12, 13, 14]   # the seven live seat-0 soldiers
S_ID = 10                         # the X-COM soldier the alien shoots
A_ID = 1000000                    # the client's alien (seat 1)
A_TYPE = "STR_SECTOID_SOLDIER"
PISTOL = "STR_PLASMA_PISTOL"      # in A's right hand (ids read at run time by owner + slot)

# ----- staging -----
S_TILE, S_DIR = (17, 11, 0), 0    # S faces north, towards A
A_TILE, A_DIR = (17, 8, 0), 4     # A faces south, towards S (open ground)
WALK_DEST = (17, 7, 0)            # one tile behind A
SEED_SHOT = 1                     # host set_seed right before the shot click (any seed: the outcome is not asserted)
# host_camera_shot: test_reaction_prox's measured host far tile on the same 40x40x4 map (MAP_FP)
HOST_FAR_TILE = (38, 38, 1)       # the host camera at view level 1, > 1 screen from A (17,8) and S (17,11)
SUPPRESSED_WALKLEVEL = 8          # host_camera_walk with the host camera suppressed: the host centres on the walker
                                  # (UnitWalkBState :203), which puts A on screen, so its one step runs all 8 walk
                                  # phases and :205 writes (suppressed) once per phase; 2 per step holds only for an
                                  # off-screen walker

# ----- UI -----
KEY_SNAP = 50                     # keyBattleActionItem2
PISTOL_ROWS = 4                   # THROW, AUTO, SNAP, AIMED (measured on this boot)
SIDE_SETTLE_S = 3.0               # after an order: time for a side_transition the order would cause to land
TEXT_SPECTATOR = "You command no soldiers - spectator mode"   # STR_COOP_SPECTATOR_MODE (en-US): a stale entry notice


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
    """The side still HOSTILE on both and no side_transition on the host since
    the order (a client-ordered alien action does not end the alien side)."""
    fails = []
    got = (after["host"]["side"], after["client"]["side"])
    if got != (FACTION_HOSTILE, FACTION_HOSTILE):
        fails.append(f"{what}: side host/client {got} after the order (want {FACTION_HOSTILE} on both: a client-ordered "
                     f"alien action does not end the alien side)")
    if st:
        fails.append(f"{what}: host side_transition evs since the order at seqs {st} (want none)")
    return fails


# ===================== staging (client first) =====================


def tele_both(host, client, uid, t, d):
    return both(host, client, {"cmd": "battle_teleport_unit", "unit": uid, "x": t[0], "y": t[1], "z": t[2],
                               "dir": d}, ("to", "dir"))


def set_stat_both(host, client, uid, stat, value):
    return both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": stat,
                               "value": value}, ("tu",))


# ===================== the client's real-UI order =====================


def alien_snap(client, ev, before_click):
    """The client's REAL-UI snap for its alien A: TAB-selection of A,
    a leftover targeting cancelled, the right-hand box (ActionMenuState),
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
    """The staging on the player side, then the host's END TURN to the
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
    """The walk leg: the client's battle_intent walk for A to WALK_DEST."""
    cw0 = cam_snap(host, client)   # host_camera_walk: both cameras before the opponent's walk
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    req = {"cmd": "battle_intent", "kind": "walk", "actor": A_ID, "dest": jt(WALK_DEST)}
    si = send_intent(host, client, req, notes, timeout=ORDER_TIMEOUT_S)
    settle(host, client, notes)
    time.sleep(SIDE_SETTLE_S)
    settle(host, client, notes)
    cw1 = cam_snap(host, client)   # host_camera_walk: after the walk
    rec = collect(host, client, seq0)
    after = sides(host, client)
    common = common_fails(host, client, before, "pvp_alien_orders walk leg")
    return {"before": before, "rec": rec, "req": req, "intent": {k: si.get(k) for k in ("sent", "iseq", "answer")},
            "resp": {k: (si.get("resp") or {}).get(k) for k in ("ok", "iseq", "error")}, "after": after,
            "st": side_transitions(rec), "common": common, "cam0": cw0, "cam1": cw1}


def leg_shot(host, client, notes):
    """The shot leg: the client's real-UI snap of A at S."""
    # host_camera_shot: A back on A_TILE facing S (both machines, client first; only when
    # the walk leg moved it, never onto its own tile), so the snap needs no turn
    a = units(host).get(A_ID) or {}
    reface = (tele_both(host, client, A_ID, A_TILE, A_DIR) if upos(a) != A_TILE
              else {"skipped": upos(a), "dir": a.get("direction")})
    staged = stage_camera(host, HOST_FAR_TILE)   # host_camera_shot: the host camera far, view level 1
    cs0 = cam_snap(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv = {}
    out = {}
    try:
        alien_snap(client, pv, lambda: host.ok({"cmd": "set_seed", "seed": SEED_SHOT}))
        out = await_press(host, client, before, notes)
    except Exception as e:
        notes.append(f"real-UI snap: {short(e, 600)}")
    settle(host, client, notes)
    time.sleep(SIDE_SETTLE_S)
    settle(host, client, notes)
    cs1 = cam_snap(host, client)   # host_camera_shot: after the shot
    rec = collect(host, client, seq0)
    after = sides(host, client)
    common = common_fails(host, client, before, "pvp_alien_orders shot leg")
    return {"before": before, "rec": rec, "press": pv, "outcome": out, "after": after, "st": side_transitions(rec),
            "common": common, "staged": staged, "cam0": cs0, "cam1": cs1,
            "reface": {k: reface.get(k) for k in ("to", "dir", "skipped")}}


def host_camera_fails(w, s, shots):
    """Row host_camera_follows: in PvP the second player's orders are the OPPONENT's, so the watching host's camera
    follows them as vanilla follows an enemy turn. host_camera_walk (the walk leg, the opponent's walk): host
    camera.suppressed delta all +0. host_camera_shot (the shot leg, the opponent's snap, the host staged on
    HOST_FAR_TILE): suppressed delta all +0, view level 0, the offset moved off the staged one. The client's camera
    is printed only. Prints one "EVIDENCE host_camera_follows:" line."""
    supw = cam_suppressed_delta(w["cam0"]["host"], w["cam1"]["host"])
    sups = cam_suppressed_delta(s["cam0"]["host"], s["cam1"]["host"])
    hs1 = s["cam1"]["host"]
    lw, ls = w["before"]["host"]["lastSeqEmitted"] or 0, s["before"]["host"]["lastSeqEmitted"] or 0
    print(f"EVIDENCE host_camera_follows: shot leg reface={s['reface']}; host staged={cam_offset(s['staged'])} "
          f"(tile {HOST_FAR_TILE}); "
          f"host_camera_walk host before={cam_view(w['cam0']['host'])} after={cam_view(w['cam1']['host'])} "
          f"suppressed delta={supw}; host_camera_shot host before={cam_view(s['cam0']['host'])} after={cam_view(hs1)} "
          f"suppressed delta={sups}; client (not asserted) walk leg before={cam_view(w['cam0']['client'], lw)} "
          f"after={cam_view(w['cam1']['client'], lw)} shot leg before={cam_view(s['cam0']['client'], ls)} "
          f"after={cam_view(s['cam1']['client'], ls)}; shot leg shots={shots}", flush=True)
    fails = []
    if any(supw.values()):
        fails.append(f"host_camera_walk: host camera.suppressed delta {supw} over the opponent's walk (want all +0: "
                     f"in PvP the opponent's walk moves the watching host's view level as vanilla does; a suppressed "
                     f"host camera shows walkLevel +{SUPPRESSED_WALKLEVEL})")
    if any(sups.values()):
        fails.append(f"host_camera_shot: host camera.suppressed delta {sups} over the opponent's shot (want all +0: "
                     f"the opponent's shot follows on the watching host)")
    if hs1.get("viewLevel") != 0:
        fails.append(f"host_camera_shot: host camera viewLevel {hs1.get('viewLevel')} after the shot (want 0, the "
                     f"shot's level: the opponent's shot follows on the watching host)")
    if cam_offset(hs1) == cam_offset(s["staged"]):
        fails.append(f"host_camera_shot: host camera offset {cam_offset(hs1)} after the shot is still the staged one "
                     f"(want moved: the opponent's shot follows on the watching host)")
    return fails


def pvp_alien_orders(host, client, ctx):
    notes = []
    stage = stage_and_cross(host, client, ctx, notes)
    fails = list(notes) + stage_fails(stage)
    if fails:
        print(f"EVIDENCE pvp_alien_orders: entry={ctx['entry']} stage={stage} notes={notes}", flush=True)
        finish(fails)
    # entry_notice_cleared: the client's banner on its own side, read before the walk leg's order
    entry_banner = stage["sides"]["client"]["banner"]
    # ---- walk leg: the command-level control ----
    notes_w = []
    w = leg_walk(host, client, notes_w)
    rw = w["rec"]
    new_w = ctx_view(w["before"], rw)
    # ---- shot leg: the real-UI snap ----
    notes_s = []
    s = leg_shot(host, client, notes_s)
    rs = s["rec"]
    new_s = ctx_view(s["before"], rs)
    hits = [c for c in new_s if c.get("origin") == "intent" and c.get("kind") == "shoot" and c.get("actorId") == A_ID]
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rs, aid)
    shots = shot_brief(shot_payloads(host, chain)) if chain else []
    print(f"EVIDENCE pvp_alien_orders: entry={ctx['entry']} stage={stage} "
          f"entry_notice_cleared client banner after the crossing={entry_banner!r} | "
          f"WALK LEG request={w['req']} resp={w['resp']} intent={w['intent']} lastDeny={rw['client']['lastDeny']} "
          f"banner={(w['before']['clientUi']['banner'], rw['clientUi']['banner'])}; {press_view(w['before'], rw)}; "
          f"newContexts={new_w}; host evs={ev_tuples(rw['hev'])} client evs={ev_tuples(rw['cev'])}; "
          f"alien host={ubrief(rw['uh'].get(A_ID))} client={ubrief(rw['uc'].get(A_ID))}; after={w['after']} "
          f"sideTransitions={w['st']}; diff={rw['diff']} desync={rw['dsc']}; notes={notes_w} | "
          f"SHOT LEG press={s['press']} outcome={s['outcome']}; {press_view(s['before'], rs)}; "
          f"ui={ui_view(s['before'], rs)}; newContexts={new_s}; action={aid} "
          f"chain={[(e['seq'], e['kind']) for e in chain]} shots={shots}; host evs={ev_tuples(rs['hev'])} "
          f"client evs={ev_tuples(rs['cev'])}; alien host={ubrief(rs['uh'].get(A_ID))} "
          f"client={ubrief(rs['uc'].get(A_ID))}; soldier host={ubrief(rs['uh'].get(S_ID))} "
          f"client={ubrief(rs['uc'].get(S_ID))}; after={s['after']} sideTransitions={s['st']}; diff={rs['diff']} "
          f"desync={rs['dsc']}; notes={notes_s}", flush=True)
    camera_fails = host_camera_fails(w, s, shots)
    fails = []
    # entry_notice_cleared: no stale entry notice once the seat commands a selected unit
    if entry_banner != "":
        fails.append(f"entry_notice_cleared: the client's coopWaitText {entry_banner!r} on its own side with A "
                     f"selected (want '': the spectator entry notice clears at the seat's first own-side side_begin)")
    # walk leg: admitted, A on WALK_DEST on both, the side still hostile
    fails += [f"walk leg: {m}" for m in notes_w]
    if not w["intent"]["sent"]:
        fails.append(f"walk leg: battle_intent walk answered {w['resp']} (want sent: an iseq)")
    dw = denied(w["before"], rw)
    if dw:
        fails.append(f"walk leg: the host denied the walk: client lastDeny {dw} (want admitted: the side is the intent "
                     f"seat's)")
    f, _ = admitted_fails(w["before"], rw, "walk", "walk", A_ID)
    fails += [f"walk leg: {m}" for m in f]
    ah, ac = rw["uh"].get(A_ID), rw["uc"].get(A_ID)
    if upos(ah) != WALK_DEST or upos(ac) != WALK_DEST:
        fails.append(f"walk leg: alien on host={upos(ah)} client={upos(ac)} (want {WALK_DEST} on both)")
    fails += hostile_fails(w["after"], w["st"], "walk leg")
    fails += [f"walk leg: {m}" for m in w["common"]]
    # shot leg: the real-UI snap admitted and executed, the side still hostile
    fails += [f"shot leg: {m}" for m in notes_s]
    pv = s["press"]
    if pv.get("rows") != PISTOL_ROWS:
        fails.append(f"shot leg: precondition: client menu rows {pv.get('rows')} (want {PISTOL_ROWS})")
    fails += [f"shot leg: {m}" for m in forwarded_fails(s["before"], rs)]
    ds = denied(s["before"], rs)
    if ds:
        fails.append(f"shot leg: the host denied the shot: client lastDeny {ds} (want admitted: the side is the intent "
                     f"seat's)")
    f, _ = admitted_fails(s["before"], rs, "shoot", "shoot", A_ID)
    fails += [f"shot leg: {m}" for m in f]
    sh, sc = unit_view(rs["uh"].get(S_ID)), unit_view(rs["uc"].get(S_ID))
    if sh is None or sh != sc:
        fails.append(f"shot leg: soldier {S_ID} host={sh} client={sc} (want equal on both)")
    fails += hostile_fails(s["after"], s["st"], "shot leg")
    fails += [f"shot leg: {m}" for m in s["common"]]
    fails += camera_fails
    finish(fails)


SCENARIOS = (("pvp_alien_orders", pvp_alien_orders),)


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
    time.sleep(1)   # the change_team broadcast settles on the client (repro_pvp_side_relative's boot phase)
    drive_to_gm2_battlescape(host, client)
    hs, cs = battle_state(host), battle_state(client)
    # the client's entry notice, read before anything is pressed; printed only
    entry = {"client": {"banner": cs.get("coopWaitText"), "selectedId": cs.get("selectedId")},
             "host": {"banner": hs.get("coopWaitText"), "selectedId": hs.get("selectedId")}}
    assert hs.get("coopGamemode") == GAMEMODE_PVP and cs.get("coopGamemode") == GAMEMODE_PVP, (
        f"coopGamemode host={hs.get('coopGamemode')} client={cs.get('coopGamemode')} (want {GAMEMODE_PVP} on both)")
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} (STR_SMALL_SCOUT, map seed 1)")
    pinned = pin_ai_neutral(host, client, tag="client_pvp")
    xcom = sorted(u["id"] for u in hs["units"] if u.get("faction") == FACTION_PLAYER
                  and u.get("coop") == COOP_SEAT_0 and not u.get("isOut"))
    assert xcom == XCOM_IDS, f"live seat-0 soldiers {xcom} (baked {XCOM_IDS})"
    for uid in xcom:   # pin_ai_neutral skips seat-0 soldiers
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
            f"{gc.name} event_state lacks the intent probes: coopIntentsSent={es.get('coopIntentsSent')!r} "
            f"intentsReceived={es.get('intentsReceived')!r}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="gm2 bring-up")
    print(f"[client_pvp] boot ok: gm2 STR_SMALL_SCOUT MAP_FP={MAP_FP!r} turn={hs.get('turn')} pinned={len(pinned)} "
          f"xcom reactions 0={xcom} alien={ubrief(a)} rightHand={rh['host']} entry={entry} "
          f"sides={sides(host, client)}", flush=True)
    return {"entry": entry}


def main():
    t0 = time.time()
    host = GameClient("host", 49884, make_user_dir("client_pvp_host"))
    client = GameClient("client", 49885, make_user_dir("client_pvp_client"))
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
                print(f"[client_pvp] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_client_pvp: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
