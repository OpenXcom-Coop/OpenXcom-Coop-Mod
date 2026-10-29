"""Create a two-player separate-campaign save for manual ROSIGMA finale testing.

The save contains a Space Marines host and an Adeptas client.  Their faction
finale research prerequisites are complete, but no final mission site is
inserted directly.  ROSIGMA's own mission scripts must create the finales.
"""
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import shared_fixture
import geo
from test_separate_campaign_three_month_factions import MOD_40K, MOD_ROSIGMA
from test_separate_campaign_rosigma_faction_finales import prepare_faction_force


SAVE_NAME = "rosigma_separate_finale_manual_test.sav"
OUTPUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", SAVE_NAME))


def add_topic(host, client, player, topic):
    # Keep the live worlds usable and persist the prerequisite in the owning
    # Separate profile, which is what faction-scoped mission generation reads.
    for gc in (host, client):
        gc.ok({"cmd": "discover_research", "topic": topic})
    host.ok({"cmd": "separate_profile_set", "player": player,
             "completedResearch": topic})


def main():
    js = shared_fixture.bring_up(
        "make_rosigma_finale_manual_save", (49610, 49611, 48910),
        mods=(MOD_40K, MOD_ROSIGMA), campaign_mode="coop",
        host_difficulty=0, client_difficulty=3, transport="tcp")
    try:
        # Space Marines finale requirements. STR_MARINES_STRATEGY is supplied
        # by faction selection, but recording it explicitly makes the fixture
        # independent of delayed opening events.
        for topic in ("STR_CYDONIA_OR_BUST", "STR_MARINES_STRATEGY",
                      "STR_CHAPTER_PURITY", "STR_NOT_SPACEWOLVES"):
            add_topic(js.host, js.client, "HostPlayer", topic)

        # Adeptas finale requirements.
        for topic in ("STR_CYDONIA_OR_BUST", "STR_ADEPTAS",
                      "STR_LANDRAIDER_ADEPTAS"):
            add_topic(js.host, js.client, "ClientPlayer", topic)

        # This is deliberately a fake late-game fixture. Keep both factions far
        # away from a monthly score defeat while the tester waits for finales.
        for player in ("HostPlayer", "ClientPlayer"):
            js.host.ok({"cmd": "separate_profile_set", "player": player,
                        "factionScore": 100000})
        for gc in (js.host, js.client):
            gc.ok({"cmd": "set_funds", "value": 100000000})

        # Give each faction the real transport and crew accepted by its finale.
        prepare_faction_force(js.host, js.client, "HostPlayer", 0,
                              "HostBase", "STR_CHAPTERARMY", "STR_PRIMARISLV1")
        prepare_faction_force(js.host, js.client, "ClientPlayer", 1,
                              "ClientBase", "STR_LANDRAIDER", "STR_CANONESS")

        # Research side effects can leave Ufopaedia/event dialogs on either
        # peer. Close them before attempting to advance the strategic clock.
        for gc in (js.host, js.client):
            geo.drain_popups(gc)

        # Move close to the monthly mission-script pass, then let ROSIGMA itself
        # create the real AlienMission. The landing site is its first wave.
        for gc in (js.host, js.client):
            gc.ok({"cmd": "set_geo_day", "day": 28, "hour": 0})

        for gc in (js.host, js.client):
            gc.ok({"cmd": "geo_set_speed", "idx": 4})
        deadline = time.time() + 180
        final_mission = None
        while time.time() < deadline:
            state = js.host.ok({"cmd": "separate_faction_mission_state"})
            final_mission = next((mission for mission in state.get("alienMissions", [])
                                  if mission["type"] in
                                  ("STR_FINAL_MISSION_MARINES",
                                   "STR_FINAL_MISSION_ADEPTAS")), None)
            if not final_mission:
                final_mission = next((site for site in state.get("missionSites", [])
                                      if site["type"] in
                                      ("STR_FINAL_MISSION_MARINES",
                                       "STR_FINAL_MISSION_ADEPTAS")), None)
            if not final_mission:
                final_mission = next((base for base in state.get("alienBases", [])
                                      if base["type"] in
                                      ("STR_MARS_CYDONIA_LANDING",
                                       "STR_MARS_CYDONIA_LANDING_ADEPTAS")), None)
            if final_mission:
                break
            states = js.host.ok({"cmd": "get_state"})["states"]
            if any("MonthlyReportState" in state for state in states):
                profile = js.host.ok({"cmd": "separate_profile_state"})
                raise RuntimeError(
                    "monthly scripts ran without a visible faction finale: " +
                    repr({"targets": state, "profile": profile}))
            for gc in (js.host, js.client):
                geo.drain_popups(gc)
                if geo.on_geoscape(gc):
                    gc.ok({"cmd": "geo_set_speed", "idx": 4})
            time.sleep(.25)
        if not final_mission:
            raise RuntimeError("ROSIGMA did not schedule a faction final mission")

        js.host.ok({"cmd": "save_game", "file": SAVE_NAME})
        source = None
        for root, _dirs, files in os.walk(js.host_dir):
            if SAVE_NAME in files:
                source = os.path.join(root, SAVE_NAME)
                break
        if source is None:
            raise RuntimeError(f"save was not written below: {js.host_dir}")
        shutil.copy2(source, OUTPUT)

        # SavedGame::save does not assign a display name when the fixture was
        # created without the save-list UI. Give the generated artifact one.
        with open(OUTPUT, "r", encoding="utf-8") as stream:
            save_text = stream.read()
        first_newline = save_text.find("\n")
        if save_text.startswith("name:") and first_newline >= 0:
            save_text = ("name: ROSIGMA Separate Finale Manual Test\n" +
                         save_text[first_newline + 1:])
        # Alien-base ids are scoped by marker type and therefore are not unique.
        # Reveal the exact generated finale by deployment, never by numeric id.
        lines = save_text.splitlines()
        for index, line in enumerate(lines):
            if line.strip() != "deployment: " + final_mission["type"]:
                continue
            block_start = index
            while block_start > 0 and not lines[block_start].startswith("  - lon:"):
                block_start -= 1
            discovered = next((pos for pos in range(block_start, index)
                               if lines[pos].strip().startswith("discovered:")), None)
            if discovered is None:
                lines.insert(index, "    discovered: true")
            else:
                lines[discovered] = "    discovered: true"
            break
        save_text = "\n".join(lines) + "\n"
        # The fixture creates both initial bases at the same coordinates. Move
        # ClientBase before distributing the manual-test artifact.
        lines = save_text.splitlines()
        for index, line in enumerate(lines):
            if line.strip() != "name: ClientBase":
                continue
            base_start = None
            old_lon = None
            old_lat = None
            for coord in range(index - 1, max(-1, index - 8), -1):
                if lines[coord].startswith("  - lon:"):
                    base_start = coord
                    old_lon = lines[coord].split(":", 1)[1].strip()
                    old_lat = lines[coord + 1].split(":", 1)[1].strip()
                    lines[coord] = "  - lon: 2.0"
                    if coord + 1 < len(lines) and lines[coord + 1].strip().startswith("lat:"):
                        lines[coord + 1] = "    lat: 0.5"
                    break
            if base_start is not None:
                base_end = len(lines)
                for end in range(index + 1, len(lines)):
                    if lines[end] and not lines[end].startswith(" "):
                        base_end = end
                        break
                for nested in range(index + 1, base_end):
                    stripped = lines[nested].strip()
                    indent = lines[nested][:-len(lines[nested].lstrip())]
                    if stripped == "lon: " + old_lon:
                        lines[nested] = indent + "lon: 2.0"
                    elif stripped == "lat: " + old_lat:
                        lines[nested] = indent + "lat: 0.5"
            break
        save_text = "\n".join(lines) + "\n"
        with open(OUTPUT, "w", encoding="utf-8", newline="") as stream:
            stream.write(save_text)

        print(f"Created {OUTPUT}")
        print(f"Scheduled by ROSIGMA: {final_mission['type']}")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
