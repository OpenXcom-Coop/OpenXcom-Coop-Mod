"""W2-H62 S-A - test_client_base_ghost.py (L-H56-1, R-H62-0; captures lh56-1-cap F18567 / F18568 and lh56-1b-cap F18708; docs
rewrite/prompts/w2h62_sa_client_ghost.md (f) and the common file rewrite/prompts/w2h62_base_marker_cache.md; TASK 0
rewrite/w2h62-task0/sa/CONSTANTS.md). In a SEPARATE campaign each machine shows the partner's bases as marker bases built from ONE
process-wide cache (j_markers, connectionTCP.cpp). The cache outlives the session: a client that leaves campaign A and joins campaign B in
the same game process keeps A's host base as a marker (the client coopBase2 keeps the cache when the new host's reply has no markers).
ONE boot; keys K1 "49213" (campaigns A and C: hosted twice, a new OS port each time, F18826) and K2 "49214" (B); dirs w2h62a_*:
  R-3 campaign A (session.new_campaign), the fresh client: R-3a GUARD - its one marker is exactly the host's base.
  R-1 the trap exit (OPTIONS > CO-OP > DISCONNECT) to campaign B, joined from the trap browser: R-1a RED - no client marker with A's host
      id at READ 1 / 2 / 3; R-1b RED - only B's host marker (READ 1: 0 or 1 of it; READ 2 / 3: exactly it); R-1c GUARD - B's host marker
      at READ 3; R-1d GUARD - the host's markers are exactly the client's B base at READ 3.
  R-2 the ordinary exit (OPTIONS > ABANDON GAME > YES) to campaign C (NEW BATTLE > COOP > Direct Connect): R-2a RED - no client marker
      with B's or A's host id; R-2b RED, R-2c GUARD, R-2d GUARD as R-1 for C; CRASH GUARD - no crash file new since the boot start and
      both games alive at the end (read at the end of every run).
READ 1 = the client at BuildNewBaseState (after the host's P3); READ 2 = 2 s after the client's P4; READ 3 = both geoscapes stable after
the host's BEGIN. Every press is a REAL click (click_widget) on a button list_widgets reads visible, not hidden, on the named top state,
except the port keys (inject_input) and the base placements (the place_first_base lever). Never dismiss_popup, coop_dialog_back or
leave_base. Every id is read from geo_state at run time (S25). One EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict;
a precondition miss ends its row and every later row (cells "not reached"); a boot miss fails every cell "boot" with ONE CAPTURE line.
WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_client_base_ghost.py"""

import glob, json, math, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402

K1 = "49213"
K2 = "49214"
NAME = "ClientPlayer"
SDLK_END, SDLK_BACKSPACE, SDLK_RETURN = 279, 8, 13
LAND = (harness.LAND_LON, harness.LAND_LAT)
# CONSTANTS.md (TASK 0 boots a, b, c): P3 HOST_LON/LAT off land 6/6, then LAND+0.06/+0.06 accepted 6/6; P4 cand 0 accepted 6/6; the trap /
# main menu and the host's 62 at the first poll after the 2 s settle; Profile OKs within 5 s; stable_geo 5.13 s; boot wall ~80 s.
P3_CANDS = [(session.HOST_LON, session.HOST_LAT), (LAND[0] + 0.06, LAND[1] + 0.06), (LAND[0] + 0.03, LAND[1] - 0.03), LAND]
P4_CANDS = [(LAND[0] - 0.03, LAND[1] - 0.03), (LAND[0] + 0.06, LAND[1] - 0.03), (LAND[0] + 0.06, LAND[1] + 0.06), LAND]
STABLE_S, STABLE_TO, TRAP_S, EXIT_S, DROP_S, PROFILE_S, BNB_S, P4_WAIT, QUIET, QUIET_EXIT, JOIN_S = (
    5.0, 90.0, 10.0, 10.0, 20.0, 30.0, 120.0, 2.0, 1.5, 2.0, 3.0)
NEEDLES = ("[coop-session]", "COOP_READY", "disconnect", "GoToMainMenu")
CELLS = {"R-3": ("R-3a",), "R-1": ("R-1a", "R-1b", "R-1c", "R-1d"), "R-2": ("R-2a", "R-2b", "R-2c", "R-2d", "CRASH")}
T0, IDS = [time.time()], {}

class Miss(Exception):
    """A precondition miss: it ends its row and every later row."""

def now(): return round(time.time() - T0[0], 3)
def unreachable(e): return "%s: %s" % (type(e).__name__, str(e)[:300])

def short(x, n=12000):
    s = x if isinstance(x, str) else json.dumps(x, default=str, sort_keys=True)
    return s if len(s) <= n else s[:n] + "..."

def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # noqa: BLE001
        return {"error": unreachable(e)}

def stk(gc):
    if gc.proc is not None and gc.proc.poll() is not None:
        return ["<exited %s>" % gc.proc.poll()]
    try:
        return session.states_stripped(gc)
    except Exception as e:  # noqa: BLE001
        return ["unreachable: " + unreachable(e)]

def top(gc): return (stk(gc) or [None])[-1]
def pick(gc, cmd, keys): return {k: v for k, v in q(gc, {"cmd": cmd}).items() if k in keys}
def dlg(gc): return pick(gc, "coop_dialog_info", ("present", "code", "title", "backText", "backVisible", "error"))
def coop(gc): return pick(gc, "get_coop", ("onConnect", "saveID", "coopCampaign", "serverOwner", "error"))
def both(host, client): return {gc.name: {"stack": stk(gc), "dlg": dlg(gc)} for gc in (host, client)}

def geo(gc):
    r = q(gc, {"cmd": "geo_state"})
    if "bases" not in r:
        return r.get("error", "no bases key")
    return [[b.get("name"), b.get("coopBaseId"), b.get("coopIcon"), b.get("coopBase"), round(b.get("lon") or 0, 6), round(b.get("lat") or 0, 6)]
            for b in r["bases"]]

def mir(bl): return [(b[0], b[1]) for b in bl if b[2]] if isinstance(bl, list) else []
def own(bl): return [(b[0], b[1]) for b in bl if not b[2] and not b[3]] if isinstance(bl, list) else []
def crashes(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))

def cpu():  # the % Processor Time counter and any foreign game (S24)
    c = harness.cpu_load()
    return {"cpu": harness.cpu_text(c["cpu"], 0), "foreign": ",".join(c["wardogs"])}

def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read().splitlines()

def lines_since(gc, n0):
    return [ln.split("\t")[0][-13:-1] + " " + ln.split("\t")[-1][:300] for ln in logl(gc)[n0:] if any(n in ln for n in NEEDLES)][-40:]

def widgets(gc):
    r = q(gc, {"cmd": "list_widgets"})
    return (r.get("state") or "").replace("class OpenXcom::", ""), r.get("widgets", [])

def shown(gc, state, match, timeout):
    """poll list_widgets until the top is `state` and the first visible interactive TextButton containing `match` reads hidden false"""
    end, last = time.time() + timeout, None
    while time.time() < end:
        if gc.proc.poll() is not None:
            raise Miss("%s exited %s waiting for %r on %s" % (gc.name, gc.proc.poll(), match, state))
        st, ws = widgets(gc)
        b = next((w for w in ws if w.get("visible") and w.get("interactive") and "TextButton" in (w.get("type") or "")
                  and match in (w.get("text") or "").lower()), None)
        last = [st, None if b is None else [b.get("text"), b.get("hidden")]]
        if st == state and b is not None and b.get("hidden") is False:
            return
        time.sleep(0.05)
    raise Miss("%s %r not shown on %s within %.0f s (last %s)" % (gc.name, match, state, timeout, last))

def settle(gc, quiet):
    end, last, prev = time.time() + 20.0, time.time(), None
    while time.time() < end and gc.proc.poll() is None:
        s = stk(gc)
        prev, last = (s, time.time()) if s != prev else (prev, last)
        if time.time() - last >= quiet:
            break
        time.sleep(0.05)
    return prev

def press(gc, state, match, ev, step, timeout=30.0, quiet=QUIET):
    shown(gc, state, match, timeout)
    r = q(gc, {"cmd": "click_widget", "match": match})
    ev["steps"].append([gc.name, step, now(), r.get("ok"), r.get("text"), settle(gc, quiet)])
    if r.get("ok") is not True:
        raise Miss("%s: click_widget %s" % (step, short(r, 200)))

def direct_connect(gc, port, ev):
    """ServerList DIRECT CONNECT; the port TextEdit (largest y): END, 10 x BACKSPACE, the digits, RETURN (real keys); JOIN"""
    press(gc, "ServerList", "direct connect", ev, "direct connect")
    shown(gc, "DirectConnect", "join", 20.0)
    st, ws = widgets(gc)
    vis = [w for w in ws if w.get("visible") and w.get("interactive")]
    edits = [w for w in vis if "TextEdit" in (w.get("type") or "")]
    if st != "DirectConnect" or len(edits) < 2:
        raise Miss("port field: top %s, %d visible TextEdits" % (st, len(edits)))
    r = q(gc, {"cmd": "click_widget", "nth": vis.index(max(edits, key=lambda w: w.get("y")))})
    time.sleep(0.3)
    oks = []
    for k in [SDLK_END] + [SDLK_BACKSPACE] * 10 + [ord(c) for c in str(port)]:
        oks.append(q(gc, {"cmd": "inject_input", "kind": "key", "key": k}).get("ok"))
        time.sleep(0.06)
    time.sleep(0.3)
    oks.append(q(gc, {"cmd": "inject_input", "kind": "key", "key": SDLK_RETURN}).get("ok"))
    time.sleep(0.4)
    ev["steps"].append([gc.name, "port %s" % port, now(), r.get("ok"), all(oks)])
    if r.get("ok") is not True or not all(oks):
        raise Miss("port entry: field click %s, key replies %s" % (short(r, 150), oks))
    press(gc, "DirectConnect", "join", ev, "join", timeout=10.0, quiet=0.3)

def watch_code(gc, codes, timeout):
    end = time.time() + timeout
    while time.time() < end and gc.proc.poll() is None:
        if top(gc) == "CoopState":
            d = dlg(gc)
            if d.get("code") in codes:
                return dict(d, t=now())
        time.sleep(0.05)
    return None

def stable_geo(host, client):
    ts, last, prev = time.time(), time.time(), None
    while time.time() - ts < STABLE_TO:
        cur = (tuple(stk(host)), tuple(stk(client)))
        prev, last = (cur, time.time()) if cur != prev else (prev, last)
        if cur[0][-1:] == ("GeoscapeState",) and cur[1][-1:] == ("GeoscapeState",) and time.time() - last >= STABLE_S:
            return now()
        time.sleep(0.1)
    raise Miss("both tops not GeoscapeState for %.0f s within %.0f s (last %s)" % (STABLE_S, STABLE_TO, prev))

def wait_state(gc, name, timeout, what):
    end = time.time() + timeout
    while time.time() < end and gc.proc.poll() is None:
        if session.has_state(gc, name):
            return
        time.sleep(0.1)
    raise Miss("%s: %s not on %s's stack within %.0f s (%s)" % (what, name, gc.name, timeout, stk(gc)))

def read(host, client, ev, key):
    hb, cb = geo(host), geo(client)
    ev[key] = {"t": now(), "client": {"stack": stk(client), "bases": cb, "mir": mir(cb)}, "host": {"stack": stk(host), "bases": hb, "mir": mir(hb)}}

def one_id(gc, what):
    o = own(geo(gc))
    if len(o) != 1:
        raise Miss("%s: own(%s) holds %d bases: %s" % (what, gc.name, len(o), o))
    return o[0][1]

def place(gc, cands, name, ev, key, avoid=None):
    """place_first_base on the first candidate that is land (and >= 0.02 rad from P3): the PINNED SETUP VALUES' replacement rule"""
    for i, (lon, lat) in enumerate(cands):
        if avoid is not None and math.hypot(lon - avoid[0], lat - avoid[1]) < 0.02:
            continue
        r = q(gc, {"cmd": "place_first_base", "lon": lon, "lat": lat, "name": name})
        ev.setdefault(key, []).append([i, round(lon, 6), round(lat, 6), r.get("ok"), r.get("error")])
        if r.get("ok"):
            return (lon, lat)
    raise Miss("%s: no placement candidate accepted: %s" % (key, ev.get(key)))

def seed_player_name(user_dir):  # the name a player typed in the browser earlier (both captures)
    for d in (os.path.join(user_dir, "xcom1"), user_dir):
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "player_name.json"), "w", encoding="utf-8") as fh:
            json.dump({"name": NAME}, fh)

def client_exit(host, client, ev, trap):
    """the client's exit by real clicks; its stack (trap: [GoToMainMenuState, ServerList], else [MainMenuState]); the host's 62; the
    host's ABANDON (real click) and its main menu"""
    presses = (("GeoscapeState", "options"), ("PauseState", "co-op"), ("LobbyMenu", "disconnect")) if trap else (
        ("GeoscapeState", "options"), ("PauseState", "abandon"), ("AbandonGameState", "yes"))
    for i, (state, match) in enumerate(presses):
        press(client, state, match, ev, match, quiet=QUIET_EXIT if i == 2 else QUIET)
    want, end, s = (["GoToMainMenuState", "ServerList"] if trap else ["MainMenuState"]), time.time() + (TRAP_S if trap else EXIT_S), None
    while time.time() < end:
        s = stk(client)
        if s[-len(want):] == want:
            break
        time.sleep(0.05)
    ev["clientExit"] = {"t": now(), "pre": both(host, client), "coop": coop(client)}
    if s is None or s[-len(want):] != want:
        raise Miss("client stack %s after the exit, want it to end %s" % (s, want))
    ev["host62"] = watch_code(host, (62,), DROP_S)
    if ev["host62"] is None:
        raise Miss("no host CoopState 62 within %.0f s: %s" % (DROP_S, both(host, client)))
    press(host, "CoopState", "abandon", ev, "host abandon", quiet=QUIET_EXIT)
    ev["hostMain"] = {"t": now(), "pre": both(host, client)}
    if stk(host) != ["MainMenuState"]:
        raise Miss("host after ABANDON: %s" % stk(host))

def newcamp(host, client, key, hn, cn, ev, ordinary):
    """NEWCAMP: the host's levers to a SEPARATE lobby on `key`; the client's Direct Connect (after NEW BATTLE > COOP on the ordinary
    route); Profile OKs; START + confirm; P3; READ 1; P4; READ 2; BEGIN; stable_geo; READ 3"""
    host.ok({"cmd": "open_new_game", "mode": "coop"})
    wait_state(host, "NewGameState", 30, "open_new_game")
    host.ok({"cmd": "newgame_ok"})
    wait_state(host, "HostMenu", 30, "newgame_ok")
    host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": key, "player": "HostPlayer"})
    wait_state(host, "LobbyMenu", 30, "host_tcp")
    port = harness._EPHEMERAL_COOP_PORTS.get(key)
    harness._wait_host_listening(host, key, port, client)
    ev["ports"] = [now(), dict(harness._EPHEMERAL_COOP_PORTS)]
    if ordinary:
        press(client, "MainMenuState", "new battle", ev, "new battle")
        press(client, "NewBattleState", "coop", ev, "coop")
    ev["browser"] = stk(client)
    direct_connect(client, port, ev)
    time.sleep(JOIN_S)
    tj = time.time()
    while not (q(host, {"cmd": "lobby_state"}).get("startEligible") and top(host) == "LobbyMenu" and top(client) != "Profile"):
        for gc in (host, client):
            if top(gc) == "Profile":
                press(gc, "Profile", "ok", ev, "profile ok", timeout=5.0, quiet=0.3)
        if time.time() - tj > PROFILE_S:
            raise Miss("no startEligible with LobbyMenu on top within %.0f s: %s" % (PROFILE_S, both(host, client)))
        time.sleep(0.2)
    ev["startEligible"] = {"t": now(), "pre": both(host, client)}
    press(host, "LobbyMenu", "start campaign", ev, "start campaign", timeout=20.0, quiet=0.5)
    press(host, "ConfirmStartCampaignState", "ok", ev, "start confirm", timeout=20.0, quiet=0.5)
    wait_state(host, "BuildNewBaseState", BNB_S, "host placement")
    p3 = place(host, P3_CANDS, hn, ev, "P3")
    time.sleep(1.0)
    ev["H"] = one_id(host, "after P3")
    wait_state(client, "BuildNewBaseState", BNB_S, "client placement")
    read(host, client, ev, "read1")
    place(client, P4_CANDS, cn, ev, "P4", avoid=p3)
    time.sleep(P4_WAIT)
    read(host, client, ev, "read2")
    ev["C"] = one_id(client, "after P4")
    d = watch_code(host, (60, 62), 120)
    if d is None:
        raise Miss("no host CoopState 60 / 62 for BEGIN within 120 s: %s" % both(host, client))
    end = time.time() + 30
    while time.time() < end and not (d.get("backVisible") is True and d.get("backText")):
        time.sleep(0.1)
        d = dlg(host)
    ev["begin"] = d
    press(host, "CoopState", (d.get("backText") or "begin").lower(), ev, "host begin", timeout=20.0, quiet=0.5)
    ev["stableGeo"] = stable_geo(host, client)
    read(host, client, ev, "read3")

def judge(rid, ev, cells, prev, hn, cn):
    H, C = ev["H"], ev["C"]
    ms = [ev[k]["client"]["mir"] for k in ("read1", "read2", "read3")]
    det = {"READ1": ms[0], "READ2": ms[1], "READ3": ms[2]}
    cells[rid + "a"] = (not [m for mm in ms for m in mm if m[1] in prev], dict(det, forbiddenIds=list(prev)))
    cells[rid + "b"] = (len(ms[0]) <= 1 and all(m[1] == H for m in ms[0]) and ms[1] == [(hn, H)] and ms[2] == [(hn, H)],
                        dict(det, want=[hn, H]))
    cells[rid + "c"] = ((hn, H) in ms[2], {"READ3": ms[2], "want": [hn, H]})
    hm = ev["read3"]["host"]["mir"]
    cells[rid + "d"] = (hm == [(cn, C)], {"hostREAD3": hm, "want": [cn, C]})

def distinct(ev, prev):
    if ev["H"] in prev or ev["C"] in prev:
        raise Miss("new campaign ids H %s / C %s not distinct from %s" % (ev["H"], ev["C"], prev))

def row_r3(host, client, ev, cells):
    """the fresh client in its first campaign A: HA, CA and the client's markers after stable_geo"""
    read(host, client, ev, "read")
    IDS["HA"], IDS["CA"] = one_id(host, "R-3"), one_id(client, "R-3")
    hn, mc = own(ev["read"]["host"]["bases"])[0][0], ev["read"]["client"]["mir"]
    cells["R-3a"] = (mc == [(hn, IDS["HA"])] and IDS["HA"] != IDS["CA"], {"mirClient": mc, "HA": IDS["HA"], "CA": IDS["CA"], "hostBase": hn})

def row_r1(host, client, ev, cells):
    """the trap exit -> campaign B on K2, joined from the trap browser the client already shows"""
    client_exit(host, client, ev, trap=True)
    newcamp(host, client, K2, "HostBaseB", "ClientBaseB", ev, ordinary=False)
    distinct(ev, (IDS["HA"], IDS["CA"]))
    IDS["HB"], IDS["CB"] = ev["H"], ev["C"]
    judge("R-1", ev, cells, (IDS["HA"],), "HostBaseB", "ClientBaseB")

def row_r2(host, client, ev, cells):
    """the ordinary exit -> campaign C on K1 hosted again (a new OS port), joined by NEW BATTLE > COOP > Direct Connect"""
    client_exit(host, client, ev, trap=False)
    newcamp(host, client, K1, "HostBaseC", "ClientBaseC", ev, ordinary=True)
    distinct(ev, (IDS["HA"], IDS["HB"], IDS["CA"], IDS["CB"]))
    judge("R-2", ev, cells, (IDS["HB"], IDS["HA"]), "HostBaseC", "ClientBaseC")

def dump(gc):
    if gc.proc is None or gc.proc.poll() is not None:
        return {"exited": gc.proc.poll() if gc.proc else None}
    ws = widgets(gc)[1]
    return {"get_state": stk(gc), "get_coop": coop(gc), "coop_dialog_info": dlg(gc), "geo_state": geo(gc),
            "list_widgets": [[w.get("type"), w.get("text"), w.get("visible"), w.get("hidden")] for w in ws][:30],
            "logTail": [ln.split("\t")[-1][:200] for ln in logl(gc)[-15:]]}

def report(rid, ev, cells, capture):
    print("EVIDENCE %s: %s" % (rid, short(ev)), flush=True)
    passed = 0
    for name in CELLS[rid]:
        ok, det = cells.get(name, (False, "not reached"))
        if capture is not None:
            ok, det = False, "boot" if name != "CRASH" else "boot; %s" % short(det, 400)
        print(("PASS %s" % name) if ok else ("FAIL %s: %s" % (name, short(det, 1500))), flush=True)
        passed += 1 if ok else 0
    print("ROW %s: %s (%d/%d cells)" % (rid, "PASS" if passed == len(CELLS[rid]) else "FAIL", passed, len(CELLS[rid])), flush=True)
    return [n for n in CELLS[rid] if not (capture is None and cells.get(n, (False,))[0])]

def main():
    T0[0] = time.time()
    cells, evs, capture, crash0 = {}, {}, None, crashes()
    host = GameClient("host", None, make_user_dir("w2h62a_host"))
    client = GameClient("client", None, make_user_dir("w2h62a_client"))
    games, boot = (host, client), {"cpu": cpu()}
    try:
        try:
            seed_player_name(client.user_dir)
            for gc in games:
                gc.spawn(); gc.connect()
            session.new_campaign(host, client, port=K1)
            boot["ports"] = dict(harness._EPHEMERAL_COOP_PORTS)
            boot["stableGeo"] = stable_geo(host, client)
        except Exception as e:  # noqa: BLE001
            boot["error"] = unreachable(e)
            capture = {gc.name: dump(gc) for gc in games}
        missed = None
        for rid, body in (("R-3", row_r3), ("R-1", row_r1), ("R-2", row_r2)):
            ev = evs[rid] = {"cpu": cpu(), "tStart": now(), "steps": []} if capture is None else {}
            if capture is not None:
                continue
            if missed is not None:
                ev["notReached"] = missed
                continue
            nh, nc = len(logl(host)), len(logl(client))
            try:
                body(host, client, ev, cells)
            except Exception as e:  # noqa: BLE001
                missed = ev["miss"] = "%s: %s" % (rid, str(e)[:1500] if isinstance(e, Miss) else unreachable(e))
                ev["probes"] = {gc.name: dump(gc) for gc in games}
            finally:
                ev["hostLog"], ev["clientLog"], ev["tEnd"] = lines_since(host, nh), lines_since(client, nc), now()
    finally:
        time.sleep(1.0)
        alive = {gc.name: gc.proc is not None and gc.proc.poll() is None for gc in games}
        rc = {}
        for gc in (client, host):
            try:
                if gc.proc is not None:
                    gc.shutdown(expected_returncodes=(0, 3221226505))
            except Exception as e:  # noqa: BLE001
                rc[gc.name + "Shutdown"] = unreachable(e)
            rc[gc.name] = gc.proc.poll() if gc.proc is not None else None
        new = sorted(os.path.basename(p) for p in crashes() - crash0)
        cells["CRASH"] = (not new and all(alive.values()), {"newCrash": new, "aliveAtEnd": alive, "rc": rc})
    print("BOOT: %s" % short(boot), flush=True)
    if capture is not None:
        print("CAPTURE: %s" % short(capture), flush=True)
    failed = []
    for rid in ("R-3", "R-1", "R-2"):
        failed += report(rid, evs.get(rid, {}), cells, capture)
    print("\ntest_client_base_ghost: %d/10 cells passed (fail=%s) wall %.1fs" % (10 - len(failed), failed, time.time() - T0[0]), flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
