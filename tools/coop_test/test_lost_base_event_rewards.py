"""test_lost_base_event_rewards.py: after a SEPARATE player loses its first base while it owns another, a geoscape
event it fires delivers its items, its craft and its soldier transfers to that player's first OWN base, the soldiers
arrive there and the player's save holds them. Vanilla treats the first base in the list as the HQ (GeoscapeEventState
eventLogic). A SEPARATE world lists the partner's base copies ("mirrors", coopBase and coopIcon true, never saved)
after the bases loaded at session start, so once a player loses its first base a mirror sits at the front: without the
fix the event's rewards go into the mirror and die with it at the next load or drop. The fix uses
SavedGame::getCoopHqBase() (the first own base) at the six HQ sites.
TWO boots on key KEY (SEPARATE, Research Sync on, mod Coop_GeoEvent_Test on both, set_seed 1 on both), each shut down
before the next:
  boot host_loses (dirs lost_base_rewards_host_loses_*): setup: the host builds HB2 (build_new_base at B2, real
    GEOSCAPE), the client lists it.
    control_event (GUARD) FIRE(host, T_INSTANT, E_INSTANT) before any loss.
         control_event-pre: S0 host list == [HB own, CB mirror, HB2 own]; start_research ok; the host's E_INSTANT
         window within EV_CAP.
         control_event-land: HB STR_PISTOL +2 and STR_INTERCEPTOR +1; HB2 ITEMSUM +0, crafts and transfers unchanged;
         mirror CB ITEMSUM +0; the host's top GeoscapeState within W_OK after the real OK.
    host_lost_base: LOSE(host, HB); FIRE(host, T_TRANSFER, E_TRANSFER); ARRIVE(host); SAVE(host,
         "lost_base_rewards_host.sav").
         host_lost_base-pre (GUARD): STRIP / spawn_ufo / trigger ok; BaseDestroyedState within W_BDS; host own bases
         == [HB2]; host bases[0] == CB with coopBase and coopIcon true (the defect's precondition); host stack
         [GeoscapeState]; start ok; the host's E_TRANSFER window.
         host_lost_base-items (FIX): HB2 ITEMSUM +2 and STR_PISTOL >= +1; mirror CB ITEMSUM +0. host_lost_base-craft
         (FIX): HB2 STR_SKYRANGER +1. host_lost_base-xfer (FIX): HB2 gains exactly 2 STR_SOLDIER transfers.
         host_lost_base-arrive (FIX): at the host's Items Arriving HB2 soldiers +2, mirror CB soldiers 0, no
         STR_SOLDIER transfer left. host_lost_base-save (FIX): the save parses; saved bases == [HB2]; HB2 ITEMSUM ==
         S0 + 2 with STR_PISTOL >= 1, STR_SKYRANGER == S0 + 1, soldiers == S0 + 2.
  boot client_loses (dirs lost_base_rewards_client_loses_*): setup: the client builds CB2 at B2, the host lists it.
    client_lost_base (the client mirror image) LOSE(client, CB); FIRE(client, T_TRANSFER, E_TRANSFER); ARRIVE(client);
         SAVE(client, "lost_base_rewards_client.sav"). client_lost_base-pre (GUARD) / -items / -craft / -xfer /
         -arrive / -save (FIX) as host_lost_base's with the roles swapped (client own bases == [CB2]; client bases[0]
         == HB, both flags true; the client's mirror HB).
  END CRASH (GUARD): no new file in harness.CRASH_DIR since the file start; every process alive until its shutdown;
    shutdown codes in OKRC.
READ(m) = geo_state + get_soldiers of m per base (ITEMSUM = the sum of `items` over ITEMS, STR_PISTOL, crafts per
type, transfers, soldier count), stack, clock, funds, the open window's geo_event_probe texts. SKIP(t, kind, want,
cap) = geo.skip_ingame_time at SKIP_IDX 4 (never a fixed short span at idx 5) with interest on GeoscapeEventState /
ItemsArrivingState, at most 12 passes, cap counted on the host clock; the hit ends it when it is t's `kind` (for a
GeoscapeEventState its geo_event_probe event.texts.title == want); any other window (the partner's own copy of the
event, or its Items Arriving) is READ and closed with a real OK and never read by a cell. FIRE(t, T, E) = S0 =
READ(t); start_research {T, cost 1, scientists 1} on t; SKIP(t, GeoscapeEventState, E, EV_CAP); S1 = READ(t) at the
open window (eventLogic ran in its constructor); real OK; t's top GeoscapeState within W_OK. ARRIVE(t) = SKIP(t,
ItemsArrivingState, -, ARRIVE_CAP); S2 = READ(t) at it; real OK. SAVE(t, f) = save_game {f} on t; the file under t's
user dir within W_SAVE; its last YAML document's bases. LOSE(m, base) = STRIP (get_soldiers + set_soldier_dead on
every soldier of m's own base), spawn_ufo, trigger_base_defense (the first own base), BaseDestroyedState within W_BDS,
the real OK until GeoscapeState, S_LOSS. The mirror's crafts are never compared (a mirror lists the partner's crafts;
the partner's own copy adds a Skyranger to them). Every TESTED press is real (OK on BaseDestroyedState, the event
window and Items Arriving; GEOSCAPE after a build); build_new_base, STRIP, spawn_ufo, trigger_base_defense,
start_research, geo_set_speed and save_game are setup test commands. No row presses BASES and no row builds a base
after a loss.
Without the fix the -items, -craft, -xfer, -arrive and -save cells of host_lost_base and client_lost_base FAIL (10 of
15); every other cell PASS. With it: 15 / 15. One EVIDENCE line per row, one PASS / FAIL line per cell, then the row
verdict; a precondition miss ends its row (later cells "not reached") with ONE CAPTURE line; a boot miss fails every
row of that boot with ONE CAPTURE line. ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_lost_base_event_rewards.py   (OXC_HARNESS_SLOT selects the harness slot)"""
import datetime, glob, json, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness, session, geo  # noqa: E401,E402
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT  # noqa: E402
import yaml  # noqa: E402

KEY = "49708"                               # lobby key (no other user in src + tools)
MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_GeoEvent_Test")
B2 = (LAND_LON + 0.06, LAND_LAT + 0.03)     # the second base (land, accepted on both machines when measured)
T_INSTANT, T_TRANSFER = "STR_GEOEV_TRG_INSTANT", "STR_GEOEV_TRG_TRANSFER"
E_INSTANT, E_TRANSFER = "STR_GEOEV_EV_INSTANT", "STR_GEOEV_EV_TRANSFER"
ITEMS = ["STR_PISTOL", "STR_RIFLE", "STR_HEAVY_CANNON", "STR_AUTO_CANNON", "STR_ROCKET_LAUNCHER", "STR_GRENADE",
         "STR_SMOKE_GRENADE", "STR_PISTOL_CLIP", "STR_RIFLE_CLIP", "STR_HC_AP_AMMO"]
UFO = {"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
       "race": "STR_SECTOID", "trajectory": "P0", "state": "flying"}
SKIP_IDX, EV_CAP, ARRIVE_CAP, SKIP_REAL = 4, 4320, 4317, 150   # ARRIVE_CAP = 3 x the measured 1,439 game min
W_OK, W_BDS, OTHER_HAS, W_SAVE, BOOT_S = 10.0, 6.0, 30.0, 5.0, 60.0
S_LOSS, S_BUILD, S_EVOK, S_ARROK = 2.0, 1.0, 1.5, 0.8
LOGN = ("[coop-ui]", "[coop] removed base: ", "delete_base", "LoadGameState")
ROWS = (("control_event", ("control_event-pre", "control_event-land")),
        ("host_lost_base", ("host_lost_base-pre", "host_lost_base-items", "host_lost_base-craft", "host_lost_base-xfer",
                            "host_lost_base-arrive", "host_lost_base-save")),
        ("client_lost_base", ("client_lost_base-pre", "client_lost_base-items", "client_lost_base-craft",
                              "client_lost_base-xfer", "client_lost_base-arrive", "client_lost_base-save")),
        ("END", ("CRASH",)))
FIX = ("host_lost_base-items", "host_lost_base-craft", "host_lost_base-xfer", "host_lost_base-arrive",
       "host_lost_base-save", "client_lost_base-items", "client_lost_base-craft", "client_lost_base-xfer",
       "client_lost_base-arrive", "client_lost_base-save")
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
T0 = [time.time()]


class Stop(Exception):  # a precondition missed: the row ends here
    pass


# ----- probes, test commands and real input -----
def js(v): return json.dumps(v, sort_keys=True, default=str)
def now(): return round(time.time() - T0[0], 3)
def rel(t): return round(t - T0[0], 3) if t else None
def alive(gc): return gc is not None and gc.proc is not None and gc.proc.poll() is None


def crashes():
    out = set()
    for d, _sub, files in os.walk(harness.CRASH_DIR):
        out.update(os.path.join(d, f) for f in files)
    return out


def q(gc, obj):
    if not alive(gc):
        return {"error": "dead rc=%s" % (gc.proc.poll() if gc and gc.proc else None)}
    try:
        return gc.cmd(obj)
    except Exception as e:  # noqa: BLE001
        return {"error": ("%s: %s" % (type(e).__name__, e))[:200]}


def stk(gc):
    r = q(gc, {"cmd": "get_state"})
    return [s.split("::")[-1] for s in r["states"]] if "states" in r else ["probe failed: %s" % r.get("error")]


def top(gc): return (stk(gc) or [None])[-1]


def census(gc):
    """geo_state rows [name, coopBase, coopIcon, lon, lat], selectedBase, clock"""
    g = q(gc, {"cmd": "geo_state"})
    bl = [[b.get("name"), bool(b.get("coopBase")), bool(b.get("coopIcon")), round(b.get("lon") or 0, 4), round(b.get("lat") or 0, 4)]
          for b in g.get("bases", [])]
    return {"bases": bl, "selected": g.get("selectedBase"), "time": g.get("time"), "error": g.get("error")}


def mir(c): return [b for b in c["bases"] if b[2]]
def own(c): return [b for b in c["bases"] if not b[1] and not b[2]]
def names(c): return [b[0] for b in c["bases"]]


def abs_min(t):
    return ((((t["year"] * 12 + t["month"]) * 31 + t["day"]) * 24 + t["hour"]) * 60 + t["minute"]) if t else None


def cpu():
    c = harness.cpu_load()
    return {"t": time.strftime("%H:%M:%S"), "cpu": harness.cpu_text(c["cpu"]), "wardogs": str(len(c["wardogs"]))}


def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def lts(ln):
    """epoch seconds of an openxcom.log line '[16-10-2026_15-08-43.457]\\t...'"""
    try:
        return datetime.datetime.strptime(ln.split("\t")[0].strip("[]"), "%d-%m-%Y_%H-%M-%S.%f").timestamp()
    except Exception:  # noqa: BLE001
        return None


def lines_since(gc, n0): return ["%s %s" % (rel(lts(ln)), ln.split("\t")[-1][:200]) for ln in logl(gc)[n0:] if any(n in ln for n in LOGN)]


def wait(pred, timeout, interval=0.05):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v or None, round(time.time() - t0, 3)
        time.sleep(interval)


def widgets(gc):
    w = q(gc, {"cmd": "list_widgets"})
    return [(z.get("text") or "")[:60] for z in w.get("widgets", []) if z.get("visible") is True and z.get("hidden") is False and
            (z.get("text") or "").strip()][:12]


def real_click(gc, text, timeout=15.0):
    t0 = time.time()
    while time.time() - t0 < timeout and alive(gc):
        ws = [w for w in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if w.get("visible") is True and w.get("hidden") is False and
              str(w.get("type", "")).endswith("TextButton") and (w.get("text") or "").strip().lower() == text.lower()]
        if ws:
            session.wait_widget_ready(gc, ws[0].get("text").strip(), timeout=5)
            c = q(gc, {"cmd": "click_widget", "match": ws[0].get("text").strip()})
            return {"text": text, "ok": bool(c.get("ok")), "s": round(time.time() - t0, 2), "tc": now()}
        time.sleep(0.05)
    return {"text": text, "ok": False, "miss": "not shown within %.0f s" % timeout, "stack": stk(gc)}


def must_click(gc, text, timeout=15.0):
    r = real_click(gc, text, timeout)
    if not r["ok"]:
        raise Stop("%s button %r not clicked: %s %s" % (gc.name, text, r.get("miss"), r.get("stack")))
    return r


def wait_top(gc, name, timeout=15.0):
    v, s = wait(lambda: top(gc) == name, timeout)
    if not v:
        raise Stop("%s top %s not %s within %.0f s" % (gc.name, stk(gc), name, timeout))
    return s


def cw(gc, match, settle=0.8):
    r = q(gc, {"cmd": "click_widget", "match": match})
    time.sleep(settle)
    return r.get("ok")


def title(gc):
    p = q(gc, {"cmd": "geo_event_probe", "names": [T_INSTANT, T_TRANSFER], "items": ITEMS, "tail": 2})
    return ((p.get("event") or {}).get("texts") or {}).get("title")


def read(gc):
    """READ(m): per base [name, coopBase, coopIcon, ITEMSUM, STR_PISTOL, items, crafts per type, transfers, soldiers]"""
    g = q(gc, {"cmd": "geo_state"})
    s = q(gc, {"cmd": "get_soldiers"})
    p = q(gc, {"cmd": "geo_event_probe", "names": [T_INSTANT, T_TRANSFER], "items": ITEMS, "tail": 2})
    sold = {(z.get("name"), bool(z.get("coopIcon"))): len(z.get("soldiers", [])) for z in s.get("bases", [])}
    bases = []
    for b in g.get("bases", []):
        it, cr = b.get("items") or {}, {}
        for c in b.get("crafts", []):
            cr[c.get("type")] = cr.get(c.get("type"), 0) + 1
        bases.append({"name": b.get("name"), "cb": bool(b.get("coopBase")), "m": bool(b.get("coopIcon")),
                      "sum": sum(int(it.get(i, 0) or 0) for i in ITEMS), "pistol": int(it.get("STR_PISTOL", 0) or 0),
                      "items": {i: it[i] for i in ITEMS if it.get(i)}, "crafts": cr,
                      "xfers": [[t.get("type"), t.get("rule"), t.get("qty"), t.get("hours")] for t in b.get("transfers", [])],
                      "sold": sold.get((b.get("name"), bool(b.get("coopIcon"))))})
    t = g.get("time") or {}
    ev = (p.get("event") or {}).get("texts") or {}
    return {"m": gc.name, "t": now(), "stack": stk(gc), "funds": g.get("funds"), "bases": bases,
            "clock": "d%s %s:%s" % (t.get("day"), t.get("hour"), str(t.get("minute")).zfill(2)) if t else None,
            "event": [ev.get("title"), ev.get("rows")] if ev else None, "error": g.get("error") or s.get("error") or p.get("error")}


def base(r, name, m):
    z = [b for b in r["bases"] if b["name"] == name and b["m"] == m]
    return z[0] if len(z) == 1 else None


def nsx(b): return sum(1 for x in (b or {}).get("xfers", []) if x[1] == "STR_SOLDIER")


def strip(gc, base_name):
    s0 = q(gc, {"cmd": "get_soldiers"})
    hb = [z for z in s0.get("bases", []) if z.get("name") == base_name and not z.get("coopIcon") and not z.get("coopBaseFlag")]
    sids = [s.get("id") for s in (hb[0].get("soldiers", []) if len(hb) == 1 else [])]
    rep = [[sid, (lambda r: [r.get("ok"), r.get("dead"), r.get("error")])(q(gc, {"cmd": "set_soldier_dead", "soldierId": sid}))] for sid in sids]
    after = [len(z.get("soldiers", [])) for z in q(gc, {"cmd": "get_soldiers"}).get("bases", []) if z.get("name") == base_name and not z.get("coopIcon")]
    return {"ids": sids, "replies": rep, "after": after, "entries": len(hb)}


def press_through(gc, cap=60.0):
    """the real OK on every screen until a bare GeoscapeState (BaseDestroyedState first)"""
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
        w = q(gc, {"cmd": "list_widgets"})
        texts = [z.get("text") for z in w.get("widgets", []) if z.get("visible") and str(z.get("type", "")).endswith("::TextButton")]
        okb = next((m for m in ("OK", "Ok") if any(m.lower() == (tx or "").strip().lower() for tx in texts)), None)
        if okb:
            session.wait_widget_ready(gc, okb, timeout=5)
            steps.append([round(time.time() - t1, 2), t, "OK", cw(gc, okb, 0.8)])
        else:
            steps.append([round(time.time() - t1, 2), t, "no OK", texts[:8]])
            time.sleep(1.0)
            if len(steps) > 3 and all(s[1] == t and s[2] == "no OK" for s in steps[-3:]):
                break
    return {"steps": steps, "secs": round(time.time() - t1, 2)}


def lose_first_base(loser, base_name):
    """LOSE(m, base): STRIP, spawn_ufo, trigger_base_defense, BaseDestroyedState within W_BDS, the real OK until GeoscapeState, S_LOSS"""
    sp = strip(loser, base_name)
    if not sp["ids"] or sp["after"] != [0] or not all(r[1][0] for r in sp["replies"]):
        raise Stop("%s STRIP of %s: %s" % (loser.name, base_name, sp))
    ufo = q(loser, UFO)
    rep = q(loser, {"cmd": "trigger_base_defense", "ufo_id": ufo.get("ufo_id")})
    if not ufo.get("ufo_id") or not rep.get("ok"):
        raise Stop("%s spawn_ufo %s / trigger_base_defense %s" % (loser.name, ufo, rep))
    v, s = wait(lambda: top(loser) == "BaseDestroyedState", W_BDS)
    st = stk(loser)
    if not v:
        raise Stop("%s: no BaseDestroyedState within %.0f s (stack %s)" % (loser.name, W_BDS, st))
    ok = press_through(loser)
    time.sleep(S_LOSS)
    return {"strip": len(sp["ids"]), "ufo": ufo.get("ufo_id"), "trigger": rep.get("base"), "bdsS": s, "stackAtBds": st, "ok": ok["steps"]}


def build_base(gc, name, pos):
    land = q(gc, {"cmd": "globe_point", "lon": pos[0], "lat": pos[1]}).get("land")
    r = q(gc, {"cmd": "build_new_base", "lon": pos[0], "lat": pos[1], "name": name})
    if not r.get("ok"):
        raise Stop("build %s at %s: %s (land %s)" % (name, pos, r, land))
    time.sleep(1.0)
    rec = {"reply": r, "pos": [round(pos[0], 4), round(pos[1], 4)], "land": land, "stack": stk(gc)}
    if top(gc) == "BasescapeState":
        rec["geoscape"] = must_click(gc, "GEOSCAPE", 10)["ok"]
    wait_top(gc, "GeoscapeState", 15)
    return rec


def other_has(gc, name, timeout=OTHER_HAS):
    v, s = wait(lambda: name in names(census(gc)), timeout, 0.25)
    if not v:
        raise Stop("%s has no base %s within %d s: %s" % (gc.name, name, timeout, census(gc)["bases"]))
    return s


def skip(b, t, kind, want, cap):
    """SKIP(t, kind, want, cap): returns {hit (t's window, left open) or None, others (windows READ and closed), passes}"""
    h, c = b.host, b.client
    t_start = abs_min(census(h)["time"])
    out = {"passes": [], "others": [], "hit": None}
    for _ in range(12):
        el = abs_min(census(h)["time"]) - t_start
        if el >= cap:
            break
        sk = geo.skip_ingame_time(h, c, cap - el, speed_idx=SKIP_IDX, interest=geo.popup("GeoscapeEventState", "ItemsArrivingState"),
                                  real_timeout=SKIP_REAL)
        hit = sk.get("hit")
        out["passes"].append([hit[0] if hit else None, sk.get("game_minutes"), now()])
        if not hit:
            if sk.get("timed_out"):
                out["timedOut"] = True
                break
            continue
        gc = h if hit[0] == h.name else c
        tp = top(gc)
        ti = title(gc) if tp == "GeoscapeEventState" else None
        if gc is t and tp == kind and (kind != "GeoscapeEventState" or ti == want):
            out["hit"] = {"m": gc.name, "top": tp, "title": ti, "elapsedMin": abs_min(census(h)["time"]) - t_start}
            return out
        r = read(gc)
        ok = must_click(gc, "OK", 10)
        time.sleep(S_EVOK if tp == "GeoscapeEventState" else S_ARROK)
        out["others"].append([gc.name, tp, ti, r["event"], r["clock"], ok["ok"], stk(gc)])
    out["elapsedMin"] = abs_min(census(h)["time"]) - t_start
    return out


def parse_save(path):
    """the last YAML document's bases: name, ITEMSUM, STR_PISTOL, craft types, soldier count"""
    with open(path, encoding="utf-8", errors="replace") as fh:
        docs = list(yaml.safe_load_all(fh))
    out = []
    for z in docs[-1].get("bases", []) or []:
        it = z.get("items") or {}
        out.append({"name": z.get("name"), "sum": sum(int(it.get(i, 0) or 0) for i in ITEMS), "pistol": int(it.get("STR_PISTOL", 0) or 0),
                    "items": {i: it[i] for i in ITEMS if it.get(i)}, "crafts": [c.get("type") for c in (z.get("crafts") or [])],
                    "soldiers": len(z.get("soldiers") or [])})
    return {"docs": len(docs), "bases": out}


def capture(b):
    out = {}
    for gc in (b.host, b.client):
        out[gc.name] = {"alive": False, "rc": gc.proc.poll() if gc.proc else None} if not alive(gc) else {
            "read": read(gc), "widgets": widgets(gc), "log": [ln.split("\t")[-1][:300] for ln in logl(gc)[-40:]]}
    return out


# ----- the boots and the rows -----
class Boot:
    def __init__(self, tag):
        self.tag, opts = tag, {"EnableResearchSync": True}
        self.host = GameClient("host", None, make_user_dir("lost_base_rewards_%s_host" % tag, mods=(MOD,),
                                                           options=opts))
        self.client = GameClient("client", None, make_user_dir("lost_base_rewards_%s_client" % tag, mods=(MOD,),
                                                               options=opts))


class Row:
    def __init__(self, x, b, rid):
        self.x, self.b, self.rid, self.res = x, b, rid, {}
        self.ev = {"t": now()}
        self.n0 = [len(logl(b.host)), len(logl(b.client))] if b is not None and alive(b.host) and alive(b.client) else [0, 0]

    def cell(self, cid, ok, label): self.res[cid] = (bool(ok), label)

    def need(self, ok, what):
        if not ok:
            raise Stop(what)

    def finish(self, stop=None, capture_it=True):
        self.ev["tEnd"] = now()
        if self.b is not None:
            self.ev["hostLog"], self.ev["clientLog"] = lines_since(self.b.host, self.n0[0]), lines_since(self.b.client, self.n0[1])
        self.ev["stop"] = stop
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        fails, cells = [], dict(ROWS)[self.rid]
        for cid in cells:
            miss = "precondition miss: %s" % stop if cid == cells[0] and cid.endswith("-pre") else "not reached (%s)" % stop
            ok, label = self.res.get(cid, (False, miss))
            print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, "FIX" if cid in FIX else "GUARD", label), flush=True)
            fails += [] if ok else [cid]
        if stop and capture_it and self.b is not None:
            print("CAPTURE %s: %s" % (self.rid, js(capture(self.b))), flush=True)
        print(("PASS %s" % self.rid) if not fails else ("FAIL %s: %s" % (self.rid, " ".join(fails))), flush=True)
        self.x.fails += fails


def bring_up(b, st):
    """Boot(KEY, tag) + SETUP: a SEPARATE campaign, speed 0, one own base and one mirror each, sync on; then the boot's
    builder (host in boot host_loses, client in boot client_loses) builds its second base at B2 (real GEOSCAPE) and the
    partner lists it"""
    st["cpu"] = cpu()
    for gc in (b.host, b.client):
        gc.spawn()
    for gc in (b.host, b.client):
        gc.connect(timeout=BOOT_S)
    st["seed"] = [q(gc, {"cmd": "set_seed", "seed": 1}).get("seed") for gc in (b.host, b.client)]
    session.new_campaign(b.host, b.client, port=KEY, campaign_mode="coop")
    for gc in (b.host, b.client):
        wait_top(gc, "GeoscapeState", 60)
        q(gc, {"cmd": "geo_set_speed", "idx": 0})
    wait(lambda: len(mir(census(b.host))) == 1 and len(mir(census(b.client))) == 1, 20, 0.25)
    h, c = census(b.host), census(b.client)
    st["sync"] = [(q(gc, {"cmd": "event_state"}).get("researchMode") or {}).get("sync") for gc in (b.host, b.client)]
    st["bases"] = {"host": h["bases"], "client": c["bases"]}
    if st["seed"] != [1, 1] or st["sync"] != [True, True]:
        raise Stop("boot: seed %s, research sync %s" % (st["seed"], st["sync"]))
    if not (stk(b.host) == ["GeoscapeState"] and stk(b.client) == ["GeoscapeState"] and len(own(h)) == 1 and len(own(c)) == 1
            and len(mir(h)) == 1 and len(mir(c)) == 1):
        raise Stop("boot: host %s, client %s" % (h["bases"], c["bases"]))
    b.HB, b.CB = own(h)[0][0], own(c)[0][0]
    builder, other, name = ((b.host, b.client, "HostBase2") if b.tag == "host_loses"
                            else (b.client, b.host, "ClientBase2"))
    st["setup"] = build_base(builder, name, B2)
    st["setup"]["otherHasS"] = other_has(other, name)
    time.sleep(S_BUILD)
    bc = census(builder)
    if [z[0] for z in own(bc)].count(name) != 1:
        raise Stop("%s's own bases %s lack %s" % (builder.name, bc["bases"], name))
    b.N = name
    st["after"] = {"bases": bc["bases"], "selected": bc["selected"]}


def fire(b, r, t, topic, want, pre):
    """FIRE(t, T, E): S0 (pre(S0) checks the row's precondition), start_research, SKIP to t's window E; S1 = READ(t) at the open window"""
    s0 = read(t)
    r.ev["S0"] = s0
    pre(s0)
    rep = q(t, {"cmd": "start_research", "topic": topic, "cost": 1, "scientists": 1})
    r.ev["start"] = rep
    r.need(rep.get("ok"), "%s start_research %s: %s" % (t.name, topic, rep))
    sk = skip(b, t, "GeoscapeEventState", want, EV_CAP)
    r.ev["skip"] = sk
    r.need(sk["hit"], "no %s window %s within %d game min (elapsed %s)" % (t.name, want, EV_CAP, sk.get("elapsedMin")))
    r.ev["S1"] = s1 = read(t)
    return s0, s1, sk


def close_window(r, t, tag):
    ok = must_click(t, "OK", 10)
    v, s = wait(lambda: top(t) == "GeoscapeState", W_OK)
    time.sleep(S_EVOK)
    r.ev[tag] = {"ok": ok["ok"], "geoS": s if v else None, "stack": stk(t)}
    return v, s


def row_control_event(b, r):
    h, lay = b.host, []

    def pre(s0):
        lay.extend([z["name"], z["cb"], z["m"]] for z in s0["bases"])
        r.need(lay == [[b.HB, False, False], [b.CB, True, True], [b.N, False, False]], "S0 host list %s (want [%s own, %s mirror, %s own])" % (
            lay, b.HB, b.CB, b.N))
    s0, s1, sk = fire(b, r, h, T_INSTANT, E_INSTANT, pre)
    r.cell("control_event-pre", True, "S0 host list %s; start ok; host %s window at %s (+%s game min)" % (
        lay, E_INSTANT, s1["clock"], sk["hit"]["elapsedMin"]))
    v, s = close_window(r, h, "ok")
    a0, a1, n0, n1 = base(s0, b.HB, False), base(s1, b.HB, False), base(s0, b.N, False), base(s1, b.N, False)
    m0, m1 = base(s0, b.CB, True), base(s1, b.CB, True)
    ic = [z["crafts"].get("STR_INTERCEPTOR", 0) for z in (a0, a1)]
    r.cell("control_event-land", a1["pistol"] - a0["pistol"] == 2 and ic[1] - ic[0] == 1 and n1["sum"] == n0["sum"]
           and n1["crafts"] == n0["crafts"]
           and n1["xfers"] == n0["xfers"] and m1["sum"] == m0["sum"] and v,
           "%s STR_PISTOL %d -> %d, STR_INTERCEPTOR %d -> %d; %s sum %d -> %d, crafts %s -> %s, transfers %d -> %d; mirror %s sum %d -> %d; "
           "GeoscapeState %s s after the OK (W_OK %.0f s); rows %s" % (b.HB, a0["pistol"], a1["pistol"], ic[0], ic[1], b.N, n0["sum"], n1["sum"],
                                                                     n0["crafts"], n1["crafts"], len(n0["xfers"]), len(n1["xfers"]), b.CB,
                                                                     m0["sum"], m1["sum"], s if v else None, W_OK, (s1["event"] or [None, None])[1]))


def row_lost(b, r, rid):
    """host_lost_base / client_lost_base: LOSE(t, its first base); FIRE(t, T_TRANSFER, E_TRANSFER); ARRIVE(t);
    SAVE(t, f)"""
    t, first, mname, f = ((b.host, b.HB, b.CB, "lost_base_rewards_host.sav") if rid == "host_lost_base"
                          else (b.client, b.CB, b.HB, "lost_base_rewards_client.sav"))
    r.ev["loss"] = loss = lose_first_base(t, first)

    def pre(s0):
        lay = [[z["name"], z["cb"], z["m"]] for z in s0["bases"]]
        ownb = [z[0] for z in lay if not z[1] and not z[2]]
        r.need(ownb == [b.N] and lay and lay[0] == [mname, True, True] and s0["stack"] == ["GeoscapeState"],
               "after the loss %s own %s (want [%s]), bases[0] %s (want [%s, True, True]), stack %s" % (
                   t.name, ownb, b.N, lay[:1], mname, s0["stack"]))
    s0, s1, sk = fire(b, r, t, T_TRANSFER, E_TRANSFER, pre)
    r.cell(rid + "-pre", True, "%s lost %s (strip %d, ufo %s, BaseDestroyedState %s s, OK %s); own [%s]; bases[0] %s mirror; stack %s; start ok; "
           "%s window at %s (+%s game min)" % (t.name, first, loss["strip"], loss["ufo"], loss["bdsS"], [z[2:] for z in loss["ok"]], b.N, mname,
                                               s0["stack"], E_TRANSFER, s1["clock"], sk["hit"]["elapsedMin"]))
    n0, n1, m0, m1 = base(s0, b.N, False), base(s1, b.N, False), base(s0, mname, True), base(s1, mname, True)
    r.cell(rid + "-items", n1["sum"] - n0["sum"] == 2 and n1["pistol"] - n0["pistol"] >= 1 and m1["sum"] == m0["sum"],
           "%s ITEMSUM %d -> %d, STR_PISTOL %d -> %d (want +2, >= +1); mirror %s ITEMSUM %d -> %d %s (want +0); window rows %s" % (
               b.N, n0["sum"], n1["sum"], n0["pistol"], n1["pistol"], mname, m0["sum"], m1["sum"], m1["items"], (s1["event"] or [None, None])[1]))
    sky = [z["crafts"].get("STR_SKYRANGER", 0) for z in (n0, n1)]
    r.cell(rid + "-craft", sky[1] - sky[0] == 1, "%s STR_SKYRANGER %d -> %d (want +1); crafts %s" % (b.N, sky[0], sky[1], n1["crafts"]))
    r.cell(rid + "-xfer", nsx(n1) - nsx(n0) == 2, "%s STR_SOLDIER transfers %d -> %d (want +2) %s; mirror %s %d -> %d" % (
        b.N, nsx(n0), nsx(n1), n1["xfers"], mname, nsx(m0), nsx(m1)))
    v, s = close_window(r, t, "ok")
    r.need(v, "%s top %s not GeoscapeState within %.0f s after the window's OK" % (t.name, stk(t), W_OK))
    ska = skip(b, t, "ItemsArrivingState", None, ARRIVE_CAP)
    r.ev["arriveSkip"] = ska
    r.ev["S2"] = s2 = read(t)
    if ska["hit"]:
        r.ev["arriveOk"] = must_click(t, "OK", 10)["ok"]
        time.sleep(S_ARROK)
    n2, m2 = base(s2, b.N, False), base(s2, mname, True)
    left = sum(nsx(z) for z in s2["bases"])
    r.cell(rid + "-arrive", ska["hit"] is not None and n2["sold"] - n0["sold"] == 2 and m2["sold"] == 0 and left == 0,
           "%s Items Arriving %s at %s (+%s game min, ARRIVE_CAP %d); %s soldiers %s -> %s (want +2); mirror %s soldiers %s (want 0); "
           "STR_SOLDIER transfers left %d" % (t.name, "came" if ska["hit"] else "NONE", s2["clock"], (ska["hit"] or {}).get("elapsedMin"),
                                              ARRIVE_CAP, b.N, n0["sold"], n2["sold"], mname, m2["sold"], left))
    rep = q(t, {"cmd": "save_game", "file": f})
    wait(lambda: glob.glob(os.path.join(t.user_dir, "**", f), recursive=True), W_SAVE, 0.1)
    found = glob.glob(os.path.join(t.user_dir, "**", f), recursive=True)
    ps, perr = None, None
    if rep.get("ok") and len(found) == 1:
        time.sleep(0.3)
        try:
            ps = parse_save(found[0])
        except Exception as e:  # noqa: BLE001
            perr = str(e)[:200]
    r.ev["save"] = {"reply": rep, "found": [os.path.relpath(p, t.user_dir) for p in found], "parsed": ps, "parseError": perr}
    sb = (ps or {}).get("bases") or []
    sn = sb[0] if len(sb) == 1 else None
    want = [n0["sum"] + 2, sky[0] + 1, n0["sold"] + 2]
    r.cell(rid + "-save", bool(ps) and [z["name"] for z in sb] == [b.N] and sn["sum"] == want[0] and sn["pistol"] >= 1
           and sn["crafts"].count("STR_SKYRANGER") == want[1] and sn["soldiers"] == want[2],
           "save_game %s, file %s, parsed %s: saved bases %s (want only %s with ITEMSUM %d, STR_PISTOL >= 1, STR_SKYRANGER %d, soldiers %d)" % (
               rep, r.ev["save"]["found"], bool(ps) if not perr else perr, sb, b.N, want[0], want[1], want[2]))


class X:  # the file's run state: failing cells, every process's alive-until-shutdown record
    def __init__(self): self.fails, self.alive = [], []


def run_boot(x, tag, rows):
    b, st = Boot(tag), {}
    try:
        try:
            bring_up(b, st)
        except Exception as e:  # noqa: BLE001 - a boot miss fails every row of the boot with ONE CAPTURE line
            r = Row(x, b, rows[0])
            r.ev["boot"] = st
            r.finish("boot miss: %s: %s" % (type(e).__name__, str(e)[:300]))
            for rid in rows[1:]:
                Row(x, None, rid).finish("boot miss", capture_it=False)
        else:
            for i, rid in enumerate(rows):
                r = Row(x, b, rid)
                if i == 0:
                    r.ev["boot"] = st
                try:
                    row_control_event(b, r) if rid == "control_event" else row_lost(b, r, rid)
                    r.finish()
                except Stop as e:
                    r.finish(str(e))
                except Exception as e:  # noqa: BLE001 - an unexpected exception ends the row like a precondition miss
                    r.finish("exception %s: %s" % (type(e).__name__, str(e)[:300]))
    finally:
        for gc in (b.client, b.host):
            x.alive.append(["%s_%s" % (tag, gc.name), alive(gc), None])
            try:
                if gc.proc is not None and alive(gc):
                    gc.shutdown(expected_returncodes=OKRC)
                x.alive[-1][2] = gc.proc.poll() if gc.proc else None
            except Exception as e:  # noqa: BLE001
                print("FAIL shutdown %s %s: %s" % (tag, gc.name, str(e)[:300]), flush=True)
                x.alive[-1][1] = False


def main():
    x, crash0 = X(), crashes()
    T0[0] = time.time()
    try:
        run_boot(x, "host_loses", ("control_event", "host_lost_base"))
        run_boot(x, "client_loses", ("client_lost_base",))
    finally:
        r, new = Row(x, None, "END"), sorted(crashes() - crash0)
        r.ev.update({"newCrash": [os.path.basename(p) for p in new], "aliveUntilShutdownRc": x.alive, "crashDir": harness.CRASH_DIR, "cpu": cpu()})
        r.cell("CRASH", not new and x.alive and all(a[1] and a[2] in OKRC for a in x.alive),
               "new crash files %d %s; [process, alive until shutdown, rc] %s" % (len(new), r.ev["newCrash"][:3], x.alive))
        r.finish()
    cl = [cid for _r, cs in ROWS for cid in cs]
    print("SUMMARY pass=%d fail=%d (lost base event rewards; failing %s; wall %.1f s)" % (
        len(cl) - len(set(x.fails)), len(set(x.fails)), sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2


if __name__ == "__main__":
    sys.exit(main())
