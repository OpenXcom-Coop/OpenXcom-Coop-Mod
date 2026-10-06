"""W2-U7c - test_w2_geoscape_wait.py: the harness's back-on-geoscape wait after `leave_base` vs a slow own-world reload
(F6361, R-W2i-1; docs rewrite/prompts/w2u7c_hidden_press_and_geoscape_wait.md (f)). BasescapeState::btnGeoscapeClick clears
insideCoopBase BEFORE it pushes the LoadGameState that reloads the leaving machine's own world ~10 frames later (F8006), so a
wait on the flag alone can return while the visited copy is still live. A quiet reload (~22 ms) ends before the wait's first
read (~100 ms, F8009), so the TEST-ONLY `slow_top {type LoadGameState, ms 30}` stretches it: the stand-in for W2i's loaded
machine (QA3). The wait under test (`back_wait`) is session.wait_back_on_geoscape when the module has it (EVIDENCE
`wait: helper`), else the pre-fix wait of session.bring_up_separate_guest_battle (`wait: inline`). Boots: A =
session.bring_up_separate_guest_battle (labels 49401/49402, lobby 47224) with slow_top armed on the client and a first-read
probe that stops the bring-up before the battle (U7c-1); B = session.new_campaign SEPARATE (labels 49403/49404, lobby 47226):
U7c-4 (guard: a quiet leave), U7c-2 (both leave directions under slow_top), U7c-3 (the bounded failure). RED (commit 1):
U7c-1/2/3 FAIL on their named cells, U7c-4 and every GUARD cell pass; GREEN (commit 2): all pass. Each row prints
"EVIDENCE <id>:" then "PASS <id>" or "FAIL <id>: ..."; a guard miss (FIXTURE-STOP) adds one "CAPTURE <id>:" line.
WV-D95/D99/D100: ONE foreground run, no skip path, every row runs after a failure; exit 0 only when every row passes, 2
otherwise. Run: python tools/coop_test/<this>
"""

import datetime, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, shutdown_clients
import geo, session

GEO = ["GeoscapeState"]
LGS = "LoadGameState"
SLOW_MS = 30                   # (f): 30 ms per LoadGameState frame, ~11 frames >= 330 ms (QA3)
SETTLE_S = 10.0                # (f) settle: the leaving machine's stack is ["GeoscapeState"] within 10 s
WAIT_KIND = "helper" if hasattr(session, "wait_back_on_geoscape") else "inline"
class GuardMiss(Exception): pass  # a guard cell failed: FIXTURE-STOP
class Probed(Exception): pass     # U7c-1's probe stops the bring-up before the battle

def short(x, n=300):
    s = x if isinstance(x, str) else json.dumps(x, default=str, sort_keys=True)
    return s if len(s) <= n else s[:n] + "..."
def safe(f):
    try: return f()
    except Exception as e: return "unreachable: %s" % short(str(e))
def stk(gc): return session.states_stripped(gc)
def inside(gc): return gc.cmd({"cmd": "get_coop"}).get("insideCoopBase")
def slow(gc, **kw): return gc.cmd(dict({"cmd": "slow_top"}, **kw))
def in_flight(first): return any(LGS in s for s in first) or first[-1:] != GEO
def until(pred, timeout, interval=0.1):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v, round(time.time() - t0, 2)
        time.sleep(interval)
def log_read(gc, cursor=None, needle=None, tail=25):  # post-cursor lines holding `needle`, else the last `tail` lines
    try:
        with open(geo._log_path(gc), "r", encoding="utf-8", errors="replace", newline="") as f:
            if cursor is not None:
                f.seek(cursor)
            lines = [ln.rstrip() for ln in f.read().splitlines()]
    except OSError as e:
        return [] if needle else ["log unreadable: %s" % e]
    return [ln for ln in lines if needle in ln] if needle else lines[-tail:]
def log_ts(ln):  # "[06-10-2026_13-11-20.266]\t..." -> epoch seconds, local clock (the harness's clock)
    try: return datetime.datetime.strptime(ln[1:ln.index("]")], "%d-%m-%Y_%H-%M-%S.%f").timestamp()
    except ValueError: return None
def lgs_pair(gc, cursor):  # the last LoadGameState push / pop pair after `cursor` in gc's [coop-ui] record
    def pair():
        push = pop = None
        for ln in log_read(gc, cursor, "[coop-ui] "):
            if "push class OpenXcom::" + LGS in ln: push, pop = ln, None
            elif "pop  class OpenXcom::" + LGS in ln and push: pop = ln
        return (push, pop) if push and pop else None
    pp, _ = until(pair, 3.0)
    if not pp:
        return {"push": None, "pop": None, "lines": log_read(gc, cursor, LGS)[-4:]}
    a, b = log_ts(pp[0]), log_ts(pp[1])
    return {"push": pp[0].split("]", 1)[0] + "]", "pop": pp[1].split("]", 1)[0] + "]",
            "lifetimeMs": round((b - a) * 1000) if a and b else None, "pushT": a}

def back_wait(gc, what, timeout=60):
    """The wait under test: the shared helper once session.py has it (commit 2), else the pre-fix wait copied VERBATIM from
    session.py's bring_up_separate_guest_battle (:2460-2462) with the machine substituted (commit 1)."""
    if WAIT_KIND == "helper":
        return session.wait_back_on_geoscape(gc, what, timeout=timeout)
    gc.wait_for(what,
                lambda: (not gc.cmd({"cmd": "get_coop"}).get("insideCoopBase")) or None,
                timeout=timeout)

class Row:
    def __init__(self, rid, host, client):
        self.rid, self.host, self.client, self.cells, self.ev, self.err, self.cap = rid, host, client, [], {"wait": WAIT_KIND}, None, None
    def cell(self, name, ok, detail, msg=None, guard=False):
        self.cells.append({"cell": name, "guard": guard, "pass": bool(ok)})
        if not ok:
            self.cells[-1]["msg"] = (msg + " | " if msg else "") + short(detail, 900)
            if guard: raise GuardMiss(name)
    def guard(self, name, ok, detail): self.cell(name, ok, detail, guard=True)
def arm(r, gc, ev, timeout_ms):
    a = ev["arm"] = slow(gc, type=LGS, ms=SLOW_MS, timeoutMs=timeout_ms)
    r.guard("%s slow_top armed" % gc.name, a.get("ok") and (a.get("slow") or {}).get("armed") is True, a)
def disarm(r, gc, ev):  # {} only reports the record (guard slowedPasses >= 10), then {off: true}
    rec = slow(gc).get("slow") or {}
    off = slow(gc, off=True)
    ev["slowTop"] = rec
    r.guard("%s slowedPasses >= 10" % gc.name, (rec.get("slowedPasses") or 0) >= 10 and off.get("ok")
            and (off.get("slow") or {}).get("armed") is False, {"record": rec, "off": off})
def settle(r, gc, ev):
    ok, secs = until(lambda: stk(gc) == GEO, SETTLE_S)
    ev["settle"] = {"stack": stk(gc), "s": secs}
    r.guard("%s settles to [GeoscapeState]" % gc.name, ok, ev["settle"])
def visit(r, gc, peer, ev):
    v = gc.cmd({"cmd": "visit_coop_base", "base": peer})
    ok, secs = until(lambda: inside(gc) is True, 60)
    ev["inside"] = {"visit": v, "s": secs, "stack": stk(gc)}
    r.guard("%s insideCoopBase true after the visit" % gc.name, v.get("ok") and ok, ev["inside"])
def leg(r, gc, peer, slowed):  # (f) Leg(gc, peer_base, slow); returns the first read
    ev = r.ev[gc.name] = {"peerBase": peer, "slow": slowed}
    visit(r, gc, peer, ev)
    if slowed:
        arm(r, gc, ev, 20000)
    cur = geo._log_cursor(gc)
    t0 = time.time()
    lv = gc.cmd({"cmd": "leave_base"})
    r.guard("%s leave_base ok" % gc.name, lv.get("ok"), lv)
    back_wait(gc, "%s back on geoscape" % gc.name)
    ev["waitS"] = round(time.time() - t0, 3)
    first = ev["firstRead"] = stk(gc)
    t1 = time.time()
    ev["firstReadMsAfterLeave"] = round((t1 - t0) * 1000)
    settle(r, gc, ev)
    if slowed:
        disarm(r, gc, ev)
    p = ev["lgs"] = lgs_pair(gc, cur)
    if p.get("pushT"):
        ev["firstReadMsAfterLgsPush"] = round((t1 - p.pop("pushT")) * 1000)
    return first
def names(r, ctx):
    r.ev["bases"] = {"host": ctx.get("hb"), "client": ctx.get("cb"), "errors": [ctx.get("hbError"), ctx.get("cbError")]}
    r.guard("base names present", ctx.get("hb") and ctx.get("cb"), r.ev["bases"])

def u7c_1(r, ctx):
    a = r.ev["arm"] = ctx.get("arm") or {}
    r.guard("client slow_top armed before the bring-up", a.get("ok") and (a.get("slow") or {}).get("armed") is True, a)
    p = r.ev["probe"] = ctx.get("probe")
    r.guard("probe reached (guest seated, client left the host base)", p is not None, {"probe": p})
    first, sent = p["firstRead"], (p.get("guestContrib") or {}).get("sent")
    r.cell("first read [GeoscapeState], insideCoopBase false, guestContrib.sent 1",
           first == GEO and p.get("insideCoopBase") is False and sent == 1, p,
           "session.py's 'client back on geoscape' wait returned while the client's world reload was still in flight (F6361)"
           if in_flight(first) else "unexpected outcome")
    settle(r, r.client, r.ev)
    disarm(r, r.client, r.ev)
    lp = r.ev["lgs"] = lgs_pair(r.client, ctx["cursor"])
    if lp.get("pushT"):
        p["readMsAfterLgsPush"] = round((p.pop("readAt") - lp.pop("pushT")) * 1000)
def u7c_4(r, ctx):
    names(r, ctx)
    first = leg(r, r.client, ctx["hb"], False)
    r.guard("client first read [GeoscapeState] after a quiet leave (F8009)", first == GEO, r.ev["client"])
def u7c_2(r, ctx):
    names(r, ctx)
    for gc, peer in ((r.client, ctx["hb"]), (r.host, ctx["cb"])):
        first = leg(r, gc, peer, True)
        e = r.ev[gc.name]
        r.cell("%s leg: first read [GeoscapeState], back_wait <= 10 s" % gc.name, first == GEO and e["waitS"] <= 10.0,
               {k: e.get(k) for k in ("firstRead", "waitS", "firstReadMsAfterLeave", "firstReadMsAfterLgsPush", "lgs")},
               "the insideCoopBase-only wait returned during the %s's world reload (F6361)" % gc.name
               if in_flight(first) else "unexpected outcome")
def u7c_3(r, ctx):
    names(r, ctx)
    c, ev = r.client, r.ev
    visit(r, c, ctx["hb"], ev)
    t0, err = time.time(), None
    try:
        back_wait(c, "U7c-3 bounded", timeout=3)
    except TimeoutError as e:
        err = str(e)
    to = ev["timeout"] = {"raised": err is not None, "s": round(time.time() - t0, 2), "text": err}
    r.cell("a bounded timeout raises with the probe dump", err is not None and to["s"] <= 5.0 and "stack=" in err
           and "BasescapeState" in err and "insideCoopBase=True" in err, to,
           "the back-on-geoscape wait times out without the probe dump (R-W2i-1)")
    lv = c.cmd({"cmd": "leave_base"})
    r.guard("cleanup leave_base ok", lv.get("ok"), lv)
    back_wait(c, "U7c-3 cleanup back on geoscape")
    settle(r, c, ev)
ROWS = {"U7c-1": u7c_1, "U7c-2": u7c_2, "U7c-3": u7c_3, "U7c-4": u7c_4}

def capture(r):
    keys = ("insideCoopBase", "coopSession", "coopDialog", "onConnect")
    out = {gc.name: safe(lambda gc=gc: {"stack": stk(gc), "coop": {k: v for k, v in gc.cmd({"cmd": "get_coop"}).items()
                                                                   if k in keys},
                                        "slowTop": slow(gc).get("slow"), "lgsLines": log_read(gc, None, LGS)[-6:]})
           for gc in (r.host, r.client)}
    return out
def exec_row(rid, host, client, ctx):
    r, t0 = Row(rid, host, client), time.time()
    try:
        ROWS[rid](r, ctx)
    except GuardMiss as e: r.err = "GUARD %s" % e
    except Exception as e: r.err = "%s: %s" % (type(e).__name__, short(str(e), 800))
    r.ev["wall"] = round(time.time() - t0, 1)
    if r.err:
        r.cap = safe(lambda: capture(r))
        for gc in (host, client):  # a stale arm slows every later reload on that machine
            safe(lambda gc=gc: slow(gc, off=True))
    return r
def report(r, results):
    r.ev["cells"] = [[c["cell"], "guard" if c["guard"] else "row", c["pass"]] for c in r.cells]
    print("EVIDENCE %s: %s" % (r.rid, json.dumps(r.ev, default=str)), flush=True)
    if r.err:
        print("CAPTURE %s: %s" % (r.rid, json.dumps(r.cap, default=str)), flush=True)
    fails = ["%s%s: %s" % ("GUARD " if c["guard"] else "", c["cell"], c["msg"]) for c in r.cells if not c["pass"]]
    fails += [r.err] if r.err and not r.err.startswith("GUARD") else []
    results[r.rid] = not fails
    print("PASS %s" % r.rid if not fails else "FAIL %s: %s" % (r.rid, " || ".join(fails)), flush=True)

def start_pair(tag, labels, bring, ctx):
    host = GameClient("host", labels[0], make_user_dir(tag + "_host"))
    client = GameClient("client", labels[1], make_user_dir(tag + "_client"))
    try:
        host.spawn(); client.spawn(); host.connect(); client.connect()
        bring(host, client, ctx)
    except BaseException as e:
        cap = {gc.name: safe(lambda gc=gc: {"stack": stk(gc), "insideCoopBase": inside(gc)}) for gc in (host, client)}
        try:
            shutdown_clients(host, client)
        finally:
            raise RuntimeError("%s | %s" % (short(str(e), 600), short(cap, 900))) from e
    return host, client
def probe(host, client, ctx):  # U7c-1: the FIRST command after session's back-on-geoscape wait is this get_state
    first = stk(client)
    t = time.time()
    ins = inside(client)
    gcon = client.cmd({"cmd": "event_state"}).get("guestContrib") or {}
    ctx["probe"] = {"firstRead": first, "insideCoopBase": ins, "guestContrib": gcon, "readAt": t,
                    "wallS": round(t - ctx["t0"], 1)}
    raise Probed()
def bring_a(host, client, ctx):
    ctx["cursor"] = geo._log_cursor(client)
    ctx["arm"] = slow(client, type=LGS, ms=SLOW_MS, timeoutMs=120000)
    ctx["t0"] = time.time()
    try:
        session.bring_up_separate_guest_battle(host, client, port="47224",
                                               pre_mission_start=lambda h, c: probe(h, c, ctx))
    except Probed:
        pass
def bring_b(host, client, ctx):
    session.new_campaign(host, client, port="47226")
    for key, gc in (("hb", host), ("cb", client)):  # the guard "base names present" judges a None
        try: ctx[key] = session._campaign_base0(gc)["name"]
        except Exception as e: ctx[key], ctx[key + "Error"] = None, short(str(e))
BOOTS = (("A", lambda ctx: start_pair("w2u7c_a", (49401, 49402), bring_a, ctx), ("U7c-1",)),
         ("B", lambda ctx: start_pair("w2u7c_b", (49403, 49404), bring_b, ctx), ("U7c-4", "U7c-2", "U7c-3")))

def run_boot(key, start, rids, results, walls, problems):
    t0, ctx, booted = time.time(), {}, None
    try:
        booted = start(ctx)
    except Exception as e:
        print("CAPTURE boot %s: %s" % (key, short(str(e), 1500)), flush=True)
    walls[key] = round(time.time() - t0, 1)
    if booted is None:
        for rid in rids:
            results[rid] = False; print("FAIL %s: boot" % rid, flush=True)
        return
    try:
        for rid in rids:
            report(exec_row(rid, booted[0], booted[1], ctx), results)
    finally:
        try:
            shutdown_clients(booted[0], booted[1])
        except Exception as e:
            problems.append("shutdown %s: %s" % (key, short(str(e), 600)))
            print("SHUTDOWN %s" % problems[-1], flush=True)

def main():
    t0, results, walls, problems = time.time(), {}, {}, []
    for key, start, rids in BOOTS:
        run_boot(key, start, rids, results, walls, problems)
    order = [rid for b in BOOTS for rid in b[2]]
    passed, failed = [x for x in order if results.get(x)], [x for x in order if not results.get(x)]
    print("\ntest_w2_geoscape_wait: %d/%d passed (pass=%s fail=%s) wait=%s in %.1fs (boot walls %s)%s"
          % (len(passed), len(order), passed, failed, WAIT_KIND, time.time() - t0, walls,
             (" problems %s" % problems) if problems else ""), flush=True)
    return 0 if not failed and not problems else 2

if __name__ == "__main__":
    sys.exit(main())
