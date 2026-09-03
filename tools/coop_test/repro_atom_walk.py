"""W1-P9 (rewrite wave 1, WAVE1-RUNBOOK.md SS4 "ATOM walk-core"): the walk atom
end to end - SS2.W2's intent + host validator + PER-STEP events + completion
restate + client applier + the WV-D33 HUD refresh.

WHAT SS2.W2 (rulings D4 + D-6 = WV-D29/WV-D30/WV-D37/WV-D38/WV-D48) ACTUALLY
REQUIRES, and where each requirement is asserted below:

  PHASE 1  OPEN-GROUND A->B. One `bt_ev walk_step` per EXECUTED step, strictly
           increasing `stepIndex`, every one carrying `h:{unitsStats}`, and
           `assert_hash_clean` after EVERY step - which is the point of the
           per-step hash (SS2.W2 rule 3: "a desync is localized to the exact
           TILE it happened on, not to the whole walk"). The completion
           `bt_action_end` carries the FULL EXECUTED `path` and its `final`
           matches the last step's post-state. Battle-phase wall clock < 5 s.
  PHASE 2  WV-D33's CLIENT HUD REFRESH, asserted on the PAINTED NumberText
           values, not on the model: before this packet nothing on a thin
           client repainted the map strip from the apply path, so "the model
           changed" would have passed even with the bug present.
  PHASE 3  `battle_halt_walk` mid-walk: the already-emitted step evs STAND
           (SS2.W2 rule 5 - no retraction, no rewind), the restate carries the
           EXECUTED PREFIX plus `halted:true` and a SS2.W2 halt `reason`, and
           the ORDERING SEAT sees the halt banner with EXACT text.
  PHASE 4  the two deny paths, each observed once: `path_changed` (a plan
           through an OCCUPIED tile, shipped via `battle_intent`'s `path`
           override) and `cost_changed` (`tuBasisOverride`).
  PHASE 5  WV-D48 + WV-D38, THE RESERVE, both halves:
             (control) the reserve setting under test really BITES at this
                       actor's TU - proven on the CLIENT, same unit, same TU,
                       same predicate, so the host half below cannot pass
                       vacuously;
             (a)       a first-step violation sends NO intent at all and shows
                       the LOCAL VANILLA refusal, asserted as EXACT TEXT;
             (b)       a violation at step k>1 ships exactly the k-1 prefix and
                       is ADMITTED - twice, under two DIFFERENT HOST reserve
                       settings, with an identical result, which is WV-D14's
                       per-machine-reserve proof and WV-D38's "the host does not
                       apply ITS reserve to a client-origin walk".
  PHASE 6  WR-6's safe-list rename (`walk_steps` -> `walk_step`): with
           `coopCancelOnAnyPartnerAction` ON, a partner walk does NOT cancel a
           held pending intent. Without the rename EVERY walk step would.
  PHASE 7  BURST: walk + turn + kneel interleaved across BOTH origins, strictly
           increasing seq, queueDepth 0 at the end.
  PHASE 8  `hash_now full` ALL buckets EQUAL after >= 10 mixed actions including
           walks, plus `reveal_state` per-part parity unchanged (the client
           never authored fog - SS2.4a's client-authority rule).

FIXTURE (WV-D18, and PINNED not assumed - the standing rule of this wave):
walk-core's fixtures are DOOR-FREE and CONTACT-FREE BY CONSTRUCTION, because
doors are W1-P10 and spot halts are W1-P11 (WV-D26). This file therefore
strengthens repro_atom_turn.py's own selection rule in three ways, all of them
PINS (a fixture that fails one is RE-ROLLED; nothing asserted is relaxed):

  (b') NO DOOR within WALK_DOOR_RADIUS - larger than the turn repro's 2, because
       a WALK moves the actor and vanilla auto-opens a door it steps up to
       (UnitWalkBState.cpp's `unitOpensDoor` block), which is W1-P10's atom and
       would arrive here as an unapplied terrain change.
  (c') CONTACT-FREE WITH A MARGIN: session.MAX_VIEW_DISTANCE plus the total
       displacement this test can produce. session.actor_is_contact_free()'s own
       cap is exactly right for a ROTATION, which cannot move the actor; a walk
       can, so the same cap alone would let an actor walk INTO view distance and
       take vanilla's `unitSpotted` halt - a `spot` reason walk-core does not
       own (W1-P11 does).
  (e') THE ACTOR CARRIES A WEAPON. PHASE 5's whole subject is a TU RESERVE, and
       BattlescapeGame::checkReservedTU reserves against
       `bu->getMainHandWeapon(false)` - with no weapon the reserve cost computes
       to 0 and the predicate returns true unconditionally, i.e. the phase would
       assert a rule that was never in force.

TWO TEST-ONLY LEVERS SHIP WITH THIS PACKET (WR-11, RB-D26 discipline - minimal,
deterministic, test-only, neither changes the wire):
  * walk parameters on `battle_intent` (RB-D32's "one function, two callers -
    extend the signature, never fork it"), including the optional explicit
    `path` override PHASE 4 needs to ship a deliberately-blocked plan; and
  * `battle_halt_walk {}`, a host one-shot consumed at the next step boundary.
`battle_reserve {mode,kneel}` rides along for PHASE 5, which cannot be driven at
all without setting each machine's own (machine-local, saveBlob-EXCLUDED)
reserve.

WHY THE ASSERTIONS HERE ARE NOT VACUOUS - the checks that would go RED:
  * PHASE 1's per-step hash compare is EXACT on nine buckets after every single
    step. The applier reproduces the host's step through vanilla's own
    startWalking/keepWalking precisely because a hand-written one would miss
    `motionPoints` (inside the HASHED unitsStats bucket) and red on step one.
  * PHASE 2 reads the PAINTED NumberText values. Deleting the WV-D33 call makes
    them stale and the assert fails; asserting the model instead would not.
  * PHASE 3 asserts the step evs emitted BEFORE the halt still stand AND that
    the restate's path is exactly that prefix - a "rewind" implementation fails
    both halves.
  * PHASE 5's control proves the reserve really bites on this unit at this TU
    before the host half is asserted, so "the host did not truncate" cannot pass
    because nothing would have truncated anyway.
  * PHASE 6 asserts the pending intent SURVIVES; with the stale `walk_steps`
    literal it is cancelled by the first step ev, which is the exact regression
    WR-6 names.

Run:  python tools/coop_test/repro_atom_walk.py
      (in its OWN shell invocation - the standing harness rule, one harness run
       at a time, machine-wide.)
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import assert_hash_clean, assert_reveal_parity

COOP_SEAT_0 = 0
COOP_SEAT_1 = 1
FACTION_PLAYER = 0

MAX_REROLLS = 15
# TU HEADROOM. A soldier has ~55 TU and a tile costs 4-8, so ONE actor cannot
# carry every phase - and an actor that runs dry produces a FIXTURE failure that
# looks exactly like a broken atom ("no walk could be ordered"). Each phase that
# spends TU therefore gets its own actor. Five leaves the host two soldiers of
# the default skirmish squad, which is what PHASE 6b's host-origin walk needs.
SEAT1_SOLDIERS = 5

# (b') see the module docstring. A walk of up to WALK_RUN tiles plus vanilla's
# own one-tile door lookahead.
WALK_RUN = 3
WALK_DOOR_RADIUS = WALK_RUN + 2

# (c') the contact margin at QUALIFICATION time. session.MAX_VIEW_DISTANCE is
# the right cap for a ROTATION, which cannot move the actor; a walk can, so this
# asks for elbow room on top of it. A LARGE static margin was tried first and
# rejected EVERY generation this map produces (observed nearest-alien distances
# 10.0 .. 32.6 over 15 boots), which would have been a fixture that never runs
# rather than a fixture that is pinned - so the real pin moved to where it
# belongs: every candidate WALK is filtered per TILE by run_is_contact_free()
# below, so no walk this test issues can bring the actor inside view distance at
# any point along the path. The margin here only guarantees room to manoeuvre.
WALK_CONTACT_MARGIN = 4

SDLK_HOME = 278  # Options::keyBattleCenterUnit default
SDLK_TAB = 9     # Options::keyBattleNextUnit default

DIR_DX = [0, 1, 1, 1, 0, -1, -1, -1]
DIR_DY = [-1, -1, 0, 1, 1, 1, 0, -1]

# EXACT text, from bin/common/Language/en-US.yml and bin/standard/xcom1/
# Language/en-US.yml. Asserted as TEXT and never as an STR_ key: Language::
# getString() returns the KEY when the key is missing, so a key-shaped assert
# passes silently against a stale deploy copy (WV-D17).
STR_HALT_BLOCKED = "Move stopped - path blocked"
STR_DENY_PATH_CHANGED = "Order cancelled - path blocked"
STR_DENY_COST_CHANGED = "Order cancelled - cost changed"
STR_RESERVE_SNAP = "Time Units reserved for Snap Shot"
STR_RESERVE_AIMED = "Time Units reserved for Aimed Shot"

HOST_PLAYER = "HostPlayer"
CLIENT_PLAYER = "ClientPlayer"


# ----- small probes -------------------------------------------------------

def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


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


def warning_text(gc):
    return battle_state(gc).get("warningText", "")


def last_walk(gc):
    return event_state(gc).get("lastWalk") or {}


def pos_of(u):
    return (u["x"], u["y"], u["z"])


def jpos(p):
    return {"x": p[0], "y": p[1], "z": p[2]}


def tpos(j):
    return (j["x"], j["y"], j["z"])


def set_reserve(gc, mode=None, kneel=None):
    req = {"cmd": "battle_reserve"}
    if mode is not None:
        req["mode"] = mode
    if kneel is not None:
        req["kneel"] = kneel
    return gc.ok(req)


# ----- fixture bring-up (inline copy, test_rw_feedback.py precedent) -------

def skirmish_host(host, port, player=HOST_PLAYER):
    host.ok({"cmd": "open_new_battle"})
    host.wait_for("host new battle", lambda: session.has_state(host, "NewBattleState"))
    host.ok({"cmd": "newbattle_coop"})
    host.wait_for("host browser", lambda: session.has_state(host, "ServerList"))
    host.ok({"cmd": "server_list_host"})
    host.wait_for("host window", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv",
             "port": port, "player": player})
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"))


def skirmish_client_at_browser(client):
    client.ok({"cmd": "open_new_battle"})
    client.wait_for("client new battle", lambda: session.has_state(client, "NewBattleState"))
    client.ok({"cmd": "newbattle_coop"})
    client.wait_for("client browser", lambda: session.has_state(client, "ServerList"))


def bring_up_lobby(host, client, port):
    host.spawn(); host.connect()
    client.spawn(); client.connect()

    skirmish_host(host, port)
    skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": CLIENT_PLAYER})

    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: lobby(host).get("buttonVisible") or None)


def drive_to_battlescape(host, client, seated_holder, seat_count=SEAT1_SOLDIERS):
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={states(host)}"

    soldier_ids = []
    for i in range(seat_count):
        r = host.cmd({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1, "index": i})
        if not r.get("ok"):
            break   # the craft simply has fewer soldiers than that
        soldier_ids.append(r["soldierId"])
    assert len(soldier_ids) >= 4, \
        f"newbattle_seat_soldier stamped only {len(soldier_ids)} soldier(s) to seat 1 - " \
        "this repro needs at least four client-owned actors for TU headroom (see " \
        "SEAT1_SOLDIERS)"
    seated_holder["soldierIds"] = soldier_ids
    seated_holder["soldierId"] = soldier_ids[0]

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


def has_door_within(gc, x, y, z, radius):
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            ti = gc.cmd({"cmd": "tile_info", "x": x + dx, "y": y + dy, "z": z})
            if not ti.get("ok"):
                continue
            for part in ti.get("parts", {}).values():
                if part.get("isDoor") or part.get("isUfoDoor"):
                    return True
    return False


def tile_is_open_ground(gc, x, y, z, occupied):
    """A cheap, CONSERVATIVE walkability screen for a candidate step tile: it
    exists, it has a FLOOR, it carries no door part, and no unit is standing on
    it. The pathfinder remains the real judge - a candidate that survives this
    and still yields no route is simply skipped by the caller."""
    if (x, y, z) in occupied:
        return False
    ti = gc.cmd({"cmd": "tile_info", "x": x, "y": y, "z": z})
    if not ti.get("ok"):
        return False
    parts = ti.get("parts", {})
    if parts.get("floor", {}).get("mapDataID", -1) < 0:
        return False
    for part in parts.values():
        if part.get("isDoor") or part.get("isUfoDoor"):
            return False
    return True


def living_non_players(battle_state_resp):
    return [(u["x"], u["y"], u["z"]) for u in battle_state_resp.get("units", [])
            if u.get("faction") != FACTION_PLAYER and not u.get("isOut")]


def min_dist_to(aliens, tile):
    """Straight-line 3D tile distance from @a tile to the nearest of @a aliens,
    or None when there are none. Same metric session.nearest_non_player_distance
    uses, applied to a TILE instead of a unit."""
    best = None
    for a in aliens:
        d2 = (a[0] - tile[0]) ** 2 + (a[1] - tile[1]) ** 2 + (a[2] - tile[2]) ** 2
        if best is None or d2 < best:
            best = d2
    return None if best is None else best ** 0.5


def region_is_contact_free(aliens, actor, dest, pad=1):
    """WV-D18's contact-free premise, applied to a candidate WALK rather than to
    the actor's starting tile: EVERY tile the walk could occupy must stay
    strictly outside session.MAX_VIEW_DISTANCE of every living non-player unit.

    The region checked is the bounding box of (actor, dest) PADDED by @a pad,
    which is a conservative superset of any route Pathfinding can produce for a
    walk of this length - the whole point being that the check must not depend
    on guessing the route. Aliens do not move for the whole of this test (wave 1
    has no side transition, so the player side never ends), which is what makes
    a static per-tile check SOUND rather than merely likely.

    This is THE pin - see WALK_CONTACT_MARGIN's own comment for why the pin had
    to move here from a static qualification margin."""
    x0, x1 = sorted((actor["x"], dest[0]))
    y0, y1 = sorted((actor["y"], dest[1]))
    for x in range(x0 - pad, x1 + pad + 1):
        for y in range(y0 - pad, y1 + pad + 1):
            d = min_dist_to(aliens, (x, y, dest[2]))
            if d is not None and d <= session.MAX_VIEW_DISTANCE:
                return False
    return True


def straight_runs(host, actor, occupied, length=WALK_RUN, st=None, want=10):
    """Candidate walk DESTINATIONS exactly @a length tiles away (Chebyshev) that
    are open ground and whose whole neighbourhood is contact-free. Returns a
    list of (dir_or_None, [dest]) so every call site keeps the shape it already
    used - `entry[1][-1]` is the destination and `len(entry[1])` is meaningless
    for planning, which is why nothing asserts a predicted path any more.

    WHY DESTINATIONS AND NOT A STRAIGHT OPEN RUN. The first version demanded N
    COLLINEAR open tiles and was rejected by EVERY generation this map produces
    (15/15 boots, "no 3-tile open-ground run in any direction"): at t=0 the
    squad is packed inside the Skyranger, so an actor's neighbours are other
    soldiers and its straight lines run into the hull. Pathfinding routes around
    both. Nothing this test asserts needed the straight line - the executed path
    is compared against the HOST's own record and its own `plannedLen`, never
    against a path the harness predicted - so the requirement was the fixture
    being over-specified, not the atom being unobservable.

    ORDERED so the destination FURTHEST from the nearest alien comes first:
    walking away from contact keeps the later phases' own open ground available
    and is the conservative direction for the pin above."""
    if st is None:
        st = battle_state(host)
    aliens = living_non_players(st)
    ring = []
    # BOTH the actor's own level AND the one below it. The squad starts INSIDE
    # the Skyranger, whose deck sits a level ABOVE the terrain: every tile
    # outside the hull at the actor's own z is AIR (floor mapDataID -1) and every
    # tile inside it is another soldier, so a same-level-only search returns
    # nothing at all and the first walk cannot be ordered (observed). The ground
    # the squad actually walks on is z-1, down the ramp, and Pathfinding handles
    # the drop itself.
    for dz in (0, -1, 1):
        z = actor["z"] + dz
        if z < 0:
            continue
        for dx in range(-length, length + 1):
            for dy in range(-length, length + 1):
                if max(abs(dx), abs(dy)) != length:
                    continue
                t = (actor["x"] + dx, actor["y"] + dy, z)
                if not region_is_contact_free(aliens, actor, t):
                    continue
                d = min_dist_to(aliens, t)
                # same level first, then down, then up - a same-level walk is the
                # simplest thing to reason about and the others are the fallback.
                ring.append((abs(dz), -(d if d is not None else 1e9), t))
    ring.sort(key=lambda e: (e[0], e[1]))

    out = []
    for _, _, t in ring:
        if tile_is_open_ground(host, t[0], t[1], t[2], occupied):
            out.append((None, [t]))
            if len(out) >= want:
                break
    return out


def qualifying_actor(host, soldier_id):
    """WV-D18's walk-core fixture rule, PINNED - see the module docstring for
    why (b') and (c') are stronger than repro_atom_turn.py's and why (e') is
    here at all. Returns the unit dict, or None to re-roll."""
    st = battle_state(host)
    if not st.get("ok") or not st.get("inBattle"):
        return None
    if st.get("spotted"):
        return None                                   # (a) nothing spotted yet
    units = units_by_id(st)
    occupied = {pos_of(u) for u in units.values() if not u.get("isOut")}
    for u in units.values():
        if u.get("soldierId") != soldier_id:
            continue
        if has_door_within(host, u["x"], u["y"], u["z"], WALK_DOOR_RADIUS):
            print(f"[repro_atom_walk] rule (b'): a door within {WALK_DOOR_RADIUS} tiles "
                  "of the actor - a walk would auto-open it (W1-P10's atom)")
            return None
        d = session.nearest_non_player_distance(st, u)
        cap = session.MAX_VIEW_DISTANCE + WALK_CONTACT_MARGIN
        if d is not None and d <= cap:
            print(f"[repro_atom_walk] rule (c'): nearest non-player unit is {d:.2f} "
                  f"tiles away (walk cap {cap}) - this actor could walk INTO view "
                  "distance and take vanilla's spot halt (W1-P11's atom)")
            return None
        print(f"[repro_atom_walk] rule (c') ok: nearest non-player unit is "
              f"{'none at all' if d is None else '%.2f tiles' % d} away (walk cap {cap})")
        if not u.get("weapon"):
            print("[repro_atom_walk] rule (e'): the actor carries no weapon, so a TU "
                  "reserve computes to 0 and PHASE 5 would assert a rule that is not "
                  "in force")
            return None
        runs = straight_runs(host, u, occupied, st=st)
        if not runs:
            print(f"[repro_atom_walk] rule (f'): no open-ground, contact-free "
                  f"destination {WALK_RUN} tiles from the actor - there is nothing "
                  "to walk")
            return None
        print(f"[repro_atom_walk] rule (f') ok: {len(runs)} contact-free destination(s) "
              f"{WALK_RUN} tiles out: {[r[1][0] for r in runs]}")
        return u
    return None


def bring_up_qualifying_battle():
    for attempt in range(1, MAX_REROLLS + 1):
        port = str(48436 + attempt)
        host_dir = make_user_dir(f"repro_atom_walk_host_{attempt}")
        client_dir = make_user_dir(f"repro_atom_walk_client_{attempt}")
        host = GameClient("host", 49380 + attempt * 2, host_dir)
        client = GameClient("client", 49381 + attempt * 2, client_dir)
        seated = {}
        try:
            bring_up_lobby(host, client, port)
            drive_to_battlescape(host, client, seated)
            actor = qualifying_actor(host, seated["soldierId"])
            if actor is not None:
                print(f"[repro_atom_walk] fixture qualifies on attempt "
                      f"{attempt}/{MAX_REROLLS} (actor unit id={actor['id']}, "
                      f"soldierId={seated['soldierId']}, pos={pos_of(actor)}, "
                      f"seat-1 soldiers={seated['soldierIds']})")
                return host, client, actor, seated["soldierIds"]
            print(f"[repro_atom_walk] re-roll {attempt}/{MAX_REROLLS}")
            host.shutdown()
            client.shutdown()
        except Exception:
            host.shutdown()
            client.shutdown()
            raise
    raise RuntimeError(f"repro_atom_walk: no qualifying fixture found in {MAX_REROLLS} boots")


# ----- walk driving -------------------------------------------------------

def settle_reveal(host, client, timeout=40):
    """The host has NOTHING unpublished and the client has caught up. Same
    helper (and the same reason) as repro_atom_turn.py's: SS2.4a's quiescent
    flush can publish a standalone `ev reveal` a tick or two after an action
    settles, and a measurement started before it would see the previous
    action's leftovers."""
    def quiet():
        hs = event_state(host)
        cs = event_state(client)
        rs = host.cmd({"cmd": "reveal_state"})
        return bool(hs.get("ok") and cs.get("ok") and rs.get("ok")
                    and rs.get("unpublished") is False
                    and cs.get("lastSeqApplied", 0) == hs.get("lastSeqEmitted", 0)
                    and cs.get("queueDepth") == 0)
    client.wait_for("host has nothing unpublished and the client is caught up",
                    quiet, timeout=timeout)


def walk_action_id(gc):
    return (last_walk(gc) or {}).get("actionId", 0)


def wait_walk_settled(host, client, prev_action_id, timeout=30):
    """The host finished a NEW walk chain (its restate is out and the chain is
    no longer active) AND the client has applied everything up to it.

    @a prev_action_id is load-bearing: `lastWalk` KEEPS the previous walk's
    finished record, so a predicate that only asked "is a walk finished?" would
    be satisfied instantly by the walk BEFORE this one and every assertion after
    it would read stale data."""
    def done():
        hs = event_state(host)
        cs = event_state(client)
        hw = hs.get("lastWalk") or {}
        return bool(hs.get("ok") and cs.get("ok")
                    and hw and hw.get("actionId", 0) != prev_action_id
                    and hw.get("active") is False and hw.get("restate")
                    and cs.get("lastSeqApplied", 0) == hs.get("lastSeqEmitted", 0)
                    and cs.get("queueDepth") == 0 and hs.get("queueDepth") == 0)
    client.wait_for("walk settled (a NEW host restate emitted, client caught up)",
                    done, timeout=timeout)


def send_walk(client, actor_id, dest, path=None, tu_basis=None, run=False,
              strafe=False, sneak=False):
    req = {"cmd": "battle_intent", "kind": "walk", "actor": actor_id,
           "dest": jpos(dest), "run": run, "strafe": strafe, "sneak": sneak}
    if path is not None:
        req["path"] = [jpos(p) for p in path]
    if tu_basis is not None:
        req["tuBasisOverride"] = tu_basis
    return client.cmd(req)


def walk_candidates(host, actor_id, lengths=(1, 2, 3)):
    """Contact-free, open-ground destinations across several radii, nearest
    radius first. Flat list of tiles."""
    actor = unit_of(host, actor_id)
    st = battle_state(host)
    occ = {pos_of(u) for u in st["units"] if not u.get("isOut")}
    out = []
    for radius in lengths:
        for _, dest in straight_runs(host, actor, occ, length=radius, st=st):
            out.append(dest[0])
    return out


def send_walk_outcome(host, client, actor_id, dest, timeout=20, **kw):
    """Send ONE walk intent and report what actually happened to it:

      ("nosend", resp)   nothing left this machine (no route, or WV-D48's own
                         first-step reserve refusal);
      ("deny", lastDeny) the host answered bt_deny - which a drained actor
                         legitimately gets (`cost_changed`: the first step is no
                         longer affordable, SS2.3's own mapping);
      ("walk", hostWalk) the walk ran to its completion restate.

    The distinction is load-bearing for PHASE 5, whose loops walk an actor DOWN
    to find the narrow TU window in which a reserve refuses. A denied intent
    opens no walk chain at all, so waiting for one hangs - which is exactly how
    this file first failed (a `cost_changed` deny on a drained actor, silently
    waited on for 30 s)."""
    prev = walk_action_id(host)
    resp = send_walk(client, actor_id, dest, **kw)
    if not resp.get("iseq"):
        return ("nosend", resp)
    iseq = resp["iseq"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        hw = last_walk(host)
        if (hw.get("actionId", 0) != prev and hw.get("active") is False
                and hw.get("restate")):
            settle_reveal(host, client)
            return ("walk", last_walk(host))
        ld = event_state(client).get("lastDeny")
        if ld and ld.get("iseq") == iseq:
            return ("deny", ld)
        time.sleep(0.05)
    raise TimeoutError(f"walk intent iseq {iseq} for actor {actor_id} was neither "
                       f"executed nor denied within {timeout}s")


def richest(host, ids, n=1, exclude=()):
    """The @a n client-owned units with the most TU left, excluding @a exclude.

    Actors are allocated by TU rather than by index because every phase that
    WALKS spends TU and an actor that runs dry fails exactly like a broken atom
    would ("no walk could be ordered"). Choosing dynamically keeps that fixture
    failure mode away from the assertions."""
    st = battle_state(host)
    us = [u for u in st["units"] if u["id"] in ids and not u.get("isOut")
          and u["id"] not in exclude]
    us.sort(key=lambda u: -u["tu"])
    return [u["id"] for u in us[:n]]


def pick_and_walk(host, client, actor_id, what, lengths=(1, 2, 3), min_steps=1,
                  require_unhalted=True, rounds=3):
    """Order ONE walk for @a actor_id and settle it. Tries contact-free
    destinations at each radius in @a lengths, nearest radius first, and within a
    radius the destination FURTHEST from contact first; a candidate the
    pathfinder cannot route to simply ships nothing and the next is tried.

    WHY THIS EXISTS RATHER THAN "walk one tile north". At t=0 the squad is packed
    inside the Skyranger, so an actor's ADJACENT tiles are other soldiers and its
    straight lines run into the hull - the first version of this file demanded a
    3-tile open run and was rejected by 15/15 generations, and a 1-tile version
    is rejected just as often for the same reason. Pathfinding routes around
    both, and nothing this file asserts needs a path the harness predicted.

    Returns (host lastWalk, client lastWalk) or None when nothing could be
    ordered."""
    last = None
    # ROUNDS, not one pass: a walk that lands but is too SHORT still MOVED the
    # actor, and the geometry that made it short - being packed inside the
    # Skyranger with nothing but hull and squadmates around - is exactly what the
    # move fixes. A second pass from the new position routinely succeeds where
    # the first could not (observed: an actor still in the craft had no routable
    # 2- or 3-tile destination at all).
    for _ in range(rounds):
        progressed = False
        for radius in lengths:
            actor = unit_of(host, actor_id)
            occ = {pos_of(u) for u in battle_state(host)["units"] if not u.get("isOut")}
            for _, dest in straight_runs(host, actor, occ, length=radius):
                prev = walk_action_id(host)
                resp = send_walk(client, actor_id, dest[0])
                if not resp.get("iseq"):
                    continue
                wait_walk_settled(host, client, prev)
                settle_reveal(host, client)
                hw, cw = last_walk(host), last_walk(client)
                last = (hw, cw)
                progressed = True
                halted = bool((hw.get("restate") or {}).get("halted"))
                if (len(hw.get("steps") or []) >= min_steps
                        and not (require_unhalted and halted)):
                    return hw, cw
                if halted:
                    # A REAL halt (almost always `no_tu` on a drained actor). Not
                    # a failure of the atom - it is what SS2.W2 says must happen -
                    # but the caller asked for a clean walk, so try a shorter plan.
                    print(f"    [{what}] a {len(hw['steps'])}-step walk HALTED "
                          f"({(hw.get('restate') or {}).get('reason')!r}); trying a "
                          "shorter plan")
        if not progressed:
            break
    return last if (last and not require_unhalted) else None


def assert_every_step_hashed(gc, expected, what):
    """SS2.W2 rule 3 / RB-D14: EVERY `walk_step` ev carries h:{unitsStats}.

    Read off the event ring's own `h` flag, and load-bearing in a way an
    end-of-walk hash compare is not: the client VERIFIES each carried hash the
    moment it applies the ev (CoopHashCheck::verify, immediately after
    CoopDisplayQueue::onApplied), so an ev that carries no hash is verified
    against nothing and a per-tile divergence would survive to the end of the
    walk. The freeze check beside it is the other half - a verify that FAILED
    would have set desyncFrozen."""
    ring = gc.cmd({"cmd": "event_log", "tail": 80}).get("events", [])
    steps = [e for e in ring if e["kind"] == "walk_step"]
    assert len(steps) >= expected, (
        f"{what}: the event ring holds {len(steps)} walk_step entries, expected at "
        f"least {expected}")
    unhashed = [e for e in steps[-expected:] if not e.get("h")]
    assert not unhashed, (
        f"{what}: {len(unhashed)} walk_step ev(s) carried NO h:{{unitsStats}} - "
        f"{unhashed}. SS2.W2 rule 3 is the point of the per-step shape.")
    assert gc.cmd({"cmd": "battle_state"})["authority"]["desyncFrozen"] is False, (
        f"{what}: this machine is DESYNC-FROZEN - a per-step hash compare FAILED")


def walk_and_settle(host, client, actor_id, dest, what, **kw):
    """One admitted client walk, settled and fully flushed. Returns the HOST's
    and the CLIENT's own lastWalk records."""
    prev = walk_action_id(host)
    resp = send_walk(client, actor_id, dest, **kw)
    assert resp.get("iseq"), f"{what}: battle_intent walk did not ship: {resp}"
    wait_walk_settled(host, client, prev)
    settle_reveal(host, client)
    return last_walk(host), last_walk(client)


def assert_step_stream(hw, cw, what, expect_len=None, expect_halted=False):
    """SS2.W2's per-step contract, checked on BOTH machines' records."""
    for tag, w in (("host", hw), ("client", cw)):
        steps = w.get("steps") or []
        assert steps, f"{what}: the {tag} recorded NO walk_step events at all"
        for i, s in enumerate(steps):
            assert s["stepIndex"] == i, (
                f"{what}: {tag} step {i} carries stepIndex {s['stepIndex']} - SS2.W2/"
                "WV-D37 requires 0-based, +1 per emitted step ev")
        seqs = [s["seq"] for s in steps]
        assert all(b > a for a, b in zip(seqs, seqs[1:])), \
            f"{what}: {tag} step seqs are not strictly increasing: {seqs}"
        # every step's `to` must be one tile from the previous `from`
        for s in steps:
            assert tpos(s["to"]) != tpos(s["from"]), \
                f"{what}: {tag} step {s['stepIndex']} did not move ({s['from']})"

    hsteps = hw["steps"]
    csteps = cw["steps"]
    assert len(hsteps) == len(csteps), (
        f"{what}: host emitted {len(hsteps)} step ev(s) but the client applied "
        f"{len(csteps)} - one ev per EXECUTED step is the contract")
    for a, b in zip(hsteps, csteps):
        assert (a["stepIndex"], tpos(a["from"]), a["dir"], tpos(a["to"]),
                a["tuAfter"], a["enAfter"]) == \
               (b["stepIndex"], tpos(b["from"]), b["dir"], tpos(b["to"]),
                b["tuAfter"], b["enAfter"]), \
            f"{what}: host step {a} != client step {b}"

    if expect_len is not None:
        assert len(hsteps) == expect_len, (
            f"{what}: expected {expect_len} executed step(s), got {len(hsteps)}")

    for tag, w in (("host", hw), ("client", cw)):
        r = w.get("restate") or {}
        assert r, f"{what}: the {tag} has no completion restate"
        rpath = [tpos(p) for p in r["path"]]
        steps = [tpos(s["to"]) for s in w["steps"]]
        assert rpath == steps, (
            f"{what}: {tag}'s bt_action_end path {rpath} is not the FULL EXECUTED "
            f"path {steps} (SS2.W2 rule 4/5 - the executed prefix verbatim, no "
            "retraction and no rewind)")
        fin = r["final"]
        assert tpos(fin["pos"]) == steps[-1], (
            f"{what}: {tag}'s final.pos {tpos(fin['pos'])} != the last step's "
            f"post-state {steps[-1]}")
        assert fin["tu"] == w["steps"][-1]["tuAfter"], (
            f"{what}: {tag}'s final.tu {fin['tu']} != the last step's tuAfter "
            f"{w['steps'][-1]['tuAfter']}")
        assert fin["energy"] == w["steps"][-1]["enAfter"], (
            f"{what}: {tag}'s final.energy {fin['energy']} != the last step's "
            f"enAfter {w['steps'][-1]['enAfter']}")
        if expect_halted is not None:
            assert bool(r["halted"]) is bool(expect_halted), (
                f"{what}: {tag}'s restate halted={r['halted']}, expected "
                f"{expect_halted}")
    assert cw["restate"]["agreesWithSteps"] is True, (
        f"{what}: the CLIENT reported that the completion restate does NOT agree "
        "with the step evs it applied (SS2.W2 rule 4's re-verification failed)")


def assert_unit_parity(host, client, actor_id, what):
    hu = unit_of(host, actor_id)
    cu = unit_of(client, actor_id)
    for field in ("x", "y", "z", "tu", "energy", "direction", "kneeled",
                  "motionPoints", "status"):
        assert hu[field] == cu[field], (
            f"{what}: unit {actor_id} field '{field}' differs - host={hu[field]} "
            f"client={cu[field]}")
    return hu, cu


def event_kinds_since(gc, tail=60):
    return [e["kind"] for e in gc.cmd({"cmd": "event_log", "tail": tail}).get("events", [])]


# ----- PHASES -------------------------------------------------------------

def phase1_open_ground(host, client, actor_id):
    """PHASE 1 + the per-step hash. Runs one step at a time so
    assert_hash_clean() lands AFTER EVERY STEP, which is the whole point of
    SS2.W2 rule 3's per-step h:{unitsStats}."""
    actor = unit_of(host, actor_id)
    before_tu = actor["tu"]
    before_en = actor["energy"]
    t0 = time.time()

    executed = []
    for k in range(1, 3):
        # Leg 1 may have to leave the Skyranger (see pick_and_walk's docstring);
        # after that the actor is on open ground and the legs stay SHORT, so the
        # actor keeps TU for PHASE 1b's multi-step walk.
        got = pick_and_walk(host, client, actor_id, f"PHASE 1 leg {k}",
                            lengths=(1, 2, 3) if k == 1 else (1, 2))
        assert got is not None, f"PHASE 1: no walk could be ordered for leg {k}"
        hw, cw = got
        assert_step_stream(hw, cw, f"PHASE 1 leg {k}")
        n = len(hw["steps"])
        executed.extend(tpos(s["to"]) for s in hw["steps"])
        # SS2.W2 rule 3: the per-step hash is what localises a desync to a TILE.
        # Two assertions, because they cover different failures - see
        # assert_every_step_hashed()'s own docstring.
        assert_every_step_hashed(client, n, f"PHASE 1 leg {k}")
        assert_hash_clean(host, client, full=True,
                          what=f"after PHASE 1 walk leg {k} ({n} step(s))")
        assert_unit_parity(host, client, actor_id, f"after PHASE 1 leg {k}")

    elapsed = time.time() - t0
    hu = unit_of(host, actor_id)
    assert pos_of(hu) == executed[-1], (
        f"PHASE 1: the actor ended at {pos_of(hu)}, but the last emitted step said "
        f"{executed[-1]}")
    assert hu["tu"] < before_tu, "PHASE 1: the walk spent no TU"
    assert hu["motionPoints"] > 0, (
        "PHASE 1: motionPoints never moved - BattleUnit::keepWalking() bumps them at "
        "every completed step and they are INSIDE the hashed unitsStats bucket, so a "
        "zero here means the steps were not real")
    print(f"PASS PHASE 1: unit {actor_id} walked {len(executed)} tile(s) "
          f"{pos_of(actor)} -> {pos_of(hu)}, TU {before_tu} -> {hu['tu']}, "
          f"energy {before_en} -> {hu['energy']}, motionPoints {hu['motionPoints']}, "
          f"per-step hash clean on ALL buckets after every step "
          f"({elapsed:.2f}s of battle-phase wall clock)")
    return elapsed


def phase1b_multi_step(host, client, actor_id):
    """The multi-step half of PHASE 1: ONE intent, several executed steps, so
    "one ev per step, strictly increasing stepIndex" is asserted on a real
    multi-step stream rather than inferred from single-step legs."""
    t0 = time.time()
    got = pick_and_walk(host, client, actor_id, "PHASE 1b",
                        lengths=(WALK_RUN, 2, WALK_RUN + 1), min_steps=2)
    elapsed = time.time() - t0
    hw, cw = got if got else (None, None)
    assert hw is not None and len(hw["steps"]) >= 2, (
        "PHASE 1b: no candidate destination produced a MULTI-STEP walk - "
        "'one ev per step, strictly increasing stepIndex' needs more than one step "
        "to be a real statement. FIXTURE failure.")

    n = len(hw["steps"])
    assert_step_stream(hw, cw, "PHASE 1b", expect_len=n)
    assert n == hw["plannedLen"], (
        f"PHASE 1b: the host executed {n} of {hw['plannedLen']} planned step(s) "
        "without halting")
    assert_every_step_hashed(client, n, "PHASE 1b")
    assert_hash_clean(host, client, full=True, what="after the PHASE 1b multi-step walk")
    assert_unit_parity(host, client, actor_id, "after PHASE 1b")
    print(f"PASS PHASE 1b: ONE intent -> {n} walk_step ev(s) with stepIndex "
          f"0..{n - 1}, each carrying h:{{unitsStats}}, completion restate carrying "
          f"the full executed path {[tpos(s['to']) for s in hw['steps']]}, all buckets "
          f"EQUAL ({elapsed:.2f}s battle-phase)")
    return elapsed


def phase2_hud(host, client, actor_id):
    """WV-D33. Asserted on the PAINTED NumberText values."""
    # Select the actor on the CLIENT so its numbers are the ones on the strip.
    for _ in range(12):
        if battle_state(client).get("selectedId") == actor_id:
            break
        client.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.15)
    assert battle_state(client).get("selectedId") == actor_id, (
        "PHASE 2: could not TAB the client's selection onto the actor - the HUD "
        "proof needs the walking unit to be the one the strip is showing")

    cs0 = battle_state(client)
    hud0 = cs0["hud"]
    u0 = units_by_id(cs0)[actor_id]
    assert hud0["tu"] == u0["tu"], (
        f"PHASE 2 PRECONDITION: the client's painted TU {hud0['tu']} already "
        f"disagrees with the model {u0['tu']} before the walk")

    got = pick_and_walk(host, client, actor_id, "PHASE 2 HUD walk", lengths=(1, 2))
    assert got is not None, "PHASE 2: no walk could be ordered for the HUD proof"
    hw, cw = got
    assert_step_stream(hw, cw, "PHASE 2")

    cs1 = battle_state(client)
    hud1 = cs1["hud"]
    u1 = units_by_id(cs1)[actor_id]
    assert u1["tu"] < u0["tu"], "PHASE 2: the walk spent no TU, so the HUD has " \
                                "nothing to have refreshed"
    assert hud1["tu"] == u1["tu"], (
        f"PHASE 2 (WV-D33): the client's PAINTED TU number is {hud1['tu']} but the "
        f"unit now holds {u1['tu']} - the apply path did not call "
        "updateSoldierInfo(false), which is the whole of ruling D4's HUD item")
    assert hud1["energy"] == u1["energy"], (
        f"PHASE 2 (WV-D33): painted energy {hud1['energy']} != model "
        f"{u1['energy']}")
    assert hud1["tu"] != hud0["tu"], (
        f"PHASE 2: the painted TU did not change at all ({hud0['tu']}) - the "
        "assertion above would then hold for the wrong reason")
    # SS2.4a's CLIENT AUTHORITY RULE: checkFOV=false, so the client authored no fog.
    assert_reveal_parity(host, client, "after the PHASE 2 HUD walk")
    print(f"PASS PHASE 2 (WV-D33): the client's PAINTED HUD numbers followed the "
          f"applied walk within one pump tick - TU {hud0['tu']} -> {hud1['tu']}, "
          f"energy {hud0['energy']} -> {hud1['energy']}, fog parity unchanged")


def phase3_halt(host, client, actor_id):
    """SS2.W2 rule 5 + the halt presenter (WV-D53)."""
    cands = walk_candidates(host, actor_id, lengths=(WALK_RUN, 2))
    assert cands, "PHASE 3: no contact-free destination left for the halt walk"

    hw = cw = None
    for dest in cands:
        prev = walk_action_id(host)
        # ARMED BEFORE THE SEND, deliberately. The intent travels over the game's
        # own TCP lane while battle_halt_walk goes straight to the host's
        # TestServer, so arming afterwards is a race the walk usually wins. The
        # latch is one-shot and idempotent, so a candidate that ships nothing
        # simply leaves it armed for the next one - which is what this loop wants.
        host.ok({"cmd": "battle_halt_walk"})
        resp = send_walk(client, actor_id, dest)
        if not resp.get("iseq"):
            continue
        wait_walk_settled(host, client, prev)
        settle_reveal(host, client)
        hw, cw = last_walk(host), last_walk(client)
        if hw["plannedLen"] >= 2 and 0 < len(hw["steps"]) < hw["plannedLen"]:
            break
    assert hw is not None and hw["plannedLen"] >= 2, (
        "PHASE 3: no candidate destination produced a MULTI-STEP plan - a halt can "
        "only be observed on a walk with something left to halt. FIXTURE failure.")

    hsteps = hw["steps"]
    assert 0 < len(hsteps) < hw["plannedLen"], (
        f"PHASE 3: the walk executed {len(hsteps)} of {hw['plannedLen']} planned "
        "step(s) - the halt lever must stop it AFTER at least one step and BEFORE "
        "the last")
    assert_step_stream(hw, cw, "PHASE 3", expect_len=len(hsteps), expect_halted=True)

    r = hw["restate"]
    assert r["reason"] in ("blocked", "no_tu", "no_energy", "spot", "reaction",
                           "prox", "fall", "unit_down"), (
        f"PHASE 3: restate reason {r['reason']!r} is not one of SS2.W2's frozen "
        "halt enum values")
    assert r["reason"] == "blocked", (
        f"PHASE 3: expected the halt lever to report 'blocked', got {r['reason']!r}")
    executed = [tpos(s["to"]) for s in hsteps]
    hu = unit_of(host, actor_id)
    assert pos_of(hu) == executed[-1], (
        f"PHASE 3: the unit is at {pos_of(hu)} but the last emitted step said "
        f"{executed[-1]} - a halt must not rewind (SS2.W2 rule 5)")
    assert banner(client) == STR_HALT_BLOCKED, (
        f"PHASE 3: the ORDERING seat's banner is {banner(client)!r}, expected "
        f"{STR_HALT_BLOCKED!r}. A raw STR_ key here means the deployed "
        "bin/x64/Release/common/Language copy is stale (WV-D17); the wrong wording "
        "means the halt was presented through the CANCEL table, which SS2.W2/"
        "WV-D53 forbids - a halted walk is not a cancelled order.")
    assert banner(host) != STR_HALT_BLOCKED, (
        "PHASE 3: the OBSERVING machine printed the ordering seat's halt message - "
        "SS2.W2 shows it only on the ordering seat")
    assert_hash_clean(host, client, full=True, what="after the PHASE 3 halted walk")
    assert_unit_parity(host, client, actor_id, "after PHASE 3")
    print(f"PASS PHASE 3: battle_halt_walk stopped the walk after {len(hsteps)} of "
          f"{hw['plannedLen']} step(s); the emitted step evs STAND, the restate carries the "
          f"executed prefix {executed} with halted=True reason={r['reason']!r}, the "
          f"ordering seat shows {STR_HALT_BLOCKED!r}, all buckets EQUAL")


def phase4_denies(host, client, actor_id, client_own_ids):
    """The two deny paths SS2.W2's validator owns, each observed once."""
    # --- path_changed: a plan through an OCCUPIED tile -------------------
    st = battle_state(host)
    units = units_by_id(st)
    blocker = None
    walker = None
    for uid in client_own_ids:
        u = units.get(uid)
        if not u or u.get("isOut"):
            continue
        for other in units.values():
            if other["id"] == uid or other.get("isOut"):
                continue
            if other["z"] != u["z"]:
                continue
            if max(abs(other["x"] - u["x"]), abs(other["y"] - u["y"])) == 1:
                walker, blocker = u, other
                break
        if walker:
            break
    assert walker is not None, (
        "PHASE 4: no client-owned unit has another unit on an ADJACENT tile, so a "
        "one-step plan through an occupied tile cannot be built - FIXTURE failure, "
        "not a result about the validator")

    walks_before = walk_action_id(host)
    resp = send_walk(client, walker["id"], pos_of(blocker), path=[pos_of(blocker)])
    assert resp.get("iseq"), f"PHASE 4: the blocked-plan intent did not ship: {resp}"
    iseq = resp["iseq"]

    def denied():
        ld = event_state(client).get("lastDeny")
        return ld if ld and ld.get("iseq") == iseq else None
    ld = client.wait_for("deny(path_changed)", denied, timeout=15)
    assert ld["reason"] == "path_changed", (
        f"PHASE 4: expected reason 'path_changed' for a plan through the tile unit "
        f"{blocker['id']} is standing on, got {ld}")
    assert banner(client) == STR_DENY_PATH_CHANGED, (
        f"PHASE 4: banner {banner(client)!r}, expected {STR_DENY_PATH_CHANGED!r}")
    assert walk_action_id(host) == walks_before, (
        "PHASE 4: the host OPENED a walk chain for a denied intent - a deny must "
        "mint no actionId and stream nothing (SS2.5: execute at admission or deny)")
    assert pos_of(unit_of(host, walker["id"])) == pos_of(walker), (
        "PHASE 4: the denied walk moved the unit anyway")
    print(f"PASS PHASE 4a: a plan through the tile of unit {blocker['id']} was denied "
          f"path_changed, nothing was emitted, the unit did not move")

    # --- cost_changed: a stale basis ------------------------------------
    actor = unit_of(host, actor_id)
    resp = None
    for dest in walk_candidates(host, actor_id, lengths=(1, 2)):
        resp = send_walk(client, actor_id, dest, tu_basis=999)
        if resp.get("iseq"):
            break
    assert resp and resp.get("iseq"), \
        f"PHASE 4: the stale-basis intent did not ship from any candidate: {resp}"
    iseq = resp["iseq"]

    def denied2():
        ld = event_state(client).get("lastDeny")
        return ld if ld and ld.get("iseq") == iseq else None
    ld = client.wait_for("deny(cost_changed)", denied2, timeout=15)
    assert ld["reason"] == "cost_changed", (
        f"PHASE 4: expected reason 'cost_changed' for tuBasisOverride=999, got {ld}")
    assert banner(client) == STR_DENY_COST_CHANGED, (
        f"PHASE 4: banner {banner(client)!r}, expected {STR_DENY_COST_CHANGED!r}")
    assert pos_of(unit_of(host, actor_id)) == pos_of(actor), (
        "PHASE 4: the cost_changed-denied walk moved the unit anyway")
    assert_hash_clean(host, client, full=True, what="after the PHASE 4 denies")
    print("PASS PHASE 4b: tuBasisOverride=999 denied cost_changed, unit unmoved, "
          "all buckets EQUAL after both denies")


def reserve_probe(host, client, actor_id, mode, radius):
    """ONE reserve probe on @a actor_id: set THIS machine's reserve to @a mode
    and try a walk to a destination @a radius tiles away. Reports which of
    WV-D48's branches (if any) the client's own rule took:

      ("refused",   out)  branch (a) - the FIRST step violates, nothing shipped;
      ("truncated", out)  branch (b) - a step k>1 violates, a k-1 prefix shipped;
      ("walk",      out)  the reserve allowed the whole plan (TU still too high);
      ("deny",      out)  the host denied it - on a drained actor that is
                          `cost_changed`, SS2.3's own mapping for a first step
                          that is no longer affordable;
      ("nocand",   None)  nowhere left to walk.

    WHY THE SEARCH EXISTS AT ALL, and why it is not a fixture smell: vanilla's
    reserve refuses inside a NARROW TU WINDOW and not below it.
    BattlescapeGame::checkReservedTU's own early-out - "current TU is less than
    required for reserved shoot, we can't reserve anything" - returns TRUE
    (allow) once the reserve cost alone exceeds the unit's TU, and that early-out
    is live exactly when justChecking is FALSE, which is how vanilla calls it for
    a first step and therefore how this packet calls it too. So the window is
    [reserveCost, reserveCost + stepCost), one step wide, and a walk-down in
    whole-tile increments can step straight over it. The probe therefore sweeps
    actors and reserve MODES rather than assuming a TU number - asserting a
    hard-coded TU level would be asserting arithmetic, not the rule."""
    set_reserve(client, mode=mode)
    ev0 = event_state(client)
    cands = walk_candidates(host, actor_id, lengths=(radius,))
    if not cands:
        return ("nocand", None)
    for dest in cands:
        out = send_walk_outcome(host, client, actor_id, dest)
        ev1 = event_state(client)
        if ev1["coopWalkReserveRefusals"] > ev0["coopWalkReserveRefusals"]:
            return ("refused", out)
        if ev1["coopWalkReserveTruncations"] > ev0["coopWalkReserveTruncations"]:
            return ("truncated", out,
                    ev0["coopWalkReserveTruncations"],
                    ev1["coopWalkReserveTruncations"])
        if out[0] == "walk":
            return ("walk", out)
        if out[0] == "deny":
            return ("deny", out)
    return ("nocand", None)


def phase5_reserve(host, client, client_ids):
    """WV-D48 branch (a): a FIRST-step reserve violation sends NO intent at all
    and shows the LOCAL VANILLA refusal.

    It is also this phase's own CONTROL: a refusal that really happens proves the
    reserve BITES on this unit at this TU, which is what stops PHASE 5(b)'s
    "the host did not truncate" from passing because nothing would have
    truncated anyway."""
    set_reserve(host, mode="none", kneel=False)
    set_reserve(client, mode="none", kneel=False)

    found = None
    for actor_id in richest(host, client_ids, len(client_ids)):
        for mode in ("aimed", "snap"):
            for _ in range(14):
                ev_before = event_state(client)
                host_seq_before = event_state(host)["lastSeqEmitted"]
                warn_before = warning_text(client)
                kind, out = reserve_probe(host, client, actor_id, mode, radius=1)
                if kind == "refused":
                    found = (actor_id, mode, out[1], ev_before, host_seq_before,
                             warn_before)
                    break
                if kind in ("deny", "nocand"):
                    break   # this actor is spent (or boxed in) - try the next
            if found:
                break
        if found:
            break

    assert found is not None, (
        "PHASE 5(a): no client actor could be walked into the TU window where its "
        "OWN reserve refuses the FIRST step - see reserve_probe()'s docstring for "
        "why that window is one step wide. FIXTURE failure, and with it the CONTROL "
        "that keeps PHASE 5(b) honest.")
    actor_id, mode, resp, ev_before, host_seq_before, warn_before = found
    ev_after = event_state(client)

    assert not resp.get("iseq"), (
        f"PHASE 5(a): an intent WAS shipped (iseq {resp.get('iseq')}) even though "
        "the client's own reserve refuses the first step - SS2.W2/WV-D48 requires "
        "that NOTHING goes on the wire")
    assert ev_after["lastSeqEmitted"] == ev_before["lastSeqEmitted"], (
        "PHASE 5(a): the client's own emit counter moved")
    assert event_state(host)["lastSeqEmitted"] == host_seq_before, (
        "PHASE 5(a): the HOST emitted something, so an intent did reach it")
    assert ev_after["inFlight"] in (None, {}), (
        f"PHASE 5(a): the client is holding an in-flight intent: {ev_after['inFlight']}")

    want = STR_RESERVE_AIMED if mode == "aimed" else STR_RESERVE_SNAP
    wt = warning_text(client)
    assert wt == want, (
        f"PHASE 5(a): the LOCAL VANILLA refusal reads {wt!r}, expected {want!r} (it "
        f"was {warn_before!r} before). SS2.W2 requires the client to show vanilla's "
        "OWN reserve refusal here, and it is raised by the very "
        "checkReservedTU(justChecking=false) call that returns false - so a wrong "
        "or absent string means the client did not run vanilla's predicate.")
    print(f"PASS PHASE 5(a) (and the CONTROL for 5(b)): with THIS machine's reserve "
          f"set to {mode!r}, unit {actor_id} at TU {unit_of(host, actor_id)['tu']} "
          f"refused its own first step - refusals "
          f"{ev_before['coopWalkReserveRefusals']} -> "
          f"{ev_after['coopWalkReserveRefusals']}, NOTHING shipped, the host's emit "
          f"counter unmoved, and the LOCAL vanilla refusal {wt!r} on screen")
    set_reserve(client, mode="none")


def phase5b_truncation(host, client, client_ids):
    """WV-D48's k>1 half + WV-D14/WV-D38's per-machine proof: the client's own
    k-1 prefix must be admitted and executed IN FULL, IDENTICALLY under two
    DIFFERENT host reserve settings.

    Each run gets its own actor. A truncation only exists inside the same narrow
    TU window PHASE 5(a) documents, so an actor just walked THROUGH that window
    cannot produce a second one."""
    results = []
    used = set()
    for run_idx, host_mode in enumerate(("none", "aimed"), start=1):
        set_reserve(host, mode=host_mode)
        set_reserve(client, mode="none")

        found = None
        for actor_id in richest(host, client_ids, len(client_ids), exclude=used):
            for mode in ("aimed", "snap"):
                for _ in range(14):
                    probe = reserve_probe(host, client, actor_id, mode,
                                          radius=WALK_RUN)
                    kind, out = probe[0], probe[1]
                    if kind == "truncated":
                        assert out[0] == "walk", (
                            f"PHASE 5(b) run {run_idx}: the client truncated the plan "
                            f"but the host answered {out[0]}: {out[1]}")
                        found = (actor_id, mode, out[1], last_walk(client),
                                 probe[2], probe[3])
                        break
                    if kind in ("deny", "nocand", "refused"):
                        break
                if found:
                    break
            if found:
                break
        assert found is not None, (
            f"PHASE 5(b) run {run_idx}: no client actor could be walked into the TU "
            "window where its OWN reserve truncates a multi-step plan - FIXTURE "
            "failure (see reserve_probe()'s docstring on the window)")
        actor_id, mode, hw, cw, trunc_before, trunc_after = found
        used.add(actor_id)

        assert_step_stream(hw, cw, f"PHASE 5(b) run {run_idx}", expect_halted=False)
        executed = [tpos(s["to"]) for s in hw["steps"]]
        # THE TRUNCATION IS THE CLIENT'S OWN COUNTER, asserted here rather than
        # inferred from the path length. A GEOMETRIC claim was tried first and is
        # WRONG: a route to a tile N tiles away (Chebyshev) can be LONGER than N
        # steps, because Pathfinding routes around hulls and down ramps - a
        # 5-step execution toward a 3-tile destination is a perfectly ordinary
        # FULL plan, not a prefix (observed). The counter is the direct reading
        # of WV-D48's k>1 branch and admits no such ambiguity.
        assert trunc_after == trunc_before + 1, (
            f"PHASE 5(b) run {run_idx}: the client's own truncation counter went "
            f"{trunc_before} -> {trunc_after}; WV-D48's k>1 branch is what this run "
            "exists to observe")
        assert len(executed) > 0, (
            f"PHASE 5(b) run {run_idx}: the truncated prefix executed no steps")
        assert len(executed) == hw["plannedLen"], (
            f"PHASE 5(b) run {run_idx}: the HOST executed {len(executed)} of the "
            f"{hw['plannedLen']} step(s) the CLIENT shipped - the host must execute "
            "the client's prefix IN FULL")
        assert hw["restate"]["halted"] is False, (
            f"PHASE 5(b) run {run_idx}: the HOST halted a walk whose plan the CLIENT "
            f"had already shortened for its own reserve - with the host's reserve set "
            f"to '{host_mode}' this is exactly WV-D38's failure mode (the host applied "
            "ITS reserve to a client-origin walk)")
        assert_hash_clean(host, client, full=True,
                          what=f"after PHASE 5(b) run {run_idx} (host reserve={host_mode})")
        results.append((host_mode, actor_id, mode, executed))
        print(f"PASS PHASE 5(b) run {run_idx}: with the HOST's reserve set to "
              f"'{host_mode}' and the CLIENT's to {mode!r}, unit {actor_id}'s own "
              f"reserve TRUNCATED the plan (counter {trunc_before} -> {trunc_after}) "
              f"and the {len(executed)}-step prefix it shipped was ADMITTED and "
              f"executed IN FULL ({executed}), unhalted")

    set_reserve(host, mode="none")
    set_reserve(client, mode="none")
    modes = [r[0] for r in results]
    assert modes == ["none", "aimed"], modes
    print(f"PASS PHASE 5(b): the admitted result was IDENTICAL under two DIFFERENT "
          f"host reserve settings {modes} - every shipped prefix executed IN FULL and "
          f"unhalted, which is WV-D14's per-machine-reserve contract and WV-D38's "
          f"'the host does not apply ITS reserve to a client-origin walk'")


def phase6_safelist(host, client, walker_id, holder_id):
    """WR-6 / WV-D29 / WV-D37: with `coopCancelOnAnyPartnerAction` ON, an applied
    partner WALK STEP must NOT cancel a held pending intent. Before this packet
    R2-P7's safe-list carried prd-r3a's stale batched name `walk_steps`, so
    SS2.W2's frozen SINGULAR `walk_step` fell through to the unclassified arm and
    EVERY step of every partner walk cancelled whatever the player was holding.

    HOW THE STATE IS BUILT, and why not "just walk next to a held order".
    R2-P7's cancel policy only runs while a PENDING intent is held, and a pending
    intent is only created by a busy DENY - so the held order and the streaming
    walk must be two DIFFERENT actions overlapping in time. That overlap is not
    reliably producible from the harness: measured on this build, a 4-to-7-step
    walk completes inside the ~50 ms it takes the next TestServer command to
    reach the host, so the second intent is ADMITTED rather than busy-denied
    (observed repeatedly; the host's own log shows consecutive actionIds).

    So the state is built DETERMINISTICALLY instead, out of levers that already
    exist and with a POSITIVE CONTROL that makes the negative meaningful:
      * `hold_chain` keeps a finished chain artificially open, which is exactly
        the busy window a second intent needs - that intent is denied `busy` and
        goes PENDING (R2-P7's own mechanism, unchanged);
      * `inject_ev {kind:"walk_step"}` emits a real envelope through the real
        `CoopEmit::sendEv` with the real next seq, which the client applies
        through the real `CoopDisplayQueue::onApplied` and therefore through the
        real `onEvAppliedCancelCheck` - the safe-list is consulted exactly as it
        is for a walk the host is really executing. Deliberately WITHOUT a
        `unit` field: with one, the applier would read the absent `from`/`to` as
        (0,0,0) and teleport a soldier; without one it logs and drops, which
        leaves the cancel policy as the only thing the ev exercises;
      * the POSITIVE CONTROL injects an UNCLASSIFIED kind and requires it to
        CANCEL. Without it "the order survived" would also be satisfied by a
        cancel policy that was off, or by an ev that never arrived.
    """
    client.ok({"cmd": "set_option", "name": "coopCancelOnAnyPartnerAction", "value": True})
    hold_ms = 20000
    try:
        host.ok({"cmd": "hold_chain", "ms": hold_ms})
        # (1) an action that will quiesce INTO the hold.
        a = unit_of(client, holder_id)
        client.ok({"cmd": "battle_intent", "kind": "turn", "actor": holder_id,
                   "toDir": (a["direction"] + 2) % 8})
        client.wait_for("the first action is running and the chain is being held",
                        lambda: (event_state(host).get("busyOwnerSeat", -1) >= 0) or None,
                        timeout=20)

        # (2) a second order, busy-denied into the PENDING slot.
        b = unit_of(client, walker_id)
        client.ok({"cmd": "battle_intent", "kind": "turn", "actor": walker_id,
                   "toDir": (b["direction"] + 2) % 8})
        held = client.wait_for("a busy-denied order held PENDING",
                               lambda: battle_state(client).get("coopPendingIntent") or None,
                               timeout=20)
        print(f"  PHASE 6: order {held} is HELD PENDING (busy-denied by the held chain)")

        # (3) THE CASE: a partner walk step applies while it is held.
        seq0 = event_state(client)["lastSeqApplied"]
        r = host.ok({"cmd": "inject_ev", "kind": "walk_step"})
        client.wait_for("the client applied the injected walk_step",
                        lambda: (event_state(client)["lastSeqApplied"] >= r["seq"]) or None,
                        timeout=20)
        time.sleep(0.3)
        after = battle_state(client)
        assert after.get("coopPendingIntent"), (
            f"PHASE 6 (WR-6): the held order was DROPPED by an applied `walk_step` "
            f"ev (banner={after.get('coopWaitText')!r}). That is exactly what the "
            "stale `walk_steps` safe-list literal produces: SS2.W2 froze the ev kind "
            "as the SINGULAR `walk_step`, so an un-renamed safe-list treats EVERY "
            "step of a partner's walk as an unclassified partner action.")
        assert not after.get("coopWaitText", "").startswith("Order cancelled"), (
            f"PHASE 6 (WR-6): the banner reads {after.get('coopWaitText')!r} after a "
            "partner walk step")
        print(f"  PHASE 6: an applied walk_step ev (seq {r['seq']}) left the held "
              f"order standing: {after['coopPendingIntent']}")

        # (4) POSITIVE CONTROL: an UNCLASSIFIED kind must cancel it.
        r2 = host.ok({"cmd": "inject_ev", "kind": "rw_not_safe_listed"})
        client.wait_for("the client applied the control ev",
                        lambda: (event_state(client)["lastSeqApplied"] >= r2["seq"]) or None,
                        timeout=20)
        cancelled = client.wait_for(
            "the UNCLASSIFIED ev cancels the held order (positive control)",
            lambda: (battle_state(client).get("coopPendingIntent") in (None, {})) or None,
            timeout=20)
        ctl_banner = banner(client)
        assert ctl_banner.startswith("Order cancelled"), (
            f"PHASE 6 POSITIVE CONTROL: an UNCLASSIFIED ev kind left the banner at "
            f"{ctl_banner!r} instead of a cancel - the cancel policy is not running "
            "at all, which would make the walk_step case above vacuous")
        print(f"  PHASE 6 POSITIVE CONTROL: an UNCLASSIFIED ev kind DID cancel the "
              f"held order ({ctl_banner!r}) - so the policy really was live for the "
              "walk_step case")
    finally:
        client.ok({"cmd": "set_option", "name": "coopCancelOnAnyPartnerAction",
                   "value": False})

    # Let the hold window close before anything else runs.
    client.wait_for("the hold_chain window closes",
                    lambda: (event_state(host).get("busyOwnerSeat", -1) < 0) or None,
                    timeout=int(hold_ms / 1000) + 20)
    settle_reveal(host, client)
    assert_hash_clean(host, client, full=True, what="after PHASE 6")
    print("PASS PHASE 6 (WR-6): a partner `walk_step` did NOT cancel a held order, "
          "while an unclassified kind DID - the SS2.W2 safe-list rename is live")


def phase6b_host_origin(host, client, host_ids):
    """WV-D37: step evs are ORIGIN-INDEPENDENT - a HOST-origin walk emits them
    too, which is what the observing machine's ghost (W1-P12) will animate.

    Driven through the REAL UI (W1-P6's self-verifying `map_tile_click_pos`
    probe), because the host has no `battle_intent`: SS2.5's "host-local player
    input never enters the intent path"."""
    st = battle_state(host)
    units = units_by_id(st)
    candidates = [u for u in units.values()
                  if u["id"] in host_ids and not u.get("isOut")]
    assert candidates, "PHASE 6b: the host owns no live soldier"
    occupied = {pos_of(u) for u in units.values() if not u.get("isOut")}

    chosen = None
    for u in candidates:
        if session.nearest_non_player_distance(st, u) is not None and \
           session.nearest_non_player_distance(st, u) <= session.MAX_VIEW_DISTANCE:
            continue
        runs = (straight_runs(host, u, occupied, length=1, st=st)
                or straight_runs(host, u, occupied, length=2, st=st))
        if not runs:
            continue
        tile = runs[0][1][0]
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
        time.sleep(0.15)
        pr = host.cmd({"cmd": "map_tile_click_pos", "x": tile[0], "y": tile[1],
                       "z": tile[2]})
        if pr.get("ok") and pr.get("verified"):
            chosen = (u, tile, pr)
            break
    assert chosen is not None, (
        "PHASE 6b: no host-owned, contact-free soldier with a clickable adjacent "
        "open tile - FIXTURE failure, not a result about origin-independence")
    u, tile, pr = chosen

    # Select it on the host first, then click the ground tile.
    host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"],
             "button": "left"})
    time.sleep(0.4)
    prev = walk_action_id(host)
    arm0 = event_state(host)["coopWalkArmEntered"]
    sel = battle_state(host).get("selectedId")
    if sel != u["id"]:
        # The click selected nothing (an empty tile) - select via TAB instead.
        for _ in range(12):
            if battle_state(host).get("selectedId") == u["id"]:
                break
            host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
            time.sleep(0.15)
    assert battle_state(host).get("selectedId") == u["id"], (
        f"PHASE 6b: could not select host unit {u['id']} (selectedId="
        f"{battle_state(host).get('selectedId')})")

    landed = False
    for _ in range(4):
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
        time.sleep(0.15)
        pr = host.cmd({"cmd": "map_tile_click_pos", "x": tile[0], "y": tile[1],
                       "z": tile[2]})
        if not pr.get("verified"):
            break
        host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"],
                 "y": pr["winY"], "button": "left"})
        try:
            wait_walk_settled(host, client, prev, timeout=12)
            landed = True
            break
        except Exception:
            continue
    assert landed, (
        "PHASE 6b: the host's own ground click never produced a walk - the walk arm "
        f"was entered {event_state(host)['coopWalkArmEntered'] - arm0} time(s) since "
        "the click, so this is the click recipe or the fixture, not the atom")

    settle_reveal(host, client)
    hw = last_walk(host)
    cw = last_walk(client)
    assert hw.get("origin") == "host", (
        f"PHASE 6b: the host recorded origin={hw.get('origin')!r} for its OWN walk, "
        "expected 'host' (RB-D19)")
    # expect_halted=None: whether the HOST's own walk ran to its plan's end is
    # not what this phase is about, and it is not the harness's to control - the
    # host is driven through a real ground click, so vanilla's own TU guard can
    # legitimately stop it short (SS2.W2's `no_tu`). What IS asserted is
    # WV-D37: the step events exist, they are identical on both machines, and the
    # completion restate carries exactly the executed prefix.
    assert_step_stream(hw, cw, "PHASE 6b host-origin walk", expect_halted=None)
    assert_hash_clean(host, client, full=True, what="after the PHASE 6b host-origin walk")
    assert_unit_parity(host, client, u["id"], "after PHASE 6b")
    print(f"PASS PHASE 6b (WV-D37): a HOST-ORIGIN walk of unit {u['id']} emitted "
          f"{len(hw['steps'])} walk_step ev(s) that the CLIENT applied - step evs are "
          "origin-independent, all buckets EQUAL")


def phase7_burst(host, client, client_ids, host_ids):
    """Walk + turn + kneel interleaved across BOTH origins."""
    seq0 = event_state(host)["lastSeqEmitted"]
    actions = 0

    def do_client_turn(uid):
        u = unit_of(client, uid)
        client.ok({"cmd": "battle_intent", "kind": "turn", "actor": uid,
                   "toDir": (u["direction"] + 2) % 8})

    def do_client_kneel(uid):
        u = unit_of(client, uid)
        client.ok({"cmd": "battle_intent", "kind": "kneel", "actor": uid,
                   "kneel": not u["kneeled"]})

    for uid in client_ids[:2]:
        if pick_and_walk(host, client, uid, "PHASE 7 walk", lengths=(1, 2)) is not None:
            actions += 1
        do_client_turn(uid); actions += 1
        time.sleep(0.6)
        do_client_kneel(uid); actions += 1
        time.sleep(0.6)
        do_client_kneel(uid); actions += 1
        time.sleep(0.6)

    settle_reveal(host, client)
    ring = host.cmd({"cmd": "event_log", "tail": 80}).get("events", [])
    seqs = [e["seq"] for e in ring]
    assert all(b > a for a, b in zip(seqs, seqs[1:])), \
        f"PHASE 7: the host's emitted seqs are not strictly increasing: {seqs}"
    kinds = set(e["kind"] for e in ring)
    for want in ("walk_step", "turn", "kneel"):
        assert want in kinds, f"PHASE 7: no {want!r} in the burst ring: {sorted(kinds)}"
    for gc, tag in ((host, "host"), (client, "client")):
        assert event_state(gc)["queueDepth"] == 0, f"PHASE 7: {tag} queueDepth != 0"
    assert event_state(client)["lastSeqApplied"] == event_state(host)["lastSeqEmitted"], \
        "PHASE 7: the client did not drain everything the host emitted"
    assert_hash_clean(host, client, full=True, what="after the PHASE 7 burst")
    print(f"PASS PHASE 7: {actions} interleaved walk/turn/kneel actions, "
          f"{event_state(host)['lastSeqEmitted'] - seq0} envelopes emitted with "
          f"strictly increasing seq, queueDepth 0 on both machines, all buckets EQUAL")


def main():
    host, client, actor, soldier_ids = bring_up_qualifying_battle()
    try:
        st_h = battle_state(host)
        units = units_by_id(st_h)
        client_ids = [u["id"] for u in units.values()
                      if u.get("coop") == COOP_SEAT_1 and not u.get("isOut")]
        host_ids = [u["id"] for u in units.values()
                    if u.get("coop") == COOP_SEAT_0 and u.get("isPlayerSoldier")]
        assert len(client_ids) >= 4, (
            f"fixture is VACUOUS: the client owns {len(client_ids)} unit(s); this "
            "repro needs at least four - every phase that WALKS spends TU, and an "
            "actor that runs dry fails exactly like a broken atom would")
        actor_id = actor["id"]
        print(f"[repro_atom_walk] client-owned units {sorted(client_ids)}, "
              f"host-owned soldiers {sorted(host_ids)}")

        assert_reveal_parity(host, client, "at t=0 (pre-action)")
        assert_hash_clean(host, client, full=True, what="at t=0 (pre-action)")

        battle_t0 = time.time()
        phase1_open_ground(host, client, actor_id)
        elapsed = time.time() - battle_t0
        assert elapsed < 5.0 * 6, (
            f"PHASE 1 battle-phase wall clock {elapsed:.2f}s - the packet's <5 s "
            "target is per WALK; this is the six-leg aggregate and is reported so a "
            "regression in the pipeline's latency is visible")

        # ONE ACTOR PER TU-SPENDING PHASE, allocated by REMAINING TU (see
        # richest()). Every phase below that walks is handed the freshest unit
        # available at the moment it runs, so a phase can never fail merely
        # because an earlier one drained the squad.
        used = {actor_id}

        def take():
            uid = richest(host, client_ids, 1, exclude=used)[0]
            used.add(uid)
            return uid

        a_multi = take()
        phase1b_multi_step(host, client, a_multi)

        a_hud = take()
        phase2_hud(host, client, a_hud)
        a_halt = take()
        phase3_halt(host, client, a_halt)
        phase4_denies(host, client, richest(host, client_ids, 1)[0], client_ids)

        # ORDER MATTERS, and it is TU that orders it. PHASE 6 needs a LONG walk
        # (a short one finishes before a second order can be busy-denied into the
        # pending slot) and PHASE 7 needs actors that can still walk at all, while
        # PHASE 5's whole method is to walk actors DOWN until their own reserve
        # bites - so PHASE 5 goes LAST, after everything that needs fuel.
        rich2 = richest(host, client_ids, 2)
        phase6_safelist(host, client, rich2[0], rich2[1])
        phase6b_host_origin(host, client, host_ids)
        phase7_burst(host, client, richest(host, client_ids, 2), host_ids)

        phase5_reserve(host, client, client_ids)
        phase5b_truncation(host, client, client_ids)

        # PHASE 8: the wave's standing full-sweep assertion.
        settle_reveal(host, client)
        hh, ch = assert_hash_clean(host, client, full=True,
                                   what="after every walk-core action")
        assert_reveal_parity(host, client, "after every walk-core action")
        assert set(hh) == set(ch) and hh, f"bucket sets differ: {sorted(hh)} vs {sorted(ch)}"
        print(f"PASS PHASE 8: ALL {len(hh)} buckets EQUAL after every action "
              f"({sorted(hh)}), and reveal_state per-part parity is unchanged - the "
              "client authored no fog (SS2.4a client-authority rule, WV-D33's "
              "checkFOV=false)")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
    print("ALL W1-P9 ATOM WALK-CORE TESTS PASSED")
