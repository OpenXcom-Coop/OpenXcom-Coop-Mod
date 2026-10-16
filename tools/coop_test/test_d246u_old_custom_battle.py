"""D246-U stage S-D1 rows R, V and N: a classic co-op Custom Battle saved mid-battle by an OLDER version (the release line,
`main` 651ae44ba) loads on the rewrite's host converted, so MG-B's CONTINUE BATTLE resumes it with each player's own
soldiers, nobody owning the aliens, the turn mode it was played in and the mission in the partner's briefing; a save this
build wrote and a release single-player save are never converted (owner D246 (b); QD246-1 .. QD246-4 (a); QD246D-1 ..
QD246D-6 (a); orchestrator ruling R-D246D-T0-1 (A): R-play turns a seat-1 soldier, the walk is unreachable in the release
craft layout, F19407).

Spec: docs repo rewrite/prompts/d246u_sd_custom_battle_convert.md section (f); parent rewrite/prompts/
d246u_midbattle_save_convert.md (the conversion E4). Constants: rewrite/d246u-task0/sd/CONSTANTS.md (TASK 0 T0-3 .. T0-7).
Fixture: tools/coop_test/fixtures/d246usd_custom_battle.sav, made by the release build's own harness on the main-check
worktree (T0-3; parallel turns off), committed unedited. Lobby key 49221.

Row R (dirs d246usd_r_host / d246usd_r_client; host option CoopTurnMode parallel; the client starts clean):
  R-load   host load_save_menu: one "D246 S-D:" line and one summary line (seats 0/1 CD_S0/CD_S1, unseated CD_UN, turnMode
           traditional, deployment DEP_CD); every unit of another original faction on no seat (-1); soldiers == CD_EXPECT
  R-cont   open_pause_coop -> HostMenu, customBattleResumePending; host_menu_host + the join; CONTINUE BATTLE: both on the
           battle, no CoopState 62 / 68, phase Active, no desync (MG-B)
  R-seats  per unit (coop, faction, isOut, x, y, z) host == client; other factions -1; soldiers == CD_EXPECT
  R-mode   turnMode traditional on both under the host option parallel; coopEndTurnTally.activeSeat 0 on both (D100)
  R-dep    battle_state.deployment client == host == DEP_CD
  R-play   host END TURN; the client turns seat-1 soldier PLAY_ID one octant: facing equal and changed on both, every hash
           bucket EQUAL, desync false, side 0
  (R-save) host save_game RESAVE, the setup step of row V
Row V (dir d246usd_v_host): the host loads RESAVE. V-load: no "[coop-convert]" line; other factions -1; soldiers == CD_EXPECT.
Row N (dir d246usd_n_host): the fixture with every whole line `coop: 1` (a sequence item's `- coop: 1` included) rewritten
  to `coop: 0`. N-solo: no "[coop-convert]" line and the save loads (QD246D-2 (a): a release solo save is not converted).
RED on the unchanged product: R-load, R-seats, R-mode, R-dep, V-load. One EVIDENCE line per row, one PASS / FAIL line per
cell, the row verdict; every row runs after a failure. A precondition miss (R-cont, a cell that raised) ends its row: later
cells FAIL "not reached". A boot step past its bound prints ONE CAPTURE line and fails every cell of that row "boot".
WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0 only when every
cell passes, else 2.   Run:  python tools/coop_test/test_d246u_old_custom_battle.py
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

FIXTURE = os.path.join(HERE, "fixtures", "d246usd_custom_battle.sav")
KEY, RESAVE, SOLO = "49221", "d246usd_resave.sav", "d246usd_custom_battle_solo.sav"
CD_EXPECT = {8: 0, 9: 0, 10: 0, 11: 0, 12: 0, 13: 0, 14: 0, 31: 1, 32: 1, 33: 1, 34: 1, 35: 1, 36: 1, 37: 1}  # unit id: seat (T0-4)
CD_S0, CD_S1, CD_UN, CD_TANKS = 7, 7, 1, ()   # seats by E4 (1)'s rule; the Sectoid; no tank (T0-4)
DEP_CD = "STR_SMALL_SCOUT"                     # the craft's UFO destination's deployment (T0-7)
PLAY_ID = 31                                   # the lowest seat-1 soldier; every seat-1 soldier is boxed in (F19407)
LOAD_S, CLIENT_S, STEP_S = 120, 120, 30        # bounds (s); TASK 0: load 0.1 s, client in battle 1.25 s
N_SD = "[coop-convert] D246 S-D:"
N_SUM = "[coop-convert] D246: an older version's mid-battle co-op save converted"
N_ANY = "[coop-convert]"
SUM_RE = re.compile(r"seats 0/1 (\d+)/(\d+), unseated (\d+); turnMode (\w+); deployment \"([^\"]*)\"")
SOLO_RE = re.compile(r"^(\s*(?:- )?)coop: 1$", re.M)   # S54 swap (F19403): the battle units' `- coop: 1` lines too
R_CELLS, V_CELLS, N_CELLS = ("R-load", "R-cont", "R-seats", "R-mode", "R-dep", "R-play"), ("V-load",), ("N-solo",)
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
    """(ok, detail): other original factions on no seat, soldiers == CD_EXPECT, tanks on seat 0."""
    other = {k: u.get("coop") for k, u in us.items() if u.get("originalFaction") != 0}
    sold = {k: us[k].get("coop") if k in us else None for k in CD_EXPECT}
    tanks = {k: us[k].get("coop") if k in us else None for k in CD_TANKS}
    ok = bool(other) and all(v == -1 for v in other.values()) and sold == CD_EXPECT and all(v == 0 for v in tanks.values())
    return ok, f"other factions {other} (want -1 each); soldiers {sold} (want {CD_EXPECT}); tanks {tanks} (want 0)"


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
        print(f"[d246usd] shutdown: {str(e)[:300]}", flush=True)


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


def r_load(host, ev):
    lines, us = conv(host), units(host)
    sd, summ = [ln for ln in lines if N_SD in ln], [ln for ln in lines if N_SUM in ln]
    m = SUM_RE.search(summ[0]) if len(summ) == 1 else None
    got = [int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5)] if m else None
    want = [CD_S0, CD_S1, CD_UN, "traditional", DEP_CD]
    sok, sdetail = seat_check(us)
    ev["load"] = {"convert": lines, "units": ptable(us)}
    ok = len(sd) == 1 and got == want and sok
    return ok, (f"{'' if ok else 'the release save loaded unconverted: '}'{N_SD}' lines {len(sd)} (want 1); summary lines "
                f"{len(summ)} with {got} (want 1 with {want}); {sdetail}")


def r_cont(host, client, ev):
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


def r_seats(host, client, ev):
    uh, uc = units(host), units(client)
    ph, pc = ptable(uh), ptable(uc)
    diff = ev["seatsDiff"] = {k: [ph.get(k), pc.get(k)] for k in set(ph) | set(pc) if ph.get(k) != pc.get(k)}
    ev["seats"] = ph
    sh, dh = seat_check(uh)
    sc, _ = seat_check(uc)
    ok, red = not diff and sh and sc, "" if sh and sc else "aliens and civilians carry the host's seat: "
    return ok, f"{red}units differing host/client {diff} (want none); host: {dh}; client seat rule met {sc}"


def r_mode(host, client, ev):
    eh, ec = es(host), es(client)
    r = ev["mode"] = {"turnMode": [eh.get("turnMode"), ec.get("turnMode")], "option": eh.get("optionTurnMode"),
                      "activeSeat": [(e.get("coopEndTurnTally") or {}).get("activeSeat") for e in (eh, ec)]}
    ok = r["turnMode"] == ["traditional"] * 2 and r["option"] == "parallel" and r["activeSeat"] == [0, 0]
    return ok, (f"{'' if ok else 'the battle did not come back in the mode it was played in: '}turnMode {r['turnMode']} "
                f"(want traditional on both) with the host option {r['option']} (want parallel); coopEndTurnTally.activeSeat "
                f"{r['activeSeat']} (want 0 on both, D100)")


def r_dep(host, client, ev):
    d = ev["deployment"] = [bs(host).get("deployment"), bs(client).get("deployment")]
    ok, red = d == [DEP_CD, DEP_CD], "" if d[1] else "the second player's briefing has no mission: "
    return ok, f"{red}deployment host/client {d} (want {DEP_CD} on both)"


def r_play(host, client, ev):
    host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    time.sleep(2)
    d0 = [session.unit_of(gc, PLAY_ID).get("direction") for gc in (host, client)]
    to, base = (d0[1] + 1) % 8, es(client).get("lastSeqApplied") or 0
    resp = session.send_turn(client, PLAY_ID, to)
    session.wait_turn_settled(host, client, base, timeout=STEP_S)
    session.wait_host_idle(host, client, timeout=STEP_S)
    d1 = [session.unit_of(gc, PLAY_ID).get("direction") for gc in (host, client)]
    try:
        hok, hdetail = bool(session.assert_hash_clean(host, client, full=True, what="R-play")), "all buckets EQUAL"
    except AssertionError as e:
        hok, hdetail = False, "hash MISMATCH: " + str(e)[:500]
    ds, side = [es(gc).get("desyncSeen") for gc in (host, client)], [bs(gc).get("side") for gc in (host, client)]
    ev["play"] = {"unit": PLAY_ID, "from": d0, "to": to, "resp": resp, "after": d1, "deny": es(client).get("lastDeny"),
                  "activeSeat": [(es(gc).get("coopEndTurnTally") or {}).get("activeSeat") for gc in (host, client)]}
    ok = d1 == [to, to] and d0[0] != to and hok and ds == [False, False] and side == [0, 0]
    return ok, (f"unit {PLAY_ID} facing {d0} -> {d1} (want {to} on both); {hdetail}; desyncSeen {ds} (want False); side "
                f"{side} (want 0 on both)")


def row_r():
    host_dir = make_user_dir("d246usd_r_host", saves=(FIXTURE,), options={"CoopTurnMode": "parallel"})
    host, client = GameClient("host", 0, host_dir), GameClient("client", 0, make_user_dir("d246usd_r_client"))
    ev = {}
    try:
        try:
            boot("R", (host, client), host, os.path.basename(FIXTURE))
        except Miss:
            return boot_failed("R", R_CELLS, ev), None
        steps = {"R-load": (False, lambda ev: r_load(host, ev)), "R-cont": (True, lambda ev: r_cont(host, client, ev)),
                 "R-seats": (False, lambda ev: r_seats(host, client, ev)), "R-mode": (False, lambda ev: r_mode(host, client, ev)),
                 "R-dep": (False, lambda ev: r_dep(host, client, ev)), "R-play": (False, lambda ev: r_play(host, client, ev))}
        cells = run_cells(R_CELLS, steps, ev)
        path = os.path.join(host_dir, "xcom1", RESAVE)
        try:
            host.ok({"cmd": "save_game", "file": RESAVE})
            ev["resave"] = wait_until(lambda: os.path.exists(path), 10, 0.2)[0]
        except Exception as e:
            ev["resave"] = f"{type(e).__name__}: {str(e)[:300]}"
        return report("R", R_CELLS, cells, ev), (path if ev["resave"] is True else None)
    finally:
        shut(host, client)


def row_v(resave):
    ev = {"resave": resave}
    if not resave:
        print("CAPTURE V: missed row R wrote no re-save (R-save); {}", flush=True)
        return boot_failed("V", V_CELLS, ev)
    host = GameClient("host", 0, make_user_dir("d246usd_v_host", saves=(resave,)))
    try:
        try:
            boot("V", (host,), host, RESAVE)
        except Miss:
            return boot_failed("V", V_CELLS, ev)

        def v_load(ev):
            lines, us = conv(host), units(host)
            sok, sdetail = seat_check(us)
            ev["convert"], ev["units"] = lines, ptable(us)
            return (not lines and sok, f"{'' if sok else 'the next save kept the release tags: '}'{N_ANY}' lines "
                                      f"{len(lines)} (want 0); {sdetail}")
        return report("V", V_CELLS, run_cells(V_CELLS, {"V-load": (False, v_load)}, ev), ev)
    finally:
        shut(host)


def row_n():
    d = make_user_dir("d246usd_n_host")
    raw = open(FIXTURE, "rb").read().decode("utf-8")
    crlf = "\r\n" in raw
    solo, n = SOLO_RE.subn(lambda m: m.group(1) + "coop: 0", raw.replace("\r\n", "\n"))
    with open(os.path.join(d, "xcom1", SOLO), "wb") as f:
        f.write((solo.replace("\n", "\r\n") if crlf else solo).encode("utf-8"))
    ev = {"replaced": n, "left": len(SOLO_RE.findall(solo))}
    host = GameClient("host", 0, d)
    try:
        try:
            boot("N", (host,), host, SOLO)
        except Miss:
            return boot_failed("N", N_CELLS, ev)

        def n_solo(ev):
            lines = ev["convert"] = conv(host)
            st = stack(host)
            return (not lines and st[-1] == "BattlescapeState" and ev["left"] == 0,
                    f"'{N_ANY}' lines {len(lines)} (want 0); stack {st} (want BattlescapeState on top); `coop: 1` lines "
                    f"rewritten {n}, left {ev['left']} (want 0 left)")
        return report("N", N_CELLS, run_cells(N_CELLS, {"N-solo": (False, n_solo)}, ev), ev)
    finally:
        shut(host)


def main():
    t0 = time.time()
    fails, resave = row_r()
    fails += row_v(resave) + row_n()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_d246u_old_custom_battle: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
