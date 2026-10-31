"""test_event_relay_once.py: in a SEPARATE campaign with shared research (Research Sync on), an ending that both players
reach through research still relays: the first OK ends both campaigns and each machine plays the ending video once.
Mod Coop_Event_Relay_Test: empty cutscenes (a "play" = one `cutscene definition empty: <id>` engine-log line after the
row's mark, read 1.0 s after the row's last OK); STR_RELAY_T_WIN -> STR_RELAY_EV_WIN, whose cutscene wins the game.
SEPARATE boot, EnableResearchSync on both machines, boot guard event_state.researchMode {shared false, sync true} on
both. OK = dismiss_popup with the keep list (CutsceneState, StatisticsState) after reading the top. F = the machine
whose window shows first, O = the other.
Boot ending (key "49434"): shared_ending, 3 GUARD cells: firstEnds, otherEnds, plays.
"guard:" = a guard: CAPTURE line and the row ends (later cells "not reached"). EVIDENCE per row, PASS / FAIL per cell,
the row verdict; ONE run: exit 0 only when every cell passes, else 2.
no wait-hook; run to completion in the foreground.
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
KEY_ENDING = "49434"
T_W, EV_W, CUT_W = "STR_RELAY_T_WIN", "STR_RELAY_EV_WIN", "STR_RELAY_WIN"
EV, KEEP = "GeoscapeEventState", ("CutsceneState", "StatisticsState")
PLAY = "cutscene definition empty: "
FLUSH_S, POLL_I, LISTED_S = 1.0, 0.2, 5.0   # every state within 0.1 s
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
def geo_events(gc):
    """This world's pending geoscape events: {name: (countdown, over)}."""
    return {e.get("name"): (e.get("countdown"), e.get("over")) for e in gc.cmd({"cmd": "geo_events"}).get("events", [])}


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
    """Since `cur` (the row's mark): this machine's cutscene plays per id."""
    out = {}
    for ln in log_lines(gc, cur):
        if PLAY in ln:
            cid = ln.split(PLAY, 1)[1].strip()
            out[cid] = out.get(cid, 0) + 1
    return out


def capture(gc):
    try:
        return {"research_probe": gc.cmd({"cmd": "research_probe", "names": [T_W], "tail": 4}),
                "geo_event_probe": gep(gc), "geo_events": geo_events(gc), "researchMode": rmode(gc),
                "get_state": stack(gc), "logTail": log_lines(gc)[-30:]}
    except Exception as e:
        return f"probe failed: {short(e)}"


def cap_line(r, x, why):
    cap = {gc.name: capture(gc) for gc in (x.host, x.client)}
    print(f"CAPTURE {r.rid} ({why}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def guard(r, x, name, ok, detail):
    """A miss: CAPTURE both machines' probes and engine log tails, then the row ends."""
    if r.cell("guard:" + name, ok, detail):
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


def seen(samples, f):
    """Distinct values of field f over the poll, as [value, first t]."""
    out = []
    for s in samples:
        if not out or out[-1][0] != s[f]:
            out.append([s[f], s["t"]])
    return out


def mark(r, x):
    r.ev["atMark"] = {gc.name: snap(gc) for gc in (x.host, x.client)}
    gstep(r, x, "atMark")
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


def row_shared_ending(r, x):
    """An ending both worlds hold: F's OK ends both campaigns; each plays the ending once."""
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
    gcell(r, x, "otherEnds", first[O.name] is not None, f"{O.name} never showed ending 1 + StatisticsState within 5 s: "
                                                        f"{r.ev['endPoll']}")
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
            print(f"[test_event_relay_once] {tag} shutdown: {short(e)}", flush=True)
        walls[tag] = round(time.time() - t0, 1)


BOOTS = (("event_relay_ending", KEY_ENDING,
          (("shared_ending", row_shared_ending, ("firstEnds", "otherEnds", "plays")),)),)


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
