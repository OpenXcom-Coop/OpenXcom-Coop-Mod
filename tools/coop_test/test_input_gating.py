"""Selection parity and no local execution on a co-op client.

Two halves, both driven through real UI input on a real 2-player classic coop
skirmish (the harness lobby flow test_handshake.py and test_faction_setup.py
use):

  A. SELECTION PARITY - "a seat cannot select what it doesn't command, and it
     CAN select what it does", on every path that writes _selectedUnit:
     battle-ENTRY auto-select, click-to-select, the TAB cycle, the middle-click
     NEXT-STOP by-distance variant, and the right-click NEXT-STOP undo.
  B. NO LOCAL EXECUTION - a co-op CLIENT ground click mints NOTHING locally.
     The walk arm has a wire message, so a client ground click on a unit it
     commands is FORWARDED as a `bt_intent walk` instead of being refused. The
     client still mints nothing locally and never reaches
     `statePushBack(new UnitWalkBState)`; the DELIVERY PROOF is
     `event_state.coopWalkArmEntered`, see assert_ground_click_mints_nothing().

     Why this half exists: primaryAction's guard sits on its commanding arms,
     not at its entry, so the select branch can run, and the walk arm is
     `else if (playableUnitSelected())`, which is TRUE on a client during the
     player side. Without the guard on the walk arm a client click would push a
     local UnitWalkBState - a state mint and a guaranteed desync.

HOW EACH HALF IS KEPT FROM PASSING VACUOUSLY:

  * The fixture stamps TWO soldiers to seat 1 (the newbattle_seat_soldier test
    command), so the client really owns units - and owns MORE THAN ONE, which
    is what makes "click-select a DIFFERENT own unit" a real transition rather
    than a no-op. Both ownership sets are asserted non-empty and disjoint
    before anything is claimed.
  * The ground-click assertions are ABSENCES (no BState, no TU change without
    an intent, buckets EQUAL), and an absence is equally consistent with a
    click that never reached BattlescapeGame::primaryAction at all. So every
    ground-click case asserts `event_state.coopWalkArmEntered` MOVED: the click
    was DELIVERED to primaryAction's walk arm. The click-select cases assert
    that neither it nor `event_state.coopLocalExecBlocked` (bumped by
    coopBlockLocalExecution() at the exact moment a commanding arm is refused)
    moved.
  * A second, independent delivery proof: the SAME injected-click mechanism, in
    the same run, on the same machine, DOES select a unit (own soldier) and DOES
    raise the ownership banner (host soldier). A recipe that could not reach
    primaryAction could do neither.
  * walk_sensitivity is the SENSITIVITY control: the HOST performs the
    identical ground click on its own soldier and really walks, and the HOST's
    OWN buckets then MOVE. That is what proves the client half's "all buckets
    EQUAL" was not true by construction. A host walk streams its step events
    like any other walk, so the control also asserts the client tracked the
    walk exactly.
  * The SPECTATOR path gets its own scenario with NO seat stamp at all, which
    is the shape a plain "NEW BATTLE > COOP" skirmish really produces (it never
    calls Soldier::setCoop(), so the joining client owns ZERO battle units).
    Without that scenario STR_COOP_SPECTATOR_MODE would be a string nobody can
    reach.

THE INITIAL SELECTION is asserted on BOTH machines. It is minted at
battle-generation time before any seat tag exists, so it can be the seat-1
soldier (observed: both machines started on unit 8); the entry auto-select then
moves each machine onto a unit it commands.

Run:  python tools/coop_test/test_input_gating.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from repro_atom_spot import pin_reaction_fire, assert_reaction_pin_holds

FACTION_PLAYER = 0
COOP_SEAT_NONE = -1
COOP_SEAT_0 = 0
COOP_SEAT_1 = 1

SDLK_BACKSPACE = 8   # Options::keyBattleEndTurn default
SDLK_TAB = 9         # Options::keyBattleNextUnit default
SDLK_BACKSLASH = 92  # Options::keyBattleDeselectUnit default (Options.cpp:328)
SDLK_HOME = 278      # Options::keyBattleCenterUnit default

# exact text (asserted, never just "non-empty": a stale deployed language copy
# shows the raw STR_ key instead)
TXT_NOT_YOUR_UNIT = "Not one of your soldiers"
TXT_SPECTATOR = "You command no soldiers - spectator mode"

DIR_DX = [0, 1, 1, 1, 0, -1, -1, -1]
DIR_DY = [-1, -1, 0, 1, 1, 1, 0, -1]


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def battle_state(gc):
    st = gc.cmd({"cmd": "battle_state"})
    assert st.get("ok") and st.get("inBattle"), f"battle_state failed: {st}"
    return st


def event_state(gc):
    ev = gc.cmd({"cmd": "event_state"})
    assert ev.get("ok"), f"event_state failed: {ev}"
    return ev


def banner(gc):
    return battle_state(gc).get("coopWaitText")


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


def log_lines(user_dir):
    log = os.path.join(user_dir, "openxcom.log")
    if not os.path.exists(log):
        return []
    with open(log, encoding="utf-8", errors="replace") as f:
        return f.readlines()


def grep_lines(lines, needle):
    return [l.rstrip("\n") for l in lines if needle in l]


def units_by_id(battle_state_resp):
    return {u["id"]: u for u in battle_state_resp.get("units", [])}


def bring_up_lobby(host, client, port):
    """Steps 1-4 of the skirmish lobby flow (test_faction_setup.py's own
    bring_up_lobby(), inlined again per that file's own precedent)."""
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


# dismiss_battle_start_overlays() lives in session.py. THIS file depends on it in
# particular: until the overlays are gone an injected TAB/click never reaches
# BattlescapeState's own handlers and the selection paths this test exists to
# check would silently do nothing.


def drive_to_battlescape(host, client, host_dir, client_dir, seated_holder,
                         seat_count=2):
    """Steps 5-7: BATTLE SETTINGS -> OK -> both machines in BattlescapeState.

    @a seat_count soldiers are stamped to COOP_SEAT_1 BEFORE generation
    (the newbattle_seat_soldier test command in the `index` form
    repro_atom_kneel.py uses). TWO is the default because this test needs the
    client to own MORE THAN ONE unit: with a single
    owned unit, "click-select one of your own soldiers" degenerates into
    clicking the one that is already selected, which primaryAction's select
    branch skips (`unit != _save->getSelectedUnit()`).

    seat_count=0 is the SPECTATOR fixture - a plain classic skirmish, which is
    what a real "NEW BATTLE > COOP" run produces (no Soldier::setCoop() call
    anywhere in that path), leaving the client with zero owned units."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={states(host)}"

    soldier_ids = []
    for i in range(seat_count):
        seat_resp = host.ok({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1,
                             "index": i})
        soldier_ids.append(seat_resp["soldierId"])
    seated_holder["soldierIds"] = soldier_ids
    seated_holder["soldierId"] = soldier_ids[0] if soldier_ids else None

    host.ok({"cmd": "newbattle_ok"})

    # the shared battle-entry spine - both briefings (the offer goes
    # out at PREPARE), the pre-battle equip screens (a seat_count=0 spectator
    # client has none), both Turn-1 screens.
    session.briefings_to_battlescape(host, client)
    assert session.has_state(host, "BattlescapeState"), \
        f"host should reach BattlescapeState after OK, stack={states(host)}"

    time.sleep(3)  # let both logs flush the handshake lines before reading them

    host_log = log_lines(host_dir)
    client_log = log_lines(client_dir)
    equal_lines = grep_lines(host_log, "[coop-handshake] battle_ready saveBlob EQUAL")
    mismatch_lines = grep_lines(host_log, "[coop-handshake] battle_ready saveBlob MISMATCH")
    client_active_lines = grep_lines(client_log, "[coop-handshake] CLIENT phase Active")

    assert not mismatch_lines, f"battle_ready saveBlob MISMATCH: {mismatch_lines[-1]}"
    assert equal_lines, "battle_ready arrived but 'saveBlob EQUAL' was never logged"
    assert client_active_lines, "client log missing 'CLIENT phase Active' line"

    # (the spine above already cleared both machines' battle-start overlays and
    # the client's entry briefing)
    assert top_state(host) == "BattlescapeState", \
        f"host should be sitting ON BattlescapeState, stack={states(host)}"

    # The entry auto-select runs on the first updateCoopTask tick that finds an
    # Active coop battle with a live
    # BattlescapeState. On the HOST that is strictly after
    # BriefingState::btnOkClick's startFirstTurn() (which writes the selection
    # itself), so give both machines a tick before reading selectedId.
    time.sleep(1.0)


def cycle_selected_ids(gc, presses, key=SDLK_TAB):
    """Press the next-unit key `presses` times, recording battle_state's
    selectedId after each press. Real faithful-UI input (inject_input pushes a
    genuine SDL_KEYDOWN/UP pair through Game::run's event loop), so it
    exercises BattlescapeState::btnNextSoldierClick -> selectNextPlayerUnit()
    -> SavedBattleGame::selectNextPlayerUnit() -> selectPlayerUnit() end to
    end, same as a real player tapping Tab."""
    seen = []
    for _ in range(presses):
        gc.ok({"cmd": "inject_input", "kind": "key", "key": key})
        time.sleep(0.05)
        seen.append(battle_state(gc).get("selectedId", -1))
    return seen


def next_stop_nth(gc):
    """Locate BattlescapeState's NEXT-STOP button (BattlescapeState.cpp:160,
    `new BattlescapeButton(32, 16, x + 176, y + 16)`) and return the `nth` index
    `click_widget` addresses it by, so the middle-click by-distance variant and
    the right-click UNDO can be driven through REAL mouse input rather than a
    synthetic handler call.

    Identified geometrically, not by a hard-coded index: the icons row carries
    seven columns of 32x16 buttons at x+48/80/112/144/176/208/240, two per
    column. NEXT-SOLDIER and NEXT-STOP are the fifth column; NEXT-STOP is the
    lower of the two. The column count is asserted, so a layout change fails
    loudly here instead of silently clicking the wrong button.

    click_widget (not inject_input) because the widget rects list_widgets
    reports are BASE coordinates while inject_input pushes WINDOW pixels -
    click_widget is the call that already applies Screen::getXScale() and the
    black bands. `nth` counts VISIBLE INTERACTIVE surfaces in add() order, which
    is exactly the order list_widgets dumps, so it is computed here rather than
    guessed."""
    lw = gc.cmd({"cmd": "list_widgets"})
    assert lw.get("ok"), f"list_widgets failed: {lw}"
    cands = [w for w in lw["widgets"]
             if w.get("w") == 32 and w.get("h") == 16 and w.get("interactive")
             and w.get("visible")]
    xs = sorted({w["x"] for w in cands})
    assert len(xs) == 7, (
        f"expected the 7 icon-row button columns of 32x16 BattlescapeButtons, "
        f"got x offsets {xs} - BattlescapeState's layout changed, fix this helper")
    col = sorted([w for w in cands if w["x"] == xs[4]], key=lambda w: w["y"])
    assert len(col) == 2, f"expected NEXT-SOLDIER + NEXT-STOP in column x={xs[4]}, got {col}"
    stop_idx = col[1]["idx"]
    nth = 0
    for w in lw["widgets"]:
        if w["idx"] == stop_idx:
            return nth
        if w.get("visible") and w.get("interactive"):
            nth += 1
    raise AssertionError("NEXT-STOP widget vanished between passes")


def click_button(gc, nth, button):
    gc.ok({"cmd": "click_widget", "nth": nth, "button": button})
    time.sleep(0.3)


def center_on_selection(gc):
    gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
    time.sleep(0.15)


def tile_click(gc, tx, ty, tz, button="left"):
    """Centre on the selected unit, ask the `map_tile_click_pos` probe for a
    VERIFIED window pixel for (tx,ty,tz), and push a real SDL click there.

    Why not repro_atom_turn.py's `map_tile_screen_pos` + raw click: three real
    offsets sit between the projected point and the point that actually selects
    a tile, and all three were observed while building this test (they are
    documented in full at the probe's own implementation, TestServer.cpp):
    mapClick reads Map::getSelectorPosition() rather than projecting the click
    itself; inject_input pushes WINDOW pixels while the camera works in base
    coordinates (Screen::getXScale() is 2 in the harness's 640x400 window); and
    a point over the icons panel is swallowed by mapClick's `_mouseOverIcons`
    early return. The probe solves all three and re-verifies the round trip, so
    a click that misses fails LOUDLY here instead of turning a gate assertion
    vacuous."""
    center_on_selection(gc)
    pr = gc.ok({"cmd": "map_tile_click_pos", "x": tx, "y": ty, "z": tz})
    assert pr.get("verified"), (
        f"tile ({tx},{ty},{tz}) is not clickable right now: {pr} - the fixture "
        f"cannot place this click, which is a FIXTURE failure, never a gate result")
    gc.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"],
           "button": button})
    return pr


def tile_click_until(gc, tx, ty, tz, ok_fn, what, button="left", tries=5, settle=0.6,
                     alt_tiles=()):
    """tile_click() with a bounded retry on the residual harness effects the
    probe cannot remove. Each attempt is independently verified by the probe,
    and the loop stops the moment @a ok_fn observes the intended effect.

    TWO effects, not one:
      * the battlescape camera can shift between the probe's round-trip check
        and the injected click arriving, so a click occasionally lands one tile
        off - a re-CLICK fixes that, because the shift is transient; and
      * a particular target tile can be systematically unproductive on a given
        map roll - it verifies every time and still never reaches the arm under
        test. Re-clicking THE SAME TILE five times then fails five times
        identically, as this helper once did ("5 verified clicks on tile
        (40,9,1) never produced the expected effect", every pre-gate healthy).
        A re-AIM is what fixes that.

    @a alt_tiles are further (x, y, z) candidates; attempts rotate through
    [(tx,ty,tz)] + alt_tiles. A caller that passes none re-clicks its one
    tile. NOTHING about what the caller asserts changes - a re-aimed click
    still has to produce the same observed effect."""
    targets = [(tx, ty, tz)] + [tuple(a) for a in alt_tiles]
    last = None
    for attempt in range(1, tries + 1):
        ax, ay, az = targets[(attempt - 1) % len(targets)]
        if (ax, ay, az) != (tx, ty, tz):
            print(f"    [{what}] attempt {attempt}: re-aiming at tile "
                  f"({ax},{ay},{az}) - the primary target has not produced the "
                  "expected effect yet")
        pre_ev = event_state(gc)
        pre_blocked = pre_ev.get("coopLocalExecBlocked")
        pre_arm = pre_ev.get("coopWalkArmEntered")
        last = tile_click(gc, ax, ay, az, button)
        time.sleep(settle)
        if ok_fn():
            last = dict(last)
            last["attempts"] = attempt
            # The counters as they stood immediately BEFORE the click that worked
            # - so a caller can still assert "this click did not go through a
            # commanding arm" without an earlier, MISSED attempt (which lands on
            # a neighbouring ground tile, i.e. legitimately in the walk arm)
            # poisoning the comparison.
            last["blockedBeforeThisClick"] = pre_blocked
            last["armBeforeThisClick"] = pre_arm
            return last
    st = battle_state(gc)
    raise AssertionError(
        f"{what}: {tries} verified clicks across tiles {targets} never produced the "
        f"expected effect (last probe={last}; mapClick's own pre-gates: "
        f"mouseOverIcons={st.get('mouseOverIcons')} cursorType={st.get('cursorType')} "
        f"isBusy={st.get('isBusy')} selectedId={st.get('selectedId')} "
        f"banner={st.get('coopWaitText')!r})")


def select_via_tab(gc, want_ids, tries=10):
    sel = battle_state(gc).get("selectedId")
    for _ in range(tries):
        if sel in want_ids:
            return sel
        gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.2)
        sel = battle_state(gc).get("selectedId")
    raise AssertionError(f"could not TAB the selection onto one of {sorted(want_ids)} "
                         f"(last selectedId={sel})")


def assert_ground_click_mints_nothing(host, client, actor_id, tx, ty, tz, label,
                                      alt_tiles=()):
    """A client ground-click must mint NOTHING LOCALLY - and the click must be
    PROVEN to have arrived.

    A ground click on a unit the client commands becomes a walk INTENT. An
    intent is not a mint: the client never reaches
    `statePushBack(new UnitWalkBState(...))`, and every "nothing was minted"
    observable below holds.

    THE DELIVERY PROOF is `coopWalkArmEntered`, not `coopLocalExecBlocked` (the
    refusal counter): a click on a unit the client DOES command is FORWARDED,
    not refused, so the refusal counter does not move for it - and a click
    whose pathfinder finds no route reaches the arm and legitimately does
    nothing at all. Counting arm ENTRY covers refused, forwarded and no-route
    clicks alike, because it says the click reached the arm whatever the arm
    then decided.

    WHAT IS ASSERTED:
      * DELIVERY - `coopWalkArmEntered` moved (the click reached the walk arm);
      * NO LOCAL BSTATE - the client's `isBusy` never goes true, sampled hard.
        A locally-minted UnitWalkBState is visible in BattlescapeGame::_states
        while it runs, and a thin client must never have one;
      * NO LOCAL DIVERGENCE - all buckets EQUAL afterwards, and host and client
        agree on the actor's position and TU. If the click became an INTENT the
        unit legitimately MOVED (the host executed it); what must never happen is
        the two machines disagreeing about it;
      * NO SILENT SECOND ORDER - nothing is left pending.
    """
    ev0 = event_state(client)
    arm0 = ev0.get("coopWalkArmEntered")
    assert isinstance(arm0, int), (
        "event_state carries no coopWalkArmEntered counter - without it the "
        "assertions below are only absences")
    sent0 = ev0.get("coopWalkIntentsSent")
    cb0 = battle_state(client)
    hb0 = battle_state(host)
    c_before = units_by_id(cb0)[actor_id]
    h_before = units_by_id(hb0)[actor_id]

    # The retry predicate IS the delivery proof: keep clicking (each click
    # independently verified by the probe) until primaryAction's walk arm has
    # actually been entered. A click that lands one tile off - the residual
    # camera-shift effect tile_click_until() exists for - would land in the
    # SELECT branch instead and leave the counter alone, so this can never
    # "pass" by never arriving.
    busy_seen = [False]

    def arm_entered():
        if battle_state(client).get("isBusy"):
            busy_seen[0] = True  # recorded, then asserted below as a FAILURE
            return True
        return event_state(client).get("coopWalkArmEntered", arm0) > arm0

    # Two full passes over the rotation, so a target still gets the re-CLICK
    # benefit for the transient camera shift as well as the re-AIM benefit for
    # an unproductive tile. Five tries for a caller with no alternates.
    pr = tile_click_until(client, tx, ty, tz, arm_entered,
                          f"client ground click [{label}]", settle=0.35,
                          tries=max(5, 2 * (1 + len(alt_tiles))),
                          alt_tiles=alt_tiles)
    sx, sy = pr["winX"], pr["winY"]

    # Sample isBusy hard for a second: a locally-minted UnitWalkBState is
    # visible in BattlescapeGame::_states while it runs, and a one-tile walk can
    # finish inside a lazy poll interval.
    for _ in range(10):
        if battle_state(client).get("isBusy"):
            busy_seen[0] = True
            break
        time.sleep(0.1)
    time.sleep(1.2)

    # the click may have become a multi-step walk the host is still
    # running, so a fixed sleep can land these reads mid-walk. Compare the two
    # machines only once the host is idle and the client has caught up.
    session.wait_host_idle(host, client)

    ev1 = event_state(client)
    cb1 = battle_state(client)
    hb1 = battle_state(host)
    c_after = units_by_id(cb1)[actor_id]
    h_after = units_by_id(hb1)[actor_id]
    became_intent = ev1.get("coopWalkIntentsSent", sent0) > sent0

    # --- DELIVERY PROOF (this is what stops the rest being vacuous) ---
    assert ev1.get("coopWalkArmEntered") > arm0, (
        f"[{label}] the click at ({sx},{sy}) for tile ({tx},{ty},{tz}) never reached "
        f"BattlescapeGame::primaryAction's walk arm - coopWalkArmEntered stayed at "
        f"{arm0}. Everything below would then pass for the wrong reason.")

    # --- NOTHING WAS MINTED LOCALLY ---
    assert not busy_seen[0], \
        f"[{label}] the client pushed a local BState after a ground click (isBusy went true)"
    assert cb1.get("isBusy") is False, f"[{label}] client left busy after a ground click"
    assert cb1.get("coopPendingIntent") in (None, {}), \
        f"[{label}] the client is holding a pending intent: {cb1.get('coopPendingIntent')}"
    # Whatever the click became, the client must have DRAINED it. "The client
    # emitted nothing" and "no deny arrived" are NOT asserted: a click on a
    # commanded unit ships an intent, and the host may legitimately answer it.
    # The stronger check is that the two machines AGREE about whatever
    # happened, asserted below.
    assert ev1.get("queueDepth") == 0, f"[{label}] client apply queue not drained: {ev1}"

    if became_intent:
        # The click became an ORDER. The unit may legitimately have
        # moved - on BOTH machines, identically, because the HOST executed it.
        for field in ("x", "y", "z", "tu", "energy"):
            assert c_after[field] == h_after[field], (
                f"[{label}] after the click became an intent, host and client "
                f"disagree on unit {actor_id}'s {field}: client={c_after[field]} "
                f"host={h_after[field]}")
    else:
        # The arm was entered and did nothing (no route, or a refusal). Then
        # neither machine may have moved anything.
        for who, before, after in (("client", c_before, c_after),
                                   ("host", h_before, h_after)):
            assert (after["x"], after["y"], after["z"]) == \
                   (before["x"], before["y"], before["z"]), (
                f"[{label}] {who}'s view of unit {actor_id} MOVED "
                f"{(before['x'], before['y'], before['z'])} -> "
                f"{(after['x'], after['y'], after['z'])} without an intent")
            assert after["tu"] == before["tu"], (
                f"[{label}] {who}'s view of unit {actor_id} spent TU "
                f"{before['tu']} -> {after['tu']} without an intent")

    hh, ch = session.assert_hash_clean(host, client, full=True,
                                       what=f"after a client ground click ({label})")
    print(f"  PASS ground-click [{label}] tile ({tx},{ty},{tz}) @ screen ({sx},{sy}): "
          f"walk arm ENTERED {arm0} -> {ev1['coopWalkArmEntered']}, "
          f"{'forwarded as an INTENT' if became_intent else 'no order minted'}, "
          f"no local BState, ALL {len(hh)} buckets EQUAL")


def test_classic_selection_gating():
    port = "47995"
    host_dir = make_user_dir("input_gating_host")
    client_dir = make_user_dir("input_gating_client")
    host = GameClient("host", 48794, host_dir)
    client = GameClient("client", 48795, client_dir)
    try:
        seated = {}
        bring_up_lobby(host, client, port)
        drive_to_battlescape(host, client, host_dir, client_dir, seated, seat_count=2)

        host_state = battle_state(host)
        client_state = battle_state(client)

        host_units = units_by_id(host_state)
        client_units = units_by_id(client_state)
        assert host_units, "host battle_state reported no units - fixture is empty"
        assert set(host_units.keys()) == set(client_units.keys()), \
            f"host/client unit id sets differ: host={sorted(host_units)} " \
            f"client={sorted(client_units)}"

        host_own_ids = {uid for uid, u in host_units.items() if u["coop"] == COOP_SEAT_0}
        client_own_ids = {uid for uid, u in host_units.items()
                          if u["coop"] not in (COOP_SEAT_0, COOP_SEAT_NONE)}
        assert host_own_ids, "no COOP_SEAT_0 (host-owned) units - fixture has no soldiers"
        # --- NON-VACUITY GATE: the client owns at least two units ------------
        assert len(client_own_ids) >= 2, \
            f"fixture is VACUOUS: the client owns {len(client_own_ids)} unit(s). " \
            f"Click-select needs TWO owned units (primaryAction's select branch skips " \
            f"`unit == _save->getSelectedUnit()`). seat stamp={seated.get('soldierIds')}, " \
            f"units(coop)={sorted((u['id'], u['coop']) for u in host_units.values())}"
        assert not (host_own_ids & client_own_ids), \
            f"a unit is claimed by both seats: {sorted(host_own_ids & client_own_ids)}"
        print(f"NON-VACUITY GATE ok: client owns {len(client_own_ids)} unit(s) "
              f"{sorted(client_own_ids)}, host owns {len(host_own_ids)} "
              f"{sorted(host_own_ids)}")

        # === entry_auto_select: each machine starts on a unit it commands =====
        # The initial selection is minted at battle-generation time before any
        # seat tag exists (observed: BOTH machines started on unit 8, the seat-1
        # one). CoopHandshake::selectOwnUnitAtEntry() is what makes it
        # assertable, on BOTH machines: the selection rule is seat-relative,
        # and the host is just as capable of starting on a unit it does not
        # command as the client is.
        host_initial_id = host_state.get("selectedId")
        client_initial_id = client_state.get("selectedId")
        assert host_initial_id in host_own_ids, (
            f"host started on unit {host_initial_id}, which is not one of its own "
            f"{sorted(host_own_ids)} - the entry auto-select did not run on the host")
        assert client_initial_id in client_own_ids, (
            f"client started on unit {client_initial_id}, which is not one of its own "
            f"{sorted(client_own_ids)} - the entry auto-select did not run on the client")
        print(f"PASS entry_auto_select: host starts on its own unit "
              f"{host_initial_id}, client on its own {client_initial_id}")

        # Entry is settled and no walk-capable input has run yet, so apply the
        # symmetric reaction-fire pin once (repro_atom_spot.pin_reaction_fire,
        # proven by a read-back on both machines): an alien reaction shot during
        # the walks below would move the hash buckets for reasons unrelated to
        # the gates this test checks. It suppresses no production path and
        # implements no reaction fire.
        reaction_pin = pin_reaction_fire(host, client)

        # === tab_cycle: TAB stays inside each machine's own units =============
        host_seen = cycle_selected_ids(host, len(host_own_ids) + 3)
        bad = [sid for sid in host_seen if sid != -1 and sid not in host_own_ids]
        assert not bad, f"host's selection cycle landed on non-owned unit id(s) {bad} " \
            f"(own set={sorted(host_own_ids)}, observed sequence={host_seen})"
        assert any(sid in host_own_ids for sid in host_seen), \
            f"host's selection cycle never landed on any of its own units " \
            f"(own set={sorted(host_own_ids)}, observed={host_seen})"
        host_leaked = [sid for sid in host_seen if sid in client_own_ids]
        assert not host_leaked, \
            f"host's selection cycle landed on the CLIENT's unit(s) {host_leaked} " \
            f"(client set={sorted(client_own_ids)}, observed={host_seen})"
        assert len(set(host_seen)) > 1 or len(host_own_ids) == 1, \
            f"host's selection cycle never advanced (observed={host_seen}) - the " \
            f"TAB presses are not reaching BattlescapeState"

        client_seen = cycle_selected_ids(client, len(host_own_ids) + 3)
        leaked = [sid for sid in client_seen if sid in host_own_ids]
        assert not leaked, f"client's selection cycle landed on host-owned unit id(s) " \
            f"{leaked} - coopMaySelectUnit()/commandsUnit() failed to exclude them " \
            f"(host set={sorted(host_own_ids)}, observed sequence={client_seen})"
        assert any(sid in client_own_ids for sid in client_seen), \
            f"client's selection cycle never landed on one of its OWN units " \
            f"{sorted(client_own_ids)} (observed={client_seen})"
        assert all(sid in client_own_ids or sid == -1 for sid in client_seen), \
            f"client's selection cycle produced an id outside its own set " \
            f"{sorted(client_own_ids)} + {{-1}}: {client_seen}"
        print(f"PASS tab_cycle: host {host_seen} stayed inside {sorted(host_own_ids)}, "
              f"client {client_seen} inside {sorted(client_own_ids)}")

        # === click_select_own: an OWN soldier, on the CLIENT =================
        # primaryAction's guard sits on its commanding arms, not at its entry: a
        # guard at the entry would return before the select branch could run,
        # so a client's left-click on its own soldier would do nothing at all.
        sel = select_via_tab(client, client_own_ids)
        others = sorted(client_own_ids - {sel})
        assert others, f"client owns only {sorted(client_own_ids)} - see the non-vacuity gate"
        target_id = others[0]
        t = units_by_id(battle_state(client))[target_id]
        own_click = tile_click_until(client, t["x"], t["y"], t["z"],
                                     lambda: battle_state(client).get("selectedId") == target_id,
                                     f"client click-select of its OWN soldier {target_id} "
                                     f"(if this never lands, either the entry guard is still "
                                     f"swallowing primaryAction or the click missed the tile)")
        after_sel = battle_state(client).get("selectedId")
        assert event_state(client)["coopLocalExecBlocked"] == own_click["blockedBeforeThisClick"], (
            "click-selecting an OWN unit went through a COMMANDING arm "
            "(coopLocalExecBlocked moved) - the select branch is the only exemption "
            "from the no-local-execution rule, and it must not be reached through the walk arm")
        # ...and the WALK ARM itself was not entered either. The walk arm can
        # FORWARD a click as an intent instead of refusing it, so the refusal
        # counter alone does not prove a click stayed out of it.
        assert event_state(client)["coopWalkArmEntered"] == own_click["armBeforeThisClick"], (
            "click-selecting an OWN unit ENTERED the walk arm (coopWalkArmEntered "
            "moved) - the select branch must not fall through into it")
        print(f"PASS click_select_own: client selected its own soldier {target_id} "
              f"by left-clicking its tile ({t['x']},{t['y']},{t['z']})")

        # === click_select_peer: a HOST soldier, on the CLIENT -> refused =====
        # The select branch gates only on `unit->getFaction() == _save->getSide()`,
        # so without the seat filter a client could select a HOST soldier.
        cu = units_by_id(battle_state(client))[after_sel]
        near_host = sorted(
            (abs(units_by_id(battle_state(client))[h]["x"] - cu["x"])
             + abs(units_by_id(battle_state(client))[h]["y"] - cu["y"]), h)
            for h in host_own_ids
            if units_by_id(battle_state(client))[h]["z"] == cu["z"])
        assert near_host, "no HOST-owned soldier on the client's map level - vacuous"
        hid = near_host[0][1]
        hu = units_by_id(battle_state(client))[hid]
        before_sel = battle_state(client).get("selectedId")
        peer_click = tile_click_until(client, hu["x"], hu["y"], hu["z"],
                                      lambda: banner(client) == TXT_NOT_YOUR_UNIT,
                                      f"client click on HOST soldier {hid} must raise the "
                                      f"ownership refusal")
        assert battle_state(client).get("selectedId") == before_sel, (
            f"client SELECTED the host's soldier {hid} - "
            f"CoopBattleUi::refuseSelectUnitClick() did not fire")
        assert banner(client) == TXT_NOT_YOUR_UNIT, (
            f"client banner is {banner(client)!r}, expected {TXT_NOT_YOUR_UNIT!r} "
            f"(the not_your_unit text, reused not duplicated). A raw STR_ key here "
            f"means the deployed bin/x64/Release/common/Language copy is stale.")
        assert event_state(client)["coopLocalExecBlocked"] == peer_click["blockedBeforeThisClick"], (
            "a refused click-select went through a COMMANDING arm - the refusal must "
            "come from the select branch's own filter, not from the walk arm")
        assert event_state(client)["coopWalkArmEntered"] == peer_click["armBeforeThisClick"], (
            "a refused click-select ENTERED the walk arm (coopWalkArmEntered "
            "moved) - the refusal must come from the select branch's own filter")
        print(f"PASS click_select_peer: client's click on host soldier {hid} was "
              f"refused with {TXT_NOT_YOUR_UNIT!r}, selection unchanged ({before_sel})")

        # === client_ground_clicks: a CLIENT ground-click mints NOTHING =======
        print("\n--- client_ground_clicks: a client ground click mints nothing locally ---")
        actor = select_via_tab(client, client_own_ids)
        center_on_selection(client)
        au = units_by_id(battle_state(client))[actor]
        occupied = {(u["x"], u["y"], u["z"]) for u in battle_state(client)["units"]}

        # WALKABLE: an EMPTY adjacent tile (an occupied one would go to the
        # select branch instead of the walk arm). Its walkability is PROVEN by
        # walk_sensitivity below, where the host performs the identical click
        # and really walks.
        walk_tile = None
        for d in range(8):
            tx, ty = au["x"] + DIR_DX[d], au["y"] + DIR_DY[d]
            if (tx, ty, au["z"]) in occupied:
                continue
            pr = client.ok({"cmd": "map_tile_click_pos", "x": tx, "y": ty, "z": au["z"]})
            if pr.get("verified"):
                walk_tile = (tx, ty)
                break
        assert walk_tile is not None, (
            "no EMPTY, clickable adjacent tile for the client's actor - the "
            "ground-click gate cannot be exercised")
        # Hand the OTHER clickable adjacent tiles over as re-aim
        # candidates. Which single tile is productive on a given map roll is a
        # camera/geometry fact; the gate under test is the same for all of them.
        walk_alts = []
        for dx2, dy2 in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            tx2, ty2 = au["x"] + dx2, au["y"] + dy2
            if (tx2, ty2) == walk_tile or (tx2, ty2, au["z"]) in occupied:
                continue
            pr2 = client.cmd({"cmd": "map_tile_click_pos", "x": tx2, "y": ty2, "z": au["z"]})
            if pr2.get("ok") and pr2.get("verified"):
                walk_alts.append((tx2, ty2, au["z"]))
        assert_ground_click_mints_nothing(host, client, actor, walk_tile[0], walk_tile[1],
                                          au["z"], "walkable adjacent tile",
                                          alt_tiles=walk_alts)

        # NO ROUTE: the actor's OWN tile. selectUnit(pos) returns the
        # already-selected unit, so the select branch's `unit != selected` test
        # is false and control falls into the WALK arm with a target the
        # pathfinder produces no route for (getStartDirection() == -1). Same
        # arm, same guard, opposite pathfinding outcome.
        assert_ground_click_mints_nothing(host, client, actor, au["x"], au["y"], au["z"],
                                          "no-route target (own tile)")

        # DISTANT: a far tile on the same level. Whether the pathfinder can
        # reach it or not, nothing may happen on the client.
        # Collect EVERY verified distant candidate, not just the first: a run
        # once failed here because the first one happened to be unproductive
        # on that map roll and all five retries re-clicked it.
        far = None
        far_alts = []
        for step in (5, 4, 3):
            for dxs, dys in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)):
                tx, ty = au["x"] + dxs * step, au["y"] + dys * step
                if (tx, ty, au["z"]) in occupied:
                    continue
                pr = client.cmd({"cmd": "map_tile_click_pos", "x": tx, "y": ty, "z": au["z"]})
                if pr.get("ok") and pr.get("verified"):
                    if far is None:
                        far = (tx, ty)
                    else:
                        far_alts.append((tx, ty, au["z"]))
        assert far, "no distant clickable empty tile found for the third ground-click variant"
        print(f"  distant ground-click candidates: primary {far}, "
              f"{len(far_alts)} re-aim alternate(s)")
        assert_ground_click_mints_nothing(host, client, actor, far[0], far[1], au["z"],
                                          f"distant tile {far}", alt_tiles=far_alts)

        assert not battle_state(client)["authority"]["desyncFrozen"], \
            "client desync-frozen after the ground-click phase"
        assert not battle_state(host)["authority"]["desyncFrozen"], \
            "host desync-frozen after the ground-click phase"

        assert_reaction_pin_holds(host, client, reaction_pin,
                                  "after the client ground-click group")

        # === selection_storm: every bucket still EQUAL =======================
        # TAB only, deliberately: NEXT-STOP's variants flag units
        # `dontReselect()` (setReselect=true), which permanently shrinks the
        # candidate pool for the rest of the turn - a storm built out of them
        # would end with -1 selected everywhere and would starve
        # next_stop_by_distance and next_stop_undo below. Those two paths get
        # their own hash check at the end of next_stop_undo.
        for _ in range(6):
            cycle_selected_ids(client, 2)
            cycle_selected_ids(host, 2)
        hh, ch = session.assert_hash_clean(host, client, full=True,
                                           what="after a selection storm")
        print(f"PASS selection_storm: ALL {len(hh)} buckets EQUAL "
              f"(selectedUnit/undoUnit are saveBlob-hash-excluded, SharedEcon.cpp:3958)")

        # === next_stop_by_distance: middle-click NEXT-STOP ===================
        # SavedBattleGame::selectNextPlayerUnitByDistance needs its own seat
        # filter: a candidate list built from a BARE isSelectable() includes
        # the peer's units. Driven through the real button, real SDL middle
        # click (BattlescapeState.cpp:518/525), via click_widget because the
        # widget rect is in BASE coordinates while inject_input takes WINDOW
        # pixels.
        #
        # PRESS COUNT IS CAPPED AT len(own) - 1 ON PURPOSE: each press flags the
        # unit it leaves with dontReselect(), and vanilla has no "un-flag all"
        # short of a new turn - press it len(own) times and every own unit is
        # out of the pool, selectedId goes -1, and every later phase starves.
        c_stop = next_stop_nth(client)
        h_stop = next_stop_nth(host)
        c_dist_seen = []
        for _ in range(max(1, len(client_own_ids) - 1)):
            click_button(client, c_stop, "middle")
            c_dist_seen.append(battle_state(client).get("selectedId"))
        leaked = [s for s in c_dist_seen if s not in client_own_ids and s != -1]
        assert not leaked, (
            f"client's middle-click NEXT-STOP (by distance) landed on non-owned "
            f"unit(s) {leaked} - selectNextPlayerUnitByDistance's seat filter is "
            f"missing (own={sorted(client_own_ids)}, observed={c_dist_seen})")
        assert any(s in client_own_ids for s in c_dist_seen), (
            f"client's by-distance cycle never landed on one of its own units "
            f"(observed={c_dist_seen}) - the filter is too restrictive, or the "
            f"middle click never reached btnNextStopMClick")
        h_dist_seen = []
        for _ in range(max(1, len(host_own_ids) - 1)):
            click_button(host, h_stop, "middle")
            h_dist_seen.append(battle_state(host).get("selectedId"))
        h_leaked = [s for s in h_dist_seen if s in client_own_ids]
        assert not h_leaked, (
            f"host's middle-click NEXT-STOP landed on the CLIENT's unit(s) {h_leaked} "
            f"(observed={h_dist_seen})")
        assert any(s in host_own_ids for s in h_dist_seen), (
            f"host's by-distance cycle never landed on one of its own units - the "
            f"filter is too restrictive or the middle click never arrived "
            f"(observed={h_dist_seen}). NOTE: this is also the proof that "
            f"click_widget's button=\"middle\" really reaches btnNextStopMClick.")
        print(f"PASS next_stop_by_distance: client {c_dist_seen} inside "
              f"{sorted(client_own_ids)}, host {h_dist_seen} never touched "
              f"{sorted(client_own_ids)}")

        # === next_stop_undo: right-click NEXT-STOP ===========================
        # Positive control FIRST, so the negative case below cannot pass just
        # because the button is dead.
        h_now = select_via_tab(host, host_own_ids)
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_BACKSLASH})
        time.sleep(0.3)
        h_moved = battle_state(host).get("selectedId")
        assert h_moved != h_now, (
            f"the host's NEXT-STOP deselect key did not move the selection off "
            f"{h_now} - the undo test below would be vacuous")
        click_button(host, h_stop, "right")
        assert battle_state(host).get("selectedId") == h_now, (
            f"right-click UNDO did not restore the host's own previous unit {h_now} "
            f"(selectedId={battle_state(host).get('selectedId')}) - the filter is too "
            f"restrictive, or the right click never reached btnNextStopRClick")
        print(f"  positive control: right-click UNDO restored the host's own unit {h_now}")

        # Negative: point the host at a CLIENT-owned unit (battle_open_inventory
        # sets the selection before calling the real handler), deselect so THAT
        # becomes _undoUnit, then UNDO. Without the seat filter
        # btnNextStopRClick would hand the client's soldier back.
        c_unit = sorted(client_own_ids)[0]
        host.cmd({"cmd": "battle_open_inventory", "unit": c_unit})
        time.sleep(0.3)
        assert battle_state(host).get("selectedId") == c_unit, (
            f"could not point the host's selection at the client's unit {c_unit} - "
            f"the undo-filter case cannot be set up")
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_BACKSLASH})
        time.sleep(0.3)
        after_deselect = battle_state(host).get("selectedId")
        assert after_deselect != c_unit, (
            f"the deselect key left the host on the client's unit {c_unit}")
        click_button(host, h_stop, "right")
        undone = battle_state(host).get("selectedId")
        assert undone != c_unit, (
            f"right-click UNDO handed the host the CLIENT's unit {c_unit} - "
            f"btnNextStopRClick's coopMaySelectUnit() filter did not fire")
        assert undone in host_own_ids, (
            f"host's selection after UNDO is {undone}, not one of its own "
            f"{sorted(host_own_ids)}")
        hh2, ch2 = session.assert_hash_clean(
            host, client, full=True,
            what="after the NEXT-STOP by-distance + UNDO paths")
        print(f"PASS next_stop_undo: restores an OWN unit, refuses the peer's "
              f"{c_unit} (landed on {undone}); ALL {len(hh2)} buckets EQUAL after "
              f"next_stop_by_distance + next_stop_undo too")

        # === client_end_turn_noop: client's End Turn key is a local no-op ====
        cb = battle_state(client)
        client_turn_before = cb.get("turn")
        client_side_before = cb.get("side")
        client.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_BACKSPACE})
        time.sleep(0.3)
        client_state_after = battle_state(client)
        assert client_state_after.get("turn") == client_turn_before, \
            f"client's End Turn key changed turn: {client_turn_before} -> " \
            f"{client_state_after.get('turn')} (the client's no-op guard did not hold)"
        assert client_state_after.get("side") == client_side_before, \
            f"client's End Turn key changed side: {client_side_before} -> " \
            f"{client_state_after.get('side')} (the client's no-op guard did not hold)"
        assert session.has_state(client, "BattlescapeState"), \
            f"client left BattlescapeState after its End Turn key, stack={states(client)}"
        assert host_state.get("authority", {}).get("hostSim") is True, \
            "host battle_state.authority.hostSim should be true"
        assert client_state.get("authority", {}).get("hostSim") is False, \
            "client battle_state.authority.hostSim should be false"
        print("PASS client_end_turn_noop: client's End Turn key was a local no-op")

        # =====================================================================
        # walk_sensitivity - the SENSITIVITY control for client_ground_clicks.
        #
        # The host performs the identical ground click and its own unit walks.
        # Step events do not depend on which machine ordered the walk, so the
        # client's copy follows it and the two machines stay EQUAL.
        #
        # What client_ground_clicks needs from this phase is proof that a walk
        # is something the HASH BUCKETS CAN SEE, so that "the buckets stayed
        # EQUAL" is a real statement. That is measured on the HOST's OWN
        # before/after hash - and the two machines staying EQUAL through it is
        # asserted as well.
        # =====================================================================
        print("\n--- walk_sensitivity: the sensitivity control for client_ground_clicks ------")
        print("    client_ground_clicks proved 'the buckets stayed EQUAL and nothing was minted'.")
        print("    That is only worth something if a real walk MOVES those buckets,")
        print("    so the host now performs the identical click for real.")
        h_actor = select_via_tab(host, host_own_ids)
        center_on_selection(host)
        hu2 = units_by_id(battle_state(host))[h_actor]
        before = dict(hu2)
        h_occupied = {(u["x"], u["y"], u["z"]) for u in battle_state(host)["units"]}
        host_hash_before = host.cmd({"cmd": "hash_now", "full": True})["h"]

        def host_unit_acted():
            now = units_by_id(battle_state(host))[h_actor]
            return ((now["x"], now["y"], now["z"]) != (before["x"], before["y"], before["z"])
                    or now["tu"] != before["tu"])

        moved = False
        for d in range(8):
            tx, ty = hu2["x"] + DIR_DX[d], hu2["y"] + DIR_DY[d]
            if (tx, ty, hu2["z"]) in h_occupied:
                continue
            pr = host.cmd({"cmd": "map_tile_click_pos", "x": tx, "y": ty, "z": hu2["z"]})
            if not (pr.get("ok") and pr.get("verified")):
                continue
            host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"],
                     "y": pr["winY"], "button": "left"})
            time.sleep(1.5)
            if host_unit_acted():
                moved = True
                break
        assert moved, (
            "the HOST's identical ground click did not move its own soldier at all - "
            "so client_ground_clicks' 'the client did not move' proves nothing about the gate. Either "
            "the injection recipe is broken or every adjacent tile is impassable.")
        # host_unit_acted() fires on the walk's first TU/position
        # change, so the walk can still be running here. Settle before the
        # host-vs-client compare below.
        session.wait_host_idle(host, client)
        h_final = units_by_id(battle_state(host))[h_actor]
        hfull = host.cmd({"cmd": "hash_now", "full": True})["h"]
        moved_buckets = sorted(k for k in hfull if hfull[k] != host_hash_before.get(k))
        assert moved_buckets, (
            "the host really walked but EVERY hash bucket on the HOST stayed the "
            "same as before the walk - the buckets cannot see a walk at all, which "
            "would make the equality assertions of client_ground_clicks, selection_storm "
            "and next_stop_undo worthless")
        # A HOST-ORIGIN walk streams its own step events, so the client's copy
        # MUST have followed it and the two machines must still agree.
        c_view = units_by_id(battle_state(client))[h_actor]
        assert (c_view["x"], c_view["y"], c_view["z"], c_view["tu"]) == \
               (h_final["x"], h_final["y"], h_final["z"], h_final["tu"]), (
            f"the client's view of unit {h_actor} is "
            f"{(c_view['x'], c_view['y'], c_view['z'], c_view['tu'])} but the host "
            f"has it at {(h_final['x'], h_final['y'], h_final['z'], h_final['tu'])} - "
            "a HOST-ORIGIN walk emits step events like any other and the "
            "client must apply them")
        session.assert_hash_clean(host, client, full=True,
                                  what="after walk_sensitivity's host-origin walk")
        assert_reaction_pin_holds(host, client, reaction_pin,
                                  "after walk_sensitivity's host-origin walk")
        print(f"PASS walk_sensitivity: the host's identical click walked "
              f"unit {h_actor} {(before['x'], before['y'], before['z'])} -> "
              f"{(h_final['x'], h_final['y'], h_final['z'])}, TU {before['tu']} -> "
              f"{h_final['tu']}, MOVING the host's own buckets {moved_buckets} - and "
              f"the client tracked it exactly, so all buckets are still EQUAL")

    finally:
        host.shutdown()
        client.shutdown()


def test_spectator_entry():
    """The spectator fallback: a plain classic skirmish with NO seat stamp -
    exactly what "NEW BATTLE > COOP" produces - leaves the joining client with
    zero owned units. It must be TOLD so (STR_COOP_SPECTATOR_MODE), and the host
    must still start on one of its own."""
    port = "47993"
    host_dir = make_user_dir("input_gating_spec_host")
    client_dir = make_user_dir("input_gating_spec_client")
    host = GameClient("host", 48792, host_dir)
    client = GameClient("client", 48793, client_dir)
    try:
        seated = {}
        bring_up_lobby(host, client, port)
        drive_to_battlescape(host, client, host_dir, client_dir, seated, seat_count=0)

        hb = battle_state(host)
        cb = battle_state(client)
        units = units_by_id(hb)
        host_own_ids = {uid for uid, u in units.items() if u["coop"] == COOP_SEAT_0}
        client_own_ids = {uid for uid, u in units.items()
                          if u["coop"] not in (COOP_SEAT_0, COOP_SEAT_NONE)}
        assert host_own_ids, "no host-owned units - fixture has no soldiers"
        assert not client_own_ids, (
            f"the no-stamp fixture gave the client owned units {sorted(client_own_ids)} - "
            f"the spectator path is then unreachable and this test is vacuous")

        assert cb.get("coopWaitText") == TXT_SPECTATOR, (
            f"client banner is {cb.get('coopWaitText')!r}, expected {TXT_SPECTATOR!r} - "
            f"CoopHandshake::selectOwnUnitAtEntry() did not raise the spectator notice "
            f"(a raw STR_ key here means the deployed language copy is stale)")
        assert hb.get("selectedId") in host_own_ids, (
            f"host started on unit {hb.get('selectedId')}, not one of its own "
            f"{sorted(host_own_ids)}")
        assert hb.get("coopWaitText") != TXT_SPECTATOR, (
            "the HOST was told it is spectating, but it owns "
            f"{len(host_own_ids)} units")

        # A spectator's TAB must never MOVE it onto somebody else's soldier.
        #
        # The baseline it must not move off is the value the blob carried:
        # SavedBattleGame::load() deserializes `selectedUnit` directly
        # (SavedBattleGame.cpp:178/285-286) without routing through
        # selectPlayerUnit(), so a client that commands nothing inherits
        # whatever the HOST had selected at snapshot time. The entry auto-select
        # deliberately does NOT clear that (it shows the notice and leaves the
        # selection alone), because every commanding arm is gated anyway and
        # `selectedUnit` is saveBlob-hash-excluded. What MUST hold is that no
        # selection PATH hands the spectator a peer's soldier: the filtered
        # cycle finds no candidate, wraps, and leaves _selectedUnit exactly where
        # it started.
        spec_baseline = cb.get("selectedId")
        spec_seen = cycle_selected_ids(client, 5)
        moved = [s for s in spec_seen if s not in (spec_baseline, -1)]
        assert not moved, (
            f"the spectating client's TAB cycle MOVED its selection to {moved} - "
            f"selectPlayerUnit()'s seat filter let a peer's soldier through "
            f"(baseline={spec_baseline}, host set={sorted(host_own_ids)}, "
            f"observed={spec_seen})")
        hh, ch = session.assert_hash_clean(host, client, full=True,
                                           what="spectator entry + TAB")
        print(f"PASS spectator: client owns 0 units, shows {TXT_SPECTATOR!r}, TAB never "
              f"moved off its inherited baseline {spec_baseline} (observed={spec_seen}, "
              f"host set={sorted(host_own_ids)}); host started on its own "
              f"{hb.get('selectedId')}; ALL {len(hh)} buckets EQUAL")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    test_classic_selection_gating()
    test_spectator_entry()
    print("ALL SELECTION-PARITY / NO-LOCAL-EXECUTION TESTS PASSED")


if __name__ == "__main__":
    main()
