"""W2-H15 - test_w2_geo_event_replica.py (SHARED): a geoscape event's reward is applied once, by the host, and the
second player sees the same window in its own language (F3261; D226 a; Q1 a / Q2 b, AMENDMENT A1, R-H15-1/2). Spec docs
rewrite/prompts/w2h15_event_replica.md (e)-(f); docs rewrite/w2h15-task0/CONSTANTS.md. Mod Coop_GeoEvent_Test.
Trigger: host research_start STR_H15_TRG_* (cost 1, 2 scientists), skip_ingame_time(3 days, speed 5, interest
GeoscapeEventState, real_timeout 150) -> the host's window at 00:30; both polled every 0.1 s for 3 s. Frame (f): S0,
fundsSeen, same window (equal picks + own render), clean (settle + 60 min + 4 s: requests == S0's, checksum equal).
Boot A (host de): H15-1, -2, -4, -5 (+ H15-8 on its windows), -6, -7; Boot B (no instant delivery): H15-3.
RED (commit 1): H15-1 fails on the replica's funds S0 + 1,000,000 (host at S0); H15-2..7 on the replica's funds above
the host's (fundsSeen) or requests above S0; H15-8 passes (guard row, F5664). "G:" cells are guards (CAPTURE on a miss).
GREEN (commit 2): all pass. EVIDENCE then PASS / FAIL per row; ONE foreground run; exit 0 only if all pass, else 2.
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

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_GeoEvent_Test")
BOOT_A = ("w2h15a", (49270, 49271, 47270), {"language": "de"})      # F5657; ports = labels (F5662)
BOOT_B = ("w2h15b", (49272, 49273, 47272), {"oxceGeoscapeEventsInstantDelivery": False})
EV = "GeoscapeEventState"
RES = ["STR_H15_RES_A", "STR_H15_RES_B", "STR_H15_RES_C"]
TRG = {k: "STR_H15_TRG_" + k for k in ("FUNDS", "TRANSFER", "INVERT", "REGION", "RESEARCH", "INSTANT")}
NAMES = RES + sorted(TRG.values())
ITEMS = ["STR_GRENADE", "STR_PISTOL", "STR_PISTOL_CLIP"]
TR_EN = {"STR_GRENADE": "Grenade", "STR_PISTOL": "Pistol"}          # the replica's tr() (xcom1 en-US)
REGION_T, REGION_M = "H15 region event: {}", "Points went to {}."   # the mod's en-US.yml (the replica)
REGION_T_DE = "H15 Regionsereignis: {}"                             # the mod's de.yml (the Boot A host)
BIG, SMALL = 1000000, 1000                                          # the events' funds
EVENT_IDS = ("STR_SOLDIER", "STR_SKYRANGER", "STR_INTERCEPTOR")    # eventLogic's getId: genSoldier, the spawned craft
POLL_S, POLL_I, BETWEEN_S = 3.0, 0.1, 30
CLEAN_S = 4.0         # > the 3000 ms mismatch debounce (P10 F5510) and the measured 3.27 s worst case (F5709)

class GuardMiss(Exception):
    """A guard failed: the row ends after its CAPTURE line."""

def short(e, n=500):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."

def wait_until(pred, timeout, interval=0.2):
    t0 = time.time()
    while not pred() and time.time() - t0 < timeout:
        time.sleep(interval)
    return bool(pred())

def probe(gc):
    return gc.cmd({"cmd": "geo_event_probe", "names": NAMES, "items": ITEMS, "tail": 8})

def funds(gc):
    return gc.cmd({"cmd": "geo_state"}).get("funds")     # None while a restream replaces the world

def rs(gc):
    r = gc.cmd({"cmd": "shared_resync_stats"})
    return {k: r.get(k) for k in ("requests", "pending", "mismatches")}

def chk(gc):
    return {k: v for k, v in gc.cmd({"cmd": "shared_checksum"}).items() if k.startswith("chk")}

def stack(gc):
    return session.states_stripped(gc)

def picks(p):
    return (p.get("event") or {}).get("picks") or {}

class Row:
    def __init__(self, rid):
        self.rid, self.t0, self.ev, self.fails, self.passed = rid, time.time(), {}, [], []
    def cell(self, name, ok, detail=""):
        (self.passed.append(name) if ok else self.fails.append(f"{name}: {detail}"))
        return ok

def guard(r, x, name, ok, detail):
    if r.cell("G:" + name, ok, detail):
        return
    cap = {}
    for gc in (x.host, x.client):
        try:
            cap[gc.name] = {"geo_event_probe": probe(gc), "geo_state": gc.cmd({"cmd": "geo_state"}),
                            "shared_resync_stats": gc.cmd({"cmd": "shared_resync_stats"}), "stack": stack(gc)}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {r.rid} (guard {name}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise GuardMiss(f"guard {name}")

def start(r, x):
    """Between rows (<= 30 s): replica pending false and both tops GeoscapeState; then S0 on both."""
    h, c = x.host, x.client
    ok = wait_until(lambda: not rs(c)["pending"] and stack(h)[-1:] == ["GeoscapeState"]
                    and stack(c)[-1:] == ["GeoscapeState"], BETWEEN_S)
    guard(r, x, "start", ok, f"stacks {stack(h)} / {stack(c)}, replica {rs(c)}")
    s0 = {gc.name: {"funds": funds(gc), "probe": probe(gc), "chk": chk(gc), "rs": rs(gc)} for gc in (h, c)}
    r.ev["S0"] = {n: {"funds": v["funds"], "requests": v["rs"]["requests"], "chk": v["chk"]} for n, v in s0.items()}
    return s0

def poll(x, secs=POLL_S):
    """Both machines every 0.1 s: funds, eventStates, the replica's requests; the first open window per machine."""
    out, win, t0 = [], {}, time.time()
    while time.time() - t0 < secs:
        s = {"t": round(time.time() - t0, 2)}
        for gc, k in ((x.host, "h"), (x.client, "c")):
            p = gc.cmd({"cmd": "geo_event_probe"})
            s[k + "F"], s[k + "Ev"] = funds(gc), p.get("eventStates")
            if p.get("eventStates") and k not in win:
                win[k] = p.get("event")
        out.append(dict(s, cReq=rs(x.client)["requests"]))
        time.sleep(POLL_I)
    return out, win

def seen(samples, s0f):
    v = lambda k: sorted(set(s[k] for s in samples), key=str)  # noqa: E731 - None while a restream runs (F5735)
    return {"replica": v("cF"), "host": v("hF"), "requests": v("cReq"), "n": len(samples), "S0": s0f}

def ids_cell(r, s0, hp, cp):
    """R-H15-1 (F5727): only the counters eventLogic mints that moved on the host (S0 -> hit); the rest EVIDENCE."""
    h0, h1, c1 = s0["host"]["probe"]["ids"], hp["ids"], cp["ids"]
    keys, v = sorted(k for k in EVENT_IDS if h0.get(k) != h1.get(k)), lambda k: [h0.get(k), h1.get(k), c1.get(k)]
    r.ev["ids [S0, host, replica]"] = ev = {"compared": {k: v(k) for k in keys}, "excluded (R-H15-1)":
                                            {k: v(k) for k in sorted(set(h1) | set(c1)) if k not in keys}}
    r.cell("ids", bool(keys) and all(h1.get(k) == c1.get(k) for k in keys), f"{ev}")

def own_render(ev, rule):
    """The replica's own tr() of its picks (Q2 b): region templates + place, else the rule id; rows [tr(id), qty]."""
    pk, place = ev.get("picks") or {}, ev.get("place")
    title, msg = (REGION_T.format(place), REGION_M.format(place)) if pk.get("region") else (rule, rule)
    return {"title": title, "message": msg, "rows": [[TR_EN.get(i, i), str(q)] for i, q in pk.get("rows") or []]}

def trigger(r, x, key, reward, s0):
    """The proven recipe; host guards: the hit, eventStates 1, the reward."""
    h, c, topic = x.host, x.client, TRG[key]
    r.ev["research_start"] = h.cmd({"cmd": "research_start", "topic": topic, "scientists": 2})
    listed = lambda gc: any(p.get("name") == topic for b in gc.ok({"cmd": "geo_state"})["bases"]  # noqa: E731
                            for p in b.get("research", []))
    r.ev["listed"] = wait_until(lambda: listed(h) and listed(c), 5, 0.1)
    t = time.time()
    sk = geo.skip_ingame_time(h, c, 60 * 24 * 3, speed_idx=5, interest=geo.popup(EV), real_timeout=150)
    r.ev["skip"] = {"hit": sk.get("hit"), "gameMin": sk.get("game_minutes"), "s": round(time.time() - t, 1)}
    hp, hf = probe(h), funds(h)
    guard(r, x, "hit", sk.get("hit") is not None and stack(h)[-1:] == [EV], f"skip {r.ev['skip']}, host {stack(h)}")
    guard(r, x, "hostEventStates", hp.get("eventStates") == 1, f"host eventStates {hp.get('eventStates')}")
    guard(r, x, "hostReward", hf == s0["host"]["funds"] + reward, f"host funds {s0['host']['funds']} -> {hf}")

def world_diff(r, x):
    r.ev["worldDiff"] = (d := shared_fixture.world_diff(x.host, x.client))[:12]
    r.cell("worldDiff", d == [], f"{len(d)} field(s): {d[:6]}")

def clean(r, x, s0):
    h, c = x.host, x.client
    st, sk = geo.settle(h, c), geo.skip_ingame_time(h, c, 60, speed_idx=3)
    time.sleep(CLEAN_S)
    req, ch, cc = rs(c)["requests"], chk(h), chk(c)
    r.ev["clean"] = {"dismissed": st.get("dismissed"), "gameMin": sk.get("game_minutes"), "requests": req,
                     "chkHost": ch, "chkClient": cc, "stacks": [stack(h), stack(c)]}
    r.cell("clean", req == s0["client"]["rs"]["requests"] and bool(ch) and ch == cc,
           f"replica requests {s0['client']['rs']['requests']} -> {req}, chk host {ch} / replica {cc}")

def common(r, x, key, reward, rule, s0=None):
    """S0, the trigger + guards, the 3 s poll; cells fundsSeen (the named RED), eventStates, sameWindow."""
    s0 = s0 or start(r, x)
    trigger(r, x, key, reward, s0)
    samples, _win = poll(x)
    hp, cp, topic = probe(x.host), probe(x.client), TRG[key]   # read after the poll: both windows open, clocks stopped
    r.ev["event"] = {"host": hp.get("event"), "replica": cp.get("event"),
                     "eventStates": [hp.get("eventStates"), cp.get("eventStates")]}
    guard(r, x, "triggerResearched", hp["research"][topic]["researched"] and cp["research"][topic]["researched"],
          f"{topic} host {hp['research'][topic]} replica {cp['research'][topic]}")
    r.ev["fundsSeen"] = seen(samples, [s0["host"]["funds"], s0["client"]["funds"]])
    r.cell("fundsSeen", all(s["cF"] == s["hF"] for s in samples),
           f"the replica applied the reward on top of the host's: {r.ev['fundsSeen']}")
    r.cell("eventStates", hp.get("eventStates") == 1 and cp.get("eventStates") == 1,
           f"host {hp.get('eventStates')} replica {cp.get('eventStates')}")
    want = own_render(ce, rule) if (ce := cp.get("event") or {}) else None
    r.cell("sameWindow", bool(ce) and picks(hp) == picks(cp) and ce.get("texts") == want,
           f"host picks {picks(hp)} / replica picks {picks(cp)}; replica texts {ce.get('texts')} vs own render {want}")
    return s0, hp, cp

def row_h15_1(r, x):
    h, c, s0 = x.host, x.client, start(r, x)
    r.ev["alert"] = h.cmd({"cmd": "shared_alert", "cls": EV, "msg": "STR_H15_EV_FUNDS"})
    samples, win = poll(x)
    f0, evmax = s0["host"]["funds"], [max(s["hEv"] for s in samples), max(s["cEv"] for s in samples)]
    r.ev["fundsSeen"] = seen(samples, f0)
    r.ev["window"] = {"replica": win.get("c"), "host": win.get("h"), "eventStatesMax": evmax}
    r.cell("fundsSeen", all(s["cF"] == s["hF"] == f0 for s in samples),
           f"the replica ran the event's logic: {r.ev['fundsSeen']}")
    ce = win.get("c") or {}
    r.cell("replicaWindow", evmax[1] == 1 and picks({"event": ce}).get("region") == "" and
           picks({"event": ce}).get("rows") == [] and (ce.get("texts") or {}).get("title") == "STR_H15_EV_FUNDS",
           f"replica window {ce}, eventStates max {evmax[1]}")
    r.cell("hostNoWindow", evmax[0] == 0, f"host eventStates max {evmax[0]}")
    if stack(c)[-1:] == [EV]:
        r.ev["dismiss"] = c.cmd({"cmd": "dismiss_popup"}).get("handled")
    clean(r, x, s0)

def row_h15_2(r, x):
    s0, _hp, _cp = common(r, x, "FUNDS", BIG, "STR_H15_EV_FUNDS")
    world_diff(r, x)
    clean(r, x, s0)

def row_h15_3(r, x):
    s0, hp, cp = common(r, x, "TRANSFER", SMALL, "STR_H15_EV_TRANSFER")
    ht, ct = hp["hq"]["transfers"], cp["hq"]["transfers"]
    r.ev["transfers"] = {"host": ht, "replica": ct}
    key = lambda t: json.dumps(t, sort_keys=True)  # noqa: E731 - the order is not asserted (F5608)
    r.cell("transfers", sorted(ht, key=key) == sorted(ct, key=key), f"host {ht} / replica {ct}")
    ids_cell(r, s0, hp, cp)
    st, sk = geo.settle(x.host, x.client), geo.skip_ingame_time(x.host, x.client, 25 * 60)
    r.ev["after25h"] = {"dismissed": [st.get("dismissed"), sk.get("dismissed")], "gameMin": sk.get("game_minutes")}
    world_diff(r, x)
    clean(r, x, s0)

def row_h15_4(r, x):
    p0 = (s0 := start(r, x))["host"]["probe"]
    sky = next(k for k in sorted(p0["craftItems"]) if k.startswith("STR_SKYRANGER#"))
    st0, sk0 = p0["stores"][x.hq]["STR_GRENADE"], p0["craftItems"][sky]["STR_GRENADE"]   # read, never assumed
    st1 = max(0, st0 - 7)
    sk1 = sk0 - min(sk0, 7 - (st0 - st1))   # invert: stores first, then crafts (GE :360-389)
    want = [["STR_GRENADE", -((st0 - st1) + (sk0 - sk1))]]
    r.ev["grenadesS0"] = {"stores": st0, sky: sk0, "want": [st1, sk1], "rows": want}
    s0, hp, cp = common(r, x, "INVERT", SMALL, "STR_H15_EV_INVERT", s0)
    got = [[p["stores"][x.hq]["STR_GRENADE"], p["craftItems"][sky]["STR_GRENADE"]] for p in (hp, cp)]
    r.ev["grenades"] = got
    r.cell("grenades", got == [[st1, sk1], [st1, sk1]], f"[stores, {sky}] host/replica {got} (want {[st1, sk1]})")
    rows = [picks(p).get("rows") for p in (hp, cp)]
    r.cell("rows", rows == [want, want], f"picks.rows host/replica {rows} (want {want})")
    world_diff(r, x)
    clean(r, x, s0)

def row_h15_5(r, x):
    s0, hp, cp = common(r, x, "REGION", SMALL, "STR_H15_EV_REGION")
    x.h158 = (hp, cp)        # H15-8 reads these, taken on the open windows before this row's clean
    pk = picks(hp)
    r.cell("picksSet", bool(pk.get("region")) and isinstance(pk.get("city"), int) and pk["city"] >= 0,
           f"host picks {pk}")
    r0 = s0["host"]["probe"]["regions"]
    moved = {k: v - r0.get(k, 0) for k, v in hp["regions"].items() if v != r0.get(k, 0)}
    r.ev["regions"] = {"S0": r0, "host": hp["regions"], "replica": cp["regions"], "hostMoved": moved,
                       "researchScore": [hp["researchScore"], cp["researchScore"]]}
    r.cell("regions", hp["regions"] == cp["regions"] and moved == {pk.get("region"): 77},
           f"host moved {moved} (want {{{pk.get('region')}: 77}}); equal {hp['regions'] == cp['regions']}")
    r.cell("researchScore", hp["researchScore"] == cp["researchScore"], f"{r.ev['regions']['researchScore']}")
    clean(r, x, s0)

def row_h15_8(r, x):
    """Guard row (F5664): each machine draws the window in its own language; the picks cell is EVIDENCE only."""
    he, ce = ((x.h158[0].get("event") or {}), (x.h158[1].get("event") or {})) if x.h158 else ({}, {})
    ht, ct = he.get("texts") or {}, ce.get("texts") or {}
    r.ev.update({"host": he, "replica": ce, "picksEqual (EVIDENCE, GREEN-only)": he.get("picks") == ce.get("picks")})
    r.cell("replicaPlace", bool(ce.get("place")), f"replica place {ce.get('place')!r} (STOP-IF 3)")
    r.cell("replicaTitle", ct.get("title") == REGION_T.format(ce.get("place")), f"{ct.get('title')!r}")
    r.cell("replicaMessage", ct.get("message") == REGION_M.format(ce.get("place")), f"{ct.get('message')!r}")
    r.cell("hostTitle", bool(he.get("place")) and ht.get("title") == REGION_T_DE.format(he.get("place")),
           f"{ht.get('title')!r} place {he.get('place')!r}")
    r.cell("titlesDiffer", ct.get("title") != ht.get("title"), f"{ct.get('title')!r} == {ht.get('title')!r}")

def row_h15_6(r, x):
    s0, hp, cp = common(r, x, "RESEARCH", SMALL, "STR_H15_EV_RESEARCH")
    hr, cr = ({n: p["research"][n] for n in RES} for p in (hp, cp))
    cr2 = [chk(x.host).get("chkResearch"), chk(x.client).get("chkResearch")]
    names = [n for n in (picks(hp).get("research"), picks(hp).get("bonus")) if n]     # R-H15-2 (F5728)
    dg = [[e for e in p["diary"]["tail"] if e["name"] in names] for p in (hp, cp)]
    ex = [[e for e in p["diary"]["tail"] if e["name"] not in names] for p in (hp, cp)]
    r.ev["research"] = {"host": hr, "replica": cr, "chkResearch": cr2, "researchScore": [hp["researchScore"],
                        cp["researchScore"]], "diary": {"names": names, "host": dg[0], "replica": dg[1],
                                                        "excluded (R-H15-2) [host, replica]": ex}}
    one = lambda d: d[RES[0]]["researched"] and [d[n]["researched"] for n in RES[1:]].count(True) == 1  # noqa: E731
    r.cell("researched", one(hr) and one(cr) and all(hr[n]["researched"] == cr[n]["researched"] for n in RES),
           f"host {hr} / replica {cr}")
    r.cell("statusPopped", all((hr[n]["status"], hr[n]["popped"]) == (cr[n]["status"], cr[n]["popped"]) for n in RES),
           f"host {hr} / replica {cr}")
    r.cell("diaryTail", bool(dg[0]) and dg[0] == dg[1], f"{r.ev['research']['diary']}")
    r.cell("researchScore", hp["researchScore"] == cp["researchScore"], f"{r.ev['research']['researchScore']}")
    hk, ck = picks(hp), picks(cp)
    r.cell("picksResearch", (hk.get("research"), hk.get("bonus")) == (ck.get("research"), ck.get("bonus")),
           f"host {hk} / replica {ck}")
    r.cell("chkResearch", cr2[0] == cr2[1], f"{cr2}")
    clean(r, x, s0)

def row_h15_7(r, x):
    s0, hp, cp = common(r, x, "INSTANT", SMALL, "STR_H15_EV_INSTANT")
    c0 = s0["host"]["probe"]["hq"]["crafts"]
    new = [k for k in hp["hq"]["crafts"] if k not in c0]
    r.ev["crafts"] = {"S0": c0, "host": hp["hq"]["crafts"], "replica": cp["hq"]["crafts"], "hostNew": new}
    r.cell("crafts", len(new) == 1 and new[0]["type"] == "STR_INTERCEPTOR" and hp["hq"]["crafts"] == cp["hq"]["crafts"],
           f"host new {new}; equal {hp['hq']['crafts'] == cp['hq']['crafts']}")
    ids_cell(r, s0, hp, cp)
    p0 = s0["host"]["probe"]["stores"][x.hq]["STR_PISTOL"]
    got = [p["stores"][x.hq]["STR_PISTOL"] for p in (hp, cp)]
    r.ev["pistols"] = {"S0": p0, "got": got}
    r.cell("pistols", got == [p0 + 2, p0 + 2], f"host/replica {got} (want {p0 + 2})")
    rows = [picks(p).get("rows") for p in (hp, cp)]
    r.cell("rows", rows == [[["STR_PISTOL", 2]]] * 2, f"picks.rows host/replica {rows}")
    world_diff(r, x)
    clean(r, x, s0)

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
            geo.settle(x.host, x.client)
        except Exception as e:
            r.ev["settleAfterMiss"] = short(e)
    r.ev["cellsPassed"], r.ev["wallS"] = r.passed, round(time.time() - r.t0, 1)
    print(f"EVIDENCE {rid}: {json.dumps(r.ev, sort_keys=True, default=str)}", flush=True)
    results[rid] = not r.fails
    print(f"PASS {rid}" if not r.fails else f"FAIL {rid}: {len(r.fails)} cell(s): " + " | ".join(r.fails), flush=True)

def boot(spec, rows, results, walls):
    tag, ports, opts = spec
    t0 = time.time()
    try:
        js = shared_fixture.bring_up(tag, ports, mods=(MOD,), host_options=opts)
        x = SimpleNamespace(host=js.host, client=js.client, h158=None,
                            hq=js.host.ok({"cmd": "geo_state"})["bases"][0]["name"])
    except Exception as e:
        print(f"CAPTURE {tag} (boot miss): {short(e, 1500)}", flush=True)
        for rid, _fn in rows:
            results[rid] = False
            print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot", flush=True)
        walls[tag] = round(time.time() - t0, 1)
        return
    print(f"[w2h15] {tag} bring-up {time.time() - t0:.1f}s hq {x.hq}", flush=True)
    try:
        for rid, fn in rows:
            run_one(rid, fn, x, results)
    finally:
        try:
            js.shutdown()
        except Exception as e:
            print(f"[w2h15] {tag} shutdown: {short(e)}", flush=True)
    walls[tag] = round(time.time() - t0, 1)

ROWS_A = (("H15-1", row_h15_1), ("H15-2", row_h15_2), ("H15-4", row_h15_4), ("H15-5", row_h15_5),
          ("H15-8", row_h15_8), ("H15-6", row_h15_6), ("H15-7", row_h15_7))
ROWS_B = (("H15-3", row_h15_3),)

def main():
    t0, results, walls = time.time(), {}, {}
    for spec, rows in ((BOOT_A, ROWS_A), (BOOT_B, ROWS_B)):
        boot(spec, rows, results, walls)
    order = [rid for rid, _ in ROWS_A + ROWS_B]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_w2_geo_event_replica: {len(order) - len(failed)}/{len(order)} passed (fail={failed}) walls {walls} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
