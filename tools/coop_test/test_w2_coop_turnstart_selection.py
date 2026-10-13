"""W2-H41 S-B rows T1, C1, CT, C2, HT, C3, F, C4 (boot B, classic co-op, gamemode 1: both seats play X-COM): at each
X-COM turn start the second player keeps the soldier it holds while that soldier is still its own and selectable, with
the action actor, HUD and camera on it, as vanilla and the co-op host do (L-H40-1, the orchestrator's ruling R-LH40-1,
design-D6, W2-H6-SEL, D171 (a)); when the held unit is no longer its own (the alien it mind-controlled reverted) it gets
its first own soldier in unit order (vanilla's fallback, QH41-3 (a)).

Spec: docs repo rewrite/prompts/w2h41_coop_selection_turnstart_mc.md section (f) test_w2_coop_turnstart_selection.py,
orchestrator rulings QH41-1 .. QH41-6 (a). Constants: rewrite/w2h41-task0/sb/CONSTANTS.md (TASK 0 boots Ba, Bb on this
file's chain, unchanged build e0fe835ca; every pin, sequence, record seq and HUD number equal on both boots; VERDICT
CONFIRMED).

Boot B (key 49042, dirs w2h41_b_host / _client, default options): test_w2_turn_cues' bring-up with this key (roster
pinned, SEED_MAP; asserts: map fingerprint, seated [8, 9], unit order on both, pinned [X], coopGamemode 1 on both,
turnMode parallel on both). No input on either machine except the presses each row names.
  T1  turn 1, two reads READ_GAP_S apart.  T1-pre client (selectedId, actor) (T1_SEL, T1_SEL) and host (HOST_T1, HOST_T1)
      at both reads (precondition).
  C1  END TURN to turn 2 (TCU.cycle), c0 / h0 = the client's / host's selection right before the cycle; two reads; the
      client's camera move records since the cycle's first seq.  C1-keep client (selectedId, actor) == (c0, c0) at both
      reads; C1-hud the client's hud equals c0's units[] view on HUD_FIELDS at the second read; C1-cam the client's moves
      as (reason, unit) == [(CAM_REASON, c0)]; C1-host host (selectedId, actor) == (h0, h0) at both reads (guard).
  CT  the client's Tab once at turn 2 (real key 9), read PRESS_READ_S later.  CT-tab the client's selectedId in SEATED,
      not the one before the press, actor equal (guard).
  C2  END TURN to turn 3: C2-keep, C2-hud, C2-cam, C2-host as C1.
  HT  the host's Tab once at turn 3, read PRESS_READ_S later.  HT-tab host (HT_NEXT, HT_NEXT), the client unchanged.
  C3  END TURN to turn 4: C3-keep, C3-hud, C3-cam, C3-host (HT_NEXT kept) as C1.
  F   MSC.stage_c; the partner's P mind-controls X (host set_seed SEED_FB, the host-local psi_attack lever); the client's
      Tab until it holds X (<= TAB_MAX_C presses).  F-mc X (faction, originalFaction, mindControllerId) == (0, 1, P) on
      both and the client holds X with its actor equal (precondition).
  C4  END TURN to turn 5: X reverts, the held unit is no longer the client's.  C4-fall client (FALLBACK, FALLBACK) at
      both reads and X (faction, originalFaction) == (1, 1) on both; C4-cam the client's moves == [(CAM_REASON,
      FALLBACK)]; C4-host the host on one of its own seat-0 units with its actor equal at both reads (never h0: the psi
      lever left the host on P, F15792).
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new crash file.

RED on the unchanged build (commit B1): C1-keep, C1-hud, C1-cam, C2-keep, C2-hud, C2-cam, C3-keep, C3-hud, C3-cam (18 of
27 cells PASS). GREEN (B2): all 27 PASS. One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict;
every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails every row "boot"; a staging
step past its bound fails the rows that need it "staging". Lever pairs go to the client first (F607). WV-D95: run in the
foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0 only when every cell passes,
else 2.

Run:  python tools/coop_test/test_w2_coop_turnstart_selection.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, pin_ai_neutral  # noqa: E402
from test_w2_ai_origins import bring_up_lobby_roster_pinned  # noqa: E402
import test_w2_turn_cues as TCU  # noqa: E402
import test_w2_mc_seat_coop as MSC  # noqa: E402
import test_w2_mc_seat_tally as MST  # noqa: E402
import test_w2_battle_end_rules as BER  # noqa: E402
import test_r5_pvp_gm3 as G3F  # noqa: E402
import test_w2_host_combat as HC  # noqa: E402
import test_w2_client_shoot as CSH  # noqa: E402

KEY = "49042"
HOST_DIR, CLIENT_DIR = "w2h41_b_host", "w2h41_b_client"    # default options
SEATED = TCU.SEATED               # [8, 9], the client seat's soldiers
S0_IDS = MSC.S0_IDS               # [10..14], the host seat's soldiers
X = TCU.A_ID                      # 1000000, the one alien (seat NONE, pinned AI-neutral)
P = 8                             # the partner's (client seat's) soldier that mind-controls X in row F
GAMEMODE = 1                      # classic co-op skirmish
T1_SEL = 8                        # the client's entry selection: the first of SEATED in unit order (Ba, Bb)
HOST_T1 = TCU.H_ID                # 10, the host's entry selection (Ba, Bb)
HT_NEXT = 11                      # the host's next own live unit after 10 in unit order (Ba, Bb)
FALLBACK = 8                      # the first of SEATED in unit order that is live and faction PLAYER after C4 (Ba, Bb)
SEED_FB = 2                       # host set_seed before the psi_attack lever: 8 takes X at turn 4 (Ba, Bb first try)
HUD_FIELDS = ("tu", "energy", "health", "morale")   # hud == the selected unit's units[] view on all four (Ba, Bb)
CAM_REASON = "side_start"         # the client's camera record at its X-COM side_begin (TCP CoopGhost::onSideStart)
MC_WAIT_S, TAB_MAX_C = 6, 3
TAB_GAP_S, PRESS_READ_S, READ_GAP_S = 0.4, 0.6, 1.0
KEY_NEXT = 9                      # Tab (keyBattleNextUnit)
CYC_CELLS = ("keep", "hud", "cam", "host", "common")
ROWS = (("T1", ("T1-pre", "T1-common")),
        ("C1", tuple(f"C1-{c}" for c in CYC_CELLS)),
        ("CT", ("CT-tab", "CT-common")),
        ("C2", tuple(f"C2-{c}" for c in CYC_CELLS)),
        ("HT", ("HT-tab", "HT-common")),
        ("C3", tuple(f"C3-{c}" for c in CYC_CELLS)),
        ("F", ("F-mc", "F-common")),
        ("C4", ("C4-fall", "C4-cam", "C4-host", "C4-common")))

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
    pinned = pin_ai_neutral(host, client, tag="w2h41b")
    assert pinned == [X], f"pin_ai_neutral pinned {pinned} (want [{X}])"
    mode = [es(host, "turnMode"), es(client, "turnMode")]
    assert mode == ["parallel"] * 2, f"turnMode host/client {mode} (want parallel on both)"
    session.wait_host_idle(host, client, timeout=30)
    return {"mapFP": fp, "seated": seated.get("soldierIds"), "pinned": pinned, "gamemode": gm, "turnMode": mode}


def xview(gc):
    """X's (faction, originalFaction, mindControllerId) on this machine."""
    u = G3F.units(gc).get(X) or {}
    return (u.get("faction"), u.get("originalFaction"), u.get("mindControllerId"))


def view(gc):
    b = battle_state(gc)
    return {k: b.get(k) for k in ("side", "turn", "selectedId", "currentActionActorId", "cursorType", "hud")}


def sa(v):
    return (v["selectedId"], v["currentActionActorId"])


def reads(host, client):
    """Two views of both machines READ_GAP_S apart."""
    r1 = {"host": view(host), "client": view(client)}
    time.sleep(READ_GAP_S)
    return [r1, {"host": view(host), "client": view(client)}]


def hud_is(gc, uid):
    """(ok, {field: (hud, units[] view)}): `gc`'s painted hud equals `uid`'s units[] view on every HUD_FIELDS field."""
    b = battle_state(gc)
    hud, u = b.get("hud") or {}, session.units_by_id(b).get(uid) or {}
    cmp_ = {f: (hud.get(f), u.get(f)) for f in HUD_FIELDS}
    return all(a == v for a, v in cmp_.values()), cmp_


def tab_once(gc):
    """`gc` presses Tab (real key 9) once; its view PRESS_READ_S after the press."""
    t0 = time.time()
    gc.cmd({"cmd": "inject_input", "kind": "key", "key": KEY_NEXT})
    time.sleep(max(0.0, t0 + PRESS_READ_S - time.time()))
    return view(gc)


def tabs(gc, n, stop=None):
    """`gc` presses Tab (real key 9) up to `n` times (stops once it holds `stop`); after each press its (selectedId,
    actor, cursorType) TAB_GAP_S later."""
    seq = []
    for _ in range(n):
        t0 = time.time()
        gc.cmd({"cmd": "inject_input", "kind": "key", "key": KEY_NEXT})
        time.sleep(max(0.0, t0 + TAB_GAP_S - time.time()))
        b = battle_state(gc)
        seq.append((b.get("selectedId"), b.get("currentActionActorId"), b.get("cursorType")))
        if stop is not None and b.get("selectedId") == stop:
            break
    return seq


def mc(host, client, actor, seed, rec, where):
    """The capture's mc_stage with ONE pinned seed: `actor` gets a psi amp and psiSkill 100, X psiStrength 0, the actor's
    TU 255, the host's set_seed right before the host-local psi_attack lever; a bounded wait (MC_WAIT_S) for X faction 0
    on the host with every box dismissed on its own machine; then settled. Returns the evidence; ev["miss"] when X is
    not faction 0 on both."""
    ev = {"amp": MST.give_amp(host, client, actor)}
    MST.set_stat_both(host, client, actor, "psiSkill", 100)
    MST.set_stat_both(host, client, X, "psiStrength", 0)
    ev["tuActor"] = CSH.set_tu_both(host, client, actor, 255)
    n0 = len(rec["boxes"])
    host.ok({"cmd": "set_seed", "seed": seed})
    r = host.cmd({"cmd": "battle_action", "action": "psi_attack", "unit": actor, "target": X, "weapon_id": ev["amp"]})
    ev["lever"] = {k: r.get(k) for k in ("ok", "tuCost", "tuHave", "error")}
    ev["wait"] = BER.wait_until(lambda: (MST.poll_box(host, rec, where) or True)
                                and (MST.poll_box(client, rec, where) or True)
                                and es(host, "busyOwnerSeat") == -1 and not battle_state(host).get("isBusy")
                                and (G3F.units(host).get(X) or {}).get("faction") == 0, MC_WAIT_S, 0.2)
    MST.settle(host, client, rec, where)
    ev["boxes"] = [(b["machine"], b["texts"]) for b in rec["boxes"][n0:]]
    b = battle_state(host)
    ev["hostAfter"] = (b.get("selectedId"), b.get("currentActionActorId"), b.get("cursorType"))
    ev["x"] = [xview(host), xview(client)]
    if not all(v[0] == 0 for v in ev["x"]):
        ev["miss"] = f"X not faction 0 on both within {MC_WAIT_S} s: {ev['x']}"
    return ev


def cyc(host, client, name):
    """END TURN to the next X-COM turn with no other input: the held ids, TCU.cycle, two reads, the client's camera move
    records since the cycle's first seq."""
    c0, h0 = battle_state(client).get("selectedId"), battle_state(host).get("selectedId")
    seq0 = es(host, "lastSeqEmitted") or 0
    rec = {"notes": [], "dismissed": [], "cycles": []}
    TCU.cycle(host, client, None, rec, name)
    r = reads(host, client)
    ok_hud, cmp_ = hud_is(client, c0)
    moves = [(m.get("seq"), m.get("reason"), m.get("unit")) for m in HC.cam_moves(HC.camera_of(client), seq0)]
    ev = {"c0": c0, "h0": h0, "seq0": seq0, "reads": r, "moves": moves, "cycles": rec["cycles"],
          "dismissed": rec["dismissed"], "notes": rec["notes"], "x": [xview(host), xview(client)],
          "panicSkipped": es(client, "coopClientPanicSkipped")}
    return c0, h0, r, moves, (ok_hud, cmp_), ev


def keep_cells(name, c0, h0, r, moves, hud, host, client, crash0):
    keep = [sa(x["client"]) for x in r]
    hold = [sa(x["host"]) for x in r]
    rm = [(m[1], m[2]) for m in moves]
    return {f"{name}-keep": (keep == [(c0, c0)] * 2, f"client (selectedId, currentActionActorId) at the two reads {keep} "
                                                     f"(want {(c0, c0)} at both; unchanged build: its other soldier, "
                                                     f"F15780)"),
            f"{name}-hud": (hud[0], f"client hud vs unit {c0}'s units[] view at the second read {{field: (hud, unit)}} "
                                    f"{hud[1]} (want equal on {list(HUD_FIELDS)}; unchanged build: the other soldier's "
                                    f"numbers)"),
            f"{name}-cam": (rm == [(CAM_REASON, c0)], f"client camera moves since the cycle's first seq (reason, unit) "
                                                      f"{rm} (want {[(CAM_REASON, c0)]}; seqs {[m[0] for m in moves]} "
                                                      f"EVIDENCE)"),
            f"{name}-host": (hold == [(h0, h0)] * 2, f"host (selectedId, currentActionActorId) at the two reads {hold} "
                                                     f"(want {(h0, h0)} at both)"),
            f"{name}-common": G3F.common(host, client, crash0)}


def staging_fail(row, why):
    return {n: (False, f"staging ({why})") for n in dict(ROWS)[row]}, {"error": f"staging: {why}"}


# ===================== rows =====================


def row_t1(host, client, crash0):
    r = reads(host, client)
    ok_c, cmp_c = hud_is(client, T1_SEL)
    ok_h, cmp_h = hud_is(host, HOST_T1)
    u = session.units_by_id(battle_state(client))
    ev = {"reads": r, "hud": {"client": (ok_c, cmp_c), "host": (ok_h, cmp_h)},
          "views89": {uid: {f: (u.get(uid) or {}).get(f) for f in HUD_FIELDS} for uid in SEATED}}
    cs, hs = [sa(x["client"]) for x in r], [sa(x["host"]) for x in r]
    return {"T1-pre": (cs == [(T1_SEL, T1_SEL)] * 2 and hs == [(HOST_T1, HOST_T1)] * 2,
                       f"client (selectedId, actor) at the two reads {cs} (want {(T1_SEL, T1_SEL)}); host {hs} (want "
                       f"{(HOST_T1, HOST_T1)})"),
            "T1-common": G3F.common(host, client, crash0)}, ev


def row_cyc(host, client, crash0, name):
    c0, h0, r, moves, hud, ev = cyc(host, client, name)
    return keep_cells(name, c0, h0, r, moves, hud, host, client, crash0), ev


def row_ct(host, client, crash0):
    s0 = battle_state(client).get("selectedId")
    v = tab_once(client)
    ev = {"before": s0, "after": v, "host": view(host)}
    s, a = sa(v)
    return {"CT-tab": (s in SEATED and s != s0 and a == s, f"client selectedId {s0} -> {s}, actor {a} (want one of "
                                                          f"{SEATED}, not {s0}, actor equal)"),
            "CT-common": G3F.common(host, client, crash0)}, ev


def row_ht(host, client, crash0):
    c0 = sa(view(client))
    s0 = battle_state(host).get("selectedId")
    v = tab_once(host)
    c1 = sa(view(client))
    ev = {"before": s0, "after": v, "client": [c0, c1]}
    return {"HT-tab": (sa(v) == (HT_NEXT, HT_NEXT) and c1 == c0,
                       f"host (selectedId, actor) {s0} -> {sa(v)} (want {(HT_NEXT, HT_NEXT)}); client {c0} -> {c1} "
                       f"(want unchanged)"),
            "HT-common": G3F.common(host, client, crash0)}, ev


def row_f(host, client, crash0, state):
    rec = {"boxes": []}
    try:
        G3F.guarded("F staging", lambda: MSC.stage_c(host, client, rec), (host, client))
    except G3F.Miss:
        state["f"] = "MSC.stage_c (see the CAPTURE F staging line)"
        return staging_fail("F", state["f"])
    state["f"] = "the F levers did not complete"
    ev = mc(host, client, P, SEED_FB, rec, "F")
    del state["f"]
    if "miss" in ev:
        state["f"] = ev["miss"]
    ev["presses"] = tabs(client, TAB_MAX_C, stop=X)
    v = ev["client"] = view(client)
    want = (0, 1, P)
    return {"F-mc": (ev["x"] == [want, want] and sa(v) == (X, X),
                     f"X (faction, originalFaction, mindControllerId) host/client {ev['x']} (want {want} on both; seed "
                     f"{SEED_FB}); client (selectedId, actor) {sa(v)} after Tab {[s[0] for s in ev['presses']]} (want "
                     f"{(X, X)} within {TAB_MAX_C} presses)"),
            "F-common": G3F.common(host, client, crash0)}, ev


def row_c4(host, client, crash0):
    c0, h0, r, moves, hud, ev = cyc(host, client, "C4")
    fall = [sa(x["client"]) for x in r]
    hold = [sa(x["host"]) for x in r]
    xf = [x[:2] for x in ev["x"]]
    rm = [(m[1], m[2]) for m in moves]
    return {"C4-fall": (fall == [(FALLBACK, FALLBACK)] * 2 and xf == [(1, 1)] * 2,
                        f"client (selectedId, actor) at the two reads {fall} (want {(FALLBACK, FALLBACK)}; held "
                        f"{c0}); X (faction, originalFaction) host/client {xf} (want (1, 1) on both: reverted)"),
            "C4-cam": (rm == [(CAM_REASON, FALLBACK)], f"client camera moves since the cycle's first seq (reason, unit) "
                                                       f"{rm} (want {[(CAM_REASON, FALLBACK)]}; seqs "
                                                       f"{[m[0] for m in moves]} EVIDENCE)"),
            "C4-host": (all(s in S0_IDS and a == s for s, a in hold),
                        f"host (selectedId, actor) at the two reads {hold} (want one of {S0_IDS}, actor equal; held "
                        f"{h0} before the cycle, F15792)"),
            "C4-common": G3F.common(host, client, crash0)}, ev


# ===================== boot B =====================


def boot_b(host, client):
    rows = dict(ROWS)
    try:
        info = G3F.guarded("B", lambda: boot(host, client), (host, client))
    except G3F.Miss:
        return G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE B line)")
    crash0 = session._crash_log_snapshot()
    print(f"[w2h41] boot B ok: {info}", flush=True)
    state = {}
    fails = G3F.run_row("T1", rows["T1"], lambda: row_t1(host, client, crash0))
    fails += G3F.run_row("C1", rows["C1"], lambda: row_cyc(host, client, crash0, "C1"))
    fails += G3F.run_row("CT", rows["CT"], lambda: row_ct(host, client, crash0))
    fails += G3F.run_row("C2", rows["C2"], lambda: row_cyc(host, client, crash0, "C2"))
    fails += G3F.run_row("HT", rows["HT"], lambda: row_ht(host, client, crash0))
    fails += G3F.run_row("C3", rows["C3"], lambda: row_cyc(host, client, crash0, "C3"))
    fails += G3F.run_row("F", rows["F"], lambda: row_f(host, client, crash0, state))
    if "f" in state:
        fails += G3F.verdict("C4", rows["C4"], *staging_fail("C4", f"F: {state['f']}"))
    else:
        fails += G3F.run_row("C4", rows["C4"], lambda: row_c4(host, client, crash0))
    return fails


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir(HOST_DIR))
    client = GameClient("client", None, make_user_dir(CLIENT_DIR))
    try:
        fails = boot_b(host, client)
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_w2_coop_turnstart_selection: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
