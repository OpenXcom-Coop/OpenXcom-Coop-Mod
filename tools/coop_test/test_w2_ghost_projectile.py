"""W2-P5 S-A - test_w2_ghost_projectile.py: the watching machine shows the
projectile of a shot it did not execute - display only (spec
rewrite/prompts/w2p5_display_ghosts.md section (f) "test_w2_ghost_projectile.py
(S-A)", sections (b)1-6 and (b)8-11 for `shot`, as amended by PLAN REVIEW +
AMENDMENT E1: PR-E1 (battle_fire keepSelection), PR-E2 (the client's
probe-only path re-derivation), PR-E3 (G8 is red at red), PR-E5 (the delivery
proof applies to option-ON rows only; a record with no display object counts
as completed at enqueue), OQ3/OQ4/OQ5).

Before S-A the second player's machine shows no shot: every applied `shot` cue
only counts in cueCounts and the state snaps (the "snap display", TASK 0
T0-6). After S-A every applied `shot` starts one display-only combat ghost on
the client: a vanilla Projectile on the client's Map flying the path
re-derived with vanilla's own path function, paced by the shooter's seat fire
dial (SPEC 17), with the fire / throw / drop sounds. Eight scenarios, ONE boot
(terror seed 1, host fire dial 12, client fire dial 4, coopGhostStepper pinned
true in both boot options), in this order (G6 last: its blast changes the
terrain):

  G1  host snap. H (rifle + clip, firing 120, TU max) on LANE_TILE facing east,
      the lane to LANE_TARGET empty but for H; host set_seed SEED_G1 and a
      real-UI snap (TAB, the right-hand box, key 50, HOME, one click on
      LANE_TARGET). RED: client cueCounts.shot +1, combatGhost.enqueued.shot
      +0. GREEN: one ring record for the shot's seq: speed 12 == the host's
      shotTrajectories speed, seat 0, trajLen == the host's trajLen,
      pathMatches, ticks == ceil(trajLen / 12), ms == ticks x 16, sound ==
      the clip's fire sound, else the rifle's (display_rules).
  G2  client snap. H to H_ASIDE, C (rifle + clip, firing 120, TU max) on
      LANE_TILE facing east; the client's real-UI snap at LANE_TARGET, host
      set_seed SEED_G2 before the click. RED as G1. GREEN: speed 4 on both
      (the host's shotTrajectories speed for that seq too: SPEC 17's D109
      host consumer), seat 1, the formula.
  G3  unowned shooter. A (alien, seat -1) on A_G3_TILE facing H on H_ASIDE,
      A's TU (base and current) set to A_G3_TU (pin_ai_neutral zeroed the
      base, and battle_fire's <tu> clamps to it) and H's health raised to
      H_G3_HEALTH (both); the host's selected unit is H (real TAB); host
      set_seed SEED_G3 and battle_fire {A, snap, target H, keepSelection}
      (PR-E1: on the player side an alien's shot is reaction fire, kept only
      when its target is the selected unit). RED as G1. GREEN: speed ==
      min(12, 4) == 4 (the D113 floor), seat -1, the formula.
  G4  autoshot. C (fresh rifle + clip) on LANE_TILE; the client's real-UI
      autoshot at LANE_TARGET, host set_seed SEED_G4. RED: 3 shots, +0
      ghosts. GREEN: 3 records in seq order (payload shotIndex 1, 2, 3), each
      speed 4, trajLen == the host's, the formula.
  G5  throw arc. An UNPRIMED grenade on C, C on G5_C_TILE facing east, the
      client's real-UI throw (key 53) at G5_TARGET due north, host set_seed
      SEED_G5. RED: +0 ghosts. GREEN: arc true, pathMatches, trajLen == the
      host's, speed 4, the formula, sound == ITEM_THROW, soundEnd ==
      ITEM_DROP.
  G7  negative control (green at red, declared). Client set_option
      coopGhostStepper false; H on LANE_TILE; host set_seed SEED_G7 and
      battle_fire {H, snap, LANE_TARGET}; then true again. RED = GREEN:
      client cueCounts.shot +1 and combatGhost.enqueued.shot +0 while off.
  G8  input during a flight. Host fire dial 1 (seat 0 on both); C gets a
      rifle + clip, the client selects C2 (so reaching C needs a TAB); host
      set_seed SEED_G8 and battle_fire {H, snap, LANE_TARGET}; once the client
      applied the shot and its combatGhost.live is 1, the client presses TAB
      (onto C) and the right-hand box. RED (PR-E3: no ghost exists at red):
      combatGhost.live stays 0 and no record. GREEN: ActionMenuState opens on
      the client while the ghost is live (Q3 = b) and the record's steps >= 2.
      The host dial goes back to 12 after the row.
  G6  launch legs. A blaster launcher + bomb on C, C on G6_C_TILE facing west,
      the client's real-UI launch with two waypoints on G6_W, host set_seed
      SEED_G6 before the launch button. RED: 2 shots, +0 ghosts. GREEN: 2
      straight records (payload action launch), each pathMatches, trajLen ==
      the host's, speed 4, the formula; the `explosion` cue is S-B's.

Common to every row (after session.wait_host_idle: the host has no context
and no BState, the client applied up to the host's lastSeqEmitted):
hash_now {full:true} every bucket EQUAL; desyncSeen false on both; client
coopClientBStatePushes unchanged and host 0; the client's rngSeed unchanged
from the row's start (V4); the host's combatGhost all zero (the host never
ghosts); the client's combatGhost.live == 0 and completed + cut == enqueued
per kind. Option-ON rows (all but G7, PR-E5) add the DELIVERY PROOF: every
host `shot` cue of the row (host event_log, payloads from the host's
openxcom.log `[coop-cue]` lines) has exactly one client ring record with that
seq and unresolved / noMap false, and combatGhost.enqueued.shot moved by the
client's cueCounts.shot delta. Every row also requires its own shots
(vacuous = red): the number of `shot` cues, their shooter and payload action.
No wall-clock duration is asserted: every timing check is an equality with
the spec (b)3 formula computed here from the record's own trajLen and the
expected dial.

Probes (event_state, added by commit S-A.1): combatGhost {enqueued, completed,
cut: {shot, hit, explosion}, joined, live, unresolved, noMap, ring} (both;
nothing writes it before S-A.2), derivedPaths (client, PR-E2: {seq, arc,
derivedLen, derivedEnd} per applied shot), rngSeed (both, read only),
shotTrajectories (host: the last 16 shots' {seq, trajLen, speed, impact});
the read-only lever display_rules {types} (items' display rules and the Mod
constants from the loaded rules); battle_fire's keepSelection (PR-E1).

FIXTURE (TASK 0 T0-3, T0-4 and T0-7 on the S-A.1 build; the roster-pinned
terror boot of test_w2_client_shoot.py): set_seed SEED_ROSTER on the HOST right
before its open_new_battle, mission STR_TERROR_MISSION, set_seed SEED_MAP right
before newbattle_ok, seat_count 2, MAP_FP asserted on both, the seated ids
asserted, pin_ai_neutral. Every lever pair goes to the CLIENT first (F607).
Item ids are read at run time from the lever replies (F1107). place()
teleports only a unit that is not already on its tile (CLAUDE.local.md S2).

RED-THEN-GREEN (spec (d) row S-A). Commit S-A.1 (this file, the probes, the
levers) is run ONCE: every row but G7 must FAIL with its RED evidence (G8's
red is PR-E3's). Commit S-A.2 is run ONCE and every row must PASS. Each row
prints ONE "EVIDENCE <id>:" line (JSON) with both machines' fields BEFORE its
green conditions are checked; main() runs every row even after an earlier one
failed and prints "PASS <id>" / "FAIL <id>: <message>". Every wait is
bounded; a wait that times out is recorded in the EVIDENCE line and fails the
row.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all eight rows pass, 2 otherwise (a
bring-up failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_ghost_projectile.py
"""

import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_rw_turn_baton import RHAND_NTH, click_nth
from test_rw_seat_pacing import tab_select, SDLK_HOME
from test_w2_delta_core import diff_buckets, desync_record, short, both
from test_w2_delta_items import items_by_id, tile_of
from test_w2_host_combat import bring_up_lobby_roster_pinned, evs_since, open_hand_menu_host
from test_w2_ai_origins import host_payloads
from test_w2_client_shoot import (top, units, ubrief, press, give_both, place, set_tu_both, set_firing_both,
                                  wait_seat_dial, aim_click, await_press, RHAND_CENTRE, TU_MAX, KEY_SNAP, KEY_AUTO,
                                  CURSOR_AIM)
from test_w2_client_grenade import (give_grenade, give_launcher, target_order, launch_order, KEY_THROW, CURSOR_THROW,
                                    C20_W)

# ----- bring-up (the roster-pinned terror boot of test_w2_client_shoot.py) -----
MISSION = "STR_TERROR_MISSION"
SEED_MAP = 1
MAP_FP = -3.451266327757785e+18   # host battle_state.mapFingerprint on SEED_MAP 1
SEATED = [8, 9]                   # the client's seated units: C and C2
C_ID, C2_ID = 8, 9
H_ID = 10                         # first host-seat soldier
A_ID = 1000000                    # Sectoid Soldier (plasma pistol in the right hand)
PORT = "48718"
COOP_SEAT_0, COOP_SEAT_1, SEAT_NONE = 0, 1, -1
FACTION_PLAYER = 0
HOST_FIRE_DIAL = 12               # host battleFireSpeed (seat 0)
CLIENT_FIRE_DIAL = 4              # client battleFireSpeed (seat 1)
FLOOR_FIRE = min(HOST_FIRE_DIAL, CLIENT_FIRE_DIAL)   # D113: an unowned shooter flies at the slowest seat's dial
TICK_MS = 16                      # vanilla ProjectileFlyBState setStateInterval(1000/60)

# ----- the lane (TASK 0 T0-1 / T0-7) -----
# T0-7 (S-A.1 build, 3 boots + K=2, identical): every lane shot starts at origin voxel (207,424,18).
LANE_TILE, LANE_DIR = (12, 26, 0), 2      # open road; faces east
LANE_TARGET = (32, 26, 0)                 # empty road floor tile, 20 tiles east
H_ASIDE, H_ASIDE_DIR = (14, 24, 0), 2     # off the lane and off the G5 throw column
SEED_G1 = 1                               # impact floor (527,425,1), host trajLen 322, speed 12
SEED_G2 = 1                               # impact floor (527,425,1), host trajLen 322, speed 4

# ----- G3 (PR-E1) -----
A_G3_TILE, A_G3_DIR = (18, 24, 0), 6      # 4 tiles east of H_ASIDE, facing it
A_G3_TU = 60                              # A's TU (base and current) for the stand-in shot (snap cost 18)
H_G3_HEALTH = 500                         # H survives the plasma shot
SEED_G3 = 1                               # a miss off the map: impact 5 at (-1,420,12), host trajLen 292, speed 4

# ----- G4 (test_w2_client_shoot C17) -----
SEED_G4 = 1                               # floors at (778,409,1) / (512,396,1) / (518,415,1), trajLen 573/307/313
G4_SHOTS = 3

# ----- G5 (test_w2_client_grenade C19 staging, unprimed grenade) -----
G5_C_TILE, G5_C_DIR = (12, 27, 0), 2      # faces east; the throw tile is due north
G5_TARGET = (12, 20, 0)
G5_ROWS = 2                               # an unprimed stock grenade: THROW + PRIME
SEED_G5 = 2                               # lands on G5_TARGET (fuse -1, owner -1), host trajLen 105

# ----- G7 / G8 -----
SEED_G7 = 1                               # impact floor (530,425,1), host trajLen 325
SEED_G8 = 1                               # impact floor (530,425,1), host trajLen 325 at dial 1 (5200 ms)
G8_HOST_FIRE_DIAL = 1
G8_LIVE_WAIT_S = 1.0                      # how long the client gets to show the ghost live after the apply
G8_MIN_STEPS = 2                          # T0-7: TAB + right-hand box -> ActionMenuState 0.74 s, solo and K=2

# ----- G6 (test_w2_client_grenade C20 staging) -----
G6_C_TILE, G6_C_DIR = (28, 25, 0), 6      # faces west, away from the waypoints (F1125)
G6_W = C20_W                              # (46, 25, 0): both waypoints (vanilla's dive; launch_order clicks it)
SEED_G6 = 1                               # legs trajLen 287 / 12; the blast changes 285 census tiles (unmodded)
G6_LEGS = 2

# ----- UI -----
SDLK_ESCAPE = 27
POLL_S = 0.05

DISPLAY_TYPES = ("STR_RIFLE", "STR_RIFLE_CLIP", "STR_PLASMA_PISTOL", "STR_PLASMA_PISTOL_CLIP", "STR_GRENADE",
                 "STR_BLASTER_LAUNCHER", "STR_BLASTER_BOMB")
CUE_KINDS = ("shot", "hit", "explosion")
PROBE_KEYS = ("combatGhost", "derivedPaths", "rngSeed", "shotTrajectories", "cueCounts", "lastSeqEmitted",
              "lastSeqApplied", "queueDepth", "desyncSeen", "coopClientBStatePushes", "coopLocalExecBlocked",
              "coopIntentsSent", "inFlight", "busyOwnerSeat")


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


def lane_units(gc, shooter):
    """Live units other than `shooter` standing on the lane (LANE_TILE..LANE_TARGET)."""
    y, z = LANE_TILE[1], LANE_TILE[2]
    return [u["id"] for u in battle_state(gc)["units"] if not u.get("isOut") and u["id"] != shooter
            and u.get("y") == y and u.get("z") == z and LANE_TILE[0] <= (u.get("x") or -1) <= LANE_TARGET[0]]


def host_cancel_aim(host):
    """F503: while the host aims, a hand click only cancels the aim. One such
    click when an earlier row left the host aiming. Returns [cursor before(, after)]."""
    c0 = battle_state(host).get("cursorType")
    if c0 != CURSOR_AIM:
        return [c0]
    click_nth(host, RHAND_NTH)
    return [c0, battle_state(host).get("cursorType")]


def wait_action_end(host, seq0, notes, timeout=60):
    """The host emitted a bt_action_end after seq0 (the row's action ended)."""
    try:
        host.wait_for("the host's action ended (a bt_action_end after the row's first seq)",
                      lambda: any(e["kind"] == "bt_action_end" for e in evs_since(host, seq0)) or None,
                      timeout=timeout, interval=0.1)
    except Exception as e:
        notes.append(f"no bt_action_end: {short(e)}")


def settle(host, client, notes):
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")


def fire_sound(rules, weapon, ammo):
    """Spec (b)7: the ammo's fire sound when it has one, else the weapon's."""
    a = (rules.get(ammo) or {}).get("fireSound", -1)
    return a if a != -1 else (rules.get(weapon) or {}).get("fireSound", -1)


# ===================== record + checks =====================


def collect(host, client, before, seq0, rng0):
    """The row's end state: both machines' probes, the row's evs, the host's
    shot payloads, the per-seq host trajectories, client ring records and
    client re-derivations."""
    after = snap2(host, client)
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    seqs = [e["seq"] for e in hev if e["kind"] == "shot"]
    pl = host_payloads(host, seqs) if seqs else {}
    shots = [(s, (pl.get(s) or {}).get("payload") or {}) for s in seqs]
    traj = {r.get("seq"): r for r in (after["host"]["shotTrajectories"] or [])}
    ring = {}
    for r in ((after["client"]["combatGhost"] or {}).get("ring") or []):
        ring.setdefault(r.get("seq"), []).append(r)
    derived = {r.get("seq"): r for r in (after["client"]["derivedPaths"] or [])}
    rec = {"before": before, "after": after, "seq0": seq0, "hev": hev, "cev": cev, "shots": shots, "traj": traj,
           "ring": ring, "derived": derived, "rng": {"start": rng0, "staged": before["client"]["rngSeed"],
                                                     "end": after["client"]["rngSeed"]},
           "hostRng": (before["host"]["rngSeed"], after["host"]["rngSeed"]), "diff": diff_buckets(host, client)}
    rec["dsc"] = desync_record(client, after["client"]["desyncSeen"])
    return rec


def shot_view(rec):
    """Per host shot: payload brief, the host's trajectory probe, the client's
    re-derivation (PR-E2) and the client's ring record(s)."""
    out = []
    for s, p in rec["shots"]:
        out.append({"seq": s, "payload": {k: p.get(k) for k in ("actor", "action", "shotIndex", "waypointsLeft",
                                                                  "originVoxel", "impactVoxel", "impact", "arc")},
                    "hostTraj": rec["traj"].get(s), "derived": rec["derived"].get(s), "ring": rec["ring"].get(s)})
    return out


def evidence(row, rec, extra):
    b, a = rec["before"], rec["after"]
    ev = {"extra": extra,
          "cueDelta": {n: {k: cue_delta(b[n]["cueCounts"], a[n]["cueCounts"], k) for k in CUE_KINDS}
                       for n in ("host", "client")},
          "clientCombatGhost": {"before": cg_counts(b["client"]["combatGhost"]),
                                "after": cg_counts(a["client"]["combatGhost"])},
          "hostCombatGhost": a["host"]["combatGhost"],
          "shots": shot_view(rec), "rngClient": rec["rng"], "rngHost": rec["hostRng"],
          "hostEvs": [(e["seq"], e["kind"], e["actionId"]) for e in rec["hev"]],
          "clientEvs": [(e["seq"], e["kind"], e["actionId"]) for e in rec["cev"]],
          "pushes": {"clientBefore": b["client"]["coopClientBStatePushes"],
                     "clientAfter": a["client"]["coopClientBStatePushes"], "host": a["host"]["coopClientBStatePushes"]},
          "desyncSeen": {"host": a["host"]["desyncSeen"], "client": a["client"]["desyncSeen"]}, "desync": rec["dsc"],
          "diff": rec["diff"]}
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)


def common_fails(host, client, rec, option_on, what):
    """Spec (f) common asserts (PR-E5: the delivery proof on option-ON rows)."""
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
        fails.append(f"host combatGhost {hc} (want all zero and no record: the host never ghosts)")
    cc = a["client"]["combatGhost"] or {}
    if not cc:
        fails.append("client event_state has no combatGhost probe")
    else:
        if cc.get("live") != 0:
            fails.append(f"client combatGhost.live={cc.get('live')} at the row's end (want 0)")
        for k in CUE_KINDS:
            e, c, u = kind_of(cc.get("enqueued"), k), kind_of(cc.get("completed"), k), kind_of(cc.get("cut"), k)
            if c + u != e:
                fails.append(f"client combatGhost {k}: completed {c} + cut {u} != enqueued {e}")
    if option_on:
        for s, _ in rec["shots"]:
            rs = rec["ring"].get(s) or []
            if len(rs) != 1 or rs[0].get("unresolved") or rs[0].get("noMap"):
                fails.append(f"delivery: host shot seq {s} has {len(rs)} client ring record(s) {rs} (want exactly "
                             f"one with unresolved/noMap false)")
        de = cue_delta(b["client"]["combatGhost"].get("enqueued") if b["client"]["combatGhost"] else {},
                       cc.get("enqueued"), "shot")
        dc = cue_delta(b["client"]["cueCounts"], a["client"]["cueCounts"], "shot")
        if de != dc:
            fails.append(f"delivery: client combatGhost.enqueued.shot +{de} but cueCounts.shot +{dc} (want equal)")
    return fails


def shots_fails(rec, n, actor, action, what):
    """The row's own shots (vacuous = red): exactly `n` host `shot` cues by
    `actor` with payload action `action`."""
    got = [(s, p.get("actor"), p.get("action")) for s, p in rec["shots"]]
    if len(got) != n or any(g[1] != actor or g[2] != action for g in got):
        return [f"precondition: the row's host `shot` cues {got} (want exactly {n} by unit {actor} with action "
                f"{action}; {what})"]
    return []


def record_fails(rec, seq, payload, speed, seat, arc=False):
    """One shot's GREEN record (spec (b)3/(b)4/(b)11): speed, seat, trajLen ==
    the host's, pathMatches, arc, ticks and ms per the formula."""
    rs = rec["ring"].get(seq) or []
    if len(rs) != 1:
        return [f"shot seq {seq}: {len(rs)} client ring record(s) (want exactly 1)"]
    r, ht = rs[0], rec["traj"].get(seq)
    fails = []
    if ht is None:
        fails.append(f"shot seq {seq}: no host shotTrajectories entry (host ring {list(rec['traj'])})")
    elif ht.get("speed") != speed:
        fails.append(f"shot seq {seq}: host shotTrajectories speed {ht.get('speed')} (want {speed})")
    want = {"kind": "shot", "unit": payload.get("actor"), "speed": speed, "seat": seat, "pathMatches": True,
            "arc": arc}
    got = {k: r.get(k) for k in want}
    if got != want:
        fails.append(f"shot seq {seq}: record {got} (want {want})")
    n = r.get("trajLen")
    if ht is not None and n != ht.get("trajLen"):
        fails.append(f"shot seq {seq}: record trajLen {n} (want the host's {ht.get('trajLen')})")
    if isinstance(n, int) and n > 0:
        ticks = int(math.ceil(n / float(speed)))
        if r.get("ticks") != ticks or r.get("ms") != ticks * TICK_MS:
            fails.append(f"shot seq {seq}: record ticks {r.get('ticks')} ms {r.get('ms')} (want ceil({n}/{speed}) = "
                         f"{ticks} ticks, {ticks * TICK_MS} ms)")
    else:
        fails.append(f"shot seq {seq}: record trajLen {n} (want a positive length)")
    return fails


def finish(fails):
    if fails:
        raise AssertionError("; ".join(fails))


# ===================== rows =====================


def g1_host_snap(host, client, ctx):
    notes = []
    rng0 = rng_of(client)
    rifle, clip = give_both(host, client, H_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    ph = place(host, client, H_ID, LANE_TILE, LANE_DIR)
    set_tu_both(host, client, H_ID, TU_MAX)
    set_firing_both(host, client, H_ID)
    lane = {"host": lane_units(host, H_ID), "client": lane_units(client, H_ID)}
    staged = diff_buckets(host, client)
    before = snap2(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv = {}
    try:
        pv["cursor"] = open_hand_menu_host(host)
        press(host, KEY_SNAP)
        host.wait_for("host BattlescapeState on top after SNAP", lambda: top(host) == "BattlescapeState" or None,
                      timeout=5)
        press(host, SDLK_HOME)
        time.sleep(0.15)
        pr = host.cmd({"cmd": "map_tile_click_pos", "x": LANE_TARGET[0], "y": LANE_TARGET[1], "z": LANE_TARGET[2]})
        pv["clickPos"] = {k: pr.get(k) for k in ("verified", "winX", "winY")}
        assert pr.get("verified"), f"map_tile_click_pos did not verify {LANE_TARGET} on the host: {pr}"
        host.ok({"cmd": "set_seed", "seed": SEED_G1})
        host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
    except Exception as e:
        notes.append(f"host real-UI snap: {short(e)}")
    wait_action_end(host, seq0, notes)
    settle(host, client, notes)
    rec = collect(host, client, before, seq0, rng0)
    evidence("G1", rec, {"rifle": rifle, "clip": clip, "H": ph, "laneOthers": lane, "stagedDiff": staged,
                         "press": pv, "H_after": {"host": ubrief(units(host).get(H_ID)),
                                                  "client": ubrief(units(client).get(H_ID))}, "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if lane["host"] or lane["client"]:
        fails.append(f"precondition: units on the lane besides H: {lane} (want none)")
    fails += shots_fails(rec, 1, H_ID, "snap", "H's real-UI snap")
    fails += common_fails(host, client, rec, True, "G1")
    for s, p in rec["shots"][:1]:
        fails += record_fails(rec, s, p, HOST_FIRE_DIAL, COOP_SEAT_0)
        r = (rec["ring"].get(s) or [{}])[0]
        want = fire_sound(ctx["rules"], "STR_RIFLE", "STR_RIFLE_CLIP")
        if r.get("sound") != want:
            fails.append(f"shot seq {s}: record sound {r.get('sound')} (want {want}: the clip's fire sound, else the "
                         f"rifle's)")
    finish(fails)


def g2_client_snap(host, client, ctx):
    notes = []
    rng0 = rng_of(client)
    ph = place(host, client, H_ID, H_ASIDE, H_ASIDE_DIR)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc = place(host, client, C_ID, LANE_TILE, LANE_DIR)
    set_tu_both(host, client, C_ID, TU_MAX)
    set_firing_both(host, client, C_ID)
    lane = {"host": lane_units(host, C_ID), "client": lane_units(client, C_ID)}
    staged = diff_buckets(host, client)
    before = snap2(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv, out = {}, {}
    try:
        pv = aim_click(client, KEY_SNAP, LANE_TARGET, lambda: host.ok({"cmd": "set_seed", "seed": SEED_G2}))
    except Exception as e:
        notes.append(f"client real-UI snap: {short(e)}")
    out = await_press(host, client, before, notes)
    settle(host, client, notes)
    rec = collect(host, client, before, seq0, rng0)
    evidence("G2", rec, {"rifle": rifle, "clip": clip, "H": ph, "C": pc, "laneOthers": lane, "stagedDiff": staged,
                         "press": pv, "outcome": out, "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if lane["host"] or lane["client"]:
        fails.append(f"precondition: units on the lane besides C: {lane} (want none)")
    fails += shots_fails(rec, 1, C_ID, "snap", "C's real-UI snap")
    fails += common_fails(host, client, rec, True, "G2")
    for s, p in rec["shots"][:1]:
        fails += record_fails(rec, s, p, CLIENT_FIRE_DIAL, COOP_SEAT_1)
    finish(fails)


def g3_unowned(host, client, ctx):
    notes = []
    rng0 = rng_of(client)
    pa = place(host, client, A_ID, A_G3_TILE, A_G3_DIR)
    # pin_ai_neutral zeroed A's BASE TU, and battle_fire's <tu> clamps to it: A gets A_G3_TU back (base and
    # current, both machines) so vanilla's haveTU admits the shot.
    atu = both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu",
                              "value": A_G3_TU, "refill": True}, ("tu",)).get("tu")
    hh = both(host, client, {"cmd": "battle_set_unit_state", "unit": H_ID, "health": H_G3_HEALTH}, ("health",))
    sel = {"tab": tab_select(host, H_ID), "aimCancel": host_cancel_aim(host)}
    sel["selectedId"] = battle_state(host).get("selectedId")
    staged = diff_buckets(host, client)
    before = snap2(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    rf = {}
    try:
        host.ok({"cmd": "set_seed", "seed": SEED_G3})
        rf = host.cmd({"cmd": "battle_fire", "unit": A_ID, "mode": "snap", "target": H_ID, "tu": TU_MAX,
                       "keepSelection": True})
        assert rf.get("ok"), f"battle_fire A answered {rf}"
    except Exception as e:
        notes.append(f"battle_fire A: {short(e)}")
    wait_action_end(host, seq0, notes)
    settle(host, client, notes)
    rec = collect(host, client, before, seq0, rng0)
    uh, uc = units(host), units(client)
    evidence("G3", rec, {"A": pa, "A_tu": atu, "H_health": hh.get("health"), "selection": sel, "fire": rf,
                         "selectedAfter": battle_state(host).get("selectedId"),
                         "H_after": {"host": ubrief(uh.get(H_ID)), "client": ubrief(uc.get(H_ID))},
                         "A_after": {"host": ubrief(uh.get(A_ID)), "client": ubrief(uc.get(A_ID))},
                         "stagedDiff": staged, "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if sel["selectedId"] != H_ID:
        fails.append(f"precondition: the host's selected unit {sel['selectedId']} (want H {H_ID}: PR-E1)")
    fails += shots_fails(rec, 1, A_ID, "snap", "A's stand-in shot at the selected H (PR-E1)")
    fails += common_fails(host, client, rec, True, "G3")
    for s, p in rec["shots"][:1]:
        fails += record_fails(rec, s, p, FLOOR_FIRE, SEAT_NONE)
    finish(fails)


def g4_autoshot(host, client, ctx):
    notes = []
    rng0 = rng_of(client)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc = place(host, client, C_ID, LANE_TILE, LANE_DIR)
    set_tu_both(host, client, C_ID, TU_MAX)
    set_firing_both(host, client, C_ID)
    staged = diff_buckets(host, client)
    before = snap2(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv, out = {}, {}
    try:
        pv = aim_click(client, KEY_AUTO, LANE_TARGET, lambda: host.ok({"cmd": "set_seed", "seed": SEED_G4}))
    except Exception as e:
        notes.append(f"client real-UI autoshot: {short(e)}")
    out = await_press(host, client, before, notes)
    settle(host, client, notes)
    rec = collect(host, client, before, seq0, rng0)
    evidence("G4", rec, {"rifle": rifle, "clip": clip, "C": pc, "stagedDiff": staged, "press": pv, "outcome": out,
                         "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    fails += shots_fails(rec, G4_SHOTS, C_ID, "auto", "C's real-UI autoshot")
    idx = [p.get("shotIndex") for _, p in rec["shots"]]
    if idx != list(range(1, G4_SHOTS + 1)):
        fails.append(f"precondition: shotIndex in seq order {idx} (want {list(range(1, G4_SHOTS + 1))})")
    fails += common_fails(host, client, rec, True, "G4")
    for s, p in rec["shots"]:
        fails += record_fails(rec, s, p, CLIENT_FIRE_DIAL, COOP_SEAT_1)
    finish(fails)


def g5_throw(host, client, ctx):
    notes = []
    rng0 = rng_of(client)
    gid = give_grenade(host, client, primed=False)
    pc = place(host, client, C_ID, G5_C_TILE, G5_C_DIR)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    before = snap2(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv, out = {}, {}
    try:
        target_order(client, pv, KEY_THROW, CURSOR_THROW, G5_TARGET,
                     lambda: host.ok({"cmd": "set_seed", "seed": SEED_G5}))
    except Exception as e:
        notes.append(f"client real-UI throw: {short(e)}")
    out = await_press(host, client, before, notes)
    settle(host, client, notes)
    rec = collect(host, client, before, seq0, rng0)
    items = {n: {"owner": (it or {}).get("owner"), "tile": tile_of(it), "fuse": (it or {}).get("fuse")}
             for n, it in (("host", items_by_id(host).get(gid)), ("client", items_by_id(client).get(gid)))}
    evidence("G5", rec, {"grenade": gid, "C": pc, "stagedDiff": staged, "press": pv, "outcome": out,
                         "grenadeAfter": items, "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if pv.get("rows") != G5_ROWS:
        fails.append(f"precondition: client menu rows {pv.get('rows')} (want {G5_ROWS})")
    fails += shots_fails(rec, 1, C_ID, "throw", "C's real-UI throw")
    if rec["shots"] and not isinstance(rec["shots"][0][1].get("arc"), dict):
        fails.append(f"precondition: the throw's payload carries no arc {rec['shots'][0][1]}")
    fails += common_fails(host, client, rec, True, "G5")
    k = ctx["constants"]
    for s, p in rec["shots"][:1]:
        fails += record_fails(rec, s, p, CLIENT_FIRE_DIAL, COOP_SEAT_1, arc=True)
        r = (rec["ring"].get(s) or [{}])[0]
        if r.get("sound") != k.get("ITEM_THROW") or r.get("soundEnd") != k.get("ITEM_DROP"):
            fails.append(f"shot seq {s}: record sound {r.get('sound')} soundEnd {r.get('soundEnd')} (want ITEM_THROW "
                         f"{k.get('ITEM_THROW')}, ITEM_DROP {k.get('ITEM_DROP')})")
    finish(fails)


def g7_option_off(host, client, ctx):
    notes = []
    rng0 = rng_of(client)
    off = client.ok({"cmd": "set_option", "name": "coopGhostStepper", "value": False}).get("value")
    ph = place(host, client, H_ID, LANE_TILE, LANE_DIR)
    set_tu_both(host, client, H_ID, TU_MAX)
    lane = {"host": lane_units(host, H_ID), "client": lane_units(client, H_ID)}
    staged = diff_buckets(host, client)
    before = snap2(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    rf = {}
    try:
        host.ok({"cmd": "set_seed", "seed": SEED_G7})
        rf = host.cmd({"cmd": "battle_fire", "unit": H_ID, "mode": "snap", "x": LANE_TARGET[0], "y": LANE_TARGET[1],
                       "z": LANE_TARGET[2], "tu": TU_MAX})
        assert rf.get("ok"), f"battle_fire H answered {rf}"
    except Exception as e:
        notes.append(f"battle_fire H: {short(e)}")
    wait_action_end(host, seq0, notes)
    settle(host, client, notes)
    rec = collect(host, client, before, seq0, rng0)
    on = client.ok({"cmd": "set_option", "name": "coopGhostStepper", "value": True}).get("value")
    evidence("G7", rec, {"optionOff": off, "optionBackOn": on, "H": ph, "laneOthers": lane, "fire": rf,
                         "stagedDiff": staged, "notes": notes})
    fails = list(notes)
    if off is not False or on is not True:
        fails.append(f"client coopGhostStepper lever answered off={off} on={on} (want False then True)")
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if lane["host"] or lane["client"]:
        fails.append(f"precondition: units on the lane besides H: {lane} (want none)")
    fails += shots_fails(rec, 1, H_ID, "snap", "H's stand-in snap")
    b, a = rec["before"]["client"], rec["after"]["client"]
    dc = cue_delta(b["cueCounts"], a["cueCounts"], "shot")
    de = cue_delta((b["combatGhost"] or {}).get("enqueued"), (a["combatGhost"] or {}).get("enqueued"), "shot")
    if dc != 1 or de != 0:
        fails.append(f"client cueCounts.shot +{dc} combatGhost.enqueued.shot +{de} while the option is off (want +1 "
                     f"and +0: Q4 = a)")
    fails += common_fails(host, client, rec, False, "G7")
    finish(fails)


def g8_input_during_flight(host, client, ctx):
    notes = []
    rng0 = rng_of(client)
    host.ok({"cmd": "set_option", "name": "battleFireSpeed", "value": G8_HOST_FIRE_DIAL})
    dial = wait_seat_dial(host, client, COOP_SEAT_0, "fire", G8_HOST_FIRE_DIAL)
    ph = place(host, client, H_ID, LANE_TILE, LANE_DIR)
    set_tu_both(host, client, H_ID, TU_MAX)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    sel0 = {"tabC2": tab_select(client, C2_ID), "selectedId": battle_state(client).get("selectedId"),
            "cursor": battle_state(client).get("cursorType")}
    lane = {"host": lane_units(host, H_ID), "client": lane_units(client, H_ID)}
    staged = diff_buckets(host, client)
    before = snap2(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    shot0 = kind_of(before["client"]["cueCounts"], "shot")
    tl, mid, rf = {}, {"liveSeen": None, "liveAtMenu": None, "menu": None, "selectedAtMenu": None}, {}
    try:
        host.ok({"cmd": "set_seed", "seed": SEED_G8})
        t0 = time.time()
        rf = host.cmd({"cmd": "battle_fire", "unit": H_ID, "mode": "snap", "x": LANE_TARGET[0], "y": LANE_TARGET[1],
                       "z": LANE_TARGET[2], "tu": TU_MAX})
        assert rf.get("ok"), f"battle_fire H answered {rf}"
        client.wait_for("client applied the host's shot",
                        lambda: kind_of(event_state(client).get("cueCounts"), "shot") > shot0 or None,
                        timeout=20, interval=POLL_S)
        t_shot = time.time()
        tl["shotApplied"] = round(t_shot - t0, 3)
        t1 = time.time()
        while time.time() - t1 < G8_LIVE_WAIT_S:
            live = (event_state(client).get("combatGhost") or {}).get("live")
            if live == 1:
                mid["liveSeen"] = round(time.time() - t_shot, 3)
                break
            time.sleep(POLL_S)
        tl["liveWaitEnd"] = round(time.time() - t0, 3)
        mid["tab"] = tab_select(client, C_ID)
        r = click_nth(client, RHAND_NTH)
        mid["rhandClick"] = (r.get("baseX"), r.get("baseY"))
        assert mid["rhandClick"] == RHAND_CENTRE, f"right-hand click landed off the box: {r}"
        client.wait_for("client ActionMenuState on top", lambda: top(client) == "ActionMenuState" or None,
                        timeout=5, interval=POLL_S)
        t_menu = time.time()
        mid["menu"] = True
        mid["latencyS"] = round(t_menu - t_shot, 3)
        mid["liveAtMenu"] = (event_state(client).get("combatGhost") or {}).get("live")
        mid["selectedAtMenu"] = battle_state(client).get("selectedId")
        tl["menu"] = round(t_menu - t0, 3)
    except Exception as e:
        notes.append(f"G8 drive: {short(e)}")
    try:
        if top(client) == "ActionMenuState":
            press(client, SDLK_ESCAPE)
            client.wait_for("client back on BattlescapeState", lambda: top(client) == "BattlescapeState" or None,
                            timeout=5)
    except Exception as e:
        notes.append(f"closing the action menu: {short(e)}")
    wait_action_end(host, seq0, notes)
    settle(host, client, notes)
    rec = collect(host, client, before, seq0, rng0)
    host.ok({"cmd": "set_option", "name": "battleFireSpeed", "value": HOST_FIRE_DIAL})
    dial_back = wait_seat_dial(host, client, COOP_SEAT_0, "fire", HOST_FIRE_DIAL)
    evidence("G8", rec, {"dial": dial, "dialBack": dial_back, "H": ph, "rifle": rifle, "clip": clip,
                         "selection0": sel0, "laneOthers": lane, "fire": rf, "timeline": tl, "mid": mid,
                         "stagedDiff": staged, "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if sel0["selectedId"] != C2_ID:
        fails.append(f"precondition: the client's selected unit before the shot {sel0['selectedId']} (want C2 "
                     f"{C2_ID}: the press needs a TAB)")
    fails += shots_fails(rec, 1, H_ID, "snap", "H's stand-in snap at dial 1")
    fails += common_fails(host, client, rec, True, "G8")
    if mid["liveSeen"] is None:
        fails.append(f"client combatGhost.live never 1 within {G8_LIVE_WAIT_S} s of the shot's apply (want the "
                     f"ghost live)")
    if not mid["menu"] or mid["liveAtMenu"] != 1 or mid["selectedAtMenu"] != C_ID:
        fails.append(f"client ActionMenuState {mid['menu']} with combatGhost.live {mid['liveAtMenu']} and the "
                     f"selection {mid['selectedAtMenu']} (want the menu open for C while the ghost is live: Q3 = b)")
    for s, p in rec["shots"][:1]:
        fails += record_fails(rec, s, p, G8_HOST_FIRE_DIAL, COOP_SEAT_0)
        r = (rec["ring"].get(s) or [{}])[0]
        if (r.get("steps") or 0) < G8_MIN_STEPS:
            fails.append(f"shot seq {s}: record steps {r.get('steps')} (want >= {G8_MIN_STEPS}: the flight animated)")
    finish(fails)


def g6_launch(host, client, ctx):
    notes = []
    rng0 = rng_of(client)
    launcher, bomb = give_launcher(host, client)
    pc = place(host, client, C_ID, G6_C_TILE, G6_C_DIR)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    before = snap2(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv, out = {}, {}
    try:
        launch_order(client, pv, lambda: host.ok({"cmd": "set_seed", "seed": SEED_G6}))
    except Exception as e:
        notes.append(f"client real-UI launch: {short(e)}")
    out = await_press(host, client, before, notes)
    settle(host, client, notes)
    rec = collect(host, client, before, seq0, rng0)
    evidence("G6", rec, {"launcher": launcher, "bomb": bomb, "C": pc, "stagedDiff": staged, "press": pv,
                         "outcome": out, "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    fails += shots_fails(rec, G6_LEGS, C_ID, "launch", "C's real-UI launch, two legs")
    fails += common_fails(host, client, rec, True, "G6")
    for s, p in rec["shots"]:
        fails += record_fails(rec, s, p, CLIENT_FIRE_DIAL, COOP_SEAT_1)
    finish(fails)


SCENARIOS = (("G1", g1_host_snap), ("G2", g2_client_snap), ("G3", g3_unowned), ("G4", g4_autoshot),
             ("G5", g5_throw), ("G7", g7_option_off), ("G8", g8_input_during_flight), ("G6", g6_launch))


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
    pinned = pin_ai_neutral(host, client, tag="w2p5-sa")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hs["units"] if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == SEATED, f"seated client units {seated_uids} (baked {SEATED})"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    opts = {gc.name: gc.ok({"cmd": "set_option", "name": "coopGhostStepper"}).get("value") for gc in (host, client)}
    assert opts == {"host": True, "client": True}, f"coopGhostStepper at boot {opts} (want True on both: pinned)"
    client.ok({"cmd": "set_option", "name": "battleFireSpeed", "value": CLIENT_FIRE_DIAL})
    host.ok({"cmd": "set_option", "name": "battleFireSpeed", "value": HOST_FIRE_DIAL})
    d1 = wait_seat_dial(host, client, COOP_SEAT_1, "fire", CLIENT_FIRE_DIAL)
    d0 = wait_seat_dial(host, client, COOP_SEAT_0, "fire", HOST_FIRE_DIAL)
    for gc in (host, client):
        es = event_state(gc)
        assert all(k in es for k in ("combatGhost", "derivedPaths", "rngSeed", "shotTrajectories")), (
            f"{gc.name} event_state lacks the W2-P5 S-A.1 probes: "
            f"{[k for k in ('combatGhost', 'derivedPaths', 'rngSeed', 'shotTrajectories') if k not in es]}")
    dr = client.ok({"cmd": "display_rules", "types": list(DISPLAY_TYPES)})
    missing = [t for t in DISPLAY_TYPES if not (dr.get("items") or {}).get(t)]
    assert not missing, f"display_rules knows no {missing}: {dr}"
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    ub = session.units_by_id(hs)
    print(f"[w2p5-sa] boot ok: {MISSION} MAP_FP={MAP_FP!r} turn={hs['turn']} seated={seated_uids} H={H_ID} "
          f"pinned={len(pinned)} dials={d0} coopGhostStepper={opts} C={ubrief(ub.get(C_ID))} "
          f"H={ubrief(ub.get(H_ID))} A={ubrief(ub.get(A_ID))} display_rules={json.dumps(dr, sort_keys=True)}",
          flush=True)
    return {"rules": dr["items"], "constants": dr["constants"], "dials": d1}


def main():
    t0 = time.time()
    host = GameClient("host", 49888, make_user_dir("w2p5_ghost_projectile_host", options={"coopGhostStepper": True}))
    client = GameClient("client", 49889, make_user_dir("w2p5_ghost_projectile_client",
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
                print(f"[w2p5-sa] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_ghost_projectile: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
