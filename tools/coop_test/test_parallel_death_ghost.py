"""Parallel battlescape "atomic unit death" Phase 2c: the CLIENT-side death GHOST.

THE MECHANISM UNDER TEST. Phase 2a/2b made the parallel HOST ship one
`unit_casualty` packet per casualty and the parallel CLIENT apply it ATOMICALLY
(BattlescapeGame::coopApplyCasualty) on the bookkeeping clock - so by the instant
the packet is applied the victim is already DEAD, tile-unlinked, and its corpse
minted with the host's ids. Phase 2b left a STUB where the death ANIMATION used to
be (the corpse simply appeared at apply). Phase 2c restores the animation as a
DISPLAY-ONLY ghost that reproduces vanilla's collapse frame-for-frame while the
real state stays final underneath:

  * BattleUnit gains presentation-only display OVERRIDE fields (status/dir/fallPhase)
    that only UnitSprite/Map read (never serialized, never hashed). coopQueueDeathGhost
    seeds them to the pre-death STANDING pose at apply, so the unit keeps drawing
    STANDING (via the Map ghost draw, since it is tile-unlinked) until its turn.
  * BattlescapeGame::coopPollDeathGhosts (handleState, idle) starts the head ghost
    once the state queue is idle AND the display has caught up to that death's chain
    (`_clientDisplaySeq >= action_seq`, or a boundary/previous-side ghost) - so the
    collapse never plays before the killing shot's animation.
  * The ghost IS a UnitDieBState in a new GHOST mode (2nd ctor): pirouette->fall for a
    DIRECT hit, instant final frame for an INDIRECT (blast) / already-unconscious one,
    two extra frames, then it drops the override (revealing the real dead unit + the
    now-unhidden corpse/kit) and pops. It writes NO world state, sends nothing.
  * Map hides the ghost's minted corpse/kit ids (coopTopItemExcluding) until the
    collapse ends, and draws the ghost unit on its (now tile-less) footprint.

  * The RED lever (`death_ghost_disable`, same build, client): coopQueueDeathGhost
    reverts to the 2b stub - completes the ghost immediately, no animation, corpse
    visible at apply. deathGhosts stays EMPTY and no corpse is ever hidden.

SCENARIO (slow client so each ghost frame lasts long enough to sample):
  * a DIRECT-hit kill (heavy plasma, mode-0 corpse): the ghost pirouettes + falls;
    its corpse is hidden until the last frame, then revealed.
  * an INDIRECT kill (kill_unit_real with damage_type=DT_HE, FixRadius -1 ->
    isDirect() false): the ghost jumps straight to the final frame (no COLLAPSING /
    no pirouette).
  * a KNOCKOUT (stun rod): the victim ends UNCONSCIOUS on both machines; a ghost runs.

Asserts (same build, "ONCE green, ONCE red"):
  GREEN (default, ghost animation ON):
    - a death ghost was observed ACTIVE with status COLLAPSING (an animation ran)
    - the DIRECT victim's collapse progressed (fallPhase advanced past 0)
    - the INDIRECT victim's ghost carried direct==false and never showed COLLAPSING
      (it took the instant-frame path)
    - the direct victim's minted corpse was hidden from the draw set (battle_state
      .hiddenItemIds) while its ghost animated, and revealed after it completed
    - every ACTIVE ghost frame respected the start gate (displaySeq >= action_seq,
      or boundary / previous-side)
    - deathGhostsCompleted (client) == casualtiesApplied (client) at the end
    - the five buckets stay 0 (the ghost touched no hashed state), corpse censuses
      identical, the drift tripwire never fired
  RED (--red, death_ghost_disable on the client -> 2b stub):
    - deathGhosts stayed EMPTY the whole run and no corpse was ever hidden (the
      animation never ran) - while deathGhostsCompleted still climbed with the kills

Run:  python tools/coop_test/test_parallel_death_ghost.py [--seed N]
                 [--slow-client MS] [--red]
Exit 0 = the expected verdict for the selected mode held; 2 = it did not.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_endturn as PE
import test_parallel_soak as SOAK
import test_parallel_atomic_death as AT

PORT = "48012"
FIVE = ("terrain", "unitsCore", "items", "itemIdCtr", "unitsCombat")

STATUS_COLLAPSING = 5
STATUS_DEAD = 6
STATUS_UNCONSCIOUS = 7
DT_HE = 3  # high explosive: FixRadius -1 -> RuleDamageType::isDirect() == false


def bstate(gc):
    return gc.cmd({"cmd": "battle_state"})


def parallel(gc):
    return gc.cmd({"cmd": "parallel_state"})


def corpse_ids(gc):
    return {i["id"] for i in gc.ok({"cmd": "battle_items"})["items"]
            if "CORPSE" in i["type"].upper()}


def units_by_id(gc):
    return {u["id"]: u for u in bstate(gc)["units"]}


def capture(client, victim_ids, timeout, interval=0.02):
    """Rapidly sample the client while the death ghost(s) for `victim_ids` animate,
    recording the distinct display frames per victim, the hidden-item snapshots seen
    while any ghost was active, and the start-gate check per active frame.

    Returns a dict keyed by unit id with:
      frames            - ordered distinct {started,active,status,dir,fallPhase,direct,
                          bnd,sideSeq,actionSeq,displaySeq} snapshots for that ghost
      seen / gone       - the ghost appeared / then disappeared (completed)
    plus module-level aggregates on the returned dict under key None:
      hidden_ever       - any poll observed a non-empty battle_state.hiddenItemIds
      hidden_ids_active - union of hidden ids observed while ANY ghost was active
      ghost_ever        - any poll observed a non-empty deathGhosts list
    """
    per = {uid: {"frames": [], "seen": False, "gone": False} for uid in victim_ids}
    agg = {"hidden_ever": False, "hidden_ids_active": set(), "ghost_ever": False}
    deadline = time.time() + timeout
    while time.time() < deadline:
        ps = parallel(client)
        bs = bstate(client)
        hidden = set(bs.get("hiddenItemIds", []))
        ghosts = {g["unit_id"]: g for g in ps.get("deathGhosts", [])}
        dseq = ps.get("displaySeq")
        cur_side = ps.get("sideSeq")
        if ghosts:
            agg["ghost_ever"] = True
        if hidden:
            agg["hidden_ever"] = True
        any_active = any(g.get("active") for g in ghosts.values())
        if any_active:
            agg["hidden_ids_active"] |= hidden
        for uid, st in per.items():
            g = ghosts.get(uid)
            if g:
                st["seen"] = True
                snap = {k: g.get(k) for k in
                        ("started", "active", "status", "dir", "fallPhase",
                         "direct", "bnd", "sideSeq", "actionSeq")}
                snap["displaySeq"] = dseq
                snap["curSide"] = cur_side
                if not st["frames"] or st["frames"][-1] != snap:
                    st["frames"].append(snap)
            elif st["seen"]:
                st["gone"] = True
        seen_any = any(st["seen"] for st in per.values())
        if seen_any and all(st["gone"] for st in per.values() if st["seen"]):
            break
        time.sleep(interval)
    per[None] = agg
    return per


def start_gate_ok(frame):
    """The ghost may only be ACTIVE once the display caught up to its chain (or it is
    a boundary / previous-side ghost)."""
    if not frame.get("active"):
        return True
    if frame.get("bnd"):
        return True
    if frame.get("sideSeq") != frame.get("curSide"):
        return True
    ds, aseq = frame.get("displaySeq"), frame.get("actionSeq")
    return ds is not None and aseq is not None and ds >= aseq


DT_AP = 1  # armor-piercing: FixRadius 0 -> isDirect() true (the pirouette+fall path)


def stage_kill(host, used, damage_type):
    """kill_unit_real on a live soldier with an explicit damage type - DETERMINISTIC
    (raw damage, no to-hit roll, no display settle here) so the caller can capture the
    CLIENT ghost as it applies and animates. DT_AP is direct (pirouette+fall, mode-0
    corpse - AP IgnoreOverKill floors health at 0, so no overkill); DT_HE is indirect
    (instant final frame). Returns the victim id, or None."""
    live = [u for u in AT.live_soldiers(host) if u["id"] not in used]
    if not live:
        return None
    victim = live[0]["id"]
    used.add(victim)
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real",
                  "unit": victim, "damage_type": damage_type})
    if victim not in r.get("killed", []):
        return None
    return victim


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260824)
    ap.add_argument("--slow-client", type=int, default=300,
                    help="ms/frame on the client so each ghost frame lasts long enough "
                         "to sample the collapse sequence (default 300)")
    ap.add_argument("--red", action="store_true",
                    help="RED: set parallel_state {death_ghost_disable:true} on the "
                         "CLIENT - coopQueueDeathGhost reverts to the 2b stub (no "
                         "animation, corpse visible at apply)")
    args = ap.parse_args()

    host_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                 "skipNextTurnScreen": True, "EnableCoopParallelTurns": True}
    client_opts = {"battleXcomSpeed": args.slow_client, "battleAlienSpeed": args.slow_client,
                   "EnableCoopParallelTurns": False}
    host = GameClient("host", 48944, make_user_dir("deathghost_host", options=host_opts))
    client = GameClient("client", 48945, make_user_dir("deathghost_client", options=client_opts))
    for gc in (host, client):
        SOAK.write_battle_fixture(gc.user_dir)
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    TW.PORT = PORT
    PE.PORT = PORT
    fails = []
    try:
        TW.bring_up_battle(host, client, seed=args.seed)
        for gc in (host, client):
            gc.ok({"cmd": "set_seed", "seed": args.seed})
        assert bstate(host)["activeSync"] is True and bstate(client)["activeSync"] is False, \
            "host must own the battle simulation, client must be the replay peer"

        # the exe must carry the Phase 2c introspection or it predates this build.
        pc = parallel(client)
        for f in ("deathGhosts", "deathGhostsPending", "deathGhostsCompleted",
                  "deathGhostDisable"):
            assert f in pc, (
                f"parallel_state carries no `{f}` - bin/x64/Release/OpenXcom.exe predates "
                f"the Phase 2c build; rebuild it (serial, MP=false). fields: {sorted(pc)}")
        assert "hiddenItemIds" in bstate(client), \
            "battle_state carries no hiddenItemIds - the Phase 2c introspection is missing"

        # disable_ghost=False: THIS test measures the ghost, so it must stay ON. (Other
        # strict-burnin tests are state-focused and disable it - see enable_strict_burnin.)
        SOAK.enable_strict_burnin(host, client, disable_ghost=False)

        if args.red:
            client.cmd({"cmd": "parallel_state", "death_ghost_disable": True})
            assert parallel(client).get("deathGhostDisable") is True, \
                "the death_ghost_disable lever did not engage on the client"
            print("== RED: death_ghost_disable ON (client) - 2b stub, no animation ==")
        else:
            print("== GREEN: death-ghost animation ON ==")

        used = set()
        completed0 = parallel(client).get("deathGhostsCompleted", 0)

        # ---- DIRECT kill: pirouette + fall + corpse hide/reveal ----
        # Fire DETERMINISTICALLY on the (fast) host and DO NOT settle - capture the
        # (slow) client's ghost live as the death applies and the collapse plays.
        print("\n-- direct kill (DT_AP -> pirouette + fall, mode-0 corpse) --")
        corp_before = corpse_ids(client)
        pk_id = stage_kill(host, used, DT_AP)
        direct_cap = capture(client, [pk_id] if pk_id else [], timeout=30) if pk_id else {}
        corp_after = corpse_ids(client)
        new_corpse = corp_after - corp_before
        print(f"  victim={pk_id} new corpse id(s)={sorted(new_corpse)}")

        SOAK.settle_display(host, client, timeout=30)

        # ---- INDIRECT kill: instant final frame (no COLLAPSING) ----
        print("\n-- indirect kill (DT_HE -> instant frame) --")
        in_id = stage_kill(host, used, DT_HE)
        indirect_cap = capture(client, [in_id] if in_id else [], timeout=30) if in_id else {}
        print(f"  victim={in_id}")

        SOAK.settle_display(host, client, timeout=30)

        # ---- KNOCKOUT: ends UNCONSCIOUS ----
        print("\n-- knockout (stun rod -> UNCONSCIOUS) --")
        ko_id = AT.stage_knockout(host, client, used)
        ko_cap = capture(client, [ko_id] if ko_id else [], timeout=20) if ko_id else {}
        print(f"  victim={ko_id}")

        SOAK.settle_display(host, client, timeout=60)
        time.sleep(2)

        # ---- gather final state ----
        pcl = parallel(client)
        cas_applied = pcl.get("casualtiesApplied", 0)
        completed = pcl.get("deathGhostsCompleted", 0)
        pending_end = pcl.get("deathGhostsPending", 0)
        hidden_end = set(bstate(client).get("hiddenItemIds", []))
        sc = session.sync_check(host)
        buckets = {n: sc["buckets"].get(n, {}).get("mismatchCount", 0) for n in FIVE}
        total = sum(buckets.values())
        hc = sorted((i["id"], i["type"]) for i in host.ok({"cmd": "battle_items"})["items"]
                    if "CORPSE" in i["type"].upper())
        cc = sorted((i["id"], i["type"]) for i in client.ok({"cmd": "battle_items"})["items"]
                    if "CORPSE" in i["type"].upper())

        # aggregate observations over the three captures
        def agg_of(cap):
            return cap.get(None, {"hidden_ever": False, "hidden_ids_active": set(),
                                  "ghost_ever": False})
        ghost_ever = any(agg_of(c)["ghost_ever"] for c in (direct_cap, indirect_cap, ko_cap))
        # a ghost seen ACTIVE with status COLLAPSING anywhere (an animation ran)
        collapsing_seen = False
        gate_bad = []
        for cap in (direct_cap, indirect_cap, ko_cap):
            for uid, st in cap.items():
                if uid is None:
                    continue
                for fr in st["frames"]:
                    if fr.get("active") and fr.get("status") == STATUS_COLLAPSING:
                        collapsing_seen = True
                    if not start_gate_ok(fr):
                        gate_bad.append((uid, fr))

        print("\n== VERDICT ==")
        print(f"  five-bucket={buckets} (sum {total})")
        print(f"  casualtiesApplied={cas_applied} deathGhostsCompleted={completed} "
              f"(baseline {completed0}) pending_end={pending_end}")
        print(f"  ghost_ever={ghost_ever} collapsing_seen={collapsing_seen} "
              f"hidden_end={sorted(hidden_end)}")

        if args.red:
            # the 2b stub: no ghost ever queued, no corpse ever hidden.
            if ghost_ever:
                fails.append("RED: deathGhosts was populated under death_ghost_disable "
                             "- the stub must never queue an animating ghost")
            if any(agg_of(c)["hidden_ever"] for c in (direct_cap, indirect_cap, ko_cap)):
                fails.append("RED: a corpse/kit id was hidden under death_ghost_disable "
                             "- the stub must leave items visible at apply")
            if collapsing_seen:
                fails.append("RED: a COLLAPSING ghost frame was observed under the stub")
            if completed <= completed0:
                fails.append(f"VACUOUS RED: deathGhostsCompleted did not climb "
                             f"({completed0}->{completed}) - no casualty was applied, so "
                             f"the stub path was never exercised")
        else:
            if pk_id is None:
                fails.append("VACUOUS: could not stage the direct-hit kill")
            if in_id is None:
                fails.append("VACUOUS: could not stage the indirect kill")
            if ko_id is None:
                fails.append("VACUOUS: could not stage the knockout")
            if not ghost_ever:
                fails.append("no death ghost was ever observed in deathGhosts - the "
                             "animation machinery never ran")
            if not collapsing_seen:
                fails.append("no ACTIVE ghost frame showed status COLLAPSING - no collapse "
                             "animation played (only the instant stub?)")
            # DIRECT victim: the fall must have progressed past phase 0.
            if pk_id and direct_cap.get(pk_id):
                frames = direct_cap[pk_id]["frames"]
                active = [f for f in frames if f.get("active")]
                if not active:
                    fails.append(f"direct victim {pk_id}: no ACTIVE ghost frame captured")
                else:
                    maxphase = max((f.get("fallPhase", 0) for f in active), default=0)
                    saw_collapse = any(f.get("status") == STATUS_COLLAPSING for f in active)
                    if not (saw_collapse and maxphase > 0):
                        fails.append(f"direct victim {pk_id}: collapse did not progress "
                                     f"(saw_collapse={saw_collapse} maxFallPhase={maxphase}) "
                                     f"frames={frames}")
                # corpse hidden during, revealed after
                if new_corpse:
                    hid_active = agg_of(direct_cap)["hidden_ids_active"]
                    if not (new_corpse & hid_active):
                        fails.append(f"direct victim {pk_id}: its corpse {sorted(new_corpse)} "
                                     f"was never hidden while the ghost animated "
                                     f"(hidden-active={sorted(hid_active)})")
                    if new_corpse & hidden_end:
                        fails.append(f"direct victim {pk_id}: its corpse {sorted(new_corpse)} "
                                     f"is STILL hidden after the ghost completed")
            # INDIRECT victim: took the instant path (never COLLAPSING; direct==false).
            if in_id and indirect_cap.get(in_id):
                frames = indirect_cap[in_id]["frames"]
                if any(f.get("status") == STATUS_COLLAPSING for f in frames):
                    fails.append(f"indirect victim {in_id}: showed COLLAPSING - it should "
                                 f"jump straight to the final frame; frames={frames}")
                directs = {f.get("direct") for f in frames if f.get("active")}
                if directs and directs != {False}:
                    fails.append(f"indirect victim {in_id}: ghost.direct={directs}, expected "
                                 f"only False for a DT_HE (indirect) death")
            # KNOCKOUT victim: ends UNCONSCIOUS on BOTH machines.
            if ko_id:
                hu = units_by_id(host).get(ko_id, {})
                cu = units_by_id(client).get(ko_id, {})
                if hu.get("status") != STATUS_UNCONSCIOUS or cu.get("status") != STATUS_UNCONSCIOUS:
                    fails.append(f"knockout victim {ko_id}: status host={hu.get('status')} "
                                 f"client={cu.get('status')} (want {STATUS_UNCONSCIOUS})")
            if gate_bad:
                fails.append(f"start-gate violated: a ghost was ACTIVE before its chain was "
                             f"displayed (displaySeq < action_seq): {gate_bad[:3]}")
            if pending_end != 0:
                fails.append(f"deathGhostsPending={pending_end} at end - a ghost never "
                             f"finished animating")
            if completed != cas_applied:
                fails.append(f"deathGhostsCompleted ({completed}) != casualtiesApplied "
                             f"({cas_applied}) - not every applied casualty produced+"
                             f"completed a ghost")
            if hidden_end:
                fails.append(f"battle_state.hiddenItemIds not empty at end: {sorted(hidden_end)} "
                             f"- a corpse stayed hidden after all ghosts completed")
            bad = {b: v for b, v in buckets.items() if v > 0}
            if bad:
                fails.append(f"five-bucket mismatch {bad} FIRED - the ghost moved hashed "
                             f"state.\n    {session._sync_mismatch_lines(sc)}")
            if hc != cc:
                fails.append(f"corpse censuses differ: host {hc} vs client {cc}")
            for gc, tag in ((host, "host"), (client, "client")):
                if TW.desync_seen(gc):
                    fails.append(f"the PRD-P2 drift tripwire FIRED on the {tag}")
    except Exception as e:
        import traceback
        fails.append(f"[ERROR] {e}\n{traceback.format_exc()}")
    finally:
        for gc in (host, client):
            try:
                gc.cmd({"cmd": "quit"})
            except Exception:
                pass

    mode = "RED (death_ghost_disable)" if args.red else "GREEN (ghost animation ON)"
    if fails:
        print(f"\n==== death ghost Phase 2c [{mode}]: FAIL ====")
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print(f"\n  PASS [{mode}]")
    sys.exit(0)


if __name__ == "__main__":
    main()
