"""Campaign co-op battle entry: SEPARATE guest battle.

A SEPARATE campaign co-op battle flown from the host's Skyranger with a guest
seated by the CLIENT (session.bring_up_separate_guest_battle) must:

  * deploy the host's 3 own soldiers at seat 0 and the client's guest "Guest
    Zzz" at seat 1, on BOTH machines - the guest identified BY NAME, since
    the host mints its battle copy a FRESH soldierId
    (`loadWorld(111)`'s materialisation shape, `setId(lastId + 1)`);
  * let the CLIENT command its own guest through the real intent path
    (admitted), refuse it on a host soldier (not_your_unit), and refuse the
    HOST's click-select on the guest's own tile;
  * leave the battle cleanly via the host-authoritative abort:
    the HOST reaches the geoscape (AbortMissionState -> finishBattle) with NO
    crash and NO desyncSeen on EITHER machine - expect_both=True: the SEPARATE
    second player returns to its OWN geoscape at the end too, so BOTH
    machines reach the geoscape;
  * after the battle (post_battle_roster), list "Guest Zzz" exactly once on
    each machine, at the host's base, still owned by the client (one world:
    the battle used the soldier itself, no copy).

The bring-up itself waits until the guest sits on the host's Skyranger on both
machines before the mission starts.

The guest's post-battle RECORD (stats/rank/wounds/missions/kills/diary/death)
returning to the CLIENT's own world is asserted by test_battle_end_separate.py
(row guest_returns_alive), not here: this test asserts the client's clean
return to its own geoscape after a SEPARATE host abort (expect_both=True) and
the host's post-battle roster (post_battle_roster).

Run:  python tools/coop_test/test_coop_separate_guest_battle.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session

PORT = "48870"


def _guest_rows(gc, name_substr="Guest"):
    """(base, id, owner) of every soldier on @a gc whose name holds @a name_substr."""
    return [(b["name"], s["id"], s["owner"]) for b in gc.ok({"cmd": "get_soldiers"})["bases"]
            for s in b["soldiers"] if name_substr in s["name"]]


def main():
    host_dir = make_user_dir("cgb_host")
    client_dir = make_user_dir("cgb_client")
    host = GameClient("host", 48871, host_dir)
    client = GameClient("client", 48872, client_dir)
    try:
        host.spawn(); client.spawn(); host.connect(); client.connect()

        host_squad, guest_id = session.bring_up_separate_guest_battle(host, client, port=PORT)

        # ---- expected roster: 3 host soldiers (seat 0) + the guest, BY NAME
        # (seat 1), on BOTH machines ------------------------------------------
        guest_battle_id = None
        for gc, tag in ((host, "host"), (client, "client")):
            bs = session.battle_state(gc)
            players = [u for u in bs.get("units", []) if u.get("isPlayerSoldier")]
            guest_units = [u for u in players if "Guest" in (u.get("name") or "")]
            assert len(guest_units) == 1, (
                f"{tag}: expected exactly one player unit named 'Guest*', got "
                f"names={[u.get('name') for u in players]}")
            guest_unit = guest_units[0]
            assert guest_unit["coop"] == 1, (
                f"{tag}: guest unit coop={guest_unit['coop']}, want 1: {guest_unit}")
            if guest_battle_id is None:
                guest_battle_id = guest_unit["soldierId"]
            else:
                assert guest_unit["soldierId"] == guest_battle_id, (
                    f"{tag}: guest battle soldierId {guest_unit['soldierId']} != "
                    f"{guest_battle_id} seen on the other machine")
            host_seat_ids = sorted(u["soldierId"] for u in players
                                   if u["soldierId"] != guest_battle_id)
            assert set(host_seat_ids) == set(host_squad), (
                f"{tag}: seat-0 roster {host_seat_ids} != expected host squad "
                f"{sorted(host_squad)}")
            for u in players:
                if u["soldierId"] == guest_battle_id:
                    continue
                assert u["coop"] == 0, f"{tag}: host soldier {u} not coop==0"
        print(f"PASS roster: 3 host soldiers {sorted(host_squad)} (seat 0) + the "
              f"guest 'Guest Zzz' (soldierId={guest_battle_id}, seat 1, identified "
              f"by name) on both machines")

        expected_seats = {sid: 0 for sid in host_squad}
        expected_seats[guest_battle_id] = 1
        session.assert_control_split(host, client, expected_seats,
                               what="separate guest battle")
        session.assert_seat_commands(host, client, guest_battle_id, host_squad[0],
                             what="separate guest battle")
        session.assert_battle_exit(host, client, what="separate guest battle",
                              expect_both=True)

        # ---- post-battle roster consumers ------------------------------
        want = [("HostBase", guest_id, 1)]
        for gc, tag in ((host, "host"), (client, "client")):
            rows = _guest_rows(gc)
            assert rows == want, (
                f"post_battle_roster: {tag} lists the guest as {rows}, want {want} "
                f"(once, at the host's base, owned by the client)")
        print("PASS post_battle_roster: 'Guest Zzz' is listed once on each machine, at the host's base, "
              "owned by the client")

        session.assert_client_zero_disk(client_dir)
        print("PASS zero-disk: client user dir clean")

        print("ALL SEPARATE GUEST BATTLE TESTS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
