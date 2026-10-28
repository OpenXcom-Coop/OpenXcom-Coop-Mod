"""R5-U1 S-A rows F6, F1, F2, F3, F5, F4 (boot A2, gm2: the client plays the aliens, seat 1; the host the seven X-COM
soldiers, seat 0): the PvP alien seat draws, on its map and minimap, only its own units and the X-COM soldiers its side
sees now (owner PvP model "fog is per side", R5-V3; QU1-1 (a)), and its psi targeting reads the same sight.

Spec: docs repo rewrite/prompts/r5u1_pvp_fog_camera.md section (f) test_pvp_fog.py, with the orchestrator rulings
AMENDMENT U1-1 (the plan review's A-1 .. A-8; here A-2: F5 is a PANIC, F4's D), R-U1-SA-1 (W_OUT) and AMENDMENT U1-2
(F5 re-staged with a second alien B made by R5-U4's conversion lever; DF-U1-2-1: F4-agree is red at A1).
Constants: rewrite/r5u1-task0/sa/CONSTANTS.md (TASK 0 boots Aa, Ab and the U1-2 re-measure boots Ae, Af; pins equal).

Boot A2 (key 48916, dirs r5u1_a2_host / _client): BER.boot_e6 (STR_SMALL_SCOUT, map seed 1, gamemode 2), every live
unit's reactions 0, RM.TILES with W (12) on W_OUT facing W_DIR (FLOOR_B also checked open ground), the settle cycle
(host END TURN, client END TURN -> side 0 turn 2). Host orders are real-UI (tab_select, RM.host_walk); client orders
are intents. VH(gc, id) = battle_state(gc).units[id].visibleHere (what that machine's map and minimap draw a unit by,
the T1 probe); HU = the HOST's union of visibleUnits over the live hostile units; X-COM ids = the live FACTION_PLAYER
units at the read.
  F6  an unseen X-COM soldier's walk does not move the alien player's camera: client camera staged on A (level 0); the
      host's real-UI walk of 13 to U_DEST. F6-walk, F6-cam (no walker_centre for 13 since the press, offset x / y ==
      staged), F6-hide (VH(client, 13) false).
  F1  the alien player does not draw X-COM soldiers its side does not see (side 0 turn 2), read right after F6:
      F1-pre (HU == SEEN0, U0), F1-hide (VH(client, id) false for U0), F1-show (true for A and SEEN0), F1-host (on the
      host visibleHere == visible for every unit).
  F5 staging (1) (U1-2): 13's rifle and TU T13, 14's spawn staging (STR_SECTOID_SOLDIER, faction 1), host set_seed
      SEED_B, the host-local lever snap of 13 at FLOOR_B converts 14 into B (alien side, seat 1, blind), B reactions 0.
      One EVIDENCE line; a failure FAILs F5 "staging" only.
  F2  an X-COM soldier the aliens come to see is drawn: the host's real-UI walk of W to W_IN. F2-walk, F2-pre (W in
      HU), F2-show (VH(client, W) true), F2-agree (every X-COM id: VH(client, id) == id in HU).
  F3  and hidden once it leaves their sight: the host's real-UI walk of 11 to S4_OUT. F3-walk, F3-pre (11 not in HU),
      F3-hide (VH(client, 11) false).
  F5  the alien player psi-attacks, with an alien that does not see it, the soldier only its other alien saw walk in:
      host END TURN -> side 1 turn 2 (the client's side_begin selects B); the amp on B, B psiSkill
      100, W psiStrength 0, B's TU. F5-pre (B from one spawn {B, convert, from 14} on B_TILE facing B_DIR; W in HU and
      in A's host list, in neither B list; the client's selectedId == B), F5-ui (the client's real-UI PANIC by B on W:
      the right-hand box, PSI_ROWS rows, KEY_PANIC, HC.stage_camera(client, W_IN) in HOME's place, host set_seed
      SEED_F5, one click; one new host context {intent, psi, B}, coopIntentsSent.psi +1, its psi cue {actor B, unit W,
      action panic} applied on the client, W faction 0 on both). From F2 to the press nothing TABs, tab_selects or
      click-selects on the client and no client inventory opens (U1-2.1 W1-W8).
      W2-U9 re-point: since W2-H41 S-B (7eb33ec00; QH41-2 (a), QH41-3 (a), R-LH40-1) the gm2 client's
      side_begin selects its FIRST alien A (vanilla's other-side rule), not B. F5-pre now reads the side-start
      selection == A, then ONE real-UI tab_select(client, B) on the client (the single exception to the rule above;
      U1-2.1 W2: it refreshes only B, the unit the ActionMenuState close refreshes anyway, W1), and checks the client's
      selectedId == B and W in neither B list AFTER that TAB. Every other F5 check is unchanged.
  F4  the aliens' own turn hides what they stop seeing: A's TU; the client's battle_intent turn of A to dir 0
      (RM.turn_order). F4-turn, F4-pre (D = (HU before - HU after) & X-COM ids non-empty), F4-hide (VH(client, id)
      false for every id in D and every X-COM id not in HU), F4-agree (every live unit: VH(client, id) == own faction
      or id in HU). F4 is the last row.
Common cell (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane crash folder.
Admitted orders: exactly one new host closedContexts entry {origin, kind, actorId}; an intent's coopIntentsSent +1.
RED at A1 per (f) as U1-2 amends it: F6-cam, F1-hide, F2-agree, F3-hide, F5-ui, F4-hide, F4-agree; every other cell
PASS. One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A
boot step past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails the
rows that need it "staging". Lever pairs go to the client first; ids come from lever replies and probes (S25).
run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_fog.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_host_combat as HC  # noqa: E402
import test_ownerless_units as OU  # noqa: E402
from test_seat_pacing import tab_select  # noqa: E402
from test_turn_baton import RHAND_NTH, click_nth  # noqa: E402
from test_client_shoot import set_tu_both, RHAND_CENTRE  # noqa: E402
from test_host_combat import evs_since  # noqa: E402
from test_ai_origins import host_payloads  # noqa: E402

KEY = "48916"
A_ID = RM.A_ID                    # 1000000: the alien of boot_e6 (STR_SECTOID_SOLDIER), the client's seat 1
W_ID, S4_ID, U_ID = 12, 11, 13    # the walker W, S4 (F3), the unseen walker (F6)
A_TILE = RM.TILES[A_ID][0]        # (15,2,0) facing 4: sees 8, 9, 10, 11
W_OUT, W_DIR = (19, 2, 0), 6      # open ground, A inside W's sector, W outside A's
W_IN = (17, 5, 0)                 # inside A's view sector and LOS
S4_OUT = (24, 8, 0)               # outside A's view sector
U_DEST = (30, 33, 0)              # out of A's sight on 13's whole path
TILES = dict(RM.TILES)
TILES[W_ID] = (W_OUT, W_DIR)
SEEN0, U0 = [8, 9, 10, 11], [12, 13, 14]   # HU and the unseen X-COM ids after the settle cycle and F6 (Aa, Ab, Ae, Af)
SHOOTER_B, VICTIM_B, B_TYPE = 13, 14, "STR_SECTOID_SOLDIER"   # U1-2: B is A's type (the amp menu measured)
FLOOR_B = (34, 37, 0)             # R5-U4's FLOOR rule from 13 on U_DEST: k 4, d 3 on both censuses (Ae, Af)
SEED_B = 1                        # host set_seed right before the conversion shot
T13 = 61                          # 13's TU at bring-up (Ae, Af)
B_TILE, B_DIR = (34, 33, 0), 0    # 14's tile and facing; convertUnit keeps both (Ae, Af)
A_TU = 54                         # A's and B's TU (STR_SECTOID_SOLDIER)
SEED_F5 = 1
KEY_PANIC, CT_PSI, PSI_ROWS = 50, 3, 3   # the amp's PANIC key, its cursor, the amp's menu rows
CURSOR_TARGETING = RM.CURSOR_TARGETING
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
WANT_B = {"type": B_TYPE, "faction": FACTION_HOSTILE, "coop": 1, "x": B_TILE[0], "y": B_TILE[1], "z": B_TILE[2],
          "direction": B_DIR}
ROWS = (("F6", ("F6-walk", "F6-cam", "F6-hide", "F6-common")),
        ("F1", ("F1-pre", "F1-hide", "F1-show", "F1-host", "F1-common")),
        ("F2", ("F2-walk", "F2-pre", "F2-show", "F2-agree", "F2-common")),
        ("F3", ("F3-walk", "F3-pre", "F3-hide", "F3-common")),
        ("F5", ("F5-pre", "F5-ui", "F5-common")),
        ("F4", ("F4-turn", "F4-pre", "F4-hide", "F4-agree", "F4-common")))

units, pos, es, ctxs, cv = G3F.units, G3F.pos, RM.es, RM.ctxs, RM.cv


# ===================== probes =====================


def vh(gc, uid):
    return (units(gc).get(uid) or {}).get("visibleHere")


def vis(gc, uid):
    return list((units(gc).get(uid) or {}).get("visibleUnits") or [])


def hu(host):
    """The HOST's union of visibleUnits over the live hostile units (the side's sight as the host holds it)."""
    s = set()
    for u in units(host).values():
        if u.get("faction") == FACTION_HOSTILE and not u.get("isOut"):
            s.update(u.get("visibleUnits") or [])
    return sorted(s)


def xcom_ids(gc):
    return sorted(i for i, u in units(gc).items() if u.get("faction") == FACTION_PLAYER and not u.get("isOut"))


def sight(gc):
    return {i: [u.get("visible"), u.get("visibleHere"), u.get("visibleUnits")] for i, u in sorted(units(gc).items())}


def lists(host, client, b):
    return {"hostA": vis(host, A_ID), "clientA": vis(client, A_ID),
            "hostB": vis(host, b) if b else None, "clientB": vis(client, b) if b else None}


def vh_false(gc, ids):
    """(ok, {id: VH}) - VH(gc, id) is False for every id."""
    got = {i: vh(gc, i) for i in ids}
    return all(v is False for v in got.values()), got


def sent_delta(client, sent0, kind):
    return (es(client, "coopIntentsSent") or {}).get(kind, 0) - (sent0 or {}).get(kind, 0)


def host_walk(host, client, uid, dest, ev):
    """The host's real-UI walk of `uid` (tab_select, then RM.host_walk's click); returns (new contexts, seq0)."""
    ev["tab"] = tab_select(host, uid)
    seq0 = es(host, "lastSeqEmitted") or 0
    try:
        new = RM.host_walk(host, client, uid, dest, ev)
    except Exception as e:
        new, ev["walkError"] = [], str(e)[:300]
    ev.update(newCtx=[cv(c) for c in new], at=[pos(host, uid), pos(client, uid)])
    return new, seq0


# ===================== rows =====================


def row_f6(host, client, crash0):
    ev, cells = {}, {}
    ev["staged"] = HC.cam_offset(HC.stage_camera(client, A_TILE))
    new, seq0 = host_walk(host, client, U_ID, U_DEST, ev)
    cam = HC.camera_of(client)
    wc = [m for m in HC.cam_moves(cam, seq0) if m.get("reason") == "walker_centre" and m.get("unit") == U_ID]
    off = HC.cam_offset(cam)
    ev.update(camera=HC.cam_view(cam, seq0), u13=[{k: (units(gc).get(U_ID) or {}).get(k) for k in
                                                  ("visible", "visibleHere", "visibleUnits")} for gc in (host, client)])
    ok, txt = OU.ctx_cell(new, "host", "walk", U_ID)
    cells["F6-walk"] = (ok and ev["at"] == [U_DEST, U_DEST],
                        f"{txt}; 13 host/client {ev['at']} (want {U_DEST} on both)")
    st = ev["staged"]
    cells["F6-cam"] = (not wc and off is not None and st is not None and off[:2] == st[:2],
                       f"client walker_centre records for 13 since seq {seq0}: {wc} (want none); client offset {off} "
                       f"(want x / y == staged {st})")
    v = vh(client, U_ID)
    cells["F6-hide"] = (v is False, f"VH(client, 13) {v} (want False)")
    cells["F6-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_f1(host, client, crash0):
    cells = {}
    h, xc = hu(host), xcom_ids(host)
    u0 = [i for i in xc if i not in h]
    ev = {"HU": h, "U0": u0, "xcom": xc, "sightHost": sight(host), "sightClient": sight(client)}
    cells["F1-pre"] = (h == SEEN0 and u0 == U0, f"HU {h} (want {SEEN0}); U0 {u0} (want {U0})")
    ok, got = vh_false(client, U0)
    cells["F1-hide"] = (ok, f"VH(client, id) for U0: {got} (want False for each)")
    shows = {i: vh(client, i) for i in [A_ID] + SEEN0}
    cells["F1-show"] = (all(v is True for v in shows.values()), f"VH(client, id) for A and SEEN0: {shows} (want True)")
    diff = {i: [u.get("visible"), u.get("visibleHere")] for i, u in units(host).items()
            if u.get("visibleHere") != u.get("visible")}
    cells["F1-host"] = (not diff, f"host units with visibleHere != visible: {diff} (want none)")
    cells["F1-common"] = G3F.common(host, client, crash0)
    return cells, ev


def stage_b(host, client, crash0):
    """F5 staging (1) (U1-2.3 (3b) (a)-(e)): returns {B, new, spawns}; B is None when it failed (F5 FAILs "staging")."""
    ev, m = {}, (host, client)
    out = {"B": None, "new": [], "spawns": []}
    try:
        g = OU.give(host, client, SHOOTER_B, "STR_RIFLE", "STR_RIFLE_CLIP")
        ev["rifle"] = (g.get("weaponId"), g.get("ammoId"))
        ev["tu13"] = set_tu_both(host, client, SHOOTER_B, T13)
        sp = OU.spawn_staging(host, client, VICTIM_B, B_TYPE, FACTION_HOSTILE)
        ev["spawnStaging"] = {k: sp.get(k) for k in ("spawnUnit", "spawnUnitFaction", "respawn")}
        cvev = {}
        b, new, spawns = OU.convert(host, client, SHOOTER_B, FLOOR_B, SEED_B, cvev)
        ev.update(convert={k: v for k, v in cvev.items() if k != "newCtx"}, newCtx=[cv(c) for c in new], B=b)
        out.update(new=new, spawns=spawns)
        if b is None:
            raise AssertionError(f"the conversion added host/client {cvev.get('added')} (want one new unit, equal)")
        RM.stat_both(host, client, b, "reactions", 0)
        ev["reactionsB"] = [(units(gc).get(b) or {}).get("reactions") for gc in m]
        ev.update(Bfields=[{k: (units(gc).get(b) or {}).get(k) for k in tuple(WANT_B) + ("hasAI", "tu", "visibleUnits")}
                           for gc in m], clientA=vis(client, A_ID), clientTop=G3F.top(client),
                  hostSel=battle_state(host).get("selectedId"), hostCursor=battle_state(host).get("cursorType"),
                  clientSel=battle_state(client).get("selectedId"), common=G3F.common(host, client, crash0))
        out["B"] = b
    except Exception as e:
        ev["error"] = f"{type(e).__name__}: {str(e)[:400]}"
        G3F.capture("F5 staging", ev["error"], m)
    print(f"EVIDENCE F5-staging: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    return out


def row_f2(host, client, crash0, b):
    ev, cells = {}, {}
    new, _seq0 = host_walk(host, client, W_ID, W_IN, ev)
    h, xc = hu(host), xcom_ids(host)
    ev.update(HU=h, xcom=xc, lists=lists(host, client, b), sightClient=sight(client),
              restate=[(es(gc, "lastWalk") or {}).get("restate") for gc in (host, client)])
    cells["F2-walk"] = OU.ctx_cell(new, "host", "walk", W_ID)
    cells["F2-pre"] = (W_ID in h, f"HU {h} (want W {W_ID} in it)")
    v = vh(client, W_ID)
    cells["F2-show"] = (v is True, f"VH(client, W) {v} (want True)")
    bad = {i: [vh(client, i), i in h] for i in xc if vh(client, i) != (i in h)}
    cells["F2-agree"] = (not bad, f"X-COM ids {xc} with VH(client, id) != (id in HU {h}): {bad} (want none)")
    cells["F2-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_f3(host, client, crash0, b):
    ev, cells = {}, {}
    new, _seq0 = host_walk(host, client, S4_ID, S4_OUT, ev)
    h = hu(host)
    ev.update(HU=h, lists=lists(host, client, b), u11=[vh(host, S4_ID), vh(client, S4_ID)])
    cells["F3-walk"] = OU.ctx_cell(new, "host", "walk", S4_ID)
    cells["F3-pre"] = (S4_ID not in h, f"HU {h} (want 11 not in it)")
    v = vh(client, S4_ID)
    cells["F3-hide"] = (v is False, f"VH(client, 11) {v} (want False)")
    cells["F3-common"] = G3F.common(host, client, crash0)
    return cells, ev


def press_panic(client, host, ev):
    """RM.psi_press copied with the action key and the camera as parameters (F10917; U1-2.3 (7)): the client's selected
    unit's right-hand box (self-verified), PSI_ROWS rows, KEY_PANIC -> CT_PSI, HC.stage_camera(client, W_IN) in HOME's
    place, one self-verified click on W_IN with the host's set_seed SEED_F5 right before it. Never TABs or selects."""
    if battle_state(client).get("cursorType") in CURSOR_TARGETING:
        click_nth(client, RHAND_NTH)
    r = click_nth(client, RHAND_NTH)
    ev["rhand"] = (r.get("baseX"), r.get("baseY"))
    assert ev["rhand"] == RHAND_CENTRE, f"right-hand click on the client landed off the box: {r}"
    ok, _s = RM.wait_until(lambda: G3F.top(client) == "ActionMenuState", 5, 0.1)
    assert ok, f"no ActionMenuState on the client (stack {G3F.stack(client)})"
    ev["rows"] = len([w for w in client.cmd({"cmd": "list_widgets"}).get("widgets", [])
                      if w.get("visible") and "ActionMenuItem" in w.get("type", "")])
    assert ev["rows"] == PSI_ROWS, f"action menu rows {ev['rows']} (want {PSI_ROWS})"
    client.ok({"cmd": "inject_input", "kind": "key", "key": KEY_PANIC})
    RM.wait_until(lambda: G3F.top(client) != "ActionMenuState", 5, 0.1)
    ev["cursorAfterKey"] = battle_state(client).get("cursorType")
    assert ev["cursorAfterKey"] == CT_PSI, f"key {KEY_PANIC}: cursorType {ev['cursorAfterKey']} (want {CT_PSI})"
    ev["cam"] = HC.cam_offset(HC.stage_camera(client, W_IN))
    pr = client.cmd({"cmd": "map_tile_click_pos", "x": W_IN[0], "y": W_IN[1], "z": W_IN[2]})
    ev["clickPos"] = (pr.get("winX"), pr.get("winY"), pr.get("verified"))
    assert pr.get("verified"), f"map_tile_click_pos {W_IN} on the client not verified: {pr}"
    ev["selAtClick"] = battle_state(client).get("selectedId")
    host.ok({"cmd": "set_seed", "seed": SEED_F5})
    client.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})


def row_f5(host, client, crash0, sb):
    ev, cells = {}, {}
    order = dict(ROWS)["F5"]
    side = ev["side"] = {}
    RM.side_change(host, client, host, FACTION_HOSTILE, 2, side)
    b = sb["B"]
    if b is None:
        return {n: (False, "staging (F5 staging (1) failed: see EVIDENCE F5-staging)") for n in order}, ev
    amp = RM.give_both(host, client, b, RM.PSI_AMP)["weaponId"]
    RM.stat_both(host, client, b, "psiSkill", 100)
    RM.stat_both(host, client, W_ID, "psiStrength", 0)
    ev["bTu"] = set_tu_both(host, client, b, A_TU)
    # the side start selects the first alien A; one real-UI TAB then selects B.
    sel0 = ev["sideStartSel"] = battle_state(client).get("selectedId")
    ev["tabB"] = tab_select(client, b) if sel0 == A_ID else None
    h, ls, sel = hu(host), lists(host, client, b), battle_state(client).get("selectedId")
    ev.update(amp=amp, HU=h, lists=ls, clientSel=sel, wTile=pos(host, W_ID))
    sp_ok, sp_txt = OU.spawn_cell(sb["new"], SHOOTER_B, sb["spawns"], b, VICTIM_B, host, client, WANT_B)
    bad = [] if sp_ok else [sp_txt]
    if W_ID not in h or W_ID not in ls["hostA"]:
        bad.append(f"HU {h}, A's host visibleUnits {ls['hostA']} (want W {W_ID} in both)")
    if W_ID in ls["hostB"] or W_ID in ls["clientB"]:
        bad.append(f"B's visibleUnits host/client {ls['hostB']} / {ls['clientB']} (want W in neither)")
    if sel0 != A_ID:
        bad.append(f"the client's side-start selectedId {sel0} (want the first alien A {A_ID}, QH41-2 (a))")
    if sel != b:
        bad.append(f"the client's selectedId {sel} after one tab_select (want B {b})")
    cells["F5-pre"] = (not bad, "; ".join(bad) or f"{sp_txt}; W in HU and A's host list, in neither B list; the "
                                                  f"client's selectedId {sel}")
    ui = ev["ui"] = {}
    if sel != b:
        cells["F5-ui"] = (False, f"not reached (the client's selectedId {sel}, want B {b}; the press never selects)")
    else:
        ctx0, sent0 = ctxs(host), dict(es(client, "coopIntentsSent") or {})
        seq0 = es(host, "lastSeqEmitted") or 0
        try:
            press_panic(client, host, ui)
        except Exception as e:
            ui["pressError"] = str(e)[:300]
        ui["listsAtClick"] = lists(host, client, b)
        new = RM.mc_order(host, client, ctx0, W_ID, ui)
        c1 = battle_state(client).get("cursorType")
        if c1 in CURSOR_TARGETING and ui["clientMap"][0]:
            click_nth(client, RHAND_NTH)   # cancel the client's leftover targeting (TASK 0: 3 -> 1)
        sent = sent_delta(client, sent0, "psi")
        hev = evs_since(host, seq0)
        aid = new[0].get("actionId") if len(new) == 1 else None
        psis = [e["seq"] for e in hev if e["kind"] == "psi" and e["actionId"] == aid]
        pl = host_payloads(host, psis, timeout=3) if psis else {}
        cues = [(s, {k: (v.get("payload") or {}).get(k) for k in ("actor", "unit", "action", "success")})
                for s, v in sorted(pl.items())]
        capplied = {e["seq"] for e in evs_since(client, seq0)}
        wf = [(units(gc).get(W_ID) or {}).get("faction") for gc in (host, client)]
        ui.update(cancel=[c1, battle_state(client).get("cursorType")], sent=sent, cues=cues, wFaction=wf,
                  hostEvs=[(e["seq"], e["kind"], e["actionId"]) for e in hev],
                  warningText=battle_state(client).get("warningText"))
        ubad = []
        if ui.get("pressError"):
            ubad.append(f"press: {ui['pressError']}")
        if not RM.ctx_ok(new, "intent", "psi", b):
            ubad.append(f"new host contexts {[cv(c) for c in new]} (want exactly one {{intent, psi, {b}}})")
        if sent != 1:
            ubad.append(f"client coopIntentsSent.psi +{sent} (want +1)")
        want_cue = {"actor": b, "unit": W_ID, "action": "panic"}
        if len(cues) != 1 or {k: cues[0][1].get(k) for k in want_cue} != want_cue or cues[0][0] not in capplied:
            ubad.append(f"psi cues {cues} (want one {want_cue}, applied on the client)")
        if wf != [FACTION_PLAYER, FACTION_PLAYER]:
            ubad.append(f"W faction host/client {wf} (want 0 on both)")
        if not ui["clientMap"][0]:
            ubad.append(f"the client's battle map not back on top within {RM.CLIENT_MAP_S} s: {ui['clientMap'][2]}")
        cells["F5-ui"] = (not ubad, "; ".join(ubad) or f"one {{intent, psi, {b}}}; psi +1; cue {cues}; W faction 0")
    cells["F5-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_f4(host, client, crash0, b):
    ev, cells = {}, {}
    ev["aTu"] = set_tu_both(host, client, A_ID, A_TU)
    h0, xc0 = hu(host), xcom_ids(host)
    sent0 = dict(es(client, "coopIntentsSent") or {})
    tnew, deny = RM.turn_order(host, client, A_ID, 0, ev)
    h1, xc = hu(host), xcom_ids(host)
    d = sorted((set(h0) - set(h1)) & set(xc0))
    dirs = [(units(gc).get(A_ID) or {}).get("direction") for gc in (host, client)]
    sent = sent_delta(client, sent0, "turn")
    ev.update(HUbefore=h0, HUafter=h1, xcom=xc, D=d, dirs=dirs, lists=lists(host, client, b), sightClient=sight(client))
    cells["F4-turn"] = (RM.ctx_ok(tnew, "intent", "turn", A_ID) and sent == 1 and dirs == [0, 0],
                        f"new host contexts {[cv(c) for c in tnew]} (want one {{intent, turn, {A_ID}}}), deny {deny}; "
                        f"client coopIntentsSent.turn +{sent} (want +1); A direction host/client {dirs} (want 0)")
    cells["F4-pre"] = (bool(d), f"D = (HU before {h0} - HU after {h1}) & X-COM ids {xc0} = {d} (want non-empty)")
    hide = sorted(set(d) | {i for i in xc if i not in h1})
    ok, got = vh_false(client, hide)
    cells["F4-hide"] = (ok, f"VH(client, id) for D and every X-COM id not in HU: {got} (want False for each)")
    live = {i: u for i, u in units(host).items() if not u.get("isOut")}
    bad = {i: [vh(client, i), u.get("faction")] for i, u in live.items()
           if vh(client, i) != (u.get("faction") == FACTION_HOSTILE or i in h1)}
    cells["F4-agree"] = (not bad, f"live units with VH(client, id) != (own faction or id in HU {h1}): {bad} "
                                  f"(want none)")
    cells["F4-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot A2 =====================


def stage(host, client):
    m, ev = (host, client), {}
    ev["placed"] = RM.stage_tiles(host, client, TILES, (W_IN, S4_OUT, U_DEST, FLOOR_B))
    sv = ev["settle"] = {}
    G3F.guarded("staging", lambda: RM.side_change(host, client, host, FACTION_HOSTILE, 1, sv.setdefault("a", {})), m)
    G3F.guarded("staging", lambda: RM.side_change(host, client, client, FACTION_PLAYER, 2, sv.setdefault("b", {})), m)
    ev["hash"] = G3F.hash_now(host, client)
    return ev


def boot_a2():
    host = GameClient("host", None, make_user_dir("r5u1_a2_host"))
    client = GameClient("client", None, make_user_dir("r5u1_a2_client"))
    m = (host, client)
    try:
        try:
            G3F.guarded("A2", lambda: BER.boot_e6(host, client, KEY), m)
            crash0 = session._crash_log_snapshot()
            G3F.guarded("A2", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE A2 line)")
        try:
            st = stage(host, client)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        print(f"EVIDENCE staging: {json.dumps(st, sort_keys=True, default=str)}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("F6", rows["F6"], lambda: row_f6(host, client, crash0))
        fails += G3F.run_row("F1", rows["F1"], lambda: row_f1(host, client, crash0))
        sb = stage_b(host, client, crash0)
        b = sb["B"]
        fails += G3F.run_row("F2", rows["F2"], lambda: row_f2(host, client, crash0, b))
        fails += G3F.run_row("F3", rows["F3"], lambda: row_f3(host, client, crash0, b))
        fails += G3F.run_row("F5", rows["F5"], lambda: row_f5(host, client, crash0, sb))
        fails += G3F.run_row("F4", rows["F4"], lambda: row_f4(host, client, crash0, b))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_a2()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_fog: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
