"""W2-P2 S-D - test_w2_host_combat_terrain.py: the host's own combat that
changes TERRAIN runs as proper actions with cue events, and the second player
ends every one of them with the host's exact state (spec
rewrite/prompts/w2p2_delta_core.md section (f) "test_w2_host_combat_terrain.py
(S-D)", sections (b)10-14 and (b)16; amendments A1, A2 and the A4/A5
SEQUENCING note; owner ruling D128 = (b)).

Stage S-D is TEST-ONLY: the product is complete for these scenarios (S-A/S-B
delta, S-C contexts + cues, S-L lighting). A scenario that fails here is a
product finding, never a reason to change product code or this test.

Three scenarios, ONE boot, in this order (the TASK 0a-2 one-boot order):

  C2  aimed shot into a wall. H gets a rifle + clip (battle_give on BOTH, ids
      equal), H -> C2_H_TILE facing C2_H_DIR (the fence north wall 4 tiles
      south), H firing 120 (BOTH). Host: set_seed SEED_C2, battle_fire
      {mode aimed, C2_WALL, tu max}. GREEN: the host event_log for the action
      is exactly shot -> hit -> bt_action_end (every one with `h`, the client
      log holds the same seqs/kinds/actionId); the `shot` payload's
      impactVoxel lies on C2_WALL and its `impact` is the wall part's V_* code
      (V_NORTHWALL); the `hit` payload names no unit; tile_info C2_WALL parts
      equal on both and changed from before on the host; the light census
      equal on both (below); the common asserts.
  C3  grenade: prime, throw, explode at end of turn. H gets a grenade
      (clear_hands, BOTH), H -> C3_H_TILE facing C3_H_DIR (AWAY from the throw
      tile: a throw at a tile the thrower already faces was a no-op, F490),
      H TU max (BOTH). Host real-UI prime: TAB-select H, the right-hand box
      (clicked once more first while H is still in aim mode after C2's shot,
      amendment A2.3 / F503), key 49 (PRIME), PrimeGrenadeState on top, key 48
      (fuse 0). Then host set_seed SEED_C3, battle_fire {mode throw,
      C3_THROW_TILE, tu max}. Then battle_drop a rifle clip on C3_ITEM_TILE on
      BOTH, both press END TURN, full cycle back to the player side. GREEN:
      after the prime - the action is exactly prime -> bt_action_end, the
      `prime` payload has fuse 0 (host log and the client's lastCue), the
      grenade's fuse is 0 on both, no bucket differs; after the throw - the
      action is exactly shot -> bt_action_end, the `shot` payload has action
      `throw` and an `arc` (host log and the client's lastCue), the grenade
      lies on C3_THROW_TILE on both with owner -1, no bucket differs; across
      the cycle - an `explosion` cue with actionId 0 whose centreVoxel lies on
      the landing tile (in both logs), the grenade and the clip absent on
      both, both machines on player turn N+1, the common asserts
      (battleInstantGrenade is false by default, Options.cpp:261).
  C4  rocket + chained terrain explosion. H gets a rocket launcher +
      STR_SMALL_ROCKET (xcom1 has no STR_HE_ROCKET: battle_give returned
      ammoId -1, F491), H -> C4_H_TILE facing C4_H_DIR, two rifle clips
      dropped on C4_ITEM_TILE (BOTH), H firing 120 (BOTH). Host: set_seed
      SEED_C4, battle_fire {mode aimed, C4_TARGET, tu max}. GREEN: the action
      starts with `shot` and ends with its `bt_action_end`, and holds >= 2
      `explosion` cues - one with chain 0 and one with chain >= 1 and
      `terrain` true (the gas pump at C4_PUMP, 1 link, amendment A2.4 / F505);
      every ev of the action carries `h` and the client log holds the same
      seqs/kinds/actionId; every clip id the host destroyed (>= 1) is absent
      on both; the terrain inside the blast is equal on both (hash_now
      `terrain`, part of the common asserts); the light census equal on both;
      the common asserts. The M1-B/M5/M6 probes (host deltaDiffUsMax,
      hashUsMax, deltaBytesMax; client deltaApplyUsMax, lightUsMax over a
      window zeroed right before the shot with light_probe_reset) are printed
      in the EVIDENCE line.

Cue payloads: event_log carries seq/kind/actionId/h only and lastCue holds the
last cue, so each payload is read from the host's own `[coop-cue] <kind> seq
<n> actionId <id>: <payload>` log line (openxcom.log, written by coopEmitCue
for every cue it sends) and, for the LAST cue of each step, compared with the
client's lastCue (the payload the client applied).

Light census on C2 and C4 (the A4/A5 SEQUENCING note; test_w2_light_scope.py's
light_census + staleness classifier, reused): after the staging both machines
recompute their light (light_recompute) and the baseline census must be equal
(identical synced state gives identical light); after the action the census
must be equal on all four layers and shade. On a mismatch the classifier runs:
CLIENT-stale (or BOTH-stale, or a difference that survives the recompute on
both) fails the scenario; HOST-stale only is the spec's Q-L3 - printed as a
`NOTE Q-L3` line with the classifier output, and the scenario is NOT failed on
it alone.

Common asserts (spec (f), after the action settles with wait_host_idle):
hash_now {full:true} - ALL buckets EQUAL on both machines (never a hard-coded
count); desyncSeen false on both; client coopClientBStatePushes unchanged and
host 0; client deltaEvsApplied increased; deltaUnresolved, deltaUnsupported,
deltaRemoveMissing and deltaAddExisting all 0 on both. The spec's C2/C3/C4
rows name no lastDelta class counts: each action's delta is split over its
cue envelopes, so which classes the LAST non-empty one holds depends on the
split; the tile, item and hash asserts prove the halves instead.

FIXTURE (deterministic, never searched here; W2-P2 TASK 0a-2 precalc,
amendment A2). STR_TERROR_MISSION, map seed SEED_MAP 12 (the first terror map
seed with the URBAN #81 gas pump, the only explosive terrain part). The roster
is pinned too: set_seed SEED_ROSTER on the HOST immediately before its
open_new_battle (names and stats repeat, amendment A2.2 / F501; C3's throw
distance depends on the throwing stat, F502) - a local bring-up helper - then
session.drive_to_battlescape with the mission pin and set_seed SEED_MAP right
before newbattle_ok, the baked MAP_FP asserted on both, session.pin_ai_neutral.
Every lever pair applies to the CLIENT first, then the HOST (F607, S-H.1a),
with the responses asserted equal; every item a lever creates is created on
both machines with ids asserted equal. set_seed on the HOST immediately before
each action.

RED: S-D adds no product commit; its red evidence is the TASK 0b M3 table at
the W2-P2 base (ledger `W2-P2 INTERIM - TASK 0b`): C2 froze the client on
unitsStats at the shot's own `reveal` ev (north wall (2,15) on the host vs
(2,13), clip 19 vs 20); C3 froze it at the prime/throw (grenade fuse 0 vs -1,
on the tile vs in the hand; gone vs present after the cycle); C4 froze it the
same way (clips gone vs present, pump gone vs present, 47 tiles changed on the
host only). GREEN = this file, ONE run, exit 0.

Each scenario prints ONE "EVIDENCE <id>:" line with both machines' fields
BEFORE its green conditions are checked; main() runs every scenario even
after an earlier one failed and prints "PASS <id>" / "FAIL <id>: <message>".
Every wait is bounded; a wait that times out is recorded in the EVIDENCE line
and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all three scenarios pass, 2
otherwise (a bring-up failure is also 2). WV-D95: run in the foreground to
completion.

Run:  python tools/coop_test/test_w2_host_combat_terrain.py
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_w2_delta_core import (probes, tile, diff_buckets, desync_record, short, both, tele_both, tu_both,
                                end_turn_cycle, common_fails, finish, delta_view)
from test_w2_delta_items import items_by_id, item_diff, tile_of, unit_view
from test_w2_host_combat import (cue_probes, evs_since, ev_tuples, chain_fails, chain_of, seq_of,
                                 open_hand_menu_host, press, red_view, cue_delta)
import test_w2_light_scope as ls

# ----- common (test_w2_host_combat.py and test_w2_host_combat_terrain.py; TASK 0a-2) -----
MISSION = "STR_TERROR_MISSION"
SEED_ROSTER = 1                  # set_seed on the HOST right before its open_new_battle (F501)
H_ID = 10                        # first host-seat soldier; with SEED_ROSTER 1 = "Henryk Kaminski",
                                 # tu 58, health 37, firing 46, throwing 73, melee 25, strength 45
KEY_ITEM1, KEY_FUSE_0 = 49, 48   # PRIME (grenade menu item 1), fuse 0
TU_MAX = 255                     # battle_set_unit_state / battle_fire tu: clamped to the unit's max TU
FIRST_LEVER_ITEM_ID = 96         # 96 items at start on both maps (ids 0..95)

# ----- test_w2_host_combat_terrain.py (S-D): C2 + C3 + C4 -----
SEED_MAP = 12                    # first terror map seed with an explosive terrain part (URBAN09 gas station)
MAP_FP = -2.6402710723327386e+18
C2_H_TILE, C2_H_DIR = (4, 16, 0), 4    # open road, facing the fence 4 tiles south
C2_WALL = (4, 20, 0)             # its NORTH wall: URBITS #13 (armor 8, die #15)
C2_WALL_PARTS = ((2, 13), (2, 15))     # northwall (setId, id) before -> after
SEED_C2 = 1                      # aimed battle_fire (firing 120): wall destroyed, clip 20 -> 19, H tu 58 -> 12
                                 # (rifle 96, clip 97; 3/3 standalone + 3/3 one-boot)
C3_H_TILE, C3_H_DIR = (5, 17, 0), 2    # faces east, AWAY from the throw tile (F490)
C3_THROW_TILE = (5, 11, 0)       # 6 tiles north (outside the blast at H); floor URBITS #16
C3_ITEM_TILE = (5, 11, 0)
SEED_C3 = 1                      # real-UI prime (key 49, fuse key 48) + battle_fire throw: lands (5,11,0), fuse 0,
                                 # owner -1, H tu 58 -> 42; END TURN cycle: grenade and clip gone, floor (2,16) ->
                                 # (2,22), host reaches turn 2 in 2.0 s, no unit hurt. Needs SEED_ROSTER (F502).
                                 # one-boot ids: grenade 98, clip 99 (3/3 standalone + 3/3 one-boot)
C4_H_TILE, C4_H_DIR = (22, 34, 0), 0
C4_TARGET = (21, 26, 0)          # ROADS #0 floor beside the pump (20,26,0)
C4_ITEM_TILE = (21, 26, 0)
C4_PUMP = (20, 26, 0)            # object URBAN #81 (HE 46, armor 18, die 0) -> removed; floor (3,74) -> (3,75)
C4_ROCKET = "STR_SMALL_ROCKET"
SEED_C4 = 1                      # aimed battle_fire: both clips destroyed, pump destroyed and its explosive consumed
                                 # (= 1 chained terrain explosion, F505), 47 tiles changed (z 0 and the z 1 canopy),
                                 # only H changed (tu 58 -> 15); action 2.5 s. one-boot ids: launcher 100,
                                 # rocket 101, clips 102/103 (3/3 standalone + 3/3 one-boot)
C4_CHAIN_LINKS = 1               # the next pump (20,23,0) survives: longest chain from this target = 1 link (M1-B)

PORT = "48626"
FACTION_PLAYER = 0
FACTION_HOSTILE = 1
COOP_SEAT_0 = 0
FIRING_120 = 120
V_NORTHWALL = 2                  # src/Mod/MapData.h enum VoxelType
VOXEL = (16, 16, 24)             # voxels per tile (x, y, z)
C2_CHAIN = ["shot", "hit", "bt_action_end"]
C3_PRIME_CHAIN = ["prime", "bt_action_end"]
C3_THROW_CHAIN = ["shot", "bt_action_end"]
# coopEmitCue's host log line (connectionTCP.cpp): one per cue the host sends.
CUE_RE = re.compile(r"\[coop-cue\] (\S+) seq (\d+) actionId (\d+): (\{.*\})\s*$", re.M)


# ===================== small probes =====================


def top(gc):
    return session.top_state(gc)


def units(gc):
    return session.units_by_id(battle_state(gc))


def voxel_tile(v):
    """The tile (x, y, z) a cue voxel {x,y,z} lies in (None if absent)."""
    if not isinstance(v, dict):
        return None
    return (v.get("x", 0) // VOXEL[0], v.get("y", 0) // VOXEL[1], v.get("z", 0) // VOXEL[2])


def host_cues(host, seqs, timeout=5.0):
    """{seq: {kind, actionId, payload}} from the HOST's own openxcom.log
    `[coop-cue]` lines for every seq in `seqs`, read with a bounded wait for the
    log write to land."""
    path = os.path.join(host.user_dir, "openxcom.log")
    want = set(seqs)
    deadline = time.time() + timeout
    found = {}
    while True:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            text = ""
        found = {}
        for m in CUE_RE.finditer(text):
            s = int(m.group(2))
            if s in want:
                try:
                    payload = json.loads(m.group(4))
                except ValueError as e:
                    payload = {"unparsed": m.group(4)[:300], "error": str(e)}
                found[s] = {"kind": m.group(1), "actionId": int(m.group(3)), "payload": payload}
        if want <= set(found) or time.time() >= deadline:
            return found
        time.sleep(0.25)


def host_action_done(host):
    """HOST only: no BState queued or running, BattlescapeState on top, no
    action context open (busyOwnerSeat -1)."""
    bs = battle_state(host)
    return (bs.get("pendingStates") == 0 and not bs.get("isBusy") and top(host) == "BattlescapeState"
            and event_state(host).get("busyOwnerSeat") == -1) or None


def settle_after_action(host, client, what, notes, timeout=30):
    """Bounded: the host's action chain has finished (host-only predicate, so a
    frozen client keeps its evidence), then wait_host_idle (client caught up)."""
    try:
        host.wait_for(f"host {what} finished (no BState, no action context)", lambda: host_action_done(host),
                      timeout=timeout)
    except Exception as e:
        notes.append(f"host {what}: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=timeout)
    except Exception as e:
        notes.append(f"wait_host_idle after {what}: {short(e)}")


def last_cue_fails(lc, aid, seq, host_cue, kind):
    """The client's lastCue must be the host's `kind` cue at `seq` (same
    actionId and payload)."""
    lc = lc or {}
    want_pl = (host_cue or {}).get("payload")
    if (lc.get("kind") != kind or lc.get("actionId") != aid or lc.get("seq") != seq
            or want_pl is None or lc.get("payload") != want_pl):
        return [f"client lastCue={lc or None} (want kind {kind}, actionId {aid}, seq {seq}, payload = the host's "
                f"{want_pl})"]
    return []


def cue_view(cues, seqs):
    return [(s, (cues.get(s) or {}).get("kind"), (cues.get(s) or {}).get("payload")) for s in seqs]


# ===================== light census (A4/A5 SEQUENCING note) =====================


def light_baseline(host, client, tag):
    """light_recompute on BOTH machines, then the baseline census. Returns
    (evidence, error): error when the recompute failed or the census differs
    (identical synced state must give identical light - a hidden input)."""
    rh, rc = host.cmd({"cmd": "light_recompute"}), client.cmd({"cmd": "light_recompute"})
    if not (rh.get("ok") and rc.get("ok")):
        return ({"recompute": {"host": rh, "client": rc}},
                f"{tag} baseline light_recompute failed: host={rh} client={rc}")
    ch, cc = ls.census(host, tag + "_baseline"), ls.census(client, tag + "_baseline")
    mism = ls.census_mismatch(ch, cc)
    diff = ls.tile_diffs(ch["bytes"], cc["bytes"])
    ev = {"mismatch": mism, "tilesDiffer": len(diff), "first (host client)": ls.fmt_tiles(ch, cc, diff),
          "host": ls.census_view(ch), "client": ls.census_view(cc)}
    if mism or diff:
        return ev, (f"{tag} baseline light census differs after light_recompute on both machines {mism}: "
                    f"{len(diff)} tile(s), first (host client) {ev['first (host client)']}; dumps "
                    f"host={ch['path']} client={cc['path']}")
    return ev, None


def light_after(host, client, tag):
    """Census after the action with the staleness classifier on a mismatch.
    Returns (fails, evidence, verdict). HOST-stale only (the spec's Q-L3) is
    printed as a NOTE and does not fail."""
    ch, cc = ls.census(host, tag + "_after"), ls.census(client, tag + "_after")
    cfails, cev = ls.census_check(host, client, ch, cc, tag + "_after")
    verdict = (cev.get("classifier") or {}).get("verdict")
    if cfails and verdict == "HOST-stale only":
        print(f"NOTE Q-L3 {tag}: light census differs after the action and the classifier says HOST-stale "
              f"only (vanilla's own history-dependent local recompute, A4 note N5) - recorded, not failed; "
              f"census={cev}", flush=True)
        cfails = []
    return cfails, cev, verdict


# ===================== scenarios =====================


def c2_wall(host, client, ctx):
    notes = []
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": "STR_RIFLE", "ammo": "STR_RIFLE_CLIP",
                            "clear_hands": True}, ("weaponId", "ammoId"))
    rifle, clip = g["weaponId"], g["ammoId"]
    tele_both(host, client, H_ID, C2_H_TILE, C2_H_DIR)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": H_ID, "stat": "firing",
                        "value": FIRING_120}, ("tu",))
    staged_diff = diff_buckets(host, client)
    w0 = {"host": tile(host, C2_WALL), "client": tile(client, C2_WALL)}
    lbase, lberr = light_baseline(host, client, "C2")
    before = {"host": probes(host), "client": probes(client)}
    cb = {"host": cue_probes(host), "client": cue_probes(client)}
    seq0 = before["host"]["lastSeqEmitted"] or 0
    host.ok({"cmd": "set_seed", "seed": SEED_C2})
    fire = host.cmd({"cmd": "battle_fire", "unit": H_ID, "mode": "aimed", "x": C2_WALL[0], "y": C2_WALL[1],
                     "z": C2_WALL[2], "tu": TU_MAX})
    if not fire.get("ok"):
        notes.append(f"battle_fire aimed refused: {fire}")
    settle_after_action(host, client, "aimed shot", notes)
    uh, uc = units(host), units(client)
    ih, ic = items_by_id(host), items_by_id(client)
    ph, pc = probes(host), probes(client)
    ca = {"host": cue_probes(host), "client": cue_probes(client)}
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    dsc = desync_record(client, pc["desyncSeen"])
    end_diff = diff_buckets(host, client)
    w1 = {"host": tile(host, C2_WALL), "client": tile(client, C2_WALL)}
    aid, chain, cfails = chain_fails(hev, cev, "shot", C2_CHAIN, seq0)
    cues = host_cues(host, [e["seq"] for e in chain if e["kind"] != "bt_action_end"])
    shot = cues.get(seq_of(chain, "shot")) or {}
    hit = cues.get(seq_of(chain, "hit")) or {}
    spl, hpl = shot.get("payload") or {}, hit.get("payload") or {}
    lfails, lev, lverdict = light_after(host, client, "C2")
    clip1 = {"host": (ih.get(clip) or {}).get("qty"), "client": (ic.get(clip) or {}).get("qty")}
    idiff = item_diff(ih, ic)
    print(f"EVIDENCE C2: staged rifle={rifle} clip={clip} H->{C2_H_TILE}/{C2_H_DIR} stagedDiff={staged_diff}; "
          f"battle_fire={fire}; hostCombatContexts host {cb['host']['hostCombatContexts']}->"
          f"{ca['host']['hostCombatContexts']}; host evs since seq {seq0}={ev_tuples(hev)} client evs="
          f"{ev_tuples(cev)} (seq, kind, actionId, h); red view={red_view(hev, cev)}; action={aid} chain="
          f"{[(e['seq'], e['kind'], e['actionId']) for e in chain]}; host cue payloads="
          f"{cue_view(cues, [e['seq'] for e in chain if e['kind'] != 'bt_action_end'])}; shot impactVoxel tile="
          f"{voxel_tile(spl.get('impactVoxel'))} impact={spl.get('impact')} (want {C2_WALL}, V_NORTHWALL "
          f"{V_NORTHWALL}); cueCounts delta host={cue_delta(cb['host']['cueCounts'], ca['host']['cueCounts'])} "
          f"client={cue_delta(cb['client']['cueCounts'], ca['client']['cueCounts'])}; lastCue client="
          f"{ca['client']['lastCue']}; wall {C2_WALL} before={w0} after={w1} (northwall want "
          f"{C2_WALL_PARTS[0]}->{C2_WALL_PARTS[1]}); clip {clip} qty={clip1}; H after host="
          f"{unit_view(uh.get(H_ID))} tu={(uh.get(H_ID) or {}).get('tu')} client={unit_view(uc.get(H_ID))} "
          f"tu={(uc.get(H_ID) or {}).get('tu')}; items hostOnly={sorted(idiff['hostOnly'])} clientOnly="
          f"{sorted(idiff['clientOnly'])} differ={idiff['differ']}; light baseline={lbase} "
          f"err={lberr}; light after={lev} verdict={lverdict}; client desyncSeen={pc['desyncSeen']} "
          f"desync={dsc} host desyncSeen={ph['desyncSeen']}; diffAfterShot={end_diff}; host lastDelta="
          f"{ph['lastDelta']} client lastDelta={pc['lastDelta']}; host {delta_view(before['host'])}->"
          f"{delta_view(ph)}; client {delta_view(before['client'])}->{delta_view(pc)}; notes={notes}",
          flush=True)
    fails = list(notes)
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    if lberr:
        fails.append(lberr)
    # spec (f) C2 GREEN: shot -> hit -> bt_action_end
    fails += cfails
    if voxel_tile(spl.get("impactVoxel")) != C2_WALL or spl.get("impact") != V_NORTHWALL:
        fails.append(f"shot payload impactVoxel tile={voxel_tile(spl.get('impactVoxel'))} impact="
                     f"{spl.get('impact')} (want {C2_WALL}, V_NORTHWALL {V_NORTHWALL}); payload={spl}")
    if not hpl or "unit" in hpl:
        fails.append(f"hit payload {hpl or None} (want present, with no unit)")
    fails += last_cue_fails(ca["client"]["lastCue"], aid, seq_of(chain, "hit"), hit, "hit")
    # tile_info C2_WALL parts equal on both and changed from before on the host
    if not w1["host"] or not w1["client"] or w1["host"]["parts"] != w1["client"]["parts"]:
        fails.append(f"wall {C2_WALL} parts host={(w1['host'] or {}).get('parts')} "
                     f"client={(w1['client'] or {}).get('parts')} (want equal)")
    if not w0["host"] or not w1["host"] or w1["host"]["parts"] == w0["host"]["parts"]:
        fails.append(f"wall {C2_WALL} parts on the host did not change: before={(w0['host'] or {}).get('parts')} "
                     f"after={(w1['host'] or {}).get('parts')}")
    fails += lfails
    fails += common_fails(host, client, before, {}, "C2")
    finish(fails)


def c3_grenade(host, client, ctx):
    notes = []
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": "STR_GRENADE", "clear_hands": True},
             ("weaponId", "ammoId"))
    gid = g["weaponId"]
    tele_both(host, client, H_ID, C3_H_TILE, C3_H_DIR)
    tu_both(host, client, H_ID)
    staged_diff = diff_buckets(host, client)
    before = {"host": probes(host), "client": probes(client)}
    cb = {"host": cue_probes(host), "client": cue_probes(client)}
    seq0 = before["host"]["lastSeqEmitted"] or 0

    # --- the prime: real UI (PRIME key, fuse 0) ---
    cursor0, prime_top = None, None
    try:
        cursor0 = open_hand_menu_host(host)
        press(host, KEY_ITEM1)
        host.wait_for("host PrimeGrenadeState on top", lambda: top(host) == "PrimeGrenadeState" or None,
                      timeout=5)
        prime_top = top(host)
        press(host, KEY_FUSE_0)
        host.wait_for("host BattlescapeState on top after the fuse key",
                      lambda: top(host) == "BattlescapeState" or None, timeout=5)
        # the prime's own effect on the host (vanilla setFuseTimer), so the
        # capture below never races the key's handling
        host.wait_for("host grenade fuse 0", lambda: (items_by_id(host).get(gid) or {}).get("fuse") == 0 or None,
                      timeout=10)
    except Exception as e:
        notes.append(f"host prime: {short(e)} (top {top(host)})")
    settle_after_action(host, client, "prime", notes)
    ih_p, ic_p = items_by_id(host), items_by_id(client)
    cp1 = {"host": cue_probes(host), "client": cue_probes(client)}
    hev_p, cev_p = evs_since(host, seq0), evs_since(client, seq0)
    diff_p = diff_buckets(host, client)
    aid_p, chain_p, pfails = chain_fails(hev_p, cev_p, "prime", C3_PRIME_CHAIN, seq0)
    pcues = host_cues(host, [e["seq"] for e in chain_p if e["kind"] == "prime"])
    prime = pcues.get(seq_of(chain_p, "prime")) or {}
    ppl = prime.get("payload") or {}
    fuse_p = {"host": (ih_p.get(gid) or {}).get("fuse"), "client": (ic_p.get(gid) or {}).get("fuse")}
    lc_prime = cp1["client"]["lastCue"]
    seq1 = probes(host)["lastSeqEmitted"] or 0

    # --- the throw: battle_fire throw (the thrower faces away, F490) ---
    host.ok({"cmd": "set_seed", "seed": SEED_C3})
    fire = host.cmd({"cmd": "battle_fire", "unit": H_ID, "mode": "throw", "x": C3_THROW_TILE[0],
                     "y": C3_THROW_TILE[1], "z": C3_THROW_TILE[2], "tu": TU_MAX})
    if not fire.get("ok"):
        notes.append(f"battle_fire throw refused: {fire}")
    settle_after_action(host, client, "throw", notes)
    ih_t, ic_t = items_by_id(host), items_by_id(client)
    cp2 = {"host": cue_probes(host), "client": cue_probes(client)}
    hev_t, cev_t = evs_since(host, seq1), evs_since(client, seq1)
    diff_t = diff_buckets(host, client)
    aid_t, chain_t, tfails = chain_fails(hev_t, cev_t, "shot", C3_THROW_CHAIN, seq1)
    tcues = host_cues(host, [e["seq"] for e in chain_t if e["kind"] == "shot"])
    shot = tcues.get(seq_of(chain_t, "shot")) or {}
    spl = shot.get("payload") or {}
    g_t = {"host": ih_t.get(gid), "client": ic_t.get(gid)}
    landed = tile_of(g_t["host"])
    lc_throw = cp2["client"]["lastCue"]

    # --- a clip on the landing tile (BOTH), then END TURN and the full cycle ---
    clip = both(host, client, {"cmd": "battle_drop", "x": C3_ITEM_TILE[0], "y": C3_ITEM_TILE[1],
                               "z": C3_ITEM_TILE[2], "item": "STR_RIFLE_CLIP"}, ("ids",))["ids"][0]
    seq2 = probes(host)["lastSeqEmitted"] or 0
    t0 = {"host": tile(host, C3_THROW_TILE), "client": tile(client, C3_THROW_TILE)}
    turn0 = end_turn_cycle(host, client, notes)
    hs, cs = battle_state(host), battle_state(client)
    ih, ic = items_by_id(host), items_by_id(client)
    ph, pc = probes(host), probes(client)
    ca = {"host": cue_probes(host), "client": cue_probes(client)}
    hev_c, cev_c = evs_since(host, seq2), evs_since(client, seq2)
    dsc = desync_record(client, pc["desyncSeen"])
    end_diff = diff_buckets(host, client)
    t1 = {"host": tile(host, C3_THROW_TILE), "client": tile(client, C3_THROW_TILE)}
    expl = [e for e in hev_c if e["kind"] == "explosion"]
    ecues = host_cues(host, [e["seq"] for e in expl])
    cmap = {e["seq"]: e for e in cev_c}
    idiff = item_diff(ih, ic)
    print(f"EVIDENCE C3: staged grenade={gid} H->{C3_H_TILE}/{C3_H_DIR} stagedDiff={staged_diff}; "
          f"PRIME: cursorType(before[, after the aim-cancel click])={cursor0} top after key 49={prime_top} "
          f"host evs since seq {seq0}={ev_tuples(hev_p)} client evs={ev_tuples(cev_p)} (seq, kind, actionId, h) "
          f"action={aid_p} chain={[(e['seq'], e['kind'], e['actionId']) for e in chain_p]} prime payload={ppl} "
          f"client lastCue={lc_prime} grenade fuse={fuse_p} diffAfterPrime={diff_p}; "
          f"THROW: battle_fire={fire} host evs since seq {seq1}={ev_tuples(hev_t)} client evs="
          f"{ev_tuples(cev_t)} action={aid_t} chain={[(e['seq'], e['kind'], e['actionId']) for e in chain_t]} "
          f"shot payload={spl} client lastCue={lc_throw} grenade host={g_t['host']} client={g_t['client']} "
          f"landed={landed} diffAfterThrow={diff_t}; hostCombatContexts host "
          f"{cb['host']['hostCombatContexts']}->{cp1['host']['hostCombatContexts']}->"
          f"{cp2['host']['hostCombatContexts']}; CYCLE: clip={clip} turn {turn0} -> host=({hs.get('turn')},"
          f"{hs.get('side')}) client=({cs.get('turn')},{cs.get('side')}); host evs since seq {seq2}="
          f"{[(e['seq'], e['kind'], e['actionId']) for e in hev_c]} client evs="
          f"{[(e['seq'], e['kind'], e['actionId']) for e in cev_c]}; explosion cues="
          f"{cue_view(ecues, [e['seq'] for e in expl])} centre tiles="
          f"{[voxel_tile(((ecues.get(e['seq']) or {}).get('payload') or {}).get('centreVoxel')) for e in expl]}; "
          f"throw tile {C3_THROW_TILE} before={t0} after={t1}; grenade present host={gid in ih} "
          f"client={gid in ic}; clip present host={clip in ih} client={clip in ic}; items hostOnly="
          f"{sorted(idiff['hostOnly'])} clientOnly={sorted(idiff['clientOnly'])} differ={idiff['differ']}; "
          f"cueCounts delta host={cue_delta(cb['host']['cueCounts'], ca['host']['cueCounts'])} client="
          f"{cue_delta(cb['client']['cueCounts'], ca['client']['cueCounts'])}; lastCue client="
          f"{ca['client']['lastCue']}; client desyncSeen={pc['desyncSeen']} desync={dsc} host desyncSeen="
          f"{ph['desyncSeen']}; diffAfterCycle={end_diff}; host lastDelta={ph['lastDelta']} client lastDelta="
          f"{pc['lastDelta']}; host {delta_view(before['host'])}->{delta_view(ph)}; client "
          f"{delta_view(before['client'])}->{delta_view(pc)}; notes={notes}", flush=True)
    fails = list(notes)
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    # after the prime: prime (fuse 0) + its bt_action_end, grenade fuse 0 on both
    fails += [f"prime: {m}" for m in pfails]
    if ppl.get("fuse") != 0 or ppl.get("item") != gid or ppl.get("unprime") is not False:
        fails.append(f"prime payload {ppl or None} (want item {gid}, fuse 0, unprime false)")
    fails += [f"prime: {m}" for m in last_cue_fails(lc_prime, aid_p, seq_of(chain_p, "prime"), prime, "prime")]
    if fuse_p["host"] != 0 or fuse_p["client"] != 0:
        fails.append(f"grenade {gid} fuse after the prime host={fuse_p['host']} client={fuse_p['client']} "
                     f"(want 0 on both)")
    if diff_p:
        fails.append(f"buckets differ after the prime: {diff_p} (want none)")
    # after the throw: shot (action throw, arc) + bt_action_end, grenade on C3_THROW_TILE on both, owner -1
    fails += [f"throw: {m}" for m in tfails]
    if spl.get("action") != "throw" or not isinstance(spl.get("arc"), dict):
        fails.append(f"throw shot payload {spl or None} (want action throw with an arc)")
    fails += [f"throw: {m}" for m in last_cue_fails(lc_throw, aid_t, seq_of(chain_t, "shot"), shot, "shot")]
    for name, it in g_t.items():
        if not it or tile_of(it) != C3_THROW_TILE or it.get("owner") != -1:
            fails.append(f"{name} grenade {gid} after the throw {it} (want on {C3_THROW_TILE}, owner -1)")
    if diff_t:
        fails.append(f"buckets differ after the throw: {diff_t} (want none)")
    # across the cycle: explosion (actionId 0, centre on the landing tile), grenade and clip gone on both
    good = [e for e in expl if e["actionId"] == 0 and landed is not None
            and voxel_tile(((ecues.get(e["seq"]) or {}).get("payload") or {}).get("centreVoxel")) == landed]
    if not good:
        fails.append(f"no host `explosion` ev with actionId 0 centred on the landing tile {landed} in the cycle "
                     f"(explosions {cue_view(ecues, [e['seq'] for e in expl])})")
    for e in good:
        ce = cmap.get(e["seq"])
        if not ce or ce["kind"] != "explosion" or ce["actionId"] != 0:
            fails.append(f"client event_log at explosion seq {e['seq']}: {ce} (want kind explosion, actionId 0)")
    for name, present in (("grenade", {"host": gid in ih, "client": gid in ic}),
                          ("clip", {"host": clip in ih, "client": clip in ic})):
        if present["host"] or present["client"]:
            fails.append(f"{name} after the cycle present host={present['host']} client={present['client']} "
                         f"(want absent on both)")
    if (hs.get("turn"), hs.get("side"), cs.get("turn"), cs.get("side")) != (turn0 + 1, FACTION_PLAYER,
                                                                             turn0 + 1, FACTION_PLAYER):
        fails.append(f"not on player turn {turn0 + 1} on both: host=({hs.get('turn')},{hs.get('side')}) "
                     f"client=({cs.get('turn')},{cs.get('side')})")
    fails += common_fails(host, client, before, {}, "C3")
    finish(fails)


def c4_chain_fails(host_evs, client_evs, seq0):
    """Spec (f) C4 GREEN: the action (found through its first `shot`) starts
    with `shot`, ends with its `bt_action_end`, holds >= 2 `explosion` cues;
    every ev carries `h`; the client log holds the same seqs/kinds/actionId.
    Returns (actionId, chain, fails)."""
    fails = []
    aid, chain = chain_of(host_evs, "shot")
    if aid is None:
        fails.append(f"host event_log has no `shot` ev since seq {seq0} (host evs={ev_tuples(host_evs)})")
        return aid, chain, fails
    if aid == 0:
        fails.append("the host's first `shot` ev carries actionId 0 (want the host-local combat context's id)")
    kinds = [e["kind"] for e in chain]
    if not kinds or kinds[0] != "shot" or kinds[-1] != "bt_action_end":
        fails.append(f"host event_log for actionId {aid} = {kinds} (want shot first, bt_action_end last)")
    if kinds.count("explosion") < 2:
        fails.append(f"host event_log for actionId {aid} = {kinds}: {kinds.count('explosion')} explosion cue(s) "
                     f"(want >= 2 before its bt_action_end)")
    noh = [e["seq"] for e in chain if not e["h"]]
    if noh:
        fails.append(f"host evs of actionId {aid} without `h`: seqs {noh} (want every one with h)")
    cmap = {e["seq"]: e for e in client_evs}
    bad = [(e["seq"], e["kind"], cmap.get(e["seq"])) for e in chain
           if not cmap.get(e["seq"]) or cmap[e["seq"]]["kind"] != e["kind"] or cmap[e["seq"]]["actionId"] != aid]
    if bad:
        fails.append(f"client event_log does not hold the host's seqs/kinds for actionId {aid}: "
                     f"(seq, host kind, client entry)={bad}")
    return aid, chain, fails


def c4_rocket(host, client, ctx):
    notes = []
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": "STR_ROCKET_LAUNCHER", "ammo": C4_ROCKET,
                            "clear_hands": True}, ("weaponId", "ammoId"))
    launcher, rocket = g["weaponId"], g["ammoId"]
    tele_both(host, client, H_ID, C4_H_TILE, C4_H_DIR)
    clips = both(host, client, {"cmd": "battle_drop", "x": C4_ITEM_TILE[0], "y": C4_ITEM_TILE[1],
                                "z": C4_ITEM_TILE[2], "item": "STR_RIFLE_CLIP", "count": 2}, ("ids",))["ids"]
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": H_ID, "stat": "firing",
                        "value": FIRING_120}, ("tu",))
    staged_diff = diff_buckets(host, client)
    pump0 = {"host": tile(host, C4_PUMP), "client": tile(client, C4_PUMP)}
    target0 = {"host": tile(host, C4_TARGET), "client": tile(client, C4_TARGET)}
    lbase, lberr = light_baseline(host, client, "C4")
    rr = client.cmd({"cmd": "light_probe_reset"})  # M6 window: the client's apply/light max over this action
    if not rr.get("ok"):
        notes.append(f"light_probe_reset on the client: {rr}")
    before = {"host": probes(host), "client": probes(client)}
    cb = {"host": cue_probes(host), "client": cue_probes(client)}
    m0 = event_state(host)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    host.ok({"cmd": "set_seed", "seed": SEED_C4})
    a0 = time.time()
    fire = host.cmd({"cmd": "battle_fire", "unit": H_ID, "mode": "aimed", "x": C4_TARGET[0], "y": C4_TARGET[1],
                     "z": C4_TARGET[2], "tu": TU_MAX})
    if not fire.get("ok"):
        notes.append(f"battle_fire aimed refused: {fire}")
    settle_after_action(host, client, "rocket shot", notes)
    secs = round(time.time() - a0, 1)
    ih, ic = items_by_id(host), items_by_id(client)
    ph, pc = probes(host), probes(client)
    mh, mc = event_state(host), event_state(client)
    ca = {"host": cue_probes(host), "client": cue_probes(client)}
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    dsc = desync_record(client, pc["desyncSeen"])
    end_diff = diff_buckets(host, client)
    aid, chain, cfails = c4_chain_fails(hev, cev, seq0)
    cue_seqs = [e["seq"] for e in chain if e["kind"] != "bt_action_end"]
    cues = host_cues(host, cue_seqs)
    expl = [(e["seq"], (cues.get(e["seq"]) or {}).get("payload") or {}) for e in chain if e["kind"] == "explosion"]
    chains = [(s, p.get("chain"), p.get("terrain"), voxel_tile(p.get("centreVoxel")), p.get("radius"),
               p.get("power")) for s, p in expl]
    last_seq = cue_seqs[-1] if cue_seqs else None
    pump1 = {"host": tile(host, C4_PUMP), "client": tile(client, C4_PUMP)}
    target1 = {"host": tile(host, C4_TARGET), "client": tile(client, C4_TARGET)}
    destroyed = [c for c in clips if c not in ih]
    lfails, lev, lverdict = light_after(host, client, "C4")
    idiff = item_diff(ih, ic)
    uh, uc = units(host), units(client)
    m1b = {"host deltaDiffUs last/max": (mh.get("deltaDiffUsLast"), f"{m0.get('deltaDiffUsMax')}->"
                                         f"{mh.get('deltaDiffUsMax')}"),
           "host hashUs last/max": (mh.get("hashUsLast"), f"{m0.get('hashUsMax')}->{mh.get('hashUsMax')}"),
           "host deltaBytes last/max": (mh.get("deltaBytesLast"), f"{m0.get('deltaBytesMax')}->"
                                        f"{mh.get('deltaBytesMax')}"),
           "client deltaApplyUs last/max(window)": (mc.get("deltaApplyUsLast"), mc.get("deltaApplyUsMax")),
           "client lightUsMax(window)": mc.get("lightUsMax"), "light_probe_reset": rr}
    print(f"EVIDENCE C4: staged launcher={launcher} rocket={rocket} clips={clips} H->{C4_H_TILE}/{C4_H_DIR} "
          f"stagedDiff={staged_diff}; battle_fire={fire} action wall {secs}s; hostCombatContexts host "
          f"{cb['host']['hostCombatContexts']}->{ca['host']['hostCombatContexts']}; host evs since seq {seq0}="
          f"{ev_tuples(hev)} client evs={ev_tuples(cev)} (seq, kind, actionId, h); action={aid} chain="
          f"{[(e['seq'], e['kind'], e['actionId']) for e in chain]}; host cue payloads={cue_view(cues, cue_seqs)}; "
          f"explosions (seq, chain, terrain, centre tile, radius, power)={chains}; cueCounts delta host="
          f"{cue_delta(cb['host']['cueCounts'], ca['host']['cueCounts'])} client="
          f"{cue_delta(cb['client']['cueCounts'], ca['client']['cueCounts'])}; lastCue client="
          f"{ca['client']['lastCue']}; pump {C4_PUMP} before={pump0} after={pump1}; target {C4_TARGET} before="
          f"{target0} after={target1}; clips destroyed on the host={destroyed} present host="
          f"{[c for c in clips if c in ih]} client={[c for c in clips if c in ic]}; H after host="
          f"{unit_view(uh.get(H_ID))} tu={(uh.get(H_ID) or {}).get('tu')} client={unit_view(uc.get(H_ID))} "
          f"tu={(uc.get(H_ID) or {}).get('tu')}; items hostOnly={sorted(idiff['hostOnly'])} clientOnly="
          f"{sorted(idiff['clientOnly'])} differ={idiff['differ']}; M1-B/M5/M6={m1b}; light baseline={lbase} "
          f"err={lberr}; light after={lev} verdict={lverdict}; client desyncSeen={pc['desyncSeen']} "
          f"desync={dsc} host desyncSeen={ph['desyncSeen']}; diffAfterShot={end_diff}; host lastDelta="
          f"{ph['lastDelta']} client lastDelta={pc['lastDelta']}; host {delta_view(before['host'])}->"
          f"{delta_view(ph)}; client {delta_view(before['client'])}->{delta_view(pc)}; notes={notes}",
          flush=True)
    fails = list(notes)
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    if rocket is None or rocket < 0:
        fails.append(f"battle_give gave no {C4_ROCKET} (ammoId {rocket}, F491)")
    if lberr:
        fails.append(lberr)
    # spec (f) C4 GREEN: >= 2 explosion cues (chain 0 and chain >= 1 with terrain true) before bt_action_end
    fails += cfails
    if not any(c == 0 for _, c, _, _, _, _ in chains):
        fails.append(f"no explosion cue with chain 0 in the action: {chains}")
    if not any(isinstance(c, int) and c >= 1 and t is True for _, c, t, _, _, _ in chains):
        fails.append(f"no chained explosion cue (chain >= 1, terrain true) in the action: {chains}")
    if last_seq is not None:
        fails += last_cue_fails(ca["client"]["lastCue"], aid, last_seq, cues.get(last_seq),
                                (cues.get(last_seq) or {}).get("kind"))
    # every clip id the host destroyed (>= 1) absent on both
    if not destroyed:
        fails.append(f"the host destroyed none of the clips {clips} (want >= 1)")
    for c in destroyed:
        if c in ic:
            fails.append(f"clip {c} destroyed on the host but present on the client: {ic.get(c)}")
    fails += lfails
    fails += common_fails(host, client, before, {}, "C4")
    finish(fails)


SCENARIOS = (("C2", c2_wall), ("C3", c3_grenade), ("C4", c4_rocket))


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
    pinned = pin_ai_neutral(host, client, tag="w2p2-sd")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    ub = session.units_by_id(hs)
    n_items = len(items_by_id(host))  # evidence only (precalc: FIRST_LEVER_ITEM_ID items at start)
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("hostCombatContexts"), int) and isinstance(es.get("cueCounts"), dict)
                and "lastCue" in es), (
            f"{gc.name} event_state lacks the S-C probes: hostCombatContexts={es.get('hostCombatContexts')!r} "
            f"cueCounts={es.get('cueCounts')!r} lastCue present={'lastCue' in es}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    ph = probes(host)
    print(f"[w2p2-sd] boot ok: {MISSION} SEED_MAP={SEED_MAP} MAP_FP={MAP_FP!r} turn={hs['turn']} H={H_ID} "
          f"({(ub.get(H_ID) or {}).get('name')}) pinned={len(pinned)} items={n_items} (precalc "
          f"{FIRST_LEVER_ITEM_ID}) host deltaArmed="
          f"{ph['deltaArmed']} deltaSeeds={ph['deltaSeeds']} probes host={cue_probes(host)} "
          f"client={cue_probes(client)}", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49848, make_user_dir("w2p2_host_combat_terrain_host"))
    client = GameClient("client", 49849, make_user_dir("w2p2_host_combat_terrain_client"))
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
                print(f"[w2p2-sd] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_host_combat_terrain: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
