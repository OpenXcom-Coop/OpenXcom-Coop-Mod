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

import glob
import os
import time

from harness import LAND_LON, LAND_LAT, EXE as _GAME_EXE

HOST_LON, HOST_LAT = 0.35, 0.85

SAVE_EXTS = (".sav", ".asav", ".data")


def states(gc):
    # The TestServer socket is available before a large mod has finished loading.
    # During that window get_state legitimately has no state array yet.
    return gc.cmd({"cmd": "get_state"}).get("states", [])


def _wait_stacks_change(machines, seen, cap, interval=0.02):
    """wait until a machine's screen stack differs from `seen` (one states() list per machine), at
    most `cap` seconds (the fixed step it replaces). Returns True on a change, False at the cap."""
    end = time.time() + cap
    while time.time() < end:
        if any(states(gc) != s for gc, s in zip(machines, seen)):
            return True
        time.sleep(interval)
    return False


def has_state(gc, name):
    return any(name in s for s in states(gc)) or None


WIDGET_READY_S = 10.0   # bound of wait_widget_ready (a POPUP window opens in about 20 thinks)


def wait_widget_ready(gc, match, nth=0, timeout=WIDGET_READY_S, interval=0.05):
    """Wait until the TextButton that
    `click_widget {match, nth}` would pick (click_widget's own rule: the nth VISIBLE TextButton of the top state
    whose caption contains `match`, case-insensitive) exists and is NOT hidden. A POPUP window (InterceptState,
    UfopaediaStartState, ...) hides every surface of its state while it opens (Window::think -> State::hideAll), a
    hidden InteractiveSurface drops the click, and click_widget (which checks only getVisible) still answers ok; under
    load the state can also be pushed only after a click aimed at it. A fixed settle before the click loses both races.
    Returns the seconds waited, or None when the button did not show within `timeout` (the caller then clicks as
    before and its own check reports the miss). Read-only: list_widgets only; a probe error counts as not ready."""
    t0, lc = time.time(), match.lower()
    while True:
        try:
            tbs = [w for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", [])
                   if str(w.get("type", "")).endswith("::TextButton") and w.get("visible")
                   and lc in str(w.get("text") or "").lower()]
            if len(tbs) > nth and tbs[nth].get("hidden") is False:
                return round(time.time() - t0, 3)
        except Exception:  # noqa: BLE001 - a busy or dead probe is "not ready"; the bound below still holds
            pass
        if time.time() - t0 >= timeout:
            return None
        time.sleep(interval)


def click_widget_ready(gc, match, nth=0, timeout=WIDGET_READY_S):
    """wait_widget_ready, then click_widget {match, nth} (one click, whatever the wait gave). Returns
    click_widget's reply with `readyS` (wait_widget_ready's result) added."""
    ready = wait_widget_ready(gc, match, nth=nth, timeout=timeout)
    r = dict(gc.cmd({"cmd": "click_widget", "match": match, "nth": nth}))
    r["readyS"] = ready
    return r


def wait_coop_session(gc, timeout=5.0, interval=0.02):
    """wait until `gc`'s get_coop coopSession is true; returns the seconds waited, or None when it stayed false for
    `timeout` (the caller goes on and its own check reports the miss). A host save shows its "Saving..." (CoopState 54) only
    in a live session (SaveGameState's deferral needs isCoopSession()); after a rejoin the host logs sessionLive first and
    sets the flag only when the partner's COOP_READY_CLIENT or the battle handshake's battle_ready lands, so a save sent at once
    writes with no 54."""
    t0 = time.time()
    while True:
        try:
            if gc.cmd({"cmd": "get_coop"}).get("coopSession") is True:
                return round(time.time() - t0, 3)
        except Exception:  # noqa: BLE001 - a busy probe is "not yet"; the bound below still holds
            pass
        if time.time() - t0 >= timeout:
            return None
        time.sleep(interval)


# PRD-13 S7: public names; the underscore forms are kept as aliases for any
# straggler caller and for this module's own internal use below.
_states = states
_has_state = has_state


def can_drive(state):
    """May THIS machine drive a battlescape action? `state` is a battle_state
    (or parallel_state) response dict.

    Classic co-op: only the machine that owns the simulation may drive, and
    `activeSync` (connectionTCP::_isActivePlayerSync) is that flag - every coop
    battle state gates its packet send on it, so an action driven from the
    passive side runs locally and never reaches the peer.

    Parallel turns (PRD-P5+): `activeSync` stops being the driver predicate and
    becomes the EXECUTOR invariant (`_isActivePlayerSync == getHost()`, so host
    true / client false, permanently). A client-side action is forwarded to the
    host as an intent (PRD-P6) rather than executed locally, so BOTH machines
    may drive. `parallelActive` says whether that mode is live.

    `parallelActive` is false until P5 lands, so this is exactly `activeSync`
    today - use it instead of reading `activeSync` directly wherever the
    question is "which machine should I drive this action from".

    NOT for invariant assertions: a test that asserts exactly one machine owns
    the simulation is asking about `activeSync` itself and must keep reading it.
    """
    return bool(state.get("activeSync") or state.get("parallelActive", False))


def start_campaign_via_button(host):
    """Press the REAL START CAMPAIGN button the way a player does: btnCancelClick
    (which opens ConfirmStartCampaignState) then the dialog's OK
    (clickStartConfirmOk). Do NOT use lobby_start_campaign - it calls
    LobbyMenu::startCampaign() directly and skips btnCancelClick's gating + the
    confirm dialog (the same class of bypass that hid the mid-battle-resume bug).
    Host must be an eligible mode-1 lobby (client joined, startEligible)."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("start confirm dialog",
                  lambda: _has_state(host, "ConfirmStartCampaignState"))
    host.ok({"cmd": "lobby_confirm_ok"})


def resume_campaign_via_button(host, client_name="ClientPlayer"):
    """Press the REAL RESUME button (btnCancelClick) on a mode-2 resume lobby,
    after the host sees the peer so the missingPlayers()/startEligible() gate is
    satisfied. Do NOT use lobby_resume_campaign - it calls resumeCampaign()
    directly and bypasses btnCancelClick's _resumeToGame branch."""
    host.wait_for(
        "client registered in resume lobby",
        lambda: (host.cmd({"cmd": "get_coop"}).get("clientName") == client_name) or None,
        timeout=60, interval=0.05,
    )
    # RESUME's own gate (LobbyMenu::btnCancelClick, mode 2: missingPlayers() empty and
    # startEligible() = clientInLobby) instead of a fixed 2 s; at most the old 2 s, then the press as before
    end = time.time() + 2.0
    while time.time() < end and not host.cmd({"cmd": "lobby_state"}).get("startEligible"):
        time.sleep(0.02)
    host.ok({"cmd": "lobby_action"})


def new_campaign(host, client, port="47900",
                 host_name="HostPlayer", client_name="ClientPlayer",
                 host_base="HostBase", client_base="ClientBase",
                 campaign_mode="coop", transport="tcp",
                 host_difficulty=None, client_difficulty=None,
                 host_settle_seconds=2):
    """Bring up a fresh co-op campaign through the redesigned flow.

    campaign_mode selects the New Game dropdown choice: "coop" (SEPARATE,
    the default, unchanged) or "shared" (PRD-J01 SHARED economy).

    transport selects the wire: "tcp" (default, host_tcp/join_tcp) or "udp"
    (host_udp/join_udp - the REAL direct-LAN connectionUDP transport on 127.0.0.1,
    no rendezvous). UDP is opt-in per test: only a repro that needs the UDP
    background threads (e.g. a UDP-only crash) should ask for it. The host binds
    UDP on `port`; the client binds `port`+1 and dials the host.
    """

    # host: New Game -> Co-op -> difficulty OK (world created, HostMenu opens)
    host.ok({"cmd": "open_new_game", "mode": campaign_mode})
    host.wait_for("difficulty", lambda: _has_state(host, "NewGameState"))
    host_newgame = {"cmd": "newgame_ok"}
    if host_difficulty is not None:
        host_newgame["difficulty"] = host_difficulty
    host.ok(host_newgame)
    host.wait_for("host window", lambda: _has_state(host, "HostMenu"))

    # one session key per harness lane. The UDP client also dials its host's port +- a radius (NAT port guessing,
    # connectionUDP::buildCandidates), and lanes on one machine get neighbouring ephemeral ports, so with one shared key
    # a lane's client can authenticate the next lane's host (seen: client :65343 -> host :65342, its own host :65341)
    udp_pw = "harness-lan-s%s" % os.environ.get("OXC_HARNESS_SLOT", "0")
    client_udp_port = str(int(port) + 1)

    # host window -> lobby
    if transport == "udp":
        client_udp_port = str(int(port) + 1)
        host.ok({"cmd": "host_udp", "port": port, "player": host_name,
                 "password": udp_pw, "campaign": True})
    else:
        hosted = host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": port,
                          "player": host_name, "campaign": True})
        # TCP port "0" asks the game to reserve an OS-selected free port.  The
        # TestServer command reports the concrete port so the client can dial
        # that listener instead of the literal zero.
        print(f"[tcp] host listening on :{hosted.get('port', port)}")
        host.wait_for(
            "host TCP listener",
            lambda: (host.cmd({"cmd": "get_coop"}).get("onConnect") == 1) or None,
            timeout=30, interval=0.25,
        )
    host.wait_for("host lobby", lambda: _has_state(host, "LobbyMenu"))

    # The lobby UI can appear one frame before a large mod's host transport has
    # completed its asynchronous startup. Stock data hides this race; give the
    # real socket a brief settling window before the peer dials it.
    time.sleep(host_settle_seconds)

    # client joins and lands in the lobby (no ready button). Both machines then
    # show the "player joined" popup over the lobby; dismiss it the way a player
    # would so callers see the lobby as the top state. The UDP handshake
    # (hole-punch + INIT_SERVER) is async, so the client can take a few seconds
    # longer to surface the lobby than on TCP.
    if transport == "udp":
        client.ok({"cmd": "join_udp", "ip": "127.0.0.1", "port": port,
                   "localport": client_udp_port, "player": client_name,
                   "password": udp_pw, "campaign": True})
    else:
        # Keep the same rendezvous key used by host_tcp. GameClient.cmd maps
        # that key to the concrete ephemeral listener selected by the host.
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port,
                   "player": client_name, "campaign": True})
    try:
        joined = client.wait_for(
            "client lobby",
            lambda: ("lobby" if _has_state(client, "LobbyMenu") else
                     "terminal" if any(name in states(client)
                                       for name in ("ModCheckMenu", "ErrorMessageState")) else None),
            timeout=120)
        if joined != "lobby":
            raise TimeoutError(f"client join stopped in {joined} state")
    except TimeoutError:
        print("DEBUG TCP join host states:", host.cmd({"cmd": "get_state"}))
        print("DEBUG TCP join client states:", client.cmd({"cmd": "get_state"}))
        print("DEBUG TCP join host coop:", host.cmd({"cmd": "get_coop"}))
        print("DEBUG TCP join client coop:", client.cmd({"cmd": "get_coop"}))
        print("DEBUG TCP join client screen:", client.cmd({"cmd": "screen_state"}))
        raise
    for gc in (host, client):
        gc.wait_for("join popup", lambda gc=gc: _has_state(gc, "Profile"))
        gc.ok({"cmd": "profile_ok"})

    # START CAMPAIGN enabled once the client is in
    host.wait_for(
        "start eligible",
        lambda: host.cmd({"cmd": "lobby_state"}).get("startEligible") or None,
    )
    # Press the REAL START CAMPAIGN button + confirm dialog (see helper).
    start_campaign_via_button(host)

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
        press_back_when_shown(host, "host BEGIN", codes=(60, 62))
    else:
        # SEPARATE: the client contributes its first base once. The host merges
        # it into the authoritative world and retains no player-world blob.
        # Mod campaigns may ask the client for its faction/difficulty before
        # base placement. Stock campaigns skip this screen.
        if client_difficulty is not None:
            client.wait_for("client faction selection",
                            lambda: _has_state(client, "NewGameState"))
            client.ok({"cmd": "newgame_ok", "difficulty": client_difficulty})
        client.wait_for("client base placement", lambda: _has_state(client, "BuildNewBaseState"))
        client.ok({"cmd": "place_first_base", "lon": LAND_LON, "lat": LAND_LAT, "name": client_base})

        host.wait_for(
            "all players placed bases",
            lambda: next((b for b in host.cmd({"cmd": "geo_state"}).get("bases", [])
                          if b.get("ownerPlayerName") == client_name), None),
            timeout=120,
        )
        press_back_when_shown(host, "host BEGIN", codes=(60, 62))

        # Popping the one visible base-placement gate lets the host finish
        # month-zero initialization and stream the settled world. The client's
        # adopted-world ack releases its hold automatically. A second host
        # CoopState here is the duplicate wait/"placed" dialog regression.
        host.wait_for(
            "client settled-world ack",
            lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None,
            timeout=120,
        )
        host.wait_for(
            "single Separate wait dialog only",
            lambda: ("GeoscapeState" in _states(host)[-1]
                     if _states(host) else None),
            timeout=30,
        )

    # session up: both synced — client sees the geoscape with no dialogs
    try:
        client.wait_for(
            "session up",
            lambda: "GeoscapeState" in _states(client)[-1]
                    if _states(client) else None,
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

    # Both machines show the "player joined" popup over the lobby, the host's
    # a moment after the join. Until it is closed LobbyMenu does not think, so
    # neither machine receives a populated roster even though TCP is connected.
    # Dismiss it on both, whenever it appears, the way a player would.
    def roster_ready(m):
        for gc in (host, client):
            if _has_state(gc, "Profile"):
                gc.ok({"cmd": "profile_ok"})
        ls = m.cmd({"cmd": "lobby_state"})
        return ls if (ls.get("hostRowName", "").strip()
                      and ls.get("clientRowName", "").strip()) else None

    for machine, who in ((host, "host"), (client, "client")):
        machine.wait_for(
            f"{who} resume lobby roster",
            lambda m=machine: roster_ready(m),
            timeout=30,
        )
        roster = machine.ok({"cmd": "lobby_state"})
        # Different-faction Separate lobbies append " (Faction)" to the
        # displayed row. Resume identity still compares the locked player name.
        row_player = lambda value: value.strip().split(" (", 1)[0]
        assert row_player(roster["hostRowName"]) == host_name, roster
        assert row_player(roster["clientRowName"]) == client_name, roster

    # Press the REAL RESUME button (see helper) instead of the direct-call shortcut.
    resume_campaign_via_button(host, client_name)

    # host holds in the loading dialog until the client acks, then RESUME
    host.wait_for(
        "client world ack",
        lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None,
        timeout=120,
    )
    press_back_when_shown(host, "host RESUME", codes=(60, 62))

    client.wait_for(
        "resume session up",
        lambda: "GeoscapeState" in _states(client)[-1]
                if _states(client) else None,
        timeout=120,
    )
    print("session resumed (redesigned flow)")


def resume_campaign_battle(host, client, save_file, port="47900",
                           host_name="HostPlayer", client_name="ClientPlayer",
                           timeout=120, interval=2.0):
    """Resume a MID-BATTLE co-op save.

    Like resume_campaign(), but the save carries a battleGame, so this must NOT
    wait on the geoscape-resume `resumeAck` / BEGIN handshake: for a battle-
    eligible client the host's resume_ack handler (connectionTCP.cpp) calls
    `CoopHandshake::offerResumedBattle()` - the disk-resume sibling of
    `offerRejoinBattle()` - which mints a fresh
    battleId, rebuilds the authority/seat store from the loaded battle, and
    emits `battle_offer{resumed:true}` through the SAME accept/blob/
    `battle_ready` pipe a fresh join uses. The client loads it, both hash-
    check it, and the host's own COOP_DLG_WAIT_PLAYERS modal - already on its
    stack from the resume lobby - is what the caller presses (`coop_dialog_
    back`) afterwards to land both machines on BattlescapeState; this
    helper does not press it. We only drive the lobby up to the host accepting
    the resume, then wait (BOUNDED - never hang) until BOTH machines report
    battle_state.inBattle.

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

    # The join notification Profile can cover either lobby. LobbyMenu cannot
    # update its visible roster until that state closes.
    for machine in (host, client):
        if _has_state(machine, "Profile"):
            machine.ok({"cmd": "profile_ok"})

    for machine, who in ((host, "host"), (client, "client")):
        machine.wait_for(
            f"{who} battle-resume lobby roster",
            lambda m=machine: (
                m.cmd({"cmd": "lobby_state"})
                if (m.cmd({"cmd": "lobby_state"}).get("hostRowName", "").strip()
                    and m.cmd({"cmd": "lobby_state"}).get("clientRowName", "").strip())
                else None
            ),
            timeout=30,
        )
        roster = machine.ok({"cmd": "lobby_state"})
        def lobby_name_matches(row, player):
            row = row.strip()
            return row == player or row.startswith(player + " (")

        assert lobby_name_matches(roster["hostRowName"], host_name), roster
        assert lobby_name_matches(roster["clientRowName"], client_name), roster

    # Press the REAL resume button (btnCancelClick). This is the branch where the
    # mid-battle-resume bug lived - the direct lobby_resume_campaign shortcut skips
    # it. See resume_campaign_via_button.
    resume_campaign_via_button(host, client_name)

    def _in_battle(gc):
        return gc.cmd({"cmd": "battle_state"}).get("inBattle")

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _in_battle(host) and _in_battle(client):
            time.sleep(1.0)
            for machine, who in ((host, "host"), (client, "client")):
                stack = states(machine)
                unexpected = [s for s in stack
                              if "BriefingState" in s or "InventoryState" in s]
                if unexpected:
                    raise AssertionError(
                        f"{who} reopened pre-battle UI while resuming a saved "
                        f"battle: {stack}")
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


# ---- PRD-P2: the battlescape drift terms -----------------------------------

def battle_checksum(gc):
    """One machine's three battle drift terms, read off `battle_state`.

    Returns (itemIdCounter, battleCensus, battleUnitsChecksum) - exactly what
    SharedEcon stamps on the per-turn `next_turn` packet as chkBattleItemId /
    chkBattleCensus / chkBattleUnits:

      itemIdCounter  SavedBattleGame::_itemId, the next id this machine will mint.
                     EVERY `new BattleItem` advances it, so a mint that happens on
                     one machine only shows up here immediately.
      battleCensus   an order-independent sum over getItems() of the item identity
                     the wire protocol matches on (id + type + owner unit id).
      battleUnits    the same shape over getUnits(): id + faction + LIVENESS
                     (on its feet / dead / unconscious - not the raw animation
                     status, which legitimately differs frame to frame) +
                     position. Deliberately carries no TU, energy, health, stun,
                     wounds, morale or mana; see SharedEcon::battleChecksumTerms
                     for why each of those would be a permanent red rather than a
                     detector.

    All three are -1 when no battle is live.
    """
    b = gc.cmd({"cmd": "battle_state"})
    for key in ("itemIdCounter", "battleCensus", "battleUnitsChecksum"):
        assert key in b, (
            f"battle_state carries no {key!r} - PRD-P2's harness exposure is "
            f"missing, so this assertion would be vacuous: {sorted(b)}")
    return b["itemIdCounter"], b["battleCensus"], b["battleUnitsChecksum"]


def assert_battle_synced(host, client, what=""):
    """PRD-P2's invariant: after every replicated action the two machines hold the
    same item-id counter and the same item census.

    This is the harness-side reading of the terms the in-game tripwire compares on
    `next_turn` - direct, so a test can check it after a single action instead of
    waiting for a turn to roll over. Returns the (agreed) triple.

    The UNIT term is READ and REPORTED here, never asserted, and the difference is
    deliberate rather than timid:

    * The two ITEM terms are permanent facts. An id minted on one machine only, or
      an item that exists on one machine only, never heals - so wherever a test
      calls this, an inequality is a bug.
    * The UNIT term is a SETTLING quantity. It hashes where every unit is and
      whether it is down, and the peer is a display that lags the executor by
      whatever is still in flight. Worse, some of its inputs differ LEGITIMATELY
      for a whole side: `test_coop_outcome_gaps` documents (and deliberately does
      not assert) a spawned unit sitting a z-level apart after a blast, because
      gravity follows host-authoritative terrain destruction and `next_turn` is
      what repairs it.

    So the unit term is asserted where it IS an invariant - by the in-game tripwire
    at the turn boundary (SharedEcon::verifyBattleChecksum, which also skips itself
    when the receive pump applied that stamp out of order), and by
    test_parallel_soak's own per-unit census, which is taken only after both
    machines are provably quiescent. Here it is a signal, printed with the term
    named so a failure elsewhere has a breadcrumb.
    """
    h = battle_checksum(host)
    c = battle_checksum(client)
    tag = f" {what}" if what else ""
    assert h[0] >= 0 and c[0] >= 0, (
        f"battle drift terms{tag}: no live battle to compare "
        f"(host={h}, client={c})")
    assert h[:2] == c[:2], (
        f"BATTLE DRIFT{tag}: the two machines no longer agree.\n"
        f"    itemIdCounter host={h[0]} client={c[0]}"
        f"{'  <-- an item was minted on one machine only' if h[0] != c[0] else ''}\n"
        f"    battleCensus  host={h[1]} client={c[1]}"
        f"{'  <-- the (id, type, owner) item sets differ' if h[1] != c[1] else ''}\n"
        f"    battleUnits   host={h[2]} client={c[2]}\n"
        f"  `battle_items` / `battle_state` units on both machines shows which.")
    if h[2] != c[2]:
        print(f"    NOTE{tag}: battleUnits differs (host={h[2]} client={c[2]}) - a "
              f"unit is in a different place, faction or liveness state. Reported, "
              f"not asserted; see assert_battle_synced.__doc__.")
    return h


# ---- PRD-I0: the per-action sync-check -------------------------------------

def sync_check(gc):
    """One machine's PRD-I0 `syncCheck` block, read off `battle_state`.

    Keys: lastSeq / lastComparedSeq (the ACTION namespace, which restarts at 0 at
    every side boundary), lastBoundarySeq / lastComparedBoundarySeq (the boundary
    pseudo-seq namespace, monotonic for the whole battle), ringDepth, compares,
    staleReports, dropped, sweepUs, buckets {name: {alarm, mismatchCount}} and the
    last 32 mismatches as {seq, boundary, kind, bucket}.

    Only the EXECUTOR compares (the client ships hashes on `action_done` and the
    host looks them up in its ring), so on a client every counter here stays 0.

    OPT-IN on the wire (`"sync": true`): the block costs a full-map hash sweep,
    and `battle_state` is the harness' hot poll. Without the flag the response is
    byte-for-byte what it was before PRD-I0.
    """
    b = gc.cmd({"cmd": "battle_state", "sync": True})
    sc = b.get("syncCheck")
    assert sc is not None, (
        f"battle_state carries no 'syncCheck' - PRD-I0's introspection is missing, "
        f"so this assertion would be vacuous: {sorted(b)}")
    return sc


def sync_buckets(gc):
    """This machine's RAW bucket values right now (`battle_state.battleHashes`).

    The deferred comparison is what the game does; this is what a test uses to
    prove a test command moved the bucket it was supposed to move, without waiting a
    round trip for a report that may never come."""
    b = gc.cmd({"cmd": "battle_state", "sync": True})
    h = b.get("battleHashes")
    assert h is not None, (
        f"battle_state carries no 'battleHashes' - PRD-I0's bucket sweep is not "
        f"exposed: {sorted(b)}")
    return h


def wait_sync_loop_closed(host, timeout=20, interval=0.2):
    """Block until the EXECUTOR's per-action sync-check loop has caught up: every
    action seq (and boundary seq) it recorded has been answered by the peer.

    Why a harness helper for this: the sync-check samples the client's per-action
    hash LATE - at the moment the client consumes that chain's gated `action_end`
    marker (coopEmitActionDone), which lags the executor by whatever display is
    still in flight. A harness test command that mints an item OUT OF BAND (battle_give is
    an immediate TestServer RPC, NOT a chain that flows through the marker pipeline)
    bumps BOTH machines' `_itemId`, but if the client still has an earlier chain's
    marker parked, that earlier chain's DEFERRED sample now reads the post-give
    counter while the executor's ring snapshot for the same seq was taken pre-give -
    a transient items/itemIdCtr divergence with no product cause (the ids the give
    minted are identical on both machines; only the sample INSTANTS straddle the
    mint). Draining the loop before the give closes that straddle: with no parked
    marker, the give cannot bleed into a prior chain's report.

    Bounded and BEST-EFFORT: returns True if the loop closed, False on timeout (the
    caller proceeds either way - a persistent open loop is a real fault the later
    assert_sync_clean will catch, this only waits out the transient). Tolerant of a
    machine with no live sync ring (classic mode, pre-battle): returns True at once.
    """
    deadline = time.time() + timeout
    while True:
        try:
            sc = sync_check(host)
        except Exception:
            return True  # no live sync ring to wait on
        if (sc["lastComparedSeq"] >= sc["lastSeq"]
                and sc["lastComparedBoundarySeq"] >= sc["lastBoundarySeq"]):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(interval)


def assert_sync_clean(host, client, what="", strict=False, allow=(), timeout=30,
                      interval=0.5, quiet=False, latch_aware=False):
    """PRD-I0's invariant, read off the EXECUTOR: every action seq the host
    recorded has been answered by the peer, and no bucket disagreed.

    Two halves, and the difference between them is the whole onboarding
    programme:

    * THE LOOP CLOSES. `lastComparedSeq` must catch `lastSeq` (and the boundary
      pair likewise), `dropped` must stay 0, and the ring must not have run away.
      This is asserted unconditionally - it says the detector is alive. A silent
      detector is worse than no detector, and the only way to tell the two apart
      is to watch the reports come back.
    * THE BUCKETS AGREE. Asserted for every bucket the build has PROMOTED to
      ALARM (`buckets[name].alarm`), and only reported for the rest. At I0 birth
      every bucket is report-only (SharedEcon.cpp BATTLE_HASH_ALARM says why), so
      by default this prints the counts and asserts nothing about them. Pass
      strict=True where the caller genuinely expects a clean battle - which is
      exactly the burn-in evidence PRD-I3 promotes a bucket on - and name the
      buckets that are NOT clean yet in `allow`, so the exception is written down
      instead of hidden behind a blanket non-strict call.

    `client` is accepted (and its own block sanity-checked) so callers read as the
    cross-machine assertion they are, and so a future two-way comparison does not
    change every call site.
    """
    tag = f" {what}" if what else ""
    peer = sync_check(client)
    assert peer["compares"] == 0, (
        f"the CLIENT compared {peer['compares']} report(s){tag} - only the executor "
        f"holds a ring, so a client that compares is comparing against nothing")

    def closed(sc):
        return (sc["lastComparedSeq"] >= sc["lastSeq"]
                and sc["lastComparedBoundarySeq"] >= sc["lastBoundarySeq"])

    sc = sync_check(host)
    deadline = time.time() + timeout
    while not closed(sc) and time.time() < deadline:
        time.sleep(interval)
        sc = sync_check(host)

    assert closed(sc), (
        f"SYNC-CHECK LOOP OPEN{tag}: the host recorded up to action seq "
        f"{sc['lastSeq']} / boundary seq {sc['lastBoundarySeq']} but the peer has "
        f"only answered {sc['lastComparedSeq']} / {sc['lastComparedBoundarySeq']} "
        f"after {timeout}s. The peer has stopped attaching hashes to its "
        f"`action_done` reports, so every bucket assertion below is vacuous. "
        f"ringDepth={sc['ringDepth']} compares={sc['compares']} "
        f"stale={sc['staleReports']} dropped={sc['dropped']}")
    assert sc["dropped"] == 0, (
        f"SYNC-CHECK RING OVERFLOW{tag}: {sc['dropped']} uncompared entries were "
        f"evicted (ring is 64 deep, the display backlog cap is 2) - the peer is "
        f"not reporting: {sc}")

    buckets = sc["buckets"]
    bad = {n: b["mismatchCount"] for n, b in buckets.items() if b["mismatchCount"]}
    if latch_aware:
        # coop (harness alignment, owner ruling 2026-08-30): in the wire-order/latch-aware
        # path the persistence latch (Increment 8 + the alarm-unmask) is the detector of
        # record - a boundary bucket mismatch PENDS on first sight and only promotes to an
        # alarm on persistence. So here the alarm condition is the LATCH state (desyncSeen OR
        # syncBoundaryPersistAlarms>0), NOT the lifetime cumulative `mismatchCount`
        # (g_syncBucketMismatches, SharedEcon.cpp:6569, increment-only), which flags every
        # pend-and-heal transient forever. The cumulative alarm-bucket counts and any still-
        # pending latch entries are REPORTED for diagnostics, never asserted. Classic/wire-order-off
        # callers keep the cumulative semantics below untouched (other suites depend on them).
        ps = host.cmd({"cmd": "parallel_state"})
        persist_alarms = int(ps.get("syncBoundaryPersistAlarms") or 0)
        pending = int(ps.get("syncBoundaryPending") or 0)
        # desyncSeen is published by event_state only (battle_state has no
        # such key); a missing key fails, never passes.
        desync = host.cmd({"cmd": "event_state"}).get("desyncSeen")
        alarmed = {n: c for n, c in bad.items() if buckets[n]["alarm"]}
        if (alarmed or pending) and not quiet:
            print(f"    NOTE{tag}: latch-aware sync-clean (report-only) - cumulative "
                  f"alarm-bucket mismatches {alarmed}; still-pending latch entries={pending}; "
                  f"persistAlarms={persist_alarms} desyncSeen={desync}\n"
                  f"    {_sync_mismatch_lines(sc)}")
        assert desync is False and not persist_alarms > 0, (
            f"SYNC-CHECK ALARM{tag} (latch): the persistence latch promoted a boundary "
            f"divergence - host event_state.desyncSeen={desync!r} syncBoundaryPersistAlarms={persist_alarms} "
            f"(cumulative alarm-bucket mismatches {alarmed}, still-pending {pending}).\n"
            f"    {_sync_mismatch_lines(sc)}")
        return sc
    alarmed = {n: c for n, c in bad.items() if buckets[n]["alarm"]}
    assert not alarmed, (
        f"SYNC-CHECK ALARM{tag}: promoted bucket(s) {alarmed} disagreed.\n"
        f"    {_sync_mismatch_lines(sc)}")
    if strict:
        hard = {n: c for n, c in bad.items() if n not in allow}
        assert not hard, (
            f"SYNC-CHECK MISMATCH{tag}: bucket(s) {hard} disagreed (strict, "
            f"allowing {list(allow)}).\n    {_sync_mismatch_lines(sc)}")
        if bad and not quiet:
            print(f"    NOTE{tag}: allowed report-only buckets differ: "
                  f"{ {n: c for n, c in bad.items() if n in allow} }")
    elif bad and not quiet:
        print(f"    NOTE{tag}: report-only sync-check buckets differ: {bad}\n"
              f"    {_sync_mismatch_lines(sc)}")
    return sc


def _sync_mismatch_lines(sc, limit=6):
    ms = sc.get("mismatches", [])
    if not ms:
        return "(no per-seq detail retained)"
    out = [f"seq={m['seq']}{' boundary' if m.get('boundary') else ''} "
           f"kind={m['kind']} bucket={m['bucket']}" for m in ms[-limit:]]
    return "\n    ".join(out)


# ---- ending a co-op battle ------------------------------------------------
#
# dismiss_popup closes the popup types it knows about and GENERICALLY pops
# anything else, so "skip all dialogs" stays robust as new popups appear. Two
# states must therefore never be handed to it while a co-op battle is live:
#
#   VoteMenu          - an AbortMissionState OK opens the abandon-mission
#                       VoteMenu on both machines; dismiss_popup refuses
#                       it: answer it with vote_cast / click_widget.
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


def abort_vote_yes(host, voter, timeout=20):
    """The partner's YES on the abort vote an AbortMissionState OK opened: wait
    the vote open on `voter`, vote_cast {id, yes: true} (accepted), wait the host's pass: its vote finished + passed,
    its abortVote.passes grown, or its stage / battleEnd record newly emitted with aborted true (the host drops the
    vote once the battle ended, and a stage hand-off's initBattleAuthority clears the abortVote record).
    One `timeout` for both waits.
    Raises TimeoutError("the partner's abort vote never opened ...") / AssertionError; a row appends str(e)."""
    t0, v = time.time(), {}
    while time.time() - t0 < timeout:
        v = voter.cmd({"cmd": "vote_state"})
        if v.get("active") and v.get("action") == "abandon_mission" and v.get("menuOpen"):
            break
        time.sleep(0.1)
    else:
        raise TimeoutError(f"the partner's abort vote never opened within {timeout}s ({voter.name} vote_state active="
                           f"{v.get('active')} action={v.get('action')!r}; host top {(states(host) or ['?'])[-1]})")
    e0 = event_state(host)
    passes0 = (e0.get("abortVote") or {}).get("passes") or 0
    stage0, end0 = ((e0.get("stage") or {}).get("emitted") or 0), ((e0.get("battleEnd") or {}).get("emitted") or 0)
    r = voter.cmd({"cmd": "vote_cast", "id": v.get("id"), "yes": True})
    if not r.get("accepted"):
        raise AssertionError(f"the partner's abort YES was not accepted: {r}")
    while time.time() - t0 < timeout:
        h, e = host.cmd({"cmd": "vote_state"}), event_state(host)
        a, st, be = e.get("abortVote") or {}, e.get("stage") or {}, e.get("battleEnd") or {}
        if ((h.get("finished") and h.get("passed")) or (a.get("passes") or 0) > passes0
                or ((st.get("emitted") or 0) > stage0 and st.get("aborted") is True)
                or ((be.get("emitted") or 0) > end0 and be.get("aborted") is True)):
            return {"voteId": v.get("id"), "secs": round(time.time() - t0, 2)}
        time.sleep(0.1)
    raise TimeoutError(f"the host's abort vote did not pass within {timeout}s of the partner's YES")


def coop_abort_battle(host, client, expect_both=True, drain_timeout=200,
                      interval=0.4):
    """End a live co-op battle through the unanimous abort vote: the host's btnAbortClick pushes the vanilla
    AbortMissionState, its OK (dismiss_popup -> AbortMissionState::btnOkClick)
    opens the unanimous abort vote with the host's YES counted, and the
    partner's YES (abort_vote_yes) passes it; the host then runs vanilla's
    setAborted() + finishBattle() -> DebriefingState -> geoscape.

    finishBattle is battle-wide and host-authoritative:
    in a SHARED battle it returns BOTH machines to the geoscape; in a SEPARATE
    battle it returns only the HOST (the client leaves through its own
    display-only debriefing from the host's `debrief_result`, which this helper
    does not drive; call with expect_both=False).

    Raises AssertionError if the host's confirm was not AbortMissionState or
    the partner's YES was refused, and TimeoutError if the vote never opened or
    passed, or (with both machines' top states) if an EXPECTED machine never
    reaches the geoscape.
    """
    host.ok({"cmd": "battle_action", "action": "abort"})
    host.wait_for("host abort confirm dialog (AbortMissionState)",
                  lambda: has_state(host, "AbortMissionState") or None,
                  timeout=30, interval=0.25)
    r = host.cmd({"cmd": "dismiss_popup"})
    assert r.get("handled") == "AbortMissionState", \
        f"host abort confirm was not AbortMissionState::btnOkClick: {r}"
    abort_vote_yes(host, client)  # the OK opened the vote; the partner's YES passes it

    deadline = time.time() + drain_timeout
    machines = ((host, "host"), (client, "client")) if expect_both else ((host, "host"),)
    for gc, name in machines:
        try:
            gc.wait_for("back on the geoscape after debriefing",
                        lambda gc=gc: drain_to_geoscape(gc, deadline, interval),
                        timeout=drain_timeout + 20, interval=1.0)
        except TimeoutError:
            raise TimeoutError(
                f"host-authoritative abort: {name} never reached the geoscape "
                f"within {drain_timeout}s\n"
                f"  host:   {states(host)[-3:]}\n"
                f"  client: {states(client)[-3:]}")

    print("host-authoritative abort: %s back on the geoscape"
          % ("both machines" if expect_both else "host (the client leaves through its own debriefing)"))


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


# ===== event pump and hash helpers. `assert_sync_clean` above (and
# `sync_check`/`sync_buckets`/`wait_sync_loop_closed`/`battle_checksum`/
# `assert_battle_synced`) read the older parallel-turns
# `parallel_state`/`sync_check` commands. The two helpers below read the
# event pump's TestServer commands (event_log/event_state/hash_now).

def assert_events(gc, kinds):
    """Assert `gc`'s event_log (CoopEventLog, BattlePump.h) tail contains at
    least one entry of each kind in `kinds`, in some order - NOT a strict
    ordering/count assertion, just "did this event actually get logged" for a
    repro that just drove an action. Returns the raw event_log entries list
    (oldest-first) so a caller that DOES care about order/count can inspect it
    further.
    """
    log = gc.cmd({"cmd": "event_log", "tail": 200})
    assert log.get("ok"), f"event_log failed: {log}"
    events = log.get("events", [])
    seen = {e.get("kind") for e in events}
    missing = [k for k in kinds if k not in seen]
    assert not missing, (
        f"event_log missing kind(s) {missing} - saw {sorted(seen)} "
        f"({len(events)} entries): {events}")
    return events


def assert_hash_clean(host, client, buckets=None, full=False, what=""):
    """The hash check of the one-way compare model: the host ships h in evs,
    the CLIENT hashes after applying and compares, the host never compares.
    Unlike assert_sync_clean (above),
    there is no host-side ring to poll for a compare-catches-up loop - this is
    a direct, synchronous `hash_now` snapshot on BOTH machines, bucket-for-
    bucket equal. Correct for a t=0 (pre-first-event) call, a boundary
    sweep; a caller comparing AFTER live actions have run
    is responsible for its own settle/quiescence wait first (e.g.
    `event_state.queueDepth == 0` on both machines) - this helper does not
    wait on anything itself.

    `buckets`: explicit bucket-name list (matches `hash_now`'s own "buckets"
    field); ignored when `full=True` (every SharedEcon.BATTLE_HASH_BUCKETS
    name plus "saveBlob"). Returns (host_h, client_h) so a caller wants to
    print/log the raw per-bucket hex can do so.
    """
    tag = f" {what}" if what else ""
    req = {"cmd": "hash_now", "full": full}
    if buckets is not None:
        req["buckets"] = list(buckets)

    hr = host.cmd(req)
    cr = client.cmd(req)
    assert hr.get("ok"), f"hash_now failed on host{tag}: {hr}"
    assert cr.get("ok"), f"hash_now failed on client{tag}: {cr}"

    hh = hr.get("h", {})
    ch = cr.get("h", {})
    assert hh, f"hash_now returned an empty 'h' object on host{tag} (no live battle?): {hr}"
    assert set(hh.keys()) == set(ch.keys()), (
        f"hash_now bucket SETS differ{tag}: host={sorted(hh.keys())} "
        f"client={sorted(ch.keys())}")

    mismatched = {k: (hh[k], ch[k]) for k in hh if hh[k] != ch[k]}
    assert not mismatched, (
        f"HASH MISMATCH{tag}: {len(mismatched)}/{len(hh)} bucket(s) differ - "
        f"{mismatched}\n  host:   {hh}\n  client: {ch}")

    return hh, ch


# deterministic placement helpers. Faction/seat/tilepart
# constants are declared locally rather than imported - every repro in this
# tree (repro_atom_walk.py, ...) already re-declares its
# own copies rather than session.py exporting a shared set, so this follows
# the existing convention instead of inventing a new one.
_FACTION_PLAYER = 0
_COOP_SEAT_1 = 1
_O_WESTWALL = 1
_O_NORTHWALL = 2

# dir 0 = north, clockwise (repro_atom_walk.py's own
# DIR_DX/DIR_DY tables): (dx, dy) -> dir.
_DIR_FROM_DELTA = {
    (0, -1): 0, (1, -1): 1, (1, 0): 2, (1, 1): 3,
    (0, 1): 4, (-1, 1): 5, (-1, 0): 6, (-1, -1): 7,
}

# The corner<->geometry mapping - TestServer.cpp's own
# battle_teleport_all comment states the same convention - NW=(low x,low y),
# NE=(high x,low y), SW=(low x,high y), SE=(high x,high y). "Facing the map
# edge" means facing further INTO that same corner, i.e. away
# from the map's centre and away from the door.
_CORNER_FACING = {"NW": 7, "NE": 1, "SW": 5, "SE": 3}


def place_deterministic(host, client, moves, what=""):
    """applies the SAME sequence of placement test commands
    (`battle_teleport_unit` / `battle_teleport_all`) to BOTH machines, in the
    same order, with identical arguments - never any coop wire traffic
    (the harness sends each machine's command independently)
    - then asserts `hash_now{full:true}` ALL buckets EQUAL: the gate every
    deterministic-placement fixture must pass before the action it tests.

    `moves`: a list of dicts, each `{"cmd": "battle_teleport_unit"|
    "battle_teleport_all", **params}` - `params` match that command's own JSON
    fields exactly (TestServer.cpp). Raises if either machine's command
    errors, if the two machines' replies for one move DIFFER (both machines
    must move the same units with identical replies - dict equality
    is the right comparison here, since these are JSON objects, not an
    ordering promise), or if the post-placement hash comparison mismatches.
    Returns the list of (host_reply, client_reply) pairs, one per move.
    """
    tag = f" {what}" if what else ""
    results = []
    for i, move in enumerate(moves):
        move = dict(move)
        command = move.pop("cmd")
        req = {"cmd": command, **move}
        # CLIENT first, then HOST. The host's per-tick
        # reveal flush stamps `h` from host state, so a host-first call would let
        # it ship an ev the client could not match yet.
        cr = client.cmd(req)
        hr = host.cmd(req)
        assert hr.get("ok"), f"place_deterministic{tag}: move {i} ({command}) failed on host: {hr}"
        assert cr.get("ok"), f"place_deterministic{tag}: move {i} ({command}) failed on client: {cr}"
        assert hr == cr, (
            f"place_deterministic{tag}: move {i} ({command}) replies differ between "
            f"host and client - host={hr} client={cr}")
        results.append((hr, cr))
        wait_seq_barrier(host, client)
    assert_hash_clean(host, client, full=True, what=f"place_deterministic{tag}")
    return results


def _tile_standable(gc, pos):
    """Conservative READ-ONLY proxy for the placement command's own
    standability predicate (Tile.cpp:289/:300/:319 via `tile_info`, the same
    floor-presence check `tile_walkable()` below uses) - used here
    only to CHOOSE which side of a door to stand on before calling the
    command; the command itself is the real judge and refuses (changing nothing)
    if this proxy ever disagrees."""
    ti = gc.cmd({"cmd": "tile_info", "x": pos[0], "y": pos[1], "z": pos[2]})
    if not ti.get("ok"):
        return False
    return ti.get("parts", {}).get("floor", {}).get("mapDataID", -1) >= 0


def contact_free_ufo_door_setup(host, client, door_pick_rule=None, what="",
                                 actor_id=None, teleport_hostiles=True):
    """builds a CONTACT-FREE UFO-door crossing SITUATION
    deterministically via `place_deterministic`, instead of searching a
    freshly generated map for one and re-rolling. Call once the battle
    is Active on both machines (after the usual bring-up +
    `dismiss_battle_start_overlays`/`dismiss_client_briefing`).

    WHY `actor_id`/`teleport_hostiles` exist: the
    door-reserve-fairness repro needs TWO deterministically-staged crossings
    in the SAME battle, one per leg - a client-origin crossing and a
    host-origin control - and this helper's own "lowest live seat-1 soldier"
    rule would otherwise hand BOTH callers the identical actor. `actor_id`
    lets a SECOND call pick a DIFFERENT soldier; `teleport_hostiles=False`
    lets that second call skip re-doing the (idempotent but redundant)
    `battle_teleport_all` the FIRST call already did in this battle.

    1. Picks a CLOSED UFO door via `find_doors` (the same TestServer command
       `find_doors()` below wraps), filtered to `isUfoDoor` and not
       `isUfoDoorOpen`, in `find_doors`' own linear tile-index order
       (deterministic). `door_pick_rule(doors)` may override the SELECTION
       from that filtered list (default: the first).
    2. `battle_teleport_all {faction:"hostile", corner:<farthest from the
       door>, facing:<into that corner>}` - moves every live hostile out of
       contact range on BOTH machines (instead of killing all but one).
       SKIPPED when `teleport_hostiles=False`
       (the caller already cleared hostiles earlier in this same battle).
    3. `battle_teleport_unit` - moves ONE live seat-1 soldier onto the
       standable tile in front of the door, facing it: the LOWEST live
       seat-1 id by default, or the given `actor_id` (asserted live, seat-1,
       and present on BOTH machines) when provided.
    4. `place_deterministic`'s own hash-equality gate (all buckets EQUAL).
    5. Returns the `(actor_id, near, far, door)` crossing descriptor.

    Raises `AssertionError` (prefixed `FIXTURE:` where the cause is "this
    generated map cannot supply the situation", never a coop-atom failure)
    if there is no closed UFO door, no live seat-1 soldier (or the requested
    `actor_id` is not one, on EITHER machine), or neither side of the chosen
    door looks standable - the caller re-picks (a fresh bring-up / a
    different door_pick_rule), the same re-roll rule the other battle
    fixtures use. The defaults (`actor_id=None, teleport_hostiles=True`)
    stage one crossing with the lowest live seat-1 soldier.
    """
    tag = f" {what}" if what else ""
    doors_resp = host.cmd({"cmd": "find_doors", "limit": 512, "ufoOnly": True})
    assert doors_resp.get("ok"), f"contact_free_ufo_door_setup{tag}: find_doors failed on host: {doors_resp}"
    closed = [d for d in doors_resp.get("doors", []) if not d.get("isUfoDoorOpen")]
    assert closed, f"FIXTURE: contact_free_ufo_door_setup{tag}: no closed UFO door on this map"
    door = (door_pick_rule or (lambda ds: ds[0]))(closed)

    mx = doors_resp["mapSizeX"]
    my = doors_resp["mapSizeY"]

    if door["part"] == _O_WESTWALL:
        side_a = (door["x"], door["y"], door["z"])
        side_b = (door["x"] - 1, door["y"], door["z"])
    elif door["part"] == _O_NORTHWALL:
        side_a = (door["x"], door["y"], door["z"])
        side_b = (door["x"], door["y"] - 1, door["z"])
    else:
        raise AssertionError(
            f"FIXTURE: contact_free_ufo_door_setup{tag}: door part {door['part']} "
            "is not a wall part (floor/object doors are not walk-through)")

    vert = "S" if door["y"] < my / 2.0 else "N"
    horiz = "E" if door["x"] < mx / 2.0 else "W"
    corner = vert + horiz
    alien_facing = _CORNER_FACING[corner]

    hs = host.cmd({"cmd": "battle_state"})
    assert hs.get("ok") and hs.get("inBattle"), (
        f"contact_free_ufo_door_setup{tag}: battle_state unusable on host: {hs}")
    seat1 = sorted(
        u["id"] for u in hs.get("units", [])
        if u.get("faction") == _FACTION_PLAYER and not u.get("isOut")
        and u.get("coop") == _COOP_SEAT_1)
    assert seat1, f"FIXTURE: contact_free_ufo_door_setup{tag}: no live seat-1 soldier"
    if actor_id is None:
        actor_id = seat1[0]
    else:
        assert actor_id in seat1, (
            f"FIXTURE: contact_free_ufo_door_setup{tag}: requested actor_id "
            f"{actor_id} is not a live seat-1 soldier on the host (live seat-1: "
            f"{seat1})")
        cs = client.cmd({"cmd": "battle_state"})
        assert cs.get("ok") and cs.get("inBattle"), (
            f"contact_free_ufo_door_setup{tag}: battle_state unusable on client: {cs}")
        cseat1 = {u["id"] for u in cs.get("units", [])
                  if u.get("faction") == _FACTION_PLAYER and not u.get("isOut")
                  and u.get("coop") == _COOP_SEAT_1}
        assert actor_id in cseat1, (
            f"FIXTURE: contact_free_ufo_door_setup{tag}: requested actor_id "
            f"{actor_id} is not a live seat-1 soldier on the CLIENT")

    if _tile_standable(host, side_a):
        near, far = side_a, side_b
    elif _tile_standable(host, side_b):
        near, far = side_b, side_a
    else:
        raise AssertionError(
            f"FIXTURE: contact_free_ufo_door_setup{tag}: neither side of door "
            f"{door} looks standable (tile_info proxy)")

    dx = (far[0] > near[0]) - (far[0] < near[0])
    dy = (far[1] > near[1]) - (far[1] < near[1])
    soldier_dir = _DIR_FROM_DELTA[(dx, dy)]

    moves = []
    if teleport_hostiles:
        moves.append({"cmd": "battle_teleport_all", "faction": "hostile",
                      "corner": corner, "facing": alien_facing})
    moves.append({"cmd": "battle_teleport_unit", "unit": actor_id,
                  "x": near[0], "y": near[1], "z": near[2], "dir": soldier_dir})
    place_deterministic(host, client, moves, what=f"contact_free_ufo_door_setup{tag}")

    return actor_id, near, far, door


def lightning_door(host):
    """The craft's own UFO door: exactly one find_doors entry with dataSet LIGHTNIN."""
    r = host.cmd({"cmd": "find_doors", "limit": 512})
    assert r.get("ok"), f"find_doors failed: {r}"
    ds = [d for d in r.get("doors", []) if d.get("dataSet") == "LIGHTNIN"]
    assert len(ds) == 1, f"FIXTURE: expected exactly one LIGHTNIN door, got {ds}"
    return ds[0], r["mapSizeX"], r["mapSizeY"]


class KnownFlake(AssertionError):
    """a KNOWN flaky scenario was detected and its evidence recorded. Exit 2, loudly."""

    def __init__(self, message, test=None, tracking="known-flake"):
        super().__init__(message)
        self.test = test
        self.tracking = tracking


KNOWN_FLAKE_BANNER = (
    "################################################################################\n"
    "#  KNOWN FLAKY SCENARIO - NOT A NEW FAILURE - EVIDENCE KEPT FOR DEBUGGING      #\n"
    "#  {test}: {summary}\n"
    "#  Tracked as {tracking}. This failure is IMPORTANT EVIDENCE toward fixing the    #\n"
    "#  known flake: keep this log. The JSON record follows / preceded this banner. #\n"
    "################################################################################")


def print_known_flake_banner(test, tracking, summary):
    print("\n" + KNOWN_FLAKE_BANNER.format(test=test, tracking=tracking, summary=summary) + "\n",
          flush=True)


def units_near(gc, tiles, radius=3):
    """Every living unit within Chebyshev `radius` of ANY of `tiles`: id, faction, position,
    armorSize, status - anything that could be on the tile."""
    out = []
    for u in battle_state(gc).get("units", []):
        if u.get("isOut"):
            continue
        p = unit_pos(u)
        if any(cheb(p, t) <= radius for t in tiles):
            out.append({"id": u["id"], "faction": u.get("faction"), "pos": p,
                        "armorSize": u.get("armorSize", 1), "status": u.get("status"),
                        "soldierId": u.get("soldierId")})
    return out


def known_flake(test, tracking, summary, record):
    """print the banner + the one-line JSON record + the banner, then raise KnownFlake
    (the caller's __main__ maps it to exit 2 and prints the banner once more)."""
    import json as _json
    print_known_flake_banner(test, tracking, summary)
    print("KNOWN-FLAKE-RECORD " + _json.dumps(record, default=str, sort_keys=True), flush=True)
    print_known_flake_banner(test, tracking, summary)
    raise KnownFlake(f"{test}: {summary} (known flake {tracking}; record printed above)", test, tracking)


_OPPOSITE_CORNER = {"NW": "SE", "NE": "SW", "SW": "NE", "SE": "NW"}
_RING_DIRS = (0, 2, 4, 6)  # N, E, S, W - straight runs are checked in this fixed order


def _nearest_non_player(st, t):
    """3D distance from tile t to the closest LIVING non-player unit, or None."""
    best = None
    for u in st.get("units", []):
        if u.get("faction") == FACTION_PLAYER or u.get("isOut"):
            continue
        d2 = (u["x"] - t[0]) ** 2 + (u["y"] - t[1]) ** 2 + (u["z"] - t[2]) ** 2
        if best is None or d2 < best:
            best = d2
    return None if best is None else best ** 0.5


def stage_open_ground_actor(host, client, soldier_ids, tag, door_radius=2, contact_min=21,
                            need_weapon=False, run_length=1, scan_radius=12):
    """Stage the 'open-ground, no-door, no-contact' actor the battle
    fixtures need on the FIRST map, instead of re-rolling for one.

    1. Every live hostile -> the corner FARTHEST from the player squad's centroid, facing into
       it; every live neutral -> the diagonally OPPOSITE corner. Both machines,
       identical moves, hash gate (place_deterministic).
    2. For each soldier in `soldier_ids` (caller's order; skip it if `need_weapon` and it carries
       none), scan tiles at the soldier's own z in rings of growing Chebyshev radius 0..scan_radius
       around its position (within a ring: sorted by (dy, dx)); take the FIRST tile that
       - has a floor and is unoccupied (tile_walkable; the soldier's own tile counts as free),
       - has no door part within `door_radius` at that z (find_doors, one round trip),
       - is >= `contact_min` (3D) from every living non-player unit,
       - if run_length > 0: has, in at least one of N/E/S/W (checked in that order), a straight
         run of `run_length` tiles that each meet the three conditions above.
    3. Teleport the soldier there (both machines, hash gate), facing the run direction (or its
       current facing when run_length == 0). Returns (unit_dict_after, tile, run_dir_or_None).

    Never re-rolls. No tile within scan_radius for any soldier => AssertionError prefixed
    'FIXTURE:' (a FAIL: the caller exits 2). A 'nothing spotted at t=0' condition is
    deliberately NOT part of this: the teleport command does not recompute sight, so
    the visible list can be stale; the contact distance is what prevents a mid-chain abort
    (spotted-set GROWTH).
    """
    what = f"stage_open_ground_actor[{tag}]"
    st = battle_state(host)
    assert st.get("ok") and st.get("inBattle"), f"{what}: no live battle on the host: {st}"
    doors_resp = host.cmd({"cmd": "find_doors", "limit": 512})
    assert doors_resp.get("ok"), f"{what}: find_doors failed: {doors_resp}"
    mx, my = doors_resp["mapSizeX"], doors_resp["mapSizeY"]
    doors = [(d["x"], d["y"], d["z"]) for d in doors_resp.get("doors", [])]

    players = [u for u in st["units"] if u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
    assert players, f"FIXTURE: {what}: no live player unit"
    cx = sum(u["x"] for u in players) / float(len(players))
    cy = sum(u["y"] for u in players) / float(len(players))
    corner = ("S" if cy < my / 2.0 else "N") + ("E" if cx < mx / 2.0 else "W")
    opposite = _OPPOSITE_CORNER[corner]
    moves = []
    if any(u.get("faction") == FACTION_HOSTILE and not u.get("isOut") for u in st["units"]):
        moves.append({"cmd": "battle_teleport_all", "faction": "hostile",
                      "corner": corner, "facing": _CORNER_FACING[corner]})
    if any(u.get("faction") == 2 and not u.get("isOut") for u in st["units"]):
        moves.append({"cmd": "battle_teleport_all", "faction": "neutral",
                      "corner": opposite, "facing": _CORNER_FACING[opposite]})
    if moves:
        place_deterministic(host, client, moves, what=f"{what} clear the field")
    st = battle_state(host)
    occupied = {unit_pos(u) for u in st["units"] if not u.get("isOut")}

    def door_near(t):
        return any(dz == t[2] and abs(dx - t[0]) <= door_radius and abs(dy - t[1]) <= door_radius
                   for (dx, dy, dz) in doors)

    def ok_tile(t, self_pos):
        if t != self_pos and not tile_walkable(host, t, occupied):
            return False
        if t == self_pos and not tile_walkable(host, t, occupied - {self_pos}):
            return False
        if door_near(t):
            return False
        d = _nearest_non_player(st, t)
        return d is None or d >= contact_min

    tried = []
    for sid in soldier_ids:
        unit = next((u for u in st["units"] if u.get("soldierId") == sid and not u.get("isOut")), None)
        if unit is None:
            tried.append((sid, "no live unit"))
            continue
        if need_weapon and not unit.get("weapon"):
            tried.append((sid, "no weapon"))
            continue
        here = unit_pos(unit)
        for radius in range(0, scan_radius + 1):
            ring = sorted(((dx, dy) for dx in range(-radius, radius + 1)
                           for dy in range(-radius, radius + 1)
                           if max(abs(dx), abs(dy)) == radius), key=lambda p: (p[1], p[0]))
            for dx, dy in ring:
                t = (here[0] + dx, here[1] + dy, here[2])
                if not ok_tile(t, here):
                    continue
                run_dir = None
                if run_length > 0:
                    for d in _RING_DIRS:
                        tiles = [(t[0] + DIR_DX[d] * k, t[1] + DIR_DY[d] * k, t[2])
                                 for k in range(1, run_length + 1)]
                        if all(ok_tile(x, here) for x in tiles):
                            run_dir = d
                            break
                    if run_dir is None:
                        continue
                facing = run_dir if run_dir is not None else unit.get("direction", 0)
                place_deterministic(host, client, [
                    {"cmd": "battle_teleport_unit", "unit": unit["id"],
                     "x": t[0], "y": t[1], "z": t[2], "dir": facing}],
                    what=f"{what} stage actor {unit['id']} at {t} facing {facing}")
                after = next(u for u in battle_state(host)["units"] if u["id"] == unit["id"])
                print(f"[{tag}] staged actor {unit['id']} (soldierId {sid}) at {t}, "
                      f"run_dir={run_dir}, hostiles -> {corner}, neutrals -> {opposite}")
                return after, t, run_dir
        tried.append((sid, f"no tile within {scan_radius}"))
    raise AssertionError(
        f"FIXTURE: {what}: no soldier could be staged on open ground (door_radius={door_radius}, "
        f"contact_min={contact_min}, run_length={run_length}, need_weapon={need_weapon}); "
        f"tried={tried}")


def assert_turret_parity(host, client, what="", unit_ids=None):
    """`battle_state`'s per-unit `directionTurret` must read
    the SAME on both machines for every unit they share (or just `unit_ids`).

    Why this needs its own assert instead of riding a bucket: the field is
    serialized unconditionally (BattleUnit.cpp:717) but NO structured hash
    bucket reads it, and it is not on `saveBlobExcludedUnitKey`'s list
    (SharedEcon.cpp) - so its only hash coverage is the saveBlob catch-all,
    which reports "saveBlob differs" without ever naming a field. This assert
    names it.

    Regression gate: a client applier that writes a body turn with
    BattleUnit::setDirection() couples the turret to the
    body (BattleUnit.cpp:988-994, "only used for initial unit placement"),
    while the host's real rotation runs through BattleUnit::turn() and leaves
    a turret-less soldier's turret untouched (the `_turretType > -1` guards,
    BattleUnit.cpp:1326-1347). Two rotations of one soldier are enough to
    drive host=0 / client=2 and break `hash_now full` on saveBlob alone.

    Lives here (next to assert_hash_clean) rather than inline in one repro:
    both repro_atom_turn.py and repro_atom_kneel.py drive turns and both need
    it. Returns the number of units compared."""
    tag = f" {what}" if what else ""
    hs = host.cmd({"cmd": "battle_state"})
    cs = client.cmd({"cmd": "battle_state"})
    assert hs.get("ok") and hs.get("inBattle"), f"battle_state unusable on host{tag}: {hs}"
    assert cs.get("ok") and cs.get("inBattle"), f"battle_state unusable on client{tag}: {cs}"
    hu = {u["id"]: u for u in hs.get("units", [])}
    cu = {u["id"]: u for u in cs.get("units", [])}
    ids = sorted(set(hu) & set(cu)) if unit_ids is None else list(unit_ids)
    assert ids, f"no common units between host and client{tag}"
    missing = [i for i in ids if "directionTurret" not in hu[i] or "directionTurret" not in cu[i]]
    assert not missing, (
        f"battle_state units {missing} carry no 'directionTurret' field{tag} - "
        "the exe predates the TestServer's directionTurret field (stale build?)")
    bad = {i: (hu[i]["directionTurret"], cu[i]["directionTurret"])
           for i in ids if hu[i]["directionTurret"] != cu[i]["directionTurret"]}
    assert not bad, (
        f"directionTurret MISMATCH{tag}: {len(bad)}/{len(ids)} unit(s) differ, "
        f"(host, client) = {bad} - the client applier dragged the turret along "
        "with the body facing again")
    return len(ids)


def assert_reveal_parity(host, client, what="", samples=24, extra_positions=()):
    """The two machines' per-tile
    fog of war must be IDENTICAL - the host is the sole author of `discovered`
    bits and a thin client never computes tile FOV of its own
    (TileEngine::calculateTilesInFOV is suppressed on hostSim==false).

    Three layers, cheapest first:
      1. aggregate per-part counts (`reveal_state`) - catches any drift,
         including on VOID tiles, which SavedBattleGame::save skips entirely
         and which the saveBlob hash therefore CANNOT see;
      2. the host has nothing left unpublished (its quiescent flush drained);
      3. per-part `isDiscovered` equality via `tile_info` on a deterministic
         spread of tile indices plus any caller-supplied `extra_positions`
         (x, y, z) tuples, e.g. the acting unit's own neighbourhood - per-TILE
         evidence, not just matching totals.

    Lives here next to assert_hash_clean/assert_turret_parity: every
    repro that drives an action needs it. Returns the host's reveal_state dict.
    """
    tag = f" {what}" if what else ""
    hr = host.cmd({"cmd": "reveal_state"})
    cr = client.cmd({"cmd": "reveal_state"})
    assert hr.get("ok") and cr.get("ok"), \
        f"reveal_state unusable{tag}: host={hr} client={cr}"
    assert hr["mapSizeXYZ"] == cr["mapSizeXYZ"], (
        f"map size differs{tag}: host={hr['mapSizeXYZ']} client={cr['mapSizeXYZ']}")

    for part in ("floor", "westwall", "northwall"):
        assert hr[part] == cr[part], (
            f"discovered {part} count MISMATCH{tag}: host={hr[part]} client={cr[part]} "
            f"(of {hr['mapSizeXYZ']} tiles) - the host's reveals did not reach the client, "
            "or the client authored fog of war of its own")

    assert hr["unpublished"] is False, (
        f"host still has UNPUBLISHED reveal bits{tag}: {hr} - CoopReveal::flushQuiescent "
        "never drained them, so the client is (silently) behind")

    n = hr["mapSizeXYZ"]
    probes = [{"index": i}
              for i in list(range(0, n, max(1, n // max(1, samples))))[:samples]]
    probes += [{"x": int(p[0]), "y": int(p[1]), "z": int(p[2])} for p in extra_positions]
    parts = ("floor", "westwall", "northwall")
    bad = []
    for probe in probes:
        req = dict(probe); req["cmd"] = "tile_info"
        ht = host.cmd(req)
        ct = client.cmd(req)
        if not ht.get("ok") or not ct.get("ok"):
            continue
        for p in parts:
            hd = ht["parts"][p]["isDiscovered"]
            cd = ct["parts"][p]["isDiscovered"]
            if hd != cd:
                bad.append((probe, p, hd, cd))
    assert not bad, (
        f"tile_info per-part isDiscovered MISMATCH{tag} on {len(bad)} (tile, part) pair(s) "
        f"out of {len(probes)} probed tiles: {bad[:12]}")

    return hr


def host_reveal_emits(host):
    """How many reveal deltas the HOST has attached to an outgoing envelope so
    far this process, read straight out of its own log. The event ring
    (CoopEventLog) is a fixed POD struct and deliberately carries no payload,
    so this is the only way to assert "this action emitted NO reveal field" -
    which is exactly what the reveal field's presence gating promises for an
    action that discovered nothing."""
    path = os.path.join(host.user_dir, "openxcom.log")
    try:
        with open(path, "r", errors="replace") as f:
            return sum(1 for ln in f if "[coop-reveal] attached reveal delta" in ln)
    except OSError:
        return 0


def dismiss_battle_start_overlays(host, timeout=10):
    """Clear the vanilla battle-start overlays stacked over one machine's
    BattlescapeState, so the map screen is on top and its _gameTimer ticks
    again. Presses ESC (Options::keyCancel) until BattlescapeState is the top
    state.

    One shared copy: repro_atom_turn.py, repro_atom_kneel.py,
    repro_reveal_sync.py, test_input_gating.py and test_retry_cancel.py each
    carried their own, and the stack it clears changes with the battle-entry
    code, so one copy is easier to keep right (as with
    dismiss_client_briefing() below).

    WHY IT EXISTS:
    a freshly generated battle stacks overlays on top of BattlescapeState, and
    Game::run() only think()s _states.back() (Game.cpp) - so BattlescapeState's
    _gameTimer, and with it the whole BState machine including an admitted coop
    action, never ticks until they are gone. An injected TAB/click would also
    land on the overlay instead of the map.

    WHAT IS ON THAT STACK: a fresh co-op battle opens the pre-battle equip
    screen on BOTH machines and its OK - which ESC is bound to - is the
    ready TOGGLE, so an ESC loop over it would flap this seat's
    ready. While this machine's `event_state.equip.phase` is "open" this helper
    therefore RAISES instead of pressing ESC: the equip screens close through
    equip_both_ready() below. After the equip end both machines hold vanilla's
    "Turn 1 begins" screen (NextTurnState), and this helper clears either one;
    drive_to_battlescape() calls it for the host and then for the client. The
    client's entry overlay before that is the read-only BriefingState, which
    dismiss_client_briefing() below owns. In a plain SP battle the stack is
    ['BattlescapeState','NextTurnState','InventoryState'], which is why this
    stays an ESC LOOP on the top state rather than a fixed number of presses:
    it is correct for every shape, and for a stack that is already clean.
    """
    deadline, t_esc = time.time() + timeout, None
    while time.time() < deadline:
        st = states(host)
        if st and "BattlescapeState" in st[-1]:
            # the Turn-1 screen's close arms a turn-start autosave that BattlescapeState::init()
            # pushes in the NEXT loop pass, after the test server has answered this read; a second read lands in a later
            # pass and shows its SaveGameState
            if "BattlescapeState" not in (states(host) or [""])[-1]:
                continue
            # 0.3 s after the LAST ESC is the floor: it also lets the battle's turn-start states end
            # (isBusy: an END TURN pressed before that does nothing). Waiting for isBusy false instead would also
            # wait out a generation casualty's collapse, which test_corpse_node reads for at this point.
            if t_esc is not None and time.time() < t_esc + 0.3:
                time.sleep(t_esc + 0.3 - time.time())
                continue
            return
        if st and "SaveGameState" in st[-1]:
            # wait out a save in progress instead of pressing ESC into it (at most 0.3 s per pass)
            _wait_stacks_change((host,), (st,), 0.3)
            continue
        phase = (event_state(host).get("equip") or {}).get("phase")
        if phase == "open":
            raise AssertionError(
                f"{host.name}: dismiss_battle_start_overlays called while the pre-battle equip phase is "
                f"open (ESC is the ready toggle there) - use equip_both_ready() first; "
                f"stack={states(host)}")
        host.ok({"cmd": "inject_input", "kind": "key", "key": 27})  # SDLK_ESCAPE / Options::keyCancel
        t_esc = time.time()
        _wait_stacks_change((host,), (st,), 0.3)  # until the overlay closes, at most 0.3 s
    raise TimeoutError(f"{host.name}: battle-start overlays never cleared, stack={states(host)}")


def dismiss_client_briefing(client, timeout=20):
    """The coop CLIENT enters a battle the way the host
    does - BattlescapeState FIRST, then a READ-ONLY BriefingState OVER it
    (CoopHandshake::onBlobChunkAppended, connectionTCP.cpp). Every fixture that
    DRIVES the client must dismiss that briefing explicitly instead of assuming
    the battle screen is on top. Two reasons:
      * Game::run() only think()s _states.back(), so an injected key/click
        lands on the BRIEFING, not on the map;
      * BriefingState's ctor holds the GEOSCAPE base resolution while it is up
        (BriefingState.cpp:58-60), so any screen-projection probe computes
        against the wrong viewport (repro_atom_turn.py's run_ui_variant then
        reports "computed click target (-330,350) is off the 320x200 map
        viewport").

    Read-only PROBES (battle_state / event_state / hash_now / get_palettes) do
    work under it - test_client_briefing.py asserts exactly that - so this
    helper is about DRIVING, not probing.

    Idempotent: a no-op when the client has no
    BriefingState on its stack (a resume entry), so it
    is safe to call unconditionally at the end of every drive_to_battlescape().

    In a fresh co-op battle the
    client's equip entry (a pump step once its briefing has closed) pushes
    vanilla's Turn-1 screen and then its pre-battle equip screen, so the landing
    top is InventoryState, NextTurnState or BattlescapeState (the entry not yet
    run, or nothing to equip).
    """
    st = states(client)
    if not any("BriefingState" in s for s in st):
        return False
    client.ok({"cmd": "close_briefing"})
    client.wait_for(
        "client dismissed its entry briefing",
        lambda: (not any("BriefingState" in s for s in states(client))) or None,
        timeout=timeout)
    top = states(client)[-1] if states(client) else None
    assert top and any(t in top for t in ("InventoryState", "NextTurnState", "BattlescapeState")), (
        "closing the client's entry briefing should land it on its pre-battle equip screen, its "
        f"Turn-1 screen or BattlescapeState, got stack={states(client)}")
    return True


# ---------------------------------------------------------------------------
# FIXTURE ACTOR SELECTION: the contact rule.
#
# The one shared copy of the contact rule, here where every coop test already
# imports from, so every test that picks a fixture actor applies the same premise.
#
# WHAT IT CHECKS. A turn fixture needs an "open-ground, no-door,
# NO-ENEMY-LOS" actor. The spotted rule ("no hostile ALREADY spotted at t=0")
# and the door rule ("no door within 2 tiles") cover the first two; NEITHER says anything
# about whether the actor's ROTATION will bring a unit into view. Vanilla
# aborts a BA_NONE turn mid-chain the moment getUnitsSpottedThisTurn() grows
# (UnitTurnBState.cpp:117), leaving the unit on an intermediate facing - and
# the engine itself calls that a FIXTURE failure, logging "[coop-turn] ...
# ABORTED mid-chain - the turn fixture guards ... should have
# prevented this".
#
# It narrows which actor a fixture picks, never relaxes anything a test
# asserts: a fixture that fails it is RE-ROLLED, and the assertions that run
# afterwards are unchanged.
# ---------------------------------------------------------------------------

FACTION_PLAYER_ID = 0

# Mod::_maxViewDistance's default (src/Mod/Mod.cpp:424), which stock xcom1 does
# not override (no `maxViewDistance` key in bin/standard/xcom1/*.rul). A HARD
# CAP: darkness and maxDarknessToSeeUnits only ever REDUCE effective view
# range, never extend it - which is what makes "nobody within this many tiles"
# a sound superset of "this actor's rotation cannot spot anybody" rather than
# merely a likely one.
MAX_VIEW_DISTANCE = 20


def nearest_non_player_distance(battle_state_resp, unit):
    """Straight-line 3D tile distance from @a unit to the closest LIVING
    non-player unit in @a battle_state_resp, or None when there are none.

    3D because vanilla's own view-distance test is a 3D squared-distance
    compare. Hostile AND neutral both count: the harness cannot cheaply tell
    which factions a given observer adds to its spotted set, so it excludes
    both - deliberately conservative."""
    best = None
    for u in battle_state_resp.get("units", []):
        if u.get("faction") == FACTION_PLAYER_ID or u.get("isOut"):
            continue
        d2 = ((u["x"] - unit["x"]) ** 2 + (u["y"] - unit["y"]) ** 2
              + (u["z"] - unit["z"]) ** 2)
        if best is None or d2 < best:
            best = d2
    return None if best is None else best ** 0.5


def actor_is_contact_free(battle_state_resp, unit, tag):
    """The contact rule: True iff no LIVING NON-PLAYER unit is within
    MAX_VIEW_DISTANCE of @a unit - i.e. no rotation of this actor can spot
    anybody, so vanilla's unitSpotted abort branch is unreachable for it.

    @a tag is the calling test's name, for the log line. Callers use this as
    the third arm of their own qualifying_actor(): fail it -> return None ->
    the bounded re-roll loop boots a fresh generation."""
    d = nearest_non_player_distance(battle_state_resp, unit)
    if d is not None and d <= MAX_VIEW_DISTANCE:
        print("[%s] contact rule: nearest non-player unit is %.2f tiles from the actor "
              "(cap %d) - its rotation could spot one and abort mid-chain"
              % (tag, d, MAX_VIEW_DISTANCE))
        return False
    print("[%s] contact rule ok: nearest non-player unit is %s away (cap %d)"
          % (tag, "none at all" if d is None else "%.2f tiles" % d,
             MAX_VIEW_DISTANCE))
    return True


# ===== battle primitives shared by the door, walk and turn repros: the state
# stack, units, doors, tiles, walks, staging and the battle bring-up.


def states_stripped(gc):
    """`states()` with MSVC's "class OpenXcom::" prefix removed - the form every
    repro compares against. The same as repro_atom_walk.states: it is a pure
    wrapper over this module's OWN states(), so it
    lives here without importing repro_atom_walk (which imports session, and
    would cycle)."""
    return [s.replace("class OpenXcom::", "") for s in states(gc)]


def top_state(gc):
    """The top of the state stack, prefix-stripped (as repro_atom_walk.top_state)."""
    st = states_stripped(gc)
    return st[-1] if st else None


COOP_SEAT_1 = 1
O_FLOOR, O_WESTWALL, O_NORTHWALL, O_OBJECT = 0, 1, 2, 3
FACTION_PLAYER = 0
FACTION_HOSTILE = 1  # standard OpenXcom UnitFaction enum (PLAYER=0, HOSTILE=1, NEUTRAL=2)
DIR_DX = [0, 1, 1, 1, 0, -1, -1, -1]
DIR_DY = [-1, -1, 0, 1, 1, 1, 0, -1]


def battle_state(gc):
    return gc.cmd({"cmd": "battle_state"})


def event_state(gc):
    return gc.cmd({"cmd": "event_state"})


def event_log(gc, tail=120):
    return gc.cmd({"cmd": "event_log", "tail": tail}).get("events", [])


COOP_SEAT_NONE = -1  # CoopSeat.h: "no seat commands this unit"


def pin_ai_neutral(host, client, tag=""):
    """The ONE shared AI-neutral pin every boundary-crossing test imports
    rather than re-implementing. A boundary-crossing test is any test that
    presses END TURN and lets the battle run through the alien (and civilian)
    phase back to the player side; no non-player unit may act during such a
    test, so this pins every unit no human seat commands so it CANNOT act.

    Call immediately after drive_to_battlescape(). Reads `battle_state.units`
    on the HOST for every LIVE unit whose `coop` seat is COOP_SEAT_NONE (-1)
    and whose `faction` is not FACTION_PLAYER (0) - i.e. no human seat owns
    it. In gm2 the client's own aliens sit at seat 1 (not NONE), so they are
    correctly left unpinned and this may legitimately find zero - callers of
    a gm2 boot must not assert count > 0 themselves; a
    CLASSIC boot with zero pinned units is a failure (the premise - a NONE-seat
    non-player unit exists for the pin to act on - is unexercised).

    THE CALL SHAPE (measured against the set_stat
    handler, TestServer.cpp): a top-level `tu` key is
    silently IGNORED by that handler (only `psiSkill`/`psiStrength` are read
    as top-level keys; `tu`/`reactions`/`firing` are read ONLY through the
    `stat`+`value` pair), and `setStat("tu", v)` alone writes only the unit's
    BASE stats, never the current `_tu` - an alien already holding a full TU
    bar at t=0 would still act on its first hostile phase. Per unit, to BOTH
    machines (each machine independently simulates the battle - the same
    rule place_deterministic above follows), three `set_stat`
    calls:
      {stat: "psiSkill",  value: 0}
      {stat: "reactions", value: 0}   - zeroes BattleUnit::getReactionScore()
                                         (TileEngine::getSpottingUnits()'s own
                                         gate), so the unit cannot react
      {stat: "tu", value: 0, refill: True} - `refill` runs
                                         unit->setTimeUnits(bs->tu) in THE
                                         SAME call, draining the CURRENT bar
                                         the instant the base stat is zeroed.
    The third call's reply reports `tu` after the write - asserted 0 on BOTH
    machines for every pinned unit.

    WHY THE PIN HOLDS AT EVERY LATER PHASE (from the code):
    SavedBattleGame::endTurn() -> prepareNewTurn() ->
    updateUnitStats(true, false) -> prepareTimeUnits() -> setValueMax(_tu,
    recovery, 0, getBaseStats()->tu) - with base tu clamped to 0 this pins
    `_tu` back to 0 every turn, forever. No re-pin per phase is needed.

    Finally asserts `assert_hash_clean(host, client, full=True)` (a t=0,
    pre-first-event boundary sweep - the clean precondition every later
    per-boundary check builds on).

    Prints and returns the pinned unit id list; does NOT itself assert the
    count is non-zero (see the gm2 note above) - that is the caller's job."""
    tagstr = f" {tag}" if tag else ""
    st = battle_state(host)
    assert st.get("ok") and st.get("inBattle"), \
        f"pin_ai_neutral{tagstr}: no live battle on host: {st}"
    targets = [u["id"] for u in st.get("units", [])
               if u.get("coop") == COOP_SEAT_NONE and u.get("faction") != FACTION_PLAYER
               and not u.get("isOut")]
    for uid in targets:
        for gc in (client, host):  # client first (see place_deterministic)
            who = "host" if gc is host else "client"
            for stat in ("psiSkill", "reactions"):
                r = gc.cmd({"cmd": "battle_action", "action": "set_stat", "unit": uid,
                            "stat": stat, "value": 0})
                assert r.get("ok"), (
                    f"pin_ai_neutral{tagstr}: set_stat {stat} unit {uid} failed "
                    f"on {who}: {r}")
            r = gc.cmd({"cmd": "battle_action", "action": "set_stat", "unit": uid,
                        "stat": "tu", "value": 0, "refill": True})
            assert r.get("ok"), (
                f"pin_ai_neutral{tagstr}: set_stat tu unit {uid} failed on {who}: {r}")
            assert r.get("tu") == 0, (
                f"pin_ai_neutral{tagstr}: unit {uid} read back tu={r.get('tu')} "
                f"after refill on {who}, expected 0")
        wait_seq_barrier(host, client)
    assert_hash_clean(host, client, full=True, what=f"pin_ai_neutral{tagstr}")
    print(f"[pin_ai_neutral{tagstr}] pinned {len(targets)} NONE-seat non-player "
          f"unit(s): {targets}")
    return targets


def action_events(gc, action_id, tail=160):
    return [e for e in event_log(gc, tail) if e.get("actionId") == action_id]


def find_doors(gc):
    r = gc.cmd({"cmd": "find_doors", "limit": 512})
    assert r.get("ok"), f"find_doors failed: {r}"
    return r["doors"]


def door_census(gc):
    """Every door part this machine knows about, as a comparable set. Used two
    ways: HOST vs CLIENT (they must be identical - that is the terrain-sync
    assertion) and BEFORE vs AFTER (they must differ - that is the non-vacuity
    control). A NORMAL door that opens leaves the census entirely, because
    Tile::openDoor clears the part's map data; a UFO door stays and flips
    isUfoDoorOpen."""
    return sorted((d["x"], d["y"], d["z"], d["part"], d["isUfoDoor"],
                   d["isUfoDoorOpen"], d["mapDataID"]) for d in find_doors(gc))


def assert_door_parity(host, client, what):
    hc, cc = door_census(host), door_census(client)
    if hc != cc:
        only_h = [e for e in hc if e not in cc]
        only_c = [e for e in cc if e not in hc]
        raise AssertionError(
            f"{what}: the two machines' DOOR CENSUS differ - "
            f"{len(only_h)} entr(ies) only on the host {only_h[:6]}, "
            f"{len(only_c)} only on the client {only_c[:6]}. The client did not "
            "apply the host's terrain change.")
    return hc


def assert_door_between_steps(gc, action_id, what):
    """The `door` ev takes its place in the
    seq stream BETWEEN the walk step evs either side of the doorway."""
    evs = action_events(gc, action_id)
    kinds = [(e["seq"], e["kind"]) for e in evs]
    doors = [e for e in evs if e["kind"] == "door"]
    steps = [e for e in evs if e["kind"] == "walk_step"]
    assert doors, (
        f"{what}: actionId {action_id} emitted NO `door` ev - the walk did not "
        f"cross a door (stream: {kinds})")
    d0 = doors[0]
    before = [s for s in steps if s["seq"] < d0["seq"]]
    after = [s for s in steps if s["seq"] > d0["seq"]]
    assert before, (
        f"{what}: the `door` ev (seq {d0['seq']}) has NO walk_step BEFORE it in "
        f"actionId {action_id} - it was emitted before the walk began stepping, "
        f"not at the doorway (stream: {kinds})")
    assert after, (
        f"{what}: the `door` ev (seq {d0['seq']}) has NO walk_step AFTER it in "
        f"actionId {action_id} - it was flushed at the END of the walk instead of "
        f"at its own position in the stream (stream: {kinds})")
    print(f"    [{what}] stream: {kinds}")
    print(f"    [{what}] door ev seq={d0['seq']} sits between {len(before)} step(s) "
          f"before and {len(after)} after, all in actionId {action_id}")
    return d0


def closed_doors(gc):
    out = []
    for d in find_doors(gc):
        if d["isUfoDoor"] and d["isUfoDoorOpen"]:
            continue
        if door_sides(d) is None:
            continue
        out.append(d)
    return out


def closed_door_at(gc, door_at):
    return any((x["x"], x["y"], x["z"], x["part"]) == door_at
               for x in closed_doors(gc))


def door_lookup(gc, door_at):
    """Diagnostic helper: the full door dict at
    (x,y,z,part) - notably its `isUfoDoorOpen` - or None if that coordinate is
    not a door on this machine right now. `find_doors`/`closed_doors` already
    exist; this just indexes by coordinate so a rejection record can report
    the door's own before/after state without re-deriving the filter."""
    for d in find_doors(gc):
        if (d["x"], d["y"], d["z"], d["part"]) == door_at:
            return d
    return None


def door_sides(d):
    """The two tiles a wall-part door joins. O_WESTWALL is the west face of its
    own tile, O_NORTHWALL the north face (TileEngine::unitOpensDoor's own
    checkPositions table, TileEngine.cpp:4108-4177). Floor/object doors are
    skipped: this file only reasons about doors you WALK THROUGH."""
    t = (d["x"], d["y"], d["z"])
    if d["part"] == O_WESTWALL:
        return t, (d["x"] - 1, d["y"], d["z"])
    if d["part"] == O_NORTHWALL:
        return t, (d["x"], d["y"] - 1, d["z"])
    return None


def unit_pos(u):
    return (u["x"], u["y"], u["z"])


def units(gc):
    return battle_state(gc).get("units", [])


def seat_units(gc, seat=COOP_SEAT_1):
    return [u for u in units(gc)
            if u.get("faction") == FACTION_PLAYER and not u.get("isOut")
            and u.get("coop") == seat]


def spotted(gc):
    return sorted(battle_state(gc).get("spotted") or [])


def dir_between(a, b):
    dx = (b[0] > a[0]) - (b[0] < a[0])
    dy = (b[1] > a[1]) - (b[1] < a[1])
    for d in range(8):
        if DIR_DX[d] == dx and DIR_DY[d] == dy:
            return d
    return None


# ===== shared walk search helpers (used by the walk, door and turn repros) =====


WALK_RUN = 3


def units_by_id(resp):
    return {u["id"]: u for u in resp.get("units", [])}


def unit_of(gc, uid):
    return units_by_id(battle_state(gc))[uid]


def last_walk(gc):
    return event_state(gc).get("lastWalk") or {}


def pos_of(u):
    return (u["x"], u["y"], u["z"])


def jpos(p):
    return {"x": p[0], "y": p[1], "z": p[2]}


def has_door_within(gc, x, y, z, radius):
    """Any door part within Chebyshev @a radius of (x,y) at the SAME level.

    Reads the `find_doors` probe - ONE round trip for the whole map -
    instead of a tile_info sweep, which is the same predicate at
    (2*radius+1)^2 round trips per soldier. At the tight WALK_DOOR_RADIUS the
    sweep is merely wasteful; at WALK_DOOR_REQUIRE_RADIUS, across every seated
    soldier, it costs ~4.7 MINUTES per fixture attempt (measured)."""
    r = gc.cmd({"cmd": "find_doors", "limit": 512})
    if not r.get("ok"):
        return False
    for d in r["doors"]:
        if d["z"] == z and abs(d["x"] - x) <= radius and abs(d["y"] - y) <= radius:
            return True
    return False


def tile_is_open_ground(gc, x, y, z, occupied):
    """A cheap, CONSERVATIVE walkability screen for a candidate step tile: it
    exists, it has a FLOOR, it carries no door part, and no unit is standing on
    it. The pathfinder remains the real judge - a candidate that survives this
    and still yields no route is simply skipped by the caller."""
    if (x, y, z) in occupied:
        return False
    ti = gc.cmd({"cmd": "tile_info", "x": x, "y": y, "z": z})
    if not ti.get("ok"):
        return False
    parts = ti.get("parts", {})
    if parts.get("floor", {}).get("mapDataID", -1) < 0:
        return False
    for part in parts.values():
        if part.get("isDoor") or part.get("isUfoDoor"):
            return False
    return True


TILE_CENSUS_MAX = 4096    # TestServer tile_census: at most this many tiles per call
FIND_DOORS_ALL = 1 << 20  # find_doors limit above any map's part count (4 parts per tile)


def tile_scan(gc, x0, x1, y0, y1, z0, z1, doors=False):
    """{(x, y, z): row} for EVERY position of the inclusive box, read in bulk:
    one TestServer `tile_census` call per <= TILE_CENSUS_MAX tiles
    instead of one `tile_info` round trip per tile. A row holds what the
    per-tile loops read from tile_info, under tile_info's own key names and
    getters: ok True, x / y / z, `parts` {floor, westwall, northwall, object}
    -> {mapDataID, mapDataSetID} (-1 when the part is empty), fire, smoke
    (and the census's `special`). A position with no tile (off the map:
    tile_info answers "no such tile") is {"ok": False}. tile_census reports no
    door flags: with @a doors, each existing row also gets `door` = some part
    isDoor or isUfoDoor, read from ONE find_doors reply (it lists every part
    where Tile::isUfoDoor or Tile::isDoor holds, the getters tile_info reports
    per part). An empty box returns {}."""
    rows = {}
    if x1 < x0 or y1 < y0 or z1 < z0:
        return rows
    w, h = x1 - x0 + 1, y1 - y0 + 1
    if w * h <= TILE_CENSUS_MAX:
        zs = TILE_CENSUS_MAX // (w * h)
        boxes = [(x0, x1, y0, y1, za, min(z1, za + zs - 1)) for za in range(z0, z1 + 1, zs)]
    else:
        xs = min(w, TILE_CENSUS_MAX)
        ys = TILE_CENSUS_MAX // xs
        boxes = [(xa, min(x1, xa + xs - 1), ya, min(y1, ya + ys - 1), z, z)
                 for z in range(z0, z1 + 1) for ya in range(y0, y1 + 1, ys) for xa in range(x0, x1 + 1, xs)]
    for bx0, bx1, by0, by1, bz0, bz1 in boxes:
        r = gc.ok({"cmd": "tile_census", "x0": bx0, "x1": bx1, "y0": by0, "y1": by1, "z0": bz0, "z1": bz1})
        tiles = r["tiles"]
        n = (bx1 - bx0 + 1) * (by1 - by0 + 1) * (bz1 - bz0 + 1)
        assert len(tiles) == n, f"{gc.name}: tile_census returned {len(tiles)} rows for a {n}-tile box"
        i = 0
        for z in range(bz0, bz1 + 1):          # the census's row order: z-, then y-, then x-major
            for y in range(by0, by1 + 1):
                for x in range(bx0, bx1 + 1):
                    t = tiles[i]
                    i += 1
                    if t is None:
                        rows[(x, y, z)] = {"ok": False}
                        continue
                    assert (t["x"], t["y"], t["z"]) == (x, y, z), f"{gc.name}: tile_census row {t} at {(x, y, z)}"
                    t["ok"] = True
                    rows[(x, y, z)] = t
    if doors:
        d = gc.ok({"cmd": "find_doors", "limit": FIND_DOORS_ALL})
        assert d["count"] < FIND_DOORS_ALL, f"{gc.name}: find_doors hit its limit {FIND_DOORS_ALL}"
        door_at = {(e["x"], e["y"], e["z"]) for e in d["doors"]}
        for pos, row in rows.items():
            if row["ok"]:
                row["door"] = pos in door_at
    return rows


def scan_is_open_ground(rows, t, occupied):
    """tile_is_open_ground's predicate read from a tile_scan(..., doors=True)
    result instead of a tile_info round trip: @a t is not occupied,
    its tile exists, it has a FLOOR part, and no part is a door. @a t must lie
    inside the scanned box (KeyError otherwise)."""
    if t in occupied:
        return False
    row = rows[t]
    if not row["ok"]:
        return False
    if row["parts"]["floor"]["mapDataID"] < 0:
        return False
    return not row["door"]


def living_non_players(battle_state_resp):
    return [(u["x"], u["y"], u["z"]) for u in battle_state_resp.get("units", [])
            if u.get("faction") != FACTION_PLAYER and not u.get("isOut")]


def min_dist_to(aliens, tile):
    """Straight-line 3D tile distance from @a tile to the nearest of @a aliens,
    or None when there are none. Same metric session.nearest_non_player_distance
    uses, applied to a TILE instead of a unit."""
    best = None
    for a in aliens:
        d2 = (a[0] - tile[0]) ** 2 + (a[1] - tile[1]) ** 2 + (a[2] - tile[2]) ** 2
        if best is None or d2 < best:
            best = d2
    return None if best is None else best ** 0.5


def region_is_contact_free(aliens, actor, dest, pad=1, max_dist=MAX_VIEW_DISTANCE):
    """The contact-free premise, applied to a candidate WALK rather than to
    the actor's starting tile: EVERY tile the walk could occupy must stay
    strictly outside session.MAX_VIEW_DISTANCE of every living non-player unit.

    The region checked is the bounding box of (actor, dest) PADDED by @a pad,
    which is a conservative superset of any route Pathfinding can produce for a
    walk of this length - the whole point being that the check must not depend
    on guessing the route. Aliens do not move while such a walk runs (the
    player side does not end), which is what makes
    a static per-tile check SOUND rather than merely likely.

    This per-walk check is what keeps a walk contact-free: a large static margin
    around the actor's start rejects every generation (see
    repro_atom_walk.WALK_CONTACT_MARGIN's comment). @a max_dist (default
    MAX_VIEW_DISTANCE) is the distance a tile must stay strictly outside
    (test_multistage.py's stage-2 walk passes a smaller one)."""
    x0, x1 = sorted((actor["x"], dest[0]))
    y0, y1 = sorted((actor["y"], dest[1]))
    for x in range(x0 - pad, x1 + pad + 1):
        for y in range(y0 - pad, y1 + pad + 1):
            d = min_dist_to(aliens, (x, y, dest[2]))
            if d is not None and d <= max_dist:
                return False
    return True


def straight_runs(host, actor, occupied, length=WALK_RUN, st=None, want=10,
                  min_alien_dist=MAX_VIEW_DISTANCE):
    """Candidate walk DESTINATIONS exactly @a length tiles away (Chebyshev) that
    are open ground and whose whole neighbourhood is contact-free. Returns a
    list of (dir_or_None, [dest]) so every call site keeps the shape it already
    used - `entry[1][-1]` is the destination and `len(entry[1])` is meaningless
    for planning, which is why nothing asserts a predicted path any more.

    WHY DESTINATIONS AND NOT A STRAIGHT OPEN RUN. A demand for N
    COLLINEAR open tiles is rejected by EVERY generation this map produces
    (15/15 boots, "no 3-tile open-ground run in any direction"): at t=0 the
    squad is packed inside the Skyranger, so an actor's neighbours are other
    soldiers and its straight lines run into the hull. Pathfinding routes around
    both. Nothing this test asserts needs the straight line - the executed path
    is compared against the HOST's own record and its own `plannedLen`, never
    against a path the harness predicted - so requiring one would over-specify
    the fixture.

    ORDERED so the destination FURTHEST from the nearest alien comes first:
    walking away from contact keeps the later phases' own open ground available
    and is the conservative direction for the pin above."""
    if st is None:
        st = battle_state(host)
    aliens = living_non_players(st)
    ring = []
    # BOTH the actor's own level AND the one below it. The squad starts INSIDE
    # the Skyranger, whose deck sits a level ABOVE the terrain: every tile
    # outside the hull at the actor's own z is AIR (floor mapDataID -1) and every
    # tile inside it is another soldier, so a same-level-only search returns
    # nothing at all and the first walk cannot be ordered (observed). The ground
    # the squad actually walks on is z-1, down the ramp, and Pathfinding handles
    # the drop itself.
    for dz in (0, -1, 1):
        z = actor["z"] + dz
        if z < 0:
            continue
        for dx in range(-length, length + 1):
            for dy in range(-length, length + 1):
                if max(abs(dx), abs(dy)) != length:
                    continue
                t = (actor["x"] + dx, actor["y"] + dy, z)
                if not region_is_contact_free(aliens, actor, t, max_dist=min_alien_dist):
                    continue
                d = min_dist_to(aliens, t)
                # same level first, then down, then up - a same-level walk is the
                # simplest thing to reason about and the others are the fallback.
                ring.append((abs(dz), -(d if d is not None else 1e9), t))
    ring.sort(key=lambda e: (e[0], e[1]))

    out = []
    for _, _, t in ring:
        if tile_is_open_ground(host, t[0], t[1], t[2], occupied):
            out.append((None, [t]))
            if len(out) >= want:
                break
    return out


def settle_reveal(host, client, timeout=40):
    """The host has NOTHING unpublished and the client has caught up. Same
    helper (and the same reason) as repro_atom_turn.py's: the host's quiescent
    reveal flush can publish a standalone `ev reveal` a tick or two after an action
    settles, and a measurement started before it would see the previous
    action's leftovers."""
    def quiet():
        cs = event_state(client)  # client, then the host's reveal_state, then its event_state
        rs = host.cmd({"cmd": "reveal_state"})
        hs = event_state(host)
        return bool(hs.get("ok") and cs.get("ok") and rs.get("ok")
                    and rs.get("unpublished") is False
                    and cs.get("lastSeqApplied", 0) == hs.get("lastSeqEmitted", 0)
                    and cs.get("queueDepth") == 0)
    client.wait_for("host has nothing unpublished and the client is caught up",
                    quiet, timeout=timeout)


def walk_action_id(gc):
    return (last_walk(gc) or {}).get("actionId", 0)


def wait_walk_settled(host, client, prev_action_id, timeout=30):
    """The host finished a NEW walk chain (its restate is out and the chain is
    no longer active) AND the client has applied everything up to it.

    @a prev_action_id is load-bearing: `lastWalk` KEEPS the previous walk's
    finished record, so a predicate that only asked "is a walk finished?" would
    be satisfied instantly by the walk BEFORE this one and every assertion after
    it would read stale data."""
    def done():
        cs = event_state(client)  # the client is read first
        hs = event_state(host)
        hw = hs.get("lastWalk") or {}
        return bool(hs.get("ok") and cs.get("ok")
                    and hw and hw.get("actionId", 0) != prev_action_id
                    and hw.get("active") is False and hw.get("restate")
                    and cs.get("lastSeqApplied", 0) == hs.get("lastSeqEmitted", 0)
                    and cs.get("queueDepth") == 0 and hs.get("queueDepth") == 0)
    try:
        client.wait_for("walk settled (a NEW host restate emitted, client caught up)",
                        done, timeout=timeout)
    except Exception:
        # on-timeout diagnostic ONLY. The poll gave up, so dump
        # both machines and WHICH predicate sub-condition is unmet, then re-raise the
        # original timeout. Fires ONLY on the failure path (no effect on passing runs);
        # the wait window is UNCHANGED; this is NOT a second poll and NOT a masking wait -
        # it records a rare stall (no desync, two lanes in parallel) for later debugging.
        _hs = event_state(host); _cs = event_state(client)
        _hw = _hs.get("lastWalk") or {}; _cw = _cs.get("lastWalk") or {}
        print("[wait_walk_settled TIMEOUT] prev_action_id=%s" % prev_action_id, flush=True)
        for _nm, _es, _lw in (("host", _hs, _hw), ("client", _cs, _cw)):
            print("  [%s] ok=%s lastSeqApplied=%s lastSeqEmitted=%s queueDepth=%s "
                  "lastWalk{actionId=%s active=%s restate=%s steps=%s}"
                  % (_nm, _es.get("ok"), _es.get("lastSeqApplied"), _es.get("lastSeqEmitted"),
                     _es.get("queueDepth"), _lw.get("actionId"), _lw.get("active"),
                     bool(_lw.get("restate")), len(_lw.get("steps") or [])), flush=True)
        _unmet = []
        if not _hs.get("ok"): _unmet.append("host_not_ok")
        if not _cs.get("ok"): _unmet.append("client_not_ok")
        if _hw.get("actionId", 0) == prev_action_id: _unmet.append("host_no_new_walk(actionId==prev)")
        if _hw.get("active") is not False: _unmet.append("host_walk_still_active")
        if not _hw.get("restate"): _unmet.append("host_restate_missing")
        if _cs.get("lastSeqApplied", 0) != _hs.get("lastSeqEmitted", 0): _unmet.append("client_behind(lastSeqApplied<lastSeqEmitted)")
        if _cs.get("queueDepth") != 0: _unmet.append("client_queueDepth_stuck")
        if _hs.get("queueDepth") != 0: _unmet.append("host_queueDepth_stuck")
        print("  [wait_walk_settled] unmet sub-conditions: %s" % (_unmet or ["<none-race>"]), flush=True)
        raise


def send_walk(client, actor_id, dest, path=None, tu_basis=None, run=False,
              strafe=False, sneak=False):
    req = {"cmd": "battle_intent", "kind": "walk", "actor": actor_id,
           "dest": jpos(dest), "run": run, "strafe": strafe, "sneak": sneak}
    if path is not None:
        req["path"] = [jpos(p) for p in path]
    if tu_basis is not None:
        req["tuBasisOverride"] = tu_basis
    return client.cmd(req)


def walk_candidates(host, actor_id, lengths=(1, 2, 3)):
    """Contact-free, open-ground destinations across several radii, nearest
    radius first. Flat list of tiles."""
    actor = unit_of(host, actor_id)
    st = battle_state(host)
    occ = {pos_of(u) for u in st["units"] if not u.get("isOut")}
    out = []
    for radius in lengths:
        for _, dest in straight_runs(host, actor, occ, length=radius, st=st):
            out.append(dest[0])
    return out


def richest(host, ids, n=1, exclude=()):
    """The @a n client-owned units with the most TU left, excluding @a exclude.

    Actors are allocated by TU rather than by index because every phase that
    WALKS spends TU and an actor that runs dry fails exactly like a broken atom
    would ("no walk could be ordered"). Choosing dynamically keeps that fixture
    failure mode away from the assertions."""
    st = battle_state(host)
    us = [u for u in st["units"] if u["id"] in ids and not u.get("isOut")
          and u["id"] not in exclude]
    us.sort(key=lambda u: -u["tu"])
    return [u["id"] for u in us[:n]]


def pick_and_walk(host, client, actor_id, what, lengths=(1, 2, 3), min_steps=1,
                  require_unhalted=True, rounds=3, min_alien_dist=MAX_VIEW_DISTANCE):
    """Order ONE walk for @a actor_id and settle it. Tries contact-free
    destinations at each radius in @a lengths, nearest radius first, and within a
    radius the destination FURTHEST from contact first; a candidate the
    pathfinder cannot route to simply ships nothing and the next is tried.

    WHY THIS EXISTS RATHER THAN "walk one tile north". At t=0 the squad is packed
    inside the Skyranger, so an actor's ADJACENT tiles are other soldiers and its
    straight lines run into the hull - a 3-tile open run is rejected by 15/15
    generations, and a 1-tile one just as often for the same reason. Pathfinding routes around
    both, and nothing this file asserts needs a path the harness predicted.

    @a min_alien_dist (default MAX_VIEW_DISTANCE; test_multistage.py's stage-2 walk
    passes 10) is the contact-free distance straight_runs() applies to every
    candidate's region.

    Returns (host lastWalk, client lastWalk) or None when nothing could be
    ordered."""
    last = None
    # ROUNDS, not one pass: a walk that lands but is too SHORT still MOVED the
    # actor, and the geometry that made it short - being packed inside the
    # Skyranger with nothing but hull and squadmates around - is exactly what the
    # move fixes. A second pass from the new position routinely succeeds where
    # the first could not (observed: an actor still in the craft had no routable
    # 2- or 3-tile destination at all).
    for _ in range(rounds):
        progressed = False
        for radius in lengths:
            actor = unit_of(host, actor_id)
            occ = {pos_of(u) for u in battle_state(host)["units"] if not u.get("isOut")}
            for _, dest in straight_runs(host, actor, occ, length=radius, min_alien_dist=min_alien_dist):
                prev = walk_action_id(host)
                resp = send_walk(client, actor_id, dest[0])
                if not resp.get("iseq"):
                    continue
                wait_walk_settled(host, client, prev)
                settle_reveal(host, client)
                hw, cw = last_walk(host), last_walk(client)
                last = (hw, cw)
                progressed = True
                halted = bool((hw.get("restate") or {}).get("halted"))
                if (len(hw.get("steps") or []) >= min_steps
                        and not (require_unhalted and halted)):
                    return hw, cw
                if halted:
                    # A REAL halt (almost always `no_tu` on a drained actor). Not
                    # a failure of the atom - a drained actor must halt -
                    # but the caller asked for a clean walk, so try a shorter plan.
                    print(f"    [{what}] a {len(hw['steps'])}-step walk HALTED "
                          f"({(hw.get('restate') or {}).get('reason')!r}); trying a "
                          "shorter plan")
        if not progressed:
            break
    return last if (last and not require_unhalted) else None


# ----- fixture bring-up ---------------------------------------------------


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]))


def tile_walkable(gc, t, occupied):
    """Cheap conservative screen for a STAGING tile: it exists, it has a floor,
    and nobody is standing on it. Pathfinding stays the real judge - a staging
    tile that survives this and yields no route is simply skipped."""
    if t in occupied:
        return False
    ti = gc.cmd({"cmd": "tile_info", "x": t[0], "y": t[1], "z": t[2]})
    if not ti.get("ok"):
        return False
    return ti.get("parts", {}).get("floor", {}).get("mapDataID", -1) >= 0


def staging_tiles(gc, near, far, occupied, self_pos=None):
    """EVERY tile from which a walk to @a far is a two-step crossing through the
    door: adjacent to `near`, exactly two steps from `far`, walkable, and free.

    A LIST, not a single tile, and that is the point. With only the
    first match, one actor parking on it makes the same door unusable for all six
    other soldiers - four of the seven rejections in one traced failing run were "no
    walkable staging tile", for a tile that existed and was simply occupied by
    the previous candidate. @a self_pos is excused from the occupancy test for
    the same reason: an actor standing on a staging tile IS staged.

    The two-step requirement is not decoration either: a neighbour of `near` that
    is also a DIAGONAL neighbour of `far` lets Pathfinding cut the corner and
    never touch the wall the door is in (observed as a one-step "routed WITHOUT
    crossing a door")."""
    dx, dy = near[0] - far[0], near[1] - far[1]
    ordered = [(near[0] + dx, near[1] + dy, near[2])]          # collinear first
    for ox in (-1, 0, 1):
        for oy in (-1, 0, 1):
            if ox or oy:
                ordered.append((near[0] + ox, near[1] + oy, near[2]))
    out = []
    for t in ordered:
        if t in (near, far) or t in out:
            continue
        if cheb(t, far) != 2:
            continue
        if t != self_pos and not tile_walkable(gc, t, occupied):
            continue
        out.append(t)
    return out


def wait_host_idle(host, client, timeout=30):
    """The host has NO action context open and NO live BState chain, and the
    client has caught up.

    `lastSeqApplied == lastSeqEmitted` ALONE IS NOT ENOUGH:
    a turn emits its `bt_ev` from UnitTurnBState and its `bt_action_end` from
    CoopArbiter::onChainQuiesced() one chain-unwind LATER, so the two counters
    are transiently EQUAL in the gap between them - and
    CoopArbiter::popActionContext() runs inside onChainQuiesced
    (connectionTCP.cpp:3737). Anything driven in that window inherits the
    previous action's actionId (a check that expects `actionId 0` then reads 3).
    `busyOwnerSeat == -1` on the HOST is
    the shipped predicate for BOTH halves at once:
    `!bg->isBusy() && currentActionId() == 0` (connectionTCP.cpp:4545-4551)."""
    client.wait_for("host idle (no action context, no BState chain), client caught up",
                    lambda: (event_state(host).get("busyOwnerSeat") == -1
                             and event_state(client).get("lastSeqApplied", 0)
                             == event_state(host).get("lastSeqEmitted", 0)
                             and event_state(client).get("queueDepth") == 0
                             and event_state(host).get("queueDepth") == 0) or None,
                    timeout=timeout)


SEQ_BARRIER_KEYS = ("lastSeqEmitted", "lastSeqApplied", "queueDepth", "busyOwnerSeat", "desyncSeen", "phase")


def wait_seq_barrier(host, client, timeout=30):
    """wait_host_idle's predicate in TWO reads per poll instead of five - the CLIENT's
    event_state first, then the HOST's - passing when the host's busyOwnerSeat == -1, the client's
    lastSeqApplied == the host's lastSeqEmitted, and both queueDepth == 0.

    Order is the argument. The host's lastSeqEmitted only grows within a battle (CoopEmit::nextSeq is
    the one writer; CoopPump::reset re-zeroes it only at a battle reset), and the client can only apply
    a seq the host minted. So a client value read BEFORE the host value that equals it means the client
    had applied every ev the host emitted up to the LATER host read. The host read comes after a client
    round trip, so it runs in a later TestServer::pump than the caller's last host test command, after
    that frame's updateCoopTask (CoopReveal::flushQuiescent's standalone `reveal`).

    wait_host_idle's hazard (counters transiently equal between a turn's bt_ev and its bt_action_end)
    stays covered: busyOwnerSeat and lastSeqEmitted come from ONE host event_state (one main-thread
    TestServer::execute), and CoopArbiter pops the action context and emits its bt_action_end in the
    same onChainQuiesced call, so a host snapshot with no open context already counts that end.
    On timeout: raises with both machines' last values."""
    last = {}

    def settled():
        c = event_state(client)
        h = event_state(host)
        last["client"] = {k: c.get(k) for k in SEQ_BARRIER_KEYS}
        last["host"] = {k: h.get(k) for k in SEQ_BARRIER_KEYS}
        return (h.get("busyOwnerSeat") == -1
                and isinstance(c.get("lastSeqApplied"), int)
                and c.get("lastSeqApplied") == h.get("lastSeqEmitted")
                and c.get("queueDepth") == 0
                and h.get("queueDepth") == 0) or None

    try:
        client.wait_for("seq barrier (client read, then host read: host idle, client applied every "
                        "host ev, both queues empty)", settled, timeout=timeout)
    except TimeoutError as e:
        raise TimeoutError(f"{e}; last reads: client={last.get('client')} host={last.get('host')}") from None


def drive_to_battlescape(host, client, seated, mission=None, seat_count=8, pre_seat=None, pre_ok=None, seat_client=True):
    """repro_atom_walk.drive_to_battlescape plus the mission choice. Kept
    separate from the walk repro's copy so that file's own boot stays as it is.

    `pre_seat`: an optional `callable(host)` invoked
    right after the mission choice and before any `newbattle_seat_soldier`
    call - the window for `newbattle_craft`/
    `newbattle_race` (race must land AFTER mission, since cbxMissionChange
    rebuilds the race list, and BEFORE seating). Default None: nothing runs.

    `pre_ok`: an optional `callable(host)` invoked
    immediately BEFORE `newbattle_ok` - the window `hunt_seed.py` and the
    fixed-seed tests use to send `set_seed` right before the
    generator reads it. Default None: nothing runs.

    `seat_client`: when False, the seat-1
    seating loop below (and its own `len(soldier_ids) >= 2` guard) is
    skipped entirely - no `newbattle_seat_soldier` call is ever sent for
    the client seat - so a caller can bring up a battle with the client
    UNSEATED (a spectator: a connected seat with no live unit).
    Default True runs the seating loop."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not has_state(host, "LobbyMenu")) or None)
    assert top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={states_stripped(host)}"
    if mission:
        r = host.cmd({"cmd": "newbattle_mission", "type": mission})
        assert r.get("ok"), (
            f"FIXTURE: this build's NEW BATTLE screen does not offer {mission!r} "
            f"- offered: {r.get('missionTypes')}")

    if pre_seat is not None:
        pre_seat(host)

    soldier_ids = []
    if seat_client:
        for i in range(seat_count):
            r = host.cmd({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1, "index": i})
            if not r.get("ok"):
                break
            soldier_ids.append(r["soldierId"])
        assert len(soldier_ids) >= 2, (
            f"FIXTURE: newbattle_seat_soldier stamped only {len(soldier_ids)} soldier(s) "
            "to seat 1 - this repro needs client-owned actors to walk")
    seated["soldierIds"] = soldier_ids

    if pre_ok is not None:
        pre_ok(host)
    host.ok({"cmd": "newbattle_ok"})
    # the steps above are bring_up_to_briefings()'s (with this helper's
    # mission / pre_seat / seat_client options); the rest is the shared entry spine.
    briefings_to_battlescape(host, client)


def bring_up_to_briefings(host, client, seated, seat_count=2, pre_ok=None, pre_newbattle=None):
    """drive_to_battlescape's
    steps through `newbattle_ok` - NEW BATTLE from the lobby, `seat_count` soldiers
    seated to seat 1 (the client), `pre_ok(host)`, `pre_newbattle(host, client)`,
    `newbattle_ok` - then a wait for the HOST's BriefingState ONLY. Returns with the
    host's briefing up and closes nothing. Whether and when the CLIENT's briefing
    appears (both briefings are up at once) is the caller's business (the pre-battle
    equip tests assert it).

    `pre_ok`: an optional `callable(host)` invoked immediately before `newbattle_ok`
    (drive_to_battlescape's window: the pinned map seed, the turn mode).
    `pre_newbattle`: an optional `callable(host, client)` invoked right after `pre_ok`,
    immediately before `newbattle_ok` - the window for a CLIENT-side test hook that
    must be armed before the host's offer (`hold_battle_ready`).
    Fills seated["soldierIds"] (the seated soldiers' ids, in seating order)."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not has_state(host, "LobbyMenu")) or None)
    assert top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={states_stripped(host)}"
    soldier_ids = []
    for i in range(seat_count):
        r = host.cmd({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1, "index": i})
        if not r.get("ok"):
            break
        soldier_ids.append(r["soldierId"])
    assert len(soldier_ids) == seat_count, (
        f"FIXTURE: newbattle_seat_soldier stamped {len(soldier_ids)} soldier(s) to seat 1 "
        f"(want {seat_count})")
    seated["soldierIds"] = soldier_ids
    if pre_ok is not None:
        pre_ok(host)
    if pre_newbattle is not None:
        pre_newbattle(host, client)
    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: has_state(host, "BriefingState"),
                  timeout=60)


def briefings_to_battlescape(host, client):
    """THE battle-entry spine every
    skirmish bring-up runs after `newbattle_ok` (drive_to_battlescape() and the
    local copies of it). The host's offer goes out at PREPARE, so
    both briefings are up at once; after its briefing each player lands
    on the pre-battle equip screen for its own soldiers; OK there is a
    ready toggle and turn 1 starts when every seat with something to equip is
    ready; the client then sees vanilla's Turn-1 screen too.

    Steps: the host's BriefingState -> the client's BriefingState (<= 90 s) ->
    the host's briefing OK -> dismiss_client_briefing(client) ->
    equip_both_ready() -> the host's Turn-1 screen -> the client's. Returns with
    turn 1 on both machines and BattlescapeState on top of both stacks."""
    host.wait_for("host briefing", lambda: has_state(host, "BriefingState"),
                  timeout=60)
    client.wait_for("client entry briefing (both briefings at once)",
                    lambda: has_state(client, "BriefingState") or None, timeout=90)
    host.ok({"cmd": "click_widget", "match": "ok"})
    dismiss_client_briefing(client)
    equip_both_ready(host, client)
    dismiss_battle_start_overlays(host)
    dismiss_battle_start_overlays(client)


def equip_both_ready(host, client, timeout=90):
    """pass both pre-battle
    equip screens. Each machine whose top state is an InventoryState gets ONE
    `battle_inventory {action: ok}` - the idempotent ready command (it only SETS
    this seat's ready, a no-op when it already is), never ESC. The client's
    screen appears only once its briefing has closed and its equip entry has run,
    and a machine with nothing to equip (a spectator, the PvP alien seat) never
    shows one, so the loop presses each screen when it appears. Returns once
    `battle_state.turn` is 1 on both machines and neither stack holds an
    InventoryState (the barrier closed both screens). Prints one line: which
    machine pressed, each seat's `equip.counted` flag on the host, the wall."""
    t0 = time.time()
    pressed = {}

    def step():
        for tag, gc in (("host", host), ("client", client)):
            if tag in pressed:
                continue
            st = states(gc)
            if st and "InventoryState" in st[-1]:
                r = gc.cmd({"cmd": "battle_inventory", "action": "ok"})
                if r.get("error") == "no InventoryState on stack":
                    continue  # the barrier closed it between the stack read and the press
                assert r.get("ok") and r.get("preBattle") is True, (
                    f"{tag}: the InventoryState on top is not the pre-battle equip screen with the equip "
                    f"phase open (battle_inventory ok -> {r}); stack={states(gc)}")
                pressed[tag] = "noop" if r.get("noop") else "ready"
        if any("InventoryState" in s for gc in (host, client) for s in states(gc)):
            return None
        return (battle_state(host).get("turn") == 1 and battle_state(client).get("turn") == 1) or None

    host.wait_for("both pre-battle equip screens ready and closed, turn 1 on both machines", step,
                  timeout=timeout, interval=0.1)
    counted = (event_state(host).get("equip") or {}).get("counted")
    print(f"[equip_both_ready] pressed={pressed} host equip.counted={counted} "
          f"wall={time.time() - t0:.2f}s", flush=True)


# ===== campaign co-op battle entry, client-owned units =====
#
# Two campaign bring-ups (SEPARATE guest battle, SHARED mixed-owner
# battle) plus the briefing-ordering drain they both need, and the common tail
# (assert_control_split / assert_seat_commands / assert_battle_exit) their scenarios assert after it.
# Imported by test_coop_separate_guest_battle.py, test_shared_battle.py,
# test_shared_soldier_ownership_battle.py and the other campaign battle tests.


def drain_host_coop_notice(host, rounds=15):
    """A guest transfer/visit pops an items-received CoopState over the host
    geoscape that freezes the sim. Pop only such notices (never a wait/merge
    dialog - those are gone by the time this runs) so the craft can fly.
    At most `rounds` presses."""
    for _ in range(rounds):
        top = states(host)[-1]
        if "GeoscapeState" in top:
            return
        if "CoopState" in top:
            host.cmd({"cmd": "coop_dialog_back"})
        else:
            host.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.4)


def drain_host_coop_notice_staged(host, rounds=15):
    """drain_host_coop_notice's presses (a CoopState notice gets coop_dialog_back, any other popup
    dismiss_popup, until GeoscapeState is on top; the same bound and the same silent return), with its fixed 0.4 s pause
    after each press replaced by a bounded wait (<= 0.4 s, 0.02 s polls) for the host's stack to change. The guest
    transfer's notice (CoopState 150 "Items received") closes on the first press."""
    for _ in range(rounds):
        st = states(host)
        if "GeoscapeState" in st[-1]:
            return
        if "CoopState" in st[-1]:
            host.cmd({"cmd": "coop_dialog_back"})
        else:
            host.cmd({"cmd": "dismiss_popup"})
        until = time.time() + 0.4
        while time.time() < until and states(host) == st:
            time.sleep(0.02)


def drive_both_to_tactical(host, client, timeout=240):
    """Close both briefings
    in ANY order - the host sends the client offer at PREPARE, so
    both briefings are up at once - and drain both machines through Briefing/
    Inventory/CoopState popups until BOTH machines sit on BattlescapeState. The
    pre-battle equip screens' `battle_inventory ok` is the idempotent ready
    command, so pressing it every second never flaps a seat's ready;
    turn 1 starts once every seat is ready.

    A campaign bring-up that settles ONE machine at a time hangs: the host's
    equip screen waits for the client's ready. Driving both machines in one loop
    is the ordering every campaign battle-entry fixture here (the
    SEPARATE guest battle, the SHARED mixed battle) needs. Returns True once both machines are on
    BattlescapeState, False on timeout (the caller raises with both machines'
    top states, which names the fixture problem instead of hanging silently)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        done = True
        seen = []
        for gc in (host, client):
            st = states(gc)
            seen.append(st)
            top = st[-1] if st else ""
            if "BattlescapeState" in top:
                continue
            done = False
            if "BriefingState" in top:
                gc.cmd({"cmd": "close_briefing"})
            elif "InventoryState" in top:
                gc.cmd({"cmd": "battle_inventory", "action": "ok"})
            elif "CoopState" in top:
                gc.cmd({"cmd": "coop_dialog_back"})
            else:
                gc.cmd({"cmd": "dismiss_popup"})
        if done:
            # settle the coop-init handshake a couple ticks (at most three rounds).
            for _ in range(3):
                moved = False
                for gc in (host, client):
                    st = states(gc)
                    if not st or "BattlescapeState" not in st[-1]:
                        gc.cmd({"cmd": "dismiss_popup"})
                        moved = True
                time.sleep(1.0)
                if not moved:
                    break
            return True
        # the next round once either stack moves from what this round saw (a press landed or the
        # partner moved on), at most 1.0 s
        _wait_stacks_change((host, client), seen, 1.0)
    return False


def _campaign_base0(gc):
    """The real (non-coop-mirror) base from geo_state - the shape
    test_shared_battle.py/test_shared_landing.py's own `_base0` uses."""
    for b in gc.ok({"cmd": "geo_state"})["bases"]:
        if not b.get("coopBase") and not b.get("coopIcon"):
            return b
    raise AssertionError("no real base")


def _campaign_skyranger(gc):
    for c in _campaign_base0(gc)["crafts"]:
        if "SKYRANGER" in c["type"]:
            return c
    raise AssertionError("no skyranger")


def _campaign_own_roster_base(gc):
    """The real base from get_soldiers (it carries `soldiers`, unlike
    geo_state's `_campaign_base0`)."""
    for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
        if not b["coopBaseFlag"] and not b.get("coopIcon") and b["soldiers"]:
            return b
    raise AssertionError("no real base with soldiers")


def wait_back_on_geoscape(gc, what="back on geoscape", timeout=60):
    """After `leave_base` from a peer's base, wait until THIS machine is back on its OWN world.
    BasescapeState::btnGeoscapeClick clears insideCoopBase BEFORE it pushes the LoadGameState that reloads the own world
    (~10 frames later), so the flag alone can read "back" while the visited copy is still live. Ready = insideCoopBase false
    AND top state GeoscapeState AND no LoadGameState on the stack. Bounded: a timeout raises with what it last saw."""
    seen = {}

    def ready():
        seen["insideCoopBase"] = gc.cmd({"cmd": "get_coop"}).get("insideCoopBase")
        seen["stack"] = states_stripped(gc)
        st = seen["stack"]
        if seen["insideCoopBase"] or not st or st[-1] != "GeoscapeState" or any("LoadGameState" in s for s in st):
            return None
        return st

    try:
        return gc.wait_for(what, ready, timeout=timeout)
    except TimeoutError as e:
        raise TimeoutError(f"{gc.name}: {what}: not back on its own geoscape within {timeout} s (want insideCoopBase "
                           f"false, top GeoscapeState, no LoadGameState): insideCoopBase={seen.get('insideCoopBase')!r} "
                           f"stack={seen.get('stack')!r}") from e


def wait_peer_base_shown(gc, base_name, timeout=30):
    """Wait (bounded) until the partner's base `base_name` is on this machine's geoscape: the base visit_coop_base looks
    for (a co-op base with that name; any co-op base when base_name is empty). A partner's base marker is never saved, so a
    world this machine has just loaded (back from a visit to a partner's base, from a battle, a rejoin, a new session) has
    none until the partner sends its base list again (its answer to the base request the geoscape sends on init). Call it
    before visit_coop_base or before reading the marker for a real click. Returns the base; a timeout raises with the bases
    this machine last listed."""
    seen = {}

    def shown():
        bases = gc.cmd({"cmd": "get_soldiers"}).get("bases") or []
        seen["bases"] = [(b.get("name"), b.get("coopBaseFlag"), b.get("coopIcon")) for b in bases]
        return next((b for b in bases if (b.get("coopBaseFlag") or b.get("coopIcon"))
                     and (not base_name or b.get("name") == base_name)), None)

    try:
        return gc.wait_for("%s on the geoscape" % (base_name or "a partner base"), shown, timeout=timeout)
    except TimeoutError as e:
        raise TimeoutError("%s: partner base %r not on this machine's geoscape within %s s; bases (name, coopBase, "
                           "coopIcon): %r" % (gc.name, base_name, timeout, seen.get("bases"))) from e


def press_back_when_shown(gc, what, codes=None, timeout=60):
    """press the top co-op dialog's BEGIN / RESUME / OK only once a player could: wait
    (bounded) until the top state is a CoopState whose back button coop_dialog_info reports shown (and whose code is in
    `codes` when given), then press it. A host wait dialog (60 / 62) shows its button up to 0.5 s after it is ready
    (CoopState.cpp :1111-1117, :1199-1213). A timeout raises with the dialog and the stack. Returns the press reply."""
    seen = {}

    def shown():
        seen["stack"] = states_stripped(gc)
        seen["dialog"] = gc.cmd({"cmd": "coop_dialog_info"})
        d = seen["dialog"]
        if not seen["stack"] or seen["stack"][-1] != "CoopState" or d.get("backVisible") is not True:
            return None
        if codes is not None and d.get("code") not in codes:
            return None
        return d

    try:
        gc.wait_for(what, shown, timeout=timeout)
    except TimeoutError as e:
        d = seen.get("dialog") or {}
        raise TimeoutError(f"{gc.name}: {what}: no shown co-op dialog button within {timeout} s: code={d.get('code')!r} "
                           f"backVisible={d.get('backVisible')!r} title={d.get('title')!r} "
                           f"stack={seen.get('stack')!r}") from e
    return gc.ok({"cmd": "coop_dialog_back"})


def _wait_skyranger_crew(host, client, base_name, craft_id, want, what, timeout=30):
    """Wait until the Skyranger @a craft_id of @a base_name carries exactly the soldier ids
    @a want on both machines. A timeout raises with the crew each machine last showed."""
    want = sorted(want)
    seen = {}

    def crew(gc):
        for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
            if b["name"] == base_name:
                return sorted(s["id"] for s in b["soldiers"]
                              if s.get("craft") == "STR_SKYRANGER" and s.get("craftId") == craft_id)
        return None

    for gc, label in ((host, "host"), (client, "client")):
        try:
            gc.wait_for(f"{what} ({label})",
                        lambda gc=gc, label=label: seen.__setitem__(label, crew(gc)) or (seen[label] == want or None),
                        timeout=timeout, interval=0.1)
        except Exception as e:
            raise AssertionError(f"{what}: {label} crew {seen.get(label)}, want {want}") from e


def assemble_separate_guest_squad(host, client):
    """The squad of the Separate guest battle, in the one shared world: 3 of the host's
    soldiers on the host's Skyranger plus the client's "Guest Zzz", transferred to
    the host's base and seated there by the client. Returns (host base name,
    Skyranger id, host squad ids, guest id); both machines show the crew."""
    hb = _campaign_own_roster_base(host)
    host_base_name = hb["name"]
    cid = _campaign_skyranger(host)["id"]
    rh = sorted(s["id"] for s in hb["soldiers"])
    # A Separate craft_assign is a command the host's game applies to the one
    # world a moment later, so its reply cannot show the seat yet: wait for the
    # crew on both machines.
    for sid in rh:
        host.ok({"cmd": "craft_assign", "base": host_base_name, "craft_id": cid,
                 "craft_type": "STR_SKYRANGER", "soldier_id": sid, "on": False})
    host_squad = rh[:3]
    for sid in host_squad:
        host.ok({"cmd": "craft_assign", "base": host_base_name, "craft_id": cid,
                 "craft_type": "STR_SKYRANGER", "soldier_id": sid, "on": True})
    _wait_skyranger_crew(host, client, host_base_name, cid, host_squad, "host squad seated")

    cb = _campaign_own_roster_base(client)
    spare = next(s for s in cb["soldiers"] if not s.get("craft"))["id"]
    # Both players' starting rosters roll the same names, so the spare is renamed
    # by id, through the client's own soldier screen.
    client.ok({"cmd": "soldier_rename", "soldierId": spare, "name": "Guest Zzz"})

    def renamed(gc):
        return any(s["id"] == spare and s["name"] == "Guest Zzz"
                   for b in gc.ok({"cmd": "get_soldiers"})["bases"] for s in b["soldiers"]) or None

    for gc in (client, host):
        gc.wait_for(f"guest renamed ({gc.name})", lambda gc=gc: renamed(gc), timeout=30, interval=0.1)
    tr = client.ok({"cmd": "transfer_to_coop_base", "name": "Guest", "toBase": host_base_name})
    assert tr.get("transferred"), f"guest transfer failed: {tr}"
    for gc in (host, client):
        gc.wait_for("guest transfer en route",
                    lambda gc=gc: (gc.ok({"cmd": "incoming_transfers",
                                          "base": host_base_name})["soldiers"] == 1) or None,
                    timeout=30, interval=0.1)
    # The host's game lands the transfer; the arrival rows it reports are the
    # host player's own, so the client's soldier is not among them.
    arrived = host.ok({"cmd": "force_transfer_arrivals", "base": host_base_name})
    assert arrived["remaining"] == 0, arrived
    # The arrival notice opens on the client, the soldier's owner, once the
    # host's alert reaches it; it holds the shared clock until it is closed.
    client.wait_for("the guest's arrival notice on the client",
                    lambda: has_state(client, "ItemsArrivingState") or None, timeout=30, interval=0.1)
    drain_host_coop_notice_staged(client)

    def guest_at_host_base(gc):
        for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
            if b["name"] == host_base_name:
                return next((s for s in b["soldiers"] if s["name"] == "Guest Zzz"), None)
        return None

    guest = host.wait_for("guest arrived at the host base", lambda: guest_at_host_base(host),
                          timeout=30, interval=0.1)
    guest_id = guest["id"]
    client.wait_for("guest arrived at the host base on the client", lambda: guest_at_host_base(client),
                    timeout=30, interval=0.1)
    client.ok({"cmd": "craft_assign", "base": host_base_name, "craft_id": cid,
               "craft_type": "STR_SKYRANGER", "soldier_id": guest_id, "on": True})
    _wait_skyranger_crew(host, client, host_base_name, cid, host_squad + [guest_id], "guest seated")
    print(f"squad assembled: host soldiers {host_squad} (coop==0) + client guest "
          f"{guest_id} (coop==1)")
    return host_base_name, cid, host_squad, guest_id


def bring_up_separate_guest_battle(host, client, port="47900", pre_mission_start=None, pre_landing=None, staged=True):
    """The SEPARATE guest battle fixture: SEPARATE campaign (one world), mixed-ownership
    squad - 3 of the host's own soldiers plus a CLIENT guest seated on the host's
    craft (the client's spare soldier is renamed "Guest Zzz", the client transfers
    it to the host's base, the host's game lands the transfer, and the client seats
    it on the host's Skyranger) - flown to a fresh terror site and entered LIVE via
    coop_mission_start.

    `pre_mission_start`: an optional `callable(host,
    client)` invoked right after the squad is assembled (guest seated, client
    back on the geoscape) and BEFORE `drain_host_coop_notice`/
    `spawn_mission_site`/`coop_mission_start` - the window
    test_coop_separate_guest_battle.py's vacuity guard needs
    (`event_state.guestContrib` must show the roster travelled
    BEFORE the battle starts). Default None, nothing runs.

    `pre_landing`: an
    optional `callable(host, client)` run right before `coop_mission_start`
    (e.g. the host's `set_seed` map seed). Default None, nothing runs.

    `staged` (default True): the same squad set-up (rename, transfer, visit, seat, soldiers
    OK, leave: the product's own sync, unchanged) and the same entry; only the flight is staged. The host's notice is
    drained without the fixed 0.4 s pauses (drain_host_coop_notice_staged) and `craft_force` starts the craft AT the
    site, so the host's next 5-second geoscape step lands it (MovingTarget::move), instead of 0.01 rad away: in
    co-op the clock runs fast only when both machines pick the same speed, so that flight took ~32 five-second steps
    (~2.5 s) behind the host's geo_set_speed. The landing prompt is polled every 0.05 s with no geo_set_speed (a press
    after the arrival's own speed reset leaves the host at speed 2). At the landing prompt both
    machines hold the same values as the slow path except the geoscape clock (about 3 game minutes earlier). A caller
    whose checks read the flight, the notice, the clock or the landing prompt passes staged=False (the full flight).

    Returns (host_squad, guest_id): host_squad is the 3 host soldier ids
    (coop==0 in battle); guest_id is the soldier id of "Guest Zzz" (the same on
    both machines in one world). Callers identify the guest's battle unit by
    name."""
    new_campaign(host, client, port=port)

    host_base_name, cid, host_squad, guest_id = assemble_separate_guest_squad(host, client)

    if pre_mission_start is not None:
        pre_mission_start(host, client)

    # One world: a popup on either machine holds the shared clock, so both are
    # cleared.
    for gc in (host, client):
        if staged:
            drain_host_coop_notice_staged(gc)
        else:
            drain_host_coop_notice(gc)
    b0 = _campaign_base0(host)
    site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                    "deployment": "STR_TERROR_MISSION", "lon": b0["lon"] + 0.35,
                    "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})
    site_id = site["site_id"]
    host.wait_for(
        "site on host",
        lambda: any(s["id"] == site_id
                    for s in host.ok({"cmd": "geo_state"})["missionSites"]) or None,
        timeout=30)
    if staged:
        at = next(s for s in host.ok({"cmd": "geo_state"})["missionSites"] if s["id"] == site_id)
        lon, lat = at["lon"], at["lat"]
    else:
        lon, lat = b0["lon"] + 0.34, b0["lat"] + 0.10
    host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
             "lon": lon, "lat": lat, "dest": f"site:{site_id}",
             "fuel": 999999, "lowFuel": False})

    def landing_prompt():
        if has_state(host, "ConfirmLandingState"):
            return True
        top = states(host)[-1]
        if "CoopState" in top:
            host.cmd({"cmd": "coop_dialog_back"})
        elif "GeoscapeState" not in top:
            # The prompt can appear between the two reads above: keep it.
            host.cmd({"cmd": "dismiss_popup", "keep": ["ConfirmLandingState"]})
        if not staged:
            host.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None

    host.wait_for("host landing prompt", landing_prompt, timeout=120, interval=0.05 if staged else 0.5)
    if pre_landing is not None:
        pre_landing(host, client)
    ms = host.ok({"cmd": "coop_mission_start"})
    print(f"coop_mission_start -> {ms}")
    host.wait_for("host entered", lambda: battle_state(host).get("inBattle") or None,
                  timeout=120, interval=1.0)
    host.wait_for("host briefing", lambda: has_state(host, "BriefingState"),
                  timeout=60, interval=0.5)
    if not drive_both_to_tactical(host, client):
        raise TimeoutError(
            "drive_both_to_tactical timed out (host=%s client=%s)"
            % (states(host)[-3:], states(client)[-3:]))
    print("both machines reached the battlescape (live SEPARATE coop battle)")
    _stage_guest_step(host, client)
    return host_squad, guest_id


def _stage_guest_step(host, client, radius=4):
    """A Separate craft deploys its crew alternating owners (host, client, host,
    host), so the guest takes the second place, on the Skyranger's closed front
    row, where no neighbouring tile is open. Callers step the guest one tile, so
    when it has no open neighbour it is placed on both machines (hashes checked)
    on the nearest open tile that has an open neighbour, keeping its facing."""
    st = battle_state(host)
    units = [u for u in st.get("units", []) if not u.get("isOut")]
    guest = next(u for u in units if "Guest" in (u.get("name") or ""))
    try:
        _adjacent_free_tile(host, guest)
        return
    except AssertionError:
        pass
    occ = {pos_of(u) for u in units if u["id"] != guest["id"]}
    x, y, z = pos_of(guest)
    near = sorted(((x + dx, y + dy, z) for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1)
                   if (dx, dy) != (0, 0)), key=lambda t: (max(abs(t[0] - x), abs(t[1] - y)), t[1], t[0]))
    for t in near:
        if not tile_walkable(host, t, occ):
            continue
        if any(tile_walkable(host, (t[0] + DIR_DX[d], t[1] + DIR_DY[d], z), occ | {t})
               for d in range(8) if (t[0] + DIR_DX[d], t[1] + DIR_DY[d], z) != (x, y, z)):
            place_deterministic(host, client, [
                {"cmd": "battle_teleport_unit", "unit": guest["id"], "x": t[0], "y": t[1], "z": t[2],
                 "dir": guest.get("direction", 0)}], what=f"guest {guest['id']} to an open tile")
            print(f"guest {guest['id']} placed from {(x, y, z)} to {t} (no open neighbour at its deployment tile)")
            return
    raise AssertionError(f"FIXTURE: no open tile with an open neighbour within {radius} of the guest at {(x, y, z)}")


def bring_up_shared_mixed_battle(js, owners, to_tactical=True, pre_landing=None):
    """The SHARED mixed-owner battle fixture core: given an already-brought-up SHARED
    session (`shared_fixture.bring_up`), board a 2-soldier squad on the shared
    craft with per-slot ownership from `owners`, fly it to a fresh terror
    site, and enter the battle LIVE via confirm_landing with both machines
    driven together (drive_both_to_tactical, never a bare inBattle wait).

    Parameterised by `owners` so test_shared_battle.py's `mixed`/`solo_client`
    scenarios and test_shared_soldier_ownership_battle.py's bootstrap-owner
    scenario can share one bring-up:

      owners  {0: seat, 1: seat} - stamps the roster's first two soldiers
              (sorted by id) to these owners via set_soldier_owner, on BOTH
              machines, before boarding.
      owners  None - the squad's EXISTING (bootstrap) owners are used
              unchanged, no set_soldier_owner call at all - the bootstrap-owner
              scenario's precondition ("no set_soldier_owner; the bootstrap split
              supplies one seat-0 and one seat-1 soldier").

    Returns (host, client, squad) - squad the 2 boarded soldier ids, sorted by
    id (squad[0]/squad[1] match `owners`' slot 0/1 when `owners` is given).

    `to_tactical` (default True: drive both machines to the battle): False
    returns right after the HOST's
    BriefingState is up, before drive_both_to_tactical - the caller runs the
    battle-entry spine (both briefings, then both pre-battle equip screens) itself.

    `pre_landing`: an optional `callable(host,
    client)` run right before `confirm_landing`. Default None, nothing runs."""
    host, client = js.host, js.client

    def _roster(gc):
        out = []
        for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
            out.extend(b["soldiers"])
        return out

    b0 = _campaign_base0(host)
    blon, blat = b0["lon"], b0["lat"]
    cid = _campaign_skyranger(host)["id"]
    rh = sorted(s["id"] for s in _roster(host))
    squad = [rh[0], rh[1]]

    if owners is not None:
        for gc in (host, client):
            for slot, sid in enumerate(squad):
                gc.ok({"cmd": "set_soldier_owner", "soldier_id": sid, "owner": owners[slot]})

    for sid in rh:
        host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False})
    for sid in squad:
        host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})

    def _aboard(gc):
        return sorted(s["id"] for s in _roster(gc) if s["craftId"] == cid)

    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} squad aboard",
                    lambda gc=gc: (_aboard(gc) == sorted(squad)) or None,
                    timeout=40, interval=0.5)
    print(f"squad {squad} aboard shared craft {cid}")

    site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                    "deployment": "STR_TERROR_MISSION", "lon": blon + 0.35,
                    "lat": blat + 0.10, "race": "STR_SECTOID", "hours": 240})
    site_id = site["site_id"]
    host.wait_for(
        "site on host",
        lambda: any(s["id"] == site_id
                    for s in host.ok({"cmd": "geo_state"})["missionSites"]) or None,
        timeout=30)
    host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
             "lon": blon + 0.34, "lat": blat + 0.10, "dest": f"site:{site_id}",
             "fuel": 999999, "lowFuel": False})

    def _landing_prompt():
        if has_state(host, "ConfirmLandingState"):
            return True
        host.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None

    host.wait_for("ConfirmLandingState on host", _landing_prompt, timeout=90, interval=0.5)
    if pre_landing is not None:
        pre_landing(host, client)
    host.ok({"cmd": "confirm_landing"})
    host.wait_for("host entered", lambda: battle_state(host).get("inBattle") or None,
                  timeout=180, interval=1.0)
    host.wait_for("host briefing", lambda: has_state(host, "BriefingState") or None,
                  timeout=60, interval=0.5)
    if not to_tactical:
        print("the host's briefing is up (live SHARED coop battle, stopped before tactical)")
        return host, client, squad
    if not drive_both_to_tactical(host, client):
        raise TimeoutError(
            "drive_both_to_tactical timed out (host=%s client=%s)"
            % (states(host)[-3:], states(client)[-3:]))
    print("both machines reached the battlescape (live SHARED coop battle)")
    return host, client, squad


# ---- the campaign battle common tail: control_split / seat_commands / battle_exit ----

def assert_control_split(host, client, expected_seat_by_soldier_id, what=""):
    """The common-tail check control_split, asserted on BOTH
    machines once both tops are BattlescapeState (after drive_both_to_
    tactical): phase Active; authority.hostSim true host / false client;
    authority.localSeat 0 host / 1 client; battleId equal non-zero; the set
    of isPlayerSoldier units' soldierId == expected_seat_by_soldier_id's keys;
    each such unit's coop == its expected seat; hash_now clean; the host log
    carries the battle_ready saveBlob EQUAL line."""
    tag = f" {what}" if what else ""
    battle_ids = {}
    for gc, tag2, want_hostsim, want_localseat in (
            (host, "host", True, 0), (client, "client", False, 1)):
        bs = battle_state(gc)
        assert bs.get("phase") == "Active", (
            f"control_split{tag}: {tag2} phase={bs.get('phase')!r}, want 'Active'")
        auth = bs.get("authority", {})
        assert auth.get("hostSim") == want_hostsim, (
            f"control_split{tag}: {tag2} authority.hostSim={auth.get('hostSim')!r}, "
            f"want {want_hostsim}")
        assert auth.get("localSeat") == want_localseat, (
            f"control_split{tag}: {tag2} authority.localSeat={auth.get('localSeat')!r}, "
            f"want {want_localseat}")
        bid = auth.get("battleId")
        assert bid, f"control_split{tag}: {tag2} authority.battleId is falsy: {bid!r}"
        battle_ids[tag2] = bid
        got = {u["soldierId"]: u["coop"] for u in bs.get("units", [])
               if u.get("isPlayerSoldier")}
        assert set(got) == set(expected_seat_by_soldier_id), (
            f"control_split{tag}: {tag2} isPlayerSoldier roster {sorted(got)} != "
            f"expected {sorted(expected_seat_by_soldier_id)}")
        bad = {sid: (got[sid], seat) for sid, seat in expected_seat_by_soldier_id.items()
               if got[sid] != seat}
        assert not bad, (
            f"control_split{tag}: {tag2} seat mismatch (soldierId: (got, want)) = {bad}")
    assert battle_ids["host"] == battle_ids["client"], (
        f"control_split{tag}: battleId differs host={battle_ids['host']} "
        f"client={battle_ids['client']}")
    assert_hash_clean(host, client, full=True, what=f"control_split{tag}")

    lines = []
    logp = os.path.join(host.user_dir, "openxcom.log")
    if os.path.exists(logp):
        with open(logp, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    equal_lines = [ln.rstrip("\n") for ln in lines if "battle_ready saveBlob EQUAL" in ln]
    mismatch_lines = [ln.rstrip("\n") for ln in lines if "battle_ready saveBlob MISMATCH" in ln]
    assert not mismatch_lines, (
        f"control_split{tag}: host log carries a 'battle_ready saveBlob MISMATCH' line: "
        f"{mismatch_lines[-1]}")
    assert equal_lines, (
        f"control_split{tag}: host log never logged 'battle_ready saveBlob EQUAL'")
    print(f"PASS control_split{tag}: roster {sorted(expected_seat_by_soldier_id)} at "
          f"expected seats on both machines, hash clean, {equal_lines[-1]}")


def _adjacent_free_tile(gc, unit):
    """ONE adjacent (Chebyshev distance 1) tile with a floor and no unit on
    it - seat_commands needs only a single admitted step, never a search/backtrack
    beyond the 8 immediate neighbours."""
    st = battle_state(gc)
    occ = {pos_of(u) for u in st.get("units", []) if not u.get("isOut")}
    x, y, z = pos_of(unit)
    for d in range(8):
        t = (x + DIR_DX[d], y + DIR_DY[d], z)
        if t in occ:
            continue
        # `occ` holds anchor tiles only; a multi-tile unit (a 2x2 tank)
        # also covers other tiles, which tile_info reports as its `unit` - skip those too.
        if gc.cmd({"cmd": "tile_info", "x": t[0], "y": t[1], "z": t[2]}).get("unit", -1) != -1:
            continue
        if tile_walkable(gc, t, occ):
            return t
    raise AssertionError(
        f"FIXTURE: seat_commands: unit {unit['id']} at {(x, y, z)} has no free adjacent "
        f"tile (occupied={sorted(occ)})")


def _dir_to(a, b):
    """OpenXcom direction 0..7 from tile a to an ADJACENT tile b (the inverse of
    DIR_DX/DIR_DY)."""
    dx = (b[0] > a[0]) - (b[0] < a[0])
    dy = (b[1] > a[1]) - (b[1] < a[1])
    for d in range(8):
        if DIR_DX[d] == dx and DIR_DY[d] == dy:
            return d
    raise AssertionError(f"_dir_to: {tuple(a)}->{tuple(b)} is not a single-tile step")


def _octant_chain(from_dir, to_dir):
    """The successive SINGLE-OCTANT facings from from_dir to to_dir along the
    shortest rotation (CW if diff<=4 else CCW), ending at to_dir; empty if already
    facing it. a MULTI-octant turn aborts on a newly-spotted enemy, but each
    single-octant turn always lands its one octant (the abort cancels only the
    REST), so chaining reaches any facing deterministically with default movement."""
    diff = (to_dir - from_dir) % 8
    if diff == 0:
        return []
    step = 1 if diff <= 4 else -1
    seq = []
    d = from_dir
    while d != to_dir:
        d = (d + step) % 8
        seq.append(d)
    return seq


def send_turn(client, actor_id, to_dir):
    """a STANDALONE single-octant turn intent."""
    return client.cmd({"cmd": "battle_intent", "kind": "turn", "actor": actor_id,
                       "toDir": to_dir})


def wait_turn_settled(host, client, baseline, timeout=15):
    """Settle a TURN intent (turns do not update lastWalk, so - like repro_atom_turn's
    turn_to - this settles on the seq stream: a NEW ev has been applied on the client
    past `baseline` (captured BEFORE the turn) and both queues have drained;
    baseline-guarded so it cannot return vacuously at rest)."""
    def settled():
        hs = event_state(host)
        cs = event_state(client)
        return bool(hs.get("ok") and cs.get("ok")
                    and hs.get("queueDepth") == 0 and cs.get("queueDepth") == 0
                    and cs.get("lastSeqApplied", 0) > baseline)
    client.wait_for("turn settled (new seq applied, queueDepth 0 on both machines)",
                    settled, timeout=timeout)


def _wait_click_ready(host, tx, ty, tz, actor_id, timeout=8.0):
    """render/hit-test readiness SYNC for a host map click.

    NOT a masking retry - it re-runs NO assertion; it establishes the precondition
    the SINGLE click that follows needs. inject_input pushes a bare SDL
    button event (no motion), so BattlescapeState::mapClick reads the stored
    selector that map_tile_click_pos left on the target tile - the tile resolution
    is deterministic. The intermittent (~1/6; masked by ANY added delay, a
    Heisenbug) miss was the click landing while the post-walk settle still had the
    map in a NON-clickable state, so mapClick SWALLOWED it at its own
    pre-primaryAction gate (BattlescapeState.cpp:1146/1150: `_mouseOverIcons` OR
    `cursorType == CT_NONE` OR `_battleGame->isBusy()`) - primaryAction never ran
    and no unit-select refusal fired. This polls those EXACT engine gate
    conditions (cursorType CT_NONE == 0, Map.h:45), plus a fresh map_tile_click_pos
    round-trip (so the stored selector is freshly on the tile and the actor is
    still there), and returns only once the map is genuinely clickable - held
    STABLE across two consecutive polls so a still-settling frame cannot slip
    through. Returns the freshly-verified (winX, winY) to click ONCE."""
    deadline = time.time() + timeout
    prev = None            # (winX, winY) from the previous READY poll, else None
    last = {}
    while time.time() < deadline:
        bs = battle_state(host)
        u = unit_of(host, actor_id)
        pr = host.cmd({"cmd": "map_tile_click_pos", "x": tx, "y": ty, "z": tz})
        last = {"pendingStates": bs.get("pendingStates"), "isBusy": bs.get("isBusy"),
                "mouseOverIcons": bs.get("mouseOverIcons"),
                "cursorType": bs.get("cursorType"), "verified": pr.get("verified"),
                "pos": pos_of(u)}
        ready = (bs.get("pendingStates", 1) == 0
                 and not bs.get("isBusy", True)
                 and not bs.get("mouseOverIcons", True)
                 and bs.get("cursorType", 0) != 0
                 and pr.get("verified")
                 and pos_of(u) == (tx, ty, tz))
        win = (pr.get("winX"), pr.get("winY")) if ready else None
        if ready and prev is not None and win == prev:
            return pr["winX"], pr["winY"]
        prev = win
        time.sleep(0.1)
    raise AssertionError(
        f"seat_commands host click target {(tx, ty, tz)} never became render-clickable "
        f"within {timeout}s (mapClick swallow gates never cleared stably); "
        f"last poll={last}")


def assert_seat_commands(host, client, seat1_actor_id, seat0_actor_id=None, host_check=True,
                 what=""):
    """The common-tail check seat_commands.

    1. The CLIENT sends `battle_intent` (walk, ONE absolute step onto an
       adjacent free tile - the test_client_gates/repro_atom_walk
       absolute-intent shape, no tile click) for its OWN seat-1 unit ->
       ADMITTED: lastDeny empty on the client, the unit's pos changed and
       EQUAL on both, hash clean.
    2. (seat0_actor_id given) The CLIENT sends the same shape of intent for a
       SEAT-0 unit it does not own -> lastDeny.reason == "not_your_unit" on
       the client, no pos change on either machine.
    3. (host_check True) The HOST's click-select on the seat-1 unit's tile is
       refused: the two-pass camera settle (test_feedback's
       pattern - a first settling pass, then a second pass
       asserted `centered is False`) verifies the click lands on the right
       tile; the refusal shows up in `battle_state.coopWaitText` (the
       STR_COOP_DENY_NOT_YOUR_UNIT, "Not one of your soldiers" -
       CoopBattleUi.h:322 / connectionTCP.cpp:8196 route EVERY coop message,
       including this one, through `_txtCoopWait` - never through vanilla
       `_warning`, which `battle_state.warningText` exposes instead;
       TestServer.cpp:7175 vs :7197 confirm the two are distinct probes), and
       `selectedId` is NOT that unit.
    """
    tag = f" {what}" if what else ""

    # ---- 1. ADMITTED: client turns (octant by octant, if needed) then walks ----
    actor = unit_of(client, seat1_actor_id)
    dest = _adjacent_free_tile(client, actor)
    before_h = pos_of(unit_of(host, seat1_actor_id))
    before_c = pos_of(actor)
    assert before_h == before_c, (
        f"seat_commands{tag}: seat-1 actor {seat1_actor_id} position differs before the "
        f"walk (host={before_h} client={before_c}) - not a clean starting point")

    # CHAINED SINGLE-OCTANT TURNS, THEN STEP. A 1-tile walk that
    # must turn - or a multi-octant turn - aborts at the octant a NEW enemy comes
    # into view (vanilla, UnitTurnBState.cpp:125-130), leaving the unit short (~1/6,
    # map-roll dependent). But each SINGLE-octant turn always lands its octant (the
    # abort cancels only the REST). Face `dest` one octant at a time, then the step
    # performs no turn and cannot spot-halt. Turning the client's OWN unit is
    # admitted (it also strengthens the ownership proof).
    to_dir = _dir_to(before_c, dest)
    chain = _octant_chain(actor.get("direction"), to_dir)
    for d in chain:
        base_t = event_state(client).get("lastSeqApplied", 0)
        rt = send_turn(client, seat1_actor_id, d)
        assert rt.get("iseq"), f"seat_commands{tag}: single-octant turn to {d} did not ship: {rt}"
        wait_turn_settled(host, client, base_t)
        ldt = event_state(client).get("lastDeny")
        assert not ldt, f"seat_commands{tag}: the client's OWN-unit turn to dir {d} was DENIED: {ldt}"
        dir_h = unit_of(host, seat1_actor_id).get("direction")
        dir_c = unit_of(client, seat1_actor_id).get("direction")
        assert dir_h == d and dir_c == d, (
            f"seat_commands{tag}: single-octant turn did not reach dir {d} (host={dir_h} client={dir_c})")
        assert dir_h == dir_c, (
            f"seat_commands{tag}: facing DIFFERS between machines after the octant turn to {d} "
            f"(host={dir_h} client={dir_c})")
        assert_hash_clean(host, client, full=True, what=f"seat_commands{tag} after octant turn to {d}")
    if chain:
        print(f"PASS seat_commands{tag}: client's own seat-1 unit {seat1_actor_id} faced dir {to_dir} "
              f"via {len(chain)} single-octant turn(s), EQUAL on both, hash clean")

    prev = walk_action_id(host)
    resp = send_walk(client, seat1_actor_id, dest)
    assert resp.get("iseq"), f"seat_commands{tag}: admitted walk did not ship at all: {resp}"
    wait_walk_settled(host, client, prev)
    ld = event_state(client).get("lastDeny")
    assert not ld, f"seat_commands{tag}: the client's OWN-unit walk was DENIED: {ld}"
    after_h = pos_of(unit_of(host, seat1_actor_id))
    after_c = pos_of(unit_of(client, seat1_actor_id))
    assert after_h == dest and after_c == dest, (
        f"seat_commands{tag}: seat-1 actor did not reach {dest} (host={after_h} "
        f"client={after_c})")
    assert after_h == after_c, (
        f"seat_commands{tag}: seat-1 actor position now DIFFERS between machines "
        f"(host={after_h} client={after_c})")
    assert_hash_clean(host, client, full=True, what=f"seat_commands{tag} after the admitted walk")
    print(f"PASS seat_commands{tag}: client's own seat-1 unit {seat1_actor_id} admitted "
          f"{before_c} -> {dest}, EQUAL on both, hash clean")

    # ---- 2. DENIED: client tries to command a seat-0 unit ------------------
    if seat0_actor_id is not None:
        before0_h = pos_of(unit_of(host, seat0_actor_id))
        before0_c = pos_of(unit_of(client, seat0_actor_id))
        dest0 = _adjacent_free_tile(host, unit_of(host, seat0_actor_id))
        resp0 = send_walk(client, seat0_actor_id, dest0)
        deadline = time.time() + 10
        ld0 = None
        while time.time() < deadline:
            ld0 = event_state(client).get("lastDeny")
            if ld0 and ld0.get("iseq") == resp0.get("iseq"):
                break
            time.sleep(0.1)
        assert ld0 and ld0.get("iseq") == resp0.get("iseq"), (
            f"seat_commands{tag}: the client's intent for seat-0 unit {seat0_actor_id} was "
            f"not denied within 10s (resp={resp0}, "
            f"lastDeny={event_state(client).get('lastDeny')})")
        assert ld0.get("reason") == "not_your_unit", (
            f"seat_commands{tag}: seat-0 unit deny reason={ld0.get('reason')!r}, want "
            f"'not_your_unit' (full deny: {ld0})")
        after0_h = pos_of(unit_of(host, seat0_actor_id))
        after0_c = pos_of(unit_of(client, seat0_actor_id))
        assert after0_h == before0_h and after0_c == before0_c, (
            f"seat_commands{tag}: seat-0 unit {seat0_actor_id} MOVED despite the deny "
            f"(host {before0_h}->{after0_h}, client {before0_c}->{after0_c})")
        print(f"PASS seat_commands{tag}: client denied 'not_your_unit' on seat-0 unit "
              f"{seat0_actor_id}, no pos change either machine")

    if not host_check:
        print(f"PASS seat_commands{tag}: host leg skipped BY CONSTRUCTION "
              f"(no host-owned unit in this scenario)")
        return

    # ---- 3. host click-select refusal on the seat-1 unit's tile ------------
    target = unit_of(host, seat1_actor_id)
    tx, ty, tz = pos_of(target)
    pr1 = host.cmd({"cmd": "map_tile_click_pos", "x": tx, "y": ty, "z": tz})
    assert pr1.get("verified"), (
        f"seat_commands{tag}: map_tile_click_pos (settling pass) not verified for "
        f"{(tx, ty, tz)}: {pr1}")
    pr2 = host.cmd({"cmd": "map_tile_click_pos", "x": tx, "y": ty, "z": tz})
    assert pr2.get("verified"), (
        f"seat_commands{tag}: map_tile_click_pos (settled pass) not verified for "
        f"{(tx, ty, tz)}: {pr2}")
    assert pr2.get("centered") is False, (
        f"seat_commands{tag}: map_tile_click_pos reports centered=True after the "
        f"settling pass - the camera is still moving (fixture problem, not a "
        f"case to re-roll): {pr2}")
    # render-readiness SYNC before the SINGLE click. pr1/pr2
    # keep the two-pass camera settle (and the centered==False fixture check);
    # _wait_click_ready then blocks until BattlescapeState::mapClick's own
    # pre-primaryAction swallow gates are clear and the click pixel round-trips
    # STABLY, so the injected click cannot land in the post-walk settle window
    # that otherwise swallows it (~1 in 6). ONE click, no retry.
    cx, cy = _wait_click_ready(host, tx, ty, tz, seat1_actor_id)
    host.ok({"cmd": "inject_input", "kind": "click", "x": cx, "y": cy,
             "button": "left"})
    time.sleep(0.6)
    hb = battle_state(host)
    # Print the whole dict this assertion reads, not a guessed
    # key - `warningText` looks like the place for this refusal, but
    # connectionTCP.cpp:8172/8196 + CoopBattleUi.h:322 route it through
    # `_txtCoopWait` (coopWaitText), and TestServer.cpp:7175 vs :7197 confirm
    # `warningText` is the DISTINCT vanilla `_warning` surface the coop refusal never
    # touches - so both are printed and the assertion below reads the one the
    # source actually writes.
    print(f"[seat_commands{tag} CAPTURE] host click-select refusal: coopWaitText="
          f"{hb.get('coopWaitText')!r} warningText={hb.get('warningText')!r} "
          f"selectedId={hb.get('selectedId')!r} target={seat1_actor_id}")
    assert hb.get("coopWaitText") == "Not one of your soldiers", (
        f"seat_commands{tag}: host coopWaitText={hb.get('coopWaitText')!r} after "
        f"clicking the client's unit's tile, want 'Not one of your soldiers' "
        f"(STR_COOP_DENY_NOT_YOUR_UNIT) - full battle_state: {hb}")
    assert hb.get("selectedId") != seat1_actor_id, (
        f"seat_commands{tag}: the host's click SELECTED the client's unit "
        f"{seat1_actor_id} instead of being refused: {hb}")
    print(f"PASS seat_commands{tag}: host click-select on seat-1 unit {seat1_actor_id}'s "
          f"tile refused ('Not one of your soldiers'), selectedId="
          f"{hb.get('selectedId')!r}")


def _crash_log_snapshot():
    """Every crash_*.log in this lane's own crash folder (harness.CRASH_DIR, where every game this process
    spawns writes its crash files), right now - a before/after diff around battle_exit is what makes
    'no crash log' mean something (a fixed set present from an EARLIER test's crash would otherwise
    false-positive every later battle_exit)."""
    import harness as _harness
    return set(glob.glob(os.path.join(_harness.CRASH_DIR, "crash_*.log")))


def assert_battle_exit(host, client, what="", expect_both=True):
    """The common-tail check battle_exit: the
    host-authoritative abort (coop_abort_battle) returns the HOST to
    GeoscapeState with NO new crash log and NO desyncSeen on EITHER machine.
    SHARED (expect_both=True): the client also returns. SEPARATE
    (expect_both=False): the client leaves through its own debriefing from the
    host's `debrief_result`, which is NOT asserted here."""
    tag = f" {what}" if what else ""
    before_crash = _crash_log_snapshot()
    # The battle teardown can reset the latch (resetBattleAuthority), so
    # desyncSeen is also read on BOTH machines while the battle is still live.
    for gc, tag2 in ((host, "host"), (client, "client")):
        desync = event_state(gc).get("desyncSeen")
        assert desync is False, f"battle_exit{tag}: {tag2} event_state.desyncSeen={desync!r} before abort"
    coop_abort_battle(host, client, expect_both=expect_both)
    geo_checks = ((host, "host"), (client, "client")) if expect_both else ((host, "host"),)
    for gc, tag2 in geo_checks:
        st = states(gc)
        assert st and "GeoscapeState" in st[-1], (
            f"battle_exit{tag}: {tag2} not on GeoscapeState after abort: {st}")
    # desyncSeen is verified on BOTH machines through the abort regardless of mode.
    # event_state is the only probe that publishes desyncSeen (battle_state has
    # no such key); anything but False fails.
    for gc, tag2 in ((host, "host"), (client, "client")):
        desync = event_state(gc).get("desyncSeen")
        assert desync is False, f"battle_exit{tag}: {tag2} event_state.desyncSeen={desync!r} after abort"
    after_crash = _crash_log_snapshot()
    new_crash = after_crash - before_crash
    assert not new_crash, f"battle_exit{tag}: NEW crash log(s) appeared: {sorted(new_crash)}"
    print(f"PASS battle_exit{tag}: both machines back on the geoscape, no crash log, "
          f"no desyncSeen")
