"""W2-H40 rows P, Z, M (boot C, classic co-op, gamemode 1: both seats play X-COM): after the start-of-side panic check
on the host's own side, a co-op host never keeps its partner's soldier selected (design-D6; the orchestrator's ruling
for W2-H40): it holds its own next soldier H_NEXT (vanilla's next-unit order, what its Tab gives), with the action actor
and the HUD on it; the panic itself still plays out on the host, and an own panicked soldier stays selected (vanilla).

Spec: docs repo rewrite/prompts/w2h40_coop_panic_selection.md section (f), orchestrator rulings QH40-1 .. QH40-7 (a).
Constants: rewrite/w2h40-task0/CONSTANTS.md (TASK 0 boots Ca, Cb on this file's red chain and Cc, Cd on the green
chain's stand-in, unchanged build 59fa2ed3a; every pin equal on the paired boots; VERDICT CONFIRMED).

Boot C (key 49038, dirs w2h40_c_host / _client, default options): test_w2_turn_cues' bring-up with this key (asserts:
map fingerprint, seated [8, 9], unit order on both, pinned [A], coopGamemode 1 on both); staging = the partner's X
stripped (client then host, remaining 0 on both) and X morale 0 on both (client first).
  P  TCU.cycle, host set_seed SEED_P right before its END TURN -> side 0 turn 2: the partner's X panics on the host.
     P-roll (0, 2) on both, no cycle note, one host panic ev {X, MODE_P} and one bt_action_end on its actionId;
     P-sel / P-actor host selectedId / currentActionActorId H_NEXT at both reads; P-hud the host's painted hud equals
     H_NEXT's units[] view on HUD_FIELDS at the second read; P-partner the client on one of SEATED with its action
     actor equal at both reads (L-H40-1: the client's id alternates, never pinned).
  Z  the host's Delete (key 127) after the panic: Z-text host coopWaitText != TEXT_NOT_YOURS ZERO_READ_S after the
     key; Z-own H_NEXT's TU 0 on both within FOLLOW_S and HLE.ctx_fails("zero_tu", H_NEXT, ...) == [] (W2-H30's host
     zero_tu context: evs [zero_tu, bt_action_end], payload {actor, unit}).
  M  X morale 100, H stripped and morale 0, TCU.cycle with SEED_M -> side 0 turn 3: the host's own H panics.
     M-roll (0, 3) on both, one panic {H, MODE_M} and its bt_action_end; M-own host selectedId and
     currentActionActorId H at both reads (guard); M-partner as P-partner. M is the last row.
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new crash file.
EVIDENCE only: both reads' views of both machines, the units' (status, tu, morale), the host boxes, the cycles, the
host camera offset before the cycle and at the second read, the top stacks.

RED on the unchanged build (commit A1): P-sel, P-actor, P-hud, Z-text, Z-own (8 of 13 cells PASS). GREEN (A2): all
13 cells PASS. One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a
failure. A boot step past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound
fails the rows that need it "staging". Lever pairs go to the client first (F607). WV-D95: run in the foreground to
completion. WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_w2_coop_panic_selection.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, pin_ai_neutral  # noqa: E402
from test_w2_ai_origins import bring_up_lobby_roster_pinned, host_payloads  # noqa: E402
from test_w2_delta_core import both  # noqa: E402
import test_w2_turn_cues as TCU  # noqa: E402
import test_r5_pvp_gm3 as G3F  # noqa: E402
import test_r5_pvp_rules as PR  # noqa: E402
import test_w2_host_combat as HC  # noqa: E402
import test_w2_host_local_ev as HLE  # noqa: E402
import test_w2_client_shoot as CSH  # noqa: E402
import test_w2_host_skill_ev as HSE  # noqa: E402

KEY = "49038"
HOST_DIR, CLIENT_DIR = "w2h40_c_host", "w2h40_c_client"    # default options
X = TCU.C2_ID                     # 9: the partner's (client seat's) soldier staged to panic
H = TCU.H_ID                      # 10: a host seat soldier (the M row's own panic)
A_ID = TCU.A_ID                   # 1000000, the only alien (pinned neutral)
SEATED = TCU.SEATED               # [8, 9], the client seat's soldiers
GAMEMODE = 1                      # classic co-op skirmish
SEED_P, MODE_P = 1, "berserk"     # host set_seed before its END TURN -> X goes berserk (Ca, Cb, Cc, Cd)
SEED_M, MODE_M = 1, "flee"        # host set_seed before its END TURN -> H flees (Ca, Cb, Cc, Cd; both chains)
TU_H = 58                         # H_NEXT's TU at turn 2 before the Delete (Ca, Cb, Cc, Cd) = HLE.H_TU_FULL
H_NEXT = 10                       # the host's Tab from X after P (Cc, Cd): the first seat-0 live unit after X
HUD_FIELDS = ("tu", "energy", "health", "morale")   # hud == units[] view on all four (Ca, Cb boot; Cc, Cd Tab)
TEXT_NOT_YOURS = "Not one of your soldiers"   # en-US :77 STR_COOP_DENY_NOT_YOUR_UNIT (Ca, Cb: 0.20 s, 1.05 s)
KEY_ZERO = 127                    # Delete: Zero TU (keyBattleZeroTUs)
ZERO_READ_S = 1.0
TEXT_WAIT_S = 8                   # the bounded wait for an empty host coopWaitText before the Delete
FOLLOW_S = HLE.FOLLOW_S           # 5.0
READ_GAP_S = 1.0
STEP_S = G3F.STEP_S
BS_KEYS = ("side", "turn", "selectedId", "currentActionActorId", "cursorType", "cursorVisible", "coopWaitText",
           "warningText", "panicHandled", "hud")
ROWS = (("P", ("P-roll", "P-sel", "P-actor", "P-hud", "P-partner", "P-common")),
        ("Z", ("Z-text", "Z-own", "Z-common")),
        ("M", ("M-roll", "M-own", "M-partner", "M-common")))

es = G3F.es


def boot(host, client):
    """test_w2_turn_cues.boot's chain with this file's lobby key (F10917: copied with the key as a parameter)."""
    bring_up_lobby_roster_pinned(host, client, KEY)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": TCU.SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    fp = [hs.get("mapFingerprint"), cs.get("mapFingerprint")]
    assert fp == [TCU.MAP_FP] * 2, f"mapFingerprint host/client {fp} (want {TCU.MAP_FP} on both)"
    assert seated.get("soldierIds") == SEATED, f"seated {seated.get('soldierIds')} (want {SEATED})"
    order = [[u["id"] for u in hs.get("units", [])], [u["id"] for u in cs.get("units", [])]]
    assert order == [TCU.UNIT_ORDER] * 2, f"unit order host/client {order} (want {TCU.UNIT_ORDER} on both)"
    gm = [hs.get("coopGamemode"), cs.get("coopGamemode")]
    assert gm == [GAMEMODE] * 2, f"coopGamemode host/client {gm} (want {GAMEMODE} on both)"
    pinned = pin_ai_neutral(host, client, tag="w2h40")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (want [{A_ID}])"
    session.wait_host_idle(host, client, timeout=30)
    return {"mapFP": fp, "seated": seated.get("soldierIds"), "pinned": pinned, "gamemode": gm}


def resolved(uid):
    """battle_state predicate: `uid`'s status is out of 8 / 9 (its panic / berserk walk resolved)."""
    return lambda bs: (session.units_by_id(bs).get(uid) or {}).get("status") not in (8, 9)


def view(gc):
    """One battle_state read: BS_KEYS plus H_NEXT's units[] view on HUD_FIELDS (the same response)."""
    b = battle_state(gc)
    v = {k: b.get(k) for k in BS_KEYS}
    u = session.units_by_id(b).get(H_NEXT) or {}
    v["nextUnit"] = {f: u.get(f) for f in HUD_FIELDS}
    return v


def reads(host, client):
    """Two views of both machines READ_GAP_S apart."""
    r1 = {"host": view(host), "client": view(client)}
    time.sleep(READ_GAP_S)
    return [r1, {"host": view(host), "client": view(client)}]


def stm(gc, uid):
    """(status, tu, morale) of `uid` on this machine."""
    u = G3F.units(gc).get(uid) or {}
    return (u.get("status"), u.get("tu"), u.get("morale"))


def tu(gc, uid):
    return (G3F.units(gc).get(uid) or {}).get("tu")


def strip(host, client, uid):
    rc = client.cmd({"cmd": "battle_strip_unit", "unit": uid})   # F607: client first
    rh = host.cmd({"cmd": "battle_strip_unit", "unit": uid})
    assert rc.get("ok") and rh.get("ok") and rc.get("remaining") == 0 == rh.get("remaining"), (
        f"battle_strip_unit {uid}: host {rh} client {rc} (want ok, remaining 0 on both)")
    session.wait_seq_barrier(host, client)
    return {"host": rh.get("deleted"), "client": rc.get("deleted")}


def morale(host, client, uid, v):
    return both(host, client, {"cmd": "battle_set_unit_state", "unit": uid, "morale": v}, ("morale",)).get("morale")


def cycle(host, client, seed, uid, what, ev):
    """TCU.cycle (the client's END TURN, the host's set_seed `seed` right before its own press, the side cycle, both
    NextTurnStates closed, host boxes dismissed host-only, the host settled with `uid` resolved), then the two
    reads. Fills `ev`; returns the reads."""
    ev["seq0"] = es(host, "lastSeqEmitted") or 0
    ev["camBefore"] = HC.cam_offset(HC.cam_snap(host, client)["host"])
    rec = ev["rec"] = {"notes": [], "dismissed": [], "cycles": []}
    TCU.cycle(host, client, seed, rec, what, extra=resolved(uid))
    r = ev["reads"] = reads(host, client)
    ev["camRead2"] = HC.cam_offset(HC.cam_snap(host, client)["host"])
    ev["units"] = {u: [stm(host, u), stm(client, u)] for u in (X, H)}
    ev["stacks"] = [G3F.stack(host), G3F.stack(client)]
    return r


def panic_cell(host, ev, uid, mode, want_turn, at):
    """(side, turn) (0, want_turn) on both at the first read, no cycle note, exactly one host panic ev since seq0 with
    payload {unit uid, mode} and exactly one bt_action_end on its actionId."""
    bad, rec = [], ev["rec"]
    st = [(at["host"]["side"], at["host"]["turn"]), (at["client"]["side"], at["client"]["turn"])]
    if st != [(0, want_turn)] * 2:
        bad.append(f"(side, turn) host/client {st} (want (0, {want_turn}) on both)")
    if rec["notes"]:
        bad.append(f"cycle notes {rec['notes']} (want none)")
    hev = HC.evs_since(host, ev["seq0"])
    ev["hostEvs"] = [(e["seq"], e["kind"], e["actionId"]) for e in hev]
    panics = [(e["seq"], e["actionId"]) for e in hev if e["kind"] == "panic"]
    if len(panics) != 1:
        bad.append(f"host panic evs (seq, actionId) since seq {ev['seq0']}: {panics} (want exactly one)")
    else:
        pl = host_payloads(host, [panics[0][0]], timeout=3)
        payload = (pl.get(panics[0][0]) or {}).get("payload") or {}
        ev["panic"] = payload
        ends = [e["seq"] for e in hev if e["kind"] == "bt_action_end" and e["actionId"] == panics[0][1]]
        if (payload.get("unit"), payload.get("mode")) != (uid, mode):
            bad.append(f"panic payload {payload} (want unit {uid}, mode {mode})")
        if len(ends) != 1:
            bad.append(f"bt_action_end evs of actionId {panics[0][1]}: {ends} (want exactly one)")
    return (not bad, "; ".join(bad) or f"(0, {want_turn}) on both, one panic {{unit {uid}, mode {mode}}} and its "
                                       f"bt_action_end, no cycle note")


def both_reads(r, key, want, red):
    got = [x["host"][key] for x in r]
    return (got == [want, want], f"host {key} at the two reads {got} (want {want} at both; unchanged build: {red})")


def partner_cell(r):
    """The client holds one of its own SEATED soldiers with its action actor equal, at both reads (no id pinned)."""
    ps = [(x["client"]["selectedId"], x["client"]["currentActionActorId"]) for x in r]
    return (all(s in SEATED and a == s for s, a in ps),
            f"client (selectedId, currentActionActorId) at the two reads {ps} (want one of {SEATED}, actor equal)")


# ===================== rows =====================


def row_p(host, client, crash0):
    ev = {}
    r = cycle(host, client, SEED_P, X, "P", ev)
    hud, nxt = r[1]["host"]["hud"] or {}, r[1]["host"]["nextUnit"]
    cmp_ = {f: (hud.get(f), nxt.get(f)) for f in HUD_FIELDS}
    cells = {"P-roll": panic_cell(host, ev, X, MODE_P, 2, r[0]),
             "P-sel": both_reads(r, "selectedId", H_NEXT, f"X {X}, F15450"),
             "P-actor": both_reads(r, "currentActionActorId", H_NEXT, f"X {X}"),
             "P-hud": (all(a == b for a, b in cmp_.values()),
                       f"host hud vs unit {H_NEXT}'s units[] view at the second read {{field: (hud, unit)}} {cmp_} "
                       f"(want equal on {list(HUD_FIELDS)}; unchanged build: X's numbers)"),
             "P-partner": partner_cell(r),
             "P-common": G3F.common(host, client, crash0)}
    return cells, ev


def row_z(host, client, crash0):
    ev = {"textBefore": battle_state(host).get("coopWaitText")}
    ev["textWait"] = PR.wait_until(lambda: battle_state(host).get("coopWaitText") == "", TEXT_WAIT_S, 0.1)
    tu0 = ev["tu0"] = [tu(host, H_NEXT), tu(client, H_NEXT)]
    eh0 = event_state(host)
    seq0 = ev["seq0"] = eh0.get("lastSeqEmitted") or 0
    before = eh0.get("closedContexts") or []
    nh, nc = len(HSE.log_lines(host)), len(HSE.log_lines(client))
    ev["selAtKey"] = battle_state(host).get("selectedId")
    t0 = time.time()
    host.ok({"cmd": "inject_input", "kind": "key", "key": KEY_ZERO})
    time.sleep(max(0.0, t0 + ZERO_READ_S - time.time()))
    b = battle_state(host)
    ev.update(atS=round(time.time() - t0, 2), text=b.get("coopWaitText"), warningText=b.get("warningText"))
    ok, _s = PR.wait_until(lambda: tu(host, H_NEXT) == 0 and tu(client, H_NEXT) == 0,
                           max(0.0, FOLLOW_S - (time.time() - t0)), 0.1)
    ev["tuPoll"] = [ok, round(time.time() - t0, 2), tu(host, H_NEXT), tu(client, H_NEXT)]
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    eh, ec = event_state(host), event_state(client)
    new = ev["new"] = CSH.new_contexts(before, eh.get("closedContexts"))
    hev, cev = HC.evs_since(host, seq0), HC.evs_since(client, seq0)
    clog = HSE.log_lines(client)[nc:]
    ev["hostEvs"] = [(e["seq"], e["kind"], e["actionId"]) for e in hev]
    ev["hostLog"] = [ln.split("\t")[-1] for ln in HSE.log_lines(host)[nh:] if "zero_tu" in ln][:6]
    ev["stack"] = G3F.stack(host)
    fails = HLE.ctx_fails("zero_tu", H_NEXT, ["zero_tu", "bt_action_end"], {"actor": H_NEXT, "unit": H_NEXT}, seq0, new,
                          hev, cev, eh, ec, clog)
    if not ok:
        fails.insert(0, f"unit {H_NEXT} TU host/client {tu0} -> {ev['tuPoll'][2:]} {FOLLOW_S} s after the key "
                        f"(want 0 on both)")
    cells = {"Z-text": (ev["text"] != TEXT_NOT_YOURS,
                        f"host coopWaitText {ev['text']!r} {ev['atS']} s after Delete (want not {TEXT_NOT_YOURS!r}; "
                        f"unchanged build: it, F15452)"),
             "Z-own": (not fails, ("; ".join(fails) + f" (unchanged build: TU {TU_H} unchanged, no new context)")
                       if fails else f"unit {H_NEXT} TU {tu0} -> 0 on both at {ev['tuPoll'][1]} s, one host zero_tu "
                                     f"context, evs [zero_tu, bt_action_end]"),
             "Z-common": G3F.common(host, client, crash0)}
    return cells, ev


def stage_m(host, client):
    m = (host, client)
    st = {"moraleX": G3F.guarded("M staging", lambda: morale(host, client, X, 100), m)}
    st["strip"] = G3F.guarded("M staging", lambda: strip(host, client, H), m)
    st["moraleH"] = G3F.guarded("M staging", lambda: morale(host, client, H, 0), m)
    return st


def row_m(host, client, crash0):
    try:
        ev = {"staging": stage_m(host, client)}
    except G3F.Miss:
        return {n: (False, "staging (see the CAPTURE M staging line)") for n in dict(ROWS)["M"]}, {"error": "staging"}
    r = cycle(host, client, SEED_M, H, "M", ev)
    own = [(x["host"]["selectedId"], x["host"]["currentActionActorId"]) for x in r]
    cells = {"M-roll": panic_cell(host, ev, H, MODE_M, 3, r[0]),
             "M-own": (own == [(H, H)] * 2, f"host (selectedId, currentActionActorId) at the two reads {own} (want "
                                            f"{(H, H)} at both: its own panicked soldier, vanilla)"),
             "M-partner": partner_cell(r),
             "M-common": G3F.common(host, client, crash0)}
    return cells, ev


# ===================== boot C =====================


def stage_c(host, client):
    m = (host, client)
    st = {"hostEntry": {k: battle_state(host).get(k) for k in ("selectedId", "currentActionActorId", "hud")}}
    st["strip"] = G3F.guarded("C staging", lambda: strip(host, client, X), m)
    st["morale"] = G3F.guarded("C staging", lambda: morale(host, client, X, 0), m)
    st["x"] = [stm(host, X), stm(client, X)]
    return st


def boot_c(host, client):
    rows = dict(ROWS)
    try:
        info = G3F.guarded("C", lambda: boot(host, client), (host, client))
    except G3F.Miss:
        return G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE C line)")
    crash0 = session._crash_log_snapshot()
    try:
        st = stage_c(host, client)
    except G3F.Miss:
        st = None
    print(f"EVIDENCE C staging: {json.dumps({'boot': info, 'staging': st}, sort_keys=True, default=str)}", flush=True)
    if st is None:
        return G3F.fail_all(ROWS, "staging (see the CAPTURE C staging line)")
    fails = G3F.run_row("P", rows["P"], lambda: row_p(host, client, crash0))
    fails += G3F.run_row("Z", rows["Z"], lambda: row_z(host, client, crash0))
    fails += G3F.run_row("M", rows["M"], lambda: row_m(host, client, crash0))
    return fails


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir(HOST_DIR))
    client = GameClient("client", None, make_user_dir(CLIENT_DIR))
    try:
        fails = boot_c(host, client)
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_w2_coop_panic_selection: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
