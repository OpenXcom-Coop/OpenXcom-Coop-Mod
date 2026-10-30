"""The HOST INPUT FREEZE.

AI-neutral: the parallel boot pins every non-player unit neutral (pin_ai_neutral).

WHY THIS EXISTS. While the coop battle phase is `Handshake` every coop input
gate that reads `isCoopBattle()` (`== phase Active`) is PERMISSIVE, so without
a freeze a host sitting on an input-taking BattlescapeState could walk/turn/
kneel units LOCALLY (a state mint with nothing on the wire) while the client
is still loading its own copy of the world.
`CoopBattleUi::freezeBattleInputUntilActive()`, hooked at the top of
`BattlescapeState::handle`, closes that window.

THE ESCAPE HATCH (the reason this file is not a one-line proof).
An UNCONDITIONAL early return in `BattlescapeState::handle` would ALSO block
`State::handle()` below it - the ONLY dispatch path to `_btnHelp` (Options)
and `_btnAbort` - trapping a waiting host with no way to open Options, save,
or abandon. The fix carries a narrow exemption: the
`Options::keyBattleOptions` KEY (not a widget), gated on `!_save->isPreview()`
exactly like vanilla's own `_btnHelp` binding. This file proves BOTH halves:
the freeze actually freezes map input, AND the escape hatch actually opens
Options without itself counting as (or breaking) the freeze. No other file
proves the hatch.

FIXTURE. A FRESH co-op
start never gives the host an input-taking BattlescapeState in phase
Handshake: the host reads its briefing, then its pre-battle equip
InventoryState stays on top for the whole Handshake,
so the freeze is unreachable from a fresh start. The one live window is the
rejoin RESUME handshake, which test_messages' rejoin-hold row builds; this
file copies that staging (steps boot..7):
test_rejoin_end_turn's parallel boot (test_death_side's default map)
on this file's lobby PORT, one END TURN cycle, the client leaves, a
fresh process (client2) arms the test-only hook hold_battle_ready {on: true}
and rejoins, the host presses RESUME. The host's rejoin
battle_offer reopened phase Handshake (`offerRejoinBattle`); client2's
battle_ready is stashed, so the host sits on BattlescapeState in phase
Handshake until THIS FILE releases the hold - the window is deterministic,
not a race. Every construction step is bounded; a miss is a setup failure
(test_rejoin_end_turn.miss: one CAPTURE line of every machine, then raise).
Before the client leaves, select_mover makes the actor a host soldier that can
walk onto a neighbour tile in one step (the Active control's precondition;
the parallel boot's first selection, soldier 10 at (14,20,1), is boxed in by its
squad and the craft hull), and the move-click tile is the first neighbour
that passes the read-only path_probe.

The checks:
  handshake_open "Handshake with nothing completed by the peer": phase
    Handshake after RESUME, client2's battle_ready stashed (held), never sent.
  host_on_battlescape "host on BattlescapeState, phase STILL Handshake": RESUME
    pops the reconnect dialog straight onto BattlescapeState (no NextTurnState
    on the host's stack).
  then the frozen ground click, the exact waiting banner, the Options-key
    hatch, the post-PauseState re-check (with the hold the window cannot close,
    so the re-check always runs and the phase is asserted), and once Active the
    same ground click moves the actor.

Run:  python tools/coop_test/test_host_input_freeze.py
      (its own shell invocation - one harness run at a time, machine-wide.)
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_rejoin_end_turn as rej
from test_death_side import FACTION_PLAYER
from test_delta_core import end_turn_cycle
from test_skirmish_rejoin_battle import (drop_client_mid_battle, rejoin_skirmish, dialog, in_battle_save, has,
                                         COOP_DLG_WAIT_PLAYERS, COOP_DLG_CLIENT_RESUME_HOLD)

SDLK_ESCAPE = 27
PORT = "47997"                   # this file's lobby key (unchanged)
HOST_PORT, CLIENT_PORT = 48850, 48851    # GameClient labels (each instance writes its own port file)
TEXT_WAITING_FOR_JOIN = "Waiting for the other player to join the battle"   # STR_COOP_WAITING_FOR_JOIN (en-US)
HELD_S = 10.0                    # client2's battle_ready stashed after RESUME (bounded wait)
ACTIVE_S = 60                    # phase Active on both after the release


# ---------------------------------------------------------------- helpers ---
def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


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


def unit_by_id(bs, uid):
    for u in bs.get("units", []):
        if u.get("id") == uid:
            return u
    return None


def hold(gc, **kw):
    """As test_messages.hold: the test-only client hook hold_battle_ready. {on: true}
    arms it (the handshake stashes battle_ready), {on: false} disarms it and sends the stash; without `on` it only
    reports."""
    req = {"cmd": "hold_battle_ready"}
    req.update(kw)
    r = gc.cmd(req)
    return {k: r.get(k) for k in ("ok", "error", "armed", "held", "sent")}


# Direction -> (dx, dy) step table, 0=North clockwise - the same table the
# other repros in this directory use (repro_atom_turn.py's own copy).
DIR_DX = [0, 1, 1, 1, 0, -1, -1, -1]
DIR_DY = [-1, -1, 0, 1, 1, 1, 0, -1]


def center_on_selection(gc):
    gc.ok({"cmd": "inject_input", "kind": "key", "key": 278})  # SDLK_HOME
    time.sleep(0.15)


def find_move_click(gc, actor):
    """The self-verifying `map_tile_click_pos` recipe (repro_atom_turn.py's
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
        if not can_step_to(gc, actor["id"], (tx, ty, tz)):
            continue
        pr = gc.cmd({"cmd": "map_tile_click_pos", "x": tx, "y": ty, "z": tz})
        if pr.get("verified"):
            return pr["winX"], pr["winY"], (tx, ty, tz)
    return None


def can_step_to(gc, uid, tile):
    """The move-click tile's precondition: unit `uid` reaches `tile` in ONE step (the read-only
    path_probe: vanilla Pathfinding::calculate with the plain walk click's move type; an occupied tile, a missing
    floor or a wall makes it unreachable)."""
    tx, ty, tz = tile
    pr = gc.cmd({"cmd": "path_probe", "unit": uid, "x": tx, "y": ty, "z": tz})
    return bool(pr.get("reachable")) and pr.get("steps") == 1


def select_mover(host):
    """Staging, before the client leaves (phase Active): the host's selected unit is the actor of every cell, and
    the Active control needs it to walk onto a neighbour. Keep the host's selection when one of its 8 neighbours
    passes can_step_to; else select the lowest-id live host-seat (coop 0) soldier that has one (the nearest value
    meeting the precondition) with the test command battle_action select. Returns (old id, actor id,
    tile) or None when no host soldier has a one-step neighbour (a setup failure)."""
    bs = battle_state(host)
    sel = bs.get("selectedId")
    own = [u for u in bs.get("units", []) if u.get("coop") == 0 and u.get("faction") == FACTION_PLAYER
           and not u.get("isOut")]
    for u in sorted(own, key=lambda u: (u["id"] != sel, u["id"])):
        for d in range(8):
            tile = (u["x"] + DIR_DX[d], u["y"] + DIR_DY[d], u["z"])
            if can_step_to(host, u["id"], tile):
                if u["id"] != sel:
                    host.ok({"cmd": "battle_action", "action": "select", "unit": u["id"]})
                return sel, u["id"], tile
    return None


def resolve_click_pixel(gc, tile):
    """Re-project an already-chosen tile's window pixel under the CURRENT camera.
    The pixel is camera-relative and the camera/view level move across the
    Handshake -> PauseState -> Active transitions, so a pixel resolved earlier
    can stop addressing the tile. map_tile_click_pos re-centres on the tile and
    re-projects it through the production selector path. Returns (winX, winY), or
    None if the tile cannot be clicked right now (a fixture condition)."""
    tx, ty, tz = tile
    pr = gc.cmd({"cmd": "map_tile_click_pos", "x": tx, "y": ty, "z": tz})
    if pr.get("verified"):
        return pr["winX"], pr["winY"]
    return None


def open_rejoin_window(host, client, m, options):
    """test_messages' rejoin-hold staging (steps boot..7) on this file's PORT. Each step bounded; a
    miss is a setup failure (rej.miss: one CAPTURE line of every machine in `m`). Returns client2 (appended to `m`)."""
    rej.step("boot (test_rejoin_end_turn's parallel boot)", lambda: rej.boot(host, client, PORT, False), m)
    pre, notes = {"host": rej.snap(host), "client": rej.snap(client)}, []
    end_turn_cycle(host, client, notes)       # the host's side-phase counter is past 0 at the pause
    post = {"host": rej.snap(host), "client": rej.snap(client)}
    bad = [f"cycle notes {notes}"] if notes else []
    for w in ("host", "client"):
        a, b = pre[w], post[w]
        if a["turn"] is None or b["turn"] != a["turn"] + 1 or b["side"] != FACTION_PLAYER \
                or b[rej.PC] != rej.K_PARALLEL or b["desyncSeen"]:
            bad.append(f"{w} turn/side {a['turn']}/{a['side']} -> {b['turn']}/{b['side']} {rej.PC} {b[rej.PC]} "
                       f"desyncSeen {b['desyncSeen']} (want +1, player, K_PARALLEL = {rej.K_PARALLEL}, false)")
    rej.check("pre-leave END TURN cycle", bad, m)
    mover = select_mover(host)
    rej.check("a host soldier with a one-step neighbour (select_mover)", [] if mover else [
        "no live host-seat soldier reaches any of its 8 neighbours in one step"], m)
    sel = battle_state(host).get("selectedId")
    rej.check("the host's selection is the mover", [] if sel == mover[1] else [
        f"selectedId {sel} after select_mover {mover}"], m)
    print(f"fixture: mover {mover} (old selection, actor, first one-step neighbour)"
          + ("" if mover[0] == mover[1] else " - swapped: the old selection had no one-step neighbour"))
    rej.step("1 drop_client_mid_battle", lambda: drop_client_mid_battle(host, client), m)
    c2 = GameClient("rejoin", None, make_user_dir("freeze_rejoin", options=options))
    m.append(c2)
    rej.step("3 client2 spawn and connect", lambda: (c2.spawn(), c2.connect()), m)
    arm = hold(c2, on=True)
    rej.check("hold_battle_ready {on: true} on client2", [] if (
        arm["ok"] and arm["armed"] is True and not arm["held"]) else [f"arm {arm}"], m)
    rej.step("4 rejoin_skirmish", lambda: rejoin_skirmish(c2, PORT), m)

    def s5():
        c2.wait_for("client2 back in the battle", lambda: in_battle_save(c2) or None, timeout=240)
        c2.wait_for("client2 held on dialog 68 over BattlescapeState",
                    lambda: (has(c2, "BattlescapeState")
                             and dialog(c2).get("code") == COOP_DLG_CLIENT_RESUME_HOLD) or None,
                    timeout=60, interval=0.5)

    def s6():
        def offered():
            if session.has_state(host, "Profile"):        # the join's popup sits over the dialog
                return host.cmd({"cmd": "profile_ok"}) and None
            return dialog(host).get("backVisible") or None
        host.wait_for("host dialog offers RESUME", offered, timeout=120, interval=0.5)
        d = dialog(host)
        assert d.get("code") == COOP_DLG_WAIT_PLAYERS and d.get("backText") == "RESUME", f"host dialog {d}"

    def s7():
        host.ok({"cmd": "coop_dialog_back"})
        for gc in (host, c2):
            gc.wait_for(f"{gc.name} top BattlescapeState",
                        lambda gc=gc: (top_state(gc) == "BattlescapeState") or None, timeout=120, interval=0.5)
    rej.step("5 client2 in the battle, held on dialog 68", s5, m)
    rej.step("6 host offers RESUME", s6, m)
    rej.step("7 RESUME, both tops BattlescapeState", s7, m)
    return c2


# ------------------------------------------------------------------- main ---
def main():
    # Hermetic camera: each instance boots with a dummy SDL mouse parked at
    # (0,0) - the top-left corner - which under battleEdgeScroll=SCROLL_AUTO arms a
    # continuous edge-scroll the moment the battlescape is interactive again (e.g.
    # returning from the Pause hatch). That scroll shifts the camera _mapOffset
    # BETWEEN map_tile_click_pos verifying the target world tile and the injected
    # click being consumed, so the click resolves one tile off and the move is
    # silently rejected. This test exercises input-freeze / Options hatch /
    # movement, NOT automatic edge scrolling, so pin a hermetic camera
    # (battleEdgeScroll=0 / SCROLL_NONE) on every instance (client2 included).
    options = {"battleEdgeScroll": 0}
    host = GameClient("host", HOST_PORT, make_user_dir("freeze_host", options=options))
    client = GameClient("client", CLIENT_PORT, make_user_dir("freeze_client", options=options))
    m = [host, client]
    try:
        c2 = open_rejoin_window(host, client, m, options)

        # === handshake_open: the handshake is open and the peer has completed nothing
        # The host's rejoin battle_offer reopened phase Handshake; client2's
        # battle_ready is stashed by hold_battle_ready, so nothing completes the
        # handshake until this file releases it.
        try:
            c2.wait_for("client2's battle_ready stashed", lambda: hold(c2).get("held") or None,
                        timeout=HELD_S, interval=0.1)
        except Exception as e:
            print(f"NOTE: client2 stash wait: {e}")
        bs0 = battle_state(host)
        h0 = hold(c2)
        print(f"EVIDENCE handshake_open: host phase {bs0.get('phase')!r} top {top_state(host)!r}; client2 hold {h0} "
              f"phase {battle_state(c2).get('phase')!r} top {top_state(c2)!r}")
        assert bs0.get("phase") == "Handshake", (
            f"host phase should be Handshake after RESUME (the rejoin battle_offer reopened it and client2's "
            f"battle_ready is held): {bs0}")
        assert h0.get("armed") is True and h0.get("held") is True, (
            f"client2's battle_ready should be stashed by hold_battle_ready (armed, held), never sent: {h0}")
        print("PASS: the rejoin handshake is open (phase=Handshake) with client2's battle_ready held - "
              "nothing completes it until this file releases the hold")

        # === host_on_battlescape: the host is on BattlescapeState, phase STILL Handshake
        # Game::run() dispatches input only to the TOP state, so
        # the freeze is observable only with BattlescapeState on top. RESUME pops
        # the reconnect dialog straight onto it - no NextTurnState is pushed.
        st1 = states(host)
        assert top_state(host) == "BattlescapeState" and not any("NextTurnState" in s for s in st1), (
            f"host top state should be BattlescapeState with no NextTurnState above it after RESUME, stack={st1}")
        bs1 = battle_state(host)
        assert bs1.get("phase") == "Handshake", (
            f"host phase should STILL be Handshake on BattlescapeState (client2's battle_ready is held): {bs1}")
        print("PASS: host on BattlescapeState (no NextTurnState), phase STILL Handshake - the "
              "freeze window is open and observable")

        # === the ordering seat's unit, for the before/after position+TU check ===
        actor = selected_unit(bs1)
        assert actor is not None, f"host has no selected unit: {bs1}"
        actor_id = actor["id"]
        before = (actor["x"], actor["y"], actor["z"], actor["tu"])
        es_before = event_state(host)

        # The move-click TILE is chosen ONCE (a verified neighbour of the actor);
        # its camera-relative window PIXEL is RE-RESOLVED (resolve_click_pixel)
        # before each later click, because the camera/view level move across
        # Handshake -> PauseState -> Active. Reusing the TILE (not the pixel) is
        # what keeps the last assertion a real, same-target move, not just an
        # absence of refusal - repro_atom_turn.py's `tile_click` precedent.
        click = find_move_click(host, actor)
        assert click is not None, (
            f"FIXTURE: none of the actor's 8 neighbour tiles verified through "
            f"map_tile_click_pos - cannot resolve a real move-click for this "
            f"boot's map/camera state (actor at {(actor['x'], actor['y'], actor['z'])})")
        click_x, click_y, click_tile = click
        print(f"fixture: actor {actor_id} at {before}; move-click resolved to window ({click_x},{click_y}) -> "
              f"tile {click_tile}")

        # === FROZEN: a ground click changes NOTHING ==========================
        # find_move_click's HOME key is itself a frozen map input, so the
        # refusal count is read again right before the click: the click's own
        # refusal is proven by growth across it, besides the count being > 0.
        r_pre_click = event_state(host)["coopHostInputFrozenRefusals"]
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
        # `lastSeqEmitted` is NOT click-specific and must not be used as the
        # freeze proof (reveal-flush race RCA: fog-reveal evs flush at a
        # nondeterministic tick). Assert CLICK-SPECIFICALLY instead: a frozen
        # click never reaches the walk arm at all (repro_atom_walk.py /
        # test_input_gating.py's own `coopWalkArmEntered`-unchanged
        # precedent), so the arm-entry counter must not move and no order may
        # have left this machine.
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
        assert es_after["coopHostInputFrozenRefusals"] > r_pre_click, (
            f"coopHostInputFrozenRefusals did not grow across the ground click "
            f"({r_pre_click} -> {es_after['coopHostInputFrozenRefusals']}) - the click itself was not refused")
        r_after_click = es_after["coopHostInputFrozenRefusals"]
        print(f"PASS: frozen ground click moved nothing (pos/tu unchanged: {before}), "
              f"coopWalkArmEntered unchanged ({es_after['coopWalkArmEntered']}), "
              f"coopWalkIntentsSent=0, "
              f"coopHostInputFrozenRefusals={r_after_click} (> 0, {r_pre_click} before the click)")

        # === the deployed banner text, EXACT (never just non-empty) ===
        assert bs2.get("coopWaitText") == TEXT_WAITING_FOR_JOIN, (
            f"battle_state.coopWaitText should be the deployed STR_COOP_WAITING_FOR_JOIN "
            f"text exactly: {bs2.get('coopWaitText')!r}")
        print(f"PASS: battle_state.coopWaitText == {bs2['coopWaitText']!r} (exact)")

        # === THE ESCAPE HATCH ==================================
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
        print(f"PASS: the Options-key hatch opened PauseState from a "
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

        # The window survives the PauseState round trip (client2's battle_ready
        # is still held): prove the freeze is STILL ARMED ("one more
        # ground click still moves nothing and the counter rises again" - the
        # non-vacuity control for THIS half: a freeze that silently lifted during
        # PauseState would also have let this click through).
        bs3 = battle_state(host)
        assert bs3.get("phase") == "Handshake", (
            f"host phase should still be Handshake after the PauseState round trip (client2's battle_ready is "
            f"held: {hold(c2)}): {bs3}")
        actor3 = selected_unit(bs3)
        before2 = (actor3["x"], actor3["y"], actor3["z"], actor3["tu"])
        r2 = event_state(host)["coopHostInputFrozenRefusals"]
        # Re-resolve the SAME tile's pixel: the PauseState open/close round
        # trip can move the camera, so the Handshake pixel may no longer
        # address click_tile. Same tile, fresh projection.
        recheck = resolve_click_pixel(host, click_tile)
        assert recheck is not None, (
            f"FIXTURE: move-click tile {click_tile} no longer verifies through "
            f"map_tile_click_pos after the PauseState round trip - cannot "
            f"re-resolve the frozen re-check click for this boot's camera state")
        recheck_x, recheck_y = recheck
        host.ok({"cmd": "inject_input", "kind": "click", "x": recheck_x, "y": recheck_y})
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
              f"(phase Handshake, pos/tu unchanged, coopHostInputFrozenRefusals {r2} -> {r3})")

        # === release client2's battle_ready, and prove the freeze LIFTS =======
        rel = hold(c2, on=False)
        assert rel.get("ok") and rel.get("sent") is True, (
            f"hold_battle_ready {{on: false}} should send client2's stashed battle_ready: {rel}")
        host.wait_for("host phase reaches Active",
                      lambda: (battle_state(host).get("phase") == "Active") or None,
                      timeout=ACTIVE_S)
        c2.wait_for("client2 phase reaches Active",
                    lambda: (battle_state(c2).get("phase") == "Active") or None,
                    timeout=ACTIVE_S)
        print("PASS: both machines reached phase Active - the handshake completed")

        r4 = event_state(host)["coopHostInputFrozenRefusals"]
        bs5 = battle_state(host)
        actor5 = selected_unit(bs5)
        # SAME actor: click_tile is the ORIGINAL actor's neighbour, so a changed
        # selection here would not be the same action. Enforce identity, then
        # track that unit BY ID (not "whatever is selected") for the move proof,
        # so a selection change can never be miscredited as movement.
        assert actor5 is not None and actor5["id"] == actor_id, (
            f"selected unit changed between the frozen check and the Active control "
            f"(was id {actor_id}, now {None if actor5 is None else actor5['id']})")
        before3 = (actor5["x"], actor5["y"], actor5["z"], actor5["tu"])

        # Re-resolve the SAME tile's pixel under the now-Active camera instead of
        # reusing the Handshake pixel: same tile, same actor, but the camera/view
        # level can move (empirically measured), so a fixed pixel would address a
        # different tile. map_tile_click_pos re-centres on click_tile and
        # re-projects it through the production selector path.
        active_click = resolve_click_pixel(host, click_tile)
        assert active_click is not None, (
            f"FIXTURE: the move-click tile {click_tile} no longer verifies through "
            f"map_tile_click_pos once phase is Active - cannot re-resolve a real "
            f"move-click for this boot's camera state (selected actor at "
            f"{(actor5['x'], actor5['y'], actor5['z'])})")
        active_x, active_y = active_click
        print(f"fixture: re-resolved move-click tile {click_tile} under the Active "
              f"camera to window ({active_x},{active_y}) "
              f"(was ({click_x},{click_y}) at Handshake)")

        host.ok({"cmd": "inject_input", "kind": "click", "x": active_x, "y": active_y})

        def _moved():
            u = unit_by_id(battle_state(host), actor_id)
            return u is not None and (u["x"], u["y"], u["z"], u["tu"]) != before3
        try:
            host.wait_for("the unfrozen ground click to move the actor", lambda: _moved() or None,
                          timeout=15)
        except TimeoutError:
            # Do NOT swallow: capture WHY the re-resolved click did not move the
            # unit (freeze failed to lift vs. a fixture no-move tile) and RE-RAISE
            # the same failure. Diagnostics only - no retry, no extended timeout,
            # no catch-to-pass. Arm entry is reported, NEVER asserted as a pass.
            diag_bs = battle_state(host)
            diag_tracked = unit_by_id(diag_bs, actor_id)
            diag_sel = selected_unit(diag_bs)
            diag_es = event_state(host)
            diag_pos = (None if diag_tracked is None
                        else (diag_tracked["x"], diag_tracked["y"], diag_tracked["z"], diag_tracked["tu"]))
            print("DIAG (Active non-vacuity control timed out):")
            print(f"  tracked actor id {actor_id}: {diag_pos} (before click: {before3})")
            print(f"  currently selected id: {None if diag_sel is None else diag_sel['id']}")
            print(f"  intended move-click tile: {click_tile}")
            print(f"  Handshake pixel: ({click_x},{click_y})  "
                  f"Active re-resolved pixel: ({active_x},{active_y})")
            print(f"  event_state: coopWalkArmEntered={diag_es.get('coopWalkArmEntered')} "
                  f"coopWalkIntentsSent={diag_es.get('coopWalkIntentsSent')} "
                  f"coopHostInputFrozenRefusals={diag_es.get('coopHostInputFrozenRefusals')} "
                  f"(refusals were {r4} before the click)")
            print(f"  lastWalk: {diag_es.get('lastWalk')}")
            print(f"  battle phase: {diag_bs.get('phase')!r}  top state: {top_state(host)!r}")
            raise

        bs6 = battle_state(host)
        actor6 = unit_by_id(bs6, actor_id)
        assert actor6 is not None, f"tracked actor id {actor_id} vanished from battle_state: {bs6}"
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
        print(f"PASS (non-vacuity control): once Active, the SAME ground-click "
              f"tile {click_tile} (re-resolved to window ({active_x},{active_y})) "
              f"no longer refuses (coopHostInputFrozenRefusals stayed at {r5}) AND "
              f"actually moves the unit: before={before3} after={after3}")

        print("ALL HOST-INPUT-FREEZE CHECKS PASSED")
    finally:
        for gc in m:
            try:
                gc.shutdown()
            except Exception as e:
                print(f"shutdown {gc.name}: {e}")


if __name__ == "__main__":
    main()
