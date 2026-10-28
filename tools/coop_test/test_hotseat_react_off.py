"""hotseat with REACT FIRE off (the default): no walk draws reaction fire, on either player's turn, and the
main menu disarms HOTSEAT. Boot B2.

Spec: docs rewrite/prompts/d247u_hotseat_battle.md, (d) Stage S-B and (f) `test_hotseat_react_off.py`. Pins: docs
rewrite/d247u-task0/sb/CONSTANTS.md (TASK 0 boots Bc / Bd on the S-A green build; every S54 swap is logged there).

ONE single-player instance (label 49113, user dir d247u_b2; the label is not a port when a user dir is given), no co-op
session. HOTSEAT is armed through the real NEW BATTLE toggle handler (`newbattle_hotseat`); REACT FIRE is left untouched
(`get_coop.hotseatReactionFire` false, a boot check).

Bring-up (boot B2): open_new_battle; newbattle_mission MISSION; newbattle_race RACE; newbattle_hotseat on; set_seed SEED_A
right before newbattle_ok; close_briefing; the battle-start overlays; BattlescapeState on top. Staging (S-B T0-4 (2)-(3),
every lever reply read, S25): AR teleported to AR_HOME facing SR_HOME, SR to SR_HOME facing AR_HOME (4 tiles apart on a
straight free line, CONSTANTS.md); SR's hands cleared and a rifle + clip given (S25: soldier loadouts vary per boot); AR
reactions 100, firing 0; every other unit reactions 0. A staging miss is a boot miss.

Rows and cells (one EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a
failure; a row whose precondition failed FAILs its cells "blocked: <reason>"; a settle that times out FAILs its value
cells "not settled", R-D247-SA-3):
  common       react_off-common  0 new crash files (lane crash folder); battle_state.coopSession false
  R1  X-COM's walk draws no reaction: the real-UI walk of SR to SR_DEST; settle. R1-walk (SR on SR_DEST, precondition),
      R1-noreact (AR's TU unchanged)
  R1b player 2's walk draws no reaction: END TURN; close_nextturn (player 2's turn); SW (= SR) reactions 100, firing 0
      (lever); the real-UI walk of AR to AR_DEST; settle. R1b-walk (AR on AR_DEST, precondition), R1b-noreact (SW's TU
      unchanged)
  AB  back to the main menu disarms HOTSEAT: Escape -> PauseState; ABANDON GAME -> AbandonGameState; YES -> MainMenuState
      (<= 30 s). Each button is clicked once its popup window has shown it (a hidden button ignores input, TASK 0 F16644).
      AB-menu (MainMenuState on top, precondition), AB-disarm (`get_coop.hotseat` false)
Every real-UI walk TABs at least once (a TAB runs calculateFOV for the selected unit, BS :1517-:1524), so the walker has
spotted what it sees before it steps; a walker that newly spots a unit halts before the walk-step reaction check (UWBS :252).

Red (B1, the S-A green base): R1-noreact, R1b-noreact, AB-disarm FAIL; R1-walk, R1b-walk, AB-menu, react_off-common PASS.
Exit 0 only when every cell passes, else 2 (WV-D99 / WV-D100: one run, no SKIP, no exit 3). run it in the
foreground to completion.

Run: python tools/coop_test/test_hotseat_react_off.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402

# Pins (CONSTANTS.md, boots Bc / Bd; S54 swaps logged there)
MISSION, RACE, SEED_A = "STR_LARGE_SCOUT", "STR_SECTOID", 2
AR, SR = 1000000, 14
SW = SR
AR_HOME, AR_DIR, AR_DEST = (5, 20, 0), 5, (4, 21, 0)
SR_HOME, SR_DIR, SR_DEST = (1, 24, 0), 1, (2, 23, 0)
SR_WEAPON, SR_AMMO = "STR_RIFLE", "STR_RIFLE_CLIP"
LABEL, UDIR = 49113, "d247u_b2"

SDLK_HOME, SDLK_TAB, SDLK_ESCAPE = 278, 9, 27
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
CELLS = {
    "common": ["react_off-common"],
    "R1": ["R1-walk", "R1-noreact"],
    "R1b": ["R1b-walk", "R1b-noreact"],
    "AB": ["AB-menu", "AB-disarm"],
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


def ub(u, keys=("x", "y", "z", "direction", "tu", "health", "status", "isOut", "faction", "hasAI", "weapon")):
    return {k: u.get(k) for k in keys} if u else None


def at(u, tile):
    return bool(u) and (u.get("x"), u.get("y"), u.get("z")) == tuple(tile)


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

    def texts(self):
        r = self.gc.cmd({"cmd": "list_widgets"})
        return [w.get("text") for w in r.get("widgets", []) if w.get("text")]

    def units(self):
        return {u["id"]: u for u in self.bst().get("units", [])}

    def lev(self, req):
        r = self.gc.cmd(req)
        if not r.get("ok"):
            raise RuntimeError("lever refused: %r -> %r" % (req, r))
        return r

    def wait(self, desc, pred, timeout, interval=0.1):
        end = time.time() + timeout
        while time.time() < end:
            v = pred()
            if v:
                return v
            time.sleep(interval)
        raise TimeoutError("timed out: " + desc)

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
            c["stack"] = self.states()
            b = self.bst()
            c["battle"] = {k: b.get(k) for k in ("inBattle", "turn", "side", "selectedId", "isBusy", "pendingStates")}
            c["coop"] = {k: v for k, v in self.gc.cmd({"cmd": "get_coop"}).items() if k in ("hotseat", "hotseatReactionFire")}
        except Exception as e:  # noqa: BLE001
            c["error"] = repr(e)
        c["log"] = self.log_tail()
        print("CAPTURE %s: %s" % (tag, json.dumps(c)), flush=True)

    def click_shown(self, match, timeout=5):
        """click_widget once the TextButton captioned `match` is shown: a popup window hides every surface until its popup
        ends and a hidden button ignores input (TS list_widgets `hidden`; TASK 0 F16644)."""
        end = time.time() + timeout
        while time.time() < end:
            ws = self.gc.cmd({"cmd": "list_widgets"}).get("widgets", [])
            hit = [w for w in ws if w.get("interactive") and match.lower() in (w.get("text") or "").lower()]
            if hit and hit[0].get("visible") and not hit[0].get("hidden"):
                return self.lev({"cmd": "click_widget", "match": match})
            time.sleep(0.05)
        raise TimeoutError("button %r never shown" % match)

    def select(self, uid, tries=40):
        """TAB at least once (TAB runs calculateFOV for the newly selected unit), then until uid is selected."""
        self.gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.15)
        for _ in range(tries):
            if self.bst().get("selectedId") == uid:
                return True
            self.gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
            time.sleep(0.15)
        return self.bst().get("selectedId") == uid

    def settle(self, timeout=15, boxes=None):
        """<= timeout: isBusy false and no NextTurnState; a message box is closed (its text is EVIDENCE)."""
        time.sleep(0.1)
        end = time.time() + timeout
        b, st = {}, []
        while time.time() < end:
            b, st = self.bst(), self.states()
            if st and st[-1] in ("InfoboxState", "InfoboxOKState"):
                if boxes is not None:
                    boxes.append({"state": st[-1], "texts": self.texts()})
                self.gc.cmd({"cmd": "dismiss_popup"})
                continue
            if not b.get("isBusy") and "NextTurnState" not in st:
                return True, b, st
            time.sleep(0.1)
        return False, b, st

    def walk(self, uid, tile, timeout=15):
        """The real-UI walk: TAB select, HOME, map_tile_click_pos (verified), a left click; waits for the walker on the tile
        or out, isBusy false. -> record."""
        rec = {"unit": uid, "to": list(tile)}
        if not self.select(uid):
            rec["fail"] = "select"
            return rec
        self.gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
        time.sleep(0.2)
        pr = self.gc.cmd({"cmd": "map_tile_click_pos", "x": tile[0], "y": tile[1], "z": tile[2]})
        if not (pr.get("ok") and pr.get("verified")):
            rec["fail"] = "click_pos %s" % pr.get("error")
            return rec
        u = self.units()[uid]
        rec["from"], rec["tu0"] = [u["x"], u["y"], u["z"]], u["tu"]
        self.gc.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
        end = time.time() + timeout
        while time.time() < end:
            b = self.bst()
            a = {v["id"]: v for v in b.get("units", [])}.get(uid)
            if a and (a["isOut"] or at(a, tile)) and not b.get("isBusy"):
                rec["arrived"] = True
                return rec
            time.sleep(0.1)
        rec["arrived"] = False
        return rec


def main():
    crash0 = crash_files()
    gc = harness.GameClient("d247u_b2", LABEL, harness.make_user_dir(UDIR))
    B = Boot(gc)
    ctx = {}
    coop_session = None
    try:
        # ---- bring-up + X-COM turn 1 staging (a miss FAILs every row "boot" with ONE CAPTURE line) ----
        try:
            gc.spawn()
            gc.connect()
            gc.ok({"cmd": "open_new_battle"})
            B.wait("NewBattleState", lambda: session.has_state(gc, "NewBattleState"), 60)
            gc.ok({"cmd": "newbattle_mission", "type": MISSION})
            gc.ok({"cmd": "newbattle_race", "race": RACE})
            if gc.ok({"cmd": "newbattle_hotseat", "on": True}).get("hotseat") is not True:
                raise RuntimeError("newbattle_hotseat did not arm hotseat")
            if gc.cmd({"cmd": "get_coop"}).get("hotseatReactionFire") is not False:
                raise RuntimeError("REACT FIRE is not off at the menu")
            gc.ok({"cmd": "set_seed", "seed": SEED_A})
            gc.ok({"cmd": "newbattle_ok"})
            B.wait("BriefingState", lambda: session.has_state(gc, "BriefingState"), 180, 0.25)
            gc.ok({"cmd": "close_briefing"})
            B.wait("equip screen", lambda: session.has_state(gc, "InventoryState"), 30, 0.2)
            session.dismiss_battle_start_overlays(gc)
            B.wait("BattlescapeState on top", lambda: B.top() == "BattlescapeState", 30)
            ctx["staging"] = stage(B)
        except Exception as e:  # noqa: BLE001
            B.capture("boot B2: %r" % e)
            for row in CELLS:
                fail_rest(row, "boot")
                verdict(row)
            return
        coop_session = B.bst().get("coopSession")
        print("bring-up done %.1f s" % (time.time() - T0), flush=True)
        for name, fn in (("R1", row_r1), ("R1b", row_r1b), ("AB", row_ab)):
            try:
                fn(B, ctx)
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
        evidence("common", newCrashFiles=new, coopSession=coop_session, wall=round(time.time() - T0, 1))
        cell("react_off-common", not new and coop_session is False, "new crash files %s, coopSession %r" % (new, coop_session))
        verdict("common")


def stage(B):
    """S-B T0-4 (2)-(3): every lever reply read; raises on a refused lever or a wrong read-back (a boot miss)."""
    us = B.units()
    al = sorted(u["id"] for u in us.values() if u["originalFaction"] == FACTION_HOSTILE and not u["isOut"])
    if not al or al[0] != AR or SR not in us or not us[SR].get("isPlayerSoldier") or us[SR]["isOut"]:
        raise RuntimeError("unit layout differs from CONSTANTS.md: aliens %s, SR %r" % (al, ub(us.get(SR))))
    st = {"AR_to": B.lev({"cmd": "battle_teleport_unit", "unit": AR, "x": AR_HOME[0], "y": AR_HOME[1], "z": AR_HOME[2], "dir": AR_DIR})["to"],
          "SR_to": B.lev({"cmd": "battle_teleport_unit", "unit": SR, "x": SR_HOME[0], "y": SR_HOME[1], "z": SR_HOME[2], "dir": SR_DIR})["to"]}
    g = B.lev({"cmd": "battle_give", "unit": SR, "item": SR_WEAPON, "ammo": SR_AMMO, "clear_hands": True})
    st["SR_give"] = [g.get("weaponId"), g.get("weaponSlot"), g.get("ammoId")]
    B.lev({"cmd": "battle_action", "action": "set_stat", "unit": AR, "stat": "reactions", "value": 100})
    B.lev({"cmd": "battle_action", "action": "set_stat", "unit": AR, "stat": "firing", "value": 0})
    for uid in us:
        if uid != AR:
            B.lev({"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions", "value": 0})
    us = B.units()
    bad = [] if at(us[AR], AR_HOME) and us[AR]["direction"] == AR_DIR and us[AR].get("reactions") == 100 else [ub(us[AR])]
    bad += [] if at(us[SR], SR_HOME) and us[SR]["direction"] == SR_DIR and us[SR].get("weapon") == SR_WEAPON else [ub(us[SR])]
    bad += [[u["id"], "reactions", u.get("reactions")] for u in us.values() if u["id"] != AR and u.get("reactions")]
    if bad:
        raise RuntimeError("staging read-back wrong: %s" % bad)
    return st


def row_r1(B, ctx):
    ar_tu0 = B.units()[AR]["tu"]
    rec = B.walk(SR, SR_DEST)
    boxes = []
    settled, b, st = B.settle(15, boxes)
    us = {u["id"]: u for u in b.get("units", [])}
    sr, ar = us.get(SR, {}), us.get(AR, {})
    evidence("R1", walk=rec, settled=settled, stack=st, boxes=boxes, ARtu=[ar_tu0, ar.get("tu")], SR=ub(sr), AR=ub(ar))
    if rec.get("fail"):
        fail_rest("R1", "blocked: SR's walk failed (%s)" % rec["fail"])
        return
    if not settled:
        fail_rest("R1", "not settled in 15 s: busy %r stack %s" % (b.get("isBusy"), st))
        return
    cell("R1-walk", at(sr, SR_DEST), "SR at %s" % [sr.get(k) for k in ("x", "y", "z")])
    if not RES["R1-walk"]:
        fail_rest("R1", "blocked: SR not on SR_DEST (R1-walk)")
        return
    cell("R1-noreact", ar.get("tu") == ar_tu0, "AR TU %r -> %r" % (ar_tu0, ar.get("tu")))


def row_r1b(B, ctx):
    B.gc.ok({"cmd": "battle_action", "action": "end_turn_button"})
    end, nts = time.time() + 40, None
    while time.time() < end:
        b = B.bst()
        if B.top() == "NextTurnState" and b.get("side") == 1:
            nts = b
            break
        time.sleep(0.1)
    if not nts:
        B.capture("R1b: no side-1 screen")
        evidence("R1b", reason="no 'Side: Aliens' screen")
        fail_rest("R1b", "blocked: no 'Side: Aliens' screen in 40 s")
        return
    nts_txt = B.texts()
    B.gc.ok({"cmd": "close_nextturn"})
    boxes = []
    settled, b, st = B.settle(10, boxes)
    us = {u["id"]: u for u in b.get("units", [])}
    p2 = b.get("side") == 0 and all(u["faction"] == FACTION_PLAYER for u in us.values()
                                    if u["originalFaction"] == FACTION_HOSTILE and not u["isOut"])
    hand = {"ntsTexts": nts_txt, "settled": settled, "side": b.get("side"), "turn": b.get("turn"), "stack": st, "p2": p2}
    if not settled:
        evidence("R1b", handover=hand, boxes=boxes)
        fail_rest("R1b", "not settled in 10 s after the hand-over: side %r busy %r stack %s" % (b.get("side"), b.get("isBusy"), st))
        return
    if not p2:
        evidence("R1b", handover=hand, boxes=boxes)
        fail_rest("R1b", "blocked: player 2's turn never started")
        return
    B.lev({"cmd": "battle_action", "action": "set_stat", "unit": SW, "stat": "reactions", "value": 100})
    B.lev({"cmd": "battle_action", "action": "set_stat", "unit": SW, "stat": "firing", "value": 0})
    sw_tu0 = B.units()[SW]["tu"]
    rec = B.walk(AR, AR_DEST)
    settled, b, st = B.settle(15, boxes)
    us = {u["id"]: u for u in b.get("units", [])}
    sw, ar = us.get(SW, {}), us.get(AR, {})
    evidence("R1b", handover=hand, walk=rec, settled=settled, stack=st, boxes=boxes, SWtu=[sw_tu0, sw.get("tu")], SW=ub(sw), AR=ub(ar))
    if rec.get("fail"):
        fail_rest("R1b", "blocked: AR's walk failed (%s)" % rec["fail"])
        return
    if not settled:
        fail_rest("R1b", "not settled in 15 s: busy %r stack %s" % (b.get("isBusy"), st))
        return
    cell("R1b-walk", at(ar, AR_DEST), "AR at %s" % [ar.get(k) for k in ("x", "y", "z")])
    if not RES["R1b-walk"]:
        fail_rest("R1b", "blocked: AR not on AR_DEST (R1b-walk)")
        return
    cell("R1b-noreact", sw.get("tu") == sw_tu0, "SW TU %r -> %r" % (sw_tu0, sw.get("tu")))


def row_ab(B, ctx):
    rec = {}
    try:
        B.lev({"cmd": "inject_input", "kind": "key", "key": SDLK_ESCAPE})
        B.wait("PauseState", lambda: B.top() == "PauseState", 10)
        rec["pause"] = B.texts()
        rec["abandon"] = B.click_shown("ABANDON").get("text")
        B.wait("AbandonGameState", lambda: B.top() == "AbandonGameState", 10)
        rec["dialog"] = B.texts()
        rec["yes"] = B.click_shown("YES").get("text")
        t = time.time()
        B.wait("MainMenuState", lambda: B.top() == "MainMenuState", 30)
        rec["menuSecs"] = round(time.time() - t, 2)
    except Exception as e:  # noqa: BLE001
        rec["error"] = repr(e)
        B.capture("AB: %r" % e)
    st = B.states()
    hs = B.gc.cmd({"cmd": "get_coop"}).get("hotseat")
    evidence("AB", route=rec, stack=st, hotseat=hs)
    cell("AB-menu", st[-1:] == ["MainMenuState"], "stack %s" % st)
    if not RES["AB-menu"]:
        fail_rest("AB", "blocked: the main menu was not reached (AB-menu)")
        return
    cell("AB-disarm", hs is False, "hotseat %r" % hs)


if __name__ == "__main__":
    main()
    failed = [n for row in CELLS.values() for n in row if not RES.get(n)]
    print("\nSUMMARY: %d/%d cells PASS; FAIL: %s (%.1f s)" % (len(RES) - len(failed), sum(len(v) for v in CELLS.values()),
                                                           failed, time.time() - T0), flush=True)
    sys.exit(0 if not failed else 2)
