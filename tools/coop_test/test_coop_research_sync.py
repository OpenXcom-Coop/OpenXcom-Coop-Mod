"""Regression test: SEPARATE research sync makes a discovery a discovery for BOTH players.

With "Research Sync" on (the default), a research completion on one player is
mirrored to the other. The receiver used to add only the main topic, so:
  * the getOneFree bonus topic never reached it, and VIEW REPORTS opened nothing
    for the bonus (the article requires the topic);
  * a topic's lookup never reached it, and VIEW REPORTS opened nothing for a
    topic whose article lives on its lookup;
  * its own running project of the same topic kept running, then completed a
    second time and gave the first player a duplicate popup;
  * a completion that brought it nothing new still popped "Research Completed".
The receiver now applies the completion the way OXCE applies any discovery
(topic + lookup + bonus, then SavedGame::handlePrimaryResearchSideEffects).

Rows (vanilla rules, SEPARATE campaign, research sync on):
  R1 bonus   host researches STR_SECTOID_ENGINEER (getOneFree: UFO types). The
             client learns the topic AND the host's bonus, and its VIEW REPORTS
             opens the bonus article.
  R2 lookup  host researches STR_SECTOID_CORPSE (lookup STR_SECTOID_AUTOPSY). The
             client learns the lookup, and its VIEW REPORTS opens that article.
  R3 dup     both research STR_LASER_WEAPONS; the host finishes first. The
             client's own project is removed (nothing left to gain from it).
  R4 keep    both research STR_SECTOID_ENGINEER; the host finishes first. The
             client's project stays: the topic still has undiscovered getOneFree
             rewards (vanilla rule). Guard row: green before and after the fix.
  R5 quiet   host re-researches STR_SECTOID_CORPSE, which both players already
             know. The client gets no "Research Completed" popup.
  R6 items   host researches STR_COOP_RS_SPAWNS_ITEM (mod Coop_ResearchSync_Test,
             spawnedItem STR_MEDI_KIT). The client learns the topic but gets no
             medi-kit: a research-spawned item goes only to the player who did the
             research (owner ruling, 2026-10-06).

  * PASS (exit 0): every row holds.
  * FAIL (exit 2): a row failed (the bug) or a game process crashed.
  * FAIL (exit 3): a precondition never held; the test proved nothing.
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
from harness import GameClient, make_user_dir  # noqa: E402

PORT = "47966"
MOD = os.path.join(HERE, "mods", "Coop_ResearchSync_Test")
DAY = 26 * 60
# STR_SECTOID_ENGINEER's getOneFree list (bin/standard/xcom1/research.rul)
ENGINEER_FREE = {"STR_SMALL_SCOUT", "STR_MEDIUM_SCOUT", "STR_LARGE_SCOUT", "STR_HARVESTER",
                 "STR_ABDUCTOR", "STR_TERROR_SHIP", "STR_BATTLESHIP", "STR_SUPPLY_SHIP"}


class Inconclusive(Exception):
    pass


def known(gc):
    return set(gc.ok({"cmd": "geo_state"}).get("discoveredResearch", []))


def projects(gc):
    g = gc.ok({"cmd": "geo_state"})
    for b in g["bases"]:
        if not b["coopBase"] and not b["coopIcon"]:
            return [r["name"] for r in b["research"]]
    return []


def medikits(gc):
    """STR_MEDI_KIT in this player's own base: in stores plus on the way in."""
    g = gc.ok({"cmd": "geo_state"})
    for b in g["bases"]:
        if not b["coopBase"] and not b["coopIcon"]:
            return b["items"].get("STR_MEDI_KIT", 0) + sum(
                t["qty"] for t in b["transfers"] if t.get("rule") == "STR_MEDI_KIT")
    return 0


def drain(gc):
    """Close every popup on gc; press VIEW REPORTS on research popups. Returns a
    list of what was seen: 'RC' per research popup, 'article:<id>' per article."""
    seen = []
    for _ in range(30):
        top = geo.top_state(gc)
        if not top or top.endswith("GeoscapeState"):
            break
        if "ResearchCompleteState" in top:
            gc.ok({"cmd": "dismiss_popup", "view_reports": True})
            seen.append("RC")
            continue
        r = gc.cmd({"cmd": "dismiss_popup"})
        if not r.get("ok"):
            break  # a WAIT dialog closes on its own
        seen.append("article:" + r["article"] if r.get("article") else r.get("handled", top))
    return seen


def advance(host, client, minutes, settle=3.0):
    """Advance the shared clock by `minutes`, draining both sides, then keep
    draining for `settle` seconds so a sync packet that lands late is seen."""
    seen = {host.name: [], client.name: []}
    start = geo.game_minutes(host)
    deadline = time.time() + 120
    while time.time() < deadline:
        for gc in (host, client):
            seen[gc.name] += drain(gc)
        now = geo.game_minutes(host)
        if now is not None and now - start >= minutes:
            break
        # speed 4 (1 hour per step): at speed 5 the host clock overwrites the
        # SEPARATE client's mid-step and the client's daily tick can be skipped
        # or doubled.
        for gc in (host, client):
            if geo.on_geoscape(gc):
                gc.cmd({"cmd": "geo_set_speed", "idx": 4})
        time.sleep(0.4)
    geo.slow_clock(host, client)
    t_end = time.time() + settle
    while time.time() < t_end:
        for gc in (host, client):
            seen[gc.name] += drain(gc)
        time.sleep(0.3)
    return seen


def start(gc, topic, cost):
    gc.ok({"cmd": "start_research", "topic": topic, "cost": cost, "scientists": 1})


def main():
    host = GameClient("host", 48991, make_user_dir("rsync_host", mods=[MOD]))
    client = GameClient("client", 48992, make_user_dir("rsync_client", mods=[MOD]))
    host.spawn(); client.spawn()
    host.connect(); client.connect()
    results = {}
    note = None
    try:
        session.new_campaign(host, client, port=PORT)
        geo.wait_both_ready(host, client)

        # R1 bonus
        geo.slow_clock(host, client)
        before = known(host)
        start(host, "STR_SECTOID_ENGINEER", 1)
        seen = advance(host, client, DAY)
        gained = known(host) - before
        bonus = sorted(gained & ENGINEER_FREE)
        if "STR_SECTOID_ENGINEER" not in gained or len(bonus) != 1:
            raise Inconclusive(f"R1: host did not complete the topic with one bonus: gained={sorted(gained)}")
        bonus = bonus[0]
        ck = known(client)
        missing = sorted(gained - ck)  # topic, its lookup STR_SECTOID and the bonus
        ok = not missing and "article:" + bonus in seen[client.name]
        results["R1 bonus"] = (ok, f"host gained={sorted(gained)} missing on client={missing} "
                                   f"client popups={seen[client.name]}")

        # R2 lookup
        start(host, "STR_SECTOID_CORPSE", 1)
        seen = advance(host, client, DAY)
        if "STR_SECTOID_AUTOPSY" not in known(host):
            raise Inconclusive("R2: host never learned STR_SECTOID_AUTOPSY")
        ck = known(client)
        ok = "STR_SECTOID_AUTOPSY" in ck and "article:STR_SECTOID_AUTOPSY" in seen[client.name]
        results["R2 lookup"] = (ok, f"client knows lookup={'STR_SECTOID_AUTOPSY' in ck} "
                                    f"client popups={seen[client.name]}")

        # R3 duplicate project removed
        start(host, "STR_LASER_WEAPONS", 1)
        start(client, "STR_LASER_WEAPONS", 100000)
        seen = advance(host, client, DAY)
        if "STR_LASER_WEAPONS" not in known(client):
            raise Inconclusive("R3: research sync never delivered STR_LASER_WEAPONS")
        cp = projects(client)
        results["R3 dup"] = ("STR_LASER_WEAPONS" not in cp, f"client projects={cp}")

        # R4 repeatable project kept
        start(host, "STR_SECTOID_ENGINEER", 1)
        start(client, "STR_SECTOID_ENGINEER", 100000)
        seen = advance(host, client, DAY)
        cp = projects(client)
        results["R4 keep"] = ("STR_SECTOID_ENGINEER" in cp, f"client projects={cp}")

        # R5 nothing new -> no popup on the receiver
        start(host, "STR_SECTOID_CORPSE", 1)
        seen = advance(host, client, DAY)
        if "RC" not in seen[host.name]:
            raise Inconclusive(f"R5: host never completed the repeat: {seen[host.name]}")
        results["R5 quiet"] = ("RC" not in seen[client.name], f"client popups={seen[client.name]}")

        # R6 a research-spawned item stays with the researcher
        h0, c0 = medikits(host), medikits(client)
        start(host, "STR_COOP_RS_SPAWNS_ITEM", 1)
        seen = advance(host, client, DAY)
        h1, c1 = medikits(host), medikits(client)
        if h1 != h0 + 1:
            raise Inconclusive(f"R6: host medi-kits {h0} -> {h1}, expected +1 from the research")
        ok = "STR_COOP_RS_SPAWNS_ITEM" in known(client) and c1 == c0
        results["R6 items"] = (ok, f"client knows topic={'STR_COOP_RS_SPAWNS_ITEM' in known(client)} "
                                   f"client medi-kits {c0} -> {c1}")
    except Inconclusive as e:
        note = "INCONCLUSIVE: " + str(e)
    except Exception as e:  # a dropped socket mid-command == a crash
        note = f"ERROR {type(e).__name__}: {e}"
    finally:
        alive = {gc.name: gc.proc.poll() is None for gc in (host, client)}
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception:
                pass

    print("==== RESULT ====")
    for row, (ok, detail) in results.items():
        print(("PASS " if ok else "FAIL ") + row + ": " + detail)
    print("alive:", alive, "| note:", note)
    if not all(alive.values()) or (note and note.startswith("ERROR")):
        sys.exit(2)
    if note:
        sys.exit(3)
    if not all(ok for ok, _ in results.values()):
        sys.exit(2)
    print("PASS: research sync makes a discovery a discovery for both players")
    sys.exit(0)


if __name__ == "__main__":
    main()
