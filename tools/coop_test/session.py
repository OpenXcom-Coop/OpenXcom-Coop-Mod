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
        timeout=60, interval=1.0,
    )
    time.sleep(2)
    host.ok({"cmd": "lobby_action"})


def new_campaign(host, client, port="47900",
                 host_name="HostPlayer", client_name="ClientPlayer",
                 host_base="HostBase", client_base="ClientBase",
                 campaign_mode="coop", transport="tcp"):
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
    host.ok({"cmd": "newgame_ok"})
    host.wait_for("host window", lambda: _has_state(host, "HostMenu"))

    udp_pw = "harness-lan"
    client_udp_port = str(int(port) + 1)

    # host window -> lobby
    if transport == "udp":
        host.ok({"cmd": "host_udp", "port": port, "player": host_name, "password": udp_pw})
    else:
        host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": port, "player": host_name})
    host.wait_for("host lobby", lambda: _has_state(host, "LobbyMenu"))

    # client joins and lands in the lobby (no ready button). Both machines then
    # show the "player joined" popup over the lobby; dismiss it the way a player
    # would so callers see the lobby as the top state. The UDP handshake
    # (hole-punch + INIT_SERVER) is async, so the client can take a few seconds
    # longer to surface the lobby than on TCP.
    if transport == "udp":
        client.ok({"cmd": "join_udp", "ip": "127.0.0.1", "port": port,
                   "localport": client_udp_port, "player": client_name, "password": udp_pw})
    else:
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": client_name})
    client.wait_for("client lobby", lambda: _has_state(client, "LobbyMenu"), timeout=120)
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

    # Press the REAL RESUME button (see helper) instead of the direct-call shortcut.
    resume_campaign_via_button(host, client_name)

    # host holds in the loading dialog until the client acks, then RESUME
    host.wait_for(
        "client world ack",
        lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None,
        timeout=120,
    )
    host.ok({"cmd": "coop_dialog_back"})

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

    # Press the REAL resume button (btnCancelClick). This is the branch where the
    # mid-battle-resume bug lived - the direct lobby_resume_campaign shortcut skips
    # it. See resume_campaign_via_button.
    resume_campaign_via_button(host, client_name)

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
    prove a lever moved the bucket it was supposed to move, without waiting a
    round trip for a report that may never come."""
    b = gc.cmd({"cmd": "battle_state", "sync": True})
    h = b.get("battleHashes")
    assert h is not None, (
        f"battle_state carries no 'battleHashes' - PRD-I0's bucket sweep is not "
        f"exposed: {sorted(b)}")
    return h


def assert_sync_clean(host, client, what="", strict=False, allow=(), timeout=30,
                      interval=0.5, quiet=False):
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
