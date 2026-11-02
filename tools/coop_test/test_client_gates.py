"""CLIENT HARD GATES on battlescape controls that would otherwise run locally
on a co-op client, plus the quick-load gate and the chat-open `allowButtons`
guard.

Ungated, all of these would run locally on a co-op CLIENT with nothing on the
wire:
  * ABORT MISSION      -> AbortMissionState, ungated on either machine.
                          Either player's press opens vanilla's dialog and
                          its OK asks a unanimous vote (the abort row below).
  * mid-battle INVENTORY -> a full re-equip of any unit, writing `items`.
                          The client opens its OWN soldiers' inventory and
                          every placement is an order the host performs (the
                          inventory row below).
  * ZERO TU            -> BattleUnit::clearTimeUnits(), writing `unitsStats`.
  * hand REACTION toggles -> preferredHandForReactions /
                          reactionsDisabledFor{Left,Right}Hand, which are
                          serialized (BattleUnit.cpp:791-796) and are NOT on
                          saveBlobExcludedUnitKey's list, so they land in the
                          saveBlob bucket.
  * QUICK LOAD (F9)    -> LoadGameState pushed unconditionally; its own
                          chokepoint then refused SILENTLY (log-only).
Three of the five would therefore diverge the two machines permanently, on one
keypress, with no message and no detector until the next hash.

WHAT THIS ASSERTS.
  PHASE 1 - every listed control, pressed on the CLIENT through its REAL
    handler: the exact refusal text on battle_state.coopWaitText, the absence
    of the effect (no dialog / no InventoryState / TU unchanged / reaction
    flags unchanged / no LoadGameState), and `hash_now full` ALL BUCKETS EQUAL
    after every single press. That last one is the MINT-PROOF.
    hand_reaction, the hand-reaction toggle, is not refused: the press is a
    `reaction_hands` intent the HOST runs with vanilla's own toggle; the row
    asserts the order (one host intent context, the client's intent counter),
    vanilla's resulting flags on BOTH machines and all buckets EQUAL.
    inventory, the mid-battle inventory, is not refused either: the client
    opens its OWN soldier's inventory (InventoryState on top, inventory_view
    naming the unit) and opening and closing it leaves all buckets EQUAL. Its
    placements are test_inventory.py's.
  PHASE 2 - the same controls on the HOST still WORK (the gate is client-side,
    not a global disable), the ownership term refuses a host press against a
    CLIENT-owned unit with its own not_your_unit string, and the chat-open
    guard suppresses a host press while the chat overlay has the keyboard.
    Everything in phase 2 is non-mutating, so the buckets stay EQUAL.
  PHASE 3 - THE NEGATIVE CONTROL, and it deliberately DIVERGES the two
    machines. Phase 1's "all buckets EQUAL after the press" would be VACUOUS
    if these controls could not move a bucket in the first place (an
    assertion that is true by construction proves nothing). So the last thing
    this test does is let the HOST press ZERO TU and the hand-reaction toggle
    for real. ZERO TU must move the host's own `unitsStats` (the host's press
    reaches the client in one host action, so the two machines are not
    compared for it); the hand toggle must make `saveBlob` DIFFER, naming the
    fields that moved. No equality assertion runs after that point, and
    nothing else happens in the battle, so nothing is left to freeze on it.

REACHABILITY, checked rather than assumed. Every control here is
genuinely pressable on a co-op client: allowButtons() needs
`_save->getSide() == FACTION_PLAYER`, which is TRUE on BOTH machines in a
classic co-op battle during the player side, and btnInventoryClick /
btn*HandItemClick gate on playableUnitSelected(), which is the same condition.
None of these is dead framing the way an off-turn END TURN press is. The one
control NOT covered here is the pre-battle equip screen.

Run:  python tools/coop_test/test_client_gates.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session

SDLK_TAB = 9        # Options::keyBattleNextUnit default (as in test_equip_freeze)
SDLK_ESCAPE = 27    # Options::keyCancel - AbortMissionState's own cancel binding
COOP_SEAT_1 = 1

# bin/common/Language/en-US.yml, VERBATIM. Exact text, never non-emptiness
# (a raw STR_ key here means the deployed bin/x64/Release/common/Language copy
# is stale relative to bin/common/).
TXT_ABORT = "Only the host can abort the mission"   # the abort row names it only in its
# failure messages: the client's press opens vanilla's abort dialog instead
TXT_INVENTORY = "Only the host can open the inventory"   # the inventory row names it only in
# its failure message: the client opens its own soldier's inventory instead
TXT_ZERO_TU = "Only the host can expend a soldier's time units"
TXT_REACTIONS = "Only the host can change reaction fire settings"
TXT_LOAD = "Saved games cannot be loaded during a co-op session"
TXT_NOT_YOUR_UNIT = "Not one of your soldiers"      # the ownership term's text, reused not duplicated
TXT_EQUIP_FROZEN = "Pre-battle equipment is locked in co-op"   # a notice the client's entry must not show


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
    before any seat filter exists - both machines have been seen starting on
    unit 8, which in this fixture is the CLIENT's soldier. The selection cycle
    itself is seat-filtered (coopMaySelectUnit), so TAB lands
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
# Same inline copies test_equip_freeze.py / test_handshake.py carry.
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

    # stamp ONE soldier to seat 1 BEFORE generation, so the client
    # really owns a unit (repro_atom_turn.py's helper set, reused).
    seat = host.ok({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1})

    host.ok({"cmd": "newbattle_ok"})
    # the shared battle-entry spine (both briefings, both pre-battle
    # equip screens, both Turn-1 screens).
    session.briefings_to_battlescape(host, client)
    time.sleep(1)
    return seat


# ------------------------------------------------------------------- main ---
def main():
    port = "47992"
    host_dir = make_user_dir("client_gates_host")
    client_dir = make_user_dir("client_gates_client")
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

        # Every press below has to CHANGE the banner, which is what makes each
        # text assertion mean "this press produced this message". The client's
        # entry banner after both equip screens and turn 1 is '' (no
        # TXT_EQUIP_FROZEN notice).
        assert banner(client) == "", (
            f"client's entry banner is {banner(client)!r}, expected '' (no "
            f"{TXT_EQUIP_FROZEN!r} notice); every press below must change it")

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
                "(a raw STR_ key = stale language deploy)")
            effect_check()
            session.assert_hash_clean(
                host, client, full=True,
                what=f"after the client's refused {label} (MINT-PROOF)")
            print(f"  PASS {label}: {got!r}, no effect, all buckets EQUAL")

        # abort ------------------------------------------------------------
        # Not refused. The client's press opens vanilla's AbortMissionState
        # (its OK asks the abort vote, test_abort_vote.py), ESC closes it, and
        # opening and closing it write nothing hashed (ALL BUCKETS EQUAL while
        # it is open and after the ESC - the MINT-PROOF). No refusal banner.
        client.ok({"cmd": "battle_ui_press", "control": "abort"})
        time.sleep(0.6)
        got = banner(client)
        assert "AbortMissionState" in states(client), (
            f"abort: the client's press did not open the abort dialog (banner {got!r}; "
            f"the host-only refusal is {TXT_ABORT!r}): {states(client)}")
        assert got != TXT_ABORT, f"abort: client banner {got!r} (the host-only refusal)"
        session.assert_hash_clean(
            host, client, full=True,
            what="with the client's abort dialog open (MINT-PROOF)")
        client.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_ESCAPE})
        client.wait_for("client abort dialog closed by ESC",
                        lambda: ("AbortMissionState" not in states(client)) or None,
                        timeout=15)
        session.assert_hash_clean(
            host, client, full=True,
            what="after the client closed its abort dialog (MINT-PROOF)")
        print("  PASS abort: the client's dialog opened and ESC closed it, all buckets EQUAL")

        # inventory (mid-battle) -------------------------------------------
        # Not refused. The client opens its OWN soldier's inventory:
        # battle_open_inventory drives the REAL bstate->btnInventoryClick
        # (TestServer.cpp), the client's top state is InventoryState,
        # inventory_view names c_unit, and opening and closing the screen write
        # nothing hashed (ALL BUCKETS EQUAL while it is open and after
        # battle_close_inventory - the MINT-PROOF). No banner assertion: the
        # banner stays '' after the abort row (no refusal), and zero_tu sees its
        # own text change. `inventory_move` is deliberately NOT used anywhere here:
        # it is a dead "unsupported" stub, so any assertion through it is
        # vacuous.
        inv_resp = client.cmd({"cmd": "battle_open_inventory", "unit": c_unit})
        inv_banner = banner(client)
        inv_view = client.cmd({"cmd": "inventory_view"})
        assert inv_resp.get("opened") is True, (
            f"the client could not open its OWN soldier's mid-battle inventory (unit "
            f"{c_unit}): {inv_resp}, client banner {inv_banner!r} (the host-only "
            f"refusal is {TXT_INVENTORY!r})")
        assert top_state(client) == "InventoryState", (
            f"the client's top state is not the inventory: {states(client)}")
        assert inv_view.get("open") is True and inv_view.get("unitId") == c_unit, (
            f"client inventory_view {inv_view} (want open on unit {c_unit})")
        session.assert_hash_clean(
            host, client, full=True,
            what="with the client's own inventory open (MINT-PROOF)")
        client.ok({"cmd": "battle_close_inventory"})
        client.wait_for("client inventory closed",
                        lambda: ("InventoryState" not in states(client)) or None,
                        timeout=15)
        session.assert_hash_clean(
            host, client, full=True,
            what="after the client closed its own inventory (MINT-PROOF)")
        print(f"  PASS inventory: the client opened and closed its own unit {c_unit}'s "
              f"inventory, all buckets EQUAL")

        # zero_tu ----------------------------------------------------------
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

        # hand_reaction ----------------------------------------------------
        # Not refused. The client's hand right-click is a `reaction_hands` intent
        # the HOST runs with vanilla's own toggleRightHandForReactions(ctrl
        # false): the press
        # produced an intent (client coopIntentsSent.reaction_hands +1), the host
        # executed it (exactly one new {origin intent, kind reaction_hands,
        # actorId c_unit} in its closedContexts), nothing ran locally (client
        # coopClientBStatePushes unchanged), and both machines hold vanilla's
        # result - offRight false, the right hand preferred unless it already
        # was - with ALL BUCKETS EQUAL (the MINT-PROOF).
        rflags = ("reactOffLeft", "reactOffRight", "reactPrefLeft", "reactPrefRight")
        want_flags = dict((f, c_before[f]) for f in rflags)
        want_flags["reactPrefRight"] = not c_before["reactPrefRight"]
        want_flags["reactPrefLeft"] = False
        want_flags["reactOffRight"] = False
        es_h0, es_c0 = session.event_state(host), session.event_state(client)
        ctx0 = {c.get("actionId") for c in (es_h0.get("closedContexts") or [])}
        sent0 = (es_c0.get("coopIntentsSent") or {}).get("reaction_hands", 0)
        pushes0 = es_c0.get("coopClientBStatePushes")

        def hands_ctxs():
            return [c for c in (session.event_state(host).get("closedContexts") or [])
                    if c.get("actionId") not in ctx0 and c.get("origin") == "intent"
                    and c.get("kind") == "reaction_hands" and c.get("actorId") == c_unit]

        client.ok({"cmd": "battle_ui_press", "control": "hand_reaction", "hand": "right"})
        client.wait_for("the client's reaction_hands order closed on the host and applied on the client",
                        lambda: (hands_ctxs() and session.event_state(client).get("inFlight") is None
                                 and session.event_state(client).get("lastSeqApplied")
                                 == session.event_state(host).get("lastSeqEmitted")) or None,
                        timeout=15, interval=0.1)
        es_c1 = session.event_state(client)
        got = banner(client)
        h_now = units_by_id(battle_state(host))[c_unit]
        c_now = units_by_id(battle_state(client))[c_unit]
        print(f"  hand_reaction: contexts={hands_ctxs()} sent {sent0}->"
              f"{(es_c1.get('coopIntentsSent') or {}).get('reaction_hands', 0)} pushes {pushes0}->"
              f"{es_c1.get('coopClientBStatePushes')} flags before={dict((f, c_before[f]) for f in rflags)} "
              f"host={dict((f, h_now[f]) for f in rflags)} client={dict((f, c_now[f]) for f in rflags)} "
              f"banner={got!r}")
        assert len(hands_ctxs()) == 1, (
            f"hand_reaction: host closedContexts gained {hands_ctxs()} (want exactly one "
            f"{{origin intent, kind reaction_hands, actorId {c_unit}}})")
        assert (es_c1.get("coopIntentsSent") or {}).get("reaction_hands", 0) == sent0 + 1, (
            f"hand_reaction: client coopIntentsSent {es_c0.get('coopIntentsSent')} -> "
            f"{es_c1.get('coopIntentsSent')} (want reaction_hands +1)")
        assert es_c1.get("coopClientBStatePushes") == pushes0, (
            f"hand_reaction: client coopClientBStatePushes {pushes0} -> {es_c1.get('coopClientBStatePushes')}")
        for f in rflags:
            assert h_now[f] == want_flags[f] and c_now[f] == want_flags[f], (
                f"hand_reaction: {f} host={h_now[f]} client={c_now[f]} (want {want_flags[f]} on both: "
                f"vanilla's toggle, run by the host)")
        assert got != TXT_REACTIONS, (
            f"hand_reaction: client banner {got!r} (the host-only refusal)")
        session.assert_hash_clean(host, client, full=True,
                                  what="after the client's hand_reaction order (MINT-PROOF)")
        print(f"  PASS hand_reaction: an order the host ran, flags {want_flags} on both, all buckets EQUAL")

        # quickload --------------------------------------------------------
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

        # host abort: really opens the dialog ------------------------------
        host.ok({"cmd": "battle_ui_press", "control": "abort"})
        time.sleep(0.6)
        assert "AbortMissionState" in states(host), (
            "the HOST could not open the abort dialog - the gate must be "
            f"client-side, not a global disable. stack={states(host)}")
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_ESCAPE})
        host.wait_for("host abort dialog dismissed",
                      lambda: ("AbortMissionState" not in states(host)) or None,
                      timeout=15)
        print("  PASS host abort: dialog opened, cancelled without aborting")

        # host inventory: opens on its OWN unit ----------------------------
        r = host.cmd({"cmd": "battle_open_inventory", "unit": h_unit})
        assert r.get("opened") is True, (
            f"the HOST could not open the mid-battle inventory on its own unit "
            f"{h_unit}: {r}")
        host.ok({"cmd": "battle_close_inventory"})
        host.wait_for("host inventory closed",
                      lambda: ("InventoryState" not in states(host)) or None,
                      timeout=15)
        print("  PASS host inventory: opened on its own unit and closed")

        # ownership term: host press against a CLIENT-owned unit -----------
        r = host.cmd({"cmd": "battle_open_inventory", "unit": c_unit})
        assert r.get("opened") is False, (
            f"the host opened the inventory of the CLIENT's unit {c_unit}: {r}")
        assert banner(host) == TXT_NOT_YOUR_UNIT, (
            f"host banner is {banner(host)!r}, expected {TXT_NOT_YOUR_UNIT!r} - "
            "the ownership term must refuse with its OWN reason "
            "(not_your_unit), not with the host-only string")
        print(f"  PASS ownership term: host refused on the client's unit "
              f"with {TXT_NOT_YOUR_UNIT!r}")

        # chat guard: the CHAT-OPEN allowButtons guard (as in older versions) -
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
        print("    runs after this point.")

        # The ownership-term check above deliberately pointed the host's selection at the
        # CLIENT's unit (battle_open_inventory sets it before calling the real
        # handler), and battle_ui_press acts on whatever is selected - so put
        # the host back on one of its own soldiers first, or phase 3 would be
        # measuring the ownership refusal instead of the mint.
        h_unit = select_owned(host, host_own, "host")
        h_before = units_by_id(battle_state(host))[h_unit]
        assert h_before["tu"] > 0, f"host unit {h_unit} already at 0 TU"

        # The host's own ZERO TU press reaches the client in one `host` action
        # (coopHostZeroTu), so this control's non-vacuity is proved on the HOST
        # alone - its own unitsStats moves with the press - and the two machines
        # are not compared for it. The hand toggle below stays the deliberate
        # divergence.
        s0 = host.cmd({"cmd": "hash_now", "buckets": ["unitsStats"]})["h"]["unitsStats"]
        host.ok({"cmd": "battle_ui_press", "control": "zero_tu"})
        time.sleep(0.6)
        h_after = units_by_id(battle_state(host))[h_unit]
        assert h_after["tu"] == 0, (
            f"the HOST's zero-TU press did nothing ({h_before['tu']} -> "
            f"{h_after['tu']}) - phase 1's 'TU unchanged' assertion is then "
            "vacuous, because the control cannot zero TU at all")
        s1 = host.cmd({"cmd": "hash_now", "buckets": ["unitsStats"]})["h"]["unitsStats"]
        assert s1 != s0, (
            "the host's unitsStats did not move when it zeroed a unit's TU - "
            "then the bucket does not cover this control and phase 1's "
            "mint-proof was vacuous for it")
        print(f"  PASS negative control (zero_tu): host TU {h_before['tu']} -> 0, "
              f"host unitsStats moved ({s0} -> {s1})")

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

        print("\nALL CLIENT-GATE TESTS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
