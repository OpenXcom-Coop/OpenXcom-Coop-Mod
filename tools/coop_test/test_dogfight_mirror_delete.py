"""W2-H76 stage S-A (spec rewrite/prompts/w2h76_dogfight_ufo_uaf.md (f); TASK 0 rewrite/w2h76-task0/sa/CONSTANTS.md; ruling R-BH4-1; capture
lbh4-cap F21435-F21443; F21582): in a SEPARATE co-op campaign the host can intercept the partner's UFO mirror. Co-op code deletes that mirror when
the partner drops (deleteAllCoopBases) or when the partner's snapshot no longer lists it (the mirror sweep) without ending the dogfight that chases
it, so the next handleDogfights() reads and writes the freed UFO. The fix ends and deletes every dogfight on the mirror first, as vanilla does.
Probes: dogfight_ufo_check (read-only pointer compares, safe after a delete) and its danglingSeen counter (dogfights handleDogfights() met whose
UFO had left the saved game). dogfight_state dereferences every dogfight's UFO: it is read ONLY before a row's delete (lever or kill).
Owner = client, fighter = host in every row. Every player press is a real click; levers stage the UFO, the clock, the globe centre, base placement,
the owner-side loss (set_ufo_damage) and the drop (kill). Each boot is fresh and shut down before the next; key "49449".
  Boot SW (dirs w2h76_sw_*): row SW - the sweep deletes a mirror a minimized dogfight chases (C2-min, no drop). Cells SW-seen RED, SW-end,
  SW-craft, SW-input, SW-common.
  Boot DM (dirs w2h76_dm_*, rejoin w2h76_dm_client2): row DM - the partner drops while a minimized dogfight chases its mirror (C1-min). Cells
  DM-dfs RED, DM-dangling RED, DM-craft RED, DM-home, DM-seen RED, DM-after, DM-input, DM-common.
  Boot DO (dirs w2h76_do_*, rejoin w2h76_do_client2): row DO - as DM with the dogfight window open (C1). Cells DO-dfs RED, DO-dangling RED,
  DO-craft RED, DO-home, DO-seen RED, DO-after, DO-input, DO-common.
Red (commit R1): exit 2, RED exactly on SW-seen, DM-dfs, DM-dangling, DM-craft, DM-seen, DO-dfs, DO-dangling, DO-craft, DO-seen (9 of 21). A guard
miss: ONE CAPTURE line and the row's remaining cells FAIL "guard"; a host crash after the row's delete: they FAIL "crash" (the UAF itself). ONE
EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; every row runs after a failure; exit 0 only when every cell passes, else 2
(WV-D99 / WV-D100). WV-D95: one foreground run per invocation.
Run: python tools/coop_test/test_dogfight_mirror_delete.py
"""
import json, math, os, sys, time  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY = "49449"
RC_SET = (0, 3221226505, 1, 3221225477)
MIRROR_S, OPEN_S, MIN_S, GONE_S, W62_S, ACK_S, W62R_S, RESUME_S = 30, 90, 5, 30, 20, 120, 20, 10
SETTLE_SW, SETTLE_DROP, MIN_HOLD, UNDER62_HOLD = 2.0, 3.0, 1.0, 1.0
MIN_CLICK = (86, 58)  # the only window's (80, 52) + 6 (DogfightState::calculateWindowPosition, one interception); CONSTANTS.md
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


def stack(gc):
    return [s.replace("class OpenXcom::", "") for s in q(gc, {"cmd": "get_state"}).get("states", [])]


def top(gc):
    return (stack(gc) or [None])[-1]


def alive(gc):
    return gc is not None and gc.proc is not None and gc.proc.poll() is None


def widgets(gc):
    r = q(gc, {"cmd": "list_widgets"})
    return r.get("widgets", []), (r.get("state") or "").replace("class OpenXcom::", "")


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
    """the base -> window affine from two click_widget replies (capture lbh4.py)"""
    if r.get("ok") and "baseX" in r:
        pts = AFF.setdefault(gc.name + "_pts", [])
        pts.append((r["baseX"], r["baseY"], r["winX"], r["winY"]))
        xs = [p for p in pts if p[0] != pts[0][0]]
        ys = [p for p in pts if p[1] != pts[0][1]]
        if xs and ys:
            p0 = pts[0]
            sx = (xs[0][2] - p0[2]) / (xs[0][0] - p0[0])
            sy = (ys[0][3] - p0[3]) / (ys[0][1] - p0[1])
            AFF[gc.name] = (sx, p0[2] - sx * p0[0], sy, p0[3] - sy * p0[1])


def aff(gc):
    return AFF.get(gc.name) or (2.0, 0.0, 2.0, 0.0)


def click_px(gc, bx, by):
    a = aff(gc)
    return q(gc, {"cmd": "inject_input", "kind": "click", "x": int(round(a[0] * bx + a[1])), "y": int(round(a[2] * by + a[3]))})


def press(gc, match, want=None, timeout=15):
    """a real click on a visible, shown TextButton whose caption contains match; then the top state `want`"""
    def shown():
        return any(w.get("visible") and w.get("hidden") is False and match.upper() in (w.get("text") or "").upper()
                   for w in widgets(gc)[0] if "TextButton" in (w.get("type") or ""))
    wait("%s: %r shown" % (gc.name, match), shown, timeout)
    r = q(gc, {"cmd": "click_widget", "match": match})
    note_click(gc, r)
    if not r.get("ok"):
        raise Guard("G: %s click %r: %s" % (gc.name, match, r))
    if want:
        wait("%s top %s after %r" % (gc.name, want, match), lambda: top(gc) == want, timeout)
    return r


def geo(gc):
    return q(gc, {"cmd": "geo_state"})


def own_base(gc):
    return next(b for b in geo(gc).get("bases", []) if not b.get("coopBase") and not b.get("coopIcon"))


def ufos(gc):
    return geo(gc).get("ufos", [])


def globe(gc, **kw):
    return q(gc, dict({"cmd": "globe_point"}, **kw))


def dist(a, b):
    return math.hypot((a[0] - b[0]) * math.cos((a[1] + b[1]) / 2), a[1] - b[1])


def chk(gc):
    r = q(gc, {"cmd": "dogfight_ufo_check"})
    return {k: r.get(k) for k in ("count", "pending", "minimized", "dangling", "danglingPending", "danglingSeen", "error") if k in r}


def icpt(gc, cid):
    """the host's own STR_INTERCEPTOR craft with id cid (geo_state)"""
    for b in geo(gc).get("bases", []):
        if not b.get("coopBase") and not b.get("coopIcon"):
            for c in b.get("crafts", []):
                if c.get("type") == "STR_INTERCEPTOR" and c.get("id") == cid:
                    return {k: c.get(k) for k in ("id", "status", "destKind", "inDogfight")}
    return None


def bring_up(row):
    """SEPARATE campaign (session.new_campaign's flow, copied from the capture) with the client's base placed near the host's -> H, C"""
    tag = "w2h76_" + row.rid.lower()
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
    hb = own_base(host)
    H = (hb["lon"], hb["lat"])
    C = next(((H[0] + dl, H[1] + dt) for dl, dt in CLIENT_OFFSETS if globe(client, lon=H[0] + dl, lat=H[1] + dt).get("land")), None)
    if C is None or not client.cmd({"cmd": "place_first_base", "lon": C[0], "lat": C[1], "name": "ClientBase"}).get("ok"):
        raise Guard("G: client base near H %s: %s" % (H, C))
    host.wait_for("all players placed bases",
                  lambda: host.cmd({"cmd": "has_coop_file",
                                    "key": f"host_{host.cmd({'cmd': 'save_markers'})['saveID']}_ClientPlayer.data"}).get("present") or None,
                  timeout=120)
    session.press_back_when_shown(host, "host BEGIN", codes=(60, 62))
    t0, last, tch = time.time(), None, time.time()
    while True:
        s = (tuple(stack(host)), tuple(stack(client)))
        if s != last:
            last, tch = s, time.time()
        if s[0] and s[1] and s[0][-1] == s[1][-1] == "GeoscapeState" and time.time() - tch >= 2.0:
            break
        if time.time() - t0 > 90:
            raise Guard("G: both tops GeoscapeState for 2 s: not within 90 s (%s)" % (s,))
        time.sleep(0.1)
    row.ev["H"], row.ev["C"] = [round(v, 5) for v in H], [round(v, 5) for v in C]
    return H, C


def pick_ufo_point(gc, H, C, want_water=None):
    """the capture's ring around H (r 0.13 / 0.16 / 0.11 / 0.19 x 16), 0.1 <= dist(C) <= 0.4; SW water, DM / DO any"""
    for r in (0.13, 0.16, 0.11, 0.19):
        for k in range(16):
            p = (H[0] + r * math.cos(2 * math.pi * k / 16) / max(0.3, math.cos(H[1])), H[1] + r * math.sin(2 * math.pi * k / 16))
            if dist(p, C) < 0.1 or dist(p, C) > 0.4:
                continue
            land = globe(gc, lon=p[0], lat=p[1]).get("land")
            if want_water is None or (want_water and not land) or (want_water is False and land):
                return p
    return None


def drain_to_geo(gc, timeout=20):
    """real clicks through any popup over the geoscape"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if top(gc) == "GeoscapeState":
            return
        caps = [w.get("text") for w in widgets(gc)[0] if "TextButton" in (w.get("type") or "") and w.get("visible") and w.get("hidden") is False]
        for m in ("OK", "CANCEL", "CLOSE"):
            if any(m == (c or "").strip().upper() for c in caps):
                note_click(gc, q(gc, {"cmd": "click_widget", "match": m}))
                break
        time.sleep(0.25)
    raise Guard("G: %s GeoscapeState on top within %d s (%s)" % (gc.name, timeout, stack(gc)))


def target_mirror(gc, mirror):
    """real clicks: INTERCEPT -> the first ready STR_INTERCEPTOR row -> a globe click on the mirror -> OK; returns the craft id"""
    rows = q(gc, {"cmd": "intercept_list"}).get("rows", [])
    idx = next((i for i, r in enumerate(rows) if r.get("type") == "STR_INTERCEPTOR" and r.get("status") == "STR_READY"), None)
    if idx is None:
        raise Guard("G: no ready STR_INTERCEPTOR row: %s" % rows)
    globe(gc, centerLon=mirror["lon"], centerLat=mirror["lat"])  # staging: the player rotates the globe to the UFO
    time.sleep(0.3)
    press(gc, "INTERCEPT", "InterceptState")
    tl = [w for w in widgets(gc)[0] if (w.get("type") or "").endswith("::TextList")]
    wait("%s InterceptState shown" % gc.name, lambda: not any(w.get("hidden") for w in widgets(gc)[0]), 5)
    if len(tl) != 1:
        raise Guard("G: one TextList on InterceptState, got %d" % len(tl))
    click_px(gc, tl[0]["x"] + 30, tl[0]["y"] + 8 * idx + 4)
    wait("%s SelectDestinationState" % gc.name, lambda: top(gc) == "SelectDestinationState", 5)
    g = globe(gc, lon=mirror["lon"], lat=mirror["lat"])
    click_px(gc, g["x"], g["y"])
    wait("%s ConfirmDestinationState" % gc.name, lambda: top(gc) == "ConfirmDestinationState", 5)
    press(gc, "OK", "GeoscapeState")
    return rows[idx]["craftId"], idx


def stage(row, H, C, want_water, minimize):
    """owner = client, fighter = host: the owner's UFO, its mirror on the host, the host's interceptor in a live dogfight"""
    host, client, ev = row.host, row.client, row.ev
    p = pick_ufo_point(client, H, C, want_water)
    if p is None:
        raise Guard("G: no UFO point")
    su = client.ok(dict({"cmd": "spawn_ufo", "lon": p[0], "lat": p[1]}, **UFO))
    ou = next(u for u in ufos(client) if u["id"] == su["ufo_id"] and not u.get("coop"))
    box = {}

    def find_mirror():
        box["m"] = next((u for u in ufos(host) if u.get("coop") and u.get("coopId") == ou["coopId"]), None)
        return box["m"]
    ev["mirror s"] = wait("the mirror on the host", find_mirror, MIRROR_S, 0.25)
    ev["ufo"] = {"point": [round(v, 5) for v in p], "owner id": ou["id"], "coopId": ou["coopId"], "mirror id": box["m"]["id"]}
    drain_to_geo(host)
    cid, idx = target_mirror(host, box["m"])
    ev["CID"], ev["row idx"] = cid, idx
    for gc in (client, host):
        q(gc, {"cmd": "geo_set_speed", "idx": 1})  # staging: the clock runs (client first)

    def opened():
        d = q(host, {"cmd": "dogfight_state"})  # BEFORE the delete only
        return d.get("count") == 1 and (d.get("dogfights") or [{}])[0].get("updates", 0) >= 1
    ev["open s"] = wait("host dogfight_state count 1 with updates >= 1", opened, OPEN_S, 0.2)
    if minimize:
        click_px(host, *MIN_CLICK)
        ev["min s"] = wait("dogfight minimized", lambda: (q(host, {"cmd": "dogfight_state"}).get("dogfights") or [{}])[0].get("minimized") is True,
                           MIN_S)
        time.sleep(MIN_HOLD)
    c = chk(host)
    ev["chk pre"] = c
    if not (c.get("count") == 1 and c.get("pending") == 0 and c.get("dangling") == 0 and c.get("danglingPending") == 0
            and c.get("minimized") == (1 if minimize else 0)):
        raise Guard("G:pre: chk %s" % c)
    ev["S0"] = c.get("danglingSeen")
    return ou, cid, c.get("danglingSeen")


class Row:
    def __init__(self, rid, cells):
        self.rid, self.cells, self.res, self.ev = rid, cells, {}, {}
        self.host = self.client = self.client2 = None
        self.deleted, self.t0, self.cr0 = False, time.time(), session._crash_log_snapshot()

    def cell(self, name, ok, detail):
        self.res[name] = (bool(ok), detail)

    def capture(self, why):
        cap = {"why": why}
        for gc in (self.host, self.client, self.client2):
            if gc is None or gc.proc is None:
                continue
            k = os.path.basename(gc.user_dir)
            if not alive(gc):
                cap[k] = {"alive": False, "rc": gc.proc.poll(), "log tail": log_lines(gc)[-40:]}
                continue
            g = geo(gc)
            cap[k] = {"stack": stack(gc), "dialog": q(gc, {"cmd": "coop_dialog_info"}), "chk": chk(gc),
                      "ufos": [{x: u.get(x) for x in ("id", "coopId", "coop", "status")} for u in g.get("ufos", [])],
                      "crafts": [{x: c.get(x) for x in ("id", "type", "status", "destKind", "inDogfight")} for b in g.get("bases", [])
                                 if not b.get("coopIcon") for c in b.get("crafts", [])],
                      "log tail": log_lines(gc)[-40:]}
        print("CAPTURE %s: %s" % (self.rid, json.dumps(cap, default=str)), flush=True)

    def miss(self, e):
        crash = self.deleted and self.host is not None and not alive(self.host)
        why = "crash" if crash else "guard"
        self.ev["miss"] = short(e, 300)
        self.capture(self.ev["miss"])
        for c in self.cells:
            if c not in self.res:
                self.res[c] = (False, why)

    def common(self, name, peer):
        new = sorted(session._crash_log_snapshot() - self.cr0)
        self.cell(name, alive(self.host) and alive(peer) and not new,
                  "host alive %s, %s alive %s, new crash files %s" % (alive(self.host), os.path.basename(peer.user_dir), alive(peer), new))

    def report(self):
        self.ev["wall s"] = round(time.time() - self.t0, 1)
        print("EVIDENCE %s: %s" % (self.rid, json.dumps(self.ev, sort_keys=True, default=str)), flush=True)
        for c in self.cells:
            ok, d = self.res.get(c, (False, "not reached"))
            print("%s %s: %s" % ("PASS" if ok else "FAIL", c, d), flush=True)
        fails = [c for c in self.cells if not self.res.get(c, (False,))[0]]
        print("ROW %s: %s (%d/%d cells pass)" % (self.rid, "PASS" if not fails else "FAIL", len(self.cells) - len(fails), len(self.cells)),
              flush=True)
        return fails

    def shut(self):
        failed = []
        for gc in (self.client2, self.client, self.host):
            if gc is None or gc.proc is None or gc.proc.poll() is not None:
                continue
            try:
                gc.shutdown(expected_returncodes=RC_SET)
            except Exception as e:
                print("FAIL %s shutdown: %s" % (os.path.basename(gc.user_dir), short(e, 300)), flush=True)
                failed.append(os.path.basename(gc.user_dir) + " shutdown")
        return failed


def row_sw(row):
    """SW - the sweep deletes a mirror a minimized dogfight chases (C2-min, no drop)"""
    H, C = bring_up(row)
    host, client, ev = row.host, row.client, row.ev
    ou, cid, s0 = stage(row, H, C, True, True)
    r = client.cmd({"cmd": "set_ufo_damage", "ufo_id": ou["id"], "damage": 1000000})  # staging: the owner loses its UFO
    row.deleted = True
    ev["lever"] = {k: r.get(k) for k in ("ok", "status", "damage", "damageMax", "error")}
    if not (r.get("ok") and r.get("status") == 3):
        raise Guard("G:lever: %s" % r)
    ev["gone s"] = wait("the host's mirror gone", lambda: not any(u.get("coop") and u.get("coopId") == ou["coopId"] for u in ufos(host)),
                        GONE_S, 0.1)
    time.sleep(SETTLE_SW)
    c, k = chk(host), icpt(host, cid)
    ev["chk"], ev["icpt"] = c, k
    seen = (c.get("danglingSeen") or 0) - (s0 or 0)
    row.cell("SW-seen", seen == 0, "RED: danglingSeen - S0 = %d (S0 %s, now %s); want 0" % (seen, s0, c.get("danglingSeen")))
    row.cell("SW-end", c.get("count") == 0 and c.get("pending") == 0 and c.get("dangling") == 0 and c.get("danglingPending") == 0,
             "chk %s; want count 0, pending 0, dangling 0, danglingPending 0" % c)
    row.cell("SW-craft", k is not None and k.get("destKind") == "base" and k.get("inDogfight") is False,
             "CID %s: %s; want destKind base, inDogfight false" % (cid, k))
    ev["stack before input"] = stack(host)
    press(host, "INTERCEPT", "InterceptState")
    press(host, "CANCEL", "GeoscapeState")
    row.cell("SW-input", True, "host INTERCEPT -> InterceptState -> CANCEL -> GeoscapeState (real clicks)")
    row.common("SW-common", client)


def row_drop(row, minimize):
    """DM / DO - the partner drops while a minimized (DM) / open (DO) dogfight chases its mirror (C1-min / C1)"""
    H, C = bring_up(row)
    host, client, ev, p = row.host, row.client, row.ev, row.rid
    ou, cid, s0 = stage(row, H, C, None, minimize)
    client.kill()  # staging: the partner's game drops
    row.deleted = True
    ev["killed client rc"] = client.proc.returncode
    ev["62 s"] = wait("host 62 on top", lambda: q(host, {"cmd": "coop_dialog_info"}).get("code") == 62 and top(host) == "CoopState", W62_S)
    time.sleep(UNDER62_HOLD)
    c, k = chk(host), icpt(host, cid)
    left = [u for u in ufos(host) if u.get("coop")]
    ev["under 62"] = {"chk": c, "icpt": k, "coop ufos": len(left)}
    if left:
        raise Guard("G: no coop UFO on the host under the 62: %s" % left)
    row.cell(p + "-dfs", c.get("count") == 0 and c.get("pending") == 0, "RED: under the 62 chk count %s, pending %s; want 0, 0"
             % (c.get("count"), c.get("pending")))
    row.cell(p + "-dangling", c.get("dangling") == 0 and c.get("danglingPending") == 0,
             "RED: under the 62 chk dangling %s, danglingPending %s; want 0, 0" % (c.get("dangling"), c.get("danglingPending")))
    row.cell(p + "-craft", k is not None and k.get("inDogfight") is False, "RED: under the 62 CID %s: %s; want inDogfight false" % (cid, k))
    row.cell(p + "-home", k is not None and k.get("destKind") == "base", "under the 62 CID %s destKind %s; want base"
             % (cid, (k or {}).get("destKind")))
    row.client2 = GameClient("client", None, make_user_dir("w2h76_%s_client2" % p.lower()))
    row.client2.spawn(); row.client2.connect()
    row.client2.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    ev["ack s"] = wait("host resumeAck", lambda: q(host, {"cmd": "get_coop"}).get("resumeAck"), ACK_S, 0.25)
    t1 = time.time()
    while time.time() - t1 < W62R_S and top(host) != "CoopState":
        if "Profile" in (top(host) or ""):
            press(host, "OK", None, 5)
            ev["profile OK"] = True
        time.sleep(0.2)
    if top(host) != "CoopState":
        raise Guard("G:62r: host top CoopState within %d s: %s" % (W62R_S, stack(host)))
    press(host, "RESUME", None, W62R_S)
    ev["resume s"] = wait("host top GeoscapeState after RESUME", lambda: top(host) == "GeoscapeState", RESUME_S)
    time.sleep(SETTLE_DROP)
    c = chk(host)
    ev["after RESUME"] = c
    seen = (c.get("danglingSeen") or 0) - (s0 or 0)
    row.cell(p + "-seen", seen == 0, "RED: after RESUME + %.0f s danglingSeen - S0 = %d (S0 %s, now %s); want 0"
             % (SETTLE_DROP, seen, s0, c.get("danglingSeen")))
    row.cell(p + "-after", c.get("count") == 0 and c.get("pending") == 0 and c.get("dangling") == 0,
             "after RESUME chk %s; want count 0, pending 0, dangling 0" % c)
    press(host, "INTERCEPT", "InterceptState")
    press(host, "CANCEL", "GeoscapeState")
    row.cell(p + "-input", True, "host INTERCEPT -> InterceptState -> CANCEL -> GeoscapeState (real clicks)")
    row.common(p + "-common", row.client2)


def main():
    t0 = time.time()
    print("CPU start: %s" % cpu(), flush=True)
    plan = (("SW", ["SW-seen", "SW-end", "SW-craft", "SW-input", "SW-common"], lambda r: row_sw(r)),
            ("DM", ["DM-dfs", "DM-dangling", "DM-craft", "DM-home", "DM-seen", "DM-after", "DM-input", "DM-common"], lambda r: row_drop(r, True)),
            ("DO", ["DO-dfs", "DO-dangling", "DO-craft", "DO-home", "DO-seen", "DO-after", "DO-input", "DO-common"], lambda r: row_drop(r, False)))
    fails, shut_fails, total, walls = [], [], 0, {}
    for rid, cells, fn in plan:
        row = Row(rid, cells)
        total += len(cells)
        try:
            fn(row)
        except Exception as e:  # a guard miss (or a crash after the delete) ends the row's construction
            row.miss(e)
        finally:
            shut_fails += row.shut()
            fails += row.report()
            walls[rid] = row.ev.get("wall s")
    print("\ntest_dogfight_mirror_delete: %d/%d cells pass (fail=%s%s) walls %s in %.1fs; CPU end %s" % (
        total - len(fails), total, fails, (" shutdown=%s" % shut_fails) if shut_fails else "", json.dumps(walls), time.time() - t0, cpu()),
        flush=True)
    return 2 if fails or shut_fails or total != 21 else 0


if __name__ == "__main__":
    sys.exit(main())
