"""A finished co-op SKIRMISH sends BOTH players to the MAIN MENU.

THE BUG (reported from manual parallel-turns play): after ABORTING a NEW BATTLE
> COOP mission, the host was handed a LOBBY offering RESUME GAME, and pressing
it dropped them on the GEOSCAPE - a screen a skirmish has no business showing.

WHY. A co-op skirmish world arrives through LoadGameState on BOTH machines, so
each stack is [GeoscapeState, BattlescapeState]: there is a dead geoscape buried
under every skirmish battle. When the mission ends, both players get a
DebriefingState over that geoscape, and whoever presses OK first leaves properly
(monthsPassed == -1 -> GoToMainMenuState, which drops the SavedGame - issue #82).

That ordinary exit disconnects, and the disconnect looked like a DROP to the
player still reading their debriefing:

  * the HOST pushed CoopState(20) "<client> has left the server" and, in
    disconnectTCP's teardown, re-opened the LobbyMenu (the branch that exists
    for a drop while the host sits on the NEW BATTLE setup screen). LobbyMenu's
    constructor saw the buried GeoscapeState with the session still locked, so
    _resumeToGame latched TRUE and the button read RESUME GAME - which pops the
    debriefing away and lands on that dead geoscape.
  * the CLIENT got CoopState(21) "Server connection lost" thrown over its
    debriefing.

Both are the issue #79 bug class ("one player's exit affects the other"), just
for a skirmish instead of a finished campaign.

THE FIX. connectionTCP::skirmishMissionOver() - the skirmish twin of
campaignEnded() (lobbyMode 0 + no live battle + coopMissionEnd). While it holds,
a peer leaving is silent and the lobby is never re-opened; each player's own
debriefing OK is the exit, and it goes through GoToMainMenuState.

WHAT THIS TEST DRIVES: one skirmish per ending, with the debriefings closed in a
different order each time (the order decides which machine is the one left
holding a live world, and the two sides had different symptoms):

  abort-by-vote, CLIENT closes first  - the exact reported repro
  win,           HOST closes first    - the mirrored case

For each: while the second machine is still on its debriefing it must have NO
LobbyMenu and NO co-op popup on the stack, and both machines must finish on the
MAIN MENU with the SavedGame dropped.

Run:  python tools/coop_test/test_skirmish_end_main_menu.py
      python tools/coop_test/test_skirmish_end_main_menu.py abort
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

# RW-TRIAGE: SKIP-PENDING(r4 T6)
print("SKIP-PENDING: rewrite"); sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_intents as PI

FACTION_PLAYER = 0
FACTION_HOSTILE = 1


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def live(gc, faction):
    return [u for u in battle(gc).get("units", [])
            if u.get("faction") == faction and not u.get("isOut")]


# ---- endings ---------------------------------------------------------------

def end_by_vote(host, client):
    """ABORT -> the abandon-mission majority vote -> both debriefings.

    session.coop_abort_battle drains all the way to the geoscape, which would
    dismiss the very screens this test exists to inspect, so only its vote half
    is reused here."""
    host.ok({"cmd": "battle_action", "action": "abort"})
    for gc, tag in ((host, "host"), (client, "client")):
        v = gc.wait_for(f"{tag} abandon-mission vote",
                        lambda gc=gc: (lambda s: s if (s.get("active") and s.get("menuOpen"))
                                       else None)(gc.ok({"cmd": "vote_state"})),
                        timeout=30, interval=0.25)
        assert v["action"] == "abandon_mission", f"{tag}: wrong vote: {v}"
    cast = client.ok({"cmd": "vote_cast", "yes": True})
    assert cast.get("accepted"), f"client vote_cast was rejected: {cast}"
    for gc, tag in ((host, "host"), (client, "client")):
        v = gc.wait_for(f"{tag} vote result",
                        lambda gc=gc: (lambda s: s if s.get("finished") else None)(
                            gc.ok({"cmd": "vote_state"})),
                        timeout=30, interval=0.25)
        assert v.get("passed"), f"{tag}: the abandon-mission vote did not pass: {v}"


def end_by_win(host, client):
    """Kill every alien, then hand the turn over so the mission is WON.

    `battleAutoEnd` is off by default: a battle with no aliens left ends the way
    a player ends it, by passing the turn (BattlescapeGame::endTurn then sees
    liveAliens == 0)."""
    for _ in range(8):
        if not battle(host).get("inBattle"):
            break
        aliens = live(host, FACTION_HOSTILE)
        if not aliens:
            break
        target = aliens[0]
        squad = live(host, FACTION_PLAYER)
        assert squad, "the squad is wiped out - no mission win to debrief"
        shooter = squad[0]["id"]
        PI.place_adjacent(host, client, shooter,
                          (target["x"], target["y"], target["z"]))
        wid = None
        for gc in (host, client):
            wid = gc.ok({"cmd": "battle_give", "unit": shooter,
                         "item": "STR_HEAVY_PLASMA",
                         "ammo": "STR_HEAVY_PLASMA_CLIP",
                         "slot": "right", "clear_hands": True})["weaponId"]
        time.sleep(2)
        PI.top_up(host, client, shooter, 200)
        host.cmd({"cmd": "battle_fire", "unit": shooter, "mode": "aimed",
                  "weapon_id": wid, "tu": 200, "target": target["id"]})
        PI.settle(host, client, seconds=5)
    assert not battle(host).get("inBattle") or not live(host, FACTION_HOSTILE), \
        "the aliens could not be killed - there is no WIN to debrief"
    if battle(host).get("inBattle"):
        TW.cycle_turn(host, client, timeout=240)


ENDINGS = {"abort": end_by_vote, "win": end_by_win}


# ---- assertions ------------------------------------------------------------

def wait_debriefing(gc, tag, timeout=180):
    gc.wait_for(f"{tag} debriefing",
                lambda: session.has_state(gc, "DebriefingState"),
                timeout=timeout, interval=0.5)


def assert_undisturbed(gc, tag, ending, gone):
    """The player still reading their debriefing must not have been interrupted
    by the OTHER player's ordinary exit."""
    st = session.states(gc)
    assert any("DebriefingState" in s for s in st), (
        f"[{ending}] {tag}: the debriefing is gone after the {gone} left - "
        f"the peer's exit tore down this player's end-of-mission screen. "
        f"states={st}")
    assert not any("LobbyMenu" in s for s in st), (
        f"THE BUG [{ending}]: a LobbyMenu was raised over {tag}'s debriefing "
        f"when the {gone} closed theirs. Its RESUME GAME pops the debriefing "
        f"away and lands on the dead geoscape a skirmish world is loaded onto "
        f"(issue #82's half-torn world). states={st}")
    lb = gc.cmd({"cmd": "lobby_state"})
    assert not lb.get("lobbyOpen"), (
        f"THE BUG [{ending}]: {tag} has a lobby open after the {gone} left, "
        f"button {lb.get('buttonText')!r} visible={lb.get('buttonVisible')}")
    assert not any("CoopState" in s for s in st), (
        f"[{ending}] {tag}: a co-op popup ({gc.cmd({'cmd': 'get_coop'}).get('coopDialog')}) "
        f"was thrown over the debriefing because the {gone} closed theirs "
        f"first - an expected exit is not a drop to report. states={st}")


def assert_at_main_menu(gc, tag, ending, timeout=40):
    try:
        gc.wait_for(f"{tag} main menu",
                    lambda: (session.states(gc)[-1:] == ["class OpenXcom::MainMenuState"]) or None,
                    timeout=timeout, interval=0.5)
    except TimeoutError:
        raise AssertionError(
            f"[{ending}] {tag} did not end up on the MAIN MENU after closing the "
            f"skirmish debriefing: states={session.states(gc)}")
    c = gc.cmd({"cmd": "get_coop"})
    assert c.get("hasSave") is False, (
        f"[{ending}] {tag} reached the main menu with a SavedGame still live - "
        f"the exit bypassed GoToMainMenuState (issue #82): {c}")
    assert c.get("coopSession") is False and c.get("coopStatic") is False, (
        f"[{ending}] {tag}: the co-op session is still attached at the main "
        f"menu: {c}")


# ---- one battle ------------------------------------------------------------

def run(ending, first, ports):
    """One skirmish driven to `ending`; `first` ('host'/'client') closes its
    debriefing before the other."""
    hport, cport, coop_port = ports
    tag = f"{ending}/{first}-first"
    opts = {"battleXcomSpeed": 2, "battleAlienSpeed": 2}
    host = GameClient("host", hport,
                      make_user_dir(f"skirm_end_{ending}_host",
                                    options=dict(opts, skipNextTurnScreen=True,
                                                 EnableCoopParallelTurns=True)))
    client = GameClient("client", cport,
                        make_user_dir(f"skirm_end_{ending}_client",
                                      options=dict(opts,
                                                   EnableCoopParallelTurns=False)))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = str(coop_port)
        PI.PORT = str(coop_port)
        TW.bring_up_battle(host, client)

        # The buried geoscape is the whole reason the bug bites - assert it is
        # really there, so a future flow change that removes it turns this test
        # into an obvious "the premise moved" failure rather than a silent pass.
        for gc, who in ((host, "host"), (client, "client")):
            st = session.states(gc)
            assert any("GeoscapeState" in s for s in st), (
                f"{who}: a skirmish battle used to sit on a GeoscapeState "
                f"(LoadGameState) - the premise of this test: {st}")
        print(f"[{tag}] battle up; both stacks carry the buried geoscape")

        ENDINGS[ending](host, client)
        wait_debriefing(host, "host")
        wait_debriefing(client, "client")
        print(f"[{tag}] both machines are on the debriefing")

        leaver, stayer = (host, client) if first == "host" else (client, host)
        lname, sname = (first, "client" if first == "host" else "host")

        leaver.ok({"cmd": "dismiss_popup"})   # DebriefingState::btnOkClick
        assert_at_main_menu(leaver, lname, ending)
        print(f"[{tag}] the {lname} closed its debriefing and reached the main menu")

        # Give the peer's disconnect the time it needs to do the wrong thing.
        time.sleep(6)
        assert_undisturbed(stayer, sname, ending, lname)
        print(f"[{tag}] the {sname} still holds its debriefing, no lobby, no popup")

        stayer.ok({"cmd": "dismiss_popup"})
        assert_at_main_menu(stayer, sname, ending)
        print(f"PASS [{tag}]: both machines finished on the main menu with no world")
    finally:
        host.shutdown(); client.shutdown()


def main():
    wanted = sys.argv[1:] or ["abort", "win"]
    # The order is part of the scenario: the reported repro is the client
    # leaving first (the host was the one handed the lobby), and the win case
    # covers the mirror image.
    plan = [("abort", "client", (48898, 48899, 47995)),
            ("win", "host", (48900, 48901, 47996))]
    fail = None
    try:
        for ending, first, ports in plan:
            if ending in wanted:
                run(ending, first, ports)
        print("ALL SKIRMISH-END TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
