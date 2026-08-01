"""Shared session bring-up for the redesigned co-op campaign flow.

One implementation of the dance, imported by every test (no more copied
bootstrap code):

  new_campaign(host, client)   - Solo/Co-op dropdown -> difficulty -> host
                                 window -> lobby -> START CAMPAIGN -> both
                                 players place bases -> host RESUME ->
                                 session up on the geoscape.
  coop_abort_battle(h, c)      - end a live co-op battle: ABORT -> the
                                 abandon-mission majority vote -> debriefing ->
                                 both machines back on the geoscape. The ONLY
                                 safe way out of a co-op battle; see the
                                 NO_DISMISS_STATES note below.
  assert_client_zero_disk(dir) - the standing invariant: a co-op client never
                                 writes save data to disk. Call in teardown.

Ports/base coordinates match the old bootstrap defaults so migrated tests
behave identically.
"""

import os
import time

from harness import LAND_LON, LAND_LAT

HOST_LON, HOST_LAT = 0.35, 0.85

SAVE_EXTS = (".sav", ".asav", ".data")


def states(gc):
    return gc.cmd({"cmd": "get_state"})["states"]


def has_state(gc, name):
    return any(name in s for s in states(gc)) or None


# PRD-13 S7: public names; the underscore forms are kept as aliases for any
# straggler caller and for this module's own internal use below.
_states = states
_has_state = has_state


def new_campaign(host, client, port="47900",
                 host_name="HostPlayer", client_name="ClientPlayer",
                 host_base="HostBase", client_base="ClientBase",
                 campaign_mode="coop"):
    """Bring up a fresh co-op campaign through the redesigned flow.

    campaign_mode selects the New Game dropdown choice: "coop" (SEPARATE,
    the default, unchanged) or "shared" (PRD-J01 SHARED economy).
    """

    # host: New Game -> Co-op -> difficulty OK (world created, HostMenu opens)
    host.ok({"cmd": "open_new_game", "mode": campaign_mode})
    host.wait_for("difficulty", lambda: _has_state(host, "NewGameState"))
    host.ok({"cmd": "newgame_ok"})
    host.wait_for("host window", lambda: _has_state(host, "HostMenu"))

    # host window -> lobby
    host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": port, "player": host_name})
    host.wait_for("host lobby", lambda: _has_state(host, "LobbyMenu"))

    # client joins and lands in the lobby (no ready button). Both machines then
    # show the "player joined" popup over the lobby; dismiss it the way a player
    # would so callers see the lobby as the top state.
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": client_name})
    client.wait_for("client lobby", lambda: _has_state(client, "LobbyMenu"))
    for gc in (host, client):
        gc.wait_for("join popup", lambda gc=gc: _has_state(gc, "Profile"))
        gc.ok({"cmd": "profile_ok"})

    # START CAMPAIGN enabled once the client is in
    host.wait_for(
        "start eligible",
        lambda: host.cmd({"cmd": "lobby_state"}).get("startEligible") or None,
    )
    # Press the REAL START CAMPAIGN button (btnCancelClick), not the
    # lobby_start_campaign shortcut which calls startCampaign() directly and skips
    # btnCancelClick's gating + the confirm dialog. btnCancelClick opens
    # ConfirmStartCampaignState; its OK (clickStartConfirmOk) actually starts.
    host.ok({"cmd": "lobby_action"})
    host.wait_for("start confirm dialog",
                  lambda: _has_state(host, "ConfirmStartCampaignState"))
    host.ok({"cmd": "lobby_confirm_ok"})

    # the host always places its own first base
    host.wait_for("host base placement", lambda: _has_state(host, "BuildNewBaseState"))
    r = host.cmd({"cmd": "place_first_base", "lon": HOST_LON, "lat": HOST_LAT, "name": host_base})
    if not r.get("ok"):
        host.ok({"cmd": "place_first_base", "lon": LAND_LON, "lat": LAND_LAT, "name": host_base})

    if campaign_mode == "shared":
        # PRD-J02: a SHARED client never builds its own world - it waits for the
        # host to stream the authoritative world after the host's base is placed.
        # The host holds in COOP_DLG_WAIT_PLAYERS until the client acks the
        # streamed world loaded, then BEGIN releases both.
        host.wait_for(
            "client world ack",
            lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None,
            timeout=120,
        )
        host.ok({"cmd": "coop_dialog_back"})
    else:
        # SEPARATE: the client places its own base and pushes its world blob;
        # the host waits for that blob, then clicks BEGIN.
        client.wait_for("client base placement", lambda: _has_state(client, "BuildNewBaseState"))
        client.ok({"cmd": "place_first_base", "lon": LAND_LON, "lat": LAND_LAT, "name": client_base})

        host.wait_for(
            "all players placed bases",
            lambda: host.cmd({"cmd": "has_coop_file",
                              "key": f"host_{host.cmd({'cmd': 'save_markers'})['saveID']}_{client_name}.data"}).get("present") or None,
            timeout=120,
        )
        host.ok({"cmd": "coop_dialog_back"})

    # session up: both synced (client holds the streamed / synced world)
    try:
        client.wait_for(
            "session up",
            lambda: (lambda c: (c.get("hasSave") and not _has_state(client, "LobbyMenu")) or None)(client.cmd({"cmd": "get_coop"})),
            timeout=120,
        )
    except TimeoutError:
        print("DEBUG host  get_coop:", host.cmd({"cmd": "get_coop"}))
        print("DEBUG host  states:  ", host.cmd({"cmd": "get_state"})["states"])
        print("DEBUG client get_coop:", client.cmd({"cmd": "get_coop"}))
        print("DEBUG client states: ", client.cmd({"cmd": "get_state"})["states"])
        raise
    print("session up (redesigned flow)")


def resume_campaign(host, client, save_file, port="47900",
                    host_name="HostPlayer", client_name="ClientPlayer"):
    """Resume a co-op campaign save through the redesigned flow: menu load ->
    host window -> resume lobby (gated on the registered roster) -> RESUME ->
    world served -> session up. `host` must be freshly at the main menu with
    the save in its user dir; `client` freshly at the main menu."""

    host.ok({"cmd": "load_save_menu", "file": save_file})
    host.wait_for("host window (resume)", lambda: _has_state(host, "HostMenu"))

    host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": port, "player": host_name})
    host.wait_for("resume lobby", lambda: _has_state(host, "LobbyMenu"))
    ls = host.ok({"cmd": "lobby_state"})
    assert ls["lobbyMode"] == 2, f"expected resume lobby, got {ls}"

    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": client_name})
    client.wait_for("client resume lobby", lambda: _has_state(client, "LobbyMenu"))

    # Press the REAL RESUME button (btnCancelClick), not the lobby_resume_campaign
    # shortcut which calls resumeCampaign() directly and bypasses btnCancelClick's
    # _resumeToGame branch + gates. Wait until the host sees the peer first so the
    # button's missingPlayers()/startEligible() gate is satisfied.
    host.wait_for(
        "client registered in resume lobby",
        lambda: (host.cmd({"cmd": "get_coop"}).get("clientName") == client_name) or None,
        timeout=60, interval=1.0,
    )
    time.sleep(2)
    host.ok({"cmd": "lobby_action"})

    # host holds in the loading dialog until the client acks, then RESUME
    host.wait_for(
        "client world ack",
        lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None,
        timeout=120,
    )
    host.ok({"cmd": "coop_dialog_back"})

    client.wait_for(
        "resume session up",
        lambda: (lambda c: (c.get("hasSave") and not _has_state(client, "LobbyMenu")) or None)(client.cmd({"cmd": "get_coop"})),
        timeout=120,
    )
    print("session resumed (redesigned flow)")


def resume_campaign_battle(host, client, save_file, port="47900",
                           host_name="HostPlayer", client_name="ClientPlayer",
                           timeout=120, interval=2.0):
    """Resume a MID-BATTLE co-op save.

    Like resume_campaign(), but the save carries a battleGame, so this must NOT
    wait on the geoscape-resume `resumeAck` / BEGIN handshake: for a battle-
    eligible client the host's resume_ack handler emits `campaign_resume_battle`
    instead of setting resumeAck (connectionTCP.cpp), and the two-phase battle
    stream (campaign_resume_battle -> SEND_FILE_CLIENT_SAVE ->
    battlehost/battleclient) drives itself. We only drive the lobby up to the
    host accepting the resume, then wait (BOUNDED - never hang) until BOTH
    machines report battle_state.inBattle.

    `host` must be freshly at the main menu with the save in its user dir;
    `client` freshly at the main menu (empty user dir). Raises TimeoutError with
    per-machine battle/state detail if either machine never enters the battle
    within `timeout` (e.g. the SHARED gap where the client is never streamed the
    battle at all)."""

    host.ok({"cmd": "load_save_menu", "file": save_file})
    host.wait_for("host window (battle resume)", lambda: _has_state(host, "HostMenu"))

    host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": port, "player": host_name})
    host.wait_for("resume lobby", lambda: _has_state(host, "LobbyMenu"))
    ls = host.ok({"cmd": "lobby_state"})
    assert ls["lobbyMode"] == 2, f"expected resume lobby, got {ls}"

    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": client_name})
    client.wait_for("client resume lobby", lambda: _has_state(client, "LobbyMenu"))

    # Wait until the client is registered in the host's resume lobby (both roster
    # slots present), THEN press the REAL resume button. We must NOT use
    # lobby_resume_campaign as the readiness probe: that command calls
    # LobbyMenu::resumeCampaign() DIRECTLY, bypassing btnCancelClick and its
    # _resumeToGame branch - the exact code path where the mid-battle-resume bug
    # lives (issue: client stuck on lobby, host plays solo). Press the button the
    # player actually presses instead, so the test exercises that branch.
    host.wait_for(
        "client registered in resume lobby",
        lambda: (host.cmd({"cmd": "get_coop"}).get("clientName") == client_name) or None,
        timeout=60, interval=1.0,
    )
    time.sleep(2)                      # let the roster/registration settle
    host.ok({"cmd": "lobby_action"})   # real RESUME button (btnCancelClick)

    def _in_battle(gc):
        return gc.cmd({"cmd": "battle_state"}).get("inBattle")

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _in_battle(host) and _in_battle(client):
            print("battle resume: BOTH machines report inBattle")
            return
        time.sleep(interval)

    def _detail(gc):
        b = gc.cmd({"cmd": "battle_state"})
        return f"inBattle={b.get('inBattle')} top={states(gc)[-3:]}"

    raise TimeoutError(
        f"battle resume: both machines did not enter the battle within {timeout}s\n"
        f"  host:   {_detail(host)}\n"
        f"  client: {_detail(client)}")


# ---- ending a co-op battle ------------------------------------------------
#
# dismiss_popup closes the popup types it knows about and GENERICALLY pops
# anything else, so "skip all dialogs" stays robust as new popups appear. Two
# states must therefore never be handed to it while a co-op battle is live:
#
#   VoteMenu          - BattlescapeState::btnAbortClick no longer pushes
#                       AbortMissionState in co-op; it opens an abandon-mission
#                       VoteMenu, which dismiss_popup does not recognise.
#   BattlescapeState  - once the VoteMenu above it has been generic-popped, the
#                       battlescape itself is the top state, and the next
#                       dismiss_popup pops the running battle off the stack.
#
# Both are closed by production code (the host's finishBattle pop-loop, the
# client's EndCoopBattle), so the drain below waits them out instead.
NO_DISMISS_STATES = ("VoteMenu", "BattlescapeState")


def drain_to_geoscape(gc, deadline, interval=0.4):
    """dismiss_popup one machine's stack down to the geoscape, never touching a
    state the game itself is still responsible for closing (NO_DISMISS_STATES).

    Returns True once the geoscape is the top state, or None when `deadline`
    (an absolute time.time() value) passes - the shape gc.wait_for() wants.
    """
    while time.time() < deadline:
        st = states(gc)
        top = st[-1] if st else ""
        if "GeoscapeState" in top:
            return True
        if any(name in top for name in NO_DISMISS_STATES):
            time.sleep(interval)  # not ours to pop; the battle is still ending
            continue
        gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(interval)
    return None


def coop_abort_battle(host, client, vote_timeout=25, drain_timeout=200,
                      interval=0.4):
    """End a live co-op battle the only way a player now can: ABORT -> vote ->
    debriefing -> geoscape, on BOTH machines.

    In multiplayer, abandoning a mission takes a strict majority: btnAbortClick
    calls requestVote("abandon_mission", ...) and every machine opens a
    VoteMenu. The host is the starter here, so its seat is an automatic YES and
    the client's YES carries the 2/2 majority; the host then runs
    abortMissionByVote -> finishBattle (which pops its own VoteMenu) and ships
    the debriefing to the client, whose EndCoopBattle does the same. Only then
    is dismiss_popup safe again - DebriefingState is a type it handles.

    Exactly ONE vote is started, so the host's 60-second vote-starter cooldown
    is never reached; a repeated battle_action/abort while a vote is already
    active is absorbed by requestVote (it just re-shows the open menu).

    Raises AssertionError if the vote is not the abandon-mission one or does not
    pass, and TimeoutError (with both machines' top states) if either machine
    never gets back to the geoscape.
    """

    host.ok({"cmd": "battle_action", "action": "abort"})

    def _vote(gc, want):
        return gc.wait_for(
            f"abandon-mission vote {want}",
            lambda: (lambda s: s if (
                s.get(want) and (want != "active" or s.get("menuOpen"))
            ) else None)(gc.ok({"cmd": "vote_state"})),
            timeout=vote_timeout,
            interval=0.25,
        )

    for gc in (host, client):
        v = _vote(gc, "active")
        assert v["action"] == "abandon_mission", \
            f"{gc.name}: ABORT opened the wrong vote: {v}"

    # The starter (the host, seat 0) auto-voted YES when the vote was created,
    # so this single YES is the second of the two a 2-player majority needs.
    cast = client.ok({"cmd": "vote_cast", "yes": True})
    assert cast.get("accepted"), f"client vote_cast was rejected: {cast}"

    for gc in (host, client):
        v = _vote(gc, "finished")
        assert v.get("passed"), \
            f"{gc.name}: the abandon-mission vote did not pass: {v}"

    deadline = time.time() + drain_timeout
    for gc in (host, client):
        try:
            gc.wait_for("back on the geoscape after debriefing",
                        lambda gc=gc: drain_to_geoscape(gc, deadline, interval),
                        timeout=drain_timeout + 20, interval=1.0)
        except TimeoutError:
            raise TimeoutError(
                f"abandon-mission abort: {gc.name} never reached the geoscape "
                f"within {drain_timeout}s\n"
                f"  host:   {states(host)[-3:]}\n"
                f"  client: {states(client)[-3:]}")

    print("abandon-mission vote passed; both machines back on the geoscape")


def save_files(user_dir):
    found = []
    for root, _dirs, files in os.walk(user_dir):
        for f in files:
            if f.lower().endswith(SAVE_EXTS):
                found.append(os.path.relpath(os.path.join(root, f), user_dir))
    return sorted(found)


def assert_client_zero_disk(client_dir):
    files = save_files(client_dir)
    assert files == [], f"CLIENT WROTE SAVE DATA TO DISK: {files}"
