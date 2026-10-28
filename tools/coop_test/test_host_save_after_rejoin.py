"""W2-H58 S-B HSR (tools/coop_test/test_host_save_after_rejoin.py): after the second player drops during a host save and rejoins, the
host's next save is written (L-LH54-2-2, ruling R-H58-0). Spec docs rewrite/prompts/w2h58_sb_rx_buffer.md (f) (stage S-B) and the common
file rewrite/prompts/w2h58_rejoin_world_kept.md (section F: the shared fixture drop_fixture.py, imported unchanged); TASK 0 values in
rewrite/w2h58-task0/sb/CONSTANTS.md. The partner uploads its world in 3000-byte chunks that the host appends to one global buffer
(mapData) and parses at the end marker. A partner that drops after some chunks leaves that half in the buffer through the drop and the
rejoin; the rejoined partner's next upload is glued to it, the YAML breaks at the seam and the host's receive loop re-queues the message
forever (crash logs, a 62 over a connected partner, the save never written) or drops the partner (F18424-F18428).
ONE boot (SEPARATE new_campaign on lobby key K1, both geoscapes stable), the controls first and the red row last:
  Row C0 (GUARD) C0-blob: the host stores the client's world under the campaign's id0 (present, bytes > 0).
  Row CB (control: no half-sent upload, then a second save) a quick save with the client running (id1), kill, client2 rejoins, RESUME,
         then LIVE, a second quick save with client2 (id2). CB-write1: the first _quick_.asav written, key(id1) present. CB-world: client2
         never BuildNewBaseState, its [GeoscapeState, CoopState] code 68 within JOIN_S, own(client2) holds (CB_NAME, CB). CB-buf0:
         buf(host) 0 after RESUME. CB-write2: the second _quick_.asav written after its trigger, key(id2) present, no new crash file.
  Row M1 (the red, LAST) an autosave drop of client2 at the host's first sight of its 54 once a half-sent upload is buffered (READY; b54 > 0,
         precondition), client3 rejoins, RESUME, the stale 54 CANCELLED when it is on top (F18431, W2-H59's), LIVE, then a host quick save
         with client3 (t3) and a 0.1 s window until the save landed (_quick_.asav after t3, pending "", top GeoscapeState) or 1 s after
         the first new crash file (QH58-B2 (a)) or SAVE2_S. M1-world (GUARD) as CB-world for client3. M1-buf (RED) b1 = buf(host) at
         DROP_READ_S after the kill == 0. M1-write (RED) _quick_.asav mtime after t3. M1-crash (RED) no crash file new since t3.
         M1-host (RED) host stack [GeoscapeState] and onConnect 1. M1-key (RED, ruling R-H58-B-1) key(id3) present with a fnv1a64
         different from key(id2)'s at the 54 (S-A's re-mint copy carries id2's bytes; only a landed upload changes the fnv).
         PRE-CRASH (GUARD) no crash file new since the boot start at t3.
Red today: M1-buf, M1-write, M1-crash, M1-host, M1-key FAIL; the other 7 cells PASS. Green (EB1: onClientDrop empties mapData): 12/12.
buf(gc) = get_coop.rxBufferBytes (the W2-H58 S-B probe); own(gc) = geo_state bases with coopIcon false as [name, coopBaseId]; key(id) =
coop_file_info {key: host_<id>_ClientPlayer.data}. Every rejoiner is a NEW GameClient on its own dir joining K1 by the name ClientPlayer.
Never dismiss_popup, coop_dialog_back or a base placement: a fresh world is evidence, never built on. One EVIDENCE line per row, one
PASS / FAIL line per cell, then the row verdict; a precondition miss ends its row (CAPTURE line) and every later row (cells "not
reached"); a boot miss fails every cell "boot" with ONE CAPTURE line. A red host is in a crash-log loop after the window: every process
is shut down right after it. WV-D95 / WV-D99 / WV-D100: ONE foreground run, no SKIP; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_host_save_after_rejoin.py   (OXC_HARNESS_SLOT selects the lane)"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import drop_fixture as F  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

K1 = "49195"
K2 = "49196"  # reserved for the BOOT replacement rule (two boots, PINNED SETUP VALUES); unused while the one boot holds
NAME = "ClientPlayer"
STABLE_S, SEEN_S, DROP_S, JOIN_S, ACK_S, SAVE_S = 5.0, 10.0, 5.0, 10.0, 30.0, 20.0
LIVE_S, READY_S = 10.0, 2.0  # bounds: the host's resume handshake after RESUME; a half-sent upload after the 54 sight (cap-save)
SUSPEND_DELAY_MS, DROP_READ_S, SAVE2_S = 0, 1.0, 20.0
ROWS = (("C0", ("C0-blob",)), ("CB", ("CB-write1", "CB-world", "CB-buf0", "CB-write2")),
        ("M1", ("M1-world", "M1-buf", "M1-write", "M1-crash", "M1-host", "M1-key", "PRE-CRASH")))
RED = ("M1-buf", "M1-write", "M1-crash", "M1-host", "M1-key")
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)


class Stop(Exception):
    """a precondition missed: the row ends here"""


def js(v):
    return json.dumps(v, sort_keys=True, default=str)


def kstr(r):
    return "%s %s %s" % ("present" if r.get("present") else "absent", r.get("bytes"), r.get("fnv1a64") or "-")


def live(host):
    """LIVE: the host's resume handshake is done (get_coop coopSession true). The host's deferred save (the 54, the saveID re-mint)
    runs only while coopSession is true (SaveGameState.cpp:255); RESUME turns it true about 0.1 s later (cap-save F23941)"""
    t0, r = time.time(), {}
    while time.time() - t0 < LIVE_S:
        r = F.q(host, {"cmd": "get_coop"})
        if r.get("coopSession") is True:
            return {"ok": True, "t": F.now(t0)}
        time.sleep(0.02)
    return {"ok": False, "t": F.now(t0), "coopSession": r.get("coopSession"), "error": r.get("error")}


def kk(host, i):
    return F.key(host, "host_%s_%s.data" % (i, NAME))


def buf(gc):
    r = F.q(gc, {"cmd": "get_coop"})
    return r.get("rxBufferBytes", r.get("error", "missing"))


def buffered(h):
    """READY: the host holds a half-sent upload (buf > 0); its first chunk lands a few ms after the 54 is first seen (cap-save F23943)"""
    b = buf(h)
    return isinstance(b, int) and b > 0


def own(gc):
    r = F.q(gc, {"cmd": "geo_state"})
    return {"own": [[b.get("name"), b.get("coopBaseId")] for b in r.get("bases", []) if not b.get("coopIcon")],
            "all": [[b.get("name"), b.get("coopBaseId"), b.get("coopIcon"), b.get("coopBase")] for b in r.get("bases", [])],
            "error": r.get("error")}


def alive(gc):
    return gc is not None and gc.proc is not None and gc.proc.poll() is None


def crash_line(p):
    """the first new crash file: its first line and the first line naming the exception"""
    try:
        ls = [ln for ln in open(p, encoding="utf-8", errors="replace").read().splitlines() if ln.strip()]
    except OSError as e:
        return {"error": repr(e)[:200]}
    ex = [ln for ln in ls if "exception" in ln.lower()]
    return {"file": os.path.basename(p), "first": ls[0][:120] if ls else "", "exception": ex[0][-240:] if ex else ""}


def capture(x):
    """every live machine's probes and log tail (the FIXTURE-STOP dump)"""
    out = {}
    for gc in x.procs():
        if alive(gc):
            w = F.q(gc, {"cmd": "list_widgets"})
            out[gc.name] = {"get_state": F.q(gc, {"cmd": "get_state"}), "get_coop": F.q(gc, {"cmd": "get_coop"}), "dialog": F.dlg(gc),
                            "widgets": [w.get("state")] + [[v.get("text"), v.get("visible"), v.get("hidden")] for v in w.get("widgets", [])
                                                           if v.get("text")], "log": F.lines_since(gc, 0)[-15:]}
        else:
            out[gc.name] = {"alive": False, "rc": gc.proc.poll() if gc.proc else None}
    return out


class X:
    def __init__(self):
        self.t0 = time.time()
        self.host = GameClient("host", None, make_user_dir("w2h58b_host"))
        self.client = GameClient("client", None, make_user_dir("w2h58b_client"))
        self.c2 = self.c3 = None
        self.fails, self.dead, self.cb, self.crash0 = [], None, None, set()

    def procs(self):
        return [g for g in (self.host, self.client, self.c2, self.c3) if g is not None]

    def rejoiner(self, n):
        return GameClient("client%d" % n, None, make_user_dir("w2h58b_client%d" % n))


class Row:
    def __init__(self, x, rid):
        self.x, self.rid, self.res = x, rid, {}
        self.ev = {"t": F.now(x.t0), "cpu": F.cpu()}
        self.n0 = len(F.logl(x.host))

    def cell(self, cid, ok, label):
        self.res[cid] = (bool(ok), label)

    def need(self, ok, what):
        if not ok:
            raise Stop(what)

    def finish(self, stop=None, reached=True):
        self.ev["tEnd"] = F.now(self.x.t0)
        self.ev["hostLog"] = F.lines_since(self.x.host, self.n0)[-30:]
        if stop:
            self.ev["stop"] = stop
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        fails = []
        for cid in dict(ROWS)[self.rid]:
            kind = "RED" if cid in RED else "GUARD"
            ok, label = self.res.get(cid, (False, "not reached (%s)" % stop))
            print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label), flush=True)
            if not ok:
                fails.append(cid)
        if stop and reached:
            print("CAPTURE %s: %s" % (self.rid, js(capture(self.x))), flush=True)
            self.x.dead = "row %s stopped: %s" % (self.rid, stop)
        print(("PASS %s" % self.rid) if not fails else ("FAIL %s: %s" % (self.rid, " ".join(fails))), flush=True)
        self.x.fails += fails


def world(x, rj, ow):
    return ("BuildNewBaseState %s; [GeoscapeState, CoopState] code 68 at %s s; own %s (want %s)"
            % ("never" if rj["buildNewBase"] is None else "at %s s" % rj["buildNewBase"], rj["t68"], ow["own"], list(x.cb)))


def world_ok(x, rj, ow):
    return rj["buildNewBase"] is None and rj["t68"] is not None and list(x.cb) in ow["own"]


def row_c0(x, r):
    r.ev["ownHost"] = own(x.host)
    r.ev["ownClient"] = oc = own(x.client)
    r.need(len(oc["own"]) == 1, "the client's own base not read from geo_state: %s" % oc)
    x.cb = tuple(oc["own"][0])  # (CB_NAME, CB), read at run time (S25)
    x.id0 = r.ev["id0"] = F.sid(x.host)
    r.ev["buf"] = buf(x.host)
    r.ev["blob0"] = b = kk(x.host, x.id0)
    r.cell("C0-blob", b.get("present") is True and (b.get("bytes") or 0) > 0, "key(id0 %s) %s" % (x.id0, kstr(b)))


def row_cb(x, r):
    r.ev["save1"] = s = F.quick_save(x.host, F.QUICK, SAVE_S)
    x.id1 = r.ev["id1"] = F.sid(x.host)
    r.ev["key1"] = k1 = kk(x.host, x.id1)
    r.cell("CB-write1", s["ok"] and k1.get("present") is True, "quick save ok %s (54 seen %s, written %s); id0 %s -> id1 %s; key(id1) %s"
           % (s["ok"], s["seen54"], s["written"], x.id0, x.id1, kstr(k1)))
    x.client.proc.kill()
    r.ev["kill"] = {"t": F.now(x.t0), "rc": x.client.proc.wait(timeout=15)}
    r.ev["w62"] = w = F.wait_62(x.host, DROP_S)
    r.need(w["ok"], "no host 62 within %.0f s of the kill" % DROP_S)
    x.c2 = x.rejoiner(2)
    r.ev["rejoin"] = rj = F.rejoin(x.host, x.c2, K1, NAME, JOIN_S, ACK_S, at_join=lambda h: {"buf": buf(h), "id1": kk(h, x.id1)})
    r.ev["own2"] = ow = own(x.c2)
    r.cell("CB-world", world_ok(x, rj, ow), "client2: " + world(x, rj, ow))
    r.need(rj["ack"] is not None, "no host 62 with resumeAck true within %.0f s of join_tcp" % (JOIN_S + ACK_S))
    r.ev["resume"] = rc = F.resume_and_clear(x.host)
    r.need(rc["ok"], "RESUME / host GeoscapeState within 5 s: %s" % js(rc.get("end")))
    r.ev["bufAfterResume"] = b0 = buf(x.host)
    r.cell("CB-buf0", b0 == 0, "buf(host) after RESUME %s" % b0)
    r.ev["live2"] = lv = live(x.host)
    r.need(lv["ok"], "the host's session not live (get_coop coopSession) within %.0f s of RESUME: %s" % (LIVE_S, js(lv)))
    crash2, tq2 = F.crashes(), time.time_ns()
    r.ev["save2"] = s2 = F.quick_save(x.host, F.QUICK, SAVE_S)
    x.id2 = r.ev["id2"] = F.sid(x.host)
    r.ev["key2"] = k2 = kk(x.host, x.id2)
    new = sorted(F.crashes() - crash2)
    q2 = s2["filesAfter"].get(F.QUICK)
    after = bool(q2 and q2[1] > tq2)
    r.cell("CB-write2", s2["ok"] and after and k2.get("present") is True and not new,
           "quick save ok %s (54 seen %s, written %s, mtime after the trigger %s); id1 %s -> id2 %s; key(id2) %s; new crash files %d"
           % (s2["ok"], s2["seen54"], s2["written"], after, x.id1, x.id2, kstr(k2), len(new)))
    r.ev["bufAfterSave2"] = buf(x.host)


def window(x, t3, crash3):
    """M1's save window (QH58-B2 (a), R-H58-B-1): until the save landed, or 1 s after the first new crash file, or SAVE2_S"""
    w, t3ns = {"trail": [], "tCrash": None, "tDone": None}, int(t3 * 1e9)
    while time.time() - t3 < SAVE2_S:
        cp = F.coop(x.host)
        i3 = cp.get("saveID")
        kn = kk(x.host, i3) if isinstance(i3, int) else {}
        s = {"hostStack": F.stk(x.host), "code": F.dlg(x.host).get("code"), "onConnect": cp.get("onConnect"),
             "pend": cp.get("pendingHostSaveName"), "quick": F.files(x.host).get(F.QUICK), "newCrash": len(F.crashes() - crash3),
             "c3": F.top(x.c3), "saveID": i3, "key": [kn.get("present"), kn.get("fnv1a64")]}
        if not w["trail"] or {k: v for k, v in w["trail"][-1].items() if k != "t"} != s:
            w["trail"].append(dict(s, t=F.now(t3)))
        if s["quick"] and s["quick"][1] > t3ns and s["pend"] == "" and s["hostStack"][-1:] == ["GeoscapeState"]:
            w["tDone"] = F.now(t3)
            break
        if s["newCrash"] and w["tCrash"] is None:
            w["tCrash"] = F.now(t3)
        if w["tCrash"] is not None and time.time() - t3 >= w["tCrash"] + 1.0:
            break
        time.sleep(0.1)
    w["tEnd"] = F.now(t3)
    return w


def row_m1(x, r):
    def probe(h):
        return {"buf": buf(h), "saveID": F.sid(h), "id2": kk(h, x.id2)}
    tcall = time.time()
    r.ev["drop"] = d = F.drop_at_54(x.host, x.c2, "auto_geoscape", SUSPEND_DELAY_MS, probe, SEEN_S, DROP_S, buffered, READY_S)
    tret = time.time()
    r.need("probe" in d, d.get("why"))
    p = d["probe"]
    b54, k2at54 = p["buf"], p["id2"]
    r.need(isinstance(b54, int) and b54 > 0, "no half-sent upload buffered at the 54: b54 %s" % b54)
    r.need(p["saveID"] == x.id2, "at the 54 saveID %s != id2 %s" % (p["saveID"], x.id2))
    r.need(d["ok"], d.get("why"))
    tkill = tret - d["after62"]["t"]  # the kill came just before wait_62 started
    r.ev["tKillAfterCall"] = round(tkill - tcall, 3)
    time.sleep(max(0.0, tkill + DROP_READ_S - time.time()))
    r.ev["b1"] = b1 = {"t": round(time.time() - tkill, 3), "buf": buf(x.host), "hostStack": F.stk(x.host), "dialog": F.dlg(x.host)}
    r.cell("M1-buf", b1["buf"] == 0, "b54 %s at the 54 (saveID %s == id2); b1 %s at %s s after the kill" % (b54, p["saveID"], b1["buf"], b1["t"]))
    x.c3 = x.rejoiner(3)
    r.ev["rejoin"] = rj = F.rejoin(x.host, x.c3, K1, NAME, JOIN_S, ACK_S, at_join=lambda h: {"buf": buf(h), "id2": kk(h, x.id2)})
    r.need(rj["join_tcp"].get("ok"), "client3 join_tcp failed: %s" % rj["join_tcp"])
    r.ev["own3"] = ow = own(x.c3)
    r.cell("M1-world", world_ok(x, rj, ow), "client3: " + world(x, rj, ow))
    r.need(rj["ack"] is not None, "no host 62 with resumeAck true within %.0f s of join_tcp" % (JOIN_S + ACK_S))
    r.ev["resume"] = rc = F.resume_and_clear(x.host)
    r.need(rc["ok"], "RESUME (+ CANCEL of a stale 54) / host GeoscapeState within 5 s: %s" % js(rc.get("end")))
    r.ev["bufAfterResume"] = buf(x.host)
    pre =sorted(F.crashes() - x.crash0)
    r.cell("PRE-CRASH", not pre, "crash files new since the boot start at t3: %d %s" % (len(pre), [os.path.basename(f) for f in pre[:3]]))
    r.ev["live3"] = lv = live(x.host)
    r.need(lv["ok"], "the host's session not live (get_coop coopSession) within %.0f s of RESUME: %s" % (LIVE_S, js(lv)))
    crash3, t3 = F.crashes(), time.time()
    r.ev["t3"] = F.now(x.t0)
    r.ev["trigger"] = F.q(x.host, {"cmd": "save_game_ui", "type": "quick"})
    r.ev["window"] = w = window(x, t3, crash3)
    cp = F.q(x.host, {"cmd": "get_coop"})
    id3, st = cp.get("saveID"), F.stk(x.host)
    k3, quick, new = kk(x.host, id3), F.files(x.host).get(F.QUICK), sorted(F.crashes() - crash3)
    r.ev["end"] = e = {"hostStack": st, "dialog": F.dlg(x.host), "onConnect": cp.get("onConnect"), "pend": cp.get("pendingHostSaveName"),
                       "buf": cp.get("rxBufferBytes"), "id2": x.id2, "id3": id3, "key3": k3, "key2": kk(x.host, x.id2), "quick": quick,
                       "newCrash": len(new), "firstCrash": crash_line(new[0]) if new else None, "c3Stack": F.stk(x.c3),
                       "c3Dialog": F.dlg(x.c3)}
    written = bool(quick and quick[1] > int(t3 * 1e9))
    r.cell("M1-write", written, "_quick_.asav %s (t3 %d ns): written after t3 %s; window done %s, first crash %s, end %s s"
           % (quick, int(t3 * 1e9), written, w["tDone"], w["tCrash"], w["tEnd"]))
    r.cell("M1-crash", not new, "crash files new since t3 at the window end: %d; first %s" % (len(new), js(e["firstCrash"])))
    r.cell("M1-host", st == ["GeoscapeState"] and cp.get("onConnect") == 1, "host stack %s dialog %s onConnect %s pending %r"
           % (st, js(e["dialog"]), cp.get("onConnect"), cp.get("pendingHostSaveName")))
    fn = [t["key"][1] for t in w["trail"]]
    r.cell("M1-key", k3.get("present") is True and k3.get("fnv1a64") != k2at54.get("fnv1a64"),
           "id2 %s -> id3 %s; key(id2) at the 54 %s; key(id3) at the window end %s; key(id3) fnv at each read %s"
           % (x.id2, id3, kstr(k2at54), kstr(k3), fn))


def boot(x):
    ev = {"cpu": F.cpu()}
    try:
        x.host.spawn()
        x.host.connect()
        x.client.spawn()
        x.client.connect()
        session.new_campaign(x.host, x.client, port=K1)
        ev["tCampaign"] = F.now(x.t0)
        ev["stable"] = F.stable_geo(x.host, x.client, STABLE_S, 90.0)
        ok = ev["stable"]["ok"]
    except Exception as e:  # noqa: BLE001 - a boot that raises is a boot miss
        ev["error"], ok = ("%s: %s" % (type(e).__name__, e))[:400], False
    print("EVIDENCE boot: %s" % js(ev), flush=True)
    if not ok:
        print("CAPTURE boot: %s" % js(capture(x)), flush=True)
        for _rid, cells in ROWS:
            for cid in cells:
                print("FAIL %s %s: boot" % (cid, "RED" if cid in RED else "GUARD"), flush=True)
                x.fails.append(cid)
    return ok


def main():
    x = X()
    x.crash0 = F.crashes()
    try:
        if boot(x):
            for rid, fn in (("C0", row_c0), ("CB", row_cb), ("M1", row_m1)):
                r = Row(x, rid)
                if x.dead:
                    r.finish(x.dead, reached=False)
                    continue
                try:
                    fn(x, r)
                    r.finish()
                except Stop as e:
                    r.finish(str(e))
                except Exception as e:  # noqa: BLE001 - an unexpected exception ends the row like a precondition miss
                    r.finish("exception %s: %s" % (type(e).__name__, str(e)[:300]))
    finally:
        for gc in x.procs()[::-1]:  # right after the window: a red host is in the crash-log loop
            try:
                if alive(gc):
                    F.resume(gc)  # harmless when not suspended
                    gc.shutdown(expected_returncodes=OKRC)
            except Exception as e:  # noqa: BLE001
                print("FAIL shutdown %s: %s" % (gc.name, str(e)[:300]), flush=True)
    new = sorted(F.crashes() - x.crash0)
    print("EVIDENCE crash census after shutdown: %d new crash files, %d .dmp" % (len(new), len([p for p in new if p.endswith(".dmp")])),
          flush=True)
    wall = F.now(x.t0)
    cells = [c for _r, cs in ROWS for c in cs]
    print("SUMMARY W2-H58 S-B HSR: %d/%d cells pass; failing %s; wall %.1f s" % (len(cells) - len(set(x.fails)), len(cells),
                                                                               sorted(set(x.fails)) or "none", wall), flush=True)
    return 0 if not x.fails else 2


if __name__ == "__main__":
    sys.exit(main())
