"""W2-H32 - test_w2_ai_mc_soldier.py: in a co-op battle the alien AI acts with a
soldier it mind-controlled in that same alien turn, as in vanilla (spec
rewrite/prompts/w2h32_ai_uses_mc_soldier.md section (f); TASK 0 pins
rewrite/w2h32-task0/CONSTANTS.md, boots Pa / Pb equal; lead L-H29-2, F11677;
rulings QH29-7 (a), D151 "follow vanilla", MJ-8, D87 (b), QH32-1..QH32-5 (a)).

Row AM (boot P: the co-op classic terror mission with sectoids, lobby key
48759, user dirs w2h32_p_host / w2h32_p_client with coopGhostStepper true,
test_w2_psi's C14 bring-up and C14-mc staging). The sectoid leader P
mind-controls the partner's soldier C with the REAL alien AI in the alien turn
of cycle 1 (SEED_C14 on the host right before its END TURN press); the alien AI
then selects C in that same turn (BattlescapeGame::handleAI gives it its AI
module); cycle 2 with P inert (psiSkill 0, tu 0) returns C to its owner at the
next alien turn start.

Cells:
  AM-mc      (precondition) P's first `ai` context is the psi mind control of
             C; C faction hostile, mindControllerId P, coop seat 1 on both;
             cycle 1 ended on player turn 2 on both, no timeout note.
  AM-ai      the host's battle_state C hasAI true after cycle 1 (the host's AI
             selected C in the alien turn). RED at H1: false - the host's turn
             loop skips a unit whose seat tag is its owner's (coopMaySelectUnit).
  AM-flow    TCU.context_fails(cycle 1) == [] (every context the cycle closed
             is well formed, the AI's actions with C included).
  AM-back    after cycle 2: C faction player, coop 1 on both; the host's hasAI
             for C false (deleted at the release); cycle 2's cycle_fails and
             context_fails == [].
  AM-common  DC.common_fails == [] after cycle 1 and after cycle 2.
A bring-up miss fails every cell "boot" (ONE CAPTURE P: line), a staging miss
"staging"; a cell whose precondition (AM-mc) failed FAILs "not reached";
AM-common is evaluated in every case past the staging. The row prints ONE
EVIDENCE line before its cell lines.

RED at H1 (no product line): AM-ai only; AM-mc, AM-flow, AM-back, AM-common
PASS. GREEN (E1, connectionTCP.cpp coopMaySelectUnit): every cell PASS.

WV-D99 / WV-D100: one run is the result; no skip path, no second boot, no
alternative map, actor or seed. Exit 0 only when every cell passes, else 2.
WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_ai_mc_soldier.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_w2_delta_core import short, both, tele_both, diff_buckets, common_fails
from test_w2_ai_origins import bring_up_lobby_roster_pinned, ctx_view, sv
from test_w2_turn_cues import begin, end, cycle, cycle_fails, context_fails, st_seqs
from test_w2_psi import (strip_both, psi_stat_both, psi_context_fails, units, read_extra_payloads, SEED_MAP,
                         MISSION, RACE, MAP_FP, SEATED, PINNED, P_ID, P_TYPE, PSI_WEAPON_ID, P_STRIPPED, C_ID,
                         C2_ID, P_TILE, P_DIR, C_TILE, C_DIR, C2_TILE, C2_DIR, P_TU, P_PSI_SKILL,
                         C_PSI_STRENGTH_1, SEED_C14, SEED_C14P, FACTION_PLAYER, FACTION_HOSTILE)

KEY = "48759"                     # boot P lobby key (spec (F); 0 hits elsewhere at the tip, F12388)
C_SEAT = 1                        # C is the client seat's soldier (CONSTANTS.md: coop 1 on both)
CELLS = ("AM-mc", "AM-ai", "AM-flow", "AM-back", "AM-common")
EV_KEYS = ("tu", "x", "y", "z", "hasAI", "faction", "coop", "mindControllerId")


class Miss(Exception):
    """A bring-up or staging miss: every cell fails with this tag."""


def cv(u):
    return {k: (u or {}).get(k) for k in EV_KEYS} if u else None


def log_tail(gc, n=40):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as f:
            return f.read().decode("utf-8", errors="replace").splitlines()[-n:]
    except OSError as e:
        return [f"log unreadable: {e}"]


def capture(where, err, host, client):
    """ONE CAPTURE P: line - both machines' stacks, battle_state side / turn and the last 40 engine log lines."""
    cap = {"where": where, "err": err}
    for gc in (host, client):
        d = {}
        try:
            d["stack"] = gc.cmd({"cmd": "get_state"}).get("states")
        except Exception as e:
            d["stack"] = f"probe failed: {short(e)}"
        try:
            bs = battle_state(gc)
            d["side/turn"] = (bs.get("side"), bs.get("turn"))
        except Exception as e:
            d["side/turn"] = f"probe failed: {short(e)}"
        d["log"] = log_tail(gc)
        cap[gc.name] = d
    print(f"CAPTURE P: {json.dumps(cap, default=str)}", flush=True)


# ===================== bring-up (test_w2_psi boot()'s body, the key a parameter: F10917) =====================


def boot_p(host, client, key):
    bring_up_lobby_roster_pinned(host, client, key)
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
    pinned = pin_ai_neutral(host, client, tag="w2h32-am")
    assert pinned == PINNED, f"pin_ai_neutral pinned {pinned} (baked {PINNED[0]}..{PINNED[-1]})"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    pt = ((uh.get(P_ID) or {}).get("type"), (uc.get(P_ID) or {}).get("type"),
          (uh.get(P_ID) or {}).get("psiWeapon"), (uc.get(P_ID) or {}).get("psiWeapon"))
    assert pt == (P_TYPE, P_TYPE, PSI_WEAPON_ID, PSI_WEAPON_ID), (
        f"P {P_ID} type/psiWeapon host, client={pt} (want {P_TYPE}, {PSI_WEAPON_ID})")
    # RQ15: every live player unit's reactions 0 on BOTH machines (no reaction fire in the AI rows)
    for uid, u in sorted(uh.items()):
        if u.get("faction") == FACTION_PLAYER and not u.get("isOut"):
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
    for gc in (host, client):
        es = event_state(gc)
        u0 = session.units_by_id(battle_state(gc)).get(C_ID) or {}
        assert (isinstance(es.get("closedContexts"), list) and isinstance(es.get("contextsOpened"), dict)
                and isinstance(es.get("contextBeginRefused"), int)
                and all(k in u0 for k in ("faction", "mindControllerId", "coop", "hasAI", "tu"))), (
            f"{gc.name} lacks a probe: closedContexts={es.get('closedContexts')!r} contextsOpened="
            f"{es.get('contextsOpened')!r} contextBeginRefused={es.get('contextBeginRefused')!r} unit {C_ID} "
            f"keys={sorted(u0)}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2h32] boot ok: {MISSION} + {RACE} key {key} turn={hs.get('turn')} seated={SEATED} "
          f"pinned={len(pinned)} P={pt[0]} psiWeapon={pt[2]}", flush=True)


# ===================== row AM =====================


def stage_c14_mc(host, client):
    """TCU.begin BEFORE any staging write, then test_w2_psi c14_mc's staging (:316-:323) exactly. Returns rec."""
    rec = begin(host, client)
    sp = strip_both(host, client, P_ID)
    strip_both(host, client, C_ID)
    tele_both(host, client, P_ID, P_TILE, P_DIR)
    tele_both(host, client, C_ID, C_TILE, C_DIR)
    tele_both(host, client, C2_ID, C2_TILE, C2_DIR)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": P_ID, "stat": "tu", "value": P_TU},
         ("tu",))
    rp = psi_stat_both(host, client, P_ID, "psiSkill", P_PSI_SKILL)
    rcs = psi_stat_both(host, client, C_ID, "psiStrength", C_PSI_STRENGTH_1)
    staged_diff = diff_buckets(host, client)
    uh0, uc0 = units(host), units(client)
    pw = ((uh0.get(P_ID) or {}).get("psiWeapon"), (uc0.get(P_ID) or {}).get("psiWeapon"))
    bad = []
    if sp["deleted"] != P_STRIPPED:
        bad.append(f"battle_strip_unit P deleted {sp['deleted']} (want {P_STRIPPED})")
    if pw != (PSI_WEAPON_ID, PSI_WEAPON_ID):
        bad.append(f"P psiWeapon host/client={pw} (want {PSI_WEAPON_ID} on both)")
    if (rp.get("psiSkill"), rcs.get("psiStrength")) != (P_PSI_SKILL, C_PSI_STRENGTH_1):
        bad.append(f"psi staging P psiSkill={rp.get('psiSkill')} C psiStrength={rcs.get('psiStrength')} (want "
                   f"{P_PSI_SKILL}, {C_PSI_STRENGTH_1})")
    if staged_diff:
        bad.append(f"buckets differ after the staging: {staged_diff}")
    if bad:
        raise Miss("; ".join(bad))
    rec["C staged"] = {"host": cv(uh0.get(C_ID)), "client": cv(uc0.get(C_ID))}
    return rec


def c_fails(rec, want, what):
    """`want` = {field: value} on BOTH machines' battle_state unit C."""
    fails = []
    for name, u in (("host", rec["uh"].get(C_ID)), ("client", rec["uc"].get(C_ID))):
        got = {k: (u or {}).get(k) for k in want}
        if not u or got != want:
            fails.append(f"{what}: C {C_ID} on the {name} {got} (want {want})")
    return fails


def row_am(host, client, rec, res):
    cycle(host, client, SEED_C14, rec, "AM cycle 1")
    end(host, client, rec)
    read_extra_payloads(host, rec)
    common1 = common_fails(host, client, rec["before"], {}, "AM cycle 1")
    pfails, ai_p, cevs, psis = psi_context_fails(rec, C_ID, "mc", "AM")
    mc = list(rec["notes"]) + pfails + cycle_fails(rec, "AM cycle 1")
    mc += c_fails(rec, {"faction": FACTION_HOSTILE, "mindControllerId": P_ID, "coop": C_SEAT}, "AM-mc")
    has_ai = (rec["uh"].get(C_ID) or {}).get("hasAI")
    ai_fail = [] if has_ai is True else [
        f"AM-ai: the host's battle_state C {C_ID} hasAI={has_ai} after cycle 1 (want true: the host's alien AI "
        f"selects the soldier P mind-controlled in that alien turn and handleAI gives it its AI module; F11677)"]
    flow = context_fails(rec, "AM cycle 1")
    # cycle 2: P inert (both, client first), C returns to its owner at the next alien turn start
    rec2 = begin(host, client)
    r_psi = psi_stat_both(host, client, P_ID, "psiSkill", 0)
    r_tu = both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": P_ID, "stat": "tu", "value": 0,
                               "refill": True}, ("tu",))
    cycle(host, client, SEED_C14P, rec2, "AM cycle 2")
    end(host, client, rec2)
    common2 = common_fails(host, client, rec2["before"], {}, "AM cycle 2")
    back = list(rec2["notes"])
    if (r_psi.get("psiSkill"), r_tu.get("tu")) != (0, 0):
        back.append(f"AM-back: P inert replies psiSkill={r_psi.get('psiSkill')} tu={r_tu.get('tu')} (want 0, 0)")
    back += c_fails(rec2, {"faction": FACTION_PLAYER, "coop": C_SEAT}, "AM-back")
    if (rec2["uh"].get(C_ID) or {}).get("hasAI") is not False:
        back.append(f"AM-back: the host's C {C_ID} hasAI={(rec2['uh'].get(C_ID) or {}).get('hasAI')} after cycle 2 "
                    f"(want false: the module is deleted at the release)")
    back += cycle_fails(rec2, "AM cycle 2") + context_fails(rec2, "AM cycle 2")
    ai1 = sorted([c for c in rec["closed"] if c.get("origin") == "ai"], key=lambda c: c.get("endSeq") or 0)
    on_c = [c for c in ai1 if c.get("actorId") == C_ID]
    ev = {"ai contexts cycle 1 (actorId, kind, endSeq)": [(c.get("actorId"), c.get("kind"), c.get("endSeq"))
                                                          for c in ai1],
          "contexts naming C": [{"ctx": ctx_view(c), "evs": sv([e for e in rec["hev"]
                                                                if e["actionId"] == c.get("actionId")])} for c in on_c],
          "psi evs (seq, actionId)": [(e["seq"], e["actionId"]) for e in psis],
          "P first ai context evs": sv(cevs),
          "C staged": rec["C staged"],
          "C after cycle 1": {"host": cv(rec["uh"].get(C_ID)), "client": cv(rec["uc"].get(C_ID))},
          "C after cycle 2": {"host": cv(rec2["uh"].get(C_ID)), "client": cv(rec2["uc"].get(C_ID))},
          "side_transitions": (st_seqs(rec["hev"]), st_seqs(rec2["hev"])),
          "cycles": rec["cycles"] + rec2["cycles"], "dismissed": (rec["dismissed"], rec2["dismissed"]),
          "diff": (rec["diff"], rec2["diff"])}
    print(f"EVIDENCE AM: {json.dumps(ev, default=str)}", flush=True)
    res["AM-mc"] = mc
    res["AM-ai"] = ai_fail
    res["AM-flow"] = flow
    res["AM-back"] = back
    res["AM-common"] = common1 + common2


def main():
    t0 = time.time()
    host = GameClient("host", 49866, make_user_dir("w2h32_p_host", options={"coopGhostStepper": True}))
    client = GameClient("client", 49867, make_user_dir("w2h32_p_client", options={"coopGhostStepper": True}))
    res = {}
    rec = None
    stage = "boot"
    try:
        try:
            boot_p(host, client, KEY)
            stage = "staging"
            rec = stage_c14_mc(host, client)
            stage = "row"
            row_am(host, client, rec, res)
            if res["AM-mc"]:  # the precondition failed: the cells that rest on it are not reached
                for c in ("AM-ai", "AM-flow", "AM-back"):
                    res[c] = ["not reached (AM-mc failed)"]
        except Exception as e:
            msg = f"{type(e).__name__}: {short(e, 600)}"
            if stage in ("boot", "staging"):
                capture(stage, msg, host, client)
                for c in CELLS:
                    res[c] = [f"{stage} ({msg})"]
            else:
                for c in CELLS[:-1]:
                    res.setdefault(c, [f"not reached ({msg})"])
                if "AM-common" not in res:  # AM-common is evaluated in every case past the staging
                    try:
                        res["AM-common"] = [msg] + common_fails(host, client, rec["before"], {}, "AM (exception)")
                    except Exception as e2:
                        res["AM-common"] = [msg, f"common_fails: {short(e2)}"]
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2h32] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [c for c in CELLS if res.get(c) == []]
    for c in CELLS:
        if res.get(c) == []:
            print(f"PASS {c}", flush=True)
        else:
            print(f"FAIL {c}: {'; '.join(res.get(c) or ['no result'])}", flush=True)
    ok = len(passed) == len(CELLS)
    print(f"ROW AM: {'PASS' if ok else 'FAIL'} ({len(passed)}/{len(CELLS)} cells)", flush=True)
    print(f"\ntest_w2_ai_mc_soldier: {len(passed)}/{len(CELLS)} cells passed (fail="
          f"{[c for c in CELLS if c not in passed]}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
