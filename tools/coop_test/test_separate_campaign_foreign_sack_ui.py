"""Sacking the last owned soldier at a foreign base closes Soldier Info."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import separate_campaign_fixture as fixture
from test_separate_visitor_actions import hire_guests


def states(machine):
    return machine.ok({"cmd": "get_state"})["states"]


def has(machine, state):
    return any(state in name for name in states(machine))


def main():
    js = fixture.bring_up(
        "sep_foreign_sack_ui", (49772, 49773, 49072))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        guest = hire_guests(host, client, 1)[0]

        client.ok({"cmd": "open_soldier_info", "base": "HostBase",
                   "soldierId": guest})
        client.wait_for("foreign SoldierInfo opened",
                        lambda: has(client, "SoldierInfoState") or None)
        client.ok({"cmd": "sack", "base": "HostBase", "soldierId": guest})
        client.wait_for(
            "last owned foreign soldier closes SoldierInfo",
            lambda: (not has(client, "SoldierInfoState")) or None,
            timeout=30, interval=0.25)
        assert not has(client, "SoldierInfoState"), states(client)
        print("PASS sacking the last owned soldier at a foreign base closes Soldier Info")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
