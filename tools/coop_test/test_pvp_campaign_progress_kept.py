"""PvP campaign: the X-COM player's progress survives a client rejoin and a host reload.

Before the campaign is interrupted, the X-COM player buys an item, starts a research
project, starts building a facility and lets the clock cross a month end so its funds
change. The campaign is then interrupted and resumed, and both machines must still hold
each of those as it was.

Layouts (each row is a fresh campaign):
  host plays X-COM       game mode 2, the client plays the aliens
  host plays the aliens  game mode 3, the client plays X-COM

Interruptions:
  rejoin     the client drops and rejoins, then the host presses RESUME
  save quit  the client drops, the host takes SAVE & QUIT, loads that save and hosts
             again, the client rejoins and both resume

Cells per row (each covers both machines): funds, purchase, research, facility, month.
On the X-COM machine each must be present before the interruption and equal after it.
On the alien machine each must equal what that machine held before the interruption.
It must also be present there when that machine holds the X-COM player's real base or
wallet; a machine that shows only a display copy of the base holds neither.

The X-COM player acts through the purchase, research and facility screens on its own
machine, the same commands a Separate campaign's client uses.

Run:  py -3 tools/coop_test/test_pvp_campaign_progress_kept.py [row ...]
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import geo
import pvp_fixture
import session

WAIT_PLAYERS = 62  # the host's "waiting for players" dialog
BASE = "XcomBase"  # the X-COM player's first base (pvp_fixture)
ITEM = "STR_ELECTRO_FLARE"  # buyable at the start; the starting base holds none
ITEM_COUNT = 5
FACILITY = "STR_GENERAL_STORES"  # 1x1, 10 days to build: still under construction after the month end
SCIENTISTS = 1  # one scientist cannot finish a starting topic within the few days before the month end
GRID = 6  # base grid size
SETTLE_S = 10  # how long the resumed machines get to show what they held before
CELLS = ("funds", "purchase", "research", "facility", "month")

# row: (host plays X-COM, interruption, lobby port, reload port)
ROWS = {
    "host_xcom_rejoin": (True, "rejoin", "49731", "49732"),
    "host_xcom_save_quit": (True, "save_quit", "49733", "49734"),
    "host_aliens_rejoin": (False, "rejoin", "49735", "49736"),
    "host_aliens_save_quit": (False, "save_quit", "49737", "49738"),
}


def top(gc):
    st = session.states(gc)
    return st[-1].replace("class OpenXcom::", "") if st else ""


def to_geoscape(gc, what):
    """Leave a base view or close popups until the geoscape is on top."""
    def step():
        t = top(gc)
        if "GeoscapeState" in t:
            return True
        if "BasescapeState" in t:
            gc.cmd({"cmd": "leave_base"})
        else:
            gc.cmd({"cmd": "dismiss_popup"})
        return None
    gc.wait_for(what, step, timeout=60, interval=0.2)


def find_base(geo_state):
    for b in geo_state.get("bases", []):
        if b.get("name") == BASE:
            return b
    return None


def free_cell(base):
    """First free grid cell (row by row) that shares an edge with a finished facility: a 1x1 build there is valid."""
    used, finished = set(), set()
    for f in base["facilities"]:
        for dx in range(f["sizeX"]):
            for dy in range(f["sizeY"]):
                used.add((f["x"] + dx, f["y"] + dy))
                if f["buildTime"] == 0:
                    finished.add((f["x"] + dx, f["y"] + dy))
    for y in range(GRID):
        for x in range(GRID):
            if (x, y) in used:
                continue
            if any(n in finished for n in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))):
                return x, y
    raise RuntimeError(f"no free connected cell in {BASE}: {base['facilities']}")


class Row:
    def __init__(self, name, host_xcom, interruption, port, reload_port):
        self.name, self.host_xcom, self.interruption = name, host_xcom, interruption
        self.port, self.reload_port = port, reload_port
        self.fails = []
        self.host = GameClient("host", None, make_user_dir(f"pvpkeep_{name}_host"))
        self.client = GameClient("client", None, make_user_dir(f"pvpkeep_{name}_client"))
        self.xcom_name = "HostPlayer" if host_xcom else "ClientPlayer"
        self.cell = None  # the facility's grid cell
        self.topic = None

    @property
    def xcom(self):
        return self.host if self.host_xcom else self.client

    def machines(self):
        """(label, machine, is the X-COM machine)"""
        return (("host", self.host, self.host_xcom), ("client", self.client, not self.host_xcom))

    def fail(self, msg):
        print(f"  FAIL {self.name} {msg}", flush=True)
        self.fails.append(f"{self.name} {msg}")

    # ---- reading the X-COM player's progress on one machine ---------------------------

    def read(self, gc, is_xcom):
        """{cell: (value, required)} for the X-COM player's progress as `gc` holds it. None = not held."""
        geo_state = gc.ok({"cmd": "geo_state"})
        wallets = gc.ok({"cmd": "month_report"}).get("playerFunds") or {}
        base = find_base(geo_state)
        real_base = base is not None and not base.get("coopIcon")
        out = {}
        if self.xcom_name in wallets:
            out["funds"] = (wallets[self.xcom_name], True)
        else:
            out["funds"] = (geo_state["funds"] if is_xcom else None, is_xcom)
        need = is_xcom or real_base
        bought = None
        research = None
        facility = None
        if base is not None:
            total = base.get("items", {}).get(ITEM, 0) + sum(
                t["qty"] for t in base.get("transfers", []) if t.get("rule") == ITEM)
            bought = total or None
            for p in base.get("research", []):
                if p["name"] == self.topic:
                    research = {"topic": p["name"], "cost": p["cost"], "assigned": p["assigned"]}
            for f in base.get("facilities", []):
                if self.cell and (f["x"], f["y"]) == self.cell and f["type"] == FACILITY:
                    facility = {"type": f["type"], "x": f["x"], "y": f["y"]}
        out["purchase"] = (bought, need)
        out["research"] = (research, need)
        out["facility"] = (facility, need)
        t = geo_state["time"]
        out["month"] = ({"monthsPassed": geo_state["monthsPassed"], "year": t["year"], "month": t["month"]}, True)
        return out

    def read_both(self):
        return {label: self.read(gc, is_xcom) for label, gc, is_xcom in self.machines()}

    @staticmethod
    def show(snapshot):
        return {label: {c: v for c, (v, _) in cells.items()} for label, cells in snapshot.items()}

    # ---- the X-COM player's actions, through its own screens ------------------------

    def xcom_base(self):
        base = find_base(self.xcom.ok({"cmd": "geo_state"}))
        if base is None:
            raise RuntimeError(f"{self.name}: the X-COM machine has no {BASE}")
        return base

    def wait_xcom(self, what, pred):
        return self.xcom.wait_for(f"{self.name}: {what}", lambda: pred(self.xcom_base()) or None,
                                  timeout=30, interval=0.1)

    def buy(self):
        base = self.xcom_base()
        start = base["items"].get(ITEM, 0) + sum(t["qty"] for t in base["transfers"] if t.get("rule") == ITEM)
        if start:
            raise RuntimeError(f"{self.name}: precondition: {BASE} already holds {start} x {ITEM}")
        self.xcom.ok({"cmd": "buy", "item": ITEM, "count": ITEM_COUNT, "base": BASE})
        self.wait_xcom(f"{ITEM_COUNT} x {ITEM} on the way",
                       lambda b: sum(t["qty"] for t in b["transfers"] if t.get("rule") == ITEM) == ITEM_COUNT)
        to_geoscape(self.xcom, f"{self.name}: X-COM machine back on the geoscape after the purchase")

    def research(self):
        topics = self.xcom.ok({"cmd": "available_research", "base": BASE})["topics"]
        if not topics:
            raise RuntimeError(f"{self.name}: precondition: no research topic available at {BASE}")
        self.topic = topics[0]
        self.xcom.ok({"cmd": "research_start", "topic": self.topic, "scientists": SCIENTISTS, "base": BASE})
        self.wait_xcom(f"research {self.topic} running",
                       lambda b: any(p["name"] == self.topic for p in b["research"]))
        to_geoscape(self.xcom, f"{self.name}: X-COM machine back on the geoscape after starting research")

    def build(self):
        self.cell = free_cell(self.xcom_base())
        x, y = self.cell
        self.xcom.ok({"cmd": "fac_build", "facility": FACILITY, "x": x, "y": y, "base": BASE})
        self.wait_xcom(f"{FACILITY} under construction at {self.cell}",
                       lambda b: any(f["type"] == FACILITY and (f["x"], f["y"]) == self.cell and f["buildTime"] > 0
                                     for f in b["facilities"]))
        to_geoscape(self.xcom, f"{self.name}: X-COM machine back on the geoscape after placing {FACILITY}")

    def month_end(self):
        """Jump the date to the 28th and let the clock run until the X-COM player's month rolls.

        The host runs the clock. A client that is not a replica runs its own world's clock too,
        so its date is moved as well."""
        h, c = self.host, self.client
        geo.slow_clock(h, c)
        client_runs_own_world = not c.ok({"cmd": "get_coop"}).get("campaignReplica")
        dated = [h, c] if client_runs_own_world else [h]
        for gc in dated:
            gc.ok({"cmd": "set_geo_day", "day": 28, "hour": 12})
        print(f"    {self.name}: date set to the 28th on {[gc.name for gc in dated]}", flush=True)
        funds0 = self.read(self.xcom, True)["funds"][0]
        mp0 = self.xcom.ok({"cmd": "geo_state"})["monthsPassed"]
        deadline = time.time() + 60
        while self.xcom.ok({"cmd": "geo_state"})["monthsPassed"] == mp0:
            if time.time() > deadline:
                raise RuntimeError(f"{self.name}: the X-COM player's month did not roll")
            geo.skip_ingame_time(h, c, minutes=60 * 24, speed_idx=5, real_timeout=30)
        geo.slow_clock(h, c)
        for label, gc, _ in self.machines():
            to_geoscape(gc, f"{self.name}: {label} closed the month-end screens")
        geo.slow_clock(h, c)
        funds1 = self.read(self.xcom, True)["funds"][0]
        print(f"    {self.name}: X-COM funds across the month end {funds0} -> {funds1}", flush=True)
        if funds1 == funds0:
            raise RuntimeError(f"{self.name}: precondition: the month end left the X-COM funds at {funds0}")

    # ---- interruptions ---------------------------------------------------------------

    def crash_client(self):
        self.client.kill()
        self.host.wait_for(f"{self.name}: host waiting dialog after the client drop",
                           lambda: (lambda d: (d.get("present") and d.get("code") == WAIT_PLAYERS) or None)(
                               self.host.ok({"cmd": "coop_dialog_info"})),
                           timeout=60, interval=0.2)

    def new_client(self, label):
        c = GameClient("client", None, make_user_dir(f"pvpkeep_{self.name}_{label}"))
        c.spawn(); c.connect()
        self.client = c
        return c

    def rejoin(self):
        """The client drops; a fresh client process rejoins the running campaign; the host presses RESUME."""
        self.crash_client()
        c = self.new_client("rejoin")
        c.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": self.port, "player": "ClientPlayer"})

        def held():
            # both machines raise a "player joined" popup; close it as a player would
            for gc in (self.host, c):
                if session.has_state(gc, "Profile"):
                    gc.ok({"cmd": "profile_ok"})
            return (session.has_state(c, "CoopState") and not session.has_state(self.host, "Profile")
                    and self.host.ok({"cmd": "get_coop"}).get("resumeAck")) or None
        c.wait_for(f"{self.name}: rejoined client holds for the host", held, timeout=60, interval=0.2)
        session.press_back_when_shown(self.host, f"{self.name} host RESUME", codes=(60, 62))

    def save_quit(self):
        """The client drops; the host takes SAVE & QUIT, loads that save and hosts again; the client rejoins."""
        save = "pvp_progress_kept"
        self.crash_client()
        self.host.ok({"cmd": "coop_dialog_save_quit"})
        self.host.wait_for(f"{self.name}: save list", lambda: session.has_state(self.host, "ListSaveState") or None,
                           timeout=30, interval=0.2)
        self.host.ok({"cmd": "list_save_confirm", "name": save})
        self.host.wait_for(f"{self.name}: host main menu after SAVE & QUIT",
                           lambda: "MainMenuState" in top(self.host) or None, timeout=60, interval=0.2)
        self.new_client("reload")
        session.resume_campaign(self.host, self.client, save + ".sav", port=self.reload_port)

    # ---- the row -----------------------------------------------------------------------

    def run(self):
        alien = "client" if self.host_xcom else "host"
        print(f"\n--- {self.name}: host plays {'X-COM' if self.host_xcom else 'the aliens'}, "
              f"interruption {self.interruption} ---", flush=True)
        self.host.spawn(); self.host.connect(); self.client.spawn(); self.client.connect()
        gm = pvp_fixture.start_pvp_campaign(self.host, self.client, self.port, alien_player=alien)
        if gm != (2 if self.host_xcom else 3):
            raise RuntimeError(f"{self.name}: unexpected game mode {gm}")
        for label, gc, _ in self.machines():
            coop = gc.ok({"cmd": "get_coop"})
            print(f"    {self.name}: {label} gamemode={coop.get('gamemode')} noBases={coop.get('noBases')} "
                  f"campaignReplica={coop.get('campaignReplica')}", flush=True)
        geo.slow_clock(self.host, self.client)
        self.buy()
        self.research()
        self.build()
        self.month_end()

        before = self.read_both()
        print(f"    {self.name}: before the interruption {self.show(before)}", flush=True)
        for label, cells in before.items():
            for cell, (value, required) in cells.items():
                if required and value is None:
                    raise RuntimeError(f"{self.name}: precondition: {label} holds no {cell} before the interruption")

        getattr(self, self.interruption)()
        for label, gc, _ in self.machines():
            to_geoscape(gc, f"{self.name}: {label} on the geoscape after the {self.interruption}")
        geo.slow_clock(self.host, self.client)

        def same():
            now = self.read_both()
            return now if self.show(now) == self.show(before) else None
        try:
            after = self.host.wait_for(f"{self.name}: both machines show what they held before", same,
                                       timeout=SETTLE_S, interval=0.25)
        except TimeoutError:
            after = self.read_both()
        print(f"    {self.name}: after the {self.interruption} {self.show(after)}", flush=True)

        for cell in CELLS:
            bad = []
            for label in ("host", "client"):
                was, _ = before[label][cell]
                now, required = after[label][cell]
                if required and now is None:
                    bad.append(f"{label} holds none (before: {was})")
                elif now != was:
                    bad.append(f"{label} {was} -> {now}")
            if bad:
                self.fail(f"{cell}: " + "; ".join(bad))
            else:
                print(f"PASS {self.name} {cell}: " + "; ".join(
                    f"{label} {after[label][cell][0]}" for label in ("host", "client")), flush=True)


def main():
    wanted = sys.argv[1:] or list(ROWS)
    unknown = [r for r in wanted if r not in ROWS]
    if unknown:
        print(f"unknown rows {unknown}; rows are {list(ROWS)}")
        sys.exit(2)
    fails = []
    verdicts = []
    t0 = time.time()
    for name in wanted:
        row = Row(name, *ROWS[name])
        t_row = time.time()
        try:
            row.run()
        except Exception as e:
            print(f"[ERROR] {name}: {e}", flush=True)
            row.fails.append(f"{name}: {e}")
        finally:
            row.host.shutdown()
            row.client.shutdown()
        fails += row.fails
        verdicts.append(f"{'PASS' if not row.fails else 'FAIL'} {name} ({time.time() - t_row:.1f}s)")
    print(f"\n==== PvP campaign progress kept summary ({time.time() - t0:.1f}s) ====")
    for v in verdicts:
        print(f"  {v}")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  the X-COM player's purchase, research, facility, funds and month survived every interruption")
    sys.exit(0)


if __name__ == "__main__":
    main()
