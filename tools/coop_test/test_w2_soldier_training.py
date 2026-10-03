"""W2-H18 (F3259, D226 a; spec rewrite/prompts/w2h18_psi_training_replica.md (e)-(f); TASK 0 w2h18-task0/CONSTANTS.md):
soldier training on the SHARED replica follows the host. Mod Coop_SoldierFx_Test: STR_H18_TRAINING (psiLabs 10, gym 10,
healthRecoveryPerDay 3) at (0, 3), index 9 (F6199). Boot A (SHARED): Phase M (option off) stages ids 1-8 psi at 0, ids 1-2
training, id 3 rtwh, id 4 healthMissing 30, rolls the month (4 host day rolls, F6205) -> H18-1..4; Phase D flips
anytimePsiTraining on (F6204), id 5 psi at 0, id 6 psi at 100 (finishes on the first roll) -> H18-5, H18-6. Boot B
(SEPARATE): H18-7 guard row. Levers client first (S25). Window: both probes every 0.5 s for 3 s from the hit, cells at its
end, the client's requests == S0. Clean (F6203): wait_resync_clear, drain client then host, 4 s, requests == S0.
RED: H18-1..6 fail on the client's cells, H18-7 passes; GREEN: all pass. "G:" = guard (a phase miss prints one CAPTURE).
EVIDENCE then PASS / FAIL per row; ONE run; exit 0 only if all pass, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_SoldierFx_Test")
BOOT_A = ("w2h18a", (49314, 49315, 47294))
BOOT_B = ("w2h18b", (49316, 49317), "47296")
FAC, FAC_IDX = "STR_H18_TRAINING", 9                  # TASK 0 F6199 / F6210
IDS = list(range(1, 9))
PHYS = ("tu", "stamina", "health", "firing", "throwing", "strength", "melee")    # Soldier::trainPhys
OPTS = ["anytimePsiTraining", "allowPsiStrengthImprovement", "psiStrengthEval"]
MRS, TFS, GEO = "MonthlyReportState", "TrainingFinishedState", "GeoscapeState"
WIN_S, WIN_I, CLEAN_S = 3.0, 0.5, 4.0

short = lambda e, n=600: (lambda s: s if len(s) <= n else s[:n] + "...")(f"{type(e).__name__}: {e}")  # noqa: E731
recs = lambda p: {s["id"]: s for s in p["soldiers"]}  # noqa: E731
stack = session.states_stripped
opts = lambda gc: gc.cmd({"cmd": "option_values", "ids": OPTS}).get("values", {})  # noqa: E731
psi = lambda r: (r["stats"]["psiSkill"], r["improvement"])  # noqa: E731
phys = lambda r: {k: r["stats"][k] for k in PHYS}  # noqa: E731
lever = lambda gc, sid, **kw: gc.ok(dict({"cmd": "set_soldier_training", "soldierId": sid}, **kw))["soldier"]  # noqa
on_geo = lambda *gcs: all(stack(gc)[-1:] == [GEO] for gc in gcs)  # noqa: E731
probe = lambda gc, ids=None: gc.ok(dict({"cmd": "soldier_training_probe"}, **({} if ids is None else {"ids": ids})))  # noqa
rs = lambda gc: {k: v for k, v in gc.cmd({"cmd": "shared_resync_stats"}).items() if k in ("requests", "pending")}  # noqa

class Miss(Exception):  # a phase guard missed: every row of the phase fails on it (one CAPTURE line printed)
    pass

def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = pred()
        if v:
            return v
        time.sleep(interval)
    return pred()
def date(gc):
    g = gc.cmd({"cmd": "geo_state"})
    t = g.get("time") or {}
    return {"t": "%s-%s-%s %s:%s" % tuple(t.get(k) for k in ("year", "month", "day", "hour", "minute")),
            "monthsPassed": g.get("monthsPassed")}
def fac_index(gc):
    facs = ((gc.cmd({"cmd": "geo_state"}).get("bases") or [{}])[0]).get("facilities") or []
    hits = [i for i, f in enumerate(facs) if (f.get("type"), f.get("x"), f.get("y")) == (FAC, 0, 3)]
    return hits[0] if hits else None
def capture(tag, x, why):
    cap = {}
    for gc in (x.host, x.client):
        try:
            cap[gc.name] = {k: gc.cmd({"cmd": k}) for k in ("soldier_training_probe", "geo_state", "shared_resync_stats")}
            cap[gc.name]["stack"] = stack(gc)
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {tag} ({why}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
def need(ph, x, name, ok, detail):
    if not ok:
        ph["miss"].append(f"{name}: {detail}")
        capture("phase " + ph["tag"], x, name)
        raise Miss(ph["miss"][-1])
    ph["guards"].append(name)
def stage(ph, x, want):  # want = {id: {field: value}}, client first; both machines' S0 records = the staged values
    for gc in (x.client, x.host):
        for i in IDS:
            lever(gc, i, **want[i])
    s0 = {gc.name: recs(probe(gc)) for gc in (x.host, x.client)}
    get = lambda r, f: r["stats"][f] if f == "psiSkill" else r[f]  # noqa: E731
    bad = [(n, i, f, get(s0[n][i], f), v) for n in s0 for i, fv in want.items() for f, v in fv.items()
           if get(s0[n][i], f) != v]
    need(ph, x, "stagedS0", not bad, f"(machine, id, field, got, want) {bad}")
    ph["S0"], ph["req0"] = s0, rs(x.client)["requests"]
    ph["ev"]["S0 requests"], ph["ev"]["dates S0"] = ph["req0"], {gc.name: date(gc) for gc in (x.host, x.client)}

def window(ph, x, top_watch=None):  # both probes every 0.5 s for 3 s; requests == S0; client top == top_watch from
    samples, t0, seen = [], time.time(), None
    while True:
        t = round(time.time() - t0, 2)
        s = {"t": t, "raw": {gc.name: probe(gc) for gc in (x.host, x.client)}, "req": rs(x.client)["requests"]}
        s["host"], s["client"] = recs(s["raw"]["host"]), recs(s["raw"]["client"])
        if top_watch and seen is None and stack(x.client)[-1:] == [top_watch]:
            seen = t
        samples.append(s)
        if t >= WIN_S:
            break
        time.sleep(WIN_I)
    ph["end"], ph["clientTop_s"] = {"host": samples[-1]["host"], "client": samples[-1]["client"]}, seen
    ph["ev"]["window [t, requests, host psiSkill 1-8, client psiSkill 1-8]"] = [
        [s["t"], s["req"]] + [[s[n][i]["stats"]["psiSkill"] for i in IDS] for n in ("host", "client")]
        for s in samples]
    for n in ("host", "client"):
        print(f"PROBE-END {ph['tag']} {n} t={samples[-1]['t']}: {json.dumps(samples[-1]['raw'][n], sort_keys=True)}",
              flush=True)
    reqs = sorted(set(s["req"] for s in samples))
    need(ph, x, "requestsWindow", reqs == [ph["req0"]], f"client requests {reqs} vs S0 {ph['req0']}")

def clean(ph, x):
    h, c = x.host, x.client
    for gc in ((h, c) if ph["tag"] == "D" else ()): gc.ok({"cmd": "geo_set_speed", "idx": 0})  # R-H18-2 (F6323, F6325)
    ph["ev"]["clean"] = cl = {"pendingWait": geo.wait_resync_clear(c, timeout=10)}
    cl["client"], cl["host"] = geo.drain_popups(c), geo.drain_popups(h)
    need(ph, x, "cleanGeoscape", wait_until(lambda: on_geo(h, c), 10, 0.2), f"stacks {stack(h)} / {stack(c)}")
    time.sleep(CLEAN_S)
    cl["requests"] = req = rs(c)
    if "req0" in ph:
        need(ph, x, "cleanRequests", req["requests"] == ph["req0"] and not req["pending"], f"{req} vs {ph['req0']}")

def month_roll(ph, x, host_top=True):  # set_geo_day 28 12; the host's MonthlyReportState; the client's, monthsPassed + 1
    h, c = x.host, x.client
    mp0 = date(c)["monthsPassed"]
    h.ok({"cmd": "set_geo_day", "day": 28, "hour": 12})
    sk = geo.skip_ingame_time(h, c, 60 * 24 * 5, speed_idx=5, interest=geo.popup(MRS), real_timeout=90)
    ph["ev"].update({"skip": {k: sk.get(k) for k in ("hit", "timed_out", "dismissed")},
                     "at hit": {gc.name: [date(gc), stack(gc)] for gc in (h, c)}})
    need(ph, x, "hostHit", sk.get("hit") is not None and (not host_top or stack(h)[-1:] == [MRS]),
         f"{sk.get('hit')} {stack(h)}")
    cm = wait_until(lambda: geo.drain_popups(c, interest=geo.popup(MRS))[1] and date(c)["monthsPassed"] == mp0 + 1, 10)
    need(ph, x, "clientMonthlyReport", cm, f"{stack(c)} monthsPassed {date(c)['monthsPassed']} (S0 {mp0})")

def phase_m(ph, x):
    h, c = x.host, x.client
    ph["ev"]["options"] = o = {gc.name: opts(gc) for gc in (h, c)}
    need(ph, x, "options", all(v.get(OPTS[0]) is False and v.get(OPTS[1]) is False for v in o.values()), o)
    ph["ev"]["fac_build"] = h.cmd({"cmd": "fac_build", "facility": FAC, "x": 0, "y": 3}).get("ok")
    ok = wait_until(lambda: fac_index(h) == FAC_IDX and fac_index(c) == FAC_IDX, 10)
    need(ph, x, "facilityListed", ok, f"index host {fac_index(h)} client {fac_index(c)} (want {FAC_IDX})")
    bt = {gc.name: gc.cmd({"cmd": "set_facility_build_time", "baseId": 0, "index": FAC_IDX, "time": 0})
          for gc in (c, h)}
    need(ph, x, "buildTime0", all(r.get("ok") and r.get("type") == FAC and r.get("buildTime") == 0
                                  for r in bt.values()), bt)
    ph["ev"]["capacities"] = caps = {gc.name: probe(gc, [])["bases"][0] for gc in (h, c)}
    need(ph, x, "capacities", all((b["psiLabs"], b["training"], b["healthRecovery"]) == (10, 10, 3)
                                  for b in caps.values()), caps)
    want = {i: {"psiTraining": True, "psiSkill": 0} for i in IDS}
    want[1]["training"] = want[2]["training"] = True
    want[3].update(training=False, rtwh=True)
    want[4]["healthMissing"] = 30
    stage(ph, x, want)
    month_roll(ph, x)
    window(ph, x)

def phase_d(ph, x):
    h, c = x.host, x.client
    ok = wait_until(lambda: not rs(c)["pending"] and on_geo(h, c), 10, 0.2)
    need(ph, x, "start", ok, f"stacks {stack(h)} / {stack(c)} replica {rs(c)}")
    ph["ev"]["optionRequest"] = h.cmd({"cmd": "synced_option_request", "id": OPTS[0], "value": True})
    ok = wait_until(lambda: all(opts(gc).get(OPTS[0]) is True for gc in (h, c)), 5)
    need(ph, x, "optionFlip", ok, {gc.name: opts(gc) for gc in (h, c)})
    want = {i: {"psiTraining": False, "training": False, "rtwh": False, "healthMissing": 0} for i in IDS}
    want[5].update(psiTraining=True, psiSkill=0)
    want[6].update(psiTraining=True, psiSkill=100)
    stage(ph, x, want)
    sk = geo.skip_ingame_time(h, c, 60 * 24 * 2, speed_idx=5, interest=geo.popup(TFS), real_timeout=60)
    ph["hostTopAtHit"] = stack(h)[-1:]
    ph["ev"].update({"skip": {k: sk.get(k) for k in ("hit", "timed_out", "dismissed")},
                     "at hit": {gc.name: [date(gc), stack(gc)] for gc in (h, c)}})
    need(ph, x, "hit", sk.get("hit") is not None, f"{sk.get('hit')} {stack(h)} / {stack(c)}")
    window(ph, x, top_watch=TFS)

class Row:
    def __init__(self, rid):
        self.rid, self.ev, self.fails, self.passed = rid, {}, [], []
    def cell(self, name, ok, detail=""):
        (self.passed.append(name) if ok else self.fails.append(f"{name}: {detail}"))
    def report(self, results):
        self.ev["cellsPassed"] = self.passed
        print(f"EVIDENCE {self.rid}: {json.dumps(self.ev, sort_keys=True, default=str)}", flush=True)
        results[self.rid] = not self.fails
        print(f"PASS {self.rid}" if not self.fails else
              f"FAIL {self.rid}: {len(self.fails)} cell(s): " + " | ".join(self.fails), flush=True)

def roster_cell(r, ph):
    h, c = ph["end"]["host"], ph["end"]["client"]
    d = [(i, k, h.get(i, {}).get(k), c.get(i, {}).get(k)) for i in sorted(set(h) | set(c))
         for k in sorted(set(h.get(i, {})) | set(c.get(i, {}))) if h.get(i, {}).get(k) != c.get(i, {}).get(k)]
    r.cell("roster", not d, f"{len(d)} (id, field, host, client) differ: {d[:10]}")
def row_1(r, ph):
    h, c = ph["end"]["host"], ph["end"]["client"]
    r.ev["(psiSkill, improvement) [host, client]"] = {i: [psi(h[i]), psi(c[i])] for i in IDS}
    r.cell("G:hostRolled", all(16 <= psi(h[i])[0] <= 24 and psi(h[i])[0] == psi(h[i])[1] for i in IDS),
           {i: psi(h[i]) for i in IDS})
    r.cell("G:clientMoved", all(c[i]["stats"]["psiSkill"] != 0 for i in IDS), {i: psi(c[i]) for i in IDS})
    diff = [i for i in IDS if psi(h[i]) != psi(c[i])]
    r.cell("psi", not diff, f"the replica rolled its own psi training: ids {diff} differ")
    roster_cell(r, ph)
def row_2(r, ph):
    h, c, s0 = ph["end"]["host"], ph["end"]["client"], ph["S0"]
    r.ev["physical ids 1-2 [S0 host, host, S0 client, client]"] = {
        i: [phys(s0["host"][i]), phys(h[i]), phys(s0["client"][i]), phys(c[i])] for i in (1, 2)}
    r.cell("G:hostTrained", all(sum(phys(h[i]).values()) > sum(phys(s0["host"][i]).values()) for i in (1, 2)),
           "host physical sum not above S0")
    same0 = all(phys(c[i]) == phys(s0["client"][i]) for i in (1, 2))
    r.cell("physical", all(phys(c[i]) == phys(h[i]) for i in (1, 2)),
           "the replica never trained (client == S0)" if same0 else "client != host")
def one(sid, name, get, gname, guard, red, red_txt):
    """A one-soldier row: host guard, then the client's value == the host's (red_txt when it is still `red`)."""
    def row(r, ph):  # noqa: E306
        h, c = get(ph["end"]["host"][sid]), get(ph["end"]["client"][sid])
        r.ev[f"id {sid} {name} [host, client]"] = [h, c]
        r.cell("G:" + gname, guard(h), h)
        r.cell(name, c == h, red_txt if c == red else f"client {c}")
    return row
row_3 = one(3, "(training, rtwh)", lambda s: [s["training"], s["rtwh"]], "hostReturned", lambda v: v == [True, False],
            [False, True], "the replica's id 3 is not back in training")
row_4 = one(4, "healthMissing", lambda s: s["healthMissing"], "hostRecovered", lambda v: v < 30, 30,
            "recovery stayed on the host")
row_5 = one(5, "psiSkill", lambda s: s["stats"]["psiSkill"], "hostDaily", lambda v: -60 <= v <= -30, 0,
            "the replica never ran daily psi training")
def row_6(r, ph):
    h, c = ph["end"]["host"], ph["end"]["client"]
    r.ev["id 6 psiTraining [host, client]"] = [h[6]["psiTraining"], c[6]["psiTraining"]]
    r.ev["improvement ids 1-8 [host, client]"] = [[h[i]["improvement"] for i in IDS], [c[i]["improvement"] for i in IDS]]
    r.ev["hostTopAtHit"], r.ev["clientTop_s"] = ph["hostTopAtHit"], ph["clientTop_s"]
    r.cell("G:hostFinished", h[6]["psiTraining"] is False, h[6]["psiTraining"])
    r.cell("G:hostWindow", ph["hostTopAtHit"] == [TFS], ph["hostTopAtHit"])
    r.cell("G:clientWindow", ph["clientTop_s"] is not None and ph["clientTop_s"] <= WIN_S, ph["clientTop_s"])
    r.cell("psiTraining", c[6]["psiTraining"] == h[6]["psiTraining"],
           f"the replica's id 6 psiTraining {c[6]['psiTraining']}")
    roster_cell(r, ph)
def run_phase(tag, fn, rows, x, results):
    ph, t0 = {"tag": tag, "ev": {}, "guards": [], "miss": []}, time.time()
    for step in (fn, clean):                     # the clean runs after a miss too, so the next phase starts clean
        try:
            step(ph, x)
        except Miss:
            pass
        except Exception as e:
            ph["miss"].append(f"exception in {step.__name__}: {short(e, 800)}")
            capture("phase " + tag, x, "exception")
    ph["ev"]["guardsPassed"], ph["ev"]["wallS"] = ph["guards"], round(time.time() - t0, 1)
    print(f"EVIDENCE phase {tag}: {json.dumps(ph['ev'], sort_keys=True, default=str)}", flush=True)
    for rid, rfn in rows:
        r = Row(rid)
        if "end" in ph:
            try:
                rfn(r, ph)
            except Exception as e:
                r.cell("exception", False, short(e, 800))
        for m in ph["miss"]:
            r.cell("G:phase " + tag, False, m)
        r.report(results)

def boot_miss(tag, e, rids, results):
    print(f"CAPTURE {tag} (boot miss): {short(e, 1500)}", flush=True)
    for rid in rids:
        results[rid] = False
        print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot", flush=True)

def boot_a(results, walls):
    (tag, ports), t0 = BOOT_A, time.time()
    rows = {"M": (("H18-1", row_1), ("H18-2", row_2), ("H18-3", row_3), ("H18-4", row_4)),
            "D": (("H18-5", row_5), ("H18-6", row_6))}
    try:
        js = shared_fixture.bring_up(tag, ports, mods=(MOD,))
    except Exception as e:
        return boot_miss(tag, e, [rid for rid, _f in rows["M"] + rows["D"]], results)
    walls[tag + " bring-up"] = round(time.time() - t0, 1)
    try:
        x = type("X", (), {"host": js.host, "client": js.client})
        run_phase("M", phase_m, rows["M"], x, results)
        run_phase("D", phase_d, rows["D"], x, results)
    finally:
        js.shutdown()
        walls[tag] = round(time.time() - t0, 1)

def row_7(ph, x, r):
    h, c = x.host, x.client
    p = probe(c)
    own = [s for s in p["soldiers"] if s["baseIndex"] == 0]
    need(ph, x, "ownBase", p["bases"][:1] and p["bases"][0]["index"] == 0 and own, p["bases"])
    sid = own[0]["id"]
    r.ev["soldier"], r.ev["staged"] = sid, lever(c, sid, psiTraining=True, psiSkill=0)          # client only
    r.ev["fac_build"] = c.cmd({"cmd": "fac_build", "facility": FAC, "x": 0, "y": 3}).get("ok")   # local in SEPARATE
    need(ph, x, "facilityListed", wait_until(lambda: fac_index(c) == FAC_IDX, 10), fac_index(c))
    bt = c.cmd({"cmd": "set_facility_build_time", "baseId": 0, "index": FAC_IDX, "time": 0})
    need(ph, x, "buildTime0", bt.get("ok") and bt.get("buildTime") == 0, bt)
    b0 = probe(c, [])["bases"][0]
    need(ph, x, "psiLabs", b0["psiLabs"] == 10, b0)
    ss = lambda: {gc.name: gc.cmd({"cmd": "shared_stats"}).get("applyCount") for gc in (h, c)}  # noqa: E731
    r.ev["applyCount before"] = ss()
    month_roll(ph, x, host_top=False)
    rec = probe(c, [sid])["soldiers"][0]
    r.ev["applyCount after"], r.ev["client soldier"] = ss(), rec
    r.cell("ownRoll", 16 <= rec["stats"]["psiSkill"] <= 24, f"(psiSkill, improvement) {psi(rec)}")

def boot_b(results, walls):
    (tag, labels, lobby), t0 = BOOT_B, time.time()
    h = GameClient("host", labels[0], make_user_dir(tag + "_host", mods=(MOD,)))
    c = GameClient("client", labels[1], make_user_dir(tag + "_client", mods=(MOD,)))
    x = type("X", (), {"host": h, "client": c})
    try:
        try:
            h.spawn(), c.spawn(), h.connect(), c.connect()
            session.new_campaign(h, c, port=lobby, campaign_mode="coop")
            geo.wait_both_ready(h, c)
        except Exception as e:
            return boot_miss(tag, e, ["H18-7"], results)
        walls[tag + " bring-up"] = round(time.time() - t0, 1)
        ph, r = {"tag": "B", "ev": {}, "guards": [], "miss": []}, Row("H18-7")
        try:
            row_7(ph, x, r)
        except Miss:
            r.cell("G:" + ph["miss"][-1].split(":")[0], False, ph["miss"][-1])
        except Exception as e:
            r.cell("exception", False, short(e, 800))
            capture("H18-7", x, "exception")
        r.ev["guardsPassed"], r.ev["phase"] = ph["guards"], ph["ev"]
        r.report(results)
    finally:
        shutdown_clients(h, c)
        walls[tag] = round(time.time() - t0, 1)

def main():
    t0, results, walls = time.time(), {}, {}
    boot_a(results, walls)
    boot_b(results, walls)
    order = ["H18-%d" % n for n in range(1, 8)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_w2_soldier_training: {len(order) - len(failed)}/{len(order)} passed (fail={failed}) walls {walls} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
