"""PvP gm3, where the host plays the aliens (gm2 with the sides inverted): started and asserted end to end on two boots.
The module's helpers (bring_up, guarded, common, run_row, ending, ...) are shared by many PvP and seat tests.

Boot gm3_boot (key 48674): the host sets SEED_ROSTER, the lobby puts the HOST on the Alien team (gamemode 3), then the
battle-entry steps (repro_pvp_side_relative.drive_to_gm2_battlescape: STR_SMALL_SCOUT, map seed 1). The host owns no
soldier, so only the partner's pre-battle screen is pressed.
  gm3_census  coopGamemode 3 and MAP_FP on both; host authority (seat 0, hostSim), partner (seat 1, not); the host's
      seat (coop 0) holds the aliens (hostile), the partner's (coop 1) the X-COM soldiers (player); both machines
      agree per unit; the host logged battle_ready saveBlob EQUAL once; side 0, turn 1.
  partner_walk  the partner orders its X-COM soldier S on its own side (battle_intent walk); the host runs it.
  turn_to_aliens  the partner's END TURN hands the turn to the aliens: side 1 with one side_transition and one
      side_begin.
  host_ui_walk  the host orders its alien A through its own UI: one TAB, tab_select, one self-verified click.
  host_wins  the host kills every X-COM soldier on its own side and presses END TURN: soldiersDown, the host's seat
      wins, both machines end on the host's debriefing, the partner's display-only.
Boot aliens_down_boot (key 48676): the same bring-up; gm3_census's mode and seat cells re-checked (a failure fails
partner_wins "boot"); then the host kills the alien on X-COM's side and the partner presses END TURN:
  partner_wins  aliensDown, the partner's seat wins; both machines end on the host's debriefing.
Staging: every live unit's reactions 0 on both machines (client first), A on A_TILE, S on S_TILE.
Common cell after each row: every hash bucket EQUAL (on an ending row, right before the kill: there is no battle to hash
after it), desyncSeen false on both, no new file in this harness slot's crash folder.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure. A boot
step past its bound prints ONE CAPTURE line and fails the boot's rows "boot"; a staging step past its bound fails the
rows that need it (partner_walk, host_ui_walk) "staging". ONE run is the result, no skip path; exit 0 only when every
cell passes, else 2.

Run:  python tools/coop_test/test_pvp_gm3.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, assert_hash_clean  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import repro_pvp_side_relative as PSR  # noqa: E402
from repro_atom_side_begin import drive_side_change  # noqa: E402
from test_delta_core import both  # noqa: E402
from test_seat_pacing import tab_select, real_click_walk, SDLK_TAB  # noqa: E402
from test_battle_end_rules import host_chain_done, host_next_turn_up, wait_until  # noqa: E402
from test_client_shoot import new_contexts  # noqa: E402
from test_host_combat import evs_since  # noqa: E402

GM3_KEY, ALIENS_DOWN_KEY = "48674", "48676"
SEED_ROSTER = 1                   # set_seed on the host before its lobby (the roster pin, test_client_pvp :470)
GAMEMODE_GM3 = 3
MAP_FP = -4.48310638993e+18       # both machines' mapFingerprint (STR_SMALL_SCOUT, map seed 1; equal on every boot)
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
ALIEN_IDS = [1000000]             # gm3: the host's seat (coop 0), FACTION_HOSTILE
XCOM_IDS = [8, 9, 10, 11, 12, 13, 14]   # gm3: the partner's seat (coop 1), FACTION_PLAYER
A_ID, A_TILE, A_DIR, A_DEST = 1000000, (17, 8, 0), 0, (17, 7, 0)   # the alien, a one-tile walk north
S_ID, S_TILE, S_DIR, S_DEST = 8, (2, 34, 0), 2, (3, 34, 0)         # min(XCOM_IDS), open ground 26 tiles from A
STEP_S = 30                       # each order / side change / ending step's bound (measured: <= 6.3 s)
N_EQUAL = "[coop-handshake] battle_ready saveBlob EQUAL"
N_MISMATCH = "[coop-handshake] battle_ready saveBlob MISMATCH"
# EVIDENCE only (the host, which owns no soldier, logs it once)
N_NOTHING = "[coop-equip] nothing to equip on this machine"
# the host's battleEnd record, as measured for host_wins and partner_wins; the partner's must carry the same fields
EXPECT = {
    "host_wins": {"reason": "soldiersDown", "aborted": False, "inExitArea": 0, "verdicts": [(0, "win"), (1, "lose")],
                  "tally": {"liveAliens": 1, "liveSoldiers": 0, "inExit": 0}},
    "partner_wins": {"reason": "aliensDown", "aborted": False, "inExitArea": 7, "verdicts": [(0, "lose"), (1, "win")],
                     "tally": {"liveAliens": 0, "liveSoldiers": 7, "inExit": 0}},
}
GM3_ROWS = (("gm3_census", ("gm3_census-mode", "gm3_census-auth", "gm3_census-seats", "gm3_census-equal",
                            "gm3_census-ready", "gm3_census-turn", "gm3_census-common")),
            ("partner_walk", ("partner_walk-ctx", "partner_walk-pos", "partner_walk-sent", "partner_walk-side",
                              "partner_walk-common")),
            ("turn_to_aliens", ("turn_to_aliens-side", "turn_to_aliens-once", "turn_to_aliens-common")),
            ("host_ui_walk", ("host_ui_walk-sel", "host_ui_walk-ctx", "host_ui_walk-pos", "host_ui_walk-common")),
            ("host_wins", ("host_wins-kill", "host_wins-host", "host_wins-client", "host_wins-ends",
                           "host_wins-common")))
ALIENS_DOWN_ROWS = (("partner_wins", ("partner_wins-kill", "partner_wins-host", "partner_wins-client",
                                      "partner_wins-ends", "partner_wins-common")),)


class Miss(Exception):
    """A boot, staging or rejoin step past its bound (its CAPTURE line is already printed)."""


def stack(gc):
    return session.states_stripped(gc)


def top(gc):
    st = stack(gc)
    return st[-1] if st else None


def log_lines(gc):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), encoding="utf-8", errors="replace") as f:
            return [line.rstrip("\n") for line in f]
    except OSError:
        return []


def log_count(gc, needle):
    return sum(1 for line in log_lines(gc) if needle in line)


def bview(gc):
    b = battle_state(gc)
    return {k: b.get(k) for k in ("phase", "inBattle", "side", "turn", "authority", "coopGamemode", "selectedId",
                                  "coopWaitText", "coopEndTurnText", "mapFingerprint")}


def units(gc):
    return {u["id"]: u for u in battle_state(gc).get("units", [])}


def pos(gc, uid):
    u = units(gc).get(uid) or {}
    return (u.get("x"), u.get("y"), u.get("z"))


def es(gc, key):
    return event_state(gc).get(key)


def capture(tag, err, machines):
    """ONE CAPTURE line: each machine's stack, battle_state view, coop_dialog_info, event_state.equip, last 40 log lines."""
    cap = {}
    for gc in machines:
        d = {}
        for k, fn in (("stack", stack), ("battle", bview), ("dialog", lambda g: g.cmd({"cmd": "coop_dialog_info"})),
                      ("equip", lambda g: es(g, "equip")), ("logTail", lambda g: log_lines(g)[-40:])):
            try:
                d[k] = fn(gc)
            except Exception as e:
                d[k] = f"probe failed: {type(e).__name__}: {e}"
        cap[gc.name] = d
    print(f"CAPTURE {tag}: missed {err}; {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def guarded(tag, fn, machines):
    try:
        return fn()
    except Exception as e:
        capture(tag, f"{type(e).__name__}: {str(e)[:600]}", machines)
        raise Miss(tag)


def tele_both(host, other, uid, t, d):
    return both(host, other, {"cmd": "battle_teleport_unit", "unit": uid, "x": t[0], "y": t[1], "z": t[2], "dir": d},
                ("to", "dir"))


def reactions_zero(host, other):
    """Every live unit's reactions 0 on both machines (client first); returns {id: (host, other)}."""
    live = sorted(i for i, u in units(host).items() if not u.get("isOut"))
    for uid in live:
        both(host, other, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions", "value": 0},
             ("tu",))
    uh, uo = units(host), units(other)
    got = {uid: (uh[uid].get("reactions"), uo[uid].get("reactions")) for uid in live}
    assert all(v == (0, 0) for v in got.values()), f"reactions host/other {got} (want 0 on both)"
    return got


def hash_now(host, other):
    try:
        assert_hash_clean(host, other, full=True, what="common")
        return "all buckets EQUAL"
    except AssertionError as e:
        return str(e)[:400]


def common(host, other, crash0, hashed=None):
    """The common cell: every bucket EQUAL (now, or `hashed`, taken before an ending), desyncSeen, new crash files."""
    hashed = hash_now(host, other) if hashed is None else hashed
    ds = [es(host, "desyncSeen"), es(other, "desyncSeen")]
    crash = sorted(session._crash_log_snapshot() - crash0)
    return (hashed == "all buckets EQUAL" and ds == [False, False] and not crash,
            f"common: hash {hashed}; desyncSeen host/{other.name} {ds} (want False/False); new crash files {crash} "
            f"(want none)")


def ctx_cell(new, origin, actor):
    return (len(new) == 1 and (new[0].get("origin"), new[0].get("kind"), new[0].get("actorId")) == (origin, "walk", actor),
            f"new host closedContexts {new} (want exactly one {{origin {origin}, kind walk, actorId {actor}}})")


def verdict(row, order, cells, ev):
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    fails = 0
    for name in order:
        ok, detail = cells.get(name, (False, f"not reached: {ev.get('error')}"))
        fails += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)
    print(f"{row} {'PASS' if not fails else 'FAIL'} ({fails} of {len(order)} cells failed)", flush=True)
    return fails


def run_row(row, order, fn):
    """One row: `fn()` returns (cells, ev); an exception fails every cell it did not reach."""
    try:
        cells, ev = fn()
    except Exception as e:
        cells, ev = {}, {"error": f"{type(e).__name__}: {str(e)[:600]}"}
    return verdict(row, order, cells, ev)


def fail_all(rows, why):
    """Every row that could not be reached: each cell FAILs `why` (boot / staging / rejoin)."""
    return sum(verdict(row, order, {n: (False, why) for n in order}, {"error": why}) for row, order in rows)


def shut(*gcs):
    for gc in gcs:
        try:
            if gc is not None and gc.proc is not None and gc.proc.poll() is None:
                gc.shutdown()
        except Exception as e:
            print(f"[pvp_gm3] shutdown {gc.name}: {type(e).__name__}: {str(e)[:200]}", flush=True)


def walk_done(host, other, uid, dest, ev):
    """Bounded: `uid` on `dest` on both machines and the other's order slot empty, then the host idle."""
    ok, ev["walkS"] = wait_until(lambda: pos(host, uid) == dest and pos(other, uid) == dest
                                 and es(other, "inFlight") is None, STEP_S, 0.2)
    try:
        session.wait_host_idle(host, other, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    return ok


# ===================== the endings (host_wins, partner_wins; test_pvp_rejoin reuses it) =====================


def record_view(rec):
    rec = rec if isinstance(rec, dict) else {}
    pv = sorted((e.get("seat"), e.get("verdict")) for e in (rec.get("perSeatVerdict") or []) if isinstance(e, dict))
    t = rec.get("tally") or {}
    return {"seq": rec.get("seq"), "reason": rec.get("reason"), "aborted": rec.get("aborted"),
            "inExitArea": rec.get("inExitArea"), "verdicts": pv,
            "tally": {k: t.get(k) for k in ("liveAliens", "liveSoldiers", "inExit")}}


def ending(row, host, other, kill_faction, dead_ids, presser, expect, crash0):
    """Pre-ending (both records at 0, every bucket EQUAL), host kill_unit_real {faction}, the kill chain, the side
    owner's END TURN, the host's NextTurnState closed by dismiss_popup, the host's DebriefingState (as
    test_battle_end_rules' stage_pvp_elimination and end_pvp_elimination). Returns (cells, ev)."""
    m, ev, cells, steps, ends = (host, other), {}, {}, [], []
    pre = {gc.name: {k: (es(gc, "battleEnd") or {}).get(k) for k in ("emitted", "applied")} for gc in m}
    hashed = hash_now(host, other)
    ev.update(pre=pre, hashBefore=hashed)
    if any(v != {"emitted": 0, "applied": 0} for v in pre.values()):
        steps.append(f"pre-ending records {pre} (want emitted 0 / applied 0 on both)")
    kill = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": kill_faction})
    ok, ev["chainS"] = wait_until(lambda: host_chain_done(host, dead_ids), STEP_S, 0.1)
    if not ok:
        steps.append(f"kill chain not done in {ev['chainS']} s (host stack {stack(host)})")
    try:
        session.wait_host_idle(host, other, timeout=STEP_S)
    except Exception as e:
        steps.append(f"wait_host_idle after the kill: {str(e)[:200]}")
    ev["kill"] = kill
    cells[f"{row}-kill"] = (kill.get("ok") is True and sorted(kill.get("killed") or []) == sorted(dead_ids) and not steps,
                            f"killed {kill.get('killed')} (want {dead_ids}); {steps or 'records at 0, chain done'}")
    ev["press"] = presser.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    ok, secs = wait_until(lambda: host_next_turn_up(host), STEP_S, 0.1)
    if not ok:
        ends.append(f"host NextTurnState not up in {secs} s after {presser.name}'s END TURN")
    d = host.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") != "NextTurnState->close":
        ends.append(f"host dismiss_popup handled {d.get('handled')!r} (want 'NextTurnState->close')")
    hok, hs = wait_until(lambda: any("DebriefingState" in s for s in stack(host)), STEP_S, 0.1)
    ook, osec = wait_until(lambda: top(other) == "DebriefingState"   # its display-only fill runs in its init()
                           and (es(other, "battleEnd") or {}).get("debriefDisplayOnly") == 1, STEP_S, 0.25)
    hrec, orec = es(host, "battleEnd") or {}, es(other, "battleEnd") or {}
    hv, ov = record_view(hrec), record_view(orec)
    ev.update(host=hv, other=ov, hostEmitted=hrec.get("emitted"), otherApplied=orec.get("applied"),
              otherDisplayOnly=orec.get("debriefDisplayOnly"), tops=[stack(host), stack(other)], hostDebriefS=hs,
              otherEndS=osec, dismiss=d.get("handled"))
    want = {k: expect[k] for k in ("reason", "aborted", "inExitArea", "verdicts", "tally")}
    cells[f"{row}-host"] = (hrec.get("emitted") == 1 and isinstance(hv["seq"], int) and hv["seq"] > 0
                            and {k: hv[k] for k in want} == want,
                            f"host battleEnd emitted {hrec.get('emitted')} (want 1) {hv} (want seq > 0 and {want})")
    cells[f"{row}-client"] = (orec.get("applied") == 1 and ov == hv,
                              f"{other.name} battleEnd applied {orec.get('applied')} (want 1) {ov} (want the host's)")
    if not hok or top(host) != "DebriefingState":
        ends.append(f"host stack {stack(host)} {hs} s after the close (want DebriefingState on top)")
    if not ook or top(other) != "DebriefingState":
        ends.append(f"{other.name} top {top(other)} {osec} s after the host's debriefing (want DebriefingState)")
    if orec.get("debriefDisplayOnly") != 1:
        ends.append(f"{other.name} battleEnd.debriefDisplayOnly {orec.get('debriefDisplayOnly')} (want 1)")
    try:
        session.assert_client_zero_disk(other.user_dir)
    except AssertionError as e:
        ends.append(str(e)[:300])
    cells[f"{row}-ends"] = (not ends, f"{ends or 'both tops DebriefingState, the other display-only, no client save'}")
    cells[f"{row}-common"] = common(host, other, crash0, hashed)
    return cells, ev


# ===================== boot gm3_boot =====================


def bring_up(host, client, key, tag):
    """The gm3 bring-up (both boots): roster pin, the HOST on the Alien team, the battle-entry steps
    (PSR.drive_to_gm2_battlescape), pin_ai_neutral."""
    m = (host, client)
    guarded(tag, lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    guarded(tag, lambda: host.ok({"cmd": "set_seed", "seed": SEED_ROSTER}), m)
    gm = guarded(tag, lambda: PF.start_pvp_skirmish_lobby(host, client, key, alien_player="host"), m)[0]
    guarded(tag, lambda: PSR.drive_to_gm2_battlescape(host, client), m)
    crash0 = session._crash_log_snapshot()
    pinned = guarded(tag, lambda: session.pin_ai_neutral(host, client, tag="pvp_gm3"), m)   # 0 is legal (PSR :147)
    guarded(tag, lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)   # as boot_pvp before its hash
    return {"lobbyGamemode": gm, "pinned": pinned}, crash0


def census_cells(host, client, boot):
    """gm3_census's mode / authority / seat / equality cells (aliens_down_boot re-checks gm3_census-mode and
    gm3_census-seats)."""
    hb, cb = bview(host), bview(client)
    uh, uc = units(host), units(client)
    ha, ca = hb.get("authority") or {}, cb.get("authority") or {}
    seat0 = sorted(i for i, u in uh.items() if u.get("coop") == 0)
    seat1 = sorted(i for i, u in uh.items() if u.get("coop") == 1)
    others = sorted((i, u.get("coop")) for i, u in uh.items() if u.get("coop") not in (0, 1, -1))
    f0, f1 = sorted({uh[i].get("faction") for i in seat0}), sorted({uh[i].get("faction") for i in seat1})
    fc = {i: ((uh.get(i) or {}).get("faction"), (uh.get(i) or {}).get("coop"), (uc.get(i) or {}).get("faction"),
              (uc.get(i) or {}).get("coop")) for i in set(uh) | set(uc)}
    diff = {i: v for i, v in fc.items() if v[:2] != v[2:]}
    cells = {"gm3_census-mode": (boot["lobbyGamemode"] == hb["coopGamemode"] == cb["coopGamemode"] == GAMEMODE_GM3
                                 and hb["mapFingerprint"] == cb["mapFingerprint"] == MAP_FP,
                                 f"lobby gamemode {boot['lobbyGamemode']}, coopGamemode host/partner "
                                 f"{hb['coopGamemode']}/{cb['coopGamemode']} (want 3), mapFingerprint "
                                 f"{hb['mapFingerprint']}/{cb['mapFingerprint']} (want {MAP_FP})"),
             "gm3_census-auth": ((ha.get("localSeat"), ha.get("hostSim"), ca.get("localSeat"), ca.get("hostSim"))
                                 == (0, True, 1, False),
                                 f"authority host {ha} partner {ca} (want localSeat 0 hostSim true / 1 false)"),
             "gm3_census-seats": (seat0 == ALIEN_IDS and f0 == [FACTION_HOSTILE] and seat1 == XCOM_IDS
                                  and f1 == [FACTION_PLAYER] and not others,
                                  f"host seat 0 ids {seat0} factions {f0} (want {ALIEN_IDS} [1]); seat 1 ids "
                                  f"{seat1} factions {f1} (want {XCOM_IDS} [0]); other seats {others} (want only "
                                  f"coop -1)"),
             "gm3_census-equal": (sorted(uh) == sorted(uc) and not diff,
                                  f"id sets equal {sorted(uh) == sorted(uc)}; per-unit (faction, coop) host vs "
                                  f"partner differences {diff} (want none)")}
    return cells, {"host": hb, "partner": cb, "boot": boot}


def row_gm3_census(host, client, boot, crash0):
    cells, ev = census_cells(host, client, boot)
    wait_until(lambda: log_count(host, N_EQUAL) >= 1, 3, 0.25)   # bounded log flush (measured: 1 at once)
    eq_n, mm_n = log_count(host, N_EQUAL), log_count(host, N_MISMATCH)
    cells["gm3_census-ready"] = (eq_n == 1 and mm_n == 0,
                                 f"host log '{N_EQUAL}' {eq_n} (want 1), MISMATCH {mm_n} (want 0)")
    st = [(ev[n]["side"], ev[n]["turn"]) for n in ("host", "partner")]
    cells["gm3_census-turn"] = (st == [(0, 1), (0, 1)], f"(side, turn) host/partner {st} (want (0, 1) on both)")
    cells["gm3_census-common"] = common(host, client, crash0)
    ev.update(nothing=[log_count(host, N_NOTHING), log_count(client, N_NOTHING)],
              equip={"host": es(host, "equip"), "partner": es(client, "equip")})
    return cells, ev


def stage_gm3(host, client):
    m = (host, client)
    ev = {"reactions": guarded("gm3_boot staging", lambda: reactions_zero(host, client), m)}
    ev["A"] = guarded("gm3_boot staging", lambda: tele_both(host, client, A_ID, A_TILE, A_DIR).get("to"), m)
    ev["S"] = guarded("gm3_boot staging", lambda: tele_both(host, client, S_ID, S_TILE, S_DIR).get("to"), m)
    guarded("gm3_boot staging", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    return ev


def row_partner_walk(host, client, crash0):
    b_ctx, b_sent, b_deny = es(host, "closedContexts") or [], es(client, "coopIntentsSent") or {}, es(client, "lastDeny")
    ev = {"resp": session.send_walk(client, S_ID, S_DEST)}
    walk_done(host, client, S_ID, S_DEST, ev)
    new = new_contexts(b_ctx, es(host, "closedContexts"))
    sent, deny, infl = es(client, "coopIntentsSent") or {}, es(client, "lastDeny"), es(client, "inFlight")
    sides, ps = [battle_state(host).get("side"), battle_state(client).get("side")], [pos(host, S_ID), pos(client, S_ID)]
    ev.update(newCtx=new, sent=sent, lastDeny=deny)
    return {"partner_walk-ctx": ctx_cell(new, "intent", S_ID),
            "partner_walk-pos": (ps == [S_DEST, S_DEST],
                                 f"S host/partner {ps} (want {S_DEST} on both; {ev['walkS']} s)"),
            "partner_walk-sent": (sent.get("walk", 0) == b_sent.get("walk", 0) + 1 and deny == b_deny and infl is None,
                        f"partner coopIntentsSent {b_sent} -> {sent} (want walk +1), lastDeny {b_deny} -> {deny} (want "
                        f"unchanged), inFlight {infl} (want None)"),
            "partner_walk-side": (sides == [0, 0], f"side host/partner {sides} (want 0 on both)"),
            "partner_walk-common": common(host, client, crash0)}, ev


def row_turn_to_aliens(host, client, crash0):
    seq0 = es(host, "lastSeqEmitted") or 0
    ev = {"resp": client.cmd({"cmd": "battle_action", "action": "end_turn_button"})}
    try:
        drive_side_change(host, client, FACTION_HOSTILE, timeout=STEP_S)
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["sideError"] = str(e)[:300]
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    hk = {k: [e["seq"] for e in hev if e["kind"] == k] for k in ("side_transition", "side_begin")}
    ck = {k: [e["seq"] for e in cev if e["kind"] == k] for k in ("side_transition", "side_begin")}
    st = [(battle_state(gc).get("side"), battle_state(gc).get("turn")) for gc in (host, client)]
    ev.update(hostEvs=[(e["seq"], e["kind"]) for e in hev], host=bview(host), partner=bview(client))
    return {"turn_to_aliens-side": (st == [(1, 1), (1, 1)], f"(side, turn) host/partner {st} (want (1, 1) on both)"),
            "turn_to_aliens-once": (len(hk["side_transition"]) == 1 and len(hk["side_begin"]) == 1 and ck == hk,
                        f"since the press host side_transition / side_begin seqs {hk} (want one each), partner {ck} "
                        f"(want the same)"),
            "turn_to_aliens-common": common(host, client, crash0)}, ev


def row_host_ui_walk(host, client, crash0):
    ev = {"sel0": battle_state(host).get("selectedId")}
    host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})   # ONE TAB first
    time.sleep(0.15)
    ev["tab"] = tab_select(host, A_ID)
    ev["sel"] = battle_state(host).get("selectedId")
    cells = {"host_ui_walk-sel": (ev["sel"] == A_ID, f"host selectedId {ev['sel']} before the click (want {A_ID})")}
    if ev["sel"] != A_ID:
        cells.update({n: (False, "staging (the host's TAB never selected A)")
                      for n in ("host_ui_walk-ctx", "host_ui_walk-pos", "host_ui_walk-common")})
        return cells, ev
    b_ctx = es(host, "closedContexts") or []
    real_click_walk(host, A_DEST)
    walk_done(host, client, A_ID, A_DEST, ev)
    new = new_contexts(b_ctx, es(host, "closedContexts"))
    pa, sides = [pos(host, A_ID), pos(client, A_ID)], [battle_state(gc).get("side") for gc in (host, client)]
    ev["newCtx"] = new
    cells["host_ui_walk-ctx"] = ctx_cell(new, "host", A_ID)
    cells["host_ui_walk-pos"] = (pa == [A_DEST, A_DEST] and sides == [1, 1],
                       f"A host/partner {pa} (want {A_DEST} on both; {ev['walkS']} s), side {sides} (want 1 on both)")
    cells["host_ui_walk-common"] = common(host, client, crash0)
    return cells, ev


def boot_gm3():
    host = GameClient("host", None, make_user_dir("pvp_gm3_host"))
    client = GameClient("client", None, make_user_dir("pvp_gm3_client"))
    try:
        try:
            boot, crash0 = bring_up(host, client, GM3_KEY, "gm3_boot")
        except Miss:
            return fail_all(GM3_ROWS, "boot (setup failure, see the CAPTURE gm3_boot line)")
        rows = dict(GM3_ROWS)
        fails = run_row("gm3_census", rows["gm3_census"], lambda: row_gm3_census(host, client, boot, crash0))
        try:
            staged = stage_gm3(host, client)
        except Miss:
            staged = None
        fails += (run_row("partner_walk", rows["partner_walk"],
                          lambda: row_partner_walk(host, client, crash0)) if staged
                  else fail_all((("partner_walk", rows["partner_walk"]),),
                                "staging (see the CAPTURE gm3_boot staging line)"))
        fails += run_row("turn_to_aliens", rows["turn_to_aliens"], lambda: row_turn_to_aliens(host, client, crash0))
        fails += (run_row("host_ui_walk", rows["host_ui_walk"],
                          lambda: row_host_ui_walk(host, client, crash0)) if staged
                  else fail_all((("host_ui_walk", rows["host_ui_walk"]),),
                                "staging (see the CAPTURE gm3_boot staging line)"))
        fails += run_row("host_wins", rows["host_wins"],
                         lambda: ending("host_wins", host, client, FACTION_PLAYER, XCOM_IDS, host,
                                        EXPECT["host_wins"], crash0))
        return fails
    finally:
        shut(host, client)


# ===================== boot aliens_down_boot =====================


def boot_aliens_down():
    host = GameClient("host", None, make_user_dir("pvp_gm3_aliens_down_host"))
    client = GameClient("client", None, make_user_dir("pvp_gm3_aliens_down_client"))
    try:
        try:
            boot, crash0 = bring_up(host, client, ALIENS_DOWN_KEY, "aliens_down_boot")
            cells, _ev = census_cells(host, client, boot)
            bad = {n: cells[n][1] for n in ("gm3_census-mode", "gm3_census-seats") if not cells[n][0]}
            if bad:
                capture("aliens_down_boot", f"pre-ending gm3_census cells {bad}", (host, client))
                raise Miss("aliens_down_boot")
            guarded("aliens_down_boot", lambda: reactions_zero(host, client), (host, client))
        except Miss:
            return fail_all(ALIENS_DOWN_ROWS, "boot (setup failure, see the CAPTURE aliens_down_boot line)")
        return run_row("partner_wins", ALIENS_DOWN_ROWS[0][1],
                       lambda: ending("partner_wins", host, client, FACTION_HOSTILE, ALIEN_IDS, client,
                                      EXPECT["partner_wins"], crash0))
    finally:
        shut(host, client)


def main():
    t0 = time.time()
    fails = boot_gm3()
    fails += boot_aliens_down()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_gm3: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
