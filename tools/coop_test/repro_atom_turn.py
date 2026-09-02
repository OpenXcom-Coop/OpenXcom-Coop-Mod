"""R3-P1 (rewrite spike, SPIKE-RUNBOOK.md R3-P1 packet text): ATOM turn e2e -
"the pipeline proof". First full loop: client intent -> ack -> host executes
vanilla -> bt_ev turn (+h) -> client applies -> hash-clean -> bt_action_end
-> client unlock, plus the deny path and a faithful-UI variant.

FIXTURE (REVIEW4 IR-4 - "by construction" made constructive): this file
drives a real 2-player skirmish through the harness lobby flow (the SAME UI
path test_rw_handshake.py/test_rw_faction_setup.py/test_rw_input_gating.py
already proved out - skirmish_host()/skirmish_client_at_browser()/
bring_up_lobby() are the same precedent-following inline copies those files
use, per test_rw_faction_setup.py's own stated precedent).

DEVIATION FROM THE LITERAL RECIPE (disclosed, not silent - see this
packet's final report): the runbook's recipe pins mission STR_UFO_CRASH_
RECOVERY / craft Skyranger / smallest map / FARM terrain / race Sectoid /
difficulty Beginner. No TestServer introspection or setter exists for the
New Battle screen's mission/craft/terrain/race/difficulty comboboxes (only
a hotseat toggle, harnessSetHotseat, precedent-wise), and building one is a
disproportionate new-surface addition for a spike pipeline-proof test. This
file instead uses whatever NEW BATTLE > COOP's persisted defaults already
produce (the SAME defaults the other test_rw_*.py files already run
against successfully) and leans on the packet's OWN stated fallback for
exactly this situation: the SELECTION RULE + a bounded re-roll loop (max 5
boots, each attempt's map/alien placement is freshly RNG-seeded, so a
re-roll has real teeth). The runbook's own words: "the two guards ARE the
construction; terrain choice just makes them cheap" - so this file leans
harder on the guards to compensate for skipping the terrain pin.

FIXTURE-COVERAGE gap closed here (test_rw_input_gating.py's own note): a
plain classic skirmish never calls Soldier::setCoop(), so every soldier
defaults to seat 0 (host) - the CLIENT would have no real unit to drive a
client-intent repro against. This packet adds the minimal debug lever that
note names as the fix: NewBattleState::harnessSeatOneSoldier() / TestServer
"newbattle_seat_soldier", stamping ONE soldier to seat 1 before OK
generates the battle.

SELECTION RULE (REVIEW4 IR-4): pick the seat-1 soldier only if (a) no
player unit currently sees a hostile - approximated via battle_state's own
`spotted` field (a UNION across every player unit's getVisibleUnits(), per
R2-P11's own field; an empty union implies every per-unit spotted set is
also empty, which is the direction this rule actually needs - a
conservative but sound proxy for the vanilla UnitTurnBState.cpp:114-118
"unitsSpottedThisTurn grew" abort predicate the runbook cites) and (b) no
door tile within 2 tiles of it (a tile_info sweep). If it does not qualify,
tear the whole session down and re-roll (fresh RNG-seeded generation) - up
to 5 attempts, logging each.

Run:  python tools/coop_test/repro_atom_turn.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import assert_hash_clean, assert_events, assert_turret_parity

FACTION_PLAYER = 0
COOP_SEAT_NONE = -1
COOP_SEAT_0 = 0
COOP_SEAT_1 = 1
MAX_REROLLS = 5

SDLK_TAB = 9  # Options::keyBattleNextUnit default (test_rw_input_gating.py precedent)
SDLK_HOME = 278  # Options::keyBattleCenterUnit default

# Direction -> (dx, dy) step table, 0=North clockwise (the same table
# TestServer.cpp's own "battle_action act==\"turn\"/\"door\"" debug helpers use).
DIR_DX = [0, 1, 1, 1, 0, -1, -1, -1]
DIR_DY = [-1, -1, 0, 1, 1, 1, 0, -1]


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


def drive_to_battlescape(host, client, seated_holder):
    """Steps 5-7 of the skirmish lobby flow (test_rw_handshake.py/
    test_rw_faction_setup.py precedent), extended with the R3-P1 fixture
    seat stamp between reaching NewBattleState and clicking OK."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={states(host)}"

    seat_resp = host.ok({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1})
    seated_holder["soldierId"] = seat_resp["soldierId"]

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


def dismiss_battle_start_overlays(host, timeout=10):
    """SURPRISE (found while building this repro, not in the packet text):
    a freshly generated battle pushes vanilla's own "Turn 1 begins"
    (NextTurnState, closed by ANY key/click) and pre-battle equip
    (InventoryState, closed by Options::keyCancel/SDLK_ESCAPE) screens ON
    TOP of BattlescapeState - exactly like a normal SP battle start (this is
    not coop-specific; a plain SP battle_action probe hit the identical
    freeze while diagnosing this). Game::run() only calls think() on
    _states.back() (Game.cpp:438) - so BattlescapeState's own _gameTimer
    (and therefore the whole BState machine, including an admitted coop
    turn's UnitTurnBState) never ticks until these overlays are dismissed
    and BattlescapeState becomes the top of the stack again. The CLIENT
    never sees this (it loads the streamed blob straight into
    BattlescapeState with no generation-time popups) - HOST-only step."""
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
    """REVIEW4 IR-4 SELECTION RULE - see this file's own module docstring
    for the exact (a)/(b) predicates and the documented approximation for
    (a). Returns the seat-1 soldier's unit dict if it qualifies, else None."""
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


def bring_up_qualifying_battle():
    """REVIEW4 IR-4: boot a live skirmish, seat one soldier to seat 1, and
    check the SELECTION RULE against it; re-roll (fresh boot - a new
    generation is RNG-seeded fresh) up to MAX_REROLLS times if it doesn't
    qualify. Returns (host, client, actor_unit_dict, soldier_id)."""
    for attempt in range(1, MAX_REROLLS + 1):
        port = str(47996 + attempt)
        host_dir = make_user_dir(f"repro_atom_turn_host_{attempt}")
        client_dir = make_user_dir(f"repro_atom_turn_client_{attempt}")
        host = GameClient("host", 48830 + attempt * 2, host_dir)
        client = GameClient("client", 48831 + attempt * 2, client_dir)
        seated = {}
        try:
            bring_up_lobby(host, client, port)
            drive_to_battlescape(host, client, seated)

            soldier_id = seated["soldierId"]
            actor = qualifying_actor(host, soldier_id)
            if actor is not None:
                print(f"[repro_atom_turn] fixture qualifies on attempt {attempt}/{MAX_REROLLS} "
                      f"(actor unit id={actor['id']}, soldierId={soldier_id}, "
                      f"pos=({actor['x']},{actor['y']},{actor['z']}))")
                return host, client, actor, soldier_id

            print(f"[repro_atom_turn] re-roll {attempt}/{MAX_REROLLS}: fixture did not "
                  "qualify (a hostile already spotted, or a door within 2 tiles) - "
                  "tearing down and retrying")
            host.shutdown()
            client.shutdown()
        except Exception:
            host.shutdown()
            client.shutdown()
            raise

    raise RuntimeError(f"repro_atom_turn: no qualifying fixture found in {MAX_REROLLS} boots")


def assert_turn_parity(host, client, what):
    """RW-FIX-TURN: `battle_state.turn` must read 1 on BOTH machines once the
    host's battle-start overlays are dismissed. The host reaches 1 through
    vanilla (InventoryState::btnOkClick -> startFirstTurn()); the thin client
    reaches it through the CoopMod counter mirror at the end of the client
    handshake (CoopHandshake::onBlobChunkAppended, connectionTCP.cpp) - the
    counter write ONLY, none of startFirstTurn()'s other work."""
    ht = host.cmd({"cmd": "battle_state"}).get("turn")
    ct = client.cmd({"cmd": "battle_state"}).get("turn")
    assert ht == 1, (f"host battle_state.turn == {ht}, expected 1 {what} - the host's own "
                     "startFirstTurn() never ran (battle-start overlays still up?)")
    assert ct == 1, (f"client battle_state.turn == {ct}, expected 1 {what} (host={ht}) - the "
                     "RW-FIX-TURN client counter mirror did not fire")
    return ht, ct


def event_seq_baseline(client):
    return client.cmd({"cmd": "event_state"}).get("lastSeqApplied", 0)


def wait_settled(host, client, baseline, timeout=15):
    """Waits for queueDepth to return to 0 on BOTH machines AND for the
    client's lastSeqApplied to have advanced past `baseline` (captured via
    event_seq_baseline() BEFORE triggering the action) - queueDepth==0 alone
    is also true trivially at REST (nothing ever enqueued), which would
    otherwise let this return immediately without the action having done
    anything at all."""
    def settled():
        hs = host.cmd({"cmd": "event_state"})
        cs = client.cmd({"cmd": "event_state"})
        return bool(hs.get("ok") and cs.get("ok")
                    and hs.get("queueDepth") == 0 and cs.get("queueDepth") == 0
                    and cs.get("lastSeqApplied", 0) > baseline)
    client.wait_for("action settled (new seq applied, queueDepth 0 on both machines)",
                     settled, timeout=timeout)


def run_ui_variant(host, client, actor_id, current_dir):
    """ONE faithful-UI variant step (packet text): a real right-click via
    inject_input, proving the RB-D10 secondaryAction intercept end-to-end -
    the client SENDS an intent (instead of running vanilla locally) exactly
    as the battle_intent-driven path above did, but reached through the
    real map-click code path this time."""
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

    # Center the camera on our selected unit (Options::keyBattleCenterUnit,
    # default SDLK_HOME) BEFORE asking map_tile_screen_pos for a target tile -
    # otherwise the camera may still be wherever it was at battle load
    # (typically centered on whichever unit the HOST had selected at
    # snapshot time), and a tile near OUR unit could resolve to a screen
    # position nowhere near the visible viewport.
    client.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
    time.sleep(0.1)

    unit = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_id]
    ui_to_dir = (current_dir + 2) % 8  # a clearly different direction (90 degrees on)
    tx = unit["x"] + DIR_DX[ui_to_dir]
    ty = unit["y"] + DIR_DY[ui_to_dir]
    tz = unit["z"]

    pos_resp = client.ok({"cmd": "map_tile_screen_pos", "x": tx, "y": ty, "z": tz})
    sx, sy = pos_resp["screenX"], pos_resp["screenY"]
    assert 0 <= sx < pos_resp["mapWidth"] and 0 <= sy < pos_resp["mapHeight"], (
        f"computed click target ({sx},{sy}) is off the "
        f"{pos_resp['mapWidth']}x{pos_resp['mapHeight']} map viewport")

    before_tu = unit["tu"]
    baseline = event_seq_baseline(client)
    client.ok({"cmd": "inject_input", "kind": "click", "x": sx, "y": sy, "button": "right"})

    wait_settled(host, client, baseline)

    host_unit = units_by_id(host.cmd({"cmd": "battle_state"}))[actor_id]
    client_unit = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_id]

    assert client_unit["direction"] == ui_to_dir, (
        f"faithful-UI right-click did not turn unit {actor_id} to dir {ui_to_dir} "
        f"(client direction={client_unit['direction']}) - the RB-D10 secondaryAction "
        "intercept did not fire end-to-end (see this repro's WATCH note on "
        "inject_input sending no preceding SDL_MOUSEMOTION)")
    assert host_unit["direction"] == ui_to_dir, (
        f"host unit {actor_id} direction={host_unit['direction']}, expected {ui_to_dir}")
    assert client_unit["tu"] < before_tu, \
        "client TU did not decrease after the faithful-UI turn"

    assert_hash_clean(host, client, buckets=["unitsStats"], what="post-UI-variant")
    print(f"PASS run_ui_variant: real right-click turned unit {actor_id} to dir {ui_to_dir} "
          f"via the RB-D10 secondaryAction intercept (client sent the intent, host executed "
          "+ emitted, client applied), hash-clean")


def run_deny_path(client, host_state, seated_soldier_id):
    """client intents a HOST-owned unit -> deny(not_your_unit) + banner
    state via event_state.lastDeny (packet text's own deny-path clause)."""
    host_units = units_by_id(host_state)
    host_owned = next(
        u for u in host_units.values()
        if u.get("isPlayerSoldier") and u.get("coop") == COOP_SEAT_0
        and u.get("soldierId") != seated_soldier_id)

    intent_resp = client.ok({"cmd": "battle_intent", "kind": "turn",
                              "actor": host_owned["id"],
                              "toDir": (host_owned["direction"] + 1) % 8})
    iseq = intent_resp["iseq"]

    def denied():
        ld = client.cmd({"cmd": "event_state"}).get("lastDeny")
        return ld if ld and ld.get("iseq") == iseq else None

    ld = client.wait_for("deny(not_your_unit) via event_state.lastDeny", denied, timeout=10)
    assert ld.get("reason") == "not_your_unit", f"expected deny reason 'not_your_unit', got {ld}"
    print(f"PASS run_deny_path: client intent on host-owned unit {host_owned['id']} "
          f"denied({ld['reason']}) via event_state.lastDeny")


def test_atom_turn_e2e():
    host, client, actor, soldier_id = bring_up_qualifying_battle()
    try:
        battle_t0 = time.time()  # battle-phase wall-clock starts once the battle is live

        actor_id = actor["id"]
        from_dir = actor["direction"]
        to_dir = (from_dir + 4) % 8  # face 180 degrees
        before_tu = actor["tu"]

        # --- t=0 hash-clean sanity (SS2.8's own boundary-sweep language) ---
        assert_hash_clean(host, client, buckets=["unitsStats"], what="at t=0 (pre-action)")

        # --- RW-FIX-TURN: turn-counter parity + FULL 8-bucket equality ---
        # bring_up_qualifying_battle() -> drive_to_battlescape() already ran
        # dismiss_battle_start_overlays(host), so the host has been through
        # InventoryState::btnOkClick -> SavedBattleGame::startFirstTurn() ->
        # `_turn = 1` by this point. Before the RW-FIX-TURN client mirror the
        # client sat at turn 0 FOREVER (its snapshot blob was streamed while
        # the host was still at turn 0, and nothing on the wire or in CoopMod
        # ever corrected it) - which is exactly the saveBlob-ONLY `hash_now
        # full` mismatch recorded as R3-P1 surprise #2 and RCA'd by the owner
        # on 2026-09-01. These two asserts are that surprise's regression gate.
        assert_turn_parity(host, client, "at t=0, post-overlay-dismissal")
        t0_h, _ = assert_hash_clean(host, client, full=True,
                                    what="at t=0, post-overlay-dismissal (RW-FIX-TURN)")
        print(f"PASS RW-FIX-TURN: battle_state.turn == 1 on BOTH machines and hash_now "
              f"full={len(t0_h)}/8 buckets EQUAL post-overlay-dismissal")

        # --- drive the client action via battle_intent (RB-D32) ---
        baseline = event_seq_baseline(client)
        intent_resp = client.ok({"cmd": "battle_intent", "kind": "turn",
                                  "actor": actor_id, "toDir": to_dir})
        assert intent_resp.get("iseq"), f"battle_intent did not mint an iseq: {intent_resp}"

        wait_settled(host, client, baseline)

        host_state = host.cmd({"cmd": "battle_state"})
        client_state = client.cmd({"cmd": "battle_state"})
        host_unit = units_by_id(host_state)[actor_id]
        client_unit = units_by_id(client_state)[actor_id]

        assert host_unit["direction"] == to_dir, (
            f"host unit {actor_id} direction={host_unit['direction']}, expected {to_dir} - "
            "the admitted turn itself never completed on the host")
        assert client_unit["direction"] == to_dir, (
            f"client unit {actor_id} direction={client_unit['direction']}, expected {to_dir} "
            f"(host direction={host_unit['direction']}) - bt_ev/bt_action_end apply failed")
        assert client_unit["tu"] == host_unit["tu"], (
            f"client/host TU differ after the turn: client={client_unit['tu']} "
            f"host={host_unit['tu']}")
        assert client_unit["tu"] < before_tu, (
            f"TU did not decrease from the pre-turn value ({before_tu}) - got "
            f"{client_unit['tu']}")

        assert_hash_clean(host, client, buckets=["unitsStats"], what="post-turn")
        assert_turret_parity(host, client, "after the e2e turn")

        assert_events(client, ["turn", "bt_action_end"])

        elapsed = time.time() - battle_t0
        print(f"PASS test_atom_turn_e2e: unit {actor_id} turned {from_dir} -> {to_dir}, "
              f"TU {before_tu} -> {client_unit['tu']} on both machines, hash-clean, "
              f"battle-phase wall-clock={elapsed:.2f}s")
        assert elapsed < 5.0, f"battle-phase wall-clock {elapsed:.2f}s exceeds the 5s target"

        # --- ONE faithful-UI variant: proves the RB-D10 secondaryAction
        # intercept end-to-end via a real right-click ---
        run_ui_variant(host, client, actor_id, client_unit["direction"])

        # --- deny path: client intents a HOST-owned unit ---
        run_deny_path(client, host_state, soldier_id)

        # --- acceptance: queueDepth back to 0 on both machines ---
        host_es = host.cmd({"cmd": "event_state"})
        client_es = client.cmd({"cmd": "event_state"})
        assert host_es.get("queueDepth") == 0, f"host queueDepth != 0: {host_es}"
        assert client_es.get("queueDepth") == 0, f"client queueDepth != 0: {client_es}"

        print("PASS test_atom_turn_e2e: queueDepth 0 on both machines after all actions")

        # --- RW-FIX-TURN + RW-FIX-TURRET: turn-counter parity, turret parity,
        # and FULL 8-bucket equality AFTER every action above - the G5 item-5
        # shape (`hash_now full` equal once real actions have run, not only at
        # t=0) ---
        # HISTORY (why this assert used to be 7/7): after the RW-FIX-TURN
        # counter mirror landed, saveBlob still diverged post-action. The
        # first attribution (per-tile FOV `discovered` bits) was WRONG - the
        # orchestrator's 2026-09-02 probes showed `hash_now full` 8/8 EQUAL
        # pre-action while mapDiscoveredFloor already read host=1044 vs
        # client=538, i.e. saveBlobMaskFowBinTiles (SharedEcon.cpp) already
        # masks those bits out of the hash. A save_game diff of both machines
        # then produced exactly ONE non-excluded differing line:
        # `directionTurret` (host=0, client=2 after two rotations). Fixed in
        # RW-FIX-TURRET (emit carries turretFrom/turretTo on every turn ev;
        # the applier writes the body facing without dragging the turret and
        # takes the turret only from the ev) - so saveBlob is back IN scope
        # here and this assert is a full 8/8 again.
        assert_turn_parity(host, client, "after all actions")
        n_units = assert_turret_parity(host, client, "after all actions")
        post_h, _ = assert_hash_clean(host, client, full=True,
                                      what="after all actions (RW-FIX-TURRET, full 8/8)")
        print(f"PASS test_atom_turn_e2e: turn 1/1, directionTurret equal on all {n_units} "
              f"units, and {len(post_h)}/8 buckets (saveBlob included) EQUAL on both "
              "machines after all actions")
        assert len(post_h) == 8, (
            f"hash_now full returned {len(post_h)} buckets, expected 8 "
            f"({sorted(post_h)}) - the spike bucket set changed under this test")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    test_atom_turn_e2e()
    print("ALL R3-P1 ATOM TURN E2E TESTS PASSED")


if __name__ == "__main__":
    main()
