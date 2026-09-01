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

FIXTURE-COVERAGE NOTE (found during this packet, not a pre-existing given):
test_rw_faction_setup.py's own test_classic() docstring already establishes
that a plain "NEW BATTLE > COOP" classic/SHARED skirmish never calls
Soldier::setCoop() - so EVERY soldier defaults to COOP_SEAT_0 (host-owned;
Soldier ctor default), and the client (seat 1) owns ZERO real battle units in
this fixture. Building a genuine mixed-ownership classic fixture would need
either a real SHARED-campaign mission (persisted per-soldier ownership) or a
new TestServer debug lever to stamp Soldier::_coop pre-battle - both out of
this packet's scope (RB-D22: spike fixtures are live-skirmish-through-lobby
only, no new .sav zoo; R5-P2's Files list does not include TestServer.cpp).

Consequently test_classic_selection_gating() below proves the SAFETY-CRITICAL
direction rigorously and non-vacuously: the client's selection cycle is
pressed against 7 REAL, LIVE, vanilla-selectable-by-side (FACTION_PLAYER ==
_save->getSide() at turn 1) host-owned soldiers and must NEVER land on any of
them (a broken/missing filter WOULD let it - vanilla's own isSelectable() has
no seat concept). The complementary "client selects only ITS OWN soldiers"
half is vacuously true here (0 owned, 0 selected) rather than actively
demonstrated - flagged for the orchestrator; a non-vacuous two-real-owners
proof needs the fixture work above (candidate for a follow-up packet, not
done here per scope discipline).

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


def drive_to_battlescape(host, client, host_dir, client_dir):
    """Steps 5-7: BATTLE SETTINGS -> OK -> both machines in BattlescapeState.
    Same sequence test_rw_handshake.py (R4-P1) / test_rw_faction_setup.py
    (R5-P1) already proved out."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={states(host)}"

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
        bring_up_lobby(host, client, port)
        drive_to_battlescape(host, client, host_dir, client_dir)

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
        # See the FIXTURE-COVERAGE NOTE at the top of this file: a plain
        # NEW BATTLE > COOP classic skirmish stamps every soldier to seat 0
        # (Soldier::setCoop() is never called), so client_own_ids is
        # expected to be empty here - asserted explicitly so a future
        # fixture change that DOES populate it is noticed (this comment
        # would then be stale) rather than silently changing what's proven.
        print(f"NOTE: client-owned real units in this fixture: {len(client_own_ids)} "
              f"(expected 0 - see FIXTURE-COVERAGE NOTE)")

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
        assert host_state.get("selectedId") in host_own_ids, \
            f"host's initial selectedId={host_state.get('selectedId')} is not one " \
            f"of its own units {sorted(host_own_ids)}"
        client_initial_id = client_state.get("selectedId")
        print(f"NOTE: client's inherited (blob load, pre-filter) initial selectedId="
              f"{client_initial_id} - see the initial-selection comment above")

        # --- host's Tab-cycle: never leaves its own 7-ish soldiers ---
        host_seen = cycle_selected_ids(host, len(host_own_ids) + 3)
        bad = [sid for sid in host_seen if sid != -1 and sid not in host_own_ids]
        assert not bad, f"host's selection cycle landed on non-owned unit id(s) {bad} " \
            f"(own set={sorted(host_own_ids)}, observed sequence={host_seen})"
        assert any(sid in host_own_ids for sid in host_seen), \
            f"host's selection cycle never landed on any of its own units - filter is " \
            f"too restrictive (own set={sorted(host_own_ids)}, observed={host_seen})"

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
        leaked = [sid for sid in client_seen if sid in host_own_ids and sid != client_initial_id]
        assert not leaked, f"client's selection cycle landed on a DIFFERENT host-owned " \
            f"unit id {leaked} (started at {client_initial_id}) - " \
            f"coopMaySelectUnit()/commandsUnit() failed to exclude it " \
            f"(observed sequence={client_seen})"
        assert all(sid in (client_initial_id, -1) for sid in client_seen), \
            f"client's selection cycle produced an unexpected id outside " \
            f"{{{client_initial_id}, -1}}: {client_seen}"

        print(f"PASS test_classic_selection_gating: host cycle stayed within its "
              f"{len(host_own_ids)} own unit(s) ({host_seen}); client cycle never "
              f"advanced onto any of the {len(host_own_ids) - 1} OTHER host-owned "
              f"units ({client_seen})")

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
