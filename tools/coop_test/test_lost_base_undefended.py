"""W2-H80 S-A LBU (tools/coop_test/test_lost_base_undefended.py): GUARD - a base the host loses undefended leaves no marker on the
partner's globe (lead L-BH2, ruling R-LBH2-1; capture lbh2-cap C1-ctl F21832, here on the host's FIRST base HB).
Spec docs rewrite/prompts/w2h80_lost_base_ghost.md (f) LBU; TASK 0 values in rewrite/w2h80-task0/sa/CONSTANTS.md.
In a SEPARATE campaign the host owns HB (its first base) and SPARE. STRIP empties HB (set_soldier_dead on every HB soldier, host only:
staging, no relay), so trigger_base_defense on HB finds no defender and pops BaseDestroyedState, whose constructor sends delete_base: the
client erases its marker of HB at once. E1 (the W2-H80 green, TCP) does not touch this path (no battle world): this file passes on both builds.
ONE boot (key KEY, dirs w2h80_u_*). Bring-up: spawn + connect both; session.new_campaign (HB at HOST_POS); geo.slow_clock; geo.drain_popups;
the window mapping per machine from INTERCEPT + CANCEL (real clicks). SPARE: BASES, BUILD NEW BASE, one globe click at PICK, OK, the name keys,
OK, LIFTS, GEOSCAPE (real clicks). P0: client INTERCEPT + CANCEL, 3 s: host own [HB, SPARE], host mirrors [CB], client mirrors {HB, SPARE}.
STRIP (levers: get_soldiers, set_soldier_dead); U-mark; spawn_ufo; trigger_base_defense (T_TRIG = its reply); GONE: poll the client's mirrors
every 0.05 s for GONE_S and the host's top for W_BDS; B0 (BaseDestroyedState open); HOST OK (real clicks to GeoscapeState); A0 both
GeoscapeState; A1 client INTERCEPT + CANCEL + RT_SETTLE; A2 >= PLUS10_S after A0. GHOST(host) = host mirrors with id LOST or within POS_TOL of
LOST_POS.
  Row R4  R4-pre (GUARD) P0; HB had >= 1 soldier and 0 after STRIP (every reply ok, dead true); the trigger reply ok naming HB;
          BaseDestroyedState on the host's top within W_BDS of T_TRIG (no BriefingState).  R4-gone (GUARD) LOST gone from the client's
          mirrors within GONE_S of T_TRIG and absent at B0, A0, A1, A2.  R4-host (GUARD) the host's own list lacks LOST at A0; the host's
          mirrors == [CB] at A0 and A2; GHOST(host) empty at A0 and A2.  R4-skip0 (GUARD) 0 SKIP lines on either machine since U-mark.
  END     CRASH (GUARD): no new crash file in the lane's crash folder since the file start; both processes alive until their shutdown.
Red today and green (E1): all 5 PASS (a guard file).
Every press is a real click_widget or inject_input except the logged levers named above. One EVIDENCE line per row, one PASS / FAIL line per
cell, then the row verdict; a precondition miss ends its row (CAPTURE line, later cells "not reached"); a boot miss fails R4-pre with ONE
CAPTURE line. ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_lost_base_undefended.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, math, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo, harness, session  # noqa: E401,E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY = "49493"                               # lobby key (CONSTANTS.md; 0 hits in src + tools at 4aaaff0c0)
HOST_POS = (0.90, -0.60)                    # rad: HB; SPARE is picked >= 0.15 rad away on land
SPARE_NAME = "spare"
LIFTS = ((2, 2), (3, 2), (2, 3), (3, 3))    # the lift tile, then its replacement tiles in row order
RT_SETTLE, PLUS10_S, GONE_S, W_BDS, POS_TOL, BOOT_S = 3.0, 10.0, 1.0, 2.0, 1e-4, 240.0
UFO = {"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
       "race": "STR_SECTOID", "trajectory": "P0", "state": "flying"}
SKIP_N = "[coop] baseRequest not answered - the live world is the SEPARATE battle world"   # E1 (the green's log line)
NEEDLES = ("baseRequest not answered", "coopBase3 marker", "coop-ui] push", "coop-ui] pop", "[coop-session]", "coop-debrief")
ROWS = (("R4", ("R4-pre", "R4-gone", "R4-host", "R4-skip0")), ("END", ("CRASH",)))
RED = ()
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
T0 = [time.time()]

class Stop(Exception):  # a precondition missed: the row ends here
    pass

# ----- probes and real input (copied from the capture rewrite/lbh2-cap/cap.py, never imported) -----
def js(v): return json.dumps(v, sort_keys=True, default=str)
def now(): return round(time.time() - T0[0], 2)
def alive(gc): return gc is not None and gc.proc is not None and gc.proc.poll() is None
def crashes(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "**", "crash_*"), recursive=True))
def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # noqa: BLE001
        return {"error": ("%s: %s" % (type(e).__name__, e))[:200]}
def stk(gc):
    r = q(gc, {"cmd": "get_state"})
    return [s.split("::")[-1] for s in r["states"]] if "states" in r else ["probe failed: %s" % r.get("error")]
def top(gc): return (stk(gc) or [None])[-1]
def dlg(gc):
    r = q(gc, {"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("code", "title", "backText", "backVisible", "error") if k in r}
def census(gc):
    g = q(gc, {"cmd": "geo_state"})
    bl = [[b.get("coopBaseId"), b.get("name"), bool(b.get("coopIcon")), bool(b.get("coopBase")), round(b.get("lon", 0), 5),
           round(b.get("lat", 0), 5)] for b in g.get("bases", [])]
    return {"t": now(), "bases": bl, "stack": stk(gc), "selectedBase": g.get("selectedBase"), "error": g.get("error")}
def own(c): return [[b[0], b[1]] for b in c["bases"] if not b[2] and not b[3]]
def mirrors(c): return [[b[0], b[1], b[4], b[5]] for b in c["bases"] if b[2]]
def mir_ids(c): return [m[0] for m in mirrors(c)]
def ghost(c, st):
    return [m for m in mirrors(c) if m[0] == st["lost"] or (abs(m[2] - st["lostPos"][0]) <= POS_TOL and abs(m[3] - st["lostPos"][1]) <= POS_TOL)]
def cpu():
    c = harness.cpu_load()
    return {"t": time.strftime("%H:%M:%S"), "cpu": harness.cpu_text(c["cpu"]), "wardogs": str(len(c["wardogs"]))}
def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []
def lines_since(gc, n0): return [ln.split("\t")[0][-13:-1] + " " + ln.split("\t")[-1][:200] for ln in logl(gc)[n0:] if any(n in ln for n in NEEDLES)]
def hits(gc, needle, n0, n1=None):
    """the log lines holding `needle` in [n0, n1): [line index, time hh-mm-ss.mmm, text]"""
    return [[i, ln.split("\t")[0][-13:-1], ln.split("\t")[-1][:120]] for i, ln in enumerate(logl(gc)[n0:n1], n0) if needle in ln]
def cw(gc, match, settle=1.0, ready=False):
    if ready:  # a POPUP window (InterceptState) drops a click on a hidden button
        session.wait_widget_ready(gc, match)
    r = q(gc, {"cmd": "click_widget", "match": match})
    time.sleep(settle)
    return {"match": match, "ok": r.get("ok"), "err": r.get("error"), "base": [r.get("baseX"), r.get("baseY")],
            "win": [r.get("winX"), r.get("winY")], "after": stk(gc)}
def affine(r1, r2):
    out = [(r1["win"][i] - r2["win"][i]) / (r1["base"][i] - r2["base"][i]) if r1["base"][i] != r2["base"][i] else None for i in (0, 1)]
    sc = round(out[0] or out[1], 3)
    return (sc, r1["win"][0] - sc * r1["base"][0], sc, r1["win"][1] - sc * r1["base"][1])
def key(gc, sym): return q(gc, {"cmd": "inject_input", "kind": "key", "key": sym})
def click_px(gc, bx, by, sc, until_not, offsets=((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2))):
    """real clicks at base pixel (bx, by) + offsets through the window mapping until the top leaves `until_not`"""
    tries = []
    for dx, dy in offsets:
        wx, wy = int(round(sc[0] * (bx + dx) + sc[1])), int(round(sc[2] * (by + dy) + sc[3]))
        q(gc, {"cmd": "inject_input", "kind": "click", "x": wx, "y": wy})
        seen, t4 = [], time.time()
        while time.time() - t4 < 1.0:
            t = top(gc)
            e = [t] + ([dlg(gc).get("code")] if t == "CoopState" else [])
            if not seen or seen[-1] != e:
                seen.append(e)
            time.sleep(0.05)
        tries.append({"base": [bx + dx, by + dy], "win": [wx, wy], "seen": seen, "top": top(gc)})
        if tries[-1]["top"] != until_not:
            break
    return tries
def globe(gc, **kw): return q(gc, dict({"cmd": "globe_point"}, **kw))
def dist(a, b): return math.hypot((a[0] - b[0] + math.pi) % (2 * math.pi) - math.pi, a[1] - b[1])
def pick_point(gc, avoid):
    """PICK: land >= 0.15 rad from every base / marker; rings 0.20-0.50 rad around the first base, 16 directions; 8 neighbours land"""
    c = avoid[0]
    for r in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
        for k in range(16):
            p = (c[0] + r * math.cos(2 * math.pi * k / 16), c[1] + r * math.sin(2 * math.pi * k / 16))
            if any(dist(p, b) < 0.15 for b in avoid):
                continue
            pr = globe(gc, lon=p[0], lat=p[1])
            if not pr.get("land"):
                continue
            nb = [globe(gc, lon=p[0] + dx, lat=p[1] + dy).get("land") for dx in (-0.02, 0, 0.02) for dy in (-0.02, 0, 0.02)]
            if all(nb) and 10 < pr["x"] < pr["globeW"] - 10 and 30 < pr["y"] < pr["globeH"] - 10:
                return {"lon": p[0], "lat": p[1], "x": pr["x"], "y": pr["y"], "r": r, "k": k}
    return None
def capture(b):
    out = {}
    for gc in (b.host, b.client):
        out[gc.name] = {"alive": False, "rc": gc.proc.poll() if gc.proc else None} if not alive(gc) else {
            "get_state": q(gc, {"cmd": "get_state"}), "get_coop": q(gc, {"cmd": "get_coop"}), "dialog": dlg(gc), "geo_state": census(gc),
            "battle": q(gc, {"cmd": "battle_state"}).get("phase"), "log": [ln.split("\t")[-1][:300] for ln in logl(gc)[-40:]]}
    return out
# ----- the boot and the construction steps -----
class Boot:
    def __init__(self):
        self.host = GameClient("host", None, make_user_dir("w2h80_u_host"))
        self.client = GameClient("client", None, make_user_dir("w2h80_u_client"))
        self.aff = {}
class Row:
    def __init__(self, x, b, rid):
        self.x, self.b, self.rid, self.res = x, b, rid, {}
        self.ev = {"t": now(), "cpu": cpu(), "swaps": []}
        self.n0 = [len(logl(b.host)), len(logl(b.client))] if b is not None else [0, 0]
    def cell(self, cid, ok, label): self.res[cid] = (bool(ok), label)
    def need(self, ok, what):
        if not ok: raise Stop(what)  # noqa: E701
    def finish(self, stop=None):
        self.ev["tEnd"] = now()
        if self.b is not None:
            self.ev["hostLog"], self.ev["clientLog"] = lines_since(self.b.host, self.n0[0]), lines_since(self.b.client, self.n0[1])
        self.ev["stop"] = stop
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        fails, cells = [], dict(ROWS)[self.rid]
        for cid in cells:
            miss = "precondition miss: %s" % stop if cid == cells[0] and cid.endswith("-pre") else "not reached (%s)" % stop
            ok, label = self.res.get(cid, (False, miss))
            print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, "RED" if cid in RED else "GUARD", label), flush=True)
            fails += [] if ok else [cid]
        if stop:
            print("CAPTURE %s: %s" % (self.rid, js(capture(self.b))), flush=True)
        print(("PASS %s" % self.rid) if not fails else ("FAIL %s: %s" % (self.rid, " ".join(fails))), flush=True)
        self.x.fails += fails
def bring_up(b, r):
    for gc in (b.host, b.client):
        gc.spawn()
        gc.connect(timeout=BOOT_S)
    session.HOST_LON, session.HOST_LAT = HOST_POS
    session.new_campaign(b.host, b.client, port=KEY)
    geo.slow_clock(b.host, b.client)
    time.sleep(2.0)
    ev = r.ev["boot"] = {"key": KEY, "slot": harness.HARNESS_SLOT, "drain": [str(geo.drain_popups(gc))[:120] for gc in (b.host, b.client)]}
    for gc in (b.host, b.client):
        b.aff[gc.name] = affine(cw(gc, "INTERCEPT", 0.6), cw(gc, "CANCEL", 0.6, ready=True))
    h, c = census(b.host), census(b.client)
    ev.update({"aff": b.aff, "host": h["bases"], "client": c["bases"], "t": now()})
    r.need(h["stack"] == ["GeoscapeState"] and c["stack"] == ["GeoscapeState"], "boot: both on GeoscapeState (%s, %s)" % (h["stack"], c["stack"]))
def build_base(b, r, gc, name):
    """SPARE: BASES, BUILD NEW BASE, ONE globe click at PICK, OK, NAME (keys), OK, the lift tile, GEOSCAPE (real clicks / keys)"""
    ev = r.ev["spare"] = {"bases": cw(gc, "BASES")["after"], "newBase": cw(gc, "NEW BASE")["after"]}
    r.need(top(gc) == "BuildNewBaseState", "SPARE: %s top %s after BUILD NEW BASE" % (gc.name, top(gc)))
    cc = census(gc)
    ev["pick"] = pick_point(gc, [(x[4], x[5]) for x in cc["bases"] if not x[2]] + [(x[4], x[5]) for x in cc["bases"] if x[2]])
    r.need(ev["pick"], "SPARE: no land point for PICK")
    ev["globeClick"] = click_px(gc, ev["pick"]["x"], ev["pick"]["y"], b.aff[gc.name], "BuildNewBaseState")[-1]
    r.need(top(gc) == "ConfirmNewBaseState", "SPARE: %s top %s after the globe click" % (gc.name, top(gc)))
    ev["confirmOk"] = cw(gc, "OK")["after"]
    r.need(top(gc) == "BaseNameState", "SPARE: %s top %s after confirm OK" % (gc.name, top(gc)))
    for ch in name:
        key(gc, ord(ch))
        time.sleep(0.08)
    time.sleep(0.4)
    ev["nameOk"] = cw(gc, "OK")["after"]
    r.need(top(gc) == "PlaceLiftState", "SPARE: %s top %s after the name's OK" % (gc.name, top(gc)))
    ev["lift"] = []
    for tx, ty in LIFTS:
        ev["lift"].append([tx, ty, click_px(gc, tx * 32 + 16, 8 + ty * 32 + 16, b.aff[gc.name], "PlaceLiftState", offsets=((0, 0),))[-1]["top"]])
        if top(gc) != "PlaceLiftState":
            break
        r.ev["swaps"].append("LIFT (%d, %d) did not leave PlaceLiftState" % (tx, ty))
    r.need(top(gc) != "PlaceLiftState", "SPARE: PlaceLiftState never left (%s)" % ev["lift"])
    ev["geo"] = cw(gc, "GEOSCAPE")["after"]
    r.need(top(gc) == "GeoscapeState", "SPARE: %s not back on GeoscapeState (%s)" % (gc.name, stk(gc)))
    nb = [x for x in own(census(gc)) if x[1] == name]
    r.need(len(nb) == 1, "SPARE: %r not in %s's own list once (%s)" % (name, gc.name, nb))
    return nb[0][0]
def cycle(gc): return [cw(gc, "INTERCEPT")["after"][-1:], cw(gc, "CANCEL", ready=True)["after"][-1:]]
def both(b): return {"host": census(b.host), "client": census(b.client)}
def p0(b, r, st):
    """P0: the client's geoscape init; host own [HB, SPARE], host mirrors [CB], client mirrors {HB, SPARE}; LOST = HB"""
    r.ev["p0Cycle"] = cycle(b.client)
    time.sleep(3.0)
    p = both(b)
    hown, cown = own(p["host"]), own(p["client"])
    hb = [x for x in hown if x[0] != st["spare"]]
    r.ev["P0"] = {"hostOwn": hown, "hostMir": mirrors(p["host"]), "clientOwn": cown, "clientMir": mirrors(p["client"])}
    r.need(len(hown) == 2 and len(hb) == 1 and len(cown) == 1, "P0: host own %s, client own %s" % (hown, cown))
    lb = [x for x in p["host"]["bases"] if x[0] == hb[0][0]][0]
    st.update({"lost": hb[0][0], "lostName": hb[0][1], "lostPos": [lb[4], lb[5]], "cb": cown[0][0], "cbName": cown[0][1]})
    r.ev["ids"] = dict(st)
    r.need(mir_ids(p["host"]) == [st["cb"]] and sorted(mir_ids(p["client"])) == sorted([st["lost"], st["spare"]]),
           "P0: host mirrors %s (want [CB]), client mirrors %s (want {HB, SPARE})" % (mir_ids(p["host"]), mir_ids(p["client"])))
def press_through(gc, cap=90.0):
    """real clicks until GeoscapeState (calm 1 s): an OK screen's 'OK'; a CoopState by its own button"""
    steps, t1 = [], time.time()
    while time.time() - t1 < cap:
        t = top(gc)
        if t == "GeoscapeState":
            time.sleep(1.0)
            if top(gc) == "GeoscapeState":
                break
            continue
        if t in ("LoadGameState", "SaveGameState") or (t or "").startswith("probe failed"):
            time.sleep(0.25)
            continue
        if t == "CoopState":
            d = dlg(gc)
            if d.get("backVisible") and d.get("backText"):
                steps.append([round(time.time() - t1, 2), t, d.get("code"), cw(gc, d["backText"], 0.8)["after"][-2:]])
            else:
                time.sleep(0.25)
                if not steps or steps[-1][1:3] != [t, d.get("code")]:
                    steps.append([round(time.time() - t1, 2), t, d.get("code"), "wait"])
            continue
        w = q(gc, {"cmd": "list_widgets"})
        texts = [x.get("text") for x in w.get("widgets", []) if x.get("visible") and str(x.get("type", "")).endswith("::TextButton")]
        okb = next((m for m in ("OK", "Ok") if any(m.lower() == (tx or "").strip().lower() for tx in texts)), None)
        if okb:
            session.wait_widget_ready(gc, okb, timeout=5)
            steps.append([round(time.time() - t1, 2), t, "OK", cw(gc, okb, 0.8)["after"][-2:]])
        else:
            steps.append([round(time.time() - t1, 2), t, "no OK", texts[:8]])
            time.sleep(1.0)
            if len(steps) > 3 and all(s[1] == t and s[2] == "no OK" for s in steps[-3:]):
                break
    return {"steps": steps, "secs": round(time.time() - t1, 2)}
# ----- the row -----
def row_r4(b, r, st):
    """R4: the boot, SPARE, P0, STRIP, the base defence on the emptied HB -> BaseDestroyedState, GONE, B0, HOST OK, A0 / A1 / A2"""
    h, c, ev = b.host, b.client, r.ev
    bring_up(b, r)
    st["spare"] = build_base(b, r, h, SPARE_NAME)
    p0(b, r, st)
    s0 = q(h, {"cmd": "get_soldiers"})
    hb0 = [x for x in s0.get("bases", []) if x.get("name") == st["lostName"] and not x.get("coopIcon") and not x.get("coopBaseFlag")]
    sids = [s.get("id") for s in (hb0[0].get("soldiers", []) if len(hb0) == 1 else [])]
    replies = [[sid, q(h, {"cmd": "set_soldier_dead", "soldierId": sid})] for sid in sids]
    s1 = q(h, {"cmd": "get_soldiers"})
    after = [len(x.get("soldiers", [])) for x in s1.get("bases", []) if x.get("name") == st["lostName"] and not x.get("coopIcon")]
    ev["strip"] = {"ids": sids, "replies": [[x[0], x[1].get("ok"), x[1].get("dead"), x[1].get("error")] for x in replies], "after": after}
    r.need(sids and all(x[1].get("ok") and x[1].get("dead") for x in replies) and after == [0],
           "STRIP: HB soldiers %s, replies %s, after %s (want >= 1, every ok + dead, [0])" % (sids, ev["strip"]["replies"], after))
    nh, nc = len(logl(h)), len(logl(c))  # U-mark
    ufo = q(h, UFO)
    t_send = time.time()
    reply = q(h, {"cmd": "trigger_base_defense", "ufo_id": ufo.get("ufo_id")})
    t_trig = time.time()
    gone, host_tr, gone_at, bds_at = [], [], None, None
    while time.time() - t_trig < max(GONE_S, W_BDS):
        tt = round(time.time() - t_trig, 3)
        if tt < GONE_S:
            g = q(c, {"cmd": "geo_state"})
            mids = [x.get("coopBaseId") for x in g.get("bases", []) if x.get("coopIcon")]
            present = st["lost"] in mids
            if not gone or gone[-1][1] != present:
                gone.append([tt, present, mids])
            gone_at = None if present else (gone_at if gone_at is not None else tt)
        hs = stk(h)
        if not host_tr or host_tr[-1][1] != hs:
            host_tr.append([tt, hs])
        if bds_at is None and hs[-1:] == ["BaseDestroyedState"]:
            bds_at = tt
        if bds_at is not None and tt >= GONE_S:
            break
        time.sleep(0.05)
    ev["trigger"] = {"ufo": ufo, "reply": reply, "replySecs": round(t_trig - t_send, 3), "gone": gone, "goneAt": gone_at,
                     "hostTrace": host_tr, "bdsAt": bds_at, "hostStackAtW_BDS": stk(h)}
    r.need(ufo.get("ok") and reply.get("ok") and reply.get("base") == st["lostName"], "trigger: %s (want ok, base %r)" % (reply, st["lostName"]))
    r.need(bds_at is not None and not any("BriefingState" in x[1] for x in host_tr),
           "BaseDestroyedState on the host within W_BDS (host trace %s)" % host_tr)
    r.cell("R4-pre", True, "P0 %s; STRIP %d soldiers -> %s; trigger %s; BaseDestroyedState at +%.3f s" % (ev["P0"]["hostOwn"], len(sids), after,
                                                                                                         reply, bds_at))
    st["B0"] = both(b)
    ev["hostOk"] = press_through(h)
    st["A0"] = both(b)
    t_a0 = time.time()
    ev["cpuA0"] = cpu()
    ev["A1cycle"] = cycle(c)
    time.sleep(RT_SETTLE)
    st["A1"] = both(b)
    while time.time() - t_a0 < PLUS10_S:
        time.sleep(0.25)
    st["A2"] = both(b)
    ev["sinceA0"] = round(time.time() - t_a0, 2)
    ks = ("B0", "A0", "A1", "A2")
    ev["censuses"] = {k: {"host": [x[:4] for x in st[k]["host"]["bases"]], "hostStack": st[k]["host"]["stack"],
                          "client": [x[:4] for x in st[k]["client"]["bases"]], "clientStack": st[k]["client"]["stack"]} for k in ks}
    cm = {k: mir_ids(st[k]["client"]) for k in ks}
    r.cell("R4-gone", gone_at is not None and not gone[-1][1] and all(st["lost"] not in v for v in cm.values()),
           "LOST %s gone from the client's mirrors at +%s s of T_TRIG (GONE trace %s); client mirrors at B0 / A0 / A1 / A2 %s" % (
               st["lost"], gone_at, gone, cm))
    a0, a2 = st["A0"]["host"], st["A2"]["host"]
    r.cell("R4-host", st["lost"] not in [x[0] for x in own(a0)] and mir_ids(a0) == [st["cb"]] and mir_ids(a2) == [st["cb"]]
           and not ghost(a0, st) and not ghost(a2, st), "host own at A0 %s; host mirrors at A0 %s, A2 %s (want [%s]); GHOST(host) A0 %s, A2 %s" % (
               own(a0), mir_ids(a0), mir_ids(a2), st["cb"], ghost(a0, st), ghost(a2, st)))
    sk = ev["skip"] = {"host": hits(h, SKIP_N, nh), "client": hits(c, SKIP_N, nc)}
    r.cell("R4-skip0", not sk["host"] and not sk["client"], "SKIP lines since U-mark: host %d, client %d (want 0)" % (len(sk["host"]),
                                                                                                                len(sk["client"])))
class X:  # the file's run state: failing cells, every process's alive-until-shutdown record
    def __init__(self): self.fails, self.alive = [], []
def main():
    x, crash0, b, st = X(), crashes(), None, {}
    T0[0] = time.time()
    try:
        b = Boot()
        r = Row(x, b, "R4")
        try:
            row_r4(b, r, st)
            r.finish()
        except Stop as e:
            r.finish(str(e))
        except Exception as e:  # noqa: BLE001 - an unexpected exception ends the row like a precondition miss
            r.finish("exception %s: %s" % (type(e).__name__, str(e)[:300]))
    finally:
        for gc in ((b.client, b.host) if b else ()):
            x.alive.append([gc.name, alive(gc)])
            try:
                if alive(gc):
                    gc.shutdown(expected_returncodes=OKRC)
            except Exception as e:  # noqa: BLE001
                print("FAIL shutdown %s: %s" % (gc.name, str(e)[:300]), flush=True)
                x.alive[-1][1] = False
        r, new = Row(x, None, "END"), sorted(crashes() - crash0)
        r.ev.update({"newCrash": [os.path.basename(p) for p in new], "aliveUntilShutdown": x.alive, "crashDir": harness.CRASH_DIR})
        r.cell("CRASH", not new and x.alive and all(a[1] for a in x.alive),
               "new crash files %d %s; alive until shutdown %s" % (len(new), r.ev["newCrash"][:3], x.alive))
        r.finish()
    cl = [cid for _r, cs in ROWS for cid in cs]
    print("SUMMARY W2-H80 S-A LBU: %d/%d cells pass; failing %s; wall %.1f s" % (len(cl) - len(set(x.fails)), len(cl),
                                                                               sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2
if __name__ == "__main__":
    sys.exit(main())
