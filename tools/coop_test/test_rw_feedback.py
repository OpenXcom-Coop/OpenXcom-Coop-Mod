"""W1-P7 (WAVE1-RUNBOOK.md ruling D7 = WV-D13, parameters WV-D24, string SS2.W8):
ORDER FEEDBACK - "the player always knows what the network did with the click".

Five things this file proves, all with EXACT banner text (never non-emptiness -
that is the wave-1 rule, and a raw STR_ key on screen means the WV-D17 robocopy
of bin/common into bin/x64/Release/common was skipped):

  PHASE 1  the four stages of a click: SENT -> ADMITTED, and SENT -> DENIED.
           `STR_COOP_ORDER_SENT` is the in-flight indicator W1-P7 mints; before
           this packet the window between the click and the host's answer showed
           nothing at all.
  PHASE 2  the AUTO-CLEAR rule for terminal denies (WV-D13 item 1). Before this
           packet the ONLY thing that ever cleared one was the player's own next
           successful action, so a refusal sat on the map strip indefinitely.
  PHASE 3  the SEAT-ATTRIBUTED wait banner (WV-D13 item 4, the donor driver at
           `cbff7951d:BattlescapeState.cpp:5292-5370`): a busy deny raised by the
           HOST's own action names the host - "Please wait for HostPlayer's
           action to finish" - and clears by itself when the retry lands. The
           donor's suppression rule is checked too: when the blocker is the
           CLIENT'S OWN action it must NOT name a peer (that case lives in
           test_rw_retry_cancel.py, which asserts the generic busy row).
  PHASE 4  the INTENT TIMEOUT (WV-D24 = ruling D-11), the NON-NEGOTIABLE half of
           D7. 10 s by default, behind a REAL user option
           (`Options::coopIntentTimeoutSeconds`, an Options.inc.h declaration +
           an Options.cpp OptionInfo registration per WR-25). On fire it shows
           STR_COOP_ACTION_TIMEOUT and RELEASES the IR-2 one-slot lock - today a
           lost intent locks the unit forever. Then the exact late-message rule:
           a late bt_ack/bt_deny for that iseq is PERMANENTLY IGNORED, while a
           late bt_action_end STILL APPLIES.
  PHASE 5  SS2.W8's END TURN local refusal: a CLIENT press during the PLAYER
           side says "Only the host can end the turn", NOT "The turn has already
           ended". Plus the dormant `_txtCoopEndTurn` surface (WV-D13 item 4)
           exists and is HIDDEN on both machines.

THE LEVER. WV-D24 cannot be tested without a genuinely unanswered intent, so
this packet adds `defer_intents {ms,count}` next to R2-P7's `hold_chain` - the
HOST holds the next N bt_intent messages for {ms} before dispatching them
normally. That gives BOTH halves of the ruling in one mechanism: the client
really times out, and the host's answer really arrives late. It carries the same
TEST-ONLY STOPGAP removal note as hold_chain at every code site.

REACHABILITY (WR-3, and this wave's standing anti-vacuity discipline). PHASE 5
presses END TURN on the CLIENT during the PLAYER side, which is the ONLY state
that reaches the handler at all: `btnEndTurnClick`'s whole body sits inside
`if (allowButtons())` and `allowButtons()` requires
`_save->getSide() == FACTION_PLAYER`. An off-turn press never arrives, so
"pressed END TURN off-turn and nothing happened" would be a vacuous assertion.
The side is asserted before the press, and the proof of delivery is POSITIVE -
the exact new string appears, and only `CoopBattleUi::showEndTurnHostOnly()` can
produce it.

FIXTURE: the repro_atom_turn.py / test_rw_retry_cancel.py recipe (WV-D18) - a
live 2-player skirmish through the harness lobby flow, REVIEW4 IR-4 selection
rule, bounded re-roll, two client-owned soldiers via `newbattle_seat_soldier`.

Run:  python tools/coop_test/test_rw_feedback.py
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
FACTION_PLAYER = 0
MAX_REROLLS = 5

SDLK_HOME = 278  # Options::keyBattleCenterUnit default

# Direction -> (dx, dy), 0 = North clockwise (repro_atom_turn.py's own table).
DIR_DX = [0, 1, 1, 1, 0, -1, -1, -1]
DIR_DY = [-1, -1, 0, 1, 1, 1, 0, -1]

# EXACT text, from bin/common/Language/en-US.yml. Asserted as TEXT and never as
# an STR_ key: Language::getString() returns the KEY when the key is missing, so
# a key-shaped assert passes silently against a stale deploy copy (WV-D17).
STR_ORDER_SENT = "Order sent - waiting for the host"
STR_BUSY = "Waiting - another action is in progress"
STR_COST_CHANGED = "Order cancelled - cost changed"
STR_TIMEOUT = "No answer from the host - action dropped"
STR_END_TURN_HOST_ONLY = "Only the host can end the turn"
# The value STR_COOP_TURN_OVER used to carry, and the text SS2.6's WIRE deny row
# STR_COOP_DENY_TURN_OVER still carries. PHASE 5 asserts it is NOT what a client
# END TURN press shows - that confusion is the bug SS2.W8 fixes.
STR_WIRE_TURN_OVER = "The turn has already ended"
WAIT_FOR = "Please wait for {0}'s action to finish"

HOST_PLAYER = "HostPlayer"
CLIENT_PLAYER = "ClientPlayer"

# CoopBattleUi.h kCoopBannerDwellMs. Kept in sync by hand (there is no probe for
# a compile-time constant); a change there fails PHASE 2 loudly, which is the
# right failure - the dwell is a user-visible contract.
BANNER_DWELL_MS = 6000

HOLD_MS = 8000       # hold_chain window for the seat-attributed wait phase
DEFER_MS = 9000      # defer_intents window for the timeout phases
SHORT_TIMEOUT_S = 3  # coopIntentTimeoutSeconds while testing the timeout
LONG_TIMEOUT_S = 120  # ...and while testing anything that must NOT time out


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def units_by_id(battle_state_resp):
    return {u["id"]: u for u in battle_state_resp.get("units", [])}


def event_state(gc):
    return gc.cmd({"cmd": "event_state"})


def banner_of(gc):
    return gc.cmd({"cmd": "battle_state"}).get("coopWaitText", "")


def end_turn_surface_of(gc):
    return gc.cmd({"cmd": "battle_state"}).get("coopEndTurnText")


def pending_of(gc):
    return gc.cmd({"cmd": "battle_state"}).get("coopPendingIntent")


# ----- fixture bring-up (inline copy, repro_atom_kneel.py precedent) -----

def skirmish_host(host, port, player=HOST_PLAYER):
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
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": CLIENT_PLAYER})

    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: lobby(host).get("buttonVisible") or None)


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
    client.wait_for("client battlescape",
                    lambda: session.has_state(client, "BattlescapeState"), timeout=60)
    time.sleep(3)
    host.ok({"cmd": "click_widget", "match": "ok"})
    host.wait_for("host battlescape",
                  lambda: session.has_state(host, "BattlescapeState"), timeout=30)
    session.dismiss_battle_start_overlays(host)
    # W1-P3 (D3): the client enters through a read-only BriefingState pushed OVER
    # its BattlescapeState - every fixture that DRIVES the client must dismiss it.
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
    """REVIEW4 IR-4 SELECTION RULE, verbatim from repro_atom_turn.py: (a) nothing
    spotted yet (an alien in LOS aborts a BA_NONE rotation,
    UnitTurnBState.cpp:114-118), (b) no door within 2 tiles."""
    st = host.cmd({"cmd": "battle_state"})
    if not st.get("ok") or not st.get("inBattle"):
        return None
    if st.get("spotted"):
        return None
    for u in units_by_id(st).values():
        if u.get("soldierId") == soldier_id:
            if has_door_within(host, u["x"], u["y"], u["z"], radius=2):
                return None
            return u
    return None


def bring_up_qualifying_battle(tag):
    """Returns (host, client, actor_unit_dict, soldier_ids)."""
    for attempt in range(1, MAX_REROLLS + 1):
        port = str(48336 + attempt)
        host_dir = make_user_dir(f"rw_fb_{tag}_host_{attempt}")
        client_dir = make_user_dir(f"rw_fb_{tag}_client_{attempt}")
        host = GameClient("host", 49180 + attempt * 2, host_dir)
        client = GameClient("client", 49181 + attempt * 2, client_dir)
        seated = {}
        try:
            bring_up_lobby(host, client, port)
            drive_to_battlescape(host, client, seated, seat_count=2)
            actor = qualifying_actor(host, seated["soldierId"])
            if actor is not None:
                print(f"[test_rw_feedback] fixture qualifies on attempt "
                      f"{attempt}/{MAX_REROLLS} (actor unit id={actor['id']}, "
                      f"soldierId={seated['soldierId']})")
                return host, client, actor, seated["soldierIds"]
            print(f"[test_rw_feedback] re-roll {attempt}/{MAX_REROLLS}: fixture did not "
                  "qualify (hostile spotted, or a door within 2 tiles)")
            host.shutdown()
            client.shutdown()
        except Exception:
            host.shutdown()
            client.shutdown()
            raise
    raise RuntimeError(f"test_rw_feedback: no qualifying fixture in {MAX_REROLLS} boots")


# ----- shared helpers -----

def settle_emits(host, client, timeout=40):
    """Host has nothing left to emit and the client has caught up. Load-bearing
    before any lastSeqEmitted baseline: SS2.4a's quiescent reveal flush can emit
    a standalone `ev reveal` a tick or two after an action settles."""
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


def set_timeout_option(gc, seconds):
    r = gc.ok({"cmd": "set_option", "name": "coopIntentTimeoutSeconds", "value": seconds})
    assert r.get("value") == seconds, \
        f"coopIntentTimeoutSeconds did not round-trip to {seconds}: {r}"


def wait_banner(gc, want, what, timeout=25):
    got = {}

    def hit():
        got["v"] = banner_of(gc)
        return True if got["v"] == want else None

    try:
        gc.wait_for(f"banner {want!r} ({what})", hit, timeout=timeout, interval=0.25)
    except Exception:
        raise AssertionError(
            f"{what}: banner is {got.get('v')!r}, expected EXACTLY {want!r}. A raw "
            "STR_ key here means bin/x64/Release/common/Language/*.yml is stale "
            "relative to bin/common/ (the WV-D17 robocopy was skipped).")
    return got["v"]


def center_on_selection(gc):
    gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
    time.sleep(0.15)


def tile_click(gc, tx, ty, tz, button="right"):
    """W1-P6's `map_tile_click_pos` recipe (test_rw_input_gating.py): the probe
    resolves mapClick's selector-position read, inject_input's WINDOW pixels and
    the icons-panel swallow, and re-verifies the round trip - so a click that
    misses fails LOUDLY instead of making an assertion vacuous."""
    center_on_selection(gc)
    pr = gc.ok({"cmd": "map_tile_click_pos", "x": tx, "y": ty, "z": tz})
    if not pr.get("verified"):
        return None
    gc.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"],
           "button": button})
    return pr


def start_host_local_turn_blocker(host, client, tries=6):
    """Arm hold_chain on the HOST, then make the HOST turn one of ITS OWN units
    with a real right-click (BattlescapeGame::secondaryAction ->
    CoopArbiter::beginHostLocalTurn, origin "host"). The chain runs to
    completion and is then HELD open, so the host's action context stays open
    and onIntent() answers deny("busy") for the whole window - and the busy
    owner is SEAT 0, which is what makes the seat attribution testable at all.

    Returns the host's lastSeqEmitted BEFORE the blocker.

    A host-local turn (not a client intent, and not a kneel) is required here:
    a kneel is chain-less (RB-D13) so hold_chain never latches it, and a CLIENT
    intent would make the busy owner the CLIENT's own seat - the case the donor
    driver deliberately SUPPRESSES."""
    settle_emits(host, client)

    st = host.cmd({"cmd": "battle_state"})
    sel = st.get("selectedId")
    units = units_by_id(st)
    unit = units.get(sel)
    assert unit is not None, f"host has no selected unit: selectedId={sel}"
    assert unit.get("coop") == COOP_SEAT_0, (
        f"host's selected unit {sel} is seat {unit.get('coop')}, not 0 - this phase "
        "needs the HOST to be the busy owner, which is a FIXTURE requirement")

    for attempt in range(1, tries + 1):
        emitted_base = event_state(host).get("lastSeqEmitted", 0)
        hold = host.ok({"cmd": "hold_chain", "ms": HOLD_MS})
        assert hold.get("ms") == HOLD_MS, f"hold_chain did not arm: {hold}"

        u = units_by_id(host.cmd({"cmd": "battle_state"}))[sel]
        # A DIFFERENT direction each attempt: an unclickable target tile (off the
        # viewport, or under the icons panel) would otherwise make every retry
        # fail identically.
        to_dir = (u["direction"] + 2 + attempt - 1) % 8
        if to_dir == u["direction"]:
            to_dir = (to_dir + 1) % 8
        pr = tile_click(host, u["x"] + DIR_DX[to_dir], u["y"] + DIR_DY[to_dir], u["z"],
                        button="right")
        if pr is None:
            print(f"[test_rw_feedback] blocker attempt {attempt}/{tries}: tile for dir "
                  f"{to_dir} is not clickable right now - retrying")
            host.ok({"cmd": "hold_chain", "ms": 1})  # disarm the unused hold
            time.sleep(0.5)
            continue
        time.sleep(1.0)

        es = event_state(host)
        if es.get("busyOwnerSeat") == COOP_SEAT_0 \
                and es.get("lastSeqEmitted", 0) == emitted_base + 1:
            # THE LEVER PROOF, same shape as test_rw_retry_cancel's: exactly ONE
            # new seq (the turn ev). A chain that quiesced normally would have
            # emitted its bt_action_end as the very next seq.
            print(f"[test_rw_feedback] host-local turn blocker engaged on attempt "
                  f"{attempt} (unit {sel} -> dir {to_dir}, busyOwnerSeat=0, "
                  f"action_end deferred)")
            return emitted_base
        print(f"[test_rw_feedback] blocker attempt {attempt}/{tries} did not engage "
              f"(busyOwnerSeat={es.get('busyOwnerSeat')}, "
              f"seq {emitted_base} -> {es.get('lastSeqEmitted')}) - retrying")
        # Let the hold expire before the next attempt so state is clean.
        time.sleep(HOLD_MS / 1000.0 + 1.0)
        settle_emits(host, client)
        st = host.cmd({"cmd": "battle_state"})
        sel = st.get("selectedId")

    raise AssertionError(
        "could not place a host-local turn blocker - FIXTURE failure (the camera "
        "or the clickable-tile probe, not the feature under test)")


# ===========================================================================
# PHASE 1 + 2: sent -> admitted, sent -> denied, and the terminal auto-clear
# ===========================================================================

def test_sent_denied_and_autoclear():
    host, client, actor, soldier_ids = bring_up_qualifying_battle("sent")
    try:
        actor_b = next(u for u in client.cmd({"cmd": "battle_state"})["units"]
                       if u.get("soldierId") == soldier_ids[1])["id"]
        assert_hash_clean(host, client, buckets=["unitsStats"], what="at t=0")

        # ----- the dormant END-TURN surface (WV-D13 item 4) -----
        for gc, who in ((host, "host"), (client, "client")):
            surf = end_turn_surface_of(gc)
            assert surf == "", (
                f"{who}: the re-added _txtCoopEndTurn surface should exist and be "
                f"HIDDEN in W1-P7 (its readiness tally is W1-P13's), got {surf!r}")
        print("PASS dormant surface: _txtCoopEndTurn exists and is hidden on both "
              "machines (W1-P13 drives it)")

        # ----- PHASE 1a: SENT -----
        set_timeout_option(client, LONG_TIMEOUT_S)  # nothing may time out here
        settle_emits(host, client)
        host.ok({"cmd": "defer_intents", "ms": 2500, "count": 1})

        b_before = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b]
        want_kneeled = not b_before["kneeled"]
        sent = client.ok({"cmd": "battle_intent", "kind": "kneel",
                          "actor": actor_b, "kneel": want_kneeled})
        iseq_sent = sent["iseq"]

        wait_banner(client, STR_ORDER_SENT, "PHASE 1a: order sent", timeout=10)
        infl = event_state(client).get("inFlight")
        assert infl and infl.get("iseq") == iseq_sent and infl.get("actorId") == actor_b, (
            f"in-flight slot does not hold the sent intent: {infl}")
        print(f"PASS PHASE 1a (SENT): banner {STR_ORDER_SENT!r} while iseq {iseq_sent} "
              f"is in flight (deferred by the host for 2.5 s)")

        # ----- PHASE 1b: ADMITTED -----
        def landed():
            cs = client.cmd({"cmd": "battle_state"})
            u = units_by_id(cs).get(actor_b)
            return True if (u and u["kneeled"] == want_kneeled
                            and event_state(client).get("queueDepth") == 0) else None
        client.wait_for("deferred kneel admitted + applied", landed, timeout=30)
        assert banner_of(client) == "", (
            f"the order-sent banner is still up ({banner_of(client)!r}) after the "
            "action completed - onActionEndApplied() must drop it")
        host_b = units_by_id(host.cmd({"cmd": "battle_state"}))[actor_b]
        assert host_b["kneeled"] == want_kneeled, f"host never ran the kneel: {host_b}"
        assert event_state(client).get("inFlight") is None, "in-flight slot not released"
        print("PASS PHASE 1b (ADMITTED): the order landed on both machines and the "
              "in-flight banner cleared itself")
        assert_hash_clean(host, client, buckets=["unitsStats"], what="after the admitted order")

        # ----- PHASE 1c: DENIED (terminal) -----
        # A deliberately WRONG tuBasis: SS2.3's validator recomputes the cost and
        # answers cost_changed on strict inequality either way. A terminal answer
        # about the plan itself - exactly the class WV-D13 item 1 is about.
        b_now = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b]
        deny_iseq = client.ok({"cmd": "battle_intent", "kind": "kneel", "actor": actor_b,
                               "kneel": not b_now["kneeled"], "tuBasisOverride": 999})["iseq"]
        wait_banner(client, STR_COST_CHANGED, "PHASE 1c: terminal deny", timeout=15)
        ld = event_state(client).get("lastDeny")
        assert ld and ld.get("iseq") == deny_iseq and ld.get("reason") == "cost_changed", (
            f"event_state.lastDeny bookkeeping is wrong after the deny: {ld}")
        assert event_state(client).get("inFlight") is None, (
            "a terminal deny must release the in-flight slot")
        after = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b]
        assert after["kneeled"] == b_now["kneeled"], "a denied kneel changed state anyway"
        print(f"PASS PHASE 1c (DENIED): banner {STR_COST_CHANGED!r}, lastDeny={ld}, "
              "nothing executed")

        # ----- PHASE 2: the AUTO-CLEAR rule (WV-D13 item 1) -----
        # NOT vacuous: the banner was just asserted PRESENT with exact text, and
        # from here the test sends NOTHING - no intent, no click, no cancel. The
        # only thing that can empty it is the dwell rule this packet adds. The
        # pre-W1-P7 build would leave it up forever.
        t0 = time.time()
        client.wait_for("terminal banner auto-clears with no further input",
                        lambda: (banner_of(client) == "") or None,
                        timeout=(BANNER_DWELL_MS / 1000.0) + 12, interval=0.25)
        elapsed_ms = (time.time() - t0) * 1000.0
        assert elapsed_ms > BANNER_DWELL_MS * 0.5, (
            f"the terminal banner vanished after only {elapsed_ms:.0f} ms - that is "
            f"not the {BANNER_DWELL_MS} ms dwell, something else cleared it")
        assert event_state(client).get("lastDeny") == ld, (
            "the auto-clear disturbed event_state.lastDeny - the banner is "
            "presentation, the bookkeeping must survive it")
        print(f"PASS PHASE 2 (AUTO-CLEAR): the terminal deny cleared itself after "
              f"~{elapsed_ms:.0f} ms with no further input, and lastDeny is intact")

        post_h, _ = assert_hash_clean(host, client, full=True,
                                      what="after the sent/denied/auto-clear phases")
        assert all(post_h.values()), f"empty bucket in {post_h}"
        print(f"PASS: {len(post_h)} buckets EQUAL after PHASE 1+2")
    finally:
        host.shutdown()
        client.shutdown()


# ===========================================================================
# PHASE 3: the seat-attributed wait banner (the donor driver)
# ===========================================================================

def test_seat_attributed_wait():
    host, client, actor, soldier_ids = bring_up_qualifying_battle("wait")
    try:
        actor_b = next(u for u in client.cmd({"cmd": "battle_state"})["units"]
                       if u.get("soldierId") == soldier_ids[1])["id"]
        set_timeout_option(client, LONG_TIMEOUT_S)

        emitted_base = start_host_local_turn_blocker(host, client)

        b_before = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b]
        want_kneeled = not b_before["kneeled"]
        iseq_b = client.ok({"cmd": "battle_intent", "kind": "kneel",
                            "actor": actor_b, "kneel": want_kneeled})["iseq"]

        def denied_busy():
            ld = event_state(client).get("lastDeny")
            return ld if ld and ld.get("iseq") == iseq_b else None
        ld = client.wait_for("LIVE deny(busy) while the HOST's own action holds the slot",
                             denied_busy, timeout=20)
        assert ld.get("reason") == "busy", f"expected busy, got {ld}"

        # ATTRIBUTION, asserted as data before it is asserted as text: the client
        # must believe seat 0 owns the slot. (Its own seat is 1; if it thought the
        # blocker were its own action the donor rule says show the generic row.)
        owner = event_state(client).get("busyOwnerSeat")
        assert owner == COOP_SEAT_0, (
            f"client attributes the busy window to seat {owner}, expected 0 (the "
            "HOST's own local turn is the blocker here)")

        want_text = WAIT_FOR.replace("{0}", HOST_PLAYER)
        got = banner_of(client)
        assert got == want_text, (
            f"the wait banner is {got!r}, expected EXACTLY {want_text!r}. If it is "
            f"{STR_BUSY!r} the seat could not be NAMED (seatName() empty and the "
            "2-player getCurrentClientName() bridge did not resolve); a raw STR_ key "
            "means the WV-D17 robocopy was skipped.")
        assert pending_of(client) is not None, "the busy-denied intent was not HELD"
        print(f"PASS PHASE 3 (WAIT): a busy deny raised by the HOST's own action shows "
              f"{got!r} - seat-attributed, not generic")

        # ...and it CLEARS BY ITSELF when the auto-retry lands (owner smoke S4).
        def resolved():
            cs = client.cmd({"cmd": "battle_state"})
            u = units_by_id(cs).get(actor_b)
            return True if (cs.get("coopPendingIntent") is None and u
                            and u["kneeled"] == want_kneeled
                            and event_state(client).get("queueDepth") == 0
                            and event_state(host).get("queueDepth") == 0) else None
        client.wait_for("held order auto-retried and admitted after the hold expires",
                        resolved, timeout=60)
        client.wait_for("wait banner clears by itself once the retry lands",
                        lambda: (banner_of(client) == "") or None, timeout=20)
        assert event_state(host).get("lastSeqEmitted", 0) >= emitted_base + 2, (
            "the held chain never released its deferred bt_action_end")
        print("PASS PHASE 3 (CLEARS BY ITSELF): the waiting message went away when the "
              "auto-retried order was admitted, with no further client command")

        post_h, _ = assert_hash_clean(host, client, full=True,
                                      what="after the seat-attributed wait cycle")
        print(f"PASS: {len(post_h)} buckets EQUAL after PHASE 3")
    finally:
        host.shutdown()
        client.shutdown()


# ===========================================================================
# PHASE 4: the intent timeout (WV-D24) + the late-message rule
# ===========================================================================

def test_intent_timeout():
    host, client, actor, soldier_ids = bring_up_qualifying_battle("timeout")
    try:
        actor_b = next(u for u in client.cmd({"cmd": "battle_state"})["units"]
                       if u.get("soldierId") == soldier_ids[1])["id"]

        # ----- 4a: the option is REAL (WR-25) -----
        default = client.ok({"cmd": "set_option", "name": "coopIntentTimeoutSeconds"})
        assert default.get("value") == 10, (
            f"coopIntentTimeoutSeconds default is {default.get('value')}, expected "
            "WV-D24's ruled 10 s (Options.cpp OptionInfo registration)")
        for want in (SHORT_TIMEOUT_S, 30, SHORT_TIMEOUT_S):
            set_timeout_option(client, want)
            rb = client.ok({"cmd": "set_option", "name": "coopIntentTimeoutSeconds"})
            assert rb.get("value") == want, f"option did not stay {want}: {rb}"
        print(f"PASS PHASE 4a: coopIntentTimeoutSeconds defaults to 10 (WV-D24) and "
              f"round-trips through set_option - a real OptionInfo, not a static")

        # ----- 4b: TIMEOUT fires, releases the lock, and a late DENY is ignored -----
        settle_emits(host, client)
        deny_before = event_state(client).get("lastDeny")
        late_before = event_state(client).get("lateAnswersIgnored", 0)
        host.ok({"cmd": "defer_intents", "ms": DEFER_MS, "count": 1})

        b_now = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b]
        # tuBasisOverride 999 guarantees the host's eventual answer is a DENY
        # (cost_changed), which is the message the timeout must then ignore.
        lost_iseq = client.ok({"cmd": "battle_intent", "kind": "kneel", "actor": actor_b,
                               "kneel": not b_now["kneeled"],
                               "tuBasisOverride": 999})["iseq"]
        t_sent = time.time()
        wait_banner(client, STR_TIMEOUT, "PHASE 4b: intent timeout",
                    timeout=SHORT_TIMEOUT_S + 15)
        fired_after = time.time() - t_sent
        assert fired_after >= SHORT_TIMEOUT_S * 0.6, (
            f"the timeout fired after only {fired_after:.1f} s with the option at "
            f"{SHORT_TIMEOUT_S} s - it is not reading the option")

        es = event_state(client)
        assert es.get("intentTimeouts") == 1, f"intentTimeouts={es.get('intentTimeouts')}"
        assert es.get("lastTimedOutIseq") == lost_iseq, (
            f"lastTimedOutIseq={es.get('lastTimedOutIseq')}, expected {lost_iseq}")
        assert es.get("inFlight") is None, (
            "the IR-2 one-slot lock was NOT released by the timeout - this is the bug "
            "WV-D24 exists to fix (a lost intent locking the unit forever)")
        print(f"PASS PHASE 4b (TIMEOUT): iseq {lost_iseq} timed out after "
              f"{fired_after:.1f} s, banner {STR_TIMEOUT!r}, in-flight slot released")

        # ...and the UNIT IS COMMANDABLE AGAIN: a fresh intent for the SAME actor
        # ships. Before this packet sendClientIntent() dropped it locally forever.
        b2 = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b]
        again = client.ok({"cmd": "battle_intent", "kind": "kneel", "actor": actor_b,
                           "kneel": not b2["kneeled"]})
        assert again.get("iseq") and again["iseq"] != lost_iseq, (
            f"a fresh intent for the timed-out actor was refused: {again}")
        client.wait_for("the fresh order lands",
                        lambda: (units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b]["kneeled"]
                                 != b2["kneeled"]) or None, timeout=30)
        print(f"PASS PHASE 4b (COMMANDABLE AGAIN): unit {actor_b} accepted a new order "
              f"(iseq {again['iseq']}) after the timeout")

        # ...and the LATE DENY, when the host finally answers, changes NOTHING.
        client.wait_for("the host's LATE answer for the timed-out iseq arrives",
                        lambda: (event_state(client).get("lateAnswersIgnored", 0)
                                 > late_before) or None,
                        timeout=DEFER_MS / 1000.0 + 25)
        es = event_state(client)
        assert es.get("lateAnswersIgnored") == late_before + 1, (
            f"lateAnswersIgnored={es.get('lateAnswersIgnored')}, expected "
            f"{late_before + 1} - exactly one late answer should have been dropped")
        assert es.get("lastDeny") == deny_before, (
            f"a LATE deny updated event_state.lastDeny ({es.get('lastDeny')} vs "
            f"{deny_before}) - WV-D24 says it is PERMANENTLY IGNORED")
        assert banner_of(client) != STR_COST_CHANGED, (
            "the late deny raised its banner anyway")
        print("PASS PHASE 4b (LATE DENY IGNORED): the host's late bt_deny was DELIVERED "
              "(lateAnswersIgnored 0 -> 1) and changed nothing - not lastDeny, not the "
              "banner, not the input lock")

        # ----- 4c: a late bt_action_end STILL APPLIES -----
        settle_emits(host, client)
        host.ok({"cmd": "defer_intents", "ms": DEFER_MS, "count": 1})
        b3 = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b]
        want3 = not b3["kneeled"]
        late_before2 = event_state(client).get("lateAnswersIgnored", 0)
        iseq3 = client.ok({"cmd": "battle_intent", "kind": "kneel",
                           "actor": actor_b, "kneel": want3})["iseq"]
        wait_banner(client, STR_TIMEOUT, "PHASE 4c: timeout on a VALID intent",
                    timeout=SHORT_TIMEOUT_S + 15)
        assert event_state(client).get("lastTimedOutIseq") == iseq3

        def applied_late():
            cs = client.cmd({"cmd": "battle_state"})
            hs = host.cmd({"cmd": "battle_state"})
            cu = units_by_id(cs).get(actor_b)
            hu = units_by_id(hs).get(actor_b)
            return True if (cu and hu and cu["kneeled"] == want3
                            and hu["kneeled"] == want3) else None
        client.wait_for("the LATE bt_action_end still applies on both machines",
                        applied_late, timeout=DEFER_MS / 1000.0 + 40)
        es = event_state(client)
        assert es.get("lateAnswersIgnored") == late_before2 + 1, (
            f"expected exactly one ignored late bt_ack, got "
            f"{es.get('lateAnswersIgnored')} vs {late_before2}")
        print(f"PASS PHASE 4c (LATE ACTION_END APPLIES): iseq {iseq3} timed out, its late "
              "bt_ack was ignored, and the host's bt_action_end STILL applied - unit "
              f"{actor_b} kneeled={want3} on BOTH machines (host truth carries state)")

        post_h, _ = assert_hash_clean(host, client, full=True,
                                      what="after the timeout phases")
        print(f"PASS: {len(post_h)} buckets EQUAL after PHASE 4")
    finally:
        host.shutdown()
        client.shutdown()


# ===========================================================================
# PHASE 5: SS2.W8's END TURN local refusal
# ===========================================================================

def test_end_turn_refusal():
    host, client, actor, soldier_ids = bring_up_qualifying_battle("endturn")
    try:
        settle_emits(host, client)

        # REACHABILITY (WR-3 / SS2.W8): btnEndTurnClick's body sits inside
        # `if (allowButtons())`, which requires _save->getSide() == FACTION_PLAYER.
        # Pressing off-turn never reaches the handler, so asserting anything about
        # an off-turn press would be VACUOUS. Assert the precondition first.
        cs = client.cmd({"cmd": "battle_state"})
        assert cs.get("side") == FACTION_PLAYER, (
            f"client side is {cs.get('side')}, not FACTION_PLAYER - the END TURN "
            "handler is not reachable and this assertion would be vacuous (WR-3)")
        assert event_state(client).get("hostSim") is not True, \
            "this machine must be the CLIENT for SS2.W8's refusal to be reachable"
        turn_before = cs.get("turn")
        banner_before = banner_of(client)
        assert banner_before != STR_END_TURN_HOST_ONLY, (
            "the refusal text is already on screen before the press - the assertion "
            "below could not tell the press apart from the previous state")

        client.ok({"cmd": "battle_action", "action": "end_turn_button"})

        got = wait_banner(client, STR_END_TURN_HOST_ONLY,
                          "PHASE 5: client END TURN during the PLAYER side", timeout=15)
        assert got != STR_WIRE_TURN_OVER, "still showing the old wire-deny text"
        after = client.cmd({"cmd": "battle_state"})
        assert after.get("turn") == turn_before and after.get("side") == FACTION_PLAYER, (
            f"the client's END TURN press actually ended the turn: "
            f"{turn_before}/{FACTION_PLAYER} -> {after.get('turn')}/{after.get('side')}")
        print(f"PASS PHASE 5: a CLIENT END TURN press during ITS OWN side shows "
              f"{got!r} - NOT {STR_WIRE_TURN_OVER!r} (SS2.W8 / WV-D23), and the turn "
              "did not advance")

        # The refusal is LOCAL: no wire deny reason was added (SS2.2 unchanged), so
        # nothing about it may show up in the deny bookkeeping.
        ld = event_state(client).get("lastDeny")
        assert not ld or ld.get("reason") != "turn_over" or ld.get("iseq"), (
            f"the local END TURN refusal produced a WIRE deny: {ld} - SS2.W8 forbids "
            "growing the SS2.2 enum for it")

        post_h, _ = assert_hash_clean(host, client, full=True,
                                      what="after the END TURN refusal")
        print(f"PASS PHASE 5: {len(post_h)} buckets EQUAL after the refused press")

        # The dormant surface again, at the end of a real battle rather than at t=0.
        for gc, who in ((host, "host"), (client, "client")):
            assert end_turn_surface_of(gc) == "", \
                f"{who}: _txtCoopEndTurn became visible without W1-P13's tally"
        print("PASS PHASE 5: _txtCoopEndTurn is still dormant on both machines")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    test_sent_denied_and_autoclear()
    test_seat_attributed_wait()
    test_intent_timeout()
    test_end_turn_refusal()
    print("ALL W1-P7 ORDER-FEEDBACK TESTS PASSED")


if __name__ == "__main__":
    main()
