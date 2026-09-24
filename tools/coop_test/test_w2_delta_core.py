"""W2-P2 S-A - test_w2_delta_core.py: every host event carries the tile state
that changed since the previous event (spec rewrite/prompts/w2p2_delta_core.md
section (f) "test_w2_delta_core.py (S-A)", orchestrator rulings Q1 = (c) and
Q4 = (b), amendment A1; owner ruling D128 = (b)).

Before W2-P2 the second player only receives what the eight wave-1 event kinds
carry. A tile that changes at a side boundary for a reason no wave-1 kind
restates - the floor a fire burns away - exists on the host only, and the
client freezes with the desync banner at the next hash check (findings
F144/F424). After stage S-A every host envelope carries a `delta` with the
absolute value of every synced field that changed, and the client writes it.
Three scenarios, ONE boot, in this order (SA-DROP LAST, spec (f)):

  C15-burnout    Fire 1 on C15_FIRE_TILE (battle_set_tile, BOTH machines). The
                 host walks H through the burning tile with a real-UI click
                 (the wave-1 walk atom), then both machines press END TURN and
                 the full side cycle runs back to the player side. On the host
                 the fire burns out at the boundary and takes the floor with
                 it (C15_BURN_PARTS). RED (commit S-A.1, no delta): the client
                 freezes at the side_transition, desync bucket `fire` or
                 `terrain`. GREEN: common asserts at player turn N+1, the fire
                 tile's fire/smoke/parts equal on both, and the host's
                 lastDelta (the side_transition) has tiles >= 1.
  C15-burnfloor  The burning-floor walker (Q1 = c): H gets specab 2
                 (SPECAB_BURNFLOOR) on BOTH machines through the new
                 battle_set_unit_state {specab} lever, is staged at
                 C15B_H_TILE, and the host walks it 3 steps along the
                 flammable floor to C15B_WALK_DEST after set_seed SEED_C15.
                 Every step ignites the unit's tile and hits it with DT_IN on
                 the host (UnitWalkBState's SPECAB_BURNFLOOR branch), which the
                 client never runs. RED: hash_now full differs after the walk.
                 GREEN: common asserts, and the host's lastDelta after the walk
                 (a walk_step or the bt_action_end of this walk) has tiles >= 1.
  SA-DROP        Fire 1 on C15_FIRE_TILE_2 on BOTH, then the host's
                 delta_drop_next one-shot, then END TURN and the full cycle.
                 This scenario's PASS is a desync on purpose: the host withholds
                 exactly one delta, and the client must freeze on `fire` or
                 `terrain` with host deltaDropped == 1 - proof that the delta,
                 and nothing else, closed the hole. RED (S-A.1): deltaDropped
                 stays 0 (there is no delta yet).

Common asserts (spec (f), after the action settles with wait_host_idle):
hash_now {full:true} - ALL buckets EQUAL on both machines (never a hard-coded
count); desyncSeen false on both; client coopClientBStatePushes unchanged and
host 0; client deltaEvsApplied increased; deltaUnresolved, deltaUnsupported,
deltaRemoveMissing and deltaAddExisting all 0 on both; the host's lastDelta
has the scenario's minimum class counts.

FIXTURE (deterministic, never searched here). The classic parallel skirmish
bring-up (raw.bring_up_lobby + session.drive_to_battlescape, seat_count=2),
pinned with set_seed SEED_MAP right before newbattle_ok, asserted against the
baked MAP_FP, then session.pin_ai_neutral. H is the first host-seat soldier
(asserted against the baked id). Every staging write (teleport, TU, specab,
tile fire) goes to BOTH machines and the responses are asserted equal. The
constants come from the W2-P2 TASK 0a precalc (SEED_MAP 1, the default NEW
BATTLE map) and SEED_C15 from the S-A precalc (the first SPECAB_BURNFLOOR seed
whose last step changes C15B_WALK_DEST on the host, confirmed on further
boots). set_seed on the HOST immediately before the walk order.

RED-THEN-GREEN (spec (d), Q4 = b). Commit S-A.1 (this file, the probe fields
and the state-writing levers - no product behaviour) is run ONCE and every
scenario must FAIL with its named red evidence. Commit S-A.2 (the delta core)
is run ONCE and every scenario must PASS. Each scenario prints ONE
"EVIDENCE <id>:" line with both machines' fields BEFORE its green conditions
are checked; main() runs every scenario even after an earlier one failed and
prints "PASS <id>" / "FAIL <id>: <message>". Every wait is bounded; a wait that
times out is recorded in the EVIDENCE line and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all three scenarios pass, 2
otherwise (a bring-up failure is also 2).

Run:  python tools/coop_test/test_w2_delta_core.py
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_rw_turn_baton import drive_full_cycle, dismiss_next_turn_if_present
from test_rw_seat_pacing import tab_select, real_click_walk

# ----- common (every W2-P2 test file; TASK 0a round 1, default map) -----
SEED_MAP = 1
MAP_FP = -4.48310638993e+18      # host battle_state.mapFingerprint on SEED_MAP 1
H_ID = 10                        # first host-seat (coop 0) soldier; stats/loadout random per boot (F488)
A_ID = 1000000                   # the only alien: Sectoid Soldier, spawn (27,12,0) dir 5, health 30
A_ITEMS = {56: ("STR_PLASMA_PISTOL", "STR_RIGHT_HAND"), 58: ("STR_PLASMA_PISTOL_CLIP", "STR_BELT"),
           59: ("STR_MIND_PROBE", "STR_BACK_PACK")}   # 60 items at start: first lever-minted id = 60
A_CORPSE = "STR_SECTOID_CORPSE"
RHAND_NTH = 25                   # click_widget nth of the right-hand box (RHAND_RECT centre base (296,172))
KEY_ITEM1, KEY_ITEM2, KEY_ITEM4, KEY_FUSE_0 = 49, 50, 52, 48   # PRIME/AIMED, SNAP, STUN (BA_HIT), fuse 0
TU_MAX = 255                     # battle_set_unit_state / battle_fire tu: clamped to the unit's max TU

# ----- test_w2_delta_core.py (S-A) -----
C15_H_TILE, C15_H_DIR = (1, 6, 0), 2      # H starts here facing east
C15_FIRE_TILE = (2, 6, 0)                 # CULTIVAT #2 floor = tile 0's MCD (burn-out observed on tile 0)
C15_WALK_DEST = (3, 6, 0)                 # real_click_walk dest; OBSERVED path (1,6)->(2,6)->(3,6), hash clean
C15_FIRE_TILE_2 = (2, 2, 0)               # SA-DROP: CULTIVAT #2, off every walk
C15_BURN_PARTS = ((1, 2), (1, 10))        # floor (setId, id) before -> after the neutral->player boundary
C15B_H_TILE, C15B_H_DIR = (1, 34, 0), 2   # burning-floor walker (specab 2 lever lands in S-A)
C15B_WALK_DEST = (4, 34, 0)               # OBSERVED 3 steps (2,34)->(3,34)->(4,34), CULTIVAT #3 (flammability 10)
SEED_C15 = 1                              # S-A precalc: all 3 walked tiles ignite (fire 3, smoke 12)
                                          # on the host, dest included; 3/3 boots (2 in this test's order)

PORT = "48622"
FACTION_PLAYER = 0
COOP_SEAT_0 = 0
SPECAB_BURNFLOOR = 2                      # src/Mod/Unit.h enum SpecialAbility
PARTS = ("floor", "westwall", "northwall", "object")
C15_WALK_PATH = [(2, 6, 0), (3, 6, 0)]
C15B_WALK_PATH = [(2, 34, 0), (3, 34, 0), (4, 34, 0)]
ZERO_PROBES = ("deltaUnresolved", "deltaUnsupported", "deltaRemoveMissing", "deltaAddExisting")
PROBE_KEYS = ("desyncSeen", "coopClientBStatePushes", "lastSeqEmitted", "lastSeqApplied",
              "deltaArmed", "deltaSeeds", "deltaEvsEmitted", "deltaEvsApplied", "deltaFieldsApplied",
              "deltaUnresolved", "deltaAddExisting", "deltaRemoveMissing", "deltaUnsupported",
              "deltaAbsorbed", "deltaDropped", "syncEvsEmitted", "syncEvsApplied", "lastDelta")
# CoopHashCheck::verify -> coopRaiseBattleDesync's one log line per battle (the latch).
DESYNC_RE = re.compile(r"\[coop-hash\] DESYNC: bucket=(\S+) seq=(\d+) kind=(\S*)")


# ===================== small probes =====================


def top(gc):
    return session.top_state(gc)


def units(gc):
    return session.units_by_id(battle_state(gc))


def probes(gc):
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return {k: es.get(k) for k in PROBE_KEYS}


def tile(gc, t):
    """tile_info as {parts: {part: (setId, id)}, fire, smoke} (None if no tile)."""
    r = gc.cmd({"cmd": "tile_info", "x": t[0], "y": t[1], "z": t[2]})
    if not r.get("ok"):
        return None
    return {"parts": {p: (r["parts"][p]["mapDataSetID"], r["parts"][p]["mapDataID"]) for p in PARTS},
            "fire": r.get("fire"), "smoke": r.get("smoke")}


def floor_of(ti):
    return ti["parts"]["floor"] if ti else None


def hashes(gc):
    r = gc.cmd({"cmd": "hash_now", "full": True})
    assert r.get("ok"), f"hash_now failed on {gc.name}: {r}"
    return r["h"]


def diff_buckets(host, client):
    hh, ch = hashes(host), hashes(client)
    return sorted(k for k in set(hh) | set(ch) if hh.get(k) != ch.get(k))


def desync_record(gc, desync_seen, timeout=5.0):
    """The desync this machine latched, from its own openxcom.log line
    `[coop-hash] DESYNC: bucket=<b> seq=<n> kind=<k>` (one per battle), as
    {bucket, seq, kind}; None when desyncSeen is false. The line is read with a
    bounded wait for the game's log write to land."""
    if not desync_seen:
        return None
    path = os.path.join(gc.user_dir, "openxcom.log")
    deadline = time.time() + timeout
    hits = []
    while True:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                hits = DESYNC_RE.findall(f.read())
        except OSError:
            hits = []
        if hits or time.time() >= deadline:
            break
        time.sleep(0.25)
    if not hits:
        return {"bucket": None, "seq": None, "kind": None}
    bucket, seq, kind = hits[-1]
    return {"bucket": bucket, "seq": int(seq), "kind": kind}


def short(e, n=300):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."


def both(host, client, req, keys):
    """Send `req` to BOTH machines; assert ok and equal on `keys`."""
    rh, rc = host.cmd(dict(req)), client.cmd(dict(req))
    assert rh.get("ok") and rc.get("ok"), f"staging {req} failed: host={rh} client={rc}"
    vh, vc = tuple(rh.get(k) for k in keys), tuple(rc.get(k) for k in keys)
    assert vh == vc, f"staging {req} differs: host={vh} client={vc}"
    return rh


def tele_both(host, client, uid, t, d):
    return both(host, client, {"cmd": "battle_teleport_unit", "unit": uid, "x": t[0], "y": t[1],
                               "z": t[2], "dir": d}, ("to", "dir"))


def tu_both(host, client, uid):
    return both(host, client, {"cmd": "battle_set_unit_state", "unit": uid, "tu": TU_MAX},
                ("tu",))["tu"]


def set_tile_both(host, client, t, **fields):
    req = dict({"cmd": "battle_set_tile", "x": t[0], "y": t[1], "z": t[2]}, **fields)
    return both(host, client, req, ("x", "y", "z", "fire", "smoke"))


# ===================== driving =====================


def settle_on_battlescape(gc, timeout=20):
    """Clear any NextTurnState left over from the cycle (the real close()
    path) and wait until BattlescapeState is on top with the panic check done."""
    def ready():
        dismiss_next_turn_if_present(gc)
        bs = battle_state(gc)
        return (top(gc) == "BattlescapeState" and bs.get("panicHandled")
                and bs.get("pendingStates") == 0) or None
    gc.wait_for(f"{gc.name} on BattlescapeState after the cycle", ready, timeout=timeout)


def end_turn_cycle(host, client, notes, client_follows=True, timeout=60):
    """Both machines press END TURN (the client first; the host presses once it
    paints END TURN 1/2), then the full side cycle back to the player side.
    client_follows=True also waits for the client to reach that side, both
    machines to settle on BattlescapeState and the host to go idle with the
    client caught up (session.wait_host_idle). client_follows=False (SA-DROP,
    whose client freezes on purpose) waits for the HOST only. Every wait is
    bounded; a timeout is recorded in `notes` (evidence), never repeated."""
    turn0 = battle_state(host).get("turn")
    try:
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        host.wait_for("host paints END TURN 1/2 after the client's press",
                      lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2" or None,
                      timeout=20)
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        if client_follows:
            drive_full_cycle(host, client, turn0, timeout=timeout)
            settle_on_battlescape(host)
            settle_on_battlescape(client)
            session.wait_host_idle(host, client, timeout=30)
        else:
            def host_back():
                dismiss_next_turn_if_present(host)
                dismiss_next_turn_if_present(client)
                hs = battle_state(host)
                return (hs.get("side") == FACTION_PLAYER and hs.get("turn", -1) >= turn0 + 1) or None
            host.wait_for("host back on the player side", host_back, timeout=timeout)
            settle_on_battlescape(host)
    except Exception as e:
        notes.append(f"end-turn cycle: {short(e)}")
    return turn0


def walk_done(host, prev):
    hw = session.last_walk(host)
    return bool(hw and hw.get("actionId", 0) != prev and hw.get("active") is False
                and hw.get("restate"))


def host_walk(host, client, dest, seed, notes):
    """ONE real-UI walk order for H on the host (TAB-select, set_seed `seed`
    when given, one click on `dest`). Waits, bounded, for the host's walk chain
    to finish - a HOST-only predicate, so a client that froze keeps its
    evidence - then for the host to go idle with the client caught up.
    Returns the host's lastWalk."""
    if not tab_select(host, H_ID):
        notes.append(f"TAB never selected H on the host (selectedId "
                     f"{battle_state(host).get('selectedId')})")
        return {}
    prev = session.walk_action_id(host)
    try:
        if seed is not None:
            host.ok({"cmd": "set_seed", "seed": seed})
        real_click_walk(host, dest)
        host.wait_for("host walk chain finished", lambda: walk_done(host, prev) or None, timeout=30)
    except Exception as e:
        notes.append(f"host walk: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle after the walk: {short(e)}")
    return session.last_walk(host) or {}


def executed_path(hw):
    return [(p["x"], p["y"], p["z"]) for p in (hw.get("executed") or [])]


# ===================== common asserts =====================


def common_fails(host, client, before, min_counts, what):
    """Spec (f) common asserts, as a list of failure messages."""
    fails = []
    try:
        assert_hash_clean(host, client, full=True, what=what)
    except AssertionError as e:
        fails.append(f"hash_now full not clean: {short(e, 600)}")
    ph, pc = probes(host), probes(client)
    if ph["desyncSeen"] or pc["desyncSeen"]:
        fails.append(f"desyncSeen host={ph['desyncSeen']} client={pc['desyncSeen']} (want false on both)")
    if pc["coopClientBStatePushes"] != before["client"]["coopClientBStatePushes"]:
        fails.append(f"client coopClientBStatePushes {before['client']['coopClientBStatePushes']}"
                     f"->{pc['coopClientBStatePushes']} (want unchanged)")
    if ph["coopClientBStatePushes"] != 0:
        fails.append(f"host coopClientBStatePushes={ph['coopClientBStatePushes']} (want 0)")
    if not (pc["deltaEvsApplied"] or 0) > (before["client"]["deltaEvsApplied"] or 0):
        fails.append(f"client deltaEvsApplied {before['client']['deltaEvsApplied']}"
                     f"->{pc['deltaEvsApplied']} (want increased)")
    for k in ZERO_PROBES:
        for name, p in (("host", ph), ("client", pc)):
            if p[k] != 0:
                fails.append(f"{name} {k}={p[k]} (want 0)")
    ld = ph["lastDelta"] or {}
    for cls, n in min_counts.items():
        if (ld.get(cls) or 0) < n:
            fails.append(f"host lastDelta.{cls}={ld.get(cls)} (want >= {n}; lastDelta={ph['lastDelta']})")
    return fails


def finish(fails):
    if fails:
        raise AssertionError("; ".join(fails))


def delta_view(p):
    return {k: p[k] for k in ("desyncSeen", "deltaArmed", "deltaSeeds", "deltaEvsEmitted",
                              "deltaEvsApplied", "deltaAbsorbed", "deltaDropped",
                              "deltaUnresolved", "deltaUnsupported", "deltaRemoveMissing",
                              "deltaAddExisting", "lastSeqEmitted", "lastSeqApplied")}


# ===================== scenarios =====================


def c15_burnout(host, client, ctx):
    notes = []
    tele_both(host, client, H_ID, C15_H_TILE, C15_H_DIR)
    tu_both(host, client, H_ID)
    st = set_tile_both(host, client, C15_FIRE_TILE, fire=1)
    t0h, t0c = tile(host, C15_FIRE_TILE), tile(client, C15_FIRE_TILE)
    staged_diff = diff_buckets(host, client)
    before = {"host": probes(host), "client": probes(client)}
    hw = host_walk(host, client, C15_WALK_DEST, None, notes)
    walk_diff = diff_buckets(host, client)
    turn0 = end_turn_cycle(host, client, notes)
    hs, cs = battle_state(host), battle_state(client)
    t1h, t1c = tile(host, C15_FIRE_TILE), tile(client, C15_FIRE_TILE)
    ph, pc = probes(host), probes(client)
    dsc = desync_record(client, pc["desyncSeen"])
    end_diff = diff_buckets(host, client)
    print(f"EVIDENCE C15-burnout: fire tile {C15_FIRE_TILE} set_tile={st.get('fire')} "
          f"staged host={t0h} client={t0c} stagedDiff={staged_diff}; "
          f"walk executed={executed_path(hw)} diffAfterWalk={walk_diff}; "
          f"turn {turn0} -> host=({hs.get('turn')},{hs.get('side')}) client=({cs.get('turn')},{cs.get('side')}); "
          f"fire tile after host={t1h} client={t1c}; "
          f"client desyncSeen={pc['desyncSeen']} desync={dsc} host desyncSeen={ph['desyncSeen']}; "
          f"diffAfterCycle={end_diff}; host lastDelta={ph['lastDelta']} client lastDelta={pc['lastDelta']}; "
          f"host {delta_view(before['host'])}->{delta_view(ph)}; "
          f"client {delta_view(before['client'])}->{delta_view(pc)}; notes={notes}", flush=True)
    fails = list(notes)
    if executed_path(hw) != C15_WALK_PATH:
        fails.append(f"walk executed {executed_path(hw)} (want {C15_WALK_PATH}, through the fire tile)")
    if floor_of(t0h) != C15_BURN_PARTS[0] or (t0h or {}).get("fire") != 1:
        fails.append(f"host fire tile staged {t0h} (want floor {C15_BURN_PARTS[0]}, fire 1)")
    if floor_of(t1h) != C15_BURN_PARTS[1]:
        fails.append(f"host fire tile floor {floor_of(t1h)} after the cycle (want {C15_BURN_PARTS[1]}: "
                     f"the burn-out did not happen on the host)")
    if t1h != t1c:
        fails.append(f"fire tile after the cycle host={t1h} client={t1c} (want equal)")
    if (hs.get("turn"), hs.get("side"), cs.get("turn"), cs.get("side")) != (turn0 + 1, FACTION_PLAYER,
                                                                             turn0 + 1, FACTION_PLAYER):
        fails.append(f"not on player turn {turn0 + 1} on both: host=({hs.get('turn')},{hs.get('side')}) "
                     f"client=({cs.get('turn')},{cs.get('side')})")
    fails += common_fails(host, client, before, {"tiles": 1}, "C15-burnout")
    if (ph["lastDelta"] or {}).get("kind") != "side_transition":
        fails.append(f"host lastDelta.kind={(ph['lastDelta'] or {}).get('kind')!r} (want 'side_transition')")
    finish(fails)


def c15_burnfloor_run(host, client, seed):
    """Stage and drive the burning-floor walk; returns the evidence dict."""
    notes = []
    sa = both(host, client, {"cmd": "battle_set_unit_state", "unit": H_ID, "specab": SPECAB_BURNFLOOR},
              ("specab",))
    tele_both(host, client, H_ID, C15B_H_TILE, C15B_H_DIR)
    tu_both(host, client, H_ID)
    path0 = {t: (tile(host, t), tile(client, t)) for t in C15B_WALK_PATH}
    hh0 = hashes(host)
    pre_diff = diff_buckets(host, client)
    before = {"host": probes(host), "client": probes(client)}
    uh0 = units(host)[H_ID]
    hw = host_walk(host, client, C15B_WALK_DEST, seed, notes)
    path1 = {t: (tile(host, t), tile(client, t)) for t in C15B_WALK_PATH}
    hh1 = hashes(host)
    post_diff = diff_buckets(host, client)
    ph, pc = probes(host), probes(client)
    uh1, uc1 = units(host)[H_ID], units(client)[H_ID]
    return {
        "notes": notes, "specab": sa.get("specab"), "seed": seed, "before": before,
        "path0": path0, "path1": path1, "preDiff": pre_diff, "postDiff": post_diff,
        "hostChanged": sorted(k for k in hh1 if hh1.get(k) != hh0.get(k)),
        "hostTilesChanged": [t for t in C15B_WALK_PATH if path0[t][0] != path1[t][0]],
        "executed": executed_path(hw), "ph": ph, "pc": pc,
        "desync": desync_record(client, pc["desyncSeen"]),
        "H": {"host": {k: uh1.get(k) for k in ("health", "unitFire", "status", "x", "y", "z", "tu")},
              "client": {k: uc1.get(k) for k in ("health", "unitFire", "status", "x", "y", "z", "tu")},
              "hostHealthBefore": uh0.get("health")},
    }


def c15_burnfloor(host, client, ctx):
    ev = c15_burnfloor_run(host, client, SEED_C15)
    ph, pc, before = ev["ph"], ev["pc"], ev["before"]
    fmt = {f"{t[0]},{t[1]}": {"before": {"host": b[0], "client": b[1]},
                              "after": {"host": ev["path1"][t][0], "client": ev["path1"][t][1]}}
           for t, b in ev["path0"].items()}
    print(f"EVIDENCE C15-burnfloor: specab={ev['specab']} seed={ev['seed']} executed={ev['executed']} "
          f"diffBeforeWalk={ev['preDiff']} diffAfterWalk={ev['postDiff']} "
          f"hostBucketsChangedByWalk={ev['hostChanged']} hostTilesChanged={ev['hostTilesChanged']} "
          f"path={fmt} H={ev['H']}; client desyncSeen={pc['desyncSeen']} desync={ev['desync']}; "
          f"host lastDelta={ph['lastDelta']} client lastDelta={pc['lastDelta']}; "
          f"host {delta_view(before['host'])}->{delta_view(ph)}; "
          f"client {delta_view(before['client'])}->{delta_view(pc)}; notes={ev['notes']}", flush=True)
    fails = list(ev["notes"])
    if ev["executed"] != C15B_WALK_PATH:
        fails.append(f"walk executed {ev['executed']} (want {C15B_WALK_PATH})")
    if not ev["hostTilesChanged"]:
        fails.append("the burning floor changed no walked tile on the host (SEED_C15 premise)")
    fails += common_fails(host, client, before, {"tiles": 1}, "C15-burnfloor")
    ld = ph["lastDelta"] or {}
    if not (ld.get("seq") or 0) > (before["host"]["lastSeqEmitted"] or 0):
        fails.append(f"host lastDelta.seq={ld.get('seq')} is not from this walk "
                     f"(host lastSeqEmitted before it {before['host']['lastSeqEmitted']})")
    finish(fails)


def sa_drop(host, client, ctx):
    notes = []
    before = {"host": probes(host), "client": probes(client)}
    st = set_tile_both(host, client, C15_FIRE_TILE_2, fire=1)
    t0h, t0c = tile(host, C15_FIRE_TILE_2), tile(client, C15_FIRE_TILE_2)
    rd = host.cmd({"cmd": "delta_drop_next"})
    if not rd.get("ok"):
        notes.append(f"delta_drop_next on the host: {rd}")
    turn0 = end_turn_cycle(host, client, notes, client_follows=False)
    try:
        client.wait_for("client desyncSeen", lambda: event_state(client).get("desyncSeen") or None,
                        timeout=30)
    except Exception as e:
        notes.append(f"client desyncSeen: {short(e)}")
    hs = battle_state(host)
    t1h, t1c = tile(host, C15_FIRE_TILE_2), tile(client, C15_FIRE_TILE_2)
    ph, pc = probes(host), probes(client)
    dsc = desync_record(client, pc["desyncSeen"])
    print(f"EVIDENCE SA-DROP: fire tile {C15_FIRE_TILE_2} set_tile={st.get('fire')} staged host={t0h} "
          f"client={t0c}; delta_drop_next={rd}; turn {turn0} -> host=({hs.get('turn')},{hs.get('side')}); "
          f"fire tile after host={t1h} client={t1c}; client desyncSeen "
          f"{before['client']['desyncSeen']}->{pc['desyncSeen']} desync={dsc}; host deltaDropped "
          f"{before['host']['deltaDropped']}->{ph['deltaDropped']}; host lastDelta={ph['lastDelta']}; "
          f"host {delta_view(ph)} client {delta_view(pc)}; notes={notes}", flush=True)
    fails = []
    if not rd.get("ok"):
        fails.append(f"delta_drop_next did not answer ok: {rd}")
    if (hs.get("turn"), hs.get("side")) != (turn0 + 1, FACTION_PLAYER):
        fails.append(f"host not on player turn {turn0 + 1}: ({hs.get('turn')},{hs.get('side')}) notes={notes}")
    if floor_of(t0h) != C15_BURN_PARTS[0] or (t0h or {}).get("fire") != 1:
        fails.append(f"host fire tile staged {t0h} (want floor {C15_BURN_PARTS[0]}, fire 1)")
    if floor_of(t1h) != C15_BURN_PARTS[1]:
        fails.append(f"host fire tile floor {floor_of(t1h)} after the cycle (want {C15_BURN_PARTS[1]})")
    if before["client"]["desyncSeen"]:
        fails.append("client desyncSeen was already true before the drop (the desync must be this scenario's)")
    if not pc["desyncSeen"]:
        fails.append("client desyncSeen false after the dropped delta (want true)")
    if not dsc or dsc.get("bucket") not in ("fire", "terrain"):
        fails.append(f"client desync {dsc} (want bucket fire or terrain)")
    if ph["deltaDropped"] != 1:
        fails.append(f"host deltaDropped={ph['deltaDropped']} (want 1)")
    finish(fails)


SCENARIOS = (("C15-burnout", c15_burnout), ("C15-burnfloor", c15_burnfloor), ("SA-DROP", sa_drop))


# ===================== bring-up =====================


def boot(host, client):
    raw.bring_up_lobby(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} (SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p2-sa")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    ph = probes(host)
    print(f"[w2p2-sa] boot ok: MAP_FP={MAP_FP!r} turn={hs['turn']} H={H_ID} pinned={pinned} "
          f"SEED_C15={SEED_C15} host deltaArmed={ph['deltaArmed']} deltaSeeds={ph['deltaSeeds']}",
          flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49840, make_user_dir("w2p2_delta_core_host"))
    client = GameClient("client", 49841, make_user_dir("w2p2_delta_core_client"))
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
                print(f"[w2p2-sa] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_delta_core: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
