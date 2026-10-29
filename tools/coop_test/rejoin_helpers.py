"""Helpers of the rejoin tests, imported by test_rejoin_after_push.py (rows upload_rejoin, control), test_rejoin_after_push_save.py
(rows drop_next_save, resumed_save) and the upload-save crossing tests. Without the saveID fix, a partner's rejoin or resume onto a
stored world whose saveID is older than the host's (the host's copy after a drop during a host save; a resumed save's embed) takes that
older id, so its next upload moves the host's id back and a second rejoin gets a new campaign. Holds boot / shut, the gift by the host's
real presses and parse_sav (the gift steps follow test_hold_until_named.py; nothing is imported from it), the reads (own, ownsold,
kept, ids, kk), the common steps and the row runner. Imports drop_fixture (F), session, geo and harness unchanged. Never a base
placement, dismiss_popup or coop_dialog_back: a fresh world is evidence. ONE foreground run per file, no SKIP."""
import base64
import json
import os
import sys
import time
from functools import reduce

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import drop_fixture as F  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
GIFT_ROW, GIVE_KEY, SETTLE_MENU = (68, 44), 258, 1.0   # SoldiersState row 0 / Options::giveUnit (SDLK_KP2) / test_hold_until_named's menu settle
STABLE_S, BOOT_S, SAVE_S, SEEN_S, DROP_S, JOIN_S, ACK_S = 5.0, 90.0, 20.0, 10.0, 5.0, 10.0, 30.0
GIFT_S, W_PUSH, W_STORE, HOLD, HOLD_R = 10.0, 10.0, 10.0, 2.0, 3.0
PUSH, KEPT = "[coop-gift] pushed client progress to host (", '[coop] own world "'

class Stop(Exception):
    """a precondition missed: the row ends here"""

def js(v):
    return json.dumps(v, sort_keys=True, default=str)

def alive(gc):
    return gc is not None and gc.proc is not None and gc.proc.poll() is None

def pick(d, ks):
    return {k: d.get(k) for k in ks}

def cw(gc, match, settle=1.0, ready=False):  # ----- the gift steps, from here to wait_fnv_change -----
    if ready:
        session.wait_widget_ready(gc, match)
    r = F.q(gc, {"cmd": "click_widget", "match": match})
    time.sleep(settle)
    return {"match": match, "ok": r.get("ok"), "base": [r.get("baseX"), r.get("baseY")], "win": [r.get("winX"), r.get("winY")], "after": F.stk(gc)}

def affine(r1, r2):
    out = [(r1["win"][i] - r2["win"][i]) / (r1["base"][i] - r2["base"][i]) if r1["base"][i] != r2["base"][i] else None for i in (0, 1)]
    sc = round(out[0] or out[1], 3)
    return (sc, r1["win"][0] - sc * r1["base"][0], sc, r1["win"][1] - sc * r1["base"][1])

def key(gc, sym):
    return F.q(gc, {"cmd": "inject_input", "kind": "key", "key": sym})

def click_px(gc, bx, by, sc, until_not, offsets=((0, 0), (0, 1))):
    tries = []
    for dx, dy in offsets:
        F.q(gc, {"cmd": "inject_input", "kind": "click", "x": int(round(sc[0] * (bx + dx) + sc[1])), "y": int(round(sc[2] * (by + dy) + sc[3]))})
        until(lambda: F.top(gc) != until_not, time.time() + 1.0)
        tries.append(F.top(gc))
        if tries[-1] != until_not:
            break
    return tries

def until(pred, deadline, step=0.05):
    while not pred():
        if time.time() >= deadline:
            return None
        time.sleep(step)
    return time.time()

def first_after(gc, a, needle):
    return next((a + i for i, ln in enumerate(F.logl(gc)[a:]) if needle in ln), None)

def soldier_names(gc):
    r = F.q(gc, {"cmd": "get_soldiers"})
    return sorted(s.get("name") for b in r.get("bases", []) if not b.get("coopIcon") and not b.get("coopBaseFlag") for s in b.get("soldiers", []))

def host_affine(host):  # the host's INTERCEPT + CANCEL real clicks give the base -> window scale (measured 2.008)
    return affine(cw(host, "INTERCEPT", 0.6), cw(host, "CANCEL", 0.6, ready=True))

def gift(host, partner, aff):  # host: BASES, SOLDIERS, GIFT_ROW, GIVE_KEY, the partner's button; partner RECV within GIFT_S; host back to geoscape
    ev, s0 = {"ok": False}, soldier_names(host)
    ev["bases"] = cw(host, "BASES")["after"][-1:]
    ev["soldiers"] = cw(host, "SOLDIERS")["after"][-1:]
    ev["row"] = click_px(host, GIFT_ROW[0], GIFT_ROW[1], aff, "SoldiersState")
    if F.top(host) != "SoldierInfoState":
        return dict(ev, stop="host top %s after the GIFT_ROW click" % F.top(host))
    key(host, GIVE_KEY)
    if not until(lambda: F.top(host) == "GiftSoldierMenu", time.time() + 3.0):
        return dict(ev, stop="host top %s after GIVE_KEY" % F.top(host))
    time.sleep(SETTLE_MENU)
    ev["menu"] = w = [x.get("text") for x in F.q(host, {"cmd": "list_widgets"}).get("widgets", []) if x.get("text") and x.get("visible")]
    tgt = [x for x in w if x.upper() != "CANCEL" and not x.startswith("Gift ")]
    if not tgt:
        return dict(ev, stop="no partner button in GiftSoldierMenu %s" % w)
    m0, tg = len(F.logl(partner)), time.time()
    ev["button"] = cw(host, tgt[0], 0.0)["match"]
    tr = until(lambda: first_after(partner, m0, "[coop-gift] RECV added soldier") is not None, tg + GIFT_S, 0.1)
    ev["tRecv"] = round(tr - tg, 2) if tr else None
    if tr is None:
        return dict(ev, stop="partner log: no RECV added soldier within %.0f s" % GIFT_S)
    ev["gifted"] = sorted(set(s0) - set(soldier_names(host)))
    for lab in ("OK", "OK", "GEOSCAPE"):
        if F.top(host) != "GeoscapeState":
            cw(host, lab, 0.8)
    return dict(ev, hostTop=F.top(host), ok=True)

def partner_notice_ok(partner):
    seen = until(lambda: F.top(partner) == "GiftNoticeState", time.time() + 5.0, 0.1) is not None
    r = cw(partner, "OK") if seen else {"ok": False, "after": [F.top(partner)]}
    return {"ok": r.get("ok"), "after": r["after"][-2:]}

def wait_log(gc, n0, needle, secs):
    t0 = time.time()
    tt = until(lambda: first_after(gc, n0, needle) is not None, t0 + secs, 0.05)
    i = first_after(gc, n0, needle)
    return {"t": round(tt - t0, 2) if tt else None, "line": F.logl(gc)[i].split("\t")[-1][:300] if i is not None else None}

def wait_fnv_change(host, k, fnv0, secs):
    t0, got = time.time(), {}
    tt = until(lambda: got.update(F.key(host, k)) or got.get("fnv1a64") != fnv0, t0 + secs, 0.05)
    return {"t": round(tt - t0, 2) if tt else None, "key": dict(got)}

def parse_sav(path):  # the .sav's saveID and each coopClientSaves entry: key, bytes, fnv1a64, the blob's own saveID
    import yaml
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    out = {"bytes": os.path.getsize(path), "mtime_ns": os.stat(path).st_mtime_ns, "entries": []}
    with open(path, encoding="utf-8", errors="replace") as fh:
        docs = [d for d in yaml.load_all(fh.read(), Loader=loader) if isinstance(d, dict)]
    for d in docs:
        if "saveID" in d:
            out.setdefault("saveID", d["saveID"])
        for en in d.get("coopClientSaves") or []:
            raw = en.get("blob")
            b = base64.b64decode(raw) if isinstance(raw, str) else bytes(raw or b"")
            ws = [x for x in yaml.load_all(b.decode("utf-8", errors="replace"), Loader=loader) if isinstance(x, dict)]
            h = reduce(lambda a, ch: ((a ^ ch) * 1099511628211) % (1 << 64), b, 1469598103934665603)
            out["entries"].append({"key": en.get("key"), "bytes": len(b), "fnv1a64": "%016x" % h,
                                   "blobSaveID": next((x.get("saveID") for x in ws if "saveID" in x), None)})
    return out

def boot(tag, key_, saves=None, names=("host", "client")):  # BOOT: SEPARATE new_campaign (resume_campaign of QUICK with saves), slow clock, stable
    host = GameClient(names[0], None, make_user_dir(tag + "_host", saves=saves or ()))
    client = GameClient(names[1], None, make_user_dir(tag + "_client"))
    ev = {"cpu": F.cpu()}
    try:
        host.spawn(); host.connect(); client.spawn(); client.connect()  # noqa: E702
        (session.resume_campaign(host, client, F.QUICK, port=key_) if saves else session.new_campaign(host, client, port=key_))
        geo.slow_clock(host, client)
        ev["stable"] = F.stable_geo(host, client, STABLE_S, BOOT_S)
    except Exception as e:  # noqa: BLE001 - a boot that raises is a boot miss
        ev["error"] = ("%s: %s" % (type(e).__name__, e))[:400]
    return host, client, ev

def shut(gcs):
    out = []
    for gc in gcs[::-1]:
        try:
            if alive(gc):
                F.resume(gc)  # harmless when not suspended
                gc.shutdown(expected_returncodes=OKRC)
            out.append([gc.name, "shut" if gc.proc is gc._shutdown_proc else "rc %s" % gc.proc.poll()])
        except Exception as e:  # noqa: BLE001
            out.append([gc.name, "shutdown failed %s" % str(e)[:200]])
    return out

def own(gc):  # ----- reads ----- geo_state bases with coopIcon false as [name, coopBaseId]
    return [[b.get("name"), b.get("coopBaseId")] for b in F.q(gc, {"cmd": "geo_state"}).get("bases", []) if not b.get("coopIcon")]

ownsold = soldier_names  # the machine's own soldiers' names (soldier_names)

def kept(gc):  # the count of '[coop] own world "' lines in the machine's log (0 on a build without the fix)
    return sum(1 for ln in F.logl(gc) if KEPT in ln)

def ids(host, gc):  # [get_coop.saveID, save_markers.saveID] of both machines
    return {"host": [F.coop(host).get("saveID"), F.sid(host)], "client": [F.coop(gc).get("saveID"), F.sid(gc)]}

def kk(host, i, name):
    return F.key(host, "host_%s_%s.data" % (i, name))

def rejoiner(tag, n):  # a NEW GameClient on a fresh dir <tag>_client<n>
    return GameClient("client%d" % n, None, make_user_dir("%s_client%d" % (tag, n)))

def start(r, tag=None, saves=None, names=("host", "client")):  # BOOT (+ NAME, MARKER on a first boot), the click scale; a boot miss fails -pre
    host, client, ev = boot(tag or r.tag, r.key, saves, names)
    r.add(host, client)
    r.ev["boot2" if saves else "boot"] = ev
    if not (ev.get("stable") or {}).get("ok"):
        r.cell(r.rid + "-pre", False, "boot miss: %s" % js(ev)[:400])
        raise Stop("boot miss")
    if not saves:
        r.name = F.q(host, {"cmd": "get_coop"}).get("clientName") or "ClientPlayer"
        r.marker = (own(client), ownsold(client))
        r.ev["marker"] = {"name": r.name, "id0": F.sid(host), "own": r.marker[0], "ownsold": r.marker[1]}
    r.aff = host_affine(host)
    return host, client

def save_then_drop(r, host, client):  # first_save = a quick save with the client running (id1), HOLD; first_drop = the drop at the host's first 54 (id2)
    s1 = F.quick_save(host, F.QUICK, SAVE_S)
    r.id1 = s1.get("saveIDAfter")
    r.ev["first_save"] = pick(s1, ("ok", "seen54", "written", "t", "saveIDBefore", "saveIDAfter", "log"))
    time.sleep(HOLD)
    def probe(h):  # noqa: E306
        i2 = F.sid(h)
        return {"saveID": i2, "id1": kk(h, r.id1, r.name), "id2": kk(h, i2, r.name)}
    d1 = F.drop_at_54(host, client, "quick", 0, probe, SEEN_S, DROP_S)
    r.ev["first_drop"] = pick(d1, ("ok", "why", "seen54", "probe", "kill", "log", "filesBefore"))
    p = d1.get("probe") or {}
    r.id2 = p.get("saveID")
    ok = bool(s1["ok"] and d1.get("ok") and r.id2 != r.id1 and (p.get("id2") or {}).get("present") is True
              and p["id2"].get("fnv1a64") == (p.get("id1") or {}).get("fnv1a64"))
    return ok, "first_save %s (id1 %s); first_drop %s (id2 %s; at the 54 %s)" % (s1["ok"], r.id1, d1.get("ok"), r.id2, js(p)[:260])

def rejoin_resume(r, host, gc, label, hold=HOLD):  # REJOIN(n) by NAME; only with an ack RESUME (CANCELs a stale 54); HOLD
    rj = F.rejoin(host, gc, r.key, r.name, JOIN_S, ACK_S)
    rc = F.resume_and_clear(host) if rj["ack"] is not None else None
    rj["ok"] = rj["buildNewBase"] is None and rj["t68"] is not None and rj["ack"] is not None
    rj["lab"] = "BuildNewBaseState %s; 68 at %s s; ack at %s s; RESUME %s" % (rj["buildNewBase"], rj["t68"], rj["ack"], None if rc is None else rc["ok"])
    r.ev[label] = dict(pick(rj, ("buildNewBase", "t68", "ack", "ackSkipped")), join=rj["join_tcp"].get("ok"), log=rj["log"][-6:],
                       resume=None if rc is None else rc["ok"], cancel=bool(rc and "cancel" in rc))
    time.sleep(hold)
    return rj, rc

def gift_push(r, host, partner, label):  # GIFT + PUSH: the partner's push line within W_PUSH, the host's key fnv change within W_STORE
    hid = F.sid(host)
    fnv0, n0 = kk(host, hid, r.name).get("fnv1a64"), len(F.logl(partner))
    g = gift(host, partner, r.aff)
    w = wait_log(partner, n0, PUSH, W_PUSH) if g["ok"] else {}
    pk = w["line"].split(PUSH, 1)[1].rstrip(")") if w.get("line") else None
    f = wait_fnv_change(host, "host_%s_%s.data" % (hid, r.name), fnv0, W_STORE) if pk else {}
    gp = {"gift": g, "hostIdBefore": hid, "push": w, "pushKey": pk, "fnv0": fnv0, "fnv": f, "gifted": (g.get("gifted") or [None])[0]}
    gp["ok"] = bool(g["ok"] and len(g.get("gifted") or []) == 1 and pk and f.get("t") is not None)
    gp["lab"] = "gift %s (gifted %s, RECV %s s); push key %s; host fnv %s -> %s at %s s" % (
        g["ok"], g.get("gifted"), g.get("tRecv"), pk, fnv0, (f.get("key") or {}).get("fnv1a64"), f.get("t"))
    r.ev[label] = gp
    return gp

def kill(r, gc, host, label):  # KILL: the partner's proc.kill() (its rc is the drop itself), the host's 62 within DROP_S
    gc.proc.kill()
    rc = gc.proc.wait(timeout=15)
    w = F.wait_62(host, DROP_S)
    r.ev[label] = {"rc": rc, "w62": pick(w, ("ok", "t", "dialog"))}
    r.need(w["ok"], "no host 62 within %.0f s of the kill" % DROP_S)

def tail(r, host, gc, rj, rc, gifted):  # read rejoined (after HOLD_R): the row's -rejoin, -world, -resume, -common cells
    P, ow, osd, tops = r.rid, own(gc), ownsold(gc), [F.stk(host)[-1:], F.stk(gc)[-1:]]
    r.ev["rejoined"] = {"own": ow, "ownsold": osd, "tops": tops, "ids": ids(host, gc), "hostDialog": F.dlg(host)}
    r.cell(P + "-rejoin", rj["ok"], rj["lab"])
    r.cell(P + "-world", ow == r.marker[0] and gifted in osd, "own %s (MARKER %s); ownsold holds %r: %s" % (ow, r.marker[0], gifted, gifted in osd))
    r.cell(P + "-resume", bool(rc and rc["ok"]) and tops == [["GeoscapeState"], ["GeoscapeState"]], "resume_and_clear %s; tops %s" % (None if rc is None else rc["ok"], tops))
    new = [os.path.basename(p) for p in sorted(F.crashes() - r.c0)]
    r.cell(P + "-common", alive(host) and alive(gc) and not new, "host alive %s; %s alive %s; new crash files %s" % (alive(host), gc.name, alive(gc), new))

class Row:
    """one row = its own boot pair: cells, need -> Stop, finish printing EVIDENCE / PASS / FAIL / CAPTURE / the row verdict"""
    def __init__(self, rid, cells, fix_cells, tag, key_):
        self.rid, self.cells, self.fix_cells, self.tag, self.key = rid, cells, fix_cells, tag, key_
        self.res, self.procs, self.fails, self.name, self.marker = {}, [], [], "ClientPlayer", ([], [])
        self.t0, self.c0, self.ev = time.time(), F.crashes(), {"cpu": F.cpu()}
    def cell(self, cid, ok, label):
        self.res[cid] = (bool(ok), label)
    def need(self, ok, what):
        if not ok:
            raise Stop(what)
    def add(self, *gcs):
        self.procs.extend(gcs)
        return gcs[0]
    def finish(self, stop=None):
        self.ev.update(wall=F.now(self.t0), cpuEnd=F.cpu(), newCrash=[os.path.basename(p) for p in sorted(F.crashes() - self.c0)])
        if stop:
            self.ev["stop"] = stop
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        for cid in self.cells:
            ok, label = self.res.get(cid, (False, "not reached (%s)" % stop))
            print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, "FIX" if cid in self.fix_cells else "GUARD", label), flush=True)
            self.fails += [] if ok else [cid]
        if stop:
            cap = {gc.name: {"stack": F.stk(gc), "dialog": F.dlg(gc), "get_coop": F.coop(gc), "log": F.lines_since(gc, 0, ("[coop",))[-40:]}
                   if alive(gc) else {"alive": False, "rc": gc.proc.poll() if gc.proc else None} for gc in self.procs}
            print("CAPTURE %s: %s" % (self.rid, js(cap)), flush=True)
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)

def run(title, rows, fix_cells):  # rows [(rid, cells, fn, tag, key)]; every row runs after a failure; exit 0 only when every cell passes, else 2
    t0, fails, allc = time.time(), [], []
    for rid, cells, fn, tag, key_ in rows:
        r = Row(rid, cells, fix_cells, tag, key_)
        allc += list(cells)
        try:
            fn(r)
            r.finish()
        except Stop as e:
            r.finish(str(e))
        except Exception as e:  # noqa: BLE001 - an unexpected exception ends the row like a precondition miss
            r.finish("exception %s: %s" % (type(e).__name__, str(e)[:300]))
        finally:
            print("SHUT %s: %s" % (rid, js(shut(r.procs))), flush=True)
        fails += r.fails
    print("SUMMARY %s: %d/%d cells pass; failing %s; wall %.1f s" % (title, len(allc) - len(fails), len(allc), fails or "none", time.time() - t0), flush=True)
    return 0 if not fails else 2
