"""W2-P4 S-D - test_w2_client_items.py: the second player uses its own medi-kit,
motion scanner, reload key and reaction-fire hand buttons; the host checks and
runs every one of them (spec rewrite/prompts/w2p4_client_combat_intents.md
section (f) "test_w2_client_items.py (S-D)", sections (b)1-6, (b)9, as amended by
AMENDMENT C1 (PR-Q9: the battle_set_unit_state `fatalWounds` lever; PR-Q10: the
medi-kit target rule; PR-Q15: the one-click kit row C23b2), AMENDMENT C2 (F1132:
C23e strips C first), AMENDMENT C3 (the owner's D148: the medi-kit screen stays
open, the host's end carries `continue`; C3-Q13: C23b3; C3-Q14: C23b4; the
owner's D150: a press while an order is in flight is ignored) and AMENDMENT C4
(PR-Q18: the client-side baton check belongs to each intercept; F1171: an
item-kind refusal does not move coopLocalExecBlocked).

Before S-D the second player can do none of this. USE MEDI-KIT and USE SCANNER
are refused in the action menu (K8, ActionMenuState::handleAction) with "Only the
host can use this item": the medi-kit screen never opens. The reload key is
refused with "Only the host can reload" (K13) and the hand right-click with "Only
the host can change reaction fire settings" (K14). Each refusal leaves
coopLocalExecBlocked +0 (F1171) and sends nothing. After S-D each press becomes
an intent (wire kinds of spec (b)1: `medikit`, `use_item` for the scanner,
`reload`, `reaction_hands`). The host admits it with vanilla's own checks and
runs vanilla's own code under an `intent` action context (context kinds of spec
(b)3: `medikit`, `scanner`, `reload`, `reaction_hands`) that ends in one
bt_action_end; the ordering client runs vanilla's aftermath for its own action.
Nine scenarios, ONE boot (the Coop_Spray_Test mod on both machines), in this
order:

  C23b   medi-kit, the D148 press sequence. C and H stripped (both, once, at the
         file's start); C -> C_TILE facing east (H's tile), H -> H_TILE facing
         C; H's fatal wounds WOUNDS (the PR-Q9 lever, both); a medi-kit on C
         (lever, both, clear hands); C TU max (both). Client: TAB-select C, the
         right-hand box (2 rows: THROW, USE MEDI-KIT), key 49 (MedikitState
         opens, nothing sent), then 51 (heal), 50 (stimulant), 49 (painkiller),
         each awaited to the client's own bt_action_end, then the cancel key.
         RED: key 49 refused at K8 with "Only the host can use this item",
         MedikitState never opens, nothing sent. GREEN per press: {origin
         intent, kind medikit, actorId C} whose evs are exactly medikit ->
         bt_action_end; client coopIntentsSent.medikit +1; the `medikit` cue
         {actor C, unit H, item, action, bodypart} (heal on the wounded part,
         stimulant and painkiller on the torso, vanilla's own arguments);
         lastActionHalt {halted false, continue true} on both; the client's
         top state still MedikitState; its three MedikitTxt numbers equal the
         host's battle_items medikit charges; H wounds / health / stun /
         morale / energy and the charges as T0-18 measured, equal on both; C
         TU 54 / 44 / 34 on both; lastAftermath {actionId, kind medikit,
         continue true}. Cancel: the screen closes locally, nothing sent.
  C23b5  D150, a press while the order is in flight. A fresh medi-kit on C; H's
         wounds WOUNDS again; C TU max; the screen open (TAB, the right-hand
         box, key 49); host defer_intents {ms DEFER_MS, count 1}; key 51, and
         once the client shows the order in flight, key 51 again. RED: the
         screen never opens. GREEN: coopIntentsSent.medikit +1 only; host
         intentsReceived.medikit.admitted +1 only; the heal count 10 -> 9
         and one wound healed only; C TU 54; the screen still open after the
         answer.
  C23b6  TU short. C TU KIT_TU - 1 (client first, then host); the screen open;
         key 50. RED: the screen never opens. GREEN: the host denies `no_tu`
         (client lastDeny.reason), the client banner reads vanilla's "Not
         Enough Time Units!", the client's MedikitState closes, nothing
         executed (no context), the charges and H unchanged.
  C23b3  the consumable one-charge kit (the test mod's STR_MEDI_KIT_ONE_CHARGE,
         charges 0 / 1 / 0, full screen). H's wounds WOUNDS; the kit on C; C
         TU max; the screen open (numbers 0 / 0 / 1); key 51. RED: the screen
         never opens. GREEN: the medikit context and heal cue; the kit removed
         on both after the use (the host removes it right after the use, C3-Q12);
         the open screen shows 0 / 0 / 0 until closed; H one wound healed; C
         TU 54; the cancel key closes it with nothing sent and no crash.
  C23b2  the one-click kit (the mod's STR_MEDI_KIT_ONE_CLICK, medikitType heal).
         H's wounds WOUNDS; the kit on C; C TU max. Client: TAB, the right-hand
         box (2 rows), key 49. RED: refused at K8. GREEN: the order is sent at
         once and no MedikitState opens on the client; the medikit context and
         heal cue on the first wounded part; H one wound healed; the kit
         10 / 9 / 10; C TU 54.
  C23c   scanner. A motion scanner on C; C TU max. Client: TAB, the right-hand
         box (2 rows: THROW, USE SCANNER), key 49. RED: refused at K8. GREEN:
         {origin intent, kind scanner, actorId C} whose evs are exactly
         scanner -> bt_action_end; coopIntentsSent.use_item +1; the `scanner`
         cue {actor C, item}; C TU 48 on both; the client opens ScannerState
         at its own end, the host does not; lastAftermath actionId.
  C23e   reload (F1132: C stripped on both first). A rifle with no ammo and a
         rifle clip on STR_BELT (0,0) (levers, both); C's inventory exactly
         these two; C TU max. Client: TAB, the reload key (keyBattleReload).
         RED: refused at K13 with "Only the host can reload". GREEN: {origin
         intent, kind reload, actorId C} whose evs are exactly bt_action_end;
         coopIntentsSent.reload +1; the clip loaded in the rifle on both; C TU
         49 on both; lastAftermath {actionId, kind reload}.
  C23f   reaction-fire hands (D133). C's flags (offLeft, offRight, prefLeft,
         prefRight) (F, F, F, F) on both. Client: TAB, battle_ui_press
         hand_reaction right (the real handler, a right-button event), then
         the client's touch Ctrl on (set_touch_modifiers), hand_reaction left,
         touch Ctrl off. RED: refused at K14 with "Only the host can change
         reaction fire settings", flags unchanged. GREEN: each press one
         {origin intent, kind reaction_hands, actorId C} whose evs are exactly
         bt_action_end, coopIntentsSent.reaction_hands +1; flags (F, F, F, T)
         after the right press and (T, F, F, T) after the Ctrl left press, on
         both (vanilla's toggle, T0b / S-D.1's T0 on H); `synced` equal.
  C23b4  `continue: false` (C3 section 4: a real knockout, the C21 melee shape).
         A stun rod on C (lever, both); C on C_TILE facing H; H health 5 and
         no fatal wound (levers, both); C TU max. Client: TAB, the right-hand
         box, host set_seed SEED_KO, key 52 (STUN): C's own stun order (S-C's
         intent) knocks H out. The host's vanilla "has become unconscious"
         InfoboxOKState holds the order's chain (N7); it is recorded and
         closed host-only through its OK button (the message policy is W2-P6's,
         H10). Then H's stun is set to health + 1 (lever, both: still
         unconscious, one stimulant revives him), a medi-kit on C (lever,
         both), C onto H's tile (lever, both), C TU max. Client: TAB, the
         right-hand box, key 49 (MedikitState on the patient on C's tile), key
         50 (stimulant). RED: key 49 refused at K8. GREEN: the medikit context
         and stim cue; lastActionHalt continue false on both; the client's
         MedikitState closes on the answer; H revived (status STANDING, on a
         tile, the same position and stun on both); the body item gone on
         both; lastAftermath continue false.

C23f comes before C23b4 (H is knocked out there). C23e strips C; later rows hand
out their own items. The scanner's ScannerState (C23c green) is closed with the
client's cancel key before C23e.

Common asserts (spec (f), after the order settles): hash_now {full:true} -
every bucket EQUAL; desyncSeen false on both; client coopClientBStatePushes
unchanged and host 0; the W2-P2 delta must-be-0 counters on both; every lever
item created on both machines with equal ids (both()). For an admitted order:
host closedContexts gains exactly one {origin intent, kind K, actorId C}; every
host ev of that actionId is in the client's log with the same seq, kind and
actionId; exactly one bt_action_end; client coopIntentsSent[wire kind] +1;
client inFlight null at the end; client intentTimeouts unchanged (no
STR_COOP_ACTION_TIMEOUT).

Probes: S-D.1 adds battle_items `medikit` [painKiller, heal, stimulant] (BT_MEDIKIT
items), battle_state units `wounds` (6 ints, UnitBodyPart order), the
battle_set_unit_state `fatalWounds` lever and `continue` in lastActionHalt /
lastAftermath (null while an end carries none). The cue payloads are read from
the HOST's own openxcom.log `[coop-cue]` lines.

STAGING (TASK 0 T0-9 = T0b; T0-18 and the C23f Ctrl half measured on the S-D.1
build, 3 boots, the host's OWN MedikitState operated by a host soldier on H as
the rule stand-in, T0b's method): the roster-pinned terror boot of
test_w2_host_combat.py (set_seed SEED_ROSTER on the HOST right before its
open_new_battle, mission STR_TERROR_MISSION, set_seed SEED_MAP right before
newbattle_ok, seat_count 2, MAP_FP asserted on both, the seated unit ids
asserted, pin_ai_neutral), the mod active on both (MAP_FP unchanged with it).
Every lever pair goes to the CLIENT first (F607). Item ids are read at run time
from the lever replies (F1107), never baked.

RED-THEN-GREEN (spec (d) row S-D). Commit S-D.1 (this file, the probes, the
fatalWounds lever, the mod's one-charge kit) is run ONCE and every scenario must
FAIL with its RED evidence. Commit S-D.2 is run ONCE and every scenario must
PASS. Each scenario prints ONE "EVIDENCE <id>:" line with both machines' fields
BEFORE its green conditions are checked; main() runs every scenario even after an
earlier one failed and prints "PASS <id>" / "FAIL <id>: <message>". Every wait is
bounded; a wait that times out is recorded in the EVIDENCE line and fails the
scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all nine scenarios pass, 2 otherwise
(a bring-up failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_client_items.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_rw_turn_baton import RHAND_NTH, click_nth
from test_rw_seat_pacing import tab_select
from test_w2_delta_core import diff_buckets, short, both
from test_w2_delta_items import unit_view
from test_w2_host_combat import bring_up_lobby_roster_pinned, ev_tuples
from test_w2_client_shoot import (top, snap, ubrief, press, menu_rows, recv_of, place, set_tu_both,
                                  await_press, order_done, collect, ctx_view, chain_of, forwarded_fails, tu_fails,
                                  common_fails, finish, press_view, ui_view, TU_MAX, C_TU_FULL, POLL_S, SENT_WAIT_S,
                                  ORDER_TIMEOUT_S, RHAND_CENTRE)
from test_w2_client_grenade import (admitted_fails, cancel_client_targeting, settle, host_payloads_of, mod_log,
                                    wait_banner_not, MOD_DIR, MOD_ACTIVE_LINE)
from test_w2_thin_client_tripwire import read_reload_key, loaded_ammo

# ----- bring-up (TASK 0: the roster-pinned terror boot, the mod on both) -----
MISSION = "STR_TERROR_MISSION"
SEED_MAP = 1
MAP_FP = -3.451266327757785e+18   # host battle_state.mapFingerprint on SEED_MAP 1, unmodded and modded (F1164)
SEATED = [8, 9]                   # the client's seated units: C and C2
C_ID = 8
H_ID = 10                         # first host-seat soldier: the patient
A_ID, A2_ID = 1000000, 1000001    # Sectoid Soldiers (bring-up check only)
PORT = "48714"
COOP_SEAT_0 = 0
FACTION_PLAYER = 0
STATUS_STANDING, STATUS_UNCONSCIOUS = 0, 7   # src/Mod/Unit.h enum UnitStatus

# ----- C23b staging (T0-9 = T0b; T0-18 on the S-D.1 build, 3/3 boots) -----
C_TILE, C_DIR = (12, 26, 0), 2    # C faces east: H's tile
H_TILE, H_DIR = (13, 26, 0), 6    # H faces C
WOUNDS = [0, 0, 2, 0, 0, 0]       # fatalWounds lever: 2 on the right arm (UnitBodyPart 2)
WOUND_PART, TORSO = 2, 1          # MedikitView selects the first wounded part; stim / painkiller use the torso
WOUNDS_HEALED = [0, 0, 1, 0, 0, 0]
H_FIELDS = {"health": 37, "stun": 0, "morale": 100, "energy": 60}   # H at the staging: full health, max energy
MEDIKIT = "STR_MEDI_KIT"
ONE_CHARGE = "STR_MEDI_KIT_ONE_CHARGE"      # the test mod: consumable, 0 / 1 / 0, full screen (C3-Q13)
ONE_CLICK = "STR_MEDI_KIT_ONE_CLICK"        # the test mod: medikitType 1 (heal at once), 10 / 10 / 10
KIT_TU = 10                       # tuUse 10, flatRate (items.rul)
KIT_ROWS = 2                      # THROW + USE MEDI-KIT
# the three MedikitTxt numbers after centerAllSurfaces (T0-18: x 193 + 27): painkiller, stimulant, heal
MEDIKIT_TXT = {(220, 52, 33, 17): "pk", (220, 88, 33, 17): "stim", (220, 124, 33, 17): "heal"}
# per press: (key, cue action, cue bodypart, charges [painKiller, heal, stimulant] after, C TU after)
C23B_PRESSES = ((51, "heal", WOUND_PART, [10, 9, 10], C_TU_FULL - KIT_TU),
                (50, "stim", TORSO, [10, 9, 9], C_TU_FULL - 2 * KIT_TU),
                (49, "painkiller", TORSO, [9, 9, 9], C_TU_FULL - 3 * KIT_TU))
MEDIKIT_CHAIN = ["medikit", "bt_action_end"]

# ----- C23b5 (D150; T0-18: a 2000 ms deferral holds the client's slot 2.12 s, harness poll 50 ms) -----
DEFER_MS = 2000

# ----- C23b6 -----
TEXT_NO_TU = "Not Enough Time Units!"        # xcom1 STR_NOT_ENOUGH_TIME_UNITS (en-US), the `no_tu` deny's key

# ----- C23c (T0-9: cost 25 % of 64) -----
SCANNER = "STR_MOTION_SCANNER"
SCANNER_TU = 16
SCANNER_CHAIN = ["scanner", "bt_action_end"]

# ----- C23e (T0-9; F1132; reload cost measured on H: 15) -----
RELOAD_TU = 15
INSTANT_CHAIN = ["bt_action_end"]

# ----- C23f (T0b right half; S-D.1's T0 Ctrl half on H) -----
FLAG_KEYS = ("reactOffLeft", "reactOffRight", "reactPrefLeft", "reactPrefRight")
FLAGS_0 = (False, False, False, False)
FLAGS_RIGHT = (False, False, False, True)        # right press, no Ctrl: prefRight on
FLAGS_CTRL_LEFT = (True, False, False, True)     # then left press with Ctrl: offLeft on

# ----- C23b4 (C3 section 4; S-D.1's T0: 3/3 boots) -----
STUN_ROD = "STR_STUN_ROD"
KO_H_HEALTH = 5                   # the C21 shape: the stun rod always knocks a health-5 unit out
SEED_KO = 1                       # H stun 113 after the rod (3/3)
STUN_RECOVERY = 4                 # items.rul STR_MEDI_KIT stunRecovery: one stimulant
KO_STUN = KO_H_HEALTH + 1         # still unconscious (stun >= health); one stimulant -> stun 2 < health
REVIVED_STUN = KO_STUN - STUN_RECOVERY

# ----- UI -----
KEY_ITEM1, KEY_STUN = 49, 52      # keyBattleActionItem1 (USE MEDI-KIT / USE SCANNER), item4 (STUN)
KEY_PK, KEY_STIM, KEY_HEAL = 49, 50, 51     # MedikitState: SDLK_1 / SDLK_2 / SDLK_3 (MedikitState.cpp)
KEY_CANCEL = 27                   # Options::keyCancel: closes MedikitState / ScannerState
TEXT_ITEM_ACTION = "Only the host can use this item"                     # STR_COOP_ITEM_ACTION_HOST_ONLY (RED)
TEXT_RELOAD = "Only the host can reload"                                  # STR_COOP_RELOAD_HOST_ONLY (RED)
TEXT_REACTIONS = "Only the host can change reaction fire settings"        # STR_COOP_REACTIONS_HOST_ONLY (RED)
SCREEN_WAIT_S = 5


# ===================== small probes =====================


def hview(u):
    """The patient's fields the medi-kit writes, plus where it lies."""
    if not u:
        return None
    return {k: u.get(k) for k in ("status", "isOut", "onTile", "x", "y", "z", "health", "stun", "morale", "energy",
                                  "tu", "wounds")}


def items_of(gc):
    """battle_items with EVERY field (incl. S-D.1's `medikit`) by id."""
    r = gc.cmd({"cmd": "battle_items"})
    assert r.get("ok"), f"battle_items failed on {gc.name}: {r}"
    return {i["id"]: i for i in r["items"]}


def collect_all(host, client, seq0):
    """test_w2_client_shoot.collect, with the items read in full: its item view
    keeps a fixed field list that has no `medikit` charges."""
    rec = collect(host, client, seq0)
    rec["ih"], rec["ic"] = items_of(host), items_of(client)
    return rec


def charges(its, iid):
    return (its.get(iid) or {}).get("medikit")


def screen(gc):
    """The top state and its MedikitTxt numbers {pk, stim, heal} by rect (None
    unless MedikitState is on top), plus any rect not in MEDIKIT_TXT."""
    lw = gc.cmd({"cmd": "list_widgets"})
    st = (lw.get("state") or "").split("::")[-1]
    nums, odd = {}, []
    for w in lw.get("widgets", []):
        if "MedikitTxt" not in (w.get("type") or ""):
            continue
        r = (w.get("x"), w.get("y"), w.get("w"), w.get("h"))
        if r in MEDIKIT_TXT:
            nums[MEDIKIT_TXT[r]] = w.get("text")
        else:
            odd.append((r, w.get("text")))
    return {"state": st, "nums": nums if st == "MedikitState" else None, "odd": odd}


def nums_of(ch):
    """battle_items medikit [painKiller, heal, stimulant] as the screen shows it."""
    return {"pk": str(ch[0]), "stim": str(ch[2]), "heal": str(ch[1])} if ch else None


def flags(gc, uid):
    u = session.units_by_id(battle_state(gc)).get(uid) or {}
    return tuple(u.get(k) for k in FLAG_KEYS)


def halt_of(rec, name):
    h = rec[name]["lastActionHalt"] or {}
    return {k: h.get(k) for k in ("actionId", "halted", "continue")}


def watch(gc, done, timeout, seen):
    """Poll gc's top state (bounded) until done(top), recording each state."""
    t0 = time.time()
    while True:
        st = top(gc)
        if not seen or seen[-1] != st:
            seen.append(st)
        if done(st):
            return True
        if time.time() - t0 > timeout:
            return False
        time.sleep(POLL_S)


def cue_fails(host, chain, kind, want, what):
    pl = host_payloads_of(host, chain, kind)
    got = {k: (pl[0] if pl else {}).get(k) for k in want}
    if len(pl) != 1 or got != want:
        return [f"{what}: `{kind}` cue payload(s) {pl} (want exactly one with {want})"]
    return []


def chain_fails(rec, cx, want, what):
    aid = cx.get("actionId") if cx else None
    kinds = [e["kind"] for e in chain_of(rec, aid)]
    if cx and kinds != want:
        return [f"{what}: host evs of actionId {aid} = {kinds} (want exactly {want})"]
    return []


def aftermath_fails(rec, aid, kind, cont, what):
    la = rec["client"]["lastAftermath"] or {}
    want = {"actionId": aid, "kind": kind}
    if cont is not None:
        want["continue"] = cont
    got = {k: la.get(k) for k in want}
    if aid is None or got != want:
        return [f"{what}: client lastAftermath={rec['client']['lastAftermath']} (want {want})"]
    return []


def halt_fails(rec, aid, cont, what):
    fails = []
    want = {"actionId": aid, "halted": False, "continue": cont}
    for name in ("host", "client"):
        got = halt_of(rec, name)
        if aid is None or got != want:
            fails.append(f"{what}: {name} lastActionHalt={rec[name]['lastActionHalt']} (want {want})")
    return fails


def h_fails(rec, wounds, what, extra=None):
    """H equal on both, with `wounds` and the staging's health / stun / morale /
    energy (the medi-kit changes nothing else on a full-health patient)."""
    hh, hc = hview(rec["uh"].get(H_ID)), hview(rec["uc"].get(H_ID))
    want = dict(H_FIELDS, wounds=wounds, **(extra or {}))
    fails = []
    if hh != hc:
        fails.append(f"{what}: H host={hh} client={hc} (want equal)")
    got = {k: (hh or {}).get(k) for k in want}
    if got != want:
        fails.append(f"{what}: H host {got} (want {want})")
    return fails


def charge_fails(rec, iid, want, what):
    ch, cc = charges(rec["ih"], iid), charges(rec["ic"], iid)
    if ch != want or cc != want:
        return [f"{what}: kit {iid} charges host={ch} client={cc} (want {want} [painKiller, heal, stimulant] on both)"]
    return []


def nothing_sent_fails(before, after_host, after_client, what):
    """A local-only press: no order, no host emission, no answer."""
    fails = []
    if after_client["coopIntentsSent"] != before["client"]["coopIntentsSent"]:
        fails.append(f"{what}: client coopIntentsSent {before['client']['coopIntentsSent']}->"
                     f"{after_client['coopIntentsSent']} (want unchanged)")
    if after_host["lastSeqEmitted"] != before["host"]["lastSeqEmitted"]:
        fails.append(f"{what}: host lastSeqEmitted {before['host']['lastSeqEmitted']}->"
                     f"{after_host['lastSeqEmitted']} (want unchanged)")
    if after_client["inFlight"] is not None:
        fails.append(f"{what}: client inFlight {after_client['inFlight']} (want null)")
    if after_client["coopClientBStatePushes"] != before["client"]["coopClientBStatePushes"]:
        fails.append(f"{what}: client coopClientBStatePushes {before['client']['coopClientBStatePushes']}->"
                     f"{after_client['coopClientBStatePushes']} (want unchanged)")
    return fails


def snap_one(gc):
    es = event_state(gc)
    return {k: es.get(k) for k in ("coopIntentsSent", "lastSeqEmitted", "inFlight", "coopClientBStatePushes",
                                   "intentsReceived", "lastDeny")}


# ===================== staging (client first, F607) =====================


def give(host, client, item, clear=True, **extra):
    req = {"cmd": "battle_give", "unit": C_ID, "item": item, "clear_hands": clear}
    req.update(extra)
    return both(host, client, req, ("weaponId", "ammoId"))["weaponId"]


def wounds_both(host, client, uid, w):
    r = both(host, client, {"cmd": "battle_set_unit_state", "unit": uid, "fatalWounds": w},
             ("fatalWounds", "health", "stun", "status"))
    return r.get("fatalWounds")


def strip_both(host, client, uid):
    rc = client.cmd({"cmd": "battle_strip_unit", "unit": uid})
    rh = host.cmd({"cmd": "battle_strip_unit", "unit": uid})
    assert rh.get("ok") and rc.get("ok"), f"battle_strip_unit {uid}: host={rh} client={rc}"
    dh, dc = set(rh.get("deleted") or []), set(rc.get("deleted") or [])
    assert dh == dc, f"battle_strip_unit {uid} deleted sets differ (F882): host={sorted(dh)} client={sorted(dc)}"
    return sorted(dh)


def owned(its, uid):
    return sorted((i, v.get("type"), v.get("slot")) for i, v in its.items() if v.get("owner") == uid)


# ===================== the client's real-UI presses =====================


def open_hand_menu(client, ev):
    """TAB-select C, cancel a leftover targeting, the right-hand box: the action
    menu opens. Fills `ev`."""
    ev["tab"] = tab_select(client, C_ID)
    assert ev["tab"], f"TAB never selected C on the client (selectedId {battle_state(client).get('selectedId')})"
    ev["targetingCancel"] = cancel_client_targeting(client)
    r = click_nth(client, RHAND_NTH)
    assert (r.get("baseX"), r.get("baseY")) == RHAND_CENTRE, f"right-hand click landed off the box: {r}"
    client.wait_for("client ActionMenuState on top", lambda: top(client) == "ActionMenuState" or None, timeout=5)
    ev["rows"] = menu_rows(client)


def menu_key(client, ev, key):
    """The action menu open, then the row's key; records the client's top states
    until the menu is gone. Fills `ev` (states, the screen after)."""
    open_hand_menu(client, ev)
    seen = ["ActionMenuState"]
    press(client, key)
    watch(client, lambda st: st != "ActionMenuState", SCREEN_WAIT_S, seen)
    time.sleep(0.3)
    st = top(client)
    if seen[-1] != st:
        seen.append(st)
    ev["states"] = seen
    ev["screen"] = screen(client)


def open_screen(client, ev):
    """The medi-kit screen: the menu, key 49. Returns whether MedikitState is on
    the client's top (RED: the K8 refusal closes the menu, nothing opens)."""
    menu_key(client, ev, KEY_ITEM1)
    ev["banner"] = battle_state(client).get("coopWaitText")
    return ev["screen"]["state"] == "MedikitState"


def close_screen(client, ev):
    """The client's cancel key while a screen is on top. Fills ev["close"]."""
    t0 = top(client)
    if t0 == "BattlescapeState":
        ev["close"] = [t0]
        return
    seen = [t0]
    press(client, KEY_CANCEL)
    watch(client, lambda st: st == "BattlescapeState", SCREEN_WAIT_S, seen)
    ev["close"] = seen


def dismiss_host_box(host, box):
    """A host infobox holds a running order's chain (N7). Record its texts and
    close it host-only: an InfoboxOKState through its OK button (the tripwire's
    A1.6 completion), any other infobox through dismiss_popup."""
    t = top(host) or ""
    if "Infobox" not in t:
        return
    texts = [w.get("text") for w in host.cmd({"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]
    if t == "InfoboxOKState":
        r = host.cmd({"cmd": "click_widget", "match": "ok"})
        how = ("ok button", r.get("ok"), r.get("error"))
    else:
        r = host.cmd({"cmd": "dismiss_popup"})
        how = ("dismiss_popup", r.get("handled"), r.get("error"))
    time.sleep(0.2)
    box.append({"top": t, "texts": texts, "how": how, "after": top(host)})


def screen_press(host, client, key, notes):
    """One MedikitState button on the client: snapshot, the key, the bounded
    wait (sent -> the order over). Returns (before, rec, out, screen after)."""
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    press(client, key)
    out = await_press(host, client, before, notes)
    time.sleep(0.3)
    scr = screen(client)
    rec = collect_all(host, client, seq0)
    return before, rec, out, scr


# ===================== scenarios =====================


def c23b_medikit(host, client, ctx):
    notes = []
    pc_ = place(host, client, C_ID, C_TILE, C_DIR)
    ph_ = place(host, client, H_ID, H_TILE, H_DIR)
    w = wounds_both(host, client, H_ID, WOUNDS)
    set_tu_both(host, client, C_ID, TU_MAX)
    kit = give(host, client, MEDIKIT)
    staged = diff_buckets(host, client)
    h0 = {"host": hview(session.units_by_id(battle_state(host)).get(H_ID)),
          "client": hview(session.units_by_id(battle_state(client)).get(H_ID))}
    b0 = snap(host, client)
    ev = {}
    opened = False
    try:
        opened = open_screen(client, ev)
    except Exception as e:
        notes.append(f"real-UI USE MEDI-KIT: {short(e)}")
    after_open = {"host": snap_one(host), "client": snap_one(client)}
    legs = []
    if opened:
        for key, action, part, ch_after, tu_after in C23B_PRESSES:
            nl = []
            before, rec, out, scr = screen_press(host, client, key, nl)
            legs.append({"key": key, "action": action, "part": part, "chargesAfter": ch_after, "tuAfter": tu_after,
                         "before": before, "rec": rec, "out": out, "screen": scr, "notes": nl})
            if scr["state"] != "MedikitState":
                break
        cb = {"host": snap_one(host), "client": snap_one(client)}
        close_screen(client, ev)
        time.sleep(0.5)
        ca = {"host": snap_one(host), "client": snap_one(client)}
    else:
        cb = ca = None
    rec_end = collect_all(host, client, b0["host"]["lastSeqEmitted"] or 0)
    print(f"EVIDENCE C23b: staged C={pc_} H={ph_} wounds={w} kit={kit} stagedDiff={staged} H before={h0} "
          f"press={ev} opened={opened} afterOpen={after_open}; "
          + " | ".join(
              f"LEG {lg['action']} (key {lg['key']}) outcome={lg['out']}; {press_view(lg['before'], lg['rec'])}; "
              f"screen={lg['screen']} newContexts={ctx_view(lg['before'], lg['rec'])} host evs="
              f"{ev_tuples(lg['rec']['hev'])} client evs={ev_tuples(lg['rec']['cev'])}; H host="
              f"{hview(lg['rec']['uh'].get(H_ID))} client={hview(lg['rec']['uc'].get(H_ID))}; kit host="
              f"{charges(lg['rec']['ih'], kit)} client={charges(lg['rec']['ic'], kit)}; C tu host="
              f"{(lg['rec']['uh'].get(C_ID) or {}).get('tu')} client={(lg['rec']['uc'].get(C_ID) or {}).get('tu')}; "
              f"diff={lg['rec']['diff']} desync={lg['rec']['dsc']}; notes={lg['notes']}" for lg in legs)
          + f" | CANCEL close={ev.get('close')} before={cb} after={ca}; end: {press_view(b0, rec_end)}; "
          f"ui={ui_view(b0, rec_end)}; diff={rec_end['diff']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if w != WOUNDS:
        fails.append(f"precondition: fatalWounds lever reply {w} (want {WOUNDS})")
    if ev.get("rows") != KIT_ROWS:
        fails.append(f"precondition: client menu rows {ev.get('rows')} (want {KIT_ROWS})")
    if not opened:
        fails.append(f"MedikitState never opened on the client after key {KEY_ITEM1} (states {ev.get('states')}, "
                     f"banner {ev.get('banner')!r}): want the screen open locally with nothing sent")
    else:
        fails += nothing_sent_fails(b0, after_open["host"], after_open["client"], "opening the screen")
        if ev["screen"]["nums"] != nums_of([10, 10, 10]):
            fails.append(f"the opened screen shows {ev['screen']} (want 10 / 10 / 10 at {sorted(MEDIKIT_TXT)})")
    if opened and len(legs) != len(C23B_PRESSES):
        fails.append(f"the screen closed after {len(legs)} press(es) (want it open through all three: D148)")
    for lg in legs:
        what, rec, before = lg["action"], lg["rec"], lg["before"]
        fails += [f"{what}: {m}" for m in lg["notes"]]
        fails += [f"{what}: {m}" for m in forwarded_fails(before, rec)]
        f, cx = admitted_fails(before, rec, "medikit", "medikit", C_ID)
        fails += [f"{what}: {m}" for m in f]
        fails += chain_fails(rec, cx, MEDIKIT_CHAIN, what)
        aid = cx.get("actionId") if cx else None
        if cx:
            fails += cue_fails(host, chain_of(rec, aid), "medikit",
                               {"actor": C_ID, "unit": H_ID, "item": kit, "action": lg["action"],
                                "bodypart": lg["part"]}, what)
        fails += halt_fails(rec, aid, True, what)
        if lg["screen"]["state"] != "MedikitState":
            fails.append(f"{what}: client top {lg['screen']['state']} after the answer (want MedikitState: D148)")
        elif lg["screen"]["nums"] != nums_of(charges(rec["ih"], kit)):
            fails.append(f"{what}: the client's screen shows {lg['screen']['nums']} (want the host's charges "
                         f"{nums_of(charges(rec['ih'], kit))})")
        wounds = WOUNDS_HEALED
        fails += h_fails(rec, wounds, what)
        fails += charge_fails(rec, kit, lg["chargesAfter"], what)
        fails += [f"{what}: {m}" for m in tu_fails(rec, C_ID, lg["tuAfter"])]
        fails += aftermath_fails(rec, aid, "medikit", True, what)
        if rec["clientUi"]["banner"] == TEXT_ITEM_ACTION:
            fails.append(f"{what}: client banner {rec['clientUi']['banner']!r} (the interim host-only refusal)")
    if opened:
        if (ev.get("close") or [None])[-1] != "BattlescapeState":
            fails.append(f"cancel: client states {ev.get('close')} (want the screen closed)")
        fails += nothing_sent_fails({"host": cb["host"], "client": cb["client"]}, ca["host"], ca["client"], "cancel")
    fails += common_fails(host, client, b0, "C23b")
    finish(fails)


def c23b5_inflight(host, client, ctx):
    notes = []
    wait_banner_not(client, TEXT_ITEM_ACTION, notes)
    w = wounds_both(host, client, H_ID, WOUNDS)
    set_tu_both(host, client, C_ID, TU_MAX)
    kit = give(host, client, MEDIKIT)
    staged = diff_buckets(host, client)
    ev = {}
    opened = False
    try:
        opened = open_screen(client, ev)
    except Exception as e:
        notes.append(f"real-UI USE MEDI-KIT: {short(e)}")
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    second = {}
    out = {"state": "not pressed"}
    dr = None
    if opened:
        dr = host.ok({"cmd": "defer_intents", "ms": DEFER_MS, "count": 1})
        t0 = time.time()
        press(client, KEY_HEAL)
        flight = None
        while time.time() - t0 < SENT_WAIT_S:
            flight = event_state(client).get("inFlight")
            if flight:
                break
            time.sleep(POLL_S)
        second["sentAfterS"] = round(time.time() - t0, 3)
        second["inFlightAtFirst"] = flight
        press(client, KEY_HEAL)
        second["pressedAtS"] = round(time.time() - t0, 3)
        second["inFlightAfterSecond"] = event_state(client).get("inFlight")
        try:
            client.wait_for("the order is over (client slot empty, host idle, client caught up)",
                            lambda: order_done(host, client) or None, timeout=ORDER_TIMEOUT_S, interval=0.1)
        except Exception as e:
            notes.append(f"order never finished: {short(e)}")
        out = {"state": "pressed twice", "tEnd": round(time.time() - t0, 3)}
        time.sleep(0.5)
    disarm = host.ok({"cmd": "defer_intents", "ms": 0, "count": 0})   # a deferral no order consumed never outlives C23b5
    scr = screen(client)
    rec = collect_all(host, client, seq0)
    new = ctx_view(before, rec)
    close_screen(client, ev)
    print(f"EVIDENCE C23b5: staged wounds={w} kit={kit} stagedDiff={staged} press={ev} opened={opened} "
          f"defer={dr} disarm={disarm} second={second} outcome={out}; {press_view(before, rec)}; "
          f"ui={ui_view(before, rec)}; screen={scr}; newContexts={new}; host evs={ev_tuples(rec['hev'])} "
          f"client evs={ev_tuples(rec['cev'])}; H host={hview(rec['uh'].get(H_ID))} client="
          f"{hview(rec['uc'].get(H_ID))}; kit host={charges(rec['ih'], kit)} client={charges(rec['ic'], kit)}; "
          f"C tu host={(rec['uh'].get(C_ID) or {}).get('tu')} client={(rec['uc'].get(C_ID) or {}).get('tu')}; "
          f"close={ev.get('close')}; diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if not opened:
        fails.append(f"MedikitState never opened on the client after key {KEY_ITEM1} (states {ev.get('states')}, "
                     f"banner {ev.get('banner')!r})")
    else:
        if not second.get("inFlightAtFirst") or not second.get("inFlightAfterSecond"):
            fails.append(f"precondition: the second heal press did not land while the first order was in flight "
                         f"({second})")
        fails += forwarded_fails(before, rec)
        f, cx = admitted_fails(before, rec, "medikit", "medikit", C_ID)
        fails += f
        d = recv_of(rec["host"]["intentsReceived"], "medikit", "admitted") - recv_of(
            before["host"]["intentsReceived"], "medikit", "admitted")
        if d != 1:
            fails.append(f"host intentsReceived.medikit.admitted +{d} (want +1: the in-flight press is ignored, D150)")
        fails += chain_fails(rec, cx, MEDIKIT_CHAIN, "C23b5")
        fails += h_fails(rec, WOUNDS_HEALED, "C23b5")
        fails += charge_fails(rec, kit, [10, 9, 10], "C23b5")
        fails += tu_fails(rec, C_ID, C_TU_FULL - KIT_TU)
        if scr["state"] != "MedikitState":
            fails.append(f"client top {scr['state']} after the answer (want MedikitState still open)")
    fails += common_fails(host, client, before, "C23b5")
    finish(fails)


def c23b6_tu_short(host, client, ctx):
    notes = []
    wait_banner_not(client, TEXT_ITEM_ACTION, notes)
    wait_banner_not(client, TEXT_NO_TU, notes)
    kit = give(host, client, MEDIKIT)
    tu = set_tu_both(host, client, C_ID, KIT_TU - 1)
    staged = diff_buckets(host, client)
    h0 = hview(session.units_by_id(battle_state(host)).get(H_ID))
    ev = {}
    opened = False
    try:
        opened = open_screen(client, ev)
    except Exception as e:
        notes.append(f"real-UI USE MEDI-KIT: {short(e)}")
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    out = {"state": "not pressed"}
    seen = []
    if opened:
        press(client, KEY_STIM)
        out = await_press(host, client, before, notes)
        watch(client, lambda st: st != "MedikitState", SCREEN_WAIT_S, seen)
        time.sleep(0.3)
    scr = screen(client)
    rec = collect_all(host, client, seq0)
    new = ctx_view(before, rec)
    print(f"EVIDENCE C23b6: staged kit={kit} C tu={tu} stagedDiff={staged} press={ev} opened={opened} "
          f"outcome={out} statesAfter={seen}; {press_view(before, rec)}; ui={ui_view(before, rec)}; screen={scr}; "
          f"newContexts={new}; host evs={ev_tuples(rec['hev'])}; H before={h0} host={hview(rec['uh'].get(H_ID))} "
          f"client={hview(rec['uc'].get(H_ID))}; kit host={charges(rec['ih'], kit)} client={charges(rec['ic'], kit)}; "
          f"diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if tu != KIT_TU - 1:
        fails.append(f"precondition: C TU {tu} (want {KIT_TU - 1})")
    if not opened:
        fails.append(f"MedikitState never opened on the client after key {KEY_ITEM1} (states {ev.get('states')}, "
                     f"banner {ev.get('banner')!r})")
    else:
        ld = rec["client"]["lastDeny"] or {}
        if ld.get("reason") != "no_tu":
            fails.append(f"client lastDeny {rec['client']['lastDeny']} (want reason no_tu)")
        if rec["clientUi"]["banner"] != TEXT_NO_TU:
            fails.append(f"client banner {rec['clientUi']['banner']!r} (want vanilla's {TEXT_NO_TU!r})")
        if scr["state"] == "MedikitState":
            fails.append("the client's MedikitState is still open after the deny (want it closed)")
        d = recv_of(rec["host"]["intentsReceived"], "medikit", "denied") - recv_of(
            before["host"]["intentsReceived"], "medikit", "denied")
        if d != 1:
            fails.append(f"host intentsReceived.medikit.denied +{d} (want +1)")
        if new:
            fails.append(f"host closedContexts gained {new} (want none: nothing executed)")
        if rec["host"]["lastSeqEmitted"] != before["host"]["lastSeqEmitted"]:
            fails.append(f"host lastSeqEmitted {before['host']['lastSeqEmitted']}->{rec['host']['lastSeqEmitted']} "
                         f"(want unchanged)")
        if rec["client"]["inFlight"] is not None:
            fails.append(f"client inFlight {rec['client']['inFlight']} (want null)")
    fails += h_fails(rec, h0.get("wounds") if h0 else None, "C23b6")
    fails += charge_fails(rec, kit, [10, 10, 10], "C23b6")
    fails += tu_fails(rec, C_ID, KIT_TU - 1)
    fails += common_fails(host, client, before, "C23b6")
    finish(fails)


def c23b3_consumable(host, client, ctx):
    notes = []
    wait_banner_not(client, TEXT_ITEM_ACTION, notes)
    w = wounds_both(host, client, H_ID, WOUNDS)
    set_tu_both(host, client, C_ID, TU_MAX)
    kit = give(host, client, ONE_CHARGE)
    staged = diff_buckets(host, client)
    k0 = (charges(items_of(host), kit), charges(items_of(client), kit))
    ev = {}
    opened = False
    try:
        opened = open_screen(client, ev)
    except Exception as e:
        notes.append(f"real-UI USE MEDI-KIT: {short(e)}")
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    out = {"state": "not pressed"}
    scr = screen(client)
    if opened:
        before, rec0, out, scr = screen_press(host, client, KEY_HEAL, notes)
    rec = collect_all(host, client, seq0)
    cb = {"host": snap_one(host), "client": snap_one(client)}
    close_screen(client, ev)
    time.sleep(0.5)
    ca = {"host": snap_one(host), "client": snap_one(client)}
    alive = {n: bool(gc.cmd({"cmd": "event_state"}).get("ok")) for n, gc in (("host", host), ("client", client))}
    new = ctx_view(before, rec)
    print(f"EVIDENCE C23b3: staged wounds={w} kit={kit} charges={k0} stagedDiff={staged} press={ev} "
          f"opened={opened} outcome={out}; {press_view(before, rec)}; ui={ui_view(before, rec)}; screen={scr}; "
          f"newContexts={new}; host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; kit host="
          f"{rec['ih'].get(kit)} client={rec['ic'].get(kit)}; H host={hview(rec['uh'].get(H_ID))} client="
          f"{hview(rec['uc'].get(H_ID))}; close={ev.get('close')} before={cb} after={ca} alive={alive}; "
          f"diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if k0 != ([0, 1, 0], [0, 1, 0]):
        fails.append(f"precondition: the one-charge kit's charges host/client {k0} (want [0, 1, 0] on both)")
    if not opened:
        fails.append(f"MedikitState never opened on the client after key {KEY_ITEM1} (states {ev.get('states')}, "
                     f"banner {ev.get('banner')!r})")
    else:
        if ev["screen"]["nums"] != nums_of([0, 1, 0]):
            fails.append(f"the opened screen shows {ev['screen']} (want 0 / 0 / 1)")
        fails += forwarded_fails(before, rec)
        f, cx = admitted_fails(before, rec, "medikit", "medikit", C_ID)
        fails += f
        fails += chain_fails(rec, cx, MEDIKIT_CHAIN, "C23b3")
        if cx:
            fails += cue_fails(host, chain_of(rec, cx.get("actionId")), "medikit",
                               {"actor": C_ID, "unit": H_ID, "item": kit, "action": "heal",
                                "bodypart": WOUND_PART}, "C23b3")
        if kit in rec["ih"] or kit in rec["ic"]:
            fails.append(f"kit {kit} host={rec['ih'].get(kit)} client={rec['ic'].get(kit)} after its last charge "
                         f"(want removed on both, C3-Q12)")
        if scr["state"] != "MedikitState" or scr["nums"] != nums_of([0, 0, 0]):
            fails.append(f"the client's screen after the answer {scr} (want MedikitState open showing 0 / 0 / 0)")
        fails += h_fails(rec, WOUNDS_HEALED, "C23b3")
        fails += tu_fails(rec, C_ID, C_TU_FULL - KIT_TU)
        if (ev.get("close") or [None])[-1] != "BattlescapeState":
            fails.append(f"cancel: client states {ev.get('close')} (want the screen closed)")
        fails += nothing_sent_fails(cb, ca["host"], ca["client"], "cancel")
    if alive != {"host": True, "client": True}:
        fails.append(f"a machine stopped answering after the close: {alive}")
    fails += common_fails(host, client, before, "C23b3")
    finish(fails)


def c23b2_one_click(host, client, ctx):
    notes = []
    wait_banner_not(client, TEXT_ITEM_ACTION, notes)
    w = wounds_both(host, client, H_ID, WOUNDS)
    set_tu_both(host, client, C_ID, TU_MAX)
    kit = give(host, client, ONE_CLICK)
    staged = diff_buckets(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {}
    try:
        menu_key(client, ev, KEY_ITEM1)
    except Exception as e:
        notes.append(f"real-UI USE MEDI-KIT: {short(e)}")
    out = await_press(host, client, before, notes)
    settle(host, client, notes)
    rec = collect_all(host, client, seq0)
    new = ctx_view(before, rec)
    print(f"EVIDENCE C23b2: staged wounds={w} kit={kit} stagedDiff={staged} press={ev} outcome={out}; "
          f"{press_view(before, rec)}; ui={ui_view(before, rec)}; newContexts={new}; host evs={ev_tuples(rec['hev'])} "
          f"client evs={ev_tuples(rec['cev'])}; H host={hview(rec['uh'].get(H_ID))} client="
          f"{hview(rec['uc'].get(H_ID))}; kit host={charges(rec['ih'], kit)} client={charges(rec['ic'], kit)}; "
          f"C tu host={(rec['uh'].get(C_ID) or {}).get('tu')} client={(rec['uc'].get(C_ID) or {}).get('tu')}; "
          f"diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if ev.get("rows") != KIT_ROWS:
        fails.append(f"precondition: client menu rows {ev.get('rows')} (want {KIT_ROWS})")
    if "MedikitState" in (ev.get("states") or []):
        fails.append(f"MedikitState opened on the client for the one-click kit (states {ev.get('states')})")
    fails += forwarded_fails(before, rec)
    f, cx = admitted_fails(before, rec, "medikit", "medikit", C_ID)
    fails += f
    fails += chain_fails(rec, cx, MEDIKIT_CHAIN, "C23b2")
    if cx:
        fails += cue_fails(host, chain_of(rec, cx.get("actionId")), "medikit",
                           {"actor": C_ID, "unit": H_ID, "item": kit, "action": "heal", "bodypart": WOUND_PART},
                           "C23b2")
    fails += h_fails(rec, WOUNDS_HEALED, "C23b2")
    fails += charge_fails(rec, kit, [10, 9, 10], "C23b2")
    fails += tu_fails(rec, C_ID, C_TU_FULL - KIT_TU)
    fails += aftermath_fails(rec, cx.get("actionId") if cx else None, "medikit", None, "C23b2")
    if rec["clientUi"]["banner"] == TEXT_ITEM_ACTION:
        fails.append(f"client banner {rec['clientUi']['banner']!r} (the interim host-only refusal)")
    fails += common_fails(host, client, before, "C23b2")
    finish(fails)


def c23c_scanner(host, client, ctx):
    notes = []
    wait_banner_not(client, TEXT_ITEM_ACTION, notes)
    set_tu_both(host, client, C_ID, TU_MAX)
    scanner = give(host, client, SCANNER)
    staged = diff_buckets(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {}
    try:
        menu_key(client, ev, KEY_ITEM1)
    except Exception as e:
        notes.append(f"real-UI USE SCANNER: {short(e)}")
    out = await_press(host, client, before, notes)
    settle(host, client, notes)
    time.sleep(0.3)
    rec = collect_all(host, client, seq0)
    tops = {"host": top(host), "client": top(client)}
    new = ctx_view(before, rec)
    ev2 = {}
    close_screen(client, ev2)
    print(f"EVIDENCE C23c: staged scanner={scanner} stagedDiff={staged} press={ev} outcome={out}; "
          f"{press_view(before, rec)}; ui={ui_view(before, rec)}; top={tops}; newContexts={new}; host evs="
          f"{ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; C host={ubrief(rec['uh'].get(C_ID))} "
          f"client={ubrief(rec['uc'].get(C_ID))}; close={ev2.get('close')}; diff={rec['diff']} desync={rec['dsc']}; "
          f"notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if ev.get("rows") != KIT_ROWS:
        fails.append(f"precondition: client menu rows {ev.get('rows')} (want {KIT_ROWS})")
    fails += forwarded_fails(before, rec)
    f, cx = admitted_fails(before, rec, "scanner", "use_item", C_ID)
    fails += f
    fails += chain_fails(rec, cx, SCANNER_CHAIN, "C23c")
    if cx:
        fails += cue_fails(host, chain_of(rec, cx.get("actionId")), "scanner", {"actor": C_ID, "item": scanner},
                           "C23c")
    fails += tu_fails(rec, C_ID, C_TU_FULL - SCANNER_TU)
    if tops["client"] != "ScannerState":
        fails.append(f"client top state {tops['client']} (want ScannerState, opened at the order's own end)")
    if tops["host"] == "ScannerState":
        fails.append("host top state ScannerState (want none on the host: the screen is the ordering player's)")
    fails += aftermath_fails(rec, cx.get("actionId") if cx else None, "scanner", None, "C23c")
    if rec["clientUi"]["banner"] == TEXT_ITEM_ACTION:
        fails.append(f"client banner {rec['clientUi']['banner']!r} (the interim host-only refusal)")
    fails += common_fails(host, client, before, "C23c")
    finish(fails)


def c23e_reload(host, client, ctx):
    notes = []
    stripped = strip_both(host, client, C_ID)
    rifle = give(host, client, "STR_RIFLE")
    clip = give(host, client, "STR_RIFLE_CLIP", clear=False, slot="STR_BELT", slotX=0, slotY=0)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    ih0, ic0 = items_of(host), items_of(client)
    inv = {"host": owned(ih0, C_ID), "client": owned(ic0, C_ID)}
    wait_banner_not(client, TEXT_RELOAD, notes)
    ev = {"tab": tab_select(client, C_ID), "targetingCancel": cancel_client_targeting(client), "top": top(client)}
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    press(client, ctx["reload_key"])
    out = await_press(host, client, before, notes)
    settle(host, client, notes)
    rec = collect_all(host, client, seq0)
    new = ctx_view(before, rec)
    la = {"host": loaded_ammo(rec["ih"].get(rifle) or {}, rifle), "client": loaded_ammo(rec["ic"].get(rifle) or {},
                                                                                         rifle)}
    print(f"EVIDENCE C23e: stripped={stripped} rifle={rifle} clip={clip} inventory={inv} stagedDiff={staged} "
          f"press={ev} key={ctx['reload_key']} outcome={out}; {press_view(before, rec)}; ui={ui_view(before, rec)}; "
          f"newContexts={new}; host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; loaded={la}; "
          f"clip host={ {k: (rec['ih'].get(clip) or {}).get(k) for k in ('owner', 'slot')} } client="
          f"{ {k: (rec['ic'].get(clip) or {}).get(k) for k in ('owner', 'slot')} }; C host="
          f"{ubrief(rec['uh'].get(C_ID))} client={ubrief(rec['uc'].get(C_ID))}; diff={rec['diff']} "
          f"desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    want_inv = sorted([(rifle, "STR_RIFLE", "STR_RIGHT_HAND"), (clip, "STR_RIFLE_CLIP", "STR_BELT")])
    if inv["host"] != want_inv or inv["client"] != want_inv:
        fails.append(f"precondition: C's inventory host={inv['host']} client={inv['client']} (want {want_inv})")
    if not ev["tab"] or ev["top"] != "BattlescapeState":
        fails.append(f"precondition: the reload key needs C selected on the battlescape ({ev})")
    fails += forwarded_fails(before, rec)
    f, cx = admitted_fails(before, rec, "reload", "reload", C_ID)
    fails += f
    fails += chain_fails(rec, cx, INSTANT_CHAIN, "C23e")
    if la != {"host": [clip], "client": [clip]}:
        fails.append(f"rifle {rifle} loaded ammo {la} (want [{clip}] on both)")
    fails += tu_fails(rec, C_ID, C_TU_FULL - RELOAD_TU)
    fails += aftermath_fails(rec, cx.get("actionId") if cx else None, "reload", None, "C23e")
    if rec["clientUi"]["banner"] == TEXT_RELOAD:
        fails.append(f"client banner {rec['clientUi']['banner']!r} (the interim host-only refusal)")
    fails += common_fails(host, client, before, "C23e")
    finish(fails)


def hand_press(host, client, hand, ctrl, notes):
    """One real hand right-click on the client (battle_ui_press hand_reaction,
    C selected), with the client's touch Ctrl set around it when `ctrl`.
    Returns (before, rec, out, ev)."""
    ev = {"tab": tab_select(client, C_ID)}
    if ctrl:
        ev["ctrlOn"] = client.ok({"cmd": "set_touch_modifiers", "ctrl": True}).get("ctrl")
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev["press"] = client.cmd({"cmd": "battle_ui_press", "control": "hand_reaction", "hand": hand})
    out = await_press(host, client, before, notes)
    if ctrl:
        ev["ctrlOff"] = client.ok({"cmd": "set_touch_modifiers", "ctrl": False}).get("ctrl")
    settle(host, client, notes)
    rec = collect_all(host, client, seq0)
    ev["banner"] = rec["clientUi"]["banner"]
    return before, rec, out, ev


def c23f_hands(host, client, ctx):
    notes = []
    wait_banner_not(client, TEXT_REACTIONS, notes)
    f0 = (flags(host, C_ID), flags(client, C_ID))
    staged = diff_buckets(host, client)
    b1, r1, o1, e1 = hand_press(host, client, "right", False, notes)
    fr = (flags(host, C_ID), flags(client, C_ID))
    notes2 = []
    b2, r2, o2, e2 = hand_press(host, client, "left", True, notes2)
    fl = (flags(host, C_ID), flags(client, C_ID))
    sy = {n: (gc.cmd({"cmd": "hash_now", "full": True}).get("h") or {}).get("synced")
          for n, gc in (("host", host), ("client", client))}
    print(f"EVIDENCE C23f: flags (offL, offR, prefL, prefR) before host={f0[0]} client={f0[1]} stagedDiff={staged} "
          f"| RIGHT press={e1} outcome={o1}; {press_view(b1, r1)}; newContexts={ctx_view(b1, r1)}; host evs="
          f"{ev_tuples(r1['hev'])} client evs={ev_tuples(r1['cev'])}; flags host={fr[0]} client={fr[1]}; "
          f"diff={r1['diff']}; notes={notes} | LEFT+CTRL press={e2} outcome={o2}; {press_view(b2, r2)}; "
          f"newContexts={ctx_view(b2, r2)}; host evs={ev_tuples(r2['hev'])} client evs={ev_tuples(r2['cev'])}; "
          f"flags host={fl[0]} client={fl[1]}; synced={sy}; diff={r2['diff']} desync={r2['dsc']}; notes={notes2}",
          flush=True)
    fails = list(notes) + list(notes2)
    if staged:
        fails.append(f"buckets differ before the presses: {staged} (want none)")
    if f0 != (FLAGS_0, FLAGS_0):
        fails.append(f"precondition: C flags host={f0[0]} client={f0[1]} (want {FLAGS_0} on both)")
    if e2.get("ctrlOn") is not True or e2.get("ctrlOff") is not False:
        fails.append(f"precondition: the client's touch Ctrl lever {e2} (want on for the left press, then off)")
    for what, before, rec, want, got in (("right", b1, r1, FLAGS_RIGHT, fr), ("left+ctrl", b2, r2, FLAGS_CTRL_LEFT,
                                                                             fl)):
        fails += [f"{what}: {m}" for m in forwarded_fails(before, rec)]
        f, cx = admitted_fails(before, rec, "reaction_hands", "reaction_hands", C_ID)
        fails += [f"{what}: {m}" for m in f]
        fails += chain_fails(rec, cx, INSTANT_CHAIN, what)
        if got != (want, want):
            fails.append(f"{what}: C flags host={got[0]} client={got[1]} (want {want} on both, vanilla's toggle)")
        if rec["clientUi"]["banner"] == TEXT_REACTIONS:
            fails.append(f"{what}: client banner {rec['clientUi']['banner']!r} (the interim host-only refusal)")
    if sy["host"] is None or sy["host"] != sy["client"]:
        fails.append(f"synced bucket host={sy['host']} client={sy['client']} (want equal)")
    fails += common_fails(host, client, b1, "C23f")
    finish(fails)


def c23b4_revive(host, client, ctx):
    notes = []
    wait_banner_not(client, TEXT_ITEM_ACTION, notes)
    # ---- a real knockout: C's own stun rod on H (the C21 shape; S-C's melee intent) ----
    rod = give(host, client, STUN_ROD)
    pc_ = place(host, client, C_ID, C_TILE, C_DIR)
    ph_ = place(host, client, H_ID, H_TILE, H_DIR)
    hs = both(host, client, {"cmd": "battle_set_unit_state", "unit": H_ID, "health": KO_H_HEALTH,
                             "fatalWounds": [0] * 6}, ("health", "stun", "status", "fatalWounds"))
    set_tu_both(host, client, C_ID, TU_MAX)
    b_ko = snap(host, client)
    seq_ko = b_ko["host"]["lastSeqEmitted"] or 0
    ko = {}
    box = []
    try:
        open_hand_menu(client, ko)
        host.ok({"cmd": "set_seed", "seed": SEED_KO})
        press(client, KEY_STUN)
        client.wait_for("the stun order sent", lambda: (event_state(client).get("inFlight") is not None or (
            event_state(host).get("lastSeqEmitted") or 0) != seq_ko) or None, timeout=SENT_WAIT_S, interval=POLL_S)
        deadline = time.time() + ORDER_TIMEOUT_S
        while time.time() < deadline:
            dismiss_host_box(host, box)
            if order_done(host, client):
                break
            time.sleep(0.1)
        session.wait_host_idle(host, client, timeout=20)
    except Exception as e:
        notes.append(f"the knockout: {short(e)}")
    r_ko = collect_all(host, client, seq_ko)
    hko = {"host": hview(r_ko["uh"].get(H_ID)), "client": hview(r_ko["uc"].get(H_ID))}
    bodies = {n: sorted(i for i, v in its.items() if v.get("unitLink") == H_ID)
              for n, its in (("host", r_ko["ih"]), ("client", r_ko["ic"]))}
    # ---- H one stimulant from waking, a medi-kit on C, C onto H's tile ----
    staged = {}
    try:
        staged["stun"] = both(host, client, {"cmd": "battle_set_unit_state", "unit": H_ID, "stun": KO_STUN},
                              ("health", "stun", "status")).get("stun")
        staged["kit"] = give(host, client, MEDIKIT)
        staged["C"] = both(host, client, {"cmd": "battle_teleport_unit", "unit": C_ID, "x": H_TILE[0],
                                          "y": H_TILE[1], "z": H_TILE[2], "dir": C_DIR}, ("to", "dir")).get("to")
        set_tu_both(host, client, C_ID, TU_MAX)
    except Exception as e:
        notes.append(f"the staging after the knockout: {short(e)}")
    kit = staged.get("kit")
    uh, uc = session.units_by_id(battle_state(host)), session.units_by_id(battle_state(client))
    pre = {"H": {"host": hview(uh.get(H_ID)), "client": hview(uc.get(H_ID))},
           "C": {"host": ubrief(uh.get(C_ID)), "client": ubrief(uc.get(C_ID))}, "diff": diff_buckets(host, client)}
    # ---- the client's medi-kit on the patient on its tile, then the stimulant ----
    ev = {}
    opened = False
    try:
        opened = open_screen(client, ev)
    except Exception as e:
        notes.append(f"real-UI USE MEDI-KIT: {short(e)}")
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    out = {"state": "not pressed"}
    seen = []
    if opened:
        press(client, KEY_STIM)
        out = await_press(host, client, before, notes)
        watch(client, lambda st: st != "MedikitState", SCREEN_WAIT_S, seen)
        time.sleep(0.3)
    scr = screen(client)
    rec = collect_all(host, client, seq0)
    new = ctx_view(before, rec)
    hh, hc = hview(rec["uh"].get(H_ID)), hview(rec["uc"].get(H_ID))
    bodies_end = {n: sorted(i for i, v in its.items() if v.get("unitLink") == H_ID)
                  for n, its in (("host", rec["ih"]), ("client", rec["ic"]))}
    print(f"EVIDENCE C23b4: KNOCKOUT rod={rod} C={pc_} H={ph_} Hset={ {k: hs.get(k) for k in ('health', 'stun', 'status', 'fatalWounds')} } "
          f"press={ko} hostInfobox={box}; {press_view(b_ko, r_ko)}; newContexts={ctx_view(b_ko, r_ko)}; host evs="
          f"{ev_tuples(r_ko['hev'])}; H={hko} bodies={bodies} | STAGED {staged} pre={pre} | STIM press={ev} "
          f"opened={opened} outcome={out} statesAfter={seen}; {press_view(before, rec)}; ui={ui_view(before, rec)}; "
          f"screen={scr}; newContexts={new}; host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; "
          f"H host={hh} client={hc}; bodies={bodies_end}; kit host={charges(rec['ih'], kit)} client="
          f"{charges(rec['ic'], kit)}; diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    for n in ("host", "client"):
        u = hko[n] or {}
        if u.get("status") != STATUS_UNCONSCIOUS:
            fails.append(f"precondition: {n} H after the stun rod {u} (want UNCONSCIOUS)")
    if bodies["host"] != bodies["client"] or len(bodies["host"]) != 1:
        fails.append(f"precondition: H's body items host={bodies['host']} client={bodies['client']} (want one, equal)")
    for n in ("host", "client"):
        u = pre["H"][n] or {}
        c = pre["C"][n] or {}
        if (u.get("status") != STATUS_UNCONSCIOUS or u.get("wounds") != [0] * 6 or u.get("stun") != KO_STUN
                or u.get("health") != KO_H_HEALTH or (u.get("x"), u.get("y"), u.get("z")) != H_TILE
                or (c.get("x"), c.get("y"), c.get("z")) != H_TILE):
            fails.append(f"precondition: {n} H={u} C={c} (want H UNCONSCIOUS on {H_TILE} with stun {KO_STUN}, "
                         f"health {KO_H_HEALTH}, no fatal wound, C standing on that tile)")
    if pre["diff"]:
        fails.append(f"buckets differ after the staging: {pre['diff']} (want none)")
    if not opened:
        fails.append(f"MedikitState never opened on the client after key {KEY_ITEM1} (states {ev.get('states')}, "
                     f"banner {ev.get('banner')!r})")
    else:
        fails += forwarded_fails(before, rec)
        f, cx = admitted_fails(before, rec, "medikit", "medikit", C_ID)
        fails += f
        aid = cx.get("actionId") if cx else None
        if cx:
            fails += cue_fails(host, chain_of(rec, aid), "medikit",
                               {"actor": C_ID, "unit": H_ID, "item": kit, "action": "stim", "bodypart": TORSO},
                               "C23b4")
        fails += halt_fails(rec, aid, False, "C23b4")
        fails += aftermath_fails(rec, aid, "medikit", False, "C23b4")
        if scr["state"] == "MedikitState":
            fails.append("the client's MedikitState is still open after `continue: false` (want it closed on the "
                         "answer)")
        if hh != hc:
            fails.append(f"H host={hh} client={hc} (want equal)")
        if (hh or {}).get("status") != STATUS_STANDING or not (hh or {}).get("onTile") or (hh or {}).get(
                "stun") != REVIVED_STUN:
            fails.append(f"H host={hh} (want revived: status STANDING, on a tile, stun {REVIVED_STUN})")
        if bodies_end["host"] or bodies_end["client"]:
            fails.append(f"H's body items after the revive host={bodies_end['host']} client={bodies_end['client']} "
                         f"(want none)")
        fails += charge_fails(rec, kit, [10, 10, 9], "C23b4")
    fails += common_fails(host, client, before, "C23b4")
    finish(fails)


SCENARIOS = (("C23b", c23b_medikit), ("C23b5", c23b5_inflight), ("C23b6", c23b6_tu_short),
             ("C23b3", c23b3_consumable), ("C23b2", c23b2_one_click), ("C23c", c23c_scanner),
             ("C23e", c23e_reload), ("C23f", c23f_hands), ("C23b4", c23b4_revive))


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    ml = {gc.name: mod_log(gc) for gc in (host, client)}
    for name, m in ml.items():
        assert MOD_ACTIVE_LINE in (m.get("active") or []) and not m.get("invalid"), (
            f"{name}: the test mod is not active (active lines {m.get('active')}, invalid {m.get('invalid')}, "
            f"error {m.get('error')})")
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} ({MISSION}, SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p4-sd")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hs["units"] if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == SEATED, f"seated client units {seated_uids} (baked {SEATED})"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    ub = session.units_by_id(hs)
    assert (ub.get(C_ID) or {}).get("tu") == C_TU_FULL, f"C at bring-up {ubrief(ub.get(C_ID))} (baked TU {C_TU_FULL})"
    h = ub.get(H_ID) or {}
    assert {k: h.get(k) for k in H_FIELDS} == H_FIELDS and h.get("wounds") == [0] * 6, (
        f"H at bring-up {hview(h)} (baked {H_FIELDS}, no fatal wound)")
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("coopIntentsSent"), dict) and isinstance(es.get("intentsReceived"), dict)
                and "lastActionHalt" in es and "lastAftermath" in es), (
            f"{gc.name} event_state lacks the W2-P4 probes: coopIntentsSent={es.get('coopIntentsSent')!r} "
            f"intentsReceived={es.get('intentsReceived')!r}")
    session.wait_host_idle(host, client, timeout=30)
    # T0-9 (T0b's order): C and H stripped on both once (their loadouts vary per boot, F1132)
    stripped = {uid: strip_both(host, client, uid) for uid in (C_ID, H_ID)}
    assert_hash_clean(host, client, full=True, what="bring-up")
    ctx = {"reload_key": read_reload_key(client.user_dir)}
    print(f"[w2p4-sd] boot ok: {MISSION} MAP_FP={MAP_FP!r} mod={ml} turn={hs['turn']} seated={seated_uids} "
          f"H={H_ID} pinned={len(pinned)} stripped={stripped} reload_key={ctx['reload_key']} "
          f"C={ubrief(ub.get(C_ID))} H={hview(h)} A={unit_view(ub.get(A_ID))} A2={unit_view(ub.get(A2_ID))}",
          flush=True)
    return ctx


def main():
    t0 = time.time()
    host = GameClient("host", 49876, make_user_dir("w2p4_client_items_host", mods=[MOD_DIR]))
    client = GameClient("client", 49877, make_user_dir("w2p4_client_items_client", mods=[MOD_DIR]))
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
                print(f"[w2p4-sd] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_client_items: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
