"""test_manual_promotion.py: a manual promotion and a nationality change made on one machine reach the shared world.
Test commands: open_soldier_info, set_soldier_rank (staging, THIS machine), soldier_attr_probe. Real input: rank badge
(click_widget nth 0) -> rank TextList shown (hidden false) -> inject_input at rankScreen.rows[r].wx/wy; flag =
click_widget nth 1. The SHARED boot: client_promotes, host_promotes, one_opening_two_promotions, nationality_change; the
SEPARATE boot (one world: the client's soldiers at ClientBase, the host's at HostBase): separate_own_soldier (the client
promotes its own soldier, staged squaddie on both machines: both hold sergeant, host applyCount +1); separate_openings
(the host's first floor(N/5) soldiers staged sergeant fill every sergeant opening counted over all N soldiers; the
client's rank screen still shows the one opening its own soldiers leave, and the promotion lands on both);
separate_nationality (the client's flag change on its own soldier reaches the host); separate_partner_refused (a
promotion and a flag change the client sends for a host soldier are refused with "Not one of your soldiers"; nothing
changes); separate_reload (the host saves and loads the campaign, the client rejoins: both hold the client's changes);
separate_auto_promotions (last: every soldier of both players staged squaddie on both machines, the host's Skyranger
fights a battle alone and both vote to abort it: the automatic promotions count only the host's own soldiers,
floor(host's N/5) sergeants, and promote none of the client's soldiers, on both machines).
S0: S1, S2 (client-owned), S3 (host-owned) -> squaddie, client then host; floor(N/5) - 1 others -> sergeant; one
sergeant opening on both (guard). A build where a Separate client's promotion and flag change stay on the client fails
every SEPARATE row on a named cell; with them applied by the host all rows pass.
"guard:" cells are guards (CAPTURE on a miss). EVIDENCE then PASS / FAIL per row; ONE run; exit 0 only if all pass, else 2.
"""

import json
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import separate_campaign_fixture as sep_fixture  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
import test_coop_client_mission_abort as abort_flow  # noqa: E402
import test_separate_equipment_templates as sep_templates  # noqa: E402  (main-guarded: drain_to_geoscape)
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402

OPT = "oxceManualPromotions"
BOOT_SHARED = ("manual_promotion_shared", (49290, 49291, 47280))      # SHARED; lobby 47280
BOOT_SEPARATE = ("manual_promotion_separate", (49292, 49293, 47282))      # SEPARATE; lobby 47282
ROOKIE, SQUADDIE, SERGEANT = 0, 1, 2
PER_SERGEANT = 5                                  # the ruleset's soldiers per sergeant
NOT_YOURS = "STR_COOP_NOT_YOUR_SOLDIER"
SEP_SAVE, SEP_RESUME = "manual_promotion_separate.sav", 47283      # the reload row's save; its resume lobby
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
def fs(gc): return pick(gc.cmd({"cmd": "shared_stats"}), "failCount", "lastFail")  # noqa: E704

def sap(gc, sid):
    p = gc.cmd({"cmd": "soldier_attr_probe", "id": sid})
    return dict(p, top=str(p.get("top", "")).replace("class OpenXcom::", ""))

def shown(gc):
    """The rank TextList of a SoldierRankState on top, no longer hidden by the POPUP window."""
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
    if r.cell("guard:" + name, ok, detail):
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
    """client_promotes / host_promotes: one machine promotes; both hold rank 2 by the end of the poll
    (client_promotes: host applyCount S0 + 1)."""
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

def row_one_opening_two_promotions(r, x):
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

def row_nationality_change(r, x):
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

def row_separate_own_soldier(r, x):
    """The client promotes its own soldier at its own base; in the one Separate world both machines hold the new rank
    by the end of the poll (host applyCount S0 + 1) and the replica asks for no re-copy."""
    h, c = x.host, x.client
    ok = wait_until(lambda: not rs(c)["pending"] and top(h) == GEO and top(c) == GEO, BETWEEN_S, 0.2)[0]
    guard(r, x, "start", ok, f"stacks {stack(h)} / {stack(c)}, replica {rs(c)}")
    guard(r, x, "option", x.option is True, f"client {OPT} {x.option}")
    seat = c.cmd({"cmd": "synced_options_state"}).get("localSeat")
    br = c.cmd({"cmd": "base_report", "base": "ClientBase"})          # the client's own base in the one world
    sid = next((s.get("id") for s in br.get("soldiers") or [] if s.get("owner") == seat), None)
    r.ids = (sid,) if sid is not None else ()
    r.ev["pick"] = {"base": br.get("name"), "seat": seat, "id": sid, "soldier": sol(c, sid) if sid is not None else None}
    guard(r, x, "own soldier", sid is not None and (r.ev["pick"]["soldier"] or {}).get("owner") == seat, f"{r.ev['pick']}")
    st = [(gc.name, gc.cmd({"cmd": "set_soldier_rank", "soldierId": sid, "rank": SQUADDIE})) for gc in (c, h)]
    guard(r, x, "staging", all(v.get("ok") is True and v.get("rank") == SQUADDIE for _, v in st), f"{st}")
    d = {"req": {gc.name: rs(gc)["requests"] for gc in (h, c)}, "ss": {gc.name: ss(gc) for gc in (h, c)},
         "openings": {gc.name: sap(gc, sid)["openings"] for gc in (h, c)},
         "soldier": {gc.name: sol(gc, sid) for gc in (h, c)}}
    r.ev["S0"] = d
    promote(r, x, c, sid, SERGEANT, "client own")
    r.ev["poll"] = poll(x, r.ids)
    v, _ = end(r, x)
    keep(x, sid, v)
    hr, cr = v["host"][sid].get("rank"), v["client"][sid].get("rank")
    a0, a1 = d["ss"]["host"]["applyCount"], ss(h)["applyCount"]
    r.cell("bothRank", hr == SERGEANT and cr == SERGEANT and a1 == a0 + 1,
           f"host rank {hr}, client rank {cr} (want 2/2), host applyCount {a0} -> {a1} (want +1): "
           "the client's promotion of its own soldier reaches the host")
    clean(r, x, d)

def stage_ranks(r, x, want):
    """STAGING on both machines (client first, no command): want [(id, rank)]; guard: every reply reads its rank."""
    st = [(gc.name, sid, rk, gc.cmd({"cmd": "set_soldier_rank", "soldierId": sid, "rank": rk}))
          for gc in (x.client, x.host) for sid, rk in want]
    guard(r, x, "staging", all(v.get("ok") is True and v.get("rank") == rk for _, _, rk, v in st), f"{st}")

def sep_start(r, x):
    """A SEPARATE row's start: tops on the geoscape, no replica repair pending; returns its requests and counters."""
    h, c = x.host, x.client
    ok = wait_until(lambda: not rs(c)["pending"] and top(h) == GEO and top(c) == GEO, BETWEEN_S, 0.2)[0]
    guard(r, x, "start", ok, f"stacks {stack(h)} / {stack(c)}, replica {rs(c)}")
    return {"req": {gc.name: rs(gc)["requests"] for gc in (h, c)}, "ss": {gc.name: ss(gc) for gc in (h, c)}}

def keep(x, sid, v):
    """The client's end values of a row soldier: what separate_reload expects on both machines."""
    x.expect[sid] = pick(v["client"][sid], "rank", "nationality")

def refused_box(r, x, gc, tag):
    """A refused command raises CoopState on its sender: close it with coop_dialog_back; guard: back on the geoscape."""
    wait_until(lambda: "CoopState" in top(gc), 1.0, 0.05)
    r.ev["box " + tag] = gc.cmd({"cmd": "coop_dialog_back"}) if "CoopState" in top(gc) else {"none": stack(gc)}
    guard(r, x, tag + " box closed", wait_until(lambda: top(gc) == GEO, UI_S, 0.05)[0], f"stack {stack(gc)}")

def row_separate_openings(r, x):
    """Manual promotion openings count the promoting player's own soldiers: the host's first floor(N/5) soldiers staged
    sergeant fill every sergeant opening counted over both players' N soldiers; the client's own soldiers still leave
    one. The client's rank screen shows it on its own squaddie and the promotion lands on both machines."""
    h, c = x.host, x.client
    sid, k = x.own[1], (len(x.own) + len(x.partner)) // PER_SERGEANT
    r.ids = (sid,)
    d = sep_start(r, x)
    guard(r, x, "fixture", len(x.partner) >= k and len(x.own) // PER_SERGEANT >= 1, f"own {x.own}, partner {x.partner}")
    stage_ranks(r, x, [(i, SQUADDIE if i == sid else ROOKIE) for i in x.own]
                + [(i, SERGEANT if n < k else ROOKIE) for n, i in enumerate(x.partner)])
    x.expect = {}                                     # the staging reset every soldier the rows before changed
    r.ev["S0"] = {gc.name: sap(gc, sid)["openings"] for gc in (h, c)}
    ev = r.ev.setdefault("rank screen", {})
    ev["open"] = open_info(r, x, c, sid, "client own")
    ev["badge"] = cw = c.cmd({"cmd": "click_widget", "nth": 0})
    ok = wait_until(lambda: sap(c, sid)["rankScreen"]["open"], UI_S)[0]
    guard(r, x, "rankScreen.open", ok and cw.get("ok") is True, f"click {cw}; stack {stack(c)}")
    guard(r, x, "list shown", wait_until(lambda: shown(c), UI_S)[0], f"{c.cmd({'cmd': 'list_widgets'})}")
    rows = ev["rows"] = sap(c, sid)["rankScreen"]["rows"]
    row = rows[SERGEANT] if SERGEANT < len(rows) else {}
    if r.cell("clientOpening", row.get("openings") == "1" and row.get("allowed") is True and "wx" in row,
              f"sergeant row {row} (want openings 1, allowed): the host's sergeants took the client's opening"):
        ev["click"] = c.cmd({"cmd": "inject_input", "kind": "click", "x": row["wx"], "y": row["wy"]})
        guard(r, x, "back to info", wait_until(lambda: top(c) == INFO, UI_S)[0], f"stack {stack(c)}")
        close_info(r, x, c, "client own")
    else:
        ev["close"] = c.cmd({"cmd": "close_screens"})
    r.ev["poll"] = poll(x, r.ids)
    v, _ = end(r, x)
    keep(x, sid, v)
    hr, cr = v["host"][sid].get("rank"), v["client"][sid].get("rank")
    r.cell("bothRank", hr == SERGEANT and cr == SERGEANT, f"host rank {hr}, client rank {cr} (want 2/2)")
    clean(r, x, d)

def row_separate_nationality(r, x):
    """The client changes its own soldier's flag: both machines hold the new nationality (host applyCount + 1)."""
    h, c = x.host, x.client
    sid = x.own[2]
    r.ids = (sid,)
    d = sep_start(r, x)
    n0, n1 = flag(r, x, c, sid, "client own")
    r.ev["poll"] = poll(x, r.ids)
    v, _ = end(r, x)
    keep(x, sid, v)
    g = [v["host"][sid].get("nationality"), v["client"][sid].get("nationality")]
    a0, a1 = d["ss"]["host"]["applyCount"], ss(h)["applyCount"]
    r.cell("nationality", g == [n1, n1] and a1 == a0 + 1, f"host / client {g} (want {n1} on both, from {n0}), host "
           f"applyCount {a0} -> {a1} (want +1): the client's flag change stayed on its machine")
    clean(r, x, d)

def row_separate_partner_refused(r, x):
    """The client sends a promotion and a flag change for one of the host's soldiers at the host's base, as a stale or
    changed client could: the host refuses each ("Not one of your soldiers"); neither machine changes."""
    h, c = x.host, x.client
    sid = x.partner[-1]
    r.ids = (sid,)
    d = sep_start(r, x)
    stage_ranks(r, x, [(sid, SQUADDIE)])
    b = r.ev["before"] = {gc.name: pick(sol(gc, sid), "rank", "nationality") for gc in (h, c)}
    for cmd, p in (("soldier_rank", {"rank": SERGEANT}), ("soldier_nationality", {"nationality": b["host"]["nationality"] + 1})):
        f0 = fs(c)["failCount"]
        r.ev["send " + cmd] = c.cmd({"cmd": "shared_cmd", "jcmd": cmd, "baseId": x.hostBase,
                                     "payload": dict(p, soldierId=sid)})
        ok = wait_until(lambda: fs(c)["failCount"] > f0, UI_S)[0]
        f = r.ev["fail " + cmd] = fs(c)
        refused_box(r, x, c, cmd)
        r.cell(cmd + "Refused", ok and f.get("lastFail") == NOT_YOURS, f"client failCount {f0} -> "
               f"{f.get('failCount')}, lastFail {f.get('lastFail')!r} (want {NOT_YOURS!r})")
    r.ev["poll"] = poll(x, r.ids)
    v, _ = end(r, x)
    now = {n: pick(v[n][sid], "rank", "nationality") for n in v}
    r.cell("unchanged", now == b, f"{now} (want {b})")
    clean(r, x, d)

def row_separate_reload(r, x):
    """The host saves the campaign, both machines leave to the main menu, the host loads the save and the client
    rejoins: both hold every soldier the rows before changed as the client left it (the host's save holds it)."""
    h, c = x.host, x.client
    r.ids = tuple(x.expect)
    sep_start(r, x)
    guard(r, x, "expect", bool(r.ids), f"{x.expect}")
    r.ev["expect"] = {str(i): e for i, e in x.expect.items()}
    r.ev["before"] = {gc.name: {str(i): pick(sol(gc, i), "rank", "nationality") for i in r.ids} for gc in (h, c)}
    session.save_and_resume(h, c, SEP_SAVE, SEP_RESUME)
    ok = wait_until(lambda: not rs(c)["pending"] and top(h) == GEO and top(c) == GEO, BETWEEN_S, 0.2)[0]
    guard(r, x, "resumed", ok, f"stacks {stack(h)} / {stack(c)}")
    now = {gc.name: {i: pick(sol(gc, i), "rank", "nationality") for i in r.ids} for gc in (h, c)}
    r.ev["after"] = {n: {str(i): e for i, e in m.items()} for n, m in now.items()}
    bad = {f"{n} {i}": e for n, m in now.items() for i, e in m.items() if e != x.expect[i]}
    r.cell("reloaded", not bad, f"after the reload {bad} differ from the client's values {r.ev['expect']}")

def battle_to_geoscape(r, x):
    """The host's Skyranger (only the host's soldiers aboard) lands at a new site beside HostBase, both machines enter
    the battle, the host OKs its equip screen, the host asks to abort and the client votes yes; both machines close
    the after-battle screens back to the geoscape."""
    h, c = x.host, x.client
    sep_fixture.fly_to_new_site(h, c, h)
    h.ok({"cmd": "confirm_landing"})
    for gc in (h, c):
        gc.wait_for(gc.name + " in battle", lambda gc=gc: gc.cmd({"cmd": "battle_state"}).get("inBattle") or None,
                    timeout=180, interval=1.0)
    for gc in (h, c):
        gc.wait_for(gc.name + " briefing", lambda gc=gc: abort_flow.has(gc, "BriefingState") or None, timeout=120, interval=0.5)
        gc.ok({"cmd": "close_briefing"})
    h.wait_for("host equip screen", lambda: abort_flow.has(h, "InventoryState") or None, timeout=120, interval=0.5)
    h.ok({"cmd": "battle_inventory", "action": "ok"})
    for _ in range(20):
        if all(abort_flow.top(gc) == "BattlescapeState" for gc in (h, c)):
            break
        for gc in (h, c):
            if abort_flow.top(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(1.0)
    ok = all(abort_flow.top(gc) == "BattlescapeState" for gc in (h, c))
    guard(r, x, "both on the battle screen", ok, f"tops {[abort_flow.top(gc) for gc in (h, c)]}")
    time.sleep(2)
    abort_flow.vote_abort(h, c, h)
    for gc in (h, c):
        sep_templates.drain_to_geoscape(gc)

def row_separate_auto_promotions(r, x):
    """Automatic promotions after a battle the host's Skyranger fought alone: the sergeant openings count only the host's
    own soldiers and none of the client's soldiers is promoted; both machines agree."""
    h, c = x.host, x.client
    sep_start(r, x)
    ids = [s["id"] for b in ("HostBase", "ClientBase") for s in h.ok({"cmd": "base_report", "base": b})["soldiers"]]
    r.ids = tuple(ids)
    stage_ranks(r, x, [(i, SQUADDIE) for i in ids])
    hseat = h.cmd({"cmd": "get_coop"}).get("localSeat")
    owner = {i: sol(h, i).get("owner") for i in ids}
    n_host = sum(1 for o in owner.values() if o == hseat)
    want = {"host": n_host // PER_SERGEANT, "client": 0}
    r.ev.update({"ids": ids, "host seat": hseat, "owners": owner, "want sergeants": want})
    guard(r, x, "both players' soldiers", 0 < n_host < len(ids), f"owners {owner}")

    def sergeants(gc):
        out = {"host": 0, "client": 0}
        for i in ids:
            s = sol(gc, i)
            if s.get("rank") == SERGEANT:
                out["host" if s.get("owner") == hseat else "client"] += 1
        return out
    battle_to_geoscape(r, x)
    same = wait_until(lambda: not rs(c)["pending"] and sergeants(h) == sergeants(c), 60, 0.5)[0]
    now = r.ev["sergeants"] = {gc.name: sergeants(gc) for gc in (h, c)}
    r.ev["promoted"] = {gc.name: [i for i in ids if sol(gc, i).get("rank") != SQUADDIE] for gc in (h, c)}
    r.cell("perOwner", same and now["host"] == want and now["client"] == want,
           f"sergeants by owner {now} (want {want} on both): the automatic promotions counted every soldier in the one world")

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
            x.client.cmd({"cmd": "shared_update_defer", "on": False})
            geo.settle(x.host, x.client)
        except Exception as e:
            r.ev["settleAfterMiss"] = short(e)
    r.ev["cellsPassed"], r.ev["wallS"] = r.passed, round(time.time() - r.t0, 1)
    print(f"EVIDENCE {rid}: {json.dumps(r.ev, sort_keys=True, default=str)}", flush=True)
    results[rid] = not r.fails
    print(f"PASS {rid}" if not r.fails else f"FAIL {rid}: {len(r.fails)} cell(s): " + " | ".join(r.fails), flush=True)

def setup(x, tag):
    """The client's option (synced from the host); the SHARED boot: S1/S2/S3 + the staged sergeants from the host's
    base_report."""
    x.option = wait_until(lambda: opt(x.client) is True, 10.0)[0] or opt(x.client)
    if tag != BOOT_SHARED[0]:
        seat = x.client.cmd({"cmd": "synced_options_state"}).get("localSeat")
        names = [b["name"] for b in x.client.ok({"cmd": "geo_state"})["bases"]]
        own, par = (x.client.ok({"cmd": "base_report", "base": n})["soldiers"] for n in ("ClientBase", "HostBase"))
        x.own, x.partner = [s["id"] for s in own if s["owner"] == seat], [s["id"] for s in par if s["owner"] != seat]
        x.hostBase, x.expect = names.index("HostBase") if "HostBase" in names else -1, {}
        info = {"option": x.option, "seat": seat, "bases": names, "own": x.own, "partner": x.partner}
        if len(x.own) < 3 or not x.partner or x.hostBase < 0:
            raise RuntimeError(f"no three own soldiers at ClientBase / a host soldier at HostBase: {info}")
        return info
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

def boot_separate():
    tag, (hp, cp, lp) = BOOT_SEPARATE
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
            print(f"[manual_promotion] {tag} shutdown: {short(e)}", flush=True)
        walls[tag] = round(time.time() - t0, 1)

ROWS_SHARED = (("client_promotes", lambda r, x: reach(r, x, x.client, x.S1, "client S1", "reachedHost",
                                                      "the client's promotion never reached the host", True)),
               ("host_promotes", lambda r, x: reach(r, x, x.host, x.S3, "host S3", "reachedClient",
                                                    "the host's promotion never reached the client", False)),
               ("one_opening_two_promotions", row_one_opening_two_promotions),
               ("nationality_change", row_nationality_change))
ROWS_SEPARATE = (("separate_own_soldier", row_separate_own_soldier), ("separate_openings", row_separate_openings),
                 ("separate_nationality", row_separate_nationality),
                 ("separate_partner_refused", row_separate_partner_refused), ("separate_reload", row_separate_reload),
                 ("separate_auto_promotions", row_separate_auto_promotions))

def main():
    t0, results, walls = time.time(), {}, {}
    boot(BOOT_SHARED[0], lambda: shared_fixture.bring_up(BOOT_SHARED[0], BOOT_SHARED[1], host_options={OPT: True}),
         ROWS_SHARED, results, walls)
    boot(BOOT_SEPARATE[0], boot_separate, ROWS_SEPARATE, results, walls)
    failed, n = ([rid for rid, _ in ROWS_SHARED + ROWS_SEPARATE if not results.get(rid)],
                 len(ROWS_SHARED + ROWS_SEPARATE))
    print(f"\ntest_manual_promotion: {n - len(failed)}/{n} passed (fail={failed}) walls {walls} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
