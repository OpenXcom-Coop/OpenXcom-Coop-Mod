"""W2-H79 VSR (spec docs rewrite/prompts/w2h79_visit_saveid_rollback.md (f); TASK 0 rewrite/w2h79-task0/sa/CONSTANTS.md; lead L-H70C-2,
ruling R-LH70C-2-1; capture lh70c-2-cap F21767-F21773): a base visit puts saveID back, so a partner who leaves, drops and rejoins after a host
save gets a new campaign. SEPARATE campaign; rows (one fresh boot pair each, key "49464", dirs w2h79_<row>_host / _client, the rejoiner
w2h79_<row>_client2; real presses only; GH = gift_helpers.py and F = drop_fixture.py imported unchanged; world, hostkeys /
keyinfo, ok67 over BasescapeState, leave and drop_now copied from the capture's cap.py):
  C1  MARKER; the client's globe click into the host's base (VISIT); read B; the host's quick save (its 54) and the client's 67 (SAVE54),
      the 67's OK; GEOSCAPE (the leave; QUICK written); read T; QUICK copied (C4's source); the client suspended and killed (the host's
      60 / 62); a NEW client rejoins by name; RESUME only after the host's ack; read R.
  C4  a fresh pair resumes C1's QUICK (only if C1 reached read T): the host's saveID, its stored partner world, the partner's world.
  CTL (control) MARKER; VISIT; read B; GEOSCAPE without a save; the host's quick save with the partner on its geoscape; read T; the drop;
      the rejoin; read R.
Cells (21): C1-pre GUARD, C1-ids RED, C1-key RED, C1-log RED, C1-rejoin RED, C1-world RED, C1-resume RED, C1-common GUARD; C4-pre, C4-id,
C4-key, C4-world, C4-common GUARD; CTL-pre, CTL-ids, CTL-key, CTL-log, CTL-rejoin, CTL-world, CTL-resume, CTL-common GUARD. Red (commit R1):
RED exactly C1-ids, C1-key, C1-log, C1-rejoin, C1-world, C1-resume (6 of 21). KEPT = '[coop] "basehost" loaded' lines in the client's log since read B.
ONE EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; every row runs after a failure; a precondition miss ends its row
(later cells "not reached"); a boot or construction miss fails the row's -pre cell with ONE CAPTURE line (both stacks, coop_dialog_info,
get_coop, the last 40 log lines of each machine); exit 0 only when every cell passes, else 2. one foreground run
per invocation.
Run: python tools/coop_test/test_visit_saveid_rejoin.py
"""
import json, os, shutil, sys, time  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gift_helpers as G  # noqa: E402
import drop_fixture as F  # noqa: E402
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY = "49464"
KEPT = '[coop] "basehost" loaded - saveID stays'
HOLD, HOLD_R, W_DROP, JOIN_S, ACK_S = 2.0, 3.0, 30.0, 10.0, 30.0
C1 = {}  # C1's read T, MARKER and QUICK copy (C4's source)


def q(gc, obj):
    return G.q(gc, obj)


def must(v, why):
    if not v:
        raise G.Stop(why)


def sid(gc):
    return q(gc, {"cmd": "get_coop"}).get("saveID")


def kept(gc, n0):
    return sum(1 for ln in G.log(gc)[n0:] if KEPT in ln) if gc is not None and n0 is not None else None


def keyinfo(gc, k):
    return G.pick(q(gc, {"cmd": "coop_file_info", "key": k}), ("present", "bytes", "fnv1a64"))


def role(gc):
    return G.pick(q(gc, {"cmd": "coop_file_info", "role": "host_copy_of_client"}), ("key", "present", "bytes", "fnv1a64"))


def hostkeys(x):
    """the host's role host_copy_of_client plus host_<id>_<partner>.data for the current id and every id of this row (CAP)"""
    h = x.host
    if not G.alive(h):
        return {"alive": False}
    cur = sid(h)
    d = {"role": role(h), "hostSaveIDnow": cur, "now host_%s" % cur: keyinfo(h, "host_%s_%s.data" % (cur, x.cname))}
    for lab, i in sorted(x.ids.items()):
        if i:
            d["%s host_%s" % (lab, i)] = keyinfo(h, "host_%s_%s.data" % (i, x.cname))
    return d


def world(gc):
    """the machine's own world: own bases [name, lon, lat, coopBaseId], funds, own soldiers [name, id] (CAP)"""
    if not G.alive(gc):
        return {"alive": False}
    g = q(gc, {"cmd": "geo_state"})
    s = q(gc, {"cmd": "get_soldiers"})
    return {"funds": g.get("funds"),
            "ownBases": [[b.get("name"), b.get("lon"), b.get("lat"), b.get("coopBaseId")] for b in g.get("bases", [])
                         if not b.get("coopIcon") and not b.get("coopBase")],
            "ownSoldiers": [[z.get("name"), z.get("id")] for b in s.get("bases", []) if not b.get("coopBaseFlag") and not b.get("coopIcon")
                            for z in b.get("soldiers", [])],
            "error": g.get("error") or s.get("error")}


def same_world(a, b, marker):
    """own bases (name, lon, lat, coopBaseId) and funds equal, the MARKER soldier [name, id] present in a"""
    a, b = a or {}, b or {}
    return bool(a.get("ownBases") and a.get("ownBases") == b.get("ownBases") and a.get("funds") is not None
                and a.get("funds") == b.get("funds") and marker and marker in (a.get("ownSoldiers") or []))


def capture(x):
    out = {}
    for n, gc in (("host", x.host), ("client", x.client)):
        if gc is None:
            continue
        d = {"log": [ln[:240] for ln in G.log(gc)[-40:]]}
        if G.alive(gc):
            d.update(stack=G.stack(gc), coop_dialog_info=G.dlg(gc), get_coop=q(gc, {"cmd": "get_coop"}))
        out[n] = d
    return out


def picker_marker(x, ev):
    """GH picker (the host's quick save + probe save + the client's window scale); MARKER = the client's world"""
    x.cname = q(x.host, {"cmd": "get_coop"}).get("clientName")
    ev["cname"] = x.cname
    G.picker(x, ev)
    wd = ev["MARKER"] = world(x.client)
    ob = (wd.get("ownBases") or [[None, None, None, None]])[0]
    x.marker = (wd.get("ownSoldiers") or [None])[0]
    must(ob[0] and ob[1] is not None and ob[2] is not None and x.marker, "MARKER: no named own base with coordinates and a soldier: %s" % wd)


def visit_b(x, ev):
    """VISIT (GH visit: the client's real globe click -> BasescapeState, insideCoopBase true); read B: both saveIDs, the log line counts"""
    G.visit(x, ev)
    x.ids["B"] = sid(x.client)
    x.nB = {"host": len(G.log(x.host)), "client": len(G.log(x.client))}
    ev["B"] = {"host": sid(x.host), "client": x.ids["B"], "n": x.nB}


def save54(x, ev):
    """SAVE54 (GH trigger54: the host's save_game_ui quick, its 54 with pending QUICK, the client's 67); S = the host's id at the 54"""
    G.trigger54(x, ev)
    x.ids["S"] = ev["S"] = ev["54"].get("saveID")
    must(x.ids["S"] != x.ids["B"], "S == B (%s): the save did not re-mint" % x.ids["S"])


def ok67_base(x, ev):
    """the client's real OK on its 67 over BasescapeState: BasescapeState on top within W_UI (insideCoopBase stays true there, F21766)"""
    c = x.client
    ok = G.real_click(c, G.dlg(c).get("backText") or "OK", G.W_UI)
    v, s = G.wait(lambda: G.top(c) == "BasescapeState", G.W_UI)
    ev["67 OK"] = {"press": ok, "s": s if v else None, "stack": G.stack(c), "inside": q(c, {"cmd": "get_coop"}).get("insideCoopBase")}
    must(v, "not BasescapeState after the 67's OK: %s" % ev["67 OK"])


def leave(x, ev, expect_write):
    """the client's real GEOSCAPE on BasescapeState: GeoscapeState with no BasescapeState within W_LEAVE; QUICK written (expect_write); HOLD"""
    c = x.client
    must(G.top(c) == "BasescapeState", "the leave: BasescapeState not on top: %s" % G.stack(c))
    ok = G.real_click(c, "GEOSCAPE", G.W_UI)
    v, s = G.wait(lambda: (lambda st: "GeoscapeState" in st and "BasescapeState" not in st)(G.stack(c)), G.W_LEAVE)
    ev["leave"] = {"press": ok, "s": s if v else None, "stack": G.stack(c)}
    must(v, "the client not back on its geoscape within %.0f s" % G.W_LEAVE)
    if expect_write:
        wv, ws = G.written(x, G.W_SAVE, 0.05)
        ev["leave"].update(written=wv, ws=ws, file=G.files(x.host).get(G.QUICK))
        must(wv, "QUICK not written within %.0f s of the leave" % G.W_SAVE)
    time.sleep(HOLD)


def read_t(x, ev):
    h, c = x.host, x.client
    ev["T"] = {"host": sid(h), "client": sid(c), "role": role(h), "keys": hostkeys(x), "world": world(c),
               "kept": {"client": kept(c, x.nB["client"]), "host": kept(h, x.nB["host"])}, "alive": [G.alive(h), G.alive(c)],
               "crash": len(G.crash() - x.c0)}
    ev["reached"].append("T")


def drop_now(x, ev):
    """no 54 in flight: suspend the client, read the host, kill it (its exit code is the drop), the host's 60 / 62 within W_DROP (CAP)"""
    h, c = x.host, x.client
    r = {"suspend": F.suspend(c), "atSuspend": {"hostStack": G.stack(h), "hostDlg": G.dlg(h), "hostSaveID": sid(h)}}
    c.proc.kill()
    r["killRc"] = c.proc.wait(timeout=15)
    x.killed.append(r["killRc"])
    x.client = None
    v, s = G.wait(lambda: G.top(h) == "CoopState" and G.dlg(h).get("code") in (60, 62), W_DROP, 0.05)
    r.update(s=s if v else None, host={"stack": G.stack(h), "dlg": G.dlg(h)})
    ev["drop"] = r
    must(v, "no host 60 / 62 within %.0f s of the kill" % W_DROP)


def rejoin_r(x, ev):
    """F rejoin: a NEW client <tag>_client2 joins by the original name (never a base placement); only with an ack F resume_and_clear;
    HOLD_R; read R = the rejoiner's world, both tops"""
    h = x.host
    x.client = GameClient("client2", None, make_user_dir(x.tag + "_client2"))
    rj = F.rejoin(h, x.client, KEY, x.cname, join_s=JOIN_S, ack_s=ACK_S)
    ev["rejoin"] = {k: rj.get(k) for k in ("spawned", "join_tcp", "profile_ok", "buildNewBase", "t68", "ack", "ackSkipped", "endJoin")}
    ev["rejoin"]["host"] = {"stack": G.stack(h), "dlg": G.dlg(h)}
    if rj.get("ack") is not None:
        rc = F.resume_and_clear(h)
        ev["resume"] = {"ok": rc.get("ok"), "cancel": bool(rc.get("cancel")), "end": rc.get("end")}
    time.sleep(HOLD_R)
    ev["R"] = {"world": world(x.client), "saveID": [sid(h), sid(x.client)], "tops": [G.top(h), G.top(x.client)],
               "alive": [G.alive(h), G.alive(x.client)], "crash": len(G.crash() - x.c0)}
    ev["reached"].append("R")


def keep_quick(x, ev):
    """QUICK (written at the leave) copied before the drop into s<slot>_w2h79_c1_save/ (C4's source; resume_campaign loads its basename)"""
    d = os.path.join(harness.TEST_ROOT, "s%d_w2h79_c1_save" % harness.HARNESS_SLOT)
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, G.QUICK)
    shutil.copyfile(os.path.join(x.host.user_dir, "xcom1", G.QUICK), dst)
    C1.update(quick=dst, T=ev["T"], marker=x.marker)
    ev["quickCopy"] = {"bytes": os.path.getsize(dst)}


def build_c1(x, ev):
    picker_marker(x, ev)
    visit_b(x, ev)
    save54(x, ev)
    ok67_base(x, ev)
    leave(x, ev, True)
    read_t(x, ev)
    keep_quick(x, ev)
    drop_now(x, ev)
    rejoin_r(x, ev)


def build_c4(x, ev):
    time.sleep(HOLD)
    h, c = x.host, x.client
    ev["read"] = {"host": sid(h), "role": role(h), "world": world(c), "alive": [G.alive(h), G.alive(c)], "crash": len(G.crash() - x.c0)}
    ev["reached"].append("T")


def build_ctl(x, ev):
    picker_marker(x, ev)
    visit_b(x, ev)
    leave(x, ev, False)
    qs = F.quick_save(x.host)
    x.ids["S"] = ev["S"] = qs.get("saveIDAfter")
    ev["save"] = {k: qs.get(k) for k in ("ok", "seen54", "written", "t", "saveIDBefore", "saveIDAfter", "log")}
    must(qs.get("ok"), "the host's quick save after the leave not seen / written: %s" % ev["save"])
    must(x.ids["S"] != x.ids["B"], "S == B (%s): the save did not re-mint" % x.ids["S"])
    time.sleep(HOLD)
    read_t(x, ev)
    drop_now(x, ev)
    rejoin_r(x, ev)


def g(ev, *path):
    for p in path:
        ev = ev.get(p) if isinstance(ev, dict) else (ev[p] if isinstance(ev, list) and isinstance(p, int) and p < len(ev) else None)
    return ev


def rejoined(ev):
    return g(ev, "rejoin", "buildNewBase") is None and g(ev, "rejoin", "t68") is not None and g(ev, "rejoin", "ack") is not None


def resumed(ev):
    return bool(g(ev, "resume", "ok")) and g(ev, "R", "tops") == ["GeoscapeState", "GeoscapeState"]


def alive_clean(ev, k):
    return g(ev, k, "alive") == [True, True] and g(ev, k, "crash") == 0


def drop_cells(p, kind, prelabel, pre_need):
    """the cells of a row with a drop + rejoin (C1 RED / CTL GUARD)"""
    return [
        ("%s-pre" % p, "GUARD", prelabel, "start", lambda ev: pre_need in ev["reached"]),
        ("%s-ids" % p, kind, "read T: host and client saveID == S", "T",
         lambda ev: ev.get("S") is not None and g(ev, "T", "host") == ev["S"] and g(ev, "T", "client") == ev["S"]),
        ("%s-key" % p, kind, "read T: role host_copy_of_client present" + (" with key host_<S>_<name>.data" if p == "C1" else ""), "T",
         lambda ev: g(ev, "T", "role", "present") is True and (p != "C1" or g(ev, "T", "role", "key") == "host_%s_%s.data" % (ev.get("S"),
                                                                                                                          ev.get("cname")))),
        ("%s-log" % p, kind, "the client log since read B: KEPT %s" % (">= 1" if p == "C1" else "== 0"), "T",
         lambda ev: (g(ev, "T", "kept", "client") or 0) >= 1 if p == "C1" else g(ev, "T", "kept", "client") == 0),
        ("%s-rejoin" % p, kind, "REJOIN: no BuildNewBaseState, the rejoiner's 68 within JOIN_S, the host's ack within ACK_S", "R", rejoined),
        ("%s-world" % p, kind, "read R: own bases, funds == read T's, the MARKER soldier [name, id] present", "R",
         lambda ev: same_world(g(ev, "R", "world"), g(ev, "T", "world"), ev.get("marker"))),
        ("%s-resume" % p, kind, "resume_and_clear ok: both tops GeoscapeState", "R", resumed),
        ("%s-common" % p, "GUARD", "the host alive to the end, the rejoiner alive at read R; no new crash file since the boot", "R",
         lambda ev: alive_clean(ev, "R")),
    ]


C1_CELLS = drop_cells("C1", "RED", "VISIT, SAVE54 with S != B, OK67B, LEAVE (QUICK written) all reached", "T")
CTL_CELLS = drop_cells("CTL", "GUARD", "VISIT, LEAVE, the quick save ok with S != B", "T")
C4_CELLS = [
    ("C4-pre", "GUARD", "the reload boot reached both GeoscapeState stable", "start", lambda ev: "T" in ev["reached"]),
    ("C4-id", "GUARD", "the host's saveID == C1's read T host saveID", "T",
     lambda ev: g(ev, "read", "host") is not None and g(ev, "read", "host") == g(ev, "c1T", "host")),
    ("C4-key", "GUARD", "role host_copy_of_client present", "T", lambda ev: g(ev, "read", "role", "present") is True),
    ("C4-world", "GUARD", "the client's own bases, funds and MARKER soldier == C1's read T", "T",
     lambda ev: same_world(g(ev, "read", "world"), g(ev, "c1T", "world"), ev.get("marker"))),
    ("C4-common", "GUARD", "both alive; no new crash file since the boot", "T", lambda ev: alive_clean(ev, "read")),
]


def run(rid, tag, cells, build, saves=None, skip=None, extra=None):
    """boot (a miss fails -pre), the construction (a Stop ends the row), shutdown, ONE EVIDENCE line, the cells, ONE CAPTURE line on a
    boot / construction miss, the row verdict -> (passed, wall, shutdown failures)"""
    r, t0, failed = G.Row(rid, [c[0] for c in cells]), time.time(), []
    ev = dict(extra or {}, reached=[] if skip else ["start"])
    if skip:
        ev["stop"] = skip
    else:
        x = G.boot(tag, KEY, saves=saves)
        x.killed, x.ids, x.nB, x.cname, x.marker = [], {}, None, None, None
        ev["cpu"] = x.cpu
        try:
            if x.err:
                ev.update(stop="boot: %s" % x.err, capture=capture(x))
            else:
                try:
                    build(x, ev)
                except Exception as e:  # Stop, or a probe that raised: the row ends here
                    ev.update(stop=G.short(e, 600), capture=capture(x))
        finally:
            failed += G.shut(x)
        ev.update(killedRc=x.killed, marker=ev.get("marker") or x.marker)
    cap = ev.pop("capture", None)
    ev["wall"] = round(time.time() - t0, 1)
    print("EVIDENCE %s: %s" % (rid, json.dumps(ev, sort_keys=True, default=str)), flush=True)
    for cid, kind, label, need, fn in cells:
        if need in ev["reached"]:
            try:
                ok = bool(fn(ev))
            except Exception as e:  # a cell that cannot read its value fails
                ok, label = False, "%s (%s)" % (label, G.short(e, 200))
            r.cell(cid, kind, label + ("" if ok or need != "start" or "stop" not in ev else " (%s)" % str(ev["stop"])[:200]), ok)
    if "stop" in ev:
        r.stop(ev["stop"])
    if cap is not None:
        print("CAPTURE %s: %s" % (rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
    print(("PASS %s" % rid) if not r.fails else ("FAIL %s: %s" % (rid, " ".join(r.fails))), flush=True)
    return not r.fails, ev["wall"], failed


def row_c1():
    C1.clear()
    shutil.rmtree(os.path.join(harness.TEST_ROOT, "s%d_w2h79_c1_save" % harness.HARNESS_SLOT), ignore_errors=True)
    return run("C1", "w2h79_c1", C1_CELLS, build_c1)


def row_c4():
    if not C1.get("quick"):
        return run("C4", "w2h79_c4", C4_CELLS, None, skip="C1 did not reach read T (no QUICK copy)")
    return run("C4", "w2h79_c4", C4_CELLS, build_c4, saves=(C1["quick"],), extra={"c1T": C1["T"], "marker": C1["marker"]})


def row_ctl():
    return run("CTL", "w2h79_ctl", CTL_CELLS, build_ctl)


if __name__ == "__main__":
    sys.exit(G.main("test_visit_saveid_rejoin", (("C1", row_c1), ("C4", row_c4), ("CTL", row_ctl))))
