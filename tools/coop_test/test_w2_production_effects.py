"""W2-H16g (F6711; D226 a; Q1 a .. Q6 a; R-H16g-1): each unit a SHARED production makes reaches the replica in the hour the
host makes it - intermediate units, the last unit counted once, a spawned soldier (owned by the player who started the
production), personnel / delivery / random outputs, a craft with a transfer time, fallback engineers. Spec docs
rewrite/prompts/w2h16g_production_soldier.md (e)-(f); TASK 0 rewrite/w2h16g-task0/CONSTANTS.md, its ten changes applied
(R-H16g-T0-1). Lever (test-only, read-only): prod_fx_probe. Real starts: manufacture_start (the real ManufactureInfoState,
SHARED man_start) and shared_cmd man_start (fallback). Boot A (SHARED): H16g-1..6 (H16g-6 last: its drift is never
repaired); Boot B (SEPARATE): H16g-7. Row frame: S0 (both probes agree) -> staging -> roll-to-unit (speed 1 until the host's
probe shows the row's change) -> hold (host SoldiersState: no heartbeat, the host's clock stops) -> window (both probes every
0.25 s for 3 s; the row's cells read at the FIRST sample) -> release (speed 0 on both, host close_screens, drain both; on a
row whose cells passed, the client's `requests` stays R0 for 4 s). RED (commit 1): H16g-1..6 fail on their named cells,
H16g-7 passes; GREEN: all pass. "G:" cells are guards (CAPTURE on a miss). Never `mismatches` (F5510). EVIDENCE then
PASS / FAIL per row; ONE run; exit 0 only if all pass, else 2.
"""

import json
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_ProdFx_Test")
BOOT_A = ("w2h16ga", (49388, 49389, 47368))     # SHARED; lobby 47368 (F7301)
BOOT_B = ("w2h16gb", (49390, 49391, 47370))     # SEPARATE; lobby 47370
ROCKETS, SOLDIER, SCIENTIST, DELIVERY, RANDOM, CRAFT, FALLBACK = ("STR_H16G_" + n for n in (
    "ROCKETS", "SOLDIER", "SCIENTIST", "DELIVERY", "RANDOM", "CRAFT", "FALLBACK"))
SR, LR, INT = "STR_SMALL_ROCKET", "STR_LARGE_ROCKET", "STR_INTERCEPTOR"
IDS = ("STR_SOLDIER", INT)       # change 2: only the counters a production moves (host UFO generation moves others)
HANGAR = (4, 0)                  # change 8: TASK 0 (v), accepted at index 9
S0_S, ROLL_S, ROLL_I, WIN_S, WIN_I, POST_S, UI_S = 20.0, 30.0, 0.1, 3.0, 0.25, 4.0, 5.0
GEO, SS = "GeoscapeState", "SoldiersState"


class GuardMiss(Exception):
    """A guard failed: the row ends after its CAPTURE line."""


def short(e, n=500):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."


def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while not (last := pred()) and time.time() - t0 < timeout:
        time.sleep(interval)
    return bool(last), last


def pick(d, *keys): return {k: d.get(k) for k in keys}  # noqa: E704
def stack(gc): return session.states_stripped(gc)  # noqa: E704
def top(gc): return (stack(gc) or [""])[-1]  # noqa: E704
def rs(gc): return pick(gc.cmd({"cmd": "shared_resync_stats"}), "requests", "pending")  # noqa: E704
def ss(gc): return pick(gc.cmd({"cmd": "shared_stats"}), "cmd", "okCount", "failCount", "applyCount", "lastFail")  # noqa: E704
def pf(gc): return gc.cmd({"cmd": "prod_fx_probe"})  # noqa: E704
def tp(gc): return gc.cmd({"cmd": "transform_probe"})  # noqa: E704
def st(p, k=SR): return (p.get("stores") or {}).get(k, 0)  # noqa: E704
def ids(p): return {k: (p.get("ids") or {}).get(k) for k in IDS}  # noqa: E704
def prod(p, name): return ([q for q in p.get("productions") or [] if q.get("name") == name] or [None])[0]  # noqa: E704
def trs(p, hours=True): return [t if hours else {k: v for k, v in t.items() if k != "hours"} for t in p.get("transfers") or []]  # noqa: E704,E501
def new_tr(p0, p): return trs(p)[len(p0.get("transfers") or []):]  # noqa: E704


def view(p):
    """What S0 compares (spec (f) row frame): funds, stores, transfers WITHOUT hours (change 3: the replica's transfer hours
    never advance), crafts, engineers, the production counters (change 2)."""
    return {"funds": p.get("funds"), "stores": p.get("stores"), "transfers": trs(p, False), "crafts": p.get("crafts"),
            "engineers": p.get("engineers"), "ids": ids(p)}


def slim(p, base=None):
    """EVIDENCE form of one prod_fx_probe: every field; with `base` the stores shrink to the keys that differ from it."""
    if not isinstance(p, dict) or not p.get("ok"):
        return p
    d = pick(p, "funds", "score", "ids", "engineers", "availableEngineers", "scientists", "crafts", "transfers", "productions")
    d["top"] = str(p.get("top", "")).replace("class OpenXcom::", "")
    s, b = p.get("stores") or {}, (base or {}).get("stores") or {}
    if base is None:
        d["stores"] = s
    else:
        d["storesDelta"] = {k: [b.get(k, 0), s.get(k, 0)] for k in sorted(set(s) | set(b)) if s.get(k, 0) != b.get(k, 0)}
    return d


class Row:
    def __init__(self, rid):
        self.rid, self.t0, self.ev, self.fails, self.passed = rid, time.time(), {}, [], []
        self.p0, self.R0 = None, None

    def cell(self, name, ok, detail=""):
        (self.passed.append(name) if ok else self.fails.append(f"{name}: {detail}"))
        return ok


def capture(x, tag):
    """FIXTURE-STOP dump (STOP-IF 3): both machines' prod_fx_probe, transform_probe, shared_stats, shared_resync_stats, stack."""
    cap = {}
    for gc in (x.host, x.client):
        try:
            cap[gc.name] = {"stack": stack(gc), "prod_fx_probe": pf(gc), "transform_probe": tp(gc),
                            "shared_stats": gc.cmd({"cmd": "shared_stats"}),
                            "shared_resync_stats": gc.cmd({"cmd": "shared_resync_stats"})}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {tag}: {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def guard(r, x, name, ok, detail):
    if r.cell("G:" + name, ok, detail):
        return
    capture(x, f"{r.rid} (guard {name})")
    raise GuardMiss(f"guard {name}")


def speed(x, idx):
    """geo_set_speed on each machine directly (works with a popup on top, R-H18-1); host first, as geo._apply_speed."""
    return {gc.name: pick(gc.cmd({"cmd": "geo_set_speed", "idx": idx}), "ok", "error") for gc in (x.host, x.client)}


def drain(gc):
    try:
        return geo.drain_popups(gc)[0]
    except Exception as e:
        return short(e)


def s0(r, x, tag="S0"):
    """Row frame S0: <= 20 s until both prod_fx_probe agree on the view, no restream is pending and both stand on the
    geoscape (a leftover popup is drained). On the red build the previous row's drift is repaired by the restream first.
    R0 = both `requests` (the window's guard; never `mismatches`)."""
    h, c = x.host, x.client
    t0, last, drained = time.time(), {}, []

    def agreed():
        if rs(c)["pending"]:
            return None
        for gc in (h, c):
            if top(gc) != GEO:
                drained.append([gc.name, drain(gc)])
                return None
        last["host"], last["client"] = pf(h), pf(c)
        return dict(last) if view(last["host"]) == view(last["client"]) else None
    ok, p = wait_until(agreed, S0_S, 0.25)
    d = {"agreeS": round(time.time() - t0, 2), "drained": drained}
    r.ev[tag] = d
    guard(r, x, f"{tag} agreement", ok, f"not agreed in {d['agreeS']} s; stacks {stack(h)} / {stack(c)}; host "
          f"{view(last.get('host') or {})} / client {view(last.get('client') or {})}")
    r.R0 = {gc.name: rs(gc)["requests"] for gc in (h, c)}
    r.p0 = p
    d.update(R0=r.R0, host=slim(p["host"]), client=slim(p["client"], p["host"]))
    return p


def listed(r, x, names, assigned, tag):
    """G: every start is listed on both machines with its assigned engineers (and both funds equal)."""
    def both():
        ph, pc = pf(x.host), pf(x.client)
        ok = all((prod(p, n) or {}).get("assigned") == assigned for p in (ph, pc) for n in names) and ph.get("funds") == pc.get("funds")
        return {"host": ph, "client": pc} if ok else None
    ok, p = wait_until(both, UI_S)
    q = p or {gc.name: pf(gc) for gc in (x.host, x.client)}
    r.ev[tag] = {"productions": {k: [prod(v, n) for n in names] for k, v in q.items()}, "funds": {k: v.get("funds") for k, v in q.items()}}
    guard(r, x, tag, ok, f"{names} not listed on both with assigned {assigned} (funds equal): {r.ev[tag]}")
    return q


def progress(r, x, names, spent):
    """set_production_progress on both machines, client first (S25)."""
    out = []
    for gc in (x.client, x.host):
        for n in names:
            v = gc.cmd({"cmd": "set_production_progress", "item": n, "timeSpent": spent})
            out.append([gc.name, n, pick(v, "ok", "found", "error")])
    r.ev[f"progress {spent}"] = out
    guard(r, x, f"progress {spent}", all(o[2].get("found") is True for o in out), f"{out}")


def roll(r, x, pred, what):
    """TASK 0 roll-to-unit: speed 1 on both; the host's probe every 0.1 s until `pred`; then the hold at once (host
    open_screen soldiers: no heartbeat, the host's clock stops)."""
    h = x.host
    if top(h) != GEO:                       # a late completion window would stop the host's clock
        r.ev["preRollDrain"] = drain(h)
    sp, t0 = speed(x, 1), time.time()
    ok, q = wait_until(lambda: (lambda p: p if pred(p) else None)(pf(h)), ROLL_S, ROLL_I)
    o = h.cmd({"cmd": "open_screen", "screen": "soldiers"})
    r.ev["roll"] = {"what": what, "s": round(time.time() - t0, 2), "speed1": sp, "hold": pick(o, "ok", "error")}
    guard(r, x, "roll", ok, f"no {what} on the host in {ROLL_S} s: {slim(pf(h), r.p0['host'])}")
    guard(r, x, "hold", o.get("ok") is True and wait_until(lambda: top(h) == SS, UI_S)[0], f"{o}; stack {stack(h)}")


def window(r, x, soldiers=False):
    """Both probes every ~0.25 s for 3 s; G: the client's `requests` stays R0 throughout. Returns the FIRST sample (the
    row's cells read there, change 7); `soldiers` adds both transform_probe to it."""
    h, c, t0, n, reqs, first = x.host, x.client, time.time(), 0, [], None
    while time.time() - t0 < WIN_S:
        smp = {"t": round(time.time() - t0, 2), "host": pf(h), "client": pf(c), "req": rs(c)["requests"]}
        if first is None:
            first = smp
            if soldiers:
                first["tp"] = {gc.name: tp(gc) for gc in (h, c)}
        reqs.append(smp["req"])
        n += 1
        time.sleep(WIN_I)
    r.ev["window"] = {"samples": n, "requests": reqs, "firstT": first["t"], "host": slim(first["host"], r.p0["host"]),
                      "client": slim(first["client"], r.p0["client"]), "stacks": {gc.name: stack(gc) for gc in (h, c)}}
    guard(r, x, "window requests flat", all(q == r.R0["client"] for q in reqs), f"client requests {reqs} (R0 {r.R0['client']})")
    return first


def release(r, x):
    """Speed 0 on both (change 5), host close_screens, drain both (change 6: the ProductionCompleteState windows). On a row
    whose cells passed: the client's `requests` stays R0 for 4 s (no repair restream)."""
    h, c = x.host, x.client
    r.ev["speed0"] = speed(x, 0)
    t0 = time.time()
    r.ev["close"] = pick(h.cmd({"cmd": "close_screens"}), "popped", "refused")
    r.ev["queuedWindow"] = wait_until(lambda: top(h) != GEO, 0.5, 0.05)[0]   # further completions surface after the pop
    r.ev["drain"] = {gc.name: drain(gc) for gc in (h, c)}
    if not r.fails:
        reqs = []
        while time.time() - t0 < POST_S:
            reqs.append(rs(c)["requests"])
            time.sleep(0.25)
        r.cell("noRepair", all(q == r.R0["client"] for q in reqs), f"client requests {reqs} in {POST_S} s after the release "
               f"(R0 {r.R0['client']}): the replica needed a repair restream")
    r.ev["end"] = {gc.name: slim(pf(gc), r.p0[gc.name]) for gc in (h, c)}
    r.ev["requestsEnd"] = {gc.name: rs(gc)["requests"] for gc in (h, c)}


def row_1(r, x):
    """An intermediate unit (stock, F7293): ROCKETS e2 q3 from the client; unit 1 completes, unit 2 is paid."""
    p0 = s0(r, x)
    K, F = st(p0["host"]), p0["host"]["funds"]
    x.K = K
    r.ev["client start"] = pick(x.client.cmd({"cmd": "manufacture_start", "item": ROCKETS, "engineers": 2, "qty": 3}), "ok", "sent", "error")
    q = listed(r, x, [ROCKETS], 2, "listed")
    Fp = q["host"]["funds"]
    progress(r, x, [ROCKETS], 8)
    roll(r, x, lambda p: st(p) >= K + 1, "unit 1")
    e = window(r, x)
    h, c = e["host"], e["client"]
    r.ev["values"] = {"K": K, "F": F, "Fprime": Fp, "rockets": [st(h), st(c)], "funds": [h["funds"], c["funds"]]}
    guard(r, x, "host unit", st(h) == K + 1 and h["funds"] == Fp - 1000, f"host rockets {st(h)} (want K+1 = {K + 1}), funds "
          f"{h['funds']} (want F'-1000 = {Fp - 1000})")
    r.cell("unitReached", st(c) == K + 1 and c["funds"] == h["funds"], f"client rockets {st(c)} (want K+1 = {K + 1}), funds "
           f"{c['funds']} (host {h['funds']}): a finished unit stays on the host until the production ends")
    release(r, x)


def row_2(r, x):
    """The end counts once (stock): progress 28 makes unit 3 only (change 1: host K + 2), the production ends."""
    p0 = s0(r, x)
    K1 = st(p0["host"])
    progress(r, x, [ROCKETS], 28)
    roll(r, x, lambda p: st(p) >= K1 + 1, "last unit")
    e = window(r, x)
    h, c = e["host"], e["client"]
    K = getattr(x, "K", None)
    r.ev["values"] = {"K": K, "K1": K1, "rockets": [st(h), st(c)], "funds": [h["funds"], c["funds"]],
                      "productions": [prod(h, ROCKETS), prod(c, ROCKETS)]}
    guard(r, x, "host end", st(h) == K1 + 1 and prod(h, ROCKETS) is None, f"host rockets {st(h)} (want {K1 + 1}), production "
          f"{prod(h, ROCKETS)} (want gone)")
    r.cell("endOnce", st(c) == st(h) and prod(c, ROCKETS) is None and c["funds"] == h["funds"], f"client rockets {st(c)} / host "
           f"{st(h)} (row-1 K {K}), client production {prod(c, ROCKETS)}, funds {c['funds']}/{h['funds']}: the replica counts "
           f"the production twice")
    release(r, x)


def row_3(r, x):
    """A spawned soldier (F6711): SOLDIER e1 q1 from the client; owner = the starting player's seat (R-H16g-1)."""
    p0 = s0(r, x)
    n0 = ids(p0["host"])["STR_SOLDIER"]
    r.ev["client start"] = pick(x.client.cmd({"cmd": "manufacture_start", "item": SOLDIER, "engineers": 1, "qty": 1}), "ok", "sent", "error")
    listed(r, x, [SOLDIER], 1, "listed")
    progress(r, x, [SOLDIER], 9)
    T0 = len(p0["host"].get("transfers") or [])
    roll(r, x, lambda p: len(p.get("transfers") or []) > T0, "soldier transfer")
    e = window(r, x, soldiers=True)
    h, c = e["host"], e["client"]
    nh, nc = new_tr(p0["host"], h), new_tr(p0["client"], c)
    sid = nh[0].get("soldierId") if nh else None
    one = {k: ([s for s in v.get("soldiers") or [] if s.get("id") == sid and s.get("where") == "transfer"] or [{}])[0]
           for k, v in e["tp"].items()}
    want = x.seat["client"]
    r.ev["values"] = {"newTransfers": {"host": nh, "client": nc}, "counters": [ids(h)["STR_SOLDIER"], ids(c)["STR_SOLDIER"]],
                      "S0counter": n0, "soldier": one, "wantOwner": want}
    guard(r, x, "host soldier", len(nh) == 1 and nh[0].get("kind") == "soldier" and nh[0].get("hours") == 24 and sid == n0
          and ids(h)["STR_SOLDIER"] == n0 + 1, f"host new transfers {nh}; counter {ids(h)['STR_SOLDIER']} (S0 {n0}; want a "
          f"soldier transfer 24 h with id {n0}, counter {n0 + 1})")
    r.cell("soldierOnBoth", nc == nh and ids(c)["STR_SOLDIER"] == ids(h)["STR_SOLDIER"] and bool(one["client"])
           and pick(one["client"], "name", "type", "nationality", "rank", "stats") == pick(one["host"], "name", "type", "nationality", "rank", "stats"),
           f"client new transfers {nc} / host {nh}; counters {r.ev['values']['counters']}; transform_probe soldier {sid} host "
           f"{pick(one['host'], 'name', 'nationality', 'stats')} / client {pick(one['client'], 'name', 'nationality', 'stats')}: "
           f"a soldier made by a production exists only on the host")
    owners = [t.get("soldierOwner") for t in nh + nc]
    r.cell("owner", len(owners) == 2 and all(o == want for o in owners), f"soldier owners host {[t.get('soldierOwner') for t in nh]}"
           f" / client {[t.get('soldierOwner') for t in nc]} (want the starter's seat {want} on both, R-H16g-1): the produced "
           f"soldier belongs to nobody")
    release(r, x)


def row_4(r, x):
    """Personnel, a delivery and a random item (mod): host starts SCIENTIST, DELIVERY, RANDOM (e1 q1 each)."""
    p0 = s0(r, x)
    names = [SCIENTIST, DELIVERY, RANDOM]
    r.ev["host starts"] = [pick(x.host.cmd({"cmd": "manufacture_start", "item": n, "engineers": 1, "qty": 1}), "ok", "sent", "error")
                           for n in names]
    listed(r, x, names, 1, "listed")
    progress(r, x, names, 9)
    T0 = len(p0["host"].get("transfers") or [])
    roll(r, x, lambda p: len(p.get("transfers") or []) >= T0 + 2, "two transfers")
    e = window(r, x)
    h, c = e["host"], e["client"]
    nh, nc = new_tr(p0["host"], h), new_tr(p0["client"], c)
    rk0, rk = st(p0["host"]) + st(p0["host"], LR), st(h) + st(h, LR)
    r.ev["values"] = {"newTransfers": {"host": nh, "client": nc}, "rocketsSmallLarge": {"S0": [st(p0["host"]), st(p0["host"], LR)],
                      "host": [st(h), st(h, LR)], "client": [st(c), st(c, LR)]}}
    got = sorted([t.get("kind"), t.get("item"), t.get("qty"), t.get("hours")] for t in nh)
    guard(r, x, "host outputs", got == [["item", SR, 2, 12], ["scientist", "", 1, 24]] and rk == rk0 + 1, f"host new transfers "
          f"{got} (want a scientist 24 h and {SR} x2 12 h); host rockets small+large {rk0} -> {rk} (want +1, the random item)")
    r.cell("outputsOnBoth", nc == nh and c.get("stores") == h.get("stores"), f"client new transfers {nc} / host {nh}; stores "
           f"delta client {slim(c, h).get('storesDelta')}: personnel, delivery and random item are never rebuilt on the replica")
    release(r, x)


def row_5(r, x):
    """A craft with a transfer time (mod): the hangar at (4, 0) first (change 8), then CRAFT e1 q1 from the client."""
    h, c = x.host, x.client
    s0(r, x, "S0pre")                       # the previous row's repair lands before the hangar is staged

    def hangar(gc):
        fs = [f for b in (gc.cmd({"cmd": "geo_state"}).get("bases") or [])[:1] for f in b.get("facilities") or []]
        return ([i for i, f in enumerate(fs) if f.get("type") == "STR_HANGAR" and (f.get("x"), f.get("y")) == HANGAR] or [None])[0]
    r.ev["fac_build"] = pick(h.cmd({"cmd": "fac_build", "facility": "STR_HANGAR", "x": HANGAR[0], "y": HANGAR[1]}), "ok", "error")
    ok = wait_until(lambda: hangar(h) is not None and hangar(c) is not None, UI_S)[0]
    guard(r, x, "hangar listed", ok, f"hangar at {HANGAR} host {hangar(h)} / client {hangar(c)}; stacks {stack(h)} / {stack(c)}")
    bt = [[gc.name, pick(gc.cmd({"cmd": "set_facility_build_time", "baseId": 0, "index": hangar(gc), "time": 0}), "ok", "type",
                         "x", "y", "buildTime")] for gc in (c, h)]
    r.ev["buildTime0"] = bt
    guard(r, x, "hangar built", all(b[1].get("ok") and b[1].get("type") == "STR_HANGAR" for b in bt), f"{bt}")
    p0 = s0(r, x)
    i0 = ids(p0["host"])[INT]
    r.ev["client start"] = pick(c.cmd({"cmd": "manufacture_start", "item": CRAFT, "engineers": 1, "qty": 1}), "ok", "sent", "error")
    listed(r, x, [CRAFT], 1, "listed")
    progress(r, x, [CRAFT], 9)
    T0 = len(p0["host"].get("transfers") or [])
    roll(r, x, lambda p: len(p.get("transfers") or []) > T0, "craft transfer")
    e = window(r, x)
    ph, pc = e["host"], e["client"]
    nh, nc = new_tr(p0["host"], ph), new_tr(p0["client"], pc)
    r.ev["values"] = {"newTransfers": {"host": nh, "client": nc}, "crafts": {"host": ph.get("crafts"), "client": pc.get("crafts")},
                      "ids": [ids(ph)[INT], ids(pc)[INT]], "S0id": i0}
    guard(r, x, "host craft transfer", len(nh) == 1 and pick(nh[0], "kind", "craftType", "craftId", "hours") == {
        "kind": "craft", "craftType": INT, "craftId": i0, "hours": 24} and ph.get("crafts") == p0["host"].get("crafts")
        and ids(ph)[INT] == i0 + 1, f"host new transfers {nh} (want craft {INT} id {i0} 24 h); crafts {ph.get('crafts')}; "
        f"ids {INT} {ids(ph)[INT]} (want {i0 + 1})")
    r.cell("craftTransfer", nc == nh and pc.get("crafts") == ph.get("crafts") and ids(pc)[INT] == ids(ph)[INT], f"client new "
           f"transfers {nc} / host {nh}; client crafts {pc.get('crafts')} / host {ph.get('crafts')}; ids {INT} "
           f"{r.ev['values']['ids']}: the craft lands in the replica's hangar instead of a transfer")
    release(r, x)


def row_6(r, x):
    """Fallback engineers (last in Boot A: engineers are not checksummed, so this drift is never repaired)."""
    p0 = s0(r, x)
    r.ev["host shared_cmd"] = pick(x.host.cmd({"cmd": "shared_cmd", "jcmd": "man_start", "baseId": 0, "payload": {
        "item": FALLBACK, "engineers": 0, "qty": 1, "infinite": False, "sell": False, "fallback": True}}), "ok", "error")
    listed(r, x, [FALLBACK], 0, "listed")
    roll(r, x, lambda p: ((prod(p, FALLBACK) or {}).get("assigned") or 0) > 0, "fallback assignment")
    e = window(r, x)
    h, c = e["host"], e["client"]
    a = [(prod(h, FALLBACK) or {}).get("assigned"), (prod(c, FALLBACK) or {}).get("assigned")]
    r.ev["values"] = {"assigned": a, "engineers": [h.get("engineers"), c.get("engineers")], "S0engineers": p0["host"].get("engineers")}
    guard(r, x, "host fallback", (a[0] or 0) > 0 and h.get("engineers") < p0["host"].get("engineers"), f"host assigned {a[0]}, "
          f"engineers {p0['host'].get('engineers')} -> {h.get('engineers')} (want assigned > 0, engineers lower)")
    r.cell("fallbackOnBoth", a[1] == a[0] and c.get("engineers") == h.get("engineers"), f"assigned host/client {a}, engineers "
           f"{r.ev['values']['engineers']}: fallback engineers stay on the host")
    release(r, x)


def row_7(r, x):
    """SEPARATE steps its own production (guard row): the client's own ROCKETS e2 q1, progress 8 on the client only."""
    h, c = x.host, x.client
    guard(r, x, "start", wait_until(lambda: top(h) == GEO and top(c) == GEO, S0_S, 0.2)[0], f"stacks {stack(h)} / {stack(c)}")
    r.ev["speed0"] = speed(x, 0)
    p0, h0, s1 = pf(c), pf(h), {gc.name: ss(gc) for gc in (h, c)}
    k0 = st(p0)
    r.ev["S0"] = {"client": slim(p0), "host": slim(h0, p0), "shared_stats": s1}
    r.ev["client start"] = pick(c.cmd({"cmd": "manufacture_start", "item": ROCKETS, "engineers": 2, "qty": 1}), "ok", "sent", "error")
    guard(r, x, "listed", wait_until(lambda: (prod(pf(c), ROCKETS) or {}).get("assigned") == 2, UI_S)[0], f"client {slim(pf(c), p0)}")
    v = c.cmd({"cmd": "set_production_progress", "item": ROCKETS, "timeSpent": 8})
    guard(r, x, "progress 8", v.get("found") is True, f"{v}")
    r.ev["speed1"], t0 = speed(x, 1), time.time()
    ok = wait_until(lambda: st(pf(c)) >= k0 + 1, ROLL_S, ROLL_I)[0]
    r.ev["roll"], r.ev["speed0 after"] = round(time.time() - t0, 2), speed(x, 0)
    p1, h1, s2 = pf(c), pf(h), {gc.name: ss(gc) for gc in (h, c)}
    r.ev["end"] = {"client": slim(p1, p0), "host": slim(h1, h0), "shared_stats": s2}
    r.cell("ownStep", ok and st(p1) == k0 + 1, f"client rockets {k0} -> {st(p1)} (want +1): the SEPARATE client did not step its "
           f"own production")
    r.cell("noCommand", all(pick(s2[n], "cmd", "applyCount") == pick(s1[n], "cmd", "applyCount") for n in s2), f"shared_stats "
           f"before {s1} / after {s2} (want cmd and applyCount unchanged)")


def run_one(rid, fn, x, results):
    r = Row(rid)
    try:
        fn(r, x)
    except GuardMiss as e:
        r.ev["guardMiss"] = str(e)
    except Exception as e:
        r.cell("exception", False, short(e, 800))
    if any(f.startswith(("G:", "exception")) for f in r.fails):
        try:
            r.ev["settleAfterMiss"] = {"speed0": speed(x, 0), "close": {gc.name: pick(gc.cmd({"cmd": "close_screens"}), "popped",
                                                                                          "refused") for gc in (x.host, x.client)}}
        except Exception as e:
            r.ev["settleAfterMiss"] = short(e)
    r.ev["cellsPassed"], r.ev["wallS"] = r.passed, round(time.time() - r.t0, 1)
    print(f"EVIDENCE {rid}: {json.dumps(r.ev, sort_keys=True, default=str)}", flush=True)
    results[rid] = not r.fails
    print(f"PASS {rid}" if not r.fails else f"FAIL {rid}: {len(r.fails)} cell(s): " + " | ".join(r.fails), flush=True)


def setup_a(x):
    """Speed 0 on both; the seats (R-H16g-1: the starter's seat owns a produced soldier); both probes answer."""
    h, c = x.host, x.client
    sp = speed(x, 0)
    x.seat = {gc.name: gc.cmd({"cmd": "synced_options_state"}).get("localSeat") for gc in (h, c)}
    p = {gc.name: pf(gc) for gc in (h, c)}
    info = {"speed0": sp, "seats": x.seat, "probes": {k: slim(v) for k, v in p.items()}}
    if not all(v.get("ok") for v in p.values()) or None in x.seat.values():
        raise RuntimeError(f"boot guard (both prod_fx_probe ok, seats known): {info}")
    return info


def boot_b():
    tag, (hp, cp, lp) = BOOT_B
    host = GameClient("host", hp, make_user_dir(f"{tag}_host", mods=(MOD,)))
    client = GameClient("client", cp, make_user_dir(f"{tag}_client", mods=(MOD,)))
    try:
        for f in (host.spawn, client.spawn, host.connect, client.connect):
            f()
        session.new_campaign(host, client, port=str(lp), campaign_mode="coop")
        geo.wait_both_ready(host, client)
    except BaseException:
        shutdown_clients(host, client)
        raise
    return SimpleNamespace(host=host, client=client, shutdown=lambda: shutdown_clients(host, client))


def boot(tag, up, setup, rows, results, walls):
    t0, js, info, x = time.time(), None, None, None
    try:
        js = up()
        x = SimpleNamespace(host=js.host, client=js.client)
        walls[tag + " bring-up"] = round(time.time() - t0, 1)
        info = setup(x)
        print(f"EVIDENCE boot {tag}: {json.dumps(info, sort_keys=True, default=str)}", flush=True)
    except Exception as e:
        print(f"CAPTURE {tag} (boot miss): {short(e, 6000)}", flush=True)
        for rid, _fn in rows:
            results[rid] = False
            print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot", flush=True)
    try:
        for rid, fn in (rows if info is not None else ()):
            run_one(rid, fn, x, results)
    finally:
        try:
            js is not None and js.shutdown()
        except Exception as e:
            print(f"[w2h16g] {tag} shutdown: {short(e)}", flush=True)
        walls[tag] = round(time.time() - t0, 1)


ROWS_A = (("H16g-1", row_1), ("H16g-2", row_2), ("H16g-3", row_3), ("H16g-4", row_4), ("H16g-5", row_5), ("H16g-6", row_6))
ROWS_B = (("H16g-7", row_7),)


def main():
    t0, results, walls = time.time(), {}, {}
    boot(BOOT_A[0], lambda: shared_fixture.bring_up(BOOT_A[0], BOOT_A[1], mods=(MOD,)), setup_a, ROWS_A, results, walls)
    boot(BOOT_B[0], boot_b, lambda x: {"mods": [os.path.basename(MOD)]}, ROWS_B, results, walls)
    failed, n = [rid for rid, _ in ROWS_A + ROWS_B if not results.get(rid)], len(ROWS_A + ROWS_B)
    print(f"\ntest_w2_production_effects: {n - len(failed)}/{n} passed (fail={failed}) walls {walls} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
