"""Regression test: an abandon-mission vote ends the battle on BOTH machines,
whichever player started the mission and whichever player asked for the vote.

Player report (X-Com Files, SEPARATE campaign): the client started a mission and
it was aborted. The host went back to the geoscape, the client stayed in the
battle with no way out, and a second ABORT opened the vote on the host, which was
already on the geoscape.

Each row starts a fresh campaign, enters one coop battle, has one player press
ABORT, the other vote YES, and requires both machines to reach the geoscape.

  S1 SEPARATE, the CLIENT starts the mission, the CLIENT asks for the abort.
  S2 SEPARATE, the CLIENT starts the mission, the HOST asks for the abort.
  S3 SEPARATE, the HOST starts the mission, the CLIENT asks for the abort (guard).
  H1 SHARED, the CLIENT commands the landing, the CLIENT asks for the abort (guard).
  H2 SHARED, the CLIENT commands the landing, the HOST asks for the abort (guard).

  * PASS (exit 0) / FAIL (exit 2: a row failed or a process crashed) /
    FAIL (exit 3: a precondition never held).

Env: OXC_TEST_CRAFT - the starting craft type to fly (default STR_SKYRANGER).
With X-Com Files loaded through the harness's OXC_TEST_EXTRA_MOD, use
STR_CIVILIAN_CAR.
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

CRAFT = os.environ.get("OXC_TEST_CRAFT", "STR_SKYRANGER")
DRAIN_TIMEOUT = 90


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
    raise Inconclusive(f"{gc.name}: no own base")


def transport(gc):
    for c in base0(gc)["crafts"]:
        if c["type"] == CRAFT:
            return c
    raise Inconclusive(f"{gc.name}: no {CRAFT} at the own base")


def spawn_site(gc):
    b = base0(gc)
    site = gc.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                  "deployment": "STR_TERROR_MISSION", "lon": b["lon"] + 0.35,
                  "lat": b["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})
    return site["site_id"], b


def wait_landing_prompt(starter, other):
    """Run both clocks until the starter's craft reaches the site and the landing
    prompt opens on the starter."""
    def landing():
        if has(starter, "ConfirmLandingState"):
            return True
        for gc in (starter, other):
            t = states(gc)[-1]
            if "CoopState" in t:
                gc.cmd({"cmd": "coop_dialog_back"})
            elif "GeoscapeState" not in t:
                gc.cmd({"cmd": "dismiss_popup"})
            gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None

    starter.wait_for(starter.name + " landing prompt", landing, timeout=120, interval=0.5)


def enter_tactical(host, client):
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
    for _ in range(20):
        if all(top(gc) == "BattlescapeState" for gc in (host, client)):
            break
        for gc in (host, client):
            if top(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(1.0)
    if not all(top(gc) == "BattlescapeState" for gc in (host, client)):
        raise Inconclusive(f"not both on the tactical map: host={top(host)} client={top(client)}")
    # Let the coop turn handshake settle before the abort.
    deadline = time.time() + 90
    while time.time() < deadline:
        turns = [gc.cmd({"cmd": "battle_state"}).get("coopTurn") for gc in (host, client)]
        if 2 in turns:
            break
        time.sleep(1.0)
    time.sleep(2)


def vote_abort(asker, voter):
    """ABORT on `asker`, YES on `voter`; returns once both saw the vote pass."""
    asker.ok({"cmd": "battle_action", "action": "abort"})

    def vote(gc, want):
        return gc.wait_for(
            f"{gc.name} abandon-mission vote {want}",
            lambda: (lambda s: s if (s.get(want) and (want != "active" or s.get("menuOpen")))
                     else None)(gc.ok({"cmd": "vote_state"})),
            timeout=25, interval=0.25)

    for gc in (asker, voter):
        v = vote(gc, "active")
        if v["action"] != "abandon_mission":
            raise Inconclusive(f"{gc.name}: ABORT opened the wrong vote: {v}")
    cast = voter.ok({"cmd": "vote_cast", "yes": True})
    if not cast.get("accepted"):
        raise Inconclusive(f"{voter.name}: vote_cast rejected: {cast}")
    for gc in (asker, voter):
        v = vote(gc, "finished")
        if not v.get("passed"):
            raise Inconclusive(f"{gc.name}: the abandon-mission vote did not pass: {v}")


def drain(gc, deadline):
    """Dismiss popups down to the geoscape, never popping a live BattlescapeState.
    A FINISHED vote menu left on top for 5 s is closed with its Close button, as a
    player would; finishBattle normally pops it itself."""
    finished_since = None
    while time.time() < deadline:
        t = top(gc)
        if t == "GeoscapeState":
            return True
        if t == "VoteMenu":
            if gc.cmd({"cmd": "vote_state"}).get("finished"):
                finished_since = finished_since or time.time()
                if time.time() - finished_since >= 5:
                    gc.cmd({"cmd": "vote_close"})
                    finished_since = None
        elif t != "BattlescapeState":
            gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.4)
    return False


def both_reach_geoscape(host, client):
    """Drain each machine to the geoscape. Returns (ok, detail)."""
    deadline = time.time() + DRAIN_TIMEOUT
    reached = {}
    for gc in (host, client):
        reached[gc.name] = drain(gc, deadline)
    detail = ", ".join(
        "%s %s (top %s, inBattle=%s)" % (gc.name, "geoscape" if reached[gc.name] else "STUCK",
                                         top(gc), gc.cmd({"cmd": "battle_state"}).get("inBattle"))
        for gc in (host, client))
    return all(reached.values()), detail


def second_abort_probe(host, client):
    """Diagnostic for the report's second symptom: if the client is still in the
    battle, press ABORT there again and record where the vote opens."""
    if not client.cmd({"cmd": "battle_state"}).get("inBattle"):
        return
    if top(client) == "VoteMenu":
        client.cmd({"cmd": "vote_close"})
    client.cmd({"cmd": "vote_clear_cooldown"})
    host.cmd({"cmd": "vote_clear_cooldown"})
    client.cmd({"cmd": "battle_action", "action": "abort"})
    time.sleep(3)
    for gc in (host, client):
        v = gc.cmd({"cmd": "vote_state"})
        print("  second ABORT: %s top=%s vote active=%s finished=%s menuOpen=%s"
              % (gc.name, top(gc), v.get("active"), v.get("finished"), v.get("menuOpen")))


def separate_row(results, row, tag, ports, starter_is_client, asker_is_client):
    host = GameClient("host", ports[0], make_user_dir(tag + "_host"))
    client = GameClient("client", ports[1], make_user_dir(tag + "_client"))
    host.spawn(); client.spawn()
    host.connect(timeout=300); client.connect(timeout=300)
    try:
        session.new_campaign(host, client, port=str(ports[2]))
        geo.wait_both_ready(host, client, timeout=120)
        geo.slow_clock(host, client)
        starter, other = (client, host) if starter_is_client else (host, client)
        site, b = spawn_site(starter)
        cid = transport(starter)["id"]
        starter.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
                    "lon": b["lon"] + 0.34, "lat": b["lat"] + 0.10, "dest": f"site:{site}",
                    "fuel": 999999, "lowFuel": False})
        wait_landing_prompt(starter, other)
        starter.ok({"cmd": "coop_mission_start"})
        enter_tactical(host, client)
        asker, voter = (client, host) if asker_is_client else (host, client)
        vote_abort(asker, voter)
        ok, detail = both_reach_geoscape(host, client)
        results[row] = (ok, detail)
        print(("PASS " if ok else "FAIL ") + row + ": " + detail)
        if not ok:
            second_abort_probe(host, client)
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception:
                pass
    return alive


def shared_row(results, row, tag, ports, asker_is_client):
    js = shared_fixture.bring_up(tag, ports)
    host, client = js.host, js.client
    try:
        geo.slow_clock(host, client)
        site, b = spawn_site(host)
        for gc in (host, client):
            gc.wait_for(gc.name + " sees the site",
                        lambda gc=gc: any(s["id"] == site for s in gc.ok({"cmd": "geo_state"})["missionSites"]) or None,
                        timeout=60, interval=0.5)
        cid = transport(host)["id"]
        r = client.ok({"cmd": "craft_order", "order": "target", "craft_id": cid,
                       "craft_type": transport(client)["type"], "site_id": site})
        if not (r.get("ok") or r.get("sent")):
            raise Inconclusive(f"client craft_order not sent: {r}")
        host.wait_for("host applied the client's craft order",
                      lambda: next((c for c in base0(host)["crafts"] if c["id"] == cid), {}).get("destKind") == "site" or None,
                      timeout=30, interval=0.5)
        host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
                 "lon": b["lon"] + 0.34, "lat": b["lat"] + 0.10, "dest": f"site:{site}",
                 "fuel": 999999, "lowFuel": False})

        def brokered():
            if has(client, "ConfirmLandingState"):
                return True
            host.cmd({"cmd": "geo_set_speed", "idx": 2})
            return None

        client.wait_for("client landing prompt", brokered, timeout=120, interval=0.5)
        client.ok({"cmd": "confirm_landing"})
        enter_tactical(host, client)
        asker, voter = (client, host) if asker_is_client else (host, client)
        vote_abort(asker, voter)
        ok, detail = both_reach_geoscape(host, client)
        results[row] = (ok, detail)
        print(("PASS " if ok else "FAIL ") + row + ": " + detail)
        if not ok:
            second_abort_probe(host, client)
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        js.shutdown()
    return alive


ROWS = {
    "S1": lambda r, sfx: separate_row(r, "S1 SEPARATE, client-started mission, client asks to abort",
                                 "cabs1" + sfx, (48941, 48942, 47981), True, True),
    "S2": lambda r, sfx: separate_row(r, "S2 SEPARATE, client-started mission, host asks to abort",
                                 "cabs2" + sfx, (48943, 48944, 47982), True, False),
    "S3": lambda r, sfx: separate_row(r, "S3 SEPARATE, host-started mission, client asks to abort",
                                 "cabs3" + sfx, (48945, 48946, 47983), False, True),
    "H1": lambda r, sfx: shared_row(r, "H1 SHARED, client-commanded landing, client asks to abort",
                               "cabh1" + sfx, (48947, 48948, 47984), True),
    "H2": lambda r, sfx: shared_row(r, "H2 SHARED, client-commanded landing, host asks to abort",
                               "cabh2" + sfx, (48949, 48950, 47985), False),
}


def main():
    wanted = sys.argv[1:] or list(ROWS)
    results = {}
    notes = []
    alive = True
    for i, key in enumerate(wanted):
        # A repeated row gets its own user folders so one run cannot overwrite
        # another run's logs.
        sfx = "" if wanted.index(key) == i else "_%d" % i
        try:
            alive = ROWS[key](results, sfx) and alive
        except Inconclusive as e:
            notes.append(f"{key} INCONCLUSIVE: {e}")
        except Exception as e:
            notes.append(f"{key} ERROR {type(e).__name__}: {e}")
            alive = False

    print("==== RESULT ====")
    for row, (ok, detail) in results.items():
        print(("PASS " if ok else "FAIL ") + row + ": " + detail)
    for n in notes:
        print(n)
    print("alive:", alive)
    if not alive:
        sys.exit(2)
    if not all(ok for ok, _ in results.values()):
        sys.exit(2)
    if notes:
        sys.exit(3)
    print("PASS: the abandon-mission vote ends the battle on both machines in every row")
    sys.exit(0)


if __name__ == "__main__":
    main()
