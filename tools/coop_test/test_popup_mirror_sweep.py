"""In a SEPARATE co-op campaign the client's mirror sweep deletes the host's UFO mirror under the client's open
UFO-detected popup when the host's snapshot no longer lists it; INTERCEPT / CENTRE there would read the freed UFO. The
fix closes the popup right before the delete, as its CANCEL does. Probe popup_mirror_check as in
test_popup_mirror_drop.py. Owner = host, holder = client; test commands only stage (bases, spawn_ufo, the globe centre,
geo_set_speed 1 on both, set_ufo_damage on the host); every player press is a real click and is made only with its
cell's named top shown and pmc dangling 0 read right before. Fresh boots, each shut down before the next; key "49508".
  Boot early_loss (dirs popup_mirror_sweep_early_loss_*): the host loses its UFO 0.2 s after the client's popup shows
  (inside the host's 1000 ms grace): the sweep deletes the mirror under it. Cells early_loss-dangling (fix),
  early_loss-held (fix), early_loss-top (fix), early_loss-alive.
  Boot late_loss (dirs popup_mirror_sweep_late_loss_*): the loss 3.0 s after (outside the grace): no sweep while the
  popup is open; after CANCEL the mirror goes. Cells late_loss-held, late_loss-after, late_loss-alive.
Without the fix: exit 2, failing exactly early_loss-dangling, early_loss-held, early_loss-top (3 of 7). A guard cell
miss: ONE CAPTURE line, the row's remaining cells FAIL "guard". ONE EVIDENCE line per row, one PASS / FAIL line per
cell, the row verdict; every row runs after a failure; exit 0 only when every cell passes, else 2. One foreground run.
Run: python tools/coop_test/test_popup_mirror_sweep.py"""
import json, math, os, sys, time  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY = "49508"
RC_SET = (0, 3221226505, 1, 3221225477)
MIRROR_S, GONE_EARLY_S, SETTLE_EARLY, ALIVE_S, LATE_HOLD_S, LATE_GONE_S, EARLY_DELAY, LATE_DELAY = (
    40, 10, 1.0, 5.0, 10.0, 6.0, 0.2, 3.0)
CLIENT_OFFSETS = ((0.25, 0), (-0.25, 0), (0, 0.2), (0, -0.2), (0.2, 0.15), (-0.2, 0.15), (0.2, -0.15), (-0.2, -0.15), (0.3, 0), (-0.3, 0))
UFO = {"type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA", "race": "STR_SECTOID", "trajectory": "P0",
       "state": "flying", "speed": 1}

class Guard(Exception):
    """a guard cell missed: the row's remaining cells fail"""

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
    raise Guard("guard: %s: not within %.0f s" % (desc, timeout))

def log_lines(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []

def cpu():
    return harness.cpu_text(harness.cpu_load()["cpu"])

AFF = {}

def note_click(gc, r):
    """the base -> window affine from two click_widget replies"""
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
        raise Guard("guard: %s click %r: %s" % (gc.name, match, r))
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

def bring_up(row):
    """SEPARATE campaign with the client's base placed near the host's -> H, C"""
    tag = "popup_mirror_sweep_" + row.rid.lower()
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
        raise Guard("guard: client base near H %s: %s" % (H, C))
    host.wait_for("all players placed bases", lambda: host.cmd({"cmd": "has_coop_file", "key": "host_%s_ClientPlayer.data"
                  % host.cmd({"cmd": "save_markers"})["saveID"]}).get("present") or None, timeout=120)
    session.press_back_when_shown(host, "host BEGIN", codes=(60, 62))
    t0, last, tch = time.time(), None, time.time()
    while not (last and last[0][-1:] == last[1][-1:] == ("GeoscapeState",) and time.time() - tch >= 2.0):
        if time.time() - t0 > 90:
            raise Guard("guard: both tops GeoscapeState for 2 s: not within 90 s (%s)" % (last,))
        s = (tuple(stack(host) or ()), tuple(stack(client) or ()))
        if s != last:
            last, tch = s, time.time()
        time.sleep(0.1)
    row.ev["H"], row.ev["C"] = [round(v, 5) for v in H], [round(v, 5) for v in C]
    return H, C

def pick_ufo_point(gc, H, C):
    """a ring around H (r 0.13 / 0.16 / 0.11 / 0.19 x 16), 0.1 <= dist(C) <= 0.4"""
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
    raise Guard("guard: %s GeoscapeState on top within %d s (%s)" % (gc.name, timeout, stack(gc)))

def calibrate(gc):
    """two real clicks at different x / y measure the window affine (INTERCEPT opens InterceptState, CANCEL closes it)"""
    press(gc, "INTERCEPT", "InterceptState")
    wait("%s InterceptState shown" % gc.name, lambda: not any(w.get("hidden") for w in widgets(gc)), 5)
    press(gc, "CANCEL", "GeoscapeState", exact=True)
    if gc.name not in AFF:
        raise Guard("guard: affine not measured on %s: %s" % (gc.name, AFF.get(gc.name + "_pts")))

def stage_ufo(row, owner, holder, H, C):
    """the owner's UFO and its detected mirror on the holder; both back on the geoscape"""
    p = pick_ufo_point(owner, H, C)
    if p is None:
        raise Guard("guard: no UFO point")
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
        raise Guard("guard: %s: the UFO to click is gone" % gc.name)
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
        raise Guard("guard: %s: no UfoDetectedState after the globe click (%s)" % (gc.name, stack(gc)))
    return time.time()

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

def sweep_stage(row, delay):
    """owner = host, holder = client: both clocks run; the client's popup on the mirror; at t_up + delay the owner
    loses it"""
    H, C = bring_up(row)
    host, client, ev = row.host, row.client, row.ev
    ou, m = stage_ufo(row, host, client, H, C)
    ev["speed"] = [q(gc, {"cmd": "geo_set_speed", "idx": 1}).get("ok") for gc in (host, client)]  # staging: a running clock on both
    calibrate(client)
    time.sleep(1.5)  # the client back on its geoscape long enough for the host's grace to reset
    t_up = open_uds(row, client, lambda: mirror_now(client, m["coopId"]))
    time.sleep(max(0.0, t_up + delay - time.time()))
    ev["damage at +s"] = round(time.time() - t_up, 3)
    r = host.cmd({"cmd": "set_ufo_damage", "ufo_id": ou["id"], "damage": 1000000})  # staging: the owner loses its UFO
    ev["damage reply"] = {k: r.get(k) for k in ("ok", "status", "damage", "damageMax", "error")}
    if not (r.get("ok") and r.get("status") == 3):
        raise Guard("guard:damage: %s" % r)
    return ou

def row_early_loss(row):
    """early_loss - the client's sweep deletes the mirror under its own UFO-detected popup"""
    ou = sweep_stage(row, EARLY_DELAY)
    client, ev = row.client, row.ev
    ev["gone s"] = wait("guard:gone the client's mirror gone", lambda: mirror_now(client, ou["coopId"]) is None,
                        GONE_EARLY_S)
    time.sleep(SETTLE_EARLY)
    S = {"pmc": pmc(client), "top": top(client), "host top": top(row.host)}
    ev["S"] = S
    row.cell("early_loss-dangling", S["pmc"].get("dangling") == 0,
             "after the sweep pmc dangling %s; want 0" % S["pmc"].get("dangling"))
    row.cell("early_loss-held", S["pmc"].get("holders") == 0,
             "after the sweep pmc holders %s (the popup closed before the delete); want 0" % S["pmc"].get("holders"))
    if row.guarded_press(client, "GeoscapeState", "INTERCEPT", "InterceptState") and \
            row.guarded_press(client, "InterceptState", "CANCEL", "GeoscapeState", exact=True):
        row.cell("early_loss-top", True,
                 "after the sweep top GeoscapeState, dangling 0; INTERCEPT -> InterceptState -> CANCEL -> "
                 "GeoscapeState (real)")
    else:
        row.cell("early_loss-top", False,
                 "top: after the sweep top %s, pmc %s; want GeoscapeState, dangling 0 (no press)"
                 % (S["top"], S["pmc"]))
    row.alive_cell("early_loss-alive", client, ALIVE_S)

def row_late_loss(row):
    """late_loss - the popup opened 3 s before the host's UFO is lost: no sweep until it closes"""
    ou = sweep_stage(row, LATE_DELAY)
    client, ev = row.client, row.ev
    samples, t0 = [], time.time()
    while time.time() - t0 < LATE_HOLD_S:
        samples.append([round(time.time() - t0, 2), mirror_now(client, ou["coopId"]) is not None, top(client)])
        time.sleep(0.25)
    bad, n = [s for s in samples if not s[1] or s[2] != "UfoDetectedState"], len(samples)
    end = pmc(client)
    ev["hold"] = {"samples": n, "off": bad[:5], "end pmc": end}
    row.cell("late_loss-held", not bad and end.get("holders") == 1 and end.get("dangling") == 0
             and end.get("mirror") == 1,
             "%d hold samples, %d off (mirror absent or top not UfoDetectedState) %s; end pmc %s; want 0 off, holders 1, dangling 0, mirror 1"
             % (n, len(bad), bad[:3], end))
    if row.guarded_press(client, "UfoDetectedState", "CANCEL", "GeoscapeState", exact=True):
        t1 = time.time()
        while time.time() - t1 < LATE_GONE_S and mirror_now(client, ou["coopId"]) is not None:
            time.sleep(0.1)
        ev["gone after CANCEL s"] = None if mirror_now(client, ou["coopId"]) is not None else round(time.time() - t1, 2)
        after = pmc(client)
        ev["after CANCEL"] = after
        row.cell("late_loss-after", ev["gone after CANCEL s"] is not None and after.get("holders") == 0
                 and after.get("dangling") == 0,
                 "after CANCEL (real) mirror gone in %s s; pmc %s; want gone within %.0f s (the sweep ran with the globe on top), holders 0, "
                 "dangling 0" % (ev["gone after CANCEL s"], after, LATE_GONE_S))
    else:
        row.cell("late_loss-after", False, "top: no press (top %s)" % top(client))
    row.alive_cell("late_loss-alive", client, ALIVE_S)

def main():
    t0 = time.time()
    print("CPU start: %s" % cpu(), flush=True)
    plan = (("early_loss", ["early_loss-dangling", "early_loss-held", "early_loss-top", "early_loss-alive"],
             row_early_loss),
            ("late_loss", ["late_loss-held", "late_loss-after", "late_loss-alive"], row_late_loss))
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
    print("\ntest_popup_mirror_sweep: %d/%d cells pass (fail=%s%s) walls %s in %.1fs; CPU end %s" % (
        total - len(fails), total, fails, (" shutdown=%s" % shut_fails) if shut_fails else "", json.dumps(walls), time.time() - t0, cpu()),
        flush=True)
    return 2 if fails or shut_fails or total != 7 else 0

if __name__ == "__main__":
    sys.exit(main())
