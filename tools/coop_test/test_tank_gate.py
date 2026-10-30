"""The host's only tank is on its own craft and the partner parks "it" from the visited base (the view turns the host's
craft tank into a view item): ONE tank fights, the host's own; the partner's copy is left out because the host's stores
hold no spare of its type.

Each tank takes 30 shells, HOST_BASE_COOP is read on every boot, and the craft's vehicle list is asserted after every
craft_equip.

Boot (SEPARATE, port 47612, dirs tank_gate_host / tank_gate_client): test_tank_entry.bring_up_tank_battle(host, client,
"47612", host_soldiers=2, host_tank_on_craft=True) (the host's 2 soldiers + its tank = 6 of its half 7; the guest still
merges); pin_ai_neutral.
  only_host_tank: parked_on_craft (pre_mission: the host's storage 0 tanks, its Skyranger holds its tank; the partner's
  Skyranger holds the parked tank tagged [HOST_BASE_COOP, HOST_SKY, STR_SKYRANGER]), host_stored (the host's
  guestContrib.vehicles[1] 1), one_tank (in the battle, on both: exactly one STR_TANK_CANNON unit, guestTank "" (absent
  = ""), coop 0), spare_refused (the host log holds exactly one "no spare" line for seat 1), guest_merged ("Guest Zzz"
  in the battle on both, coop 1), gate_common.
Without the fix host_stored and spare_refused FAIL; every other cell PASS.

One EVIDENCE line, then one PASS/FAIL line per cell, then the row verdict. A boot step past its bound prints ONE CAPTURE
line and fails the row "boot". Common cell: every hash bucket EQUAL, desyncSeen false on both, no new crash file. Run in
the foreground to completion. ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

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
ROWS = (("only_host_tank",
         ("parked_on_craft", "host_stored", "one_tank", "spare_refused", "guest_merged", "gate_common")),)


def pre_tank_gate(out):
    def pre(host, client, pins):
        ev, cells = out.setdefault("ev", {}), out.setdefault("cells", {})
        try:
            st, hv = TE.storage(host)[0], TE.craft_vehicles(host, pins["HOST_SKY"])
            p_ok, p_txt = TE.parked_cell(client, pins, "the partner's")
            ev["host"] = {"storage": st, "craft": hv}
            cells["parked_on_craft"] = (st[TANK] == 0 and hv.get("vehicles") == {TANK: 1} and p_ok,
                                        f"host storage {st} (want {TANK} 0); host craft_vehicles "
                                        f"{pins['HOST_SKY']} {hv} (want {{{TANK}: 1}}); {p_txt}")
        except Exception as e:
            cells["parked_on_craft"] = (False, f"probe failed: {type(e).__name__}: {str(e)[:300]}")
        try:
            _sent, cells["host_stored"] = TE.census_wait(host, client, ev)
        except Exception as e:
            cells["host_stored"] = (False, f"probe failed: {type(e).__name__}: {str(e)[:300]}")
    return pre


def row_only_host_tank(host, client, pins, pre, crash0):
    cells, ev = dict(pre.get("cells") or {}), dict(pre.get("ev") or {})
    ev.update(pins={k: pins[k] for k in ("HOST_BASE_COOP", "HOST_SKY", "CLIENT_SKY", "guest_id", "viewStores", "viewSpaceUsed")},
              units={"host": TE.unit_view(host), "partner": TE.unit_view(client)},
              hostLog=[ln for ln in TE.log_lines(host) if TE.GT_LOG in ln][-8:])
    th, tc = TE.tanks(host), TE.tanks(client)
    uh, uc = TE.units(host), TE.units(client)
    tv = [{"guestTank": (g.get(t[0]) or {}).get("guestTank", ""), "coop": (g.get(t[0]) or {}).get("coop")} if len(t) == 1
          else None for g, t in ((uh, th), (uc, tc))]
    cells["one_tank"] = (len(th) == 1 and th == tc and tv == [{"guestTank": "", "coop": 0}] * 2,
                         f"{TANK} units host/partner {th}/{tc} (want exactly one, the same id); guestTank / coop "
                         f"host/partner {tv} (want \"\" / 0)")
    n = log_count(host, REFUSED)
    cells["spare_refused"] = (n == 1, f"host log lines {REFUSED!r}: {n} (want exactly 1)")
    gs = [[(u.get("coop"), u.get("faction")) for u in g.values() if TE.GUEST in (u.get("name") or "")] for g in (uh, uc)]
    cells["guest_merged"] = (gs == [[(1, 0)], [(1, 0)]],
                             f"{TE.GUEST!r} (coop, faction) host/partner {gs} (want one (1, 0) on both)")
    cells["gate_common"] = TE.boot_common(host, client, crash0)
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("tank_gate_host"))
    client = GameClient("client", None, make_user_dir("tank_gate_client"))
    fails, pre = 0, {}
    try:
        try:
            crash0 = session._crash_log_snapshot()
            pins = TE.guarded("gate_battle", lambda: TE.bring_up_tank_battle(host, client, PORT, host_soldiers=2,
                                                                             host_tank_on_craft=True,
                                                                             pre_mission=pre_tank_gate(pre)),
                              (host, client))
            TE.guarded("gate_battle", lambda: session.pin_ai_neutral(host, client, tag="tank_gate"), (host, client))
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE gate_battle line)")
        else:
            fails += G3F.run_row("only_host_tank", ROWS[0][1],
                                 lambda: row_only_host_tank(host, client, pins, pre, crash0))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_tank_gate: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
