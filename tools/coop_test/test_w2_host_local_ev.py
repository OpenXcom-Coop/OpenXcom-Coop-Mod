"""W2-H30 - the host's own presses that change the battle on the host only reach the second player in one host
action (spec docs rewrite/prompts/w2h30_host_local_actions.md (f); TASK 0 docs rewrite/w2h30-task0/sa/CONSTANTS.md;
W2-H28 QH-4 (a); F12351, F12354, F11564). Before the fix the HOST's own mind probe (L-1) and its Zero TU key (L-4)
spend / zero the soldier's time units on the host only and emit nothing, so the second player keeps the old value
(and hash_now differs) until the host's next ev of any kind, which carries the change (the -next cells).
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
Common cell: after wait_host_idle, test_w2_client_shoot.common_fails minus its hash entry and no crash file since the
boot; the -hash cell is that entry. RED (commit A1, unchanged build): exactly HP-ev, HP-follow, HP-hash, HZ-ev,
HZ-follow, HZ-hash FAIL. GREEN (A2): every cell PASS.
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
         "HZ": ("HZ-press", "HZ-ev", "HZ-follow", "HZ-hash", "HZ-common", "HZ-next")}


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


ROWS = (("HS0", row_hs0), ("HP", row_hp), ("HZ", row_hz))


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
