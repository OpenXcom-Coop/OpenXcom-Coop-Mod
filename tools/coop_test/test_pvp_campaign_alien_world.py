"""PvP campaign, the host plays X-COM and the client plays the aliens (game mode 2): the alien player's machine
holds the host's one world.

The alien client never builds a base of its own. It holds a replica of the host's world: the same bases, UFOs,
mission sites and alien bases (the undetected ones too), the same wallet (shown as $1,000), the same month end. The
host refuses every Geoscape command that comes from the alien player. After a rejoin the alien client again holds
the host's world, and the host's save holds no world of the alien player.

The boot: lobby key 53291, user dirs pvp_alien_world_host / pvp_alien_world_client (pvp_alien_world_rejoin for the
rejoined client). Bring-up: pvp_fixture.start_pvp_campaign(alien_player="client"); crash baseline; geo.slow_clock.
A bring-up miss prints ONE "CAPTURE boot:" line and FAILs every cell "boot".

Rows and cells (one PASS / FAIL line per cell, one EVIDENCE line per row; every row runs after a failure, a row whose
precondition was never reached FAILs its cells "blocked: <why>"):
  start      start_side (coop_sides: one world, game mode 2, the client plays the aliens), start_replica (the client is a
             replica holding exactly the host's bases, every base named for the X-COM player), start_checksum (world
             checksums equal), start_funds (the client is shown $1,000 and holds the host's wallet).
  objects    the host spawns an undetected UFO, an undetected terror site and two alien bases (one found):
             objects_ufos, objects_sites, objects_alien_bases (each host object on the client once, with the host's
             ids, as a real object, not a display copy).
  month      the host's month ends: month_checksum (checksums equal, no resync, $1,000 shown), month_graph_balance
             (the finance graph's balance line is $1,000 in every month on the alien machine and the real history on
             the host).
  commands   the alien client sends each X-COM Geoscape command (CMDS): cmd_<name> (the host refuses it and its world
             is unchanged).
  found      a UFO finds the X-COM base on the host: found_before (no base found yet), found_snapshot (the alien
             machine learns it within FOUND_S).
  rejoin     the alien client's process dies and a fresh one rejoins: rejoin_replica, rejoin_no_own_world (no world
             of the alien player's own on either machine), rejoin_save (the host's quick save holds no embedded world
             and names the X-COM player on every base), rejoin_found (the found base is still found).
  final      the alien client asks the host for the final mission with an X-COM craft: cmd_final_mission (refused,
             no battle starts). Last row of the session: without the refusal it starts a battle.
  reload     a third process menu-loads the host's quick save: reload_funds (at the host window, before START HOST,
             the loaded world holds the wallet the host saved, not the $1,000 the alien player is shown).
  Each row's <row>_common cell: 0 new crash files, both machines alive, no error window pushed in the row, the alien
  client never pushed the base placement screen.

Without the one-world layout the alien client holds a world of its own with an empty base at 0/0 and display copies
of the host's objects: every start, objects, month, rejoin and found cell FAILs. Without the host's refusal the
alien player's commands change the X-COM world: every cmd_* cell FAILs.

ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  py -3 tools/coop_test/test_pvp_campaign_alien_world.py
"""

import glob
import json
import math
import os
import sys
import time

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import geo  # noqa: E402
import pvp_fixture  # noqa: E402
import session  # noqa: E402

KEY = "53291"
HOST_NAME, CLIENT_NAME = "HostPlayer", "ClientPlayer"
BASE = "XcomBase"  # the X-COM player's first base (pvp_fixture)
SHOWN_FUNDS = 1000
REFUSED = "alien player command refused"
FINAL_REFUSED = "final mission request refused"
RESYNC_LINE = "resync requested"
WAIT_PLAYERS = 62  # the host's "waiting for players" dialog
HOST_SAVE_WAIT = 54  # the host's "Saving..." dialog
COMMAND_FAILED = 556  # the window that tells a player the host refused its command

UFO = dict(type="STR_SMALL_SCOUT", mission="STR_ALIEN_RESEARCH", region="STR_NORTH_AMERICA", race="STR_SECTOID",
           trajectory="P0", state="flying", speed=1, detected=False)
UFO_LON_OFF = 0.5  # radians of longitude from the X-COM base: outside every radar of the starting base
SITE = dict(mission="STR_ALIEN_TERROR", deployment="STR_TERROR_MISSION", race="STR_SECTOID", hours=240, detected=False)
ALIEN_BASE_RACE = "STR_SECTOID"
ALIEN_BASE_LON_OFF = (1.0, -1.0)
ASSAULT_LON_OFF = 1.5  # the base assault UFO is moved this far away before the clock runs again: no base defence
SELL_PREFER = ("STR_PISTOL", "STR_RIFLE", "STR_GRENADE")
FACILITY = "STR_GENERAL_STORES"
MANUFACTURE = "STR_LASER_PISTOL"  # needs the research of the same name, given to both machines first
GRID = 6

OBJECTS_S = 15.0
CHECKSUM_S = 15.0
MONTH_S = 60.0
FAIL_S = 5.0
FOUND_S = 3.0
SAVE_S = 15.0
FINAL_WATCH_S = 3.0
POLL_S = 0.1

CELLS = ["start_side", "start_replica", "start_checksum", "start_funds", "start_common",
         "objects_ufos", "objects_sites", "objects_alien_bases", "objects_common",
         "month_checksum", "month_graph_balance", "month_common"]
CMDS = ["buy", "sell", "transfer", "fac_build", "res_start", "man_start", "craft_pilots", "land_reply", "base_rename"]
CELLS += [f"cmd_{c}" for c in CMDS] + ["commands_common",
          "found_before", "found_snapshot", "found_common",
          "rejoin_replica", "rejoin_no_own_world", "rejoin_save", "rejoin_found", "rejoin_common",
          "cmd_final_mission", "final_common", "reload_funds"]

ROW_CELLS = {
    "start": ["start_side", "start_replica", "start_checksum", "start_funds", "start_common"],
    "objects": ["objects_ufos", "objects_sites", "objects_alien_bases", "objects_common"],
    "month": ["month_checksum", "month_graph_balance", "month_common"],
    "commands": [f"cmd_{c}" for c in CMDS] + ["commands_common"],
    "found": ["found_before", "found_snapshot", "found_common"],
    "rejoin": ["rejoin_replica", "rejoin_no_own_world", "rejoin_save", "rejoin_found", "rejoin_common"],
    "final": ["cmd_final_mission", "final_common"],
    "reload": ["reload_funds"],
}
assert sum(ROW_CELLS.values(), []) == CELLS

RESULTS = []  # (cell, ok, detail)


class FixtureMiss(Exception):
    pass


def cell(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)


def cell_bad(name, bad, good):
    cell(name, not bad, "; ".join(bad) if bad else good)


def block(names, why):
    done = {r[0] for r in RESULTS}
    for n in names:
        if n not in done:
            cell(n, False, f"blocked: {why}")


def evidence(row, obj):
    print(f"EVIDENCE {row}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)


def stack(gc):
    return session.states_stripped(gc)


def top(gc):
    st = stack(gc)
    return st[-1] if st else ""


def crash_set():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))


def log_since(gc, cursor):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as f:
            f.seek(cursor)
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def pushes(gc, cursor):
    events, _ = geo._read_coop_ui(gc, cursor)
    return [typ for op, typ, _ in events if op == "push"]


def to_geoscape(gc, timeout=30.0):
    """Leave a base view or close popups until the Geoscape is on top. Returns True when it is."""
    end = time.time() + timeout
    while time.time() < end:
        t = top(gc)
        if t == "GeoscapeState":
            return True
        if t == "BasescapeState":
            gc.cmd({"cmd": "leave_base"})
        elif t == "CoopState":
            if gc.cmd({"cmd": "coop_dialog_info"}).get("code") == COMMAND_FAILED:
                gc.cmd({"cmd": "coop_dialog_back"})
        elif t not in ("SaveGameState",):
            gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.2)
    return top(gc) == "GeoscapeState"


def geo_state(gc):
    return gc.ok({"cmd": "geo_state"})


def base_of(g, coop_base_id=None):
    """The X-COM base: by its coop id once known (a command that got through may have renamed it), else by name."""
    for b in g.get("bases", []):
        if (b.get("coopBaseId") == coop_base_id) if coop_base_id is not None else (b.get("name") == BASE):
            return b
    return None


def base_rows(g):
    return [{"name": b.get("name"), "coopBaseId": b.get("coopBaseId"), "ownerPlayerName": b.get("ownerPlayerName"),
             "lon": round(b.get("lon", 0.0), 6), "lat": round(b.get("lat", 0.0), 6)} for b in g.get("bases", [])]


def checksum(gc):
    r = gc.cmd({"cmd": "shared_checksum"})
    return {k: v for k, v in r.items() if k.startswith("chk")}


def diff(a, b):
    return {k: (a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}


def free_cell(base):
    """First free grid cell (row by row) that shares an edge with a finished facility."""
    used, finished = set(), set()
    for f in base["facilities"]:
        for dx in range(f["sizeX"]):
            for dy in range(f["sizeY"]):
                used.add((f["x"] + dx, f["y"] + dy))
                if f["buildTime"] == 0:
                    finished.add((f["x"] + dx, f["y"] + dy))
    for y in range(GRID):
        for x in range(GRID):
            if (x, y) not in used and any(n in finished for n in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))):
                return x, y
    return None


def wrap_lon(lon):
    return lon % (2 * math.pi)


class Run:
    def __init__(self):
        self.host = GameClient("host", None, make_user_dir("pvp_alien_world_host"))
        self.client = GameClient("client", None, make_user_dir("pvp_alien_world_client"))
        self.crash0 = set()
        self.host_cursor0 = 0
        self.spawned = {}
        self.found_set = False
        self.loader = None
        self.base_id = None  # the X-COM base's coop id, read on the host at the start
        self.saved = None  # (path, the host's wallet when it saved)

    def both(self):
        return (self.host, self.client)

    # ---- shared checks ---------------------------------------------------------------------------------------

    def check_replica(self):
        h, c = self.host, self.client
        rep = c.cmd({"cmd": "get_coop"}).get("campaignReplica")
        hb, cb = base_rows(geo_state(h)), base_rows(geo_state(c))
        bad = []
        if rep is not True:
            bad.append(f"client campaignReplica {rep!r} (want true)")
        if cb != hb:
            bad.append(f"client bases {cb} != host bases {hb}")
        owners = [b for b in hb + cb if b["ownerPlayerName"] != HOST_NAME]
        if owners:
            bad.append(f"bases not named for {HOST_NAME}: {owners}")
        extra = [b for b in cb if b not in hb]
        if extra:
            bad.append(f"client bases the host lacks: {extra}")
        return bad, {"campaignReplica": rep, "hostBases": hb, "clientBases": cb}

    def check_checksum(self, bound=CHECKSUM_S):
        t0 = time.time()
        while True:
            hc, cc = checksum(self.host), checksum(self.client)
            if hc and hc == cc:
                return [], {"equalAfterS": round(time.time() - t0, 2), "checksum": hc}
            if time.time() - t0 > bound:
                return [f"checksums differ after {bound} s (host, client): {diff(hc, cc)}"], {"host": hc, "client": cc}
            time.sleep(0.25)

    def check_funds(self):
        hf, cf = self.host.cmd({"cmd": "pvp_funds_shown"}), self.client.cmd({"cmd": "pvp_funds_shown"})
        ev = {"host": hf, "client": cf}
        if not hf.get("ok") or not cf.get("ok"):
            return [f"pvp_funds_shown host {hf} client {cf}"], ev
        bad = []
        if cf.get("fundsShown") != SHOWN_FUNDS:
            bad.append(f"client fundsShown {cf.get('fundsShown')} (want {SHOWN_FUNDS})")
        if cf.get("funds") != hf.get("funds"):
            bad.append(f"client funds {cf.get('funds')} != host funds {hf.get('funds')}")
        if hf.get("fundsShown") != hf.get("funds"):
            bad.append(f"host fundsShown {hf.get('fundsShown')} != host funds {hf.get('funds')}")
        return bad, ev

    def object_checks(self, staged=True):
        """(ufo problems, site problems, alien base problems, evidence) comparing every host object with the client."""
        hg, cg = geo_state(self.host), geo_state(self.client)
        ha = self.host.ok({"cmd": "alien_base_state"}).get("alienBases", [])
        ca = self.client.ok({"cmd": "alien_base_state"}).get("alienBases", [])
        ufo_bad, site_bad, ab_bad = [], [], []
        cu = {u.get("uniqueId"): u for u in cg.get("ufos", [])}
        for u in hg.get("ufos", []):
            r = cu.get(u.get("uniqueId"))
            if r is None:
                ufo_bad.append(f"host UFO uniqueId {u.get('uniqueId')} ({u.get('type')}, detected {u.get('detected')}) "
                               f"not on the client")
                continue
            d = {k: (u.get(k), r.get(k)) for k in ("coopId", "id", "type", "detected", "hyperDetected") if u.get(k) != r.get(k)}
            if d:
                ufo_bad.append(f"UFO {u.get('uniqueId')} (host, client) {d}")
            if r.get("coop") is not False:
                ufo_bad.append(f"client UFO {u.get('uniqueId')} coop {r.get('coop')!r} (want false)")
        want = self.spawned.get("ufoUnique")
        if want is not None and want not in {u.get("uniqueId") for u in hg.get("ufos", [])}:
            ufo_bad.append(f"precondition: the spawned UFO {want} is not on the host")
        cs = {}
        for m in cg.get("missionSites", []):
            cs.setdefault(m.get("id"), []).append(m)
        for m in hg.get("missionSites", []):
            rs = cs.get(m.get("id"), [])
            if len(rs) != 1:
                site_bad.append(f"host site {m.get('id')} ({m.get('type')}) on the client {len(rs)} times")
                continue
            r = rs[0]
            d = {k: (m.get(k), r.get(k)) for k in ("type", "race", "detected") if m.get(k) != r.get(k)}
            if d:
                site_bad.append(f"site {m.get('id')} (host, client) {d}")
            if r.get("coop") is not False:
                site_bad.append(f"client site {m.get('id')} coop {r.get('coop')!r} (want false)")
        want = self.spawned.get("siteId")
        if want is not None and want not in {m.get("id") for m in hg.get("missionSites", [])}:
            site_bad.append(f"precondition: the spawned site {want} is not on the host")
        ca_by = {}
        for a in ca:
            ca_by.setdefault(a.get("coopId"), []).append(a)
        for a in ha:
            rs = ca_by.get(a.get("coopId"), [])
            if len(rs) != 1:
                ab_bad.append(f"host alien base coopId {a.get('coopId')} (id {a.get('id')}, discovered "
                              f"{a.get('discovered')}) on the client {len(rs)} times")
                continue
            r = rs[0]
            d = {k: (a.get(k), r.get(k)) for k in ("id", "discovered", "race") if a.get(k) != r.get(k)}
            if d:
                ab_bad.append(f"alien base {a.get('coopId')} (host, client) {d}")
            if r.get("coop") is not False:
                ab_bad.append(f"client alien base {a.get('coopId')} coop {r.get('coop')!r} (want false)")
        extra = [a for a in ca if a.get("coopId") not in {x.get("coopId") for x in ha}]
        if extra:
            ab_bad.append(f"client alien bases the host lacks: {extra}")
        spawned = self.spawned.get("alienBases") or []
        if spawned and len([a for a in ha if a.get("id") in spawned]) != len(spawned):
            ab_bad.append(f"precondition: spawned alien bases {spawned} not all on the host {ha}")
        if staged and spawned and not any(not a.get("discovered") for a in ha):
            ab_bad.append(f"precondition: no undiscovered alien base on the host {ha}")
        ev = {"hostUfos": [{k: u.get(k) for k in ("uniqueId", "coopId", "id", "type", "detected", "coop")}
                           for u in hg.get("ufos", [])],
              "clientUfos": [{k: u.get(k) for k in ("uniqueId", "coopId", "id", "type", "detected", "coop")}
                             for u in cg.get("ufos", [])],
              "hostSites": [{k: m.get(k) for k in ("id", "type", "detected", "coop")} for m in hg.get("missionSites", [])],
              "clientSites": [{k: m.get(k) for k in ("id", "type", "detected", "coop")}
                              for m in cg.get("missionSites", [])],
              "hostAlienBases": ha, "clientAlienBases": ca}
        return ufo_bad, site_bad, ab_bad, ev

    def wait_objects(self, bound=OBJECTS_S, staged=True):
        """staged: right after the objects row staged them (one alien base still undiscovered); later rows let the
        month end discover it."""
        t0 = time.time()
        while True:
            u, s, a, ev = self.object_checks(staged)
            if not (u or s or a) or time.time() - t0 > bound:
                ev["waitedS"] = round(time.time() - t0, 2)
                return u, s, a, ev
            time.sleep(0.5)

    def bases_found(self, gc):
        r = gc.cmd({"cmd": "pvp_bases_found"})
        if not r.get("ok"):
            return None, r
        for b in r.get("bases", []):
            if b.get("coopBaseId") == self.base_id:
                return b.get("found"), r
        return None, r

    def common(self, row, crash0, cursors):
        bad = []
        new = sorted(crash_set() - crash0)
        if new:
            bad.append(f"{len(new)} new crash file(s) (first {os.path.basename(new[0])})")
        for gc in self.both():
            if not gc.proc or gc.proc.poll() is not None:
                bad.append(f"{gc.name} not running (rc {gc.proc.poll() if gc.proc else None})")
            errors = [t for t in pushes(gc, cursors.get(gc.name, 0)) if t == "ErrorMessageState"]
            if errors:
                bad.append(f"{gc.name} pushed {errors}")
        if "BuildNewBaseState" in pushes(self.client, 0):
            bad.append("the alien client pushed BuildNewBaseState")
        cell_bad(f"{row}_common", bad, "0 new crash files, both running, no error window, no base placement on the "
                 "alien client")

    def row_start(self):
        return set(crash_set()), {gc.name: geo._log_cursor(gc) for gc in self.both()}

    # ---- rows ----------------------------------------------------------------------------------------------

    def boot(self):
        print(f"EVIDENCE boot: cpu {harness.cpu_load()}", flush=True)
        for gc in self.both():
            gc.spawn()
            gc.connect()
        try:
            gm = pvp_fixture.start_pvp_campaign(self.host, self.client, KEY, alien_player="client")
        except Exception as e:  # noqa: BLE001
            cap = {}
            for gc in self.both():
                try:
                    cap[gc.name] = {"stack": stack(gc), "dialog": gc.cmd({"cmd": "coop_dialog_info"}),
                                    "coop": gc.cmd({"cmd": "get_coop"})}
                except Exception as e2:  # noqa: BLE001
                    cap[gc.name] = f"probe failed: {e2!r}"[:300]
            print(f"CAPTURE boot: (missed: {e}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
            raise FixtureMiss(str(e))
        self.crash0 = set(crash_set())
        self.host_cursor0 = 0
        geo.slow_clock(*self.both())
        print(f"[bring-up] game mode {gm}", flush=True)

    def start(self):
        crash0, cursors = self.row_start()
        h, c = self.host, self.client
        self.base_id = (base_of(geo_state(h)) or {}).get("coopBaseId")
        hs, cs = h.cmd({"cmd": "coop_sides"}), c.cmd({"cmd": "coop_sides"})
        bad = []
        for nm, s, plays in (("host", hs, False), ("client", cs, True)):
            if s.get("oneWorld") is not True or s.get("gamemode") != 2:
                bad.append(f"{nm} oneWorld {s.get('oneWorld')!r} gamemode {s.get('gamemode')!r} (want true, 2)")
            if s.get("playsAliens") is not plays:
                bad.append(f"{nm} playsAliens {s.get('playsAliens')!r} (want {plays})")
        cell_bad("start_side", bad, "one world, game mode 2 on both; the client plays the aliens, the host X-COM")
        bad, ev_rep = self.check_replica()
        cell_bad("start_replica", bad, f"the client is a replica holding the host's bases {ev_rep['hostBases']}")
        bad, ev_chk = self.check_checksum()
        cell_bad("start_checksum", bad, f"checksums equal after {ev_chk.get('equalAfterS')} s")
        bad, ev_funds = self.check_funds()
        cell_bad("start_funds", bad, f"client shown {SHOWN_FUNDS}, holds the host's {ev_funds['host'].get('funds')}")
        evidence("start", {"sides": {"host": hs, "client": cs}, "replica": ev_rep, "checksum": ev_chk, "funds": ev_funds})
        self.common("start", crash0, cursors)

    def objects(self):
        crash0, cursors = self.row_start()
        h = self.host
        b = base_of(geo_state(h), self.base_id)
        if b is None:
            block(["objects_ufos", "objects_sites", "objects_alien_bases"], f"the host has no {BASE}")
            self.common("objects", crash0, cursors)
            return
        geo.slow_clock(*self.both())
        ufo = h.cmd(dict(UFO, cmd="spawn_ufo", lon=wrap_lon(b["lon"] + UFO_LON_OFF), lat=b["lat"]))
        site = h.cmd(dict(SITE, cmd="spawn_mission_site", lon=wrap_lon(b["lon"] - 0.3), lat=b["lat"] + 0.2))
        abs_ = [h.cmd({"cmd": "spawn_alien_base", "lon": wrap_lon(b["lon"] + off), "lat": b["lat"],
                       "race": ALIEN_BASE_RACE}) for off in ALIEN_BASE_LON_OFF]
        found = h.cmd({"cmd": "host_alien_base_found", "alien_base_id": abs_[1].get("alien_base_id")})
        self.spawned = {"ufoUnique": ufo.get("unique_id"), "siteId": site.get("site_id"),
                        "alienBases": [a.get("alien_base_id") for a in abs_]}
        hu = [u for u in geo_state(h).get("ufos", []) if u.get("uniqueId") == ufo.get("unique_id")]
        u_bad, s_bad, a_bad, ev = self.wait_objects()
        ev.update(spawn={"ufo": ufo, "site": site, "alienBases": abs_, "found": found},
                  spawnedUfoAtSpawn=hu)
        cell_bad("objects_ufos", u_bad, f"every host UFO on the client with the host's ids, a real object "
                 f"({len(ev['hostUfos'])} UFOs, spawned {ufo.get('unique_id')} detected "
                 f"{hu[0].get('detected') if hu else None})")
        cell_bad("objects_sites", s_bad, f"every host site on the client once, a real object ({len(ev['hostSites'])})")
        cell_bad("objects_alien_bases", a_bad, f"every host alien base on the client once by coop id, a real object "
                 f"({len(ev['hostAlienBases'])}, one undiscovered)")
        evidence("objects", ev)
        for gc in self.both():
            to_geoscape(gc)
        self.common("objects", crash0, cursors)

    def month(self):
        crash0, cursors = self.row_start()
        h, c = self.host, self.client
        ev = {}
        try:
            geo.slow_clock(h, c)
            own = [h] if c.cmd({"cmd": "get_coop"}).get("campaignReplica") else [h, c]
            for gc in own:
                gc.ok({"cmd": "set_geo_day", "day": 28, "hour": 12})
            mp0 = geo_state(h)["monthsPassed"]
            t0 = time.time()
            while geo_state(h)["monthsPassed"] == mp0:
                if time.time() - t0 > MONTH_S:
                    raise RuntimeError(f"the host's month did not roll within {MONTH_S} s")
                geo.skip_ingame_time(h, c, minutes=60 * 24, speed_idx=5, real_timeout=30)
            geo.slow_clock(h, c)
            ev["dated"] = [gc.name for gc in own]
            ev["monthsPassed"] = [mp0, geo_state(h)["monthsPassed"]]
            ev["onGeoscape"] = [to_geoscape(gc) for gc in self.both()]
            geo.slow_clock(h, c)
        except Exception as e:  # noqa: BLE001
            block(["month_checksum", "month_graph_balance"], f"month end: {e}")
            evidence("month", ev)
            self.common("month", crash0, cursors)
            return
        bad, ev["checksum"] = self.check_checksum()
        resync = log_since(h, self.host_cursor0).count(RESYNC_LINE)
        if resync:
            bad.append(f"host log has {resync} '{RESYNC_LINE}' line(s) since boot")
        fbad, ev["funds"] = self.check_funds()
        cell_bad("month_checksum", bad + fbad, f"checksums equal after the month end, no resync, client shown "
                 f"{SHOWN_FUNDS} with the host's wallet")
        hf, cf = h.cmd({"cmd": "pvp_funds_shown"}), c.cmd({"cmd": "pvp_funds_shown"})
        ev["graph"] = {"host": {k: hf.get(k) for k in ("fundsList", "fundsListShown")},
                       "client": {k: cf.get(k) for k in ("fundsList", "fundsListShown")}}
        gbad = []
        if not hf.get("ok") or not cf.get("ok") or not isinstance(hf.get("fundsListShown"), list) \
                or not isinstance(cf.get("fundsListShown"), list):
            gbad.append(f"pvp_funds_shown has no finance graph balance: host {hf} client {cf}")
        else:
            if len(hf["fundsList"]) < 2:
                gbad.append(f"precondition: the host's funds history {hf['fundsList']} holds no finished month")
            if cf["fundsListShown"] != [SHOWN_FUNDS] * len(cf["fundsList"]):
                gbad.append(f"client graph balance {cf['fundsListShown']} (want {SHOWN_FUNDS} in each of "
                            f"{len(cf['fundsList'])} months)")
            if hf["fundsListShown"] != hf["fundsList"]:
                gbad.append(f"host graph balance {hf['fundsListShown']} != its history {hf['fundsList']}")
        cell_bad("month_graph_balance", gbad, f"the alien machine's finance graph shows {SHOWN_FUNDS} in every month, "
                 f"the host's shows its history {hf.get('fundsList')}")
        evidence("month", ev)
        self.common("month", crash0, cursors)

    def payloads(self):
        """{command: (baseId, payload)}: each an order the X-COM player could give at the X-COM base."""
        h = self.host
        b = base_of(geo_state(h), self.base_id) or {}
        items = b.get("items", {}) or {}
        sell = next((i for i in SELL_PREFER if items.get(i, 0) > 0), None) or next(
            (i for i, n in sorted(items.items()) if n > 0), "STR_PISTOL")
        cellxy = free_cell(b) if b.get("facilities") else None
        topics = h.cmd({"cmd": "available_research", "base": b.get("name", BASE)}).get("topics") or ["STR_LASER_WEAPONS"]
        sky = next((cr for cr in b.get("crafts", []) if "SKYRANGER" in cr.get("type", "")), {"id": 1})
        soldiers = []
        for sb in h.cmd({"cmd": "get_soldiers"}).get("bases", []):
            if sb.get("name") == b.get("name", BASE):
                soldiers = [s["id"] for s in sb.get("soldiers", [])]
        x, y = cellxy or (0, 0)
        craft = {"craftId": sky.get("id"), "craftType": "STR_SKYRANGER"}
        return {
            "buy": (0, {"items": [{"type": 0, "rule": "STR_ELECTRO_FLARE", "qty": 1}]}),
            "sell": (0, {"items": [{"rule": sell, "qty": 1}]}),
            "transfer": (0, {"toBaseId": 0, "items": [{"rule": sell, "qty": 1}], "soldiers": [], "crafts": [],
                             "scientists": 0, "engineers": 0}),
            "fac_build": (0, {"facilityType": FACILITY, "x": x, "y": y}),
            "res_start": (0, {"project": topics[0]}),
            "man_start": (0, {"item": MANUFACTURE, "engineers": 0, "qty": 1, "infinite": False, "sell": False}),
            "craft_pilots": (0, dict(craft, op="add", soldierId=soldiers[0] if soldiers else -1)),
            "land_reply": (0, dict(craft, yes=False, patrol=True)),
            "base_rename": (0, {"name": "Renamed by the aliens"}),
        }

    def commands(self):
        crash0, cursors = self.row_start()
        h, c = self.host, self.client
        for gc in self.both():
            gc.cmd({"cmd": "discover_research", "topic": MANUFACTURE})
        self.check_checksum()
        pl = self.payloads()
        ev = {"payloads": pl}
        for name in CMDS:
            base_id, payload = pl[name]
            to_geoscape(c)
            chk0, st0, bases0 = checksum(h), h.cmd({"cmd": "shared_stats"}), base_rows(geo_state(h))
            sent = c.cmd({"cmd": "shared_cmd", "jcmd": name, "baseId": base_id, "payload": payload})
            t0, st1 = time.time(), st0
            while time.time() - t0 < FAIL_S:
                st1 = h.cmd({"cmd": "shared_stats"})
                if st1.get("failCount", 0) > st0.get("failCount", 0):
                    break
                time.sleep(POLL_S)
            failed = st1.get("failCount", 0) > st0.get("failCount", 0)
            time.sleep(0.3)  # a command applied after its failure count is read would still change the world here
            chk1, bases1 = checksum(h), base_rows(geo_state(h))
            closed = to_geoscape(c, timeout=10)
            bad = []
            if not sent.get("ok"):
                bad.append(f"shared_cmd {sent}")
            if not failed:
                bad.append(f"the host never refused it within {FAIL_S} s (okCount {st0.get('okCount')} -> "
                           f"{st1.get('okCount')}, applyCount {st0.get('applyCount')} -> {st1.get('applyCount')})")
            if st1.get("lastFail") != REFUSED:
                bad.append(f"host lastFail {st1.get('lastFail')!r} (want {REFUSED!r})")
            if chk1 != chk0:
                bad.append(f"host checksum changed {diff(chk0, chk1)}")
            if bases1 != bases0:
                bad.append(f"host bases changed {bases0} -> {bases1}")
            if not closed:
                bad.append(f"the alien client is not back on the Geoscape ({stack(c)})")
            ev[name] = {"stats": [st0, st1], "refusedS": round(time.time() - t0, 2)}
            cell_bad(f"cmd_{name}", bad, f"the host refused {name} from the alien player; its world is unchanged")
        evidence("commands", ev)
        self.common("commands", crash0, cursors)

    def found(self):
        crash0, cursors = self.row_start()
        h, c = self.host, self.client
        ev = {}
        hf, ev["hostBefore"] = self.bases_found(h)
        cf, ev["clientBefore"] = self.bases_found(c)
        if hf is True or cf is True:
            cell("found_before", False, f"blocked: base already found (host {hf}, client {cf})")
        else:
            cell_bad("found_before", [f"host {hf!r}, client {cf!r} (want false on both)"] if (hf, cf) != (False, False)
                     else [], f"{BASE} not found on either machine")
        # The host's Geoscape stands still while a window is open: the assault UFO is moved away before it can land.
        b = base_of(geo_state(h), self.base_id) or {}
        geo.slow_clock(h, c)
        click = session.click_widget_ready(h, "INTERCEPT")
        covered = h.wait_for("the host's interception window", lambda: top(h) == "InterceptState" or None,
                             timeout=5, interval=0.02) if click.get("ok") else None
        assault = h.cmd({"cmd": "spawn_base_assault", "base": b.get("name", BASE), "speed": 1})
        moved = h.cmd({"cmd": "move_ufo", "ufo_id": assault["ufo_id"], "lon": wrap_lon(b.get("lon", 0.0) + ASSAULT_LON_OFF),
                       "lat": b.get("lat", 0.0)}) if assault.get("ok") else {"skipped": "no assault UFO"}
        session.click_widget_ready(h, "CANCEL")
        to_geoscape(h, timeout=10)
        t0 = time.time()
        hf, ev["hostAfter"] = self.bases_found(h)
        cf, last = None, None
        while time.time() - t0 < FOUND_S:
            cf, last = self.bases_found(c)
            if cf is True:
                break
            time.sleep(0.05)
        ev.update(covered=covered, assault=assault, moved=moved, clientAfter=last, clientTrueS=round(time.time() - t0, 2),
                  hostStack=stack(h))
        bad = []
        if not assault.get("ok") or not moved.get("ok"):
            bad.append(f"staging: spawn_base_assault {assault}, move_ufo {moved}")
        if hf is not True:
            bad.append(f"host {BASE} found {hf!r} (want true)")
        if cf is not True:
            bad.append(f"client {BASE} found {cf!r} after {FOUND_S} s (want true)")
        if any(t in ("BaseDefenseState", "BriefingState") for t in pushes(h, cursors["host"])):
            bad.append(f"a base defence started on the host: {pushes(h, cursors['host'])}")
        self.found_set = hf is True
        cell_bad("found_snapshot", bad, f"a UFO found {BASE} on the host; the alien machine shows it found "
                 f"{ev['clientTrueS']} s later")
        evidence("found", ev)
        to_geoscape(c)
        self.common("found", crash0, cursors)

    def rejoin(self):
        crash0, cursors = self.row_start()
        h = self.host
        names = ["rejoin_replica", "rejoin_no_own_world", "rejoin_save", "rejoin_found"]
        ev = {}
        try:
            self.client.kill()
            h.wait_for("host waiting dialog after the client drop",
                       lambda: (lambda d: (d.get("present") and d.get("code") == WAIT_PLAYERS) or None)(
                           h.ok({"cmd": "coop_dialog_info"})), timeout=60, interval=0.2)
            c = GameClient("client", None, make_user_dir("pvp_alien_world_rejoin"))
            c.spawn()
            c.connect()
            self.client = c
            cursors["client"] = 0
            c.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": CLIENT_NAME})

            def held():
                for gc in (h, c):
                    if session.has_state(gc, "Profile"):
                        gc.ok({"cmd": "profile_ok"})
                return (session.has_state(c, "CoopState") and not session.has_state(h, "Profile")
                        and h.ok({"cmd": "get_coop"}).get("resumeAck")) or None
            c.wait_for("rejoined client holds for the host", held, timeout=60, interval=0.2)
            session.press_back_when_shown(h, "host RESUME", codes=(60, 62))
            ev["onGeoscape"] = [to_geoscape(gc, timeout=60) for gc in self.both()]
            geo.slow_clock(*self.both())
        except Exception as e:  # noqa: BLE001
            block(names, f"rejoin: {e}")
            evidence("rejoin", ev)
            self.common("rejoin", crash0, cursors)
            return
        bad, ev["replica"] = self.check_replica()
        cbad, ev["checksum"] = self.check_checksum()
        u, s, a, ev["objects"] = self.wait_objects(staged=False)
        cell_bad("rejoin_replica", bad + cbad + u + s + a, "the rejoined alien client is a replica of the host's "
                 "world: bases, checksum, UFOs, sites and alien bases")
        # The host's copy of the alien player's world, and the client's own world as a two-world start keeps it. The
        # client's client_ key is the host's world as it streamed in (stored there while no world was loaded yet):
        # printed, not a world of its own.
        hk = h.cmd({"cmd": "coop_file_info", "role": "host_copy_of_client"})
        ck = self.client.cmd({"cmd": "coop_file_info", "role": "host_copy_of_client"})
        streamed = self.client.cmd({"cmd": "coop_file_info", "role": "own_world"})
        ev["files"] = {"host": hk, "client": ck, "clientStreamedWorld": streamed}
        fbad = []
        if not hk.get("ok") or hk.get("present") is not False:
            fbad.append(f"host holds {hk.get('key')!r}: {hk}")
        if not ck.get("ok") or ck.get("present") is not False:
            fbad.append(f"client holds {ck.get('key')!r}: {ck}")
        cell_bad("rejoin_no_own_world", fbad, f"no world of the alien player's own: host {hk.get('key')!r} absent, "
                 f"client {ck.get('key')!r} absent")
        self.save_cell(ev)
        cf, ev["clientFound"] = self.bases_found(self.client)
        if not self.found_set:
            cell("rejoin_found", False, "blocked: the host never marked the base found (found_snapshot)")
        else:
            cell_bad("rejoin_found", [] if cf is True else [f"rejoined client {BASE} found {cf!r} (want true)"],
                     f"the rejoined alien client shows {BASE} found")
        evidence("rejoin", ev)
        self.common("rejoin", crash0, cursors)

    def save_cell(self, ev):
        h = self.host
        path = os.path.join(h.user_dir, "xcom1", "_quick_.asav")
        if os.path.exists(path):
            os.remove(path)
        ev["coopSessionS"] = session.wait_coop_session(h)
        funds = h.cmd({"cmd": "pvp_funds_shown"}).get("funds", geo_state(h).get("funds"))
        t0, saw54 = time.time(), False
        h.ok({"cmd": "save_game_ui", "type": "quick"})
        while time.time() - t0 < SAVE_S and not os.path.exists(path):
            if h.cmd({"cmd": "coop_dialog_info"}).get("code") == HOST_SAVE_WAIT:
                saw54 = True
            time.sleep(0.05)
        written = os.path.exists(path)
        bad = []
        if not written:
            bad.append(f"the quick save was not written within {SAVE_S} s (host {stack(h)})")
            if h.cmd({"cmd": "coop_dialog_info"}).get("code") == HOST_SAVE_WAIT:
                h.cmd({"cmd": "coop_dialog_back"})
        if saw54:
            bad.append("the host showed its Saving... dialog (CoopState 54)")
        to_geoscape(h)
        if written:
            time.sleep(0.2)
            with open(path, "r", encoding="utf-8") as f:
                docs = list(yaml.safe_load_all(f.read()))
            header, body = docs[0], docs[1]
            self.saved = (path, funds)
            ev["save"] = {"writtenS": round(time.time() - t0, 2), "saveSchema": header.get("saveSchema"), "hostFunds": funds,
                          "coopPlayers": header.get("coopPlayers"),
                          "bases": [{"name": b.get("name"), "ownerplayername": b.get("ownerplayername")}
                                    for b in body.get("bases", [])]}
            if "coopPvpBorrowed" in header:
                bad.append("header has coopPvpBorrowed")
            if body.get("coop_gamemode") != 2:
                bad.append(f"coop_gamemode {body.get('coop_gamemode')!r} (want 2)")
            if body.get("no_bases") is not False:
                bad.append(f"no_bases {body.get('no_bases')!r} (want false)")
            if "coopClientSaves" in body:
                bad.append(f"body embeds {len(body.get('coopClientSaves') or [])} player world(s) (coopClientSaves)")
            if "separateCampaign" in body:
                bad.append("body has separateCampaign")
            for b in body.get("bases", []):
                if b.get("ownerplayername") != HOST_NAME:
                    bad.append(f"base {b.get('name')!r} ownerplayername {b.get('ownerplayername')!r} (want {HOST_NAME})")
                wrong = [s.get("id") for s in b.get("soldiers", []) or []
                         if s.get("coop", 0) == 0 and s.get("ownerplayerid") != 0]
                if wrong:
                    bad.append(f"base {b.get('name')!r} soldiers {wrong} not owned by player 0")
        cell_bad("rejoin_save", bad, f"the host's quick save holds one world, no embedded player world, every base "
                 f"named for {HOST_NAME}")

    def final(self):
        crash0, cursors = self.row_start()
        h, c = self.host, self.client
        ev = {}
        b = base_of(geo_state(c), self.base_id) or {}
        craft_id = (b.get("crafts") or [{}])[0].get("id", -1)
        msg = c.cmd({"cmd": "separate_craft_message", "base": b.get("name", BASE), "craftId": craft_id})
        ev["message"] = msg
        if not msg.get("ok"):
            cell("cmd_final_mission", False, f"the alien client holds no X-COM craft at {BASE} to name: {msg}")
        else:
            hcur = geo._log_cursor(h)
            sent = c.cmd({"cmd": "send_peer_message", "message": msg["message"]})
            t0, seen = time.time(), []
            while time.time() - t0 < FINAL_WATCH_S:
                st = stack(h)
                if "ConfirmCydoniaState" in st or "BattlescapeState" in st or "BriefingState" in st:
                    seen = st
                    break
                time.sleep(0.05)
            pushed = pushes(h, hcur)
            refused = FINAL_REFUSED in log_since(h, hcur)
            ev.update(sent=sent, pushed=pushed, refusedLine=refused, hostStack=stack(h))
            bad = []
            if not sent.get("ok"):
                bad.append(f"send_peer_message {sent}")
            if seen or any(t in ("ConfirmCydoniaState", "BriefingState", "BattlescapeState") for t in pushed):
                bad.append(f"the host started the final mission: stack {seen or stack(h)}, pushed {pushed}")
            if not refused:
                bad.append(f"the host log has no '{FINAL_REFUSED}' line")
            cell_bad("cmd_final_mission", bad, "the host ignored the alien player's final mission request")
        evidence("final", ev)
        self.common("final", crash0, cursors)

    def reload(self):
        if not self.saved:
            block(["reload_funds"], "no host save was written (rejoin_save)")
            return
        path, funds = self.saved
        name = "pvp_alien_world_reload.asav"
        user_dir = make_user_dir("pvp_alien_world_reload")
        os.makedirs(os.path.join(user_dir, "xcom1"), exist_ok=True)
        with open(path, "rb") as src, open(os.path.join(user_dir, "xcom1", name), "wb") as dst:
            dst.write(src.read())
        gc = GameClient("loader", None, user_dir)
        self.loader = gc
        gc.spawn()
        gc.connect()
        gc.ok({"cmd": "load_save_menu", "file": name})

        def outcome():
            st = stack(gc)
            if any("ErrorMessage" in t for t in st):
                return "error message"
            return "HostMenu" if any("HostMenu" in t for t in st) else None
        reached = gc.wait_for("the loaded save at the host window", outcome, timeout=60, interval=0.25)
        f = gc.cmd({"cmd": "pvp_funds_shown"})
        g = gc.cmd({"cmd": "geo_state"})
        ev = {"reached": reached, "stack": stack(gc), "pvpFundsShown": f, "geoFunds": g.get("funds"), "savedFunds": funds,
              "seat": gc.cmd({"cmd": "get_coop"}).get("localSeat")}
        bad = []
        if reached != "HostMenu":
            bad.append(f"the load reached {reached} ({stack(gc)}), not the host window")
        if g.get("funds") != funds:
            bad.append(f"the loaded world's funds {g.get('funds')} (want the {funds} the host saved)")
        cell_bad("reload_funds", bad, f"the menu-loaded save holds the host's wallet {funds} before START HOST")
        evidence("reload", ev)

    def run(self):
        self.boot()
        for row in (self.start, self.objects, self.month, self.commands, self.found, self.rejoin, self.final, self.reload):
            try:
                row()
            except FixtureMiss:
                raise
            except Exception as e:  # noqa: BLE001 - reported as the row's failure; later rows still run
                print(f"[ERROR] {row.__name__}: {type(e).__name__}: {e}", flush=True)
                block(ROW_CELLS[row.__name__], f"error {type(e).__name__}: {str(e)[:200]}")


def main():
    t0 = time.time()
    r = Run()
    try:
        r.run()
    except FixtureMiss as e:
        block(CELLS, f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
        block(CELLS, f"error {type(e).__name__}: {str(e)[:200]}")
    finally:
        try:
            harness.shutdown_clients(r.host, r.client, r.loader)
        except RuntimeError as e:
            print(f"[ERROR] shutdown: {e}", flush=True)
    block(CELLS, "not reached")
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== test_pvp_campaign_alien_world: {len(RESULTS) - len(fails)}/{len(RESULTS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(CELLS) else 2)


if __name__ == "__main__":
    main()
