"""in SEPARATE co-op with Research Sync on, a paired certain
event (coopShared) whose reward is one random research topic teaches BOTH players the host's pick and opens the same article;
today each machine rolls its own (GE :453) and the sync skips a paired copy (GE :514). Spec docs
rewrite/prompts/w2h77_event_research_pick.md (f); TASK 0 rewrite/w2h77-task0/sa/CONSTANTS.md. Mod Coop_Event_Pick_Test (spec
Appendix C): topics STR_H77_P01..Z16; certain events EV_P, EV_Z (month 0), EV_W (every month from 1). One SEPARATE boot (key
"49470"), EnableResearchSync on both, boot guard researchMode {shared false, sync true} on both, EV_Z's countdown pinned to
EVZ_PIN on both right after the bring-up (W2-U9d, R-I63-1: its boot roll is unseeded). Every fire seeds both machines
(SEEDS: host, client) right before the host's set_event_countdown; the client's copy fires on the host's packet (G:held). Picks
are read at runtime, no topic is pinned: the host's draws before its pick vary per boot.
Collision: the host's pick equals the client's own roll (its seed's one draw over its unknown topics, F21893): the row
prints COLLISION and fires once more on the next month's EV_W with host seed + RESEED; a second collision fails it "fixture".
Rows (8 cells):
  EP-1 month 0, EV_P: sameTopic (RED), sameArticle (RED), noPopup (GUARD cell)
  EP-2 roll_month, EV_W (the X-Com Files red-tape shape): sameTopic (RED), sameArticle (RED), noPopup (GUARD cell)
  EP-3 research sync off, EV_Z: ownTopics (GUARD cell), noPopup (GUARD cell)
"G:" = a guard: CAPTURE line and the row ends (later cells "not reached"). EVIDENCE per row, PASS / FAIL per cell, the row
verdict; every row runs after a failure; ONE run: exit 0 only when every cell passes, else 2.
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

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_Event_Pick_Test")
KEY = "49470"
EV_P, EV_W, EV_Z = "STR_H77_EV_P", "STR_H77_EV_W", "STR_H77_EV_Z"
P, W, Z = (["STR_H77_%s%02d" % (k, i) for i in range(1, 17)] for k in "PWZ")
SEEDS = {"EP-1": (11, 12), "EP-2": (21, 22), "EP-3": (31, 32)}   # TASK 0 (CONSTANTS.md): host, client
COUNTDOWN, SKIP_MIN, PAIRED_S, HELD_MIN, RESEED = 60, 180, 10.0, 240, 2
# EV_Z's countdown is rolled at the boot (timer 1440 + random(20000), before any
# set_seed) and EP-1 + EP-2 spend 1380-1560 game min (more under load) before EP-3's G:held, so a roll below ~1710 failed it.
# Pinned on both machines: > HELD_MIN + EP-3's own spend before its fire (0) + 2 x the worst EP-1 + EP-2 spend (570 + 3 x 990,
# a collision refire in each row) = 7320.
EVZ_PIN = 7500
MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
U64 = (1 << 64) - 1


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
def rmode(gc): return gc.cmd({"cmd": "event_state"}).get("researchMode") or {}  # noqa: E704
def rng(gc): return gc.cmd({"cmd": "event_state"}).get("rngSeed")  # noqa: E704
def learned(gc, t): return gc.cmd({"cmd": "is_researched", "topic": t}).get("researched")  # noqa: E704
def known(gc, topics): return [t for t in topics if learned(gc, t)]  # noqa: E704
def months(gc): return (gc.cmd({"cmd": "geo_state"}) or {}).get("monthsPassed")  # noqa: E704


def geo_events(gc):
    """This world's pending geoscape events: {name: (countdown, over)}."""
    return {e.get("name"): (e.get("countdown"), e.get("over")) for e in gc.cmd({"cmd": "geo_events"}).get("events", [])}


def pending(gc, name):
    ge = geo_events(gc)
    return name in ge and not ge[name][1]


def own_roll(seed, unknown):
    """The client's own pick at `seed`: one draw of src/Engine/RNG.cpp (xorshift64*) over GE's possibilities (its unknown
    topics in researchList order). Returns (topic, the RNG state after that draw as event_state.rngSeed shows it)."""
    x = seed & U64
    x ^= x >> 12
    x ^= (x << 25) & U64
    x ^= x >> 27
    pick = unknown[((x * 2685821657736338717) & U64) % len(unknown)] if unknown else None
    return pick, x - (1 << 64) if x >> 63 else x


def log_lines(gc):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace", newline="") as f:
            return f.read().splitlines()
    except OSError as e:
        return [f"<log read error {e}>"]


def capture(gc, topics):
    try:
        return {"known": known(gc, topics), "geo_events": geo_events(gc), "researchMode": rmode(gc), "rngSeed": rng(gc),
                "get_state": stack(gc), "logTail": log_lines(gc)[-30:]}
    except Exception as e:
        return f"probe failed: {short(e)}"


def cap_line(r, x, why):
    cap = {gc.name: capture(gc, r.topics) for gc in (x.host, x.client)}
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
    def __init__(self, rid, cells, topics):
        self.rid, self.t0, self.ev, self.cells, self.want, self.topics = rid, time.time(), {}, {}, cells, topics

    def cell(self, name, ok, detail=""):
        self.cells[name] = (bool(ok), "" if ok else detail)
        return ok


def drain(gc, win):
    """ES drain (copied): close every popup, VIEW REPORTS on a research popup; 'RC' / 'EV' / 'article:<id>' per popup.
    Also records this machine's rngSeed at the first event window it closes (EVIDENCE only)."""
    seen = []
    for _ in range(30):
        t = geo.top_state(gc)
        if not t or t.endswith("GeoscapeState"):
            break
        if "GeoscapeEventState" in t and gc.name not in win:
            win[gc.name] = rng(gc)
        if "ResearchCompleteState" in t:
            gc.ok({"cmd": "dismiss_popup", "view_reports": True})
            seen.append("RC")
            continue
        r = gc.cmd({"cmd": "dismiss_popup"})
        if not r.get("ok"):
            break
        if r.get("article"):
            seen.append("article:" + r["article"])
        elif r.get("handled") == "GeoscapeEventState":
            seen.append("EV")
        else:
            seen.append(r.get("handled", t))
    return seen


def advance(host, client, minutes, win, settle=3.0):
    """ES advance (copied): speed 4 until the host's clock moved `minutes` (real deadline 120 s), then a 3 s settle."""
    seen = {host.name: [], client.name: []}
    start = geo.game_minutes(host)
    deadline = time.time() + 120
    while time.time() < deadline:
        for gc in (host, client):
            seen[gc.name] += drain(gc, win)
        now = geo.game_minutes(host)
        if now is not None and now - start >= minutes:
            break
        for gc in (host, client):
            if geo.on_geoscape(gc):
                gc.cmd({"cmd": "geo_set_speed", "idx": 4})
        time.sleep(0.4)
    geo.slow_clock(host, client)
    t_end = time.time() + settle
    while time.time() < t_end:
        for gc in (host, client):
            seen[gc.name] += drain(gc, win)
        time.sleep(0.3)
    return seen


def roll_month(r, x, label):
    """ES roll_month (copied): the host's set_geo_day to the month's last day 23:00 (31 in month 0), advance 120, sleep 2.0."""
    h, c = x.host, x.client
    before = {gc.name: months(gc) for gc in (h, c)}
    m = ((h.cmd({"cmd": "geo_state"}) or {}).get("time") or {}).get("month") or 1
    resp = h.cmd({"cmd": "set_geo_day", "day": MONTH_DAYS[m - 1], "hour": 23})
    seen = advance(h, c, 120, {})
    time.sleep(2.0)
    after = {gc.name: months(gc) for gc in (h, c)}
    r.ev[label] = {"setGeoDay": resp, "monthsPassed": [before, after], "seen": seen}
    guard(r, x, "month" + ("" if label == "roll" else "2"), resp.get("ok") is True
          and all(after[n] == (before[n] or 0) + 1 for n in after), f"{r.ev[label]}")


def fire(r, x, ev, topics, seeds, tag):
    """Spec (f) fire: the pair, the held client copy, both seeds, the host's countdown, the skip. Returns this fire's picks."""
    h, c = x.host, x.client
    g = "" if tag == "fire" else "2"
    r.topics = topics
    ok, w = wait_until(lambda: pending(h, ev) and pending(c, ev), PAIRED_S)
    ge = {gc.name: geo_events(gc).get(ev) for gc in (h, c)}
    e = r.ev[tag] = {"event": ev, "countdowns": ge, "pairedS": w}
    guard(r, x, "paired" + g, ok, f"{ev} not pending on both within {PAIRED_S} s: {ge}")
    guard(r, x, "held" + g, (ge["client"] or (0,))[0] > HELD_MIN, f"client countdown {ge['client']} <= {HELD_MIN}")
    before = {gc.name: known(gc, topics) for gc in (h, c)}
    unknown = [t for t in topics if t not in before["client"]]
    for gc in (h, c):
        geo.drain_popups(gc)
    geo.slow_clock(h, c)
    sd = {"host": h.cmd({"cmd": "set_seed", "seed": seeds[0]}), "client": c.cmd({"cmd": "set_seed", "seed": seeds[1]})}
    e["seeds"] = [sd["host"].get("seed"), sd["client"].get("seed")]
    guard(r, x, "seeded" + g, all(v.get("ok") is True for v in sd.values()) and e["seeds"] == list(seeds), f"set_seed {sd}")
    cd = h.cmd({"cmd": "set_event_countdown", "name": ev, "minutes": COUNTDOWN})
    guard(r, x, "countdown" + g, cd.get("ok") is True, f"set_event_countdown {cd}")
    win = {}
    seen = advance(h, c, SKIP_MIN, win)
    new = {gc.name: [t for t in known(gc, topics) if t not in before[gc.name]] for gc in (h, c)}
    own, state = own_roll(seeds[1], unknown)
    p = {"host": (new["host"] or [None])[0], "client": new["client"], "own": own, "RC": {n: seen[n].count("RC") for n in seen},
         "arts": {n: [s for s in seen[n] if s.startswith("article:STR_H77_")] for n in seen}}
    e.update(seen=seen, before=before, new=new, clientOwnRoll=own, windowRng=win, clientOneDraw=win.get("client") == state,
             after={gc.name: geo_events(gc) for gc in (h, c)})
    guard(r, x, "hostWindow" + g, "EV" in seen["host"], f"host seen {seen['host']}")
    guard(r, x, "clientWindow" + g, "EV" in seen["client"], f"client seen {seen['client']}")
    guard(r, x, "hostOne" + g, len(new["host"]) == 1, f"host learned {new['host']}")
    return p


def picks(r, x, ev, topics, seeds):
    """fire; on a collision ONE more fire on the next month's EV_W with host seed + RESEED."""
    p = fire(r, x, ev, topics, seeds, "fire")
    if p["host"] != p["own"]:
        return p
    r.ev["collision"] = [p["host"]]
    print(f"COLLISION {r.rid}: the host's pick {p['host']} = the client's own roll at seed {seeds[1]}; one more fire on the "
          f"next month's {EV_W} with host seed {seeds[0] + RESEED} (R-H77-2)", flush=True)
    roll_month(r, x, "refireRoll")
    p2 = fire(r, x, EV_W, W, (seeds[0] + RESEED, seeds[1]), "refire")
    p2["RC"] = {n: p["RC"][n] + p2["RC"][n] for n in p2["RC"]}
    if p2["host"] == p2["own"]:
        r.ev["collision"].append(p2["host"])
        p2["fixture"] = f"fixture: a second collision ({p2['host']}, R-H77-2)"
    return p2


def red_cells(r, x, p):
    fx, h, cl = p.get("fixture"), p["host"], p["client"]
    r.cell("sameTopic", not fx and cl == [h], fx or f"the client learned {cl}, the host {h} (each rolled its own, F21550)")
    want = ["article:" + str(h)]
    r.cell("sameArticle", not fx and p["arts"]["client"] == p["arts"]["host"] == want,
           fx or f"articles host {p['arts']['host']} / client {p['arts']['client']}, want {want} on both")
    gcell(r, x, "noPopup", p["RC"] == {"host": 0, "client": 0}, f"research popups (RC) {p['RC']}")


def row_ep1(r, x):
    """Month 0, a paired oneTimeSequentialEvents certain event: the client learns the host's pick."""
    red_cells(r, x, picks(r, x, EV_P, P, SEEDS["EP-1"]))


def row_ep2(r, x):
    """Month 1, a paired eventWeights certain event (its two countdowns may differ by 60 min, F21554: never compared)."""
    roll_month(r, x, "roll")
    red_cells(r, x, picks(r, x, EV_W, W, SEEDS["EP-2"]))


def row_ep3(r, x):
    """Research sync off: each player keeps exactly its own roll, as today."""
    h, c = x.host, x.client
    so = r.ev["syncOff"] = {gc.name: gc.cmd({"cmd": "set_research_sync", "enabled": False}) for gc in (c, h)}
    rm = {gc.name: rmode(gc).get("sync") for gc in (h, c)}
    guard(r, x, "syncOff", all(v.get("ok") is True for v in so.values()) and rm == {"host": False, "client": False},
          f"set_research_sync {so}; researchMode.sync {rm}")
    p = picks(r, x, EV_Z, Z, SEEDS["EP-3"])
    fx = p.get("fixture")
    gcell(r, x, "ownTopics", not fx and len(p["client"]) == 1 and p["client"] != [p["host"]],
          fx or f"the host learned {p['host']}, the client {p['client']} (own roll {p['own']}): each must learn exactly its own")
    gcell(r, x, "noPopup", p["RC"] == {"host": 0, "client": 0}, f"research popups (RC) {p['RC']}")


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


def run_one(rid, fn, cells, topics, x, results):
    r = Row(rid, cells, topics)
    try:
        fn(r, x)
    except GuardMiss:
        try:
            geo.settle(x.host, x.client)
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
        time.sleep(2.0)  # ES bring_up: the host's event schedule reaches the client
        for gc in (x.host, x.client):
            geo.drain_popups(gc)
        geo.slow_clock(x.host, x.client)
        walls[tag + " bring-up"] = round(time.time() - t0, 1)
        info = {gc.name: {"researchMode": rmode(gc), "geoEvents": geo_events(gc), "stack": stack(gc), "rngSeed": rng(gc),
                          "mod": [ln.split("\t")[-1] for ln in log_lines(gc) if "Coop_Event_Pick_Test" in ln][:2]}
                for gc in (x.host, x.client)}
        # pin EV_Z on both machines (host first; each world keeps its own copy after the pairing)
        info["evZPin"] = {gc.name: {"reply": gc.cmd({"cmd": "set_event_countdown", "name": EV_Z, "minutes": EVZ_PIN})}
                          for gc in (x.host, x.client)}
        for gc in (x.host, x.client):
            info["evZPin"][gc.name]["after"] = geo_events(gc).get(EV_Z)
        info["startedAt"] = time.strftime("%H:%M:%S", time.localtime(t0))
        print(f"EVIDENCE boot {tag}: {json.dumps(info, sort_keys=True, default=str)}", flush=True)
        rm = {n: (info[n]["researchMode"].get("shared"), info[n]["researchMode"].get("sync")) for n in ("host", "client")}
        if rm != {"host": (False, True), "client": (False, True)}:
            raise RuntimeError(f"boot guard researchMode (shared, sync) {rm}: "
                               + json.dumps({gc.name: capture(gc, P) for gc in (x.host, x.client)}, default=str))
        pin = {n: (info["evZPin"][n]["reply"].get("ok"), (info["evZPin"][n]["after"] or (None,))[0]) for n in ("host", "client")}
        if not all(ok is True and cd is not None and EVZ_PIN - 30 <= cd <= EVZ_PIN for ok, cd in pin.values()):
            raise RuntimeError(f"boot guard {EV_Z} pin {EVZ_PIN} (reply ok, countdown after) {pin}")
    except Exception as e:
        x = None
        print(f"CAPTURE {tag} (boot miss): {short(e, 6000)}", flush=True)
        for rid, _fn, cells, _t in rows:
            results[rid] = ["boot"]
            print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}", flush=True)
            print("\n".join(f"FAIL {rid} {n}: boot" for n in cells) + f"\nFAIL {rid}: boot", flush=True)
    try:
        for rid, fn, cells, topics in (rows if x is not None else ()):
            run_one(rid, fn, cells, topics, x, results)
    finally:
        try:
            if js is not None:
                js.shutdown()
        except Exception as e:
            print(f"[w2h77] {tag} shutdown: {short(e)}", flush=True)
        walls[tag] = round(time.time() - t0, 1)


ROWS = (("EP-1", row_ep1, ("sameTopic", "sameArticle", "noPopup"), P),
        ("EP-2", row_ep2, ("sameTopic", "sameArticle", "noPopup"), W),
        ("EP-3", row_ep3, ("ownTopics", "noPopup"), Z))


def main():
    t0, results, walls = time.time(), {}, {}
    boot("w2h77", KEY, ROWS, results, walls)
    n_cells = sum(len(c) for _r, _fn, c, _t in ROWS)
    failed = {rid: results.get(rid, ["not run"]) for rid, _fn, _c, _t in ROWS if results.get(rid, ["not run"])}
    print(f"\ntest_event_research_pick: {len(ROWS) - len(failed)}/{len(ROWS)} rows passed, failed cells {failed} "
          f"(of {n_cells}) walls {walls} in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
