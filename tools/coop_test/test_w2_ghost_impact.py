"""W2-P5 S-B - test_w2_ghost_impact.py: the watching machine shows the hit
spark and the explosion of an action it did not execute - display only (spec
rewrite/prompts/w2p5_display_ghosts.md section (f) "test_w2_ghost_impact.py
(S-B)", sections (b)3, (b)5, (b)7 and (b)11 for `hit` and `explosion`, ruling
Q2 (b), as amended by PLAN REVIEW + AMENDMENT E1: PR-E5 (the delivery proof on
option-ON rows only; a record with no display object counts completed at
enqueue), PR-E6 (row order H1, H4, H6, H3, H2; H6 has its own battle_fire
small rocket), OQ1 (a pellet `hit` joins the running combat ghost of its
actionId; with none running it counts `joined` and draws nothing), OQ2 (Q2's
two fields on all four coopCueExplosionInit branches and on coopCuePellet);
amendments E3 / E3.1 (stage S-T): H2's throw follows its pre-action `turn`, so
the Q1 (b) hold applies to its projectile ghost).

Before S-B the second player's machine shows no hit and no explosion: every
applied `hit` / `explosion` cue only counts in cueCounts and the state snaps
(TASK 0 T0-6). After S-B every applied `hit` / `explosion` cue starts one
display-only combat ghost on the client (vanilla Explosion sprites on the
client's Map, frame timing and sounds from the loaded rules; the explosion
scatter from RNG::seedless), a pellet `hit` joins the running hit ghost, and
the host's `hit` / `explosion` payloads carry the damage item's `itemType` and
the weapon's `weaponType` (Q2 (b)). Six rows, ONE boot (terror seed 12, the
Coop_Pellet_Test mod on both machines, coopGhostStepper pinned true in both
boot options, every fire dial at its default), in this order (PR-E6: the END
TURN last, the terrain-changing rockets before it):

  H1  bullet hit on a wall (test_w2_host_combat_terrain C2's staging). H gets
      a rifle + clip (clear_hands, BOTH), H -> H1_H_TILE facing H1_H_DIR, H
      firing 120; host set_seed SEED_H1 and battle_fire {aimed, H1_WALL}.
      RED: client cueCounts.hit +1 and combatGhost.enqueued.hit +0; the hit
      payload has no weaponType / itemType. GREEN: one hit record for the
      hit's seq: frame == hitAnimation(STR_RIFLE_CLIP), frames == its
      hitAnimationFrames when > 0 else Explosion::BULLET_FRAMES (10),
      intervalMs == max(1, 50 - 10 x explosionSpeed) (50), ms == frames x
      intervalMs (500), sprites == 1, sound == hitSound(STR_RIFLE_CLIP); the
      hit payload's weaponType STR_RIFLE, itemType STR_RIFLE_CLIP.
  H4  pellets (TASK 0 T0-5). H stays on H1_H_TILE facing H1_H_DIR (never
      teleported onto its own tile, S2); H gets STR_PISTOL + the mod's
      STR_COOP_PELLET_CLIP (clear_hands, BOTH); host set_seed SEED_H4 and
      battle_fire {snap, H4_TARGET}. RED: shot +1, hit +1 +H4_PELLETS, hit
      +0 ghosts. GREEN: the shot record has pellets true and ms 0; ONE hit
      record (the main hit's seq) with sprites == 1 + H4_PELLETS; joined
      +H4_PELLETS; the record's sound == hitSound(STR_COOP_PELLET_CLIP) (one
      hit sound: the pellets play none); every hit payload (main and
      pellets, OQ2) has weaponType STR_PISTOL, itemType STR_COOP_PELLET_CLIP.
  H6  option OFF (declared green at red; "as G7 for an explosion"). Client
      set_option coopGhostStepper false; H gets a rocket launcher +
      STR_SMALL_ROCKET (clear_hands, BOTH), H -> H6_H_TILE facing H6_H_DIR,
      H firing 120; host set_seed SEED_H6 and battle_fire {aimed,
      H6_TARGET}; then the option back on. RED = GREEN: client
      cueCounts.shot +1, cueCounts.explosion +H6_EXPLOSIONS, and
      combatGhost.enqueued.shot / .explosion +0 while off (Q4 = a).
  H3  rocket + terrain chain (test_w2_host_combat_terrain C4's staging). H
      gets a rocket launcher + STR_SMALL_ROCKET (clear_hands, BOTH), H ->
      H3_H_TILE facing H3_H_DIR, two rifle clips dropped on H3_TARGET (BOTH),
      H firing 120; host set_seed SEED_H3 and battle_fire {aimed, H3_TARGET}.
      RED: +0 explosion ghosts; no weaponType / itemType. GREEN: the shot
      record (as G1: speed == the host seat's fire dial + bulletSpeeds, seat
      0, trajLen == the host's, pathMatches, ticks / ms per the formula,
      sound == the ammo's fire sound, else the weapon's); the chain-0
      explosion record from STR_SMALL_ROCKET's rules and the chain-1
      (`terrain`, itemless) record: frame == EXPLOSION_OFFSET, payload power
      46 -> 9 sprites, step 1, maxDelay 7, ms == (7 + 8) x 50 == 750; the
      chain-0 payload's weaponType STR_ROCKET_LAUNCHER, itemType
      STR_SMALL_ROCKET, the chain-1 payload neither (no item, Q2 "when
      present").
  H2  throw + END TURN grenade (test_w2_host_combat_terrain C3's staging). H
      gets a grenade (clear_hands, BOTH), H -> H2_H_TILE facing H2_H_DIR
      (away from the throw tile, F490: a two-octant pre-action `turn`, stage
      S-T), H TU max; host real-UI prime (fuse 0); host set_seed SEED_H2 and
      battle_fire {throw, H2_THROW_TILE}; a rifle clip dropped on the landing
      tile (BOTH); END TURN on both and the full side cycle. RED: +0
      explosion ghosts; no weaponType / itemType. GREEN: the throw record as
      G5 (arc, pathMatches, trajLen == the host's, the formula, sound ==
      ITEM_THROW, soundEnd == ITEM_DROP); the explosion record (an `endturn`
      context, no shot): sprites == max(1, power / 5), maxDelay / ms per
      (b)3, sound == SMALL_EXPLOSION (power 50), 0 <= spread <= power / 2;
      the payload's itemType STR_GRENADE (and weaponType STR_GRENADE: the
      timed grenade is the attack's weapon and its own ammo).
  H5  V4 over the whole file (declared: no ghost is needed for it): the
      client's rngSeed after the last row equals its value after the boot
      (TASK 0 T0-3 (ii)).

Explosion formula (spec (b)3, vanilla ExplosionBState::init; computed here from
the payload and the LOADED rules of the damage item the row names, itemless for
a terrain link): pfa = the rule's powerForAnimation when > 0 else the payload
power; sprites = max(1, pfa / 5); step = max(1, (pfa / 5) / 5); sprite i
(0-based) waits the count of j in [1, i - 1] with j % step == 0, so maxDelay =
(sprites - 2) / step (0 for one sprite); frame = the rule's hitAnimation
(itemless: EXPLOSION_OFFSET), minus the frame count when the battle's depth is
above 0 (xcom1: always 0); frames = the rule's hitAnimationFrames when > 0 else
Explosion::EXPLODE_FRAMES (8); intervalMs = max(1, 50 - 10 x explosionSpeed)
(itemless 50), 1 when chain > 6; ms = (maxDelay + frames) x intervalMs; sound =
the rule's explosionHitSound when set, else SMALL_EXPLOSION when pfa <= 80,
else LARGE_EXPLOSION. Bullet hit (not a miss): frame = hitAnimation, frames =
hitAnimationFrames when > 0 else Explosion::BULLET_FRAMES (10), one sprite,
intervalMs = max(1, 50 - 10 x explosionSpeed), ms = frames x intervalMs, sound =
hitSound. Sound ids are compared exactly only for single-id lists (F1539); a
multi-id list admits any of its ids.

Common to every row (after session.wait_host_idle: the host has no context and
no BState, the client applied up to the host's lastSeqEmitted): hash_now
{full:true} every bucket EQUAL; desyncSeen false on both; client
coopClientBStatePushes unchanged and host 0; the client's rngSeed unchanged from
the row's start (V4); the host's combatGhost all zero (the host never ghosts);
the client's combatGhost.live == 0 and completed + cut == enqueued per kind;
the client's cueCounts moved by exactly the host's cues of the row per kind (its
cues applied). Option-ON rows (all but H6, PR-E5) add the DELIVERY PROOF: every
host `shot` / `hit` / `explosion` cue of the row (host event_log; payloads from
the host's openxcom.log `[coop-cue]` lines) has exactly one client ring record
with that seq, its kind and unresolved / noMap false - except a pellet `hit`
(payload `pellet`), which has none and counts in `joined` (OQ1) -
combatGhost.enqueued[k] moved by the client's cueCounts[k] delta minus the
row's pellet hits, and joined by the row's pellet hits. Every row also requires
its own cues (vacuous = red): their number, kind, shooter and pinned outcome.
No wall-clock duration is asserted (F1503 / F1505: the harness host steps a
projectile every ~24 ms; a ghost may complete or be cut, so only completed +
cut == enqueued): every timing check is an equality with the (b)3 formula
computed here.

Probes (event_state, all present before S-B: S-A.1 / S-T.1): combatGhost
{enqueued, completed, cut: {shot, hit, explosion}, joined, live, unresolved,
noMap, ring} (both machines; hit / explosion records are written by S-B's green
commit), rngSeed (both, read only), shotTrajectories (host: the last 16 shots'
{seq, trajLen, speed, impact}), speed (the SPEC 17 seat table), cueCounts,
closedContexts; the read-only lever display_rules {types} (items' display rules
and the Mod constants from the loaded rules). S-B.1 adds no probe and no lever:
the rows read only what S-A.1 already exposes.

FIXTURE (TASK 0 T0-5 and T0-7 on the S-B.1 build; the roster-pinned terror boot
of test_w2_host_combat_terrain.py with the Coop_Pellet_Test mod on both):
set_seed SEED_ROSTER on the HOST right before its open_new_battle, mission
STR_TERROR_MISSION, set_seed SEED_MAP right before newbattle_ok, seat_count 2,
MAP_FP asserted on both, pin_ai_neutral, the mod's active line on both. Every
lever pair goes to the CLIENT first (F607); item ids are read from the lever
replies at run time.

RED-THEN-GREEN (spec (d) row S-B). Commit S-B.1 (this file and the pellet mod;
no probe, no lever, no product change) is run ONCE: H1, H4, H3 and H2 must FAIL
with their RED evidence (enqueued.hit / .explosion +0 while the cues applied,
the payload rule fields absent); H6 and H5 are declared green at red. Commit
S-B.2 (the product) is run ONCE and every row must PASS. Each row prints ONE
"EVIDENCE <id>:" line (JSON) with both machines' fields BEFORE its green
conditions are checked; main() runs every row even after an earlier one failed
and prints "PASS <id>" / "FAIL <id>: <message>". Every wait is bounded; a wait
that times out is recorded in the EVIDENCE line and fails the row.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all six rows pass, 2 otherwise (a
bring-up failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_ghost_impact.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_w2_delta_core import diff_buckets, desync_record, short, both, tele_both, tu_both, end_turn_cycle
from test_w2_delta_items import items_by_id, tile_of
from test_w2_host_combat import bring_up_lobby_roster_pinned, evs_since, open_hand_menu_host, press
from test_w2_ai_origins import host_payloads, voxel_tile
from test_w2_client_shoot import ubrief, units
from test_w2_ghost_projectile import record_fails

# ----- bring-up (the roster-pinned terror boot of test_w2_host_combat_terrain.py + the pellet mod) -----
MISSION = "STR_TERROR_MISSION"
SEED_MAP = 12
MAP_FP = -2.6402710723327386e+18   # host battle_state.mapFingerprint on SEED_MAP 12, unmodded and modded (F1501)
H_ID = 10                          # first host-seat soldier (SEED_ROSTER 1: "Henryk Kaminski", tu 58)
PORT = "48719"
COOP_SEAT_0 = 0
FACTION_PLAYER = 0
TU_MAX = 255                       # battle_set_unit_state / battle_fire tu: clamped to the unit's max TU
FIRING_120 = 120
MOD_NAME = "Coop_Pellet_Test"
MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", MOD_NAME)
MOD_ACTIVE_LINE = "- Coop_Pellet_Test v1.0"
PELLET_CLIP = "STR_COOP_PELLET_CLIP"

# T0-7 (S-B.1 build; 3 boots + one K=2 run of this file, every outcome below identical; the fire dials stay at
# their default 6 on both seats): the item ids run rifle 96 / clip 97, pistol 98 / pellet clip 99, H6 launcher
# 100 / rocket 101, H3 launcher 102 / rocket 103 / clips 104, 105, grenade 106 / clip 107 (read at run time).

# ----- H1 (test_w2_host_combat_terrain C2; TASK 0 T0-5 / T0-7) -----
H1_H_TILE, H1_H_DIR = (4, 16, 0), 4       # open road, facing the fence 4 tiles south
H1_WALL = (4, 20, 0)                      # the fence's NORTH wall
V_NORTHWALL = 2                           # src/Mod/MapData.h enum VoxelType
SEED_H1 = 1                               # aimed: impact (72,320,5) on H1_WALL's north wall, host trajLen 51;
                                          # hit power 30, not a miss; chain shot, hit, bt_action_end

# ----- H4 (TASK 0 T0-5: Coop_Pellet_Test, SEED_H4 1, k = 3) -----
H4_TARGET = (4, 18, 0)                    # road floor 2 tiles south of H1_H_TILE (H faces it after H1)
SEED_H4 = 1                               # snap: impact floor (73,294,1), host trajLen 25; main hit + 3 pellet
H4_PELLETS = 3                            # hits (pellet 1, 2, 3), power 26 each; H tu cost 10

# ----- H6 (PR-E6: its own small rocket; TASK 0 T0-7, the first and only construction) -----
H6_H_TILE, H6_H_DIR = (14, 8, 0), 0       # the open street north of the URBAN block (x 10..19); faces north
H6_TARGET = (14, 2, 0)                    # road floor 6 tiles north: no unit and no explosive part within 3 tiles
SEED_H6 = 1                               # aimed: impact floor (233,47,1), host trajLen 84; ONE explosion
H6_EXPLOSIONS = 1                         # centred (233,48,2), power 75, radius 3, chain 0, no terrain link,
H6_BLAST = (0, False, 75)                 # no `hit`: (chain, terrain, power)

# ----- H3 (test_w2_host_combat_terrain C4; TASK 0 T0-5 / T0-7) -----
H3_H_TILE, H3_H_DIR = (22, 34, 0), 0
H3_TARGET = (21, 26, 0)                   # ROADS floor beside the gas pump (20,26,0); two rifle clips dropped here
H3_ROCKET = "STR_SMALL_ROCKET"
SEED_H3 = 1                               # aimed: impact floor (346,432,1), host trajLen 115; explosion chain 0
H3_POWERS = (75, 46)                      # (power 75, radius 3) + the pump's chained terrain link (chain 1,
                                          # `terrain`, itemless, power 46, radius 4); both clips destroyed

# ----- H2 (test_w2_host_combat_terrain C3; TASK 0 T0-5 / T0-7) -----
H2_H_TILE, H2_H_DIR = (5, 17, 0), 2       # faces east, AWAY from the throw tile (F490): a two-octant turn first
H2_THROW_TILE = (5, 11, 0)                # 6 tiles north; the grenade lands here, a rifle clip is dropped here
SEED_H2 = 1                               # throw chain turn, shot, bt_action_end (the shot record waits on the
H2_POWER = 50                             # turn: afterTurnSeq); host trajLen 89; lands on H2_THROW_TILE; END TURN:
                                          # ONE explosion (endturn context), power 50, radius 5, centre (88,184,0)
KEY_PRIME, KEY_FUSE_0 = 49, 48            # PRIME (grenade menu item 1), fuse 0

# ----- display constants (vanilla code, not rules: Explosion.cpp, ExplosionBState.cpp) -----
BULLET_FRAMES = 10                        # Explosion::BULLET_FRAMES
EXPLODE_FRAMES = 8                        # Explosion::EXPLODE_FRAMES
HALF_ANIM_MS = 50                         # BattlescapeState::DEFAULT_ANIM_SPEED / 2
DEPTH = 0                                 # SavedBattleGame::getDepth(): xcom1 battles have no depth
NO_SOUND = -1                             # Mod::NO_SOUND

DISPLAY_TYPES = ("STR_RIFLE", "STR_RIFLE_CLIP", "STR_PISTOL", PELLET_CLIP, "STR_ROCKET_LAUNCHER", H3_ROCKET,
                 "STR_GRENADE")
CUE_KINDS = ("shot", "hit", "explosion")
Q2_KEYS = ("weaponType", "itemType")
PROBE_KEYS = ("combatGhost", "rngSeed", "shotTrajectories", "cueCounts", "lastSeqEmitted", "lastSeqApplied",
              "desyncSeen", "coopClientBStatePushes", "speed", "closedContexts")


# ===================== small probes =====================


def probe(gc):
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return {k: es.get(k) for k in PROBE_KEYS}


def snap2(host, client):
    return {"host": probe(host), "client": probe(client)}


def rng_of(gc):
    return event_state(gc).get("rngSeed")


def cg_counts(cg):
    """combatGhost without its ring."""
    cg = cg or {}
    return {k: cg.get(k) for k in ("enqueued", "completed", "cut", "joined", "live", "unresolved", "noMap")}


def kind_of(d, kind):
    return (d or {}).get(kind) or 0


def cue_delta(before, after, kind):
    return kind_of(after, kind) - kind_of(before, kind)


def fire_dial(snap, seat):
    """`seat`'s fire dial in this machine's SPEC 17 seat table (None when absent)."""
    ent = [s for s in ((snap.get("speed") or {}).get("seats") or []) if s.get("seat") == seat]
    return ent[0].get("fire") if ent else None


def settle(host, client, notes, timeout=30):
    """Bounded: the host's action finished (no BState, no context), then the client caught up."""
    def done():
        bs = battle_state(host)
        return (bs.get("pendingStates") == 0 and not bs.get("isBusy") and session.top_state(host) ==
                "BattlescapeState" and event_state(host).get("busyOwnerSeat") == -1) or None
    try:
        host.wait_for("the host's action finished (no BState, no action context)", done, timeout=timeout)
    except Exception as e:
        notes.append(f"host action: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=timeout)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")


def mod_log(gc):
    """This machine's openxcom.log: the active-mods lines naming the test mod and every invalid-mod line."""
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError as e:
        return {"error": short(e)}
    return {"active": [ln.split("\t")[-1] for ln in lines if MOD_NAME in ln and "- " in ln and "Invalid" not in ln],
            "invalid": [ln.split("\t")[-1] for ln in lines if "Invalid" in ln and "mod" in ln]}


def fire(host, req, notes, what):
    """One host battle_fire; a refusal is recorded in `notes` (evidence)."""
    try:
        r = host.cmd(req)
        if not r.get("ok"):
            notes.append(f"battle_fire {what} refused: {r}")
        return r
    except Exception as e:
        notes.append(f"battle_fire {what}: {short(e)}")
        return {}


def staging_fails(staged):
    return [f"buckets differ after the staging: {staged} (want none)"] if staged else []


# ===================== record + checks =====================


def collect(host, client, before, seq0, rng0):
    """The row's end state: both machines' probes, the row's evs, the host's
    P5 cues with their payloads, the host's per-seq trajectories and the client's
    ring records by seq."""
    after = snap2(host, client)
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    seqs = [e["seq"] for e in hev if e["kind"] in CUE_KINDS]
    pl = host_payloads(host, seqs) if seqs else {}
    cues = [{"seq": e["seq"], "kind": e["kind"], "actionId": e["actionId"],
             "payload": (pl.get(e["seq"]) or {}).get("payload") or {}} for e in hev if e["kind"] in CUE_KINDS]
    shots = [(c["seq"], c["payload"]) for c in cues if c["kind"] == "shot"]
    traj = {r.get("seq"): r for r in (after["host"]["shotTrajectories"] or [])}
    ring = {}
    for r in ((after["client"]["combatGhost"] or {}).get("ring") or []):
        ring.setdefault(r.get("seq"), []).append(r)
    rec = {"before": before, "after": after, "seq0": seq0, "hev": hev, "cev": cev, "cues": cues, "shots": shots,
           "traj": traj, "ring": ring, "rng": {"start": rng0, "staged": before["client"]["rngSeed"],
                                              "end": after["client"]["rngSeed"]},
           "hostRng": (before["host"]["rngSeed"], after["host"]["rngSeed"]), "diff": diff_buckets(host, client)}
    rec["dsc"] = desync_record(client, after["client"]["desyncSeen"])
    return rec


def pellet_of(c):
    return c["kind"] == "hit" and "pellet" in c["payload"]


def cue_view(rec):
    """Per host P5 cue: seq, kind, actionId, the payload brief (incl. Q2's fields) and the client's ring record(s)."""
    keys = ("actor", "unit", "action", "impact", "impactVoxel", "voxel", "centreVoxel", "power", "radius", "chain",
            "terrain", "miss", "pellet", "damageType") + Q2_KEYS
    return [{"seq": c["seq"], "kind": c["kind"], "actionId": c["actionId"],
             "payload": {k: c["payload"].get(k) for k in keys if k in c["payload"]},
             "hostTraj": rec["traj"].get(c["seq"]) if c["kind"] == "shot" else None,
             "ring": rec["ring"].get(c["seq"])} for c in rec["cues"]]


def evidence(row, rec, extra):
    b, a = rec["before"], rec["after"]
    ev = {"extra": extra,
          "cueDelta": {n: {k: cue_delta(b[n]["cueCounts"], a[n]["cueCounts"], k) for k in CUE_KINDS}
                       for n in ("host", "client")},
          "clientCombatGhost": {"before": cg_counts(b["client"]["combatGhost"]),
                                "after": cg_counts(a["client"]["combatGhost"])},
          "hostCombatGhost": a["host"]["combatGhost"],
          "cues": cue_view(rec), "rngClient": rec["rng"], "rngHost": rec["hostRng"],
          "hostEvs": [(e["seq"], e["kind"], e["actionId"]) for e in rec["hev"]],
          "clientEvs": [(e["seq"], e["kind"], e["actionId"]) for e in rec["cev"]],
          "fireDial": {n: fire_dial(a[n], COOP_SEAT_0) for n in ("host", "client")},
          "pushes": {"clientBefore": b["client"]["coopClientBStatePushes"],
                     "clientAfter": a["client"]["coopClientBStatePushes"], "host": a["host"]["coopClientBStatePushes"]},
          "desyncSeen": {"host": a["host"]["desyncSeen"], "client": a["client"]["desyncSeen"]}, "desync": rec["dsc"],
          "diff": rec["diff"]}
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)


def common_fails(host, client, rec, option_on, what):
    """Spec (f) common asserts; PR-E5: the delivery proof on option-ON rows only."""
    fails = []
    try:
        assert_hash_clean(host, client, full=True, what=what)
    except AssertionError as e:
        fails.append(f"hash_now full not clean: {short(e, 600)}")
    b, a = rec["before"], rec["after"]
    if a["host"]["desyncSeen"] or a["client"]["desyncSeen"]:
        fails.append(f"desyncSeen host={a['host']['desyncSeen']} client={a['client']['desyncSeen']} "
                     f"(want false on both; {rec['dsc']})")
    if a["client"]["coopClientBStatePushes"] != b["client"]["coopClientBStatePushes"]:
        fails.append(f"client coopClientBStatePushes {b['client']['coopClientBStatePushes']}->"
                     f"{a['client']['coopClientBStatePushes']} (want unchanged)")
    if a["host"]["coopClientBStatePushes"] != 0:
        fails.append(f"host coopClientBStatePushes={a['host']['coopClientBStatePushes']} (want 0)")
    if rec["rng"]["start"] is None or rec["rng"]["end"] != rec["rng"]["start"]:
        fails.append(f"client rngSeed {rec['rng']} (want the row's start value at its end: V4)")
    hc = a["host"]["combatGhost"] or {}
    hz = all(kind_of(hc.get(g), k) == 0 for g in ("enqueued", "completed", "cut") for k in CUE_KINDS) \
        and all((hc.get(k) or 0) == 0 for k in ("joined", "live", "unresolved", "noMap")) and not hc.get("ring")
    if not hc or not hz:
        fails.append(f"host combatGhost {cg_counts(hc)} ring {len(hc.get('ring') or [])} (want all zero and no "
                     f"record: the host never ghosts)")
    cb, cc = b["client"]["combatGhost"] or {}, a["client"]["combatGhost"] or {}
    if not cc:
        fails.append("client event_state has no combatGhost probe")
        return fails
    if cc.get("live") != 0:
        fails.append(f"client combatGhost.live={cc.get('live')} at the row's end (want 0)")
    for k in CUE_KINDS:
        e, c, u = kind_of(cc.get("enqueued"), k), kind_of(cc.get("completed"), k), kind_of(cc.get("cut"), k)
        if c + u != e:
            fails.append(f"client combatGhost {k}: completed {c} + cut {u} != enqueued {e}")
        n = sum(1 for x in rec["cues"] if x["kind"] == k)
        dc = cue_delta(b["client"]["cueCounts"], a["client"]["cueCounts"], k)
        if dc != n:
            fails.append(f"client cueCounts.{k} +{dc} but the host sent {n} `{k}` cue(s) in the row (want equal: "
                         f"every cue applied)")
    if not option_on:
        return fails
    pellets = [x for x in rec["cues"] if pellet_of(x)]
    for x in rec["cues"]:
        rs = rec["ring"].get(x["seq"]) or []
        if pellet_of(x):
            if rs:
                fails.append(f"delivery: pellet hit seq {x['seq']} has client ring record(s) {rs} (want none: a "
                             f"pellet joins, OQ1)")
            continue
        if len(rs) != 1 or rs[0].get("kind") != x["kind"] or rs[0].get("unresolved") or rs[0].get("noMap"):
            fails.append(f"delivery: host {x['kind']} seq {x['seq']} has {len(rs)} client ring record(s) {rs} (want "
                         f"exactly one of kind {x['kind']} with unresolved/noMap false)")
    for k in CUE_KINDS:
        np = len(pellets) if k == "hit" else 0
        de = cue_delta(cb.get("enqueued"), cc.get("enqueued"), k)
        dc = cue_delta(b["client"]["cueCounts"], a["client"]["cueCounts"], k)
        if de != dc - np:
            fails.append(f"delivery: client cueCounts.{k} +{dc} but combatGhost.enqueued.{k} +{de} (want "
                         f"+{dc - np}{' = the cues minus the pellet hits' if np else ''})")
    dj = (cc.get("joined") or 0) - (cb.get("joined") or 0)
    if dj != len(pellets):
        fails.append(f"delivery: client combatGhost.joined +{dj} (want +{len(pellets)}: the row's pellet hits, OQ1)")
    return fails


def cues_of(rec, kind, pellet=None):
    out = [c for c in rec["cues"] if c["kind"] == kind]
    if pellet is not None:
        out = [c for c in out if pellet_of(c) == pellet]
    return out


def only_record(rec, c):
    rs = rec["ring"].get(c["seq"]) or []
    return rs[0] if len(rs) == 1 else None


def q2_fails(c, weapon, item):
    """Q2 (b), OQ2: the cue's payload carries the RuleItem type strings of the attack's weapon and damage item,
    when present (an itemless terrain link carries neither)."""
    want = {}
    if weapon:
        want["weaponType"] = weapon
    if item:
        want["itemType"] = item
    got = {k: c["payload"].get(k) for k in Q2_KEYS if k in c["payload"]}
    if got != want:
        return [f"{c['kind']} seq {c['seq']}: payload rule fields {got or 'absent'} (want {want or 'absent'}: Q2 (b))"]
    return []


def sound_fails(what, got, ids, default=NO_SOUND):
    """F1539: one id -> exactly it; several -> any of them; none -> `default`."""
    if (len(ids) == 1 and got != ids[0]) or (len(ids) > 1 and got not in ids) or (not ids and got != default):
        return [f"{what}: record sound {got} (want {ids[0] if len(ids) == 1 else (ids or default)})"]
    return []


def rule_list(rules, item, field):
    return list((((rules.get(item) or {}).get("soundLists") or {}).get(field)) or [])


def hit_want(rules, item):
    """Spec (b)3 bullet hit, not a miss (vanilla ExplosionBState::init's non-melee branch)."""
    r = rules.get(item) or {}
    anim = r.get("hitAnimation", -1)
    fc = r.get("hitAnimationFrames", -1)
    frames = fc if isinstance(fc, int) and fc > 0 else BULLET_FRAMES
    interval = max(1, HALF_ANIM_MS - 10 * (r.get("explosionSpeed") or 0))
    return {"frame": anim, "frames": frames, "intervalMs": interval, "ms": frames * interval,
            "sprites": 1 if anim != -1 else 0}


def hit_record_fails(rec, c, rules, item):
    """H1 GREEN: the bullet hit's record."""
    if c["payload"].get("miss") is not False:
        return [f"precondition: hit seq {c['seq']} payload miss={c['payload'].get('miss')} (want false)"]
    r = only_record(rec, c)
    if r is None:
        return [f"hit seq {c['seq']}: client ring record(s) {rec['ring'].get(c['seq'])} (want exactly 1)"]
    want = dict({"kind": "hit", "actionId": c["actionId"]}, **hit_want(rules, item))
    got = {k: r.get(k) for k in want}
    fails = [f"hit seq {c['seq']}: record {got} (want {want}: {item})"] if got != want else []
    fails += sound_fails(f"hit seq {c['seq']}", r.get("sound"), rule_list(rules, item, "hitSound"))
    return fails


def explosion_want(c, rules, item, k):
    """Spec (b)3 explosion from the payload and `item`'s loaded rules (None = itemless: a terrain link)."""
    p = c["payload"]
    r = (rules.get(item) or {}) if item else None
    power, chain = p.get("power"), p.get("chain")
    if not isinstance(power, int) or not isinstance(chain, int):
        return None, None
    if power <= 0:
        return {"sprites": 0, "ms": 0}, []
    pfa = r["powerForAnimation"] if r and (r.get("powerForAnimation") or 0) > 0 else power
    frame = r.get("hitAnimation", -1) if r else k["EXPLOSION_OFFSET"]
    fc = r.get("hitAnimationFrames", -1) if r else -1
    frames = fc if isinstance(fc, int) and fc > 0 else EXPLODE_FRAMES
    if DEPTH > 0:
        frame -= frames
    sprites = max(1, pfa // 5)
    step = max(1, (pfa // 5) // 5)
    max_delay = (sprites - 2) // step if sprites >= 2 else 0
    interval = max(1, HALF_ANIM_MS - 10 * (r.get("explosionSpeed") or 0)) if r else HALF_ANIM_MS
    if chain > 6:
        interval = 1
    ids = rule_list(rules, item, "explosionHitSound") if r else []
    if not ids:
        ids = [k["SMALL_EXPLOSION"] if pfa <= 80 else k["LARGE_EXPLOSION"]]
    want = {"frame": frame, "frames": frames, "sprites": sprites, "maxDelay": max_delay, "intervalMs": interval,
            "ms": (max_delay + frames) * interval, "pfa": pfa}
    return want, ids


def explosion_record_fails(rec, c, rules, item, k):
    """H2 / H3 GREEN: one explosion record per the formula; 0 <= spread <= pfa / 2 (the seedless scatter)."""
    want, ids = explosion_want(c, rules, item, k)
    if want is None:
        return [f"precondition: explosion seq {c['seq']} payload power/chain {c['payload']} (want ints)"]
    r = only_record(rec, c)
    if r is None:
        return [f"explosion seq {c['seq']}: client ring record(s) {rec['ring'].get(c['seq'])} (want exactly 1)"]
    pfa = want.pop("pfa", None)
    want = dict({"kind": "explosion", "actionId": c["actionId"]}, **want)
    got = {k2: r.get(k2) for k2 in want}
    fails = [f"explosion seq {c['seq']}: record {got} (want {want}: {item or 'itemless'}, payload power "
             f"{c['payload'].get('power')} chain {c['payload'].get('chain')})"] if got != want else []
    if pfa is not None:
        sp = r.get("spread")
        if not isinstance(sp, int) or not 0 <= sp <= pfa // 2:
            fails.append(f"explosion seq {c['seq']}: record spread {sp} (want 0..{pfa // 2}: the scatter within "
                         f"+-pfa/2)")
        fails += sound_fails(f"explosion seq {c['seq']}", r.get("sound"), ids)
    return fails


def shot_record_fails(rec, s, p, rules, weapon, ammo, dial, arc=False):
    """A shot's S-A record (as G1 / G5): speed == the seat's dial + the bulletSpeeds (a throw: the dial only)."""
    wr, ar = rules.get(weapon) or {}, rules.get(ammo) or {}
    if arc:
        speed = dial
    else:
        speed = max(1, max(1, (dial or 0) + (ar.get("bulletSpeed") or 0)) + (wr.get("bulletSpeed") or 0))
    fails = record_fails(rec, s, p, speed, COOP_SEAT_0, arc=arc)
    r = (rec["ring"].get(s) or [{}])[0]
    if not arc:
        ids = rule_list(rules, ammo, "fireSound") or rule_list(rules, weapon, "fireSound")
        fails += sound_fails(f"shot seq {s}", r.get("sound"), ids)
    return fails


def finish(fails):
    if fails:
        raise AssertionError("; ".join(fails))


# ===================== rows =====================


def h1_wall_hit(host, client, ctx):
    notes = []
    rng0 = rng_of(client)
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": "STR_RIFLE", "ammo": "STR_RIFLE_CLIP",
                            "clear_hands": True}, ("weaponId", "ammoId"))
    ph = tele_both(host, client, H_ID, H1_H_TILE, H1_H_DIR)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": H_ID, "stat": "firing",
                        "value": FIRING_120}, ("tu",))
    staged = diff_buckets(host, client)
    before = snap2(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    host.ok({"cmd": "set_seed", "seed": SEED_H1})
    rf = fire(host, {"cmd": "battle_fire", "unit": H_ID, "mode": "aimed", "x": H1_WALL[0], "y": H1_WALL[1],
                     "z": H1_WALL[2], "tu": TU_MAX}, notes, "aimed")
    settle(host, client, notes)
    rec = collect(host, client, before, seq0, rng0)
    evidence("H1", rec, {"rifle": g.get("weaponId"), "clip": g.get("ammoId"), "H": ph, "fire": rf,
                         "stagedDiff": staged, "notes": notes,
                         "H_after": {"host": ubrief(units(host).get(H_ID)), "client": ubrief(units(client).get(H_ID))}})
    fails = list(notes) + staging_fails(staged)
    shots, hits = cues_of(rec, "shot"), cues_of(rec, "hit")
    sp = shots[0]["payload"] if len(shots) == 1 else {}
    if (len(shots) != 1 or sp.get("actor") != H_ID or sp.get("action") != "aimed"
            or voxel_tile(sp.get("impactVoxel")) != H1_WALL or sp.get("impact") != V_NORTHWALL
            or len(hits) != 1 or pellet_of(hits[0]) or cues_of(rec, "explosion")):
        fails.append(f"precondition: the row's cues {[(c['seq'], c['kind'], c['payload']) for c in rec['cues']]} "
                     f"(want one aimed `shot` by H on {H1_WALL} impact V_NORTHWALL {V_NORTHWALL}, then one `hit`)")
    fails += common_fails(host, client, rec, True, "H1")
    for c in hits[:1]:
        fails += hit_record_fails(rec, c, ctx["rules"], "STR_RIFLE_CLIP")
        fails += q2_fails(c, "STR_RIFLE", "STR_RIFLE_CLIP")
    finish(fails)


def h4_pellets(host, client, ctx):
    notes = []
    rng0 = rng_of(client)
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": "STR_PISTOL", "ammo": PELLET_CLIP,
                            "clear_hands": True}, ("weaponId", "ammoId"))
    uh, uc = units(host).get(H_ID) or {}, units(client).get(H_ID) or {}
    at = {n: (u.get("x"), u.get("y"), u.get("z"), u.get("direction")) for n, u in (("host", uh), ("client", uc))}
    staged = diff_buckets(host, client)
    before = snap2(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    host.ok({"cmd": "set_seed", "seed": SEED_H4})
    rf = fire(host, {"cmd": "battle_fire", "unit": H_ID, "mode": "snap", "x": H4_TARGET[0], "y": H4_TARGET[1],
                     "z": H4_TARGET[2], "tu": TU_MAX}, notes, "snap")
    settle(host, client, notes)
    rec = collect(host, client, before, seq0, rng0)
    evidence("H4", rec, {"pistol": g.get("weaponId"), "clip": g.get("ammoId"), "H_at": at, "fire": rf,
                         "stagedDiff": staged, "notes": notes})
    fails = list(notes) + staging_fails(staged)
    want_at = tuple(H1_H_TILE) + (H1_H_DIR,)
    if at["host"] != want_at or at["client"] != want_at:
        fails.append(f"precondition: H before the pellet snap {at} (want {want_at} on both: H1 left it there)")
    if g.get("ammoId") is None or g.get("ammoId") < 0:
        fails.append(f"precondition: battle_give gave no {PELLET_CLIP} (ammoId {g.get('ammoId')}: the mod loaded?)")
    shots, mains, pels = cues_of(rec, "shot"), cues_of(rec, "hit", pellet=False), cues_of(rec, "hit", pellet=True)
    sp = shots[0]["payload"] if len(shots) == 1 else {}
    if (len(shots) != 1 or sp.get("actor") != H_ID or sp.get("action") != "snap" or len(mains) != 1
            or [c["payload"].get("pellet") for c in pels] != list(range(1, H4_PELLETS + 1))
            or cues_of(rec, "explosion")):
        fails.append(f"precondition: the row's cues {[(c['seq'], c['kind'], c['payload']) for c in rec['cues']]} "
                     f"(want one snap `shot` by H, one main `hit`, then pellet hits 1..{H4_PELLETS})")
    fails += common_fails(host, client, rec, True, "H4")
    for c in shots[:1]:
        r = only_record(rec, c) or {}
        if r.get("pellets") is not True or r.get("ms") != 0:
            fails.append(f"shot seq {c['seq']}: record pellets {r.get('pellets')} ms {r.get('ms')} (want true, 0: "
                         f"shotgun ammo has no flight)")
    hit_recs = [r for c in rec["cues"] if c["kind"] == "hit" for r in (rec["ring"].get(c["seq"]) or [])]
    if len(hit_recs) != 1:
        fails.append(f"client hit records for the row {hit_recs} (want ONE: the main hit's; the pellets join it)")
    for c in mains[:1]:
        r = only_record(rec, c) or {}
        if r.get("sprites") != 1 + len(pels):
            fails.append(f"hit seq {c['seq']}: record sprites {r.get('sprites')} (want 1 + {len(pels)} pellet hits)")
        fails += sound_fails(f"hit seq {c['seq']}", r.get("sound"), rule_list(ctx["rules"], PELLET_CLIP, "hitSound"))
    for c in mains + pels:
        fails += q2_fails(c, "STR_PISTOL", PELLET_CLIP)
    finish(fails)


def h6_option_off(host, client, ctx):
    notes = []
    rng0 = rng_of(client)
    off = client.ok({"cmd": "set_option", "name": "coopGhostStepper", "value": False}).get("value")
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": "STR_ROCKET_LAUNCHER", "ammo": H3_ROCKET,
                            "clear_hands": True}, ("weaponId", "ammoId"))
    ph = tele_both(host, client, H_ID, H6_H_TILE, H6_H_DIR)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": H_ID, "stat": "firing",
                        "value": FIRING_120}, ("tu",))
    staged = diff_buckets(host, client)
    before = snap2(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    host.ok({"cmd": "set_seed", "seed": SEED_H6})
    rf = fire(host, {"cmd": "battle_fire", "unit": H_ID, "mode": "aimed", "x": H6_TARGET[0], "y": H6_TARGET[1],
                     "z": H6_TARGET[2], "tu": TU_MAX}, notes, "aimed rocket")
    settle(host, client, notes)
    rec = collect(host, client, before, seq0, rng0)
    on = client.ok({"cmd": "set_option", "name": "coopGhostStepper", "value": True}).get("value")
    evidence("H6", rec, {"optionOff": off, "optionBackOn": on, "launcher": g.get("weaponId"),
                         "rocket": g.get("ammoId"), "H": ph, "fire": rf, "stagedDiff": staged, "notes": notes})
    fails = list(notes) + staging_fails(staged)
    if off is not False or on is not True:
        fails.append(f"client coopGhostStepper lever answered off={off} on={on} (want False then True)")
    shots, expl = cues_of(rec, "shot"), cues_of(rec, "explosion")
    sp = shots[0]["payload"] if len(shots) == 1 else {}
    blasts = [(c["payload"].get("chain"), c["payload"].get("terrain"), c["payload"].get("power")) for c in expl]
    if (len(shots) != 1 or sp.get("actor") != H_ID or sp.get("action") != "aimed"
            or blasts != [H6_BLAST] * H6_EXPLOSIONS or cues_of(rec, "hit")):
        fails.append(f"precondition: the row's cues {[(c['seq'], c['kind'], c['payload']) for c in rec['cues']]} "
                     f"(want one aimed `shot` by H and {H6_EXPLOSIONS} `explosion`(s) (chain, terrain, power) "
                     f"{H6_BLAST}, no `hit`)")
    b, a = rec["before"]["client"], rec["after"]["client"]
    for k, n in (("shot", 1), ("explosion", H6_EXPLOSIONS)):
        dc = cue_delta(b["cueCounts"], a["cueCounts"], k)
        de = cue_delta((b["combatGhost"] or {}).get("enqueued"), (a["combatGhost"] or {}).get("enqueued"), k)
        if dc != n or de != 0:
            fails.append(f"client cueCounts.{k} +{dc} combatGhost.enqueued.{k} +{de} while the option is off (want "
                         f"+{n} and +0: Q4 = a)")
    fails += common_fails(host, client, rec, False, "H6")
    finish(fails)


def h3_rocket_chain(host, client, ctx):
    notes = []
    rng0 = rng_of(client)
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": "STR_ROCKET_LAUNCHER", "ammo": H3_ROCKET,
                            "clear_hands": True}, ("weaponId", "ammoId"))
    ph = tele_both(host, client, H_ID, H3_H_TILE, H3_H_DIR)
    clips = both(host, client, {"cmd": "battle_drop", "x": H3_TARGET[0], "y": H3_TARGET[1], "z": H3_TARGET[2],
                                "item": "STR_RIFLE_CLIP", "count": 2}, ("ids",))["ids"]
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": H_ID, "stat": "firing",
                        "value": FIRING_120}, ("tu",))
    staged = diff_buckets(host, client)
    before = snap2(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    host.ok({"cmd": "set_seed", "seed": SEED_H3})
    rf = fire(host, {"cmd": "battle_fire", "unit": H_ID, "mode": "aimed", "x": H3_TARGET[0], "y": H3_TARGET[1],
                     "z": H3_TARGET[2], "tu": TU_MAX}, notes, "aimed rocket")
    settle(host, client, notes)
    rec = collect(host, client, before, seq0, rng0)
    ih = items_by_id(host)
    evidence("H3", rec, {"launcher": g.get("weaponId"), "rocket": g.get("ammoId"), "clips": clips, "H": ph,
                         "fire": rf, "clipsLeftHost": [c for c in clips if c in ih], "stagedDiff": staged,
                         "notes": notes})
    fails = list(notes) + staging_fails(staged)
    shots, expl = cues_of(rec, "shot"), cues_of(rec, "explosion")
    sp = shots[0]["payload"] if len(shots) == 1 else {}
    got = [(c["payload"].get("chain"), c["payload"].get("terrain"), c["payload"].get("power")) for c in expl]
    want = [(0, False, H3_POWERS[0]), (1, True, H3_POWERS[1])]
    if (len(shots) != 1 or sp.get("actor") != H_ID or sp.get("action") != "aimed" or got != want
            or cues_of(rec, "hit")):
        fails.append(f"precondition: the row's cues {[(c['seq'], c['kind'], c['payload']) for c in rec['cues']]} "
                     f"(want one aimed `shot` by H, then explosions (chain, terrain, power) {want}, no `hit`)")
    fails += common_fails(host, client, rec, True, "H3")
    dial = fire_dial(rec["after"]["host"], COOP_SEAT_0)
    for s, p in rec["shots"][:1]:
        fails += shot_record_fails(rec, s, p, ctx["rules"], "STR_ROCKET_LAUNCHER", H3_ROCKET, dial)
    k = ctx["constants"]
    for c in expl:
        link = c["payload"].get("terrain") is True
        item = None if link else H3_ROCKET
        fails += explosion_record_fails(rec, c, ctx["rules"], item, k)
        fails += q2_fails(c, None if link else "STR_ROCKET_LAUNCHER", item)
    finish(fails)


def h2_grenade_endturn(host, client, ctx):
    notes = []
    rng0 = rng_of(client)
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": "STR_GRENADE", "clear_hands": True},
             ("weaponId", "ammoId"))
    gid = g["weaponId"]
    ph = tele_both(host, client, H_ID, H2_H_TILE, H2_H_DIR)
    tu_both(host, client, H_ID)
    staged = diff_buckets(host, client)
    before = snap2(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    # the prime: real UI (PRIME key, fuse 0), as test_w2_host_combat_terrain C3
    pv = {}
    try:
        pv["cursor"] = open_hand_menu_host(host)
        press(host, KEY_PRIME)
        host.wait_for("host PrimeGrenadeState on top", lambda: session.top_state(host) == "PrimeGrenadeState" or None,
                      timeout=5)
        press(host, KEY_FUSE_0)
        host.wait_for("host BattlescapeState on top after the fuse key",
                      lambda: session.top_state(host) == "BattlescapeState" or None, timeout=5)
        host.wait_for("host grenade fuse 0", lambda: (items_by_id(host).get(gid) or {}).get("fuse") == 0 or None,
                      timeout=10)
    except Exception as e:
        notes.append(f"host prime: {short(e)} (top {session.top_state(host)})")
    settle(host, client, notes)
    fuse = {n: (items_by_id(gc).get(gid) or {}).get("fuse") for n, gc in (("host", host), ("client", client))}
    # the throw (the thrower faces away: its pre-action turn, stage S-T)
    host.ok({"cmd": "set_seed", "seed": SEED_H2})
    rf = fire(host, {"cmd": "battle_fire", "unit": H_ID, "mode": "throw", "x": H2_THROW_TILE[0],
                     "y": H2_THROW_TILE[1], "z": H2_THROW_TILE[2], "tu": TU_MAX}, notes, "throw")
    settle(host, client, notes)
    landed = {n: tile_of(items_by_id(gc).get(gid)) for n, gc in (("host", host), ("client", client))}
    clip = both(host, client, {"cmd": "battle_drop", "x": H2_THROW_TILE[0], "y": H2_THROW_TILE[1],
                               "z": H2_THROW_TILE[2], "item": "STR_RIFLE_CLIP"}, ("ids",))["ids"][0]
    turn0 = end_turn_cycle(host, client, notes)
    rec = collect(host, client, before, seq0, rng0)
    hs, cs = battle_state(host), battle_state(client)
    ih, ic = items_by_id(host), items_by_id(client)
    closed = event_state(host).get("closedContexts") or []
    endturn = {c.get("actionId") for c in closed if c.get("origin") == "endturn"}
    evidence("H2", rec, {"grenade": gid, "H": ph, "prime": pv, "fuse": fuse, "fire": rf, "landed": landed,
                         "clip": clip, "turn": (turn0, (hs.get("turn"), hs.get("side")), (cs.get("turn"),
                                                                                         cs.get("side"))),
                         "endturnContexts": sorted(endturn), "grenadeLeft": {"host": gid in ih, "client": gid in ic},
                         "stagedDiff": staged, "notes": notes})
    fails = list(notes) + staging_fails(staged)
    if fuse != {"host": 0, "client": 0}:
        fails.append(f"precondition: grenade {gid} fuse after the prime {fuse} (want 0 on both)")
    if landed != {"host": H2_THROW_TILE, "client": H2_THROW_TILE}:
        fails.append(f"precondition: the grenade after the throw lies on {landed} (want {H2_THROW_TILE} on both)")
    if (hs.get("turn"), hs.get("side"), cs.get("turn"), cs.get("side")) != (turn0 + 1, FACTION_PLAYER,
                                                                             turn0 + 1, FACTION_PLAYER):
        fails.append(f"precondition: not on player turn {turn0 + 1} on both after the cycle: host=({hs.get('turn')},"
                     f"{hs.get('side')}) client=({cs.get('turn')},{cs.get('side')})")
    shots, expl = cues_of(rec, "shot"), cues_of(rec, "explosion")
    sp = shots[0]["payload"] if len(shots) == 1 else {}
    ep = expl[0]["payload"] if len(expl) == 1 else {}
    shot_aids = {c["actionId"] for c in shots}
    if (len(shots) != 1 or sp.get("actor") != H_ID or sp.get("action") != "throw"
            or not isinstance(sp.get("arc"), dict) or len(expl) != 1 or ep.get("power") != H2_POWER
            or ep.get("chain") != 0 or voxel_tile(ep.get("centreVoxel")) != H2_THROW_TILE
            or expl[0]["actionId"] not in endturn or expl[0]["actionId"] in shot_aids or cues_of(rec, "hit")):
        view = [(c["seq"], c["kind"], c["actionId"], c["payload"]) for c in rec["cues"]]
        fails.append(f"precondition: the row's cues {view} (want one `throw` shot by H with an arc, then ONE "
                     f"explosion of power {H2_POWER}, chain 0, centred on {H2_THROW_TILE}, on an `endturn` context "
                     f"{sorted(endturn)} holding no shot; no `hit`)")
    fails += common_fails(host, client, rec, True, "H2")
    dial = fire_dial(rec["after"]["host"], COOP_SEAT_0)
    k = ctx["constants"]
    for s, p in rec["shots"][:1]:
        fails += shot_record_fails(rec, s, p, ctx["rules"], "STR_GRENADE", None, dial, arc=True)
        r = (rec["ring"].get(s) or [{}])[0]
        if r.get("sound") != k.get("ITEM_THROW") or r.get("soundEnd") != k.get("ITEM_DROP"):
            fails.append(f"shot seq {s}: record sound {r.get('sound')} soundEnd {r.get('soundEnd')} (want ITEM_THROW "
                         f"{k.get('ITEM_THROW')}, ITEM_DROP {k.get('ITEM_DROP')})")
    for c in expl[:1]:
        fails += explosion_record_fails(rec, c, ctx["rules"], "STR_GRENADE", k)
        fails += q2_fails(c, "STR_GRENADE", "STR_GRENADE")
    finish(fails)


def h5_v4_file(host, client, ctx):
    """H5 (declared: no ghost is needed): the client's rngSeed after the last row equals its value after the boot."""
    end = rng_of(client)
    ev = {"rngClientBoot": ctx["rng0"], "rngClientEnd": end, "rngHostBoot": ctx["rngHost0"],
          "rngHostEnd": rng_of(host)}
    print(f"EVIDENCE H5: {json.dumps(ev, sort_keys=True)}", flush=True)
    if ctx["rng0"] is None or end != ctx["rng0"]:
        raise AssertionError(f"client rngSeed after the file {end} (want its value after the boot {ctx['rng0']}: V4, "
                             f"TASK 0 T0-3 (ii))")


SCENARIOS = (("H1", h1_wall_hit), ("H4", h4_pellets), ("H6", h6_option_off), ("H3", h3_rocket_chain),
             ("H2", h2_grenade_endturn), ("H5", h5_v4_file))


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    ml = {gc.name: mod_log(gc) for gc in (host, client)}
    for name, m in ml.items():
        assert MOD_ACTIVE_LINE in (m.get("active") or []) and not m.get("invalid"), (
            f"{name}: {MOD_NAME} not active (active lines {m.get('active')}, invalid {m.get('invalid')}, "
            f"error {m.get('error')})")
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} ({MISSION}, SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p5-sb")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    opts = {gc.name: gc.ok({"cmd": "set_option", "name": "coopGhostStepper"}).get("value") for gc in (host, client)}
    assert opts == {"host": True, "client": True}, f"coopGhostStepper at boot {opts} (want True on both: pinned)"
    for gc in (host, client):
        es = event_state(gc)
        miss = [k for k in ("combatGhost", "rngSeed", "shotTrajectories", "speed", "cueCounts") if k not in es]
        assert not miss, f"{gc.name} event_state lacks the W2-P5 probes {miss}"
    dr = client.ok({"cmd": "display_rules", "types": list(DISPLAY_TYPES)})
    drh = host.ok({"cmd": "display_rules", "types": list(DISPLAY_TYPES)})
    missing = [t for t in DISPLAY_TYPES if not (dr.get("items") or {}).get(t)]
    assert not missing, f"display_rules knows no {missing}: {dr}"
    assert (dr.get("items"), dr.get("constants")) == (drh.get("items"), drh.get("constants")), (
        f"display_rules differ between the machines: host={drh} client={dr}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    ub = session.units_by_id(hs)
    ctx = {"rules": dr["items"], "constants": dr["constants"], "rng0": rng_of(client), "rngHost0": rng_of(host)}
    dials = {gc.name: (event_state(gc).get("speed") or {}).get("seats") for gc in (host, client)}
    print(f"[w2p5-sb] boot ok: {MISSION} MAP_FP={MAP_FP!r} mod={ml} turn={hs['turn']} H={H_ID} "
          f"({ubrief(ub.get(H_ID))}) pinned={len(pinned)} items={len(items_by_id(host))} coopGhostStepper={opts} "
          f"dials={dials} rngClient={ctx['rng0']} display_rules={json.dumps(dr, sort_keys=True)}", flush=True)
    return ctx


def main():
    t0 = time.time()
    host = GameClient("host", 49890, make_user_dir("w2p5_ghost_impact_host", mods=[MOD_DIR],
                                                   options={"coopGhostStepper": True}))
    client = GameClient("client", 49891, make_user_dir("w2p5_ghost_impact_client", mods=[MOD_DIR],
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
                print(f"[w2p5-sb] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_ghost_impact: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
