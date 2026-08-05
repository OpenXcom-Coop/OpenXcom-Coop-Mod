"""Empirically prove the alien unit count bug in PvP skirmish."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "coop_test"))
from harness import GameClient, make_user_dir
import pvp_fixture as PVP

PORT = "47991"
host = GameClient("host", 48998, make_user_dir("bug_alien_host"))
client = GameClient("client", 48999, make_user_dir("bug_alien_client"))
try:
    host.spawn()
    host.connect()
    client.spawn()
    client.connect()
    gm = PVP.start_pvp_skirmish_battle(host, client, PORT, alien_player="client")

    hb = host.cmd({"cmd": "battle_state"})
    cb = client.cmd({"cmd": "battle_state"})

    print("gm=%d" % gm)
    print("\n=== ALL UNITS ON HOST ===")
    print("%7s %7s %4s %4s %5s %s" % ("id", "faction", "coop", "sel", "isOut", "name"))
    for u in hb["units"]:
        print("%7s %7s %4s %4s %5s %s" % (
            u["id"], u["faction"], u.get("coop", "?"),
            u.get("selectable"), u.get("isOut"),
            u.get("name", "?")[:30]))

    print("\n=== ALL UNITS ON CLIENT ===")
    print("%7s %7s %4s %4s %5s %s" % ("id", "faction", "coop", "sel", "isOut", "name"))
    for u in cb["units"]:
        print("%7s %7s %4s %4s %5s %s" % (
            u["id"], u["faction"], u.get("coop", "?"),
            u.get("selectable"), u.get("isOut"),
            u.get("name", "?")[:30]))

    # Count: which faction/coop combos are selectable?
    for tag, b in (("host", hb), ("client", cb)):
        xcom_sel = [u for u in b["units"] if u["faction"] == 0 and u.get("selectable")]
        alien_sel = [u for u in b["units"] if u["faction"] == 1 and u.get("selectable")]
        xcom_total = [u for u in b["units"] if u["faction"] == 0 and not u.get("isOut")]
        alien_total = [u for u in b["units"] if u["faction"] == 1 and not u.get("isOut")]
        print(f"\n{tag}: {len(xcom_sel)}/{len(xcom_total)} XCOM selectable, "
              f"{len(alien_sel)}/{len(alien_total)} alien selectable")

        if alien_total:
            for u in alien_total:
                print(f"  alien {u['id']}: coop={u.get('coop')} sel={u.get('selectable')} "
                      f"tu={u.get('tu')} name={u.get('name', '?')[:30]}")

    # After end turn, what happens to alien units?
    print("\n--- after end turn ---")
    host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    time.sleep(3)

    cb2 = client.cmd({"cmd": "battle_state"})
    alien_sel2 = [u for u in cb2["units"] if u["faction"] == 1 and u.get("selectable")]
    alien_total2 = [u for u in cb2["units"] if u["faction"] == 1 and not u.get("isOut")]
    print(f"client after end turn: {len(alien_sel2)}/{len(alien_total2)} alien selectable")
    for u in alien_total2:
        print(f"  alien {u['id']}: coop={u.get('coop')} sel={u.get('selectable')} "
              f"tu={u.get('tu')} name={u.get('name', '?')[:30]}")

finally:
    host.shutdown()
    client.shutdown()
