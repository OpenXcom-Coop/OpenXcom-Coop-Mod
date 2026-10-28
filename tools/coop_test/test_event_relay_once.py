"""W2-H75 (R-B109-1; F20998, F21090-F21094; QH75-1 .. QH75-6 (a)): in SEPARATE co-op with shared research (Research Sync
on), an event window that both worlds hold - a paired certain event (coopShared) or an event spawned by research both
players learn (main #197's receiver) - plays its video once for each player, at that player's own OK, with no relay.
An ending still relays (the first OK ends both campaigns, R-H17b-1); a private SEPARATE event keeps its relay (W2-H17d
Q1 (a)). Spec docs rewrite/prompts/w2h75_event_relay_once.md (f); TASK 0 rewrite/w2h75-task0/sa/CONSTANTS.md.
Mod Coop_Event_Relay_Test (spec (e) M2): four empty cutscenes (a "play" = one `cutscene definition empty: <id>` engine-log
line after the row's S0 mark, read 1.0 s after the row's last OK, R-H17d-T0-1); STR_H75_EV_C certain in month 0 (paired
on both machines); STR_H75_T_A -> STR_H75_EV_A; STR_H75_T_M (a terror site's despawn topic) -> STR_H75_EV_M;
STR_H75_T_WIN -> STR_H75_EV_WIN, whose cutscene wins the game. Both boots SEPARATE, EnableResearchSync on both machines,
boot guard event_state.researchMode {shared false, sync true} on both. OK = dismiss_popup with the keep list
(CutsceneState, StatisticsState) after reading the top. F = the machine whose window shows first, O = the other.
Boot S (key "49433"): ER-2, ER-1, ER-3. Boot E (key "49434"): ER-4. 13 cells:
  ER-2 a paired certain event: secondNoRelay (RED), secondMid (RED), secondOnce (RED), firstOnce (GUARD cell)
  ER-1 a research-spawned event: otherMid (RED), otherOnce (RED), firstOnce (RED)
  ER-3 a mission-outcome topic (private, keeps its relay): hostNoWindow, clientOnce, hostRelay (GUARD cells)
  ER-4 an ending both worlds hold: firstEnds, otherEnds, plays (GUARD cells)
"G:" = a guard: CAPTURE line and the row ends (later cells "not reached"). EVIDENCE per row, PASS / FAIL per cell, the row
verdict; every row runs after a failure; ONE run (WV-D99 / WV-D100): exit 0 only when every cell passes, else 2.
WV-D95: no wait-hook; run to completion in the foreground.
"""

import json
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import geo  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_Event_Relay_Test")
KEY_S, KEY_E = "49433", "49434"
T_A, EV_A, CUT_A = "STR_H75_T_A", "STR_H75_EV_A", "STR_H75_A"
EV_C, CUT_C = "STR_H75_EV_C", "STR_H75_C"
T_M, EV_M, CUT_M = "STR_H75_T_M", "STR_H75_EV_M", "STR_H75_M"
T_W, EV_W, CUT_W = "STR_H75_T_WIN", "STR_H75_EV_WIN", "STR_H75_WIN"
EV, KEEP = "GeoscapeEventState", ("CutsceneState", "StatisticsState")
PLAY = "cutscene definition empty: "
FLUSH_S, POLL_I, LISTED_S, WINDOWS_S, PAIRED_S = 1.0, 0.2, 5.0, 5.0, 10.0   # TASK 0: every state within 0.1 s
# F23963: ER-1 holds the host's EV_A copy HOLD_M game minutes until F's window is shown and OK'd (TASK 0's roles F = client,
# O = host), then sets O's copy to RELEASE_M, TASK 0's measured O countdown, before skip2. Replacement rules: HOLD_M a multiple
# of 30 far above what the host's clock runs before F's OK (a speed-5 tick runs a whole game day; up to 3210 minutes measured in
# 4 runs, F23963); RELEASE_M a multiple of 30 inside skip2's one-day window.
RC, HOLD_M, RELEASE_M = "ResearchCompleteState", 43200, 30
SKIP_2D = 60 * 24 * 2


class GuardMiss(Exception):
    """A guard failed: the row ends after its CAPTURE line."""


def short(e, n=500):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."


def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while not (last := pred()) and time.time() - t0 < timeout:
        time.sleep(interval)
    return bool(last), round(time.time() - t0, 2)


def stack(gc): return session.states_stripped(gc)  # noqa: E704
def top(gc): return (stack(gc) or [""])[-1]  # noqa: E704
def gep(gc): return gc.cmd({"cmd": "geo_event_probe", "names": [], "items": []})  # noqa: E704
def evs(gc): return gep(gc).get("eventStates")  # noqa: E704
def title(gc): return ((gep(gc).get("event") or {}).get("texts") or {}).get("title")  # noqa: E704
def allow(gc): return gc.cmd({"cmd": "research_probe", "names": [], "tail": 0}).get("allowCutscene")  # noqa: E704
def ending(gc): return gc.cmd({"cmd": "ending_state"}).get("ending")  # noqa: E704
def geo_s(gc): return gc.cmd({"cmd": "geo_state"})  # noqa: E704
def rmode(gc): return gc.cmd({"cmd": "event_state"}).get("researchMode") or {}  # noqa: E704
def learned(gc, t): return gc.cmd({"cmd": "is_researched", "topic": t}).get("researched")  # noqa: E704


def geo_events(gc):
    """This world's pending geoscape events: {name: (countdown, over)}."""
    return {e.get("name"): (e.get("countdown"), e.get("over")) for e in gc.cmd({"cmd": "geo_events"}).get("events", [])}


def pending(gc, name):
    ge = geo_events(gc)
    return name in ge and not ge[name][1]


def base0(gc):
    """test_coop_mission_research.base0 (copied): this machine's own base, or None."""
    for b in gc.ok({"cmd": "geo_state"})["bases"]:
        if not b.get("coopBase") and not b.get("coopIcon"):
            return b
    return None


def listed(gc, topic):
    g = geo_s(gc)
    return bool(g.get("ok")) and any(p.get("name") == topic for b in g.get("bases", []) for p in b.get("research", []))


def snap(gc):
    return {"allow": allow(gc), "ending": ending(gc), "eventStates": evs(gc), "title": title(gc), "stack": stack(gc),
            "time": geo_s(gc).get("time")}


def log_cur(gc):
    try:
        return os.path.getsize(os.path.join(gc.user_dir, "openxcom.log"))
    except OSError:
        return 0


def log_lines(gc, cur=0):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace", newline="") as f:
            f.seek(cur)
            return f.read().splitlines()
    except OSError as e:
        return [f"<log read error {e}>"]


def plays(gc, cur):
    """Since `cur` (the row's S0 mark): this machine's cutscene plays per id."""
    out = {}
    for ln in log_lines(gc, cur):
        if PLAY in ln:
            cid = ln.split(PLAY, 1)[1].strip()
            out[cid] = out.get(cid, 0) + 1
    return out


def capture(gc):
    try:
        return {"research_probe": gc.cmd({"cmd": "research_probe", "names": [T_A, T_M, T_W], "tail": 4}),
                "geo_event_probe": gep(gc), "geo_events": geo_events(gc), "researchMode": rmode(gc),
                "get_state": stack(gc), "logTail": log_lines(gc)[-30:]}
    except Exception as e:
        return f"probe failed: {short(e)}"


def cap_line(r, x, why):
    cap = {gc.name: capture(gc) for gc in (x.host, x.client)}
    print(f"CAPTURE {r.rid} ({why}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def guard(r, x, name, ok, detail):
    """A miss: CAPTURE both machines' probes and engine log tails, then the row ends."""
    if r.cell("G:" + name, ok, detail):
        return
    cap_line(r, x, "guard " + name)
    raise GuardMiss(f"guard {name}")


def gcell(r, x, name, ok, detail):
    """A GUARD cell: it passes before and after the fix; a miss gets a CAPTURE line and the row goes on."""
    if not r.cell(name, ok, detail):
        cap_line(r, x, "guard cell " + name)


class Row:
    def __init__(self, rid, cells):
        self.rid, self.t0, self.ev, self.cells, self.want = rid, time.time(), {}, {}, cells

    def cell(self, name, ok, detail=""):
        self.cells[name] = (bool(ok), "" if ok else detail)
        return ok


def gstep(r, x, step):
    r.ev.setdefault("geoEvents", {})[step] = {gc.name: geo_events(gc) for gc in (x.host, x.client)}


def skip(r, x, minutes, label, speed=5, real_timeout=150):
    """Advance both clocks until a GeoscapeEventState is on top somewhere; returns that machine's name or None."""
    t = time.time()
    sk = geo.skip_ingame_time(x.host, x.client, minutes, speed_idx=speed, interest=geo.popup(EV, *KEEP),
                              real_timeout=real_timeout)
    hit = sk.get("hit")
    r.ev[label] = {"hit": hit, "skipS": round(time.time() - t, 2), "timedOut": sk.get("timed_out"),
                   "dismissed": sk.get("dismissed")}
    return hit[0] if hit and EV in str(hit[1]) else None


def press_ok(r, x, gc, want, label):
    """The real OK on `gc`: its top read first, the atomic keep list passed anyway (guard: handled == want)."""
    t = top(gc)
    ok_top = want in t and not any(k in t for k in KEEP)
    resp = gc.cmd({"cmd": "dismiss_popup", "keep": list(KEEP)}) if ok_top else {}
    o = r.ev[label] = {"top": t, "handled": resp.get("handled"), "at": round(time.time() - r.t0, 2), "after": top(gc)}
    guard(r, x, label, resp.get("handled") == want, f"top {t}, resp {resp}")
    return o


def poll(gc, secs):
    out, t0 = [], time.time()
    while time.time() - t0 < secs:
        ts = time.time()
        out.append({"t": round(ts - t0, 2), "allow": allow(gc), "top": top(gc)})
        time.sleep(max(0.0, POLL_I - (time.time() - ts)))
    return out


def seen(samples, f):
    """Distinct values of field f over the poll, as [value, first t]."""
    out = []
    for s in samples:
        if not out or out[-1][0] != s[f]:
            out.append([s[f], s["t"]])
    return out


def mark(r, x):
    r.ev["S0"] = {gc.name: snap(gc) for gc in (x.host, x.client)}
    gstep(r, x, "S0")
    return {gc.name: log_cur(gc) for gc in (x.host, x.client)}


def counts(r, x, cur):
    time.sleep(FLUSH_S)
    pl = r.ev["plays"] = {gc.name: plays(gc, cur[gc.name]) for gc in (x.host, x.client)}
    r.ev["end"] = {gc.name: snap(gc) for gc in (x.host, x.client)}
    gstep(r, x, "end")
    return pl


def start_topic(r, x, topic):
    """Host research_start (10 scientists), listed on the host within 5 s, set_research_cost 1."""
    h = x.host
    st = h.cmd({"cmd": "research_start", "topic": topic, "scientists": 10}).get("ok")
    ok, w = wait_until(lambda: listed(h, topic), LISTED_S)
    r.ev["trigger"] = {"topic": topic, "start": st, "listedS": w}
    guard(r, x, "listed", st is True and ok, f"start {st}; listed {ok} after {w} s")
    r.ev["trigger"]["cost"] = h.cmd({"cmd": "set_research_cost", "topic": topic, "cost": 1}).get("ok")


def roles(x, name):
    return (x.host, x.client) if name == "host" else (x.client, x.host)


def row_er2(r, x):
    """A paired certain event (B5): the host's OK first; the client must not get the host's video over its window."""
    h, c = x.host, x.client

    def paired():
        a, b = geo_events(h), geo_events(c)
        return EV_C in a and EV_C in b and not a[EV_C][1] and not b[EV_C][1] and a[EV_C][0] == b[EV_C][0]
    ok, w = wait_until(paired, PAIRED_S)
    gstep(r, x, "paired")
    guard(r, x, "paired", ok, f"{EV_C} not paired with equal countdowns after {w} s: {r.ev['geoEvents']['paired']}")
    r.ev["drain"] = {gc.name: geo.drain_popups(gc)[0] for gc in (h, c)}
    geo.slow_clock(h, c)
    resp = h.cmd({"cmd": "set_event_countdown", "name": EV_C, "minutes": 60})
    guard(r, x, "countdown", resp.get("ok") is True, f"set_event_countdown {resp}")
    guard(r, x, "hit", skip(r, x, 180, "skip") is not None, f"skip {r.ev['skip']}")
    ok, w = wait_until(lambda: evs(h) == 1 and evs(c) == 1, WINDOWS_S)
    tt = r.ev["titles"] = {gc.name: title(gc) for gc in (h, c)}
    guard(r, x, "bothWindows", ok and tt == {"host": EV_C, "client": EV_C},
          f"eventStates host {evs(h)} / client {evs(c)} after {w} s; titles {tt}")
    cur = mark(r, x)
    press_ok(r, x, h, EV, "hostOK")
    p = poll(c, 2.0)
    r.ev["clientPoll"] = {"allow": seen(p, "allow"), "top": seen(p, "top"), "n": len(p)}
    mid = r.ev["clientMid"] = plays(c, cur["client"])
    al = r.ev["clientPoll"]["allow"]
    r.cell("secondNoRelay", all(s["allow"] is True for s in p), "the host's OK relayed the paired event's video over "
                                                               f"the client's open window: allowCutscene {al}")
    r.cell("secondMid", mid.get(CUT_C, 0) == 0, f"the client played {CUT_C} {mid.get(CUT_C, 0)} time(s) before its own OK "
                                                "(the host's relay, F21094)")
    press_ok(r, x, c, EV, "clientOK")
    pl = counts(r, x, cur)
    r.cell("secondOnce", pl["client"].get(CUT_C, 0) == 1, f"client {CUT_C} plays {pl['client'].get(CUT_C, 0)} (the host's "
                                                          "relay, then its own OK)")
    gcell(r, x, "firstOnce", pl["host"].get(CUT_C, 0) == 1, f"host {CUT_C} plays {pl['host'].get(CUT_C, 0)}")


def hold(r, x):
    """F23963 (ER-1's premise, TASK 0's F = client, O = host): skip until T_A's ResearchCompleteState shows, wait until both worlds
    hold EV_A pending, stop both clocks (geo_set_speed 0 works under a popup, R-H18-1), hold the host's copy HOLD_M minutes, close
    the research popups (never a GeoscapeEventState). Both copies count down from the same half hour, so without the hold both
    windows open inside one skip pass once test-server calls take 2-3 ms (the 50 ms calls staggered the two clocks)."""
    h, c = x.host, x.client
    t = time.time()
    sk = geo.skip_ingame_time(h, c, SKIP_2D, speed_idx=5, interest=geo.popup(RC, EV, *KEEP), real_timeout=150)
    hit = sk.get("hit")
    ok, w = wait_until(lambda: pending(h, EV_A) and pending(c, EV_A), WINDOWS_S)
    ev = r.ev["hold"] = {"hit": hit, "skipS": round(time.time() - t, 2), "pendingS": w,
                         "geoEvents": {gc.name: geo_events(gc) for gc in (h, c)}}
    guard(r, x, "held", ok and hit is not None and RC in str(hit[1]), f"hold {ev}")
    ev["stop"] = {gc.name: gc.cmd({"cmd": "geo_set_speed", "idx": 0}).get("ok") for gc in (h, c)}
    ev["set"] = h.cmd({"cmd": "set_event_countdown", "name": EV_A, "minutes": HOLD_M})
    guard(r, x, "holdSet", ev["set"].get("ok") is True and all(v is True for v in ev["stop"].values()), f"hold {ev}")
    ev["drain"] = {gc.name: geo.drain_popups(gc, interest=geo.popup(EV, *KEEP))[0] for gc in (h, c)}


def row_er1(r, x):
    """A research-spawned event (B1 + B3): F's window first, O's copy pending; O must not get F's video."""
    start_topic(r, x, T_A)
    hold(r, x)
    name = skip(r, x, SKIP_2D, "skip")
    guard(r, x, "hit", name is not None, f"skip {r.ev['skip']}")
    F, O = roles(x, name)
    r.ev["roles"] = {"F": F.name, "O": O.name}
    tf = r.ev["firstTitle"] = title(F)
    guard(r, x, "firstWindow", tf == EV_A, f"{F.name} title {tf}")
    ok, w = wait_until(lambda: evs(O) == 0 and pending(O, EV_A), WINDOWS_S)
    r.ev["otherPending"] = {"s": w, "eventStates": evs(O), "geoEvents": geo_events(O), "stack": stack(O)}
    guard(r, x, "otherPending", ok, f"{O.name} {r.ev['otherPending']}")
    cur = mark(r, x)
    press_ok(r, x, F, EV, "firstOK")
    p = poll(O, 2.0)
    r.ev["otherPoll"] = {"allow": seen(p, "allow"), "top": seen(p, "top"), "n": len(p)}
    omid = r.ev["otherMid"] = plays(O, cur[O.name])
    r.cell("otherMid", omid.get(CUT_A, 0) == 0, f"{O.name} played {CUT_A} {omid.get(CUT_A, 0)} time(s) before its own "
                                                f"window ({F.name}'s relay, F20998)")
    rel = r.ev["release"] = O.cmd({"cmd": "set_event_countdown", "name": EV_A, "minutes": RELEASE_M})  # F23963: the hold ends
    guard(r, x, "release", rel.get("ok") is True, f"{O.name} set_event_countdown {rel}")
    name2 = skip(r, x, 60 * 24, "skip2", real_timeout=90)
    to = r.ev["otherTitle"] = title(O)
    guard(r, x, "otherWindow", name2 == O.name and to == EV_A, f"hit {r.ev['skip2']['hit']}, {O.name} title {to}")
    press_ok(r, x, O, EV, "otherOK")
    pl = counts(r, x, cur)
    r.cell("otherOnce", pl[O.name].get(CUT_A, 0) == 1, f"{O.name} {CUT_A} plays {pl[O.name].get(CUT_A, 0)} (the relay, "
                                                       "then its own OK)")
    r.cell("firstOnce", pl[F.name].get(CUT_A, 0) == 1, f"{F.name} {CUT_A} plays {pl[F.name].get(CUT_A, 0)} ({O.name}'s OK "
                                                       "relayed back, F21093)")


def row_er3(r, x):
    """A mission-outcome topic (B4): only the client's world spawns EV_M; its private window keeps the relay."""
    h, c = x.host, x.client
    b = base0(h)
    resp = h.cmd({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION",
                  "lon": b["lon"] + 0.35, "lat": b["lat"] + 0.10, "race": "STR_SECTOID", "hours": 1}) if b else {}
    r.ev["site"] = {"base": b and [b.get("name"), b.get("lon"), b.get("lat")], "resp": resp}
    guard(r, x, "site", resp.get("ok") is True, f"spawn_mission_site {resp}")
    name = skip(r, x, 360, "skip", speed=4, real_timeout=120)
    tc = r.ev["clientTitle"] = title(c)
    guard(r, x, "clientWindow", name == "client" and tc == EV_M, f"hit {r.ev['skip']['hit']}, client title {tc}")
    lt = r.ev["learned"] = {gc.name: learned(gc, T_M) for gc in (h, c)}
    guard(r, x, "learned", lt == {"host": True, "client": True}, f"is_researched {T_M} {lt}")
    cur = mark(r, x)
    press_ok(r, x, c, EV, "clientOK")
    pl = counts(r, x, cur)
    hs = [(r.ev[k]["host"]["eventStates"], EV_M in r.ev["geoEvents"][k]["host"]) for k in ("S0", "end")]
    gcell(r, x, "hostNoWindow", hs == [(0, False), (0, False)], f"host (eventStates, holds {EV_M}) at S0 / end {hs} (F21101)")
    gcell(r, x, "clientOnce", pl["client"].get(CUT_M, 0) == 1, f"client {CUT_M} plays {pl['client'].get(CUT_M, 0)}")
    gcell(r, x, "hostRelay", pl["host"].get(CUT_M, 0) == 1, f"host {CUT_M} plays {pl['host'].get(CUT_M, 0)}: a private "
                                                            "SEPARATE event keeps its relay (W2-H17d Q1 (a))")


def row_er4(r, x):
    """An ending both worlds hold (B1 + B3): F's OK ends both campaigns; each plays the ending once."""
    start_topic(r, x, T_W)
    name = skip(r, x, SKIP_2D, "skip")
    guard(r, x, "hit", name is not None, f"skip {r.ev['skip']}")
    F, O = roles(x, name)
    r.ev["roles"] = {"F": F.name, "O": O.name}
    tf = r.ev["firstTitle"] = title(F)
    guard(r, x, "firstWindow", tf == EV_W, f"{F.name} title {tf}")
    cur = mark(r, x)
    press_ok(r, x, F, EV, "firstOK")
    out, t0 = [], time.time()
    while time.time() - t0 < 5.0:
        ts = time.time()
        s = {"t": round(ts - t0, 2)}
        for gc in (F, O):
            e = gc.cmd({"cmd": "ending_state"})
            s[gc.name] = [e.get("ending"), bool(e.get("statistics"))]
        out.append(s)
        time.sleep(max(0.0, POLL_I - (time.time() - ts)))
    first = r.ev["endsAt"] = {gc.name: next((s["t"] for s in out if s[gc.name] == [1, True]), None) for gc in (F, O)}
    r.ev["endPoll"] = {gc.name: seen([{"t": s["t"], "v": s[gc.name]} for s in out], "v") for gc in (F, O)}
    pl = counts(r, x, cur)
    gcell(r, x, "firstEnds", first[F.name] is not None, f"{F.name} never showed ending 1 + StatisticsState: {r.ev['endPoll']}")
    gcell(r, x, "otherEnds", first[O.name] is not None, f"{O.name} never showed ending 1 + StatisticsState within 5 s "
                                                        f"(R-H17b-1): {r.ev['endPoll']}")
    gcell(r, x, "plays", pl[F.name].get(CUT_W, 0) == 1 and pl[O.name].get(CUT_W, 0) == 1,
          f"{CUT_W} plays {F.name} {pl[F.name].get(CUT_W, 0)} / {O.name} {pl[O.name].get(CUT_W, 0)}")


def report(r, results):
    print(f"EVIDENCE {r.rid}: {json.dumps(r.ev, sort_keys=True, default=str)}", flush=True)
    for name in r.want:
        ok, d = r.cells.get(name, (False, "not reached"))
        print(f"PASS {r.rid} {name}" if ok else f"FAIL {r.rid} {name}: {d}", flush=True)
    extra = [n for n, (ok, _d) in r.cells.items() if n not in r.want and not ok]
    for n in extra:
        print(f"FAIL {r.rid} {n}: {r.cells[n][1]}", flush=True)
    bad = [n for n in r.want if not r.cells.get(n, (False,))[0]] + extra
    print(f"PASS {r.rid}" if not bad else f"FAIL {r.rid}: {len(bad)} failed ({', '.join(bad)})", flush=True)
    results[r.rid] = bad


def run_one(rid, fn, cells, x, results):
    r = Row(rid, cells)
    try:
        fn(r, x)
    except GuardMiss:
        try:
            geo.settle(x.host, x.client, keep=list(KEEP))
        except Exception as e:
            r.ev["settleAfterMiss"] = short(e)
    except Exception as e:
        r.cell("exception", False, short(e, 800))
        try:
            cap_line(r, x, "exception")
        except Exception:
            pass
    r.ev["wallS"] = round(time.time() - r.t0, 1)
    report(r, results)


def boot_sep(tag, key):
    opts = {"EnableResearchSync": True}
    host = GameClient("host", None, make_user_dir(f"{tag}_host", mods=(MOD,), options=opts))
    client = GameClient("client", None, make_user_dir(f"{tag}_client", mods=(MOD,), options=opts))
    try:
        [f() for f in (host.spawn, client.spawn, host.connect, client.connect)]
        session.new_campaign(host, client, port=key, campaign_mode="coop")
        geo.wait_both_ready(host, client)
    except BaseException:
        shutdown_clients(host, client)
        raise
    return SimpleNamespace(host=host, client=client, shutdown=lambda: shutdown_clients(host, client))


def boot(tag, key, rows, results, walls):
    t0, js, x = time.time(), None, None
    try:
        js = boot_sep(tag, key)
        x = SimpleNamespace(host=js.host, client=js.client)
        walls[tag + " bring-up"] = round(time.time() - t0, 1)
        info = {gc.name: dict(snap(gc), researchMode=rmode(gc), geoEvents=geo_events(gc),
                              mod=[ln.split("\t")[-1] for ln in log_lines(gc) if "Coop_Event_Relay_Test" in ln][:2])
                for gc in (x.host, x.client)}
        info["startedAt"] = time.strftime("%H:%M:%S", time.localtime(t0))
        print(f"EVIDENCE boot {tag}: {json.dumps(info, sort_keys=True, default=str)}", flush=True)
        rm = {n: (info[n]["researchMode"].get("shared"), info[n]["researchMode"].get("sync")) for n in ("host", "client")}
        if rm != {"host": (False, True), "client": (False, True)}:
            raise RuntimeError(f"boot guard researchMode (shared, sync) {rm}: "
                               + json.dumps({gc.name: capture(gc) for gc in (x.host, x.client)}, default=str))
    except Exception as e:
        x = None
        print(f"CAPTURE {tag} (boot miss): {short(e, 6000)}", flush=True)
        for rid, _fn, cells in rows:
            results[rid] = ["boot"]
            print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}", flush=True)
            print("\n".join(f"FAIL {rid} {n}: boot" for n in cells) + f"\nFAIL {rid}: boot", flush=True)
    try:
        for rid, fn, cells in (rows if x is not None else ()):
            run_one(rid, fn, cells, x, results)
    finally:
        try:
            if js is not None:
                js.shutdown()
        except Exception as e:
            print(f"[w2h75] {tag} shutdown: {short(e)}", flush=True)
        walls[tag] = round(time.time() - t0, 1)


BOOTS = (("w2h75s", KEY_S, (("ER-2", row_er2, ("secondNoRelay", "secondMid", "secondOnce", "firstOnce")),
                            ("ER-1", row_er1, ("otherMid", "otherOnce", "firstOnce")),
                            ("ER-3", row_er3, ("hostNoWindow", "clientOnce", "hostRelay")))),
         ("w2h75e", KEY_E, (("ER-4", row_er4, ("firstEnds", "otherEnds", "plays")),)))


def main():
    t0, results, walls = time.time(), {}, {}
    for tag, key, rows in BOOTS:
        boot(tag, key, rows, results, walls)
    all_rows = [rid for _t, _k, rows in BOOTS for rid, _fn, _c in rows]
    n_cells = sum(len(c) for _t, _k, rows in BOOTS for _r, _fn, c in rows)
    failed = {rid: results.get(rid, ["not run"]) for rid in all_rows if results.get(rid, ["not run"])}
    print(f"\ntest_event_relay_once: {len(all_rows) - len(failed)}/{len(all_rows)} rows passed, failed cells {failed} "
          f"(of {n_cells}) walls {walls} in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
