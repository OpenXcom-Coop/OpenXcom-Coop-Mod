"""R5-P1 (rewrite spike, SPIKE-RUNBOOK.md RB-D23): assignSeatsAndFactions()
canonical-faction/seat probe.

Two scenarios, each a real 2-player skirmish co-op battle start through the
harness lobby flow (host: NEW BATTLE > COOP > Host > START HOST -> lobby ->
[gm2 only: lobby_set_team ClientPlayer -> Alien] -> BATTLE SETTINGS -> OK ->
tactical map) - the SAME UI path test_rw_handshake.py (R4-P1) already proved
out, extended with the PvP team-select step `pvp_fixture.py` uses for its own
gm2/gm3 lobby drive (read as a reference, not imported - test_skirmish_flow.py,
which pvp_fixture.py itself imports, still carries its own pre-existing
SKIP-PENDING(R4-P1) guard that exits at import time; test_rw_handshake.py hit
the same thing and inlined skirmish_host()/skirmish_client_at_browser() rather
than touch that guard - this test follows the same precedent).

  (a) test_classic(): default lobby (no team changes -> gamemode 1, "PVE",
      grouped with gamemode 0 under RB-D23's "classic/SHARED" umbrella).
      Every real soldier unit (`isPlayerSoldier`) must be FACTION_PLAYER on
      BOTH machines; since nothing in this flow ever calls Soldier::setCoop()
      (NewBattleState.cpp has no such call), every soldier's ownership stamp
      sits at its Soldier ctor default (_coop == 0) - so every soldier unit's
      seat tag must be COOP_SEAT_0 on both machines, and every non-soldier
      unit (HWPs/civilians/real mission aliens) must be COOP_SEAT_NONE (-1).

  (b) test_pvp_gm2(): ClientPlayer set to the Alien team pre-battle
      (lobby_set_team -> gamemode 2, "PVP" - pvp_fixture.py's own
      "host=XCOM, client=Alien" contract). assignSeatsAndFactions() must seat
      the vanilla-generated FACTION_PLAYER group at seat 0 and the
      vanilla-generated FACTION_HOSTILE group (the mission's real aliens) at
      seat 1 - checked the other direction from (a): every coop==0 unit is
      FACTION_PLAYER, every coop==1 unit is FACTION_HOSTILE, on BOTH machines,
      and the split is non-vacuous (both groups actually populated).

Both scenarios additionally assert per-unit id-for-id equality between the
host's and the client's own `battle_state` unit dump - the client never
regenerates or recomputes factions/seats (assignSeatsAndFactions() is
HOST-ONLY, called once inside offerBattle() before the battle blob is
snapshotted), so an equal dump on both machines is direct evidence that the
host's canonical assignment actually made it into the streamed blob, not just
into the host's own live SavedBattleGame.

The two `hash_now {full:true}` all-buckets-equal-at-ready clauses (REVIEW4
IR-11) run at the G4 joint check (needs R2-P9->P11's introspection from the
parallel branch, already landed, but the JOINT verification itself is a
separate cross-packet gate) - this test does not attempt them; it reuses the
EXISTING R2-P9 saveBlob-EQUAL hard gate (already wired into onReady()
unconditionally, proven by test_rw_handshake.py) purely as a "did the
handshake actually complete" sanity check alongside the faction/seat asserts.

Run:  python tools/coop_test/test_rw_faction_setup.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session

FACTION_PLAYER = 0
FACTION_HOSTILE = 1
COOP_SEAT_NONE = -1
COOP_SEAT_0 = 0
COOP_SEAT_1 = 1


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def row_for(gc, name_substring):
    """pvp_fixture.py's row_for(): the _connectedPlayers index of the player
    whose name contains `name_substring` - the roster is sorted, so this finds
    the right row regardless of sort order."""
    names = lobby(gc).get("players", [])
    for i, n in enumerate(names):
        if name_substring in n:
            return i
    raise AssertionError(f"could not find {name_substring!r} in roster: {names}")


def skirmish_host(host, port, player="HostPlayer"):
    host.ok({"cmd": "open_new_battle"})
    host.wait_for("host new battle", lambda: session.has_state(host, "NewBattleState"))
    host.ok({"cmd": "newbattle_coop"})
    host.wait_for("host browser", lambda: session.has_state(host, "ServerList"))
    host.ok({"cmd": "server_list_host"})
    host.wait_for("host window", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv",
             "port": port, "player": player})
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"))


def skirmish_client_at_browser(client):
    client.ok({"cmd": "open_new_battle"})
    client.wait_for("client new battle", lambda: session.has_state(client, "NewBattleState"))
    client.ok({"cmd": "newbattle_coop"})
    client.wait_for("client browser", lambda: session.has_state(client, "ServerList"))


def log_lines(user_dir):
    log = os.path.join(user_dir, "openxcom.log")
    if not os.path.exists(log):
        return []
    with open(log, encoding="utf-8", errors="replace") as f:
        return f.readlines()


def grep_lines(lines, needle):
    return [l.rstrip("\n") for l in lines if needle in l]


def units_by_id(battle_state_resp):
    return {u["id"]: u for u in battle_state_resp.get("units", [])}


def bring_up_lobby(host, client, host_dir, client_dir, port):
    """Steps 1-4 of the skirmish lobby flow, common to both scenarios."""
    host.spawn(); host.connect()
    client.spawn(); client.connect()

    skirmish_host(host, port)
    skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer"})

    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: lobby(host).get("buttonVisible") or None)


def drive_to_battlescape(host, client, host_dir, client_dir):
    """Steps 5-7: BATTLE SETTINGS -> OK -> both machines in BattlescapeState.
    Same sequence test_rw_handshake.py (R4-P1) already proved for the classic
    path; R5-P1 only adds the PvP team-select step BEFORE this is called."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={states(host)}"

    host.ok({"cmd": "newbattle_ok"})

    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=30)

    # WV-D56 (FX-1): the coop blob snapshot/battle_offer now move to AFTER the
    # host's own startFirstTurn() - i.e. to THIS click, not to newbattle_ok.
    # None of the log lines below exist until it runs.
    host.ok({"cmd": "click_widget", "match": "ok"})
    host.wait_for("host battlescape",
                  lambda: session.has_state(host, "BattlescapeState"), timeout=30)
    assert session.has_state(host, "BattlescapeState"), \
        f"host should reach BattlescapeState after OK, stack={states(host)}"

    client.wait_for("client battlescape",
                    lambda: session.has_state(client, "BattlescapeState"), timeout=60)

    # settle so both logs have flushed the handshake lines before reading them
    time.sleep(3)

    host_log = log_lines(host_dir)
    client_log = log_lines(client_dir)

    offer_lines = grep_lines(host_log, "[coop-handshake] battle_offer sent")
    accept_lines = grep_lines(host_log, "[coop-handshake] battle_accept received")
    client_active_lines = grep_lines(client_log, "[coop-handshake] CLIENT phase Active")
    equal_lines = grep_lines(host_log, "[coop-handshake] battle_ready saveBlob EQUAL")
    mismatch_lines = grep_lines(host_log, "[coop-handshake] battle_ready saveBlob MISMATCH")
    host_active_lines = grep_lines(host_log, "[coop-handshake] HOST phase Active")

    assert offer_lines, "host log missing 'battle_offer sent' line"
    assert accept_lines, "host log missing 'battle_accept received' line"
    assert client_active_lines, "client log missing 'CLIENT phase Active' line"
    assert not mismatch_lines, \
        f"battle_ready saveBlob MISMATCH - assignSeatsAndFactions() perturbed the " \
        f"canonical hash: {mismatch_lines[-1]}"
    assert equal_lines, \
        "battle_ready arrived but 'saveBlob EQUAL' was never logged - onReady() " \
        "did not run to completion"
    assert host_active_lines, "host did not reach phase Active after an EQUAL saveBlob"

    # W1-P3 (SS1 WAVE-1 ADDITIONS trap 2 / WV-D9): the client now enters the
    # battle through a read-only BriefingState pushed OVER its
    # BattlescapeState, so every fixture that DRIVES the client must dismiss
    # it explicitly - injected input would otherwise land on the briefing and
    # screen-projection probes would compute against the GEOSCAPE viewport the
    # briefing holds. No-op on a stack with no BriefingState.
    session.dismiss_client_briefing(client)


def assert_cross_machine_equal(host_units, client_units):
    assert set(host_units.keys()) == set(client_units.keys()), \
        f"host/client unit id sets differ: host={sorted(host_units)} " \
        f"client={sorted(client_units)}"
    for uid, hu in host_units.items():
        cu = client_units[uid]
        assert hu["faction"] == cu["faction"], \
            f"unit {uid} faction differs: host={hu['faction']} client={cu['faction']}"
        assert hu["coop"] == cu["coop"], \
            f"unit {uid} seat differs: host={hu['coop']} client={cu['coop']}"


def test_classic():
    """(a): classic 2-seat skirmish - every soldier FACTION_PLAYER, seat 0."""
    port = "47993"
    host_dir = make_user_dir("rw_faction_classic_host")
    client_dir = make_user_dir("rw_faction_classic_client")
    host = GameClient("host", 48790, host_dir)
    client = GameClient("client", 48791, client_dir)
    try:
        bring_up_lobby(host, client, host_dir, client_dir, port)
        drive_to_battlescape(host, client, host_dir, client_dir)

        host_state = host.cmd({"cmd": "battle_state"})
        client_state = client.cmd({"cmd": "battle_state"})
        assert host_state.get("inBattle"), "host battle_state.inBattle is false"
        assert client_state.get("inBattle"), "client battle_state.inBattle is false"

        host_units = units_by_id(host_state)
        client_units = units_by_id(client_state)
        assert host_units, "host battle_state reported no units"

        soldier_count = 0
        for uid, u in host_units.items():
            if u["isPlayerSoldier"]:
                soldier_count += 1
                assert u["faction"] == FACTION_PLAYER, \
                    f"soldier unit {uid} ({u['name']}) faction={u['faction']}, expected FACTION_PLAYER"
                assert u["coop"] == COOP_SEAT_0, \
                    f"soldier unit {uid} ({u['name']}) coop seat={u['coop']}, " \
                    f"expected COOP_SEAT_0 (Soldier::getCoop() ownership default)"
            else:
                assert u["coop"] == COOP_SEAT_NONE, \
                    f"non-soldier unit {uid} ({u['name']}) coop seat={u['coop']}, " \
                    f"expected COOP_SEAT_NONE (HWP/civilian/alien - nobody commands it)"
        assert soldier_count > 0, "no isPlayerSoldier units in the generated battle - fixture is empty"

        assert_cross_machine_equal(host_units, client_units)

        print(f"PASS test_classic: {soldier_count} soldier unit(s) FACTION_PLAYER/seat0 "
              f"on both machines, non-soldiers COOP_SEAT_NONE, host/client dumps equal")
    finally:
        host.shutdown()
        client.shutdown()


def test_pvp_gm2():
    """(b): PvP skirmish, ClientPlayer on Alien (gamemode 2) - seat0 FACTION_PLAYER,
    seat1 FACTION_HOSTILE, both machines, non-vacuous split."""
    port = "47994"
    host_dir = make_user_dir("rw_faction_pvp_host")
    client_dir = make_user_dir("rw_faction_pvp_client")
    host = GameClient("host", 48792, host_dir)
    client = GameClient("client", 48793, client_dir)
    try:
        bring_up_lobby(host, client, host_dir, client_dir, port)

        row = row_for(host, "ClientPlayer")
        r = host.ok({"cmd": "lobby_set_team", "row": row, "team": "Alien"})
        gamemode = r.get("gamemode")
        assert gamemode == 2, f"expected gamemode 2 (PVP, client=Alien), got {gamemode}"
        time.sleep(1)  # let the change_team broadcast settle on the client (pvp_fixture.py precedent)

        drive_to_battlescape(host, client, host_dir, client_dir)

        host_state = host.cmd({"cmd": "battle_state"})
        client_state = client.cmd({"cmd": "battle_state"})
        assert host_state.get("inBattle"), "host battle_state.inBattle is false"
        assert client_state.get("inBattle"), "client battle_state.inBattle is false"
        assert host_state.get("coopGamemode") == 2, \
            f"host battle_state.coopGamemode={host_state.get('coopGamemode')}, expected 2"
        assert client_state.get("coopGamemode") == 2, \
            f"client battle_state.coopGamemode={client_state.get('coopGamemode')}, expected 2"

        host_units = units_by_id(host_state)
        client_units = units_by_id(client_state)
        assert host_units, "host battle_state reported no units"

        seat0_count = 0
        seat1_count = 0
        for uid, u in host_units.items():
            if u["coop"] == COOP_SEAT_0:
                seat0_count += 1
                assert u["faction"] == FACTION_PLAYER, \
                    f"seat0 unit {uid} ({u['name']}) faction={u['faction']}, expected FACTION_PLAYER"
            elif u["coop"] == COOP_SEAT_1:
                seat1_count += 1
                assert u["faction"] == FACTION_HOSTILE, \
                    f"seat1 unit {uid} ({u['name']}) faction={u['faction']}, expected FACTION_HOSTILE"
            else:
                assert u["coop"] == COOP_SEAT_NONE, \
                    f"unit {uid} ({u['name']}) has an unexpected coop seat={u['coop']}"

        assert seat0_count > 0, "no seat0 (FACTION_PLAYER) units - fixture has no soldiers"
        assert seat1_count > 0, "no seat1 (FACTION_HOSTILE) units - fixture has no real aliens " \
            "to hand to the PvP hostile seat"

        assert_cross_machine_equal(host_units, client_units)

        print(f"PASS test_pvp_gm2: seat0={seat0_count} FACTION_PLAYER, "
              f"seat1={seat1_count} FACTION_HOSTILE on both machines, dumps equal")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    test_classic()
    test_pvp_gm2()
    print("ALL R5-P1 FACTION/SEAT TESTS PASSED")


if __name__ == "__main__":
    main()
