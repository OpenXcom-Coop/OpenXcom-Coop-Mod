"""A saved co-op Custom Battle hosted from the battle's pause menu continues for both players through CONTINUE
BATTLE; a loaded single-player Custom Battle's pause-menu CO-OP hides while an action runs. The saved PvE2 battle's
row is in test_skirmish_saved_pve2_continue.py. Lobby key 49207.

coop_button_gate (one solo boot): a settled single-player New Battle (set_seed 1). coop_shown_at_rest: open_pause_coop
(a real PauseState and its CO-OP click), pop its HostMenu: CO-OP visible. coop_hidden_while_busy: WALK (the first
soldier with TU >= 30 to the farthest open tile 6..12 tiles away on a straight line, pendingStates > 0), then as
coop_shown_at_rest: CO-OP hidden, as vanilla hides Save.
saved_coop_continue (classic gm1): the seed pair (host CoopTurnMode traditional, seat 1 = squad index 0, 1) saves its
settled battle; a fresh host (CoopTurnMode parallel) loads it, a clean client joins. host_menu_pending:
open_pause_coop: HostMenu, customBattleResumePending. lobby_offer: host_menu_host + the join: both in LobbyMenu,
CONTINUE BATTLE offered. both_on_battle: CONTINUE BATTLE: both on the saved battle, no dialog 62 / 68, no LobbyMenu or
BriefingState on the client (read 2 s later). session_active: phase Active, no desync, the disk-resume offer and the
CONTINUE BATTLE line once each. units_equal: units (coop, faction, isOut, x, y, z) host == client == P, seat counts.
turn_mode_kept: turnMode traditional under the host option parallel; holder == the seed's active seat.
hash_equal: every bucket EQUAL. end_turn_walk: host END TURN: holder 1; the client walks a staged seat-1 unit one
tile; equal on both, every bucket EQUAL, no desync.
Without the fix: coop_hidden_while_busy fails (CO-OP shows while an action runs), both_on_battle fails (the client
never gets the saved battle), session_active .. end_turn_walk are not reached. One EVIDENCE line per row, one PASS /
FAIL line per cell, the row verdict; every row runs after a failure. A precondition miss (host_menu_pending,
lobby_offer, both_on_battle, coop_hidden_while_busy's walk, a cell that raised) ends its row: later cells FAIL "not
reached (<cell>)". A boot step past its bound prints ONE CAPTURE line and fails every cell of that row "boot". ONE run
is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_skirmish_saved_battle_join.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402
import session  # noqa: E402
import test_skirmish_flow as SK  # noqa: E402

KEY, SAVE = "49207", "saved_continue.sav"
SEED, SEATED = 1, 2      # set_seed right before newbattle_ok; seat 1 = squad index 0, 1
CLIENT_S, HOST_S, STEP_S, LOAD_S, BUSY_S = 120, 30, 30, 120, 5   # bounds (s); measured: 1.0, 1.4, -, 1.5, 0.05
TU_WALK, WALK_FAR, WALK_NEAR = 30, 12, 6
N_REFUSE = "offerRejoinBattle() called while the battle is not paused"
N_DISK_RESUME = "disk-resume battle_offer sent"
N_CONTINUE = "[coop] CONTINUE BATTLE offers the loaded Custom Battle"
DLG_WAIT_PLAYERS, DLG_RESUME_HOLD = 62, 68
GATE_CELLS, CONTINUE_CELLS = (("coop_shown_at_rest", "coop_hidden_while_busy"),
                              ("host_menu_pending", "lobby_offer", "both_on_battle", "session_active", "units_equal",
                               "turn_mode_kept", "hash_equal", "end_turn_walk"))
stack, bs, es = session.states_stripped, session.battle_state, session.event_state


class Miss(Exception):
    """A boot step past its bound (its CAPTURE line is printed)."""


def top(gc):
    s = stack(gc)
    return s[-1] if s else None


def holder(gc):
    e = es(gc)
    return [e.get("coopActiveSeat"), (e.get("coopEndTurnTally") or {}).get("activeSeat")]


def dialog(gc):
    d = gc.cmd({"cmd": "coop_dialog_info"})
    return d.get("code") if d.get("present") else None


def log_lines(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def log_count(gc, needle):
    return sum(1 for line in log_lines(gc) if needle in line)


def ptable(b):
    return {str(u["id"]): [u.get("coop"), u.get("faction"), u.get("isOut"), u.get("x"), u.get("y"), u.get("z")]
            for u in b.get("units", [])}


def hash_cell(host, client, what):
    try:
        return bool(session.assert_hash_clean(host, client, full=True, what=what)), "all buckets EQUAL"
    except AssertionError as e:
        return False, "hash MISMATCH: " + str(e)[:500]


def wait_until(pred, bound, interval=0.25):
    t = time.time()
    while time.time() - t < bound:
        if pred():
            return True, round(time.time() - t, 2)
        time.sleep(interval)
    return bool(pred()), round(time.time() - t, 2)


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


def guarded(tag, fn, machines):
    try:
        return fn()
    except Miss:
        raise
    except Exception as e:
        missed(tag, f"{type(e).__name__}: {str(e)[:600]}", machines)


def shut(*gcs):
    try:
        shutdown_clients(*gcs)
    except RuntimeError as e:
        print(f"[saved_battle] shutdown: {str(e)[:300]}", flush=True)


def report(row, order, cells, ev):
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    for name in order:
        print(f"{'PASS' if cells[name][0] else 'FAIL'} {name}: {cells[name][1]}", flush=True)
    fails = sum(1 for name in order if not cells[name][0])
    print(f"{row} {'PASS' if not fails else 'FAIL'} ({fails} of {len(order)} cells failed)", flush=True)
    return fails


def boot_failed(row, order, why, ev):
    return report(row, order, {c: (False, f"boot (see the CAPTURE {why} line)") for c in order}, ev)


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


def join(host, client, key):
    """The client's browser + join_tcp; profile_ok on both join popups (main #181's shape)."""
    SK.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": "ClientPlayer"})
    for gc in (host, client):
        gc.wait_for(f"{gc.name} join popup", lambda gc=gc: session.has_state(gc, "Profile"), timeout=60)
        gc.ok({"cmd": "profile_ok"})


def load_saved(host, client, save, tag):
    """The resume pair's boot: spawn both; the host loads `save` through the real load menu, no locked session."""
    def boot():
        host.spawn(), client.spawn(), host.connect(), client.connect()
        host.ok({"cmd": "load_save_menu", "file": save})
        host.wait_for("the loaded battle", lambda: bs(host).get("inBattle") and top(host) == "BattlescapeState",
                      timeout=LOAD_S, interval=0.3)
    guarded(tag, boot, (host, client))
    if host.cmd({"cmd": "get_coop"}).get("sessionLocked"):
        missed(tag, "the freshly loaded battle already holds a locked session", (host, client))


def continue_battle(host, client, ev, what):
    """CONTINUE BATTLE, then the arrival read 2 s after the client is in battle (this file's both_on_battle and
    the saved PvE2 test's arrival cell)."""
    t, c_at, h_at = time.time(), None, None
    host.ok({"cmd": "lobby_action"})
    while time.time() - t < CLIENT_S and (c_at is None or (h_at is None and time.time() - t < HOST_S)):
        h_at = h_at if h_at is not None or top(host) != "BattlescapeState" else round(time.time() - t, 2)
        c_at = c_at if c_at is not None or not bs(client).get("inBattle") else round(time.time() - t, 2)
        time.sleep(0.25)
    time.sleep(2)
    r = ev["arrival"] = {"clientInBattleS": c_at, "hostBattleS": h_at, "host": stack(host), "client": stack(client),
                         "hostDialog": dialog(host), "clientDialog": dialog(client), "refusal": log_count(host, N_REFUSE),
                         "hostPhase": es(host).get("phase")}
    ok = (c_at is not None and h_at is not None and h_at <= HOST_S and r["host"][-1] == "BattlescapeState"
          and r["hostDialog"] != DLG_WAIT_PLAYERS and r["client"][-1] == "BattlescapeState"
          and r["clientDialog"] != DLG_RESUME_HOLD and "LobbyMenu" not in r["client"] and "BriefingState" not in r["client"])
    return ok, (f"{'' if c_at is not None else what + ': '}client in battle at {c_at} s (bound {CLIENT_S}); host battle on "
                f"top at {h_at} s (bound {HOST_S}); host {r['host']} dialog {r['hostDialog']} (want no {DLG_WAIT_PLAYERS}); "
                f"client {r['client']} dialog {r['clientDialog']} (want BattlescapeState on top, no {DLG_RESUME_HOLD}, "
                f"LobbyMenu or BriefingState); host refusal lines {r['refusal']}, phase {r['hostPhase']}")


def coop_cell(host, ev, key, want, at):
    """open_pause_coop, pop the HostMenu it opened, read the PauseState's CO-OP TextButton `visible` (want `want`)."""
    host.ok({"cmd": "open_pause_coop"})
    opened = ev.setdefault(key, {})["opened"] = stack(host)
    if opened[-1] != "HostMenu":
        raise AssertionError(f"open_pause_coop left {opened} (want HostMenu on top)")
    lw = host.ok({"cmd": "pop_state"}) and host.cmd({"cmd": "list_widgets"})
    co = ev[key]["coop"] = [w for w in lw.get("widgets", []) if w.get("text") == "CO-OP"
                            and "TextButton" in str(w.get("type"))]
    if "PauseState" not in str(lw.get("state")) or len(co) != 1:
        raise AssertionError(f"list_widgets on {lw.get('state')}: CO-OP buttons {co} (want one on the PauseState)")
    vis = co[0].get("visible")
    return vis is want, (f"{'CO-OP shows while an action runs: ' if vis and not want else ''}CO-OP visible {vis} {at} "
                         f"(want {want})")


def pop_to_battle(host):
    pops = []
    while top(host) != "BattlescapeState" and len(pops) < 6:
        pops.append((top(host), host.cmd({"cmd": "pop_state"}).get("ok")))
    return pops


def order_walk(host):
    """WALK (its own level, then the one below; a refused line moves on to the next)."""
    units, tried = bs(host).get("units", []), []
    occupied = {(u["x"], u["y"], u["z"]) for u in units if not u.get("isOut")}
    for u in [u for u in units if u.get("faction") == 0 and not u.get("isOut") and (u.get("tu") or 0) >= TU_WALK]:
        for z, d in [(z, d) for z in (u["z"], u["z"] - 1) if z >= 0 for d in range(8)]:
            line = [(u["x"] + session.DIR_DX[d] * k, u["y"] + session.DIR_DY[d] * k, z)
                    for k in range(WALK_FAR, WALK_NEAR - 1, -1)]
            t = next((t for t in line if session.tile_walkable(host, t, occupied)), None)
            if t is None:
                continue
            r = host.cmd({"cmd": "battle_action", "action": "move", "unit": u["id"], "x": t[0], "y": t[1], "z": t[2]})
            if r.get("ok"):
                return {"unit": u["id"], "from": (u["x"], u["y"], u["z"]), "tu": u.get("tu"), "dest": t, "refused": tried}
            tried.append((u["id"], t, r.get("error")))
    return {"unit": None, "refused": tried}


def row_coop_button_gate():
    host = GameClient("host", 0, make_user_dir("coop_button_gate_host"))
    m, ev = (host,), {}

    def boot():
        host.spawn(), host.connect(), host.ok({"cmd": "open_new_battle"})
        host.wait_for("NewBattleState", lambda: session.has_state(host, "NewBattleState"), timeout=60)
        host.ok({"cmd": "set_seed", "seed": SEED}), host.ok({"cmd": "newbattle_ok"})
        host.wait_for("SP battle", lambda: (session.has_state(host, "BriefingState") or session.has_state(
            host, "InventoryState") or session.has_state(host, "BattlescapeState")), timeout=180, interval=0.5)
        if session.has_state(host, "BriefingState"):
            host.ok({"cmd": "close_briefing"})
        host.wait_for("equip screen", lambda: session.has_state(host, "InventoryState"), timeout=STEP_S, interval=0.3)
        session.dismiss_battle_start_overlays(host)
        ok, secs = wait_until(lambda: top(host) == "BattlescapeState" and bs(host).get("pendingStates") == 0
                              and bs(host).get("side") == 0, STEP_S)
        if not ok:
            missed("coop_button_gate",
                   f"settle: top BattlescapeState, pendingStates 0, side 0 not reached in {secs} s", m)

    def cell_coop_hidden(ev):
        ev["busyPops"] = pop_to_battle(host)
        ev["walk"] = order_walk(host)
        busy, ev["busyS"] = wait_until(lambda: (bs(host).get("pendingStates") or 0) > 0, BUSY_S, 0.05)
        ev["pendingAtCheck"] = bs(host).get("pendingStates")
        if ev["walk"]["unit"] is None or not busy:
            capture("coop_button_gate walk", f"WALK: no walk reached pendingStates > 0 ({ev['walk']}) (FIXTURE)", m)
            raise AssertionError("WALK: no walk reached pendingStates > 0 (FIXTURE; see the CAPTURE coop_button_gate "
                                 "walk line)")
        return coop_cell(host, ev, "busyCheck", False, f"with pendingStates {ev['pendingAtCheck']} at the check")

    try:
        try:
            guarded("coop_button_gate", boot, m)
        except Miss:
            return boot_failed("coop_button_gate", GATE_CELLS, "coop_button_gate", {"boot": "miss"})
        ev["settled"] = {"stack": stack(host), "mapFingerprint": bs(host).get("mapFingerprint")}
        cells = run_cells(GATE_CELLS,
                          {"coop_shown_at_rest": (False, lambda ev: coop_cell(host, ev, "restCheck", True, "at rest")),
                           "coop_hidden_while_busy": (True, cell_coop_hidden)}, ev)
        ev["endPops"] = pop_to_battle(host)
        return report("coop_button_gate", GATE_CELLS, cells, ev)
    finally:
        shut(host)


def seed_pair():
    """The saved_coop_continue seed pair; returns (save path, seed record) or raises Miss after ONE CAPTURE line."""
    host_dir = make_user_dir("saved_continue_seed_host", options={"CoopTurnMode": "traditional"})
    host, client = GameClient("host", 0, host_dir), GameClient("client", 0, make_user_dir("saved_continue_seed_client"))
    m, seated = (host, client), {}

    def boot():
        host.spawn(), client.spawn(), host.connect(), client.connect()
        SK.skirmish_host(host, KEY), join(host, client, KEY)
        host.wait_for("BATTLE SETTINGS", lambda: host.cmd({"cmd": "lobby_state"}).get("buttonVisible"), timeout=STEP_S)
        session.drive_to_battlescape(host, client, seated, seat_count=SEATED,
                                     pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED}))
        session.wait_host_idle(host, client, timeout=STEP_S)
        session.assert_hash_clean(host, client, full=True, what="saved_coop_continue seed")

    try:
        guarded("saved_coop_continue seed", boot, m)
        hb, cb = bs(host), bs(client)
        units = hb.get("units", [])
        rec = {"P": ptable(hb), "seat1": sorted(u["id"] for u in units if u.get("coop") == 1),
               "fp": hb.get("mapFingerprint"), "seat0": sorted(u["id"] for u in units if u.get("coop") == 0),
               "seedActiveSeat": es(host).get("coopActiveSeat"),
               "sideTurn": [[b.get("side"), b.get("turn")] for b in (hb, cb)], "seated": seated.get("soldierIds")}
        alien = any(u.get("faction") == 1 and not u.get("isOut") for u in units)
        if rec["sideTurn"] != [[0, 1], [0, 1]] or len(rec["seat1"]) != SEATED or not alien or rec["P"] != ptable(cb):
            missed("saved_coop_continue seed",
                   f"seed precondition: {json.dumps(rec, default=str)}; alien alive {alien}; P equal on both "
                               f"{rec['P'] == ptable(cb)} (want side 0 turn 1 on both, {SEATED} seat-1 units, an alien)", m)
        guarded("saved_coop_continue seed", lambda: host.ok({"cmd": "save_game", "file": SAVE}), m)
        path = os.path.join(host_dir, "xcom1", SAVE)
        if not wait_until(lambda: os.path.exists(path), 10, 0.2)[0]:
            missed("saved_coop_continue seed", f"save_game wrote no {path} in 10 s", m)
        return path, rec
    finally:
        shut(host, client)


def cell_end_turn_walk(host, client, ev):
    s1 = [u.get("soldierId") for u in bs(host).get("units", []) if u.get("coop") == 1 and not u.get("isOut")]
    host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    ok, secs = wait_until(lambda: holder(host)[0] == 1 and holder(client)[0] == 1, STEP_S, 0.2)
    if not ok:
        return False, f"holder host/client {[holder(host), holder(client)]} {secs} s after END TURN (want 1 on both)"
    after, tile, run_dir = session.stage_open_ground_actor(host, client, s1, tag="end-turn-walk")
    dest, prev = (tile[0] + session.DIR_DX[run_dir], tile[1] + session.DIR_DY[run_dir], tile[2]), session.walk_action_id(
        host)
    ev["endTurnWalk"] = {"unit": after["id"], "tile": tile, "dir": run_dir, "dest": dest,
                    "resp": session.send_walk(client, after["id"], dest)}
    session.wait_walk_settled(host, client, prev, timeout=STEP_S), session.wait_host_idle(host, client, timeout=STEP_S)
    p = [(lambda u: (u["x"], u["y"], u["z"]))(session.unit_of(gc, after["id"])) for gc in (host, client)]
    hok, hdetail = hash_cell(host, client, "saved_coop_continue end_turn_walk")
    ds = [es(host).get("desyncSeen"), es(client).get("desyncSeen")]
    return (p[0] == p[1] == dest and hok and ds == [False, False],
            f"holder 1 on both after END TURN ({secs} s); unit {after['id']} host/client {p} (want {dest} on both); "
            f"{hdetail}; desyncSeen {ds} (want False/False)")


def row_saved_coop_continue():
    try:
        save, seed = seed_pair()
    except Miss:
        return boot_failed("saved_coop_continue", CONTINUE_CELLS, "saved_coop_continue seed",
                           {"boot": "seed pair miss"})
    host = GameClient("host", 0,
                      make_user_dir("saved_continue_resume_host", saves=[save], options={"CoopTurnMode": "parallel"}))
    client = GameClient("client", 0, make_user_dir("saved_continue_resume_client"))
    ev = {"seed": seed}

    def cell_host_menu(ev):
        host.ok({"cmd": "open_pause_coop"})
        host.wait_for("HostMenu", lambda: session.has_state(host, "HostMenu"), timeout=STEP_S)
        st, pend = ev["hostMenu"] = stack(host), host.cmd({"cmd": "get_coop"}).get("customBattleResumePending")
        return (st[-1] == "HostMenu" and "ServerList" not in st and pend is True,
                f"host stack {st} (want HostMenu on top, no ServerList); customBattleResumePending {pend} (want True)")

    def cell_lobby_offer(ev):
        host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "SavedBattle", "port": KEY, "player": "HostPlayer"})
        host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"), timeout=STEP_S)
        ls = (join(host, client, KEY), time.sleep(2), host.cmd({"cmd": "lobby_state"}))[2]
        r = ev["lobbyOffer"] = {"host": stack(host), "client": stack(client),
                                "clientInBattle": bs(client).get("inBattle"),
                                "button": [ls.get("buttonVisible"), ls.get("buttonText")]}
        return ("LobbyMenu" in r["host"] and "LobbyMenu" in r["client"] and not r["clientInBattle"] and r["button"] == [
            True, "CONTINUE BATTLE"], f"stacks host {r['host']} client {r['client']} (want LobbyMenu on both); client "
                f"inBattle {r['clientInBattle']} (want False); host button {r['button']} (want visible CONTINUE BATTLE)")

    def cell_session_active(ev):
        eh, ec = es(host), es(client)
        r = ev["sessionState"] = {"phase": [eh.get("phase"), ec.get("phase")],
                                  "desync": [eh.get("desyncSeen"), ec.get("desyncSeen")],
                                  "coopSession": client.cmd({"cmd": "get_coop"}).get("coopSession"),
                                  "diskResume": log_count(host, N_DISK_RESUME),
                                  "continueLine": log_count(host, N_CONTINUE)}
        return (r["phase"] == ["Active", "Active"] and r["desync"] == [False, False] and r["coopSession"] is True
                and r["diskResume"] == 1 and r["continueLine"] == 1,
                f"phase {r['phase']} (want Active on both); desyncSeen {r['desync']} (want False/False); client coopSession "
                f"{r['coopSession']} (want True); host log '{N_DISK_RESUME}' {r['diskResume']}, '{N_CONTINUE}' "
                f"{r['continueLine']} (want 1, 1)")

    def cell_units_equal(ev):
        ph, pc, p = ptable(bs(host)), ptable(bs(client)), seed["P"]
        s1, s0 = sum(1 for v in ph.values() if v[0] == 1), sum(1 for v in ph.values() if v[0] == 0)
        diff = ev["unitDiff"] = {k: [ph.get(k), pc.get(k), p.get(k)] for k in set(ph) | set(pc) | set(p)
                                 if not ph.get(k) == pc.get(k) == p.get(k)}
        return (not diff and s1 == len(seed["seat1"]) and s0 == len(seed["seat0"]),
                f"units differing host/client/P {diff} (want none); seat-1 / seat-0 {s1} / {s0} (want "
                f"{len(seed['seat1'])} / {len(seed['seat0'])})")

    def cell_turn_mode(ev):
        eh, ec, a0 = es(host), es(client), seed["seedActiveSeat"]
        r = ev["mode"] = {"turnMode": [eh.get("turnMode"), ec.get("turnMode")], "option": eh.get("optionTurnMode"),
                          "holder": [holder(host), holder(client)]}
        return (r["turnMode"] == ["traditional"] * 2 and r["option"] == "parallel" and r["holder"] == [[a0, a0]] * 2,
                f"turnMode {r['turnMode']} (want traditional on both) with the host option {r['option']} (want parallel); "
                f"holder [coopActiveSeat, tally.activeSeat] host/client {r['holder']} (want {a0} on both)")

    try:
        try:
            load_saved(host, client, SAVE, "saved_coop_continue resume")
        except Miss:
            return boot_failed("saved_coop_continue", CONTINUE_CELLS, "saved_coop_continue resume", ev)
        steps = {"host_menu_pending": (True, cell_host_menu), "lobby_offer": (True, cell_lobby_offer),
                 "both_on_battle": (True, lambda ev: continue_battle(host, client, ev,
                                                                     "the client never got the saved battle")),
                 "session_active": (False, cell_session_active), "units_equal": (False, cell_units_equal),
                 "turn_mode_kept": (False, cell_turn_mode),
                 "hash_equal": (False, lambda ev: hash_cell(host, client, "saved_coop_continue hash_equal")),
                 "end_turn_walk": (False, lambda ev: cell_end_turn_walk(host, client, ev))}
        return report("saved_coop_continue", CONTINUE_CELLS, run_cells(CONTINUE_CELLS, steps, ev), ev)
    finally:
        shut(host, client)


def main():
    t0 = time.time()
    fails = row_coop_button_gate() + row_saved_coop_continue()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_skirmish_saved_battle_join: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
