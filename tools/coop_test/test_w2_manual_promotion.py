"""W2-H16 (F3260; D226 a; Q1 a / Q2 a / Q3 a; veto V1): a manual promotion and a nationality change made on one machine
reach the shared world. Spec docs rewrite/prompts/w2h16_manual_promotion.md (e)-(f); TASK 0 rewrite/w2h16-task0/
CONSTANTS.md (its five corrections applied). Levers (test-only): open_soldier_info, set_soldier_rank (staging, THIS
machine), soldier_attr_probe. Real input: rank badge (click_widget nth 0) -> rank TextList shown (hidden false) ->
inject_input at rankScreen.rows[r].wx/wy; flag = click_widget nth 1. Boot A (SHARED): H16-1..4; Boot B (SEPARATE): H16-5
(guard row). S0: S1, S2 (client-owned), S3 (host-owned) -> squaddie, client then host; floor(N/5) - 1 others -> sergeant;
one sergeant opening on both (guard). RED (commit 1): H16-1..4 fail on their named cell, H16-5 passes; GREEN: all pass.
"G:" cells are guards (CAPTURE on a miss). EVIDENCE then PASS / FAIL per row; ONE run; exit 0 only if all pass, else 2.
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

OPT = "oxceManualPromotions"
BOOT_A = ("w2h16a", (49290, 49291, 47280))      # SHARED; lobby 47280 (F5764)
BOOT_B = ("w2h16b", (49292, 49293, 47282))      # SEPARATE; lobby 47282
SQUADDIE, SERGEANT = 1, 2
POLL_S, POLL_I, UI_S, BETWEEN_S, CLEAN_S = 3.0, 0.1, 3.0, 30, 4.0
INFO, GEO = "SoldierInfoState", "GeoscapeState"

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
def sol(gc, sid): return sap(gc, sid).get("soldier") or {}  # noqa: E704
def rs(gc): return pick(gc.cmd({"cmd": "shared_resync_stats"}), "requests", "pending", "mismatches")  # noqa: E704
def ss(gc): return pick(gc.cmd({"cmd": "shared_stats"}), "cmd", "okCount", "applyCount", "applyQueued")  # noqa: E704
def opt(gc): return gc.cmd({"cmd": "option_values", "ids": [OPT]}).get("values", {}).get(OPT)  # noqa: E704

def sap(gc, sid):
    p = gc.cmd({"cmd": "soldier_attr_probe", "id": sid})
    return dict(p, top=str(p.get("top", "")).replace("class OpenXcom::", ""))

def shown(gc):
    """The rank TextList of a SoldierRankState on top, no longer hidden by the POPUP window (TASK 0 correction 1)."""
    w = gc.cmd({"cmd": "list_widgets"})
    tl = [e for e in w.get("widgets", []) if "TextList" in e.get("type", "")]
    return tl[0] if ("SoldierRankState" in w.get("state", "") and tl and tl[0].get("hidden") is False) else None

class Row:
    def __init__(self, rid):
        self.rid, self.t0, self.ev, self.fails, self.passed, self.ids = rid, time.time(), {}, [], [], ()
    def cell(self, name, ok, detail=""):
        (self.passed.append(name) if ok else self.fails.append(f"{name}: {detail}"))
        return ok

def guard(r, x, name, ok, detail):
    """A miss: CAPTURE both machines' stack, shared_stats, each row soldier's [soldier_attr_probe, soldier_record]."""
    if r.cell("G:" + name, ok, detail):
        return
    cap = {}
    for gc in (x.host, x.client):
        try:
            cap[gc.name] = {"stack": stack(gc), "shared_stats": gc.cmd({"cmd": "shared_stats"}), "resync": rs(gc),
                            "soldiers": {i: [sap(gc, i), gc.cmd({"cmd": "soldier_record", "id": i})] for i in r.ids}}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {r.rid} (guard {name}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise GuardMiss(f"guard {name}")

def open_info(r, x, gc, sid, tag):
    o = gc.cmd({"cmd": "open_soldier_info", "soldierId": sid})
    guard(r, x, f"{tag} open", o.get("ok") is True, f"{o}")
    guard(r, x, f"{tag} info", wait_until(lambda: top(gc) == INFO, UI_S)[0], f"stack {stack(gc)}")
    return o

def close_info(r, x, gc, tag):
    cw = gc.cmd({"cmd": "click_widget", "match": "OK"})
    guard(r, x, f"{tag} closed", wait_until(lambda: top(gc) == GEO, UI_S)[0] and cw.get("ok") is True,
          f"click {cw}; stack {stack(gc)}")

def promote(r, x, gc, sid, rank, tag):
    """open_soldier_info -> rank badge -> the list shown -> real click on the target row -> back -> OK."""
    ev = r.ev.setdefault("promote " + tag, {})
    ev["open"] = open_info(r, x, gc, sid, tag)
    ev["badge"] = cw = gc.cmd({"cmd": "click_widget", "nth": 0})
    ok = wait_until(lambda: sap(gc, sid)["rankScreen"]["open"], UI_S)[0]
    guard(r, x, f"{tag} rankScreen.open", ok and cw.get("ok") is True, f"click {cw}; stack {stack(gc)}")
    ok, lw = wait_until(lambda: shown(gc), UI_S)
    guard(r, x, f"{tag} list shown", ok, f"{gc.cmd({'cmd': 'list_widgets'})}")
    rows = (p := sap(gc, sid))["rankScreen"]["rows"]
    row = rows[rank] if rank < len(rows) else {}
    ev.update(row=row, openings=p["openings"], before=p["soldier"], list=lw)
    guard(r, x, f"{tag} row {rank} allowed", row.get("allowed") is True and "wx" in row, f"row {row}; rows {rows}")
    ev["click"] = gc.cmd({"cmd": "inject_input", "kind": "click", "x": row["wx"], "y": row["wy"]})
    guard(r, x, f"{tag} back to info", wait_until(lambda: top(gc) == INFO, UI_S)[0], f"stack {stack(gc)}")
    ev["after"] = own = sol(gc, sid)
    guard(r, x, f"{tag} own rank", own.get("rank") == rank, f"{own} (want rank {rank})")
    close_info(r, x, gc, tag)

def flag(r, x, gc, sid, tag):
    """open_soldier_info -> left click on the flag -> 0.5 s -> OK; returns (before, after) on the clicking machine."""
    ev = r.ev.setdefault("flag " + tag, {})
    ev["open"] = open_info(r, x, gc, sid, tag)
    ev["before"] = b = sol(gc, sid)
    ev["flag"] = cw = gc.cmd({"cmd": "click_widget", "nth": 1, "button": "left"})
    time.sleep(0.5)
    ev["after"] = a = sol(gc, sid)
    guard(r, x, f"{tag} own nationality", cw.get("ok") is True and a.get("nationality") is not None
          and a.get("nationality") != b.get("nationality"), f"click {cw}; before {b}; after {a}")
    close_info(r, x, gc, tag)
    return b["nationality"], a["nationality"]

def poll(x, ids, secs=POLL_S):
    """Both machines' soldier_attr_probe every 0.1 s: [rank, nationality] per soldier; only the changes are kept."""
    out, n, t0 = [], 0, time.time()
    while time.time() - t0 < secs:
        s = {f"{gc.name[0]}{i}": [p.get("rank"), p.get("nationality")]
             for gc in (x.host, x.client) for i in ids for p in (sol(gc, i),)}
        if not out or {k: v for k, v in out[-1].items() if k != "t"} != s:
            out.append(dict(s, t=round(time.time() - t0, 2)))
        n += 1
        time.sleep(POLL_I)
    return {"samples": n, "changes": out}

def end(r, x):
    """Both machines' soldier_attr_probe of every row soldier at the row's end (pasted in EVIDENCE)."""
    e = {gc.name: {i: sap(gc, i) for i in r.ids} for gc in (x.host, x.client)}
    r.ev["end"] = {n: {str(i): pick(p, "top", "soldier", "openings") for i, p in v.items()} for n, v in e.items()}
    return {n: {i: (p.get("soldier") or {}) for i, p in v.items()} for n, v in e.items()}, e

def s0(r, x):
    """Row frame S0: tops on the geoscape; S1-S3 squaddies (client, then host); one sergeant opening on both."""
    h, c = x.host, x.client
    ok = wait_until(lambda: not rs(c)["pending"] and top(h) == GEO and top(c) == GEO, BETWEEN_S, 0.2)[0]
    guard(r, x, "start", ok, f"stacks {stack(h)} / {stack(c)}, replica {rs(c)}")
    guard(r, x, "option", x.option is True, f"client {OPT} {x.option}")
    want = [(x.S1, SQUADDIE), (x.S2, SQUADDIE), (x.S3, SQUADDIE)] + [(i, SERGEANT) for i in x.sergeants]
    st = [(gc.name, sid, gc.cmd({"cmd": "set_soldier_rank", "soldierId": sid, "rank": rk}))
          for gc in (c, h) for sid, rk in want]
    guard(r, x, "staging", all(v.get("ok") is True for _, _, v in st), f"{st}")
    d = {"req": {gc.name: rs(gc)["requests"] for gc in (h, c)}, "ss": {gc.name: ss(gc) for gc in (h, c)},
         "openings": {gc.name: sap(gc, x.S1)["openings"] for gc in (h, c)},
         "soldiers": {gc.name: {str(i): sol(gc, i) for i in (x.S1, x.S2, x.S3)} for gc in (h, c)}}
    r.ev["S0"] = d
    guard(r, x, "openings S0", all(o.get("sergeant") == 1 for o in d["openings"].values()), f"{d['openings']}")
    return d

def clean(r, x, d):
    time.sleep(CLEAN_S)
    now = r.ev["clean"] = {gc.name: rs(gc) for gc in (x.host, x.client)}
    r.cell("clean", now["client"]["requests"] == d["req"]["client"],
           f"replica requests {now['client']['requests']} vs S0 {d['req']['client']}")

def reach(r, x, gc, sid, tag, name, why, host_apply):
    """H16-1 / H16-2: one machine promotes; both hold rank 2 by the end of the poll (H16-1: host applyCount S0 + 1)."""
    r.ids = (sid,)
    d = s0(r, x)
    promote(r, x, gc, sid, SERGEANT, tag)
    r.ev["poll"] = poll(x, r.ids)
    v, _ = end(r, x)
    hr, cr = v["host"][sid].get("rank"), v["client"][sid].get("rank")
    a0, a1 = d["ss"]["host"]["applyCount"], ss(x.host)["applyCount"]
    r.cell(name, hr == SERGEANT and cr == SERGEANT and (a1 == a0 + 1 or not host_apply),
           f"{tag}: host rank {hr}, client rank {cr} (want 2/2), host applyCount {a0} -> {a1}"
           f"{' (want +1)' if host_apply else ''}: {why}")
    clean(r, x, d)

def row_h16_3(r, x):
    r.ids = (x.S2, x.S3)
    h, c = x.host, x.client
    d = s0(r, x)
    try:
        r.ev["defer on"] = dn = c.cmd({"cmd": "shared_update_defer", "on": True})
        guard(r, x, "defer on", dn.get("deferred") is True, f"{dn}")
        a0 = ss(h)["applyCount"]
        promote(r, x, h, x.S3, SERGEANT, "host S3")
        ok = wait_until(lambda: ss(h)["applyCount"] >= a0 + 1, UI_S)[0]
        r.ev["host applyCount +1 (wait; EVIDENCE only)"] = {"ok": ok, "before": a0, "now": ss(h)["applyCount"]}
        promote(r, x, c, x.S2, SERGEANT, "client S2")      # its row allowed on its stale world: guard + EVIDENCE
        time.sleep(1.0)
    finally:
        r.ev["defer off"] = c.cmd({"cmd": "shared_update_defer", "on": False})
    r.ev["poll"] = poll(x, r.ids)
    v, e = end(r, x)
    hv, cv = ([v[n][x.S3].get("rank"), v[n][x.S2].get("rank")] for n in ("host", "client"))
    r.cell("agree", hv == [SERGEANT, SQUADDIE] and cv == [SERGEANT, SQUADDIE],
           f"host S3/S2 {hv}, client S3/S2 {cv} (want 2/1 on both): two promotions into one opening; the worlds disagree")
    op = {n: e[n][x.S3]["openings"].get("sergeant") for n in e}
    r.cell("openings", all(o == 0 for o in op.values()), f"sergeant openings {op} (want 0 on both)")
    clean(r, x, d)

def row_h16_4(r, x):
    r.ids = (x.S1, x.S3)
    d = s0(r, x)
    n0, n1 = flag(r, x, x.client, x.S1, "client S1")
    r.ev["poll client flag"] = poll(x, r.ids)
    m0, m1 = flag(r, x, x.host, x.S3, "host S3")
    r.ev["poll host flag"] = poll(x, r.ids)
    v, _ = end(r, x)
    g1, g3 = ([v["host"][i].get("nationality"), v["client"][i].get("nationality")] for i in (x.S1, x.S3))
    r.ev["nationality"] = {"S1 client n0->n1": [n0, n1], "S3 host m0->m1": [m0, m1], "S1 h/c": g1, "S3 h/c": g3}
    r.cell("nationality", g1 == [n1, n1] and g3 == [m1, m1], f"S1 host/client {g1} (want {n1} on both), S3 host/client "
           f"{g3} (want {m1} on both): a nationality change stayed on one machine")
    clean(r, x, d)

def row_h16_5(r, x):
    h, c = x.host, x.client
    ok = wait_until(lambda: top(h) == GEO and top(c) == GEO, BETWEEN_S, 0.2)[0]
    guard(r, x, "start", ok, f"stacks {stack(h)} / {stack(c)}")
    guard(r, x, "option", x.option is True, f"client {OPT} {x.option}")
    br = c.cmd({"cmd": "base_report"})                # the client's own base (correction 4: not owner == seat)
    sid = (br.get("soldiers") or [{}])[0].get("id")
    r.ids = (sid,) if sid is not None else ()
    r.ev["pick"] = {"base": br.get("name"), "id": sid, "soldier": sol(c, sid) if sid is not None else None}
    guard(r, x, "own base 0", (r.ev["pick"]["soldier"] or {}).get("baseIndex") == 0, f"{r.ev['pick']}")
    hc0 = ss(h)["cmd"]
    st = c.cmd({"cmd": "set_soldier_rank", "soldierId": sid, "rank": SQUADDIE})
    guard(r, x, "staging", st.get("ok") is True and st.get("rank") == SQUADDIE, f"{st}")
    r.ev["S0"] = {"client": sol(c, sid), "openings": sap(c, sid)["openings"], "host shared_stats": ss(h)}
    promote(r, x, c, sid, SERGEANT, "client own")
    time.sleep(2.0)
    v, _ = end(r, x)
    cr, hc = v["client"][sid].get("rank"), ss(h)["cmd"]
    r.cell("clientRank", cr == SERGEANT, f"client rank {cr} (want 2)")
    r.cell("hostCmd", hc == hc0, f"host shared_stats.cmd {hc0} -> {hc} (want unchanged)")

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
            x.client.cmd({"cmd": "shared_update_defer", "on": False})
            geo.settle(x.host, x.client)
        except Exception as e:
            r.ev["settleAfterMiss"] = short(e)
    r.ev["cellsPassed"], r.ev["wallS"] = r.passed, round(time.time() - r.t0, 1)
    print(f"EVIDENCE {rid}: {json.dumps(r.ev, sort_keys=True, default=str)}", flush=True)
    results[rid] = not r.fails
    print(f"PASS {rid}" if not r.fails else f"FAIL {rid}: {len(r.fails)} cell(s): " + " | ".join(r.fails), flush=True)

def setup(x, tag):
    """The client's option (W2-P10 sync); Boot A: S1/S2/S3 + the staged sergeants from the host's base_report."""
    x.option = wait_until(lambda: opt(x.client) is True, 10.0)[0] or opt(x.client)
    if tag != BOOT_A[0]:
        return {"option": x.option}
    seat = {gc.name: gc.cmd({"cmd": "synced_options_state"}).get("localSeat") for gc in (x.host, x.client)}
    bases = x.host.ok({"cmd": "geo_state"})["bases"]
    sols = x.host.ok({"cmd": "base_report", "base": bases[0]["name"]})["soldiers"]
    cl, ho = ([s["id"] for s in sols if s["owner"] == seat[k]] for k in ("client", "host"))
    if len(cl) < 2 or not ho:
        raise RuntimeError(f"no S1/S2/S3 at base 0: seats {seat}, soldiers {sols}")
    x.S1, x.S2, x.S3 = cl[0], cl[1], ho[0]
    n = sum(int(b.get("soldiers") or 0) for b in bases)
    x.sergeants = [s["id"] for s in sols if s["id"] not in (x.S1, x.S2, x.S3)][:max(0, n // 5 - 1)]
    return {"option": x.option, "seats": seat, "N": n, "S1": x.S1, "S2": x.S2, "S3": x.S3, "sergeants": x.sergeants,
            "owners": {s["id"]: s["owner"] for s in sols}, "bases": [b["name"] for b in bases]}

def boot_b():
    tag, (hp, cp, lp) = BOOT_B
    host = GameClient("host", hp, make_user_dir(f"{tag}_host", options={OPT: True}))
    client = GameClient("client", cp, make_user_dir(f"{tag}_client"))
    try:
        for f in (host.spawn, client.spawn, host.connect, client.connect):
            f()
        session.new_campaign(host, client, port=str(lp), campaign_mode="coop")
        geo.wait_both_ready(host, client)
    except BaseException:
        shutdown_clients(host, client)
        raise
    return SimpleNamespace(host=host, client=client, shutdown=lambda: shutdown_clients(host, client))

def boot(tag, up, rows, results, walls):
    t0, js, info = time.time(), None, None
    try:
        js = up()
        x = SimpleNamespace(host=js.host, client=js.client)
        walls[tag + " bring-up"] = round(time.time() - t0, 1)
        info = setup(x, tag)
        print(f"EVIDENCE boot {tag}: {json.dumps(info, sort_keys=True, default=str)}", flush=True)
    except Exception as e:
        print(f"CAPTURE {tag} (boot miss): {short(e, 1500)}", flush=True)
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
            print(f"[w2h16] {tag} shutdown: {short(e)}", flush=True)
        walls[tag] = round(time.time() - t0, 1)

ROWS_A = (("H16-1", lambda r, x: reach(r, x, x.client, x.S1, "client S1", "reachedHost",
                                       "the client's promotion never reached the host (F3260)", True)),
          ("H16-2", lambda r, x: reach(r, x, x.host, x.S3, "host S3", "reachedClient",
                                       "the host's promotion never reached the client", False)),
          ("H16-3", row_h16_3), ("H16-4", row_h16_4))
ROWS_B = (("H16-5", row_h16_5),)

def main():
    t0, results, walls = time.time(), {}, {}
    boot(BOOT_A[0], lambda: shared_fixture.bring_up(BOOT_A[0], BOOT_A[1], host_options={OPT: True}),
         ROWS_A, results, walls)
    boot(BOOT_B[0], boot_b, ROWS_B, results, walls)
    failed, n = [rid for rid, _ in ROWS_A + ROWS_B if not results.get(rid)], len(ROWS_A + ROWS_B)
    print(f"\ntest_w2_manual_promotion: {n - len(failed)}/{n} passed (fail={failed}) walls {walls} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
