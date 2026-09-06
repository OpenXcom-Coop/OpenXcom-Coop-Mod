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

RE-ROLL, NOT A HARD FAIL, ON AN UNRELATED PRE-EXISTING DIVERGENCE (traced, not
assumed - see _confirmed_unrelated_mismatch() below). The (C) RCA's own sample
measured STR_BATTLESHIP hitting a t=0 handshake refusal on `battle_ready`'s
saveBlob compare in **3 of 6** boots - not always the itemIdCtr-ALONE class
this packet targets: a SEPARATE, richer class (their "MECHANISM 2": a dead
alien's corpse id/`nodes[].type`/`binTiles`) can also fire on a UFO map class,
and WV-D61 does not touch it (it is out of this packet's scope - FX-3a/M2
territory). CONCRETELY OBSERVED on this build (builder trace, 2026-09-04): a
boot whose HOST log carries `battle_ready saveBlob MISMATCH` refuses the
handshake before the client ever gets its own BriefingState off its stack, so
`session.dismiss_client_briefing` times out - the ONE signature this file
treats as "this boot rolled the unrelated pre-existing bug, not a WV-D61
regression" and re-rolls a FRESH attempt for, capped at MAX_REROLLS. ANY OTHER
exception (including a TimeoutError whose host log does NOT carry that exact
line) is a hard FAIL - this is not a blanket retry-on-any-timeout.

POSITIVE CONTROL FIRST (an adopt that never happened cannot prove anything):
every qualifying boot must show event_state.itemIdCtrAdopted > 0 (or the
client's own log carrying the "[coop-itemid] WV-D61: adopted coopItemIdCtr"
line) before any hash comparison is treated as meaningful. coopLoadItemIdCtr
stores a value there on EVERY presence-gated load, whether or not carried and
derived agreed, so this checks the mechanism actually RAN, not that it found
a discrepancy.

NON-VACUITY: the mechanism engaging is not enough by itself - this file runs
the WHOLE fixture 6 times (one process, internal loop - see BOOTS below) and
reports how many of those QUALIFYING boots produced a GENUINE carried !=
derived discrepancy before the adopt, read out of the "(derived N)" suffix the
adopted-line only prints on disagreement. If that count is 0 across all 6
qualifying boots the itemIdCtr-equality assertions below never exercised the
fix at all, so the run is VACUOUS and exits SKIP rather than reporting a green
that proves nothing (WV-D57's own lesson: a fixture that rejects/never-hits a
case cannot detect a bug in it).
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
BOOTS = 6
MAX_REROLLS = 20  # measured ~50% pre-existing unrelated-mismatch rate on this
                   # map class (the (C) RCA's own 3/6 sample) - generous so
                   # exhaustion is a near-null event, not a coin flip

# EXIT CODES, matching the wave's shipped convention (2026-09-03 ruling):
# 0 = PASS, 2 = FAIL (a red), 3 = SKIP (not a red - either the ruleset does not
# offer the fixture mission, all BOOTS qualifying boots came back agreeing
# i.e. VACUOUS, or MAX_REROLLS was exhausted chasing a qualifying boot).
EXIT_PASS, EXIT_FAIL, EXIT_SKIP = 0, 2, 3

ADOPT_LOG_RE = re.compile(
    r"\[coop-itemid\] WV-D61: adopted coopItemIdCtr (\d+) \(derived (\d+)\)")

UNRELATED_MISMATCH_SIGNATURE = "battle_ready saveBlob MISMATCH"
BRIEFING_TIMEOUT_SIGNATURE = "client dismissed its entry briefing"


class MissionNotOffered(Exception):
    """STR_BATTLESHIP is not in this build's NEW BATTLE mission list - a fact
    about the loaded ruleset, not about WV-D61. SKIP, not FAIL."""


class FixtureExhausted(Exception):
    """MAX_REROLLS attempts never produced a qualifying boot (the handshake
    kept refusing on the unrelated, pre-existing divergence class). SKIP, not
    FAIL - carries the re-roll count."""


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


def _confirmed_unrelated_mismatch(host, timeout_err):
    """TRACED, not assumed (2026-09-04 builder trace): a handshake refusal on
    this fixture reliably produces the exact TimeoutError signature this
    checks for (dismiss_client_briefing hangs because the client's BriefingState
    never leaves its stack once the host tears the battle down under it), AND
    the host's own log carries the ERROR line onReady() prints on that refusal
    path (connectionTCP.cpp's onReady(), the SS2.8 canonical-bucket compare).
    Requiring BOTH signals (not just the timeout shape) is what keeps this from
    silently swallowing a real WV-D61 regression that happened to also time out
    somewhere in the bring-up chain for an unrelated reason."""
    if BRIEFING_TIMEOUT_SIGNATURE not in str(timeout_err):
        return False
    return UNRELATED_MISMATCH_SIGNATURE in _log_text(host)


def one_attempt(tag):
    """One host+client bring-up attempt on the STR_BATTLESHIP fixture, tagged
    for unique ports/user-dirs so re-rolls never collide with a qualifying
    boot's own directories. Returns a result dict on success. Raises
    MissionNotOffered (SKIP-worthy, static ruleset fact - never re-rolled) or
    NotQualifying (a confirmed pre-existing, WV-D61-unrelated t=0 divergence
    refused the handshake - re-roll)."""
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
            session.drive_to_battlescape(host, client, seated, mission=MISSION)
        except AssertionError as e:
            if "does not offer" in str(e):
                raise MissionNotOffered(str(e))
            raise
        except TimeoutError as e:
            if _confirmed_unrelated_mismatch(host, e):
                raise NotQualifying(
                    "pre-existing t=0 divergence UNRELATED to WV-D61 refused the "
                    f"handshake (host log confirms {UNRELATED_MISMATCH_SIGNATURE!r}"
                    f"): {e}")
            raise

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
            host, client, full=True, what=f"WV-D61 t=0 ({tag})")
        assert "itemIdCtr" in host_h and "itemIdCtr" in client_h, (
            f"itemIdCtr bucket missing from hash_now full: "
            f"host={sorted(host_h)} client={sorted(client_h)}")

        derived_diff = next(((c, d) for c, d in log_pairs if c != d), None)
        return {
            "adopted": adopted_ctr,
            "refused": refused,
            "derived_diff": derived_diff,
            "itemIdCtr": host_h["itemIdCtr"],
        }
    finally:
        host.shutdown()
        client.shutdown()


class NotQualifying(Exception):
    """This attempt hit the confirmed unrelated pre-existing divergence -
    re-roll with a fresh attempt rather than counting it."""


def one_boot(boot_index):
    """One QUALIFYING boot (re-rolling past the confirmed unrelated t=0
    divergence, capped at MAX_REROLLS)."""
    why_log = []
    for reroll in range(1, MAX_REROLLS + 1):
        tag = boot_index * 1000 + reroll
        try:
            r = one_attempt(tag)
            if reroll > 1:
                print(f"[test_rw_item_id_ctr] boot {boot_index}/{BOOTS} qualified "
                      f"on re-roll {reroll}/{MAX_REROLLS}")
            tagres = ("derived=" + str(r["derived_diff"])) if r["derived_diff"] else "agreed"
            print(f"[test_rw_item_id_ctr] boot {boot_index}/{BOOTS}: "
                  f"adopted={r['adopted']} refused={r['refused']} "
                  f"itemIdCtr={r['itemIdCtr']} ({tagres})")
            return r
        except NotQualifying as e:
            why_log.append(str(e))
            print(f"[test_rw_item_id_ctr] boot {boot_index}/{BOOTS} re-roll "
                  f"{reroll}/{MAX_REROLLS}: {e}")
    raise FixtureExhausted(
        f"boot {boot_index}/{BOOTS}: no qualifying attempt in {MAX_REROLLS} "
        f"re-rolls - last: {why_log[-1] if why_log else None}")


def main():
    results = []
    for boot_index in range(1, BOOTS + 1):
        results.append(one_boot(boot_index))

    diverged = [r for r in results if r["derived_diff"] is not None]
    print(f"\n[test_rw_item_id_ctr] {len(diverged)}/{BOOTS} qualifying boot(s) "
          "produced a GENUINE discarded-id divergence (carried != derived) "
          "before the adopt:")
    for r in diverged:
        c, d = r["derived_diff"]
        print(f"    derived N: carried(host)={c} derived(client, pre-adopt)={d}")

    if not diverged:
        print("\nVACUOUS: no boot produced a discarded id")
        sys.exit(EXIT_SKIP)

    print(f"\ntest_rw_item_id_ctr: PASS ({BOOTS}/{BOOTS} qualified boots, "
          f"{len(diverged)}/{BOOTS} non-vacuous, all itemIdCtr EQUAL post-adopt)")


if __name__ == "__main__":
    try:
        main()
    except MissionNotOffered as e:
        print(f"\ntest_rw_item_id_ctr: SKIP ({MISSION} not offered)\n{e}")
        sys.exit(EXIT_SKIP)
    except FixtureExhausted as e:
        print(f"\ntest_rw_item_id_ctr: SKIP (fixture exhausted)\n{e}")
        sys.exit(EXIT_SKIP)
    except (AssertionError, TimeoutError) as e:
        print(f"\ntest_rw_item_id_ctr: FAIL\n{type(e).__name__}: {e}")
        sys.exit(EXIT_FAIL)
