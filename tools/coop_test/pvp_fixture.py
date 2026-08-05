"""PvP game-mode bring-up helpers for the co-op test harness.

Skirmish PvP (NEW BATTLE > COOP):
  start_pvp_skirmish(host, client, port, alien_player="client")
    -> gamemode, both machines at the tactical map

Campaign PvP (New Game > Co-op):
  start_pvp_campaign(host, client, port, alien_player="client")
    -> gamemode, both machines on the geoscape
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import LAND_LON, LAND_LAT
import session
import test_skirmish_flow as SK


def _lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def _states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def _has(gc, name):
    return any(name in s for s in _states(gc))


def _top(gc):
    return _states(gc)[-1]


def row_for(gc, name_substring):
    """Return the _connectedPlayers index of the player whose name contains
    `name_substring`. The roster is sorted (by name ascending by default);
    this finds the correct row regardless of sort order."""
    names = _lobby(gc).get("players", [])
    for i, n in enumerate(names):
        if name_substring in n:
            return i
    raise AssertionError(f"could not find {name_substring!r} in roster: {names}")


# ---- skirmish PvP -----------------------------------------------------------


def start_pvp_skirmish_lobby(host, client, port, alien_player="client"):
    """Skirmish lobby with one player on the Alien team.

    alien_player: 'client' (gamemode 2) or 'host' (gamemode 3).

    Returns (gamemode, host_lobby_state, client_lobby_state).
    The host's BATTLE SETTINGS button is visible.  No battle has started.
    """
    SK.skirmish_host(host, port)
    SK.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port,
               "player": "ClientPlayer"})
    host.wait_for("host join popup",
                  lambda: _has(host, "Profile"))
    client.wait_for("client join popup",
                    lambda: _has(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered",
                  lambda: _lobby(host).get("buttonVisible") or None)


    if alien_player == "client":
        row = row_for(host, "ClientPlayer")
    else:
        row = row_for(host, "HostPlayer")
    r = host.ok({"cmd": "lobby_set_team", "row": row, "team": "Alien"})
    gamemode = r["gamemode"]
    assert gamemode in (2, 3), \
        f"expected a PvP mode (2 or 3), got gamemode {gamemode}"
    time.sleep(1)

    host_ls = _lobby(host)
    client_ls = _lobby(client)
    return gamemode, host_ls, client_ls


def start_pvp_skirmish_battle(host, client, port, alien_player="client"):
    """Full PvP skirmish: lobby -> BATTLE SETTINGS -> OK -> tactical map.

    Returns gamemode.  Both machines are on the BattlescapeState tactical map.
    """
    gamemode, _host_ls, _client_ls = \
        start_pvp_skirmish_lobby(host, client, port, alien_player)

    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not _has(host, "LobbyMenu")) or None)
    host.ok({"cmd": "newbattle_ok"})

    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(
            f"{tag} in battle",
            lambda gc=gc: (
                _has(gc, "BriefingState") or _has(gc, "InventoryState")
                or _has(gc, "BattlescapeState")
            ) or None,
            timeout=180, interval=0.5)

    for gc in (host, client):
        if _has(gc, "BriefingState"):
            gc.ok({"cmd": "close_briefing"})

    for gc in (host, client):
        deadline = time.time() + 120
        while time.time() < deadline:
            if _has(gc, "InventoryState"):
                gc.ok({"cmd": "battle_inventory", "action": "ok"})
            if _top(gc) == "BattlescapeState":
                break
            gc.cmd({"cmd": "dismiss_popup"})
            time.sleep(0.5)

    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(
            f"{tag} tactical map",
            lambda gc=gc: _has(gc, "BattlescapeState"),
            timeout=120, interval=0.5)

    for gc in (host, client):
        for _ in range(20):
            if _top(gc) == "BattlescapeState":
                break
            gc.cmd({"cmd": "dismiss_popup"})
            time.sleep(0.5)

    return gamemode


# ---- campaign PvP -----------------------------------------------------------


def start_pvp_campaign(host, client, port, alien_player="client"):
    """New PvP campaign through the real flow.

    alien_player: 'client' (gamemode 2) or 'host' (gamemode 3).

    Returns gamemode.  Both machines land on the geoscape.
    The alien-controlling player skips base placement (no_bases fix).
    """
    host.ok({"cmd": "open_new_game", "mode": "coop"})
    host.wait_for("difficulty", lambda: _has(host, "NewGameState"))
    host.ok({"cmd": "newgame_ok"})
    host.wait_for("host window", lambda: _has(host, "HostMenu"))

    host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": port,
             "player": "HostPlayer"})
    host.wait_for("host lobby", lambda: _has(host, "LobbyMenu"))

    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port,
               "player": "ClientPlayer"})
    client.wait_for("client lobby", lambda: _has(client, "LobbyMenu"),
                    timeout=120)
    for gc in (host, client):
        gc.wait_for("join popup", lambda gc=gc: _has(gc, "Profile"))
        gc.ok({"cmd": "profile_ok"})

    host.wait_for("start eligible",
                  lambda: _lobby(host).get("startEligible") or None)

    if alien_player == "client":
        row = row_for(host, "ClientPlayer")
    else:
        row = row_for(host, "HostPlayer")
    r = host.ok({"cmd": "lobby_set_team", "row": row, "team": "Alien"})
    gamemode = r["gamemode"]
    assert gamemode in (2, 3), \
        f"expected a PvP mode (2 or 3), got gamemode {gamemode}"

    session.start_campaign_via_button(host)

    # gamemode 2: host=XCOM (places base), client=Alien (no_bases)
    # gamemode 3: host=Alien (no_bases), client=XCOM (places base)
    xcom_gc = host if alien_player == "client" else client
    alien_gc = client if alien_player == "client" else host

    # XCOM player places base via BuildNewBaseState.
    # The alien player (if host) enters COOP_DLG_WAIT_PLAYERS instead.
    if _has(xcom_gc, "BuildNewBaseState"):
        xcom_gc.wait_for(f"{alien_player} XCOM base placement",
                         lambda gc_=xcom_gc: _has(gc_, "BuildNewBaseState"))
        r = xcom_gc.ok({"cmd": "place_first_base",
                        "lon": LAND_LON, "lat": LAND_LAT,
                        "name": "XcomBase"})
        if not r.get("ok"):
            r = xcom_gc.ok({"cmd": "place_first_base",
                            "lon": 0.706, "lat": -0.507,
                            "name": "XcomBase"})
    else:
        # Can't place base (no_bases). Fall through to session-up.
        pass

    # If the alien player is the host, they enter COOP_DLG_WAIT_PLAYERS
    # and need to click BEGIN once the client's world blob arrives.
    if alien_player == "host":
        alien_gc = host  # host=alien, client=XCOM places base
        has_blob = alien_gc.wait_for(
            "host wait for client world blob",
            lambda: host.cmd({"cmd": "has_coop_file",
                "key": host.cmd({"cmd": "get_coop"}).get(
                    "pendingHostSaveName", "")
            }).get("present") or None,
            timeout=120, interval=1.0)
        # Actual blob check: use has_coop_file with the right key
        # For simplicity, just wait and click BEGIN
        time.sleep(3)
        if _has(host, "CoopState"):
            host.ok({"cmd": "coop_dialog_back"})

    time.sleep(2)
    if _has(alien_gc if alien_player == "client" else host, "BuildNewBaseState"):
        print(f"WARNING: {alien_player} (alien player) was prompted to place "
              f"a base (no_bases not set)")

    for gc in (host, client):
        # Session is up when the player sees the geoscape globe with
        # no dialogs on top — the top state IS GeoscapeState.
        gc.wait_for("session up (geoscape)",
                    lambda gc_=gc: (
                        _states(gc_) and "GeoscapeState" in _states(gc_)[-1]
                    ) or None,
                    timeout=120)
    print("PvP campaign session up")
    return gamemode
