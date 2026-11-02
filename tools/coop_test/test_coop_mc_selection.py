"""A co-op host never selects an alien its partner mind-controlled (classic co-op, gamemode 1: both seats play X-COM):
its Tab skips the alien and a click on it answers "Not one of your soldiers" and keeps the host's own soldier; the
partner still selects its alien; the host's own mind-controlled alien stays selectable on the host.

Boot classic (key 49041, dirs coop_mc_selection_host / _client, default options): MSC.boot_seated (BER.boot_classic:
the one alien X 1000000 pinned AI-neutral; seats [10..14] host / [8, 9] client; turnMode parallel), the unit order
asserted on both, every unit's reactions 0, MSC.stage_tiles (X (15,2,0), 8 (14,5,0), 9 (16,5,0)).
  host_tab_first  the host's Tab x5 before any mind control (turn 1). host_tab_first-seq the five selectedIds ==
       FIRST_SEQ (guard).
  partner_mc  the partner's P mind-controls X (host set_seed SEED_PARTNER_MC, the host-local psi_attack test command).
       partner_mc-taken X (faction, originalFaction, mindControllerId) == (0, 1, P) on both (precondition).
  host_tab_skips  the host's Tab x6 after the partner's mind control, two reads READ_GAP_S apart. host_tab_skips-seq
       == SKIP_SEQ; host_tab_skips-hold host (selectedId, actor) == (SKIP_SEQ[-1], SKIP_SEQ[-1]) at both reads;
       host_tab_skips-hud the host's hud equals that unit's units[] view on HUD_FIELDS at the second read;
       host_tab_skips-partner the client on one of S1_IDS, actor equal, at both reads (guard).
  host_click_refused  the host Tab-selects H, waits for an empty coopWaitText, clicks X's tile (ONE map_tile_click).
       host_click_refused-pre host on H; host_click_refused-click the answer ok / verified / clicked;
       host_click_refused-effect within SEL_S the host shows TEXT_NOT_YOURS and at SEL_S holds (H, H),
       coopLocalExecBlocked / coopWalkArmEntered unchanged.
  partner_tab_reaches  the partner's Tab reaches its alien. partner_tab_reaches-alien the client's selectedId and actor
       X within TAB_MAX_C presses (guard).
  turn_cycle  END TURN to turn 2 (TCU.cycle). turn_cycle-turn (side, turn) (0, 2) on both, no cycle note, X (1, 1, P)
       on both (precondition: X reverted). The client's selection is EVIDENCE only (test_coop_turnstart_selection
       checks it).
  host_mc  X and H on TCU's stun-rod tiles (STUN_A_TILE, STUN_H_TILE), H mind-controls X (SEED_HOST_MC).
       host_mc-taken X == (0, 1, H) on both (precondition).
  host_tab_own_mc  the host's Tab x5, two reads, then the client's Tab x3. host_tab_own_mc-reach the five ==
       OWN_MC_SEQ, host (X, X) at both reads, hud on X at the second (guard); host_tab_own_mc-client none of the
       client's three is X, each in S1_IDS with its actor (guard).
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new crash file.

A host whose Tab and click do not skip the partner's alien fails host_tab_skips-seq, host_tab_skips-hold,
host_tab_skips-hud and host_click_refused-effect (18 of 22 cells pass).
One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot
step past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails the rows
that need it "staging". Test command pairs go to the client first. Run in the foreground to completion. ONE run is
the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_coop_mc_selection.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_mc_seat_coop as MSC  # noqa: E402
import test_mc_seat_tally as MST  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_turn_cues as TCU  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_rules as PR  # noqa: E402
import test_client_shoot as CSH  # noqa: E402
import test_seat_pacing as RSP  # noqa: E402
import test_tile_click as TTC  # noqa: E402

KEY = "49041"
HOST_DIR, CLIENT_DIR = "coop_mc_selection_host", "coop_mc_selection_client"    # default options
X = MSC.X_ID                      # 1000000, the one alien (seat NONE, pinned AI-neutral)
P = 8                             # the partner's (client seat's) soldier that mind-controls X at turn 1
H = 10                            # the host seat's first soldier (host_click_refused's selection, host_mc's mind
                                  # control at turn 2)
S0_IDS, S1_IDS = MSC.S0_IDS, MSC.S1_IDS   # [10..14] host seat, [8, 9] client seat
SEED_PARTNER_MC = 2               # host set_seed before the psi_attack test command: 8 takes X at turn 1, first try
SEED_HOST_MC = 2                  # host set_seed before the psi_attack test command: 10 takes X at turn 2, first try
FIRST_SEQ = [11, 12, 13, 14, 10]      # the host's own live units after 10 in unit order, wrapping
SKIP_SEQ = [10, 11, 12, 13, 14, 10]   # the host's own live units after 8 (the psi_attack test command selects its
                                      # actor on the host), wrapping, 6 presses
OWN_MC_SEQ = [11, 12, 13, 14, X]      # the host's own live units after 10 in unit order, then its own MC'd X
HUD_FIELDS = ("tu", "energy", "health", "morale")   # hud == the selected unit's units[] view on all four
TEXT_NOT_YOURS = "Not one of your soldiers"   # the host's click on the partner's 9 (shown from 0.1 s after the click)
MC_WAIT_S, TEXT_WAIT_S, SEL_S, TAB_MAX_C = 6, 8, 2.0, 3
TAB_GAP_S, READ_GAP_S = 0.4, 1.0
KEY_NEXT = 9                      # Tab (keyBattleNextUnit)
ROWS = (("host_tab_first", ("host_tab_first-seq", "host_tab_first-common")),
        ("partner_mc", ("partner_mc-taken", "partner_mc-common")),
        ("host_tab_skips", ("host_tab_skips-seq", "host_tab_skips-hold", "host_tab_skips-hud", "host_tab_skips-partner",
                            "host_tab_skips-common")),
        ("host_click_refused", ("host_click_refused-pre", "host_click_refused-click", "host_click_refused-effect",
                                "host_click_refused-common")),
        ("partner_tab_reaches", ("partner_tab_reaches-alien", "partner_tab_reaches-common")),
        ("turn_cycle", ("turn_cycle-turn", "turn_cycle-common")),
        ("host_mc", ("host_mc-taken", "host_mc-common")),
        ("host_tab_own_mc", ("host_tab_own_mc-reach", "host_tab_own_mc-client", "host_tab_own_mc-common")))

es = G3F.es


def boot(host, client):
    """MSC.boot_seated with this file's key, the unit order on both, every unit's reactions 0, MSC.stage_tiles."""
    info = MSC.boot_seated(host, client, KEY)
    order = [[u["id"] for u in battle_state(gc).get("units", [])] for gc in (host, client)]
    assert order == [TCU.UNIT_ORDER] * 2, f"unit order host/client {order} (want {TCU.UNIT_ORDER} on both)"
    info["reactions"] = len(G3F.reactions_zero(host, client))
    rec = {"boxes": []}
    MSC.stage_tiles(host, client, rec)
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
    """`actor` mind-controls X with ONE fixed seed: `actor` gets a psi amp and psiSkill 100, X psiStrength 0, the
    actor's TU 255, the host's set_seed right before the host-local psi_attack test command; a bounded wait (MC_WAIT_S)
    for X faction 0 on the host with every box dismissed on its own machine; then settled. Returns the evidence;
    ev["miss"] when X is not faction 0 on both."""
    ev = {"amp": MST.give_amp(host, client, actor)}
    MST.set_stat_both(host, client, actor, "psiSkill", 100)
    MST.set_stat_both(host, client, X, "psiStrength", 0)
    ev["tuActor"] = CSH.set_tu_both(host, client, actor, 255)
    n0 = len(rec["boxes"])
    host.ok({"cmd": "set_seed", "seed": seed})
    r = host.cmd({"cmd": "battle_action", "action": "psi_attack", "unit": actor, "target": X, "weapon_id": ev["amp"]})
    ev["command"] = {k: r.get(k) for k in ("ok", "tuCost", "tuHave", "error")}
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


def row_host_tab_first(host, client, crash0):
    seq = tabs(host, 5)
    ev = {"seq": seq, "client": view(client)}
    got = [s[0] for s in seq]
    return {"host_tab_first-seq": (got == FIRST_SEQ, f"host Tab x5 selectedIds {got} (want {FIRST_SEQ})"),
            "host_tab_first-common": G3F.common(host, client, crash0)}, ev


def row_partner_mc(host, client, crash0, rec, state):
    state["partner_mc"] = "the partner_mc test commands did not complete"
    ev = mc(host, client, P, SEED_PARTNER_MC, rec, "partner_mc")
    del state["partner_mc"]
    if "miss" in ev:
        state["partner_mc"] = ev["miss"]
    ev["reads"] = reads(host, client)
    want = (0, 1, P)
    return {"partner_mc-taken": (ev["x"] == [want, want],
                                 f"X (faction, originalFaction, mindControllerId) host/client {ev['x']} "
                                 f"(want {want} on both; seed {SEED_PARTNER_MC})"),
            "partner_mc-common": G3F.common(host, client, crash0)}, ev


def row_host_tab_skips(host, client, crash0):
    seq = tabs(host, 6)
    r = reads(host, client)
    want = SKIP_SEQ[-1]
    ok_hud, cmp_ = hud_is(host, want)
    ev = {"seq": seq, "reads": r, "texts": MST.texts_of(host), "x": [xview(host), xview(client)]}
    got = [s[0] for s in seq]
    hold = [(x["host"]["selectedId"], x["host"]["currentActionActorId"]) for x in r]
    ps = [(x["client"]["selectedId"], x["client"]["currentActionActorId"]) for x in r]
    return {"host_tab_skips-seq": (got == SKIP_SEQ, f"host Tab x6 selectedIds {got} (want {SKIP_SEQ}; a Tab that does "
                                                    f"not skip the alien makes the sixth X {X})"),
            "host_tab_skips-hold": (hold == [(want, want)] * 2,
                                    f"host (selectedId, currentActionActorId) at the two reads {hold} "
                                    f"(want {(want, want)} at both; a Tab that does not skip the alien holds X / X)"),
            "host_tab_skips-hud": (ok_hud, f"host hud vs unit {want}'s units[] view at the second read "
                                           f"{{field: (hud, unit)}} {cmp_} (want equal on {list(HUD_FIELDS)}; a Tab "
                                           f"that does not skip the alien shows X's numbers)"),
            "host_tab_skips-partner": (all(s in S1_IDS and a == s for s, a in ps),
                           f"client (selectedId, currentActionActorId) at the two reads {ps} (want one of {S1_IDS}, "
                           f"actor equal)"),
            "host_tab_skips-common": G3F.common(host, client, crash0)}, ev


def row_host_click_refused(host, client, crash0):
    ev = {"tab": RSP.tab_select(host, H)}
    ev["textWait"] = PR.wait_until(lambda: battle_state(host).get("coopWaitText") == "", TEXT_WAIT_S, 0.1)
    ev["sel0"] = battle_state(host).get("selectedId")
    blocked0, arm0 = es(host, "coopLocalExecBlocked"), es(host, "coopWalkArmEntered")
    tile = tile_of(host, X)
    ev["tile"] = [tile, tile_of(client, X)]
    t0 = time.time()
    a = ev["answer"] = TTC.click(host, tile)
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
    return {"host_click_refused-pre": (pre_ok, f"host selectedId {ev['sel0']} after tab_select (want {H}); "
                                               f"empty coopWaitText wait "
                                               f"{ev['textWait']} (want True within {TEXT_WAIT_S} s)"),
            "host_click_refused-click": (TTC.clicked(a),
                                         f"host map_tile_click {tile}: {a} (want ok, verified, clicked)"),
            "host_click_refused-effect": (eff_ok, f"host coopWaitText {TEXT_NOT_YOURS!r} at {text_at} s "
                                                  f"(want within {SEL_S} s); host "
                                                  f"(selectedId, currentActionActorId) at {ev['atS']} s {at} "
                                                  f"(want {(H, H)}); "
                                                  f"coopLocalExecBlocked {blocked0} -> {blocked1}, coopWalkArmEntered "
                                                  f"{arm0} -> {arm1} (want both unchanged; a click that does not "
                                                  f"refuse the alien selects X {X} and shows no text)"),
            "host_click_refused-common": G3F.common(host, client, crash0)}, ev


def row_partner_tab_reaches(host, client, crash0):
    seq = tabs(client, TAB_MAX_C, stop=X)
    v = view(client)
    ev = {"seq": seq, "client": v, "host": view(host)}
    got = (v["selectedId"], v["currentActionActorId"])
    return {"partner_tab_reaches-alien": (got == (X, X) and any(s[0] == X for s in seq),
                         f"client Tab selectedIds {[s[0] for s in seq]} (want X {X} within {TAB_MAX_C} presses); client "
                         f"(selectedId, currentActionActorId) {got} (want {(X, X)})"),
            "partner_tab_reaches-common": G3F.common(host, client, crash0)}, ev


def row_turn_cycle(host, client, crash0):
    rec = {"notes": [], "dismissed": [], "cycles": []}
    TCU.cycle(host, client, None, rec, "turn_cycle")
    hv, cv = view(host), view(client)
    x = [xview(host), xview(client)]
    ev = {"rec": rec, "host": hv, "client": cv, "x": x}
    st = [(hv["side"], hv["turn"]), (cv["side"], cv["turn"])]
    want = (1, 1, P)
    return {"turn_cycle-turn": (st == [(0, 2)] * 2 and not rec["notes"] and x == [want, want],
                         f"(side, turn) host/client {st} (want (0, 2) on both); cycle notes {rec['notes']} (want "
                         f"none); X host/client {x} (want {want} on both: reverted)"),
            "turn_cycle-common": G3F.common(host, client, crash0)}, ev


def row_host_mc(host, client, crash0, rec, state):
    m = (host, client)
    try:
        pl = G3F.guarded("host_mc staging", lambda: {
            "X": CSH.place(host, client, X, TCU.STUN_A_TILE, TCU.STUN_A_DIR),
            "H": CSH.place(host, client, H, TCU.STUN_H_TILE, TCU.STUN_H_DIR)}, m)
    except G3F.Miss:
        state["host_mc"] = "the stun-tile placement (see the CAPTURE host_mc staging line)"
        return staging_fail("host_mc", state["host_mc"])
    pl["tiles"] = {u: [tile_of(host, u), tile_of(client, u)] for u in (X, H)}
    state["host_mc"] = "the host_mc test commands did not complete"
    ev = mc(host, client, H, SEED_HOST_MC, rec, "host_mc")
    del state["host_mc"]
    ev["place"] = pl
    if "miss" in ev:
        state["host_mc"] = ev["miss"]
    want = (0, 1, H)
    return {"host_mc-taken": (ev["x"] == [want, want],
                              f"X (faction, originalFaction, mindControllerId) host/client {ev['x']} "
                              f"(want {want} on both; seed {SEED_HOST_MC})"),
            "host_mc-common": G3F.common(host, client, crash0)}, ev


def row_host_tab_own_mc(host, client, crash0):
    seq = tabs(host, 5)
    r = reads(host, client)
    ok_hud, cmp_ = hud_is(host, X)
    cseq = tabs(client, 3)
    ev = {"seq": seq, "reads": r, "cseq": cseq}
    got = [s[0] for s in seq]
    hold = [(x["host"]["selectedId"], x["host"]["currentActionActorId"]) for x in r]
    return {"host_tab_own_mc-reach": (got == OWN_MC_SEQ and hold == [(X, X)] * 2 and ok_hud,
                          f"host Tab x5 selectedIds {got} (want {OWN_MC_SEQ}); "
                          f"host (selectedId, currentActionActorId) at the two reads {hold} (want {(X, X)} at both); "
                          f"hud vs X's units[] view at the second read {cmp_} (want equal on {list(HUD_FIELDS)})"),
            "host_tab_own_mc-client": (all(s != X and s in S1_IDS and a == s for s, a, _c in cseq) and len(cseq) == 3,
                           f"client Tab x3 (selectedId, actor, cursor) {cseq} (want never X {X}, each one of {S1_IDS} "
                           f"with its actor equal)"),
            "host_tab_own_mc-common": G3F.common(host, client, crash0)}, ev


# ===================== boot classic =====================


def run_classic_boot(host, client):
    rows = dict(ROWS)
    try:
        info = G3F.guarded("classic", lambda: boot(host, client), (host, client))
    except G3F.Miss:
        return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE classic line)")
    crash0 = session._crash_log_snapshot()
    print(f"[mc_selection] boot classic ok: {info}", flush=True)
    rec, state = {"boxes": []}, {}

    def gated(row, need, fn):
        if need in state:
            return G3F.verdict(row, rows[row], *staging_fail(row, f"{need.upper()}: {state[need]}"))
        return G3F.run_row(row, rows[row], fn)

    fails = G3F.run_row("host_tab_first", rows["host_tab_first"], lambda: row_host_tab_first(host, client, crash0))
    fails += G3F.run_row("partner_mc", rows["partner_mc"], lambda: row_partner_mc(host, client, crash0, rec, state))
    fails += gated("host_tab_skips", "partner_mc", lambda: row_host_tab_skips(host, client, crash0))
    fails += gated("host_click_refused", "partner_mc", lambda: row_host_click_refused(host, client, crash0))
    fails += gated("partner_tab_reaches", "partner_mc", lambda: row_partner_tab_reaches(host, client, crash0))
    fails += G3F.run_row("turn_cycle", rows["turn_cycle"], lambda: row_turn_cycle(host, client, crash0))
    fails += G3F.run_row("host_mc", rows["host_mc"], lambda: row_host_mc(host, client, crash0, rec, state))
    fails += gated("host_tab_own_mc", "host_mc", lambda: row_host_tab_own_mc(host, client, crash0))
    return fails


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir(HOST_DIR))
    client = GameClient("client", None, make_user_dir(CLIENT_DIR))
    try:
        fails = run_classic_boot(host, client)
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_coop_mc_selection: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
