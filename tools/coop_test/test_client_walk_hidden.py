"""test_client_walk_hidden.py: a walk into a unit the walker cannot see is left to vanilla's walk interruption. The
walk starts, and stops when the unit is spotted or blocks the next step, with TU spent only for what was done. The
host's own walks do that; the second player's walk (the thin client's, checked by the host's validateWalk) does the
same instead of being refused up front with "Order cancelled - path blocked", which would tell the walker where a unit
it cannot see stands.
Classic terror boot (test_client_shoot.boot: STR_TERROR_MISSION, map seed 1, client seats 8 / 9, host seat 10,
pin_ai_neutral), its PORT set to lobby key 49155, dirs client_walk_hidden_host / client_walk_hidden_client, reactions
0 on both.

Staging (side 0 turn 1, by the battle_teleport_unit test command, which runs no FOV on either machine): the map census
on both machines, the lane T..T+4d and the side line TS..TS+4d (TS = T+s) open on both, every live X-COM unit but H
within 20 tiles of T parked >= 21 tiles from T and TS, then H on T facing FACE (away from the lane) and U1 on T+2d.
The HIDDEN set = live faction 1 units, armorSize 1, visible false on both, in no live X-COM unit's visibleUnits or
spottedThisTurn on either machine; U1 / U2 / U3 = its lowest unused id, read at the start of each row. Every walk is
real input: the host's (Tab onto H, one left click) and the client's (Tab onto C, one left click).
Rows (a cell's name is <row>-<cell>):
  host_baseline  the host's own walk T -> D through the hidden U1 (vanilla's behaviour): start, walk (one host walk
                 context; halted HALT, H unmoved, TU spent HALT[1], lastSpot {H, [U1]}), common.
  client_halted  the client's walk T -> D through the hidden U2: start, admit (no deny; one intent walk context), halt
                 (halted HALT as in host_baseline, C unmoved, TU spent HALT[1], lastSpot {C, [U2]}), text (the halt
                 banner), common.
  client_beside  the client's walk TS -> DS beside the hidden U3 (control), LAST: start, admit (any halt), common.
A build that refuses the client's walk up front (a path_changed deny) fails client_halted-admit, client_halted-halt
and client_halted-text.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure; a
precondition (<row>-start) miss ends its row and the later rows (cells "not reached"); a boot or staging miss prints
ONE CAPTURE line and fails every row. Common cell: every hash bucket EQUAL, desyncSeen false on both, no new crash
file. Ids are read at run time. No skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_client_walk_hidden.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import test_client_shoot as CS  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
from test_seat_pacing import tab_select, real_click_walk  # noqa: E402

KEY = "49155"
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
T, D_DIR, FACE = (22, 26, 0), 2, 6               # the lane's start and direction; the walkers face away from it
S_DIR = 4                                        # the side line T+s (y 27), open on both
HALT = ("spot", 3)                               # the halt reason and TU spent: 3 octants x turn cost 1
TEXT = {"spot": "Order cancelled - enemy spotted", "blocked": "Move stopped - path blocked"}
PARK_MIN, PARK_GAP, NEAR = 21, 2, 20             # PARK: Chebyshev >= 21 from T and TS, >= 2 apart
TU_MAX = 255                                     # battle_set_unit_state tu clamps to the unit's full TU
WALK_S, SETTLE_S = 15, 5.0                       # a walk's answer bound / the read after the click
VEC = {0: (0, -1), 1: (1, -1), 2: (1, 0), 3: (1, 1), 4: (0, 1), 5: (-1, 1), 6: (-1, 0), 7: (-1, -1)}
ROWS = (("host_baseline", ("host_baseline-start", "host_baseline-walk", "host_baseline-common")),
        ("client_halted", ("client_halted-start", "client_halted-admit", "client_halted-halt", "client_halted-text",
                           "client_halted-common")),
        ("client_beside", ("client_beside-start", "client_beside-admit", "client_beside-common")))


class Precond(Exception):
    """A <row>-start (precondition) cell failed: the row ends, later cells and rows are "not reached"."""


def add(p, d, k=1):   # copied from test_client_spotted_reset.py
    return (p[0] + VEC[d][0] * k, p[1] + VEC[d][1] * k, p[2])


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


D, U_TILE, TS = add(T, D_DIR, 4), add(T, D_DIR, 2), add(T, S_DIR)
DS = add(TS, D_DIR, 4)


def units(gc):
    return {u["id"]: u for u in battle_state(gc).get("units", [])}


def upos(u):
    return (u.get("x"), u.get("y"), u.get("z")) if u else None


def uview(u):
    return {"pos": upos(u), "dir": u.get("direction"), "tu": u.get("tu"), "visible": u.get("visible"),
            "faction": u.get("faction"), "isOut": u.get("isOut")}


def census(gc, sx, sy):
    """{(x, y): (floor, west, north, object) (mapDataID, mapDataSetID)} at z 0, boxes of <= 4096 tiles."""
    out, rows = {}, max(1, 4096 // sx)
    for y0 in range(0, sy, rows):
        r = gc.ok({"cmd": "tile_census", "x0": 0, "x1": sx - 1, "y0": y0, "y1": min(sy - 1, y0 + rows - 1),
                   "z0": 0, "z1": 0})
        for t in r["tiles"]:
            if t:
                out[(t["x"], t["y"])] = tuple((t["parts"][p]["mapDataID"], t["parts"][p]["mapDataSetID"])
                                              for p in ("floor", "westwall", "northwall", "object"))
    return out


def occupied(host, client):
    occ = set()
    for gc in (host, client):
        for u in battle_state(gc).get("units", []):
            if not u.get("isOut") and u.get("x") is not None:
                n = u.get("armorSize") or 1
                occ.update((u["x"] + i, u["y"] + j, u["z"]) for i in range(n) for j in range(n))
    return occ


def open_both(th, tc, t, occ):   # test_client_spotted_reset's open_both on the four parts
    k = t[:2]
    return (t[2] == 0 and k in th and th.get(k) == tc.get(k) and th[k][0][0] != -1 and th[k][3][0] == -1
            and t not in occ)


def hidden_set(host, client):
    uh, uc = units(host), units(client)
    seen = set()
    for us in (uh, uc):
        for u in us.values():
            if u.get("faction") == FACTION_PLAYER and not u.get("isOut"):
                seen.update(u.get("visibleUnits") or [])
                seen.update(u.get("spottedThisTurn") or [])
    return sorted(i for i, u in uh.items() if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")
                  and (u.get("armorSize") or 1) == 1 and u.get("visible") is False
                  and (uc.get(i) or {}).get("visible") is False and i not in seen)


def near_xcom(host, but):
    return sorted(i for i, u in units(host).items() if u.get("faction") == FACTION_PLAYER and not u.get("isOut")
                  and i != but and upos(u) and cheb(upos(u), T) <= NEAR)


def probe(gc, uid, dest):   # copied from test_client_spotted_reset.py
    r = gc.cmd({"cmd": "path_probe", "unit": uid, "x": dest[0], "y": dest[1], "z": dest[2]})
    return {k: r.get(k) for k in ("ok", "steps", "tuCost", "reachable", "error")}


def straight(host, client, w, a, b):
    """W on a: path_probe w -> b steps 4 on both, (steps, tuCost) equal, tuCost == 4 x w -> a+d's."""
    pb = {"host": probe(host, w, b), "client": probe(client, w, b)}
    p1 = {m: probe(gc, w, add(a, D_DIR)) for m, gc in (("host", host), ("client", client))}
    ok = all(pb[m].get("steps") == 4 and pb[m].get("reachable") and p1[m].get("tuCost") is not None
             and pb[m].get("tuCost") == 4 * p1[m]["tuCost"] for m in pb)
    ok = ok and (pb["host"]["steps"], pb["host"]["tuCost"]) == (pb["client"]["steps"], pb["client"]["tuCost"])
    return ok, {"to": b, "probe": pb, "oneStep": {m: p1[m].get("tuCost") for m in p1}}


def staged(host, client, ids):
    uh, uc = units(host), units(client)
    return {i: {"host": uview(uh.get(i) or {}), "client": uview(uc.get(i) or {})} for i in ids}


def screen(host, client):
    return {gc.name: {"turnSide": (battle_state(gc).get("turn"), battle_state(gc).get("side")),
                      "selectedId": battle_state(gc).get("selectedId"), "top": G3F.top(gc)} for gc in (host, client)}


def walkrec(host, client, w, u, ctx0):
    hs = event_state(host)
    uh, uc = units(host), units(client)
    return {"pos": [upos(uh.get(w)), upos(uc.get(w))], "dir": [uh[w].get("direction"), uc[w].get("direction")],
            "tu": [uh[w].get("tu"), uc[w].get("tu")], "hostLastWalk": hs.get("lastWalk") or {},
            "hostLastSpot": hs.get("lastSpot") or {}, "uVisible": [uh[u].get("visible"), uc[u].get("visible")],
            "coopWaitText": [battle_state(host).get("coopWaitText"), battle_state(client).get("coopWaitText")],
            "newCtx": CS.new_contexts(ctx0, RM.ctxs(host))}


def client_walk(host, client, uid, dest):
    """The client's REAL-UI walk of uid to dest (as in test_client_spotted_reset.py): set_tu_both, tab_select, one
    left click; the outcome is the first of a new client lastDeny or a new inactive host lastWalk within WALK_S; reads
    at SETTLE_S."""
    ev = {"dest": dest, "tuSet": CS.set_tu_both(host, client, uid, TU_MAX), "tab": tab_select(client, uid)}
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
    hw, cs = event_state(host).get("lastWalk") or {}, event_state(client)
    ev["hostLastWalkIsNew"] = hw.get("actionId", 0) != prev_walk
    ev["clientLastDeny"], ev["clientDenyIsNew"] = cs.get("lastDeny"), cs.get("lastDeny") != deny0
    return ev


def need(cells, name, ok, detail):
    cells[name] = (bool(ok), detail)
    if not ok:
        raise Precond(f"precondition {name} failed: {detail}")


def next_u(host, client, st):
    """The lowest id of the HIDDEN set no earlier row used (the row's U), or None."""
    free = [i for i in hidden_set(host, client) if i not in st["used"]]
    if free:
        st["used"].append(free[0])
    return free[0] if free else None


def start_cell(host, client, row, w, a, u, b, cells, ev, extra_ok=True, extra=""):
    c = ev["start"] = {"staged": staged(host, client, [w] + ([u] if u else [])), "screen": screen(host, client),
                       "hidden": hidden_set(host, client), "near": near_xcom(host, w)}
    ok_s, ev["straight"] = straight(host, client, w, a, b) if u else (False, None)
    s = c["staged"]
    at = u is not None and all(s[w][m]["pos"] == a and s[w][m]["dir"] == FACE and s[u][m]["pos"] == U_TILE
                               for m in ("host", "client"))
    need(cells, f"{row}-start", at and u in c["hidden"] and (row == "client_beside" or not c["near"]) and ok_s
         and extra_ok,
         f"walker {w} on {a} facing {FACE} and U {u} on {U_TILE} on both: {at} ({s}); hidden(U) {u in c['hidden']} "
         f"(set {c['hidden']}); X-COM within {NEAR} of {T} {c['near']} (want none); straight {ok_s} "
         f"({ev['straight']}){extra}")


def halt_cells(row, w, u, full, rec):
    hw, sp = rec["hostLastWalk"], rec["hostLastSpot"]
    return (hw.get("halted") is True and hw.get("reason") == HALT[0] and rec["pos"] == [T, T]
            and rec["tu"] == [full - HALT[1]] * 2 and sp.get("unit") == w and sp.get("seen") == [u]
            and sp.get("actionId") == hw.get("actionId"),
            f"host lastWalk halted {hw.get('halted')} reason {hw.get('reason')!r} (want True, {HALT[0]!r}); walker "
            f"{w} {rec['pos']} TU {rec['tu']} (want {T}, {full - HALT[1]} on both); host lastSpot {sp} (want unit {w}, "
            f"seen [{u}], this walk's actionId {hw.get('actionId')})")


def row_host_baseline_u1(host, client, crash0, st, cells, ev):
    H, U1 = CS.H_ID, st["U1"]
    full = ev["tuFull"] = CS.set_tu_both(host, client, H, TU_MAX)
    tab = ev["tab"] = tab_select(host, H)
    tus = [units(host)[H].get("tu"), units(client)[H].get("tu")]
    start_cell(host, client, "host_baseline", H, T, U1, D, cells, ev, tab and tus == [full] * 2,
               f"; H TU {tus} (want {full} on both); tab_select(host, H) {tab}")
    ctx0 = RM.ctxs(host)
    wev = ev["walk"] = {}
    RM.host_walk(host, client, H, D, wev)
    rec = ev["walkrec"] = walkrec(host, client, H, U1, ctx0)
    hw = rec["hostLastWalk"]
    ok_c = RM.ctx_ok(rec["newCtx"], "host", "walk", H)
    ok_h, det = halt_cells("host_baseline", H, U1, full, rec)
    cells["host_baseline-walk"] = (ok_c and hw.get("unit") == H and hw.get("origin") == "host" and ok_h,
                        f"new host contexts {[RM.cv(c) for c in rec['newCtx']]} (want exactly one {{host, walk, {H}}}); "
                        f"lastWalk unit {hw.get('unit')} origin {hw.get('origin')!r} (want {H}, 'host'); {det}")
    cells["host_baseline-common"] = G3F.common(host, client, crash0)


def row_client_halted_u2(host, client, crash0, st, cells, ev):
    C, U2 = CS.C_ID, st["U2"]
    start_cell(host, client, "client_halted", C, T, U2, D, cells, ev)
    ctx0 = RM.ctxs(host)
    w = ev["walk"] = client_walk(host, client, C, D)
    rec = ev["walkrec"] = walkrec(host, client, C, U2, ctx0)
    hw = rec["hostLastWalk"]
    new_walk = w["hostLastWalkIsNew"] and hw.get("unit") == C
    cells["client_halted-admit"] = (not w["clientDenyIsNew"] and new_walk and hw.get("origin") == "intent"
                         and RM.ctx_ok(rec["newCtx"], "intent", "walk", C),
                         f"walk {D}: outcome {w['outcome']} in {w['answerS']} s; new client lastDeny {w['clientDenyIsNew']} "
                         f"{w['clientLastDeny']} (want none); host lastWalk new {w['hostLastWalkIsNew']} unit "
                         f"{hw.get('unit')} origin {hw.get('origin')!r} (want a new walk of {C}, 'intent'); new host "
                         f"contexts {[RM.cv(c) for c in rec['newCtx']]} (want exactly one {{intent, walk, {C}}})")
    ok_h, det = halt_cells("client_halted", C, U2, w["tuSet"], rec)
    cells["client_halted-halt"] = (new_walk and ok_h,
                                   f"new host walk of {C} {new_walk}; {det} (the host's own host_baseline outcome)")
    want = TEXT[HALT[0]]
    cells["client_halted-text"] = (rec["coopWaitText"][1] == want,
                                   f"client coopWaitText {rec['coopWaitText'][1]!r} (want {want!r})")
    cells["client_halted-common"] = G3F.common(host, client, crash0)


def row_client_beside_u3(host, client, crash0, st, cells, ev):
    C, U3 = CS.C_ID, st["U3"]
    start_cell(host, client, "client_beside", C, TS, U3, DS, cells, ev)
    ctx0 = RM.ctxs(host)
    w = ev["walk"] = client_walk(host, client, C, DS)
    rec = ev["walkrec"] = walkrec(host, client, C, U3, ctx0)
    hw = rec["hostLastWalk"]
    cells["client_beside-admit"] = (not w["clientDenyIsNew"] and w["hostLastWalkIsNew"] and hw.get("unit") == C
                         and hw.get("origin") == "intent" and RM.ctx_ok(rec["newCtx"], "intent", "walk", C),
                         f"walk {DS}: outcome {w['outcome']} in {w['answerS']} s; new client lastDeny "
                         f"{w['clientDenyIsNew']} {w['clientLastDeny']} (want none); host lastWalk new "
                         f"{w['hostLastWalkIsNew']} {({k: hw.get(k) for k in ('unit', 'origin', 'halted', 'reason')})} "
                         f"(want a new walk of {C}, 'intent', any halt); new host contexts "
                         f"{[RM.cv(c) for c in rec['newCtx']]} (want exactly one {{intent, walk, {C}}})")
    cells["client_beside-common"] = G3F.common(host, client, crash0)


def between(host, client, st, row):
    """The staging between rows: park the previous row's units, place the next row's walker and U."""
    rec = {}
    if row == "client_halted":
        for uid in (CS.H_ID, st["U1"]):
            rec[uid] = CS.place(host, client, uid, st["park"].pop(0), 0)
        st["U2"] = next_u(host, client, st)
        if st["U2"] is not None:
            rec[st["U2"]] = CS.place(host, client, st["U2"], U_TILE, FACE)
        rec[CS.C_ID] = CS.place(host, client, CS.C_ID, T, FACE)
    else:
        rec[st["U2"]] = CS.place(host, client, st["U2"], st["park"].pop(0), 0)
        rec[CS.C_ID] = CS.place(host, client, CS.C_ID, TS, FACE)
        st["U3"] = next_u(host, client, st)
        if st["U3"] is not None:
            rec[st["U3"]] = CS.place(host, client, st["U3"], U_TILE, FACE)
    return rec


def stage(host, client, st):
    """Map census, PARK by rule, the X-COM near T parked, the lane and side line open on both, H on T and U1 on
    T+2d. Returns None, or the miss."""
    fd = host.ok({"cmd": "find_doors"})
    sx, sy = fd["mapSizeX"], fd["mapSizeY"]
    th, tc = census(host, sx, sy), census(client, sx, sy)
    occ = occupied(host, client)
    near = near_xcom(host, CS.H_ID)
    big = [i for i in near if (units(host)[i].get("armorSize") or 1) > 1]
    cand = sorted((t for t in ((x, y, 0) for (x, y) in th) if open_both(th, tc, t, occ)
                   and cheb(t, T) >= PARK_MIN and cheb(t, TS) >= PARK_MIN), key=lambda t: (-cheb(t, T), t[1], t[0]))
    park = []
    for t in cand:
        if all(cheb(t, x) >= PARK_GAP for x in park):
            park.append(t)
    need_n = len(near) + 3
    st["staging"] = {"map": [sx, sy], "censusEqual": th == tc, "near": near, "park": park[:need_n], "big": big}
    if big or len(park) < need_n:
        return f"near X-COM armorSize > 1 {big}; PARK tiles {len(park)} (want >= {need_n})"
    st["park"] = park[:need_n]
    st["parked"] = {i: CS.place(host, client, i, st["park"].pop(0), 0) for i in near}
    occ = occupied(host, client)
    lane = [add(T, D_DIR, k) for k in range(5)] + [add(TS, D_DIR, k) for k in range(5)]
    shut_ = [t for t in lane if not open_both(th, tc, t, occ)]
    st["staging"]["notOpen"] = shut_
    if shut_:
        return f"lane / side line tiles not open on both {shut_}"
    st["used"] = []
    st["U1"] = next_u(host, client, st)
    if st["U1"] is None:
        return f"no hidden hostile (HIDDEN set {hidden_set(host, client)})"
    st["parked"][st["U1"]] = CS.place(host, client, st["U1"], U_TILE, FACE)
    st["parked"][CS.H_ID] = CS.place(host, client, CS.H_ID, T, FACE)
    st["lastParking"] = st["parked"]
    return None


def row(fn, host, client, crash0, st):
    """(cells, ev) for G3F.run_row: cells set before an exception are kept; a precondition miss (or any other
    exception, after which the fixture state is unknown) ends the later rows."""
    def run():
        # the row function's name ends in its hidden unit's digit: row_..._u1 reads st["U1"]
        cells, ev = {}, {"U": st.get("U" + fn.__name__[-1]), "parking": st.get("lastParking")}
        try:
            fn(host, client, crash0, st, cells, ev)
        except Exception as e:
            ev["error"] = f"{type(e).__name__}: {str(e)[:600]}"
            st["stop"] = ev["error"]
        return cells, ev
    return run


def run_all(host, client):
    """Boot, staging, then host_baseline, client_halted, client_beside; returns the failed cell count."""
    rows, fails, st = dict(ROWS), 0, {}
    try:
        CS.PORT = KEY
        CS.boot(host, client)
        crash0 = session._crash_log_snapshot()
        reactions = G3F.reactions_zero(host, client)
        print(f"[walk_hidden] boot: reactions 0 on {len(reactions)} units; screen {json.dumps(screen(host, client))}",
              flush=True)
    except Exception as e:
        G3F.capture("boot", f"{type(e).__name__}: {str(e)[:600]}", (host, client))
        return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
    try:
        miss = stage(host, client, st)
    except Exception as e:
        miss = f"{type(e).__name__}: {str(e)[:600]}"
    print(f"[walk_hidden] staging: {json.dumps({k: st.get(k) for k in ('staging', 'parked', 'U1')}, default=str)}",
          flush=True)
    if miss:
        G3F.capture("staging", miss, (host, client))
        return G3F.fail_all(ROWS, f"staging: {miss[:300]}")
    fails += G3F.run_row("host_baseline", rows["host_baseline"], row(row_host_baseline_u1, host, client, crash0, st))
    for name, fn in (("client_halted", row_client_halted_u2), ("client_beside", row_client_beside_u3)):
        if not st.get("stop"):
            try:
                st["lastParking"] = between(host, client, st, name)
            except Exception as e:
                st["stop"] = f"staging {name}: {type(e).__name__}: {str(e)[:300]}"
        if st.get("stop"):
            fails += G3F.verdict(name, rows[name], {}, {"error": f"an earlier step missed: {st['stop'][:300]}"})
        else:
            fails += G3F.run_row(name, rows[name], row(fn, host, client, crash0, st))
    return fails


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("client_walk_hidden_host"))
    client = GameClient("client", None, make_user_dir("client_walk_hidden_client"))
    fails = 1
    try:
        fails = run_all(host, client)
    finally:
        G3F.shut(host, client)
        print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
        print(f"test_client_walk_hidden: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
