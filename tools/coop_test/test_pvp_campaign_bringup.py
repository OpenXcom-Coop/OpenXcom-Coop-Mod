"""PvP campaign bringup: validates the no_bases fix.

Gamemode 2 (client plays aliens):
  1. Host starts campaign, places base.
  2. Client (alien player) skips base placement — no BuildNewBaseState.
  3. Both machines reach the geoscape.

Gamemode 3 (host plays aliens):
  4. Client (XCOM) places base.
  5. Host (alien player) skips base placement — no BuildNewBaseState.
  6. Both machines reach the geoscape.

After bringup, the test aborts cleanly (the campaign world is not needed).

Run:  python tools/coop_test/test_pvp_campaign_bringup.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import pvp_fixture as PVP


def _states(gc):
    return [s.replace("class OpenXcom::", "")
            for s in session.states(gc)]


def _has(gc, name):
    return any(name in s for s in _states(gc))


PORT = "47995"


def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)


def test_campaign_bringup(fails, alien_player, expect_mode):
    tag = "gm" + str(expect_mode) + "_" + alien_player
    print(f"\n--- campaign gamemode {expect_mode} ({alien_player} plays aliens) ---")

    host = GameClient("host", 48900, make_user_dir(f"pvp_camp_{tag}_host"))
    client = GameClient("client", 48901, make_user_dir(f"pvp_camp_{tag}_client"))
    try:
        host.spawn()
        host.connect()
        client.spawn()
        client.connect()

        alien_gc = client if alien_player == "client" else host
        xcom_gc = host if alien_player == "client" else client

        # Our fixture handles the full flow: lobby -> start campaign -> bases -> geoscape
        gm = PVP.start_pvp_campaign(host, client, PORT, alien_player=alien_player)
        if gm != expect_mode:
            _fail(fails, f"{tag}: expected gamemode {expect_mode}, got {gm}")
        else:
            print(f"PASS {tag}: gamemode {expect_mode}")

        # ---- alien player must NOT get base placement ----------------------
        time.sleep(2)
        if _has(alien_gc, "BuildNewBaseState"):
            _fail(fails,
                  f"{tag}: {alien_player} (alien side) was prompted to place a base "
                  f"(no_bases not set)")
        else:
            print(f"PASS {tag}: {alien_player} (alien side) skipped base placement")

        # ---- XCOM player must place a base --------------------------------
        if _has(xcom_gc, "BuildNewBaseState"):
            _fail(fails,
                  f"{tag}: XCOM player still on BuildNewBaseState "
                  f"(base placement not completed)")
        else:
            has_geo = _has(xcom_gc, "GeoscapeState")
            if has_geo:
                print(f"PASS {tag}: XCOM player reached geoscape")
            else:
                _fail(fails,
                      f"{tag}: XCOM player not on geoscape: {_states(xcom_gc)[-3:]}")

        # ---- both machines must reach the geoscape -------------------------
        for gc, label in ((host, "host"), (client, "client")):
            if _has(gc, "GeoscapeState"):
                print(f"PASS {tag}: {label} on geoscape")
            else:
                _fail(fails,
                      f"{tag}: {label} not on geoscape: {_states(gc)[-3:]}")

    except Exception as e:
        print(f"[ERROR] {tag}: {e}")
        _fail(fails, str(e))
    finally:
        host.shutdown()
        client.shutdown()


def main():
    fails = []

    test_campaign_bringup(fails, alien_player="client", expect_mode=2)
    test_campaign_bringup(fails, alien_player="host", expect_mode=3)

    print("\n==== PvP campaign bringup summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  both gamemodes: alien player skips base, both reach geoscape")
    sys.exit(0)


if __name__ == "__main__":
    main()
