"""A SEPARATE co-op campaign saved mid-battle by an older version and converted at the host's load, in which the
guest dies: its death reaches its owner's world and the host's memorial keeps no copy of it.

Fixture: tools/coop_test/fixtures/separate_battle.sav (unedited). Records are found by id, never by a display name the
partner world also has. The helpers and the construction are test_old_battle_end.py's.

One boot, row dead_guest_returns_home (key 46613, dirs old_battle_end_dead_*): the host gets the fixture, the client
an EMPTY dir. Construction as in test_old_battle_end.py (load, the conversion line == test_old_battle_resume.py's
values, the resume, the host's RESUME, the host's go); a miss prints ONE CAPTURE line and FAILs every cell "boot".
  kill_hostiles_and_guest  every live hostile killed (ids == HOSTILES), then the host's kill_unit_real {unit: GUEST};
                           the guest status 6 (DEAD) on both
  both_debriefings         host END TURN only (CLIENT_PRESS False: with seat 1 dead the host's press closes the
                           side); the host's NextTurnState closed; DebriefingState on both (the client's display-only)
  client_record_dead       the client's OK through its follow-ups -> its own GeoscapeState;
                           battleEnd.sepReturn.deadApplied 1; the client's soldier_record {id: OWN_ID}: one record,
                           dead true, where "dead" (the memorial); none in a base (without the fix: deadApplied 0,
                           the own soldier alive in its base)
  no_host_memorial_copy    the host's OK + BES.drain -> GeoscapeState; the host's soldier_record {id: COPY_ID} returns
                           no record (the merged memorial copy removed) (without the fix: the untagged older-version
                           copy stays in the memorial)
  common_checks            every hash bucket EQUAL (taken after the guest's death, the last point both machines hold
                           the battle); desyncSeen false on both, no new lane crash file and the client wrote no save
                           (at the end)

One EVIDENCE line, then one PASS/FAIL line per cell, then the row verdict. Every cell runs after a failure; a cell whose
precondition failed FAILs "not reached". ONE run is the result, no skip path; exit 0 only when every cell passes, else
2.

Run:  python tools/coop_test/test_old_battle_end_dead.py
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_old_battle_resume as OBR  # noqa: E402
import test_old_battle_end as OBE  # noqa: E402
import test_battle_end_separate as BES  # noqa: E402

KEY = "46613"
CLIENT_PRESS = False  # measured: the host's END TURN alone closes the side
CELLS = ("kill_hostiles_and_guest", "both_debriefings", "client_record_dead", "no_host_memorial_copy", "common_checks")


def dead_return_cell(client, ev, tag):
    geo = OBE.client_ok(client, ev, tag)
    sep = BES.record(client).get("sepReturn") or {}
    recs = OBE.own_records(client, sid=OBE.OWN_ID)
    dead = [r for r in recs if r.get("dead") is True and r.get("where") == "dead"]
    base = [r for r in recs if r.get("where") == "base"]
    ev[f"{tag}Return"] = {"sepReturn": sep, "own": recs}
    ok = geo and sep.get("deadApplied") == 1 and len(recs) == 1 and len(dead) == 1 and not base
    return ok, geo, (f"client on its own GeoscapeState {geo}; sepReturn.deadApplied {sep.get('deadApplied')!r} "
                     f"(want 1); soldier_record {{id: {OBE.OWN_ID}}} {[(r['where'], r['dead']) for r in recs]} "
                     f"(want exactly one, "
                     f"('dead', True); none in a base)")


def memorial_cell(host, ev, tag):
    reached, recs = OBE.host_ok(host, ev, tag)
    return (reached and not recs, f"host on GeoscapeState {reached}; soldier_record {{id: {OBE.COPY_ID}}} "
                                  f"{[(r['where'], r['dead'], r['coopName']) for r in recs]} (want no record)")


def row_dead_guest_returns_home(host, client, crash0, cells, ev):
    OBR.attempt(cells, "kill_hostiles_and_guest", lambda: OBE.kill_cell(host, client, ev, "end_dead", guest_too=True),
                (host, client))
    OBR.need(cells, "kill_hostiles_and_guest")
    OBR.attempt(cells, "both_debriefings",
                lambda: OBE.end_cell(host, client, ev, "end_dead", client_press=CLIENT_PRESS), (host, client))
    OBR.need(cells, "both_debriefings")
    ok, geo, detail = dead_return_cell(client, ev, "end_dead")
    cells["client_record_dead"] = (ok, detail)
    if not geo:
        OBR.capture("client_record_dead", detail[:300], (host, client))
        raise OBR.NotReached("the client's OK did not reach its own geoscape")
    OBR.attempt(cells, "no_host_memorial_copy", lambda: memorial_cell(host, ev, "end_dead"))
    cells["common_checks"] = OBE.common_cell(host, client, crash0, ev, "end_dead")


def main():
    t0 = time.time()
    fails = OBE.run_boot("dead_guest_returns_home", CELLS, KEY, "end_dead", row_dead_guest_returns_home)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_old_battle_end_dead: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
