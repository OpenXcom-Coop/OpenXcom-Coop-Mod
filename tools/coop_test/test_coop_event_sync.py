"""Regression test: Separate campaign geoscape events belong to the month's
rotation owner, and their popup, report and rewards reach that player only.

The Separate campaign is one host-owned world. Each month the host runs the
event scripts once, for ONE player in rotation (SeparateEcon
CampaignData::nextMissionOwner). The event belongs to that
player: its popup and its report appear only on the owner's machine, its funds go
to the owner's wallet and its research to the owner (with Shared Research: the
canonical list, so both players learn it). The other player gets nothing.

Fixture mod Coop_EventSync_Test:
  STR_COOP_EV_CERTAIN    month 0, odds 100, one possible event, pays 100000
  STR_COOP_EV_RANDOM_A/B month 0, 50/50 pick
  STR_COOP_EV_COND       month 1+, once STR_COOP_EV_TRIGGER is known, pays 100000
  STR_COOP_EV_COND_HOST  month 1+, once STR_COOP_EV_TRIGGER_HOST is known, pays 100000
Each event grants its own STR_*_TOPIC research. Delays are 1440 + random(20000)
minutes; rows that need a fire shorten the host's countdown.

Session 1 (Shared Research on):
  month-0 owner: the month-0 certain event is scheduled once, owned by the first
     player of the rotation (sorted roster: ClientPlayer).
  one schedule: the client's view lists the same events (name, countdown, owner).
  one random pick: exactly one of RANDOM_A/B is scheduled, owned by the same
     player.
  owner only: the certain event fires: event popup and article on the owner's
     machine only; 100000 into the owner's wallet only; its topic reaches both
     players through the canonical list; no "Research Completed" popup anywhere.
  next owner: both players know STR_COOP_EV_TRIGGER: at month 1 STR_COOP_EV_COND
     belongs to the next player in the rotation (HostPlayer) and fires for that
     player only, under the same owner-only rules.
Session 2 (private research):
  owner only: the certain event fires for its owner: its topic goes to the
     owner's profile only (both machines), the global list is unchanged, and the
     wallet and popup rules are the same as in session 1.
  owner's trigger: at month 1 (owner HostPlayer) only HostPlayer's profile holds
     STR_COOP_EV_TRIGGER_HOST and only ClientPlayer's holds STR_COOP_EV_TRIGGER:
     STR_COOP_EV_COND_HOST is scheduled for HostPlayer, STR_COOP_EV_COND is not;
     COND_HOST's topic goes to HostPlayer's profile only.
  research side effects (both sessions): STR_COOP_EV_EFFECTS grants a topic
     whose research side effects raise COOP_EV_COUNTER, schedule
     STR_COOP_EV_FOLLOWUP and send a medi-kit to the owner's base. The replica
     holds the host's counter, the host's follow-up event (its countdown, not one
     the replica rolled) and the medi-kit.
  item, craft and soldier rewards: STR_COOP_EV_REWARD gives the owner's base a
     medi-kit, a Skyranger and a soldier; the replica's copy of that base equals
     the host's, and once the soldier arrives it belongs to the event's owner on
     both machines.

Every firing row also checks that the client's view of the pending events (names
and owners) equals the host's, and reports the client's world-checksum repairs:
the replica must reach the host's result through the host's messages, not a world
restream.

  * PASS (exit 0) / FAIL (exit 2: a row failed or a process crashed) /
    FAIL (exit 2: a precondition never held).
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import geo  # noqa: E402
import separate_campaign_fixture as sep  # noqa: E402

MOD = os.path.join(HERE, "mods", "Coop_EventSync_Test")
CERTAIN, COND, COND_HOST = "STR_COOP_EV_CERTAIN", "STR_COOP_EV_COND", "STR_COOP_EV_COND_HOST"
RANDOM = {"STR_COOP_EV_RANDOM_A", "STR_COOP_EV_RANDOM_B"}
PLAYERS = ("ClientPlayer", "HostPlayer")  # rotation order (sorted roster)
REWARD = 100000


class Inconclusive(Exception):
    pass


def events(gc):
    return {e["name"]: (e["countdown"], e["owner"])
            for e in gc.ok({"cmd": "geo_events"})["events"] if not e["over"]}


def known(gc):
    return set(gc.ok({"cmd": "geo_state"}).get("discoveredResearch", []))


def profiles(gc):
    """Per player on THIS machine: (wallet, private research)."""
    return {p["name"]: (p["funds"], set(p.get("completedResearch", [])))
            for p in gc.ok({"cmd": "separate_profile_state"})["players"]}


def player_knows(gc, topic):
    return {p: gc.ok({"cmd": "separate_research_check", "research": topic,
                      "player": p})["researched"] for p in PLAYERS}


def requests(gc):
    return gc.ok({"cmd": "shared_resync_stats"})["requests"]


def machine_of(host, client, player):
    return host if player == "HostPlayer" else client


def other(player):
    return PLAYERS[1] if player == PLAYERS[0] else PLAYERS[0]


def drain(gc):
    """Close every popup; press VIEW REPORTS on research popups. Returns what was
    seen: 'RC' per research popup, 'EV' per event popup, 'article:<id>' per article."""
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
            break
        if r.get("article"):
            seen.append("article:" + r["article"])
        elif r.get("handled") == "GeoscapeEventState":
            seen.append("EV")
        else:
            seen.append(r.get("handled", top))
    return seen


def advance(host, client, minutes, settle=3.0):
    """Run the one simulation (speed 4, one hour per step) for `minutes`. The host
    runs the slower of the two players' chosen speeds, so both are set."""
    seen = {host.name: [], client.name: []}
    start = geo.game_minutes(host)
    deadline = time.time() + 120
    while time.time() < deadline:
        for gc in (host, client):
            seen[gc.name] += drain(gc)
        now = geo.game_minutes(host)
        if now is not None and now - start >= minutes:
            break
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


def bring_up(tag, ports, sync):
    opts = {"EnableResearchSync": sync}
    js = sep.bring_up(tag, ports, mods=[MOD], host_options=opts, client_options=opts)
    try:
        for gc in (js.host, js.client):
            state = gc.ok({"cmd": "separate_profile_state"})
            if state["researchSharingEnabled"] is not sync:
                raise Inconclusive(f"{gc.name}: research mode is not {sync}: {state}")
        time.sleep(2.0)  # let any start-of-campaign popup land
        for gc in (js.host, js.client):
            geo.drain_popups(gc)
        geo.slow_clock(js.host, js.client)
    except BaseException:
        js.shutdown()
        raise
    return js


def roll_month(host, client):
    host.ok({"cmd": "set_geo_day", "day": 31, "hour": 23})
    seen = advance(host, client, 120)
    time.sleep(2.0)
    for gc in (host, client):
        drain(gc)
    return seen


def fire(host, client, name, row, shared):
    """Fire the host's copy of `name` and check the owner-only rules. Returns
    (ok, detail)."""
    pending = events(host)
    if name not in pending:
        raise Inconclusive(f"{row}: {name} is not scheduled on the host: {pending}")
    owner = pending[name][1]
    if owner not in PLAYERS:
        raise Inconclusive(f"{row}: {name} has no player owner: {pending}")
    topic = name + "_TOPIC"
    r0 = requests(client)
    before = {gc.name: (profiles(gc), known(gc)) for gc in (host, client)}
    host.ok({"cmd": "set_event_countdown", "name": name, "minutes": 60})
    seen = advance(host, client, 180)
    if topic not in (known(host) if shared else profiles(host)[owner][1]):
        raise Inconclusive(f"{row}: the host world never granted {topic}: {seen}")
    owner_gc = machine_of(host, client, owner)
    other_gc = machine_of(host, client, other(owner))
    problems = []
    if seen[owner_gc.name].count("EV") != 1 or "article:" + topic not in seen[owner_gc.name]:
        problems.append(f"owner machine {owner_gc.name} popups={seen[owner_gc.name]}")
    if "EV" in seen[other_gc.name] or any(s.startswith("article:") for s in seen[other_gc.name]):
        problems.append(f"other machine {other_gc.name} popups={seen[other_gc.name]}")
    if any("RC" in seen[m] for m in seen):
        problems.append(f"Research Completed popup: {seen}")
    for gc in (host, client):
        prof0, known0 = before[gc.name]
        prof = profiles(gc)
        if prof[owner][0] != prof0[owner][0] + REWARD:
            problems.append(f"{gc.name}: owner wallet {prof0[owner][0]} -> {prof[owner][0]}")
        if prof[other(owner)][0] != prof0[other(owner)][0]:
            problems.append(f"{gc.name}: other wallet {prof0[other(owner)][0]} -> "
                            f"{prof[other(owner)][0]}")
        checks = player_knows(gc, topic)
        if shared:
            if topic not in known(gc) or not all(checks.values()):
                problems.append(f"{gc.name}: shared topic not known to both: {checks}")
            if {p: prof[p][1] for p in PLAYERS} != {p: prof0[p][1] for p in PLAYERS}:
                problems.append(f"{gc.name}: a private profile changed")
        else:
            if topic not in prof[owner][1] or topic in prof[other(owner)][1]:
                problems.append(f"{gc.name}: private topic owner={topic in prof[owner][1]} "
                                f"other={topic in prof[other(owner)][1]}")
            if checks != {owner: True, other(owner): False}:
                problems.append(f"{gc.name}: research checks {checks}")
            if known(gc) != known0:
                problems.append(f"{gc.name}: global list changed by {sorted(known(gc) - known0)}")
    # The fired event leaves the host's schedule; the replica's view of the
    # schedule must follow (names and owners; a frozen replica never counts down).
    hs, cs = schedule(host), schedule(client)
    if hs != cs:
        problems.append(f"pending events host={hs} client={cs}")
    restreams = requests(client) - r0
    if restreams:
        problems.append(f"the replica needed {restreams} world restream(s)")
    return (not problems, f"owner={owner} " + ("; ".join(problems) if problems else
                                               f"popups={seen}"))


def schedule(gc):
    return sorted((e["name"], e["owner"]) for e in gc.ok({"cmd": "geo_events"})["events"]
                  if not e["over"])


def counter(gc, name):
    return gc.ok({"cmd": "custom_counters", "names": [name]})["counters"].get(name)


def owner_base(gc, player):
    """The canonical (comparable) view of the player's base on THIS machine."""
    name = "HostBase" if player == "HostPlayer" else "ClientBase"
    return next(b for b in sep.canonical_world(gc)["bases"] if b["name"] == name)


def medikits(b):
    return b["items"].get("STR_MEDI_KIT", 0) + sum(
        q for t, r, q in b["transfers"] if r == "STR_MEDI_KIT")


def spawn_on_host(host, name, owner):
    """Schedule `name` for `owner` in the one world (the host's), due in an hour."""
    host.ok({"cmd": "spawn_event", "name": name, "owner": owner})


def effects(host, client, row, owner):
    """The event grants STR_COOP_EV_EFFECTS_TOPIC, whose research side effects
    raise COOP_EV_COUNTER, schedule STR_COOP_EV_FOLLOWUP and send a medi-kit to the
    owner's base. The replica holds the host's result: the same counter, the same
    follow-up event on the host's countdown (never one the replica rolled) and the
    same medi-kit."""
    ctr, follow = "COOP_EV_COUNTER", "STR_COOP_EV_FOLLOWUP"
    r0 = requests(client)
    c0 = (counter(host, ctr), counter(client, ctr))
    k0 = (medikits(owner_base(host, owner)), medikits(owner_base(client, owner)))
    spawn_on_host(host, "STR_COOP_EV_EFFECTS", owner)
    t0 = geo.game_minutes(host)
    advance(host, client, 180)
    elapsed = geo.game_minutes(host) - t0

    def view(gc):
        evs = [e for e in gc.ok({"cmd": "geo_events"})["events"]
               if e["name"] == follow and not e["over"]]
        return counter(gc, ctr), [(e["owner"], e["countdown"]) for e in evs]

    hv, cv = view(host), view(client)
    if hv[0] == c0[0] or len(hv[1]) != 1:
        raise Inconclusive(f"{row}: the host world did not run the topic's side effects: {hv}")
    deadline = time.time() + 15
    while time.time() < deadline and (cv[0] != hv[0] or [o for o, _ in cv[1]] != [o for o, _ in hv[1]]):
        time.sleep(0.5)
        hv, cv = view(host), view(client)
    k = (medikits(owner_base(host, owner)), medikits(owner_base(client, owner)))
    same_event = (len(cv[1]) == 1 and cv[1][0][0] == hv[1][0][0]
                  and abs(cv[1][0][1] - hv[1][0][1]) <= elapsed + 30)
    ok = (cv[0] == hv[0] and same_event and k == (k0[0] + 1, k0[1] + 1)
          and requests(client) == r0)
    return (ok, f"owner={owner} counter host={hv[0]} client={cv[0]} (before {c0}) "
                f"{follow} host={hv[1]} client={cv[1]} (window {elapsed} min) "
                f"medi-kits before={k0} after={k} restreams={requests(client) - r0}")


def rewards(host, client, owner):
    """STR_COOP_EV_REWARD gives the owner's base a medi-kit (stores), a Skyranger
    (hangar) and a soldier (on the way in). The replica's base is the host's."""
    r0 = requests(client)
    b0 = owner_base(host, owner)
    s0 = set(soldier_owners(host, owner))
    spawn_on_host(host, "STR_COOP_EV_REWARD", owner)
    advance(host, client, 180)
    hb = owner_base(host, owner)
    rangers = lambda b: sum(1 for c in b["crafts"] if c[1] == "STR_SKYRANGER")
    # On the way or, once a slow window passed 24 hours, arrived.
    soldiers_in = lambda b: sum(1 for t in b["transfers"] if t[1] == "STR_SOLDIER") + len(b["soldiers"])
    counts = lambda b: (b["items"].get("STR_MEDI_KIT", 0), rangers(b), soldiers_in(b))
    if counts(hb) != tuple(n + 1 for n in counts(b0)):
        raise Inconclusive(f"rewards: the host world did not give the rewards: (medi-kits, Skyrangers, "
                           f"soldiers on the way) before={counts(b0)} after={counts(hb)} "
                           f"transfers={hb['transfers']}")
    deadline = time.time() + 15
    cb = owner_base(client, owner)
    while time.time() < deadline and cb != hb:
        time.sleep(0.5)
        hb, cb = owner_base(host, owner), owner_base(client, owner)
    ok = hb == cb and requests(client) == r0
    diff = {k: (hb[k], cb[k]) for k in hb if hb[k] != cb[k]}
    owners = event_soldier_owners(host, client, owner, s0)
    seat = SEATS[owner]
    ok = ok and owners == {"host": [seat], "client": [seat]}
    return (ok, f"owner={owner} base differs={diff} restreams={requests(client) - r0} "
                f"event soldier owners={owners} (want seat {seat})")


SEATS = {"HostPlayer": 0, "ClientPlayer": 1}


def soldier_owners(gc, player):
    name = "HostBase" if player == "HostPlayer" else "ClientBase"
    return {s["id"]: s["owner"] for b in gc.ok({"cmd": "get_soldiers"})["bases"]
            if b["name"] == name for s in b["soldiers"]}


def event_soldier_owners(host, client, player, before):
    """Land the event's soldier at the owner's base; its owner on each machine."""
    name = "HostBase" if player == "HostPlayer" else "ClientBase"
    host.ok({"cmd": "force_transfer_arrivals", "base": name})
    deadline = time.time() + 20
    new = {}
    while time.time() < deadline:
        new = {gc.name: [o for i, o in soldier_owners(gc, player).items() if i not in before]
               for gc in (host, client)}
        if all(new.values()):
            break
        time.sleep(0.5)
    return new


def session_shared(results):
    js = bring_up("evsync", (48993, 48994, 47995), True)
    host, client = js.host, js.client
    try:
        he, ce = events(host), events(client)
        if CERTAIN not in he:
            raise Inconclusive(f"E1: host never scheduled {CERTAIN}: {he}")
        owner0 = he[CERTAIN][1]
        results["month-0 owner"] = (owner0 == PLAYERS[0], f"host events={he}")
        # A 30-minute countdown step may land between the two reads.
        same = (set(ce) == set(he)
                and all(ce[n][1] == he[n][1] and abs(ce[n][0] - he[n][0]) <= 30 for n in he))
        results["one schedule"] = (same, f"host={he} client={ce}")
        picked = sorted(RANDOM & set(he))
        results["one random pick"] = (
            len(picked) == 1 and he[picked[0]][1] == owner0,
            f"picked={picked} owners={[he[p][1] for p in picked]}")
        results["owner only, shared research"] = fire(host, client, CERTAIN, "certain event", True)

        for gc in (host, client):
            gc.ok({"cmd": "discover_research", "topic": "STR_COOP_EV_TRIGGER"})
        roll_month(host, client)
        he = events(host)
        if COND not in he:
            raise Inconclusive(f"next owner: host did not schedule {COND} at month 1: {he}")
        ok_owner = he[COND][1] == other(owner0) and COND_HOST not in he
        ok_fire, detail = fire(host, client, COND, "next owner", True)
        results["next owner, shared research"] = (
            ok_owner and ok_fire, f"month-1 events={he} {detail}")
        results["research side effects, shared research"] = effects(
            host, client, "side effects, shared research", "ClientPlayer")
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        js.shutdown()
    return alive


def session_private(results):
    js = bring_up("evnosync", (48995, 48996, 47996), False)
    host, client = js.host, js.client
    try:
        he = events(host)
        if CERTAIN not in he:
            raise Inconclusive(f"private research: host never scheduled {CERTAIN}: {he}")
        owner0 = he[CERTAIN][1]
        ok_fire, detail = fire(host, client, CERTAIN, "certain event, private research", False)
        results["owner only, private research"] = (
            ok_fire and owner0 == PLAYERS[0], detail)

        owner1 = other(owner0)
        for gc in (host, client):  # the world and its replica
            gc.ok({"cmd": "separate_profile_set", "player": owner1,
                   "research": "STR_COOP_EV_TRIGGER_HOST"})
            gc.ok({"cmd": "separate_profile_set", "player": owner0,
                   "research": "STR_COOP_EV_TRIGGER"})
        roll_month(host, client)
        he = events(host)
        if COND_HOST not in he:
            raise Inconclusive(f"owner's trigger: host did not schedule {COND_HOST} at month 1: {he}")
        ok_sched = he[COND_HOST][1] == owner1 and COND not in he
        ok_fire, detail = fire(host, client, COND_HOST, "owner's trigger", False)
        results["owner's trigger, private research"] = (
            ok_sched and ok_fire, f"month-1 events={he} {detail}")
        results["item, craft and soldier rewards"] = rewards(host, client, "ClientPlayer")
        results["research side effects, private research"] = effects(
            host, client, "side effects, private research", "ClientPlayer")
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        js.shutdown()
    return alive


def main():
    results = {}
    note = None
    alive = True
    try:
        alive = session_shared(results) and alive
        alive = session_private(results) and alive
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
        sys.exit(2)  # a precondition miss fails the run
    if not all(ok for ok, _ in results.values()):
        sys.exit(2)
    print("PASS: Separate events belong to the month's rotation owner")
    sys.exit(0)


if __name__ == "__main__":
    main()
