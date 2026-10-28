"""MG-B S-B row CB3: a single-player Custom Battle hosted from the battle's pause menu (CO-OP, host, CONTINUE BATTLE) becomes a
classic co-op battle before the lobby opens: the soldiers split evenly in unit-list order, the second player (seat 1) takes the
first floor(N/2), the host (seat 0) the rest (the odd one included) and every other original-PLAYER unit, and the battle plays in
the host window's TURNS mode (owner D237 (b), D245 (a), D237-V1, D235 (a); QMB2-2 (a), QMB2-3 (a); V5). Spec: docs repo
rewrite/prompts/mgb2_common.md (rulings, R3, QMB2-1 .. QMB2-5 (a)), mgb2_sb_convert.md (this stage, (f)), mgb2_sa_continue.md
(S-A, whose CONTINUE BATTLE route this rides); constants rewrite/mgb2-task0/sb/CONSTANTS.md (TASK 0 boots a, b, c at efd5389ac);
orchestrator ruling R-MGBB-1 (a) (C1's red value). Lobby key 49209.

CB3 (one boot pair): the host (CoopTurnMode parallel) settles a solo New Battle (set_seed 1) and records N soldiers, T other
original-PLAYER units and the unit-list order; open_pause_coop (a real PauseState and its CO-OP click); host_menu_host; a clean
client joins; the host presses CONTINUE BATTLE; the cells read 2 s after the client is in battle.
C1 transfer: the client in battle, no CoopState 68 on its stack, both phase Active (R-MGBB-1 (a): only "in battle" and "Active"
gate the row). C2 seats: seat 1 = the first floor(N/2) soldiers in unit order, seat 0 = the other ceil(N/2) and the T others,
every other unit no seat, host == client per unit id, the host's "is now co-op" line once with N / floor / ceil / T. C3 mode:
coopGamemode 1 and turnMode parallel on both. C4 play: the client walks a staged seat-1 soldier one tile: equal on both, every
bucket EQUAL, no desync on either.
RED on the unchanged product: C1 (the hold stays under the alien-turn screen: with no seat, W2-H31 ends the
players' side at once, F19162), C2 (the hosted single-player battle has no seats, F5103), C3-C4 not reached (C2). GREEN
(EB1-EB2): every cell PASS. One EVIDENCE line, one PASS / FAIL line per cell, the row verdict. A precondition miss (C1's gate,
C2, a cell that raised) ends the row: later cells FAIL "not reached (<cell>)". A boot step past its bound prints ONE CAPTURE
line and fails every cell "boot". run in the foreground to completion. ONE run is the result, no
skip path; exit 0 only when every cell passes, else 2.   Run:  python tools/coop_test/test_skirmish_saved_battle_convert.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402
import session  # noqa: E402
import test_skirmish_flow as SK  # noqa: E402

KEY3, SEED3 = "49209", 1        # TASK 0 boots a, b, c: N 14 (ids 1-14), T 0, one alien, every seat -1 before the host
CLIENT_S, STEP_S = 120, 30      # bounds (s); TASK 0: the client in battle 1.16 s after CONTINUE BATTLE (red and green)
N_CONV = "[coop] MG-B: the single-player Custom Battle is now co-op"
N_H31 = "W2-H31: no seat has a live unit on the active side"
DLG_RESUME_HOLD = 68
CELLS = ("C1", "C2", "C3", "C4")
stack, bs, es = session.states_stripped, session.battle_state, session.event_state


class Miss(Exception):
    """A boot step past its bound (its CAPTURE line is printed)."""


def top(gc):
    s = stack(gc)
    return s[-1] if s else None


def dialog(gc):
    d = gc.cmd({"cmd": "coop_dialog_info"})
    return d.get("code") if d.get("present") else None


def log_lines(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def seats(gc):
    return {str(u["id"]): u.get("coop") for u in bs(gc).get("units", [])}


def wait_until(pred, bound, interval=0.25):
    t = time.time()
    while time.time() - t < bound:
        if pred():
            return True, round(time.time() - t, 2)
        time.sleep(interval)
    return bool(pred()), round(time.time() - t, 2)


def hash_cell(host, client, what):
    try:
        return bool(session.assert_hash_clean(host, client, full=True, what=what)), "all buckets EQUAL"
    except AssertionError as e:
        return False, "hash MISMATCH: " + str(e)[:500]


PROBES = (("stack", stack), ("dialog", dialog), ("coop", lambda g: g.cmd({"cmd": "get_coop"})),
          ("battle", lambda g: {k: bs(g).get(k) for k in ("inBattle", "side", "turn", "coopGamemode", "pendingStates")}),
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


def missed(tag, err, machines):
    capture(tag, err, machines)
    raise Miss(tag)


def shut(*gcs):
    try:
        shutdown_clients(*gcs)
    except RuntimeError as e:
        print(f"[mgb] shutdown: {str(e)[:300]}", flush=True)


def report(row, cells, ev):
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    for name in CELLS:
        print(f"{'PASS' if cells[name][0] else 'FAIL'} {name}: {cells[name][1]}", flush=True)
    fails = sum(1 for name in CELLS if not cells[name][0])
    print(f"{row} {'PASS' if not fails else 'FAIL'} ({fails} of {len(CELLS)} cells failed)", flush=True)
    return fails


def run_cells(steps, ev):
    """Cells in order. A cell returns (pass, detail[, gate]); a gating cell whose gate (default: its pass) fails, or any cell
    that raises, ends the row (later cells: not reached)."""
    cells, stop = {}, None
    for name in CELLS:
        gating, fn = steps[name]
        if stop:
            cells[name] = (False, f"not reached ({stop})")
            continue
        try:
            r = fn(ev)
        except Exception as e:
            cells[name], stop = (False, f"raised {type(e).__name__}: {str(e)[:500]}"), name
            continue
        cells[name] = r[:2]
        stop = name if gating and not (r[2] if len(r) > 2 else r[0]) else None
    return cells


def join(host, client, key):
    """The client's browser + join_tcp; profile_ok on both join popups (main #181's shape)."""
    SK.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": "ClientPlayer"})
    for gc in (host, client):
        gc.wait_for(f"{gc.name} join popup", lambda gc=gc: session.has_state(gc, "Profile"), timeout=60)
        gc.ok({"cmd": "profile_ok"})


def row_cb3():
    host = GameClient("host", 0, make_user_dir("mgb_cb3_host", options={"CoopTurnMode": "parallel"}))
    client = GameClient("client", 0, make_user_dir("mgb_cb3_client"))
    m, ev = (host, client), {}

    def boot():
        host.spawn(), client.spawn(), host.connect(), client.connect()
        host.ok({"cmd": "open_new_battle"})
        host.wait_for("NewBattleState", lambda: session.has_state(host, "NewBattleState"), timeout=60)
        host.ok({"cmd": "set_seed", "seed": SEED3}), host.ok({"cmd": "newbattle_ok"})
        host.wait_for("SP battle", lambda: (session.has_state(host, "BriefingState") or session.has_state(
            host, "InventoryState") or session.has_state(host, "BattlescapeState")), timeout=180, interval=0.5)
        if session.has_state(host, "BriefingState"):
            host.ok({"cmd": "close_briefing"})
        host.wait_for("equip screen", lambda: session.has_state(host, "InventoryState"), timeout=STEP_S, interval=0.3)
        session.dismiss_battle_start_overlays(host)
        ok, secs = wait_until(lambda: top(host) == "BattlescapeState" and bs(host).get("pendingStates") == 0
                              and bs(host).get("side") == 0, STEP_S)
        if not ok:
            missed("CB3", f"settle: top BattlescapeState, pendingStates 0, side 0 not reached in {secs} s", m)
        us = bs(host).get("units", [])
        ev["solo"] = {"order": [u["id"] for u in us], "seats": sorted({u.get("coop") for u in us}),
                      "soldiers": [u["id"] for u in us if u.get("originalFaction") == 0 and u.get("isPlayerSoldier")],
                      "others": [u["id"] for u in us if u.get("originalFaction") == 0 and not u.get("isPlayerSoldier")],
                      "alien": any(u.get("faction") == 1 and not u.get("isOut") for u in us)}
        if len(ev["solo"]["soldiers"]) < 2 or not ev["solo"]["alien"] or ev["solo"]["seats"] != [-1]:
            missed("CB3", f"solo precondition: {ev['solo']} (want >= 2 soldiers, an alien alive, every seat -1)", m)
        host.ok({"cmd": "open_pause_coop"})
        host.wait_for("HostMenu", lambda: top(host) == "HostMenu", timeout=STEP_S)
        host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "SoloBattle", "port": KEY3, "player": "HostPlayer"})
        host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"), timeout=STEP_S)
        join(host, client, KEY3)
        host.wait_for("CONTINUE BATTLE", lambda: (lambda ls: ls.get("buttonVisible") and ls.get("buttonText") == (
            "CONTINUE BATTLE"))(host.cmd({"cmd": "lobby_state"})), timeout=STEP_S)

    def c1(ev):
        t = time.time()
        host.ok({"cmd": "lobby_action"})
        _, at = wait_until(lambda: bs(client).get("inBattle"), CLIENT_S)
        time.sleep(2)
        r = ev["c1"] = {"clientInBattleS": at, "inBattle": bool(bs(client).get("inBattle")), "host": stack(host),
                        "client": stack(client), "clientDialog": dialog(client), "phase": [es(g).get("phase") for g in m],
                        "h31": sum(1 for line in log_lines(host) if N_H31 in line), "wallS": round(time.time() - t, 2)}
        gate = r["inBattle"] and r["phase"] == ["Active", "Active"]
        hold = r["clientDialog"] == DLG_RESUME_HOLD
        return gate and not hold, (
            f"client in battle {r['inBattle']} at {at} s (bound {CLIENT_S}); client {r['client']} dialog {r['clientDialog']} "
            f"(want no {DLG_RESUME_HOLD} on its stack{'; the hold stays under ' + r['client'][-1] if hold else ''}); host "
            f"{r['host']}; phase {r['phase']} (want Active on both); host '{N_H31}' lines {r['h31']}"), gate

    def c2(ev):
        sold, others = ev["solo"]["soldiers"], ev["solo"]["others"]
        n, t = len(sold), len(others)
        hs, cs = seats(host), seats(client)
        want = {str(i): (1 if k < n // 2 else 0) for k, i in enumerate(sold)}
        want.update({str(i): 0 for i in others})
        want.update({k: -1 for k in set(hs) | set(cs) if k not in want})
        s1, s0 = [i for i in sold if hs.get(str(i)) == 1], [i for i in sold if hs.get(str(i)) == 0]
        diff = ev["c2Diff"] = {k: [hs.get(k), cs.get(k), want[k]] for k in sorted(want, key=int)
                               if not hs.get(k) == cs.get(k) == want[k]}
        conv = ev["c2Conv"] = [line[-200:] for line in log_lines(host) if N_CONV in line]
        tail = f"{n} soldier(s), seat 1: {n // 2}, seat 0: {n - n // 2} + {t} other unit(s)"
        return (not diff and len(conv) == 1 and tail in conv[0],
                f"{'the hosted single-player battle has no seats: ' if not s1 and not s0 else ''}seat-1 / seat-0 soldiers "
                f"{s1} / {s0} (want the first {n // 2} / the other {n - n // 2} of N {n} in unit order; T {t} others on seat "
                f"0); units differing [host, client, want] {json.dumps(diff)[:600]} (want none); host '{N_CONV}' lines "
                f"{len(conv)} (want 1 reading '{tail}')")

    def c3(ev):
        r = ev["c3"] = {"coopGamemode": [bs(g).get("coopGamemode") for g in m], "turnMode": [es(g).get("turnMode") for g in m]}
        return (r["coopGamemode"] == [1, 1] and r["turnMode"] == ["parallel", "parallel"],
                f"coopGamemode {r['coopGamemode']} (want 1 on both); turnMode {r['turnMode']} (want parallel on both)")

    def c4(ev):
        s1 = [u.get("soldierId") for u in bs(host).get("units", []) if u.get("coop") == 1 and u.get("isPlayerSoldier")
              and not u.get("isOut")]
        after, tile, run_dir = session.stage_open_ground_actor(host, client, s1, tag="mgb-cb3")
        dest, prev = (tile[0] + session.DIR_DX[run_dir], tile[1] + session.DIR_DY[run_dir], tile[2]), session.walk_action_id(
            host)
        ev["c4"] = {"unit": after["id"], "tile": tile, "dir": run_dir, "dest": dest,
                    "resp": session.send_walk(client, after["id"], dest)}
        session.wait_walk_settled(host, client, prev, timeout=STEP_S), session.wait_host_idle(host, client, timeout=STEP_S)
        p = [(lambda u: (u["x"], u["y"], u["z"]))(session.unit_of(gc, after["id"])) for gc in m]
        hok, hdetail = hash_cell(host, client, "CB3 C4")
        ds = [es(g).get("desyncSeen") for g in m]
        return (p[0] == p[1] == dest and hok and ds == [False, False],
                f"the client walked unit {after['id']} {tile} -> {dest}: host/client {p} (want {dest} on both); {hdetail}; "
                f"desyncSeen {ds} (want False/False)")

    try:
        try:
            boot()
        except Exception as e:
            if not isinstance(e, Miss):
                capture("CB3", f"{type(e).__name__}: {str(e)[:600]}", m)
            return report("CB3", {c: (False, "boot (see the CAPTURE CB3 line)") for c in CELLS}, ev)
        steps = {"C1": (True, c1), "C2": (True, c2), "C3": (False, c3), "C4": (False, c4)}
        return report("CB3", run_cells(steps, ev), ev)
    finally:
        shut(host, client)


def main():
    t0 = time.time()
    fails = row_cb3()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_skirmish_saved_battle_convert: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
