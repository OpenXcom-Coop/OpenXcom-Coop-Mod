"""test_geo_event_replica.py (SHARED): a geoscape event's reward is applied once, by the host, and the
second player sees the same window in its own language, built from the host's picks. Mod Coop_GeoEvent_Test.
Trigger: host research_start STR_GEOEV_TRG_* (cost 1, 2 scientists), skip_ingame_time(3 days, speed 5, interest
GeoscapeEventState, real_timeout 150) -> the host's window at 00:30; both polled every 0.1 s for 3 s. Each row checks:
the baseline, fundsSeen, the same window (equal picks + the replica's own render), clean (settle + 60 min + 4 s:
requests == the baseline's, checksum equal).
German-host boot (host language de): alert_window_only, funds_reward, item_removal_reward, region_reward (+
own_language_window on its windows), research_reward, instant_craft_reward. Queued-delivery boot (no instant delivery):
transfer_reward.
When broken (the replica runs the event's logic itself): alert_window_only fails on the replica's funds baseline +
1,000,000 (host at the baseline); the other reward rows fail on the replica's funds above the host's (fundsSeen) or
requests above the baseline; own_language_window passes (guard row). "guard:" cells are guards (CAPTURE on a miss).
With the fix: all pass. EVIDENCE then PASS / FAIL per row; ONE foreground run; exit 0 only if all pass, else 2.
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
BOOT_GERMAN_HOST = ("geo_event_replica_de", (49270, 49271, 47270), {"language": "de"})      # the host in German
BOOT_QUEUED_DELIVERY = ("geo_event_replica_queued", (49272, 49273, 47272), {"oxceGeoscapeEventsInstantDelivery": False})
EV = "GeoscapeEventState"
RES = ["STR_GEOEV_RES_A", "STR_GEOEV_RES_B", "STR_GEOEV_RES_C"]
TRG = {k: "STR_GEOEV_TRG_" + k for k in ("FUNDS", "TRANSFER", "INVERT", "REGION", "RESEARCH", "INSTANT")}
NAMES = RES + sorted(TRG.values())
ITEMS = ["STR_GRENADE", "STR_PISTOL", "STR_PISTOL_CLIP"]
TR_EN = {"STR_GRENADE": "Grenade", "STR_PISTOL": "Pistol"}          # the replica's tr() (xcom1 en-US)
REGION_T, REGION_M = "Test region event: {}", "Points went to {}."   # the mod's en-US.yml (the replica)
REGION_T_DE = "Test-Regionsereignis: {}"                             # the mod's de.yml (the German host)
BIG, SMALL = 1000000, 1000                                          # the events' funds
EVENT_IDS = ("STR_SOLDIER", "STR_SKYRANGER", "STR_INTERCEPTOR")    # eventLogic's getId: genSoldier, the spawned craft
POLL_S, POLL_I, BETWEEN_S = 3.0, 0.1, 30
CLEAN_S = 4.0         # > the 3000 ms mismatch debounce and the measured 3.27 s worst case

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
    if r.cell("guard:" + name, ok, detail):
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
    """Between rows (<= 30 s): replica pending false and both tops GeoscapeState; then the baseline on both."""
    h, c = x.host, x.client
    ok = wait_until(lambda: not rs(c)["pending"] and stack(h)[-1:] == ["GeoscapeState"]
                    and stack(c)[-1:] == ["GeoscapeState"], BETWEEN_S)
    guard(r, x, "start", ok, f"stacks {stack(h)} / {stack(c)}, replica {rs(c)}")
    baseline = {gc.name: {"funds": funds(gc), "probe": probe(gc), "chk": chk(gc), "rs": rs(gc)} for gc in (h, c)}
    r.ev["baseline"] = {n: {"funds": v["funds"], "requests": v["rs"]["requests"], "chk": v["chk"]}
                        for n, v in baseline.items()}
    return baseline

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

def seen(samples, base_funds):
    v = lambda k: sorted(set(s[k] for s in samples), key=str)  # noqa: E731 - None while a restream runs
    return {"replica": v("cF"), "host": v("hF"), "requests": v("cReq"), "n": len(samples), "baseline": base_funds}

def ids_cell(r, baseline, hp, cp):
    """only the counters eventLogic mints that moved on the host (baseline -> hit); the rest EVIDENCE."""
    h0, h1, c1 = baseline["host"]["probe"]["ids"], hp["ids"], cp["ids"]
    keys, v = sorted(k for k in EVENT_IDS if h0.get(k) != h1.get(k)), lambda k: [h0.get(k), h1.get(k), c1.get(k)]
    r.ev["ids [baseline, host, replica]"] = ev = {"compared": {k: v(k) for k in keys}, "excluded":
                                            {k: v(k) for k in sorted(set(h1) | set(c1)) if k not in keys}}
    r.cell("ids", bool(keys) and all(h1.get(k) == c1.get(k) for k in keys), f"{ev}")

def own_render(ev, rule):
    """The replica's own tr() of its picks: region templates + place, else the rule id; rows [tr(id), qty]."""
    pk, place = ev.get("picks") or {}, ev.get("place")
    title, msg = (REGION_T.format(place), REGION_M.format(place)) if pk.get("region") else (rule, rule)
    return {"title": title, "message": msg, "rows": [[TR_EN.get(i, i), str(q)] for i, q in pk.get("rows") or []]}

def trigger(r, x, key, reward, baseline):
    """Research the trigger topic and skip to the event window; host guards: the hit, eventStates 1, the reward."""
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
    guard(r, x, "hostReward", hf == baseline["host"]["funds"] + reward,
          f"host funds {baseline['host']['funds']} -> {hf}")

def world_diff(r, x):
    r.ev["worldDiff"] = (d := shared_fixture.world_diff(x.host, x.client))[:12]
    r.cell("worldDiff", d == [], f"{len(d)} field(s): {d[:6]}")

def clean(r, x, baseline):
    h, c = x.host, x.client
    st, sk = geo.settle(h, c), geo.skip_ingame_time(h, c, 60, speed_idx=3)
    time.sleep(CLEAN_S)
    req, ch, cc = rs(c)["requests"], chk(h), chk(c)
    r.ev["clean"] = {"dismissed": st.get("dismissed"), "gameMin": sk.get("game_minutes"), "requests": req,
                     "chkHost": ch, "chkClient": cc, "stacks": [stack(h), stack(c)]}
    r.cell("clean", req == baseline["client"]["rs"]["requests"] and bool(ch) and ch == cc,
           f"replica requests {baseline['client']['rs']['requests']} -> {req}, chk host {ch} / replica {cc}")

def common(r, x, key, reward, rule, baseline=None):
    """The baseline, the trigger + guards, the 3 s poll; cells fundsSeen (the cell a broken build fails), eventStates,
    sameWindow."""
    baseline = baseline or start(r, x)
    trigger(r, x, key, reward, baseline)
    samples, _win = poll(x)
    hp, cp, topic = probe(x.host), probe(x.client), TRG[key]   # read after the poll: both windows open, clocks stopped
    r.ev["event"] = {"host": hp.get("event"), "replica": cp.get("event"),
                     "eventStates": [hp.get("eventStates"), cp.get("eventStates")]}
    guard(r, x, "triggerResearched", hp["research"][topic]["researched"] and cp["research"][topic]["researched"],
          f"{topic} host {hp['research'][topic]} replica {cp['research'][topic]}")
    r.ev["fundsSeen"] = seen(samples, [baseline["host"]["funds"], baseline["client"]["funds"]])
    r.cell("fundsSeen", all(s["cF"] == s["hF"] for s in samples),
           f"the replica applied the reward on top of the host's: {r.ev['fundsSeen']}")
    r.cell("eventStates", hp.get("eventStates") == 1 and cp.get("eventStates") == 1,
           f"host {hp.get('eventStates')} replica {cp.get('eventStates')}")
    want = own_render(ce, rule) if (ce := cp.get("event") or {}) else None
    r.cell("sameWindow", bool(ce) and picks(hp) == picks(cp) and ce.get("texts") == want,
           f"host picks {picks(hp)} / replica picks {picks(cp)}; replica texts {ce.get('texts')} vs own render {want}")
    return baseline, hp, cp

def row_alert_window_only(r, x):
    h, c, baseline = x.host, x.client, start(r, x)
    r.ev["alert"] = h.cmd({"cmd": "shared_alert", "cls": EV, "msg": "STR_GEOEV_EV_FUNDS"})
    samples, win = poll(x)
    f0, evmax = baseline["host"]["funds"], [max(s["hEv"] for s in samples), max(s["cEv"] for s in samples)]
    r.ev["fundsSeen"] = seen(samples, f0)
    r.ev["window"] = {"replica": win.get("c"), "host": win.get("h"), "eventStatesMax": evmax}
    r.cell("fundsSeen", all(s["cF"] == s["hF"] == f0 for s in samples),
           f"the replica ran the event's logic: {r.ev['fundsSeen']}")
    ce = win.get("c") or {}
    r.cell("replicaWindow", evmax[1] == 1 and picks({"event": ce}).get("region") == "" and
           picks({"event": ce}).get("rows") == [] and (ce.get("texts") or {}).get("title") == "STR_GEOEV_EV_FUNDS",
           f"replica window {ce}, eventStates max {evmax[1]}")
    r.cell("hostNoWindow", evmax[0] == 0, f"host eventStates max {evmax[0]}")
    if stack(c)[-1:] == [EV]:
        r.ev["dismiss"] = c.cmd({"cmd": "dismiss_popup"}).get("handled")
    clean(r, x, baseline)

def row_funds_reward(r, x):
    baseline, _hp, _cp = common(r, x, "FUNDS", BIG, "STR_GEOEV_EV_FUNDS")
    world_diff(r, x)
    clean(r, x, baseline)

def row_transfer_reward(r, x):
    baseline, hp, cp = common(r, x, "TRANSFER", SMALL, "STR_GEOEV_EV_TRANSFER")
    ht, ct = hp["hq"]["transfers"], cp["hq"]["transfers"]
    r.ev["transfers"] = {"host": ht, "replica": ct}
    key = lambda t: json.dumps(t, sort_keys=True)  # noqa: E731 - the order is not asserted
    r.cell("transfers", sorted(ht, key=key) == sorted(ct, key=key), f"host {ht} / replica {ct}")
    ids_cell(r, baseline, hp, cp)
    st, sk = geo.settle(x.host, x.client), geo.skip_ingame_time(x.host, x.client, 25 * 60)
    r.ev["after25h"] = {"dismissed": [st.get("dismissed"), sk.get("dismissed")], "gameMin": sk.get("game_minutes")}
    world_diff(r, x)
    clean(r, x, baseline)

def row_item_removal_reward(r, x):
    p0 = (baseline := start(r, x))["host"]["probe"]
    sky = next(k for k in sorted(p0["craftItems"]) if k.startswith("STR_SKYRANGER#"))
    st0, sk0 = p0["stores"][x.hq]["STR_GRENADE"], p0["craftItems"][sky]["STR_GRENADE"]   # read, never assumed
    st1 = max(0, st0 - 7)
    sk1 = sk0 - min(sk0, 7 - (st0 - st1))   # invert: stores first, then crafts (GeoscapeEventState.cpp :360-389)
    want = [["STR_GRENADE", -((st0 - st1) + (sk0 - sk1))]]
    r.ev["grenadesBaseline"] = {"stores": st0, sky: sk0, "want": [st1, sk1], "rows": want}
    baseline, hp, cp = common(r, x, "INVERT", SMALL, "STR_GEOEV_EV_INVERT", baseline)
    got = [[p["stores"][x.hq]["STR_GRENADE"], p["craftItems"][sky]["STR_GRENADE"]] for p in (hp, cp)]
    r.ev["grenades"] = got
    r.cell("grenades", got == [[st1, sk1], [st1, sk1]], f"[stores, {sky}] host/replica {got} (want {[st1, sk1]})")
    rows = [picks(p).get("rows") for p in (hp, cp)]
    r.cell("rows", rows == [want, want], f"picks.rows host/replica {rows} (want {want})")
    world_diff(r, x)
    clean(r, x, baseline)

def row_region_reward(r, x):
    baseline, hp, cp = common(r, x, "REGION", SMALL, "STR_GEOEV_EV_REGION")
    x.region_probes = (hp, cp)        # own_language_window reads these, taken on the open windows before the clean
    pk = picks(hp)
    r.cell("picksSet", bool(pk.get("region")) and isinstance(pk.get("city"), int) and pk["city"] >= 0,
           f"host picks {pk}")
    r0 = baseline["host"]["probe"]["regions"]
    moved = {k: v - r0.get(k, 0) for k, v in hp["regions"].items() if v != r0.get(k, 0)}
    r.ev["regions"] = {"baseline": r0, "host": hp["regions"], "replica": cp["regions"], "hostMoved": moved,
                       "researchScore": [hp["researchScore"], cp["researchScore"]]}
    r.cell("regions", hp["regions"] == cp["regions"] and moved == {pk.get("region"): 77},
           f"host moved {moved} (want {{{pk.get('region')}: 77}}); equal {hp['regions'] == cp['regions']}")
    r.cell("researchScore", hp["researchScore"] == cp["researchScore"], f"{r.ev['regions']['researchScore']}")
    clean(r, x, baseline)

def row_own_language_window(r, x):
    """Guard row: each machine draws the window in its own language; the picks cell is EVIDENCE only."""
    he, ce = (((x.region_probes[0].get("event") or {}), (x.region_probes[1].get("event") or {}))
              if x.region_probes else ({}, {}))
    ht, ct = he.get("texts") or {}, ce.get("texts") or {}
    r.ev.update({"host": he, "replica": ce, "picksEqual (EVIDENCE only)": he.get("picks") == ce.get("picks")})
    r.cell("replicaPlace", bool(ce.get("place")), f"replica place {ce.get('place')!r}")
    r.cell("replicaTitle", ct.get("title") == REGION_T.format(ce.get("place")), f"{ct.get('title')!r}")
    r.cell("replicaMessage", ct.get("message") == REGION_M.format(ce.get("place")), f"{ct.get('message')!r}")
    r.cell("hostTitle", bool(he.get("place")) and ht.get("title") == REGION_T_DE.format(he.get("place")),
           f"{ht.get('title')!r} place {he.get('place')!r}")
    r.cell("titlesDiffer", ct.get("title") != ht.get("title"), f"{ct.get('title')!r} == {ht.get('title')!r}")

def row_research_reward(r, x):
    baseline, hp, cp = common(r, x, "RESEARCH", SMALL, "STR_GEOEV_EV_RESEARCH")
    hr, cr = ({n: p["research"][n] for n in RES} for p in (hp, cp))
    cr2 = [chk(x.host).get("chkResearch"), chk(x.client).get("chkResearch")]
    names = [n for n in (picks(hp).get("research"), picks(hp).get("bonus")) if n]
    dg = [[e for e in p["diary"]["tail"] if e["name"] in names] for p in (hp, cp)]
    ex = [[e for e in p["diary"]["tail"] if e["name"] not in names] for p in (hp, cp)]
    r.ev["research"] = {"host": hr, "replica": cr, "chkResearch": cr2, "researchScore": [hp["researchScore"],
                        cp["researchScore"]], "diary": {"names": names, "host": dg[0], "replica": dg[1],
                                                        "excluded [host, replica]": ex}}
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
    clean(r, x, baseline)

def row_instant_craft_reward(r, x):
    baseline, hp, cp = common(r, x, "INSTANT", SMALL, "STR_GEOEV_EV_INSTANT")
    c0 = baseline["host"]["probe"]["hq"]["crafts"]
    new = [k for k in hp["hq"]["crafts"] if k not in c0]
    r.ev["crafts"] = {"baseline": c0, "host": hp["hq"]["crafts"], "replica": cp["hq"]["crafts"], "hostNew": new}
    r.cell("crafts", len(new) == 1 and new[0]["type"] == "STR_INTERCEPTOR" and hp["hq"]["crafts"] == cp["hq"]["crafts"],
           f"host new {new}; equal {hp['hq']['crafts'] == cp['hq']['crafts']}")
    ids_cell(r, baseline, hp, cp)
    p0 = baseline["host"]["probe"]["stores"][x.hq]["STR_PISTOL"]
    got = [p["stores"][x.hq]["STR_PISTOL"] for p in (hp, cp)]
    r.ev["pistols"] = {"baseline": p0, "got": got}
    r.cell("pistols", got == [p0 + 2, p0 + 2], f"host/replica {got} (want {p0 + 2})")
    rows = [picks(p).get("rows") for p in (hp, cp)]
    r.cell("rows", rows == [[["STR_PISTOL", 2]]] * 2, f"picks.rows host/replica {rows}")
    world_diff(r, x)
    clean(r, x, baseline)

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
        try:
            x = SimpleNamespace(host=js.host, client=js.client, region_probes=None,
                                hq=js.host.ok({"cmd": "geo_state"})["bases"][0]["name"])
        except BaseException:
            # the except below reports a boot miss and returns without js, so a failed probe after
            # the bring-up shuts down its games before the error propagates (shared_fixture.bring_up's form)
            js.shutdown()
            raise
    except Exception as e:
        print(f"CAPTURE {tag} (boot miss): {short(e, 1500)}", flush=True)
        for rid, _fn in rows:
            results[rid] = False
            print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot", flush=True)
        walls[tag] = round(time.time() - t0, 1)
        return
    print(f"[test_geo_event_replica] {tag} bring-up {time.time() - t0:.1f}s hq {x.hq}", flush=True)
    try:
        for rid, fn in rows:
            run_one(rid, fn, x, results)
    finally:
        try:
            js.shutdown()
        except Exception as e:
            print(f"[test_geo_event_replica] {tag} shutdown: {short(e)}", flush=True)
    walls[tag] = round(time.time() - t0, 1)

ROWS_GERMAN_HOST = (("alert_window_only", row_alert_window_only), ("funds_reward", row_funds_reward),
                    ("item_removal_reward", row_item_removal_reward), ("region_reward", row_region_reward),
                    ("own_language_window", row_own_language_window), ("research_reward", row_research_reward),
                    ("instant_craft_reward", row_instant_craft_reward))
ROWS_QUEUED_DELIVERY = (("transfer_reward", row_transfer_reward),)

def main():
    t0, results, walls = time.time(), {}, {}
    for spec, rows in ((BOOT_GERMAN_HOST, ROWS_GERMAN_HOST), (BOOT_QUEUED_DELIVERY, ROWS_QUEUED_DELIVERY)):
        boot(spec, rows, results, walls)
    order = [rid for rid, _ in ROWS_GERMAN_HOST + ROWS_QUEUED_DELIVERY]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_geo_event_replica: {len(order) - len(failed)}/{len(order)} passed (fail={failed}) walls {walls} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
