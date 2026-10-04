"""ROSIGMA Separate Campaign: observe three faction-aware month rolls.

This is a real two-process mod-loaded run.  Marines (difficulty/faction 0) and
Adeptas (3) must retain distinct private faction progression while the host
keeps one authoritative world.  Every month prints all live strategic targets
and their player-name owner; empty owner is reported as Shared.

The harness clears a pending campaign ending while advancing.  This is deliberate:
the test is about faction scheduling, not whether unattended bases lose the war.

Run from the repository root after compiling:
  python -u tools/coop_test/test_separate_campaign_three_month_factions.py
"""

import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import shared_fixture


DEFAULT_MOD_ROOT = os.path.join(os.path.expanduser("~"), "Documents", "OpenXcom", "mods")
MOD_40K = os.environ.get("OXC_40K_MOD", os.path.join(DEFAULT_MOD_ROOT, "40k"))
MOD_ROSIGMA = os.environ.get("OXC_ROSIGMA_MOD", os.path.join(DEFAULT_MOD_ROOT, "rosigma"))


def snapshot(gc):
    return gc.ok({"cmd": "separate_faction_mission_state"})


def owner_summary(state):
    result = Counter()
    for key in ("alienMissions", "missionSites", "alienBases"):
        for item in state.get(key, []):
            result[item.get("ownerPlayerName") or "Shared"] += 1
    return dict(sorted(result.items()))


def print_state(label, state):
    print(f"\n[{label}] monthsPassed={state['monthsPassed']} ending={state['ending']}")
    for player in state["players"]:
        interesting = sorted(topic for topic in
                             player["factionResearch"] + player["completedResearch"]
                             if any(word in topic for word in
                                    ("MARINES", "ADEPTAS", "CHAMBER", "ARBITES",
                                     "IMPERIAL_GUARD", "STRATEGY")))
        print(f"  {player['name']}: {player['faction']} faction topics={interesting}")
    print(f"  target owners: {owner_summary(state)}")
    for key in ("alienMissions", "missionSites", "alienBases"):
        for item in state.get(key, []):
            print(f"    {key}: {item['type']} owner="
                  f"{item.get('ownerPlayerName') or 'Shared'}")


def roll_one_month(host, client, old_month):
    host.ok({"cmd": "set_geo_day", "day": 28, "hour": 0})
    deadline = time.time() + 180
    while time.time() < deadline:
        for gc in (host, client):
            if gc.proc.poll() is not None:
                raise AssertionError(f"{gc.name} exited during month roll: {gc.proc.returncode}")
            state = snapshot(gc)
            if state["ending"] != 0:
                gc.ok({"cmd": "set_ending", "ending": 0})
            geo.drain_popups(gc)
            if geo.on_geoscape(gc):
                gc.ok({"cmd": "geo_set_speed", "idx": 5})
        current = snapshot(host)["monthsPassed"]
        if current > old_month:
            client.wait_for("client received month roll",
                            lambda: snapshot(client)["monthsPassed"] >= current or None,
                            timeout=45, interval=0.5)
            # Clear the monthly report and any detection dialogs, then freeze.
            for gc in (host, client):
                geo.drain_popups(gc)
                gc.ok({"cmd": "set_ending", "ending": 0})
                if geo.on_geoscape(gc):
                    gc.ok({"cmd": "geo_set_speed", "idx": 0})
            return current
        time.sleep(0.25)
    raise AssertionError(f"month did not advance beyond {old_month}")


def main():
    for path in (MOD_40K, MOD_ROSIGMA):
        if not os.path.isdir(path):
            raise SystemExit(f"required mod directory not found: {path}")

    js = shared_fixture.bring_up(
        "sep_40k_3month_v9", (48984, 48985, 48284),
        mods=(MOD_40K, MOD_ROSIGMA), campaign_mode="coop",
        host_difficulty=0, client_difficulty=3, transport="tcp")
    host, client = js.host, js.client
    try:
        host.ok({"cmd": "set_option", "name": "EnableResearchSync", "value": False})
        host.ok({"cmd": "set_seed", "seed": 40003})
        client.ok({"cmd": "set_seed", "seed": 40003})

        initial = snapshot(host)
        print_state("campaign start", initial)
        factions = {p["name"]: p["faction"] for p in initial["players"]}
        assert factions.get("HostPlayer") == "difficulty:0", factions
        assert factions.get("ClientPlayer") == "difficulty:3", factions

        seen_owners = Counter(owner_summary(initial))
        month = initial["monthsPassed"]
        for number in range(1, 4):
            month = roll_one_month(host, client, month)
            state = snapshot(host)
            print_state(f"after roll {number}", state)
            seen_owners.update(owner_summary(state))
            assert state["ending"] == 0, state
            assert snapshot(client)["monthsPassed"] == month

        final = snapshot(host)
        final_factions = {p["name"]: p["faction"] for p in final["players"]}
        assert final_factions.get("HostPlayer") == "difficulty:0", final_factions
        assert final_factions.get("ClientPlayer") == "difficulty:3", final_factions
        assert "HostPlayer" in seen_owners, \
            f"no HostPlayer-owned faction target in three months: {dict(seen_owners)}"
        assert "ClientPlayer" in seen_owners, \
            f"no ClientPlayer-owned faction target in three months: {dict(seen_owners)}"
        assert "Shared" in seen_owners, \
            f"normal shared target stream disappeared: {dict(seen_owners)}"
        print("\nPASS three-month ROSIGMA Separate run: both faction selections, "
              "both player-owned target streams and shared targets appeared "
              "without Game Over")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
