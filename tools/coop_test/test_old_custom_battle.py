"""A classic co-op Custom Battle saved mid-battle by an older version loads on the host converted, so CONTINUE BATTLE
resumes it with each player's own soldiers, nobody owning the aliens, the turn mode it was played in and the mission in
the partner's briefing; a save this build wrote and an older single-player save are never converted. The play cell
turns a seat-1 soldier instead of walking it: the older version's craft layout boxes every seat-1 soldier in.

Fixture: tools/coop_test/fixtures/custom_battle.sav, made by the released game's own harness (parallel turns off),
committed unedited. Lobby key 49221.

Row old_save_converts (dirs old_custom_battle_host / old_custom_battle_client; host option CoopTurnMode parallel; the
client starts clean):
  conversion_lines      host load_save_menu: one "older version's co-op Custom Battle save" line and one summary line
                        (seats 0/1 SEATED0/SEATED1, unseated UNSEATED, turnMode traditional, deployment DEPLOYMENT);
                        every unit of another original faction on no seat (-1); soldiers == SEATS_BY_UNIT
  continue_battle       open_pause_coop -> HostMenu, customBattleResumePending; host_menu_host + the join; CONTINUE
                        BATTLE: both on the battle, no CoopState 62 / 68, phase Active, no desync
  seat_split            per unit (coop, faction, isOut, x, y, z) host == client; other factions -1; soldiers ==
                        SEATS_BY_UNIT
  played_mode           turnMode traditional on both under the host option parallel; coopEndTurnTally.activeSeat 0 on
                        both
  deployment_shared     battle_state.deployment client == host == DEPLOYMENT
  client_turns_soldier  host END TURN; the client turns seat-1 soldier PLAY_ID one octant: facing equal and changed on
                        both, every hash bucket EQUAL, desync false, side 0
  then the host's save_game RESAVE, the setup step of row resave_not_converted
Row resave_not_converted (dir old_custom_battle_resave_host): the host loads RESAVE. no_conversion_line: no
  "[coop-convert]" line; other factions -1; soldiers == SEATS_BY_UNIT.
Row solo_not_converted (dir old_custom_battle_solo_host): the fixture with every whole line `coop: 1` (a sequence item's
  `- coop: 1` included) rewritten to `coop: 0`. solo_save_loads: no "[coop-convert]" line and the save loads (an older
  single-player save is not converted).
Without the fix these fail: conversion_lines, seat_split, played_mode, deployment_shared, no_conversion_line. One
EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; every row runs after a failure. A precondition
miss (continue_battle, a cell that raised) ends its row: later cells FAIL "not reached". A boot step past its bound
prints ONE CAPTURE line and fails every cell of that row "boot". ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.

Run:  python tools/coop_test/test_old_custom_battle.py
"""

import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402
import session  # noqa: E402
import test_skirmish_flow as SK  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "custom_battle.sav")
KEY, RESAVE, SOLO = "49221", "old_custom_battle_resave.sav", "custom_battle_solo.sav"
# unit id: seat
SEATS_BY_UNIT = {8: 0, 9: 0, 10: 0, 11: 0, 12: 0, 13: 0, 14: 0, 31: 1, 32: 1, 33: 1, 34: 1, 35: 1, 36: 1, 37: 1}
SEATED0, SEATED1, UNSEATED, TANKS = 7, 7, 1, ()  # seats from the saved coop tags; the Sectoid; no tank
DEPLOYMENT = "STR_SMALL_SCOUT"                   # the craft's UFO destination's deployment
PLAY_ID = 31                                     # the lowest seat-1 soldier; every seat-1 soldier is boxed in
LOAD_S, CLIENT_S, STEP_S = 120, 120, 30          # bounds (s); measured: load 0.1 s, client in battle 1.25 s
N_CUSTOM = "[coop-convert] an older version's co-op Custom Battle save"
N_SUM = "[coop-convert] an older version's mid-battle co-op save converted"
N_ANY = "[coop-convert]"
SUM_RE = re.compile(r"seats 0/1 (\d+)/(\d+), unseated (\d+); turnMode (\w+); deployment \"([^\"]*)\"")
SOLO_RE = re.compile(r"^(\s*(?:- )?)coop: 1$", re.M)   # the battle units' `- coop: 1` lines too
CONVERT_CELLS, RESAVE_CELLS, SOLO_CELLS = (("conversion_lines", "continue_battle", "seat_split", "played_mode",
                                            "deployment_shared", "client_turns_soldier"),
                                           ("no_conversion_line",), ("solo_save_loads",))
stack, bs, es = session.states_stripped, session.battle_state, session.event_state


class Miss(Exception):
    """A boot step past its bound (its CAPTURE line is printed)."""


def top(gc):
    s = stack(gc)
    return s[-1] if s else None


def log_lines(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def conv(gc):
    return [ln.split("\t")[-1] for ln in log_lines(gc) if N_ANY in ln]


def units(gc):
    return {u["id"]: u for u in bs(gc).get("units", [])}


def ptable(us):
    return {k: [u.get("coop"), u.get("faction"), u.get("isOut"), u.get("x"), u.get("y"), u.get("z")] for k, u in us.items()}


def seat_check(us):
    """(ok, detail): other original factions on no seat, soldiers == SEATS_BY_UNIT, tanks on seat 0."""
    other = {k: u.get("coop") for k, u in us.items() if u.get("originalFaction") != 0}
    sold = {k: us[k].get("coop") if k in us else None for k in SEATS_BY_UNIT}
    tanks = {k: us[k].get("coop") if k in us else None for k in TANKS}
    ok = (bool(other) and all(v == -1 for v in other.values()) and sold == SEATS_BY_UNIT
          and all(v == 0 for v in tanks.values()))
    return ok, f"other factions {other} (want -1 each); soldiers {sold} (want {SEATS_BY_UNIT}); tanks {tanks} (want 0)"


def wait_until(pred, bound, interval=0.25):
    t = time.time()
    while time.time() - t < bound:
        if pred():
            return True, round(time.time() - t, 2)
        time.sleep(interval)
    return bool(pred()), round(time.time() - t, 2)


PROBES = (("stack", stack), ("dialog", lambda g: g.cmd({"cmd": "coop_dialog_info"})),
          ("coop", lambda g: g.cmd({"cmd": "get_coop"})),
          ("battle", lambda g: {k: bs(g).get(k) for k in ("inBattle", "side", "turn", "coopGamemode", "deployment")}),
          ("es", lambda g: {k: es(g).get(k) for k in ("phase", "desyncSeen", "turnMode", "coopActiveSeat")}),
          ("logTail", lambda g: log_lines(g)[-30:]))


def capture(tag, err, machines):
    """ONE CAPTURE line: each machine's stack, coop_dialog_info, get_coop, battle view, event_state picks, log tail."""
    def probe(fn, gc):
        try:
            return fn(gc)
        except Exception as e:
            return f"probe failed: {type(e).__name__}: {e}"
    cap = {gc.name: {k: probe(fn, gc) for k, fn in PROBES} for gc in machines}
    print(f"CAPTURE {tag}: missed {err}; {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def boot(tag, machines, host, save):
    """Spawn + connect every machine; the host loads `save` through the real load menu to a top BattlescapeState."""
    try:
        for gc in machines:
            gc.spawn()
        for gc in machines:
            gc.connect()
        host.ok({"cmd": "load_save_menu", "file": save})
        ok, secs = wait_until(lambda: bs(host).get("inBattle") and top(host) == "BattlescapeState", LOAD_S, 0.3)
        if not ok:
            raise AssertionError(f"the loaded battle not on top in {secs} s (bound {LOAD_S})")
    except Exception as e:
        capture(tag, f"{type(e).__name__}: {str(e)[:600]}", machines)
        raise Miss(tag)


def shut(*gcs):
    try:
        shutdown_clients(*gcs)
    except RuntimeError as e:
        print(f"[old_custom_battle] shutdown: {str(e)[:300]}", flush=True)


def report(row, order, cells, ev):
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    for name in order:
        print(f"{'PASS' if cells[name][0] else 'FAIL'} {name}: {cells[name][1]}", flush=True)
    fails = sum(1 for name in order if not cells[name][0])
    print(f"{row} {'PASS' if not fails else 'FAIL'} ({fails} of {len(order)} cells failed)", flush=True)
    return fails


def boot_failed(row, order, ev):
    return report(row, order, {c: (False, f"boot (see the CAPTURE {row} line)") for c in order}, ev)


def run_cells(order, steps, ev):
    """Cells in order; a gating cell that fails, or any cell that raises, ends the row (later: not reached)."""
    cells, stop = {}, None
    for name in order:
        gating, fn = steps[name]
        try:
            cells[name] = (False, f"not reached ({stop})") if stop else fn(ev)
        except Exception as e:
            cells[name], stop = (False, f"raised {type(e).__name__}: {str(e)[:500]}"), name
        stop = stop or (name if gating and not cells[name][0] else None)
    return cells


def load_cell(host, ev):
    lines, us = conv(host), units(host)
    sd, summ = [ln for ln in lines if N_CUSTOM in ln], [ln for ln in lines if N_SUM in ln]
    m = SUM_RE.search(summ[0]) if len(summ) == 1 else None
    got = [int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5)] if m else None
    want = [SEATED0, SEATED1, UNSEATED, "traditional", DEPLOYMENT]
    sok, sdetail = seat_check(us)
    ev["load"] = {"convert": lines, "units": ptable(us)}
    ok = len(sd) == 1 and got == want and sok
    return ok, (f"{'' if ok else 'the older-version save loaded unconverted: '}'{N_CUSTOM}' lines {len(sd)} "
                f"(want 1); summary lines "
                f"{len(summ)} with {got} (want 1 with {want}); {sdetail}")


def continue_cell(host, client, ev):
    host.ok({"cmd": "open_pause_coop"})
    host.wait_for("HostMenu", lambda: session.has_state(host, "HostMenu"), timeout=STEP_S)
    g1 = [stack(host), host.cmd({"cmd": "get_coop"}).get("customBattleResumePending")]
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "SavedBattle", "port": KEY, "player": "HostPlayer"})
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"), timeout=STEP_S)
    SK.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    for gc in (host, client):
        gc.wait_for(f"{gc.name} join popup", lambda gc=gc: session.has_state(gc, "Profile"), timeout=60)
        gc.ok({"cmd": "profile_ok"})
    time.sleep(2)
    ls = host.cmd({"cmd": "lobby_state"})
    button = [ls.get("buttonVisible"), ls.get("buttonText")]
    host.ok({"cmd": "lobby_action"})
    okc, secs = wait_until(lambda: bs(client).get("inBattle"), CLIENT_S)
    time.sleep(2)
    r = ev["cont"] = {"g1": g1, "button": button, "clientInBattleS": secs if okc else None,
                      "stacks": [stack(host), stack(client)],
                      "dialogs": [[gc.cmd({"cmd": "coop_dialog_count", "code": c}).get("count") for c in (62, 68)]
                                  for gc in (host, client)],
                      "phase": [es(gc).get("phase") for gc in (host, client)],
                      "desync": [es(gc).get("desyncSeen") for gc in (host, client)]}
    ok = (g1[0][-1] == "HostMenu" and "ServerList" not in g1[0] and g1[1] is True and button == [True, "CONTINUE BATTLE"]
          and okc and all(s[-1] == "BattlescapeState" for s in r["stacks"]) and r["dialogs"] == [[0, 0], [0, 0]]
          and r["phase"] == ["Active", "Active"] and r["desync"] == [False, False])
    return ok, (f"HostMenu {g1[0]} pending {g1[1]} (want HostMenu on top, no ServerList, True); button {button} (want visible "
                f"CONTINUE BATTLE); client in battle at {r['clientInBattleS']} s (bound {CLIENT_S}); stacks {r['stacks']} "
                f"(want BattlescapeState on top); dialogs 62/68 {r['dialogs']} (want 0); phase {r['phase']} (want Active); "
                f"desyncSeen {r['desync']} (want False)")


def seats_cell(host, client, ev):
    uh, uc = units(host), units(client)
    ph, pc = ptable(uh), ptable(uc)
    diff = ev["seatsDiff"] = {k: [ph.get(k), pc.get(k)] for k in set(ph) | set(pc) if ph.get(k) != pc.get(k)}
    ev["seats"] = ph
    sh, dh = seat_check(uh)
    sc, _ = seat_check(uc)
    ok, why = not diff and sh and sc, "" if sh and sc else "aliens and civilians carry the host's seat: "
    return ok, f"{why}units differing host/client {diff} (want none); host: {dh}; client seat rule met {sc}"


def mode_cell(host, client, ev):
    eh, ec = es(host), es(client)
    r = ev["mode"] = {"turnMode": [eh.get("turnMode"), ec.get("turnMode")], "option": eh.get("optionTurnMode"),
                      "activeSeat": [(e.get("coopEndTurnTally") or {}).get("activeSeat") for e in (eh, ec)]}
    ok = r["turnMode"] == ["traditional"] * 2 and r["option"] == "parallel" and r["activeSeat"] == [0, 0]
    return ok, (f"{'' if ok else 'the battle did not come back in the mode it was played in: '}turnMode {r['turnMode']} "
                f"(want traditional on both) with the host option {r['option']} (want parallel); coopEndTurnTally.activeSeat "
                f"{r['activeSeat']} (want 0 on both: the host's go)")


def deployment_cell(host, client, ev):
    d = ev["deployment"] = [bs(host).get("deployment"), bs(client).get("deployment")]
    ok, why = d == [DEPLOYMENT, DEPLOYMENT], "" if d[1] else "the second player's briefing has no mission: "
    return ok, f"{why}deployment host/client {d} (want {DEPLOYMENT} on both)"


def play_cell(host, client, ev):
    host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    time.sleep(2)
    d0 = [session.unit_of(gc, PLAY_ID).get("direction") for gc in (host, client)]
    to, base = (d0[1] + 1) % 8, es(client).get("lastSeqApplied") or 0
    resp = session.send_turn(client, PLAY_ID, to)
    session.wait_turn_settled(host, client, base, timeout=STEP_S)
    session.wait_host_idle(host, client, timeout=STEP_S)
    d1 = [session.unit_of(gc, PLAY_ID).get("direction") for gc in (host, client)]
    try:
        hok, hdetail = (bool(session.assert_hash_clean(host, client, full=True, what="client_turns_soldier")),
                        "all buckets EQUAL")
    except AssertionError as e:
        hok, hdetail = False, "hash MISMATCH: " + str(e)[:500]
    ds, side = [es(gc).get("desyncSeen") for gc in (host, client)], [bs(gc).get("side") for gc in (host, client)]
    ev["play"] = {"unit": PLAY_ID, "from": d0, "to": to, "resp": resp, "after": d1, "deny": es(client).get("lastDeny"),
                  "activeSeat": [(es(gc).get("coopEndTurnTally") or {}).get("activeSeat") for gc in (host, client)]}
    ok = d1 == [to, to] and d0[0] != to and hok and ds == [False, False] and side == [0, 0]
    return ok, (f"unit {PLAY_ID} facing {d0} -> {d1} (want {to} on both); {hdetail}; desyncSeen {ds} (want False); side "
                f"{side} (want 0 on both)")


def row_old_save_converts():
    host_dir = make_user_dir("old_custom_battle_host", saves=(FIXTURE,), options={"CoopTurnMode": "parallel"})
    host, client = GameClient("host", 0, host_dir), GameClient("client", 0, make_user_dir("old_custom_battle_client"))
    ev = {}
    try:
        try:
            boot("old_save_converts", (host, client), host, os.path.basename(FIXTURE))
        except Miss:
            return boot_failed("old_save_converts", CONVERT_CELLS, ev), None
        steps = {"conversion_lines": (False, lambda ev: load_cell(host, ev)),
                 "continue_battle": (True, lambda ev: continue_cell(host, client, ev)),
                 "seat_split": (False, lambda ev: seats_cell(host, client, ev)),
                 "played_mode": (False, lambda ev: mode_cell(host, client, ev)),
                 "deployment_shared": (False, lambda ev: deployment_cell(host, client, ev)),
                 "client_turns_soldier": (False, lambda ev: play_cell(host, client, ev))}
        cells = run_cells(CONVERT_CELLS, steps, ev)
        path = os.path.join(host_dir, "xcom1", RESAVE)
        try:
            host.ok({"cmd": "save_game", "file": RESAVE})
            ev["resave"] = wait_until(lambda: os.path.exists(path), 10, 0.2)[0]
        except Exception as e:
            ev["resave"] = f"{type(e).__name__}: {str(e)[:300]}"
        return report("old_save_converts", CONVERT_CELLS, cells, ev), (path if ev["resave"] is True else None)
    finally:
        shut(host, client)


def row_resave_not_converted(resave):
    ev = {"resave": resave}
    if not resave:
        print("CAPTURE resave_not_converted: missed row old_save_converts wrote no re-save; {}", flush=True)
        return boot_failed("resave_not_converted", RESAVE_CELLS, ev)
    host = GameClient("host", 0, make_user_dir("old_custom_battle_resave_host", saves=(resave,)))
    try:
        try:
            boot("resave_not_converted", (host,), host, RESAVE)
        except Miss:
            return boot_failed("resave_not_converted", RESAVE_CELLS, ev)

        def resave_load(ev):
            lines, us = conv(host), units(host)
            sok, sdetail = seat_check(us)
            ev["convert"], ev["units"] = lines, ptable(us)
            return (not lines and sok, f"{'' if sok else 'the next save kept the older-version tags: '}'{N_ANY}' "
                                      f"lines {len(lines)} (want 0); {sdetail}")
        return report("resave_not_converted", RESAVE_CELLS,
                      run_cells(RESAVE_CELLS, {"no_conversion_line": (False, resave_load)}, ev), ev)
    finally:
        shut(host)


def row_solo_not_converted():
    d = make_user_dir("old_custom_battle_solo_host")
    raw = open(FIXTURE, "rb").read().decode("utf-8")
    crlf = "\r\n" in raw
    solo, n = SOLO_RE.subn(lambda m: m.group(1) + "coop: 0", raw.replace("\r\n", "\n"))
    with open(os.path.join(d, "xcom1", SOLO), "wb") as f:
        f.write((solo.replace("\n", "\r\n") if crlf else solo).encode("utf-8"))
    ev = {"replaced": n, "left": len(SOLO_RE.findall(solo))}
    host = GameClient("host", 0, d)
    try:
        try:
            boot("solo_not_converted", (host,), host, SOLO)
        except Miss:
            return boot_failed("solo_not_converted", SOLO_CELLS, ev)

        def solo_load(ev):
            lines = ev["convert"] = conv(host)
            st = stack(host)
            return (not lines and st[-1] == "BattlescapeState" and ev["left"] == 0,
                    f"'{N_ANY}' lines {len(lines)} (want 0); stack {st} (want BattlescapeState on top); `coop: 1` lines "
                    f"rewritten {n}, left {ev['left']} (want 0 left)")
        return report("solo_not_converted", SOLO_CELLS,
                      run_cells(SOLO_CELLS, {"solo_save_loads": (False, solo_load)}, ev), ev)
    finally:
        shut(host)


def main():
    t0 = time.time()
    fails, resave = row_old_save_converts()
    fails += row_resave_not_converted(resave) + row_solo_not_converted()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_old_custom_battle: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
