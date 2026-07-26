"""Issue #93: rejoining a SKIRMISH battle, and what happens when the HOST leaves.

Ruling 1 of the issue says a peer dropping mid-battle raises the reconnect
dialog - "waiting for X" with SAVE & QUIT / ABANDON GAME while nobody is there,
"All players connected" / RESUME once they are back. In a NEW BATTLE > COOP
session the second half was unreachable: nothing let a client rejoin a running
skirmish battle, so the dialog could only ever be escaped by quitting.

A skirmish battle is streamed as ONE live snapshot ("battlehost" -> the client
loads it as "battleclient"), which is exactly what a rejoiner needs. This suite
covers the wiring that lets the host serve that snapshot to a returning player:

  REJOIN     the client comes back mid-battle -> it lands in the RUNNING battle
             (not a lobby, not a new campaign) and holds; the host's dialog flips
             to "All players connected" with RESUME.
  RESUME     the host presses RESUME -> both machines are on the tactical map,
             connected, with the co-op battle handshake re-armed and command of
             the squad split between them again.
  HOST-LEAVE (ruling 4) the HOST walks out of a skirmish battle -> the client is
             told, stays frozen behind the message, and lands on the main menu
             when it acknowledges. It must never be handed the battle to finish
             on its own.
  CAMPAIGN-HOST-LEAVE the same for a SHARED campaign mission.

Run:  python tools/coop_test/test_skirmish_rejoin_battle.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import shared_fixture
import test_skirmish_flow as SK
import test_resume_game_in_battle as I93

states = I93.states
top = I93.top
has = I93.has
dialog = I93.dialog
in_battle_save = I93.in_battle_save

COOP_DLG_WAIT_PLAYERS = 62
COOP_DLG_CLIENT_RESUME_HOLD = 68
COOP_DLG_CONNECTION_LOST = 21


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def rejoin_skirmish(client, port, player="ClientPlayer"):
    """A returning player: NEW BATTLE > COOP > browser > join."""
    client.ok({"cmd": "open_new_battle"})
    client.wait_for("new battle", lambda: session.has_state(client, "NewBattleState"))
    client.ok({"cmd": "newbattle_coop"})
    client.wait_for("browser", lambda: session.has_state(client, "ServerList"))
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": player})


def clear_popups(gc, rounds=10):
    """Dismiss join popups (Profile) without touching a CoopState dialog."""
    for _ in range(rounds):
        if session.has_state(gc, "Profile"):
            gc.cmd({"cmd": "profile_ok"})
            time.sleep(0.5)
        else:
            return


# ----------------------------------------------------------- REJOIN/RESUME --

def scenario_rejoin_and_resume():
    print("\n===== scenario REJOIN / RESUME =====")
    port = "47997"
    host = GameClient("host", 48810, make_user_dir("i93_rj_host"))
    client = GameClient("client", 48811, make_user_dir("i93_rj_client"))
    client2 = GameClient("client2", 48812, make_user_dir("i93_rj_client2"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        I93.start_skirmish_battle(host, client, port)
        before = battle(host)
        # the split the pair had BEFORE the drop is the yardstick for the rejoin:
        # the returning player must get its own units back, not zero of them.
        before_sel = {tag: sorted(u["id"] for u in battle(gc).get("units", [])
                                  if u.get("selectable"))
                      for tag, gc in (("host", host), ("client", client))}
        print(f"PASS entry: both on the skirmish tactical map, turn "
              f"{before.get('turn')}, command split {before_sel}")

        I93.drop_client_mid_battle(host, client)
        I93.assert_frozen_over_the_battle(host, "REJOIN")
        print(f"PASS freeze: host held on {dialog(host)['title']!r}")

        # the player comes back in a fresh process (the report's flow: they went
        # all the way out to the main menu)
        client2.spawn(); client2.connect()
        rejoin_skirmish(client2, port)

        # REJOIN: the returning client must land in the RUNNING battle, held.
        client2.wait_for("client2 back in the battle",
                         lambda: in_battle_save(client2) or None, timeout=240, interval=1.0)
        assert has(client2, "BattlescapeState"), (
            f"issue #93 REJOIN: the rejoining player did not reach the battle "
            f"(stack={states(client2)}); a skirmish rejoin used to land in a lobby")
        assert not has(client2, "LobbyMenu"), \
            f"REJOIN: the rejoiner was parked in a lobby: {states(client2)}"
        hold = dialog(client2)
        assert hold.get("code") == COOP_DLG_CLIENT_RESUME_HOLD, (
            f"REJOIN: the rejoiner is not held until the host resumes: {hold} "
            f"(stack={states(client2)})")
        print(f"PASS rejoin-client: landed in the running battle, held on "
              f"{hold.get('title')!r}")

        # ...and the host's freeze dialog flips to the ready half. The join also
        # lands a "<player> has joined" popup on top of it, and a dialog only
        # think()s while it is the top state, so clear that as it appears.
        def _resume_offered():
            if session.has_state(host, "Profile"):
                host.cmd({"cmd": "profile_ok"})
                return None
            return dialog(host).get("backVisible") or None

        host.wait_for("host dialog offers RESUME", _resume_offered,
                      timeout=120, interval=0.5)
        d = dialog(host)
        assert d["code"] == COOP_DLG_WAIT_PLAYERS, f"REJOIN: wrong dialog: {d}"
        assert d["title"] == "All players connected", \
            f"issue #93 REJOIN: dialog did not report the peer's return: {d}"
        assert d["backText"] == "RESUME", f"REJOIN: action is not RESUME: {d}"
        assert not d["saveQuitVisible"] and not d["abandonVisible"], \
            f"REJOIN: the escape hatch outlived the wait: {d}"
        print(f"PASS rejoin-host: {d['title']!r} with {d['backText']!r}")

        # RESUME: both machines return to the battle they were in.
        host.ok({"cmd": "coop_dialog_back"})
        for gc, tag in ((host, "host"), (client2, "client")):
            gc.wait_for(f"{tag} back on the tactical map",
                        lambda gc=gc: (top(gc) == "BattlescapeState") or None,
                        timeout=120, interval=0.5)
        print("PASS resume: both machines are back on the tactical map")

        after = battle(host)
        assert after.get("turn") == before.get("turn"), \
            f"RESUME: the battle moved on during the drop: " \
            f"{before.get('turn')} -> {after.get('turn')}"

        # the co-op battle is live again on both machines, not two solo games
        for gc, tag in ((host, "host"), (client2, "client")):
            gc.wait_for(f"{tag} co-op session re-armed",
                        lambda gc=gc: (battle(gc).get("coopSession")
                                       and battle(gc).get("battleInit")) or None,
                        timeout=120, interval=0.5)
        hb, cb = battle(host), battle(client2)
        assert hb["coopSession"] and cb["coopSession"], \
            f"RESUME: co-op session not restored (host={hb.get('coopSession')} " \
            f"client={cb.get('coopSession')})"
        assert hb["battleInit"] and cb["battleInit"], \
            f"RESUME: the co-op battle handshake never re-ran: " \
            f"host battleInit={hb.get('battleInit')} client={cb.get('battleInit')}"

        # command is split the SAME way it was before the drop. Which machine may
        # move right now follows the co-op turn/sim ownership (one side is empty
        # while the other simulates), so the yardstick is the pre-drop split, not
        # "both sides own something".
        hsel = sorted(u["id"] for u in hb.get("units", []) if u.get("selectable"))
        csel = sorted(u["id"] for u in cb.get("units", []) if u.get("selectable"))
        assert not (set(hsel) & set(csel)), (
            f"RESUME: both machines command the same units after the rejoin "
            f"(host={hsel} client={csel})")
        assert hsel == before_sel["host"] and csel == before_sel["client"], (
            f"issue #93 RESUME: the rejoin re-dealt the squad: before={before_sel} "
            f"after={{'host': {hsel}, 'client': {csel}}}")
        # the rejoiner is looking at the same battle, not a copy of its own
        hunits = sorted(u["id"] for u in hb.get("units", []))
        cunits = sorted(u["id"] for u in cb.get("units", []))
        assert hunits == cunits, (
            f"issue #93 RESUME: the two machines hold different battles after the "
            f"rejoin (host units={hunits} client units={cunits})")
        print(f"PASS resume-control: co-op re-armed, same battle on both machines, "
              f"command split restored (host={hsel} client={csel})")
    finally:
        for gc in (host, client, client2):
            try:
                gc.shutdown()
            except Exception:
                pass


# -------------------------------------------------------------- HOST-LEAVE --

def _assert_client_sees_the_host_leave(client, tag):
    client.wait_for(f"{tag}: client told the host is gone",
                    lambda: (lambda d: (d.get("present")
                                        and d.get("code") == COOP_DLG_CONNECTION_LOST) or None)(
                        dialog(client)),
                    timeout=120, interval=0.5)
    d = dialog(client)
    assert d["backVisible"], f"{tag}: the message has no way to acknowledge it: {d}"
    assert top(client) == "CoopState", \
        f"{tag}: the message is not holding the client: {states(client)}"
    print(f"PASS {tag} told: {d['title']!r}, held behind it")

    # frozen: it must not be handed the co-op battle to finish alone
    time.sleep(8)
    assert top(client) == "CoopState", (
        f"issue #93 ({tag}): the client was left free to play a co-op battle on its "
        f"own after the host left: {states(client)}")
    print(f"PASS {tag} frozen: still held 8s later")

    client.ok({"cmd": "coop_dialog_back"})
    client.wait_for(f"{tag}: client reached the main menu",
                    lambda: (top(client) == "MainMenuState") or None,
                    timeout=60, interval=0.5)
    print(f"PASS {tag} acknowledged: OK took the client to the main menu")


def scenario_host_leaves_skirmish():
    print("\n===== scenario HOST-LEAVE (skirmish) =====")
    host = GameClient("host", 48814, make_user_dir("i93_hl_host"))
    client = GameClient("client", 48815, make_user_dir("i93_hl_client"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        I93.start_skirmish_battle(host, client, "47998")
        host.cmd({"cmd": "disconnect_to_menu"})
        _assert_client_sees_the_host_leave(client, "HOST-LEAVE")
    finally:
        host.shutdown(); client.shutdown()


def scenario_host_leaves_campaign_battle():
    print("\n===== scenario CAMPAIGN-HOST-LEAVE =====")
    js = shared_fixture.bring_up("i93_hlc", (48816, 48817, 48416))
    try:
        I93._fly_shared_squad_into_a_battle(js)
        js.host.cmd({"cmd": "disconnect_to_menu"})
        _assert_client_sees_the_host_leave(js.client, "CAMPAIGN-HOST-LEAVE")
    finally:
        js.shutdown()


def main():
    scenario_rejoin_and_resume()
    scenario_host_leaves_skirmish()
    scenario_host_leaves_campaign_battle()
    print("\nALL SKIRMISH REJOIN / HOST-LEAVE TESTS PASSED")


if __name__ == "__main__":
    main()
