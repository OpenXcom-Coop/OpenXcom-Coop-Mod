"""W2-H21c (F8883 routed, F8968; spec rewrite/prompts/w2h21c_deployment_preview_recopy.md (f), QH21c-2 a, QH21c-3 a, QH21c-4 a;
TASK 0 rewrite/w2h21c-task0/CONSTANTS.md): in SHARED, a world copy the host sends while ITS Ufopaedia craft deployment preview is open
carries the preview battle; its stand-in soldiers (ids -1..-n) are in no base, so the second player's load builds a unit from a null
soldier and crashes (TASK 0, every red construction: Soldier::getName <- BattleUnit::BattleUnit <- SavedBattleGame::load; BLOB unit ids
-1..-14). A copy landing on the second player's OWN preview closes it like any screen (F8883's premise; guard).
  Boot A bring_up("w2h21pva", (49512, 49513, 47965)):
    H21c-G (GUARD; TASK 0 0/3 deaths) PV(client); client force_resync (role replica, sent true); within W the client stack ==
        [GeoscapeState], has_battle false, alive HOLD s more, no CRASH; CL in order push / pop LoadGameState, pop BattlescapeState,
        pop GeoscapeState, push GeoscapeState; the host alive on [GeoscapeState].
    H21c-1 (named RED; TASK 0 3/3 client crashes) PV(host); HOST force_resync (role host, ok); the host right after the reply: alive,
        BattlescapeState on its stack, isPreview true; RED 1: BLOB noBattle; RED 2: the G client cell; CL in order push / pop
        LoadGameState, push GeoscapeState; END(host) -> [GeoscapeState], has_battle false; js.finish() (worlds equal, zero disk).
  Boot B bring_up("w2h21pvb", (49514, 49515, 47968)):
    H21c-2 (named RED; TASK 0 3/3 client crashes) PV(host); client force_resync (role replica, sent true); within W the host's
        shared_resync_stats.requests +1, alive, BattlescapeState on its stack, isPreview true; then every H21c-1 cell after the reply.
PV = keyGeoUfopedia, "X-COM CRAFT", the SKYRANGER row, keyGeoUfopedia (INFO), "Preview", close_briefing (<= 2 s per probe, SETTLE 0.3 s
before a key or click, F2888); END = end_turn_button, StatsForNerdsState + has_battle false, keyCancel to depth 0; never close_screens on a
preview (F8973). W = 10 s at 0.25 s polls, HOLD = 2 s. CL = the client's openxcom.log after the trigger. BLOB = the host's dump_coop_file
{shared_world} at host.user_dir/xcom1/shared_world; noBattle = no line `battleGame:`. CRASH = new crashlogs/crash_*.log. Setup guard per
boot: stacks [GeoscapeState], localSeat 0 / 1, has_battle false (a miss fails the boot's rows `boot`). A dead client leaves its row's
later cells "not reached" (its crash rc is tolerated at shutdown). EVIDENCE before each verdict; a failed row prints ONE CAPTURE line;
every row runs after a failure; ONE run (WV-D95); exit 0 iff every row passes, else 2.
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import shared_fixture  # noqa: E402
import test_w2_client_research as cr  # noqa: E402  (main-guarded: pd*, read_key)
import test_w2_shared_base_equip as h20  # noqa: E402  (main-guarded)

PORTS_A, PORTS_B = (49512, 49513, 47965), (49514, 49515, 47968)
W, POLL, HOLD, STEP, SETTLE = 10.0, 0.25, 2.0, 2.0, 0.3
GEO, BS, SFN, BRF = "GeoscapeState", "BattlescapeState", "StatsForNerdsState", "BriefingState"
PUSH, POP = "push class OpenXcom::", "pop  class OpenXcom::"
CL_G = [PUSH + "LoadGameState", POP + "LoadGameState", POP + BS, POP + GEO, PUSH + GEO]
CL_1 = [PUSH + "LoadGameState", POP + "LoadGameState", PUSH + GEO]
CRASH_DIR = os.path.join(os.path.dirname(harness.EXE), "crashlogs")
q, stack, short, wait_until = h20.q, h20.stack, h20.short, h20.wait_until

def alive(gc):
    return gc.proc is not None and gc.proc.poll() is None and bool(q(gc, {"cmd": "ping"}).get("pong"))

def on_top(gc, name):
    return stack(gc)[-1:] == [name]

def log_size(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return os.path.getsize(p) if os.path.exists(p) else 0

def log_lines(gc, n0=0):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as f:
            f.seek(n0)
            return [ln.rstrip("\r") for ln in f.read().decode("utf-8", errors="replace").split("\n") if ln.strip()]
    except OSError as e:
        return ["<%s>" % e]

def ui(lines):  # the screen record, the SHARED lines and any T0-I line, message part only
    return [ln.split("\t")[-1] for ln in lines if "[coop-ui]" in ln or "[SHARED]" in ln or "[h21c-t0]" in ln]

def in_order(lines, seq):  # every seq entry in some line, in seq's order
    it = iter(lines)
    return all(any(s in ln for ln in it) for s in seq)

def crash_names():
    return set(os.listdir(CRASH_DIR)) if os.path.isdir(CRASH_DIR) else set()

def crash_info(before):
    out = []
    for name in sorted(n for n in crash_names() - before if n.endswith(".log")):
        with open(os.path.join(CRASH_DIR, name), encoding="utf-8", errors="replace") as f:
            out.append({"file": name, "frames": [ln.strip()[:150] for ln in f if ln.lstrip().startswith(("#0 ", "#1 ", "#2 ", "#3 "))][:4]})
    return out

def blob(host):
    """BLOB: the dump reply, battleGame: present, its negative unit ids (the stand-ins), the file's first 30 lines"""
    path = os.path.join(host.user_dir, "xcom1", "shared_world")
    if os.path.exists(path):
        os.remove(path)
    rep = q(host, {"cmd": "dump_coop_file", "key": "shared_world"})
    if not os.path.exists(path):
        return {"reply": rep, "error": "no file", "battleGame": None, "head": []}
    with open(path, "rb") as f:
        lines = f.read().decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    has = "battleGame:" in lines
    ids = [int(ln.split(":")[1]) for ln in lines[lines.index("battleGame:"):] if re.match(r"^\s*- id: -\d+\s*$", ln)] if has else []
    return {"reply": rep, "battleGame": has, "stand-in ids": ids, "head": lines[:30]}

def capture(x, n_cl, crash, bl=None):
    out = {"CL": ui(log_lines(x.client, n_cl))[-30:], "host log": [ln.split("\t")[-1] for ln in log_lines(x.host)[-20:]],
           "CRASH": crash, "BLOB head": (bl or {}).get("head")}
    for gc in (x.host, x.client):
        bs = q(gc, {"cmd": "battle_state"})
        out[gc.name] = {"stack": stack(gc), "battle_state": {k: bs.get(k) for k in ("isPreview", "phase", "turn", "error")},
                        "world_state": q(gc, {"cmd": "world_state"}), "shared_resync_stats": q(gc, {"cmd": "shared_resync_stats"})}
    return out

class Row(h20.Row):
    def __init__(self, rid, task0):
        super().__init__(rid, h20.X(None, None))
        self.ev = {"TASK 0": task0}

    def report(self, results):
        self.evidence()
        if self.fails:
            print(f"CAPTURE {self.rid}: {json.dumps(self.cap, sort_keys=True, default=str)}", flush=True)
        results[self.rid] = not self.fails
        print(f"PASS {self.rid}" if not self.fails else f"FAIL {self.rid}: " + " | ".join(self.fails), flush=True)

def pv(gc, keys):
    """PV(gc) -> (ok, {step: probe}); a missed step is recorded as ["MISSED", probe] and ends the drive."""
    ev = {}

    def ok(name, cond, val):
        ev[name] = val if cond else ["MISSED", val]
        return bool(cond)
    if not (ok("P1 geoscape", stack(gc) == [GEO], stack(gc))
            and ok("P2 start", cr.pd_key(gc, keys["ufo"]) and cr.pd_wait_kind(gc, "start")[0], cr.pd_brief(cr.pd(gc)))):
        return False, ev
    time.sleep(SETTLE)
    sec = q(gc, {"cmd": "click_widget", "match": "X-COM CRAFT"})
    cr.pd_wait_kind(gc, "select")
    p = cr.pd(gc)
    if not ok("P3 select", sec.get("ok") and p.get("kind") == "select" and "SKYRANGER" in (p.get("rows") or []),
              [sec.get("text"), p.get("rows")]):
        return False, ev
    rc = cr.pd_row_click(gc, dict(p, section=sec), "SKYRANGER")
    if not ok("P4 article", rc.get("opened") and (rc.get("at") or {}).get("article") == "STR_SKYRANGER", rc.get("at")):
        return False, ev
    k = cr.pd_key(gc, keys["ufo"]) and cr.pd_wait_kind(gc, "nerds")[0]
    btn = [w.get("text") for w in q(gc, {"cmd": "list_widgets"}).get("widgets") or [] if w.get("visible")
           and "TextButton" in str(w.get("type")) and str(w.get("text")).startswith("Preview")]
    if not ok("P5 nerds", k and len(btn) == 1, [cr.pd_brief(cr.pd(gc)), btn]):
        return False, ev
    time.sleep(SETTLE)
    c = q(gc, {"cmd": "click_widget", "match": "preview"})
    if not ok("P6 briefing", c.get("ok") and wait_until(lambda: on_top(gc, BRF), STEP, 0.05), stack(gc)):
        return False, ev
    cb, dis = q(gc, {"cmd": "close_briefing"}), 0
    while not wait_until(lambda: on_top(gc, BS), STEP, 0.05) and dis < 3:
        dis += 1
        q(gc, {"cmd": "dismiss_popup"})
    pre, hb = q(gc, {"cmd": "battle_state"}).get("isPreview"), q(gc, {"cmd": "world_state"}).get("has_battle")
    return ok("P7 preview", cb.get("ok") and on_top(gc, BS) and pre is True and hb is True, [stack(gc), pre, hb, dis]), ev

def end_preview(gc, keys):
    """END(gc) -> (ok, record); dismiss_popup only for a top other than BattlescapeState / StatsForNerdsState"""
    time.sleep(SETTLE)
    b, dis = q(gc, {"cmd": "battle_action", "action": "end_turn_button"}), 0
    done = lambda: on_top(gc, SFN) and q(gc, {"cmd": "world_state"}).get("has_battle") is False  # noqa: E731
    while not wait_until(done, STEP, 0.05) and dis < 3:
        dis += 1
        if not (on_top(gc, BS) or on_top(gc, SFN)):
            q(gc, {"cmd": "dismiss_popup"})
    nerds = done()
    pc = cr.pd_close(gc, keys) if nerds else None
    st = stack(gc)
    return bool(b.get("ok") and nerds and st == [GEO]), {"reply": b.get("ok"), "nerds": nerds, "close": pc and pc["steps"], "stack": st}

def client_cells(r, x, t1, n_cl, before, seq, red, bl=None):
    """poll W s (death, or [GeoscapeState] held HOLD s after the LoadGameState ran); the client's cells; False = it died"""
    reached, tl, dead, geo_ms = None, [], None, None
    while True:
        now = time.time()
        s = stack(x.client) if alive(x.client) else ["<dead>"]
        if not tl or tl[-1][1] != s:
            tl.append((round((now - t1) * 1000), s))
        if s == ["<dead>"]:
            dead = tl[-1][0]
            time.sleep(0.5)  # the crash handler's files
            break
        reached = (reached or now) if s == [GEO] and in_order(log_lines(x.client, n_cl), CL_1[:2]) else None
        if reached and now - reached >= HOLD:
            geo_ms = round((reached - t1) * 1000)
            break
        if now - t1 >= W:
            break
        time.sleep(POLL)
    cl, crash = log_lines(x.client, n_cl), crash_info(before)
    r.ev.update({"client timeline": tl, "CL": ui(cl), "CRASH": crash, "died ms": dead, "geoscape ms": geo_ms})
    hb = None if dead else q(x.client, {"cmd": "world_state"}).get("has_battle")
    r.cell(f"{red}within {W:.0f} s the client stack == [{GEO}], has_battle false, alive {HOLD:.0f} s more, no CRASH",
           not dead and geo_ms is not None and hb is False and not crash,
           {"died ms": dead, "timeline": tl[-4:], "has_battle": hb, "CRASH": crash})
    if dead:
        r.ev["not reached (the client died)"] = "CL order, END(host), js.finish" if seq is CL_1 else "CL order, host cells"
        r.cap.update(capture(x, n_cl, crash, bl))
        return False
    return r.cell("CL in order " + " -> ".join(s.split("OpenXcom::")[-1] for s in seq), in_order(cl, seq), ui(cl)[-14:])

def row(r, x, js, mode):
    """mode G: the client's preview + the client's force_resync; 1: the host's preview + the HOST's; 2: the host's + the client's"""
    pg, trig = (x.client, x.client) if mode == "G" else (x.host, x.host if mode == "1" else x.client)
    ok, r.ev[f"PV({pg.name})"] = pv(pg, x.keys[pg.name])
    if not r.cell(f"G: PV({pg.name}) reached the preview", ok, r.ev[f"PV({pg.name})"]):
        return r.cap.update(capture(x, 0, []))
    req0 = q(x.host, {"cmd": "shared_resync_stats"}).get("requests") or 0
    n_cl, before, t1 = log_size(x.client), crash_names(), time.time()
    r.ev["force_resync"] = rep = q(trig, {"cmd": "force_resync"})
    want = {"role": "host", "ok": True} if trig is x.host else {"role": "replica", "sent": True}
    if not r.cell(f"{trig.name} force_resync -> {want}", all(rep.get(a) == b for a, b in want.items()), rep):
        return r.cap.update(capture(x, n_cl, []))
    if mode == "G":
        if client_cells(r, x, t1, n_cl, before, CL_G, ""):
            r.cell("the host alive and on [GeoscapeState]", alive(x.host) and stack(x.host) == [GEO], stack(x.host))
        if r.fails and not r.cap:
            r.cap.update(capture(x, n_cl, r.ev.get("CRASH")))
        return
    reqs = lambda: q(x.host, {"cmd": "shared_resync_stats"}).get("requests") or 0  # noqa: E731
    served = wait_until(lambda: reqs() >= req0 + 1, W, 0.05) if mode == "2" else True
    h = r.ev["host after the reply"] = {"alive": alive(x.host), "stack": stack(x.host), "requests": [req0, reqs()],
                                        "isPreview": q(x.host, {"cmd": "battle_state"}).get("isPreview")}
    what = "the host served it during its preview (requests +1, alive" if mode == "2" else "the host right after the reply (alive"
    r.cell(f"{what}, {BS} on its stack, isPreview true)", served and h["alive"] and BS in h["stack"] and h["isPreview"] is True, h)
    bl = blob(x.host)
    r.ev["BLOB"] = {k: v for k, v in bl.items() if k != "head"}
    r.cell("RED 1: BLOB noBattle (the host's copy carries no preview battle)", bl["reply"].get("ok") and bl["battleGame"] is False,
           r.ev["BLOB"])
    if not client_cells(r, x, t1, n_cl, before, CL_1, "RED 2: ", bl):
        return
    ok, r.ev["END(host)"] = end_preview(x.host, x.keys["host"])
    r.cell("END(host) -> [GeoscapeState], has_battle false", ok and q(x.host, {"cmd": "world_state"}).get("has_battle") is False,
           r.ev["END(host)"])
    try:
        js.finish()
    except AssertionError as e:
        r.cell("js.finish (both worlds equal, the replica's zero disk)", False, short(e, 1500))
    if r.fails and not r.cap:
        r.cap.update(capture(x, n_cl, r.ev.get("CRASH"), bl))

def boot(tag, ports, rows):
    """bring_up + the setup guard -> (js, x), or (None, None) with every row failed `boot` (one CAPTURE each)"""
    js = x = None
    try:
        js = shared_fixture.bring_up(tag, ports)
        x = h20.X(js.host, js.client, js)
        x.keys = {gc.name: {"ufo": cr.read_key(gc.user_dir, "keyGeoUfopedia"), "cancel": cr.read_key(gc.user_dir, "keyCancel")}
                  for gc in (x.host, x.client)}
        su = {gc.name: [stack(gc), q(gc, {"cmd": "get_coop"}).get("localSeat"), q(gc, {"cmd": "world_state"}).get("has_battle")]
              for gc in (x.host, x.client)}
        for r in rows:
            r.ev["setup " + tag] = dict(su, keys=x.keys)
        assert su == {"host": [[GEO], 0, False], "client": [[GEO], 1, False]}, f"setup guard: {su}"
        return js, x
    except Exception as e:
        for r in rows:
            r.cap["boot " + tag] = dict(capture(x, 0, []) if x is not None else {}, error=short(e, 1500))
            r.cell(f"boot {tag}", False, short(e, 300))
        if js is not None:
            shut(js, rows[0], tag, False)
        return None, None

def shut(js, r, tag, died):
    """a dead client's crash rc is tolerated (its CRASH is the evidence); anything else fails `<tag> shutdown`"""
    try:
        js.shutdown()
    except Exception as e:
        if died and "host:" not in short(e):
            r.ev["shutdown, dead client (tolerated)"] = short(e, 300)
        else:
            r.cell(f"{tag} shutdown", False, short(e, 300))

def run_boot(tag, ports, rows, modes, results, walls):
    t0 = time.time()
    js, x = boot(tag, ports, rows)
    for r, mode in zip(rows, modes):
        t = time.time()
        try:
            if js is not None and not alive(x.client):
                r.cell("G: the boot's client is alive before the row", False, "dead")
            elif js is not None:
                row(r, x, js, mode)
        except Exception as e:
            r.cell(f"G: {r.rid} exception", False, short(e))
        walls[r.rid] = r.ev["wall s"] = round(time.time() - t, 1)
    if js is not None:
        shut(js, rows[-1], tag, not alive(x.client))
    walls[tag] = round(time.time() - t0, 1)
    for r in rows:
        r.report(results)

def main():
    t0, results, walls = time.time(), {}, {}
    red = "named red: 3/3 client crashes (Soldier::getName <- BattleUnit::BattleUnit <- SavedBattleGame::load), BLOB ids -1..-14"
    run_boot("w2h21pva", PORTS_A, [Row("H21c-G", "guard: 0/3 deaths"), Row("H21c-1", red)], ["G", "1"], results, walls)
    run_boot("w2h21pvb", PORTS_B, [Row("H21c-2", red)], ["2"], results, walls)
    failed = [rid for rid in ("H21c-G", "H21c-1", "H21c-2") if not results.get(rid)]
    print(f"\ntest_w2_preview_restream: {3 - len(failed)}/3 passed (fail={failed}) walls {json.dumps(walls)} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
