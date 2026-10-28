"""W2-H58 S-A KEPT (tools/coop_test/test_rejoin_world_kept.py): a partner who drops during the host's quick save rejoins into its own
campaign (L-LH54-2-1, ruling R-H58-0). Spec docs rewrite/prompts/w2h58_sa_rekey.md (f) (stage S-A) and the common file
rewrite/prompts/w2h58_rejoin_world_kept.md (section F: the shared fixture drop_fixture.py); TASK 0 values in
rewrite/w2h58-task0/sa/CONSTANTS.md. A host quick or manual save gives the campaign a new saveID before the partner's fresh world arrives;
the host's copy of the partner's world is stored under host_<saveID>_<name>.data. A partner that drops during "Saving..." (54) leaves the
copy under the OLD id only; the rejoin looks up the NEW id, misses, and starts the partner on a fresh world (F18420-F18421).
ONE boot (SEPARATE new_campaign on lobby key K1, both geoscapes stable), the controls first and the red row last:
  Row C0   (GUARD) C0-blob: the host stores the client's world under the campaign's id0 (present, bytes > 0).
  Row K2i  (control: the blob lands before the drop, F18422) a quick save with the client running, kill, client2 rejoins, RESUME.
           K2i-key: the save written, id1 != id0, key(id1) present, key(id0) pruned. K2i-world: client2 never BuildNewBaseState, its
           [GeoscapeState, CoopState] code 68 within JOIN_S, own(client2) holds (CB_NAME, CB).
  Row K2ii (control: an autosave drop, F18423) client2 dropped at the host's first sight of its 54, client3 rejoins, RESUME, the stale 54
           CANCELLED when it is on top (F18431, W2-H59's). K2ii-id: at the 54 saveID == id1, key(id1) with K2i's end fnv.
           K2ii-world: as K2i-world for client3.
  Row RK1  (the red, LAST) a quick save, client3 dropped at its 54 (id2 = the re-minted id), client4 rejoins. RK1-key (RED): key(id2)
           present at the 54 with key(id1)'s bytes and fnv1a64. RK1-world (RED): client4 never BuildNewBaseState and its 68 within JOIN_S.
           RK1-bases (RED): own(client4) holds (CB_NAME, CB). RK1-store (GUARD): key(id1) present at the join with its at-54 fnv.
  END      CRASH (GUARD, evaluated at the end of every run): no crash file new since the boot start; the host alive.
Red today: RK1-key, RK1-world, RK1-bases FAIL (the fresh world); every other cell PASS. Green (EA1-EA3): all PASS.
own(gc) = geo_state bases with coopIcon false as [name, coopBaseId]; key(id) = coop_file_info {key: host_<id>_ClientPlayer.data}. Every
rejoiner is a NEW GameClient on its own dir joining K1 by the name ClientPlayer. Never dismiss_popup, coop_dialog_back or a base placement:
a fresh world is evidence, never built on. One EVIDENCE line per row, one PASS / FAIL line per cell, then the row verdict; a precondition
miss ends its row (CAPTURE line) and every later row (cells "not reached"); a boot miss fails every cell "boot" with ONE CAPTURE line.
WV-D95 / WV-D99 / WV-D100: ONE foreground run, no SKIP; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_rejoin_world_kept.py   (OXC_HARNESS_SLOT selects the lane)"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import drop_fixture as F  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

K1 = "49193"
K2 = "49194"  # reserved for the BOOT replacement rule (two boots, PINNED SETUP VALUES); unused while the one boot holds
NAME = "ClientPlayer"
STABLE_S, SEEN_S, DROP_S, JOIN_S, ACK_S, SAVE_S = 5.0, 10.0, 5.0, 10.0, 30.0, 20.0
ROWS = (("C0", ("C0-blob",)), ("K2i", ("K2i-key", "K2i-world")), ("K2ii", ("K2ii-id", "K2ii-world")),
        ("RK1", ("RK1-key", "RK1-world", "RK1-bases", "RK1-store")), ("END", ("CRASH",)))
RED = ("RK1-key", "RK1-world", "RK1-bases")
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)


class Stop(Exception):
    """a precondition missed: the row ends here"""


def js(v):
    return json.dumps(v, sort_keys=True, default=str)


def kstr(r):
    return "%s %s %s" % ("present" if r.get("present") else "absent", r.get("bytes"), r.get("fnv1a64") or "-")


def kk(host, i):
    return F.key(host, "host_%s_%s.data" % (i, NAME))


def own(gc):
    r = F.q(gc, {"cmd": "geo_state"})
    return {"own": [[b.get("name"), b.get("coopBaseId")] for b in r.get("bases", []) if not b.get("coopIcon")],
            "all": [[b.get("name"), b.get("coopBaseId"), b.get("coopIcon"), b.get("coopBase")] for b in r.get("bases", [])],
            "error": r.get("error")}


def alive(gc):
    return gc is not None and gc.proc is not None and gc.proc.poll() is None


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
        self.host = GameClient("host", None, make_user_dir("w2h58a_host"))
        self.client = GameClient("client", None, make_user_dir("w2h58a_client"))
        self.c2 = self.c3 = self.c4 = None
        self.fails, self.dead, self.cb = [], None, None

    def procs(self):
        return [g for g in (self.host, self.client, self.c2, self.c3, self.c4) if g is not None]

    def rejoiner(self, n):
        return GameClient("client%d" % n, None, make_user_dir("w2h58a_client%d" % n))


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
        self.ev["hostLog"] = F.lines_since(self.x.host, self.n0)
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


def row_c0(x, r):
    r.ev["ownHost"] = own(x.host)
    r.ev["ownClient"] = oc = own(x.client)
    r.need(len(oc["own"]) == 1, "the client's own base not read from geo_state: %s" % oc)
    x.cb = tuple(oc["own"][0])  # (CB_NAME, CB), read at run time (S25)
    x.id0 = r.ev["id0"] = F.sid(x.host)
    r.ev["blob0"] = b = kk(x.host, x.id0)
    r.cell("C0-blob", b.get("present") is True and (b.get("bytes") or 0) > 0, "key(id0 %s) %s" % (x.id0, kstr(b)))


def row_k2i(x, r):
    r.ev["save"] = s = F.quick_save(x.host, F.QUICK, SAVE_S)
    x.id1 = r.ev["id1"] = F.sid(x.host)
    k0, k1 = kk(x.host, x.id0), kk(x.host, x.id1)
    r.ev["keys"] = {"id0": k0, "id1": k1}
    r.cell("K2i-key", s["ok"] and x.id1 != x.id0 and k1.get("present") is True and k0.get("present") is False,
           "quick save ok %s (54 seen %s, written %s); id0 %s -> id1 %s; key(id1) %s; key(id0) %s"
           % (s["ok"], s["seen54"], s["written"], x.id0, x.id1, kstr(k1), kstr(k0)))
    x.client.proc.kill()
    r.ev["kill"] = {"t": F.now(x.t0), "rc": x.client.proc.wait(timeout=15)}
    r.ev["w62"] = w = F.wait_62(x.host, DROP_S)
    r.need(w["ok"], "no host 62 within %.0f s of the kill" % DROP_S)
    x.c2 = x.rejoiner(2)
    r.ev["tJoin"] = F.now(x.t0)
    r.ev["rejoin"] = rj = F.rejoin(x.host, x.c2, K1, NAME, JOIN_S, ACK_S, at_join=lambda h: {"id0": kk(h, x.id0), "id1": kk(h, x.id1)})
    r.ev["own2"] = ow = own(x.c2)
    r.cell("K2i-world", rj["buildNewBase"] is None and rj["t68"] is not None and list(x.cb) in ow["own"], "client2: " + world(x, rj, ow))
    r.need(rj["ack"] is not None, "no host 62 with resumeAck true within %.0f s of join_tcp" % (JOIN_S + ACK_S))
    r.ev["resume"] = rc = F.resume_and_clear(x.host)
    r.need(rc["ok"] and "cancel" not in rc, "RESUME / host GeoscapeState within 5 s: %s" % js(rc.get("end")))
    x.end1 = r.ev["endKey"] = kk(x.host, x.id1)
    r.ev["files"] = F.files(x.host)


def row_k2ii(x, r):
    r.ev["drop"] = d = F.drop_at_54(x.host, x.c2, "auto_geoscape", 0, lambda h: {"saveID": F.sid(h), "id1": kk(h, x.id1)}, SEEN_S, DROP_S)
    r.need("probe" in d, d.get("why"))
    p = d["probe"]
    r.cell("K2ii-id", p["saveID"] == x.id1 and p["id1"].get("present") is True and x.end1.get("present") is True
           and p["id1"].get("fnv1a64") == x.end1.get("fnv1a64"),
           "at the 54 saveID %s (id1 %s); key(id1) %s; K2i's end fnv %s" % (p["saveID"], x.id1, kstr(p["id1"]), x.end1.get("fnv1a64")))
    r.need(d["ok"], d.get("why"))
    x.c3 = x.rejoiner(3)
    r.ev["tJoin"] = F.now(x.t0)
    r.ev["rejoin"] = rj = F.rejoin(x.host, x.c3, K1, NAME, JOIN_S, ACK_S, at_join=lambda h: {"id1": kk(h, x.id1)})
    r.ev["own3"] = ow = own(x.c3)
    r.cell("K2ii-world", rj["buildNewBase"] is None and rj["t68"] is not None and list(x.cb) in ow["own"], "client3: " + world(x, rj, ow))
    r.need(rj["ack"] is not None, "no host 62 with resumeAck true within %.0f s of join_tcp" % (JOIN_S + ACK_S))
    r.ev["resume"] = rc = F.resume_and_clear(x.host)
    r.need(rc["ok"], "RESUME (+ CANCEL of a stale 54) / host GeoscapeState within 5 s: %s" % js(rc.get("end")))
    r.ev["endKey"] = kk(x.host, x.id1)
    r.ev["files"] = F.files(x.host)


def row_rk1(x, r):
    def probe(h):
        i2 = F.sid(h)
        return {"id2": i2, "id1": kk(h, x.id1), "id2key": kk(h, i2)}
    r.ev["drop"] = d = F.drop_at_54(x.host, x.c3, "quick", 0, probe, SEEN_S, DROP_S)
    r.need("probe" in d, d.get("why"))
    p = d["probe"]
    x.id2 = p["id2"]
    r.need(isinstance(x.id2, int) and x.id2 != x.id1, "the re-mint did not run: id2 %s, id1 %s" % (x.id2, x.id1))
    k1, k2 = p["id1"], p["id2key"]
    r.cell("RK1-key", k2.get("present") is True and k1.get("present") is True and k2.get("bytes") == k1.get("bytes")
           and k2.get("fnv1a64") == k1.get("fnv1a64"), "at the 54 (id1 %s -> id2 %s): key(id2) %s; key(id1) %s" % (x.id1, x.id2, kstr(k2), kstr(k1)))
    r.need(d["ok"], d.get("why"))
    x.c4 = x.rejoiner(4)
    r.ev["tJoin"] = F.now(x.t0)
    r.ev["rejoin"] = rj = F.rejoin(x.host, x.c4, K1, NAME, JOIN_S, ACK_S, at_join=lambda h: {"id1": kk(h, x.id1), "id2": kk(h, x.id2)})
    r.need(rj["join_tcp"].get("ok"), "client4 join_tcp failed: %s" % rj["join_tcp"])
    r.ev["own4"] = ow = own(x.c4)
    r.cell("RK1-world", rj["buildNewBase"] is None and rj["t68"] is not None, "client4: " + world(x, rj, ow))
    r.cell("RK1-bases", list(x.cb) in ow["own"], "own(client4) %s (want %s); all %s" % (ow["own"], list(x.cb), ow["all"]))
    j1 = rj["atJoin"]["id1"]
    r.cell("RK1-store", j1.get("present") is True and j1.get("fnv1a64") == k1.get("fnv1a64"),
           "key(id1) at the join %s; at the 54 %s" % (kstr(j1), kstr(k1)))
    r.ev["afterJoinKeys"] = {"id1": kk(x.host, x.id1), "id2": kk(x.host, x.id2)}
    if rj["ack"] is not None:  # END (EVIDENCE only, green): RESUME, then the host's top (the stale 54 is W2-H59's, F18497)
        r.ev["end"] = F.resume_and_clear(x.host)
    r.ev["files"] = F.files(x.host)


def end_row(x, crash0):
    r = Row(x, "END")
    new = sorted(F.crashes() - crash0)
    r.ev["newCrash"] = [os.path.basename(p) for p in new]
    r.ev["alive"] = {gc.name: alive(gc) for gc in x.procs()}
    r.ev["w2h58Lines"] = [ln.split("\t")[-1] for ln in F.logl(x.host) if "W2-H58" in ln]
    r.cell("CRASH", not new and alive(x.host), "new crash files %d %s; host alive %s" % (len(new), r.ev["newCrash"][:3], alive(x.host)))
    r.finish()


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
    crash0 = F.crashes()
    try:
        if boot(x):
            for rid, fn in (("C0", row_c0), ("K2i", row_k2i), ("K2ii", row_k2ii), ("RK1", row_rk1)):
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
            end_row(x, crash0)
    finally:
        for gc in x.procs()[::-1]:
            try:
                if alive(gc):
                    F.resume(gc)  # harmless when not suspended
                    gc.shutdown(expected_returncodes=OKRC)
            except Exception as e:  # noqa: BLE001
                print("FAIL shutdown %s: %s" % (gc.name, str(e)[:300]), flush=True)
    wall = F.now(x.t0)
    cells = [c for _r, cs in ROWS for c in cs]
    print("SUMMARY W2-H58 S-A KEPT: %d/%d cells pass; failing %s; wall %.1f s" % (len(cells) - len(set(x.fails)), len(cells),
                                                                                sorted(set(x.fails)) or "none", wall), flush=True)
    return 0 if not x.fails else 2


if __name__ == "__main__":
    sys.exit(main())
