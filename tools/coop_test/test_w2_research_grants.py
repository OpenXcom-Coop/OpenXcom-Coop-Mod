"""W2-H17c (F7222, F7224, F7225; D226 a): research granted outside the lab (a despawned mission site, a monthly arc script)
reaches the second player, and the monthly roll carries the ended month's research score. Spec docs
rewrite/prompts/w2h17c_research_grants.md (e)-(f) + ORCHESTRATOR RULINGS; TASK 0 rewrite/w2h17c-task0/CONSTANTS.md
(R-H17c-T0-1..3). Test mod Coop_ResearchGrant_Test. Boot A (SHARED): H17c-1 a host-only terror site (hours 1) despawns
untouched (research + getOneFree, diary, counter, score, despawn event); H17c-2 the month-1 arc grants STR_H17C_ARC and
opens its article, then the ended month's score after both rolled. Boot B (SEPARATE): H17c-3 (guard row). Row frame: S0
(research_probe, geo_event_probe, requests R0); poll both every 0.25 s for 3 s while a host window is open (F7230); clean =
settle + 60 game-min at speed 3 + 4 s: requests == R0, checksum equal. RED (commit 1): H17c-1/2 fail on their named cells,
H17c-3 passes; "G:" cells are guards (CAPTURE on a miss). GREEN: all pass. EVIDENCE then PASS / FAIL per row; ONE run;
exit 0 only if all pass, else 2.
"""

import json
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_ResearchGrant_Test")
BOOT_A = ("w2h17ca", (49370, 49371, 47360))      # SHARED; lobby 47360 (F7232)
BOOT_B = ("w2h17cb", (49372, 49373, 47362))      # SEPARATE; lobby 47362
DESPAWN, FREE, ARC, CNT = "STR_H17C_DESPAWN", "STR_H17C_FREE", "STR_H17C_ARC", "STR_H17C_DESPAWN_CNT"
NAMES = [DESPAWN, FREE, ARC]
MISSION, FREE_FROM = 3, 1                        # research_probe diary sourceType
WANT_DIARY = [[DESPAWN, MISSION, "STR_TERROR_MISSION"], [FREE, FREE_FROM, DESPAWN]]
POLL_S, POLL_I, LIST_S, HIT_S, DAY_S, ROLL_S, CLEAN_S = 3.0, 0.25, 40, 150, 5, 10, 4.0
EVENT, ARTICLE, GEO = "GeoscapeEventState", "ArticleState", "GeoscapeState"
SS_KEYS = ("cmd", "okCount", "failCount", "applyCount", "unknownCount", "applyQueued")

class GuardMiss(Exception):
    """A guard failed: the row ends after its CAPTURE line."""

def short(e, n=500):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."

def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while not pred() and time.time() - t0 < timeout:
        time.sleep(interval)
    return bool(pred())

def pick(d, *keys): return {k: d.get(k) for k in keys}  # noqa: E704
def stack(gc): return session.states_stripped(gc)  # noqa: E704
def top(gc): return (stack(gc) or [""])[-1]  # noqa: E704
def geo_s(gc): return gc.cmd({"cmd": "geo_state"})  # noqa: E704
def sites(gc): return [s["id"] for s in geo_s(gc).get("missionSites", [])]  # noqa: E704
def rs(gc): return pick(gc.cmd({"cmd": "shared_resync_stats"}), "requests", "pending", "mismatches")  # noqa: E704
def ss(gc): return pick(gc.cmd({"cmd": "shared_stats"}), *SS_KEYS)  # noqa: E704
def chk(gc): return {k: v for k, v in gc.cmd({"cmd": "shared_checksum"}).items() if k.startswith("chk")}  # noqa: E704
def rp(gc): return pick(gc.cmd({"cmd": "research_probe", "names": NAMES, "tail": 8}), "researched", "diary", "ids")  # noqa: E704
def gp(gc): return pick(gc.cmd({"cmd": "geo_event_probe", "names": NAMES, "items": [], "tail": 8}),  # noqa: E704
                        "eventStates", "pendingWindows", "researchScore", "researchScores", "ids", "research")
def pedia(gc): return pick(gc.cmd({"cmd": "pedia_state", "ids": [ARC]}), "top", "kind", "depth", "article")  # noqa: E704
def nscores(gc): return len(gp(gc).get("researchScores") or [])  # noqa: E704

def dump(gc):
    out = {}
    for k, f in (("research_probe", lambda: rp(gc)), ("geo_event_probe", lambda: gp(gc)), ("pedia_state", lambda: pedia(gc)),
                 ("get_state", lambda: stack(gc)), ("shared_resync_stats", lambda: gc.cmd({"cmd": "shared_resync_stats"})),
                 ("shared_stats", lambda: ss(gc)), ("sites", lambda: sites(gc))):
        try:
            out[k] = f()
        except Exception as e:
            out[k] = short(e)
    return out

def capture(rid, why, x):
    cap = json.dumps({gc.name: dump(gc) for gc in (x.host, x.client)}, sort_keys=True, default=str)
    print(f"CAPTURE {rid} ({why}): {cap}", flush=True)

class Row:
    def __init__(self, rid, x):
        self.rid, self.x, self.ev, self.fails, self.passed, self.captured = rid, x, {}, [], [], False
    def cell(self, name, ok, detail=""):
        (self.passed.append(name) if ok else self.fails.append(f"{name}: {detail}"))
        return ok
    def guard(self, name, ok, detail, stop=True):
        self.cell("G:" + name, ok, detail)
        if stop:
            self.stop_on_miss()
    def stop_on_miss(self):
        miss = [f.split(":")[1] for f in self.fails if f.startswith("G:")]
        if miss:
            capture(self.rid, "guard " + ",".join(miss), self.x)
            self.captured = True
            raise GuardMiss(miss[0])

def sample(gc, pedia_too=False):
    p, g = rp(gc), gp(gc)
    s = {"res": p.get("researched") or {}, "diary": p.get("diary") or {}, "cnt": (p.get("ids") or {}).get(CNT),
         "score": g.get("researchScore"), "scores": g.get("researchScores"), "ev": g.get("eventStates"), "top": top(gc)}
    if pedia_too:
        s["article"] = pedia(gc).get("article")
    return s

def poll(x, pedia_too=False):
    """Both machines every POLL_I for POLL_S (a sample of both costs ~0.5-0.75 s, TASK 0)."""
    out, t0 = [], time.time()
    while time.time() - t0 < POLL_S:
        ts = time.time()
        out.append({"t": round(ts - t0, 2), "h": sample(x.host, pedia_too), "c": sample(x.client, pedia_too)})
        time.sleep(max(0.0, POLL_I - (time.time() - ts)))
    return out

def snap(x, pedia_too=False):
    out = {}
    for gc in (x.host, x.client):
        out[gc.name] = {"research_probe": rp(gc), "geo_event_probe": gp(gc), "requests": rs(gc)["requests"], "stack": stack(gc)}
        if pedia_too:
            out[gc.name]["pedia_state"] = pedia(gc)
    return out

def seen(ps, k, f):
    out = []
    for s in ps:
        if (v := f(s[k])) not in out:
            out.append(v)
    return out

def both(ps, f): return {"host": seen(ps, "h", f), "replica": seen(ps, "c", f)}  # noqa: E704
def triples(d): return [[e.get("name"), e.get("sourceType"), e.get("sourceName")] for e in (d.get("tail") or [])]  # noqa: E704

def dismiss_to_geo(gc, limit=12):
    """dismiss_popup until the geoscape is on top (<= limit); never while this machine's resync is pending (W2-U7)."""
    done = []
    for _ in range(limit):
        t = top(gc)
        if not t or t.endswith(GEO):
            break
        geo.wait_resync_clear(gc)
        r = gc.cmd({"cmd": "dismiss_popup"})
        done.append(r.get("handled") or r.get("type") or r.get("error") or t)
        time.sleep(0.05 if r.get("ok") else 0.3)
    return {"dismissed": done, "top": top(gc)}

def skip(x, minutes, interest):
    t = time.time()
    sk = geo.skip_ingame_time(x.host, x.client, minutes, speed_idx=5, interest=geo.popup(interest), real_timeout=HIT_S)
    return {"hit": sk.get("hit"), "gameMin": sk.get("game_minutes"), "s": round(time.time() - t, 2),
            "dismissed": sk.get("dismissed")}

def spawn_site(gc):
    b0 = next(b for b in geo_s(gc)["bases"] if not b.get("coopBase") and not b.get("coopIcon"))
    return gc.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION",
                  "lon": b0["lon"] + 0.40, "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 1})["site_id"]

def clean(r, x, r0):
    st = geo.settle(x.host, x.client)
    sk = geo.skip_ingame_time(x.host, x.client, 60, speed_idx=3)
    time.sleep(CLEAN_S)
    cl = r.ev["clean"] = {"dismissed": st.get("dismissed"), "gameMin": sk.get("game_minutes"), "R0": r0,
                          "requests": rs(x.client)["requests"], "chkHost": chk(x.host), "chkClient": chk(x.client)}
    r.cell("clean", cl["requests"] == r0 and bool(cl["chkHost"]) and cl["chkHost"] == cl["chkClient"],
           f"replica requests {r0} -> {cl['requests']}, chk host {cl['chkHost']} / replica {cl['chkClient']}")

def row_1(r, x):
    """H17c-1 despawn (Boot A): the host-only site despawns untouched; every cell read while both event windows are open."""
    h, c = x.host, x.client
    sid = spawn_site(h)
    r.guard("listed", wait_until(lambda: sid in sites(h) and sid in sites(c), LIST_S, 0.2),
            f"site {sid}: host {sites(h)} / replica {sites(c)}")
    s0 = r.ev["S0"] = snap(x)
    sk = r.ev["skip"] = skip(x, 240, EVENT)
    r.guard("hit", sk["hit"] is not None, f"no {EVENT} within {HIT_S} s: {sk}")
    ps = poll(x)
    r.ev["end"] = snap(x)
    sc0 = {k: s0[gc.name]["geo_event_probe"].get("researchScore") for k, gc in (("h", h), ("c", c))}
    p0, n = ps[0], len(ps)
    ev = r.ev["seen"] = {"res": both(ps, lambda v: [v["res"].get(DESPAWN), v["res"].get(FREE)]),
                         "diarySize": both(ps, lambda v: v["diary"].get("size")), "cnt": both(ps, lambda v: v["cnt"]),
                         "score": both(ps, lambda v: v["score"]), "ev": both(ps, lambda v: v["ev"]), "S0score": sc0,
                         "samples": n, "t": [s["t"] for s in ps]}
    r.guard("hostResearched", p0["h"]["res"].get(DESPAWN) and p0["h"]["res"].get(FREE), f"{ev['res']}", stop=False)
    r.guard("hostDiary", triples(p0["h"]["diary"])[-2:] == WANT_DIARY, f"{triples(p0['h']['diary'])}", stop=False)
    r.guard("hostCounter", p0["h"]["cnt"] == 2, f"{ev['cnt']}", stop=False)
    r.guard("hostScore", p0["h"]["score"] == sc0["h"] + 10, f"S0 {sc0} {ev['score']}", stop=False)
    r.guard("eventStates", all(s["h"]["ev"] == 1 and s["c"]["ev"] == 1 for s in ps), f"{ev['ev']}")
    r.cell("despawn", any(all(s[k]["res"].get(t) for k in "hc" for t in (DESPAWN, FREE)) for s in ps),
           f"the despawn research never reached the second player (F7222): DESPAWN/FREE {ev['res']}")
    r.cell("diary", any(s["c"]["diary"] == s["h"]["diary"] for s in ps),
           f"research diary differs: sizes {ev['diarySize']} (S0 {s0['client']['research_probe']['diary'].get('size')}), "
           f"replica tail {triples(ps[-1]['c']['diary'])}")
    r.cell("counter", any(s["h"]["cnt"] == 2 and s["c"]["cnt"] == 2 for s in ps), f"{CNT} differs: {ev['cnt']}")
    r.cell("score", any(s["h"]["score"] == s["c"]["score"] for s in ps), f"research score differs: {ev['score']} S0 {sc0}")
    r.ev["dismiss"] = {"client": dismiss_to_geo(c), "host": dismiss_to_geo(h)}
    clean(r, x, s0["client"]["requests"])

def row_2(r, x):
    """H17c-2 arc at the month end (Boot A): the month-1 arc on the host, its article, and the ended month's score."""
    h, c = x.host, x.client
    r.ev["setDay"] = h.cmd({"cmd": "set_geo_day", "day": 31, "hour": 22})
    r.guard("clientDay31", wait_until(lambda: (geo_s(c).get("time") or {}).get("day") == 31, DAY_S),
            f"host {geo_s(h).get('time')} / replica {geo_s(c).get('time')}")
    s0 = r.ev["S0"] = snap(x, True)
    n0 = len(s0["host"]["geo_event_probe"].get("researchScores") or [])
    sk = r.ev["skip"] = skip(x, 180, ARTICLE)
    r.guard("hit", sk["hit"] is not None, f"no {ARTICLE} within {HIT_S} s: {sk}")
    ps = poll(x, True)
    r.ev["end"] = snap(x, True)
    ev = r.ev["seen"] = {"arc": both(ps, lambda v: v["res"].get(ARC)), "article": both(ps, lambda v: v["article"]),
                         "top": both(ps, lambda v: v["top"]), "scores": both(ps, lambda v: v["scores"]), "samples": len(ps),
                         "t": [s["t"] for s in ps]}
    r.guard("hostArc", ps[0]["h"]["res"].get(ARC) and ps[0]["h"]["article"] == ARC, f"{ev['arc']} {ev['article']}")
    r.cell("arc", any(s["c"]["res"].get(ARC) and s["c"]["article"] == ARC for s in ps),
           f"the arc research and its article never reached the second player (F7224): ARC {ev['arc']} article {ev['article']}")
    r.ev["clientDismiss"] = dismiss_to_geo(c)
    r.guard("bothRolled", wait_until(lambda: nscores(h) == n0 + 1 and nscores(c) == nscores(h), ROLL_S),
            f"S0 length {n0}; host {gp(h).get('researchScores')} / replica {gp(c).get('researchScores')}")
    hs, cs = gp(h).get("researchScores") or [], gp(c).get("researchScores") or []
    r.ev["rolled"] = {"host": hs, "replica": cs, "hostMinusReplica": hs[-2] - cs[-2], "stacks": [stack(h), stack(c)]}
    r.cell("scoreEnded", hs[-2] == cs[-2], f"the month's research score differs from the host's (F7225): host {hs} / replica {cs}")
    r.cell("scoreNew", hs[-1] == cs[-1], f"new month: host {hs} / replica {cs}")
    st = geo.settle(h, c)                     # the host's chain: article, report, save, CoopState wait (R-H17c-T0-2)
    r.ev["hostWindows"] = {"dismissed": st.get("dismissed"), "stalled": st.get("stalled")}
    clean(r, x, s0["client"]["requests"])

def row_3(r, x):
    """H17c-3 SEPARATE guard (Boot B): a despawn in the host's own world changes only the host's world."""
    h, c = x.host, x.client
    sid = spawn_site(h)
    s0 = r.ev["S0"] = {gc.name: {"research_probe": rp(gc), "shared_stats": ss(gc), "sites": sites(gc)} for gc in (h, c)}
    r.ev["site"] = sid
    sk = r.ev["skip"] = skip(x, 240, EVENT)
    r.guard("hit", sk["hit"] is not None, f"no {EVENT} within {HIT_S} s: {sk}")
    ps = poll(x)
    r.ev["end"] = snap(x)
    r.ev["dismiss"] = {"host": dismiss_to_geo(h), "client": dismiss_to_geo(c)}
    fin = r.ev["final"] = {gc.name: {"research_probe": rp(gc), "shared_stats": ss(gc)} for gc in (h, c)}
    ev = r.ev["seen"] = {"res": both(ps, lambda v: v["res"].get(DESPAWN)), "ev": both(ps, lambda v: v["ev"]),
                         "diarySize": both(ps, lambda v: v["diary"].get("size")), "samples": len(ps)}
    r.cell("hostDespawn", fin["host"]["research_probe"]["researched"].get(DESPAWN), f"{ev['res']}")
    r.cell("clientNot", not any(s["c"]["res"].get(DESPAWN) for s in ps)
           and not fin["client"]["research_probe"]["researched"].get(DESPAWN), f"{ev['res']}")
    c0, c1 = s0["client"]["research_probe"]["diary"].get("size"), fin["client"]["research_probe"]["diary"].get("size")
    r.cell("clientDiary", c1 == c0, f"S0 {c0} final {c1} {ev['diarySize']}")
    r.cell("sharedStats", all(fin[n]["shared_stats"] == s0[n]["shared_stats"] for n in ("host", "client")),
           f"S0 / final {[(s0[n]['shared_stats'], fin[n]['shared_stats']) for n in ('host', 'client')]}")

def run_row(rid, fn, x, results):
    r = Row(rid, x)
    try:
        fn(r, x)
    except GuardMiss:
        pass
    except Exception as e:
        r.cell("exception", False, short(e, 800))
        if not r.captured:
            capture(rid, "exception", x)
    if any(f.startswith(("G:", "exception")) for f in r.fails):
        try:
            geo.settle(x.host, x.client)
        except Exception as e:
            r.ev["settleAfterMiss"] = short(e)
    r.ev["cellsPassed"] = r.passed
    print(f"EVIDENCE {rid}: {json.dumps(r.ev, sort_keys=True, default=str)}", flush=True)
    results[rid] = not r.fails
    print(f"PASS {rid}" if not r.fails else f"FAIL {rid}: {len(r.fails)} cell(s): " + " | ".join(r.fails), flush=True)

def boot_a():
    return shared_fixture.bring_up(BOOT_A[0], BOOT_A[1], mods=(MOD,))

def boot_b():
    tag, (hp, cp, lp) = BOOT_B
    host = GameClient("host", hp, make_user_dir(f"{tag}_host", mods=(MOD,)))
    client = GameClient("client", cp, make_user_dir(f"{tag}_client", mods=(MOD,)))
    try:
        for f in (host.spawn, client.spawn, host.connect, client.connect):
            f()
        session.new_campaign(host, client, port=str(lp), campaign_mode="coop")
        geo.wait_both_ready(host, client)
    except BaseException:
        shutdown_clients(host, client)
        raise
    return SimpleNamespace(host=host, client=client, shutdown=lambda: shutdown_clients(host, client))

def boot(tag, up, rows, results, walls):
    t0 = time.time()
    try:
        js = up()
    except Exception as e:
        print(f"CAPTURE {tag} (boot miss): {short(e, 1500)}", flush=True)
        for rid, _fn in rows:
            results[rid] = False
            print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot", flush=True)
        return
    walls[tag + " bring-up"] = round(time.time() - t0, 1)
    x = SimpleNamespace(host=js.host, client=js.client)
    try:
        for rid, fn in rows:
            t = time.time()
            run_row(rid, fn, x, results)
            walls[rid] = round(time.time() - t, 1)
    finally:
        try:
            js.shutdown()
        except Exception as e:
            print(f"[w2h17c] {tag} shutdown: {short(e)}", flush=True)

ROWS_A = (("H17c-1", row_1), ("H17c-2", row_2))
ROWS_B = (("H17c-3", row_3),)

def main():
    t0, results, walls = time.time(), {}, {}
    boot(BOOT_A[0], boot_a, ROWS_A, results, walls)
    boot(BOOT_B[0], boot_b, ROWS_B, results, walls)
    rows = [rid for rid, _ in ROWS_A + ROWS_B]
    failed = [rid for rid in rows if not results.get(rid)]
    print(f"\ntest_w2_research_grants: {len(rows) - len(failed)}/{len(rows)} passed (fail={failed}) walls {walls} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
