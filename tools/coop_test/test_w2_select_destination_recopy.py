"""W2-H21b (QH21-3 a, F8671; spec rewrite/prompts/w2h21b_select_destination_recopy.md (f) as ruled by R-H21b-T0-1; TASK 0
rewrite/w2h21b-task0/CONSTANTS.md): a world re-copy, or a teardown to the main menu, pops the second player's open craft
destination picker together with its GeoscapeState; Game::run frees the geoscape's globe first and the picker's destructor then
writes 25 bytes into it (T0-I: `~Globe this=G` before `write globe=G`, rows 1 and 3). Silent, so every row is a GUARD (TASK 0,
unchanged product: rows C, 1, 2, 3 each 0/3 client deaths); the red evidence is T0-I, the green G-I. open = the client's
TEST-ONLY open_select_destination {SKY, STR_SKYRANGER}: ok, depth 2, stack [GeoscapeState, SelectDestinationState], CL push.
Boot A bring_up("w2h21dsa", (49494, 49495, 47946)), rows C, 1, 2; Boot B bring_up("w2h21dsb", (49496, 49497, 47947)), row 3.
  H21b-C open; the client's click_widget CANCEL (text CANCEL); CL pop SelectDestinationState, no GeoscapeState pop after it.
  H21b-1 open; the client's force_resync (role replica, sent true); CL in order: push / pop LoadGameState, pop
         SelectDestinationState directly followed by pop GeoscapeState, push GeoscapeState; alive(host).
  H21b-2 open; the HOST's force_resync (role host); the H21b-1 cells, then js.finish() (both worlds equal, zero disk).
  C, 1, 2: within W the client stack == [GeoscapeState], alive(client) HOLD s more, no CRASH.
  H21b-3 open; js.host.kill(); within 30 s (0.5 s polls) the client's coop_dialog_info code 21, backVisible true; the stack
         before the OK == [GoToMainMenuState, CoopState] (R-H21b-T0-1: the teardown pops the picker and its geoscape at the
         drop); coop_dialog_back code 21; within 15 s [MainMenuState], alive HOLD s more; world_state.has_save false; CL in
         order: pop SelectDestinationState directly followed by pop GeoscapeState, push GoToMainMenuState, push / pop
         CoopState, push MainMenuState; no CRASH; the client's shutdown clean (rc 0).
W = 10 s at 0.25 s polls, HOLD = 2 s; alive = the process runs and `ping` answers; CL = the client's openxcom.log after the size
noted before the row's open; CRASH = new crashlogs/crash_*.log (first 4 frames). Setup guard per boot: both stacks
[GeoscapeState] and SKY found, else the boot's rows fail `boot` (ONE CAPTURE line); a client death fails its row and the boot's
later rows `boot`. EVIDENCE before each verdict; a failed row prints ONE CAPTURE line; every row runs after a failure; ONE run
(WV-D95); exit 0 iff every row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import shared_fixture  # noqa: E402
import test_w2_shared_base_equip as h20  # noqa: E402  (main-guarded)

PORTS_A, PORTS_B = (49494, 49495, 47946), (49496, 49497, 47947)
W, POLL, HOLD, W3, POLL3, W3OK = 10.0, 0.25, 2.0, 30.0, 0.5, 15.0
HB, GEO, SDS, MM, GTM, CS = "HostBase", "GeoscapeState", "SelectDestinationState", "MainMenuState", "GoToMainMenuState", "CoopState"
PUSH, POP = "push class OpenXcom::", "pop  class OpenXcom::"
RECOPY = [(PUSH + "LoadGameState", 0), (POP + "LoadGameState", 0), (POP + SDS, 0), (POP + GEO, 1), (PUSH + GEO, 0)]
TEARDOWN = [(POP + SDS, 0), (POP + GEO, 1), (PUSH + GTM, 0), (PUSH + CS, 0), (POP + CS, 0), (PUSH + MM, 0)]
TRIG = {"H21b-C": ("client", {"cmd": "click_widget", "match": "CANCEL"}, {"ok": True, "text": "CANCEL"}),
        "H21b-1": ("client", {"cmd": "force_resync"}, {"ok": True, "role": "replica", "sent": True}),
        "H21b-2": ("host", {"cmd": "force_resync"}, {"ok": True, "role": "host"})}
ROWS_A, ORDER = ["H21b-C", "H21b-1", "H21b-2"], ["H21b-C", "H21b-1", "H21b-2", "H21b-3"]
CRASH_DIR = harness.CRASH_DIR  # (W2-U8h F9563: this lane's own crash folder)
q, stack, short, wait_until = h20.q, h20.stack, h20.short, h20.wait_until

def alive(gc):
    return gc.proc is not None and gc.proc.poll() is None and bool(q(gc, {"cmd": "ping"}).get("pong"))

def log_size(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return os.path.getsize(p) if os.path.isfile(p) else 0

def log_lines(gc, n0=0):
    p = os.path.join(gc.user_dir, "openxcom.log")
    if not os.path.isfile(p):
        return []
    with open(p, "rb") as f:
        f.seek(n0)
        return [ln.rstrip("\r") for ln in f.read().decode("utf-8", errors="replace").split("\n") if ln.strip()]

def ui(lines, keys=("[coop-ui]", "[SHARED]")):
    """the screen record (and the SHARED lines), message part only"""
    return [ln.split("\t")[-1] for ln in lines if any(k in ln for k in keys)]

def crash_names():
    return set(os.listdir(CRASH_DIR)) if os.path.isdir(CRASH_DIR) else set()

def crash_info(before):
    """CRASH: every crash log written since `before`, with its first 4 frames"""
    out = []
    for name in sorted(n for n in crash_names() - before if n.endswith(".log")):
        with open(os.path.join(CRASH_DIR, name), encoding="utf-8", errors="replace") as f:
            fr = [ln.strip()[:150] for ln in f if ln.lstrip().startswith(("#0 ", "#1 ", "#2 ", "#3 "))]
        out.append({"file": name, "frames": fr[:4]})
    return out

def in_order(scr, steps):
    """steps [(text, direct)]: each text on a screen-record line after the previous match; direct = on the very next line"""
    i = -1
    for text, direct in steps:
        rng = range(i + 1, min(i + 2, len(scr))) if direct else range(i + 1, len(scr))
        i = next((k for k in rng if text in scr[k]), None)
        if i is None:
            return False
    return True

def ms(t, t1):
    return None if t is None else round((t - t1) * 1000)

def capture(js, n_cl, crash):
    """both machines' stacks and shared_resync_stats, CL after n_cl, the host log's last 20 lines, CRASH"""
    return {"stacks": {gc.name: stack(gc) for gc in (js.host, js.client)},
            "shared_resync_stats": {gc.name: q(gc, {"cmd": "shared_resync_stats"}) for gc in (js.host, js.client)},
            "CL": ui(log_lines(js.client, n_cl))[-30:], "host log": log_lines(js.host)[-20:], "CRASH": crash}

class Row:
    def __init__(self, rid, tag):
        self.rid, self.fails, self.cap, self.ev, self.t0 = rid, [], None, {"boot": tag}, time.time()

    def cell(self, name, ok, detail=""):
        if not ok:
            self.fails.append(f"{name}: {detail}")
        return bool(ok)

    def report(self, results, walls):
        walls[self.rid] = self.ev["wall s"] = round(time.time() - self.t0, 1)
        print(f"EVIDENCE {self.rid}: {json.dumps(self.ev, sort_keys=True, default=str)}", flush=True)
        if self.fails:
            print(f"CAPTURE {self.rid}: {json.dumps(self.cap, sort_keys=True, default=str)}", flush=True)
        results[self.rid] = not self.fails
        print(f"PASS {self.rid}" if not self.fails else f"FAIL {self.rid}: " + " | ".join(self.fails), flush=True)

def end(js, died=False):
    """shut the boot down -> None, or the error; a dead client's own shutdown error is tolerated (its CRASH is the evidence)"""
    try:
        js.shutdown()
    except Exception as e:
        return None if died and "host:" not in str(e) else short(e, 300)

def boot(tag, ports, rids, results):
    """bring_up + the setup guard -> (js, SKY); a miss fails the boot's rows `boot` with ONE CAPTURE line -> (None, None)"""
    js = None
    try:
        js = shared_fixture.bring_up(tag, ports)
        crafts = q(js.client, {"cmd": "base_report", "base": HB}).get("crafts") or []
        sky = next((c.get("id") for c in crafts if c.get("type") == "STR_SKYRANGER"), None)
        st = {gc.name: stack(gc) for gc in (js.host, js.client)}
        if not (st == {"host": [GEO], "client": [GEO]} and sky is not None):
            raise RuntimeError(f"setup guard: stacks {st}, the client's HostBase crafts {crafts}")
        return js, sky
    except Exception as e:
        cap = dict(capture(js, 0, []) if js is not None else {}, error=short(e, 1500))
        print(f"CAPTURE boot {tag} (boot miss): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
        for rid in rids:
            results[rid] = False
            print(f"EVIDENCE {rid}: {json.dumps({'boot': tag, 'miss': short(e, 300)})}\nFAIL {rid}: boot", flush=True)
        if js is not None:
            end(js)
        return None, None

def open_picker(r, js, sky):
    """open(r) -> (ok, n_cl, crash names before)"""
    c = js.client
    r.ev["SKY"], n_cl, before = sky, log_size(c), crash_names()
    r.ev["open"] = rep = q(c, {"cmd": "open_select_destination", "craft_id": sky, "craft_type": "STR_SKYRANGER"})
    shown = wait_until(lambda: stack(c) == [GEO, SDS], W)
    r.ev["stack open"], scr = stack(c), ui(log_lines(c, n_cl), ("[coop-ui]",))
    ok = r.cell("G: open_select_destination ok, depth 2", rep.get("ok") is True and rep.get("depth") == 2, rep)
    ok = r.cell(f"G: the client stack == [{GEO}, {SDS}] within {W:.0f} s", shown, r.ev["stack open"]) and ok
    return r.cell(f"G: CL {PUSH + SDS}", any(PUSH + SDS in x for x in scr), scr) and ok, n_cl, before

def settle(r, c, t1, want, limit, what):
    """poll the client (POLL s) until it dies, holds the stack `want` HOLD s, or `limit` s pass without it; record the outcome
    cells and evidence -> (died, CRASH, the screen record)"""
    dead = reached = None
    while True:
        now = time.time()
        if not alive(c):
            dead = now
            time.sleep(0.5)  # the crash handler's files
            break
        if reached is None and stack(c) == want:
            reached = now
        if (reached and now - reached >= HOLD) or (not reached and now - t1 >= limit):
            break
        time.sleep(POLL)
    cl, crash = log_lines(c, r.n_cl), crash_info(r.before)
    r.ev.update({"ms to death": ms(dead, t1), "ms to settle": ms(reached, t1), "CL": ui(cl), "CRASH": crash})
    r.cell(f"the client died when {what} under its open destination picker (F8671)", dead is None, ms(dead, t1))
    if dead is None:
        r.ev["client stack after"] = st = stack(c)
        r.cell(f"the client stack == {want} within {limit:.0f} s", reached is not None and st == want, st)
    return dead is not None, crash, ui(cl, ("[coop-ui]",))

def row_a(rid, js, sky):
    """one Boot A row on the live boot -> (Row, the client died)"""
    r, h, c = Row(rid, js.tag), js.host, js.client
    r.n_cl, crash, died = 0, [], False
    try:
        ok, r.n_cl, r.before = open_picker(r, js, sky)
        if ok:
            t1 = time.time()
            who, req, want = TRIG[rid]
            r.ev["trigger"] = trig = q(h if who == "host" else c, req)
            if r.cell(f"non-vacuity: the {who}'s {req['cmd']} reply {want}", all(trig.get(k) == v for k, v in want.items()), trig):
                died, crash, scr = settle(r, c, t1, [GEO], W, "Cancel was pressed" if rid == "H21b-C" else "a world re-copy landed")
                if rid == "H21b-C":
                    i = next((k for k, x in enumerate(scr) if POP + SDS in x), len(scr))
                    r.cell(f"CL {POP + SDS}, no {POP + GEO} after it", i < len(scr) and not any(POP + GEO in x for x in scr[i:]), scr)
                else:
                    r.cell("CL in order: " + ", ".join(t + (" (directly)" if d else "") for t, d in RECOPY), in_order(scr, RECOPY), scr)
                    r.cell("the host is alive", alive(h), h.proc.poll() if h.proc else None)
                r.cell("no CRASH", not crash, crash)
                if rid == "H21b-2" and not died:
                    try:
                        js.finish()
                    except AssertionError as e:
                        r.cell("js.finish (both worlds equal, the replica's zero disk)", False, short(e, 1500))
    except Exception as e:
        r.cell(f"G: {rid} exception", False, short(e))
    if r.fails:
        r.cap = capture(js, r.n_cl, crash)
        if not died and stack(c) != [GEO]:  # a stopped row leaves no screen behind for the next one
            r.cap["client cleanup"] = {"close_screens": q(c, {"cmd": "close_screens"}),
                                       "after": wait_until(lambda: stack(c) == [GEO], 5.0) and stack(c)}
    return r, died

def boot_a(results, walls):
    js, sky = boot("w2h21dsa", PORTS_A, ROWS_A, results)
    if js is None:
        return
    died, rows = None, []
    for rid in ROWS_A:
        if died:
            r = Row(rid, js.tag)
            r.cell("boot", False, f"the client died on {died} (no fresh boot inside the file)")
            r.cap = {"skipped": rid}
        else:
            r, d = row_a(rid, js, sky)
            died = rid if d else None
        rows.append(r)
        if rid != ROWS_A[-1]:
            r.report(results, walls)
    err = end(js, died=bool(died))
    if err:
        rows[-1].cell("Boot A shutdown", False, err)
        rows[-1].cap = rows[-1].cap or {"shutdown": err}
    rows[-1].report(results, walls)

def row_3(results, walls):
    js, sky = boot("w2h21dsb", PORTS_B, ["H21b-3"], results)
    if js is None:
        return
    r, h, c = Row("H21b-3", js.tag), js.host, js.client
    r.n_cl, crash, died = 0, [], False
    try:
        ok, r.n_cl, r.before = open_picker(r, js, sky)
        if ok:
            t1 = time.time()
            h.kill()  # reaps the host with rc 1; js.shutdown() then quits only the client
            r.ev["host kill rc"] = h.proc.poll()
            info = wait_until(lambda: (lambda d: d if d.get("code") == 21 else None)(q(c, {"cmd": "coop_dialog_info"})), W3, POLL3)
            r.ev["ms to code 21"], r.ev["coop_dialog_info"] = ms(time.time(), t1), info or q(c, {"cmd": "coop_dialog_info"})
            r.ev["stack before OK"] = st = stack(c)
            ok = r.cell(f"non-vacuity: the client's coop_dialog_info code 21 within {W3:.0f} s, backVisible true",
                        bool(info) and info.get("backVisible") is True, r.ev["coop_dialog_info"])
            r.cell(f"the client stack before the OK == [{GTM}, {CS}] (R-H21b-T0-1)", st == [GTM, CS], st)
        if ok:
            t2 = time.time()
            r.ev["coop_dialog_back"] = back = q(c, {"cmd": "coop_dialog_back"})
            r.cell("coop_dialog_back code 21", back.get("code") == 21, back)
            died, crash, scr = settle(r, c, t2, [MM], W3OK, "the host left")
            if not died:
                r.ev["world_state"] = ws = q(c, {"cmd": "world_state"})
                r.cell("world_state.has_save false", ws.get("has_save") is False, ws)
            r.cell("CL in order: " + ", ".join(t + (" (directly)" if d else "") for t, d in TEARDOWN), in_order(scr, TEARDOWN), scr)
            r.cell("no CRASH", not crash, crash)
    except Exception as e:
        r.cell("G: H21b-3 exception", False, short(e))
    if r.fails:
        r.cap = capture(js, r.n_cl, crash)
    err = end(js)
    r.ev["client rc"] = c.proc.poll() if c.proc else None
    r.cell("the client's shutdown clean (rc 0)", not err and r.ev["client rc"] == 0, err or r.ev["client rc"])
    r.cap = r.cap or ({"shutdown": err} if r.fails else None)
    r.report(results, walls)

def main():
    t0, results, walls = time.time(), {}, {}
    boot_a(results, walls)
    row_3(results, walls)
    failed = [rid for rid in ORDER if not results.get(rid)]
    print(f"\ntest_w2_select_destination_recopy: {len(ORDER) - len(failed)}/{len(ORDER)} passed (fail={failed}) "
          f"walls {json.dumps(walls)} in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
