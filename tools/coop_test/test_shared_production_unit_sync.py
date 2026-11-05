"""SHARED: each finished unit of a running production reaches the replica's stores in the hour the host makes it
(issue #134).

The scenario test_shared_month_run hit on 2026-08-02: the client starts 40x STR_LASER_PISTOL at 1 engineer through
the real ManufactureInfoState, and the first finished unit landed in the host's stores but never in the client's.
Two rows, each one hourly step on a running batch:

  mid_batch   unit 1 of 40 finishes on an ordinary hour.
  month_end   unit 2 finishes in the hour the month rolls, the same step that sends the monthly settlement.

Each row seeds the production's progress on both machines so the unit finishes on a known hourly step, rolls both
clocks at speed 1 until the host's stores show the unit, then holds the host on the Soldiers screen. Off the
geoscape the host sends no heartbeat, so the client cannot detect a mismatch and ask for a repair restream: the unit
has to arrive by the production's own message. The row then checks, for up to 3 s, that the client's stores, funds
and production match the host's, and that the client never asked for a resync (during the hold and for 4 s after
it). Ends with full world equality and the replica's zero-disk check.

Run:  python tools/coop_test/test_shared_production_unit_sync.py
"""

import calendar
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402

LASER = "STR_LASER_PISTOL"
QTY = 40                 # the issue's batch: still running after both rows
HOURS = 300              # STR_LASER_PISTOL manufacture time at 1 engineer
EVENT_HOLD_MINUTES = 60 * 24 * 60
ROLL_S, WIN_S, POST_S = 60.0, 3.0, 4.0
GEO, SS = "GeoscapeState", "SoldiersState"


def probe(gc):
    return gc.ok({"cmd": "prod_fx_probe"})


def laser(p):
    return (p.get("stores") or {}).get(LASER, 0)


def production(p):
    for q in p.get("productions") or []:
        if q.get("name") == LASER:
            return q
    return None


def resyncs(gc):
    return gc.cmd({"cmd": "shared_resync_stats"}).get("requests")


def top(gc):
    return (session.states_stripped(gc) or [""])[-1]


def geo_time(gc):
    return gc.ok({"cmd": "geo_state"})["time"]


def months(gc):
    return gc.ok({"cmd": "geo_state"})["monthsPassed"]


def speed(host, client, idx):
    for gc in (host, client):
        gc.cmd({"cmd": "geo_set_speed", "idx": idx})


def view(p):
    """The fields a unit changes on both machines."""
    q = production(p) or {}
    return {LASER: laser(p), "funds": p.get("funds"),
            "production": {k: q.get(k) for k in ("assigned", "amount", "infinite", "sell")}}


def evidence(tag, **kw):
    print(f"EVIDENCE {tag}: {json.dumps(kw, sort_keys=True, default=str)}", flush=True)


def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    last = pred()
    while not last and time.time() - t0 < timeout:
        time.sleep(interval)
        last = pred()
    return last


def set_progress(host, client, spent):
    for gc in (client, host):
        r = gc.ok({"cmd": "set_production_progress", "item": LASER, "timeSpent": spent})
        assert r.get("found"), f"{gc.name}: could not set {LASER} progress: {r}"


def unit_row(host, client, tag, want, before):
    """Roll to the unit, hold the host off the geoscape, then compare both machines."""
    speed(host, client, 1)
    t0 = time.time()
    drained = []

    def rolled():
        p = probe(host)
        if laser(p) >= want:
            return p
        # A popup on either machine stops the shared clock (a UFO detected mid-roll held one run at 22:xx for the
        # whole roll). Close it and resume; the monthly report is the row's own window and stays open.
        for gc in (host, client):
            if top(gc) not in (GEO, "MonthlyReportState"):
                d, _ = geo.drain_popups(gc, interest=geo.popup("MonthlyReportState"))
                drained.append([gc.name, d])
                gc.cmd({"cmd": "geo_set_speed", "idx": 1})
        return None
    hit = wait_until(rolled, ROLL_S)
    hold = host.cmd({"cmd": "open_screen", "screen": "soldiers"})
    roll_s = round(time.time() - t0, 2)
    assert hit, f"{tag}: the host made no unit {want} in {ROLL_S} s: {view(probe(host))}; drained {drained}; " \
        f"stacks {session.states_stripped(host)} / {session.states_stripped(client)}"
    assert hold.get("ok") and wait_until(lambda: top(host) == SS, 5.0), \
        f"{tag}: host hold failed: {hold}; stack {session.states_stripped(host)}"

    samples, reqs, t1 = [], [], time.time()
    matched = None
    while time.time() - t1 < WIN_S:
        h, c = probe(host), probe(client)
        reqs.append(resyncs(client))
        samples.append({"t": round(time.time() - t1, 2), "host": view(h), "client": view(c)})
        if matched is None and view(h) == view(c):
            matched = samples[-1]
        time.sleep(0.2)
    evidence(tag, rollS=roll_s, want=want, first=samples[0], last=samples[-1], matchedAt=matched and matched["t"],
             requests=reqs, before=before, drained=drained, stacks={gc.name: session.states_stripped(gc) for gc in (host, client)})
    h = samples[-1]["host"]
    assert h[LASER] == want, f"{tag}: host holds {h[LASER]} {LASER}, want {want}"
    assert all(q == before for q in reqs), \
        f"{tag}: the client asked for a resync during the hold (requests {reqs}, before {before})"
    assert matched, (f"{tag}: the finished unit never reached the client: host {samples[-1]['host']} != "
                     f"client {samples[-1]['client']} after {WIN_S} s with no resync")

    speed(host, client, 0)
    host.ok({"cmd": "pop_state"})  # only the hold: a monthly report under it closes through its own button below
    for gc in (host, client):
        geo.drain_popups(gc)
    post = []
    t2 = time.time()
    while time.time() - t2 < POST_S:
        post.append(resyncs(client))
        time.sleep(0.25)
    assert all(q == before for q in post), \
        f"{tag}: the client needed a repair restream after the hold (requests {post}, before {before})"
    print(f"PASS {tag}: unit {want} of {QTY} {LASER} reached the client in the hour the host made it "
          f"(matched at {matched['t']} s, no resync)")


def main():
    t_start = time.time()
    js = shared_fixture.bring_up("punit", (48820, 48821, 48120))
    host, client = js.host, js.client
    try:
        js.assert_world_equal("bootstrap")
        for gc in (host, client):
            gc.ok({"cmd": "discover_research", "topic": LASER})
        # no pending geoscape event may open a window (and stop the clock) inside a row
        for event in host.ok({"cmd": "geo_events"})["events"]:
            if not event["over"]:
                host.ok({"cmd": "set_event_countdown", "name": event["name"], "minutes": EVENT_HOLD_MINUTES})
        geo.slow_clock(host, client)

        pr = client.ok({"cmd": "manufacture_start", "item": LASER, "engineers": 1, "qty": QTY})
        assert pr.get("sent"), f"client manufacture_start not sent: {pr}"
        for gc in (host, client):
            gc.wait_for(f"{gc.name} lists {QTY}x {LASER} at 1 engineer",
                        lambda gc=gc: ((production(probe(gc)) or {}).get("assigned") == 1) or None,
                        timeout=30, interval=0.25)
        p_h, p_c = probe(host), probe(client)
        assert view(p_h) == view(p_c), f"baseline differs: host {view(p_h)} client {view(p_c)}"
        k = laser(p_h)
        before = resyncs(client)
        print(f"PASS setup: {QTY}x {LASER} running on both at 1 engineer; {k} in stores; client resync requests {before}")

        # mid_batch: the next hourly step makes unit 1
        set_progress(host, client, HOURS - 1)
        unit_row(host, client, "mid_batch", k + 1, before)

        # month_end: unit 2 finishes in the step that rolls the month
        t = geo_time(host)
        last_day = calendar.monthrange(t["year"], t["month"])[1]
        mp0 = months(host)
        host.ok({"cmd": "set_geo_day", "day": last_day, "hour": 22})
        set_progress(host, client, 2 * HOURS - 2)
        t = geo_time(host)
        p = production(probe(host)) or {}
        assert (t["day"], t["hour"]) == (last_day, 22) and p.get("timeSpent") == 2 * HOURS - 2, \
            f"month_end setup moved before the roll: time {t}, production {p}"
        unit_row(host, client, "month_end", k + 2, before)
        mh, mc = months(host), months(client)
        assert mh == mc == mp0 + 1, f"month_end: monthsPassed host {mh} client {mc}, want {mp0 + 1}"
        print(f"PASS month_end: the month rolled on both (monthsPassed {mh}) in the same step as the unit")

        js.finish()
        print(f"ALL SHARED PRODUCTION UNIT SYNC TESTS PASSED ({(time.time() - t_start) / 60.0:.1f} min)")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
