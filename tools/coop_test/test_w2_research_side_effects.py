"""W2-H17 - test_w2_research_side_effects.py (SHARED): a finished research project leaves the same world on both machines
(corpse, diary, obsolete project + refund, delivered items, counters; F3262, D226 a). Spec rewrite/prompts/
w2h17_research_side_effects.md (e)-(f) + RULINGS C1-C3, F5728; docs rewrite/w2h17-task0/CONSTANTS.md. Trigger 1 interrogates
STR_SECTOID_SOLDIER; trigger 2 completes STR_H17_A while STR_H17_B runs. Per trigger: S0, skip (2 days, speed 5, interest
ResearchCompleteState), hit window (both windows open, both read every ~0.5 s for 3 s, C3), clean (settle + 60 min + 4 s).
C2: no client dismissal while its resync is pending (10 s; timeout = FAIL + dump). RED (commit 1): H17-1..5 fail on their
named cells, H17-6 passes (guard row); "G:" cells are guards (CAPTURE on a miss). GREEN: all pass. Exit 0 only if all pass.
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

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_ResearchFx_Test")
BOOT = ("w2h17a", (49294, 49295, 47284), {"retainCorpses": True})   # labels + lobby key (F5764)
HQ, RC, GEO = "HostBase", "ResearchCompleteState", "GeoscapeState"
LIVE, CORPSE, LOOKUP = "STR_SECTOID_SOLDIER", "STR_SECTOID_CORPSE", "STR_SECTOID"
A, B, PISTOL, COUNTER = "STR_H17_A", "STR_H17_B", "STR_PISTOL", "STR_H17_COUNTER"
NAMES, ITEMS = [LIVE, LOOKUP, A, B], [LIVE, CORPSE, B, PISTOL]
WINDOW_S, CADENCE_S = 3.0, 0.5      # C3 (F5827): ~0.5 s per both-machine sample
CLEAN_S = 4.0                       # > the 3000 ms mismatch debounce (P10 F5510) and H15 F5709's 3.27 s worst case
PENDING_S, BETWEEN_S = 10.0, 30.0   # C2 (F5820) bound; between triggers

class GuardMiss(Exception):
    """A guard failed: the trigger ends after its CAPTURE line."""
class PendingTimeout(Exception):
    """C2: the client's resync stayed pending past PENDING_S."""

def short(e, n=500):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."
def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while not pred() and time.time() - t0 < timeout:
        time.sleep(interval)
    return bool(pred())
def rs(gc):
    r = gc.cmd({"cmd": "shared_resync_stats"})
    return {k: r.get(k) for k in ("requests", "pending", "mismatches", "gaveUp")}
def chk(gc):
    return {k: v for k, v in gc.cmd({"cmd": "shared_checksum"}).items() if k.startswith("chk")}
def probe(gc):
    return gc.cmd({"cmd": "research_probe", "names": NAMES, "tail": 12})
stack = session.states_stripped
def view(gc):
    """The hq's stores, research list, free scientists and transfers (None while a restream replaces the world)."""
    g = gc.cmd({"cmd": "geo_state"})
    b = next((b for b in g.get("bases", []) if b.get("name") == HQ), None) if g.get("ok") else None
    return None if b is None else {"items": {k: b["items"].get(k, 0) for k in ITEMS}, "free": b["freeScientists"],
                                   "research": sorted(p["name"] for p in b["research"]), "transfers": b["transfers"]}
def listed(gc, topic, item0=False):
    v = view(gc) or {}
    return topic in v.get("research", []) and (not item0 or v["items"].get(topic) == 0)
def dump(gc):
    out = {}
    for k, f in (("geo_state", lambda: gc.cmd({"cmd": "geo_state"})), ("research_probe", lambda: probe(gc)),
                 ("shared_resync_stats", lambda: gc.cmd({"cmd": "shared_resync_stats"})), ("stack", lambda: stack(gc))):
        try:
            out[k] = f()
        except Exception as e:
            out[k] = short(e)
    return out
def wait_pending(x, send=None):
    """C2 (F5820): before any client dismissal or settle, the client's resync `pending` must be false (bounded)."""
    send, t0 = send or x.client.cmd, time.time()
    while send({"cmd": "shared_resync_stats"}).get("pending"):
        if time.time() - t0 >= PENDING_S:
            raise PendingTimeout(json.dumps({gc.name: dump(gc) for gc in (x.host, x.client)}, sort_keys=True, default=str))
        time.sleep(0.05)
    if time.time() - t0 > 0.1:
        x.waits.append(round(time.time() - t0, 2))
def guard_client(x):
    """Every dismiss_popup the client is sent (the geo.settle / skip walks included) first waits out a pending resync."""
    orig = x.client.cmd
    def cmd(obj):
        if obj.get("cmd") == "dismiss_popup":
            wait_pending(x, orig)
        return orig(obj)
    x.client.cmd = cmd
class Phase:
    def __init__(self, name):
        self.name, self.ev, self.guards, self.samples, self.s0, self.clean, self.error = name, {}, [], [], {}, None, None
    def guard(self, x, gname, ok, detail):
        self.guards.append((gname, bool(ok), detail))
        if not ok:
            cap = json.dumps({gc.name: dump(gc) for gc in (x.host, x.client)}, sort_keys=True, default=str)
            print(f"CAPTURE {self.name} (guard {gname}): {cap}", flush=True)
            raise GuardMiss(gname)

def setup1(x, ph):
    h, c = x.host, x.client
    ph.guard(x, "clientRetainCorpses", x.opt.get("client") is True, f"option_values {x.opt}")
    give = [gc.cmd({"cmd": "give_items", "item": LIVE, "count": 1}).get("ok") for gc in (c, h)]
    st = h.cmd({"cmd": "research_start", "topic": LIVE, "scientists": 10}).get("ok")      # host only
    ok = wait_until(lambda: listed(h, LIVE) and listed(c, LIVE), 5)
    ph.guard(x, "listed", all(give) and st and ok, f"give {give} start {st}; host {view(h)} / replica {view(c)}")
    ph.ev["cost"] = h.cmd({"cmd": "set_research_cost", "topic": LIVE, "cost": 1}).get("ok")  # host only, both list it
def setup2(x, ph):
    h, c = x.host, x.client
    give = [gc.cmd({"cmd": "give_items", "item": B, "count": 1}).get("ok") for gc in (c, h)]
    sb = h.cmd({"cmd": "research_start", "topic": B, "scientists": 5}).get("ok")            # host only
    ok = wait_until(lambda: listed(h, B, True) and listed(c, B, True), 10)
    ph.guard(x, "listedB", all(give) and sb and ok, f"give {give} start {sb}; host {view(h)} / replica {view(c)}")
    sa = h.cmd({"cmd": "research_start", "topic": A, "scientists": 5}).get("ok")
    ok = wait_until(lambda: listed(h, A) and listed(c, A), 10)
    ph.guard(x, "listedA", sa and ok, f"start {sa}; host {view(h)} / replica {view(c)}")
def sample(x, t0):
    s = {"t": round(time.time() - t0, 2)}
    for gc, k in ((x.host, "h"), (x.client, "c")):
        p = probe(gc)
        s[k] = dict(view(gc) or {}, diary=p.get("diary"), researched=p.get("researched"), ids=p.get("ids"), stack=stack(gc))
    s["cReq"] = rs(x.client)["requests"]
    return s
def run_phase(x, ph, setup):
    h, c, t_ph = x.host, x.client, time.time()
    try:
        ok = wait_until(lambda: not rs(c)["pending"] and stack(h)[-1:] == [GEO] and stack(c)[-1:] == [GEO], BETWEEN_S, 0.2)
        ph.guard(x, "start", ok, f"stacks {stack(h)} / {stack(c)}, replica {rs(c)}")
        setup(x, ph)
        ph.s0 = {gc.name: {"view": view(gc), "probe": probe(gc), "chk": chk(gc), "rs": rs(gc)} for gc in (h, c)}
        wait_pending(x)
        t = time.time()
        sk = geo.skip_ingame_time(h, c, 60 * 24 * 2, speed_idx=5, interest=geo.popup(RC), real_timeout=150)
        ph.ev["skip"] = {"hit": sk.get("hit"), "gameMin": sk.get("game_minutes"), "s": round(time.time() - t, 1),
                         "dismissed": sk.get("dismissed")}
        ph.guard(x, "hit", sk.get("hit") is not None and stack(h)[-1:] == [RC], f"skip {ph.ev['skip']}, host {stack(h)}")
        t0 = time.time()
        while time.time() - t0 < WINDOW_S:       # the hit window: every RED/GREEN cell is read here, before any dismiss
            ts = time.time()
            ph.samples.append(sample(x, t0))
            time.sleep(max(0.0, CADENCE_S - (time.time() - ts)))
        wait_pending(x)                         # clean (C2 before the settle; every client dismissal waits too)
        st = geo.settle(h, c)
        wait_pending(x)
        sk = geo.skip_ingame_time(h, c, 60, speed_idx=3)
        time.sleep(CLEAN_S)
        ph.clean = {"dismissed": st.get("dismissed"), "gameMin": sk.get("game_minutes"), "requests": rs(c)["requests"],
                    "chkHost": chk(h), "chkClient": chk(c), "stacks": [stack(h), stack(c)]}
    except GuardMiss:
        pass
    except PendingTimeout as e:
        ph.error = f"the client's resync stayed pending > {PENDING_S} s (C2)"
        print(f"CAPTURE {ph.name} (resync pending): {e}", flush=True)
    except Exception as e:
        ph.error = short(e, 800)
    if ph.error or not all(ok for _n, ok, _d in ph.guards):
        try:
            wait_pending(x)
            geo.settle(h, c)
        except Exception as e:
            ph.ev["settleAfterMiss"] = short(e)
    ph.ev["wallS"] = round(time.time() - t_ph, 1)

class Row:
    def __init__(self, rid):
        self.rid, self.ev, self.fails, self.passed = rid, {}, [], []
    def cell(self, name, ok, detail=""):
        (self.passed.append(name) if ok else self.fails.append(f"{name}: {detail}"))
        return ok
def phase_ok(r, p):
    """The trigger's guard cells on this row (+ its hit-window EVIDENCE); False when the window was never read."""
    for n, ok, d in p.guards:
        r.cell(f"G:{p.name}.{n}", ok, d)
    if p.error:
        r.cell(f"{p.name}.error", False, p.error)
    last, dg = (p.samples[-1] if p.samples else {}), (lambda v: (v.get("diary") or {}))  # noqa: E731
    r.ev[p.name] = {"S0": {n: {"view": v.get("view"), "diarySize": dg(v.get("probe") or {}).get("size"),
                               "requests": (v.get("rs") or {}).get("requests")} for n, v in p.s0.items()},
                    "last": {n: dict(last[k], diary=None, diaryTail=dg(last[k]).get("tail", [])[-4:], diarySize=dg(last[k])
                                     .get("size")) for n, k in (("host", "h"), ("replica", "c")) if k in last},
                    "samples": len(p.samples), "requests": sorted({s["cReq"] for s in p.samples}), "skip": p.ev.get("skip"),
                    "wallS": p.ev.get("wallS")}
    return all(ok for _n, ok, _d in p.guards) and bool(p.samples)

def every(p, pred):
    return all(pred(s) for s in p.samples)
def seen(p, k, f):
    """Distinct values of f(sample[k]) over the hit window, in first-seen order."""
    out = []
    for s in p.samples:
        if (v := f(s[k])) not in out:
            out.append(v)
    return out
def both(p, f):
    return {"host": seen(p, "h", f), "replica": seen(p, "c", f)}
def clean_cell(r, p):
    s0req, cl = p.s0["client"]["rs"]["requests"], p.clean or {}
    r.ev["clean." + p.name] = cl
    r.cell("clean", bool(cl) and cl["requests"] == s0req and bool(cl["chkHost"]) and cl["chkHost"] == cl["chkClient"],
           f"replica requests {s0req} -> {cl.get('requests')}, chk host {cl.get('chkHost')} / replica {cl.get('chkClient')}")

def row_h17_1(r, x):
    if not phase_ok(r, p := x.p1):
        return
    s0 = {k: p.s0[n]["view"]["items"][CORPSE] for k, n in (("h", "host"), ("c", "client"))}
    ev = r.ev["corpse"] = dict(both(p, lambda v: v["items"][CORPSE]), S0=s0)
    r.cell("G:hostCorpse", every(p, lambda s: s["h"]["items"][CORPSE] == s0["h"] + 1), f"{ev}")
    r.cell("replicaCorpse", every(p, lambda s: s["c"]["items"][CORPSE] == s0["c"] + 1), f"the replica skipped the corpse: {ev}")
    clean_cell(r, p)

def new_entries(s, k, n0):
    d, m = s[k]["diary"], s[k]["diary"]["size"] - n0
    return [[e["name"], e["sourceType"], e["sourceName"]] for e in d["tail"][-m:]] if m > 0 else []
def diary_cells(r, p, want):
    if not phase_ok(r, p):
        return
    n0 = {k: p.s0[n]["probe"]["diary"]["size"] for k, n in (("h", "host"), ("c", "client"))}
    ev = r.ev["diary." + p.name] = dict(both(p, lambda v: v["diary"]), S0size=n0, want=want,
                                        hostNew=new_entries(p.samples[-1], "h", n0["h"]),
                                        replicaNew=new_entries(p.samples[-1], "c", n0["c"]))
    r.cell(f"G:hostEntries.{p.name}", every(p, lambda s: all(w in new_entries(s, "h", n0["h"]) for w in want)), f"{ev['hostNew']}")
    r.cell(f"replicaEntries.{p.name}", every(p, lambda s: all(w in new_entries(s, "c", n0["c"]) for w in want)),
           f"research diary differs: replica new {ev['replicaNew']} want {want}")
    r.cell(f"diary.{p.name}", every(p, lambda s: s["c"]["diary"] == s["h"]["diary"]),
           f"research diary differs: host {ev['host']} / replica {ev['replica']}")
def row_h17_2(r, x):
    diary_cells(r, x.p1, [[LIVE, 0, HQ], [LOOKUP, 0, HQ]])       # BASE topic (F5728) + BASE lookup
    diary_cells(r, x.p2, [[A, 0, HQ], [B, 1, A]])                 # BASE topic + FREE_FROM bonus

def row_h17_3(r, x):
    if not phase_ok(r, p := x.p2):
        return
    h0 = p.s0["host"]["view"]
    ev = r.ev["obsolete"] = {k: both(p, f) for k, f in (("research", lambda v: v["research"]), (B, lambda v: v["items"][B]),
                                                         ("free", lambda v: v["free"]), ("researchedB", lambda v: v["researched"][B]))}
    r.cell("G:hostNoB", every(p, lambda s: B not in s["h"]["research"]), f"{ev['research']}")
    r.cell("G:hostBDiscovered", every(p, lambda s: s["h"]["researched"][B]), f"{ev['researchedB']}")
    r.cell("G:hostRefund", every(p, lambda s: s["h"]["items"][B] == h0["items"][B] + 1), f"S0 {h0['items'][B]} {ev[B]}")
    r.cell("G:hostFree", every(p, lambda s: s["h"]["free"] == h0["free"] + 10), f"S0 {h0['free']} {ev['free']}")
    r.cell("replicaNoB", every(p, lambda s: B not in s["c"]["research"]), f"the obsolete project stayed: {ev['research']}")
    r.cell("storesB", every(p, lambda s: s["c"]["items"][B] == s["h"]["items"][B]), f"{ev[B]}")
    r.cell("freeScientists", every(p, lambda s: s["c"]["free"] == s["h"]["free"]), f"{ev['free']}")
    clean_cell(r, p)

def row_h17_4(r, x):
    if not phase_ok(r, p := x.p2):
        return
    s0 = {k: p.s0[n]["view"]["items"][PISTOL] for k, n in (("h", "host"), ("c", "client"))}
    ev = r.ev["delivered"] = {"S0": s0, "pistols": both(p, lambda v: v["items"][PISTOL]),
                              "transfers": both(p, lambda v: v["transfers"])}
    r.cell("G:hostPistols", every(p, lambda s: s["h"]["items"][PISTOL] == s0["h"] + 2), f"{ev}")
    r.cell("G:hostTransfers", every(p, lambda s: s["h"]["transfers"] == []), f"{ev['transfers']}")   # C1 (F5825)
    r.cell("pistols", every(p, lambda s: s["c"]["items"][PISTOL] == s0["c"] + 2), f"the delivered items never arrived: {ev}")
    r.cell("replicaTransfers", every(p, lambda s: s["c"]["transfers"] == []), f"{ev['transfers']}")

def row_h17_5(r, x):
    if not phase_ok(r, p := x.p2):
        return
    h0 = p.s0["host"]["probe"]["ids"]
    ev = r.ev["counter"] = dict(both(p, lambda v: v["ids"].get(COUNTER)),
                                S0=[h0.get(COUNTER), p.s0["client"]["probe"]["ids"].get(COUNTER)])
    r.cell("G:hostCounter", COUNTER not in h0 and every(p, lambda s: s["h"]["ids"].get(COUNTER) == 2), f"{ev}")
    r.cell("counter", every(p, lambda s: s["c"]["ids"].get(COUNTER) == s["h"]["ids"].get(COUNTER)), f"counter differs: {ev}")

def row_h17_6(r, x):
    """Guard row: the research itself on both machines, and a ResearchCompleteState reached both."""
    for p, names in ((x.p1, [LIVE]), (x.p2, [A, B])):
        if not phase_ok(r, p):
            continue
        got = r.ev["researched." + p.name] = {n: both(p, lambda v, n=n: v["researched"][n]) for n in names}
        r.cell(f"researched.{p.name}", every(p, lambda s: all(s[k]["researched"][n] for k in "hc" for n in names)), f"{got}")
        dis = ((p.ev.get("skip") or {}).get("dismissed") or {}).get("client") or []
        rc = [any(RC in str(t) for s in p.samples for t in s[k]["stack"]) for k in "hc"]
        r.cell(f"rcBoth.{p.name}", rc[0] and (rc[1] or any(RC in str(t) for t in dis)), f"stacks {rc} dismissed {dis}")

def run_row(rid, fn, x, results):
    r = Row(rid)
    try:
        fn(r, x)
    except Exception as e:
        r.cell("exception", False, short(e, 800))
    r.ev["cellsPassed"] = r.passed
    print(f"EVIDENCE {rid}: {json.dumps(r.ev, sort_keys=True, default=str)}", flush=True)
    results[rid] = not r.fails
    print(f"PASS {rid}" if not r.fails else f"FAIL {rid}: {len(r.fails)} cell(s): " + " | ".join(r.fails), flush=True)

ROWS = (("H17-1", row_h17_1), ("H17-2", row_h17_2), ("H17-3", row_h17_3), ("H17-4", row_h17_4), ("H17-5", row_h17_5),
        ("H17-6", row_h17_6))

def main():
    t0, results, tag, x, js = time.time(), {}, BOOT[0], None, None
    try:
        js = shared_fixture.bring_up(tag, BOOT[1], mods=(MOD,), host_options=BOOT[2])
    except Exception as e:
        print(f"CAPTURE {tag} (boot miss): {short(e, 1500)}", flush=True)
        for rid, _fn in ROWS:
            print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot", flush=True)
    boot_s = round(time.time() - t0, 1)
    if js is not None:
        print(f"[w2h17] {tag} bring-up {boot_s}s", flush=True)
        x = SimpleNamespace(host=js.host, client=js.client, waits=[], p1=Phase("t1"), p2=Phase("t2"))
        try:
            guard_client(x)
            x.opt = {gc.name: (gc.cmd({"cmd": "option_values", "ids": ["retainCorpses"]}).get("values") or {})
                     .get("retainCorpses") for gc in (x.host, x.client)}
            run_phase(x, x.p1, setup1)
            run_phase(x, x.p2, setup2)
            for rid, fn in ROWS:
                run_row(rid, fn, x, results)
        finally:
            try:
                js.shutdown()
            except Exception as e:
                print(f"[w2h17] shutdown: {short(e)}", flush=True)
    failed = [rid for rid, _ in ROWS if not results.get(rid)]
    walls = {"boot": boot_s, "t1": x and x.p1.ev.get("wallS"), "t2": x and x.p2.ev.get("wallS"), "pendingWaits": x and x.waits}
    print(f"\ntest_w2_research_side_effects: {len(ROWS) - len(failed)}/{len(ROWS)} passed (fail={failed}) walls {walls} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
