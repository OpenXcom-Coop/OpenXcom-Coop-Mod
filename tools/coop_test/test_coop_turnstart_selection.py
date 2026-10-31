"""Rows first_turn, keep_turn2, client_tab, keep_turn3, host_tab, keep_turn4, partner_mc, mc_reverts (boot classic,
classic co-op, gamemode 1: both seats play X-COM): at each X-COM turn start the second player keeps the soldier it
holds while that soldier is still its own and selectable, with the action actor, HUD and camera on it, as vanilla and
the co-op host do; when the held unit is no longer its own (the alien it mind-controlled reverted) it gets its first
own soldier in unit order (vanilla's fallback).

Boot classic (key 49042, dirs coop_turnstart_selection_host / _client, default options): test_turn_cues' bring-up with
this key (roster pinned, SEED_MAP; asserts: map fingerprint, seated [8, 9], unit order on both, pinned [X],
coopGamemode 1 on both, turnMode parallel on both). No input on either machine except the presses each row names.
  first_turn  turn 1, two reads READ_GAP_S apart.  first_turn-pre client (selectedId, actor) (CLIENT_ENTRY_SEL,
      CLIENT_ENTRY_SEL) and host (HOST_ENTRY_SEL, HOST_ENTRY_SEL) at both reads (precondition).
  keep_turn2  END TURN to turn 2 (TCU.cycle), c0 / h0 = the client's / host's selection right before the cycle; two
      reads; the client's camera move records since the cycle's first seq.  keep_turn2-keep client (selectedId, actor)
      == (c0, c0) at both reads; keep_turn2-hud the client's hud equals c0's units[] view on HUD_FIELDS at the second
      read; keep_turn2-cam the client's moves as (reason, unit) == [(CAM_REASON, c0)]; keep_turn2-host host
      (selectedId, actor) == (h0, h0) at both reads (guard).
  client_tab  the client's Tab once at turn 2 (real key 9), read PRESS_READ_S later.  client_tab-next the client's
      selectedId in SEATED, not the one before the press, actor equal (guard).
  keep_turn3  END TURN to turn 3: keep_turn3-keep, keep_turn3-hud, keep_turn3-cam, keep_turn3-host as keep_turn2.
  host_tab  the host's Tab once at turn 3, read PRESS_READ_S later.  host_tab-next host (HOST_TAB_NEXT,
      HOST_TAB_NEXT), the client unchanged.
  keep_turn4  END TURN to turn 4: keep_turn4-keep, keep_turn4-hud, keep_turn4-cam, keep_turn4-host (HOST_TAB_NEXT
      kept) as keep_turn2.
  partner_mc  MSC.stage_tiles; the partner's P mind-controls X (host set_seed SEED_PARTNER_MC, the host-local
      psi_attack test command); the client's Tab until it holds X (<= TAB_MAX_C presses).  partner_mc-taken X
      (faction, originalFaction, mindControllerId) == (0, 1, P) on both and the client holds X with its actor equal
      (precondition).
  mc_reverts  END TURN to turn 5: X reverts, the held unit is no longer the client's.  mc_reverts-fall client
      (FALLBACK, FALLBACK) at both reads and X (faction, originalFaction) == (1, 1) on both; mc_reverts-cam the
      client's moves == [(CAM_REASON, FALLBACK)]; mc_reverts-host the host on one of its own seat-0 units with its
      actor equal at both reads (never h0: the psi_attack test command left the host on P).
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new crash file.

A client that drops its held soldier at the turn start fails keep_turn2-keep, keep_turn2-hud, keep_turn2-cam,
keep_turn3-keep, keep_turn3-hud, keep_turn3-cam, keep_turn4-keep, keep_turn4-hud and keep_turn4-cam (18 of 27 cells
pass); a client that keeps it passes all 27. One EVIDENCE line per row, one PASS/FAIL line per cell, then the row
verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails every row
"boot"; a staging step past its bound fails the rows that need it "staging". Paired test commands go to the client
first. Run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when every cell passes,
else 2.

Run:  python tools/coop_test/test_coop_turnstart_selection.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, pin_ai_neutral  # noqa: E402
from test_ai_origins import bring_up_lobby_roster_pinned  # noqa: E402
import test_turn_cues as TCU  # noqa: E402
import test_mc_seat_coop as MSC  # noqa: E402
import test_mc_seat_tally as MST  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_host_combat as HC  # noqa: E402
import test_client_shoot as CSH  # noqa: E402

KEY = "49042"
HOST_DIR, CLIENT_DIR = "coop_turnstart_selection_host", "coop_turnstart_selection_client"    # default options
SEATED = TCU.SEATED               # [8, 9], the client seat's soldiers
S0_IDS = MSC.S0_IDS               # [10..14], the host seat's soldiers
X = TCU.A_ID                      # 1000000, the one alien (seat NONE, pinned AI-neutral)
P = 8                             # the partner's (client seat's) soldier that mind-controls X in row partner_mc
GAMEMODE = 1                      # classic co-op skirmish
CLIENT_ENTRY_SEL = 8              # the client's entry selection: the first of SEATED in unit order
HOST_ENTRY_SEL = TCU.H_ID         # 10, the host's entry selection
HOST_TAB_NEXT = 11                # the host's next own live unit after 10 in unit order
FALLBACK = 8                      # the first of SEATED in unit order that is live and faction PLAYER after mc_reverts
SEED_PARTNER_MC = 2               # host set_seed before the psi_attack test command: 8 takes X at turn 4, first try
HUD_FIELDS = ("tu", "energy", "health", "morale")   # hud == the selected unit's units[] view on all four
CAM_REASON = "side_start"         # the client's camera record at its X-COM side_begin (TCP CoopGhost::onSideStart)
MC_WAIT_S, TAB_MAX_C = 6, 3
TAB_GAP_S, PRESS_READ_S, READ_GAP_S = 0.4, 0.6, 1.0
KEY_NEXT = 9                      # Tab (keyBattleNextUnit)
CYC_CELLS = ("keep", "hud", "cam", "host", "common")
ROWS = (("first_turn", ("first_turn-pre", "first_turn-common")),
        ("keep_turn2", tuple(f"keep_turn2-{c}" for c in CYC_CELLS)),
        ("client_tab", ("client_tab-next", "client_tab-common")),
        ("keep_turn3", tuple(f"keep_turn3-{c}" for c in CYC_CELLS)),
        ("host_tab", ("host_tab-next", "host_tab-common")),
        ("keep_turn4", tuple(f"keep_turn4-{c}" for c in CYC_CELLS)),
        ("partner_mc", ("partner_mc-taken", "partner_mc-common")),
        ("mc_reverts", ("mc_reverts-fall", "mc_reverts-cam", "mc_reverts-host", "mc_reverts-common")))

es = G3F.es


def boot(host, client):
    """test_turn_cues.boot's chain with this file's lobby key (a copy that takes the key as a parameter)."""
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
    pinned = pin_ai_neutral(host, client, tag="turnstart_selection")
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
                                                     f"(want {(c0, c0)} at both; a client that drops its "
                                                     f"soldier holds its other soldier)"),
            f"{name}-hud": (hud[0], f"client hud vs unit {c0}'s units[] view at the second read {{field: (hud, unit)}} "
                                    f"{hud[1]} (want equal on {list(HUD_FIELDS)}; a client that drops its soldier "
                                    f"shows the other soldier's numbers)"),
            f"{name}-cam": (rm == [(CAM_REASON, c0)], f"client camera moves since the cycle's first seq (reason, unit) "
                                                      f"{rm} (want {[(CAM_REASON, c0)]}; seqs {[m[0] for m in moves]} "
                                                      f"EVIDENCE)"),
            f"{name}-host": (hold == [(h0, h0)] * 2, f"host (selectedId, currentActionActorId) at the two reads {hold} "
                                                     f"(want {(h0, h0)} at both)"),
            f"{name}-common": G3F.common(host, client, crash0)}


def staging_fail(row, why):
    return {n: (False, f"staging ({why})") for n in dict(ROWS)[row]}, {"error": f"staging: {why}"}


# ===================== rows =====================


def row_first_turn(host, client, crash0):
    r = reads(host, client)
    ok_c, cmp_c = hud_is(client, CLIENT_ENTRY_SEL)
    ok_h, cmp_h = hud_is(host, HOST_ENTRY_SEL)
    u = session.units_by_id(battle_state(client))
    ev = {"reads": r, "hud": {"client": (ok_c, cmp_c), "host": (ok_h, cmp_h)},
          "views89": {uid: {f: (u.get(uid) or {}).get(f) for f in HUD_FIELDS} for uid in SEATED}}
    cs, hs = [sa(x["client"]) for x in r], [sa(x["host"]) for x in r]
    return {"first_turn-pre": (cs == [(CLIENT_ENTRY_SEL, CLIENT_ENTRY_SEL)] * 2
                               and hs == [(HOST_ENTRY_SEL, HOST_ENTRY_SEL)] * 2,
                               f"client (selectedId, actor) at the two reads {cs} (want "
                               f"{(CLIENT_ENTRY_SEL, CLIENT_ENTRY_SEL)}); host {hs} (want "
                               f"{(HOST_ENTRY_SEL, HOST_ENTRY_SEL)})"),
            "first_turn-common": G3F.common(host, client, crash0)}, ev


def row_cyc(host, client, crash0, name):
    c0, h0, r, moves, hud, ev = cyc(host, client, name)
    return keep_cells(name, c0, h0, r, moves, hud, host, client, crash0), ev


def row_client_tab(host, client, crash0):
    s0 = battle_state(client).get("selectedId")
    v = tab_once(client)
    ev = {"before": s0, "after": v, "host": view(host)}
    s, a = sa(v)
    return {"client_tab-next": (s in SEATED and s != s0 and a == s,
                                f"client selectedId {s0} -> {s}, actor {a} (want one of {SEATED}, not {s0}, "
                                f"actor equal)"),
            "client_tab-common": G3F.common(host, client, crash0)}, ev


def row_host_tab(host, client, crash0):
    c0 = sa(view(client))
    s0 = battle_state(host).get("selectedId")
    v = tab_once(host)
    c1 = sa(view(client))
    ev = {"before": s0, "after": v, "client": [c0, c1]}
    return {"host_tab-next": (sa(v) == (HOST_TAB_NEXT, HOST_TAB_NEXT) and c1 == c0,
                              f"host (selectedId, actor) {s0} -> {sa(v)} (want {(HOST_TAB_NEXT, HOST_TAB_NEXT)}); "
                              f"client {c0} -> {c1} (want unchanged)"),
            "host_tab-common": G3F.common(host, client, crash0)}, ev


def row_partner_mc(host, client, crash0, state):
    rec = {"boxes": []}
    try:
        G3F.guarded("partner_mc staging", lambda: MSC.stage_tiles(host, client, rec), (host, client))
    except G3F.Miss:
        state["partner_mc"] = "MSC.stage_tiles (see the CAPTURE partner_mc staging line)"
        return staging_fail("partner_mc", state["partner_mc"])
    state["partner_mc"] = "the partner_mc test commands did not complete"
    ev = mc(host, client, P, SEED_PARTNER_MC, rec, "partner_mc")
    del state["partner_mc"]
    if "miss" in ev:
        state["partner_mc"] = ev["miss"]
    ev["presses"] = tabs(client, TAB_MAX_C, stop=X)
    v = ev["client"] = view(client)
    want = (0, 1, P)
    return {"partner_mc-taken": (ev["x"] == [want, want] and sa(v) == (X, X),
                                 f"X (faction, originalFaction, mindControllerId) host/client {ev['x']} (want {want} "
                                 f"on both; seed {SEED_PARTNER_MC}); client (selectedId, actor) {sa(v)} after Tab "
                                 f"{[s[0] for s in ev['presses']]} (want {(X, X)} within {TAB_MAX_C} presses)"),
            "partner_mc-common": G3F.common(host, client, crash0)}, ev


def row_mc_reverts(host, client, crash0):
    c0, h0, r, moves, hud, ev = cyc(host, client, "mc_reverts")
    fall = [sa(x["client"]) for x in r]
    hold = [sa(x["host"]) for x in r]
    xf = [x[:2] for x in ev["x"]]
    rm = [(m[1], m[2]) for m in moves]
    return {"mc_reverts-fall": (fall == [(FALLBACK, FALLBACK)] * 2 and xf == [(1, 1)] * 2,
                                f"client (selectedId, actor) at the two reads {fall} (want {(FALLBACK, FALLBACK)}; "
                                f"held {c0}); X (faction, originalFaction) host/client {xf} (want (1, 1) on both: "
                                f"reverted)"),
            "mc_reverts-cam": (rm == [(CAM_REASON, FALLBACK)],
                               f"client camera moves since the cycle's first seq (reason, unit) {rm} (want "
                               f"{[(CAM_REASON, FALLBACK)]}; seqs {[m[0] for m in moves]} EVIDENCE)"),
            "mc_reverts-host": (all(s in S0_IDS and a == s for s, a in hold),
                                f"host (selectedId, actor) at the two reads {hold} (want one of {S0_IDS}, actor "
                                f"equal; held {h0} before the cycle: the psi_attack test command selected P on the "
                                f"host)"),
            "mc_reverts-common": G3F.common(host, client, crash0)}, ev


# ===================== boot classic =====================


def run_classic_boot(host, client):
    rows = dict(ROWS)
    try:
        info = G3F.guarded("classic", lambda: boot(host, client), (host, client))
    except G3F.Miss:
        return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE classic line)")
    crash0 = session._crash_log_snapshot()
    print(f"[turnstart_selection] boot classic ok: {info}", flush=True)
    state = {}
    fails = G3F.run_row("first_turn", rows["first_turn"], lambda: row_first_turn(host, client, crash0))
    fails += G3F.run_row("keep_turn2", rows["keep_turn2"], lambda: row_cyc(host, client, crash0, "keep_turn2"))
    fails += G3F.run_row("client_tab", rows["client_tab"], lambda: row_client_tab(host, client, crash0))
    fails += G3F.run_row("keep_turn3", rows["keep_turn3"], lambda: row_cyc(host, client, crash0, "keep_turn3"))
    fails += G3F.run_row("host_tab", rows["host_tab"], lambda: row_host_tab(host, client, crash0))
    fails += G3F.run_row("keep_turn4", rows["keep_turn4"], lambda: row_cyc(host, client, crash0, "keep_turn4"))
    fails += G3F.run_row("partner_mc", rows["partner_mc"], lambda: row_partner_mc(host, client, crash0, state))
    if "partner_mc" in state:
        fails += G3F.verdict("mc_reverts", rows["mc_reverts"],
                             *staging_fail("mc_reverts", f"partner_mc: {state['partner_mc']}"))
    else:
        fails += G3F.run_row("mc_reverts", rows["mc_reverts"], lambda: row_mc_reverts(host, client, crash0))
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
    print(f"test_coop_turnstart_selection: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
