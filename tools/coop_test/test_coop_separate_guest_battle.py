"""SPEC 19 (W1-P20) S1 - campaign co-op battle entry: SEPARATE guest battle.

A SEPARATE campaign co-op battle flown from the host's Skyranger with a guest
seated by the CLIENT (session.bring_up_separate_guest_battle - the archived
r1a_v2.bring_up_fixed recipe, R1(b)'s own measured fixture) must, at the tip:

  * deploy the host's 3 own soldiers at seat 0 and the client's guest "Guest
    Zzz" at seat 1, on BOTH machines - the guest identified BY NAME, since
    Branch B mints its battle copy a FRESH soldierId (M2 Branch B:
    `loadWorld(111)`'s materialisation shape, `setId(lastId + 1)`);
  * let the CLIENT command its own guest through the real intent path
    (admitted), refuse it on a host soldier (not_your_unit), and refuse the
    HOST's click-select on the guest's own tile;
  * leave the battle cleanly (abort -> geoscape, no crash, no desyncSeen);
  * satisfy F366's post-battle roster consumers: the host's merged COPY of the
    guest (coopBase == -1) is gone; the client's own durable "Guest Zzz"
    survives.

Vacuity guard (Branch B): BEFORE coop_mission_start is ever pressed, the
client's `event_state.guestContrib.sent` must already be >= 1 and the host's
per-seat stored count for seat 1 must already be >= 1 - proof the
`battle_roster_contrib` census actually reached the host, not just an absence
any unrelated bring-up failure would also produce.

OUT-OF-WAVE (D103): the guest's post-battle state (stats/wounds/death/
promotions) returning to the CLIENT's world is r4 T2 (`debrief_result`) and is
NOT asserted here - only that both machines return to the geoscape cleanly and
the host's roster satisfies F366.

Run:  python tools/coop_test/test_coop_separate_guest_battle.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session

PORT = "48870"


def _vacuity_guard(host, client):
    """Called by bring_up_separate_guest_battle right after the squad is
    assembled (guest seated, client back on the geoscape) and BEFORE
    drain_host_coop_notice/spawn_mission_site/coop_mission_start."""
    es_c = client.cmd({"cmd": "event_state"})
    gcontrib = es_c.get("guestContrib") or {}
    sent = gcontrib.get("sent")
    assert isinstance(sent, int) and sent >= 1, (
        f"VACUITY (Branch B): client event_state.guestContrib.sent={sent!r} "
        f"BEFORE coop_mission_start - the guest roster contribution never "
        f"travelled: {es_c}")

    es_h = host.cmd({"cmd": "event_state"})
    hcontrib = es_h.get("guestContrib") or {}
    soldiers = hcontrib.get("soldiers") or []
    seat1_stored = soldiers[1] if len(soldiers) > 1 else 0
    assert seat1_stored >= 1, (
        f"VACUITY (Branch B): host's stored guestContrib count for seat 1 = "
        f"{seat1_stored} BEFORE coop_mission_start - full guestContrib: {hcontrib}")
    print(f"PASS vacuity guard (before coop_mission_start): client "
          f"guestContrib.sent={sent}, host seat-1 stored={seat1_stored}")


def _guest_present(gc, name_substr="Guest"):
    for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
        for s in b["soldiers"]:
            if name_substr in s["name"]:
                return True
    return False


def main():
    host_dir = make_user_dir("cgb_host")
    client_dir = make_user_dir("cgb_client")
    host = GameClient("host", 48871, host_dir)
    client = GameClient("client", 48872, client_dir)
    try:
        host.spawn(); client.spawn(); host.connect(); client.connect()

        host_squad, _guest_local_id = session.bring_up_separate_guest_battle(
            host, client, port=PORT, pre_mission_start=_vacuity_guard)

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
        session.assert_t_split(host, client, expected_seats,
                               what="S1 separate guest battle")
        session.assert_t_cmd(host, client, guest_battle_id, host_squad[0],
                             what="S1 separate guest battle")
        session.assert_t_exit(host, client, what="S1 separate guest battle")

        # ---- F366: post-battle roster consumers ------------------------------
        assert not _guest_present(host), (
            "F366: the host's get_soldiers STILL lists a 'Guest' soldier after "
            "the battle - the merged copy (Branch B, coopBase==-1) was not "
            "deleted post-battle")
        assert _guest_present(client), (
            "F366: the client's own base no longer lists 'Guest Zzz' - the "
            "client's durable guest soldier was lost")
        print("PASS F366: the host's merged guest copy is gone; the client's own "
              "durable guest 'Guest Zzz' survives")

        session.assert_client_zero_disk(client_dir)
        print("PASS zero-disk: client user dir clean")

        print("ALL SPEC 19 (W1-P20) S1 SEPARATE GUEST BATTLE TESTS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
