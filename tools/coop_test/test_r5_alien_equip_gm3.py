"""R5-U6 S-D rows AG1-AG7 (boot DG, gm3 Small Scout: the HOST plays the aliens, seat 0; the client the seven X-COM
soldiers, seat 1; default options, so "Enable XCOM Equipment for Aliens in PVP" is on): the gm3 alien host equips its own
aliens on the pre-battle screen from the ONE X-COM craft pile both sides share, no refusal, the aliens' starting gear stays
in their hands, and after the equip screen every drop lands on the dropping unit's own tile (owner D236 (b), D274 and its
2026-10-13 confirmation, R-U6-OF3, QU6-6 (a)).

Spec: docs repo rewrite/prompts/r5u6_pvp_options.md AMENDMENT U6-1.5.7 (f') with U6-1.7's run-time rules and the orchestrator
ruling R-U6-SD-1 (D-1 the drop cell on the pile: the first free ground cell in column-major order where the item fits; D-2
PISTOL: the first A_START item whose type is not on the pile; D-3: event_state.equip has no `noScreen` field, so AG1-screen
reads the host log line "[coop-equip] nothing to equip on this machine" (the only noScreen writer's own line) == 0 in the
host's openxcom.log). Constants: docs repo rewrite/r5u6-task0/sd/CONSTANTS.md (TASK 0 boots DGa, DGb, DGc). No id is pinned.
Helpers: test_r5_alien_equip.py (the gm2 file of this stage).

Boot DG (key 49066): set_seed 1, pvp_fixture.start_pvp_skirmish_lobby(alien_player="host") (gamemode 3), the PSR drive without
its last line; both briefings; R0 on each machine (A = the host seat's first unit with items); the host's briefing OK (a bounded
wait for its top); the client's briefing closed -> its screen on C1 (PILE_IDS = G(client) at its open); CENSUS0.
  AG1  the host alien's screen and its own gear: AG1-counted, AG1-screen, AG1-ground, AG1-gear
  AG2  the host alien takes RIFLE into BACKPACK_CELL (host-local real UI): AG2-held, AG2-gone
  AG3  the host alien's own PISTOL goes on the shared pile: AG3-pile, AG3-seen
  AG4  the X-COM player takes it onto C1_CELL (the client's real UI): AG4-order, AG4-held, AG4-gone
  AG5  turn 1 (the client's OK, the host's OK where its screen is up): AG5-turn, AG5-held, AG5-census
  AG6  a soldier's turn-1 drop lands on its own tile (the client's IV5-shaped drop): AG6-ground, AG6-order, AG6-tile
  AG7  an alien's turn-1 drop lands on its own tile (the client's END TURN, the host's drop): AG7-ground, AG7-tile
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new lane crash file.

RED on the unchanged build (commit D1): AG1-counted, AG1-screen, AG1-ground, AG2-held, AG2-gone, AG3-pile, AG3-seen, AG4-order,
AG4-held, AG4-gone, AG5-held; every other cell PASS. One EVIDENCE line per row, one PASS/FAIL line per cell, then the row
verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails every row "boot"; a
staging step past its bound fails that row "staging". WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run
is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_r5_alien_equip_gm3.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_r5_pvp_gm3 as G3F  # noqa: E402
import test_r5_pvp_react_mc as RM  # noqa: E402
import test_w2_prebattle_equip as PEQ  # noqa: E402
import test_r5_alien_equip as AE  # noqa: E402

KEY = "49066"
N_NOTHING = "[coop-equip] nothing to equip on this machine"   # D-3: the host's no-screen branch's own log line
SEL_AFTER_ENTRY = -1              # the host's selectedId after the equip entry (W2-H36; TASK 0 DGa, DGb)
BACK, LH = AE.BACK, AE.LH
ROWS = (("AG1", ("AG1-counted", "AG1-screen", "AG1-ground", "AG1-gear", "AG1-common")),
        ("AG2", ("AG2-held", "AG2-gone", "AG2-common")),
        ("AG3", ("AG3-pile", "AG3-seen", "AG3-common")),
        ("AG4", ("AG4-order", "AG4-held", "AG4-gone", "AG4-common")),
        ("AG5", ("AG5-turn", "AG5-held", "AG5-census", "AG5-common")),
        ("AG6", ("AG6-ground", "AG6-order", "AG6-tile", "AG6-common")),
        ("AG7", ("AG7-ground", "AG7-tile", "AG7-common")))


def log_path(gc):
    return os.path.join(gc.user_dir, "openxcom.log")


def setup_dg(host, client):
    m = (host, client)
    ctx = AE.bring_up(host, client, KEY, "host", "DG", 0)
    ctx["nothingBefore"] = G3F.log_count(host, N_NOTHING)
    G3F.guarded("DG", lambda: host.ok({"cmd": "click_widget", "match": "ok"}), m)
    _, ctx["hostTopS"] = AE.wait_until(lambda: G3F.top(host) in ("InventoryState", "NextTurnState"), AE.SCREEN_S)
    G3F.guarded("DG", lambda: session.dismiss_client_briefing(client), m)
    up, ctx["clientScreenS"] = AE.wait_until(lambda: PEQ.screen_up(client), AE.SCREEN_S)
    if not up:
        G3F.capture("DG", "the client's pre-battle screen never came up", m)
        raise G3F.Miss("DG")
    v = AE.iv(client)
    ctx.update(X=v.get("unitId"), PILE=tuple((AE.es(host, "equip") or {}).get("pile") or ()), PILE_IDS=PEQ.ground_ids(v),
               cols={g["id"]: (g.get("x"), g.get("y")) for g in v.get("ground") or []})
    ctx["CENSUS0"] = AE.census(host)
    ctx["census0Client"] = AE.census(client) == ctx["CENSUS0"]
    AE.reads(ctx, host, client)
    return ctx


def row_ag1(host, client, ctx, crash0):
    A, v = ctx["A"], AE.iv(host)
    cnt = ((AE.es(host, "equip") or {}).get("counted") or [])[:2]
    n = G3F.log_count(host, N_NOTHING)
    ev = {k: ctx[k] for k in ("gm", "R0", "X", "PILE", "PILE_IDS", "cols", "PISTOL", "RIFLE", "BP0", "BACKPACK_CELL",
                              "X_CELL", "types", "hostTopS", "clientScreenS", "census0Client", "nothingBefore")}
    ev.update(hostView=PEQ.view_brief(v), stacks=[G3F.stack(host), G3F.stack(client)], logPath=log_path(host),
              equip=[AE.es(host, "equip"), AE.es(client, "equip")])
    return {"AG1-counted": (cnt == [True, True], f"host equip.counted[:2] {cnt} (want [true, true])"),
            "AG1-screen": (G3F.top(host) == "InventoryState" and AE.screen_on(host, A) and n == 0,
                           f"host top {G3F.top(host)}, inventory_view {PEQ.view_brief(v)} (want the pre-battle InventoryState "
                           f"on {A}); '{N_NOTHING}' in {log_path(host)}: {n} (want 0, D-3)"),
            "AG1-ground": (AE.G(host) == ctx["PILE_IDS"], f"G(host) {AE.G(host)} (want PILE_IDS {ctx['PILE_IDS']})"),
            "AG1-gear": AE.gear_cell(host, client, ctx),
            "AG1-common": G3F.common(host, client, crash0)}, ev


def row_ag2(host, client, ctx, crash0):
    A, bc, m = ctx["A"], ctx["BACKPACK_CELL"], (host, client)
    ev = {"candidate": ctx["RIFLE"], "cell": bc}
    if AE.screen_on(host, A) and bc is not None:
        cand = AE.rifle_choice(host, AE.IT(host), A, ctx["BP0"])
        p, d = {}, {}
        got = AE.pick_ground(host, cand, p)
        if got is not None:
            ctx["RIFLE"] = got
            AE.drop_at(host, BACK, bc[0], bc[1], d)
            ev["drainS"] = AE.drained(host, client)
            ev["landS"] = AE.wait_until(lambda: all(AE.owned(AE.IT(gc), got, A, BACK) for gc in m), AE.LAND_S)[1]
        ev.update(pick=p, drop=d)
    else:
        ev["step"] = f"no pre-battle screen on the host on {A} (top {G3F.top(host)})"
    R = ctx["RIFLE"]
    gone = AE.screen_on(client, ctx["X"]) and R not in AE.G(client)
    return {"AG2-held": AE.held_cells(host, client, R, A, BACK, ctx["PILE"]),
            "AG2-gone": (gone, f"client screen on {ctx['X']} {AE.screen_on(client, ctx['X'])}; RIFLE {R} in G(client) "
                         f"{R in AE.G(client)} (want the screen up and RIFLE gone from it)"),
            "AG2-common": G3F.common(host, client, crash0)}, ev


def row_ag3(host, client, ctx, crash0):
    A, P = ctx["A"], ctx["PISTOL"]
    ev = {"PISTOL": P}
    s = ctx["R0"]["host"]["A_START"].get(P) or (None, 0, 0)
    if AE.screen_on(host, A):
        p, d = {}, {}
        if AE.pick_at(host, s[0], s[1], s[2], P, p):
            AE.drop_ground(host, AE.IT(host), d)
            ev["drainS"] = AE.drained(host, client)
            ev["landS"] = AE.wait_until(lambda: AE.at_both(host, client, P, ctx["PILE"]), AE.LAND_S)[1]
        ev.update(pick=p, drop=d)
    else:
        ev["step"] = f"no pre-battle screen on the host on {A} (top {G3F.top(host)})"
    return {"AG3-pile": (AE.at_both(host, client, P, ctx["PILE"]), f"PISTOL {P} host/client {AE.views(host, client, P)} "
                         f"(want at PILE {ctx['PILE']} on both)"),
            "AG3-seen": (P in AE.G(client), f"PISTOL {P} in G(client) {P in AE.G(client)} (want true)"),
            "AG3-common": G3F.common(host, client, crash0)}, ev


def row_ag4(host, client, ctx, crash0):
    A, P, C1, xc = ctx["A"], ctx["PISTOL"], ctx["X"], ctx["X_CELL"]
    b, ev = AE.before(host, client), {"PISTOL": P, "C1_CELL": xc}
    if AE.screen_on(client, C1) and P in AE.G(client) and xc is not None:
        p, d = {}, {}
        if AE.pick_ground(client, P, p) is not None:
            AE.drop_at(client, BACK, xc[0], xc[1], d)
            ev["orderS"] = AE.settle(host, client)
            ev["landS"] = AE.wait_until(lambda: all(AE.owned(AE.IT(gc), P, C1) for gc in (host, client)), AE.LAND_S)[1]
        ev.update(pick=p, drop=d)
    else:
        ev["step"] = f"no PISTOL {P} on the client's ground (screen on {C1} {AE.screen_on(client, C1)})"
    gone = AE.screen_on(host, A) and P not in AE.G(host)
    return {"AG4-order": AE.order_cell(host, client, b, C1),
            "AG4-held": AE.held_cells(host, client, P, C1, None, ctx["PILE"]),
            "AG4-gone": (gone, f"host screen on {A} {AE.screen_on(host, A)}; PISTOL {P} in G(host) {P in AE.G(host)} (want "
                         f"the screen up and PISTOL gone from it)"),
            "AG4-common": G3F.common(host, client, crash0)}, ev


def row_ag5(host, client, ctx, crash0):
    A, R = ctx["A"], ctx["RIFLE"]
    ev = {"RIFLE": R}
    turn = AE.barrier(host, client, client, host, ev)
    hashed = G3F.hash_now(host, client)
    ps = [AE.pos(host, A), AE.pos(client, A)]
    sel = battle_state(host).get("selectedId")
    held = all(AE.owned(AE.IT(gc), R, A) for gc in (host, client))
    return {"AG5-turn": turn,
            "AG5-held": (held and ps == [ctx["R0"]["host"]["A_SPAWN"]] * 2 and sel == SEL_AFTER_ENTRY
                         and hashed == "all buckets EQUAL",
                         f"RIFLE {R} host/client {AE.views(host, client, R)} (want owner {A}); A at {ps} (want A_SPAWN "
                         f"{ctx['R0']['host']['A_SPAWN']} on both); host selectedId {sel} (want {SEL_AFTER_ENTRY}); "
                         f"hash {hashed}"),
            "AG5-census": AE.census_cell(host, client, ctx["CENSUS0"]),
            "AG5-common": G3F.common(host, client, crash0, hashed)}, ev


def row_ag6(host, client, ctx, crash0):
    s = AE.own_unit(host, 1, ctx["PILE"])
    ev = {"S_OWN": s, "sideTurn": [(battle_state(gc).get("side"), battle_state(gc).get("turn")) for gc in (host, client)]}
    if s is None:
        raise AssertionError(f"staging: no client soldier off the pile {ctx['PILE']}")
    r = AE.own_tile(host, client, client, s, ev)
    return {"AG6-ground": (r["opened"] and r["ground"] == r["tile"], f"client inventory opened {r['opened']} {ev['open']}; "
                           f"G(client) {r['ground']} (want the ids on S_OWN's tile in IT(host) {r['tile']})"),
            "AG6-order": AE.order_cell(host, client, r["before"], s),
            "AG6-tile": (r["landed"], f"grenade {ev['grenade']} host/client {ev['grenadeViews']} (want at S_OWN's "
                         f"position {ev['pos'][0]} on both)"),
            "AG6-common": G3F.common(host, client, crash0)}, ev


def row_ag7(host, client, ctx, crash0):
    A, ev = ctx["A"], {}
    try:
        RM.side_change(host, client, client, 1, 1, ev)
    except Exception as e:
        raise AssertionError(f"staging: the client's END TURN: {str(e)[:300]}")
    r = AE.own_tile(host, client, host, A, ev)
    return {"AG7-ground": (r["opened"] and r["ground"] == r["tile"], f"host inventory opened {r['opened']} {ev['open']}; "
                           f"G(host) {r['ground']} (want the ids on A's tile {r['tile']})"),
            "AG7-tile": (r["landed"], f"grenade {ev['grenade']} host/client {ev['grenadeViews']} (want at A's position "
                         f"{ev['pos'][0]} on both)"),
            "AG7-common": G3F.common(host, client, crash0)}, ev


FN = {"AG1": row_ag1, "AG2": row_ag2, "AG3": row_ag3, "AG4": row_ag4, "AG5": row_ag5, "AG6": row_ag6, "AG7": row_ag7}


def main():
    t0 = time.time()
    fails = AE.run_boot("DG", ROWS, FN, setup_dg, "r5u6_dg_host", "r5u6_dg_client")
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_r5_alien_equip_gm3: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
