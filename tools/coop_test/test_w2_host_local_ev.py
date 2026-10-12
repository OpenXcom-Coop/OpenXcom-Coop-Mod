"""W2-H30 - the host's own presses that change the battle on the host only reach the second player in one host
action (spec docs rewrite/prompts/w2h30_host_local_actions.md (f); TASK 0 docs rewrite/w2h30-task0/sa/CONSTANTS.md and
rewrite/w2h30-task0/sb/CONSTANTS.md; W2-H28 QH-4 (a); F12351, F12352, F12353, F12354, F12355, F11564). Before the fix
the HOST's own mind probe (L-1), its Zero TU key (L-4), the last charge of its single-use medi-kit (L-2: the emptied
kit leaves only at the screen's close) and its instant-grenade skill (L-5: the fuse write after the skill's context
closed) change the battle on the host only and emit nothing, so the second player keeps the old value (and hash_now
differs) until the host's next ev of any kind, which carries the change (the -next cells).
ONE boot, test_w2_client_grenade's recipe (the roster-pinned terror map, SEED_MAP 1, the Coop_Spray_Test MOD on both,
coopGhostStepper true), lobby key 48856; rows in this order:
  HS0  bring-up: HS0-mod (MOD line, 0 [ERROR] lines), HS0-units (H, A, C on both), HS0-common.
  HP   the host's mind probe (stage H on PROBE_H_TILE with the probe, A on A_TILE made visible by the lever; TAB to H,
       the right-hand box, key 49, HOME, one click on A): HP-press (UnitInfoState, H TU H_TU_FULL - PROBE_TU, key 27
       closes it), HP-ev (one {host, mindprobe, H} context whose evs are exactly [mindprobe, bt_action_end], lastCue
       {actor H, unit A, item} on both, a clean client log), HP-follow (the client's H TU equals the host's within
       FOLLOW_S), HP-hash, HP-common, HP-next (the client's lever turn of C heals the window).
  HZ   the host's Zero TU key (TAB to H, key 127): HZ-press (host H TU 0), HZ-ev ({host, zero_tu, H}, evs [zero_tu,
       bt_action_end], payload {actor H, unit H}), HZ-follow (client H TU 0 within FOLLOW_S), HZ-hash, HZ-common,
       HZ-next.
  HK   the host's single-use kit (P wounded on P_TILE, the tile H faces; ONE_CHARGE in H's right hand; TAB to H, the
       right-hand box, key 49, key 51 heals, key 27 closes): HK-open (MedikitState, charges [0, 1, 0] on both), HK-use
       (one {host, medikit, H} context, evs [medikit, bt_action_end], P's wounds and H's TU on both), HK-inctx (the
       emptied kit gone on both before the close), HK-close (the close and the BA_USE aftermath emit nothing: L-3),
       HK-follow (the kit gone on both within FOLLOW_S of the close), HK-hash, HK-common, HK-next (the kit's presence).
  HG   the host's instant-grenade skill, LAST (GRENADE in H's hand; TAB to H, SKILLS by SKILLS_RECT, key 51, then one
       right-hand click cancels the throw): HG-press (throw targeting, the host's grenade (0, true), the cancel), HG-ev
       ({host, skill, H} then {host, prime, H}, the prime context's evs [prime, bt_action_end], lastCue {actor H,
       unit H, item g, fuse 0, unprime false}), HG-follow (the client's grenade (0, true) within FOLLOW_S), HG-hash,
       HG-common.
Common cell: after wait_host_idle, test_w2_client_shoot.common_fails minus its hash entry and no crash file since the
boot; the -hash cell is that entry. RED (commit A1, unchanged build): exactly HP-ev, HP-follow, HP-hash, HZ-ev,
HZ-follow, HZ-hash FAIL. GREEN (A2): the 15 S-A cells PASS. RED (commit B1, S-A's green build): exactly HK-inctx,
HK-follow, HK-hash, HG-ev, HG-follow, HG-hash FAIL. GREEN (B2): all 28 cells PASS.
Each row prints ONE "EVIDENCE <row>:" line, one PASS/FAIL line per cell, then its verdict; every row runs after a
failure. A boot failure prints ONE "CAPTURE boot:" line and fails every row "boot"; a missed construction step
prints ONE "CAPTURE <row>:" line and fails that row's cells.
WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path; exit 0 only when every cell passes, 2 otherwise.
Run:  python tools/coop_test/test_w2_host_local_ev.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral
import test_w2_client_grenade as CGR
from test_w2_client_shoot import (snap, press, menu_rows, new_contexts, mine, place, set_tu_both, give_both,
                                  send_intent, top, units, TU_MAX)
from test_w2_delta_core import both, short, diff_buckets
from test_w2_host_combat import bring_up_lobby_roster_pinned, evs_since
from test_w2_host_skill_ev import log_lines, capture, common, joined, pairs
from test_w2_client_melee_psi import visible
from test_rw_turn_baton import RHAND_NTH, RHAND_RECT, click_nth
from test_rw_seat_pacing import tab_select, SDLK_HOME
from test_w2_client_items import items_of, charges, wounds_both
from test_w2_delta_items import items_by_id
from test_w2_host_skill_ev import skills_nth, SKILLS_RECT

PORT = "48856"
HOST_DIR, CLIENT_DIR = "w2h30_host_local_host", "w2h30_host_local_client"
H_ID, C_ID, A_ID = 10, 8, 1000000
SEATED = [8, 9]
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
PROBE_H_TILE, PROBE_H_DIR = (12, 26, 0), 0
A_TILE, A_DIR = (12, 23, 0), 4            # CMP C23d's tiles
MIND_PROBE = "STR_MIND_PROBE"
H_TU_FULL = 58                            # CONSTANTS.md: H 10's max TU (Sa, Sb)
PROBE_TU = 29                             # CONSTANTS.md: the probe's 50 % of 58 (Sa, Sb)
PROBE_ROWS = 2                            # THROW + USE MIND PROBE
KEY_ITEM1, KEY_CANCEL, KEY_ZERO_TU = 49, 27, 127
CURSOR_PSI = 3
RHAND_CENTRE = (RHAND_RECT[0] + RHAND_RECT[2] // 2, RHAND_RECT[1] + RHAND_RECT[3] // 2)
SCRIPT_S = 2.0
FOLLOW_S = 5.0
MENU_S = 5.0
POLL_S = 0.1
HASH_FAIL = "hash_now full not clean"
CELLS = {"HS0": ("HS0-mod", "HS0-units", "HS0-common"),
         "HP": ("HP-press", "HP-ev", "HP-follow", "HP-hash", "HP-common", "HP-next"),
         "HZ": ("HZ-press", "HZ-ev", "HZ-follow", "HZ-hash", "HZ-common", "HZ-next"),
         "HK": ("HK-open", "HK-use", "HK-inctx", "HK-close", "HK-follow", "HK-hash", "HK-common", "HK-next"),
         "HG": ("HG-press", "HG-ev", "HG-follow", "HG-hash", "HG-common")}
# S-B rows HK, HG (docs rewrite/w2h30-task0/sb/CONSTANTS.md: boots Ka and Kb)
P_ID = 11                                 # CONSTANTS.md: the second host-seat soldier (Ka, Kb)
P_TILE, P_DIR = (12, 25, 0), 4            # the tile H faces from PROBE_H_TILE (direction 0)
ONE_CHARGE = "STR_MEDI_KIT_ONE_CHARGE"    # the Spray MOD: consumable, 0 / 1 / 0, full screen
GRENADE = "STR_GRENADE"
WOUNDS, WOUNDS_HEALED = [0, 0, 2, 0, 0, 0], [0, 0, 1, 0, 0, 0]
CHARGES_FULL = [0, 1, 0]
KIT_TU = 10                               # the Spray MOD: tuUse 10, flatRate
KIT_ROWS, SKILL_ROWS = 2, 3               # THROW + USE MEDI-KIT; the MOD's three soldier skills
KEY_HEAL = 51                             # MedikitState's heal key
KEY_SKILL_GRENADE = 51                    # the third skill row: STR_COOP_TEST_SKILL_GRENADE
CURSOR_THROW = 5
FUSE_OFF, FUSE_INSTANT = (-1, False), (0, True)


def tu(gc, uid):
    return (units(gc).get(uid) or {}).get("tu")


def wait_top(gc, state):
    try:
        gc.wait_for(f"{gc.name} {state} on top", lambda: top(gc) == state or None, timeout=MENU_S, interval=POLL_S)
        return True
    except Exception:
        return False


def ctx_fails(kind, actor, want_evs, want_p, seq0, new, hev, cev, eh, ec, clog):
    """The host-context cell: exactly one new {host, kind, actor} context (endSeq > 0, hasFinal true), its evs
    exactly `want_evs`, lastCue {kind, its actionId, want_p} on the host and the same kind at that seq on the client,
    the client applied the host's seqs, no RW-UNSUPPORTED / "has no known actor" client line."""
    f, ctx = [], mine(new, "host", kind, actor)
    if len(new) != 1 or len(ctx) != 1:
        f.append(f"new host closedContexts {new} (want exactly one {{origin host, kind {kind}, actorId {actor}}})")
    else:
        c, aid = ctx[0], ctx[0].get("actionId")
        if not (c.get("endSeq") or 0) > 0 or c.get("hasFinal") is not True:
            f.append(f"context {c} (want endSeq > 0 and hasFinal true)")
        mine_evs = [e for e in hev if e["actionId"] == aid]
        if [e["kind"] for e in mine_evs] != want_evs:
            f.append(f"host evs of actionId {aid} since seq {seq0}: {mine_evs} (want exactly {want_evs})")
        lc = eh.get("lastCue") or {}
        if lc.get("kind") != kind or lc.get("actionId") != aid or lc.get("payload") != want_p:
            f.append(f"host lastCue {lc} (want kind {kind}, actionId {aid}, payload {want_p})")
        cmap = {e["seq"]: e["kind"] for e in cev}
        if not hev or any(cmap.get(e["seq"]) != e["kind"] for e in hev):
            f.append(f"client evs since seq {seq0}: {cev} (want the host's seqs {hev} applied)")
        cue_seq, clc = next((e["seq"] for e in mine_evs if e["kind"] == kind), None), ec.get("lastCue") or {}
        if clc.get("kind") != kind or clc.get("seq") != cue_seq:
            f.append(f"client lastCue {clc} (want kind {kind} at seq {cue_seq})")
    bad = [ln for ln in clog if "RW-UNSUPPORTED" in ln or "has no known actor" in ln]
    if bad:
        f.append(f"client log since the press: {bad[:3]}")
    return f


def follow_tu(host, client, t0, want):
    """Poll (nothing else ordered) until the client's H TU equals the host's or FOLLOW_S after t0."""
    while True:
        th, tc = tu(host, H_ID), tu(client, H_ID)
        if th == tc:
            return {"t": round(time.time() - t0, 2), "host": th, "client": tc}, (
                None if th == want else f"H TU host {th} client {tc} (want {want} on both)")
        if time.time() - t0 >= FOLLOW_S:
            return {"t": None, "host": th, "client": tc}, (
                f"client H TU {tc}, host {th} {FOLLOW_S} s after the press (want equal, {want})")
        time.sleep(POLL_S)


def after(ev, res, rid, kind, want_evs, want_p, host, client, before, seq0, nh, nc, st):
    """The -ev, -hash and -common cells of a host-context row, and its EVIDENCE fields."""
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        ev["idle"] = short(e)
    eh, ec = event_state(host), event_state(client)
    new = new_contexts(before["host"]["closedContexts"], eh.get("closedContexts"))
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    hlog, clog = log_lines(host)[nh:], log_lines(client)[nc:]
    ev.update({"newCtx": new, "hostEvs": hev, "clientEvs": cev, "hostLastCue": eh.get("lastCue"),
               "clientLastCue": ec.get("lastCue")})
    res[f"{rid}-ev"] = joined(ctx_fails(kind, H_ID, want_evs, want_p, seq0, new, hev, cev, eh, ec, clog))
    fails = common(host, client, before, rid, st["crash0"])   # the common cell, split
    res[f"{rid}-hash"] = joined([x for x in fails if x.startswith(HASH_FAIL)])
    res[f"{rid}-common"] = joined([x for x in fails if not x.startswith(HASH_FAIL)])
    ev["after"] = {"hostLastSeqEmitted": eh.get("lastSeqEmitted"), "clientLastSeqApplied": ec.get("lastSeqApplied"),
                   "tu": {n: tu(gc, H_ID) for n, gc in pairs(host, client)},
                   "cue": {n: (e.get("cueCounts") or {}).get(kind) for n, e in (("host", eh), ("client", ec))},
                   "hostContextsOpenedHost": (eh.get("contextsOpened") or {}).get("host"),
                   "diff": diff_buckets(host, client),
                   "hostLog": [ln.split("\t")[-1] for ln in hlog
                               if f"[coop-ctx] host {kind} context" in ln or f"[coop-cue] {kind}" in ln]}


def heal(ev, host, client):
    """<row>-next: ONE heal order, the client's lever turn of C by one octant (F11564); answer `end`, buckets equal,
    desyncSeen false on both, H's TU equal on both."""
    d = (units(host).get(C_ID) or {}).get("direction")
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    notes = []
    out = send_intent(host, client, {"cmd": "battle_intent", "kind": "turn", "actor": C_ID, "toDir": (d + 1) % 8},
                      notes)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    dsc = {n: event_state(gc).get("desyncSeen") for n, gc in pairs(host, client)}
    sub, diff = {n: tu(gc, H_ID) for n, gc in pairs(host, client)}, diff_buckets(host, client)
    ev["next"] = {"cDir": d, "answer": out["answer"], "iseq": out["iseq"], "subjectTu": sub, "diff": diff,
                  "desyncSeen": dsc, "hostEvs": [(e["seq"], e["kind"], e["actionId"]) for e in evs_since(host, seq0)]}
    f = list(notes)
    if out["answer"] != "end":
        f.append(f"heal order answer {out['answer']} (resp {out['resp']}; want end)")
    if diff:
        f.append(f"buckets differ after the heal order: {diff}")
    if dsc["host"] or dsc["client"]:
        f.append(f"desyncSeen {dsc} (want false on both)")
    if sub["host"] != sub["client"]:
        f.append(f"H TU host {sub['host']} client {sub['client']} after the heal order (want equal)")
    return joined(f)


def boot(host, client):   # test_w2_client_grenade.boot() with lobby key PORT
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=CGR.MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": CGR.SEED_MAP}))
    ml = {gc.name: CGR.mod_log(gc) for gc in (host, client)}
    for name, m in ml.items():
        assert CGR.MOD_ACTIVE_LINE in (m.get("active") or []) and not m.get("invalid"), f"{name}: MOD not active {m}"
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == CGR.MAP_FP and cs.get("mapFingerprint") == CGR.MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r} (baked {CGR.MAP_FP!r})")
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hs["units"] if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == SEATED, f"seated client units {seated_uids} (baked {SEATED})"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == 0 and u.get("faction") == FACTION_PLAYER
                   and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    pinned = pin_ai_neutral(host, client, tag="w2h30")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    session.wait_host_idle(host, client, timeout=30)
    session.assert_hash_clean(host, client, full=True, what="bring-up")
    return {"mod": ml, "mapFP": hs.get("mapFingerprint"), "seated": seated_uids, "H": h_ids[0], "pinned": len(pinned),
            "turn": hs.get("turn")}


def row_hs0(ev, res, host, client, st):
    ev["boot"], logs = st["ctx"], {}
    for n, gc in pairs(host, client):
        lines = log_lines(gc)
        logs[n] = {"active": sum(1 for ln in lines if CGR.MOD_ACTIVE_LINE in ln),
                   "errors": [ln for ln in lines if "[ERROR]" in ln][:5]}
    ev["log"] = logs
    res["HS0-mod"] = joined([f"{n} log: {v['active']} line(s) with {CGR.MOD_ACTIVE_LINE!r}, [ERROR] lines "
                             f"{v['errors']} (want >= 1 and none)" for n, v in logs.items()
                             if v["active"] < 1 or v["errors"]])
    fails, view = [], {}
    for n, gc in pairs(host, client):
        ub = units(gc)
        h = sorted(i for i, u in ub.items() if u.get("coop") == 0 and u.get("faction") == FACTION_PLAYER
                   and not u.get("isOut"))
        a, c = ub.get(A_ID) or {}, ub.get(C_ID) or {}
        view[n] = {"H": h[0] if h else None, "A": (a.get("faction"), a.get("isOut")),
                   "C": (c.get("faction"), c.get("coop"), c.get("isOut"))}
    ev["units"] = view
    if not (view["host"]["H"] == view["client"]["H"] == H_ID):
        fails.append(f"first host-seat soldier host {view['host']['H']} client {view['client']['H']} (want {H_ID})")
    if not (view["host"]["A"] == view["client"]["A"] == (FACTION_HOSTILE, False)):
        fails.append(f"A {A_ID} (faction, isOut) host {view['host']['A']} client {view['client']['A']} "
                     "(want a live hostile)")
    if not (view["host"]["C"] == view["client"]["C"] == (FACTION_PLAYER, 1, False)):
        fails.append(f"C {C_ID} (faction, coop, isOut) host {view['host']['C']} client {view['client']['C']}")
    res["HS0-units"] = joined(fails)
    res["HS0-common"] = joined(common(host, client, st["bootSnap"], "HS0", st["crash0"]))


def row_hp(ev, res, host, client, st):
    miss = None
    try:   # staging (levers, client first) and the host's right-hand box
        ev["probe"] = probe = give_both(host, client, H_ID, MIND_PROBE)[0]
        ev["placeH"] = place(host, client, H_ID, PROBE_H_TILE, PROBE_H_DIR)
        ev["placeA"] = place(host, client, A_ID, A_TILE, A_DIR)
        ev["tuMax"] = set_tu_both(host, client, H_ID, TU_MAX)
        ev["tab"] = tab_select(host, H_ID)
        ev["visLever"] = both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID,
                                             "visible": True}, ("visible",)).get("visible")
        ev["staged"] = staged = diff_buckets(host, client)
        ev["visible"] = vis = visible(host, A_ID)
        r = click_nth(host, RHAND_NTH)
        ev["rhand"] = (r.get("baseX"), r.get("baseY"))
        ev["menu"] = wait_top(host, "ActionMenuState")
        ev["rows"] = menu_rows(host)
        if not ev["tab"] or ev["rhand"] != RHAND_CENTRE or not ev["menu"] or ev["rows"] != PROBE_ROWS:
            miss = (f"tab {ev['tab']}, right-hand click {ev['rhand']} (want {RHAND_CENTRE}), ActionMenuState "
                    f"{ev['menu']}, menu rows {ev['rows']} (want {PROBE_ROWS})")
    except Exception as e:
        miss = short(e, 500)
    if not miss:
        before = snap(host, client)
        seq0 = before["host"]["lastSeqEmitted"] or 0
        ev["before"] = {"hostLastSeqEmitted": seq0, "clientLastSeqApplied": before["client"]["lastSeqApplied"],
                        "tu": {n: tu(gc, H_ID) for n, gc in pairs(host, client)}}
        nh, nc = len(log_lines(host)), len(log_lines(client))
        press(host, KEY_ITEM1)
        wait_top(host, "BattlescapeState")
        ev["cursor"] = battle_state(host).get("cursorType")
        press(host, SDLK_HOME)
        time.sleep(0.15)
        pr = host.cmd({"cmd": "map_tile_click_pos", "x": A_TILE[0], "y": A_TILE[1], "z": A_TILE[2]})
        ev["clickPos"] = {k: pr.get(k) for k in ("verified", "winX", "winY")}
        if ev["cursor"] != CURSOR_PSI or not pr.get("verified"):
            miss = f"cursorType {ev['cursor']} after key {KEY_ITEM1} (want {CURSOR_PSI}), click pos {ev['clickPos']}"
    if miss:
        capture(host, client, "HP")
        res.update({c: f"construction: {miss}" for c in CELLS["HP"]})
        return
    pre = [f"buckets differ after the staging: {staged}"] if staged else []
    if vis is not True:
        pre.append(f"visible(host, A) {vis} (want true)")
    t0 = time.time()
    host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
    if not wait_top(host, "UnitInfoState"):
        pre.append(f"host top {top(host)} {MENU_S} s after the click (want UnitInfoState)")
    want = H_TU_FULL - PROBE_TU
    while tu(host, H_ID) != want and time.time() - t0 < SCRIPT_S:
        time.sleep(POLL_S)
    ev["tuHost"] = (tu(host, H_ID), round(time.time() - t0, 2))
    if ev["tuHost"][0] != want:
        pre.append(f"host H TU {ev['tuHost'][0]} {SCRIPT_S} s after the click (want {want})")
    if top(host) == "UnitInfoState":   # never ESC on the battlescape itself (it opens the options screen)
        press(host, KEY_CANCEL)
    if not wait_top(host, "BattlescapeState"):
        pre.append(f"host top {top(host)} after key {KEY_CANCEL} (want BattlescapeState)")
    res["HP-press"] = joined(pre)
    ev["follow"], res["HP-follow"] = follow_tu(host, client, t0, want)
    after(ev, res, "HP", "mindprobe", ["mindprobe", "bt_action_end"], {"actor": H_ID, "unit": A_ID, "item": probe},
          host, client, before, seq0, nh, nc, st)
    res["HP-next"] = heal(ev, host, client)


def row_hz(ev, res, host, client, st):
    try:
        ev["tuMax"] = set_tu_both(host, client, H_ID, TU_MAX)
        ev["tab"] = tab_select(host, H_ID)
        ev["staged"] = staged = diff_buckets(host, client)
        miss = None if ev["tab"] else f"TAB never selected H (host selectedId {battle_state(host).get('selectedId')})"
    except Exception as e:
        miss = short(e, 500)
    if miss:
        capture(host, client, "HZ")
        res.update({c: f"construction: {miss}" for c in CELLS["HZ"]})
        return
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev["before"] = {"hostLastSeqEmitted": seq0, "clientLastSeqApplied": before["client"]["lastSeqApplied"],
                    "tu": {n: tu(gc, H_ID) for n, gc in pairs(host, client)}}
    nh, nc = len(log_lines(host)), len(log_lines(client))
    t0 = time.time()
    press(host, KEY_ZERO_TU)
    while tu(host, H_ID) != 0 and time.time() - t0 < SCRIPT_S:
        time.sleep(POLL_S)
    ev["tuHost"] = (tu(host, H_ID), round(time.time() - t0, 2))
    pre = [f"buckets differ after the staging: {staged}"] if staged else []
    if ev["tuHost"][0] != 0:
        pre.append(f"host H TU {ev['tuHost'][0]} {SCRIPT_S} s after key {KEY_ZERO_TU} (want 0)")
    res["HZ-press"] = joined(pre)
    ev["follow"], res["HZ-follow"] = follow_tu(host, client, t0, 0)
    after(ev, res, "HZ", "zero_tu", ["zero_tu", "bt_action_end"], {"actor": H_ID, "unit": H_ID},
          host, client, before, seq0, nh, nc, st)
    res["HZ-next"] = heal(ev, host, client)


def kit_on(gc, kit):
    return kit in items_of(gc)


def fuse_of(gc, gid):
    it = items_by_id(gc).get(gid) or {}
    return (it.get("fuse"), it.get("fuseEnabled"))


def split_common(res, rid, host, client, before, st):
    """<rid>-hash and <rid>-common: the common cell (after wait_host_idle), split on its hash entry."""
    fails = common(host, client, before, rid, st["crash0"])
    res[f"{rid}-hash"] = joined([x for x in fails if x.startswith(HASH_FAIL)])
    res[f"{rid}-common"] = joined([x for x in fails if not x.startswith(HASH_FAIL)])


def tail_ev(ev, host, client, kinds, nh, subject):
    """EVIDENCE after a row: seqs, the subject on both, cueCounts of the row's kinds on both, contextsOpened.host,
    the buckets that differ, the host's context / cue log lines of those kinds."""
    eh, ec = event_state(host), event_state(client)
    ev["after"] = {"hostLastSeqEmitted": eh.get("lastSeqEmitted"), "clientLastSeqApplied": ec.get("lastSeqApplied"),
                   "subject": subject(),
                   "cue": {k: [(e.get("cueCounts") or {}).get(k) for e in (eh, ec)] for k in kinds},
                   "hostContextsOpenedHost": (eh.get("contextsOpened") or {}).get("host"),
                   "diff": diff_buckets(host, client),
                   "hostLog": [ln.split("\t")[-1] for ln in log_lines(host)[nh:]
                               if any(f"[coop-ctx] host {k}" in ln or f"[coop-cue] {k}" in ln for k in kinds)]}


def row_hk(ev, res, host, client, st):
    miss = None
    try:   # staging (levers, client first): P wounded on the tile H faces, the one-charge kit in H's right hand
        ub = units(host)
        ids = sorted(i for i, u in ub.items() if u.get("coop") == 0 and u.get("faction") == FACTION_PLAYER
                     and not u.get("isOut"))
        ev["P"] = ids[1] if len(ids) > 1 else None
        assert ev["P"] == P_ID, f"second host-seat soldier {ev['P']} (baked P={P_ID})"
        ev["placeH"] = place(host, client, H_ID, PROBE_H_TILE, PROBE_H_DIR)
        ev["placeP"] = place(host, client, P_ID, P_TILE, P_DIR)
        ev["wounds"] = wounds_both(host, client, P_ID, WOUNDS)
        ev["kit"] = kit = give_both(host, client, H_ID, ONE_CHARGE)[0]
        ev["tuMax"] = set_tu_both(host, client, H_ID, TU_MAX)
        ev["tab"] = tab_select(host, H_ID)
        ev["staged"] = staged = diff_buckets(host, client)
        ev["charges"] = ch = {n: charges(items_of(gc), kit) for n, gc in pairs(host, client)}
        r = click_nth(host, RHAND_NTH)
        ev["rhand"] = (r.get("baseX"), r.get("baseY"))
        ev["menu"] = wait_top(host, "ActionMenuState")
        ev["rows"] = menu_rows(host)
        if not ev["tab"] or ev["rhand"] != RHAND_CENTRE or not ev["menu"]:
            miss = (f"tab {ev['tab']}, right-hand click {ev['rhand']} (want {RHAND_CENTRE}), ActionMenuState "
                    f"{ev['menu']}")
        else:
            press(host, KEY_ITEM1)
            ev["open"] = wait_top(host, "MedikitState")
            if not ev["open"]:
                miss = f"host top {top(host)} {MENU_S} s after key {KEY_ITEM1} (want MedikitState)"
    except Exception as e:
        miss = short(e, 500)
    if miss:
        capture(host, client, "HK")
        res.update({c: f"construction: {miss}" for c in CELLS["HK"]})
        return
    pre = [f"buckets differ after the staging: {staged}"] if staged else []
    if ch != {"host": CHARGES_FULL, "client": CHARGES_FULL}:
        pre.append(f"kit {kit} charges {ch} (want {CHARGES_FULL} on both)")
    if ev["rows"] != KIT_ROWS:
        pre.append(f"host menu rows {ev['rows']} (want {KIT_ROWS})")
    res["HK-open"] = joined(pre)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev["before"] = {"hostLastSeqEmitted": seq0, "clientLastSeqApplied": before["client"]["lastSeqApplied"],
                    "kit": {n: kit_on(gc, kit) for n, gc in pairs(host, client)}}
    nh = len(log_lines(host))
    press(host, KEY_HEAL)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        ev["idle"] = short(e)
    new = new_contexts(before["host"]["closedContexts"], event_state(host).get("closedContexts"))
    ctx, hev = mine(new, "host", "medikit", H_ID), evs_since(host, seq0)
    ev["use"] = u = {"newCtx": new, "hostEvs": hev, "top": top(host),
                     "wounds": {n: (units(gc).get(P_ID) or {}).get("wounds") for n, gc in pairs(host, client)},
                     "tu": {n: tu(gc, H_ID) for n, gc in pairs(host, client)}}
    f = []
    if len(new) != 1 or len(ctx) != 1:
        f.append(f"new host closedContexts {new} (want exactly one {{origin host, kind medikit, actorId {H_ID}}})")
    elif [e["kind"] for e in hev if e["actionId"] == ctx[0].get("actionId")] != ["medikit", "bt_action_end"]:
        f.append(f"host evs since seq {seq0}: {hev} (want [medikit, bt_action_end] on the new context)")
    if u["wounds"] != {"host": WOUNDS_HEALED, "client": WOUNDS_HEALED}:
        f.append(f"P {P_ID} wounds {u['wounds']} (want {WOUNDS_HEALED} on both)")
    if u["tu"] != {"host": H_TU_FULL - KIT_TU, "client": H_TU_FULL - KIT_TU}:
        f.append(f"H TU {u['tu']} (want {H_TU_FULL - KIT_TU} on both)")
    if u["top"] != "MedikitState":
        f.append(f"host top {u['top']} after the heal (want MedikitState still open)")
    res["HK-use"] = joined(f)
    ev["inctx"] = on = {n: kit_on(gc, kit) for n, gc in pairs(host, client)}
    res["HK-inctx"] = joined([f"kit {kit} listed {on} after the use that emptied it, before the close (want gone on "
                              "both: the removal rides the medikit context)"] if any(on.values()) else [])
    s1, t1, f = event_state(host).get("lastSeqEmitted"), time.time(), []
    if top(host) == "MedikitState":   # never ESC on the battlescape itself (it opens the options screen)
        press(host, KEY_CANCEL)
    if not wait_top(host, "BattlescapeState"):
        f.append(f"host top {top(host)} after key {KEY_CANCEL} (want BattlescapeState)")
    gone = None
    while time.time() - t1 < FOLLOW_S:
        if gone is None and not kit_on(host, kit) and not kit_on(client, kit):
            gone = round(time.time() - t1, 2)
        time.sleep(POLL_S)
    ev["close"] = {"s1": s1, "s2": event_state(host).get("lastSeqEmitted"), "gone": gone,
                   "kit": {n: kit_on(gc, kit) for n, gc in pairs(host, client)}}
    if ev["close"]["s2"] != s1:
        f.append(f"host lastSeqEmitted {s1} -> {ev['close']['s2']} {FOLLOW_S} s after the close (want unchanged: the "
                 "close and the BA_USE aftermath emit nothing, L-3)")
    res["HK-close"] = joined(f)
    res["HK-follow"] = joined([] if gone is not None else [f"kit {kit} listed {ev['close']['kit']} {FOLLOW_S} s after "
                                                           "the close (want gone on both)"])
    split_common(res, "HK", host, client, before, st)
    tail_ev(ev, host, client, ("medikit",), nh, lambda: {n: kit_on(gc, kit) for n, gc in pairs(host, client)})
    nf = heal(ev, host, client)
    ev["next"]["kit"] = on = {n: kit_on(gc, kit) for n, gc in pairs(host, client)}
    res["HK-next"] = joined(([nf] if nf else []) + ([f"kit {kit} listed {on} after the heal order (want gone on "
                                                     "both)"] if any(on.values()) else []))


def row_hg(ev, res, host, client, st):   # LAST: its red leaves the split and a primed grenade standing
    miss = None
    try:
        ev["g"] = g = give_both(host, client, H_ID, GRENADE)[0]
        ev["tuMax"] = set_tu_both(host, client, H_ID, TU_MAX)
        ev["tab"] = tab_select(host, H_ID)
        ev["staged"] = staged = diff_buckets(host, client)
        ev["fuse0"] = fuse0 = {n: fuse_of(gc, g) for n, gc in pairs(host, client)}
        ev["skillsNth"] = nth = skills_nth(host)
        if not ev["tab"] or nth is None:
            miss = f"tab {ev['tab']}, SKILLS nth {nth} (want a visible widget at {SKILLS_RECT})"
        else:
            r = click_nth(host, nth)
            ev["skills"] = (r.get("baseX"), r.get("baseY"))
            ev["menu"] = wait_top(host, "SkillMenuState")
            ev["rows"] = menu_rows(host)
            if not ev["menu"]:
                miss = f"host top {top(host)} {MENU_S} s after the SKILLS click (want SkillMenuState)"
    except Exception as e:
        miss = short(e, 500)
    if miss:
        capture(host, client, "HG")
        res.update({c: f"construction: {miss}" for c in CELLS["HG"]})
        return
    pre = [f"buckets differ after the staging: {staged}"] if staged else []
    if fuse0 != {"host": FUSE_OFF, "client": FUSE_OFF}:
        pre.append(f"grenade {g} (fuse, fuseEnabled) before {fuse0} (want {FUSE_OFF} on both)")
    if ev["rows"] != SKILL_ROWS:
        pre.append(f"host skill menu rows {ev['rows']} (want {SKILL_ROWS})")
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev["before"] = {"hostLastSeqEmitted": seq0, "clientLastSeqApplied": before["client"]["lastSeqApplied"]}
    nh, nc = len(log_lines(host)), len(log_lines(client))
    t0, t_aim, t_fuse = time.time(), None, None
    press(host, KEY_SKILL_GRENADE)
    while time.time() - t0 < MENU_S and (t_aim is None or t_fuse is None):
        if t_aim is None and top(host) == "BattlescapeState" and battle_state(host).get("cursorType") == CURSOR_THROW:
            t_aim = round(time.time() - t0, 2)
        if t_fuse is None and fuse_of(host, g) == FUSE_INSTANT:
            t_fuse = round(time.time() - t0, 2)
        time.sleep(POLL_S)
    ev["press"] = {"tAim": t_aim, "tFuseHost": t_fuse, "cursor": battle_state(host).get("cursorType"), "top": top(host)}
    if t_aim is None:
        pre.append(f"host top {ev['press']['top']} cursorType {ev['press']['cursor']} {MENU_S} s after key "
                   f"{KEY_SKILL_GRENADE} (want BattlescapeState, {CURSOR_THROW})")
    if t_fuse is None or t_fuse > SCRIPT_S:
        pre.append(f"host grenade {fuse_of(host, g)} at {t_fuse} s (want {FUSE_INSTANT} within {SCRIPT_S} s)")
    seen = None   # HG-follow: poll the client's grenade, nothing else ordered meanwhile
    while seen is None and time.time() - t0 < FOLLOW_S:
        if fuse_of(client, g) == FUSE_INSTANT:
            seen = round(time.time() - t0, 2)
        else:
            time.sleep(POLL_S)
    ev["follow"] = fo = {"t": seen, "host": fuse_of(host, g), "client": fuse_of(client, g)}
    res["HG-follow"] = joined([] if seen is not None else [f"client grenade {fo['client']}, host {fo['host']} "
                                                           f"{FOLLOW_S} s after the key (want {FUSE_INSTANT} on both)"])
    r, t2 = click_nth(host, RHAND_NTH), time.time()   # cancel the throw (F503: a hand click only cancels targeting)
    while battle_state(host).get("cursorType") in CGR.CURSOR_TARGETING and time.time() - t2 < MENU_S:
        time.sleep(POLL_S)
    ev["cancel"] = {"click": (r.get("baseX"), r.get("baseY")), "cursor": battle_state(host).get("cursorType"),
                    "top": top(host)}
    if ev["cancel"]["cursor"] in CGR.CURSOR_TARGETING:
        pre.append(f"host cursorType {ev['cancel']['cursor']} after the cancel click (want outside "
                   f"{CGR.CURSOR_TARGETING})")
    res["HG-press"] = joined(pre)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        ev["idle"] = short(e)
    eh, ec = event_state(host), event_state(client)
    new = sorted(new_contexts(before["host"]["closedContexts"], eh.get("closedContexts")),
                 key=lambda c: c.get("actionId") or 0)
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    ev.update({"newCtx": new, "hostEvs": hev, "clientEvs": cev, "hostLastCue": eh.get("lastCue"),
               "clientLastCue": ec.get("lastCue")})
    got, want = [(c.get("origin"), c.get("kind"), c.get("actorId")) for c in new], [("host", "skill", H_ID),
                                                                                    ("host", "prime", H_ID)]
    f = [] if got == want else [f"new host closedContexts {got} (want exactly {want}, in actionId order)"]
    f += ctx_fails("prime", H_ID, ["prime", "bt_action_end"],
                   {"actor": H_ID, "unit": H_ID, "item": g, "fuse": 0, "unprime": False}, seq0,
                   [c for c in new if c.get("kind") == "prime"], hev, cev, eh, ec, log_lines(client)[nc:])
    res["HG-ev"] = joined(f)
    split_common(res, "HG", host, client, before, st)
    tail_ev(ev, host, client, ("skill", "prime"), nh, lambda: {n: fuse_of(gc, g) for n, gc in pairs(host, client)})


ROWS = (("HS0", row_hs0), ("HP", row_hp), ("HZ", row_hz), ("HK", row_hk), ("HG", row_hg))


def report(rid, ev, res):
    print(f"EVIDENCE {rid}: {json.dumps(ev, default=str)}", flush=True)
    for c in CELLS[rid]:
        f = res.get(c, "not reached")
        print(f"PASS {c}" if f is None else f"FAIL {c}: {f}", flush=True)
    bad = [c for c in CELLS[rid] if res.get(c, "not reached") is not None]
    print(f"PASS {rid}" if not bad else f"FAIL {rid}: {', '.join(bad)}", flush=True)
    return bad


def run_row(rid, fn, host, client, st):
    ev, res = {}, {}
    try:
        fn(ev, res, host, client, st)
    except Exception as e:
        ev["error"] = msg = short(e, 500)
        for c in CELLS[rid]:
            res.setdefault(c, f"the row raised before this cell: {msg}")
    return report(rid, ev, res)


def main():
    t_start = time.time()
    host = GameClient("host", 1, make_user_dir(HOST_DIR, mods=[CGR.MOD_DIR], options={"coopGhostStepper": True}))
    client = GameClient("client", 2, make_user_dir(CLIENT_DIR, mods=[CGR.MOD_DIR], options={"coopGhostStepper": True}))
    failed = []
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:
            print(f"boot failed: {short(e, 600)}", flush=True)
            capture(host, client, "boot")
            for rid, _ in ROWS:
                failed += report(rid, {"error": "boot"}, {c: "boot" for c in CELLS[rid]})
        else:
            st = {"ctx": ctx, "crash0": session._crash_log_snapshot(), "bootSnap": snap(host, client)}
            for rid, fn in ROWS:
                failed += run_row(rid, fn, host, client, st)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2h30] shutdown {gc.name}: {short(e)}", flush=True)
    n = sum(len(v) for v in CELLS.values())
    print(f"\ntest_w2_host_local_ev: {n - len(failed)}/{n} cells passed (fail={failed}) in "
          f"{round(time.time() - t_start, 1)} s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
