"""W2-H87 (F23069; R-LBH2-1, VL-H87-2) - SEPARATE campaign: while a player's "base destroyed" message is open, the partner's
base request never brings the lost base back as a marker on the partner's globe (both directions).

BaseDestroyedState tells the partner at once that the base is gone (delete_base, its constructor) but erases the base from
the loser's own list only at its OK. Every co-op GeoscapeState::init sends a base request; the loser's answer lists every
own base, the lost one included, and the partner's handler re-creates the mirror and never drops one a later answer
leaves out. Today closing any window on the partner's side while the message is open brings the lost base back as a
mirror (same id, same name) that stays after the OK and after the next re-init.

ONE boot, lobby key "49693" (user dirs w2h87_g_*), slot from OXC_HARNESS_SLOT. Spec
rewrite/prompts/w2h87_lost_first_base_revert.md (f) (ruling R-H87-1: QH87-1 .. QH87-8 (a)); pins from
rewrite/w2h87-task0/sa/CONSTANTS.md (TASK 0 boots h87t0_r_g red, h87t0_g_g green). F23069 captured by h83c-red
(rewrite/w2h83-task0/sc); spec findings F23200-F23215 (F23209: the host-side ghost). The same unit's F23065 (R-LF23065-1,
VL-H87-1: losing a first base reverts the campaign) is test_w2_lost_first_base.py.

  SETUP-G host builds HostBase2, client builds ClientBase2 (build_new_base lever), each listed by the partner
  RL-4   the host loses HostBase (soldiers stripped, spawn_ufo, trigger_base_defense: setup levers) and leaves its
         BaseDestroyedState open; the client CYCLEs (real INTERCEPT, real CANCEL); the host's real OK; the client
         CYCLEs again                                                       RL4-pre RL4-open RL4-after
  RL-4c  the same with roles swapped (the client loses ClientBase, the host CYCLEs)  RL4c-pre RL4c-open RL4c-after
  end    shutdown                                                            CRASH
RED on the unchanged build (TASK 0): RL4-open, RL4-after, RL4c-open, RL4c-after (4 of 7). The ghost cells compare
coopBaseIds, never names (a ghost keeps the lost base's name).

Each row prints ONE "EVIDENCE <row>:" line, one "PASS <cell>" / "FAIL <cell>: <why>" line per cell and "ROW <row>:
PASS|FAIL". Every row runs after a failure; a precondition miss ends its row (its later cells FAIL "not reached") with ONE
CAPTURE line. Every TESTED press is a real click_widget. WV-D95: run it to completion in the foreground. WV-D99 / D100:
ONE run is the bar, no SKIP. Exit 0 = every cell passed; 2 = at least one cell failed.
Run:  python tools/coop_test/test_w2_lost_base_reply_ghost.py
"""

import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT  # noqa: E402

KEY = "49693"
B2 = (LAND_LON + 0.06, LAND_LAT + 0.03)   # the host's second base (land, accepted; TASK 0)
B2C = (LAND_LON + 0.09, LAND_LAT + 0.03)  # the client's second base (land, accepted; TASK 0)
UFO = {"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
       "race": "STR_SECTOID", "trajectory": "P0", "state": "flying"}
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
W_BDS, GONE, POP, RT_SETTLE = 6.0, 1.0, 10.0, 3.0
ROWCELLS = (("RL-4", ("RL4-pre", "RL4-open", "RL4-after")), ("RL-4c", ("RL4c-pre", "RL4c-open", "RL4c-after")))
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


def wait(pred, timeout, interval=0.05):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v or None, round(time.time() - t0, 3)
        time.sleep(interval)


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
    """the window scale per machine (the Boot of the spec's (f); CAP bring_up): INTERCEPT, CANCEL"""
    a = cw(gc, "INTERCEPT")
    wait(lambda: top(gc) == "InterceptState", 5)
    session.wait_widget_ready(gc, "CANCEL")
    b = cw(gc, "CANCEL")
    if not wait(lambda: top(gc) == "GeoscapeState", 5)[0] and top(gc) == "InterceptState":
        real_click(gc, "CANCEL", 5)
        wait(lambda: top(gc) == "GeoscapeState", 5)
    return affine(a, b)


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


def cycle(gc):
    """CYCLE(m): real INTERCEPT, real CANCEL, GeoscapeState on top (a GeoscapeState re-init: its base request), then RT_SETTLE"""
    must_click(gc, "INTERCEPT", 10)
    wait_top(gc, "InterceptState", 5)
    session.wait_widget_ready(gc, "CANCEL")
    must_click(gc, "CANCEL", 10)
    wait_top(gc, "GeoscapeState")
    time.sleep(RT_SETTLE)


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
    return "%s sel=%s inside=%s bases=%s funds=%s clock=%s" % (stk(gc), c["selected"], q(gc, {"cmd": "get_coop"}).get("insideCoopBase"),
                                                                 c["bases"], c["funds"], c["clock"])


# --------------------------------------------------------------------------- rows

def ghost(x, ev, v, rid, loser, cycler, base, keep):
    """loser loses `base` and leaves its BaseDestroyedState open; cycler CYCLEs; loser's real OK; cycler CYCLEs again.
    `keep` = the loser's other own base id (it must survive on both sides)."""
    p = rid.replace("-", "")
    if not keep:
        raise Pre("SETUP-G: the loser's second base is missing")
    ev["lose"] = lose(loser, cycler, base)
    cycle(cycler)
    ls, c1, l1 = stk(loser), census(cycler), census(loser)
    ev["open"] = "loser stack %s; %s mirror ids %s; loser own %s" % (ls, cycler.name, mir_ids(c1), own_ids(l1))
    if ls[-1:] != ["BaseDestroyedState"]:
        raise Pre("the loser's top is not BaseDestroyedState after the CYCLE: %s" % ls)
    v[p + "-pre"] = (True, "")
    v[p + "-open"] = (base[0] not in mir_ids(c1), "%s's id %s %s the %s's mirror ids %s after the CYCLE while the message is open" % (
        base[1], base[0], "in" if base[0] in mir_ids(c1) else "not in", cycler.name, mir_ids(c1)))
    ev["ok"] = press_through(loser)
    if top(loser) != "GeoscapeState":
        raise Pre("%s top %s after the OK" % (loser.name, stk(loser)))
    time.sleep(1.0)
    cycle(cycler)
    c2, l2 = census(cycler), census(loser)
    ev["after"] = "%s mirror ids %s; %s own ids %s" % (cycler.name, mir_ids(c2), loser.name, own_ids(l2))
    v[p + "-after"] = (base[0] not in mir_ids(c2) and mir_ids(c2) == own_ids(l2),
                       "after the OK and a second CYCLE: %s (lost id %s)" % (ev["after"], base[0]))


def row_rl4(x, ev, v):
    """SETUP-G + RL-4: the host loses HostBase, the client cycles while the host's message is open"""
    x.hb2 = build(x, x.host, "HostBase2", B2)
    x.cb2 = build(x, x.client, "ClientBase2", B2C)
    ev["setup"] = "HB %s CB %s HB2 %s CB2 %s" % (x.hb, x.cb, x.hb2, x.cb2)
    ghost(x, ev, v, "RL-4", x.host, x.client, x.hb, x.hb2)


def row_rl4c(x, ev, v):
    """RL-4c: the client loses ClientBase, the host cycles while the client's message is open"""
    ghost(x, ev, v, "RL-4c", x.client, x.host, x.cb, x.cb2)


ROWS = (("RL-4", row_rl4), ("RL-4c", row_rl4c))

# --------------------------------------------------------------------------- driver


class X:
    def __init__(self):
        self.host = GameClient("host", None, make_user_dir("w2h87_g_host"))
        self.client = GameClient("client", None, make_user_dir("w2h87_g_client"))
        self.hb = self.cb = self.hb2 = self.cb2 = None
        self.sc = {}


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
    print("EVIDENCE boot: HB %s CB %s funds %s/%s clock %s" % (x.hb, x.cb, h["funds"], c["funds"], h["clock"]), flush=True)


def main():
    crash0, t0, shut, x = crashes(), time.time(), [], None
    try:
        x = X()
        try:
            bring_up(x)
            booted = True
        except Exception as e:  # noqa: BLE001 - a boot miss fails every row
            booted = False
            print("CAPTURE boot: %s" % capture(x, "%s: %s" % (type(e).__name__, str(e)[:300])), flush=True)
            for c in CELLS[:-1]:
                record(c, False, "boot")
        if booted:
            for rid, fn in ROWS:
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
    finally:
        if x is not None:
            for gc in (x.client, x.host):
                rec = [gc.name, alive(gc)]
                try:
                    if gc.proc is not None and alive(gc):
                        gc.shutdown(expected_returncodes=OKRC)
                    rec.append(gc.proc.poll() if gc.proc else None)
                except Exception as e:  # noqa: BLE001
                    rec.append("shutdown: %s" % str(e)[:200])
                shut.append(rec)
        new = sorted(crashes() - crash0)
        ok = not new and len(shut) == 2 and all(r[1] is True and r[2] in OKRC for r in shut)
        print("EVIDENCE end: newCrash=%s shutdown=%s crashDir=%s" % ([os.path.basename(p) for p in new][:3], shut, harness.CRASH_DIR), flush=True)
        record("CRASH", ok, "new crash files %d %s; [machine, alive until shutdown, rc] %s" % (
            len(new), [os.path.basename(p) for p in new][:3], shut))
        print("ROW end: %s" % ("PASS" if ok else "FAIL"), flush=True)
    failed = [c for c in CELLS if not RESULT.get(c, (False,))[0]]
    print("SUMMARY pass=%d fail=%d failing=%s wall=%.1f s" % (len(CELLS) - len(failed), len(failed), failed, time.time() - t0), flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
