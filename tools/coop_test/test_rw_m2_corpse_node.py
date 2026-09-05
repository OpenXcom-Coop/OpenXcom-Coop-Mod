"""SPEC 5 (FX-3b, WV-D62 owner ruling 2026-09-05): vanilla-wide generation-time
AIModule release. BattlescapeGenerator::releaseAIModulesOfUnitsKilledDuringGeneration()
runs ONCE, from run() immediately after explodePowerSources()
(BattlescapeGenerator.cpp:955), and clears the AIModule of every STATUS_DEAD
non-player unit that still carries one, so the host stops serialising an `AI:`
node the client's loader already drops (SavedBattleGame.cpp:298) - the exact
t=0 saveBlob divergence on a crashed-UFO map whose power-source explosion
killed crew during generation.

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

THE ROLL: explodePowerSources() only fires 75% of the time per power-source
tile (RNG::percent(75), BattlescapeGenerator.cpp:2532), and even then a hit
does not always kill a unit standing near one. A single diagnostic boot of
this fixture (host-only, no coop) already rolled 1 STATUS_DEAD non-player unit
on its FIRST attempt, consistent with the ~1/8 rate this packet's brief
measured. This file loops fresh host+client bring-ups, UP TO MAX_BRINGUPS,
until the HOST reports at least one STATUS_DEAD (status==6) non-player
(faction != FACTION_PLAYER) unit in its own `battle_state.units[]` at t=0. A
run that never rolls one in MAX_BRINGUPS attempts is VACUOUS - it never
exercised the fix at all - and exits SKIP(3) rather than reporting a green
that proves nothing (the same WV-D57 lesson every other rewrite fixture in
this tree follows).

ON A QUALIFYING BOOT, this asserts (in this order, so a red says exactly which
half failed):
  1. the POSITIVE CONTROL FIRST (an assertion an inert fix could not fail): the
     host's own log carries "released N AIModule(s)" with N >= 1 - the release
     mechanism actually ran and found something to release, not merely that
     nothing is visibly wrong afterwards;
  2. `battle_state.unitsDeadWithAI == 0` on BOTH machines - the counter this
     packet's own TestServer.cpp probe adds beside `turnBeforeFirstStep`
     (:6309), counting STATUS_DEAD units that still carry a non-null
     AIModule;
  3. `hash_now {full:true}` - every SharedEcon bucket, saveBlob included, EQUAL
     between host and client;
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

Bar (BLOCK RUN's own convention): TEN CONSECUTIVE QUALIFIED GREEN runs (each a
separate process invocation - "one test per invocation"), SKIPs (VACUOUS
boots) do not break the streak. The SKIP rate is reported at every gate.

RED-THEN-GREEN is NOT automated by this file - it is the owner's second
independent hit, done by hand per the brief: comment out the single call in
BattlescapeGenerator::run(), rebuild, run this file until a qualifying boot,
capture the failure (expected: the host log's own
"battle_ready saveBlob MISMATCH" line plus an `AI:` node count delta between
the two machines' saved documents), then restore the call, rebuild, and
confirm green again.

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
import repro_atom_door as D

MISSION = "STR_SUPPLY_SHIP"
MAX_BRINGUPS = 24
FACTION_PLAYER = 0
STATUS_DEAD = 6

BASE_PORT = 48400          # the coop lobby TCP port (bring_up_lobby's `port`)
BASE_PROBE = 49400         # the TestServer control-socket port base

# EXIT CODES, the wave's shipped convention (2026-09-03 ruling):
# 0 = PASS, 2 = FAIL (a red), 3 = SKIP - either the ruleset does not offer the
# fixture mission, or MAX_BRINGUPS attempts never rolled a qualifying
# crash-kill (VACUOUS). Neither is a statement about WV-D62 itself.
EXIT_PASS, EXIT_FAIL, EXIT_SKIP = 0, 2, 3

RELEASE_LOG_RE = re.compile(r"released (\d+) AIModule\(s\)")
SAVEBLOB_EQUAL_TEXT = "[coop-handshake] battle_ready saveBlob EQUAL"
SAVEBLOB_MISMATCH_TEXT = "[coop-handshake] battle_ready saveBlob MISMATCH"


class MissionNotOffered(Exception):
    """STR_SUPPLY_SHIP is not in this build's NEW BATTLE mission list - a fact
    about the loaded ruleset, not about WV-D62. SKIP, not FAIL, and never
    retried (every bring-up would fail identically)."""


class FixtureExhausted(Exception):
    """MAX_BRINGUPS fresh bring-ups never produced a HOST-side STATUS_DEAD
    non-player unit at t=0. VACUOUS - SKIP, not FAIL."""


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

def one_bringup(tag):
    """One fresh host+client bring-up on the STR_SUPPLY_SHIP fixture. Returns
    (host, client, dead_count) - the caller decides whether dead_count >= 1
    qualifies this boot or whether to shut it down and roll again.

    Raises MissionNotOffered (a static ruleset fact, never retried) or lets
    any other AssertionError/TimeoutError propagate as a hard FAIL: after
    WV-D62 there is no known reason a clean bring-up on this fixture should
    fail or hang, so this file does not reclassify one as an unrelated,
    re-rollable mismatch the way test_rw_item_id_ctr.py does for its own
    (different, already-fixed-elsewhere) map class."""
    port = str(BASE_PORT + tag)
    host = GameClient("host", BASE_PROBE + tag * 2,
                       make_user_dir(f"rw_m2_corpse_host_{tag}"))
    client = GameClient("client", BASE_PROBE + 1 + tag * 2,
                         make_user_dir(f"rw_m2_corpse_client_{tag}"))
    seated = {}
    try:
        W.bring_up_lobby(host, client, port)
        try:
            D.drive_to_battlescape(host, client, seated, mission=MISSION)
        except AssertionError as e:
            if "does not offer" in str(e):
                raise MissionNotOffered(str(e))
            raise
    except Exception:
        host.shutdown()
        client.shutdown()
        raise

    dead = dead_non_player_units(battle_state(host))
    return host, client, len(dead)


def find_qualifying_bringup():
    for attempt in range(1, MAX_BRINGUPS + 1):
        host, client, dead_count = one_bringup(attempt)
        if dead_count >= 1:
            print(f"[test_rw_m2_corpse_node] QUALIFIED on bring-up "
                  f"{attempt}/{MAX_BRINGUPS}: {dead_count} STATUS_DEAD "
                  "non-player unit(s) in the host's battle_state at t=0")
            return host, client, dead_count, attempt
        print(f"[test_rw_m2_corpse_node] bring-up {attempt}/{MAX_BRINGUPS}: "
              "no crash-kill rolled, re-rolling with a fresh bring-up")
        host.shutdown()
        client.shutdown()
    raise FixtureExhausted(
        f"no HOST-side STATUS_DEAD non-player unit at t=0 in {MAX_BRINGUPS} "
        f"fresh bring-ups of {MISSION!r} - VACUOUS, not a result about WV-D62")


# ----- assertions on a qualified boot --------------------------------------

def run_assertions(host, client, dead_count):
    # Settle: both sides' onReady()/phase bookkeeping runs during/after the
    # blob load that follows the click driving startFirstTurn() - the same
    # settle test_rw_item_id_ctr.py and test_rw_hash_now.py use before their
    # own t=0 introspection.
    time.sleep(2)

    host_es, client_es = event_state(host), event_state(client)
    assert host_es.get("phase") == "Active" and client_es.get("phase") == "Active", (
        "both machines should be phase Active after a qualifying boot: "
        f"host={host_es.get('phase')} client={client_es.get('phase')}")

    # --- (1) POSITIVE CONTROL FIRST: the release mechanism actually ran ---
    host_log = log_text(host)
    m = RELEASE_LOG_RE.search(host_log)
    assert m, (
        "positive control FAILED: the host log does not carry "
        "'released N AIModule(s)' - "
        "BattlescapeGenerator::releaseAIModulesOfUnitsKilledDuringGeneration "
        f"never logged a release even though the host reported {dead_count} "
        "STATUS_DEAD non-player unit(s) at t=0 - nothing below can prove "
        "anything if the mechanism never engaged")
    released = int(m.group(1))
    assert released >= 1, (
        f"positive control: the host log's release count is {released}, expected >= 1")

    # --- (2) the actual fix: unitsDeadWithAI == 0 on BOTH machines ---
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

    # --- (3) hash_now full: every bucket, saveBlob included, EQUAL ---
    session.assert_hash_clean(host, client, full=True,
                               what="WV-D62 t=0 (qualified boot)")

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

    print(f"PASS: {dead_count} STATUS_DEAD non-player unit(s) at t=0; host log "
          f"'released {released} AIModule(s)'; unitsDeadWithAI == 0 on both "
          "machines; hash_now full EQUAL (saveBlob included); host log "
          f"{SAVEBLOB_EQUAL_TEXT!r} present; {len(host_nodes)} node(s) and "
          f"{len(host_items)} item(s) agree byte-for-byte between the two "
          "machines' saved documents")


def main():
    t0 = time.time()
    host, client, dead_count, bringup_index = find_qualifying_bringup()
    try:
        run_assertions(host, client, dead_count)
    finally:
        host.shutdown()
        client.shutdown()
    print(f"\ntest_rw_m2_corpse_node: PASS (qualified on bring-up "
          f"{bringup_index}/{MAX_BRINGUPS}, {time.time() - t0:.1f}s)")


if __name__ == "__main__":
    try:
        main()
    except MissionNotOffered as e:
        print(f"\ntest_rw_m2_corpse_node: SKIP ({MISSION} not offered)\n{e}")
        sys.exit(EXIT_SKIP)
    except FixtureExhausted as e:
        print(f"\ntest_rw_m2_corpse_node: SKIP (fixture exhausted, VACUOUS)\n{e}")
        sys.exit(EXIT_SKIP)
    except (AssertionError, TimeoutError) as e:
        print(f"\ntest_rw_m2_corpse_node: FAIL\n{type(e).__name__}: {e}")
        import traceback
        print("")
        print("--- traceback (classification aid) ---")
        traceback.print_exc()
        sys.exit(EXIT_FAIL)
