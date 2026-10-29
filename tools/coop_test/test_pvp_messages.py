"""PvP battle messages in gm2 (the client plays the aliens, seat 1; the host the seven X-COM soldiers, seat 0; both
instances with noAlienPanicMessages ON): in PvP each player sees vanilla's battle messages for its own units only, and
its own unit's death sets its dying flag.

Boot (key 48889, dirs pvp_messages_host / _client): BER.boot_pvp (STR_SMALL_SCOUT, map seed 1, gamemode 2), every live
unit's reactions 0, RM.TILES with every X-COM unit facing 4 (A unseen; A sees 8, 9, 10, 11), the host's END TURN ->
side 1 turn 1. Host boxes are closed host-only (test_messages idiom), the client's OK boxes by their OK button.
RING(gc) = the new `messages` ring records on gc since the row's start {unit, key, owner, presenter}. Seeds are set on
the host right before the action they govern. The ids, tiles and TUs below were measured equal on five boots without
the fix.
  alien_panic_attack  the alien player's panic attack gets vanilla's attacker message: the amp on A, A psiSkill 100,
       W (11) psiStrength 0, A's TU; the client's real-UI PANIC by A on W (the right-hand box, key 50, HOME, host
       set_seed ALIEN_PSI_SEED, one click).
       alien_panic_attack-psi     one new host context {intent, psi, A}; its psi cue {actor A, unit W, action panic,
                                  success true}
       alien_panic_attack-msg     RING(client) holds {key STR_MORALE_ATTACK_SUCCESSFUL, owner own}
                                  (without the fix: none)
       alien_panic_attack-host    RING(host) holds no STR_MORALE / STR_MIND key (guard)
  own_alien_panics  its own alien's panic gets its message with the option ON: A morale 0 (both); the client's END
       TURN -> side 0 turn 2; host set_seed PANIC_ROLL_SEED right before its END TURN -> side 1 turn 2.
       own_alien_panics-roll      the host's panic ev for A; A status 8 at the roll on both (precondition)
       own_alien_panics-msg       RING(client) holds {A, STR_HAS_PANICKED, own} (PANIC_ROLL_SEED's mode flee)
                                  (without the fix: none)
       own_alien_panics-cam       the client's camera.moves since the row's start hold a panic_centre for A
                                  (without the fix: none)
       own_alien_panics-host      RING(host) has no STR_HAS_PANICKED for A (guard: A unseen, option ON)
  opponent_death  no message for the opponent's fatal-wound death: S (12) health 1 + STAGE_WOUNDS (both); the client's
       END TURN -> side 0 turn 3.
       opponent_death-dead        S DEAD on both; RING(host) holds {S, STR_HAS_DIED_FROM_A_FATAL_WOUND, own}
                                  (precondition / guard)
       opponent_death-client      RING(client) holds no entry for S (without the fix: {S, the same key, other, okbox})
  xcom_panic_attack  the X-COM host's psi PANIC on the alien gives the alien player no attacker's message (side 0
       turn 3): the amp on PP (8), PP psiSkill 100, A psiStrength 0, PP's TU; tab_select(host, PP); while A is not in
       PP's host visibleUnits, the host's real-UI turn (HOME, map_tile_click_pos on A's tile verified, ONE right
       click); the host's real-UI PANIC by PP on A (host set_seed XCOM_PSI_SEED).
       xcom_panic_attack-seen     A in PP's host visibleUnits before the press (precondition)
       xcom_panic_attack-psi      one new host context {host, psi, PP}; its psi cue {actor PP, unit A, action panic,
                                  success true}
       xcom_panic_attack-client   RING(client) holds no STR_MORALE_ATTACK_SUCCESSFUL entry
                                  (without the fix: one, attacker PP)
       xcom_panic_attack-host     RING(host) holds {PP, STR_MORALE_ATTACK_SUCCESSFUL, own} (guard)
  B staging: a second alien B keeps the battle going after A's bleed-out in own_alien_death, so the death message can
       be read. The rifle on 13 and its TU, 14's spawn staging (STR_SECTOID_SOLDIER, faction 1, both), host set_seed
       SEED_B right before the host-local snap shot of 13 at FLOOR_B (a test command): one spawn {B, convert, from 14},
       B on 14's tile and facing on both (alien side), 14 dead; B reactions 0. One EVIDENCE line; a failure FAILs
       own_alien_death "staging".
  own_alien_death  (last) its own alien's fatal-wound death: A health 1 + STAGE_WOUNDS (both); the host's END TURN ->
       side 1 turn 3.
       own_alien_death-dead       A DEAD on both (precondition)
       own_alien_death-msg        RING(client) holds {A, STR_HAS_DIED_FROM_A_FATAL_WOUND, own} (without the fix: none)
       own_alien_death-dying      the client's displayTwo death record for A has unitDyingSet true
                                  (without the fix: false)
Common cell (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in this harness slot's crash
folder.
Without the fix, alien_panic_attack-msg, own_alien_panics-msg, own_alien_panics-cam, opponent_death-client,
xcom_panic_attack-client, own_alien_death-msg and own_alien_death-dying FAIL; every other cell passes. One EVIDENCE line
per row (both rings, the client's warningText), one PASS/FAIL line per cell, then the row verdict; every row runs after
a failure. A boot step past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound
fails the rows that need it "staging". Test-command pairs go to the client first; item ids come from the command
replies. ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_messages.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_messages as MSG  # noqa: E402
import test_host_combat as HC  # noqa: E402
from test_seat_pacing import tab_select, SDLK_HOME  # noqa: E402
from test_client_shoot import new_contexts, set_tu_both, RHAND_CENTRE  # noqa: E402

KEY = "48889"
OPTS = {"noAlienPanicMessages": True}   # both instances
A_ID = RM.A_ID                    # 1000000: the only alien at bring-up (STR_SECTOID_SOLDIER), the client's seat 1
W_ID, S_ID, PP_ID = 11, 12, 8     # the panic target, the bleed-out (opponent_death), the X-COM attacker
SHOOTER_B, VICTIM_B = 13, 14      # no row uses them; both outside A's sight
FACE = 4                          # every X-COM unit: A outside its view sector, A still sees 8..11
TILES = {u: (t, d if u == A_ID else FACE) for u, (t, d) in RM.TILES.items()}
FLOOR_B = (37, 37, 0)             # test_ownerless_units' FLOOR rule from 13 on (33,33,0): k 4, d 3 on both censuses
B_TYPE = "STR_SECTOID_SOLDIER"
TU = {A_ID: 54, PP_ID: 64, SHOOTER_B: 61}   # bring-up TUs
ALIEN_PSI_SEED = PANIC_ROLL_SEED = XCOM_PSI_SEED = SEED_B = 1
KEY_PANIC, CT_PSI, PSI_ROWS = 50, 3, 3      # the amp's PANIC key, its cursor, its menu rows
K_MORALE, K_MIND = "STR_MORALE_ATTACK_SUCCESSFUL", "STR_MIND_CONTROL_SUCCESSFUL"
K_UNDER, K_PANICKED, K_FATAL = "STR_IS_UNDER_ALIEN_CONTROL", "STR_HAS_PANICKED", "STR_HAS_DIED_FROM_A_FATAL_WOUND"
STATUS_DEAD, STATUS_PANICKING = 6, 8
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
STEP_S, PANIC_S = 30, 15
ROWS = (("alien_panic_attack", ("alien_panic_attack-psi", "alien_panic_attack-msg", "alien_panic_attack-host",
                                "alien_panic_attack-common")),
        ("own_alien_panics", ("own_alien_panics-roll", "own_alien_panics-msg", "own_alien_panics-cam",
                              "own_alien_panics-host", "own_alien_panics-common")),
        ("opponent_death", ("opponent_death-dead", "opponent_death-client", "opponent_death-common")),
        ("xcom_panic_attack", ("xcom_panic_attack-seen", "xcom_panic_attack-psi", "xcom_panic_attack-client",
                               "xcom_panic_attack-host", "xcom_panic_attack-common")),
        ("own_alien_death", ("own_alien_death-dead", "own_alien_death-msg", "own_alien_death-dying",
                             "own_alien_death-common")))

units, pos, es, ctxs, cv = G3F.units, G3F.pos, RM.es, RM.ctxs, RM.cv


# ===================== shared helpers (test_pvp_messages_gm3 imports them) =====================


def uv(gc, uid):
    u = units(gc).get(uid) or {}
    return {k: u.get(k) for k in ("x", "y", "z", "direction", "faction", "status", "tu", "health", "morale", "isOut",
                                  "visible", "visibleHere", "mindControllerId")}


def vis(gc, uid):
    return sorted((units(gc).get(uid) or {}).get("visibleUnits") or [])


def union(gc, faction):
    s = set()
    for u in units(gc).values():
        if u.get("faction") == faction and not u.get("isOut"):
            s.update(u.get("visibleUnits") or [])
    return sorted(s)


def snap(host, client):
    return MSG.msg_snap(host, client)


def ring(before, host, client):
    """RING: each machine's new ring records since `before` as {unit, key, owner, presenter, kind, seq}."""
    d = MSG.msg_delta(before, MSG.msg_snap(host, client))
    return {n: [{k: r.get(k) for k in ("unit", "key", "owner", "presenter", "kind", "seq")} for r in d[n]]
            for n in ("host", "client")}


def has(recs, **want):
    return [r for r in recs if all(r.get(k) == v for k, v in want.items())]


def evidence(ev, host, client, rg):
    ev.update(rings=rg, warningText=[battle_state(gc).get("warningText") for gc in (host, client)])


def close_client_ok(client, rec, where):
    """The client's OK box (its own message) closed by its OK button; its 2 s boxes close by themselves."""
    if G3F.top(client) != "InfoboxOKState":
        return False
    e = {"where": where, "texts": MSG.texts_of(client)}
    r = client.cmd({"cmd": "click_widget", "match": "OK"})
    e["closed"] = (r.get("ok"), r.get("error"))
    rec["clientBoxes"].append(e)
    return True


def quiet(host, client):
    return (G3F.top(host) == "BattlescapeState" and G3F.top(client) == "BattlescapeState"
            and es(host, "busyOwnerSeat") == -1
            and (es(client, "lastSeqApplied") or 0) == (es(host, "lastSeqEmitted") or 0)
            and (MSG.messages(client).get("queueDepth") or 0) == 0)


def settle(host, client, rec, where):
    """Bounded: host boxes closed host-only, the client's OK boxes by OK, NextTurnStates closed on both, until both tops
    are BattlescapeState, the host idle and the client caught up for 0.6 s. False on the bound."""
    deadline, since = time.time() + STEP_S, None
    while True:
        busy = MSG.poll_host_box(host, rec, where)
        busy = close_client_ok(client, rec, where) or busy
        for gc in (host, client):
            if G3F.top(gc) == "NextTurnState":
                gc.cmd({"cmd": "close_nextturn"})
                busy = True
        if not busy and quiet(host, client):
            since = since or time.time()
            if time.time() - since >= 0.6:
                return True
        else:
            since = None
        if time.time() > deadline:
            rec.setdefault("notes", []).append(f"{where}: not settled in {STEP_S} s: {G3F.stack(host)} / "
                                               f"{G3F.stack(client)}")
            return False
        time.sleep(0.05)


def side_change(host, client, presser, side, turn, where, seed=None, at_roll=None):
    """presser's END TURN (host set_seed `seed` right before it) -> both on (side, turn >= turn); `at_roll()` read right
    there, before any screen closes; then settle(). Returns ev; asserts the (turn, side) reached."""
    ev, rec = {"seq0": es(host, "lastSeqEmitted") or 0}, {"hostBoxes": [], "clientBoxes": []}
    if seed is not None:
        host.ok({"cmd": "set_seed", "seed": seed})
    ev["press"] = presser.cmd({"cmd": "battle_action", "action": "end_turn_button"}).get("ok")
    ok, secs = RM.wait_until(lambda: all(battle_state(gc).get("side") == side and (battle_state(gc).get("turn") or 0)
                                         >= turn for gc in (host, client)), STEP_S, 0.05)
    ev["sideS"] = [ok, secs]
    if at_roll:
        ev["roll"] = at_roll()
    ev.update(settled=settle(host, client, rec, where), boxes=rec,
              turnSide=[(battle_state(gc).get("turn"), battle_state(gc).get("side")) for gc in (host, client)])
    assert ev["turnSide"] == [(turn, side)] * 2, f"{where}: (turn, side) {ev['turnSide']} (want {(turn, side)})"
    return ev


def psi_press(gc, host, tile, seed, ev, key=KEY_PANIC, cursor=CT_PSI, rows=PSI_ROWS):
    """RM.psi_press with the action key, its cursor and the menu rows as parameters: the right-hand box
    (self-verified), `rows` rows, `key` -> `cursor`, HOME, the host's set_seed right before ONE verified click."""
    if battle_state(gc).get("cursorType") in RM.CURSOR_TARGETING:
        RM.click_nth(gc, RM.RHAND_NTH)
    r = RM.click_nth(gc, RM.RHAND_NTH)
    ev["rhand"] = (r.get("baseX"), r.get("baseY"))
    assert ev["rhand"] == RHAND_CENTRE, f"right-hand click on {gc.name} landed off the box: {r}"
    ok, _s = RM.wait_until(lambda: G3F.top(gc) == "ActionMenuState", 5, 0.1)
    assert ok, f"no ActionMenuState on {gc.name} (stack {G3F.stack(gc)})"
    ev["rows"] = len([w for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", [])
                      if w.get("visible") and "ActionMenuItem" in w.get("type", "")])
    assert ev["rows"] == rows, f"action menu rows {ev['rows']} (want {rows})"
    gc.ok({"cmd": "inject_input", "kind": "key", "key": key})
    RM.wait_until(lambda: G3F.top(gc) != "ActionMenuState", 5, 0.1)
    ev["cursorAfterKey"] = battle_state(gc).get("cursorType")
    assert ev["cursorAfterKey"] == cursor, f"key {key}: cursorType {ev['cursorAfterKey']} (want {cursor})"
    gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
    time.sleep(0.15)
    pr = gc.cmd({"cmd": "map_tile_click_pos", "x": tile[0], "y": tile[1], "z": tile[2]})
    assert pr.get("verified"), f"map_tile_click_pos {tile} on {gc.name} not verified: {pr}"
    host.ok({"cmd": "set_seed", "seed": seed})
    gc.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})


def cancel_aim(gc, ev):
    c1 = battle_state(gc).get("cursorType")
    if c1 in RM.CURSOR_TARGETING and G3F.top(gc) == "BattlescapeState":
        RM.click_nth(gc, RM.RHAND_NTH)   # the right-hand box cancels a leftover aim
    ev["cancel"] = [c1, battle_state(gc).get("cursorType")]


def psi_cell(host, client, new, seq0, origin, actor, want, ev):
    """Exactly one new host context {origin, psi, actor}; its chain holds one psi cue carrying `want`, all applied on
    the client."""
    aid = new[0].get("actionId") if len(new) == 1 else None
    hev = [(e["seq"], e["kind"]) for e in HC.evs_since(host, seq0) if aid is not None and e["actionId"] == aid]
    cseqs = {e["seq"] for e in HC.evs_since(client, seq0)}
    seqs = [s for s, k in hev if k == "psi"]
    pl = RM.host_payloads(host, seqs, timeout=3) if seqs else {}
    cues = [{k: (v.get("payload") or {}).get(k) for k in ("actor", "unit", "action", "success")} for _s, v in
            sorted(pl.items())]
    lacks = [s for s, _k in hev if s not in cseqs]
    ev.update(newCtx=[cv(c) for c in new], chain=hev, cues=cues, lacks=lacks)
    ok = (RM.ctx_ok(new, origin, "psi", actor) and len(cues) == 1
          and {k: cues[0].get(k) for k in want} == want and not lacks)
    return ok, (f"new host contexts {ev['newCtx']} (want one {{{origin}, psi, {actor}}}); psi cues {cues} (want one "
                f"carrying {want}); the client lacks {lacks} (want none)")


def psi_after(host, client, ctx0, target, ev):
    """RM.mc_order's bounded wait (a new host context, host free, host boxes closed host-only, the client's map back on
    top), then settle(). Returns the new host contexts."""
    new = RM.mc_order(host, client, ctx0, target, ev)
    rec = {"hostBoxes": [], "clientBoxes": []}
    settle(host, client, rec, "psi after")
    ev["afterBoxes"] = rec
    return new


def fatal(host, client, uid):
    r = RM.both(host, client, {"cmd": "battle_set_unit_state", "unit": uid, "health": MSG.STAGE_HEALTH,
                               "fatalWounds": MSG.STAGE_WOUNDS}, ("health", "fatalWounds"))
    return {"health": r.get("health"), "fatalWounds": r.get("fatalWounds")}


def morale0(host, client, uid):
    return RM.both(host, client, {"cmd": "battle_set_unit_state", "unit": uid, "morale": 0}, ("morale",)).get("morale")


def panic_wait(host, client, seq0, ev):
    """Bounded (PANIC_S): a host `panic` ev since seq0 and its bt_action_end, the host free; then settle()."""
    def done():
        evs = HC.evs_since(host, seq0)
        pids = [e["actionId"] for e in evs if e["kind"] == "panic"]
        return bool(pids) and any(e["kind"] == "bt_action_end" and e["actionId"] == pids[-1] for e in evs) \
            and es(host, "busyOwnerSeat") == -1
    ev["panicWait"] = RM.wait_until(done, PANIC_S, 0.2)
    rec = {"hostBoxes": [], "clientBoxes": []}
    settle(host, client, rec, "panic after")
    ev["panicBoxes"] = rec
    hev = HC.evs_since(host, seq0)
    pseqs = [e["seq"] for e in hev if e["kind"] == "panic"]
    return [(v.get("payload") or {}) for _s, v in sorted(RM.host_payloads(host, pseqs, timeout=3).items())]


def statuses(host, client, uid):
    return [(units(gc).get(uid) or {}).get("status") for gc in (host, client)]


def dead_cell(host, client, uid, ev):
    ok, secs = RM.wait_until(lambda: statuses(host, client, uid) == [STATUS_DEAD] * 2, 15, 0.1)
    got = statuses(host, client, uid)
    ev["deadWait"] = [ok, secs]
    return got == [STATUS_DEAD] * 2, f"unit {uid} status host/client {got} (want {STATUS_DEAD} on both)"


def host_drained(host, client, where):
    """S's bleed-out runs in the host's UnitDieBState after side_change()'s settle()
    went quiet (quiet() does not read the host's BState queue); vanilla pushes the fatal-wound box, and with it the host's
    ring record, when that state pops (UnitDieBState.cpp, _extraFrame 2), about 0.2 s after S reads DEAD. Bounded (STEP_S):
    the host's BState queue empty (battle_state pendingStates 0, isBusy false), then settle() (that box closed host-only,
    the client caught up). Returns ([ok, s], the settle's boxes)."""
    ok = RM.wait_until(lambda: (battle_state(host).get("pendingStates") or 0) == 0
                       and not battle_state(host).get("isBusy"), STEP_S, 0.05)
    rec = {"hostBoxes": [], "clientBoxes": []}
    settle(host, client, rec, where)
    return list(ok), rec


def death_records(client, uid):
    r = ((es(client, "displayTwo") or {}).get("death") or {}).get("ring") or []
    return [{k: x.get(k) for k in ("seq", "unit", "instant", "outcome", "unitDyingSet", "endedBy")} for x in r
            if x.get("unit") == uid]


def convert_b(host, client, crash0, coop):
    """Stages the second alien B, which keeps the battle going after A's bleed-out in own_alien_death: 14 set to
    respawn as B_TYPE (the spawnUnit test command), then 13's snap shot at FLOOR_B converts it. Returns B's id or
    None."""
    ev = {}
    try:
        g = RM.give_both(host, client, SHOOTER_B, "STR_RIFLE", "STR_RIFLE_CLIP")
        ev["rifle"] = (g.get("weaponId"), g.get("ammoId"))
        ev["tu13"] = set_tu_both(host, client, SHOOTER_B, TU[SHOOTER_B])
        sp = RM.both(host, client, {"cmd": "battle_set_unit_state", "unit": VICTIM_B, "spawnUnit": B_TYPE,
                                    "spawnUnitFaction": FACTION_HOSTILE, "respawn": True},
                     ("spawnUnit", "spawnUnitFaction", "respawn"))
        ev["spawnStaging"] = {k: sp.get(k) for k in ("spawnUnit", "spawnUnitFaction", "respawn")}
        u0, seq0, ctx0 = set(units(host)), es(host, "lastSeqEmitted") or 0, ctxs(host)
        vt = uv(host, VICTIM_B)
        host.ok({"cmd": "set_seed", "seed": SEED_B})
        fire = host.cmd({"cmd": "battle_fire", "unit": SHOOTER_B, "mode": "snap", "x": FLOOR_B[0], "y": FLOOR_B[1],
                         "z": FLOOR_B[2], "tu": TU[SHOOTER_B]})
        ev["fire"] = {k: fire.get(k) for k in ("ok", "error", "tuCost")}
        rec = {"hostBoxes": [], "clientBoxes": []}
        RM.wait_until(lambda: len(new_contexts(ctx0, ctxs(host))) >= 1 and es(host, "busyOwnerSeat") == -1, STEP_S, 0.1)
        settle(host, client, rec, "B")
        new = new_contexts(ctx0, ctxs(host))
        hev = [(e["seq"], e["kind"]) for e in HC.evs_since(host, seq0)]
        sp_seqs = [s for s, k in hev if k == "spawn"]
        spawns = [(v.get("payload") or {}) for _s, v in sorted(RM.host_payloads(host, sp_seqs, timeout=3).items())]
        added = [sorted(set(units(gc)) - u0) for gc in (host, client)]
        ev.update(newCtx=[cv(c) for c in new], chain=hev, spawns=spawns, added=added, boxes=rec)
        b = added[0][0] if len(added[0]) == 1 and added[1] == added[0] else None
        want = {"x": vt["x"], "y": vt["y"], "z": vt["z"], "direction": vt["direction"], "faction": FACTION_HOSTILE,
                "type": B_TYPE, "coop": coop}
        got = [{k: (units(gc).get(b) or {}).get(k) for k in want} for gc in (host, client)]
        ev.update(B=b, Bfields=got, victim=[uv(gc, VICTIM_B)["status"] for gc in (host, client)])
        assert (b is not None and RM.ctx_ok(new, "host", "shoot", SHOOTER_B)
                and spawns == [{"unit": b, "cause": "convert", "from": VICTIM_B}] and got == [want, want]
                and ev["victim"] == [STATUS_DEAD] * 2), (f"B: contexts {ev['newCtx']} (want one {{host, shoot, 13}}), "
                                                         f"spawns {spawns}, B {got} (want {want}), 14 status "
                                                         f"{ev['victim']} (want dead on both)")
        RM.stat_both(host, client, b, "reactions", 0)
        ev["common"] = G3F.common(host, client, crash0)
    except Exception as e:
        ev["error"] = f"{type(e).__name__}: {str(e)[:500]}"
        G3F.capture("B staging", ev["error"], (host, client))
        b = None
    print(f"EVIDENCE B-staging: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    return b


def own_death(host, client, presser, ev):
    """A's fatal wound (both), the presser's END TURN -> side 1 turn 3 (A bleeds out at its side's start; B keeps the
    battle going), settled; returns (RING, the DEAD cell)."""
    ev["staged"] = fatal(host, client, A_ID)
    s0 = snap(host, client)
    ev["side"] = side_change(host, client, presser, FACTION_HOSTILE, 3, "own death END TURN")
    dead = dead_cell(host, client, A_ID, ev)
    rec = {"hostBoxes": [], "clientBoxes": []}
    settle(host, client, rec, "own death after")
    hev = HC.evs_since(host, ev["side"]["seq0"])
    ev.update(after=rec, hostEvs=[(e["seq"], e["kind"]) for e in hev], A=[uv(host, A_ID), uv(client, A_ID)],
              battleEnd=[(es(gc, "battleEnd") or {}).get("reason") for gc in (host, client)])
    return ring(s0, host, client), dead


# ===================== rows =====================


def row_alien_panic_attack(host, client, crash0):
    ev, cells = {}, {}
    ev["amp"] = RM.give_both(host, client, A_ID, RM.PSI_AMP)["weaponId"]
    RM.stat_both(host, client, A_ID, "psiSkill", 100)
    RM.stat_both(host, client, W_ID, "psiStrength", 0)
    ev["tu"] = set_tu_both(host, client, A_ID, TU[A_ID])
    s0, ctx0, seq0 = snap(host, client), ctxs(host), es(host, "lastSeqEmitted") or 0
    ui = ev["ui"] = {}
    try:
        ui["tab"] = tab_select(client, A_ID)
        psi_press(client, host, RM.TILES[W_ID][0], ALIEN_PSI_SEED, ui)
    except Exception as e:
        ui["pressError"] = str(e)[:300]
    new = psi_after(host, client, ctx0, W_ID, ui)
    cancel_aim(client, ui)
    rg = ring(s0, host, client)
    evidence(ev, host, client, rg)
    cells["alien_panic_attack-psi"] = psi_cell(host, client, new, seq0, "intent", A_ID,
                                               {"actor": A_ID, "unit": W_ID, "action": "panic", "success": True}, ev)
    cells["alien_panic_attack-msg"] = (bool(has(rg["client"], key=K_MORALE, owner="own")),
                                       f"RING(client) {rg['client']} (want one {{key {K_MORALE}, owner own}})")
    bad = [r for r in rg["host"] if r.get("key") in (K_MORALE, K_MIND)]
    cells["alien_panic_attack-host"] = (not bad, f"RING(host) {rg['host']} (want no {K_MORALE} / {K_MIND} key)")
    cells["alien_panic_attack-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_own_alien_panics(host, client, crash0):
    ev, cells = {}, {}
    ev["morale"] = morale0(host, client, A_ID)
    s0, seq0 = snap(host, client), es(host, "lastSeqEmitted") or 0
    ev["a"] = side_change(host, client, client, FACTION_PLAYER, 2, "own_alien_panics client END TURN")
    ev["b"] = side_change(host, client, host, FACTION_HOSTILE, 2, "own_alien_panics host END TURN",
                          seed=PANIC_ROLL_SEED,
                          at_roll=lambda: statuses(host, client, A_ID))
    panics = panic_wait(host, client, seq0, ev)
    cam = HC.cam_moves(HC.camera_of(client), seq0)
    rg = ring(s0, host, client)
    evidence(ev, host, client, rg)
    ev.update(panics=panics, camMoves=[{k: m.get(k) for k in ("seq", "reason", "unit")} for m in cam],
              A=[uv(host, A_ID), uv(client, A_ID)])
    roll = ev["b"].get("roll")
    cells["own_alien_panics-roll"] = ([p.get("unit") for p in panics] == [A_ID] and roll == [STATUS_PANICKING] * 2,
                                      f"host panic payloads {panics} (want one for unit {A_ID}); A status at the roll "
                                      f"host/client {roll} (want {STATUS_PANICKING} on both)")
    cells["own_alien_panics-msg"] = (bool(has(rg["client"], unit=A_ID, key=K_PANICKED, owner="own")),
                                     f"RING(client) {rg['client']} (want {{unit {A_ID}, key {K_PANICKED}, owner own}})")
    pc = [m for m in cam if m.get("reason") == "panic_centre" and m.get("unit") == A_ID]
    cells["own_alien_panics-cam"] = (bool(pc),
                                     f"client camera.moves since seq {seq0}: {ev['camMoves']} (want a panic_centre for "
                                     f"{A_ID})")
    cells["own_alien_panics-host"] = (not has(rg["host"], unit=A_ID, key=K_PANICKED),
                                      f"RING(host) {rg['host']} (want no {K_PANICKED} for {A_ID})")
    cells["own_alien_panics-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_opponent_death(host, client, crash0):
    ev, cells = {}, {}
    ev["staged"] = fatal(host, client, S_ID)
    s0 = snap(host, client)
    ev["side"] = side_change(host, client, client, FACTION_PLAYER, 3, "opponent_death client END TURN")
    dead = dead_cell(host, client, S_ID, ev)
    ev["drain"], ev["after"] = host_drained(host, client, "opponent_death after")
    rg = ring(s0, host, client)
    evidence(ev, host, client, rg)
    hr = has(rg["host"], unit=S_ID, key=K_FATAL, owner="own")
    cells["opponent_death-dead"] = (dead[0] and bool(hr),
                                    f"{dead[1]}; RING(host) {rg['host']} (want {{unit {S_ID}, key {K_FATAL}, "
                                    f"owner own}})")
    cells["opponent_death-client"] = (not has(rg["client"], unit=S_ID),
                                      f"RING(client) {rg['client']} (want no entry for {S_ID})")
    cells["opponent_death-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_xcom_panic_attack(host, client, crash0):
    ev, cells = {}, {}
    ev["amp"] = RM.give_both(host, client, PP_ID, RM.PSI_AMP)["weaponId"]
    RM.stat_both(host, client, PP_ID, "psiSkill", 100)
    RM.stat_both(host, client, A_ID, "psiStrength", 0)
    ev["tu"] = set_tu_both(host, client, PP_ID, TU[PP_ID])
    turn = ev["turn"] = {}
    try:
        turn["tab"] = tab_select(host, PP_ID)
        turn["before"] = {"pp": uv(host, PP_ID), "sees": vis(host, PP_ID), "a": G3F.pos(host, A_ID)}
        if A_ID not in vis(host, PP_ID):
            at, d0, ctx0 = G3F.pos(host, A_ID), uv(host, PP_ID)["direction"], ctxs(host)
            host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
            time.sleep(0.15)
            pr = host.cmd({"cmd": "map_tile_click_pos", "x": at[0], "y": at[1], "z": at[2]})
            assert pr.get("verified"), f"turn target {at} not verified: {pr}"
            host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "right"})
            turn["wait"] = RM.wait_until(lambda: uv(host, PP_ID)["direction"] != d0, 10, 0.1)
            RM.settle(host, client, turn)
            turn.update(newCtx=[cv(c) for c in new_contexts(ctx0, ctxs(host))], pp=uv(host, PP_ID))
    except Exception as e:
        turn["error"] = str(e)[:300]
    sees = vis(host, PP_ID)
    cells["xcom_panic_attack-seen"] = (A_ID in sees,
                                       f"PP {PP_ID}'s host visibleUnits {sees} before the press (want {A_ID} in it)")
    s0, ctx0, seq0 = snap(host, client), ctxs(host), es(host, "lastSeqEmitted") or 0
    ui = ev["ui"] = {}
    try:
        psi_press(host, host, G3F.pos(host, A_ID), XCOM_PSI_SEED, ui)
    except Exception as e:
        ui["pressError"] = str(e)[:300]
    new = psi_after(host, client, ctx0, A_ID, ui)
    cancel_aim(host, ui)
    rg = ring(s0, host, client)
    evidence(ev, host, client, rg)
    cells["xcom_panic_attack-psi"] = psi_cell(host, client, new, seq0, "host", PP_ID,
                                              {"actor": PP_ID, "unit": A_ID, "action": "panic", "success": True}, ev)
    cells["xcom_panic_attack-client"] = (not has(rg["client"], key=K_MORALE),
                                         f"RING(client) {rg['client']} (want no {K_MORALE} entry)")
    cells["xcom_panic_attack-host"] = (bool(has(rg["host"], unit=PP_ID, key=K_MORALE, owner="own")),
                                       f"RING(host) {rg['host']} (want {{unit {PP_ID}, key {K_MORALE}, owner own}})")
    cells["xcom_panic_attack-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_own_alien_death(host, client, crash0):
    ev, cells = {}, {}
    rg, dead = own_death(host, client, host, ev)
    recs = death_records(client, A_ID)
    evidence(ev, host, client, rg)
    ev["deathRecords"] = recs
    cells["own_alien_death-dead"] = dead
    cells["own_alien_death-msg"] = (bool(has(rg["client"], unit=A_ID, key=K_FATAL, owner="own")),
                                    f"RING(client) {rg['client']} (want {{unit {A_ID}, key {K_FATAL}, owner own}})")
    cells["own_alien_death-dying"] = (len(recs) == 1 and recs[0].get("unitDyingSet") is True,
                                      f"the client's displayTwo death records for {A_ID}: {recs} (want one with "
                                      f"unitDyingSet true)")
    cells["own_alien_death-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot =====================


def stage(host, client, presser):
    """RM.TILES with the X-COM facings (FLOOR_B also open ground), then presser's END TURN -> side 1 turn 1."""
    m, ev = (host, client), {}
    ev["placed"] = RM.stage_tiles(host, client, TILES, (FLOOR_B,))
    ev["side"] = G3F.guarded("staging", lambda: side_change(host, client, presser, FACTION_HOSTILE, 1, "staging"), m)
    ev.update(aSees=vis(host, A_ID), aVisible=[uv(gc, A_ID)["visible"] for gc in m], xcomUnion=union(host,
                                                                                                    FACTION_PLAYER),
              sel=[battle_state(gc).get("selectedId") for gc in m], hash=G3F.hash_now(host, client))
    print(f"EVIDENCE staging: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    return ev


def run_boot():
    host = GameClient("host", None, make_user_dir("pvp_messages_host", options=OPTS))
    client = GameClient("client", None, make_user_dir("pvp_messages_client", options=OPTS))
    m = (host, client)
    try:
        try:
            G3F.guarded("boot", lambda: BER.boot_pvp(host, client, KEY), m)
            crash0 = session._crash_log_snapshot()
            G3F.guarded("boot", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        try:
            stage(host, client, host)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        rows = dict(ROWS)
        fails = G3F.run_row("alien_panic_attack", rows["alien_panic_attack"],
                            lambda: row_alien_panic_attack(host, client, crash0))
        fails += G3F.run_row("own_alien_panics", rows["own_alien_panics"],
                             lambda: row_own_alien_panics(host, client, crash0))
        fails += G3F.run_row("opponent_death", rows["opponent_death"], lambda: row_opponent_death(host, client, crash0))
        fails += G3F.run_row("xcom_panic_attack", rows["xcom_panic_attack"],
                             lambda: row_xcom_panic_attack(host, client, crash0))
        if convert_b(host, client, crash0, 1) is None:
            fails += G3F.fail_all((("own_alien_death", rows["own_alien_death"]),),
                                  "staging (see the CAPTURE B staging line)")
        else:
            fails += G3F.run_row("own_alien_death", rows["own_alien_death"],
                                 lambda: row_own_alien_death(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_messages: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
