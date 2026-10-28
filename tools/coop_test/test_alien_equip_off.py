"""R5-U6 S-E rows EO1-EO2 (boot EO, gm2 STR_SMALL_SCOUT: the client plays the aliens, seat 1; the host the X-COM soldiers,
seat 0; the HOST's "Enable XCOM Equipment for Aliens in PVP" OFF, which the join gives the client): with the option off the
PvP alien seat has nothing to equip and sees vanilla's Turn-1 screen at once (P8b's rule stands, D215 (a), QU6-6 (a)), and
turn 1 follows the X-COM host's OK with the aliens' gear untouched. A guard: it passes before and after S-E's E2.

Spec: docs repo rewrite/prompts/r5u6_pvp_options.md (d) Stage S-E and (f) `test_alien_equip_off.py`, with AMENDMENT
U6-1.6 item 3 (A's items are read on both machines before the host's OK and compared after the barrier; no pinned ids).
Constants: docs repo rewrite/r5u6-task0/se/CONSTANTS.md (TASK 0 boots EOa, EOb on the HEAD build of 8d04bf087, equal but
for the pile's item ids).

Boot EO (key 49068): host options {EnableXcomEquipmentAliensPVP: false}; set_seed 1, the client joins and takes the Alien
team (gamemode 2), the PSR drive without its last line (STR_SMALL_SCOUT); R0 on both before the briefings close (A = the
client seat's first unit owning an item, A_START, A_SPAWN); the host's briefing OK -> its screen on H1;
dismiss_client_briefing -> the client's equip entry (a bounded wait for entryDone and a top other than BattlescapeState).
  EO1  the alien seat has nothing to equip: EO1-counted, EO1-screen
  EO2  turn 1 on the host's OK: EO2-turn
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new lane crash file.

RED on the build without E2 (commit E1): none (a guard); every cell PASS before and after E2. One EVIDENCE line per row, one
PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE
line and fails every row "boot". run in the foreground to completion. ONE run is the result, no
skip path; exit 0 only when every cell passes, else 2.

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
N_NO_OWN = "[coop-equip] client: no own soldier with an inventory"   # TCP coopEquipPumpClient (TASK 0: 0 -> 1)
ENTRY_S, LOG_S = 15, 5            # the client's equip entry and its log line (TASK 0: 0.1 s)
ROWS = (("EO1", ("EO1-counted", "EO1-screen", "EO1-common")),
        ("EO2", ("EO2-turn", "EO2-common")))


def setup_eo(host, client):
    m = (host, client)
    ctx = {"gm": CY.lobby_drive(host, client, KEY, MISSION, "EO")}
    ctx["R0"] = {gc.name: G3F.guarded("EO", lambda gc=gc: AE.r0(gc, CY.CLIENT_SEAT), m) for gc in m}
    A = ctx["R0"]["host"]["A"]
    if A is None or A != ctx["R0"]["client"]["A"]:
        G3F.capture("EO", f"R0 {ctx['R0']} (want one A on both)", m)
        raise G3F.Miss("EO")
    ctx["A"], ctx["log0"] = A, G3F.log_count(client, N_NO_OWN)
    ctx["H1"], ctx["hostScreenS"] = CY.host_screen(host, client, "EO")
    G3F.guarded("EO", lambda: session.dismiss_client_briefing(client), m)
    entered, ctx["clientEntryS"] = AE.wait_until(lambda: (AE.es(client, "equip") or {}).get("entryDone")
                                                 and G3F.top(client) != "BattlescapeState", ENTRY_S)
    if not entered:
        G3F.capture("EO", f"the client's equip entry never ran (stacks {CY.stacks(host, client)})", m)
        raise G3F.Miss("EO")
    _, ctx["logS"] = AE.wait_until(lambda: G3F.log_count(client, N_NO_OWN) > ctx["log0"], LOG_S)
    ctx["log1"] = G3F.log_count(client, N_NO_OWN)
    return ctx


def a_items(host, client, A):
    return [AE.items_of(AE.IT(host), A), AE.items_of(AE.IT(client), A)]


def row_eo1(host, client, ctx, crash0):
    A = ctx["A"]
    cnt = ((AE.es(host, "equip") or {}).get("counted") or [])[:2]
    st = CY.stacks(host, client)
    pa = [AE.pos(host, A), AE.pos(client, A)]
    ev = {k: ctx[k] for k in ("gm", "R0", "A", "H1", "hostScreenS", "clientEntryS", "logS")}
    ev.update(stacks=st, equip=[AE.es(host, "equip"), AE.es(client, "equip")], Apos=pa,
              AtileItems=[AE.on_tile(AE.IT(host), pa[0]), AE.on_tile(AE.IT(client), pa[1])],
              pile=(AE.es(host, "equip") or {}).get("pile"), clientView=PEQ.view_brief(AE.iv(client)))
    screen = G3F.top(client) == "NextTurnState" and not any("InventoryState" in s for s in st[1])
    return {"EO1-counted": (cnt == [True, False], f"host equip.counted[:2] {cnt} (want [true, false])"),
            "EO1-screen": (screen and ctx["log1"] == ctx["log0"] + 1,
                           f"client top {G3F.top(client)}, stack {st[1]} (want NextTurnState on top, no InventoryState); "
                           f"client log '{N_NO_OWN}' {ctx['log0']} -> {ctx['log1']} (want +1)"),
            "EO1-common": G3F.common(host, client, crash0)}, ev


def row_eo2(host, client, ctx, crash0):
    A = ctx["A"]
    before = a_items(host, client, A)
    ev = {"before": before, "A_START": [ctx["R0"]["host"]["A_START"], ctx["R0"]["client"]["A_START"]]}
    ok, detail = AE.barrier(host, client, host, client, ev)
    hashed = G3F.hash_now(host, client)
    after = a_items(host, client, A)
    ev.update(after=after, Apos=[AE.pos(host, A), AE.pos(client, A)])
    return {"EO2-turn": (ok and after == before and before[0] == before[1] and hashed == "all buckets EQUAL",
                         f"{detail}; A {A}'s items after host {after[0]} client {after[1]} (want == before the host's OK "
                         f"{before[0]} on both); hash {hashed}"),
            "EO2-common": G3F.common(host, client, crash0, hashed)}, ev


FN = {"EO1": row_eo1, "EO2": row_eo2}


def run_boot(tag, rows, fns, setup, host_dir, client_dir, host_options):
    """S-D's AE.run_boot with the host's options a parameter."""
    host = GameClient("host", None, make_user_dir(host_dir, options=host_options))
    client = GameClient("client", None, make_user_dir(client_dir))
    crash0 = session._crash_log_snapshot()
    try:
        try:
            ctx = setup(host, client)
        except G3F.Miss:
            return G3F.fail_all(rows, f"boot (FIXTURE-STOP, see the CAPTURE {tag} line)")
        return sum(G3F.run_row(row, order, lambda r=row: fns[r](host, client, ctx, crash0)) for row, order in rows)
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot("EO", ROWS, FN, setup_eo, "r5u6_eo_host", "r5u6_eo_client", HOST_OPTIONS)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_alien_equip_off: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
