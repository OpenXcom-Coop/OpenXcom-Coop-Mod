"""PvP campaign: the screens the alien player sees on the Geoscape.

Each layout is a fresh campaign:
  host_xcom    the host plays X-COM, the client plays the aliens (game mode 2)
  host_aliens  the host plays the aliens, the client plays X-COM (game mode 3)

Cells, read on the alien player's machine unless stated:
  dead_buttons    INTERCEPT and BASES on the Geoscape open nothing: no screen is pushed and the
                  Geoscape stays on top. Control: INTERCEPT on the X-COM machine opens the
                  interception window, so the clicks do land.
  ufo_window      X-COM detects a UFO: the alien machine shows the UFO-detected window, and every
                  UFO window it shows in the run has INTERCEPT hidden. Control: a UFO window on the
                  X-COM machine shows INTERCEPT.
  mission_window  X-COM detects a terror site: the alien machine shows the mission window with
                  INTERCEPT hidden.
  month_report    at the month end the alien machine shows X-COM's monthly report and its balance
                  line reads $1,000. Control: the X-COM machine's report shows another balance.
  no_notices      the X-COM player completes a research project and receives a purchase: the X-COM
                  machine shows the research-complete and item-arrival windows, and the alien machine
                  shows no research, production, arrival or base notice for the whole run.
  end_clean       both machines end the run on the Geoscape with no error dialog.

Everything asserted is a screen: the top window, its buttons and texts (list_widgets) and the
screens each machine pushed (the "[coop-ui] push" lines of its openxcom.log).

Staging. Both machines load mods/Coop_GlobeRadar_Test: every base's access lift is a radar that
covers the whole globe and always detects, so X-COM detects a flying UFO at its first 30-minute
check. The host runs the aliens' side of the world in both layouts, so the undetected UFO and the
undetected terror site are spawned on the host, beside the X-COM base. The X-COM player starts a
research project and buys an item through the research and purchase screens on its own machine.
The project's cost is set to 1 on every machine that runs a world of its own (the host, and the
client while it is not a replica), so it completes at the next daily step. The month end is reached
by moving the date to the 28th on those same machines. RNG seeds are pinned on both machines after
the bring-up, and every pending Geoscape event is pushed past the run.

Run:  py -3 tools/coop_test/test_pvp_campaign_alien_player_screens.py [layout ...]
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from harness import GameClient, make_user_dir
import geo
import pvp_fixture
import session

MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_GlobeRadar_Test")
BASE = "XcomBase"  # the X-COM player's first base (pvp_fixture)
ITEM = "STR_ELECTRO_FLARE"  # buyable at the start
SEED = 241
EVENT_PUSH_MIN = 60 * 24 * 90  # pending Geoscape events wait 90 days: past the end of the run
DAY = 60 * 24

UFO = dict(type="STR_SMALL_SCOUT", mission="STR_ALIEN_RESEARCH", region="STR_NORTH_AMERICA",
           race="STR_SECTOID", trajectory="P0", state="flying", speed=1, detected=False)
SITE = dict(mission="STR_ALIEN_TERROR", deployment="STR_TERROR_MISSION", race="STR_SECTOID",
            hours=240, detected=False)

OBSERVE_S = 1.5   # a dead button is watched this long after its click (the control opens its window well inside it)
OPEN_S = 5.0      # a window opening after a click
ACTION_S = 30.0   # the X-COM player's research or purchase showing on its machine
WINDOWS_S = 60.0  # real-time bound of the detection and notices window
WINDOWS_MIN = 3 * DAY  # game-time bound of the same window
MONTH_S = 60.0    # real-time bound of the month end
SETTLE_S = 30.0   # both machines back on the Geoscape at the end
POLL_S = 0.1

WATCHED = ("UfoDetectedState", "MissionDetectedState", "MonthlyReportState")
SELF_CLOSING = ("SaveGameState", "CoopState")  # left to close on their own
NOTICES = ("ResearchCompleteState", "NewPossibleResearchState", "NewPossibleManufactureState",
           "NewPossiblePurchaseState", "NewPossibleCraftState", "NewPossibleFacilityState",
           "ResearchRequiredState", "ProductionCompleteState", "ItemsArrivingState",
           "LowFuelState", "CraftPatrolState")
ERRORS = ("ErrorMessageState",)

# layout: (the alien player's machine, game mode, lobby key)
LAYOUTS = {
    "host_xcom": ("client", 2, "53271"),
    "host_aliens": ("host", 3, "53272"),
}


def stack(gc):
    return [s.split("::")[-1] for s in session.states(gc)]


def top(gc):
    st = stack(gc)
    return st[-1] if st else ""


def window(gc):
    """The top window as the player sees it: its state, shown and hidden buttons, and texts."""
    r = gc.ok({"cmd": "list_widgets"})
    shown, hidden, texts = [], [], []
    for w in r.get("widgets", []):
        text = w.get("text")
        if not text:
            continue
        if str(w.get("type", "")).endswith("::TextButton"):
            (shown if w.get("visible") is True else hidden).append(text)
        elif w.get("visible") is True:
            texts.append(text)
    return {"state": str(r.get("state", "")).split("::")[-1], "shown": shown, "hidden": hidden, "texts": texts}


def shows(win, caption):
    return any(caption in str(b).upper() for b in win["shown"])


def balance(win):
    """(the balance line, its digits after '$') of a monthly report window."""
    for t in win["texts"]:
        if str(t).startswith("Balance"):
            after = t.split("$", 1)[1] if "$" in t else ""
            return t, "".join(ch for ch in after if ch.isdigit() or ch == "-")
    return None, ""


class Layout:
    def __init__(self, name, alien_player, mode, key):
        self.name, self.mode, self.key = name, mode, key
        self.alien_player = alien_player
        self.host = GameClient("host", None, make_user_dir(f"pvp_alien_screens_{name}_host", mods=[MOD_DIR]))
        self.client = GameClient("client", None, make_user_dir(f"pvp_alien_screens_{name}_client", mods=[MOD_DIR]))
        self.fails = []
        self.windows = {"host": [], "client": []}  # every watched window read, per machine
        self.cursors = {}

    @property
    def alien(self):
        return self.client if self.alien_player == "client" else self.host

    @property
    def xcom(self):
        return self.host if self.alien_player == "client" else self.client

    def both(self):
        return (self.host, self.client)

    def fail(self, cell, msg):
        print(f"FAIL {self.name} {cell}: {msg}", flush=True)
        self.fails.append(f"{self.name} {cell}: {msg}")

    def ok(self, cell, msg):
        print(f"PASS {self.name} {cell}: {msg}", flush=True)

    def pushes(self, gc, cursor):
        events, _ = geo._read_coop_ui(gc, cursor)
        return [typ for op, typ, _ in events if op == "push"]

    def own_world_machines(self):
        """The host, and the client while it runs a world of its own (not a replica)."""
        out = [self.host]
        if not self.client.ok({"cmd": "get_coop"}).get("campaignReplica"):
            out.append(self.client)
        return out

    # ---- popups ---------------------------------------------------------------------------

    def handle_top(self, gc):
        """Read a watched window on top of `gc`, then close whatever popup is on top."""
        t = top(gc)
        if not t or t == "GeoscapeState" or t in SELF_CLOSING:
            return
        if t in WATCHED:
            session.wait_widget_ready(gc, "OK" if t == "MonthlyReportState" else "CANCEL", timeout=OPEN_S)
            win = window(gc)
            if win["state"] == t:
                win["gameMinutes"] = geo.game_minutes(gc)
                self.windows[gc.name].append(win)
                print(f"EVIDENCE {self.name} {gc.name} {t}: shown={win['shown']} hidden={win['hidden']} "
                      f"texts={[x for x in win['texts'] if not str(x).startswith('The council')]}", flush=True)
        gc.cmd({"cmd": "dismiss_popup"})

    def seen(self, gc, state):
        return [w for w in self.windows[gc.name] if w["state"] == state]

    def advance(self, label, speed_idx, done, real_s, game_min=None):
        """Run both clocks at `speed_idx`, reading and closing popups, until done() or a bound."""
        t_end = time.time() + real_s
        start = geo.game_minutes(self.host)
        while True:
            for gc in self.both():
                self.handle_top(gc)
            if done():
                break
            now = geo.game_minutes(self.host)
            if time.time() > t_end or (game_min and start is not None and now is not None and now - start > game_min):
                print(f"EVIDENCE {self.name} {label}: bound reached after {now - start if None not in (now, start) else '?'} "
                      f"game minutes; stacks host={stack(self.host)[-3:]} client={stack(self.client)[-3:]}", flush=True)
                break
            for gc in self.both():
                if top(gc) == "GeoscapeState":
                    gc.cmd({"cmd": "geo_set_speed", "idx": speed_idx})
            time.sleep(POLL_S)
        geo.slow_clock(*self.both())

    def to_geoscape(self, label, bound=SETTLE_S):
        """Close popups until both machines show the Geoscape on two reads in a row."""
        t_end = time.time() + bound
        steady = 0
        while time.time() < t_end:
            for gc in self.both():
                self.handle_top(gc)
            if all(top(gc) == "GeoscapeState" for gc in self.both()):
                steady += 1
                if steady >= 2:
                    return True
            else:
                steady = 0
            time.sleep(0.3)
        print(f"EVIDENCE {self.name} {label}: not both on the Geoscape after {bound}s: "
              f"host={stack(self.host)} client={stack(self.client)}", flush=True)
        return False

    # ---- setup ----------------------------------------------------------------------------

    def bring_up(self):
        print(f"\n--- {self.name}: the {self.alien_player} plays the aliens (game mode {self.mode}) ---", flush=True)
        print(f"EVIDENCE {self.name} cpu at boot {harness.cpu_load()}", flush=True)
        for gc in self.both():
            gc.spawn()
            gc.connect()
        gm = pvp_fixture.start_pvp_campaign(self.host, self.client, self.key, alien_player=self.alien_player)
        if gm != self.mode:
            raise RuntimeError(f"{self.name}: game mode {gm}, expected {self.mode}")
        geo.slow_clock(*self.both())
        for gc in self.both():
            gc.ok({"cmd": "set_seed", "seed": SEED})
        pinned = {}
        for gc in self.both():
            for ev in gc.ok({"cmd": "geo_events"}).get("events", []):
                if not ev.get("over"):
                    gc.ok({"cmd": "set_event_countdown", "name": ev["name"], "minutes": EVENT_PUSH_MIN})
                    pinned.setdefault(gc.name, []).append(ev["name"])
        print(f"EVIDENCE {self.name} pending Geoscape events pushed past the run: {pinned or 'none'}", flush=True)
        self.cursors["run"] = {gc.name: geo._log_cursor(gc) for gc in self.both()}

    # ---- cells ----------------------------------------------------------------------------

    def dead_buttons(self):
        cell = "dead_buttons"
        xcom, alien = self.xcom, self.alien
        t0 = time.time()
        click = session.click_widget_ready(xcom, "INTERCEPT")
        opened = xcom.wait_for("the X-COM machine's interception window",
                               lambda: top(xcom) == "InterceptState" or None, timeout=OPEN_S, interval=0.02)
        opened_s = round(time.time() - t0, 2)
        session.click_widget_ready(xcom, "CANCEL")
        xcom.wait_for("the X-COM machine back on the Geoscape", lambda: top(xcom) == "GeoscapeState" or None,
                      timeout=OPEN_S)
        print(f"EVIDENCE {self.name} control: INTERCEPT on the X-COM machine opened InterceptState in {opened_s}s "
              f"({click.get('text')!r})", flush=True)
        bad = []
        for caption in ("INTERCEPT", "BASES"):
            before = stack(alien)
            cursor = geo._log_cursor(alien)
            click = session.click_widget_ready(alien, caption)
            if not click.get("ok"):
                bad.append(f"{caption}: no visible button to click ({click})")
                continue
            changed = None
            end = time.time() + OBSERVE_S
            while time.time() < end:
                now = stack(alien)
                if now != before:
                    changed = now
                    break
                time.sleep(0.05)
            pushed = self.pushes(alien, cursor)
            if changed or pushed:
                bad.append(f"{caption}: stack {before} -> {changed or stack(alien)}, pushed {pushed}")
                self.to_geoscape(f"after {caption}")
            else:
                print(f"EVIDENCE {self.name} {caption} on the alien machine: stack stays {before} for {OBSERVE_S}s, "
                      f"nothing pushed", flush=True)
        if bad:
            self.fail(cell, "; ".join(bad))
        else:
            self.ok(cell, "INTERCEPT and BASES open nothing on the alien machine; the Geoscape stays on top")

    def xcom_actions(self):
        """The X-COM player starts a research project and buys an item on its own machine; the host gets an
        undetected UFO and terror site beside the X-COM base."""
        xcom = self.xcom

        def xcom_base():
            for b in xcom.ok({"cmd": "geo_state"}).get("bases", []):
                if b.get("name") == BASE:
                    return b
            raise RuntimeError(f"{self.name}: the X-COM machine has no {BASE}")

        topics = xcom.ok({"cmd": "available_research", "base": BASE})["topics"]
        if not topics:
            raise RuntimeError(f"{self.name}: precondition: no research topic available at {BASE}")
        topic = topics[0]
        xcom.ok({"cmd": "research_start", "topic": topic, "scientists": 2, "base": BASE})
        xcom.wait_for(f"research {topic} running on the X-COM machine",
                      lambda: any(p["name"] == topic for p in xcom_base()["research"]) or None,
                      timeout=ACTION_S, interval=0.1)
        cost = {gc.name: gc.cmd({"cmd": "set_research_cost", "topic": topic, "cost": 1, "base": BASE}).get("found")
                for gc in self.own_world_machines()}
        if not any(cost.values()):
            raise RuntimeError(f"{self.name}: precondition: no machine runs research {topic}: {cost}")
        xcom.ok({"cmd": "buy", "item": ITEM, "count": 1, "base": BASE})
        xcom.wait_for(f"{ITEM} on the way to {BASE}",
                      lambda: any(t.get("rule") == ITEM for t in xcom_base()["transfers"]) or None,
                      timeout=ACTION_S, interval=0.1)
        self.to_geoscape("after the X-COM player's research and purchase")
        geo.slow_clock(*self.both())
        b = xcom_base()
        ufo = self.host.ok({"cmd": "spawn_ufo", **UFO, "lon": b["lon"] + 0.05, "lat": b["lat"] + 0.03})
        site = self.host.ok({"cmd": "spawn_mission_site", **SITE, "lon": b["lon"] - 0.3, "lat": b["lat"] + 0.2})
        print(f"EVIDENCE {self.name} X-COM research {topic} cost 1 on {cost}; bought {ITEM}; host UFO "
              f"{ufo.get('unique_id')} and site {site.get('site_id')} spawned undetected beside {BASE} "
              f"({b['lon']:.3f}, {b['lat']:.3f})", flush=True)

    def detection_window(self):
        xcom, alien = self.xcom, self.alien
        cursor = self.cursors["run"][xcom.name]

        def done():
            xp = self.pushes(xcom, cursor)
            return ("ResearchCompleteState" in xp and "ItemsArrivingState" in xp
                    and self.seen(xcom, "UfoDetectedState") and self.seen(alien, "UfoDetectedState")
                    and self.seen(alien, "MissionDetectedState"))
        self.advance("detection and notices", 4, done, WINDOWS_S, WINDOWS_MIN)

    def month_end(self):
        geo.slow_clock(*self.both())
        dated = self.own_world_machines()
        for gc in dated:
            gc.ok({"cmd": "set_geo_day", "day": 28, "hour": 12})
        print(f"EVIDENCE {self.name} date set to the 28th on {[gc.name for gc in dated]}", flush=True)

        def done():
            return self.seen(self.alien, "MonthlyReportState") and self.seen(self.xcom, "MonthlyReportState")
        self.advance("month end", 5, done, MONTH_S)

    def check_windows(self):
        alien, xcom = self.alien, self.xcom
        # ufo_window
        cell = "ufo_window"
        a_ufo, x_ufo = self.seen(alien, "UfoDetectedState"), self.seen(xcom, "UfoDetectedState")
        with_intercept = [w for w in a_ufo if shows(w, "INTERCEPT")]
        if not a_ufo:
            self.fail(cell, f"the alien machine showed no UFO window (X-COM machine showed {len(x_ufo)})")
        elif with_intercept:
            self.fail(cell, f"{len(with_intercept)} of {len(a_ufo)} UFO windows on the alien machine show INTERCEPT: "
                            f"{with_intercept[0]}")
        elif not any(shows(w, "INTERCEPT") for w in x_ufo):
            self.fail(cell, f"control: no UFO window on the X-COM machine shows INTERCEPT ({len(x_ufo)} windows: "
                            f"{x_ufo[:1]})")
        else:
            self.ok(cell, f"{len(a_ufo)} UFO window(s) on the alien machine, INTERCEPT hidden in each "
                          f"(control: X-COM machine's window shows INTERCEPT)")
        # mission_window
        cell = "mission_window"
        a_site = self.seen(alien, "MissionDetectedState")
        with_intercept = [w for w in a_site if shows(w, "INTERCEPT")]
        if not a_site:
            self.fail(cell, "the alien machine showed no mission window")
        elif with_intercept:
            self.fail(cell, f"{len(with_intercept)} of {len(a_site)} mission windows on the alien machine show "
                            f"INTERCEPT: {with_intercept[0]}")
        else:
            self.ok(cell, f"{len(a_site)} mission window(s) on the alien machine, INTERCEPT hidden in each "
                          f"({[w['texts'][:2] for w in a_site]})")
        # month_report
        cell = "month_report"
        a_rep, x_rep = self.seen(alien, "MonthlyReportState"), self.seen(xcom, "MonthlyReportState")
        if not a_rep:
            self.fail(cell, "the alien machine showed no monthly report")
        else:
            line, digits = balance(a_rep[0])
            x_line, x_digits = balance(x_rep[0]) if x_rep else (None, "")
            print(f"EVIDENCE {self.name} monthly report: alien {a_rep[0]['texts'][:6]} / X-COM "
                  f"{x_rep[0]['texts'][:6] if x_rep else None}", flush=True)
            if digits != "1000":
                self.fail(cell, f"the alien machine's balance line reads {line!r}, expected $1,000")
            elif not x_digits or x_digits == "1000":
                self.fail(cell, f"control: the X-COM machine's balance line reads {x_line!r}")
            else:
                self.ok(cell, f"the alien machine shows X-COM's monthly report with balance {line!r} "
                              f"(X-COM machine: {x_line!r})")

    def check_notices(self):
        cell = "no_notices"
        alien, xcom = self.alien, self.xcom
        a_push = self.pushes(alien, self.cursors["run"][alien.name])
        x_push = self.pushes(xcom, self.cursors["run"][xcom.name])
        print(f"EVIDENCE {self.name} pushed since the bring-up: alien {a_push} / X-COM {x_push}", flush=True)
        a_notices = [t for t in a_push if t in NOTICES]
        missing = [t for t in ("ResearchCompleteState", "ItemsArrivingState") if t not in x_push]
        if a_notices:
            self.fail(cell, f"the alien machine showed X-COM notices {a_notices}")
        elif missing:
            self.fail(cell, f"control: the X-COM machine never showed {missing}")
        else:
            self.ok(cell, "the X-COM machine showed research-complete and item-arrival windows; the alien machine "
                          "showed no research, production, arrival or base notice")

    def check_end(self):
        cell = "end_clean"
        on_geo = self.to_geoscape("end of the run")
        bad = []
        for gc in self.both():
            st = stack(gc)
            errors = [t for t in self.pushes(gc, self.cursors["run"][gc.name]) if t in ERRORS]
            if not st or st[-1] != "GeoscapeState" or "CoopState" in st or errors:
                bad.append(f"{gc.name} stack {st}, error windows pushed {errors}")
        if bad or not on_geo:
            self.fail(cell, "; ".join(bad) or "not both on the Geoscape")
        else:
            self.ok(cell, "both machines end on the Geoscape with no error dialog")

    def run(self):
        self.bring_up()
        self.dead_buttons()
        self.xcom_actions()
        self.detection_window()
        self.month_end()
        self.to_geoscape("after the month end")
        self.check_windows()
        self.check_notices()
        self.check_end()


def main():
    wanted = sys.argv[1:] or list(LAYOUTS)
    unknown = [w for w in wanted if w not in LAYOUTS]
    if unknown:
        print(f"unknown layouts {unknown}; layouts are {list(LAYOUTS)}")
        sys.exit(2)
    fails, verdicts = [], []
    t0 = time.time()
    for name in wanted:
        layout = Layout(name, *LAYOUTS[name])
        t_layout = time.time()
        try:
            layout.run()
        except Exception as e:  # noqa: BLE001 - reported as the layout's failure
            print(f"[ERROR] {name}: {e!r}", flush=True)
            layout.fails.append(f"{name}: {e!r}")
        finally:
            try:
                harness.shutdown_clients(layout.host, layout.client)
            except RuntimeError as e:
                layout.fails.append(f"{name}: {e}")
        fails += layout.fails
        verdicts.append(f"{'PASS' if not layout.fails else 'FAIL'} {name} ({time.time() - t_layout:.1f}s)")
    print(f"\n==== PvP campaign alien player screens summary ({time.time() - t0:.1f}s) ====")
    for v in verdicts:
        print(f"  {v}")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  both layouts: the alien player's dead buttons, detection windows, monthly report, "
          "missing notices and clean end hold")
    sys.exit(0)


if __name__ == "__main__":
    main()
