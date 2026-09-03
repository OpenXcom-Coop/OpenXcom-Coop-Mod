"""Regression: a resumed PVE2 custom battle must cross the AI turn boundary.

The fresh-battle path is already covered by the parallel PVE2 suites.  This
test deliberately saves that battle, replaces both processes, loads the custom
battle through LoadGameState, hosts it through CONTINUE BATTLE, and then presses
the real END TURN button on both seats.  The test closes every host boundary
screen and requires that click to release the client's matching screen; neither
copy may remain parked there, and the following shared PLAYER side must open on
both machines.

Run: python tools/coop_test/test_skirmish_saved_pve2_end_turn.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import pvp_fixture as PVP
import session
import test_skirmish_flow as SK


SAVE = "skirmish_saved_pve2_end_turn.sav"
PORT = "47997"
OPTIONS = {"EnableCoopParallelTurns": True}
MISSION_BATTLESHIP = 6
SEED = 20260903


def write_battle_fixture(user_dir):
    """Avoid the one-unit Small Scout fixture ending during startup AI."""
    path = os.path.join(user_dir, "xcom1", "battle.cfg")
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(f"mission: {MISSION_BATTLESHIP}\n")


def top(gc):
    states = session.states(gc)
    return states[-1].split("::")[-1] if states else ""


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def in_battle(gc):
    return battle(gc).get("inBattle") or None


def battle_summary(gc):
    b = battle(gc)
    return {key: b.get(key) for key in (
        "inBattle", "coopGamemode", "parallelActive", "host", "side",
        "turn", "sideSeq", "battleInit", "activeSync", "playerTurn")}


def parallel_summary(gc):
    p = gc.cmd({"cmd": "parallel_state"})
    return {key: p.get(key) for key in (
        "parallelActive", "sideSeq", "readySeats", "autoSeats", "allReady",
        "commitBlocked", "admitBlocked", "sideCommit")}


def make_pve2_fixture(host, client):
    PVP.start_pvp_skirmish_lobby(host, client, PORT, alien_player="client")
    host_row = PVP.row_for(host, "HostPlayer")
    mode = host.ok({"cmd": "lobby_set_team", "row": host_row,
                    "team": "Alien"}).get("gamemode")
    assert mode == 4, f"fixture did not select PVE2/gamemode 4: {mode}"

    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: not session.has_state(host, "LobbyMenu") or None)
    host.ok({"cmd": "set_seed", "seed": SEED})
    client.ok({"cmd": "set_seed", "seed": SEED + 1})
    host.ok({"cmd": "newbattle_ok"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"seed {tag} entered battle", lambda gc=gc: in_battle(gc),
                    timeout=180, interval=0.5)

    # Keep the two startup stacks moving together.  PVE2 deliberately begins
    # with an opponent-AI cycle; draining one process all the way before even
    # entering the other would manufacture a startup skew unrelated to resume.
    deadline = time.time() + 180
    while time.time() < deadline:
        for gc in (host, client):
            state = top(gc)
            if state == "BriefingState":
                gc.ok({"cmd": "close_briefing"})
            elif state == "InventoryState":
                gc.ok({"cmd": "battle_inventory", "action": "ok"})
            elif state == "NextTurnState":
                gc.ok({"cmd": "dismiss_popup"})
            elif state != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
        hb, cb = battle(host), battle(client)
        if (hb.get("battleInit") and cb.get("battleInit")
                and hb.get("side") == 0 and cb.get("side") == 0
                and top(host) == "BattlescapeState"
                and top(client) == "BattlescapeState"):
            live_players = [u for u in hb.get("units", [])
                            if u.get("faction") == 0 and not u.get("isOut")]
            assert len(live_players) >= 2, (
                "deterministic PVE2 fixture has too few surviving player units: "
                f"{[u.get('id') for u in live_players]}")
            return
        time.sleep(0.25)
    raise TimeoutError(
        f"seed PVE2 did not initialize: host={session.states(host)} {battle(host)}; "
        f"client={session.states(client)} {battle(client)}")


def resume_saved_battle(host, client):
    host.ok({"cmd": "load_save_menu", "file": SAVE})
    host.wait_for("host loaded saved PVE2 battle", lambda: in_battle(host),
                  timeout=120, interval=0.5)
    host.ok({"cmd": "open_pause_coop"})
    host.wait_for("loaded battle opened HostMenu",
                  lambda: session.has_state(host, "HostMenu"), timeout=30)
    host.ok({"cmd": "host_menu_host", "visibility": 0,
             "server": "SavedPVE2", "port": PORT, "player": "HostPlayer"})
    host.wait_for("host entered resume lobby",
                  lambda: session.has_state(host, "LobbyMenu"), timeout=30)

    SK.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": PORT,
               "player": "ClientPlayer"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} joined resume lobby",
                    lambda gc=gc: session.has_state(gc, "Profile"), timeout=60)
        gc.ok({"cmd": "profile_ok"})

    host.ok({"cmd": "lobby_action"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"resumed {tag} entered battle", lambda gc=gc: in_battle(gc),
                    timeout=240, interval=0.25)

    # A mid-player-side save must resume on that same side.  In particular,
    # loading must not replay PVE2's one-time NEW-battle AI hand-off before the
    # two seats have pressed END TURN.
    deadline = time.time() + 120
    while time.time() < deadline:
        hb, cb = battle(host), battle(client)
        assert hb.get("side") == 0 and cb.get("side") == 0, (
            "loading replayed the new-PVE2 initial AI hand-off: "
            f"host side={hb.get('side')} turn={hb.get('turn')} "
            f"battleInit={hb.get('battleInit')} sideSeq={hb.get('sideSeq')}; "
            f"client side={cb.get('side')} turn={cb.get('turn')} "
            f"battleInit={cb.get('battleInit')} sideSeq={cb.get('sideSeq')}")
        if (hb.get("battleInit") and cb.get("battleInit")
                and hb.get("coopGamemode") == 4 and cb.get("coopGamemode") == 4
                and hb.get("parallelActive") and cb.get("parallelActive")):
            return
        time.sleep(0.25)
    raise TimeoutError(
        f"resumed PVE2 did not initialize: host={battle(host)} client={battle(client)}")


def main():
    host_dir = make_user_dir("saved_pve2_end_host", options=OPTIONS)
    seed_client_dir = make_user_dir("saved_pve2_end_seed", options=OPTIONS)
    write_battle_fixture(host_dir)
    write_battle_fixture(seed_client_dir)
    host = GameClient("host", 48830, host_dir)
    client = GameClient("client", 48831, seed_client_dir)
    failure = None
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        make_pve2_fixture(host, client)
        host.ok({"cmd": "save_game", "file": SAVE})
        save_path = os.path.join(host_dir, "xcom1", SAVE)
        assert os.path.exists(save_path), f"fixture save was not written: {save_path}"
        print("PASS fixture: saved a live PVE2 custom battle")

        host.shutdown(); client.shutdown()
        host = GameClient("host", 48832, host_dir)
        client = GameClient("client", 48833,
                            make_user_dir("saved_pve2_end_clean", options=OPTIONS))
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        resume_saved_battle(host, client)
        print("PASS resume: both machines restored gamemode 4 parallel battle")

        start_turn = battle(host).get("turn")
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        # Dismiss each host-owned boundary exactly as a player does in the UI.
        # The host click must mirror to the client; never dismiss the client
        # independently, because that would hide a broken click_close packet.
        deadline = time.time() + 180
        while time.time() < deadline:
            hb, cb = battle(host), battle(client)
            if (top(host) == "BattlescapeState"
                    and top(client) == "BattlescapeState"
                    and hb.get("side") == 0 and cb.get("side") == 0
                    and hb.get("turn", 0) > start_turn
                    and hb.get("battleInit") and cb.get("battleInit")):
                break
            if top(host) == "NextTurnState":
                client_had_screen = top(client) == "NextTurnState"
                host.ok({"cmd": "dismiss_popup"})
                if client_had_screen:
                    host.wait_for(
                        "host click mirrored off the client End Turn screen",
                        lambda: top(client) != "NextTurnState" or None,
                        timeout=30, interval=0.2)
            else:
                # A desync notice or an ordinary informational popup is not the
                # End Turn screen under test.  Clear it symmetrically so it
                # cannot prevent the post-turn battleInit handshake from running.
                for gc in (host, client):
                    if top(gc) not in ("BattlescapeState", "NextTurnState"):
                        gc.cmd({"cmd": "dismiss_popup"})
            time.sleep(0.5)
        else:
            raise TimeoutError(
                "saved PVE2 remained in the end-turn/AI boundary: "
                f"host stack={session.states(host)} battle={battle_summary(host)}; "
                f"client stack={session.states(client)} battle={battle_summary(client)}")

        print("PASS regression: saved PVE2 completed AI turn without a stuck End Turn screen")
    except Exception as exc:
        failure = exc
        print(f"[FAIL] {exc}")
        for tag, gc in (("host", host), ("client", client)):
            try:
                print(f"  {tag} stack: {session.states(gc)}")
                print(f"  {tag} battle: {battle_summary(gc)}")
                print(f"  {tag} parallel: {parallel_summary(gc)}")
            except Exception as debug_exc:
                print(f"  {tag} debug failed: {debug_exc}")
    finally:
        host.shutdown(); client.shutdown()

    if failure:
        raise SystemExit(2)
    print("ALL SAVED PVE2 END-TURN TESTS PASSED")


if __name__ == "__main__":
    main()
