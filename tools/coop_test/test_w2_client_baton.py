"""W2-P4 S-E3 - test_w2_client_baton.py (C24): the turn check (the baton) on
every combat order the second player gives, on its own machine AND on the host
(spec rewrite/prompts/w2p4_client_combat_intents.md section (f)
"test_w2_client_baton.py (S-E; traditional)", sections (b)10 and Q2, as amended
by AMENDMENT C1 (N26 = F1093: Q2's shared admission term also denies an
off-baton turn / kneel / walk intent) and AMENDMENT C4 (PR-Q18: the client-side
baton check sits in every intercept since the intercept's own stage, so C24's
real-UI presses render not_your_go already at this file's red commit - the
column's "green at red, declared" part).

TRADITIONAL mode, two seats. At battle start the baton is at seat 0 (the host,
D-23), so the second player (seat 1) is OFF-BATON the whole file. E54.1: a seat
off its go may do anything LOCAL (open the action menu, choose a row, aim, place
waypoints, pick a fuse, open the medi-kit screen or the skill menu); every order
that would change the shared battle is refused with the rendered
STR_COOP_DENY_NOT_YOUR_GO ("Not your turn - waiting for HostPlayer": the baton
holder's name) BEFORE anything is sent.

PART 1 - the second player's REAL-UI presses (eleven rows, in this order). Each
row: the client's banner back to the off-baton text first (a deny banner dwells
6 s), the staging (levers, client first), then the press:

  C24-snap     rifle + clip; C (12,26,0) dir 1, A (12,23,0) dir 4 (T0-1). TAB C,
               the right-hand box, key 50 (SNAP), HOME, one left click on A.
  C24-throw    an unprimed grenade; C (12,27,0) dir 2, A back on its bring-up
               tile. Key 53 (THROW), HOME, one left click on (12,22,0).
  C24-prime    an unprimed grenade. Key 49 (PRIME), fuse key 48.
  C24-stun     a stun rod; C (24,24,0) dir 0, A2 (24,23,0) dir 4 (T0-7). Key 52.
  C24-medikit  a medi-kit; C (12,26,0) dir 2, H (13,26,0) dir 6 (T0-9). Key 49
               (the medi-kit screen opens locally), then key 49 (painkiller).
  C24-scanner  a motion scanner. Key 49 (USE SCANNER).
  C24-reload   C stripped (both), a rifle with no clip in hand and a clip on the
               belt (W2-P1 S5 shape). The reload key (options.cfg).
  C24-hands    the right-hand box's right-click (battle_ui_press hand_reaction).
  C24-psi      a psi amp; C (12,26,0) dir 1, A (12,23,0) dir 4 and visible on
               both (set_stat visible), C psiSkill 100, A psiStrength 0 (T0-8).
               Key 50 (PANIC), HOME, one left click on A.
  C24-skill    C stripped (both). The SKILLS button (found by its rect), key 50
               (STR_COOP_TEST_SKILL_STOP).
  C24-spray    rifle + clip (the mod's STR_RIFLE sprays); C (12,26,0) dir 2. Key
               51 (AUTO), HOME, the client's touch Ctrl + Shift ON, one left click
               on (24,24,0) (the spray start: local display), one left click on
               (24,27,0) (the spray fires), the touch flags OFF.

  GREEN (every press): the client banner goes from the off-baton text to the
  rendered not_your_go text; client coopLocalExecBlocked exactly +1; nothing
  sent (client inFlight null, client coopIntentsSent unchanged, host
  lastSeqEmitted unchanged, host intentsReceived unchanged); every unit and item
  field unchanged on both machines. RED: declared green at red (PR-Q18); a press
  that does not render not_your_go at the red commit is a finding.

PART 2 - one `battle_intent` order of each combat kind the second player has
(spec (b)1: shoot, throw, prime, melee, psi, use_item, medikit, reload,
reaction_hands, skill) and of the three wave-1 kinds (turn, walk, kneel - C1 N26
= F1093), thirteen rows. The lever builds and sends the order exactly as the
real intercept would (sendClientIntent, tuBasis computed unless overridden) but
skips the client's own baton check, so the HOST's admission alone decides. Each
plan is a valid order (every other admission term passes): its staging repeats
the matching press's, plus C23b's patient H for the medi-kit, a floor tile for
the shot (24,26,0), a two-step walk to (14,26,0), a turn to dir 4, a kneel.

  GREEN (every order): the host denies it `not_your_go` (client lastDeny {iseq,
  reason not_your_go}; host intentsReceived[kind] denied +1, admitted +0; client
  coopIntentsSent[kind] +1; client inFlight null after the answer); nothing
  executed (host lastSeqEmitted unchanged, no new host closedContexts); every
  unit and item field unchanged on both machines; buckets equal. RED: the host
  has no baton term (Q2 not built) - every order is ADMITTED and executes.

Common asserts (spec (f), after the row settles): hash_now {full:true} - every
bucket EQUAL; desyncSeen false on both; client coopClientBStatePushes unchanged
and host 0; the W2-P2 delta must-be-0 counters on both; every lever item created
on both machines with equal ids (both()).

FIXTURE (TASK 0 T0-11, T0b; the constants of T0-1, T0-7, T0-8, T0-9 and T0-10):
the roster-pinned terror boot (set_seed SEED_ROSTER on the HOST right before its
open_new_battle), test_rw_turn_baton.pre_ok_traditional (host CoopTurnMode
traditional, set_seed 1 right before newbattle_ok), mission STR_TERROR_MISSION,
seat_count 2, the Coop_Spray_Test mod on both (the spray rifle and the soldier
skills), MAP_FP asserted on both, the seated unit ids asserted, pin_ai_neutral.
Both machines report turnMode traditional and coopActiveSeat 0; the client shows
"It is HostPlayer's turn". Every lever pair goes to the CLIENT first (F607). Item
ids are read at run time from the lever replies (F1107). battle_strip_unit id
lists are compared as sets (F882). The host's own vanilla infobox (a psi success
at the red commit) is recorded and closed host-only; a screen the client's own
order end opens (the scanner at the red commit) is closed with the client's
cancel key before the next row.

RED-THEN-GREEN (spec (d) row S-E, the orchestrator's S-E3). Commit S-E3.1 (this
file and the battle_intent plans for every kind) is run ONCE: PART 1 is declared
green at red, every PART 2 row FAILS with its order ADMITTED by the host. Commit
S-E3.2 is run ONCE and every row must PASS. Each row prints ONE "EVIDENCE <id>:"
line with both machines' fields BEFORE its green conditions are checked; main()
runs every row even after an earlier one failed and prints "PASS <id>" /
"FAIL <id>: <message>". Every wait is bounded; a wait that times out is recorded
in the EVIDENCE line and fails the row.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when every row passes, 2 otherwise (a
bring-up failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_client_baton.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_rw_turn_baton import RHAND_NTH, click_nth, pre_ok_traditional, get_coop
from test_rw_turn_mode import live_mode, TRADITIONAL
from test_rw_feedback import wait_banner
from test_rw_seat_pacing import tab_select, SDLK_HOME
from test_w2_delta_core import diff_buckets, short, both
from test_w2_host_combat import bring_up_lobby_roster_pinned, ev_tuples
from test_w2_client_shoot import (top, snap, ubrief, press, menu_rows, place, set_tu_both, give_both, aim_click,
                                  order_done, collect, ctx_view, common_fails, finish, press_view, ui_view,
                                  count_of, recv_of, RHAND_CENTRE, TU_MAX, CURSOR_AIM, POLL_S, ORDER_TIMEOUT_S)
from test_w2_client_grenade import (mod_log, open_hand_menu, menu_order, target_order, cancel_client_targeting,
                                    CURSOR_THROW)
from test_w2_client_melee_psi import await_order, set_stat_both, CURSOR_PSI
from test_w2_client_items import strip_both, dismiss_host_box
from test_w2_client_rules import touch, open_skill_menu, click_state
from test_w2_thin_client_tripwire import read_reload_key

# ----- bring-up (TASK 0 T0-11: traditional + the roster pin; the mod on both) -----
MISSION = "STR_TERROR_MISSION"
MAP_FP = -3.451266327757785e+18   # host battle_state.mapFingerprint on map seed 1, unmodded and modded (F1164)
SEATED = [8, 9]                   # the client's seated units: C and C2
C_ID = 8
H_ID = 10                         # first host-seat soldier: C23b's patient
A_ID, A2_ID = 1000000, 1000001    # Sectoid Soldiers
PORT = "48716"
COOP_SEAT_0 = 0
FACTION_PLAYER = 0
MOD_NAME = "Coop_Spray_Test"
MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", MOD_NAME)
MOD_ACTIVE_LINE = "- Coop_Spray_Test v1.0"
HOST_NAME = raw.HOST_PLAYER       # the baton holder, seat 0
TEXT_TURN = f"It is {HOST_NAME}'s turn"                        # STR_COOP_WAIT_TURN (the off-baton banner)
TEXT_NOT_YOUR_GO = f"Not your turn - waiting for {HOST_NAME}"   # STR_COOP_DENY_NOT_YOUR_GO (T0-11)

# ----- staging (T0-1, T0-6/C23s3, T0-7, T0-8, T0-9, T0-10) -----
C_TILE = (12, 26, 0)              # open road
SNAP_C_DIR = 1                    # T0-1: one octant off A
A_TILE, A_DIR = (12, 23, 0), 4
THROW_C_TILE, THROW_C_DIR = (12, 27, 0), 2    # C23s3's thrower tile (the throw tile is north, F490)
THROW_TILE = (12, 22, 0)          # C23s3: clear of the SKILLS button at HOME (F1283)
STUN_C_TILE, STUN_C_DIR = (24, 24, 0), 0      # T0-7: C faces north
STUN_A2_TILE, STUN_A2_DIR = (24, 23, 0), 4    # the tile C faces
MEDIKIT_C_DIR = 2
H_TILE, H_DIR = (13, 26, 0), 6    # T0-9: the tile C faces
PAINKILLER_PART = 1               # UnitBodyPart torso (the painkiller's part, F1249)
C_PSI_SKILL = 100
A_PSI_STRENGTH = 0
SKILL_STOP = "STR_COOP_TEST_SKILL_STOP"       # no follow-up; the script spends the cost
SPRAY_C_DIR = 2
SPRAY_W0, SPRAY_W1 = (24, 24, 0), (24, 27, 0) # T0-10 / C18
FLOOR_TARGET = (24, 26, 0)        # road floor due east of C (C16a)
SEED_SHOT = 1                     # SEED_C16A
SEED_THROW = 2                    # SEED_C23S3
SEED_MELEE = 1                    # SEED_C21
SEED_PSI = 1                      # SEED_C22P
TURN_TO = 4                       # C faces east (2): two octants
WALK_DEST = (14, 26, 0)           # two road tiles east of C

# ----- menus (spec (f) keys; rows with the mod: T0b / T0c / T0-17) -----
KEY_ITEM1, KEY_ITEM2, KEY_ITEM3, KEY_ITEM4, KEY_ITEM5 = 49, 50, 51, 52, 53   # keyBattleActionItem1..5
KEY_SNAP, KEY_AUTO, KEY_PRIME, KEY_THROW = KEY_ITEM2, KEY_ITEM3, KEY_ITEM1, KEY_ITEM5
KEY_STUN, KEY_USE, KEY_PANIC, KEY_SKILL_STOP = KEY_ITEM4, KEY_ITEM1, KEY_ITEM2, KEY_ITEM2
KEY_FUSE_0 = 48                   # PrimeGrenadeState button 0 (SDLK_0)
KEY_PAINKILLER = 49               # MedikitState SDLK_1
KEY_CANCEL = 27                   # Options::keyCancel: closes a screen or a menu
ROWS = {"rifle": 4, "grenade": 2, "rod": 2, "kit": 2, "scanner": 2, "amp": 3, "skills": 3}
BANNER_READY_S = 12               # the deny banner's Terminal dwell is 6 s (CoopBattleUi.h)
SCREEN_WAIT_S = 5

# ----- the unit and item fields a refused order must leave unchanged -----
UNIT_KEYS = ("x", "y", "z", "direction", "directionTurret", "tu", "energy", "health", "stun", "morale", "status",
             "faction", "isOut", "kneeled", "reactOffLeft", "reactOffRight", "reactPrefLeft", "reactPrefRight",
             "wounds", "mindControllerId")


# ===================== small helpers =====================


def world(gc):
    """Every unit's UNIT_KEYS and every item's battle_items fields, by id."""
    units = {u["id"]: {k: u.get(k) for k in UNIT_KEYS} for u in battle_state(gc)["units"]}
    r = gc.cmd({"cmd": "battle_items"})
    assert r.get("ok"), f"battle_items failed on {gc.name}: {r}"
    return {"units": units, "items": {i["id"]: i for i in r["items"]}}


def world_delta(w0, w1):
    """{units|items: {id: (before, after)}} for every unit / item that changed."""
    out = {}
    for part in ("units", "items"):
        a, b = w0[part], w1[part]
        ch = {i: (a.get(i), b.get(i)) for i in sorted(set(a) | set(b)) if a.get(i) != b.get(i)}
        if ch:
            out[part] = ch
    return out


def worlds(host, client):
    return {"host": world(host), "client": world(client)}


def worlds_delta(w0, w1):
    return {n: world_delta(w0[n], w1[n]) for n in ("host", "client")}


def home(host, client, ctx, uid):
    """`uid` back on its bring-up tile and facing (kept when already there)."""
    t, d = ctx["spawn"][uid]
    return place(host, client, uid, t, d)


def client_idle(client):
    """The client back on its battlescape, not targeting: a screen or menu left on
    top is closed with the cancel key, then one hand click cancels a targeting
    (F503). Returns what was done."""
    out = {"top": top(client)}
    if out["top"] != "BattlescapeState":
        press(client, KEY_CANCEL)
        try:
            client.wait_for("client BattlescapeState on top", lambda: top(client) == "BattlescapeState" or None,
                            timeout=SCREEN_WAIT_S)
        except Exception as e:
            out["closeError"] = short(e)
        out["topAfter"] = top(client)
    out["targeting"] = cancel_client_targeting(client)
    return out


def banner_ready(client, notes):
    """The client banner back on the off-baton text (a deny before it dwells 6 s)."""
    try:
        wait_banner(client, TEXT_TURN, "the off-baton banner before the row", timeout=BANNER_READY_S)
        return True
    except AssertionError as e:
        notes.append(f"precondition: {short(e, 400)}")
        return False


def nothing_sent_fails(before, rec):
    fails = []
    if rec["client"]["inFlight"] is not None:
        fails.append(f"client inFlight {rec['client']['inFlight']} (want null)")
    if rec["client"]["coopIntentsSent"] != before["client"]["coopIntentsSent"]:
        fails.append(f"client coopIntentsSent {before['client']['coopIntentsSent']}->"
                     f"{rec['client']['coopIntentsSent']} (want unchanged)")
    if rec["host"]["lastSeqEmitted"] != before["host"]["lastSeqEmitted"]:
        fails.append(f"host lastSeqEmitted {before['host']['lastSeqEmitted']}->{rec['host']['lastSeqEmitted']} "
                     f"(want unchanged)")
    if rec["host"]["intentsReceived"] != before["host"]["intentsReceived"]:
        fails.append(f"host intentsReceived {before['host']['intentsReceived']}->{rec['host']['intentsReceived']} "
                     f"(want unchanged)")
    return fails


def unchanged_fails(delta):
    if delta["host"] or delta["client"]:
        return [f"units / items changed {delta} (want none on both)"]
    return []


def rows_fails(ev, key, what):
    if ev.get("rows") != ROWS[key]:
        return [f"precondition: client {what} rows {ev.get('rows')} (want {ROWS[key]})"]
    return []


# ===================== PART 1: the real-UI presses =====================


def press_row(host, client, ctx, rid, stage, act):
    """One off-baton real-UI press: the banner back to the off-baton text, the
    staging, the press, then (bounded) the press's outcome - refused (client
    coopLocalExecBlocked moved) or sent (then until the order is over, a host
    infobox closed host-only). The banner is read right after the outcome."""
    notes = []
    idle0 = client_idle(client)
    ready = banner_ready(client, notes)
    st = {}
    try:
        st = stage(host, client, ctx) or {}
    except Exception as e:
        notes.append(f"staging: {short(e)}")
    staged = diff_buckets(host, client)
    w0 = worlds(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev, box = {}, []
    try:
        act(host, client, ctx, ev, before, st)
    except Exception as e:
        notes.append(f"real-UI press: {short(e)}")
    out = await_order(host, client, before, notes, box)
    after_banner = battle_state(client).get("coopWaitText")
    idle1 = client_idle(client)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    dismiss_host_box(host, box)
    rec = collect(host, client, seq0)
    w1 = worlds(host, client)
    delta = worlds_delta(w0, w1)
    print(f"EVIDENCE {rid}: idle={idle0} bannerReady={ready} staged={st} stagedDiff={staged} press={ev} "
          f"outcome={out} banner before={before['clientUi']['banner']!r} after={after_banner!r} "
          f"warning client={ui_view(before, rec)['client']['warning']}; {press_view(before, rec)}; "
          f"newContexts={ctx_view(before, rec)}; host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; "
          f"hostBox={box}; cleanup={idle1}; changed={delta}; C host={ubrief(rec['uh'].get(C_ID))} "
          f"client={ubrief(rec['uc'].get(C_ID))}; diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    fails += st.get("fails", [])
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if before["clientUi"]["banner"] != TEXT_TURN or after_banner != TEXT_NOT_YOUR_GO:
        fails.append(f"client banner {before['clientUi']['banner']!r} -> {after_banner!r} (want {TEXT_TURN!r} -> "
                     f"{TEXT_NOT_YOUR_GO!r}: the rendered STR_COOP_DENY_NOT_YOUR_GO naming the baton holder)")
    b, a = before["client"]["coopLocalExecBlocked"], rec["client"]["coopLocalExecBlocked"]
    if a != b + 1:
        fails.append(f"client coopLocalExecBlocked {b}->{a} (want exactly +1)")
    fails += nothing_sent_fails(before, rec)
    fails += unchanged_fails(delta)
    fails += common_fails(host, client, before, rid)
    finish(fails)


# ----- stagings (client first, F607) -----


def stage_snap(host, client, ctx):
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    return {"rifle": rifle, "clip": clip, "H": home(host, client, ctx, H_ID),
            "C": place(host, client, C_ID, C_TILE, SNAP_C_DIR), "A": place(host, client, A_ID, A_TILE, A_DIR),
            "tu": set_tu_both(host, client, C_ID, TU_MAX)}


def stage_throw(host, client, ctx):
    g = both(host, client, {"cmd": "battle_give", "unit": C_ID, "item": "STR_GRENADE", "clear_hands": True},
             ("weaponId", "ammoId"))["weaponId"]
    return {"grenade": g, "C": place(host, client, C_ID, THROW_C_TILE, THROW_C_DIR),
            "A": home(host, client, ctx, A_ID), "tu": set_tu_both(host, client, C_ID, TU_MAX)}


def stage_prime(host, client, ctx):
    g = both(host, client, {"cmd": "battle_give", "unit": C_ID, "item": "STR_GRENADE", "clear_hands": True},
             ("weaponId", "ammoId"))["weaponId"]
    return {"grenade": g, "tu": set_tu_both(host, client, C_ID, TU_MAX)}


def stage_stun(host, client, ctx):
    rod = both(host, client, {"cmd": "battle_give", "unit": C_ID, "item": "STR_STUN_ROD", "clear_hands": True},
               ("weaponId", "ammoId"))["weaponId"]
    return {"rod": rod, "C": place(host, client, C_ID, STUN_C_TILE, STUN_C_DIR),
            "A2": place(host, client, A2_ID, STUN_A2_TILE, STUN_A2_DIR), "tu": set_tu_both(host, client, C_ID, TU_MAX)}


def stage_medikit(host, client, ctx):
    kit = both(host, client, {"cmd": "battle_give", "unit": C_ID, "item": "STR_MEDI_KIT", "clear_hands": True},
               ("weaponId", "ammoId"))["weaponId"]
    return {"kit": kit, "C": place(host, client, C_ID, C_TILE, MEDIKIT_C_DIR),
            "H": place(host, client, H_ID, H_TILE, H_DIR), "tu": set_tu_both(host, client, C_ID, TU_MAX)}


def stage_scanner(host, client, ctx):
    sc = both(host, client, {"cmd": "battle_give", "unit": C_ID, "item": "STR_MOTION_SCANNER", "clear_hands": True},
              ("weaponId", "ammoId"))["weaponId"]
    return {"scanner": sc, "H": home(host, client, ctx, H_ID), "tu": set_tu_both(host, client, C_ID, TU_MAX)}


def stage_reload(host, client, ctx):
    stripped = strip_both(host, client, C_ID)
    rifle = both(host, client, {"cmd": "battle_give", "unit": C_ID, "item": "STR_RIFLE", "clear_hands": True},
                 ("weaponId", "ammoId"))["weaponId"]
    clip = both(host, client, {"cmd": "battle_give", "unit": C_ID, "item": "STR_RIFLE_CLIP", "clear_hands": False,
                               "slot": "STR_BELT", "slotX": 0, "slotY": 0}, ("weaponId", "ammoId"))["weaponId"]
    return {"stripped": stripped, "rifle": rifle, "clip": clip, "H": home(host, client, ctx, H_ID),
            "tu": set_tu_both(host, client, C_ID, TU_MAX)}


def stage_hands(host, client, ctx):
    return {"H": home(host, client, ctx, H_ID), "tu": set_tu_both(host, client, C_ID, TU_MAX)}


def stage_psi(host, client, ctx):
    amp = both(host, client, {"cmd": "battle_give", "unit": C_ID, "item": "STR_PSI_AMP", "clear_hands": True},
               ("weaponId", "ammoId"))["weaponId"]
    st = {"amp": amp, "H": home(host, client, ctx, H_ID), "C": place(host, client, C_ID, C_TILE, SNAP_C_DIR),
          "A": place(host, client, A_ID, A_TILE, A_DIR)}
    st["Avisible"] = both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "visible": True},
                          ("visible",)).get("visible")
    st["psiSkill"] = set_stat_both(host, client, C_ID, "psiSkill", C_PSI_SKILL).get("psiSkill")
    st["psiStrength"] = set_stat_both(host, client, A_ID, "psiStrength", A_PSI_STRENGTH).get("psiStrength")
    st["tu"] = set_tu_both(host, client, C_ID, TU_MAX)
    if st["Avisible"] is not True:
        st["fails"] = [f"precondition: A visible {st['Avisible']} after set_stat (want true on both)"]
    return st


def stage_skill(host, client, ctx):
    return {"stripped": strip_both(host, client, C_ID), "H": home(host, client, ctx, H_ID),
            "tu": set_tu_both(host, client, C_ID, TU_MAX)}


def stage_spray(host, client, ctx):
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    return {"rifle": rifle, "clip": clip, "H": home(host, client, ctx, H_ID),
            "C": place(host, client, C_ID, C_TILE, SPRAY_C_DIR), "tu": set_tu_both(host, client, C_ID, TU_MAX)}


# ----- presses -----


def act_snap(host, client, ctx, ev, before, st):
    ev.update(aim_click(client, KEY_SNAP, A_TILE))
    ev.pop("clickAt", None)
    st.setdefault("fails", []).extend(rows_fails(ev, "rifle", "rifle menu"))


def act_throw(host, client, ctx, ev, before, st):
    target_order(client, ev, KEY_THROW, CURSOR_THROW, THROW_TILE)
    ev.pop("clickAt", None)
    st.setdefault("fails", []).extend(rows_fails(ev, "grenade", "grenade menu"))


def act_prime(host, client, ctx, ev, before, st):
    menu_order(client, ev, KEY_PRIME, fuse_key=KEY_FUSE_0)
    st.setdefault("fails", []).extend(rows_fails(ev, "grenade", "grenade menu"))


def act_stun(host, client, ctx, ev, before, st):
    open_hand_menu(client, ev)
    st.setdefault("fails", []).extend(rows_fails(ev, "rod", "stun rod menu"))
    press(client, KEY_STUN)
    client.wait_for("client left the action menu", lambda: top(client) != "ActionMenuState" or None, timeout=5)
    ev["topAfterKey"] = top(client)


def act_medikit(host, client, ctx, ev, before, st):
    open_hand_menu(client, ev)
    st.setdefault("fails", []).extend(rows_fails(ev, "kit", "medi-kit menu"))
    press(client, KEY_USE)
    client.wait_for("client MedikitState on top", lambda: top(client) == "MedikitState" or None,
                    timeout=SCREEN_WAIT_S)
    ev["screen"] = top(client)
    press(client, KEY_PAINKILLER)


def act_scanner(host, client, ctx, ev, before, st):
    open_hand_menu(client, ev)
    st.setdefault("fails", []).extend(rows_fails(ev, "scanner", "scanner menu"))
    press(client, KEY_USE)
    client.wait_for("client left the action menu", lambda: top(client) != "ActionMenuState" or None, timeout=5)
    ev["topAfterKey"] = top(client)


def act_reload(host, client, ctx, ev, before, st):
    ev["tab"] = tab_select(client, C_ID)
    assert ev["tab"], f"TAB never selected C on the client (selectedId {battle_state(client).get('selectedId')})"
    ev["top"] = top(client)
    ev["key"] = ctx["reload_key"]
    press(client, ctx["reload_key"])


def act_hands(host, client, ctx, ev, before, st):
    ev["tab"] = tab_select(client, C_ID)
    assert ev["tab"], f"TAB never selected C on the client (selectedId {battle_state(client).get('selectedId')})"
    r = client.cmd({"cmd": "battle_ui_press", "control": "hand_reaction", "hand": "right"})
    ev["press"] = {k: r.get(k) for k in ("ok", "error")}


def act_psi(host, client, ctx, ev, before, st):
    target_order(client, ev, KEY_PANIC, CURSOR_PSI, A_TILE)
    ev.pop("clickAt", None)
    st.setdefault("fails", []).extend(rows_fails(ev, "amp", "psi amp menu"))


def act_skill(host, client, ctx, ev, before, st):
    open_skill_menu(client, ev)
    st.setdefault("fails", []).extend(rows_fails(ev, "skills", "skill menu"))
    press(client, KEY_SKILL_STOP)


def act_spray(host, client, ctx, ev, before, st):
    ev["tab"] = tab_select(client, C_ID)
    assert ev["tab"], f"TAB never selected C on the client (selectedId {battle_state(client).get('selectedId')})"
    r = click_nth(client, RHAND_NTH)
    assert (r.get("baseX"), r.get("baseY")) == RHAND_CENTRE, f"right-hand click landed off the box: {r}"
    client.wait_for("client ActionMenuState on top", lambda: top(client) == "ActionMenuState" or None, timeout=5)
    ev["rows"] = menu_rows(client)
    st.setdefault("fails", []).extend(rows_fails(ev, "rifle", "rifle menu"))
    press(client, KEY_AUTO)
    client.wait_for("client BattlescapeState on top after the AUTO key",
                    lambda: top(client) == "BattlescapeState" or None, timeout=5)
    ev["cursorAfterKey"] = battle_state(client).get("cursorType")
    assert ev["cursorAfterKey"] == CURSOR_AIM, (
        f"key {KEY_AUTO} did not start targeting on the client (cursorType {ev['cursorAfterKey']})")
    press(client, SDLK_HOME)
    time.sleep(0.15)
    pos = {n: client.cmd({"cmd": "map_tile_click_pos", "x": t[0], "y": t[1], "z": t[2]})
           for n, t in (("W0", SPRAY_W0), ("W1", SPRAY_W1))}
    ev["clickPos"] = {n: {k: p.get(k) for k in ("verified", "winX", "winY", "centered")} for n, p in pos.items()}
    assert pos["W0"].get("verified") and pos["W1"].get("verified"), (
        f"precondition: map_tile_click_pos did not verify both spray waypoints on the client: {ev['clickPos']}")
    try:
        ev["clientMods"] = touch(client, ctrl=True, shift=True)
        client.ok({"cmd": "inject_input", "kind": "click", "x": pos["W0"]["winX"], "y": pos["W0"]["winY"],
                   "button": "left"})
        ev["W0"] = click_state(host, client, before)
        ev["W0blocked"] = event_state(client).get("coopLocalExecBlocked")
        client.ok({"cmd": "inject_input", "kind": "click", "x": pos["W1"]["winX"], "y": pos["W1"]["winY"],
                   "button": "left"})
    finally:
        ev["clientModsAfter"] = touch(client, ctrl=False, shift=False)
    if ev["W0"]["state"] != "quiet" or ev["W0blocked"] != before["client"]["coopLocalExecBlocked"]:
        st.setdefault("fails", []).append(
            f"the spray start click (W0) {ev['W0']}, coopLocalExecBlocked {before['client']['coopLocalExecBlocked']}"
            f"->{ev['W0blocked']} (want quiet and unchanged: placing a waypoint is local, E54.1)")


PRESSES = (("C24-snap", stage_snap, act_snap), ("C24-throw", stage_throw, act_throw),
           ("C24-prime", stage_prime, act_prime), ("C24-stun", stage_stun, act_stun),
           ("C24-medikit", stage_medikit, act_medikit), ("C24-scanner", stage_scanner, act_scanner),
           ("C24-reload", stage_reload, act_reload), ("C24-hands", stage_hands, act_hands),
           ("C24-psi", stage_psi, act_psi), ("C24-skill", stage_skill, act_skill),
           ("C24-spray", stage_spray, act_spray))


# ===================== PART 2: the battle_intent orders =====================


def jt(t):
    return {"x": t[0], "y": t[1], "z": t[2]}


def send_order(host, client, req, notes, box):
    """One battle_intent order from the client, then (bounded) the host's answer:
    its deny (client lastDeny.iseq) or the end of the order (a host infobox
    closed host-only meanwhile, N7)."""
    r = client.cmd(dict(req))
    iseq = r.get("iseq") if r.get("ok") else None
    out = {"resp": {k: r.get(k) for k in ("ok", "iseq", "error")}, "sent": bool(iseq), "iseq": iseq, "answer": None}
    if not iseq:
        return out
    t0 = time.time()
    while time.time() - t0 < ORDER_TIMEOUT_S:
        dismiss_host_box(host, box)
        ld = event_state(client).get("lastDeny") or {}
        if ld.get("iseq") == iseq:
            out["answer"] = "deny"
            break
        if order_done(host, client):
            out["answer"] = "end"
            break
        time.sleep(POLL_S)
    if out["answer"] is None:
        notes.append(f"no answer to iseq {iseq} within {ORDER_TIMEOUT_S}s (host top {top(host)})")
    out["t"] = round(time.time() - t0, 3)
    return out


def intent_row(host, client, ctx, rid, kind, stage, request):
    """One off-baton battle_intent order: the staging, the order, the answer."""
    notes = []
    idle0 = client_idle(client)
    st = {}
    try:
        st = stage(host, client, ctx) or {}
    except Exception as e:
        notes.append(f"staging: {short(e)}")
    staged = diff_buckets(host, client)
    req = None
    try:
        req = request(st)
    except Exception as e:
        notes.append(f"request: {short(e)}")
    w0 = worlds(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    box = []
    si = {"sent": False, "resp": None, "iseq": None, "answer": None}
    if req is not None:
        if st.get("seed") is not None:
            host.ok({"cmd": "set_seed", "seed": st["seed"]})
        si = send_order(host, client, req, notes, box)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    dismiss_host_box(host, box)
    time.sleep(0.3)
    after_banner = battle_state(client).get("coopWaitText")
    idle1 = client_idle(client)
    rec = collect(host, client, seq0)
    w1 = worlds(host, client)
    delta = worlds_delta(w0, w1)
    new = ctx_view(before, rec)
    answer = {"admitted": recv_of(rec["host"]["intentsReceived"], kind, "admitted")
              - recv_of(before["host"]["intentsReceived"], kind, "admitted"),
              "denied": recv_of(rec["host"]["intentsReceived"], kind, "denied")
              - recv_of(before["host"]["intentsReceived"], kind, "denied")}
    sent = count_of(rec["client"]["coopIntentsSent"], kind) - count_of(before["client"]["coopIntentsSent"], kind)
    print(f"EVIDENCE {rid}: idle={idle0} staged={ {k: v for k, v in st.items() if k != 'fails'} } "
          f"stagedDiff={staged} request={req} intent={si} hostAnswer={answer} sent={sent} "
          f"lastDeny={rec['client']['lastDeny']} banner after={after_banner!r}; {press_view(before, rec)}; "
          f"newContexts={new}; host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; hostBox={box}; "
          f"cleanup={idle1}; changed={delta}; C host={ubrief(rec['uh'].get(C_ID))} "
          f"client={ubrief(rec['uc'].get(C_ID))}; diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    fails += st.get("fails", [])
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if not si["sent"]:
        fails.append(f"battle_intent {kind} answered {si['resp']} (want sent: an iseq)")
    else:
        ld = rec["client"]["lastDeny"] or {}
        if ld.get("iseq") != si["iseq"] or ld.get("reason") != "not_your_go":
            fails.append(f"client lastDeny {rec['client']['lastDeny']} (want {{iseq {si['iseq']}, reason "
                         f"not_your_go}}: the host's baton term, Q2)")
        if (answer["denied"], answer["admitted"]) != (1, 0):
            fails.append(f"host intentsReceived.{kind} denied +{answer['denied']} admitted +{answer['admitted']} "
                         f"(want +1 / +0)")
        if sent != 1:
            fails.append(f"client coopIntentsSent.{kind} +{sent} (want +1)")
    if rec["host"]["lastSeqEmitted"] != before["host"]["lastSeqEmitted"] or new:
        fails.append(f"host lastSeqEmitted {before['host']['lastSeqEmitted']}->{rec['host']['lastSeqEmitted']} "
                     f"newContexts={new} (want nothing executed)")
    if rec["client"]["inFlight"] is not None:
        fails.append(f"client inFlight after the answer {rec['client']['inFlight']} (want null)")
    fails += unchanged_fails(delta)
    fails += common_fails(host, client, before, rid)
    finish(fails)


# ----- stagings and plans -----


def i_shoot(host, client, ctx):
    st = stage_spray(host, client, ctx)   # rifle + clip, C on C_TILE facing east, H home, TU max
    st["seed"] = SEED_SHOT
    return st


def r_shoot(st):
    return {"cmd": "battle_intent", "kind": "shoot", "actor": C_ID,
            "plan": {"action": "snap", "weapon": st["rifle"], "ammo": st["clip"], "target": jt(FLOOR_TARGET),
                     "targetUnit": -1, "forceFire": False}}


def i_throw(host, client, ctx):
    st = stage_throw(host, client, ctx)
    st["seed"] = SEED_THROW
    return st


def r_throw(st):
    return {"cmd": "battle_intent", "kind": "throw", "actor": C_ID,
            "plan": {"item": st["grenade"], "target": jt(THROW_TILE), "targetUnit": -1}}


def r_prime(st):
    return {"cmd": "battle_intent", "kind": "prime", "actor": C_ID,
            "plan": {"item": st["grenade"], "fuse": 0, "unprime": False}}


def i_melee(host, client, ctx):
    st = stage_stun(host, client, ctx)
    st["seed"] = SEED_MELEE
    return st


def r_melee(st):
    return {"cmd": "battle_intent", "kind": "melee", "actor": C_ID,
            "plan": {"weapon": st["rod"], "target": jt(STUN_A2_TILE), "terrainPart": 0, "targetUnit": A2_ID,
                     "targetPos": jt(STUN_A2_TILE)}}


def i_psi(host, client, ctx):
    st = stage_psi(host, client, ctx)
    st["seed"] = SEED_PSI
    return st


def r_psi(st):
    return {"cmd": "battle_intent", "kind": "psi", "actor": C_ID,
            "plan": {"weapon": st["amp"], "action": "panic", "target": jt(A_TILE), "targetUnit": A_ID,
                     "targetPos": jt(A_TILE)}}


def r_use_item(st):
    return {"cmd": "battle_intent", "kind": "use_item", "actor": C_ID, "plan": {"item": st["scanner"]}}


def r_medikit(st):
    return {"cmd": "battle_intent", "kind": "medikit", "actor": C_ID,
            "plan": {"item": st["kit"], "targetUnit": H_ID, "targetPos": jt(H_TILE), "action": "painkiller",
                     "bodypart": PAINKILLER_PART}}


def r_reload(st):
    return {"cmd": "battle_intent", "kind": "reload", "actor": C_ID, "plan": {}}


def r_hands(st):
    return {"cmd": "battle_intent", "kind": "reaction_hands", "actor": C_ID, "plan": {"hand": "right", "ctrl": False}}


def r_skill(st):
    return {"cmd": "battle_intent", "kind": "skill", "actor": C_ID, "plan": {"skill": SKILL_STOP, "weapon": -1}}


def i_move(host, client, ctx):
    """C on C_TILE (kept, with its facing, when already there), H home, TU max."""
    st = {"H": home(host, client, ctx, H_ID), "C": place(host, client, C_ID, C_TILE, SPRAY_C_DIR),
          "tu": set_tu_both(host, client, C_ID, TU_MAX)}
    uh, uc = (session.units_by_id(battle_state(gc)).get(C_ID) or {} for gc in (host, client))
    st["C now"] = {"host": (uh.get("direction"), uh.get("kneeled")), "client": (uc.get("direction"), uc.get("kneeled"))}
    if uh.get("kneeled") or uc.get("kneeled"):
        st["fails"] = [f"precondition: C kneeled host={uh.get('kneeled')} client={uc.get('kneeled')} (want standing)"]
    return st


def r_turn(st):
    return {"cmd": "battle_intent", "kind": "turn", "actor": C_ID, "toDir": TURN_TO}


def r_walk(st):
    return {"cmd": "battle_intent", "kind": "walk", "actor": C_ID, "dest": jt(WALK_DEST)}


def r_kneel(st):
    return {"cmd": "battle_intent", "kind": "kneel", "actor": C_ID, "kneel": True}


INTENTS = (("C24i-shoot", "shoot", i_shoot, r_shoot), ("C24i-throw", "throw", i_throw, r_throw),
           ("C24i-prime", "prime", stage_prime, r_prime), ("C24i-melee", "melee", i_melee, r_melee),
           ("C24i-medikit", "medikit", stage_medikit, r_medikit),
           ("C24i-psi", "psi", i_psi, r_psi), ("C24i-use_item", "use_item", stage_scanner, r_use_item),
           ("C24i-reload", "reload", stage_reload, r_reload),
           ("C24i-reaction_hands", "reaction_hands", stage_hands, r_hands),
           ("C24i-skill", "skill", stage_skill, r_skill), ("C24i-turn", "turn", i_move, r_turn),
           ("C24i-walk", "walk", i_move, r_walk), ("C24i-kneel", "kneel", i_move, r_kneel))


def scenarios():
    out = []
    for rid, stage, act in PRESSES:
        out.append((rid, lambda h, c, x, rid=rid, stage=stage, act=act: press_row(h, c, x, rid, stage, act)))
    for rid, kind, stage, request in INTENTS:
        out.append((rid, lambda h, c, x, rid=rid, kind=kind, stage=stage, request=request:
                    intent_row(h, c, x, rid, kind, stage, request)))
    return out


SCENARIOS = scenarios()


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2, pre_ok=pre_ok_traditional)
    ml = {gc.name: mod_log(gc) for gc in (host, client)}
    for name, m in ml.items():
        assert MOD_ACTIVE_LINE in (m.get("active") or []) and not m.get("invalid"), (
            f"{name}: {MOD_NAME} not active (active lines {m.get('active')}, invalid {m.get('invalid')}, "
            f"error {m.get('error')})")
    modes = {gc.name: live_mode(gc) for gc in (host, client)}
    assert modes == {"host": TRADITIONAL, "client": TRADITIONAL}, f"live battle mode {modes} (want traditional)"
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} ({MISSION}, map seed 1)")
    pinned = pin_ai_neutral(host, client, tag="w2p4-se3")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hs["units"] if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == SEATED, f"seated client units {seated_uids} (baked {SEATED})"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("coopIntentsSent"), dict) and isinstance(es.get("intentsReceived"), dict)
                and "lastDeny" in es), (
            f"{gc.name} event_state lacks the W2-P4 probes: coopIntentsSent={es.get('coopIntentsSent')!r} "
            f"intentsReceived={es.get('intentsReceived')!r}")
    seats = {gc.name: event_state(gc).get("coopActiveSeat") for gc in (host, client)}
    assert seats == {"host": 0, "client": 0}, f"coopActiveSeat {seats} (want 0 on both: the host holds the baton)"
    peer = get_coop(client).get("clientName")
    assert peer == HOST_NAME, f"the client's peer name {peer!r} (want {HOST_NAME!r}, the baton holder)"
    wait_banner(client, TEXT_TURN, "bring-up: the client's off-baton banner names the baton holder", timeout=20)
    mods = {gc.name: touch(gc) for gc in (host, client)}
    assert not any(v for m in mods.values() for v in m.values()), f"touch flags at bring-up {mods} (want all off)"
    ub = session.units_by_id(hs)
    spawn = {uid: ((ub[uid]["x"], ub[uid]["y"], ub[uid]["z"]), ub[uid]["direction"]) for uid in (H_ID, A_ID, A2_ID)}
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    ctx = {"reload_key": read_reload_key(client.user_dir), "spawn": spawn}
    print(f"[w2p4-se3] boot ok: {MISSION} MAP_FP={MAP_FP!r} mod={ml} modes={modes} coopActiveSeat={seats} "
          f"peer={peer!r} turn={hs['turn']} seated={seated_uids} H={H_ID} pinned={len(pinned)} touch={mods} "
          f"spawn={spawn} reload_key={ctx['reload_key']} C={ubrief(ub.get(C_ID))}", flush=True)
    return ctx


def main():
    t0 = time.time()
    host = GameClient("host", 49882, make_user_dir("w2p4_client_baton_host", mods=[MOD_DIR]))
    client = GameClient("client", 49883, make_user_dir("w2p4_client_baton_client", mods=[MOD_DIR]))
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
                print(f"[w2p4-se3] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_client_baton: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
