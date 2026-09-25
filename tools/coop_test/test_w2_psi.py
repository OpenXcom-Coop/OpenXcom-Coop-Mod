"""W2-P3 S-E - test_w2_psi.py: a sectoid leader's AI psi attacks on the
second player's soldiers each run as a named `ai` action - a mind control that
turns C hostile (and reverts at the next hostile side start), then a psi panic
whose panic at the next player side start runs as its own `panic` action -
with both machines equal (spec rewrite/prompts/w2p3_nonplayer_origins.md
section (f) "test_w2_psi.py (S-E; C14 mission)", sections (b)1-(b)6 (the `ai`
origin, kind `psi`: no pre-attack turn), (b)7 (the `panic` context), research
note N11 (the mind-control revert); amendment B1 (RQ5, RQ7, RQ15); ledger
`## W2-P3 TASK 0c` (F874-F877, F882) and `## W2-P3 TASK 0d`; owner ruling
D128 = (b)).

S-E is test-only: the product (S-A..S-D) is complete for this scenario. Its RED
is TASK 0d's C14 row, run on the W2-P3 base exe (`27bdec94e`): no freeze, but
the psi evs carried actionId 0 ((7 psi 0) mc, (21 psi 0) panic), no `ai`
context, and C2's panic rode a context-less `sync` (30 sync 0).

Two scenarios (the two halves of spec row C14), ONE boot, in this order:

  C14-mc     mind control (cycle 1, battle turn 1 -> 2). The terror mission
             with the sectoid race, map seed SEED_MAP. P (the Sectoid Leader,
             psiSkill 50, owns ALIEN_PSI_WEAPON PSI_WEAPON_ID) stripped (BOTH;
             battle_strip_unit keeps the special weapon, which is not in the
             inventory - F875: an armed P prefers its pistol) and C stripped
             (BOTH; deleted ids compared as SETS, F882). P on P_TILE facing C
             and C2; C and C2 on C_TILE / C2_TILE facing AWAY from P (neither
             spots P, F875); P base tu P_TU and psiSkill P_PSI_SKILL (BOTH);
             C psiStrength 0 (BOTH). Host set_seed SEED_C14 right before its
             END TURN press. The host shows a vanilla infobox with the mind
             control: the host dismisses it (dismiss_popup, host only, F876).
             GREEN: P's first `ai` context of the alien side is {kind psi,
             actorId P, nestedIn 0, hasFinal true} and its evs are exactly
             psi {actor P, unit C, action mc, success true} -> bt_action_end
             (no `turn`); after the cycle C faction hostile and
             mindControllerId P on both.
  C14-panic  the revert and the psi panic (cycle 2, turn 2 -> 3). P and C2
             re-teleported to the same tiles (BOTH); C psiStrength 100 (out of
             P's reach) and C2 psiStrength 0 (BOTH); host set_seed SEED_C14P
             right before its END TURN press. C reverts to the player faction
             at the PLAYER -> HOSTILE side start (N11, F874). P's psi panic
             lowers C2's morale; at the player side start of turn 3 C2 panics
             and freezes in place (F877); the host dismisses its panic infobox
             (host only, F876).
             GREEN: after the cycle C faction player on both; P's first `ai`
             context of the alien side is {kind psi, actorId P, nestedIn 0,
             hasFinal true} with evs exactly psi {actor P, unit C2, action
             panic, success true} -> bt_action_end; C2's morale lowered and
             equal on both (C2_MORALE_END: -70 by the psi, +15 at the panic's
             end); exactly one host context {origin panic, actorId C2,
             nestedIn 0, hasFinal true} after the cycle's last side_transition,
             its evs exactly panic {unit C2, mode freeze} -> bt_action_end (the
             C13 panic context shape); C2 on C2_TILE, STANDING, TU 0 on both.

Common asserts (spec (f) as amended by B1 RQ5, per scenario, after its chain
settled): W2-P2's common asserts (hash_now {full:true} ALL buckets EQUAL;
desyncSeen false on both; client coopClientBStatePushes unchanged and host 0;
client deltaEvsApplied increased; deltaUnresolved, deltaUnsupported,
deltaRemoveMissing, deltaAddExisting 0 on both; staging writes on BOTH with
equal responses); host contextBeginRefused 0; contextsOpened grew by exactly
the number of contexts the scenario closed; every chain ev carries the id of a
context the scenario closed; every context has exactly one bt_action_end, its
last ev, recorded in closedContexts (endSeq); no `sync` and no
side_transition inside a context; every side_transition carries actionId 0;
the client log holds the host's seqs/kinds/actionIds.
contextsClosedAtEndTurn is a diagnostic (printed, never asserted, RQ5).

Probes: event_state closedContexts, contextsOpened, contextBeginRefused,
contextsClosedAtEndTurn, cueCounts, deltaRing, lastWalk, the W2-P2 delta
counters; battle_state units (type, faction, originalFaction,
mindControllerId, mindControlled, morale, status, tu, position, psiWeapon);
battle_items (owner, slot); the host's own `[coop-cue]` log lines for the
payloads and its `[coop-delta] attached` lines (the revert, printed);
hash_now {full:true}.

Bring-up (deterministic, never searched here; ledger `## W2-P3 TASK 0c`,
scratch w2p3/T0c/constants.md, 3 boots identical plus a 2.6 s NextTurnState
dwell variant on both cycles): set_seed SEED_ROSTER on the HOST right before
its open_new_battle; newbattle_mission STR_TERROR_MISSION, then
newbattle_race STR_SECTOID (pre_seat), set_seed SEED_MAP right before
newbattle_ok, seat_count=2, MAP_FP asserted on both; session.pin_ai_neutral
(the 23 non-player units); RQ15: every live player unit's reactions 0 on
BOTH. Every lever pair applies to the CLIENT first, then the HOST (F607). The
seeds are set on the HOST immediately before the press that starts the chain.

Each scenario prints ONE "EVIDENCE <id>:" line with both machines' fields
BEFORE its green conditions are checked; main() runs every scenario even
after an earlier one failed and prints "PASS <id>" / "FAIL <id>: <message>".
Every wait is bounded; a wait that times out is recorded in the EVIDENCE line
and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when both scenarios pass, 2 otherwise
(a bring-up failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_psi.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_w2_delta_core import diff_buckets, short, both, tele_both, common_fails, finish
from test_w2_ai_origins import host_payloads, ctx_probes, ctx_view, sv, bring_up_lobby_roster_pinned
from test_w2_turn_cues import (begin, end, cycle, rec_evidence, cycle_fails, context_fails, payload, held_by_client,
                               items, st_seqs, panic_context_fails, c2_state_fails, c2_resolved)

# ----- bring-up (W2-P3 TASK 0c, T0c constants.md "Common bring-up" + "C14") -----
SEED_ROSTER = 1                  # set_seed on the HOST right before its open_new_battle (F501)
SEED_MAP = 1                     # set_seed in pre_ok right before newbattle_ok
MISSION, RACE = "STR_TERROR_MISSION", "STR_SECTOID"   # newbattle_mission, then newbattle_race (pre_seat)
MAP_FP = -3.451266327757785e+18  # host AND client battle_state.mapFingerprint (the C12b map; the race changes the aliens)
SEATED = [8, 9]                  # the client seat's soldiers
PINNED = list(range(1000000, 1000023))   # pin_ai_neutral: the 23 non-player units
PORT = "48638"
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
STATUS_STANDING = 0

# ----- C14 (T0c constants.md "C14"; F874-F877) -----
P_ID, P_TYPE = 1000008, "STR_SECTOID_LEADER"   # spawn (45,45,0) dir 6, psiSkill 50, psiStrength 50
PSI_WEAPON_ID = 84               # ALIEN_PSI_WEAPON, owner P, slot "" (not in P's inventory; kept by the strip)
P_STRIPPED = [85, 87]            # battle_strip_unit P deleted (STR_PLASMA_PISTOL + its clip), as a set
C_ID, C2_ID = 8, 9               # client seat: C (mind-controlled) and C2 (psi panic)
P_TILE, P_DIR = (30, 24, 0), 6   # open street, faces C and C2
C_TILE, C_DIR = (26, 23, 0), 6   # faces AWAY from P
C2_TILE, C2_DIR = (26, 25, 0), 6
P_TU, P_PSI_SKILL = 54, 50       # set_stat tu (no refill: recovered at P's side start) + psiSkill (both)
C_PSI_STRENGTH_1 = 0             # cycle 1: C in P's reach
SEED_C14 = 1                     # host set_seed right before its cycle-1 END TURN press: mind control of C
C_PSI_STRENGTH_2 = 100           # cycle 2: C out of P's reach
C2_PSI_STRENGTH_2 = 0
SEED_C14P = 1                    # host set_seed right before its cycle-2 END TURN press: psi panic on C2
C2_MORALE_END = 45               # 100 - 70 (psi panic) + 15 (UnitPanicBState at the panic's end)
PANIC_MODE = "freeze"            # F877: C2's panic at turn 3 resolves in place (no walk, no shot)
PSI_CHAIN = ["psi", "bt_action_end"]
PANIC_CHAIN = ["panic", "bt_action_end"]
PAYLOAD_EXTRA = ("psi",)         # payloads read beyond test_w2_turn_cues.end()'s kinds
UNIT_KEYS = ("type", "faction", "originalFaction", "mindControllerId", "mindControlled", "status", "isOut",
             "onTile", "x", "y", "z", "direction", "tu", "health", "morale", "psiWeapon", "specialWeapons")


# ===================== small probes =====================


def units(gc):
    return session.units_by_id(battle_state(gc))


def uview(u):
    if not u:
        return None
    return {k: u.get(k) for k in UNIT_KEYS}


def units_evidence(rec, ids):
    return {uid: {"host": uview(rec["uh"].get(uid)), "client": uview(rec["uc"].get(uid))} for uid in ids}


def owned_items(its, uid):
    return sorted((i, it.get("type"), it.get("slot")) for i, it in its.items() if it.get("owner") == uid)


def log_size(gc):
    try:
        return os.path.getsize(os.path.join(gc.user_dir, "openxcom.log"))
    except OSError:
        return 0


def faction_delta_lines(gc, off):
    """This machine's `[coop-delta] attached` log lines since byte `off` that
    carry a unit faction or mind-controller field (printed, never asserted)."""
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as f:
            f.seek(off)
            lines = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [ln.split("] ", 1)[-1][:400] for ln in lines
            if "[coop-delta] attached" in ln and ('"faction"' in ln or '"mindController' in ln or '"mcId"' in ln)]


def strip_both(host, client, uid):
    """battle_strip_unit on BOTH (client first, F607). `deleted` lists each
    machine's own inventory order (F882), so the two are compared as SETS."""
    rc = client.cmd({"cmd": "battle_strip_unit", "unit": uid})
    rh = host.cmd({"cmd": "battle_strip_unit", "unit": uid})
    assert rh.get("ok") and rc.get("ok"), f"battle_strip_unit {uid} failed: host={rh} client={rc}"
    dh, dc = rh.get("deleted") or [], rc.get("deleted") or []
    assert sorted(dh) == sorted(dc) and rh.get("skippedSpecial") == rc.get("skippedSpecial"), (
        f"battle_strip_unit {uid} differs as sets: host={dh} {rh.get('skippedSpecial')} client={dc} "
        f"{rc.get('skippedSpecial')}")
    return {"deleted": sorted(dh), "hostOrder": dh, "clientOrder": dc, "skippedSpecial": rh.get("skippedSpecial")}


def psi_stat_both(host, client, uid, stat, value):
    return both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": stat,
                               "value": value}, ("psiSkill", "psiStrength"))


def read_extra_payloads(host, rec):
    rec["pl"].update(host_payloads(host, [e["seq"] for e in rec["hev"] if e["kind"] in PAYLOAD_EXTRA]))


# ===================== checks =====================


def psi_context_fails(rec, victim, action, what):
    """P's first `ai` context of the scenario (by endSeq) = {kind psi, actorId
    P, nestedIn 0, hasFinal true} with evs exactly PSI_CHAIN; the first `psi`
    ev = {actor P, unit victim, action, success true} in that context.
    Returns (fails, P's ai contexts, the first one's evs, the psi evs)."""
    fails = []
    ai_p = sorted([c for c in rec["closed"] if c.get("origin") == "ai" and c.get("actorId") == P_ID],
                  key=lambda c: c.get("endSeq") or 0)
    c1 = ai_p[0] if ai_p else None
    cevs = [e for e in rec["hev"] if c1 and e["actionId"] == c1.get("actionId")]
    psis = [e for e in rec["hev"] if e["kind"] == "psi"]
    if not c1:
        fails.append(f"{what}: no host context {{origin ai, actorId {P_ID}}} (new entries "
                     f"{[ctx_view(c) for c in rec['closed']]})")
    else:
        if (c1.get("kind"), c1.get("nestedIn"), c1.get("hasFinal")) != ("psi", 0, True):
            fails.append(f"{what}: P's first ai context {ctx_view(c1)} (want kind psi, nestedIn 0, hasFinal true)")
        if [e["kind"] for e in cevs] != PSI_CHAIN:
            fails.append(f"{what}: P's first ai context {c1.get('actionId')} evs {sv(cevs)} (want exactly "
                         f"{PSI_CHAIN}, no `turn`)")
        missing = [e["seq"] for e in cevs if not held_by_client(rec, e)]
        if missing:
            fails.append(f"{what}: the client log does not hold P's psi context evs at seq(s) {missing}")
    if not psis:
        fails.append(f"{what}: no `psi` ev in the host log (host evs {sv(rec['hev'])})")
    else:
        p = payload(rec, psis[0])
        if (p.get("actor"), p.get("unit"), p.get("action"), p.get("success")) != (P_ID, victim, action, True):
            fails.append(f"{what}: psi seq {psis[0]['seq']} payload {p or None} (want actor {P_ID}, unit {victim}, "
                         f"action {action}, success true)")
        if c1 and psis[0]["actionId"] != c1.get("actionId"):
            fails.append(f"{what}: psi seq {psis[0]['seq']} carries actionId {psis[0]['actionId']} (want P's ai "
                         f"context {c1.get('actionId')})")
    return fails, ai_p, cevs, psis


def unit_fails(rec, uid, want, what):
    """`want` = {field: value} on BOTH machines' battle_state unit `uid`."""
    fails = []
    for name, u in (("host", rec["uh"].get(uid)), ("client", rec["uc"].get(uid))):
        got = {k: (u or {}).get(k) for k in want}
        if not u or got != want:
            fails.append(f"{what}: unit {uid} on the {name} {got} (want {want})")
    return fails


# ===================== scenarios =====================


def c14_mc(host, client, ctx):
    rec = begin(host, client)
    sp = strip_both(host, client, P_ID)
    sc = strip_both(host, client, C_ID)
    tele_both(host, client, P_ID, P_TILE, P_DIR)
    tele_both(host, client, C_ID, C_TILE, C_DIR)
    tele_both(host, client, C2_ID, C2_TILE, C2_DIR)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": P_ID, "stat": "tu", "value": P_TU},
         ("tu",))
    rp = psi_stat_both(host, client, P_ID, "psiSkill", P_PSI_SKILL)
    rcs = psi_stat_both(host, client, C_ID, "psiStrength", C_PSI_STRENGTH_1)
    staged_diff = diff_buckets(host, client)
    uh0, uc0 = units(host), units(client)
    staged = {"P psiWeapon h/c": ((uh0.get(P_ID) or {}).get("psiWeapon"), (uc0.get(P_ID) or {}).get("psiWeapon")),
              "C": uview(uh0.get(C_ID)), "C2": uview(uh0.get(C2_ID))}
    cycle(host, client, SEED_C14, rec, "cycle 1")
    end(host, client, rec)
    read_extra_payloads(host, rec)
    pfails, ai_p, cevs, psis = psi_context_fails(rec, C_ID, "mc", "C14-mc")
    print(f"EVIDENCE C14-mc: strip P={sp} strip C={sc}; P {P_TILE}/{P_DIR} C {C_TILE}/{C_DIR} C2 {C2_TILE}/{C2_DIR}; "
          f"psi responses (psiSkill, psiStrength) P={(rp.get('psiSkill'), rp.get('psiStrength'))} C="
          f"{(rcs.get('psiSkill'), rcs.get('psiStrength'))}; staged={staged} stagedDiff={staged_diff}; seed {SEED_C14}; "
          f"cycle side_transitions={st_seqs(rec['hev'])}; P's ai contexts={[ctx_view(c) for c in ai_p]} first's evs="
          f"{sv(cevs)}; psi evs (seq, actionId, payload)={[(e['seq'], e['actionId'], payload(rec, e)) for e in psis]}; "
          f"units={units_evidence(rec, [P_ID, C_ID, C2_ID])}; {rec_evidence(rec)}", flush=True)
    fails = list(rec["notes"])
    if sp["deleted"] != P_STRIPPED:
        fails.append(f"battle_strip_unit P deleted {sp['deleted']} (want {P_STRIPPED})")
    if staged["P psiWeapon h/c"] != (PSI_WEAPON_ID, PSI_WEAPON_ID):
        fails.append(f"P psiWeapon after the staging host/client={staged['P psiWeapon h/c']} (want {PSI_WEAPON_ID} on "
                     f"both: the strip keeps the special weapon)")
    if (rp.get("psiSkill"), rcs.get("psiStrength")) != (P_PSI_SKILL, C_PSI_STRENGTH_1):
        fails.append(f"psi staging responses P psiSkill={rp.get('psiSkill')} C psiStrength={rcs.get('psiStrength')} "
                     f"(want {P_PSI_SKILL}, {C_PSI_STRENGTH_1})")
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    fails += cycle_fails(rec, "C14-mc")
    fails += pfails
    fails += unit_fails(rec, C_ID, {"faction": FACTION_HOSTILE, "mindControllerId": P_ID}, "C14-mc C")
    fails += context_fails(rec, "C14-mc")
    fails += common_fails(host, client, rec["before"], {}, "C14-mc")
    finish(fails)


def c14_panic(host, client, ctx):
    rec = begin(host, client)
    tele_both(host, client, P_ID, P_TILE, P_DIR)
    tele_both(host, client, C2_ID, C2_TILE, C2_DIR)
    rc = psi_stat_both(host, client, C_ID, "psiStrength", C_PSI_STRENGTH_2)
    rc2 = psi_stat_both(host, client, C2_ID, "psiStrength", C2_PSI_STRENGTH_2)
    staged_diff = diff_buckets(host, client)
    uh0, uc0 = units(host), units(client)
    staged = {"C": {"host": uview(uh0.get(C_ID)), "client": uview(uc0.get(C_ID))},
              "C2": {"host": uview(uh0.get(C2_ID)), "client": uview(uc0.get(C2_ID))},
              "C2 items (id, type, slot)": owned_items(items(host), C2_ID)}
    off = log_size(host)
    cycle(host, client, SEED_C14P, rec, "cycle 2", extra=c2_resolved)
    end(host, client, rec)
    read_extra_payloads(host, rec)
    flines = faction_delta_lines(host, off)
    hev = rec["hev"]
    sts = st_seqs(hev)
    last_st = sts[-1] if sts else None
    pfails, ai_p, cevs, psis = psi_context_fails(rec, C2_ID, "panic", "C14-panic")
    kfails, pc, pevs = panic_context_fails(rec, PANIC_MODE, "C14-panic")
    m = ((rec["uh"].get(C2_ID) or {}).get("morale"), (rec["uc"].get(C2_ID) or {}).get("morale"))
    m0 = ((uh0.get(C2_ID) or {}).get("morale"), (uc0.get(C2_ID) or {}).get("morale"))
    print(f"EVIDENCE C14-panic: P {P_TILE}/{P_DIR} C2 {C2_TILE}/{C2_DIR}; psi responses (psiSkill, psiStrength) C="
          f"{(rc.get('psiSkill'), rc.get('psiStrength'))} C2={(rc2.get('psiSkill'), rc2.get('psiStrength'))}; staged="
          f"{staged} stagedDiff={staged_diff}; seed {SEED_C14P}; cycle side_transitions={sts}; host faction/mc delta "
          f"lines={flines}; P's ai contexts={[ctx_view(c) for c in ai_p]} first's evs={sv(cevs)}; psi evs (seq, "
          f"actionId, payload)={[(e['seq'], e['actionId'], payload(rec, e)) for e in psis]}; panic context="
          f"{ctx_view(pc)} kind={pc and pc.get('kind')} its evs={sv(pevs)} payloads="
          f"{[(e['seq'], e['kind'], payload(rec, e)) for e in pevs]}; C2 morale before h/c={m0} after h/c={m}; units="
          f"{units_evidence(rec, [P_ID, C_ID, C2_ID])}; {rec_evidence(rec)}", flush=True)
    fails = list(rec["notes"])
    if (rc.get("psiStrength"), rc2.get("psiStrength")) != (C_PSI_STRENGTH_2, C2_PSI_STRENGTH_2):
        fails.append(f"psi staging responses C psiStrength={rc.get('psiStrength')} C2 psiStrength="
                     f"{rc2.get('psiStrength')} (want {C_PSI_STRENGTH_2}, {C2_PSI_STRENGTH_2})")
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    fails += cycle_fails(rec, "C14-panic")
    fails += unit_fails(rec, C_ID, {"faction": FACTION_PLAYER}, "C14-panic C (N11: reverted at the hostile side start)")
    fails += pfails
    if m != (C2_MORALE_END, C2_MORALE_END) or m0[0] is None or not C2_MORALE_END < m0[0]:
        fails.append(f"C14-panic: C2 morale before h/c={m0} after h/c={m} (want lowered, {C2_MORALE_END} on both)")
    fails += kfails
    if pc:
        if [e["kind"] for e in pevs] != PANIC_CHAIN:
            fails.append(f"C14-panic: the panic context {pc.get('actionId')} evs {sv(pevs)} (want exactly {PANIC_CHAIN}: "
                         f"a freeze, F877)")
        if pevs and (last_st is None or pevs[0]["seq"] < last_st
                     or (psis and pevs[0]["seq"] < psis[0]["seq"])):
            fails.append(f"C14-panic: the panic context starts at seq {pevs[0]['seq']} (want after the psi "
                         f"{psis and psis[0]['seq']} and after the cycle's last side_transition {last_st}: the next "
                         f"player side start)")
    fails += c2_state_fails(rec, {"pos": C2_TILE, "status": STATUS_STANDING, "tu": 0}, "C14-panic")
    fails += context_fails(rec, "C14-panic")
    fails += common_fails(host, client, rec["before"], {}, "C14-panic")
    finish(fails)


SCENARIOS = (("C14-mc", c14_mc), ("C14-panic", c14_panic))


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}

    def pre_seat(h):
        r = h.cmd({"cmd": "newbattle_race", "race": RACE})
        assert r.get("ok"), f"newbattle_race {RACE} refused: {r}"

    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2, pre_seat=pre_seat,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, baked "
        f"MAP_FP={MAP_FP!r} ({MISSION} + {RACE}, SEED_MAP {SEED_MAP})")
    assert seated.get("soldierIds") == SEATED, f"seated {seated.get('soldierIds')} (baked {SEATED})"
    pinned = pin_ai_neutral(host, client, tag="w2p3-se-psi")
    assert pinned == PINNED, f"pin_ai_neutral pinned {pinned} (baked {PINNED[0]}..{PINNED[-1]})"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    pt = ((uh.get(P_ID) or {}).get("type"), (uc.get(P_ID) or {}).get("type"),
          (uh.get(P_ID) or {}).get("psiWeapon"), (uc.get(P_ID) or {}).get("psiWeapon"))
    assert pt == (P_TYPE, P_TYPE, PSI_WEAPON_ID, PSI_WEAPON_ID), (
        f"P {P_ID} type/psiWeapon host, client={pt} (want {P_TYPE}, {PSI_WEAPON_ID})")
    # RQ15: every live player unit's reactions 0 on BOTH machines (no reaction fire in the AI rows)
    rz = []
    for uid, u in sorted(uh.items()):
        if u.get("faction") == FACTION_PLAYER and not u.get("isOut"):
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
            rz.append(uid)
    for gc in (host, client):
        es = event_state(gc)
        u0 = session.units_by_id(battle_state(gc)).get(C2_ID) or {}
        assert (isinstance(es.get("deltaRing"), list) and isinstance(es.get("closedContexts"), list)
                and isinstance(es.get("contextsOpened"), dict) and isinstance(es.get("cueCounts"), dict)
                and isinstance(es.get("contextBeginRefused"), int) and "lastWalk" in es
                and all(k in u0 for k in ("faction", "mindControllerId", "morale", "status", "psiWeapon"))), (
            f"{gc.name} lacks a probe: deltaRing={es.get('deltaRing')!r} closedContexts={es.get('closedContexts')!r} "
            f"contextsOpened={es.get('contextsOpened')!r} contextBeginRefused={es.get('contextBeginRefused')!r} "
            f"lastWalk present={'lastWalk' in es} unit {C2_ID} keys={sorted(u0)}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2p3-se] boot ok: {MISSION} + {RACE} SEED_MAP={SEED_MAP} MAP_FP={MAP_FP!r} missionType="
          f"{hs.get('missionType')} turn={hs['turn']} seated={SEATED} pinned={len(pinned)} ({pinned[0]}..{pinned[-1]}) "
          f"P={pt[0]} psiWeapon={pt[2]} reactions 0 (both) for {rz} probes host={ctx_probes(host)} "
          f"client={ctx_probes(client)}", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49864, make_user_dir("w2p3_psi_host"))
    client = GameClient("client", 49865, make_user_dir("w2p3_psi_client"))
    results = {}
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:  # a bring-up failure fails the whole run
            print(f"FAIL boot: {type(e).__name__}: {e}", flush=True)
            return 2
        for name, fn in SCENARIOS:
            try:
                fn(host, client, ctx)
                results[name] = True
                print(f"PASS {name}", flush=True)
            except Exception as e:
                results[name] = False
                kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
                print(f"FAIL {name}: {kind}{e}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p3-se] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_psi: {len(passed)}/{len(SCENARIOS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
