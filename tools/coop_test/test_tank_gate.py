"""D248-U S-A row T3 (boot D; QD248-1 (a), owner D248 (b)): the host's only tank is on its own craft and the partner parks
"it" from the visited base (the view turns the host's craft tank into a view item): ONE tank fights, the host's own; the
partner's copy is left out because the host's stores hold no spare of its type.

Spec: docs repo rewrite/prompts/d248u_client_tank_host_craft.md section (f) test_tank_gate.py (QD248-1 .. QD248-11 (a);
ORCHESTRATOR RULING R-D248-SA-1: 30 shells per tank, HOST_BASE_COOP read each boot, the craft's vehicle list asserted after
every craft_equip). Constants: rewrite/d248u-task0/sa/CONSTANTS.md (TASK 0 boots Da, Db).

Boot D (SEPARATE, port 47612, dirs d248u_d_host / d248u_d_client): test_tank_entry.bring_up_tank_battle(host, client,
"47612", host_soldiers=2, host_tank_on_craft=True) (the host's 2 soldiers + its tank = 6 of its half 7; the guest still
merges); pin_ai_neutral.
  T3  T3-park (pre_mission: the host's storage 0 tanks, its Skyranger holds its tank; the partner's Skyranger holds the parked
      tank tagged [HOST_BASE_COOP, HOST_SKY, STR_SKYRANGER]), T3-store (the host's guestContrib.vehicles[1] 1), T3-one (in the
      battle, on both: exactly one STR_TANK_CANNON unit, guestTank "" (absent = ""), coop 0), T3-refused (the host log holds
      exactly one "no spare" line for seat 1), T3-guest ("Guest Zzz" in the battle on both, coop 1), T3-common.
Red at A1 (the unchanged product + T1-T3): T3-store, T3-refused FAIL; every other cell PASS.

One EVIDENCE line, then one PASS/FAIL line per cell, then the row verdict. A boot step past its bound prints ONE CAPTURE line and
fails the row "boot". Common cell: every hash bucket EQUAL, desyncSeen false on both, no new crash file. WV-D95: run in the
foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_tank_gate.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_tank_entry as TE  # noqa: E402
from test_battle_end_separate import log_count  # noqa: E402

PORT = "47612"
TANK, SKYR = TE.TANK, TE.SKYR
REFUSED = "[coop-guest-tank] host: partner tank STR_TANK_CANNON of seat 1 left out: no spare in the host's stores"
ROWS = (("T3", ("T3-park", "T3-store", "T3-one", "T3-refused", "T3-guest", "T3-common")),)


def pre_d(out):
    def pre(host, client, pins):
        ev, cells = out.setdefault("ev", {}), out.setdefault("cells", {})
        try:
            st, hv = TE.storage(host)[0], TE.craft_vehicles(host, pins["HOST_SKY"])
            p_ok, p_txt = TE.parked_cell(client, pins, "the partner's")
            ev["host"] = {"storage": st, "craft": hv}
            cells["T3-park"] = (st[TANK] == 0 and hv.get("vehicles") == {TANK: 1} and p_ok,
                                f"host storage {st} (want {TANK} 0); host craft_vehicles {pins['HOST_SKY']} {hv} (want "
                                f"{{{TANK}: 1}}); {p_txt}")
        except Exception as e:
            cells["T3-park"] = (False, f"probe failed: {type(e).__name__}: {str(e)[:300]}")
        try:
            _sent, cells["T3-store"] = TE.census_wait(host, client, ev)
        except Exception as e:
            cells["T3-store"] = (False, f"probe failed: {type(e).__name__}: {str(e)[:300]}")
    return pre


def row_t3(host, client, pins, pre, crash0):
    cells, ev = dict(pre.get("cells") or {}), dict(pre.get("ev") or {})
    ev.update(pins={k: pins[k] for k in ("HOST_BASE_COOP", "HOST_SKY", "CLIENT_SKY", "guest_id", "viewStores", "viewSpaceUsed")},
              units={"host": TE.unit_view(host), "partner": TE.unit_view(client)},
              hostLog=[ln for ln in TE.log_lines(host) if TE.GT_LOG in ln][-8:])
    th, tc = TE.tanks(host), TE.tanks(client)
    uh, uc = TE.units(host), TE.units(client)
    tv = [{"guestTank": (g.get(t[0]) or {}).get("guestTank", ""), "coop": (g.get(t[0]) or {}).get("coop")} if len(t) == 1
          else None for g, t in ((uh, th), (uc, tc))]
    cells["T3-one"] = (len(th) == 1 and th == tc and tv == [{"guestTank": "", "coop": 0}] * 2,
                       f"{TANK} units host/partner {th}/{tc} (want exactly one, the same id); guestTank / coop host/partner "
                       f"{tv} (want \"\" / 0)")
    n = log_count(host, REFUSED)
    cells["T3-refused"] = (n == 1, f"host log lines {REFUSED!r}: {n} (want exactly 1)")
    gs = [[(u.get("coop"), u.get("faction")) for u in g.values() if TE.GUEST in (u.get("name") or "")] for g in (uh, uc)]
    cells["T3-guest"] = (gs == [[(1, 0)], [(1, 0)]], f"{TE.GUEST!r} (coop, faction) host/partner {gs} (want one (1, 0) on both)")
    cells["T3-common"] = TE.boot_common(host, client, crash0)
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("d248u_d_host"))
    client = GameClient("client", None, make_user_dir("d248u_d_client"))
    fails, pre = 0, {}
    try:
        try:
            crash0 = session._crash_log_snapshot()
            pins = TE.guarded("D", lambda: TE.bring_up_tank_battle(host, client, PORT, host_soldiers=2, host_tank_on_craft=True,
                                                                   pre_mission=pre_d(pre)), (host, client))
            TE.guarded("D", lambda: session.pin_ai_neutral(host, client, tag="d248u"), (host, client))
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE D line)")
        else:
            fails += G3F.run_row("T3", ROWS[0][1], lambda: row_t3(host, client, pins, pre, crash0))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_tank_gate: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
