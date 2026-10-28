"""a saved hotseat battle loads back as hotseat.

Spec: docs rewrite/prompts/d247u_hotseat_battle.md, (f) `test_hotseat_save.py`, with the orchestrator rulings of session
42155bc1 (R-D247-SC-1..2, docs rewrite/w2-resume-42155bc1/ruling-d247uc.md). Pins and the load route: docs
rewrite/d247u-task0/sc/CONSTANTS.md (TASK 0 boots Ca / Cb); MISSION / RACE / SEED_A / A / A_DEST from rewrite/d247u-task0/sa/.

TWO single-player processes on ONE user dir (label 49114, dir d247u_c; the label is not a port with a user dir), no co-op session.
Process 1: bring-up (open_new_battle, newbattle_mission, newbattle_race, newbattle_hotseat on, set_seed SEED_A, newbattle_ok,
close_briefing, the start overlays), X-COM END, the "Side: Aliens" screen (FX_STASH = X-COM's map), close it, player 2's real-UI
walk of A to A_DEST (FA_SAVE = player 2's map), the real F5 quicksave (`save_game_ui {type quick_battle}`), quit. Process 2, same
dir, the real load route: the LOAD button's `hidden` false, click_widget "Load Game", the list's `hidden` false, a
click on the quicksave's row (found by its NAME in vanilla's order: reserved saves first, newest file time first; only row 0 is
clickable, the row height is not readable), BattlescapeState on top with A on A_DEST (the turn-1 autosave has A elsewhere).
Rows (one EVIDENCE line per row, one PASS/FAIL line per cell, the row verdict; a failed precondition FAILs "blocked: <reason>"):
  common  save-common: 0 new crash files (lane crash folder); battle_state.coopSession false (process 1)
  S1  S1-armed (get_coop.hotseat true), S1-turn (side 0, turn 1, every live alien faction 0), S1-fog (player 2's map == FA_SAVE)
  S2  END, the side-0 screen, close, settle (<= 10 s): S2-handback (turn 2, side 0, every live unit faction == originalFaction),
      S2-fogX (X-COM's map has every bit of FX_STASH). Another side's screen first = "blocked"; a settle timeout = "not settled".
a battle save writes only non-void tiles (SavedBattleGame::save; Tile::isVoid: no part, smoke or item), so
both map cells read only the non-void tiles (tile_census of every level + battle_items on tiles, in the loaded battle) and print
the void-tile difference count as EVIDENCE.
Red (C1, the S-B green build): S1-armed, S2-handback, S2-fogX FAIL; S1-turn, S1-fog, save-common PASS. Exit 0 only when every cell
passes, else 2 (WV-D99 / WV-D100: one run, no SKIP, no exit 3). run it in the foreground to completion.

Run: python tools/coop_test/test_hotseat_save.py
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402

# Pins (CONSTANTS.md; S54 swaps logged there)
MISSION, RACE, SEED_A = "STR_LARGE_SCOUT", "STR_SECTOID", 2
A, A_DEST = 1000004, (16, 36, 0)
LABEL, UDIR = 49114, "d247u_c"
QUICK, LOAD_BUTTON = "_quick_.asav", "Load Game"
RESERVED = ("_quick_.asav", "_autogeo_", "_autobattle_")

SDLK_HOME, SDLK_TAB = 278, 9
CELLS = {
    "common": ["save-common"],
    "S1": ["S1-armed", "S1-turn", "S1-fog"],
    "S2": ["S2-handback", "S2-fogX"],
}
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
    d = harness.CRASH_DIR
    return set(os.listdir(d)) if os.path.isdir(d) else set()


def udir_path():
    return os.path.join(harness.TEST_ROOT, "s%d_%s" % (harness.HARNESS_SLOT, UDIR))


def nfloor(bits):
    return sum(1 for i in range(len(bits) // 2) if int(bits[2 * i:2 * i + 2], 16) & 4)


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

    def bits(self):
        return self.gc.ok({"cmd": "reveal_state", "bits": True})["playerBits"]

    def widgets(self):
        return self.gc.cmd({"cmd": "list_widgets"}).get("widgets", [])

    def texts(self):
        return [w.get("text") for w in self.widgets() if w.get("text")]

    def units(self):
        return {u["id"]: u for u in self.bst().get("units", [])}

    def wait(self, desc, pred, timeout, interval=0.1):
        end = time.time() + timeout
        while time.time() < end:
            v = pred()
            if v:
                return v
            time.sleep(interval)
        raise TimeoutError("timed out: " + desc)

    def shown(self, pick, timeout=5):
        """poll until the widget `pick` selects is visible and not hidden (a POPUP window hides every surface
        until its popup ends). -> the widget, or None on timeout."""
        end = time.time() + timeout
        while time.time() < end:
            w = [x for x in self.widgets() if pick(x)]
            if w and w[0].get("visible") and not w[0].get("hidden"):
                return w[0]
            time.sleep(0.05)
        return None

    def capture(self, tag):
        c = {}
        try:
            b = self.bst()
            c["stack"] = self.states()
            c["battle"] = {k: b.get(k) for k in ("inBattle", "turn", "side", "selectedId", "isBusy", "pendingStates")}
            c["coop"] = {k: v for k, v in self.gc.cmd({"cmd": "get_coop"}).items() if k in ("hotseat", "hotseatReactionFire")}
        except Exception as e:  # noqa: BLE001
            c["error"] = repr(e)
        try:
            with open(os.path.join(udir_path(), "openxcom.log"), encoding="utf-8", errors="replace") as f:
                c["log"] = f.read().splitlines()[-40:]
        except OSError as e:
            c["log"] = ["<no log: %s>" % e]
        print("CAPTURE %s: %s" % (tag, json.dumps(c)), flush=True)

    def select(self, uid, tries=24):
        for _ in range(tries):
            if self.bst().get("selectedId") == uid:
                return True
            self.gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
            time.sleep(0.15)
        return self.bst().get("selectedId") == uid

    def walk(self, uid, tile, timeout=15):
        """The real-UI walk: TAB select, HOME, map_tile_click_pos (verified), a left click. -> (ok, record)."""
        rec = {"unit": uid, "to": list(tile)}
        if not self.select(uid):
            rec["fail"] = "select"
            return False, rec
        self.gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
        time.sleep(0.2)
        pr = self.gc.cmd({"cmd": "map_tile_click_pos", "x": tile[0], "y": tile[1], "z": tile[2]})
        if not (pr.get("ok") and pr.get("verified")):
            rec["fail"] = "click_pos %s" % pr.get("error")
            return False, rec
        u = self.units()[uid]
        rec["from"], rec["tu0"] = [u["x"], u["y"], u["z"]], u["tu"]
        self.gc.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
        end = time.time() + timeout
        while time.time() < end:
            b = self.bst()
            u = {v["id"]: v for v in b.get("units", [])}.get(uid)
            if u and (u["x"], u["y"], u["z"]) == tuple(tile) and not b.get("isBusy"):
                rec["tu1"] = u["tu"]
                return u["tu"] < rec["tu0"], rec
            time.sleep(0.15)
        rec["fail"] = "no arrival in %d s" % timeout
        return False, rec

    def popups(self, st, seen):
        if st and st[-1] in ("InfoboxState", "InfoboxOKState"):
            seen.append({"state": st[-1], "texts": self.texts()})
            self.gc.cmd({"cmd": "dismiss_popup"})
            return True
        return False

    def settle(self, timeout=10):
        """<= timeout: isBusy false and no NextTurnState on the stack. -> (settled, battle_state, stack, popups)."""
        time.sleep(0.1)
        end = time.time() + timeout
        b, st, pops = {}, [], []
        while time.time() < end:
            b, st = self.bst(), self.states()
            if self.popups(st, pops):
                continue
            if not b.get("isBusy") and "NextTurnState" not in st:
                return True, b, st, pops
            time.sleep(0.1)
        return False, b, st, pops

    def next_screen(self, timeout):
        """Poll every 0.1 s until a NextTurnState is on top. -> its battle_state, or None."""
        end, pops = time.time() + timeout, []
        while time.time() < end:
            st = self.states()
            if self.popups(st, pops):
                continue
            if st and st[-1] == "NextTurnState":
                return self.bst()
            time.sleep(0.1)
        return None

    def nonvoid(self):
        """the tile indexes a battle save writes (Tile::isVoid false): any part, smoke or an item on the tile."""
        fd = self.gc.ok({"cmd": "find_doors", "limit": 0})
        X, Y, Z = fd["mapSizeX"], fd["mapSizeY"], fd["mapSizeZ"]
        items = {(it["tx"], it["ty"], it["tz"]) for it in self.gc.ok({"cmd": "battle_items"})["items"] if it.get("onTile")}
        idx = set()
        for z in range(Z):
            r = self.gc.ok({"cmd": "tile_census", "x0": 0, "x1": X - 1, "y0": 0, "y1": Y - 1, "z0": z, "z1": z})
            for t in r["tiles"]:
                if not t:
                    continue
                p = (t["x"], t["y"], t["z"])
                parts = any(t["parts"][k]["mapDataID"] != -1 for k in ("floor", "westwall", "northwall", "object"))
                if parts or t["smoke"] or p in items:
                    idx.add(p[2] * X * Y + p[1] * X + p[0])
        return idx, X * Y * Z


def compare(a, b, idx, n, superset):
    """a == b (or a has every bit of b) on the non-void tiles idx. -> (holds, void tiles where it does not)."""
    def ok(i):
        x, y = int(a[2 * i:2 * i + 2], 16), int(b[2 * i:2 * i + 2], 16)
        return (x & y) == y if superset else x == y
    return all(ok(i) for i in idx), sum(1 for i in range(n) if i not in idx and not ok(i))


def blocked(row, reason, ev, cap=None):
    """A row whose precondition failed: ONE capture (optional), its EVIDENCE, every cell FAILs with the reason."""
    if cap:
        cap[0].capture("%s: %s" % (row, cap[1]))
    evidence(row, **ev)
    fail_rest(row, reason)


def live(units, ofac):
    return [u for u in units.values() if u["originalFaction"] == ofac and not u["isOut"]]


def save_files():
    d = os.path.join(udir_path(), "xcom1")
    return [(n, int(os.stat(os.path.join(d, n)).st_mtime)) for n in sorted(os.listdir(d)) if n.endswith((".sav", ".asav"))]


def quick_row(files):
    """The quicksave's row in ListLoadState (ListGamesState::sortList SORT_DATE_DESC: reserved saves first, then the newest file
    time; SavedGame::getSaveInfo), found by its name. -> (row, reason); row None when it is missing or tied."""
    key = {n: (not any(r in n for r in RESERVED), -m) for n, m in files}
    if QUICK not in key:
        return None, "no %s" % QUICK
    if any(k == key[QUICK] for n, k in key.items() if n != QUICK):
        return None, "%s ties another save's sort key" % QUICK
    return sorted(key, key=lambda n: key[n]).index(QUICK), ""


def main():
    crash0 = crash_files()
    gc = harness.GameClient("d247u_c", LABEL, harness.make_user_dir(UDIR))
    B = Boot(gc)
    ctx = {"gc2": None}
    coop_session = None
    try:
        # ---- bring-up, process 1 (a miss here FAILs every row "boot" with ONE CAPTURE line) ----
        try:
            gc.spawn()
            gc.connect()
            gc.ok({"cmd": "open_new_battle"})
            B.wait("NewBattleState", lambda: session.has_state(gc, "NewBattleState"), 60)
            gc.ok({"cmd": "newbattle_mission", "type": MISSION})
            gc.ok({"cmd": "newbattle_race", "race": RACE})
            if gc.ok({"cmd": "newbattle_hotseat", "on": True}).get("hotseat") is not True:
                raise RuntimeError("newbattle_hotseat did not arm hotseat")
            gc.ok({"cmd": "set_seed", "seed": SEED_A})
            gc.ok({"cmd": "newbattle_ok"})
            B.wait("BriefingState", lambda: session.has_state(gc, "BriefingState"), 180, 0.25)
            gc.ok({"cmd": "close_briefing"})
            B.wait("equip screen", lambda: session.has_state(gc, "InventoryState"), 30, 0.2)
            session.dismiss_battle_start_overlays(gc)
            B.wait("BattlescapeState on top", lambda: B.top() == "BattlescapeState", 30)
        except Exception as e:  # noqa: BLE001
            B.capture("boot C: %r" % e)
            for row in ("S1", "S2"):
                fail_rest(row, "boot")
                verdict(row)
            return
        coop_session = B.bst().get("coopSession")
        print("bring-up done %.1f s" % (time.time() - T0), flush=True)
        for name, fn in (("S1", row_s1), ("S2", row_s2)):
            try:
                fn(B, ctx)
            except Exception as e:  # noqa: BLE001
                bb = ctx.get("B2") or B
                bb.capture("%s: %r" % (name, e))
                fail_rest(name, "error: %r" % e)
            verdict(name)
    finally:
        for g in (gc, ctx.get("gc2")):
            if g is None:
                continue
            try:
                g.shutdown()
            except Exception as e:  # noqa: BLE001
                print("shutdown: %r" % e, flush=True)
        new = sorted(crash_files() - crash0)
        evidence("common", newCrashFiles=new, coopSession=coop_session, loadedCoopSession=ctx.get("loadedCoopSession"),
                 wall=round(time.time() - T0, 1))
        cell("save-common", not new and coop_session is False, "new crash files %s, coopSession %r" % (new, coop_session))
        verdict("common")


def row_s1(B, ctx):
    ev = {}
    gc = B.gc
    gc.ok({"cmd": "battle_action", "action": "end_turn_button"})
    nts = B.next_screen(40)
    if not nts or nts.get("side") != 1:
        ev["screen"] = nts and [nts.get("side"), nts.get("turn")]
        return blocked("S1", "blocked: no 'Side: Aliens' screen in 40 s", ev, (B, "no side-1 screen"))
    ctx["FX_STASH"] = fx = B.bits()
    ev["ntsTexts"] = B.texts()
    gc.ok({"cmd": "close_nextturn"})
    settled, b, st, pops = B.settle(10)
    us = {u["id"]: u for u in b.get("units", [])}
    ev["p2"] = {"settled": settled, "side": b.get("side"), "turn": b.get("turn"), "selectedId": b.get("selectedId"), "stack": st,
                "popups": pops, "aliens": {u["id"]: u["faction"] for u in live(us, 1)}}
    if not (settled and b.get("side") == 0 and all(u["faction"] == 0 for u in live(us, 1))):
        return blocked("S1", "blocked: player 2's turn did not start (settled %r side %r)" % (settled, b.get("side")), ev)
    ok, ev["walk"] = B.walk(A, A_DEST)
    if not ok:
        return blocked("S1", "blocked: A's walk failed (%s)" % ev["walk"].get("fail"), ev)
    ctx["FA_SAVE"] = fa = B.bits()
    ev["faFloor"], ev["fxFloor"] = nfloor(fa), nfloor(fx)
    t_req = time.time()
    gc.ok({"cmd": "save_game_ui", "type": "quick_battle"})
    qpath = os.path.join(udir_path(), "xcom1", QUICK)
    try:
        B.wait("quicksave written", lambda: "SaveGameState" not in B.states() and os.path.exists(qpath)
               and os.stat(qpath).st_mtime >= t_req - 1, 20)
    except TimeoutError:
        return blocked("S1", "blocked: no %s written in 20 s" % QUICK, ev, (B, "no quicksave"))
    gc.shutdown()  # quit process 1; its engine log is kept beside the second process's
    log = os.path.join(udir_path(), "openxcom.log")
    if os.path.exists(log):
        shutil.copyfile(log, os.path.join(udir_path(), "openxcom_p1.log"))
    ev["files"] = save_files()

    # ---- process 2 on the same user dir: the real load route ----
    gc2 = ctx["gc2"] = harness.GameClient("d247u_c_load", LABEL, udir_path())
    B2 = ctx["B2"] = Boot(gc2)
    gc2.spawn()
    gc2.connect()
    B2.wait("MainMenuState on top", lambda: B2.top() == "MainMenuState", 60)
    if not B2.shown(lambda w: w.get("text") == LOAD_BUTTON):
        return blocked("S1", "button not shown: %s (stack %s)" % (LOAD_BUTTON, B2.states()), ev, (B2, "LOAD button not shown"))
    c = ev["loadClick"] = gc2.ok({"cmd": "click_widget", "match": LOAD_BUTTON})
    try:
        B2.wait("ListLoadState on top", lambda: B2.top() == "ListLoadState", 10)
    except TimeoutError:
        return blocked("S1", "blocked: the load list did not open (stack %s)" % B2.states(), ev, (B2, "no load list"))
    lst = B2.shown(lambda w: "TextList" in w.get("type", ""))
    row, why = quick_row(ev["files"])
    ev["list"], ev["quickRow"] = lst and {k: lst[k] for k in ("x", "y", "w", "h")}, row
    if not lst or row != 0:
        return blocked("S1", "button not shown: the load list" if not lst else "blocked: the quicksave is not row 0 (row %r %s)"
                       % (row, why), ev, (B2, "load list"))
    sx, sy = c["winX"] / float(c["baseX"]), c["winY"] / float(c["baseY"])
    wx, wy = int((lst["x"] + lst["w"] / 2.0) * sx), int((lst["y"] + 3) * sy)  # row 0: the top line of the list
    ev["rowClick"] = [wx, wy]
    gc2.ok({"cmd": "inject_input", "kind": "click", "x": wx, "y": wy, "button": "left"})
    try:
        B2.wait("BattlescapeState after the load", lambda: B2.states()[-1:] == ["BattlescapeState"]
                and "LoadGameState" not in B2.states(), 30)
    except TimeoutError:
        return blocked("S1", "blocked: the load did not reach BattlescapeState (stack %s)" % B2.states(), ev, (B2, "load"))
    time.sleep(0.3)
    b = B2.bst()
    us = {u["id"]: u for u in b.get("units", [])}
    hs = gc2.ok({"cmd": "get_coop"}).get("hotseat")
    ctx["loadedCoopSession"] = b.get("coopSession")
    a = us.get(A, {})
    ev["loaded"] = {"stack": B2.states(), "hotseat": hs, "side": b.get("side"), "turn": b.get("turn"),
                    "selectedId": b.get("selectedId"), "A": [a.get("x"), a.get("y"), a.get("z")],
                    "aliens": {u["id"]: u["faction"] for u in live(us, 1)}}
    if (a.get("x"), a.get("y"), a.get("z")) != A_DEST:
        return blocked("S1", "blocked: the loaded battle is not the quicksave (A at %s)" % ev["loaded"]["A"], ev)
    p2 = B2.bits()
    idx, n = B2.nonvoid()
    ctx.update(idx=idx, n=n, loaded=True)
    eq, voidd = compare(p2, fa, idx, n, False)
    ev["fog"] = {"nonVoidTiles": len(idx), "loadedFloor": nfloor(p2), "voidTilesDiffering": voidd}
    evidence("S1", **ev)
    cell("S1-armed", hs is True, "hotseat %r" % hs)
    al = live(us, 1)
    cell("S1-turn", b.get("side") == 0 and b.get("turn") == 1 and al and all(u["faction"] == 0 for u in al),
         "side %r turn %r alien factions %s" % (b.get("side"), b.get("turn"), [u["faction"] for u in al]))
    cell("S1-fog", eq, "player 2's map == FA_SAVE on %d non-void tiles: %r (void tiles differing %d)" % (len(idx), eq, voidd))


def row_s2(B, ctx):
    if not ctx.get("loaded"):
        return blocked("S2", "blocked: the quicksave was never loaded (S1)", {"reason": "S1"})
    B2 = ctx["B2"]
    B2.gc.ok({"cmd": "battle_action", "action": "end_turn_button"})
    nts = B2.next_screen(60)
    if not nts or nts.get("side") != 0:
        ev = {"screen": nts and [nts.get("side"), nts.get("turn")], "texts": B2.texts() if nts else None, "stack": B2.states()}
        return blocked("S2", "blocked: the side-%s screen came first (the X-COM screen never came)"
                       % (nts.get("side") if nts else "none"), ev)
    nts_txt = B2.texts()
    B2.gc.ok({"cmd": "close_nextturn"})
    settled, b, st, pops = B2.settle(10)
    xm = B2.bits() if b.get("inBattle") else ""
    us = {u["id"]: u for u in b.get("units", [])}
    mism = [[u["id"], u["faction"], u["originalFaction"]] for u in us.values() if not u["isOut"] and u["faction"] != u["originalFaction"]]
    sup, voidd = compare(xm, ctx["FX_STASH"], ctx["idx"], ctx["n"], True) if xm else (False, None)
    evidence("S2", ntsSide=nts.get("side"), ntsTurn=nts.get("turn"), ntsTexts=nts_txt, settled=settled, side=b.get("side"),
             turn=b.get("turn"), stack=st, popups=pops, mismatch=mism, xFloor=nfloor(xm),
             fxFloor=nfloor(ctx["FX_STASH"]), voidTilesMissing=voidd)
    if not settled:  # no vacuous pass after a timed-out settle
        fail_rest("S2", "not settled in 10 s: side %r turn %r busy %r stack %s" % (b.get("side"), b.get("turn"), b.get("isBusy"), st))
        return
    cell("S2-handback", b.get("turn") == 2 and b.get("side") == 0 and not mism,
         "turn %r side %r faction mismatches %s" % (b.get("turn"), b.get("side"), mism))
    cell("S2-fogX", sup, "X-COM's map has FX_STASH on %d non-void tiles: %r (void tiles missing %r)" % (len(ctx["idx"]), sup, voidd))


if __name__ == "__main__":
    main()
    failed = [n for row in CELLS.values() for n in row if not RES.get(n)]
    print("\nSUMMARY: %d/%d cells PASS; FAIL: %s (%.1f s)" % (len(RES) - len(failed), sum(len(v) for v in CELLS.values()),
                                                           failed, time.time() - T0), flush=True)
    sys.exit(0 if not failed else 2)
