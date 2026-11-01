"""On the second player's machine (the thin client) the NEXT STOP mark ("don't reselect") and the NEXT STOP undo unit
must reset at every side change, as vanilla's SavedBattleGame::endTurn does on the host. Classic co-op skirmish
(gamemode 1), the boot of test_battle_gift.bring_up (roster seed 1, crew C1 / C2 seat 1, H + TANK seat 0, map seed 1,
pinned AI, reactions 0), lobby key 49124, user dirs client_nextstop_reset_host / client_nextstop_reset_client.

Every press is real input: Tab = inject_input key 9 (test_input_gating.cycle_selected_ids); NEXT STOP = a LEFT
click_widget on next_stop_nth; the undo = a RIGHT click on the same button; Previous = a RIGHT click on the NEXT SOLDIER
button (the upper button of the same icon column, BattlescapeState :539). END TURN = test_delta_core.end_turn_cycle,
then both machines on side 0 at the next turn within TURN_S. tab_presses / prev_presses = TAB_N presses (2 x the own
live units).
  first_turn_marks  turn 1, the marks:
      first_turn_start (client selection A; A, B own live on both), first_next_stop (client NEXT STOP A -> B),
      first_tab_skips_mark ([B]*4), first_previous_skips_mark ([B]*4), host_next_stop (host Tab onto H, NEXT STOP
      H -> TANK, Tab [TANK]*4), first_turn_common.
  second_turn_reset  turn 2:
      second_turn_start (client B, host TANK), second_tab_mark_reset ([A,B,A,B]), second_previous_mark_reset
      ([A,B,A,B]), second_host_tab_mark_reset ([H,TANK,H,TANK]), second_client_undo_empty (client undo: selection
      unchanged), second_host_undo_empty (host undo: unchanged), second_next_stop (client NEXT STOP moves to its other
      own unit: D -> E), second_mark_holds ([E]*4: the turn-2 mark holds in turn 2), second_turn_common.
  third_turn_reset  turn 3, LAST:
      third_turn_start (client E, host TANK), third_tab_mark_reset ([D,E,D,E]), third_previous_mark_reset
      ([D,E,D,E]), third_client_undo_empty (client undo: unchanged), third_host_tab_mark_reset ([H,TANK,H,TANK]),
      third_turn_common.
Without the client-side reset, second_tab_mark_reset, second_previous_mark_reset, second_client_undo_empty,
third_tab_mark_reset, third_previous_mark_reset and third_client_undo_empty fail (6 of 21 cells).

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure; a
precondition (GUARD) miss ends its row (later cells "not reached"); a cycle note or a missed turn fails the next row's
cells "not reached"; a boot miss prints ONE CAPTURE line and fails every row "boot". Common cell: every hash bucket
EQUAL, desyncSeen false on both, no new crash file. Ids and button nths come from probes at run time. ONE run is the
result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_client_nextstop_reset.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
from session import battle_state  # noqa: E402
import test_battle_gift as TBG  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
from test_input_gating import next_stop_nth, cycle_selected_ids  # noqa: E402
from test_delta_core import end_turn_cycle  # noqa: E402
from test_seat_pacing import tab_select  # noqa: E402

KEY = "49124"
TANK = TBG.TANK                  # 1000000, the host seat's STR_TANK_CANNON (host own live [1000000, 10])
CLICK_S = 0.3                    # after each click_widget (every read was stable at this wait)
TURN_S = 60                      # both machines on side 0 at the next turn (measured: 0.1 s after end_turn_cycle)
SETTLE_S = 0.5                   # after the turn lands
ROWS = (("first_turn_marks", ("first_turn_start", "first_next_stop", "first_tab_skips_mark",
                               "first_previous_skips_mark", "host_next_stop", "first_turn_common")),
        ("second_turn_reset", ("second_turn_start", "second_tab_mark_reset", "second_previous_mark_reset",
                               "second_host_tab_mark_reset", "second_client_undo_empty", "second_host_undo_empty",
                               "second_next_stop", "second_mark_holds", "second_turn_common")),
        ("third_turn_reset", ("third_turn_start", "third_tab_mark_reset", "third_previous_mark_reset",
                              "third_client_undo_empty", "third_host_tab_mark_reset", "third_turn_common")))


class Precond(Exception):
    """A GUARD (precondition) cell failed: the row ends, later cells are "not reached"."""


def sel(gc):
    return battle_state(gc).get("selectedId", -1)


def side_turn(gc):
    b = battle_state(gc)
    return [b.get("side"), b.get("turn"), b.get("selectedId")]


def own_live(gc, seat):
    """The seat's own live units in battle_state.units order."""
    return [u["id"] for u in battle_state(gc).get("units", [])
            if u.get("coop") == seat and u.get("faction") == 0 and not u.get("isOut")]


def unit_view(gc, ids):
    us = G3F.units(gc)
    return {i: [(us.get(i) or {}).get(k) for k in ("coop", "faction", "originalFaction", "isOut", "status")]
            for i in ids}


def column5(gc):
    """[NEXT SOLDIER nth, NEXT STOP nth]: the fifth 32x16 icon column, upper / lower."""
    lw = gc.cmd({"cmd": "list_widgets"})
    cands = [w for w in lw["widgets"] if w.get("w") == 32 and w.get("h") == 16 and w.get("interactive")
             and w.get("visible")]
    xs = sorted({w["x"] for w in cands})
    col = sorted([w for w in cands if w["x"] == xs[4]], key=lambda w: w["y"])
    out = []
    for target in (col[0]["idx"], col[1]["idx"]):
        nth = 0
        for w in lw["widgets"]:
            if w["idx"] == target:
                out.append(nth)
                break
            if w.get("visible") and w.get("interactive"):
                nth += 1
    return out


def click(gc, nth, button):
    r = gc.cmd({"cmd": "click_widget", "nth": nth, "button": button})
    time.sleep(CLICK_S)
    if not r.get("ok"):
        raise Precond(f"{gc.name} click_widget nth {nth} {button}: {r}")
    return r


def wait_turn(host, client, turn, timeout=TURN_S):
    t0 = time.time()
    while time.time() - t0 < timeout:
        hs, cs = battle_state(host), battle_state(client)
        if (hs.get("side"), hs.get("turn"), cs.get("side"), cs.get("turn")) == (0, turn, 0, turn):
            return round(time.time() - t0, 2)
        time.sleep(0.2)
    return None


def nths(gc):
    c5, ns = column5(gc), next_stop_nth(gc)
    return {"prev": c5[0], "stop": ns, "column5": c5}


def seq(ev, key, gc, other, fn):
    """One press sequence on gc; EVIDENCE: its selectedId per press and the other machine's selection around it."""
    o0 = sel(other)
    got = fn()
    ev[key] = {"seen": got, "other": [o0, sel(other)]}
    return got


def tab_presses(ev, key, gc, other, n):
    return seq(ev, key, gc, other, lambda: cycle_selected_ids(gc, n))


def prev_presses(ev, key, gc, other, nth, n):
    def run():
        seen = []
        for _ in range(n):
            click(gc, nth, "right")
            seen.append(sel(gc))
        return seen
    return seq(ev, key, gc, other, run)


def press(ev, key, gc, other, nth, button):
    """One NEXT STOP press (left = stop, right = undo): [selectedId before, after]."""
    def run():
        before = sel(gc)
        click(gc, nth, button)
        return [before, sel(gc)]
    return seq(ev, key, gc, other, run)


def need(cells, name, ok, detail):
    cells[name] = (bool(ok), detail)
    if not ok:
        raise Precond(f"precondition {name} failed: {detail}")


def ids_of(st, keys):
    if any(st.get(k) is None for k in keys):
        raise Precond(f"an earlier row did not name {keys}: {st}")
    return [st[k] for k in keys]


def start_ev(host, client, st, ev, turn):
    ev["start"] = {"host": side_turn(host), "client": side_turn(client)}
    ids = [i for i in (st.get("A"), st.get("B"), st.get("H"), TANK) if i is not None]
    ev["units"] = {"host": unit_view(host, ids), "client": unit_view(client, ids)}
    ev["nth"] = {"client": nths(client), "host": nths(host)}
    if turn > 1:
        ev["cycle"] = st.get(f"cycle{turn}")
    return ev["nth"]["client"], ev["nth"]["host"]


def row_first_turn_marks(host, client, crash0, st, cells, ev):
    c_own, h_own = own_live(client, 1), own_live(host, 0)
    ev["own"] = {"client": c_own, "host": h_own}
    A = sel(client)
    if A not in c_own and c_own:
        ev["tabToFirstOwn"] = tab_select(client, c_own[0])
        A = sel(client)
    B = ([u for u in c_own if u != A] or [None])[0]
    hs = [u for u in h_own if u != TANK]
    st.update(A=A, B=B, H=hs[0] if len(hs) == 1 else None, TAB_N=2 * len(c_own))
    nc, nh = start_ev(host, client, st, ev, 1)
    ev["ids"] = {k: st[k] for k in ("A", "B", "H", "TAB_N")}
    on_both = all(A in own_live(gc, 1) and B in own_live(gc, 1) for gc in (host, client))
    need(cells, "first_turn_start", len(c_own) == 2 and A in c_own and on_both,
         f"client selectedId {A}, own live {c_own} (want exactly 2, the selection one of them); A {A}, B {B} own live "
         f"(coop 1, faction 0, not out) on both {on_both}")
    got = press(ev, "stop", client, host, nc["stop"], "left")
    need(cells, "first_next_stop", got == [A, B], f"client NEXT STOP selectedId {got[0]} -> {got[1]} (want {A} -> {B})")
    n = st["TAB_N"]
    got = tab_presses(ev, "tab", client, host, n)
    cells["first_tab_skips_mark"] = (got == [B] * n, f"client Tab x{n} {got} (want {[B] * n}: A marked this turn)")
    got = prev_presses(ev, "prev", client, host, nc["prev"], n)
    cells["first_previous_skips_mark"] = (got == [B] * n, f"client Previous x{n} {got} (want {[B] * n})")
    H = st["H"]
    ev["hostSel0"] = sel(host)
    ok_h = H is not None and tab_select(host, H)
    hstop = press(ev, "hstop", host, client, nh["stop"], "left") if ok_h else None
    htab = tab_presses(ev, "htab", host, client, n) if ok_h else None
    need(cells, "host_next_stop", ok_h and hstop == [H, TANK] and htab == [TANK] * n,
         f"host own live {h_own}, H {H}: tab_select {ok_h}; NEXT STOP {hstop} (want [{H}, {TANK}]); Tab {htab} "
         f"(want {[TANK] * n})")
    cells["first_turn_common"] = G3F.common(host, client, crash0)


def row_second_turn_reset(host, client, crash0, st, cells, ev):
    A, B, H, n = ids_of(st, ("A", "B", "H", "TAB_N"))
    nc, nh = start_ev(host, client, st, ev, 2)
    s = ev["start"]
    need(cells, "second_turn_start", s["client"] == [0, 2, B] and s["host"] == [0, 2, TANK],
         f"client [side, turn, selectedId] {s['client']} (want [0, 2, {B}]), host {s['host']} (want [0, 2, {TANK}])")
    got = tab_presses(ev, "tab", client, host, n)
    cells["second_tab_mark_reset"] = (got == [A, B] * (n // 2),
                                      f"client Tab x{n} {got} (want {[A, B] * (n // 2)}: A back at its side's next "
                                      f"turn)")
    got = prev_presses(ev, "prev", client, host, nc["prev"], n)
    cells["second_previous_mark_reset"] = (got == [A, B] * (n // 2),
                                           f"client Previous x{n} {got} (want {[A, B] * (n // 2)})")
    got = tab_presses(ev, "htab", host, client, n)
    cells["second_host_tab_mark_reset"] = (got == [H, TANK] * (n // 2),
                                           f"host Tab x{n} {got} (want {[H, TANK] * (n // 2)})")
    got = press(ev, "undo", client, host, nc["stop"], "right")
    cells["second_client_undo_empty"] = (got[0] == got[1],
                                         f"client undo (right click NEXT STOP) selectedId {got[0]} -> {got[1]} (want "
                                         f"unchanged: no undo unit left from turn 1)")
    got = press(ev, "hundo", host, client, nh["stop"], "right")
    cells["second_host_undo_empty"] = (got[0] == got[1], f"host undo selectedId {got[0]} -> {got[1]} (want unchanged)")
    got = press(ev, "stop", client, host, nc["stop"], "left")
    st.update(D=got[0], E=got[1])
    need(cells, "second_next_stop", got[0] in (A, B) and got[1] in (A, B) and got[0] != got[1],
         f"client NEXT STOP selectedId {got[0]} -> {got[1]} (want its other own unit; D = {got[0]}, E = {got[1]})")
    E = st["E"]
    got = tab_presses(ev, "same", client, host, n)
    cells["second_mark_holds"] = (got == [E] * n,
                                  f"client Tab x{n} {got} (want {[E] * n}: the turn-2 mark holds in turn 2)")
    cells["second_turn_common"] = G3F.common(host, client, crash0)


def row_third_turn_reset(host, client, crash0, st, cells, ev):
    D, E, H, n = ids_of(st, ("D", "E", "H", "TAB_N"))
    nc, nh = start_ev(host, client, st, ev, 3)
    s = ev["start"]
    need(cells, "third_turn_start", s["client"] == [0, 3, E] and s["host"] == [0, 3, TANK],
         f"client [side, turn, selectedId] {s['client']} (want [0, 3, {E}]), host {s['host']} (want [0, 3, {TANK}])")
    got = tab_presses(ev, "tab", client, host, n)
    cells["third_tab_mark_reset"] = (got == [D, E] * (n // 2),
                                     f"client Tab x{n} {got} (want {[D, E] * (n // 2)}: D, marked in turn 2, back in "
                                     f"turn 3)")
    got = prev_presses(ev, "prev", client, host, nc["prev"], n)
    cells["third_previous_mark_reset"] = (got == [D, E] * (n // 2),
                                          f"client Previous x{n} {got} (want {[D, E] * (n // 2)})")
    got = press(ev, "undo", client, host, nc["stop"], "right")
    cells["third_client_undo_empty"] = (got[0] == got[1],
                                        f"client undo selectedId {got[0]} -> {got[1]} (want unchanged: no undo unit "
                                        f"left from turn 2)")
    got = tab_presses(ev, "htab", host, client, n)
    cells["third_host_tab_mark_reset"] = (got == [H, TANK] * (n // 2),
                                          f"host Tab x{n} {got} (want {[H, TANK] * (n // 2)})")
    cells["third_turn_common"] = G3F.common(host, client, crash0)


def row(fn, host, client, crash0, st):
    """(cells, ev) for G3F.run_row: cells set before an exception (a precondition miss) are kept."""
    def run():
        cells, ev = {}, {}
        try:
            fn(host, client, crash0, st, cells, ev)
        except Exception as e:
            ev["error"] = f"{type(e).__name__}: {str(e)[:600]}"
        return cells, ev
    return run


def cycle(host, client, st, turn):
    """END TURN on both, then both machines on side 0 at `turn` within TURN_S; None when it landed clean."""
    notes, t0 = [], time.time()
    end_turn_cycle(host, client, notes)
    waited = wait_turn(host, client, turn)
    st[f"cycle{turn}"] = {"notes": notes, "cycleS": round(time.time() - t0, 2), "waitedS": waited,
                          "host": side_turn(host), "client": side_turn(client)}
    time.sleep(SETTLE_S)
    if notes or waited is None:
        return f"cycle to turn {turn}: {json.dumps(st[f'cycle{turn}'], default=str)}"
    return None


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("client_nextstop_reset_host"))
    client = GameClient("client", None, make_user_dir("client_nextstop_reset_client"))
    rows, fails, st = dict(ROWS), 0, {}
    try:
        try:
            boot, crash0 = TBG.bring_up(host, client, KEY)
            print(f"[test_client_nextstop_reset] boot: {json.dumps(boot, default=str)}", flush=True)
        except Exception as e:
            if not isinstance(e, G3F.Miss):
                G3F.capture("boot", f"{type(e).__name__}: {str(e)[:600]}", (host, client))
            fails = G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        else:
            fails += G3F.run_row("first_turn_marks", rows["first_turn_marks"],
                                 row(row_first_turn_marks, host, client, crash0, st))
            for name, turn, fn in (("second_turn_reset", 2, row_second_turn_reset),
                                   ("third_turn_reset", 3, row_third_turn_reset)):
                miss = cycle(host, client, st, turn)
                if miss is None:
                    fails += G3F.run_row(name, rows[name], row(fn, host, client, crash0, st))
                else:
                    fails += G3F.verdict(name, rows[name], {}, {"error": miss})
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_client_nextstop_reset: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
