"""PvP campaign geoscape: validates no_bases effects on the strategic layer.

After campaign bringup:
  - Alien player's funds are stub (1000, from SavedGame::getFunds no_bases gate).
  - XCOM player's funds are normal starting funds (>1000).
  - Both machines can push the basescape screen.

Run:  python tools/coop_test/test_pvp_campaign_geoscape.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import pvp_fixture as PVP

PORT = "47996"


def _states(gc):
    return [s.replace("class OpenXcom::", "")
            for s in gc.cmd({"cmd": "get_state"})["states"]]


def _has(gc, name):
    return any(name in s for s in _states(gc))


def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)


def test_geoscape_gm2(fails):
    """Gamemode 2: host=XCOM, client=alien."""
    print("\n--- geoscape gamemode 2 (host=XCOM, client=Alien) ---")
    host = GameClient("host", 48910, make_user_dir("pvp_geo2_host"))
    client = GameClient("client", 48911, make_user_dir("pvp_geo2_client"))
    try:
        host.spawn()
        host.connect()
        client.spawn()
        client.connect()

        gm = PVP.start_pvp_campaign(host, client, PORT, alien_player="client")
        if gm != 2:
            _fail(fails, f"expected gamemode 2, got {gm}")
            return

        # ---- funds: alien has stub, XCOM has real ------------------------
        hf = host.ok({"cmd": "geo_state"}).get("funds", 0)
        cf = client.ok({"cmd": "geo_state"}).get("funds", 0)
        print(f"    host (XCOM)   funds: {hf}")
        print(f"    client (Alien) funds: {cf}")

        if hf < 1000000:
            _fail(fails, f"host (XCOM) funds too low: {hf} (expected >1M)")
        else:
            print("PASS gm2 funds: host (XCOM) has normal starting funds")
        if cf < 500 or cf > 2000:
            _fail(fails, f"client (Alien) funds {cf}, expected stub ~1000")
        else:
            print("PASS gm2 funds: client (Alien) has stub funds (no_bases)")

        # ---- both can push basescape -------------------------------------
        for gc, label in ((host, "host"), (client, "client")):
            r = gc.ok({"cmd": "open_screen", "screen": "basescape"})
            if r.get("ok"):
                if _has(gc, "BasescapeState"):
                    print(f"PASS gm2 basescape: {label} pushed BasescapeState")
                    gc.ok({"cmd": "dismiss_popup"})
                else:
                    _fail(fails, f"gm2: {label} basescape not on stack")
            else:
                _fail(fails, f"gm2: {label} basescape open_screen failed: {r}")
            time.sleep(0.5)

    except Exception as e:
        print(f"[ERROR] gm2: {e}")
        _fail(fails, str(e))
    finally:
        host.shutdown()
        client.shutdown()


def test_geoscape_gm3(fails):
    """Gamemode 3: host=Aliens, client=XCOM."""
    print("\n--- geoscape gamemode 3 (host=Alien, client=XCOM) ---")
    host = GameClient("host", 48912, make_user_dir("pvp_geo3_host"))
    client = GameClient("client", 48913, make_user_dir("pvp_geo3_client"))
    try:
        host.spawn()
        host.connect()
        client.spawn()
        client.connect()

        gm = PVP.start_pvp_campaign(host, client, PORT, alien_player="host")
        if gm != 3:
            _fail(fails, f"expected gamemode 3, got {gm}")
            return

        hf = host.ok({"cmd": "geo_state"}).get("funds", 0)
        cf = client.ok({"cmd": "geo_state"}).get("funds", 0)
        print(f"    host (Alien)  funds: {hf}")
        print(f"    client (XCOM)  funds: {cf}")

        if hf < 500 or hf > 2000:
            _fail(fails, f"host (Alien) funds {hf}, expected stub ~1000")
        else:
            print("PASS gm3 funds: host (Alien) has stub funds (no_bases)")
        if cf < 1000000:
            _fail(fails, f"client (XCOM) funds too low: {cf} (expected >2M)")
        else:
            print("PASS gm3 funds: client (XCOM) has normal starting funds")

        for gc, label in ((host, "host"), (client, "client")):
            r = gc.ok({"cmd": "open_screen", "screen": "basescape"})
            if r.get("ok"):
                if _has(gc, "BasescapeState"):
                    print(f"PASS gm3 basescape: {label} pushed BasescapeState")
                    gc.ok({"cmd": "dismiss_popup"})
                else:
                    _fail(fails, f"gm3: {label} basescape not on stack")
            else:
                _fail(fails, f"gm3: {label} basescape open_screen failed: {r}")
            time.sleep(0.5)

    except Exception as e:
        print(f"[ERROR] gm3: {e}")
        _fail(fails, str(e))
    finally:
        host.shutdown()
        client.shutdown()


def main():
    fails = []
    test_geoscape_gm2(fails)
    test_geoscape_gm3(fails)

    print("\n==== PvP campaign geoscape summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  both gamemodes: alien stub funds, XCOM normal funds, "
          "basescape loads")
    sys.exit(0)


if __name__ == "__main__":
    main()
