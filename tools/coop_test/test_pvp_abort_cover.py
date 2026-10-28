"""RV-U5 S-B row PA3 (boot P): in a gm3 PvP skirmish the alien host starts the abort vote and the battle ends for both
machines, the gm3 leg of the legacy test_pvp_skirmish_abort (owner D229 (a) + hard gate; D231: any player may start the
vote; D157 (a): the alien seat ends on the host's debriefing, display-only on the partner; QV5-3 (a)).

Spec: docs repo rewrite/prompts/rvu5_quarantine_gate.md section (f) test_pvp_abort_cover.py, with the orchestrator
ruling R-RV5-SB-2 (the host presses ABORT on its own side: the partner's END TURN first; the battle buttons are locked
during the other side's turn as in vanilla and main, VL-RV5-2). Constants: rewrite/rvu5-task0/sb/CONSTANTS.md (TASK 0
boot Pa and its capture, F15956 / F15957).

Boot P (key 49712, dirs rv5_p_host / rv5_p_client): G3F.bring_up (the roster pin, the HOST on the Alien team, gm3; the
W2-P8b battle-entry spine; pin_ai_neutral). Staging: the partner's END TURN hands the side to the aliens, (side, turn)
(1, 1) on both; a miss fails PA3 "staging".
  PA3  the host's battle_action abort; its AbortMissionState; the host's dismiss_popup (the OK opens the vote with the
       host's YES); session.abort_vote_yes(host, client).
       PA3-dialog  the host's top AbortMissionState within STEP_S and the dismiss handled AbortMissionState
       PA3-vote    abort_vote_yes returns (the vote opened on both and passed)
       PA3-record  both tops DebriefingState within STEP_S; battleEnd: the host emitted 1 with EXPECT (reason abort,
                   aborted true, seat 0 win, seat 1 abort); the partner applied 1, display-only, the host's view
       PA3-menu    the client's OK (handled DebriefingState) then the host's: each top MainMenuState within MENU_S;
                   world_state.has_save false on both
       PA3-common  every hash bucket EQUAL right before the press (no battle is left to hash after it), desyncSeen
                   false on both at the debriefing, no new crash file at the end

One EVIDENCE line, then one PASS/FAIL line per cell, then the row verdict. A boot step past its bound prints ONE CAPTURE
line and fails PA3 "boot". WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip
path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_abort_cover.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
from test_pvp_gm3 import (Miss, stack, top, es, capture, guarded, hash_now, record_view, run_row,  # noqa: E402
                             fail_all)
from repro_atom_side_begin import drive_side_change  # noqa: E402
from test_battle_end_rules import wait_until  # noqa: E402

P_KEY = "49712"
FACTION_HOSTILE = 1               # the side the alien host commands (gm3)
STEP_S, MENU_S = 30, 10           # TASK 0 Pa capture: the dialog 0.05 s, the vote 0.25 s, each debriefing / menu 0.05 s
EXPECT = {"reason": "abort", "aborted": True, "verdicts": [(0, "win"), (1, "abort")]}   # D157 (a); TASK 0 Pa capture
P_ROWS = (("PA3", ("PA3-dialog", "PA3-vote", "PA3-record", "PA3-menu", "PA3-common")),)


def stage_p(host, client):
    """The partner's END TURN; both machines on (1, 1); the host idle. Raises Miss (CAPTURE P staging)."""
    m = (host, client)
    ev = {"press": guarded("P staging", lambda: client.ok({"cmd": "battle_action", "action": "end_turn_button"}), m)}
    guarded("P staging", lambda: drive_side_change(host, client, FACTION_HOSTILE, timeout=STEP_S), m)
    guarded("P staging", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    ev["sideTurn"] = [(battle_state(gc).get("side"), battle_state(gc).get("turn")) for gc in m]
    if ev["sideTurn"] != [(1, 1), (1, 1)]:
        capture("P staging", f"(side, turn) host/client {ev['sideTurn']} (want (1, 1) on both)", m)
        raise Miss("P staging")
    return ev


def be(gc):
    rec = es(gc, "battleEnd") or {}
    v = record_view(rec)
    v.update({k: rec.get(k) for k in ("emitted", "applied", "debriefDisplayOnly")})
    return v


def row_pa3(host, client, crash0, staged):
    m, cells = (host, client), {}
    ev = dict(staged)
    pre = {gc.name: {k: (es(gc, "battleEnd") or {}).get(k) for k in ("emitted", "applied")} for gc in m}
    hashed = hash_now(host, client)
    ev.update(pre=pre, hashBefore=hashed, abort=host.cmd({"cmd": "battle_action", "action": "abort"}))
    ok, secs = wait_until(lambda: top(host) == "AbortMissionState", STEP_S, 0.1)
    ev["dialog"] = {"secs": secs, "host": stack(host), "client": stack(client)}
    d = host.cmd({"cmd": "dismiss_popup"}) if ok else {}
    cells["PA3-dialog"] = (ok and d.get("handled") == "AbortMissionState",
                           f"host top AbortMissionState {ok} in {secs} s (want within {STEP_S} s), dismiss handled "
                           f"{d.get('handled')!r} (want 'AbortMissionState'); stacks {ev['dialog']}")
    try:
        ev["vote"] = session.abort_vote_yes(host, client)
        cells["PA3-vote"] = (True, f"abort_vote_yes returned {ev['vote']}")
    except Exception as e:
        cells["PA3-vote"] = (False, f"abort_vote_yes: {type(e).__name__}: {str(e)[:300]}")
    hok, hs = wait_until(lambda: top(host) == "DebriefingState", STEP_S, 0.1)
    cok, cs = wait_until(lambda: top(client) == "DebriefingState", STEP_S, 0.1)
    hv, cv = be(host), be(client)
    ds = [es(host, "desyncSeen"), es(client, "desyncSeen")]
    ev.update(debrief={"host": (hok, hs), "client": (cok, cs), "stacks": [stack(gc) for gc in m]}, host=hv, client=cv,
              desyncAtDebrief=ds)
    keys = ("seq", "reason", "aborted", "inExitArea", "verdicts", "tally")
    want, same = {k: hv.get(k) for k in EXPECT}, {k: cv[k] for k in keys} == {k: hv[k] for k in keys}
    zero = {"emitted": 0, "applied": 0}
    cells["PA3-record"] = (hok and cok and pre == {"host": zero, "client": zero} and hv["emitted"] == 1
                           and want == EXPECT and cv["applied"] == 1 and cv["debriefDisplayOnly"] == 1 and same,
                           f"tops DebriefingState host {hok} {hs} s / client {cok} {cs} s (want within {STEP_S} s); "
                           f"records before {pre} (want 0 / 0); host emitted {hv['emitted']} (want 1) {want} (want "
                           f"{EXPECT}); client applied {cv['applied']} (want 1), debriefDisplayOnly "
                           f"{cv['debriefDisplayOnly']} (want 1), its view == the host's {same} (want True)")
    steps = []
    for gc in (client, host):   # the client's OK first, then the host's
        dm = gc.cmd({"cmd": "dismiss_popup"})
        mok, ms = wait_until(lambda: top(gc) == "MainMenuState", MENU_S, 0.1)
        ev[f"{gc.name}Ok"] = {"handled": dm.get("handled"), "menu": (mok, ms), "stacks": [stack(x) for x in m]}
        if dm.get("handled") != "DebriefingState" or not mok:
            steps.append(f"{gc.name} OK handled {dm.get('handled')!r} (want 'DebriefingState'), top MainMenuState "
                         f"{mok} in {ms} s (want within {MENU_S} s; stack {stack(gc)})")
    world = {gc.name: gc.cmd({"cmd": "world_state"}) for gc in m}
    ev["world"] = {n: {k: w.get(k) for k in ("ok", "has_save", "has_battle")} for n, w in world.items()}
    if any(w.get("has_save") is not False for w in world.values()):
        steps.append(f"world_state has_save {ev['world']} (want false on both)")
    cells["PA3-menu"] = (not steps, f"{steps or 'client then host OK -> MainMenuState, has_save false on both'}")
    try:
        session.assert_client_zero_disk(client.user_dir)
        ev["clientZeroDisk"] = True
    except AssertionError as e:
        ev["clientZeroDisk"] = str(e)[:200]
    crash = sorted(session._crash_log_snapshot() - crash0)
    cells["PA3-common"] = (hashed == "all buckets EQUAL" and ds == [False, False] and not crash,
                           f"common: hash before the press {hashed}; desyncSeen host/client at the debriefing {ds} "
                           f"(want False/False); new crash files {crash} (want none)")
    return cells, ev


def boot_p():
    host = GameClient("host", None, make_user_dir("rv5_p_host"))
    client = GameClient("client", None, make_user_dir("rv5_p_client"))
    try:
        try:
            boot, crash0 = G3F.bring_up(host, client, P_KEY, "P")
        except Miss:
            return fail_all(P_ROWS, "boot (FIXTURE-STOP, see the CAPTURE P line)")
        try:
            staged = stage_p(host, client)
        except Miss:
            return fail_all(P_ROWS, "staging (see the CAPTURE P staging line)")
        staged["boot"] = boot
        return run_row("PA3", P_ROWS[0][1], lambda: row_pa3(host, client, crash0, staged))
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_p()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_abort_cover: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
