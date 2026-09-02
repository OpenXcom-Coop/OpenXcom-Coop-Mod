"""R5-P2 (rewrite spike, SPIKE-RUNBOOK.md R5-P2 packet text): input-gating
probe for BattleAuthority::commandsUnit()/mySideActive() and the THIN vanilla
hooks that gate on them (BattlescapeGame::primaryAction/secondaryAction,
BattlescapeState::btnKneelClick, SavedBattleGame::selectPlayerUnit's
selection-cycle filter, BattlescapeState::btnEndTurnClick's REVIEW4 IR-13
no-op guard).

Drive: a real 2-player classic coop skirmish through the harness lobby flow -
the SAME UI path test_rw_handshake.py (R4-P1) and test_rw_faction_setup.py
(R5-P1) already proved out. Lobby helpers are INLINED here (not imported)
per test_rw_faction_setup.py's own precedent: test_skirmish_flow.py (which
pvp_fixture.py imports) still carries a pre-existing SKIP-PENDING(R4-P1)
guard that exits at import time.

PRE-R3-P1 NOTE (packet text, important): R3-P1's client intent path does NOT
exist yet (it lands AFTER G4 - see CoopArbiter.h's "PLACE new callers here"
marker at the secondaryAction/btnKneelClick sites, and this file's own
R2-P5 grep confirms neither vanilla site had a call before this packet). So
the "client click on peer unit -> deny(not_your_unit)" clause CANNOT be
exercised now - this file asserts SELECTION FILTERING (+ the IR-13 end-turn
no-op) ONLY, exactly as the packet text allows ("if run pre-R3-P1: assert
selection filtering only").

FIXTURE-COVERAGE NOTE - GAP CLOSED IN W1-P1 (wave 1, EXIT-REPORT-G5 HANDOFF
item 5). As originally written this file could only prove the SAFETY-CRITICAL
direction: a plain "NEW BATTLE > COOP" classic skirmish never calls
Soldier::setCoop(), so EVERY soldier defaulted to COOP_SEAT_0 (host-owned) and
the client owned ZERO real battle units - which made the complementary "client
selects only ITS OWN soldiers" half VACUOUSLY true (0 owned, 0 selected)
rather than actively demonstrated.

R3-P1 shipped the lever that closes it - NewBattleState::harnessSeatOneSoldier()
via TestServer's "newbattle_seat_soldier" (TestServer.cpp:4453), stamping ONE
soldier on the selected craft to seat 1 BEFORE newbattle_ok generates the
battle. drive_to_battlescape() below now calls it, exactly the way
repro_atom_turn.py:137 / repro_atom_kneel.py:149 / test_rw_retry_cancel.py:169
already do (WV-D18: reuse repro_atom_turn's helper set, do not invent a new
fixture path). Observed shape at 8c53c2592: units 9..14 coop==0 (host) and
unit 8 coop==1 (client).

BOTH directions are now non-vacuous, and each has an explicit guard assertion
in front of it so the test can NEVER pass by having nothing to select:
  - >= 1 CLIENT-owned unit exists (the W1-P1 acceptance gate), and the
    client's Tab-cycle actively lands on one and only ever on client-owned
    ids;
  - >= 1 HOST-owned unit exists, the host's Tab-cycle stays inside them, and
    it must NEVER land on the client-owned unit - an exclusion that had
    nothing to exclude before this packet.

SECOND VACUITY FOUND AND CLOSED HERE (W1-P1, from a probe run, not assumed):
the host's Tab presses were being swallowed. A freshly generated battle leaves
NextTurnState + InventoryState stacked ON TOP of BattlescapeState (observed
host stack after the briefing OK: ['BattlescapeState', 'NextTurnState',
'InventoryState']) and Game::run() only think()s _states.back(), so
inject_input TAB never reached BattlescapeState::btnNextSoldierClick and
selectedId simply never moved. drive_to_battlescape() now dismisses those
overlays with repro_atom_turn.py:161's own documented ESC helper before any
assertion runs. (The CLIENT never sees those overlays - it loads the streamed
blob straight into BattlescapeState - so its half was always really pressing
keys.)

Run:  python tools/coop_test/test_rw_input_gating.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session

FACTION_PLAYER = 0
COOP_SEAT_NONE = -1
COOP_SEAT_0 = 0
COOP_SEAT_1 = 1

SDLK_BACKSPACE = 8   # Options::keyBattleEndTurn default
SDLK_TAB = 9         # Options::keyBattleNextUnit default


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


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
    """Steps 1-4 of the skirmish lobby flow (test_rw_faction_setup.py's own
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


def dismiss_battle_start_overlays(host, timeout=10):
    """repro_atom_turn.py:157-161's helper, reused verbatim in shape (WV-D18).

    A freshly generated battle pushes vanilla's own "Turn 1 begins"
    (NextTurnState, closed by ANY key/click) and the pre-battle equip screen
    (InventoryState, closed by Options::keyCancel/SDLK_ESCAPE) ON TOP of
    BattlescapeState. Game::run() only think()s _states.back(), so until they
    are gone an injected TAB never reaches BattlescapeState's own handlers and
    the selection cycle this file exists to test silently does nothing.
    HOST-only: the client loads the streamed blob straight into
    BattlescapeState with no generation-time popups."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = states(host)
        if st and st[-1] == "BattlescapeState":
            return
        host.ok({"cmd": "inject_input", "kind": "key", "key": 27})  # SDLK_ESCAPE
        time.sleep(0.3)
    raise TimeoutError(f"host: battle-start overlays never cleared, stack={states(host)}")


def drive_to_battlescape(host, client, host_dir, client_dir, seated_holder):
    """Steps 5-7: BATTLE SETTINGS -> OK -> both machines in BattlescapeState.
    Same sequence test_rw_handshake.py (R4-P1) / test_rw_faction_setup.py
    (R5-P1) already proved out, extended in W1-P1 with R3-P1's seat-1 stamp
    (see this file's FIXTURE-COVERAGE NOTE) and the battle-start overlay
    dismissal."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={states(host)}"

    # W1-P1 / WV-D18: stamp ONE soldier on the selected craft to seat 1 BEFORE
    # generation, so the client really owns a unit (repro_atom_turn.py:137).
    seat_resp = host.ok({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1})
    seated_holder["soldierId"] = seat_resp["soldierId"]

    host.ok({"cmd": "newbattle_ok"})

    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=30)
    client.wait_for("client battlescape",
                    lambda: session.has_state(client, "BattlescapeState"), timeout=60)

    time.sleep(3)  # let both logs flush the handshake lines before reading them

    host_log = log_lines(host_dir)
    client_log = log_lines(client_dir)
    equal_lines = grep_lines(host_log, "[coop-handshake] battle_ready saveBlob EQUAL")
    mismatch_lines = grep_lines(host_log, "[coop-handshake] battle_ready saveBlob MISMATCH")
    client_active_lines = grep_lines(client_log, "[coop-handshake] CLIENT phase Active")

    assert not mismatch_lines, f"battle_ready saveBlob MISMATCH: {mismatch_lines[-1]}"
    assert equal_lines, "battle_ready arrived but 'saveBlob EQUAL' was never logged"
    assert client_active_lines, "client log missing 'CLIENT phase Active' line"

    host.ok({"cmd": "click_widget", "match": "ok"})
    host.wait_for("host battlescape",
                  lambda: session.has_state(host, "BattlescapeState"), timeout=30)
    assert session.has_state(host, "BattlescapeState"), \
        f"host should reach BattlescapeState after OK, stack={states(host)}"

    dismiss_battle_start_overlays(host)
    assert top_state(host) == "BattlescapeState", \
        f"host should be sitting ON BattlescapeState, stack={states(host)}"

    # W1-P3 (SS1 WAVE-1 ADDITIONS trap 2 / WV-D9): the client now enters the
    # battle through a read-only BriefingState pushed OVER its
    # BattlescapeState, so every fixture that DRIVES the client must dismiss
    # it explicitly - injected input would otherwise land on the briefing and
    # screen-projection probes would compute against the GEOSCAPE viewport the
    # briefing holds. No-op on a stack with no BriefingState.
    session.dismiss_client_briefing(client)


def cycle_selected_ids(gc, presses, key=SDLK_TAB):
    """Press the next-unit key `presses` times, recording battle_state's
    selectedId after each press (R2-P11's battle_state.selectedId - the same
    field test_rw_faction_setup.py's units[].coop reads sit alongside).
    Real faithful-UI input (inject_input pushes a genuine SDL_KEYDOWN/UP
    pair through Game::run's event loop), not a direct C++ call, so it
    exercises BattlescapeState::btnNextSoldierClick -> selectNextPlayerUnit()
    -> SavedBattleGame::selectNextPlayerUnit() -> selectPlayerUnit() end to
    end, same as a real player tapping Tab."""
    seen = []
    for _ in range(presses):
        gc.ok({"cmd": "inject_input", "kind": "key", "key": key})
        time.sleep(0.05)
        st = gc.cmd({"cmd": "battle_state"})
        assert st.get("ok") and st.get("inBattle"), f"battle_state failed mid-cycle: {st}"
        seen.append(st.get("selectedId", -1))
    return seen


def test_classic_selection_gating():
    port = "47995"
    host_dir = make_user_dir("rw_input_gating_host")
    client_dir = make_user_dir("rw_input_gating_client")
    host = GameClient("host", 48794, host_dir)
    client = GameClient("client", 48795, client_dir)
    try:
        seated = {}
        bring_up_lobby(host, client, port)
        drive_to_battlescape(host, client, host_dir, client_dir, seated)

        host_state = host.cmd({"cmd": "battle_state"})
        client_state = client.cmd({"cmd": "battle_state"})
        assert host_state.get("inBattle"), "host battle_state.inBattle is false"
        assert client_state.get("inBattle"), "client battle_state.inBattle is false"

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
        # --- W1-P1 NON-VACUITY GATE (the packet's own acceptance criterion) ---
        # Asserted BEFORE anything is claimed about selecting a client unit,
        # so this test can never pass by having nothing to select. It is also
        # what makes the HOST cycle's exclusion below mean something: before
        # the seat stamp there was no non-host-owned unit to exclude.
        assert len(client_own_ids) >= 1, \
            f"fixture is VACUOUS: the client owns no units. The " \
            f"newbattle_seat_soldier seat-1 stamp (soldierId=" \
            f"{seated.get('soldierId')}) did not reach the battle - " \
            f"units(coop)={sorted((u['id'], u['coop']) for u in host_units.values())}"
        assert not (host_own_ids & client_own_ids), \
            f"a unit is claimed by both seats: {sorted(host_own_ids & client_own_ids)}"
        print(f"NON-VACUITY GATE ok: client owns {len(client_own_ids)} unit(s) "
              f"{sorted(client_own_ids)}, host owns {len(host_own_ids)} "
              f"{sorted(host_own_ids)}")

        # --- initial (pre-keypress) selection ---
        # SavedBattleGame::load() deserializes "selectedUnit" directly off the
        # streamed blob (SavedBattleGame.cpp:178/285-286) - it does NOT route
        # through selectPlayerUnit(), so the CLIENT inherits whatever unit the
        # HOST had selected at snapshot time verbatim, bypassing this packet's
        # filter entirely (a pre-existing vanilla load-time fact, not a
        # regression introduced here - confirmed empirically: both machines
        # report the SAME initial selectedId below). Only the host's initial
        # selection is asserted against host_own_ids; the client's inherited
        # value is recorded, not asserted, and used as the cycle's baseline.
        # W1-P1: the host's INITIAL selection is minted at generation time,
        # before any seat filter runs, so with a seat-1 soldier in the craft it
        # can legitimately BE that soldier (observed at 8c53c2592: both
        # machines start on unit 8, the seat-1 one). Same pre-existing class as
        # the client's inherited value below (EXIT-REPORT-G5 HANDOFF item 7);
        # D6/WV-D12's "auto-select your own first unit at entry" is W1-P6's
        # work, not this packet's. So the initial value is RECORDED, and it is
        # the Tab CYCLE - the thing coopMaySelectUnit()/commandsUnit() actually
        # gates - that is asserted, on both machines.
        host_initial_id = host_state.get("selectedId")
        client_initial_id = client_state.get("selectedId")
        print(f"NOTE: initial (pre-filter) selectedId - host={host_initial_id}, "
              f"client={client_initial_id}; asserted via the Tab cycles below")

        # --- host's Tab-cycle: never leaves its own 7-ish soldiers ---
        host_seen = cycle_selected_ids(host, len(host_own_ids) + 3)
        bad = [sid for sid in host_seen if sid != -1 and sid not in host_own_ids]
        assert not bad, f"host's selection cycle landed on non-owned unit id(s) {bad} " \
            f"(own set={sorted(host_own_ids)}, observed sequence={host_seen})"
        assert any(sid in host_own_ids for sid in host_seen), \
            f"host's selection cycle never landed on any of its own units - filter is " \
            f"too restrictive (own set={sorted(host_own_ids)}, observed={host_seen})"
        # W1-P1: the exclusion direction, now with something real to exclude -
        # a live, vanilla-selectable-by-side soldier the host does NOT command.
        host_leaked = [sid for sid in host_seen if sid in client_own_ids]
        assert not host_leaked, \
            f"host's selection cycle landed on the CLIENT's unit(s) {host_leaked} " \
            f"(client set={sorted(client_own_ids)}, observed={host_seen})"
        # It must also actually MOVE - a cycle frozen on its start value would
        # satisfy every assertion above without exercising the filter at all.
        assert len(set(host_seen)) > 1 or len(host_own_ids) == 1, \
            f"host's selection cycle never advanced (observed={host_seen}) - the " \
            f"TAB presses are not reaching BattlescapeState"

        # --- client's Tab-cycle: the safety-critical, non-vacuous check (see
        # the FIXTURE-COVERAGE NOTE at the top of this file). The client owns
        # no units, so SavedBattleGame::selectPlayerUnit()'s do-while wraps
        # all the way around and - per its own pre-existing "no more units
        # found" contract (SavedBattleGame.cpp's "back to where we started"
        # branch) - leaves _selectedUnit exactly where it started (the
        # inherited value above) rather than advancing. What matters here:
        # across every press, the client's selection must NEVER move onto any
        # of the host's OTHER 6-ish real, live, vanilla-selectable-by-side
        # units - coopMaySelectUnit()/commandsUnit() is the ONLY thing vanilla
        # isSelectable() doesn't already provide to stop that.
        client_seen = cycle_selected_ids(client, len(host_own_ids) + 3)
        leaked = [sid for sid in client_seen if sid in host_own_ids]
        assert not leaked, f"client's selection cycle landed on host-owned unit id(s) " \
            f"{leaked} - coopMaySelectUnit()/commandsUnit() failed to exclude them " \
            f"(host set={sorted(host_own_ids)}, observed sequence={client_seen})"
        # --- W1-P1: the half that used to be vacuous, now ACTIVE ---
        assert any(sid in client_own_ids for sid in client_seen), \
            f"client's selection cycle never landed on one of its OWN units " \
            f"{sorted(client_own_ids)} - the filter is too restrictive, or the seat " \
            f"stamp never reached the battle (observed={client_seen})"
        assert all(sid in client_own_ids or sid == -1 for sid in client_seen), \
            f"client's selection cycle produced an id outside its own set " \
            f"{sorted(client_own_ids)} + {{-1}}: {client_seen}"

        print(f"PASS test_classic_selection_gating: host cycle stayed within its "
              f"{len(host_own_ids)} own unit(s) ({host_seen}) and never touched the "
              f"client's {sorted(client_own_ids)}; client cycle landed ONLY on its "
              f"own {sorted(client_own_ids)} ({client_seen}) and never on any of the "
              f"{len(host_own_ids)} host-owned units")

        # --- REVIEW4 IR-13: client's End Turn button is a local no-op ---
        client_turn_before = client_state.get("turn")
        client_side_before = client_state.get("side")
        client.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_BACKSPACE})
        time.sleep(0.3)
        client_state_after = client.cmd({"cmd": "battle_state"})
        assert client_state_after.get("turn") == client_turn_before, \
            f"client's End Turn key changed turn: {client_turn_before} -> " \
            f"{client_state_after.get('turn')} (IR-13 no-op guard did not hold)"
        assert client_state_after.get("side") == client_side_before, \
            f"client's End Turn key changed side: {client_side_before} -> " \
            f"{client_state_after.get('side')} (IR-13 no-op guard did not hold)"
        assert session.has_state(client, "BattlescapeState"), \
            f"client left BattlescapeState after its End Turn key, stack={states(client)}"
        print("PASS IR-13: client's End Turn key was a local no-op (turn/side unchanged)")

        # host's End Turn must remain live (hostSim==True runs vanilla locally) -
        # sanity-check only, not exercised further (ending the turn for real is
        # r3b/r4 territory - the coop turn-transition wire doesn't exist yet).
        assert host_state.get("authority", {}).get("hostSim") is True, \
            "host battle_state.authority.hostSim should be true"
        assert client_state.get("authority", {}).get("hostSim") is False, \
            "client battle_state.authority.hostSim should be false"

    finally:
        host.shutdown()
        client.shutdown()


def main():
    test_classic_selection_gating()
    print("ALL R5-P2 INPUT GATING TESTS PASSED")


if __name__ == "__main__":
    main()
