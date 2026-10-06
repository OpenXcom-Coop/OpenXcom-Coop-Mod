"""ROSIGMA: an initial pilot can leave and re-enter a one-seat craft."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
from test_separate_campaign_three_month_factions import MOD_40K, MOD_ROSIGMA


def soldiers(gc, base_name):
    bases = gc.ok({"cmd": "get_soldiers"})["bases"]
    return next(base["soldiers"] for base in bases if base["name"] == base_name)


def craft_screen(gc, base, craft_id):
    gc.ok({"cmd": "open_screen", "screen": "craft_soldiers",
           "base": base, "craft_id": craft_id})
    result = gc.ok({"cmd": "screen_state"})
    gc.ok({"cmd": "pop_state"})
    return result


def main():
    js = shared_fixture.bring_up(
        "sep_rosigma_single_seat_craft", (49050, 49051, 48350),
        mods=(MOD_40K, MOD_ROSIGMA), campaign_mode="coop",
        # Experienced is ROSIGMA's Chamber/Inquisition faction. Its starting
        # base contains the one-seat STR_XIPHON_GK and compatible pilots.
        host_difficulty=1, client_difficulty=1, transport="tcp")
    host, client = js.host, js.client
    try:
        host_base = next(b for b in host.ok({"cmd": "geo_state"})["bases"]
                         if b["name"] == "HostBase")
        craft_id = None
        for craft in host_base["crafts"]:
            state = craft_screen(host, "HostBase", craft["id"])
            if state["maxUnits"] == 1:
                craft_id = craft["id"]
                break
        assert craft_id is not None, {
            "error": "ROSIGMA host faction has no one-seat craft",
            "crafts": host_base["crafts"],
        }

        roster = soldiers(host, "HostBase")
        pilot = next((s for s in roster
                      if s["owner"] == 0 and s["craftId"] == craft_id), None)
        if pilot is None:
            # Campaign initialization does not always pre-seat the pilot. Try the
            # owner's free roster through the real validator and retain the first
            # soldier whose ROSIGMA group/armor is legal for this craft.
            for candidate in roster:
                if candidate["owner"] != 0 or candidate["craftId"] >= 0:
                    continue
                host.ok({"cmd": "craft_assign", "base": "HostBase",
                         "craft_id": craft_id, "soldier_id": candidate["id"], "on": True})
                deadline = time.time() + 4
                while time.time() < deadline:
                    current = next(s for s in soldiers(host, "HostBase")
                                   if s["id"] == candidate["id"])
                    if current["craftId"] == craft_id:
                        pilot = current
                        break
                    time.sleep(0.2)
                if pilot is not None:
                    client.wait_for(
                        "initial one-seat pilot assignment replicated",
                        lambda: (next(s for s in soldiers(client, "HostBase")
                                      if s["id"] == pilot["id"])["craftId"] == craft_id) or None,
                        timeout=30, interval=0.5)
                    break
                # A rejected group/armor assignment may leave an error popup.
                host.cmd({"cmd": "dismiss_popup"})
        assert pilot is not None, {
            "error": "no host soldier is legal crew for the ROSIGMA one-seat craft",
            "craftId": craft_id, "roster": roster,
        }

        occupied_initial = craft_screen(host, "HostBase", craft_id)
        assert occupied_initial["usedNum"] == 1
        assert occupied_initial["availableNum"] == 0, occupied_initial

        host.ok({"cmd": "craft_assign", "base": "HostBase",
                 "craft_id": craft_id, "soldier_id": pilot["id"], "on": False})
        for gc in (host, client):
            gc.wait_for(
                "pilot removed from one-seat craft",
                lambda gc=gc: (next(s for s in soldiers(gc, "HostBase")
                                     if s["id"] == pilot["id"])["craftId"] < 0) or None,
                timeout=30, interval=0.5)

        empty = craft_screen(host, "HostBase", craft_id)
        assert empty["maxUnits"] == 1, empty
        assert empty["usedNum"] == 0 and empty["availableNum"] == 1, empty

        host.ok({"cmd": "craft_assign", "base": "HostBase",
                 "craft_id": craft_id, "soldier_id": pilot["id"], "on": True})
        for gc in (host, client):
            gc.wait_for(
                "pilot reassigned to one-seat craft",
                lambda gc=gc: (next(s for s in soldiers(gc, "HostBase")
                                     if s["id"] == pilot["id"])["craftId"] == craft_id) or None,
                timeout=30, interval=0.5)

        occupied = craft_screen(host, "HostBase", craft_id)
        assert occupied["usedNum"] == 1 and occupied["availableNum"] == 0, occupied
        print("PASS ROSIGMA one-seat craft pilot can be removed and reassigned")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
