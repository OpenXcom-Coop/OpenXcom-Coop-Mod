"""W2-H79 VSW (spec docs rewrite/prompts/w2h79_visit_saveid_rollback.md (f); TASK 0 rewrite/w2h79-task0/sa/CONSTANTS.md; lead L-H70C-2,
ruling R-LH70C-2-1; capture lh70c-2-cap F21771, F21772): the save-window rows beside test_visit_saveid_rejoin.py. SEPARATE campaign; rows
(one fresh boot pair each, key "49465", dirs w2h79_<row>_host / _client, the rejoiner w2h79_<row>_client2; real presses only; GH =
gift_helpers.py and F = drop_fixture.py imported unchanged; world, hostkeys / keyinfo, ok67 over BasescapeState and leave copied
from the capture's cap.py):
  C2  MARKER; the client's globe click into the host's base (VISIT); read B; the host's quick save (its 54) and the client's 67 (SAVE54), the
      67's OK; GEOSCAPE (the leave; QUICK written); read T; the host's NEXT quick save with the client suspended at its first 54 and killed
      (F drop_at_54; S2 = the host's id at that 54); a NEW client rejoins by name; RESUME only after the host's ack; read R.
  C3  MARKER; VISIT; read B; SOLDIERS; SAVE54 (the 67 over SoldiersState), its OK (insideCoopBase false); the client's real OK on
      SoldiersState -> BasescapeState inside the 67 window; read W (the client's saveID); GEOSCAPE (QUICK written); read T.
Cells (13): C2-pre GUARD, C2-copied RED, C2-key RED, C2-rejoin RED, C2-world RED, C2-resume RED, C2-common GUARD; C3-pre GUARD, C3-ok RED,
C3-log RED, C3-ids RED, C3-key RED, C3-common GUARD. Red (commit R1): RED exactly C2-copied, C2-key, C2-rejoin, C2-world, C2-resume, C3-ok,
C3-log, C3-ids, C3-key (9 of 13). KEPT = '[coop] "basehost" loaded' lines in the client's log since read B. ONE EVIDENCE line per row, one PASS / FAIL
line per cell, the row verdict; every row runs after a failure; a precondition miss ends its row (later cells "not reached"); a boot or
construction miss fails the row's -pre cell with ONE CAPTURE line (both stacks, coop_dialog_info, get_coop, the last 40 log lines of each
machine); exit 0 only when every cell passes, else 2. one foreground run per invocation.
Run: python tools/coop_test/test_visit_saveid_window.py
"""
import json, os, re, sys, time  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gift_helpers as G  # noqa: E402
import drop_fixture as F  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY = "49465"
KEPT = '[coop] "basehost" loaded - saveID stays'
H58 = re.compile(r"\[coop\] (\d+) partner world\(s\) copied from saveID (\d+) to (\d+)")
HOLD, HOLD_R, W_DROP, JOIN_S, ACK_S = 2.0, 3.0, 30.0, 10.0, 30.0


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


def leave(x, ev):
    """the client's real GEOSCAPE on BasescapeState: GeoscapeState with no BasescapeState within W_LEAVE; QUICK written; HOLD (CAP)"""
    c = x.client
    must(G.top(c) == "BasescapeState", "the leave: BasescapeState not on top: %s" % G.stack(c))
    ok = G.real_click(c, "GEOSCAPE", G.W_UI)
    v, s = G.wait(lambda: (lambda st: "GeoscapeState" in st and "BasescapeState" not in st)(G.stack(c)), G.W_LEAVE)
    ev["leave"] = {"press": ok, "s": s if v else None, "stack": G.stack(c)}
    must(v, "the client not back on its geoscape within %.0f s" % G.W_LEAVE)
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


def drop54(x, ev):
    """DROP54: F drop_at_54 on the host's NEXT quick save (the client suspended at the host's first 54, the probe, the kill, the 62);
    S2 = the host's id at that 54; the host log's W2-H58 lines since the trigger"""
    h = x.host
    probe = lambda hh: (lambda cur: {"saveID": cur, "key": "host_%s_%s.data" % (cur, x.cname),  # noqa: E731
                                     "info": keyinfo(hh, "host_%s_%s.data" % (cur, x.cname)), "keys": hostkeys(x)})(sid(hh))
    d = F.drop_at_54(h, x.client, "quick", probe=probe, drop_s=W_DROP)
    x.ids["S2"] = ev["S2"] = (d.get("at54") or {}).get("saveID")
    if "kill" in d:
        x.killed.append(d["kill"].get("returncode"))
        x.client = None
    ev["drop54"] = {k: d.get(k) for k in ("ok", "why", "seen54", "suspend", "probe", "kill", "after62", "saveIDBefore")}
    ev["h58"] = [ln.split("\t")[-1][:240] for ln in G.log(h)[d.get("n0", 0):] if "partner world(s) copied from saveID" in ln]
    must(d.get("ok"), "drop_at_54: %s" % d.get("why"))
    ev["reached"].append("D")


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


def build_c2(x, ev):
    picker_marker(x, ev)
    visit_b(x, ev)
    save54(x, ev)
    ok67_base(x, ev)
    leave(x, ev)
    read_t(x, ev)
    drop54(x, ev)
    rejoin_r(x, ev)


def build_c3(x, ev):
    picker_marker(x, ev)
    visit_b(x, ev)
    G.to_soldiers(x, ev)
    save54(x, ev)
    G.ok67(x, ev)
    c = x.client
    ok = G.real_click(c, "OK", G.W_UI)
    v, s = G.wait(lambda: G.top(c) == "BasescapeState", G.W_UI)
    ev["soldiers OK"] = {"press": ok, "s": s if v else None, "stack": G.stack(c)}
    must(v, "SoldiersState's OK did not return to BasescapeState: %s" % ev["soldiers OK"])
    ev["W"] = {"client": sid(c), "kept": kept(c, x.nB["client"]), "inside": q(c, {"cmd": "get_coop"}).get("insideCoopBase")}
    leave(x, ev)
    read_t(x, ev)


def g(ev, *path):
    for p in path:
        ev = ev.get(p) if isinstance(ev, dict) else None
    return ev


def copied(ev):
    """the host log since the second trigger: 'W2-H58: N partner world(s) copied from saveID S to S2' with N >= 1"""
    return any(int(m.group(1)) >= 1 and int(m.group(2)) == ev.get("S") and int(m.group(3)) == ev.get("S2")
               for m in (H58.search(ln) for ln in ev.get("h58") or []) if m)


C2_CELLS = [
    ("C2-pre", "GUARD", "VISIT, SAVE54 (S != B), OK67B, LEAVE, DROP54 ok (the 54 seen, the 62 after the kill)", "start",
     lambda ev: "D" in ev["reached"]),
    ("C2-copied", "RED", "the host log since the second trigger: 'W2-H58: N partner world(s) copied from saveID S to S2', N >= 1", "D", copied),
    ("C2-key", "RED", "DROP54's probe at the 54: host_<S2>_<name>.data present", "D",
     lambda ev: g(ev, "drop54", "probe", "saveID") == ev.get("S2") and g(ev, "drop54", "probe", "info", "present") is True),
    ("C2-rejoin", "RED", "REJOIN: no BuildNewBaseState, the rejoiner's 68 within JOIN_S, the host's ack within ACK_S", "R",
     lambda ev: g(ev, "rejoin", "buildNewBase") is None and g(ev, "rejoin", "t68") is not None and g(ev, "rejoin", "ack") is not None),
    ("C2-world", "RED", "read R: own bases, funds == read T's, the MARKER soldier [name, id] present", "R",
     lambda ev: same_world(g(ev, "R", "world"), g(ev, "T", "world"), ev.get("marker"))),
    ("C2-resume", "RED", "resume_and_clear ok: both tops GeoscapeState", "R",
     lambda ev: bool(g(ev, "resume", "ok")) and g(ev, "R", "tops") == ["GeoscapeState", "GeoscapeState"]),
    ("C2-common", "GUARD", "the host alive to the end, the rejoiner alive at read R; no new crash file since the boot", "R",
     lambda ev: g(ev, "R", "alive") == [True, True] and g(ev, "R", "crash") == 0),
]
C3_CELLS = [
    ("C3-pre", "GUARD", "VISIT, SOLDIERS, SAVE54 (S != B), the 67's OK, the SoldiersState OK, LEAVE (QUICK written) reached", "start",
     lambda ev: "T" in ev["reached"]),
    ("C3-ok", "RED", "read W: the client's saveID == S", "T", lambda ev: ev.get("S") is not None and g(ev, "W", "client") == ev["S"]),
    ("C3-log", "RED", "the client log since read B: KEPT >= 1", "T", lambda ev: (g(ev, "T", "kept", "client") or 0) >= 1),
    ("C3-ids", "RED", "read T: host and client saveID == S", "T",
     lambda ev: ev.get("S") is not None and g(ev, "T", "host") == ev["S"] and g(ev, "T", "client") == ev["S"]),
    ("C3-key", "RED", "read T: role host_copy_of_client present", "T", lambda ev: g(ev, "T", "role", "present") is True),
    ("C3-common", "GUARD", "both alive; no new crash file since the boot", "T",
     lambda ev: g(ev, "T", "alive") == [True, True] and g(ev, "T", "crash") == 0),
]


def run(rid, tag, cells, build):
    """boot (a miss fails -pre), the construction (a Stop ends the row), shutdown, ONE EVIDENCE line, the cells, ONE CAPTURE line on a
    boot / construction miss, the row verdict -> (passed, wall, shutdown failures)"""
    r, t0, failed, ev = G.Row(rid, [c[0] for c in cells]), time.time(), [], {"reached": ["start"]}
    x = G.boot(tag, KEY)
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
    ev.update(killedRc=x.killed, marker=x.marker)
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


def row_c2():
    return run("C2", "w2h79_c2", C2_CELLS, build_c2)


def row_c3():
    return run("C3", "w2h79_c3", C3_CELLS, build_c3)


if __name__ == "__main__":
    sys.exit(G.main("test_visit_saveid_window", (("C2", row_c2), ("C3", row_c3))))
