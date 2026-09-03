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

WHAT THIS ASSERTS (the packet's acceptance list, in order).
  (a) NO InventoryState on the HOST's stack after close_briefing - that IS the
      freeze - and none on the client's either (its entry briefing is infoOnly,
      so btnOkClick returns at BriefingState.cpp:302 and never reaches the
      push). Backed by the freeze's own log line, so "no InventoryState" cannot
      pass for the wrong reason.
  (b) The EXACT refusal text on BOTH machines via battle_state.coopWaitText -
      STR_COOP_EQUIP_FROZEN through the _txtCoopWait presenter (SS2.6), never
      vanilla _warning. Exact text, never non-emptiness: a raw STR_ key here
      means the WV-D17 language deploy is stale.
  (c) The host lands in BattlescapeState with the battle PLAYABLE - phase
      Active, not busy, a unit selected, and TAB actually advances the
      selection (i.e. BattlescapeState's _gameTimer ticks again once vanilla's
      "Turn 1 begins" overlay is gone; that is the only overlay left in a coop
      battle now).
  (d) `hash_now full` all buckets EQUAL on both machines. THIS assertion is the
      host-equip gap regression: it is what an unfrozen host equip would break.
      No hard-coded bucket count (SS1 WAVE-1 ADDITIONS: the sweep grows to nine
      at W1-P8).
  (e) `battle_state.turn == 1` on the HOST *immediately after close_briefing*,
      with the `saveBlob` bucket EQUAL on both machines AT THAT MOMENT. This is
      the assertion that catches a freeze implemented without the
      startFirstTurn() replacement; (d) alone does NOT - two machines can be
      equal-and-wrong if both skip the turn bump, and this fixture's client
      does not (its mirror already forced 1 at the end of its handshake, which
      the same step re-asserts).

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
        client.wait_for("client battlescape",
                        lambda: session.has_state(client, "BattlescapeState"), timeout=60)
        time.sleep(3)  # let both logs flush the handshake lines

        pre = states(host)
        assert "InventoryState" not in pre, \
            f"host already had an InventoryState BEFORE close_briefing: {pre}"
        print(f"host stack at the briefing: {pre}")
        print(f"client stack at entry:      {states(client)}")

        # ===== the real pre-battle path: BriefingState::btnOkClick ===========
        # close_briefing calls the REAL handler (TestServer.cpp), not a
        # synthetic shortcut - which is the whole point: the freeze lives
        # inside it.
        host.ok({"cmd": "close_briefing"})
        host.wait_for("host battlescape",
                      lambda: session.has_state(host, "BattlescapeState"), timeout=30)

        # === (a) NO InventoryState - that IS the freeze ======================
        post = states(host)
        assert "InventoryState" not in post, (
            "the pre-battle equip screen was still pushed on the HOST - the W1-P4 coop "
            f"freeze at BriefingState::btnOkClick did not fire. stack={post}")
        assert "BattlescapeState" in post, \
            f"host never reached BattlescapeState after close_briefing: {post}"
        assert "BriefingState" not in post, \
            f"the host's briefing was not popped by btnOkClick: {post}"
        assert post[-1] == "NextTurnState", (
            "with equip frozen, vanilla's own 'Turn 1 begins' overlay should be the only "
            f"thing left over the map on the host. stack={post}")

        # NON-VACUITY: prove the gate actually FIRED, rather than the screen
        # being absent for some unrelated reason.
        froze = grep(host_dir, "W1-P4: pre-battle equip FROZEN")
        assert froze, (
            "host log has no '[coop-handshake] W1-P4: pre-battle equip FROZEN' line - "
            "InventoryState is missing for some OTHER reason, so this test would be "
            "vacuous")
        print("HOST LOG:", froze[-1])

        cstack = states(client)
        assert "InventoryState" not in cstack, (
            "the client got a pre-battle equip screen - it must be frozen on BOTH "
            f"machines. stack={cstack}")
        print(f"PASS (a) freeze: host stack={post} (no InventoryState), "
              f"client stack={cstack} (no InventoryState)")

        # === (e) turn == 1 on the HOST *right now*, saveBlob EQUAL ===========
        # IMMEDIATELY after close_briefing, before any overlay dismissal: this
        # is where a freeze that skipped startFirstTurn() would read 0.
        hb = battle_state(host)
        cb = battle_state(client)
        assert hb.get("turn") == 1, (
            f"host battle_state.turn == {hb.get('turn')} right after close_briefing, "
            "expected 1 - the equip freeze skipped the InventoryState push WITHOUT "
            "replacing its SavedBattleGame::startFirstTurn() call (WV-D43). The host is "
            "now at turn 0 against a client whose RW-FIX-TURN mirror forced 1, which is "
            "a permanent saveBlob divergence.")
        assert cb.get("turn") == 1, (
            f"client battle_state.turn == {cb.get('turn')}, expected 1 - the RW-FIX-TURN "
            "mirror did not fire, so this step could not have caught a missing host "
            "startFirstTurn() either")
        hsb, csb = session.assert_hash_clean(
            host, client, buckets=["saveBlob"],
            what="immediately after close_briefing (WV-D43 turn parity)")
        print(f"PASS (e) WV-D43: host turn == 1 immediately after close_briefing "
              f"(client 1 too) and saveBlob EQUAL at that moment: {hsb['saveBlob']}")

        # === (b) the exact refusal text on BOTH machines =====================
        assert hb.get("coopWaitText") == STR_EQUIP_FROZEN_TEXT, (
            f"host coopWaitText is {hb.get('coopWaitText')!r}, expected "
            f"{STR_EQUIP_FROZEN_TEXT!r} - either CoopBattleUi::showEquipFrozen() did not "
            "fire, or the string did not resolve (a raw STR_ key here means the deployed "
            "bin/x64/Release/common/Language copy is stale relative to bin/common/, "
            "WV-D17)")
        assert cb.get("coopWaitText") == STR_EQUIP_FROZEN_TEXT, (
            f"client coopWaitText is {cb.get('coopWaitText')!r}, expected "
            f"{STR_EQUIP_FROZEN_TEXT!r} - the freeze must be VISIBLE on both machines, "
            "and the client never sees the skip site at all (its entry briefing is "
            "infoOnly), so its notice is raised by the battle entry itself")
        print(f"PASS (b) refusal: both machines show {STR_EQUIP_FROZEN_TEXT!r} on the "
              "_txtCoopWait presenter (SS2.6), never vanilla _warning")

        # === (c) the host lands on a PLAYABLE battle =========================
        session.dismiss_battle_start_overlays(host)
        session.dismiss_client_briefing(client)
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
            what="after the frozen pre-battle equip (HOST-EQUIP GAP regression)")
        assert "saveBlob" in hh, f"the full sweep did not include saveBlob: {sorted(hh)}"
        print(f"PASS (d) host-equip gap: ALL {len(hh)} hash buckets EQUAL on both "
              f"machines after the refused equip ({sorted(hh)})")

        assert not battle_state(client)["authority"]["desyncFrozen"], \
            "client desync-frozen at the end of the run"
        assert not battle_state(host)["authority"]["desyncFrozen"], \
            "host desync-frozen at the end of the run"

        print("ALL W1-P4 EQUIP-FREEZE TESTS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
