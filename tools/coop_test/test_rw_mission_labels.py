"""W1-P2 (WAVE1-RUNBOOK.md SS2.W1, ruling D-4 = shape (d); WV-D9/WV-D28/WV-D42):
`battle_offer` mission identity on the wire + the ctrl-B gate.

WHAT WAS BROKEN. A thin client never runs BriefingState, so it never learned
what mission it was in: the two display labels vanilla mints inside
BriefingState (strTarget "LANDING SITE-0" / strCraftOrBase "CRAFT> SKYRANGER-1",
BriefingState.cpp:151-188) stayed EMPTY on the client - test_rw_hash_now.py's
own docstring records them as the last unexcluded saveBlob divergence, closed at
the time by EXCLUDING them from the hash rather than by syncing them. And ctrl-B
on the client scanned getSavedGame()->getBases() for a craft with
isInBattlescape() (BattlescapeState.cpp:2841-2854), found none (the client never
generated the mission), and pushed a BriefingState with a null craft - which
cannot re-derive the deployment either, so it rendered the "should never happen"
generic fallback (BriefingState.cpp:104-108) with two empty labels.

WHAT THIS ASSERTS.
  1. The host mints the labels BEFORE it builds the offer (the SS2.W1 ORDERING
     TRAP: offerBattle() snapshots the blob and the CALLER pushes BriefingState
     only afterwards, so at offer-build time the labels are still empty).
  2. The client applies target/craftOrBase from the offer and reports them
     EQUAL to the host's, with a non-empty carried `deployment`. Non-emptiness
     of the two labels is asserted only on craft-entry paths; on base defense
     only KEY PRESENCE is asserted, because strTarget is empty there when (and
     only when) the loaded mod defines no operationNames - the mint block's
     condition is `if (craft || base)` at BriefingState.cpp:172-186
     (SS2.W1 / WR-9 / IR2-10).
  3. RE-MINT SUPPRESSION: the host's own BriefingState does NOT overwrite the
     labels it minted before the offer. Asserted twice - once deterministically
     on the host's "label re-mint SUPPRESSED" log line, and once on the VALUE,
     by comparing the host's live label after BriefingState has run against the
     one the client received from the offer. The guard covers the WHOLE
     `if (!_infoOnly)` body (BriefingState.cpp:151-188), not just the
     operation-name block: this test's first run traced the half-guard failing
     from the other direction - the craft branch writes strTarget FIRST
     ("LANDING SITE-0") and the operation-name block then overwrites it, so
     suppressing only the second half locks in the clobbered value and the two
     players STILL read different mission names.
  4. ctrl-B on the CLIENT renders the carried labels instead of the generic
     fallback: the pushed BriefingState's Text widgets carry the mission target
     and the craft label, and the coop resolution hook reports a deployment
     (VANILLA or CARRIED), never NONE - NONE is the generic branch at
     BriefingState.cpp:104-108. NOTE which of the two wins is FIXTURE-dependent
     and deliberately not asserted: on this skirmish the client's streamed blob
     is the host's whole SavedGame, so its ctrl-B craft scan
     (BattlescapeState.cpp:2841-2854) still finds the in-battlescape Craft and
     vanilla resolves on its own; the CARRIED path is what covers a client whose
     world has no such craft. WR-27: the "ctrl-B never rewrites strTarget"
     assertion is NOT shipped - ctrl-B passes infoOnly=true and the
     `if (!_infoOnly)` gate at BriefingState.cpp:151 makes it vacuous by
     construction.
  5. WR-24: after the ctrl-B BriefingState is dismissed (it swaps the palette
     and the base resolution to GEOSCAPE and back, BriefingState.cpp:58-60 /
     :273-274) the client's battlescape is intact - same top state, same
     BattlescapeState palette, same map fingerprint, and hash_now full still
     all-buckets EQUAL.
  6. The whole thing is HASH-NEUTRAL: strTarget/strCraftOrBase are saveBlob-
     hash-EXCLUDED (SharedEcon.cpp:3974, applied by the tree-walker
     saveBlobHashTree :4033), so writing them on the client cannot move a
     bucket. hash_now {full:true} is asserted ALL-BUCKETS-EQUAL (never a
     hard-coded bucket count - W1-P8 adds a ninth, see the WAVE-1 ADDITIONS
     "HASH BUCKET COUNT CHANGES MID-WAVE" trap).

WHY THE Coop_OperationNames_Test MOD. The shipped xcom1 ruleset defines NO
operationNamesFirst/Last, so BriefingState's random-operation-name mint never
fires on the stock skirmish fixture and assertion 3's VALUE half would be
vacuous (the only other writer on that path is the craft-destination name, which
is deterministic and re-derives the identical string with or without the guard).
The mod supplies a 24 x 24 pool, so an unsuppressed re-mint lands on a different
name with p = 575/576. Both machines get the SAME mod (their rulesets must not
diverge).

Run:  python tools/coop_test/test_rw_mission_labels.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session

HERE = os.path.dirname(os.path.abspath(__file__))
OPNAMES_MOD = os.path.join(HERE, "mods", "Coop_OperationNames_Test")

SDLK_b = ord("b")
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


def labels(gc):
    """battle_state's W1-P2 mission-identity fields (WR-23, additive)."""
    bs = gc.cmd({"cmd": "battle_state"})
    assert bs.get("ok") or bs.get("inBattle") is not None, f"battle_state failed: {bs}"
    return bs


def assert_label_keys(bs, who):
    # SS2.W1 / WR-9: REQUIRED means the KEY IS PRESENT, not that the value is
    # non-empty. This is the assertion that holds on every entry path,
    # base defense included.
    for key in ("strTarget", "strCraftOrBase", "deployment"):
        assert key in bs, (
            f"{who} battle_state is missing the W1-P2 mission-identity key "
            f"'{key}' (WR-23 added all three additively): {sorted(bs.keys())}")


def palette_of(gc, state_name):
    r = gc.cmd({"cmd": "get_palettes"})
    assert r.get("ok"), f"get_palettes failed: {r}"
    for e in r["states"]:
        if e["state"].replace("class OpenXcom::", "") == state_name:
            return e["colors"]
    return None


def widget_texts(gc):
    r = gc.cmd({"cmd": "list_widgets"})
    assert r.get("ok"), f"list_widgets failed: {r}"
    return r, [w.get("text", "") for w in r["widgets"] if w.get("text")]


# ------------------------------------------------------------------- main ---
def main():
    port = "47987"
    host_dir = make_user_dir("rw_labels_host", mods=[OPNAMES_MOD])
    client_dir = make_user_dir("rw_labels_client", mods=[OPNAMES_MOD])
    host = GameClient("host", 48794, host_dir)
    client = GameClient("client", 48795, client_dir)
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        # --- bring-up: test_rw_handshake.py's own lobby drive -----------------
        skirmish_host(host, port)
        skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer"})

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

        host.ok({"cmd": "newbattle_ok"})
        host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=30)
        client.wait_for("client battlescape",
                        lambda: session.has_state(client, "BattlescapeState"), timeout=60)
        time.sleep(2)  # let both logs flush the handshake lines
        print("PASS bring-up: host in BriefingState, client in BattlescapeState")

        # === 1. the host minted BEFORE the offer ============================
        minted = grep(host_dir, "[coop-handshake] mission labels minted pre-offer")
        assert minted, (
            "host log has no 'mission labels minted pre-offer' line - "
            "CoopHandshake::mintMissionLabels() never ran at the offerBattle() call "
            "site (SS2.W1 ORDERING TRAP / WV-D42)")
        print("HOST LOG:", minted[-1])

        applied = grep(client_dir, "[coop-handshake] mission labels applied from battle_offer")
        assert applied, (
            "client log has no 'mission labels applied from battle_offer' line - "
            "battle_offer.missionLabel never arrived or was not applied (SS2.W1)")
        print("CLIENT LOG:", applied[-1])

        # === 2. probe BOTH machines while the HOST SITS IN BriefingState =====
        # WAVE-1 ADDITIONS / EXIT-REPORT-G5 surprise 30: battle_state against a
        # machine parked in BriefingState used to hard-kill the process; the
        # guard is at TestServer.cpp:5260. This wave puts a BriefingState on the
        # CLIENT too (W1-P3), so the new W1-P2 fields are re-verified here,
        # deliberately, with the host still in its briefing.
        assert top_state(host) == "BriefingState", \
            f"host should still be in BriefingState for this probe, stack={states(host)}"
        hb = labels(host)
        cb = labels(client)
        assert_label_keys(hb, "host")
        assert_label_keys(cb, "client")
        print("HOST   battle_state identity:", json.dumps(
            {k: hb.get(k) for k in ("missionType", "strTarget", "strCraftOrBase", "deployment")},
            sort_keys=True))
        print("CLIENT battle_state identity:", json.dumps(
            {k: cb.get(k) for k in ("missionType", "strTarget", "strCraftOrBase", "deployment")},
            sort_keys=True))
        print("PASS: battle_state probes both machines with the host parked in "
              "BriefingState (TestServer.cpp:5260 guard still holds)")

        assert hb["strTarget"] == cb["strTarget"], (
            f"strTarget differs: host={hb['strTarget']!r} client={cb['strTarget']!r} - the "
            "client did not receive/apply battle_offer.missionLabel, or the host re-minted")
        assert hb["strCraftOrBase"] == cb["strCraftOrBase"], (
            f"strCraftOrBase differs: host={hb['strCraftOrBase']!r} "
            f"client={cb['strCraftOrBase']!r}")
        assert hb["deployment"] == cb["deployment"], (
            f"carried deployment differs: host={hb['deployment']!r} client={cb['deployment']!r}")
        assert hb["deployment"], (
            "carried `deployment` is EMPTY - SS2.W1 requires it to always resolve; without "
            "it the client's briefing renders the generic 'should never happen' fallback "
            "(BriefingState.cpp:104-108)")

        # NON-EMPTINESS only on craft-entry paths (SS2.W1 / WR-9 / IR2-10).
        mission = hb.get("missionType", "")
        if mission != "STR_BASE_DEFENSE":
            assert hb["strTarget"], (
                f"strTarget is empty on a craft-entry mission ({mission}) - the pre-offer "
                "mint did not run BriefingState.cpp:154-164's craft branch")
            assert hb["strCraftOrBase"], (
                f"strCraftOrBase is empty on a craft-entry mission ({mission})")
            print(f"PASS: mission identity EQUAL and non-empty on both machines "
                  f"(missionType={mission}, target={hb['strTarget']!r}, "
                  f"craftOrBase={hb['strCraftOrBase']!r}, deployment={hb['deployment']!r})")
        else:
            print(f"PASS: mission identity EQUAL on both machines; base defense, so only "
                  f"KEY PRESENCE asserted for the labels (deployment={hb['deployment']!r})")

        # === 3. RE-MINT SUPPRESSION =========================================
        # (a) deterministic: the guard actually fired inside BriefingState.
        suppressed = grep(host_dir, "label re-mint SUPPRESSED")
        assert suppressed, (
            "host log has no 'label re-mint SUPPRESSED' line - BriefingState's "
            "UNCONDITIONAL `if (!_infoOnly)` label-write body (BriefingState.cpp:151-188) "
            "was not gated, so the host is free to overwrite the labels the offer already "
            "shipped (SS2.W1 RE-MINT SUPPRESSION / WV-D42)")
        print("HOST LOG:", suppressed[-1])

        # (b) by value: the mod defines a 24x24 operation-name pool, so an
        # unsuppressed re-mint inside the host's BriefingState ctor - which has
        # ALREADY RUN by the time this reads the host - would have landed on a
        # different string than the one the client got from the offer. NOTE the
        # guard has to cover the WHOLE `if (!_infoOnly)` body, not just the
        # operation-name block: the craft branch writes strTarget FIRST (the
        # destination name, "LANDING SITE-0") and the operation-name block then
        # overwrites it, so a half-guard reds this assertion from the other
        # direction - host="LANDING SITE-0" vs client="<operation name>". That
        # is exactly what this assertion caught on its first run.
        assert hb["strTarget"] == cb["strTarget"], "re-mint suppression failed (value)"
        print("PASS re-mint suppression: host's post-BriefingState label still "
              f"{hb['strTarget']!r}, identical to the one the offer shipped")

        # === host proceeds to the battlescape; labels must not move ==========
        host.ok({"cmd": "click_widget", "match": "ok"})
        host.wait_for("host battlescape",
                      lambda: session.has_state(host, "BattlescapeState"), timeout=30)
        deadline = time.time() + 10
        while time.time() < deadline and top_state(host) != "BattlescapeState":
            host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_ESCAPE})
            time.sleep(0.3)
        assert top_state(host) == "BattlescapeState", \
            f"host battle-start overlays never cleared, stack={states(host)}"
        time.sleep(2)

        hb2 = labels(host)
        assert (hb2["strTarget"], hb2["strCraftOrBase"], hb2["deployment"]) == \
               (hb["strTarget"], hb["strCraftOrBase"], hb["deployment"]), (
            f"the host's mission identity CHANGED between BriefingState and the "
            f"battlescape: before={hb['strTarget']!r}/{hb['strCraftOrBase']!r}/"
            f"{hb['deployment']!r} after={hb2['strTarget']!r}/{hb2['strCraftOrBase']!r}/"
            f"{hb2['deployment']!r}")
        print("PASS: the host's labels are UNCHANGED after its own BriefingState ran")

        # === 6. hash neutrality (labels are hash-EXCLUDED) ==================
        hh, ch = session.assert_hash_clean(host, client, full=True,
                                           what="t=0 after mission labels landed")
        print(f"PASS hash_now full: ALL {len(hh)} buckets EQUAL at t=0 with the labels "
              "carried and applied on the client (SharedEcon.cpp:3974 exclusion holds)")
        print("HOST   h:", json.dumps(hh, indent=2, sort_keys=True))

        # === 4. ctrl-B on the CLIENT ========================================
        pal_before = palette_of(client, "BattlescapeState")
        map_before = (cb.get("mapFingerprint"), cb.get("mapObjTiles"), cb.get("mapSizeXYZ"))
        assert top_state(client) == "BattlescapeState", \
            f"client should be on BattlescapeState before ctrl-B, stack={states(client)}"

        # SDL_GetModState() is what Game::isCtrlPressed() reads (Game.cpp:845-852)
        # and SDL_PushEvent does not update it, so the modifier is LATCHED first
        # (W1-P2's inject_input "mod") and cleared again below.
        client.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_b, "mod": "ctrl"})
        try:
            client.wait_for("client ctrl-B briefing",
                            lambda: session.has_state(client, "BriefingState"), timeout=15)
        finally:
            # kind=modstate clears the latch WITHOUT pushing a key: an ESC here
            # lands on the BriefingState ctrl-B just opened and closes it again
            # (observed on this test's first run - the briefing was correct, the
            # clearing keystroke ate it).
            client.ok({"cmd": "inject_input", "kind": "modstate", "mod": "none"})
        assert top_state(client) == "BriefingState", \
            f"ctrl-B should push a BriefingState on the client, stack={states(client)}"

        # POSITIVE, fixture-independent proof that the generic fallback was NOT
        # taken. The coop hook logs the resolution outcome of every BriefingState
        # built inside a coop battle - VANILLA (this machine re-derived it),
        # CARRIED (from battle_offer, for a machine with no Craft/Ufo) or NONE
        # (the generic "should never happen" branch). The client builds exactly
        # one BriefingState here, via ctrl-B, so the last line is that one.
        resolved = grep(client_dir, "[coop-handshake] BriefingState deployment:")
        assert resolved, (
            "client log has no '[coop-handshake] BriefingState deployment:' line - the "
            "W1-P2 resolution hook at BriefingState.cpp did not run for the ctrl-B "
            "briefing (SS2.W1)")
        print("CLIENT LOG:", resolved[-1])
        assert "deployment: NONE" not in resolved[-1], (
            "the ctrl-B briefing on the client fell through to the generic 'should never "
            "happen' branch (BriefingState.cpp:104-108) - the live trap this packet "
            f"kills (SS2.W1): {resolved[-1]}")

        raw, texts = widget_texts(client)
        joined = " | ".join(texts)
        assert any(cb["strTarget"] in t for t in texts), (
            f"the ctrl-B briefing does not render the carried mission target "
            f"{cb['strTarget']!r}; widget texts = {joined}")
        assert any(cb["strCraftOrBase"] in t for t in texts), (
            f"the ctrl-B briefing does not render the carried craft label "
            f"{cb['strCraftOrBase']!r}; widget texts = {joined}")
        print(f"PASS ctrl-B on the client: BriefingState renders the CARRIED labels "
              f"({joined})")

        # === 5. WR-24: the battlescape survives the briefing round trip ======
        client.ok({"cmd": "close_briefing"})
        client.wait_for("client back on battlescape",
                        lambda: (top_state(client) == "BattlescapeState") or None, timeout=15)
        time.sleep(1)
        pal_after = palette_of(client, "BattlescapeState")
        assert pal_after == pal_before, (
            "the client's BattlescapeState palette CHANGED across the ctrl-B briefing "
            "(BriefingState swaps to PAL_GEOSCAPE and the GEOSCAPE resolution in its "
            "ctor, BriefingState.cpp:58-60) - WR-24's battlePaletteSource trap shape")
        cb2 = labels(client)
        assert (cb2.get("mapFingerprint"), cb2.get("mapObjTiles"), cb2.get("mapSizeXYZ")) \
            == map_before, (
            f"the client's map fingerprint changed across the ctrl-B briefing: "
            f"before={map_before} after="
            f"{(cb2.get('mapFingerprint'), cb2.get('mapObjTiles'), cb2.get('mapSizeXYZ'))}")
        session.assert_hash_clean(host, client, full=True,
                                  what="after the client's ctrl-B briefing round trip")
        print("PASS WR-24: client battlescape intact after the ctrl-B briefing "
              "(same top state, same palette, same map, all buckets still EQUAL)")

        print("ALL W1-P2 MISSION-LABEL TESTS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
