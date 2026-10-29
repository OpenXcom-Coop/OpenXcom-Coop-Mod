"""test_client_base_ghost.py: in a SEPARATE campaign each machine shows the partner's bases as marker bases built from
ONE process-wide cache (j_markers, connectionTCP.cpp). The cache must not outlive the session (deleteAllCoopBases clears
it): kept, a client that leaves campaign A and joins campaign B in the same game process would keep A's host base as a
marker, because the client's coopBase2 handler keeps the cache when the new host's reply has no markers.
ONE boot; lobby keys KEY_AC "49213" (campaigns A and C: hosted twice, a new OS port each time) and KEY_B "49214" (B);
user dirs client_base_ghost_*:
  first_campaign: campaign A (session.new_campaign), the fresh client. first_campaign_host_marker: its one marker is
      exactly the host's base.
  lobby_exit: the client leaves by the lobby (OPTIONS > CO-OP > DISCONNECT, which leaves it on the server browser) and
      joins campaign B from that browser. lobby_exit_no_old_host_marker: no client marker with A's host id at any of the
      three reads; lobby_exit_only_new_host_marker: only B's host marker (while placing: 0 or 1 of it; after placing and
      after BEGIN: exactly it); lobby_exit_new_host_marker_shown: B's host marker after BEGIN;
      lobby_exit_host_shows_client_base: the host's markers are exactly the client's B base after BEGIN.
  abandon_exit: the client leaves by OPTIONS > ABANDON GAME > YES and joins campaign C (NEW BATTLE > COOP > Direct
      Connect). abandon_exit_no_old_host_marker: no client marker with B's or A's host id; the other three cells as
      lobby_exit's for C; no_crash: no crash file new since the boot start and both games alive at the end (read at the
      end of every run).
The *_no_old_host_marker and *_only_new_host_marker cells fail when the cache outlives the session; the other cells
check the setup and pass either way.
The three reads: while placing = the client at BuildNewBaseState (after the host placed its base); after placing = 2 s
after the client placed its base; after BEGIN = both geoscapes stable after the host's BEGIN. Every press is a REAL
click (click_widget) on a button list_widgets reads visible, not hidden, on the named top state, except the port keys
(inject_input) and the base placements (the place_first_base test command). The test never uses dismiss_popup,
coop_dialog_back or leave_base. Every id is read from geo_state at run time. One EVIDENCE line per row, one PASS / FAIL
line per cell, the row verdict; a precondition miss ends its row and every later row (cells "not reached"); a boot miss
fails every cell "boot" with ONE CAPTURE line. The test never skips; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_client_base_ghost.py"""

import glob, json, math, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402

KEY_AC = "49213"
KEY_B = "49214"
NAME = "ClientPlayer"
SDLK_END, SDLK_BACKSPACE, SDLK_RETURN = 279, 8, 13
LAND = (harness.LAND_LON, harness.LAND_LAT)
# Three trial boots (six placements each side): the host's first candidate (HOST_LON / HOST_LAT) was off land every time
# and LAND + 0.06 / + 0.06 was accepted; the client's first candidate was always accepted. The client's exit screen
# (server browser or main menu) and the host's CoopState 62 showed at the first poll after the 2 s settle; Profile OKs
# came within 5 s; stable_geo took 5.13 s; the whole run about 80 s.
HOST_CANDS = [(session.HOST_LON, session.HOST_LAT), (LAND[0] + 0.06, LAND[1] + 0.06), (LAND[0] + 0.03, LAND[1] - 0.03),
              LAND]
CLIENT_CANDS = [(LAND[0] - 0.03, LAND[1] - 0.03), (LAND[0] + 0.06, LAND[1] - 0.03), (LAND[0] + 0.06, LAND[1] + 0.06),
                LAND]
STABLE_S, STABLE_TO, LOBBY_EXIT_S, EXIT_S, DROP_S, PROFILE_S, BNB_S, CLIENT_PLACE_WAIT, QUIET, QUIET_EXIT, JOIN_S = (
    5.0, 90.0, 10.0, 10.0, 20.0, 30.0, 120.0, 2.0, 1.5, 2.0, 3.0)
NEEDLES = ("[coop-session]", "COOP_READY", "disconnect", "GoToMainMenu")
CELLS = {"first_campaign": ("first_campaign_host_marker",),
         "lobby_exit": ("lobby_exit_no_old_host_marker", "lobby_exit_only_new_host_marker",
                        "lobby_exit_new_host_marker_shown", "lobby_exit_host_shows_client_base"),
         "abandon_exit": ("abandon_exit_no_old_host_marker", "abandon_exit_only_new_host_marker",
                          "abandon_exit_new_host_marker_shown", "abandon_exit_host_shows_client_base", "no_crash")}
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

def cpu():  # the % Processor Time counter and any foreign game
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
    """place_first_base on each candidate in order until the game accepts one (land), skipping any < 0.02 rad from
    `avoid`"""
    for i, (lon, lat) in enumerate(cands):
        if avoid is not None and math.hypot(lon - avoid[0], lat - avoid[1]) < 0.02:
            continue
        r = q(gc, {"cmd": "place_first_base", "lon": lon, "lat": lat, "name": name})
        ev.setdefault(key, []).append([i, round(lon, 6), round(lat, 6), r.get("ok"), r.get("error")])
        if r.get("ok"):
            return (lon, lat)
    raise Miss("%s: no placement candidate accepted: %s" % (key, ev.get(key)))

def seed_player_name(user_dir):  # the name a player typed in the browser earlier
    for d in (os.path.join(user_dir, "xcom1"), user_dir):
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "player_name.json"), "w", encoding="utf-8") as fh:
            json.dump({"name": NAME}, fh)

def client_exit(host, client, ev, via_lobby):
    """the client's exit by real clicks; its stack (via_lobby: [GoToMainMenuState, ServerList], else [MainMenuState]);
    the host's CoopState 62 (waiting for players); the host's ABANDON (real click) and its main menu"""
    presses = (("GeoscapeState", "options"), ("PauseState", "co-op"), ("LobbyMenu", "disconnect")) if via_lobby else (
        ("GeoscapeState", "options"), ("PauseState", "abandon"), ("AbandonGameState", "yes"))
    for i, (state, match) in enumerate(presses):
        press(client, state, match, ev, match, quiet=QUIET_EXIT if i == 2 else QUIET)
    want, end, s = ((["GoToMainMenuState", "ServerList"] if via_lobby else ["MainMenuState"]),
                    time.time() + (LOBBY_EXIT_S if via_lobby else EXIT_S), None)
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
    """the host's test commands to a SEPARATE lobby on `key`; the client's Direct Connect (after NEW BATTLE > COOP on
    the ordinary route); Profile OKs; START + confirm; the host's placement; the read while placing; the client's
    placement; the read after placing; BEGIN; stable_geo; the read after BEGIN"""
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
    host_spot = place(host, HOST_CANDS, hn, ev, "hostPlace")
    time.sleep(1.0)
    ev["H"] = one_id(host, "after hostPlace")
    wait_state(client, "BuildNewBaseState", BNB_S, "client placement")
    read(host, client, ev, "readWhilePlacing")
    place(client, CLIENT_CANDS, cn, ev, "clientPlace", avoid=host_spot)
    time.sleep(CLIENT_PLACE_WAIT)
    read(host, client, ev, "readAfterPlacing")
    ev["C"] = one_id(client, "after clientPlace")
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
    read(host, client, ev, "readAfterBegin")

def judge(rid, ev, cells, prev, hn, cn):
    H, C = ev["H"], ev["C"]
    ms = [ev[k]["client"]["mir"] for k in ("readWhilePlacing", "readAfterPlacing", "readAfterBegin")]
    det = {"whilePlacing": ms[0], "afterPlacing": ms[1], "afterBegin": ms[2]}
    cells[rid + "_no_old_host_marker"] = (not [m for mm in ms for m in mm if m[1] in prev],
                                          dict(det, forbiddenIds=list(prev)))
    cells[rid + "_only_new_host_marker"] = (len(ms[0]) <= 1 and all(m[1] == H for m in ms[0]) and
                                            ms[1] == [(hn, H)] and ms[2] == [(hn, H)], dict(det, want=[hn, H]))
    cells[rid + "_new_host_marker_shown"] = ((hn, H) in ms[2], {"afterBegin": ms[2], "want": [hn, H]})
    hm = ev["readAfterBegin"]["host"]["mir"]
    cells[rid + "_host_shows_client_base"] = (hm == [(cn, C)], {"hostAfterBegin": hm, "want": [cn, C]})

def distinct(ev, prev):
    if ev["H"] in prev or ev["C"] in prev:
        raise Miss("new campaign ids H %s / C %s not distinct from %s" % (ev["H"], ev["C"], prev))

def row_first_campaign(host, client, ev, cells):
    """the fresh client in its first campaign A: HA, CA and the client's markers after stable_geo"""
    read(host, client, ev, "read")
    IDS["HA"], IDS["CA"] = one_id(host, "first_campaign"), one_id(client, "first_campaign")
    hn, mc = own(ev["read"]["host"]["bases"])[0][0], ev["read"]["client"]["mir"]
    cells["first_campaign_host_marker"] = (mc == [(hn, IDS["HA"])] and IDS["HA"] != IDS["CA"],
                                           {"mirClient": mc, "HA": IDS["HA"], "CA": IDS["CA"], "hostBase": hn})

def row_lobby_exit(host, client, ev, cells):
    """the lobby exit -> campaign B on KEY_B, joined from the server browser the lobby exit leaves on screen"""
    client_exit(host, client, ev, via_lobby=True)
    newcamp(host, client, KEY_B, "HostBaseB", "ClientBaseB", ev, ordinary=False)
    distinct(ev, (IDS["HA"], IDS["CA"]))
    IDS["HB"], IDS["CB"] = ev["H"], ev["C"]
    judge("lobby_exit", ev, cells, (IDS["HA"],), "HostBaseB", "ClientBaseB")

def row_abandon_exit(host, client, ev, cells):
    """the ordinary exit (ABANDON GAME) -> campaign C on KEY_AC hosted again (a new OS port), joined by NEW BATTLE >
    COOP > Direct Connect"""
    client_exit(host, client, ev, via_lobby=False)
    newcamp(host, client, KEY_AC, "HostBaseC", "ClientBaseC", ev, ordinary=True)
    distinct(ev, (IDS["HA"], IDS["HB"], IDS["CA"], IDS["CB"]))
    judge("abandon_exit", ev, cells, (IDS["HB"], IDS["HA"]), "HostBaseC", "ClientBaseC")

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
            ok, det = False, "boot" if name != "no_crash" else "boot; %s" % short(det, 400)
        print(("PASS %s" % name) if ok else ("FAIL %s: %s" % (name, short(det, 1500))), flush=True)
        passed += 1 if ok else 0
    print("ROW %s: %s (%d/%d cells)" % (rid, "PASS" if passed == len(CELLS[rid]) else "FAIL", passed, len(CELLS[rid])), flush=True)
    return [n for n in CELLS[rid] if not (capture is None and cells.get(n, (False,))[0])]

def main():
    T0[0] = time.time()
    cells, evs, capture, crash0 = {}, {}, None, crashes()
    host = GameClient("host", None, make_user_dir("client_base_ghost_host"))
    client = GameClient("client", None, make_user_dir("client_base_ghost_client"))
    games, boot = (host, client), {"cpu": cpu()}
    try:
        try:
            seed_player_name(client.user_dir)
            for gc in games:
                gc.spawn(); gc.connect()
            session.new_campaign(host, client, port=KEY_AC)
            boot["ports"] = dict(harness._EPHEMERAL_COOP_PORTS)
            boot["stableGeo"] = stable_geo(host, client)
        except Exception as e:  # noqa: BLE001
            boot["error"] = unreachable(e)
            capture = {gc.name: dump(gc) for gc in games}
        missed = None
        for rid, body in (("first_campaign", row_first_campaign), ("lobby_exit", row_lobby_exit),
                          ("abandon_exit", row_abandon_exit)):
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
        cells["no_crash"] = (not new and all(alive.values()), {"newCrash": new, "aliveAtEnd": alive, "rc": rc})
    print("BOOT: %s" % short(boot), flush=True)
    if capture is not None:
        print("CAPTURE: %s" % short(capture), flush=True)
    failed = []
    for rid in ("first_campaign", "lobby_exit", "abandon_exit"):
        failed += report(rid, evs.get(rid, {}), cells, capture)
    print("\ntest_client_base_ghost: %d/10 cells passed (fail=%s) wall %.1fs" % (10 - len(failed), failed, time.time() - T0[0]), flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
