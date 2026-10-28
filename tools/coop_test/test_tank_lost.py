"""D248-U S-B row R2 (boot RL; owner D248 (b) "the surviving tank returns"): a SEPARATE partner's own tank parked on the
host's craft fights in the host's battle (S-A) and is destroyed: at the battle's end it leaves the partner's world, the
host's stores do not change, and the host's battleEnd lists it lost.

Spec: docs repo rewrite/prompts/d248u_client_tank_host_craft.md section (f) test_tank_lost.py, as amended by
AMENDMENT D248-1 section 4 (SB-1 the ending: T killed first, then the hostiles, END TURN on both, the host's NextTurnState
closed; SB-3 30 shells, S0 {2, 30}) and section 5 (each pin's rule); rulings QD248-1 .. QD248-11 (a), R-D248-SA-1,
QD248-B1-1 .. -4 (a). Constants: rewrite/d248u-task0/sb/CONSTANTS.md (TASK 0 boots RLa, RLb).

Boot RL (SEPARATE, port 47615, dirs d248u_rl_host / d248u_rl_client): test_tank_return.bring_up(host, client, "47615")
- test_tank_entry.bring_up_tank_battle with the pre_mission reads of S0 (the host's storage) and PARK0 (the partner's
craft_vehicles on its own Skyranger), pin_ai_neutral, the pins HOST_BASE_COOP / HOST_SKY / CLIENT_SKY / TAG / T (the one
STR_TANK_CANNON unit whose guestTank == TAG on both machines) and the PARK0 guard (the parked tank, 30 shells).
  R2  R2-kill (precondition: the host's kill_unit_real {unit: T}, chain_settled; T status 6 on both), R2-common (after
      R2-kill), R2-end (precondition: as R1-end - every live hostile killed with chain_settled after each, END TURN on
      both, the host's NextTurnState closed, the host's DebriefingState, the partner's display-only one, the partner's OK
      through its follow-ups with sepReturn.ownLoaded 1, the host's OK + drain), R2-record (the host's battleEnd.guestTanks
      == [{ownerSeat 1, baseId HOST_BASE_COOP, craftId HOST_SKY, craftType STR_SKYRANGER, type STR_TANK_CANNON, unitId T,
      lost true}]), R2-home (the partner's Skyranger holds no STR_TANK_CANNON), R2-stores (the host's storage == S0),
      R2-sep (the partner's sepReturn tanksLost 1, tanksMissing 0).
Red at B1 (the S-A green build): R2-record (absent), R2-home (the parked tank stays), R2-sep (absent) FAIL; every other
cell PASS (a dead tank is never credited: R2-stores).

One EVIDENCE line, then one PASS/FAIL line per cell, then the row verdict. A cell whose precondition failed FAILs "not
reached (<cell> failed)". A boot step past its bound prints ONE CAPTURE RL line and fails the row "boot". Common cell: every
hash bucket EQUAL, desyncSeen false on both, no new crash file. Ids come from probes (S25); a key the build does not write
reads as absent. WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0
only when every cell passes, else 2.

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
ROWS = (("R2", ("R2-kill", "R2-common", "R2-end", "R2-record", "R2-home", "R2-stores", "R2-sep")),)


def row_r2(host, client, pins, crash0):
    cells, ev = {}, RT.ev0(host, client, pins)
    T = pins["T"]
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": T})
    ok, secs, _s = SEP.chain_settled(host, client, timeout=RT.KILL_S)
    st = [(RT.units(gc).get(T) or {}).get("status") for gc in (host, client)]
    ev["kill"] = {"resp": {k: r.get(k) for k in ("ok", "killed", "error")}, "settled": ok, "secs": secs, "status": st}
    cells["R2-kill"] = (ok and st == [RT.STATUS_DEAD] * 2,
                        f"host kill_unit_real {{unit: {T}}} {ev['kill']['resp']}; settled {ok} within {RT.KILL_S} s "
                        f"({secs} s); unit {T} status host/partner {st} (want {RT.STATUS_DEAD} / {RT.STATUS_DEAD})")
    cells["R2-common"] = G3F.common(host, client, crash0)
    cells["R2-end"] = RT.ending(host, client, ev.setdefault("end", {}))
    cells["R2-record"], cells["R2-sep"] = RT.record_cells(host, client, pins, True, ev)
    cells["R2-stores"], _craft, pc = RT.after_cells(host, client, pins, ev)
    cells["R2-home"] = (pc.get("error") is None and TANK not in (pc.get("vehicles") or {}),
                        f"partner craft_vehicles {pins['CLIENT_SKY']} after both OKs "
                        f"{dict((k, pc.get(k)) for k in RT.VKEYS + ('error',))} (want no {TANK}: a lost tank leaves the "
                        f"partner's world; PARK0 {pins['PARK0']})")
    pre = "R2-kill" if not cells["R2-kill"][0] else "R2-end" if not cells["R2-end"][0] else None
    if pre:
        RT.not_reached(cells, ("R2-record", "R2-home", "R2-stores", "R2-sep"), f"{pre} failed")
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("d248u_rl_host"))
    client = GameClient("client", None, make_user_dir("d248u_rl_client"))
    fails = 0
    try:
        try:
            pins, crash0 = RT.bring_up(host, client, PORT, "RL")
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE RL line)")
        else:
            fails += G3F.run_row("R2", ROWS[0][1], lambda: row_r2(host, client, pins, crash0))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_tank_lost: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
