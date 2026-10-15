"""W2-H63 (R-H63-0, lead L-MGB-1, F18926): a single-player battle's pause menu hides SAVE GAME while an action runs and
during the enemy turn, as vanilla OpenXcom does (PauseState's "ENOUGH!" guard, OXCE 4a6ade5ef). The co-op build's
"re-show Load / Save when this machine is truly solo" blocks (the constructor and init()) turn SAVE GAME back on in every
single-player battle. Spec: docs repo rewrite/prompts/w2h63_solo_pause_save_guard.md ((f), QH63-1 .. QH63-6 (a));
constants rewrite/w2h63-task0/sa/CONSTANTS.md (TASK 0 boots a, b red and c green at b63def857). No lobby key.

ONE solo boot (w2h63_spg_host): a settled New Battle (set_seed 1). Every read = open_pause_coop (a real
PauseState(OPT_BATTLESCAPE) and its CO-OP click), pop the HostMenu it opened, wait until every interactive PauseState
widget reads `hidden` false (the window popup ends after init()), then ONE list_widgets and ONE battle_state.
Row R: R-rest SAVE GAME visible at rest. Then WALK (the first soldier with TU >= 30 to the first open tile 12..6 tiles
away on a straight line) and the read with the walk in flight (precondition: pendingStates > 0 after the read and
GAME OPTIONS hidden, the constructor saw busy): R-busy-save SAVE GAME hidden, R-busy-load LOAD GAME shown.
Row T: the walk ended, END TURN (battle_action end_turn_button), the read over the "Side: Aliens" NextTurnState
(precondition: side 1 after the read; the aliens never move): T-enemy-save SAVE GAME hidden, T-enemy-load LOAD GAME shown.
C-crash: no new file in the lane crash folder since the boot started and no DebriefingState seen.
CO-OP's visibility is EVIDENCE only (MG-B's cell, D238 (a)). No save is written.
RED on the unchanged product: R-busy-save, T-enemy-save. GREEN (E1-E3): every cell PASS.
One EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; every row runs after a failure. A precondition
miss ends its row (later cells FAIL "not reached (<step>)", ONE CAPTURE line). A boot miss fails every cell "boot" with
ONE CAPTURE line. WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip path;
exit 0 only when every cell passes, else 2.   Run:  python tools/coop_test/test_w2_solo_pause_save_guard.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402
import session  # noqa: E402

SEED = 1                                            # set_seed right before newbattle_ok (TASK 0 boots a, b, c)
TU_WALK, WALK_FAR, WALK_NEAR = 30, 12, 6
GEN_S, STEP_S, BUSY_S, SETTLE_S, NTS_S = 180, 30, 5, 5, 10   # bounds (s); TASK 0: 2.5, 3.0, 0.05, 0.2, 0.1
SAVE, LOAD, OPTS, COOP = "SAVE GAME", "LOAD GAME", "GAME OPTIONS", "CO-OP"
R_CELLS, T_CELLS, C_CELLS = ("R-rest", "R-busy-save", "R-busy-load"), ("T-enemy-save", "T-enemy-load"), ("C-crash",)
stack, bs = session.states_stripped, session.battle_state


class Miss(Exception):
    """A step that missed its precondition (its CAPTURE line is printed by the row)."""

    def __init__(self, step, why):
        super().__init__(f"{step}: {why}")
        self.step, self.why = step, why


def top(gc):
    s = stack(gc)
    return s[-1] if s else None


def wait_until(pred, bound, interval=0.25):
    t = time.time()
    while time.time() - t < bound:
        if pred():
            return True, round(time.time() - t, 2)
        time.sleep(interval)
    return bool(pred()), round(time.time() - t, 2)


def pop_to(gc, name):
    pops = []
    while top(gc) != name and len(pops) < 6:
        pops.append((top(gc), gc.cmd({"cmd": "pop_state"}).get("ok")))
    return pops


def crash_files():
    d = harness.CRASH_DIR
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def log_tail(gc, n=30):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines()[-n:] if os.path.exists(p) else []


def capture(tag, err, gc):
    """ONE CAPTURE line: the stack, get_coop, the battle view, the top state's widgets, the engine log tail."""
    def probe(fn):
        try:
            return fn()
        except Exception as e:
            return f"probe failed: {type(e).__name__}: {e}"
    cap = {"stack": probe(lambda: stack(gc)), "coop": probe(lambda: gc.cmd({"cmd": "get_coop"})),
           "battle": probe(lambda: {k: bs(gc).get(k) for k in ("inBattle", "side", "turn", "pendingStates", "isBusy")}),
           "widgets": probe(lambda: [(w.get("text"), w.get("visible"), w.get("hidden")) for w in
                                     gc.cmd({"cmd": "list_widgets"}).get("widgets", [])]),
           "logTail": probe(lambda: log_tail(gc))}
    print(f"CAPTURE {tag}: missed {err}; {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def report(row, order, cells, ev):
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    for name in order:
        print(f"{'PASS' if cells[name][0] else 'FAIL'} {name}: {cells[name][1]}", flush=True)
    fails = sum(1 for name in order if not cells[name][0])
    print(f"{row} {'PASS' if not fails else 'FAIL'} ({fails} of {len(order)} cells failed)", flush=True)
    return fails


def order_walk(gc):
    """WALK (spec PINNED SETUP VALUES; its own level, then the one below; a refused line moves on to the next)."""
    units, tried = bs(gc).get("units", []), []
    occupied = {(u["x"], u["y"], u["z"]) for u in units if not u.get("isOut")}
    for u in [u for u in units if u.get("faction") == 0 and not u.get("isOut") and (u.get("tu") or 0) >= TU_WALK]:
        for z, d in [(z, d) for z in (u["z"], u["z"] - 1) if z >= 0 for d in range(8)]:
            line = [(u["x"] + session.DIR_DX[d] * k, u["y"] + session.DIR_DY[d] * k, z)
                    for k in range(WALK_FAR, WALK_NEAR - 1, -1)]
            t = next((t for t in line if session.tile_walkable(gc, t, occupied)), None)
            if t is None:
                continue
            r = gc.cmd({"cmd": "battle_action", "action": "move", "unit": u["id"], "x": t[0], "y": t[1], "z": t[2]})
            if r.get("ok"):
                return {"unit": u["id"], "from": (u["x"], u["y"], u["z"]), "tu": u.get("tu"), "dest": t, "refused": tried}
            tried.append((u["id"], t, r.get("error")))
    return {"unit": None, "refused": tried}


def settled(gc):
    lw = gc.cmd({"cmd": "list_widgets"})
    inter = [w for w in lw.get("widgets", []) if w.get("interactive")]
    return "PauseState" in str(lw.get("state")) and inter and not any(w.get("hidden") for w in inter)


def pause_read(gc, seen):
    """The read (QH63-3 (a)): lever, pop its HostMenu, settle, ONE list_widgets + ONE battle_state."""
    b0 = bs(gc)
    r = {"pendingAtLever": b0.get("pendingStates"), "sideAtLever": b0.get("side")}
    gc.ok({"cmd": "open_pause_coop"})
    r["lever"] = stack(gc)
    seen.update(r["lever"])
    if r["lever"][-2:] != ["PauseState", "HostMenu"]:
        raise Miss("READ", f"open_pause_coop left {r['lever']} (want PauseState, HostMenu on top)")
    gc.ok({"cmd": "pop_state"})
    ok, r["settleS"] = wait_until(lambda: settled(gc), SETTLE_S, 0.1)
    if not ok:
        raise Miss("READ", f"the PauseState widgets did not settle (hidden false) in {SETTLE_S} s; stack {stack(gc)}")
    lw, b = gc.cmd({"cmd": "list_widgets"}), bs(gc)
    tb = [w for w in lw.get("widgets", []) if "TextButton" in str(w.get("type"))]
    r["buttons"] = {w.get("text"): [w.get("visible"), w.get("hidden")] for w in tb}
    counts = {c: sum(1 for w in tb if w.get("text") == c) for c in (SAVE, LOAD, OPTS)}
    if "PauseState" not in str(lw.get("state")) or any(n != 1 for n in counts.values()):
        raise Miss("READ", f"list_widgets on {lw.get('state')}: caption counts {counts} (want one each on the PauseState)")
    r.update({"side": b.get("side"), "turn": b.get("turn"), "pendingAfterRead": b.get("pendingStates"),
              "isBusy": b.get("isBusy"), "stack": stack(gc), "coopVisible": (r["buttons"].get(COOP) or [None])[0]})
    seen.update(r["stack"])
    return r


def vis(r, cap):
    return r["buttons"][cap][0]


def end_row(row, cells, order, step, why, gc):
    capture(f"{row} {step}", why, gc)
    for c in order:
        cells.setdefault(c, (False, f"not reached ({step})"))


def row_r(host, seen, ev):
    cells = {}
    try:
        r = ev["rest"] = pause_read(host, seen)
        cells["R-rest"] = (vis(r, SAVE) is True, f"SAVE GAME visible {vis(r, SAVE)} at rest (want True)")
        ev["restPops"] = pop_to(host, "BattlescapeState")
        ev["walk"] = order_walk(host)
        busy, ev["busyS"] = wait_until(lambda: (bs(host).get("pendingStates") or 0) > 0, BUSY_S, 0.05)
        if ev["walk"]["unit"] is None or not busy:
            raise Miss("WALK", f"no walk reached pendingStates > 0 in {BUSY_S} s: {ev['walk']}")
        r = ev["busy"] = pause_read(host, seen)
        if not ((r["pendingAfterRead"] or 0) > 0 and vis(r, OPTS) is False):
            raise Miss("WALK", f"pendingStates {r['pendingAfterRead']} after the read, GAME OPTIONS visible "
                               f"{vis(r, OPTS)} (want > 0 and False: the constructor saw busy); walk {ev['walk']}")
        at = f"with pendingStates {r['pendingAtLever']} at the lever, {r['pendingAfterRead']} after the read"
        cells["R-busy-save"] = (vis(r, SAVE) is False, f"{'SAVE GAME shows while an action runs: ' if vis(r, SAVE) else ''}"
                                f"SAVE GAME visible {vis(r, SAVE)} {at} (want False, vanilla's guard)")
        cells["R-busy-load"] = (vis(r, LOAD) is True, f"LOAD GAME visible {vis(r, LOAD)} {at} (want True)")
    except Miss as e:
        end_row("R", cells, R_CELLS, e.step, e.why, host)
    except Exception as e:
        end_row("R", cells, R_CELLS, "raised", f"{type(e).__name__}: {str(e)[:600]}", host)
    ev["endPops"] = pop_to(host, "BattlescapeState")
    return report("R", R_CELLS, cells, ev)


def row_t(host, seen, ev, t_boot):
    cells = {}
    try:
        ev["startPops"] = pop_to(host, "BattlescapeState")
        ok, ev["walkEndS"] = wait_until(lambda: top(host) == "BattlescapeState" and bs(host).get("pendingStates") == 0
                                        and bs(host).get("side") == 0, STEP_S)
        if not ok:
            raise Miss("TURN", f"the walk did not end (top BattlescapeState, pendingStates 0, side 0) in {STEP_S} s")
        ev["endTurnPressS"] = round(time.time() - t_boot, 2)
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        ok, ev["ntsWaitS"] = wait_until(lambda: top(host) == "NextTurnState" and bs(host).get("side") == 1, NTS_S, 0.1)
        if not ok:
            raise Miss("TURN", f"no NextTurnState on top with side 1 in {NTS_S} s after END TURN; stack {stack(host)}")
        r = ev["read"] = pause_read(host, seen)
        if r["side"] != 1:
            raise Miss("TURN", f"side {r['side']} after the read (want 1, the aliens' turn)")
        at = f"over the NextTurnState with side {r['side']}, turn {r['turn']}, pendingStates {r['pendingAfterRead']}"
        cells["T-enemy-save"] = (vis(r, SAVE) is False, f"{'SAVE GAME shows during the enemy turn: ' if vis(r, SAVE) else ''}"
                                 f"SAVE GAME visible {vis(r, SAVE)} {at} (want False, vanilla's guard)")
        cells["T-enemy-load"] = (vis(r, LOAD) is True, f"LOAD GAME visible {vis(r, LOAD)} {at} (want True)")
    except Miss as e:
        end_row("T", cells, T_CELLS, e.step, e.why, host)
    except Exception as e:
        end_row("T", cells, T_CELLS, "raised", f"{type(e).__name__}: {str(e)[:600]}", host)
    ev["endPops"] = pop_to(host, "NextTurnState")
    return report("T", T_CELLS, cells, ev)


def boot(host, seen):
    host.spawn(), host.connect(), host.ok({"cmd": "open_new_battle"})
    host.wait_for("NewBattleState", lambda: session.has_state(host, "NewBattleState"), timeout=60)
    host.ok({"cmd": "set_seed", "seed": SEED}), host.ok({"cmd": "newbattle_ok"})
    host.wait_for("SP battle", lambda: (session.has_state(host, "BriefingState") or session.has_state(
        host, "InventoryState") or session.has_state(host, "BattlescapeState")), timeout=GEN_S, interval=0.5)
    if session.has_state(host, "BriefingState"):
        host.ok({"cmd": "close_briefing"})
    host.wait_for("equip screen", lambda: session.has_state(host, "InventoryState"), timeout=STEP_S, interval=0.3)
    session.dismiss_battle_start_overlays(host)
    ok, secs = wait_until(lambda: top(host) == "BattlescapeState" and bs(host).get("pendingStates") == 0
                          and bs(host).get("side") == 0, STEP_S)
    seen.update(stack(host))
    if not ok:
        raise Miss("boot", f"settle: top BattlescapeState, pendingStates 0, side 0 not reached in {secs} s")
    return secs


def main():
    host = GameClient("host", 0, make_user_dir("w2h63_spg_host"))
    before, seen, fails, t_boot = crash_files(), set(), 0, time.time()
    ev_r, ev_t, booted = {}, {}, False
    try:
        try:
            ev_r["settleS"] = boot(host, seen)
            booted = True
        except Exception as e:
            capture("boot", f"{type(e).__name__}: {str(e)[:600]}", host)
        if not booted:
            for row, order in (("R", R_CELLS), ("T", T_CELLS), ("C", C_CELLS)):
                fails += report(row, order, {c: (False, "boot (see the CAPTURE boot line)") for c in order},
                                {"boot": "miss"})
            return fails
        ev_r["mapFingerprint"] = bs(host).get("mapFingerprint")
        fails += row_r(host, seen, ev_r)
        fails += row_t(host, seen, ev_t, t_boot)
        seen.update(stack(host))
    finally:
        try:
            shutdown_clients(host)
            shut = "rc 0"
        except RuntimeError as e:
            shut = str(e)[:300]
            print(f"[spg] shutdown: {shut}", flush=True)
    new = sorted(set(crash_files()) - set(before))
    debrief = "DebriefingState" in seen
    fails += report("C", C_CELLS, {"C-crash": (not new and not debrief, f"new crash files {new} in {harness.CRASH_DIR}; "
                                               f"DebriefingState seen {debrief}; shutdown {shut} (want none, False)")},
                    {"crashDir": harness.CRASH_DIR, "new": new, "statesSeen": sorted(seen)})
    return fails


if __name__ == "__main__":
    n = main()
    print(f"SPG {'PASS' if not n else 'FAIL'}: {n} of 6 cells failed", flush=True)
    sys.exit(0 if n == 0 else 2)
