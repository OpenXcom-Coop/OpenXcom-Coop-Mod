"""W2-H17b (F7207, F7209; D226 a, D239 a; Q1 a .. Q5 a; R-H17b-1, R-H17b-T0-1/-2): a game-ending cutscene ends the
campaign on both machines, and a cutscene never rewrites the month count. Spec docs rewrite/prompts/
w2h17b_research_endings.md (e)-(f); TASK 0 rewrite/w2h17b-task0/CONSTANTS.md. Mod Coop_Cutscene_Test: three empty
cutscenes (a "play" logs `cutscene definition empty: <id>`), two events, five topics. Probes (read-only): ending_state,
research_probe (ending, monthsPassed, daysPassed, allowCutscene), geo_event_probe (eventStates), get_state.
Row frame: trigger = research_start (10 scientists) on the starting machine (the host in A-C, the client in D), the
project listed (both in SHARED) within 5 s, set_research_cost 1, a 2-day skip (speed 5, real timeout 150 s) to the row's
interest; poll = both machines' ending_state + research_probe every 0.2 s for 5 s (3 s in H17b-1). Every interest and
keep list names CutsceneState and StatisticsState (H17b-3 also SlideshowState, R-H17b-T0-1); no dismiss_popup ever
reaches a machine whose top is one of them (atomic keep list, top read first). The packet-arrived guard is the receiving
machine's allowCutscene false in H17b-1 / H17b-4 (a window sits under its cutscene) and, in H17b-2 / -3 / -5, its engine
log's play of the packet's cutscene after the row's S0 mark (R-H17b-R-1; there GeoscapeState::init re-arms the latch);
H17b-3 also accepts a SlideshowState push after that machine's StatisticsState push (the stock loseGame, R-H17b-G-2).
Boot A (SHARED): H17b-1 (first), H17b-2; Boot B: H17b-3; Boot C: H17b-4; Boot D (SEPARATE): H17b-5.
RED (commit 1): H17b-1..5 fail on their named cells; GREEN: all pass. "G:" cells are guards (CAPTURE on a miss).
EVIDENCE then PASS / FAIL per row; ONE run; every row runs after a failure; exit 0 only if all pass, else 2.
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

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_Cutscene_Test")
BOOT_A = ("w2h17ba", (49360, 49361, 47350))      # SHARED; lobby 47350 (F7219)
BOOT_B = ("w2h17bb", (49362, 49363, 47352))      # SHARED
BOOT_C = ("w2h17bc", (49364, 49365, 47354))      # SHARED
BOOT_D = ("w2h17bd", (49366, 49367, 47356))      # SEPARATE
T_WIN, T_FREE, T_LOSE = "STR_H17B_T_WIN", "STR_H17B_T_FREE", "STR_H17B_T_LOSE"
T_EVSTORY, T_EVWIN = "STR_H17B_T_EVSTORY", "STR_H17B_T_EVWIN"
TOPICS = [T_WIN, T_FREE, T_LOSE, T_EVSTORY, T_EVWIN]
EV, KEEP = "GeoscapeEventState", ("CutsceneState", "StatisticsState")
KEEP_B = KEEP + ("SlideshowState",)             # R-H17b-T0-1: the host's time5Seconds lose check plays stock loseGame
UI_TYPES = KEEP + ("SlideshowState", EV, "ResearchCompleteState", "NewPossibleResearchState", "GeoscapeState")
SKIP_MIN, POLL_I, LISTED_S, WINDOWS_S = 60 * 24 * 2, 0.2, 5.0, 5.0

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

def keys(d, *ks): return {k: d.get(k) for k in ks}  # noqa: E704
def stack(gc): return session.states_stripped(gc)  # noqa: E704
def top(gc): return (stack(gc) or [""])[-1]  # noqa: E704
def es(gc): return keys(gc.cmd({"cmd": "ending_state"}), "ending", "statistics", "campaignEnded", "mainMenu")  # noqa: E704
def evs(gc): return gc.cmd({"cmd": "geo_event_probe", "names": [], "items": []}).get("eventStates")  # noqa: E704

def rp(gc, tail=2):
    r = gc.cmd({"cmd": "research_probe", "names": TOPICS, "tail": tail})
    return dict(keys(r, "ok", "error", "researched", "ending", "monthsPassed", "daysPassed", "allowCutscene"),
                diary=(r.get("diary") or {}).get("tail"))

def listed(gc, topic):
    g = gc.cmd({"cmd": "geo_state"})
    return bool(g.get("ok")) and any(p.get("name") == topic for b in g.get("bases", []) for p in b.get("research", []))

def snap(gc):
    return {"ending_state": es(gc), "research_probe": rp(gc), "stack": stack(gc)}

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

def log_ev(gc, cur):
    """Since `cur`: the cutscene plays per id and the [coop-ui] push / pop of the row's window types (time-stamped)."""
    plays, ui = {}, []
    for ln in log_lines(gc, cur):
        if "cutscene definition empty: " in ln:
            cid = ln.split("cutscene definition empty: ", 1)[1].strip()
            plays[cid] = plays.get(cid, 0) + 1
        i = ln.find("[coop-ui] ")
        if i >= 0:
            op, _, body = ln[i + 10:].partition(" ")
            typ = body.strip().split(" depth=")[0].split("::")[-1]
            if typ in UI_TYPES:
                ui.append(f"{ln[1:24][-12:]} {op} {typ}")
    return {"plays": plays, "ui": ui[-24:]}

def stock_play(gc, cur):
    """R-H17b-G-2: since `cur`, a [coop-ui] push of SlideshowState after this machine's StatisticsState push."""
    stat = False
    for ln in log_lines(gc, cur):
        i = ln.find("[coop-ui] push ")
        typ = ln[i + 15:].strip().split(" depth=")[0].split("::")[-1] if i >= 0 else ""
        stat = stat or typ == "StatisticsState"
        if stat and typ == "SlideshowState":
            return True
    return False

def guard(r, x, name, ok, detail):
    """A miss: CAPTURE both machines' ending_state, research_probe, get_state, eventStates and engine log tail."""
    if r.cell("G:" + name, ok, detail):
        return
    cap = {}
    for gc in (x.host, x.client):
        try:
            cap[gc.name] = dict(snap(gc), eventStates=evs(gc), logTail=log_lines(gc)[-30:])
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {r.rid} (guard {name}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise GuardMiss(f"guard {name}")

class Row:
    def __init__(self, rid):
        self.rid, self.t0, self.ev, self.fails, self.passed = rid, time.time(), {}, [], []
    def cell(self, name, ok, detail=""):
        (self.passed.append(name) if ok else self.fails.append(f"{name}: {detail}"))
        return ok

def trigger(r, x, on, topic, shared, interest):
    """research_start on `on`, listed (both in SHARED) within 5 s, set_research_cost 1, then the 2-day skip to `interest`."""
    other = x.client if on is x.host else x.host
    st = on.cmd({"cmd": "research_start", "topic": topic, "scientists": 10})
    ok, w = wait_until(lambda: listed(on, topic) and (not shared or listed(other, topic)), LISTED_S)
    guard(r, x, "listed", st.get("ok") is True and ok, f"start {st}; listed {ok} after {w} s")
    cost = on.cmd({"cmd": "set_research_cost", "topic": topic, "cost": 1})
    t = time.time()
    sk = geo.skip_ingame_time(x.host, x.client, SKIP_MIN, speed_idx=5, interest=interest, real_timeout=150)
    r.ev["trigger"] = {"on": on.name, "topic": topic, "listedS": w, "cost": cost.get("ok"), "hit": sk.get("hit"),
                       "skipS": round(time.time() - t, 2), "gameMin": sk.get("game_minutes"),
                       "dismissed": sk.get("dismissed")}
    guard(r, x, "hit", sk.get("hit") is not None, f"skip {r.ev['trigger']} timed_out {sk.get('timed_out')}")

def windows(r, x):
    ok, w = wait_until(lambda: evs(x.host) == 1 and evs(x.client) == 1, WINDOWS_S)
    r.ev["windowsS"] = w
    guard(r, x, "bothWindows", ok, f"eventStates host {evs(x.host)} / client {evs(x.client)}; "
                                   f"stacks {stack(x.host)} / {stack(x.client)}")

def press_ok(r, x, gc):
    """The real event-window OK on `gc`: its top read first, the atomic keep list passed anyway."""
    t = top(gc)
    resp = gc.cmd({"cmd": "dismiss_popup", "keep": list(KEEP)}) if EV in t else {}
    r.ev[f"{gc.name}OK"] = {"top": t, "handled": resp.get("handled"), "at": round(time.time() - r.t0, 2)}
    guard(r, x, f"{gc.name}OK", resp.get("handled") == EV, f"top {t}, resp {resp}")

def poll(x, secs):
    out, t0 = [], time.time()
    while time.time() - t0 < secs:
        ts = time.time()
        s = {"t": round(ts - t0, 2)}
        for gc, k in ((x.host, "h"), (x.client, "c")):
            e, p = es(gc), rp(gc, 0)
            s[k] = dict(e, mp=p.get("monthsPassed"), dp=p.get("daysPassed"), allow=p.get("allowCutscene"))
        out.append(s)
        time.sleep(max(0.0, POLL_I - (time.time() - ts)))
    return out

def seen(samples, k, f):
    """Distinct values of field f on side k over the poll, as [value, first t]."""
    out = []
    for s in samples:
        if not out or out[-1][0] != s[k][f]:
            out.append([s[k][f], s["t"]])
    return out

def summary(samples):
    return {f"{k}.{f}": seen(samples, k, f) for k in "hc"
            for f in ("ending", "statistics", "campaignEnded", "mp", "dp", "allow")} | {"n": len(samples)}

def end(r, x, cur):
    r.ev["end"] = {gc.name: snap(gc) for gc in (x.host, x.client)}
    r.ev["log"] = {gc.name: log_ev(gc, cur[gc.name]) for gc in (x.host, x.client)}

def row_h17b_1(r, x):
    """Month counter: the client's event OK first; the host keeps its counters."""
    h, c = x.host, x.client
    trigger(r, x, h, T_EVSTORY, True, geo.popup(EV, *KEEP))
    windows(r, x)
    cur = {gc.name: log_cur(gc) for gc in (h, c)}
    s0 = r.ev["S0"] = {gc.name: snap(gc) for gc in (h, c)}
    m0, d0 = s0["host"]["research_probe"]["monthsPassed"], s0["host"]["research_probe"]["daysPassed"]
    press_ok(r, x, c)
    p = poll(x, 3.0)
    r.ev["poll"] = summary(p)
    guard(r, x, "hostLatch", any(s["h"]["allow"] is False for s in p),
          f"the client's packet never reached the host: {r.ev['poll']['h.allow']}")
    press_ok(r, x, h)
    time.sleep(1.0)
    st = geo.settle(h, c, keep=list(KEEP))
    r.ev["settle"] = st.get("dismissed")
    end(r, x, cur)
    e = {n: v["research_probe"] for n, v in r.ev["end"].items()}
    r.cell("hostMonths", all(s["h"]["mp"] == m0 for s in p),
           f"the host's month count took the client's day count (F7209): S0 {m0}, polls {r.ev['poll']['h.mp']}")
    r.cell("hostDays", all(s["h"]["dp"] == d0 for s in p), f"S0 {d0}, polls {r.ev['poll']['h.dp']}")
    r.cell("clientMonths", e["client"]["monthsPassed"] == e["host"]["monthsPassed"],
           f"end client {e['client']['monthsPassed']} / host {e['host']['monthsPassed']}")
    r.cell("endings", e["host"]["ending"] == 0 and e["client"]["ending"] == 0,
           f"end host {e['host']['ending']} / client {e['client']['ending']}")

def ending_row(r, x, on, topic, shared, keep, want, cut, stock=False):
    """trigger(topic, on) to the row's interest; the starting machine ends; the other machine must end the same way."""
    h, c = x.host, x.client
    rx, sk, rk = (c, "h", "c") if on is h else (h, "c", "h")
    cur = {gc.name: log_cur(gc) for gc in (h, c)}
    s0 = r.ev["S0"] = {gc.name: snap(gc) for gc in (h, c)}
    trigger(r, x, on, topic, shared, geo.popup(*keep))
    p = poll(x, 5.0)
    r.ev["poll"] = summary(p)
    end(r, x, cur)
    guard(r, x, "starterEnds", any(s[sk]["ending"] == want and s[sk]["statistics"] for s in p),
          f"{on.name}: ending {r.ev['poll'][sk + '.ending']}, statistics {r.ev['poll'][sk + '.statistics']}")
    plays = r.ev["log"][rx.name]["plays"].get(cut, 0)    # R-H17b-R-1: the receiver played this packet's cutscene since S0
    slide = stock and stock_play(rx, cur[rx.name])      # R-H17b-G-2 (H17b-3): or the stock loseGame slideshow
    guard(r, x, "receiverPlay", plays >= 1 or slide, f"the packet never reached {rx.name}: {cut} plays since S0 {plays}, "
                                                     f"stock slideshow {slide}, log {r.ev['log'][rx.name]}")
    return p, s0, rk

def row_h17b_2(r, x):
    p, _s0, rk = ending_row(r, x, x.host, T_WIN, True, KEEP, 1, "STR_H17B_WIN")
    r.cell("replicaEnds", any(s[rk]["ending"] == 1 and s[rk]["statistics"] and s[rk]["campaignEnded"] for s in p),
           "the second player's campaign did not end with the host's research ending (F7207): replica ending "
           f"{r.ev['poll']['c.ending']}, statistics {r.ev['poll']['c.statistics']}")

def row_h17b_3(r, x):
    p, _s0, rk = ending_row(r, x, x.host, T_FREE, True, KEEP_B, 2, "STR_H17B_LOSE", stock=True)
    lose = (r.ev["end"]["host"]["research_probe"].get("researched") or {}).get(T_LOSE)
    guard(r, x, "hostResearchedLose", lose is True, f"host researched {T_LOSE}: {lose}")
    r.cell("replicaEnds", any(s[rk]["ending"] == 2 and s[rk]["statistics"] for s in p),
           "the free topic's ending never reached the second player (F7207): replica ending "
           f"{r.ev['poll']['c.ending']}, statistics {r.ev['poll']['c.statistics']}")

def row_h17b_4(r, x):
    """Event ending: the host's OK first; the replica's open window is replaced by the end screen."""
    h, c = x.host, x.client
    trigger(r, x, h, T_EVWIN, True, geo.popup(EV, *KEEP))
    windows(r, x)
    cur = {gc.name: log_cur(gc) for gc in (h, c)}
    r.ev["S0"] = {gc.name: snap(gc) for gc in (h, c)}
    press_ok(r, x, h)
    p = poll(x, 5.0)
    r.ev["poll"] = summary(p)
    end(r, x, cur)
    r.ev["replicaEventStates"] = n_ev = evs(c)
    guard(r, x, "starterEnds", any(s["h"]["ending"] == 1 and s["h"]["statistics"] for s in p),
          f"host: ending {r.ev['poll']['h.ending']}, statistics {r.ev['poll']['h.statistics']}")
    guard(r, x, "receiverLatch", any(s["c"]["allow"] is False for s in p),
          f"the packet never reached the replica: allowCutscene {r.ev['poll']['c.allow']}")
    r.cell("replicaEnds", any(s["c"]["ending"] == 1 and s["c"]["statistics"] for s in p),
           "the host's event ending did not end the second player's campaign (F7207): replica ending "
           f"{r.ev['poll']['c.ending']}, statistics {r.ev['poll']['c.statistics']}")
    r.cell("replicaWindow", n_ev == 0, f"the replica's event window stayed: eventStates {n_ev}, stack "
                                       f"{r.ev['end']['client']['stack']}")

def row_h17b_5(r, x):
    """SEPARATE: the client's own research ending ends the host's campaign too (V1, D239 a); the host keeps its months."""
    p, s0, rk = ending_row(r, x, x.client, T_WIN, False, KEEP, 1, "STR_H17B_WIN")
    m0 = s0["host"]["research_probe"]["monthsPassed"]
    r.cell("hostEnds", any(s["h"]["ending"] == 1 and s["h"]["statistics"] for s in p),
           f"the partner's campaign did not end (V1, D239 a): host ending {r.ev['poll']['h.ending']}, "
           f"statistics {r.ev['poll']['h.statistics']}")
    r.cell("hostMonths", all(s["h"]["mp"] == m0 for s in p),
           f"the host's month count took the client's day count: S0 {m0}, polls {r.ev['poll']['h.mp']}")

def run_one(rid, fn, x, results):
    r = Row(rid)
    try:
        fn(r, x)
    except GuardMiss:
        try:
            geo.settle(x.host, x.client, keep=list(KEEP_B))
        except Exception as e:
            r.ev["settleAfterMiss"] = short(e)
    except Exception as e:
        r.cell("exception", False, short(e, 800))
    r.ev["cellsPassed"], r.ev["wallS"] = r.passed, round(time.time() - r.t0, 1)
    print(f"EVIDENCE {rid}: {json.dumps(r.ev, sort_keys=True, default=str)}", flush=True)
    results[rid] = not r.fails
    print(f"PASS {rid}" if not r.fails else f"FAIL {rid}: {len(r.fails)} cell(s): " + " | ".join(r.fails), flush=True)

def boot_d():
    tag, (hp, cp, lp) = BOOT_D
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
    t0, js, x = time.time(), None, None
    try:
        js = up()
        x = SimpleNamespace(host=js.host, client=js.client)
        walls[tag + " bring-up"] = round(time.time() - t0, 1)
        info = {gc.name: dict(snap(gc), mod=[ln.split("\t")[-1] for ln in log_lines(gc) if "Coop_Cutscene_Test" in ln][:2])
                for gc in (x.host, x.client)}
        print(f"EVIDENCE boot {tag}: {json.dumps(info, sort_keys=True, default=str)}", flush=True)
    except Exception as e:
        x = None
        print(f"CAPTURE {tag} (boot miss): {short(e, 3000)}", flush=True)
        for rid, _fn in rows:
            results[rid] = False
            print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot", flush=True)
    try:
        for rid, fn in (rows if x is not None else ()):
            run_one(rid, fn, x, results)
    finally:
        try:
            js is not None and js.shutdown()
        except Exception as e:
            print(f"[w2h17b] {tag} shutdown: {short(e)}", flush=True)
        walls[tag] = round(time.time() - t0, 1)

ROWS_A = (("H17b-1", row_h17b_1), ("H17b-2", row_h17b_2))
ROWS_B, ROWS_C, ROWS_D = (("H17b-3", row_h17b_3),), (("H17b-4", row_h17b_4),), (("H17b-5", row_h17b_5),)

def main():
    t0, results, walls = time.time(), {}, {}
    for (tag, ports), rows in ((BOOT_A, ROWS_A), (BOOT_B, ROWS_B), (BOOT_C, ROWS_C)):
        boot(tag, lambda tag=tag, ports=ports: shared_fixture.bring_up(tag, ports, mods=(MOD,)), rows, results, walls)
    boot(BOOT_D[0], boot_d, ROWS_D, results, walls)
    all_rows = ROWS_A + ROWS_B + ROWS_C + ROWS_D
    failed = [rid for rid, _ in all_rows if not results.get(rid)]
    print(f"\ntest_w2_cutscene_endings: {len(all_rows) - len(failed)}/{len(all_rows)} passed (fail={failed}) "
          f"walls {walls} in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
