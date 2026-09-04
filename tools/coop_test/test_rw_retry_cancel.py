"""R2-P7 (rewrite spike, SPIKE-RUNBOOK.md R2-P7 packet text, OWNER-1 resolved
2026-08-31): CLIENT auto-retry on deny("busy") + the four info-cancel user
options + the `hold_chain` test lever that finally makes a LIVE busy deny
reproducible.

WHY THIS FILE EXISTS AT ALL: R3-P2's own burst proof recorded a GAP
(spike-log "R3-P2 ACCEPTED", GAP paragraph) - deny("busy") had never been
live-fired, because a full 4-tick UnitTurnBState chain resolves host-side in
well under one TestServer round trip, so a natural two-seat race cannot land.
The owner approved (2026-09-02) a test-only `hold_chain {ms}` lever as a
STOPGAP: the HOST defers a quiesced chain's bt_action_end + action-context pop
for N ms, which keeps CoopArbiter::onIntent()'s SS2.5 `currentActionId() != 0`
busy arm true for a deterministic window. Its removal note is carried verbatim
at every one of its code sites.

hold_chain holds CHAIN-FUL actions only. A kneel is chain-less (RB-D13):
coopOnKneelFinished() emits its own bt_action_end and pops its own action
context inside the single BattlescapeGame::kneel() call, never reaching
BattlescapeGame::popState()/onChainQuiesced() where the latch lives. So every
blocker in this file is a TURN, and every blocked intent is a kneel.

Three sessions:
  test_option_round_trip() - ONE instance at the main menu (no battle needed):
                             set_option round-trip for all four option names
                             (packet acceptance (c)). The response echoes the
                             LIVE Options:: global read back AFTER the write,
                             so this proves the value landed rather than
                             bouncing off the request.
  test_busy_live_fire()    - deny("busy") -> pending banner -> auto-resubmit
                             on the blocker's bt_action_end -> ack + apply,
                             hash-clean 9/9, queueDepth 0 (packet acceptance
                             (a)). Plus the SAME-unit variant, which R3-P1's
                             own IR-2 actor lock suppresses CLIENT-side - see
                             run_same_unit_variant()'s doc comment (this is a
                             disclosed packet tension, not a silent skip).
  test_cancel_policy()     - a pending intent + a synthetic `spot` ev injected
                             via inject_ev (RB-D32) at default-ON options ->
                             pending CLEARED + STR_COOP_CANCEL banner; the
                             same sequence at all-OFF -> pending SURVIVES and
                             resubmits at quiescence (packet acceptance (b)).

W1-P7 EXTENSIONS (WAVE1-RUNBOOK.md ruling D7 = WV-D13; its own acceptance says
"extend test_rw_retry_cancel.py"):

  * the option round-trip now also covers `coopIntentTimeoutSeconds` (WV-D24's
    10 s intent timeout), which is a real Options.inc.h + Options.cpp OptionInfo
    like the four cancel toggles and never a connectionTCP static (WR-25);
  * the busy-live-fire pass now asserts the "order sent" IN-FLIGHT indicator
    (STR_COOP_ORDER_SENT) between the send and the host's answer;
  * ...and it asserts the donor wait driver's SUPPRESSION rule POSITIVELY. The
    blocker in this file is the CLIENT'S OWN admitted turn, so the seat that
    owns the host's execution slot is the client's own - and the donor rule
    (`cbff7951d:BattlescapeState.cpp:5292-5370`) says a machine must NOT be told
    to "wait for {someone}" when it is waiting on ITSELF. The generic SS2.6 busy
    row is therefore the CORRECT text here, and `event_state.busyOwnerSeat` is
    asserted to be this machine's own seat so that is a proven rule rather than
    a coincidence. The peer-attributed case (a HOST-local blocker naming the
    host) lives in test_rw_feedback.py PHASE 3.

FIXTURE: same recipe/precedent as repro_atom_kneel.py (R3-P2) / repro_atom_turn
.py (R3-P1) - a live 2-player skirmish through the harness lobby flow with the
REVIEW4 IR-4 SELECTION RULE and a bounded re-roll loop, two client-owned
soldiers (newbattle_seat_soldier index param) so a blocker and a blocked intent
can name DIFFERENT units.

Run:  python tools/coop_test/test_rw_retry_cancel.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import assert_hash_clean

COOP_SEAT_0 = 0
COOP_SEAT_1 = 1
# Raised from 5 by the WV-D5 fixture-pinning sweep: SELECTION RULE (c)
# rejects more generations than (a)+(b) did, and a re-roll is the CORRECT
# response to a fixture that cannot prove the property.
MAX_REROLLS = 15

# W1-P7 (WV-D13 item 2): the in-flight indicator's exact text.
STR_ORDER_SENT_TEXT = "Order sent - waiting for the host"

# SPIKE-RUNBOOK.md sec 2.6, verbatim (bin/common/Language/en-US.yml:65,73).
# Asserted as TEXT, not as an STR_ key: Language::getString() returns the KEY
# itself when the key is missing, so a key-shaped assert would silently pass
# against a stale deployed bin/x64/Release/common/Language/en-US.yml - which is
# exactly the state this packet found the tree in (see its final report).
STR_BUSY_TEXT = "Waiting - another action is in progress"
STR_CANCEL_SPOTTED_TEXT = "Order cancelled - enemy spotted"

CANCEL_OPTIONS = (
    "coopCancelOnEnemySpotted",
    "coopCancelOnOwnUnitHit",
    "coopCancelOnVisibilityGain",
    "coopCancelOnAnyPartnerAction",
)
# W1-P7 (WV-D13 / WV-D24): the fifth co-op battle option, and the only INT one.
# Its ruled default is 10 s.
TIMEOUT_OPTION = "coopIntentTimeoutSeconds"
TIMEOUT_DEFAULT = 10
# Options.cpp createAdvancedOptionsOTHER() registrations (R2-P7): the packet
# table's "narrowed scope" defaults.
CANCEL_DEFAULTS = {
    "coopCancelOnEnemySpotted": True,
    "coopCancelOnOwnUnitHit": True,
    "coopCancelOnVisibilityGain": True,
    "coopCancelOnAnyPartnerAction": False,
}

# Long enough that a client round trip (~50ms observed, R3-P2) fits many times
# over inside the window, short enough not to pad the suite.
HOLD_MS = 6000


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def units_by_id(battle_state_resp):
    return {u["id"]: u for u in battle_state_resp.get("units", [])}


# ----- fixture bring-up (inline copy, repro_atom_kneel.py precedent) -----

def skirmish_host(host, port, player="HostPlayer"):
    host.ok({"cmd": "open_new_battle"})
    host.wait_for("host new battle", lambda: session.has_state(host, "NewBattleState"))
    host.ok({"cmd": "newbattle_coop"})
    host.wait_for("host browser", lambda: session.has_state(host, "ServerList"))
    host.ok({"cmd": "server_list_host"})
    host.wait_for("host window", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv",
             "port": port, "player": player})
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"))


def skirmish_client_at_browser(client):
    client.ok({"cmd": "open_new_battle"})
    client.wait_for("client new battle", lambda: session.has_state(client, "NewBattleState"))
    client.ok({"cmd": "newbattle_coop"})
    client.wait_for("client browser", lambda: session.has_state(client, "ServerList"))


def bring_up_lobby(host, client, port):
    host.spawn(); host.connect()
    client.spawn(); client.connect()

    skirmish_host(host, port)
    skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer"})

    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: lobby(host).get("buttonVisible") or None)


# dismiss_battle_start_overlays() MOVED TO session.py by W1-P4 (harness ripple,
# IR2-1) - see the shared helper's docstring.


def drive_to_battlescape(host, client, seated_holder, seat_count=2):
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={states(host)}"

    soldier_ids = []
    for i in range(seat_count):
        seat_resp = host.ok({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1, "index": i})
        soldier_ids.append(seat_resp["soldierId"])
    seated_holder["soldierIds"] = soldier_ids
    seated_holder["soldierId"] = soldier_ids[0]

    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=30)
    # WV-D56 (FX-1): snapshot/offer move to AFTER startFirstTurn() - i.e. to
    # this click. "client battlescape" can only be waited for AFTER it.
    host.ok({"cmd": "click_widget", "match": "ok"})
    host.wait_for("host battlescape",
                  lambda: session.has_state(host, "BattlescapeState"), timeout=30)
    session.dismiss_battle_start_overlays(host)
    client.wait_for("client battlescape",
                    lambda: session.has_state(client, "BattlescapeState"), timeout=60)
    time.sleep(3)  # let both logs flush the handshake lines

    # W1-P3 (SS1 WAVE-1 ADDITIONS trap 2 / WV-D9): the client now enters the
    # battle through a read-only BriefingState pushed OVER its
    # BattlescapeState, so every fixture that DRIVES the client must dismiss
    # it explicitly - injected input would otherwise land on the briefing and
    # screen-projection probes would compute against the GEOSCAPE viewport the
    # briefing holds. No-op on a stack with no BriefingState.
    session.dismiss_client_briefing(client)


def has_door_within(gc, x, y, z, radius=2):
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            ti = gc.cmd({"cmd": "tile_info", "x": x + dx, "y": y + dy, "z": z})
            if not ti.get("ok"):
                continue
            for part in ti.get("parts", {}).values():
                if part.get("isDoor") or part.get("isUfoDoor"):
                    return True
    return False


def qualifying_actor(host, soldier_id):
    """REVIEW4 IR-4 SELECTION RULE, reused verbatim from repro_atom_turn.py:
    (a) nothing spotted yet (an alien in LOS aborts a BA_NONE rotation,
    UnitTurnBState.cpp:114-118), (b) no door within 2 tiles.

    RULE (c) - added by the WV-D5 fixture-pinning sweep (2026-09-03). RB-D15 and
    WV-D18 require an "open-ground, no-door, NO-ENEMY-LOS" actor, and (a)+(b)
    cover only the first two: (a) asks whether a hostile is ALREADY spotted at
    t=0, which is silent on whether this actor's ROTATION will bring one into
    view. Vanilla aborts a BA_NONE turn mid-chain the moment
    getUnitsSpottedThisTurn() grows (UnitTurnBState.cpp:117). The predicate is
    session.actor_is_contact_free() - THE one shared copy (session.py).
    """
    st = host.cmd({"cmd": "battle_state"})
    if not st.get("ok") or not st.get("inBattle"):
        return None
    if st.get("spotted"):
        return None
    for u in units_by_id(st).values():
        if u.get("soldierId") == soldier_id:
            if has_door_within(host, u["x"], u["y"], u["z"], radius=2):
                return None  # rule (b)
            if not session.actor_is_contact_free(st, u, "retry_cancel"):
                return None  # rule (c)
            return u
    return None


def bring_up_qualifying_battle(tag):
    """Returns (host, client, actor_unit_dict, soldier_ids)."""
    for attempt in range(1, MAX_REROLLS + 1):
        port = str(48236 + attempt)
        host_dir = make_user_dir(f"rw_retry_{tag}_host_{attempt}")
        client_dir = make_user_dir(f"rw_retry_{tag}_client_{attempt}")
        host = GameClient("host", 49080 + attempt * 2, host_dir)
        client = GameClient("client", 49081 + attempt * 2, client_dir)
        seated = {}
        try:
            bring_up_lobby(host, client, port)
            drive_to_battlescape(host, client, seated, seat_count=2)
            actor = qualifying_actor(host, seated["soldierId"])
            if actor is not None:
                print(f"[test_rw_retry_cancel] fixture qualifies on attempt "
                      f"{attempt}/{MAX_REROLLS} (actor unit id={actor['id']}, "
                      f"soldierId={seated['soldierId']})")
                return host, client, actor, seated["soldierIds"]
            print(f"[test_rw_retry_cancel] re-roll {attempt}/{MAX_REROLLS}: fixture did "
                  "not qualify (hostile spotted, or a door within 2 tiles)")
            host.shutdown()
            client.shutdown()
        except Exception:
            host.shutdown()
            client.shutdown()
            raise
    raise RuntimeError(f"test_rw_retry_cancel: no qualifying fixture in {MAX_REROLLS} boots")


# ----- shared observation helpers -----

def event_state(gc):
    return gc.cmd({"cmd": "event_state"})


def pending_of(gc):
    """CLIENT's held (busy-denied, awaiting auto-resubmit) intent, or None.
    battle_state.coopPendingIntent (R2-P7 introspection) - null when the slot
    is empty, so this makes "pending" an observable state rather than
    something inferred from banner text (the busy DENY and the PENDING hold
    deliberately SHARE the SS2.6 busy string)."""
    return gc.cmd({"cmd": "battle_state"}).get("coopPendingIntent")


def banner_of(gc):
    return gc.cmd({"cmd": "battle_state"}).get("coopWaitText", "")


def settle_emits(host, client, timeout=30):
    """Waits until the HOST has nothing left to emit and the client has caught
    up. Load-bearing before reading a `lastSeqEmitted` baseline: RW-REVEAL-SYNC's
    quiescent flush (CoopReveal::flushQuiescent, at the RB-D5 pump point) can
    emit a standalone `ev reveal` a tick or two AFTER an action settles, and a
    baseline read in that window would make start_held_blocker()'s exactly-+1
    lever proof spuriously red."""
    def quiet():
        hs = event_state(host)
        cs = event_state(client)
        rs = host.cmd({"cmd": "reveal_state"})
        return bool(hs.get("ok") and cs.get("ok") and rs.get("ok")
                    and rs.get("unpublished") is False
                    and cs.get("lastSeqApplied", 0) == hs.get("lastSeqEmitted", 0)
                    and cs.get("queueDepth") == 0)
    client.wait_for("host has nothing unpublished and the client is caught up",
                    quiet, timeout=timeout)


def start_held_blocker(host, client, actor_id, hold_ms=HOLD_MS):
    """Arms hold_chain on the HOST, then fires a client TURN intent on
    `actor_id` (180 degrees = the longest single rotation, 4 ticks). Returns
    once the turn's bt_ev has been applied client-side AND the host's
    bt_action_end is provably still outstanding - i.e. the chain has run to
    completion and is now being HELD open, so onIntent() answers busy for
    anything else.

    Returns the host's lastSeqEmitted BEFORE the blocker, so a caller can wait
    for the release (base + 2 = the ev plus the deferred action_end)."""
    settle_emits(host, client)
    emitted_base = event_state(host).get("lastSeqEmitted", 0)
    hold = host.ok({"cmd": "hold_chain", "ms": hold_ms})
    assert hold.get("ms") == hold_ms, f"hold_chain did not arm: {hold}"

    applied_base = event_state(client).get("lastSeqApplied", 0)
    a = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_id]
    to_dir = (a["direction"] + 4) % 8
    client.ok({"cmd": "battle_intent", "kind": "turn", "actor": actor_id, "toDir": to_dir})

    client.wait_for("blocker turn ev applied on the client",
                    lambda: (event_state(client).get("lastSeqApplied", 0) > applied_base) or None,
                    timeout=20)

    # THE LEVER PROOF: exactly ONE new seq exists (the turn ev). A chain that
    # quiesced normally would already have emitted its bt_action_end as the
    # very next seq. While the reveal flush could in principle add a seq here,
    # CoopReveal::flushQuiescent() self-gates on currentActionId()==0 - which
    # a held chain keeps non-zero - so nothing else can emit during the hold.
    emitted_now = event_state(host).get("lastSeqEmitted", 0)
    assert emitted_now == emitted_base + 1, (
        f"host lastSeqEmitted {emitted_base} -> {emitted_now}: the bt_action_end was NOT "
        "deferred, so hold_chain did not engage (expected exactly +1 for the turn ev)")
    return emitted_base


def wait_hold_released(host, client, emitted_base, timeout=40):
    """Waits for the held chain's deferred bt_action_end to be emitted (host
    lastSeqEmitted reaches base+2) and drained on the client."""
    def released():
        hs = event_state(host)
        cs = event_state(client)
        return bool(hs.get("lastSeqEmitted", 0) >= emitted_base + 2
                    and cs.get("lastSeqApplied", 0) >= emitted_base + 2
                    and cs.get("queueDepth") == 0)
    client.wait_for("held chain released (deferred bt_action_end emitted + applied)",
                    released, timeout=timeout)


def wait_pending_cleared_and_applied(host, client, unit_id, want_kneeled, timeout=40):
    def done():
        cs = client.cmd({"cmd": "battle_state"})
        if cs.get("coopPendingIntent") is not None:
            return None
        u = units_by_id(cs).get(unit_id)
        if not u or u["kneeled"] != want_kneeled:
            return None
        if event_state(client).get("queueDepth") != 0:
            return None
        if event_state(host).get("queueDepth") != 0:
            return None
        return True
    client.wait_for(f"pending resubmitted + unit {unit_id} kneeled={want_kneeled} on the client",
                    done, timeout=timeout)


# ----- (c) option round-trip -----

def test_option_round_trip():
    """Packet acceptance (c): TestServer set_option round-trip for all four
    option names. Runs on ONE instance at the main menu - the four toggles are
    plain client-side user options (Options.inc.h + OptionInfo registration,
    REVIEW4 IR-9), nothing about them needs a live battle."""
    d = make_user_dir("rw_retry_options")
    g = GameClient("options", 45997, d)
    g.spawn()
    try:
        g.connect(timeout=180)
        g.wait_for("main menu",
                   lambda: (lambda s: s if s and s[0] != "class OpenXcom::StartState" else None)(
                       g.cmd({"cmd": "get_state"}).get("states")),
                   timeout=180, interval=2)

        # 1. Registered defaults (the packet's own table).
        for name, want in CANCEL_DEFAULTS.items():
            resp = g.ok({"cmd": "set_option", "name": name})  # no "value" = pure read
            assert resp.get("value") is want, (
                f"{name} default should be {want}, got {resp} - the Options.cpp "
                "OptionInfo registration's default does not match the R2-P7 packet table")
        print(f"PASS test_option_round_trip: registered defaults match the packet table "
              f"{CANCEL_DEFAULTS}")

        # 2. Full round-trip both ways for every name. The response echoes the
        #    LIVE Options:: global read back AFTER the write, so a value that
        #    merely bounced off the request would not pass this.
        for name in CANCEL_OPTIONS:
            for want in (False, True, False):
                resp = g.ok({"cmd": "set_option", "name": name, "value": want})
                assert resp.get("value") is want, \
                    f"set_option {name}={want} did not round-trip: {resp}"
                readback = g.ok({"cmd": "set_option", "name": name})
                assert readback.get("value") is want, \
                    f"{name} did not stay {want} on a separate read: {readback}"
        print(f"PASS test_option_round_trip: all four names round-trip through set_option "
              f"({', '.join(CANCEL_OPTIONS)})")

        # 3. W1-P7 (WV-D24 = ruling D-11): the intent timeout is behind the SAME
        #    kind of real user option, not a static. WR-25 makes that a hard
        #    requirement - a static would be unpersisted, invisible to the player
        #    and untouchable from this lever.
        d = g.ok({"cmd": "set_option", "name": TIMEOUT_OPTION})
        assert d.get("value") == TIMEOUT_DEFAULT, (
            f"{TIMEOUT_OPTION} default is {d.get('value')}, expected WV-D24's ruled "
            f"{TIMEOUT_DEFAULT} s - check the Options.cpp OptionInfo registration")
        for want in (3, 25, TIMEOUT_DEFAULT):
            resp = g.ok({"cmd": "set_option", "name": TIMEOUT_OPTION, "value": want})
            assert resp.get("value") == want, \
                f"set_option {TIMEOUT_OPTION}={want} did not round-trip: {resp}"
            readback = g.ok({"cmd": "set_option", "name": TIMEOUT_OPTION})
            assert readback.get("value") == want, \
                f"{TIMEOUT_OPTION} did not stay {want} on a separate read: {readback}"
        print(f"PASS test_option_round_trip: {TIMEOUT_OPTION} defaults to "
              f"{TIMEOUT_DEFAULT} (WV-D24) and round-trips - a real OptionInfo (WR-25)")
    finally:
        g.shutdown()


# ----- (a) busy live-fire -----

def run_same_unit_variant(host, client, actor_id):
    """The packet text's literal "(a) ... intent A + immediate kneel intent B
    on the SAME unit" case.

    DISCLOSED PACKET TENSION (surfaced to the orchestrator in this packet's
    final report, NOT silently adapted): a SAME-unit second intent can never
    reach the host, so it can never produce a wire deny("busy"). R3-P1's own
    client intent tracker (REVIEW4 IR-2, CoopArbiter.h/sendClientIntent) locks
    input for THE ACTING UNIT while its intent is outstanding, and drops a
    second intent for that same actor locally: "while active, input is locked
    for THE ACTING UNIT ONLY (other own units remain selectable - deny-only
    serialization means a second unit's intent would just deny 'busy', which
    is fine to send)". Relaxing that lock would be a design change and this
    packet makes none, so the SAME-unit case is asserted as what the contract
    actually produces - a local suppression, no wire traffic, no new deny -
    and the live busy deny is proven with the SECOND unit's intent (which the
    packet text itself calls out as the case that "sends and denies busy
    fine")."""
    deny_before = event_state(client).get("lastDeny")
    a = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_id]
    resp = client.cmd({"cmd": "battle_intent", "kind": "kneel",
                       "actor": actor_id, "kneel": not a["kneeled"]})

    assert not resp.get("ok"), (
        f"a SECOND intent on the acting unit {actor_id} was accepted while its first "
        f"one is still in flight - R3-P1's IR-2 per-actor input lock is gone: {resp}")
    assert "iseq" not in resp, f"suppressed intent still minted an iseq: {resp}"

    time.sleep(1.0)  # a wire deny, if one were coming, would have landed by now
    assert event_state(client).get("lastDeny") == deny_before, (
        "the suppressed same-unit intent produced a NEW deny - it must never have "
        "reached the host at all")
    assert pending_of(client) is None, (
        "the suppressed same-unit intent created a pending slot - only a wire "
        "deny('busy') may do that")
    print(f"PASS run_same_unit_variant: a second intent on the ACTING unit {actor_id} is "
          "suppressed client-side by R3-P1's IR-2 per-actor input lock (no wire traffic, "
          "no deny, no pending) - see this function's docstring for the disclosed "
          "packet tension")


def test_busy_live_fire():
    """Packet acceptance (a). hold_chain + a client turn intent A (blocker) +
    a kneel intent B on a SECOND client-owned unit -> B deny(busy) observed
    via event_state.lastDeny -> pending banner state -> auto-resubmit on A's
    bt_action_end -> B acked + applied, hash-clean 9/9, queueDepth 0."""
    host, client, actor, soldier_ids = bring_up_qualifying_battle("busy")
    try:
        actor_a = actor["id"]
        actor_b = next(u for u in client.cmd({"cmd": "battle_state"})["units"]
                       if u.get("soldierId") == soldier_ids[1])["id"]
        assert actor_a != actor_b
        assert_hash_clean(host, client, buckets=["unitsStats"], what="at t=0 (pre-action)")

        # --- pass 1: the SAME-unit variant (disclosed tension), under its own
        #     held blocker so it cannot eat the second pass's hold window ---
        base1 = start_held_blocker(host, client, actor_a)
        print("[test_rw_retry_cancel] hold_chain engaged: the blocker turn's bt_action_end "
              "is deferred and the host's action context stays open")
        run_same_unit_variant(host, client, actor_a)
        wait_hold_released(host, client, base1)

        # --- pass 2: the blocker again, then the SECOND unit's intent, which
        #     sends and denies busy for real ---
        start_held_blocker(host, client, actor_a)
        b_before = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b]
        want_kneeled = not b_before["kneeled"]
        intent_b = client.ok({"cmd": "battle_intent", "kind": "kneel",
                              "actor": actor_b, "kneel": want_kneeled})
        iseq_b = intent_b["iseq"]

        # W1-P7 (WV-D13 item 2): the IN-FLIGHT indicator. Between the send and
        # the host's answer the player used to see nothing at all. The blocker is
        # held open for HOLD_MS, so this window is wide and deterministic.
        sent_banner = banner_of(client)
        assert sent_banner in (STR_ORDER_SENT_TEXT, STR_BUSY_TEXT), (
            f"banner right after the send is {sent_banner!r}, expected either the "
            f"in-flight indicator {STR_ORDER_SENT_TEXT!r} or - if the busy deny had "
            f"already landed - {STR_BUSY_TEXT!r}. A raw STR_ key means the WV-D17 "
            "robocopy was skipped.")
        if sent_banner == STR_ORDER_SENT_TEXT:
            print(f"PASS test_busy_live_fire: in-flight indicator {sent_banner!r} shown "
                  f"while iseq {iseq_b} is unanswered (W1-P7 / WV-D13 item 2)")
        else:
            print("NOTE test_busy_live_fire: the busy deny beat the banner read - the "
                  "in-flight indicator is proven deterministically in "
                  "test_rw_feedback.py PHASE 1a, which defers the host's answer")

        def denied_busy():
            ld = event_state(client).get("lastDeny")
            return ld if ld and ld.get("iseq") == iseq_b else None

        ld = client.wait_for("LIVE deny(busy) via event_state.lastDeny", denied_busy, timeout=15)
        assert ld.get("reason") == "busy", (
            f"expected a LIVE deny reason 'busy' for iseq {iseq_b}, got {ld} - the "
            "hold_chain lever did not keep the host's action context open")
        print(f"PASS test_busy_live_fire: LIVE deny(busy) observed for iseq {iseq_b} "
              f"(unit {actor_b}) - closes the R3-P2 GAP")

        # --- pending state + SS2.6 banner (NOT a drop) ---
        pending = pending_of(client)
        assert pending is not None, (
            "deny(busy) dropped the intent instead of holding it - R2-P7's whole "
            "auto-retry core is not wired")
        assert pending.get("kind") == "kneel" and pending.get("actorId") == actor_b \
            and pending.get("iseq") == iseq_b, \
            f"pending slot holds the wrong plan: {pending}"
        # W1-P7 (WV-D13 item 4): the donor wait driver's SUPPRESSION rule, proven
        # positively rather than assumed. The blocker here is the CLIENT'S OWN
        # admitted turn, so this machine is waiting on ITSELF - the donor
        # explicitly does not name anybody in that case, and SS2.6's generic busy
        # row is the correct text. Asserting busyOwnerSeat first makes that a
        # tested rule instead of a coincidence: if the attribution were wrong the
        # banner would read "Please wait for HostPlayer's action to finish".
        my_seat = event_state(client).get("localSeat")
        owner = event_state(client).get("busyOwnerSeat")
        assert owner == my_seat, (
            f"client attributes the busy window to seat {owner} but its own seat is "
            f"{my_seat} - the blocker IS this client's own admitted turn, so the "
            "donor rule must suppress any peer attribution here")
        banner = banner_of(client)
        assert banner == STR_BUSY_TEXT, (
            f"the pending banner is {banner!r}, expected SS2.6's busy row {STR_BUSY_TEXT!r} - "
            "either showPending() did not fire, the seat-attribution suppression rule "
            "regressed (a peer name here would be wrong: the client is waiting on its "
            "OWN action), or the string table did not resolve (a raw STR_ key here means "
            "the deployed bin/x64/Release/common/Language/en-US.yml is stale relative to "
            "bin/common/)")
        print(f"PASS test_busy_live_fire: intent HELD pending (slot={pending}) with the "
              f"SS2.6 busy banner {banner!r}")

        # --- auto-resubmit on the blocker's bt_action_end, with NO further
        #     client command of any kind ---
        wait_pending_cleared_and_applied(host, client, actor_b, want_kneeled)

        host_b = units_by_id(host.cmd({"cmd": "battle_state"}))[actor_b]
        client_b = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b]
        assert host_b["kneeled"] == want_kneeled, (
            f"the auto-resubmitted kneel never executed on the host: {host_b}")
        assert client_b["kneeled"] == host_b["kneeled"] and client_b["tu"] == host_b["tu"], (
            f"host/client disagree after the auto-resubmit: host={host_b} client={client_b}")
        assert banner_of(client) == "", (
            f"the pending banner is still up ({banner_of(client)!r}) after the retried "
            "action landed - onActionEndApplied() must drop it once nothing is held")
        print(f"PASS test_busy_live_fire: pending auto-resubmitted at the blocker's "
              f"bt_action_end and ADMITTED - unit {actor_b} kneeled={want_kneeled}, "
              f"TU {host_b['tu']} on both machines, with no further client command")

        # --- the acceptance sweep ---
        assert event_state(host).get("queueDepth") == 0, "host queueDepth != 0"
        assert event_state(client).get("queueDepth") == 0, "client queueDepth != 0"
        post_h, _ = assert_hash_clean(host, client, full=True,
                                      what="after the busy/retry cycle (full 9/9)")
        # W1-P8 (WAVE1-RUNBOOK.md SS1 WAVE-1 ADDITIONS / SS2.W4 / WV-D31): the sweep is NINE buckets now - the 7 BattleHashSet members + saveBlob + the dual-set reveal's `revealHostile`.
        assert len(post_h) == 9, f"hash_now full returned {len(post_h)} buckets: {sorted(post_h)}"
        print(f"PASS test_busy_live_fire: {len(post_h)}/9 buckets EQUAL and queueDepth 0 on "
              "both machines after the whole busy/retry cycle")
    finally:
        host.shutdown()
        client.shutdown()


# ----- (b) cancel policy -----

def set_cancel_options(gc, value_map):
    for name, want in value_map.items():
        resp = gc.ok({"cmd": "set_option", "name": name, "value": want})
        assert resp.get("value") is want, f"set_option {name}={want} failed: {resp}"


def make_pending(host, client, actor_a, actor_b):
    """Blocker turn on A (held) + kneel intent on B -> a live pending slot.
    Returns (emitted_base, iseq_b, want_kneeled)."""
    emitted_base = start_held_blocker(host, client, actor_a)
    b_before = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b]
    want_kneeled = not b_before["kneeled"]
    iseq_b = client.ok({"cmd": "battle_intent", "kind": "kneel",
                        "actor": actor_b, "kneel": want_kneeled})["iseq"]
    client.wait_for("pending slot created by deny(busy)",
                    lambda: pending_of(client) or None, timeout=15)
    return emitted_base, iseq_b, want_kneeled


def inject_spot(host, client):
    """RB-D32 HOST lever: a synthetic bt_ev{kind:"spot"} through the real
    CoopEmit::sendEv path with the real next seq. RB-D32's own corollary makes
    it legal - the spike CLIENT applies an unknown ev kind as a state-no-op
    (seq consumed, RW-UNSUPPORTED logged) precisely because inject_ev's spike
    payloads are state-less - and the cancel policy is still evaluated for it,
    which is exactly what this exercises."""
    before = event_state(client).get("lastSeqApplied", 0)
    resp = host.ok({"cmd": "inject_ev", "kind": "spot"})
    client.wait_for("synthetic spot ev applied on the client",
                    lambda: (event_state(client).get("lastSeqApplied", 0) > before) or None,
                    timeout=20)
    return resp


def test_cancel_policy():
    """Packet acceptance (b): pending intent + a synthetic spot ev at
    default-ON options -> pending CLEARED + STR_COOP_CANCEL banner; the same
    at all-OFF -> pending SURVIVES and resubmits at quiescence."""
    host, client, actor, soldier_ids = bring_up_qualifying_battle("cancel")
    try:
        actor_a = actor["id"]
        actor_b = next(u for u in client.cmd({"cmd": "battle_state"})["units"]
                       if u.get("soldierId") == soldier_ids[1])["id"]

        # ===== default-ON: the spot ev CANCELS the held order =====
        set_cancel_options(client, CANCEL_DEFAULTS)  # explicit, not inherited
        base_on, iseq_b, want_kneeled = make_pending(host, client, actor_a, actor_b)
        print(f"[test_cancel_policy] default-ON: pending {pending_of(client)}")

        inject_spot(host, client)
        client.wait_for("pending CLEARED by the spot ev (coopCancelOnEnemySpotted=ON)",
                        lambda: (pending_of(client) is None) or None, timeout=15)
        banner = banner_of(client)
        assert banner == STR_CANCEL_SPOTTED_TEXT, (
            f"cancel banner is {banner!r}, expected SS2.6's STR_COOP_CANCEL_ENEMY_SPOTTED "
            f"text {STR_CANCEL_SPOTTED_TEXT!r} - the message must NAME the trigger, never "
            "be generic (and must actually resolve through the string table)")
        print(f"PASS test_cancel_policy (default-ON): the synthetic spot ev cleared the "
              f"pending intent and showed {banner!r}")

        # ...and it stays cancelled: the blocker's action_end must NOT resurrect
        # it. The spot ev consumed one seq of its own, so the deferred
        # action_end lands at base+3 on the client (turn ev, spot ev,
        # action_end) - wait_hold_released's base+2 floor is satisfied by the
        # spot ev alone, so this waits on the HOST's own emit counter instead.
        b_state = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b]
        host.wait_for("held chain released (deferred blocker action_end emitted)",
                      lambda: (event_state(host).get("lastSeqEmitted", 0) >= base_on + 3) or None,
                      timeout=40)
        time.sleep(2.0)
        assert pending_of(client) is None, "a CANCELLED intent came back at quiescence"
        after = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b]
        assert after["kneeled"] == b_state["kneeled"] != want_kneeled, (
            f"unit {actor_b} kneeled anyway ({after['kneeled']}) - a cancelled intent "
            "must never be resubmitted")
        print(f"PASS test_cancel_policy (default-ON): the cancelled intent was NOT "
              f"resubmitted at quiescence (unit {actor_b} kneeled={after['kneeled']})")

        assert_hash_clean(host, client, buckets=["unitsStats"], what="after the ON cancel")

        # ===== all-OFF: pure auto-retry, the spot ev changes nothing =====
        set_cancel_options(client, {n: False for n in CANCEL_OPTIONS})
        _base_off, iseq_b2, want_kneeled2 = make_pending(host, client, actor_a, actor_b)
        print(f"[test_cancel_policy] all-OFF: pending {pending_of(client)}")

        inject_spot(host, client)
        time.sleep(1.0)  # a cancel, if one were coming, would have landed with the apply
        survived = pending_of(client)
        assert survived is not None, (
            "the spot ev cancelled the pending intent with ALL FOUR toggles OFF - "
            "all-OFF must be pure auto-retry")
        assert survived.get("iseq") == iseq_b2, f"pending slot changed identity: {survived}"
        print(f"PASS test_cancel_policy (all-OFF): the spot ev did NOT cancel - pending "
              f"SURVIVES as {survived}")

        wait_pending_cleared_and_applied(host, client, actor_b, want_kneeled2)
        host_b = units_by_id(host.cmd({"cmd": "battle_state"}))[actor_b]
        client_b = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b]
        assert host_b["kneeled"] == want_kneeled2 and client_b["kneeled"] == host_b["kneeled"], (
            f"the surviving pending never resubmitted/applied: host={host_b} client={client_b}")
        print(f"PASS test_cancel_policy (all-OFF): the surviving pending resubmitted at "
              f"quiescence and was admitted - unit {actor_b} kneeled={want_kneeled2}")

        post_h, _ = assert_hash_clean(host, client, full=True,
                                      what="after both cancel-policy passes (full 9/9)")
        # W1-P8 (WAVE1-RUNBOOK.md SS1 WAVE-1 ADDITIONS / SS2.W4 / WV-D31): the sweep is NINE buckets now - the 7 BattleHashSet members + saveBlob + the dual-set reveal's `revealHostile`.
        assert len(post_h) == 9, f"hash_now full returned {len(post_h)} buckets: {sorted(post_h)}"
        print(f"PASS test_cancel_policy: {len(post_h)}/9 buckets EQUAL after both passes")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    test_option_round_trip()
    test_busy_live_fire()
    test_cancel_policy()
    print("ALL R2-P7 AUTO-RETRY + CANCEL-POLICY TESTS PASSED")


if __name__ == "__main__":
    main()
