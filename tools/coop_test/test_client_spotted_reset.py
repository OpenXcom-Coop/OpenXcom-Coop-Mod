"""test_client_spotted_reset.py: on the second player's machine (the thin client) each unit's per-turn "spotted" list
resets at every side change, as vanilla's BattleUnit::prepareNewTurn does on the host, so the alien player's path
preview counts what the host counts. The PvP boot (test_battle_end_rules.boot_pvp: gamemode 2, STR_SMALL_SCOUT, map
seed 1; the host plays the X-COM soldiers, seat 0; the client the only alien A, seat 1), reactions 0 on both, lobby key
49153, dirs client_spotted_reset_host / client_spotted_reset_client.

Staging (side 0 turn 1, by the battle_teleport_unit test command, which runs no FOV on either machine; A first): A on
A_TILE facing A_DIR, S1 in front of it (S1_FRONT), S2 / S3 out of its view, the other soldiers far away; then A's
list [] on both. Every END TURN is real input (battle_action end_turn_button through test_pvp_react_mc.side_change,
which closes every NextTurnState); the walks are the client's real UI (Tab onto A, one left click on the tile).
Rows (a cell's name is <row>-<cell>):
  sees_front    side 1 turn 1: start (A on A_TILE on both, client selection A), list (both lists [S1]), probe
                (path_probe A -> STEP equal), walk (the walk to STEP admitted), common.
  stale_entry   side 1 turn 2, S1 moved behind A at side 0 (the stale entry): start, host (host list []), list (client
                list == host list), probe (path_probe A -> PAST_S1 on the client == the host's), walk (the walk to
                PAST_S1 through S1, a soldier A does not know: admitted, then halted by vanilla's walk interruption as
                STALE_HALT says), common.
  refill_front  side 1 turn 3, S2 moved in front of A at side 0 (the refill after the clear), LAST: start, host (host
                list = REFILL_HOST: what A sees from the facing the stale_entry walk's halt left it), list (client ==
                host), keep (every host id in the client's list), probe, common.
A client that keeps the list across the side change fails stale_entry-list, stale_entry-probe, refill_front-list and
refill_front-probe. A build that denies the walk through S1 (path_changed) instead of letting vanilla's walk
interruption halt it fails stale_entry-walk and refill_front-host.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure; a
precondition (GUARD) miss ends its row and the later rows (cells "not reached"); a boot miss prints ONE CAPTURE line and
fails every row "boot". Common cell: every hash bucket EQUAL, desyncSeen false on both, no new crash file. Ids are read
at run time. Lists are read before any client Tab or click in a row (a selection refreshes the alien's list).
No skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_client_spotted_reset.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
from test_seat_pacing import tab_select, real_click_walk  # noqa: E402
from test_client_shoot import set_tu_both, place  # noqa: E402

KEY = "49153"
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
A_TILE, A_DIR = (15, 8, 0), 4                    # A's staging tile and facing (open on both, every rule met)
STEP = (15, 9, 0)                                # A_TILE + 1 on A_DIR: sees_front's walk
S1_FRONT = (15, 11, 0)                           # A_TILE + 3 on A_DIR, in A's view from A_TILE and STEP
S2_START, S2_DIR = (19, 11, 0), 6                # out of A's view from A_TILE and STEP
S3_START, S3_DIR = (12, 4, 0), 4                 # out of A's view from A_TILE and STEP
FAR = [(33, 33, 0), (34, 33, 0), (35, 33, 0), (36, 33, 0)]   # Chebyshev > 20 from A_TILE
S1_BACK, PAST_S1 = (15, 7, 0), (15, 5, 0)        # STEP + 2 / + 4 on (A_DIR + 4) % 8: S1 behind A, the walk through it
S2_FRONT = (15, 12, 0)                           # STEP + 3 on A_DIR, in A's view, off the STEP -> PAST_S1 line
WALK_S, SETTLE_S = 15, 5.0                       # a walk's answer bound / the read after the click (measured 0.4-1.1 s)
STALE_HALT = ("spot", 3)   # stale_entry's walk halt reason (vanilla's walk interruption) and A's TU spent
REFILL_HOST = ("S1", "S3")   # the st names in the host's refill_front list after that halt
VEC = {0: (0, -1), 1: (1, -1), 2: (1, 0), 3: (1, 1), 4: (0, 1), 5: (-1, 1), 6: (-1, 0), 7: (-1, -1)}
ROWS = (("sees_front", ("sees_front-start", "sees_front-list", "sees_front-probe", "sees_front-walk",
                        "sees_front-common")),
        ("stale_entry", ("stale_entry-start", "stale_entry-host", "stale_entry-list", "stale_entry-probe",
                         "stale_entry-walk", "stale_entry-common")),
        ("refill_front", ("refill_front-start", "refill_front-host", "refill_front-list", "refill_front-keep",
                          "refill_front-probe", "refill_front-common")))


class Precond(Exception):
    """A GUARD (precondition) cell failed: the row ends, later cells and rows are "not reached"."""


def add(p, d, k=1):
    return (p[0] + VEC[d][0] * k, p[1] + VEC[d][1] * k, p[2])


def in_cone(a, adir, t):   # BattleUnit::checkViewSector for a 1x1 unit at a facing adir
    dx, dy = t[0] - a[0], a[1] - t[1]
    return {0: dx + dy >= 0 and dy - dx >= 0, 1: dx >= 0 and dy >= 0, 2: dx + dy >= 0 and dy - dx <= 0,
            3: dy <= 0 and dx >= 0, 4: dx + dy <= 0 and dy - dx <= 0, 5: dx <= 0 and dy <= 0,
            6: dx + dy <= 0 and dy - dx >= 0, 7: dy >= 0 and dx <= 0}[adir]


def open_both(th, tc, t, occupied):
    k = t[:2]
    return (t[2] == 0 and k in th and th.get(k) == tc.get(k) and th[k][0] != -1 and th[k][3] == -1
            and t not in occupied)


def uview(u):
    return {"pos": (u.get("x"), u.get("y"), u.get("z")), "dir": u.get("direction"), "tu": u.get("tu"),
            "visible": u.get("visible"), "faction": u.get("faction"), "isOut": u.get("isOut")}


def census(host, client, st):
    """Both machines' turn / side / selection / top state, A / S1 / S2, A's lists."""
    uh, uc = G3F.units(host), G3F.units(client)
    bh, bc = battle_state(host), battle_state(client)
    c = {"turnSide": [(bh.get("turn"), bh.get("side")), (bc.get("turn"), bc.get("side"))],
         "selectedId": [bh.get("selectedId"), bc.get("selectedId")], "top": [G3F.top(host), G3F.top(client)],
         "listHost": sorted((uh.get(st["A"]) or {}).get("spottedThisTurn") or []),
         "listClient": sorted((uc.get(st["A"]) or {}).get("spottedThisTurn") or [])}
    for n in ("A", "S1", "S2"):
        c[n] = {"host": uview(uh.get(st[n]) or {}), "client": uview(uc.get(st[n]) or {})}
    return c


def probe(gc, uid, dest):   # a private Pathfinding on the same unit, read-only
    r = gc.cmd({"cmd": "path_probe", "unit": uid, "x": dest[0], "y": dest[1], "z": dest[2]})
    return {k: r.get(k) for k in ("ok", "steps", "tuCost", "reachable", "error")}


def probes(host, client, uid, dest):
    return {"dest": dest, "host": probe(host, uid, dest), "client": probe(client, uid, dest)}


def pv(p, m):
    return (p[m].get("steps"), p[m].get("tuCost"), p[m].get("reachable"))


def client_walk(host, client, uid, dest, a_tu):
    """The client's REAL-UI walk of uid to dest: set_tu_both, tab_select, one left click; the
    outcome is the first of a new client lastDeny or a new inactive host lastWalk within WALK_S; reads at SETTLE_S."""
    ev = {"dest": dest, "tuSet": set_tu_both(host, client, uid, a_tu), "tab": tab_select(client, uid)}
    hs0, cs0 = event_state(host), event_state(client)
    prev_walk, deny0 = (hs0.get("lastWalk") or {}).get("actionId", 0), cs0.get("lastDeny")
    t0 = time.time()
    real_click_walk(client, dest)
    ev["outcome"] = None
    while time.time() - t0 < WALK_S:
        d, hw = event_state(client).get("lastDeny"), event_state(host).get("lastWalk") or {}
        if d and d != deny0:
            ev["outcome"] = "deny"
            break
        if hw.get("actionId", 0) != prev_walk and hw.get("active") is False:
            ev["outcome"] = "walk"
            break
        time.sleep(0.2)
    ev["answerS"] = round(time.time() - t0, 2)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    rest = SETTLE_S - (time.time() - t0)
    if rest > 0:
        time.sleep(rest)
    hs, cs = event_state(host), event_state(client)
    hw = hs.get("lastWalk") or {}
    ev["hostLastWalk"] = {k: hw.get(k) for k in ("actionId", "unit", "plannedLen", "executed", "halted", "reason")}
    ev["hostLastWalkIsNew"] = hw.get("actionId", 0) != prev_walk
    ev["clientLastDeny"], ev["clientDenyIsNew"] = cs.get("lastDeny"), cs.get("lastDeny") != deny0
    ev["coopWaitText"] = battle_state(client).get("coopWaitText")
    ev["pos"] = [G3F.pos(host, uid), G3F.pos(client, uid)]
    ev["tu"] = [G3F.units(host)[uid].get("tu"), G3F.units(client)[uid].get("tu")]
    return ev


def need(cells, name, ok, detail):
    cells[name] = (bool(ok), detail)
    if not ok:
        raise Precond(f"precondition {name} failed: {detail}")


def side(host, client, presser, sd, turn, ev, key):
    """RM side_change (closes every NextTurnState); its (turn, side) assert is the caller's precondition."""
    rec, t0 = {}, time.time()
    try:
        RM.side_change(host, client, presser, sd, turn, rec)
        return None
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e)[:400]}"
        return rec["error"]
    finally:
        rec["s"] = round(time.time() - t0, 1)
        ev[key] = rec


def at_both(c, n, tile):
    return c[n]["host"]["pos"] == tile and c[n]["client"]["pos"] == tile


def lists_cells(row, c, want_host, cells):
    lh, lc = c["listHost"], c["listClient"]
    if want_host is not None:
        cells[f"{row}-host"] = (lh == want_host, f"host A list {lh} (want {want_host}: vanilla's clear, then A's sight)")
    cells[f"{row}-list"] = (lc == lh, f"client A list {lc}, host {lh} (want equal: the client resets the list at the "
                                      f"side change as vanilla does)")


def row_sees_front(host, client, crash0, st, cells, ev):
    A, S1 = st["A"], st["S1"]
    err = side(host, client, host, FACTION_HOSTILE, 1, ev, "side")
    c = ev["census"] = census(host, client, st)
    need(cells, "sees_front-start", err is None and at_both(c, "A", A_TILE)
         and c["A"]["host"]["faction"] == FACTION_HOSTILE and c["A"]["client"]["faction"] == FACTION_HOSTILE
         and not c["A"]["host"]["isOut"] and c["selectedId"][1] == A,
         f"side change {err or 'ok'}; (turn, side) host/client {c['turnSide']} (want (1, 1)); A host {c['A']['host']} "
         f"client {c['A']['client']} (want live, faction 1, on {A_TILE}); client selectedId {c['selectedId'][1]} "
         f"(want {A})")
    lh, lc = c["listHost"], c["listClient"]
    cells["sees_front-list"] = (lc == lh == [S1], f"client A list {lc}, host {lh} (want both [{S1}]: S1 in A's view)")
    p = ev["probe"] = probes(host, client, A, STEP)
    cells["sees_front-probe"] = (pv(p, "host") == pv(p, "client") and p["host"].get("ok"),
                                 f"path_probe A -> {STEP} (steps, tuCost, reachable) host {pv(p, 'host')} client "
                                 f"{pv(p, 'client')} (want equal)")
    w = ev["walk"] = client_walk(host, client, A, STEP, st["A_TU"])
    need(cells, "sees_front-walk", w["outcome"] == "walk" and w["pos"] == [STEP, STEP],
         f"walk {STEP}: outcome {w['outcome']} in {w['answerS']} s, A host/client {w['pos']} (want walk, on {STEP} "
         f"on both)")
    cells["sees_front-common"] = G3F.common(host, client, crash0)


def row_stale_entry(host, client, crash0, st, cells, ev):
    A, S1 = st["A"], st["S1"]
    ev["place"] = place(host, client, S1, S1_BACK, 0)
    err = side(host, client, host, FACTION_HOSTILE, 2, ev, "side")
    c = ev["census"] = census(host, client, st)
    need(cells, "stale_entry-start", err is None and at_both(c, "A", STEP) and c["A"]["host"]["dir"] == A_DIR
         and c["A"]["client"]["dir"] == A_DIR and at_both(c, "S1", S1_BACK),
         f"side change {err or 'ok'}; (turn, side) {c['turnSide']} (want (2, 1)); A host {c['A']['host']} client "
         f"{c['A']['client']} (want {STEP} dir {A_DIR}); S1 {c['S1']['host']['pos']} / {c['S1']['client']['pos']} "
         f"(want {S1_BACK})")
    lists_cells("stale_entry", c, [], cells)
    p = ev["probe"] = probes(host, client, A, PAST_S1)
    cells["stale_entry-probe"] = (pv(p, "client")[:2] == pv(p, "host")[:2] and p["host"].get("ok"),
                                  f"path_probe A -> {PAST_S1} (steps, tuCost) client {pv(p, 'client')[:2]} host "
                                  f"{pv(p, 'host')[:2]} (want equal: the client's preview counts what the host "
                                  f"counts)")
    w = ev["walk"] = client_walk(host, client, A, PAST_S1, st["A_TU"])
    hw, tu_want = w["hostLastWalk"], st["A_TU"] - STALE_HALT[1]
    cells["stale_entry-walk"] = (not w["clientDenyIsNew"] and w["hostLastWalkIsNew"] and hw.get("unit") == A
                                 and hw.get("halted") is True and hw.get("reason") == STALE_HALT[0]
                                 and w["pos"] == [STEP, STEP] and w["tu"] == [tu_want] * 2,
                                 f"walk {PAST_S1}: new client lastDeny {w['clientDenyIsNew']} {w['clientLastDeny']} "
                                 f"(want none); host lastWalk new {w['hostLastWalkIsNew']} {hw} (want a new walk of A "
                                 f"halted {STALE_HALT[0]!r}: vanilla's walk interruption); A {w['pos']} TU {w['tu']} "
                                 f"(want {STEP}, {tu_want} on both)")
    cells["stale_entry-common"] = G3F.common(host, client, crash0)


def row_refill_front(host, client, crash0, st, cells, ev):
    A, S2 = st["A"], st["S2"]
    ev["place"] = place(host, client, S2, S2_FRONT, 0)
    err = side(host, client, host, FACTION_HOSTILE, 3, ev, "side")
    c = ev["census"] = census(host, client, st)
    need(cells, "refill_front-start", err is None and at_both(c, "A", STEP) and at_both(c, "S1", S1_BACK)
         and at_both(c, "S2", S2_FRONT),
         f"side change {err or 'ok'}; (turn, side) {c['turnSide']} (want (3, 1)); A {c['A']['host']['pos']} / "
         f"{c['A']['client']['pos']} (want {STEP}); S1 {c['S1']['host']['pos']} / {c['S1']['client']['pos']} (want "
         f"{S1_BACK}); S2 {c['S2']['host']['pos']} / {c['S2']['client']['pos']} (want {S2_FRONT})")
    lists_cells("refill_front", c, sorted(st[n] for n in REFILL_HOST), cells)
    miss = sorted(set(c["listHost"]) - set(c["listClient"]))
    cells["refill_front-keep"] = (not miss, f"host ids missing from the client's list {miss} (want none: the refill "
                                            f"keeps what A sees now)")
    p = ev["probe"] = probes(host, client, A, PAST_S1)
    cells["refill_front-probe"] = (pv(p, "client")[:2] == pv(p, "host")[:2] and p["host"].get("ok"),
                                   f"path_probe A -> {PAST_S1} (steps, tuCost) client {pv(p, 'client')[:2]} host "
                                   f"{pv(p, 'host')[:2]} (want equal)")
    cells["refill_front-common"] = G3F.common(host, client, crash0)


def row(fn, host, client, crash0, st):
    """(cells, ev) for G3F.run_row: cells set before an exception are kept; a precondition miss (or any other
    exception, after which the fixture state is unknown) ends the later rows."""
    def run():
        cells, ev = {}, {}
        try:
            fn(host, client, crash0, st, cells, ev)
        except Exception as e:
            ev["error"] = f"{type(e).__name__}: {str(e)[:600]}"
            st["stop"] = ev["error"]
        return cells, ev
    return run


def stage(host, client, st):
    """Ids by rule, every pinned tile open on both (and in / out of A's view as the table says), then `place`
    (A first); A's list [] on both. Returns None, or the miss."""
    hostile = [u["id"] for u in battle_state(client).get("units", [])
               if u.get("coop") == 1 and u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]
    seat0 = [u["id"] for u in battle_state(host).get("units", [])
             if u.get("coop") == 0 and u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
    if len(hostile) != 1 or len(seat0) != 3 + len(FAR):
        return f"client seat live hostiles {hostile} (want exactly one), seat-0 live soldiers {seat0} (want {3 + len(FAR)})"
    st.update(A=hostile[0], S1=seat0[0], S2=seat0[1], S3=seat0[2], FAR=seat0[3:])
    st["A_TU"] = G3F.units(host)[st["A"]]["tu"]
    th, tc = RM.tile_parts(host), RM.tile_parts(client)
    occ = {(u.get("x"), u.get("y"), u.get("z")) for u in battle_state(host).get("units", []) if not u.get("isOut")}
    tiles = [A_TILE, STEP, S1_FRONT, S2_START, S3_START, S1_BACK, PAST_S1, S2_FRONT] + FAR
    shut_ = [t for t in tiles if not open_both(th, tc, t, occ)]
    view = {"S1inStart": in_cone(A_TILE, A_DIR, S1_FRONT), "S1inStep": in_cone(STEP, A_DIR, S1_FRONT),
            "S2out": not in_cone(A_TILE, A_DIR, S2_START) and not in_cone(STEP, A_DIR, S2_START),
            "S3out": not in_cone(A_TILE, A_DIR, S3_START) and not in_cone(STEP, A_DIR, S3_START),
            "S1backOut": not in_cone(STEP, A_DIR, S1_BACK), "S2frontIn": in_cone(STEP, A_DIR, S2_FRONT),
            "pastS1Line": [add(STEP, (A_DIR + 4) % 8, k) for k in (2, 4)] == [S1_BACK, PAST_S1]}
    st["staging"] = {"ids": {k: st[k] for k in ("A", "S1", "S2", "S3", "FAR", "A_TU")}, "notOpen": shut_, "view": view}
    if th != tc or shut_ or not all(view.values()):
        return f"tiles equal {th == tc}, not open on both {shut_}, view rules {view}"
    st["placed"] = {st["A"]: place(host, client, st["A"], A_TILE, A_DIR),
                    st["S1"]: place(host, client, st["S1"], S1_FRONT, 0),
                    st["S2"]: place(host, client, st["S2"], S2_START, S2_DIR),
                    st["S3"]: place(host, client, st["S3"], S3_START, S3_DIR)}
    for uid, t in zip(st["FAR"], FAR):
        st["placed"][uid] = place(host, client, uid, t, 0)
    c = st["stagedCensus"] = census(host, client, st)
    if c["listHost"] or c["listClient"] or not at_both(c, "A", A_TILE) or not at_both(c, "S1", S1_FRONT):
        return (f"after staging: {json.dumps(c, default=str)} (want A on {A_TILE}, S1 on {S1_FRONT}, A's lists [] "
                f"on both)")
    return None


def run_all(host, client):
    """The PvP boot, staging, then sees_front, (client END TURN) stale_entry, (client END TURN) refill_front; returns
    the failed cell count."""
    rows, fails, st = dict(ROWS), 0, {}
    try:
        boot = BER.boot_pvp(host, client, KEY)
        crash0 = session._crash_log_snapshot()
        boot["reactions"] = G3F.reactions_zero(host, client)
        print(f"[spotted_reset] boot pvp: {json.dumps(boot, default=str)}", flush=True)
    except Exception as e:
        G3F.capture("pvp", f"{type(e).__name__}: {str(e)[:600]}", (host, client))
        return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE pvp line)")
    try:
        miss = stage(host, client, st)
    except Exception as e:
        miss = f"{type(e).__name__}: {str(e)[:600]}"
    print(f"[spotted_reset] staging: {json.dumps({k: st.get(k) for k in ('staging', 'placed')}, default=str)}",
          flush=True)
    if miss:
        G3F.capture("staging", miss, (host, client))
        return G3F.fail_all(ROWS, f"staging: {miss[:300]}")
    fails += G3F.run_row("sees_front", rows["sees_front"], row(row_sees_front, host, client, crash0, st))
    for name, turn, fn in (("stale_entry", 2, row_stale_entry), ("refill_front", 3, row_refill_front)):
        if not st.get("stop"):
            ev = {}
            err = side(host, client, client, FACTION_PLAYER, turn, ev, f"clientEndTurn{turn}")
            print(f"[spotted_reset] client END TURN -> side 0 turn {turn}: {json.dumps(ev, default=str)}", flush=True)
            if err:
                st["stop"] = f"client END TURN to side 0 turn {turn}: {err}"
        if st.get("stop"):
            fails += G3F.verdict(name, rows[name], {}, {"error": f"an earlier step missed: {st['stop'][:300]}"})
        else:
            fails += G3F.run_row(name, rows[name], row(fn, host, client, crash0, st))
    return fails


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("client_spotted_reset_host"))
    client = GameClient("client", None, make_user_dir("client_spotted_reset_client"))
    fails = 1
    try:
        fails = run_all(host, client)
    finally:
        G3F.shut(host, client)
        print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
        print(f"test_client_spotted_reset: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
