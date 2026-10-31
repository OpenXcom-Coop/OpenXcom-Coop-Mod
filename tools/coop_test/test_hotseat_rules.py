"""panic, kills and reactions on hotseat player 2's turn. REACT FIRE on.

ONE single-player instance (label 49112, user dir hotseat_rules; the label is not a port when a user dir is given), no
co-op session. HOTSEAT is armed through the real NEW BATTLE toggle handler (`newbattle_hotseat`), REACT FIRE through
`click_widget {match "REACT FIRE"}`, both before `newbattle_ok`.

Bring-up: open_new_battle; newbattle_mission MISSION; newbattle_race RACE; newbattle_hotseat on; REACT FIRE on;
set_seed SEED_A right before newbattle_ok; close_briefing; the battle-start overlays; BattlescapeState on top. X-COM
turn 1 staging (every test command's reply read): AP morale 0; S1 health 1, teleported to S1_TILE facing A2; A2 firing
100, morale 60; S3 teleported to S3_TILE facing A3, its hands cleared and a rifle + clip given (soldier loadouts vary
per boot), reactions 100, firing 100; A3 health 1; every other unit reactions 0. A staging miss is a boot miss.

Rows and cells (one EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a
failure; a row whose precondition failed FAILs its cells "blocked: <reason>"; a settle that times out FAILs its value
cells "not settled"):
  common: rules-common, 0 new crash files (this harness slot's crash folder); battle_state.coopSession false.
  alien_panic: player 2's alien panics at the start of its turn: set_seed SEED_PANIC right before END TURN; at the
      "Side: Aliens" screen AP {status, tu, morale = M0}; close_nextturn; wait <= 15 s for AP status 0 and TU 0,
      closing message boxes (EVIDENCE their text). alien_panic-rolled (AP status 8 at the screen, precondition),
      alien_panic-acted (status 0, TU 0 within 15 s), alien_panic-morale (AP morale == M0 + 15; UnitPanicBState's
      +15).
  alien_kill: player 2's alien kills a soldier: set_seed SEED_ALIEN_KILL; battle_action shoot {A2 -> S1, aimed};
      settle. alien_kill-dead (S1 out, status dead; precondition), alien_kill-killedBy (S1 killedBy 1,
      FACTION_HOSTILE), alien_kill-morale (A2's morale delta == D_WITHOUT_BONUS + 20: vanilla's killer bonus for a
      hostile killer).
  reaction_kill: a soldier's reaction kills player 2's walking alien: set_seed SEED_REACTION_KILL; the real-UI walk of
      A3 to A3_DEST; settle. reaction_kill-reacted (S3's TU dropped; A3 not on A3_DEST or out; precondition),
      reaction_kill-killedBy (A3 out, killedBy 0, FACTION_PLAYER), reaction_kill-no_ai (S3 hasAI false).
Every real-UI walk TABs at least once (a TAB runs calculateFOV for the selected unit, BS :1517-:1524), so the walker
has spotted what it sees before it steps; a walker that newly spots a unit halts before the walk-step reaction check
(UWBS :252).

When broken: alien_panic-acted, alien_panic-morale, alien_kill-killedBy, alien_kill-morale, reaction_kill-killedBy and
reaction_kill-no_ai FAIL; alien_panic-rolled, alien_kill-dead, reaction_kill-reacted and rules-common PASS. Exit 0
only when every cell passes, else 2 (one run, no SKIP, no exit 3). Run it in the foreground to completion.

Run: python tools/coop_test/test_hotseat_rules.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402

# Measured setup values
MISSION, RACE, SEED_A = "STR_LARGE_SCOUT", "STR_SECTOID", 2
AP, A2, S1, A3, S3 = 1000000, 1000001, 1, 1000002, 2
S1_TILE, S1_DIR = (48, 20, 1), 6
S3_TILE, S3_DIR, A3_DEST = (41, 48, 2), 1, (44, 45, 2)
S3_WEAPON, S3_AMMO = "STR_RIFLE", "STR_RIFLE_CLIP"
SEED_PANIC, SEED_ALIEN_KILL, SEED_REACTION_KILL = 1, 1, 1
D_WITHOUT_BONUS = 10
LABEL, UDIR = 49112, "hotseat_rules"

SDLK_HOME, SDLK_TAB = 278, 9
STATUS_STANDING, STATUS_DEAD, STATUS_PANICKING = 0, 6, 8
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
CELLS = {
    "common": ["rules-common"],
    "alien_panic": ["alien_panic-rolled", "alien_panic-acted", "alien_panic-morale"],
    "alien_kill": ["alien_kill-dead", "alien_kill-killedBy", "alien_kill-morale"],
    "reaction_kill": ["reaction_kill-reacted", "reaction_kill-killedBy", "reaction_kill-no_ai"],
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


def ub(u, keys=("x", "y", "z", "direction", "tu", "health", "morale", "status", "isOut", "faction", "hasAI", "killedBy",
                "murdererId", "weapon")):
    return {k: u.get(k) for k in keys} if u else None


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

    def cmd_ok(self, req):
        r = self.gc.cmd(req)
        if not r.get("ok"):
            raise RuntimeError("test command refused: %r -> %r" % (req, r))
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
            b = self.bst()
            c["stack"] = self.states()
            c["battle"] = {k: b.get(k) for k in ("inBattle", "turn", "side", "selectedId", "isBusy", "pendingStates")}
            c["coop"] = {k: v for k, v in self.gc.cmd({"cmd": "get_coop"}).items() if k in ("hotseat", "hotseatReactionFire")}
        except Exception as e:  # noqa: BLE001
            c["error"] = repr(e)
        c["log"] = self.log_tail()
        print("CAPTURE %s: %s" % (tag, json.dumps(c)), flush=True)

    def click_shown(self, match, timeout=5):
        """click_widget once the TextButton captioned `match` is shown: a popup window hides every surface until its popup
        ends and a hidden button ignores input (TestServer list_widgets `hidden`)."""
        end = time.time() + timeout
        while time.time() < end:
            ws = self.gc.cmd({"cmd": "list_widgets"}).get("widgets", [])
            hit = [w for w in ws if w.get("interactive") and match.lower() in (w.get("text") or "").lower()]
            if hit and hit[0].get("visible") and not hit[0].get("hidden"):
                return self.cmd_ok({"cmd": "click_widget", "match": match})
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
            if a and (a["isOut"] or (a["x"], a["y"], a["z"]) == tuple(tile)) and not b.get("isBusy"):
                rec["arrived"] = True
                return rec
            time.sleep(0.1)
        rec["arrived"] = False
        return rec


def main():
    crash0 = crash_files()
    gc = harness.GameClient("hotseat_rules", LABEL, harness.make_user_dir(UDIR))
    B = Boot(gc)
    ctx = {"p2": False}
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
            B.click_shown("REACT FIRE")
            B.wait("REACT FIRE armed", lambda: gc.cmd({"cmd": "get_coop"}).get("hotseatReactionFire") is True, 5)
            gc.ok({"cmd": "set_seed", "seed": SEED_A})
            gc.ok({"cmd": "newbattle_ok"})
            B.wait("BriefingState", lambda: session.has_state(gc, "BriefingState"), 180, 0.25)
            gc.ok({"cmd": "close_briefing"})
            B.wait("equip screen", lambda: session.has_state(gc, "InventoryState"), 30, 0.2)
            session.dismiss_battle_start_overlays(gc)
            B.wait("BattlescapeState on top", lambda: B.top() == "BattlescapeState", 30)
            ctx["staging"] = stage(B)
        except Exception as e:  # noqa: BLE001
            B.capture("boot: %r" % e)
            for row in CELLS:
                fail_rest(row, "boot")
                verdict(row)
            return
        coop_session = B.bst().get("coopSession")
        print("bring-up done %.1f s" % (time.time() - T0), flush=True)
        for name, fn in (("alien_panic", row_alien_panic), ("alien_kill", row_alien_kill),
                         ("reaction_kill", row_reaction_kill)):
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
        cell("rules-common", not new and coop_session is False, "new crash files %s, coopSession %r" % (new, coop_session))
        verdict("common")


def stage(B):
    """The staging: every test command's reply read; raises on a refused command or a wrong read-back (a boot miss)."""
    us = B.units()
    al = sorted(u["id"] for u in us.values() if u["originalFaction"] == FACTION_HOSTILE and not u["isOut"])
    so = sorted(u["id"] for u in us.values() if u["originalFaction"] == FACTION_PLAYER and u.get("isPlayerSoldier") and not u["isOut"])
    if al[:3] != [AP, A2, A3] or so[:2] != [S1, S3]:
        raise RuntimeError("unit layout differs from the measured one: aliens %s soldiers %s" % (al, so))
    st = {"AP_morale": B.cmd_ok({"cmd": "battle_set_unit_state", "unit": AP, "morale": 0}).get("morale"),
          "S1_health": B.cmd_ok({"cmd": "battle_set_unit_state", "unit": S1, "health": 1}).get("health")}
    st["S1_to"] = B.cmd_ok({"cmd": "battle_teleport_unit", "unit": S1, "x": S1_TILE[0], "y": S1_TILE[1],
                            "z": S1_TILE[2], "dir": S1_DIR})["to"]
    B.cmd_ok({"cmd": "battle_action", "action": "set_stat", "unit": A2, "stat": "firing", "value": 100})
    st["A2_morale"] = B.cmd_ok({"cmd": "battle_set_unit_state", "unit": A2, "morale": 60}).get("morale")
    st["S3_to"] = B.cmd_ok({"cmd": "battle_teleport_unit", "unit": S3, "x": S3_TILE[0], "y": S3_TILE[1],
                            "z": S3_TILE[2], "dir": S3_DIR})["to"]
    g = B.cmd_ok({"cmd": "battle_give", "unit": S3, "item": S3_WEAPON, "ammo": S3_AMMO, "clear_hands": True})
    st["S3_give"] = [g.get("weaponId"), g.get("weaponSlot"), g.get("ammoId")]
    B.cmd_ok({"cmd": "battle_action", "action": "set_stat", "unit": S3, "stat": "reactions", "value": 100})
    B.cmd_ok({"cmd": "battle_action", "action": "set_stat", "unit": S3, "stat": "firing", "value": 100})
    st["A3_health"] = B.cmd_ok({"cmd": "battle_set_unit_state", "unit": A3, "health": 1}).get("health")
    for uid in us:
        if uid != S3:
            B.cmd_ok({"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions", "value": 0})
    us = B.units()
    want = {AP: {"morale": 0}, A2: {"morale": 60}, S1: {"health": 1, "x": S1_TILE[0], "y": S1_TILE[1], "z": S1_TILE[2]},
            S3: {"x": S3_TILE[0], "y": S3_TILE[1], "z": S3_TILE[2], "direction": S3_DIR, "reactions": 100, "weapon": S3_WEAPON},
            A3: {"health": 1}}
    bad = [[uid, k, us[uid].get(k), v] for uid, kv in want.items() for k, v in kv.items() if us[uid].get(k) != v]
    bad += [[u["id"], "reactions", u.get("reactions")] for u in us.values() if u["id"] != S3 and u.get("reactions")]
    if bad:
        raise RuntimeError("staging read-back wrong: %s" % bad)
    return st


def row_alien_panic(B, ctx):
    B.gc.ok({"cmd": "set_seed", "seed": SEED_PANIC})
    B.gc.ok({"cmd": "battle_action", "action": "end_turn_button"})
    end, nts = time.time() + 40, None
    while time.time() < end:
        b = B.bst()
        if B.top() == "NextTurnState" and b.get("side") == 1:
            nts = b
            break
        time.sleep(0.1)
    if not nts:
        B.capture("alien_panic: no side-1 screen")
        evidence("alien_panic", reason="no 'Side: Aliens' screen")
        fail_rest("alien_panic", "blocked: no 'Side: Aliens' screen in 40 s")
        return
    scr = {u["id"]: u for u in nts["units"]}.get(AP, {})
    m0 = scr.get("morale")
    nts_txt = B.texts()
    B.gc.ok({"cmd": "close_nextturn"})
    boxes, acted, a = [], False, {}
    end = time.time() + 15
    while time.time() < end:
        st = B.states()
        if st and st[-1] in ("InfoboxState", "InfoboxOKState"):
            boxes.append({"state": st[-1], "texts": B.texts()})
            B.gc.cmd({"cmd": "dismiss_popup"})
            continue
        a = B.units().get(AP, {})
        if a.get("status") == STATUS_STANDING and a.get("tu") == 0:
            acted = True
            break
        time.sleep(0.2)
    settled, b, st = B.settle(10, boxes)
    us = {u["id"]: u for u in b.get("units", [])}
    ctx["p2"] = settled and b.get("side") == 0 and all(u["faction"] == FACTION_PLAYER for u in us.values()
                                                       if u["originalFaction"] == FACTION_HOSTILE and not u["isOut"])
    a = us.get(AP, a)
    evidence("alien_panic", ntsSide=nts.get("side"), ntsTurn=nts.get("turn"), ntsTexts=nts_txt, atScreen=ub(scr), M0=m0,
             acted=acted, boxes=boxes, settled=settled, side=b.get("side"), stack=st, after=ub(a))
    cell("alien_panic-rolled", scr.get("status") == STATUS_PANICKING,
         "AP status %r at the screen (M0 %r, TU %r)" % (scr.get("status"), m0, scr.get("tu")))
    if scr.get("status") != STATUS_PANICKING:
        fail_rest("alien_panic", "blocked: AP did not panic at the side start (alien_panic-rolled)")
        return
    cell("alien_panic-acted", acted,
         "AP status %r TU %r after %s" % (a.get("status"), a.get("tu"), "the act" if acted else "15 s"))
    if not acted:
        cell("alien_panic-morale", False,
             "not settled: AP never acted out its panic (morale %r, M0 %r)" % (a.get("morale"), m0))
    else:
        cell("alien_panic-morale", a.get("morale") == m0 + 15,
             "AP morale %r (M0 %r, expect %r)" % (a.get("morale"), m0, m0 + 15))


def row_alien_kill(B, ctx):
    if not ctx["p2"]:
        evidence("alien_kill", reason="player 2's turn never started")
        fail_rest("alien_kill", "blocked: player 2's turn never started (alien_panic)")
        return
    us = B.units()
    m0, s1b = us[A2]["morale"], ub(us[S1])
    B.gc.ok({"cmd": "set_seed", "seed": SEED_ALIEN_KILL})
    r = B.cmd_ok({"cmd": "battle_action", "action": "shoot", "unit": A2, "target": S1, "mode": "aimed"})
    boxes = []
    settled, b, st = B.settle(15, boxes)
    us = {u["id"]: u for u in b.get("units", [])}
    s1, a2 = us.get(S1, {}), us.get(A2, {})
    d = a2.get("morale", 0) - m0
    evidence("alien_kill", shot={k: r.get(k) for k in ("tuCost", "tuHave")}, settled=settled, stack=st, boxes=boxes,
             S1before=s1b, S1=ub(s1), A2=ub(a2), A2morale=[m0, a2.get("morale")], D=d,
             D_WITHOUT_BONUS=D_WITHOUT_BONUS)
    if not settled:
        fail_rest("alien_kill", "not settled in 15 s: busy %r stack %s" % (b.get("isBusy"), st))
        return
    cell("alien_kill-dead", s1.get("isOut") and s1.get("status") == STATUS_DEAD,
         "S1 isOut %r status %r" % (s1.get("isOut"), s1.get("status")))
    if not RES["alien_kill-dead"]:
        fail_rest("alien_kill", "blocked: S1 not killed (alien_kill-dead)")
        return
    cell("alien_kill-killedBy", s1.get("killedBy") == FACTION_HOSTILE,
         "S1 killedBy %r (murdererId %r)" % (s1.get("killedBy"), s1.get("murdererId")))
    cell("alien_kill-morale", d == D_WITHOUT_BONUS + 20,
         "A2 morale %r -> %r, delta %r (D_WITHOUT_BONUS %r, expect %r)"
         % (m0, a2.get("morale"), d, D_WITHOUT_BONUS, D_WITHOUT_BONUS + 20))


def row_reaction_kill(B, ctx):
    if not ctx["p2"]:
        evidence("reaction_kill", reason="player 2's turn never started")
        fail_rest("reaction_kill", "blocked: player 2's turn never started (alien_panic)")
        return
    us = B.units()
    s3_tu0 = us[S3]["tu"]
    B.gc.ok({"cmd": "set_seed", "seed": SEED_REACTION_KILL})
    rec = B.walk(A3, A3_DEST)
    boxes = []
    settled, b, st = B.settle(15, boxes)
    us = {u["id"]: u for u in b.get("units", [])}
    s3, a3 = us.get(S3, {}), us.get(A3, {})
    evidence("reaction_kill", walk=rec, settled=settled, stack=st, boxes=boxes, S3tu=[s3_tu0, s3.get("tu")], S3=ub(s3),
             A3=ub(a3))
    if rec.get("fail"):
        fail_rest("reaction_kill", "blocked: A3's walk failed (%s)" % rec["fail"])
        return
    if not settled:
        fail_rest("reaction_kill", "not settled in 15 s: busy %r stack %s" % (b.get("isBusy"), st))
        return
    on_dest = (a3.get("x"), a3.get("y"), a3.get("z")) == A3_DEST
    cell("reaction_kill-reacted", s3.get("tu", s3_tu0) < s3_tu0 and (not on_dest or a3.get("isOut")),
         "S3 TU %r -> %r; A3 at %s isOut %r" % (s3_tu0, s3.get("tu"), [a3.get(k) for k in ("x", "y", "z")], a3.get("isOut")))
    if not RES["reaction_kill-reacted"]:
        fail_rest("reaction_kill", "blocked: no reaction from S3 (reaction_kill-reacted)")
        return
    cell("reaction_kill-killedBy", a3.get("isOut") and a3.get("killedBy") == FACTION_PLAYER,
         "A3 isOut %r killedBy %r (murdererId %r)" % (a3.get("isOut"), a3.get("killedBy"), a3.get("murdererId")))
    cell("reaction_kill-no_ai", s3.get("hasAI") is False, "S3 hasAI %r" % s3.get("hasAI"))


if __name__ == "__main__":
    main()
    failed = [n for row in CELLS.values() for n in row if not RES.get(n)]
    print("\nSUMMARY: %d/%d cells PASS; FAIL: %s (%.1f s)" % (len(RES) - len(failed), sum(len(v) for v in CELLS.values()),
                                                           failed, time.time() - T0), flush=True)
    sys.exit(0 if not failed else 2)
