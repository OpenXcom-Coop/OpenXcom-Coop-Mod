"""W1-P11 (rewrite wave 1, WAVE1-RUNBOOK.md SS4 "ATOM spot" = WV-D26): the
SPOTTING HALT as a first-class ev - "a walk that stops on contact is the same
story on both machines".

WHAT THE PACKET REQUIRES, and where each requirement is asserted below:

  PHASE 0  THE REACTION-FIRE PIN. See "THE HARD PART" below - this is the whole
           risk of the packet and it is engineered, not hoped for. Asserted as a
           READ-BACK on both machines plus all-buckets-EQUAL, because a pin you
           cannot read is not a pin.
  PHASE 1  THE SCRIPTED CONTACT. The walk halts on BOTH machines at the SAME
           tile; the step evs emitted before the halt STAND (SS2.W2 rule 5 - no
           retraction, no rewind); the completion `path` is exactly the executed
           prefix; the `spot` ev sits at its OWN position in the seq stream
           (after the last `walk_step` of its actionId, before that action's
           `bt_action_end`); `unitsCore`/`unitsStats` - indeed all nine buckets -
           EQUAL at the halt; the ORDERING SEAT shows the exact cancel banner;
           the per-side reveal sets (W1-P8) are still EQUAL after the contact.
  PHASE 2  THE CONTROL. One more walk for the same actor immediately afterwards:
           either it does NOT halt on spot and emits NO second `spot` ev (which
           proves the halt is not latched and that `seen` really is the
           ADDITIONS to the actor's spotted-this-turn set rather than the whole
           set), or it spots something NEW and its `seen` is DISJOINT from the
           first one's - which proves the same thing more strongly.

============================================================================
THE HARD PART, AND IT IS NOT THE ATOM: A SPOT WITHOUT A SHOT.

`TileEngine::checkReactionFire` sits INSIDE the very `if (unitSpotted)` region
this packet hooks (UnitWalkBState.cpp - the reaction check is the next statement
after the spot halt's own `return cancelCurentMove()`), so spot and reaction fire
are ADJACENT BY CONSTRUCTION. And S5's AI-ORIGIN PRECONDITION rules that an alien
SHOT is an EXPECTED client desync freeze for the whole of wave 1 - W1-P10 lost
multiple cycles to exactly this, its crossing walks wandering into alien LOS and
producing terrain/items/unitsStats/saveBlob divergences that looked like product
bugs and were not.

So this file does not hope for a shot-free spot; it makes one IMPOSSIBLE, and it
does so with ONE field. PHASE 0 sets `reactions` to 0 on every living non-player
unit, on BOTH machines. That closes THREE independent gates in vanilla, any one
of which alone would be enough:

  1. `TileEngine::getSpottingUnits()` keeps a candidate only while
     `bu->getReactionScore() >= threshold`, where `threshold` is the WALKER's own
     score. BattleUnit::getReactionScore() is `reactions * TU / maxTU`, so a
     zeroed unit scores exactly 0.0 and a walker with reactions > 0 and TU > 0
     scores > 0 - the alien never enters the spotters vector at all.
  2. `TileEngine::getReactor()` returns 0 unless
     `walker->getReactionScore() <= best->reactionScore`, which is false for the
     same reason.
  3. `TileEngine::determineReactionType()` returns early on
     `reactionScore <= 0.001` with `attackType = BA_NONE` and `weapon = nullptr`,
     and `tryReaction()`'s first statement is
     `if (!_save->canUseWeapon(action.weapon, ...)) return false;`.

Gate 1 depends on the walker's score being strictly positive, so PHASE 0 also
ASSERTS the actor's own `reactions > 0` and PHASE 1 asserts its TU > 0 at the
halt - the only way `threshold` could be 0 is a walker at 0 TU, and gates 2 and 3
still hold even then.

`currStats` IS serialized (BattleUnit::save writes it) and is NOT on
SharedEcon's `saveBlobExcludedUnitKey` list, so it rides the saveBlob bucket:
the pin is applied to BOTH machines and PHASE 0 asserts all buckets EQUAL
immediately afterwards, which is what proves the application was symmetric.

Belt and braces, because a pin can rot: every leg of the approach also asserts
that the host's `items` and `terrain` bucket hashes are UNCHANGED from the
pre-walk baseline (a reaction shot spends ammo and damages terrain - that is the
exact signature W1-P10 traced), that no `hit`/`death` ev reached either ring,
that the actor's health and stun never moved, and that no halt ever reports
SS2.W2's `reaction` reason. A run that DOES get shot at therefore fails loudly
and specifically, instead of surfacing as a mysterious hash red.
============================================================================

FIXTURE (WR-29, and the RB-D15/IR-4 "pin the selection rule" shape). Walk-core's
fixtures are CONTACT-FREE by construction (WV-D18) precisely so they cannot take
this halt, so this packet must CREATE the contact rather than find one. The
qualifying rule is repro_atom_turn.py's rule (c) INVERTED:
session.actor_is_contact_free() asks for NO living non-player unit within
session.MAX_VIEW_DISTANCE; this file asks for one INSIDE a band, close enough
that a few steps can bring it into view and far enough that the actor is not
already standing in its lap. Everything else about the fixture is the shared
helper set (bring_up_lobby / drive_to_battlescape / straight_runs /
send_walk_outcome, imported from repro_atom_walk).

FIXTURE EXHAUSTION IS A SKIP, NOT A RED (the orchestrator's 2026-09-03 ruling,
shipped in repro_atom_door.py). "The map generator never offered a testable
situation" is a statement about map generation, not about the spot atom.
`FixtureExhausted` is raised at EXACTLY ONE site - the end of the bring-up
re-roll loop - with a rejection histogram; every assertion inside the drive is a
hard FAIL (exit 2) whether or not a contact was eventually staged, so a SKIP
cannot mask a real failure.

WHY THE ASSERTIONS HERE ARE NOT VACUOUS - the checks that would go RED:
  * The stream-position check reads the event ring on BOTH machines and requires
    the `spot` entry's seq to be strictly ABOVE every `walk_step` of the same
    actionId and strictly BELOW that action's `bt_action_end`. An implementation
    that emitted the spot before the last step, or folded it into the
    action_end, fails here and nowhere else.
  * The reason check requires `spot` EXACTLY. Both vanilla halt sites leave
    `_action.result` empty, so without W1-P11's own hook the completion restate
    reports W1-P9's catch-all `blocked` and the ordering seat shows
    "Move stopped - path blocked" - so BOTH the reason assert and the exact-text
    banner assert go red on a missing latch, independently.
  * The delivery proof is `coopSpotEvsApplied` plus the client's own `lastSpot`
    matching the host's field for field, INCLUDING `seq`.

AND ONE HONEST LIMIT, MEASURED WITH A CONTROL BUILD RATHER THAN ARGUED (the
builder found this by running the control, not by reasoning about it):

  * "the CLIENT's spottedThisTurn set contains `seen`" is a CONSISTENCY check,
    NOT a delivery proof, and it cannot be made into one on the walk path. With
    the applier's `spotted.push_back(seenUnit)` compiled out and the exe rebuilt,
    this file STILL PASSED - twice, once with the client's selection on the
    walker and once parked off it. The reason is A5's targeted per-unit FOV
    refresh: CoopDisplayQueue::onApplied() calls
    `save->getTileEngine()->calculateFOV(unit)` for EVERY bt_ev that carries a
    `unit` payload field (connectionTCP.cpp, the "A5 (turn/kneel bt_ev path)"
    block and the bt_action_end block above it), and SS2.4a suppresses only the
    TILE half of a client's FOV - `calculateUnitsInFOV` is untouched and writes
    _unitsSpottedThisTurn locally. So on this path the client reaches the host's
    answer by its own recompute, per walk step, whether or not the `spot` ev's
    bookkeeping is applied at all.
    The apply is KEPT because it is prd-r3a's specified shape and because host
    truth is strictly safer than a client-side derivation SS2.4a permits but
    does not guarantee to agree - it is the belt to A5's braces, it is
    idempotent (it de-duplicates) and it is hash-neutral. It is simply not what
    this file's green proves. What this file DOES prove is the atom's
    load-bearing half: the halt REASON, the ev's POSITION in the seq stream, and
    the exact banner on the ordering seat - each of which was RED in its own
    control build.
  * PHASE 2 asserts the SECOND walk emits no second `spot` for a unit already in
    the set - an implementation that shipped the whole set instead of the
    additions, or that never cleared the halt, fails there.

Run:  python tools/coop_test/repro_atom_spot.py
      (in its OWN shell invocation - the standing harness rule, one harness run
       at a time, machine-wide. Headless is forced by harness.GameClient.spawn();
       export SDL_VIDEODRIVER=dummy / SDL_AUDIODRIVER=dummy anyway.)

Exit codes: 0 PASS - 2 FAIL - 3 SKIP (fixture exhausted).
"""

import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import assert_hash_clean, assert_reveal_parity
import repro_atom_walk as W

COOP_SEAT_1 = 1
FACTION_PLAYER = 0

EXIT_PASS, EXIT_FAIL, EXIT_SKIP = 0, 2, 3


class FixtureExhausted(Exception):
    """MAX_REROLLS boots produced no stageable contact. Carries the histogram."""


# The bring-up ceiling. Each boot is ~25-40 s plus a bounded drive, so this is
# sized for a fixture that qualifies OFTEN rather than for a lottery: the rule
# below is the INVERSE of the one repro_atom_walk.py re-rolls on, and that file
# measured nearest-alien distances of 10.0 .. 32.6 over 15 boots while needing
# > 24 - i.e. most boots of this map class have an alien inside the band this
# file wants. The measured rate is reported by every run.
MAX_REROLLS = 12

# Seat-1 soldiers to stamp. Each one is an INDEPENDENT chance at a contact (its
# spotted-this-turn set is its own) and TU never regenerates in wave 1, so an
# actor that walks itself dry cannot be reused - the same reason
# repro_atom_walk.py allocates an actor per phase.
SEAT1_SOLDIERS = 5

# THE INVERTED SELECTION RULE. session.actor_is_contact_free() rejects an actor
# with any living non-player unit within session.MAX_VIEW_DISTANCE; this file
# REQUIRES one, inside a band:
#   * below SPOT_CONTACT_MIN the actor is close enough that a single leg could
#     walk into contact range, and a walk that ENDS adjacent to an alien is not
#     a spot fixture, it is a melee fixture;
#   * above SPOT_CONTACT_MAX no achievable number of legs brings it into view -
#     session.MAX_VIEW_DISTANCE is 20 and it is a HARD cap (darkness only ever
#     reduces effective range), so an alien further out than that plus a couple
#     of legs' worth of travel can never be spotted at all.
SPOT_CONTACT_MIN = 5
SPOT_CONTACT_MAX = 20 + 6

# No candidate destination may bring the actor within this many tiles of ANY
# living non-player unit. Keeps the contact a SPOTTING event and nothing else -
# no melee, no walking onto the alien's tile, and no `path_changed` deny from a
# plan that runs through it.
APPROACH_FLOOR = 4

# Legs per actor, and destinations tried per leg. A leg is 1-3 tiles; a soldier
# holds ~55 TU and a tile costs 4-8, so ~4 legs is the whole TU budget and the
# fifth would only ever produce a `no_tu` halt.
MAX_LEGS = 4
CANDIDATES_PER_LEG = 4

# `tile_is_open_ground` is one round trip per tile and the ordered ring can hold
# ~150 of them across three z-levels; the fixture rule calls this once per
# seat-1 soldier, so an unbounded scan costs minutes per boot. Bounded: the ring
# is sorted nearest-to-target first, so the tiles that matter are probed first.
MAX_TILE_PROBES = 45

SDLK_TAB = 9  # Options::keyBattleNextUnit default (repro_atom_walk.py precedent)

# EXACT text, from bin/common/Language/en-US.yml (asserted as TEXT and never as
# an STR_ key: Language::getString() returns the KEY when it is missing, so a
# key-shaped assert passes silently against a stale deploy copy - WV-D17).
# SS2.W2's halt-presenter table maps `spot` to the EXISTING SS2.6 row
# STR_COOP_CANCEL_ENEMY_SPOTTED, already wired by W1-P9; this packet mints NO
# new string, because an unreferenced key would be a WV-D41 orphan.
STR_HALT_SPOT = "Order cancelled - enemy spotted"
STR_HALT_BLOCKED = "Move stopped - path blocked"

# SS2.W2's frozen halt enum, for the "is this even a legal reason" check.
HALT_REASONS = ("spot", "reaction", "blocked", "no_tu", "no_energy", "prox",
                "fall", "unit_down")


# ----- small probes (thin wrappers over the shared helpers) ----------------

def battle_state(gc):
    return gc.cmd({"cmd": "battle_state"})


def event_state(gc):
    return gc.cmd({"cmd": "event_state"})


def units_by_id(resp):
    return {u["id"]: u for u in resp.get("units", [])}


def unit_of(gc, uid):
    return units_by_id(battle_state(gc))[uid]


def banner(gc):
    return battle_state(gc).get("coopWaitText", "")


def last_spot(gc):
    return event_state(gc).get("lastSpot") or {}


def pos_of(u):
    return (u["x"], u["y"], u["z"])


def dist3(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def living_non_players(st):
    return [u for u in st.get("units", [])
            if u.get("faction") != FACTION_PLAYER and not u.get("isOut")]


def bucket_hashes(gc):
    r = gc.cmd({"cmd": "hash_now", "full": True})
    assert r.get("ok"), f"hash_now failed: {r}"
    h = r.get("h", {})
    assert h, f"hash_now returned an empty 'h' object (no live battle?): {r}"
    return dict(h)


def ring(gc, tail=120):
    r = gc.cmd({"cmd": "event_log", "tail": tail})
    assert r.get("ok"), f"event_log failed: {r}"
    return r.get("events", [])


# ----- fixture bring-up ---------------------------------------------------

def drive_to_battlescape(host, client, seated):
    """repro_atom_walk.drive_to_battlescape, with this file's own seat count and
    WITHOUT its door/contact rules (which are exactly what this packet inverts).
    Deliberately leaves the NEW BATTLE mission on the persisted default: trap 11
    of this wave - a CRAFT SKIRMISH is MEASURED clean at t=0, while UFO map
    classes carry the separate, already-diagnosed `itemIdCtr` divergence
    (SavedBattleGame.cpp:351/:356, an owner ruling in flight) that would red this
    file's hash asserts for a reason that is not this packet's."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert W.top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={W.states(host)}"

    soldier_ids = []
    for i in range(SEAT1_SOLDIERS):
        r = host.cmd({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1, "index": i})
        if not r.get("ok"):
            break
        soldier_ids.append(r["soldierId"])
    assert len(soldier_ids) >= 3, \
        f"newbattle_seat_soldier stamped only {len(soldier_ids)} soldier(s) to seat 1 - " \
        "this repro needs at least three client-owned actors, each an independent " \
        "chance at a contact (see SEAT1_SOLDIERS)"
    seated["soldierIds"] = soldier_ids

    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=30)
    client.wait_for("client battlescape",
                    lambda: session.has_state(client, "BattlescapeState"), timeout=60)
    time.sleep(3)
    host.ok({"cmd": "click_widget", "match": "ok"})
    host.wait_for("host battlescape",
                  lambda: session.has_state(host, "BattlescapeState"), timeout=30)
    session.dismiss_battle_start_overlays(host)
    # W1-P3 (D3): the client enters through a read-only BriefingState pushed OVER
    # its BattlescapeState - every fixture that DRIVES the client must dismiss it.
    session.dismiss_client_briefing(client)


def seat1_units(host, soldier_ids):
    st = battle_state(host)
    want = set(soldier_ids)
    return [u for u in st.get("units", [])
            if u.get("soldierId") in want and not u.get("isOut")]


def fixture_rejection(host, client, soldier_ids):  # noqa: C901
    """The INVERTED selection rule. Returns None when this boot can be driven,
    else a one-line reason (the histogram key is its leading clause).

    Rules, in order:
      (a) NOTHING already spotted at t=0. Kept from repro_atom_turn.py verbatim:
          an alien a player unit can already see is an alien whose reaction fire
          the approach walk is standing in front of, and it is also an alien this
          actor may already carry in its spotted-this-turn set - in which case
          the walk cannot produce a NEW spot at all.
      (c-inv) at least one seat-1 soldier has a living non-player unit inside
          [SPOT_CONTACT_MIN, SPOT_CONTACT_MAX]. This is session.
          actor_is_contact_free()'s predicate with the sense reversed, and it is
          pinned exactly as hard: a boot that fails it is RE-ROLLED, never
          driven with a relaxed assertion.
      (d) the actor's OWN spotted-this-turn set is empty ON BOTH MACHINES, so a
          spot during its walk is a genuine ADDITION. Readable directly since
          this packet (battle_state's per-unit `spottedThisTurn`). Checked on
          the client too because that set is machine-local: a client that has
          ever SELECTED a unit has computed that unit's FOV for itself
          (SS2.W5), which the host has not.
      (e) at least one routable, contact-floor-respecting approach destination
          exists for that actor.
    """
    st = battle_state(host)
    if not st.get("ok") or not st.get("inBattle"):
        return "no battle: battle_state reports inBattle=False"
    if st.get("spotted"):
        return f"rule (a) a hostile is ALREADY spotted at t=0: {st['spotted']}"

    aliens = living_non_players(st)
    if not aliens:
        return "rule (c-inv) the map holds no living non-player unit at all"

    mine = seat1_units(host, soldier_ids)
    if not mine:
        return "no seat-1 soldier resolved to a live battle unit"

    occupied = {pos_of(u) for u in st["units"] if not u.get("isOut")}
    cst = units_by_id(battle_state(client))
    best = None
    for u in mine:
        cu = cst.get(u["id"], {})
        if u.get("spottedThisTurn") or cu.get("spottedThisTurn"):
            continue                                        # rule (d), BOTH machines
        d = session.nearest_non_player_distance(st, u)
        if d is None or not (SPOT_CONTACT_MIN <= d <= SPOT_CONTACT_MAX):
            continue                                        # rule (c-inv)
        cands = approach_candidates(host, u, aliens, occupied)
        if not cands:
            continue                                        # rule (e)
        if best is None or d < best[0]:
            best = (d, u, len(cands))
    if best is None:
        ds = []
        for u in mine:
            d = session.nearest_non_player_distance(st, u)
            ds.append("none" if d is None else "%.1f" % d)
        return ("rule (c-inv/d/e) no seat-1 soldier has a clean, approachable "
                "non-player unit in the band [%d, %d] - per-actor nearest: %s"
                % (SPOT_CONTACT_MIN, SPOT_CONTACT_MAX, ", ".join(ds)))

    d, u, ncands = best
    print("[repro_atom_spot] rule (c-inv) ok: actor %d (soldierId %s) at %s has a "
          "living non-player unit %.2f tiles away (band [%d, %d]), %d approach "
          "destination(s), its own spotted-this-turn set EMPTY"
          % (u["id"], u.get("soldierId"), pos_of(u), d, SPOT_CONTACT_MIN,
             SPOT_CONTACT_MAX, ncands))
    return None


def approach_candidates(host, actor, aliens, occupied, radii=(2, 3, 1)):
    """Open-ground destinations that move the actor CLOSER to the nearest living
    non-player unit without ever coming inside APPROACH_FLOOR of any of them.

    Searched across z, z-1 and z+1 and ordered nearest-to-target-first, for the
    reason repro_atom_walk.straight_runs() documents and MEASURED: the squad
    starts INSIDE the Skyranger, whose deck sits one level ABOVE the terrain, so
    a same-level-only search finds air on every side and 15/15 boots produce no
    candidate at all. Pathfinding routes the drop itself.

    This is the INVERSE ordering of straight_runs(), which sorts the destination
    FURTHEST from contact first."""
    apos = [(a["x"], a["y"], a["z"]) for a in aliens]
    if not apos:
        return []
    here = pos_of(actor)
    target = min(apos, key=lambda p: dist3(here, p))
    d_here = dist3(here, target)

    ring_tiles = []
    for radius in radii:
        for dz in (0, -1, 1):
            z = actor["z"] + dz
            if z < 0:
                continue
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if max(abs(dx), abs(dy)) != radius:
                        continue
                    t = (actor["x"] + dx, actor["y"] + dy, z)
                    if min(dist3(t, a) for a in apos) < APPROACH_FLOOR:
                        continue                       # never close in past the floor
                    d_t = dist3(t, target)
                    if d_t >= d_here:
                        continue                       # must actually approach
                    ring_tiles.append((d_t, abs(dz), t))
    ring_tiles.sort(key=lambda e: (e[0], e[1]))

    out = []
    probed = 0
    for _, _, t in ring_tiles:
        if probed >= MAX_TILE_PROBES:
            break
        probed += 1
        if W.tile_is_open_ground(host, t[0], t[1], t[2], occupied):
            out.append(t)
            if len(out) >= CANDIDATES_PER_LEG * 2:
                break
    return out


# ----- PHASE 0: the reaction-fire pin -------------------------------------

def phase0_pin_reaction_fire(host, client):
    """Make an alien reaction shot IMPOSSIBLE, then PROVE it. See the module
    docstring for the three vanilla gates this closes and why one field is
    enough. Returns the actor-independent baseline bucket hashes every later leg
    checks itself against."""
    st = battle_state(host)
    aliens = living_non_players(st)
    assert aliens, "PHASE 0: no living non-player unit to pin - the fixture rule " \
                   "should have rejected this boot"

    for a in aliens:
        for gc, tag in ((host, "host"), (client, "client")):
            r = gc.cmd({"cmd": "battle_action", "action": "set_stat",
                        "unit": a["id"], "stat": "reactions", "value": 0})
            assert r.get("ok"), \
                f"PHASE 0: could not zero unit {a['id']}'s reactions on the {tag}: {r}"

    # READ-BACK on BOTH machines. A pin that cannot be read is not a pin, and the
    # symmetry matters twice over: `currStats` is serialized and NOT on
    # saveBlobExcludedUnitKey's list, so an asymmetric write would diverge the
    # saveBlob bucket - which the hash assert below is what catches.
    for gc, tag in ((host, "host"), (client, "client")):
        live = living_non_players(battle_state(gc))
        bad = [(u["id"], u.get("reactions")) for u in live if u.get("reactions") != 0]
        assert not bad, (
            f"PHASE 0: on the {tag}, {len(bad)} living non-player unit(s) still carry a "
            f"non-zero `reactions` stat {bad} - reaction fire is NOT pinned and S5's "
            "AI-ORIGIN PRECONDITION makes an alien shot an EXPECTED wave-1 client "
            "desync freeze, so this run could not tell a fixture accident from a "
            "product defect")
        assert live, f"PHASE 0: the {tag} reports no living non-player unit at all"

    host_h, client_h = assert_hash_clean(
        host, client, full=True,
        what="after PHASE 0 zeroed every non-player unit's `reactions` on both machines")
    print(f"PASS PHASE 0: reaction fire PINNED - {len(aliens)} living non-player unit(s) "
          f"at reactions=0 on BOTH machines, all {len(host_h)} buckets EQUAL "
          f"(the write rides `currStats` -> saveBlob, so equality is what proves it "
          f"was applied symmetrically)")
    baseline = dict(host_h)
    baseline["_doorEvs"] = event_state(host)["coopDoorEvsEmitted"]
    return baseline


def assert_reaction_pin_holds(host, client, baseline, what):
    """The belt-and-braces half, run after EVERY leg. Anything a reaction shot
    would have done, asserted absent - and asserted by its SIGNATURE, not by the
    absence of a log line:
      * `items` moves when a shot spends ammo (SS2.8: the items bucket carries
        ammoQty). A WALK cannot move it, so it is a clean, unconditional control.
      * `terrain` moves when a shot damages the map - and ALSO, legitimately,
        when a walk auto-opens a NORMAL door, because W1-P10's `door` atom
        rewrites the part's mapDataID/mapDataSetID and that is exactly what this
        bucket sums. MEASURED, not reasoned: the first version of this control
        asserted `terrain` unconditionally and went red on a door crossing during
        the control build's longer walks. So the rule is CONDITIONAL and the
        baseline MOVES WITH IT: terrain may change only on a leg that emitted a
        `door` ev, and the new value becomes the baseline. A terrain change with
        no door ev is still a hard failure - which is the shot signature W1-P10
        traced.
      * a `hit` or `death` ev on either ring is the direct evidence.
      * neither machine may be desync-frozen.
    @a baseline is MUTATED by this function (it is the running baseline).
    """
    hh = bucket_hashes(host)
    doors = event_state(host)["coopDoorEvsEmitted"]
    assert hh["items"] == baseline["items"], (
        f"{what}: the HOST's `items` bucket moved ({baseline['items']} -> "
        f"{hh['items']}) during a plain walk. That is the signature of a REACTION "
        "SHOT (ammo spent) - PHASE 0's reactions=0 pin has failed, and S5's "
        "AI-ORIGIN PRECONDITION means the client is now expected to desync for a "
        "reason that is NOT this packet's atom")
    if hh["terrain"] != baseline["terrain"]:
        assert doors > baseline["_doorEvs"], (
            f"{what}: the HOST's `terrain` bucket moved ({baseline['terrain']} -> "
            f"{hh['terrain']}) during a plain walk that emitted NO `door` ev "
            f"(coopDoorEvsEmitted still {doors}). A walk has exactly two ways to "
            "rewrite terrain - W1-P10's door auto-open, and damage - so with the "
            "door excluded this is the REACTION SHOT signature and PHASE 0's pin "
            "has failed")
        print(f"    [{what}] terrain moved with {doors - baseline['_doorEvs']} `door` "
              "ev(s) - a walk-time auto-open (W1-P10), re-baselining")
        baseline["terrain"] = hh["terrain"]
    baseline["_doorEvs"] = doors
    for gc, tag in ((host, "host"), (client, "client")):
        kinds = {e["kind"] for e in ring(gc)}
        assert "hit" not in kinds and "death" not in kinds, (
            f"{what}: the {tag}'s event ring carries a combat ev {sorted(kinds)} - "
            "something shot at the actor")
        assert battle_state(gc)["authority"]["desyncFrozen"] is False, \
            f"{what}: the {tag} is DESYNC-FROZEN"
    live = living_non_players(battle_state(host))
    bad = [(u["id"], u.get("reactions")) for u in live if u.get("reactions") != 0]
    assert not bad, f"{what}: the reaction pin ROTTED mid-run on the host: {bad}"


# ----- PHASE 1: staging and asserting the contact --------------------------

def action_ring(gc, action_id, tail=200):
    """The event ring filtered to ONE actionId, oldest first. This is where the
    SS2.W2 rule 6 statement - "an interleaved consequence arrives as its own ev
    in-stream and breaks the walk exactly at its own position" - becomes an
    assertion rather than a claim."""
    return [e for e in ring(gc, tail=tail) if e.get("actionId") == action_id]


def assert_stream_position(gc, tag, action_id, n_steps):
    """The `spot` ev sits AFTER every `walk_step` of its action and BEFORE that
    action's `bt_action_end`, exactly once, carrying h:{unitsStats} (RB-D14)."""
    entries = action_ring(gc, action_id)
    assert entries, f"{tag}: the event ring holds nothing at all for actionId {action_id}"
    spots = [e for e in entries if e["kind"] == "spot"]
    steps = [e for e in entries if e["kind"] == "walk_step"]
    ends = [e for e in entries if e["kind"] == "bt_action_end"]
    assert len(spots) == 1, (
        f"{tag}: actionId {action_id} carries {len(spots)} `spot` ev(s), expected exactly "
        f"1 - ring for this action: {[(e['seq'], e['kind']) for e in entries]}")
    assert len(steps) == n_steps, (
        f"{tag}: actionId {action_id} carries {len(steps)} `walk_step` ev(s) but the walk "
        f"record says {n_steps} executed step(s)")
    assert len(ends) == 1, (
        f"{tag}: actionId {action_id} carries {len(ends)} `bt_action_end`, expected 1")
    spot_seq = spots[0]["seq"]
    for e in steps:
        assert e["seq"] < spot_seq, (
            f"{tag}: `walk_step` at seq {e['seq']} lands AFTER the `spot` ev at seq "
            f"{spot_seq} - SS2.W2 rule 6 says the spot breaks the walk at its OWN "
            "position, so every executed step must precede it")
    assert spot_seq < ends[0]["seq"], (
        f"{tag}: the `spot` ev at seq {spot_seq} lands at or after this action's "
        f"bt_action_end at seq {ends[0]['seq']} - the halt must be in-stream BEFORE the "
        "completion restate, not folded into it")
    assert spots[0]["h"], (
        f"{tag}: the `spot` ev at seq {spot_seq} carries NO h:{{unitsStats}} - RB-D14 "
        "puts one on every ev, and an ev that carries no hash is verified against "
        "nothing when the client applies it")
    return spot_seq, [e["seq"] for e in steps], ends[0]["seq"]


def assert_contact(host, client, actor_id, hw, cw, before, baseline):
    """Every acceptance clause of W1-P11, on a walk that has just halted on a
    spot. @a before is the pre-walk snapshot taken by the driver."""
    action_id = hw["actionId"]
    hsteps = hw["steps"]
    n = len(hsteps)

    # --- SS2.W2's per-step contract on BOTH machines, halted -----------------
    # (step evs stand, stepIndex 0..n-1, strictly increasing seq, host == client
    #  step for step, restate path == the executed prefix, final == last step)
    W.assert_step_stream(hw, cw, "PHASE 1", expect_len=n, expect_halted=True)

    # --- the reason, on both machines ---------------------------------------
    for tag, w in (("host", hw), ("client", cw)):
        r = w["restate"]
        assert r["reason"] in HALT_REASONS, (
            f"PHASE 1: the {tag}'s halt reason {r['reason']!r} is not one of SS2.W2's "
            f"frozen enum values {HALT_REASONS}")
        assert r["reason"] == "spot", (
            f"PHASE 1: the {tag}'s halt reason is {r['reason']!r}, expected 'spot'. "
            "Both vanilla spot sites leave `_action.result` EMPTY, so W1-P9's catch-all "
            "maps them to 'blocked' - a 'blocked' here means W1-P11's own latch did not "
            "run at this site")
        assert r["halted"] is True, f"PHASE 1: the {tag}'s restate is not marked halted"
    assert hw["plannedLen"] > n, (
        f"PHASE 1: the walk executed {n} of {hw['plannedLen']} planned step(s) - the "
        "contact must break the walk with something LEFT to break, or 'it breaks the "
        "walk exactly at its own position' is unobservable")

    # --- the SAME tile on both machines --------------------------------------
    executed = [W.tpos(s["to"]) for s in hsteps]
    hu, cu = W.assert_unit_parity(host, client, actor_id, "PHASE 1 at the spot halt")
    assert pos_of(hu) == executed[-1], (
        f"PHASE 1: the actor is at {pos_of(hu)} on the host but the last emitted step "
        f"said {executed[-1]} - a halt must not rewind (SS2.W2 rule 5)")
    assert pos_of(cu) == executed[-1], (
        f"PHASE 1: the actor is at {pos_of(cu)} on the CLIENT but the halt tile is "
        f"{executed[-1]} - the two machines did not stop on the same tile")
    assert hu["tu"] > 0, (
        "PHASE 1: the actor halted at 0 TU, which makes its own reaction score 0 and "
        "therefore PHASE 0's gate-1 argument vacuous for this leg (gates 2 and 3 still "
        "hold, but this run can no longer claim the strong form of the pin)")

    # --- SS2.W2 rule 6: the ev's POSITION in the stream, on both machines -----
    h_spot_seq, h_step_seqs, h_end_seq = assert_stream_position(host, "host", action_id, n)
    c_spot_seq, c_step_seqs, c_end_seq = assert_stream_position(client, "client", action_id, n)
    assert (h_spot_seq, h_step_seqs, h_end_seq) == (c_spot_seq, c_step_seqs, c_end_seq), (
        f"PHASE 1: host and client disagree about the seq stream for actionId "
        f"{action_id} - host spot={h_spot_seq} steps={h_step_seqs} end={h_end_seq}, "
        f"client spot={c_spot_seq} steps={c_step_seqs} end={c_end_seq}")

    # --- the ev PAYLOAD, host emit vs client apply ---------------------------
    hs, cs = last_spot(host), last_spot(client)
    assert hs and cs, f"PHASE 1: lastSpot missing (host={hs}, client={cs})"
    for key in ("actionId", "unit", "seen", "haltStep", "seq"):
        assert hs.get(key) == cs.get(key), (
            f"PHASE 1: the host EMITTED and the client APPLIED different `spot` evs - "
            f"field {key!r}: host={hs.get(key)!r} client={cs.get(key)!r}")
    assert hs["unit"] == actor_id, \
        f"PHASE 1: the spot ev names unit {hs['unit']}, expected the actor {actor_id}"
    assert hs["actionId"] == action_id, (
        f"PHASE 1: the spot ev rides actionId {hs['actionId']} but the halted walk is "
        f"{action_id} - it must be part of the walk's own action chain")
    assert hs["seq"] == h_spot_seq, \
        f"PHASE 1: lastSpot.seq {hs['seq']} != the ring's spot seq {h_spot_seq}"
    seen = list(hs["seen"])
    assert seen, (
        "PHASE 1: the `spot` ev carries an EMPTY `seen` list - vanilla halted on "
        "`unitSpotted`, so the actor's spotted-this-turn set MUST have grown, and an "
        "empty additions list means the bookkeeping half of this atom did nothing")
    assert hs["haltStep"] == n, (
        f"PHASE 1: the spot ev reports haltStep {hs['haltStep']} but {n} step(s) were "
        "executed - haltStep names the executed-step count at the halt")

    # --- DELIVERY, not coincidence -------------------------------------------
    he, ce = event_state(host), event_state(client)
    assert he["coopSpotEvsEmitted"] >= 1, \
        f"PHASE 1: the host emitted no `spot` ev at all ({he['coopSpotEvsEmitted']})"
    assert ce["coopSpotEvsApplied"] == he["coopSpotEvsEmitted"], (
        f"PHASE 1: the host emitted {he['coopSpotEvsEmitted']} `spot` ev(s) but the "
        f"client applied {ce['coopSpotEvsApplied']}")
    assert ce["coopSpotEvsEmitted"] == 0, (
        f"PHASE 1: the CLIENT emitted {ce['coopSpotEvsEmitted']} `spot` ev(s) - a thin "
        "client is never an author")

    # --- the APPLY: the client's own model, not the mirror -------------------
    h_set = set(unit_of(host, actor_id)["spottedThisTurn"])
    c_set = set(unit_of(client, actor_id)["spottedThisTurn"])
    assert battle_state(client)["selectedId"] != actor_id, (
        f"PHASE 1: the CLIENT's selection drifted onto the walker {actor_id} during "
        "the contact - see park_client_selection() for why this file keeps it away")
    # CONSISTENCY, not delivery - see the module docstring's "ONE HONEST LIMIT".
    # A5's targeted per-ev calculateFOV(unit) reaches the same answer on the walk
    # path, so this cannot go red on a missing applier; it CAN go red on an
    # applier that writes the WRONG ids, and on a machine whose model and whose
    # wire disagree.
    assert set(seen) <= c_set, (
        f"PHASE 1: the `spot` ev carried {seen} but the CLIENT's actor holds "
        f"{sorted(c_set)} in its spotted-this-turn set - the two disagree "
        "(prd-r3a: 'append ids to the actor's spotted-this-turn set')")
    assert h_set == c_set, (
        f"PHASE 1: the two machines disagree about the actor's spotted-this-turn set - "
        f"host {sorted(h_set)} client {sorted(c_set)}")
    assert before["actor_spotted_host"] == [] and before["actor_spotted_client"] == [], (
        "PHASE 1 NON-VACUITY: the actor already carried a spotted-this-turn set before "
        f"the contact walk (host {before['actor_spotted_host']}, client "
        f"{before['actor_spotted_client']}) - the fixture rule should have rejected it")
    for uid in seen:
        u = units_by_id(battle_state(host)).get(uid)
        assert u is not None, f"PHASE 1: `seen` names unit {uid}, which is not on the map"
        assert u["faction"] != FACTION_PLAYER, (
            f"PHASE 1: `seen` names unit {uid}, a PLAYER unit - vanilla only adds "
            "hostiles to a player unit's spotted-this-turn set")

    # --- the presenter, EXACT TEXT, ordering seat only -----------------------
    assert banner(client) == STR_HALT_SPOT, (
        f"PHASE 1: the ORDERING seat's banner is {banner(client)!r}, expected "
        f"{STR_HALT_SPOT!r}. {STR_HALT_BLOCKED!r} here means the halt reason latched as "
        "`blocked` (W1-P11's own hook did not run); a raw STR_ key means the deployed "
        "bin/x64/Release/common/Language copy is stale (WV-D17)")
    assert banner(host) != STR_HALT_SPOT, (
        "PHASE 1: the OBSERVING machine printed the ordering seat's halt message - "
        "SS2.W2/WV-D53 shows it only on the ordering seat")

    # --- hashes and fog ------------------------------------------------------
    hh, ch = assert_hash_clean(host, client, full=True, what="at the spot halt")
    for bucket in ("unitsCore", "unitsStats"):
        assert hh[bucket] == ch[bucket], \
            f"PHASE 1: `{bucket}` differs at the halt: host={hh[bucket]} client={ch[bucket]}"
    assert_reaction_pin_holds(host, client, baseline, "PHASE 1 at the spot halt")
    alien = min((u for u in living_non_players(battle_state(host))),
                key=lambda u: dist3(pos_of(u), executed[-1]))
    assert_reveal_parity(
        host, client, "after the spot contact",
        extra_positions=[(executed[-1][0] + dx, executed[-1][1] + dy, executed[-1][2])
                         for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
                        + [(alien["x"] + dx, alien["y"] + dy, alien["z"])
                           for dx in (-1, 0, 1) for dy in (-1, 0, 1)])

    print(f"PASS PHASE 1: unit {actor_id} walked {n} of {hw['plannedLen']} planned step(s) "
          f"{before['actor_pos']} -> {executed[-1]} and HALTED ON CONTACT. The `spot` ev "
          f"landed at seq {h_spot_seq}, after step seqs {h_step_seqs} and before the "
          f"bt_action_end at seq {h_end_seq}, carrying seen={seen} haltStep={n} + "
          f"h:{{unitsStats}}. Restate: halted=True reason='spot' path={executed}. Both "
          f"machines stopped on {executed[-1]}, the client applied the spot into its own "
          f"spotted-this-turn set {sorted(c_set)}, the ordering seat shows "
          f"{STR_HALT_SPOT!r}, all {len(hh)} buckets EQUAL, fog parity unchanged, and NO "
          f"reaction shot was possible.")
    return seen


def park_client_selection(host, client, park_id):
    """Move the CLIENT's selection to one of its OWN units that is NOT the
    walker, and keep it there for the whole contact.

    WHAT IT BUYS, stated exactly (the first version of this helper claimed it
    made the apply proof non-vacuous; a control build disproved that, and the
    module docstring's "ONE HONEST LIMIT" carries the measurement):
      * it removes ONE of the two client-side writers of the walker's
        _unitsSpottedThisTurn - SS2.W5's
        updateSoldierInfo(checkFOV) -> calculateFOV(selectedUnit, false, true).
        The OTHER writer, A5's targeted per-ev calculateFOV(unit) in
        CoopDisplayQueue::onApplied, still reaches the same unit, which is why
        the set comparison remains a consistency check;
      * it makes the walk a REMOTE-unit walk from the client's own HUD's point
        of view, which is the more interesting case and the one W1-P12's ghost
        will animate;
      * it proves the halt banner reaches the ORDERING SEAT even when the
        walker is not that seat's selected unit.

    Selection is a machine-local presentation act (SS2.W5: a selection change
    authors no shared fog in a co-op battle) and the client is only ever
    selecting its OWN units (W1-P6), so nothing here is a state mint - the
    all-buckets-EQUAL asserts that follow are what hold that claim."""
    for _ in range(14):
        if battle_state(client).get("selectedId") == park_id:
            print(f"    [selection] client PARKED on unit {park_id} for the whole run; "
                  "every walker below is a unit the client's own HUD is not showing")
            return
        client.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.15)
    raise AssertionError(
        f"could not TAB the CLIENT's selection onto its parking unit {park_id} - "
        f"battle_state says selectedId={battle_state(client).get('selectedId')}")


def attempt_contact(host, client, soldier_ids, baseline, why_log):
    """Walk seat-1 actors toward the nearest living non-player unit until one of
    them takes vanilla's own `unitSpotted` halt, then assert the whole packet
    against it. Returns the accepted contact's (actor_id, hw, seen) or None.

    EVERY assertion inside here runs at FULL STRENGTH whether or not a contact is
    eventually staged - only "this boot never staged one" is a rejection. That is
    the orchestrator's SKIP ruling applied honestly: a product misbehaviour on
    the way to a contact is a hard FAIL, never a re-roll."""
    clean_legs = 0
    zero_step_spots = 0
    candidates = sorted(seat1_units(host, soldier_ids), key=lambda u: -u["tu"])
    assert len(candidates) >= 2,         f"only {len(candidates)} live seat-1 unit(s) - one is reserved as the client's "         "selection parking spot and at least one more is needed to walk"
    # The PARKING unit is chosen ONCE and never walked. Selecting a unit on the
    # CLIENT runs SS2.W5's updateSoldierInfo(checkFOV) ->
    # calculateFOV(selectedUnit, doTileRecalc=false, doUnitRecalc=true), which
    # writes THAT unit's _unitsSpottedThisTurn locally while the HOST's copy of
    # the same unit stays empty (the host never selected it and never recomputed
    # its FOV). That asymmetry is hash-free and architecturally legal - the field
    # is in no bucket and in no serializer - but it means a unit the client has
    # ever had selected is no longer a clean spot fixture. MEASURED: an earlier
    # version TABbed per actor and reds appeared at ~2/4 runs with
    # "host [] client [1000000]" before the contact walk. So: park once, on a
    # unit that is never a walker.
    park_id = candidates[-1]["id"]
    park_client_selection(host, client, park_id)
    for actor in [u for u in candidates if u["id"] != park_id]:
        actor_id = actor["id"]
        if (unit_of(host, actor_id)["spottedThisTurn"]
                or unit_of(client, actor_id)["spottedThisTurn"]):
            continue
        # PHASE 0's gate-1 argument (getSpottingUnits' `bu->getReactionScore() >=
        # threshold`) needs the WALKER's own score strictly positive, and the
        # score is `reactions * TU / maxTU`. Asserted here rather than assumed:
        # gates 2 and 3 would still hold with a zero-score walker, but this run
        # would no longer be able to claim the strong form of the pin.
        for gc, tag in ((host, "host"), (client, "client")):
            u = unit_of(gc, actor_id)
            assert u["reactions"] > 0 and u["tu"] > 0, (
                f"PHASE 0 gate 1: the actor {actor_id} on the {tag} has reactions="
                f"{u['reactions']} tu={u['tu']} - its own reaction score is 0, so a "
                "zeroed alien would tie the getSpottingUnits threshold test")
        assert battle_state(client)["selectedId"] == park_id, (
            f"the CLIENT's selection drifted off its parking unit {park_id} onto "
            f"{battle_state(client)['selectedId']} - see park_client_selection()")
        for leg in range(1, MAX_LEGS + 1):
            st = battle_state(host)
            aliens = living_non_players(st)
            live = unit_of(host, actor_id)
            occupied = {pos_of(u) for u in st["units"] if not u.get("isOut")}
            cands = approach_candidates(host, live, aliens, occupied)
            if not cands:
                why_log.append(f"no approach destination for actor {actor_id} at leg {leg}")
                break

            progressed = False
            for dest in cands[:CANDIDATES_PER_LEG]:
                before = {
                    "actor_pos": pos_of(unit_of(host, actor_id)),
                    "actor_spotted_host": list(unit_of(host, actor_id)["spottedThisTurn"]),
                    "actor_spotted_client": list(unit_of(client, actor_id)["spottedThisTurn"]),
                    "health": unit_of(host, actor_id)["health"],
                    "stun": unit_of(host, actor_id)["stun"],
                }
                spots_before = event_state(host)["coopSpotEvsEmitted"]
                kind, payload = W.send_walk_outcome(host, client, actor_id, dest)
                if kind == "nosend":
                    continue
                if kind == "deny":
                    # A drained actor legitimately gets `cost_changed` (SS2.3's own
                    # mapping). Not a failure of anything - move to the next actor.
                    why_log.append(f"actor {actor_id} denied ({payload.get('reason')}) "
                                   f"at leg {leg}")
                    progressed = True
                    break
                progressed = True
                hw, cw = payload, W.last_walk(client)

                # SAFETY FIRST, every leg, before anything is interpreted.
                assert_reaction_pin_holds(host, client, baseline,
                                          f"after actor {actor_id} leg {leg}")
                after = unit_of(host, actor_id)
                assert (after["health"], after["stun"]) == (before["health"], before["stun"]), (
                    f"actor {actor_id} lost health/stun during a plain walk "
                    f"({before['health']}/{before['stun']} -> {after['health']}/"
                    f"{after['stun']}) - something attacked it")

                r = hw.get("restate") or {}
                reason = r.get("reason") or ""
                halted = bool(r.get("halted"))
                assert reason in ("",) + HALT_REASONS, (
                    f"actor {actor_id} leg {leg}: halt reason {reason!r} is not one of "
                    f"SS2.W2's frozen enum values")
                assert reason != "reaction", (
                    f"actor {actor_id} leg {leg} halted on SS2.W2 reason 'reaction' - "
                    "PHASE 0's pin has failed and this run cannot separate the spot atom "
                    "from S5's expected AI-origin desync class")

                # ===== THE TRIPWIRE, and it is what stops a SKIP from masking a
                # real failure (the orchestrator's own stated risk in the
                # 2026-09-03 SKIP ruling).
                #
                # VANILLA ITSELF is the oracle. BattleUnit::_unitsSpottedThisTurn
                # is written by TileEngine::calculateUnitsInFOV on the HOST
                # whether or not any coop hook exists, and UnitWalkBState's own
                # halt predicate is literally "that set's size changed"
                # (`_numUnitsSpotted != _unit->getUnitsSpottedThisTurn().size()`).
                # So: if the set GREW during this walk, vanilla spotted something,
                # and W1-P11 is REQUIRED to have reported it as `spot` + emitted
                # one ev. Anything else is the atom silently not firing.
                #
                # MEASURED, NOT REASONED: with both coopNoteWalkSpot() call sites
                # commented out and the exe rebuilt, this file previously walked
                # every actor of every boot to exhaustion and exited SKIP(3) -
                # a missing atom classified as "the map generator offered
                # nothing". With this tripwire the same build FAILS(2) on the
                # first leg that spots.
                grew = (set(unit_of(host, actor_id)["spottedThisTurn"])
                        - set(before["actor_spotted_host"]))
                if grew:
                    assert halted and reason == "spot", (
                        f"actor {actor_id} leg {leg}: vanilla ADDED {sorted(grew)} to the "
                        f"actor's spotted-this-turn set during this walk - which is "
                        "UnitWalkBState's own halt predicate - but the completion restate "
                        f"says halted={halted} reason={reason!r}. W1-P11's coopNoteWalkSpot "
                        "hook did not run at the site vanilla actually took. (The one "
                        "other way to reach this: vanilla suppresses the halt while "
                        "`_falling`, which this fixture's routes are not supposed to "
                        "produce - either way it is a red, not a re-roll.)")
                    assert event_state(host)["coopSpotEvsEmitted"] > spots_before, (
                        f"actor {actor_id} leg {leg}: the restate reports reason='spot' but "
                        f"the host emitted no `spot` ev (counter still {spots_before}) - "
                        "the halt reason and the ev must always travel together")

                if halted and reason == "spot":
                    n = len(hw.get("steps") or [])
                    if n == 0:
                        # A spot during the PRE-FIRST-STEP facing turn. A legal and
                        # correct outcome of the atom, but "the step evs before the
                        # halt STAND" is vacuous with no step evs, so this boot cannot
                        # carry the packet's acceptance. Recorded with its numbers.
                        zero_step_spots += 1
                        why_log.append(f"actor {actor_id} spotted during its "
                                       f"pre-first-step turn (0 executed steps)")
                        break
                    if hw["plannedLen"] <= n:
                        why_log.append(f"actor {actor_id} spotted on the LAST planned "
                                       f"step ({n}/{hw['plannedLen']}) - nothing left to "
                                       "break")
                        break
                    seen = assert_contact(host, client, actor_id, hw, cw, before, baseline)
                    print(f"[repro_atom_spot] staged after {clean_legs} clean leg(s) and "
                          f"{zero_step_spots} zero-step spot(s)")
                    return actor_id, hw, seen

                if halted and reason in ("no_tu", "no_energy"):
                    why_log.append(f"actor {actor_id} ran out of {reason} at leg {leg}")
                    break
                if halted:
                    # `blocked` - the pathfinder walked into something. Try the next
                    # candidate at this radius.
                    continue
                clean_legs += 1
                break                                   # leg done, walk the next one
            if not progressed:
                why_log.append(f"actor {actor_id} could not order any walk at leg {leg}")
                break
            if unit_of(host, actor_id)["spottedThisTurn"]:
                break                                   # this actor's contact is spent
    why_log.append(f"no stageable contact: {clean_legs} clean leg(s), "
                   f"{zero_step_spots} zero-step spot(s)")
    return None


# ----- PHASE 2: the control ------------------------------------------------

def phase2_control(host, client, actor_id, first_seen, baseline):
    """One more walk for the same actor. Either it does NOT halt on a spot and
    emits NO second `spot` ev - which proves the halt is not latched and that
    `seen` is the ADDITIONS since the chain opened rather than the whole set -
    or it spots something NEW, in which case its `seen` must be DISJOINT from the
    first one's, which proves the same thing more strongly."""
    emitted_before = event_state(host)["coopSpotEvsEmitted"]
    st = battle_state(host)
    aliens = living_non_players(st)
    live = unit_of(host, actor_id)
    occupied = {pos_of(u) for u in st["units"] if not u.get("isOut")}
    cands = approach_candidates(host, live, aliens, occupied, radii=(1, 2))
    assert cands, ("PHASE 2: no destination left for the control walk - the actor is "
                   "boxed in against the approach floor. FIXTURE failure.")

    outcome = None
    for dest in cands[:CANDIDATES_PER_LEG]:
        kind, payload = W.send_walk_outcome(host, client, actor_id, dest)
        if kind == "walk":
            outcome = payload
            break
        if kind == "deny":
            outcome = ("deny", payload)
            break
    assert outcome is not None, "PHASE 2: no control walk could be ordered at all"
    assert_reaction_pin_holds(host, client, baseline, "after the PHASE 2 control walk")

    emitted_after = event_state(host)["coopSpotEvsEmitted"]
    if isinstance(outcome, tuple):
        # A deny (a drained actor). The control still holds in its weak form: no
        # second spot ev was emitted for a walk that never ran.
        assert emitted_after == emitted_before, (
            f"PHASE 2: a DENIED walk emitted {emitted_after - emitted_before} `spot` "
            "ev(s)")
        print(f"PASS PHASE 2 (weak form): the control walk was denied "
              f"({outcome[1].get('reason')!r}) and emitted no `spot` ev")
        return

    hw = outcome
    r = hw["restate"]
    if emitted_after == emitted_before:
        assert not (r["halted"] and r["reason"] == "spot"), (
            "PHASE 2: the restate says the walk halted on 'spot' but no `spot` ev was "
            "emitted - the reason and the ev must always travel together")
        h_set = set(unit_of(host, actor_id)["spottedThisTurn"])
        c_set = set(unit_of(client, actor_id)["spottedThisTurn"])
        assert h_set == c_set, (
            f"PHASE 2: the spotted-this-turn sets drifted apart after the control walk - "
            f"host {sorted(h_set)} client {sorted(c_set)}")
        assert set(first_seen) <= h_set, (
            f"PHASE 2: the first contact's ids {first_seen} are no longer in the actor's "
            f"spotted-this-turn set {sorted(h_set)} - the atom is not additive")
        assert_hash_clean(host, client, full=True, what="after the PHASE 2 control walk")
        print(f"PASS PHASE 2: the actor walked {len(hw['steps'])} more step(s) toward the "
              f"SAME unit(s) {first_seen} and emitted NO second `spot` ev "
              f"(halted={r['halted']} reason={r['reason']!r}) - the halt is not latched "
              f"and `seen` carries ADDITIONS, not the whole set")
        return

    # A genuinely NEW contact. The stronger branch.
    assert r["halted"] and r["reason"] == "spot", (
        f"PHASE 2: a second `spot` ev was emitted but the restate says halted="
        f"{r['halted']} reason={r['reason']!r}")
    second = list(last_spot(host)["seen"])
    assert second, "PHASE 2: the second `spot` ev carries an empty `seen`"
    assert not (set(second) & set(first_seen)), (
        f"PHASE 2: the second `spot` ev re-ships {sorted(set(second) & set(first_seen))}, "
        "which the first one already carried - `seen` must be the ADDITIONS since the "
        "chain opened, never the whole spotted-this-turn set")
    assert_hash_clean(host, client, full=True, what="after the PHASE 2 second contact")
    print(f"PASS PHASE 2 (strong form): a SECOND contact spotted {second}, DISJOINT from "
          f"the first {first_seen} - `seen` is the additions, not the set")


# ----- bring-up ------------------------------------------------------------

def bring_up_staged_contact():
    why_log = []
    for attempt in range(1, MAX_REROLLS + 1):
        port = str(48660 + attempt)
        host = GameClient("host", 49620 + attempt * 2,
                          make_user_dir(f"repro_atom_spot_host_{attempt}"))
        client = GameClient("client", 49621 + attempt * 2,
                            make_user_dir(f"repro_atom_spot_client_{attempt}"))
        seated = {}
        try:
            W.bring_up_lobby(host, client, port)
            drive_to_battlescape(host, client, seated)

            why = fixture_rejection(host, client, seated["soldierIds"])
            if why is not None:
                why_log.append(why)
                print(f"[repro_atom_spot] re-roll {attempt}/{MAX_REROLLS}: {why}")
                host.shutdown()
                client.shutdown()
                continue

            baseline = phase0_pin_reaction_fire(host, client)
            staged = attempt_contact(host, client, seated["soldierIds"], baseline, why_log)
            if staged is not None:
                print(f"[repro_atom_spot] contact staged on attempt {attempt}/"
                      f"{MAX_REROLLS} ({attempt - 1} re-roll(s))")
                return host, client, staged, baseline
            print(f"[repro_atom_spot] re-roll {attempt}/{MAX_REROLLS}: {why_log[-1]}")
            host.shutdown()
            client.shutdown()
        except Exception:
            host.shutdown()
            client.shutdown()
            raise

    tally = {}
    for w in why_log:
        key = w.split(":")[0].split("(")[0].strip()
        tally[key] = tally.get(key, 0) + 1
    lines = [f"no stageable contact in {MAX_REROLLS} boots - the map generator never "
             "offered an alien this squad could walk into view of without being shot "
             "at, which is not a statement about the spot atom",
             "      rejection histogram:"]
    for k, v in sorted(tally.items(), key=lambda kv: -kv[1]):
        lines.append(f"      {v:4d}  {k}")
    lines.append(f"      last: {why_log[-1] if why_log else None}")
    raise FixtureExhausted("\n".join(lines))


def main():
    t0 = time.time()
    host, client, staged, baseline = bring_up_staged_contact()
    actor_id, hw, seen = staged
    try:
        phase2_control(host, client, actor_id, seen, baseline)
    finally:
        host.shutdown()
        client.shutdown()
    print(f"\nrepro_atom_spot: PASS ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    try:
        main()
    except FixtureExhausted as e:
        # NOT a failure: no boot ever staged a contact, so PHASE 1 never ran.
        # Distinct status and exit code so a gate can count it separately and
        # report the exhaustion rate (the orchestrator's 2026-09-03 ruling).
        print(f"\nrepro_atom_spot: SKIP (fixture exhausted)\n{e}")
        sys.exit(EXIT_SKIP)
    except (AssertionError, TimeoutError) as e:
        # TimeoutError too: a bare `wait_for` timeout is a FAILED RUN and must be
        # reported as one (exit 2, with the message), not as an exit-1 traceback
        # that reads like a crash.
        print(f"\nrepro_atom_spot: FAIL\n{type(e).__name__}: {e}")
        #
        # The TRACEBACK is printed as well, and that is not cosmetic: this
        # file's asserts fall into three classes with very different
        # consequences (a hole in the atom, a wire/field defect, a fixture
        # premise), and the FILE:LINE is what separates them in one read. A
        # red that has to be REPRODUCED before it can be classified costs a
        # cycle, and this wave has already paid that twice. Purely additive:
        # no assertion, no control flow and no exit code depends on it.
        print("")
        print("--- traceback (classification aid) ---")
        traceback.print_exc()
        sys.exit(EXIT_FAIL)
