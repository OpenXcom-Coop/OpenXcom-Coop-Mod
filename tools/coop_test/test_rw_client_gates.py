"""W1-P5 (WAVE1-RUNBOOK.md SS4 / ruling D8 = WV-D14): CLIENT HARD GATES on the
battlescape controls that were still pure vanilla in the rewrite, plus the
deleted quick-load gate and the chat-open `allowButtons` guard.

WHAT WAS BROKEN (evidence F1/F2 of DESIGN-SESSION-2026-09-02-evidence.md).
On a co-op CLIENT, all of these ran locally with nothing on the wire:
  * ABORT MISSION      -> AbortMissionState, ungated on either machine; the
                          strict-majority VOTE legacy used is an r4 T3 stub.
  * mid-battle INVENTORY -> a full re-equip of any unit, writing `items`.
  * ZERO TU            -> BattleUnit::clearTimeUnits(), writing `unitsStats`.
  * hand REACTION toggles -> preferredHandForReactions /
                          reactionsDisabledFor{Left,Right}Hand, which are
                          serialized (BattleUnit.cpp:791-796) and are NOT on
                          saveBlobExcludedUnitKey's list, so they land in the
                          saveBlob bucket.
  * QUICK LOAD (F9)    -> LoadGameState pushed unconditionally; its own
                          chokepoint then refused SILENTLY (log-only).
Three of the five therefore diverged the two machines permanently, on one
keypress, with no message and no detector until the next hash.

WHAT THIS ASSERTS.
  PHASE 1 - every listed control, pressed on the CLIENT through its REAL
    handler: the exact refusal text on battle_state.coopWaitText, the absence
    of the effect (no dialog / no InventoryState / TU unchanged / reaction
    flags unchanged / no LoadGameState), and `hash_now full` ALL BUCKETS EQUAL
    after every single press. That last one is the MINT-PROOF.
  PHASE 2 - the same controls on the HOST still WORK (the gate is client-side,
    not a global disable), the ownership term refuses a host press against a
    CLIENT-owned unit with SS2.6's own not_your_unit string, and the chat-open
    guard suppresses a host press while the chat overlay has the keyboard.
    Everything in phase 2 is non-mutating, so the buckets stay EQUAL.
  PHASE 3 - THE NEGATIVE CONTROL, and it deliberately DIVERGES the two
    machines. Phase 1's "all buckets EQUAL after the press" would be VACUOUS
    if these controls could not move a bucket in the first place (WR-27: do
    not ship an assertion that is true by construction). So the last thing
    this test does is let the HOST press ZERO TU and the hand-reaction toggle
    for real, and asserts that `unitsStats` and `saveBlob` NOW DIFFER, naming
    the fields that moved. No equality assertion runs after that point, and
    nothing else happens in the battle, so nothing is left to freeze on it.

REACHABILITY, checked rather than assumed (WR-27 again). Every control here is
genuinely pressable on a co-op client: allowButtons() needs
`_save->getSide() == FACTION_PLAYER`, which is TRUE on BOTH machines in a
classic co-op battle during the player side, and btnInventoryClick /
btn*HandItemClick gate on playableUnitSelected(), which is the same condition.
None of these is dead framing the way an off-turn END TURN press is (SS2.W8's
REACHABILITY note). The one control NOT covered here is the pre-battle equip
screen - W1-P4 owns that, it is a skipped push rather than a refused press, and
there IS no pre-battle InventoryState in a co-op battle any more.

Run:  python tools/coop_test/test_rw_client_gates.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session

SDLK_TAB = 9        # Options::keyBattleNextUnit default (test_rw_equip_freeze precedent)
SDLK_ESCAPE = 27    # Options::keyCancel - AbortMissionState's own cancel binding
COOP_SEAT_1 = 1

# bin/common/Language/en-US.yml, VERBATIM. Exact text, never non-emptiness
# (SS1 WAVE-1 ADDITIONS / WV-D17: a raw STR_ key here means the deployed
# bin/x64/Release/common/Language copy is stale relative to bin/common/).
TXT_ABORT = "Only the host can abort the mission"
TXT_INVENTORY = "Only the host can open the inventory"
TXT_ZERO_TU = "Only the host can expend a soldier's time units"
TXT_REACTIONS = "Only the host can change reaction fire settings"
TXT_LOAD = "Saved games cannot be loaded during a co-op session"
TXT_NOT_YOUR_UNIT = "Not one of your soldiers"      # SS2.6, reused not duplicated
TXT_EQUIP_FROZEN = "Pre-battle equipment is locked in co-op"   # W1-P4's entry notice


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


def units_by_id(bs):
    return {u["id"]: u for u in bs.get("units", [])}


def banner(gc):
    return battle_state(gc).get("coopWaitText")


def grep(user_dir, needle):
    log = os.path.join(user_dir, "openxcom.log")
    if not os.path.exists(log):
        return []
    with open(log, encoding="utf-8", errors="replace") as f:
        return [l.rstrip("\n") for l in f if needle in l]


def select_owned(gc, own_ids, who, tries=12):
    """TAB until the machine's selection sits on a unit it OWNS.

    Needed because the INITIAL selection is minted at battle generation time,
    before any seat filter exists - W1-P1 observed both machines starting on
    unit 8, which in this fixture is the CLIENT's soldier. The selection cycle
    itself is already seat-filtered (R5-P2's coopMaySelectUnit), so TAB lands
    on an owned unit; `selectedUnit` is saveBlob-hash-excluded, so cycling is
    hash-free either way.
    """
    sel = battle_state(gc).get("selectedId")
    for _ in range(tries):
        if sel in own_ids:
            return sel
        gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.4)
        sel = battle_state(gc).get("selectedId")
    raise AssertionError(
        f"{who}: could not get an OWNED unit selected (own={sorted(own_ids)}, "
        f"selected={sel})")


# ------------------------------------------------------------ lobby drive ---
# Same inline copies test_rw_equip_freeze.py / test_rw_handshake.py carry
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


def bring_up(host, client, port):
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

    # WV-D18: stamp ONE soldier to seat 1 BEFORE generation, so the client
    # really owns a unit (repro_atom_turn.py's helper set, reused).
    seat = host.ok({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1})

    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing",
                  lambda: session.has_state(host, "BriefingState"), timeout=30)
    # WV-D56 (FX-1): snapshot/offer move to AFTER startFirstTurn() - i.e. to
    # this close_briefing. "client battlescape" can only be waited for AFTER it.
    host.ok({"cmd": "close_briefing"})
    host.wait_for("host battlescape",
                  lambda: session.has_state(host, "BattlescapeState"), timeout=30)
    session.dismiss_battle_start_overlays(host)
    client.wait_for("client battlescape",
                    lambda: session.has_state(client, "BattlescapeState"), timeout=60)
    session.dismiss_client_briefing(client)
    time.sleep(1)
    return seat


# ------------------------------------------------------------------- main ---
def main():
    port = "47992"
    host_dir = make_user_dir("rw_client_gates_host")
    client_dir = make_user_dir("rw_client_gates_client")
    host = GameClient("host", 48806, host_dir)
    client = GameClient("client", 48807, client_dir)
    try:
        seat = bring_up(host, client, port)

        assert top_state(host) == "BattlescapeState", \
            f"host is not on the map: {states(host)}"
        assert top_state(client) == "BattlescapeState", \
            f"client is not on the map: {states(client)}"

        hb = battle_state(host)
        cb = battle_state(client)
        assert hb.get("phase") == "Active" and cb.get("phase") == "Active", \
            f"phases: host={hb.get('phase')} client={cb.get('phase')}"

        hu = units_by_id(hb)
        host_own = {u["id"] for u in hu.values() if u["coop"] == 0 and u["isPlayerSoldier"]}
        client_own = {u["id"] for u in hu.values() if u["coop"] == 1 and u["isPlayerSoldier"]}

        # NON-VACUITY GATE, before anything is claimed about a client press.
        assert client_own, (
            f"fixture is VACUOUS: the client owns no units - the seat-1 stamp "
            f"(soldierId={seat.get('soldierId')}) did not reach the battle")
        assert host_own, "fixture is VACUOUS: the host owns no units"
        assert not (host_own & client_own), "a unit is claimed by both seats"
        print(f"fixture: host owns {sorted(host_own)}, client owns {sorted(client_own)}")

        # The client entered on W1-P4's equip notice; every press below has to
        # CHANGE the banner, which is what makes each text assertion mean
        # "this press produced this message".
        assert banner(client) == TXT_EQUIP_FROZEN, (
            f"client's entry banner is {banner(client)!r}, expected "
            f"{TXT_EQUIP_FROZEN!r} - if this is a raw STR_ key the WV-D17 language "
            "deploy is stale and every text assertion below is meaningless")

        session.assert_hash_clean(host, client, full=True, what="at the gate baseline")

        c_unit = select_owned(client, client_own, "client")
        print(f"client has its OWN unit {c_unit} selected")
        c_before = units_by_id(battle_state(client))[c_unit]

        # =====================================================================
        # PHASE 1 - the client hard gates
        # =====================================================================
        print("\n--- PHASE 1: client presses, every one refused -------------")

        def client_press_check(label, press, expect_text, effect_check):
            press()
            time.sleep(0.6)
            got = banner(client)
            assert got == expect_text, (
                f"{label}: client banner is {got!r}, expected {expect_text!r} - "
                "either the gate did not fire, or it fired with the wrong string "
                "(a raw STR_ key = stale WV-D17 deploy)")
            effect_check()
            session.assert_hash_clean(
                host, client, full=True,
                what=f"after the client's refused {label} (MINT-PROOF)")
            print(f"  PASS {label}: {got!r}, no effect, all buckets EQUAL")

        # (1) ABORT --------------------------------------------------------
        def abort_effect():
            assert "AbortMissionState" not in states(client), (
                "the client opened the abort dialog - AbortMissionState ends in "
                f"setAborted() + finishBattle(): {states(client)}")

        client_press_check(
            "abort",
            lambda: client.ok({"cmd": "battle_ui_press", "control": "abort"}),
            TXT_ABORT, abort_effect)

        # (2) MID-BATTLE INVENTORY ----------------------------------------
        # battle_open_inventory drives the REAL bstate->btnInventoryClick
        # (TestServer.cpp) - the mid-battle screen, which is W1-P5's gate.
        # `inventory_move` is deliberately NOT used anywhere here: it is a dead
        # "rewrite-pending" stub, so any assertion through it is vacuous.
        inv_resp = {}

        def open_inv():
            inv_resp.update(client.cmd({"cmd": "battle_open_inventory", "unit": c_unit}))

        def inv_effect():
            assert inv_resp.get("opened") is False, (
                f"the client OPENED the mid-battle inventory: {inv_resp}")
            assert "InventoryState" not in states(client), \
                f"client stack has an InventoryState: {states(client)}"

        client_press_check("inventory", open_inv, TXT_INVENTORY, inv_effect)

        # (3) ZERO TU ------------------------------------------------------
        def zero_tu_effect():
            now = units_by_id(battle_state(client))[c_unit]
            assert now["tu"] == c_before["tu"], (
                f"the client ZEROED its unit's TU locally: {c_before['tu']} -> "
                f"{now['tu']} (unitsStats mint)")
            assert now["tu"] > 0, (
                f"fixture problem: unit {c_unit} started at {now['tu']} TU, so "
                "'TU unchanged' cannot distinguish a refusal from a zeroing")

        client_press_check(
            "zero_tu",
            lambda: client.ok({"cmd": "battle_ui_press", "control": "zero_tu"}),
            TXT_ZERO_TU, zero_tu_effect)

        # (4) HAND REACTION TOGGLE ----------------------------------------
        def react_effect():
            now = units_by_id(battle_state(client))[c_unit]
            for f in ("reactOffLeft", "reactOffRight", "reactPrefLeft", "reactPrefRight"):
                assert now[f] == c_before[f], (
                    f"the client flipped {f} locally ({c_before[f]} -> {now[f]}) - "
                    "that field is serialized and NOT saveBlob-excluded")

        client_press_check(
            "hand_reaction",
            lambda: client.ok({"cmd": "battle_ui_press", "control": "hand_reaction",
                               "hand": "right"}),
            TXT_REACTIONS, react_effect)

        # (5) QUICK LOAD ---------------------------------------------------
        # Driven as a REAL SDL keypress through Game::run's event loop, because
        # the gate lives in BattlescapeState::handle's key chain, not in a
        # button handler. The key comes from the running game's own Options.
        key_quickload = cb.get("keyQuickLoad")
        assert isinstance(key_quickload, int) and key_quickload > 0, \
            f"battle_state did not report keyQuickLoad: {key_quickload!r}"

        def quickload_effect():
            st = states(client)
            assert "LoadGameState" not in st, \
                f"the client pushed a LoadGameState: {st}"
            assert battle_state(client).get("inBattle"), \
                "the client left the battle on a quick load"

        client_press_check(
            "quickload",
            lambda: client.ok({"cmd": "inject_input", "kind": "key",
                               "key": key_quickload}),
            TXT_LOAD, quickload_effect)

        assert not battle_state(client)["authority"]["desyncFrozen"], \
            "client desync-frozen after the refused presses"

        # =====================================================================
        # PHASE 2 - the HOST still works; ownership term; chat guard
        # =====================================================================
        print("\n--- PHASE 2: host-side presses still work ------------------")

        h_unit = select_owned(host, host_own, "host")
        print(f"  host has its OWN unit {h_unit} selected")

        # (6) host ABORT really opens the dialog --------------------------
        host.ok({"cmd": "battle_ui_press", "control": "abort"})
        time.sleep(0.6)
        assert "AbortMissionState" in states(host), (
            "the HOST could not open the abort dialog - W1-P5's gate must be "
            f"client-side, not a global disable. stack={states(host)}")
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_ESCAPE})
        host.wait_for("host abort dialog dismissed",
                      lambda: ("AbortMissionState" not in states(host)) or None,
                      timeout=15)
        print("  PASS host abort: dialog opened, cancelled without aborting")

        # (7) host INVENTORY opens on its OWN unit -------------------------
        r = host.cmd({"cmd": "battle_open_inventory", "unit": h_unit})
        assert r.get("opened") is True, (
            f"the HOST could not open the mid-battle inventory on its own unit "
            f"{h_unit}: {r}")
        host.ok({"cmd": "battle_close_inventory"})
        host.wait_for("host inventory closed",
                      lambda: ("InventoryState" not in states(host)) or None,
                      timeout=15)
        print("  PASS host inventory: opened on its own unit and closed")

        # (8) the OWNERSHIP term: host press against a CLIENT-owned unit ----
        r = host.cmd({"cmd": "battle_open_inventory", "unit": c_unit})
        assert r.get("opened") is False, (
            f"the host opened the inventory of the CLIENT's unit {c_unit}: {r}")
        assert banner(host) == TXT_NOT_YOUR_UNIT, (
            f"host banner is {banner(host)!r}, expected {TXT_NOT_YOUR_UNIT!r} - "
            "the ownership term must refuse with its OWN reason (SS2.6's "
            "not_your_unit row), not with the host-only string")
        print(f"  PASS ownership term: host refused on the client's unit "
              f"with {TXT_NOT_YOUR_UNIT!r}")

        # (9) the CHAT-OPEN allowButtons guard (legacy parity) -------------
        hb2 = battle_state(host)
        assert hb2.get("chatMenuExists"), (
            "no ChatMenu on the host - the chat guard cannot be exercised and "
            "this sub-test would be vacuous")
        key_chat = hb2.get("keyChat")
        assert isinstance(key_chat, int) and key_chat > 0, \
            f"battle_state did not report keyChat: {key_chat!r}"
        host.ok({"cmd": "inject_input", "kind": "key", "key": key_chat})
        host.wait_for("host chat opened",
                      lambda: battle_state(host).get("chatActive") or None, timeout=15)

        host.ok({"cmd": "battle_ui_press", "control": "abort"})
        time.sleep(0.6)
        assert "AbortMissionState" not in states(host), (
            "the host opened the abort dialog WHILE THE CHAT WAS OPEN - "
            f"allowButtons()'s chat guard did not fire. stack={states(host)}")
        print("  PASS chat guard: abort suppressed while the chat holds the keyboard")

        host.ok({"cmd": "inject_input", "kind": "key", "key": key_chat})
        host.wait_for("host chat closed",
                      lambda: (not battle_state(host).get("chatActive")) or None,
                      timeout=15)
        host.ok({"cmd": "battle_ui_press", "control": "abort"})
        time.sleep(0.6)
        assert "AbortMissionState" in states(host), (
            "with the chat closed again the host's abort must work - otherwise "
            "the previous assertion proved nothing about the chat. "
            f"stack={states(host)}")
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_ESCAPE})
        host.wait_for("host abort dialog dismissed",
                      lambda: ("AbortMissionState" not in states(host)) or None,
                      timeout=15)
        print("  PASS chat guard: same press works again once the chat is closed")

        # nothing in phase 2 mutated hashed state
        hh, ch = session.assert_hash_clean(
            host, client, full=True, what="after the whole host-side pass")
        print(f"  PASS: all {len(hh)} buckets still EQUAL after phase 2 "
              f"({sorted(hh)})")
        assert not battle_state(client)["authority"]["desyncFrozen"], \
            "client desync-frozen at the end of phase 2"

        # =====================================================================
        # PHASE 3 - NEGATIVE CONTROL. This DELIBERATELY diverges the machines.
        # =====================================================================
        print("\n--- PHASE 3: negative control (deliberate divergence) ------")
        print("    Everything above proved 'the buckets stayed EQUAL'. That is")
        print("    only worth something if these controls CAN move a bucket, so")
        print("    the host now presses them for real. No equality assertion")
        print("    runs after this point (WR-27).")

        # Step (8) above deliberately pointed the host's selection at the
        # CLIENT's unit (battle_open_inventory sets it before calling the real
        # handler), and battle_ui_press acts on whatever is selected - so put
        # the host back on one of its own soldiers first, or phase 3 would be
        # measuring the ownership refusal instead of the mint.
        h_unit = select_owned(host, host_own, "host")
        h_before = units_by_id(battle_state(host))[h_unit]
        assert h_before["tu"] > 0, f"host unit {h_unit} already at 0 TU"

        host.ok({"cmd": "battle_ui_press", "control": "zero_tu"})
        time.sleep(0.6)
        h_after = units_by_id(battle_state(host))[h_unit]
        c_view = units_by_id(battle_state(client))[h_unit]
        assert h_after["tu"] == 0, (
            f"the HOST's zero-TU press did nothing ({h_before['tu']} -> "
            f"{h_after['tu']}) - phase 1's 'TU unchanged' assertion is then "
            "vacuous, because the control cannot zero TU at all")
        assert c_view["tu"] == h_before["tu"], (
            "the client's copy changed too - nothing on the wire carries this, "
            f"so it should still read {h_before['tu']}, got {c_view['tu']}")
        stats = {}
        for gc, who in ((host, "host"), (client, "client")):
            stats[who] = gc.cmd({"cmd": "hash_now", "buckets": ["unitsStats"]})["h"]
        assert stats["host"]["unitsStats"] != stats["client"]["unitsStats"], (
            "unitsStats is EQUAL after the host zeroed a unit's TU locally - "
            "then the bucket does not cover this control and phase 1's "
            "mint-proof was vacuous for it")
        print(f"  PASS negative control (zero_tu): host TU {h_before['tu']} -> 0, "
              f"client still {c_view['tu']}, unitsStats now DIFFERS "
              f"({stats['host']['unitsStats']} vs {stats['client']['unitsStats']})")

        host.ok({"cmd": "battle_ui_press", "control": "hand_reaction", "hand": "right"})
        time.sleep(0.6)
        h_after2 = units_by_id(battle_state(host))[h_unit]
        moved = [f for f in ("reactOffLeft", "reactOffRight", "reactPrefLeft",
                             "reactPrefRight")
                 if h_after2[f] != h_before[f]]
        assert moved, (
            "the HOST's hand-reaction press changed none of the reaction fields "
            f"({h_before} -> {h_after2}) - phase 1's 'flags unchanged' assertion "
            "is then vacuous")
        blobs = {}
        for gc, who in ((host, "host"), (client, "client")):
            blobs[who] = gc.cmd({"cmd": "hash_now", "buckets": ["saveBlob"]})["h"]
        assert blobs["host"]["saveBlob"] != blobs["client"]["saveBlob"], (
            "saveBlob is EQUAL after the host flipped a reaction-hand field - "
            "then those fields are not in the hash and phase 1's mint-proof was "
            "vacuous for them")
        print(f"  PASS negative control (hand_reaction): host moved {moved}, "
              f"client unchanged, saveBlob now DIFFERS")

        print("\nALL W1-P5 CLIENT-GATE TESTS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
