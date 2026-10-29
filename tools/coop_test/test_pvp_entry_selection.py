"""W2-H36 rows S3, I3, V3, H3 (boot E3, gm3: the HOST plays the aliens) and S2, C2 (boot E2, gm2: the client plays the
aliens): at battle start a PvP seat that does not play the first side holds none of the other side's units (design-D6,
QU2-7 (a) = R5-U2's UC5) and gets no "You command no soldiers - spectator mode" notice (R5-V4); the gm3 host's off-turn
screen and refusals then match its later X-COM turns.

Spec: docs repo rewrite/prompts/w2h36_gm3_host_turn1_selection.md section (f), orchestrator rulings QH36-1 .. QH36-5 (a).
Constants: rewrite/w2h36-task0/CONSTANTS.md (TASK 0 boots Ea, Eb (gm3) and Ec, Ed (gm2) on the unchanged build; every pin
equal; VERDICT CONFIRMED).

Boot E3 (key 49034, dirs w2h36_e3_host / _client): G3F.bring_up (the HOST on the Alien team, STR_SMALL_SCOUT, map seed 1).
  S3  the alien host at battle start, read at once, nothing pressed: S3-turn (side, turn) (0, 1) on both; S3-sel host
      selectedId -1; S3-actor host currentActionActorId -1; S3-text host coopWaitText != TEXT_SPECTATOR; S3-partner the
      partner on its own soldier PARTNER_SEL3 without the notice.
  I3  the alien host's keys during X-COM's turn 1 (G3F.reactions_zero first): I3-zero 1.0 s after Delete the host's
      coopWaitText != TEXT_NOT_YOURS; I3-tu X0's TU unchanged on both; I3-keys each of KEYS_OTHER (0.5 s apart) changes
      nothing (host top, host selection, X0's TU / kneeled on both, host closedContexts, partner coopIntentsSent).
  V3  the host's off-turn screen while X0 stands in its alien's sight: RM.stage_tiles (A on (15,2,0) facing south, X0 on
      (15,9,0)), the partner's send_walk(X0, V_DEST), G3F.walk_done. V3-walk one new host context {intent, walk, X0} and X0
      on V_DEST on both; V3-seen X0 in HU; V3-screen host hiddenMovementShown false 0.5 s and 1.5 s after the walk's
      context closed; V3-sel host selectedId -1.
  H3  the partner's END TURN -> side 1 turn 1: H3-own host selectedId A, cursorType 1; the host's END TURN -> side 0 turn
      2: H3-off2 host selectedId -1.
Boot E2 (key 49035, dirs w2h36_e2_host / _client): BER.boot_e6 (gm2).
  S2  the gm2 alien player at battle start, read at once: S2-turn (0, 1) on both; S2-sel client selectedId A; S2-actor
      client currentActionActorId A; S2-text client coopWaitText != TEXT_SPECTATOR; S2-host host on an X-COM soldier
      without the notice.
  C2  the host's END TURN -> side 1 turn 1: C2-own client selectedId A and coopWaitText "".
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane
crash folder. HU = the HOST's union of visibleUnits over the live hostile units (FG3.hu).

RED on the unchanged build (commit A1): S3-sel, S3-text, I3-zero, V3-screen, V3-sel, S2-text, S2-sel, S2-actor (TASK 0:
EN2_SEL 8, ACT2 -1; S3-actor is a guard, ACT3 -1); every other cell PASS. One EVIDENCE line per row, one PASS/FAIL line
per cell, then the row verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and
fails the boot's rows "boot"; a staging step past its bound fails the rows that need it "staging". Lever pairs go to the
client first. run in the foreground to completion. ONE run is the result, no skip
path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_entry_selection.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_pvp_fog_gm3 as FG3  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
from test_client_shoot import new_contexts  # noqa: E402

E3_KEY, E2_KEY = "49034", "49035"
TEXT_SPECTATOR = "You command no soldiers - spectator mode"   # en-US :146 STR_COOP_SPECTATOR_MODE
TEXT_NOT_YOURS = "Not one of your soldiers"                   # en-US :77 STR_COOP_DENY_NOT_YOUR_UNIT
KEY_ZERO = 127                    # Delete: Zero TU (keyBattleZeroTUs)
KEYS_OTHER = (107, 105, 115, 113, 101, 114, 9, 109, 97, 8, 278)   # k i s q e r Tab m a Backspace Home
A_ID = 1000000                    # the only alien (gm3: the host's, seat 0; gm2: the client's, seat 1)
XCOM_IDS = [8, 9, 10, 11, 12, 13, 14]   # the live FACTION_PLAYER units (Ea, Eb, Ec, Ed)
X0 = 8                            # the X-COM unit the gm3 host holds at entry on the unchanged build (Ea, Eb)
ACT3 = -1                         # the gm3 host's action actor at entry (Ea, Eb): S3-actor is a guard
PARTNER_SEL3 = 8                  # the gm3 partner's entry selection (Ea, Eb)
EN2_SEL, ACT2 = 8, -1             # the gm2 client's entry selection / action actor on the unchanged build (Ec, Ed)
V_DEST = (15, 8, 0)               # one tile north of X0's staging tile (15,9,0): open ground on both, in A's sight after the walk
ZERO_READ_S = 1.0                 # TASK 0 DWELL 5.95 s (kCoopBannerDwellMs 6000): the text is up at 1.0 s
KEY_GAP_S = 0.5
SCREEN_READS = (0.5, 1.5)         # V3-screen: seconds after the walk's context closed
STEP_S = G3F.STEP_S
ENTRY_LINE = "[coop-select] entry selection"
E3_ROWS = (("S3", ("S3-turn", "S3-sel", "S3-actor", "S3-text", "S3-partner", "S3-common")),
           ("I3", ("I3-zero", "I3-tu", "I3-keys", "I3-common")),
           ("V3", ("V3-walk", "V3-seen", "V3-screen", "V3-sel", "V3-common")),
           ("H3", ("H3-own", "H3-off2", "H3-common")))
E2_ROWS = (("S2", ("S2-turn", "S2-sel", "S2-actor", "S2-text", "S2-host", "S2-common")),
           ("C2", ("C2-own", "C2-common")))

units, pos, es = G3F.units, G3F.pos, G3F.es


def view(b, keys=("side", "turn", "selectedId", "currentActionActorId", "coopWaitText", "warningText", "cursorType",
                  "cursorVisible", "hiddenMovementShown", "hud")):
    return {k: b.get(k) for k in keys}


def x0_state(host, client):
    """X0's (tu, kneeled) on the host and on the partner."""
    uh, uc = units(host).get(X0) or {}, units(client).get(X0) or {}
    return [(uh.get("tu"), uh.get("kneeled")), (uc.get("tu"), uc.get("kneeled"))]


def wait_until(pred, timeout, interval):
    return BER.wait_until(pred, timeout, interval)


# ===================== boot E3 (gm3) =====================


def row_s3(host, client, crash0):
    bh, bc = battle_state(host), battle_state(client)   # read at once: nothing pressed since the bring-up
    hv, cv = view(bh), view(bc)
    wait_until(lambda: G3F.log_count(host, ENTRY_LINE) >= 1, 3, 0.25)   # bounded log flush (EVIDENCE only)
    ev = {"host": hv, "partner": cv, "HU": FG3.hu(host), "camera": es(host, "camera"),
          "hostEntryLines": [x.split("\t")[-1] for x in G3F.log_lines(host) if ENTRY_LINE in x]}
    ev["hostEntryLineCount"] = len(ev["hostEntryLines"])
    st =[(hv["side"], hv["turn"]), (cv["side"], cv["turn"])]
    cells = {"S3-turn": (st == [(0, 1), (0, 1)], f"(side, turn) host/partner {st} (want (0, 1) on both)"),
             "S3-sel": (hv["selectedId"] == -1, f"host selectedId {hv['selectedId']} (want -1; unchanged build: X0 {X0})"),
             "S3-actor": (hv["currentActionActorId"] == -1,
                          f"host currentActionActorId {hv['currentActionActorId']} (want -1; TASK 0 pin {ACT3})"),
             "S3-text": (hv["coopWaitText"] != TEXT_SPECTATOR,
                         f"host coopWaitText {hv['coopWaitText']!r} (want not {TEXT_SPECTATOR!r})"),
             "S3-partner": (cv["selectedId"] == PARTNER_SEL3 and cv["coopWaitText"] != TEXT_SPECTATOR,
                            f"partner selectedId {cv['selectedId']} (want {PARTNER_SEL3}), coopWaitText "
                            f"{cv['coopWaitText']!r} (want not {TEXT_SPECTATOR!r})"),
             "S3-common": G3F.common(host, client, crash0)}
    return cells, ev


def key_view(host, client):
    return {"top": G3F.top(host), "sel": battle_state(host).get("selectedId"), "x0": x0_state(host, client),
            "ctx": len(es(host, "closedContexts") or []), "sent": es(client, "coopIntentsSent") or {}}


def row_i3(host, client, crash0, staged):
    ev = {"reactions": staged, "tu0": x0_state(host, client), "before": view(battle_state(host))}
    tu0 = ev["tu0"]
    t0 = time.time()
    ev["zeroPress"] = host.cmd({"cmd": "inject_input", "kind": "key", "key": KEY_ZERO}).get("ok")
    time.sleep(max(0.0, t0 + ZERO_READ_S - time.time()))
    b = battle_state(host)
    ev.update(zeroAtS=round(time.time() - t0, 2), zeroWait=b.get("coopWaitText"), zeroWarn=b.get("warningText"))
    tu1 = x0_state(host, client)
    cells = {"I3-zero": (ev["zeroWait"] != TEXT_NOT_YOURS,
                         f"host coopWaitText {ev['zeroWait']!r} {ev['zeroAtS']} s after Delete (want not "
                         f"{TEXT_NOT_YOURS!r})"),
             "I3-tu": ([t[0] for t in tu1] == [t[0] for t in tu0],
                       f"X0 TU host/partner {[t[0] for t in tu0]} -> {[t[0] for t in tu1]} after Delete (want unchanged)")}
    base, bad, keys = key_view(host, client), [], {}
    for key in KEYS_OTHER:
        host.ok({"cmd": "inject_input", "kind": "key", "key": key})
        time.sleep(KEY_GAP_S)
        now = key_view(host, client)
        keys[key] = now
        diff = {k: (base[k], now[k]) for k in base if now[k] != base[k]}
        if now["top"] != "BattlescapeState":
            diff["top"] = (base["top"], now["top"], G3F.stack(host))
        if diff:
            bad.append((key, diff))
    ev.update(keysBase=base, keys=keys)
    cells["I3-keys"] = (not bad, f"keys {list(KEYS_OTHER)}: changes {bad or 'none'} (want none: host top BattlescapeState, "
                                 f"selection, X0 TU / kneeled on both, host contexts, partner intents unchanged)")
    cells["I3-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_v3(host, client, crash0):
    ev = {"HUbefore": FG3.hu(host)}
    ctx0, sent0 = es(host, "closedContexts") or [], dict(es(client, "coopIntentsSent") or {})
    tw = time.time()
    ev["resp"] = session.send_walk(client, X0, V_DEST)
    closed, ev["closeS"] = wait_until(lambda: new_contexts(ctx0, es(host, "closedContexts")), STEP_S, 0.1)
    t_close, reads = time.time(), {}
    for lag in SCREEN_READS:
        time.sleep(max(0.0, t_close + lag - time.time()))
        b = battle_state(host)
        reads[lag] = {"atS": round(time.time() - t_close, 2), "hm": b.get("hiddenMovementShown"),
                      "sel": b.get("selectedId")}
    done = G3F.walk_done(host, client, X0, V_DEST, ev)
    new = new_contexts(ctx0, es(host, "closedContexts"))
    sent = es(client, "coopIntentsSent") or {}
    at, h, bh = [pos(host, X0), pos(client, X0)], FG3.hu(host), battle_state(host)
    ev.update(walkS=round(time.time() - tw, 2), contextClosed=bool(closed), walkDone=done, newCtx=[RM.cv(c) for c in new],
              sent=[sent0, sent], at=at, HU=h, reads=reads, host=view(bh), aView=RM.uv(host, A_ID))
    ok, txt = G3F.ctx_cell(new, "intent", X0)
    cells = {"V3-walk": (ok and closed and at == [V_DEST, V_DEST],
                         f"{txt}; X0 host/partner {at} (want {V_DEST} on both); context closed {bool(closed)} in "
                         f"{ev['closeS']} s"),
             "V3-seen": (X0 in h, f"HU {h} (want X0 {X0} in it)"),
             "V3-screen": (all(r["hm"] is False for r in reads.values()),
                           f"host hiddenMovementShown {[(r['atS'], r['hm']) for r in reads.values()]} s after the walk's "
                           f"context closed (want False at {SCREEN_READS[0]} s and {SCREEN_READS[1]} s)"),
             "V3-sel": (bh.get("selectedId") == -1, f"host selectedId {bh.get('selectedId')} after the walk (want -1)"),
             "V3-common": G3F.common(host, client, crash0)}
    return cells, ev


def row_h3(host, client, crash0):
    ev, cells = {"side1": {}, "side0": {}}, {}
    RM.side_change(host, client, client, G3F.FACTION_HOSTILE, 1, ev["side1"])
    b = battle_state(host)
    ev["own"] = view(b)
    cells["H3-own"] = (b.get("selectedId") == A_ID and b.get("cursorType") == 1,
                       f"at side 1 turn 1 host selectedId {b.get('selectedId')} (want {A_ID}), cursorType "
                       f"{b.get('cursorType')} (want 1)")
    try:
        RM.side_change(host, client, host, G3F.FACTION_PLAYER, 2, ev["side0"])
        b = battle_state(host)
        ev["off2"] = view(b)
        cells["H3-off2"] = (b.get("selectedId") == -1 and (b.get("side"), b.get("turn")) == (0, 2),
                            f"at (side, turn) {(b.get('side'), b.get('turn'))} host selectedId {b.get('selectedId')} "
                            f"(want -1 at (0, 2))")
    except Exception as e:
        cells["H3-off2"] = (False, f"the host's END TURN -> side 0 turn 2 failed: {type(e).__name__}: {str(e)[:300]}")
    cells["H3-common"] = G3F.common(host, client, crash0)
    return cells, ev


def boot_e3():
    host = GameClient("host", None, make_user_dir("w2h36_e3_host"))
    client = GameClient("client", None, make_user_dir("w2h36_e3_client"))
    m, rows = (host, client), dict(E3_ROWS)
    try:
        try:
            boot, crash0 = G3F.bring_up(host, client, E3_KEY, "E3")
        except G3F.Miss:
            return G3F.fail_all(E3_ROWS, "boot (setup failure, see the CAPTURE E3 line)")
        fails = G3F.run_row("S3", rows["S3"], lambda: row_s3(host, client, crash0))
        try:
            staged = G3F.guarded("E3 staging", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            staged = None
        fails += (G3F.run_row("I3", rows["I3"], lambda: row_i3(host, client, crash0, staged)) if staged
                  else G3F.fail_all((("I3", rows["I3"]),), "staging (see the CAPTURE E3 staging line)"))
        try:
            placed = RM.stage_tiles(host, client, {A_ID: RM.TILES[A_ID], X0: RM.TILES[8]}, [V_DEST]) if staged else None
        except G3F.Miss:
            placed = None
        print(f"EVIDENCE E3 staging: {json.dumps({'boot': boot, 'placed': placed}, sort_keys=True, default=str)}",
              flush=True)
        fails += (G3F.run_row("V3", rows["V3"], lambda: row_v3(host, client, crash0)) if placed
                  else G3F.fail_all((("V3", rows["V3"]),), "staging (see the CAPTURE staging line)"))
        fails += G3F.run_row("H3", rows["H3"], lambda: row_h3(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


# ===================== boot E2 (gm2) =====================


def row_s2(host, client, crash0):
    bh, bc = battle_state(host), battle_state(client)   # read at once: nothing pressed since the bring-up
    hv, cv = view(bh), view(bc)
    ev = {"client": cv, "host": hv, "camera": es(client, "camera")}
    st = [(hv["side"], hv["turn"]), (cv["side"], cv["turn"])]
    cells = {"S2-turn": (st == [(0, 1), (0, 1)], f"(side, turn) host/client {st} (want (0, 1) on both)"),
             "S2-sel": (cv["selectedId"] == A_ID,
                        f"client selectedId {cv['selectedId']} (want {A_ID}; unchanged build: {EN2_SEL})"),
             "S2-actor": (cv["currentActionActorId"] == A_ID,
                          f"client currentActionActorId {cv['currentActionActorId']} (want {A_ID}; unchanged build: "
                          f"{ACT2})"),
             "S2-text": (cv["coopWaitText"] != TEXT_SPECTATOR,
                         f"client coopWaitText {cv['coopWaitText']!r} (want not {TEXT_SPECTATOR!r})"),
             "S2-host": (hv["selectedId"] in XCOM_IDS and hv["coopWaitText"] != TEXT_SPECTATOR,
                         f"host selectedId {hv['selectedId']} (want one of {XCOM_IDS}), coopWaitText "
                         f"{hv['coopWaitText']!r} (want not {TEXT_SPECTATOR!r})"),
             "S2-common": G3F.common(host, client, crash0)}
    return cells, ev


def row_c2(host, client, crash0):
    ev = {"side": {}}
    RM.side_change(host, client, host, G3F.FACTION_HOSTILE, 1, ev["side"])
    b = battle_state(client)
    ev.update(client=view(b), host=view(battle_state(host)))
    return {"C2-own": (b.get("selectedId") == A_ID and b.get("coopWaitText") == "",
                       f"at side 1 turn 1 client selectedId {b.get('selectedId')} (want {A_ID}), coopWaitText "
                       f"{b.get('coopWaitText')!r} (want '')"),
            "C2-common": G3F.common(host, client, crash0)}, ev


def boot_e2():
    host = GameClient("host", None, make_user_dir("w2h36_e2_host"))
    client = GameClient("client", None, make_user_dir("w2h36_e2_client"))
    rows = dict(E2_ROWS)
    try:
        try:
            info = G3F.guarded("E2", lambda: BER.boot_e6(host, client, E2_KEY), (host, client))
        except G3F.Miss:
            return G3F.fail_all(E2_ROWS, "boot (setup failure, see the CAPTURE E2 line)")
        crash0 = session._crash_log_snapshot()
        fails = G3F.run_row("S2", rows["S2"], lambda: row_s2(host, client, crash0))
        print(f"EVIDENCE E2 boot: {json.dumps(info, sort_keys=True, default=str)}", flush=True)
        fails += G3F.run_row("C2", rows["C2"], lambda: row_c2(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_e3()
    fails += boot_e2()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_entry_selection: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
