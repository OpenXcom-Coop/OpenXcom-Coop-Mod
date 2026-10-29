"""R5-U4 rows T, S and E (owner D235 (a); D235-VL1 / R5-V2, D235-VL2): the host commands every player-side unit no
player owns - a tank at the battle start, a player-side unit created mid-battle - and END TURN counts a host whose only
live units are such units. Boot C: classic co-op (gamemode 1), lobby key 48688, dirs r5u4_c_host / r5u4_c_client.

Spec: docs repo rewrite/prompts/r5u4_ownerless_units.md section (f) test_ownerless_units.py (QU4-1..QU4-8 (a)), with
the orchestrator rulings R-U4-A-1 (the shooter staged onto open ground, hash-gated), R-U4-A-5 (the victim staged onto
open ground first, room for its converted unit's one-tile walk), R-U4-A-6 (one TAB before the click that selects the
converted unit) and R-U4-A-7 (the victim faces that walk, so the converted unit walks with no turn).
Constants: rewrite/r5u4-task0/CONSTANTS.md (TASK 0 boots Ca, Cb, Cc, Cd; section RED2 and its RESUME 1 pins).

Boot C: the host sets SEED_ROSTER before its NEW BATTLE; the W2-P8b spine (session.drive_to_battlescape, STR_SMALL_SCOUT)
with a pre_seat hook that picks the Skyranger, cuts its crew to three (C1, C2, H; F11261: classic co-op halves the
craft's capacity) and loads one STR_TANK_CANNON; C1 / C2 go to seat 1, H stays the host's; map seed 1 right before
newbattle_ok; pin_ai_neutral; every live unit's reactions 0 on both machines.
  T  the tank: T-gen (one STR_TANK_CANNON unit, the crew's seats), T-seat (the tank carries seat 0), T-sel (the host's
     TAB selects it), T-walk (the host's real click walk moves it), T-deny (the partner's turn intent is refused
     not_your_unit), T-common.
  S  a player-side unit created mid-battle: H and C1 staged on open ground (hash-gated teleports), H's spawn staging
     (STR_SECTOID_SOLDIER, spawnUnitFaction 0), host set_seed, the host-local lever snap shot of C1 at FLOOR_S converts H
     into P: S-spawn, S-seat, S-sel (one TAB, then one click on P), S-walk, S-deny, S-common.
  E  END TURN while the host's only live units are the tank and P: E-wait (the partner's press: count 1, needed 2, the
     side keeps running), E-end (the host's press ends it), E-common. E ends the X-COM side, so it is the last row.
Red at A1 (the unchanged build): T-seat, T-walk, S-seat, S-walk, E-wait, E-end FAIL; every other cell PASS.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure. A boot
step past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails the rows
that need it "staging"; a cell whose precondition cell failed FAILs "not reached". Common cell: every hash bucket EQUAL,
desyncSeen false on both, no new crash file. Lever pairs go to the client first; ids come from probes (S25).
run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.

Run:  python tools/coop_test/test_ownerless_units.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import repro_atom_walk as RAW  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
from repro_atom_side_begin import drive_side_change  # noqa: E402
from test_seat_pacing import tab_select, real_click_walk, SDLK_HOME, SDLK_TAB  # noqa: E402
from test_battle_end_rules import wait_until  # noqa: E402
from test_client_shoot import new_contexts  # noqa: E402
from test_delta_core import both  # noqa: E402
from test_host_combat import evs_since  # noqa: E402
from test_ai_origins import host_payloads  # noqa: E402

KEY = "48688"
SEED_ROSTER, SEED_MAP, SEED_S = 1, 1, 1   # host set_seed before the lobby / newbattle_ok / the S shot
STEP_S = 30                               # every bounded wait (TASK 0: each step <= 3 s)
MISSION, CRAFT, TANK_ITEM = "STR_SMALL_SCOUT", "STR_SKYRANGER", "STR_TANK_CANNON"
MAP_FP_C = -4.48310638993e+18             # both machines (Ca-Cd)
TANK = 1000000                            # the tank's unit id (Ca-Cd)
KEPT, C1, C2, H = [8, 9, 10], 8, 9, 10    # the crew kept (11-14 cut); C1 / C2 seat 1, H seat 0
T_DEST = (14, 17, 1)                      # 2 tiles north of the tank (14,19,1): path_probe steps 2, tuCost 8 on both
T_END = (14, 17, 0)                       # the walk's measured end on both machines - vanilla steps
                                          # the tank down onto the Skyranger ramp; path_probe sums the path's directions
                                          # and cannot see that step-down
STAGE_H, H_DIR = (20, 19, 0), 0           # the victim, facing P_DEST
STAGE_C1, C1_DIR = (24, 19, 0), 5         # the shooter; a clear ray west to STAGE_H
FLOOR_S = (28, 19, 0)                     # the FLOOR rule's target from STAGE_C1 (k 4, d 2)
S_TYPE = "STR_SECTOID_SOLDIER"
P_TU = 30
P_DEST = (20, 18, 0)                      # 1 tile north of STAGE_H: path_probe steps 1, tuCost 4 on both
STATUS_DEAD = 6
ROWS = (("T", ("T-gen", "T-seat", "T-sel", "T-walk", "T-deny", "T-common")),
        ("S", ("S-spawn", "S-seat", "S-sel", "S-walk", "S-deny", "S-common")),
        ("E", ("E-wait", "E-end", "E-common")))

units, pos, es = G3F.units, G3F.pos, G3F.es


# ===================== shared with test_pvp_spawn_seat.py =====================


def blocked(gc):
    return es(gc, "coopLocalExecBlocked") or 0


def ctx_cell(new, origin, kind, actor):
    got = [(c.get("origin"), c.get("kind"), c.get("actorId")) for c in new]
    return (got == [(origin, kind, actor)],
            f"new host closedContexts {got} (want exactly one ({origin!r}, {kind!r}, {actor}))")


def not_reached(cells, names, why):
    for n in names:
        cells[n] = (False, f"not reached ({why})")


def give(host, client, uid, item, ammo):
    return both(host, client, {"cmd": "battle_give", "unit": uid, "item": item, "ammo": ammo, "slot": "right",
                               "clear_hands": True}, ("weaponId", "ammoId"))


def tele(host, client, uid, t, d, what):
    """One hash-gated teleport (session.place_deterministic: both machines, equal replies, every bucket EQUAL)."""
    return session.place_deterministic(host, client, [{"cmd": "battle_teleport_unit", "unit": uid, "x": t[0],
                                                       "y": t[1], "z": t[2], "dir": d}], what=what)[0][0]


def spawn_staging(host, client, victim, spawn_type, faction):
    return both(host, client, {"cmd": "battle_set_unit_state", "unit": victim, "spawnUnit": spawn_type,
                               "spawnUnitFaction": faction, "respawn": True}, ("spawnUnit", "spawnUnitFaction", "respawn"))


def host_settled(host):
    b = battle_state(host)
    return b.get("pendingStates") == 0 and not b.get("isBusy") and es(host, "busyOwnerSeat") == -1


def convert(host, client, shooter, floor, seed, ev):
    """The lever conversion (QU4-5 (a), the C12a shape): host set_seed right before the host-local battle_fire {shooter,
    snap, floor, tu = its own TU}, then settle. Fills ev; returns (new unit id or None, new contexts, spawn payloads)."""
    uh0 = units(host)
    seq0, ctx0 = es(host, "lastSeqEmitted") or 0, es(host, "closedContexts") or []
    host.ok({"cmd": "set_seed", "seed": seed})
    fire = host.cmd({"cmd": "battle_fire", "unit": shooter, "mode": "snap", "x": floor[0], "y": floor[1],
                     "z": floor[2], "tu": (uh0.get(shooter) or {}).get("tu")})
    ok, secs = wait_until(lambda: host_settled(host), STEP_S, 0.1)
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    new = new_contexts(ctx0, es(host, "closedContexts"))
    end = new[0].get("endSeq") if len(new) == 1 else None
    hev = [e for e in evs_since(host, seq0) if end is None or (e["seq"] or 0) <= end]
    sp = [e["seq"] for e in hev if e["kind"] == "spawn"]
    pl = host_payloads(host, sp) if sp else {}
    spawns = [(pl.get(s) or {}).get("payload") for s in sp]
    uh, uc = units(host), units(client)
    added, added_c = sorted(set(uh) - set(uh0)), sorted(set(uc) - set(uh0))
    ev.update(fire={k: fire.get(k) for k in ("ok", "error", "tuCost", "weaponId", "ammoId")}, settled=[ok, secs],
              newCtx=new, chain=[(e["seq"], e["kind"]) for e in hev], spawns=spawns, added=[added, added_c])
    return (added[0] if len(added) == 1 and added_c == added else None), new, spawns


def spawn_cell(new, shooter, spawns, unit, victim, host, client, want):
    """One new host context {host, shoot, shooter} whose evs hold exactly one spawn {unit, convert, from victim}; the new
    unit on both machines with the `want` fields; the victim dead on both."""
    c_ok, c_txt = ctx_cell(new, "host", "shoot", shooter)
    sp_ok = spawns == [{"unit": unit, "cause": "convert", "from": victim}]
    uh, uc = units(host), units(client)
    nu = [{k: (u.get(unit) or {}).get(k) for k in want} for u in (uh, uc)]
    dead = [((u.get(victim) or {}).get("status"), (u.get(victim) or {}).get("isOut")) for u in (uh, uc)]
    ok = unit is not None and c_ok and sp_ok and nu == [want, want] and dead == [(STATUS_DEAD, True)] * 2
    return ok, (f"{c_txt}; spawn payloads {spawns} (want one {{unit {unit}, cause convert, from {victim}}}); new unit "
                f"{unit} host/client {nu} (want {want}); victim {victim} (status, isOut) host/client {dead} (want dead)")


def both_fields(host, client, uid, key, want):
    got = [(units(gc).get(uid) or {}).get(key) for gc in (host, client)]
    return got == [want, want], f"unit {uid} {key} host/client {got} (want {want} on both)"


def tab_then_click(host, uid, ev):
    """ONE TAB (it leaves the post-shot cursor state), the TAB-selected unit recorded and required
    not to be `uid`; then HOME and ONE self-verified left click on uid's tile must select it."""
    ev["cursor0"] = battle_state(host).get("cursorType")
    host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
    time.sleep(0.15)
    ev["tabSel"], ev["tabCursor"] = battle_state(host).get("selectedId"), battle_state(host).get("cursorType")
    if ev["tabSel"] == uid:
        return False, f"the TAB selected {uid} itself (want another unit: the click must select it; FIXTURE-STOP)"
    host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
    time.sleep(0.15)
    t = pos(host, uid)
    pr = host.cmd({"cmd": "map_tile_click_pos", "x": t[0], "y": t[1], "z": t[2]})
    if not pr.get("verified"):
        return False, f"map_tile_click_pos {t} did not verify: {pr}"
    host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
    ok, ev["selS"] = wait_until(lambda: battle_state(host).get("selectedId") == uid, STEP_S, 0.1)
    sel = battle_state(host).get("selectedId")
    return ok, (f"TAB selected {ev['tabSel']} (cursorType {ev['cursor0']} -> {ev['tabCursor']}); after the click "
                f"selectedId {sel} (want {uid})")


def path_both(host, client, uid, t):
    rr = [gc.cmd({"cmd": "path_probe", "unit": uid, "x": t[0], "y": t[1], "z": t[2]}) for gc in (host, client)]
    return [{k: r.get(k) for k in ("reachable", "steps", "tuCost")} for r in rr]


def host_walk(host, client, uid, dest, ev, end=None):
    """The host's real click walk (the unit already selected): bounded until `uid` stands on `end` (default `dest`, the
    clicked tile) on both machines with the partner's order slot empty, or the host refuses it (coopLocalExecBlocked
    grows). Returns the walk cell."""
    end = dest if end is None else end
    ev["path"] = path_both(host, client, uid, dest)
    b0, ctx0 = blocked(host), es(host, "closedContexts") or []
    try:
        real_click_walk(host, dest)
    except AssertionError as e:
        return False, f"the host's click walk was never sent: {str(e)[:300]}"
    ok, ev["walkS"] = wait_until(lambda: (pos(host, uid) == end and pos(client, uid) == end
                                          and es(client, "inFlight") is None) or blocked(host) > b0, STEP_S, 0.2)
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    new = new_contexts(ctx0, es(host, "closedContexts"))
    ps, b1 = [pos(host, uid), pos(client, uid)], blocked(host)
    ev.update(newCtx=new, blocked=[b0, b1], at=ps)
    c_ok, c_txt = ctx_cell(new, "host", "walk", uid)
    return (c_ok and ps == [end, end],
            f"{c_txt}; unit {uid} host/client {ps} (want {end} on both; {ev['walkS']} s); host coopLocalExecBlocked "
            f"{b0} -> {b1}; path_probe host/client {ev['path']}")


def partner_turn(host, client, uid, to_dir, ev):
    """The partner's turn intent {uid, to_dir}, bounded until both machines face to_dir or its lastDeny changes."""
    ctx0, d0 = es(host, "closedContexts") or [], es(client, "lastDeny")
    ev["intent"] = client.cmd({"cmd": "battle_intent", "kind": "turn", "actor": uid, "toDir": to_dir})
    dirs = lambda: [(units(gc).get(uid) or {}).get("direction") for gc in (host, client)]
    _, ev["turnS"] = wait_until(lambda: es(client, "lastDeny") != d0 or (dirs() == [to_dir, to_dir]
                                                                          and es(client, "inFlight") is None), STEP_S, 0.1)
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    ev.update(newCtx=new_contexts(ctx0, es(host, "closedContexts")), lastDeny0=d0, lastDeny=es(client, "lastDeny"),
              dirs=dirs())
    return ev


def deny_cell(ev, uid):
    d = ev["lastDeny"] or {}
    return (d != ev["lastDeny0"] and d.get("reason") == "not_your_unit" and not ev["newCtx"],
            f"partner lastDeny {ev['lastDeny0']} -> {d} (want a new not_your_unit); new host contexts {ev['newCtx']} "
            f"(want none); unit {uid} directions host/partner {ev['dirs']}")


# ===================== boot C =====================


def bring_up(host, client):
    m, pre, seated = (host, client), {}, {}

    def lobby():
        host.spawn(); host.connect(); client.spawn(); client.connect()
        host.ok({"cmd": "set_seed", "seed": SEED_ROSTER})
        RAW.skirmish_host(host, KEY)
        RAW.skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": RAW.CLIENT_PLAYER})
        host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
        client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
        host.ok({"cmd": "profile_ok"}); client.ok({"cmd": "profile_ok"})
        host.wait_for("start offered", lambda: RAW.lobby(host).get("buttonVisible") or None)

    def pre_seat(h):
        """After the craft pin: the Skyranger, every crew soldier after the first three off it, one tank on it."""
        r = h.cmd({"cmd": "newbattle_craft", "type": CRAFT})
        assert r.get("ok"), f"newbattle_craft {CRAFT}: {r}"
        br = h.cmd({"cmd": "base_report"})
        sky = [c for c in br.get("crafts") or [] if c.get("type") == CRAFT]
        assert len(sky) == 1, f"base_report crafts {br.get('crafts')} (want exactly one {CRAFT})"
        cid = sky[0]["id"]
        crew = [s["id"] for s in br.get("soldiers") or [] if s.get("craft") == cid]
        pre.update(craft=cid, crew=crew, kept=crew[:3], cut=[])
        for sid in crew[3:]:
            a = h.cmd({"cmd": "craft_assign", "soldier_id": sid, "craft_id": cid, "on": False})
            assert a.get("ok") and a.get("seated") is False, f"craft_assign {sid} off: {a}"
            pre["cut"].append(sid)
        eq = h.cmd({"cmd": "craft_equip", "item": TANK_ITEM, "count": 1, "craft_id": cid})
        assert eq.get("moved") is True, f"craft_equip {TANK_ITEM}: {eq}"
        cv = h.cmd({"cmd": "base_screen_op", "op": "craft_vehicles", "craft_id": cid, "craft_type": CRAFT})
        pre["vehicles"] = cv.get("vehicles")
        assert (cv.get("vehicles") or {}).get(TANK_ITEM) == 1, f"craft_vehicles: {cv}"

    G3F.guarded("C", lobby, m)
    G3F.guarded("C", lambda: session.drive_to_battlescape(
        host, client, seated, mission=MISSION, seat_count=2, pre_seat=pre_seat,
        pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP})), m)
    crash0 = session._crash_log_snapshot()
    hb, cb = battle_state(host), battle_state(client)
    view = {"kept": pre.get("kept"), "seated": seated.get("soldierIds"), "vehicles": pre.get("vehicles"),
            "mapFp": [hb.get("mapFingerprint"), cb.get("mapFingerprint")],
            "sides": [(hb.get("side"), hb.get("turn")), (cb.get("side"), cb.get("turn"))]}
    want = {"kept": KEPT, "seated": [C1, C2], "vehicles": {TANK_ITEM: 1}, "mapFp": [MAP_FP_C, MAP_FP_C],
            "sides": [(0, 1), (0, 1)]}
    def pins():
        assert view == want, f"boot C pins {view} (want {want})"
    G3F.guarded("C", pins, m)
    pinned = G3F.guarded("C", lambda: session.pin_ai_neutral(host, client, tag="r5u4"), m)
    G3F.guarded("C", lambda: G3F.reactions_zero(host, client), m)
    G3F.guarded("C", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    return dict(view, pinned=pinned), crash0


def row_t(host, client, crash0):
    cells, ev = {}, {}
    uh, uc = units(host), units(client)
    tanks = [sorted(i for i, u in g.items() if u.get("type") == TANK_ITEM) for g in (uh, uc)]
    tv = [{k: (g.get(TANK) or {}).get(k) for k in ("originalFaction", "isPlayerSoldier", "coop", "x", "y", "z", "tu")}
          for g in (uh, uc)]
    seats = [[(g.get(i) or {}).get("coop") for i in (H, C1, C2)] for g in (uh, uc)]
    ev.update(tanks=tanks, tank=tv, seatsHC1C2=seats)
    cells["T-gen"] = (tanks == [[TANK], [TANK]] and all(t["originalFaction"] == 0 and t["isPlayerSoldier"] is False
                                                        for t in tv) and seats == [[0, 1, 1], [0, 1, 1]],
                      f"{TANK_ITEM} units host/client {tanks} (want [{TANK}] on both); tank host/client {tv} (want "
                      f"originalFaction 0, isPlayerSoldier false); coop of H, C1, C2 host/client {seats} (want [0, 1, 1])")
    if not cells["T-gen"][0]:
        not_reached(cells, ("T-seat", "T-sel", "T-walk", "T-deny"), "T-gen failed")
    else:
        cells["T-seat"] = both_fields(host, client, TANK, "coop", 0)
        ev["sel"] = tab_select(host, TANK)
        cells["T-sel"] = (ev["sel"], f"tab_select(host, {TANK}) {ev['sel']}, selectedId "
                                     f"{battle_state(host).get('selectedId')} (want {TANK})")
        if cells["T-sel"][0]:
            cells["T-walk"] = host_walk(host, client, TANK, T_DEST, ev.setdefault("walk", {}), end=T_END)
        else:
            not_reached(cells, ("T-walk",), "T-sel failed")
        to = ((units(client).get(TANK) or {}).get("direction", 0) + 2) % 8
        cells["T-deny"] = deny_cell(partner_turn(host, client, TANK, to, ev.setdefault("deny", {"toDir": to})), TANK)
    cells["T-common"] = G3F.common(host, client, crash0)
    return cells, ev


def stage_s(host, client):
    """C1's rifle; H then C1 onto their open-ground tiles; H's spawn staging."""
    m, ev = (host, client), {}
    ev["rifle"] = G3F.guarded("S staging", lambda: give(host, client, C1, "STR_RIFLE", "STR_RIFLE_CLIP")
                              .get("weaponId"), m)
    ev["H"] = G3F.guarded("S staging", lambda: tele(host, client, H, STAGE_H, H_DIR, "r5u4 S victim").get("to"), m)
    ev["C1"] = G3F.guarded("S staging", lambda: tele(host, client, C1, STAGE_C1, C1_DIR, "r5u4 S shooter").get("to"), m)
    ev["spawn"] = G3F.guarded("S staging", lambda: spawn_staging(host, client, H, S_TYPE, 0).get("spawnUnit"), m)
    return ev


def row_s(host, client, crash0, st, out):
    cells, ev = {}, {"staging": st}
    p, new, spawns = convert(host, client, C1, FLOOR_S, SEED_S, ev)
    out["P"] = p
    want = {"type": S_TYPE, "faction": 0, "originalFaction": 0, "isPlayerSoldier": False}
    cells["S-spawn"] = spawn_cell(new, C1, spawns, p, H, host, client, want)
    if not cells["S-spawn"][0]:
        not_reached(cells, ("S-seat", "S-sel", "S-walk", "S-deny"), "S-spawn failed")
    else:
        out["spawned"] = True
        cells["S-seat"] = both_fields(host, client, p, "coop", 0)
        ev["P"] = [{k: (units(gc).get(p) or {}).get(k) for k in ("coop", "hasAI", "tu", "direction")}
                   for gc in (host, client)]
        ev["tu"] = both(host, client, {"cmd": "battle_set_unit_state", "unit": p, "tu": P_TU}, ("tu",)).get("tu")
        cells["S-sel"] = tab_then_click(host, p, ev.setdefault("sel", {}))
        if cells["S-sel"][0]:
            cells["S-walk"] = host_walk(host, client, p, P_DEST, ev.setdefault("walk", {}))
        else:
            G3F.capture("S sel", cells["S-sel"][1], (host, client))
            not_reached(cells, ("S-walk",), "S-sel failed")
        to = ((units(client).get(p) or {}).get("direction", 0) + 2) % 8
        cells["S-deny"] = deny_cell(partner_turn(host, client, p, to, ev.setdefault("deny", {"toDir": to})), p)
    cells["S-common"] = G3F.common(host, client, crash0)
    return cells, ev


def tally(gc):
    t = es(gc, "coopEndTurnTally") or {}
    return {k: t.get(k) for k in ("count", "needed", "ready")}


def side_turn(gc):
    b = battle_state(gc)
    return (b.get("side"), b.get("turn"))


def row_e(host, client, crash0, out):
    cells, ev = {}, {"P": out.get("P")}
    if not out.get("spawned"):
        not_reached(cells, ("E-wait", "E-end"), "S-spawn failed: the host's live units are not the tank and P")
        cells["E-common"] = G3F.common(host, client, crash0)
        return cells, ev
    ev["before"] = [tally(host), tally(client)]
    ev["press"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    snap = {}

    def seen():
        th, tc = tally(host), tally(client)
        if 1 in (th.get("ready") or []) and 1 in (tc.get("ready") or []):
            snap.update(host=th, client=tc, sides=[side_turn(host), side_turn(client)])
            return True
        return False
    ok, ev["waitS"] = wait_until(seen, STEP_S, 0.1)
    ev["snap"], ev["sidesAfter"] = snap, [side_turn(host), side_turn(client)]
    want = {"count": 1, "needed": 2, "ready": [1]}
    cells["E-wait"] = (ok and snap.get("host") == want and snap.get("client") == want
                       and snap.get("sides") == [(0, 1), (0, 1)] and ev["sidesAfter"] == [(0, 1), (0, 1)],
                       f"after the partner's END TURN ({ev['waitS']} s) tally host {snap.get('host')} partner "
                       f"{snap.get('client')} (want {want} on both); (side, turn) at that read {snap.get('sides')} and "
                       f"after it {ev['sidesAfter']} (want (0, 1) on both)")
    ev["banners"] = [{k: battle_state(gc).get(k) for k in ("coopWaitText", "coopEndTurnText")} for gc in (host, client)]
    ev["messages"] = [str(es(gc, "messages"))[:400] for gc in (host, client)]
    if not cells["E-wait"][0]:
        not_reached(cells, ("E-end",), "E-wait failed")
    else:
        ev["sideBefore"] = side_turn(host)
        ev["hostPress"] = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        try:
            drive_side_change(host, client, 1, timeout=STEP_S)
            ev["drive"] = "ok"
        except Exception as e:
            ev["drive"] = str(e)[:300]
        cells["E-end"] = (ev["sideBefore"] == (0, 1) and ev["drive"] == "ok",
                          f"host (side, turn) before its press {ev['sideBefore']} (want (0, 1)); side change to 1 on "
                          f"both: {ev['drive']}")
    try:   # settle before the hash: the AI-pinned alien side passes, X-COM's turn 2 (both builds reach it)
        drive_side_change(host, client, 0, want_turn_min=2, timeout=STEP_S)
        session.wait_host_idle(host, client, timeout=STEP_S)
        ev["settle"] = [side_turn(host), side_turn(client)]
    except Exception as e:
        ev["settle"] = str(e)[:300]
    cells["E-common"] = G3F.common(host, client, crash0)
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("r5u4_c_host"))
    client = GameClient("client", None, make_user_dir("r5u4_c_client"))
    rows, fails = dict(ROWS), 0
    try:
        try:
            boot, crash0 = bring_up(host, client)
            print(f"[r5u4] boot C: {json.dumps(boot, default=str)}", flush=True)
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE C line)")
        else:
            fails += G3F.run_row("T", rows["T"], lambda: row_t(host, client, crash0))
            try:
                st = stage_s(host, client)
            except G3F.Miss:
                st = None
            if st is None:
                fails += G3F.fail_all(ROWS[1:], "staging (see the CAPTURE S staging line)")
            else:
                out = {}
                fails += G3F.run_row("S", rows["S"], lambda: row_s(host, client, crash0, st, out))
                fails += G3F.run_row("E", rows["E"], lambda: row_e(host, client, crash0, out))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_ownerless_units: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
