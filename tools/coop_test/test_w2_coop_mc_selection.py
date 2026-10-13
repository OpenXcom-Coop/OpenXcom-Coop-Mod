"""W2-H41 S-A rows T, M, HT, HK, HC, CYC, HM, HMT (boot A, classic co-op, gamemode 1: both seats play X-COM): a co-op
host never selects an alien its partner mind-controlled (L-H40-3, the orchestrator's ruling R-LH40-3, owner D87 (b) as
written, design-D6): its Tab skips the alien and a click on it answers "Not one of your soldiers" and keeps the host's own
soldier; the partner still selects its alien; the host's own mind-controlled alien stays selectable on the host.

Spec: docs repo rewrite/prompts/w2h41_coop_selection_turnstart_mc.md section (f) test_w2_coop_mc_selection.py, orchestrator
rulings QH41-1 .. QH41-6 (a). Constants: rewrite/w2h41-task0/sa/CONSTANTS.md (TASK 0 boots Aa, Ab on this file's chain,
unchanged build e0fe835ca; every pin equal on both boots; VERDICT CONFIRMED).

Boot A (key 49041, dirs w2h41_a_host / _client, default options): test_w2_mc_seat_coop's boot C (BER.boot_classic: the one
alien X 1000000 pinned AI-neutral; seats [10..14] host / [8, 9] client; turnMode parallel), the unit order asserted on both,
every unit's reactions 0, MSC.stage_c (X (15,2,0), 8 (14,5,0), 9 (16,5,0)).
  T    the host's Tab x5 before any mind control (turn 1).  T-seq the five selectedIds == T_SEQ (guard).
  M    the partner's P mind-controls X (host set_seed SEED_MA, the host-local psi_attack lever).  M-mc X (faction,
       originalFaction, mindControllerId) == (0, 1, P) on both (precondition).
  HT   the host's Tab x6 after the partner's mind control, two reads READ_GAP_S apart.  HT-seq == HT_SEQ; HT-hold host
       (selectedId, actor) == (HT_SEQ[-1], HT_SEQ[-1]) at both reads; HT-hud the host's hud equals that unit's units[] view
       on HUD_FIELDS at the second read; HT-partner the client on one of S1_IDS, actor equal, at both reads (guard).
  HK   the host Tab-selects H, waits for an empty coopWaitText, clicks X's tile (ONE map_tile_click).  HK-pre host on H;
       HK-click the answer ok / verified / clicked; HK-effect within SEL_S the host shows TEXT_NOT_YOURS and at SEL_S holds
       (H, H), coopLocalExecBlocked / coopWalkArmEntered unchanged.
  HC   the partner's Tab reaches its alien.  HC-reach the client's selectedId and actor X within TAB_MAX_C presses (guard).
  CYC  END TURN to turn 2 (TCU.cycle).  CYC-turn (side, turn) (0, 2) on both, no cycle note, X (1, 1, P) on both
       (precondition: X reverted). The client's selection is EVIDENCE only (S-B changes it).
  HM   X and H on TCU's C5r tiles, H mind-controls X (SEED_HM).  HM-mc X == (0, 1, H) on both (precondition).
  HMT  the host's Tab x5, two reads, then the client's Tab x3.  HMT-reach the five == HM_SEQ, host (X, X) at both reads,
       hud on X at the second (guard); HMT-client none of the client's three is X, each in S1_IDS with its actor (guard).
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new crash file.

RED on the unchanged build (commit A1): HT-seq, HT-hold, HT-hud, HK-effect (18 of 22 cells PASS). GREEN (A2): all 22 PASS.
One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step
past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails the rows that need it
"staging". Lever pairs go to the client first (F607). WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE
run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_w2_coop_mc_selection.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_w2_mc_seat_coop as MSC  # noqa: E402
import test_w2_mc_seat_tally as MST  # noqa: E402
import test_w2_battle_end_rules as BER  # noqa: E402
import test_w2_turn_cues as TCU  # noqa: E402
import test_r5_pvp_gm3 as G3F  # noqa: E402
import test_r5_pvp_rules as PR  # noqa: E402
import test_w2_client_shoot as CSH  # noqa: E402
import test_rw_seat_pacing as RSP  # noqa: E402
import test_rv_tile_click as RV2  # noqa: E402

KEY = "49041"
HOST_DIR, CLIENT_DIR = "w2h41_a_host", "w2h41_a_client"    # default options
X = MSC.X_ID                      # 1000000, the one alien (seat NONE, pinned AI-neutral)
P = 8                             # the partner's (client seat's) soldier that mind-controls X at turn 1
H = 10                            # the host seat's first soldier (HK's selection, HM's mind control at turn 2)
S0_IDS, S1_IDS = MSC.S0_IDS, MSC.S1_IDS   # [10..14] host seat, [8, 9] client seat
SEED_MA = 2                       # host set_seed before the psi_attack lever: 8 takes X at turn 1 (Aa, Ab first try)
SEED_HM = 2                       # host set_seed before the psi_attack lever: 10 takes X at turn 2 (Aa, Ab first try)
T_SEQ = [11, 12, 13, 14, 10]      # the host's own live units after 10 in unit order, wrapping (Aa, Ab)
HT_SEQ = [10, 11, 12, 13, 14, 10]   # the host's own live units after 8 (the lever's actor, F15792), wrapping, 6 presses
HM_SEQ = [11, 12, 13, 14, X]      # the host's own live units after 10 in unit order, then its own MC'd X (Aa, Ab)
HUD_FIELDS = ("tu", "energy", "health", "morale")   # hud == the selected unit's units[] view on all four (Aa, Ab)
TEXT_NOT_YOURS = "Not one of your soldiers"   # the host's click on the partner's 9 (Aa, Ab HKs: from 0.1 s)
MC_WAIT_S, TEXT_WAIT_S, SEL_S, TAB_MAX_C = 6, 8, 2.0, 3
TAB_GAP_S, READ_GAP_S = 0.4, 1.0
KEY_NEXT = 9                      # Tab (keyBattleNextUnit)
ROWS = (("T", ("T-seq", "T-common")),
        ("M", ("M-mc", "M-common")),
        ("HT", ("HT-seq", "HT-hold", "HT-hud", "HT-partner", "HT-common")),
        ("HK", ("HK-pre", "HK-click", "HK-effect", "HK-common")),
        ("HC", ("HC-reach", "HC-common")),
        ("CYC", ("CYC-turn", "CYC-common")),
        ("HM", ("HM-mc", "HM-common")),
        ("HMT", ("HMT-reach", "HMT-client", "HMT-common")))

es = G3F.es


def boot(host, client):
    """MSC.boot_c with this file's key, the unit order on both, every unit's reactions 0, MSC.stage_c."""
    info = MSC.boot_c(host, client, KEY)
    order = [[u["id"] for u in battle_state(gc).get("units", [])] for gc in (host, client)]
    assert order == [TCU.UNIT_ORDER] * 2, f"unit order host/client {order} (want {TCU.UNIT_ORDER} on both)"
    info["reactions"] = len(G3F.reactions_zero(host, client))
    rec = {"boxes": []}
    MSC.stage_c(host, client, rec)
    info["order"] = order[0]
    return info


def xview(gc):
    """X's (faction, originalFaction, mindControllerId) on this machine."""
    u = G3F.units(gc).get(X) or {}
    return (u.get("faction"), u.get("originalFaction"), u.get("mindControllerId"))


def tile_of(gc, uid):
    u = G3F.units(gc).get(uid) or {}
    return (u.get("x"), u.get("y"), u.get("z"))


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


def view(gc):
    b = battle_state(gc)
    return {k: b.get(k) for k in ("side", "turn", "selectedId", "currentActionActorId", "cursorType", "coopWaitText",
                                  "warningText", "hud")}


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
    ev["xTile"] = [tile_of(host, X), tile_of(client, X)]
    if not all(v[0] == 0 for v in ev["x"]):
        ev["miss"] = f"X not faction 0 on both within {MC_WAIT_S} s: {ev['x']}"
    return ev


def staging_fail(row, why):
    return {n: (False, f"staging ({why})") for n in dict(ROWS)[row]}, {"error": f"staging: {why}"}


# ===================== rows =====================


def row_t(host, client, crash0):
    seq = tabs(host, 5)
    ev = {"seq": seq, "client": view(client)}
    got = [s[0] for s in seq]
    return {"T-seq": (got == T_SEQ, f"host Tab x5 selectedIds {got} (want {T_SEQ})"),
            "T-common": G3F.common(host, client, crash0)}, ev


def row_m(host, client, crash0, rec, state):
    state["m"] = "the M levers did not complete"
    ev = mc(host, client, P, SEED_MA, rec, "M")
    del state["m"]
    if "miss" in ev:
        state["m"] = ev["miss"]
    ev["reads"] = reads(host, client)
    want = (0, 1, P)
    return {"M-mc": (ev["x"] == [want, want], f"X (faction, originalFaction, mindControllerId) host/client {ev['x']} "
                                              f"(want {want} on both; seed {SEED_MA})"),
            "M-common": G3F.common(host, client, crash0)}, ev


def row_ht(host, client, crash0):
    seq = tabs(host, 6)
    r = reads(host, client)
    want = HT_SEQ[-1]
    ok_hud, cmp_ = hud_is(host, want)
    ev = {"seq": seq, "reads": r, "texts": MST.texts_of(host), "x": [xview(host), xview(client)]}
    got = [s[0] for s in seq]
    hold = [(x["host"]["selectedId"], x["host"]["currentActionActorId"]) for x in r]
    ps = [(x["client"]["selectedId"], x["client"]["currentActionActorId"]) for x in r]
    return {"HT-seq": (got == HT_SEQ, f"host Tab x6 selectedIds {got} (want {HT_SEQ}; unchanged build: the sixth is X "
                                      f"{X}, F15786)"),
            "HT-hold": (hold == [(want, want)] * 2, f"host (selectedId, currentActionActorId) at the two reads {hold} "
                                                    f"(want {(want, want)} at both; unchanged build: X / X)"),
            "HT-hud": (ok_hud, f"host hud vs unit {want}'s units[] view at the second read {{field: (hud, unit)}} "
                               f"{cmp_} (want equal on {list(HUD_FIELDS)}; unchanged build: X's numbers)"),
            "HT-partner": (all(s in S1_IDS and a == s for s, a in ps),
                           f"client (selectedId, currentActionActorId) at the two reads {ps} (want one of {S1_IDS}, "
                           f"actor equal)"),
            "HT-common": G3F.common(host, client, crash0)}, ev


def row_hk(host, client, crash0):
    ev = {"tab": RSP.tab_select(host, H)}
    ev["textWait"] = PR.wait_until(lambda: battle_state(host).get("coopWaitText") == "", TEXT_WAIT_S, 0.1)
    ev["sel0"] = battle_state(host).get("selectedId")
    blocked0, arm0 = es(host, "coopLocalExecBlocked"), es(host, "coopWalkArmEntered")
    tile = tile_of(host, X)
    ev["tile"] = [tile, tile_of(client, X)]
    t0 = time.time()
    a = ev["answer"] = RV2.click(host, tile)
    text_at, seen = None, []
    while time.time() - t0 < SEL_S:
        b = battle_state(host)
        if b.get("coopWaitText") == TEXT_NOT_YOURS and text_at is None:
            text_at = round(time.time() - t0, 2)
        if b.get("selectedId") not in seen:
            seen.append(b.get("selectedId"))
        time.sleep(0.1)
    b = battle_state(host)
    at = (b.get("selectedId"), b.get("currentActionActorId"))
    blocked1, arm1 = es(host, "coopLocalExecBlocked"), es(host, "coopWalkArmEntered")
    ev.update(textAt=text_at, selSeen=seen, at=at, atS=round(time.time() - t0, 2), text=b.get("coopWaitText"),
              warningText=b.get("warningText"), counters=[(blocked0, blocked1), (arm0, arm1)])
    pre_ok = ev["sel0"] == H and ev["textWait"][0]
    eff_ok = text_at is not None and at == (H, H) and blocked1 == blocked0 and arm1 == arm0
    return {"HK-pre": (pre_ok, f"host selectedId {ev['sel0']} after tab_select (want {H}); empty coopWaitText wait "
                               f"{ev['textWait']} (want True within {TEXT_WAIT_S} s)"),
            "HK-click": (RV2.clicked(a), f"host map_tile_click {tile}: {a} (want ok, verified, clicked)"),
            "HK-effect": (eff_ok, f"host coopWaitText {TEXT_NOT_YOURS!r} at {text_at} s (want within {SEL_S} s); host "
                                  f"(selectedId, currentActionActorId) at {ev['atS']} s {at} (want {(H, H)}); "
                                  f"coopLocalExecBlocked {blocked0} -> {blocked1}, coopWalkArmEntered {arm0} -> {arm1} "
                                  f"(want both unchanged; unchanged build: X {X} selected, no text)"),
            "HK-common": G3F.common(host, client, crash0)}, ev


def row_hc(host, client, crash0):
    seq = tabs(client, TAB_MAX_C, stop=X)
    v = view(client)
    ev = {"seq": seq, "client": v, "host": view(host)}
    got = (v["selectedId"], v["currentActionActorId"])
    return {"HC-reach": (got == (X, X) and any(s[0] == X for s in seq),
                         f"client Tab selectedIds {[s[0] for s in seq]} (want X {X} within {TAB_MAX_C} presses); client "
                         f"(selectedId, currentActionActorId) {got} (want {(X, X)})"),
            "HC-common": G3F.common(host, client, crash0)}, ev


def row_cyc(host, client, crash0):
    rec = {"notes": [], "dismissed": [], "cycles": []}
    TCU.cycle(host, client, None, rec, "CYC")
    hv, cv = view(host), view(client)
    x = [xview(host), xview(client)]
    ev = {"rec": rec, "host": hv, "client": cv, "x": x}
    st = [(hv["side"], hv["turn"]), (cv["side"], cv["turn"])]
    want = (1, 1, P)
    return {"CYC-turn": (st == [(0, 2)] * 2 and not rec["notes"] and x == [want, want],
                         f"(side, turn) host/client {st} (want (0, 2) on both); cycle notes {rec['notes']} (want "
                         f"none); X host/client {x} (want {want} on both: reverted)"),
            "CYC-common": G3F.common(host, client, crash0)}, ev


def row_hm(host, client, crash0, rec, state):
    m = (host, client)
    try:
        pl = G3F.guarded("HM staging", lambda: {
            "X": CSH.place(host, client, X, TCU.C5_A_TILE, TCU.C5_A_DIR),
            "H": CSH.place(host, client, H, TCU.C5_H_TILE, TCU.C5_H_DIR)}, m)
    except G3F.Miss:
        state["hm"] = "the C5r placement (see the CAPTURE HM staging line)"
        return staging_fail("HM", state["hm"])
    pl["tiles"] = {u: [tile_of(host, u), tile_of(client, u)] for u in (X, H)}
    state["hm"] = "the HM levers did not complete"
    ev = mc(host, client, H, SEED_HM, rec, "HM")
    del state["hm"]
    ev["place"] = pl
    if "miss" in ev:
        state["hm"] = ev["miss"]
    want = (0, 1, H)
    return {"HM-mc": (ev["x"] == [want, want], f"X (faction, originalFaction, mindControllerId) host/client {ev['x']} "
                                               f"(want {want} on both; seed {SEED_HM})"),
            "HM-common": G3F.common(host, client, crash0)}, ev


def row_hmt(host, client, crash0):
    seq = tabs(host, 5)
    r = reads(host, client)
    ok_hud, cmp_ = hud_is(host, X)
    cseq = tabs(client, 3)
    ev = {"seq": seq, "reads": r, "cseq": cseq}
    got = [s[0] for s in seq]
    hold = [(x["host"]["selectedId"], x["host"]["currentActionActorId"]) for x in r]
    return {"HMT-reach": (got == HM_SEQ and hold == [(X, X)] * 2 and ok_hud,
                          f"host Tab x5 selectedIds {got} (want {HM_SEQ}); host (selectedId, currentActionActorId) at "
                          f"the two reads {hold} (want {(X, X)} at both); hud vs X's units[] view at the second read "
                          f"{cmp_} (want equal on {list(HUD_FIELDS)})"),
            "HMT-client": (all(s != X and s in S1_IDS and a == s for s, a, _c in cseq) and len(cseq) == 3,
                           f"client Tab x3 (selectedId, actor, cursor) {cseq} (want never X {X}, each one of {S1_IDS} "
                           f"with its actor equal)"),
            "HMT-common": G3F.common(host, client, crash0)}, ev


# ===================== boot A =====================


def boot_a(host, client):
    rows = dict(ROWS)
    try:
        info = G3F.guarded("A", lambda: boot(host, client), (host, client))
    except G3F.Miss:
        return G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE A line)")
    crash0 = session._crash_log_snapshot()
    print(f"[w2h41] boot A ok: {info}", flush=True)
    rec, state = {"boxes": []}, {}

    def gated(row, need, fn):
        if need in state:
            return G3F.verdict(row, rows[row], *staging_fail(row, f"{need.upper()}: {state[need]}"))
        return G3F.run_row(row, rows[row], fn)

    fails = G3F.run_row("T", rows["T"], lambda: row_t(host, client, crash0))
    fails += G3F.run_row("M", rows["M"], lambda: row_m(host, client, crash0, rec, state))
    fails += gated("HT", "m", lambda: row_ht(host, client, crash0))
    fails += gated("HK", "m", lambda: row_hk(host, client, crash0))
    fails += gated("HC", "m", lambda: row_hc(host, client, crash0))
    fails += G3F.run_row("CYC", rows["CYC"], lambda: row_cyc(host, client, crash0))
    fails += G3F.run_row("HM", rows["HM"], lambda: row_hm(host, client, crash0, rec, state))
    fails += gated("HMT", "hm", lambda: row_hmt(host, client, crash0))
    return fails


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir(HOST_DIR))
    client = GameClient("client", None, make_user_dir(CLIENT_DIR))
    try:
        fails = boot_a(host, client)
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_w2_coop_mc_selection: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
