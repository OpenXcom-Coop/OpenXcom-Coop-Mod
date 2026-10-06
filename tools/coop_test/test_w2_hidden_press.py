"""W2-U7d - test_w2_hidden_press.py: the harness vs a hidden host BEGIN / RESUME (F8018, F6474, F6824; docs rewrite/prompts/
w2u7c_hidden_press_and_geoscape_wait.md PART B (f) + AMENDMENT U7d-1). The host's wait dialogs 60 (BEGIN) and 62 (RESUME)
show their button only once the game is ready for it (CoopState.cpp :1199-1216); `coop_dialog_back` presses a hidden one
anyway and `previous()` begins / resumes the campaign with nobody ready. Boots: C the test_lobby_dialogs campaign lobby
(labels 49405/49406, lobby 47228): B-1 (a hidden BEGIN before the client placed its base). D SEPARATE new_campaign
(49407/49408, rejoiner 49410, lobby 47230): B-3 (the bring-up's BEGIN waits for the button: EVIDENCE only while session.py
has no press_back_when_shown, a verdict once it has), then B-2 (a hidden RESUME after the client was killed). RED (commit
1): B-1 and B-2 FAIL on their press cell, B-3 and every GUARD cell pass; GREEN (commit 2b): all pass. B-1 / B-2 reach
session.press_back_when_shown only after their hidden press was refused ("hidden"). Each row prints "EVIDENCE <id>:" then
"PASS <id>" or "FAIL <id>: ..."; a guard miss (FIXTURE-STOP) adds one "CAPTURE <id>:" line. WV-D95/D99/D100: ONE
foreground run, no skip path, no retried press, every row runs after a failure; exit 0 only when every row passes, 2
otherwise. Run: python tools/coop_test/<this>
"""

import json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, shutdown_clients, LAND_LON, LAND_LAT
import geo, session
import test_lobby_dialogs as tld

HOLD_S = 2.0                       # (f) 2 s of 0.1 s polls after each hidden press
GEO = ["GeoscapeState"]
DIAG = "[coop-test] coop_dialog_back:"
PRESS = "coop_dialog_back: code "  # a PRESS line; a refusal (2b) reads "coop_dialog_back: refused hidden code N"
class GuardMiss(Exception): pass  # a guard cell failed: FIXTURE-STOP

def short(x, n=300):
    s = x if isinstance(x, str) else json.dumps(x, default=str, sort_keys=True)
    return s if len(s) <= n else s[:n] + "..."
def safe(f):
    try: return f()
    except Exception as e: return "unreachable: %s" % short(str(e))
def stk(gc): return [s.split("::")[-1] for s in gc.cmd({"cmd": "get_state"}).get("states", [])]
def dlg(gc): return {k: v for k, v in gc.cmd({"cmd": "coop_dialog_info"}).items()
                     if k in ("present", "code", "title", "backVisible", "backText")}
def snap(gc): return {"stack": stk(gc), "dlg": dlg(gc)}
def bases(gc): return [b.get("name") for b in gc.cmd({"cmd": "geo_state"}).get("bases") or []]
def on_wait(s, code): return s["stack"][-1:] == ["CoopState"] and s["dlg"].get("code") == code  # C5: TOP CoopState
def refused(rep, code):
    return rep.get("ok") is False and rep.get("wait") is True and rep.get("refused") == "hidden" and rep.get("code") == code
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
class Row:
    def __init__(self, rid, host, client):
        self.rid, self.host, self.client, self.cells, self.ev, self.err, self.cap = rid, host, client, [], {}, None, None
    def cell(self, name, ok, detail, msg=None, guard=False):
        self.cells.append({"cell": name, "guard": guard, "pass": bool(ok)})
        if not ok:
            self.cells[-1]["msg"] = (msg + " | " if msg else "") + short(detail, 900)
            if guard: raise GuardMiss(name)
    def guard(self, name, ok, detail): self.cell(name, ok, detail, guard=True)
    def both(self, key):
        self.ev[key] = {"host": snap(self.host), "client": snap(self.client)}
        return self.ev[key]
def watch(secs, probe):  # probe() every 0.1 s for secs; keep the change points and the last poll (t >= secs)
    polls, t0 = [], time.time()
    while True:
        p = dict(probe(), t=round(time.time() - t0, 2))
        last = p["t"] >= secs
        if last or not polls or {k: v for k, v in p.items() if k != "t"} != {k: v for k, v in polls[-1].items() if k != "t"}:
            polls.append(p)
        if last:
            return polls
        time.sleep(0.1)
def host_probe(host, client=None):
    d = dlg(host)
    p = {"hostTop": (stk(host) or [""])[-1], "code": d.get("code"), "bv": d.get("backVisible")}
    if client is not None:
        p["clientTop"] = (stk(client) or [""])[-1]
    return p
def capture(r):
    keys = ("coopSession", "coopDialog", "lobbyMode", "onConnect", "shared", "resumeAck", "serverOwner")
    out = {gc.name: safe(lambda gc=gc: dict(snap(gc), coop={k: v for k, v in gc.cmd({"cmd": "get_coop"}).items()
                                                            if k in keys})) for gc in (r.host, r.client)}
    out["hostDiag"] = log_read(r.host, None, DIAG)
    return out

def b_1(r, ctx):
    host, cl = r.host, r.client
    host.wait_for("start eligible", lambda: host.cmd({"cmd": "lobby_state"}).get("startEligible") or None)
    session.start_campaign_via_button(host)
    host.wait_for("host base placement", lambda: session.has_state(host, "BuildNewBaseState"))
    if not host.cmd({"cmd": "place_first_base", "lon": tld.HOST_LON, "lat": tld.HOST_LAT, "name": "HostBase"}).get("ok"):
        host.ok({"cmd": "place_first_base", "lon": LAND_LON, "lat": LAND_LAT, "name": "HostBase"})
    v, secs = until(lambda: on_wait(snap(host), 60), 60, 0.25)
    b = r.both("before")
    r.guard("host 60 on top, button hidden", v and on_wait(b["host"], 60) and b["host"]["dlg"].get("backVisible") is False,
            dict(b["host"], s=secs))
    r.guard("client still on BuildNewBaseState", b["client"]["stack"][-1:] == ["BuildNewBaseState"], b["client"])
    cur = geo._log_cursor(host)
    rep = r.ev["reply"] = host.cmd({"cmd": "coop_dialog_back"})
    polls = r.ev["polls"] = watch(HOLD_S, lambda: host_probe(host, cl))
    r.both("after")
    r.ev["diag"], _ = until(lambda: log_read(host, cur, DIAG), 2.0)
    left = next((p for p in polls if not (p["hostTop"] == "CoopState" and p["code"] == 60)), None)
    res = done = None
    if refused(rep, 60) and left is None and polls[-1]["t"] >= HOLD_S:
        cl.ok({"cmd": "place_first_base", "lon": LAND_LON, "lat": LAND_LAT, "name": "ClientBase"})
        res = r.ev["begin"] = session.press_back_when_shown(host, "host BEGIN", codes=(60,))
        done, secs = until(lambda: stk(host)[-1:] == GEO and stk(cl)[-1:] == GEO, 30.0, 0.25)
        nm = {"host": bases(host), "client": bases(cl)}
        r.ev["release"] = {"bothGeo": done, "s": secs, "host": stk(host), "client": stk(cl), "bases": nm}
        r.guard("base names present", all(n in nm[k] for k in nm for n in ("HostBase", "ClientBase")), nm)
    ok = (refused(rep, 60) and left is None and res is not None and res.get("ok") is True and res.get("code") == 60
          and res.get("backVisible") is True and done)
    red = rep.get("ok") is True and left is not None
    r.cell("press on the hidden BEGIN", ok, {"reply": rep, "left": left, "begin": res},
           "coop_dialog_back pressed the host's hidden BEGIN (F8018)" if red else "unexpected outcome")

def b_3(r, ctx):
    helper = hasattr(session, "press_back_when_shown")
    lines, _ = until(lambda: log_read(r.host, None, DIAG), 2.0)
    presses = [x for x in lines or [] if PRESS in x]
    refusals = [x for x in lines or [] if "refused hidden" in x]
    r.ev.update(helper="yes" if helper else "no", bringUpPress=presses, refusedHidden=refusals)
    s0 = r.both("S0")
    r.guard("session up", s0["client"]["stack"][-1:] == GEO, s0)
    nm = r.ev["bases"] = {"host": bases(r.host), "client": bases(r.client)}
    r.guard("base names present", all(n in nm[k] for k in nm for n in ("HostBase", "ClientBase")), nm)
    if helper:  # 2a / 2b: the bring-up pressed through press_back_when_shown; commit 1: EVIDENCE only (F8019 census)
        r.cell("the bring-up's BEGIN waited for the button",
               len(presses) == 1 and "code 60 backVisible 1" in presses[0] and not refusals,
               {"presses": presses, "refused": refusals}, "the bring-up pressed a BEGIN no player could see (F6474)")

def b_2(r, ctx):
    host = r.host
    r.client.kill()
    v, secs = until(lambda: on_wait(snap(host), 62), 60, 0.25)
    h = r.ev["host62"] = dict(snap(host), s=secs)
    r.guard("host 62 on top, button hidden", v and on_wait(h, 62) and h["dlg"].get("backVisible") is False, h)
    cur = geo._log_cursor(host)
    rep = r.ev["reply"] = host.cmd({"cmd": "coop_dialog_back"})
    polls = r.ev["polls"] = watch(HOLD_S, lambda: host_probe(host))
    r.ev["after"] = snap(host)
    r.ev["diag"], _ = until(lambda: log_read(host, cur, DIAG), 2.0)
    left = next((p for p in polls if not (p["hostTop"] == "CoopState" and p["code"] == 62)), None)
    resumed = next((p for p in polls if p["hostTop"] == GEO[0]), None)
    res = back = None
    if refused(rep, 62) and left is None and polls[-1]["t"] >= HOLD_S:
        rj = r.client = ctx["rejoiner"] = GameClient("client", 49410, make_user_dir("w2u7dd_client2"))
        rj.spawn(); rj.connect()
        j = rj.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": "47230", "player": "ClientPlayer"})
        r.guard("join_tcp", j.get("ok"), j)
        v, secs = until(lambda: dlg(rj).get("code") == 68, 120, 0.25)
        r.ev["hold68"] = dict(dlg(rj), s=secs)
        r.guard("the rejoiner reaches 68", v, r.ev["hold68"])
        closed = []
        def top62():  # T0-B2: the host's join Profile is pushed before the rejoiner's 68
            if stk(host)[-1:] == ["Profile"]:
                closed.append(host.cmd({"cmd": "profile_ok"}))
                return None
            return on_wait(snap(host), 62) or None
        v, secs = until(top62, 30.0)
        r.ev["profile"] = {"closed": closed, "s": secs, "host": snap(host)}
        r.guard("host Profile closed, 62 on top", v, r.ev["profile"])
        res = r.ev["resume"] = session.press_back_when_shown(host, "host RESUME", codes=(62,))
        back, secs = until(lambda: stk(rj)[-1:] == GEO, 10.0, 0.25)
        r.ev["release"] = {"rejoinerTop": back, "s": secs, "host": stk(host)}
    ok = (refused(rep, 62) and left is None and res is not None and res.get("ok") is True and res.get("code") == 62
          and res.get("backVisible") is True and back and r.ev["release"]["host"][-1:] == GEO)
    red = rep.get("ok") is True and resumed is not None
    r.cell("press on the hidden RESUME", ok, {"reply": rep, "left": left, "resumed": resumed, "resume": res},
           "coop_dialog_back pressed the host's hidden RESUME (F8018)" if red else "unexpected outcome")
ROWS = {"B-1": b_1, "B-2": b_2, "B-3": b_3}

def exec_row(rid, host, client, ctx):
    r, t0 = Row(rid, host, client), time.time()
    try:
        ROWS[rid](r, ctx)
    except GuardMiss as e: r.err = "GUARD %s" % e
    except Exception as e: r.err = "%s: %s" % (type(e).__name__, short(str(e), 800))
    r.ev["wall"] = round(time.time() - t0, 1)
    r.cap = safe(lambda: capture(r)) if r.err else None
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
def start_pair(tag, labels, bring):
    host = GameClient("host", labels[0], make_user_dir(tag + "_host"))
    client = GameClient("client", labels[1], make_user_dir(tag + "_client"))
    try:
        host.spawn(); client.spawn(); host.connect(); client.connect()
        bring(host, client)
    except BaseException as e:
        cap = {gc.name: safe(lambda gc=gc: snap(gc)) for gc in (host, client)}
        try:
            shutdown_clients(host, client)
        finally:
            raise RuntimeError("%s | %s" % (short(str(e), 600), short(cap, 900))) from e
    return host, client
BOOTS = (("C", lambda: start_pair("w2u7dc", (49405, 49406), lambda h, c: tld._campaign_lobby(h, c, "47228")), ("B-1",)),
         ("D", lambda: start_pair("w2u7dd", (49407, 49408), lambda h, c: session.new_campaign(h, c, port="47230")),
          ("B-3", "B-2")))

def run_boot(key, start, rids, results, walls, problems):
    t0, ctx, booted = time.time(), {}, None
    try:
        booted = start()
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
            shutdown_clients(booted[0], booted[1], ctx.get("rejoiner"))
        except Exception as e:
            problems.append("shutdown %s: %s" % (key, short(str(e), 600)))
            print("SHUTDOWN %s" % problems[-1], flush=True)

def main():
    t0, results, walls, problems = time.time(), {}, {}, []
    for key, start, rids in BOOTS:
        run_boot(key, start, rids, results, walls, problems)
    order = [rid for b in BOOTS for rid in b[2]]
    passed, failed = [x for x in order if results.get(x)], [x for x in order if not results.get(x)]
    print("\ntest_w2_hidden_press: %d/%d passed (pass=%s fail=%s) in %.1fs (boot walls %s)%s"
          % (len(passed), len(order), passed, failed, time.time() - t0, walls,
             (" problems %s" % problems) if problems else ""), flush=True)
    return 0 if not failed and not problems else 2

if __name__ == "__main__":
    sys.exit(main())
