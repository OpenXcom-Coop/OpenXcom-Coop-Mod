"""Regression: joining a hosted custom-battle save must not wait for RESUME.

A loaded skirmish save already has a SavedBattleGame before its new multiplayer
session starts.  The join gate used to mistake that fact for a live-session
reconnect: the client downloaded the map and reached BattlescapeState, then was
parked forever in COOP_DLG_CLIENT_RESUME_HOLD even though the host had no
reconnect dialog (and therefore no RESUME button capable of releasing it).

This test creates a real co-op skirmish save, replaces both processes, loads the
save on the new host, and opens COOP through the real Battlescape pause menu.
Like a campaign resume, that must open HostMenu and put both players in a lobby;
the map must not stream until the host presses CONTINUE BATTLE. The client must
then enter it without dialog 68.  The existing
test_skirmish_rejoin_battle.py covers the opposite half: a genuine mid-session
reconnect still must hold until the host presses RESUME.

Run:  python tools/coop_test/test_skirmish_saved_battle_join.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_skirmish_flow as skirmish_flow
import pvp_fixture


SAVE = "skirmish_saved_battle_join.sav"
PORT = "47998"
CLIENT_RESUME_HOLD = 68


def in_battle(gc):
    return gc.cmd({"cmd": "battle_state"}).get("inBattle") or None


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def selectable(gc):
    return sorted(u["id"] for u in battle(gc).get("units", [])
                  if u.get("selectable") and not u.get("isOut"))


def end_turn(gc):
    gc.ok({"cmd": "battle_action", "action": "end_turn_button"})


def main():
    host_dir = make_user_dir(
        "skirm_saved_join_host", options={"EnableCoopParallelTurns": True})
    host = GameClient("host", 48820, host_dir)
    client = GameClient(
        "client", 48821, make_user_dir("skirm_saved_join_client_seed"))
    fail = None

    try:
        # Produce the fixture through the real skirmish flow.  Only the host's
        # local save survives; the joining client below starts with a clean dir.
        host.spawn()
        host.connect()
        client.spawn()
        client.connect()
        gamemode = pvp_fixture.start_pvp_skirmish_battle(
            host, client, PORT, alien_player="host")
        assert gamemode == 3, f"fixture did not create PvP2 gamemode 3: {gamemode}"
        host.wait_for("seed host in battle", lambda: in_battle(host), timeout=120)
        host.wait_for("seed PvP battle initialized",
                      lambda: battle(host).get("battleInit") or None, timeout=120)
        host.ok({"cmd": "save_game", "file": SAVE})
        save_path = os.path.join(host_dir, "xcom1", SAVE)
        assert os.path.exists(save_path), f"host did not write {save_path}"
        print(f"PASS fixture: wrote a real custom-battle save ({SAVE})")

        host.shutdown()
        client.shutdown()

        # Fresh processes are important: no live-session/reconnect flags may
        # leak from the session that produced the save.
        host = GameClient("host", 48822, host_dir)
        client = GameClient(
            "client", 48823,
            make_user_dir("skirm_saved_join_client_clean",
                          options={"EnableCoopParallelTurns": False}))
        host.spawn()
        host.connect()
        client.spawn()
        client.connect()

        host.ok({"cmd": "load_save", "file": SAVE})
        host.wait_for("host loaded saved battle", lambda: in_battle(host), timeout=120)
        before = host.ok({"cmd": "get_coop"})
        assert not before.get("sessionLocked"), (
            "a freshly loaded custom battle already looks like a live session: "
            f"{before}")

        host.ok({"cmd": "open_pause_coop"})
        host.wait_for("loaded battle opened HostMenu",
                      lambda: session.has_state(host, "HostMenu"), timeout=30)
        assert not session.has_state(host, "ServerList"), (
            "loaded Custom Battle COOP opened the server browser instead of "
            f"HostMenu: {session.states(host)}")
        assert host.ok({"cmd": "get_coop"}).get("customBattleResumePending"), (
            "loaded Custom Battle did not arm its lobby-gated resume flow")

        host.ok({"cmd": "host_menu_host", "visibility": 0,
                 "server": "SavedBattle", "port": PORT,
                 "player": "HostPlayer"})
        host.wait_for("host entered continue-battle lobby",
                      lambda: session.has_state(host, "LobbyMenu"), timeout=30)

        skirmish_flow.skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": PORT,
                   "player": "ClientPlayer"})

        # Campaign-style gate: joining alone must put both players in the lobby.
        # In particular it must not trigger Downloading map or adopt the battle.
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} join popup",
                        lambda gc=gc: session.has_state(gc, "Profile"), timeout=60)
            assert session.has_state(gc, "LobbyMenu"), (
                f"{tag} did not wait in LobbyMenu: {session.states(gc)}")
            gc.ok({"cmd": "profile_ok"})

        time.sleep(2)
        assert not in_battle(client), (
            "client downloaded the saved map before the host pressed CONTINUE BATTLE")
        action = host.ok({"cmd": "lobby_state"})
        assert action.get("buttonVisible") and action.get("buttonText") == "CONTINUE BATTLE", (
            f"host lobby did not offer CONTINUE BATTLE: {action}")
        assert not client.ok({"cmd": "coop_dialog_info"}).get("present"), (
            "client opened a download/hold dialog while it should still be in lobby")
        print("PASS gate: HostMenu -> both in lobby; no map transfer before CONTINUE BATTLE")

        host.ok({"cmd": "lobby_action"})
        host.wait_for("host returned to loaded battle",
                      lambda: (not session.has_state(host, "LobbyMenu")
                               and not session.has_state(host, "PauseState")) or None,
                      timeout=30)
        assert session.has_state(host, "BattlescapeState"), (
            f"host did not return to its loaded battle: {session.states(host)}")

        # CONTINUE BATTLE is the sole map-transfer trigger.
        client.wait_for("client downloaded the saved battle",
                        lambda: in_battle(client), timeout=240, interval=0.5)
        time.sleep(2)

        dialog = client.ok({"cmd": "coop_dialog_info"})
        assert not (dialog.get("present")
                    and dialog.get("code") == CLIENT_RESUME_HOLD), (
            "client reached the saved custom battle but was stranded on "
            f"Waiting for host to resume: {dialog}; "
            f"stack={session.states(client)}")
        assert not session.has_state(client, "LobbyMenu"), (
            "the saved battle was routed back through the pre-battle lobby: "
            f"{session.states(client)}")
        assert not session.has_state(client, "BriefingState"), (
            "the saved battle incorrectly entered the new-mission briefing path: "
            f"{session.states(client)}")
        client_coop = client.ok({"cmd": "get_coop"})
        assert client_coop.get("onConnect", 0) > 0 and client_coop.get("coopSession"), (
            "client escaped the hold without a live multiplayer session: "
            f"{client_coop}")

        # Match campaign PvP battle resume: preserve gamemode 3 and its opposing
        # turns. Parallel Turns is intentionally inactive in PvP even though the
        # host option is enabled in this fixture.
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(
                f"{tag} PvP battle initialized",
                lambda gc=gc: (lambda b: b if (b.get("battleInit")
                                                and b.get("coopGamemode") == 3)
                               else None)(battle(gc)),
                timeout=120, interval=0.5)

        hb, cb = battle(host), battle(client)
        assert not hb.get("parallelActive") and not cb.get("parallelActive"), (
            f"PvP incorrectly entered Parallel Turns: host={hb}, client={cb}")
        assert hb.get("coopTurn") == 1 and cb.get("coopTurn") == 2, (
            "gamemode 3 must resume with client=XCOM on YOUR TURN and the alien "
            f"host waiting: host={hb}, client={cb}")
        assert hb.get("activeSync") is False and cb.get("activeSync") is True, (
            f"PvP executor/turn ownership is wrong: host={hb}, client={cb}")
        hp = host.ok({"cmd": "parallel_state"})
        cp = client.ok({"cmd": "parallel_state"})
        assert not hp.get("readySeats") and not hp.get("autoSeats"), (
            f"PvP host displayed a Parallel END TURN tally: {hp}")
        assert not cp.get("readySeats"), (
            f"PvP client retained Parallel END TURN readiness: {cp}")

        # Complete the exact reported PvP2 round: client XCOM ends, host Alien
        # ends, then the Next Turn screen closes. Both seats are alive, so the
        # battle must return to the client's XCOM turn instead of Debriefing.
        end_turn(client)
        host.wait_for("alien host received turn",
                      lambda: selectable(host) or None, timeout=30)
        end_turn(host)
        time.sleep(1)
        if session.states(host)[-1].endswith("NextTurnState"):
            host.ok({"cmd": "dismiss_popup"})
        time.sleep(3)

        hb, cb = battle(host), battle(client)
        assert hb.get("inBattle") and cb.get("inBattle"), (
            "saved PvP2 battle falsely ended after the first complete round: "
            f"host={hb}, client={cb}")
        assert hb.get("pvpWin", 0) == 0 and cb.get("pvpWin", 0) == 0, (
            f"saved PvP2 battle produced a false winner: host={hb}, client={cb}")
        assert selectable(client) and not selectable(host), (
            "saved PvP2 battle did not return control to client XCOM after the "
            f"alien turn: host={hb}, client={cb}")

        print("PASS regression: client downloaded the hosted custom-battle save "
              "with gamemode 3, completed XCOM+alien turns, and battle continued")
    except Exception as exc:
        fail = exc
        print(f"[FAIL] {exc}")
        for tag, gc in (("host", host), ("client", client)):
            try:
                print(f"  {tag} stack: {session.states(gc)}")
                print(f"  {tag} coop:  {gc.cmd({'cmd': 'get_coop'})}")
            except Exception as debug_exc:
                print(f"  {tag} debug failed: {debug_exc}")
    finally:
        host.shutdown()
        client.shutdown()

    if fail:
        raise SystemExit(2)
    print("ALL SAVED CUSTOM-BATTLE JOIN TESTS PASSED")


if __name__ == "__main__":
    main()
