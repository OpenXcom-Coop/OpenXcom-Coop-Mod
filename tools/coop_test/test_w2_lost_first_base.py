"""W2-H87 (F23065; R-LF23065-1, VL-H87-1) - SEPARATE campaign: after a player loses its FIRST base while it owns another
base, the geoscape BASES button opens its own remaining base with every button, and leaving that screen reloads nothing.

A lost base is erased without re-pointing the selected-base index, and the partner's session-start mirror sits right after
the first base, so the index names the mirror. Today BASES opens that mirror as a visit (insideCoopBase true, no BUILD
FACILITIES / RESEARCH / MANUFACTURE / TRANSFER / SELL) and its GEOSCAPE loads "basehost", the player's own session-start
world: the lost base comes back with its old id, the base built since vanishes, the funds jump back to the session start,
the host's clock (and the client's, which follows it) goes back, and the two machines' maps disagree for good.

TWO boots, lobby key "49692" (user dirs w2h87_a_* / w2h87_b_*), slot from OXC_HARNESS_SLOT. Spec
rewrite/prompts/w2h87_lost_first_base_revert.md (f) (ruling R-H87-1: QH87-1 .. QH87-8 (a)); pins from
rewrite/w2h87-task0/sa/CONSTANTS.md (TASK 0 boots h87t0_r_a / _r_b red, h87t0_g_a / _g_b green). Capture lf23065-cap
(F23180-F23192); spec findings F23200-F23215. The same unit's F23069 (a lost base back on the partner's globe; R-LBH2-1,
VL-H87-2) is test_w2_lost_base_reply_ghost.py.

  boot A (host acts)
    SETUP-A host builds HostBase2 (build_new_base lever), the client lists it                    (feeds RL3-pre)
    RL-3  guard: real BASES on HostBase2, the BaseView lift (inject), real OK of the dismantle,
          real GEOSCAPE, real BASES, real GEOSCAPE                     RL3-pre RL3-loss RL3-geo RL3-bases
    BUILD3 host builds HostBase3 (lever), the client lists it                                    (feeds RL1-pre)
    RL-1  the host loses HostBase (soldiers stripped, spawn_ufo, trigger_base_defense: setup levers),
          real OK, real BASES, real GEOSCAPE        RL1-pre RL1-bases RL1-reload RL1-world RL1-cclock RL1-agree
          (LAST row of boot A: on the unchanged build its GEOSCAPE reverts the host's world)
  boot B (client acts)
    SETUP-B client builds ClientBase2 (lever), the host lists it                                 (feeds RL2-pre)
    RL-2  as RL-1 on the client               RL2-pre RL2-bases RL2-reload RL2-world RL2-clock RL2-agree
  end   shutdown of both boots                                         CRASH
RED on the unchanged build (TASK 0): RL1-bases, RL1-reload, RL1-world, RL1-cclock, RL1-agree, RL2-bases, RL2-reload,
RL2-world, RL2-agree (9 of 17). RL-3 (a second base lost: no defect), every -pre cell, RL2-clock and CRASH pass on both
builds. The reload needle is the engine log line "[coop-ui] push class OpenXcom::LoadGameState" in the actor's log.

Each row prints ONE "EVIDENCE <row>:" line, one "PASS <cell>" / "FAIL <cell>: <why>" line per cell and "ROW <row>:
PASS|FAIL". Every row runs after a failure; a precondition miss ends its row (its later cells FAIL "not reached") with ONE
CAPTURE line. Every TESTED press is a real click_widget or inject_input. WV-D95: run it to completion in the foreground.
WV-D99 / D100: ONE run is the bar, no SKIP. Exit 0 = every cell passed; 2 = at least one cell failed.
Run:  python tools/coop_test/test_w2_lost_first_base.py
"""

import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT  # noqa: E402

KEY = "49692"
B2 = (LAND_LON + 0.06, LAND_LAT + 0.03)   # second base (land, accepted; TASK 0)
B3 = (LAND_LON + 0.09, LAND_LAT + 0.03)   # third base (land, accepted; TASK 0)
LIFT = (80, 80)                           # BaseView tile (2, 2): the access lift of a lever-built base
KEY_1 = 49                                # Options::keyBaseSelect1 = SDLK_1
UFO = {"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
       "race": "STR_SECTOID", "trajectory": "P0", "state": "flying"}
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
NEEDLE = "[coop-ui] push class OpenXcom::LoadGameState"
W_BDS, GONE, DEL, POP, RELOAD, AGREE_S = 6.0, 1.0, 3.0, 10.0, 2.0, 15.0
BUILD_FAC = "BUILD FACILITIES"
ROWCELLS = (("RL-3", ("RL3-pre", "RL3-loss", "RL3-geo", "RL3-bases")),
            ("RL-1", ("RL1-pre", "RL1-bases", "RL1-reload", "RL1-world", "RL1-cclock", "RL1-agree")),
            ("RL-2", ("RL2-pre", "RL2-bases", "RL2-reload", "RL2-world", "RL2-clock", "RL2-agree")))
CELLS = [c for _, cs in ROWCELLS for c in cs] + ["CRASH"]
RESULT = {}


class Pre(Exception):
    """A fixture step missed its precondition: ends its row."""


# --------------------------------------------------------------------------- probes and presses (copied from docs rewrite/lf23065-cap/cap.py)

def alive(gc): return gc is not None and gc.proc is not None and gc.proc.poll() is None
def crashes(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "**", "crash_*"), recursive=True))


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
def inside(gc): return q(gc, {"cmd": "get_coop"}).get("insideCoopBase")


def census(gc):
    g = q(gc, {"cmd": "geo_state"})
    t = g.get("time") or {}
    return {"bases": [[b.get("coopBaseId"), b.get("name"), bool(b.get("coopIcon")), bool(b.get("coopBase"))] for b in g.get("bases", [])],
            "selected": g.get("selectedBase"), "funds": g.get("funds"),
            "clock": [t.get(k) for k in ("year", "month", "day", "hour", "minute")] if t else None}


def own_ids(c): return sorted(b[0] for b in c["bases"] if not b[2] and not b[3])
def mir_ids(c): return sorted(b[0] for b in c["bases"] if b[2])
def names(c): return [b[1] for b in c["bases"]]
def id_of(c, name): return next((b[0] for b in c["bases"] if b[1] == name and not b[2] and not b[3]), None)


def buttons(gc):
    return [w.get("text") for w in q(gc, {"cmd": "list_widgets"}).get("widgets", [])
            if w.get("visible") and not w.get("hidden") and str(w.get("type", "")).endswith("::TextButton")]


def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def loads(gc, n0): return sum(1 for ln in logl(gc)[n0:] if NEEDLE in ln)


def wait(pred, timeout, interval=0.05):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v or None, round(time.time() - t0, 3)
        time.sleep(interval)


def until(t_abs):
    time.sleep(max(0.0, t_abs - time.time()))


def real_click(gc, text, timeout=15.0):
    t0 = time.time()
    while time.time() - t0 < timeout and alive(gc):
        ws = [w for w in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if w.get("visible") is True and w.get("hidden") is False and
              (w.get("text") or "").strip().lower() == text.lower()]
        if ws:
            c = q(gc, {"cmd": "click_widget", "match": ws[0].get("text").strip()})
            return {"text": text, "ok": bool(c.get("ok"))}
        time.sleep(0.05)
    return {"text": text, "ok": False, "miss": "not shown within %.0f s" % timeout, "stack": stk(gc)}


def must_click(gc, text, timeout=15.0):
    r = real_click(gc, text, timeout)
    if not r["ok"]:
        raise Pre("%s button %r not clicked: %s %s" % (gc.name, text, r.get("miss"), r.get("stack")))
    return r


def wait_top(gc, name, timeout=POP):
    v, s = wait(lambda: top(gc) == name, timeout)
    if not v:
        raise Pre("%s top %s not %s within %.0f s" % (gc.name, stk(gc), name, timeout))
    return s


def cw(gc, match, settle=0.8):
    r = q(gc, {"cmd": "click_widget", "match": match})
    time.sleep(settle)
    return {"base": [r.get("baseX"), r.get("baseY")], "win": [r.get("winX"), r.get("winY")], "ok": r.get("ok")}


def affine(r1, r2):
    out = [(r1["win"][i] - r2["win"][i]) / (r1["base"][i] - r2["base"][i]) if r1["base"][i] != r2["base"][i] else None for i in (0, 1)]
    sc = round(out[0] or out[1], 3)
    return (sc, r1["win"][0] - sc * r1["base"][0], sc, r1["win"][1] - sc * r1["base"][1])


def scale(gc):
    a = cw(gc, "INTERCEPT")
    wait(lambda: top(gc) == "InterceptState", 5)
    session.wait_widget_ready(gc, "CANCEL")
    b = cw(gc, "CANCEL")
    if not wait(lambda: top(gc) == "GeoscapeState", 5)[0] and top(gc) == "InterceptState":
        real_click(gc, "CANCEL", 5)
        wait(lambda: top(gc) == "GeoscapeState", 5)
    return affine(a, b)


def inject(gc, sc, bx, by):
    return q(gc, {"cmd": "inject_input", "kind": "click", "x": int(round(sc[0] * bx + sc[1])), "y": int(round(sc[2] * by + sc[3]))})


def key(gc, sym): return q(gc, {"cmd": "inject_input", "kind": "key", "key": sym})


def press_through(gc, cap=60.0):
    """real OK presses until GeoscapeState (calm 1 s)"""
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
        texts = buttons(gc)
        okb = next((m for m in ("OK", "Ok") if any(m.lower() == (tx or "").strip().lower() for tx in texts)), None)
        if okb:
            session.wait_widget_ready(gc, okb, timeout=5)
            steps.append([t, "OK", cw(gc, okb, 0.8)["ok"]])
        else:
            steps.append([t, "no OK", texts[:8]])
            time.sleep(1.0)
            if len(steps) > 3 and all(s[0] == t and s[1] == "no OK" for s in steps[-3:]):
                break
    return steps


# --------------------------------------------------------------------------- setup levers (logged)

def build(x, actor, name, pos):
    """build_new_base lever; a BasescapeState it leaves on top is closed by a real GEOSCAPE; the partner lists it within 30 s"""
    other = x.client if actor is x.host else x.host
    r = q(actor, {"cmd": "build_new_base", "lon": pos[0], "lat": pos[1], "name": name})
    if not r.get("ok"):
        raise Pre("build_new_base %s at %s -> %s" % (name, pos, r))
    time.sleep(1.0)
    if top(actor) == "BasescapeState":
        must_click(actor, "GEOSCAPE", 10)
    wait_top(actor, "GeoscapeState", 15)
    if not wait(lambda: name in names(census(other)), 30, 0.25)[0]:
        raise Pre("%s does not list %s within 30 s: %s" % (other.name, name, census(other)["bases"]))
    time.sleep(1.0)
    return id_of(census(actor), name)


def lose(loser, partner, base):
    """LOSE(m, base): every soldier of base dead, spawn_ufo, trigger_base_defense; BaseDestroyedState within W_BDS; the base's id
    gone from the partner's mirrors within GONE. No OK here."""
    s0 = q(loser, {"cmd": "get_soldiers"})
    hb = [b for b in s0.get("bases", []) if b.get("name") == base[1] and not b.get("coopIcon") and not b.get("coopBaseFlag")]
    sids = [s.get("id") for s in (hb[0].get("soldiers", []) if len(hb) == 1 else [])]
    reps = [q(loser, {"cmd": "set_soldier_dead", "soldierId": sid}) for sid in sids]
    after = [len(b.get("soldiers", [])) for b in q(loser, {"cmd": "get_soldiers"}).get("bases", []) if b.get("name") == base[1] and not b.get("coopIcon")]
    if not sids or not all(r.get("ok") and r.get("dead") for r in reps) or after != [0]:
        raise Pre("STRIP %s: soldiers %s, replies %s, after %s" % (base[1], sids, reps[:2], after))
    ufo = q(loser, UFO)
    rep = q(loser, {"cmd": "trigger_base_defense", "ufo_id": ufo.get("ufo_id")})
    if not (rep.get("ok") and rep.get("base") == base[1]):
        raise Pre("trigger_base_defense: ufo %s reply %s (want ok naming %s)" % (ufo, rep, base[1]))
    v, s = wait(lambda: top(loser) == "BaseDestroyedState", W_BDS)
    if not v:
        raise Pre("%s: no BaseDestroyedState within %.0f s: %s" % (loser.name, W_BDS, stk(loser)))
    g, gs = wait(lambda: base[0] not in mir_ids(census(partner)), GONE, 0.02)
    if not g:
        raise Pre("%s still holds %s's id %s %.1f s after the BDS: %s" % (partner.name, base[1], base[0], GONE, mir_ids(census(partner))))
    return "strip=%d bdsS=%.2f goneS=%.2f" % (len(sids), s, gs)


def snap(gc):
    c = census(gc)
    return "%s sel=%s inside=%s bases=%s funds=%s clock=%s" % (stk(gc), c["selected"], inside(gc), c["bases"], c["funds"], c["clock"])


def agree(x):
    h, c = census(x.host), census(x.client)
    return own_ids(h) == mir_ids(c) and own_ids(c) == mir_ids(h), "host own %s / client mir %s; client own %s / host mir %s" % (
        own_ids(h), mir_ids(c), own_ids(c), mir_ids(h))


def watch_agree(x):
    t1, tr, last = time.time(), [], None
    while time.time() - t1 < AGREE_S:
        e = agree(x)
        if e[0] != last:
            tr.append("%.1f:%s" % (time.time() - t1, e[0]))
            last = e[0]
        time.sleep(0.5)
    return agree(x), tr


# --------------------------------------------------------------------------- rows

def row_rl3(x, ev, v):
    """SETUP-A + RL-3 (guard): HostBase2 lost by its lift dismantle; BASES / GEOSCAPE stay on HostBase without a reload"""
    h, c = x.host, x.client
    x.hb2 = build(x, h, "HostBase2", B2)
    must_click(h, "BASES", 10)
    wait_top(h, "BasescapeState")
    time.sleep(0.3)
    c0 = census(h)
    if c0["selected"] != "HostBase2" and "HostBase2" in names(c0):
        ev["key"] = KEY_1 + names(c0).index("HostBase2")
        key(h, ev["key"])
        time.sleep(0.5)
    sel, cmir = census(h)["selected"], mir_ids(census(c))
    ev["pre"] = "HB2=%s host own %s client mir %s shown %s" % (x.hb2, own_ids(census(h)), cmir, sel)
    if not (x.hb2 and x.hb2 in own_ids(census(h)) and x.hb2 in cmir and sel == "HostBase2"):
        raise Pre("HostBase2 not on both lists or not shown: %s" % ev["pre"])
    v["RL3-pre"] = (True, "")
    bv = next((z for z in q(h, {"cmd": "list_widgets"}).get("widgets", []) if (z.get("type") or "").endswith("::BaseView")), None)
    if not bv:
        raise Pre("no BaseView on the host")
    inject(h, x.sc["host"], bv["x"] + LIFT[0], bv["y"] + LIFT[1])
    wait_top(h, "DismantleFacilityState", 5)
    must_click(h, "OK", 5)
    gone, ds = wait(lambda: x.hb2 not in own_ids(census(h)) and x.hb2 not in mir_ids(census(c)), DEL, 0.05)
    wait_top(h, "BasescapeState")
    time.sleep(0.5)
    fb = census(h)["selected"]
    ev["loss"] = "goneS=%s view %s" % (ds if gone else "no", fb)
    v["RL3-loss"] = (bool(gone) and fb == x.hb[1], "HostBase2 gone within %.0f s: %s; view %r (want %r)" % (DEL, bool(gone), fb, x.hb[1]))
    n0, b0 = len(logl(h)), census(h)
    must_click(h, "GEOSCAPE", 10)
    wait_top(h, "GeoscapeState")
    time.sleep(2.0)
    g = census(h)
    ev["geo"] = "loads=%d own %s funds %s->%s clock %s->%s" % (loads(h, n0), own_ids(g), b0["funds"], g["funds"], b0["clock"], g["clock"])
    v["RL3-geo"] = (loads(h, n0) == 0 and own_ids(g) == [x.hb[0]] and (g["funds"] or 0) >= (b0["funds"] or 0)
                    and (g["clock"] or []) >= (b0["clock"] or []), ev["geo"])
    must_click(h, "BASES", 10)
    wait_top(h, "BasescapeState")
    time.sleep(0.3)
    r, ins, bt = census(h), inside(h), buttons(h)
    must_click(h, "GEOSCAPE", 10)
    wait_top(h, "GeoscapeState")
    time.sleep(1.0)
    ev["bases"] = "sel=%s inside=%s buttons=%s loads=%d" % (r["selected"], ins, bt, loads(h, n0))
    v["RL3-bases"] = (r["selected"] == x.hb[1] and ins is False and BUILD_FAC in bt and loads(h, n0) == 0, ev["bases"])


def lost_first(x, ev, v, rid, actor, partner, base, b2name):
    """RL-1 / RL-2: the actor loses its first base `base` (real OK), then real BASES and real GEOSCAPE; `b2name` = its other base"""
    pre = rid.replace("-", "") + "-pre"
    ev["lose"] = lose(actor, partner, base)
    ev["ok"] = press_through(actor)
    if top(actor) != "GeoscapeState":
        raise Pre("%s top %s after the OK" % (actor.name, stk(actor)))
    time.sleep(2.0)
    a0, p0 = census(actor), census(partner)
    b2 = id_of(a0, b2name)
    funds0, ck0 = a0["funds"], {actor.name: a0["clock"], partner.name: p0["clock"]}
    want_sel = next((b[1] for b in a0["bases"] if b[2] and b[0] == x.first[partner.name][0]), None)
    ev["after_ok"] = "own %s sel %s (partner first base %s) funds %s clocks %s" % (own_ids(a0), a0["selected"], x.first[partner.name], funds0, ck0)
    if not (b2 and own_ids(a0) == [b2] and a0["selected"] == x.first[partner.name][1] and want_sel == a0["selected"]):
        raise Pre("after the loss: %s (want own [%s], selected the partner's first base mirror)" % (ev["after_ok"], b2name))
    v[pre] = (True, "")
    p = rid.replace("-", "")
    must_click(actor, "BASES", 10)
    wait_top(actor, "BasescapeState")
    time.sleep(0.3)
    r, ins, bt = census(actor), inside(actor), buttons(actor)
    ev["bases"] = "sel=%s inside=%s buttons=%s" % (r["selected"], ins, bt)
    v[p + "-bases"] = (r["selected"] == b2name and ins is False and BUILD_FAC in bt, ev["bases"] + " (want %s, False, %s)" % (b2name, BUILD_FAC))
    n1 = len(logl(actor))
    tg = time.time()
    must_click(actor, "GEOSCAPE", 10)
    wait_top(actor, "GeoscapeState")
    until(tg + 1.0)
    w, wp = census(actor), census(partner)
    ev["world"] = "+1 s own %s funds %s (FUNDS0 %s) clock %s / partner clock %s (before %s)" % (
        own_ids(w), w["funds"], funds0, w["clock"], wp["clock"], ck0)
    until(tg + RELOAD)
    n = loads(actor, n1)
    ev["reload"] = "loads=%d top=%s" % (n, stk(actor))
    v[p + "-reload"] = (n == 0 and top(actor) == "GeoscapeState", ev["reload"])
    world = own_ids(w) == [b2] and w["funds"] == funds0
    if actor is x.host:
        v[p + "-world"] = (world and (w["clock"] or []) >= ck0["host"], ev["world"])
        v[p + "-cclock"] = ((wp["clock"] or []) >= ck0["client"], ev["world"])
    else:
        v[p + "-world"] = (world, ev["world"])
        v[p + "-clock"] = ((w["clock"] or []) >= ck0["client"] and (wp["clock"] or []) >= ck0["host"], ev["world"])
    (ok, msg), tr = watch_agree(x)
    ev["agree"] = "%s trace %s" % (msg, tr)
    v[p + "-agree"] = (ok, msg)


def row_rl1(x, ev, v):
    """BUILD3 + RL-1: the host loses HostBase (its first base) while it owns HostBase3"""
    x.hb3 = build(x, x.host, "HostBase3", B3)
    lost_first(x, ev, v, "RL-1", x.host, x.client, x.hb, "HostBase3")


def row_rl2(x, ev, v):
    """SETUP-B + RL-2: the client loses ClientBase (its first base) while it owns ClientBase2"""
    x.cb2 = build(x, x.client, "ClientBase2", B2)
    lost_first(x, ev, v, "RL-2", x.client, x.host, x.cb, "ClientBase2")


BOOTS = (("a", (("RL-3", row_rl3), ("RL-1", row_rl1))), ("b", (("RL-2", row_rl2),)))

# --------------------------------------------------------------------------- driver


class X:
    def __init__(self, tag):
        self.host = GameClient("host", None, make_user_dir("w2h87_%s_host" % tag))
        self.client = GameClient("client", None, make_user_dir("w2h87_%s_client" % tag))
        self.sc, self.first = {}, {}
        self.hb = self.cb = self.hb2 = self.hb3 = self.cb2 = None


def record(cid, ok, msg):
    RESULT[cid] = (ok, msg)
    print("%s %s%s" % ("PASS" if ok else "FAIL", cid, "" if ok else ": " + msg), flush=True)


def capture(x, why):
    out = ["why=%s" % why]
    for gc in (x.host, x.client):
        if not alive(gc):
            out.append("%s dead rc=%s" % (gc.name, gc.proc.poll() if gc.proc else None))
            continue
        out.append("%s %s log=%s" % (gc.name, snap(gc), [ln.split("\t")[-1][:160] for ln in logl(gc)[-8:]]))
    return " | ".join(out)


def bring_up(x):
    for gc in (x.host, x.client):
        gc.spawn()
    for gc in (x.host, x.client):
        gc.connect(timeout=60)
    session.new_campaign(x.host, x.client, port=KEY, campaign_mode="coop")
    for gc in (x.host, x.client):
        wait_top(gc, "GeoscapeState", 60)
        q(gc, {"cmd": "geo_set_speed", "idx": 0})
    time.sleep(2.0)
    x.sc = {"host": scale(x.host), "client": scale(x.client)}
    wait(lambda: len(mir_ids(census(x.host))) == 1 and len(mir_ids(census(x.client))) == 1, 15, 0.25)
    h, c = census(x.host), census(x.client)
    if not (stk(x.host) == ["GeoscapeState"] and stk(x.client) == ["GeoscapeState"] and len(own_ids(h)) == 1 and len(own_ids(c)) == 1
            and len(mir_ids(h)) == 1 and len(mir_ids(c)) == 1):
        raise Pre("boot: host %s, client %s" % (snap(x.host), snap(x.client)))
    x.hb = next([b[0], b[1]] for b in h["bases"] if not b[2] and not b[3])
    x.cb = next([b[0], b[1]] for b in c["bases"] if not b[2] and not b[3])
    x.first = {"host": x.hb, "client": x.cb}
    print("EVIDENCE boot: HB %s CB %s funds %s/%s clock %s scale %s" % (x.hb, x.cb, h["funds"], c["funds"], h["clock"], x.sc["host"]), flush=True)


def run_rows(x, rows):
    for rid, fn in rows:
        ev, v, miss = {}, {}, None
        try:
            fn(x, ev, v)
        except Exception as e:  # noqa: BLE001 - every row runs after a failure
            miss = "%s: %s" % (type(e).__name__, str(e)[:400])
        print("EVIDENCE %s: %s" % (rid, " ".join("%s=%s" % kv for kv in ev.items())), flush=True)
        cs = dict(ROWCELLS)[rid]
        if miss:
            print("CAPTURE %s: %s" % (rid, capture(x, miss)), flush=True)
            if cs[0] not in v:
                v[cs[0]] = (False, miss)
        for c in cs:
            record(c, *v.get(c, (False, "not reached: %s" % (miss or "no value"))))
        print("ROW %s: %s" % (rid, "PASS" if all(RESULT[c][0] for c in cs) else "FAIL"), flush=True)


def main():
    crash0, t0, shut = crashes(), time.time(), []
    try:
        for tag, rows in BOOTS:
            x = X(tag)
            try:
                try:
                    bring_up(x)
                    booted = True
                except Exception as e:  # noqa: BLE001 - a boot miss fails every row of that boot
                    booted = False
                    print("CAPTURE boot %s: %s" % (tag, capture(x, "%s: %s" % (type(e).__name__, str(e)[:300]))), flush=True)
                    for rid, _ in rows:
                        for c in dict(ROWCELLS)[rid]:
                            record(c, False, "boot %s" % tag)
                if booted:
                    run_rows(x, rows)
            finally:
                for gc in (x.client, x.host):
                    rec = [tag, gc.name, alive(gc)]
                    try:
                        if gc.proc is not None and alive(gc):
                            gc.shutdown(expected_returncodes=OKRC)
                        rec.append(gc.proc.poll() if gc.proc else None)
                    except Exception as e:  # noqa: BLE001
                        rec.append("shutdown: %s" % str(e)[:200])
                    shut.append(rec)
    finally:
        new = sorted(crashes() - crash0)
        ok = not new and len(shut) == 4 and all(r[2] is True and r[3] in OKRC for r in shut)
        print("EVIDENCE end: newCrash=%s shutdown=%s crashDir=%s" % ([os.path.basename(p) for p in new][:3], shut, harness.CRASH_DIR), flush=True)
        record("CRASH", ok, "new crash files %d %s; [boot, machine, alive until shutdown, rc] %s" % (
            len(new), [os.path.basename(p) for p in new][:3], shut))
        print("ROW end: %s" % ("PASS" if ok else "FAIL"), flush=True)
    failed = [c for c in CELLS if not RESULT.get(c, (False,))[0]]
    print("SUMMARY pass=%d fail=%d failing=%s wall=%.1f s" % (len(CELLS) - len(failed), len(failed), failed, time.time() - t0), flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
