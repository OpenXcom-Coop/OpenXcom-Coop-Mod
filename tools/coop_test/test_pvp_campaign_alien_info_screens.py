"""PvP campaign: the alien player's information screens, checked on the machine that runs the world.

The host plays X-COM and the client plays the aliens (game mode 2). Every input and every read is on the HOST: the
alien_view test command shows the host's screens as the alien player sees them (process-wide, never saved), so each
rule is checked against the world it reads, with X-COM's real research beside it.

The rules, with the view on:
  the Ufopaedia lists only the articles that need no research (the starting set), whatever X-COM has researched;
  the tech tree shows no topic as researched and nothing as unlocked by research; it still opens (key Q);
  the Funding screen shows X-COM's real country funding;
  X-COM's production, research, prisoner and pilot lists open from no key and no link;
  the Notes screen (X-COM's notes, kept in the campaign) opens from no route: Ctrl+N and the Links window on the
  Geoscape, and Ctrl+N, the Links window and the inventory's Links window in battle.
The view is read-only: no row changes X-COM's research or funds.

Rows and cells (one line per assertion; "off" lines are the controls with the view off):
  host_world: stage, pedia_control, pedia_starting_set, pedia_screen, tech_tree, tech_tree_key, funding_real,
    lists_closed, notes_closed, world_unchanged (after every row);
  host_battle (the host's own battle, entered from the campaign): notes_closed.

Run:  py -3 tools/coop_test/test_pvp_campaign_alien_info_screens.py
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

LAYOUT = "host_xcom"
KEY = "53351"
SEED = 241
EVENT_PUSH_MIN = 60 * 24 * 90  # pending Geoscape events wait 90 days: past the end of the run

# an article that needs exactly one research topic; the first of these whose topic X-COM has not researched yet
ARTICLE_CANDIDATES = ("STR_LASER_PISTOL", "STR_LASER_RIFLE", "STR_HEAVY_LASER", "STR_MEDI_KIT", "STR_MOTION_SCANNER")

# default key bindings (Options.cpp)
SYM = {"P": 112, "C": 99, "J": 106, "E": 101, "Q": 113, "I": 105, "N": 110, "ESC": 27}
LIST_KEYS = (("P", "GlobalManufactureState"), ("C", "GlobalResearchState"),
             ("J", "GlobalAlienContainmentState"), ("E", "DogfightExperienceState"))
LIST_LINKS = (("PRODUCTION OVERVIEW", "GlobalManufactureState"), ("RESEARCH OVERVIEW", "GlobalResearchState"),
              ("DAILY PILOT EXPERIENCE", "DogfightExperienceState"))
LINKS_RECTS = ((213, 0, 23, 22), (213, 1, 23, 22))  # InventoryState's Links button (two layouts)
SHOW_LAYERS_COLUMN = 5  # the Battlescape's top icon row: unit up, map up, map, inventory, next soldier, layers / Links

UFOPAEDIA_BUTTON = "UFOP"  # the Geoscape's button: "UFOPEDIA" (xcom1) or "UFOPAEDIA"

OPEN_S = 5.0       # a window opening after a click or key
NOTHING_S = 1.5    # an input that must open nothing is watched this long
POLL_S = 0.05


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


class Stop(Exception):
    pass


class AlienScreens:
    def __init__(self):
        self.host = GameClient("host", None, make_user_dir("pvp_alien_info_host"))
        self.client = GameClient("client", None, make_user_dir("pvp_alien_info_client"))
        self.fails = []
        self.row = "host_world"
        self.article = None
        self.topic = None
        self.section = None
        self.section_text = None
        self.funds = None

    # ---- output ---------------------------------------------------------------------------

    def check(self, cell, label, cond, values=""):
        verdict = "PASS" if cond else "FAIL"
        line = f"{verdict} {self.row} {cell}: {label}" + (f" ({values})" if values != "" else "")
        print(line, flush=True)
        if not cond:
            self.fails.append(line)

    def evidence(self, msg):
        print(f"EVIDENCE {self.row} {msg}", flush=True)

    # ---- probes ---------------------------------------------------------------------------

    def view(self, on):
        return self.host.ok({"cmd": "alien_view", "on": on})

    def screens(self, ids=None):
        return self.host.ok({"cmd": "alien_screens", "ids": list(ids or ([self.article] if self.article else []))})

    def option(self, name, value):
        return self.host.ok({"cmd": "set_option", "name": name, "value": value})

    def key(self, sym, mod=None):
        req = {"cmd": "inject_input", "kind": "key", "key": sym}
        if mod:
            req["mod"] = mod
        self.host.ok(req)
        if mod:
            self.host.cmd({"cmd": "inject_input", "kind": "modstate", "mod": "none"})

    # ---- screens --------------------------------------------------------------------------

    def back_to(self, base, label):
        """Close windows above `base` (OK / CANCEL, else Escape); logged."""
        for _ in range(8):
            t = top(self.host)
            if t == base:
                return True
            self.evidence(f"{label}: closing {t}")
            for caption in ("OK", "CANCEL"):
                if session.wait_widget_ready(self.host, caption, timeout=0.5) is not None:
                    self.host.cmd({"cmd": "click_widget", "match": caption})
                    break
            else:
                self.key(SYM["ESC"])
            wait(lambda: top(self.host) != t, 2.0)
        return top(self.host) == base

    def opened_by(self, action, base):
        """Run `action` with `base` on top; the stack it changed to within NOTHING_S (None = unchanged)."""
        before = stack(self.host)
        action()
        changed = wait(lambda: stack(self.host) != before, NOTHING_S)
        if not changed:
            return None
        wait(lambda: False, 0.3)  # a link window pops itself before its target is pushed
        return stack(self.host)

    def link_click(self, caption, base="GeoscapeState"):
        """FUNDING opens the Links window (oxceLinks on); click `caption` there. The stack after it settles."""
        session.click_widget_ready(self.host, "FUNDING", timeout=OPEN_S)
        if not wait(lambda: top(self.host) == "ExtendedGeoscapeLinksState", OPEN_S):
            return ["links window did not open"] + stack(self.host)
        session.click_widget_ready(self.host, caption, timeout=OPEN_S)
        wait(lambda: top(self.host) != "ExtendedGeoscapeLinksState", OPEN_S)
        wait(lambda: False, NOTHING_S)
        return stack(self.host)

    # ---- setup ----------------------------------------------------------------------------

    def bring_up(self):
        print(f"\n--- {LAYOUT}: the host plays X-COM; the host's screens are shown as the alien player sees them ---",
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
        self.option("oxceLinks", False)
        self.back_to("GeoscapeState", "after the bring-up")

    def world(self):
        g = self.host.ok({"cmd": "geo_state"})
        r = self.host.ok({"cmd": "is_researched", "topic": self.topic})
        return {"funds": g.get("funds"), "worldFunds": g.get("worldFunds"), "researched": r.get("researched")}

    # ---- rows -----------------------------------------------------------------------------

    def stage(self):
        cell = "stage"
        self.view(False)
        before = self.screens(ARTICLE_CANDIDATES)["ids"]
        for a in ARTICLE_CANDIDATES:
            e = before.get(a) or {}
            if len(e.get("requires") or []) == 1 and e.get("worldReleases") is False:
                self.article, self.topic = a, e["requires"][0]
                self.section, self.section_text = e["section"], e["sectionText"]
                break
        if not self.article:
            raise Stop(f"no candidate article needs exactly one topic X-COM has not researched: {before}")
        self.evidence(f"article {self.article} (topic {self.topic}, section {self.section} '{self.section_text}')")
        for gc in (self.host, self.client):
            gc.ok({"cmd": "discover_research", "topic": self.topic})
        after = self.screens()["ids"][self.article]
        self.check(cell, "host: the world's research releases the article after the topic is discovered",
                   after.get("worldReleases") is True, after)

    def pedia_control(self):
        cell = "pedia_control"
        self.view(False)
        s = self.screens()
        self.check(cell, "off: the article is listed, and at least one listed article needs research",
                   s["ids"][self.article]["listed"] is True and s["listedNeedingResearch"] >= 1,
                   f"listed {s['ids'][self.article]['listed']}, needing research {s['listedNeedingResearch']}, "
                   f"articles {len(s['articles'])}")

    def pedia_starting_set(self):
        cell = "pedia_starting_set"
        self.view(True)
        s = self.screens()
        self.view(False)
        self.check(cell, "on: the article is not listed, no listed article needs research, the list is the starting set",
                   s["alienView"] is True and s["ids"][self.article]["listed"] is False
                   and s["listedNeedingResearch"] == 0 and len(s["articles"]) == s["startingSet"],
                   f"alienView {s['alienView']}, listed {s['ids'][self.article]['listed']}, needing research "
                   f"{s['listedNeedingResearch']}, articles {len(s['articles'])}, starting set {s['startingSet']}")

    def _section_rows(self):
        r = session.click_widget_ready(self.host, UFOPAEDIA_BUTTON, timeout=OPEN_S)
        if not wait(lambda: top(self.host) == "UfopaediaStartState", OPEN_S):
            return None, f"the Ufopaedia button opened {top(self.host)} ({r.get('error')})"
        r = session.click_widget_ready(self.host, self.section_text, timeout=OPEN_S)
        if not wait(lambda: top(self.host) == "UfopaediaSelectState", OPEN_S):
            return None, f"section button opened {top(self.host)} ({r.get('error')})"
        p = self.host.ok({"cmd": "pedia_state"})
        return p.get("rows") or [], f"{len(p.get('rows') or [])} rows"

    def pedia_screen(self):
        cell = "pedia_screen"
        counts = {}
        for mode in ("on", "off"):
            self.view(mode == "on")
            probe = self.screens()["articlesPerSection"].get(self.section)
            rows, note = self._section_rows()
            counts[mode] = {"rows": None if rows is None else len(rows), "probe": probe, "note": note}
            self.back_to("GeoscapeState", f"after the {self.section} list ({mode})")
        self.view(False)
        on, off = counts["on"], counts["off"]
        self.check(cell, "on: the section lists as many articles as the probe and fewer than with the view off",
                   on["rows"] is not None and on["rows"] == on["probe"] and off["rows"] is not None
                   and on["rows"] < off["rows"], f"on {on}, off {off}")

    def tech_tree(self):
        cell = "tech_tree"
        self.view(True)
        on = self.screens()["techTree"]
        self.view(False)
        off = self.screens()["techTree"]
        self.check(cell, "on: no topic researched, no item unlocked, no more productions or craft than with the view off",
                   on["research"] == 0 and on["items"] == 0 and on["manufacture"] <= off["manufacture"]
                   and on["crafts"] <= off["crafts"], f"on {on}, off {off}")
        self.check(cell, "off: X-COM's research shows (at least one topic)", off["research"] >= 1, off)

    def tech_tree_key(self):
        cell = "tech_tree_key"
        self.view(True)
        after = self.opened_by(lambda: self.key(SYM["Q"]), "GeoscapeState")
        self.check(cell, "on: key Q opens the tech tree", bool(after) and after[-1] == "TechTreeViewerState",
                   after or "stack unchanged")
        self.back_to("GeoscapeState", "after the tech tree")
        self.view(False)

    def _funding_rows(self):
        session.click_widget_ready(self.host, "FUNDING", timeout=OPEN_S)
        if not wait(lambda: top(self.host) == "FundingState", OPEN_S):
            return None, top(self.host)
        rows = self.screens()["topRows"]
        self.back_to("GeoscapeState", "after Funding")
        return rows, "FundingState"

    def funding_real(self):
        cell = "funding_real"
        self.view(True)
        on, on_top = self._funding_rows()
        self.view(False)
        off, off_top = self._funding_rows()
        self.check(cell, "on: FUNDING opens the Funding screen with the same country rows as with the view off",
                   on is not None and len(on) > 1 and on == off,
                   f"on {on_top} {len(on or [])} rows, off {off_top} {len(off or [])} rows, first {(on or [''])[0]!r}, "
                   f"total {(on or [''])[-1]!r}")

    def lists_closed(self):
        cell = "lists_closed"
        for mode in ("on", "off"):
            self.view(mode == "on")
            for name, state in LIST_KEYS:
                after = self.opened_by(lambda name=name: self.key(SYM[name]), "GeoscapeState")
                if mode == "on":
                    self.check(cell, f"on: key {name} opens nothing", after is None,
                               f"stack became {after}" if after else f"stack unchanged {NOTHING_S}s")
                else:
                    self.check(cell, f"off: key {name} opens {state}", bool(after) and after[-1] == state,
                               after or "stack unchanged")
                if after:
                    self.back_to("GeoscapeState", f"after key {name} ({mode})")
            self.option("oxceLinks", True)
            for caption, state in LIST_LINKS:
                after = self.link_click(caption)
                if mode == "on":
                    self.check(cell, f"on: Links > {caption} opens nothing", after == ["GeoscapeState"], after)
                else:
                    self.check(cell, f"off: Links > {caption} opens {state}", after[-1] == state, after)
                self.back_to("GeoscapeState", f"after Links > {caption} ({mode})")
            self.option("oxceLinks", False)
        self.view(False)

    def notes_closed(self):
        cell = "notes_closed"
        for mode in ("on", "off"):
            self.view(mode == "on")
            after = self.opened_by(lambda: self.key(SYM["N"], mod="ctrl"), "GeoscapeState")
            self.report_notes(cell, mode, "Ctrl+N on the Geoscape", after, "GeoscapeState")
            self.option("oxceLinks", True)
            after = self.link_click("NOTES")
            self.report_notes(cell, mode, "Links > NOTES on the Geoscape", after, "GeoscapeState")
            self.option("oxceLinks", False)
        self.view(False)

    def report_notes(self, cell, mode, route, after, base):
        if mode == "on":
            self.check(cell, f"on: {route} opens nothing", not after or after[-1] == base, after or "stack unchanged")
        else:
            self.check(cell, f"off: {route} opens the notes", bool(after) and after[-1] == "NotesState",
                       after or "stack unchanged")
        if after and after[-1] != base:
            self.back_to(base, f"after {route} ({mode})")

    def world_unchanged(self, after):
        cell = "world_unchanged"
        try:
            now = self.world()
            forced = self.host.ok({"cmd": "alien_view"}).get("forced")
            self.check(cell, f"after {after}: topic still researched, funds unchanged, view off",
                       now["researched"] is True and now["funds"] == self.funds["funds"] and forced is False,
                       f"now {now}, at start {self.funds}, forced {forced}")
        except (KeyError, TypeError) as e:
            self.check(cell, f"after {after}: probe read", False, repr(e))

    # ---- battle ---------------------------------------------------------------------------

    def enter_battle(self):
        """The host's craft lands on a mission site; both machines reach the Battlescape (the campaign battle
        recipe of test_pvp_campaign_battle)."""
        hg = self.host.ok({"cmd": "geo_state"})
        b0 = next((b for b in hg.get("bases", []) if not b.get("coopBase")), None)
        if not b0:
            raise Stop("no X-COM base on the host")
        cid = next((c["id"] for c in b0.get("crafts", []) if "SKYRANGER" in c.get("type", "")), None)
        sb = next((b for b in self.host.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
        if cid is None or not sb or len(sb.get("soldiers", [])) < 2:
            raise Stop(f"no Skyranger or fewer than 2 soldiers: craft {cid}, soldiers {sb}")
        sids = [s["id"] for s in sb["soldiers"]]
        for sid in sids:
            self.host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False})
        for sid in sids[:2]:
            self.host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})
        site = self.host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_RESEARCH", "deployment": "STR_MEDIUM_SCOUT",
                             "lon": b0["lon"] + 0.35, "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})
        self.host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT", "lon": b0["lon"] + 0.34,
                      "lat": b0["lat"] + 0.10, "dest": f"site:{site['site_id']}", "fuel": 999999, "lowFuel": False})

        def prompt():
            if session.has_state(self.host, "ConfirmLandingState"):
                return True
            for gc in (self.host, self.client):
                geo.drain_popups(gc, interest=geo.popup("ConfirmLandingState"))
                gc.cmd({"cmd": "geo_set_speed", "idx": 2})
            return None

        self.host.wait_for("landing prompt", prompt, timeout=180, interval=0.5)
        self.host.ok({"cmd": "confirm_landing"})
        for gc in (self.host, self.client):
            gc.wait_for("entered battle", lambda gc=gc: gc.cmd({"cmd": "battle_state"}).get("inBattle") or None,
                        timeout=180, interval=0.5)
        session.briefings_to_battlescape(self.host, self.client)
        for gc in (self.host, self.client):
            gc.wait_for("tactical", lambda gc=gc: session.has_state(gc, "BattlescapeState") or None,
                        timeout=120, interval=0.2)
        self.back_to("BattlescapeState", "after the battle start")

    def click_rect(self, pick, label):
        """click_widget by index: the visible interactive widget `pick` chooses from the top state's list."""
        ws = [w for w in self.host.ok({"cmd": "list_widgets"}).get("widgets") or []
              if w.get("visible") and w.get("interactive")]
        nth = pick(ws)
        if nth is None:
            self.evidence(f"{label}: no such button on {top(self.host)}")
            return False
        self.host.ok({"cmd": "click_widget", "nth": nth})
        return True

    @staticmethod
    def show_layers(ws):
        row = [(w["x"], i) for i, w in enumerate(ws) if (w.get("w"), w.get("h")) == (32, 16)
               and str(w.get("type", "")).endswith("BattlescapeButton")]
        if not row:
            return None
        y0 = min(ws[i]["y"] for _, i in row)
        top_row = sorted((x, i) for x, i in row if ws[i]["y"] == y0)
        return top_row[SHOW_LAYERS_COLUMN][1] if len(top_row) > SHOW_LAYERS_COLUMN else None

    @staticmethod
    def inventory_links(ws):
        return next((i for i, w in enumerate(ws) if (w.get("x"), w.get("y"), w.get("w"), w.get("h")) in LINKS_RECTS), None)

    def battle_link_notes(self, opener, links_state, base, label):
        """`opener` opens the Links window over `base`; click its Notes. The stack after it settles."""
        if not opener():
            return [f"no {label} button"] + stack(self.host)
        if not wait(lambda: top(self.host) == links_state, OPEN_S):
            return [f"{label} opened no Links window"] + stack(self.host)
        session.click_widget_ready(self.host, "Notes", timeout=OPEN_S)
        wait(lambda: top(self.host) != links_state, OPEN_S)
        wait(lambda: False, NOTHING_S)
        return stack(self.host)

    def battle_notes_closed(self):
        cell = "notes_closed"
        self.option("oxceLinks", True)
        self.evidence(f"oxceReplaceNotesLink {self.host.ok({'cmd': 'set_option', 'name': 'oxceReplaceNotesLink'}).get('value')}")
        base = "BattlescapeState"
        for mode in ("on", "off"):
            self.view(mode == "on")
            after = self.opened_by(lambda: self.key(SYM["N"], mod="ctrl"), base)
            self.report_notes(cell, mode, "Ctrl+N in battle", after, base)
            after = self.battle_link_notes(lambda: self.click_rect(self.show_layers, "Links"),
                                           "ExtendedBattlescapeLinksState", base, "Battlescape Links")
            self.report_notes(cell, mode, "Links > Notes in battle", after, base)
            self.key(SYM["I"])
            if not wait(lambda: top(self.host) == "InventoryState", OPEN_S):
                self.check(cell, f"{mode}: the inventory opens for the Links window", False, stack(self.host))
                self.back_to(base, f"after the inventory key ({mode})")
                continue
            after = self.battle_link_notes(lambda: self.click_rect(self.inventory_links, "inventory Links"),
                                           "ExtendedInventoryLinksState", "InventoryState", "inventory Links")
            self.report_notes(cell, mode, "inventory Links > Notes", after, "InventoryState")
            self.back_to(base, f"after the inventory ({mode})")
        self.view(False)
        forced = self.host.ok({"cmd": "alien_view"}).get("forced")
        self.check("world_unchanged", "after notes_closed in battle: view off", forced is False, f"forced {forced}")

    # ---- run ------------------------------------------------------------------------------

    def run(self):
        self.bring_up()
        self.stage()
        self.funds = self.world()
        self.evidence(f"world at start {self.funds}")
        self.world_unchanged("stage")
        for row in (self.pedia_control, self.pedia_starting_set, self.pedia_screen, self.tech_tree, self.tech_tree_key,
                    self.funding_real, self.lists_closed, self.notes_closed):
            self.back_to("GeoscapeState", f"before {row.__name__}")
            try:
                row()
            except (KeyError, TypeError, IndexError) as e:
                self.check(row.__name__, "row ran", False, repr(e))
                self.view(False)
                self.back_to("GeoscapeState", f"after {row.__name__}")
            self.world_unchanged(row.__name__)
        self.row = "host_battle"
        self.enter_battle()
        try:
            self.battle_notes_closed()
        except (KeyError, TypeError, IndexError) as e:
            self.check("notes_closed", "row ran", False, repr(e))


def main():
    t0 = time.time()
    run = AlienScreens()
    try:
        run.run()
    except Exception as e:  # noqa: BLE001 - reported as the run's failure
        print(f"[ERROR] {run.row}: {e!r}", flush=True)
        run.fails.append(f"{run.row}: {e!r}")
    finally:
        try:
            run.host.cmd({"cmd": "alien_view", "on": False})
        except Exception:  # noqa: BLE001 - the process may be gone
            pass
        try:
            harness.shutdown_clients(run.host, run.client)
        except RuntimeError as e:
            run.fails.append(f"{LAYOUT}: {e}")
    print(f"\n==== PvP campaign alien information screens summary ({time.time() - t0:.1f}s) ====")
    if run.fails:
        for f in run.fails:
            print(f"  {f}")
        sys.exit(2)
    print("  the alien player's Ufopaedia and tech tree show only what needs no research, Funding stays real, "
          "X-COM's lists and notes stay closed, and nothing in the world changes")
    sys.exit(0)


if __name__ == "__main__":
    main()
