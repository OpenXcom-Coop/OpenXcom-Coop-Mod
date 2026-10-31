"""PvP battle messages in gm3 (the HOST plays the aliens, seat 0; the partner the seven X-COM soldiers, seat 1; both
instances with noAlienPanicMessages ON): in PvP each player sees vanilla's battle messages for its own units only.

Boot (key 48909, dirs pvp_messages_gm3_host / _client): G3F.bring_up (the HOST on the Alien team, STR_SMALL_SCOUT, map
seed 1), every live unit's reactions 0, RM.TILES with every X-COM unit facing 4 (A unseen; A sees 8, 9, 10, 11), the
partner's END TURN -> side 1 turn 1. Host orders are real-UI, partner orders are intents. Host boxes are closed
host-only, the partner's OK boxes by their OK button. RING(gc) = the new `messages` ring records on gc since the row's
start. The ids, tiles and TUs below were measured equal on four boots without the fix.
  alien_mind_control  the alien host's mind control gets vanilla's attacker message: the amp on A, A psiSkill 100,
       S2 (10) psiStrength 0, A's TU; the host's real-UI MIND CONTROL by A on S2 (the right-hand box, key 51, HOME,
       set_seed MIND_CONTROL_SEED, one click).
       alien_mind_control-mc      S2 faction 1, mindControllerId A on both (precondition)
       alien_mind_control-msg     RING(host) holds {key STR_MIND_CONTROL_SUCCESSFUL, owner own} and no
                                  STR_IS_UNDER_ALIEN_CONTROL (without the fix: {S2, STR_IS_UNDER_ALIEN_CONTROL, other,
                                  box})
       alien_mind_control-client  RING(client) holds {S2, STR_IS_UNDER_ALIEN_CONTROL, own} (guard)
  own_alien_panics  its own alien's panic gets its message with the option ON: A morale 0 (both); the host's END TURN
       -> side 0 turn 2; host set_seed PANIC_ROLL_SEED right before the partner's END TURN -> side 1 turn 2.
       own_alien_panics-roll      the host's panic ev for A (precondition)
       own_alien_panics-msg       RING(host) holds {A, STR_HAS_PANICKED, own} (PANIC_ROLL_SEED's mode flee)
                                  (without the fix: no entry, and no pause entry either)
  opponent_death  no message for the opponent's fatal-wound death: S (12) health 1 + STAGE_WOUNDS (both); the host's
       END TURN -> side 0 turn 3.
       opponent_death-dead        S DEAD on both (precondition)
       opponent_death-client      RING(client) holds {S, STR_HAS_DIED_FROM_A_FATAL_WOUND, own} (guard)
       opponent_death-host        RING(host) holds no entry for S (without the fix: {S, the same key, other, okbox})
  xcom_panic_attack  the X-COM partner's psi PANIC on the alien host's alien gives the alien host no attacker's
       message (side 0 turn 3): the amp on PP (8), PP psiSkill 100, A psiStrength 0, PP's TU; while A is not in the
       X-COM union on the host, RM.turn_order(PP, PP_DIR); host set_seed XCOM_PSI_SEED; the partner's psi intent
       {panic, amp, A's tile, A} (test command).
       xcom_panic_attack-seen     A in the union of the X-COM units' host visibleUnits before the intent (precondition)
       xcom_panic_attack-psi      one new host context {intent, psi, PP}; its psi cue {actor PP, unit A, action panic,
                                  success true}
       xcom_panic_attack-host     RING(host) holds no STR_MORALE_ATTACK_SUCCESSFUL entry (without the fix: one)
       xcom_panic_attack-client   RING(client) holds {PP, STR_MORALE_ATTACK_SUCCESSFUL, own} (guard)
  B staging: as test_pvp_messages.py's (B on the host's seat 0; a second alien keeps the battle going after A's
       bleed-out, so the host's death message can be read); a failure FAILs own_alien_death "staging".
  own_alien_death  (last) its own alien's fatal-wound death gets its message: A health 1 + STAGE_WOUNDS (both); the
       partner's END TURN -> side 1 turn 3.
       own_alien_death-msg        A DEAD on both; RING(host) holds {A, STR_HAS_DIED_FROM_A_FATAL_WOUND, own}
                                  (without the fix: none)
Common cell (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in this harness slot's crash
folder.
Without the fix, alien_mind_control-msg, own_alien_panics-msg, opponent_death-host, xcom_panic_attack-host and
own_alien_death-msg FAIL; every other cell passes. One EVIDENCE line per row (both rings, the partner's warningText),
one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step past its bound prints
ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails the rows that need it "staging".
Test-command pairs go to the client first; item ids come from the command replies. ONE run is the result, no skip
path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_messages_gm3.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_pvp_messages as M  # noqa: E402
from test_seat_pacing import tab_select  # noqa: E402
from test_client_shoot import send_intent, set_tu_both, jt  # noqa: E402

KEY = "48909"
A_ID, S2_ID, S_ID, PP_ID = M.A_ID, 10, M.S_ID, M.PP_ID   # S2 10, S 12, PP 8
PP_DIR = 0                        # vanilla getDirectionTo(PP (15,9,0), A after its flee (14,3,0)); the turn stops at 7
                                  # when A comes into PP's sight
MIND_CONTROL_SEED = PANIC_ROLL_SEED = XCOM_PSI_SEED = 1
KEY_MC = 51                       # the amp's MIND CONTROL key (cursor 3, rows 3; measured)
STEP_S = M.STEP_S
FACTION_PLAYER, FACTION_HOSTILE = M.FACTION_PLAYER, M.FACTION_HOSTILE
ROWS = (("alien_mind_control", ("alien_mind_control-mc", "alien_mind_control-msg", "alien_mind_control-client",
                                "alien_mind_control-common")),
        ("own_alien_panics", ("own_alien_panics-roll", "own_alien_panics-msg", "own_alien_panics-common")),
        ("opponent_death", ("opponent_death-dead", "opponent_death-client", "opponent_death-host",
                            "opponent_death-common")),
        ("xcom_panic_attack", ("xcom_panic_attack-seen", "xcom_panic_attack-psi", "xcom_panic_attack-host",
                               "xcom_panic_attack-client", "xcom_panic_attack-common")),
        ("own_alien_death", ("own_alien_death-msg", "own_alien_death-common")))

units, es, ctxs, has = G3F.units, RM.es, RM.ctxs, M.has


# ===================== rows =====================


def row_alien_mind_control(host, client, crash0):
    ev, cells = {}, {}
    ev["amp"] = RM.give_both(host, client, A_ID, RM.PSI_AMP)["weaponId"]
    RM.stat_both(host, client, A_ID, "psiSkill", 100)
    RM.stat_both(host, client, S2_ID, "psiStrength", 0)
    ev["tu"] = set_tu_both(host, client, A_ID, M.TU[A_ID])
    s0, ctx0 = M.snap(host, client), ctxs(host)
    ui = ev["ui"] = {}
    try:
        ui["tab"] = tab_select(host, A_ID)
        M.psi_press(host, host, RM.TILES[S2_ID][0], MIND_CONTROL_SEED, ui, key=KEY_MC)
    except Exception as e:
        ui["pressError"] = str(e)[:300]
    new = M.psi_after(host, client, ctx0, S2_ID, ui)
    M.cancel_aim(host, ui)
    rg = M.ring(s0, host, client)
    M.evidence(ev, host, client, rg)
    ev["newCtx"] = [RM.cv(c) for c in new]
    got = [(M.uv(gc, S2_ID)["faction"], M.uv(gc, S2_ID)["mindControllerId"]) for gc in (host, client)]
    cells["alien_mind_control-mc"] = (got == [(FACTION_HOSTILE, A_ID)] * 2,
                                      f"S2 (faction, mindControllerId) host/client {got} "
                                      f"(want {(FACTION_HOSTILE, A_ID)} on both)")
    cells["alien_mind_control-msg"] = (bool(has(rg["host"], key=M.K_MIND, owner="own"))
                                       and not has(rg["host"], key=M.K_UNDER),
                                       f"RING(host) {rg['host']} (want {{key {M.K_MIND}, owner own}} "
                                       f"and no {M.K_UNDER})")
    cells["alien_mind_control-client"] = (bool(has(rg["client"], unit=S2_ID, key=M.K_UNDER, owner="own")),
                                          f"RING(client) {rg['client']} "
                                          f"(want {{unit {S2_ID}, key {M.K_UNDER}, owner own}})")
    cells["alien_mind_control-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_own_alien_panics(host, client, crash0):
    ev, cells = {}, {}
    ev["morale"] = M.morale0(host, client, A_ID)
    s0, seq0 = M.snap(host, client), es(host, "lastSeqEmitted") or 0
    ev["a"] = M.side_change(host, client, host, FACTION_PLAYER, 2, "own_alien_panics host END TURN")
    ev["b"] = M.side_change(host, client, client, FACTION_HOSTILE, 2, "own_alien_panics partner END TURN",
                            seed=PANIC_ROLL_SEED,
                            at_roll=lambda: M.statuses(host, client, A_ID))
    panics = M.panic_wait(host, client, seq0, ev)
    rg = M.ring(s0, host, client)
    M.evidence(ev, host, client, rg)
    ev.update(panics=panics, A=[M.uv(host, A_ID), M.uv(client, A_ID)])
    cells["own_alien_panics-roll"] = ([p.get("unit") for p in panics] == [A_ID],
                                      f"host panic payloads {panics} (want one for unit {A_ID}); A status at the roll "
                                      f"{ev['b'].get('roll')}")
    cells["own_alien_panics-msg"] = (bool(has(rg["host"], unit=A_ID, key=M.K_PANICKED, owner="own")),
                                     f"RING(host) {rg['host']} (want {{unit {A_ID}, key {M.K_PANICKED}, owner own}})")
    cells["own_alien_panics-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_opponent_death(host, client, crash0):
    ev, cells = {}, {}
    ev["staged"] = M.fatal(host, client, S_ID)
    s0 = M.snap(host, client)
    ev["side"] = M.side_change(host, client, host, FACTION_PLAYER, 3, "opponent_death host END TURN")
    cells["opponent_death-dead"] = M.dead_cell(host, client, S_ID, ev)
    # S's bleed-out still runs in the host's UnitDieBState after side_change()'s settle() went quiet; read
    # opponent_death-host only once that state pops, and close the client's OK box before xcom_panic_attack.
    ev["drain"], ev["after"] = M.host_drained(host, client, "opponent_death after")
    rg = M.ring(s0, host, client)
    M.evidence(ev, host, client, rg)
    cells["opponent_death-client"] = (bool(has(rg["client"], unit=S_ID, key=M.K_FATAL, owner="own")),
                                      f"RING(client) {rg['client']} (want {{unit {S_ID}, key {M.K_FATAL}, owner own}})")
    cells["opponent_death-host"] = (not has(rg["host"], unit=S_ID),
                                    f"RING(host) {rg['host']} (want no entry for {S_ID})")
    cells["opponent_death-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_xcom_panic_attack(host, client, crash0):
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
    cells["xcom_panic_attack-seen"] = (A_ID in u,
                                       f"the X-COM union on the host {u} before the intent (want {A_ID} in it)")
    s0, ctx0, seq0 = M.snap(host, client), ctxs(host), es(host, "lastSeqEmitted") or 0
    sent = ev["intent"] = {}
    at = G3F.pos(host, A_ID)
    host.ok({"cmd": "set_seed", "seed": XCOM_PSI_SEED})
    notes = []
    try:
        si = send_intent(host, client, {"cmd": "battle_intent", "kind": "psi", "actor": PP_ID,
                                        "plan": {"action": "panic", "weapon": amp, "target": jt(at), "targetUnit": A_ID}},
                         notes, timeout=STEP_S)
        sent.update(iseq=si.get("iseq"), answer=si.get("answer"))
    except Exception as e:
        sent["intentError"] = str(e)[:300]
    sent["notes"] = notes
    new = M.psi_after(host, client, ctx0, A_ID, sent)
    rg = M.ring(s0, host, client)
    M.evidence(ev, host, client, rg)
    cells["xcom_panic_attack-psi"] = M.psi_cell(host, client, new, seq0, "intent", PP_ID,
                                                {"actor": PP_ID, "unit": A_ID, "action": "panic", "success": True}, ev)
    cells["xcom_panic_attack-host"] = (not has(rg["host"], key=M.K_MORALE),
                                       f"RING(host) {rg['host']} (want no {M.K_MORALE} entry)")
    cells["xcom_panic_attack-client"] = (bool(has(rg["client"], unit=PP_ID, key=M.K_MORALE, owner="own")),
                                         f"RING(client) {rg['client']} "
                                         f"(want {{unit {PP_ID}, key {M.K_MORALE}, owner own}})")
    cells["xcom_panic_attack-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_own_alien_death(host, client, crash0):
    ev, cells = {}, {}
    rg, dead = M.own_death(host, client, client, ev)
    M.evidence(ev, host, client, rg)
    hr = has(rg["host"], unit=A_ID, key=M.K_FATAL, owner="own")
    cells["own_alien_death-msg"] = (dead[0] and bool(hr),
                                    f"{dead[1]}; RING(host) {rg['host']} (want {{unit {A_ID}, key "
                                    f"{M.K_FATAL}, owner own}})")
    cells["own_alien_death-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot =====================


def run_boot():
    host = GameClient("host", None, make_user_dir("pvp_messages_gm3_host", options=M.OPTS))
    client = GameClient("client", None, make_user_dir("pvp_messages_gm3_client", options=M.OPTS))
    m = (host, client)
    try:
        try:
            _boot, crash0 = G3F.bring_up(host, client, KEY, "boot")
            G3F.guarded("boot", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        try:
            M.stage(host, client, client)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        rows = dict(ROWS)
        fails = G3F.run_row("alien_mind_control", rows["alien_mind_control"],
                            lambda: row_alien_mind_control(host, client, crash0))
        fails += G3F.run_row("own_alien_panics", rows["own_alien_panics"],
                             lambda: row_own_alien_panics(host, client, crash0))
        fails += G3F.run_row("opponent_death", rows["opponent_death"], lambda: row_opponent_death(host, client, crash0))
        fails += G3F.run_row("xcom_panic_attack", rows["xcom_panic_attack"],
                             lambda: row_xcom_panic_attack(host, client, crash0))
        if M.convert_b(host, client, crash0, 0) is None:
            fails += G3F.fail_all((("own_alien_death", rows["own_alien_death"]),),
                                  "staging (see the CAPTURE B staging line)")
        else:
            fails += G3F.run_row("own_alien_death", rows["own_alien_death"],
                                 lambda: row_own_alien_death(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_messages_gm3: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
