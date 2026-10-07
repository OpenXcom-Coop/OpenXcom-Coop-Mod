"""W2-H23 (F9871, F9874, F9904, F9913; spec rewrite/prompts/w2h23_separate_clock_boundary.md (f); TASK 0
rewrite/w2h23-task0/CONSTANTS.md): a SEPARATE second player's own geoscape loops skip or run twice, because the host's
"time" heartbeat moves its clock while its loops run only on its own step. Deterministic lever: the per-player
geoClockSpeed option (250 ms on the slow side, the default 80 ms on the other), no TestServer lever.
Boot S (lobby 47931; host 80 ms, client 250 ms): R1 day (wound recovery -1 a day, ROLL_DAY(4)), R2 hour (Skyranger
repair -1 an hour, ROLL_HOUR(6)), R4 jump guard (set_geo_day +2 / -1 day runs no day loop; both builds pass),
R5 month end (R-H23-G-2: SETTLE_AT(28, 12), roll to the host's MonthlyReportState; every client date sampled at B0,
while the client's report is open and for 3 s after both close is a valid calendar date (V1) and never moves backwards (M1)).
Boot F (lobby 47932; host 250 ms, client 80 ms): R3 day (ROLL_DAY(3), the double).
Each machine's loop counts are judged against its OWN clock B0 -> B1: the host's are guards (G1-G3), the client's are
RED (A1-A3); C1 = the client's clock within 1 game minute of the host's at B0 and B1; J1 also needs STAGE's replies.
FREEZE / RELEASE / SETTLE_AT / STAGE / READ / ROLL as the spec (f); W = 10 s at 0.1 s polls; a WAIT that times out ends
the row; every row RELEASEs in a finally. RED: R1 fails A1 only, R2 A2 only, R3 A3 only, R4 passes. R5 is red on
d089b0138 (V1 and M1: the monthly_report handler writes the host's month into the client's clock, 1999-02-31). GREEN: all pass.
CAPTURE (a failed row) then EVIDENCE then PASS / FAIL per row; every row runs; ONE run; exit 0 only if all pass, else 2.
"""

import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402

W, POLL, GEO, SOL, MRS = 10.0, 0.1, "GeoscapeState", "SoldiersState", "MonthlyReportState"
SLOW = {"geoClockSpeed": 250}
BOOT_S = ("w2h23_s", (49610, 49611), "47931", None, SLOW)
BOOT_F = ("w2h23_f", (49612, 49613), "47932", SLOW, None)
ORDER = ["R1", "R2", "R4", "R5", "R3"]
KEYS = "[elapsed days, elapsed hours, heal days, repair hours] host / client"

short = lambda e, n=600: (lambda s: s if len(s) <= n else s[:n] + "...")(f"{type(e).__name__}: {e}")  # noqa: E731
stack = session.states_stripped


class Halt(Exception):  # a WAIT timed out: the row ends there (later cells not reached)
    pass


def wait_until(pred, timeout=W, interval=POLL):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return round(time.time() - t0, 2)
        time.sleep(interval)
    return round(time.time() - t0, 2) if pred() else None


def top(gc):
    s = stack(gc)
    return s[-1] if s else ""


def gtime(gc):
    t = gc.cmd({"cmd": "geo_state"}).get("time") or {}
    return [t.get(k) for k in ("year", "month", "day", "hour", "minute")]


def dt(t):
    return datetime.datetime(*t)


def valid(t):  # a real calendar date (1999-02-31 is not)
    try:
        return bool(dt(t))
    except (TypeError, ValueError):
        return False


def apart(a, b):  # game minutes between two [year .. minute] times
    return abs((dt(a) - dt(b)).total_seconds()) / 60.0


def own_base(g):
    return next((b for b in g.get("bases") or [] if not b.get("coopBase") and not b.get("coopIcon")), None)


def own(gc):  # OWN: the first soldier_fx_probe soldier with baseIndex 0; the first craft of the first own base
    sols = [s["id"] for s in gc.ok({"cmd": "soldier_fx_probe"})["soldiers"] if s["baseIndex"] == 0]
    cr = ((own_base(gc.ok({"cmd": "geo_state"})) or {}).get("crafts") or [{}])[0]
    o = {"sid": sols[0] if sols else None, "craft": [cr.get("id"), cr.get("type")]}
    if o["sid"] is None or o["craft"] != [1, "STR_SKYRANGER"]:
        raise RuntimeError(f"OWN not found on {gc.name}: {o}")
    return o


def read(gc, o):  # READ: own clock, own soldier's recoveryExact, own craft's damage
    g = gc.cmd({"cmd": "geo_state"})
    s = (gc.cmd({"cmd": "soldier_fx_probe", "ids": [o["sid"]]}).get("soldiers") or [{}])[0]
    cr = next((c for c in (own_base(g) or {}).get("crafts") or [] if [c.get("id"), c.get("type")] == o["craft"]), {})
    t = g.get("time") or {}
    return {"time": [t.get(k) for k in ("year", "month", "day", "hour", "minute")],
            "recovery": s.get("recoveryExact"), "damage": cr.get("damage")}


def loops(b0, b1):  # one machine, its own clock: [calendar days, hour marks (truncated to the hour), heal days, repairs]
    t0, t1 = dt(b0["time"]), dt(b1["time"])
    hours = int((t1.replace(minute=0) - t0.replace(minute=0)).total_seconds() // 3600)
    return [(t1.date() - t0.date()).days, hours, round(b0["recovery"] - b1["recovery"], 3), b0["damage"] - b1["damage"]]


def log_tail(gc, n=20):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()[-n:]
    except OSError as e:
        return [f"log unreadable: {e}"]


class Row:
    def __init__(self, rid, x):
        self.rid, self.x, self.ev, self.fails, self.passed = rid, x, {"own": x.own, "waits": []}, [], []

    def cell(self, name, ok, detail=""):
        (self.passed.append(name) if ok else self.fails.append(f"{name}: {detail}"))
        return bool(ok)

    def wait(self, name, pred):
        t = wait_until(pred)
        self.ev["waits"].append([name, t])
        if t is None:
            self.fails.append(f"{name}: not met within {W:.0f} s (later cells not reached)")
            raise Halt(name)
        return t

    def report(self, results):
        if self.fails:
            capture(self)
        self.ev["cellsPassed"] = self.passed
        print(f"EVIDENCE {self.rid}: {json.dumps(self.ev, sort_keys=True, default=str)}", flush=True)
        results[self.rid] = not self.fails
        print(f"PASS {self.rid}" if not self.fails else
              f"FAIL {self.rid}: {len(self.fails)} cell(s): " + " | ".join(self.fails), flush=True)


def capture(r):
    cap = {"roll": r.ev.get("roll"), "reads": {b: r.ev[b] for b in ("B0", "B1", "B2") if b in r.ev}}
    for gc in (r.x.h, r.x.c):
        try:
            cap[gc.name] = {"stack": stack(gc), "time": gtime(gc), "log": log_tail(gc)}
        except Exception as e:
            cap[gc.name] = {"probe failed": short(e), "log": log_tail(gc)}
    print(f"CAPTURE {r.rid}: {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def freeze(r):  # both clocks still; the client holds the host's FINAL time (F9915)
    h, c = r.x.h, r.x.c
    c.cmd({"cmd": "open_screen", "screen": "soldiers"})
    r.wait("freeze1 client SoldiersState", lambda: top(c) == SOL)
    time.sleep(1.5)                                   # the host's clock stops 1 s after the client's last heartbeat
    h.cmd({"cmd": "open_screen", "screen": "soldiers"})
    r.wait("freeze3 host SoldiersState", lambda: top(h) == SOL)
    c.cmd({"cmd": "close_screens"})
    r.wait("freeze4 client GeoscapeState", lambda: top(c) == GEO)
    geo.drain_popups(c)
    r.wait("freeze5 clocks within 1 game minute", lambda: apart(gtime(h), gtime(c)) <= 1.0)
    time.sleep(0.5)


def release(r):
    r.x.h.cmd({"cmd": "close_screens"})
    r.wait("release both GeoscapeState", lambda: top(r.x.h) == GEO and top(r.x.c) == GEO)


def final_release(x):  # the row's finally: pop a SoldiersState a stopped row left on either machine
    return {gc.name: (gc.cmd({"cmd": "close_screens"}).get("popped") if top(gc) == SOL else 0) for gc in (x.c, x.h)}


def settle_at(r, day, hour):
    h, c = r.x.h, r.x.c
    freeze(r)
    rep = h.cmd({"cmd": "set_geo_day", "day": day, "hour": hour})
    r.ev.setdefault("set_geo_day [day, month]", []).append([rep.get("day"), rep.get("month")])
    release(r)
    r.wait(f"settle client adopts day {day} hour {hour}", lambda: gtime(c)[:4] == gtime(h)[:4])
    freeze(r)


def stage(r):  # client first (S25): wound recovery 60 days, own craft at damage 149 in repairs
    rep = {}
    for gc in (r.x.c, r.x.h):
        o = r.x.own[gc.name]
        a = gc.cmd({"cmd": "set_soldier_recovery", "soldierId": o["sid"], "days": 60})
        b = gc.cmd({"cmd": "craft_force", "damage": 149, "status": "STR_REPAIRS"})
        rep[gc.name] = [a.get("recovery"), b.get("ok"), b.get("craft_id")]
    r.ev["stage [recovery, craft ok, craft id]"] = rep
    return all(v == [60, True, r.x.own[n]["craft"][0]] for n, v in rep.items())


def reads(r, tag):
    r.ev[tag] = {gc.name: read(gc, r.x.own[gc.name]) for gc in (r.x.h, r.x.c)}
    return r.ev[tag]


def roll(r, minutes, speed):
    sk = geo.skip_ingame_time(r.x.h, r.x.c, minutes, speed_idx=speed, real_timeout=30)
    r.ev["roll"] = {k: sk.get(k) for k in ("game_minutes", "timed_out", "dismissed")}


def measure(r, minutes, speed):  # B0 (frozen, staged) -> RELEASE -> roll -> FREEZE -> B1 -> RELEASE
    ok = stage(r)
    b0 = reads(r, "B0")
    release(r)
    roll(r, minutes, speed)
    freeze(r)
    b1 = reads(r, "B1")
    release(r)
    lh, lc = loops(b0["host"], b1["host"]), loops(b0["client"], b1["client"])
    r.ev[KEYS] = [lh, lc]
    return ok, b0, b1, lh, lc


def miss(kind, ran, el):
    how = f"{el - ran} skipped" if ran < el else f"{ran - el} extra (run twice)"
    return f"the client's own {kind} loop ran {ran} times over its own {el} {kind}s: {how}"


def c1(r):
    gaps = [round(apart(r.ev[b]["host"]["time"], r.ev[b]["client"]["time"]), 2) for b in ("B0", "B1")]
    r.cell("C1", all(g <= 1.0 for g in gaps), f"client vs host clock gap (game minutes) at B0 / B1: {gaps}")


def day_row(r, ndays, dmin, red):  # R1 (slow client) and R3 (slow host)
    settle_at(r, 2, 12)
    ok, b0, b1, lh, lc = measure(r, ndays * 1440, 5)
    d, month = lh[0], [b0["host"]["time"][1], b1["host"]["time"][1]]
    rec = [b1["host"]["recovery"], b1["client"]["recovery"]]
    r.cell("setup", ok and d >= dmin and month[0] == month[1] and min(rec) > 0,
           f"stage ok {ok}, host days {d} (>= {dmin}), host month {month}, recoveries at B1 {rec}")
    r.cell("G1", lh[2] == d, f"host heal days {lh[2]} vs its {d} days")
    r.cell(red, lc[2] == lc[0], miss("day", lc[2], lc[0]) + f" (host days {d})")
    c1(r)


row_r1 = lambda r: day_row(r, 4, 2, "A1")  # noqa: E731  R1: ROLL_DAY(4), host days >= 2, boot S (slow client)
row_r3 = lambda r: day_row(r, 3, 1, "A3")  # noqa: E731  R3: ROLL_DAY(3), host days >= 1, boot F (slow host)


def row_r2(r):  # hour, slow client
    settle_at(r, 20, 1)
    ok, b0, b1, lh, lc = measure(r, 6 * 60, 4)
    hh, dmg = lh[1], [b1["host"]["damage"], b1["client"]["damage"]]
    r.cell("setup", ok and hh >= 3 and b0["host"]["time"][:3] == b1["host"]["time"][:3] and min(dmg) > 0,
           f"stage ok {ok}, host hours {hh} (>= 3), host date {b0['host']['time'][:3]} -> {b1['host']['time'][:3]}, "
           f"damages at B1 {dmg}")
    r.cell("G2", lh[3] == hh, f"host repair hours {lh[3]} vs its {hh} hours")
    r.cell("A2", lc[3] == lc[1], miss("hour", lc[3], lc[1]) + f" (host hours {hh})")
    r.cell("G3", lh[2] == 0 and lc[2] == 0, f"heal days host {lh[2]} / client {lc[2]} with no midnight")
    c1(r)


def row_r4(r):  # jump guard: a forward and a backward set_geo_day run no day loop on either machine
    h, c = r.x.h, r.x.c
    settle_at(r, 22, 12)
    ok = stage(r)
    reads(r, "B0")
    r.ev["jump +2 [day, month]"] = [h.cmd({"cmd": "set_geo_day", "day": 24, "hour": 12}).get(k) for k in ("day", "month")]
    release(r)
    t24 = r.wait("J3 client date day 24", lambda: gtime(c)[2] == 24)
    freeze(r)
    reads(r, "B1")
    r.ev["jump -1 [day, month]"] = [h.cmd({"cmd": "set_geo_day", "day": 23, "hour": 12}).get(k) for k in ("day", "month")]
    release(r)
    t23 = r.wait("J3 client date day 23", lambda: gtime(c)[2] == 23)
    freeze(r)
    reads(r, "B2")
    release(r)
    j = {}
    for a, b in (("B0", "B1"), ("B1", "B2")):
        j[a + "-" + b] = [loops(r.ev[a][n], r.ev[b][n])[2] for n in ("host", "client")]
    r.ev["heal days host / client"] = j
    r.cell("J1", ok and j["B0-B1"] == [0, 0], f"stage ok {ok}, heal days host / client {j['B0-B1']} over the +2 day jump")
    r.cell("J2", j["B1-B2"] == [0, 0], f"heal days host / client {j['B1-B2']} over the -1 day jump")
    r.cell("J3", True, f"client followed in {t24} s / {t23} s")


def row_r5(r):  # R-H23-G-2: across a month-end report the client's date stays a valid calendar date, never backwards
    h, c = r.x.h, r.x.c
    settle_at(r, 28, 12)
    smp = r.ev["samples [phase, client top, year .. minute]"] = [["B0", top(c)] + gtime(c)]
    release(r)
    sk = geo.skip_ingame_time(h, c, 5 * 1440, speed_idx=5, interest=geo.popup(MRS), real_timeout=60)
    r.ev["roll"] = {k: sk.get(k) for k in ("game_minutes", "timed_out", "dismissed", "hit")}
    r.wait("client MonthlyReportState", lambda: geo.drain_popups(c, interest=geo.popup(MRS))[1])
    for phase, secs in (("open", 0.5), ("closed", 3.0)):
        if phase == "closed":                         # close the client's report, then the host's
            for gc in (c, h):
                geo.drain_popups(gc)
            r.wait("both GeoscapeState", lambda: top(h) == GEO and top(c) == GEO)
        t0 = time.time()
        while time.time() - t0 < secs:
            smp.append([phase, top(c)] + gtime(c))
            time.sleep(POLL)
    bad = [s for s in smp if not valid(s[2:])]
    back = [[a, b] for a, b in zip(smp, smp[1:]) if b[2:] < a[2:]]
    r.cell("setup", sk.get("hit") is not None and gtime(h)[1] == 2 and smp[-1][3] == 2,
           f"roll hit {sk.get('hit')}, host {gtime(h)}, client last sample {smp[-1]}")
    r.cell("V1", not bad, f"client dates that are not calendar dates: {bad}")
    r.cell("M1", not back, f"client date moved backwards: {back}")


def run_row(rid, fn, x, results):
    r, t0 = Row(rid, x), time.time()
    try:
        fn(r)
    except Halt:
        pass
    except Exception as e:
        r.cell("exception", False, short(e, 800))
    finally:
        try:
            r.ev["finalRelease popped"] = final_release(x)
        except Exception as e:
            r.ev["finalRelease popped"] = short(e)
    r.ev["wallS"] = round(time.time() - t0, 1)
    r.report(results)


def boot(spec, rows, results, walls):
    (tag, labels, lobby, hopt, copt), t0 = spec, time.time()
    h = GameClient("host", labels[0], make_user_dir(tag + "_host", options=hopt))
    c = GameClient("client", labels[1], make_user_dir(tag + "_client", options=copt))
    x = type("X", (), {"h": h, "c": c, "own": {}})
    try:
        try:
            h.spawn(), c.spawn(), h.connect(), c.connect()
            session.new_campaign(h, c, port=lobby, campaign_mode="coop")
            geo.wait_both_ready(h, c)
            x.own = {gc.name: own(gc) for gc in (h, c)}
        except Exception as e:
            cap = {}
            for gc in (h, c):
                try:
                    cap[gc.name] = {"stack": stack(gc), "log": log_tail(gc)}
                except Exception as e2:
                    cap[gc.name] = {"probe failed": short(e2), "log": log_tail(gc)}
            print(f"CAPTURE {tag} (boot miss): {short(e, 1500)} {json.dumps(cap, default=str)}", flush=True)
            for rid, _fn in rows:
                results[rid] = False
                print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot", flush=True)
            return
        walls[tag + " bring-up"] = round(time.time() - t0, 1)
        for rid, fn in rows:
            run_row(rid, fn, x, results)
    finally:
        shutdown_clients(h, c)
        walls[tag] = round(time.time() - t0, 1)


def main():
    t0, results, walls = time.time(), {}, {}
    boot(BOOT_S, (("R1", row_r1), ("R2", row_r2), ("R4", row_r4), ("R5", row_r5)), results, walls)
    boot(BOOT_F, (("R3", row_r3),), results, walls)
    failed = [n for n in ORDER if not results.get(n)]
    print(f"\ntest_w2_separate_clock: {len(ORDER) - len(failed)}/{len(ORDER)} passed (fail={failed}) walls {walls} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
