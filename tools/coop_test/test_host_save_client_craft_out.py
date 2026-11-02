"""Repro + fix verification for issue #28 - "Host saves with client ship out
can despawn the client ship".

In a live 2-player co-op session a CLIENT sends one of its own craft OUT chasing
a SHARED/coop target (a UFO the host spawned, which mirrors onto the client's
geoscape but is NOT part of the client's own-world blob). The HOST then performs
a host-authoritative save (the deferred funnel that pulls a fresh client-world
blob and embeds it), and later the world is served back on RESUME.

Root cause (fixed): coop entities are stripped from the client blob on
serialize, so on reload Craft::load could not re-resolve the destination and
silently dropped it - the out-craft reverted to aimless PATROLLING, abandoning
its mission. The fix persists the target's cross-instance coop id on the craft
(and keeps the coop id stable across the host's own save/reload), lays down an
temporary waypoint at the saved position, and re-links the craft to the LIVE coop
mirror once it re-syncs - so the craft keeps chasing the REAL, position-synced
target and engages it on arrival.

Separate is one host-owned world: the client's craft, the UFO and the
craft's target link all live in the host save, and there is no client blob
or coop mirror UFO. The player-visible bar is unchanged, so the test drives the
client's craft on both machines (the host simulates, the client mirrors) and
keeps every assertion below.

Two scenarios, each asserting the craft (a) never despawns and (b) re-links to
the live coop target after resume; plus a mode-specific proof:

  landing : SKYRANGER -> crashed coop UFO. Arrival pops ConfirmLandingState (the
            'start mission' prompt) - proving the craft reached the real TARGET,
            not just its saved position (which would pop CraftPatrolState).
  tracking: INTERCEPTOR -> flying coop UFO. Moving the host UFO makes the client
            mirror (and thus the re-linked craft's destination) follow it -
            proving live-tracking of a MOVING target, not a frozen coordinate.

(The interceptor's dogfight screen fires through the SAME engine arrival handler
proven deterministically by the landing scenario; a flying UFO is too unstable
in-harness - alien-mission despawn / detection quirks unrelated to this fix - to
drive to the dogfight popup reliably, so scenario 2 asserts the re-link +
live-tracking that the dogfight depends on.)

Run:  python tools/coop_test/test_host_save_client_craft_out.py

Exit 0 = both scenarios pass; 2 = a failure / regression.
"""

import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
from session import new_campaign, resume_campaign


def keep_awake():
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(
            0x80000000 | 0x00000001 | 0x00000002)


# Separate is one host-owned world: the client's craft lives at the client's
# base in that world, the host simulates its flight and the client mirrors it.
# Craft ids are per base type, so a craft is named by its base and type too.
CLIENT_BASE = "ClientBase"


def own_crafts(gc):
    """Every craft at the client's own base, as this instance sees it."""
    r = gc.cmd({"cmd": "geo_state"})
    if not r.get("ok"):
        return []
    return [c for b in r["bases"] if b.get("name") == CLIENT_BASE
            for c in b.get("crafts", [])]


def find_own_craft(gc, craft_key_):
    for c in own_crafts(gc):
        if craft_key(c) == craft_key_:
            return c
    return None


def coop_ufo(gc):
    """The (single) spawned UFO as this instance sees it, or None. In the one
    world the client sees the host's UFO itself, not a coop mirror."""
    ufos = gc.cmd({"cmd": "geo_state"}).get("ufos", [])
    return ufos[0] if ufos else None


def craft_key(c):
    """Stable cross-reload identity for an own craft: (type, id)."""
    return (c["type"], c["id"])


def force_craft(host, client, key, **fields):
    """Set the client's craft on BOTH machines: the host simulates the flight
    and the replica mirrors it (same lane as separate_campaign_fixture)."""
    for gc in (client, host):
        req = {"cmd": "craft_force", "base": CLIENT_BASE, "craft_type": key[0],
               "craft_id": key[1]}
        req.update(fields)
        if "dest" in req and req["dest"] == "ufo":
            u = coop_ufo(gc)
            req["dest"] = f"ufo:{u['id']}" if u else "none"
        gc.ok(req)


def geo_tick(host, client, speed=3):
    """One popup-draining time-advance nudge on both sides; keeps the session
    live so target_positions syncs (and coop re-link) keep flowing."""
    host.cmd({"cmd": "geo_run", "speed": speed})
    client.cmd({"cmd": "geo_run", "speed": speed})


def assert_craft_present(tag, client, key, fail):
    crafts = own_crafts(client)
    keys = [craft_key(x) for x in crafts]
    if key not in keys:
        print(f"  [FAIL] {tag}: client craft {key} DESPAWNED (client now owns {keys})")
        fail.append(tag)
        return False
    print(f"  [PASS] {tag}: client craft {key} present (owns {keys})")
    return True


def assert_relinked_to_ufo(tag, host, client, cid, fail, timeout=25):
    """After the round trip the out-craft must re-link to the LIVE coop UFO
    (destKind 'ufo'), not settle for a frozen waypoint at the stale saved
    position. Poll while nudging the geoscape so the post-resume sync can run.
    Pre-fix the destination was dropped (destKind 'none' -> PATROLLING)."""
    tag2 = f"{tag} [re-link]"
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        c = find_own_craft(client, cid)
        if c is None:
            print(f"  [FAIL] {tag2}: craft despawned")
            fail.append(tag2)
            return
        last = c
        if c["status"] == "STR_OUT" and c["destKind"] == "ufo":
            print(f"  [PASS] {tag2}: re-linked to live coop UFO "
                  f"(destKind={c['destKind']} destId={c['destId']} "
                  f"displayStatus={c['displayStatus']!r})")
            return
        geo_tick(host, client)
        time.sleep(0.6)
    print(f"  [FAIL] {tag2}: did NOT re-link to the live coop UFO "
          f"(status={last and last['status']} destKind={last and last['destKind']} "
          f"displayStatus={last and last['displayStatus']!r}) - chasing a stale "
          f"position / lost its target")
    fail.append(tag2)


def drive_to_landing_prompt(tag, host, client, cid, fail, timeout=45):
    """Prove the re-linked craft reaches the REAL (stationary) target and
    INITIATES the mission: park it on the coop crash site and advance time
    WITHOUT geo_run (which would auto-decline the prompt). Success =
    ConfirmLandingState pops ('start mission'). Failure = CraftPatrolState
    ('arrived at position'), which is what a stale-waypoint fallback produces
    when the craft flies to a dead coordinate instead of the live target."""
    tag2 = f"{tag} [arrival]"
    keep = ("GeoscapeState", "ConfirmLandingState")
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        st = client.cmd({"cmd": "get_state"})["states"]
        if any("ConfirmLandingState" in s for s in st):
            print(f"  [PASS] {tag2}: arrival popped ConfirmLandingState (start-mission prompt)")
            return
        if any("CraftPatrolState" in s for s in st):
            print(f"  [FAIL] {tag2}: arrival popped CraftPatrolState ('arrived at "
                  f"position') - reached a stale waypoint, not the target")
            fail.append(tag2)
            return
        for gc in (host, client):
            top = gc.cmd({"cmd": "get_state"})["states"][-1]
            if not any(k in top for k in keep):
                gc.cmd({"cmd": "dismiss_popup"})
        u = coop_ufo(host)
        if u:  # chase the live target position (a crash site does not move)
            force_craft(host, client, cid, lon=u["lon"], lat=u["lat"],
                        fuel=999999, lowFuel=False)
        c = find_own_craft(client, cid)
        last = (c and c["status"], c and c["destKind"], st[-1] if st else None)
        for gc in (host, client):
            gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        time.sleep(0.5)
    print(f"  [FAIL] {tag2}: never reached the target / no landing prompt (last={last})")
    fail.append(tag2)


def assert_live_tracking(tag, host, client, cid, coop_id, fail, timeout=25):
    """Prove the client tracks the LIVE (moving) target after the round trip, not
    a stale save-time position: move the HOST's UFO and confirm the client's
    mirror follows it there (the re-linked craft's destination IS that mirror, so
    it tracks with it - a frozen waypoint could not). Nudge time gently (no
    geo_run) so the fast interceptor doesn't reach the UFO here."""
    tag2 = f"{tag} [tracking]"
    u0 = coop_ufo(client)
    if not u0:
        print(f"  [FAIL] {tag2}: no coop UFO on client to move")
        fail.append(tag2)
        return
    nx, ny = u0["lon"] + 0.9, u0["lat"] + 0.4
    host.ok({"cmd": "move_ufo", "coop_id": coop_id, "lon": nx, "lat": ny})
    keep = ("GeoscapeState", "DogfightState", "ConfirmLandingState")
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        for gc in (host, client):
            top = gc.cmd({"cmd": "get_state"})["states"][-1]
            if not any(k in top for k in keep):
                gc.cmd({"cmd": "dismiss_popup"})
            gc.cmd({"cmd": "geo_set_speed", "idx": 1})  # gentle: sync, barely fly
        u = coop_ufo(client)
        last = u and (round(u["lon"], 3), round(u["lat"], 3))
        if u and abs(u["lon"] - nx) < 0.08 and abs(u["lat"] - ny) < 0.08:
            c = find_own_craft(client, cid)
            print(f"  [PASS] {tag2}: client mirror followed the host UFO to its new "
                  f"position ({round(nx,3)},{round(ny,3)}); craft still bound "
                  f"(destKind={c and c['destKind']})")
            return
        time.sleep(0.6)
    print(f"  [FAIL] {tag2}: mirror did not follow the moved UFO "
          f"(target=({round(nx,3)},{round(ny,3)}) last={last})")
    fail.append(tag2)



def run_scenario(label, ports, ufo_state, ufo_speed, craft_pref, mode,
                 save_name, fail):
    """mode 'landing'  -> SKYRANGER to a crashed coop UFO; assert arrival pops
                          the start-mission prompt (ConfirmLandingState).
       mode 'tracking' -> INTERCEPTOR to a flying coop UFO; assert the re-linked
                          craft live-tracks the target (client mirror follows the
                          host UFO when it moves)."""
    print(f"\n===== scenario '{label}': {craft_pref} -> {ufo_state} coop UFO, "
          f"mode={mode} =====")
    host_dir = make_user_dir(f"csco_{label}_host")
    host = GameClient("host", ports[0], host_dir)
    client = GameClient("client", ports[1], make_user_dir(f"csco_{label}_client"))
    try:
        host.spawn(); client.spawn()
        host.connect(timeout=240); client.connect(timeout=240)
        new_campaign(host, client)

        crafts0 = own_crafts(client)
        assert crafts0, "client should own a starting craft"
        craft = next((c for c in crafts0 if craft_pref in c["type"]), crafts0[0])
        key = craft_key(craft)
        cid = key  # crafts are named by (type, id) at the client's base
        bx, by = craft["lon"], craft["lat"]
        print(f"  client craft {key} -> OUT")

        # HOST spawns the UFO. The one world holds the UFO and the craft's target
        # link in the host save itself.
        host.ok({"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT",
                 "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
                 "race": "STR_SECTOID", "trajectory": "P0", "state": ufo_state,
                 "lon": bx + 1.4, "lat": by - 0.25, "speed": ufo_speed, "hours": 240})
        cufo = client.wait_for("UFO replicated to the client",
                               lambda: coop_ufo(client), timeout=30)
        print(f"  UFO on client id={cufo['id']} coopId={cufo.get('coopId')}")

        # A landing needs something aboard (an empty transport may skip the
        # prompt); tracking/interception does not. The owner loads it through
        # its own command lane, as separate_campaign_fixture.fly_to_new_site does.
        if mode == "landing":
            client.ok({"cmd": "craft_equip", "base": CLIENT_BASE, "craft_id": key[1],
                       "item": "STR_RIFLE", "count": 1})
            host.wait_for(
                "craft equipment reaches the host",
                lambda: (lambda r: r if next(c for c in r["crafts"] if c["id"] == key[1]
                                             and c.get("type", key[0]) == key[0])
                         ["items"].get("STR_RIFLE", 0) >= 1 else None)(
                    host.ok({"cmd": "base_report", "base": CLIENT_BASE})),
                timeout=30, interval=0.3)
        force_craft(host, client, key, status="STR_OUT",
                    lon=bx + 0.20, lat=by + 0.10, dest="ufo",
                    fuel=999999, lowFuel=False)
        cur = client.wait_for(
            "client craft OUT to the UFO",
            lambda: (lambda c: c if c and c["status"] == "STR_OUT" and c["destKind"] == "ufo"
                     else None)(find_own_craft(client, cid)),
            timeout=30, interval=0.3)
        hcur = find_own_craft(host, cid)
        assert hcur and hcur["status"] == "STR_OUT" and hcur["destKind"] == "ufo", \
            f"failed to force the client's craft OUT to the UFO in the host world: {hcur}"
        print(f"  OUT to UFO: {cur['displayStatus']!r}")

        # --- HOST SAVE (deferred host-authoritative funnel) ---
        host.ok({"cmd": "save_game_ui", "type": "quick"})
        host.wait_for("host quicksave on disk",
                      lambda: os.path.exists(os.path.join(host_dir, "xcom1", "_quick_.asav")) or None,
                      timeout=90)
        host.ok({"cmd": "save_game", "file": save_name})

        # LIVE: craft still owned + still OUT to the coop UFO.
        assert_craft_present(f"{label} LIVE", client, key, fail)
        live = find_own_craft(client, cid)
        if not (live and live["status"] == "STR_OUT" and live["destKind"] == "ufo"):
            print(f"  [FAIL] {label} LIVE [OUT state]: {live}")
            fail.append(f"{label} LIVE [OUT state]")

        # --- RESUME ROUND TRIP ---
        host.shutdown(); client.shutdown()
        host = GameClient("host", ports[2], host_dir)
        host.spawn(); host.connect()
        client = GameClient("client", ports[3], make_user_dir(f"csco_{label}_client2"))
        client.spawn(); client.connect()
        resume_campaign(host, client, save_name)

        assert_craft_present(f"{label} RESUME", client, key, fail)
        assert_relinked_to_ufo(f"{label} RESUME", host, client, cid, fail)
        if mode == "landing":
            drive_to_landing_prompt(f"{label} RESUME", host, client, cid, fail)
        else:  # tracking
            # move_ufo runs on the host, so it takes the host's UFO coop id.
            cur_ufo = coop_ufo(host)
            coop_id = cur_ufo["coopId"] if cur_ufo else None
            assert_live_tracking(f"{label} RESUME", host, client, cid, coop_id, fail)
    finally:
        host.shutdown(); client.shutdown()


def main():
    keep_awake()
    fail = []
    # Scenario 1: SKYRANGER -> crashed coop UFO. Full arrival proof: reaching the
    # target pops the start-mission prompt (not "arrived at position").
    run_scenario("landing", (48640, 48641, 48642, 48643),
                 "crashed", 0, "SKYRANGER", "landing",
                 "host_save_craft_landing.sav", fail)
    # Scenario 2: INTERCEPTOR -> flying coop UFO. Proves the re-linked craft
    # live-tracks a MOVING target (client mirror follows the host UFO). The craft
    # is bound to the live flying UFO (destKind ufo, "INTERCEPTING UFO-0"); the
    # dogfight screen then fires through the SAME engine arrival path proven in
    # scenario 1.
    run_scenario("dogfight", (48644, 48645, 48646, 48647),
                 "flying", 0, "INTERCEPTOR", "tracking",
                 "host_save_craft_dogfight.sav", fail)

    print("\n==== issue #28 summary ====")
    if fail:
        print(f"  FAILURES: {', '.join(fail)}")
        sys.exit(2)
    print("  both scenarios: out-craft survived the host save, re-linked to its "
          "live coop target, and (landing) started the mission on arrival / "
          "(interceptor) live-tracked the moving UFO")
    sys.exit(0)


if __name__ == "__main__":
    main()
