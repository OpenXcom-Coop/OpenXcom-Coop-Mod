"""D246-U S-D2a rows P3 (gm3, the host plays the aliens) and P2 (gm2, the partner plays the aliens): a PvP co-op Custom
Battle the REWRITE saved mid-battle continues for both players through MG-B's route (load, CO-OP in the pause menu, host,
a clean partner joins, CONTINUE BATTLE): both machines are back on the same battle in the saved mode, every unit where it
was and on the seat it had, the battle state equal, and the side to move hands the turn over with END TURN (owner D225 (a);
MG-B Q6 (a), whose PvP rows this file writes; orchestrator ruling R-D246D2-1: a proof stage, no product change).

Spec: docs repo rewrite/prompts/d246u_sd2a_pvp_cb_resume_proof.md (this stage, section (f)); the common file
d246u_sd2_pvp_custom_battle_convert.md (rulings, R3, QD246D2-2 / -3 (a)). Constants: rewrite/d246u-task0/sd2a/CONSTANTS.md
(TASK 0 boots a = P3, b = P2 at 796ca70ed). Lobby key 49253.

Each row is a seed pair (dirs d246sd2a_<row>_seed_host / _client): the host's set_seed SEED_ROSTER; the PvP lobby (P3: the
HOST on the Alien team, gamemode 3; P2: the partner, gamemode 2); the W2-P8b battle-entry spine (STR_SMALL_SCOUT, map
seed 1); pin_ai_neutral; the host idle. Precondition: both in battle in the row's mode, side 0 turn 1, every bucket EQUAL,
a live soldier and a live alien, equal map fingerprints. The record P (per unit id: coop, faction, isOut, x, y, z); the
host saves (the battle block carries coopTurnMode and coopItemIdCtr: a REWRITE save). Then a resume pair (dirs
d246sd2a_<row>_res_host / _client): a fresh host with the save (default options) loads it from the menu; open_pause_coop
(HostMenu, customBattleResumePending); host_menu_host; a clean partner joins; CONTINUE BATTLE; the partner in battle. The
cells read SETTLE_S later:
  <row>-arrive  no CoopState 62 / 68 on either stack, both tops BattlescapeState, no LobbyMenu / BriefingState on the
                partner, phase Active and desyncSeen false on both, the host's MG-B offer line once
  <row>-mode    get_coop.gamemode and battle_state.coopGamemode the row's mode on both; turnMode == the saved coopTurnMode
  <row>-seats   per unit host == partner == P; live aliens (faction 1) and X-COM (faction 0) on the mode's seats (P3: aliens
                seat 0, X-COM seat 1; P2: X-COM seat 0, aliens seat 1), civilians -1
  <row>-side    (side, turn) == the seed's on both
  <row>-turn    the side to move (P3: the partner; P2: the host) presses END TURN: side 1 of the saved turn on both; since
                the press one side_transition and one side_begin on the host, the partner's seqs equal; both in battle
  <row>-common  every bucket EQUAL right before the press, desyncSeen false on both after it, no new lane crash file

One EVIDENCE line per row, one PASS/FAIL line per cell, the row verdict; every row runs after a failure. A cell that raises
ends its row (later cells FAIL "not reached (<cell>)"). A boot step past its bound prints ONE CAPTURE <row> line and fails
every cell of that row "boot". WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the result, no
skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_skirmish_saved_pvp_continue.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import repro_pvp_side_relative as PSR  # noqa: E402
import test_skirmish_flow as SK  # noqa: E402
from repro_atom_side_begin import drive_side_change  # noqa: E402
from test_w2_host_combat import evs_since  # noqa: E402
from test_w2_battle_end_rules import wait_until  # noqa: E402
from test_r5_pvp_gm3 import (Miss, stack, top, log_count, bview, hash_now, capture, guarded, common,  # noqa: E402
                             verdict, shut)

KEY = "49253"
SEED_ROSTER = 1                   # set_seed on the host before its lobby (test_r5_pvp_gm3 :52; TASK 0 boots a, b)
LOAD_S, CLIENT_S = 120, 120       # the menu load / the partner in battle after CONTINUE BATTLE (TASK 0: 0.1 s / 0.95 s)
STEP_S, SETTLE_S = 30, 2          # each lever / side change (TASK 0: <= 3.7 s); the read delay after the arrival
N_MGB = "[coop] MG-B: CONTINUE BATTLE offers the loaded Custom Battle"
FACTION_PLAYER, FACTION_HOSTILE, FACTION_NEUTRAL = 0, 1, 2
SIDE_ALIENS = 1                   # the side END TURN hands to (side 0 = X-COM moves first in both modes)
KINDS = ("side_transition", "side_begin")
# row: (the lobby's alien_player, gamemode, END TURN presser, save file, the aliens' seat, X-COM's seat)
ROWS = {"P3": ("host", 3, "client", "d246sd2a_gm3.sav", 0, 1),
        "P2": ("client", 2, "host", "d246sd2a_gm2.sav", 1, 0)}
CELLS = ("arrive", "mode", "seats", "side", "turn", "common")


def ptable(gc):
    return {str(u["id"]): [u.get("coop"), u.get("faction"), u.get("isOut"), u.get("x"), u.get("y"), u.get("z")]
            for u in battle_state(gc).get("units", [])}


def coop(gc, key):
    return gc.cmd({"cmd": "get_coop"}).get(key)


def picks(gc, cmd, keys):
    r = gc.cmd({"cmd": cmd})
    return {k: r.get(k) for k in keys}


def side_turn(gc):
    b = battle_state(gc)
    return [b.get("side"), b.get("turn")]


def saved_keys(path):
    """The save's coop battle keys {key: [values]} (a REWRITE save carries coopTurnMode and coopItemIdCtr, F19850)."""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = [ln.strip() for ln in f]
    return {k: [ln.split(":", 1)[1].strip() for ln in lines if ln.startswith(k + ":")]
            for k in ("coopTurnMode", "coopItemIdCtr", "coop_gamemode")}


def missed(row, err, machines):
    capture(row, err, machines)
    raise Miss(row)


def seed_pair(row, ev):
    """The row's seed pair: the PvP bring-up, its precondition, the record P, the host's save. Returns (save path, seed)."""
    alien, gm, _presser, save, _sa, _sx = ROWS[row]
    host = GameClient("host", None, make_user_dir(f"d246sd2a_{row.lower()}_seed_host"))
    client = GameClient("client", None, make_user_dir(f"d246sd2a_{row.lower()}_seed_client"))
    m, s = (host, client), {}
    ev["seed"] = s
    try:
        guarded(row, lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
        guarded(row, lambda: host.ok({"cmd": "set_seed", "seed": SEED_ROSTER}), m)
        s["lobbyGamemode"] = guarded(row, lambda: PF.start_pvp_skirmish_lobby(host, client, KEY, alien_player=alien), m)[0]
        guarded(row, lambda: PSR.drive_to_gm2_battlescape(host, client), m)
        s["pinned"] = guarded(row, lambda: session.pin_ai_neutral(host, client, tag="d246sd2a"), m)   # 0 is legal
        guarded(row, lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
        hb, cb, pc = guarded(row, lambda: (bview(host), bview(client), ptable(client)), m)
        s.update(P=guarded(row, lambda: ptable(host), m), sideTurn=[[b.get("side"), b.get("turn")] for b in (hb, cb)],
                 gamemode=[b.get("coopGamemode") for b in (hb, cb)], fp=[b.get("mapFingerprint") for b in (hb, cb)])
        s.update(guarded(row, lambda: {
            "hash": hash_now(host, client),
            "turnMode": [picks(g, "event_state", ("turnMode", "coopActiveSeat")) for g in m],
            "hostCoop": picks(host, "get_coop", ("gamemode", "lobbyMode", "localSeat", "pvpBorrow")),
            "hostLobby": picks(host, "lobby_state", ("lobbyOpen", "lobbyMode", "playerTeams"))}, m))
        live = {f: sorted(int(i) for i, v in s["P"].items() if v[1] == f and not v[2])
                for f in (FACTION_PLAYER, FACTION_HOSTILE)}
        s["live"] = live
        if not (hb.get("inBattle") and cb.get("inBattle") and s["gamemode"] == [gm, gm] and s["sideTurn"] == [[0, 1], [0, 1]]
                and s["hash"] == "all buckets EQUAL" and s["P"] == pc and live[FACTION_PLAYER] and live[FACTION_HOSTILE]
                and s["fp"][0] == s["fp"][1]):
            missed(row, f"seed precondition: {s} (want both in battle, gamemode {gm} on both, side 0 turn 1, every bucket "
                        f"EQUAL, P equal on both, a live soldier and a live alien, equal map fingerprints)", m)
        guarded(row, lambda: host.ok({"cmd": "save_game", "file": save}), m)
        path = os.path.join(host.user_dir, "xcom1", save)
        ok, s["saveS"] = wait_until(lambda: os.path.exists(path), 10, 0.2)
        time.sleep(1.0)   # the write completes after the file appears
        s["saved"] = saved_keys(path) if ok else None
        if not ok or not s["saved"]["coopTurnMode"] or not s["saved"]["coopItemIdCtr"]:
            missed(row, f"save_game: {path} written {ok}, keys {s['saved']} (want coopTurnMode and coopItemIdCtr)", m)
        return path, s
    finally:
        shut(host)     # the host first (F18815)
        shut(client)


def resume_boot(row, host, client, r):
    """The resume pair's boot: the menu load, CO-OP, START HOST, the join, CONTINUE BATTLE, the partner in battle."""
    m, save = (host, client), ROWS[row][3]
    guarded(row, lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    guarded(row, lambda: host.ok({"cmd": "load_save_menu", "file": save}), m)
    ok, r["loadS"] = wait_until(lambda: battle_state(host).get("inBattle") and top(host) == "BattlescapeState", LOAD_S, 0.25)
    r["locked"] = guarded(row, lambda: coop(host, "sessionLocked"), m)
    if not ok or r["locked"]:
        missed(row, f"the loaded battle on top {ok} in {r['loadS']} s (bound {LOAD_S}); sessionLocked {r['locked']} "
                    f"(want False)", m)
    guarded(row, lambda: host.ok({"cmd": "open_pause_coop"}), m)
    ok, r["hostMenuS"] = wait_until(lambda: session.has_state(host, "HostMenu"), STEP_S, 0.25)
    r["pause"] = guarded(row, lambda: [stack(host), coop(host, "customBattleResumePending")], m)
    if not ok or "ServerList" in r["pause"][0] or r["pause"][1] is not True:
        missed(row, f"open_pause_coop: host stack {r['pause'][0]} (want HostMenu, no ServerList), "
                    f"customBattleResumePending {r['pause'][1]} (want True)", m)
    guarded(row, lambda: host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "SavedBattle", "port": KEY,
                                  "player": "HostPlayer"}), m)
    if not wait_until(lambda: session.has_state(host, "LobbyMenu"), STEP_S, 0.25)[0]:
        missed(row, f"host_menu_host: no host LobbyMenu in {STEP_S} s", m)

    def join():
        SK.skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
        for gc in m:
            gc.wait_for(f"{gc.name} join popup", lambda gc=gc: session.has_state(gc, "Profile"), timeout=STEP_S)
            gc.ok({"cmd": "profile_ok"})
    guarded(row, join, m)
    time.sleep(SETTLE_S)
    ls = guarded(row, lambda: [g.cmd({"cmd": "lobby_state"}) for g in m], m)
    r["lobby"] = {"button": [ls[0].get("buttonVisible"), ls[0].get("buttonText")],
                  "playerTeams": [x.get("playerTeams") for x in ls], "players": ls[0].get("players"),
                  "gamemode": guarded(row, lambda: [coop(g, "gamemode") for g in m], m),
                  "clientInBattle": guarded(row, lambda: battle_state(client).get("inBattle"), m)}
    if r["lobby"]["clientInBattle"] or r["lobby"]["button"] != [True, "CONTINUE BATTLE"]:
        missed(row, f"the resume lobby: {r['lobby']} (want the host's visible CONTINUE BATTLE, the partner not in "
                    f"battle)", m)
    guarded(row, lambda: host.ok({"cmd": "lobby_action"}), m)
    ok, r["clientInBattleS"] = wait_until(lambda: battle_state(client).get("inBattle"), CLIENT_S, 0.25)
    if not ok:
        missed(row, f"CONTINUE BATTLE: the partner not in battle in {CLIENT_S} s", m)
    time.sleep(SETTLE_S)


def resume_row(row, save, seed, crash0, ev):
    _alien, gm, presser, _save, seat_a, seat_x = ROWS[row]
    host = GameClient("host", None, make_user_dir(f"d246sd2a_{row.lower()}_res_host", saves=(save,)))
    client = GameClient("client", None, make_user_dir(f"d246sd2a_{row.lower()}_res_client"))
    m, r, order = (host, client), {}, [f"{row}-{n}" for n in CELLS]
    ev["resume"] = r

    def arrive():
        st = [stack(g) for g in m]
        dl = [[g.cmd({"cmd": "coop_dialog_count", "code": c}).get("count") for c in (62, 68)] for g in m]
        ph = [[event_state(g).get(k) for k in ("phase", "desyncSeen")] for g in m]
        mgb = log_count(host, N_MGB)
        r["arrive"] = {"stacks": st, "dialogs62_68": dl, "phaseDesync": ph, "mgb": mgb}
        return (dl == [[0, 0], [0, 0]] and st[0][-1:] == st[1][-1:] == ["BattlescapeState"] and "LobbyMenu" not in st[1]
                and "BriefingState" not in st[1] and ph == [["Active", False]] * 2 and mgb == 1,
                f"CoopState 62 / 68 counts host/partner {dl} (want 0 / 0 on both); stacks host {st[0]} partner {st[1]} "
                f"(want BattlescapeState on top, no LobbyMenu / BriefingState on the partner); phase, desyncSeen "
                f"host/partner {ph} (want Active, False on both); host '{N_MGB}' lines {mgb} (want 1)")

    def mode():
        saved = (seed["saved"]["coopTurnMode"] or [None])[0]
        g, b = [coop(x, "gamemode") for x in m], [battle_state(x).get("coopGamemode") for x in m]
        tm = [event_state(x).get("turnMode") for x in m]
        r["mode"] = {"gamemode": g, "coopGamemode": b, "turnMode": tm, "saved": saved,
                     "option": event_state(host).get("optionTurnMode")}
        return (g == b == [gm, gm] and tm == [saved, saved],
                f"get_coop.gamemode host/partner {g}, coopGamemode {b} (want {gm} on both); turnMode {tm} (want the "
                f"saved coopTurnMode {saved!r} on both; host option {r['mode']['option']!r})")

    def seats():
        ph, pc, p = ptable(host), ptable(client), seed["P"]
        diff = {k: [ph.get(k), pc.get(k), p.get(k)] for k in sorted(set(ph) | set(pc) | set(p))
                if not ph.get(k) == pc.get(k) == p.get(k)}
        want = {FACTION_HOSTILE: seat_a, FACTION_PLAYER: seat_x, FACTION_NEUTRAL: -1}
        off = {g.name: {k: v[:2] for k, v in t.items() if not v[2] and v[1] in want and v[0] != want[v[1]]}
               for g, t in ((host, ph), (client, pc))}
        census = {f: sorted(int(k) for k, v in ph.items() if v[1] == f and not v[2]) for f in want}
        r["seats"] = {"census": census, "units": len(ph)}
        return (not diff and not off["host"] and not off["client"] and bool(census[FACTION_PLAYER])
                and bool(census[FACTION_HOSTILE]),
                f"units (coop, faction, isOut, x, y, z) differing host/partner/P {diff} (want none, {len(ph)} units); live "
                f"units off their seat {off} (want none: aliens seat {seat_a}, X-COM seat {seat_x}, civilians -1); live "
                f"by faction {census} (want soldiers and aliens)")

    def side():
        st = [side_turn(g) for g in m]
        return st == seed["sideTurn"], f"(side, turn) host/partner {st} (want the seed's {seed['sideTurn']})"

    def turn():
        r["hashBefore"] = hash_now(host, client)   # the common cell's hash, right before the press
        seq0 = event_state(host).get("lastSeqEmitted") or 0
        gc = host if presser == "host" else client
        r["press"] = gc.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        try:
            drive_side_change(host, client, SIDE_ALIENS, timeout=STEP_S)
            session.wait_host_idle(host, client, timeout=STEP_S)
        except Exception as e:
            r["sideError"] = f"{type(e).__name__}: {str(e)[:300]}"
        hev, cev = evs_since(host, seq0), evs_since(client, seq0)
        hk = {k: [e["seq"] for e in hev if e["kind"] == k] for k in KINDS}
        ck = {k: [e["seq"] for e in cev if e["kind"] == k] for k in KINDS}
        st, ib = [side_turn(g) for g in m], [battle_state(g).get("inBattle") for g in m]
        want = [SIDE_ALIENS, seed["sideTurn"][0][1]]
        r["turn"] = {"seq0": seq0, "hostEvs": [(e["seq"], e["kind"]) for e in hev], "views": [bview(g) for g in m]}
        return (r["press"].get("ok") is True and "sideError" not in r and st == [want, want] and ib == [True, True]
                and len(hk["side_transition"]) == 1 and len(hk["side_begin"]) == 1 and ck == hk,
                f"{presser} END TURN {r['press']}; {r.get('sideError') or 'side change reached'}; (side, turn) "
                f"host/partner {st} (want {want} on both); inBattle {ib} (want True on both); since seq {seq0} host "
                f"{hk} (want one each), partner {ck} (want the same)")

    steps = {"arrive": arrive, "mode": mode, "seats": seats, "side": side, "turn": turn,
             "common": lambda: common(host, client, crash0, r.get("hashBefore"))}
    try:
        try:
            resume_boot(row, host, client, r)
        except Miss:
            return verdict(row, order, {c: (False, f"boot (see the CAPTURE {row} line)") for c in order}, ev)
        cells, stop = {}, None
        for name in CELLS:
            cell = f"{row}-{name}"
            try:
                cells[cell] = (False, f"not reached ({stop})") if stop else steps[name]()
            except Exception as e:
                cells[cell], stop = (False, f"raised {type(e).__name__}: {str(e)[:400]}"), cell
        return verdict(row, order, cells, ev)
    finally:
        shut(host)
        shut(client)


def run(row):
    crash0, ev, order = session._crash_log_snapshot(), {}, [f"{row}-{n}" for n in CELLS]
    try:
        save, seed = seed_pair(row, ev)
    except Miss:
        return verdict(row, order, {c: (False, f"boot (see the CAPTURE {row} line)") for c in order}, ev)
    except Exception as e:   # a step outside every guarded call (a user dir, a client object)
        capture(row, f"{type(e).__name__}: {str(e)[:600]}", ())
        return verdict(row, order, {c: (False, f"boot (see the CAPTURE {row} line)") for c in order}, ev)
    return resume_row(row, save, seed, crash0, ev)


def main():
    t0 = time.time()
    fails = run("P3")
    fails += run("P2")
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_skirmish_saved_pvp_continue: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
