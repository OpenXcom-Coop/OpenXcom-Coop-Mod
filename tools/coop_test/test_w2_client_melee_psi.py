"""W2-P4 S-C - test_w2_client_melee_psi.py: the second player hits with its own
stun rod, psi-attacks with its own psi amp and uses its own mind probe; the host
checks and runs every one of them (spec rewrite/prompts/w2p4_client_combat_intents.md
section (f) "test_w2_client_melee_psi.py (S-C)", sections (b)1-6, as amended by
AMENDMENT C1 (PR-Q2: K1 keeps refusing psi and the mind probe until S-C;
PR-Q3: the K8 action-menu refusal narrows for BA_HIT in S-C's green commit),
AMENDMENT C2 (F1129: a successful panic already sets the target's
mindControllerId, so the mind-control proof is the target's faction) and
AMENDMENT C4 (PR-Q18: the client-side baton check belongs to each intercept;
F1171: an item-kind refusal does not move coopLocalExecBlocked).

Before S-C the second player can do none of this. The stun rod's STUN row is
refused in the action menu (K8, ActionMenuState::handleAction) with "Only the
host can use this item" and coopLocalExecBlocked +0 (F1171). The psi click and
the mind-probe click are refused at K1 (BattlescapeGame::primaryAction's
targeting arm; client coopLocalExecBlocked +1, nothing sent). After S-C each
press becomes an intent (wire kinds of spec (b)1: `melee` for BA_HIT, `psi`
for the psi amp's panic and mind control, `use_item` for the mind probe). The
host admits it with vanilla's own checks and runs vanilla's own code under an
`intent` action context (context kinds of spec (b)3: `melee`, `psi`,
`mindprobe`) that ends in one bt_action_end; the ordering client runs vanilla's
aftermath for its own action.
Four scenarios, ONE boot, in this order:

  C21    stun rod (W2-P2 C5's staging with C). A stun rod on C (lever, both,
         clear hands), C -> C21_C_TILE facing north (dir 0), A2 -> C21_A2_TILE
         (the tile C faces) facing C, A2 health C21_A2_HEALTH, C TU max (all on
         BOTH). Client: TAB-select C, the right-hand box (2 rows: THROW,
         STUN), host set_seed SEED_C21, key 52 (STUN). RED: refused at K8 with
         "Only the host can use this item", coopLocalExecBlocked +0, nothing
         sent. GREEN: {origin intent, kind melee, actorId C} whose evs are
         exactly melee -> death -> corpse -> bt_action_end (the W2-P2 C5
         chain); the `melee` cue {actor C, unit A2, success true}; A2
         UNCONSCIOUS on both with equal stun; exactly one body item (unitLink
         A2) with the same id and tile on both; C TU C21_TU_AFTER on both;
         the client's own aftermath ran for the order (lastAftermath {actionId,
         kind melee}); the interim text is not on the client banner.
  C23d   mind probe. A mind probe on C (lever, both, clear hands); C ->
         FOV_C_TILE facing east (dir 2), A -> A_TILE facing south (dir 4), C TU
         max (both); one client `turn` intent toward A (a wave-1 kind): the
         turn halts at FOV_C_DIR on spotting A and A is visible on both
         (F1131: a teleport recomputes no FOV). Client: TAB, the right-hand box
         (2 rows: THROW, USE MIND PROBE), key 49 (psi cursor), HOME, one left
         click on A's tile. RED: refused at K1 (+1), nothing sent, no
         UnitInfoState, C TU unchanged. GREEN: {origin intent, kind mindprobe,
         actorId C} whose evs are exactly bt_action_end; client
         coopIntentsSent.use_item +1; C TU C23D_TU_AFTER on both; the client
         opens UnitInfoState at its own end (list_widgets state; lastAftermath
         actionId = the order's), the host does not.
  C22    psi: panic, then mind control. A psi amp on C (lever, both, clear
         hands); C and A kept where C23d left them (or placed and re-faced the
         same way); C psiSkill C_PSI_SKILL and A psiStrength A_PSI_STRENGTH
         (set_stat, both, client first); C TU max (both). Leg P: client TAB,
         the right-hand box (3 rows: THROW, MIND CONTROL, PANIC), key 50 (psi
         cursor), HOME, host set_seed SEED_C22P, one left click on A. Leg M:
         C TU max again (both), key 51, host set_seed SEED_C22M, one left
         click on A. The host shows vanilla's success infobox for each leg: it
         is recorded in EVIDENCE and dismissed host-only (H10 / D132: the
         message policy is W2-P6's; never asserted here). RED: both clicks
         refused at K1 (+1 each), nothing sent, A unchanged. GREEN: each leg
         {origin intent, kind psi, actorId C} whose evs are exactly psi ->
         bt_action_end; leg P's `psi` cue {action panic, actor C, unit A,
         success true}, A morale C22P_A_MORALE on both, A still hostile; leg
         M's `psi` cue {action mc, actor C, unit A, success true}, A faction
         player and mindControllerId C on both (C2 / F1129: the faction is the
         proof); C TU C22_TU_AFTER on both after each leg; lastAftermath
         {actionId, kind psi} for each leg.
  C22o   an order for the mind-controlled alien (W2-P4 S-E4; review N29 =
         F1096, Q8 (a); TASK 0 T0-8). Right after C22 on the same boot: A is
         FACTION_PLAYER with mindControllerId C on both (the precondition, C2
         / F1129). A's TU is set to max on both (client first; A has 0 TU
         after the mind control, so the turn below is affordable). One client
         `battle_intent turn` for A to A's facing + C22O_OCTANTS. RED (at
         S-E4.1): the host denies it `not_your_unit` (onIntent compares A's
         coop seat with the intent seat; the client's lastDeny), nothing
         executed. GREEN (at S-E4.2): admitted through the seat-parametrised
         commandsUnit (MJ-8: a mind-controlled unit is commanded by its
         controller's seat): host closedContexts gains exactly one {origin
         intent, kind turn, actorId A}; A's facing changed and equal on both.

The order puts C23d before C22: C22's mind control makes A a player unit, and
the mind probe refuses a target of the prober's own faction (primaryAction's
BT_MINDPROBE branch). C23d's FOV staging (C facing A, A spotted) is the one
C22 needs, so C22 keeps C and A where they stand (CLAUDE.local.md S2: a unit
is never teleported onto its own tile, it keeps the facing its last turn
produced) and re-faces C only when C23d did not leave C facing A. The client
UnitInfoState C23d's green opens is closed with the client's cancel key
before C22. A hand click while the client targets only cancels the targeting
(F503).

Common asserts (spec (f), after the order settles): hash_now {full:true} -
every bucket EQUAL; desyncSeen false on both; client coopClientBStatePushes
unchanged and host 0; the W2-P2 delta must-be-0 counters on both; every lever
item created on both machines with equal ids (both()). For an admitted order:
host closedContexts gains exactly one {origin intent, kind K, actorId C}; every
host ev of that actionId is in the client's log with the same seq, kind and
actionId; exactly one bt_action_end; client coopIntentsSent[wire kind] +1;
client inFlight null at the end; client intentTimeouts unchanged (no
STR_COOP_ACTION_TIMEOUT).

Out of this file (spec, amendments): the host's psi infobox (H10) is W2-P6's.

Probes: all exist before this file (S-A.1 added coopIntentsSent,
intentsReceived, lastActionHalt, lastAftermath). The cue payloads are read from
the HOST's own openxcom.log `[coop-cue]` lines.

FIXTURE (TASK 0 T0-7 on the S-C.1 red build, T0-8 and T0-9 = T0b; the
roster-pinned terror boot of test_w2_host_combat.py): set_seed SEED_ROSTER on
the HOST right before its open_new_battle, mission STR_TERROR_MISSION,
set_seed SEED_MAP right before newbattle_ok, seat_count 2, MAP_FP asserted on
both, the seated unit ids asserted (SEATED), pin_ai_neutral. Every lever pair
goes to the CLIENT first (F607). Item ids are read at run time from the lever
replies or by unitLink (F1107), never baked. The seeds were found with HOST
stand-ins that run the executor's states for C (SEED_C21: S-C.1's battle_fire
{mode melee}; SEED_C22P / SEED_C22M: battle_action psi_attack): S-C's executor
build proves them again (N18 = F1085).

RED-THEN-GREEN (spec (d) row S-C). Commit S-C.1 (this file and the battle_fire
melee / use stand-ins) is run ONCE and every scenario must FAIL with its RED
evidence. Commit S-C.2 is run ONCE and every scenario must PASS. C22o is S-E4's
row: its commit S-E4.1 is run ONCE with C21, C23d and C22 passing and C22o
failing with its RED evidence; commit S-E4.2 is run ONCE and all four must
PASS. Each scenario
prints ONE "EVIDENCE <id>:" line with both machines' fields BEFORE its green
conditions are checked; main() runs every scenario even after an earlier one
failed and prints "PASS <id>" / "FAIL <id>: <message>". Every wait is bounded;
a wait that times out is recorded in the EVIDENCE line and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all four scenarios pass, 2
otherwise (a bring-up failure is also 2). WV-D95: run in the foreground to
completion.

Run:  python tools/coop_test/test_w2_client_melee_psi.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_w2_delta_core import diff_buckets, short, both
from test_w2_delta_items import unit_view, tile_of
from test_w2_host_combat import bring_up_lobby_roster_pinned, ev_tuples
from test_w2_client_shoot import (top, snap, ubrief, press, units, place, set_tu_both, await_press, order_done,
                                  collect, ctx_view, chain_of, forwarded_fails, tu_fails, common_fails, finish,
                                  press_view, ui_view, send_intent, TU_MAX, C_TU_FULL, POLL_S, SENT_WAIT_S,
                                  ORDER_TIMEOUT_S)
from test_w2_client_grenade import (admitted_fails, cancel_client_targeting, open_hand_menu, target_order, settle,
                                    host_payloads_of)

# ----- bring-up (TASK 0: the roster-pinned terror boot) -----
MISSION = "STR_TERROR_MISSION"
SEED_MAP = 1
MAP_FP = -3.451266327757785e+18   # host battle_state.mapFingerprint on SEED_MAP 1 (T0a, every boot)
SEATED = [8, 9]                   # the client's seated units: C and C2
C_ID = 8
H_ID = 10                         # first host-seat soldier
A_ID, A2_ID = 1000000, 1000001    # Sectoid Soldiers
PORT = "48713"
COOP_SEAT_0 = 0
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
STATUS_UNCONSCIOUS = 7            # src/Mod/Unit.h enum UnitStatus

# ----- C21 (T0-7, hunted on the S-C.1 red build: seeds tried [1], met at 1, 3/3 proof boots) -----
C21_C_TILE, C21_C_DIR = (24, 24, 0), 0        # C faces north
C21_A2_TILE, C21_A2_DIR = (24, 23, 0), 4      # the tile C faces; A2 faces C
C21_A2_HEALTH = 5
SEED_C21 = 1                      # A2 UNCONSCIOUS (stun 120), one body item on (24,23,0)
STUN_ROD = "STR_STUN_ROD"
STUN_TU = 19                      # the rod's BA_HIT cost for C (max TU 64), measured with the stand-in
C21_TU_AFTER = C_TU_FULL - STUN_TU            # 45: a melee turns nobody (no UnitTurnBState)
C21_ROWS = 2                      # THROW + STUN
C21_CHAIN = ["melee", "death", "corpse", "bt_action_end"]
TEXT_ITEM_ACTION = "Only the host can use this item"   # STR_COOP_ITEM_ACTION_HOST_ONLY (the RED text)

# ----- C23d (T0-9 = T0b; the cost measured with S-C.1's battle_fire {mode use}) -----
FOV_C_TILE, FOV_C_DIR0 = (12, 26, 0), 2       # C teleported facing east, then a client `turn` toward A
FOV_TURN_TO, FOV_C_DIR = 0, 1                 # the turn to dir 0 halts at dir 1 on spotting A (F1131)
A_TILE, A_DIR = (12, 23, 0), 4
MIND_PROBE = "STR_MIND_PROBE"
PROBE_TU = 32                     # 50 % of C's max TU 64
C23D_TU_AFTER = C_TU_FULL - PROBE_TU
C23D_ROWS = 2                     # THROW + USE MIND PROBE
C23D_CHAIN = ["bt_action_end"]    # an instant kind: no cue, the one end

# ----- C22 (T0-8 = T0b; SEED_C22P / SEED_C22M re-proved 3/3 on the S-C.1 red build) -----
PSI_AMP = "STR_PSI_AMP"
C_PSI_SKILL = 100                 # C's natural psiSkill is 4
A_PSI_STRENGTH = 0
SEED_C22P = 1
SEED_C22M = 1
PSI_TU = 25                       # the amp's panic / mind-control cost (flat)
C22_TU_AFTER = C_TU_FULL - PSI_TU             # 39
C22P_A_MORALE = 70                # A morale 100 -> 70 after the panic
C22_ROWS = 3                      # THROW + MIND CONTROL + PANIC
C22_CHAIN = ["psi", "bt_action_end"]

# ----- C22o (T0-8's order for A after the mind control; review N29 = F1096) -----
C22O_OCTANTS = 2                  # T0b's order: A's facing + 2 octants

# ----- UI -----
KEY_ITEM1, KEY_ITEM2, KEY_ITEM3, KEY_ITEM4 = 49, 50, 51, 52   # keyBattleActionItem1..4
KEY_PROBE, KEY_PANIC, KEY_MC, KEY_STUN = KEY_ITEM1, KEY_ITEM2, KEY_ITEM3, KEY_ITEM4
KEY_CANCEL = 27                   # Options::keyCancel (SDLK_ESCAPE): closes UnitInfoState
CURSOR_PSI = 3                    # battle_state.cursorType CT_PSI (Map.h): psi amp and mind probe targeting
TURN_WAIT_S = 20


# ===================== small probes =====================


def a_view(u):
    v = unit_view(u)
    if v is not None:
        v["mindControllerId"] = u.get("mindControllerId")
        v["direction"] = u.get("direction")
        v["tu"] = u.get("tu")
    return v


def visible(gc, uid):
    """getVisible() of `uid` on this machine (battle_action set_stat with no
    stat is a read)."""
    return gc.cmd({"cmd": "battle_action", "action": "set_stat", "unit": uid}).get("visible")


def cue_fails(host, chain, kind, want, what):
    """Exactly one `kind` cue in `chain` whose payload holds `want`."""
    pl = host_payloads_of(host, chain, kind)
    got = {k: (pl[0] if pl else {}).get(k) for k in want}
    if len(pl) != 1 or got != want:
        return [f"{what}: `{kind}` cue payload(s) {pl} (want one with {want})"]
    return []


def aftermath_fails(rec, aid, kind, what):
    la = rec["client"]["lastAftermath"] or {}
    if aid is None or la.get("actionId") != aid or (kind is not None and la.get("kind") != kind):
        want = f"actionId {aid}" + (f", kind {kind}" if kind is not None else "")
        return [f"{what}: client lastAftermath={rec['client']['lastAftermath']} (want {{{want}}}: the client runs "
                f"vanilla's aftermath at its own order's end)"]
    return []


def close_client_popup(client):
    """The client's cancel key while a state other than the battlescape is on
    top (C23d's green UnitInfoState). Returns [top before(, after)]."""
    t0 = top(client)
    if t0 == "BattlescapeState":
        return [t0]
    press(client, KEY_CANCEL)
    try:
        client.wait_for("client BattlescapeState on top", lambda: top(client) == "BattlescapeState" or None,
                        timeout=5)
    except Exception:
        pass
    return [t0, top(client)]


# ===================== staging (client first, F607) =====================


def give(host, client, item):
    return both(host, client, {"cmd": "battle_give", "unit": C_ID, "item": item, "clear_hands": True},
                ("weaponId", "ammoId"))["weaponId"]


def set_stat_both(host, client, uid, stat, value):
    return both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": stat,
                               "value": value}, ("tu",))


def fov_stage(host, client, notes):
    """C on FOV_C_TILE facing A with A spotted on both (T0b, F1131): C and A are
    placed (kept when already there), then - unless C already faces
    FOV_C_DIR on both - one client `turn` intent toward A, which halts on
    spotting A. Returns the evidence."""
    ev = {"C": place(host, client, C_ID, FOV_C_TILE, FOV_C_DIR0), "A": place(host, client, A_ID, A_TILE, A_DIR)}
    dirs = (units(host)[C_ID].get("direction"), units(client)[C_ID].get("direction"))
    if dirs != (FOV_C_DIR, FOV_C_DIR):
        r = client.cmd({"cmd": "battle_intent", "kind": "turn", "actor": C_ID, "toDir": FOV_TURN_TO})
        ev["turnIntent"] = {k: r.get(k) for k in ("ok", "iseq", "error")}
        try:
            client.wait_for("the FOV turn is over (client slot empty, host idle, C re-faced on both)",
                            lambda: (order_done(host, client)
                                     and units(host)[C_ID].get("direction") != FOV_C_DIR0
                                     and units(host)[C_ID].get("direction") == units(client)[C_ID].get("direction"))
                            or None, timeout=TURN_WAIT_S, interval=0.1)
            session.wait_host_idle(host, client, timeout=20)
        except Exception as e:
            notes.append(f"FOV turn: {short(e)}")
    ev["dir"] = (units(host)[C_ID].get("direction"), units(client)[C_ID].get("direction"))
    ev["AVisible"] = (visible(host, A_ID), visible(client, A_ID))
    return ev


def fov_fails(ev):
    fails = []
    if ev.get("dir") != (FOV_C_DIR, FOV_C_DIR):
        fails.append(f"precondition: C faces {ev.get('dir')} host/client after the FOV staging (want {FOV_C_DIR})")
    if ev.get("AVisible") != (True, True):
        fails.append(f"precondition: A visible host/client {ev.get('AVisible')} (want True on both)")
    return fails


# ===================== the client's real-UI presses =====================


def stun_order(host, client, ev):
    """TAB C, the right-hand box, the host's set_seed, key 52 (STUN): the menu
    closes and vanilla's non-targeting execution point runs. Fills `ev`."""
    open_hand_menu(client, ev)
    host.ok({"cmd": "set_seed", "seed": SEED_C21})
    press(client, KEY_STUN)
    client.wait_for("client left the action menu", lambda: top(client) != "ActionMenuState" or None, timeout=5)
    ev["topAfterKey"] = top(client)


def await_order(host, client, before, notes, box):
    """await_press, plus the host's psi infobox: while the order runs, a host
    InfoboxState on top holds the chain (N7), so it is recorded into `box` and
    dismissed host-only (H10, never asserted). Returns {state, t, tEnd}."""
    t0 = time.time()
    state = "quiet"
    while time.time() - t0 < SENT_WAIT_S:
        ec, eh = event_state(client), event_state(host)
        if (ec.get("inFlight") or ec.get("coopIntentsSent") != before["client"]["coopIntentsSent"]
                or eh.get("lastSeqEmitted") != before["host"]["lastSeqEmitted"]):
            state = "sent"
            break
        if ec.get("coopLocalExecBlocked") != before["client"]["coopLocalExecBlocked"]:
            state = "refusedAtK1"
            break
        time.sleep(POLL_S)
    out = {"state": state, "t": round(time.time() - t0, 3)}
    if state == "sent":
        deadline = time.time() + ORDER_TIMEOUT_S
        done = False
        while time.time() < deadline:
            dismiss_host_infobox(host, box)
            if order_done(host, client):
                done = True
                break
            time.sleep(0.1)
        if not done:
            notes.append(f"order never finished within {ORDER_TIMEOUT_S}s (host top {top(host)})")
        time.sleep(0.3)
        dismiss_host_infobox(host, box)
    else:
        time.sleep(0.5)
    out["tEnd"] = round(time.time() - t0, 3)
    return out


def dismiss_host_infobox(host, box):
    t = top(host) or ""
    if "Infobox" not in t:
        return
    texts = [w.get("text") for w in host.cmd({"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]
    r = host.cmd({"cmd": "dismiss_popup"})
    box.append({"top": t, "texts": texts, "dismissed": r.get("handled") or r.get("type"),
                "after": top(host)})


# ===================== scenarios =====================


def c21_stun(host, client, ctx):
    notes = []
    rod = give(host, client, STUN_ROD)
    pc_ = place(host, client, C_ID, C21_C_TILE, C21_C_DIR)
    pa_ = place(host, client, A2_ID, C21_A2_TILE, C21_A2_DIR)
    both(host, client, {"cmd": "battle_set_unit_state", "unit": A2_ID, "health": C21_A2_HEALTH},
         ("health", "stun", "status"))
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv = {}
    try:
        stun_order(host, client, pv)
    except Exception as e:
        notes.append(f"real-UI stun: {short(e)}")
    out = await_press(host, client, before, notes)
    settle(host, client, notes)
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    hits = [c for c in new if c.get("origin") == "intent" and c.get("kind") == "melee" and c.get("actorId") == C_ID]
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    bodies = {n: [i for i in its.values() if i.get("unitLink") == A2_ID]
              for n, its in (("host", rec["ih"]), ("client", rec["ic"]))}
    print(f"EVIDENCE C21: staged rod={rod} C={pc_} A2={pa_} stagedDiff={staged} press={pv} outcome={out}; "
          f"{press_view(before, rec)}; ui={ui_view(before, rec)}; newContexts={new}; action={aid} "
          f"chain={[(e['seq'], e['kind']) for e in chain]}; host evs={ev_tuples(rec['hev'])} "
          f"client evs={ev_tuples(rec['cev'])}; A2 host={a_view(rec['uh'].get(A2_ID))} "
          f"client={a_view(rec['uc'].get(A2_ID))}; C host={ubrief(rec['uh'].get(C_ID))} "
          f"client={ubrief(rec['uc'].get(C_ID))}; bodies={bodies}; diff={rec['diff']} desync={rec['dsc']}; "
          f"notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if pv.get("rows") != C21_ROWS:
        fails.append(f"precondition: client menu rows {pv.get('rows')} (want {C21_ROWS})")
    fails += forwarded_fails(before, rec)
    f, cx = admitted_fails(before, rec, "melee", "melee", C_ID)
    fails += f
    kinds = [e["kind"] for e in chain]
    if cx and kinds != C21_CHAIN:
        fails.append(f"host evs of actionId {aid} = {kinds} (want exactly {C21_CHAIN})")
    if cx:
        fails += cue_fails(host, chain, "melee", {"actor": C_ID, "unit": A2_ID, "success": True}, "C21")
    sh, sc = rec["uh"].get(A2_ID) or {}, rec["uc"].get(A2_ID) or {}
    for n, u in (("host", sh), ("client", sc)):
        if u.get("status") != STATUS_UNCONSCIOUS:
            fails.append(f"{n} A2 {a_view(u)} (want status UNCONSCIOUS ({STATUS_UNCONSCIOUS}))")
    if sh.get("stun") is None or sh.get("stun") != sc.get("stun"):
        fails.append(f"A2 stun host={sh.get('stun')} client={sc.get('stun')} (want equal)")
    hb, cb = bodies["host"], bodies["client"]
    if len(hb) != 1 or len(cb) != 1 or hb[0] != cb[0] or tile_of(hb[0]) is None:
        fails.append(f"body items of A2 host={hb} client={cb} (want exactly one, equal on both, on a tile)")
    fails += tu_fails(rec, C_ID, C21_TU_AFTER)
    fails += aftermath_fails(rec, aid, "melee", "C21")
    if rec["clientUi"]["banner"] == TEXT_ITEM_ACTION:
        fails.append(f"client banner {rec['clientUi']['banner']!r} (the interim host-only refusal: want the press "
                     f"sent as an order)")
    fails += common_fails(host, client, before, "C21")
    finish(fails)


def c23d_probe(host, client, ctx):
    notes = []
    aim0 = cancel_client_targeting(client)
    probe = give(host, client, MIND_PROBE)
    set_tu_both(host, client, C_ID, TU_MAX)
    fv = fov_stage(host, client, notes)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv = {}
    try:
        target_order(client, pv, KEY_PROBE, CURSOR_PSI, A_TILE)
    except Exception as e:
        notes.append(f"real-UI mind probe: {short(e)}")
    out = await_press(host, client, before, notes)
    settle(host, client, notes)
    rec = collect(host, client, seq0)
    tops = {"host": top(host), "client": top(client)}
    new = ctx_view(before, rec)
    hits = [c for c in new if c.get("origin") == "intent" and c.get("kind") == "mindprobe"
            and c.get("actorId") == C_ID]
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    print(f"EVIDENCE C23d: staged probe={probe} aimCancel={aim0} fov={fv} stagedDiff={staged} press={pv} "
          f"outcome={out}; {press_view(before, rec)}; ui={ui_view(before, rec)}; top={tops}; newContexts={new}; "
          f"action={aid} chain={[(e['seq'], e['kind']) for e in chain]}; host evs={ev_tuples(rec['hev'])} "
          f"client evs={ev_tuples(rec['cev'])}; C host={ubrief(rec['uh'].get(C_ID))} "
          f"client={ubrief(rec['uc'].get(C_ID))}; A host={a_view(rec['uh'].get(A_ID))} "
          f"client={a_view(rec['uc'].get(A_ID))}; diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    fails += fov_fails(fv)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if pv.get("rows") != C23D_ROWS:
        fails.append(f"precondition: client menu rows {pv.get('rows')} (want {C23D_ROWS})")
    fails += forwarded_fails(before, rec)
    f, cx = admitted_fails(before, rec, "mindprobe", "use_item", C_ID)
    fails += f
    kinds = [e["kind"] for e in chain]
    if cx and kinds != C23D_CHAIN:
        fails.append(f"host evs of actionId {aid} = {kinds} (want exactly {C23D_CHAIN})")
    fails += tu_fails(rec, C_ID, C23D_TU_AFTER)
    if tops["client"] != "UnitInfoState":
        fails.append(f"client top state {tops['client']} (want UnitInfoState, opened at the order's own end)")
    if tops["host"] == "UnitInfoState":
        fails.append("host top state UnitInfoState (want none on the host: the screen is the ordering player's)")
    fails += aftermath_fails(rec, aid, None, "C23d")
    fails += common_fails(host, client, before, "C23d")
    finish(fails)


def psi_leg(host, client, key, seed, action, notes, box):
    """One C22 leg: C TU max (both), the real-UI psi order at A with the host's
    set_seed right before the click, the bounded wait (the host infobox
    recorded and dismissed host-only). Returns (before, rec, pv, out)."""
    set_tu_both(host, client, C_ID, TU_MAX)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv = {}
    try:
        target_order(client, pv, key, CURSOR_PSI, A_TILE, lambda: host.ok({"cmd": "set_seed", "seed": seed}))
    except Exception as e:
        notes.append(f"real-UI {action}: {short(e)}")
    out = await_order(host, client, before, notes, box)
    settle(host, client, notes)
    dismiss_host_infobox(host, box)
    rec = collect(host, client, seq0)
    return before, rec, pv, out


def psi_leg_fails(host, before, rec, pv, action, what):
    fails = []
    if pv.get("rows") != C22_ROWS:
        fails.append(f"{what}: precondition: client menu rows {pv.get('rows')} (want {C22_ROWS})")
    fails += [f"{what}: {m}" for m in forwarded_fails(before, rec)]
    f, cx = admitted_fails(before, rec, "psi", "psi", C_ID)
    fails += [f"{what}: {m}" for m in f]
    aid = cx.get("actionId") if cx else None
    chain = chain_of(rec, aid)
    kinds = [e["kind"] for e in chain]
    if cx and kinds != C22_CHAIN:
        fails.append(f"{what}: host evs of actionId {aid} = {kinds} (want exactly {C22_CHAIN})")
    if cx:
        fails += cue_fails(host, chain, "psi", {"action": action, "actor": C_ID, "unit": A_ID, "success": True}, what)
    fails += [f"{what}: {m}" for m in tu_fails(rec, C_ID, C22_TU_AFTER)]
    fails += aftermath_fails(rec, aid, "psi", what)
    return fails, aid


def c22_psi(host, client, ctx):
    notes = []
    popup0 = close_client_popup(client)
    aim0 = cancel_client_targeting(client)
    amp = give(host, client, PSI_AMP)
    fv = fov_stage(host, client, notes)
    rc = set_stat_both(host, client, C_ID, "psiSkill", C_PSI_SKILL)
    ra = set_stat_both(host, client, A_ID, "psiStrength", A_PSI_STRENGTH)
    stats = {"C psiSkill": rc.get("psiSkill"), "A psiStrength": ra.get("psiStrength")}
    staged = diff_buckets(host, client)
    a0 = {"host": a_view(units(host).get(A_ID)), "client": a_view(units(client).get(A_ID))}
    # ---- leg P: panic (key 50) ----
    box_p = []
    before, rec, pv, out = psi_leg(host, client, KEY_PANIC, SEED_C22P, "panic", notes, box_p)
    new = ctx_view(before, rec)
    common_p = common_fails(host, client, before, "C22 leg P")   # leg P's end state, before leg M
    # ---- leg M: mind control (key 51) ----
    notes_m = []
    box_m = []
    before_m, rec_m, pv_m, out_m = psi_leg(host, client, KEY_MC, SEED_C22M, "mc", notes_m, box_m)
    new_m = ctx_view(before_m, rec_m)
    common_m = common_fails(host, client, before_m, "C22 leg M")
    fp, aid_p = psi_leg_fails(host, before, rec, pv, "panic", "leg P")
    fm, aid_m = psi_leg_fails(host, before_m, rec_m, pv_m, "mc", "leg M")
    print(f"EVIDENCE C22: staged amp={amp} popupClose={popup0} aimCancel={aim0} fov={fv} stats={stats} "
          f"stagedDiff={staged} A before host={a0['host']} client={a0['client']} | "
          f"LEG P press={pv} outcome={out}; {press_view(before, rec)}; ui={ui_view(before, rec)}; hostInfobox={box_p}; "
          f"newContexts={new}; action={aid_p} chain={[(e['seq'], e['kind']) for e in chain_of(rec, aid_p)]}; "
          f"host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; A host={a_view(rec['uh'].get(A_ID))} "
          f"client={a_view(rec['uc'].get(A_ID))}; C host={ubrief(rec['uh'].get(C_ID))} "
          f"client={ubrief(rec['uc'].get(C_ID))}; diff={rec['diff']} desync={rec['dsc']}; notes={notes} | "
          f"LEG M press={pv_m} outcome={out_m}; {press_view(before_m, rec_m)}; ui={ui_view(before_m, rec_m)}; "
          f"hostInfobox={box_m}; newContexts={new_m}; action={aid_m} "
          f"chain={[(e['seq'], e['kind']) for e in chain_of(rec_m, aid_m)]}; host evs={ev_tuples(rec_m['hev'])} "
          f"client evs={ev_tuples(rec_m['cev'])}; A host={a_view(rec_m['uh'].get(A_ID))} "
          f"client={a_view(rec_m['uc'].get(A_ID))}; C host={ubrief(rec_m['uh'].get(C_ID))} "
          f"client={ubrief(rec_m['uc'].get(C_ID))}; diff={rec_m['diff']} desync={rec_m['dsc']}; notes={notes_m}",
          flush=True)
    fails = list(notes) + list(notes_m)
    fails += fov_fails(fv)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    # leg P: the panic
    fails += fp
    ah, ac = rec["uh"].get(A_ID) or {}, rec["uc"].get(A_ID) or {}
    got = ((ah.get("morale"), ah.get("faction")), (ac.get("morale"), ac.get("faction")))
    if got != ((C22P_A_MORALE, FACTION_HOSTILE), (C22P_A_MORALE, FACTION_HOSTILE)):
        fails.append(f"leg P: A (morale, faction) host={got[0]} client={got[1]} (want ({C22P_A_MORALE}, "
                     f"{FACTION_HOSTILE}) on both)")
    fails += [f"leg P: {m}" for m in common_p]
    # leg M: the mind control (C2 / F1129: the faction is the proof)
    fails += fm
    ah, ac = rec_m["uh"].get(A_ID) or {}, rec_m["uc"].get(A_ID) or {}
    got = ((ah.get("faction"), ah.get("mindControllerId")), (ac.get("faction"), ac.get("mindControllerId")))
    if got != ((FACTION_PLAYER, C_ID), (FACTION_PLAYER, C_ID)):
        fails.append(f"leg M: A (faction, mindControllerId) host={got[0]} client={got[1]} (want ({FACTION_PLAYER}, "
                     f"{C_ID}) on both)")
    fails += [f"leg M: {m}" for m in common_m]
    finish(fails)


def c22o_order(host, client, ctx):
    notes = []
    a0 = {"host": a_view(units(host).get(A_ID)), "client": a_view(units(client).get(A_ID))}
    mc = all((a0[n] or {}).get("faction") == FACTION_PLAYER and (a0[n] or {}).get("mindControllerId") == C_ID
             for n in ("host", "client"))
    staged = None
    req = None
    si = {}
    d0 = None
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    if mc:
        try:
            set_tu_both(host, client, A_ID, TU_MAX)
            staged = diff_buckets(host, client)
            d0 = units(client)[A_ID].get("direction")
            req = {"cmd": "battle_intent", "kind": "turn", "actor": A_ID, "toDir": (d0 + C22O_OCTANTS) % 8}
            before = snap(host, client)
            seq0 = before["host"]["lastSeqEmitted"] or 0
            si = send_intent(host, client, req, notes, timeout=ORDER_TIMEOUT_S)
        except Exception as e:
            notes.append(f"order: {short(e)}")
        settle(host, client, notes)
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    ah, ac = rec["uh"].get(A_ID) or {}, rec["uc"].get(A_ID) or {}
    print(f"EVIDENCE C22o: A before host={a0['host']} client={a0['client']} mindControlled={mc} stagedDiff={staged} "
          f"request={req} intent={ {k: si.get(k) for k in ('sent', 'iseq', 'answer')} } "
          f"lastDeny={rec['client']['lastDeny']} banner={rec['clientUi']['banner']!r}; {press_view(before, rec)}; "
          f"newContexts={new}; host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; "
          f"A host={a_view(ah)} client={a_view(ac)}; diff={rec['diff']} desync={rec['dsc']}; notes={notes}",
          flush=True)
    fails = list(notes)
    if not mc:
        fails.append(f"precondition: A host={a0['host']} client={a0['client']} (want faction {FACTION_PLAYER} and "
                     f"mindControllerId {C_ID} on both: C22's mind control)")
        finish(fails)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if not si.get("sent"):
        fails.append(f"battle_intent turn answered {si.get('resp')} (want sent: an iseq)")
    ld = rec["client"]["lastDeny"] or {}
    if si.get("iseq") and ld.get("iseq") == si.get("iseq"):
        fails.append(f"the host denied the order: client lastDeny {ld} (want admitted: a mind-controlled unit is "
                     f"commanded by its controller's seat, Q8 / MJ-8)")
    f, _ = admitted_fails(before, rec, "turn", "turn", A_ID)
    fails += f
    if ah.get("direction") is None or ah.get("direction") != ac.get("direction") or ah.get("direction") == d0:
        fails.append(f"A direction host={ah.get('direction')} client={ac.get('direction')} (want equal on both and "
                     f"changed from {d0})")
    fails += common_fails(host, client, before, "C22o")
    finish(fails)


SCENARIOS = (("C21", c21_stun), ("C23d", c23d_probe), ("C22", c22_psi), ("C22o", c22o_order))


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} ({MISSION}, SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p4-sc")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hs["units"] if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == SEATED, f"seated client units {seated_uids} (baked {SEATED})"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    ub = session.units_by_id(hs)
    assert (ub.get(C_ID) or {}).get("tu") == C_TU_FULL, f"C at bring-up {ubrief(ub.get(C_ID))} (baked TU {C_TU_FULL})"
    for uid in (A_ID, A2_ID):
        u = ub.get(uid) or {}
        assert u.get("faction") == FACTION_HOSTILE and not u.get("isOut"), (
            f"alien {uid} at bring-up: {unit_view(u)} (want a live FACTION_HOSTILE unit)")
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("coopIntentsSent"), dict) and isinstance(es.get("intentsReceived"), dict)
                and "lastActionHalt" in es and "lastAftermath" in es), (
            f"{gc.name} event_state lacks the W2-P4 probes: coopIntentsSent={es.get('coopIntentsSent')!r} "
            f"intentsReceived={es.get('intentsReceived')!r}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2p4-sc] boot ok: {MISSION} MAP_FP={MAP_FP!r} turn={hs['turn']} seated={seated_uids} H={H_ID} "
          f"pinned={len(pinned)} C={ubrief(ub.get(C_ID))} A={ubrief(ub.get(A_ID))} A2={ubrief(ub.get(A2_ID))}",
          flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49874, make_user_dir("w2p4_client_melee_psi_host"))
    client = GameClient("client", 49875, make_user_dir("w2p4_client_melee_psi_client"))
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
                print(f"[w2p4-sc] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_client_melee_psi: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
