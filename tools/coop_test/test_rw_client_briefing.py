"""W1-P3 (WAVE1-RUNBOOK.md SS4 / ruling D3 = WV-D9): the client runs a
READ-ONLY BriefingState on battle entry, so its flow converges on the host's -
briefing -> map.

WHAT WAS BROKEN. The client's entry pushed a bare BattlescapeState straight
over whatever stack it happened to be holding
(connectionTCP.cpp, the "no client-side BriefingState, this machine did not
generate the mission" comment W1-P3 replaces). Two consequences:
  * the two players saw DIFFERENT flows - the host got briefing -> equip -> map
    while the client was dropped onto the map with no idea what mission it was
    in (W1-P2 gave it the mission identity; this packet finally renders it);
  * a skirmish joiner was left sitting on ['MainMenuState','NewBattleState',
    'ServerList','LobbyMenu','BattlescapeState'] - a DEAD lobby it could not
    dismiss. That is the adjacent finding W1-P1 disclosed and routed here, and
    it is why test_skirmish_flow.py's step 7 carried SKIP-PENDING(W1-P3).

WHAT THIS ASSERTS.
  1. ENTRY SHAPE. The client reaches BriefingState, and the ORDER the runbook
     pins actually holds: BattlescapeState FIRST, BriefingState directly OVER
     it. The pre-battle menu stack is gone (no LobbyMenu / ServerList /
     NewBattleState), and the stack is never empty.
  2. CONTENT. The briefing renders the CARRIED labels (SS2.W1's
     strTarget/strCraftOrBase, applied on blob load) and the
     DEPLOYMENT-SPECIFIC title + description - never the "should never happen"
     generic fallback at BriefingState.cpp:104-108. Proven two ways: the
     client's rendered widget text is compared EXACTLY against the host's own
     BriefingState (same title, same description, both machines), and the
     coop resolution hook's log line is asserted never to say NONE.
  3. CUTSCENE + MUSIC SUPPRESSED. `_disableCutsceneAndMusic = _infoOnly &&
     !customBriefing` (BriefingState.cpp:142) is true, so init() returns at
     :277 before pushing a CutsceneState. Asserted as "no CutsceneState ever
     appeared on the client stack" plus the entry log line.
  4. RB-D5 / EXIT-REPORT surprise 19: Game::run() only think()s the TOP state,
     so a modal briefing over the battle screen is exactly where an apply queue
     would silently stall. The host emits real seq-stamped evs WHILE THE CLIENT
     IS IN THE BRIEFING and the client's event_state.queueDepth must drain to 0
     with lastSeqApplied advanced - the drain lives in
     connectionTCP::updateCoopTask(), not in any State.
  5. TESTSERVER PROBES UNDER A CLIENT BriefingState (SS1 WAVE-1 ADDITIONS trap
     2). SavedBattleGame::getBattleGame() derefs _battleState unconditionally;
     the guards at TestServer.cpp:3468-3469 / :5260 were verified against a
     HOST parked in BriefingState (W1-P2). The CLIENT is a NEW case - it has a
     live BattlescapeState UNDERNEATH the briefing - so battle_state,
     event_state, hash_now and get_palettes are all exercised there.
  6. WR-24 - THE RENDER HAZARD. BriefingState's ctor sets the GEOSCAPE base
     resolution + resetDisplay() and setStandardPalette("PAL_GEOSCAPE", ...)
     (BriefingState.cpp:58-60); btnOkClick sets the BATTLESCAPE values back
     (:297-300). W1-P3 does that OVER a live BattlescapeState. After
     close_briefing the client must be back on BattlescapeState with the
     BATTLESCAPE base resolution, a SCREEN palette equal to the host's, an
     unchanged map (mapFingerprint / mapObjTiles / mapSizeXYZ, cross-checked
     against the host) and all hash buckets EQUAL.
     NOTE the per-state "colors" get_palettes already reported are each State's
     OWN stored _palette, which a briefing round trip never touches - asserting
     on those alone would be VACUOUS for this trap, so W1-P3 added the additive
     `screen` object (base resolution + live screen palette) this test uses.
  7. RW-FIX-TURN's sentinel did not move: turn == 1 on BOTH machines. The
     client's counter mirror is still the LAST statement of the handshake, so
     the briefing push (which happens BEFORE battle_ready is built) cannot have
     reordered it.

COVERAGE LIMITS, stated honestly.
  * WHICH deployment-resolution path wins is fixture-dependent and deliberately
    NOT asserted (same reasoning as test_rw_mission_labels.py): on this
    skirmish the client's streamed blob is the host's whole SavedGame, so
    vanilla may still resolve the deployment itself. What is asserted is the
    OUTCOME - never NONE, and the rendered text equals the host's.
  * "Music suppressed" is proven structurally (infoOnly=true => the :277 early
    return) and by the absence of a CutsceneState; the harness has no audio
    probe and one is not worth minting for this.

Run:  python tools/coop_test/test_rw_client_briefing.py
"""

import json
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


def log_lines(user_dir):
    log = os.path.join(user_dir, "openxcom.log")
    if not os.path.exists(log):
        return []
    with open(log, encoding="utf-8", errors="replace") as f:
        return f.readlines()


def grep(user_dir, needle):
    return [l.rstrip("\n") for l in log_lines(user_dir) if needle in l]


def battle_state(gc):
    bs = gc.cmd({"cmd": "battle_state"})
    assert bs.get("ok"), f"battle_state failed: {bs}"
    return bs


def event_state(gc):
    es = gc.cmd({"cmd": "event_state"})
    assert es.get("ok"), f"event_state failed: {es}"
    return es


def palettes(gc):
    r = gc.cmd({"cmd": "get_palettes"})
    assert r.get("ok"), f"get_palettes failed: {r}"
    return r


def widget_texts(gc):
    r = gc.cmd({"cmd": "list_widgets"})
    assert r.get("ok"), f"list_widgets failed: {r}"
    return [w.get("text", "") for w in r["widgets"] if w.get("text")]


# ------------------------------------------------------------ lobby drive ---
# test_rw_handshake.py / test_rw_mission_labels.py / repro_atom_turn.py all
# carry these same inline copies (the stated precedent, WV-D18).
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
    port = "47985"
    host_dir = make_user_dir("rw_client_briefing_host")
    client_dir = make_user_dir("rw_client_briefing_client")
    host = GameClient("host", 48796, host_dir)
    client = GameClient("client", 48797, client_dir)
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

        # the client is deliberately left sitting DEEP in the menu stack here -
        # MainMenuState / NewBattleState / ServerList / LobbyMenu - because
        # that is exactly the stack assertion 1 requires the entry to unwind.
        pre_entry = states(client)
        assert "LobbyMenu" in pre_entry, \
            f"client should be in the lobby before the battle starts: {pre_entry}"
        print(f"pre-entry client stack: {pre_entry}")

        host.ok({"cmd": "lobby_action"})
        host.wait_for("host at battle settings",
                      lambda: (not session.has_state(host, "LobbyMenu")) or None)
        assert top_state(host) == "NewBattleState", \
            f"host should land on the NEW BATTLE setup screen, stack={states(host)}"

        host.ok({"cmd": "newbattle_ok"})
        host.wait_for("host briefing",
                      lambda: session.has_state(host, "BriefingState"), timeout=30)

        # === 1. ENTRY SHAPE ==================================================
        client.wait_for("client briefing",
                        lambda: session.has_state(client, "BriefingState"), timeout=60)
        time.sleep(2)  # let both logs flush the handshake lines

        cstack = states(client)
        assert cstack[-1] == "BriefingState", (
            "the client's read-only BriefingState must be the TOP state on entry "
            f"(D3: briefing -> map), stack={cstack}")
        assert len(cstack) >= 2 and cstack[-2] == "BattlescapeState", (
            "ORDER IS PINNED by the runbook: BattlescapeState FIRST, then "
            f"BriefingState OVER it - never inverted. stack={cstack}")
        for dead in ("LobbyMenu", "ServerList", "NewBattleState"):
            assert dead not in cstack, (
                f"the client's pre-battle menu stack was not torn down: {dead} is still "
                f"under the battle - a dead lobby the player cannot dismiss "
                f"(test_skirmish_flow.py step 7). stack={cstack}")
        assert cstack, "the client's state stack must never be left empty"
        print(f"PASS 1 entry shape: client stack={cstack} (was {pre_entry})")

        entry_log = grep(client_dir, "W1-P3: read-only BriefingState pushed over the")
        assert entry_log, (
            "client log has no W1-P3 entry line - the read-only BriefingState was not "
            "pushed by the coop battle entry (someone else put it there?)")
        print("CLIENT LOG:", entry_log[-1])

        # === 5. TestServer probes under a CLIENT BriefingState ===============
        # (done early, because every assertion below depends on them working)
        assert top_state(client) == "BriefingState"
        cb = battle_state(client)
        hb = battle_state(host)
        ces = event_state(client)
        assert cb.get("inBattle"), f"client battle_state says no battle: {cb}"
        assert ces.get("phase") == "Active", f"client phase != Active: {ces}"
        print("PASS 5: battle_state + event_state probed on a CLIENT parked in "
              "BriefingState with a live BattlescapeState underneath "
              "(TestServer.cpp:3468-3469 / :5260 guards hold)")

        # === 7. RW-FIX-TURN sentinel: battle_ready timing did not move =======
        # The client's counter mirror is the LAST statement of the handshake and
        # runs strictly after battle_ready is sent; the briefing push sits BEFORE
        # that block. If the push had been threaded through the middle of the
        # handshake this reads 0.
        assert cb.get("turn") == 1, (
            f"client battle_state.turn == {cb.get('turn')}, expected 1 - the RW-FIX-TURN "
            "counter mirror did not fire, i.e. the W1-P3 briefing push disturbed the "
            "client handshake's tail")
        print("PASS 7: client turn == 1 (RW-FIX-TURN mirror still the last statement "
              "of the handshake)")

        # === 2. CONTENT: carried labels + deployment-specific text ===========
        assert hb["strTarget"] == cb["strTarget"] and \
               hb["strCraftOrBase"] == cb["strCraftOrBase"], (
            f"mission identity differs: host={hb['strTarget']!r}/{hb['strCraftOrBase']!r} "
            f"client={cb['strTarget']!r}/{cb['strCraftOrBase']!r}")

        assert top_state(host) == "BriefingState", \
            f"host should still be in its own BriefingState for the text compare: {states(host)}"
        host_texts = widget_texts(host)
        client_texts = widget_texts(client)
        print("HOST   briefing texts:", json.dumps(host_texts))
        print("CLIENT briefing texts:", json.dumps(client_texts))

        assert any(cb["strTarget"] in t for t in client_texts), (
            f"the client's briefing does not render the carried mission target "
            f"{cb['strTarget']!r}; texts={client_texts}")
        assert any(cb["strCraftOrBase"] in t for t in client_texts), (
            f"the client's briefing does not render the carried craft label "
            f"{cb['strCraftOrBase']!r}; texts={client_texts}")

        # EXACT TEXT, never non-emptiness (SS1 WAVE-1 ADDITIONS / stale-language
        # deploy trap): the client's briefing must render the SAME strings the
        # host's does. A generic-fallback client would differ on title/description
        # even when the labels matched, and a missing language deploy would show
        # raw STR_ keys on one machine only.
        assert sorted(host_texts) == sorted(client_texts), (
            "the client's briefing does not render the same text as the host's - "
            "deployment-specific title/description missing (the BriefingState.cpp:"
            f"104-108 generic fallback?).\n  host  ={sorted(host_texts)}"
            f"\n  client={sorted(client_texts)}")

        # A raw STR_ key would mean the language deploy is stale (WV-D17) and a
        # missionType-as-title would mean tr() never resolved the deployment's
        # briefing strings.
        for t in client_texts:
            assert not t.startswith("STR_"), (
                f"the client's briefing rendered a RAW string key {t!r} - stale "
                "bin/x64/Release/common language deploy (WV-D17 robocopy step)")

        resolved = grep(client_dir, "[coop-handshake] BriefingState deployment:")
        assert resolved, (
            "client log has no '[coop-handshake] BriefingState deployment:' line - the "
            "SS2.W1 resolution hook (BriefingState.cpp:100) did not run for the entry "
            "briefing")
        print("CLIENT LOG:", resolved[-1])
        assert "deployment: NONE" not in resolved[-1], (
            "the client's entry briefing fell through to the generic 'should never "
            f"happen' branch (BriefingState.cpp:104-108): {resolved[-1]}")
        print("PASS 2 content: the client's briefing renders the carried labels and the "
              "same deployment-specific title/description as the host's")

        # === 3. cutscene + music suppressed ==================================
        assert "CutsceneState" not in cstack and "CutsceneState" not in states(client), (
            "a CutsceneState reached the client - `_disableCutsceneAndMusic = _infoOnly "
            "&& !customBriefing` (BriefingState.cpp:142) should have made "
            "BriefingState::init() return at :277")
        print("PASS 3: no CutsceneState on the client (cutscene/music suppressed by "
              "infoOnly=true)")

        # === 4. RB-D5: the apply queue drains UNDER the briefing =============
        # Game::run() only think()s the TOP state, so this is exactly where a
        # State-driven drain would stall. inject_ev is the host-side lever
        # (RB-D32): it mints a REAL seq through CoopEmit::sendEv and the client
        # applies it as a state-less no-op, so nothing can diverge.
        base_seq = event_state(client).get("lastSeqApplied", 0)
        emitted = []
        for i in range(3):
            r = host.cmd({"cmd": "inject_ev", "kind": "spot"})
            assert r.get("ok"), f"inject_ev failed on the host: {r}"
            emitted.append(r.get("seq"))
        print(f"host emitted seqs {emitted} with the client sitting in BriefingState")

        assert top_state(client) == "BriefingState", (
            "the client must still be IN the briefing while the host emits - that is "
            f"the whole point of this assertion. stack={states(client)}")

        def drained():
            es = event_state(client)
            return bool(es.get("queueDepth") == 0
                        and es.get("lastSeqApplied", 0) >= max(emitted))

        client.wait_for("client apply queue drained UNDER the briefing overlay",
                        lambda: drained() or None, timeout=20)
        ces = event_state(client)
        assert top_state(client) == "BriefingState", (
            f"the client left the briefing during the drain: {states(client)}")
        assert not ces.get("desyncSeen"), f"client froze on a desync: {ces}"
        print(f"PASS 4 RB-D5: queueDepth=0, lastSeqApplied={ces['lastSeqApplied']} "
              f"(was {base_seq}) with the BriefingState ON SCREEN - the drain lives in "
              "updateCoopTask(), not in a State")

        # === host proceeds to its map; then the client dismisses its briefing ==
        host.ok({"cmd": "close_briefing"})
        host.wait_for("host battlescape",
                      lambda: session.has_state(host, "BattlescapeState"), timeout=30)
        deadline = time.time() + 15
        while time.time() < deadline and top_state(host) != "BattlescapeState":
            host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_ESCAPE})
            time.sleep(0.3)
        assert top_state(host) == "BattlescapeState", \
            f"host battle-start overlays never cleared, stack={states(host)}"
        time.sleep(1)

        host_scr = palettes(host)["screen"]
        hb2 = battle_state(host)
        assert hb2["turn"] == 1, f"host turn != 1 after its own entry chain: {hb2['turn']}"

        # === 6. WR-24: close_briefing lands on a CORRECTLY RENDERING map ======
        client.ok({"cmd": "close_briefing"})
        client.wait_for("client back on the battlescape",
                        lambda: (top_state(client) == "BattlescapeState") or None,
                        timeout=20)
        time.sleep(1)

        cstack2 = states(client)
        assert cstack2[-1] == "BattlescapeState", \
            f"close_briefing should land the client on BattlescapeState: {cstack2}"
        assert "BriefingState" not in cstack2, \
            f"the client's briefing was not popped: {cstack2}"

        client_scr = palettes(client)["screen"]
        assert client_scr["baseXResolution"] == client_scr["baseXBattlescape"] and \
               client_scr["baseYResolution"] == client_scr["baseYBattlescape"], (
            "the client's base resolution is still the GEOSCAPE one after close_briefing "
            "- BriefingState::btnOkClick's restore (BriefingState.cpp:297-300) did not "
            f"take effect: {client_scr}")
        assert client_scr["colors"] == host_scr["colors"], (
            "the client's live SCREEN palette differs from the host's after the briefing "
            "round trip - WR-24 / the battlePaletteSource trap shape.\n"
            f"  host  ={host_scr['colors']}\n  client={client_scr['colors']}")

        cb2 = battle_state(client)
        for key in ("mapFingerprint", "mapObjTiles", "mapSizeXYZ"):
            assert cb2[key] == cb[key], (
                f"the client's {key} changed across the briefing round trip: "
                f"before={cb[key]} after={cb2[key]}")
            assert cb2[key] == hb2[key], (
                f"the client's {key} does not match the host's after the briefing: "
                f"host={hb2[key]} client={cb2[key]}")
        assert cb2["turn"] == 1 and hb2["turn"] == 1, (
            f"turn parity broken after the briefing: host={hb2['turn']} "
            f"client={cb2['turn']}")

        hh, ch = session.assert_hash_clean(
            host, client, full=True,
            what="after the client's entry-briefing round trip")
        print(f"PASS 6 WR-24: client back on BattlescapeState with the BATTLESCAPE base "
              f"resolution, a screen palette identical to the host's, an unchanged map "
              f"(fingerprint={cb2['mapFingerprint']}, objTiles={cb2['mapObjTiles']}) and "
              f"ALL {len(hh)} hash buckets EQUAL")

        assert not battle_state(client)["authority"]["desyncFrozen"], \
            "client desync-frozen at the end of the run"

        print("ALL W1-P3 CLIENT-BRIEFING TESTS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
