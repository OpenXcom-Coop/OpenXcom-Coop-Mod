"""Real-save regression for a client-owned ROSIGMA Valkyrie cannon mount."""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import GameClient, make_user_dir
import session
from test_separate_campaign_three_month_factions import (
    MOD_40K, MOD_ROSIGMA, require_mods)


SOURCE = os.environ.get(
    "ROSIGMA_CRAFT_TURRET_SAVE",
    r"C:\Users\arita\Documents\OpenXcom\40k\turret.sav")
SAVE = "separate_rosigma_client_craft_turret.sav"


def stage_save():
    user = make_user_dir(
        "sep_rosigma_craft_turret_host", saves=(SOURCE,),
        mods=(MOD_40K, MOD_ROSIGMA))
    master = os.path.join(user, "40k")
    os.makedirs(master, exist_ok=True)
    shutil.move(os.path.join(user, "xcom1", os.path.basename(SOURCE)),
                os.path.join(master, SAVE))
    return user


def cannon(machine):
    units = machine.ok({"cmd": "battle_state"})["units"]
    matches = [unit for unit in units
               if unit.get("faction") == 0
               and unit.get("weapon") == "STR_CAS_CANNON"]
    assert len(matches) == 1, matches
    return matches[0]


def main():
    require_mods(("the ROSIGMA craft-turret save", SOURCE))
    host = GameClient("host", 49670, stage_save())
    client = GameClient("client", 49671, make_user_dir(
        "sep_rosigma_craft_turret_client", mods=(MOD_40K, MOD_ROSIGMA)))
    try:
        host.spawn(); client.spawn()
        host.connect(timeout=180); client.connect(timeout=180)
        session.resume_campaign_battle(
            host, client, SAVE, port="48970", host_name="Player",
            client_name="Player2", timeout=240)

        host_cannon = cannon(host)
        client_cannon = cannon(client)
        assert host_cannon["id"] == client_cannon["id"], (
            host_cannon, client_cannon)
        assert host_cannon["coop"] == 1 and client_cannon["coop"] == 1, (
            host_cannon, client_cannon)
        assert host_cannon["selectable"] is False, host_cannon

        # The fixture may resume on the host's classic co-op turn. Ownership
        # must already exclude the host, but the client becomes selectable only
        # after the active side is handed to it.
        if not client_cannon["selectable"]:
            host.ok({"cmd": "battle_action", "action": "end_turn_button"})
            client.wait_for(
                "client receives control of its Valkyrie cannon",
                lambda: cannon(client) if cannon(client)["selectable"] else None,
                timeout=90, interval=0.5)
        client_cannon = cannon(client)
        host_cannon = cannon(host)
        assert client_cannon["selectable"] is True, client_cannon
        assert host_cannon["selectable"] is False, host_cannon
        print("PASS ROSIGMA client craft cannon is controllable only by Player2")
    finally:
        host.shutdown(); client.shutdown()


if __name__ == "__main__":
    main()
