"""PvP alien equipment with the option off (boot equipment_off, gm2 STR_SMALL_SCOUT: the client plays the aliens,
seat 1; the host the X-COM soldiers, seat 0; the HOST's "Enable XCOM Equipment for Aliens in PVP" OFF, which the join
gives the client): with the option off the PvP alien seat has nothing to equip and sees vanilla's Turn-1 screen at
once, and turn 1 follows the X-COM host's OK with the aliens' gear untouched. A guard: it passes with or without the
alien seat's own PREV / NEXT cycle (test_alien_equip_cycle).

A's items are read on both machines before the host's OK and compared after the barrier; no item id is pinned.

Boot equipment_off (key 49068): host options {EnableXcomEquipmentAliensPVP: false}; set_seed 1, the client joins and
takes the Alien team (gamemode 2), repro_pvp_side_relative's gm2 drive without its last line (STR_SMALL_SCOUT); the
initial reads on both before the briefings close (A = the client seat's first unit owning an item, A_START, A_SPAWN);
the host's briefing OK -> its screen on H1, the unit it opens on; dismiss_client_briefing -> the client's equip entry
(a bounded wait for entryDone and a top other than BattlescapeState).
  alien_nothing_to_equip  the alien seat has nothing to equip: only_host_counted, alien_turn_screen_at_once
  turn_one_on_host_ok     turn 1 on the host's OK: turn_one_gear_untouched
Each row ends with a common cell (<row>_common): every hash bucket EQUAL, desyncSeen false on both, no new crash
file.

Every cell passes with or without that cycle. One EVIDENCE line per row, one PASS/FAIL line per cell, then the row
verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails every row "boot".
Run it in the foreground to completion: one run is the result, with no skip path; exit 0 only when every cell passes,
else 2.

Run:  python tools/coop_test/test_alien_equip_off.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_prebattle_equip as PEQ  # noqa: E402
import test_alien_equip as AE  # noqa: E402
import test_alien_equip_cycle as CY  # noqa: E402

KEY = "49068"
MISSION = "STR_SMALL_SCOUT"
HOST_OPTIONS = {"EnableXcomEquipmentAliensPVP": False}   # the host's session value (the join gives it to the client)
N_NO_OWN = "[coop-equip] client: no own soldier with an inventory"   # coopEquipPumpClient logs it once
ENTRY_S, LOG_S = 15, 5            # the client's equip entry and its log line (measured: 0.1 s)
ROWS = (("alien_nothing_to_equip", ("only_host_counted", "alien_turn_screen_at_once",
                                    "alien_nothing_to_equip_common")),
        ("turn_one_on_host_ok", ("turn_one_gear_untouched", "turn_one_on_host_ok_common")))


def setup_equipment_off(host, client):
    m = (host, client)
    ctx = {"gm": CY.lobby_drive(host, client, KEY, MISSION, "equipment_off")}
    ctx["initial"] = {gc.name: G3F.guarded("equipment_off", lambda gc=gc: AE.initial_reads(gc, CY.CLIENT_SEAT), m)
                      for gc in m}
    A = ctx["initial"]["host"]["A"]
    if A is None or A != ctx["initial"]["client"]["A"]:
        G3F.capture("equipment_off", f"initial {ctx['initial']} (want one A on both)", m)
        raise G3F.Miss("equipment_off")
    ctx["A"], ctx["log0"] = A, G3F.log_count(client, N_NO_OWN)
    ctx["H1"], ctx["hostScreenS"] = CY.host_screen(host, client, "equipment_off")
    G3F.guarded("equipment_off", lambda: session.dismiss_client_briefing(client), m)
    entered, ctx["clientEntryS"] = AE.wait_until(lambda: (AE.es(client, "equip") or {}).get("entryDone")
                                                 and G3F.top(client) != "BattlescapeState", ENTRY_S)
    if not entered:
        G3F.capture("equipment_off", f"the client's equip entry never ran (stacks {CY.stacks(host, client)})", m)
        raise G3F.Miss("equipment_off")
    _, ctx["logS"] = AE.wait_until(lambda: G3F.log_count(client, N_NO_OWN) > ctx["log0"], LOG_S)
    ctx["log1"] = G3F.log_count(client, N_NO_OWN)
    return ctx


def a_items(host, client, A):
    return [AE.items_of(AE.IT(host), A), AE.items_of(AE.IT(client), A)]


def row_alien_nothing_to_equip(host, client, ctx, crash0):
    A = ctx["A"]
    cnt = ((AE.es(host, "equip") or {}).get("counted") or [])[:2]
    st = CY.stacks(host, client)
    pa = [AE.pos(host, A), AE.pos(client, A)]
    ev = {k: ctx[k] for k in ("gm", "initial", "A", "H1", "hostScreenS", "clientEntryS", "logS")}
    ev.update(stacks=st, equip=[AE.es(host, "equip"), AE.es(client, "equip")], Apos=pa,
              AtileItems=[AE.on_tile(AE.IT(host), pa[0]), AE.on_tile(AE.IT(client), pa[1])],
              pile=(AE.es(host, "equip") or {}).get("pile"), clientView=PEQ.view_brief(AE.iv(client)))
    screen = G3F.top(client) == "NextTurnState" and not any("InventoryState" in s for s in st[1])
    return {"only_host_counted": (cnt == [True, False], f"host equip.counted[:2] {cnt} (want [true, false])"),
            "alien_turn_screen_at_once": (screen and ctx["log1"] == ctx["log0"] + 1,
                           f"client top {G3F.top(client)}, stack {st[1]} (want NextTurnState on top, no InventoryState); "
                           f"client log '{N_NO_OWN}' {ctx['log0']} -> {ctx['log1']} (want +1)"),
            "alien_nothing_to_equip_common": G3F.common(host, client, crash0)}, ev


def row_turn_one_on_host_ok(host, client, ctx, crash0):
    A = ctx["A"]
    before = a_items(host, client, A)
    ev = {"before": before, "A_START": [ctx["initial"]["host"]["A_START"], ctx["initial"]["client"]["A_START"]]}
    ok, detail = AE.barrier(host, client, host, client, ev)
    hashed = G3F.hash_now(host, client)
    after = a_items(host, client, A)
    ev.update(after=after, Apos=[AE.pos(host, A), AE.pos(client, A)])
    return {"turn_one_gear_untouched": (ok and after == before and before[0] == before[1] and hashed == "all buckets EQUAL",
                         f"{detail}; A {A}'s items after host {after[0]} client {after[1]} (want == before the host's OK "
                         f"{before[0]} on both); hash {hashed}"),
            "turn_one_on_host_ok_common": G3F.common(host, client, crash0, hashed)}, ev


FN = {"alien_nothing_to_equip": row_alien_nothing_to_equip, "turn_one_on_host_ok": row_turn_one_on_host_ok}


def run_boot(tag, rows, fns, setup, host_dir, client_dir, host_options):
    """test_alien_equip's run_boot with the host's options a parameter."""
    host = GameClient("host", None, make_user_dir(host_dir, options=host_options))
    client = GameClient("client", None, make_user_dir(client_dir))
    crash0 = session._crash_log_snapshot()
    try:
        try:
            ctx = setup(host, client)
        except G3F.Miss:
            return G3F.fail_all(rows, f"boot (see the CAPTURE {tag} line)")
        return sum(G3F.run_row(row, order, lambda r=row: fns[r](host, client, ctx, crash0)) for row, order in rows)
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot("equipment_off", ROWS, FN, setup_equipment_off, "alien_equip_off_host", "alien_equip_off_client",
                     HOST_OPTIONS)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_alien_equip_off: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
