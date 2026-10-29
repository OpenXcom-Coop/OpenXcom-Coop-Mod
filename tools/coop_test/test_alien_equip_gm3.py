"""PvP alien equipment, gm3 (boot host_aliens, Small Scout: the HOST plays the aliens, seat 0; the client the seven
X-COM soldiers, seat 1; default options, so "Enable XCOM Equipment for Aliens in PVP" is on): the gm3 alien host equips
its own aliens on the pre-battle screen from the ONE X-COM craft pile both sides share, nothing is refused, the aliens'
starting gear stays in their hands, and after the equip screen every drop lands on the dropping unit's own tile.

The steps follow test_alien_equip's rules for the drop cell on the pile, PISTOL and RIFLE, and use its helpers.
event_state.equip has no `noScreen` field, so alien_screen_up reads the host log line "[coop-equip] nothing to equip on
this machine" (the only noScreen writer's own line) == 0 in the host's openxcom.log. No item id is pinned.

Boot host_aliens (key 49066): set_seed 1, pvp_fixture.start_pvp_skirmish_lobby(alien_player="host") (gamemode 3),
repro_pvp_side_relative's battle drive without its last line; both briefings; the initial reads on each machine (A = the
host seat's first unit with items); the host's briefing OK (a bounded wait for its top); the client's briefing closed
-> its screen on C1, the unit it opens on (PILE_IDS = G(client) at its open); CENSUS0.
  alien_screen_opens       the host alien's screen and its own gear: both_seats_counted, alien_screen_up,
                           alien_sees_pile, alien_keeps_start_gear
  alien_takes_rifle        the host alien takes RIFLE into BACKPACK_CELL (host-local real UI): rifle_held_by_alien,
                           rifle_gone_from_xcom_screen
  alien_drops_pistol       the host alien's own PISTOL goes on the shared pile: pistol_on_pile, xcom_sees_pistol
  xcom_takes_pistol        the X-COM player takes it onto C1_CELL (the client's real UI): pistol_take_order,
                           pistol_held_by_xcom, pistol_gone_from_alien_screen
  turn_one_with_xcom_gear  turn 1 (the client's OK, the host's OK where its screen is up): turn_one_starts,
                           alien_keeps_rifle, item_census_unchanged
  soldier_drop_own_tile    a soldier's turn-1 drop lands on its own tile (the client drops from the soldier's
                           inventory): soldier_ground_is_tile, soldier_drop_order, soldier_drop_lands
  alien_drop_own_tile      an alien's turn-1 drop lands on its own tile (the client's END TURN, the host's drop):
                           alien_ground_is_tile, alien_drop_lands
Each row ends with a common cell (<row>_common): every hash bucket EQUAL, desyncSeen false on both, no new crash
file.

On a build without this feature, these cells fail: both_seats_counted, alien_screen_up, alien_sees_pile,
rifle_held_by_alien, rifle_gone_from_xcom_screen, pistol_on_pile, xcom_sees_pistol, pistol_take_order,
pistol_held_by_xcom, pistol_gone_from_alien_screen, alien_keeps_rifle; every other cell passes. One EVIDENCE line per
row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step past its bound
prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails that row "staging". Run it in
the foreground to completion: one run is the result, with no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_alien_equip_gm3.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_prebattle_equip as PEQ  # noqa: E402
import test_alien_equip as AE  # noqa: E402

KEY = "49066"
N_NOTHING = "[coop-equip] nothing to equip on this machine"   # the host's no-screen branch's own log line
SEL_AFTER_ENTRY = -1              # the host's selectedId after the equip entry: none (it holds no X-COM unit)
BACK, LH = AE.BACK, AE.LH
ROWS = (("alien_screen_opens", ("both_seats_counted", "alien_screen_up", "alien_sees_pile", "alien_keeps_start_gear",
                                "alien_screen_opens_common")),
        ("alien_takes_rifle", ("rifle_held_by_alien", "rifle_gone_from_xcom_screen", "alien_takes_rifle_common")),
        ("alien_drops_pistol", ("pistol_on_pile", "xcom_sees_pistol", "alien_drops_pistol_common")),
        ("xcom_takes_pistol", ("pistol_take_order", "pistol_held_by_xcom", "pistol_gone_from_alien_screen",
                               "xcom_takes_pistol_common")),
        ("turn_one_with_xcom_gear", ("turn_one_starts", "alien_keeps_rifle", "item_census_unchanged",
                                     "turn_one_with_xcom_gear_common")),
        ("soldier_drop_own_tile", ("soldier_ground_is_tile", "soldier_drop_order", "soldier_drop_lands",
                                   "soldier_drop_own_tile_common")),
        ("alien_drop_own_tile", ("alien_ground_is_tile", "alien_drop_lands", "alien_drop_own_tile_common")))


def log_path(gc):
    return os.path.join(gc.user_dir, "openxcom.log")


def setup_host_aliens(host, client):
    m = (host, client)
    ctx = AE.bring_up(host, client, KEY, "host", "host_aliens", 0)
    ctx["nothingBefore"] = G3F.log_count(host, N_NOTHING)
    G3F.guarded("host_aliens", lambda: host.ok({"cmd": "click_widget", "match": "ok"}), m)
    _, ctx["hostTopS"] = AE.wait_until(lambda: G3F.top(host) in ("InventoryState", "NextTurnState"), AE.SCREEN_S)
    G3F.guarded("host_aliens", lambda: session.dismiss_client_briefing(client), m)
    up, ctx["clientScreenS"] = AE.wait_until(lambda: PEQ.screen_up(client), AE.SCREEN_S)
    if not up:
        G3F.capture("host_aliens", "the client's pre-battle screen never came up", m)
        raise G3F.Miss("host_aliens")
    v = AE.iv(client)
    ctx.update(X=v.get("unitId"), PILE=tuple((AE.es(host, "equip") or {}).get("pile") or ()), PILE_IDS=PEQ.ground_ids(v),
               cols={g["id"]: (g.get("x"), g.get("y")) for g in v.get("ground") or []})
    ctx["CENSUS0"] = AE.census(host)
    ctx["census0Client"] = AE.census(client) == ctx["CENSUS0"]
    AE.reads(ctx, host, client)
    return ctx


def row_alien_screen_opens(host, client, ctx, crash0):
    A, v = ctx["A"], AE.iv(host)
    cnt = ((AE.es(host, "equip") or {}).get("counted") or [])[:2]
    n = G3F.log_count(host, N_NOTHING)
    ev = {k: ctx[k] for k in ("gm", "initial", "X", "PILE", "PILE_IDS", "cols", "PISTOL", "RIFLE", "RIFLE_CELL",
                              "BACKPACK_CELL", "X_CELL", "types", "hostTopS", "clientScreenS", "census0Client",
                              "nothingBefore")}
    ev.update(hostView=PEQ.view_brief(v), stacks=[G3F.stack(host), G3F.stack(client)], logPath=log_path(host),
              equip=[AE.es(host, "equip"), AE.es(client, "equip")])
    return {"both_seats_counted": (cnt == [True, True], f"host equip.counted[:2] {cnt} (want [true, true])"),
            "alien_screen_up": (G3F.top(host) == "InventoryState" and AE.screen_on(host, A) and n == 0,
                           f"host top {G3F.top(host)}, inventory_view {PEQ.view_brief(v)} (want the pre-battle InventoryState "
                           f"on {A}); '{N_NOTHING}' in {log_path(host)}: {n} (want 0)"),
            "alien_sees_pile": (AE.G(host) == ctx["PILE_IDS"], f"G(host) {AE.G(host)} (want PILE_IDS {ctx['PILE_IDS']})"),
            "alien_keeps_start_gear": AE.gear_cell(host, client, ctx),
            "alien_screen_opens_common": G3F.common(host, client, crash0)}, ev


def row_alien_takes_rifle(host, client, ctx, crash0):
    A, bc, m = ctx["A"], ctx["BACKPACK_CELL"], (host, client)
    ev = {"candidate": ctx["RIFLE"], "cell": bc}
    if AE.screen_on(host, A) and bc is not None:
        cand = AE.rifle_choice(host, AE.IT(host), A, ctx["RIFLE_CELL"])
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
    return {"rifle_held_by_alien": AE.held_cells(host, client, R, A, BACK, ctx["PILE"]),
            "rifle_gone_from_xcom_screen": (gone, f"client screen on {ctx['X']} {AE.screen_on(client, ctx['X'])}; RIFLE {R} in G(client) "
                         f"{R in AE.G(client)} (want the screen up and RIFLE gone from it)"),
            "alien_takes_rifle_common": G3F.common(host, client, crash0)}, ev


def row_alien_drops_pistol(host, client, ctx, crash0):
    A, P = ctx["A"], ctx["PISTOL"]
    ev = {"PISTOL": P}
    s = ctx["initial"]["host"]["A_START"].get(P) or (None, 0, 0)
    if AE.screen_on(host, A):
        p, d = {}, {}
        if AE.pick_at(host, s[0], s[1], s[2], P, p):
            AE.drop_ground(host, AE.IT(host), d)
            ev["drainS"] = AE.drained(host, client)
            ev["landS"] = AE.wait_until(lambda: AE.at_both(host, client, P, ctx["PILE"]), AE.LAND_S)[1]
        ev.update(pick=p, drop=d)
    else:
        ev["step"] = f"no pre-battle screen on the host on {A} (top {G3F.top(host)})"
    return {"pistol_on_pile": (AE.at_both(host, client, P, ctx["PILE"]), f"PISTOL {P} host/client {AE.views(host, client, P)} "
                         f"(want at PILE {ctx['PILE']} on both)"),
            "xcom_sees_pistol": (P in AE.G(client), f"PISTOL {P} in G(client) {P in AE.G(client)} (want true)"),
            "alien_drops_pistol_common": G3F.common(host, client, crash0)}, ev


def row_xcom_takes_pistol(host, client, ctx, crash0):
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
    return {"pistol_take_order": AE.order_cell(host, client, b, C1),
            "pistol_held_by_xcom": AE.held_cells(host, client, P, C1, None, ctx["PILE"]),
            "pistol_gone_from_alien_screen": (gone, f"host screen on {A} {AE.screen_on(host, A)}; PISTOL {P} in G(host) {P in AE.G(host)} (want "
                         f"the screen up and PISTOL gone from it)"),
            "xcom_takes_pistol_common": G3F.common(host, client, crash0)}, ev


def row_turn_one_with_xcom_gear(host, client, ctx, crash0):
    A, R = ctx["A"], ctx["RIFLE"]
    ev = {"RIFLE": R}
    turn = AE.barrier(host, client, client, host, ev)
    hashed = G3F.hash_now(host, client)
    ps = [AE.pos(host, A), AE.pos(client, A)]
    sel = battle_state(host).get("selectedId")
    held = all(AE.owned(AE.IT(gc), R, A) for gc in (host, client))
    return {"turn_one_starts": turn,
            "alien_keeps_rifle": (held and ps == [ctx["initial"]["host"]["A_SPAWN"]] * 2 and sel == SEL_AFTER_ENTRY
                         and hashed == "all buckets EQUAL",
                         f"RIFLE {R} host/client {AE.views(host, client, R)} (want owner {A}); A at {ps} (want A_SPAWN "
                         f"{ctx['initial']['host']['A_SPAWN']} on both); host selectedId {sel} (want {SEL_AFTER_ENTRY}); "
                         f"hash {hashed}"),
            "item_census_unchanged": AE.census_cell(host, client, ctx["CENSUS0"]),
            "turn_one_with_xcom_gear_common": G3F.common(host, client, crash0, hashed)}, ev


def row_soldier_drop_own_tile(host, client, ctx, crash0):
    s = AE.own_unit(host, 1, ctx["PILE"])
    ev = {"S_OWN": s, "sideTurn": [(battle_state(gc).get("side"), battle_state(gc).get("turn")) for gc in (host, client)]}
    if s is None:
        raise AssertionError(f"staging: no client soldier off the pile {ctx['PILE']}")
    r = AE.own_tile(host, client, client, s, ev)
    return {"soldier_ground_is_tile": (r["opened"] and r["ground"] == r["tile"], f"client inventory opened {r['opened']} {ev['open']}; "
                           f"G(client) {r['ground']} (want the ids on S_OWN's tile in IT(host) {r['tile']})"),
            "soldier_drop_order": AE.order_cell(host, client, r["before"], s),
            "soldier_drop_lands": (r["landed"], f"grenade {ev['grenade']} host/client {ev['grenadeViews']} (want at S_OWN's "
                         f"position {ev['pos'][0]} on both)"),
            "soldier_drop_own_tile_common": G3F.common(host, client, crash0)}, ev


def row_alien_drop_own_tile(host, client, ctx, crash0):
    A, ev = ctx["A"], {}
    try:
        RM.side_change(host, client, client, 1, 1, ev)
    except Exception as e:
        raise AssertionError(f"staging: the client's END TURN: {str(e)[:300]}")
    r = AE.own_tile(host, client, host, A, ev)
    return {"alien_ground_is_tile": (r["opened"] and r["ground"] == r["tile"], f"host inventory opened {r['opened']} {ev['open']}; "
                           f"G(host) {r['ground']} (want the ids on A's tile {r['tile']})"),
            "alien_drop_lands": (r["landed"], f"grenade {ev['grenade']} host/client {ev['grenadeViews']} (want at A's position "
                         f"{ev['pos'][0]} on both)"),
            "alien_drop_own_tile_common": G3F.common(host, client, crash0)}, ev


FN = {"alien_screen_opens": row_alien_screen_opens, "alien_takes_rifle": row_alien_takes_rifle,
      "alien_drops_pistol": row_alien_drops_pistol, "xcom_takes_pistol": row_xcom_takes_pistol,
      "turn_one_with_xcom_gear": row_turn_one_with_xcom_gear, "soldier_drop_own_tile": row_soldier_drop_own_tile,
      "alien_drop_own_tile": row_alien_drop_own_tile}


def main():
    t0 = time.time()
    fails = AE.run_boot("host_aliens", ROWS, FN, setup_host_aliens, "alien_equip_gm3_host", "alien_equip_gm3_client")
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_alien_equip_gm3: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
