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


def wait_sync_loop_closed(host, timeout=20, interval=0.2):
    """Block until the EXECUTOR's per-action sync-check loop has caught up: every
    action seq (and boundary seq) it recorded has been answered by the peer.

    Why a harness helper for this: the sync-check samples the client's per-action
    hash LATE - at the moment the client consumes that chain's gated `action_end`
    marker (coopEmitActionDone), which lags the executor by whatever display is
    still in flight. A harness lever that mints an item OUT OF BAND (battle_give is
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
        # pending latch entries are REPORTED for diagnostics, never asserted. Classic/lever-off
        # callers keep the cumulative semantics below untouched (other suites depend on them).
        ps = host.cmd({"cmd": "parallel_state"})
        persist_alarms = int(ps.get("syncBoundaryPersistAlarms") or 0)
        pending = int(ps.get("syncBoundaryPending") or 0)
        desync = bool(host.cmd({"cmd": "battle_state"}).get("desyncSeen"))
        alarmed = {n: c for n, c in bad.items() if buckets[n]["alarm"]}
        if (alarmed or pending) and not quiet:
            print(f"    NOTE{tag}: latch-aware sync-clean (report-only) - cumulative "
                  f"alarm-bucket mismatches {alarmed}; still-pending latch entries={pending}; "
                  f"persistAlarms={persist_alarms} desyncSeen={desync}\n"
                  f"    {_sync_mismatch_lines(sc)}")
        assert not (desync or persist_alarms > 0), (
            f"SYNC-CHECK ALARM{tag} (latch): the persistence latch promoted a boundary "
            f"divergence - desyncSeen={desync} syncBoundaryPersistAlarms={persist_alarms} "
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


# ===== R2-P11 (rewrite spike, SPIKE-RUNBOOK.md RB-D32): the new pump/hash
# introspection surface's harness helpers. `assert_sync_clean` above (and
# `sync_check`/`sync_buckets`/`wait_sync_loop_closed`/`battle_checksum`/
# `assert_battle_synced`, all reading the OLD parallel-architecture
# `parallel_state`/`sync_check` commands) are LEFT IN PLACE per this packet's
# own instructions - they still back whatever SKIP-PENDING tests eventually
# resume against the pre-rewrite build. These two are their rewrite-era
# successors, reading the NEW TestServer commands (event_log/event_state/
# hash_now) this packet adds.

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
    """Successor of `assert_sync_clean` (above) for the rewrite spike's
    one-way compare model (SS2.8: "host ships h in evs; CLIENT hashes
    post-apply, compares... host never compares"). Unlike assert_sync_clean,
    there is no host-side ring to poll for a compare-catches-up loop - this is
    a direct, synchronous `hash_now` snapshot on BOTH machines, bucket-for-
    bucket equal. Correct for a t=0 (pre-first-event) call (SS2.8's own
    boundary-sweep language); a caller comparing AFTER live actions have run
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


# WV-D63 (SPEC 6a): deterministic placement helpers. Faction/seat/tilepart
# constants are declared locally rather than imported - every repro in this
# tree (repro_atom_door.py, repro_atom_walk.py, ...) already re-declares its
# own copies rather than session.py exporting a shared set, so this follows
# the existing convention instead of inventing a new one.
_FACTION_PLAYER = 0
_COOP_SEAT_1 = 1
_O_WESTWALL = 1
_O_NORTHWALL = 2

# dir 0 = north, clockwise (repro_atom_door.py/repro_atom_walk.py's own
# DIR_DX/DIR_DY tables): (dx, dy) -> dir.
_DIR_FROM_DELTA = {
    (0, -1): 0, (1, -1): 1, (1, 0): 2, (1, 1): 3,
    (0, 1): 4, (-1, 1): 5, (-1, 0): 6, (-1, -1): 7,
}

# This lever OWNS the corner<->geometry mapping - TestServer.cpp's own
# battle_teleport_all comment states the same convention - NW=(low x,low y),
# NE=(high x,low y), SW=(low x,high y), SE=(high x,high y). "Facing the map
# edge" (WV-D63(a)) means facing further INTO that same corner, i.e. away
# from the map's centre and away from the door.
_CORNER_FACING = {"NW": 7, "NE": 1, "SW": 5, "SE": 3}


def place_deterministic(host, client, moves, what=""):
    """WV-D63(a): applies the SAME sequence of placement-lever calls
    (`battle_teleport_unit` / `battle_teleport_all`) to BOTH machines, in the
    same order, with identical arguments - never any coop wire traffic
    (WV-D63(b): the harness applies each machine's lever call independently)
    - then asserts `hash_now{full:true}` ALL buckets EQUAL: the gate every
    WV-D63 fixture must pass before its measured action.

    `moves`: a list of dicts, each `{"lever": "battle_teleport_unit"|
    "battle_teleport_all", **params}` - `params` match that lever's own JSON
    fields exactly (TestServer.cpp). Raises if either machine's lever call
    errors, if the two machines' replies for one move DIFFER (WV-D63(f):
    "moves N units on BOTH machines with identical replies" - dict equality
    is the right comparison here, since these are JSON objects, not an
    ordering promise), or if the post-placement hash comparison mismatches.
    Returns the list of (host_reply, client_reply) pairs, one per move.
    """
    tag = f" {what}" if what else ""
    results = []
    for i, move in enumerate(moves):
        move = dict(move)
        lever = move.pop("lever")
        req = {"cmd": lever, **move}
        hr = host.cmd(req)
        cr = client.cmd(req)
        assert hr.get("ok"), f"place_deterministic{tag}: move {i} ({lever}) failed on host: {hr}"
        assert cr.get("ok"), f"place_deterministic{tag}: move {i} ({lever}) failed on client: {cr}"
        assert hr == cr, (
            f"place_deterministic{tag}: move {i} ({lever}) replies differ between "
            f"host and client - host={hr} client={cr}")
        results.append((hr, cr))
    assert_hash_clean(host, client, full=True, what=f"place_deterministic{tag}")
    return results


def _tile_standable(gc, pos):
    """Conservative READ-ONLY proxy for the placement lever's own
    standability predicate (Tile.cpp:289/:300/:319 via `tile_info`, the same
    floor-presence check `repro_atom_door.tile_walkable()` uses) - used here
    only to CHOOSE which side of a door to stand on before calling the
    lever; the lever itself is the real judge and refuses (changing nothing)
    if this proxy ever disagrees."""
    ti = gc.cmd({"cmd": "tile_info", "x": pos[0], "y": pos[1], "z": pos[2]})
    if not ti.get("ok"):
        return False
    return ti.get("parts", {}).get("floor", {}).get("mapDataID", -1) >= 0


def contact_free_ufo_door_setup(host, client, door_pick_rule=None, what="",
                                 actor_id=None, teleport_hostiles=True):
    """WV-D63(c): builds a CONTACT-FREE UFO-door crossing SITUATION
    deterministically via `place_deterministic`, instead of searching a
    freshly generated map for one the way `repro_atom_door.py`'s
    `walk_through_candidates()`/`MAX_REROLLS` loop does. Call once the battle
    is Active on both machines (after the usual bring-up +
    `dismiss_battle_start_overlays`/`dismiss_client_briefing`).

    WHY `actor_id`/`teleport_hostiles` exist (SPEC 6c2 (d) step 2): the WV-D59
    door-reserve-fairness repro needs TWO deterministically-staged crossings
    in the SAME battle, one per leg - a client-origin crossing and a
    host-origin control - and this helper's own "lowest live seat-1 soldier"
    rule would otherwise hand BOTH callers the identical actor. `actor_id`
    lets a SECOND call pick a DIFFERENT soldier; `teleport_hostiles=False`
    lets that second call skip re-doing the (idempotent but redundant)
    `battle_teleport_all` the FIRST call already did in this battle.

    1. Picks a CLOSED UFO door via `find_doors` (the same TestServer lever
       `repro_atom_door.find_doors()` wraps), filtered to `isUfoDoor` and not
       `isUfoDoorOpen`, in `find_doors`' own linear tile-index order
       (deterministic). `door_pick_rule(doors)` may override the SELECTION
       from that filtered list (default: the first).
    2. `battle_teleport_all {faction:"hostile", corner:<farthest from the
       door>, facing:<into that corner>}` - moves every live hostile out of
       contact range on BOTH machines (WV-D63(a): "teleport all aliens away"
       replaces "kill all but one"). SKIPPED when `teleport_hostiles=False`
       (the caller already cleared hostiles earlier in this same battle).
    3. `battle_teleport_unit` - moves ONE live seat-1 soldier onto the
       standable tile in front of the door, facing it: the LOWEST live
       seat-1 id by default, or the given `actor_id` (asserted live, seat-1,
       and present on BOTH machines) when provided.
    4. `place_deterministic`'s own hash-equality gate (all buckets EQUAL).
    5. Returns the `(actor_id, near, far, door)` crossing descriptor
       `repro_atom_door.py`'s `walk_through_candidates()` already produces,
       so a caller can feed it straight into that file's
       `phase_walk_through()`/`phase_right_click()` unchanged.

    Raises `AssertionError` (prefixed `FIXTURE:` where the cause is "this
    generated map cannot supply the situation", never a coop-atom failure)
    if there is no closed UFO door, no live seat-1 soldier (or the requested
    `actor_id` is not one, on EITHER machine), or neither side of the chosen
    door looks standable - the caller re-picks (a fresh bring-up / a
    different door_pick_rule), the same re-roll discipline every other
    wave-1 fixture uses. Defaults preserve every existing caller byte-for-
    byte (`actor_id=None, teleport_hostiles=True` = today's behaviour).
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
        moves.append({"lever": "battle_teleport_all", "faction": "hostile",
                      "corner": corner, "facing": alien_facing})
    moves.append({"lever": "battle_teleport_unit", "unit": actor_id,
                  "x": near[0], "y": near[1], "z": near[2], "dir": soldier_dir})
    place_deterministic(host, client, moves, what=f"contact_free_ufo_door_setup{tag}")

    return actor_id, near, far, door


def lightning_door(host):
    """The craft's own UFO door: exactly one find_doors entry with dataSet LIGHTNIN (WV-D87)."""
    r = host.cmd({"cmd": "find_doors", "limit": 512})
    assert r.get("ok"), f"find_doors failed: {r}"
    ds = [d for d in r.get("doors", []) if d.get("dataSet") == "LIGHTNIN"]
    assert len(ds) == 1, f"FIXTURE: expected exactly one LIGHTNIN door, got {ds}"
    return ds[0], r["mapSizeX"], r["mapSizeY"]


class KnownFlake(AssertionError):
    """WV-D90: a KNOWN flaky scenario was detected and its evidence recorded. Exit 2, loudly."""


KNOWN_FLAKE_BANNER = (
    "################################################################################\n"
    "#  KNOWN FLAKY SCENARIO - NOT A NEW FAILURE - EVIDENCE CAPTURED FOR THE RCA    #\n"
    "#  {test}: {summary}\n"
    "#  Tracked as {tracking}. This failure is IMPORTANT EVIDENCE toward fixing the    #\n"
    "#  known flake: keep this log. The JSON record follows / preceded this banner. #\n"
    "################################################################################")


def print_known_flake_banner(test, tracking, summary):
    print("\n" + KNOWN_FLAKE_BANNER.format(test=test, tracking=tracking, summary=summary) + "\n",
          flush=True)


def units_near(gc, tiles, radius=3):
    """Every living unit within Chebyshev `radius` of ANY of `tiles`: id, faction, position,
    armorSize, status - 'anything that could be on the tile' (owner, 2026-09-06)."""
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
    """WV-D90: print the banner + the one-line JSON record + the banner, then raise KnownFlake
    (the caller's __main__ maps it to exit 2 and prints the banner once more)."""
    import json as _json
    print_known_flake_banner(test, tracking, summary)
    print("KNOWN-FLAKE-RECORD " + _json.dumps(record, default=str, sort_keys=True), flush=True)
    print_known_flake_banner(test, tracking, summary)
    raise KnownFlake(f"{test}: {summary} (WV-D90 {tracking}; record printed above)")


def assert_turret_parity(host, client, what="", unit_ids=None):
    """RW-FIX-TURRET: `battle_state`'s per-unit `directionTurret` must read
    the SAME on both machines for every unit they share (or just `unit_ids`).

    Why this needs its own assert instead of riding a bucket: the field is
    serialized unconditionally (BattleUnit.cpp:717) but NO structured hash
    bucket reads it, and it is not on `saveBlobExcludedUnitKey`'s list
    (SharedEcon.cpp) - so its only hash coverage is the saveBlob catch-all,
    which reports "saveBlob differs" without ever naming a field. This assert
    names it.

    Regression gate for the 2026-09-02 RCA: the R3-P1 applier wrote a body
    turn with BattleUnit::setDirection(), which couples the turret to the
    body (BattleUnit.cpp:988-994, "only used for initial unit placement"),
    while the host's real rotation runs through BattleUnit::turn() and leaves
    a turret-less soldier's turret untouched (the `_turretType > -1` guards,
    BattleUnit.cpp:1326-1347). Two rotations of one soldier were enough to
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
        "the exe predates the RW-FIX-TURRET TestServer addition (stale build?)")
    bad = {i: (hu[i]["directionTurret"], cu[i]["directionTurret"])
           for i in ids if hu[i]["directionTurret"] != cu[i]["directionTurret"]}
    assert not bad, (
        f"directionTurret MISMATCH{tag}: {len(bad)}/{len(ids)} unit(s) differ, "
        f"(host, client) = {bad} - the client applier dragged the turret along "
        "with the body facing again (RW-FIX-TURRET)")
    return len(ids)


def assert_reveal_parity(host, client, what="", samples=24, extra_positions=()):
    """RW-REVEAL-SYNC (SPIKE-RUNBOOK.md SS2.4a): the two machines' per-tile
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

    Lives here next to assert_hash_clean/assert_turret_parity: every rewrite
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
    which is exactly what SS2.4a's presence-gating promises for an action that
    discovered nothing."""
    path = os.path.join(host.user_dir, "openxcom.log")
    try:
        with open(path, "r", errors="replace") as f:
            return sum(1 for ln in f if "[coop-reveal] attached reveal delta" in ln)
    except OSError:
        return 0


def dismiss_battle_start_overlays(host, timeout=10):
    """Clear the vanilla battle-start overlays stacked over the HOST's
    BattlescapeState, so the map screen is on top and its _gameTimer ticks
    again. Presses ESC (Options::keyCancel) until BattlescapeState is the top
    state.

    CONSOLIDATED HERE BY W1-P4 (WAVE1-RUNBOOK.md SS4 harness ripple, IR2-1).
    Five files carried a copy of this helper - repro_atom_turn.py,
    repro_atom_kneel.py, repro_reveal_sync.py, test_rw_input_gating.py and
    test_rw_retry_cancel.py - each documenting the same surprise in slightly
    different words. W1-P4 changed what is actually on that stack, so keeping
    five copies in sync stopped being free; this follows W1-P3's own precedent
    (dismiss_client_briefing() below).

    WHY IT EXISTS (the original surprise, found while building repro_atom_turn):
    a freshly generated battle stacks overlays on top of BattlescapeState, and
    Game::run() only think()s _states.back() (Game.cpp) - so BattlescapeState's
    _gameTimer, and with it the whole BState machine including an admitted coop
    action, never ticks until they are gone. An injected TAB/click would also
    land on the overlay instead of the map.

    WHAT IS ON THAT STACK NOW (W1-P4, ruling D3 = WV-D9/WV-D34, mechanism
    WV-D43): in a COOP battle it is ONLY vanilla's "Turn 1 begins"
    (NextTurnState). The pre-battle equip screen (InventoryState) is FROZEN -
    BriefingState::btnOkClick skips its push and calls
    SavedBattleGame::startFirstTurn() itself - so there is no InventoryState to
    dismiss any more. In a plain SP battle BOTH are still there
    (['BattlescapeState','NextTurnState','InventoryState']), which is why this
    stays an ESC LOOP on the top state rather than a fixed number of presses:
    it is correct for both shapes, and for a stack that is already clean.

    HOST-only. The client loads the streamed blob straight into
    BattlescapeState with no generation-time popups; its own entry overlay is
    the read-only BriefingState, which dismiss_client_briefing() below owns.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = states(host)
        if st and "BattlescapeState" in st[-1]:
            return
        host.ok({"cmd": "inject_input", "kind": "key", "key": 27})  # SDLK_ESCAPE / Options::keyCancel
        time.sleep(0.3)
    raise TimeoutError(f"host: battle-start overlays never cleared, stack={states(host)}")


def dismiss_client_briefing(client, timeout=20):
    """W1-P3 (WAVE1-RUNBOOK.md SS4 / ruling D3 = WV-D9, and SS1's WAVE-1
    ADDITIONS trap 2): the coop CLIENT now enters a battle the way the host
    does - BattlescapeState FIRST, then a READ-ONLY BriefingState OVER it
    (CoopHandshake::onBlobChunkAppended, connectionTCP.cpp). Every fixture that
    DRIVES the client must dismiss that briefing explicitly instead of assuming
    the battle screen is on top. Three reasons, all real:
      * Game::run() only think()s _states.back(), so an injected key/click
        lands on the BRIEFING, not on the map;
      * BriefingState's ctor holds the GEOSCAPE base resolution while it is up
        (BriefingState.cpp:58-60), so any screen-projection probe computes
        against the wrong viewport - the exact failure repro_atom_turn.py's
        run_ui_variant hit on W1-P3's first run ("computed click target
        (-330,350) is off the 320x200 map viewport");
      * the runbook's own rule: "any repro that drives the client through a
        briefing must dismiss it explicitly (close_briefing) rather than
        assuming the battle probes work under it."

    Read-only PROBES (battle_state / event_state / hash_now / get_palettes) do
    work under it - test_rw_client_briefing.py asserts exactly that - so this
    helper is about DRIVING, not probing.

    Idempotent and version-tolerant: a no-op when the client has no
    BriefingState on its stack (a resume entry, or any pre-W1-P3 build), so it
    is safe to call unconditionally at the end of every drive_to_battlescape().
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
    assert top and "BattlescapeState" in top, (
        "closing the client's entry briefing should land it on BattlescapeState "
        f"(W1-P3 pushes the briefing directly OVER it), got stack={states(client)}")
    return True


# ---------------------------------------------------------------------------
# FIXTURE PINNING (WV-D5 sweep, 2026-09-03; RB-D15, WV-D18, REVIEW4 IR-4).
#
# THE ONE shared copy of SELECTION RULE (c). It lived inline in three repros
# before this sweep; four separate files were caught in three days carrying an
# UNPINNED version of the same premise, each costing a red run to discover, so
# it is hoisted here where every coop test already imports from.
#
# WHAT IT PINS. RB-D15 and WV-D18 both require an "open-ground, no-door,
# NO-ENEMY-LOS" fixture actor. Rules (a) "no hostile ALREADY spotted at t=0"
# and (b) "no door within 2 tiles" cover the first two; NEITHER says anything
# about whether the actor's ROTATION will bring a unit into view. Vanilla
# aborts a BA_NONE turn mid-chain the moment getUnitsSpottedThisTurn() grows
# (UnitTurnBState.cpp:117), leaving the unit on an intermediate facing - and
# the engine itself calls that a FIXTURE failure, logging "[coop-turn] ...
# ABORTED mid-chain - the RB-D15/REVIEW4 IR-4 fixture guards ... should have
# prevented this".
#
# It is a PIN on the selection rule (the IR-4 treatment), never a relaxation of
# anything a test asserts: a fixture that fails it is RE-ROLLED, and the
# assertions that run afterwards are unchanged.
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
    """SELECTION RULE (c): True iff no LIVING NON-PLAYER unit is within
    MAX_VIEW_DISTANCE of @a unit - i.e. no rotation of this actor can spot
    anybody, so vanilla's unitSpotted abort branch is unreachable for it.

    @a tag is the calling test's name, for the log line. Callers use this as
    the third arm of their own qualifying_actor(): fail it -> return None ->
    the bounded re-roll loop boots a fresh generation."""
    d = nearest_non_player_distance(battle_state_resp, unit)
    if d is not None and d <= MAX_VIEW_DISTANCE:
        print("[%s] rule (c): nearest non-player unit is %.2f tiles from the actor "
              "(cap %d) - its rotation could spot one and abort mid-chain"
              % (tag, d, MAX_VIEW_DISTANCE))
        return False
    print("[%s] rule (c) ok: nearest non-player unit is %s away (cap %d)"
          % (tag, "none at all" if d is None else "%.2f tiles" % d,
             MAX_VIEW_DISTANCE))
    return True


# ===== SPEC 6g (WV-D78/WV-D80): primitives relocated from repro_atom_door.py ==
# That file was 2113 lines of map-ROLLED door search whose coverage now lives in
# repro_door_deterministic.py (SPEC 6d/6e/6f), and it was a proven flake. These
# helpers were shared, so they move here VERBATIM; the file itself is deleted.
# Two authorized substitutions were made in drive_to_battlescape: its
# W.top_state/W.states calls became the session-local top_state/states_stripped
# below, and its session.-prefixed self-calls lost the prefix now that it lives
# here. Nothing else changed.


def states_stripped(gc):
    """`states()` with MSVC's "class OpenXcom::" prefix removed - the form every
    repro compares against. Copied from repro_atom_walk.states (SPEC 6g
    AMENDMENT 1): it is a pure wrapper over this module's OWN states(), so it
    lives here without importing repro_atom_walk (which imports session, and
    would cycle)."""
    return [s.replace("class OpenXcom::", "") for s in states(gc)]


def top_state(gc):
    """The top of the state stack, prefix-stripped. Copied from
    repro_atom_walk.top_state (SPEC 6g AMENDMENT 1)."""
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
    """SS2.W2 rule 6 / SS4's acceptance: the `door` ev takes its place in the
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
    """SPEC 6c5 step 1 (WV-D77) instrumentation helper. The full door dict at
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

    A LIST, not a single tile, and that is the point. When this returned only the
    first match, one actor parking on it made the same door unusable for all six
    other soldiers - four of the seven rejections in a traced red were "no
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

    `lastSeqApplied == lastSeqEmitted` ALONE IS NOT ENOUGH, and this cost a run:
    a turn emits its `bt_ev` from UnitTurnBState and its `bt_action_end` from
    CoopArbiter::onChainQuiesced() one chain-unwind LATER, so the two counters
    are transiently EQUAL in the gap between them - and
    CoopArbiter::popActionContext() runs inside onChainQuiesced
    (connectionTCP.cpp:3737). Anything driven in that window inherits the
    previous action's actionId, which is exactly how PHASE 2's `actionId 0`
    assertion first failed (it observed 3). `busyOwnerSeat == -1` on the HOST is
    the shipped predicate for BOTH halves at once:
    `!bg->isBusy() && currentActionId() == 0` (connectionTCP.cpp:4545-4551)."""
    client.wait_for("host idle (no action context, no BState chain), client caught up",
                    lambda: (event_state(host).get("busyOwnerSeat") == -1
                             and event_state(client).get("lastSeqApplied", 0)
                             == event_state(host).get("lastSeqEmitted", 0)
                             and event_state(client).get("queueDepth") == 0
                             and event_state(host).get("queueDepth") == 0) or None,
                    timeout=timeout)


def drive_to_battlescape(host, client, seated, mission=None, seat_count=8, pre_seat=None):
    """repro_atom_walk.drive_to_battlescape plus the mission pin. Kept local
    rather than parameterising the walk repro's copy: that file carries a
    stop-line criterion and this packet must not change how it boots.

    `pre_seat` (SPEC 0e-1, additive): an optional `callable(host)` invoked
    right after the mission pin and before any `newbattle_seat_soldier`
    call - the window WV-D87/WV-D88 need for `newbattle_craft`/
    `newbattle_race` (race must land AFTER mission, since cbxMissionChange
    rebuilds the race list, and BEFORE seating). Every existing caller is
    unaffected: default None, nothing runs."""
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
    for i in range(seat_count):
        r = host.cmd({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1, "index": i})
        if not r.get("ok"):
            break
        soldier_ids.append(r["soldierId"])
    assert len(soldier_ids) >= 2, (
        f"FIXTURE: newbattle_seat_soldier stamped only {len(soldier_ids)} soldier(s) "
        "to seat 1 - this repro needs client-owned actors to walk")
    seated["soldierIds"] = soldier_ids

    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: has_state(host, "BriefingState"),
                  timeout=60)
    # WV-D56 (FX-1): the snapshot/offer now move to AFTER startFirstTurn() -
    # i.e. to this click, not to newbattle_ok. "client battlescape" can only be
    # waited for AFTER it, never before.
    host.ok({"cmd": "click_widget", "match": "ok"})
    host.wait_for("host battlescape",
                  lambda: has_state(host, "BattlescapeState"), timeout=40)
    dismiss_battle_start_overlays(host)
    client.wait_for("client battlescape",
                    lambda: has_state(client, "BattlescapeState"), timeout=90)
    # WV-D82: connectionTCP.cpp:8280-8330 pushes BattlescapeState and the read-only BriefingState in ONE synchronous handler; this asserts that precondition loudly instead of napping 3 s past it (WV-D80).
    client.wait_for("client entry briefing pushed over BattlescapeState",
                    lambda: has_state(client, "BriefingState") or None, timeout=20)
    dismiss_client_briefing(client)
