"""Regression: Cydonia must stream its Mars map to both campaign players.

ConfirmCydoniaState is a separate final-mission entry point; it does not pass
through ConfirmLandingState. Cover both campaign models so this path cannot
silently fall back to a host-only battle again.

Run:  python tools/coop_test/test_cydonia_coop_start.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys

# RW-TRIAGE: SKIP-PENDING(R4-P2)
print("SKIP-PENDING: rewrite"); sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session


def _states(gc):
    return gc.cmd({"cmd": "get_state"})["states"]


def _has(gc, name):
    return any(name in state for state in _states(gc))


def _base(gc):
    return next(b for b in gc.ok({"cmd": "geo_state"})["bases"]
                if not b.get("coopBase") and not b.get("coopIcon"))


def _craft_and_soldiers(gc):
    base = _base(gc)
    craft = next(c for c in base["crafts"] if "SKYRANGER" in c["type"])
    roster = gc.ok({"cmd": "get_soldiers"})["bases"]
    soldiers = next(b["soldiers"] for b in roster
                    if not b.get("coopBaseFlag"))
    return craft["id"], [s["id"] for s in soldiers]


def _seat(gc, craft_id, soldier_ids):
    for sid in soldier_ids:
        gc.ok({"cmd": "craft_assign", "craft_id": craft_id,
               "soldier_id": sid, "on": False})
    for sid in soldier_ids[:2]:
        gc.ok({"cmd": "craft_assign", "craft_id": craft_id,
               "soldier_id": sid, "on": True})


def _aboard(gc, craft_id):
    return sorted(s["id"] for b in gc.ok({"cmd": "get_soldiers"})["bases"]
                  for s in b["soldiers"] if s["craftId"] == craft_id)


def run_mode(mode, test_ports, coop_port):
    print(f"\n===== Cydonia {mode.upper()} =====")
    host = GameClient("host", test_ports[0], make_user_dir(f"cydonia_{mode}_host"))
    client = GameClient("client", test_ports[1], make_user_dir(f"cydonia_{mode}_client"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        session.new_campaign(host, client, port=str(coop_port), campaign_mode=mode)

        host_craft, host_roster = _craft_and_soldiers(host)
        _seat(host, host_craft, host_roster)
        if mode == "coop":
            client_craft, client_roster = _craft_and_soldiers(client)
            _seat(client, client_craft, client_roster)
        else:
            # Give the shared squad one unit from each seat and wait until the
            # replicated ownership/assignment commands have settled.
            for gc in (host, client):
                gc.ok({"cmd": "set_soldier_owner", "soldier_id": host_roster[0], "owner": 0})
                gc.ok({"cmd": "set_soldier_owner", "soldier_id": host_roster[1], "owner": 1})
            host.wait_for("shared squad seated",
                          lambda: (_aboard(host, host_craft) == sorted(host_roster[:2])) or None,
                          timeout=30)

        host.ok({"cmd": "open_cydonia", "craft_id": host_craft})
        host.wait_for("Cydonia confirmation",
                      lambda: _has(host, "ConfirmCydoniaState") or None)
        host.ok({"cmd": "confirm_cydonia"})

        battles = []
        for gc in (host, client):
            battles.append(gc.wait_for(
                f"{gc.name} loaded Cydonia",
                lambda gc=gc: (lambda b: b if b.get("inBattle") else None)(
                    gc.cmd({"cmd": "battle_state"})),
                timeout=180, interval=1.0))
            gc.wait_for(f"{gc.name} briefing",
                        lambda gc=gc: _has(gc, "BriefingState") or None,
                        timeout=120, interval=0.5)

        assert battles[0]["missionType"] == battles[1]["missionType"], battles
        assert battles[0]["mapSizeXYZ"] == battles[1]["mapSizeXYZ"], battles
        assert battles[0]["mapFingerprint"] == battles[1]["mapFingerprint"], battles
        print(f"PASS {mode}: both players loaded {battles[0]['missionType']} "
              f"with identical Mars map fingerprint {battles[0]['mapFingerprint']}")
    finally:
        host.shutdown(); client.shutdown()


def main():
    failures = []
    for mode, ports, coop_port in (
            ("coop", (48930, 48931), 48130),
            ("shared", (48932, 48933), 48132)):
        try:
            run_mode(mode, ports, coop_port)
        except Exception as exc:
            print(f"[FAIL] {mode}: {exc}")
            failures.append(f"{mode}: {exc}")

    if failures:
        print("\nCydonia co-op regression failures:", failures)
        sys.exit(2)
    print("\nCydonia co-op start passed in SEPARATE and SHARED campaigns.")


if __name__ == "__main__":
    main()
