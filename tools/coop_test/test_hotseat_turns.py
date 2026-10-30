"""hotseat's turn hand-over and one explored map per player.

ONE single-player instance (label 49111, user dir hotseat_turns; the label is not a port when a user dir is given), no
co-op session. HOTSEAT is armed through the real NEW BATTLE toggle handler (`newbattle_hotseat`). Player 1 commands
X-COM, player 2 the aliens on the aliens' own side of each vanilla round.

Bring-up: open_new_battle; newbattle_mission MISSION; newbattle_race RACE; newbattle_hotseat on; set_seed SEED_A right
before newbattle_ok; close_briefing; the battle-start overlays; BattlescapeState on top. S_WALK (the lowest-id
soldier) is staged by `battle_teleport_unit` onto S_HOME (dir S_DIR) - the 14 soldiers fill the Skyranger cabin at
turn 1 and no soldier can leave it. Then every unit `set_stat reactions 0` and TU0 is read. The setup values were
measured.

Rows and cells (one EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a
failure; a row whose precondition failed FAILs its cells "blocked: <reason>"):
  common: turns-common, 0 new crash files (this harness slot's crash folder); battle_state.coopSession false.
  setup: setup-armed (hotseat true at the battlescape, turn 1, side 0), setup-real (faction == originalFaction for
      every unit; >= 3 live aliens, 0 civilians).
  first_handover: the hand-over to player 2: S_WALK's real-UI walk to S_DEST, END TURN, the "Side: Aliens" screen
      (FX_STASH = X-COM's map, every alien's x/y/z/direction/tu), close it, settle (<= 10 s, isBusy false, no
      NextTurnState). first_handover-side, -swap, -noai, -select, -ai, -fog, -shown, -hidden. A settle that times out
      FAILs every first_handover cell "not settled" (no vacuous pass).
  alien_orders: player 2 commands an alien: A's real-UI walk to A_DEST, a primed fuse-0 grenade dropped on G_TILE.
      alien_orders-walk.
  handback: the hand-back to player 1: END TURN, poll to the side-0 screen. handback-dark, -boom, -real, -turn, -fogX,
      -tu.
  second_handover: the second hand-over: S_WALK walks back to S_HOME, END TURN, close the screen.
      second_handover-swap, -fogA, -select, -tu.
  battle_end: the battle ends on player 2's turn: ABORT, the debriefing. battle_end-debrief, -real, -disarm.
alien_orders to battle_end need player 2's turn (first_handover); without the fix the AI plays the aliens' side, so
they are blocked there. battle_end-real: `battle_state` has no battle at the debriefing, so it reads the debriefing's
own display (`debrief_state`): rows[] item "X-COM OPERATIVES KILLED" qty == soldiers dead at the battle's end (0 when
the row is absent), rows[] item "X-COM OPERATIVES MISSING IN ACTION" qty == soldiers alive outside the craft / exit
tiles at the end (vanilla's abort rule; S_WALK stands outside the craft), and soldiers[] (the soldier-stats page)
names == the soldiers alive on the craft / exit tiles. Expected values are read on battle_state + tile_census just
before ABORT.

When broken: every first_handover to battle_end cell FAILs; setup-armed, setup-real and turns-common PASS. Exit 0 only
when every cell passes, else 2 (one run, no SKIP, no exit 3). Run it in the foreground to completion.

Run: python tools/coop_test/test_hotseat_turns.py
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
S_WALK, S_HOME, S_DIR, S_DEST = 1, (24, 19, 0), 4, (24, 18, 0)
A, A_DEST, G_TILE = 1000004, (16, 36, 0), (20, 0, 0)
LABEL, UDIR = 49111, "hotseat_turns"

SDLK_HOME, SDLK_TAB = 278, 9
STATUS_DEAD, START_POINT, END_POINT = 6, 1, 13
CELLS = {
    "common": ["turns-common"],
    "setup": ["setup-armed", "setup-real"],
    "first_handover": ["first_handover-side", "first_handover-swap", "first_handover-noai", "first_handover-select",
                       "first_handover-ai", "first_handover-fog", "first_handover-shown", "first_handover-hidden"],
    "alien_orders": ["alien_orders-walk"],
    "handback": ["handback-dark", "handback-boom", "handback-real", "handback-turn", "handback-fogX", "handback-tu"],
    "second_handover": ["second_handover-swap", "second_handover-fogA", "second_handover-select", "second_handover-tu"],
    "battle_end": ["battle_end-debrief", "battle_end-real", "battle_end-disarm"],
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


class Boot:
    def __init__(self, gc):
        self.gc = gc
        self.X = self.Y = self.Z = None

    def states(self):
        return [s.replace("class OpenXcom::", "") for s in session.states(self.gc)]

    def top(self):
        s = self.states()
        return s[-1] if s else ""

    def bst(self):
        return self.gc.cmd({"cmd": "battle_state"})

    def bits(self):
        return self.gc.ok({"cmd": "reveal_state", "bits": True})["playerBits"]

    def texts(self):
        r = self.gc.cmd({"cmd": "list_widgets"})
        return [w.get("text") for w in r.get("widgets", []) if w.get("text")]

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

    def ix(self, p):
        return p[2] * self.X * self.Y + p[1] * self.X + p[0]

    def pos_of(self, i):
        return (i % self.X, (i // self.X) % self.Y, i // (self.X * self.Y))

    def floor(self, bits, p):
        return (int(bits[2 * self.ix(p):2 * self.ix(p) + 2], 16) & 4) != 0

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

    def wait_nts(self, side, timeout, samples=None):
        """Poll every 0.1 s until a NextTurnState is on top with battle_state.side == side."""
        end = time.time() + timeout
        while time.time() < end:
            b = self.bst()
            tp = self.top()
            if samples is not None:
                samples.append({"side": b.get("side"), "hms": b.get("hiddenMovementShown"), "pending": b.get("pendingStates")})
            if tp == "NextTurnState" and b.get("side") == side:
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


def live(units, ofac):
    return [u for u in units.values() if u["originalFaction"] == ofac and not u["isOut"]]


def swapped(units):
    """Every live alien faction 0 / original 1, every live soldier faction 1 / original 0."""
    bad = [[u["id"], u["faction"], u["originalFaction"]] for u in live(units, 1) if u["faction"] != 0]
    bad += [[u["id"], u["faction"], u["originalFaction"]] for u in live(units, 0) if u["faction"] != 1]
    return not bad, bad


def main():
    crash0 = crash_files()
    gc = harness.GameClient("hotseat_turns", LABEL, harness.make_user_dir(UDIR))
    B = Boot(gc)
    ctx = {"p2": False}
    coop_session = None
    try:
        # ---- bring-up (a miss here FAILs every row "boot" with ONE CAPTURE line) ----
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
            fd = gc.ok({"cmd": "find_doors", "limit": 0})
            B.X, B.Y, B.Z = fd["mapSizeX"], fd["mapSizeY"], fd["mapSizeZ"]
            tp = gc.ok({"cmd": "battle_teleport_unit", "unit": S_WALK, "x": S_HOME[0], "y": S_HOME[1], "z": S_HOME[2], "dir": S_DIR})
            if (tp["to"]["x"], tp["to"]["y"], tp["to"]["z"]) != S_HOME:
                raise RuntimeError("staging teleport landed at %r" % tp["to"])
            for uid in list(B.units()):
                gc.ok({"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions", "value": 0})
            ctx["TU0"] = {u["id"]: u["tu"] for u in B.units().values()}
        except Exception as e:  # noqa: BLE001
            B.capture("boot: %r" % e)
            for row in CELLS:
                fail_rest(row, "boot")
                verdict(row)
            return
        b0 = B.bst()
        coop_session = b0.get("coopSession")
        print("bring-up done %.1f s" % (time.time() - T0), flush=True)
        for name, fn in (("setup", row_setup), ("first_handover", row_first_handover),
                         ("alien_orders", row_alien_orders), ("handback", row_handback),
                         ("second_handover", row_second_handover), ("battle_end", row_battle_end)):
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
        cell("turns-common", not new and coop_session is False, "new crash files %s, coopSession %r" % (new, coop_session))
        verdict("common")


def row_setup(B, ctx):
    b = B.bst()
    hs = B.gc.ok({"cmd": "get_coop"}).get("hotseat")
    us = {u["id"]: u for u in b["units"]}
    al, civ = live(us, 1), [u for u in us.values() if u["originalFaction"] == 2]
    mism = [u["id"] for u in us.values() if u["faction"] != u["originalFaction"]]
    evidence("setup", hotseat=hs, turn=b.get("turn"), side=b.get("side"), liveAliens=len(al), civilians=len(civ),
             mismatch=mism, staged=[us[S_WALK][k] for k in ("x", "y", "z", "direction")], TU0=ctx["TU0"])
    cell("setup-armed", hs is True and b.get("turn") == 1 and b.get("side") == 0,
         "hotseat %r turn %r side %r" % (hs, b.get("turn"), b.get("side")))
    cell("setup-real", not mism and len(al) >= 3 and not civ,
         "mismatch %s, live aliens %d, civilians %d" % (mism, len(al), len(civ)))


def row_first_handover(B, ctx):
    ok, rec = B.walk(S_WALK, S_DEST)
    if not ok:
        evidence("first_handover", walk=rec)
        fail_rest("first_handover", "blocked: S_WALK's walk failed (%s)" % rec.get("fail"))
        return
    B.gc.ok({"cmd": "battle_action", "action": "end_turn_button"})
    nts = B.wait_nts(1, 40)
    if not nts:
        B.capture("first_handover: no side-1 screen")
        fail_rest("first_handover", "blocked: no 'Side: Aliens' screen in 40 s")
        return
    fx = B.bits()
    scr = {u["id"]: (u["x"], u["y"], u["z"], u["direction"], u["tu"]) for u in nts["units"] if u["originalFaction"] == 1 and not u["isOut"]}
    ctx["FX_STASH"], ctx["A_TU0"] = fx, scr.get(A, (0, 0, 0, 0, None))[4]
    alpos = [v[:3] for v in scr.values()]
    tx = None
    for i in range(len(fx) // 2):
        if int(fx[2 * i:2 * i + 2], 16) & 4:
            p = B.pos_of(i)
            if all(max(abs(p[0] - q[0]), abs(p[1] - q[1]), abs(p[2] - q[2])) > 21 for q in alpos):
                tx = p
                break
    ctx["TX"] = tx
    nts_txt = B.texts()
    B.gc.ok({"cmd": "close_nextturn"})
    settled, b, st = B.settle(10)
    us = {u["id"]: u for u in b.get("units", [])}
    p2 = B.bits() if b.get("inBattle") else ""
    evidence("first_handover", walk=rec, ntsSide=nts.get("side"), ntsTurn=nts.get("turn"), ntsTexts=nts_txt,
             screenAliens=scr, TX=tx, settled=settled, side=b.get("side"), turn=b.get("turn"), stack=st,
             selectedId=b.get("selectedId"),
             hms=b.get("hiddenMovementShown"), fxFloor=sum(1 for i in range(len(fx) // 2) if int(fx[2 * i:2 * i + 2], 16) & 4),
             p2Floor=sum(1 for i in range(len(p2) // 2) if int(p2[2 * i:2 * i + 2], 16) & 4),
             camera=B.gc.cmd({"cmd": "event_state"}).get("camera", {}).get("offset"))
    if not settled:
        fail_rest("first_handover", "not settled in 10 s: side %r turn %r busy %r stack %s"
                  % (b.get("side"), b.get("turn"), b.get("isBusy"), st))
        return
    ok_swap, bad = swapped(us)
    ctx["p2"] = b.get("side") == 0 and all(u["faction"] == 0 for u in live(us, 1))
    cell("first_handover-side", b.get("side") == 0 and b.get("turn") == 1 and st[-1:] == ["BattlescapeState"],
         "side %r turn %r top %s" % (b.get("side"), b.get("turn"), st[-1:]))
    cell("first_handover-swap", ok_swap, "wrong %s" % bad)
    now = {u["id"]: (u["x"], u["y"], u["z"], u["direction"], u["tu"]) for u in live(us, 1)}
    moved = {k: [scr[k], now.get(k)] for k in scr if now.get(k) != scr[k]}
    cell("first_handover-noai", not moved, "changed %s" % moved)
    sel = b.get("selectedId")
    cell("first_handover-select", sel in {u["id"] for u in live(us, 1)} and all(u["selectable"] for u in live(us, 1))
         and not any(u["selectable"] for u in live(us, 0)),
         "selectedId %r, alien selectable %s, soldier selectable %s" % (sel, [u["selectable"] for u in live(us, 1)],
                                                                         [u["id"] for u in live(us, 0) if u["selectable"]]))
    cell("first_handover-ai", not any(u["hasAI"] for u in live(us, 1)),
         "hasAI %s" % [u["id"] for u in live(us, 1) if u["hasAI"]])
    if tx is None:
        cell("first_handover-fog", False, "blocked: no TX in FX_STASH")
    else:
        cell("first_handover-fog", p2 != fx and not B.floor(p2, tx),
             "map differs %r, TX %s discovered %r" % (p2 != fx, tx, B.floor(p2, tx)))
    cell("first_handover-shown", b.get("hiddenMovementShown") is True,
         "hiddenMovementShown %r" % b.get("hiddenMovementShown"))
    seen = set()
    for u in live(us, 1):
        seen.update(u.get("visibleUnits") or [])
    leak = [u["id"] for u in live(us, 0) if u["id"] not in seen and u["visible"]]
    cell("first_handover-hidden", not leak, "unseen soldiers drawn %s" % leak)


def row_alien_orders(B, ctx):
    if not ctx["p2"]:
        evidence("alien_orders", reason="player 2's turn never started")
        fail_rest("alien_orders", "blocked: player 2's turn never started (first_handover)")
        return
    ok, rec = B.walk(A, A_DEST)
    d = B.gc.cmd({"cmd": "battle_drop", "item": "STR_GRENADE", "x": G_TILE[0], "y": G_TILE[1], "z": G_TILE[2], "prime": True, "fuse": 0})
    ctx["gid"] = (d.get("ids") or [None])[0]
    ctx["FA_END"] = B.bits()
    a = B.units().get(A, {})
    ctx["A_TU1"] = a.get("tu")
    evidence("alien_orders", walk=rec, drop=d, A=[a.get(k) for k in ("x", "y", "z", "tu")])
    cell("alien_orders-walk",
         ok and (a.get("x"), a.get("y"), a.get("z")) == A_DEST and a.get("tu", 999) < (ctx.get("A_TU0") or 0),
         "A at %s TU %r -> %r" % ([a.get(k) for k in ("x", "y", "z")], ctx.get("A_TU0"), a.get("tu")))


def superset(big, small):
    return all((int(big[i:i + 2], 16) & int(small[i:i + 2], 16)) == int(small[i:i + 2], 16) for i in range(0, len(small), 2))


def row_handback(B, ctx):
    if not ctx["p2"]:
        evidence("handback", reason="player 2's turn never started")
        fail_rest("handback", "blocked: player 2's turn never started (first_handover)")
        return
    samples = []
    B.gc.ok({"cmd": "battle_action", "action": "end_turn_button"})
    nts = B.wait_nts(0, 60, samples)
    if not nts:
        B.capture("handback: no side-0 screen")
        evidence("handback", samples=samples[-20:])
        fail_rest("handback", "blocked: no side-0 screen in 60 s")
        return
    scr = {u["id"]: u for u in nts["units"]}
    gren = [it for it in B.gc.ok({"cmd": "battle_items"})["items"] if it["id"] == ctx.get("gid")]
    nts_txt = B.texts()
    B.gc.ok({"cmd": "close_nextturn"})
    settled, b, st = B.settle(10)
    xm = B.bits()
    ctx["handback_ok"] = settled and b.get("side") == 0
    us = {u["id"]: u for u in b.get("units", [])}
    fx, fa = ctx.get("FX_STASH", ""), ctx.get("FA_END", "")
    ta = None
    if fx and fa:
        cands = [B.pos_of(i) for i in range(len(fa) // 2) if (int(fa[2 * i:2 * i + 2], 16) & 4) and not (int(fx[2 * i:2 * i + 2], 16) & 4)]
        cands.sort(key=lambda p: (max(abs(p[0] - A_DEST[0]), abs(p[1] - A_DEST[1]), abs(p[2] - A_DEST[2])), B.ix(p)))
        ta = cands[0] if cands else None
    off = [s for s in samples if s["side"] != 0]
    evidence("handback", samples=samples, ntsTexts=nts_txt, ntsSide=nts.get("side"), ntsTurn=nts.get("turn"),
             grenade=gren, settled=settled, TA=ta,
             xFloor=sum(1 for i in range(len(xm) // 2) if int(xm[2 * i:2 * i + 2], 16) & 4),
             screenTU={k: v["tu"] for k, v in scr.items()})
    cell("handback-dark", any(s["pending"] for s in off) and not any(s["hms"] for s in off),
         "%d off-side samples, pending %s, shown %s" % (len(off), [s["pending"] for s in off], [s["hms"] for s in off]))
    cell("handback-boom", ctx.get("gid") is not None and not gren, "grenade %r still %s" % (ctx.get("gid"), gren))
    mism = [u["id"] for u in us.values() if not u["isOut"] and u["faction"] != u["originalFaction"]]
    cell("handback-real", settled and not mism, "settled %r, mismatch %s" % (settled, mism))
    cell("handback-turn", nts.get("side") == 0 and nts.get("turn") == 2,
         "side %r turn %r" % (nts.get("side"), nts.get("turn")))
    if ta is None or ctx.get("TX") is None:
        cell("handback-fogX", False, "blocked: TA %r TX %r" % (ta, ctx.get("TX")))
    else:
        cell("handback-fogX", superset(xm, fx) and B.floor(xm, ctx["TX"]) and not B.floor(xm, ta),
             "X map has FX_STASH %r, TX %r, TA %s %r" % (superset(xm, fx), B.floor(xm, ctx["TX"]), ta, B.floor(xm, ta)))
    wrong = [[k, scr[k]["tu"], ctx["TU0"].get(k)] for k in scr if scr[k]["originalFaction"] == 0 and not scr[k]["isOut"]
             and scr[k]["tu"] != ctx["TU0"].get(k)]
    a_tu = scr.get(A, {}).get("tu")
    cell("handback-tu", a_tu == ctx.get("A_TU1") and not wrong,
         "A TU %r (A_TU1 %r), soldiers off TU0 %s" % (a_tu, ctx.get("A_TU1"), wrong))


def row_second_handover(B, ctx):
    if not ctx["p2"] or not ctx.get("handback_ok"):
        evidence("second_handover", reason="player 2's turn 1 or the hand-back did not happen")
        fail_rest("second_handover", "blocked: player 2's turn never started (first_handover)" if not ctx["p2"]
                  else "blocked: the hand-back was not settled")
        return
    ok, rec = B.walk(S_WALK, S_HOME)
    s_tu2 = B.units().get(S_WALK, {}).get("tu")
    B.gc.ok({"cmd": "battle_action", "action": "end_turn_button"})
    nts = B.wait_nts(1, 40)
    if not nts:
        B.capture("second_handover: no side-1 screen")
        fail_rest("second_handover", "blocked: no 'Side: Aliens' screen in 40 s")
        return
    fx2 = B.bits()
    B.gc.ok({"cmd": "close_nextturn"})
    settled, b, st = B.settle(10)
    us = {u["id"]: u for u in b.get("units", [])}
    p2m = B.bits()
    ctx["p2b"] = settled and b.get("side") == 0 and all(u["faction"] == 0 for u in live(us, 1))
    evidence("second_handover", walk=rec, S_TU2=s_tu2, settled=settled, side=b.get("side"), turn=b.get("turn"),
             stack=st, selectedId=b.get("selectedId"),
             fx2Floor=sum(1 for i in range(len(fx2) // 2) if int(fx2[2 * i:2 * i + 2], 16) & 4))
    if not settled:
        fail_rest("second_handover", "not settled in 10 s: side %r busy %r stack %s"
                  % (b.get("side"), b.get("isBusy"), st))
        return
    ok_swap, bad = swapped(us)
    cell("second_handover-swap", ok_swap, "wrong %s" % bad)
    fa, tx = ctx.get("FA_END", ""), ctx.get("TX")
    cell("second_handover-fogA", bool(fa) and tx is not None and superset(p2m, fa) and not B.floor(p2m, tx),
         "map has FA_END %r, TX %s discovered %r" % (bool(fa) and superset(p2m, fa), tx, tx is not None and B.floor(p2m, tx)))
    cell("second_handover-select", b.get("selectedId") == A, "selectedId %r" % b.get("selectedId"))
    a_tu, s_tu = us.get(A, {}).get("tu"), us.get(S_WALK, {}).get("tu")
    cell("second_handover-tu", ok and a_tu == ctx.get("A_TU0") and s_tu == s_tu2,
         "walk ok %r, A TU %r (A_TU0 %r), S_WALK TU %r (S_TU2 %r)" % (ok, a_tu, ctx.get("A_TU0"), s_tu, s_tu2))


def row_battle_end(B, ctx):
    if not ctx.get("p2b"):
        evidence("battle_end", reason="player 2's turn 2 never started")
        fail_rest("battle_end", "blocked: player 2's turn never started (first_handover)" if not ctx["p2"]
                  else "blocked: the second hand-over did not happen")
        return
    crash0 = crash_files()
    us = B.units()
    dead, home, out = [], [], []
    for u in us.values():
        if u["originalFaction"] != 0 or not u.get("isPlayerSoldier"):
            continue
        if u["status"] == STATUS_DEAD:
            dead.append(u["name"])
            continue
        t = B.gc.ok({"cmd": "tile_census", "x0": u["x"], "x1": u["x"], "y0": u["y"], "y1": u["y"], "z0": u["z"], "z1": u["z"]})["tiles"][0]
        (home if t and t.get("special") in (START_POINT, END_POINT) else out).append(u["name"])
    B.gc.ok({"cmd": "battle_action", "action": "abort"})
    B.wait("AbortMissionState", lambda: B.top() == "AbortMissionState", 10)
    dlg = B.texts()
    B.gc.ok({"cmd": "dismiss_popup"})
    got = B.wait("DebriefingState", lambda: B.top() == "DebriefingState", 30)
    db = B.gc.cmd({"cmd": "debrief_state"})
    rows = db.get("rows", [])

    def qty(word):
        return sum(r["qty"] for r in rows if "OPERATIVES" in r["item"].upper() and word in r["item"].upper())
    killed, mia, names = qty("KILLED"), qty("MISSING"), sorted(s["name"] for s in db.get("soldiers", []))
    new = sorted(crash_files() - crash0)
    hs = B.gc.ok({"cmd": "get_coop"}).get("hotseat")
    evidence("battle_end", abortDialog=dlg, expect={"killed": len(dead), "mia": len(out), "returning": len(home)},
             debriefRows=rows, debriefSoldiers=len(names), title=db.get("title"), rating=db.get("rating"))
    cell("battle_end-debrief", bool(got) and B.top() == "DebriefingState" and not new,
         "top %s, new crash files %s" % (B.top(), new))
    cell("battle_end-real", killed == len(dead) and mia == len(out) and names == sorted(home),
         "killed %d/%d, MIA %d/%d, returning %d/%d" % (killed, len(dead), mia, len(out), len(names), len(home)))
    cell("battle_end-disarm", hs is False, "hotseat %r" % hs)


if __name__ == "__main__":
    main()
    failed = [n for row in CELLS.values() for n in row if not RES.get(n)]
    print("\nSUMMARY: %d/%d cells PASS; FAIL: %s (%.1f s)" % (len(RES) - len(failed), sum(len(v) for v in CELLS.values()),
                                                           failed, time.time() - T0), flush=True)
    sys.exit(0 if not failed else 2)
