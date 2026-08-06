"""Regression test for double-TU on turn (commit 76d057644).

Before the fix, UnitTurnBState::init() spent TUs to gate the turn-sync
packet, and think() spent them again during the turn animation. A 1/8
turn (one direction step) cost 2 TU instead of 1 on BOTH machines: the
host double-charged locally, and the client mirrored the already-double-
charged TU and then charged once more via the replayed turn state.

The fix (76d057644):
  - moved the turn-sync packet from init() to deinit()
  - client replay uses chargeTUs=false (TU already mirrored from host)
  - think() is the single place that charges turn TUs

The test turns a soldier 1/8 step clockwise and asserts:
  1. TU decreased by exactly 1 on BOTH host and client.
  2. Host and client TU match after the turn.

If the double-charge returns, the decrease is 2+ TU per 1/8 turn.

Run:  python tools/coop_test/test_coop_double_turn_tu.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import test_shared_battle as B


def _aboard(gc, cid):
    return sorted(s["id"] for s in B._roster(gc) if s["craftId"] == cid)


def _top(gc):
    return gc.cmd({"cmd": "get_state"})["states"][-1].split("::")[-1]


def _drain_to_tactical(host, client, rounds=8):
    for _ in range(rounds):
        moved = False
        for gc in (host, client):
            if _top(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
                moved = True
        time.sleep(1.0)
        if not moved and all(_top(gc) == "BattlescapeState" for gc in (host, client)):
            return


def _bstate(gc):
    return gc.cmd({"cmd": "battle_state"})


def _tu(gc, uid):
    for u in _bstate(gc).get("units", []):
        if u["id"] == uid:
            return u["tu"]
    return None


def main():
    js = shared_fixture.bring_up("dbltu", (48992, 48993, 48192))
    host, client = js.host, js.client
    try:
        owner = {s["id"]: s["owner"] for s in B._roster(host)}
        seat0 = sorted(sid for sid, o in owner.items() if o == 0)
        assert len(seat0) >= 2, f"need >=2 host soldiers: {seat0}"
        cid = B._skyranger(host)["id"]
        for sid in owner:
            host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False})
        squad = seat0[:2]
        for sid in squad:
            host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})
        host.wait_for("squad aboard",
                      lambda: (_aboard(host, cid) == sorted(squad)) or None,
                      timeout=45, interval=0.5)

        b0 = B._base0(host)
        blon, blat = b0["lon"], b0["lat"]
        site_id = host.ok({"cmd": "spawn_mission_site",
                           "mission": "STR_ALIEN_TERROR",
                           "deployment": "STR_TERROR_MISSION",
                           "lon": blon + 0.35, "lat": blat + 0.10,
                           "race": "STR_SECTOID", "hours": 240})["site_id"]
        host.wait_for("site on host",
                      lambda: any(s["id"] == site_id
                                  for s in B._geo(host)["missionSites"]) or None,
                      timeout=30)
        host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
                 "lon": blon + 0.34, "lat": blat + 0.10,
                 "dest": f"site:{site_id}", "fuel": 999999, "lowFuel": False})

        def _landing():
            if B._has(host, "ConfirmLandingState"):
                return True
            host.cmd({"cmd": "geo_set_speed", "idx": 2})
            return None
        host.wait_for("landing prompt", _landing, timeout=90, interval=0.5)
        host.ok({"cmd": "confirm_landing"})

        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} in battle",
                        lambda gc=gc: B._battle(gc).get("inBattle") or None,
                        timeout=180, interval=1.0)
        for gc in (host, client):
            gc.wait_for("briefing",
                        lambda gc=gc: B._has(gc, "BriefingState") or None,
                        timeout=30, interval=0.5)
            gc.ok({"cmd": "close_briefing"})
        for gc in (host, client):
            gc.wait_for("inventory",
                        lambda gc=gc: B._has(gc, "InventoryState") or None,
                        timeout=30, interval=0.5)
            gc.ok({"cmd": "battle_inventory", "action": "ok"})
        _drain_to_tactical(host, client)

        host.wait_for("host turn active",
                      lambda: (B._battle(host).get("coopTurn") == 2) or None,
                      timeout=30, interval=0.5)
        time.sleep(2)

        # Pick any host-owned soldier with TUs
        hb = B._battle(host)
        shooters = [u for u in hb["units"]
                    if u.get("soldierId") in squad
                    and not u.get("isOut")
                    and u.get("tu", 0) >= 2]
        assert shooters, "no host soldier with >=2 TU"
        sid = shooters[0]["id"]
        print(f"soldier id={sid} soldierId={shooters[0]['soldierId']} "
              f"tu={shooters[0]['tu']} dir={shooters[0].get('direction','?')}")

        host.cmd({"cmd": "battle_action", "action": "select", "unit": sid})

        # Record TU before the turn
        tu_h_before = _tu(host, sid)
        tu_c_before = _tu(client, sid)
        assert tu_h_before == tu_c_before, \
            f"TU mismatch before turn: host={tu_h_before} client={tu_c_before}"

        # Execute a pure 1/8 turn clockwise
        res = host.cmd({"cmd": "battle_action", "action": "turn", "unit": sid})
        assert res.get("ok"), f"turn action failed: {res}"

        # Wait for turn animation to complete
        time.sleep(3.0)
        _drain_to_tactical(host, client, rounds=4)

        # Record TU after
        tu_h_after = _tu(host, sid)
        tu_c_after = _tu(client, sid)

        h_cost = tu_h_before - tu_h_after
        c_cost = tu_c_before - tu_c_after

        print(f"TU: host {tu_h_before}->{tu_h_after} (cost={h_cost}) "
              f"client {tu_c_before}->{tu_c_after} (cost={c_cost})")

        # A 1/8 turn costs exactly 1 TU for XCOM soldiers
        assert h_cost == 1, \
            f"host paid {h_cost} TU for a 1/8 turn (expected 1). " \
            f"If >=2, the double-TU bug returned on the host."
        assert c_cost == 1, \
            f"client paid {c_cost} TU for a 1/8 turn (expected 1). " \
            f"If >=2, the double-TU bug returned on the client."
        assert tu_h_after == tu_c_after, \
            f"TU mismatch after turn: host={tu_h_after} client={tu_c_after}"

        print(f"PASS: 1/8 turn cost exactly 1 TU on both machines "
              f"(host={tu_h_after} client={tu_c_after})")
        print("DOUBLE-TU REGRESSION TEST PASSED")

    finally:
        js.shutdown()

    print("DONE")


if __name__ == "__main__":
    main()
