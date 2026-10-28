"""W2-H55 stage S-A (spec rewrite/prompts/w2h55_host_drop_dialog_resumeack.md (f); TASK 0 rewrite/w2h55-task0/sa/CONSTANTS.md; F18081,
R-H55-0): when the host's TCP thread drops the partner on a failed send (or a bad frame) during a co-op campaign with no live battle, the -3
arm pushes the wait dialog 62 without CoopSession::onClientDrop(): resumeAck keeps its campaign-start true and the 62 reads "All players
connected" with RESUME shown and SAVE & QUIT / ABANDON GAME hidden for a partner who is gone. A failed receive (-2) takes the canonical drop.
  Row R-A (the lever; key "49184", dirs w2h55_a_*): session.new_campaign (SEPARATE gm1, tcp), both tops GeoscapeState unchanged STABLE_S;
  host force_send_failure (TEST-ONLY, one-shot, -3); the client's 21 within W_21; the host's 62 on top within SEEN_S; settled; R1; R2.
  Cells: A-pre GUARD (resumeAck true before the arm, armed + ARMED +1, the 21, the 62 settled); A-hatch RED (SAVE & QUIT and ABANDON GAME
  shown at R1 and R2); A-resume RED (the wait: RESUME hidden, "...to reconnect", at R1 and R2); A-ack RED (resumeAck false at R1); A-drop RED
  (FREEZE +1, DROP +1, SEND_LOST_GEO +1, SEND_LOST +0); A-common GUARD (both alive at R2, no new crash file).
  Row R-B (the control, LAST; dirs w2h55_b_*): the same boot; client.kill(); the 62; settled; R1; R2. Cells: B-pre GUARD (the 62 settled);
  B-dialog GUARD (the hatch and the wait at R1 and R2, resumeAck false at R1); B-drop GUARD (FREEZE +1, DROP +1; SEND_LOST_GEO recorded);
  B-common GUARD (the host alive at R2, no new crash file).
Nothing is clicked: R1 = coop_dialog_info + list_widgets (RESUME / SAVE & QUIT / ABANDON GAME: visible, hidden) + get_coop once every
TextButton on the top CoopState reads hidden false plus SETTLE_S; R2 = HOLD_S later. QH55-2 (a), red build only: a kill can race to
the same -3; a row B whose EVIDENCE shows the F18081 signature (FREEZE +1, DROP +0, a READY 62) is recorded and the file run ONCE
more (that run binds). Red (commit R1): exit 2, RED exactly on A-hatch, A-resume, A-ack, A-drop. A precondition miss ends its row (cells "not
reached"); a boot miss fails the row "boot" with ONE CAPTURE line. ONE EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict;
exit 0 only when every cell passes, else 2. one foreground run per invocation.
Run: python tools/coop_test/test_host_drop_dialog.py
"""
import json, os, sys, time  # noqa: E401
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
from harness import GameClient, make_user_dir, cpu_load, cpu_text  # noqa: E402

KEY = "49184"
POLL_S, W_21, SEEN_S, SHOWN_S, SETTLE_S, HOLD_S, STABLE_S, BOOT_S = 0.1, 15.0, 15.0, 10.0, 2.0, 10.0, 2.0, 60.0
RC_OK = (0, 3221226505)
READY, WAITING = "All players connected", "to reconnect"
NEEDLES = {"ARMED": "[coop-test] force_send_failure: armed", "FREEZE": "[coop-session] freeze (lobbyMode=",
           "DROP": "[coop-session] onClientDrop", "SEND_LOST_GEO": "[coop] W2-H55: the partner was lost on a failed send - the canonical drop",
           "SEND_LOST": "R4-L2: the partner was lost on a failed send during the battle"}
NAMES = ("RESUME", "SAVE & QUIT", "ABANDON GAME")

class Stop(Exception):
    """a WAIT timed out or a precondition missed: the row ends here"""

def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]

def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead or gone machine is a value
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
    return pick(q(gc, {"cmd": "get_coop"}), ("resumeAck", "onConnect", "coopSession", "clientName", "lobbyMode", "lobbyClosed", "error"))

def dlg(gc):
    return pick(q(gc, {"cmd": "coop_dialog_info"}), ("present", "code", "title", "backText", "backVisible", "saveQuitVisible", "abandonVisible",
                                                     "error"))

def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []

def since(gc, n0, needle):
    return [ln.split("\t")[-1][:220] for ln in log(gc)[n0:] if needle in ln]

def counts(gc, n0):
    lines = log(gc)[n0:]
    return {k: sum(1 for ln in lines if v in ln) for k, v in NEEDLES.items()}

def wait(desc, pred, timeout, interval=POLL_S):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return round(time.time() - t0, 2)
        time.sleep(interval)
    raise Stop("WAIT %s: timed out after %.0f s" % (desc, timeout))

def cpu():
    return cpu_text(cpu_load()["cpu"])

def buttons(gc):
    """the top state's name and its TextButtons (text, visible, hidden)"""
    r = q(gc, {"cmd": "list_widgets"})
    return (r.get("state") or "").replace("class OpenXcom::", ""), [pick(w, ("text", "visible", "hidden")) for w in r.get("widgets", [])
                                                                    if "TextButton" in (w.get("type") or "")]

def named(bs):
    return {n: next((pick(b, ("visible", "hidden")) for b in bs if (b.get("text") or "").strip().upper() == n), None) for n in NAMES}

def sight62(h, tt):
    """coop_dialog_info present and code 62 on a top CoopState within SEEN_S -> seconds after the trigger"""
    wait("the host's 62 on a top CoopState", lambda: (lambda d: d.get("present") and d.get("code") == 62)(dlg(h)) and top(h) == "CoopState",
         SEEN_S)
    return round(time.time() - tt, 2)

def settled(h, tt, ev):
    """list_widgets until the top state is CoopState and every TextButton reads hidden false within SHOWN_S; then SETTLE_S"""
    t0, trail = time.time(), ev.setdefault("trail", [])
    while time.time() - t0 < SHOWN_S:
        st, bs = buttons(h)
        e = [st, named(bs)]
        if not trail or trail[-1][1:] != e:
            trail.append([round(time.time() - tt, 2)] + e)
        if st == "CoopState" and bs and all(b.get("hidden") is False for b in bs):
            ev["settled s"] = round(time.time() - tt, 2)
            time.sleep(SETTLE_S)
            return
        time.sleep(POLL_S)
    raise Stop("WAIT the 62's widgets settled: timed out after %.0f s" % SHOWN_S)

def read(h, tt):
    st, bs = buttons(h)
    return {"t": round(time.time() - tt, 2), "dialog": dlg(h), "top": st, "buttons": named(bs), "coop": coop(h)}

def hatch(rd):
    d, b = rd["dialog"], rd["buttons"]
    return (d.get("saveQuitVisible") is True and d.get("abandonVisible") is True
            and all((b.get(n) or {}).get("visible") is True and (b.get(n) or {}).get("hidden") is False for n in ("SAVE & QUIT", "ABANDON GAME")))

def waits(rd):
    d, t = rd["dialog"], rd["dialog"].get("title") or ""
    return (d.get("backVisible") is False and (rd["buttons"].get("RESUME") or {}).get("visible") is False and t != READY and WAITING in t)

class Row:
    def __init__(self, rid, cells, x):
        self.rid, self.cells, self.x, self.fails, self.done, self.t0, self.n_h = rid, cells, x, [], set(), time.time(), 0
        self.cr0, self.ev = session._crash_log_snapshot(), {}

    def evidence(self):
        print("EVIDENCE %s: %s" % (self.rid, json.dumps(self.ev, sort_keys=True, default=str)), flush=True)

    def cell(self, cid, kind, label, ok):
        print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label), flush=True)
        self.done.add(cid)
        self.fails += [] if ok else [cid]

    def stop(self, why):
        for cid in [c for c in self.cells if c not in self.done]:
            print("FAIL %s: not reached (%s)" % (cid, str(why)[:160]), flush=True)
            self.fails.append(cid)

    def end(self, results, walls):
        """ONE CAPTURE line when a cell failed, then the row verdict"""
        x, walls[self.rid] = self.x, round(time.time() - self.t0, 1)
        if self.fails:
            cap = {n: {"stack": stack(gc), "get_coop": coop(gc), "coop_dialog_info": dlg(gc)} for n, gc in (("host", x.host), ("client", x.client))
                   if alive(gc)}
            if alive(x.host):
                cap["host needle deltas"] = counts(x.host, self.n_h)
                cap["HL"] = [ln.split("\t")[-1][:200] for ln in log(x.host) if "[coop]" in ln or "coop-session" in ln][-12:]
            cap["new crash"] = sorted(session._crash_log_snapshot() - self.cr0)
            print("CAPTURE %s: %s" % (self.rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
        results[self.rid] = not self.fails
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)

    def boot_miss(self, results, walls):
        print("FAIL %s boot: the boot did not reach both tops GeoscapeState unchanged %.0f s (%s)" % (self.rid, STABLE_S, self.x.err), flush=True)
        self.fails.append("boot")
        self.end(results, walls)

def baseline(r, x):
    """just before the trigger: crash snapshot, the host log's line count, the host's stack and get_coop, CPU"""
    r.cr0, r.n_h = session._crash_log_snapshot(), len(log(x.host))
    r.ev.update({"cpu": cpu(), "host stack before": stack(x.host), "host get_coop before": coop(x.host)})

def row_a(x, results, walls):
    r = Row("R-A", ["A-pre", "A-hatch", "A-resume", "A-ack", "A-drop", "A-common"], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c, ev = x.host, x.client, r.ev
    try:
        baseline(r, x)
        ack0 = ev["host get_coop before"].get("resumeAck") is True
        ev["trigger"] = pick(q(h, {"cmd": "force_send_failure"}), ("ok", "armed", "error"))
        tt = time.time()
        ev["trigger at"] = time.strftime("%H:%M:%S")
        try:
            ev["21 s"] = wait("the client's 21", lambda: dlg(c).get("code") == 21, W_21)
            ev["client"] = {"stack": stack(c), "dialog": dlg(c)}
            ev["62 s"] = sight62(h, tt)
            settled(h, tt, ev)
        except Stop as e:
            ev["stop"] = str(e)
        n = counts(h, r.n_h)
        ok = ack0 and ev["trigger"].get("armed") is True and n["ARMED"] == 1 and "stop" not in ev
        if not ok:
            ev["needles"] = n
            r.evidence()
            r.cell("A-pre", "GUARD", "resumeAck true before the arm, armed true + ARMED +1, the client's 21 within %.0f s, the host's 62 on top, "
                   "settled" % W_21, False)
            raise Stop("A-pre: %s" % ev.get("stop", "resumeAck %s, armed %s, ARMED %d" % (ack0, ev["trigger"].get("armed"), n["ARMED"])))
        ev["R1"] = read(h, tt)
        time.sleep(HOLD_S)
        ev["R2"] = read(h, tt)
        ev["host stack R2"], ev["needles"], ev["alive R2"] = stack(h), counts(h, r.n_h), [alive(h), alive(c)]
        ev["client"]["top dialog R2"] = dlg(c)
        ev["new crash"] = sorted(session._crash_log_snapshot() - r.cr0)
        r.evidence()
        r.cell("A-pre", "GUARD", "resumeAck true before the arm, armed true + ARMED +1, the client's 21 within %.0f s, the host's 62 on top, "
               "settled" % W_21, True)
        R1, R2, n = ev["R1"], ev["R2"], ev["needles"]
        r.cell("A-hatch", "RED", "SAVE & QUIT and ABANDON GAME shown (dialog + TextButtons visible, not hidden) at R1 and R2 (red today: hidden, "
               "F18081)", hatch(R1) and hatch(R2))
        r.cell("A-resume", "RED", "the wait at R1 and R2: RESUME hidden, the title contains \"%s\" and is not \"%s\" (red today: \"%s\", RESUME "
               "shown, F10809)" % (WAITING, READY, READY), waits(R1) and waits(R2))
        r.cell("A-ack", "RED", "the host's resumeAck false at R1 (red today: true, F18186)", R1["coop"].get("resumeAck") is False)
        r.cell("A-drop", "RED", "FREEZE +1, DROP +1, SEND_LOST_GEO +1, SEND_LOST +0 (red today: DROP +0, SEND_LOST_GEO +0)",
               (n["FREEZE"], n["DROP"], n["SEND_LOST_GEO"], n["SEND_LOST"]) == (1, 1, 1, 0))
        r.cell("A-common", "GUARD", "host and client alive at R2, no new crash_*.log since the row's baseline",
               ev["alive R2"] == [True, True] and not ev["new crash"])
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end(results, walls)

def row_b(x, results, walls):
    r = Row("R-B", ["B-pre", "B-dialog", "B-drop", "B-common"], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, ev = x.host, r.ev
    try:
        baseline(r, x)
        tt = time.time()
        ev["trigger at"] = time.strftime("%H:%M:%S")
        x.client.kill()
        ev["trigger"] = "client.kill() reaped in %.2f s" % (time.time() - tt)
        try:
            ev["62 s"] = sight62(h, tt)
            settled(h, tt, ev)
        except Stop as e:
            ev["stop"] = str(e)
            ev["needles"] = counts(h, r.n_h)
            r.evidence()
            r.cell("B-pre", "GUARD", "the host's 62 on top within %.0f s, settled" % SEEN_S, False)
            raise
        ev["R1"] = read(h, tt)
        time.sleep(HOLD_S)
        ev["R2"] = read(h, tt)
        ev["host stack R2"], ev["needles"], ev["alive R2"] = stack(h), counts(h, r.n_h), alive(h)
        ev["new crash"] = sorted(session._crash_log_snapshot() - r.cr0)
        R1, R2, n = ev["R1"], ev["R2"], ev["needles"]
        race = n["FREEZE"] == 1 and n["DROP"] == 0 and (R1["dialog"].get("title") == READY or R2["dialog"].get("title") == READY)
        ev["path"] = ("F18081 race signature (FREEZE +1, DROP +0, a READY 62): QH55-2 (a) - on the red build run the file ONCE more" if race
                      else "send (-3, SEND_LOST_GEO +1)" if n["SEND_LOST_GEO"] else "receive (-2, canonical)" if n["DROP"] else "other")
        r.evidence()
        r.cell("B-pre", "GUARD", "the host's 62 on top within %.0f s, settled" % SEEN_S, True)
        r.cell("B-dialog", "GUARD", "the hatch and the wait at R1 and R2, resumeAck false at R1",
               hatch(R1) and hatch(R2) and waits(R1) and waits(R2) and R1["coop"].get("resumeAck") is False)
        r.cell("B-drop", "GUARD", "FREEZE +1, DROP +1 (SEND_LOST_GEO %d recorded)" % n["SEND_LOST_GEO"], n["FREEZE"] == 1 and n["DROP"] == 1)
        r.cell("B-common", "GUARD", "the host alive at R2, no new crash_*.log since the row's baseline", ev["alive R2"] and not ev["new crash"])
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end(results, walls)

def boot(rid, tag):
    """host + client spawn, connect, session.new_campaign(port=KEY), both tops GeoscapeState unchanged STABLE_S (else x.err)"""
    x = SimpleNamespace(rid=rid, tag=tag, host=None, client=None, err=None)
    try:
        x.host, x.client = GameClient("host", None, make_user_dir(tag + "_host")), GameClient("client", None, make_user_dir(tag + "_client"))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
        session.new_campaign(x.host, x.client, port=KEY)
        t0, last, tch = time.time(), None, time.time()
        while True:
            s = (tuple(stack(x.host)), tuple(stack(x.client)))
            if s != last:
                last, tch = s, time.time()
            if s[0] and s[1] and s[0][-1] == s[1][-1] == "GeoscapeState" and time.time() - tch >= STABLE_S:
                break
            if time.time() - t0 > BOOT_S:
                raise Stop("both tops GeoscapeState unchanged %.0f s: not within %.0f s" % (STABLE_S, BOOT_S))
            time.sleep(POLL_S)
    except Exception as e:
        x.err = short(e, 600)
        cap = {n: {"stack": stack(gc), "coop_dialog_info": dlg(gc), "get_coop": coop(gc)} for n, gc in (("host", x.host), ("client", x.client))
               if alive(gc)}
        print("CAPTURE %s boot: %s" % (rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
    return x

def shut(x):
    """every machine of the boot (a killed client was reaped by kill()) -> the shutdown failures"""
    failed = []
    for gc in (x.client, x.host):
        try:
            if gc is not None and gc.proc is not None:
                gc.shutdown(expected_returncodes=RC_OK)
        except Exception as e:
            print("FAIL %s shutdown (%s): %s" % (x.tag, gc.name, short(e, 300)), flush=True)
            failed.append("%s shutdown %s" % (x.tag, gc.name))
    return failed

def main():
    t0, results, walls, failed = time.time(), {}, {}, []
    for rid, tag, row in (("R-A", "w2h55_a", row_a), ("R-B", "w2h55_b", row_b)):
        tb = time.time()
        x = boot(rid, tag)
        walls[tag + " boot"] = round(time.time() - tb, 1)
        try:
            row(x, results, walls)
        finally:
            failed += shut(x)
        walls[tag] = round(time.time() - tb, 1)
    failed += [rid for rid in ("R-A", "R-B") if not results.get(rid)]
    print("\ntest_host_drop_dialog: %d/2 rows passed (fail=%s) walls %s in %.1fs" % (sum(1 for rid in ("R-A", "R-B") if results.get(rid)),
                                                                                     failed, json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
