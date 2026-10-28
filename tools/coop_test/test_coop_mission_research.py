"""Regression test: research unlocked by a mission outcome reaches the right players.

An alien deployment can unlock research when its mission site expires on its own
(unlockedResearchOnDespawn) or when the battle there is won or lost
(unlockedResearch / unlockedResearchOnFailure); SavedGame::handleResearchUnlockedByMissions
adds the topic, its lookup and a random getOneFree bonus. Only the world that owns
the mission runs it. Owner rules (2026-10-06):
  * SEPARATE campaign, shared research (research sync on): both players learn the
    same research item, bonus included, and can read the report.
  * SEPARATE campaign, separate research (sync off): only the owning player learns it.
  * SHARED campaign: one world; both machines hold the same research.

Fixture mod Coop_ResearchSync_Test makes STR_TERROR_MISSION unlock
STR_COOP_RS_DESPAWN_TOPIC on expiry and STR_COOP_RS_FAIL_TOPIC on failure, each with
four getOneFree bonuses (STR_COOP_RS_FREE_1..8).

Rows (the host owns every site):
  M1 SEPARATE, shared research: a site expires -> the client learns the topic and
     the host's bonus.
  M2 SEPARATE, shared research: a coop battle there is aborted (mission failure) ->
     the client learns the topic and the host's bonus.
  M3 SEPARATE, separate research: a site expires -> the client learns nothing (guard).
  M4 SHARED: a site expires, then a battle is aborted -> both machines hold the same
     topics and bonuses (guard).

  * PASS (exit 0) / FAIL (exit 2: a row failed or a process crashed) /
    FAIL (exit 3: a precondition never held).
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, HERE)
import session  # noqa: E402
import geo  # noqa: E402
import shared_fixture  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

MOD = os.path.join(HERE, "mods", "Coop_ResearchSync_Test")
DESPAWN, FAIL = "STR_COOP_RS_DESPAWN_TOPIC", "STR_COOP_RS_FAIL_TOPIC"
FREE = {"STR_COOP_RS_FREE_%d" % i for i in range(1, 9)}


class Inconclusive(Exception):
    pass


def states(gc):
    return gc.cmd({"cmd": "get_state"})["states"]


def has(gc, name):
    return any(name in s for s in states(gc))


def top(gc):
    return states(gc)[-1].split("::")[-1]


def base0(gc):
    for b in gc.ok({"cmd": "geo_state"})["bases"]:
        if not b.get("coopBase") and not b.get("coopIcon"):
            return b
    raise Inconclusive("no own base")


def known(gc):
    return set(gc.ok({"cmd": "geo_state"})["discoveredResearch"])


def gained(gc, before, topic):
    """The topic and the bonus this machine learned since `before`."""
    new = known(gc) - before
    return (topic in new, sorted(new & FREE))


def spawn_site(host, hours):
    b = base0(host)
    return host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                    "deployment": "STR_TERROR_MISSION", "lon": b["lon"] + 0.35,
                    "lat": b["lat"] + 0.10, "race": "STR_SECTOID", "hours": hours})["site_id"]


def expire_site(host, client):
    """A 1-hour site expires on its own; returns what each machine learned."""
    geo.slow_clock(host, client)
    before = {gc.name: known(gc) for gc in (host, client)}
    spawn_site(host, 1)
    geo.skip_ingame_time(host, client, minutes=4 * 60, speed_idx=4, real_timeout=90, stuck_timeout=40)
    geo.slow_clock(host, client)
    time.sleep(3)
    for gc in (host, client):
        geo.drain_popups(gc)
    return {gc.name: gained(gc, before[gc.name], DESPAWN) for gc in (host, client)}


def abort_battle(host, client, shared):
    """Fly the host's Skyranger to a terror site, enter the coop battle on both
    machines, abort it (mission failure); returns what each machine learned."""
    b0 = base0(host)
    cid = next(c for c in b0["crafts"] if "SKYRANGER" in c["type"])["id"]
    site = spawn_site(host, 240)
    host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT", "lon": b0["lon"] + 0.34,
             "lat": b0["lat"] + 0.10, "dest": f"site:{site}", "fuel": 999999, "lowFuel": False})

    def landing():
        if has(host, "ConfirmLandingState"):
            return True
        t = states(host)[-1]
        if "CoopState" in t:
            host.cmd({"cmd": "coop_dialog_back"})
        elif "GeoscapeState" not in t:
            host.cmd({"cmd": "dismiss_popup"})
        host.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None

    host.wait_for("landing prompt", landing, timeout=120, interval=0.5)
    host.ok({"cmd": "confirm_landing" if shared else "coop_mission_start"})
    for gc in (host, client):
        gc.wait_for(gc.name + " in battle",
                    lambda gc=gc: gc.cmd({"cmd": "battle_state"}).get("inBattle") or None,
                    timeout=180, interval=1.0)
    for gc in (host, client):
        gc.wait_for(gc.name + " briefing", lambda gc=gc: has(gc, "BriefingState") or None,
                    timeout=120, interval=0.5)
        gc.ok({"cmd": "close_briefing"})
    for gc in (host, client):
        gc.wait_for(gc.name + " inventory", lambda gc=gc: has(gc, "InventoryState") or None,
                    timeout=120, interval=0.5)
        gc.ok({"cmd": "battle_inventory", "action": "ok"})
    for _ in range(15):
        if all(top(gc) == "BattlescapeState" for gc in (host, client)):
            break
        for gc in (host, client):
            if top(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(1.0)
    host.wait_for("coop turn", lambda: (host.cmd({"cmd": "battle_state"}).get("coopTurn") == 2) or None,
                  timeout=90, interval=1.0)
    time.sleep(2)
    before = {gc.name: known(gc) for gc in (host, client)}
    session.coop_abort_battle(host, client)
    time.sleep(3)
    for gc in (host, client):
        geo.drain_popups(gc)
    return {gc.name: gained(gc, before[gc.name], FAIL) for gc in (host, client)}


def same_for_both(r, host, client, what):
    h, c = r[host.name], r[client.name]
    if not h[0] or len(h[1]) != 1:
        raise Inconclusive(f"{what}: the host did not learn the topic with one bonus: {h}")
    return h == c, f"host={h} client={c}"


def separate_session(results, sync):
    opts = {"EnableResearchSync": sync}
    tag = "mres" if sync else "mresoff"
    host = GameClient("host", 48621, make_user_dir(tag + "_host", mods=[MOD], options=opts))
    client = GameClient("client", 48622, make_user_dir(tag + "_client", mods=[MOD], options=opts))
    host.spawn(); client.spawn()
    host.connect(); client.connect()
    try:
        session.new_campaign(host, client, port="47623" if sync else "47624")
        geo.wait_both_ready(host, client)
        r = expire_site(host, client)
        if sync:
            results["M1 SEPARATE shared research, site expiry"] = same_for_both(r, host, client, "M1")
            r = abort_battle(host, client, shared=False)
            results["M2 SEPARATE shared research, battle lost"] = same_for_both(r, host, client, "M2")
        else:
            if not r[host.name][0]:
                raise Inconclusive(f"M3: the host did not learn the topic: {r}")
            results["M3 SEPARATE separate research, site expiry"] = (
                r[client.name] == (False, []), f"host={r[host.name]} client={r[client.name]}")
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception:
                pass
    return alive


def shared_session(results):
    js = shared_fixture.bring_up("mresshr", (48625, 48626, 47627), mods=[MOD])
    host, client = js.host, js.client
    try:
        r = expire_site(host, client)
        ok1, d1 = same_for_both(r, host, client, "M4 expiry")
        r = abort_battle(host, client, shared=True)
        ok2, d2 = same_for_both(r, host, client, "M4 battle")
        results["M4 SHARED, site expiry + battle lost"] = (ok1 and ok2, f"expiry {d1}; battle {d2}")
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        js.shutdown()
    return alive


def main():
    results = {}
    note = None
    alive = True
    try:
        alive = separate_session(results, True) and alive
        alive = separate_session(results, False) and alive
        alive = shared_session(results) and alive
    except Inconclusive as e:
        note = "INCONCLUSIVE: " + str(e)
    except Exception as e:
        note = f"ERROR {type(e).__name__}: {e}"
        alive = False

    print("==== RESULT ====")
    for row, (ok, detail) in results.items():
        print(("PASS " if ok else "FAIL ") + row + ": " + detail)
    print("alive:", alive, "| note:", note)
    if not alive:
        sys.exit(2)
    if note:
        sys.exit(3)
    if not all(ok for ok, _ in results.values()):
        sys.exit(2)
    print("PASS: mission-outcome research reaches the right players in every mode")
    sys.exit(0)


if __name__ == "__main__":
    main()
