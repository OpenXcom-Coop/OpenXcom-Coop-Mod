"""D246-U stage S-B row ED: a SEPARATE co-op campaign saved mid-battle by an OLDER version (the release line, `main`
651ae44ba), converted at the rewrite host's load (S-A), in which the guest dies: its death reaches its owner's world
and the host's memorial keeps no copy of it (owner D246 (b); D181 (a), D155 (a), F366; QD246-5 (a)).

Spec: docs repo rewrite/prompts/d246u_midbattle_save_convert.md section (f) test_d246u_old_battle_end_dead.py
(QD246-1 .. QD246-9 (a), orchestrator rulings 2026-10-12). Constants: rewrite/d246u-task0/sb/CONSTANTS.md (TASK 0 T0-4 / T0-5; the
DISPATCH NOTE's name pins F13300 / F13301: records found by id, never by a display name the partner world also has).
Fixture: tools/coop_test/fixtures/d246u_separate_battle.sav (S-A, unedited). The helpers are
test_d246u_old_battle_end.py's (the same construction; the S-A shared-file precedent).

Boot ED (key 46613, dirs d246u_ed_*): the host gets the fixture, the client an EMPTY dir. Construction as EA (load, the
conversion line == S-A's RS pin, the resume, the host's RESUME, the host's go); a miss prints ONE CAPTURE line and
FAILs every ED cell "boot".
  ED-kill      every live hostile killed (ids == HOSTILES), then the host's kill_unit_real {unit: GUEST}; the guest
               status 6 (DEAD) on both
  ED-end       host END TURN only (ED_CLIENT_PRESS False: with seat 1 dead the host's press closes the side, D-23,
               F13602); the host's NextTurnState closed; DebriefingState on both (the client's display-only)
  ED-return    the client's OK through its follow-ups -> its own GeoscapeState; battleEnd.sepReturn.deadApplied 1; the
               client's soldier_record {id: OWN_ID}: one record, dead true, where "dead" (the memorial); none in a base
               (D181) (RED at B1: deadApplied 0, the own soldier alive in its base)
  ED-memorial  the host's OK + b1.drain -> GeoscapeState; the host's soldier_record {id: COPY_ID} returns no record (the
               merged memorial copy removed) (RED at B1: the untagged release-line copy stays in the memorial)
  ED-common    every hash bucket EQUAL (taken after the guest's death, the last point both machines hold the battle);
               desyncSeen false on both, no new lane crash file and the client wrote no save (at the end)

One EVIDENCE line, then one PASS/FAIL line per cell, then the row verdict. Every cell runs after a failure; a cell whose
precondition failed FAILs "not reached". WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the
result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_d246u_old_battle_end_dead.py
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_d246u_old_battle_resume as rs  # noqa: E402
import test_d246u_old_battle_end as ea  # noqa: E402
import test_w2_battle_end_separate as b1  # noqa: E402

ED_KEY = "46613"
ED_CLIENT_PRESS = False           # TASK 0 T0-4 / T0-5: the host's END TURN alone closes the side (F13602)
ED_CELLS = ("ED-kill", "ED-end", "ED-return", "ED-memorial", "ED-common")


def dead_return_cell(client, ev, tag):
    geo = ea.client_ok(client, ev, tag)
    sep = b1.record(client).get("sepReturn") or {}
    recs = ea.own_records(client, sid=ea.OWN_ID)
    dead = [r for r in recs if r.get("dead") is True and r.get("where") == "dead"]
    base = [r for r in recs if r.get("where") == "base"]
    ev[f"{tag}Return"] = {"sepReturn": sep, "own": recs}
    ok = geo and sep.get("deadApplied") == 1 and len(recs) == 1 and len(dead) == 1 and not base
    return ok, geo, (f"client on its own GeoscapeState {geo}; sepReturn.deadApplied {sep.get('deadApplied')!r} "
                     f"(want 1); soldier_record {{id: {ea.OWN_ID}}} {[(r['where'], r['dead']) for r in recs]} (want exactly one, "
                     f"('dead', True); none in a base)")


def memorial_cell(host, ev, tag):
    reached, recs = ea.host_ok(host, ev, tag)
    return (reached and not recs, f"host on GeoscapeState {reached}; soldier_record {{id: {ea.COPY_ID}}} "
                                  f"{[(r['where'], r['dead'], r['coopName']) for r in recs]} (want no record)")


def row_ed(host, client, crash0, cells, ev):
    rs.attempt(cells, "ED-kill", lambda: ea.kill_cell(host, client, ev, "ed", guest_too=True), (host, client))
    rs.need(cells, "ED-kill")
    rs.attempt(cells, "ED-end", lambda: ea.end_cell(host, client, ev, "ed", client_press=ED_CLIENT_PRESS),
               (host, client))
    rs.need(cells, "ED-end")
    ok, geo, detail = dead_return_cell(client, ev, "ed")
    cells["ED-return"] = (ok, detail)
    if not geo:
        rs.capture("ED-return", detail[:300], (host, client))
        raise rs.NotReached("the client's OK did not reach its own geoscape")
    rs.attempt(cells, "ED-memorial", lambda: memorial_cell(host, ev, "ed"))
    cells["ED-common"] = ea.common_cell(host, client, crash0, ev, "ed")


def main():
    t0 = time.time()
    fails = ea.run_boot("ED", ED_CELLS, ED_KEY, "ed", row_ed)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_d246u_old_battle_end_dead: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
