"""R5-U3 S-A rows P1, D2, D1 (boot A, gm2: the client plays the aliens, seat 1): the human alien side plays by the
player-side rules vanilla gives X-COM - its panic acts out at its side start (R5-V1) and its units skip only the AI's
weapon-use delay.

Spec: docs repo rewrite/prompts/r5u3_pvp_rules.md section (f) test_pvp_rules.py, with its ORCHESTRATOR RULINGS
R-U3-A-1 (A staged on A_D2_TILE before D2), R-U3-A-2 ("the bomb gone on both" is a D2-admit cell, D2-census is census
equality) and R-U3-A-3 (D2 is C20's vanilla dive, two waypoints on LAUNCH_W, with lever-dropped gear inside the blast).
Constants: rewrite/r5u3-task0/sa/CONSTANTS.md (TASK 0 boots Aa, abcap, Ac-Ag on the unchanged build).

Boot A (key 48677): BER.boot_e6 (STR_SMALL_SCOUT, map seed 1, gamemode 2), every live unit's reactions 0, A morale 0.
  P1  host set_seed SEED_P1 right before its END TURN; A's status read on both before any NextTurnState closes (the
      roll); drive_side_change to side 1; a bounded wait (PANIC_S) for the host's `panic` ev, every host infobox
      dismissed host-only, leftover NextTurnStates closed.
      P1-roll   A status 8 (PANICKING) on both at the roll (precondition)
      P1-act    exactly one host `panic` ev {unit A, mode flee or freeze} and its bt_action_end on the same actionId
                since the press; the client applied the same seqs
      P1-after  A status 0, TU 0, morale M0 + 15 on both
  D2  reset A {status 0, TU A_TU, morale 100} (both); A on A_D2_TILE facing A_D2_DIR (teleported only when it does
      not stand there, S2); launcher + bomb (lever, both); DROPS by battle_drop (both); host set_seed SEED_D2; the
      client's launch lever with waypoints [LAUNCH_W, LAUNCH_W]; settle.
      D2-turn   turn 1, side 1 on both (precondition)
      D2-canuse can_use_weapon {A, launcher, none} true on both, read before the launch
      D2-admit  one new host context {intent, launch, A}; its ev kinds = D2_KINDS; no client lastDeny for the iseq;
                coopIntentsSent.shoot +1; inFlight null; the bomb and the dropped gear gone on both
      D2-census item census (id, type, owner) equal on host and client
  D1  battle_strip_unit A (both); a grenade (lever, both); TU A_TU (both); the client's real-UI PRIME (TAB, the
      right-hand box, key 49, the fuse key 48 when the fuse screen opens).
      D1-canuse can_use_weapon {A, grenade, none} true on both, before the press
      D1-press  the fuse screen opened on the client; one new host context {intent, prime, A}; coopIntentsSent.prime
                +1; the grenade's fuse 0 on both
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane
crash folder. EVIDENCE only: the panic mode, host infoboxes, the client's warningText and menu rows, the explosion.

RED on the unchanged build (commit A1): P1-act, P1-after, D2-canuse, D2-admit, D1-canuse, D1-press; every other cell
PASS. One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A
boot step past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails the
rows that need it "staging". run in the foreground to completion. ONE run is the result, no
skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_rules.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
from repro_atom_side_begin import drive_side_change  # noqa: E402
from test_delta_core import both  # noqa: E402
from test_delta_items import items_by_id  # noqa: E402
from test_seat_pacing import tab_select  # noqa: E402
from test_turn_baton import RHAND_NTH, click_nth  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
from test_client_shoot import new_contexts, send_intent, shoot_req, set_tu_both, place, jt, RHAND_CENTRE  # noqa: E402
from test_host_combat import evs_since  # noqa: E402
from test_ai_origins import host_payloads, voxel_tile  # noqa: E402
from test_messages import poll_host_box, client_quiet  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402

KEY = "48677"
A_ID = 1000000                    # the only alien (STR_SECTOID_SOLDIER), the client's (seat 1), spawn (27,12,0) dir 5
A_TU = 54                         # A's TU at bring-up
M0 = 0                            # A's morale after the roll; P1-after wants M0 + 15
SEED_P1 = 1                       # host set_seed before its END TURN: A rolls STATUS_PANICKING (8) on both
STATUS_STANDING, STATUS_PANICKING = 0, 8
FACTION_HOSTILE = 1
PANIC_S = 15                      # spec (f): the bounded wait for the host's panic ev after both screens close
STEP_S = 30
A_D2_TILE, A_D2_DIR = (20, 4, 0), 2   # open ground, a straight open path east to LAUNCH_W
LAUNCH_W = (32, 4, 0)             # the LAUNCH_W rule: 12 tiles east, Chebyshev >= 12 from every live unit
SEED_D2 = 1
D2_KINDS = ["shot", "shot", "explosion", "bt_action_end"]   # the dive at turn 3 (TASK 0 Ae, Af, Ag)
DROPS = (("STR_BLASTER_LAUNCHER", (32, 4, 0)), ("STR_RIFLE", (33, 4, 0)))   # gear inside the blast
KEY_PRIME, KEY_FUSE_0 = 49, 48    # keyBattleActionItem1 (PRIME for a grenade); PrimeGrenadeState button 0
CURSOR_TARGETING = (2, 3, 4, 5)
ROWS = (("P1", ("P1-roll", "P1-act", "P1-after", "P1-common")),
        ("D2", ("D2-turn", "D2-canuse", "D2-admit", "D2-census", "D2-common")),
        ("D1", ("D1-canuse", "D1-press", "D1-common")))


def es(gc, key):
    return event_state(gc).get(key)


def a_view(gc):
    u = G3F.units(gc).get(A_ID) or {}
    return {k: u.get(k) for k in ("status", "tu", "morale", "x", "y", "z", "direction", "isOut")}


def census(gc):
    return {i: (v.get("type"), v.get("owner")) for i, v in items_by_id(gc).items()}


def can_use(gc, iid):
    r = gc.cmd({"cmd": "can_use_weapon", "unit": A_ID, "item": iid, "action": "none"})
    return r.get("canUse") if r.get("ok") else f"probe failed: {r.get('error')}"


def wait_until(pred, timeout, interval):
    t0 = time.time()
    while True:
        if pred():
            return True, round(time.time() - t0, 2)
        if time.time() - t0 > timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)


def close_leftovers(host, client):
    """Close a NextTurnState left on either top (drive_side_change can return before one is pushed, TASK 0 F11011)."""
    closed = []
    for gc in (host, client):
        if G3F.top(gc) == "NextTurnState":
            gc.cmd({"cmd": "close_nextturn"})
            closed.append(gc.name)
    return closed


def settle(host, client, ev):
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]


# ===================== P1 =====================


def row_p1(host, client, crash0):
    ev, cells = {}, {}
    seq0 = es(host, "lastSeqEmitted") or 0
    host.ok({"cmd": "set_seed", "seed": SEED_P1})
    ev["press"] = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    ok, ev["sideS"] = wait_until(lambda: battle_state(host).get("side") == 1 and battle_state(client).get("side") == 1,
                                 STEP_S, 0.1)
    roll = [a_view(host), a_view(client)]
    ev.update(roll=roll, rollStacks=[G3F.stack(host), G3F.stack(client)])
    cells["P1-roll"] = (ok and [r["status"] for r in roll] == [STATUS_PANICKING] * 2,
                        f"side 1 on both {ok} ({ev['sideS']} s); A status host/client at the roll "
                        f"{[r['status'] for r in roll]} (want [8, 8], SEED_P1 {SEED_P1})")
    try:
        drive_side_change(host, client, FACTION_HOSTILE, timeout=STEP_S)
    except Exception as e:
        ev["sideError"] = str(e)[:300]
    rec, closed = {"hostBoxes": []}, []

    def panic_done():
        poll_host_box(host, rec, "P1")
        closed.extend(close_leftovers(host, client))
        hev = evs_since(host, seq0)
        pids = [e["actionId"] for e in hev if e["kind"] == "panic"]
        return bool(pids) and any(e["kind"] == "bt_action_end" and e["actionId"] == pids[0] for e in hev) \
            and es(host, "busyOwnerSeat") == -1
    ev["panicWait"] = wait_until(panic_done, PANIC_S, 0.2)
    settle(host, client, ev)
    poll_host_box(host, rec, "P1 after")
    ev["quiet"] = client_quiet(client)
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    cmap = {e["seq"]: (e["kind"], e["actionId"]) for e in cev}
    panics = [e for e in hev if e["kind"] == "panic"]
    pl = host_payloads(host, [e["seq"] for e in panics], timeout=3) if panics else {}
    ev.update(hostEvs=[(e["seq"], e["kind"], e["actionId"]) for e in hev], hostBoxes=rec["hostBoxes"],
              leftoverClosed=closed, panicPayloads={s: v.get("payload") for s, v in pl.items()},
              warningText=[battle_state(gc).get("warningText") for gc in (host, client)])
    act = []
    if len(panics) != 1:
        act.append(f"host panic evs {[(e['seq'], e['actionId']) for e in panics]} (want exactly one)")
    else:
        p, aid = panics[0], panics[0]["actionId"]
        payload = (pl.get(p["seq"]) or {}).get("payload") or {}
        mine = [e for e in hev if e["actionId"] == aid]
        ends = [e["seq"] for e in mine if e["kind"] == "bt_action_end"]
        if payload.get("unit") != A_ID or payload.get("mode") not in ("flee", "freeze"):
            act.append(f"panic payload {payload} (want unit {A_ID}, mode flee or freeze)")
        if len(ends) != 1:
            act.append(f"bt_action_end evs of actionId {aid}: {ends} (want exactly one)")
        bad = [(e["seq"], e["kind"], cmap.get(e["seq"])) for e in mine if cmap.get(e["seq"]) != (e["kind"], aid)]
        if bad:
            act.append(f"client log lacks the host's evs of actionId {aid}: (seq, kind, client entry) {bad}")
    cells["P1-act"] = (not act, "; ".join(act) or f"one panic ev {ev['panicPayloads']} and its bt_action_end, "
                                                   f"the client the same seqs")
    after = [a_view(host), a_view(client)]
    ev["after"] = after
    want = (STATUS_STANDING, 0, M0 + 15)
    got = [(a["status"], a["tu"], a["morale"]) for a in after]
    cells["P1-after"] = (got == [want, want], f"A (status, TU, morale) host/client {got} (want {want} on both)")
    cells["P1-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== D2 =====================


def drop_gear(host, client):
    """DROPS by battle_drop on both (client first, F607); the ids from the replies, each looked up by type (S25)."""
    ids = {}
    for typ, t in DROPS:
        rc = client.cmd({"cmd": "battle_drop", "x": t[0], "y": t[1], "z": t[2], "item": typ})
        rh = host.cmd({"cmd": "battle_drop", "x": t[0], "y": t[1], "z": t[2], "item": typ})
        assert rh.get("ok") and rc.get("ok") and rh.get("ids") == rc.get("ids"), (
            f"battle_drop {typ} at {t}: host {rh} client {rc} (want ok and equal ids)")
        session.wait_seq_barrier(host, client)
        for i in rh["ids"]:
            seen = [census(host).get(i), census(client).get(i)]
            assert seen == [(typ, -1), (typ, -1)], f"dropped {i}: census host/client {seen} (want {typ} on the floor)"
            ids[i] = typ
    return ids


def stage_d2(host, client):
    m = (host, client)
    ev = {"reset": G3F.guarded("D2 staging", lambda: both(host, client, {
        "cmd": "battle_set_unit_state", "unit": A_ID, "status": STATUS_STANDING, "tu": A_TU, "morale": 100},
        ("status", "tu", "morale")), m).get("tu")}
    ev["place"] = G3F.guarded("D2 staging", lambda: place(host, client, A_ID, A_D2_TILE, A_D2_DIR), m)
    g = G3F.guarded("D2 staging", lambda: both(host, client, {
        "cmd": "battle_give", "unit": A_ID, "item": "STR_BLASTER_LAUNCHER", "ammo": "STR_BLASTER_BOMB",
        "slot": "right", "clear_hands": True}, ("weaponId", "ammoId")), m)
    ev.update(launcher=g["weaponId"], bomb=g["ammoId"])
    ev["drops"] = G3F.guarded("D2 staging", lambda: drop_gear(host, client), m)
    ev["A"] = [a_view(host), a_view(client)]
    return ev


def row_d2(host, client, crash0, st):
    ev, cells = dict(st), {}
    ts = [(battle_state(gc).get("turn"), battle_state(gc).get("side")) for gc in (host, client)]
    cells["D2-turn"] = (ts == [(1, 1), (1, 1)], f"(turn, side) host/client {ts} (want (1, 1) on both)")
    cu = [can_use(host, st["launcher"]), can_use(client, st["launcher"])]
    cells["D2-canuse"] = (cu == [True, True], f"can_use_weapon {{A, launcher, none}} host/client {cu} (want true on both)")
    b_ctx, sent0 = es(host, "closedContexts") or [], dict(es(client, "coopIntentsSent") or {})
    seq0 = es(host, "lastSeqEmitted") or 0
    host.ok({"cmd": "set_seed", "seed": SEED_D2})
    req = shoot_req(A_ID, "launch", st["launcher"], st["bomb"], LAUNCH_W)
    req["plan"]["waypoints"] = [jt(LAUNCH_W), jt(LAUNCH_W)]   # C20's vanilla dive
    notes = []
    sent = send_intent(host, client, req, notes, timeout=STEP_S)
    settle(host, client, ev)
    new = new_contexts(b_ctx, es(host, "closedContexts"))
    hev = evs_since(host, seq0)
    deny, sent1, infl = es(client, "lastDeny") or {}, es(client, "coopIntentsSent") or {}, es(client, "inFlight")
    expl = [e["seq"] for e in hev if e["kind"] == "explosion"]
    pl = host_payloads(host, expl, timeout=3) if expl else {}
    ih, ic = census(host), census(client)
    gone = {i: [i not in ih, i not in ic] for i in [st["bomb"]] + sorted(st["drops"])}
    ev.update(intent={k: sent.get(k) for k in ("sent", "iseq", "answer")}, notes=notes, lastDeny=deny, newCtx=new,
              hostEvs=[(e["seq"], e["kind"], e["actionId"]) for e in hev], gone=gone,
              explosion=[(v["payload"].get("power"), v["payload"].get("radius"),
                          voxel_tile(v["payload"].get("centreVoxel"))) for v in pl.values()],
              sentDelta=sent1.get("shoot", 0) - sent0.get("shoot", 0), Aafter=[a_view(host), a_view(client)])
    adm = []
    if len(new) != 1 or (new[0].get("origin"), new[0].get("kind"), new[0].get("actorId")) != ("intent", "launch", A_ID):
        adm.append(f"new host closedContexts {new} (want exactly one {{intent, launch, {A_ID}}})")
    else:
        kinds = [e["kind"] for e in hev if e["actionId"] == new[0].get("actionId")]
        if kinds != D2_KINDS:
            adm.append(f"ev kinds of actionId {new[0].get('actionId')} {kinds} (want {D2_KINDS})")
    if sent.get("iseq") and deny.get("iseq") == sent.get("iseq"):
        adm.append(f"client lastDeny {deny} for the order's iseq {sent.get('iseq')} (want none)")
    if ev["sentDelta"] != 1 or infl is not None:
        adm.append(f"client coopIntentsSent.shoot +{ev['sentDelta']} (want +1), inFlight {infl} (want None)")
    if any(v != [True, True] for v in gone.values()):
        adm.append(f"gone on host/client {gone} (want the bomb {st['bomb']} and the dropped gear gone on both)")
    cells["D2-admit"] = (not adm, "; ".join(adm) or f"one {{intent, launch, A}} with {D2_KINDS}, bomb and gear gone")
    diff = sorted(i for i in set(ih) | set(ic) if ih.get(i) != ic.get(i))
    cells["D2-census"] = (not diff, f"item census host vs client: {len(ih)} / {len(ic)} items, differing ids "
                                    f"{[(i, ih.get(i), ic.get(i)) for i in diff][:12]} (want none)")
    cells["D2-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== D1 =====================


def stage_d1(host, client):
    m = (host, client)
    rc = client.cmd({"cmd": "battle_strip_unit", "unit": A_ID})
    rh = host.cmd({"cmd": "battle_strip_unit", "unit": A_ID})
    if not (rh.get("ok") and rc.get("ok")) or rh.get("deleted") != rc.get("deleted"):
        G3F.capture("D1 staging", f"battle_strip_unit host {rh} client {rc}", m)
        raise G3F.Miss("D1 staging")
    G3F.guarded("D1 staging", lambda: session.wait_seq_barrier(host, client), m)
    g = G3F.guarded("D1 staging", lambda: both(host, client, {
        "cmd": "battle_give", "unit": A_ID, "item": "STR_GRENADE", "slot": "right", "clear_hands": True},
        ("weaponId",)), m)
    G3F.guarded("D1 staging", lambda: set_tu_both(host, client, A_ID, A_TU), m)
    return {"stripped": rh.get("deleted"), "grenade": g["weaponId"]}


def prime_press(client, ev):
    """The client's real-UI PRIME on A: TAB, a leftover targeting cancelled, the right-hand box (self-verified), key 49,
    the fuse key 48 only when PrimeGrenadeState opens. Records the press; never retries."""
    ev["tab"] = tab_select(client, A_ID)
    if battle_state(client).get("cursorType") in CURSOR_TARGETING:
        click_nth(client, RHAND_NTH)
    r = click_nth(client, RHAND_NTH)
    ev["rhand"] = (r.get("baseX"), r.get("baseY"))
    assert ev["tab"] and ev["rhand"] == RHAND_CENTRE, f"the client's TAB {ev['tab']} / right-hand click {ev['rhand']} " \
                                                      f"(want True / {RHAND_CENTRE})"
    ok, _s = wait_until(lambda: G3F.top(client) == "ActionMenuState", 5, 0.1)
    assert ok, f"no ActionMenuState on the client (top {G3F.top(client)})"
    ev["rows"] = len([w for w in client.cmd({"cmd": "list_widgets"}).get("widgets", [])
                      if w.get("visible") and "ActionMenuItem" in w.get("type", "")])
    client.ok({"cmd": "inject_input", "kind": "key", "key": KEY_PRIME})
    wait_until(lambda: G3F.top(client) != "ActionMenuState", 5, 0.1)
    ev["topAfterKey"] = G3F.top(client)
    if ev["topAfterKey"] == "PrimeGrenadeState":
        client.ok({"cmd": "inject_input", "kind": "key", "key": KEY_FUSE_0})
        wait_until(lambda: G3F.top(client) == "BattlescapeState", 5, 0.1)
    ev["topAfter"] = G3F.top(client)


def row_d1(host, client, crash0, st):
    ev, cells = dict(st), {}
    gid = st["grenade"]
    cu = [can_use(host, gid), can_use(client, gid)]
    cells["D1-canuse"] = (cu == [True, True], f"can_use_weapon {{A, grenade, none}} host/client {cu} (want true on both)")
    b_ctx, sent0 = es(host, "closedContexts") or [], dict(es(client, "coopIntentsSent") or {})
    try:
        prime_press(client, ev)
    except Exception as e:
        ev["pressError"] = str(e)[:300]
    wait_until(lambda: (es(client, "coopIntentsSent") or {}).get("prime", 0) > sent0.get("prime", 0), 2, 0.1)
    settle(host, client, ev)
    new = new_contexts(b_ctx, es(host, "closedContexts"))
    fuse = [(items_by_id(gc).get(gid) or {}).get("fuse") for gc in (host, client)]
    delta = (es(client, "coopIntentsSent") or {}).get("prime", 0) - sent0.get("prime", 0)
    ev.update(newCtx=new, fuse=fuse, primeDelta=delta, warningText=battle_state(client).get("warningText"),
              inFlight=es(client, "inFlight"))
    pr = []
    if ev.get("topAfterKey") != "PrimeGrenadeState":
        pr.append(f"the client's top after key {KEY_PRIME} {ev.get('topAfterKey')} (want PrimeGrenadeState; "
                  f"{ev.get('pressError', 'no press error')})")
    if len(new) != 1 or (new[0].get("origin"), new[0].get("kind"), new[0].get("actorId")) != ("intent", "prime", A_ID):
        pr.append(f"new host closedContexts {new} (want exactly one {{intent, prime, {A_ID}}})")
    if delta != 1 or ev["inFlight"] is not None:
        pr.append(f"client coopIntentsSent.prime +{delta} (want +1), inFlight {ev['inFlight']} (want None)")
    if fuse != [0, 0]:
        pr.append(f"grenade {gid} fuse host/client {fuse} (want 0 on both)")
    cells["D1-press"] = (not pr, "; ".join(pr) or "fuse screen, one {intent, prime, A}, fuse 0 on both")
    cells["D1-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot A =====================


def boot_a():
    host = GameClient("host", None, make_user_dir("r5u3_a_host"))
    client = GameClient("client", None, make_user_dir("r5u3_a_client"))
    m = (host, client)
    try:
        try:
            G3F.guarded("A", lambda: BER.boot_e6(host, client, KEY), m)
            G3F.guarded("A", lambda: G3F.reactions_zero(host, client), m)
            crash0 = session._crash_log_snapshot()
            G3F.guarded("A", lambda: both(host, client, {"cmd": "battle_set_unit_state", "unit": A_ID, "morale": 0},
                                          ("morale",)), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE A line)")
        rows = dict(ROWS)
        fails = G3F.run_row("P1", rows["P1"], lambda: row_p1(host, client, crash0))
        try:
            st2 = stage_d2(host, client)
        except G3F.Miss:
            st2 = None
        fails += (G3F.run_row("D2", rows["D2"], lambda: row_d2(host, client, crash0, st2)) if st2
                  else G3F.fail_all((("D2", rows["D2"]),), "staging (see the CAPTURE D2 staging line)"))
        try:
            st1 = stage_d1(host, client)
        except G3F.Miss:
            st1 = None
        fails += (G3F.run_row("D1", rows["D1"], lambda: row_d1(host, client, crash0, st1)) if st1
                  else G3F.fail_all((("D1", rows["D1"]),), "staging (see the CAPTURE D1 staging line)"))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_a()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_rules: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
