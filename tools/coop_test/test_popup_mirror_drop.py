"""W2-H81 stage S-A PMD (spec rewrite/prompts/w2h81_popup_mirror_uaf.md (f); TASK 0 rewrite/w2h81-task0/sa/CONSTANTS.md; ruling R-LH76-1-1;
capture lh76-1-cap F22185-F22188): in a SEPARATE co-op campaign a geoscape popup (UFO detected, destination confirm, target info) keeps a raw
pointer to the partner's UFO mirror. When the partner drops, deleteAllCoopBases deletes every mirror without looking at those popups; after
RESUME the popup is on top again over the freed UFO, and INTERCEPT / OK there close the host's game. The fix closes every popup holding a doomed
mirror right before the delete, as its CANCEL does. Probe popup_mirror_check (read-only pointer compares): holders = popups on the
stack holding a target, dangling = those holding one in no live list, mirror = those holding a live co-op mirror, queued / queuedDangling = the
same for GeoscapeState's queued popups; the drop reds are read under the 62, before the rejoin. Owner = client, holder = host (DC: the
host owns its UFO). Every player press is a real click (globe, INTERCEPT, list rows, the tracker hotkey T, Profile OK, RESUME, CANCEL); levers
stage only (bases, spawn_ufo, the globe centre, the drop = kill). Binding rule: no press on a popup unless its cell's named top shows and pmc
dangling 0 was read right before. Each boot is fresh and shut down before the next; key "49507"; the rejoin is a NEW client (ClientPlayer).
  Boot UD (dirs w2h81_ud_*): the partner drops while the host's UFO-detected popup shows its UFO (D-UD). Cells UD-dangling RED, UD-held RED,
  UD-gone, UD-top RED, UD-alive.
  Boot CD (dirs w2h81_cd_*): ... while the host confirms a craft's destination on its UFO (D-CD). Cells CD-dangling RED, CD-held RED, CD-below,
  CD-top RED, CD-craft, CD-alive.
  Boot TI (dirs w2h81_ti_*): ... while the host's target-info window shows its UFO (D-TI). Cells TI-dangling RED, TI-held RED, TI-top RED, TI-alive.
  Boot DC (dirs w2h81_dc_*): ... while the host's popup shows the host's OWN UFO (the targeting guard). Cells DC-kept, DC-top, DC-cancel.
Red (commit R1): exit 2, RED exactly on UD-dangling, UD-held, UD-top, CD-dangling, CD-held, CD-top, TI-dangling, TI-held, TI-top (9 of 18).
A guard (G:) miss: ONE CAPTURE line and the row's remaining cells FAIL "guard". ONE EVIDENCE line per row, one PASS / FAIL line per cell, the
row verdict; every row runs after a failure; exit 0 only when every cell passes, else 2. one foreground run.
Run: python tools/coop_test/test_popup_mirror_drop.py"""
import json, math, os, sys, time  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY = "49507"
RC_SET = (0, 3221226505, 1, 3221225477)
MIRROR_S, W62_S, ACK_S, W62R_S, RESUME_S, DRAIN2_S = 40, 20, 120, 20, 20, 30
UNDER62_S, SETTLE_DROP, ALIVE_S, ALIVE_DC_S = 1.0, 2.0, 5.0, 10.0
CLIENT_OFFSETS = ((0.25, 0), (-0.25, 0), (0, 0.2), (0, -0.2), (0.2, 0.15), (-0.2, 0.15), (0.2, -0.15), (-0.2, -0.15), (0.3, 0), (-0.3, 0))
UFO = {"type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA", "race": "STR_SECTOID", "trajectory": "P0",
       "state": "flying", "speed": 1}

class Guard(Exception):
    """a guard (G:) missed: the row's remaining cells fail"""

def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]

def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead or gone machine is a value
        return {"error": short(e, 200)}

def alive(gc):
    return gc is not None and gc.proc is not None and gc.proc.poll() is None

def stack(gc):
    return [s.replace("class OpenXcom::", "") for s in q(gc, {"cmd": "get_state"}).get("states", [])] if alive(gc) else None

def top(gc):
    return (stack(gc) or [None])[-1]

def widgets(gc):
    return q(gc, {"cmd": "list_widgets"}).get("widgets", [])

def wait(desc, pred, timeout, interval=0.1):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return round(time.time() - t0, 2)
        time.sleep(interval)
    raise Guard("G: %s: not within %.0f s" % (desc, timeout))

def log_lines(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []

def cpu():
    return harness.cpu_text(harness.cpu_load()["cpu"])

AFF = {}

def note_click(gc, r):
    """the base -> window affine from two click_widget replies (capture lh76.py)"""
    if r.get("ok") and "baseX" in r:
        pts = AFF.setdefault(gc.name + "_pts", [])
        pts.append((r["baseX"], r["baseY"], r["winX"], r["winY"]))
        xs, ys, p0 = [p for p in pts if p[0] != pts[0][0]], [p for p in pts if p[1] != pts[0][1]], pts[0]
        if xs and ys:
            sx, sy = (xs[0][2] - p0[2]) / (xs[0][0] - p0[0]), (ys[0][3] - p0[3]) / (ys[0][1] - p0[1])
            AFF[gc.name] = (sx, p0[2] - sx * p0[0], sy, p0[3] - sy * p0[1])

def click_px(gc, bx, by):
    a = AFF.get(gc.name) or (2.0, 0.0, 2.0, 0.0)
    return q(gc, {"cmd": "inject_input", "kind": "click", "x": int(round(a[0] * bx + a[1])), "y": int(round(a[2] * by + a[3]))})

def press(gc, match, want=None, timeout=15, exact=False):
    """a real click on a visible, shown TextButton whose caption contains (exact: equals) match; then the top state `want`"""
    def shown():
        return any(w.get("visible") and w.get("hidden") is False and (t == match.upper() if exact else match.upper() in t)
                   for w in widgets(gc) if "TextButton" in (w.get("type") or "") for t in [(w.get("text") or "").strip().upper()])
    wait("%s: %r shown" % (gc.name, match), shown, timeout)
    r = q(gc, {"cmd": "click_widget", "match": match})
    note_click(gc, r)
    if not r.get("ok"):
        raise Guard("G: %s click %r: %s" % (gc.name, match, r))
    if want:
        wait("%s top %s after %r" % (gc.name, want, match), lambda: top(gc) == want, timeout)

def pmc(gc):
    r = q(gc, {"cmd": "popup_mirror_check"})
    return {k: r.get(k) for k in ("holders", "dangling", "mirror", "queued", "queuedDangling", "error") if k in r}

def geo(gc):
    return q(gc, {"cmd": "geo_state"})

def ufos(gc):
    return geo(gc).get("ufos", [])

def globe(gc, **kw):
    return q(gc, dict({"cmd": "globe_point"}, **kw))

def mirror_now(gc, coop_id):
    return next((u for u in ufos(gc) if u.get("coop") and u.get("coopId") == coop_id), None)

def own_now(gc, uid):
    return next((u for u in ufos(gc) if u.get("id") == uid and not u.get("coop")), None)

def craft(gc, cid, ctype="STR_INTERCEPTOR"):
    """the host's own craft; craft ids are per craft type (SKYRANGER-1 and INTERCEPTOR-1 are both id 1; CONSTANTS.md)"""
    return next(({k: c.get(k) for k in ("id", "type", "status", "destKind")} for b in geo(gc).get("bases", []) if not b.get("coopIcon")
                 for c in b.get("crafts", []) if c.get("id") == cid and c.get("type") == ctype), None)

def bring_up(row):
    """SEPARATE campaign (the capture's flow) with the client's base placed near the host's -> H, C"""
    tag = "w2h81_" + row.rid.lower()
    row.host = GameClient("host", None, make_user_dir(tag + "_host"))
    row.client = GameClient("client", None, make_user_dir(tag + "_client"))
    host, client = row.host, row.client
    host.spawn(); client.spawn(); host.connect(); client.connect()
    host.ok({"cmd": "open_new_game", "mode": "coop"})
    host.wait_for("difficulty", lambda: session._has_state(host, "NewGameState"))
    host.ok({"cmd": "newgame_ok"})
    host.wait_for("host window", lambda: session._has_state(host, "HostMenu"))
    host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": KEY, "player": "HostPlayer"})
    host.wait_for("host lobby", lambda: session._has_state(host, "LobbyMenu"))
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    client.wait_for("client lobby", lambda: session._has_state(client, "LobbyMenu"), timeout=120)
    for gc in (host, client):
        gc.wait_for("join popup", lambda gc=gc: session._has_state(gc, "Profile"))
        gc.ok({"cmd": "profile_ok"})
    host.wait_for("start eligible", lambda: host.cmd({"cmd": "lobby_state"}).get("startEligible") or None)
    session.start_campaign_via_button(host)
    host.wait_for("host base placement", lambda: session._has_state(host, "BuildNewBaseState"))
    if not host.cmd({"cmd": "place_first_base", "lon": session.HOST_LON, "lat": session.HOST_LAT, "name": "HostBase"}).get("ok"):
        host.ok({"cmd": "place_first_base", "lon": harness.LAND_LON, "lat": harness.LAND_LAT, "name": "HostBase"})
    client.wait_for("client base placement", lambda: session._has_state(client, "BuildNewBaseState"))
    H = next((b["lon"], b["lat"]) for b in geo(host).get("bases", []) if not b.get("coopBase") and not b.get("coopIcon"))
    C = next(((H[0] + dl, H[1] + dt) for dl, dt in CLIENT_OFFSETS if globe(client, lon=H[0] + dl, lat=H[1] + dt).get("land")), None)
    if C is None or not client.cmd({"cmd": "place_first_base", "lon": C[0], "lat": C[1], "name": "ClientBase"}).get("ok"):
        raise Guard("G: client base near H %s: %s" % (H, C))
    host.wait_for("all players placed bases", lambda: host.cmd({"cmd": "has_coop_file", "key": "host_%s_ClientPlayer.data"
                  % host.cmd({"cmd": "save_markers"})["saveID"]}).get("present") or None, timeout=120)
    session.press_back_when_shown(host, "host BEGIN", codes=(60, 62))
    t0, last, tch = time.time(), None, time.time()
    while not (last and last[0][-1:] == last[1][-1:] == ("GeoscapeState",) and time.time() - tch >= 2.0):
        if time.time() - t0 > 90:
            raise Guard("G: both tops GeoscapeState for 2 s: not within 90 s (%s)" % (last,))
        s = (tuple(stack(host) or ()), tuple(stack(client) or ()))
        if s != last:
            last, tch = s, time.time()
        time.sleep(0.1)
    row.ev["H"], row.ev["C"] = [round(v, 5) for v in H], [round(v, 5) for v in C]
    return H, C

def pick_ufo_point(gc, H, C):
    """the capture's ring around H (r 0.13 / 0.16 / 0.11 / 0.19 x 16), 0.1 <= dist(C) <= 0.4"""
    for r in (0.13, 0.16, 0.11, 0.19):
        for k in range(16):
            p = (H[0] + r * math.cos(2 * math.pi * k / 16) / max(0.3, math.cos(H[1])), H[1] + r * math.sin(2 * math.pi * k / 16))
            if 0.1 <= math.hypot((p[0] - C[0]) * math.cos((p[1] + C[1]) / 2), p[1] - C[1]) <= 0.4:  # dist(C)
                return p

def drain_to_geo(gc, timeout=20):
    """real clicks through any popup over the geoscape"""
    t0, clicks = time.time(), []
    while time.time() - t0 < timeout:
        t = top(gc)
        if t == "GeoscapeState":
            return clicks
        caps = [w.get("text") for w in widgets(gc) if "TextButton" in (w.get("type") or "") and w.get("visible") and w.get("hidden") is False]
        for m in ("OK", "CANCEL", "CLOSE"):
            if any(m == (c or "").strip().upper() for c in caps):
                note_click(gc, q(gc, {"cmd": "click_widget", "match": m}))
                clicks.append([t, m])
                break
        time.sleep(0.25)
    raise Guard("G: %s GeoscapeState on top within %d s (%s)" % (gc.name, timeout, stack(gc)))

def calibrate(gc):
    """two real clicks at different x / y measure the window affine (INTERCEPT opens InterceptState, CANCEL closes it)"""
    press(gc, "INTERCEPT", "InterceptState")
    wait("%s InterceptState shown" % gc.name, lambda: not any(w.get("hidden") for w in widgets(gc)), 5)
    press(gc, "CANCEL", "GeoscapeState", exact=True)
    if gc.name not in AFF:
        raise Guard("G: affine not measured on %s: %s" % (gc.name, AFF.get(gc.name + "_pts")))

def stage_ufo(row, owner, holder, H, C):
    """the owner's UFO and its detected mirror on the holder; both back on the geoscape"""
    p = pick_ufo_point(owner, H, C)
    if p is None:
        raise Guard("G: no UFO point")
    su = owner.ok(dict({"cmd": "spawn_ufo", "lon": p[0], "lat": p[1]}, **UFO))
    ou = next(u for u in ufos(owner) if u["id"] == su["ufo_id"] and not u.get("coop"))
    box = {}
    def find_mirror():
        box["m"] = next((u for u in ufos(holder) if u.get("coop") and u.get("coopId") == ou["coopId"] and u.get("detected")), None)
        return box["m"]
    row.ev["mirror s"] = wait("the detected mirror on the %s" % holder.name, find_mirror, MIRROR_S, 0.25)
    row.ev["ufo"] = {"point": [round(v, 5) for v in p], "owner": owner.name, "owner id": ou["id"], "coopId": ou["coopId"], "mirror id": box["m"]["id"]}
    row.ev["drained"] = drain_to_geo(holder) + drain_to_geo(owner)
    time.sleep(1.0)
    row.ev["drained"] += drain_to_geo(holder) + drain_to_geo(owner)
    return ou, box["m"]

def open_uds(row, gc, find):
    """a real globe click on the UFO find() returns -> MultipleTargetsState (one target) -> UfoDetectedState"""
    m = find()
    if m is None:
        raise Guard("G: %s: the UFO to click is gone" % gc.name)
    globe(gc, centerLon=m["lon"], centerLat=m["lat"])  # staging: the player rotates the globe to the UFO
    time.sleep(0.3)
    m = find() or m
    g = globe(gc, lon=m["lon"], lat=m["lat"])
    t0 = time.time()
    click_px(gc, g["x"], g["y"])
    while time.time() - t0 < 5:
        s = stack(gc) or []
        if s and s[-1] in ("UfoDetectedState", "MultipleTargetsState") and time.time() - t0 > 0.5:
            break
        time.sleep(0.02)
    row.ev["globe click"] = [g.get("x"), g.get("y"), stack(gc)]
    if top(gc) != "UfoDetectedState":
        raise Guard("G: %s: no UfoDetectedState after the globe click (%s)" % (gc.name, stack(gc)))

def list_row_click(row, gc, idx, want):
    tl = [w for w in widgets(gc) if (w.get("type") or "").endswith("::TextList")]
    if len(tl) != 1:
        raise Guard("G: %s: one TextList on %s, got %d" % (gc.name, top(gc), len(tl)))
    click_px(gc, tl[0]["x"] + 30, tl[0]["y"] + 8 * idx + 4)
    wait("%s %s after the row click" % (gc.name, want), lambda: top(gc) == want, 5)

def pre(row, gc, want_top, holders, mirror):
    t, c = top(gc), pmc(gc)
    row.ev["pre"] = {"top": t, "pmc": c}
    if t != want_top or c.get("holders") != holders or c.get("dangling") != 0 or c.get("mirror") != mirror:
        raise Guard("G:pre: %s top %s pmc %s; want %s, holders %d, dangling 0, mirror %d" % (gc.name, t, c, want_top, holders, mirror))

def drop(row):
    """the common drop sequence (f): kill the owner (client), read U under the 62, rejoin, RESUME (real), read R"""
    host, ev = row.host, row.ev
    row.client.kill()  # staging: the partner's game drops
    ev["killed client rc"] = row.client.proc.returncode
    ev["62 s"] = wait("G:62 host 62 on top", lambda: q(host, {"cmd": "coop_dialog_info"}).get("code") == 62 and top(host) == "CoopState", W62_S)
    time.sleep(UNDER62_S)
    U = {"pmc": pmc(host), "stack": stack(host), "coop ufos": [u.get("id") for u in ufos(host) if u.get("coop")]}
    ev["U"] = U
    row.client2 = GameClient("client", None, make_user_dir("w2h81_%s_client2" % row.rid.lower()))
    row.client2.spawn(); row.client2.connect()
    row.client2.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    ev["ack s"] = wait("G:ack host resumeAck", lambda: q(host, {"cmd": "get_coop"}).get("resumeAck"), ACK_S, 0.25)
    t1 = time.time()
    while time.time() - t1 < W62R_S and top(host) != "CoopState":
        if "Profile" in (top(host) or ""):
            try:
                press(host, "OK", None, 5)
                ev["profile"] = "OK"
            except Guard:
                ev["profile"] = "profile_ok lever (no OK TextButton shown)"
                q(host, {"cmd": "profile_ok"})
        time.sleep(0.2)
    if top(host) != "CoopState":
        raise Guard("G:62r: host top CoopState within %d s: %s" % (W62R_S, stack(host)))
    press(host, "RESUME", None, W62R_S)
    ev["resume s"] = wait("G:resume host 62 gone", lambda: q(host, {"cmd": "coop_dialog_info"}).get("code") != 62, RESUME_S)
    try:
        ev["client2 drained"] = drain_to_geo(row.client2, DRAIN2_S)
    except Guard as e:
        ev["client2 drained"] = short(e, 200)
    time.sleep(SETTLE_DROP)
    R = {"pmc": pmc(host), "top": top(host)}
    ev["R"] = R
    return U, R

class Row:
    def __init__(self, rid, cells):
        self.rid, self.cells, self.res, self.ev = rid, cells, {}, {}
        self.host = self.client = self.client2 = None
        self.t0, self.cr0 = time.time(), session._crash_log_snapshot()

    def cell(self, name, ok, detail):
        self.res[name] = (bool(ok), detail)

    def guarded_press(self, gc, need_top, match, want, exact=False):
        """the binding test rule: press only with need_top on top and pmc dangling 0 read right before; else no press, False"""
        t, c = top(gc), pmc(gc)
        if t != need_top or c.get("dangling") != 0:
            self.ev.setdefault("no press", []).append([gc.name, match, t, c])
            return False
        press(gc, match, want, exact=exact)
        self.ev.setdefault("pressed", []).append([gc.name, match, want])
        return True

    def alive_cell(self, name, peer, secs, what=""):
        t0 = time.time()
        while time.time() - t0 < secs and alive(self.host) and alive(peer):
            time.sleep(0.25)
        new = sorted(session._crash_log_snapshot() - self.cr0)
        self.cell(name, alive(self.host) and alive(peer) and not new, "%s%.0f s later: host alive %s, %s alive %s, new crash files %s"
                  % (what, secs, alive(self.host), os.path.basename(peer.user_dir), alive(peer), new))

    def capture(self, why):
        """ONE CAPTURE line: every machine's stack, coop dialog, pmc, geo_state ufos and crafts, the last 40 engine log lines"""
        cap = {"why": why}
        for gc in [g for g in (self.host, self.client, self.client2) if g is not None and g.proc is not None]:
            k, g = os.path.basename(gc.user_dir), (geo(gc) if alive(gc) else {})
            cap[k] = {"alive": alive(gc), "rc": gc.proc.poll(), "log tail": log_lines(gc)[-40:]}
            if alive(gc):
                cap[k].update({"stack": stack(gc), "dialog": q(gc, {"cmd": "coop_dialog_info"}), "pmc": pmc(gc),
                               "ufos": [{x: u.get(x) for x in ("id", "coopId", "coop", "status", "detected")} for u in g.get("ufos", [])],
                               "crafts": [{x: c.get(x) for x in ("id", "type", "status", "destKind")} for b in g.get("bases", [])
                                          if not b.get("coopIcon") for c in b.get("crafts", [])]})
        print("CAPTURE %s: %s" % (self.rid, json.dumps(cap, default=str)), flush=True)

    def miss(self, e):
        self.ev["miss"] = short(e, 300)
        self.capture(self.ev["miss"])
        for c in self.cells:
            if c not in self.res:
                self.res[c] = (False, "guard")

    def report(self):
        self.ev["wall s"] = round(time.time() - self.t0, 1)
        print("EVIDENCE %s: %s" % (self.rid, json.dumps(self.ev, sort_keys=True, default=str)), flush=True)
        for c in self.cells:
            ok, d = self.res.get(c, (False, "not reached"))
            print("%s %s: %s" % ("PASS" if ok else "FAIL", c, d), flush=True)
        fails = [c for c in self.cells if not self.res.get(c, (False,))[0]]
        print("ROW %s: %s (%d/%d cells pass)" % (self.rid, "FAIL" if fails else "PASS", len(self.cells) - len(fails), len(self.cells)), flush=True)
        return fails

    def shut(self):
        failed = []
        for gc in [g for g in (self.client2, self.client, self.host) if alive(g)]:
            try:
                gc.shutdown(expected_returncodes=RC_SET)
            except Exception as e:
                print("FAIL %s shutdown: %s" % (os.path.basename(gc.user_dir), short(e, 300)), flush=True)
                failed.append(os.path.basename(gc.user_dir) + " shutdown")
        return failed

def drop_reds(row, U, p):
    row.cell(p + "-dangling", U["pmc"].get("dangling") == 0, "RED: under the 62 pmc dangling %s; want 0" % U["pmc"].get("dangling"))
    row.cell(p + "-held", U["pmc"].get("holders") == 0, "RED: under the 62 pmc holders %s (the popup closed before the delete); want 0"
             % U["pmc"].get("holders"))

def intercept_round(row, p, R):
    """R: top GeoscapeState and dangling 0, then INTERCEPT -> InterceptState -> CANCEL -> GeoscapeState (real); else FAIL "top", no press"""
    host = row.host
    if row.guarded_press(host, "GeoscapeState", "INTERCEPT", "InterceptState") and \
            row.guarded_press(host, "InterceptState", "CANCEL", "GeoscapeState", exact=True):
        row.cell(p + "-top", True, "RED: after RESUME top GeoscapeState, dangling 0; INTERCEPT -> InterceptState -> CANCEL -> GeoscapeState (real)")
    else:
        row.cell(p + "-top", False, "RED: top: after RESUME top %s, pmc %s; want GeoscapeState, dangling 0 (no press)" % (R["top"], R["pmc"]))

def row_ud(row):
    """UD - the partner drops while the host's UFO-detected popup shows its UFO (D-UD)"""
    H, C = bring_up(row)
    host = row.host
    ou, m = stage_ufo(row, row.client, host, H, C)
    calibrate(host)
    open_uds(row, host, lambda: mirror_now(host, m["coopId"]))
    pre(row, host, "UfoDetectedState", 1, 1)
    U, R = drop(row)
    drop_reds(row, U, "UD")
    row.cell("UD-gone", not U["coop ufos"] and U["pmc"].get("queued") == 0 and U["pmc"].get("queuedDangling") == 0,
             "under the 62 host coop ufos %s, pmc queued %s, queuedDangling %s; want none, 0, 0"
             % (U["coop ufos"], U["pmc"].get("queued"), U["pmc"].get("queuedDangling")))
    intercept_round(row, "UD", R)
    row.alive_cell("UD-alive", row.client2, ALIVE_S)

def row_cd(row):
    """CD - the partner drops while the host confirms a craft's destination on its UFO (D-CD)"""
    H, C = bring_up(row)
    host, ev = row.host, row.ev
    ou, m = stage_ufo(row, row.client, host, H, C)
    calibrate(host)
    rows = q(host, {"cmd": "intercept_list"}).get("rows", [])
    idx = next((i for i, r in enumerate(rows) if r.get("type") == "STR_INTERCEPTOR" and r.get("status") == "STR_READY"), None)
    if idx is None:
        raise Guard("G: no ready STR_INTERCEPTOR row: %s" % rows)
    cid = rows[idx].get("craftId")
    ev["interceptor"] = {"row": idx, "CID": cid}
    mm = mirror_now(host, m["coopId"]) or m
    globe(host, centerLon=mm["lon"], centerLat=mm["lat"])  # staging: the player rotates the globe to the UFO
    time.sleep(0.3)
    press(host, "INTERCEPT", "InterceptState")
    wait("host InterceptState shown", lambda: not any(w.get("hidden") for w in widgets(host)), 5)
    list_row_click(row, host, idx, "SelectDestinationState")
    mm = mirror_now(host, m["coopId"]) or mm
    g = globe(host, lon=mm["lon"], lat=mm["lat"])
    click_px(host, g["x"], g["y"])
    try:
        wait("host ConfirmDestinationState", lambda: (stack(host) or [])[-2:] == ["SelectDestinationState", "ConfirmDestinationState"], 5)
    except Guard:
        raise Guard("G:pre: host stack %s; want [..., SelectDestinationState, ConfirmDestinationState] (FIXTURE-STOP)" % stack(host))
    pre(row, host, "ConfirmDestinationState", 1, 1)
    U, R = drop(row)
    drop_reds(row, U, "CD")
    row.cell("CD-below", "SelectDestinationState" in (U["stack"] or []),
             "under the 62 host stack %s; want SelectDestinationState in it" % U["stack"])
    k = craft(host, cid)
    ev["CID after R"] = k
    if row.guarded_press(host, "SelectDestinationState", "CANCEL", "GeoscapeState"):
        row.cell("CD-top", True, "RED: after RESUME top SelectDestinationState, dangling 0; CANCEL -> GeoscapeState (real)")
    else:
        row.cell("CD-top", False, "RED: top: after RESUME top %s, pmc %s; want SelectDestinationState, dangling 0 (no press)"
                 % (R["top"], R["pmc"]))
    row.cell("CD-craft", k is not None and k.get("status") == "STR_READY", "after R CID %s: %s; want status STR_READY" % (cid, k))
    row.alive_cell("CD-alive", row.client2, ALIVE_S)

def row_ti(row):
    """TI - the partner drops while the host's target-info window shows its UFO (D-TI)"""
    H, C = bring_up(row)
    host, ev = row.host, row.ev
    ou, m = stage_ufo(row, row.client, host, H, C)
    calibrate(host)
    g0 = geo(host)
    sites = [s for s in g0.get("missionSites", []) if s.get("detected")]
    U0 = [u for u in g0.get("ufos", []) if u.get("detected") and u.get("status") != 4]
    ui = next((i for i, u in enumerate(U0) if u.get("coop") and u.get("coopId") == m["coopId"]), None)
    if ui is None:
        raise Guard("G: the mirror is not a tracker row: %s" % U0)
    ev["tracker row"] = len(sites) + ui
    q(host, {"cmd": "inject_input", "kind": "key", "key": 116})  # the UFO tracker hotkey T (keyGeoUfoTracker = SDLK_t)
    wait("host UfoTrackerState", lambda: top(host) == "UfoTrackerState", 5)
    wait("host UfoTrackerState shown", lambda: not any(w.get("hidden") for w in widgets(host)), 5)
    list_row_click(row, host, len(sites) + ui, "TargetInfoState")
    pre(row, host, "TargetInfoState", 1, 1)
    U, R = drop(row)
    drop_reds(row, U, "TI")
    intercept_round(row, "TI", R)
    row.alive_cell("TI-alive", row.client2, ALIVE_S)

def row_dc(row):
    """DC - the partner drops while the host's popup shows the host's OWN UFO (the targeting guard)"""
    H, C = bring_up(row)
    host = row.host
    ou, m = stage_ufo(row, host, row.client, H, C)
    calibrate(host)
    open_uds(row, host, lambda: own_now(host, ou["id"]))
    pre(row, host, "UfoDetectedState", 1, 0)
    U, R = drop(row)
    c = U["pmc"]
    row.cell("DC-kept", c.get("holders") == 1 and c.get("dangling") == 0 and c.get("mirror") == 0,
             "under the 62 pmc %s; want holders 1, dangling 0, mirror 0 (the drop closes only popups on the partner's objects)" % c)
    row.cell("DC-top", R["top"] == "UfoDetectedState" and R["pmc"].get("dangling") == 0,
             "after RESUME top %s, pmc %s; want UfoDetectedState, dangling 0" % (R["top"], R["pmc"]))
    if row.guarded_press(host, "UfoDetectedState", "CANCEL", "GeoscapeState", exact=True):
        row.alive_cell("DC-cancel", row.client2, ALIVE_DC_S, "CANCEL -> GeoscapeState (real); ")
    else:
        row.cell("DC-cancel", False, "top: no press (top %s)" % top(host))

def main():
    t0 = time.time()
    print("CPU start: %s" % cpu(), flush=True)
    plan = (("UD", ["UD-dangling", "UD-held", "UD-gone", "UD-top", "UD-alive"], row_ud),
            ("CD", ["CD-dangling", "CD-held", "CD-below", "CD-top", "CD-craft", "CD-alive"], row_cd),
            ("TI", ["TI-dangling", "TI-held", "TI-top", "TI-alive"], row_ti),
            ("DC", ["DC-kept", "DC-top", "DC-cancel"], row_dc))
    fails, shut_fails, total, walls = [], [], 0, {}
    for rid, cells, fn in plan:
        row = Row(rid, cells)
        total += len(cells)
        try:
            fn(row)
        except Exception as e:  # a guard miss ends the row's construction
            row.miss(e)
        finally:
            shut_fails += row.shut()
            fails += row.report()
            walls[rid] = row.ev.get("wall s")
    print("\ntest_popup_mirror_drop: %d/%d cells pass (fail=%s%s) walls %s in %.1fs; CPU end %s" % (
        total - len(fails), total, fails, (" shutdown=%s" % shut_fails) if shut_fails else "", json.dumps(walls), time.time() - t0, cpu()),
        flush=True)
    return 2 if fails or shut_fails or total != 18 else 0

if __name__ == "__main__":
    sys.exit(main())
