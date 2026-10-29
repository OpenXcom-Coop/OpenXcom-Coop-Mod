"""W2-H60 stage S-A (spec rewrite/prompts/w2h60_rx_throw_drop.md (f), ORCHESTRATOR RULINGS QH60-1..QH60-6 (a) and R-H60-R-1 (QH60-2 (b):
no CS edit, row R-B dropped); TASK 0 rewrite/w2h60-task0/sa/CONSTANTS.md; lead L-H58-1, ruling R-LT6-1): when a message handler throws,
updateCoopTask()'s receive-loop catch puts the same message back and sets -3. On a campaign HOST that loops: the waiting window 62 reads
"All players connected" over a partner who is still connected, the partner's name is cleared, and the message throws again every frame
(hundreds of crash logs a second). A message one game cannot read must be dropped once and the partner dropped as a bad frame does (TCP:
the host thread's canonical drop; UDP: the canonical -2), so the partner sees "Server connection lost" and can rejoin.
Three rows, one fresh boot pair each (key "49201", dirs w2h60_<row>_host / _client / _client2; session.new_campaign SEPARATE gm1, R-U
transport udp; then F.stable_geo(host, client, STABLE_S)). Every trigger is the TEST-ONLY lever throw_next_rx (commit P1).
  R-A (tcp) host throw_next_rx {state: "target_positions"}; MARKED on the host within W_MARK; the client's 21 within W_21; wait(host) R1 / R2;
      then (only if A-partner passed) client.kill(), F.rejoin(host, client2, KEY, NAME), F.resume_and_clear(host), client2's top
      GeoscapeState within W_GEO, F.quick_save(host). Cells: A-pre GUARD, A-flood FIX, A-hatch FIX, A-drop FIX, A-name FIX, A-partner FIX,
      A-rejoin FIX, A-resume FIX, A-save FIX, A-common GUARD.
  R-U (udp) as R-A over transport udp, the client's 21 within W_21U, no rejoin. Cells: U-pre GUARD, U-flood FIX, U-hatch FIX, U-drop FIX,
      U-partner FIX, U-common GUARD.
  R-C (tcp, the client cannot read a message: control, LAST) client throw_next_rx {state: "target_positions"}; MARKED on the client; the
      client's 440 within W_440; wait(host) R1; R2 = HOLD_S after the 440. Cells: C-pre GUARD, C-440 GUARD, C-log FIX, C-host GUARD,
      C-common GUARD.
wait(host) = F.wait_62(host, SEEN_S), the top's TextButtons settled (every TextButton hidden false, W2-H55 HDD's settled, copied) +
SETTLE_S = R1; R2 = HOLD_S later. hatch = code 62, saveQuitVisible and abandonVisible true, RESUME visible false, title contains "to
reconnect". CRASH = new files in F.crashes() (the lane crash folder) since the row's baseline. 21 cells. Red (commit R1, P1 build): exit 2,
RED exactly on A-flood, A-hatch, A-drop, A-name, A-partner, A-rejoin, A-resume, A-save, U-flood, U-hatch, U-drop, U-partner, C-log (13).
A precondition miss ends its row (later cells "not reached" = FAIL); a boot miss fails the row "boot" with ONE CAPTURE line. ONE EVIDENCE
line per row, one PASS / FAIL line per cell, then the row verdict; exit 0 only when every cell passes, else 2. Kills only
its own clients (by their GameClient). The red writes thousands of crash_*.log files (the builder moves them out after the run). one
foreground run per invocation.
Run: python tools/coop_test/test_rx_throw_drop.py   (OXC_HARNESS_SLOT selects the lane)
"""
import json, os, sys, time  # noqa: E401
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import drop_fixture as F  # noqa: E402
from harness import GameClient, make_user_dir, cpu_load, cpu_text  # noqa: E402

KEY = "49201"
POLL_S, W_MARK, W_21, W_21U, W_440, SEEN_S = 0.05, 10.0, 15.0, 25.0, 15.0, 15.0
SETTLE_S, HOLD_S, STABLE_S, W_GEO, SHOWN_S, CRASH_MAX = 2.0, 5.0, 2.0, 10.0, 10.0, 9
RC_OK = (0, 3221226505)
DEFAULT_NAME, WAITING = "ClientPlayer", "to reconnect"
NEEDLES = {"ARMED": "[coop-test] throw_next_rx: armed", "MARKED": "[coop-test] throw_next_rx: marked",
           "H60H": "[coop] a message could not be handled - the partner is dropped",
           "H60C": "[coop] a message could not be handled - the session ends",
           "LOSTGEO": "[coop] the partner was lost on a failed send - the canonical drop",
           "FREEZE": "[coop-session] freeze (lobbyMode=", "DROP": "[coop-session] onClientDrop"}
NAMES = ("RESUME", "SAVE & QUIT", "ABANDON GAME")
CELLS = {"R-A": ("A-pre", "A-flood", "A-hatch", "A-drop", "A-name", "A-partner", "A-rejoin", "A-resume", "A-save", "A-common"),
         "R-U": ("U-pre", "U-flood", "U-hatch", "U-drop", "U-partner", "U-common"),
         "R-C": ("C-pre", "C-440", "C-log", "C-host", "C-common")}
FIX = ("A-flood", "A-hatch", "A-drop", "A-name", "A-partner", "A-rejoin", "A-resume", "A-save", "U-flood", "U-hatch", "U-drop", "U-partner",
       "C-log")


class Stop(Exception):
    """a precondition missed: the row ends here"""


def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]


def js(v):
    return json.dumps(v, sort_keys=True, default=str)


def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # noqa: BLE001 - a dead or gone machine is a value
        return {"error": short(e, 200)}


def pick(r, keys):
    return {k: r.get(k) for k in keys}


def alive(gc):
    return gc is not None and gc.proc is not None and gc.proc.poll() is None


def stack(gc):
    return [s.replace("class OpenXcom::", "") for s in q(gc, {"cmd": "get_state"}).get("states", [])]


def top(gc):
    return (stack(gc) or [None])[-1]


def coop(gc):
    return pick(q(gc, {"cmd": "get_coop"}), ("onConnect", "resumeAck", "coopSession", "clientName", "lobbyMode", "error"))


def dlg(gc):
    return pick(q(gc, {"cmd": "coop_dialog_info"}), ("present", "code", "title", "backText", "backVisible", "saveQuitVisible", "abandonVisible",
                                                     "error"))


def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def counts(gc, n0):
    lines = log(gc)[n0:]
    return {k: sum(1 for ln in lines if v in ln) for k, v in NEEDLES.items()}


def marked(gc, n0):
    return next((ln.split("\t")[-1][:200] for ln in log(gc)[n0:] if NEEDLES["MARKED"] in ln), None)


def wait(pred, timeout, interval=POLL_S):
    """seconds until pred() holds, or None after timeout"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return round(time.time() - t0, 3)
        time.sleep(interval)
    return None


def cpu():
    return cpu_text(cpu_load()["cpu"])


def buttons(gc):
    r = q(gc, {"cmd": "list_widgets"})
    return (r.get("state") or "").replace("class OpenXcom::", ""), [pick(w, ("text", "visible", "hidden")) for w in r.get("widgets", [])
                                                                    if "TextButton" in (w.get("type") or "")]


def named(bs):
    return {n: next((pick(b, ("visible", "hidden")) for b in bs if (b.get("text") or "").strip().upper() == n), None) for n in NAMES}


def crash_n(c0):
    return len(F.crashes() - c0)


def read(h, tt, c0):
    st, bs = buttons(h)
    return {"t": round(time.time() - tt, 3), "stack": stack(h), "dialog": dlg(h), "top": st, "buttons": named(bs), "coop": coop(h),
            "crash": crash_n(c0)}


def hatch(rd):
    d, b = rd["dialog"], rd["buttons"]
    return bool(d.get("code") == 62 and d.get("saveQuitVisible") is True and d.get("abandonVisible") is True
                and (b.get("RESUME") or {}).get("visible") is False and WAITING in (d.get("title") or ""))


def wait_host(r, h, tt):
    """F.wait_62 + settled (every TextButton of the top CoopState hidden false, F18080) + SETTLE_S -> R1 (else Stop)"""
    w = F.wait_62(h, SEEN_S)
    r.ev["62"] = {"ok": w["ok"], "at s": round(time.time() - tt, 3), "dialog": w["dialog"], "hostStack": w["hostStack"]}
    if not w["ok"]:
        raise Stop("WAIT the host's 62 on a top CoopState: not within %.0f s" % SEEN_S)
    t0, trail = time.time(), r.ev.setdefault("settle trail", [])
    while time.time() - t0 < SHOWN_S:
        st, bs = buttons(h)
        e = [st, named(bs)]
        if not trail or trail[-1][1:] != e:
            trail.append([round(time.time() - tt, 3)] + e)
        if st == "CoopState" and bs and all(b.get("hidden") is False for b in bs):
            r.ev["settled s"] = round(time.time() - tt, 3)
            time.sleep(SETTLE_S)
            return
        time.sleep(POLL_S)
    raise Stop("WAIT the 62's widgets settled: not within %.0f s" % SHOWN_S)


def trim_rejoin(rj):
    return {k: rj.get(k) for k in ("t68", "ack", "ackSkipped", "buildNewBase", "endJoin", "join_tcp", "profile_ok")} | {
        "last trail": (rj.get("trail") or [None])[-1]}


class Row:
    def __init__(self, x):
        self.x, self.rid, self.res, self.ev, self.t0 = x, x.rid, {}, {}, time.time()

    def cell(self, cid, ok, label):
        self.res[cid] = (bool(ok), label)

    def finish(self, results, walls, stop=None):
        x = self.x
        if stop:
            self.ev["stop"] = stop
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        fails = []
        for cid in CELLS[self.rid]:
            ok, label = self.res.get(cid, (False, "not reached (%s)" % (str(stop)[:160] if stop else "?")))
            print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, "FIX" if cid in FIX else "GUARD", label), flush=True)
            fails += [] if ok else [cid]
        if stop and not x.err:
            cap = {g.name: {"stack": stack(g), "coop_dialog_info": dlg(g), "get_coop": coop(g)} for g in procs(x) if alive(g)}
            print("CAPTURE %s: %s" % (self.rid, js(cap)), flush=True)
        walls[self.rid] = round(time.time() - self.t0, 1)
        results[self.rid] = fails
        print(("PASS %s" % self.rid) if not fails else ("FAIL %s: %s" % (self.rid, " ".join(fails))), flush=True)

    def boot_miss(self, results, walls):
        for cid in CELLS[self.rid]:
            print("FAIL %s %s: boot (%s)" % (cid, "FIX" if cid in FIX else "GUARD", self.x.err), flush=True)
        walls[self.rid], results[self.rid] = 0.0, list(CELLS[self.rid])
        print("FAIL %s: boot" % self.rid, flush=True)


def baseline(r, x):
    x.c0, x.n_h, x.n_c = F.crashes(), len(log(x.host)), len(log(x.client))
    hc = coop(x.host)
    r.ev["base"] = {"cpu": cpu(), "host stack": stack(x.host), "client stack": stack(x.client), "host get_coop": hc,
                    "client get_coop": coop(x.client), "crash folder": len(x.c0)}
    x.name = hc.get("clientName") or DEFAULT_NAME
    r.ev["NAME"] = x.name if hc.get("clientName") else "%s (get_coop.clientName empty: the name new_campaign passed)" % DEFAULT_NAME


def arm(r, gc, n0):
    """throw_next_rx {state: target_positions} on gc; MARKED within W_MARK -> the pre cell's ok"""
    ta = time.time()
    r.ev["arm"] = pick(q(gc, {"cmd": "throw_next_rx", "state": "target_positions"}), ("ok", "armed", "error"))
    r.ev["arm at"] = time.strftime("%H:%M:%S")
    r.ev["mark s"] = wait(lambda: marked(gc, n0) is not None, W_MARK)
    r.ev["MARKED"] = mk = marked(gc, n0)
    n = counts(gc, n0)
    ok = r.ev["arm"].get("armed") is True and n["ARMED"] == 1 and n["MARKED"] == 1 and mk is not None and "target_positions" in mk
    return ta, ok, "armed %s, ARMED %d, MARKED %d (%s) within %.0f s" % (r.ev["arm"].get("armed"), n["ARMED"], n["MARKED"], mk, W_MARK)


def reads(r, x, tt):
    r.ev["R1"] = read(x.host, tt, x.c0)
    time.sleep(HOLD_S)
    r.ev["R2"] = read(x.host, tt, x.c0)
    r.ev["client R2"] = {"stack": stack(x.client), "dialog": dlg(x.client), "get_coop": coop(x.client)} if alive(x.client) else "gone"
    r.ev["needles host"], r.ev["needles client"] = counts(x.host, x.n_h), counts(x.client, x.n_c)


def geo_cells(r, x, p, w21):
    """the shared R-A / R-U trigger and cells (p = "A" or "U") -> the 21 seen"""
    h, c, ev = x.host, x.client, r.ev
    ack0 = ev["base"]["host get_coop"].get("resumeAck") is True
    tt, ok, why = arm(r, h, x.n_h)
    r.cell(p + "-pre", ack0 and ok, "host resumeAck %s before the arm; %s" % (ack0, why))
    if not (ack0 and ok):
        raise Stop("%s-pre: resumeAck %s; %s" % (p, ack0, why))
    ev["21 s"] = t21 = wait(lambda: dlg(c).get("code") == 21 and top(c) == "CoopState", w21)
    ev["client at the 21 wait"] = {"stack": stack(c), "dialog": dlg(c)}
    wait_host(r, h, tt)
    reads(r, x, tt)
    R1, R2, n = ev["R1"], ev["R2"], ev["needles host"]
    r.cell(p + "-flood", R2["crash"] == 1, "CRASH == 1 at R2: %d (R1 %d) (red today: hundreds a second, F18427)" % (R2["crash"], R1["crash"]))
    r.cell(p + "-hatch", hatch(R1) and hatch(R2) and R1["coop"].get("resumeAck") is False,
           "hatch at R1 %s / R2 %s (title %r, RESUME %s, SAVE & QUIT %s, ABANDON GAME %s); resumeAck at R1 %s (red today: \"All players "
           "connected\", RESUME shown)" % (hatch(R1), hatch(R2), R2["dialog"].get("title"), R2["buttons"].get("RESUME"),
                                         R2["buttons"].get("SAVE & QUIT"), R2["buttons"].get("ABANDON GAME"), R1["coop"].get("resumeAck")))
    return t21, R1, R2, n


def row_a(x, results, walls):
    r = Row(x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c, ev = x.host, x.client, r.ev
    try:
        baseline(r, x)
        t21, R1, R2, n = geo_cells(r, x, "A", W_21)
        r.cell("A-drop", (n["H60H"], n["LOSTGEO"], n["DROP"]) == (1, 1, 1) and R2["coop"].get("coopSession") is False
               and R2["coop"].get("onConnect") == 1, "host H60H %d, LOSTGEO %d, DROP %d (want 1 / 1 / 1); at R2 coopSession %s, onConnect %s "
               "(want false, 1)" % (n["H60H"], n["LOSTGEO"], n["DROP"], R2["coop"].get("coopSession"), R2["coop"].get("onConnect")))
        r.cell("A-name", R1["coop"].get("clientName") == x.name, "host clientName at R1 %r (want %r; red today: \"\", a3)"
               % (R1["coop"].get("clientName"), x.name))
        r.cell("A-partner", t21 is not None, "the client's top CoopState 21 within %.0f s: %s (red today: it stays connected on GeoscapeState)"
               % (W_21, t21))
        if t21 is None:
            raise Stop("A-partner failed: the rejoin is not reached")
        c.kill()
        x.c2 = GameClient("client2", None, make_user_dir("w2h60_a_client2"))
        ev["rejoin"] = rj = trim_rejoin(F.rejoin(h, x.c2, KEY, x.name))
        r.cell("A-rejoin", rj["t68"] is not None and rj["ack"] is not None, "client2 t68 %s, ack %s" % (rj["t68"], rj["ack"]))
        if rj["t68"] is None or rj["ack"] is None:
            raise Stop("A-rejoin failed: the resume is not reached")
        rc = F.resume_and_clear(h)
        ev["resume"] = {"ok": rc.get("ok"), "click": rc["resume"].get("click"), "cancel": "cancel" in rc, "end": rc.get("end")}
        ev["client2 geo s"] = geo = wait(lambda: top(x.c2) == "GeoscapeState", W_GEO)
        r.cell("A-resume", rc.get("ok") and geo is not None, "resume_and_clear ok %s; client2's top GeoscapeState within %.0f s: %s"
               % (rc.get("ok"), W_GEO, geo))
        if not (rc.get("ok") and geo is not None):
            raise Stop("A-resume failed: the save is not reached")
        sv = F.quick_save(h)
        ev["save"] = {k: sv.get(k) for k in ("ok", "seen54", "written", "t", "trigger")} | {"last trail": (sv.get("trail") or [None])[-1]}
        r.cell("A-save", sv.get("ok"), "quick_save ok %s (the 54 seen %s, _quick_.asav written %s)" % (sv.get("ok"), sv.get("seen54"),
                                                                                                     sv.get("written")))
    except Stop as e:
        stop = str(e)
    except Exception as e:  # noqa: BLE001 - a probe that raised ends the row like a precondition miss
        stop = "exception " + short(e, 300)
    else:
        stop = None
    al = [alive(h)] + ([alive(x.c2)] if x.c2 is not None else [])
    ev["alive end"], ev["crash end"], ev["needles host end"] = al, crash_n(x.c0), counts(h, x.n_h)
    r.cell("A-common", all(al), "host%s alive at the row's end %s; CRASH at the end %d (recorded, judged by A-flood)"
           % (" and client2" if x.c2 is not None else "", al, ev["crash end"]))
    r.finish(results, walls, stop)


def row_u(x, results, walls):
    r = Row(x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c, ev = x.host, x.client, r.ev
    try:
        baseline(r, x)
        t21, R1, R2, n = geo_cells(r, x, "U", W_21U)
        r.cell("U-drop", (n["H60H"], n["DROP"], n["LOSTGEO"]) == (1, 1, 0) and R2["coop"].get("coopSession") is False,
               "host H60H %d, DROP %d, LOSTGEO %d (want 1 / 1 / 0); coopSession at R2 %s (want false)"
               % (n["H60H"], n["DROP"], n["LOSTGEO"], R2["coop"].get("coopSession")))
        r.cell("U-partner", t21 is not None, "the client's top CoopState 21 within %.0f s: %s (red today: connected)" % (W_21U, t21))
        ev["alive R2"] = al = [alive(h), alive(c)]
        r.cell("U-common", al == [True, True], "host and client alive at R2 %s" % al)
        stop = None
    except Stop as e:
        stop = str(e)
    except Exception as e:  # noqa: BLE001
        stop = "exception " + short(e, 300)
    r.finish(results, walls, stop)


def row_c(x, results, walls):
    r = Row(x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c, ev = x.host, x.client, r.ev
    try:
        baseline(r, x)
        tt, ok, why = arm(r, c, x.n_c)
        r.cell("C-pre", ok, "the client's " + why)
        if not ok:
            raise Stop("C-pre: " + why)
        ev["440 s"] = t440 = wait(lambda: dlg(c).get("code") == 440 and top(c) == "CoopState", W_440)
        t4 = time.time()
        ev["client at 440"] = {"stack": stack(c), "dialog": dlg(c), "get_coop": coop(c)}
        r.cell("C-440", t440 is not None, "the client's top CoopState 440 within %.0f s: %s (%r)" % (W_440, t440, ev["client at 440"]["dialog"]
                                                                                                    .get("title")))
        wait_host(r, h, tt)
        ev["R1"] = R1 = read(h, tt, x.c0)
        rest = t4 + HOLD_S - time.time()
        if rest > 0:
            time.sleep(rest)
        ev["R2"] = R2 = read(h, tt, x.c0)
        ev["client R2"] = {"stack": stack(c), "dialog": dlg(c), "get_coop": coop(c)} if alive(c) else "gone"
        ev["needles host"], ev["needles client"] = nh, nc = counts(h, x.n_h), counts(c, x.n_c)
        r.cell("C-log", nc["H60C"] == 1, "the client's H60C %d (want 1; red today: 0)" % nc["H60C"])
        r.cell("C-host", hatch(R1) and nh["DROP"] == 1, "the host's hatch at R1 %s (title %r); host DROP %d (want 1)"
               % (hatch(R1), R1["dialog"].get("title"), nh["DROP"]))
        ev["alive R2"] = al = [alive(h), alive(c)]
        r.cell("C-common", al == [True, True] and 1 <= R2["crash"] <= CRASH_MAX, "both alive at R2 %s; 1 <= CRASH %d <= %d"
               % (al, R2["crash"], CRASH_MAX))
        stop = None
    except Stop as e:
        stop = str(e)
    except Exception as e:  # noqa: BLE001
        stop = "exception " + short(e, 300)
    r.finish(results, walls, stop)


def procs(x):
    return [g for g in (x.host, x.client, x.c2) if g is not None]


def boot(rid, tag, udp):
    """host + client spawn, connect, session.new_campaign(port=KEY), F.stable_geo (else x.err + ONE CAPTURE line)"""
    x = SimpleNamespace(rid=rid, tag=tag, host=None, client=None, c2=None, err=None, c0=set(), n_h=0, n_c=0, name=DEFAULT_NAME)
    try:
        x.host, x.client = GameClient("host", None, make_user_dir(tag + "_host")), GameClient("client", None, make_user_dir(tag + "_client"))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
        if udp:
            session.new_campaign(x.host, x.client, port=KEY, transport="udp")
        else:
            session.new_campaign(x.host, x.client, port=KEY)
        s = F.stable_geo(x.host, x.client, STABLE_S)
        if not s["ok"]:
            raise Stop("F.stable_geo: %s" % js(s))
    except Exception as e:  # noqa: BLE001 - a boot that raises is a boot miss
        x.err = short(e, 600)
        cap = {n: {"stack": stack(g), "coop_dialog_info": dlg(g), "get_coop": coop(g)} for n, g in (("host", x.host), ("client", x.client))
               if alive(g)}
        print("CAPTURE %s boot: %s" % (rid, js(cap)), flush=True)
    return x


def shut(x):
    """every live machine of the row (a killed one was reaped by kill()) -> the shutdown failures"""
    failed = []
    for g in procs(x)[::-1]:
        try:
            if g.proc is not None and g.proc is not g._shutdown_proc:
                g.shutdown(expected_returncodes=RC_OK)
        except Exception as e:  # noqa: BLE001
            print("FAIL %s shutdown (%s): %s" % (x.tag, g.name, short(e, 300)), flush=True)
            failed.append("%s shutdown %s" % (x.tag, g.name))
    return failed


def main():
    t0, results, walls, failed, opened = time.time(), {}, {}, [], []
    for rid, tag, row, udp in (("R-A", "w2h60_a", row_a, False), ("R-U", "w2h60_u", row_u, True), ("R-C", "w2h60_c", row_c, False)):
        tb = time.time()
        x = boot(rid, tag, udp)
        walls[tag + " boot"] = round(time.time() - tb, 1)
        try:
            row(x, results, walls)
        finally:
            failed += shut(x)
            opened += ["%s %s" % (tag, g.name) for g in procs(x) if g.proc is not None and g.proc.poll() is None]
        walls[tag] = round(time.time() - tb, 1)
    cells = [c for cs in CELLS.values() for c in cs]
    bad = sorted({c for fs in results.values() for c in fs}, key=cells.index)
    print("\ntest_rx_throw_drop: %d/%d cells pass; failing %s; shutdown failures %s; popen open %s; walls %s in %.1fs"
          % (len(cells) - len(bad), len(cells), bad or "none", failed or "none", opened or "none", js(walls), time.time() - t0), flush=True)
    return 2 if (bad or failed or opened) else 0


if __name__ == "__main__":
    sys.exit(main())
