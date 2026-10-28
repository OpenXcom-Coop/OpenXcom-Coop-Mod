"""Client-owned ROSIGMA finale survives its first multi-stage map transfer."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import shared_fixture
from test_separate_campaign_three_month_factions import MOD_40K, MOD_ROSIGMA
from test_separate_campaign_rosigma_faction_finales import (
    prepare_faction_force, start_finale, top, has,
)


def main():
    js = shared_fixture.bring_up(
        "sep_rosigma_client_finale_transition", (49620, 49621, 48920),
        mods=(MOD_40K, MOD_ROSIGMA), campaign_mode="coop",
        host_difficulty=0, client_difficulty=3, transport="tcp")
    host, client = js.host, js.client
    try:
        craft = prepare_faction_force(
            host, client, "ClientPlayer", 1, "ClientBase",
            "STR_LANDRAIDER", "STR_CANONESS")
        start_finale(
            host, client, "ClientPlayer", "ClientBase", craft,
            "STR_FINAL_MISSION_ADEPTAS", "STR_MARS_CYDONIA_LANDING_ADEPTAS")

        before = host.ok({"cmd": "battle_state"})
        assert before["battleOwnerPlayerName"] == "ClientPlayer", before
        assert before["missionType"] == "STR_MARS_CYDONIA_LANDING_ADEPTAS", before
        host.ok({"cmd": "battle_action", "action": "finish_victory"})

        deadline = time.time() + 180
        client_briefing_closed = False
        while time.time() < deadline:
            for gc in (host, client):
                if top(gc) == "CoopDesyncNoticeState":
                    gc.ok({"cmd": "dismiss_popup"})
                if top(gc) == "BriefingState":
                    current = gc.ok({"cmd": "get_state"}).get("states", [])
                    assert sum("BriefingState" in state for state in current) == 1, current
                    gc.ok({"cmd": "close_briefing"})
                    if gc is client:
                        client_briefing_closed = True
                        try:
                            client.wait_for("single client briefing closes",
                                lambda: (lambda current: current if not any(
                                    "BriefingState" in state for state in current) else None)(
                                        client.ok({"cmd": "get_state"}).get("states", [])),
                                timeout=5, interval=.1)
                        except TimeoutError as error:
                            raise AssertionError(client.ok({"cmd": "get_state"})) from error
                        time.sleep(.5)
                        after = client.ok({"cmd": "get_state"}).get("states", [])
                        assert not any("BriefingState" in state for state in after), after
                        assert not any("InventoryState" in state for state in after), after
                if has(gc, "InventoryState"):
                    gc.ok({"cmd": "battle_inventory", "action": "ok"})
                if gc is host and top(gc) == "NextTurnState":
                    gc.cmd({"cmd": "close_nextturn"})
            host_battle = host.cmd({"cmd": "battle_state"})
            client_battle = client.cmd({"cmd": "battle_state"})
            if (client_battle.get("missionType") ==
                    "STR_MARS_CYDONIA_ENTRANCE_ADEPTAS" and not client_briefing_closed):
                assert top(client) != "BattlescapeState", client.ok({"cmd": "get_state"})
            if (host_battle.get("missionType") == "STR_MARS_CYDONIA_ENTRANCE_ADEPTAS"
                    and client_battle.get("missionType") ==
                    "STR_MARS_CYDONIA_ENTRANCE_ADEPTAS"
                    and client_briefing_closed):
                assert host_battle["battleOwnerPlayerName"] == "ClientPlayer", host_battle
                assert client_battle["battleOwnerPlayerName"] == "ClientPlayer", client_battle
                print("PASS client ROSIGMA finale transferred to stage 2 without a crash")
                return
            time.sleep(.25)
        raise AssertionError({"host": host_battle, "client": client_battle})
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
