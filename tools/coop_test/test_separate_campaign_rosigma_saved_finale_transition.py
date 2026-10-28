"""Reproduce a ROSIGMA finale transition from a real stage-2 battle save.

Unlike the synthetic finale harness, this test kills the live enemies through
the normal casualty path and advances turns until the mission changes stage.
During the transfer the client must remain covered by its loading state; the
old Battlescape must never become the top state before the new briefing.

By default the test uses the local manual-test save. Override it with
ROSIGMA_FINALE_SAVE when running on another machine.
"""

import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import GameClient, make_user_dir
import session
from test_separate_campaign_three_month_factions import MOD_40K, MOD_ROSIGMA


SAVE_SRC = os.environ.get(
    "ROSIGMA_FINALE_SAVE",
    r"C:\Users\arita\Documents\OpenXcom\40k\battle2_2.sav")
SAVE_NAME = "separate_rosigma_finale_stage2_fixture.sav"
PORT = "48941"


def states(machine):
    return machine.cmd({"cmd": "get_state"}).get("states", [])


def top(machine):
    current = states(machine)
    return current[-1].split("::")[-1] if current else ""


def battle(machine):
    return machine.cmd({"cmd": "battle_state"})


def live_hostiles(machine):
    return [unit for unit in battle(machine).get("units", [])
            if unit.get("faction") == 1 and not unit.get("isOut")]


def stage_save(source):
    host_dir = make_user_dir(
        "sep_rosigma_saved_finale_host", saves=(source,),
        mods=(MOD_40K, MOD_ROSIGMA))
    master_dir = os.path.join(host_dir, "40k")
    os.makedirs(master_dir, exist_ok=True)
    staged = os.path.join(host_dir, "xcom1", os.path.basename(source))
    target = os.path.join(master_dir, SAVE_NAME)
    shutil.move(staged, target)
    return host_dir


def dismiss_transition_ui(machine):
    current_top = top(machine)
    if current_top == "CoopDesyncNoticeState":
        machine.ok({"cmd": "dismiss_popup"})
    elif current_top == "NextTurnState":
        machine.ok({"cmd": "close_nextturn"})


def main():
    if not os.path.isfile(SAVE_SRC):
        print("SKIP: ROSIGMA finale save not found: " + SAVE_SRC)
        return

    host_dir = stage_save(SAVE_SRC)
    client_dir = make_user_dir(
        "sep_rosigma_saved_finale_client", mods=(MOD_40K, MOD_ROSIGMA))
    host = GameClient("host", 49640, host_dir)
    client = GameClient("client", 49641, client_dir)
    try:
        host.spawn(); client.spawn()
        host.connect(timeout=180); client.connect(timeout=180)
        try:
            session.resume_campaign_battle(
                host, client, SAVE_NAME, port=PORT, timeout=240)
        except TimeoutError:
            print("host lobby:", host.cmd({"cmd": "lobby_state"}))
            print("client lobby:", client.cmd({"cmd": "lobby_state"}))
            raise

        initial = battle(host).get("missionType")
        assert initial == "STR_MARS_CYDONIA_ENTRANCE", initial
        print("resumed real ROSIGMA stage-2 battle: " + initial)

        deadline = time.time() + 300
        turn = 0
        transition_started = False
        client_briefings = 0
        new_stage = None
        while time.time() < deadline:
            dismiss_transition_ui(host)
            dismiss_transition_ui(client)

            host_battle = battle(host)
            client_battle = battle(client)
            host_mission = host_battle.get("missionType")
            client_mission = client_battle.get("missionType")

            if host_mission != initial:
                transition_started = True
                new_stage = host_mission

            client_top = top(client)
            if transition_started and client_top == "BattlescapeState":
                raise AssertionError(
                    "client exposed BattlescapeState between map download and "
                    "the new-stage briefing: " + str(states(client)))

            if client_top == "BriefingState":
                client_briefings += 1
                assert client_briefings == 1, states(client)
                client.ok({"cmd": "close_briefing"})
            if top(host) == "BriefingState":
                host.ok({"cmd": "close_briefing"})

            if (new_stage and client_mission == new_stage
                    and client_briefings == 1
                    and top(client) != "BriefingState"):
                assert not any("InventoryState" in name for name in states(client)), \
                    states(client)
                print("PASS: real save reached %s with one client briefing and "
                      "no exposed old Battlescape" % new_stage)
                return

            # Match the manual Ctrl+K repro: remove every current hostile, then
            # advance the turn. ROSIGMA may spawn a new wave, so repeat until
            # the scripted next stage starts.
            if not transition_started and top(host) == "BattlescapeState":
                hostile_count = len(live_hostiles(host))
                if hostile_count:
                    turn += 1
                    print("turn %d: killing %d live hostile(s)" %
                          (turn, hostile_count))
                    result = host.ok({
                        "cmd": "battle_action", "action": "kill_unit",
                        "faction": 1})
                    assert result.get("killed"), result
                    time.sleep(2)
                    remaining = len(live_hostiles(host))
                    print("turn %d: %d hostile(s) remain after Ctrl+K" %
                          (turn, remaining))
                    host.ok({"cmd": "battle_autoend"})
                    time.sleep(.5)
                    if top(host) == "NextTurnState":
                        host.ok({"cmd": "close_nextturn"})

            time.sleep(.1)

        raise AssertionError({
            "reason": "timed out before the real finale transition completed",
            "hostStates": states(host), "clientStates": states(client),
            "hostBattle": battle(host), "clientBattle": battle(client)})
    finally:
        host.shutdown(); client.shutdown()


if __name__ == "__main__":
    main()
