"""W2-P3 S-D - test_w2_turn_cues.py: the turn machine's own chains reach the
second player as named cues - a unit that wakes up at a side change
(`revive`), a unit whose floor burns away under it (`fall`), a soldier who
panics or goes berserk at the start of the player side (a `panic` action with
its own context; a flee walk streams as `walk_step` evs) - and a burning map
runs two full turn cycles with both machines equal (spec
rewrite/prompts/w2p3_nonplayer_origins.md section (f) "test_w2_turn_cues.py
(S-D)", sections (b)1, (b)7, (b)9 (V14 `fall`, V15 `revive`, V10 `panic`),
(b)13 (the `morale` lever field), (b)14 (C9 green at the base); amendment B1
(RQ5, RQ7); ledger `## W2-P3 TASK 0b` (F863-F868) and `## W2-P3 TASK 0d`;
owner ruling D128 = (b)).

Before S-D, on the W2-P3 base, nothing here freezes: every state change
already reaches the client through W2-P2's delta (a side_transition's delta or
a context-less `sync`). What is missing is the cue and, for a panic, the
action: the revive rides the side_transition's delta, the fall rides a
context-less `sync`, a panicking soldier's flee walk streams no step and its
result rides one `sync` (F867), a berserk soldier's shots carry actionId 0.

Five scenarios, ONE boot, in this order (the S-D red precalc's combined
order, 3 boots identical; C9 runs last because its burning unit is at health
16 after its two cycles, T0b R2):

  C5r  revive at a side change (cycle 1, battle turn 1 -> 2). W2-P2's
       default-map stun-rod staging: H gets a STR_STUN_ROD (battle_give,
       BOTH), H on C5_H_TILE, A on C5_A_TILE, H tu TU_MAX (BOTH). Host real
       UI: TAB-select H, the right-hand box (ActionMenuState), set_seed
       SEED_C5, key 52 (STUN): A UNCONSCIOUS, body item C5_BODY_ID. Then
       battle_set_unit_state {unit A, stun 0} on BOTH, and one full END TURN
       cycle (no seed). A wakes up inside the PLAYER -> HOSTILE side change
       (SavedBattleGame::reviveUnconsciousUnits via newTurnUpdateScripts,
       F863).
       GREEN: exactly one `revive` ev {unit A, pos C5R_A_TILE}, actionId 0,
       seq lower than the cycle's first side_transition; A STANDING and on
       its tile on both; its body item absent on both.
       RED (TASK 0d): no `revive` ev - the revive rides side_transition seq
       8's delta (itemsRemoved [C5_BODY_ID], A status 0 / onTile).
  C10  fall (cycle 2, turn 2 -> 3). U on C10_TILE, the barn loft floor
       (BOTH), battle_set_tile {C10_TILE, fire 1} on BOTH; one full cycle (no
       seed). The floor burns out at NEUTRAL -> PLAYER; U falls one level in
       the player-side think() after that side_transition (F864).
       GREEN: exactly one `fall` ev {units [{unit U, from C10_TILE}]},
       actionId 0, after the cycle's last side_transition, followed by a
       `sync` whose delta (host deltaRing entry) has units >= 1; U on
       C10_BELOW on both; C10_TILE's floor part equal on both (burnt out).
       RED (TASK 0d): no `fall` ev - the fall rides (reveal 0)(sync 0).
  C13a panic + flee (cycle 3, turn 3 -> 4; player turn 2 already reached).
       C2 gets a loaded STR_RIFLE (battle_give clear_hands, BOTH), C2 on
       C13_C2_TILE (BOTH), battle_set_unit_state {unit C2, morale 0} on BOTH
       (the S-D.1 lever field) before the END TURN; host set_seed SEED_C13A
       right before its press. The morale roll runs at NEUTRAL -> PLAYER
       (BattleUnit::prepareMorale; xcom1 armors define no morale recovery,
       so morale 0 = a 100% panic chance, F866); SEED_C13A picks panic (not
       berserk) and a flee with a path. The host shows its own panic infobox
       (F425): the host dismisses it (dismiss_popup, host only) when it is on
       top.
       GREEN: exactly one new host context {origin panic, actorId C2,
       nestedIn 0, hasFinal true}; its evs are exactly panic {unit C2, mode
       flee} -> >= 1 walk_step -> bt_action_end; the host's lastWalk is that
       walk (unit C2, origin panic, its steps = those walk_step seqs, the
       executed path ending on C13A_DEST); both machines' lastWalk carry that
       action and the end's path (the completion restate); C2's rifle on
       C13_C2_TILE with owner -1 on both; C2 on C13A_DEST, STANDING, TU 0 and
       morale 15 (the panic's end: +15) on both.
       RED (TASK 0d / F867): no `panic` ev, no context, no `walk_step` - the
       whole flee rides one `sync`.
  C13b berserk (cycle 4, turn 4 -> 5). The same staging (a new rifle, C2
       back on C13_C2_TILE, morale 0 on BOTH), host set_seed SEED_C13B.
       SEED_C13B picks berserk; C2 sees no enemy and fires at random tiles.
       GREEN: exactly one new host context {origin panic, actorId C2,
       nestedIn 0, hasFinal true}; its evs are panic {unit C2, mode berserk}
       -> >= 1 shot (every shot's actor C2), `hit`s -> bt_action_end; C2
       STANDING, TU 0, morale 15, still holding its rifle on both; no other
       unit's health/stun/status changed.
       RED (TASK 0d / F867): no `panic` ev, the shots and hits carry actionId
       0, a `sync` closes the burst.
  C9   burning-map turn cycle (cycles 5 and 6, turn 5 -> 7; revisit rows 5
       and 7, F144). C2's morale back to 100 on BOTH first (morale 15 after
       C13b = a 70% panic chance at every player side start). H gets a
       STR_ROCKET_LAUNCHER + STR_INCENDIARY_ROCKET (BOTH), H on C9_H_TILE, tu
       TU_MAX (BOTH); host set_seed SEED_C9, battle_fire {aimed, C9_TARGET}
       (the rocket lands on C9_EXPLOSION_TILE, F868). Then U_FIRE on the
       burning C9_FIRE_UNIT_TILE, U_STUN stun C9_STUN, battle_set_tile
       {C9_EXTRA_FIRE_TILE, fire 1} (all BOTH). Two full cycles, host
       set_seed SEED_C9 right before each host END TURN press.
       GREEN = RED (section (b)14: every burning-cycle field already rides the
       delta and wave 1's perUnit; C9 passes on the red commit too): after
       each boundary the 9x9 window around C9_TARGET plus C9_EXTRA_FIRE_TILE
       (tile_info fire, smoke, floor, object) is equal on both and at least
       one tile's fire/smoke changed; U_FIRE's health fell (equal on both);
       U_STUN's stun fell (equal on both); >= 1 floor burnt out since the
       start (equal on both); all buckets equal.

Common asserts (spec (f) as amended by B1 RQ5, per scenario, after its
chain settled): W2-P2's common asserts (hash_now {full:true} ALL buckets
EQUAL; desyncSeen false on both; client coopClientBStatePushes unchanged and
host 0; client deltaEvsApplied increased; deltaUnresolved, deltaUnsupported,
deltaRemoveMissing, deltaAddExisting 0 on both; lever-made items created on
BOTH with equal ids; staging writes on BOTH with equal responses); host
contextBeginRefused 0; contextsOpened grew by exactly the number of contexts
the scenario closed; every chain ev carries the id of a context the scenario
closed - except `fall`, `revive` and `spawn`, which open no context and carry
actionId 0 outside a chain (section (b)1); every context has exactly one
bt_action_end, its last ev, recorded in closedContexts (endSeq); no `sync`
and no side_transition inside a context; every side_transition carries
actionId 0; the client log holds the host's seqs/kinds/actionIds.
contextsClosedAtEndTurn is a diagnostic (printed, never asserted, RQ5).

Probes: event_state closedContexts, contextsOpened, contextBeginRefused,
contextsClosedAtEndTurn, cueCounts, deltaRing (the host's attached deltas by
seq), lastWalk (both machines), the W2-P2 delta counters; battle_state units
(status, onTile, tu, morale, health, stun, unitFire, position), turn, side,
panicHandled, pendingStates; battle_items (owner, slot, tile, unitLink);
tile_info (parts, fire, smoke); the host's own `[coop-cue] <kind> seq <n>
actionId <id>: <payload>` log line for the cue payloads (event_log carries
no payload); hash_now {full:true}. The lever: battle_set_unit_state {morale}
(commit S-D.1; BattleUnit::coopSetMorale, absorbed on the host).

Bring-up (deterministic, never searched here; ledger `## W2-P3 TASK 0b`
"Common bring-up", scratch w2p3/T0b/constants.md, and the S-D red precalc
(scratch w2p3/SD/red): SEED_C13A tried 1 (berserk), 2 (panic + flee: met);
SEED_C13B tried 1 (berserk, 6 shots: met); the combined order proven on 3
boots, identical chains, cues, deltas, snapshots and outcomes): set_seed
SEED_ROSTER on the HOST right before its open_new_battle; the DEFAULT NEW
BATTLE map with set_seed SEED_MAP right before newbattle_ok, seat_count=2,
MAP_FP asserted on both; the unit order UNIT_ORDER and the 60 start items
asserted; session.pin_ai_neutral (pins A). Every lever pair applies to the
CLIENT first, then the HOST (F607). The seeds are set on the HOST
immediately before the press that starts the chain.

RED-THEN-GREEN (spec (d) row S-D). Commit S-D.1 (this file + the `morale`
lever field; product behaviour unchanged) is run ONCE: C5r, C10, C13a and
C13b must FAIL with the RED above and C9 must PASS (section (b)14); commit
S-D.2 (the panic context and flee walk chain, the `fall`/`revive`/`panic`
cues) is run ONCE and all five must PASS. Each scenario prints ONE
"EVIDENCE <id>:" line with both machines' fields BEFORE its green conditions
are checked; main() runs every scenario even after an earlier one failed and
prints "PASS <id>" / "FAIL <id>: <message>". Every wait is bounded; a wait
that times out is recorded in the EVIDENCE line and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all five scenarios pass, 2
otherwise (a bring-up failure is also 2). WV-D95: run in the foreground to
completion.

Run:  python tools/coop_test/test_w2_turn_cues.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_rw_turn_baton import dismiss_next_turn_if_present
from test_w2_delta_core import (probes, diff_buckets, desync_record, short, both, tele_both, set_tile_both, tile,
                                floor_of, settle_on_battlescape, common_fails, finish, delta_view)
from test_w2_host_combat import (evs_since, ev_tuples, cue_probes, cue_delta, open_hand_menu_host, press,
                                 KEY_ITEM4, host_chain_done)
from test_w2_ai_origins import (host_payloads, ctx_probes, new_closed, opened_delta, ctx_of, ctx_view, sv, by_seq,
                                bring_up_lobby_roster_pinned)
from test_w2_unit_spawn import ring_of, ring_at, ring_view

# ----- bring-up (W2-P3 TASK 0b, ledger `## W2-P3 TASK 0b`, T0b constants.md "Common bring-up") -----
SEED_ROSTER = 1                  # set_seed on the HOST right before its open_new_battle (F501)
SEED_MAP = 1                     # set_seed in pre_ok right before newbattle_ok; DEFAULT NEW BATTLE (no mission)
MAP_FP = -4.48310638993e+18      # host AND client battle_state.mapFingerprint (STR_UFO_GROUND_ASSAULT, small scout)
SEATED = [8, 9]                  # the client seat's soldiers
A_ID = 1000000                   # the only alien, pinned by session.pin_ai_neutral (tu 0 + refill, reactions 0)
UNIT_ORDER = [8, 9, 10, 11, 12, 13, 14, 1000000]   # battle_state.units order = _units order
FIRST_LEVER_ITEM_ID = 60         # 60 items at start (ids 0..59): the first lever-made item is 60
PORT = "48636"
TU_MAX = 255                     # battle_set_unit_state tu: clamped to the unit's max TU
FACTION_PLAYER = 0
STATUS_STANDING, STATUS_UNCONSCIOUS, STATUS_PANICKING, STATUS_BERSERK = 0, 7, 8, 9   # src/Mod/Unit.h UnitStatus

# ----- C5r (T0b constants.md "C5r"; F863) -----
H_ID = 10                        # host seat soldier (the stun rod in C5r, the rocket in C9)
C5_H_TILE, C5_H_DIR = (4, 4, 0), 0
C5_A_TILE, C5_A_DIR = (4, 3, 0), 4
SEED_C5 = 1                      # host set_seed right before key 52 (STUN): A UNCONSCIOUS, stun 120
C5_ROD_ID = 60                   # battle_give {unit H, STR_STUN_ROD, clear_hands} on both
C5_BODY_ID = 61                  # STR_SECTOID_CORPSE, unitLink A (A's body while unconscious)
C5R_A_TILE = (4, 3, 0)           # A wakes up on its own tile inside the cycle's PLAYER -> HOSTILE change

# ----- C10 (T0b constants.md "C10"; F864) -----
U_ID, U_DIR = 11, 2              # host seat soldier, teleported onto the loft
C10_TILE = (21, 14, 1)           # BARN #2 loft floor (flammable 100, die MCD 0); burns out at NEUTRAL -> PLAYER
C10_BELOW = (21, 14, 0)          # the empty tile below = U's landing tile
C10_FLOOR_PRE = (2, 2)           # tile_info floor part (mapDataSetID, mapDataID) before the cycle
C10_FLOOR_AFTER = (-1, -1)       # burnt out: no floor part

# ----- C13a / C13b (T0b staging; the S-D red precalc's morale-route seeds) -----
C2_ID = 9                        # client seat soldier
C13_C2_TILE, C13_C2_DIR = (6, 34, 0), 0   # open field, > 20 tiles from A (C2 sees no enemy)
SEED_C13A = 2                    # host set_seed right before its END TURN press: panic + flee
C13A_RIFLE_ID, C13A_CLIP_ID = 62, 63
C13A_DEST = (8, 36, 0)           # the flee's end tile
SEED_C13B = 1                    # host set_seed right before its END TURN press: berserk, 6 random auto shots
C13B_RIFLE_ID, C13B_CLIP_ID = 64, 65
# W2-P5 S-T (owner D151 = (b); amendment E3.1 ST3 = (a), OR3 (a); TASK 0 T0-S5, F1590, 3 boots identical): C2's
# berserk turns animate - each berserk iteration that must turn (0 -> 7, 7 -> 6, 6 -> 2) emits one `turn` ev in
# the panic context before its burst; the third turns 4 octants with no TU left and fires nothing.
C13B_TURNS = 3
C13B_KINDS = ["panic", "turn", "shot", "hit", "shot", "hit", "shot", "hit", "turn", "shot", "shot", "hit", "shot",
              "hit", "turn", "bt_action_end"]
MORALE_AFTER_PANIC = 15          # UnitPanicBState: moraleChange(+15) when the panic ends

# ----- C9 (T0b constants.md "C9"; F868) -----
U_FIRE, U_STUN = 11, 12
C9_H_TILE, C9_H_DIR = (25, 38, 0), 0
C9_TARGET = (25, 33, 0)
SEED_C9 = 1                      # host set_seed before the rocket AND right before each of the two host END TURNs
C9_LAUNCHER_ID, C9_ROCKET_ID = 66, 67
C9_EXPLOSION_TILE = (24, 34, 0)  # the incendiary rocket's centre tile (one tile off the aim, F868)
C9_FIRE_UNIT_TILE, C9_FIRE_UNIT_DIR = (25, 33, 0), 0   # burning after the rocket; U_FIRE teleported onto it
C9_STUN = 10                     # battle_set_unit_state {unit U_STUN, stun} on both
C9_EXTRA_FIRE_TILE = (2, 6, 0)   # battle_set_tile {fire 1} on both; its floor burns out in cycle 5
C9_WINDOW = [(x, y, 0) for x in range(C9_TARGET[0] - 4, C9_TARGET[0] + 5)
             for y in range(C9_TARGET[1] - 4, C9_TARGET[1] + 5)] + [C9_EXTRA_FIRE_TILE]

# The ev kinds a named chain emits (the combat cues, the W2-P3 cues and the
# wave-1 action kinds); `sync`, `reveal`, `side_*`, `door` and `spot` are not
# chain evs here. `fall`, `revive` and `spawn` open no context (spec (b)1):
# outside a chain they carry actionId 0.
CHAIN_KINDS = ("turn", "walk_step", "kneel", "shot", "hit", "explosion", "melee", "psi", "death", "corpse",
               "prime", "fall", "revive", "spawn", "panic", "prox_trigger", "medikit", "scanner")
CONTEXTLESS_KINDS = ("fall", "revive", "spawn")
PAYLOAD_KINDS = ("revive", "fall", "panic", "shot", "hit", "explosion", "melee", "death", "corpse", "spawn")
UNIT_KEYS = ("x", "y", "z", "direction", "status", "isOut", "onTile", "tu", "health", "stun", "morale",
             "unitFire", "faction")


# ===================== small probes =====================


def units(gc):
    return session.units_by_id(battle_state(gc))


def items(gc):
    """battle_items as {id: the full item record} (every BattleItem this machine holds)."""
    r = gc.cmd({"cmd": "battle_items"})
    assert r.get("ok"), f"battle_items failed on {gc.name}: {r}"
    return {it["id"]: it for it in r.get("items", [])}


def xyz(u):
    return (u.get("x"), u.get("y"), u.get("z")) if u else None


def as_tile(p):
    """A payload position ({x,y,z} or [x,y,z]) as a tuple."""
    if isinstance(p, dict):
        return (p.get("x"), p.get("y"), p.get("z"))
    if isinstance(p, (list, tuple)) and len(p) == 3:
        return tuple(p)
    return None


def uview(u):
    if not u:
        return None
    return {k: u.get(k) for k in UNIT_KEYS}


def iview(it):
    if not it:
        return None
    return {k: it.get(k) for k in ("type", "owner", "slot", "onTile", "tx", "ty", "tz", "unitLink")}


def item_tile(it):
    return (it.get("tx"), it.get("ty"), it.get("tz")) if it else None


def st_seqs(evs):
    return [e["seq"] for e in evs if e["kind"] == "side_transition"]


def payload(rec, e):
    return (rec["pl"].get(e["seq"]) or {}).get("payload") or {}


def walk_view(w):
    w = w or {}
    r = w.get("restate") or {}
    return {"actionId": w.get("actionId"), "unit": w.get("unit"), "origin": w.get("origin"),
            "active": w.get("active"), "stepSeqs": [s.get("seq") for s in (w.get("steps") or [])],
            "executed": [as_tile(p) for p in (w.get("executed") or [])], "plannedLen": w.get("plannedLen"),
            "restate": {"halted": r.get("halted"), "reason": r.get("reason"),
                        "path": [as_tile(p) for p in (r.get("path") or [])]}}


# ===================== driving =====================


def host_idle_now(host, rec, extra=None):
    """HOST only: a vanilla infobox on top is dismissed (host only, F425) and
    recorded, a NextTurnState on top is closed through its real close(); True
    when BattlescapeState is on top with the panic check done, no BState
    queued or running, no action context open (busyOwnerSeat -1) and `extra`
    (a predicate on battle_state) holds."""
    lw = host.cmd({"cmd": "list_widgets"}).get("state", "")
    if "Infobox" in lw:
        rec["dismissed"].append((lw.split(">")[-1], host.cmd({"cmd": "dismiss_popup"}).get("handled")))
        return False
    if "NextTurnState" in lw:
        dismiss_next_turn_if_present(host)
        return False
    bs = battle_state(host)
    ok = (session.top_state(host) == "BattlescapeState" and bs.get("panicHandled")
          and bs.get("pendingStates") == 0 and not bs.get("isBusy")
          and event_state(host).get("busyOwnerSeat") == -1)
    return bool(ok and (extra is None or extra(bs)))


def settle_host(host, rec, extra=None, timeout=30, hold=0.6):
    """host_idle_now() held for `hold` seconds (the panic check runs in the
    think() after BattlescapeState::init(), one frame after a NextTurnState
    or an infobox pops); bounded."""
    deadline = time.time() + timeout
    since = None
    while time.time() < deadline:
        if host_idle_now(host, rec, extra):
            since = since or time.time()
            if time.time() - since >= hold:
                return
        else:
            since = None
        time.sleep(0.05)
    bs = battle_state(host)
    raise TimeoutError(f"host not settled within {timeout}s: top={session.top_state(host)} panicHandled="
                       f"{bs.get('panicHandled')} pendingStates={bs.get('pendingStates')} isBusy={bs.get('isBusy')}")


def cycle(host, client, seed, rec, what, extra=None, timeout=90):
    """Both machines press END TURN (the client first; the host presses once it
    paints END TURN 1/2, with set_seed `seed` on the HOST right before its
    press when `seed` is not None), then the full side cycle back to the
    player side: NextTurnStates closed through their real close() on both
    machines, the host's own infoboxes dismissed (host only, F425), the host
    settled (settle_host with `extra`), the client on BattlescapeState, the
    host idle with the client caught up. Every wait is bounded; a timeout is
    recorded in rec["notes"]. Appends the cycle's record to rec["cycles"]."""
    turn0 = battle_state(host).get("turn")
    seq_before = event_state(host).get("lastSeqEmitted") or 0
    try:
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        host.wait_for("host paints END TURN 1/2 after the client's press",
                      lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2" or None, timeout=20)
        if seed is not None:
            host.ok({"cmd": "set_seed", "seed": seed})
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        deadline = time.time() + timeout
        while True:
            lw = host.cmd({"cmd": "list_widgets"}).get("state", "")
            if "Infobox" in lw:
                rec["dismissed"].append((lw.split(">")[-1], host.cmd({"cmd": "dismiss_popup"}).get("handled")))
            if "NextTurnState" in lw:
                dismiss_next_turn_if_present(host)
            dismiss_next_turn_if_present(client)
            hs, cs = battle_state(host), battle_state(client)
            if (hs.get("side") == FACTION_PLAYER and hs.get("turn", -1) >= turn0 + 1
                    and cs.get("side") == FACTION_PLAYER and cs.get("turn", -1) >= turn0 + 1):
                break
            if time.time() > deadline:
                raise TimeoutError(f"the cycle did not reach player turn {turn0 + 1} on both within {timeout}s: "
                                   f"host=({hs.get('turn')},{hs.get('side')}) client=({cs.get('turn')},"
                                   f"{cs.get('side')})")
            time.sleep(0.05)
        settle_host(host, rec, extra)
        settle_on_battlescape(client)
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        rec["notes"].append(f"{what}: {short(e)}")
    hs, cs = battle_state(host), battle_state(client)
    rec["cycles"].append({"what": what, "seed": seed, "turn0": turn0, "seqBefore": seq_before,
                          "host": (hs.get("turn"), hs.get("side")), "client": (cs.get("turn"), cs.get("side"))})


def begin(host, client):
    """A scenario's record: the probes before its first staging write."""
    before = {"host": probes(host), "client": probes(client)}
    return {"before": before, "cb": {"host": ctx_probes(host), "client": ctx_probes(client)},
            "kb": {"host": cue_probes(host), "client": cue_probes(client)},
            "seq0": before["host"]["lastSeqEmitted"] or 0, "notes": [], "dismissed": [], "cycles": []}


def end(host, client, rec):
    """Everything the scenario's checks read, after its chain settled."""
    ph, pc = probes(host), probes(client)
    ca = {"host": ctx_probes(host), "client": ctx_probes(client)}
    hev, cev = evs_since(host, rec["seq0"]), evs_since(client, rec["seq0"])
    rec.update({"ph": ph, "pc": pc, "ca": ca, "ka": {"host": cue_probes(host), "client": cue_probes(client)},
                "hev": hev, "cev": cev,
                "pl": host_payloads(host, [e["seq"] for e in hev if e["kind"] in PAYLOAD_KINDS]),
                "ring": ring_of(host), "uh": units(host), "uc": units(client), "ih": items(host),
                "ic": items(client), "hw": session.last_walk(host), "cw": session.last_walk(client),
                "closed": new_closed(rec["cb"]["host"], ca["host"]),
                "opened": opened_delta(rec["cb"]["host"], ca["host"]),
                "diff": diff_buckets(host, client), "desync": desync_record(client, pc["desyncSeen"])})
    return rec


# ===================== evidence =====================


def rec_evidence(rec):
    ph, pc = rec["ph"], rec["pc"]
    cb, ca = rec["cb"]["host"], rec["ca"]["host"]
    cues = [(e["seq"], e["kind"], e["actionId"], payload(rec, e)) for e in rec["hev"] if e["kind"] in PAYLOAD_KINDS]
    ring = [ring_view(r) for r in (rec["ring"] or []) if (r.get("seq") or 0) > rec["seq0"]]
    desync = rec["desync"] and {k: rec["desync"].get(k) for k in ("bucket", "seq")}   # F888: never the kind label
    return (f"cycles={rec['cycles']}; host evs since seq {rec['seq0']}={ev_tuples(rec['hev'])} client evs="
            f"{ev_tuples(rec['cev'])} (seq, kind, actionId, h); host cues (seq, kind, actionId, payload)={cues}; "
            f"host deltaRing since seq {rec['seq0']}={ring}; closedContexts(new, host)="
            f"{[ctx_view(c) for c in rec['closed']]} kinds={[c.get('kind') for c in rec['closed']]}; "
            f"contextsOpened delta(host)={rec['opened']}; contextsClosedAtEndTurn(host, diagnostic)="
            f"{cb['contextsClosedAtEndTurn']}->{ca['contextsClosedAtEndTurn']}; contextBeginRefused(host)="
            f"{ca['contextBeginRefused']}; armingDeferrals(host)={cb['armingDeferrals']}->{ca['armingDeferrals']}; "
            f"cueCounts delta host={cue_delta(rec['kb']['host']['cueCounts'], rec['ka']['host']['cueCounts'])} "
            f"client={cue_delta(rec['kb']['client']['cueCounts'], rec['ka']['client']['cueCounts'])}; lastWalk "
            f"host={walk_view(rec['hw'])} client={walk_view(rec['cw'])}; diff={rec['diff']}; desyncSeen host="
            f"{ph['desyncSeen']} client={pc['desyncSeen']} desync(bucket, seq)={desync}; host "
            f"{delta_view(rec['before']['host'])}->{delta_view(ph)}; client {delta_view(rec['before']['client'])}"
            f"->{delta_view(pc)}; host lastDelta={ph['lastDelta']} client lastDelta={pc['lastDelta']}; infoboxes "
            f"dismissed(host)={rec['dismissed']}; notes={rec['notes']}")


def units_evidence(rec, ids):
    return {uid: {"host": uview(rec["uh"].get(uid)), "client": uview(rec["uc"].get(uid))} for uid in ids}


def items_evidence(rec, ids):
    return {iid: {"host": iview(rec["ih"].get(iid)), "client": iview(rec["ic"].get(iid))} for iid in ids}


# ===================== common checks =====================


def cycle_fails(rec, what):
    """Every cycle of the scenario ended on player turn turn0 + 1 on both."""
    fails = []
    for c in rec["cycles"]:
        want = (c["turn0"] + 1, FACTION_PLAYER)
        if c["host"] != want or c["client"] != want:
            fails.append(f"{what}: {c['what']} ended host (turn, side)={c['host']} client={c['client']} (want "
                         f"{want} on both)")
    return fails


def context_fails(rec, what):
    """Spec (f) common asserts on the context side (B1 RQ5), over the host evs
    of one scenario: contextBeginRefused 0 on the host; contextsOpened grew by
    exactly the number of contexts closed; every chain ev carries the id of a
    context this scenario closed (a `fall`/`revive`/`spawn` may carry 0:
    they open no context); every actionId has exactly one bt_action_end, its
    last ev, recorded in closedContexts with endSeq = its seq; no `sync` and
    no side_transition inside a context; a nested context ends before its
    base; every side_transition carries actionId 0; the client log holds the
    host's seq/kind/actionId for every ev of every context."""
    fails = []
    hev, cev, closed = rec["hev"], rec["cev"], rec["closed"]
    ca = rec["ca"]["host"]
    if ca["contextBeginRefused"] != 0:
        fails.append(f"{what}: host contextBeginRefused={ca['contextBeginRefused']} (want 0)")
    n_open = sum(rec["opened"].values())
    if n_open != len(closed):
        fails.append(f"{what}: host contextsOpened +{n_open} {rec['opened']} but closedContexts +{len(closed)} "
                     f"(want every context the scenario opened closed and recorded)")
    ids = {c.get("actionId") for c in closed}
    for e in hev:
        if e["kind"] == "side_transition" and e["actionId"] != 0:
            fails.append(f"{what}: side_transition seq {e['seq']} carries actionId {e['actionId']} (want 0)")
        if e["kind"] in CHAIN_KINDS and not (e["actionId"] == 0 and e["kind"] in CONTEXTLESS_KINDS):
            if not e["actionId"] or e["actionId"] not in ids:
                fails.append(f"{what}: {e['kind']} seq {e['seq']} carries actionId {e['actionId']} (want the id "
                             f"of a context this scenario closed: {sorted(ids)})")
    cmap = by_seq(cev)
    syncs = [e["seq"] for e in hev if e["kind"] == "sync"]
    sts = st_seqs(hev)
    for aid in sorted({e["actionId"] for e in hev if e["actionId"]}):
        evs = [e for e in hev if e["actionId"] == aid]
        kinds = [e["kind"] for e in evs]
        if kinds.count("bt_action_end") != 1 or kinds[-1] != "bt_action_end":
            fails.append(f"{what}: context {aid} evs {sv(evs)} (want exactly one bt_action_end, its last ev)")
        c = ctx_of(closed, aid)
        if not c:
            fails.append(f"{what}: context {aid} (evs {sv(evs)}) is not in the host's closedContexts (new entries "
                         f"{[ctx_view(x) for x in closed]})")
        elif c.get("endSeq") != evs[-1]["seq"]:
            fails.append(f"{what}: closedContexts {ctx_view(c)} endSeq != its last ev seq {evs[-1]['seq']}")
        lo, hi = evs[0]["seq"], evs[-1]["seq"]
        inside = [s for s in syncs if lo < s < hi]
        if inside:
            fails.append(f"{what}: `sync` seq(s) {inside} inside context {aid} ({sv(evs)}) (want none)")
        span = [s for s in sts if lo < s < hi]
        if span:
            fails.append(f"{what}: context {aid} ({lo}..{hi}) spans side_transition seq(s) {span} (want its "
                         f"bt_action_end before the next side_transition)")
        bad = [(e["seq"], e["kind"], cmap.get(e["seq"]) and (cmap[e["seq"]]["kind"], cmap[e["seq"]]["actionId"]))
               for e in evs if not cmap.get(e["seq"]) or cmap[e["seq"]]["kind"] != e["kind"]
               or cmap[e["seq"]]["actionId"] != aid]
        if bad:
            fails.append(f"{what}: client event_log does not hold the host's evs of context {aid}: "
                         f"(seq, host kind, client (kind, actionId))={bad}")
    for c in closed:
        ends = [e["seq"] for e in hev if e["actionId"] == c.get("actionId") and e["kind"] == "bt_action_end"]
        if ends != [c.get("endSeq")]:
            fails.append(f"{what}: closedContexts {ctx_view(c)} - its bt_action_end seq(s) in the host log = {ends} "
                         f"(want exactly [endSeq])")
        if c.get("nestedIn"):
            base = ctx_of(closed, c.get("nestedIn"))
            if not base or not (c.get("endSeq") or 0) < (base.get("endSeq") or 0):
                fails.append(f"{what}: nested {ctx_view(c)} does not end before its base {ctx_view(base)}")
    return fails


def held_by_client(rec, e):
    ce = by_seq(rec["cev"]).get(e["seq"])
    return bool(ce and ce["kind"] == e["kind"] and ce["actionId"] == e["actionId"])


def panic_context_fails(rec, mode, what):
    """Exactly one new host context {origin panic, actorId C2, nestedIn 0,
    hasFinal true}; its evs start with panic {unit C2, mode} and end with its
    bt_action_end. Returns (fails, the context or None, its evs)."""
    fails = []
    pcs = [c for c in rec["closed"] if c.get("origin") == "panic"]
    panics = [e for e in rec["hev"] if e["kind"] == "panic"]
    if len(pcs) != 1:
        fails.append(f"{what}: host closedContexts with origin panic = {[ctx_view(c) for c in pcs]} (want exactly "
                     f"one: {{origin panic, actorId {C2_ID}}}; new entries {[ctx_view(c) for c in rec['closed']]})")
    if len(panics) != 1:
        fails.append(f"{what}: `panic` evs in the host log {sv(panics)} (want exactly one: panic {{unit {C2_ID}, "
                     f"mode {mode}}})")
    c = pcs[0] if len(pcs) == 1 else None
    evs = [e for e in rec["hev"] if c and e["actionId"] == c.get("actionId")]
    if c and (c.get("actorId"), c.get("nestedIn"), c.get("hasFinal")) != (C2_ID, 0, True):
        fails.append(f"{what}: the panic context {ctx_view(c)} (want actorId {C2_ID}, nestedIn 0, hasFinal true)")
    if c and (not evs or evs[0]["kind"] != "panic" or evs[-1]["kind"] != "bt_action_end"):
        fails.append(f"{what}: the panic context {c.get('actionId')} evs {sv(evs)} (want the panic cue first and "
                     f"its bt_action_end last)")
    if panics:
        p = payload(rec, panics[0])
        if (p.get("unit"), p.get("mode")) != (C2_ID, mode):
            fails.append(f"{what}: panic seq {panics[0]['seq']} payload {p or None} (want unit {C2_ID}, mode {mode})")
        if c and panics[0]["actionId"] != c.get("actionId"):
            fails.append(f"{what}: panic seq {panics[0]['seq']} carries actionId {panics[0]['actionId']} (want the "
                         f"panic context {c.get('actionId')})")
        if not held_by_client(rec, panics[0]):
            fails.append(f"{what}: the client log does not hold panic seq {panics[0]['seq']}")
    return fails, c, evs


def c2_state_fails(rec, want, what):
    fails = []
    for name, u in (("host", rec["uh"].get(C2_ID)), ("client", rec["uc"].get(C2_ID))):
        got = {k: (xyz(u) if k == "pos" else (u or {}).get(k)) for k in want}
        if got != want:
            fails.append(f"{what}: C2 on the {name} {got} (want {want})")
    return fails


# ===================== scenarios =====================


def c5r_revive(host, client, ctx):
    rec = begin(host, client)
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": "STR_STUN_ROD", "clear_hands": True},
             ("weaponId", "ammoId"))
    tele_both(host, client, H_ID, C5_H_TILE, C5_H_DIR)
    tele_both(host, client, A_ID, C5_A_TILE, C5_A_DIR)
    both(host, client, {"cmd": "battle_set_unit_state", "unit": H_ID, "tu": TU_MAX}, ("tu",))
    staged_diff = diff_buckets(host, client)
    try:
        open_hand_menu_host(host)
        host.ok({"cmd": "set_seed", "seed": SEED_C5})
        press(host, KEY_ITEM4)
        host.wait_for("host stun chain finished", lambda: host_chain_done(host, A_ID, STATUS_UNCONSCIOUS), timeout=30)
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        rec["notes"].append(f"stun: {short(e)}")
    uh1, uc1 = units(host), units(client)
    ih1, ic1 = items(host), items(client)
    stunned = {"A": {"host": uview(uh1.get(A_ID)), "client": uview(uc1.get(A_ID))},
               "body": {"host": sorted(i for i, it in ih1.items() if it.get("unitLink") == A_ID),
                        "client": sorted(i for i, it in ic1.items() if it.get("unitLink") == A_ID)}}
    s0 = both(host, client, {"cmd": "battle_set_unit_state", "unit": A_ID, "stun": 0}, ("stun", "status"))
    cycle(host, client, None, rec, "cycle 1")
    end(host, client, rec)
    hev = rec["hev"]
    c1 = rec["cycles"][0]["seqBefore"] if rec["cycles"] else rec["seq0"]
    sts = [s for s in st_seqs(hev) if s > c1]
    st1 = sts[0] if sts else None
    revs = [e for e in hev if e["kind"] == "revive"]
    st1_ring = ring_view(ring_at(rec["ring"], st1)) if st1 else None
    print(f"EVIDENCE C5r: rod={g.get('weaponId')} H {C5_H_TILE}/{C5_H_DIR} A {C5_A_TILE}/{C5_A_DIR} stagedDiff="
          f"{staged_diff}; after the stun (seed {SEED_C5})={stunned}; stun 0 response (stun, status)="
          f"{(s0.get('stun'), s0.get('status'))}; cycle side_transitions={sts}; revive evs="
          f"{[(e['seq'], e['actionId'], payload(rec, e)) for e in revs]}; the first side_transition's delta="
          f"{st1_ring}; units={units_evidence(rec, [A_ID, H_ID])}; body {C5_BODY_ID}="
          f"{items_evidence(rec, [C5_BODY_ID])}; {rec_evidence(rec)}", flush=True)
    fails = list(rec["notes"])
    if g.get("weaponId") != C5_ROD_ID:
        fails.append(f"battle_give H stun rod id {g.get('weaponId')} (want {C5_ROD_ID})")
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    for name in ("host", "client"):
        a = stunned["A"][name] or {}
        if a.get("status") != STATUS_UNCONSCIOUS or stunned["body"][name] != [C5_BODY_ID]:
            fails.append(f"precondition: after the stun A on the {name} {a} body {stunned['body'][name]} (want "
                         f"UNCONSCIOUS, body [{C5_BODY_ID}])")
    if s0.get("stun") != 0:
        fails.append(f"stun 0 staging response stun={s0.get('stun')} (want 0)")
    fails += cycle_fails(rec, "C5r")
    if st1 is None:
        fails.append(f"no side_transition in the cycle's host log (host evs {sv(hev)})")
    if len(revs) != 1:
        fails.append(f"`revive` evs in the host log {sv(revs)} (want exactly one: revive {{unit {A_ID}, pos "
                     f"{C5R_A_TILE}}} before the cycle's first side_transition seq {st1}; host evs {sv(hev)})")
    for e in revs[:1]:
        p = payload(rec, e)
        if e["actionId"] != 0:
            fails.append(f"revive seq {e['seq']} carries actionId {e['actionId']} (want 0: no context)")
        if st1 is None or not (c1 < e["seq"] < st1):
            fails.append(f"revive seq {e['seq']} is not inside the cycle before its first side_transition seq {st1}")
        if (p.get("unit"), as_tile(p.get("pos"))) != (A_ID, C5R_A_TILE):
            fails.append(f"revive seq {e['seq']} payload {p or None} (want unit {A_ID}, pos {C5R_A_TILE})")
        if not held_by_client(rec, e):
            fails.append(f"the client log does not hold revive seq {e['seq']}")
    for name, u in (("host", rec["uh"].get(A_ID)), ("client", rec["uc"].get(A_ID))):
        if not u or (u.get("status"), u.get("onTile"), xyz(u)) != (STATUS_STANDING, True, C5R_A_TILE):
            fails.append(f"A on the {name} after the cycle {uview(u)} (want STANDING, onTile true, on {C5R_A_TILE})")
    for name, its in (("host", rec["ih"]), ("client", rec["ic"])):
        if C5_BODY_ID in its:
            fails.append(f"A's body item {C5_BODY_ID} present on the {name} after the revive {iview(its[C5_BODY_ID])} "
                         f"(want absent)")
    fails += context_fails(rec, "C5r")
    fails += common_fails(host, client, rec["before"], {}, "C5r")
    finish(fails)


def c10_fall(host, client, ctx):
    rec = begin(host, client)
    t0h, t0c = tile(host, C10_TILE), tile(client, C10_TILE)
    tele_both(host, client, U_ID, C10_TILE, U_DIR)
    ft = set_tile_both(host, client, C10_TILE, fire=1)
    staged_diff = diff_buckets(host, client)
    cycle(host, client, None, rec, "cycle 2")
    end(host, client, rec)
    hev = rec["hev"]
    t1h, t1c = tile(host, C10_TILE), tile(client, C10_TILE)
    bh, bc = tile(host, C10_BELOW), tile(client, C10_BELOW)
    sts = st_seqs(hev)
    last_st = sts[-1] if sts else None
    falls = [e for e in hev if e["kind"] == "fall"]
    fall = falls[0] if falls else None
    after = [e for e in hev if e["kind"] == "sync" and fall and e["seq"] > fall["seq"]]
    sync_rings = [(e["seq"], ring_view(ring_at(rec["ring"], e["seq"]))) for e in hev if e["kind"] == "sync"]
    print(f"EVIDENCE C10: U={U_ID} -> {C10_TILE}/{U_DIR}; set_tile fire response={ft.get('fire')}; stagedDiff="
          f"{staged_diff}; C10_TILE before host={t0h} client={t0c} after host={t1h} client={t1c}; below after host="
          f"{bh} client={bc}; cycle side_transitions={sts}; fall evs="
          f"{[(e['seq'], e['actionId'], payload(rec, e)) for e in falls]}; syncs (seq, delta)={sync_rings}; units="
          f"{units_evidence(rec, [U_ID])}; {rec_evidence(rec)}", flush=True)
    fails = list(rec["notes"])
    if ft.get("fire") != 1:
        fails.append(f"battle_set_tile fire response {ft.get('fire')} (want 1)")
    if floor_of(t0h) != C10_FLOOR_PRE or floor_of(t0c) != C10_FLOOR_PRE:
        fails.append(f"precondition: C10_TILE floor before host={floor_of(t0h)} client={floor_of(t0c)} (want "
                     f"{C10_FLOOR_PRE})")
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    fails += cycle_fails(rec, "C10")
    if floor_of(t1h) != C10_FLOOR_AFTER or floor_of(t1c) != C10_FLOOR_AFTER:
        fails.append(f"C10_TILE floor after the cycle host={floor_of(t1h)} client={floor_of(t1c)} (want the burnt-out "
                     f"{C10_FLOOR_AFTER} on both)")
    for name, u in (("host", rec["uh"].get(U_ID)), ("client", rec["uc"].get(U_ID))):
        if xyz(u) != C10_BELOW:
            fails.append(f"U on the {name} at {xyz(u)} after the cycle (want {C10_BELOW}: one level down)")
    if len(falls) != 1:
        fails.append(f"`fall` evs in the host log {sv(falls)} (want exactly one: fall {{units [{{unit {U_ID}, from "
                     f"{C10_TILE}}}]}} after the side_transition seq {last_st}; host evs {sv(hev)})")
    if fall:
        p = payload(rec, fall)
        got = [(d.get("unit"), as_tile(d.get("from"))) for d in (p.get("units") or []) if isinstance(d, dict)]
        if fall["actionId"] != 0:
            fails.append(f"fall seq {fall['seq']} carries actionId {fall['actionId']} (want 0: no context)")
        if last_st is None or fall["seq"] < last_st:
            fails.append(f"fall seq {fall['seq']} precedes the cycle's last side_transition seq {last_st}")
        if got != [(U_ID, C10_TILE)]:
            fails.append(f"fall seq {fall['seq']} payload {p or None} (want units [{{unit {U_ID}, from {C10_TILE}}}])")
        if not held_by_client(rec, fall):
            fails.append(f"the client log does not hold fall seq {fall['seq']}")
        good = [e for e in after if ((ring_at(rec["ring"], e["seq"]) or {}).get("units") or 0) >= 1
                and held_by_client(rec, e)]
        if not good:
            fails.append(f"no `sync` after fall seq {fall['seq']} whose delta has units >= 1 (syncs after it "
                         f"{[(e['seq'], ring_view(ring_at(rec['ring'], e['seq']))) for e in after]})")
    fails += context_fails(rec, "C10")
    fails += common_fails(host, client, rec["before"], {}, "C10")
    finish(fails)


def c13_stage(host, client, rifle_id, clip_id, fails, what):
    """C2: a loaded STR_RIFLE (battle_give clear_hands), on C13_C2_TILE, morale
    0 - all on BOTH (client first)."""
    g = both(host, client, {"cmd": "battle_give", "unit": C2_ID, "item": "STR_RIFLE", "ammo": "STR_RIFLE_CLIP",
                            "clear_hands": True}, ("weaponId", "ammoId"))
    tele_both(host, client, C2_ID, C13_C2_TILE, C13_C2_DIR)
    m = both(host, client, {"cmd": "battle_set_unit_state", "unit": C2_ID, "morale": 0}, ("morale", "status"))
    if (g.get("weaponId"), g.get("ammoId")) != (rifle_id, clip_id):
        fails.append(f"{what}: battle_give C2 rifle/clip {(g.get('weaponId'), g.get('ammoId'))} (want "
                     f"{(rifle_id, clip_id)})")
    if m.get("morale") != 0:
        fails.append(f"{what}: morale staging response {m.get('morale')} (want 0)")
    return g, m


def c2_resolved(bs):
    """The host resolved C2's panic: C2 is no longer PANICKING/BERSERK."""
    return (session.units_by_id(bs).get(C2_ID) or {}).get("status") not in (STATUS_PANICKING, STATUS_BERSERK)


def c13a_flee(host, client, ctx):
    rec = begin(host, client)
    fails = []
    turn_at = battle_state(host).get("turn")
    g, m = c13_stage(host, client, C13A_RIFLE_ID, C13A_CLIP_ID, fails, "C13a")
    staged_diff = diff_buckets(host, client)
    staged = {"host": uview(units(host).get(C2_ID)), "client": uview(units(client).get(C2_ID))}
    cycle(host, client, SEED_C13A, rec, "cycle 3", extra=c2_resolved)
    end(host, client, rec)
    pfails, pc, pevs = panic_context_fails(rec, "flee", "C13a")
    walks = [e for e in pevs if e["kind"] == "walk_step"]
    c2_walks = [e for e in rec["hev"] if e["kind"] == "walk_step"]
    hw, cw = walk_view(rec["hw"]), walk_view(rec["cw"])
    print(f"EVIDENCE C13a: player turn at staging={turn_at}; C2 rifle={g.get('weaponId')} clip={g.get('ammoId')} "
          f"-> {C13_C2_TILE}/{C13_C2_DIR} morale response={m.get('morale')} staged={staged} stagedDiff={staged_diff}; "
          f"seed {SEED_C13A}; panic context={ctx_view(pc)} kind={pc and pc.get('kind')} its evs={sv(pevs)}; "
          f"walk_step evs in the scenario={sv(c2_walks)}; units={units_evidence(rec, [C2_ID])}; rifle="
          f"{items_evidence(rec, [C13A_RIFLE_ID])}; {rec_evidence(rec)}", flush=True)
    fails = list(rec["notes"]) + fails
    if not (turn_at or 0) >= 2:
        fails.append(f"precondition: battle turn {turn_at} at the staging (want player turn 2 reached)")
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    fails += cycle_fails(rec, "C13a")
    fails += c2_state_fails(rec, {"pos": C13A_DEST, "status": STATUS_STANDING, "tu": 0,
                                  "morale": MORALE_AFTER_PANIC}, "C13a")
    for name, it in (("host", rec["ih"].get(C13A_RIFLE_ID)), ("client", rec["ic"].get(C13A_RIFLE_ID))):
        if not it or (it.get("owner"), item_tile(it)) != (-1, C13_C2_TILE):
            fails.append(f"C13a: C2's rifle {C13A_RIFLE_ID} on the {name} {iview(it)} (want owner -1 on "
                         f"{C13_C2_TILE}: dropped by the flee)")
    fails += pfails
    if pc:
        kinds = [e["kind"] for e in pevs]
        if not walks or kinds != ["panic"] + ["walk_step"] * len(walks) + ["bt_action_end"]:
            fails.append(f"C13a: the panic context {pc.get('actionId')} evs {sv(pevs)} (want exactly panic -> >= 1 "
                         f"walk_step -> bt_action_end)")
        want_path = [C13A_DEST] if not hw["executed"] else hw["executed"]
        if (hw["actionId"], hw["unit"], hw["origin"], hw["active"]) != (pc.get("actionId"), C2_ID, "panic", False) \
                or hw["stepSeqs"] != [e["seq"] for e in walks] or not hw["executed"] \
                or hw["executed"][-1] != C13A_DEST:
            fails.append(f"C13a: host lastWalk {hw} (want actionId {pc.get('actionId')}, unit {C2_ID}, origin panic, "
                         f"inactive, steps = the walk_step seqs {[e['seq'] for e in walks]}, executed ending on "
                         f"{C13A_DEST})")
        for name, w in (("host", hw), ("client", cw)):
            if w["actionId"] != pc.get("actionId") or w["unit"] != C2_ID or not w["restate"]["path"] \
                    or w["restate"]["path"] != want_path:
                fails.append(f"C13a: {name} lastWalk actionId {w['actionId']} unit {w['unit']} end path "
                             f"{w['restate']['path']} (want the panic action {pc.get('actionId')}, unit {C2_ID}, the "
                             f"bt_action_end's path = the executed path {want_path})")
    elif not c2_walks:
        fails.append(f"C13a: no `walk_step` ev for C2's flee (want the flee walk streamed under the panic context)")
    fails += context_fails(rec, "C13a")
    fails += common_fails(host, client, rec["before"], {}, "C13a")
    finish(fails)


def c13b_berserk(host, client, ctx):
    rec = begin(host, client)
    fails = []
    g, m = c13_stage(host, client, C13B_RIFLE_ID, C13B_CLIP_ID, fails, "C13b")
    staged_diff = diff_buckets(host, client)
    uh0 = units(host)
    cycle(host, client, SEED_C13B, rec, "cycle 4", extra=c2_resolved)
    end(host, client, rec)
    pfails, pc, pevs = panic_context_fails(rec, "berserk", "C13b")
    shots = [e for e in rec["hev"] if e["kind"] == "shot"]
    others = {uid: {"before": (u.get("health"), u.get("stun"), u.get("status")),
                    "after": ((rec["uh"].get(uid) or {}).get("health"), (rec["uh"].get(uid) or {}).get("stun"),
                              (rec["uh"].get(uid) or {}).get("status"))}
              for uid, u in uh0.items() if uid != C2_ID}
    changed = {uid: v for uid, v in others.items() if v["before"] != v["after"]}
    turns = [e for e in pevs if e["kind"] == "turn"]
    tpl = host_payloads(host, [e["seq"] for e in turns]) if turns else {}
    turn_pl = [(e["seq"], (tpl.get(e["seq"]) or {}).get("payload")) for e in turns]
    print(f"EVIDENCE C13b: C2 rifle={g.get('weaponId')} clip={g.get('ammoId')} -> {C13_C2_TILE}/{C13_C2_DIR} morale "
          f"response={m.get('morale')} stagedDiff={staged_diff}; seed {SEED_C13B}; panic context={ctx_view(pc)} "
          f"kind={pc and pc.get('kind')} its evs={sv(pevs)}; turns (seq, [coop-turn] payload)={turn_pl}; "
          f"shots (seq, actionId, payload)="
          f"{[(e['seq'], e['actionId'], payload(rec, e)) for e in shots]}; other units changed={changed}; units="
          f"{units_evidence(rec, [C2_ID])}; rifle={items_evidence(rec, [C13B_RIFLE_ID])}; {rec_evidence(rec)}",
          flush=True)
    fails = list(rec["notes"]) + fails
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    fails += cycle_fails(rec, "C13b")
    if not shots or any(payload(rec, e).get("actor") != C2_ID for e in shots):
        fails.append(f"C13b: shot evs {[(e['seq'], payload(rec, e).get('actor')) for e in shots]} (want >= 1, every "
                     f"one fired by C2 {C2_ID})")
    if changed:
        fails.append(f"C13b: other units' (health, stun, status) changed {changed} (want none: the berserk shots hit "
                     f"no unit)")
    fails += c2_state_fails(rec, {"status": STATUS_STANDING, "tu": 0, "morale": MORALE_AFTER_PANIC}, "C13b")
    for name, it in (("host", rec["ih"].get(C13B_RIFLE_ID)), ("client", rec["ic"].get(C13B_RIFLE_ID))):
        if not it or it.get("owner") != C2_ID:
            fails.append(f"C13b: C2's rifle {C13B_RIFLE_ID} on the {name} {iview(it)} (want still owned by C2)")
    fails += pfails
    if pc:
        # W2-P5 S-T (E3.1 ST3 = (a)): the berserk turns are `turn` evs in the panic context (T0-S5's exact list).
        kinds = [e["kind"] for e in pevs]
        if kinds != C13B_KINDS or len(turns) != C13B_TURNS:
            fails.append(f"C13b: the panic context {pc.get('actionId')} evs {sv(pevs)} carry {len(turns)} `turn` "
                         f"ev(s) (want exactly {C13B_TURNS}: panic -> each berserk turn before its burst -> "
                         f"bt_action_end, exactly {C13B_KINDS})")
        bad = [(s, (p or {}).get("unit")) for s, p in turn_pl if (p or {}).get("unit") != C2_ID]
        if bad:
            fails.append(f"C13b: [coop-turn] payload units {bad} (want every berserk turn's unit C2 {C2_ID})")
    fails += context_fails(rec, "C13b")
    fails += common_fails(host, client, rec["before"], {}, "C13b")
    finish(fails)


def window(gc):
    """(fire, smoke, floor part, object part) per C9_WINDOW tile."""
    out = {}
    for t in C9_WINDOW:
        ti = tile(gc, t)
        out[t] = (ti["fire"], ti["smoke"], ti["parts"]["floor"], ti["parts"]["object"]) if ti else None
    return out


def snap(host, client):
    wh, wc = window(host), window(client)
    uh, uc = units(host), units(client)
    return {"wh": wh, "wc": wc, "uh": uh, "uc": uc, "diff": diff_buckets(host, client),
            "tdiff": sorted(t for t in wh if wh[t] != wc[t])}


def snap_view(s):
    wh = s["wh"]
    return {"burning": sum(1 for v in wh.values() if v and v[0]), "smoking": sum(1 for v in wh.values() if v and v[1]),
            "tileDiffs": s["tdiff"], "U_FIRE health h/c": ((s["uh"].get(U_FIRE) or {}).get("health"),
                                                           (s["uc"].get(U_FIRE) or {}).get("health")),
            "U_FIRE unitFire h/c": ((s["uh"].get(U_FIRE) or {}).get("unitFire"),
                                    (s["uc"].get(U_FIRE) or {}).get("unitFire")),
            "U_STUN stun h/c": ((s["uh"].get(U_STUN) or {}).get("stun"), (s["uc"].get(U_STUN) or {}).get("stun")),
            "extra": wh.get(C9_EXTRA_FIRE_TILE), "diff": s["diff"]}


def c9_burning(host, client, ctx):
    rec = begin(host, client)
    fails = []
    mr = both(host, client, {"cmd": "battle_set_unit_state", "unit": C2_ID, "morale": 100}, ("morale",))
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": "STR_ROCKET_LAUNCHER",
                            "ammo": "STR_INCENDIARY_ROCKET", "clear_hands": True}, ("weaponId", "ammoId"))
    tele_both(host, client, H_ID, C9_H_TILE, C9_H_DIR)
    both(host, client, {"cmd": "battle_set_unit_state", "unit": H_ID, "tu": TU_MAX}, ("tu",))
    s0 = snap(host, client)
    host.ok({"cmd": "set_seed", "seed": SEED_C9})
    fire = host.cmd({"cmd": "battle_fire", "unit": H_ID, "mode": "aimed", "x": C9_TARGET[0], "y": C9_TARGET[1],
                     "z": C9_TARGET[2]})
    if not fire.get("ok"):
        rec["notes"].append(f"battle_fire refused: {fire}")
    try:
        settle_host(host, rec)
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        rec["notes"].append(f"rocket: {short(e)}")
    s1 = snap(host, client)
    tele_both(host, client, U_FIRE, C9_FIRE_UNIT_TILE, C9_FIRE_UNIT_DIR)
    st = both(host, client, {"cmd": "battle_set_unit_state", "unit": U_STUN, "stun": C9_STUN}, ("stun",))
    ft = set_tile_both(host, client, C9_EXTRA_FIRE_TILE, fire=1)
    s2 = snap(host, client)
    snaps = [s2]
    for k in (5, 6):
        cycle(host, client, SEED_C9, rec, f"cycle {k}")
        snaps.append(snap(host, client))
    end(host, client, rec)
    expl = [e for e in rec["hev"] if e["kind"] == "explosion"]
    centres = [as_tile({a: (payload(rec, e).get("centreVoxel") or {}).get(a, 0) // d
                        for a, d in (("x", 16), ("y", 16), ("z", 24))}) for e in expl]
    fut = s1["wh"].get(C9_FIRE_UNIT_TILE), s1["wc"].get(C9_FIRE_UNIT_TILE)
    print(f"EVIDENCE C9: C2 morale response={mr.get('morale')}; launcher/rocket={(g.get('weaponId'), g.get('ammoId'))} "
          f"H {C9_H_TILE}/{C9_H_DIR}; fire={ {k: fire.get(k) for k in ('ok', 'error', 'tuCost')} } seed {SEED_C9}; "
          f"explosions (seq, actionId, centre tile)={[(e['seq'], e['actionId'], c) for e, c in zip(expl, centres)]}; "
          f"C9_FIRE_UNIT_TILE after the rocket host/client={fut}; stun response={st.get('stun')} extra fire "
          f"response={ft.get('fire')}; snapshots pre={snap_view(s0)} rocket={snap_view(s1)} staged={snap_view(s2)} "
          f"cycle5={snap_view(snaps[1])} cycle6={snap_view(snaps[2])}; {rec_evidence(rec)}", flush=True)
    fails = list(rec["notes"]) + fails
    if (g.get("weaponId"), g.get("ammoId")) != (C9_LAUNCHER_ID, C9_ROCKET_ID):
        fails.append(f"battle_give H launcher/rocket {(g.get('weaponId'), g.get('ammoId'))} (want "
                     f"{(C9_LAUNCHER_ID, C9_ROCKET_ID)})")
    if mr.get("morale") != 100 or st.get("stun") != C9_STUN or ft.get("fire") != 1:
        fails.append(f"staging responses morale={mr.get('morale')} stun={st.get('stun')} fire={ft.get('fire')} (want "
                     f"100, {C9_STUN}, 1)")
    if C9_EXPLOSION_TILE not in centres:
        fails.append(f"precondition: explosion centre tiles {centres} (want the rocket on {C9_EXPLOSION_TILE})")
    if not (fut[0] and fut[0][0] and fut[1] and fut[1][0]):
        fails.append(f"precondition: C9_FIRE_UNIT_TILE {C9_FIRE_UNIT_TILE} after the rocket host/client={fut} (want "
                     f"burning on both)")
    for name, s in (("pre", s0), ("rocket", s1), ("staged", s2)):
        if s["tdiff"] or s["diff"]:
            fails.append(f"{name}: tile diffs {s['tdiff']} buckets {s['diff']} (want none)")
    fails += cycle_fails(rec, "C9")
    for k, (prev, s) in enumerate(zip(snaps, snaps[1:]), start=5):
        what = f"after cycle {k}"
        if s["tdiff"]:
            fails.append(f"{what}: tile_info differs host/client on {s['tdiff']} (want equal)")
        if s["diff"]:
            fails.append(f"{what}: buckets differ {s['diff']} (want none)")
        changed = [t for t in C9_WINDOW if (prev["wh"][t] or ())[:2] != (s["wh"][t] or ())[:2]]
        if not changed:
            fails.append(f"{what}: no staged tile's fire/smoke changed (want >= 1)")
        fh0, fh1 = (prev["uh"].get(U_FIRE) or {}).get("health"), (s["uh"].get(U_FIRE) or {}).get("health")
        fhc = (s["uc"].get(U_FIRE) or {}).get("health")
        if fh0 is None or fh1 is None or not fh1 < fh0 or fh1 != fhc:
            fails.append(f"{what}: U_FIRE health {fh0} -> host {fh1} client {fhc} (want lower, equal on both)")
        st0, st1 = (prev["uh"].get(U_STUN) or {}).get("stun"), (s["uh"].get(U_STUN) or {}).get("stun")
        if st0 is None or st1 is None or not st1 < st0 or st1 != (s["uc"].get(U_STUN) or {}).get("stun"):
            fails.append(f"{what}: U_STUN stun {st0} -> host {st1} client {(s['uc'].get(U_STUN) or {}).get('stun')} "
                         f"(want lower, equal on both)")
        burnt = [t for t in C9_WINDOW if (s["wh"][t] or (None,) * 4)[2] != (s0["wh"][t] or (None,) * 4)[2]]
        if not burnt:
            fails.append(f"{what}: no staged tile's floor changed since the start (want >= 1 burnt out)")
    fails += context_fails(rec, "C9")
    fails += common_fails(host, client, rec["before"], {}, "C9")
    finish(fails)


SCENARIOS = (("C5r", c5r_revive), ("C10", c10_fall), ("C13a", c13a_flee), ("C13b", c13b_berserk),
             ("C9", c9_burning))


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, baked "
        f"MAP_FP={MAP_FP!r} (default NEW BATTLE, SEED_MAP {SEED_MAP})")
    assert seated.get("soldierIds") == SEATED, f"seated {seated.get('soldierIds')} (baked {SEATED})"
    order = ([u["id"] for u in hs.get("units", [])], [u["id"] for u in cs.get("units", [])])
    assert order == (UNIT_ORDER, UNIT_ORDER), f"battle_state unit order host/client={order} (baked {UNIT_ORDER})"
    pinned = pin_ai_neutral(host, client, tag="w2p3-sd")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    ih, ic = items(host), items(client)
    assert (len(ih), max(ih) + 1, len(ic), max(ic) + 1) == (FIRST_LEVER_ITEM_ID,) * 4, (
        f"items at start host n={len(ih)} max={max(ih)} client n={len(ic)} max={max(ic)} (baked "
        f"{FIRST_LEVER_ITEM_ID} items, ids 0..{FIRST_LEVER_ITEM_ID - 1})")
    for gc in (host, client):
        es = event_state(gc)
        u0 = session.units_by_id(battle_state(gc)).get(C2_ID) or {}
        assert (isinstance(es.get("deltaRing"), list) and isinstance(es.get("closedContexts"), list)
                and isinstance(es.get("contextsOpened"), dict) and isinstance(es.get("cueCounts"), dict)
                and "lastWalk" in es and all(k in u0 for k in ("morale", "onTile", "unitFire", "status"))), (
            f"{gc.name} lacks a probe: deltaRing={es.get('deltaRing')!r} closedContexts={es.get('closedContexts')!r} "
            f"contextsOpened={es.get('contextsOpened')!r} lastWalk present={'lastWalk' in es} unit {C2_ID} "
            f"keys={sorted(u0)}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2p3-sd] boot ok: SEED_MAP={SEED_MAP} MAP_FP={MAP_FP!r} turn={hs['turn']} seated={SEATED} "
          f"order={UNIT_ORDER} pinned={pinned} items={len(ih)} probes host={ctx_probes(host)} "
          f"client={ctx_probes(client)}", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49858, make_user_dir("w2p3_turn_cues_host"))
    client = GameClient("client", 49859, make_user_dir("w2p3_turn_cues_client"))
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
                print(f"[w2p3-sd] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_turn_cues: {len(passed)}/{len(SCENARIOS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
