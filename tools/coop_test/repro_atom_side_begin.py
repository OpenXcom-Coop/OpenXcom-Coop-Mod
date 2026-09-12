"""W1-P13a SPEC 9 (REV E.48 SS.B.4) - repro_atom_side_begin.py: two-seat
`activeSeats` correctness in CLASSIC (both seats, player side) vs gm2 (one
seat per side); each machine re-selects one of its OWN units at side begin,
never a peer's; the endTurn `_lastSelectedUnit` restore never lands on a
non-owned unit (WR-18 - the criterion that could not be proven at G1).

AI-NEUTRAL PINNING (WV-D45/IR2-9, REV E.48 SS.B.2) - see
repro_atom_side_transition.py's module docstring for the full rationale;
this file imports the SAME session.pin_ai_neutral() helper (SS.A.7) rather
than re-implementing it. STR_SMALL_SCOUT is the pinned mission in BOTH
scenarios below (no civilians, no terror units).

REV E.48 SS.B.4, verbatim: "Test 2 (repro_atom_side_begin.py) carries B.2;
its gm2 hostile phase is advanced by the host `battle_action end_turn`
lever (the button is dead off-side by vanilla design - `allowButtons()`
requires `_save->getSide() == FACTION_PLAYER`, BattlescapeState.cpp), and
the assertion 'each machine re-selects one of its OWN units' is checked on
the client during the hostile phase in gm2 and on both machines during the
player phase in classic."

READ-BACK LIMITATION (disclosed, not silent - same one
repro_atom_side_transition.py's L2/L3 document): `CoopEventLog::Entry`
(BattlePump.h) is a fixed POD ring slot carrying ONLY
{seq, actionId, kind, hasHash} - no payload field exists for `activeSeats`,
so this file cannot read that array back from the wire directly. Instead it
proves the FUNCTIONAL claim `activeSeats` exists to guarantee - which
machine can actually SELECT/COMMAND a live unit of its own seat while that
seat's side is active - via `battle_state.selectedId` plus each unit's
`coop` field, and separately proves the ENVELOPE COUNT (3 side_begin per
full cycle, M9a-4) via event_log.

Cites WV-D45, WV-D51, WR-18, D48, D49, D58.

Run:  python tools/coop_test/repro_atom_side_begin.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import (battle_state, event_log, pin_ai_neutral, assert_hash_clean,
                      FACTION_PLAYER, FACTION_HOSTILE)

MISSION = "STR_SMALL_SCOUT"


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def row_for(gc, name_substring):
    """test_rw_faction_setup.py's row_for(): the _connectedPlayers index of
    the player whose name contains `name_substring`."""
    names = lobby(gc).get("players", [])
    for i, n in enumerate(names):
        if name_substring in n:
            return i
    raise AssertionError(f"could not find {name_substring!r} in roster: {names}")


# ----- fixture bring-up (inline copy, test_rw_faction_setup.py / repro_atom_walk.py
# precedent) -----

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


def bring_up_lobby(host, client, port):
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


def drive_side_change(host, client, want_side, want_turn_min=None, timeout=60):
    """Advance until BOTH machines report side==want_side (and, when
    `want_turn_min` is given, turn>=want_turn_min), tolerating and
    dismissing any NextTurnState pushed on EITHER machine along the way
    (M9a-5 / REV E.1 S-3 - see repro_atom_side_transition.py's own driver
    for the full rationale). Simpler than that file's driver: this file's
    assertions do not need the L10 dismiss-is-hash-neutral proof, only to
    not stall on an un-dismissed banner."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for gc in (host, client):
            lw = gc.cmd({"cmd": "list_widgets"})
            if "NextTurnState" in lw.get("state", ""):
                gc.cmd({"cmd": "close_nextturn"})
        hs = battle_state(host)
        cs = battle_state(client)
        host_ok = hs.get("side") == want_side and (
            want_turn_min is None or hs.get("turn", -1) >= want_turn_min)
        client_ok = cs.get("side") == want_side and (
            want_turn_min is None or cs.get("turn", -1) >= want_turn_min)
        if host_ok and client_ok:
            return hs, cs
        time.sleep(0.05)
    raise TimeoutError(
        f"repro_atom_side_begin: did not reach side={want_side} "
        f"(turn_min={want_turn_min}) within {timeout}s - "
        f"host={battle_state(host)} client={battle_state(client)}")


def run_classic():
    """CLASSIC: both seats are FACTION_PLAYER. activeSeats == [0, 1] on the
    (only) side that is ever active; WR-18 checked on BOTH machines during
    the player phase, per SS.B.4."""
    port = "48130"
    host_dir = make_user_dir("repro_atom_side_begin_classic_host")
    client_dir = make_user_dir("repro_atom_side_begin_classic_client")
    host = GameClient("host", 49520, host_dir)
    client = GameClient("client", 49521, client_dir)
    seated = {}
    try:
        bring_up_lobby(host, client, port)
        session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2)

        pinned = pin_ai_neutral(host, client, tag="side_begin-classic")
        assert len(pinned) > 0, (
            f"pin_ai_neutral pinned ZERO NONE-seat non-player units on a "
            f"CLASSIC {MISSION} boot - the premise is unexercised (M9a-3)")

        hs0 = battle_state(host)
        cs0 = battle_state(client)
        turn0 = hs0["turn"]
        assert hs0["side"] == FACTION_PLAYER and cs0["side"] == FACTION_PLAYER, (
            f"fixture premise broke: host side={hs0['side']} client side={cs0['side']}")

        # activeSeats == [0, 1] functional proxy (see module docstring): both
        # seats must have a live player-side unit of their own to select
        # while the player side is active.
        host_units = [u for u in hs0["units"]
                      if u.get("coop") == 0 and u.get("faction") == FACTION_PLAYER
                      and not u.get("isOut")]
        client_units = [u for u in hs0["units"]
                         if u.get("coop") == 1 and u.get("faction") == FACTION_PLAYER
                         and not u.get("isOut")]
        assert host_units, "classic boot: seat 0 (host) has no live player unit"
        assert client_units, "classic boot: seat 1 (client) has no live player unit"

        # WR-18 setup: deliberately select an OWN unit on EACH machine before
        # the cycle, so the endTurn _lastSelectedUnit restore has something
        # concrete to restore (rather than restoring an already-null
        # selection, which would pass vacuously).
        host_pre = host_units[0]["id"]
        client_pre = client_units[0]["id"]
        r = host.cmd({"cmd": "battle_action", "action": "select", "unit": host_pre})
        assert r.get("ok"), f"pre-cycle select failed on host: {r}"
        r = client.cmd({"cmd": "battle_action", "action": "select", "unit": client_pre})
        assert r.get("ok"), f"pre-cycle select failed on client: {r}"
        assert battle_state(host)["selectedId"] == host_pre
        assert battle_state(client)["selectedId"] == client_pre
        print(f"[classic] pre-cycle selection armed: host unit {host_pre}, "
              f"client unit {client_pre}")

        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        hs1, cs1 = drive_side_change(host, client, FACTION_PLAYER, turn0 + 1, timeout=60)

        session.wait_host_idle(host, client, timeout=30)

        # Envelope-count sanity: 3 side_begin per full cycle, same invariant
        # as side_transition's L2 (M9a-4 - HOSTILE->NEUTRAL is unconditional,
        # so a full cycle is always three transitions regardless of
        # civilians).
        cevs = event_log(client, tail=256)
        begins = [e for e in cevs if e.get("actionId") == 0 and e.get("kind") == "side_begin"]
        assert len(begins) == 3, (
            f"expected 3 side_begin envelopes for one full classic cycle "
            f"(M9a-4), got {len(begins)}: {begins}")

        # WR-18: the restored selection is an OWN unit on BOTH machines -
        # never a peer's. Checked on BOTH machines during the player phase
        # (SS.B.4's classic clause).
        hu = {u["id"]: u for u in hs1["units"]}
        cu = {u["id"]: u for u in cs1["units"]}
        host_sel = hs1.get("selectedId", -1)
        client_sel = cs1.get("selectedId", -1)
        assert host_sel in hu and hu[host_sel]["coop"] == 0, (
            f"WR-18: host's restored selection {host_sel} does not resolve "
            f"to an OWN (seat 0) unit: {hu.get(host_sel)}")
        assert client_sel in cu and cu[client_sel]["coop"] == 1, (
            f"WR-18: client's restored selection {client_sel} does not "
            f"resolve to an OWN (seat 1) unit: {cu.get(client_sel)}")
        print(f"[classic] activeSeats==[0,1] functional proxy + WR-18 OK: "
              f"host selected {host_sel} (coop=0), client selected "
              f"{client_sel} (coop=1)")
        print("PASS: repro_atom_side_begin classic scenario")
    finally:
        host.shutdown()
        client.shutdown()


def run_gm2():
    """gm2 (PvP, ClientPlayer on Alien): seat 0 is FACTION_PLAYER, seat 1 is
    FACTION_HOSTILE. activeSeats == [0] on the player side, [1] on the
    hostile side (functional proxy - see module docstring); WR-18 checked
    on the CLIENT during the hostile phase, per SS.B.4."""
    port = "48131"
    host_dir = make_user_dir("repro_atom_side_begin_gm2_host")
    client_dir = make_user_dir("repro_atom_side_begin_gm2_client")
    host = GameClient("host", 49522, host_dir)
    client = GameClient("client", 49523, client_dir)
    try:
        bring_up_lobby(host, client, port)

        row = row_for(host, "ClientPlayer")
        r = host.ok({"cmd": "lobby_set_team", "row": row, "team": "Alien"})
        assert r.get("gamemode") == 2, f"expected gamemode 2 (PVP, client=Alien), got {r.get('gamemode')}"
        time.sleep(1)  # let the change_team broadcast settle on the client (pvp_fixture.py precedent)

        # gm2 assigns seat0/seat1 via assignSeatsAndFactions() automatically
        # (test_rw_faction_setup.test_pvp_gm2's own precedent: no
        # newbattle_seat_soldier call at all) - session.drive_to_battlescape's
        # seat_count loop is a CLASSIC-only mechanism (it asserts >= 2
        # stamped soldiers), so this scenario drives NewBattleState inline
        # instead, adding only the STR_SMALL_SCOUT mission pin on top of
        # test_pvp_gm2's own steps.
        host.ok({"cmd": "lobby_action"})
        host.wait_for("host at battle settings",
                      lambda: (not session.has_state(host, "LobbyMenu")) or None)
        assert top_state(host) == "NewBattleState", \
            f"host should land on the NEW BATTLE setup screen, stack={states(host)}"
        r = host.cmd({"cmd": "newbattle_mission", "type": MISSION})
        assert r.get("ok"), (
            f"this build's NEW BATTLE screen does not offer {MISSION!r} "
            f"in gm2 - offered: {r.get('missionTypes')}")

        host.ok({"cmd": "newbattle_ok"})
        host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=60)
        host.ok({"cmd": "click_widget", "match": "ok"})
        host.wait_for("host battlescape", lambda: session.has_state(host, "BattlescapeState"), timeout=40)
        session.dismiss_battle_start_overlays(host)
        client.wait_for("client battlescape",
                        lambda: session.has_state(client, "BattlescapeState"), timeout=90)
        client.wait_for("client entry briefing pushed over BattlescapeState",
                        lambda: session.has_state(client, "BriefingState") or None, timeout=20)
        session.dismiss_client_briefing(client)

        hs0 = battle_state(host)
        cs0 = battle_state(client)
        assert hs0.get("coopGamemode") == 2 and cs0.get("coopGamemode") == 2, (
            f"expected coopGamemode 2 on both machines: host={hs0.get('coopGamemode')} "
            f"client={cs0.get('coopGamemode')}")

        seat0 = [u for u in hs0["units"] if u.get("coop") == 0]
        seat1 = [u for u in hs0["units"] if u.get("coop") == 1]
        assert seat0 and all(u["faction"] == FACTION_PLAYER for u in seat0), (
            f"seat0 units are not all FACTION_PLAYER: {seat0}")
        assert seat1 and all(u["faction"] == FACTION_HOSTILE for u in seat1), (
            f"seat1 units are not all FACTION_HOSTILE (no real alien(s) to "
            f"hand to the PvP hostile seat?): {seat1}")
        print(f"[gm2] seat0={len(seat0)} FACTION_PLAYER, "
              f"seat1={len(seat1)} FACTION_HOSTILE")

        # SS.B.4: in gm2, pin_ai_neutral pins whatever has seat NONE - by
        # construction that may legitimately be ZERO here (the mission's
        # real alien(s) sit at seat 1, not NONE). The ">0" assertion applies
        # ONLY to the classic boot above - do NOT assert it here.
        pinned = pin_ai_neutral(host, client, tag="side_begin-gm2")
        print(f"[gm2] pin_ai_neutral pinned {len(pinned)} unit(s) - 0 is "
              "legal here (SS.B.4)")

        turn0 = battle_state(host)["turn"]

        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        drive_side_change(host, client, FACTION_HOSTILE, timeout=30)

        # WR-18 / SS.B.4: during the hostile phase, the CLIENT re-selects ONE
        # OF ITS OWN (seat-1) units - never a peer's.
        cs_hostile = battle_state(client)
        cu_hostile = {u["id"]: u for u in cs_hostile["units"]}
        client_sel = cs_hostile.get("selectedId", -1)
        assert client_sel in cu_hostile and cu_hostile[client_sel]["coop"] == 1, (
            f"gm2 hostile phase: client's selection {client_sel} does not "
            f"resolve to an OWN (seat 1) unit: {cu_hostile.get(client_sel)}")
        print(f"[gm2] hostile phase: client selected {client_sel} (coop=1) "
              "- OWN unit, OK")

        # SS.B.4, verbatim: "the button is dead off-side by vanilla design"
        # (allowButtons() requires side==FACTION_PLAYER,
        # BattlescapeState.cpp:btnEndTurnClick) - advance with the host
        # `battle_action end_turn` LEVER instead (bg->requestEndTurn(false),
        # TestServer.cpp), which is what bypasses that gate.
        host.ok({"cmd": "battle_action", "action": "end_turn"})
        drive_side_change(host, client, FACTION_PLAYER, turn0 + 1, timeout=30)

        session.wait_host_idle(host, client, timeout=30)

        cevs = event_log(client, tail=256)
        begins = [e for e in cevs if e.get("actionId") == 0 and e.get("kind") == "side_begin"]
        assert len(begins) == 3, (
            f"expected 3 side_begin envelopes for one full gm2 cycle (M9a-4), "
            f"got {len(begins)}: {begins}")

        hh, ch = assert_hash_clean(host, client, full=True, what="gm2 post-cycle boundary")
        print(f"[gm2] all {len(hh)} buckets EQUAL after the full cycle")
        print("PASS: repro_atom_side_begin gm2 scenario")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    run_classic()
    run_gm2()


if __name__ == "__main__":
    try:
        main()
        print("ALL SPEC 9 repro_atom_side_begin TESTS PASSED")
    except session.KnownFlake as e:
        session.print_known_flake_banner("repro_atom_side_begin", e.tracking, str(e))
        print(f"\nrepro_atom_side_begin: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(2)
    except AssertionError as e:
        print(f"\nrepro_atom_side_begin: FAIL\nAssertionError: {e}")
        sys.exit(2)
    except TimeoutError as e:
        print(f"\nrepro_atom_side_begin: FAIL\nTimeoutError: {e}")
        sys.exit(2)
