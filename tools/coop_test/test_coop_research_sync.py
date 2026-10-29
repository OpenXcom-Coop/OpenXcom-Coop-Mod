"""Regression test: in a Separate campaign with Shared Research, a discovery is a
discovery for BOTH players.

The Separate campaign is one host-owned world. The host simulates every base, so
a research project completes once, on the host. With Shared Research (the
multiplayer option "Research Sync"), discoveries go to the one canonical research
list, which the client replica adopts from the host's research_done result. The
old two-world rows (main #197) checked that a peer's completion was mirrored into
the other player's own world; here each row runs the host-simulated completion
and checks:
  * both players' knowledge: the global list on both machines, each player's
    research check (isResearchedForPlayer) on both machines, and the private
    profiles (unchanged and identical on both machines);
  * both machines' views of the bases (research projects, items);
  * the popups each machine shows (Shared Research: both players get the same
    "Research Completed" dialog, as in a Shared campaign).

Rows (vanilla rules plus Coop_ResearchSync_Test, Shared Research on, the host
player researches at HostBase):
  R1 bonus   STR_SECTOID_ENGINEER (getOneFree: UFO types). Both players learn the
             topic, its lookup and the one bonus the host rolled; each machine
             shows one popup whose VIEW REPORTS opens the bonus article.
  R2 lookup  STR_SECTOID_CORPSE (lookup STR_SECTOID_AUTOPSY). Both players learn
             the lookup; each machine's VIEW REPORTS opens that article.
  R3 dup     the client player's ClientBase also runs STR_LASER_WEAPONS. When the
             host player's copy finishes, the ClientBase copy is removed on both
             machines (nothing left to gain from it).
  R4 keep    the same with STR_SECTOID_ENGINEER: the ClientBase copy stays on both
             machines, the topic still has undiscovered getOneFree rewards (vanilla
             rule). Guard row.
  R5 quiet   STR_SECTOID_CORPSE again, already known to both. Single-world
             equivalent of "a completion that brings nothing new pops nothing": the
             old receiver-side mirror is gone, so each machine shows exactly the one
             Shared Research dialog (no duplicate), no article opens and nobody
             learns anything.
  R6 items   STR_COOP_RS_SPAWNS_ITEM (spawnedItem STR_MEDI_KIT). Both players learn
             the topic; the medi-kit goes only to HostBase, the researcher's base,
             on both machines (owner ruling RU5).
  R7 effects STR_COOP_RS_COUNTER_EVENT (increaseCounter COOP_RS_COUNTER, spawnedEvent
             STR_COOP_RS_EVENT). Both machines hold the same counter value and the
             same pending event (owner, the host's countdown).
  R8 corpse  STR_SECTOID_SOLDIER, an interrogation, with retainCorpses on the host
             only. The corpse returns to HostBase's stores on both machines.

Every row also reports the client's world-checksum repairs (resync requests):
the replica must reach the host's result through the research_done result, not
through a whole-world restream.

  * PASS (exit 0): every row holds.
  * FAIL (exit 2): a row failed or a game process crashed.
  * FAIL (exit 3): a precondition never held; the test proved nothing.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import geo  # noqa: E402
import separate_campaign_fixture as sep  # noqa: E402

MOD = os.path.join(HERE, "mods", "Coop_ResearchSync_Test")
DAY = 26 * 60
PLAYERS = ("HostPlayer", "ClientPlayer")
# STR_SECTOID_ENGINEER's getOneFree list (bin/standard/xcom1/research.rul)
ENGINEER_FREE = {"STR_SMALL_SCOUT", "STR_MEDIUM_SCOUT", "STR_LARGE_SCOUT", "STR_HARVESTER",
                 "STR_ABDUCTOR", "STR_TERROR_SHIP", "STR_BATTLESHIP", "STR_SUPPLY_SHIP"}


class Inconclusive(Exception):
    pass


def known(gc):
    return set(gc.ok({"cmd": "geo_state"}).get("discoveredResearch", []))


def profiles(gc):
    return {p["name"]: sorted(p.get("completedResearch", []))
            for p in gc.ok({"cmd": "separate_profile_state"})["players"]}


def player_knows(gc, topic):
    """Each player's research check on THIS machine."""
    return {p: gc.ok({"cmd": "separate_research_check", "research": topic,
                      "player": p})["researched"] for p in PLAYERS}


def base(gc, name):
    return next(b for b in gc.ok({"cmd": "geo_state"})["bases"] if b["name"] == name)


def projects(gc, name):
    return sorted(r["name"] for r in base(gc, name)["research"])


def medikits(gc, name):
    """STR_MEDI_KIT at a base: in stores plus on the way in."""
    b = base(gc, name)
    return b["items"].get("STR_MEDI_KIT", 0) + sum(
        t["qty"] for t in b["transfers"] if t.get("rule") == "STR_MEDI_KIT")


def requests(gc):
    return gc.ok({"cmd": "shared_resync_stats"})["requests"]


def counter(gc, name):
    return gc.ok({"cmd": "custom_counters", "names": [name]})["counters"].get(name)


def pending(gc, name):
    """(owner, countdown) of each pending `name` event on THIS machine."""
    return sorted((e["owner"], e["countdown"]) for e in gc.ok({"cmd": "geo_events"})["events"]
                  if e["name"] == name and not e["over"])


def corpses(gc, name):
    return base(gc, name)["items"].get("STR_SECTOID_CORPSE", 0)


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
    """Run the host's clock (the one simulation) for `minutes` at speed 4 (one
    hour per step), draining both machines, then keep draining for `settle`
    seconds so a late result is seen."""
    seen = {host.name: [], client.name: []}
    start = geo.game_minutes(host)
    deadline = time.time() + 120
    while time.time() < deadline:
        for gc in (host, client):
            seen[gc.name] += drain(gc)
        now = geo.game_minutes(host)
        if now is not None and now - start >= minutes:
            break
        # The host runs the slower of the two players' chosen speeds.
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


def start(gc, topic, cost, base_name="HostBase"):
    gc.ok({"cmd": "start_research", "topic": topic, "cost": cost, "scientists": 1,
           "base": base_name})


def knowledge(host, client, topics):
    """What both machines say about `topics`: the global list and each player's
    research check. Equal on both machines when the replica holds the result."""
    out = {}
    for gc in (host, client):
        k = known(gc)
        out[gc.name] = {t: (t in k, player_knows(gc, t)) for t in sorted(topics)}
    return out


def everyone_knows(view, topics):
    return all(view[m][t][0] and all(view[m][t][1].values())
               for m in view for t in topics)


def converge(host, client, what, fn, timeout=15):
    """Wait until fn(host) == fn(client); returns both values."""
    deadline = time.time() + timeout
    while True:
        h, c = fn(host), fn(client)
        if h == c or time.time() > deadline:
            return h, c
        time.sleep(0.5)


def row_bonus(host, client, results, profiles0):
    before = known(host)
    r0 = requests(client)
    start(host, "STR_SECTOID_ENGINEER", 1)
    seen = advance(host, client, DAY)
    gained = known(host) - before
    bonus = sorted(gained & ENGINEER_FREE)
    if "STR_SECTOID_ENGINEER" not in gained or len(bonus) != 1:
        raise Inconclusive(f"R1: host did not complete the topic with one bonus: gained={sorted(gained)}")
    bonus = bonus[0]
    h, c = converge(host, client, "R1", known)
    view = knowledge(host, client, gained)
    article = "article:" + bonus
    popups = {m: (seen[m].count("RC"), article in seen[m]) for m in seen}
    ok = (h == c and everyone_knows(view, gained)
          and profiles(host) == profiles(client) == profiles0
          and all(n == 1 and a for n, a in popups.values())
          and requests(client) == r0)
    results["R1 bonus"] = (ok, f"gained={sorted(gained)} missing on client={sorted(h - c)} "
                               f"(RC count, bonus article) per machine={popups} "
                               f"restreams={requests(client) - r0} popups={seen}")


def row_lookup(host, client, results, profiles0):
    r0 = requests(client)
    start(host, "STR_SECTOID_CORPSE", 1)
    seen = advance(host, client, DAY)
    if "STR_SECTOID_AUTOPSY" not in known(host):
        raise Inconclusive("R2: host never learned STR_SECTOID_AUTOPSY")
    converge(host, client, "R2", known)
    view = knowledge(host, client, {"STR_SECTOID_AUTOPSY"})
    article = "article:STR_SECTOID_AUTOPSY"
    ok = (everyone_knows(view, {"STR_SECTOID_AUTOPSY"})
          and all(article in seen[m] for m in seen)
          and profiles(host) == profiles(client) == profiles0
          and requests(client) == r0)
    results["R2 lookup"] = (ok, f"knowledge={view} restreams={requests(client) - r0} popups={seen}")


def row_duplicate(host, client, results, topic, keep, row):
    r0 = requests(client)
    for gc in (host, client):  # the client player's copy, in the world and its replica
        start(gc, topic, 100000, base_name="ClientBase")
    if topic not in projects(host, "ClientBase") or topic not in projects(client, "ClientBase"):
        raise Inconclusive(f"{row}: the ClientBase copy of {topic} never started")
    start(host, topic, 1)
    seen = advance(host, client, DAY)
    if topic in projects(host, "HostBase"):
        raise Inconclusive(f"{row}: the host player's {topic} never completed: {seen}")
    h, c = converge(host, client, row, lambda gc: projects(gc, "ClientBase"))
    ok = (topic in h) == keep and (topic in c) == keep and requests(client) == r0
    results[row] = (ok, f"ClientBase projects host={h} client={c} "
                        f"restreams={requests(client) - r0}")


def row_quiet(host, client, results, profiles0):
    r0 = requests(client)
    before = (known(host), known(client))
    start(host, "STR_SECTOID_CORPSE", 1)
    seen = advance(host, client, DAY)
    if "RC" not in seen[host.name]:
        raise Inconclusive(f"R5: host never completed the repeat: {seen[host.name]}")
    after = (known(host), known(client))
    articles = {m: [s for s in seen[m] if s.startswith("article:")] for m in seen}
    ok = (all(seen[m].count("RC") == 1 for m in seen)
          and not any(articles.values()) and after == before
          and profiles(host) == profiles(client) == profiles0
          and requests(client) == r0)
    results["R5 quiet"] = (ok, f"articles={articles} learned host={sorted(after[0] - before[0])} "
                               f"client={sorted(after[1] - before[1])} "
                               f"restreams={requests(client) - r0} popups={seen}")


def row_items(host, client, results):
    topic = "STR_COOP_RS_SPAWNS_ITEM"
    r0 = requests(client)
    kits0 = {(gc.name, b): medikits(gc, b) for gc in (host, client)
             for b in ("HostBase", "ClientBase")}
    start(host, topic, 1)
    seen = advance(host, client, DAY)
    if medikits(host, "HostBase") != kits0[(host.name, "HostBase")] + 1:
        raise Inconclusive(f"R6: host HostBase medi-kits did not grow by one: {kits0} -> "
                           f"{medikits(host, 'HostBase')}")
    converge(host, client, "R6", lambda gc: medikits(gc, "HostBase"))
    kits = {(gc.name, b): medikits(gc, b) for gc in (host, client)
            for b in ("HostBase", "ClientBase")}
    want = dict(kits0)
    for gc in (host, client):
        want[(gc.name, "HostBase")] += 1
    view = knowledge(host, client, {topic})
    ok = kits == want and everyone_knows(view, {topic}) and requests(client) == r0
    results["R6 items"] = (ok, f"medi-kits before={kits0} after={kits} knowledge={view} "
                               f"restreams={requests(client) - r0}")


def row_counter_event(host, client, results):
    """R7: the topic's custom counter and spawned event reach the replica from the
    host's result. The event's countdown is the host's roll (minus the half hours
    the host counted since), never a roll of the replica's own."""
    topic, ctr, ev = "STR_COOP_RS_COUNTER_EVENT", "COOP_RS_COUNTER", "STR_COOP_RS_EVENT"
    r0 = requests(client)
    c0 = (counter(host, ctr), counter(client, ctr))
    t0 = geo.game_minutes(host)
    start(host, topic, 1)
    advance(host, client, DAY)
    elapsed = geo.game_minutes(host) - t0
    if counter(host, ctr) == c0[0] or not pending(host, ev):
        raise Inconclusive(f"R7: the host world did not run the side effects: counter "
                           f"{c0[0]} -> {counter(host, ctr)} events={pending(host, ev)}")
    converge(host, client, "R7", lambda gc: (counter(gc, ctr), [o for o, _ in pending(gc, ev)]))
    hc, cc = counter(host, ctr), counter(client, ctr)
    he, ce = pending(host, ev), pending(client, ev)
    same_event = (len(he) == len(ce) == 1 and he[0][0] == ce[0][0]
                  and abs(he[0][1] - ce[0][1]) <= elapsed + 30)
    ok = hc == cc and same_event and requests(client) == r0
    results["R7 counter+event"] = (ok, f"counter host={hc} client={cc} (before {c0}) "
                                       f"{ev} host={he} client={ce} (window {elapsed} min) "
                                       f"restreams={requests(client) - r0}")


def row_interrogation(host, client, results):
    """R8: a finished interrogation puts the alien's corpse back in the researching
    base's stores (host option retainCorpses). The replica gets the same corpse
    from the host's result, not from a world restream."""
    r0 = requests(client)
    k0 = (corpses(host, "HostBase"), corpses(client, "HostBase"))
    start(host, "STR_SECTOID_SOLDIER", 1)
    advance(host, client, DAY)
    if "STR_SECTOID_SOLDIER" in projects(host, "HostBase"):
        raise Inconclusive("R8: the interrogation never completed on the host")
    if corpses(host, "HostBase") != k0[0] + 1:
        raise Inconclusive(f"R8: the host kept no corpse: {k0[0]} -> {corpses(host, 'HostBase')}")
    h, c = converge(host, client, "R8", lambda gc: corpses(gc, "HostBase"))
    ok = h == c == k0[1] + 1 and requests(client) == r0
    results["R8 interrogation"] = (ok, f"HostBase corpses before={k0} host={h} client={c} "
                                       f"restreams={requests(client) - r0}")


def main():
    opts = {"EnableResearchSync": True}
    # R8: only the host keeps interrogation corpses; the replica must follow the
    # host's result, not its own option.
    js = sep.bring_up("rsync", (48991, 48992, 47966), mods=[MOD],
                      host_options=dict(opts, retainCorpses=True), client_options=opts)
    host, client = js.host, js.client
    results = {}
    note = None
    try:
        for gc in (host, client):
            state = gc.ok({"cmd": "separate_profile_state"})
            if state["researchSharingEnabled"] is not True:
                raise Inconclusive(f"{gc.name}: Shared Research is off: {state}")
        geo.slow_clock(host, client)
        for gc in (host, client):
            geo.drain_popups(gc)
        profiles0 = profiles(host)
        if profiles(client) != profiles0:
            raise Inconclusive(f"profiles differ at start: {profiles0} vs {profiles(client)}")
        row_bonus(host, client, results, profiles0)
        row_lookup(host, client, results, profiles0)
        row_duplicate(host, client, results, "STR_LASER_WEAPONS", False, "R3 dup")
        row_duplicate(host, client, results, "STR_SECTOID_ENGINEER", True, "R4 keep")
        row_quiet(host, client, results, profiles0)
        row_items(host, client, results)
        row_counter_event(host, client, results)
        row_interrogation(host, client, results)
    except Inconclusive as e:
        note = "INCONCLUSIVE: " + str(e)
    except Exception as e:  # a dropped socket mid-command == a crash
        note = f"ERROR {type(e).__name__}: {e}"
    finally:
        alive = {gc.name: gc.proc.poll() is None for gc in (host, client)}
        js.shutdown()

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
    print("PASS: with Shared Research a discovery is a discovery for both players")
    sys.exit(0)


if __name__ == "__main__":
    main()
