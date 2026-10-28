"""R5-U2 S-B rows HD, HDX (boot B2, gm2: the client plays the aliens, seat 1; the host the seven X-COM soldiers,
seat 0): the alien player's HUD indicators list its own wounded and stunned units and never X-COM's (a click on one
centres the camera on it), and the X-COM host's HUD is unchanged (design-D5, F12882; VL-U2-2).

Spec: docs repo rewrite/prompts/r5u2_pvp_presentation.md section (f) test_pvp_hud.py, with AMENDMENT U2-1 (U2-1.4:
HDX's soldier rule; U2-1.8: the S-B X-COM facings) and the orchestrator rulings (QU2-1 .. QU2-17 (a), QU2-A1-1 ..
QU2-A1-5 (a)). Constants: rewrite/r5u2-task0/sb/CONSTANTS.md (TASK 0 boots Ba2, Bb on the B1 probe build; every pin
equal; boot Ba's RM.TILES facings left A on the host's HUD at HDX, so the U2-1.8 facing rule binds here too, F14810).

Boot B2 (key 48878, dirs r5u2_b2_host / _client): BER.boot_e6 (STR_SMALL_SCOUT, map seed 1, gamemode 2), every live
unit's reactions 0, RM.TILES with every X-COM unit facing FACE_AWAY (A (15,2,0) facing 4 outside each view sector; A
still sees 8, 9, 10, 11), the host's END TURN -> side 1 turn 1 (the client holds A).
  HD  the alien player's HUD lists its own wounded and stunned units, not X-COM's: levers (client first) A and 13
      STAGE_WOUNDS, A and 14 the pinned stun (the smallest stun with stun * 100 / health >= 75 and stun < health); the
      client's TAB to A (one TAB, then tab_select: the HUD refresh)
      HD-pre    the client's selectedId A; hudUnits present; A's and 14's health the pins (precondition)
      HD-own    A in HUD(client)                 (RED on the unchanged product: absent)
      HD-opp    13 and 14 not in HUD(client)     (RED on the unchanged product: present)
      then the levers back to 0 on both (wounds, stun)
  HDX the X-COM host's HUD is unchanged (guard): the client's END TURN -> side 0 turn 2; HDX_SEL = the host's
      selectedId with its screens closed (-1: tab_select(host, 8), U2-1.4); 13 and A STAGE_WOUNDS; the host's TAB to
      HDX_SEL
      HDX-hud   13 in HUD(host), A not; the levers back
HUD(gc) = battle_state(gc).hudUnits.ids (the B1 TEST-ONLY getter: the indicator buttons now shown, in button order).
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane
crash folder.

RED on the unchanged product (commit B1): HD-own, HD-opp; every other cell PASS (HDX is a guard). One EVIDENCE line per
row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step past its bound prints
ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails the rows that need it "staging".
run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_hud.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import session  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
from test_seat_pacing import tab_select, SDLK_TAB  # noqa: E402
from test_client_shoot import both  # noqa: E402
from test_messages import STAGE_WOUNDS  # noqa: E402

KEY = "48878"
A_ID = RM.A_ID                    # the only alien (the client's in gm2, the host's in gm3)
S13_ID, S14_ID = 13, 14           # X-COM soldiers far from A (RM.TILES (33,33,0) / (34,33,0)): the wounded / stunned
XCOM_IDS = [8, 9, 10, 11, 12, 13, 14]
FACE_AWAY = 4                     # U2-1.8: every X-COM unit faces 4 (south); A's tile (and gm3's WP_DEST) lie outside
                                  # each one's view sector, A still sees 8..11 (TASK 0 Ba2 / Bb / Bc2 / Bd)
TILES = {uid: (RM.TILES[uid][0], FACE_AWAY if uid in XCOM_IDS else RM.TILES[uid][1]) for uid in RM.TILES}
HEALTH_A, HEALTH_14 = 30, 39      # health at bring-up (TASK 0, both gm2 boots)
STUN_A, STUN_14 = 23, 30          # the smallest stun with stun * 100 / health >= 75 and stun < health (23*100/30 = 76)
HDX_SEL = 8                       # the host's selectedId at side 0 turn 2 with its screens closed (TASK 0, U2-1.4)
NO_WOUNDS = [0, 0, 0, 0, 0, 0]
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
TAB_S = 0.15
ROWS = (("HD", ("HD-pre", "HD-own", "HD-opp", "HD-common")), ("HDX", ("HDX-hud", "HDX-common")))


# ===================== shared helpers (test_pvp_pace_gm3 imports them) =====================


def hud(gc):
    return battle_state(gc).get("hudUnits")


def hud_ids(gc):
    h = hud(gc)
    return h.get("ids") if isinstance(h, dict) else None


def pace(gc):
    return event_state(gc).get("walkPace") or {}


def pace_delta(w0, w1, uid):
    """WP(gc, uid): the walkPace[uid] counts gained between two reads {animated, instant}."""
    a, b = w0.get(str(uid)) or {}, w1.get(str(uid)) or {}
    return {"animated": (b.get("animated") or 0) - (a.get("animated") or 0),
            "instant": (b.get("instant") or 0) - (a.get("instant") or 0)}


def hu(gc):
    """HU: the union of visibleUnits over gc's live hostile units (the aliens' side's sight on this machine)."""
    s = set()
    for u in G3F.units(gc).values():
        if u.get("faction") == FACTION_HOSTILE and not u.get("isOut"):
            s.update(u.get("visibleUnits") or [])
    return sorted(s)


def uview(gc, ids):
    us = G3F.units(gc)
    return {i: {k: (us.get(i) or {}).get(k) for k in ("x", "y", "z", "direction", "health", "stun", "visible",
                                                   "visibleUnits", "isOut")} for i in ids}


def wounds_both(host, client, uid, w):
    return both(host, client, {"cmd": "battle_set_unit_state", "unit": uid, "fatalWounds": w},
                ("fatalWounds",))["fatalWounds"]


def stun_both(host, client, uid, s):
    return both(host, client, {"cmd": "battle_set_unit_state", "unit": uid, "stun": s}, ("stun",))["stun"]


def tab_to(gc, uid):
    """The real-UI HUD refresh: ONE TAB (updateSoldierInfo runs), then tab_select(uid). Returns evidence."""
    gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
    time.sleep(TAB_S)
    after_tab = battle_state(gc).get("selectedId")
    ok = tab_select(gc, uid)
    return {"afterTab": after_tab, "tabSelect": ok, "sel": battle_state(gc).get("selectedId")}


def levers_back(host, client, ev, wounded=(), stunned=()):
    """Wounds and stun back to 0 on both machines (client first); every lever is tried, failures to `ev`."""
    back = {}
    for uid in wounded:
        try:
            back[f"w{uid}"] = wounds_both(host, client, uid, NO_WOUNDS)
        except Exception as e:
            back[f"w{uid}"] = f"{type(e).__name__}: {str(e)[:200]}"
    for uid in stunned:
        try:
            back[f"s{uid}"] = stun_both(host, client, uid, 0)
        except Exception as e:
            back[f"s{uid}"] = f"{type(e).__name__}: {str(e)[:200]}"
    ev["leversBack"] = back
    return back


def hud_cell(gc, mine, opp, ev, sel):
    """`mine` in HUD(gc) and none of `opp` in it (`mine` None: only `opp` checked; `sel` the unit gc must hold)."""
    ids, s = hud_ids(gc), battle_state(gc).get("selectedId")
    ev[f"hud{gc.name.capitalize()}"] = hud(gc)
    bad = []
    if ids is None:
        bad.append(f"{gc.name} battle_state.hudUnits {hud(gc)!r} (want the B1 probe)")
    else:
        if mine is not None and mine not in ids:
            bad.append(f"{mine} not in HUD({gc.name}) {ids}")
        hit = [u for u in opp if u in ids]
        if hit:
            bad.append(f"{hit} in HUD({gc.name}) {ids} (want absent)")
    if s != sel:
        bad.append(f"{gc.name} selectedId {s} (want {sel})")
    return (not bad, "; ".join(bad) or f"HUD({gc.name}) {ids}: {'' if mine is None else f'{mine} in, '}{opp} not in")


# ===================== rows =====================


def row_hd(host, client, crash0):
    ev, cells = {}, {}
    try:
        ev["levers"] = {"wA": wounds_both(host, client, A_ID, STAGE_WOUNDS),
                        "w13": wounds_both(host, client, S13_ID, STAGE_WOUNDS),
                        "s14": stun_both(host, client, S14_ID, STUN_14), "sA": stun_both(host, client, A_ID, STUN_A)}
        ev["tab"] = tab_to(client, A_ID)
        ev["units"] = uview(client, [A_ID, S13_ID, S14_ID])
        hp = (ev["units"][A_ID]["health"], ev["units"][S14_ID]["health"])
        sel, ids = battle_state(client).get("selectedId"), hud_ids(client)
        cells["HD-pre"] = (sel == A_ID and ids is not None and hp == (HEALTH_A, HEALTH_14),
                           f"client selectedId {sel} (want {A_ID}), hudUnits {hud(client)} (want present), health "
                           f"A/14 {hp} (want {(HEALTH_A, HEALTH_14)})")
        ev["hudClient"], ev["hudHost"] = hud(client), hud(host)
        ids = ids or []
        cells["HD-own"] = (A_ID in ids, f"A ({A_ID}) in HUD(client) {ids}: {A_ID in ids} (want True; wounds "
                                        f"{STAGE_WOUNDS}, stun {STUN_A}/{HEALTH_A})")
        hit = [u for u in (S13_ID, S14_ID) if u in ids]
        cells["HD-opp"] = (not hit, f"HUD(client) {ids}: X-COM's {hit or 'none'} of [13 wounded, 14 stun "
                                    f"{STUN_14}/{HEALTH_14}] listed (want none)")
    finally:
        levers_back(host, client, ev, (A_ID, S13_ID), (S14_ID, A_ID))
    cells["HD-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_hdx(host, client, crash0, side_ok, side_ev):
    ev, cells = {"side": side_ev}, {}
    if not side_ok:
        return {"HDX-hud": (False, f"staging (the client's END TURN -> side 0 turn 2: {side_ev.get('sideError')})"),
                "HDX-common": G3F.common(host, client, crash0)}, ev
    try:
        sel0 = battle_state(host).get("selectedId")
        ev["sel0"] = sel0
        if sel0 == -1:
            ev["fallback"] = tab_select(host, HDX_SEL)   # U2-1.4 item 1
        ev["levers"] = {"w13": wounds_both(host, client, S13_ID, STAGE_WOUNDS),
                        "wA": wounds_both(host, client, A_ID, STAGE_WOUNDS)}
        ev["tab"] = tab_to(host, HDX_SEL)
        ev["units"] = uview(host, [A_ID, HDX_SEL, S13_ID])
        cells["HDX-hud"] = hud_cell(host, S13_ID, (A_ID,), ev, HDX_SEL)
    finally:
        levers_back(host, client, ev, (S13_ID, A_ID))
    cells["HDX-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot B2 =====================


def side_to(host, client, presser, side, turn, ev):
    """presser's END TURN -> (side, turn) on both; True when both got there (else the error in ev)."""
    try:
        RM.side_change(host, client, presser, side, turn, ev)
        return True
    except Exception as e:
        ev["sideError"] = f"{type(e).__name__}: {str(e)[:300]}"
        return False


def stage(host, client):
    """TILES (the U2-1.8 facings) on both (open ground checked), then the host's END TURN -> side 1 turn 1."""
    m = (host, client)
    ev = {"placed": RM.stage_tiles(host, client, TILES, ())}
    side = {}
    G3F.guarded("staging", lambda: RM.side_change(host, client, host, FACTION_HOSTILE, 1, side), m)
    ev.update(side=side, hash=G3F.hash_now(host, client), aSees=(G3F.units(host).get(A_ID) or {}).get("visibleUnits"),
              aVisible=(G3F.units(host).get(A_ID) or {}).get("visible"))
    return ev


def boot_b2():
    host = GameClient("host", None, make_user_dir("r5u2_b2_host"))
    client = GameClient("client", None, make_user_dir("r5u2_b2_client"))
    m = (host, client)
    try:
        try:
            G3F.guarded("B2", lambda: BER.boot_e6(host, client, KEY), m)
            G3F.guarded("B2", lambda: G3F.reactions_zero(host, client), m)
            crash0 = session._crash_log_snapshot()
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE B2 line)")
        try:
            st = stage(host, client)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        print(f"EVIDENCE staging: {st}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("HD", rows["HD"], lambda: row_hd(host, client, crash0))
        side_ev = {}
        side_ok = side_to(host, client, client, FACTION_PLAYER, 2, side_ev)
        fails += G3F.run_row("HDX", rows["HDX"], lambda: row_hdx(host, client, crash0, side_ok, side_ev))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_b2()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_hud: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
