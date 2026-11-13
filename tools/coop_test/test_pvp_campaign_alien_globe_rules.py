"""PvP campaign: what the alien player's globe shows, checked on the machine that runs the world.

The host plays X-COM and the client plays the aliens (game mode 2). Every input and every read is on the HOST:
the alien_view test command shows the host's Geoscape as the alien player sees it (process-wide, never saved),
so each rule is checked against the world it reads, with X-COM's real detection flags beside it.

The rules, with the view on:
  every UFO and every mission site is drawn and can be clicked, X-COM's detection or not; a UFO's window shows
  the hyper-wave details, and a click never gives a UFO its number (only X-COM's detection does);
  every alien base is drawn, found by X-COM or not;
  an X-COM base is drawn once a UFO has found it (its retaliation-target flag); its window offers Cancel only and
  lists no craft;
  an X-COM craft in flight is drawn while it is inside a UFO's radar range or an alien base's detection range; its
  window has no orders; its route is never drawn;
  each rule has its own switch (alien activity, X-COM sightings, alien bases).
The view is draw-only: no row changes a detection flag, a UFO number or the base flag.

Cells (one line per assertion; "off" lines are the controls with the view off):
  ufo_every, ufo_details, site_every, alien_base_every, xcom_base_found, xcom_base_window, craft_range,
  craft_window, switches, routes_hidden, world_unchanged (after every row).

Staging, all on the host. P is the antipode of the X-COM base XB. U1 (an undetected UFO) at P, AB1 (an alien
base X-COM has not found) and AB2 (a found one) 2,000 nm from P, U3 (a UFO X-COM has detected, without hyper-wave
details) inside XB's radar, so X-COM keeps tracking it. Three X-COM craft are parked in flight: A inside U3's
radar range, C inside AB1's detection range and B where nothing sees it. mods/Coop_AlienBaseRadar_Test (both
machines) gives alien bases a 600 nm range (stock alien bases have none) and takes the starting craft's alien base
sight away, so a parked craft never finds AB1. X-COM detects every mission site at the next game hour, so the
rows that need an undetected site spawn S1 (2,000 nm from P) themselves, early enough in the hour, and run last.

Run:  py -3 tools/coop_test/test_pvp_campaign_alien_globe_rules.py
Exit 0 = pass; 1 = failure.
"""

import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from harness import GameClient, make_user_dir
import geo
import pvp_fixture
import session

MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_AlienBaseRadar_Test")
LAYOUT = "host_xcom"
KEY = "53281"
BASE = "XcomBase"  # the X-COM player's first base (pvp_fixture)
SEED = 241
EVENT_PUSH_MIN = 60 * 24 * 90  # pending Geoscape events wait 90 days: past the end of the run

UFO = dict(type="STR_SMALL_SCOUT", mission="STR_ALIEN_RESEARCH", region="STR_NORTH_AMERICA",
           race="STR_SECTOID", trajectory="P0", state="flying", speed=1)
SITE = dict(mission="STR_ALIEN_TERROR", deployment="STR_TERROR_MISSION", race="STR_SECTOID", hours=240,
            detected=False)
RACE = "STR_SECTOID"

FAR_NM = 2000      # U1's neighbours from P
U3_NM = 900        # U3 from XB: inside its radar (stock small radar 1,695 nm)
CRAFT_C_NM = 300   # craft C from AB1 (its detection range is 600 nm)
STEP_NM = 500      # a placement that misses its precondition moves this far along its bearing
STEP_MAX = 4

SYM_PLUS = 43      # the zoom-in key
ZOOM_MIN = 3
OPEN_S = 5.0       # a window opening after a click
NOTHING_S = 1.5    # a click that must open nothing is watched this long
POLL_S = 0.05
SITE_MARGIN_MIN = 15  # a row that needs an undetected site starts at least this many game minutes before the hour


def dest(lon, lat, nm, bearing_deg):
    """The point `nm` nautical miles from (lon, lat) along a great circle at `bearing_deg` (radians in and out)."""
    d = nm / 60.0 * math.pi / 180.0
    b = math.radians(bearing_deg)
    lat2 = math.asin(math.sin(lat) * math.cos(d) + math.cos(lat) * math.sin(d) * math.cos(b))
    lon2 = lon + math.atan2(math.sin(b) * math.sin(d) * math.cos(lat), math.cos(d) - math.sin(lat) * math.sin(lat2))
    return lon2, lat2


def dist_nm(a, b):
    (lon1, lat1), (lon2, lat2) = a, b
    h = (math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * math.asin(min(1.0, math.sqrt(h))) * 180.0 / math.pi * 60.0


def stack(gc):
    return [s.split("::")[-1] for s in session.states(gc)]


def top(gc):
    st = stack(gc)
    return st[-1] if st else ""


def wait(pred, timeout, interval=POLL_S):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v
        time.sleep(interval)


def u3_point(xb, p):
    """U3 sits inside XB's radar: X-COM keeps tracking it while the rows run."""
    return dest(xb[0], xb[1], U3_NM, 90)


class Stop(Exception):
    pass


class AlienGlobe:
    def __init__(self):
        self.host = GameClient("host", None, make_user_dir("pvp_alien_globe_host", mods=[MOD_DIR]))
        self.client = GameClient("client", None, make_user_dir("pvp_alien_globe_client", mods=[MOD_DIR]))
        self.fails = []
        self.sc = None
        self.obj = {}       # name -> spawn record
        self.crafts = {}    # "A" / "B" / "C" -> {"type", "id", "lon", "lat"}
        self.xb = None
        self.xb_flag = False
        self.site_hour = None

    # ---- output ---------------------------------------------------------------------------

    def check(self, cell, label, cond, values=""):
        verdict = "PASS" if cond else "FAIL"
        line = f"{verdict} {LAYOUT} {cell}: {label}" + (f" ({values})" if values != "" else "")
        print(line, flush=True)
        if not cond:
            self.fails.append(line)

    def evidence(self, msg):
        print(f"EVIDENCE {LAYOUT} {msg}", flush=True)

    # ---- probes ---------------------------------------------------------------------------

    def view(self, **kw):
        return self.host.ok({"cmd": "alien_view", **kw})

    def gv(self):
        return self.host.ok({"cmd": "globe_view"})

    @staticmethod
    def ufo(g, uid):
        return next((u for u in g["ufos"] if u["uniqueId"] == uid), None)

    @staticmethod
    def site(g, sid):
        return next((s for s in g["sites"] if s["id"] == sid), None)

    @staticmethod
    def alien_base(g, aid):
        return next((a for a in g["alienBases"] if a["id"] == aid), None)

    @staticmethod
    def xbase(g):
        return next((b for b in g["xcomBases"] if b["name"] == BASE), None)

    def craft(self, g, key):
        c = self.crafts[key]
        return next((k for k in g["crafts"] if k["type"] == c["type"] and k["id"] == c["id"]), None)

    def drawn(self, g, kind, key):
        rec = {"ufo": lambda: self.ufo(g, self.obj[key]["uniqueId"]),
               "site": lambda: self.site(g, self.obj[key]["id"]),
               "alienBase": lambda: self.alien_base(g, self.obj[key]["id"]),
               "xcomBase": lambda: self.xbase(g),
               "craft": lambda: self.craft(g, key)}[kind]()
        return None if rec is None else rec.get("drawn")

    # ---- screens --------------------------------------------------------------------------

    def to_geo(self, label):
        """Close whatever popup is on the host's Geoscape (logged)."""
        for _ in range(12):
            t = top(self.host)
            if t == "GeoscapeState":
                return True
            self.evidence(f"{label}: closing {t} on the host")
            for caption in ("CANCEL", "OK"):
                if session.wait_widget_ready(self.host, caption, timeout=0.5) is not None:
                    self.host.cmd({"cmd": "click_widget", "match": caption})
                    break
            else:
                self.host.cmd({"cmd": "dismiss_popup"})
            wait(lambda: top(self.host) != t, 2.0)
        return top(self.host) == "GeoscapeState"

    def close(self, caption):
        session.click_widget_ready(self.host, caption, timeout=OPEN_S)
        if not wait(lambda: top(self.host) == "GeoscapeState", OPEN_S):
            self.to_geo(f"after {caption}")

    def scale(self):
        """INTERCEPT -> CANCEL: the window affine for injected globe clicks."""
        def cw(match):
            session.wait_widget_ready(self.host, match, timeout=OPEN_S)
            r = self.host.cmd({"cmd": "click_widget", "match": match})
            return {"base": [r.get("baseX"), r.get("baseY")], "win": [r.get("winX"), r.get("winY")]}
        a = cw("INTERCEPT")
        wait(lambda: top(self.host) == "InterceptState", OPEN_S)
        b = cw("CANCEL")
        if not wait(lambda: top(self.host) == "GeoscapeState", OPEN_S):
            self.to_geo("after the scale clicks")
        out = [(a["win"][i] - b["win"][i]) / (a["base"][i] - b["base"][i]) if a["base"][i] != b["base"][i] else None
               for i in (0, 1)]
        s = round(out[0] or out[1], 3)
        self.sc = (s, a["win"][0] - s * a["base"][0], s, a["win"][1] - s * a["base"][1])

    def aim(self, lon, lat):
        """Centre the host's globe on (lon, lat), zoom to ZOOM_MIN; the point's globe pixel."""
        gc = self.host
        gc.ok({"cmd": "globe_point", "centerLon": lon, "centerLat": lat})
        for _ in range(6):
            if (gc.ok({"cmd": "globe_point"}).get("zoom") or 0) >= ZOOM_MIN:
                break
            gc.cmd({"cmd": "inject_input", "kind": "key", "key": SYM_PLUS})
            time.sleep(0.6)
        g = gc.ok({"cmd": "globe_point", "lon": lon, "lat": lat})
        return g["x"], g["y"]

    def inject(self, bx, by):
        s = self.sc
        self.host.cmd({"cmd": "inject_input", "kind": "click", "x": int(round(s[0] * bx + s[1])),
                       "y": int(round(s[2] * by + s[3]))})

    def click(self, lon, lat):
        """A player's click on the marker at (lon, lat): the window it opens ('' = none) and the pixels tried."""
        x, y = self.aim(lon, lat)
        tries = []
        for dx, dy in ((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2)):
            self.inject(x + dx, y + dy)
            opened = wait(lambda: top(self.host) != "GeoscapeState", 1.0)
            tries.append((x + dx, y + dy))
            if opened:
                if top(self.host) == "MultipleTargetsState":
                    self.evidence(f"click at {tries[-1]} opened the target chooser: "
                                  f"{[w.get('text') for w in self.host.ok({'cmd': 'list_widgets'}).get('widgets', []) if w.get('text')]}")
                return top(self.host), tries
        return "", tries

    def click_nothing(self, lon, lat):
        """A click on (lon, lat) that must open nothing: the stack it changed to within NOTHING_S, or None."""
        x, y = self.aim(lon, lat)
        before = stack(self.host)
        self.inject(x, y)
        changed = wait(lambda: stack(self.host) != before, NOTHING_S)
        if changed:
            after = stack(self.host)
            self.to_geo("after a click that should open nothing")
            return after
        return None

    # ---- setup ----------------------------------------------------------------------------

    def bring_up(self):
        print(f"\n--- {LAYOUT}: the host plays X-COM; the host's Geoscape is shown as the alien player sees it ---",
              flush=True)
        self.evidence(f"cpu at boot {harness.cpu_load()}")
        for gc in (self.host, self.client):
            gc.spawn()
            gc.connect()
        gm = pvp_fixture.start_pvp_campaign(self.host, self.client, KEY, alien_player="client")
        if gm != 2:
            raise Stop(f"game mode {gm}, expected 2")
        geo.slow_clock(self.host, self.client)
        for gc in (self.host, self.client):
            gc.ok({"cmd": "set_seed", "seed": SEED})
            for ev in gc.ok({"cmd": "geo_events"}).get("events", []):
                if not ev.get("over"):
                    gc.ok({"cmd": "set_event_countdown", "name": ev["name"], "minutes": EVENT_PUSH_MIN})
        self.to_geo("after the bring-up")
        self.scale()
        self.evidence(f"click affine {self.sc}")

    def place(self, key, start, nm, bearing, want):
        """Park craft `key` in flight `nm` from `start` along `bearing`; if its sighting is not `want`, move on in
        STEP_NM steps (at most STEP_MAX)."""
        c = self.crafts[key]
        for step in range(STEP_MAX + 1):
            lon, lat = dest(start[0], start[1], nm + step * STEP_NM, bearing)
            self.host.ok({"cmd": "place_craft", "base": BASE, "craft_id": c["id"], "craft_type": c["type"],
                          "lon": lon, "lat": lat})
            got = self.craft(self.gv(), key)
            if got and got["sighting"] == want:
                if step:
                    self.evidence(f"craft {key}: {nm} nm missed sighting {want}; moved to {nm + step * STEP_NM} nm")
                c["lon"], c["lat"] = lon, lat
                return got
        raise Stop(f"craft {key}: no point along bearing {bearing} from {start} gives sighting {want} ({got})")

    def stage(self):
        g = self.gv()
        xb = self.xbase(g)
        if not xb:
            raise Stop(f"no {BASE} on the host: {[b['name'] for b in g['xcomBases']]}")
        self.xb = (xb["lon"], xb["lat"])
        if xb["retaliationTarget"]:
            self.host.ok({"cmd": "xcom_base_found", "base": BASE, "on": False})
            self.evidence(f"{BASE} started with its retaliation-target flag on; set off")
        self.xb_flag = False
        p = (self.xb[0] + math.pi, -self.xb[1])
        self.p = p
        points = {"U1": p, "U3": u3_point(self.xb, p), "AB1": dest(p[0], p[1], FAR_NM, 0),
                  "AB2": dest(p[0], p[1], FAR_NM, 180)}
        for name, detected in (("U1", False), ("U3", True)):
            lon, lat = points[name]
            r = self.host.ok({"cmd": "spawn_ufo", **UFO, "detected": detected, "lon": lon, "lat": lat})
            self.obj[name] = {"uniqueId": r["unique_id"], "lon": lon, "lat": lat}
        for name in ("AB1", "AB2"):
            lon, lat = points[name]
            r = self.host.ok({"cmd": "spawn_alien_base", "race": RACE, "lon": lon, "lat": lat})
            self.obj[name] = {"id": r["alien_base_id"], "lon": lon, "lat": lat}
        self.host.ok({"cmd": "host_alien_base_found", "alien_base_id": self.obj["AB2"]["id"]})
        self.to_geo("after the spawns")
        g = self.gv()
        u1, u3 = self.ufo(g, self.obj["U1"]["uniqueId"]), self.ufo(g, self.obj["U3"]["uniqueId"])
        ab1, ab2 = self.alien_base(g, self.obj["AB1"]["id"]), self.alien_base(g, self.obj["AB2"]["id"])
        pre = [("U1 undetected, no details, number 0", u1 and not u1["detected"] and not u1["hyperDetected"] and u1["id"] == 0,
                u1),
               ("U3 detected, no details", u3 and u3["detected"] and not u3["hyperDetected"], u3),
               ("AB1 not found, detection range 600", ab1 and not ab1["discovered"] and ab1["detectionRange"] == 600, ab1),
               ("AB2 found", ab2 and ab2["discovered"], ab2)]
        for label, ok, rec in pre:
            self.evidence(f"staging: {label}: {'met' if ok else 'NOT MET'} {rec}")
            if not ok:
                raise Stop(f"staging precondition not met: {label}: {rec}")
        self.obj["U3"]["radarRange"] = u3["radarRange"]
        out = [k for k in g["crafts"] if k["base"] == BASE]
        if len(out) < 3:
            raise Stop(f"{BASE} has {len(out)} craft, the rows need 3: {out}")
        # A is the base's first craft: fly_craft (routes_hidden) sends that one
        for key, k in zip(("A", "C", "B"), out):
            self.crafts[key] = {"type": k["type"], "id": k["id"]}
        self.r3 = u3["radarRange"]
        u3p = (self.obj["U3"]["lon"], self.obj["U3"]["lat"])
        a = self.place("A", u3p, 0.5 * self.r3, 0, 1)
        c = self.place("C", (self.obj["AB1"]["lon"], self.obj["AB1"]["lat"]), CRAFT_C_NM, 90, 2)
        b = self.place("B", p, FAR_NM, 45, 0)
        self.evidence(f"staging: XB {self.xb}, P {p}; U3 radar range {self.r3} nm; craft A {self.crafts['A']} "
                      f"sighting {a['sighting']}, C {self.crafts['C']} sighting {c['sighting']}, B {self.crafts['B']} "
                      f"sighting {b['sighting']}")
        self.spawned = {"U1": (False, False), "U3": (True, False), "AB1": False}

    def fresh_site(self):
        """Spawn S1 undetected, at least SITE_MARGIN_MIN game minutes before the hour X-COM would detect it."""
        t_end = time.time() + 120
        while True:
            minute = geo.game_minutes(self.host)
            if minute is not None and 60 - minute % 60 >= SITE_MARGIN_MIN:
                break
            if time.time() > t_end:
                raise Stop(f"the game clock did not reach a fresh hour (minute {minute})")
            time.sleep(0.5)
        self.to_geo("before the site spawn")
        lon, lat = dest(self.p[0], self.p[1], FAR_NM, 270)
        r = self.host.ok({"cmd": "spawn_mission_site", **SITE, "lon": lon, "lat": lat})
        self.obj["S1"] = {"id": r["site_id"], "lon": lon, "lat": lat}
        self.site_hour = minute // 60
        s1 = self.site(self.gv(), r["site_id"])
        self.evidence(f"S1 spawned at game minute {minute % 60} of the hour: {s1}")

    # ---- cells ----------------------------------------------------------------------------

    def world_unchanged(self, after):
        try:
            self._world_unchanged(after)
        except (KeyError, TypeError, Stop) as e:
            self.check("world_unchanged", f"after {after}: probe read", False, repr(e))

    def _world_unchanged(self, after):
        cell = "world_unchanged"
        g = self.gv()
        u1, u3 = self.ufo(g, self.obj["U1"]["uniqueId"]), self.ufo(g, self.obj["U3"]["uniqueId"])
        ab1, xb = self.alien_base(g, self.obj["AB1"]["id"]), self.xbase(g)
        now = {"U1": (u1["detected"], u1["hyperDetected"]), "U3": (u3["detected"], u3["hyperDetected"]),
               "AB1": ab1["discovered"]}
        want = dict(self.spawned)
        if self.site_hour is not None:
            # the row's own site, read in the hour it was spawned in (X-COM detects it at the next one)
            now["S1"] = self.site(g, self.obj["S1"]["id"])["detected"]
            want["S1"] = False
            minute = geo.game_minutes(self.host)
            if minute is None or minute // 60 != self.site_hour:
                raise Stop(f"the game hour passed during a site row (spawned in hour {self.site_hour}, now minute {minute})")
            self.site_hour = None
        ok = now == want and u1["id"] == 0 and xb["retaliationTarget"] == self.xb_flag
        self.check(cell, f"after {after}: flags as spawned, U1 number 0, XB flag as last set",
                   ok, f"flags {now}, U1 number {u1['id']}, XB flag {xb['retaliationTarget']} (set {self.xb_flag})")

    def ufo_every(self):
        cell = "ufo_every"
        self.view(on=True)
        on = self.ufo(self.gv(), self.obj["U1"]["uniqueId"])
        self.view(on=False)
        off = self.ufo(self.gv(), self.obj["U1"]["uniqueId"])
        self.view(on=True)
        self.check(cell, "on: U1 drawn", on["drawn"] is True, on)
        self.check(cell, "off: U1 not drawn", off["drawn"] is False, off)
        self.check(cell, "U1 undetected both times", not on["detected"] and not off["detected"])

    def ufo_window(self, key):
        """Click UFO `key`; (window, the UFO's record after the window closed)."""
        u = self.obj[key]
        opened, tries = self.click(u["lon"], u["lat"])
        win = self.gv()["window"] if opened == "UfoDetectedState" else {"state": opened or "nothing", "tries": tries}
        if opened == "UfoDetectedState":
            self.close("CANCEL")
        elif opened:
            self.to_geo(f"after the click on {key}")
        return win, self.ufo(self.gv(), u["uniqueId"])

    def ufo_details(self):
        cell = "ufo_details"
        self.view(on=True)
        w1, u1 = self.ufo_window("U1")
        self.check(cell, "on: U1's click opens its window with the hyper-wave details",
                   w1.get("state") == "ufo" and w1.get("ufoUniqueId") == self.obj["U1"]["uniqueId"]
                   and w1.get("hyperwave") is True, w1)
        self.check(cell, "U1 keeps number 0 after its window closed", u1["id"] == 0, u1)
        w3, u3 = self.ufo_window("U3")
        self.check(cell, "on: U3's window shows the hyper-wave details",
                   w3.get("state") == "ufo" and w3.get("ufoUniqueId") == self.obj["U3"]["uniqueId"]
                   and w3.get("hyperwave") is True, w3)
        self.view(on=False)
        w3off, u3off = self.ufo_window("U3")
        self.view(on=True)
        self.check(cell, "off: U3's window has no hyper-wave details",
                   w3off.get("state") == "ufo" and w3off.get("hyperwave") is False, w3off)
        self.check(cell, "U1 and U3 never get X-COM's hyper-wave flag",
                   not u1["hyperDetected"] and not u3["hyperDetected"] and not u3off["hyperDetected"])

    def site_every(self):
        cell = "site_every"
        self.fresh_site()
        self.view(on=True)
        on = self.site(self.gv(), self.obj["S1"]["id"])
        self.view(on=False)
        off = self.site(self.gv(), self.obj["S1"]["id"])
        self.view(on=True)
        self.check(cell, "on: S1 drawn", on["drawn"] is True, on)
        self.check(cell, "off: S1 not drawn", off["drawn"] is False, off)
        self.check(cell, "S1 undetected", not on["detected"] and not off["detected"])

    def alien_base_every(self):
        cell = "alien_base_every"
        self.view(on=True)
        g = self.gv()
        on = self.alien_base(g, self.obj["AB1"]["id"])
        opened, tries = self.click(self.obj["AB1"]["lon"], self.obj["AB1"]["lat"])
        if opened == "TargetInfoState":
            self.close("OK")
        elif opened:
            self.to_geo("after the click on AB1")
        after = self.alien_base(self.gv(), self.obj["AB1"]["id"])
        self.view(on=False)
        g = self.gv()
        off1, off2 = self.alien_base(g, self.obj["AB1"]["id"]), self.alien_base(g, self.obj["AB2"]["id"])
        self.view(on=True)
        self.check(cell, "on: AB1 drawn", on["drawn"] is True, on)
        self.check(cell, "on: AB1's click opens its target window", opened == "TargetInfoState",
                   f"opened {opened or 'nothing'}, tries {tries}")
        self.check(cell, "AB1 still not found by X-COM after its window", after["discovered"] is False, after)
        self.check(cell, "off: AB1 not drawn, AB2 drawn", off1["drawn"] is False and off2["drawn"] is True,
                   f"AB1 {off1}, AB2 {off2}")

    def set_found(self, on):
        self.host.ok({"cmd": "xcom_base_found", "base": BASE, "on": on})
        self.xb_flag = on

    def xcom_base_found(self):
        cell = "xcom_base_found"
        self.view(on=True)
        self.set_found(False)
        before = self.xbase(self.gv())
        changed = self.click_nothing(*self.xb)
        self.set_found(True)
        after = self.xbase(self.gv())
        self.check(cell, "flag off: XB not drawn", before["drawn"] is False, before)
        self.check(cell, "flag off: a click on XB's point opens nothing", changed is None,
                   f"stack became {changed}" if changed else f"stack unchanged {NOTHING_S}s")
        self.check(cell, "flag on: XB drawn", after["drawn"] is True, after)

    def xcom_base_window(self):
        cell = "xcom_base_window"
        self.view(on=True)
        self.set_found(True)
        wins = {}
        for mode in ("on", "off"):
            self.view(on=(mode == "on"))
            opened, tries = self.click(*self.xb)
            wins[mode] = self.gv()["window"] if opened == "InterceptState" else {"state": opened or "nothing", "tries": tries}
            if opened == "InterceptState":
                self.close("CANCEL")
            elif opened:
                self.to_geo(f"after the click on XB ({mode})")
        self.view(on=True)
        on, off = wins["on"], wins["off"]
        self.check(cell, "on: XB's window offers Cancel only and lists no craft",
                   on.get("state") == "intercept" and on.get("gotoBase") is False and on.get("crafts") == 0, on)
        self.check(cell, "off: XB's window offers Go to Base and lists its craft",
                   off.get("state") == "intercept" and off.get("gotoBase") is True and (off.get("crafts") or 0) >= 1, off)

    def craft_range(self):
        cell = "craft_range"
        self.view(on=True)
        g = self.gv()
        a, b, c = self.craft(g, "A"), self.craft(g, "B"), self.craft(g, "C")
        u3 = (self.obj["U3"]["lon"], self.obj["U3"]["lat"])
        lon, lat = dest(u3[0], u3[1], 1.5 * self.r3, 0)
        self.host.ok({"cmd": "place_craft", "base": BASE, "craft_id": self.crafts["A"]["id"],
                      "craft_type": self.crafts["A"]["type"], "lon": lon, "lat": lat})
        moved = self.craft(self.gv(), "A")
        self.place("A", u3, 0.5 * self.r3, 0, 1)
        self.check(cell, "A (inside U3's radar range) drawn", a["drawn"] is True, a)
        self.check(cell, "C (inside AB1's detection range) drawn", c["drawn"] is True, c)
        self.check(cell, "B (seen by nothing) not drawn", b["drawn"] is False, b)
        self.check(cell, "A moved to 1.5 x U3's radar range: not drawn, no sighting",
                   moved["drawn"] is False and moved["sighting"] == 0, moved)

    def craft_window(self):
        cell = "craft_window"
        wins = {}
        for mode in ("on", "off"):
            self.view(on=(mode == "on"))
            opened, tries = self.click(self.crafts["A"]["lon"], self.crafts["A"]["lat"])
            if opened == "GeoscapeCraftState":
                wins[mode] = self.host.ok({"cmd": "geoscape_craft_menu_state"})
                self.close("CANCEL")
            else:
                wins[mode] = {"opened": opened or "nothing", "tries": tries}
                if opened:
                    self.to_geo(f"after the click on A ({mode})")
            if mode == "on":
                b_changed = self.click_nothing(self.crafts["B"]["lon"], self.crafts["B"]["lat"])
        self.view(on=True)
        on, off = wins["on"], wins["off"]
        self.check(cell, "on: A's window has no orders", on.get("controlButtonsVisible") is False, on)
        self.check(cell, "on: a click on B's point opens nothing", b_changed is None,
                   f"stack became {b_changed}" if b_changed else f"stack unchanged {NOTHING_S}s")
        self.check(cell, "off: A's window has its orders", off.get("controlButtonsVisible") is True, off)

    def switches(self):
        cell = "switches"
        self.fresh_site()
        self.view(on=True, alienActivity=True, xcomSightings=True, alienBases=True)
        self.set_found(False)
        reads = {}
        for rule in ("alienActivity", "xcomSightings", "alienBases"):
            self.view(**{rule: False})
            g = self.gv()
            self.view(**{rule: True})
            reads[rule] = {"U1": self.drawn(g, "ufo", "U1"), "S1": self.drawn(g, "site", "S1"),
                           "AB1": self.drawn(g, "alienBase", "AB1"), "XB": self.drawn(g, "xcomBase", None),
                           "B": self.drawn(g, "craft", "B")}
        r = reads["alienActivity"]
        self.check(cell, "alien activity off: U1 and S1 not drawn, AB1 drawn, B not drawn",
                   r["U1"] is False and r["S1"] is False and r["AB1"] is True and r["B"] is False, r)
        r = reads["xcomSightings"]
        self.check(cell, "X-COM sightings off (XB flag off): XB and B drawn, U1 drawn",
                   r["XB"] is True and r["B"] is True and r["U1"] is True, r)
        r = reads["alienBases"]
        self.check(cell, "alien bases off: AB1 not drawn, U1 drawn, XB not drawn",
                   r["AB1"] is False and r["U1"] is True and r["XB"] is False, r)

    def routes_hidden(self):
        cell = "routes_hidden"
        self.view(on=True)
        r = self.host.ok({"cmd": "fly_craft", "base": BASE})
        on = self.craft(self.gv(), "A")
        self.view(on=False)
        off = self.craft(self.gv(), "A")
        self.view(on=True)
        self.evidence(f"fly_craft sent craft {r.get('craftId')} on a route")
        self.check(cell, "on: A drawn, its route not drawn", on["drawn"] is True and on["routeDrawn"] is False, on)
        self.check(cell, "off: A's route drawn", off["routeDrawn"] is True, off)

    def run(self):
        self.bring_up()
        self.stage()
        self.world_unchanged("staging")
        for row in (self.ufo_every, self.ufo_details, self.alien_base_every, self.xcom_base_found,
                    self.xcom_base_window, self.craft_range, self.craft_window, self.routes_hidden, self.site_every,
                    self.switches):
            self.to_geo(f"before {row.__name__}")
            try:
                row()
            except (KeyError, TypeError) as e:
                self.check(row.__name__, "row ran", False, repr(e))
                self.to_geo(f"after {row.__name__}")
            self.world_unchanged(row.__name__)


def main():
    t0 = time.time()
    run = AlienGlobe()
    try:
        run.run()
    except Exception as e:  # noqa: BLE001 - reported as the run's failure
        print(f"[ERROR] {LAYOUT}: {e!r}", flush=True)
        run.fails.append(f"{LAYOUT}: {e!r}")
    finally:
        try:
            run.host.cmd({"cmd": "alien_view", "on": False})
        except Exception:  # noqa: BLE001 - the process may be gone
            pass
        try:
            harness.shutdown_clients(run.host, run.client)
        except RuntimeError as e:
            run.fails.append(f"{LAYOUT}: {e}")
    print(f"\n==== PvP campaign alien globe rules summary ({time.time() - t0:.1f}s) ====")
    if run.fails:
        for f in run.fails:
            print(f"  {f}")
        sys.exit(1)
    print("  the alien player's globe shows every UFO, site and alien base, X-COM bases and craft once seen, "
          "and changes nothing in the world")
    sys.exit(0)


if __name__ == "__main__":
    main()
