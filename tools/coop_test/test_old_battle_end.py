"""A SEPARATE co-op campaign saved mid-battle by an older version (two worlds), upgraded to one world and converted at
the host's load, ends with the client's soldier keeping this battle's record in the shared save and no battle copy
left.

Fixture: tools/coop_test/fixtures/separate_battle.sav (the file test_old_battle_resume.py loads, unedited). Every
record is found by id and checked by coopName, never by a display name the partner world also has.

One boot, row guest_returns_home (key 46612, dirs old_battle_end_*): the host gets the fixture, the client an EMPTY
dir. Construction (preconditions, not cells; a miss prints ONE CAPTURE line and FAILs every cell "boot"): the
fixture through the save upgrade (test_old_battle_resume.upgrade_save), host load_save_menu of the upgraded save ->
HostMenu; the one conversion line == CONVERT_LINE (test_old_battle_resume.py's values); the resume
(test_old_battle_resume.py's resume steps on key 46612); the host's RESUME (CoopState 60 / 62); traditional mode with
the host's go (coopEndTurnTally.activeSeat 0 on both).
  kill_hostiles           every live hostile killed by the host's kill_unit_real, BES.chain_settled after each: the
                          ids == HOSTILES, no live hostile on either machine
  both_debriefings        host END TURN -> coopEndTurnTally.activeSeat 1 on both; client END TURN; the host's
                          NextTurnState closed; the host's DebriefingState (title DEBRIEF_TITLE) within 60 s; the
                          client's display-only DebriefingState within 20 s
  client_record_updated   the client's OK through its follow-ups -> its GeoscapeState; soldier_record {name:
                          GUEST_NAME} on each machine: exactly one record, living, in a base, the client's (owner
                          CLIENT_SEAT), with missions == OWN_MISSIONS + 1, the same on both machines (the battle copy
                          fought this battle; its record is the client's soldier's)
  no_host_copy            the host's OK + BES.drain -> GeoscapeState; no living soldier_record {id: COPY_ID} on the
                          host (the battle copy is gone)
  common_checks           every hash bucket EQUAL (taken after the kills); desyncSeen false on both, no new lane
                          crash file and the client wrote no save (at the end)

One EVIDENCE line, then one PASS/FAIL line per cell, then the row verdict. Every cell runs after a failure; a cell whose
precondition failed FAILs "not reached". ONE run is the result, no skip path; exit 0 only when every cell passes, else
2.

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
import test_old_battle_resume as OBR  # noqa: E402
import battle_end_helpers as BES  # noqa: E402

KEY = "46612"
CONVERT_LINE = (OBR.PARTNER_SNAPSHOTS, OBR.PARTNER_MIRRORS, OBR.SEATED[0], OBR.SEATED[1], OBR.UNSEATED, "traditional",
                OBR.DEPLOYMENT)
GUEST = OBR.GUEST_UNIT            # the guest copy's battle unit (9)
COPY_ID = 9                       # the older version's battle copy of the client's soldier: owner 999, coop 1
GUEST_NAME, OWN_MISSIONS = "Guest Zzz", 0   # the client's own soldier (one record once upgraded) and its saved missions
CLIENT_SEAT = 1                   # the client's soldier's owner in the upgraded save
HOSTILES = list(range(1000000, 1000014))
DEBRIEF_TITLE = "Aliens defeated"
STATUS_DEAD = 6
SETTLE_S, END_S, DEBRIEF_S, CLIENT_DEBRIEF_S = 45, 30, 60, 20
CELLS = ("kill_hostiles", "both_debriefings", "client_record_updated", "no_host_copy", "common_checks")


def hostiles(gc):
    return sorted(u["id"] for u in battle_state(gc).get("units", []) if u.get("faction") == 1 and not u.get("isOut"))


def seats(host, client):
    return [OBR.tally_seat(gc) for gc in (host, client)]


def entry_mode(host, client, ev, tag):
    """Traditional mode with the host's go on both, bounded OBR.MODE_S."""
    def ok():
        return ([OBR.es(gc, "turnMode") for gc in (host, client)] == ["traditional"] * 2
                and seats(host, client) == [0, 0])
    _, s = OBR.wait_until(ok, OBR.MODE_S)
    got = [(OBR.es(gc, "turnMode"), OBR.tally_seat(gc)) for gc in (host, client)]
    ev[f"{tag}Mode"] = got
    return ok(), f"(turnMode, activeSeat) host/client {got} after {s} s (want traditional, 0 on both)"


def load_upgraded(host, ev, tag):
    """The fixture through the save upgrade (OBR.upgrade_save), then the host's load of the upgraded save."""
    up, save, why = OBR.upgrade_save(host, os.path.basename(OBR.FIXTURE), ev, tag)
    return OBR.load_cell(host, save, ev, tag) if up else (False, why)


def enter(host, client, key, ev, tag):
    """The boot's construction: load, the conversion line, the resume, the host's RESUME, the host's go. Returns None,
    or the miss (ONE CAPTURE line printed)."""
    steps = (("load", lambda: load_upgraded(host, ev, tag)),
             ("convert", lambda: OBR.log_cell(host, ev, tag, CONVERT_LINE)),
             ("resume", lambda: OBR.resume_loaded(host, client, key, ev, tag)),
             ("click", lambda: OBR.click_cell(host, client, ev, tag)),
             ("mode", lambda: entry_mode(host, client, ev, tag)))
    for name, fn in steps:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {str(e)[:500]}"
        if not ok:
            ev["bootMiss"] = f"{name}: {detail}"
            OBR.capture(f"{tag.upper()} boot step {name}", detail[:300], (host, client))
            return ev["bootMiss"]
    return None


def kill_cell(host, client, ev, tag, guest_too=False):
    """Every live hostile killed by the host's kill_unit_real, the chain settled after each (BES.chain_settled); with
    `guest_too` the guest (GUEST) after them, status DEAD on both. Takes the common cell's hash once settled."""
    killed, unsettled = hostiles(host), []
    for uid in killed + ([GUEST] if guest_too else []):
        host.ok({"cmd": "battle_action", "action": "kill_unit_real", "unit": uid})
        if not BES.chain_settled(host, client, stable=1.0, timeout=SETTLE_S)[0]:
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
        passed, d["passS"] = OBR.wait_until(lambda: seats(host, client) == [1, 1], END_S, 0.2)
        d["seats"] = seats(host, client)
        if not passed:
            return False, f"tally activeSeat host/client {d['seats']} after {d['passS']} s (want 1 on both)"
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
    nt = BES.close_host_nextturn(host)
    d["nextTurn"] = nt if nt is None else nt.get("handled") or nt.get("error")
    hok, d["hostS"] = BES.wait_until(lambda: "DebriefingState" in BES.stack(host), DEBRIEF_S)
    title = host.cmd({"cmd": "debrief_state"}).get("title") if hok else None

    def client_shown():
        cd = client.cmd({"cmd": "debrief_state"})
        return cd.get("shown") is True and cd.get("onTop") is True and cd.get("displayOnly") is True
    cok, d["clientS"] = BES.wait_until(client_shown, CLIENT_DEBRIEF_S) if hok else (False, 0)
    d.update({"title": title, "hostStack": BES.stack(host), "clientStack": BES.stack(client)})
    return (hok and title == DEBRIEF_TITLE and cok,
            f"host DebriefingState {hok} after {d['hostS']} s, title {title!r} (want {DEBRIEF_TITLE!r}); client "
            f"display-only DebriefingState {cok} after {d['clientS']} s; NextTurnState {d['nextTurn']!r}")


def client_ok(client, ev, tag):
    """The client's OK through its follow-ups (BES.client_ok_through_followups) -> its clean GeoscapeState."""
    ctx = {}
    ok1, geo, s = BES.client_ok_through_followups(client, ctx, "ret")
    ev[f"{tag}ClientOk"] = {"press": ok1, "geo": geo, "s": s, "chain": (ctx.get("ret") or {}).get("clientChain"),
                            "stack": BES.stack(client), "branch": BES.record(client).get("debriefOkBranch")}
    return bool(ok1.get("pressed") and (ok1.get("resp") or {}).get("handled") == "DebriefingState" and geo)


def own_records(gc, **kw):
    return [{k: r.get(k) for k in ("where", "id", "name", "coopName", "coop", "owner", "missions", "dead")}
            for r in BES.soldier_recs(gc, **kw)[0]]


def guest_records(host, client, ev, tag):
    """soldier_record {name: GUEST_NAME} on both machines (host first); EVIDENCE."""
    recs = [own_records(gc, name=GUEST_NAME) for gc in (host, client)]
    ev[f"{tag}Guest"] = recs
    return recs


def return_cell(host, client, ev, tag):
    geo = client_ok(client, ev, tag)
    hrecs, crecs = guest_records(host, client, ev, tag)
    want = [("base", CLIENT_SEAT, False, OWN_MISSIONS + 1)]
    got = [[(r["where"], r["owner"], r["dead"], r["missions"]) for r in rr] for rr in (hrecs, crecs)]
    ok = geo and got == [want, want] and hrecs == crecs
    return ok, geo, (f"client on its GeoscapeState {geo}; soldier_record {{name: {GUEST_NAME!r}}} (where, owner, dead, "
                     f"missions) host / client {got} (want {want} on both: the client's soldier keeps this battle); "
                     f"records equal on both {hrecs == crecs}")


def host_ok(host, ev, tag):
    """The host's OK + BES.drain -> GeoscapeState; returns (reached, the host's records of COPY_ID)."""
    p = BES.press_ok(host)
    reached, screens = BES.drain(host) if p["pressed"] else (False, [])
    recs = own_records(host, sid=COPY_ID)
    ev[f"{tag}HostOk"] = {"press": p, "reached": reached, "screens": [x.get("top") for x in screens],
                          "stack": BES.stack(host), "copy": recs,
                          "memorialRemoved": BES.record(host).get("memorialRemoved")}
    return reached, recs


def copy_cell(host, ev, tag):
    reached, recs = host_ok(host, ev, tag)
    alive = [r for r in recs if not r.get("dead")]
    return (reached and not alive, f"host on GeoscapeState {reached}; living soldier_record {{id: {COPY_ID}}} {alive} "
                                   f"(want none; all records {recs})")


def common_cell(host, client, crash0, ev, tag):
    hashed = ev.get(f"{tag}Hash")
    ds = [OBR.es(host, "desyncSeen"), OBR.es(client, "desyncSeen")]
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


def row_guest_returns_home(host, client, crash0, cells, ev):
    OBR.attempt(cells, "kill_hostiles", lambda: kill_cell(host, client, ev, "end"), (host, client))
    OBR.need(cells, "kill_hostiles")
    OBR.attempt(cells, "both_debriefings", lambda: end_cell(host, client, ev, "end", client_press=True),
                (host, client))
    OBR.need(cells, "both_debriefings")
    ok, geo, detail = return_cell(host, client, ev, "end")
    cells["client_record_updated"] = (ok, detail)
    if not geo:
        OBR.capture("client_record_updated", detail[:300], (host, client))
        raise OBR.NotReached("the client's OK did not reach its geoscape")
    OBR.attempt(cells, "no_host_copy", lambda: copy_cell(host, ev, "end"))
    cells["common_checks"] = common_cell(host, client, crash0, ev, "end")


def run_boot(row, cells_order, key, slug, row_fn):
    """Spawn the pair (host with the fixture, client empty), the construction, then `row_fn(host, client, crash0,
    cells, ev)`; a boot miss FAILs every cell "boot" after its ONE CAPTURE line."""
    host = GameClient("host", None, make_user_dir(f"old_battle_{slug}_host", saves=(OBR.FIXTURE,)))
    client = GameClient("client", None, make_user_dir(f"old_battle_{slug}_client"))
    crash0 = session._crash_log_snapshot()
    try:
        try:
            OBR.boot(row, (host, client))
        except OBR.Miss:
            return OBR.fail_all(((row, cells_order),), f"boot (setup failure, see the CAPTURE {row} line)")
        ev = {}
        miss = enter(host, client, key, ev, slug)
        if miss:
            return OBR.verdict(row, cells_order,
                               {n: (False, f"boot (setup failure, see the CAPTURE line): {miss[:300]}")
                                for n in cells_order}, ev)
        cells = {}
        try:
            row_fn(host, client, crash0, cells, ev)
        except OBR.NotReached as e:
            ev["error"] = str(e)
        except Exception as e:
            ev["error"] = f"{type(e).__name__}: {str(e)[:600]}"
        return OBR.verdict(row, cells_order, cells, ev)
    finally:
        OBR.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot("guest_returns_home", CELLS, KEY, "end", row_guest_returns_home)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_old_battle_end: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
