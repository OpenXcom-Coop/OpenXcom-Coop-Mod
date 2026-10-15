#!/usr/bin/env python3
"""RV-U5 - the D229 hard gate (owner D229 (a) + gate, D250): every one of the 40 files the rewrite quarantined
(revisit-walk Row 10, tag census at 3a62c7309) is either DELETED with its scenario covered by named running tests, or
GREEN (present, unguarded and passing). Spec: docs repo rewrite/prompts/rvu5_sg_gate.md (Appendix C).

    python tools/coop_test/check_quarantine_gate.py                        # structural checks
    python tools/coop_test/check_quarantine_gate.py --results a.json ...   # + every named file PASS in those runs
    ... --allow-owned   # a guard listed in OWNED (held by its named unit) does not fail the run; never at the merge

Structural checks (always):
  S1  no file tools/coop_test/*.py has a column-0 SKIP-PENDING guard (run_parallel.GUARD_RE, copied) or prints
      SKIP-PENDING (a non-comment line holding both `print(` and `SKIP-PENDING`), except an OWNED file's own guard;
  S2  every DELETED row's file is absent and every one of its cover files is present;
  S3  every GREEN row's file is present;
  S4  tools/ci/run_coop_suite.ps1 keeps an empty CI quarantine list (`$quarantine = @()`);
  O   every OWNED row's file is present and still guarded, its tag naming SKIP-PENDING(<owner>). The owning unit lifts
      the guard and deletes the row in the same commit; a row whose guard is gone fails.
Result checks (only with --results; run_parallel.py / run_regression.py --json outputs, merged, the last record wins):
  R   every GREEN file not in OWNED, and every cover file of a DELETED row, has status PASS.
One line per check; exit 0 only when no check fails and OWNED is empty (or every open row is OWNED and --allow-owned
is given), else 2 (WV-D99 / WV-D100: no SKIP status).
"""

import argparse
import json
import os
import re
import sys

TESTDIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(TESTDIR))
GUARD_RE = re.compile(r"""^print\(\s*["']SKIP-PENDING""")   # = run_parallel.py GUARD_RE

# The 40. DELETED rows name the running files that cover their scenario (W1_TRIAGE.md, Dispositions (RV-U5));
# GREEN rows name the unit that lifted the guard.
DELETED = {
    "test_coop_debrief_sync": ["test_w2_battle_end"],
    "test_skirmish_end_main_menu": ["test_w2_battle_end"],
    "test_skirmish_debrief_disconnect": ["test_w2_battle_end"],
    "test_pvp_skirmish_turn_control": ["test_rw_faction_setup", "repro_atom_side_begin", "test_w2_client_pvp",
                                       "test_r5_pvp_gm3"],
    "test_pvp_skirmish_end_turn": ["repro_atom_side_begin", "test_r5_pvp_gm3"],
    "test_pvp_skirmish_win_lose": ["test_w2_battle_end_rules", "test_r5_pvp_rejoin", "test_r5_pvp_gm3"],
    "test_pvp_skirmish_rejoin": ["test_r5_pvp_rejoin"],
    "test_pvp_skirmish_psi": ["test_r5_pvp_react_mc", "test_r5_pvp_react_mc_gm3"],
    "test_pvp_skirmish_census": ["test_r5_pvp_rules"],
    "test_coop_pvp_blaster": ["test_r5_pvp_rules"],
    "test_battlescape_soldier_gift": ["test_r5_battle_gift", "test_r5_battle_gift_keep"],
    "test_vote_abort_battle": ["test_r4_abort_vote", "test_shared_battle"],
    "test_pvp_skirmish_abort": ["test_w2_battle_end_rules", "test_rv5_pvp_abort_cover"],
    "test_coop_door_sync": ["repro_door_deterministic"],
    "test_coop_ufo_door_close": ["repro_door_deterministic"],
    "test_coop_alien_launcher_item_loss": ["test_rv5_item_cover", "test_w2_client_grenade", "test_w2_ai_origins"],
    "test_coop_blast_item_damage": ["test_rv5_item_cover", "test_w2_host_combat_terrain", "test_w2_delta_items"],
    "test_coop_inventory_item_theft": ["test_rv5_item_cover", "test_w2_inventory", "test_w2_inventory_held"],
    "test_coop_double_turn_tu": ["test_rv5_item_cover", "test_w2_client_grenade"],
    "test_coop_proximity_item_sweep": ["test_rv5_item_cover", "test_w2_reaction_prox"],
    "test_coop_wait_banner": ["test_rv5_wait_cover", "test_r5_pvp_notices", "test_rw_feedback"],
}
GREEN = {
    "test_shared_month_run": "RV-U5 S-C",
    "test_shared_base_defense": "RV-U5 S-C",
    "test_battlescape_exit_palette": "RV-U5 S-D",
    "test_campaign_then_skirmish_debrief": "RV-U5 S-D",
    "test_pvp_skirmish_gamemode_selection": "R5-U9",
    "test_pvp_dogfight": "D250-U S-A",
    "test_pvp_duplicate_bases": "D250-U S-A",
    "test_pvp_campaign_bringup": "D250-U S-A",
    "test_pvp_campaign_geoscape": "D250-U S-A",
    "test_pvp_campaign_month": "D250-U S-A",
    "test_pvp_campaign_reconnect": "D250-U S-A",
    "test_pvp_campaign_battle": "D250-U S-B / S-C1",
    "test_pvp_campaign_ufo_spawn": "D250-U S-A2",
    "test_pvp_campaign_resume": "D246-U S-C + D250-U S-D",
    "test_coop_peer_equip_screens": "U6",
    "test_unload_weapon_crash": "U6",
    "test_shared_soldier_gift_dup": "R5-U5 S-B",
    "test_crash_reporter": "RV-U9",
    "test_shared_autoend_crashsite": "RV-U7",
}
# Guards still held by a named later unit: GREEN rows, and INCOMING = `main` files MG-C took in guarded (QSG-5). That
# unit lifts the guard and deletes its row here in the same commit; the gate without --allow-owned (MG-R) needs this
# dict empty.
INCOMING = {"test_coop_event_sync", "test_coop_mission_research", "test_coop_research_known_topic", "test_coop_research_sync", "test_coop_client_mission_abort", "test_coop_battle_start_sync", "test_coop_parallel_turns_latch", "test_skirmish_saved_battle_join", "test_skirmish_saved_pve2_end_turn"}
OWNED = {
    "test_pvp_campaign_resume": "D250-U S-D",
    "test_coop_event_sync": "MG-F",
    "test_coop_mission_research": "MG-F",
    "test_coop_research_known_topic": "MG-F",
    "test_coop_research_sync": "MG-F",
    "test_coop_client_mission_abort": "MG-P1",
    "test_coop_battle_start_sync": "MG-P1",
    "test_coop_parallel_turns_latch": "MG-P1",
    "test_skirmish_saved_battle_join": "MG-B",
    "test_skirmish_saved_pve2_end_turn": "R5-U8 S-D",
}
assert len(DELETED) + len(GREEN) == 40 and not set(DELETED) & set(GREEN) and set(OWNED) <= set(GREEN) | INCOMING


def path_of(name):
    return os.path.join(TESTDIR, name + ".py")


def load_results(paths):
    status = {}
    for p in paths:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        for rec in doc.get("results", []):
            status[rec.get("test")] = rec.get("status")
    return status


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", nargs="*", default=None, help="run_parallel / run_regression --json outputs")
    ap.add_argument("--allow-owned", action="store_true", help="an OWNED guard held as listed does not fail the run")
    args = ap.parse_args()
    fails, held = [], []

    # S1 (and O): no guard and no SKIP-PENDING print anywhere in the test tree, except an OWNED file's own guard
    seen = {}
    for fn in sorted(os.listdir(TESTDIR)):
        if not fn.endswith(".py") or fn == os.path.basename(__file__):
            continue
        with open(os.path.join(TESTDIR, fn), encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        g = [i + 1 for i, ln in enumerate(lines) if GUARD_RE.match(ln)]
        p = [i + 1 for i, ln in enumerate(lines)
             if not ln.lstrip().startswith("#") and "print(" in ln and "SKIP-PENDING" in ln and i + 1 not in g]
        seen[fn[:-3]] = (g, p, next((ln.strip() for ln in lines if "SKIP-PENDING(" in ln), ""))
    s1 = [(n, g, p) for n, (g, p, _) in sorted(seen.items()) if (g and n not in OWNED) or p]
    for n, g, p in s1:
        print("FAIL S1 %s.py: guard lines %s, SKIP-PENDING prints %s" % (n, g, p))
        fails.append("S1 " + n)
    if not s1:
        print("PASS S1 no SKIP-PENDING guard or print in tools/coop_test%s" % (" outside OWNED" if OWNED else ""))
    for name, owner in sorted(OWNED.items()):
        g, p, tag = seen.get(name, ([], [], ""))
        if name not in seen:
            print("FAIL O %s: file absent" % name)
            fails.append("O " + name)
        elif not g:
            print("FAIL O %s: no guard left; %s deletes its OWNED row in the commit that lifts the guard" % (name, owner))
            fails.append("O " + name)
        elif "SKIP-PENDING(%s)" % owner not in tag:
            print("FAIL O %s: guard tag %r does not name SKIP-PENDING(%s)" % (name, tag, owner))
            fails.append("O " + name)
        else:
            print("HELD O %s: guard line %s held by %s (%s)" % (name, g, owner, tag))
            held.append("%s (%s)" % (name, owner))

    # S2 / S3: the 40
    for name, covers in sorted(DELETED.items()):
        missing = [c for c in covers if not os.path.exists(path_of(c))]
        present = os.path.exists(path_of(name))
        ok = not present and not missing
        print("%s S2 DELETED %s (covers %s%s%s)" % ("PASS" if ok else "FAIL", name, ", ".join(covers),
                                                   "; missing " + ", ".join(missing) if missing else "",
                                                   "; file still present" if present else ""))
        if not ok:
            fails.append("S2 " + name)
    for name, unit in sorted(GREEN.items()):
        ok = os.path.exists(path_of(name))
        print("%s S3 GREEN %s (%s)%s" % ("PASS" if ok else "FAIL", name, unit, "" if ok else ": file absent"))
        if not ok:
            fails.append("S3 " + name)

    # S4: the CI quarantine list stays empty
    try:
        with open(os.path.join(REPO, "tools", "ci", "run_coop_suite.ps1"), encoding="utf-8", errors="replace") as f:
            src = f.read()
        ok = src.count("$quarantine = @()") == 1 and src.count("$quarantine = @(\n") == 0
    except OSError:
        ok = False
    print("%s S4 run_coop_suite.ps1 CI quarantine list empty" % ("PASS" if ok else "FAIL"))
    if not ok:
        fails.append("S4")

    # R: results
    if args.results is None:
        print("NOTE results not checked (no --results)")
    else:
        status = load_results(args.results)
        need = sorted((set(GREEN) - set(OWNED)) | {c for cs in DELETED.values() for c in cs})
        for name in need:
            st = status.get(name)
            print("%s R %s status %s" % ("PASS" if st == "PASS" else "FAIL", name, st))
            if st != "PASS":
                fails.append("R " + name)

    if fails:
        print("\nD229 gate: FAIL (%d failing checks)" % len(fails))
        return 2
    if held and not args.allow_owned:
        print("\nD229 gate: HELD (%d owned guard(s): %s; the owner lifts each)" % (len(held), ", ".join(held)))
        return 2
    print("\nD229 gate: PASS%s" % (" with %d owned guard(s) held (--allow-owned): %s" % (len(held), ", ".join(held))
                                   if held else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
