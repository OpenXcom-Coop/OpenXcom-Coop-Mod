"""W2-H39 rows X3, Z3, O3 (boot P3, gm3: the HOST plays the aliens) and A2, Z2, H2 (boot P2, gm2: the client plays the
aliens): after the start-of-side panic check of the side the host does not play, the PvP host holds no unit and no
action actor (design-D6, QU2-7 (a)); the panic itself still plays out on the host, and the host's own side is unchanged.

Spec: docs repo rewrite/prompts/w2h39_pvp_panic_selection.md section (f), orchestrator rulings QH39-1 .. QH39-5 (a) and
R-H39-SA-1. Constants: rewrite/w2h39-task0/CONSTANTS.md (TASK 0 boots Pa, Pb (gm3) and Pc, Pd (gm2) on the unchanged
build; every pin equal on the paired boots; VERDICT CONFIRMED).

Boot P3 (key 49036, dirs w2h39_p3_host / _client, options OPTS_P3): G3F.bring_up; staging = G3F.reactions_zero,
RM.stage_tiles(TILES_D), the partner's END TURN -> side 1 turn 1, X stripped and X morale 0 on both (R-U2-SD-1).
  X3  host set_seed SEED_X, the host's END TURN -> side 0 turn 2: X panics on the alien host. X3-roll (0, 2) on both, X
      status STATUS_X at the roll, one host panic ev {X, MODE_X} and one bt_action_end on its actionId; X3-sel host
      selectedId -1 at both reads; X3-actor host currentActionActorId -1 at both reads; X3-partner the partner on
      PARTNER_SEL3 / PARTNER_SEL3 at both reads.
  Z3  the alien host's Delete after the panic: Z3-zero host coopWaitText != TEXT_NOT_YOURS ZERO_READ_S after the key;
      Z3-quiet X's TU on both, the host's closedContexts count and its top (BattlescapeState) unchanged.
  O3  A morale 0, host set_seed SEED_O3, the PARTNER's END TURN -> side 1 turn 2: the host's own alien panics. O3-roll
      (1, 2) on both, A status STATUS_O3, one panic ev {A, MODE_O3} and its bt_action_end; O3-own host selectedId and
      currentActionActorId A (the drop leaves the host's own side alone). O3 is the boot's last row.
Boot P2 (key 49037, dirs w2h39_p2_host / _client, default options): BER.boot_e6, G3F.reactions_zero, A morale 0 (R5-U3's
boot A).
  A2  PR.row_p1 (host set_seed SEED_P1, the host's END TURN -> side 1 turn 1, A panics on the X-COM host). A2-roll every
      P1 cell passes; A2-sel / A2-actor host selectedId / currentActionActorId -1 at both reads; A2-client the client
      on A / A at both reads.
  Z2  as Z3 with A: Z2-zero, Z2-quiet.
  H2  the client's END TURN -> side 0 turn 2: H2-own host selectedId and currentActionActorId HOST_SEL2.
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane
crash folder. EVIDENCE only: cursorType, cursorVisible, hiddenMovementShown, coopWaitText, warningText, panicHandled, the
host boxes, the units' (status, tu, morale), the top stacks.

RED on the unchanged build (commit A1): X3-sel, X3-actor, Z3-zero, A2-sel, A2-actor, Z2-zero (15 of 21 cells PASS). One
EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step
past its bound prints ONE CAPTURE line and fails the boot's rows "boot"; a staging step past its bound fails the rows
that need it "staging". Lever pairs go to the client first (F607). WV-D95: run in the foreground to completion. WV-D99 /
WV-D100: ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_panic_selection.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
from repro_atom_side_begin import drive_side_change  # noqa: E402
from test_delta_core import both  # noqa: E402
from test_host_combat import evs_since  # noqa: E402
from test_ai_origins import host_payloads  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_pvp_rules as PR  # noqa: E402
import test_messages as MSG  # noqa: E402

P3_KEY, P2_KEY = "49036", "49037"
OPTS_P3 = {"noAlienPanicMessages": True}   # S-D's Le / Lf user-dir option (F14755)
A_ID = 1000000                    # the only alien (gm3: the host's, seat 0; gm2: the client's, seat 1)
X = 13                            # the partner's X-COM soldier staged to panic in gm3 (stripped, morale 0)
TILES_D = {u: (t, d if u == A_ID else 4) for u, (t, d) in RM.TILES.items()}   # every X-COM unit faces 4 (Pa, Pb)
SEED_X, STATUS_X, MODE_X = 1, 9, "berserk"     # host set_seed before the host's END TURN (Pa, Pb)
SEED_O3, STATUS_O3, MODE_O3 = 1, 8, "flee"     # host set_seed before the PARTNER's END TURN (Pa, Pb)
PARTNER_SEL3 = 8                  # the gm3 partner's selection and action actor after X's panic (Pa, Pb)
HOST_SEL2 = 8                     # the gm2 host's selection and action actor at entry and at side 0 turn 2 (Pc, Pd)
TEXT_NOT_YOURS = "Not one of your soldiers"   # en-US :77 STR_COOP_DENY_NOT_YOUR_UNIT
KEY_ZERO = 127                    # Delete: Zero TU (keyBattleZeroTUs)
ZERO_READ_S = 1.0                 # the refusal banner dwells ~5.95 s (W2-H36 TASK 0); up at 1.05 s on Pa-Pd
TEXT_WAIT_S = 8                   # the bounded wait for an empty host coopWaitText before the Delete
PANIC_S = 15                      # the bounded wait for the host's panic ev and its bt_action_end
READ_GAP_S = 1.0
STEP_S = G3F.STEP_S
BS_KEYS = ("side", "turn", "selectedId", "currentActionActorId", "cursorType", "cursorVisible", "hiddenMovementShown",
           "coopWaitText", "warningText", "panicHandled")
P1_CELLS = ("P1-roll", "P1-act", "P1-after", "P1-common")
P3_ROWS = (("X3", ("X3-roll", "X3-sel", "X3-actor", "X3-partner", "X3-common")),
           ("Z3", ("Z3-zero", "Z3-quiet", "Z3-common")),
           ("O3", ("O3-roll", "O3-own", "O3-common")))
P2_ROWS = (("A2", ("A2-roll", "A2-sel", "A2-actor", "A2-client", "A2-common")),
           ("Z2", ("Z2-zero", "Z2-quiet", "Z2-common")),
           ("H2", ("H2-own", "H2-common")))

es = G3F.es


def view(gc):
    b = battle_state(gc)
    return {k: b.get(k) for k in BS_KEYS}


def stm(gc, uid):
    """(status, tu, morale) of `uid` on this machine."""
    u = G3F.units(gc).get(uid) or {}
    return (u.get("status"), u.get("tu"), u.get("morale"))


def morale0(host, client, uid):
    return both(host, client, {"cmd": "battle_set_unit_state", "unit": uid, "morale": 0}, ("morale",)).get("morale")


def reads(host, client):
    """Two battle_state views of both machines READ_GAP_S apart."""
    r1 = {"host": view(host), "client": view(client)}
    time.sleep(READ_GAP_S)
    return [r1, {"host": view(host), "client": view(client)}]


def seeded_side(host, client, presser, side, turn, seed, uid, ev):
    """PR.row_p1's first half (:134-:168) with the presser, side, turn and watched unit as parameters: the host's
    set_seed, the presser's END TURN, the wait for (side, turn) on both, the roll read on both before any NextTurnState
    closes, drive_side_change, the panic wait (host boxes closed host-only, leftover NextTurnStates closed),
    wait_host_idle. Fills `ev`."""
    seq0 = es(host, "lastSeqEmitted") or 0
    host.ok({"cmd": "set_seed", "seed": seed})
    ev.update(seq0=seq0, seed=seed, press=presser.cmd({"cmd": "battle_action", "action": "end_turn_button"}).get("ok"))
    ok, secs = PR.wait_until(lambda: all((battle_state(gc).get("side"), (battle_state(gc).get("turn") or 0) >= turn)
                                         == (side, True) for gc in (host, client)), STEP_S, 0.05)
    ev.update(sideS=[ok, secs], roll=[stm(host, uid), stm(client, uid)], rollStacks=[G3F.stack(host), G3F.stack(client)])
    try:
        drive_side_change(host, client, side, want_turn_min=turn, timeout=STEP_S)
    except Exception as e:
        ev["sideError"] = str(e)[:300]
    rec, closed = {"hostBoxes": []}, []

    def panic_done():
        MSG.poll_host_box(host, rec, f"side {side}")
        closed.extend(PR.close_leftovers(host, client))
        hev = evs_since(host, seq0)
        pids = [e["actionId"] for e in hev if e["kind"] == "panic"]
        return bool(pids) and any(e["kind"] == "bt_action_end" and e["actionId"] == pids[0] for e in hev) \
            and es(host, "busyOwnerSeat") == -1
    ev["panicWait"] = PR.wait_until(panic_done, PANIC_S, 0.2)
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    MSG.poll_host_box(host, rec, f"side {side} after")
    closed.extend(PR.close_leftovers(host, client))
    hev = evs_since(host, seq0)
    pseqs = [e["seq"] for e in hev if e["kind"] == "panic"]
    pl = host_payloads(host, pseqs, timeout=3) if pseqs else {}
    ev.update(hostEvs=[(e["seq"], e["kind"], e["actionId"]) for e in hev], hostBoxes=rec["hostBoxes"],
              leftoverClosed=closed, panics={s: (v.get("payload"), v.get("actionId")) for s, v in sorted(pl.items())},
              after=[stm(host, uid), stm(client, uid)], stacks=[G3F.stack(host), G3F.stack(client)])


def roll_cell(ev, want_st, uid, status, mode, at):
    """(side, turn) on both, the unit's status at the roll on both, one panic ev {uid, mode}, one bt_action_end on it."""
    bad = []
    st = [(at["host"]["side"], at["host"]["turn"]), (at["client"]["side"], at["client"]["turn"])]
    if not ev["sideS"][0] or st != [want_st] * 2:
        bad.append(f"(side, turn) host/client {st} (want {want_st} on both; reached {ev['sideS']})")
    if [r[0] for r in ev["roll"]] != [status, status]:
        bad.append(f"unit {uid} status at the roll host/client {[r[0] for r in ev['roll']]} (want {status} on both)")
    panics = [(s, a) for s, k, a in ev["hostEvs"] if k == "panic"]
    if len(panics) != 1:
        bad.append(f"host panic evs (seq, actionId) {panics} (want exactly one)")
    else:
        payload = (ev["panics"].get(panics[0][0]) or (None,))[0] or {}
        ends = [s for s, k, a in ev["hostEvs"] if k == "bt_action_end" and a == panics[0][1]]
        if (payload.get("unit"), payload.get("mode")) != (uid, mode):
            bad.append(f"panic payload {payload} (want unit {uid}, mode {mode})")
        if len(ends) != 1:
            bad.append(f"bt_action_end evs of actionId {panics[0][1]}: {ends} (want exactly one)")
    return (not bad, "; ".join(bad) or f"{want_st} on both, status {status} at the roll, one panic {ev['panics']} and "
                                       f"its bt_action_end")


def none_cell(r, machine, key, want, unchanged):
    got = [x[machine][key] for x in r]
    return (got == [want, want], f"{machine} {key} at the two reads {got} (want {want} at both; unchanged build: "
                                 f"{unchanged})")


def row_zero(row, host, client, uid, crash0):
    """The host's Delete with the panicked unit off its side: ZERO_READ_S after the key no "Not one of your soldiers";
    the unit's TU on both, the host's closedContexts count and its top unchanged."""
    ev = {"textBefore": battle_state(host).get("coopWaitText")}
    ev["textWait"] = PR.wait_until(lambda: battle_state(host).get("coopWaitText") == "", TEXT_WAIT_S, 0.1)
    tu0, ctx0 = [stm(host, uid)[1], stm(client, uid)[1]], len(es(host, "closedContexts") or [])
    t0 = time.time()
    host.ok({"cmd": "inject_input", "kind": "key", "key": KEY_ZERO})
    time.sleep(max(0.0, t0 + ZERO_READ_S - time.time()))
    b = battle_state(host)
    ev.update(atS=round(time.time() - t0, 2), text=b.get("coopWaitText"), warningText=b.get("warningText"),
              selectedId=b.get("selectedId"))
    tu1, ctx1, tp = [stm(host, uid)[1], stm(client, uid)[1]], len(es(host, "closedContexts") or []), G3F.stack(host)
    ev.update(tu=[tu0, tu1], ctx=[ctx0, ctx1], top=tp)
    cells = {f"{row}-zero": (ev["text"] != TEXT_NOT_YOURS,
                             f"host coopWaitText {ev['text']!r} {ev['atS']} s after Delete (want not {TEXT_NOT_YOURS!r}; "
                             f"unchanged build: it)"),
             f"{row}-quiet": (tu1 == tu0 and ctx1 == ctx0 and tp[-1:] == ["BattlescapeState"],
                              f"unit {uid} TU host/other {tu0} -> {tu1}, host closedContexts {ctx0} -> {ctx1}, host stack "
                              f"{tp} (want unchanged, BattlescapeState on top)"),
             f"{row}-common": G3F.common(host, client, crash0)}
    return cells, ev


# ===================== boot P3 (gm3) =====================


def stage_p3(host, client):
    m, st = (host, client), {}
    st["reactions"] = G3F.guarded("P3 staging", lambda: G3F.reactions_zero(host, client), m)
    st["placed"] = RM.stage_tiles(host, client, TILES_D, ())
    st["side1"] = {}
    G3F.guarded("P3 staging", lambda: RM.side_change(host, client, client, G3F.FACTION_HOSTILE, 1, st["side1"]), m)

    def strip():
        rc = client.cmd({"cmd": "battle_strip_unit", "unit": X})   # F607: client first
        rh = host.cmd({"cmd": "battle_strip_unit", "unit": X})
        assert rc.get("ok") and rh.get("ok") and rc.get("remaining") == 0 == rh.get("remaining"), (
            f"battle_strip_unit {X}: host {rh} client {rc} (want ok, remaining 0 on both)")
        return {"host": rh.get("deleted"), "client": rc.get("deleted")}
    st["strip"] = G3F.guarded("P3 staging", strip, m)
    st["morale"] = G3F.guarded("P3 staging", lambda: morale0(host, client, X), m)
    st["hostSel"] = battle_state(host).get("selectedId")
    return st


def row_x3(host, client, crash0):
    ev = {}
    seeded_side(host, client, host, G3F.FACTION_PLAYER, 2, SEED_X, X, ev)
    r = ev["reads"] = reads(host, client)
    ps = [(x["client"]["selectedId"], x["client"]["currentActionActorId"]) for x in r]
    cells = {"X3-roll": roll_cell(ev, (G3F.FACTION_PLAYER, 2), X, STATUS_X, MODE_X, r[0]),
             "X3-sel": none_cell(r, "host", "selectedId", -1, f"X {X}"),
             "X3-actor": none_cell(r, "host", "currentActionActorId", -1, f"X {X}"),
             "X3-partner": (ps == [(PARTNER_SEL3, PARTNER_SEL3)] * 2,
                            f"partner (selectedId, currentActionActorId) at the two reads {ps} (want "
                            f"{(PARTNER_SEL3, PARTNER_SEL3)} at both)"),
             "X3-common": G3F.common(host, client, crash0)}
    return cells, ev


def row_o3(host, client, crash0):
    ev = {"morale": morale0(host, client, A_ID)}
    seeded_side(host, client, client, G3F.FACTION_HOSTILE, 2, SEED_O3, A_ID, ev)
    at = ev["read"] = {"host": view(host), "client": view(client)}
    own = (at["host"]["selectedId"], at["host"]["currentActionActorId"])
    cells = {"O3-roll": roll_cell(ev, (G3F.FACTION_HOSTILE, 2), A_ID, STATUS_O3, MODE_O3, at),
             "O3-own": (own == (A_ID, A_ID), f"host (selectedId, currentActionActorId) after its own alien's panic {own} "
                                             f"(want {(A_ID, A_ID)})"),
             "O3-common": G3F.common(host, client, crash0)}
    return cells, ev


def boot_p3():
    host = GameClient("host", None, make_user_dir("w2h39_p3_host", options=OPTS_P3))
    client = GameClient("client", None, make_user_dir("w2h39_p3_client", options=OPTS_P3))
    rows = dict(P3_ROWS)
    try:
        try:
            boot, crash0 = G3F.bring_up(host, client, P3_KEY, "P3")
        except G3F.Miss:
            return G3F.fail_all(P3_ROWS, "boot (FIXTURE-STOP, see the CAPTURE P3 line)")
        entry = view(host)
        try:
            st = stage_p3(host, client)
        except G3F.Miss:
            st = None
        evd = {"boot": boot, "hostEntry": entry, "staging": st}
        print(f"EVIDENCE P3 staging: {json.dumps(evd, sort_keys=True, default=str)}", flush=True)
        if st is None:
            return G3F.fail_all(P3_ROWS, "staging (see the CAPTURE P3 staging line)")
        fails = G3F.run_row("X3", rows["X3"], lambda: row_x3(host, client, crash0))
        fails += G3F.run_row("Z3", rows["Z3"], lambda: row_zero("Z3", host, client, X, crash0))
        fails += G3F.run_row("O3", rows["O3"], lambda: row_o3(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


# ===================== boot P2 (gm2) =====================


def row_a2(host, client, crash0):
    cells_p1, ev_p1 = PR.row_p1(host, client, crash0)
    r = reads(host, client)
    ev = {"p1": ev_p1, "reads": r}
    p1 = [(n, cells_p1.get(n, (False, "not reached"))) for n in P1_CELLS]
    cs = [(x["client"]["selectedId"], x["client"]["currentActionActorId"]) for x in r]
    cells = {"A2-roll": (all(c[0] for _n, c in p1), "; ".join(f"{n} {'PASS' if c[0] else 'FAIL'}: {c[1]}" for n, c in p1)),
             "A2-sel": none_cell(r, "host", "selectedId", -1, f"A {A_ID}"),
             "A2-actor": none_cell(r, "host", "currentActionActorId", -1, f"A {A_ID}"),
             "A2-client": (cs == [(A_ID, A_ID)] * 2, f"client (selectedId, currentActionActorId) at the two reads {cs} "
                                                     f"(want {(A_ID, A_ID)} at both)"),
             "A2-common": G3F.common(host, client, crash0)}
    return cells, ev


def row_h2(host, client, crash0):
    ev, cells = {"side": {}}, {}
    try:
        RM.side_change(host, client, client, G3F.FACTION_PLAYER, 2, ev["side"])
        b = ev["host"] = view(host)
        got = ((b["side"], b["turn"]), b["selectedId"], b["currentActionActorId"])
        cells["H2-own"] = (got == ((0, 2), HOST_SEL2, HOST_SEL2),
                           f"host ((side, turn), selectedId, currentActionActorId) {got} (want "
                           f"{((0, 2), HOST_SEL2, HOST_SEL2)})")
    except Exception as e:
        cells["H2-own"] = (False, f"the client's END TURN -> side 0 turn 2 failed: {type(e).__name__}: {str(e)[:300]}")
    cells["H2-common"] = G3F.common(host, client, crash0)
    return cells, ev


def boot_p2():
    host = GameClient("host", None, make_user_dir("w2h39_p2_host"))
    client = GameClient("client", None, make_user_dir("w2h39_p2_client"))
    m, rows = (host, client), dict(P2_ROWS)
    try:
        try:
            info = G3F.guarded("P2", lambda: BER.boot_e6(host, client, P2_KEY), m)
            G3F.guarded("P2", lambda: G3F.reactions_zero(host, client), m)
            crash0 = session._crash_log_snapshot()
            G3F.guarded("P2", lambda: morale0(host, client, A_ID), m)
        except G3F.Miss:
            return G3F.fail_all(P2_ROWS, "boot (FIXTURE-STOP, see the CAPTURE P2 line)")
        print(f"EVIDENCE P2 boot: {json.dumps({'info': info, 'hostEntry': view(host)}, sort_keys=True, default=str)}",
              flush=True)
        fails = G3F.run_row("A2", rows["A2"], lambda: row_a2(host, client, crash0))
        fails += G3F.run_row("Z2", rows["Z2"], lambda: row_zero("Z2", host, client, A_ID, crash0))
        fails += G3F.run_row("H2", rows["H2"], lambda: row_h2(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_p3()
    fails += boot_p2()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_panic_selection: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
