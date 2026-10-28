"""W2-H86 helpers (tools/coop_test/crossing_helpers.py, "CH"), imported by test_upload_save_crossing.py (UXC: rows U1, CTL) and
test_upload_save_crossing_heal.py (UXH: rows U2, U2D). Spec docs rewrite/prompts/w2h86_upload_save_crossing.md (f); TASK 0 values in
rewrite/w2h86-task0/sa/CONSTANTS.md. Lead L-LT17-1, ruling R-LLT17-1-1 (VL-H86-1, VL-H86-2): a partner's unasked upload (here its push
after the host gifts it a soldier) carries the saveID the partner had when the stream started; a host quick save inside that stream
re-mints the host's id, and the host's check of the upload (a scratch load) then moved the host's id to the upload's older one while the
world was stored under the newer key, so a drop + rejoin got a new campaign.
Holds the CROSSING (S1, ARM-A, GIFT, PUSH, HELD, ARM-B, S2, REPLY, REL-A, RESULT1, read X1, REL-B, RESULT2, HOLD 1 s, read X2) on the
TEST-ONLY levers hold_blob_ack scope "upload" (W2-H86 L1: the host withholds every world chunk's ack while armed, so the push parks after
its first chunk before the save starts) and hold_save_reply (W2-H82 L3: the host keeps its go-ahead to the partner's save answer, so the
host is readable between the two checks); both released in a finally (levers_off). Reads: kept_id_count (the "[coop] W2-H86:" count), blobs
({id: host_<id>_<NAME>.data}), w58 (the W2-H58 copy line). Every step is recorded in r.ev["X"]; a precondition miss fails the row's -pre
cell and raises RH.Stop (later cells "not reached"). Imports drop_fixture (F) and rejoin_helpers (RH) unchanged. Never a base
placement, never the 54's CANCEL (only F resume_and_clear after an ack CANCELs a stale 54). Polls 0.05 s.
WV-D95 / WV-D99 / WV-D100: ONE foreground run per test file, no SKIP; exit 0 only when every cell passes, else 2."""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drop_fixture as F  # noqa: E402
import rejoin_helpers as RH  # noqa: E402

W_HELD, W_REPLY, W_RESULT, HOLD_X = 10.0, 10.0, 15.0, 1.0
NEEDLE = "[coop] W2-H86:"
H58 = re.compile(r"\[coop\] W2-H58: (\d+) partner world\(s\) copied from saveID (\d+) to (\d+)")


def kept_id_count(gc, n0=0):
    """the count of "[coop] W2-H86:" lines in the machine's log from line n0 (0 on a build without the fix)"""
    return sum(1 for ln in F.logl(gc)[n0:] if NEEDLE in ln)


def blobs(host, name, ids_):
    """{str(id): the host's coop_file_info of host_<id>_<NAME>.data} for every non-empty id given"""
    return {str(i): RH.kk(host, i, name) for i in dict.fromkeys(ids_) if i}


def sig(b):
    return {k: [v.get("present"), v.get("fnv1a64")] for k, v in b.items()}


def hold(host, **kw):
    return RH.pick(F.q(host, dict({"cmd": "hold_blob_ack"}, **kw)), ("ok", "armed", "held", "scope", "sent", "error"))


def reply(host, **kw):
    return RH.pick(F.q(host, dict({"cmd": "hold_save_reply"}, **kw)), ("ok", "armed", "held", "sent", "error"))


def levers_off(host):
    """hold_blob_ack {on: false} and hold_save_reply {on: false}, each only when armed"""
    out = {}
    if RH.alive(host):
        if hold(host).get("armed"):
            out["hold_blob_ack"] = hold(host, on=False)
        if reply(host).get("armed"):
            out["hold_save_reply"] = reply(host, on=False)
    return out


def w58(lines):
    """the last W2-H58 line's (N copied, from saveID, to saveID), or None"""
    m = [x for x in (H58.search(ln) for ln in lines) if x]
    return tuple(int(g) for g in m[-1].groups()) if m else None


def world_copy_since(host, n0, secs=3.0):
    got = []
    RH.until(lambda: got.append(w58(F.lines_since(host, n0, ("W2-H58",)))) or got[-1] is not None, time.time() + secs)
    return got[-1]


def newer(a, b):
    return bool(a and (not b or a[1] > b[1]))


def x_read(r, host, client, extra=()):
    hid = F.coop(host).get("saveID")
    return {"ids": RH.ids(host, client), "blobs": blobs(host, r.name, [r.id1, r.id2, hid] + list(extra)), "hostId": hid}


def crossing(r, host, client):
    """the CROSSING; returns r.ev["X"] (with "lab") when every step met; a miss fails the -pre cell and raises RH.Stop"""
    ev = r.ev.setdefault("X", {})
    try:
        _crossing(r, host, client, ev)
    finally:
        ev["leversOff"] = levers_off(host)
    return ev


def _miss(r, ev, step, why):
    ev["miss"] = [step, why]
    r.cell(r.rid + "-pre", False, "%s: %s" % (step, why))
    raise RH.Stop("%s: %s" % (step, why))


def _crossing(r, host, client, ev):
    s1 = F.quick_save(host, F.QUICK, RH.SAVE_S)
    r.id0, r.id1 = r.ev["marker"]["id0"], s1.get("saveIDAfter")
    ev["S1"] = RH.pick(s1, ("ok", "seen54", "written", "t", "saveIDBefore", "saveIDAfter", "log"))
    if not (s1["ok"] and r.id1 != r.id0):
        _miss(r, ev, "S1", "ok %s, id0 %s, id1 %s" % (s1["ok"], r.id0, r.id1))
    time.sleep(RH.HOLD)
    ev["ARM-A"] = a = hold(host, on=True, scope="upload")
    if not (a.get("armed") is True and a.get("scope") == 3 and a.get("held") == 0):
        _miss(r, ev, "ARM-A", RH.js(a))
    n0, nh = len(F.logl(client)), len(F.logl(host))
    g = RH.gift(host, client, r.aff)
    r.gifted = (g.get("gifted") or [None])[0]
    ev["GIFT"] = RH.pick(g, ("ok", "stop", "tRecv", "gifted", "hostTop", "button"))
    if not (g["ok"] and len(g.get("gifted") or []) == 1 and g.get("hostTop") == "GeoscapeState"):
        _miss(r, ev, "GIFT", RH.js(ev["GIFT"]))
    w = RH.wait_log(client, n0, RH.PUSH, RH.W_PUSH)
    pk = w["line"].split(RH.PUSH, 1)[1].rstrip(")") if w.get("line") else None
    ev["PUSH"] = dict(w, key=pk)
    if pk != "client_%s_%s.data" % (r.id1, r.name):
        _miss(r, ev, "PUSH", "push key %s (id1 %s, NAME %s)" % (pk, r.id1, r.name))
    got, t0 = {}, time.time()
    th = RH.until(lambda: got.update(hold(host), rx=F.q(host, {"cmd": "get_coop"}).get("rxBufferBytes")) or
                  ((got.get("held") or 0) >= 1 and (got.get("rx") or 0) > 0), t0 + W_HELD)
    ev["HELD"] = dict(got, t=None if th is None else round(th - t0, 2), log=F.lines_since(host, nh, ("hold_blob_ack",))[-3:])
    if th is None:
        _miss(r, ev, "HELD", "held %s, rxBufferBytes %s within %.0f s" % (got.get("held"), got.get("rx"), W_HELD))
    ev["ARM-B"] = b = reply(host, on=True)
    if not (b.get("armed") is True and b.get("held") is False):
        _miss(r, ev, "ARM-B", RH.js(b))
    q0, n2, t2 = F.files(host).get(F.QUICK), len(F.logl(host)), time.time()
    r.n2 = n2
    trig = F.q(host, {"cmd": "save_game_ui", "type": "quick"})
    t54 = RH.until(lambda: F.dlg(host).get("code") == 54, t2 + RH.SEEN_S)
    r.id2 = F.sid(host)
    h = world_copy_since(host, n2)
    ev["S2"] = {"trigger": trig.get("ok"), "t54": None if t54 is None else round(t54 - t2, 2), "id2": r.id2, "w58": h}
    if t54 is None or r.id2 == r.id1 or h != (1, r.id1, r.id2):
        _miss(r, ev, "S2", "54 at %s s, id1 %s, id2 %s, W2-H58 %s" % (ev["S2"]["t54"], r.id1, r.id2, h))
    tr = RH.until(lambda: reply(host).get("held") is True, time.time() + W_REPLY)
    ev["REPLY"] = {"t": None if tr is None else round(tr - t2, 2), "P": RH.ids(host, client), "hostDlg": F.dlg(host).get("code")}
    if tr is None or ev["REPLY"]["P"]["client"] != [r.id2, r.id2]:
        _miss(r, ev, "REPLY", "held at %s s; read P %s (id2 %s)" % (ev["REPLY"]["t"], ev["REPLY"]["P"], r.id2))
    ev["REL-A"] = ra = hold(host, on=False)
    if ra.get("sent") is not True:
        _miss(r, ev, "REL-A", RH.js(ra))
    ta = time.time()
    t1 = RH.until(lambda: F.dlg(host).get("code") != 54 and F.coop(host).get("pendingHostSaveName") == ""
                  and newer(F.files(host).get(F.QUICK), q0), ta + W_RESULT)
    ev["RESULT1"] = {"t": None if t1 is None else round(t1 - ta, 2), "top": F.top(host), "dlg": F.dlg(host).get("code")}
    if t1 is None:
        _miss(r, ev, "RESULT1", "54 / pending / QUICK not done within %.0f s: %s" % (W_RESULT, RH.js(F.coop(host))))
    x1 = x_read(r, host, client)
    x1.update(h86=kept_id_count(host, n2), sav=RH.parse_sav(os.path.join(host.user_dir, "xcom1", F.QUICK)))
    ev["X1"] = x1
    ev["REL-B"] = rb = reply(host, on=False)
    if rb.get("sent") is not True:
        _miss(r, ev, "REL-B", RH.js(rb))
    tb, s0 = time.time(), sig(blobs(host, r.name, [r.id1, r.id2]))
    t5 = RH.until(lambda: sig(blobs(host, r.name, [r.id1, r.id2])) != s0, tb + W_RESULT)
    s5 = sig(blobs(host, r.name, [r.id1, r.id2]))
    ev["RESULT2"] = {"t": None if t5 is None else round(t5 - tb, 2), "blobs": s5}
    if t5 is None:
        _miss(r, ev, "RESULT2", "the host's store unchanged within %.0f s: %s" % (W_RESULT, RH.js(s0)))
    time.sleep(HOLD_X)
    ev["X2"] = x2 = x_read(r, host, client)
    x2["quiet"] = sig(blobs(host, r.name, [r.id1, r.id2])) == s5
    ev["lab"] = ("S1 id1 %s; ARM-A scope 3; gifted %s; push %s; HELD %s (rx %s) at %s s; S2 54 at %s s, id2 %s, W2-H58 %s; REPLY at %s s, P %s; "
                 "REL-A sent; RESULT1 at %s s; REL-B sent; RESULT2 at %s s" % (
                     r.id1, r.gifted, pk, got.get("held"), got.get("rx"), ev["HELD"]["t"], ev["S2"]["t54"], r.id2, h, ev["REPLY"]["t"],
                     ev["REPLY"]["P"], ev["RESULT1"]["t"], ev["RESULT2"]["t"]))
