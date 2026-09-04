"""FX-1 (WAVE1-RUNBOOK.md REV E.1, WV-D56): the HOST INPUT FREEZE.

AI-neutral: asserts only at t=0, before any side advances.

WHY THIS EXISTS. WV-D56 moves the coop blob snapshot and the `battle_offer`
that advertises it from `offerBattle()` (battle-generation time, before
BriefingState even exists) to `CoopHandshake::emitPreparedOffer()`, called
from `BriefingState::btnOkClick`'s freeze branch AFTER
`SavedBattleGame::startFirstTurn()`. That branch has ALREADY pushed
`BattlescapeState` (+ `NextTurnState` on top of it) by the time it calls
`emitPreparedOffer()` - so the host now sits inside `BattlescapeState`,
possibly with `NextTurnState` already dismissed, for the entire remainder of
the handshake round trip (offer sent -> client accepts -> blob streams ->
client loads -> `battle_ready` -> host `onReady()` -> phase Active). Every
coop input gate that reads `isCoopBattle()` (`== phase Active`) is
PERMISSIVE in that window, because phase is still `Handshake` - so without a
freeze, the host could walk/turn/kneel units LOCALLY (a state mint with
nothing on the wire) while the client is still loading its own copy of the
world. `CoopBattleUi::freezeBattleInputUntilActive()`, hooked at the top of
`BattlescapeState::handle`, closes that window.

THE ESCAPE HATCH (REV E.1 S-4, the reason this file is not a one-line proof).
An UNCONDITIONAL early return in `BattlescapeState::handle` would ALSO block
`State::handle()` below it - the ONLY dispatch path to `_btnHelp` (Options)
and `_btnAbort` - trapping a waiting host with no way to open Options, save,
or abandon. The fix carries a PRE-DECIDED, narrow exemption: the
`Options::keyBattleOptions` KEY (not a widget), gated on `!_save->isPreview()`
exactly like vanilla's own `_btnHelp` binding. This file proves BOTH halves:
the freeze actually freezes map input, AND the escape hatch actually opens
Options without itself counting as (or breaking) the freeze.

FIXTURE. A normal 2-seat craft skirmish (test_rw_handshake.py's own lobby
drive - `bring_up_lobby()`/`skirmish_host()`/`skirmish_client_at_browser()`,
the same precedent-following inline copies every rewrite test in this
directory carries). The CLIENT is deliberately held back: it connects far
enough to make the host's own lobby-start flow eligible
(`LobbyMenu::startEligible()` requires `session.clientInLobby`, so the client
must at least `join_tcp` + confirm its `Profile` popup to reach `LobbyMenu`),
and is then NEVER driven any further by this file - no `lobby_action`, no
`NewBattleState` navigation, nothing. Its actual battle entry is 100%
network-driven (`CoopHandshake::onOffer`/`onBlobChunkAppended`/`onReady`),
never a test-issued click, so "the client is held back" is true in the only
sense that matters here: it makes zero progress until the HOST'S OWN OK
click on its briefing causes `emitPreparedOffer()` to actually send the
offer - which, under WV-D56, is later than it has EVER been in this test
suite (after `startFirstTurn()`, with `BattlescapeState`+`NextTurnState`
already on the host's stack).

REV E.1 (IR3-3): NextTurnState MUST be dismissed via the `close_nextturn`
lever (`NextTurnState::close()` called directly, TestServer.cpp) BEFORE any
of the freeze assertions - `BriefingState::btnOkClick` pushes `NextTurnState`
ABOVE `BattlescapeState`, and `Game::run()` dispatches input only to the TOP
state, so `BattlescapeState::handle` (and therefore the freeze) is simply
never reached while `NextTurnState` sits on top. That window is not what this
file measures - it dismisses `NextTurnState` immediately (racing the
handshake round trip, which needs a real TCP round trip + blob stream + hash
compare to complete) and RE-ASSERTS `phase == "Handshake"` right after, so a
too-slow dismissal fails loudly instead of silently testing nothing.

Run:  python tools/coop_test/test_rw_host_input_freeze.py
      (its own shell invocation - one harness run at a time, machine-wide.)
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session

SDLK_ESCAPE = 27


# ---------------------------------------------------------------- helpers ---
def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def battle_state(gc):
    return gc.cmd({"cmd": "battle_state"})


def event_state(gc):
    return gc.cmd({"cmd": "event_state"})


def selected_unit(bs):
    sel_id = bs.get("selectedId", -1)
    for u in bs.get("units", []):
        if u.get("id") == sel_id:
            return u
    return None


# Direction -> (dx, dy) step table, 0=North clockwise - the same table every
# other rewrite repro in this directory uses (repro_atom_turn.py's own copy).
DIR_DX = [0, 1, 1, 1, 0, -1, -1, -1]
DIR_DY = [-1, -1, 0, 1, 1, 1, 0, -1]


def center_on_selection(gc):
    gc.ok({"cmd": "inject_input", "kind": "key", "key": 278})  # SDLK_HOME
    time.sleep(0.15)


def find_move_click(gc, actor):
    """W1-P6's self-verifying `map_tile_click_pos` recipe (repro_atom_turn.py's
    `tile_click` precedent): resolve a REAL screen (winX, winY) for one of the
    actor's 8 neighbour tiles, so "the SAME ground click" used for the frozen
    check can ALSO be relied on to actually move the unit once unfrozen -
    proving movement, not just an absence of refusal. Returns (winX, winY,
    target-tile) for the first neighbour the probe verifies, or None if none
    of the 8 does (a FIXTURE condition on this particular map roll, never a
    result about the freeze itself)."""
    center_on_selection(gc)
    for d in range(8):
        tx = actor["x"] + DIR_DX[d]
        ty = actor["y"] + DIR_DY[d]
        tz = actor["z"]
        pr = gc.cmd({"cmd": "map_tile_click_pos", "x": tx, "y": ty, "z": tz})
        if pr.get("verified"):
            return pr["winX"], pr["winY"], (tx, ty, tz)
    return None


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
    """test_rw_handshake.py's own lobby drive, the precedent every rewrite
    test in this directory follows (repro_atom_turn.py's own docstring cites
    it). The client reaches LobbyMenu here and is NEVER driven past it by
    this file - see the module docstring's FIXTURE section for why that is
    "held back" in the sense this packet's spec means."""
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


# ------------------------------------------------------------------- main ---
def main():
    port = "47997"
    host_dir = make_user_dir("rw_freeze_host")
    client_dir = make_user_dir("rw_freeze_client")
    host = GameClient("host", 48850, host_dir)
    client = GameClient("client", 48851, client_dir)
    try:
        bring_up_lobby(host, client, port)

        # === host alone into NEW BATTLE > OK; the client stays parked on ====
        # === LobbyMenu, driven by nothing but the wire from here on. ========
        host.ok({"cmd": "lobby_action"})
        host.wait_for("host at battle settings",
                      lambda: (not session.has_state(host, "LobbyMenu")) or None)
        assert top_state(host) == "NewBattleState", \
            f"host should land on the NEW BATTLE setup screen, stack={states(host)}"

        host.ok({"cmd": "newbattle_ok"})
        host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"),
                      timeout=30)

        # WV-D56: prepareBattleOffer() has run (battleId minted, phase ->
        # Handshake) but emitPreparedOffer() has NOT - the snapshot/offer are
        # deferred to the freeze branch of btnOkClick, which the host has not
        # clicked yet. Nothing has been sent; the client (still on LobbyMenu)
        # has learned nothing about this battle.
        bs0 = battle_state(host)
        assert bs0.get("phase") == "Handshake", (
            f"host phase should be Handshake right after newbattle_ok, before the "
            f"briefing OK click (prepareBattleOffer() ran, emitPreparedOffer() has "
            f"not): {bs0}")
        assert top_state(client) == "LobbyMenu", (
            f"client should still be sitting on LobbyMenu, untouched by this file - "
            f"got stack={states(client)}")
        print("PASS: prepareBattleOffer() ran (phase=Handshake) with nothing sent - "
              "client still parked on LobbyMenu, never driven")

        # === dismiss BriefingState -> emitPreparedOffer() actually fires =====
        host.ok({"cmd": "click_widget", "match": "ok"})

        # REV E.1 (IR3-3): NextTurnState sits ABOVE BattlescapeState the instant
        # btnOkClick pushes both, and Game::run() only dispatches to the TOP
        # state - so BattlescapeState::handle (and the freeze) is unreachable
        # until NextTurnState is gone. Race the handshake round trip: dismiss it
        # via the real close() (not dismiss_popup, which only pops without
        # running it) as fast as this process can issue the command.
        host.wait_for("host has a NextTurnState to close",
                      lambda: session.has_state(host, "NextTurnState"), timeout=15)
        nt = host.ok({"cmd": "close_nextturn"})
        assert nt.get("ok"), f"close_nextturn failed: {nt}"
        assert top_state(host) == "BattlescapeState", (
            f"host top state should be BattlescapeState right after closing "
            f"NextTurnState, stack={states(host)}")

        bs1 = battle_state(host)
        assert bs1.get("phase") == "Handshake", (
            f"host phase should STILL be Handshake immediately after dismissing "
            f"NextTurnState (the handshake round trip - offer send, client accept, "
            f"blob stream, battle_ready, onReady - has not had time to complete): "
            f"{bs1}")
        print("PASS (REV E.1 IR3-3): NextTurnState dismissed via close_nextturn, "
              "host on BattlescapeState, phase STILL Handshake - the freeze window "
              "is open and observable")

        # === the ordering seat's unit, for the before/after position+TU check ===
        actor = selected_unit(bs1)
        assert actor is not None, f"host has no selected unit: {bs1}"
        before = (actor["x"], actor["y"], actor["z"], actor["tu"])
        es_before = event_state(host)

        # THE SAME ground click is reused for every click in this file (frozen
        # AND unfrozen): a real, verified screen position over one of the
        # actor's neighbour tiles, resolved ONCE while the map/camera state is
        # settled. This is what lets the LAST assertion below ("the SAME ground
        # click DOES move the unit") be a real move, not just an absence of
        # refusal - repro_atom_turn.py's `tile_click` precedent.
        click = find_move_click(host, actor)
        assert click is not None, (
            f"FIXTURE: none of the actor's 8 neighbour tiles verified through "
            f"map_tile_click_pos - cannot resolve a real move-click for this "
            f"boot's map/camera state (actor at {(actor['x'], actor['y'], actor['z'])})")
        click_x, click_y, click_tile = click
        print(f"fixture: move-click resolved to window ({click_x},{click_y}) -> "
              f"tile {click_tile}")

        # === FROZEN: a ground click changes NOTHING ==========================
        host.ok({"cmd": "inject_input", "kind": "click", "x": click_x, "y": click_y})
        time.sleep(0.3)

        bs2 = battle_state(host)
        actor2 = selected_unit(bs2)
        after = (actor2["x"], actor2["y"], actor2["z"], actor2["tu"])
        assert after == before, (
            f"a ground click while phase=={bs2.get('phase')} moved the selected "
            f"unit: before={before} after={after} - the host input freeze did not "
            "hold")
        es_after = event_state(host)
        # NOTE (reveal-flush race RCA, orchestrator-traced): `lastSeqEmitted`
        # is NOT click-specific here and must not be used as the freeze proof.
        # Under WV-D56, `emitPreparedOffer()` (fired above, at the briefing OK
        # click) calls `CoopReveal::seedPublished()`, which seeds fog-reveal
        # evs the pump flushes ASYNCHRONOUSLY at a nondeterministic tick. When
        # such a flush lands inside this ~0.3s window, `lastSeqEmitted` moves
        # (e.g. 0->1) even though the click itself minted nothing - a NO-CLICK
        # control reproduced the same seq bump 6/6 times, and `event_log`
        # showed both bumped seqs are `kind='reveal'`, never an action. Assert
        # CLICK-SPECIFICALLY instead: a frozen click never reaches the walk
        # arm at all (repro_atom_walk.py / test_rw_input_gating.py's own
        # `coopWalkArmEntered`-unchanged precedent), so the arm-entry counter
        # must not move and no order may have left this machine.
        assert es_after["coopWalkArmEntered"] == es_before["coopWalkArmEntered"], (
            f"coopWalkArmEntered moved from {es_before['coopWalkArmEntered']} to "
            f"{es_after['coopWalkArmEntered']} while frozen - the click reached "
            "the walk arm despite the freeze")
        assert es_after["coopWalkIntentsSent"] == 0, (
            f"coopWalkIntentsSent is {es_after['coopWalkIntentsSent']} after a "
            "ground click during the freeze window - the click became an order "
            "despite the freeze")
        assert es_after["coopHostInputFrozenRefusals"] > 0, (
            f"coopHostInputFrozenRefusals is {es_after['coopHostInputFrozenRefusals']} "
            "after a ground click during the freeze window - this is a POSITIVE "
            "delivery proof, not an absence, and it did not fire: "
            f"{es_after}")
        r_after_click = es_after["coopHostInputFrozenRefusals"]
        print(f"PASS: frozen ground click moved nothing (pos/tu unchanged: {before}), "
              f"coopWalkArmEntered unchanged ({es_after['coopWalkArmEntered']}), "
              f"coopWalkIntentsSent=0, "
              f"coopHostInputFrozenRefusals={r_after_click} (> 0)")

        # === the deployed banner text, EXACT (WV-D17: never non-emptiness) ===
        # Read HERE, guaranteed still inside the Handshake window (the frozen
        # click above just proved it) - the round trip that follows can close
        # that window at any moment (measured: well under a second once the
        # client is already connected), so this is the last point this file can
        # rely on phase still being Handshake.
        assert bs2.get("coopWaitText") == "Waiting for the other player to join the battle", (
            f"battle_state.coopWaitText should be the deployed STR_COOP_WAITING_FOR_JOIN "
            f"text exactly: {bs2.get('coopWaitText')!r}")
        print(f"PASS: battle_state.coopWaitText == {bs2['coopWaitText']!r} (exact)")

        # === REV E.1 (S-4): THE ESCAPE HATCH ==================================
        # MEASURED (this file's own first runs): once the client is already
        # connected and idle in the lobby (required for LobbyMenu::
        # startEligible() to ever let the host past it), the handshake round
        # trip - offer send, accept, ~140 KB blob stream, hash compare,
        # onReady -> phase Active - completes in well under a second. Every
        # assertion up to and including the escape-hatch open below is proven
        # to land inside that window (this file's own PASS lines evidence it);
        # what happens AFTER the PauseState round trip is NOT assumed - it is
        # READ, once, and branched on. Neither branch below weakens an
        # assertion: each is the correct, full-strength check for the phase
        # actually observed.
        r0 = event_state(host)["coopHostInputFrozenRefusals"]
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_ESCAPE})
        host.wait_for("host PauseState opened by the Options-key hatch",
                      lambda: session.has_state(host, "PauseState"), timeout=10)
        lw = host.cmd({"cmd": "list_widgets"})
        assert "PauseState" in lw.get("state", ""), (
            f"the Options-key hatch should have opened PauseState: {lw}")
        r1 = event_state(host)["coopHostInputFrozenRefusals"]
        assert r1 == r0, (
            f"coopHostInputFrozenRefusals moved from {r0} to {r1} when the host "
            "pressed the Options key while frozen - the hatch's `&&` short-circuit "
            "is wrong: the exemption must not itself count as (or trigger) a refusal")
        print(f"PASS (REV E.1 S-4): the Options-key hatch opened PauseState from a "
              f"FROZEN battlescape without moving coopHostInputFrozenRefusals "
              f"({r0} -> {r1})")

        # Dismiss PauseState (its own `_btnCancel` is bound to the SAME key,
        # PauseState.cpp:112/119 - unaffected by this file's freeze, which only
        # ever hooks BattlescapeState::handle). A short settle first: pressing a
        # second key immediately after the state that just opened has not yet
        # had a pump cycle to process its OWN init is unreliable in this
        # harness (measured - every other UI-transition site in this directory
        # sleeps for the same reason, e.g. repro_atom_turn.py's tile_click).
        time.sleep(0.3)
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_ESCAPE})
        time.sleep(0.3)
        host.wait_for("host back on BattlescapeState after PauseState",
                      lambda: top_state(host) == "BattlescapeState", timeout=10)

        bs3 = battle_state(host)
        if bs3.get("phase") == "Handshake":
            # The window survived the PauseState round trip: prove the freeze
            # is STILL ARMED (spec's own "one more ground click still moves
            # nothing and the counter rises again" - the non-vacuity control
            # for THIS half: a freeze that silently lifted during PauseState
            # would also have let this click through).
            actor3 = selected_unit(bs3)
            before2 = (actor3["x"], actor3["y"], actor3["z"], actor3["tu"])
            r2 = event_state(host)["coopHostInputFrozenRefusals"]
            host.ok({"cmd": "inject_input", "kind": "click", "x": click_x, "y": click_y})
            time.sleep(0.3)
            bs4 = battle_state(host)
            actor4 = selected_unit(bs4)
            after2 = (actor4["x"], actor4["y"], actor4["z"], actor4["tu"])
            r3 = event_state(host)["coopHostInputFrozenRefusals"]
            assert after2 == before2, (
                f"a ground click after dismissing PauseState moved the unit: "
                f"before={before2} after={after2} - the freeze did not survive the "
                "PauseState round trip")
            assert r3 > r2, (
                f"coopHostInputFrozenRefusals did not rise after dismissing "
                f"PauseState and clicking again ({r2} -> {r3}) - the freeze may "
                "have been silently lifted by the PauseState round trip")
            print(f"PASS: after dismissing PauseState the freeze is STILL armed "
                  f"(pos/tu unchanged, coopHostInputFrozenRefusals {r2} -> {r3})")
        else:
            # The handshake completed WHILE this file was driving PauseState -
            # legitimate under the measured sub-second round trip. Nothing to
            # assert here (there is no "still Handshake" left to prove); the
            # non-vacuity control below covers the same ground from the other
            # side (freeze correctly LIFTED, not silently disabled).
            print(f"NOTE: host phase is already {bs3.get('phase')!r} - the handshake "
                  "completed during the PauseState round trip (measured sub-second "
                  "once the client is pre-connected). Skipping the redundant "
                  "'still Handshake' re-check; the Active-phase non-vacuity control "
                  "below covers the freeze-lifted proof.")

        # === now make sure the client actually joins, and prove the freeze LIFTS ==
        host.wait_for("host phase reaches Active",
                      lambda: (battle_state(host).get("phase") == "Active") or None,
                      timeout=60)
        client.wait_for("client phase reaches Active",
                        lambda: (battle_state(client).get("phase") == "Active") or None,
                        timeout=60)
        print("PASS: both machines reached phase Active - the handshake completed")

        r4 = event_state(host)["coopHostInputFrozenRefusals"]
        bs5 = battle_state(host)
        actor5 = selected_unit(bs5)
        before3 = (actor5["x"], actor5["y"], actor5["z"], actor5["tu"])

        host.ok({"cmd": "inject_input", "kind": "click", "x": click_x, "y": click_y})

        def _moved():
            u = selected_unit(battle_state(host))
            return u is not None and (u["x"], u["y"], u["z"], u["tu"]) != before3
        host.wait_for("the unfrozen ground click to move the actor", lambda: _moved() or None,
                      timeout=15)

        bs6 = battle_state(host)
        actor6 = selected_unit(bs6)
        after3 = (actor6["x"], actor6["y"], actor6["z"], actor6["tu"])
        r5 = event_state(host)["coopHostInputFrozenRefusals"]

        assert r5 == r4, (
            f"coopHostInputFrozenRefusals rose from {r4} to {r5} AFTER phase reached "
            "Active - the freeze is still refusing input once it should have "
            f"self-lifted: {bs6}")
        assert after3 != before3, (
            f"the SAME ground click that was refused while frozen did not move the "
            f"unit once phase reached Active: before={before3} after={after3} - the "
            "freeze lifted (no refusal) but nothing downstream actually let the "
            "click through")
        print(f"PASS (non-vacuity control): once Active, the SAME ground click "
              f"({click_x},{click_y}) no longer refuses (coopHostInputFrozenRefusals "
              f"stayed at {r5}) AND actually moves the unit: before={before3} "
              f"after={after3}")

        print("ALL FX-1 HOST-INPUT-FREEZE CHECKS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
