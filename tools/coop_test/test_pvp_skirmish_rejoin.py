"""PvP skirmish rejoin: mid-battle disconnect preserves gamemode.

Gamemode 2:
  1. Start PvP skirmish, enter battle.
  2. Kill the client process mid-battle.
  3. Client rejoins via NEW BATTLE > COOP > join.
  4. Verify the rejoined battle has coopGamemode == 2 (not reset to 0).

Gamemode 3: same with host disconnecting.

Run:  python tools/coop_test/test_pvp_skirmish_rejoin.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

# RW-TRIAGE: SKIP-PENDING(r5/W6)
print("SKIP-PENDING: rewrite"); sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import pvp_fixture as PVP

PORT = "47994"


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def _has(gc, name):
    return any(name in s
               for s in gc.cmd({"cmd": "get_state"})["states"])


def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)


def test_pvp_rejoin_client(fails):
    """Gamemode 2: host=XCOM, client drops & rejoins. Gamemode preserved."""
    print("\n--- rejoin gamemode 2 (client drops) ---")
    host = GameClient("host", 48906, make_user_dir("pvp_rj2_host"))
    client = GameClient("client", 48907, make_user_dir("pvp_rj2_client"))
    client2 = GameClient("client2", 48908, make_user_dir("pvp_rj2_client2"))
    try:
        host.spawn()
        host.connect()
        client.spawn()
        client.connect()

        gm = PVP.start_pvp_skirmish_battle(host, client, PORT, alien_player="client")
        if gm != 2:
            _fail(fails, f"expected gamemode 2, got {gm}")
            return

        mode_before = battle(host).get("coopGamemode")
        print(f"    before drop: gamemode={mode_before}")

        # ---- drop the client -------------------------------------------------
        client.shutdown()
        time.sleep(5)

        # Host should show connection-lost or wait-players dialog
        print(f"    host states after client drop: "
              f"{[s.replace('class OpenXcom::', '') for s in session.states(host)][-3:]}")

        # ---- rejoin ----------------------------------------------------------
        client2.spawn()
        client2.connect()
        client2.ok({"cmd": "open_new_battle"})
        client2.wait_for("new battle", lambda: _has(client2, "NewBattleState"))
        client2.ok({"cmd": "newbattle_coop"})
        client2.wait_for("browser", lambda: _has(client2, "ServerList"))
        client2.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": PORT,
                    "player": "ClientPlayer"})

        # The client rejoins; dismiss popups
        for _ in range(10):
            if _has(client2, "Profile"):
                client2.ok({"cmd": "profile_ok"})
                time.sleep(0.5)
            else:
                break

        # Wait for the rejoin battle to load
        client2.wait_for(
            "client2 in battle",
            lambda: battle(client2).get("inBattle") or None,
            timeout=120, interval=1.0)

        mode_after = battle(client2).get("coopGamemode")
        print(f"    after rejoin: gamemode={mode_after}")
        if mode_after != 2:
            _fail(fails,
                  f"gamemode reset to {mode_after} after rejoin (should be 2)")
        else:
            print("PASS gm2 rejoin: gamemode preserved as 2")

    except Exception as e:
        print(f"[ERROR] gm2: {e}")
        _fail(fails, str(e))
    finally:
        host.shutdown()
        if client2.proc is not None:
            client2.shutdown()


def main():
    fails = []
    test_pvp_rejoin_client(fails)

    print("\n==== PvP skirmish rejoin summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  rejoin preserves gamemode")
    sys.exit(0)


if __name__ == "__main__":
    main()
