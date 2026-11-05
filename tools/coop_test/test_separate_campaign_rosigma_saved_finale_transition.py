"""Reproduce a ROSIGMA finale transition from a real stage-2 battle save.

Unlike the synthetic finale harness, this test kills the live enemies through
the normal casualty path and advances turns until the mission changes stage.
During the transfer the client must remain covered by its loading state; the
old Battlescape must never become the top state before the new briefing.

The test makes its own save: the host's Space Marines finale is played through
its first stage, and the host quick-saves once both machines are on stage 2.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import GameClient, make_user_dir
import session
import shared_fixture
from test_separate_campaign_three_month_factions import (
    MOD_40K, MOD_ROSIGMA, require_mods)
from test_separate_campaign_rosigma_faction_finales import (
    prepare_faction_force, start_finale)


TAG = "sep_rosigma_saved_finale"
STAGE_ONE = "STR_MARS_CYDONIA_LANDING"
STAGE_TWO = "STR_MARS_CYDONIA_ENTRANCE"
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


def win_stage_one(host):
    result = None
    for _ in range(10):
        result = host.cmd({"cmd": "battle_action", "action": "finish_victory"})
        if result.get("ok"):
            return
        if ("Access violation" not in result.get("error", "")
                and result.get("error") != "not in battlescape"):
            break
        time.sleep(.5)
    raise AssertionError(result)


def reach_stage_two(host, client, timeout=240):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for machine in (host, client):
            current_top = top(machine)
            if current_top == "BriefingState":
                machine.cmd({"cmd": "close_briefing"})
            elif current_top == "InventoryState":
                machine.cmd({"cmd": "battle_inventory", "action": "ok"})
            elif current_top == "NextTurnState":
                machine.cmd({"cmd": "close_nextturn"})
        if all(top(machine) == "BattlescapeState"
               and battle(machine).get("missionType") == STAGE_TWO
               for machine in (host, client)):
            return
        time.sleep(.25)
    raise AssertionError({machine.name: {
        "states": states(machine),
        "missionType": battle(machine).get("missionType")}
        for machine in (host, client)})


def make_save():
    """The host's Marines finale saved on its second stage."""
    js = shared_fixture.bring_up(
        TAG, (49640, 49641, 48940), mods=(MOD_40K, MOD_ROSIGMA),
        campaign_mode="coop", host_difficulty=0, client_difficulty=3,
        transport="tcp")
    host, client = js.host, js.client
    try:
        craft = prepare_faction_force(host, client, "HostPlayer", 0, "HostBase",
                                      "STR_CHAPTERARMY", "STR_PRIMARISLV1")
        start_finale(host, client, "HostPlayer", "HostBase", craft,
                     "STR_FINAL_MISSION_MARINES", STAGE_ONE)
        win_stage_one(host)
        reach_stage_two(host, client)
        before = set(session.save_files(host.user_dir))
        host.ok({"cmd": "save_game_ui", "type": "quick_battle"})
        host.wait_for("host quick-save written",
                      lambda: sorted(set(session.save_files(host.user_dir)) - before) or None,
                      timeout=60, interval=0.5)
        saved = sorted(set(session.save_files(host.user_dir)) - before)
        assert len(saved) == 1 and saved[0].endswith(".asav"), saved
        print(f"made save {saved[0]} on {STAGE_TWO}")
        return host.user_dir, os.path.basename(saved[0])
    finally:
        js.shutdown()


def dismiss_transition_ui(machine):
    current_top = top(machine)
    if current_top == "CoopDesyncNoticeState":
        machine.ok({"cmd": "dismiss_popup"})
    elif current_top == "NextTurnState":
        machine.ok({"cmd": "close_nextturn"})


def main():
    # Local-only (no SKIP pass): the mods must exist.
    require_mods()

    host_dir, save_name = make_save()
    client_dir = make_user_dir(TAG + "_client2", mods=(MOD_40K, MOD_ROSIGMA))
    host = GameClient("host", 49642, host_dir)
    client = GameClient("client", 49643, client_dir)
    try:
        host.spawn(); client.spawn()
        host.connect(timeout=180); client.connect(timeout=180)
        try:
            session.resume_campaign_battle(
                host, client, save_name, port=PORT, timeout=240)
        except TimeoutError:
            print("host lobby:", host.cmd({"cmd": "lobby_state"}))
            print("client lobby:", client.cmd({"cmd": "lobby_state"}))
            raise
        session.press_back_when_shown(host, "host RESUME", codes=(60, 62))
        for machine in (host, client):
            machine.wait_for(f"{machine.name} on the resumed battle",
                             lambda machine=machine: top(machine) == "BattlescapeState" or None,
                             timeout=90, interval=.5)

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
