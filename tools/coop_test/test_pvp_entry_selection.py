"""PvP entry selection: at battle start a PvP seat that does not play the first side holds none of the other side's
units and gets no "You command no soldiers - spectator mode" notice; the gm3 host's off-turn screen and refusals then
match its later X-COM turns. Two boots: gm3 (the HOST plays the aliens) and gm2 (the client plays the aliens). The
unit ids below were measured on two boots of each mode without the fix, equal on all of them.

Boot gm3 (key 49034, dirs pvp_entry_selection_gm3_host / _client): G3F.bring_up (the HOST on the Alien team,
STR_SMALL_SCOUT, map seed 1).
  host_alien_entry  the alien host at battle start, read at once, nothing pressed: host_alien_entry-turn (side, turn)
      (0, 1) on both; host_alien_entry-sel host selectedId -1; host_alien_entry-actor host currentActionActorId -1;
      host_alien_entry-text host coopWaitText != TEXT_SPECTATOR; host_alien_entry-partner the partner on its own
      soldier PARTNER_ENTRY_SEL without the notice.
  host_offturn_keys  the alien host's keys during X-COM's turn 1 (G3F.reactions_zero first): host_offturn_keys-zero
      1.0 s after Delete the host's coopWaitText != TEXT_NOT_YOURS; host_offturn_keys-tu X0's TU unchanged on both;
      host_offturn_keys-keys each of KEYS_OTHER (0.5 s apart) changes nothing (host top, host selection, X0's TU /
      kneeled on both, host closedContexts, partner coopIntentsSent).
  host_offturn_screen  the host's off-turn screen while X0 stands in its alien's sight: RM.stage_tiles (A on (15,2,0)
      facing south, X0 on (15,9,0)), the partner's send_walk(X0, WALK_DEST), G3F.walk_done. host_offturn_screen-walk one
      new host context {intent, walk, X0} and X0 on WALK_DEST on both; host_offturn_screen-seen X0 in HU;
      host_offturn_screen-screen host hiddenMovementShown false 0.5 s and 1.5 s after the walk's context closed;
      host_offturn_screen-sel host selectedId -1.
  host_own_turn  the partner's END TURN -> side 1 turn 1: host_own_turn-own host selectedId A, cursorType 1; the
      host's END TURN -> side 0 turn 2: host_own_turn-off2 host selectedId -1.
Boot gm2 (key 49035, dirs pvp_entry_selection_gm2_host / _client): BER.boot_pvp (gm2).
  client_alien_entry  the gm2 alien player at battle start, read at once: client_alien_entry-turn (0, 1) on both;
      client_alien_entry-sel client selectedId A; client_alien_entry-actor client currentActionActorId A;
      client_alien_entry-text client coopWaitText != TEXT_SPECTATOR; client_alien_entry-host host on an X-COM soldier
      without the notice.
  client_own_turn  the host's END TURN -> side 1 turn 1: client_own_turn-own client selectedId A and coopWaitText "".
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in this
harness slot's crash folder. HU = the HOST's union of visibleUnits over the live hostile units (FG3.hu).

Without the fix, host_alien_entry-sel, host_alien_entry-text, host_offturn_keys-zero, host_offturn_screen-screen,
host_offturn_screen-sel, client_alien_entry-text, client_alien_entry-sel and client_alien_entry-actor FAIL (the gm2
client enters on CLIENT_SEL_WITHOUT_FIX 8 with action actor CLIENT_ACT_WITHOUT_FIX -1; host_alien_entry-actor is a
guard: HOST_ACT_WITHOUT_FIX is -1 too); every other cell passes. One EVIDENCE line per row, one PASS/FAIL line per
cell, then the row verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and
fails the boot's rows "boot"; a staging step past its bound fails the rows that need it "staging". Test-command pairs
go to the client first. ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

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

GM3_KEY, GM2_KEY = "49034", "49035"
TEXT_SPECTATOR = "You command no soldiers - spectator mode"   # en-US :146 STR_COOP_SPECTATOR_MODE
TEXT_NOT_YOURS = "Not one of your soldiers"                   # en-US :77 STR_COOP_DENY_NOT_YOUR_UNIT
KEY_ZERO = 127                    # Delete: Zero TU (keyBattleZeroTUs)
KEYS_OTHER = (107, 105, 115, 113, 101, 114, 9, 109, 97, 8, 278)   # k i s q e r Tab m a Backspace Home
A_ID = 1000000                    # the only alien (gm3: the host's, seat 0; gm2: the client's, seat 1)
XCOM_IDS = [8, 9, 10, 11, 12, 13, 14]   # the live FACTION_PLAYER units
X0 = 8                            # the X-COM unit the gm3 host held at entry without the fix
HOST_ACT_WITHOUT_FIX = -1         # the gm3 host's action actor at entry: host_alien_entry-actor is a guard
PARTNER_ENTRY_SEL = 8             # the gm3 partner's entry selection
# the gm2 client's entry selection / action actor without the fix
CLIENT_SEL_WITHOUT_FIX, CLIENT_ACT_WITHOUT_FIX = 8, -1
# one tile north of X0's staging tile (15,9,0): open ground on both, in A's sight after the walk
WALK_DEST = (15, 8, 0)
ZERO_READ_S = 1.0                 # the text stays up 5.95 s (kCoopBannerDwellMs 6000): it is up at 1.0 s
KEY_GAP_S = 0.5
SCREEN_READS = (0.5, 1.5)         # host_offturn_screen-screen: seconds after the walk's context closed
STEP_S = G3F.STEP_S
ENTRY_LINE = "[coop-select] entry selection"
GM3_ROWS = (("host_alien_entry", ("host_alien_entry-turn", "host_alien_entry-sel", "host_alien_entry-actor",
                                  "host_alien_entry-text", "host_alien_entry-partner", "host_alien_entry-common")),
            ("host_offturn_keys", ("host_offturn_keys-zero", "host_offturn_keys-tu", "host_offturn_keys-keys",
                                   "host_offturn_keys-common")),
            ("host_offturn_screen", ("host_offturn_screen-walk", "host_offturn_screen-seen",
                                     "host_offturn_screen-screen", "host_offturn_screen-sel",
                                     "host_offturn_screen-common")),
            ("host_own_turn", ("host_own_turn-own", "host_own_turn-off2", "host_own_turn-common")))
GM2_ROWS = (("client_alien_entry", ("client_alien_entry-turn", "client_alien_entry-sel", "client_alien_entry-actor",
                                    "client_alien_entry-text", "client_alien_entry-host", "client_alien_entry-common")),
            ("client_own_turn", ("client_own_turn-own", "client_own_turn-common")))

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


# ===================== boot gm3 =====================


def row_host_alien_entry(host, client, crash0):
    bh, bc = battle_state(host), battle_state(client)   # read at once: nothing pressed since the bring-up
    hv, cv = view(bh), view(bc)
    wait_until(lambda: G3F.log_count(host, ENTRY_LINE) >= 1, 3, 0.25)   # bounded log flush (EVIDENCE only)
    ev = {"host": hv, "partner": cv, "HU": FG3.hu(host), "camera": es(host, "camera"),
          "hostEntryLines": [x.split("\t")[-1] for x in G3F.log_lines(host) if ENTRY_LINE in x]}
    ev["hostEntryLineCount"] = len(ev["hostEntryLines"])
    st =[(hv["side"], hv["turn"]), (cv["side"], cv["turn"])]
    cells = {"host_alien_entry-turn": (st == [(0, 1), (0, 1)],
                                       f"(side, turn) host/partner {st} (want (0, 1) on both)"),
             "host_alien_entry-sel": (hv["selectedId"] == -1,
                                      f"host selectedId {hv['selectedId']} (want -1; without the fix: X0 {X0})"),
             "host_alien_entry-actor": (hv["currentActionActorId"] == -1,
                                        f"host currentActionActorId {hv['currentActionActorId']} (want -1; without the "
                                        f"fix: {HOST_ACT_WITHOUT_FIX})"),
             "host_alien_entry-text": (hv["coopWaitText"] != TEXT_SPECTATOR,
                                       f"host coopWaitText {hv['coopWaitText']!r} (want not {TEXT_SPECTATOR!r})"),
             "host_alien_entry-partner": (cv["selectedId"] == PARTNER_ENTRY_SEL
                                          and cv["coopWaitText"] != TEXT_SPECTATOR,
                                          f"partner selectedId {cv['selectedId']} (want {PARTNER_ENTRY_SEL}), "
                                          f"coopWaitText {cv['coopWaitText']!r} (want not {TEXT_SPECTATOR!r})"),
             "host_alien_entry-common": G3F.common(host, client, crash0)}
    return cells, ev


def key_view(host, client):
    return {"top": G3F.top(host), "sel": battle_state(host).get("selectedId"), "x0": x0_state(host, client),
            "ctx": len(es(host, "closedContexts") or []), "sent": es(client, "coopIntentsSent") or {}}


def row_host_offturn_keys(host, client, crash0, staged):
    ev = {"reactions": staged, "tu0": x0_state(host, client), "before": view(battle_state(host))}
    tu0 = ev["tu0"]
    t0 = time.time()
    ev["zeroPress"] = host.cmd({"cmd": "inject_input", "kind": "key", "key": KEY_ZERO}).get("ok")
    time.sleep(max(0.0, t0 + ZERO_READ_S - time.time()))
    b = battle_state(host)
    ev.update(zeroAtS=round(time.time() - t0, 2), zeroWait=b.get("coopWaitText"), zeroWarn=b.get("warningText"))
    tu1 = x0_state(host, client)
    cells = {"host_offturn_keys-zero": (ev["zeroWait"] != TEXT_NOT_YOURS,
                                        f"host coopWaitText {ev['zeroWait']!r} {ev['zeroAtS']} s after Delete "
                                        f"(want not {TEXT_NOT_YOURS!r})"),
             "host_offturn_keys-tu": ([t[0] for t in tu1] == [t[0] for t in tu0],
                                      f"X0 TU host/partner {[t[0] for t in tu0]} -> {[t[0] for t in tu1]} after Delete "
                                      f"(want unchanged)")}
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
    cells["host_offturn_keys-keys"] = (not bad, f"keys {list(KEYS_OTHER)}: changes {bad or 'none'} (want none: "
                                                f"host top BattlescapeState, selection, X0 TU / kneeled on both, host "
                                                f"contexts, partner intents unchanged)")
    cells["host_offturn_keys-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_host_offturn_screen(host, client, crash0):
    ev = {"HUbefore": FG3.hu(host)}
    ctx0, sent0 = es(host, "closedContexts") or [], dict(es(client, "coopIntentsSent") or {})
    tw = time.time()
    ev["resp"] = session.send_walk(client, X0, WALK_DEST)
    closed, ev["closeS"] = wait_until(lambda: new_contexts(ctx0, es(host, "closedContexts")), STEP_S, 0.1)
    t_close, reads = time.time(), {}
    for lag in SCREEN_READS:
        time.sleep(max(0.0, t_close + lag - time.time()))
        b = battle_state(host)
        reads[lag] = {"atS": round(time.time() - t_close, 2), "hm": b.get("hiddenMovementShown"),
                      "sel": b.get("selectedId")}
    done = G3F.walk_done(host, client, X0, WALK_DEST, ev)
    new = new_contexts(ctx0, es(host, "closedContexts"))
    sent = es(client, "coopIntentsSent") or {}
    at, h, bh = [pos(host, X0), pos(client, X0)], FG3.hu(host), battle_state(host)
    ev.update(walkS=round(time.time() - tw, 2), contextClosed=bool(closed), walkDone=done, newCtx=[RM.cv(c) for c in new],
              sent=[sent0, sent], at=at, HU=h, reads=reads, host=view(bh), aView=RM.uv(host, A_ID))
    ok, txt = G3F.ctx_cell(new, "intent", X0)
    cells = {"host_offturn_screen-walk": (ok and closed and at == [WALK_DEST, WALK_DEST],
                                          f"{txt}; X0 host/partner {at} (want {WALK_DEST} on both); context closed "
                                          f"{bool(closed)} in {ev['closeS']} s"),
             "host_offturn_screen-seen": (X0 in h, f"HU {h} (want X0 {X0} in it)"),
             "host_offturn_screen-screen": (all(r["hm"] is False for r in reads.values()),
                                            f"host hiddenMovementShown {[(r['atS'], r['hm']) for r in reads.values()]} "
                                            f"s after the walk's context closed (want False at {SCREEN_READS[0]} s and "
                                            f"{SCREEN_READS[1]} s)"),
             "host_offturn_screen-sel": (bh.get("selectedId") == -1,
                                         f"host selectedId {bh.get('selectedId')} after the walk (want -1)"),
             "host_offturn_screen-common": G3F.common(host, client, crash0)}
    return cells, ev


def row_host_own_turn(host, client, crash0):
    ev, cells = {"side1": {}, "side0": {}}, {}
    RM.side_change(host, client, client, G3F.FACTION_HOSTILE, 1, ev["side1"])
    b = battle_state(host)
    ev["own"] = view(b)
    cells["host_own_turn-own"] = (b.get("selectedId") == A_ID and b.get("cursorType") == 1,
                                  f"at side 1 turn 1 host selectedId {b.get('selectedId')} (want {A_ID}), cursorType "
                                  f"{b.get('cursorType')} (want 1)")
    try:
        RM.side_change(host, client, host, G3F.FACTION_PLAYER, 2, ev["side0"])
        b = battle_state(host)
        ev["off2"] = view(b)
        cells["host_own_turn-off2"] = (b.get("selectedId") == -1 and (b.get("side"), b.get("turn")) == (0, 2),
                                       f"at (side, turn) {(b.get('side'), b.get('turn'))} host selectedId "
                                       f"{b.get('selectedId')} (want -1 at (0, 2))")
    except Exception as e:
        cells["host_own_turn-off2"] = (False, f"the host's END TURN -> side 0 turn 2 failed: {type(e).__name__}: "
                                              f"{str(e)[:300]}")
    cells["host_own_turn-common"] = G3F.common(host, client, crash0)
    return cells, ev


def boot_gm3():
    host = GameClient("host", None, make_user_dir("pvp_entry_selection_gm3_host"))
    client = GameClient("client", None, make_user_dir("pvp_entry_selection_gm3_client"))
    m, rows = (host, client), dict(GM3_ROWS)
    try:
        try:
            boot, crash0 = G3F.bring_up(host, client, GM3_KEY, "gm3")
        except G3F.Miss:
            return G3F.fail_all(GM3_ROWS, "boot (setup failure, see the CAPTURE gm3 line)")
        fails = G3F.run_row("host_alien_entry", rows["host_alien_entry"],
                            lambda: row_host_alien_entry(host, client, crash0))
        try:
            staged = G3F.guarded("gm3 staging", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            staged = None
        fails += (G3F.run_row("host_offturn_keys", rows["host_offturn_keys"],
                              lambda: row_host_offturn_keys(host, client, crash0, staged)) if staged
                  else G3F.fail_all((("host_offturn_keys", rows["host_offturn_keys"]),),
                                    "staging (see the CAPTURE gm3 staging line)"))
        try:
            placed = (RM.stage_tiles(host, client, {A_ID: RM.TILES[A_ID], X0: RM.TILES[8]}, [WALK_DEST]) if staged
                      else None)
        except G3F.Miss:
            placed = None
        print(f"EVIDENCE gm3 staging: {json.dumps({'boot': boot, 'placed': placed}, sort_keys=True, default=str)}",
              flush=True)
        fails += (G3F.run_row("host_offturn_screen", rows["host_offturn_screen"],
                              lambda: row_host_offturn_screen(host, client, crash0)) if placed
                  else G3F.fail_all((("host_offturn_screen", rows["host_offturn_screen"]),),
                                    "staging (see the CAPTURE staging line)"))
        fails += G3F.run_row("host_own_turn", rows["host_own_turn"], lambda: row_host_own_turn(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


# ===================== boot gm2 =====================


def row_client_alien_entry(host, client, crash0):
    bh, bc = battle_state(host), battle_state(client)   # read at once: nothing pressed since the bring-up
    hv, cv = view(bh), view(bc)
    ev = {"client": cv, "host": hv, "camera": es(client, "camera")}
    st = [(hv["side"], hv["turn"]), (cv["side"], cv["turn"])]
    cells = {"client_alien_entry-turn": (st == [(0, 1), (0, 1)],
                                         f"(side, turn) host/client {st} (want (0, 1) on both)"),
             "client_alien_entry-sel": (cv["selectedId"] == A_ID,
                                        f"client selectedId {cv['selectedId']} (want {A_ID}; without the fix: "
                                        f"{CLIENT_SEL_WITHOUT_FIX})"),
             "client_alien_entry-actor": (cv["currentActionActorId"] == A_ID,
                                          f"client currentActionActorId {cv['currentActionActorId']} (want {A_ID}; "
                                          f"without the fix: {CLIENT_ACT_WITHOUT_FIX})"),
             "client_alien_entry-text": (cv["coopWaitText"] != TEXT_SPECTATOR,
                                         f"client coopWaitText {cv['coopWaitText']!r} (want not {TEXT_SPECTATOR!r})"),
             "client_alien_entry-host": (hv["selectedId"] in XCOM_IDS and hv["coopWaitText"] != TEXT_SPECTATOR,
                                         f"host selectedId {hv['selectedId']} (want one of {XCOM_IDS}), coopWaitText "
                                         f"{hv['coopWaitText']!r} (want not {TEXT_SPECTATOR!r})"),
             "client_alien_entry-common": G3F.common(host, client, crash0)}
    return cells, ev


def row_client_own_turn(host, client, crash0):
    ev = {"side": {}}
    RM.side_change(host, client, host, G3F.FACTION_HOSTILE, 1, ev["side"])
    b = battle_state(client)
    ev.update(client=view(b), host=view(battle_state(host)))
    return {"client_own_turn-own": (b.get("selectedId") == A_ID and b.get("coopWaitText") == "",
                                    f"at side 1 turn 1 client selectedId {b.get('selectedId')} (want {A_ID}), "
                                    f"coopWaitText {b.get('coopWaitText')!r} (want '')"),
            "client_own_turn-common": G3F.common(host, client, crash0)}, ev


def boot_gm2():
    host = GameClient("host", None, make_user_dir("pvp_entry_selection_gm2_host"))
    client = GameClient("client", None, make_user_dir("pvp_entry_selection_gm2_client"))
    rows = dict(GM2_ROWS)
    try:
        try:
            info = G3F.guarded("gm2", lambda: BER.boot_pvp(host, client, GM2_KEY), (host, client))
        except G3F.Miss:
            return G3F.fail_all(GM2_ROWS, "boot (setup failure, see the CAPTURE gm2 line)")
        crash0 = session._crash_log_snapshot()
        fails = G3F.run_row("client_alien_entry", rows["client_alien_entry"],
                            lambda: row_client_alien_entry(host, client, crash0))
        print(f"EVIDENCE gm2 boot: {json.dumps(info, sort_keys=True, default=str)}", flush=True)
        fails += G3F.run_row("client_own_turn", rows["client_own_turn"],
                             lambda: row_client_own_turn(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_gm3()
    fails += boot_gm2()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_entry_selection: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
