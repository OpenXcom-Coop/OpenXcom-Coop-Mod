"""ROSIGMA regression: the second faction gets a valid Research menu.

Starts a new two-player Separate Campaign with the host on faction/difficulty
zero and the client on faction/difficulty one.  The client then opens the real
NewResearchListState for its own base.  Internal ROSIGMA score and script rules
must never be displayed as research projects.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
from test_separate_campaign_three_month_factions import MOD_40K, MOD_ROSIGMA


INTERNAL_TOPICS = {"STR_GAME_START", "STR_GENERALLOCK"}
INTERNAL_PREFIXES = ("STR_GAIN_", "STR_LOSE_")


def main():
    for path in (MOD_40K, MOD_ROSIGMA):
        if not os.path.isdir(path):
            raise SystemExit(f"required mod directory not found: {path}")

    js = shared_fixture.bring_up(
        "sep_rosigma_client_research_menu",
        (49052, 49053, 48352),
        wait_ready=False,
        mods=(MOD_40K, MOD_ROSIGMA),
        campaign_mode="coop",
        host_difficulty=0,
        client_difficulty=1,
        host_options={"EnableResearchSync": False},
        client_options={"EnableResearchSync": False},
        host_name="Ari",
        client_name="Jer3i",
        transport="tcp",
    )
    try:
        opened = js.client.ok({
            "cmd": "open_screen",
            "screen": "new_research",
            "base": "ClientBase",
        })
        assert opened.get("ok"), opened

        menu = js.client.ok({"cmd": "screen_state"})
        assert menu.get("top") == "new_research", menu
        projects = menu.get("projects", [])
        assert projects, "client faction Research menu is empty"

        leaked = [
            topic for topic in projects
            if topic in INTERNAL_TOPICS or topic.startswith(INTERNAL_PREFIXES)
        ]
        assert not leaked, {
            "reason": "internal ROSIGMA score/script topics are visible in the client Research menu",
            "leaked": leaked,
            "projects": projects,
            "hostProfiles": js.host.ok({"cmd": "separate_profile_state"}),
            "clientProfiles": js.client.ok({"cmd": "separate_profile_state"}),
        }

        print(
            "PASS ROSIGMA Separate Campaign: faction 1 client Research menu "
            "contains no internal score or script topics"
        )
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
