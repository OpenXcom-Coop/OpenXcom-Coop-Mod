"""R5-U2 S-D rows PS3, PN3, DM4, PP3, DM3 (boot D3, gm3: the HOST plays the aliens, seat 0; the partner the seven X-COM
soldiers, seat 1; both instances with noAlienPanicMessages ON): in PvP each player sees vanilla's battle messages for its
own units only (QU2-12 (a), QU1-7; VL-U2-7; F12889, F13328).

Spec: docs repo rewrite/prompts/r5u2_pvp_presentation.md section (f) test_r5_pvp_messages_gm3.py, AMENDMENT U2-1 (U2-1.6:
row PP3 = F13328, QU2-A1-4 (a)) and the orchestrator ruling R-U2-SD-1 (a second alien B before DM3, so A's bleed-out does
not end the battle and the host's death message can be read).
Constants: rewrite/r5u2-task0/sd/CONSTANTS.md (TASK 0 boots Dc, Dd, D3a, D3b on the unchanged build; every pin equal).

Boot D3 (key 48909, dirs r5u2_d3_host / _client): G3F.bring_up (the HOST on the Alien team, STR_SMALL_SCOUT, map seed 1),
every live unit's reactions 0, RM.TILES with every X-COM unit facing 4 (A unseen; A sees 8, 9, 10, 11), the partner's
END TURN -> side 1 turn 1. Host orders are real-UI, partner orders are intents. Host boxes are closed host-only, the
partner's OK boxes by their OK button. RING(gc) = the new `messages` ring records on gc since the row's start.
  PS3  the alien host's mind control gets vanilla's attacker message: the amp on A, A psiSkill 100, S2 (10) psiStrength
       0, A's TU; the host's real-UI MIND CONTROL by A on S2 (the right-hand box, key 51, HOME, set_seed SEED_PS3, one
       click).
       PS3-mc      S2 faction 1, mindControllerId A on both (precondition)
       PS3-msg     RING(host) holds {key STR_MIND_CONTROL_SUCCESSFUL, owner own} and no STR_IS_UNDER_ALIEN_CONTROL
                                                               (RED: {S2, STR_IS_UNDER_ALIEN_CONTROL, other, box})
       PS3-client  RING(client) holds {S2, STR_IS_UNDER_ALIEN_CONTROL, own} (guard)
  PN3  its own alien's panic gets its message with the option ON: A morale 0 (both); the host's END TURN -> side 0 turn
       2; host set_seed SEED_PN3 right before the partner's END TURN -> side 1 turn 2.
       PN3-roll    the host's panic ev for A (precondition)
       PN3-msg     RING(host) holds {A, STR_HAS_PANICKED, own} (SEED_PN3's mode flee)
                                                               (RED: no entry; TASK 0: no pause entry either)
  DM4  no message for the opponent's fatal-wound death: S (12) health 1 + STAGE_WOUNDS (both); the host's END TURN ->
       side 0 turn 3.
       DM4-dead    S DEAD on both (precondition)
       DM4-client  RING(client) holds {S, STR_HAS_DIED_FROM_A_FATAL_WOUND, own} (guard)
       DM4-host    RING(host) holds no entry for S                          (RED: {S, the same key, other, okbox})
  PP3  the X-COM partner's psi PANIC on the alien host's alien gives the alien host no attacker's message (F13328; side 0
       turn 3): the amp on PP (8), PP psiSkill 100, A psiStrength 0, PP's TU; while A is not in the X-COM union on the
       host, RM.turn_order(PP, PP_DIR); host set_seed SEED_PP3; the partner's lever psi {panic, amp, A's tile, A}.
       PP3-seen    A in the union of the X-COM units' host visibleUnits before the intent (precondition)
       PP3-psi     one new host context {intent, psi, PP}; its psi cue {actor PP, unit A, action panic, success true}
       PP3-host    RING(host) holds no STR_MORALE_ATTACK_SUCCESSFUL entry                      (RED: one, F13328)
       PP3-client  RING(client) holds {PP, STR_MORALE_ATTACK_SUCCESSFUL, own} (guard)
  B staging (R-U2-SD-1): as test_r5_pvp_messages.py's (B on the host's seat 0); a failure FAILs DM3 "staging".
  DM3  (last) its own alien's fatal-wound death gets its message: A health 1 + STAGE_WOUNDS (both); the partner's END TURN
       -> side 1 turn 3.
       DM3-msg     A DEAD on both; RING(host) holds {A, STR_HAS_DIED_FROM_A_FATAL_WOUND, own}          (RED: none)
Common cell (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane crash folder.
RED at D1: PS3-msg, PN3-msg, DM4-host, PP3-host, DM3-msg; every other cell PASS. One EVIDENCE line per row (both rings,
the partner's warningText), one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step
past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails the rows that need
it "staging". Lever pairs go to the client first (F607); ids come from lever replies (S25). WV-D95: run in the foreground
to completion. WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_r5_pvp_messages_gm3.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import test_r5_pvp_gm3 as G3F  # noqa: E402
import test_r5_pvp_react_mc as RM  # noqa: E402
import test_r5_pvp_messages as M  # noqa: E402
from test_rw_seat_pacing import tab_select  # noqa: E402
from test_w2_client_shoot import send_intent, set_tu_both, jt  # noqa: E402

KEY = "48909"
A_ID, S2_ID, S_ID, PP_ID = M.A_ID, 10, M.S_ID, M.PP_ID   # S2 10, S 12, PP 8 (U2-1.6 item 5; no swap)
PP_DIR = 0                        # vanilla getDirectionTo(PP (15,9,0), A after its flee (14,3,0)); the turn stops at 7
                                  # when A comes into PP's sight (TASK 0)
SEED_PS3 = SEED_PN3 = SEED_PP3 = 1
KEY_MC = 51                       # the amp's MIND CONTROL key (cursor 3, rows 3; TASK 0)
STEP_S = M.STEP_S
FACTION_PLAYER, FACTION_HOSTILE = M.FACTION_PLAYER, M.FACTION_HOSTILE
ROWS = (("PS3", ("PS3-mc", "PS3-msg", "PS3-client", "PS3-common")),
        ("PN3", ("PN3-roll", "PN3-msg", "PN3-common")),
        ("DM4", ("DM4-dead", "DM4-client", "DM4-host", "DM4-common")),
        ("PP3", ("PP3-seen", "PP3-psi", "PP3-host", "PP3-client", "PP3-common")),
        ("DM3", ("DM3-msg", "DM3-common")))

units, es, ctxs, has = G3F.units, RM.es, RM.ctxs, M.has


# ===================== rows =====================


def row_ps3(host, client, crash0):
    ev, cells = {}, {}
    ev["amp"] = RM.give_both(host, client, A_ID, RM.PSI_AMP)["weaponId"]
    RM.stat_both(host, client, A_ID, "psiSkill", 100)
    RM.stat_both(host, client, S2_ID, "psiStrength", 0)
    ev["tu"] = set_tu_both(host, client, A_ID, M.TU[A_ID])
    s0, ctx0 = M.snap(host, client), ctxs(host)
    ui = ev["ui"] = {}
    try:
        ui["tab"] = tab_select(host, A_ID)
        M.psi_press(host, host, RM.TILES[S2_ID][0], SEED_PS3, ui, key=KEY_MC)
    except Exception as e:
        ui["pressError"] = str(e)[:300]
    new = M.psi_after(host, client, ctx0, S2_ID, ui)
    M.cancel_aim(host, ui)
    rg = M.ring(s0, host, client)
    M.evidence(ev, host, client, rg)
    ev["newCtx"] = [RM.cv(c) for c in new]
    got = [(M.uv(gc, S2_ID)["faction"], M.uv(gc, S2_ID)["mindControllerId"]) for gc in (host, client)]
    cells["PS3-mc"] = (got == [(FACTION_HOSTILE, A_ID)] * 2,
                       f"S2 (faction, mindControllerId) host/client {got} (want {(FACTION_HOSTILE, A_ID)} on both)")
    cells["PS3-msg"] = (bool(has(rg["host"], key=M.K_MIND, owner="own")) and not has(rg["host"], key=M.K_UNDER),
                        f"RING(host) {rg['host']} (want {{key {M.K_MIND}, owner own}} and no {M.K_UNDER})")
    cells["PS3-client"] = (bool(has(rg["client"], unit=S2_ID, key=M.K_UNDER, owner="own")),
                           f"RING(client) {rg['client']} (want {{unit {S2_ID}, key {M.K_UNDER}, owner own}})")
    cells["PS3-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_pn3(host, client, crash0):
    ev, cells = {}, {}
    ev["morale"] = M.morale0(host, client, A_ID)
    s0, seq0 = M.snap(host, client), es(host, "lastSeqEmitted") or 0
    ev["a"] = M.side_change(host, client, host, FACTION_PLAYER, 2, "PN3 host END TURN")
    ev["b"] = M.side_change(host, client, client, FACTION_HOSTILE, 2, "PN3 partner END TURN", seed=SEED_PN3,
                            at_roll=lambda: M.statuses(host, client, A_ID))
    panics = M.panic_wait(host, client, seq0, ev)
    rg = M.ring(s0, host, client)
    M.evidence(ev, host, client, rg)
    ev.update(panics=panics, A=[M.uv(host, A_ID), M.uv(client, A_ID)])
    cells["PN3-roll"] = ([p.get("unit") for p in panics] == [A_ID],
                         f"host panic payloads {panics} (want one for unit {A_ID}); A status at the roll "
                         f"{ev['b'].get('roll')}")
    cells["PN3-msg"] = (bool(has(rg["host"], unit=A_ID, key=M.K_PANICKED, owner="own")),
                        f"RING(host) {rg['host']} (want {{unit {A_ID}, key {M.K_PANICKED}, owner own}})")
    cells["PN3-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_dm4(host, client, crash0):
    ev, cells = {}, {}
    ev["staged"] = M.fatal(host, client, S_ID)
    s0 = M.snap(host, client)
    ev["side"] = M.side_change(host, client, host, FACTION_PLAYER, 3, "DM4 host END TURN")
    cells["DM4-dead"] = M.dead_cell(host, client, S_ID, ev)
    # cap-tail (F24060, Y1-exposed read): S's bleed-out still runs in the host's UnitDieBState after side_change()'s
    # settle() went quiet; read DM4-host only once that state pops, and close the client's OK box before PP3.
    ev["drain"], ev["after"] = M.host_drained(host, client, "DM4 after")
    rg = M.ring(s0, host, client)
    M.evidence(ev, host, client, rg)
    cells["DM4-client"] = (bool(has(rg["client"], unit=S_ID, key=M.K_FATAL, owner="own")),
                           f"RING(client) {rg['client']} (want {{unit {S_ID}, key {M.K_FATAL}, owner own}})")
    cells["DM4-host"] = (not has(rg["host"], unit=S_ID), f"RING(host) {rg['host']} (want no entry for {S_ID})")
    cells["DM4-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_pp3(host, client, crash0):
    ev, cells = {}, {}
    amp = ev["amp"] = RM.give_both(host, client, PP_ID, RM.PSI_AMP)["weaponId"]
    RM.stat_both(host, client, PP_ID, "psiSkill", 100)
    RM.stat_both(host, client, A_ID, "psiStrength", 0)
    ev["tu"] = set_tu_both(host, client, PP_ID, M.TU[PP_ID])
    turn = ev["turn"] = {"before": M.union(host, FACTION_PLAYER)}
    if A_ID not in turn["before"]:
        try:
            tnew, deny = RM.turn_order(host, client, PP_ID, PP_DIR, turn)
            turn.update(newCtx=[RM.cv(c) for c in tnew], deny=deny, pp=M.uv(host, PP_ID))
        except Exception as e:
            turn["error"] = str(e)[:300]
    u = M.union(host, FACTION_PLAYER)
    cells["PP3-seen"] = (A_ID in u, f"the X-COM union on the host {u} before the intent (want {A_ID} in it)")
    s0, ctx0, seq0 = M.snap(host, client), ctxs(host), es(host, "lastSeqEmitted") or 0
    lv = ev["lever"] = {}
    at = G3F.pos(host, A_ID)
    host.ok({"cmd": "set_seed", "seed": SEED_PP3})
    notes = []
    try:
        si = send_intent(host, client, {"cmd": "battle_intent", "kind": "psi", "actor": PP_ID,
                                        "plan": {"action": "panic", "weapon": amp, "target": jt(at), "targetUnit": A_ID}},
                         notes, timeout=STEP_S)
        lv.update(iseq=si.get("iseq"), answer=si.get("answer"))
    except Exception as e:
        lv["intentError"] = str(e)[:300]
    lv["notes"] = notes
    new = M.psi_after(host, client, ctx0, A_ID, lv)
    rg = M.ring(s0, host, client)
    M.evidence(ev, host, client, rg)
    cells["PP3-psi"] = M.psi_cell(host, client, new, seq0, "intent", PP_ID,
                                  {"actor": PP_ID, "unit": A_ID, "action": "panic", "success": True}, ev)
    cells["PP3-host"] = (not has(rg["host"], key=M.K_MORALE), f"RING(host) {rg['host']} (want no {M.K_MORALE} entry)")
    cells["PP3-client"] = (bool(has(rg["client"], unit=PP_ID, key=M.K_MORALE, owner="own")),
                           f"RING(client) {rg['client']} (want {{unit {PP_ID}, key {M.K_MORALE}, owner own}})")
    cells["PP3-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_dm3(host, client, crash0):
    ev, cells = {}, {}
    rg, dead = M.own_death(host, client, client, ev)
    M.evidence(ev, host, client, rg)
    hr = has(rg["host"], unit=A_ID, key=M.K_FATAL, owner="own")
    cells["DM3-msg"] = (dead[0] and bool(hr), f"{dead[1]}; RING(host) {rg['host']} (want {{unit {A_ID}, key "
                                              f"{M.K_FATAL}, owner own}})")
    cells["DM3-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot D3 =====================


def boot_d3():
    host = GameClient("host", None, make_user_dir("r5u2_d3_host", options=M.OPTS))
    client = GameClient("client", None, make_user_dir("r5u2_d3_client", options=M.OPTS))
    m = (host, client)
    try:
        try:
            _boot, crash0 = G3F.bring_up(host, client, KEY, "D3")
            G3F.guarded("D3", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE D3 line)")
        try:
            M.stage(host, client, client)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        rows = dict(ROWS)
        fails = G3F.run_row("PS3", rows["PS3"], lambda: row_ps3(host, client, crash0))
        fails += G3F.run_row("PN3", rows["PN3"], lambda: row_pn3(host, client, crash0))
        fails += G3F.run_row("DM4", rows["DM4"], lambda: row_dm4(host, client, crash0))
        fails += G3F.run_row("PP3", rows["PP3"], lambda: row_pp3(host, client, crash0))
        if M.convert_b(host, client, crash0, 0) is None:
            fails += G3F.fail_all((("DM3", rows["DM3"]),), "staging (see the CAPTURE B staging line)")
        else:
            fails += G3F.run_row("DM3", rows["DM3"], lambda: row_dm3(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_d3()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_r5_pvp_messages_gm3: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
