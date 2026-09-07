"""SPEC 5 (FX-3b, WV-D62 owner ruling 2026-09-05): vanilla-wide generation-time
AIModule release. BattlescapeGenerator::releaseAIModulesOfUnitsKilledDuringGeneration()
runs ONCE, from run() immediately after explodePowerSources()
(BattlescapeGenerator.cpp:955), and clears the AIModule of every STATUS_DEAD
non-player unit that still carries one, so the host stops serialising an `AI:`
node the client's loader already drops (SavedBattleGame.cpp:298) - the exact
t=0 saveBlob divergence on a crashed-UFO map whose power-source explosion
killed crew during generation.

EXTENDED for FX-4 (WV-D68, 2026-09-05): this file now QUALIFIES a boot on
EITHER a killed (STATUS_DEAD, status==6) OR a stunned (STATUS_UNCONSCIOUS,
status==7) non-player unit in the host's `battle_state.units[]` at t=0 - not
killed alone. WV-D68 settles BOTH kinds of generation casualty synchronously
inside UnitDieBState's ctor (the outer :53 condition gains
`|| isBeforeGame()`), closing the M2 corpse/node divergence class that FX-3b's
own SPEC 5 cycle-2 was RETURNED over (a stunned victim used to animate a "fall
to death" pirouette on the first map frames, racing `isBeforeGame()`'s flip
between host and client). A qualifying boot additionally asserts the WV-D68
settle proof: `pendingStates == 0` AND `isBusy == false` on BOTH machines,
read IMMEDIATELY at phase Active - proof that no collapse animation is still
in flight on either machine.

SPEC 0e-4 (owner D11, 2026-09-07): stun is rare under a random roll
(~1/30 boots, per WV-D68's own measurement), so this file used to accept 0
stun-qualified boots in a green run. It now PINS SEED_STUNNED (found once by
`hunt_seed.py`), so the stunned boot always qualifies; see "THE SEED" below.

AI-NEUTRAL AND ACTION-FREE: t=0 only. Every assertion below runs before
anything moves - no walk, no turn, no kneel, no end-turn. This fixture never
drives a battle atom, so none of their contact/reaction/spot hazards apply
here; the only thing this file exercises is BattlescapeGenerator::run() and
the coop handshake that follows it.

FIXTURE: repro_atom_walk's bring_up_lobby + repro_atom_door's
drive_to_battlescape shape, with newbattle_mission type="STR_SUPPLY_SHIP" (the
UFO_CRASH_RECOVERY deployment measured to actually offer a CRASHED ship on this
build - `missionType: STR_UFO_CRASH_RECOVERY`, `reinforcementsDeployment:
STR_SUPPLY_SHIP`, confirmed against a real generated save, 2026-09-05).

THE SEED (SPEC 0e-4, owner D11, 2026-09-07): explodePowerSources() only fires
75% of the time per power-source tile (RNG::percent(75),
BattlescapeGenerator.cpp:2532), and even then a hit does not always kill a
unit standing near one - so a fresh bring-up used to have to be re-rolled,
bounded by a bring-up budget, until one landed. `set_seed` sent to the host right
before `newbattle_ok` (session.drive_to_battlescape's `pre_ok` hook) makes the
map/NPC/squad deterministic (measured M5/M9: same seed -> identical
mapFingerprint/NPC ids/positions/sizes/squad positions), so this file instead
PINS a seed found ONCE by `tools/coop_test/hunt_seed.py`: SEED_KILLED (>= 1
STATUS_DEAD non-player unit at t=0) and SEED_STUNNED (>= 1
STATUS_UNCONSCIOUS non-player unit at t=0, WV-D68's second kind). Each pinned
boot asserts `battle_state.mapFingerprint` matches the fingerprint the hunt
recorded for that seed BEFORE anything else; a mismatch means a
ruleset/map/generator change shifted what the seed produces, and raises
`session.known_flake(..., "WV-D91", ...)` (the WV-D90 banner, exit 2) rather
than silently reporting a boot that proves nothing (the same WV-D57 lesson
every other rewrite fixture in this tree follows). No reroll loop remains.

ON A QUALIFYING BOOT, this asserts (in this order, so a red says exactly which
half failed):
  0. the POSITIVE CONTROL (an assertion an inert fix could not fail), ONLY
     when this boot rolled a KILLED casualty (FX-3b's release predicate is
     `health <= 0`, which is never true for a stunned unit, so a stun-only
     boot skips this control rather than false-failing it): the host's own
     log carries "released N AIModule(s)" with N >= 1;
  1. `battle_state.unitsDeadWithAI == 0` on BOTH machines - the counter FX-3b's
     own TestServer.cpp probe adds beside `turnBeforeFirstStep` (:6309),
     counting STATUS_DEAD units that still carry a non-null AIModule
     (RETAINED from FX-3b; re-run here on FX-3b+FX-4 together per WV-D68 (f) -
     no separate FX-3b test is needed);
  2. WV-D68's OWN settle proof: `pendingStates == 0` AND `isBusy == false` on
     BOTH machines, read IMMEDIATELY at phase Active (before any further
     settle delay) - proof that no collapse BState is in flight on either
     machine, i.e. that a stunned (or killed) generation casualty was fully
     settled synchronously and never animated;
  3. `hash_now {full:true}` - every SharedEcon bucket, saveBlob included, EQUAL
     between host and client (bucket count is never hard-coded - "all buckets
     EQUAL" is asserted over whatever the sweep reports);
  4. the host's own log carries "[coop-handshake] battle_ready saveBlob EQUAL"
     (and never "... MISMATCH" for this session) - the handshake this fix
     exists to stop refusing actually accepted the world;
  5. both machines' `save_game` documents (the real on-disk .sav, not a live
     probe) agree on every `nodes[].type` and every item id - the two fields
     the (C) RCA's own docstring (test_rw_item_id_ctr.py) named as "MECHANISM
     2 - a dead alien's corpse id/nodes[].type/binTiles", the divergence class
     this file's name refers to and which WV-D61 explicitly left untouched.
     Comparing the SAVED documents (rather than the live JSON probes) is
     deliberate: it is what the (C) RCA's own investigation compared, and it
     is what the coop handshake's saveBlob hash is itself computed over.

Bar (WV-D65, SPEC 0e-4): the fixture is now DETERMINISTIC (a pinned seed, not
a map roll), so the bar is THREE CONSECUTIVE GREEN runs (each a separate
process invocation - "one test per invocation").

RED-THEN-GREEN is NOT automated by this file - it is the owner's second
independent hit, done by hand per each packet's brief:
  - FX-3b (WV-D62): comment out the single call in BattlescapeGenerator::run(),
    rebuild, run this file until a qualifying boot, capture the failure
    (expected: the host log's own "battle_ready saveBlob MISMATCH" line plus
    an `AI:` node count delta between the two machines' saved documents), then
    restore the call, rebuild, and confirm green again.
  - FX-4 (WV-D68): revert ONLY the `|| _parent->getSave()->isBeforeGame()`
    clause on UnitDieBState.cpp:53 (leave everything else - the comment block,
    the pendingStates probe, this test - in place), rebuild, loop this file
    hunting a STUN-qualified (not merely killed-qualified) boot, capture the
    failure (expected: a `pendingStates`/`isBusy` non-zero reading on the
    client and/or a `nodes[].type` divergence and/or a saveBlob MISMATCH),
    then restore the clause, rebuild, and confirm green again.

Run: python tools/coop_test/test_rw_m2_corpse_node.py (its own shell
invocation - one harness run at a time, machine-wide).
"""

import glob
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import repro_atom_walk as W

MISSION = "STR_SUPPLY_SHIP"
FACTION_PLAYER = 0
STATUS_DEAD = 6
STATUS_UNCONSCIOUS = 7  # WV-D68 (FX-4): a stunned generation casualty qualifies too

# PINNED (SPEC 0e-4, owner D11): found ONCE by hunt_seed.py, never re-rolled.
# pinned 2026-09-07 by hunt_seed.py at 29536ea95
SEED_KILLED = 2
FINGERPRINT_KILLED = 8.979686268403716e+18
# pinned 2026-09-07 by hunt_seed.py at 29536ea95
SEED_STUNNED = 23
FINGERPRINT_STUNNED = -6.768173743533399e+18

BASE_PORT = 48400          # the coop lobby TCP port (bring_up_lobby's `port`)
BASE_PROBE = 49400         # the TestServer control-socket port base

# EXIT CODES, the wave's shipped convention (2026-09-03 ruling):
# 0 = PASS, 2 = FAIL (a red - includes a WV-D91/WV-D92 known-flake banner), 3 =
# SKIP (the ruleset does not offer the fixture mission, or a pinned seed's
# fingerprint guard passed yet the casualty vanished - see FIXTURE: below).
EXIT_PASS, EXIT_FAIL, EXIT_SKIP = 0, 2, 3

RELEASE_LOG_RE = re.compile(r"released (\d+) AIModule\(s\)")
SAVEBLOB_EQUAL_TEXT = "[coop-handshake] battle_ready saveBlob EQUAL"
SAVEBLOB_MISMATCH_TEXT = "[coop-handshake] battle_ready saveBlob MISMATCH"


# SPEC 0e-4: the "does not offer" mission check raises an AssertionError
# already prefixed "FIXTURE:" by session.drive_to_battlescape itself, which
# the REV E.22 __main__ template's own `str(e).startswith("FIXTURE:")` check
# routes to SKIP(3) - no bespoke MissionNotOffered wrapper needed any more.

# ----- small probes --------------------------------------------------------

def battle_state(gc):
    return gc.cmd({"cmd": "battle_state"})


def event_state(gc):
    return gc.cmd({"cmd": "event_state"})


def log_text(gc):
    path = os.path.join(gc.user_dir, "openxcom.log")
    try:
        with open(path, "r", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def dead_non_player_units(st):
    return [u for u in st.get("units", [])
            if u.get("status") == STATUS_DEAD and u.get("faction") != FACTION_PLAYER]


def stunned_non_player_units(st):
    """WV-D68 (FX-4): the OTHER generation-casualty kind - a non-player unit
    STATUS_UNCONSCIOUS (stunned) rather than STATUS_DEAD (killed) at t=0."""
    return [u for u in st.get("units", [])
            if u.get("status") == STATUS_UNCONSCIOUS and u.get("faction") != FACTION_PLAYER]


# ----- save-file introspection (the (C) RCA's own "MECHANISM 2" fields) ---

def save_and_read(gc, filename):
    """Writes a real .sav through the EXISTING `save_game` lever (no new C++:
    SavedGame::save is called exactly as any player save does) and reads the
    file back as text. `save_game` writes under
    Options::getMasterUserFolder() == <user_dir>/<masterMod>/ (measured
    2026-09-05: .../xcom1/<file> on this build's ruleset), so this globs for
    it under the instance's own user_dir rather than assuming the mod name."""
    r = gc.cmd({"cmd": "save_game", "file": filename})
    assert r.get("ok"), f"save_game failed on {gc.name}: {r}"
    matches = glob.glob(os.path.join(gc.user_dir, "**", filename), recursive=True)
    assert matches, (
        f"save_game reported ok on {gc.name} but {filename!r} is not anywhere "
        f"under {gc.user_dir}")
    with open(matches[0], "r", errors="replace") as f:
        return f.read()


def _block_slice(text, key):
    """The text of one top-level (2-space-indent) `battleGame:` child block,
    from its own `  <key>:` line up to (not including) the next 2-space-indent
    key line. MEASURED shape (2026-09-05, a real generated .sav):
        battleGame:
          nodes:
            - {id: 0,position: [4,4,0],type: 0,rank: 0,...}
          units:
            - id: 0
              ...
          items:
            - id: 0
              type: STR_PISTOL
              ...
          itemsSpecial:
    """
    m = re.search(rf"^  {re.escape(key)}:\s*$", text, re.M)
    assert m, f"no `  {key}:` block in the save - this is not a battle save, or the shape changed"
    rest = text[m.end():]
    nxt = re.search(r"^  [A-Za-z]", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


# Node::save (Node.cpp:92-109) is UNCONDITIONAL and FLOW-STYLE: `id` then
# `position` then `type`, always, one node per line inside `{...}`.
NODE_ENTRY_RE = re.compile(r"\{id:\s*(-?\d+),.*?type:\s*(-?\d+),")

# BattleItem::save (BattleItem.cpp:136-139) writes `id` FIRST, UNCONDITIONALLY,
# as its own block-sequence line (`    - id: N`), before any other field.
ITEM_ID_RE = re.compile(r"^\s*-\s*id:\s*(\d+)\s*$", re.M)


def node_types(save_text):
    """{node id: node type} for every node in the save's `nodes:` block."""
    blk = _block_slice(save_text, "nodes")
    out = {}
    for m in NODE_ENTRY_RE.finditer(blk):
        out[int(m.group(1))] = int(m.group(2))
    assert out, "parsed ZERO nodes out of a `nodes:` block that exists - the regex is wrong, not the save"
    return out


def item_ids(save_text):
    """Sorted list of every item id in the save's `items:` block (the plain
    item list; `itemsSpecial` - built-in weapons - is a separate block and not
    part of this comparison)."""
    blk = _block_slice(save_text, "items")
    ids = sorted(int(m.group(1)) for m in ITEM_ID_RE.finditer(blk))
    assert ids, "parsed ZERO items out of an `items:` block that exists - the regex is wrong, not the save"
    return ids


# ----- fixture bring-up -----------------------------------------------------

def one_bringup(tag, seed, expected_fingerprint):
    """One fresh host+client bring-up on the STR_SUPPLY_SHIP fixture with the
    PINNED `seed` (SPEC 0e-4, owner D11): `set_seed` is sent to the host via
    session.drive_to_battlescape's `pre_ok` hook immediately before
    `newbattle_ok`, so the map/NPC/squad are deterministic (measured M5/M9).

    Immediately after drive_to_battlescape returns, asserts the FINGERPRINT
    GUARD: `battle_state.mapFingerprint == expected_fingerprint`. A mismatch
    means a ruleset/map/generator change shifted what this seed produces, so
    this raises `session.known_flake(..., "WV-D91", ...)` (WV-D90 banner,
    exit 2) rather than silently reporting a boot that no longer proves
    anything.

    Returns (host, client, killed, stunned). Lets a "does not offer" mission
    AssertionError (already "FIXTURE:"-prefixed by session.py) or any other
    AssertionError/TimeoutError propagate as a hard FAIL/SKIP via the
    REV E.22 __main__ template: after WV-D62/WV-D68 there is no known reason
    a clean bring-up on a PINNED seed should fail or hang, so this file does
    not reclassify one as an unrelated, re-rollable mismatch the way
    test_rw_item_id_ctr.py does for its own (different, already-fixed-
    elsewhere) map class."""
    port = str(BASE_PORT + tag)
    host = GameClient("host", BASE_PROBE + tag * 2,
                       make_user_dir(f"rw_m2_corpse_host_{tag}"))
    client = GameClient("client", BASE_PROBE + 1 + tag * 2,
                         make_user_dir(f"rw_m2_corpse_client_{tag}"))
    seated = {}
    try:
        W.bring_up_lobby(host, client, port)
        session.drive_to_battlescape(
            host, client, seated, mission=MISSION,
            pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": seed}))
    except Exception:
        host.shutdown()
        client.shutdown()
        raise

    st = battle_state(host)
    fp = st.get("mapFingerprint")
    if fp != expected_fingerprint:
        killed = len(dead_non_player_units(st))
        stunned = len(stunned_non_player_units(st))
        record = {
            "seed": seed, "expected_fingerprint": expected_fingerprint,
            "actual_fingerprint": fp, "mapSizeXYZ": st.get("mapSizeXYZ"),
            "killed": killed, "stunned": stunned,
            "units": [{"id": u.get("id"), "faction": u.get("faction"),
                       "status": u.get("status")} for u in st.get("units", [])],
        }
        host.shutdown()
        client.shutdown()
        session.known_flake(
            "test_rw_m2_corpse_node", "WV-D91",
            f"pinned seed {seed} no longer reproduces the scenario - re-run hunt_seed.py",
            record)

    killed = len(dead_non_player_units(st))
    stunned = len(stunned_non_player_units(st))
    return host, client, killed, stunned


# ----- assertions on a qualified boot --------------------------------------

def run_assertions(host, client, killed, stunned):
    # Reach phase Active on BOTH machines first, polled TIGHT (not the coarse
    # default interval) so the WV-D68 settle-proof below reads "IMMEDIATELY at
    # phase Active" rather than after a blanket settle delay that could let an
    # in-flight collapse animation quietly finish first and hide a real red.
    host.wait_for("host phase reaches Active",
                  lambda: (event_state(host).get("phase") == "Active") or None,
                  timeout=30, interval=0.1)
    client.wait_for("client phase reaches Active",
                    lambda: (event_state(client).get("phase") == "Active") or None,
                    timeout=30, interval=0.1)

    # --- (2) WV-D68's OWN settle proof, read IMMEDIATELY: no collapse BState
    # is in flight on EITHER machine right at phase Active ---
    host_st_t0 = battle_state(host)
    client_st_t0 = battle_state(client)
    assert host_st_t0.get("pendingStates") == 0, (
        f"HOST battle_state.pendingStates={host_st_t0.get('pendingStates')} "
        "(expected 0) IMMEDIATELY at phase Active - a BState (e.g. an animated "
        "UnitDieBState collapse) is still in flight on the host; WV-D68's "
        "synchronous settle did not complete before the first frame")
    assert host_st_t0.get("isBusy") is False, (
        f"HOST battle_state.isBusy={host_st_t0.get('isBusy')} (expected False) "
        "IMMEDIATELY at phase Active - the host's BattlescapeGame reports busy, "
        "i.e. an animation/chain is still running at t=0")
    assert client_st_t0.get("pendingStates") == 0, (
        f"CLIENT battle_state.pendingStates={client_st_t0.get('pendingStates')} "
        "(expected 0) IMMEDIATELY at phase Active - the client is replaying a "
        "collapse the host already settled synchronously, the exact M2 "
        "divergence WV-D68 exists to close")
    assert client_st_t0.get("isBusy") is False, (
        f"CLIENT battle_state.isBusy={client_st_t0.get('isBusy')} (expected "
        "False) IMMEDIATELY at phase Active - the client's BattlescapeGame "
        "reports busy, i.e. an animation/chain is still running at t=0")

    # Settle: both sides' onReady()/phase bookkeeping runs during/after the
    # blob load that follows the click driving startFirstTurn() - the same
    # settle test_rw_item_id_ctr.py and test_rw_hash_now.py use before their
    # own t=0 introspection. Deliberately AFTER the immediate settle-proof
    # above, never before it.
    time.sleep(2)

    host_log = log_text(host)

    # --- (0) POSITIVE CONTROL, only when this boot rolled a KILLED casualty:
    # FX-3b's release predicate is health<=0, never true for a stunned unit,
    # so a stun-only qualifying boot correctly has nothing to release here ---
    released = 0
    if killed >= 1:
        m = RELEASE_LOG_RE.search(host_log)
        assert m, (
            "positive control FAILED: the host log does not carry "
            "'released N AIModule(s)' - "
            "BattlescapeGenerator::releaseAIModulesOfUnitsKilledDuringGeneration "
            f"never logged a release even though the host reported {killed} "
            "STATUS_DEAD non-player unit(s) at t=0 - nothing below can prove "
            "anything if the mechanism never engaged")
        released = int(m.group(1))
        assert released >= 1, (
            f"positive control: the host log's release count is {released}, expected >= 1")
    else:
        print("[test_rw_m2_corpse_node] no KILLED casualty this boot (stun-only "
              "qualification) - FX-3b's release positive control does not apply "
              "(its predicate is health<=0, never true for a stunned unit)")

    # --- (1) FX-3b's own assertion, RETAINED: unitsDeadWithAI == 0 on BOTH
    # machines, re-run here on FX-3b+FX-4 together (WV-D68 (f)) ---
    host_st, client_st = battle_state(host), battle_state(client)
    assert host_st.get("unitsDeadWithAI") == 0, (
        f"HOST battle_state.unitsDeadWithAI={host_st.get('unitsDeadWithAI')} "
        "(expected 0) - a STATUS_DEAD unit still carries a non-null AIModule "
        "after generation; the release did not run/complete for it")
    assert client_st.get("unitsDeadWithAI") == 0, (
        f"CLIENT battle_state.unitsDeadWithAI={client_st.get('unitsDeadWithAI')} "
        "(expected 0) - SavedBattleGame::load never reconstructs an AIModule "
        "for a dead unit (SavedBattleGame.cpp:298), so a non-zero count here "
        "means the host's own generation-time release did not run before the "
        "snapshot was taken (WV-D62)")

    # --- (3) hash_now full: every bucket, saveBlob included, EQUAL. Never
    # hard-code a bucket count - assert "all buckets EQUAL" over whatever the
    # sweep reports. ---
    session.assert_hash_clean(host, client, full=True,
                               what="WV-D62/WV-D68 t=0 (qualified boot)")

    # --- (4) the host's own handshake log: accepted, never mismatched ---
    assert SAVEBLOB_EQUAL_TEXT in host_log, (
        f"the host log does not carry {SAVEBLOB_EQUAL_TEXT!r} - the coop "
        "handshake for this battle did not conclude normally, so the "
        "hash-clean assertion above would not be meaningful")
    assert SAVEBLOB_MISMATCH_TEXT not in host_log, (
        f"the host log DOES carry {SAVEBLOB_MISMATCH_TEXT!r} for this "
        "session - a real t=0 divergence occurred even though the release "
        "mechanism ran and reported success")

    # --- (5) the two SAVED documents agree on nodes[].type and item ids ---
    host_text = save_and_read(host, "rw_m2_corpse_host.sav")
    client_text = save_and_read(client, "rw_m2_corpse_client.sav")

    host_nodes, client_nodes = node_types(host_text), node_types(client_text)
    assert host_nodes == client_nodes, (
        "the two machines' SAVED `nodes[].type` disagree - MECHANISM 2, the "
        "exact class test_rw_item_id_ctr.py's docstring named as out of "
        f"WV-D61's scope: differing ids "
        f"{sorted(k for k in set(host_nodes) | set(client_nodes) if host_nodes.get(k) != client_nodes.get(k))} "
        f"(host has {len(host_nodes)} node(s), client has {len(client_nodes)})")

    host_items, client_items = item_ids(host_text), item_ids(client_text)
    assert host_items == client_items, (
        "the two machines' SAVED item id lists disagree: "
        f"host-only={sorted(set(host_items) - set(client_items))} "
        f"client-only={sorted(set(client_items) - set(host_items))}")

    print(f"PASS: killed={killed} stunned={stunned} non-player casualty(ies) at "
          f"t=0; pendingStates==0 and isBusy==False on both machines "
          "IMMEDIATELY at phase Active (WV-D68 settle proof); "
          f"host log 'released {released} AIModule(s)'"
          f"{' (skipped: stun-only boot)' if killed == 0 else ''}; "
          "unitsDeadWithAI == 0 on both machines; hash_now full EQUAL "
          f"(saveBlob included); host log {SAVEBLOB_EQUAL_TEXT!r} present; "
          f"{len(host_nodes)} node(s) and {len(host_items)} item(s) agree "
          "byte-for-byte between the two machines' saved documents")


def main():
    t0 = time.time()

    host, client, killed, stunned = one_bringup(1, SEED_KILLED, FINGERPRINT_KILLED)
    try:
        assert killed >= 1, (
            f"FIXTURE: pinned SEED_KILLED={SEED_KILLED} passed its fingerprint "
            "guard but rolled 0 STATUS_DEAD non-player unit(s) at t=0 - the map "
            "reproduced but the casualty did not (report this)")
        run_assertions(host, client, killed, stunned)
    finally:
        host.shutdown()
        client.shutdown()
    print(f"[test_rw_m2_corpse_node] killed boot (seed {SEED_KILLED}): "
          f"killed={killed} stunned={stunned}")

    host, client, killed, stunned = one_bringup(2, SEED_STUNNED, FINGERPRINT_STUNNED)
    try:
        assert stunned >= 1, (
            f"FIXTURE: pinned SEED_STUNNED={SEED_STUNNED} passed its fingerprint "
            "guard but rolled 0 STATUS_UNCONSCIOUS non-player unit(s) at t=0 - "
            "the map reproduced but the casualty did not (report this)")
        run_assertions(host, client, killed, stunned)
    finally:
        host.shutdown()
        client.shutdown()
    print(f"[test_rw_m2_corpse_node] stunned boot (seed {SEED_STUNNED}): "
          f"killed={killed} stunned={stunned}")

    print(f"\ntest_rw_m2_corpse_node: PASS (2/2 pinned boots - killed seed "
          f"{SEED_KILLED}, stunned seed {SEED_STUNNED} - {time.time() - t0:.1f}s)")


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("test_rw_m2_corpse_node", "WV-D91", str(e))
        print(f"\ntest_rw_m2_corpse_node: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(EXIT_FAIL)
    except AssertionError as e:
        if str(e).startswith("FIXTURE:"):
            print(f"\ntest_rw_m2_corpse_node: SKIP (fixture) - {e}")
            sys.exit(EXIT_SKIP)
        print(f"\ntest_rw_m2_corpse_node: FAIL\nAssertionError: {e}")
        sys.exit(EXIT_FAIL)
    except TimeoutError as e:
        print(f"\ntest_rw_m2_corpse_node: FAIL\nTimeoutError: {e}")
        sys.exit(EXIT_FAIL)
