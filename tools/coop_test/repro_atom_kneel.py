"""R3-P2 (rewrite spike, SPIKE-RUNBOOK.md R3-P2 packet text): ATOM kneel +
burst + spike sweep - the second atom (chain-less path, RB-D13) plus the r2
acceptance bullets that need two atoms (burst/drain proof, forced-mismatch
proof).

FIXTURE: same recipe/precedent as repro_atom_turn.py (R3-P1) - a live
2-player skirmish through the harness lobby flow, the same SELECTION RULE +
bounded re-roll loop (REVIEW4 IR-4), reused here via inline copy (this
file's own precedent: repro_atom_turn.py; that file's own precedent:
test_rw_faction_setup.py). Extended for R3-P2's burst/drain proof: TWO
client-owned soldiers (harnessSeatOneSoldier's new `index` param, added by
this packet) so a mixed turn+kneel burst can drive two DIFFERENT actors
back-to-back. A genuine host-side "busy" admission race was ATTEMPTED with
this same two-unit setup (actor A's longest-possible turn, actor B's kneel
fired immediately after with no sleep) but could not be made to land - see
run_burst_drain_proof()'s own doc comment for the diagnostic finding
(BState think()-loop resolution in this harness is effectively
un-throttled, faster than a second TestServer command's own round trip).
SUPERSEDED (R2-P7, 2026-09-02): the owner-approved `hold_chain {ms}`
TestServer lever now makes a LIVE deny("busy") deterministic, and
tools/coop_test/test_rw_retry_cancel.py fires it end-to-end (deny -> pending
-> auto-resubmit). THIS file is deliberately left as-is: its burst proof is
about in-order drain across origins, not about busy, and it stays a
lever-free natural-race regression.
The "oldest-denied-first observable via lastDeny" clause is instead proven
via a not_your_unit deny mixed into the same burst (recordDeny()'s
bookkeeping fires identically for every deny reason, not just "busy" - see
that function's own doc comment).

RB-D13 recap (why kneel's code shape differs from turn's): kneel is
CHAIN-LESS - no BState is ever pushed, so admit -> call -> emit -> pop all
happen synchronously inside ONE call (CoopArbiter::onIntent()'s "kneel"
branch for an admitted remote intent, or BattlescapeState::btnKneelClick's
host-local branch). The actual emit lives in ONE thin hook inside
BattlescapeGame::kneel() itself (coopOnKneelFinished, connectionTCP.cpp),
generalized by this packet from R2-P5's original admitted-intent-only inline
version so it fires identically for BOTH the host's own local kneel click
and an admitted remote intent - see this packet's final report for why that
refactor was necessary (R2-P5 only ever covered the intent-admitted origin).

Two sessions:
  test_atom_kneel_e2e()  - ONE session: kneel via battle_intent (RB-D13
                            chain-less e2e), a faithful-UI variant via a
                            real SDLK_k keypress (RB-D10 btnKneelClick
                            intercept, Options::keyBattleKneel default),
                            deny paths (not_your_unit, cost_changed), and
                            the burst/drain proof (r2 acceptance 1).
  test_forced_mismatch()  - a SEPARATE, freshly-booted session: corrupt_
                            bucket{unitsStats} on the host (poking a unit
                            OTHER than the one about to kneel - see that
                            function's own comment for why), then a kneel
                            via the HOST's OWN local input -> client
                            desyncSeen/frozen/bundle/banner (r2 acceptance
                            3). Ends with an explicit clean shutdown - a
                            desync-frozen battle cannot be un-frozen (SS2.8
                            "no partial repair"), so this session is never
                            reused for anything else.

Run:  python tools/coop_test/repro_atom_kneel.py
"""

import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import (assert_hash_clean, assert_events, assert_turret_parity,
                     assert_reveal_parity)

FACTION_PLAYER = 0
COOP_SEAT_NONE = -1
COOP_SEAT_0 = 0
COOP_SEAT_1 = 1
MAX_REROLLS = 5

SDLK_TAB = 9    # Options::keyBattleNextUnit default (test_rw_input_gating.py precedent)
SDLK_K = 107    # Options::keyBattleKneel default (SDLK_k, Options.cpp:337)


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def units_by_id(battle_state_resp):
    return {u["id"]: u for u in battle_state_resp.get("units", [])}


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


def drive_to_battlescape(host, client, seated_holder, seat_count=1):
    """Steps 5-7 of the skirmish lobby flow (repro_atom_turn.py precedent),
    extended with the fixture seat stamp(s) between reaching NewBattleState
    and clicking OK. `seat_count` seats that many DIFFERENT soldiers to
    COOP_SEAT_1 via this packet's own harnessSeatOneSoldier `index`
    extension - repro_atom_turn.py's single-actor recipe used 1 (index
    defaults to 0); the burst/drain proof needs 2 real client-owned units."""
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

    time.sleep(3)  # let both logs flush the handshake lines before reading them

    host.ok({"cmd": "click_widget", "match": "ok"})
    host.wait_for("host battlescape",
                  lambda: session.has_state(host, "BattlescapeState"), timeout=30)
    assert session.has_state(host, "BattlescapeState"), \
        f"host should reach BattlescapeState after OK, stack={states(host)}"

    dismiss_battle_start_overlays(host)

    # W1-P3 (SS1 WAVE-1 ADDITIONS trap 2 / WV-D9): the client now enters the
    # battle through a read-only BriefingState pushed OVER its
    # BattlescapeState, so every fixture that DRIVES the client must dismiss
    # it explicitly - injected input would otherwise land on the briefing and
    # screen-projection probes would compute against the GEOSCAPE viewport the
    # briefing holds. No-op on a stack with no BriefingState.
    session.dismiss_client_briefing(client)


def dismiss_battle_start_overlays(host, timeout=10):
    """Same pre-existing surprise repro_atom_turn.py's own module docstring
    names (its "NEXT" section carried it forward to this packet): a freshly
    generated battle stacks vanilla's "Turn 1 begins" (NextTurnState) and
    pre-battle equip (InventoryState) over BattlescapeState. Game::run()
    only think()s _states.back(), so the host's whole BState machine (and
    therefore any admitted coop action, turn OR kneel) never ticks until
    these are dismissed. Host-only - the client loads the streamed blob
    straight into BattlescapeState with no generation-time popups."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = states(host)
        if st and st[-1] == "BattlescapeState":
            return
        host.ok({"cmd": "inject_input", "kind": "key", "key": 27})  # SDLK_ESCAPE / Options::keyCancel
        time.sleep(0.3)
    raise TimeoutError(f"host: battle-start overlays never cleared, stack={states(host)}")


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
    """REVIEW4 IR-4 SELECTION RULE, reused verbatim from repro_atom_turn.py
    (RB-D15's own text calls out this file's kneel reaction-fire branch by
    name, so the same empty-spotted-set guard applies even though the
    no-door clause is really only a turn/door concern) - see that file's own
    module docstring for the exact (a)/(b) predicates."""
    st = host.cmd({"cmd": "battle_state"})
    if not st.get("ok") or not st.get("inBattle"):
        return None
    if st.get("spotted"):
        return None  # rule (a)
    units = units_by_id(st)
    for u in units.values():
        if u.get("soldierId") == soldier_id:
            if has_door_within(host, u["x"], u["y"], u["z"], radius=2):
                return None  # rule (b)
            return u
    return None


def bring_up_qualifying_battle(seat_count=1, tag="kneel"):
    """Returns (host, client, actor_unit_dict, soldier_ids list)."""
    for attempt in range(1, MAX_REROLLS + 1):
        port = str(48196 + attempt)
        host_dir = make_user_dir(f"repro_atom_{tag}_host_{attempt}")
        client_dir = make_user_dir(f"repro_atom_{tag}_client_{attempt}")
        host = GameClient("host", 49030 + attempt * 2, host_dir)
        client = GameClient("client", 49031 + attempt * 2, client_dir)
        seated = {}
        try:
            bring_up_lobby(host, client, port)
            drive_to_battlescape(host, client, seated, seat_count=seat_count)

            soldier_id = seated["soldierId"]
            actor = qualifying_actor(host, soldier_id)
            if actor is not None:
                print(f"[repro_atom_kneel] fixture qualifies on attempt {attempt}/{MAX_REROLLS} "
                      f"(actor unit id={actor['id']}, soldierId={soldier_id}, "
                      f"pos=({actor['x']},{actor['y']},{actor['z']}))")
                return host, client, actor, seated["soldierIds"]

            print(f"[repro_atom_kneel] re-roll {attempt}/{MAX_REROLLS}: fixture did not "
                  "qualify (a hostile already spotted, or a door within 2 tiles) - "
                  "tearing down and retrying")
            host.shutdown()
            client.shutdown()
        except Exception:
            host.shutdown()
            client.shutdown()
            raise

    raise RuntimeError(f"repro_atom_kneel: no qualifying fixture found in {MAX_REROLLS} boots")


def event_seq_baseline(client):
    return client.cmd({"cmd": "event_state"}).get("lastSeqApplied", 0)


def wait_settled(host, client, baseline, timeout=15):
    """Waits for queueDepth to return to 0 on BOTH machines AND for the
    client's lastSeqApplied to have advanced past `baseline` - same
    contract as repro_atom_turn.py's own helper (precedent)."""
    def settled():
        hs = host.cmd({"cmd": "event_state"})
        cs = client.cmd({"cmd": "event_state"})
        return bool(hs.get("ok") and cs.get("ok")
                    and hs.get("queueDepth") == 0 and cs.get("queueDepth") == 0
                    and cs.get("lastSeqApplied", 0) > baseline)
    client.wait_for("action settled (new seq applied, queueDepth 0 on both machines)",
                     settled, timeout=timeout)


def run_ui_variant(host, client, actor_id, was_kneeled):
    """ONE faithful-UI variant step (packet text): a real SDLK_k keypress via
    inject_input, proving the RB-D10 BattlescapeState::btnKneelClick
    intercept end-to-end - the client SENDS an intent (instead of running
    vanilla locally) exactly as the battle_intent-driven path did, but
    reached through the real keybinding this time (BattlescapeState.cpp's
    own onKeyboardPress registration, Options::keyBattleKneel default
    SDLK_k). A keypress (not a click) sidesteps this repro family's own
    documented WATCH note about inject_input's click kind sending no
    preceding SDL_MOUSEMOTION - keys need no hover state."""
    selected = None
    for _ in range(12):
        st = client.cmd({"cmd": "battle_state"})
        selected = st.get("selectedId")
        if selected == actor_id:
            break
        client.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.1)
    assert selected == actor_id, (
        f"could not Tab-cycle the client's selection onto unit {actor_id} "
        f"(last selectedId={selected}) - see test_rw_input_gating.py's own "
        "'initial-selection' note on why a fresh load may start elsewhere")

    before_tu = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_id]["tu"]
    baseline = event_seq_baseline(client)
    client.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_K})

    wait_settled(host, client, baseline)

    host_unit = units_by_id(host.cmd({"cmd": "battle_state"}))[actor_id]
    client_unit = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_id]

    assert client_unit["kneeled"] != was_kneeled, (
        f"faithful-UI SDLK_k keypress did not toggle unit {actor_id}'s kneel state "
        f"(client kneeled={client_unit['kneeled']}, was {was_kneeled}) - the RB-D10 "
        "btnKneelClick intercept did not fire end-to-end")
    assert host_unit["kneeled"] == client_unit["kneeled"], (
        f"host/client kneel state differ: host={host_unit['kneeled']} client={client_unit['kneeled']}")
    assert client_unit["tu"] < before_tu, "client TU did not decrease after the faithful-UI kneel"

    assert_hash_clean(host, client, buckets=["unitsStats"], what="post-UI-variant")
    # RW-REVEAL-SYNC (SS2.4a): kneeling changes the unit's eye height, so it can
    # discover (or stop being able to see) tiles - whatever the HOST discovered
    # must have ridden this action's own ev/action_end.
    assert_reveal_parity(host, client, "post-UI-variant",
                         extra_positions=[(host_unit["x"], host_unit["y"], host_unit["z"])])
    print(f"PASS run_ui_variant: real SDLK_k keypress toggled unit {actor_id}'s kneel to "
          f"{client_unit['kneeled']} via the RB-D10 btnKneelClick intercept (client sent the "
          "intent, host executed + emitted, client applied), hash-clean")


def run_deny_paths(client, host_state, seated_soldier_id, actor_id, actor_kneeled, actor_tu_basis):
    """Two kneel-specific deny checks (packet text's own deny-path clause,
    generalized to kneel's own validator per this packet's scope):
      not_your_unit - client intents a HOST-owned unit.
      cost_changed  - client intents its OWN unit with a deliberately wrong
                      tuBasisOverride (RB-D32's own "G5 stale-basis lever"),
                      proving validateKneel()'s recomputed-cost check."""
    host_units = units_by_id(host_state)
    host_owned = next(
        u for u in host_units.values()
        if u.get("isPlayerSoldier") and u.get("coop") == COOP_SEAT_0
        and u.get("soldierId") != seated_soldier_id)

    intent_resp = client.ok({"cmd": "battle_intent", "kind": "kneel",
                              "actor": host_owned["id"], "kneel": not host_owned["kneeled"]})
    iseq = intent_resp["iseq"]

    def denied(want_iseq):
        return lambda: (lambda ld: ld if ld and ld.get("iseq") == want_iseq else None)(
            client.cmd({"cmd": "event_state"}).get("lastDeny"))

    ld = client.wait_for("deny(not_your_unit) via event_state.lastDeny", denied(iseq), timeout=10)
    assert ld.get("reason") == "not_your_unit", f"expected deny reason 'not_your_unit', got {ld}"
    print(f"PASS run_deny_paths: client intent on host-owned unit {host_owned['id']} "
          f"denied({ld['reason']}) via event_state.lastDeny")

    # cost_changed: OUR own actor, wrong tuBasisOverride (validateKneel's
    # `recomputed != tuBasis` check, connectionTCP.cpp).
    wrong_basis = actor_tu_basis + 37
    intent_resp2 = client.ok({"cmd": "battle_intent", "kind": "kneel", "actor": actor_id,
                               "kneel": not actor_kneeled, "tuBasisOverride": wrong_basis})
    iseq2 = intent_resp2["iseq"]
    ld2 = client.wait_for("deny(cost_changed) via event_state.lastDeny", denied(iseq2), timeout=10)
    assert ld2.get("reason") == "cost_changed", f"expected deny reason 'cost_changed', got {ld2}"
    print(f"PASS run_deny_paths: client intent with wrong tuBasisOverride={wrong_basis} "
          f"denied({ld2['reason']}) via event_state.lastDeny")


def run_burst_drain_proof(host, client, actor_a_id, actor_b_id):
    """r2 acceptance 1: turn+kneel+turn intents fired back-to-back from the
    client while the host-seat acts too - assert strictly increasing applied
    seq, queueDepth drains to 0, no rotation (the legacy wedge class),
    oldest-denied-first observable via lastDeny.

    DISCLOSED DEVIATION (not silent - see this packet's final report): a
    genuine host-side "busy" admission RACE was attempted first (two real
    client-owned units, actor A's turn picked as the LONGEST possible single
    rotation - 180 degrees / 4 ticks - to maximize the window
    bg->isBusy()==true should hold, actor B's kneel fired immediately
    afterward with no sleep). It could not be made to land: a live
    diagnostic run showed a full 4-tick UnitTurnBState chain (push -> 4
    think() ticks -> pop -> quiesce -> emit) resolving host-side in well
    under 100ms - faster than even ONE TestServer command's own round trip
    (~50ms observed) - so by the time actor B's intent could possibly reach
    onIntent()'s busy check, actor A's chain had already fully unwound and
    admitted normally. At the time this file was written the harness had no
    lever to artificially pause a BState mid-chain, so "busy" was validated
    ONLY by R2-P5's own enumerated code-review checklist (item 1), not by a
    live fire in either R3-P1 or R3-P2.

    RESOLVED by R2-P7 (owner-approved 2026-09-02): the TestServer
    `hold_chain {ms}` lever defers a quiesced chain's bt_action_end +
    action-context pop on the HOST, which keeps onIntent()'s
    `currentActionId() != 0` busy arm true for a deterministic window.
    test_rw_retry_cancel.py owns that live-fire proof now; this function
    keeps its lever-free natural-race shape on purpose.

    Given deny()/recordDeny() (connectionTCP.cpp) updates the SAME
    oldest-denied-first bookkeeping (g_coopLastDenyTick) for EVERY deny
    reason, not just "busy", this proof substitutes a not_your_unit deny
    (already proven reliable in run_deny_paths above) for the "oldest-
    denied-first observable via lastDeny" clause - the bookkeeping path
    exercised is identical regardless of which reason triggered it."""
    baseline = event_seq_baseline(client)

    a_before = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_a_id]
    to_dir = (a_before["direction"] + 4) % 8  # a turn, mixed in with the kneel below

    client.ok({"cmd": "battle_intent", "kind": "turn", "actor": actor_a_id, "toDir": to_dir})
    wait_settled(host, client, baseline)

    b_before = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_b_id]
    baseline2 = event_seq_baseline(client)
    client.ok({"cmd": "battle_intent", "kind": "kneel", "actor": actor_b_id,
               "kneel": not b_before["kneeled"]})
    wait_settled(host, client, baseline2)

    # oldest-denied-first bookkeeping (recordDeny()/g_coopLastDenyTick fires
    # for EVERY deny reason, not just "busy" - see this function's own doc
    # comment): a not_your_unit deny mixed into the same burst.
    host_state_for_deny = host.cmd({"cmd": "battle_state"})
    host_owned = next(
        u for u in units_by_id(host_state_for_deny).values()
        if u.get("isPlayerSoldier") and u.get("coop") == COOP_SEAT_0)
    deny_intent = client.ok({"cmd": "battle_intent", "kind": "kneel", "actor": host_owned["id"],
                              "kneel": not host_owned["kneeled"]})

    def denied_not_your_unit():
        ld = client.cmd({"cmd": "event_state"}).get("lastDeny")
        return ld if ld and ld.get("iseq") == deny_intent["iseq"] else None

    ld = client.wait_for("burst deny(not_your_unit) via event_state.lastDeny",
                          denied_not_your_unit, timeout=10)
    assert ld.get("reason") == "not_your_unit", f"expected deny reason 'not_your_unit', got {ld}"
    print(f"PASS run_burst_drain_proof: mixed-in deny(not_your_unit) observable via "
          "event_state.lastDeny (recordDeny()'s oldest-denied-first bookkeeping fires "
          "identically for every deny reason)")

    baseline3 = event_seq_baseline(client)
    client.ok({"cmd": "battle_intent", "kind": "turn", "actor": actor_a_id,
               "toDir": a_before["direction"]})  # turn A back
    wait_settled(host, client, baseline3)

    # The host-seat acts too: a local kneel (RB-D19 origin="host") on a
    # genuinely HOST-OWNED unit - select_away_from()'s own doc comment
    # explains why "whatever the host currently has selected" is NOT good
    # enough (the inherited initial selection is often actor A/B itself).
    host_sel = select_away_from(host, actor_a_id)
    host_unit_before = units_by_id(host.cmd({"cmd": "battle_state"}))[host_sel]

    baseline4 = event_seq_baseline(client)
    host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_K})
    wait_settled(host, client, baseline4)

    host_unit_after = units_by_id(host.cmd({"cmd": "battle_state"}))[host_sel]
    client_unit_after = units_by_id(client.cmd({"cmd": "battle_state"}))[host_sel]
    assert host_unit_after["kneeled"] != host_unit_before["kneeled"], (
        f"host's own local Kneel keypress did not toggle its selected unit {host_sel}")
    assert client_unit_after["kneeled"] == host_unit_after["kneeled"], (
        f"host-local kneel (origin=host) did not sync to the client: "
        f"host={host_unit_after['kneeled']} client={client_unit_after['kneeled']}")
    print(f"PASS run_burst_drain_proof: host-seat's OWN local kneel (unit {host_sel}) synced "
          "to the client too - the shared seq stream spans both origins")

    # Strictly increasing seq across the whole burst (turn A, kneel B, the
    # not_your_unit-denied attempt which consumed no seq, turn A back, host
    # kneel = 4 seq'd actions x2 evs each = 8) - "no rotation" (the legacy
    # wedge class). event_log's ring is battle-scoped, so this also covers
    # every earlier action this session ran (e2e kneel, stand, UI variant) -
    # a stronger check, not a weaker one.
    log = client.cmd({"cmd": "event_log", "tail": 200})
    seqs = [e["seq"] for e in log.get("events", []) if e.get("seq")]
    assert len(seqs) >= 8, f"expected at least 8 seq'd events across the burst, got {seqs}"
    assert seqs == sorted(seqs) and len(seqs) == len(set(seqs)), (
        f"SEQ NOT STRICTLY INCREASING (rotation/wedge class): {seqs}")
    print(f"PASS run_burst_drain_proof: seq stream strictly increasing across the whole burst "
          f"({len(seqs)} events): {seqs}")

    host_es = host.cmd({"cmd": "event_state"})
    client_es = client.cmd({"cmd": "event_state"})
    assert host_es.get("queueDepth") == 0, f"host queueDepth != 0 after the burst: {host_es}"
    assert client_es.get("queueDepth") == 0, f"client queueDepth != 0 after the burst: {client_es}"
    print("PASS run_burst_drain_proof: queueDepth drained to 0 on both machines after the burst")


def test_atom_kneel_e2e():
    host, client, actor, soldier_ids = bring_up_qualifying_battle(seat_count=2, tag="kneel_e2e")
    try:
        # RW-REVEAL-SYNC (SS2.4a): the host's bring-up reveals must already be on
        # the client before the first action runs. Probed BEFORE battle_t0:
        # assert_reveal_parity makes dozens of tile_info round trips and is TEST
        # INSTRUMENTATION, not pipeline latency - counting it against the 5s
        # battle-phase budget below would measure the probe, not the atom.
        assert_reveal_parity(host, client, "at t=0 (pre-action)",
                             extra_positions=[(actor["x"], actor["y"], actor["z"])])

        battle_t0 = time.time()  # battle-phase wall-clock starts once the battle is live

        actor_id = actor["id"]
        was_kneeled = actor["kneeled"]
        before_tu = actor["tu"]

        # --- t=0 hash-clean sanity ---
        assert_hash_clean(host, client, buckets=["unitsStats"], what="at t=0 (pre-action)")

        # --- drive the client kneel via battle_intent (RB-D13/RB-D32) ---
        baseline = event_seq_baseline(client)
        intent_resp = client.ok({"cmd": "battle_intent", "kind": "kneel",
                                  "actor": actor_id, "kneel": not was_kneeled})
        assert intent_resp.get("iseq"), f"battle_intent did not mint an iseq: {intent_resp}"

        wait_settled(host, client, baseline)

        host_state = host.cmd({"cmd": "battle_state"})
        client_state = client.cmd({"cmd": "battle_state"})
        host_unit = units_by_id(host_state)[actor_id]
        client_unit = units_by_id(client_state)[actor_id]

        assert host_unit["kneeled"] != was_kneeled, (
            f"host unit {actor_id} kneeled={host_unit['kneeled']}, expected the toggled state - "
            "the admitted kneel itself never executed on the host")
        assert client_unit["kneeled"] == host_unit["kneeled"], (
            f"client unit {actor_id} kneeled={client_unit['kneeled']}, host="
            f"{host_unit['kneeled']} - bt_ev/bt_action_end apply failed")
        assert client_unit["tu"] == host_unit["tu"], (
            f"client/host TU differ after the kneel: client={client_unit['tu']} "
            f"host={host_unit['tu']}")
        assert client_unit["tu"] < before_tu, (
            f"TU did not decrease from the pre-kneel value ({before_tu}) - got "
            f"{client_unit['tu']}")

        assert_hash_clean(host, client, buckets=["unitsStats"], what="post-kneel")
        assert host_state.get("mapDiscoveredFloor") == client_state.get("mapDiscoveredFloor"), (
            f"mapDiscoveredFloor differs after the e2e kneel: "
            f"host={host_state.get('mapDiscoveredFloor')} "
            f"client={client_state.get('mapDiscoveredFloor')} - a reveal delta this kneel's ev "
            "should have carried (RW-REVEAL-SYNC SS2.4a) did not land")
        assert_events(client, ["kneel", "bt_action_end"])

        elapsed = time.time() - battle_t0
        print(f"PASS test_atom_kneel_e2e: unit {actor_id} kneeled {was_kneeled} -> "
              f"{client_unit['kneeled']}, TU {before_tu} -> {client_unit['tu']} on both "
              f"machines, hash-clean, battle-phase wall-clock={elapsed:.2f}s")
        assert elapsed < 5.0, f"battle-phase wall-clock {elapsed:.2f}s exceeds the 5s target"

        # RW-REVEAL-SYNC per-tile check for the kneel just measured - deliberately
        # AFTER the latency gate, same instrumentation-vs-latency reason as the
        # pre-action probe (the cheap mapDiscoveredFloor equality inside the
        # window already caught a missing delta).
        assert_reveal_parity(host, client, "after the e2e kneel",
                             extra_positions=[(client_unit["x"], client_unit["y"], client_unit["z"])])

        # --- kneel back down (needed as a clean baseline for the UI variant
        # and so actor_a's later burst-test state is unsurprising) ---
        baseline_stand = event_seq_baseline(client)
        client.ok({"cmd": "battle_intent", "kind": "kneel", "actor": actor_id, "kneel": was_kneeled})
        wait_settled(host, client, baseline_stand)
        cur_kneeled = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_id]["kneeled"]
        assert cur_kneeled == was_kneeled, "stand-back-up kneel intent did not restore state"

        # --- ONE faithful-UI variant: proves the RB-D10 btnKneelClick
        # intercept end-to-end via a real SDLK_k keypress ---
        run_ui_variant(host, client, actor_id, cur_kneeled)

        # --- deny paths: not_your_unit + cost_changed (kneel's own validator).
        # tu_kneel_cost is derived from the e2e action's own observed TU
        # delta above (BattleUnit::getKneelChangeCost() is a constant per
        # unit/armor - no separate C++ introspection needed) rather than
        # hardcoding a value that could silently drift from the ruleset.
        actor_now = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_id]
        tu_kneel_cost = before_tu - client_unit["tu"]
        assert tu_kneel_cost > 0, f"could not derive a positive kneel TU cost: {tu_kneel_cost}"
        run_deny_paths(client, host_state, soldier_ids[0], actor_id,
                        actor_now["kneeled"], tu_kneel_cost)

        # --- burst/drain proof (r2 acceptance 1): needs the SECOND seated
        # soldier's battle unit id (soldier_ids[1], stamped by this packet's
        # harnessSeatOneSoldier index extension) ---
        client_state_now = client.cmd({"cmd": "battle_state"})
        actor_b = next(u for u in client_state_now["units"] if u.get("soldierId") == soldier_ids[1])
        run_burst_drain_proof(host, client, actor_id, actor_b["id"])

        # --- RW-FIX-TURRET: FULL 8-bucket equality AFTER every action above
        # (the G5 item-5 shape). This scope is NEW here - R3-P2 only ever
        # compared the single `unitsStats` bucket per action - and it is worth
        # having on this file specifically because run_burst_drain_proof()
        # mixes TWO body turns of actor A into the burst alongside the kneels,
        # i.e. it exercises exactly the applier path whose turret coupling
        # produced the post-action saveBlob-only `directionTurret` mismatch
        # RCA'd 2026-09-02 (see session.assert_turret_parity's own docstring
        # for the mechanism and the corrected attribution). The burst also
        # spans both origins (a host-local kneel via origin="host") and leaves
        # host/client selections deliberately on different units - `selectedUnit`
        # is a top-level saveBlob exclusion (saveBlobExcludedTopKey,
        # SharedEcon.cpp), so that does not weaken the compare.
        # RW-REVEAL-SYNC: the same 8 buckets are now a STRICTLY stronger claim -
        # saveBlobMaskFowBinTiles is gone, so the per-tile `discovered` bits are
        # inside saveBlob rather than carved out of it. assert_reveal_parity
        # additionally covers what the hash still cannot see (void tiles, which
        # SavedBattleGame::save skips entirely).
        n_units = assert_turret_parity(host, client, "after the whole kneel/turn burst")
        assert_reveal_parity(host, client, "after the whole kneel/turn burst")
        post_h, _ = assert_hash_clean(host, client, full=True,
                                      what="after the whole kneel/turn burst (full 8/8)")
        assert len(post_h) == 8, (
            f"hash_now full returned {len(post_h)} buckets, expected 8 "
            f"({sorted(post_h)}) - the spike bucket set changed under this test")
        print(f"PASS test_atom_kneel_e2e: directionTurret equal on all {n_units} units, fog of "
              f"war in parity, and {len(post_h)}/8 buckets (saveBlob included, binTiles now "
              "UNMASKED) EQUAL on both machines after the whole burst")

        print("PASS test_atom_kneel_e2e: ALL scenarios (e2e, UI variant, deny paths, "
              "burst/drain) passed in one session")
    finally:
        host.shutdown()
        client.shutdown()


def corrupted_unit_id(host, client):
    """Runs corrupt_bucket{unitsStats} on the HOST and diffs host/client TU
    per unit to find which unit id it touched (RB-D26's own poke: +-1 TU to
    "the first live unit" it finds, iteration-order dependent - NOT
    necessarily the fixture's own seat-1 soldier). Returns that unit id so
    the caller can deliberately kneel a DIFFERENT unit: CoopApply's own
    absolute-value semantics (unit->setTimeUnits(tuAfter)) would otherwise
    RESYNC the corrupted field the instant the SAME unit's kneel ev applies
    (tuAfter overwrites whatever discrepancy existed for that one unit),
    masking the corruption entirely and making this proof vacuous."""
    before = {u["id"]: u["tu"] for u in host.cmd({"cmd": "battle_state"})["units"]}
    resp = host.ok({"cmd": "corrupt_bucket", "name": "unitsStats"})
    assert resp.get("ok"), f"corrupt_bucket failed: {resp}"
    after = {u["id"]: u["tu"] for u in host.cmd({"cmd": "battle_state"})["units"]}
    diffs = [uid for uid, tu in after.items() if before.get(uid) != tu]
    assert len(diffs) == 1, f"corrupt_bucket touched {len(diffs)} unit(s), expected exactly 1: {diffs}"
    return diffs[0]


def select_away_from(host, avoid_id, max_tabs=12):
    """Tab-cycles the HOST's own selection until it lands on a HOST-OWNED
    unit (coop==COOP_SEAT_0, repro_atom_turn.py's own run_deny_path
    precedent for identifying one) other than `avoid_id`.

    SURPRISE (found while building this repro, not in the packet text): the
    battle's INHERITED initial selection (blob load, before any Tab press -
    same "pre-filter" wording test_rw_input_gating.py's own NOTE uses for
    the client side) is NOT itself seat-filtered - it is very often the
    SAME soldier this fixture's own harnessSeatOneSoldier(index=0) just
    stamped to COOP_SEAT_1 (both pick "the first soldier on the craft"), so
    a naive `selectedId != avoid_id` check can return a CLIENT-owned unit
    the host does not command - btnKneelClick's coopMayCommand() gate then
    silently no-ops it (correct behavior, but a stuck test). R5-P2 already
    seat-filters the Tab-cycle ITSELF (SavedBattleGame::selectNextPlayerUnit
    predicate), so one press reliably moves off it once actually checked."""
    for _ in range(max_tabs):
        st = host.cmd({"cmd": "battle_state"})
        sel = st.get("selectedId")
        if sel and sel != avoid_id:
            unit = units_by_id(st).get(sel)
            if unit and unit.get("coop") == COOP_SEAT_0:
                return sel
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.1)
    raise AssertionError(
        f"could not select a HOST-OWNED unit other than {avoid_id} within {max_tabs} tabs")


def test_forced_mismatch():
    """r2 acceptance 3: corrupt_bucket{unitsStats} on the host, then one
    kneel -> client freezes input, event_state.desyncSeen:true, bundle file
    exists (path in bt_desync), banner shown. A SEPARATE, freshly-booted
    session - SS2.8 "NO partial repair" means a desync-frozen battle stays
    frozen forever, so this session is torn down (not reused) once done."""
    host, client, actor, soldier_ids = bring_up_qualifying_battle(seat_count=1, tag="kneel_mismatch")
    try:
        assert_hash_clean(host, client, buckets=["unitsStats"], what="at t=0 (pre-corruption)")

        corrupted_id = corrupted_unit_id(host, client)
        print(f"[test_forced_mismatch] corrupt_bucket touched unit {corrupted_id} on the host "
              "(client copy untouched)")

        # Kneel via the HOST's OWN local input (RB-D19 origin=host), on a
        # unit deliberately DIFFERENT from corrupted_id (see
        # corrupted_unit_id()'s own doc comment for why).
        kneel_actor_id = select_away_from(host, corrupted_id)
        host_unit_before = units_by_id(host.cmd({"cmd": "battle_state"}))[kneel_actor_id]
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_K})

        def client_desynced():
            return client.cmd({"cmd": "event_state"}).get("desyncSeen") or None

        client.wait_for("client event_state.desyncSeen becomes true", client_desynced, timeout=15)
        es = client.cmd({"cmd": "event_state"})
        assert es.get("desyncSeen") is True, f"client did not latch desyncSeen: {es}"
        print(f"PASS test_forced_mismatch: client event_state.desyncSeen=True after the host's "
              f"kneel on unit {kneel_actor_id} (host's own unit {corrupted_id} carried the "
              "corrupted TU into the unitsStats hash)")

        # "client freezes input": the apply queue halts (g_battleFrozen) - a
        # FURTHER host action's ev never reaches lastSeqApplied on the
        # client, even though the host keeps emitting (lastSeqEmitted
        # advances). Prove it with one more host-local action.
        host_es_before = host.cmd({"cmd": "event_state"})
        client_es_before = client.cmd({"cmd": "event_state"})
        another_actor_id = select_away_from(host, corrupted_id)
        if another_actor_id == kneel_actor_id:
            another_actor_id = select_away_from(host, kneel_actor_id)
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_K})
        time.sleep(2.0)  # give the pump several ticks to (not) drain it
        host_es_after = host.cmd({"cmd": "event_state"})
        client_es_after = client.cmd({"cmd": "event_state"})
        assert host_es_after.get("lastSeqEmitted", 0) > host_es_before.get("lastSeqEmitted", 0), (
            f"host did not even emit the post-freeze action (test setup issue): "
            f"before={host_es_before} after={host_es_after}")
        assert client_es_after.get("lastSeqApplied", 0) == client_es_before.get("lastSeqApplied", 0), (
            f"CLIENT INPUT NOT FROZEN: lastSeqApplied advanced past the freeze point "
            f"(before={client_es_before}, after={client_es_after}) - g_battleFrozen did not "
            "halt the apply queue")
        print(f"PASS test_forced_mismatch: client input frozen - host emitted a further action "
              f"(lastSeqEmitted {host_es_before.get('lastSeqEmitted')} -> "
              f"{host_es_after.get('lastSeqEmitted')}) but the client's apply queue never "
              f"advanced past it (lastSeqApplied stuck at {client_es_after.get('lastSeqApplied')})")

        # bundle file exists (path in bt_desync): the CLIENT writes the
        # bundle to its OWN user dir's desync-reports/ (SharedEcon::
        # writeDesyncBundle); the HOST's log records the received bt_desync
        # report, including the bundlePath the client reported.
        bundle_glob = os.path.join(client.user_dir, "desync-reports", "desync-*.zip")
        bundles = glob.glob(bundle_glob)
        assert bundles, f"no desync bundle file found under {bundle_glob}"
        print(f"PASS test_forced_mismatch: desync bundle file exists on the client: {bundles[0]}")

        host_log_path = os.path.join(host.user_dir, "openxcom.log")
        with open(host_log_path, "r", errors="replace") as f:
            host_log = f.read()
        assert "bt_desync" in host_log, (
            f"host log has no 'bt_desync' line - the client's desync report never reached "
            f"the host: {host_log_path}")
        assert "bundlePath=" in host_log, (
            f"host log's bt_desync line carries no bundlePath: {host_log_path}")
        bundle_line = next(ln for ln in host_log.splitlines() if "bt_desync" in ln and "bundlePath=" in ln)
        assert "bundlePath=\n" not in bundle_line, bundle_line  # sanity: not literally empty
        print(f"PASS test_forced_mismatch: host log recorded the peer bt_desync report with a "
              f"bundlePath: {bundle_line.strip()}")

        # banner shown: BattlescapeState::_txtCoopWait (CoopBattleUi::
        # showDesyncHalted() -> setCoopWaitText()), read via this packet's
        # new getCoopWaitText()/TestServer battle_state.coopWaitText.
        client_banner = client.cmd({"cmd": "battle_state"}).get("coopWaitText", "")
        assert client_banner, "client's coop wait banner is empty - showDesyncHalted() never fired"
        print(f"PASS test_forced_mismatch: client banner shown: {client_banner!r}")

    finally:
        # Restart harness cleanly (packet text): a desync-frozen battle has
        # no path back to a working state (SS2.8 "no partial repair") - just
        # tear this session down, never reuse it.
        host.shutdown()
        client.shutdown()


def main():
    test_atom_kneel_e2e()
    test_forced_mismatch()
    print("ALL R3-P2 ATOM KNEEL + BURST + MISMATCH TESTS PASSED")


if __name__ == "__main__":
    main()
