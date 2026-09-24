"""W2-P2 S-C - test_w2_host_combat.py: the host's own combat runs as proper
actions with cue events, so the second player sees a clean start and end
(spec rewrite/prompts/w2p2_delta_core.md section (f) "test_w2_host_combat.py
(S-C)", sections (b)11-14 and (b)16; orchestrator rulings Q2 = (a) and
Q4 = (b), amendments A1 and A2; owner ruling D128 = (b)).

After stage S-B the host's combat RESULT already reaches the client: the
chain ends context-less, onChainQuiesced's empty-stack branch runs
CoopDelta::flushSync(), and one `sync` ev carries the delta (units, items,
the corpse with the host's id). What is missing is the ACTION: no context is
opened for the host's shot or stun, so no cue ev (`shot`, `hit`, `melee`,
`death`, `corpse`) is sent and no `bt_action_end` closes it. After stage S-C
the host opens a host-local combat context (CoopArbiter::beginHostLocalCombat,
spec (b)13), the six vanilla cue hooks emit their cues with the action's id and
`h`, and the chain's end emits the action's `bt_action_end`. Two scenarios,
ONE boot, in this order:

  C1  host real-UI snap shot kills alien A. H gets a rifle + clip
      (battle_give on BOTH, ids equal), H -> C1_H_TILE facing C1_H_DIR (one
      octant off A: the shot's own UnitTurnBState recalculates FOV and A
      becomes visible), A -> C1_A_TILE, A health 1, H TU max, H firing 120
      (all on BOTH). Host: TAB-select H, click the right-hand box
      (ActionMenuState), key 50 (SNAP), set_seed SEED_C1, one left click on
      A's tile. RED (commit S-C.1): the state is equal on both machines (the
      S-B `sync`), but host hostCombatContexts +0, no shot/hit/death/corpse
      ev in either event log, no bt_action_end for the shot. GREEN: host
      hostCombatContexts +1; the host event_log for that actionId is exactly
      shot -> hit -> death -> corpse -> bt_action_end, every one with `h`; the
      client event_log holds the same seqs with the same kinds and actionId;
      client lastCue = corpse (payload.unit A, payload.corpses = [the corpse
      id]); SB1's item / morale / onTile asserts; H tu and the clip's qty
      equal on both; the common asserts.
  C5  host stun rod knocks alien A2 unconscious. H gets a stun rod (BOTH),
      H -> C5_H_TILE facing A2 at C5_A2_TILE, A2 health 5, H TU max (BOTH).
      Host: TAB-select H, click the right-hand box once more first when H is
      still in aim mode after C1 (cursorType 2, amendment A2.3 / F503), click
      it (ActionMenuState), set_seed SEED_C5, key 52 (STUN). RED: as C1 - no
      context, no melee/death/corpse ev. GREEN: host hostCombatContexts +1;
      the host event_log for that actionId is exactly melee -> death ->
      corpse -> bt_action_end, every one with `h`; the client log holds the
      same seqs and kinds; client lastCue = corpse (payload.unit A2,
      payload.corpses = [the body item id]); A2 status UNCONSCIOUS and stun
      equal on both; the body item (unitLink A2) equal on both; A2's weapon
      on the ground on both; the common asserts.

Both scenarios also check the cueCounts probe against the event logs (for
each cue kind the scenario expects: host cueCounts delta == `kind` evs the
host emitted since the scenario's first seq, client cueCounts delta == evs
the client applied) - spec (b)16's "host emitted, client applied".

Per-cue payloads other than the last one (shot actor H, hit unit A, death
outcome) have no probe of their own: event_log carries seq/kind/actionId/h
only and lastCue holds the last cue. They are covered by the state asserts
(A DEAD / A2 UNCONSCIOUS on both) and by H's tu equal on both (the client
maps the action's bt_action_end `final` onto the FIRST cue's actor, spec
(b)12; a wrong mapping writes H's final onto the victim and the hash sees it).

Common asserts (spec (f), after the action settles with wait_host_idle):
hash_now {full:true} - ALL buckets EQUAL on both machines (never a hard-coded
count); desyncSeen false on both; client coopClientBStatePushes unchanged and
host 0; client deltaEvsApplied increased; deltaUnresolved, deltaUnsupported,
deltaRemoveMissing and deltaAddExisting all 0 on both. The spec's C1/C5 rows
name no lastDelta class counts: at GREEN the action's delta is split over its
cues, so which classes the LAST non-empty one holds depends on the split; the
item and unit equality asserts prove the item/unit halves instead.

FIXTURE (deterministic, never searched here; W2-P2 TASK 0a-2 precalc,
amendment A2). STR_TERROR_MISSION, map seed SEED_MAP 1. The roster is pinned
too: set_seed SEED_ROSTER on the HOST immediately before its open_new_battle
(names and stats repeat, amendment A2.2 / F501) - a local bring-up helper, not
raw.bring_up_lobby unchanged - then session.drive_to_battlescape with the
mission pin and set_seed SEED_MAP right before newbattle_ok, the baked MAP_FP
asserted on both, session.pin_ai_neutral. Every lever pair applies to the
CLIENT first, then the HOST (F607, S-H.1a), with the responses asserted equal;
every item a lever creates is created on both machines with ids asserted
equal. set_seed on the HOST immediately before each action.

RED-THEN-GREEN (spec (d), Q4 = b). Commit S-C.1 (this file and the
event_state probes hostCombatContexts / cueCounts / lastCue - storage and
readers only, nothing writes them) is run ONCE and both scenarios must FAIL
with their named red evidence while the state is already equal. Commit S-C.2
(contexts, cue hooks, prime action) is run ONCE and both must PASS. Each
scenario prints ONE "EVIDENCE <id>:" line with both machines' fields BEFORE its
green conditions are checked; main() runs every scenario even after an earlier
one failed and prints "PASS <id>" / "FAIL <id>: <message>". Every wait is
bounded; a wait that times out is recorded in the EVIDENCE line and fails the
scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when both scenarios pass, 2 otherwise
(a bring-up failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_host_combat.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_rw_turn_baton import RHAND_RECT, click_nth
from test_rw_seat_pacing import tab_select, SDLK_HOME
from test_w2_delta_core import (probes, diff_buckets, desync_record, short, both, tele_both, tu_both,
                                common_fails, finish, delta_view)
from test_w2_delta_items import items_by_id, item_diff, tile_of, unit_view

# ----- common (test_w2_host_combat.py and test_w2_host_combat_terrain.py; TASK 0a-2) -----
MISSION = "STR_TERROR_MISSION"
SEED_ROSTER = 1                  # set_seed on the HOST right before its open_new_battle (F501)
H_ID = 10                        # first host-seat soldier; with SEED_ROSTER 1 = "Henryk Kaminski",
                                 # tu 58, health 37, firing 46, throwing 73, melee 25, strength 45
RHAND_NTH = 25                   # click_widget nth of the right-hand box
KEY_ITEM1, KEY_ITEM2, KEY_ITEM4, KEY_FUSE_0 = 49, 50, 52, 48   # PRIME/AIMED, SNAP, STUN, fuse 0
TU_MAX = 255                     # battle_set_unit_state / battle_fire tu: clamped to the unit's max TU
FIRST_LEVER_ITEM_ID = 96         # 96 items at start on both maps (ids 0..95)

# ----- test_w2_host_combat.py (S-C): C1 + C5 -----
SEED_MAP = 1                     # first terror map seed (>= 2 capturable 1x1 aliens on every seed)
MAP_FP = -3.451266327757785e+18  # host battle_state.mapFingerprint
A_ID = 1000000                   # Sectoid Soldier, spawn (37,38,0) dir 2; STR_PLASMA_PISTOL id 56 (RIGHT_HAND),
                                 # STR_PLASMA_PISTOL_CLIP id 58 (BELT)
A2_ID = 1000001                  # Sectoid Soldier, spawn (33,45,0) dir 0; STR_PLASMA_RIFLE id 59 (RIGHT_HAND),
                                 # STR_ALIEN_GRENADE id 61, STR_PLASMA_RIFLE_CLIP id 62 (BELT)
A_CORPSE = "STR_SECTOID_CORPSE"
C1_H_TILE, C1_H_DIR = (12, 26, 0), 1   # open road; one octant off A (the shot's turn recalculates FOV)
C1_A_TILE, C1_A_DIR = (12, 23, 0), 4
C1_A_HEALTH = 1                  # battle_set_unit_state {unit: A, health: 1} on both
C1_ITEMS = ("STR_RIFLE", "STR_RIFLE_CLIP")   # give_both clear_hands -> ids 96, 97; set_stat firing 120 on both
SEED_C1 = 1                      # snap (key 50) + click A's tile: A DEAD, clip 20 -> 19, H tu 58 -> 43,
                                 # corpse id 98; host spotted [] -> [1000000, 1000005]  (3/3 standalone + 3/3 one-boot)
C5_H_TILE, C5_H_DIR = (24, 24, 0), 0   # H faces A2 on the tile north
C5_A2_TILE, C5_A2_DIR = (24, 23, 0), 4
C5_A2_HEALTH = 5                 # battle_set_unit_state {unit: A2, health: 5} on both (measured with H tu = max too)
SEED_C5 = 1                      # STUN (key 52): A2 UNCONSCIOUS, stun 120, health 5, H tu 58 -> 41
                                 # standalone: rod 96, body 97 (3/3); one-boot after C1: rod 99, body 100 (3/3)

A_WEAPON = 56                    # A's right-hand STR_PLASMA_PISTOL
A2_WEAPON = 59                   # A2's right-hand STR_PLASMA_RIFLE
FIRING_120 = 120

PORT = "48625"
FACTION_PLAYER = 0
FACTION_HOSTILE = 1
COOP_SEAT_0 = 0
STATUS_DEAD = 6                  # src/Mod/Unit.h enum UnitStatus
STATUS_UNCONSCIOUS = 7
CURSOR_AIM = 2                   # battle_state.cursorType CT_AIM: H still targeting after a shot (F503)
# spec (b)11: the 16 frozen cue kinds; `sync` is the context-less flush, not a combat cue.
CUE_KINDS = ("shot", "hit", "explosion", "melee", "psi", "death", "corpse", "prime", "sync", "fall",
             "revive", "spawn", "panic", "prox_trigger", "medikit", "scanner")
COMBAT_CUES = tuple(k for k in CUE_KINDS if k != "sync")
C1_CHAIN = ["shot", "hit", "death", "corpse", "bt_action_end"]
C5_CHAIN = ["melee", "death", "corpse", "bt_action_end"]
LOG_TAIL = 256                   # CoopEventLog::kCapacity


# ===================== small probes =====================


def top(gc):
    return session.top_state(gc)


def units(gc):
    return session.units_by_id(battle_state(gc))


def cue_probes(gc):
    """The S-C event_state probes: hostCombatContexts, cueCounts, lastCue."""
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return {"hostCombatContexts": es.get("hostCombatContexts"), "cueCounts": es.get("cueCounts") or {},
            "lastCue": es.get("lastCue")}


def evs_since(gc, seq0):
    """This machine's event ring (host: emitted, client: applied) after seq0,
    as [{seq, kind, actionId, h}] in ring order."""
    r = gc.cmd({"cmd": "event_log", "tail": LOG_TAIL})
    assert r.get("ok"), f"event_log failed on {gc.name}: {r}"
    return [{"seq": e.get("seq"), "kind": e.get("kind"), "actionId": e.get("actionId"), "h": e.get("h")}
            for e in r.get("events", []) if (e.get("seq") or 0) > seq0]


def ev_tuples(evs):
    return [(e["seq"], e["kind"], e["actionId"], e["h"]) for e in evs]


def unit_brief(u):
    v = unit_view(u)
    if v is not None:
        v["tu"] = u.get("tu")
        v["direction"] = u.get("direction")
    return v


def host_chain_done(host, uid, status):
    """HOST only: `uid` has `status`, no BState is queued or running,
    BattlescapeState on top."""
    bs = battle_state(host)
    u = session.units_by_id(bs).get(uid) or {}
    return (u.get("status") == status and bs.get("pendingStates") == 0 and not bs.get("isBusy")
            and top(host) == "BattlescapeState") or None


def open_hand_menu_host(host):
    """TAB-select H on the host, then click the right-hand box so
    ActionMenuState opens: ONE extra click first when H is still in aim mode
    (cursorType 2) after an earlier shot - that click only cancels the
    targeting (BattlescapeState's hand-click handler, amendment A2.3 / F503).
    Returns [cursorType before the clicks] or, with the extra click,
    [before, after the extra click] (evidence only)."""
    assert tab_select(host, H_ID), (f"TAB never selected H on the host (selectedId "
                                    f"{battle_state(host).get('selectedId')})")
    want = (RHAND_RECT[0] + RHAND_RECT[2] // 2, RHAND_RECT[1] + RHAND_RECT[3] // 2)
    cursor = [battle_state(host).get("cursorType")]
    if cursor[0] == CURSOR_AIM:
        r = click_nth(host, RHAND_NTH)
        assert (r.get("baseX"), r.get("baseY")) == want, f"right-hand click landed off the box: {r}"
        cursor.append(battle_state(host).get("cursorType"))
    r = click_nth(host, RHAND_NTH)
    assert (r.get("baseX"), r.get("baseY")) == want, f"right-hand click landed off the box: {r}"
    host.wait_for("host ActionMenuState on top",
                  lambda: host.cmd({"cmd": "list_widgets"}).get("state", "").endswith("ActionMenuState") or None,
                  timeout=5)
    return cursor


def press(gc, key):
    gc.ok({"cmd": "inject_input", "kind": "key", "key": key})


# ===================== action-chain checks =====================


def chain_of(host_evs, first_kind):
    """The action whose FIRST `first_kind` ev appears in the host log: its
    actionId and every host ev carrying that actionId. (None, []) when the
    host emitted no `first_kind` ev."""
    firsts = [e for e in host_evs if e["kind"] == first_kind]
    if not firsts:
        return None, []
    aid = firsts[0]["actionId"]
    return aid, [e for e in host_evs if e["actionId"] == aid]


def chain_fails(host_evs, client_evs, first_kind, want_kinds, seq0):
    """Spec (f) GREEN: the host log for the action = exactly `want_kinds`, all
    with `h`, and the client log holds the same seqs with the same kinds and
    actionId. Returns (actionId, chain, fails)."""
    fails = []
    aid, chain = chain_of(host_evs, first_kind)
    if aid is None:
        fails.append(f"host event_log has no `{first_kind}` ev since seq {seq0} (want the action's first "
                     f"cue; host evs since then={ev_tuples(host_evs)})")
        return aid, chain, fails
    if aid == 0:
        fails.append(f"the host's first `{first_kind}` ev carries actionId 0 (want the host-local combat "
                     f"context's id)")
    kinds = [e["kind"] for e in chain]
    if kinds != want_kinds:
        fails.append(f"host event_log for actionId {aid} = {kinds} (want exactly {want_kinds})")
    noh = [e["seq"] for e in chain if not e["h"]]
    if noh:
        fails.append(f"host evs of actionId {aid} without `h`: seqs {noh} (want every one with h)")
    cmap = {e["seq"]: e for e in client_evs}
    bad = [(e["seq"], e["kind"], cmap.get(e["seq"])) for e in chain
           if not cmap.get(e["seq"]) or cmap[e["seq"]]["kind"] != e["kind"]
           or cmap[e["seq"]]["actionId"] != aid]
    if bad:
        fails.append(f"client event_log does not hold the host's seqs/kinds for actionId {aid}: "
                     f"(seq, host kind, client entry)={bad}")
    return aid, chain, fails


def seq_of(chain, kind):
    for e in chain:
        if e["kind"] == kind:
            return e["seq"]
    return None


def cue_count_fails(name, before, after, evs, kinds, seq0):
    """spec (b)16: cueCounts = host emitted / client applied. For each kind the
    scenario expects, the delta equals this machine's own `kind` evs since seq0."""
    fails = []
    for k in kinds:
        d = (after.get(k) or 0) - (before.get(k) or 0)
        n = sum(1 for e in evs if e["kind"] == k)
        if d != n:
            fails.append(f"{name} cueCounts.{k} +{d} but its event_log has {n} `{k}` ev(s) since seq {seq0} "
                         f"(want equal)")
    return fails


def last_cue_fails(lc, aid, seq, unit_id, corpse_ids):
    lc = lc or {}
    pl = lc.get("payload") or {}
    if (lc.get("kind") != "corpse" or aid is None or lc.get("actionId") != aid or lc.get("seq") != seq
            or pl.get("unit") != unit_id or pl.get("corpses") != corpse_ids):
        return [f"client lastCue={lc or None} (want kind corpse, actionId {aid}, seq {seq}, payload.unit "
                f"{unit_id}, payload.corpses {corpse_ids})"]
    return []


def context_fails(cb, ca):
    d = (ca["host"]["hostCombatContexts"] or 0) - (cb["host"]["hostCombatContexts"] or 0)
    if d != 1:
        return [f"host hostCombatContexts {cb['host']['hostCombatContexts']}->{ca['host']['hostCombatContexts']} "
                f"(+{d}; want +1)"]
    return []


def red_view(host_evs, client_evs):
    """The spec's red evidence in one dict: cue and bt_action_end evs per log."""
    return {"hostCues": [(e["seq"], e["kind"], e["actionId"]) for e in host_evs if e["kind"] in COMBAT_CUES],
            "clientCues": [(e["seq"], e["kind"], e["actionId"]) for e in client_evs if e["kind"] in COMBAT_CUES],
            "hostActionEnds": [(e["seq"], e["actionId"]) for e in host_evs if e["kind"] == "bt_action_end"],
            "clientActionEnds": [(e["seq"], e["actionId"]) for e in client_evs if e["kind"] == "bt_action_end"],
            "hostSyncs": [e["seq"] for e in host_evs if e["kind"] == "sync"],
            "clientSyncs": [e["seq"] for e in client_evs if e["kind"] == "sync"]}


def cue_delta(before, after):
    keys = sorted(set(before) | set(after))
    return {k: (after.get(k) or 0) - (before.get(k) or 0) for k in keys if (after.get(k) or 0) != (before.get(k) or 0)}


# ===================== scenarios =====================


def c1_snap_kill(host, client, ctx):
    notes = []
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": C1_ITEMS[0], "ammo": C1_ITEMS[1],
                            "clear_hands": True}, ("weaponId", "ammoId"))
    rifle, clip = g["weaponId"], g["ammoId"]
    tele_both(host, client, H_ID, C1_H_TILE, C1_H_DIR)
    tele_both(host, client, A_ID, C1_A_TILE, C1_A_DIR)
    both(host, client, {"cmd": "battle_set_unit_state", "unit": A_ID, "health": C1_A_HEALTH},
         ("health", "stun", "status"))
    tu_both(host, client, H_ID)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": H_ID, "stat": "firing",
                        "value": FIRING_120}, ("tu",))
    staged_diff = diff_buckets(host, client)
    uh0, uc0 = units(host), units(client)
    aliens = sorted(uid for uid, u in uh0.items() if u.get("faction") == FACTION_HOSTILE)
    morale0 = {uid: uh0[uid].get("morale") for uid in aliens}
    ih0, ic0 = items_by_id(host), items_by_id(client)
    w0 = {"host": ih0.get(A_WEAPON), "client": ic0.get(A_WEAPON)}
    spotted0 = battle_state(host).get("spotted")
    before = {"host": probes(host), "client": probes(client)}
    cb = {"host": cue_probes(host), "client": cue_probes(client)}
    seq0 = before["host"]["lastSeqEmitted"] or 0
    cursor0 = None
    try:
        cursor0 = open_hand_menu_host(host)
        press(host, KEY_ITEM2)
        host.wait_for("host BattlescapeState on top after SNAP", lambda: top(host) == "BattlescapeState" or None,
                      timeout=5)
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
        time.sleep(0.15)
        pr = host.cmd({"cmd": "map_tile_click_pos", "x": C1_A_TILE[0], "y": C1_A_TILE[1], "z": C1_A_TILE[2]})
        assert pr.get("verified"), f"map_tile_click_pos did not verify A's tile {C1_A_TILE}: {pr}"
        host.ok({"cmd": "set_seed", "seed": SEED_C1})
        host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
        host.wait_for("host shot chain finished (A DEAD, no BState)",
                      lambda: host_chain_done(host, A_ID, STATUS_DEAD), timeout=30)
    except Exception as e:
        notes.append(f"host snap shot: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle after the shot: {short(e)}")
    uh, uc = units(host), units(client)
    ih, ic = items_by_id(host), items_by_id(client)
    ph, pc = probes(host), probes(client)
    ca = {"host": cue_probes(host), "client": cue_probes(client)}
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    dsc = desync_record(client, pc["desyncSeen"])
    end_diff = diff_buckets(host, client)
    corpses = {"host": [i for i in ih.values() if i["type"] == A_CORPSE and i.get("unitLink") == A_ID],
               "client": [i for i in ic.values() if i["type"] == A_CORPSE and i.get("unitLink") == A_ID]}
    w1 = {"host": ih.get(A_WEAPON), "client": ic.get(A_WEAPON)}
    clip1 = {"host": (ih.get(clip) or {}).get("qty"), "client": (ic.get(clip) or {}).get("qty")}
    morale1 = {uid: {"host": (uh.get(uid) or {}).get("morale"), "client": (uc.get(uid) or {}).get("morale")}
               for uid in aliens}
    idiff = item_diff(ih, ic)
    aid, chain, cfails = chain_fails(hev, cev, "shot", C1_CHAIN, seq0)
    print(f"EVIDENCE C1: staged rifle={rifle} clip={clip} H->{C1_H_TILE}/{C1_H_DIR} A->{C1_A_TILE}/{C1_A_DIR} "
          f"stagedDiff={staged_diff} cursorType(before[, after the aim-cancel click])={cursor0} spotted {spotted0}->"
          f"{battle_state(host).get('spotted')}; hostCombatContexts host {cb['host']['hostCombatContexts']}->"
          f"{ca['host']['hostCombatContexts']} client {cb['client']['hostCombatContexts']}->"
          f"{ca['client']['hostCombatContexts']}; host evs since seq {seq0}={ev_tuples(hev)} "
          f"client evs={ev_tuples(cev)} (seq, kind, actionId, h); red view={red_view(hev, cev)}; "
          f"action={aid} chain={[(e['seq'], e['kind']) for e in chain]}; cueCounts delta host="
          f"{cue_delta(cb['host']['cueCounts'], ca['host']['cueCounts'])} client="
          f"{cue_delta(cb['client']['cueCounts'], ca['client']['cueCounts'])}; lastCue host="
          f"{ca['host']['lastCue']} client={ca['client']['lastCue']}; A before host={unit_brief(uh0.get(A_ID))} "
          f"after host={unit_brief(uh.get(A_ID))} client={unit_brief(uc.get(A_ID))}; H after host="
          f"{unit_brief(uh.get(H_ID))} client={unit_brief(uc.get(H_ID))}; clip {clip} qty={clip1}; corpses="
          f"{corpses}; weapon {A_WEAPON} before={w0} after={w1}; items total host={len(ih)} client={len(ic)} "
          f"hostOnly={sorted(idiff['hostOnly'])} clientOnly={sorted(idiff['clientOnly'])} "
          f"differ={idiff['differ']}; morale before(host)={morale0} after={morale1}; client desyncSeen="
          f"{pc['desyncSeen']} desync={dsc} host desyncSeen={ph['desyncSeen']}; diffAfterShot={end_diff}; "
          f"host syncEvsEmitted {before['host']['syncEvsEmitted']}->{ph['syncEvsEmitted']} client "
          f"syncEvsApplied {before['client']['syncEvsApplied']}->{pc['syncEvsApplied']}; host lastDelta="
          f"{ph['lastDelta']} client lastDelta={pc['lastDelta']}; host {delta_view(before['host'])}->"
          f"{delta_view(ph)}; client {delta_view(before['client'])}->{delta_view(pc)}; notes={notes}",
          flush=True)
    fails = list(notes)
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    for name, it in w0.items():
        if not it or it.get("owner") != A_ID:
            fails.append(f"{name} weapon {A_WEAPON} before the shot {it} (want held by A)")
    # the action (spec (f) C1 GREEN)
    fails += context_fails(cb, ca)
    fails += cfails
    corpse_ids = [i["id"] for i in corpses["host"]]
    fails += last_cue_fails(ca["client"]["lastCue"], aid, seq_of(chain, "corpse"), A_ID, corpse_ids)
    fails += cue_count_fails("host", cb["host"]["cueCounts"], ca["host"]["cueCounts"], hev, C1_CHAIN[:-1], seq0)
    fails += cue_count_fails("client", cb["client"]["cueCounts"], ca["client"]["cueCounts"], cev, C1_CHAIN[:-1],
                             seq0)
    # SB1's item / morale / onTile asserts
    if idiff["hostOnly"] or idiff["clientOnly"] or idiff["differ"]:
        fails.append(f"battle_items differ: hostOnly={sorted(idiff['hostOnly'])} "
                     f"clientOnly={sorted(idiff['clientOnly'])} differ={idiff['differ']} (want equal)")
    if len(corpse_ids) != 1:
        fails.append(f"host corpses linked to A: {corpse_ids} (want exactly 1 {A_CORPSE} with unitLink {A_ID})")
    for cid in corpse_ids:
        hcp, ccp = ih.get(cid), ic.get(cid)
        if not ccp:
            fails.append(f"corpse {cid} missing on the client (host {hcp})")
        elif (ccp.get("unitLink") != A_ID or ccp.get("type") != A_CORPSE or tile_of(ccp) != tile_of(hcp)
              or tile_of(hcp) is None):
            fails.append(f"corpse {cid} host={hcp} client={ccp} (want {A_CORPSE}, unitLink {A_ID}, the same "
                         f"tile on both)")
    for name, it in w1.items():
        if not it or it.get("owner") != -1 or not it.get("onTile") or it.get("previousOwner") != A_ID:
            fails.append(f"{name} weapon {A_WEAPON} after the shot {it} (want owner -1, onTile, previousOwner "
                         f"{A_ID})")
    if tile_of(w1["host"]) != tile_of(w1["client"]):
        fails.append(f"weapon {A_WEAPON} tile host={tile_of(w1['host'])} client={tile_of(w1['client'])} "
                     f"(want the same)")
    for name, u in (("host", uh.get(A_ID)), ("client", uc.get(A_ID))):
        if not u or u.get("status") != STATUS_DEAD or u.get("onTile") is not False:
            fails.append(f"{name} A {unit_view(u)} (want status DEAD ({STATUS_DEAD}), onTile false)")
    lowered = [uid for uid in aliens if (morale1[uid]["host"] is not None and morale0[uid] is not None
                                         and morale1[uid]["host"] < morale0[uid])]
    if not lowered:
        fails.append(f"no alien's morale lower on the host after the kill: before={morale0} after={morale1}")
    for uid in lowered:
        if morale1[uid]["host"] != morale1[uid]["client"]:
            fails.append(f"alien {uid} morale host={morale1[uid]['host']} client={morale1[uid]['client']} "
                         f"(want equal)")
    # H tu and the clip's qty equal on both
    th, tc = (uh.get(H_ID) or {}).get("tu"), (uc.get(H_ID) or {}).get("tu")
    if th is None or th != tc:
        fails.append(f"H tu host={th} client={tc} (want equal)")
    if clip1["host"] is None or clip1["host"] != clip1["client"]:
        fails.append(f"clip {clip} qty host={clip1['host']} client={clip1['client']} (want equal)")
    fails += common_fails(host, client, before, {}, "C1")
    finish(fails)


def c5_stun(host, client, ctx):
    notes = []
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": "STR_STUN_ROD", "clear_hands": True},
             ("weaponId", "ammoId"))
    rod = g["weaponId"]
    tele_both(host, client, H_ID, C5_H_TILE, C5_H_DIR)
    tele_both(host, client, A2_ID, C5_A2_TILE, C5_A2_DIR)
    both(host, client, {"cmd": "battle_set_unit_state", "unit": A2_ID, "health": C5_A2_HEALTH},
         ("health", "stun", "status"))
    tu_both(host, client, H_ID)
    staged_diff = diff_buckets(host, client)
    uh0, uc0 = units(host), units(client)
    ih0, ic0 = items_by_id(host), items_by_id(client)
    w0 = {"host": ih0.get(A2_WEAPON), "client": ic0.get(A2_WEAPON)}
    before = {"host": probes(host), "client": probes(client)}
    cb = {"host": cue_probes(host), "client": cue_probes(client)}
    seq0 = before["host"]["lastSeqEmitted"] or 0
    cursor0 = None
    try:
        cursor0 = open_hand_menu_host(host)
        host.ok({"cmd": "set_seed", "seed": SEED_C5})
        press(host, KEY_ITEM4)
        host.wait_for("host stun chain finished (A2 UNCONSCIOUS, no BState)",
                      lambda: host_chain_done(host, A2_ID, STATUS_UNCONSCIOUS), timeout=30)
    except Exception as e:
        notes.append(f"host stun: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle after the stun: {short(e)}")
    uh, uc = units(host), units(client)
    ih, ic = items_by_id(host), items_by_id(client)
    ph, pc = probes(host), probes(client)
    ca = {"host": cue_probes(host), "client": cue_probes(client)}
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    dsc = desync_record(client, pc["desyncSeen"])
    end_diff = diff_buckets(host, client)
    bodies = {"host": [i for i in ih.values() if i.get("unitLink") == A2_ID],
              "client": [i for i in ic.values() if i.get("unitLink") == A2_ID]}
    w1 = {"host": ih.get(A2_WEAPON), "client": ic.get(A2_WEAPON)}
    idiff = item_diff(ih, ic)
    aid, chain, cfails = chain_fails(hev, cev, "melee", C5_CHAIN, seq0)
    print(f"EVIDENCE C5: staged rod={rod} H->{C5_H_TILE}/{C5_H_DIR} A2->{C5_A2_TILE}/{C5_A2_DIR} "
          f"stagedDiff={staged_diff} cursorType(before[, after the aim-cancel click])={cursor0}; hostCombatContexts host "
          f"{cb['host']['hostCombatContexts']}->{ca['host']['hostCombatContexts']} client "
          f"{cb['client']['hostCombatContexts']}->{ca['client']['hostCombatContexts']}; host evs since seq "
          f"{seq0}={ev_tuples(hev)} client evs={ev_tuples(cev)} (seq, kind, actionId, h); red view="
          f"{red_view(hev, cev)}; action={aid} chain={[(e['seq'], e['kind']) for e in chain]}; cueCounts delta "
          f"host={cue_delta(cb['host']['cueCounts'], ca['host']['cueCounts'])} client="
          f"{cue_delta(cb['client']['cueCounts'], ca['client']['cueCounts'])}; lastCue host="
          f"{ca['host']['lastCue']} client={ca['client']['lastCue']}; A2 before host={unit_brief(uh0.get(A2_ID))} "
          f"after host={unit_brief(uh.get(A2_ID))} client={unit_brief(uc.get(A2_ID))}; H after host="
          f"{unit_brief(uh.get(H_ID))} client={unit_brief(uc.get(H_ID))}; bodies={bodies}; weapon {A2_WEAPON} "
          f"before={w0} after={w1}; items total host={len(ih)} client={len(ic)} "
          f"hostOnly={sorted(idiff['hostOnly'])} clientOnly={sorted(idiff['clientOnly'])} "
          f"differ={idiff['differ']}; client desyncSeen={pc['desyncSeen']} desync={dsc} host desyncSeen="
          f"{ph['desyncSeen']}; diffAfterStun={end_diff}; host syncEvsEmitted {before['host']['syncEvsEmitted']}"
          f"->{ph['syncEvsEmitted']} client syncEvsApplied {before['client']['syncEvsApplied']}->"
          f"{pc['syncEvsApplied']}; host lastDelta={ph['lastDelta']} client lastDelta={pc['lastDelta']}; "
          f"host {delta_view(before['host'])}->{delta_view(ph)}; client {delta_view(before['client'])}->"
          f"{delta_view(pc)}; notes={notes}", flush=True)
    fails = list(notes)
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    for name, it in w0.items():
        if not it or it.get("owner") != A2_ID:
            fails.append(f"{name} weapon {A2_WEAPON} before the stun {it} (want held by A2)")
    # the action (spec (f) C5 GREEN)
    fails += context_fails(cb, ca)
    fails += cfails
    body_ids = [i["id"] for i in bodies["host"]]
    fails += last_cue_fails(ca["client"]["lastCue"], aid, seq_of(chain, "corpse"), A2_ID, body_ids)
    fails += cue_count_fails("host", cb["host"]["cueCounts"], ca["host"]["cueCounts"], hev, C5_CHAIN[:-1], seq0)
    fails += cue_count_fails("client", cb["client"]["cueCounts"], ca["client"]["cueCounts"], cev, C5_CHAIN[:-1],
                             seq0)
    # A2 UNCONSCIOUS and stun equal on both
    sh, sc = uh.get(A2_ID) or {}, uc.get(A2_ID) or {}
    for name, u in (("host", sh), ("client", sc)):
        if u.get("status") != STATUS_UNCONSCIOUS:
            fails.append(f"{name} A2 {unit_view(u)} (want status UNCONSCIOUS ({STATUS_UNCONSCIOUS}))")
    if sh.get("stun") is None or sh.get("stun") != sc.get("stun"):
        fails.append(f"A2 stun host={sh.get('stun')} client={sc.get('stun')} (want equal)")
    # the body item (unitLink A2) equal on both
    if len(body_ids) != 1:
        fails.append(f"host items linked to A2: {body_ids} (want exactly 1 body item with unitLink {A2_ID})")
    for bid in body_ids:
        hb, cbd = ih.get(bid), ic.get(bid)
        if not cbd or hb != cbd or tile_of(hb) is None:
            fails.append(f"body item {bid} host={hb} client={cbd} (want equal on both, on a tile)")
    # A2's weapon on the ground on both
    for name, it in w1.items():
        if not it or it.get("owner") != -1 or not it.get("onTile"):
            fails.append(f"{name} weapon {A2_WEAPON} after the stun {it} (want owner -1, onTile)")
    if tile_of(w1["host"]) != tile_of(w1["client"]):
        fails.append(f"weapon {A2_WEAPON} tile host={tile_of(w1['host'])} client={tile_of(w1['client'])} "
                     f"(want the same)")
    fails += common_fails(host, client, before, {}, "C5")
    finish(fails)


SCENARIOS = (("C1", c1_snap_kill), ("C5", c5_stun))


# ===================== bring-up =====================


def bring_up_lobby_roster_pinned(host, client, port):
    """raw.bring_up_lobby with ONE added call (amendment A2.2): set_seed
    SEED_ROSTER on the HOST immediately before its open_new_battle, so the
    roster (names and stats) the NEW BATTLE screen generates repeats."""
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    host.ok({"cmd": "set_seed", "seed": SEED_ROSTER})
    raw.skirmish_host(host, port)
    raw.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": raw.CLIENT_PLAYER})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: raw.lobby(host).get("buttonVisible") or None)


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} ({MISSION}, SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p2-sc")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    ub = session.units_by_id(hs)
    for uid in (A_ID, A2_ID):
        u = ub.get(uid) or {}
        assert u.get("faction") == FACTION_HOSTILE and not u.get("isOut"), (
            f"alien {uid} at bring-up: {unit_view(u)} (want a live FACTION_HOSTILE unit)")
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("hostCombatContexts"), int) and isinstance(es.get("cueCounts"), dict)
                and "lastCue" in es), (
            f"{gc.name} event_state lacks the S-C probes: hostCombatContexts={es.get('hostCombatContexts')!r} "
            f"cueCounts={es.get('cueCounts')!r} lastCue present={'lastCue' in es}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    ph = probes(host)
    print(f"[w2p2-sc] boot ok: {MISSION} MAP_FP={MAP_FP!r} turn={hs['turn']} H={H_ID} "
          f"({(ub.get(H_ID) or {}).get('name')}) pinned={len(pinned)} host deltaArmed={ph['deltaArmed']} "
          f"deltaSeeds={ph['deltaSeeds']} probes host={cue_probes(host)} client={cue_probes(client)}",
          flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49846, make_user_dir("w2p2_host_combat_host"))
    client = GameClient("client", 49847, make_user_dir("w2p2_host_combat_client"))
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
                print(f"[w2p2-sc] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_host_combat: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
