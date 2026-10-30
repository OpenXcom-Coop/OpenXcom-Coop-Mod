"""A SEPARATE partner's own tank parked on the host's craft fights in the host's battle (as in test_tank_entry) and is
destroyed: at the battle's end it leaves the partner's world, the host's stores do not change, and the host's battleEnd
lists it lost.

The ending kills T first, then every hostile, presses END TURN on both and closes the host's NextTurnState; each tank
takes 30 shells (S0 {2, 30}).

Boot (SEPARATE, port 47615, dirs tank_lost_host / tank_lost_client): test_tank_return.bring_up(host, client, "47615") -
test_tank_entry.bring_up_tank_battle with the pre_mission reads of S0 (the host's storage) and PARK0 (the partner's
craft_vehicles on its own Skyranger), pin_ai_neutral, the setup values HOST_BASE_COOP / HOST_SKY / CLIENT_SKY / TAG / T
(the one STR_TANK_CANNON unit whose guestTank == TAG on both machines) and the PARK0 guard (the parked tank, 30 shells).
  destroyed_tank_lost: tank_killed (precondition: the host's kill_unit_real {unit: T}, chain_settled; T status 6 on
  both), lost_common (after tank_killed), battle_ends (precondition: as in test_tank_return - every live hostile killed
  with chain_settled after each, END TURN on both, the host's NextTurnState closed, the host's DebriefingState, the
  partner's display-only one, the partner's OK through its follow-ups with sepReturn.ownLoaded 1, the host's OK +
  drain), tank_recorded_lost (the host's battleEnd.guestTanks == [{ownerSeat 1, baseId HOST_BASE_COOP, craftId HOST_SKY,
  craftType STR_SKYRANGER, type STR_TANK_CANNON, unitId T, lost true}]), tank_left_world (the partner's Skyranger holds
  no STR_TANK_CANNON), host_stores_kept (the host's storage == S0), partner_counts (the partner's sepReturn tanksLost 1,
  tanksMissing 0).
Without the fix tank_recorded_lost (absent), tank_left_world (the parked tank stays), partner_counts (absent) FAIL;
every other cell PASS (a dead tank is never credited: host_stores_kept).

One EVIDENCE line, then one PASS/FAIL line per cell, then the row verdict. A cell whose precondition failed FAILs "not
reached (<cell> failed)". A boot step past its bound prints ONE CAPTURE lost_battle line and fails the row "boot".
Common cell: every hash bucket EQUAL, desyncSeen false on both, no new crash file. Ids come from probes; a key the build
does not write reads as absent. Run in the foreground to completion. ONE run is the result, no skip path; exit 0 only
when every cell passes, else 2.

Run:  python tools/coop_test/test_tank_lost.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_battle_end_separate as SEP  # noqa: E402
import test_tank_return as RT  # noqa: E402

PORT = "47615"
TANK = RT.TANK
ROWS = (("destroyed_tank_lost", ("tank_killed", "lost_common", "battle_ends", "tank_recorded_lost", "tank_left_world",
                                 "host_stores_kept", "partner_counts")),)


def row_destroyed_tank_lost(host, client, pins, crash0):
    cells, ev = {}, RT.ev0(host, client, pins)
    T = pins["T"]
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": T})
    ok, secs, _s = SEP.chain_settled(host, client, timeout=RT.KILL_S)
    st = [(RT.units(gc).get(T) or {}).get("status") for gc in (host, client)]
    ev["kill"] = {"resp": {k: r.get(k) for k in ("ok", "killed", "error")}, "settled": ok, "secs": secs, "status": st}
    cells["tank_killed"] = (ok and st == [RT.STATUS_DEAD] * 2,
                            f"host kill_unit_real {{unit: {T}}} {ev['kill']['resp']}; settled {ok} "
                            f"within {RT.KILL_S} s ({secs} s); unit {T} status host/partner {st} (want "
                            f"{RT.STATUS_DEAD} / {RT.STATUS_DEAD})")
    cells["lost_common"] = G3F.common(host, client, crash0)
    cells["battle_ends"] = RT.ending(host, client, ev.setdefault("end", {}))
    cells["tank_recorded_lost"], cells["partner_counts"] = RT.record_cells(host, client, pins, True, ev)
    cells["host_stores_kept"], _craft, pc = RT.after_cells(host, client, pins, ev)
    cells["tank_left_world"] = (pc.get("error") is None and TANK not in (pc.get("vehicles") or {}),
                                f"partner craft_vehicles {pins['CLIENT_SKY']} after both OKs "
                                f"{dict((k, pc.get(k)) for k in RT.VKEYS + ('error',))} (want no {TANK}: a lost tank "
                                f"leaves the partner's world; PARK0 {pins['PARK0']})")
    pre = ("tank_killed" if not cells["tank_killed"][0]
           else "battle_ends" if not cells["battle_ends"][0] else None)
    if pre:
        RT.not_reached(cells, ("tank_recorded_lost", "tank_left_world", "host_stores_kept", "partner_counts"),
                       f"{pre} failed")
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("tank_lost_host"))
    client = GameClient("client", None, make_user_dir("tank_lost_client"))
    fails = 0
    try:
        try:
            pins, crash0 = RT.bring_up(host, client, PORT, "lost_battle")
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE lost_battle line)")
        else:
            fails += G3F.run_row("destroyed_tank_lost", ROWS[0][1],
                                 lambda: row_destroyed_tank_lost(host, client, pins, crash0))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_tank_lost: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
