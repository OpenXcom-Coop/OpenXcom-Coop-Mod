"""D249-U S-A - test_follow_camera.py: `main`'s per-player option "Follow Teammate Actions with Camera"
(`coopFollowPeerActions`) comes back, default OFF (D131 stays the default); with it ON a machine's camera follows the
co-op partner's soldiers as it follows an alien in the alien turn (owner D249 (a); D171 (a); QD249-1..9 (a)).

Spec: docs repo rewrite/prompts/d249u_follow_teammate_camera.md section (f).
Constants: docs repo rewrite\\d249u-task0\\sa\\CONSTANTS.md (TASK 0 boots Fa-Ff on the TB1 probe build).

Boot F: one co-op skirmish (STR_TERROR_MISSION, map seed 1, lobby key 46652, dirs d249u_f_host / _client, options
{"coopGhostStepper": True} only: the new option is never written to a user dir, its default is read live). Rows, in
this order (P1 last: it ends the turn):
  O1  the option exists, default off, each player's own (the CLIENT turns it on here):
      O1-default, O1-meta, O1-client-on
  W1  the client's camera follows the host's real-UI walk: W1-walk (precondition), W1-moves, W1-offset, W1-host (guard)
  W2  the host, its option still off, keeps D131 for the client's walk: W2-walk (precondition), W2-host (guard)
  O2  the host turns its own option on: O2-host-on
  W3  the host's camera follows the client's walk: W3-walk (precondition), W3-host
  S1  the client's camera follows the host's real-UI snap shot: S1-shot (precondition), S1-moves, S1-offset,
      S1-host (guard)
  S2  the host's camera follows the client's lever snap shot: S2-shot (precondition), S2-host
  P1  a panic on either side moves the other player's camera (both on; one END TURN cycle): P1-roll (precondition),
      P1-client, P1-host
Every row ends with <row>-common: every hash bucket EQUAL, desyncSeen false on both, no new file in the lane crash
folder.
`set_option` for this option rides TB1, the test-only TestServer fallback that answers any registered bool option by
id; a build without the option answers `error` "unknown option: coopFollowPeerActions" (a FAIL value, never an
exception). Lever pairs go to the client first (F607); every item id comes from a lever reply (S25).

One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure; a cell
whose precondition failed FAILs "not reached". A boot step past its bound prints ONE "CAPTURE F:" line and fails every
row "boot". WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0
only when every cell passes, else 2.

Run:  python tools/coop_test/test_follow_camera.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, assert_hash_clean  # noqa: E402
import test_host_combat as HC  # noqa: E402
import test_client_shoot as CSH  # noqa: E402
import test_seat_pacing as SPC  # noqa: E402
import test_turn_cues as TCU  # noqa: E402
from test_ai_origins import host_payloads  # noqa: E402

KEY = "46652"                     # the skirmish_host lobby key (spec (F), F14132)
OPT = "coopFollowPeerActions"     # `main`'s id (QD249-5 (a))
OPT_TEXT = "Follow Teammate Actions with Camera"   # `main`'s literal row text (QD249-9 (a))
OPT_CATEGORY = "STR_BATTLESCAPE"
OPTION_OTHER = 2                  # src/Engine/OptionInfo.h enum OptionOwner: the Multiplayer screen's options
H_ID, HP_ID = 10, 11              # the host seat's first two soldiers (TASK 0: host seat [10, 11, 12, 13, 14])
C_ID, C2_ID = 8, 9                # the client's seated soldiers
TU_MAX = 255                      # battle_set_unit_state tu: clamped to the unit's max
W1_H_TILE, W1_DIR, W1_DEST = (14, 24, 0), 2, (17, 24, 0)
W1_STEPS = 3                      # walk_step evs of W1's walk (TASK 0: seqs 8, 9, 10)
W2_C_TILE, W2_DIR, W2_DEST = (12, 26, 0), 2, (15, 26, 0)
W2_WL = 6                         # host suppressed.walkLevel for W2's 3 steps, the walker off the host's screen
W3_DEST = (13, 26, 0)
W3_WL = 4                         # W3's 2 steps: the red's host suppressed.walkLevel (evidence of the RED shape)
S1_TARGET, SEED_S1 = (34, 24, 0), 1   # empty road floor 17 tiles east of W1_DEST; H stays there facing 2 (S2)
S1_CHAIN = ["shot", "hit", "bt_action_end"]
S2_C_TILE, S2_DIR, S2_TARGET, SEED_S2 = (12, 26, 0), 2, (32, 26, 0), 1
S2_CHAIN = ["shot", "bt_action_end"]   # the shot leaves the map: no `hit` (TASK 0: impact 5)
S2_RED = {"follow": 1, "explosion": 0, "hitLevel": 0, "walkLevel": 0, "panic": 0}   # the red's host delta
P1_HP_TILE, P1_C2_TILE, P1_DIR = (21, 26, 0), (12, 30, 0), 2   # by the spec's rule (TASK 0 swap, S54)
SEED_P1 = 5                       # host set_seed right before its END TURN press: HP and C2 both flee
PANIC_MODES = ("flee", "freeze")
STEP_S = 30                       # every order / settle bound (TASK 0: <= 1.4 s)
SUP_ZERO = {k: 0 for k in HC.CAM_SUPPRESSED}
ROWS = (("O1", ("O1-default", "O1-meta", "O1-client-on", "O1-common")),
        ("W1", ("W1-walk", "W1-moves", "W1-offset", "W1-host", "W1-common")),
        ("W2", ("W2-walk", "W2-host", "W2-common")),
        ("O2", ("O2-host-on", "O2-common")),
        ("W3", ("W3-walk", "W3-host", "W3-common")),
        ("S1", ("S1-shot", "S1-moves", "S1-offset", "S1-host", "S1-common")),
        ("S2", ("S2-shot", "S2-host", "S2-common")),
        ("P1", ("P1-roll", "P1-client", "P1-host", "P1-common")))


class Miss(Exception):
    """A boot step past its bound (its CAPTURE line is already printed)."""


# ===================== probes =====================


def es(gc, key):
    return event_state(gc).get(key)


def units(gc):
    return session.units_by_id(battle_state(gc))


def upos(u):
    return (u.get("x"), u.get("y"), u.get("z")) if u else None


def ubrief(u):
    return {k: (u or {}).get(k) for k in ("x", "y", "z", "direction", "status", "morale", "tu")} if u else None


def opt_value(gc):
    """This machine's live `coopFollowPeerActions` (option_values): None when the build does not register it."""
    return (gc.cmd({"cmd": "option_values", "ids": [OPT]}).get("values") or {}).get(OPT)


def log_tail(gc, n=40):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), encoding="utf-8", errors="replace") as f:
            return [line.rstrip("\n") for line in f][-n:]
    except OSError:
        return []


def capture(tag, err, host, client):
    """ONE CAPTURE line: both machines' stacks, battle_state side / turn / units, event_state camera / busyOwnerSeat,
    coop_dialog_info and the last 40 engine log lines (after a 3 s log flush)."""
    time.sleep(3)
    cap = {}
    for gc in (host, client):
        d = {}
        for k, fn in (("stack", session.states_stripped),
                      ("battle", lambda g: {k2: battle_state(g).get(k2) for k2 in ("side", "turn", "units")}),
                      ("event", lambda g: {k2: es(g, k2) for k2 in ("camera", "busyOwnerSeat")}),
                      ("dialog", lambda g: g.cmd({"cmd": "coop_dialog_info"})), ("logTail", log_tail)):
            try:
                d[k] = fn(gc)
            except Exception as e:
                d[k] = f"probe failed: {type(e).__name__}: {e}"
        cap[gc.name] = d
    print(f"CAPTURE {tag}: missed {err}; {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def guarded(tag, fn, host, client):
    try:
        return fn()
    except Exception as e:
        capture(tag, f"{type(e).__name__}: {str(e)[:600]}", host, client)
        raise Miss(tag)


def wait_until(pred, timeout, interval=0.2):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True, round(time.time() - t0, 2)
        time.sleep(interval)
    return bool(pred()), round(time.time() - t0, 2)


def idle(host, client, ev):
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:300]


def common(host, client, crash0):
    try:
        assert_hash_clean(host, client, full=True, what="d249u common")
        hashed = "all buckets EQUAL"
    except AssertionError as e:
        hashed = str(e)[:400]
    ds = [es(host, "desyncSeen"), es(client, "desyncSeen")]
    crash = sorted(session._crash_log_snapshot() - crash0)
    return (hashed == "all buckets EQUAL" and ds == [False, False] and not crash,
            f"common: hash {hashed}; desyncSeen host/client {ds} (want False/False); new crash files {crash} "
            f"(want none)")


# ===================== cells and rows =====================


def verdict(row, order, cells, ev):
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    failed = []
    for name in order:
        ok, detail = cells.get(name, (False, f"not reached: {ev.get('error')}"))
        if not ok:
            failed.append(name)
        print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)
    print(f"{row} {'PASS' if not failed else 'FAIL'} ({len(failed)} of {len(order)} cells failed)", flush=True)
    return failed


def run_row(row, order, fn, host, client):
    """One row: `fn()` returns (cells, ev); an exception fails every cell it did not reach (after a CAPTURE line)."""
    try:
        cells, ev = fn()
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:600]}"
        capture(row, err, host, client)
        cells, ev = {}, {"error": err}
    return verdict(row, order, cells, ev)


def unreached(names, pre):
    return {n: (False, f"not reached ({pre} failed)") for n in names}


def sup_delta(cam0, cam1):
    return HC.cam_suppressed_delta(cam0["host"], cam1["host"])


def new_ctx(host, ctx0):
    return CSH.new_contexts(ctx0, es(host, "closedContexts"))


def ctx_cell(new, origin, kind, actor, extra_ok=True, extra=""):
    one = CSH.mine(new, origin, kind, actor)
    view = [{k: c.get(k) for k in ("actionId", "origin", "kind", "actorId")} for c in new]
    return (len(new) == 1 and len(one) == 1 and extra_ok,
            f"new host closedContexts {view} (want exactly one {{origin {origin}, kind {kind}, actorId {actor}}}){extra}")


def chain(evs, aid):
    return [e for e in evs if aid is not None and e["actionId"] == aid]


def row_o1(host, client, crash0):
    vals = [opt_value(host), opt_value(client)]
    meta = client.cmd({"cmd": "set_option", "name": OPT})
    on = client.cmd({"cmd": "set_option", "name": OPT, "value": True})
    host_after = opt_value(host)
    want = {"ok": True, "value": False, "description": OPT_TEXT, "category": OPT_CATEGORY, "owner": OPTION_OTHER}
    got = {k: meta.get(k) for k in want}
    ev = {"optionValues": vals, "clientMeta": meta, "clientOn": on, "hostAfter": host_after}
    return {"O1-default": (vals[0] is False and vals[1] is False,
                           f"option_values {OPT} host/client {vals} (want False/False: registered, default off)"),
            "O1-meta": (got == want and meta.get("value") is False and "error" not in meta,
                        f"client set_option {{name: {OPT}}} -> {meta} (want {want})"),
            "O1-client-on": (on.get("ok") is True and on.get("value") is True and host_after is False,
                             f"client set_option {{name, value true}} -> {on} (want ok, value True); host "
                             f"option_values after {host_after} (want False: each player's own)"),
            "O1-common": common(host, client, crash0)}, ev


def walker_cell(moves, steps, uid):
    """W1-moves: at each walk_step seq exactly {walker_level}, preceded by {walker_centre} when that step's record has
    visible true and onScreen false; at least one walker_centre; every record names `uid`."""
    got = [(m.get("seq"), m.get("reason")) for m in moves]
    want = []
    for s in steps:
        lv = [m for m in moves if (m.get("seq"), m.get("reason")) == (s, "walker_level")]
        if lv and lv[0].get("visible") is True and lv[0].get("onScreen") is False:
            want.append((s, "walker_centre"))
        want.append((s, "walker_level"))
    who = sorted({m.get("unit") for m in moves})
    ok = got == want and (any(r == "walker_centre" for _, r in got)) and who == [uid]
    return ok, (f"client camera.moves at the walk_step seqs {steps}: {got} (want {want}, at least one walker_centre); "
                f"units {who} (want [{uid}])")


def row_w1(host, client, crash0):
    ev = {"place": CSH.place(host, client, H_ID, W1_H_TILE, W1_DIR), "tu": CSH.set_tu_both(host, client, H_ID, TU_MAX)}
    staged = HC.stage_camera(client, HC.K_FAR_TERROR)
    cam0 = HC.cam_snap(host, client)
    ctx0, seq0 = es(host, "closedContexts"), es(host, "lastSeqEmitted") or 0
    ev["tab"] = SPC.tab_select(host, H_ID)
    SPC.real_click_walk(host, W1_DEST)
    ok, ev["settleS"] = wait_until(lambda: bool(CSH.mine(new_ctx(host, ctx0), "host", "walk", H_ID))
                                   and upos(units(host).get(H_ID)) == W1_DEST
                                   and upos(units(client).get(H_ID)) == W1_DEST, STEP_S)
    idle(host, client, ev)
    cam1 = HC.cam_snap(host, client)
    new = new_ctx(host, ctx0)
    one = CSH.mine(new, "host", "walk", H_ID)
    aid = one[0].get("actionId") if len(one) == 1 else None
    hev, cev = HC.evs_since(host, seq0), HC.evs_since(client, seq0)
    steps = [e["seq"] for e in chain(hev, aid) if e["kind"] == "walk_step"]
    csteps = [e["seq"] for e in chain(cev, aid) if e["kind"] == "walk_step"]
    moves = [m for m in HC.cam_moves(cam1["client"]) if m.get("seq") in steps]
    sup = sup_delta(cam0, cam1)
    ev.update(settled=ok, staged=HC.cam_offset(staged), steps=steps, clientSteps=csteps,
              client0=HC.cam_view(cam0["client"]), client1=HC.cam_view(cam1["client"], seq0), hostSup=sup,
              H=[ubrief(units(gc).get(H_ID)) for gc in (host, client)])
    cells = {"W1-walk": ctx_cell(new, "host", "walk", H_ID, ok and len(steps) == W1_STEPS and csteps == steps,
                                 f"; walk_step seqs host {steps} client {csteps} (want {W1_STEPS} on both, the same); "
                                 f"H on {W1_DEST} on both {ok} ({ev['settleS']} s)")}
    if cells["W1-walk"][0]:
        cells["W1-moves"] = walker_cell(moves, steps, H_ID)
        o1 = HC.cam_offset(cam1["client"])
        cells["W1-offset"] = (o1 != HC.cam_offset(staged), f"client offset after {o1} (want != the staged "
                                                           f"{HC.cam_offset(staged)}: centred on the host's walker)")
        cells["W1-host"] = (sup == SUP_ZERO, f"host camera.suppressed delta {sup} (want all 0: the host's own walk)")
    else:
        cells.update(unreached(("W1-moves", "W1-offset", "W1-host"), "W1-walk"))
    cells["W1-common"] = common(host, client, crash0)
    return cells, ev


def partner_walk(host, client, dest, ev):
    """The client's lever walk of C to `dest` with the host's camera staged far (K_HOSTFAR_TERROR, level 1).
    Returns (staged, cam0, cam1, the new host contexts); `ev` gains the walk_step seqs and the camera views."""
    staged = HC.stage_camera(host, HC.K_HOSTFAR_TERROR)
    cam0 = HC.cam_snap(host, client)
    ctx0, seq0 = es(host, "closedContexts"), es(host, "lastSeqEmitted") or 0
    ev["resp"] = session.send_walk(client, C_ID, dest)
    ev["settled"], ev["settleS"] = wait_until(lambda: bool(CSH.mine(new_ctx(host, ctx0), "intent", "walk", C_ID))
                                              and CSH.order_done(host, client)
                                              and upos(units(host).get(C_ID)) == dest
                                              and upos(units(client).get(C_ID)) == dest, STEP_S)
    idle(host, client, ev)
    cam1 = HC.cam_snap(host, client)
    new = new_ctx(host, ctx0)
    one = CSH.mine(new, "intent", "walk", C_ID)
    steps = [e["seq"] for e in chain(HC.evs_since(host, seq0), one[0].get("actionId") if len(one) == 1 else None)
             if e["kind"] == "walk_step"]
    ev.update(staged=HC.cam_offset(staged), steps=steps, host0=HC.cam_view(cam0["host"]),
              host1=HC.cam_view(cam1["host"]), hostSup=sup_delta(cam0, cam1),
              clientMoves=[(m.get("seq"), m.get("reason"), m.get("unit")) for m in HC.cam_moves(cam1["client"], seq0)],
              C=[ubrief(units(gc).get(C_ID)) for gc in (host, client)])
    return staged, cam0, cam1, new


def row_w2(host, client, crash0):
    ev = {"place": CSH.place(host, client, C_ID, W2_C_TILE, W2_DIR), "tu": CSH.set_tu_both(host, client, C_ID, TU_MAX)}
    staged, cam0, cam1, new = partner_walk(host, client, W2_DEST, ev)
    cells = {"W2-walk": ctx_cell(new, "intent", "walk", C_ID, ev["settled"],
                                 f"; C on {W2_DEST} on both, order over {ev['settled']} ({ev['settleS']} s)")}
    if cells["W2-walk"][0]:
        sup, o1, vl = ev["hostSup"], HC.cam_offset(cam1["host"]), cam1["host"].get("viewLevel")
        want = dict(SUP_ZERO, walkLevel=W2_WL)
        cells["W2-host"] = (sup == want and o1 == HC.cam_offset(staged) and vl == 1,
                            f"host camera.suppressed delta {sup} (want {want}); offset {o1} (want the staged "
                            f"{HC.cam_offset(staged)}); viewLevel {vl} (want 1): the host's option is off (D131)")
    else:
        cells.update(unreached(("W2-host",), "W2-walk"))
    cells["W2-common"] = common(host, client, crash0)
    return cells, ev


def row_o2(host, client, crash0):
    on = host.cmd({"cmd": "set_option", "name": OPT, "value": True})
    other = opt_value(client)
    ev = {"hostOn": on, "clientAfter": other}
    return {"O2-host-on": (on.get("ok") is True and on.get("value") is True and other is True,
                           f"host set_option {{name: {OPT}, value true}} -> {on} (want ok, value True); client "
                           f"option_values after {other} (want True: still the client's own)"),
            "O2-common": common(host, client, crash0)}, ev


def row_w3(host, client, crash0):
    ev = {"tu": CSH.set_tu_both(host, client, C_ID, TU_MAX)}
    staged, cam0, cam1, new = partner_walk(host, client, W3_DEST, ev)
    cells = {"W3-walk": ctx_cell(new, "intent", "walk", C_ID, ev["settled"],
                                 f"; C on {W3_DEST} on both, order over {ev['settled']} ({ev['settleS']} s)")}
    if cells["W3-walk"][0]:
        sup, o1, vl = ev["hostSup"], HC.cam_offset(cam1["host"]), cam1["host"].get("viewLevel")
        cells["W3-host"] = (sup == SUP_ZERO and o1 != HC.cam_offset(staged) and vl == 0,
                            f"host camera.suppressed delta {sup} (want all 0; red: walkLevel +{W3_WL}); offset {o1} "
                            f"(want != the staged {HC.cam_offset(staged)}); viewLevel {vl} (want 0, C's level)")
    else:
        cells.update(unreached(("W3-host",), "W3-walk"))
    cells["W3-common"] = common(host, client, crash0)
    return cells, ev


def row_s1(host, client, crash0):
    rifle, clip = CSH.give_both(host, client, H_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    ev = {"rifle": rifle, "clip": clip, "H": CSH.place(host, client, H_ID, W1_DEST, W1_DIR),
          "tu": CSH.set_tu_both(host, client, H_ID, TU_MAX)}
    staged = HC.stage_camera(client, HC.K_FAR_TERROR)
    cam0 = HC.cam_snap(host, client)
    ctx0, seq0 = es(host, "closedContexts"), es(host, "lastSeqEmitted") or 0
    ev["cursor"] = HC.open_hand_menu_host(host)
    HC.press(host, HC.KEY_ITEM2)
    host.wait_for("host BattlescapeState on top after SNAP", lambda: session.top_state(host) == "BattlescapeState"
                  or None, timeout=5)
    host.ok({"cmd": "inject_input", "kind": "key", "key": SPC.SDLK_HOME})
    time.sleep(0.15)
    pr = host.cmd({"cmd": "map_tile_click_pos", "x": S1_TARGET[0], "y": S1_TARGET[1], "z": S1_TARGET[2]})
    assert pr.get("verified"), f"map_tile_click_pos did not verify S1_TARGET {S1_TARGET}: {pr}"
    host.ok({"cmd": "set_seed", "seed": SEED_S1})
    host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
    ok, ev["settleS"] = wait_until(lambda: bool(CSH.mine(new_ctx(host, ctx0), "host", "shoot", H_ID))
                                   and es(host, "busyOwnerSeat") == -1, STEP_S)
    idle(host, client, ev)
    cam1 = HC.cam_snap(host, client)
    new = new_ctx(host, ctx0)
    one = CSH.mine(new, "host", "shoot", H_ID)
    aid = one[0].get("actionId") if len(one) == 1 else None
    hch, cch = chain(HC.evs_since(host, seq0), aid), chain(HC.evs_since(client, seq0), aid)
    kinds, ckinds = [e["kind"] for e in hch], [e["kind"] for e in cch]
    seqs = [e["seq"] for e in hch]
    moves = [m for m in HC.cam_moves(cam1["client"]) if m.get("seq") in seqs]
    sup = sup_delta(cam0, cam1)
    ev.update(settled=ok, chain=[(e["seq"], e["kind"]) for e in hch], clientChain=[(e["seq"], e["kind"]) for e in cch],
              staged=HC.cam_offset(staged), client0=HC.cam_view(cam0["client"]),
              client1=HC.cam_view(cam1["client"], seq0), hostSup=sup)
    cells = {"S1-shot": ctx_cell(new, "host", "shoot", H_ID, ok and kinds == S1_CHAIN and ckinds == kinds,
                                 f"; its evs host {kinds} client {ckinds} (want {S1_CHAIN} on both)")}
    if cells["S1-shot"][0]:
        shot, hit = [s for s, k in zip(seqs, kinds) if k == "shot"], [s for s, k in zip(seqs, kinds) if k == "hit"]
        got = sorted((m.get("seq"), m.get("reason")) for m in moves)
        want = [(shot[0], "follow"), (hit[0], "hit_level")]
        fu = [m.get("unit") for m in moves if m.get("reason") == "follow"]
        cells["S1-moves"] = (got == want and fu == [H_ID],
                             f"client camera.moves in the chain {got} (want {want}); follow unit {fu} (want [{H_ID}])")
        o1 = HC.cam_offset(cam1["client"])
        cells["S1-offset"] = (o1 != HC.cam_offset(staged), f"client offset after {o1} (want != the staged "
                                                           f"{HC.cam_offset(staged)}: the shot was followed)")
        cells["S1-host"] = (sup == SUP_ZERO, f"host camera.suppressed delta {sup} (want all 0: the host's own shot)")
    else:
        cells.update(unreached(("S1-moves", "S1-offset", "S1-host"), "S1-shot"))
    cells["S1-common"] = common(host, client, crash0)
    return cells, ev


def row_s2(host, client, crash0):
    rifle, clip = CSH.give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    ev = {"rifle": rifle, "clip": clip, "C": CSH.place(host, client, C_ID, S2_C_TILE, S2_DIR),
          "tu": CSH.set_tu_both(host, client, C_ID, TU_MAX), "notes": []}
    staged = HC.stage_camera(host, HC.K_HOSTFAR_TERROR)
    cam0 = HC.cam_snap(host, client)
    ctx0, seq0 = es(host, "closedContexts"), es(host, "lastSeqEmitted") or 0
    host.ok({"cmd": "set_seed", "seed": SEED_S2})
    si = CSH.send_intent(host, client, CSH.shoot_req(C_ID, "snap", rifle, clip, S2_TARGET), ev["notes"])
    ok, ev["settleS"] = wait_until(lambda: bool(CSH.mine(new_ctx(host, ctx0), "intent", "shoot", C_ID))
                                   and CSH.order_done(host, client), STEP_S)
    idle(host, client, ev)
    cam1 = HC.cam_snap(host, client)
    new = new_ctx(host, ctx0)
    one = CSH.mine(new, "intent", "shoot", C_ID)
    aid = one[0].get("actionId") if len(one) == 1 else None
    hch, cch = chain(HC.evs_since(host, seq0), aid), chain(HC.evs_since(client, seq0), aid)
    kinds, ckinds = [e["kind"] for e in hch], [e["kind"] for e in cch]
    sup = sup_delta(cam0, cam1)
    ev.update(answer=si.get("answer"), settled=ok, chain=[(e["seq"], e["kind"]) for e in hch],
              clientChain=[(e["seq"], e["kind"]) for e in cch], staged=HC.cam_offset(staged),
              host0=HC.cam_view(cam0["host"]), host1=HC.cam_view(cam1["host"], seq0), hostSup=sup,
              clientMoves=[(m.get("seq"), m.get("reason"), m.get("unit")) for m in HC.cam_moves(cam1["client"])
                           if m.get("seq") in [e["seq"] for e in hch]])
    cells = {"S2-shot": ctx_cell(new, "intent", "shoot", C_ID, ok and kinds == S2_CHAIN and ckinds == kinds,
                                 f"; its evs host {kinds} client {ckinds} (want {S2_CHAIN} on both); answer "
                                 f"{si.get('answer')}")}
    if cells["S2-shot"][0]:
        o1 = HC.cam_offset(cam1["host"])
        cells["S2-host"] = (sup == SUP_ZERO and o1 != HC.cam_offset(staged),
                            f"host camera.suppressed delta {sup} (want all 0; red: {S2_RED}); offset {o1} (want != "
                            f"the staged {HC.cam_offset(staged)}: the partner's shot was followed)")
    else:
        cells.update(unreached(("S2-host",), "S2-shot"))
    cells["S2-common"] = common(host, client, crash0)
    return cells, ev


def row_p1(host, client, crash0):
    ev = {"HP": CSH.place(host, client, HP_ID, P1_HP_TILE, P1_DIR),
          "C2": CSH.place(host, client, C2_ID, P1_C2_TILE, P1_DIR)}
    for uid in (HP_ID, C2_ID):
        ev[f"morale{uid}"] = CSH.both(host, client, {"cmd": "battle_set_unit_state", "unit": uid, "morale": 0},
                                      ("morale", "status")).get("morale")
    rec = {"notes": [], "dismissed": [], "cycles": []}
    cam0 = HC.cam_snap(host, client)
    seq0 = es(host, "lastSeqEmitted") or 0
    TCU.cycle(host, client, SEED_P1, rec, "P1")
    cam1 = HC.cam_snap(host, client)
    hev, cev = HC.evs_since(host, seq0), HC.evs_since(client, seq0)
    pseqs = [e["seq"] for e in hev if e["kind"] == "panic"]
    pl = host_payloads(host, pseqs)
    panics = {}
    for s in pseqs:
        p = (pl.get(s) or {}).get("payload") or {}
        panics.setdefault(str(p.get("unit")), []).append((s, p.get("mode")))
    applied = {e["seq"] for e in cev}
    sup = sup_delta(cam0, cam1)
    moves = [(m.get("seq"), m.get("reason"), m.get("unit")) for m in HC.cam_moves(cam1["client"], seq0)]
    ev.update(rec=rec, panics=panics, appliedOnClient=sorted(s for s in pseqs if s in applied), hostSup=sup,
              host1=HC.cam_offset(cam1["host"]), clientMoves=moves,
              units={uid: [ubrief(units(gc).get(uid)) for gc in (host, client)] for uid in (HP_ID, C2_ID)})
    roll = {uid: panics.get(str(uid)) or [] for uid in (HP_ID, C2_ID)}
    ok = (not rec["notes"] and all(len(v) == 1 and v[0][1] in PANIC_MODES and v[0][0] in applied
                                   for v in roll.values()))
    cells = {"P1-roll": (ok, f"host panic evs per unit {roll} (want one each for {HP_ID} and {C2_ID}, mode in "
                             f"{PANIC_MODES}, applied on the client); cycle notes {rec['notes']} (want none)")}
    if ok:
        need = [(roll[HP_ID][0][0], "panic_centre", HP_ID), (roll[C2_ID][0][0], "panic_centre", C2_ID)]
        miss = [x for x in need if x not in moves]
        cells["P1-client"] = (not miss, f"client camera.moves lack {miss} (want {need}; the partner's panic "
                                        f"{need[0]} is the red)")
        cells["P1-host"] = (sup == SUP_ZERO, f"host camera.suppressed delta over the cycle {sup} (want all 0; red: "
                                             f"panic 1 and walkLevel for C2's flee)")
    else:
        cells.update(unreached(("P1-client", "P1-host"), "P1-roll"))
    cells["P1-common"] = common(host, client, crash0)
    return cells, ev


ROW_FNS = {"O1": row_o1, "W1": row_w1, "W2": row_w2, "O2": row_o2, "W3": row_w3, "S1": row_s1, "S2": row_s2,
           "P1": row_p1}


# ===================== boot F =====================


def bring_up(host, client):
    """HC's boot body with key 46652: roster pin, terror skirmish on map seed 1, MAP_FP on both, pin_ai_neutral,
    wait_host_idle, every bucket EQUAL; the seats TASK 0 pinned."""
    guarded("F", lambda: HC.bring_up_lobby_roster_pinned(host, client, KEY), host, client)
    seated = {}
    guarded("F", lambda: session.drive_to_battlescape(
        host, client, seated, mission=HC.MISSION, seat_count=2,
        pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": HC.SEED_MAP})), host, client)
    pinned = guarded("F", lambda: session.pin_ai_neutral(host, client, tag="d249u"), host, client)
    guarded("F", lambda: session.wait_host_idle(host, client, timeout=STEP_S), host, client)
    guarded("F", lambda: assert_hash_clean(host, client, full=True, what="bring-up"), host, client)
    fps = [battle_state(gc).get("mapFingerprint") for gc in (host, client)]
    uh = units(host)
    hseat = sorted(i for i, u in uh.items() if u.get("coop") == 0 and u.get("faction") == 0 and not u.get("isOut"))
    bad = []
    if fps != [HC.MAP_FP, HC.MAP_FP]:
        bad.append(f"mapFingerprint host/client {fps} (want {HC.MAP_FP})")
    if seated.get("soldierIds") != [C_ID, C2_ID] or hseat[:2] != [H_ID, HP_ID] or not pinned:
        bad.append(f"seated {seated.get('soldierIds')} (want {[C_ID, C2_ID]}), host seat {hseat} (want "
                   f"{[H_ID, HP_ID]} first), pinned {len(pinned or [])} (want >= 1)")
    if bad:
        capture("F", "; ".join(bad), host, client)
        raise Miss("F")
    print(f"[d249u] boot ok: {HC.MISSION} MAP_FP {fps[0]!r} seated {seated.get('soldierIds')} host seat {hseat} "
          f"pinned {len(pinned)}", flush=True)


def shut(*gcs):
    for gc in gcs:
        try:
            if gc is not None and gc.proc is not None and gc.proc.poll() is None:
                gc.shutdown()
        except Exception as e:
            print(f"[d249u] shutdown {gc.name}: {type(e).__name__}: {str(e)[:200]}", flush=True)


def main():
    t0 = time.time()
    crash0 = session._crash_log_snapshot()
    host = GameClient("host", 49898, make_user_dir("d249u_f_host", options={"coopGhostStepper": True}))
    client = GameClient("client", 49899, make_user_dir("d249u_f_client", options={"coopGhostStepper": True}))
    failed = []
    try:
        try:
            bring_up(host, client)
        except Miss:
            for row, order in ROWS:
                why = "boot (FIXTURE-STOP, see the CAPTURE F line)"
                failed += verdict(row, order, {n: (False, why) for n in order},
                                  {"error": "boot"})
        else:
            for row, order in ROWS:
                failed += run_row(row, order, lambda fn=ROW_FNS[row]: fn(host, client, crash0), host, client)
    finally:
        shut(host, client)
    print("ALL ROWS PASS" if not failed else f"FAILED: {len(failed)} cell(s): {failed}", flush=True)
    print(f"test_follow_camera: {'PASS' if not failed else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not failed else 2)


if __name__ == "__main__":
    main()
