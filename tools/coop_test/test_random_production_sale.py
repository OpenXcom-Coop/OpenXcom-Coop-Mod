"""In SHARED the random-production window lists the host's items on both machines and its right-click sale goes
through the host (`sell`, capped at the host's stores); in the one SEPARATE world the host runs the client's own
production at ClientBase and the client's sale reaches the host. Test hook (read-only): prodwin_probe; real input
(inject_input). SHARED boot: client_list, client_sells, host_sells (one completion's windows), two_sales, after_repair
(last); SEPARATE boot: separate_reaches_host (guard row: progress 9 staged on both machines, the window on the client,
its right-click on SMALL; both machines' ClientBase SMALL -3). Without the fix the five SHARED rows fail on their named
cells and separate_reaches_host passes; with it all pass. "guard:" cells are guards (CAPTURE on a miss); never `mismatches`.
EVIDENCE then PASS / FAIL per row; ONE run; exit 0 if all pass, else 2."""

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

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_RandomSale_Test")
SHARED_BOOT = ("random_sale_shared", (49411, 49412, 47380))     # SHARED; lobby 47380
SEPARATE_BOOT = ("random_sale_separate", (49413, 49414, 47382))     # SEPARATE; lobby 47382
ITEM, SR, LR = "STR_SALETEST_RANDOM", "STR_SMALL_ROCKET", "STR_LARGE_ROCKET"
CAPTION = "Summary"                             # en-US tr("STR_RANDOM_PRODUCTION_SUMMARY")
P_S, P_L = 480, 720                             # the window's price of one small / large rocket
AGREE_S, ROLL_S, ROLL_I, OPEN_S, WIN_S, WIN_I, POST_S, UI_S = 20.0, 30.0, 0.1, 3.0, 3.0, 0.25, 4.0, 5.0
GEO = "GeoscapeState"
ADOPTED = "restream adopted; released the client hold"   # the host's log line per adopted restream (test_shared_resync_storm)


class GuardMiss(Exception): """A guard failed: the row ends after its CAPTURE line."""  # noqa: E701


def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while not (last := pred()) and time.time() - t0 < timeout:
        time.sleep(interval)
    return bool(last), last


def short(e, n=500): return (lambda s: s if len(s) <= n else s[:n] + "...")(f"{type(e).__name__}: {e}")  # noqa: E704
def pick(d, *keys): return {k: d.get(k) for k in keys}  # noqa: E704
def stack(gc): return session.states_stripped(gc)  # noqa: E704
def top(gc): return (stack(gc) or [""])[-1]  # noqa: E704
def rs(gc): return pick(gc.cmd({"cmd": "shared_resync_stats"}), "requests", "pending")  # noqa: E704
def ss(gc): return pick(gc.cmd({"cmd": "shared_stats"}), "cmd", "okCount", "failCount", "applyCount", "applyQueued", "lastFail")  # noqa: E704,E501
def pf(gc): return gc.cmd({"cmd": "prod_fx_probe"})  # noqa: E704
def pw(gc): return gc.cmd({"cmd": "prodwin_probe"})  # noqa: E704
def pfb(gc, base): return gc.cmd({"cmd": "prod_fx_probe", "base": base})  # noqa: E704
def owner_funds(gc, base): return gc.cmd({"cmd": "base_report", "base": base}).get("ownerFunds")  # noqa: E704
def st(p, k=SR): return (p.get("stores") or {}).get(k, 0)  # noqa: E704
def prods(p): return [[q.get("name"), q.get("amount")] for q in p.get("productions") or []]  # noqa: E704
def prod(p): return ([q for q in p.get("productions") or [] if q.get("name") == ITEM] or [None])[0]  # noqa: E704
def view(p): return {"funds": p.get("funds"), "SR": st(p), "LR": st(p, LR), "prods": prods(p)}  # noqa: E704
def rows(w): return [[q.get("item"), q.get("qty")] for q in w.get("rows") or []]  # noqa: E704
def rowof(w, item): return ([q for q in w.get("rows") or [] if q.get("item") == item] or [None])[0]  # noqa: E704
def both(x, f): return {gc.name: f(gc) for gc in (x.host, x.client)}  # noqa: E704
def wslim(w): return {"open": w.get("open"), "rows": rows(w), "list": [w.get("listVisible"), w.get("listHidden")]}  # noqa: E704
def speed(x, idx): return both(x, lambda g: pick(g.cmd({"cmd": "geo_set_speed", "idx": idx}), "ok", "error"))  # noqa: E704
def req0(x): return {k: v["requests"] for k, v in both(x, rs).items()}  # noqa: E704


class Row:
    def __init__(self, rid):
        self.rid, self.t0, self.ev, self.fails, self.passed, self.baseline = rid, time.time(), {}, [], [], None

    def cell(self, name, ok, detail=""): return (self.passed.append(name) if ok else self.fails.append(f"{name}: {detail}")) or ok  # noqa: E704,E501


def capture(x, tag):
    """Setup-failure dump: both machines' prod_fx_probe, prodwin_probe, shared_stats, shared_resync_stats, stack."""
    cap = {}
    for gc in (x.host, x.client):
        try:
            cap[gc.name] = {"stack": stack(gc), "prod_fx_probe": pf(gc), "prodwin_probe": pw(gc), "shared_stats": gc.cmd({"cmd": "shared_stats"}),
                            "shared_resync_stats": gc.cmd({"cmd": "shared_resync_stats"})}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {tag}: {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def guard(r, x, name, ok, detail):
    if r.cell("guard:" + name, ok, detail):
        return
    capture(x, f"{r.rid} (guard {name})")
    raise GuardMiss(f"guard {name}")


def drain(gc):
    try:
        return geo.drain_popups(gc)[0]
    except Exception as e:
        return short(e)


def agreed(x, drained=None):
    """Both prod_fx_probe agree on funds, both rocket counts, productions (never `ids`); no restream pending; on the
    geoscape."""
    if rs(x.client)["pending"]:
        return None
    for gc in (x.host, x.client):
        if top(gc) != GEO:
            d = drain(gc)
            drained is not None and drained.append([gc.name, d])
            return None
    p = both(x, pf)
    return p if view(p["host"]) == view(p["client"]) else None


def wait_agreed(r, x, tag="atStart"):
    """Row frame atStart: <= 20 s until both machines agree; baseline = both `requests`."""
    t0, drained = time.time(), []
    ok, p = wait_until(lambda: agreed(x, drained), AGREE_S, 0.25)
    d = {"agreeS": round(time.time() - t0, 2), "drained": drained}
    r.ev[tag] = d
    guard(r, x, f"{tag} agreement", ok, f"not agreed in {d['agreeS']} s; stacks {both(x, stack)}; views {both(x, lambda g: view(pf(g)))}")
    r.baseline = req0(x)
    d.update(baseline=r.baseline, view={k: view(v) for k, v in p.items()}, window=both(x, lambda g: wslim(pw(g))))
    return p


def start(r, x, qty):
    """The client's real start (ManufactureInfoState; SHARED man_start); guard: listed on both (assigned 1, amount qty), funds equal."""
    r.ev["start"] = pick(x.client.cmd({"cmd": "manufacture_start", "item": ITEM, "engineers": 1, "qty": qty}), "ok", "sent", "error")
    ok, p = wait_until(lambda: (lambda p: p if all(pick(prod(v) or {}, "assigned", "amount") == {"assigned": 1, "amount": qty}
                                                   for v in p.values()) and p["host"]["funds"] == p["client"]["funds"] else None)(
        both(x, pf)), UI_S)
    q = p or both(x, pf)
    r.ev["listed"] = {k: [prod(v), v.get("funds")] for k, v in q.items()}
    guard(r, x, "listed", ok, f"{ITEM} x{qty} not listed on both with 1 engineer (funds equal): {r.ev['listed']}")


def progress(r, x, spent):
    out = [[gc.name, pick(gc.cmd({"cmd": "set_production_progress", "item": ITEM, "timeSpent": spent}), "found", "error")]
           for gc in (x.client, x.host)]
    r.ev[f"progress {spent}"] = out
    guard(r, x, f"progress {spent}", all(o[1].get("found") is True for o in out), f"{out}")


def roll_to_window(r, x, gcs):
    """Speed 1 on both; gcs[0]'s prodwin_probe every 0.1 s until open (<= 30 s); the others' until open (<= 3 s); speed 0 on both."""
    sp, t0 = speed(x, 1), time.time()
    ok = wait_until(lambda: pw(gcs[0]).get("open"), ROLL_S, ROLL_I)[0]
    ok2 = ok and all(wait_until(lambda: pw(gc).get("open"), OPEN_S, 0.05)[0] for gc in gcs[1:])
    r.ev["roll"] = {"speed1": sp, "s": round(time.time() - t0, 2), "speed0": speed(x, 0)}
    guard(r, x, "window open", ok and ok2, f"windows {both(x, lambda g: wslim(pw(g)))} after {r.ev['roll']['s']} s")


def summary(r, x, gcs):
    """Wait each window's buttons unhidden (POPUP); left-click Summary ONCE (it shares its rect with Allocate); wait the list."""
    d = r.ev["summary"] = {}
    for gc in gcs:
        ok, w = wait_until(lambda: (lambda w: w if w.get("open") and not any(b.get("hidden") for b in w.get("buttons") or [])
                                    else None)(pw(gc)), UI_S, 0.05)
        b = [b for b in (w or {}).get("buttons") or [] if b.get("text") == CAPTION and b.get("visible")]
        guard(r, x, f"{gc.name} Summary", ok and len(b) == 1, f"{gc.name} buttons {(w or pw(gc)).get('buttons')}")
        d[gc.name] = pick(gc.cmd({"cmd": "inject_input", "kind": "click", "button": "left", "x": b[0]["cx"], "y": b[0]["cy"]}), "ok", "error")
    for gc in gcs:
        ok = wait_until(lambda: (lambda w: w.get("listVisible") and not w.get("listHidden"))(pw(gc)), UI_S, 0.05)[0]
        guard(r, x, f"{gc.name} list shown", ok, f"{gc.name} {wslim(pw(gc))}")


def rclick(r, x, gc, item, tag):
    """Right-click `item`'s row in gc's OWN window, or at the host's row when gc lists none (one layout; an empty list ignores it)."""
    own = rowof(pw(gc), item)
    q = own or rowof(pw(x.host), item)
    guard(r, x, f"{tag} row", q is not None, f"no {item} row on {gc.name} or the host")
    r.ev[tag] = {"by": gc.name, "item": item, "at": [q["cx"], q["cy"]], "ownRow": own is not None, "ok": gc.cmd(
        {"cmd": "inject_input", "kind": "click", "button": "right", "x": q["cx"], "y": q["cy"]}).get("ok")}


def funds_equal(r, x, tag):
    """F = both machines' funds just before the row's first right-click (guard: equal)."""
    f = r.ev[tag] = both(x, lambda g: pf(g).get("funds"))
    guard(r, x, tag, f["host"] == f["client"], f"funds {f}")
    return f["host"]


def window(r, x):
    """Both probes every ~0.25 s for 3 s; guard: the client's `requests` stays baseline at every sample. Returns the
    LAST sample."""
    t0, reqs, smp = time.time(), [], []
    while time.time() - t0 < WIN_S:
        p, w = both(x, pf), both(x, pw)
        smp.append({"t": round(time.time() - t0, 2), "view": {k: view(v) for k, v in p.items()},
                    "rows": {k: rows(v) for k, v in w.items()}, "open": {k: v.get("open") for k, v in w.items()}})
        reqs.append(rs(x.client)["requests"])
        time.sleep(WIN_I)
    r.ev["window"] = {"n": len(smp), "requests": reqs, "first": smp[0], "last": smp[-1]}
    guard(r, x, "window requests flat", all(q == r.baseline["client"] for q in reqs),
          f"client requests {reqs} (baseline {r.baseline['client']})")
    return smp[-1]


def release(r, x):
    """Speed 0, host close_screens, drain both; cells passed: the client's `requests` stays baseline for 4 s (else
    EVIDENCE of the repair)."""
    t0 = time.time()
    r.ev["release"], reqs = {"speed0": speed(x, 0), "close": pick(x.host.cmd({"cmd": "close_screens"}), "popped", "refused"),
                             "drain": both(x, drain)}, []
    while time.time() - t0 < POST_S:
        reqs.append(rs(x.client)["requests"])
        time.sleep(0.25)
    r.ev["release"]["requests"] = reqs
    if not r.fails:
        r.cell("noRepair", all(q == r.baseline["client"] for q in reqs), f"client requests {reqs} in {POST_S} s after "
               f"the release (baseline {r.baseline['client']}): the replica needed a repair restream")
    r.ev["end"] = {k: view(v) for k, v in both(x, pf).items()}


def row_client_list(r, x):
    """The second player's list: the client's own start (1, 1); both windows; Summary on both."""
    p0 = wait_agreed(r, x)
    x.K, x.L = st(p0["host"]), st(p0["host"], LR)
    start(r, x, 1)
    progress(r, x, 9)
    roll_to_window(r, x, [x.host, x.client])
    summary(r, x, [x.host, x.client])
    p, w = both(x, pf), both(x, pw)
    r.ev["values"] = {"K": x.K, "L": x.L, "view": {k: view(v) for k, v in p.items()}, "rows": {k: rows(v) for k, v in w.items()}}
    guard(r, x, "host result", st(p["host"]) == x.K + 3 and st(p["host"], LR) == x.L + 1 and prod(p["host"]) is None and prod(
        p["client"]) is None and rows(w["host"]) == [[LR, 1], [SR, 3]], f"{r.ev['values']} (want host K+3 / L+1, production gone on both)")
    r.cell("clientList", rows(w["client"]) == rows(w["host"]), f"client rows {rows(w['client'])} / host {rows(w['host'])}: the "
           f"second player's production window lists nothing")


def row_client_sells(r, x):
    """The second player sells (client_list's windows): right-click its SMALL row."""
    guard(r, x, "windows open", all(v.get("open") for v in both(x, pw).values()), f"{both(x, lambda g: wslim(pw(g)))}")
    r.baseline = req0(x)
    F = funds_equal(r, x, "F")
    rclick(r, x, x.client, SR, "client rclick SMALL")
    e = window(r, x)
    h, c = e["view"]["host"], e["view"]["client"]
    r.ev["values"] = {"K": x.K, "F": F, "last": e}
    guard(r, x, "host rows unchanged", e["rows"]["host"] == [[LR, 1], [SR, 3]], f"host rows {e['rows']['host']}")
    r.cell("clientSells", h["SR"] == c["SR"] == x.K and h["funds"] == c["funds"] == F + 3 * P_S and e["rows"]["client"] == [[LR, 1]],
           f"SMALL host {h['SR']} / client {c['SR']} (want K = {x.K}), funds host {h['funds']} / client {c['funds']} (want F + 3 x "
           f"P_S = {F + 3 * P_S}), client rows {e['rows']['client']}: the second player cannot sell from its window")


def row_host_sells(r, x):
    """The host sells (the same windows): right-click its LARGE row; then the release."""
    guard(r, x, "windows open", all(v.get("open") for v in both(x, pw).values()), f"{both(x, lambda g: wslim(pw(g)))}")
    r.baseline = req0(x)
    F = funds_equal(r, x, "F")
    rclick(r, x, x.host, LR, "host rclick LARGE")
    e = window(r, x)
    h, c = e["view"]["host"], e["view"]["client"]
    r.ev["values"] = {"L": x.L, "F": F, "last": e}
    guard(r, x, "host sale", h["LR"] == x.L and h["funds"] == F + P_L, f"host LARGE {h['LR']} (want L = {x.L}), funds {h['funds']} "
          f"(want F + P_L = {F + P_L})")
    r.cell("hostSaleShared", c["LR"] == x.L and c["funds"] == h["funds"], f"client LARGE {c['LR']} (want L = {x.L}), funds "
           f"{c['funds']} / host {h['funds']}: the host's sale stayed on the host")
    release(r, x)


def row_two_sales(r, x):
    """Two sales at once sell what is left: the host's LARGE sale held on the client, then the client's own LARGE
    click."""
    p0 = wait_agreed(r, x)
    L = st(p0["host"], LR)
    guard(r, x, "L == 0", L == 0 and st(p0["client"], LR) == 0,
          f"LARGE {view(p0['host'])} / {view(p0['client'])} (two_sales needs 0)")
    start(r, x, 1)
    progress(r, x, 9)
    roll_to_window(r, x, [x.host, x.client])
    summary(r, x, [x.host, x.client])
    w = both(x, pw)
    r.ev["rows"] = {k: rows(v) for k, v in w.items()}
    guard(r, x, "host rows", rows(w["host"]) == [[LR, 1], [SR, 3]], f"host rows {rows(w['host'])}")
    if not r.cell("clientList", rows(w["client"]) == rows(w["host"]), f"client rows {rows(w['client'])} / host {rows(w['host'])}: "
                  f"the second player's production window lists nothing (the sale steps are not run)"):
        return release(r, x)
    F = funds_equal(r, x, "F")
    s0s = r.ev["stats0"] = both(x, ss)
    try:
        r.ev["deferOn"] = pick(x.client.cmd({"cmd": "shared_update_defer", "on": True}), "ok", "deferred")
        rclick(r, x, x.host, LR, "host rclick LARGE")
        ok, _ = wait_until(lambda: st(pf(x.host), LR) == L and (ss(x.client).get("applyQueued") or 0) >= 1
                           and st(pf(x.client), LR) == L + 1, UI_S, 0.05)
        guard(r, x, "host sold, client held", ok, f"host {view(pf(x.host))}, client {view(pf(x.client))} {ss(x.client)}")
        rclick(r, x, x.client, LR, "client rclick LARGE")
        ok = wait_until(lambda: (ss(x.host).get("cmd") or 0) >= s0s["host"]["cmd"] + 2, 3.0, 0.05)[0]
        r.ev["hostCmd"] = [s0s["host"]["cmd"], ss(x.host)["cmd"]]
        guard(r, x, "both sales reached the host", ok, f"host cmd {r.ev['hostCmd']} (want +2)")
    finally:
        r.ev["deferOff"] = pick(x.client.cmd({"cmd": "shared_update_defer", "on": False}), "ok", "deferred")
    e = window(r, x)
    h, c, s1 = e["view"]["host"], e["view"]["client"], both(x, ss)
    r.ev["values"] = {"L": L, "F": F, "last": e, "stats": s1}
    r.cell("leftover", h["LR"] == c["LR"] == L and h["funds"] == c["funds"] == F + P_L, f"LARGE host {h['LR']} / client {c['LR']} "
           f"(want {L}), funds {h['funds']} / {c['funds']} (want F + P_L = {F + P_L}): the later sale did not sell what was left")
    r.cell("noFailBox", e["open"]["client"] is True and all(s1[k]["failCount"] == s0s[k]["failCount"] for k in s1), f"client window "
           f"open {e['open']['client']}, failCount {s0s} -> {s1}: the later seller got a shared-fail box")
    release(r, x)


def row_after_repair(r, x):
    """After a repair copy (last in the SHARED boot): a 2-unit run, a host force_resync after unit 1, then unit 2's
    windows."""
    p0 = wait_agreed(r, x)
    K, L = st(p0["host"]), st(p0["host"], LR)
    start(r, x, 2)
    progress(r, x, 9)
    r.ev["speed1"], t0 = speed(x, 1), time.time()
    ok, p1 = wait_until(lambda: (lambda p: p if st(p, LR) >= L + 1 else None)(pf(x.host)), ROLL_S, ROLL_I)
    r.ev["unit1"] = {"s": round(time.time() - t0, 2), "speed0": speed(x, 0), "host": prod(p1 or pf(x.host))}
    guard(r, x, "unit 1", ok and (prod(p1) or {}).get("produced") == 1, f"host {view(pf(x.host))} {prod(pf(x.host))} (want L+1, produced 1)")
    log = os.path.join(x.host_dir, "openxcom.log")
    off = os.path.getsize(log)
    r.ev["force_resync"] = pick(x.host.cmd({"cmd": "force_resync"}), "ok", "role", "error")

    def adopted():
        with open(log, "r", encoding="utf-8", errors="replace") as f:
            return f.seek(off) >= 0 and ADOPTED in f.read()
    t0 = time.time()
    ok = wait_until(adopted, 10.0, 0.05)[0] and wait_until(lambda: agreed(x), 10.0, 0.05)[0]
    r.ev["restream"] = {"s": round(time.time() - t0, 2), "stacks": both(x, stack)}
    guard(r, x, "restream adopted", ok, f"no '{ADOPTED}' + agreement in 10 s: {r.ev['restream']}")
    progress(r, x, 19)
    roll_to_window(r, x, [x.host, x.client])
    summary(r, x, [x.host, x.client])
    p, w = both(x, pf), both(x, pw)
    r.ev["atWindow"] = {"view": {k: view(v) for k, v in p.items()}, "rows": {k: rows(v) for k, v in w.items()}}
    guard(r, x, "host result", rows(w["host"]) == [[LR, 2], [SR, 6]] and st(p["host"]) == K + 6 and st(p["host"], LR) == L + 2,
          f"{r.ev['atWindow']} (want host rows [[{LR}, 2], [{SR}, 6]], stores K+6 = {K + 6} / L+2 = {L + 2})")
    r.cell("clientListFresh", rows(w["client"]) == rows(w["host"]), f"client rows {rows(w['client'])} / host {rows(w['host'])}: the "
           f"second player lists the copy from the repair")
    r.baseline = req0(x)
    F = funds_equal(r, x, "F")
    rclick(r, x, x.client, SR, "client rclick SMALL")
    e = window(r, x)
    h, c = e["view"]["host"], e["view"]["client"]
    r.ev["values"] = {"K": K, "L": L, "F": F, "last": e}
    r.cell("clientSaleShared", h["SR"] == c["SR"] == K and h["funds"] == c["funds"] == F + 6 * P_S, f"SMALL host {h['SR']} / client "
           f"{c['SR']} (want K = {K}), funds host {h['funds']} / client {c['funds']} (want F + 6 x P_S = {F + 6 * P_S}): the second "
           f"player's sale stayed on its machine")
    release(r, x)


def row_separate_reaches_host(r, x):
    """SEPARATE (guard row): the client's own start (1, 1) at ClientBase; in the one world the host runs it (progress 9
    staged on both machines), the window opens on the client and its right-click on SMALL sells through the host."""
    h, c, cb = x.host, x.client, "ClientBase"
    guard(r, x, "start", wait_until(lambda: top(h) == GEO and top(c) == GEO, AGREE_S, 0.2)[0],
          f"stacks {both(x, stack)}")
    r.ev["speed0"] = speed(x, 0)
    p0, h0, s1 = pf(c), pfb(h, cb), both(x, ss)
    r.ev["atStart"] = {"client": view(p0), "host ClientBase": view(h0), "shared_stats": s1,
                       "window": both(x, lambda g: wslim(pw(g)))}
    r.ev["start"] = pick(c.cmd({"cmd": "manufacture_start", "item": ITEM, "engineers": 1, "qty": 1}), "ok", "sent", "error")
    guard(r, x, "listed", wait_until(lambda: (prod(pf(c)) or {}).get("assigned") == 1
                                     and (prod(pfb(h, cb)) or {}).get("assigned") == 1, UI_S)[0],
          f"client {view(pf(c))} {prod(pf(c))}, host ClientBase {prod(pfb(h, cb))}")
    st9 = {gc.name: gc.cmd({"cmd": "set_production_progress", "item": ITEM, "timeSpent": 9, "base": cb}) for gc in (c, h)}
    guard(r, x, "progress 9", all(v.get("found") is True for v in st9.values()), f"{st9}")
    roll_to_window(r, x, [c])
    summary(r, x, [c])
    # the host's ClientBase holds the delivered units and the client's funds when the window opens; the client's own
    # view may still lag the host's delivery then
    r.ev["atWindow"] = {"client": view(p1 := pf(c)), "host ClientBase": view(h1 := pfb(h, cb)),
                        "host's client funds": (f1 := owner_funds(h, cb)), "rows": rows(w := pw(c))}
    r.cell("rows", rows(w) == [[LR, 1], [SR, 3]], f"client rows {rows(w)} (want [[{LR}, 1], [{SR}, 3]])")
    rclick(r, x, c, SR, "client rclick SMALL")
    sold = wait_until(lambda: st(pfb(h, cb)) == st(h1) - 3 and owner_funds(h, cb) == f1 + 3 * P_S, UI_S, 0.05)[0]
    seen = wait_until(lambda: st(pf(c)) == st(pfb(h, cb)) and pf(c).get("funds") == owner_funds(h, cb), UI_S, 0.05)[0]
    p2, h2, f2, s2 = pf(c), pfb(h, cb), owner_funds(h, cb), both(x, ss)
    r.ev["end"] = {"client": view(p2), "host ClientBase": view(h2), "host's client funds": f2, "shared_stats": s2,
                   "rows": rows(pw(c))}
    r.cell("hostAgrees", sold, f"host's ClientBase SMALL {st(h1)} -> {st(h2)} (want -3), the client's funds on the host "
           f"{f1} -> {f2} (want +3 x P_S = {3 * P_S}): the sale did not reach the host")
    r.cell("ownSale", seen, f"client SMALL {st(p2)} / funds {p2.get('funds')}, the host's {st(h2)} / {f2}: the client does "
           f"not show the host's result")


def run_one(rid, fn, x, results):
    r = Row(rid)
    try:
        fn(r, x)
    except GuardMiss as e:
        r.ev["guardMiss"] = str(e)
    except Exception as e:
        r.cell("exception", False, short(e, 800))
    if any(f.startswith(("guard:", "exception")) for f in r.fails):
        try:
            r.ev["settleAfterMiss"] = {"speed0": speed(x, 0), "close": {gc.name: pick(gc.cmd({"cmd": "close_screens"}), "popped",
                                                                                          "refused") for gc in (x.host, x.client)}}
        except Exception as e:
            r.ev["settleAfterMiss"] = short(e)
    r.ev["cellsPassed"], r.ev["wallS"] = r.passed, round(time.time() - r.t0, 1)
    print(f"EVIDENCE {rid}: {json.dumps(r.ev, sort_keys=True, default=str)}", flush=True)
    results[rid] = not r.fails
    print(f"PASS {rid}" if not r.fails else f"FAIL {rid}: {len(r.fails)} cell(s): " + " | ".join(r.fails), flush=True)


def setup_shared(x):
    """Speed 0 on both; the seats; both probes answer; the mod's project exists (a start is listed in client_list)."""
    sp, seats, p = speed(x, 0), both(x, lambda g: g.cmd({"cmd": "synced_options_state"}).get("localSeat")), both(x, pf)
    info = {"speed0": sp, "seats": seats, "view": {k: view(v) for k, v in p.items()}, "mods": [os.path.basename(MOD)]}
    if not all(v.get("ok") for v in p.values()) or None in seats.values():
        raise RuntimeError(f"boot guard (both prod_fx_probe ok, seats known): {info}")
    return info


def bring_up_separate():
    tag, (hp, cp, lp) = SEPARATE_BOOT
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


def boot(tag, up, setup, rows_, results, walls):
    t0, js, info, x = time.time(), None, None, None
    try:
        js = up()
        x = SimpleNamespace(host=js.host, client=js.client, host_dir=getattr(js, "host_dir", None))
        walls[tag + " bring-up"] = round(time.time() - t0, 1)
        info = setup(x)
        print(f"EVIDENCE boot {tag}: {json.dumps(info, sort_keys=True, default=str)}", flush=True)
    except Exception as e:
        print(f"CAPTURE {tag} (boot miss): {short(e, 6000)}", flush=True)
        for rid, _fn in rows_:
            results[rid] = False
            print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot", flush=True)
    try:
        for rid, fn in (rows_ if info is not None else ()):
            run_one(rid, fn, x, results)
    finally:
        try:
            js is not None and js.shutdown()
        except Exception as e:
            print(f"[random_sale] {tag} shutdown: {short(e)}", flush=True)
        walls[tag] = round(time.time() - t0, 1)


def main():
    t0, results, walls = time.time(), {}, {}
    SHARED_ROWS = (("client_list", row_client_list), ("client_sells", row_client_sells),
                   ("host_sells", row_host_sells), ("two_sales", row_two_sales), ("after_repair", row_after_repair))
    SEPARATE_ROWS = (("separate_reaches_host", row_separate_reaches_host),)
    boot(SHARED_BOOT[0], lambda: shared_fixture.bring_up(SHARED_BOOT[0], SHARED_BOOT[1], mods=(MOD,)), setup_shared,
         SHARED_ROWS, results, walls)
    boot(SEPARATE_BOOT[0], bring_up_separate, lambda x: {"mods": [os.path.basename(MOD)]}, SEPARATE_ROWS, results,
         walls)
    failed, n = [rid for rid, _ in SHARED_ROWS + SEPARATE_ROWS if not results.get(rid)], len(SHARED_ROWS
                                                                                             + SEPARATE_ROWS)
    print(f"\ntest_random_production_sale: {n - len(failed)}/{n} passed (fail={failed}) walls {walls} in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
