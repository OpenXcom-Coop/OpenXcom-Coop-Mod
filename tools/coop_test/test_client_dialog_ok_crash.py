"""W2-H56 S-A - test_client_dialog_ok_crash.py (L-H54-1, R-H56-0; capture lh54-1-cap F18240-F18250; docs
rewrite/prompts/w2h56_client_dialog_ok_crash.md (f); TASK 0 rewrite/w2h56-task0/sa/CONSTANTS.md). The second player of a co-op
campaign presses OPTIONS > CO-OP > DISCONNECT: its teardown sets GoToMainMenuState, but the lobby pushes the server browser over it
and the world stays loaded (the trap). A Direct Connect from there that fails (16 "Cannot connect") or reaches a NEW BATTLE host
(3000 "New Battle") builds a dialog whose constructor runs disconnectTCP() (stack = GoToMainMenuState) and then popState(): the
dialog is the only state, its OK pops the last state and Game::run reads the empty stack (Game.cpp :444, exit 3, a crash log).
Rows, one fresh boot each (keys "49182" the campaign / "49186" the NEW BATTLE key and the refused port; dirs w2h56_<row>_*):
  R-A trap -> Direct Connect to the refused port -> 16 alone -> OK: A-pre, A-alive, A-nocrash, A-menu, A-host (the host's 62).
  R-B trap; the host ABANDONs its 62 (real click), hosts a NEW BATTLE (levers) -> Direct Connect to it -> 3000 alone -> OK:
      B-pre, B-alive, B-nocrash, B-menu, B-host (the host's 20). R-C the control, LAST: no world (NEW BATTLE > COOP) -> the
      refused port -> 16 over the browser -> OK: C-pre, C-list. RED: the -alive / -nocrash / -menu cells of A and B; the rest GUARD.
Every press is a REAL click (click_widget) once list_widgets reads the button visible true, hidden false on the named top state; the
port is typed with real keys (inject_input), RETURN before JOIN (F18249). Never coop_dialog_back, dismiss_popup, lobby_disconnect or
join_tcp (W2-U7c / W2-U7d). One EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; a precondition miss ends its
row (cells "not reached"); a boot miss fails the row "boot" with ONE CAPTURE line. WV-D95 / WV-D99 / WV-D100: ONE foreground run, no
skip path, every row runs after a failure; exit 0 only when every cell passes, else 2. Run: python tools/coop_test/<this file>"""

import json, os, socket, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402

KEY = "49182"
KEY2 = "49186"
DEAD_PORT = int(KEY2)
# CONSTANTS.md (TASK 0 boots a, b, c): 16 seen 3.2 s / 3000 1.3 s after JOIN, buttons shown <= 2.9 s, the trap 0.4 s after the
# DISCONNECT, red exit <= 0.61 s after the OK click, green menu 0.10 s, the host's 62 0.7 s after the DISCONNECT.
POLL_S, SHOWN_S, STABLE_S, OUTCOME_S, HOST_S, BOOT_S = 0.05, 30.0, 2.0, 15.0, 15.0, 30.0
SEEN_S = {16: 30.0, 3000: 40.0}
KEY_GAP_S, AFTER_FIELD_S, AFTER_RETURN_S = 0.06, 0.3, 0.4
SDLK_END, SDLK_BACKSPACE, SDLK_RETURN = 279, 8, 13
CELLS = {"A": ("A-pre", "A-alive", "A-nocrash", "A-menu", "A-host"),
         "B": ("B-pre", "B-alive", "B-nocrash", "B-menu", "B-host"),
         "C": ("C-pre", "C-list")}
TITLE = {16: "Cannot connect to server", 3000: "Please click the 'New Battle' button"}
HOST_TITLE = {62: lambda t: t.startswith("Waiting for"), 20: lambda t: t.endswith("has left the server")}
LIST = ["MainMenuState", "NewBattleState", "ServerList"]

class Miss(Exception):
    """A precondition miss: it ends its row; the row's pre cell fails with it, the other cells are not reached."""

def now(t0): return round(time.time() - t0, 3)
def unreachable(e): return "unreachable: %s: %s" % (type(e).__name__, str(e)[:160])

def short(x, n=700):
    s = x if isinstance(x, str) else json.dumps(x, default=str, sort_keys=True)
    return s if len(s) <= n else s[:n] + "..."

def probe(f, fallback):
    try:
        return f()
    except Exception as e:  # noqa: BLE001
        return fallback(unreachable(e))

def stk(gc):
    if gc.proc is not None and gc.proc.poll() is not None:
        return ["<exited %s>" % gc.proc.poll()]
    return probe(lambda: session.states_stripped(gc), lambda u: [u])

def pick(gc, cmd, keys):
    return probe(lambda: {k: v for k, v in gc.cmd({"cmd": cmd}).items() if k in keys}, lambda u: {"error": u})

def info(gc): return pick(gc, "coop_dialog_info", ("present", "code", "title", "backText", "backVisible"))
def coop(gc): return pick(gc, "get_coop", ("coopCampaign", "onConnect", "coopDialog", "serverOwner", "hasSave"))
def has_save(gc): return probe(lambda: gc.cmd({"cmd": "world_state"}).get("has_save"), lambda u: u)

def cpu():  # the % Processor Time counter and any foreign game (S24)
    c = harness.cpu_load()
    return {"cpu": harness.cpu_text(c["cpu"], 0), "foreign": ",".join(c["wardogs"])}

def read_text(p):
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()

def crash_lines(paths):  # each new crash_*.log and its #0 line
    return {os.path.basename(p): probe(lambda p=p: next((ln.strip() for ln in read_text(p).splitlines()
                                                         if ln.strip().startswith("#0 ")), None), lambda u: u) for p in sorted(paths)}

def widgets(gc):
    r = gc.cmd({"cmd": "list_widgets"})
    return (r.get("state") or "").replace("class OpenXcom::", ""), r.get("widgets", [])

def shown(gc, state, match, t0, step, trail=None):
    """poll list_widgets every POLL_S until the top is `state` and the first visible interactive TextButton containing `match`
    reads hidden false, within SHOWN_S; a miss raises Miss naming the step"""
    end, last = time.time() + SHOWN_S, None
    while time.time() < end:
        if gc.proc.poll() is not None:
            raise Miss("%s: %s exited %s" % (step, gc.name, gc.proc.poll()))
        st, ws = widgets(gc)
        b = next((w for w in ws if w.get("visible") and w.get("interactive") and "TextButton" in (w.get("type") or "")
                  and match in (w.get("text") or "").lower()), None)
        last = [st, None if b is None else [b.get("text"), b.get("visible"), b.get("hidden")]]
        if trail is not None and (not trail or trail[-1][1:] != last):
            trail.append([now(t0)] + last)
        if st == state and b is not None and b.get("hidden") is False:
            return
        time.sleep(POLL_S)
    raise Miss("%s: %s %r not shown on %s in %.0f s (last %s)" % (step, gc.name, match, state, SHOWN_S, last))

def press(gc, state, match, t0, ev, step):
    shown(gc, state, match, t0, step)
    r = gc.cmd({"cmd": "click_widget", "match": match})
    ev["steps"].append([gc.name, step, now(t0), r.get("ok"), r.get("text")])
    if r.get("ok") is not True:
        raise Miss("%s: click_widget %s" % (step, short(r, 200)))

def trap(client, t0, ev):
    """OPTIONS > CO-OP > DISCONNECT (real clicks); within STABLE_S the trap's stack, has_save true and coopCampaign true"""
    for state, match in (("GeoscapeState", "options"), ("PauseState", "co-op"), ("LobbyMenu", "disconnect")):
        press(client, state, match, t0, ev, match)
    end, last = time.time() + STABLE_S, None
    while time.time() < end:
        last = [stk(client), has_save(client), coop(client).get("coopCampaign")]
        if last == [["GoToMainMenuState", "ServerList"], True, True]:
            ev["trap"] = [now(t0)] + last
            return
        time.sleep(POLL_S)
    raise Miss("trap: [stack, has_save, coopCampaign] %s" % short(last, 300))

def refused(port, ev):
    """a Python connect to 127.0.0.1:port raises ConnectionRefusedError (just before the dial)"""
    r = probe(lambda: socket.create_connection(("127.0.0.1", port), timeout=3).close() or "listening", lambda u: u)
    ev["refused"] = [port, r]
    if not r.startswith("unreachable: ConnectionRefusedError"):
        raise Miss("port %d not refused: %s" % (port, r))

def client_address(gc):
    """the port in the client's client_address.json (user dir xcom1/ or root), polled within SHOWN_S"""
    end = time.time() + SHOWN_S
    while time.time() < end:
        for p in (os.path.join(gc.user_dir, "xcom1", "client_address.json"), os.path.join(gc.user_dir, "client_address.json")):
            got = probe(lambda p=p: json.loads(read_text(p)).get("port"), lambda u: None) if os.path.exists(p) else None
            if got is not None:
                return got
        time.sleep(POLL_S)
    return "absent"

def dial(client, port, t0, ev):
    """Direct Connect; the port TextEdit (largest y): END, 10 x BACKSPACE, the digits, RETURN (real keys); JOIN; client_address.json"""
    press(client, "ServerList", "direct connect", t0, ev, "direct connect")
    shown(client, "DirectConnect", "join", t0, "join shown")
    st, ws = widgets(client)
    vis = [w for w in ws if w.get("visible") and w.get("interactive")]
    edits = [w for w in vis if "TextEdit" in (w.get("type") or "")]
    if st != "DirectConnect" or not edits:
        raise Miss("port field: top %s, %d visible TextEdits" % (st, len(edits)))
    nth = vis.index(max(edits, key=lambda w: w.get("y")))
    r = client.cmd({"cmd": "click_widget", "nth": nth})
    time.sleep(AFTER_FIELD_S)
    oks = []
    for k in [SDLK_END] + [SDLK_BACKSPACE] * 10 + [ord(c) for c in str(port)] + [SDLK_RETURN]:
        oks.append(client.cmd({"cmd": "inject_input", "kind": "key", "key": k}).get("ok"))
        time.sleep(KEY_GAP_S)
    time.sleep(AFTER_RETURN_S - KEY_GAP_S)
    ev["steps"].append([client.name, "port %s (nth %d)" % (port, nth), now(t0), r.get("ok"), all(oks)])
    if r.get("ok") is not True or not all(oks):
        raise Miss("port entry: field click %s, key replies %s" % (short(r, 150), oks))
    press(client, "DirectConnect", "join", t0, ev, "join")
    ev["clientAddress"] = addr = client_address(client)
    if str(addr) != str(port):
        raise Miss("client_address.json port %s, typed %s" % (addr, port))

def top_dialog(gc, code, t0, timeout, title_ok=lambda t: True):
    """poll every POLL_S until a top CoopState with coop_dialog_info.code == code and title_ok(title), within `timeout`: (ok, read)"""
    end, last = time.time() + timeout, None
    while time.time() < end:
        if gc.proc.poll() is not None:
            return False, {"t": now(t0), "exit": gc.proc.poll()}
        s, d = stk(gc), info(gc)
        last = {"t": now(t0), "stack": s, "dlg": d}
        if s[-1:] == ["CoopState"] and d.get("code") == code and title_ok(d.get("title") or ""):
            return True, last
        time.sleep(POLL_S)
    return False, dict(last or {}, miss="no top CoopState %s in %.0f s" % (code, timeout))

def dialog(gc, code, t0, ev, timeout):
    ok, last = top_dialog(gc, code, t0, timeout)
    ev.setdefault("seen", []).append([gc.name, code, last])
    if not ok:
        raise Miss("dialog %s on %s: %s" % (code, gc.name, short(last, 300)))
    return last["dlg"].get("title") or ""

def click_ok(client, host, code, want, rid, t0, ev, cells):
    """the code's dialog, its OK shown (the widget trail), the stack and title at the click, crash0, one REAL OK click: the pre cell"""
    title = dialog(client, code, t0, ev, SEEN_S[code])
    ev["okTrail"] = trail = []
    shown(client, "CoopState", "ok", t0, "ok shown", trail)
    ev["beforeClick"] = {"stack": stk(client), "dlg": info(client), "get_coop": coop(client), "hostStack": stk(host) if host else None}
    if ev["beforeClick"]["stack"] != want or not title.startswith(TITLE[code]):
        raise Miss("at the click: stack %s (want %s), title %r" % (ev["beforeClick"]["stack"], want, title))
    crash0 = session._crash_log_snapshot()
    r = client.cmd({"cmd": "click_widget", "match": "ok"})
    ev["okClick"] = [now(t0), r.get("ok"), r.get("text")]
    if r.get("ok") is not True or r.get("text") != "OK":
        raise Miss("OK click %s" % short(r, 200))
    cells[rid + "-pre"] = (True, None)
    return crash0

def outcome(gc, t0, ev, want, key="outcome"):
    """poll every 0.1 s within OUTCOME_S until the process exits or its stack == want (MainMenuState: and has_save false): reached"""
    end, last = time.time() + OUTCOME_S, None
    while time.time() < end:
        if gc.proc.poll() is not None:
            ev[key] = {"t": now(t0), "exit": gc.proc.poll()}
            return False
        s = stk(gc)
        hs = has_save(gc) if s == want else None
        last = [s, hs]
        if s == want and (want != ["MainMenuState"] or hs is False):
            ev[key] = {"t": now(t0), "stack": s, "has_save": hs}
            return True
        time.sleep(0.1)
    ev[key] = {"miss": "neither an exit nor %s in %.0f s" % (want, OUTCOME_S), "last": last}
    return False

def finish(client, host, rid, want, t0, ev, cells, crash0):
    """outcome -> alive -> the host's top dialog within HOST_S (A: 62, B: 20) -> the crash diff -> the row's cells"""
    reached = outcome(client, t0, ev, want)
    alive = client.proc.poll() is None
    ev["afterOutcome"] = {gc.name: stk(gc) for gc in (client, host) if gc is not None}
    if host is not None:
        code = 62 if rid == "A" else 20
        host_ok, ev["host"] = top_dialog(host, code, t0, HOST_S, HOST_TITLE[code])
    time.sleep(1.0)  # the crash handler's files
    new = session._crash_log_snapshot() - crash0
    ev["newCrash"], ev["exit"] = crash_lines(new), client.proc.poll()
    if rid == "C":
        cells["C-list"] = (alive and reached and not new, {"outcome": ev["outcome"], "newCrash": ev["newCrash"]})
        return
    cells.update({rid + "-alive": (alive, {"outcome": ev["outcome"], "exit": ev["exit"]}), rid + "-nocrash": (not new, ev["newCrash"]),
                  rid + "-menu": (reached, ev["outcome"]), rid + "-host": (host_ok, ev["host"])})

def row_a(host, client, ev, cells):
    """trap -> Direct Connect to the refused DEAD_PORT -> 16 alone -> OK"""
    t0 = time.time()
    trap(client, t0, ev)
    refused(DEAD_PORT, ev)
    dial(client, DEAD_PORT, t0, ev)
    crash0 = click_ok(client, host, 16, ["CoopState"], "A", t0, ev, cells)
    finish(client, host, "A", ["MainMenuState"], t0, ev, cells, crash0)

def row_b(host, client, ev, cells):
    """trap; the host's 62 -> its ABANDON (real click) -> a NEW BATTLE host on KEY2 (the four levers) -> Direct Connect -> 3000 -> OK"""
    t0 = time.time()
    trap(client, t0, ev)
    dialog(host, 62, t0, ev, HOST_S)
    press(host, "CoopState", "abandon", t0, ev, "host abandon")
    if not outcome(host, t0, ev, ["MainMenuState"], "hostMain"):
        raise Miss("host after ABANDON: %s" % short(ev["hostMain"], 300))
    try:
        hm = {"visibility": 0, "server": "TestSrv", "port": KEY2, "player": "HostPlayer"}
        for lever, state, extra in (("open_new_battle", "NewBattleState", {}), ("newbattle_coop", "ServerList", {}),
                                    ("server_list_host", "HostMenu", {}), ("host_menu_host", "LobbyMenu", hm)):
            host.ok(dict({"cmd": lever}, **extra))
            host.wait_for("host " + state, lambda state=state: session.has_state(host, state))
        port = harness._EPHEMERAL_COOP_PORTS[KEY2]
        harness._wait_host_listening(host, KEY2, port, client)
    except Exception as e:  # noqa: BLE001
        raise Miss("NEW BATTLE host: %s" % unreachable(e))
    ev["steps"].append([host.name, "NEW BATTLE host listening", now(t0), port])
    dial(client, port, t0, ev)
    crash0 = click_ok(client, host, 3000, ["CoopState"], "B", t0, ev, cells)
    finish(client, host, "B", ["MainMenuState"], t0, ev, cells, crash0)

def row_c(host, client, ev, cells):
    """the control: no world. NEW BATTLE > COOP -> the browser -> Direct Connect to DEAD_PORT -> 16 over the browser -> OK"""
    t0 = time.time()
    press(client, "MainMenuState", "new battle", t0, ev, "new battle")
    press(client, "NewBattleState", "coop", t0, ev, "coop")
    shown(client, "ServerList", "direct connect", t0, "browser")
    ev["coopCampaign"] = coop(client).get("coopCampaign")
    if ev["coopCampaign"] is not False:
        raise Miss("coopCampaign %r on the browser" % ev["coopCampaign"])
    refused(DEAD_PORT, ev)
    dial(client, DEAD_PORT, t0, ev)
    crash0 = click_ok(client, None, 16, LIST + ["CoopState"], "C", t0, ev, cells)
    finish(client, None, "C", LIST, t0, ev, cells, crash0)

def settle(host, client, ev):
    """both tops GeoscapeState, both stacks unchanged STABLE_S, within BOOT_S"""
    t0, last, since = time.time(), None, time.time()
    while time.time() - t0 < BOOT_S:
        cur = (tuple(stk(host)), tuple(stk(client)))
        last, since = (cur, time.time()) if cur != last else (last, since)
        if cur[0][-1:] == ("GeoscapeState",) and cur[1][-1:] == ("GeoscapeState",) and time.time() - since >= STABLE_S:
            ev["settle"] = now(t0)
            return True
        time.sleep(0.1)
    return False

def run_row(rid, body):
    """one fresh boot (R-A / R-B: a SEPARATE session.new_campaign pair; R-C: the client alone); the row body; then shutdown"""
    cells, ev, w0, boot_capture = {}, {"cpu": cpu(), "steps": []}, time.time(), None
    client = GameClient("client", None, make_user_dir("w2h56_%s_client" % rid.lower()))
    host = None if rid == "C" else GameClient("host", None, make_user_dir("w2h56_%s_host" % rid.lower()))
    games = [gc for gc in (host, client) if gc is not None]
    try:
        try:
            for gc in games:
                gc.spawn(); gc.connect()
            if host is not None:
                session.new_campaign(host, client, port=KEY)
            booted = host is None or settle(host, client, ev)
        except Exception as e:  # noqa: BLE001
            booted, ev["bootError"] = False, unreachable(e)
        if not booted:  # ONE CAPTURE line: every game's stack, coop_dialog_info, get_coop
            return cells, ev, {gc.name: {"stack": stk(gc), "dlg": info(gc), "get_coop": coop(gc)} for gc in games if gc.proc}
        try:
            body(host, client, ev, cells)
        except Miss as m:
            ev["miss"] = str(m)
            cells.setdefault(rid + "-pre", (False, "precondition miss: %s" % m))
    except Exception as e:  # noqa: BLE001
        ev["error"] = unreachable(e)
        cells.setdefault(rid + "-pre", (False, ev["error"]))
    finally:
        for gc, exp in ((client, (0, 3, 3221226505)), (host, (0, 3221226505))):  # a red client already exited 3
            try:
                if gc is not None and gc.proc is not None:
                    gc.shutdown(expected_returncodes=exp)
            except Exception as e:  # noqa: BLE001
                ev.setdefault("shutdown", {})[gc.name] = str(e)[:200]
        ev["rc"] = {gc.name: gc.proc.poll() if gc.proc is not None else None for gc in games}
        ev["wall"] = round(time.time() - w0, 1)
    return cells, ev, boot_capture

def report(rid, cells, ev, boot_capture):
    print("EVIDENCE R-%s: %s" % (rid, short(ev, 4000)), flush=True)
    if boot_capture is not None:
        print("FAIL R-%s boot: %s" % (rid, "no spawn + connect" if rid == "C" else "both tops not GeoscapeState for %.0f s within %.0f s"
                                     % (STABLE_S, BOOT_S)), flush=True)
        print("CAPTURE R-%s: %s" % (rid, short(boot_capture, 3000)), flush=True)
    passed = []
    for name in CELLS[rid]:
        ok, detail = cells.get(name, (False, "not reached"))
        print(("PASS %s" % name) if ok else ("FAIL %s: %s" % (name, short(detail))), flush=True)
        passed += [name] if ok else []
    print("ROW R-%s: %s (%d/%d cells, wall %s s)" % (rid, "PASS" if len(passed) == len(CELLS[rid]) else "FAIL", len(passed),
                                                    len(CELLS[rid]), ev.get("wall")), flush=True)
    return passed

def main():
    t0, passed, walls = time.time(), [], {}
    for rid, body in (("A", row_a), ("B", row_b), ("C", row_c)):
        cells, ev, boot_capture = run_row(rid, body)
        passed += report(rid, cells, ev, boot_capture)
        walls["R-" + rid] = ev.get("wall")
    failed = [c for rid in ("A", "B", "C") for c in CELLS[rid] if c not in passed]
    print("\ntest_client_dialog_ok_crash: %d/12 cells passed (fail=%s) walls %s in %.1fs"
          % (12 - len(failed), failed, json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
