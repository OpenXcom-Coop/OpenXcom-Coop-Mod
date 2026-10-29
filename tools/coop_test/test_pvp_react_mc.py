"""R5-U3 S-B rows R2, M2, R1, M1 (boot B2, gm2: the client plays the aliens, seat 1; the host the seven X-COM soldiers,
seat 0): reaction fire and mind control both ways, the human alien side playing by the player-side rules vanilla gives
X-COM (R5-V1, QU3-4 (a); O1 (a): the alien player may mind-control only a unit its own side sees).

Spec: docs repo rewrite/prompts/r5u3_pvp_rules.md section (f) test_pvp_react_mc.py, with the orchestrator rulings
R-U3-B-2 (row order R2, M2, R1, M1: R1's reaction gives A a host AI module, F11585) and register row R5U3-O1 (O1 (a)).
Constants: rewrite/r5u3-task0/sb/CONSTANTS.md (TASK 0 boots Ba2, Bb2, Bn2 on the unchanged build; every pin equal).

Boot B2 (key 48678): BER.boot_pvp (STR_SMALL_SCOUT, map seed 1, gamemode 2), every live unit's reactions 0, the TASK 0
staging (TILES; A's plasma pistol and S3's rifle by lever), the host's END TURN -> side 1 turn 1.
  R2  X-COM reacts to the alien seat's walk: S3 reactions 100, firing 0, TU; host set_seed SEED_R2; client send_walk.
      R2-walk   one new host context W {intent, walk, A}; the client's coopIntentsSent.walk +1, inFlight null
      R2-react  one `reaction` context {actorId S3, nestedIn W}; a `shot` by S3 in it; the client has its seqs;
                lastWalk.restate halted, reason `reaction` on both
      R2-alive  A not out, health equal on both
  M2  the alien seat mind-controls X-COM soldiers (side 1 turn 1): S3 reactions 0; the amp on A; A psiSkill 100; S2,
      S4, S5 psiStrength 0; TU (both).
      M2-sees   S2 and S4 in A's spottedThisTurn on the host; S5 Chebyshev >= 21 from every hostile unit (precondition)
      M2-ui     the client's real-UI MIND CONTROL on S2 (TAB, the right-hand box, key 51, HOME, host set_seed SEED_M2,
                one click): one new host context {intent, psi, A}; psi +1; S2 faction 1, mindControllerId A on both
      M2-ctrl   S2's TU cap refilled (both); the client's battle_intent turn for S2 admitted {intent, turn, S2}; S2's
                facing changed and equal on both
      M2-lever  the client's psi lever at S4: one new host context {intent, psi, A}; S4 faction 1 on both (E10)
      M2-unseen the client's psi lever at S5 (unseen): denied invalid_target, S5 unchanged (O1 (a))
      After M2: S2 / S4 TU 0, reactions 0 (both); then both move by the hash-gated lever to
      MOVE_AWAY, out of every later walk's sight (on green they stay mind-controlled, so R1's walk would halt on
      `spot` at S's first turn step).
  R1  the alien reacts to the X-COM host's walk (side 0 turn 2): the client's END TURN; A's pistol back (lever); A
      reactions 100, firing 0, TU A_TU; host set_seed SEED_R1; the host's real-UI walk of S.
      R1-walk / R1-react / R1-alive   as R2 with W {host, walk, S} and the reaction by A; S not out
      R1-ai     hasAI false for A on the host and on the client after the reaction
  M1  X-COM mind-controls the alien and the host commands it (side 0 turn 2): the amp on S, S psiSkill 100, A
      psiStrength 0, S's TU; A in the host's battle_state.spotted.
      M1-ui     the host's real-UI MIND CONTROL on A (set_seed SEED_M1): one new host context {host, psi, S}; A faction 0,
                mindControllerId S on both
      M1-ctrl   A's TU cap refilled; the host's real-UI walk of A to M1_DEST: {host, walk, A}, A on M1_DEST on both;
                the client's battle_intent turn for A denied not_your_unit
      M1 is the last row (A is the only alien; no END TURN after it, F10911).
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane
crash folder. EVIDENCE only: host infoboxes (dismissed host-only), messages, camera, the client's warningText.
After every mind-control order the client's own message box is waited out (its battle map back on top, capped at
CLIENT_MAP_S; a cap hit fails the order's cell with the client's stack, R-U3-B-4).

RED on the unchanged build (commit B1): M2-ui, M2-ctrl, M2-lever, R1-ai; every other cell PASS. One EVIDENCE line per
row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step past its bound prints
ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails the rows that need it "staging".
run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_react_mc.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
from repro_atom_side_begin import drive_side_change  # noqa: E402
from test_delta_core import both  # noqa: E402
from test_seat_pacing import tab_select, real_click_walk, SDLK_HOME  # noqa: E402
from test_turn_baton import RHAND_NTH, click_nth  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
from test_client_shoot import new_contexts, send_intent, set_tu_both, place, jt, RHAND_CENTRE  # noqa: E402
from test_host_combat import evs_since  # noqa: E402
from test_ai_origins import host_payloads  # noqa: E402
from test_messages import poll_host_box, client_quiet  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402

KEY = "48678"
A_ID = 1000000                    # the only alien (STR_SECTOID_SOLDIER), the client's (seat 1)
S_ID, S3_ID, S2_ID, S4_ID, S5_ID = 8, 9, 10, 11, 12   # R1's walker / M1's attacker, R2's reactor, M2's targets
TILES = {   # TASK 0 staging (open ground, z 0, equal on both; S5 and 13 / 14 far from every walk tile)
    A_ID: ((15, 2, 0), 4), S3_ID: ((18, 6, 0), 7), S_ID: ((15, 9, 0), 0), S2_ID: ((12, 7, 0), 0),
    S4_ID: ((18, 8, 0), 0), S5_ID: ((36, 36, 0), 0), 13: ((33, 33, 0), 0), 14: ((34, 33, 0), 0)}
R2_DEST = (15, 4, 0)              # A 2 tiles south; SEED_R2 halts it after (15,3,0)
R1_DEST = (17, 9, 0)              # S 2 tiles east; SEED_R1 halts it after (16,9,0)
M1_DEST = (14, 3, 0)              # A one tile west of its R2 halt tile (15,3,0)
A_TU, S2_TU = 54, 58              # bring-up TUs: A's refill / TU cap after M1, S2's TU cap after M2
SEED_R2 = SEED_R1 = SEED_M2 = SEED_M1 = 1
PSI_AMP, PISTOL, CLIP = "STR_PSI_AMP", "STR_PLASMA_PISTOL", "STR_PLASMA_PISTOL_CLIP"
KEY_MC, CT_PSI, PSI_ROWS = 51, 3, 3   # MIND CONTROL key, its cursor, the amp's menu rows
CURSOR_TARGETING = (2, 3, 4, 5)
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
UNSEEN_MIN = 21                   # S5's Chebyshev distance from every hostile unit
MOVE_AWAY = {S2_ID: (4, 34, 0), S4_ID: (8, 34, 0)}   # R-U3-B-5 (TASK 0, 2 red + 2 green boots): open ground on both,
FACE_AWAY = 4                     # Chebyshev 25 from every R1 / M1 walk tile and live unit; south, away from them
STEP_S, ORDER_S = 30, 5           # step bound; the bounded wait for an order's context (ends early on green)
CLIENT_MAP_S = 5                  # the client's message box after an applied psi ev closes in 2.0 s
ROWS = (("R2", ("R2-walk", "R2-react", "R2-alive", "R2-common")),
        ("M2", ("M2-sees", "M2-ui", "M2-ctrl", "M2-lever", "M2-unseen", "M2-common")),
        ("R1", ("R1-walk", "R1-react", "R1-alive", "R1-ai", "R1-common")),
        ("M1", ("M1-ui", "M1-ctrl", "M1-common")))


# ===================== shared helpers (test_pvp_react_mc_gm3 imports them) =====================


def es(gc, key):
    return event_state(gc).get(key)


def ctxs(gc):
    return es(gc, "closedContexts") or []


def unit(gc, uid):
    return G3F.units(gc).get(uid) or {}


def uv(gc, uid):
    u = unit(gc, uid)
    return {k: u.get(k) for k in ("x", "y", "z", "direction", "faction", "mindControllerId", "tu", "health", "isOut",
                                  "status", "morale", "hasAI")}


def cv(c):
    return {k: c.get(k) for k in ("actionId", "origin", "kind", "actorId", "nestedIn")}


def wait_until(pred, timeout, interval=0.2):
    t0 = time.time()
    while True:
        if pred():
            return True, round(time.time() - t0, 2)
        if time.time() - t0 >= timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)


def settle(host, client, ev):
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]


def stat_both(host, client, uid, stat, value, refill=False):
    req = {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": stat, "value": value}
    if refill:
        req["refill"] = True
    return both(host, client, req, ("tu",))


def give_both(host, client, uid, item, ammo=None):
    req = {"cmd": "battle_give", "unit": uid, "item": item, "slot": "right", "clear_hands": True}
    if ammo:
        req["ammo"] = ammo
    return both(host, client, req, ("weaponId",) + (("ammoId",) if ammo else ()))


def side_change(host, client, presser, side, turn, ev):
    """presser's END TURN -> both on (side, turn >= turn), every NextTurnState closed, host boxes dismissed host-only."""
    ev["press"] = presser.cmd({"cmd": "battle_action", "action": "end_turn_button"}).get("ok")
    drive_side_change(host, client, side, want_turn_min=turn, timeout=STEP_S)
    rec = {"hostBoxes": []}
    wait_until(lambda: G3F.top(host) == "BattlescapeState" and G3F.top(client) == "BattlescapeState", 10, 0.1)
    for gc in (host, client):
        if G3F.top(gc) == "NextTurnState":
            gc.cmd({"cmd": "close_nextturn"})
    poll_host_box(host, rec, f"side {side}")
    session.wait_host_idle(host, client, timeout=STEP_S)
    ev["sideBoxes"] = rec["hostBoxes"]
    ev["turnSide"] = [(battle_state(gc).get("turn"), battle_state(gc).get("side")) for gc in (host, client)]
    assert ev["turnSide"] == [(turn, side)] * 2, f"(turn, side) host/client {ev['turnSide']} (want {(turn, side)})"


def stage_tiles(host, client, tiles, dests):
    """Every staging tile and destination open ground on both machines (equal floor, no object), then `place` (S2)."""
    th = G3F.guarded("staging", lambda: tile_parts(host), (host, client))
    tc = G3F.guarded("staging", lambda: tile_parts(client), (host, client))
    bad = [(t, th.get(t[:2]), tc.get(t[:2])) for t in [td[0] for td in tiles.values()] + list(dests)
           if th.get(t[:2]) != tc.get(t[:2]) or th.get(t[:2], (-1,))[0] == -1 or th.get(t[:2])[3] != -1]
    if bad:
        G3F.capture("staging", f"tiles not open ground on both: {bad}", (host, client))
        raise G3F.Miss("staging")
    return {uid: G3F.guarded("staging", lambda u=uid, td=td: place(host, client, u, td[0], td[1]), (host, client))
            for uid, td in tiles.items()}


def tile_parts(gc):
    """{(x, y): (floor, westwall, northwall, object) mapDataIDs} at z 0 over the 40x40 map (tile_census)."""
    outd = {}
    for y0 in range(0, 40, 20):
        r = gc.ok({"cmd": "tile_census", "x0": 0, "x1": 39, "y0": y0, "y1": y0 + 19, "z0": 0, "z1": 0})
        for t in r["tiles"]:
            if t:
                outd[(t["x"], t["y"])] = tuple(t["parts"][p]["mapDataID"] for p in ("floor", "westwall", "northwall",
                                                                                    "object"))
    return outd


def walk_react(row, host, client, ctx0, seq0, origin, walker, reactor, ev, sent0=None):
    """The `<row>-walk` and `<row>-react` cells of a walk that draws one reaction."""
    new = new_contexts(ctx0, ctxs(host))
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    walks = [c for c in new if (c.get("origin"), c.get("kind"), c.get("actorId")) == (origin, "walk", walker)]
    reacts = [c for c in new if c.get("kind") == "reaction" and c.get("actorId") == reactor]
    shots = [e["seq"] for e in hev if e["kind"] == "shot" and reacts and e["actionId"] == reacts[0].get("actionId")]
    pl = host_payloads(host, shots, timeout=3) if shots else {}
    cmap = {e["seq"]: (e["kind"], e["actionId"]) for e in cev}
    lacks = [e["seq"] for e in hev if cmap.get(e["seq"]) != (e["kind"], e["actionId"])]
    halts = [((es(gc, "lastWalk") or {}).get("restate") or {}) for gc in (host, client)]
    halts = [(h.get("halted"), h.get("reason")) for h in halts]
    ev.update(newCtx=[cv(c) for c in new], hostEvs=[(e["seq"], e["kind"], e["actionId"]) for e in hev], halts=halts,
              shots=[(v["payload"].get("actor"), v["payload"].get("impact")) for v in pl.values()])
    wk = []
    if len(walks) != 1:
        wk.append(f"new host contexts {[cv(c) for c in new]} (want exactly one {{{origin}, walk, {walker}}})")
    if sent0 is not None:
        d = (es(client, "coopIntentsSent") or {}).get("walk", 0) - sent0.get("walk", 0)
        if d != 1 or es(client, "inFlight") is not None:
            wk.append(f"client coopIntentsSent.walk +{d} (want +1), inFlight {es(client, 'inFlight')} (want None)")
    rc = []
    if len(reacts) != 1 or not walks or reacts[0].get("nestedIn") != walks[0].get("actionId"):
        rc.append(f"reaction contexts {[cv(c) for c in reacts]} (want exactly one by {reactor} nested in the walk)")
    if not any(v["payload"].get("actor") == reactor for v in pl.values()):
        rc.append(f"shots in the reaction context {ev['shots']} (want a shot by {reactor})")
    if lacks:
        rc.append(f"the client lacks the host's seqs {lacks}")
    if halts != [(True, "reaction")] * 2:
        rc.append(f"lastWalk restate (halted, reason) host/client {halts} (want (True, 'reaction') on both)")
    return {f"{row}-walk": (not wk, "; ".join(wk) or f"one {{{origin}, walk, {walker}}}"),
            f"{row}-react": (not rc, "; ".join(rc) or f"one reaction by {reactor} nested in the walk, a shot, halted")}


def alive_cell(host, client, uid):
    h, c = uv(host, uid), uv(client, uid)
    return (h["isOut"] is False and c["isOut"] is False and h["health"] == c["health"],
            f"unit {uid} isOut host/client {h['isOut']}/{c['isOut']} (want False), health {h['health']}/{c['health']} "
            f"(want equal)")


def ai_cell(host, client):
    got = [uv(host, A_ID)["hasAI"], uv(client, A_ID)["hasAI"]]
    return (got == [False, False], f"A hasAI host/client {got} (want False / False, QU3-4 (a))")


def psi_press(gc, host, tile, seed, ev):
    """The real-UI MIND CONTROL press of `gc`'s selected unit: the right-hand box (self-verified), PSI_ROWS rows, key 51
    -> CT_PSI, HOME, one self-verified click on `tile` with the host's set_seed right before it. Never retries."""
    if battle_state(gc).get("cursorType") in CURSOR_TARGETING:
        click_nth(gc, RHAND_NTH)
    r = click_nth(gc, RHAND_NTH)
    ev["rhand"] = (r.get("baseX"), r.get("baseY"))
    assert ev["rhand"] == RHAND_CENTRE, f"right-hand click on {gc.name} landed off the box: {r}"
    ok, _s = wait_until(lambda: G3F.top(gc) == "ActionMenuState", 5, 0.1)
    assert ok, f"no ActionMenuState on {gc.name} (stack {G3F.stack(gc)})"
    ev["rows"] = len([w for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", [])
                      if w.get("visible") and "ActionMenuItem" in w.get("type", "")])
    assert ev["rows"] == PSI_ROWS, f"action menu rows {ev['rows']} (want {PSI_ROWS})"
    gc.ok({"cmd": "inject_input", "kind": "key", "key": KEY_MC})
    wait_until(lambda: G3F.top(gc) != "ActionMenuState", 5, 0.1)
    ev["cursorAfterKey"] = battle_state(gc).get("cursorType")
    assert ev["cursorAfterKey"] == CT_PSI, f"key {KEY_MC}: cursorType {ev['cursorAfterKey']} (want {CT_PSI})"
    gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
    time.sleep(0.15)
    pr = gc.cmd({"cmd": "map_tile_click_pos", "x": tile[0], "y": tile[1], "z": tile[2]})
    assert pr.get("verified"), f"map_tile_click_pos {tile} on {gc.name} not verified: {pr}"
    host.ok({"cmd": "set_seed", "seed": seed})
    gc.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})


def mc_order(host, client, ctx0, target, ev, timeout=ORDER_S):
    """After a mind-control press or lever: a bounded wait for a new host context and the host idle, host boxes
    dismissed host-only, then a wait capped at CLIENT_MAP_S for the client's battle map on top (its own
    message box gone; stacks to EVIDENCE, a cap hit fails the order's cell). Returns the new contexts."""
    rec = {"hostBoxes": []}
    wait_until(lambda: (poll_host_box(host, rec, "mc") or True) and len(new_contexts(ctx0, ctxs(host))) >= 1
               and es(host, "busyOwnerSeat") == -1, timeout)
    settle(host, client, ev)
    poll_host_box(host, rec, "mc after")
    st0 = G3F.stack(client)
    ok, secs = wait_until(lambda: G3F.top(client) == "BattlescapeState", CLIENT_MAP_S, 0.1)
    new = new_contexts(ctx0, ctxs(host))
    ev.update(boxes=rec["hostBoxes"], newCtx=[cv(c) for c in new], target=[uv(host, target), uv(client, target)],
              clientStack=st0, clientMap=[ok, secs, G3F.stack(client)])
    return new


def mc_cell(new, origin, actor, host, client, target, faction, ev, sent=None):
    bad = []
    cm = ev.get("clientMap")
    if cm and not cm[0]:
        bad.append(f"the client's battle map not back on top within {CLIENT_MAP_S} s (R-U3-B-4): stack {cm[2]}")
    if len(new) != 1 or (new[0].get("origin"), new[0].get("kind"), new[0].get("actorId")) != (origin, "psi", actor):
        bad.append(f"new host contexts {[cv(c) for c in new]} (want exactly one {{{origin}, psi, {actor}}})")
    if sent is not None and sent != 1:
        bad.append(f"client coopIntentsSent.psi +{sent} (want +1)")
    got = [(uv(gc, target)["faction"], uv(gc, target)["mindControllerId"]) for gc in (host, client)]
    if got != [(faction, actor)] * 2:
        bad.append(f"unit {target} (faction, mindControllerId) host/client {got} (want {(faction, actor)} on both)")
    return (not bad, "; ".join(bad) or f"one {{{origin}, psi, {actor}}}; {target} controlled by {actor} on both")


def turn_order(host, client, uid, to_dir, ev):
    """The client's battle_intent turn for `uid`; returns (new contexts, the client's lastDeny for its iseq)."""
    ctx0 = ctxs(host)
    notes = []
    si = send_intent(host, client, {"cmd": "battle_intent", "kind": "turn", "actor": uid, "toDir": to_dir}, notes,
                     timeout=STEP_S)
    settle(host, client, ev)
    deny = es(client, "lastDeny") or {}
    ev["turn"] = {"toDir": to_dir, "iseq": si.get("iseq"), "answer": si.get("answer"), "notes": notes,
                  "deny": deny if deny.get("iseq") == si.get("iseq") else None}
    return new_contexts(ctx0, ctxs(host)), ev["turn"]["deny"]


def host_walk(host, client, uid, dest, ev, seed=None):
    """The host's real-UI walk of its selected `uid` to `dest` (asserted selected first); returns new contexts."""
    assert battle_state(host).get("selectedId") == uid, f"host selectedId {battle_state(host).get('selectedId')} " \
                                                        f"(want {uid}) before the walk click"
    ctx0, prev = ctxs(host), session.walk_action_id(host)
    if seed is not None:
        host.ok({"cmd": "set_seed", "seed": seed})
    real_click_walk(host, dest)
    try:
        session.wait_walk_settled(host, client, prev, timeout=STEP_S)
    except Exception as e:
        ev["walkError"] = str(e)[:200]
    settle(host, client, ev)
    return new_contexts(ctx0, ctxs(host))


def ctx_ok(new, origin, kind, actor):
    return len(new) == 1 and (new[0].get("origin"), new[0].get("kind"), new[0].get("actorId")) == (origin, kind, actor)


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


# ===================== rows =====================


def row_r2(host, client, crash0, st):
    ev = dict(st)
    stat_both(host, client, S3_ID, "reactions", 100)
    stat_both(host, client, S3_ID, "firing", 0)
    ev["s3Tu"] = set_tu_both(host, client, S3_ID, 255)
    ev["aSees"] = uv(host, A_ID), unit(host, A_ID).get("spottedThisTurn")
    seq0, ctx0, prev = es(host, "lastSeqEmitted") or 0, ctxs(host), session.walk_action_id(host)
    sent0 = dict(es(client, "coopIntentsSent") or {})
    host.ok({"cmd": "set_seed", "seed": SEED_R2})
    ev["walk"] = session.send_walk(client, A_ID, R2_DEST)
    try:
        session.wait_walk_settled(host, client, prev, timeout=STEP_S)
    except Exception as e:
        ev["walkError"] = str(e)[:200]
    settle(host, client, ev)
    cells = walk_react("R2", host, client, ctx0, seq0, "intent", A_ID, S3_ID, ev, sent0)
    cells["R2-alive"] = alive_cell(host, client, A_ID)
    ev["A"] = [uv(host, A_ID), uv(client, A_ID)]
    cells["R2-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_m2(host, client, crash0):
    ev, cells = {}, {}
    stat_both(host, client, S3_ID, "reactions", 0)
    amp = give_both(host, client, A_ID, PSI_AMP)["weaponId"]
    stat_both(host, client, A_ID, "psiSkill", 100)
    for uid in (S2_ID, S4_ID, S5_ID):
        stat_both(host, client, uid, "psiStrength", 0)
    set_tu_both(host, client, A_ID, A_TU)
    seen = unit(host, A_ID).get("spottedThisTurn") or []
    hostile = [(u.get("x"), u.get("y")) for u in G3F.units(host).values()
               if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]
    far = min(cheb(TILES[S5_ID][0], p) for p in hostile)
    ts = [(battle_state(gc).get("turn"), battle_state(gc).get("side")) for gc in (host, client)]
    ev.update(amp=amp, aSpotted=seen, s5Cheb=far, turnSide=ts)
    cells["M2-sees"] = (S2_ID in seen and S4_ID in seen and far >= UNSEEN_MIN and ts == [(1, 1)] * 2,
                        f"A spottedThisTurn on the host {seen} (want {S2_ID} and {S4_ID}); S5 Chebyshev {far} from "
                        f"the hostile units (want >= {UNSEEN_MIN}); (turn, side) {ts} (want (1, 1))")
    ui = ev["ui"] = {}
    ctx0, sent0 = ctxs(host), dict(es(client, "coopIntentsSent") or {})
    try:
        ui["tab"] = tab_select(client, A_ID)
        psi_press(client, host, TILES[S2_ID][0], SEED_M2, ui)
    except Exception as e:
        ui["pressError"] = str(e)[:300]
    new = mc_order(host, client, ctx0, S2_ID, ui)
    c1 = battle_state(client).get("cursorType")
    if c1 in CURSOR_TARGETING and ui["clientMap"][0]:
        click_nth(client, RHAND_NTH)   # cancel the client's leftover targeting (TASK 0: 3 -> 1)
    ui.update(cancel=[c1, battle_state(client).get("cursorType")], warningText=battle_state(client).get("warningText"))
    sent = (es(client, "coopIntentsSent") or {}).get("psi", 0) - sent0.get("psi", 0)
    cells["M2-ui"] = mc_cell(new, "intent", A_ID, host, client, S2_ID, FACTION_HOSTILE, ui, sent)
    ctl = ev["ctrl"] = {}
    s2 = [(uv(gc, S2_ID)["faction"], uv(gc, S2_ID)["mindControllerId"]) for gc in (host, client)]
    if s2 != [(FACTION_HOSTILE, A_ID)] * 2:
        cells["M2-ctrl"] = (False, f"S2 (faction, mindControllerId) host/client {s2} (want (1, {A_ID})): not mind-"
                                   f"controlled, no order sent")
    else:
        cap = stat_both(host, client, S2_ID, "tu", S2_TU, refill=True)["tu"]
        d0 = uv(client, S2_ID)["direction"]
        tnew, deny = turn_order(host, client, S2_ID, (d0 + 6) % 8, ctl)
        dirs = [uv(gc, S2_ID)["direction"] for gc in (host, client)]
        ctl.update(cap=cap, d0=d0, dirs=dirs, newCtx=[cv(c) for c in tnew])
        cells["M2-ctrl"] = (cap == S2_TU and ctx_ok(tnew, "intent", "turn", S2_ID) and deny is None
                            and dirs[0] == dirs[1] != d0,
                            f"S2 TU refill {cap} (want {S2_TU}); turn contexts {ctl['newCtx']} (want one {{intent, "
                            f"turn, {S2_ID}}}), deny {deny} (want none); direction {d0} -> host/client {dirs} (want "
                            f"changed and equal)")
    for cell, uid, want in (("M2-lever", S4_ID, "admit"), ("M2-unseen", S5_ID, "deny")):
        lv = ev[cell] = {}
        set_tu_both(host, client, A_ID, A_TU)
        ctx0 = ctxs(host)
        t = G3F.pos(host, uid)
        notes = []
        si = send_intent(host, client, {"cmd": "battle_intent", "kind": "psi", "actor": A_ID,
                                        "plan": {"action": "mc", "weapon": amp, "target": jt(t), "targetUnit": uid}},
                         notes, timeout=STEP_S)
        lnew = mc_order(host, client, ctx0, uid, lv, timeout=1)
        deny = es(client, "lastDeny") or {}
        lv.update(iseq=si.get("iseq"), answer=si.get("answer"), deny=deny, notes=notes)
        if want == "admit":
            cells[cell] = mc_cell(lnew, "intent", A_ID, host, client, uid, FACTION_HOSTILE, lv)
        else:
            got = [(uv(gc, uid)["faction"], uv(gc, uid)["mindControllerId"]) for gc in (host, client)]
            cells[cell] = (bool(si.get("iseq")) and deny.get("iseq") == si.get("iseq")
                           and deny.get("reason") == "invalid_target" and not lnew and got == [(0, 0)] * 2,
                           f"deny {deny} for iseq {si.get('iseq')} (want invalid_target, O1 (a)); new contexts "
                           f"{lv['newCtx']} (want none); S5 (faction, mcId) host/client {got} (want (0, 0))")
    for uid in (S2_ID, S4_ID):
        set_tu_both(host, client, uid, 0)
        stat_both(host, client, uid, "reactions", 0)
    cells["M2-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_r1(host, client, crash0):
    ev = {}
    ev["moved"] = [r[0].get("to") for r in session.place_deterministic(host, client, [
        {"cmd": "battle_teleport_unit", "unit": uid, "x": t[0], "y": t[1], "z": t[2], "dir": FACE_AWAY}
        for uid, t in MOVE_AWAY.items()], "R-U3-B-5")]
    side_change(host, client, client, FACTION_PLAYER, 2, ev)
    g = give_both(host, client, A_ID, PISTOL, CLIP)
    stat_both(host, client, A_ID, "reactions", 100)
    stat_both(host, client, A_ID, "firing", 0)
    stat_both(host, client, A_ID, "tu", A_TU, refill=True)
    ev.update(pistol=(g["weaponId"], g["ammoId"]), sSees=unit(host, S_ID).get("spottedThisTurn"))
    ev["tab"] = tab_select(host, S_ID)
    seq0, ctx0 = es(host, "lastSeqEmitted") or 0, ctxs(host)
    try:
        host_walk(host, client, S_ID, R1_DEST, ev, seed=SEED_R1)
    except Exception as e:
        ev["walkError"] = str(e)[:300]
    cells = walk_react("R1", host, client, ctx0, seq0, "host", S_ID, A_ID, ev)
    cells["R1-alive"] = alive_cell(host, client, S_ID)
    cells["R1-ai"] = ai_cell(host, client)
    stat_both(host, client, A_ID, "reactions", 0)
    ev["S"] = [uv(host, S_ID), uv(client, S_ID)]
    cells["R1-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_m1(host, client, crash0):
    ev, cells = {}, {}
    ev["ampS"] = give_both(host, client, S_ID, PSI_AMP)["weaponId"]
    stat_both(host, client, S_ID, "psiSkill", 100)
    stat_both(host, client, A_ID, "psiStrength", 0)
    ev["sTu"] = set_tu_both(host, client, S_ID, 255)
    ev["spotted"] = battle_state(host).get("spotted")
    ui = ev["ui"] = {}
    ctx0 = ctxs(host)
    try:
        ui["tab"] = tab_select(host, S_ID)
        psi_press(host, host, G3F.pos(host, A_ID), SEED_M1, ui)
    except Exception as e:
        ui["pressError"] = str(e)[:300]
    new = mc_order(host, client, ctx0, A_ID, ui)
    cells["M1-ui"] = mc_cell(new, "host", S_ID, host, client, A_ID, FACTION_PLAYER, ui)
    ctl = ev["ctrl"] = {}
    a = [(uv(gc, A_ID)["faction"], uv(gc, A_ID)["mindControllerId"]) for gc in (host, client)]
    if a != [(FACTION_PLAYER, S_ID)] * 2:
        cells["M1-ctrl"] = (False, f"A (faction, mindControllerId) host/client {a} (want (0, {S_ID})): not mind-"
                                   f"controlled, no order sent")
    else:
        ctl["tuBefore"] = [uv(gc, A_ID)["tu"] for gc in (host, client)]
        cap = stat_both(host, client, A_ID, "tu", A_TU, refill=True)["tu"]
        ctl["tab"] = tab_select(host, A_ID)
        try:
            wnew = host_walk(host, client, A_ID, M1_DEST, ctl)
        except Exception as e:
            wnew, ctl["walkError"] = [], str(e)[:300]
        pa = [G3F.pos(gc, A_ID) for gc in (host, client)]
        tnew, deny = turn_order(host, client, A_ID, (uv(client, A_ID)["direction"] + 2) % 8, ctl)
        ctl.update(cap=cap, walkCtx=[cv(c) for c in wnew], pos=pa, turnCtx=[cv(c) for c in tnew])
        cells["M1-ctrl"] = (cap == A_TU and ctx_ok(wnew, "host", "walk", A_ID) and pa == [M1_DEST] * 2 and not tnew
                            and (deny or {}).get("reason") == "not_your_unit",
                            f"A TU refill {cap} (want {A_TU}); walk contexts {ctl['walkCtx']} (want one {{host, walk, "
                            f"{A_ID}}}); A host/client {pa} (want {M1_DEST}); the client's turn: contexts "
                            f"{ctl['turnCtx']} (want none), deny {deny} (want not_your_unit)")
    cells["M1-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot B2 =====================


def stage(host, client):
    ev = {"placed": stage_tiles(host, client, TILES, (R2_DEST, R1_DEST, M1_DEST))}
    m = (host, client)
    g = G3F.guarded("staging", lambda: give_both(host, client, A_ID, PISTOL, CLIP), m)
    ev["aPistol"] = (g["weaponId"], g["ammoId"])
    g = G3F.guarded("staging", lambda: give_both(host, client, S3_ID, "STR_RIFLE", "STR_RIFLE_CLIP"), m)
    ev["s3Rifle"] = (g["weaponId"], g["ammoId"])
    side = {}
    G3F.guarded("staging", lambda: side_change(host, client, host, FACTION_HOSTILE, 1, side), m)
    ev.update(side=side, hash=G3F.hash_now(host, client))
    return ev


def boot_b2():
    host = GameClient("host", None, make_user_dir("r5u3_b2_host"))
    client = GameClient("client", None, make_user_dir("r5u3_b2_client"))
    m = (host, client)
    try:
        try:
            G3F.guarded("B2", lambda: BER.boot_pvp(host, client, KEY), m)
            G3F.guarded("B2", lambda: G3F.reactions_zero(host, client), m)
            crash0 = session._crash_log_snapshot()
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE B2 line)")
        try:
            st = stage(host, client)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        rows = dict(ROWS)
        fails = G3F.run_row("R2", rows["R2"], lambda: row_r2(host, client, crash0, st))
        fails += G3F.run_row("M2", rows["M2"], lambda: row_m2(host, client, crash0))
        fails += G3F.run_row("R1", rows["R1"], lambda: row_r1(host, client, crash0))
        fails += G3F.run_row("M1", rows["M1"], lambda: row_m1(host, client, crash0))
        print(f"EVIDENCE quiet: {client_quiet(client)}", flush=True)
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_b2()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_react_mc: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
