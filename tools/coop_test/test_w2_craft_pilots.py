"""W2-H16f (F6606; D226 a; Q1 a .. Q6 a; OC-H16f-1 = R-H16f-1; veto V1-V3): a craft pilot pick and a "Remove All
Pilots" made on one machine reach the shared world; a launch's automatic pilots reach the replica. Spec docs
rewrite/prompts/w2h16f_craft_pilots.md (e)-(f); TASK 0 rewrite/w2h16f-task0/CONSTANTS.md (R-H16f-T0-1..5 applied).
Mod Coop_Pilots_Test: the Skyranger gets two pilot seats (stock xcom1 crafts have none). Levers (test-only):
open_craft_pilots (the REAL CraftPilotsState), craft_pilots_probe (read-only; the list read through Craft::save),
set_craft_pilots (staging, THIS machine). Real input: click_widget "Add Pilot" -> the select list not hidden -> inject_input
at the probe's row of the soldier; click_widget "Remove All". Boot A (SHARED): H16f-1..7 (H16f-7, the launch, last);
Boot B (SEPARATE): H16f-8 (guard row). S0: set_craft_pilots on both (client first) to the row's start list.
RED (commit 1): H16f-1..7 fail on their named cell, H16f-8 passes; GREEN: all pass. "G:" cells are guards (CAPTURE on a
miss). EVIDENCE then PASS / FAIL per row; ONE run; exit 0 only if all pass, else 2.
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

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_Pilots_Test")
BOOT_A = ("w2h16fa", (49344, 49345, 47334))      # SHARED; lobby 47334 (spec F6709)
BOOT_B = ("w2h16fb", (49346, 49347, 47336))      # SEPARATE; lobby 47336
SKY = {"craftId": 1, "craftType": "STR_SKYRANGER"}
POLL_S, POLL_I, UI_S, BETWEEN_S, SETTLE_S = 3.0, 0.25, 3.0, 10.0, 0.25
GEO, CPS, CPSS = "GeoscapeState", "CraftPilotsState", "CraftPilotSelectState"

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

def keys(d, *ks): return {k: d.get(k) for k in ks}  # noqa: E704
def stack(gc): return session.states_stripped(gc)  # noqa: E704
def top(gc): return (stack(gc) or [""])[-1]  # noqa: E704
def rs(gc): return keys(gc.cmd({"cmd": "shared_resync_stats"}), "requests", "pending", "mismatches")  # noqa: E704
def ss(gc): return keys(gc.cmd({"cmd": "shared_stats"}), "cmd", "failCount", "applyCount", "lastFail")  # noqa: E704
def pil(gc): return probe(gc).get("pilots")  # noqa: E704

def probe(gc):
    p = gc.cmd(dict({"cmd": "craft_pilots_probe"}, **SKY))
    return dict(p, top=str(p.get("top", "")).replace("class OpenXcom::", ""))

def shown(gc):
    """CraftPilotSelectState on top with its TextList no longer hidden by the POPUP_BOTH window (R-H16f-T0-1)."""
    w = gc.cmd({"cmd": "list_widgets"})
    tl = [e for e in w.get("widgets", []) if "TextList" in e.get("type", "")]
    return tl[0] if (CPSS in w.get("state", "") and tl and tl[0].get("hidden") is False) else None

class Row:
    def __init__(self, rid):
        self.rid, self.t0, self.ev, self.fails, self.passed = rid, time.time(), {}, [], []
    def cell(self, name, ok, detail=""):
        (self.passed.append(name) if ok else self.fails.append(f"{name}: {detail}"))
        return ok

def guard(r, x, name, ok, detail):
    """A miss: CAPTURE both machines' stack, craft_pilots_probe, list_widgets of the top state, shared_stats."""
    if r.cell("G:" + name, ok, detail):
        return
    cap = {}
    for gc in (x.host, x.client):
        try:
            cap[gc.name] = {"stack": stack(gc), "probe": probe(gc), "list_widgets": gc.cmd({"cmd": "list_widgets"}),
                            "shared_stats": gc.cmd({"cmd": "shared_stats"}), "resync": rs(gc)}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {r.rid} (guard {name}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise GuardMiss(f"guard {name}")

def open_cps(r, x, gc, tag):
    o = gc.cmd(dict({"cmd": "open_craft_pilots"}, **SKY))
    guard(r, x, f"{tag} open", o.get("ok") is True, f"{o}")
    guard(r, x, f"{tag} pilots screen", wait_until(lambda: top(gc) == CPS, UI_S, 0.05)[0], f"stack {stack(gc)}")
    time.sleep(SETTLE_S)        # init() -> updateUI() sets the button visibilities on the frame after the push
    return probe(gc)

def pick(r, x, gc, sid, tag):
    """open_craft_pilots -> Add Pilot -> list shown -> real click on the soldier's row; guard: the clicker's own list."""
    ev = r.ev.setdefault("pick " + tag, {})
    p = open_cps(r, x, gc, tag)
    add = next((b for b in p.get("buttons") or [] if b.get("text") == "Add Pilot"), None)
    ev["before"] = {"pilots": p.get("pilots"), "add": add}
    guard(r, x, f"{tag} Add shown", bool(add) and add.get("visible") is True and add.get("hidden") is False,
          f"pilots {p.get('pilots')}, buttons {p.get('buttons')}")
    ev["add"] = cw = gc.cmd({"cmd": "click_widget", "match": "Add Pilot"})
    guard(r, x, f"{tag} select shown", wait_until(lambda: shown(gc), UI_S, 0.05)[0] and cw.get("ok") is True,
          f"click {cw}; stack {stack(gc)}")
    rows = probe(gc).get("rows") or []
    row = next((w for w in rows if w.get("name") == x.names.get(sid) and "wx" in w), None)
    ev["select"] = {"want": [sid, x.names.get(sid)], "rows": rows}
    guard(r, x, f"{tag} row of {sid}", row is not None, f"rows {rows}")
    ev["click"] = gc.cmd({"cmd": "inject_input", "kind": "click", "x": row["wx"], "y": row["wy"]})
    guard(r, x, f"{tag} back on CPS", wait_until(lambda: top(gc) == CPS, UI_S, 0.05)[0], f"stack {stack(gc)}")
    time.sleep(SETTLE_S)
    ev["after"] = a = pil(gc)
    guard(r, x, f"{tag} own change", sid in (a or []), f"{tag} pilots {a} (want {sid} in it)")

def clear(r, x, gc, own, tag):
    """open_craft_pilots -> Remove All Pilots; guard: the clicking machine's own pilot is gone from its list."""
    ev = r.ev.setdefault("clear " + tag, {})
    ev["before"] = open_cps(r, x, gc, tag).get("pilots")
    ev["click"] = cw = gc.cmd({"cmd": "click_widget", "match": "Remove All"})
    time.sleep(SETTLE_S)
    ev["after"] = a = pil(gc)
    guard(r, x, f"{tag} own change", cw.get("ok") is True and a is not None and own not in a,
          f"click {cw}; pilots {a} (want {own} gone)")

def poll(x, secs=POLL_S):
    """Both machines' pilot lists every 0.25 s; only the changes are kept."""
    out, n, t0 = [], 0, time.time()
    while time.time() - t0 < secs:
        s = {"host": pil(x.host), "client": pil(x.client)}
        if not out or {k: v for k, v in out[-1].items() if k != "t"} != s:
            out.append(dict(s, t=round(time.time() - t0, 2)))
        n += 1
        time.sleep(POLL_I)
    return {"samples": n, "changes": out}

def end(r, x):
    """Both machines' craft_pilots_probe at the row's end (pasted in EVIDENCE); returns the pilot lists."""
    e = {gc.name: probe(gc) for gc in (x.host, x.client)}
    r.ev["end"] = {n: keys(p, "top", "required", "pilots", "crew", "rows", "buttons") for n, p in e.items()}
    r.ev["end shared_stats"] = {gc.name: ss(gc) for gc in (x.host, x.client)}
    return {n: p.get("pilots") for n, p in e.items()}

def s0(r, x, start):
    """Row frame S0: both on the geoscape; set_craft_pilots on both (client first); guard: both lists equal the start."""
    h, c = x.host, x.client
    ok = wait_until(lambda: top(h) == GEO and top(c) == GEO, BETWEEN_S, 0.2)[0]
    guard(r, x, "start", ok, f"stacks {stack(h)} / {stack(c)}")
    st = {gc.name: gc.cmd(dict({"cmd": "set_craft_pilots", "pilots": list(start)}, **SKY)) for gc in (c, h)}
    r.ev["S0"] = d = {"start": list(start), "set": st, "pilots": {gc.name: pil(gc) for gc in (h, c)},
                      "req": {gc.name: rs(gc)["requests"] for gc in (h, c)}, "ss": {gc.name: ss(gc) for gc in (h, c)}}
    guard(r, x, "S0 equal", all(v.get("ok") is True for v in st.values())
          and d["pilots"]["host"] == d["pilots"]["client"] == list(start), f"{d}")
    return d

def close(r, x, d):
    """close_screens on both; the replica-repair guard: shared_resync_stats.requests unchanged since S0 (STOP-IF 5)."""
    r.ev["close"] = {gc.name: keys(gc.cmd({"cmd": "close_screens"}), "popped", "refused") for gc in (x.client, x.host)}
    now = {gc.name: rs(gc)["requests"] for gc in (x.host, x.client)}
    r.cell("clean", now == d["req"], f"resync requests S0 {d['req']} -> {now} (a rise = STOP-IF 5)")

def dialog_back(r, x, gc, tag):
    """A refused shared command raises CoopState on its sender: close it with coop_dialog_back (guard: back on GEO)."""
    wait_until(lambda: "CoopState" in top(gc), 1.0, 0.05)
    b = gc.cmd({"cmd": "coop_dialog_back"}) if "CoopState" in top(gc) else {"skipped": stack(gc)}
    r.ev[f"dialog back {tag}"] = b
    guard(r, x, f"{tag} refusal box closed", wait_until(lambda: top(gc) == GEO, UI_S, 0.05)[0], f"{b}; {stack(gc)}")

def reach(r, x, gc, sid, tag, why, host_apply):
    """H16f-1 / H16f-2: one machine picks its own soldier; both hold [sid] by the end of the poll."""
    d = s0(r, x, [])
    pick(r, x, gc, sid, tag)
    r.ev["poll"] = poll(x)
    v = end(r, x)
    a0, a1 = d["ss"]["host"]["applyCount"], ss(x.host)["applyCount"]
    r.cell("reached", v["host"] == [sid] and v["client"] == [sid] and (a1 == a0 + 1 or not host_apply),
           f"{tag}: host {v['host']}, client {v['client']} (want [{sid}] on both), host applyCount {a0} -> {a1}"
           f"{' (want +1)' if host_apply else ''}: {why}")
    close(r, x, d)

def remove(r, x, gc, own, keep, tag):
    """H16f-3 / H16f-4: S0 [H1, C1]; one machine's Remove All Pilots; both keep only the partner's pilot."""
    d = s0(r, x, [x.H1, x.C1])
    clear(r, x, gc, own, tag)
    r.ev["poll"] = poll(x)
    v = end(r, x)
    me, other = ("client", "host") if gc is x.client else ("host", "client")
    r.cell("keepsPartner", v[me] == [keep], f"{me} {v[me]} (want [{keep}]): the {me}'s Remove All took the "
           f"partner's pilot (aud-E1-11)")
    r.cell("applied", v[other] == [keep], f"{other} {v[other]} (want [{keep}]): the {me}'s Remove All stayed local")
    close(r, x, d)

def row_h16f_5(r, x):
    """The host refuses an add of the partner's soldier ("not your soldier"); the control (own soldier) lands."""
    h, c = x.host, x.client
    d = s0(r, x, [])
    r.ev["reset"] = [gc.ok({"cmd": "shared_reset_stats"}) for gc in (h, c)]
    def send(sid): return c.cmd({"cmd": "shared_cmd", "jcmd": "craft_pilots", "baseId": 0,  # noqa: E704
                                 "payload": dict(SKY, op="add", soldierId=sid)})
    r.ev["send H1"] = send(x.H1)
    ok, _ = wait_until(lambda: ss(c)["failCount"] >= 1, UI_S)
    r.ev["refusal"] = f1 = ss(c)
    dialog_back(r, x, c, "H1")
    r.ev["after refusal"] = p1 = {gc.name: pil(gc) for gc in (h, c)}
    r.cell("refusal", ok and f1.get("lastFail") == "not your soldier" and p1["host"] == [] and p1["client"] == [],
           f"client failCount {f1.get('failCount')}, lastFail {f1.get('lastFail')!r} (want 'not your soldier'), "
           f"pilots {p1} (want [] on both)")
    fc = ss(c)["failCount"]
    r.ev["send C1"] = send(x.C1)
    r.ev["poll"] = poll(x)
    if ss(c)["failCount"] > fc:
        r.ev["control refusal"] = ss(c)
        dialog_back(r, x, c, "C1")
    v = end(r, x)
    r.cell("control", v["host"] == [x.C1] and v["client"] == [x.C1],
           f"host {v['host']}, client {v['client']} (want [{x.C1}] on both): the control pick never landed")
    close(r, x, d)

def row_h16f_6(r, x):
    """The last seat, both at once: the client's applies held; the host takes H2, the client (stale) takes C1."""
    h, c = x.host, x.client
    d = s0(r, x, [x.H1])
    try:
        r.ev["defer on"] = dn = c.cmd({"cmd": "shared_update_defer", "on": True})
        guard(r, x, "defer on", dn.get("deferred") is True, f"{dn}")
        a0 = ss(h)["applyCount"]
        pick(r, x, h, x.H2, "host H2")
        guard(r, x, "host [H1, H2]", (hp := pil(h)) == [x.H1, x.H2], f"host {hp}")
        ok = wait_until(lambda: ss(h)["applyCount"] >= a0 + 1, 2.0)[0]
        r.ev["host applyCount +1 (wait; EVIDENCE only)"] = {"ok": ok, "before": a0, "now": ss(h)["applyCount"]}
        pick(r, x, c, x.C1, "client C1")      # its stale list [H1] shows Add: guard "client C1 Add shown" + EVIDENCE
        time.sleep(1.0)
    finally:
        r.ev["defer off"] = c.cmd({"cmd": "shared_update_defer", "on": False})
    r.ev["poll"] = poll(x)
    v = end(r, x)
    r.cell("agree", v["host"] == [x.H1, x.H2] and v["client"] == [x.H1, x.H2],
           f"host {v['host']}, client {v['client']} (want [{x.H1}, {x.H2}] on both): two pilots for one seat; "
           f"the worlds disagree")
    close(r, x, d)

def sky_status(gc):
    return next((cr.get("status") for b in gc.ok({"cmd": "geo_state"}).get("bases") or [] for cr in b.get("crafts") or []
                 if cr.get("id") == SKY["craftId"] and cr.get("type") == SKY["craftType"]), None)

def row_h16f_7(r, x):
    """The host launches the Skyranger (REAL ConfirmDestinationState): its automatic pilots reach the client too."""
    h, c = x.host, x.client
    d = s0(r, x, [])
    b0 = h.ok({"cmd": "geo_state"})["bases"][0]
    r.ev["order"] = o = h.cmd({"cmd": "craft_order", "order": "target", "craft_id": SKY["craftId"],
                               "craft_type": SKY["craftType"], "lon": b0["lon"] + 0.05, "lat": b0["lat"] + 0.03})
    ok = wait_until(lambda: sky_status(h) == "STR_OUT" and sky_status(c) == "STR_OUT", 5.0)[0]
    guard(r, x, "launched", o.get("ok") is True and ok, f"order {o}; status host {sky_status(h)}, client {sky_status(c)}")
    r.ev["poll"] = poll(x)
    v = end(r, x)
    auto = list(reversed(x.crew))[:2]
    guard(r, x, "host automatic pilots", v["host"] == auto, f"host {v['host']} (want {auto}, the crew's rear)")
    r.cell("launchPilots", v["client"] == auto, f"client {v['client']}, host {v['host']} (want {auto} on both): "
           f"after a launch the client's craft shows no pilots (F6703)")
    close(r, x, d)

def row_h16f_8(r, x):
    """SEPARATE: the client's pick on its own base's Skyranger stays local; no shared command on either machine."""
    h, c = x.host, x.client
    guard(r, x, "start", wait_until(lambda: top(h) == GEO and top(c) == GEO, BETWEEN_S, 0.2)[0],
          f"stacks {stack(h)} / {stack(c)}")
    p0, sid = probe(c), (x.crew[0] if x.crew else None)
    r.ev["S0"] = {"client": keys(p0, "required", "pilots", "crew"), "id": sid, "name": x.names.get(sid)}
    guard(r, x, "S0", p0.get("required") == 2 and sid is not None and p0.get("pilots") == [], f"{r.ev['S0']}")
    s_0 = {gc.name: ss(gc) for gc in (h, c)}
    pick(r, x, c, sid, "client own")
    time.sleep(2.0)
    a, s_1 = pil(c), {gc.name: ss(gc) for gc in (h, c)}
    r.ev["end"] = {"client": probe(c), "shared_stats": {"S0": s_0, "end": s_1}}
    r.cell("clientOwn", a == [sid], f"client {a} (want [{sid}])")
    r.cell("noCmd", all(keys(s_0[n], "cmd", "applyCount") == keys(s_1[n], "cmd", "applyCount") for n in s_0),
           f"shared_stats {s_0} -> {s_1} (want cmd / applyCount unchanged)")
    r.ev["close"] = {gc.name: keys(gc.cmd({"cmd": "close_screens"}), "popped", "refused") for gc in (c, h)}

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
            for gc in (x.client, x.host):
                ("CoopState" in top(gc)) and gc.cmd({"cmd": "coop_dialog_back"})
                gc.cmd({"cmd": "close_screens"})
        except Exception as e:
            r.ev["settleAfterMiss"] = short(e)
    r.ev["cellsPassed"], r.ev["wallS"] = r.passed, round(time.time() - r.t0, 1)
    print(f"EVIDENCE {rid}: {json.dumps(r.ev, sort_keys=True, default=str)}", flush=True)
    results[rid] = not r.fails
    print(f"PASS {rid}" if not r.fails else f"FAIL {rid}: {len(r.fails)} cell(s): " + " | ".join(r.fails), flush=True)

def setup(x, tag):
    """Boot A: C1, C2 / H1, H2 from base_report owners; Boot B: the client's own crew by craft (R-H16f-T0-5)."""
    h, c = x.host, x.client
    pr = {gc.name: probe(gc) for gc in (h, c)}
    info = {"probe": {n: keys(p, "required", "pilots", "crew", "top") for n, p in pr.items()}}
    if tag == BOOT_B[0]:
        br = c.ok({"cmd": "base_report"})      # no args: the client's own base (index 0)
        x.names = {s["id"]: s["name"] for s in br["soldiers"]}
        x.crew = [e["id"] for e in pr["client"].get("crew") or []]
        info.update(base=br.get("name"), crew=x.crew, names=x.names)
        if pr["client"].get("required") != 2 or pr["client"].get("pilots") != [] or not x.crew:
            raise RuntimeError(f"boot B guard (client's own Skyranger: two seats, no pilot, a crew): {info}")
        return info
    seat = {gc.name: gc.cmd({"cmd": "synced_options_state"}).get("localSeat") for gc in (h, c)}
    br = h.ok({"cmd": "base_report"})
    owner = {s["id"]: s["owner"] for s in br["soldiers"]}
    x.names = {s["id"]: s["name"] for s in br["soldiers"]}
    x.crew = [e["id"] for e in pr["host"].get("crew") or []]
    cl, ho = ([i for i in x.crew if owner.get(i) == seat[k]] for k in ("client", "host"))
    info.update(seats=seat, base=br.get("name"), owners=owner, names=x.names, crew=x.crew, client=cl, host=ho)
    ok = (all(p.get("required") == 2 and p.get("pilots") == [] and [e["id"] for e in p.get("crew") or []] == x.crew
              for p in pr.values()) and x.crew == list(range(1, 9)) and len(cl) >= 2 and len(ho) >= 2)
    if not ok:
        raise RuntimeError(f"boot A guard (the two seats on both, no pilot, crew 1-8, two soldiers per seat): {info}")
    x.C1, x.C2, x.H1, x.H2 = cl[0], cl[1], ho[0], ho[1]
    info.update(C1=x.C1, C2=x.C2, H1=x.H1, H2=x.H2)
    return info

def boot_b():
    tag, (hp, cp, lp) = BOOT_B
    host = GameClient("host", hp, make_user_dir(f"{tag}_host", mods=(MOD,)))
    client = GameClient("client", cp, make_user_dir(f"{tag}_client", mods=(MOD,)))
    try:
        [f() for f in (host.spawn, client.spawn, host.connect, client.connect)]
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
        print(f"CAPTURE {tag} (boot miss): {short(e, 3000)}", flush=True)
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
            print(f"[w2h16f] {tag} shutdown: {short(e)}", flush=True)
        walls[tag] = round(time.time() - t0, 1)

ROWS_A = (("H16f-1", lambda r, x: reach(r, x, x.client, x.C1, "client C1",
                                        "the client's pilot pick stayed on its machine (F6606)", True)),
          ("H16f-2", lambda r, x: reach(r, x, x.host, x.H1, "host H1", "the host's pick never reached the client", False)),
          ("H16f-3", lambda r, x: remove(r, x, x.client, x.C1, x.H1, "client")),
          ("H16f-4", lambda r, x: remove(r, x, x.host, x.H1, x.C1, "host")),
          ("H16f-5", row_h16f_5), ("H16f-6", row_h16f_6), ("H16f-7", row_h16f_7))
ROWS_B = (("H16f-8", row_h16f_8),)

def main():
    t0, results, walls = time.time(), {}, {}
    boot(BOOT_A[0], lambda: shared_fixture.bring_up(BOOT_A[0], BOOT_A[1], mods=(MOD,)), ROWS_A, results, walls)
    boot(BOOT_B[0], boot_b, ROWS_B, results, walls)
    failed, n = [rid for rid, _ in ROWS_A + ROWS_B if not results.get(rid)], len(ROWS_A + ROWS_B)
    print(f"\ntest_w2_craft_pilots: {n - len(failed)}/{n} passed (fail={failed}) walls {walls} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
