"""A world re-copy, or a teardown to the main menu, pops the second player's open craft destination picker together with
its GeoscapeState. Without the fix Game::run frees the geoscape's globe first and the picker's destructor then writes 25
bytes into it (instrumented runs showed `~Globe this=G` before `write globe=G` in client_resync_recopy and
host_drop_teardown). The write is silent (no client death in 3 runs of any row without the fix), so every row is a
GUARD. open = the client's test-only open_select_destination {SKY, STR_SKYRANGER}: ok, depth 2, stack
[GeoscapeState, SelectDestinationState], CL push.
The recopy boot bring_up("picker_recopy", (49494, 49495, 47946)) runs picker_cancel, client_resync_recopy and
host_resync_recopy; the teardown boot bring_up("picker_teardown", (49496, 49497, 47947)) runs host_drop_teardown.
  picker_cancel  open; the client's click_widget CANCEL (text CANCEL); CL pop SelectDestinationState, no GeoscapeState
         pop after it.
  client_resync_recopy  open; the client's force_resync (role replica, sent true); CL in order: push / pop
         LoadGameState, pop SelectDestinationState directly followed by pop GeoscapeState, push GeoscapeState;
         alive(host).
  host_resync_recopy  open; the HOST's force_resync (role host); the client_resync_recopy cells, then js.finish() (both
         worlds equal, zero disk).
  The three recopy-boot rows: within W the client stack == [GeoscapeState], alive(client) HOLD s more, no CRASH.
  host_drop_teardown  open; js.host.kill(); within 30 s (0.5 s polls) the client's coop_dialog_info code 21,
         backVisible true; the stack before the OK == [GoToMainMenuState, CoopState] (the teardown pops the picker and
         its geoscape at the drop); coop_dialog_back code 21; within 15 s [MainMenuState], alive HOLD s more;
         world_state.has_save false; CL in order: pop SelectDestinationState directly followed by pop GeoscapeState,
         push GoToMainMenuState, push / pop CoopState, push MainMenuState; no CRASH; the client's shutdown clean (rc 0).
W = 10 s at 0.25 s polls, HOLD = 2 s; alive = the process runs and `ping` answers; CL = the client's openxcom.log after the size
noted before the row's open; CRASH = new crashlogs/crash_*.log (first 4 frames). Setup guard per boot: both stacks
[GeoscapeState] and SKY found, else the boot's rows fail `boot` (ONE CAPTURE line); a client death fails its row and the boot's
later rows `boot`. EVIDENCE before each verdict; a failed row prints ONE CAPTURE line; every row runs after a failure; ONE run;
exit 0 iff every row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import shared_fixture  # noqa: E402
import test_shared_base_equip as sbe  # noqa: E402  (main-guarded)

PORTS_RECOPY, PORTS_TEARDOWN = (49494, 49495, 47946), (49496, 49497, 47947)
W, POLL, HOLD, W_DROP, POLL_DROP, W_DROP_OK = 10.0, 0.25, 2.0, 30.0, 0.5, 15.0
HB, GEO, SDS, MM, GTM, CS = "HostBase", "GeoscapeState", "SelectDestinationState", "MainMenuState", "GoToMainMenuState", "CoopState"
PUSH, POP = "push class OpenXcom::", "pop  class OpenXcom::"
RECOPY = [(PUSH + "LoadGameState", 0), (POP + "LoadGameState", 0), (POP + SDS, 0), (POP + GEO, 1), (PUSH + GEO, 0)]
TEARDOWN = [(POP + SDS, 0), (POP + GEO, 1), (PUSH + GTM, 0), (PUSH + CS, 0), (POP + CS, 0), (PUSH + MM, 0)]
TRIG = {"picker_cancel": ("client", {"cmd": "click_widget", "match": "CANCEL"}, {"ok": True, "text": "CANCEL"}),
        "client_resync_recopy": ("client", {"cmd": "force_resync"}, {"ok": True, "role": "replica", "sent": True}),
        "host_resync_recopy": ("host", {"cmd": "force_resync"}, {"ok": True, "role": "host"})}
ROWS_RECOPY, ORDER = (["picker_cancel", "client_resync_recopy", "host_resync_recopy"],
                      ["picker_cancel", "client_resync_recopy", "host_resync_recopy", "host_drop_teardown"])
CRASH_DIR = harness.CRASH_DIR  # this harness slot's own crash folder
q, stack, short, wait_until = sbe.q, sbe.stack, sbe.short, sbe.wait_until

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
    ok = r.cell("guard: open_select_destination ok, depth 2", rep.get("ok") is True and rep.get("depth") == 2, rep)
    ok = r.cell(f"guard: the client stack == [{GEO}, {SDS}] within {W:.0f} s", shown, r.ev["stack open"]) and ok
    return r.cell(f"guard: CL {PUSH + SDS}", any(PUSH + SDS in x for x in scr), scr) and ok, n_cl, before

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
    r.cell(f"the client died when {what} under its open destination picker", dead is None, ms(dead, t1))
    if dead is None:
        r.ev["client stack after"] = st = stack(c)
        r.cell(f"the client stack == {want} within {limit:.0f} s", reached is not None and st == want, st)
    return dead is not None, crash, ui(cl, ("[coop-ui]",))

def recopy_row(rid, js, sky):
    """one recopy boot row on the live boot -> (Row, the client died)"""
    r, h, c = Row(rid, js.tag), js.host, js.client
    r.n_cl, crash, died = 0, [], False
    try:
        ok, r.n_cl, r.before = open_picker(r, js, sky)
        if ok:
            t1 = time.time()
            who, req, want = TRIG[rid]
            r.ev["trigger"] = trig = q(h if who == "host" else c, req)
            if r.cell(f"non-vacuity: the {who}'s {req['cmd']} reply {want}", all(trig.get(k) == v for k, v in want.items()), trig):
                died, crash, scr = settle(r, c, t1, [GEO], W, "Cancel was pressed" if rid == "picker_cancel"
                                          else "a world re-copy landed")
                if rid == "picker_cancel":
                    i = next((k for k, x in enumerate(scr) if POP + SDS in x), len(scr))
                    r.cell(f"CL {POP + SDS}, no {POP + GEO} after it", i < len(scr) and not any(POP + GEO in x for x in scr[i:]), scr)
                else:
                    r.cell("CL in order: " + ", ".join(t + (" (directly)" if d else "") for t, d in RECOPY), in_order(scr, RECOPY), scr)
                    r.cell("the host is alive", alive(h), h.proc.poll() if h.proc else None)
                r.cell("no CRASH", not crash, crash)
                if rid == "host_resync_recopy" and not died:
                    try:
                        js.finish()
                    except AssertionError as e:
                        r.cell("js.finish (both worlds equal, the replica's zero disk)", False, short(e, 1500))
    except Exception as e:
        r.cell(f"guard: {rid} exception", False, short(e))
    if r.fails:
        r.cap = capture(js, r.n_cl, crash)
        if not died and stack(c) != [GEO]:  # a stopped row leaves no screen behind for the next one
            r.cap["client cleanup"] = {"close_screens": q(c, {"cmd": "close_screens"}),
                                       "after": wait_until(lambda: stack(c) == [GEO], 5.0) and stack(c)}
    return r, died

def boot_recopy_rows(results, walls):
    js, sky = boot("picker_recopy", PORTS_RECOPY, ROWS_RECOPY, results)
    if js is None:
        return
    died, rows = None, []
    for rid in ROWS_RECOPY:
        if died:
            r = Row(rid, js.tag)
            r.cell("boot", False, f"the client died on {died} (no fresh boot inside the file)")
            r.cap = {"skipped": rid}
        else:
            r, d = recopy_row(rid, js, sky)
            died = rid if d else None
        rows.append(r)
        if rid != ROWS_RECOPY[-1]:
            r.report(results, walls)
    err = end(js, died=bool(died))
    if err:
        rows[-1].cell("recopy boot shutdown", False, err)
        rows[-1].cap = rows[-1].cap or {"shutdown": err}
    rows[-1].report(results, walls)

def row_host_drop(results, walls):
    js, sky = boot("picker_teardown", PORTS_TEARDOWN, ["host_drop_teardown"], results)
    if js is None:
        return
    r, h, c = Row("host_drop_teardown", js.tag), js.host, js.client
    r.n_cl, crash, died = 0, [], False
    try:
        ok, r.n_cl, r.before = open_picker(r, js, sky)
        if ok:
            t1 = time.time()
            h.kill()  # reaps the host with rc 1; js.shutdown() then quits only the client
            r.ev["host kill rc"] = h.proc.poll()
            info = wait_until(lambda: (lambda d: d if d.get("code") == 21 else None)(q(c, {"cmd": "coop_dialog_info"})),
                              W_DROP, POLL_DROP)
            r.ev["ms to code 21"], r.ev["coop_dialog_info"] = ms(time.time(), t1), info or q(c, {"cmd": "coop_dialog_info"})
            r.ev["stack before OK"] = st = stack(c)
            ok = r.cell(f"non-vacuity: the client's coop_dialog_info code 21 within {W_DROP:.0f} s, backVisible true",
                        bool(info) and info.get("backVisible") is True, r.ev["coop_dialog_info"])
            r.cell(f"the client stack before the OK == [{GTM}, {CS}]", st == [GTM, CS], st)
        if ok:
            t2 = time.time()
            r.ev["coop_dialog_back"] = back = q(c, {"cmd": "coop_dialog_back"})
            r.cell("coop_dialog_back code 21", back.get("code") == 21, back)
            died, crash, scr = settle(r, c, t2, [MM], W_DROP_OK, "the host left")
            if not died:
                r.ev["world_state"] = ws = q(c, {"cmd": "world_state"})
                r.cell("world_state.has_save false", ws.get("has_save") is False, ws)
            r.cell("CL in order: " + ", ".join(t + (" (directly)" if d else "") for t, d in TEARDOWN), in_order(scr, TEARDOWN), scr)
            r.cell("no CRASH", not crash, crash)
    except Exception as e:
        r.cell("guard: host_drop_teardown exception", False, short(e))
    if r.fails:
        r.cap = capture(js, r.n_cl, crash)
    err = end(js)
    r.ev["client rc"] = c.proc.poll() if c.proc else None
    r.cell("the client's shutdown clean (rc 0)", not err and r.ev["client rc"] == 0, err or r.ev["client rc"])
    r.cap = r.cap or ({"shutdown": err} if r.fails else None)
    r.report(results, walls)

def main():
    t0, results, walls = time.time(), {}, {}
    boot_recopy_rows(results, walls)
    row_host_drop(results, walls)
    failed = [rid for rid in ORDER if not results.get(rid)]
    print(f"\ntest_select_destination_recopy: {len(ORDER) - len(failed)}/{len(ORDER)} passed (fail={failed}) "
          f"walls {json.dumps(walls)} in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
