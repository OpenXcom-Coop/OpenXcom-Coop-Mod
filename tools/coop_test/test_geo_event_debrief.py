"""test_geo_event_debrief.py (SHARED): the after-battle geoscape event (the host's debriefing OK) reaches
the second player.
Mod Coop_GeoEvent_Test: STR_TERROR_MISSION successEvents {STR_GEOEV_EV_DEBRIEF: 100} (funds 1000, 3 x STR_PISTOL_CLIP).
The boot, then test_battle_end_campaign.stage (SEED_S, the kill, the host's DebriefingState); host_ok_first's order:
the client's display-only debriefing and worldAdopted 1; the baseline snapshot; the host's OK (bec.press_ok + a drain
that STOPS at its GeoscapeEventState) while the client stays on its debriefing; both polled 0.1 s for 5 s; the client's
OK; both polled 0.1 s for 10 s; both dismiss; clean (settle + 60 min + 4 s: replica requests == the baseline's,
checksum equal).
When broken (the event window never reaches the replica): the replica's eventStates stays 0 for 10 s after its OK AND
(its funds != the host's OR its requests > the baseline's) -> FAIL "the after-battle event never reached the second
player". "guard:" cells are guards (they pass with or without the fix). With the fix: pendingWindows 1 and equal funds /
clips before the client's OK; after it the same window within 10 s, pendingWindows 0, fundsSeen == host funds,
world_diff [], clean. One "EVIDENCE debrief_event:" line, then "PASS debrief_event" / "FAIL debrief_event: <cells>".
ONE foreground run; exit 0 only on PASS, else 2; a boot or guard miss prints one CAPTURE line.
Run:  python tools/coop_test/test_geo_event_debrief.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
import test_battle_end_campaign as bec  # noqa: E402

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_GeoEvent_Test")
BOOT = ("geo_event_debrief", (49274, 49275, 47274))
EV, RULE, ITEM, REWARD = "GeoscapeEventState", "STR_GEOEV_EV_DEBRIEF", "STR_PISTOL_CLIP", 1000
ROWS = [["STR_PISTOL_CLIP", 3]]
RENDER = {"title": RULE, "message": RULE, "rows": [["Pistol Clip", "3"]]}   # the replica's own tr() (no entry for RULE)
PRE_S, POST_S, POLL_I, CLEAN_S = 5.0, 10.0, 0.1, 4.0

class GuardMiss(Exception):
    """A guard failed: the row ends after its CAPTURE line."""

def short(e, n=600):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."

def probe(gc):
    return gc.cmd({"cmd": "geo_event_probe", "items": [ITEM], "tail": 8})

def funds(gc):
    return gc.cmd({"cmd": "geo_state"}).get("funds")     # None while a restream replaces the world

def rs(gc):
    r = gc.cmd({"cmd": "shared_resync_stats"})
    return {k: r.get(k) for k in ("requests", "pending", "mismatches")}

def chk(gc):
    return {k: v for k, v in gc.cmd({"cmd": "shared_checksum"}).items() if k.startswith("chk")}

def stack(gc):
    return session.states_stripped(gc)

def cell(r, name, ok, detail=""):
    (r["passed"].append(name) if ok else r["fails"].append(f"{name}: {detail}"))

def guard(r, js, name, ok, detail, cap=True):
    cell(r, "guard:" + name, ok, detail)
    if ok:
        return
    out = {}
    for gc in (js.host, js.client) if cap else ():
        try:
            out[gc.name] = {"geo_event_probe": probe(gc), "geo_state": gc.cmd({"cmd": "geo_state"}), "stack": stack(gc),
                            "shared_resync_stats": gc.cmd({"cmd": "shared_resync_stats"}),
                            "debrief_state": gc.cmd({"cmd": "debrief_state"}), "battleEnd": bec.record(gc)}
        except Exception as e:
            out[gc.name] = f"probe failed: {short(e)}"
    if cap:
        print(f"CAPTURE debrief_event (guard {name}): {json.dumps(out, sort_keys=True, default=str)}", flush=True)
    raise GuardMiss(name)

def host_drain_to_window(host, timeout=bec.DRAIN_S, interval=0.3):
    """bec.drain's loop, stopping when GeoscapeEventState is on top. -> (up, screens, why)."""
    screens, t0 = [], time.time()
    while time.time() - t0 < timeout:
        st = stack(host)
        t = st[-1] if st else ""
        if t in (EV, "GeoscapeState"):
            return t == EV, screens, t
        if not any(n in t for n in bec.WAIT_TOPS):
            r = host.cmd({"cmd": "coop_dialog_back"}) if "CoopState" in t else host.cmd({"cmd": "dismiss_popup"})
            screens.append({"t": round(time.time() - t0, 2), "top": t, "resp": r.get("handled") or r.get("error")})
        time.sleep(interval)
    return False, screens, f"timeout {timeout}s (stack {stack(host)})"

def poll(js, hq, secs):
    """Both every 0.1 s: funds, eventStates, top, STR_PISTOL_CLIP; the replica's requests and pendingWindows."""
    out, win, t0 = [], {}, time.time()
    while time.time() - t0 < secs:
        s = {"t": round(time.time() - t0, 2)}
        for gc, k in ((js.host, "h"), (js.client, "c")):
            p, st = probe(gc), stack(gc)
            s.update({k + "F": funds(gc), k + "Ev": p.get("eventStates"), k + "Top": st[-1] if st else None,
                      k + "Clips": (p.get("stores") or {}).get(hq, {}).get(ITEM), k + "Pw": p.get("pendingWindows", 0)})
            if p.get("eventStates") and k not in win:
                win[k] = p.get("event")
        out.append(dict(s, cReq=rs(js.client)["requests"]))
        time.sleep(POLL_I)
    keys = [json.dumps({a: b for a, b in p.items() if a != "t"}, sort_keys=True) for p in out]
    return out, win, [p for i, p in enumerate(out) if i == 0 or keys[i] != keys[i - 1]]

def row(r, js):
    host, client, ctx = js.host, js.client, {}
    try:
        bec.stage("debrief_event", js, ctx)       # prints its own CAPTURE line on a miss
        cell(r, "guard:stage", True)
    except bec.FixtureMiss as e:
        guard(r, js, "stage", False, short(e), cap=False)
    r["ev"]["stage"] = {k: ctx.get(k) for k in ("squad", "mapFingerprint", "autoEnd", "kill")}
    okd, secs = bec.wait_until(lambda: (lambda d: d.get("shown") is True and d.get("displayOnly") is True)(
        client.cmd({"cmd": "debrief_state"})), bec.CLIENT_DEBRIEF_S, interval=0.1)
    guard(r, js, "clientDebrief", okd, f"no display-only DebriefingState on the client within {secs}s")
    oka, secs = bec.wait_until(lambda: bec.record(client).get("worldAdopted") == 1, bec.ADOPT_S, interval=0.1)
    guard(r, js, "adoptedBeforeHostOk", oka, f"client battleEnd {bec.record(client)} after {secs}s")
    hq = host.ok({"cmd": "geo_state"})["bases"][0]["name"]
    base_raw = {gc.name: {"funds": funds(gc), "probe": probe(gc), "rs": rs(gc), "stack": stack(gc)}
                for gc in (host, client)}
    r["ev"]["baseline"] = baseline = {n: {"funds": v["funds"], "requests": v["rs"]["requests"], "stack": v["stack"],
                                          "clips": v["probe"]["stores"][hq][ITEM],
                                          "eventStates": v["probe"]["eventStates"]}
                                      for n, v in base_raw.items()}
    guard(r, js, "noWindowYet", baseline["host"]["eventStates"] == 0 and baseline["client"]["eventStates"] == 0,
          f"{baseline}")
    t_hok = time.time()
    ok1 = bec.press_ok(host)
    up, screens, why = host_drain_to_window(host) if ok1.get("pressed") else (False, [], ok1.get("note"))
    hp, hf = probe(host), funds(host)
    r["ev"]["hostOk"] = {"press": ok1, "why": why, "screens": screens, "windowAfterS": round(time.time() - t_hok, 2),
                         "stack": stack(host), "event": hp.get("event")}
    guard(r, js, "hostWindow", up, why)
    guard(r, js, "hostEventStates", hp.get("eventStates") == 1, f"host eventStates {hp.get('eventStates')}")
    guard(r, js, "hostReward", hf == baseline["host"]["funds"] + REWARD,
          f"host funds {baseline['host']['funds']} -> {hf}")
    pre, _w, r["ev"]["preClientOk"] = poll(js, hq, PRE_S)
    guard(r, js, "clientOnDebrief", all(s["cTop"] == "DebriefingState" for s in pre)
          and bec.top(client) == "DebriefingState", f"client tops {sorted(set(str(s['cTop']) for s in pre))}")
    last = pre[-1]
    cell(r, "pendingBeforeOk", last["cPw"] == 1, f"replica pendingWindows {last['cPw']} (want 1, the queued path)")
    cell(r, "worldBeforeOk", last["cF"] == last["hF"] and last["cClips"] == last["hClips"],
         f"funds host {last['hF']} / replica {last['cF']}, {ITEM} host {last['hClips']} / replica {last['cClips']}")
    r["ev"]["clientOk"] = {"press": bec.press_ok(client), "afterHostOkS": round(time.time() - t_hok, 2)}
    post, win, chg = poll(js, hq, POST_S)
    end, ev_max = post[-1], max(s["cEv"] for s in post)
    diverged = end["cF"] != end["hF"] or end["cReq"] > baseline["client"]["requests"]
    r["ev"]["postClientOk"] = {"changes": chg, "cEvMax": ev_max, "diverged": diverged,
                               "namedFailure": ev_max == 0 and diverged, "replicaWindow": win.get("c")}
    cell(r, "reached", ev_max >= 1, "the after-battle event never reached the second player: replica "
         f"eventStates 0 for {POST_S}s after its OK; funds host {end['hF']} / replica {end['cF']}, requests "
         f"{baseline['client']['requests']} -> {end['cReq']} (diverged {diverged})")
    ce, he = win.get("c") or {}, win.get("h") or hp.get("event") or {}
    cell(r, "sameWindow", bool(ce) and ce.get("picks") == he.get("picks") and (ce.get("picks") or {}).get("rows")
         == ROWS and ce.get("texts") == RENDER, f"host {he.get('picks')} / replica {ce}")
    cell(r, "pendingAfterOk", end["cPw"] == 0, f"replica pendingWindows {end['cPw']}")
    fs = pre + post
    r["ev"]["fundsSeen"] = {"replica": sorted(set(s["cF"] for s in fs)), "host": sorted(set(s["hF"] for s in fs))}
    cell(r, "fundsSeen", all(s["cF"] == s["hF"] for s in fs), f"{r['ev']['fundsSeen']}")
    d = shared_fixture.world_diff(host, client)
    r["ev"]["worldDiff"] = d[:12]
    cell(r, "worldDiff", d == [], f"{len(d)} field(s): {d[:6]}")
    hd = host.cmd({"cmd": "dismiss_popup"}).get("handled") if stack(host)[-1:] == [EV] else None
    hreach, hscreens = bec.drain(host)
    cd = client.cmd({"cmd": "dismiss_popup"}).get("handled") if stack(client)[-1:] == [EV] else None
    st, sk = geo.settle(host, client), geo.skip_ingame_time(host, client, 60, speed_idx=3)
    time.sleep(CLEAN_S)
    req, ch, cc = rs(client)["requests"], chk(host), chk(client)
    r["ev"]["clean"] = {"dismiss": [hd, hreach, hscreens, cd], "settle": st.get("dismissed"), "chk": [ch, cc],
                        "gameMin": sk.get("game_minutes"), "requests": req, "stacks": [stack(host), stack(client)]}
    cell(r, "clean", req == baseline["client"]["requests"] and bool(ch) and ch == cc,
         f"replica requests {baseline['client']['requests']} -> {req}, chk host {ch} / replica {cc}")

def main():
    t0, r = time.time(), {"ev": {}, "fails": [], "passed": []}
    try:
        js = shared_fixture.bring_up(BOOT[0], BOOT[1], mods=(MOD,))
    except Exception as e:
        print(f"CAPTURE debrief_event (boot miss): {short(e, 1500)}\nEVIDENCE debrief_event: {{}}\n"
              f"FAIL debrief_event: boot", flush=True)
        return 2
    print(f"[test_geo_event_debrief] {BOOT[0]} bring-up {time.time() - t0:.1f}s", flush=True)
    try:
        row(r, js)
    except GuardMiss as e:
        r["ev"]["guardMiss"] = str(e)
    except Exception as e:
        cell(r, "exception", False, short(e, 800))
    finally:
        try:
            js.shutdown()
        except Exception as e:
            print(f"[test_geo_event_debrief] shutdown: {short(e)}", flush=True)
    r["ev"]["cellsPassed"], r["ev"]["wallS"] = r["passed"], round(time.time() - t0, 1)
    print(f"EVIDENCE debrief_event: {json.dumps(r['ev'], sort_keys=True, default=str)}", flush=True)
    print("PASS debrief_event" if not r["fails"]
          else f"FAIL debrief_event: {len(r['fails'])} cell(s): " + " | ".join(r["fails"]), flush=True)
    print(f"\ntest_geo_event_debrief: {0 if r['fails'] else 1}/1 passed in {time.time() - t0:.1f}s", flush=True)
    return 0 if not r["fails"] else 2

if __name__ == "__main__":
    sys.exit(main())
