"""W1-P4 (WAVE1-RUNBOOK.md SS4 / ruling D3 = WV-D9 + WV-D34; MECHANISM PINNED
by WV-D43): the PRE-BATTLE EQUIP SCREEN IS FROZEN in a coop battle, on BOTH
machines, and the freeze REPLACES the SavedBattleGame::startFirstTurn() call it
would otherwise have skipped.

WHAT WAS BROKEN (the HOST-EQUIP GAP the design session found).
CoopHandshake::offerBattle() snapshots the blob the client loads at battle
GENERATION time (connectionTCP.cpp:3544) and the caller pushes BriefingState
only afterwards. So the host's pre-battle equip screen runs strictly AFTER the
client's copy was taken: anything the host moved on it - a rifle from the
ground into a soldier's hands - diverged the items/saveBlob buckets silently and
permanently. The harness never caught it because no test ever equipped. Wave 1
closes the gap by FREEZING equip on both machines rather than by re-staging the
snapshot (that alternative is explicitly rejected for this wave); un-freezing
belongs to the synchronized-equip initiative's `inventory_move`, later.

THE MECHANISM IS PINNED, AND SO IS THE REASON.
BriefingState::btnOkClick gets ONE coop-gated branch that skips
`pushState(new InventoryState(false, bs, 0))` AND THEN CALLS
`startFirstTurn()`, byte-for-byte the way the isPreview branch three lines above
it already does. That second half is not decoration: that push is the host's
ONLY non-preview route into startFirstTurn() (`git grep startFirstTurn` finds
exactly two callers - the preview branch, and InventoryState::btnOkClick at
InventoryState.cpp:1174). A freeze without it leaves the host at `_turn == 0`
while the thin client's RW-FIX-TURN mirror forces 1 - the exact saveBlob
divergence class that fix was built to close - and also skips
randomizeItemLocations() / resetUnitTiles() / the per-unit prepareNewTurn(false)
/ newTurnUpdateScripts() (SavedBattleGame.cpp:1230-1260).

W2-P8b S-H RE-POINT (chain rule A.10; docs rewrite/prompts/w2p8b_prebattle_equip.md,
AMENDMENT P8b-1 section 4 S-H): the freeze is GONE for a fresh co-op battle. The
offer goes out at PREPARE at turn 0 (owner D210 b), each player equips its own
soldiers on the vanilla pre-battle screen (D174 a), OK is a ready toggle and
turn 1 starts on the host when every seat is ready (D206 c). The W1-P4 freeze
survives only for the next-stage briefing (D158), which this file does not
reach. This file is now the "no freeze" check, with each assertion re-pointed
to the value this build measures:

WHAT THIS ASSERTS (in order).
  (a) BOTH pre-battle equip screens are OPEN: the host's InventoryState on top
      right after close_briefing with vanilla's NextTurnState under it, the
      client's on top once its own briefing closes, `inventory_view.preBattle`
      true on both; the host log carries the equip entry's line and NOT the
      W1-P4 freeze line (so "an InventoryState is up" cannot pass for the wrong
      reason).
  (e) `battle_state.turn == 0` on BOTH machines while the equip screens are
      up, with `saveBlob` EQUAL at that moment; (e2) the host readying alone
      leaves turn 0 on both and both screens up, and turn is 1 on both once
      both seats are ready.
  (b) NO freeze text on either banner: `battle_state.coopWaitText` is the
      exact measured entry value on both machines, not STR_COOP_EQUIP_FROZEN.
  (c) The host lands in BattlescapeState with the battle PLAYABLE - phase
      Active, not busy, a unit selected, and TAB actually advances the
      selection.
  (d) `hash_now full` all buckets EQUAL on both machines after both equip
      screens and turn 1 (the host-equip gap regression).

WHAT THIS DELIBERATELY DOES NOT USE.
  * `inventory_move` - a dead R1-P4 stub that answers "rewrite-pending", so any
    "it changed nothing" assertion through it would be true by construction.
  * `battle_open_inventory` - that drives bstate->btnInventoryClick, the
    MID-BATTLE inventory. Gating that one is W1-P5's packet, not this one.
The pre-battle screen is the one pushed from BriefingState::btnOkClick, and the
only honest way to reach it is the real thing: host `close_briefing`, which
calls the real BriefingState::btnOkClick.

COVERAGE LIMIT, stated honestly. That SP still gets its equip screen (the gate
self-guards off outside coop) is proven by the mandatory SP battle smoke, which
runs one instance with no coop at all and requires the stack
['BattlescapeState','NextTurnState','InventoryState'] - it cannot be asserted
from inside a coop fixture, because there is no SP battle here to compare with.

Run:  python tools/coop_test/test_rw_equip_freeze.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session

SDLK_TAB = 9  # Options::keyBattleNextUnit default (test_rw_input_gating.py precedent)

# bin/common/Language/en-US.yml, verbatim. EXACT TEXT, never non-emptiness
# (SS1 WAVE-1 ADDITIONS / the stale-language-deploy trap, WV-D17).
STR_EQUIP_FROZEN_TEXT = "Pre-battle equipment is locked in co-op"


# ---------------------------------------------------------------- helpers ---
def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def battle_state(gc):
    bs = gc.cmd({"cmd": "battle_state"})
    assert bs.get("ok"), f"battle_state failed: {bs}"
    return bs


def grep(user_dir, needle):
    log = os.path.join(user_dir, "openxcom.log")
    if not os.path.exists(log):
        return []
    with open(log, encoding="utf-8", errors="replace") as f:
        return [l.rstrip("\n") for l in f if needle in l]


# ------------------------------------------------------------ lobby drive ---
# Same inline copies test_rw_handshake.py / test_rw_client_briefing.py carry
# (the stated precedent, WV-D18).
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


# ------------------------------------------------------------------- main ---
def main():
    port = "47988"
    host_dir = make_user_dir("rw_equip_freeze_host")
    client_dir = make_user_dir("rw_equip_freeze_client")
    host = GameClient("host", 48798, host_dir)
    client = GameClient("client", 48799, client_dir)
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        skirmish_host(host, port)
        skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port,
                   "player": "ClientPlayer"})

        host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
        client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
        host.ok({"cmd": "profile_ok"})
        client.ok({"cmd": "profile_ok"})
        host.wait_for("start offered", lambda: lobby(host).get("buttonVisible") or None)

        host.ok({"cmd": "lobby_action"})
        host.wait_for("host at battle settings",
                      lambda: (not session.has_state(host, "LobbyMenu")) or None)
        assert top_state(host) == "NewBattleState", \
            f"host should land on the NEW BATTLE setup screen, stack={states(host)}"

        # W1-P6 (WV-D12): stamp ONE soldier to seat 1 before generation
        # (R3-P1's newbattle_seat_soldier lever, WV-D18's standard fixture
        # shape). Two reasons, both real:
        #   1. REPRESENTATIVENESS - without it the joining client owns ZERO
        #      battle units, which is not what a 2-player battle looks like.
        #   2. W1-P6's battle-entry auto-select raises the SPECTATOR notice
        #      (STR_COOP_SPECTATOR_MODE) on a machine that commands nothing,
        #      and that notice would land on the same _txtCoopWait strip this
        #      test reads for STR_COOP_EQUIP_FROZEN in (b). With a seat-1
        #      soldier the client is not a spectator, so both notices keep
        #      their own machine and (b)'s assertion stays byte-identical.
        host.ok({"cmd": "newbattle_seat_soldier", "seat": 1})

        host.ok({"cmd": "newbattle_ok"})
        host.wait_for("host briefing",
                      lambda: session.has_state(host, "BriefingState"), timeout=30)

        pre = states(host)
        assert "InventoryState" not in pre, \
            f"host already had an InventoryState BEFORE close_briefing: {pre}"
        print(f"host stack at the briefing: {pre}")

        # ===== the real pre-battle path: BriefingState::btnOkClick ===========
        # close_briefing calls the REAL handler (TestServer.cpp), not a
        # synthetic shortcut - which is the whole point: the equip entry lives
        # inside it.
        #
        # W2-P8b S-H (owner D210 b): the coop blob snapshot and the battle_offer
        # now go out at PREPARE (newbattle_ok), at turn 0, so the client's own
        # entry briefing is up BEFORE the host closes its briefing.
        client.wait_for("client entry briefing (both briefings at once, D210 b)",
                        lambda: session.has_state(client, "BriefingState") or None, timeout=90)
        host.ok({"cmd": "close_briefing"})
        host.wait_for("host pre-battle equip screen on top",
                      lambda: (top_state(host) == "InventoryState") or None, timeout=30)
        # the client closes its read-only briefing; its equip entry (a pump step)
        # then pushes its Turn-1 screen and its own pre-battle equip screen
        session.dismiss_client_briefing(client)
        client.wait_for("client pre-battle equip screen on top",
                        lambda: (top_state(client) == "InventoryState") or None, timeout=30)
        time.sleep(3)  # let both logs flush the handshake lines
        print(f"client stack at entry:      {states(client)}")

        # === (a) BOTH equip screens OPEN - the freeze is gone (W2-P8b) =======
        post = states(host)
        assert post[-1] == "InventoryState", (
            "the host's pre-battle equip screen is not on top after close_briefing - "
            f"W2-P8b's host equip entry (D174 a) did not run. stack={post}")
        assert "BattlescapeState" in post, \
            f"host never reached BattlescapeState after close_briefing: {post}"
        assert "BriefingState" not in post, \
            f"the host's briefing was not popped by btnOkClick: {post}"
        assert post[-2] == "NextTurnState", (
            "vanilla's own 'Turn 1 begins' overlay should sit right under the host's "
            f"pre-battle equip screen (BriefingState::btnOkClick's push order). stack={post}")

        # NON-VACUITY: the freeze did NOT fire, and the equip phase opened.
        froze = grep(host_dir, "W1-P4: pre-battle equip FROZEN")
        assert not froze, (
            "host log has a '[coop-handshake] W1-P4: pre-battle equip FROZEN' line - the "
            f"fresh co-op battle took the freeze branch: {froze[-1]}")
        opened = grep(host_dir, "[coop-equip] host: pre-battle equip OPEN")
        assert opened, (
            "host log has no '[coop-equip] host: pre-battle equip OPEN' line - the "
            "InventoryState on top was not pushed by W2-P8b's equip entry")
        print("HOST LOG:", opened[-1])

        cstack = states(client)
        assert cstack[-1] == "InventoryState", (
            "the client has no pre-battle equip screen on top - W2-P8b's client equip "
            f"entry (D174 a) did not run. stack={cstack}")
        hv = host.cmd({"cmd": "inventory_view"})
        cv = client.cmd({"cmd": "inventory_view"})
        assert hv.get("preBattle") is True and cv.get("preBattle") is True, (
            f"inventory_view.preBattle host={hv.get('preBattle')} client={cv.get('preBattle')} "
            "(want True on both: each screen is the equip entry's own)")
        print(f"PASS (a) no freeze: host stack={post}, client stack={cstack} - both "
              "pre-battle equip screens open")

        # === (e) turn == 0 on BOTH while the equip screens are up, saveBlob EQUAL
        # The offer is snapshotted at turn 0 and turn 1 starts only at the ready
        # barrier (D206 c), so nothing may have run startFirstTurn() yet.
        hb = battle_state(host)
        cb = battle_state(client)
        assert hb.get("turn") == 0, (
            f"host battle_state.turn == {hb.get('turn')} with both pre-battle equip screens "
            "up, expected 0 - turn 1 started before every seat was ready")
        assert cb.get("turn") == 0, (
            f"client battle_state.turn == {cb.get('turn')} with both pre-battle equip screens "
            "up, expected 0 (the turn-0 offer; the RW-FIX-TURN mirror is skipped)")
        hsb, csb = session.assert_hash_clean(
            host, client, buckets=["saveBlob"],
            what="with both pre-battle equip screens up (turn 0)")
        print(f"PASS (e) turn == 0 on both machines with both equip screens up and "
              f"saveBlob EQUAL at that moment: {hsb['saveBlob']}")

        # === (b) no freeze text on either banner =============================
        # W2-P8b S-H re-point (chain rule A.10): was STR_EQUIP_FROZEN_TEXT on both;
        # measured "" on both machines (2/2 runs at f225f1fc5).
        assert hb.get("coopWaitText") == "", (
            f"host coopWaitText is {hb.get('coopWaitText')!r} with its pre-battle equip screen up, "
            f"expected '' (no {STR_EQUIP_FROZEN_TEXT!r} notice - the freeze is gone, W2-P8b)")
        assert cb.get("coopWaitText") == "", (
            f"client coopWaitText is {cb.get('coopWaitText')!r} with its pre-battle equip screen up, "
            f"expected '' (the client's entry freeze notice was deleted, W2-P8b b2)")
        print(f"PASS (b) no freeze text: coopWaitText '' on both machines (never "
              f"{STR_EQUIP_FROZEN_TEXT!r})")

        # === (e2) turn stays 0 until BOTH are ready ==========================
        # The host readies alone (the idempotent lever, Q11 a); once the client
        # has applied the host's ready flag, turn is still 0 on both and both
        # screens are still up. Then equip_both_ready() readies the client.
        r = host.ok({"cmd": "battle_inventory", "action": "ok"})
        assert r.get("preBattle") is True and not r.get("noop"), \
            f"host ready press did not toggle ready on its pre-battle screen: {r}"
        client.wait_for("the host's ready flag applied on the client",
                        lambda: ((session.event_state(client).get("equip") or {}).get("ready") or [False])[0] is True
                        or None, timeout=10)
        hb1, cb1 = battle_state(host), battle_state(client)
        assert hb1.get("turn") == 0 and cb1.get("turn") == 0, (
            f"turn host/client = {hb1.get('turn')}/{cb1.get('turn')} with only the host ready, "
            "expected 0/0 - turn 1 must wait for every seat (D206 c)")
        assert top_state(host) == "InventoryState" and top_state(client) == "InventoryState", (
            f"a ready press closed an equip screen: host={states(host)} client={states(client)}")
        print("PASS (e2) host ready alone: turn 0 on both, both equip screens still up")
        session.equip_both_ready(host, client)
        hb2, cb2 = battle_state(host), battle_state(client)
        assert hb2.get("turn") == 1 and cb2.get("turn") == 1, (
            f"turn host/client = {hb2.get('turn')}/{cb2.get('turn')} after both seats are ready, "
            "expected 1/1")
        print("PASS (e2) both ready: turn 1 on both machines")

        # === (c) the host lands on a PLAYABLE battle =========================
        session.dismiss_battle_start_overlays(host)
        session.dismiss_battle_start_overlays(client)
        assert top_state(host) == "BattlescapeState", \
            f"host battle-start overlays never cleared: {states(host)}"
        time.sleep(1)

        hb2 = battle_state(host)
        assert hb2.get("inBattle"), f"host battle_state says no battle: {hb2}"
        assert hb2.get("phase") == "Active", f"host phase != Active: {hb2.get('phase')}"
        assert hb2.get("isBusy") is False, f"host is stuck busy after entry: {hb2}"
        sel0 = hb2.get("selectedId")
        assert sel0 not in (None, -1), f"host has no selected unit after entry: {hb2}"

        # PLAYABLE, not merely "on the right state": the whole reason the
        # overlays matter is that Game::run() only think()s _states.back(), so
        # BattlescapeState's _gameTimer (and the BState machine with it) is dead
        # while one is up. A TAB that actually moves the selection proves it
        # ticks.
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        host.wait_for("host selection advanced by TAB",
                      lambda: (battle_state(host).get("selectedId") != sel0) or None,
                      timeout=15)
        sel1 = battle_state(host).get("selectedId")
        print(f"PASS (c) playable: host on BattlescapeState, phase Active, not busy, "
              f"TAB moved the selection {sel0} -> {sel1}")

        # === (d) the host-equip gap regression: every bucket EQUAL ===========
        # No hard-coded count - the sweep grows to nine at W1-P8 (SS1 WAVE-1
        # ADDITIONS). "All buckets EQUAL" is the invariant.
        hh, ch = session.assert_hash_clean(
            host, client, full=True,
            what="after both pre-battle equip screens and turn 1 (HOST-EQUIP GAP regression)")
        assert "saveBlob" in hh, f"the full sweep did not include saveBlob: {sorted(hh)}"
        print(f"PASS (d) host-equip gap: ALL {len(hh)} hash buckets EQUAL on both "
              f"machines after both equip screens and turn 1 ({sorted(hh)})")

        assert not battle_state(client)["authority"]["desyncFrozen"], \
            "client desync-frozen at the end of the run"
        assert not battle_state(host)["authority"]["desyncFrozen"], \
            "host desync-frozen at the end of the run"

        print("ALL W2-P8b NO-FREEZE (FORMER W1-P4 EQUIP-FREEZE) TESTS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
