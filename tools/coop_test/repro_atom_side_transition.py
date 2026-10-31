"""repro_atom_side_transition.py: the HAZARD-FREE full turn cycle end to end,
with `side_transition` / `side_begin` applied on the CLIENT.

AI-NEUTRAL PINNING. Every unit no human seat commands is pinned to 0 TU via
session.pin_ai_neutral() right after drive_to_battlescape(), so no
non-player unit acts during the alien phase and the cycle is a pure side
change. The mission is STR_SMALL_SCOUT (no civilians, no terror units -
exactly one alien on every seed).

HAZARD-FREE. The cycle runs on a map with no fire or smoke, so it has no
tile decay, unit fire damage or stun recovery: igniting a map on both
machines here would need a harness-only seeded-hazard hook, not the vanilla
path. This file runs the pin, ONE host END TURN press, ONE full cycle (three
side_transitions), and checks everything EXCEPT the tile-decay /
fire-damage / stun-recovery legs. In their place, `perTile` must be empty on
every transition (non-vacuous: the host must not emit tiles that did not
change - see hazard_unchanged below for exactly how that is checked given this test
surface's limits), and the terrain tripwire (terrain_tripwire) stays in place: it costs
nothing and cannot fire without fire. The perTile smoke/fire and perUnit
fire/stun/health APPLY paths are not exercised here.

COVERAGE NOTE: the fire/smoke-unchanged check at hazard_unchanged below is the outcome
check for tiles, in place of a direct `perTile == []` read - "the host
emits only tiles that changed" is a sender-side property no outcome check
can reach, and this file does not prove it.

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

STR_TERRAIN_TRIPWIRE = (
    "terrain changed at the side boundary in this hazard-free cycle (fire burnout, "
    "SavedBattleGame::prepareNewTurn) - side_transition's frozen perTile carries no "
    "terrain field; the whole-battle delta carries tile changes to the second player")


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


# ----- fixture bring-up (inline copy, test_faction_setup.py / repro_atom_walk.py
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
    agnostic - TestServer.cpp:7754) rather than dismiss_popup (which
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


def drive_full_cycle(host, client, turn0, timeout=60, check_client_screen=True):
    """full_cycle driver. Presses nothing itself (the caller already pressed END
    TURN) - polls both machines to completion, TOLERATING and DISMISSING:

      * the HOST's OWN NextTurnState pushes. Vanilla always pushes one per
        non-neutral side change; `Options::skipNextTurnScreen` defaults to
        false (Options.cpp), so nothing auto-closes it via its
        NEXT_TURN_DELAY timer - the host cycle would otherwise stall forever
        waiting for a human "OK" click a harness never sends.
      * the CLIENT's OWN NextTurnState pushes. The FIRST one seen is used
        for client_turn_screen's dismiss-is-hash-neutral proof (when `check_client_screen`
        is True); any later one in the same cycle is just swept out of the
        way the same way the host's are.

    `check_client_screen=False` (used by run_script_rng_fixture's script_tags boot
    and by test_side_driver_race.py): dismiss NextTurnStates on both
    machines WITHOUT any intermediate hash_now check. The ScriptRng mod's
    newTurnUnit hook fires on every unit at every side close (script_rng.rul),
    so a hash check inside this driver would raise a generic HASH MISMATCH
    from inside assert_hash_clean before the script_tags check (which prints the
    per-unit COOP_RNG_R/COOP_RNG_C tag dump) got to run. script_tags does its own,
    single, post-cycle hash_now comparison instead; this only moves which
    hash check runs where, not what is asserted. The client receives the
    host's scriptTags on the same side_transition envelope, so saveBlob no
    longer diverges; script_tags keeps its single post-cycle check as the check of
    record for that parity.

    Returns (client_saw_next_turn_state: bool, screen_evidence: (pre_h, post_h)
    or None - always None when check_client_screen is False). Raises
    TimeoutError if the full cycle never completes on both machines."""
    deadline = time.time() + timeout
    client_seen = False
    screen_evidence = None
    while time.time() < deadline:
        # read both sides FIRST, then close (repro_atom_side_begin.drive_side_change has the
        # reason): once both reads show the new side, every NextTurnState of that change is up for the close pass,
        # which closes every stacked one once and stops when a close pops nothing (a held turn screen): no retry.
        hs = battle_state(host)
        cs = battle_state(client)
        done = (hs.get("side") == FACTION_PLAYER and hs.get("turn", -1) >= turn0 + 1
                and cs.get("side") == FACTION_PLAYER and cs.get("turn", -1) >= turn0 + 1)
        depth = None  # never stall the host on its own banner
        while True:
            st = host.cmd({"cmd": "get_state"}).get("states") or []
            if not st or "NextTurnState" not in st[-1] or (depth is not None and len(st) >= depth):
                break
            depth = len(st)
            host.cmd({"cmd": "close_nextturn"})

        if top_state(client) and "NextTurnState" in top_state(client):
            if not check_client_screen:
                dismiss_next_turn_if_present(client)
            elif screen_evidence is None:
                # client_turn_screen: the FIRST client NextTurnState. Prove
                # dismissing it is presentation-only: hash-neutral,
                # and the battle does not end.
                # Nine-bucket EQUAL boundary check.
                pre, _ = assert_hash_clean(host, client, full=True,
                                            what="client_turn_screen pre-close_nextturn(client)")
                r = client.cmd({"cmd": "close_nextturn"})
                assert r.get("ok"), f"client_turn_screen: close_nextturn failed on client: {r}"
                # Nine-bucket EQUAL boundary check.
                post, _ = assert_hash_clean(host, client, full=True,
                                             what="client_turn_screen post-close_nextturn(client)")
                cs = battle_state(client)
                assert cs.get("inBattle"), (
                    "client_turn_screen: the client's battle ended after dismissing its own "
                    f"NextTurnState (dismissing it must be presentation-"
                    f"only): {cs}")
                client_seen = True
                screen_evidence = (pre, post)
                print("[client_turn_screen] client showed a NextTurnState at the boundary; "
                      "dismissed via close_nextturn - hash_now full stayed "
                      "EQUAL both before and after, inBattle stayed true")
            else:
                dismiss_next_turn_if_present(client)

        if screen_evidence is not None or not check_client_screen:  # never close the client's first screen before client_turn_screen proves it
            depth = None  # a client NextTurnState stacked under the one just closed
            while True:
                st = client.cmd({"cmd": "get_state"}).get("states") or []
                if not st or "NextTurnState" not in st[-1] or (depth is not None and len(st) >= depth):
                    break
                depth = len(st)
                client.cmd({"cmd": "close_nextturn"})
        if done:
            return client_seen, screen_evidence
        time.sleep(0.05)
    raise TimeoutError(
        f"repro_atom_side_transition: full cycle did not complete within "
        f"{timeout}s - host={battle_state(host)} "
        f"client={battle_state(client)}")


def _read_script_rng_tags(path):
    """Tag reader of the script_tags check: called on BOTH machines on EVERY run of
    run_script_rng_fixture's script_tags leg, which asserts on what this returns.

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
    """The main hazard-free cycle boot: every check of the cycle except the
    hazard legs (see the module docstring). Returns nothing; raises on any
    failed assertion or tripwire."""
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
            "act on) is unexercised")

        # ----- full_cycle: the cycle happens on BOTH machines -----
        hs0 = battle_state(host)
        cs0 = battle_state(client)
        turn0 = hs0["turn"]
        assert hs0["side"] == FACTION_PLAYER and cs0["side"] == FACTION_PLAYER, (
            f"fixture premise broke: expected both machines to start on the "
            f"player side, host side={hs0['side']} client side={cs0['side']}")
        print(f"[full_cycle] before: host turn={hs0['turn']} side={hs0['side']}, "
              f"client turn={cs0['turn']} side={cs0['side']}")

        # terrain (terrain_tripwire) is a HOST-only snapshot taken here, before the
        # cycle, and compared after settle below.
        pre_terrain = host.cmd({"cmd": "hash_now", "buckets": ["terrain"]})
        assert pre_terrain.get("ok"), f"hash_now(terrain) failed pre-cycle: {pre_terrain}"
        # hazard_unchanged proxy (see below for the full rationale): the host's fire/smoke
        # buckets, snapshotted before the cycle.
        pre_hazard = host.cmd({"cmd": "hash_now", "buckets": ["fire", "smoke"]})
        assert pre_hazard.get("ok"), f"hash_now(fire,smoke) failed pre-cycle: {pre_hazard}"

        # `needed` is the LIVE-seat count - this classic fixture has TWO live
        # seats, so a lone host press cannot close the side. The client arms
        # through its OWN real button first, and this driver waits for the
        # HOST's tally text to reach the rendered STR_COOP_END_TURN_TALLY for
        # count 1 of needed 2 before the host's press - a bounded wait_for on
        # a surface, not an attempt loop.
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def _host_shows_1_of_2():
            return True if battle_state(host).get("coopEndTurnText") == "END TURN 1/2" else None
        host.wait_for("host paints END TURN 1/2 after the client's arm",
                      _host_shows_1_of_2, timeout=15)

        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        client_saw_nts, _screen_evidence = drive_full_cycle(host, client, turn0, timeout=60)
        assert client_saw_nts, (
            "the CLIENT never showed a NextTurnState during the full cycle - "
            "a client that changes sides must push one (mirroring "
            "BattlescapeGame.cpp's own vanilla trigger client-side)")

        hs1 = battle_state(host)
        cs1 = battle_state(client)
        print(f"[full_cycle] after:  host turn={hs1['turn']} side={hs1['side']}, "
              f"client turn={cs1['turn']} side={cs1['side']}")
        # A client that does not apply side_transition stays at (side 0,
        # turn 1) forever while the host reaches (side 0, turn 2). This
        # assertion catches exactly that.
        assert cs1["turn"] == turn0 + 1 and cs1["side"] == FACTION_PLAYER, (
            f"CLIENT did not complete the full cycle: before turn={turn0}, "
            f"after client={cs1}")
        assert hs1["turn"] == turn0 + 1 and hs1["side"] == FACTION_PLAYER, (
            f"HOST did not complete the full cycle: before turn={turn0}, "
            f"after host={hs1}")

        session.wait_host_idle(host, client, timeout=30)  # settle before any hash read

        # ----- envelopes: exactly THREE side_transition envelopes, in seq order -----
        # CoopEventLog::Entry (BattlePump.h) is a fixed POD ring slot carrying
        # ONLY {seq, actionId, kind, hasHash} - no payload field, so
        # `newSide` cannot be read back from this introspection surface (this
        # was verified by reading the struct, not assumed). This leg proves
        # the COUNT and the SEQ ORDER from event_log directly, and cites the
        # CODE-PROVEN invariant for the newSide progression itself:
        # SavedBattleGame.cpp's `_turn++` lives ONLY in
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
            f"(HOSTILE->NEUTRAL is unconditional), got "
            f"{len(transitions)}: {transitions}")
        assert len(begins) == 3, (
            f"expected exactly 3 side_begin envelopes (one per side_transition, "
            f"emitted from the same guarded hook), got {len(begins)}: {begins}")
        seqs = [e["seq"] for e in boundary]
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), (
            f"boundary envelopes are not strictly seq-ordered: {boundary}")
        # h present on every side_transition entry.
        for e in transitions:
            assert e.get("h"), (
                f"side_transition seq={e['seq']} carried an EMPTY h "
                f"(the boundary needs the full sweep): {e}")
        print(f"[envelopes] client event_log: {len(transitions)} side_transition + "
              f"{len(begins)} side_begin envelope(s), seq-ordered: "
              f"{[(e['kind'], e['seq']) for e in boundary]}")

        # ----- hazard_unchanged: perTile == [] proxy (non-vacuous: fire/smoke UNCHANGED) -----
        # As envelopes explains, CoopEventLog carries no payload, so this file
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
        # host fire/smoke buckets unchanged - the outcome check for tiles,
        # in place of a direct `perTile == []` read.
        assert pre_hazard["h"] == post_hazard["h"], (
            f"hazard_unchanged: the host's fire/smoke buckets changed across a HAZARD-FREE "
            f"cycle - pre={pre_hazard['h']} post={post_hazard['h']} - "
            "something restated a tile hazard this fixture never introduced")
        print(f"[hazard_unchanged] perTile==[] proxy OK: host fire/smoke buckets unchanged "
              f"across the cycle ({post_hazard['h']})")

        # ----- buckets_equal: nine buckets EQUAL at the boundary -----
        hh, ch = assert_hash_clean(host, client, full=True, what="buckets_equal post-cycle boundary")
        print(f"[buckets_equal] all {len(hh)} buckets EQUAL after the boundary: {sorted(hh)}")

        # ----- no_desync: the client's own hash compare recorded no mismatch -----
        # the client's own verify did not fire.
        es = event_state(client)
        assert es.get("desyncSeen") is False, (
            f"no_desync: the client's desyncSeen flag is not False after a clean "
            f"boundary sweep - a hash mismatch was recorded: {es}")
        print("[no_desync] client event_state.desyncSeen == False throughout")

        # ----- unit_fields: the exercised perUnit legs -----
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
        # wounds: NOT a battle_state field - getFatalWound() for every
        # BODYPART_MAX part lives INSIDE the unitsStats hash bucket
        # (SharedEcon.cpp), so buckets_equal's nine-bucket equality above IS the wounds
        # assertion; no probe field is added here.
        print(f"[unit_fields] perUnit legs OK: status/kneeled/faction/mcId equal for "
              f"{len(hu)} unit(s); player-side tu/energy restored: "
              f"{player_tu_energy}")

        # ----- turret_parity: the turret-reset loop reproduced -----
        assert_turret_parity(host, client, what="turret_parity post-cycle boundary")
        print("[turret_parity] directionTurret parity OK for every shared unit")

        # ----- turn_side_equal: newTurn/newSide applied -----
        assert hs1["turn"] == cs1["turn"] and hs1["side"] == cs1["side"], (
            f"turn_side_equal: turn/side not equal post-cycle: host=({hs1['turn']},"
            f"{hs1['side']}) client=({cs1['turn']},{cs1['side']})")
        print(f"[turn_side_equal] newTurn/newSide applied equally: turn={hs1['turn']} "
              f"side={hs1['side']}")

        # ----- terrain_tripwire: the terrain tripwire -----
        post_terrain = host.cmd({"cmd": "hash_now", "buckets": ["terrain"]})
        assert post_terrain.get("ok"), f"hash_now(terrain) failed post-cycle: {post_terrain}"
        if pre_terrain["h"] != post_terrain["h"]:
            raise AssertionError(STR_TERRAIN_TRIPWIRE)
        print(f"[terrain_tripwire] terrain tripwire OK: host terrain bucket unchanged "
              f"({post_terrain['h']})")

        print("PASS: repro_atom_side_transition hazard-free cycle "
              f"({len(pinned)} pinned unit(s), 3 side_transitions, 9/9 "
              "buckets equal, client NextTurnState observed and dismissed "
              "hash-neutrally)")
    finally:
        host.shutdown()
        client.shutdown()


def run_script_rng_fixture():
    """script_tags: the Coop_ScriptRng_Test scriptTags parity leg. A SECOND boot,
    same pin, same one cycle, with
    tools/coop_test/mods/Coop_ScriptRng_Test loaded on BOTH machines
    (make_user_dir's `mods=` param - both machines need the SAME mods or
    their rulesets diverge, per that helper's own docstring).

    The invariant this leg asserts: after ONE full cycle on this fixture,
    the saveBlob bucket is EQUAL AND the per-unit COOP_RNG_R/COOP_RNG_C maps
    read by `_read_script_rng_tags` are EQUAL host == client for every unit.
    `BattleUnit::coopSetScriptValues` applies the host's freshly-rolled tags
    to the client from side_transition's perUnit `scriptTags` field as an
    absolute overwrite, so the mod's own newTurnUnit hook (script_rng.rul,
    which fires on the HOST for every unit at every side close and stores
    fresh COOP_RNG_R/COOP_RNG_C values) reaches the client on the wire.

    The client does not draw script values itself, so the leg proves that
    the client's tags EQUAL the host's after a boundary."""
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
        # Same as run_hazard_free_cycle's above: `needed` is 2 in this
        # classic-seat fixture, so the client arms through its own real
        # button and this driver waits for the host's tally text before the
        # host's press.
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def _host_shows_1_of_2_rng():
            return True if battle_state(host).get("coopEndTurnText") == "END TURN 1/2" else None
        host.wait_for("host paints END TURN 1/2 after the client's arm",
                      _host_shows_1_of_2_rng, timeout=15)

        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        drive_full_cycle(host, client, turn0, timeout=60, check_client_screen=False)
        session.wait_host_idle(host, client, timeout=30)

        hr = host.cmd({"cmd": "hash_now", "full": True})
        cr = client.cmd({"cmd": "hash_now", "full": True})
        assert hr.get("ok") and cr.get("ok"), f"hash_now failed: host={hr} client={cr}"
        hh, ch = hr["h"], cr["h"]
        mismatched = {k: (hh[k], ch.get(k)) for k in hh if hh.get(k) != ch.get(k)}

        # Read the per-unit COOP_RNG_R/COOP_RNG_C tag maps on BOTH machines
        # UNCONDITIONALLY - the checks below assert on them, so a parse
        # failure here is itself a failure.
        tag_maps = {}
        for gc, role in ((host, "host"), (client, "client")):
            fname = f"coop_rng_probe_{role}.sav"
            r = gc.cmd({"cmd": "save_game", "file": fname})
            assert r.get("ok"), f"save_game failed on {role} (script_tags tag read): {r}"
            path = os.path.join(gc.user_dir, "xcom1", fname)
            tag_maps[role] = _read_script_rng_tags(path)
            print(f"[script_tags map] {role} COOP_RNG_R/COOP_RNG_C per unit "
                  f"(from {path}): {tag_maps[role]}")

        # All nine hash_now buckets, saveBlob included, are EQUAL after the
        # cycle - the host's freshly-rolled tags reach the client on the wire.
        assert not mismatched, (
            "repro_atom_side_transition script_tags: bucket(s) "
            f"mismatched after one hazard-free ScriptRng cycle: "
            f"{sorted(mismatched)} - host={hh} client={ch}; per-unit tag "
            f"maps: host={tag_maps['host']} client={tag_maps['client']}")

        # The per-unit COOP_RNG_R/COOP_RNG_C maps themselves are EQUAL
        # host == client for every unit - the direct read, not implied by
        # the bucket-hash check above.
        tag_diff = {u: (tag_maps["host"].get(u), tag_maps["client"].get(u))
                    for u in set(tag_maps["host"]) | set(tag_maps["client"])
                    if tag_maps["host"].get(u) != tag_maps["client"].get(u)}
        assert tag_maps["host"] == tag_maps["client"], (
            "repro_atom_side_transition script_tags: per-unit "
            f"COOP_RNG_R/COOP_RNG_C maps differ host vs client: {tag_diff} "
            f"- host={tag_maps['host']} client={tag_maps['client']}")

        print(f"[script_tags] Coop_ScriptRng_Test scriptTags parity OK: "
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
        print("ALL repro_atom_side_transition TESTS PASSED")
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
