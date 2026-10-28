"""D246-U stage S-D2b rows R2, R3, R4 and V: a PvP (gm2, gm3) or PvE2 (gm4) co-op Custom Battle saved mid-battle by an OLDER
version (the release line, `main` 651ae44ba) loads on the rewrite's host converted, so MG-B's CONTINUE BATTLE resumes it with
each side on the seat the rewrite gives it in that mode (gm2: X-COM seat 0, the aliens seat 1; gm3: the release host's
faction swap undone, the aliens seat 0, X-COM seat 1; gm4: each alien on the seat it had, X-COM nobody's), the turn mode it
was played in, the mission in the partner's briefing, and a re-save in the rewrite's format (owner D246 (b); orchestrator
rulings R-D246D2-1, R-D246D2-3, R-D246D2-4; QD246D2-4 .. QD246D2-8 (a)).

Spec: docs repo rewrite/prompts/d246u_sd2b_release_pvp_cb_convert.md section (f); the common file
d246u_sd2_pvp_custom_battle_convert.md (rulings, R3). Constants: rewrite/d246u-task0/sd2b/CONSTANTS.md (TASK 0 T0-3 .. T0-7).
Fixtures: tools/coop_test/fixtures/gm<2|3|4>_custom_battle.sav, made by the release build's own harness on the
main-check worktree (T0-3; parallel turns off), committed unedited. Lobby key 49254.

Rows R2 / R3 / R4 (dirs d246sd2b_r<n>_host / _client; host option CoopTurnMode parallel; the partner starts clean):
  Rn-load   host load_save_menu: one "D246 S-D:" line, one "an older version's PvP / PvE2 Custom Battle save" line naming game mode n (gm3: the swap undone on
            > 0 units) and one summary line (seats 0/1 CD_S0/CD_S1, unseated CD_UN, turnMode traditional, deployment DEP);
            every unit's seat == CD_SEAT
  Rn-cont   open_pause_coop -> HostMenu, customBattleResumePending; host_menu_host + the join; CONTINUE BATTLE: both on the
            battle, no CoopState 62 / 68, phase Active, no desync
  Rn-seats  per unit (coop, faction, isOut, x, y, z) host == partner; seats == CD_SEAT, factions == CD_FAC (gm3: the aliens
            faction 1 seat 0, X-COM faction 0 seat 1; gm4: X-COM nobody's, the aliens 0 / 1 as tagged); gm4 also: every
            X-COM unit's armorCur AND armorMax per side == G4_X_ARMOR on BOTH machines at the resumed turn (the save's
            turn 2; battle_state.units, the probe of the TASK 0 capture for F20049; QD246D2-9 (a), R-D246D2-5)
  Rn-mode   turnMode traditional on both under the host option parallel
  Rn-dep    battle_state.deployment partner == host == DEP
  Rn-play   the side to move presses END TURN (gm2 the host, gm3 the partner, gm4 the host then the partner): side 1 on
            both; every hash bucket EQUAL before the press; desyncSeen false on both. gm4: side 1 is
            the host's X-COM AI side, which ends on its own: side 1 on both is drive_side_change's return, then side 0 of
            turn 3 (G4_SETTLE) on both after wait_host_idle (the AI side crossed, test_skirmish_saved_pve2_end_turn SD2)
  (R3-save) host save_game RESAVE after R3-play's reads, the setup step of row V
Row V (dir d246sd2b_v_host): the host loads RESAVE. V-load: no "[coop-convert]" line; seats == CD_SEAT[3], factions ==
  CD_FAC[3] (the aliens faction 1, X-COM faction 0).
RED on the unchanged product (TASK 0 T0-6, R-D246D2-4; 15 of 19): R2-load, R2-mode, R2-dep; R3-load, R3-seats, R3-mode,
R3-dep, R3-play; R4-load, R4-cont (the release gm4 battle desyncs: its X-COM units' saved armor is above the maximum the
rewrite builds, F20049), R4-seats, R4-mode, R4-dep, R4-play (not reached); V-load. R2-seats is green at red (the release
gm2 tags already equal the rule); R2-cont, R2-play, R3-cont pass. One EVIDENCE line per row, one PASS / FAIL line per
cell, the row verdict; every row runs after a failure. A precondition miss (Rn-cont, a cell that raised) ends its row:
later cells FAIL "not reached". A boot step past its bound prints ONE CAPTURE line and fails every cell of that row "boot".
run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.
Run:  python tools/coop_test/test_old_pvp_custom_battle.py
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
from repro_atom_side_begin import drive_side_change  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
KEY, RESAVE, DIR = "49254", "d246sd2b_resave.sav", "d246sd2b"
XCOM, ALIENS = (8, 9, 10, 11, 12, 13, 14), (1000000,)          # gm2 / gm3 battle unit ids (T0-4)
G4_A1, G4_A0 = (1000000, 1000001, 1000002, 1000003, 1000004), (1000005, 1000006, 1000007, 1000008)   # gm4 aliens tagged 1 / 0
G4_X = (2000008, 2000009, 2000010, 2000011, 2000012, 2000013, 2000014)                               # gm4 X-COM (MALE_CIVILIAN)
G4_X_ARMOR = [12, 8, 8, 5, 2]   # gm4 X-COM armor as played, front/left/right/rear/under, cur AND max
CD_SEAT = {2: {**{i: 0 for i in XCOM}, **{i: 1 for i in ALIENS}}, 3: {**{i: 1 for i in XCOM}, **{i: 0 for i in ALIENS}},
           4: {**{i: 1 for i in G4_A1}, **{i: 0 for i in G4_A0}, **{i: -1 for i in G4_X}}}   # (b) 2's rule (T0-4, T0-7)
CD_FAC = {2: {**{i: 0 for i in XCOM}, **{i: 1 for i in ALIENS}}, 3: {**{i: 0 for i in XCOM}, **{i: 1 for i in ALIENS}},
          4: {**{i: 0 for i in G4_A1 + G4_A0}, **{i: 1 for i in G4_X}}}                     # faction after the load (T0-7)
CD_SUM = {2: (7, 1, 0), 3: (1, 7, 0), 4: (4, 5, 7)}            # summary line seats 0 / 1, unseated (T0-4, T0-7)
DEP = {2: "STR_SMALL_SCOUT", 3: "STR_SMALL_SCOUT", 4: "STR_BATTLESHIP"}   # the in-battle craft's UFO (T0-7)
PRESS = {2: ("host",), 3: ("client",), 4: ("host", "client")}  # the side to move; gm4: both seats, the host first (T0-6/7)
SIDE_NEXT = 1                                                  # END TURN hands side 0 to side 1 in every mode
G4_SETTLE = [0, 3]   # gm4: side 0 of the save's turn 2 + 1 once the X-COM AI side ends (R-D246D2-6, F20250; SD2's settle)
LOAD_S, CLIENT_S, STEP_S = 120, 120, 30                        # bounds (s); TASK 0 measured times in CONSTANTS.md
N_SD, N_SD2 = "[coop-convert] D246 S-D:", "[coop-convert] an older version's PvP / PvE2 Custom Battle save, game mode"
N_SUM = "[coop-convert] an older version's mid-battle co-op save converted"
N_ANY = "[coop-convert]"
SUM_RE = re.compile(r"seats 0/1 (\d+)/(\d+), unseated (\d+); turnMode (\w+); deployment \"([^\"]*)\"")
SD2_RE = re.compile(r"game mode (\d+) - the release gm3 swap undone on (\d+) unit")
R_CELLS = ("load", "cont", "seats", "mode", "dep", "play")
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


def seat_check(n, us):
    """(ok, detail): every unit's seat == CD_SEAT[n] and faction == CD_FAC[n]."""
    seats = {k: us[k].get("coop") if k in us else None for k in CD_SEAT[n]}
    facs = {k: us[k].get("faction") if k in us else None for k in CD_FAC[n]}
    off = {k: [seats[k], facs[k]] for k in CD_SEAT[n] if seats[k] != CD_SEAT[n][k] or facs[k] != CD_FAC[n][k]}
    ok = not off and set(us) == set(CD_SEAT[n])
    return ok, (f"units off (seat, faction) {off} (want CD_SEAT / CD_FAC: {sorted(set(CD_SEAT[n].items()))} / "
                f"{sorted(set(CD_FAC[n].items()))}); unit ids {sorted(us)} (want {sorted(CD_SEAT[n])})")


def hash_now(host, client):
    try:
        session.assert_hash_clean(host, client, full=True, what="play")
        return "all buckets EQUAL"
    except AssertionError as e:
        return "MISMATCH: " + str(e)[:400]


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
        return secs
    except Exception as e:
        capture(tag, f"{type(e).__name__}: {str(e)[:600]}", machines)
        raise Miss(tag)


def shut(*gcs):
    try:
        shutdown_clients(*gcs)
    except RuntimeError as e:
        print(f"[d246sd2b] shutdown: {str(e)[:300]}", flush=True)


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


def r_load(n, host, ev):
    lines, us = conv(host), units(host)
    sd, sd2, summ = ([ln for ln in lines if k in ln] for k in (N_SD, N_SD2, N_SUM))
    m = SUM_RE.search(summ[0]) if len(summ) == 1 else None
    got = [int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5)] if m else None
    want = [*CD_SUM[n], "traditional", DEP[n]]
    m2 = SD2_RE.search(sd2[0]) if len(sd2) == 1 else None
    mode = [int(m2.group(1)), int(m2.group(2))] if m2 else None
    mode_ok = bool(mode) and mode[0] == n and (mode[1] > 0 if n == 3 else True)
    sok, sdetail = seat_check(n, us)
    ev["load"] = {"convert": lines, "units": ptable(us)}
    ok = len(sd) == 1 and mode_ok and got == want and sok
    return ok, (f"{'' if ok else 'the release save loaded unconverted: '}'{N_SD}' lines {len(sd)} (want 1); '{N_SD2}' lines "
                f"{len(sd2)} with (game mode, units unswapped) {mode} (want 1 with mode {n}{', > 0 units' if n == 3 else ''}); "
                f"summary lines {len(summ)} with {got} (want 1 with {want}); {sdetail}")


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
    r = ev["cont"] = {"g1": g1, "button": button, "teams": ls.get("playerTeams"), "clientInBattleS": secs if okc else None,
                      "stacks": [stack(host), stack(client)],
                      "dialogs": [[gc.cmd({"cmd": "coop_dialog_count", "code": c}).get("count") for c in (62, 68)]
                                  for gc in (host, client)],
                      "phase": [es(gc).get("phase") for gc in (host, client)],
                      "desync": [es(gc).get("desyncSeen") for gc in (host, client)],
                      "gamemode": [bs(gc).get("coopGamemode") for gc in (host, client)]}
    ok = (g1[0][-1] == "HostMenu" and "ServerList" not in g1[0] and g1[1] is True and button == [True, "CONTINUE BATTLE"]
          and okc and all(s[-1] == "BattlescapeState" for s in r["stacks"]) and r["dialogs"] == [[0, 0], [0, 0]]
          and r["phase"] == ["Active", "Active"] and r["desync"] == [False, False])
    return ok, (f"HostMenu {g1[0]} pending {g1[1]} (want HostMenu on top, no ServerList, True); button {button} (want visible "
                f"CONTINUE BATTLE); partner in battle at {r['clientInBattleS']} s (bound {CLIENT_S}); stacks {r['stacks']} "
                f"(want BattlescapeState on top); dialogs 62/68 {r['dialogs']} (want 0); phase {r['phase']} (want Active); "
                f"desyncSeen {r['desync']} (want False)")


def r_seats(n, host, client, ev):
    uh, uc = units(host), units(client)
    ph, pc = ptable(uh), ptable(uc)
    diff = ev["seatsDiff"] = {k: [ph.get(k), pc.get(k)] for k in set(ph) | set(pc) if ph.get(k) != pc.get(k)}
    ev["seats"] = ph
    sh, dh = seat_check(n, uh)
    sc, _ = seat_check(n, uc)
    red = {3: "the release gm3 swap kept (factions swapped): ", 4: "the X-COM side carries the host's seat: "}.get(n, "")
    armor_off, armor = {}, ""
    if n == 4:   # the X-COM side keeps its played armor (cur AND max) on both machines at the resumed turn
        a = ev["armor"] = {gc.name: {k: [us[k].get("armorCur"), us[k].get("armorMax")] if k in us else None for k in G4_X}
                           for gc, us in ((host, uh), (client, uc))}
        ev["armorAt"] = [[bs(g).get("side"), bs(g).get("turn")] for g in (host, client)]
        for m in a:
            off = {k: v for k, v in a[m].items() if v != [G4_X_ARMOR, G4_X_ARMOR]}
            if off:
                armor_off[m] = off
        armor = (f"; {'' if not armor_off else 'the X-COM side lost its played armor: '}X-COM (armorCur, armorMax) off "
                 f"host/partner {armor_off} (want {G4_X_ARMOR} / {G4_X_ARMOR} on both) at (side, turn) {ev['armorAt']}")
    ok = not diff and sh and sc and not armor_off
    return ok, (f"{'' if sh and sc else red}units differing host/partner {diff} (want none); host: {dh}; partner rule met {sc}"
                f"{armor}")


def r_mode(host, client, ev):
    eh, ec = es(host), es(client)
    r = ev["mode"] = {"turnMode": [eh.get("turnMode"), ec.get("turnMode")], "option": eh.get("optionTurnMode"),
                      "activeSeat": [eh.get("coopActiveSeat"), ec.get("coopActiveSeat")]}
    ok = r["turnMode"] == ["traditional"] * 2 and r["option"] == "parallel"
    return ok, (f"{'' if ok else 'the battle did not come back in the mode it was played in: '}turnMode {r['turnMode']} "
                f"(want traditional on both) with the host option {r['option']} (want parallel)")


def r_dep(n, host, client, ev):
    d = ev["deployment"] = [bs(host).get("deployment"), bs(client).get("deployment")]
    ok, red = d == [DEP[n], DEP[n]], "" if d[1] else "the second player's briefing has no mission: "
    return ok, f"{red}deployment host/partner {d} (want {DEP[n]} on both)"


def r_play(n, host, client, ev):
    m = {"host": host, "client": client}
    p = ev["play"] = {"before": [[bs(g).get("side"), bs(g).get("turn")] for g in (host, client)],
                      "hash": hash_now(host, client), "press": []}
    for i, who in enumerate(PRESS[n]):
        if i:   # the second seat presses once its END TURN is live (traditional: the baton reached it)
            p["readyS"] = wait_until(lambda: es(client).get("coopActiveSeat") != 0, STEP_S)[1]
        p["press"].append([who, m[who].cmd({"cmd": "battle_action", "action": "end_turn_button"}),
                           [es(g).get("coopActiveSeat") for g in (host, client)]])
    try:
        p["side1"] = [[s.get("side"), s.get("turn")] for s in drive_side_change(host, client, SIDE_NEXT, timeout=STEP_S)]
        session.wait_host_idle(host, client, timeout=STEP_S)
        if n == 4:   # the host's X-COM AI side ends on its own; SD2's settle on side 0 of turn 3
            drive_side_change(host, client, G4_SETTLE[0], want_turn_min=G4_SETTLE[1], timeout=STEP_S)
    except Exception as e:
        p["sideError"] = f"{type(e).__name__}: {str(e)[:300]}"
    side = p["after"] = [[bs(g).get("side"), bs(g).get("turn")] for g in (host, client)]
    ds = p["desync"] = [es(g).get("desyncSeen") for g in (host, client)]
    if n == 4:
        side_ok = [s[0] for s in p.get("side1", [[None], [None]])] == [SIDE_NEXT] * 2 and side == [G4_SETTLE] * 2
        want = (f"want side {SIDE_NEXT} on both from drive_side_change: {p.get('side1')}; then {G4_SETTLE} on both, the X-COM "
                f"AI side crossed")
    else:
        side_ok, want = side[0][0] == side[1][0] == SIDE_NEXT, f"want side {SIDE_NEXT} on both"
    ok = "sideError" not in p and side_ok and p["hash"] == "all buckets EQUAL" and ds == [False, False]
    return ok, (f"{' then '.join(PRESS[n])} END TURN {[x[1].get('ok') for x in p['press']]}; "
                f"{p.get('sideError') or 'side change reached'}; (side, turn) host/partner {p['before']} -> {side} ({want}); "
                f"hash before the press {p['hash']} (want all buckets EQUAL); desyncSeen {ds} (want False)")


def row_r(n):
    row, order = f"R{n}", [f"R{n}-{c}" for c in R_CELLS]
    host_dir = make_user_dir(f"{DIR}_r{n}_host", saves=(os.path.join(FIX, f"gm{n}_custom_battle.sav"),),
                             options={"CoopTurnMode": "parallel"})
    host, client = GameClient("host", 0, host_dir), GameClient("client", 0, make_user_dir(f"{DIR}_r{n}_client"))
    ev, resave = {}, None
    try:
        try:
            ev["loadS"] = boot(row, (host, client), host, f"gm{n}_custom_battle.sav")
        except Miss:
            return boot_failed(row, order, ev), None
        fns = {"load": (False, lambda ev: r_load(n, host, ev)), "cont": (True, lambda ev: r_cont(host, client, ev)),
               "seats": (False, lambda ev: r_seats(n, host, client, ev)), "mode": (False, lambda ev: r_mode(host, client, ev)),
               "dep": (False, lambda ev: r_dep(n, host, client, ev)), "play": (False, lambda ev: r_play(n, host, client, ev))}
        cells = run_cells(order, {f"{row}-{c}": fns[c] for c in R_CELLS}, ev)
        if n == 3:
            path = os.path.join(host_dir, "xcom1", RESAVE)
            try:
                host.ok({"cmd": "save_game", "file": RESAVE})
                ev["resave"] = wait_until(lambda: os.path.exists(path), 10, 0.2)[0]
                time.sleep(1.0)   # the write completes after the file appears
            except Exception as e:
                ev["resave"] = f"{type(e).__name__}: {str(e)[:300]}"
            resave = path if ev["resave"] is True else None
        return report(row, order, cells, ev), resave
    finally:
        shut(host, client)


def row_v(resave):
    ev = {"resave": resave}
    if not resave:
        print("CAPTURE V: missed row R3 wrote no re-save (R3-save); {}", flush=True)
        return boot_failed("V", ("V-load",), ev)
    host = GameClient("host", 0, make_user_dir(f"{DIR}_v_host", saves=(resave,)))
    try:
        try:
            ev["loadS"] = boot("V", (host,), host, RESAVE)
        except Miss:
            return boot_failed("V", ("V-load",), ev)

        def v_load(ev):
            lines, us = conv(host), units(host)
            sok, sdetail = seat_check(3, us)
            ev["convert"], ev["units"] = lines, ptable(us)
            return (not lines and sok, f"{'' if sok else 'the next save kept the release tags: '}'{N_ANY}' lines "
                                      f"{len(lines)} (want 0); {sdetail}")
        return report("V", ("V-load",), run_cells(("V-load",), {"V-load": (False, v_load)}, ev), ev)
    finally:
        shut(host)


def main():
    t0 = time.time()
    fails, resave = 0, None
    for n in (2, 3, 4):
        f, r = row_r(n)
        fails, resave = fails + f, (r if n == 3 else resave)
    fails += row_v(resave)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_old_pvp_custom_battle: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
