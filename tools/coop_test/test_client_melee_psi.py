"""test_client_melee_psi.py: the second player hits with its own
stun rod, psi-attacks with its own psi amp and uses its own mind probe; the host
checks and runs every one of them.

Each press on the client becomes an intent (wire kinds `melee` for BA_HIT,
`psi` for the psi amp's panic and mind control, `use_item` for the mind
probe). The host admits it with vanilla's own checks and runs vanilla's own
code under an `intent` action context (context kinds `melee`, `psi`,
`mindprobe`) that ends in one bt_action_end; the ordering client runs
vanilla's aftermath for its own action. Four scenarios, ONE boot, in this
order:

  stun_rod_hit: the stun rod. A stun rod on C (staging command, both, clear
    hands), C -> STUN_C_TILE facing north (dir 0), A2 -> STUN_A2_TILE (the
    tile C faces) facing C, A2 health STUN_A2_HEALTH, C TU max (all on
    BOTH). Client: TAB-select C, the right-hand box (2 rows: THROW, STUN),
    host set_seed SEED_STUN, key 52 (STUN). Checks: {origin intent, kind
    melee, actorId C} whose evs are exactly melee -> death -> corpse ->
    bt_action_end (the chain of the host's own stun-rod hit); the `melee`
    cue {actor C, unit A2, success true}; A2 UNCONSCIOUS on both with equal
    stun; exactly one body item (unitLink A2) with the same id and tile on
    both; C TU STUN_TU_AFTER on both; the client's own aftermath ran for the
    order (lastAftermath {actionId, kind melee}); the host-only refusal text
    is not on the client banner.
  mind_probe_use: the mind probe. A mind probe on C (staging command, both,
    clear hands); C -> FOV_C_TILE facing east (dir 2), A -> A_TILE facing
    south (dir 4), C TU max (both); one client `turn` intent toward A: the
    turn halts at FOV_C_DIR on spotting A and A is visible on both (a
    teleport recomputes no FOV). Client: TAB, the right-hand box (2 rows:
    THROW, USE MIND PROBE), key 49 (psi cursor), HOME, one left click on A's
    tile. Checks: {origin intent, kind mindprobe, actorId C} whose evs are
    exactly bt_action_end; client coopIntentsSent.use_item +1; C TU
    PROBE_TU_AFTER on both; the client opens UnitInfoState at its own end
    (list_widgets state; lastAftermath actionId = the order's), the host
    does not.
  psi_panic_and_control: psi panic, then mind control. A psi amp on C
    (staging command, both, clear hands); C and A kept where mind_probe_use
    left them (or placed and re-faced the same way); C psiSkill C_PSI_SKILL
    and A psiStrength A_PSI_STRENGTH (set_stat, both, client first); C TU
    max (both). Panic leg: client TAB, the right-hand box (3 rows: THROW,
    MIND CONTROL, PANIC), key 50 (psi cursor), HOME, host set_seed
    SEED_PANIC, one left click on A. Mind-control leg: C TU max again
    (both), key 51, host set_seed SEED_MIND_CONTROL, one left click on A. A
    host InfoboxState that comes up during a leg is recorded in EVIDENCE and
    dismissed host-only (psi_messages wants none). Checks: each leg {origin
    intent, kind psi, actorId C} whose evs are exactly psi -> bt_action_end;
    the panic leg's `psi` cue {action panic, actor C, unit A, success true},
    A morale PANIC_A_MORALE on both, A still hostile; the mind-control leg's
    `psi` cue {action mc, actor C, unit A, success true}, A faction player
    and mindControllerId C on both (a successful panic already sets the
    target's mindControllerId, so the faction is the proof); C TU
    PSI_TU_AFTER on both after each leg; lastAftermath {actionId, kind psi}
    for each leg.
  controlled_alien_turn: an order for the mind-controlled alien. Right
    after psi_panic_and_control on the same boot: A is FACTION_PLAYER with
    mindControllerId C on both (the precondition). After the mind control A
    has 0 TU and a TU cap of 0, so battle_set_unit_state cannot raise its
    TU; `battle_action set_stat {stat tu, value A_TU_CAP, refill true}` on
    both (client first) writes the cap back to A's bring-up TU and refills
    TU to it. Staging asserts: A's TU after the refill (= the cap) equal on
    both and at least A_TURN_TU, the turn's cost. One client `battle_intent
    turn` for A to A's facing + A_TURN_OCTANTS. Checks: the host admits it
    (a mind-controlled unit is commanded by its controller's seat; a host
    deny `not_your_unit` shows as the client's lastDeny for the order's
    iseq); host closedContexts gains exactly one {origin intent, kind turn,
    actorId A}; A's facing changed and equal on both.

The order puts mind_probe_use before psi_panic_and_control: the mind control
makes A a player unit, and the mind probe refuses a target of the prober's
own faction (primaryAction's BT_MINDPROBE branch). mind_probe_use's FOV
staging (C facing A, A spotted) is the one psi_panic_and_control needs, so
psi_panic_and_control keeps C and A where they stand (a unit is never
teleported onto its own tile, it keeps the facing its last turn produced) and
re-faces C only when mind_probe_use did not leave C facing A. The client
UnitInfoState that mind_probe_use opens is closed with the client's cancel
key before psi_panic_and_control. A hand click while the client targets only
cancels the targeting.

Common asserts (after the order settles): hash_now {full:true} - every
bucket EQUAL; desyncSeen false on both; client coopClientBStatePushes
unchanged and host 0; the delta counters that must stay 0 on both; every
staged item created on both machines with equal ids (both()). For an
admitted order: host closedContexts gains exactly one {origin intent, kind K,
actorId C}; every host ev of that actionId is in the client's log with the
same seq, kind and actionId; exactly one bt_action_end; client
coopIntentsSent[wire kind] +1; client inFlight null at the end; client
intentTimeouts unchanged (no STR_COOP_ACTION_TIMEOUT).

psi_messages (checked inside psi_panic_and_control): the success message of
the second player's psi attack is about the attacker C, the HOST's partner's
soldier. Panic leg: the host's event_state `messages` ring +1 {C,
STR_MORALE_ATTACK_SUCCESSFUL, partner, notice} and no host infobox (box_p ==
[]); the client's ring +1 {C, same key, own, box, queued Q_PANIC}.
Mind-control leg: the same with STR_MIND_CONTROL_SUCCESSFUL, queued
Q_MIND_CONTROL, box_m == []. After each leg's collect, one bounded wait
(test_messages.client_quiet: the client's message queue empty and
BattlescapeState on top within BOX_WAIT_S) so the client's own 2 s box never
eats the mind-control leg's first hand click or controlled_alien_turn's
input; it is recorded in EVIDENCE, and a timeout fails the row.

melee_ghost and psi_ghost: the watching machine plays the melee and psi
display. melee_ghost (stun_rod_hit): ONE client combatGhost record of kind
melee for the `melee` ev's seq with the rule chain's frame, frames,
intervalMs, ms, sound and soundEnd (test_host_combat.impact_row /
impact_expect, the pins in EFFECT_PINS). psi_ghost (psi_panic_and_control,
both legs): ONE record of kind psi per `psi` ev with the psi chain's frame,
frames, intervalMs, ms and sound, and `voxel` equal to the payload's additive
`voxel`. Both add the common effect-row asserts (client rngSeed unchanged
across the row, host displayTwo / combatGhost all zero, completed + cut ==
enqueued per record kind). mind_probe_use: the client's rngSeed is unchanged
across the mind probe - the aftermath's hit sound must come from the raw
list, never RuleItem::getHitSound(). coopGhostStepper is pinned true in both
instances.

host_view_kept: the second player's melee and psi never move the host's view
level (ExplosionBState's hit branch). Before each order (stun_rod_hit and
both psi_panic_and_control legs) the host camera is staged on
K_HOSTFAR_TERROR (view level 1). Checks per order: host
camera.suppressed.hitLevel +1 and the host view level still 1. One
"EVIDENCE host_view_kept <order>:" line per order.

hit_log_weapon: the hit log after each of the second player's own orders,
both machines in English. After stun_rod_hit (stun rod), each
psi_panic_and_control leg (psi amp) and mind_probe_use (mind probe): the
client's hitLog.text == the host's, and the host's text starts with the
English weapon name (test_hit_log WEAPONS_EN) - the weapon line the host logs
at the order's executor, which the client's own local line gives way to. One
"EVIDENCE hit_log_weapon <order>:" line per order.

Probes: event_state's coopIntentsSent, intentsReceived, lastActionHalt and
lastAftermath (the boot checks they exist). The cue payloads are read from
the HOST's own openxcom.log `[coop-cue]` lines.

FIXTURE (the roster-pinned terror boot of test_host_combat.py): set_seed
SEED_ROSTER on the HOST right before its open_new_battle, mission
STR_TERROR_MISSION, set_seed SEED_MAP right before newbattle_ok, seat_count
2, MAP_FP asserted on both, the seated unit ids asserted (SEATED),
pin_ai_neutral. Every staging pair goes to the CLIENT first. Item ids are
read at run time from the staging replies or by unitLink, never baked. The
seeds were found with HOST stand-ins that run the executor's states for C
(SEED_STUN: battle_fire {mode melee}; SEED_PANIC / SEED_MIND_CONTROL:
battle_action psi_attack).

Each scenario prints ONE "EVIDENCE <id>:" line with both machines' fields
BEFORE its conditions are checked; main() runs every scenario even after an
earlier one failed and prints "PASS <id>" / "FAIL <id>: <message>". Every
wait is bounded; a wait that times out is recorded in the EVIDENCE line and
fails the scenario.

One run is the result: no skip path, no second boot, no alternative map or
actor. Exit 0 only when all four scenarios pass, 2 otherwise (a bring-up
failure is also 2).

Run:  python tools/coop_test/test_client_melee_psi.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_delta_core import diff_buckets, short, both
from test_delta_items import unit_view, tile_of
from test_host_combat import bring_up_lobby_roster_pinned, ev_tuples, effect_snap, impact_row, rng_of
from test_client_shoot import (top, snap, ubrief, press, units, place, set_tu_both, await_press, order_done,
                                  collect, ctx_view, chain_of, forwarded_fails, tu_fails, common_fails, finish,
                                  press_view, ui_view, send_intent, TU_MAX, C_TU_FULL, POLL_S, SENT_WAIT_S,
                                  ORDER_TIMEOUT_S)
from test_client_grenade import (admitted_fails, cancel_client_targeting, open_hand_menu, target_order, settle,
                                    host_payloads_of)
from test_messages import msg_snap, msg_delta, msg_rows_fails, msg_evidence, want, client_quiet
from test_host_combat import cam_snap, cam_offset, stage_camera, cam_suppressed_delta, cam_view, K_HOSTFAR_TERROR
from test_hit_log import hl_snap, hl_view, first_line, WEAPONS_EN

# ----- bring-up (the roster-pinned terror boot) -----
MISSION = "STR_TERROR_MISSION"
SEED_MAP = 1
MAP_FP = -3.451266327757785e+18   # host battle_state.mapFingerprint on SEED_MAP 1 (the same on every boot)
SEATED = [8, 9]                   # the client's seated units: C and C2
C_ID = 8
H_ID = 10                         # first host-seat soldier
A_ID, A2_ID = 1000000, 1000001    # Sectoid Soldiers
PORT = "48713"
COOP_SEAT_0 = 0
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
STATUS_UNCONSCIOUS = 7            # src/Mod/Unit.h enum UnitStatus

# ----- stun_rod_hit (SEED_STUN 1 gave this outcome on 3 of 3 boots) -----
STUN_C_TILE, STUN_C_DIR = (24, 24, 0), 0      # C faces north
STUN_A2_TILE, STUN_A2_DIR = (24, 23, 0), 4    # the tile C faces; A2 faces C
STUN_A2_HEALTH = 5
SEED_STUN = 1                     # A2 UNCONSCIOUS (stun 120), one body item on (24,23,0)
STUN_ROD = "STR_STUN_ROD"
STUN_TU = 19                      # the rod's BA_HIT cost for C (max TU 64), measured with the stand-in
STUN_TU_AFTER = C_TU_FULL - STUN_TU           # 45: a melee turns nobody (no UnitTurnBState)
STUN_ROWS = 2                     # THROW + STUN
STUN_CHAIN = ["melee", "death", "corpse", "bt_action_end"]
TEXT_ITEM_ACTION = "Only the host can use this item"   # STR_COOP_ITEM_ACTION_HOST_ONLY (a refusal banner)

# ----- mind_probe_use (the cost measured with the battle_fire {mode use} stand-in) -----
FOV_C_TILE, FOV_C_DIR0 = (12, 26, 0), 2       # C teleported facing east, then a client `turn` toward A
FOV_TURN_TO, FOV_C_DIR = 0, 1                 # the turn to dir 0 halts at dir 1 on spotting A
A_TILE, A_DIR = (12, 23, 0), 4
MIND_PROBE = "STR_MIND_PROBE"
PROBE_TU = 32                     # 50 % of C's max TU 64
PROBE_TU_AFTER = C_TU_FULL - PROBE_TU
PROBE_ROWS = 2                    # THROW + USE MIND PROBE
PROBE_CHAIN = ["bt_action_end"]   # an instant kind: no cue, the one end

# ----- psi_panic_and_control (SEED_PANIC / SEED_MIND_CONTROL each gave their outcome on 3 of 3 boots) -----
PSI_AMP = "STR_PSI_AMP"
C_PSI_SKILL = 100                 # C's natural psiSkill is 4
A_PSI_STRENGTH = 0
SEED_PANIC = 1
SEED_MIND_CONTROL = 1
PSI_TU = 25                       # the amp's panic / mind-control cost (flat)
PSI_TU_AFTER = C_TU_FULL - PSI_TU             # 39
PANIC_A_MORALE = 70               # A morale 100 -> 70 after the panic
PSI_ROWS = 3                      # THROW + MIND CONTROL + PANIC
PSI_CHAIN = ["psi", "bt_action_end"]
# psi_messages: the success message keys, and whether the client queued each leg's box (its `seen` record)
KEY_MORALE_ATTACK = "STR_MORALE_ATTACK_SUCCESSFUL"
KEY_MIND_CONTROL = "STR_MIND_CONTROL_SUCCESSFUL"   # STR_PSI_AMP does not convertToCivilian (not the _ALT key)
Q_PANIC = False                   # PIN: the panic leg's `psi` applied with BattlescapeState on top (not queued)
Q_MIND_CONTROL = False
BOX_WAIT_S = 5                    # the client's own 2 s success box closes by itself before the next input

# ----- controlled_alien_turn (the order for A after the mind control) -----
A_TURN_OCTANTS = 2                # the order: A's facing + 2 octants
A_TU_CAP = 54                     # A's TU at bring-up (this file's boot line, before the mind control)
A_TURN_TU = 2                     # 2 octants x armor turnCost 1 (Armor.cpp default; no xcom1 / common ruleset sets it)

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
    top (the UnitInfoState mind_probe_use opens). Returns [top before(, after)]."""
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


# ===================== staging (client first) =====================


def give(host, client, item):
    return both(host, client, {"cmd": "battle_give", "unit": C_ID, "item": item, "clear_hands": True},
                ("weaponId", "ammoId"))["weaponId"]


def set_stat_both(host, client, uid, stat, value):
    return both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": stat,
                               "value": value}, ("tu",))


def fov_stage(host, client, notes):
    """C on FOV_C_TILE facing A with A spotted on both: C and A are
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
    host.ok({"cmd": "set_seed", "seed": SEED_STUN})
    press(client, KEY_STUN)
    client.wait_for("client left the action menu", lambda: top(client) != "ActionMenuState" or None, timeout=5)
    ev["topAfterKey"] = top(client)


def await_order(host, client, before, notes, box):
    """await_press, plus the host's psi infobox: a host InfoboxState that comes
    up while the order runs (the chain runs under it) is recorded into `box`
    and dismissed host-only. Returns {state, t, tEnd}."""
    t0 = time.time()
    state = "quiet"
    while time.time() - t0 < SENT_WAIT_S:
        ec, eh = event_state(client), event_state(host)
        if (ec.get("inFlight") or ec.get("coopIntentsSent") != before["client"]["coopIntentsSent"]
                or eh.get("lastSeqEmitted") != before["host"]["lastSeqEmitted"]):
            state = "sent"
            break
        if ec.get("coopLocalExecBlocked") != before["client"]["coopLocalExecBlocked"]:
            state = "refusedLocally"
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


def hit_log_fails(what, s, weapon):
    """Row hit_log_weapon: after one of the second player's own orders (the host runs it at the order's
    executor), both machines in English: the client's hitLog.text == the host's and the host's text starts with the
    English weapon name (the partner's weapon line the host logs, its first line). `s` = hl_snap() after the order
    settled. Prints one "EVIDENCE hit_log_weapon <what>:" line."""
    want = WEAPONS_EN[weapon]
    print(f"EVIDENCE hit_log_weapon {what}: weapon {weapon} -> {want!r}; {hl_view(s)}", flush=True)
    hl, cl = s["host"]["log"], s["client"]["log"]
    fails = []
    if first_line(hl.get("text")) != want:
        fails.append(f"hit_log_weapon {what}: the host's hitLog first line {first_line(hl.get('text'))!r} "
                     f"(text {hl.get('text')!r}; want {want!r}: the partner's weapon line)")
    if cl.get("text") != hl.get("text"):
        fails.append(f"hit_log_weapon {what}: client hitLog text {cl.get('text')!r} != host {hl.get('text')!r} "
                     f"(want the host's log mirrored)")
    return fails


def host_view_fails(what, staged, cam0, cam1):
    """Row host_view_kept: one order of the second player's melee / psi. The host's camera.suppressed.hitLevel +1
    and its view level still the staged 1. Prints one "EVIDENCE host_view_kept <what>:" line."""
    sup = cam_suppressed_delta(cam0["host"], cam1["host"])
    print(f"EVIDENCE host_view_kept {what}: host staged={cam_offset(staged)} before={cam_view(cam0['host'])} after="
          f"{cam_view(cam1['host'])} suppressed delta={sup}", flush=True)
    fails = []
    if sup["hitLevel"] != 1:
        fails.append(f"host_view_kept {what}: host camera.suppressed.hitLevel +{sup['hitLevel']} "
                     f"(want +1: the partner's order)")
    if cam1["host"].get("viewLevel") != K_HOSTFAR_TERROR[2]:
        fails.append(f"host_view_kept {what}: host view level {cam1['host'].get('viewLevel')} after the order "
                     f"(want the staged {K_HOSTFAR_TERROR[2]}: the partner's melee / psi never moves the host's view "
                     f"level)")
    return fails


# ===================== scenarios =====================


def stun_rod_hit(host, client, ctx):
    notes = []
    rod = give(host, client, STUN_ROD)
    pc_ = place(host, client, C_ID, STUN_C_TILE, STUN_C_DIR)
    pa_ = place(host, client, A2_ID, STUN_A2_TILE, STUN_A2_DIR)
    both(host, client, {"cmd": "battle_set_unit_state", "unit": A2_ID, "health": STUN_A2_HEALTH},
         ("health", "stun", "status"))
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    cam_staged = stage_camera(host, K_HOSTFAR_TERROR)   # for host_view_kept: the host at view level 1
    cam0 = cam_snap(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    snap_e = effect_snap(host, client)   # for melee_ghost
    pv = {}
    try:
        stun_order(host, client, pv)
    except Exception as e:
        notes.append(f"real-UI stun: {short(e)}")
    out = await_press(host, client, before, notes)
    settle(host, client, notes)
    view_fails = host_view_fails("stun_rod_hit", cam_staged, cam0, cam_snap(host, client))
    rec = collect(host, client, seq0)
    hit_log_stun = hl_snap(host, client)   # for hit_log_weapon
    new = ctx_view(before, rec)
    hits = [c for c in new if c.get("origin") == "intent" and c.get("kind") == "melee" and c.get("actorId") == C_ID]
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    bodies = {n: [i for i in its.values() if i.get("unitLink") == A2_ID]
              for n, its in (("host", rec["ih"]), ("client", rec["ic"]))}
    print(f"EVIDENCE stun_rod_hit: staged rod={rod} C={pc_} A2={pa_} stagedDiff={staged} press={pv} outcome={out}; "
          f"{press_view(before, rec)}; ui={ui_view(before, rec)}; newContexts={new}; action={aid} "
          f"chain={[(e['seq'], e['kind']) for e in chain]}; host evs={ev_tuples(rec['hev'])} "
          f"client evs={ev_tuples(rec['cev'])}; A2 host={a_view(rec['uh'].get(A2_ID))} "
          f"client={a_view(rec['uc'].get(A2_ID))}; C host={ubrief(rec['uh'].get(C_ID))} "
          f"client={ubrief(rec['uc'].get(C_ID))}; bodies={bodies}; diff={rec['diff']} desync={rec['dsc']}; "
          f"notes={notes}", flush=True)
    # melee_ghost: C's own stun-rod swing as a melee ghost on the client
    melee_ghost_fails = impact_row("melee_ghost", host, client, snap_e,
                                   [(next((e["seq"] for e in chain if e["kind"] == "melee"), None), "melee")], STUN_ROD)
    log_fails = hit_log_fails("stun_rod_hit", hit_log_stun, STUN_ROD)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if pv.get("rows") != STUN_ROWS:
        fails.append(f"precondition: client menu rows {pv.get('rows')} (want {STUN_ROWS})")
    fails += forwarded_fails(before, rec)
    f, cx = admitted_fails(before, rec, "melee", "melee", C_ID)
    fails += f
    kinds = [e["kind"] for e in chain]
    if cx and kinds != STUN_CHAIN:
        fails.append(f"host evs of actionId {aid} = {kinds} (want exactly {STUN_CHAIN})")
    if cx:
        fails += cue_fails(host, chain, "melee", {"actor": C_ID, "unit": A2_ID, "success": True}, "stun_rod_hit")
    sh, sc = rec["uh"].get(A2_ID) or {}, rec["uc"].get(A2_ID) or {}
    for n, u in (("host", sh), ("client", sc)):
        if u.get("status") != STATUS_UNCONSCIOUS:
            fails.append(f"{n} A2 {a_view(u)} (want status UNCONSCIOUS ({STATUS_UNCONSCIOUS}))")
    if sh.get("stun") is None or sh.get("stun") != sc.get("stun"):
        fails.append(f"A2 stun host={sh.get('stun')} client={sc.get('stun')} (want equal)")
    hb, cb = bodies["host"], bodies["client"]
    if len(hb) != 1 or len(cb) != 1 or hb[0] != cb[0] or tile_of(hb[0]) is None:
        fails.append(f"body items of A2 host={hb} client={cb} (want exactly one, equal on both, on a tile)")
    fails += tu_fails(rec, C_ID, STUN_TU_AFTER)
    fails += aftermath_fails(rec, aid, "melee", "stun_rod_hit")
    if rec["clientUi"]["banner"] == TEXT_ITEM_ACTION:
        fails.append(f"client banner {rec['clientUi']['banner']!r} (the host-only refusal: want the press "
                     f"sent as an order)")
    fails += melee_ghost_fails
    fails += view_fails
    fails += log_fails
    fails += common_fails(host, client, before, "stun_rod_hit")
    finish(fails)


def mind_probe_use(host, client, ctx):
    notes = []
    aim0 = cancel_client_targeting(client)
    probe = give(host, client, MIND_PROBE)
    set_tu_both(host, client, C_ID, TU_MAX)
    fv = fov_stage(host, client, notes)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    rng0 = rng_of(client)   # the mind-probe rngSeed guard
    pv = {}
    try:
        target_order(client, pv, KEY_PROBE, CURSOR_PSI, A_TILE)
    except Exception as e:
        notes.append(f"real-UI mind probe: {short(e)}")
    out = await_press(host, client, before, notes)
    settle(host, client, notes)
    rec = collect(host, client, seq0)
    rng1 = rng_of(client)
    hit_log_probe = hl_snap(host, client)   # for hit_log_weapon
    tops = {"host": top(host), "client": top(client)}
    new = ctx_view(before, rec)
    hits = [c for c in new if c.get("origin") == "intent" and c.get("kind") == "mindprobe"
            and c.get("actorId") == C_ID]
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    print(f"EVIDENCE mind_probe_use: staged probe={probe} aimCancel={aim0} fov={fv} stagedDiff={staged} press={pv} "
          f"outcome={out}; {press_view(before, rec)}; ui={ui_view(before, rec)}; top={tops}; newContexts={new}; "
          f"action={aid} chain={[(e['seq'], e['kind']) for e in chain]}; host evs={ev_tuples(rec['hev'])} "
          f"client evs={ev_tuples(rec['cev'])}; C host={ubrief(rec['uh'].get(C_ID))} "
          f"client={ubrief(rec['uc'].get(C_ID))}; A host={a_view(rec['uh'].get(A_ID))} "
          f"client={a_view(rec['uc'].get(A_ID))}; diff={rec['diff']} desync={rec['dsc']}; client rngSeed {rng0} -> "
          f"{rng1}; notes={notes}", flush=True)
    log_fails = hit_log_fails("mind_probe_use", hit_log_probe, MIND_PROBE)
    fails = list(notes)
    # The client's own mind-probe aftermath plays the probe's hit sound; it must never draw the sim RNG.
    # RuleItem::getHitSound() would draw one xorshift step; the client picks from the raw list with RNG::seedless.
    if rng0 is None or rng1 != rng0:
        fails.append(f"client rngSeed {rng0} -> {rng1} across the mind probe (want unchanged: the aftermath's hit "
                     f"sound from the raw list, never RuleItem::getHitSound())")
    fails += fov_fails(fv)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if pv.get("rows") != PROBE_ROWS:
        fails.append(f"precondition: client menu rows {pv.get('rows')} (want {PROBE_ROWS})")
    fails += forwarded_fails(before, rec)
    f, cx = admitted_fails(before, rec, "mindprobe", "use_item", C_ID)
    fails += f
    kinds = [e["kind"] for e in chain]
    if cx and kinds != PROBE_CHAIN:
        fails.append(f"host evs of actionId {aid} = {kinds} (want exactly {PROBE_CHAIN})")
    fails += tu_fails(rec, C_ID, PROBE_TU_AFTER)
    if tops["client"] != "UnitInfoState":
        fails.append(f"client top state {tops['client']} (want UnitInfoState, opened at the order's own end)")
    if tops["host"] == "UnitInfoState":
        fails.append("host top state UnitInfoState (want none on the host: the screen is the ordering player's)")
    fails += aftermath_fails(rec, aid, None, "mind_probe_use")
    fails += log_fails
    fails += common_fails(host, client, before, "mind_probe_use")
    finish(fails)


def psi_leg(host, client, key, seed, action, notes, box):
    """One psi_panic_and_control leg: C TU max (both), the real-UI psi order at A with the host's
    set_seed right before the click, the bounded wait (the host infobox
    recorded and dismissed host-only). Returns (before, rec, pv, out)."""
    set_tu_both(host, client, C_ID, TU_MAX)
    cam_staged = stage_camera(host, K_HOSTFAR_TERROR)   # for host_view_kept: the host at view level 1
    cam0 = cam_snap(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    mb = msg_snap(host, client)          # for psi_messages
    pv = {}
    try:
        target_order(client, pv, key, CURSOR_PSI, A_TILE, lambda: host.ok({"cmd": "set_seed", "seed": seed}))
    except Exception as e:
        notes.append(f"real-UI {action}: {short(e)}")
    out = await_order(host, client, before, notes, box)
    settle(host, client, notes)
    dismiss_host_infobox(host, box)
    cam_after = cam_snap(host, client)
    rec = collect(host, client, seq0)
    rec["camStage"] = (cam_staged, cam0, cam_after)   # for host_view_kept
    rec["hl"] = hl_snap(host, client)                 # for hit_log_weapon
    # the client's own success box closed before the next leg / controlled_alien_turn
    rec["boxWait"] = client_quiet(client, timeout=BOX_WAIT_S)
    rec["msg"] = (mb, msg_snap(host, client), seq0)
    return before, rec, pv, out


def psi_leg_fails(host, before, rec, pv, action, what):
    fails = []
    if pv.get("rows") != PSI_ROWS:
        fails.append(f"{what}: precondition: client menu rows {pv.get('rows')} (want {PSI_ROWS})")
    fails += [f"{what}: {m}" for m in forwarded_fails(before, rec)]
    f, cx = admitted_fails(before, rec, "psi", "psi", C_ID)
    fails += [f"{what}: {m}" for m in f]
    aid = cx.get("actionId") if cx else None
    chain = chain_of(rec, aid)
    kinds = [e["kind"] for e in chain]
    if cx and kinds != PSI_CHAIN:
        fails.append(f"{what}: host evs of actionId {aid} = {kinds} (want exactly {PSI_CHAIN})")
    if cx:
        fails += cue_fails(host, chain, "psi", {"action": action, "actor": C_ID, "unit": A_ID, "success": True}, what)
    fails += [f"{what}: {m}" for m in tu_fails(rec, C_ID, PSI_TU_AFTER)]
    fails += aftermath_fails(rec, aid, "psi", what)
    return fails, aid


def psi_message_fails(rec, box, key, queued, what):
    """Row psi_messages: the success message of the client's own psi attack - a notice on the host (box == []: no
    host infobox), vanilla's 2 s box on the client; psi_leg's bounded wait closed it. Prints the leg's EVIDENCE
    line."""
    mb, ma, seq0 = rec["msg"]
    d = msg_delta(mb, ma)
    print(f"EVIDENCE psi_panic_and_control psi_messages {what}: messages={msg_evidence(mb, ma, seq0)}; "
          f"hostInfobox={box}; client box wait={rec.get('boxWait')}", flush=True)
    fails = msg_rows_fails(f"psi_panic_and_control psi_messages {what}", "host", d["host"],
                           [want(C_ID, key, "partner", "notice")])
    fails += msg_rows_fails(f"psi_panic_and_control psi_messages {what}", "client", d["client"],
                            [want(C_ID, key, "own", "box", queued=queued)])
    if box:
        fails.append(f"psi_panic_and_control psi_messages {what}: the host showed infoboxes {box} (want none: a "
                     f"message about the partner's soldier never pauses the host)")
    if not (rec.get("boxWait") or {}).get("ok"):
        fails.append(f"psi_panic_and_control psi_messages {what}: the client's message queue / top after the leg "
                     f"{rec.get('boxWait')} (want empty and BattlescapeState within {BOX_WAIT_S} s)")
    return fails


def psi_panic_and_control(host, client, ctx):
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
    snap_e = effect_snap(host, client)   # for psi_ghost (both legs)
    # ---- the panic leg (key 50) ----
    box_p = []
    before, rec, pv, out = psi_leg(host, client, KEY_PANIC, SEED_PANIC, "panic", notes, box_p)
    new = ctx_view(before, rec)
    # the panic leg's end state, before the mind-control leg
    common_p = common_fails(host, client, before, "psi_panic_and_control panic leg")
    # ---- the mind-control leg (key 51) ----
    notes_m = []
    box_m = []
    before_m, rec_m, pv_m, out_m = psi_leg(host, client, KEY_MC, SEED_MIND_CONTROL, "mc", notes_m, box_m)
    new_m = ctx_view(before_m, rec_m)
    common_m = common_fails(host, client, before_m, "psi_panic_and_control mind-control leg")
    fp, aid_p = psi_leg_fails(host, before, rec, pv, "panic", "panic leg")
    fm, aid_m = psi_leg_fails(host, before_m, rec_m, pv_m, "mc", "mind-control leg")
    print(f"EVIDENCE psi_panic_and_control: staged amp={amp} popupClose={popup0} aimCancel={aim0} fov={fv} "
          f"stats={stats} stagedDiff={staged} A before host={a0['host']} client={a0['client']} | "
          f"PANIC LEG press={pv} outcome={out}; {press_view(before, rec)}; ui={ui_view(before, rec)}; "
          f"hostInfobox={box_p}; "
          f"newContexts={new}; action={aid_p} chain={[(e['seq'], e['kind']) for e in chain_of(rec, aid_p)]}; "
          f"host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; A host={a_view(rec['uh'].get(A_ID))} "
          f"client={a_view(rec['uc'].get(A_ID))}; C host={ubrief(rec['uh'].get(C_ID))} "
          f"client={ubrief(rec['uc'].get(C_ID))}; diff={rec['diff']} desync={rec['dsc']}; notes={notes} | "
          f"MIND-CONTROL LEG press={pv_m} outcome={out_m}; {press_view(before_m, rec_m)}; "
          f"ui={ui_view(before_m, rec_m)}; "
          f"hostInfobox={box_m}; newContexts={new_m}; action={aid_m} "
          f"chain={[(e['seq'], e['kind']) for e in chain_of(rec_m, aid_m)]}; host evs={ev_tuples(rec_m['hev'])} "
          f"client evs={ev_tuples(rec_m['cev'])}; A host={a_view(rec_m['uh'].get(A_ID))} "
          f"client={a_view(rec_m['uc'].get(A_ID))}; C host={ubrief(rec_m['uh'].get(C_ID))} "
          f"client={ubrief(rec_m['uc'].get(C_ID))}; diff={rec_m['diff']} desync={rec_m['dsc']}; notes={notes_m}",
          flush=True)
    # psi_ghost: each leg's `psi` cue as a psi ghost on the client
    psi_seqs = [next((e["seq"] for e in chain_of(r_, a_) if e["kind"] == "psi"), None)
                for r_, a_ in ((rec, aid_p), (rec_m, aid_m))]
    psi_ghost_fails = impact_row("psi_ghost", host, client, snap_e, [(s, "psi") for s in psi_seqs], PSI_AMP)
    # psi_messages (both legs)
    msg_fails = (psi_message_fails(rec, box_p, KEY_MORALE_ATTACK, Q_PANIC, "panic leg")
                 + psi_message_fails(rec_m, box_m, KEY_MIND_CONTROL, Q_MIND_CONTROL, "mind-control leg"))
    # host_view_kept (both legs)
    view_fails = (host_view_fails("psi_panic_and_control panic leg", *rec["camStage"])
                  + host_view_fails("psi_panic_and_control mind-control leg", *rec_m["camStage"]))
    # hit_log_weapon (both legs)
    log_fails = (hit_log_fails("psi_panic_and_control panic leg", rec["hl"], PSI_AMP)
                 + hit_log_fails("psi_panic_and_control mind-control leg", rec_m["hl"], PSI_AMP))
    fails = list(notes) + list(notes_m)
    fails += fov_fails(fv)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    # the panic leg
    fails += fp
    ah, ac = rec["uh"].get(A_ID) or {}, rec["uc"].get(A_ID) or {}
    got = ((ah.get("morale"), ah.get("faction")), (ac.get("morale"), ac.get("faction")))
    if got != ((PANIC_A_MORALE, FACTION_HOSTILE), (PANIC_A_MORALE, FACTION_HOSTILE)):
        fails.append(f"panic leg: A (morale, faction) host={got[0]} client={got[1]} (want ({PANIC_A_MORALE}, "
                     f"{FACTION_HOSTILE}) on both)")
    fails += [f"panic leg: {m}" for m in common_p]
    # the mind-control leg (a successful panic already sets mindControllerId, so the faction is the proof)
    fails += fm
    ah, ac = rec_m["uh"].get(A_ID) or {}, rec_m["uc"].get(A_ID) or {}
    got = ((ah.get("faction"), ah.get("mindControllerId")), (ac.get("faction"), ac.get("mindControllerId")))
    if got != ((FACTION_PLAYER, C_ID), (FACTION_PLAYER, C_ID)):
        fails.append(f"mind-control leg: A (faction, mindControllerId) host={got[0]} client={got[1]} (want "
                     f"({FACTION_PLAYER}, {C_ID}) on both)")
    fails += [f"mind-control leg: {m}" for m in common_m]
    fails += psi_ghost_fails
    fails += msg_fails
    fails += view_fails
    fails += log_fails
    finish(fails)


def controlled_alien_turn(host, client, ctx):
    notes = []
    a0 = {"host": a_view(units(host).get(A_ID)), "client": a_view(units(client).get(A_ID))}
    mc = all((a0[n] or {}).get("faction") == FACTION_PLAYER and (a0[n] or {}).get("mindControllerId") == C_ID
             for n in ("host", "client"))
    staged = None
    req = None
    si = {}
    d0 = None
    tu = {}
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    if mc:
        try:
            # the TU cap is getBaseStats()->tu (= _stats, the clamp of setTimeUnits); set_stat writes it and
            # `refill` writes TU = the cap, so the reply's `tu` is the cap on each machine (both(): equal on both).
            tu["staged"] = both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu",
                                               "value": A_TU_CAP, "refill": True}, ("tu",)).get("tu")
            tu["now"] = (units(host)[A_ID].get("tu"), units(client)[A_ID].get("tu"))
            staged = diff_buckets(host, client)
            d0 = units(client)[A_ID].get("direction")
            req = {"cmd": "battle_intent", "kind": "turn", "actor": A_ID, "toDir": (d0 + A_TURN_OCTANTS) % 8}
            before = snap(host, client)
            seq0 = before["host"]["lastSeqEmitted"] or 0
            si = send_intent(host, client, req, notes, timeout=ORDER_TIMEOUT_S)
        except Exception as e:
            notes.append(f"order: {short(e)}")
        settle(host, client, notes)
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    ah, ac = rec["uh"].get(A_ID) or {}, rec["uc"].get(A_ID) or {}
    print(f"EVIDENCE controlled_alien_turn: A before host={a0['host']} client={a0['client']} mindControlled={mc} "
          f"tuStaging={tu} stagedDiff={staged} request={req} "
          f"intent={ {k: si.get(k) for k in ('sent', 'iseq', 'answer')} } "
          f"lastDeny={rec['client']['lastDeny']} banner={rec['clientUi']['banner']!r}; {press_view(before, rec)}; "
          f"newContexts={new}; host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; "
          f"A host={a_view(ah)} client={a_view(ac)}; diff={rec['diff']} desync={rec['dsc']}; notes={notes}",
          flush=True)
    fails = list(notes)
    if not mc:
        fails.append(f"precondition: A host={a0['host']} client={a0['client']} (want faction {FACTION_PLAYER} and "
                     f"mindControllerId {C_ID} on both: psi_panic_and_control's mind control)")
        finish(fails)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    ts = tu.get("staged")
    if ts is None or ts < A_TURN_TU or tu.get("now") != (ts, ts):
        fails.append(f"precondition: A's TU staging {tu} (want the refilled TU = the cap equal on both and at least "
                     f"{A_TURN_TU}, the {A_TURN_OCTANTS}-octant turn's cost)")
    if not si.get("sent"):
        fails.append(f"battle_intent turn answered {si.get('resp')} (want sent: an iseq)")
    ld = rec["client"]["lastDeny"] or {}
    if si.get("iseq") and ld.get("iseq") == si.get("iseq"):
        fails.append(f"the host denied the order: client lastDeny {ld} (want admitted: a mind-controlled unit is "
                     f"commanded by its controller's seat)")
    f, _ = admitted_fails(before, rec, "turn", "turn", A_ID)
    fails += f
    if ah.get("direction") is None or ah.get("direction") != ac.get("direction") or ah.get("direction") == d0:
        fails.append(f"A direction host={ah.get('direction')} client={ac.get('direction')} (want equal on both and "
                     f"changed from {d0})")
    fails += common_fails(host, client, before, "controlled_alien_turn")
    finish(fails)


SCENARIOS = (("stun_rod_hit", stun_rod_hit), ("mind_probe_use", mind_probe_use),
             ("psi_panic_and_control", psi_panic_and_control), ("controlled_alien_turn", controlled_alien_turn))


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
    pinned = pin_ai_neutral(host, client, tag="client_melee_psi")
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
            f"{gc.name} event_state lacks the intent probes: coopIntentsSent={es.get('coopIntentsSent')!r} "
            f"intentsReceived={es.get('intentsReceived')!r}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[client_melee_psi] boot ok: {MISSION} MAP_FP={MAP_FP!r} turn={hs['turn']} seated={seated_uids} H={H_ID} "
          f"pinned={len(pinned)} C={ubrief(ub.get(C_ID))} A={ubrief(ub.get(A_ID))} A2={ubrief(ub.get(A2_ID))}",
          flush=True)
    return {}


def main():
    t0 = time.time()
    # coopGhostStepper pinned true in both instances (melee_ghost / psi_ghost need the client's melee / psi ghosts)
    host = GameClient("host", 49874, make_user_dir("client_melee_psi_host", options={"coopGhostStepper": True}))
    client = GameClient("client", 49875, make_user_dir("client_melee_psi_client",
                                                       options={"coopGhostStepper": True}))
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
                print(f"[client_melee_psi] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_client_melee_psi: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
