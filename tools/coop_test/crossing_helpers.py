"""Helpers for the upload / save crossing tests (test_upload_save_crossing.py, test_upload_save_crossing_heal.py), imported as CH.
A partner's unasked upload (here its push after the host gifts it a soldier) carries the saveID the partner had when the stream
started, and a host quick save inside that stream re-mints the host's id. The host's check of the upload (a scratch load) must keep
the host's newer id: moving it to the upload's older one while the world is stored under the newer key makes a drop + rejoin start a
new campaign.
crossing() holds the CROSSING (first_save, arm_ack_hold, GIFT, PUSH, HELD, arm_reply_hold, crossing_save, REPLY, release_ack_hold, save_done, read after_save, release_reply_hold, store_done, HOLD 1 s,
read after_store) on the test-only hooks hold_blob_ack scope "upload" (the host withholds every world chunk's ack while armed, so the push parks
after its first chunk before the save starts) and hold_save_reply (the host keeps its go-ahead to the partner's save answer, so the
host is readable between the two checks); both are released in a finally (hooks_off). Reads: kept_id_count (the "[coop] partner
upload validated" count), blobs ({id: host_<id>_<NAME>.data}), world_copy (the "[coop] N partner world(s) copied" line). Every step is
recorded in r.ev["crossing"]; a precondition miss fails the row's -pre cell and raises RH.Stop (later cells "not reached"). Uses
drop_fixture (F) and rejoin_helpers (RH). Never a base placement, never the 54's CANCEL (only F resume_and_clear after an ack CANCELs
a stale 54). Polls 0.05 s. ONE foreground run per test file, no SKIP; exit 0 only when every cell passes, else 2."""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drop_fixture as F  # noqa: E402
import rejoin_helpers as RH  # noqa: E402

W_HELD, W_REPLY, W_RESULT, HOLD_X = 10.0, 10.0, 15.0, 1.0
NEEDLE = "[coop] partner upload validated - saveID stays"
WORLD_COPY_RE = re.compile(r"\[coop\] (\d+) partner world\(s\) copied from saveID (\d+) to (\d+)")


def kept_id_count(gc, n0=0):
    """the count of "[coop] partner upload validated" lines in the machine's log from line n0 (0 on a build without the fix)"""
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


def hooks_off(host):
    """hold_blob_ack {on: false} and hold_save_reply {on: false}, each only when armed"""
    out = {}
    if RH.alive(host):
        if hold(host).get("armed"):
            out["hold_blob_ack"] = hold(host, on=False)
        if reply(host).get("armed"):
            out["hold_save_reply"] = reply(host, on=False)
    return out


def world_copy(lines):
    """the last "partner world(s) copied" line's (N copied, from saveID, to saveID), or None"""
    m = [x for x in (WORLD_COPY_RE.search(ln) for ln in lines) if x]
    return tuple(int(g) for g in m[-1].groups()) if m else None


def world_copy_since(host, n0, secs=3.0):
    got = []
    RH.until(lambda: got.append(world_copy(F.lines_since(host, n0, ("partner world(s) copied",)))) or got[-1] is not None, time.time() + secs)
    return got[-1]


def newer(a, b):
    return bool(a and (not b or a[1] > b[1]))


def x_read(r, host, client, extra=()):
    hid = F.coop(host).get("saveID")
    return {"ids": RH.ids(host, client), "blobs": blobs(host, r.name, [r.id1, r.id2, hid] + list(extra)), "hostId": hid}


def crossing(r, host, client):
    """the CROSSING; returns r.ev["crossing"] (with "lab") when every step met; a miss fails the -pre cell and raises RH.Stop"""
    ev = r.ev.setdefault("crossing", {})
    try:
        _crossing(r, host, client, ev)
    finally:
        ev["hooksOff"] = hooks_off(host)
    return ev


def _miss(r, ev, step, why):
    ev["miss"] = [step, why]
    r.cell(r.rid + "-pre", False, "%s: %s" % (step, why))
    raise RH.Stop("%s: %s" % (step, why))


def _crossing(r, host, client, ev):
    s1 = F.quick_save(host, F.QUICK, RH.SAVE_S)
    r.id0, r.id1 = r.ev["marker"]["id0"], s1.get("saveIDAfter")
    ev["first_save"] = RH.pick(s1, ("ok", "seen54", "written", "t", "saveIDBefore", "saveIDAfter", "log"))
    if not (s1["ok"] and r.id1 != r.id0):
        _miss(r, ev, "first_save", "ok %s, id0 %s, id1 %s" % (s1["ok"], r.id0, r.id1))
    time.sleep(RH.HOLD)
    ev["arm_ack_hold"] = a = hold(host, on=True, scope="upload")
    if not (a.get("armed") is True and a.get("scope") == 3 and a.get("held") == 0):
        _miss(r, ev, "arm_ack_hold", RH.js(a))
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
    ev["arm_reply_hold"] = b = reply(host, on=True)
    if not (b.get("armed") is True and b.get("held") is False):
        _miss(r, ev, "arm_reply_hold", RH.js(b))
    q0, n2, t2 = F.files(host).get(F.QUICK), len(F.logl(host)), time.time()
    r.n2 = n2
    trig = F.q(host, {"cmd": "save_game_ui", "type": "quick"})
    t54 = RH.until(lambda: F.dlg(host).get("code") == 54, t2 + RH.SEEN_S)
    r.id2 = F.sid(host)
    h = world_copy_since(host, n2)
    ev["crossing_save"] = {"trigger": trig.get("ok"), "t54": None if t54 is None else round(t54 - t2, 2), "id2": r.id2, "world_copy": h}
    if t54 is None or r.id2 == r.id1 or h != (1, r.id1, r.id2):
        _miss(r, ev, "crossing_save", "54 at %s s, id1 %s, id2 %s, world copy %s" % (ev["crossing_save"]["t54"], r.id1, r.id2, h))
    tr = RH.until(lambda: reply(host).get("held") is True, time.time() + W_REPLY)
    ev["REPLY"] = {"t": None if tr is None else round(tr - t2, 2), "idsRead": RH.ids(host, client), "hostDlg": F.dlg(host).get("code")}
    if tr is None or ev["REPLY"]["idsRead"]["client"] != [r.id2, r.id2]:
        _miss(r, ev, "REPLY", "held at %s s; read idsRead %s (id2 %s)" % (ev["REPLY"]["t"], ev["REPLY"]["idsRead"], r.id2))
    ev["release_ack_hold"] = ra = hold(host, on=False)
    if ra.get("sent") is not True:
        _miss(r, ev, "release_ack_hold", RH.js(ra))
    ta = time.time()
    t1 = RH.until(lambda: F.dlg(host).get("code") != 54 and F.coop(host).get("pendingHostSaveName") == ""
                  and newer(F.files(host).get(F.QUICK), q0), ta + W_RESULT)
    ev["save_done"] = {"t": None if t1 is None else round(t1 - ta, 2), "top": F.top(host), "dlg": F.dlg(host).get("code")}
    if t1 is None:
        _miss(r, ev, "save_done", "54 / pending / QUICK not done within %.0f s: %s" % (W_RESULT, RH.js(F.coop(host))))
    x1 = x_read(r, host, client)
    x1.update(keptCount=kept_id_count(host, n2), sav=RH.parse_sav(os.path.join(host.user_dir, "xcom1", F.QUICK)))
    ev["after_save"] = x1
    ev["release_reply_hold"] = rb = reply(host, on=False)
    if rb.get("sent") is not True:
        _miss(r, ev, "release_reply_hold", RH.js(rb))
    tb, s0 = time.time(), sig(blobs(host, r.name, [r.id1, r.id2]))
    t5 = RH.until(lambda: sig(blobs(host, r.name, [r.id1, r.id2])) != s0, tb + W_RESULT)
    s5 = sig(blobs(host, r.name, [r.id1, r.id2]))
    ev["store_done"] = {"t": None if t5 is None else round(t5 - tb, 2), "blobs": s5}
    if t5 is None:
        _miss(r, ev, "store_done", "the host's store unchanged within %.0f s: %s" % (W_RESULT, RH.js(s0)))
    time.sleep(HOLD_X)
    ev["after_store"] = x2 = x_read(r, host, client)
    x2["quiet"] = sig(blobs(host, r.name, [r.id1, r.id2])) == s5
    ev["lab"] = ("first_save id1 %s; arm_ack_hold scope 3; gifted %s; push %s; HELD %s (rx %s) at %s s; crossing_save 54 at %s s, id2 %s, world copy %s; REPLY at %s s, idsRead %s; "
                 "release_ack_hold sent; save_done at %s s; release_reply_hold sent; store_done at %s s" % (
                     r.id1, r.gifted, pk, got.get("held"), got.get("rx"), ev["HELD"]["t"], ev["crossing_save"]["t54"], r.id2, h, ev["REPLY"]["t"],
                     ev["REPLY"]["idsRead"], ev["save_done"]["t"], ev["store_done"]["t"]))
