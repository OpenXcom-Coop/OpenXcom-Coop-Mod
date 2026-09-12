"""W1-P13a SPEC 9 (REV E.48 SS.B.3/B.4) - repro_atom_side_transition.py: the
HAZARD-FREE full turn-cycle end to end - `side_transition`/`side_begin`
applied on the CLIENT for the first time (the engine half landed in commit
0b33e72c2, "feat(coop): engine half of side_transition + side_begin
(W1-P13a)"; this file is this packet's own tool-half acceptance).

AI-NEUTRAL PINNING (WV-D45/IR2-9, REV E.48 SS.B.2/D49). Every unit no human
seat commands is pinned to 0 TU via session.pin_ai_neutral() immediately
after drive_to_battlescape() - wave 1 streams no alien action at all (walk/
turn ship in SPEC 12, shots are out of wave entirely), so an un-pinned
non-player unit that acted during the alien phase would desync the client
the instant it moved. The mission is pinned to STR_SMALL_SCOUT (no
civilians, no terror units - exactly one alien on every seed, M9a-3).

B.3/D58 POSTPONEMENT (owner-ruled 2026-09-11, REV E.48 SS.B.3). SPEC 9 (f)
test 1 originally specified a burning/smoking-map turn cycle (tile decay,
unit fire damage, stun recovery). That is POSTPONED to the shot wave: wave 1
streams no shot to the client, so the only in-wave way to ignite a map on
both machines would be a harness-only seeded-hazard lever, not the vanilla
path the owner wants driving that test (D50/D58). This file is therefore the
HAZARD-FREE cycle test: SS.B.2's pin, ONE host END TURN press, ONE full
cycle (three side_transitions), and every SPEC 9 (f) test-1 assertion EXCEPT
the tile-decay/fire-damage/stun-recovery legs. `perTile` is asserted empty
on every transition instead (non-vacuous: the host must not emit tiles that
did not change - see L3 below for exactly how that is checked given this
test surface's limits) and the terrain tripwire (L9) stays in place exactly
as SPEC 9 (f) writes it - it costs nothing and cannot fire without fire, and
per D50(iii a) the burnout-terrain gap rides the same shot-wave OUT-OF-WAVE
row. The perTile smoke/fire and perUnit fire/stun/health APPLY paths ship in
SPEC 9 as specified but UNEXERCISED in wave 1 (documented here, not silently
dropped).

D64 (REV E.49 E49.2.1) COVERAGE NOTE: the fire/smoke-unchanged check at L3
below is the outcome assertion of record for tiles, REPLACING B.3's
`perTile == []` wording above - "the host emits only tiles that changed"
is a sender-discipline property no outcome check can reach, and stays
UNPROVEN in wave 1.

Cites WV-D45, WV-D51, WR-18, D-5, D48, D49, D58.

Run:  python tools/coop_test/repro_atom_side_transition.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import (battle_state, event_state, event_log, pin_ai_neutral,
                      assert_hash_clean, assert_turret_parity)

import yaml

FACTION_PLAYER = 0
MISSION = "STR_SMALL_SCOUT"
SCRIPT_RNG_MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "mods", "Coop_ScriptRng_Test")

STR_TERRAIN_STOP = (
    "terrain destroyed at the side boundary (fire burnout, "
    "SavedBattleGame.cpp:2489-2516) - side_transition's frozen perTile "
    "carries no terrain field")


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


# ----- fixture bring-up (inline copy, test_rw_faction_setup.py / repro_atom_walk.py
# precedent - every coop test in this tree carries its own copy of the skirmish
# lobby dance rather than sharing one, per those files' own stated convention).

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


def dismiss_next_turn_if_present(gc):
    """If `gc`'s TOP state is a NextTurnState, close it via the REAL
    NextTurnState::close() path (TestServer `close_nextturn`, machine-
    agnostic - TestServer.cpp:7754/F140) rather than dismiss_popup (which
    only pops the state WITHOUT running close()). Returns whether one was
    found (and closed); never raises on absence."""
    lw = gc.cmd({"cmd": "list_widgets"})
    if "NextTurnState" not in lw.get("state", ""):
        return False
    r = gc.cmd({"cmd": "close_nextturn"})
    assert r.get("ok"), (
        f"close_nextturn failed on a machine whose list_widgets just reported "
        f"NextTurnState on top: {r}")
    return True


def drive_full_cycle(host, client, turn0, timeout=60, capture_l10=True):
    """L1 driver. Presses nothing itself (the caller already pressed END
    TURN) - polls both machines to completion, TOLERATING and DISMISSING:

      * the HOST's OWN NextTurnState pushes. Vanilla always pushes one per
        non-neutral side change (M9a-5); `Options::skipNextTurnScreen`
        defaults to false (Options.cpp), so nothing auto-closes it via its
        NEXT_TURN_DELAY timer - the host cycle would otherwise stall forever
        waiting for a human "OK" click a harness never sends.
      * the CLIENT's OWN NextTurnState pushes (REV E.1 S-3) - this is the
        FIRST packet that ever makes a client change sides, so this file is
        also the first fixture to ever observe one. The FIRST one seen is
        used for L10's dismiss-is-hash-neutral proof (when `capture_l10` is
        True); any later one in the same cycle is just swept out of the way
        the same way the host's are.

    `capture_l10=False` (used ONLY by run_script_rng_fixture's L11 boot):
    dismiss NextTurnStates on both machines WITHOUT any intermediate
    hash_now check. The ScriptRng mod's newTurnUnit hook fires - and can
    diverge saveBlob - starting at the FIRST side_transition already
    (script_rng.rul: "fires on EVERY unit at every side close"), so this
    driver's OWN L10 hash-clean assertion would raise a generic
    HASH MISMATCH from inside assert_hash_clean before L11's own dedicated
    STOP-IF block (which captures the per-unit COOP_RNG_R/COOP_RNG_C tag
    dump, per WV-D77) ever got to run. L11 does its own, single, post-cycle
    hash_now comparison instead - this is a TEST-PLUMBING fix (which hash
    check runs where), not a product fix, and does not touch what is
    asserted or when the STOP-IF fires. D63 closes the mechanical reason
    cited above (the client now receives the host's scriptTags on the same
    side_transition envelope, so saveBlob no longer diverges from the first
    one) - L11 keeps this single, post-cycle check unchanged regardless,
    because that is the invariant REV E.49 E49.1 names.

    Returns (client_saw_next_turn_state: bool, l10_evidence: (pre_h, post_h)
    or None - always None when capture_l10 is False). Raises TimeoutError if
    the full cycle never completes on both machines."""
    deadline = time.time() + timeout
    client_seen = False
    l10_evidence = None
    while time.time() < deadline:
        dismiss_next_turn_if_present(host)  # M9a-5: never stall the host on its own banner

        if top_state(client) and "NextTurnState" in top_state(client):
            if not capture_l10:
                dismiss_next_turn_if_present(client)
            elif l10_evidence is None:
                # L10 / REV E.1 S-3: the FIRST client NextTurnState. Prove
                # dismissing it is presentation-only (WV-D51): hash-neutral,
                # and the battle does not end.
                # D64 (E49.2.1/E49.2.3): nine-bucket EQUAL boundary check.
                pre, _ = assert_hash_clean(host, client, full=True,
                                            what="L10 pre-close_nextturn(client)")
                r = client.cmd({"cmd": "close_nextturn"})
                assert r.get("ok"), f"L10: close_nextturn failed on client: {r}"
                # D64 (E49.2.1/E49.2.3): nine-bucket EQUAL boundary check.
                post, _ = assert_hash_clean(host, client, full=True,
                                             what="L10 post-close_nextturn(client)")
                cs = battle_state(client)
                assert cs.get("inBattle"), (
                    "L10: the client's battle ended after dismissing its own "
                    f"NextTurnState (WV-D51 requires this to be presentation-"
                    f"only): {cs}")
                client_seen = True
                l10_evidence = (pre, post)
                print("[L10] client showed a NextTurnState at the boundary; "
                      "dismissed via close_nextturn - hash_now full stayed "
                      "EQUAL both before and after, inBattle stayed true")
            else:
                dismiss_next_turn_if_present(client)

        hs = battle_state(host)
        cs = battle_state(client)
        if (hs.get("side") == FACTION_PLAYER and hs.get("turn", -1) >= turn0 + 1
                and cs.get("side") == FACTION_PLAYER and cs.get("turn", -1) >= turn0 + 1):
            return client_seen, l10_evidence
        time.sleep(0.05)
    raise TimeoutError(
        f"repro_atom_side_transition: full cycle did not complete within "
        f"{timeout}s (M9a's own bar) - host={battle_state(host)} "
        f"client={battle_state(client)}")


def _read_script_rng_tags(path):
    """D63/E49.1 acceptance reader: called on BOTH machines on EVERY run of
    run_script_rng_fixture's L11 leg (no longer a failure-path-only WV-D77
    capture helper - the green path now asserts on what this returns).

    Reads a `save_game` dump's battleGame.units[].tags for the ScriptRng
    mod's two tags. Grounded directly in the C++ writers (not guessed):
    BattleUnit::save() calls `_scriptValues.save(writer, shared)`
    (BattleUnit.cpp), whose default nodeName is "tags" (Script.h
    ScriptValues::save); SavedBattleGame::save() writes the unit list under
    "units" (`writer.write("units", _units, ...)`, SavedBattleGame.cpp);
    SavedGame::save() nests the whole in-progress battle under "battleGame"
    (`_battleGame->save(writer["battleGame"])`, SavedGame.cpp). The file
    itself is TWO YAML documents (header, then the full save) - same
    `yaml.safe_load_all()` shape test_save_upgrade.py's own two_docs() uses.

    Returns {unit_id: {"COOP_RNG_R": v, "COOP_RNG_C": v}} for every unit
    that carries either tag."""
    with open(path, "r", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f.read()))
    full = docs[1] if len(docs) > 1 else (docs[0] if docs else {})
    battle = (full or {}).get("battleGame") or {}
    out = {}
    for u in battle.get("units", []) or []:
        tags = u.get("tags") or {}
        picked = {k: v for k, v in tags.items() if k in ("COOP_RNG_R", "COOP_RNG_C")}
        if picked:
            out[u.get("id")] = picked
    return out


def run_hazard_free_cycle():
    """The main hazard-free cycle boot: SPEC 9 (f) test 1 minus the legs
    B.3 postponed. Returns nothing; raises on any failed assertion or
    STOP-IF."""
    port = "48120"
    host_dir = make_user_dir("repro_atom_side_transition_host")
    client_dir = make_user_dir("repro_atom_side_transition_client")
    host = GameClient("host", 49500, host_dir)
    client = GameClient("client", 49501, client_dir)
    seated = {}
    try:
        bring_up_lobby(host, client, port)
        session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2)

        pinned = pin_ai_neutral(host, client, tag="side_transition")
        assert len(pinned) > 0, (
            f"pin_ai_neutral pinned ZERO NONE-seat non-player units on a "
            f"CLASSIC {MISSION} boot - the premise (a unit for the pin to "
            "act on) is unexercised (M9a-3)")

        # ----- L1: the cycle happens on BOTH machines -----
        hs0 = battle_state(host)
        cs0 = battle_state(client)
        turn0 = hs0["turn"]
        assert hs0["side"] == FACTION_PLAYER and cs0["side"] == FACTION_PLAYER, (
            f"fixture premise broke: expected both machines to start on the "
            f"player side, host side={hs0['side']} client side={cs0['side']}")
        print(f"[L1] before: host turn={hs0['turn']} side={hs0['side']}, "
              f"client turn={cs0['turn']} side={cs0['side']}")

        # M9a-5: terrain (L9) is a HOST-only snapshot taken here, before the
        # cycle, and compared after settle below.
        pre_terrain = host.cmd({"cmd": "hash_now", "buckets": ["terrain"]})
        assert pre_terrain.get("ok"), f"hash_now(terrain) failed pre-cycle: {pre_terrain}"
        # L3 proxy (see below for the full rationale): the host's fire/smoke
        # buckets, snapshotted before the cycle.
        pre_hazard = host.cmd({"cmd": "hash_now", "buckets": ["fire", "smoke"]})
        assert pre_hazard.get("ok"), f"hash_now(fire,smoke) failed pre-cycle: {pre_hazard}"

        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        client_saw_nts, _l10_evidence = drive_full_cycle(host, client, turn0, timeout=60)
        assert client_saw_nts, (
            "REV E.1 S-3: the CLIENT never showed a NextTurnState during the "
            "full cycle - this is the FIRST packet that makes a client change "
            "sides at all, so it must push one (mirroring "
            "BattlescapeGame.cpp's own vanilla trigger client-side)")

        hs1 = battle_state(host)
        cs1 = battle_state(client)
        print(f"[L1] after:  host turn={hs1['turn']} side={hs1['side']}, "
              f"client turn={cs1['turn']} side={cs1['side']}")
        # M9a-6's own negative control, reproduced here: on the pre-commit-0
        # build the client stayed at (side 0, turn 1) forever while the host
        # reached (side 0, turn 2). This assertion is exactly what turns that
        # red green.
        assert cs1["turn"] == turn0 + 1 and cs1["side"] == FACTION_PLAYER, (
            f"CLIENT did not complete the full cycle: before turn={turn0}, "
            f"after client={cs1}")
        assert hs1["turn"] == turn0 + 1 and hs1["side"] == FACTION_PLAYER, (
            f"HOST did not complete the full cycle: before turn={turn0}, "
            f"after host={hs1}")

        session.wait_host_idle(host, client, timeout=30)  # settle before any hash read

        # ----- L2: exactly THREE side_transition envelopes, in seq order -----
        # CoopEventLog::Entry (BattlePump.h) is a fixed POD ring slot carrying
        # ONLY {seq, actionId, kind, hasHash} - no payload field, so
        # `newSide` cannot be read back from this introspection surface (this
        # was verified by reading the struct, not assumed). This leg proves
        # the COUNT and the SEQ ORDER from event_log directly, and cites the
        # CODE-PROVEN invariant for the newSide progression itself (M9a-4,
        # verified at the tip): SavedBattleGame.cpp's `_turn++` lives ONLY in
        # the FACTION_NEUTRAL branch and HOSTILE->NEUTRAL is unconditional
        # (the skip-neutral branch is commented out there), so the ONLY path
        # from (turn T, side player) to (turn T+1, side player) is
        # PLAYER -> HOSTILE -> NEUTRAL -> PLAYER, i.e. newSide = hostile,
        # neutral, player in that order for these three envelopes - a fact
        # about vanilla's own algorithm, not independently re-derivable from
        # this test surface, and not claimed as directly read back here.
        cevs = event_log(client, tail=256)
        boundary = [e for e in cevs if e.get("actionId") == 0
                    and e.get("kind") in ("side_transition", "side_begin")]
        transitions = [e for e in boundary if e["kind"] == "side_transition"]
        begins = [e for e in boundary if e["kind"] == "side_begin"]
        assert len(transitions) == 3, (
            f"expected exactly 3 side_transition envelopes for one full cycle "
            f"(M9a-4: HOSTILE->NEUTRAL is unconditional), got "
            f"{len(transitions)}: {transitions}")
        assert len(begins) == 3, (
            f"expected exactly 3 side_begin envelopes (one per side_transition, "
            f"emitted from the same guarded hook), got {len(begins)}: {begins}")
        seqs = [e["seq"] for e in boundary]
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), (
            f"boundary envelopes are not strictly seq-ordered: {boundary}")
        # D64 (E49.2.3): h present on every side_transition entry.
        for e in transitions:
            assert e.get("h"), (
                f"side_transition seq={e['seq']} carried an EMPTY h "
                f"(SS2.8/RB-D14 requires the boundary full sweep): {e}")
        print(f"[L2] client event_log: {len(transitions)} side_transition + "
              f"{len(begins)} side_begin envelope(s), seq-ordered: "
              f"{[(e['kind'], e['seq']) for e in boundary]}")

        # ----- L3: perTile == [] proxy (non-vacuous: fire/smoke UNCHANGED) -----
        # As L2 explains, CoopEventLog carries no payload, so this file
        # cannot read the wire's `perTile` array back directly. The
        # constructive equivalent for THIS HAZARD-FREE fixture: if no tile's
        # smoke/fire value changed anywhere on the map across the whole
        # cycle, the host had nothing to restate, so `perTile` was empty on
        # every transition by construction. A bug that spuriously wrote
        # fire/smoke to any tile (e.g. a stray ignite()) would flip these
        # bucket hashes - this is disclosed as a PROXY, not claimed as a
        # literal per-envelope read of the frozen wire field.
        post_hazard = host.cmd({"cmd": "hash_now", "buckets": ["fire", "smoke"]})
        assert post_hazard.get("ok"), f"hash_now(fire,smoke) failed post-cycle: {post_hazard}"
        # D64 (E49.2.1): host fire/smoke buckets unchanged - assertion of
        # record for tiles, replacing B.3's `perTile == []` wording.
        assert pre_hazard["h"] == post_hazard["h"], (
            f"L3: the host's fire/smoke buckets changed across a HAZARD-FREE "
            f"cycle - pre={pre_hazard['h']} post={post_hazard['h']} - "
            "something restated a tile hazard this fixture never introduced")
        print(f"[L3] perTile==[] proxy OK: host fire/smoke buckets unchanged "
              f"across the cycle ({post_hazard['h']})")

        # ----- L4: nine buckets EQUAL at the boundary -----
        # D64 (E49.2.1/E49.2.3): nine-bucket EQUAL boundary check.
        hh, ch = assert_hash_clean(host, client, full=True, what="L4 post-cycle boundary")
        print(f"[L4] all {len(hh)} buckets EQUAL after the boundary: {sorted(hh)}")

        # ----- L5: the client's own hash compare recorded no mismatch -----
        # D64 (E49.2.3): the client's own verify did not fire.
        es = event_state(client)
        assert es.get("desyncSeen") is False, (
            f"L5: the client's desyncSeen flag is not False after a clean "
            f"boundary sweep - a hash mismatch was recorded: {es}")
        print("[L5] client event_state.desyncSeen == False throughout")

        # ----- L6: the exercised perUnit legs -----
        hu = {u["id"]: u for u in hs1["units"]}
        cu = {u["id"]: u for u in cs1["units"]}
        assert set(hu) == set(cu), (
            f"unit id sets differ after the cycle: host={sorted(hu)} "
            f"client={sorted(cu)}")
        player_tu_energy = {}
        for uid, hunit in hu.items():
            cunit = cu[uid]
            if hunit.get("isOut"):
                continue
            for field in ("status", "kneeled", "faction", "mindControllerId"):
                assert hunit.get(field) == cunit.get(field), (
                    f"unit {uid} field '{field}' differs after the cycle: "
                    f"host={hunit.get(field)} client={cunit.get(field)}")
            if hunit.get("faction") == FACTION_PLAYER:
                player_tu_energy[uid] = (hunit.get("tu"), hunit.get("energy"))
                assert hunit.get("tu", 0) > 0, (
                    f"player-side unit {uid} tu was not restored by the new "
                    f"side's turn: {hunit.get('tu')}")
                assert hunit.get("energy", 0) > 0, (
                    f"player-side unit {uid} energy was not restored by the "
                    f"new side's turn: {hunit.get('energy')}")
        # wounds: NOT a battle_state field (F134) - getFatalWound() for every
        # BODYPART_MAX part lives INSIDE the unitsStats hash bucket
        # (SharedEcon.cpp), so L4's nine-bucket equality above IS the wounds
        # assertion; no probe field is added here.
        print(f"[L6] perUnit legs OK: status/kneeled/faction/mcId equal for "
              f"{len(hu)} unit(s); player-side tu/energy restored: "
              f"{player_tu_energy}")

        # ----- L7: the turret-reset loop reproduced -----
        assert_turret_parity(host, client, what="L7 post-cycle boundary")
        print("[L7] directionTurret parity OK for every shared unit")

        # ----- L8: newTurn/newSide applied -----
        assert hs1["turn"] == cs1["turn"] and hs1["side"] == cs1["side"], (
            f"L8: turn/side not equal post-cycle: host=({hs1['turn']},"
            f"{hs1['side']}) client=({cs1['turn']},{cs1['side']})")
        print(f"[L8] newTurn/newSide applied equally: turn={hs1['turn']} "
              f"side={hs1['side']}")

        # ----- L9: the terrain tripwire -----
        post_terrain = host.cmd({"cmd": "hash_now", "buckets": ["terrain"]})
        assert post_terrain.get("ok"), f"hash_now(terrain) failed post-cycle: {post_terrain}"
        if pre_terrain["h"] != post_terrain["h"]:
            raise AssertionError(STR_TERRAIN_STOP)
        print(f"[L9] terrain tripwire OK: host terrain bucket unchanged "
              f"({post_terrain['h']})")

        print("PASS: repro_atom_side_transition hazard-free cycle "
              f"({len(pinned)} pinned unit(s), 3 side_transitions, 9/9 "
              "buckets equal, client NextTurnState observed and dismissed "
              "hash-neutrally)")
    finally:
        host.shutdown()
        client.shutdown()


def run_script_rng_fixture():
    """SPEC 9 (f) test 1's L11: the Coop_ScriptRng_Test scriptTags parity
    leg (D63/E49.1 - this is now the acceptance leg, not a KNOWN-GAP
    capture). A SECOND boot, same pin, same one cycle, with
    tools/coop_test/mods/Coop_ScriptRng_Test loaded on BOTH machines
    (make_user_dir's `mods=` param - both machines need the SAME mods or
    their rulesets diverge, per that helper's own docstring).

    REV E.49 E49.1 (D63 = (a)), the invariant this leg asserts: after ONE
    full cycle on this fixture, the saveBlob bucket is EQUAL AND the
    per-unit COOP_RNG_R/COOP_RNG_C maps read by `_read_script_rng_tags` are
    EQUAL host == client for every unit. `BattleUnit::coopSetScriptValues`
    (landed in commit ecf58062f, "feat(coop): side_transition perUnit
    carries scriptTags (D63)") applies the host's freshly-rolled tags to the
    client from side_transition's new perUnit `scriptTags` field as an
    absolute overwrite, so the mod's own newTurnUnit hook
    (script_rng.rul, which fires on the HOST for every unit at every side
    close and stores fresh COOP_RNG_R/COOP_RNG_C values) now reaches the
    client on the wire.

    F147: this fixture was built for PRD-P3 GAP-10 to prove a PARALLEL
    client's own script draws match the host's by seed replay; under the
    rewrite's thin client the client is not supposed to draw at all, so the
    leg now proves a different and correct property - the client's tags
    EQUAL the host's after a boundary."""
    port = "48121"
    host_dir = make_user_dir("repro_atom_side_transition_rng_host", mods=[SCRIPT_RNG_MOD])
    client_dir = make_user_dir("repro_atom_side_transition_rng_client", mods=[SCRIPT_RNG_MOD])
    host = GameClient("host", 49510, host_dir)
    client = GameClient("client", 49511, client_dir)
    seated = {}
    try:
        bring_up_lobby(host, client, port)
        session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2)

        pin_ai_neutral(host, client, tag="side_transition-rng")

        hs0 = battle_state(host)
        turn0 = hs0["turn"]
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        drive_full_cycle(host, client, turn0, timeout=60, capture_l10=False)
        session.wait_host_idle(host, client, timeout=30)

        hr = host.cmd({"cmd": "hash_now", "full": True})
        cr = client.cmd({"cmd": "hash_now", "full": True})
        assert hr.get("ok") and cr.get("ok"), f"hash_now failed: host={hr} client={cr}"
        hh, ch = hr["h"], cr["h"]
        mismatched = {k: (hh[k], ch.get(k)) for k in hh if hh.get(k) != ch.get(k)}

        # D63/E49.1: read the per-unit COOP_RNG_R/COOP_RNG_C tag maps on BOTH
        # machines UNCONDITIONALLY - this is the acceptance read now, not a
        # failure-path capture, so a parse failure here is itself a RED.
        tag_maps = {}
        for gc, role in ((host, "host"), (client, "client")):
            fname = f"coop_rng_probe_{role}.sav"
            r = gc.cmd({"cmd": "save_game", "file": fname})
            assert r.get("ok"), f"save_game failed on {role} (L11 acceptance read): {r}"
            path = os.path.join(gc.user_dir, "xcom1", fname)
            tag_maps[role] = _read_script_rng_tags(path)
            print(f"[L11 MAP] {role} COOP_RNG_R/COOP_RNG_C per unit "
                  f"(from {path}): {tag_maps[role]}")

        # D63/E49.1 named assertion: all nine hash_now buckets, saveBlob
        # included, are EQUAL after the cycle - the host's freshly-rolled
        # tags now reach the client on the wire, so this is no longer an
        # expected divergence.
        assert not mismatched, (
            "repro_atom_side_transition L11 (D63/E49.1): bucket(s) "
            f"mismatched after one hazard-free ScriptRng cycle: "
            f"{sorted(mismatched)} - host={hh} client={ch}; per-unit tag "
            f"maps: host={tag_maps['host']} client={tag_maps['client']}")

        # D63/E49.1 named assertion: the per-unit COOP_RNG_R/COOP_RNG_C maps
        # themselves are EQUAL host == client for every unit - the direct
        # read, not implied by the bucket-hash check above.
        tag_diff = {u: (tag_maps["host"].get(u), tag_maps["client"].get(u))
                    for u in set(tag_maps["host"]) | set(tag_maps["client"])
                    if tag_maps["host"].get(u) != tag_maps["client"].get(u)}
        assert tag_maps["host"] == tag_maps["client"], (
            "repro_atom_side_transition L11 (D63/E49.1): per-unit "
            f"COOP_RNG_R/COOP_RNG_C maps differ host vs client: {tag_diff} "
            f"- host={tag_maps['host']} client={tag_maps['client']}")

        print(f"[L11] Coop_ScriptRng_Test scriptTags parity OK: "
              f"{len(tag_maps['host'])} unit(s) carry tags, all {len(hh)} "
              f"buckets EQUAL ({sorted(hh)}), per-unit tag maps EQUAL host "
              "== client")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    run_hazard_free_cycle()
    run_script_rng_fixture()


if __name__ == "__main__":
    try:
        main()
        print("ALL SPEC 9 repro_atom_side_transition TESTS PASSED")
    except session.KnownFlake as e:
        session.print_known_flake_banner("repro_atom_side_transition", e.tracking, str(e))
        print(f"\nrepro_atom_side_transition: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(2)
    except AssertionError as e:
        print(f"\nrepro_atom_side_transition: FAIL\nAssertionError: {e}")
        sys.exit(2)
    except TimeoutError as e:
        print(f"\nrepro_atom_side_transition: FAIL\nTimeoutError: {e}")
        sys.exit(2)
