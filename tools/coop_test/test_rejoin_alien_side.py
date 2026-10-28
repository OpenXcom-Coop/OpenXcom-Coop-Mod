"""a player who rejoins a co-op or PvP battle while it is on the alien side gets the alien side, as the host has
it (spec: docs repo rewrite/prompts/w2h33_rejoin_doc_side.md (f); orchestrator ruling R-9B-4, F11800; owner D91 Q2 and
PRD T5 "kill -9 the client mid-alien-turn -> reconnect -> rejoin -> hash-clean continue"; QH33-1 .. QH33-7 (a)).
Constants: docs repo rewrite/w2h33-task0/CONSTANTS.md (TASK 0 boots Pa / Pb, Ta / Tb, Va / Vb; EVIDENCE Pr, Pc).

THREE boots, each shut down before the next, one row each (every id and pin read from a probe at bring-up):
  AP  boot P, key "48745", co-op parallel: test_rejoin_end_turn.boot; the client then the host press END TURN; both
      machines on side 1 with the host's alien turn screen up (no NextTurnState is closed); the client is killed (PRD T5);
      a fresh process (client2) rejoins and is held on dialog 68; the host offers RESUME; RESUME; the alien side ends.
  AT  boot T, key "48746", co-op traditional: the same in turn-by-turn mode (the host passes, the client's last pass ends
      the side); the client leaves gracefully (disconnect_to_menu).
  AV  boot V, key "48747", PvP gm2: test_battle_end_rules.boot_e6; the host's END TURN hands the turn to the alien
      player (the client), who leaves on its own turn (disconnect_to_menu), rejoins and presses END TURN.
The host's TEST-ONLY `resync_hold {on: true}` is armed right after each bring-up: a desync then
halts client2 instead of being repaired, so the cells read the defect itself; a green never desyncs.
Cells per row (X = AP / AT / AV):
  X-pause  GUARD at the host's first 62: top CoopState 62 with backVisible false over NextTurnState / BattlescapeState
           (AV: BattlescapeState right below, coopGamemode 2); authority phase Active, peerAbsent true, battleId B0; host
           side 1, turn T0.
  X-side   RED at the hold (client2 on 68, RESUME offered, nothing pressed): client2 side == host side == 1, turn T0 on
           both.
  X-synced RED at the hold: hash_now {buckets: [synced]} equal on host and client2 (EVIDENCE: the full-hash diff).
  X-resume GUARD RESUME (press_back_when_shown, codes 62): within 60 s no 62 on the host, host top NextTurnState (AV:
           BattlescapeState), client2 holds BattlescapeState and no 68, phase Active on both, host peerAbsent false,
           battleId B0 on both.
  X-end    client2 not frozen (else "not reached"); AP / AT: test_turn_baton.drive_full_cycle, settle, both side 0,
           turn >= T0 + 1 (AT: coopActiveSeat 0 on both); AV: client2 END TURN, drive_side_change to side 0, turn >= T0 + 1.
  X-hash   after X-end: wait_host_idle + assert_hash_clean(full).
  X-clean  every case: client2 desyncSeen false and desyncFrozen false; the host's resync_state desyncs / held / offered
           deltas from the row's baseline all 0.
  X-crash  GUARD every case: no new crash_*.log in this lane's crash folder since the row's start.
RED at H1 (TASK 0 decision rule (i), measured on both boots of each shape): AP-side, AP-synced, AP-end, AP-hash,
AP-clean, AT-side, AT-synced, AT-end, AT-hash, AT-clean, AV-side, AV-synced, AV-end, AV-hash, AV-clean (X-end / X-hash
"not reached": client2 frozen by the held desync); every GUARD (X-pause, X-resume, X-crash) PASS.
A bring-up step past its bound is a FIXTURE-STOP: ONE "CAPTURE <row>:" line (every machine's get_state, battle_state,
event_state, coop_dialog_info and the last 40 engine log lines) and every cell of the row FAILs "boot". A leave or rejoin
step past its bound FAILs the cells from X-side on "rejoin" (X-clean and X-crash are still evaluated). One EVIDENCE line
per row, one PASS / FAIL line per cell, then the row verdict; every row runs after a failure. battle_state is probed only
with a BattlescapeState on the machine's stack. run in the foreground to completion.
ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_rejoin_alien_side.py
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from test_rejoin_end_turn import boot as rej_boot, EK, BK  # noqa: E402
from test_battle_end_rules import boot_e6  # noqa: E402
from test_pvp_gm3 import reactions_zero, shut  # noqa: E402
from test_skirmish_rejoin_battle import rejoin_skirmish  # noqa: E402
from test_turn_baton import drive_full_cycle  # noqa: E402
from repro_atom_side_begin import drive_side_change  # noqa: E402
from test_delta_core import settle_on_battlescape, desync_record  # noqa: E402
from test_turn_mode import live_mode, PARALLEL, TRADITIONAL  # noqa: E402

ROWS = (("AP", "p", "48745"), ("AT", "t", "48746"), ("AV", "v", "48747"))   # row, boot, lobby key (unused elsewhere)
CELLS = ("pause", "side", "synced", "resume", "end", "hash", "clean", "crash")
FROM_SIDE = ("side", "synced", "resume", "end", "hash")
POLL, POLL_SIDE = 0.25, 0.1
SIDE_S, PAUSE_S, REJOIN_S, HOLD_S, CYCLE_S, IDLE_S, RESUME_S, MENU_S, PAINT_S = 15, 30, 120, 2, 60, 30, 60, 60, 20
FACTION_PLAYER, FACTION_HOSTILE, GAMEMODE_PVP = 0, 1, 2
DLG_WAIT, DLG_HOLD = 62, 68
BS, NTS, CS = "BattlescapeState", "NextTurnState", "CoopState"
BELOW_62 = {"p": [BS, NTS], "t": [BS, NTS], "v": [BS]}      # CONSTANTS: the host's stack right below its first 62
TOP_AFTER_RESUME = {"p": NTS, "t": NTS, "v": BS}            # CONSTANTS: the host's top after RESUME
OFFER = "SPEC16 M5: rejoin battle_offer sent (battleId="
RS_KEYS = ("desyncs", "held", "offered")
TS_RE = re.compile(r"^\[(\d\d)-(\d\d)-(\d{4})_(\d\d)-(\d\d)-(\d\d)\.(\d{3})\]")


class Miss(Exception):
    """a bring-up, leave or rejoin step past its bound (its CAPTURE line is printed)"""


def short(e, n=300):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."


def alive(gc):
    return gc is not None and gc.proc is not None and gc.proc.poll() is None and gc.sock is not None


def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead or gone machine is a value
        return {"error": short(e, 200)}


def stack(gc):
    return [s.replace("class OpenXcom::", "") for s in (q(gc, {"cmd": "get_state"}).get("states") or [])]


def top(gc):
    return (stack(gc) or [None])[-1]


def bs(gc):
    """battle_state, only with a BattlescapeState on the stack; {} otherwise"""
    return q(gc, {"cmd": "battle_state"}) if BS in stack(gc) else {}


def dlg(gc):
    r = q(gc, {"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("present", "code", "title", "backVisible", "backText")}


def rs(gc):
    r = q(gc, {"cmd": "resync_state"})
    return r.get("resync") if r.get("ok") else None


def rs_delta(a, b):
    if a is None or b is None:
        return None
    return {k: b.get(k, 0) - a.get(k, 0) for k in RS_KEYS}


def snap(gc):
    """REJ.snap's keys (event_state EK, battle_state BK, battle_state guarded) + authority + coopGamemode + stack"""
    if not alive(gc):
        return {"alive": False}
    e, b = q(gc, {"cmd": "event_state"}), bs(gc)
    a = b.get("authority") or {}
    s = dict({k: e.get(k) for k in EK}, **{k: b.get(k) for k in BK})
    s.update(battleId=a.get("battleId"), peerAbsent=a.get("peerAbsent"), desyncFrozen=a.get("desyncFrozen"),
             coopGamemode=b.get("coopGamemode"), stack=stack(gc))
    return s


def log_lines(gc):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


def line_time(ln):
    m = TS_RE.match(ln)
    if not m:
        return None
    d, mo, y, hh, mi, s, ms = (int(v) for v in m.groups())
    return time.mktime((y, mo, d, hh, mi, s, 0, 0, -1)) + ms / 1000.0


def wait(desc, pred, timeout, interval=POLL):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = pred()
        if v:
            return v
        time.sleep(interval)
    raise TimeoutError(f"timed out after {timeout} s waiting for {desc}")


def hashes(gc, buckets=None):
    req = {"cmd": "hash_now", "full": buckets is None}
    if buckets:
        req["buckets"] = list(buckets)
    return q(gc, req).get("h") or {}


def capture(rid, err, machines):
    """ONE CAPTURE line: every machine's get_state, battle_state (guarded), event_state, coop_dialog_info, last 40 log lines"""
    cap = {}
    for gc in machines:
        if gc is None or gc.proc is None:
            continue
        logt = [ln[-220:] for ln in log_lines(gc)[-40:]]
        if not alive(gc):
            cap[gc.name] = {"rc": gc.proc.poll(), "log": logt}
            continue
        b = bs(gc)
        cap[gc.name] = {"get_state": stack(gc), "event_state": q(gc, {"cmd": "event_state"}), "coop_dialog_info": dlg(gc),
                        "battle_state": {k: b.get(k) for k in ("inBattle", "side", "turn", "phase", "authority",
                                                               "coopGamemode", "coopEndTurnText")}, "log": logt}
    print(f"CAPTURE {rid}: missed {err}; {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def step(x, name, fn, machines):
    try:
        return fn()
    except Exception as e:
        capture(x["rid"], f"{name}: {short(e, 600)}", machines)
        raise Miss(f"{name}: {short(e, 300)}")


def fail(msg):
    raise AssertionError(msg)


def mark(x, name):
    x["ev"]["t"][name] = round(time.time() - x["t_press"], 3) if "t_press" in x else None


# ===================== bring-up (FIXTURE-STOP -> every cell "boot") =====================


def side1_no_close(x):
    """both machines read side 1 (0.1 s poll, SIDE_S; no NextTurnState closed); after HOLD_S the host is still on side 1 with
    its NextTurnState (the alien turn screen, which holds the AI) on top"""
    h, c, m, seen = x["host"], x["client"], (x["host"], x["client"]), {}

    def both1():
        for name, gc in (("t_side_host", h), ("t_side_client", c)):
            if name not in seen and bs(gc).get("side") == FACTION_HOSTILE:
                seen[name] = True
                mark(x, name)
        return len(seen) == 2
    step(x, "both machines on side 1 (no NextTurnState closed)", lambda: wait("side 1 on both", both1, SIDE_S, POLL_SIDE), m)
    time.sleep(HOLD_S)
    hv = snap(h)
    x["ev"]["hold_s"] = {"host": hv, "client": snap(c)}
    if hv.get("side") != FACTION_HOSTILE or hv.get("stack", [])[-1:] != [NTS]:
        step(x, "host still on side 1 with NextTurnState on top after HOLD_S",
             lambda: fail(f"host side {hv.get('side')} stack {hv.get('stack')}"), m)


def bring_up(x):
    h, c, shape, key, m = x["host"], x["client"], x["shape"], x["key"], (x["host"], x["client"])
    end_turn = {"cmd": "battle_action", "action": "end_turn_button"}
    if shape in "pt":
        step(x, "bring-up (test_rejoin_end_turn.boot)", lambda: rej_boot(h, c, key, shape == "t"), m)
        modes, want = [live_mode(h), live_mode(c)], (TRADITIONAL if shape == "t" else PARALLEL)
        x["ev"]["liveMode"] = modes
        if modes != [want, want]:
            step(x, f"live_mode {want} on both", lambda: fail(f"live_mode {modes}"), m)
    else:
        step(x, "bring-up (test_battle_end_rules.boot_e6)", lambda: boot_e6(h, c, key), m)
        x["ev"]["reactions"] = len(step(x, "reactions_zero", lambda: reactions_zero(h, c), m))
        step(x, "wait_host_idle", lambda: session.wait_host_idle(h, c, timeout=IDLE_S), m)
    b = bs(h)
    x["T0"], x["B0"] = b.get("turn"), (b.get("authority") or {}).get("battleId")
    armed = q(h, {"cmd": "resync_hold", "on": True}).get("armed")
    x["RS0"] = rs(h)
    x["ev"].update(T0=x["T0"], B0=x["B0"], holdArmed=armed, RS0={k: (x["RS0"] or {}).get(k) for k in RS_KEYS})
    if armed is not True or x["RS0"] is None or not x["T0"] or not x["B0"]:
        step(x, "resync_hold armed, RS0, T0 and B0 read", lambda: fail(
            f"armed {armed} RS0 {x['RS0']} T0 {x['T0']} B0 {x['B0']}"), m)
    if shape == "p":
        step(x, "client END TURN", lambda: c.ok(end_turn), m)
        step(x, "host paints END TURN 1/2", lambda: wait("END TURN 1/2 on the host", lambda: bs(h).get(
            "coopEndTurnText") == "END TURN 1/2", PAINT_S, POLL_SIDE), m)
        x["t_press"] = time.time()
        step(x, "host END TURN", lambda: h.ok(end_turn), m)
        side1_no_close(x)
    elif shape == "t":
        step(x, "host END TURN -> coopActiveSeat 1 on both", lambda: (h.ok(end_turn), wait(
            "coopActiveSeat 1 on both", lambda: q(h, {"cmd": "event_state"}).get("coopActiveSeat") == 1
            and q(c, {"cmd": "event_state"}).get("coopActiveSeat") == 1, SIDE_S, POLL_SIDE)), m)
        x["t_press"] = time.time()
        step(x, "client END TURN (its last pass)", lambda: c.ok(end_turn), m)
        side1_no_close(x)
    else:
        x["t_press"] = time.time()
        step(x, "host END TURN -> side 1 on both (drive_side_change), host idle", lambda: (
            h.ok(end_turn), drive_side_change(h, c, FACTION_HOSTILE, None, SIDE_S),
            session.wait_host_idle(h, c, timeout=IDLE_S)), m)
        mark(x, "t_side_both")
        tops, sides = [top(h), top(c)], [bs(h).get("side"), bs(c).get("side")]
        if tops != [BS, BS] or sides != [FACTION_HOSTILE, FACTION_HOSTILE]:
            step(x, "both tops BattlescapeState, side 1", lambda: fail(f"tops {tops} sides {sides}"), m)
    x["ev"]["preLeave"] = {"host": snap(h), "client": snap(c)}
    x["t"]["t_press"] = 0.0


# ===================== the leave, the pause, the rejoin =====================


def leave_and_pause(x, cells):
    h, c, shape, m = x["host"], x["client"], x["shape"], (x["host"], x["client"])
    x["nlog"] = len(log_lines(h))
    mark(x, "t_leave")
    try:
        if shape == "p":
            step(x, "client.kill() (PRD T5)", c.kill, m)
        else:
            step(x, "client disconnect_to_menu -> MainMenuState", lambda: (c.cmd({"cmd": "disconnect_to_menu"}), wait(
                "client at the main menu", lambda: top(c) == "MainMenuState", MENU_S, POLL_SIDE)), m)
    except Miss as e:
        cells["pause"] = (False, f"not reached (the leave missed: {e})")
        raise
    seen, err = {}, None

    def paused():
        if "t_drop" not in seen and not q(h, {"cmd": "get_coop"}).get("coopSession"):
            seen["t_drop"] = True
            mark(x, "t_drop")
        d = dlg(h)
        return d.get("present") and d.get("code") == DLG_WAIT
    try:
        wait("the host's 62 after the leave", paused, PAUSE_S, POLL_SIDE)
        mark(x, "t_62")
    except TimeoutError as e:
        err = str(e)
    hv, d = snap(h), dlg(h)
    st, below = hv.get("stack") or [], BELOW_62[shape]
    x["ev"]["pause"] = {"host": hv, "dialog": d}
    ok = (d.get("present") and d.get("code") == DLG_WAIT and d.get("backVisible") is False and st[-1:] == [CS]
          and st[-1 - len(below):-1] == below and hv.get("phase") == "Active" and hv.get("peerAbsent") is True
          and hv.get("battleId") == x["B0"] and hv.get("side") == FACTION_HOSTILE and hv.get("turn") == x["T0"]
          and (shape != "v" or hv.get("coopGamemode") == GAMEMODE_PVP))
    cells["pause"] = (bool(ok), f"host dialog code {d.get('code')} backVisible {d.get('backVisible')} (want 62, False); "
                                f"stack {st[-4:]} (want {below + [CS]} on top); phase {hv.get('phase')} peerAbsent "
                                f"{hv.get('peerAbsent')} battleId {hv.get('battleId')} (want Active, True, B0 {x['B0']}); "
                                f"side {hv.get('side')} turn {hv.get('turn')} (want 1, T0 {x['T0']})"
                                + (f"; coopGamemode {hv.get('coopGamemode')} (want 2)" if shape == "v" else "")
                                + (f"; {err}" if err else ""))
    if err:
        capture(x["rid"], err, m)
        raise Miss(err)


def rejoin(x):
    h, c2, key = x["host"], x["client2"], x["key"]
    m = (h, c2)
    step(x, "client2 spawn and connect", lambda: (c2.spawn(), c2.connect()), m)
    step(x, "rejoin_skirmish", lambda: rejoin_skirmish(c2, key), m)
    step(x, "client2 back in the battle, held on dialog 68 over BattlescapeState", lambda: wait(
        "client2 held on 68", lambda: q(c2, {"cmd": "get_coop"}).get("inBattle") and BS in stack(c2)
        and dlg(c2).get("code") == DLG_HOLD, REJOIN_S), m)
    mark(x, "t_68")

    def offered():
        if session.has_state(h, "Profile"):        # the join's popup sits over the dialog (REJ :193-194)
            q(h, {"cmd": "profile_ok"})
            return False
        d = dlg(h)
        return d.get("code") == DLG_WAIT and d.get("backVisible") is True and d.get("backText") == "RESUME"
    step(x, "the host's 62 offers RESUME", lambda: wait("RESUME offered", offered, REJOIN_S), m)
    mark(x, "t_ready")
    offers = [ln for ln in log_lines(h)[x["nlog"]:] if OFFER in ln]
    t_off = line_time(offers[0]) if offers else None
    x["ev"]["t"]["t_offer"] = round(t_off - x["t_press"], 3) if t_off else None
    x["ev"]["hostOfferLines"] = len(offers)


# ===================== the cells =====================


def hold_cells(x, cells):
    h, c2 = x["host"], x["client2"]
    hv, cv = snap(h), snap(c2)
    hh, ch = hashes(h), hashes(c2)
    diff = sorted(k for k in set(hh) | set(ch) if hh.get(k) != ch.get(k))
    sy = [hashes(h, ["synced"]).get("synced"), hashes(c2, ["synced"]).get("synced")]
    x["ev"]["hold"] = {"host": hv, "client2": cv, "hostDialog": dlg(h), "client2Dialog": dlg(c2), "fullHashDiff": diff,
                       "synced": sy, "client2Desync": desync_record(c2, cv.get("desyncSeen"), timeout=2.0),
                       "hostRSdelta": rs_delta(x["RS0"], rs(h))}
    sides, turns = [hv.get("side"), cv.get("side")], [hv.get("turn"), cv.get("turn")]
    cells["side"] = (sides == [FACTION_HOSTILE, FACTION_HOSTILE] and turns == [x["T0"], x["T0"]],
                     f"side host / client2 {sides} (want [1, 1]); turn {turns} (want T0 {x['T0']} on both)")
    cells["synced"] = (sy[0] is not None and sy[0] == sy[1],
                       f"synced host / client2 {sy} (want equal); full-hash diff {diff}")


def resume_cell(x, cells):
    h, c2, shape = x["host"], x["client2"], x["shape"]
    mark(x, "t_resume")
    try:
        session.press_back_when_shown(h, "host RESUME", codes=(DLG_WAIT,))
    except Exception as e:
        cells["resume"] = (False, f"RESUME press: {short(e, 400)}")
        return False

    def back():
        d = dlg(h)
        return (not (d.get("present") and d.get("code") == DLG_WAIT) and BS in stack(c2)
                and dlg(c2).get("code") != DLG_HOLD and bs(h).get("phase") == "Active" and bs(c2).get("phase") == "Active")
    try:
        wait("RESUME: no 62 on the host, client2 off 68, phase Active on both", back, RESUME_S, POLL_SIDE)
        mark(x, "t_back")
    except TimeoutError:
        pass
    hv, cv, hd, cd = snap(h), snap(c2), dlg(h), dlg(c2)
    x["ev"]["afterResume"] = {"host": hv, "client2": cv, "hostDialog": hd, "client2Dialog": cd}
    hst, cst = hv.get("stack") or [], cv.get("stack") or []
    ok = (not (hd.get("present") and hd.get("code") == DLG_WAIT) and hst[-1:] == [TOP_AFTER_RESUME[shape]]
          and BS in cst and cd.get("code") != DLG_HOLD and [hv.get("phase"), cv.get("phase")] == ["Active", "Active"]
          and hv.get("peerAbsent") is False and hv.get("battleId") == cv.get("battleId") == x["B0"])
    cells["resume"] = (bool(ok), f"host dialog {hd.get('code')} present {hd.get('present')} (want no 62); host top {hst[-1:]} "
                                 f"(want {TOP_AFTER_RESUME[shape]}); client2 stack {cst[-3:]} dialog {cd.get('code')} "
                                 f"(want BattlescapeState, no 68); phase {[hv.get('phase'), cv.get('phase')]} (want Active); "
                                 f"host peerAbsent {hv.get('peerAbsent')} (want False); "
                                 f"battleId {[hv.get('battleId'), cv.get('battleId')]} (want B0 {x['B0']})")
    return bool(ok)


def end_cells(x, cells, resumed):
    h, c2, shape, rid = x["host"], x["client2"], x["shape"], x["rid"]
    if not resumed:
        cells["end"] = (False, f"not reached ({rid}-resume failed)")
        cells["hash"] = (False, f"not reached ({rid}-end failed)")
        return
    cv = snap(c2)
    if cv.get("desyncFrozen") or cv.get("desyncSeen"):
        cells["end"] = (False, f"not reached (client2 frozen by the held desync: desyncFrozen {cv.get('desyncFrozen')} "
                               f"desyncSeen {cv.get('desyncSeen')})")
        cells["hash"] = (False, f"not reached ({rid}-end failed)")
        return
    err, t0 = None, time.time()
    try:
        if shape in "pt":
            drive_full_cycle(h, c2, x["T0"], timeout=CYCLE_S)
            settle_on_battlescape(h)
            settle_on_battlescape(c2)
        else:
            c2.ok({"cmd": "battle_action", "action": "end_turn_button"})
            drive_side_change(h, c2, FACTION_PLAYER, x["T0"] + 1, SIDE_S)
    except Exception as e:
        err = short(e, 400)
    mark(x, "t_end")
    hv, cv = snap(h), snap(c2)
    x["ev"]["end"] = {"host": hv, "client2": cv, "cycleS": round(time.time() - t0, 2), "error": err}
    sides, turns = [hv.get("side"), cv.get("side")], [hv.get("turn"), cv.get("turn")]
    seats = [hv.get("coopActiveSeat"), cv.get("coopActiveSeat")]
    ok = (err is None and sides == [FACTION_PLAYER, FACTION_PLAYER] and all((t or 0) >= x["T0"] + 1 for t in turns)
          and (shape != "t" or seats == [0, 0]))
    cells["end"] = (ok, f"side {sides} (want [0, 0]); turn {turns} (want >= T0 + 1 = {x['T0'] + 1})"
                        + (f"; coopActiveSeat {seats} (want [0, 0])" if shape == "t" else "") + (f"; {err}" if err else ""))
    if not ok:
        cells["hash"] = (False, f"not reached ({rid}-end failed)")
        return
    try:
        session.wait_host_idle(h, c2, timeout=IDLE_S)
        session.assert_hash_clean(h, c2, full=True, what=f"{rid} after the alien side")
        cells["hash"] = (True, "wait_host_idle; every bucket EQUAL (full)")
    except Exception as e:
        cells["hash"] = (False, short(e, 600))


def clean_cell(x, cells):
    c2 = x["client2"]
    cv = snap(c2)
    d = rs_delta(x["RS0"], rs(x["host"]))
    x["ev"]["final"] = {"host": snap(x["host"]), "client2": cv, "hostRSdelta": d,
                        "client2Desync": desync_record(c2, cv.get("desyncSeen"), timeout=2.0) if alive(c2) else None}
    ok = cv.get("desyncSeen") is False and cv.get("desyncFrozen") is False and d == {k: 0 for k in RS_KEYS}
    cells["clean"] = (ok, f"client2 desyncSeen {cv.get('desyncSeen')} desyncFrozen {cv.get('desyncFrozen')} (want False, "
                          f"False); host resync_state deltas {d} (want all 0)")


# ===================== a row =====================


def verdict(rid, cells, ev):
    print(f"EVIDENCE {rid}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    fails = []
    for c in CELLS:
        ok, detail = cells.get(c, (False, "not reached"))
        print(f"{'PASS' if ok else 'FAIL'} {rid}-{c}: {detail}", flush=True)
        if not ok:
            fails.append(f"{rid}-{c}")
    print(f"{rid} {'PASS' if not fails else 'FAIL'} ({len(fails)} of {len(CELLS)} cells failed)", flush=True)
    return fails


def run_row(rid, shape, key, walls):
    t0 = time.time()
    tag = f"w2h33_{shape}"
    host = GameClient("host", None, make_user_dir(tag + "_host"))
    client = GameClient("client", None, make_user_dir(tag + "_client"))
    client2 = GameClient("client2", None, make_user_dir(tag + "_client2"))
    crash0 = session._crash_log_snapshot()
    cells, ev = {}, {"t": {}}
    x = {"rid": rid, "shape": shape, "key": key, "host": host, "client": client, "client2": client2, "ev": ev,
         "t": ev["t"], "RS0": None, "T0": None, "B0": None}
    try:
        try:
            bring_up(x)
        except Miss as e:
            cells = {c: (False, f"boot (FIXTURE-STOP: {e})") for c in CELLS}
            return verdict(rid, cells, ev)
        try:
            leave_and_pause(x, cells)
            rejoin(x)
            hold_cells(x, cells)
            end_cells(x, cells, resume_cell(x, cells))
        except Exception as e:  # a Miss printed its CAPTURE line; anything else is unexpected, still a FAIL
            for c in FROM_SIDE:
                cells.setdefault(c, (False, f"rejoin ({e if isinstance(e, Miss) else short(e, 400)})"))
            cells.setdefault("pause", (False, f"not reached ({short(e, 300)})"))
        clean_cell(x, cells)
        new = sorted(session._crash_log_snapshot() - crash0)
        cells["crash"] = (not new, f"new crash files {new} (want none)")
        return verdict(rid, cells, ev)
    finally:
        shut(client2, client, host)
        walls[rid] = round(time.time() - t0, 1)


def main():
    t0, fails, walls = time.time(), [], {}
    for rid, shape, key in ROWS:
        fails += run_row(rid, shape, key, walls)
    n = len(ROWS) * len(CELLS)
    print(f"\ntest_rejoin_alien_side: {n - len(fails)}/{n} cells passed (fail={fails}) row walls {walls} in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
