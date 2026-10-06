"""W2-H17d (F7719, F7720, F7721, F7727; D226 a; Q1 a .. Q5 a; R-H17d-T0-1): in SHARED a story cutscene that both
machines play at their own OK (a geoscape event window, the monthly game-over report) plays exactly once on each
machine; an ending is still relayed (R-H17b-1) and SEPARATE keeps the relay. Spec docs rewrite/prompts/
w2h17d_event_cutscene_once.md (f); TASK 0 rewrite/w2h17d-task0/CONSTANTS.md. Mod Coop_Event_Cutscene_Test: three
empty cutscenes (a "play" = one `cutscene definition empty: <id>` engine-log line after the row's S0 mark, read 1.0 s
after the row's last OK), events STR_H17D_EV_A -> STR_H17D_A and STR_H17D_EV_B -> STR_H17D_B spawned by topics
STR_H17D_T_A / STR_H17D_T_B, and defeatScore 100000 + gameOver.loseRating STR_H17D_MR (a month-1 game over whose
video has no loseGame). Probes (read-only): research_probe (allowCutscene), geo_event_probe (eventStates,
event.texts.title), get_state, ending_state, geo_state; levers research_start, set_research_cost, set_geo_day,
dismiss_popup. Row frame: trigger = host research_start per topic, listed on the host (and the replica in SHARED)
within 5 s, set_research_cost 1, a 2-day skip (speed 5, real timeout 150 s) to the event window; OK = dismiss_popup
with the keep list (CutsceneState, StatisticsState) after reading the top, so no dismiss_popup ever reaches a machine
whose top is one of them; poll = research_probe.allowCutscene every 0.2 s. A latch read is a cell only where a window
sits under the received cutscene (H17d-1 host, H17d-2 replica before its own OK, H17d-4 host); elsewhere
GeoscapeState::init re-arms the latch and the counts carry the verdict. H17d-2 reads its first window's title at run
time (events of one day fire in pointer order, F7730); X = the first window, Y = the other event.
Boot A (SHARED): H17d-1; Boot B (SHARED): H17d-2; Boot C (SEPARATE): H17d-3; Boot D (SHARED): H17d-4.
RED (commit 1): H17d-1, H17d-2, H17d-4 fail on their named cells, H17d-3 passes; GREEN: all pass. "G:" cells are
guards (CAPTURE on a miss). EVIDENCE then PASS / FAIL per row; ONE run; every row runs after a failure; exit 0 only if
all pass, else 2.
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

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_Event_Cutscene_Test")
BOOT_A = ("w2h17da", (49392, 49393, 47372))      # SHARED; lobby 47372 (F7731)
BOOT_B = ("w2h17db", (49394, 49395, 47374))      # SHARED
BOOT_C = ("w2h17dc", (49396, 49397, 47376))      # SEPARATE
BOOT_D = ("w2h17dd", (49398, 49399, 47378))      # SHARED
T_A, T_B = "STR_H17D_T_A", "STR_H17D_T_B"
EV_A, EV_B = "STR_H17D_EV_A", "STR_H17D_EV_B"
CUT, CUT_MR = {EV_A: "STR_H17D_A", EV_B: "STR_H17D_B"}, "STR_H17D_MR"
EV, MRS, KEEP = "GeoscapeEventState", "MonthlyReportState", ("CutsceneState", "StatisticsState")
PLAY = "cutscene definition empty: "
SKIP_MIN, POLL_I, LISTED_S, WINDOWS_S, SECOND_S, DAY_S = 60 * 24 * 2, 0.2, 5.0, 5.0, 3.0, 10.0
FLUSH_S = 1.0                                    # TASK 0: every play line readable <= 0.104 s after its OK

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
        return {"research_probe": gc.cmd({"cmd": "research_probe", "names": [T_A, T_B], "tail": 4}),
                "geo_event_probe": gep(gc), "get_state": stack(gc), "logTail": log_lines(gc)[-30:]}
    except Exception as e:
        return f"probe failed: {short(e)}"

def guard(r, x, name, ok, detail):
    """A miss: CAPTURE both machines' research_probe, geo_event_probe, get_state and engine log tail."""
    if r.cell("G:" + name, ok, detail):
        return
    cap = {gc.name: capture(gc) for gc in (x.host, x.client)}
    print(f"CAPTURE {r.rid} (guard {name}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise GuardMiss(f"guard {name}")

class Row:
    def __init__(self, rid):
        self.rid, self.t0, self.ev, self.fails, self.passed = rid, time.time(), {}, [], []
    def cell(self, name, ok, detail=""):
        (self.passed.append(name) if ok else self.fails.append(f"{name}: {detail}"))
        return ok

def skip(r, x, minutes, interest, want):
    t = time.time()
    sk = geo.skip_ingame_time(x.host, x.client, minutes, speed_idx=5, interest=interest, real_timeout=150)
    r.ev["skip"] = {"hit": sk.get("hit"), "skipS": round(time.time() - t, 2), "dismissed": sk.get("dismissed")}
    guard(r, x, "hit", sk.get("hit") is not None and want in str(sk.get("hit")),       # F7809: never game_minutes
          f"skip {r.ev['skip']} timed_out {sk.get('timed_out')}")

def trigger(r, x, topics, scientists, shared):
    """Host research_start per topic, listed (both in SHARED) within 5 s, set_research_cost 1, the skip to a window."""
    h, c = x.host, x.client
    st = {t: h.cmd({"cmd": "research_start", "topic": t, "scientists": scientists}).get("ok") for t in topics}
    ok, w = wait_until(lambda: all(listed(h, t) and (not shared or listed(c, t)) for t in topics), LISTED_S)
    r.ev["trigger"] = {"topics": topics, "start": st, "listedS": w}
    guard(r, x, "listed", all(v is True for v in st.values()) and ok, f"start {st}; listed {ok} after {w} s")
    r.ev["trigger"]["cost"] = {t: h.cmd({"cmd": "set_research_cost", "topic": t, "cost": 1}).get("ok") for t in topics}
    skip(r, x, SKIP_MIN, geo.popup(EV, *KEEP), EV)

def press_ok(r, x, gc, want, label):
    """The real OK on `gc`: its top read first, the atomic keep list passed anyway (guard: handled == want)."""
    t = top(gc)
    ok_top = want in t and not any(k in t for k in KEEP)
    resp = gc.cmd({"cmd": "dismiss_popup", "keep": list(KEEP)}) if ok_top else {}
    o = r.ev[label] = {"top": t, "handled": resp.get("handled"), "at": round(time.time() - r.t0, 2), "after": top(gc)}
    guard(r, x, label, resp.get("handled") == want, f"top {t}, resp {resp}")
    return o

def poll(gc, secs, with_title=False):
    out, t0 = [], time.time()
    while time.time() - t0 < secs:
        ts = time.time()
        s = {"t": round(ts - t0, 2), "allow": allow(gc), "top": top(gc)}
        if with_title:
            s["title"] = title(gc)
        out.append(s)
        time.sleep(max(0.0, POLL_I - (time.time() - ts)))
    return out

def seen(samples, f):
    """Distinct values of field f over the poll, as [value, first t]."""
    out = []
    for s in samples:
        if not out or out[-1][0] != s[f]:
            out.append([s[f], s["t"]])
    return out

def both_windows(r, x):
    ok, w = wait_until(lambda: evs(x.host) == 1 and evs(x.client) == 1, WINDOWS_S)
    tt = r.ev["titles"] = {gc.name: title(gc) for gc in (x.host, x.client)}
    return ok, f"eventStates host {evs(x.host)} / client {evs(x.client)} after {w} s; titles {tt}"

def mark(r, x):
    r.ev["S0"] = {gc.name: snap(gc) for gc in (x.host, x.client)}
    return {gc.name: log_cur(gc) for gc in (x.host, x.client)}

def counts(r, x, cur):
    time.sleep(FLUSH_S)
    pl = r.ev["plays"] = {gc.name: plays(gc, cur[gc.name]) for gc in (x.host, x.client)}
    r.ev["end"] = {gc.name: snap(gc) for gc in (x.host, x.client)}
    return pl

def row_h17d_1(r, x):
    """S1: both windows open, the client presses OK first; the host must not get the client's video."""
    h, c, a = x.host, x.client, CUT[EV_A]
    trigger(r, x, [T_A], 10, True)
    ok, d = both_windows(r, x)
    guard(r, x, "bothWindows", ok and r.ev["titles"] == {"host": EV_A, "client": EV_A}, d)
    cur = mark(r, x)
    press_ok(r, x, c, EV, "clientOK")
    p = poll(h, 3.0)
    r.ev["hostPoll"] = {"allow": seen(p, "allow"), "top": seen(p, "top"), "n": len(p)}
    r.cell("hostNoRelay", all(s["allow"] is True for s in p),
           f"the client's OK relayed a story cutscene: host allowCutscene {r.ev['hostPoll']['allow']}")
    press_ok(r, x, h, EV, "hostOK")
    pl = counts(r, x, cur)
    r.cell("hostOnce", pl["host"].get(a, 0) == 1, "the host played the story cutscene twice: the client's relay, then "
                                                   f"its own OK (F7719): host {a} plays {pl['host'].get(a, 0)}")
    guard(r, x, "clientOnce", pl["client"].get(a, 0) == 1, f"client {a} plays {pl['client'].get(a, 0)}")

def row_h17d_2(r, x):
    """Two windows (R-H17d-T0-1): the host's OK on both first, then the replica's; the replica must play X once."""
    h, c = x.host, x.client
    trigger(r, x, [T_A, T_B], 5, True)
    ok, d = both_windows(r, x)
    th, tc = r.ev["titles"]["host"], r.ev["titles"]["client"]
    guard(r, x, "sameFirst", ok and th == tc and th in CUT, d)
    X, Y = th, (EV_B if th == EV_A else EV_A)
    cx, cy = CUT[X], CUT[Y]
    r.ev["order"] = {"X": X, "Y": Y}
    cur = mark(r, x)
    press_ok(r, x, h, EV, "hostOK1")
    ok, w = wait_until(lambda: title(h) == Y, SECOND_S)
    held = r.ev["held"] = {"hostSecondS": w, "hostTime": geo_s(h).get("time"), "replicaTitle": title(c),
                           "replicaStack": stack(c)}
    guard(r, x, "hostSecond", ok, f"the host's second window {Y} did not show within {SECOND_S} s: {title(h)}")
    guard(r, x, "replicaHeld", held["replicaTitle"] == X, f"the replica's top is not its first window: {held}")
    press_ok(r, x, h, EV, "hostOK2")
    p = poll(c, 2.0, with_title=True)
    r.ev["replicaPoll"] = {"allow": seen(p, "allow"), "title": seen(p, "title"), "n": len(p)}
    r.cell("replicaNoRelay", all(s["allow"] is True for s in p), "the host's OK relayed a story cutscene over the "
                                                                 f"replica's open window: {r.ev['replicaPoll']['allow']}")
    guard(r, x, "replicaHeldPoll", all(s["title"] == X for s in p),
          f"the replica showed another window before its own first OK: {r.ev['replicaPoll']['title']}")
    hp = r.ev["hostPlaysMid"] = plays(h, cur["host"])
    guard(r, x, "hostMid", hp.get(cx, 0) == 1 and hp.get(cy, 0) == 1, f"host plays before the replica's OK {hp}")
    press_ok(r, x, c, EV, "replicaOK1")
    ok, w = wait_until(lambda: title(c) == Y, SECOND_S, 0.05)
    r.ev["replicaSecond"] = {"s": w, "allow": allow(c)}
    guard(r, x, "replicaSecond", ok, f"the replica's second window {Y} did not show within {SECOND_S} s: {title(c)}")
    press_ok(r, x, c, EV, "replicaOK2")
    pl = counts(r, x, cur)
    n = r.ev["counts"] = {f"{m}.{k}": pl[m].get(cid, 0) for m in ("host", "client") for k, cid in (("X", cx), ("Y", cy))}
    r.cell("replicaOnce", n["client.X"] == 1, f"the second player played the story cutscene {cx} twice: the host's "
                                              f"relay over its open window, then its own OK (F7720): {n['client.X']}")
    guard(r, x, "onceElse", n["host.X"] == 1 and n["host.Y"] == 1 and n["client.Y"] == 1, f"counts {n}")

def row_h17d_3(r, x):
    """SEPARATE (no-change control): the host's own event; the partner has no window and plays the relay once."""
    h, c, a = x.host, x.client, CUT[EV_A]
    trigger(r, x, [T_A], 10, False)
    e0 = evs(c)
    time.sleep(1.0)
    pw = r.ev["partnerWindows"] = {"atHit": e0, "plus1s": evs(c), "stack": stack(c)}
    guard(r, x, "partnerNoWindow", e0 == 0 and pw["plus1s"] == 0, f"the SEPARATE partner has an event window: {pw}")
    cur = mark(r, x)
    press_ok(r, x, h, EV, "hostOK")
    pl = counts(r, x, cur)
    r.cell("hostOnce", pl["host"].get(a, 0) == 1, f"host {a} plays {pl['host'].get(a, 0)}")
    r.cell("partnerOnce", pl["client"].get(a, 0) == 1, "the SEPARATE partner no longer sees the host's event video "
                                                       f"(F7724, R-H17b-1): client {a} plays {pl['client'].get(a, 0)}")

def row_h17d_4(r, x):
    """Monthly game over without an ending (F7727): the client's two OKs first; the host must not get its video."""
    h, c = x.host, x.client
    r.ev["setDay"] = h.cmd({"cmd": "set_geo_day", "day": 31, "hour": 22}).get("ok")
    ok, w = wait_until(lambda: (geo_s(c).get("time") or {}).get("day") == 31, DAY_S)
    guard(r, x, "replicaDay31", ok, f"host {geo_s(h).get('time')} / replica {geo_s(c).get('time')} after {w} s")
    skip(r, x, 180, geo.popup(MRS, *KEEP), MRS)
    ok, w = wait_until(lambda: MRS in top(h) and MRS in top(c), WINDOWS_S)
    guard(r, x, "bothReports", ok, f"stacks {stack(h)} / {stack(c)} after {w} s")
    cur = mark(r, x)
    o = press_ok(r, x, c, MRS, "clientOK1")
    guard(r, x, "failurePage", MRS in o["after"], f"the client's first OK left {o['after']} on top (no failure page)")
    press_ok(r, x, c, MRS, "clientOK2")
    p = poll(h, 3.0)
    r.ev["hostPoll"] = {"allow": seen(p, "allow"), "top": seen(p, "top"), "n": len(p)}
    r.cell("hostNoRelay", all(s["allow"] is True for s in p),
           f"the client's OK relayed the game-over video: host allowCutscene {r.ev['hostPoll']['allow']}")
    press_ok(r, x, h, MRS, "hostOK1")
    press_ok(r, x, h, MRS, "hostOK2")
    pl = counts(r, x, cur)
    r.cell("hostOnce", pl["host"].get(CUT_MR, 0) == 1,
           f"the host played the game-over video twice (F7727): host {CUT_MR} plays {pl['host'].get(CUT_MR, 0)}")
    guard(r, x, "clientOnce", pl["client"].get(CUT_MR, 0) == 1, f"client {CUT_MR} plays {pl['client'].get(CUT_MR, 0)}")
    e = {n: v["ending"] for n, v in r.ev["end"].items()}
    guard(r, x, "endings", e == {"host": 0, "client": 0}, f"endings {e}")

def run_one(rid, fn, x, results):
    r = Row(rid)
    try:
        fn(r, x)
    except GuardMiss:
        try:
            geo.settle(x.host, x.client, keep=list(KEEP))
        except Exception as e:
            r.ev["settleAfterMiss"] = short(e)
    except Exception as e:
        r.cell("exception", False, short(e, 800))
    r.ev["cellsPassed"], r.ev["wallS"] = r.passed, round(time.time() - r.t0, 1)
    print(f"EVIDENCE {rid}: {json.dumps(r.ev, sort_keys=True, default=str)}", flush=True)
    results[rid] = not r.fails
    print(f"PASS {rid}" if not r.fails else f"FAIL {rid}: {len(r.fails)} cell(s): " + " | ".join(r.fails), flush=True)

def boot_sep(tag, ports):
    hp, cp, lp = ports
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
        info = {gc.name: dict(snap(gc), mod=[ln.split("\t")[-1] for ln in log_lines(gc) if "Coop_Event_Cutscene_Test" in ln][:2])
                for gc in (x.host, x.client)}
        info["startedAt"] = time.strftime("%H:%M:%S", time.localtime(t0))
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
            print(f"[w2h17d] {tag} shutdown: {short(e)}", flush=True)
        walls[tag] = round(time.time() - t0, 1)

BOOTS = ((BOOT_A, (("H17d-1", row_h17d_1),), True), (BOOT_B, (("H17d-2", row_h17d_2),), True),
         (BOOT_C, (("H17d-3", row_h17d_3),), False), (BOOT_D, (("H17d-4", row_h17d_4),), True))

def main():
    t0, results, walls = time.time(), {}, {}
    for (tag, ports), rows, shared in BOOTS:
        up = (lambda t=tag, p=ports: shared_fixture.bring_up(t, p, mods=(MOD,))) if shared else \
             (lambda t=tag, p=ports: boot_sep(t, p))
        boot(tag, up, rows, results, walls)
    all_rows = [rid for _b, rows, _s in BOOTS for rid, _fn in rows]
    failed = [rid for rid in all_rows if not results.get(rid)]
    print(f"\ntest_w2_event_cutscene_once: {len(all_rows) - len(failed)}/{len(all_rows)} passed (fail={failed}) "
          f"walls {walls} in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
