"""W2-U7b - test_w2_dialog_back_guard.py: the harness vs a no-button client hold (F5864; docs rewrite/prompts/
w2u7b_dialog_back_guard.md (f)). Two client holds hide their button and close themselves when the host releases them:
68 (the resume hold after a world (re)stream) and 65 (the base-placement hold); `coop_dialog_back` presses the top
CoopState's back button whatever it shows (68: disconnects the client; 65: pops the hold early). Boots: A SHARED bring_up
(labels 49324/49325, lobby 47304): U7b-4 (guard: the replica's save refusal 123 shows its button, pressed as before), then
U7b-1 (the TEST-ONLY `dismiss_arm {type CoopState, fire coop_dialog_back}` fires on the one-frame 68 after a forced repair,
F6188). B SEPARATE new_campaign (49326/49327, rejoiner 49328, lobby 47306): U7b-2 (the rejoin hold 68). C the
test_lobby_dialogs campaign lobby (49329/49330, lobby 47308): U7b-3 (65). RED (commit 1): U7b-1/2/3 FAIL on their press
cell, U7b-4 and every GUARD cell pass; GREEN (commit 2): all pass. U7b-4's press-diagnostic cell (Q3) is judged once U7b-1
has classified the build: one that refuses the hold replies `code` 123 / `backVisible` true and logs the `[coop-test]
coop_dialog_back:` line; one that presses it (commit 1) has neither. Each row prints "EVIDENCE <id>:" then "PASS <id>" or
"FAIL <id>: ..."; a guard miss (FIXTURE-STOP) adds one "CAPTURE <id>:" line. WV-D95/D99/D100: ONE foreground run, no skip
path, every row runs after a failure; exit 0 only when every row passes, 2 otherwise. Run: python tools/coop_test/<this>
"""

import json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, shutdown_clients, LAND_LON, LAND_LAT
import geo, session, shared_fixture
import test_lobby_dialogs as tld

ARM_MS = 10000
GONE_S = 5.0                   # (f) "gone": within 5 s top MainMenuState / GoToMainMenuState or has_save false
GEO = ["GeoscapeState"]
MENU = (["MainMenuState"], ["GoToMainMenuState"])
DIAG = "[coop-test] coop_dialog_back:"
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
def has_save(gc): return gc.cmd({"cmd": "world_state"}).get("has_save")
def pending(gc): return gc.cmd({"cmd": "shared_resync_stats"}).get("pending")
def snap(gc): return {"stack": stk(gc), "dlg": dlg(gc), "has_save": has_save(gc)}
def name0(gc): return ((gc.cmd({"cmd": "geo_state"}).get("bases") or [{}])[0]).get("name")
def chk(gc): return {k: v for k, v in gc.cmd({"cmd": "shared_checksum"}).items() if k.startswith("chk")}
def gone(p): return p["stack"][-1:] in MENU or p["has_save"] is False
def on_hold(s, code): return s["stack"][-1:] == ["CoopState"] and s["dlg"].get("code") == code
def refused(rep, code):
    return rep.get("ok") is False and rep.get("wait") is True and rep.get("refused") == "hold" and rep.get("code") == code
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
def watch(r, gc, secs, stop):  # poll gc (+ the host's top) every 0.1 s up to secs or stop(p); keep the change points
    polls, t0, K = [], time.time(), ("stack", "has_save", "code", "pending", "hostTop")
    while True:
        p = {"t": round(time.time() - t0, 2), "stack": stk(gc), "has_save": has_save(gc), "code": dlg(gc).get("code"),
             "pending": pending(gc), "hostTop": (stk(r.host) or [""])[-1]}
        done = stop(p) or p["t"] >= secs
        if done or not polls or [p[k] for k in K] != [polls[-1][k] for k in K]:
            polls.append(p)
        if done:
            return polls
        time.sleep(0.1)
def host_offers(host, timeout):  # the rejoin_end_turn pattern: close a host Profile popup, wait its back button shown
    def offered():
        if session.has_state(host, "Profile"):
            return host.cmd({"cmd": "profile_ok"}) and None
        return dlg(host).get("backVisible") or None
    v, secs = until(offered, timeout, 0.25)
    return v, dict(dlg(host), s=secs, stack=stk(host))
def capture(r):
    keys = ("coopSession", "coopDialog", "lobbyMode", "onConnect", "shared", "resumeAck", "serverOwner")
    out = {gc.name: safe(lambda gc=gc: dict(snap(gc), coop={k: v for k, v in gc.cmd({"cmd": "get_coop"}).items()
                                                            if k in keys})) for gc in (r.host, r.client)}
    out["arm"] = safe(lambda: r.client.cmd({"cmd": "dismiss_arm_state"}).get("arm"))
    out["clientLogTail"] = log_read(r.client)
    return out

def u7b_4(r, ctx):
    st = geo.settle(r.host, r.client)
    r.ev["S0"] = {"client": stk(r.client), "host": stk(r.host), "dismissed": st.get("dismissed")}
    r.guard("S0 client [GeoscapeState]", r.ev["S0"]["client"] == GEO, r.ev["S0"])
    q = r.client.cmd({"cmd": "save_game_ui", "type": "quick"})
    v, secs = until(lambda: on_hold(snap(r.client), 123), 3.0)
    c = r.both("before")["client"]
    r.guard("123 shown on top", q.get("ok") and v and c["dlg"].get("backVisible") is True, {"save": q, "s": secs, "c": c})
    cur = geo._log_cursor(r.client)
    rep = r.ev["reply"] = r.client.cmd({"cmd": "coop_dialog_back"})
    v, secs = until(lambda: stk(r.client) == GEO, 2.0)
    r.both("after")
    r.cell("press closes 123", rep.get("ok") is True and v, {"reply": rep, "s": secs, "after": r.ev["after"]["client"]},
           "a shown back button was not pressed as before")
    lines, _ = until(lambda: log_read(r.client, cur, DIAG), 2.0)
    ctx["u7b4"] = r.ev["diag"] = {"reply": rep, "logLines": lines or []}
def u7b_4_diag(r, ctx):  # Q3, judged after U7b-1 classified the build (refuses the hold: commit 2; presses it: commit 1)
    d, build = ctx.get("u7b4"), ctx.get("build")
    if d is None:
        return  # U7b-4 stopped before its press; its guard already failed the row
    rep, lines = d["reply"], d["logLines"]
    if build == "refuses":
        ok = rep.get("code") == 123 and rep.get("backVisible") is True and any("code 123 backVisible 1" in x for x in lines)
    else:
        ok = build == "presses" and "code" not in rep and "backVisible" not in rep and not lines
    r.cell("press diagnostic matches the build (%s)" % build, ok, d,
           "the press reply / log line do not match a build that %s the hold" % build)

def u7b_1(r, ctx):
    st = geo.settle(r.host, r.client)
    s0 = r.ev["S0"] = {"client": stk(r.client), "host": stk(r.host), "pending": pending(r.client),
                       "dismissed": st.get("dismissed")}
    r.guard("S0 client [GeoscapeState], not pending", s0["client"] == GEO and s0["pending"] is False, s0)
    r.both("before")
    a = r.client.cmd({"cmd": "dismiss_arm", "type": "CoopState", "fire": "coop_dialog_back", "timeoutMs": ARM_MS})
    r.guard("armed", a.get("ok") and a.get("armed"), a)
    f = r.ev["force_resync"] = r.client.cmd({"cmd": "force_resync"})
    r.guard("sent", f.get("role") == "replica" and f.get("sent") is True, f)
    arm, _ = until(lambda: (lambda x: x if x.get("fired") or x.get("expired") else None)(
        r.client.cmd({"cmd": "dismiss_arm_state"}).get("arm") or {}), ARM_MS / 1000.0 + 1.0)
    arm = r.ev["arm"] = arm or r.client.cmd({"cmd": "dismiss_arm_state"}).get("arm")
    r.guard("fired on 68, button hidden", arm.get("fired") is True and arm.get("topBefore") == "CoopState"
            and arm.get("codeAtFire") == 68 and arm.get("backVisibleAtFire") is False, arm)
    rep = json.loads(arm.get("response") or "{}")
    ctx["build"] = "refuses" if rep.get("refused") == "hold" else "presses" if rep.get("ok") is True else None
    rel = lambda p: p["stack"] == GEO and p["has_save"] is True and p["pending"] is False and p["hostTop"] == GEO[0]
    polls = r.ev["polls"] = watch(r, r.client, GONE_S, lambda p: rel(p) or gone(p))
    r.both("after")
    hit, lost = next((p for p in polls if rel(p)), None), next((p for p in polls if gone(p)), None)
    renamed = same = None
    if refused(rep, 68) and hit is not None and hit["t"] <= 3.0:
        r.host.ok({"cmd": "base_rename", "name": "U7B"})
        renamed, secs = until(lambda: name0(r.client) == "U7B", 3.0)
        same, _ = until(lambda: (lambda a, b: bool(a) and a == b)(chk(r.host), chk(r.client)), 5.0)
        r.ev["rename"] = {"reached": renamed, "s": secs, "chkEqual": same}
    if lost is not None:  # EVIDENCE only: the host's top after the drop (expected its reconnect dialog 62)
        hd, secs = until(lambda: (lambda d: d if d.get("code") == 62 else None)(dlg(r.host)), 5.0)
        r.ev["hostAfterDrop"] = {"dlg": hd or dlg(r.host), "s": secs, "stack": stk(r.host)}
    red = rep.get("ok") is True and lost is not None
    r.cell("press on the hidden resume hold", refused(rep, 68) and hit is not None and hit["t"] <= 3.0 and renamed and same,
           {"response": rep, "released": hit, "gone": lost},
           "coop_dialog_back on the hidden resume hold disconnected the client (F5864)" if red else "unexpected outcome")

def u7b_2(r, ctx):
    host = r.host
    r.client.kill()
    v, secs = until(lambda: dlg(host).get("code") == 62, 60, 0.25)
    r.ev["host62"] = dict(dlg(host), s=secs)
    r.guard("host 62 after the kill", v, r.ev["host62"])
    rj = r.client = ctx["rejoiner"] = GameClient("client", 49328, make_user_dir("w2u7bb_client2"))
    rj.spawn(); rj.connect()
    j = rj.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": "47306", "player": "ClientPlayer"})
    r.guard("join_tcp", j.get("ok"), j)
    v, secs = until(lambda: dlg(rj).get("code") == 68, 120, 0.25)
    r.ev["hold68"] = dict(dlg(rj), s=secs)
    r.guard("rejoiner reaches 68", v and r.ev["hold68"].get("title") == tld.RESUME_HOLD_MSG, r.ev["hold68"])
    v, hd = host_offers(host, 120)
    r.guard("host offers RESUME", v and hd.get("code") == 62, hd)
    c = r.both("before")["client"]
    r.guard("68 on top, button hidden", on_hold(c, 68) and c["dlg"].get("backVisible") is False, c)
    rep = r.ev["reply"] = rj.cmd({"cmd": "coop_dialog_back"})
    polls = r.ev["polls"] = watch(r, rj, 2.0 if refused(rep, 68) else GONE_S, gone)
    lost = next((p for p in polls if gone(p)), None)
    held = lost is None and on_hold(r.both("after")["client"], 68) and polls[-1]["t"] >= 2.0
    res = back = None
    if refused(rep, 68) and held:
        res = r.ev["resume"] = host.cmd({"cmd": "coop_dialog_back"})
        back, secs = until(lambda: stk(rj)[-1:] == GEO, 10.0, 0.25)
        r.ev["release"] = {"rejoinerTop": back, "s": secs, "host": stk(host)}
    ok = (refused(rep, 68) and held and res and res.get("ok") is True and res.get("code") == 62
          and res.get("backVisible") is True and back and r.ev["release"]["host"][-1:] == GEO)
    red = rep.get("ok") is True and lost is not None
    r.cell("press on the rejoin hold", ok, {"reply": rep, "gone": lost, "resume": res},
           "coop_dialog_back on the rejoin hold disconnected the rejoining client (F5864)" if red else "unexpected outcome")

def u7b_3(r, ctx):
    host, cl = r.host, r.client
    host.wait_for("start eligible", lambda: host.cmd({"cmd": "lobby_state"}).get("startEligible") or None)
    session.start_campaign_via_button(host)
    host.wait_for("host base placement", lambda: session.has_state(host, "BuildNewBaseState"))
    if not host.cmd({"cmd": "place_first_base", "lon": tld.HOST_LON, "lat": tld.HOST_LAT, "name": "HostBase"}).get("ok"):
        host.ok({"cmd": "place_first_base", "lon": LAND_LON, "lat": LAND_LAT, "name": "HostBase"})
    v, secs = until(lambda: dlg(host).get("code") == 60, 60, 0.25)
    r.ev["host60"] = dict(dlg(host), s=secs)
    r.guard("host 60", v, r.ev["host60"])
    cl.wait_for("client base placement", lambda: session.has_state(cl, "BuildNewBaseState"))
    cl.ok({"cmd": "place_first_base", "lon": LAND_LON, "lat": LAND_LAT, "name": "ClientBase"})
    v, secs = until(lambda: dlg(cl).get("code") == 65, 60, 0.25)
    c = r.both("before")["client"]
    r.guard("65 on top, button hidden", v and on_hold(c, 65) and c["dlg"].get("backVisible") is False, dict(c, s=secs))
    rep = r.ev["reply"] = cl.cmd({"cmd": "coop_dialog_back"})
    polls = r.ev["polls"] = watch(r, cl, 2.0, lambda p: False)
    r.both("after")
    left = next((p for p in polls if not (p["stack"][-1:] == ["CoopState"] and p["code"] == 65)), None)
    v, hd = host_offers(host, 120)
    r.guard("host offers BEGIN", v and hd.get("code") == 60, hd)
    res = r.ev["begin"] = host.cmd({"cmd": "coop_dialog_back"})
    back, secs = until(lambda: stk(cl)[-1:] == GEO, 30.0, 0.25)
    r.ev["release"] = {"clientTop": back, "s": secs, "client": stk(cl), "host": stk(host)}
    red = rep.get("ok") is True and left is not None
    r.cell("press on the base-placement hold", refused(rep, 65) and left is None and res.get("ok") is True and back,
           {"reply": rep, "left": left, "begin": res, "release": r.ev["release"]},
           "the harness released the base-placement hold no player can close" if red else "unexpected outcome")
ROWS = {"U7b-1": u7b_1, "U7b-2": u7b_2, "U7b-3": u7b_3, "U7b-4": u7b_4}

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
def start_a(): return (lambda js: (js.host, js.client))(shared_fixture.bring_up("w2u7ba", (49324, 49325, 47304)))
def start_pair(tag, labels, bring):
    host = GameClient("host", labels[0], make_user_dir(tag + "_host"))
    client = GameClient("client", labels[1], make_user_dir(tag + "_client"))
    try:
        host.spawn(); client.spawn(); host.connect(); client.connect()
        bring(host, client)
    except BaseException as e:
        cap = {gc.name: safe(lambda gc=gc: {"stack": stk(gc), "dlg": dlg(gc)}) for gc in (host, client)}
        try:
            shutdown_clients(host, client)
        finally:
            raise RuntimeError("%s | %s" % (short(str(e), 600), short(cap, 900))) from e
    return host, client
BOOTS = (("A", start_a, ("U7b-4", "U7b-1")),
         ("B", lambda: start_pair("w2u7bb", (49326, 49327), lambda h, c: session.new_campaign(h, c, port="47306")), ("U7b-2",)),
         ("C", lambda: start_pair("w2u7bc", (49329, 49330), lambda h, c: tld._campaign_lobby(h, c, "47308")), ("U7b-3",)))

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
        rows = [exec_row(rid, booted[0], booted[1], ctx) for rid in rids]
        if key == "A" and not rows[0].err:
            u7b_4_diag(rows[0], ctx)
        for r in rows:
            report(r, results)
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
    print("\ntest_w2_dialog_back_guard: %d/%d passed (pass=%s fail=%s) in %.1fs (boot walls %s)%s"
          % (len(passed), len(order), passed, failed, time.time() - t0, walls,
             (" problems %s" % problems) if problems else ""), flush=True)
    return 0 if not failed and not problems else 2

if __name__ == "__main__":
    sys.exit(main())
