"""D246-U stage S-B row EA: a SEPARATE co-op campaign saved mid-battle by an OLDER version (the release line, `main`
651ae44ba), converted at the rewrite host's load (S-A), ends with the guest's record back in its owner's world and no
copy left in the host's world.

Spec: docs repo rewrite/prompts/d246u_midbattle_save_convert.md section (f) test_old_battle_end.py (QD246-1 ..
QD246-9 (a), orchestrator rulings 2026-10-12). Constants: rewrite/d246u-task0/sb/CONSTANTS.md (TASK 0 T0-2 .. T0-5; the
DISPATCH NOTE's name pins F13300 / F13301: every record is found by id and checked by coopName, never by a display name
the partner world also has, F13600). Fixture: tools/coop_test/fixtures/separate_battle.sav (S-A, unedited).

Boot EA (key 46612, dirs d246u_ea_*): the host gets the fixture, the client an EMPTY dir. Construction (preconditions,
not cells; a miss prints ONE CAPTURE line and FAILs every EA cell "boot"): host load_save_menu -> HostMenu; the one
conversion line == S-A's RS pin; the resume (S-A's RS-resume steps on key 46612); the host's RESUME (CoopState 60 / 62);
traditional mode with the host's go (coopEndTurnTally.activeSeat 0 on both).
  EA-kill       every live hostile killed by the host's kill_unit_real, b1.chain_settled after each: the ids ==
                HOSTILES, no live hostile on either machine
  EA-end        host END TURN -> coopEndTurnTally.activeSeat 1 on both; client END TURN; the host's NextTurnState
                closed; the host's DebriefingState (title DEBRIEF_TITLE) within 60 s; the client's display-only
                DebriefingState within 20 s
  EA-return     the client's OK through its follow-ups -> its own GeoscapeState; battleEnd.sepReturn == SEP_ALIVE; the
                client's soldier_record {id: OWN_ID}: missions == OWN_MISSIONS + 1, coopName == OWN_COOPNAME
                (RED at B1: guestsApplied 0, missions unchanged - the release line's copy carries no coop-origin tag)
  EA-own-world  the client's soldier_record {name} for each host squad name == exactly OWN_TWINS (the partner's own
                soldier of that name, coop 0): no host mirror in the client's own world (E4 (0); F13601)
  EA-copy       the host's OK + b1.drain -> GeoscapeState; no living soldier_record {id: COPY_ID} on the host
  EA-common     every hash bucket EQUAL (taken after the kills, the last point both machines hold the battle: after the
                debriefing a SEPARATE pair holds two worlds); desyncSeen false on both, no new lane crash file and the
                client wrote no save (at the end)

One EVIDENCE line, then one PASS/FAIL line per cell, then the row verdict. Every cell runs after a failure; a cell whose
precondition failed FAILs "not reached". run in the foreground to completion. ONE run is the
result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_old_battle_end.py
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, assert_hash_clean  # noqa: E402
import test_old_battle_resume as rs  # noqa: E402
import test_battle_end_separate as b1  # noqa: E402

EA_KEY = "46612"
RS_LINE = (rs.RS_PB, rs.RS_PM, rs.RS_SEATS[0], rs.RS_SEATS[1], rs.RS_UNSEATED, "traditional", rs.DEP_RS)
GUEST = rs.RS_GUEST               # the guest copy's battle unit (9)
COPY_ID = 9                       # the host world's release-line copy: "Guest Zzz", coopname "Gaston Faure", owner 999
OWN_ID, OWN_MISSIONS = 8, 0       # the client's own guest soldier (partner world id 8) and its saved missions
OWN_COOPNAME = "Gaston Faure"     # its coopName (TASK 0: 4 of 4 boots; "Guest Zzz" is only its display name, F13300)
# (id, coopName, coop) of the partner's own soldiers named as the host squad: no host mirror beside them
OWN_TWINS = {"Erno Bartok": [(1, "Erno Bartok", 0)], "Robin Berggren": [(2, "Robin Berggren", 0)],
             "Lyris Kollias": [(3, "Lyris Kollias", 0)]}
HOSTILES = list(range(1000000, 1000014))
DEBRIEF_TITLE = "Aliens defeated"
SEP_ALIVE = {"ownLoaded": 1, "guestsApplied": 1, "guestsMissing": 0, "pushed": 1}
STATUS_DEAD = 6
SETTLE_S, END_S, DEBRIEF_S, CLIENT_DEBRIEF_S = 45, 30, 60, 20
EA_CELLS = ("EA-kill", "EA-end", "EA-return", "EA-own-world", "EA-copy", "EA-common")


def hostiles(gc):
    return sorted(u["id"] for u in battle_state(gc).get("units", []) if u.get("faction") == 1 and not u.get("isOut"))


def seats(host, client):
    return [rs.tally_seat(gc) for gc in (host, client)]


def entry_mode(host, client, ev, tag):
    """Traditional mode with the host's go on both, bounded rs.MODE_S."""
    def ok():
        return [rs.es(gc, "turnMode") for gc in (host, client)] == ["traditional"] * 2 and seats(host, client) == [0, 0]
    _, s = rs.wait_until(ok, rs.MODE_S)
    got = [(rs.es(gc, "turnMode"), rs.tally_seat(gc)) for gc in (host, client)]
    ev[f"{tag}Mode"] = got
    return ok(), f"(turnMode, activeSeat) host/client {got} after {s} s (want traditional, 0 on both)"


def enter(host, client, key, ev, tag):
    """The boot's construction: load, the conversion line, the resume, the host's RESUME, the host's go. Returns None,
    or the miss (ONE CAPTURE line printed)."""
    steps = (("load", lambda: rs.load_cell(host, os.path.basename(rs.FIXTURE), ev, tag)),
             ("convert", lambda: rs.log_cell(host, ev, tag, RS_LINE)),
             ("resume", lambda: rs.resume_loaded(host, client, key, ev, tag)),
             ("click", lambda: rs.click_cell(host, client, ev, tag)),
             ("mode", lambda: entry_mode(host, client, ev, tag)))
    for name, fn in steps:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {str(e)[:500]}"
        if not ok:
            ev["bootMiss"] = f"{name}: {detail}"
            rs.capture(f"{tag.upper()} boot step {name}", detail[:300], (host, client))
            return ev["bootMiss"]
    return None


def kill_cell(host, client, ev, tag, guest_too=False):
    """Every live hostile killed by the host's kill_unit_real, the chain settled after each (b1.chain_settled); with
    `guest_too` the guest (GUEST) after them, status DEAD on both. Takes the common cell's hash once settled."""
    killed, unsettled = hostiles(host), []
    for uid in killed + ([GUEST] if guest_too else []):
        host.ok({"cmd": "battle_action", "action": "kill_unit_real", "unit": uid})
        if not b1.chain_settled(host, client, stable=1.0, timeout=SETTLE_S)[0]:
            unsettled.append(uid)
    live = [hostiles(host), hostiles(client)]
    status = [session.unit_of(gc, GUEST).get("status") for gc in (host, client)]
    ev[f"{tag}Kill"] = {"killed": killed, "unsettled": unsettled, "live": live, "guestStatus": status}
    ev[f"{tag}Hash"] = hash_now(host, client, tag)
    ok = killed == HOSTILES and not unsettled and live == [[], []]
    detail = (f"killed {len(killed)} hostiles {killed[:1]}..{killed[-1:]} (want HOSTILES {HOSTILES[0]}.."
              f"{HOSTILES[-1]}); unsettled {unsettled} (want none); live hostiles host/client {live} (want none)")
    if guest_too:
        ok = ok and status == [STATUS_DEAD] * 2
        detail += f"; guest {GUEST} status host/client {status} (want {STATUS_DEAD} on both)"
    return ok, detail


def hash_now(host, client, tag):
    try:
        assert_hash_clean(host, client, full=True, what=f"{tag}-common")
        return "all buckets EQUAL"
    except AssertionError as e:
        return str(e)[:400]


def end_cell(host, client, ev, tag, client_press=True):
    """Host END TURN; with `client_press` the baton passes (activeSeat 1 on both) and the client presses END TURN too;
    the host's NextTurnState closed; both debriefings (the client's display-only)."""
    host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    d = ev[f"{tag}End"] = {}
    if client_press:
        passed, d["passS"] = rs.wait_until(lambda: seats(host, client) == [1, 1], END_S, 0.2)
        d["seats"] = seats(host, client)
        if not passed:
            return False, f"tally activeSeat host/client {d['seats']} after {d['passS']} s (want 1 on both)"
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
    nt = b1.close_host_nextturn(host)
    d["nextTurn"] = nt if nt is None else nt.get("handled") or nt.get("error")
    hok, d["hostS"] = b1.wait_until(lambda: "DebriefingState" in b1.stack(host), DEBRIEF_S)
    title = host.cmd({"cmd": "debrief_state"}).get("title") if hok else None

    def client_shown():
        cd = client.cmd({"cmd": "debrief_state"})
        return cd.get("shown") is True and cd.get("onTop") is True and cd.get("displayOnly") is True
    cok, d["clientS"] = b1.wait_until(client_shown, CLIENT_DEBRIEF_S) if hok else (False, 0)
    d.update({"title": title, "hostStack": b1.stack(host), "clientStack": b1.stack(client)})
    return (hok and title == DEBRIEF_TITLE and cok,
            f"host DebriefingState {hok} after {d['hostS']} s, title {title!r} (want {DEBRIEF_TITLE!r}); client "
            f"display-only DebriefingState {cok} after {d['clientS']} s; NextTurnState {d['nextTurn']!r}")


def client_ok(client, ev, tag):
    """The client's OK through its follow-ups (b1.client_ok_through_followups) -> its own clean GeoscapeState."""
    ctx = {}
    ok1, geo, s = b1.client_ok_through_followups(client, ctx, "ret")
    ev[f"{tag}ClientOk"] = {"press": ok1, "geo": geo, "s": s, "chain": (ctx.get("ret") or {}).get("clientChain"),
                            "stack": b1.stack(client), "branch": b1.record(client).get("debriefOkBranch")}
    return bool(ok1.get("pressed") and (ok1.get("resp") or {}).get("handled") == "DebriefingState" and geo)


def own_records(gc, **kw):
    return [{k: r.get(k) for k in ("where", "id", "name", "coopName", "coop", "owner", "missions", "dead")}
            for r in b1.soldier_recs(gc, **kw)[0]]


def return_cell(client, ev, tag):
    geo = client_ok(client, ev, tag)
    sep = b1.record(client).get("sepReturn") or {}
    recs = own_records(client, sid=OWN_ID)
    got_sep = {k: sep.get(k) for k in SEP_ALIVE}
    rec = recs[0] if len(recs) == 1 else {}
    ev[f"{tag}Return"] = {"sepReturn": sep, "own": recs}
    ok = (geo and got_sep == SEP_ALIVE and len(recs) == 1 and rec.get("missions") == OWN_MISSIONS + 1
          and rec.get("coopName") == OWN_COOPNAME)
    return ok, geo, (f"client on its own GeoscapeState {geo}; sepReturn {got_sep} (want {SEP_ALIVE}); soldier_record "
                     f"{{id: {OWN_ID}}} {[(r['where'], r['missions'], r['coopName']) for r in recs]} (want one record "
                     f"with missions {OWN_MISSIONS + 1}, coopName {OWN_COOPNAME!r})")


def own_world_cell(client, ev, tag):
    got = {n: [(r["id"], r["coopName"], r["coop"]) for r in own_records(client, name=n)] for n in OWN_TWINS}
    ev[f"{tag}OwnWorld"] = got
    return got == OWN_TWINS, f"(id, coopName, coop) by host squad name {got} (want exactly {OWN_TWINS})"


def host_ok(host, ev, tag):
    """The host's OK + b1.drain -> GeoscapeState; returns (reached, the host's records of COPY_ID)."""
    p = b1.press_ok(host)
    reached, screens = b1.drain(host) if p["pressed"] else (False, [])
    recs = own_records(host, sid=COPY_ID)
    ev[f"{tag}HostOk"] = {"press": p, "reached": reached, "screens": [x.get("top") for x in screens],
                          "stack": b1.stack(host), "copy": recs,
                          "memorialRemoved": b1.record(host).get("memorialRemoved")}
    return reached, recs


def copy_cell(host, ev, tag):
    reached, recs = host_ok(host, ev, tag)
    alive = [r for r in recs if not r.get("dead")]
    return (reached and not alive, f"host on GeoscapeState {reached}; living soldier_record {{id: {COPY_ID}}} {alive} "
                                   f"(want none; all records {recs})")


def common_cell(host, client, crash0, ev, tag):
    hashed = ev.get(f"{tag}Hash")
    ds = [rs.es(host, "desyncSeen"), rs.es(client, "desyncSeen")]
    crash = sorted(session._crash_log_snapshot() - crash0)
    try:
        session.assert_client_zero_disk(client.user_dir)
        disk = "client wrote no save"
    except AssertionError as e:
        disk = str(e)[:200]
    ev[f"{tag}Common"] = {"hash": hashed, "desync": ds, "crash": crash, "disk": disk}
    return (hashed == "all buckets EQUAL" and ds == [False, False] and not crash and disk == "client wrote no save",
            f"hash after the kills {hashed}; desyncSeen {ds} (want False/False); new crash files {crash} (want none); "
            f"{disk}")


def row_ea(host, client, crash0, cells, ev):
    rs.attempt(cells, "EA-kill", lambda: kill_cell(host, client, ev, "ea"), (host, client))
    rs.need(cells, "EA-kill")
    rs.attempt(cells, "EA-end", lambda: end_cell(host, client, ev, "ea", client_press=True), (host, client))
    rs.need(cells, "EA-end")
    ok, geo, detail = return_cell(client, ev, "ea")
    cells["EA-return"] = (ok, detail)
    if not geo:
        rs.capture("EA-return", detail[:300], (host, client))
        raise rs.NotReached("the client's OK did not reach its own geoscape")
    rs.attempt(cells, "EA-own-world", lambda: own_world_cell(client, ev, "ea"))
    rs.attempt(cells, "EA-copy", lambda: copy_cell(host, ev, "ea"))
    cells["EA-common"] = common_cell(host, client, crash0, ev, "ea")


def run_boot(row, cells_order, key, slug, row_fn):
    """Spawn the pair (host with the fixture, client empty), the construction, then `row_fn(host, client, crash0,
    cells, ev)`; a boot miss FAILs every cell "boot" after its ONE CAPTURE line."""
    host = GameClient("host", None, make_user_dir(f"d246u_{slug}_host", saves=(rs.FIXTURE,)))
    client = GameClient("client", None, make_user_dir(f"d246u_{slug}_client"))
    crash0 = session._crash_log_snapshot()
    try:
        try:
            rs.boot(row, (host, client))
        except rs.Miss:
            return rs.fail_all(((row, cells_order),), f"boot (FIXTURE-STOP, see the CAPTURE {row} line)")
        ev = {}
        miss = enter(host, client, key, ev, slug)
        if miss:
            return rs.verdict(row, cells_order, {n: (False, f"boot (FIXTURE-STOP, see the CAPTURE line): {miss[:300]}")
                                                 for n in cells_order}, ev)
        cells = {}
        try:
            row_fn(host, client, crash0, cells, ev)
        except rs.NotReached as e:
            ev["error"] = str(e)
        except Exception as e:
            ev["error"] = f"{type(e).__name__}: {str(e)[:600]}"
        return rs.verdict(row, cells_order, cells, ev)
    finally:
        rs.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot("EA", EA_CELLS, EA_KEY, "ea", row_ea)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_old_battle_end: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
