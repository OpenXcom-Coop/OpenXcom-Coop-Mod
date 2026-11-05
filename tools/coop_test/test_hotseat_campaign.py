"""Issue #136: hotseat in a single-player campaign, started from the geoscape.

In a campaign, hotseat only covers the battles: the geoscape stays single player. Player 1 commands X-COM,
and when X-COM ends its turn player 2 takes the aliens on the same computer; when the aliens' turn ends,
control returns to X-COM. The campaign's way in is the geoscape's OPTIONS > CO-OP > HOST window, whose
connection-type combo offers HOTSEAT MODE, then ENABLE HOTSEAT (and the REACTION FIRE toggle). New Battle
has its own HOTSEAT toggle (test_hotseat_start.py); this file covers the campaign.

ONE single-player instance (label 49136, user dir hotseat_campaign), no co-op session.

Bring-up: New Game (solo) > OK > first base > geoscape. Rows (one EVIDENCE line per row, one PASS/FAIL line per
cell, then the row verdict; a row whose precondition failed FAILs its cells "blocked: <reason>"):
  entry: OPTIONS and CO-OP clicked on screen; the HOST window is on top (entry-dialog), its combo offers HOTSEAT
      MODE (entry-offer); picking it shows ENABLE HOTSEAT and ENABLE REACTION FIRE and hides START HOST
      (entry-pick); clicking ENABLE HOTSEAT arms hotseat and the button reads DISABLE HOTSEAT (entry-arm); CANCEL,
      CANCEL returns to the geoscape with hotseat still armed (entry-back).
  battle_start: the 3 lowest-id soldiers on the Skyranger, a terror site beside the base, the landing prompt's YES
      after set_seed SEED, the briefing, the battle-start overlays. battle_start-armed: hotseat armed at the
      battlescape, turn 1, X-COM's side, no co-op session, every unit on its real faction.
  first_handover: X-COM's END TURN, the aliens' turn screen, close it, settle. -side (the active side reads
      X-COM's, turn 1), -swap (aliens on the player faction, soldiers on the alien one), -select (an alien is
      selected, every live alien selectable, no soldier), -noai (no alien has an AI, none moved or spent TU).
  handback: player 2's END TURN, X-COM's turn-2 screen, close it, settle. -turn (screen side 0 turn 2), -real
      (every live unit on its real faction).
  second_handover: X-COM's END TURN again, the aliens' screen, close, settle. second_handover-swap.
  battle_end: player 2 aborts the mission. -debrief (the debriefing on top, 0 new crash files), -real (0 soldiers
      killed or missing, the soldier page lists the squad), -disarm (the debriefing disarms hotseat, as it does
      for a New Battle).
  geoscape: the debriefing's OK, back on the geoscape. -back (geoscape on top, 0 new crash files), -roster (every
      squad soldier is still in the base roster and the roster size is unchanged).
  common: campaign-common, 0 new crash files over the whole run.
On a build without the campaign entry, entry-offer and every later cell FAIL. Exit 0 only when every cell passes,
else 2 (one run, no SKIP).

Run: python tools/coop_test/test_hotseat_campaign.py
"""
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402

LABEL, UDIR = 49136, "hotseat_campaign"
SEED = 7
SQUAD = 3
HOTSEAT_OPTION = "HOTSEAT MODE"
CELLS = {
    "entry": ["entry-dialog", "entry-offer", "entry-pick", "entry-arm", "entry-back"],
    "battle_start": ["battle_start-armed"],
    "first_handover": ["first_handover-side", "first_handover-swap", "first_handover-select", "first_handover-noai"],
    "handback": ["handback-turn", "handback-real"],
    "second_handover": ["second_handover-swap"],
    "battle_end": ["battle_end-debrief", "battle_end-real", "battle_end-disarm"],
    "geoscape": ["geoscape-back", "geoscape-roster"],
    "common": ["campaign-common"],
}
ORDER = ["entry", "battle_start", "first_handover", "handback", "second_handover", "battle_end", "geoscape"]
RES = {}
T0 = time.time()


def cell(name, ok, detail=""):
    if name in RES:
        return
    RES[name] = bool(ok)
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)


def fail_rest(row, reason):
    for n in CELLS[row]:
        cell(n, False, reason)


def evidence(row, **kv):
    print("EVIDENCE %s: %s" % (row, json.dumps(kv, default=str)), flush=True)


def verdict(row):
    ok = all(RES.get(n) for n in CELLS[row])
    print("ROW %s: %s (%.1f s)" % (row, "PASS" if ok else "FAIL", time.time() - T0), flush=True)


def crash_files():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))


class Blocked(Exception):
    pass


class Boot:
    def __init__(self, gc):
        self.gc = gc

    def states(self):
        return [s.replace("class OpenXcom::", "") for s in session.states(self.gc)]

    def top(self):
        s = self.states()
        return s[-1] if s else ""

    def bst(self):
        return self.gc.cmd({"cmd": "battle_state"})

    def units(self):
        return {u["id"]: u for u in self.bst().get("units", [])}

    def buttons(self):
        """Captions of the top state's visible, not hidden TextButtons (what the player can press)."""
        r = self.gc.cmd({"cmd": "list_widgets"})
        return [w.get("text") for w in r.get("widgets", []) if str(w.get("type", "")).endswith("::TextButton")
                and w.get("visible") and not w.get("hidden") and w.get("text")]

    def texts(self):
        r = self.gc.cmd({"cmd": "list_widgets"})
        return [w.get("text") for w in r.get("widgets", []) if w.get("visible") and w.get("text")]

    def wait(self, desc, pred, timeout, interval=0.1):
        end = time.time() + timeout
        while time.time() < end:
            v = pred()
            if v:
                return v
            time.sleep(interval)
        raise TimeoutError("timed out: " + desc)

    def click(self, caption):
        r = session.click_widget_ready(self.gc, caption)
        if not r.get("ok"):
            raise Blocked("no '%s' button on %s: %s" % (caption, self.top(), r.get("error")))
        return r

    def drain_one(self, keep=()):
        top = self.top()
        if "GeoscapeState" in top or any(k in top for k in keep):
            return
        self.gc.cmd({"cmd": "dismiss_popup", "keep": list(keep)})

    def log_tail(self, n=40):
        p = os.path.join(harness.TEST_ROOT, "s%d_%s" % (harness.HARNESS_SLOT, UDIR), "openxcom.log")
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                return f.read().splitlines()[-n:]
        except OSError as e:
            return ["<no log: %s>" % e]

    def capture(self, tag):
        c = {}
        try:
            b = self.bst()
            c["stack"] = self.states()
            c["battle"] = {k: b.get(k) for k in ("inBattle", "turn", "side", "selectedId", "isBusy", "pendingStates")}
            c["coop"] = {k: v for k, v in self.gc.cmd({"cmd": "get_coop"}).items()
                         if k in ("hotseat", "coopStatic", "serverOwner")}
            c["buttons"] = self.buttons()
        except Exception as e:  # noqa: BLE001
            c["error"] = repr(e)
        c["log"] = self.log_tail()
        print("CAPTURE %s: %s" % (tag, json.dumps(c)), flush=True)

    def wait_nts(self, side, timeout):
        """Poll until a NextTurnState is on top with battle_state.side == side."""
        end = time.time() + timeout
        while time.time() < end:
            b = self.bst()
            if self.top() == "NextTurnState" and b.get("side") == side:
                return b
            time.sleep(0.1)
        return None

    def settle(self, timeout=10):
        """<= timeout: isBusy false and no NextTurnState on the stack. -> (settled, battle_state, stack)."""
        time.sleep(0.1)
        end = time.time() + timeout
        b, st = {}, []
        while time.time() < end:
            b, st = self.bst(), self.states()
            if st and st[-1] in ("InfoboxState", "InfoboxOKState"):
                evidence("popup", state=st[-1], texts=self.texts())
                self.gc.cmd({"cmd": "dismiss_popup"})
                continue
            if not b.get("isBusy") and "NextTurnState" not in st:
                return True, b, st
            time.sleep(0.1)
        return False, b, st

    def end_turn_to(self, side, timeout):
        """END TURN, then the turn screen of `side`; returns that screen's battle_state (None on a miss)."""
        self.gc.ok({"cmd": "battle_action", "action": "end_turn_button"})
        return self.wait_nts(side, timeout)


def live(units, ofac):
    return [u for u in units.values() if u["originalFaction"] == ofac and not u["isOut"]]


def swapped(units):
    """Every live alien faction 0 / original 1, every live soldier faction 1 / original 0."""
    bad = [[u["id"], u["faction"], u["originalFaction"]] for u in live(units, 1) if u["faction"] != 0]
    bad += [[u["id"], u["faction"], u["originalFaction"]] for u in live(units, 0) if u["faction"] != 1]
    return not bad, bad


def real(units):
    return [[u["id"], u["faction"], u["originalFaction"]] for u in units.values()
            if not u["isOut"] and u["faction"] != u["originalFaction"]]


# ---- geoscape helpers ----

def base0(gc):
    for b in gc.ok({"cmd": "geo_state"})["bases"]:
        if not b.get("coopBase") and not b.get("coopIcon"):
            return b
    raise Blocked("no own base on the geoscape")


def skyranger(gc):
    for c in base0(gc)["crafts"]:
        if "SKYRANGER" in c["type"]:
            return c
    raise Blocked("no Skyranger at the base")


def roster(gc):
    for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
        if not b["coopBaseFlag"] and not b.get("coopIcon"):
            return b
    raise Blocked("no own base in get_soldiers")


def bring_up(B):
    gc = B.gc
    gc.ok({"cmd": "open_new_game", "mode": "solo"})
    B.wait("NewGameState", lambda: session.has_state(gc, "NewGameState"), 30)
    gc.ok({"cmd": "newgame_ok"})
    B.wait("BuildNewBaseState", lambda: session.has_state(gc, "BuildNewBaseState"), 60)
    r = gc.cmd({"cmd": "place_first_base", "lon": session.HOST_LON, "lat": session.HOST_LAT, "name": "HotseatBase"})
    if not r.get("ok"):
        gc.ok({"cmd": "place_first_base", "lon": harness.LAND_LON, "lat": harness.LAND_LAT, "name": "HotseatBase"})

    def on_geoscape():
        if B.top() == "GeoscapeState":
            return True
        B.drain_one()
        return None
    B.wait("geoscape on top", on_geoscape, 30, 0.5)
    gc.ok({"cmd": "geo_set_speed", "idx": 0})


def row_entry(B, ctx):
    gc = B.gc
    path = [B.top()]
    B.click("OPTIONS")
    B.wait("PauseState on top", lambda: B.top() == "PauseState", 10)
    path.append(B.top())
    B.click("CO-OP")
    B.wait("a state over PauseState", lambda: B.top() != "PauseState", 10)
    path.append(B.top())
    session.wait_widget_ready(gc, "CANCEL")  # the popup window shows its buttons once it has opened
    hm = gc.cmd({"cmd": "host_menu_state"})
    evidence("entry", path=path, hostMenu=hm, buttons=B.buttons())
    if B.top() != "HostMenu":
        fail_rest("entry", "blocked: CO-OP opened %s, not the HOST window" % B.top())
        return
    cell("entry-dialog", True, "path %s" % path)
    opts = hm.get("visibilityOptions") or []
    cell("entry-offer", HOTSEAT_OPTION in opts, "combo options %s" % opts)
    if HOTSEAT_OPTION not in opts:
        fail_rest("entry", "blocked: the HOST window offers no %s" % HOTSEAT_OPTION)
        return
    gc.ok({"cmd": "host_menu_visibility", "label": HOTSEAT_OPTION})
    picked = B.buttons()
    cell("entry-pick", "ENABLE HOTSEAT" in picked and "ENABLE REACTION FIRE" in picked and "START HOST" not in picked,
         "buttons %s" % picked)
    B.click("ENABLE HOTSEAT")
    armed = B.wait("hotseat armed", lambda: gc.ok({"cmd": "get_coop"}).get("hotseat") is True, 5)
    after = B.buttons()
    evidence("entry_arm", buttons=after, texts=B.texts())
    cell("entry-arm", armed and "DISABLE HOTSEAT" in after and "ENABLE HOTSEAT" not in after,
         "hotseat %r, buttons %s" % (armed, after))
    B.click("CANCEL")
    B.wait("PauseState on top", lambda: B.top() == "PauseState", 10)
    B.click("CANCEL")
    B.wait("geoscape on top", lambda: B.top() == "GeoscapeState", 10)
    co = gc.ok({"cmd": "get_coop"})
    cell("entry-back", B.top() == "GeoscapeState" and co.get("hotseat") is True and co.get("coopStatic") is False,
         "top %s, hotseat %r, coopStatic %r" % (B.top(), co.get("hotseat"), co.get("coopStatic")))
    ctx["armed"] = co.get("hotseat") is True and B.top() == "GeoscapeState"


def row_battle_start(B, ctx):
    gc = B.gc
    if not ctx.get("armed"):
        evidence("battle_start", reason="hotseat was never armed from the geoscape")
        fail_rest("battle_start", "blocked: hotseat was never armed from the geoscape (entry)")
        return
    rb = roster(gc)
    ids = sorted(s["id"] for s in rb["soldiers"])
    ctx["roster0"] = ids
    cid = skyranger(gc)["id"]
    for sid in ids:
        gc.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False, "base": rb["name"]})
    squad = ids[:SQUAD]
    for sid in squad:
        r = gc.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True, "base": rb["name"]})
        if not r.get("seated"):
            raise Blocked("soldier %s not seated: %s" % (sid, r))
    ctx["squad"] = squad
    ctx["squadNames"] = sorted(s["name"] for s in rb["soldiers"] if s["id"] in squad)
    b0 = base0(gc)
    gc.ok({"cmd": "set_seed", "seed": SEED})
    site = gc.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION",
                  "lon": b0["lon"] + 0.35, "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})
    sid_ = site["site_id"]
    B.wait("site listed", lambda: any(s["id"] == sid_ for s in gc.ok({"cmd": "geo_state"})["missionSites"]), 30)
    gc.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT", "lon": b0["lon"] + 0.34,
           "lat": b0["lat"] + 0.10, "dest": "site:%d" % sid_, "fuel": 999999, "lowFuel": False})
    end = time.time() + 60
    while B.top() != "ConfirmLandingState":
        if time.time() > end:
            raise Blocked("the craft never reached the site (stack %s)" % B.states()[-3:])
        B.drain_one(keep=("ConfirmLandingState",))
        gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        time.sleep(0.5)
    gc.ok({"cmd": "set_seed", "seed": SEED})
    gc.ok({"cmd": "confirm_landing"})
    B.wait("BriefingState", lambda: session.has_state(gc, "BriefingState"), 120, 0.25)
    gc.ok({"cmd": "close_briefing"})
    B.wait("BattlescapeState", lambda: session.has_state(gc, "BattlescapeState"), 60, 0.2)
    session.dismiss_battle_start_overlays(gc, timeout=20)
    B.wait("BattlescapeState on top", lambda: B.top() == "BattlescapeState", 30)
    b = B.bst()
    us = {u["id"]: u for u in b.get("units", [])}
    co = gc.ok({"cmd": "get_coop"})
    ctx["coopSession"] = b.get("coopSession")
    mism = real(us)
    evidence("battle_start", site=sid_, squad=squad, hotseat=co.get("hotseat"), turn=b.get("turn"), side=b.get("side"),
             coopSession=b.get("coopSession"), liveAliens=len(live(us, 1)), soldiers=len(live(us, 0)), mismatch=mism,
             missionType=b.get("missionType"))
    ok = (co.get("hotseat") is True and b.get("turn") == 1 and b.get("side") == 0 and b.get("coopSession") is False
          and not mism and live(us, 1))
    cell("battle_start-armed", ok, "hotseat %r turn %r side %r coopSession %r mismatch %s live aliens %d"
         % (co.get("hotseat"), b.get("turn"), b.get("side"), b.get("coopSession"), mism, len(live(us, 1))))
    ctx["battle"] = ok


def row_first_handover(B, ctx):
    if not ctx.get("battle"):
        fail_rest("first_handover", "blocked: no armed hotseat battle (battle_start)")
        return
    nts = B.end_turn_to(1, 60)
    if not nts:
        B.capture("first_handover: no aliens' turn screen")
        fail_rest("first_handover", "blocked: no aliens' turn screen in 60 s")
        return
    scr = {u["id"]: (u["x"], u["y"], u["z"], u["direction"], u["tu"]) for u in nts["units"]
           if u["originalFaction"] == 1 and not u["isOut"]}
    B.gc.ok({"cmd": "close_nextturn"})
    settled, b, st = B.settle(10)
    us = {u["id"]: u for u in b.get("units", [])}
    evidence("first_handover", ntsSide=nts.get("side"), ntsTurn=nts.get("turn"), settled=settled, side=b.get("side"),
             turn=b.get("turn"), stack=st, selectedId=b.get("selectedId"))
    if not settled:
        fail_rest("first_handover", "not settled in 10 s: side %r busy %r stack %s" % (b.get("side"), b.get("isBusy"), st))
        return
    cell("first_handover-side", b.get("side") == 0 and b.get("turn") == 1 and st[-1:] == ["BattlescapeState"],
         "side %r turn %r top %s" % (b.get("side"), b.get("turn"), st[-1:]))
    ok_swap, bad = swapped(us)
    cell("first_handover-swap", ok_swap, "wrong %s" % bad)
    sel = b.get("selectedId")
    al, so = live(us, 1), live(us, 0)
    cell("first_handover-select", sel in {u["id"] for u in al} and all(u["selectable"] for u in al)
         and not any(u["selectable"] for u in so),
         "selectedId %r, alien selectable %s, soldier selectable %s"
         % (sel, [u["selectable"] for u in al], [u["id"] for u in so if u["selectable"]]))
    now = {u["id"]: (u["x"], u["y"], u["z"], u["direction"], u["tu"]) for u in al}
    moved = {k: [scr[k], now.get(k)] for k in scr if now.get(k) != scr[k]}
    ai = [u["id"] for u in al if u["hasAI"]]
    cell("first_handover-noai", not moved and not ai, "changed %s, hasAI %s" % (moved, ai))
    ctx["p2"] = ok_swap and b.get("side") == 0


def row_handback(B, ctx):
    if not ctx.get("p2"):
        fail_rest("handback", "blocked: player 2's turn never started (first_handover)")
        return
    nts = B.end_turn_to(0, 90)
    if not nts:
        B.capture("handback: no X-COM turn screen")
        fail_rest("handback", "blocked: no X-COM turn screen in 90 s")
        return
    B.gc.ok({"cmd": "close_nextturn"})
    settled, b, st = B.settle(10)
    us = {u["id"]: u for u in b.get("units", [])}
    mism = real(us)
    evidence("handback", ntsSide=nts.get("side"), ntsTurn=nts.get("turn"), settled=settled, side=b.get("side"),
             stack=st, mismatch=mism)
    cell("handback-turn", nts.get("side") == 0 and nts.get("turn") == 2,
         "side %r turn %r" % (nts.get("side"), nts.get("turn")))
    cell("handback-real", settled and not mism, "settled %r, mismatch %s" % (settled, mism))
    ctx["p1b"] = settled and b.get("side") == 0 and not mism


def row_second_handover(B, ctx):
    if not ctx.get("p1b"):
        fail_rest("second_handover", "blocked: the hand-back did not happen (handback)")
        return
    nts = B.end_turn_to(1, 60)
    if not nts:
        B.capture("second_handover: no aliens' turn screen")
        fail_rest("second_handover", "blocked: no aliens' turn screen in 60 s")
        return
    B.gc.ok({"cmd": "close_nextturn"})
    settled, b, st = B.settle(10)
    us = {u["id"]: u for u in b.get("units", [])}
    ok_swap, bad = swapped(us)
    evidence("second_handover", settled=settled, side=b.get("side"), turn=b.get("turn"), stack=st, wrong=bad)
    cell("second_handover-swap", settled and b.get("side") == 0 and ok_swap,
         "settled %r side %r wrong %s" % (settled, b.get("side"), bad))
    ctx["p2b"] = settled and ok_swap


def row_battle_end(B, ctx):
    if not ctx.get("p2b"):
        fail_rest("battle_end", "blocked: player 2's second turn never started (second_handover)")
        return
    crash0 = crash_files()
    us = B.units()
    dead = [u["name"] for u in us.values() if u["originalFaction"] == 0 and u.get("isPlayerSoldier") and u["isOut"]]
    B.gc.ok({"cmd": "battle_action", "action": "abort"})
    B.wait("AbortMissionState", lambda: B.top() == "AbortMissionState", 10)
    dlg = B.texts()
    B.gc.ok({"cmd": "dismiss_popup"})
    B.wait("DebriefingState", lambda: B.top() == "DebriefingState", 30)
    db = B.gc.cmd({"cmd": "debrief_state"})
    rows = db.get("rows", [])

    def qty(word):
        return sum(r["qty"] for r in rows if "OPERATIVES" in r["item"].upper() and word in r["item"].upper())
    killed, mia = qty("KILLED"), qty("MISSING")
    names = sorted(s["name"] for s in db.get("soldiers", []))
    new = sorted(crash_files() - crash0)
    hs = B.gc.ok({"cmd": "get_coop"}).get("hotseat")
    evidence("battle_end", abortDialog=dlg, outBeforeAbort=dead, debriefRows=rows, debriefSoldiers=names,
             title=db.get("title"), rating=db.get("rating"))
    cell("battle_end-debrief", B.top() == "DebriefingState" and not new, "top %s, new crash files %s" % (B.top(), new))
    cell("battle_end-real", killed == 0 and mia == 0 and names == ctx["squadNames"],
         "killed %d, MIA %d, soldiers %s (squad %s)" % (killed, mia, names, ctx["squadNames"]))
    cell("battle_end-disarm", hs is False, "hotseat %r" % hs)
    ctx["debrief"] = B.top() == "DebriefingState"


def row_geoscape(B, ctx):
    if not ctx.get("debrief"):
        fail_rest("geoscape", "blocked: no debriefing (battle_end)")
        return
    crash0 = crash_files()
    B.gc.wait_for("back on the geoscape",
                  lambda: session.drain_to_geoscape(B.gc, time.time() + 2, 0.3), timeout=60, interval=0.1)
    rb = roster(B.gc)
    ids = sorted(s["id"] for s in rb["soldiers"])
    missing = [s for s in ctx["squad"] if s not in ids]
    new = sorted(crash_files() - crash0)
    evidence("geoscape", top=B.top(), roster=ids, roster0=ctx["roster0"], missing=missing)
    cell("geoscape-back", B.top() == "GeoscapeState" and not new, "top %s, new crash files %s" % (B.top(), new))
    cell("geoscape-roster", not missing and ids == ctx["roster0"],
         "squad missing %s, roster %d (was %d)" % (missing, len(ids), len(ctx["roster0"])))


ROWS = {"entry": row_entry, "battle_start": row_battle_start, "first_handover": row_first_handover,
        "handback": row_handback, "second_handover": row_second_handover, "battle_end": row_battle_end,
        "geoscape": row_geoscape}


def main():
    crash0 = crash_files()
    gc = harness.GameClient("hotseat_campaign", LABEL, harness.make_user_dir(UDIR))
    B = Boot(gc)
    ctx = {}
    try:
        try:
            gc.spawn()
            gc.connect()
            bring_up(B)
        except Exception as e:  # noqa: BLE001
            B.capture("boot: %r" % e)
            for row in ORDER:
                fail_rest(row, "boot")
                verdict(row)
            return
        print("bring-up done %.1f s" % (time.time() - T0), flush=True)
        for name in ORDER:
            try:
                ROWS[name](B, ctx)
            except Exception as e:  # noqa: BLE001
                B.capture("%s: %r" % (name, e))
                fail_rest(name, "error: %r" % e)
            verdict(name)
    finally:
        try:
            gc.shutdown()
        except Exception as e:  # noqa: BLE001
            print("shutdown: %r" % e, flush=True)
        new = sorted(crash_files() - crash0)
        evidence("common", newCrashFiles=new, coopSession=ctx.get("coopSession"), wall=round(time.time() - T0, 1))
        cell("campaign-common", not new, "new crash files %s" % new)
        verdict("common")


if __name__ == "__main__":
    main()
    failed = [n for row in CELLS.values() for n in row if not RES.get(n)]
    total = sum(len(v) for v in CELLS.values())
    print("\nSUMMARY: %d/%d cells PASS; FAIL: %s (%.1f s)" % (total - len(failed), total, failed, time.time() - T0),
          flush=True)
    sys.exit(0 if not failed else 2)
