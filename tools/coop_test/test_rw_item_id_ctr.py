"""SPEC 3 (FX-2, WV-D61 / owner ruling R-B, 2026-09-04): itemIdCtr rides the
blob - the host's true SavedBattleGame::_itemId is carried in the BATTLE save
block (key `coopItemIdCtr`) and the loading machine ADOPTS it verbatim instead
of re-deriving max(item id)+1 (RB-D24's fallback, superseded here).

WHY: the (C) RCA (rewrite/wave1-log.md, 2026-09-03, "UFO-MAP t=0 DIVERGENCE")
root-caused a structural FALSE-POSITIVE desync source: SavedBattleGame::_itemId
is NEVER serialized, so the client re-derives it as max(surviving id)+1 while
the host runs a true running allocation counter - and any id the host
allocates that does NOT survive into the serialized document (e.g. discarded
during generation) leaves the two permanently offset with otherwise IDENTICAL
worlds. Measured on STR_BATTLESHIP: `diverged=['itemIdCtr']` alone, host 97 vs
client 96, the two documents byte-identical except the excluded `animFrame`
(3/6 boots hit it in that RCA's own sample).

AI-NEUTRAL AND ACTION-FREE: every assertion below is at t=0, before anything
moves - no walk, no turn, no kneel. This fixture never drives a walk/door/spot
atom, so none of their contact/reaction hazards apply here.

FIXTURE: repro_atom_door.py's bring-up shape (W.bring_up_lobby +
session.drive_to_battlescape) with newbattle_mission type="STR_BATTLESHIP" - the map
class the (C) RCA measured diverging on itemIdCtr ALONE.

PINNED SEEDS, NOT A REROLL (SPEC 0e-4, owner D11, 2026-09-07): the (C) RCA's
own sample measured STR_BATTLESHIP hitting a t=0 handshake refusal on
`battle_ready`'s saveBlob compare in **3 of 6** boots - not always the
itemIdCtr-ALONE class this packet targets: a SEPARATE, richer class (their
"MECHANISM 2": a dead alien's corpse id/`nodes[].type`/`binTiles`) can also
fire on a UFO map class, and WV-D61 does not touch it (it is out of this
packet's scope - FX-3a/M2 territory). This file used to re-roll a fresh
attempt past that unrelated refusal, up to a re-roll budget. `set_seed` sent
to the host right before `newbattle_ok` (session.drive_to_battlescape's
`pre_ok` hook) makes the map/NPC/squad deterministic (measured M5/M9), so
this file instead PINS two seeds found ONCE by `tools/coop_test/hunt_seed.py`:
SEED_DIVERGENT (the adopt line logs `carried != derived`) and SEED_AGREED
(the adopt ran, `carried == derived` - the control that proves the mechanism
ran without a discrepancy). Each pinned boot asserts
`battle_state.mapFingerprint` matches the fingerprint the hunt recorded for
that seed BEFORE anything else; a mismatch raises `session.known_flake(...,
"WV-D91", ...)` (the WV-D90 banner, exit 2). On a `TimeoutError` whose host
log carries `UNRELATED_MISMATCH_SIGNATURE` ("battle_ready saveBlob
MISMATCH"), this raises `session.known_flake(..., "WV-D92", ...)` instead of
re-rolling - the pinned seeds are ones that do NOT refuse (measured M9: 0
refusals in 33 boots on this tip), so a refusal on a pinned seed is evidence
a ruleset/product change shifted its behaviour, not something to roll past.

POSITIVE CONTROL FIRST (an adopt that never happened cannot prove anything):
every boot must show event_state.itemIdCtrAdopted > 0 (or the client's own
log carrying the "[coop-itemid] WV-D61: adopted coopItemIdCtr" line) before
any hash comparison is treated as meaningful. coopLoadItemIdCtr stores a
value there on EVERY presence-gated load, whether or not carried and derived
agreed, so this checks the mechanism actually RAN, not that it found a
discrepancy.

NON-VACUITY BY CONSTRUCTION: this file runs exactly TWO pinned boots -
SEED_DIVERGENT and SEED_AGREED - and asserts
`(derived_diff is not None) == expect_diverged` on each, read out of the
"(derived N)" suffix the adopted-line only prints on disagreement. The
divergent seed is pinned precisely because the hunt already confirmed it
produces a genuine carried != derived discrepancy, so this file can never
report a green that proves nothing (WV-D57's own lesson).
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import repro_atom_walk as W

MISSION = "STR_BATTLESHIP"

# PINNED (SPEC 0e-4, owner D11): found ONCE by hunt_seed.py, never re-rolled.
# pinned 2026-09-07 by hunt_seed.py at 29536ea95
SEED_DIVERGENT = 7
FINGERPRINT_DIVERGENT = -6.208391770701378e+18
# pinned 2026-09-07 by hunt_seed.py at 29536ea95
SEED_AGREED = 1
FINGERPRINT_AGREED = 1.870118385057293e+18

# EXIT CODES, matching the wave's shipped convention (2026-09-03 ruling):
# 0 = PASS, 2 = FAIL (a red - includes a WV-D91/WV-D92 known-flake banner), 3 =
# SKIP (the ruleset does not offer the fixture mission).
EXIT_PASS, EXIT_FAIL, EXIT_SKIP = 0, 2, 3

ADOPT_LOG_RE = re.compile(
    r"\[coop-itemid\] WV-D61: adopted coopItemIdCtr (\d+) \(derived (\d+)\)")

UNRELATED_MISMATCH_SIGNATURE = "battle_ready saveBlob MISMATCH"


def _log_text(gc):
    path = os.path.join(gc.user_dir, "openxcom.log")
    try:
        with open(path, "r", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _adopted_derived_pairs(gc):
    """Every (carried, derived) pair the [coop-itemid] adopted line logged on
    this machine. The hook logs this line ONLY when the two values actually
    DISAGREED (coopLoadItemIdCtr in connectionTCP.cpp), so a non-empty list
    here is itself the non-vacuity proof for this boot."""
    return [(int(m.group(1)), int(m.group(2)))
            for m in ADOPT_LOG_RE.finditer(_log_text(gc))]


def one_attempt(tag, seed, expected_fingerprint, expect_diverged):
    """One host+client bring-up on the STR_BATTLESHIP fixture with the PINNED
    `seed` (SPEC 0e-4, owner D11): `set_seed` is sent to the host via
    session.drive_to_battlescape's `pre_ok` hook right before `newbattle_ok`,
    so the map/NPC/squad are deterministic (measured M5/M9).

    Asserts the FINGERPRINT GUARD immediately after drive_to_battlescape
    returns: `battle_state.mapFingerprint == expected_fingerprint`. A
    mismatch raises `session.known_flake(..., "WV-D91", ...)` (WV-D90
    banner, exit 2) - a ruleset/map/generator change shifted what this seed
    produces.

    On a TimeoutError whose host log carries the confirmed pre-existing
    UNRELATED_MISMATCH_SIGNATURE, raises `session.known_flake(..., "WV-D92",
    "pinned seed <n> now hits the pre-existing battle_ready saveBlob
    mismatch", {...})` - evidence, not a re-roll (the pinned seeds are ones
    that do NOT refuse; a refusal here means the ruleset/product shifted).
    Any other exception is a hard FAIL.

    Returns a result dict and asserts
    `(derived_diff is not None) == expect_diverged` at the end: SEED_DIVERGENT
    must show a genuine carried != derived discrepancy and SEED_AGREED must
    not, by construction."""
    port = str(48250 + tag)
    host = GameClient("host", 48950 + tag * 2,
                       make_user_dir(f"rw_itemidctr_host_{tag}"))
    client = GameClient("client", 48951 + tag * 2,
                         make_user_dir(f"rw_itemidctr_client_{tag}"))
    seated = {}
    try:
        # W.bring_up_lobby: spawn+connect both, host a lobby, join the
        # client, clear both Profile popups - the exact same lobby-flow drive
        # repro_atom_door.py's own bring_up() uses ahead of its
        # drive_to_battlescape() call.
        W.bring_up_lobby(host, client, port)

        try:
            session.drive_to_battlescape(
                host, client, seated, mission=MISSION,
                pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": seed}))
        except TimeoutError as e:
            if UNRELATED_MISMATCH_SIGNATURE in _log_text(host):
                session.known_flake(
                    "test_rw_item_id_ctr", "WV-D92",
                    f"pinned seed {seed} now hits the pre-existing "
                    "battle_ready saveBlob mismatch",
                    {"seed": seed, "error": str(e)[:200]})
            raise

        st = session.battle_state(host)
        fp = st.get("mapFingerprint")
        if fp != expected_fingerprint:
            session.known_flake(
                "test_rw_item_id_ctr", "WV-D91",
                f"pinned seed {seed} no longer reproduces the scenario - "
                "re-run hunt_seed.py",
                {"seed": seed, "expected_fingerprint": expected_fingerprint,
                 "actual_fingerprint": fp, "mapSizeXYZ": st.get("mapSizeXYZ")})

        # settle so both sides' battle_ready/onReady bookkeeping (phase ->
        # Active) - and with it the ADOPT hook, which runs during blob load,
        # well before this point - has landed. Same settle test_rw_hash_now.py
        # uses before its own t=0 introspection.
        time.sleep(2)

        host_es = host.cmd({"cmd": "event_state"})
        client_es = client.cmd({"cmd": "event_state"})
        assert host_es.get("ok") and client_es.get("ok"), \
            f"event_state failed: host={host_es} client={client_es}"
        assert host_es["phase"] == "Active" and client_es["phase"] == "Active", \
            f"both machines should be phase Active: host={host_es} client={client_es}"

        # --- positive control: the adopt mechanism actually engaged ---
        log_pairs = _adopted_derived_pairs(client)
        adopted_ctr = client_es.get("itemIdCtrAdopted", 0)
        assert adopted_ctr > 0 or log_pairs, (
            "positive control FAILED: neither event_state.itemIdCtrAdopted nor "
            "the client's own log shows an adopt - the ADOPT hook never ran, so "
            f"nothing below can prove anything. client event_state={client_es}")

        # --- SPEC 3 STOP-IF: the refusal guard must never fire in a clean run ---
        refused = client_es.get("itemIdCtrRefused", 0)
        assert refused == 0, (
            "SPEC 3 STOP-IF: coopLoadItemIdCtr hit the `carried < *live` branch "
            f"in a CLEAN two-machine run ({refused} time(s)) - the host's "
            "document is BEHIND the client's own derivation, which contradicts "
            f"the whole WV-D61 model. client event_state={client_es}")

        # --- hash_now full: itemIdCtr (and every other bucket) EQUAL ---
        host_h, client_h = session.assert_hash_clean(
            host, client, full=True, what=f"WV-D61 t=0 (seed {seed})")
        assert "itemIdCtr" in host_h and "itemIdCtr" in client_h, (
            f"itemIdCtr bucket missing from hash_now full: "
            f"host={sorted(host_h)} client={sorted(client_h)}")

        derived_diff = next(((c, d) for c, d in log_pairs if c != d), None)
        assert (derived_diff is not None) == expect_diverged, (
            f"pinned seed {seed}: expected "
            f"{'a genuine carried != derived discrepancy' if expect_diverged else 'carried == derived (no discrepancy)'} "
            f"but got derived_diff={derived_diff} (pairs={log_pairs})")

        tagres = ("derived=" + str(derived_diff)) if derived_diff else "agreed"
        print(f"[test_rw_item_id_ctr] seed {seed}: adopted={adopted_ctr} "
              f"refused={refused} itemIdCtr={host_h['itemIdCtr']} ({tagres})")
        return {
            "adopted": adopted_ctr,
            "refused": refused,
            "derived_diff": derived_diff,
            "itemIdCtr": host_h["itemIdCtr"],
        }
    finally:
        host.shutdown()
        client.shutdown()


def main():
    t0 = time.time()
    divergent = one_attempt(1, SEED_DIVERGENT, FINGERPRINT_DIVERGENT, expect_diverged=True)
    agreed = one_attempt(2, SEED_AGREED, FINGERPRINT_AGREED, expect_diverged=False)

    print(f"\n[test_rw_item_id_ctr] divergent boot (seed {SEED_DIVERGENT}) "
          f"produced a GENUINE discarded-id divergence (carried != derived) "
          f"before the adopt: derived_diff={divergent['derived_diff']} "
          "(non-vacuity by construction)")
    print(f"[test_rw_item_id_ctr] agreed boot (seed {SEED_AGREED}): "
          f"derived_diff={agreed['derived_diff']} (control - no discrepancy)")

    print(f"\ntest_rw_item_id_ctr: PASS (2/2 pinned boots - divergent seed "
          f"{SEED_DIVERGENT}, agreed seed {SEED_AGREED} - both itemIdCtr EQUAL "
          f"post-adopt, {time.time() - t0:.1f}s)")


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("test_rw_item_id_ctr", "WV-D90", str(e))
        print(f"\ntest_rw_item_id_ctr: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(EXIT_FAIL)
    except AssertionError as e:
        if str(e).startswith("FIXTURE:"):
            print(f"\ntest_rw_item_id_ctr: SKIP (fixture) - {e}")
            sys.exit(EXIT_SKIP)
        print(f"\ntest_rw_item_id_ctr: FAIL\nAssertionError: {e}")
        sys.exit(EXIT_FAIL)
    except TimeoutError as e:
        print(f"\ntest_rw_item_id_ctr: FAIL\nTimeoutError: {e}")
        sys.exit(EXIT_FAIL)
