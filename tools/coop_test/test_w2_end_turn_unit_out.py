"""RV-U8 - the END TURN count drops a seat the moment its last soldier goes out (REV E.48 C.4, D53, RV-Vb; spec
docs rewrite/prompts/rvu8_tally_on_unit_out.md (f); TASK 0 docs rewrite/rvu8-task0/CONSTANTS.md).

FOUR rows, each its own boot (test_rw_end_turn_tally.py's recipe: bring_up_lobby, drive_to_battlescape on
STR_SMALL_SCOUT with seat_count 2 and set_seed 1 - plus set_mode(traditional) first for the T rows - then
pin_ai_neutral), each shut down before the next. The kill is the host's real casualty chain (battle_action
kill_unit_real {coop_side N}); "victims out" = every killed id DEAD (status 6) on the host. A press is the real
END TURN button (battle_action end_turn_button) on the pressing machine.
  U1 (parallel)    the host pressed; the client's last soldier goes out -> the side ends with no further press
                   (design-D1 on the recounted live set); after the cycle seat 1 stays out of the count.
  U2 (parallel)    the client pressed, then its last soldier goes out -> its press stops counting at once (tally
                   0/1, text and its pressed button clear); nothing ends until the host presses.
  T1 (traditional) the holder at entry (seat 0) loses its last soldier -> the turn passes to seat 1 (D-23 skip);
                   seat 1's own press is then the LAST pass.
  T2 (traditional) the host passed; the new holder (seat 1) loses its last soldier -> nobody after it: the side
                   ends (D-23 "the last pass closes the side", D-24 no take-back).
Premise (every row): seat 0 / seat 1 live player units == S0_IDS / S1_IDS on both machines; the live turn mode on
both; T rows: coopActiveSeat 0 on both. A premise or pre-cell miss = ONE CAPTURE line and "FAIL <row>: pre-cell
(FIXTURE-STOP)". Cells run in order; a failed cell ends its row (later cells "not reached"). Guards per row: no new
crash file, both processes alive at the row end. Each row prints ONE "EVIDENCE <row>:" line, one PASS/FAIL line per
cell and guard, then its verdict; every row runs after a failure.
Rulings: D53, design-D1, D-23, D-24, RV-Vb (QU8-1..6 (a)). WV-D95 / D99 / D100: ONE foreground run, no skip path;
exit 0 only when every row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_end_turn_unit_out.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral
from test_rw_end_turn_tally import bring_up_lobby, drive_full_cycle
from test_rw_turn_mode import set_mode, live_mode, TRADITIONAL, PARALLEL

MISSION = "STR_SMALL_SCOUT"
# TASK 0 (docs rewrite/rvu8-task0/CONSTANTS.md; 8/8 boots identical on both machines at 0d4a61d0e):
S0_IDS = [10, 11, 12, 13, 14]      # seat 0 (host) live player units
S1_IDS = [8, 9]                    # seat 1 (client) live player units
RECOUNT_S, SIDE_S, HOLD_S = 10, 15, 3   # the spec's windows (victims out: 1.56 s seat 1, 4.28 s seat 0)
VICTIMS_S, PAINT_S = 10, 15        # victims-out bound (pre-cell); a press's paint bound (pre-cell)
DEAD = 6                           # STATUS_DEAD as battle_state reports it
FACTION_PLAYER = 0
TEXT1 = "END TURN 1/2"
PRESS = {"cmd": "battle_action", "action": "end_turn_button"}
TALLY_KEYS = ("count", "needed", "ready", "side", "activeSeat")


class FixtureMiss(Exception):
    """A premise / pre-cell step missed its bound: the row is a FIXTURE-STOP."""


def short(e, n=300):
    s = str(e).replace("\n", " ")
    return s if len(s) <= n else s[:n] + "..."


def snap(gc):
    """Both probes' END TURN fields on one machine."""
    es, bs = event_state(gc), battle_state(gc)
    t = es.get("coopEndTurnTally") or {}
    return {"tally": {k: t.get(k) for k in TALLY_KEYS}, "pc": es.get("coopEndTurnPhaseCounter"),
            "active": es.get("coopActiveSeat"), "seen": es.get("coopEndTurnTalliesSeen"),
            "text": bs.get("coopEndTurnText"), "armed": bs.get("coopEndTurnArmed"), "turn": bs.get("turn"),
            "side": bs.get("side")}


def pc(gc):
    return event_state(gc).get("coopEndTurnPhaseCounter")


def live_ids(gc, seat):
    return sorted(u["id"] for u in battle_state(gc).get("units", [])
                  if u.get("coop") == seat and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))


def log_tail(gc, n=8):
    p = os.path.join(gc.user_dir, "openxcom.log")
    if not os.path.exists(p):
        return []
    with open(p, "r", errors="replace") as f:
        return [ln.rstrip()[:200] for ln in f.readlines()[-n:]]


def endturn_lines(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    if not os.path.exists(p):
        return None
    with open(p, "r", errors="replace") as f:
        return sum(1 for ln in f if "[coop-endturn]" in ln)


def until(pred, timeout, interval=0.1):
    """Polls pred() until truthy or timeout; returns the seconds it took, or None."""
    t = time.time()
    while True:
        if pred():
            return round(time.time() - t, 2)
        if time.time() - t >= timeout:
            return None
        time.sleep(interval)


def until_by(pred, deadline, interval=0.1):
    return until(pred, max(0.0, deadline - time.time()), interval)


def holds(pred, seconds, interval=0.25):
    """pred() true at every poll for `seconds`; returns None, or the seconds at the first false poll."""
    t = time.time()
    while time.time() - t < seconds:
        if not pred():
            return round(time.time() - t, 2)
        time.sleep(interval)
    return None


def press(gc, ctx, what):
    r = gc.cmd(dict(PRESS))
    ctx.setdefault("presses", []).append({"what": what, "resp": r})
    if not r.get("ok"):
        raise FixtureMiss(f"{gc.name} end_turn_button refused: {r}")


def kill_seat(host, ctx, seat):
    """The host's real casualty chain on every unit of `seat`; then every victim DEAD on the host (<= VICTIMS_S)."""
    want = S0_IDS if seat == 0 else S1_IDS
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "coop_side": seat})
    killed = sorted(r.get("killed", []))
    ctx["kill"] = {"coop_side": seat, "resp": r}
    if not r.get("ok") or killed != want:
        raise FixtureMiss(f"kill_unit_real coop_side {seat} answered {r} (want killed {want})")

    def out():
        by = {u["id"]: u.get("status") for u in battle_state(host).get("units", [])}
        return all(by.get(i) == DEAD for i in killed)
    s = until(out, VICTIMS_S)
    if s is None:
        raise FixtureMiss(f"victims {killed} not all DEAD on the host within {VICTIMS_S} s")
    ctx["victimsOutS"] = s
    ctx["tOut"] = time.time()


def premise(host, client, mode, ctx):
    got = {w: {"S0": live_ids(gc, 0), "S1": live_ids(gc, 1), "mode": live_mode(gc),
               "active": event_state(gc).get("coopActiveSeat")} for w, gc in (("host", host), ("client", client))}
    ctx["premise"] = got
    bad = []
    for w, g in got.items():
        if g["S0"] != S0_IDS or g["S1"] != S1_IDS:
            bad.append(f"{w} seat ids S0 {g['S0']} S1 {g['S1']} (want {S0_IDS} / {S1_IDS})")
        if g["mode"] != mode:
            bad.append(f"{w} live mode {g['mode']!r} (want {mode!r})")
        if mode == TRADITIONAL and g["active"] != 0:
            bad.append(f"{w} coopActiveSeat {g['active']} (want 0, the entry holder)")
    if bad:
        raise FixtureMiss("premise: " + "; ".join(bad))


def tally_is(s, **want):
    return all(s["tally"].get(k) == v for k, v in want.items())


# ----- the rows: pre(host, client, ctx) builds the pre-cell; cells is an ordered list of (name, fn) where fn returns
# a failure string or None -----

def u1_pre(host, client, ctx):
    press(host, ctx, "host")
    if until(lambda: battle_state(host).get("coopEndTurnText") == TEXT1, PAINT_S) is None:
        raise FixtureMiss(f"host did not paint {TEXT1!r} within {PAINT_S} s of its press")
    h = snap(host)
    if not tally_is(h, count=1, needed=2, ready=[0]):
        raise FixtureMiss(f"host tally after its press {h['tally']} (want count 1, needed 2, ready [0])")
    ctx["P0"], ctx["C0"], ctx["turn0"] = pc(host), pc(client), battle_state(host).get("turn")
    kill_seat(host, ctx, 1)


def side_ended(who):
    """The side ended on `who` (its phase counter past P0 / C0) within SIDE_S of victims out, with no further press."""
    key = "P0" if who == "host" else "C0"

    def cell(host, client, ctx):
        gc = host if who == "host" else client
        s = until_by(lambda: pc(gc) > ctx[key], ctx["tOut"] + SIDE_S)
        if s is None:
            return (f"{who}'s phase counter still {pc(gc)} (P0/C0 {ctx[key]}) {SIDE_S} s after victims out - the side "
                    f"did not end; host tally {snap(host)['tally']}, {who} coopActiveSeat {snap(gc)['active']}")
        return None
    return cell


def u1_cycle(host, client, ctx):
    try:
        drive_full_cycle(host, client, ctx["turn0"])
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        return f"the full cycle did not complete: {short(e)}"
    bad = []
    for w, gc in (("host", host), ("client", client)):
        s = snap(gc)
        if not tally_is(s, count=0, needed=1, ready=[], side="player") or s["text"] != "" or s["armed"] is not False:
            bad.append(f"{w} tally {s['tally']} text {s['text']!r} armed {s['armed']} (want count 0, needed 1, "
                       f"ready [], side 'player', text '', armed False)")
    return "; ".join(bad) or None


def u2_pre(host, client, ctx):
    press(client, ctx, "client")
    if until(lambda: battle_state(host).get("coopEndTurnText") == TEXT1, PAINT_S) is None:
        raise FixtureMiss(f"host did not paint {TEXT1!r} within {PAINT_S} s of the client's press")
    h, c = snap(host), snap(client)
    if c["armed"] is not True or not tally_is(h, count=1, needed=2, ready=[1]):
        raise FixtureMiss(f"after the client's press: client armed {c['armed']} (want True), host tally {h['tally']} "
                          "(want count 1, needed 2, ready [1])")
    ctx["P0"], ctx["C0"] = pc(host), pc(client)
    kill_seat(host, ctx, 1)


def u2_host_recount(host, client, ctx):
    def ok():
        h = snap(host)
        return tally_is(h, count=0, needed=1, ready=[]) and h["text"] == ""
    if until_by(ok, ctx["tOut"] + RECOUNT_S) is None:
        h = snap(host)
        return (f"host tally still {h['tally']} text {h['text']!r} {RECOUNT_S} s after victims out (want count 0, "
                "needed 1, ready [], text '')")
    return None


def u2_client_recount(host, client, ctx):
    def ok():
        c = snap(client)
        return tally_is(c, count=0, needed=1, ready=[]) and c["armed"] is False and c["text"] == ""
    if until_by(ok, ctx["tOut"] + RECOUNT_S) is None:
        c = snap(client)
        return (f"client tally {c['tally']} armed {c['armed']} text {c['text']!r} (want count 0, needed 1, ready [], "
                "armed False, text '')")
    return None


def no_side_end(host, client, ctx):
    s = holds(lambda: pc(host) == ctx["P0"], HOLD_S)
    if s is not None:
        return f"the host's phase counter moved to {pc(host)} (P0 {ctx['P0']}) {s} s into the {HOLD_S} s hold"
    return None


def press_ends_side(presser):
    def cell(host, client, ctx):
        gc = host if presser == "host" else client
        r = gc.cmd(dict(PRESS))
        ctx.setdefault("presses", []).append({"what": f"{presser} (cell)", "resp": r})
        if not r.get("ok"):
            return f"{presser} end_turn_button refused: {r}"
        if until(lambda: pc(host) > ctx["P0"], SIDE_S) is None:
            return (f"the {presser}'s press did not end the side within {SIDE_S} s: host phase counter {pc(host)} "
                    f"(P0 {ctx['P0']}), host tally {snap(host)['tally']}")
        return None
    return cell


def t1_pre(host, client, ctx):
    ctx["P0"], ctx["C0"] = pc(host), pc(client)
    kill_seat(host, ctx, 0)


def t1_pass(host, client, ctx):
    def ok():
        return (event_state(host).get("coopActiveSeat") == 1 and event_state(client).get("coopActiveSeat") == 1
                and tally_is(snap(host), needed=1, count=0, ready=[], activeSeat=1))
    if until_by(ok, ctx["tOut"] + RECOUNT_S) is None:
        h, c = snap(host), snap(client)
        return (f"coopActiveSeat host {h['active']} client {c['active']}, host tally {h['tally']} {RECOUNT_S} s after "
                "victims out (want 1 on both, tally needed 1, count 0, ready [], activeSeat 1)")
    return None


def t2_pre(host, client, ctx):
    p = pc(host)
    press(host, ctx, "host")
    if until(lambda: event_state(host).get("coopActiveSeat") == 1
             and event_state(client).get("coopActiveSeat") == 1, PAINT_S) is None:
        raise FixtureMiss(f"coopActiveSeat did not reach 1 on both within {PAINT_S} s of the host's pass")
    if pc(host) != p:
        raise FixtureMiss(f"the host's pass moved the phase counter {p} -> {pc(host)} (a pass is not a side change)")
    ctx["P0"], ctx["C0"] = pc(host), pc(client)
    kill_seat(host, ctx, 1)


ROWS = (
    ("U1", "48164", 49660, 49661, PARALLEL, u1_pre,
     [("(1) host side ends, no press", side_ended("host")),
      ("(2) client side ends", side_ended("client")),
      ("(3) next side counts seat 0 only", u1_cycle)]),
    ("U2", "48165", 49662, 49663, PARALLEL, u2_pre,
     [("(1) host recount 0/1", u2_host_recount),
      ("(2) client recount, unarmed", u2_client_recount),
      ("(3) no side end for HOLD_S", no_side_end),
      ("(4) host press ends the side", press_ends_side("host"))]),
    ("T1", "48166", 49664, 49665, TRADITIONAL, t1_pre,
     [("(1) the turn passes to seat 1", t1_pass),
      ("(2) no side end for HOLD_S", no_side_end),
      ("(3) client press is the last pass", press_ends_side("client"))]),
    ("T2", "48167", 49666, 49667, TRADITIONAL, t2_pre,
     [("(1) host side ends, no press", side_ended("host")),
      ("(2) client side ends", side_ended("client"))]),
)


def run_row(row, results, walls):
    rid, key, lh, lc, mode, pre, cells = row
    t0, ctx, lines = time.time(), {"row": rid}, []
    crash0 = session._crash_log_snapshot()
    host = GameClient("host", lh, make_user_dir(f"rvu8_{rid}_host"))
    client = GameClient("client", lc, make_user_dir(f"rvu8_{rid}_client"))
    failed, verdict = [], None
    try:
        try:
            bring_up_lobby(host, client, key)

            def pre_ok(h):
                if mode == TRADITIONAL:
                    set_mode(h, TRADITIONAL)
                h.ok({"cmd": "set_seed", "seed": 1})
            session.drive_to_battlescape(host, client, {}, mission=MISSION, seat_count=2, pre_ok=pre_ok)
            ctx["pinned"] = pin_ai_neutral(host, client, tag=f"rvu8-{rid}")
            premise(host, client, mode, ctx)
            ctx["entry"] = {"host": snap(host), "client": snap(client)}
            pre(host, client, ctx)
            ctx["preCell"] = {"host": snap(host), "client": snap(client)}
        except Exception as e:
            cap = {}
            for w, gc in (("host", host), ("client", client)):
                try:
                    cap[w] = {"battle_state": {k: battle_state(gc).get(k) for k in
                                               ("ok", "inBattle", "turn", "side", "phase", "coopEndTurnText",
                                                "coopEndTurnArmed")},
                              "event_state": snap(gc), "log": log_tail(gc)}
                except Exception as e2:
                    cap[w] = {"error": short(e2), "log": log_tail(gc)}
            print(f"CAPTURE {rid}: {type(e).__name__}: {short(e, 600)} | {json.dumps(cap, default=str)}", flush=True)
            verdict = "pre-cell (FIXTURE-STOP)"
            return
        reached = True
        for name, fn in cells:
            if not reached:
                lines.append(f"{rid} {name}: not reached")
                continue
            try:
                f = fn(host, client, ctx)
            except Exception as e:
                f = f"{type(e).__name__}: {short(e, 500)}"
            ctx.setdefault("cells", {})[name] = {"host": snap(host), "client": snap(client),
                                                 "atS": round(time.time() - ctx["tOut"], 2)}
            if f:
                lines.append(f"FAIL {rid} {name}: {f}")
                failed.append("cell " + name.split(")")[0] + ")")
                reached = False
            else:
                lines.append(f"PASS {rid} {name}")
    finally:
        alive = {gc.name: (gc.proc is not None and gc.proc.poll() is None) for gc in (host, client)}
        ctx["hostEndturnLines"] = endturn_lines(host)
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[rvu8] shutdown {gc.name}: {short(e)}", flush=True)
        new_crash = sorted(session._crash_log_snapshot() - crash0)
        ctx["crash"], ctx["alive"] = new_crash, alive
        if verdict is None:
            lines.append(f"PASS {rid} guard crash" if not new_crash else f"FAIL {rid} guard crash: new {new_crash}")
            lines.append(f"PASS {rid} guard alive" if all(alive.values())
                         else f"FAIL {rid} guard alive: {alive}")
            if new_crash:
                failed.append("guard crash")
            if not all(alive.values()):
                failed.append("guard alive")
        ev = {k: v for k, v in ctx.items() if k != "tOut"}
        print(f"EVIDENCE {rid}: {json.dumps(ev, default=str)}", flush=True)
        if verdict is None:
            for ln in lines:
                print(ln, flush=True)
            verdict = ", ".join(failed)
        results[rid] = verdict == ""
        print(f"PASS {rid}" if verdict == "" else f"FAIL {rid}: {verdict}", flush=True)
        walls[rid] = round(time.time() - t0, 1)


def main():
    t0, results, walls = time.time(), {}, {}
    for row in ROWS:
        run_row(row, results, walls)
    rids = [r[0] for r in ROWS]
    passed, failed = [r for r in rids if results.get(r)], [r for r in rids if not results.get(r)]
    print(f"\ntest_w2_end_turn_unit_out: {len(passed)}/{len(rids)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (row walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
