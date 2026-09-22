"""Issue #93: a peer dropping mid-battle, and RESUME GAME while a battle runs.

Reported: in a NEW BATTLE > COOP battle the client left for the main menu, the
host's coop menu (LobbyMenu) popped up over the tactical map offering RESUME
GAME - and pressing it dropped the host on the GEOSCAPE with the battle gone.

SPEC 18 (r4 T4) D97/R1(c) ROUTING (2026-09-21): this file used to also cover
a client dropping mid-battle (FREEZE/STAY-FROZEN/ABANDON). Those scenarios are
SPEC 16's (test_spec16_pause_on_leave.py's S1/S4, test_skirmish_rejoin_
battle.py) and are REMOVED from this file - their bodies are deleted below;
the helper functions SAVE-AND-QUIT still uses are kept. R1(c) ran every
scenario in this file once at the SPEC 18 tip with the skip removed:
SAVE-AND-QUIT's own assertions pass (un-skipped here, S6 - this unit's, the
mid-battle save->load-back-into-battle proof, one of the "nine save/resume
harness tests" SPEC 18 re-points); MENU-HOST/MENU-CLIENT and PRE-BATTLE/
PRE-GAME were GREEN at the tip and stay, unmodified, no code. The pre-existing
teardown rc=3 on SAVE-AND-QUIT (F391/F392 family, D120-waived) is OUT OF this
unit's scope - not fixed here.

SCENARIOS (this file, post-routing)
  SAVE-AND-QUIT SAVE & QUIT -> save-slot list -> a .sav that loads back INTO the
                battle -> main menu.
  MENU-HOST     campaign mission, both players in it, HOST opens the coop menu
                and presses RESUME GAME -> back on the tactical map.
  MENU-CLIENT   the same from the CLIENT's machine.
  PRE-BATTLE    a skirmish drop with no battle running still re-opens the lobby
                (that IS where the host belongs) - the fix is scoped to battles.
  PRE-GAME      the pre-game campaign lobby still offers no RESUME GAME.

The geoscape half of the coop menu (playtest B7) is test_shared_ingame_coop_menu.

Run:  python tools/coop_test/test_resume_game_in_battle.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import shared_fixture
import test_skirmish_flow as SK

COOP_DLG_WAIT_PLAYERS = 62


# ---------------------------------------------------------------- helpers --

def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top(gc):
    return states(gc)[-1].split("::")[-1]


def has(gc, name):
    return any(name in s for s in states(gc))


def in_battle_save(gc):
    """The world carries a SavedBattleGame (independent of the UI stack)."""
    return bool(gc.cmd({"cmd": "get_coop"}).get("inBattle"))


def dialog(gc):
    return gc.cmd({"cmd": "coop_dialog_info"})


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def settle_on_tactical(gc, tag, timeout=180):
    """Walk briefing / pre-battle inventory / popups until the tactical map is
    the top state, exactly as a player would: press each dialog's real control
    and wait through transient no-button coop holds instead of forcing them."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = top(gc)
        if t == "BattlescapeState":
            return
        if t == "BriefingState":
            gc.cmd({"cmd": "close_briefing"})
        elif t == "InventoryState":
            gc.cmd({"cmd": "battle_inventory", "action": "ok"})
        else:
            # dismiss_popup presses the dialog's real button now (CoopState
            # Back, GeoscapeEvent / MonthlyReport / NextTurn / etc. OK). A
            # transient coop load/stream hold has no button to press yet and
            # answers {"wait": True} - that is not an error; we keep polling,
            # the way a player waits for the battle to finish landing.
            gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.5)
    raise AssertionError(f"{tag}: never settled on the tactical map: {states(gc)}")


def wait_peer_dropped(gc, what):
    gc.wait_for(what,
                lambda: (not gc.cmd({"cmd": "get_coop"}).get("coopSession")) or None,
                timeout=90, interval=0.5)


def start_skirmish_battle(host, client, port):
    """NEW BATTLE > COOP > lobby > BATTLE SETTINGS > OK, both on the tactical map."""
    SK.skirmish_host(host, port)
    SK.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port,
               "player": "ClientPlayer"})
    for gc in (host, client):
        gc.wait_for("join popup", lambda gc=gc: session.has_state(gc, "Profile"))
        gc.ok({"cmd": "profile_ok"})
    host.wait_for("BATTLE SETTINGS offered",
                  lambda: lobby(host).get("buttonVisible") or None)
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at the setup screen",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    host.ok({"cmd": "newbattle_ok"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} in the battle",
                    lambda gc=gc: in_battle_save(gc) or None, timeout=180, interval=1.0)
        settle_on_tactical(gc, tag)


def drop_client_mid_battle(host, client):
    """The client leaves the battle for the main menu (battlescape Options >
    ABANDON GAME in the report); returns once the host has raised its dialog."""
    client.cmd({"cmd": "disconnect_to_menu"})
    client.wait_for("client at the main menu",
                    lambda: (top(client) == "MainMenuState") or None,
                    timeout=60, interval=0.5)
    wait_peer_dropped(host, "host noticed the drop")
    host.wait_for("host raised the reconnect dialog",
                  lambda: (lambda d: (d.get("present")
                                      and d.get("code") == COOP_DLG_WAIT_PLAYERS) or None)(
                      dialog(host)),
                  timeout=90, interval=0.5)


# ------------------------------------------------------- the drop itself ---
# (FREEZE/STAY-FROZEN/ABANDON scenario BODIES removed per D97/R1(c): they are
# SPEC 16's S1/S4, live in test_spec16_pause_on_leave.py/test_skirmish_
# rejoin_battle.py. drop_client_mid_battle/wait_peer_dropped above are KEPT -
# scenario_save_and_quit below still uses them.)


def scenario_save_and_quit():
    """SAVE & QUIT on the mid-battle freeze writes a real BATTLE save."""
    print("\n===== scenario SAVE-AND-QUIT =====")
    host_dir = make_user_dir("i93_savequit_host")
    host = GameClient("host", 48796, host_dir)
    client = GameClient("client", 48797, make_user_dir("i93_savequit_client"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        start_skirmish_battle(host, client, "47994")
        drop_client_mid_battle(host, client)

        before = set(session.save_files(host_dir))
        host.ok({"cmd": "coop_dialog_save_quit"})
        host.wait_for("save-slot list opened",
                      lambda: session.has_state(host, "ListSaveState"),
                      timeout=30, interval=0.5)
        host.ok({"cmd": "list_save_confirm", "name": "stranded_battle"})
        host.wait_for("host reached the main menu after saving",
                      lambda: (top(host) == "MainMenuState") or None,
                      timeout=90, interval=0.5)

        new = sorted(set(session.save_files(host_dir)) - before)
        saves = [f for f in new if f.endswith(".sav")]
        assert saves, f"SAVE & QUIT wrote no save file (user dir gained {new})"
        print(f"PASS save-quit: wrote {saves} and returned to the main menu")

        # the point of saving mid-battle: it comes back as a battle
        # (load_save resolves inside the save dir, so pass the bare file name)
        host.ok({"cmd": "load_save", "file": os.path.basename(saves[0])})
        host.wait_for("save loaded",
                      lambda: in_battle_save(host) or None, timeout=90, interval=0.5)
        print("PASS save-quit-load: the save comes back INTO the battle")
    finally:
        host.shutdown(); client.shutdown()


# ------------------------------------------- the coop menu over a battle ---

def _fly_shared_squad_into_a_battle(js):
    """Put the SHARED campaign's craft on a seeded terror site and take both
    machines into the mission (same drive as test_shared_battle)."""
    host, client = js.host, js.client
    base = next(b for b in host.ok({"cmd": "geo_state"})["bases"]
                if not b.get("coopBase") and not b.get("coopIcon"))
    blon, blat = base["lon"], base["lat"]
    cid = next(c for c in base["crafts"] if "SKYRANGER" in c["type"])["id"]

    soldiers = []
    for b in host.ok({"cmd": "get_soldiers"})["bases"]:
        soldiers.extend(b["soldiers"])
    for sid in sorted(s["id"] for s in soldiers)[:2]:
        host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})

    site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                    "deployment": "STR_TERROR_MISSION", "lon": blon + 0.35,
                    "lat": blat + 0.10, "race": "STR_SECTOID", "hours": 240})
    host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
             "lon": blon + 0.34, "lat": blat + 0.10, "dest": f"site:{site['site_id']}",
             "fuel": 999999, "lowFuel": False})

    def _prompt():
        if has(host, "ConfirmLandingState"):
            return True
        host.cmd({"cmd": "geo_set_speed", "idx": 2})  # geo_run auto-declines
        return None

    host.wait_for("landing prompt", _prompt, timeout=120, interval=0.5)
    host.ok({"cmd": "confirm_landing"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} entered the battle",
                    lambda gc=gc: in_battle_save(gc) or None, timeout=240, interval=1.0)
        settle_on_tactical(gc, tag)


def _resume_from_the_coop_menu(gc, who, peer):
    """Open the in-game coop menu over a running battle and press RESUME GAME."""
    gc.ok({"cmd": "open_coop_menu"})
    gc.wait_for(f"{who} coop menu on top",
                lambda: ("LobbyMenu" in top(gc)) or None, timeout=30, interval=0.3)
    gc.wait_for(f"{who} lobby offers RESUME GAME",
                lambda: (lobby(gc).get("buttonText") == "RESUME GAME"
                         and lobby(gc).get("buttonVisible")) or None,
                timeout=30, interval=0.3)
    print(f"PASS {who} menu: coop menu over the battle offers RESUME GAME")

    gc.ok({"cmd": "lobby_action"})
    gc.wait_for(f"{who} back on the tactical map",
                lambda: (top(gc) == "BattlescapeState") or None, timeout=30, interval=0.3)
    assert not has(gc, "LobbyMenu"), \
        f"{who}: RESUME GAME left the coop menu on the stack: {states(gc)}"
    assert top(gc) == "BattlescapeState", (
        f"issue #93 ({who}): RESUME GAME dropped the player on {top(gc)!r} instead of "
        f"the running battle: {states(gc)}")
    assert gc.cmd({"cmd": "get_coop"}).get("coopStatic"), \
        f"{who}: RESUME GAME dropped the connection"
    assert in_battle_save(peer), f"{who}: the peer lost its battle: {states(peer)}"
    print(f"PASS {who} resume: back on the tactical map, still connected, "
          f"peer unaffected")


def scenario_coop_menu_midbattle():
    """MENU-HOST + MENU-CLIENT: the campaign half of the report."""
    print("\n===== scenario MENU-HOST / MENU-CLIENT =====")
    js = shared_fixture.bring_up("i93_menu", (48798, 48799, 48398))
    host, client = js.host, js.client
    try:
        _fly_shared_squad_into_a_battle(js)
        print(f"PASS entry: both machines in the campaign mission (host={states(host)})")
        assert has(host, "GeoscapeState"), \
            f"premise changed: no campaign geoscape under the battle: {states(host)}"
        _resume_from_the_coop_menu(host, "host", client)
        _resume_from_the_coop_menu(client, "client", host)
    finally:
        js.shutdown()


# --------------------------------------------------- untouched behaviour ---

def scenario_prebattle_drop_and_lobby_gating():
    """PRE-BATTLE + PRE-GAME: the fix is scoped to running battles.

    A skirmish drop with no battle running still re-opens the lobby (the host is
    back at NEW BATTLE and that is where a peer would rejoin), and the pre-game
    campaign lobby still shows no RESUME GAME."""
    print("\n===== scenario PRE-BATTLE / PRE-GAME =====")
    host = GameClient("host", 48800, make_user_dir("i93_pre_host"))
    client = GameClient("client", 48801, make_user_dir("i93_pre_client"))
    port = "47995"
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        SK.skirmish_host(host, port)
        SK.skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port,
                   "player": "ClientPlayer"})
        for gc in (host, client):
            gc.wait_for("join popup", lambda gc=gc: session.has_state(gc, "Profile"))
            gc.ok({"cmd": "profile_ok"})
        host.wait_for("BATTLE SETTINGS offered",
                      lambda: lobby(host).get("buttonVisible") or None)
        # step out to the setup screen: lobby closed, session live, NO battle
        host.ok({"cmd": "lobby_action"})
        host.wait_for("host at the setup screen",
                      lambda: (not session.has_state(host, "LobbyMenu")) or None)
        assert not in_battle_save(host), "premise: no battle should be running yet"

        client.cmd({"cmd": "disconnect_to_menu"})
        wait_peer_dropped(host, "host noticed the pre-battle drop")
        host.wait_for("host back in the lobby",
                      lambda: session.has_state(host, "LobbyMenu") or None,
                      timeout=60, interval=0.5)
        assert dialog(host).get("code") != COOP_DLG_WAIT_PLAYERS, (
            "PRE-BATTLE: a drop with no battle running must not freeze the host "
            f"behind the reconnect dialog: {dialog(host)}")
        print("PASS pre-battle: a drop before the battle still re-opens the lobby")
    finally:
        host.shutdown(); client.shutdown()

    # PRE-GAME: the pre-game campaign lobby (paused geoscape underneath, session
    # not locked) must still not offer RESUME GAME.
    host2 = GameClient("host", 48800, make_user_dir("i93_pre2_host"))
    try:
        host2.spawn(); host2.connect()
        host2.ok({"cmd": "open_new_game", "mode": "shared"})
        host2.wait_for("difficulty", lambda: session.has_state(host2, "NewGameState"))
        host2.ok({"cmd": "newgame_ok"})
        host2.wait_for("host window", lambda: session.has_state(host2, "HostMenu"))
        host2.ok({"cmd": "host_tcp", "server": "TestSrv", "port": "47996",
                  "player": "HostPlayer"})
        host2.wait_for("host lobby", lambda: session.has_state(host2, "LobbyMenu"))
        ls = lobby(host2)
        assert ls.get("buttonText") != "RESUME GAME", (
            "PRE-GAME: the pre-game campaign lobby offers RESUME GAME - its paused "
            f"geoscape is not a running game: {ls}")
        print(f"PASS pre-game: the pre-game lobby button is {ls.get('buttonText')!r}, "
              f"not RESUME GAME")
    finally:
        host2.shutdown()


def main():
    # FREEZE/STAY-FROZEN/ABANDON dropped per D97/R1(c) routing (SPEC 16 owns
    # them now) - this file runs SAVE-AND-QUIT (S6) + the coop-menu-over-a-
    # battle + pre-battle/pre-game scenarios only.
    scenario_save_and_quit()
    scenario_coop_menu_midbattle()
    scenario_prebattle_drop_and_lobby_gating()
    print("\nALL RESUME-GAME-IN-BATTLE TESTS PASSED")


if __name__ == "__main__":
    main()
