"""Regression test: Separate campaign geoscape events belong to the month's
rotation owner, and their popup, report and rewards reach that player only.

The Separate campaign is one host-owned world. Each month the host runs the
event scripts once, for ONE player in rotation (SeparateEcon
CampaignData::nextMissionOwner, owner ruling RU15). The event belongs to that
player: its popup and its report appear only on the owner's machine, its funds go
to the owner's wallet and its research to the owner (with Shared Research: the
canonical list, so both players learn it). The other player gets nothing.

The old two-world rows (main #197) checked that each player's own world rolled the
same certain event at the same time. Their single-world equivalents:
  E1 (client rolls at game start)  -> the month-0 event exists once and belongs to
                                      the month-0 rotation owner;
  E2 (same countdown)              -> the client's view lists the host's events;
  E3 (each rolls its own random)   -> the 50/50 script picks ONE event, for the
                                      same owner;
  E4/E5 (fires for both)           -> fires for its owner only;
  E6 (research sync to the other)  -> Shared Research gives the event's research
                                      to both through the canonical list (part
                                      of E4/E5); with private research the
                                      script's research trigger is the owner's;
  E7/E8 (sync off)                 -> private research: the owner's profile only.

Fixture mod Coop_EventSync_Test:
  STR_COOP_EV_CERTAIN    month 0, odds 100, one possible event, pays 100000
  STR_COOP_EV_RANDOM_A/B month 0, 50/50 pick
  STR_COOP_EV_COND       month 1+, once STR_COOP_EV_TRIGGER is known, pays 100000
  STR_COOP_EV_COND_HOST  month 1+, once STR_COOP_EV_TRIGGER_HOST is known, pays 100000
Each event grants its own STR_*_TOPIC research. Delays are 1440 + random(20000)
minutes; rows that need a fire shorten the host's countdown.

Session 1 (Shared Research on):
  E1 the month-0 certain event is scheduled once, owned by the first player of the
     rotation (sorted roster: ClientPlayer).
  E2 the client's view lists the same events (name, countdown, owner).
  E3 exactly one of RANDOM_A/B is scheduled, owned by the same player.
  E4 the certain event fires: event popup and article on the owner's machine only;
     100000 into the owner's wallet only; its topic reaches both players through
     the canonical list; no "Research Completed" popup anywhere.
  E5 both players know STR_COOP_EV_TRIGGER: at month 1 STR_COOP_EV_COND belongs to
     the next player in the rotation (HostPlayer) and fires for that player only,
     as in E4.
Session 2 (private research):
  E7 the certain event fires for its owner: its topic goes to the owner's profile
     only (both machines), the global list is unchanged, the wallet and popup rules
     are E4's.
  E8 at month 1 (owner HostPlayer) only HostPlayer's profile holds
     STR_COOP_EV_TRIGGER_HOST and only ClientPlayer's holds STR_COOP_EV_TRIGGER:
     STR_COOP_EV_COND_HOST is scheduled for HostPlayer, STR_COOP_EV_COND is not;
     COND_HOST's topic goes to HostPlayer's profile only.

Every firing row also reports the client's world-checksum repairs: the replica
must reach the host's result through the event message, not a world restream.

  * PASS (exit 0) / FAIL (exit 2: a row failed or a process crashed) /
    FAIL (exit 3: a precondition never held).
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
    """Fire the host's copy of `name` and check E4's owner-only rules. Returns
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
    restreams = requests(client) - r0
    if restreams:
        problems.append(f"the replica needed {restreams} world restream(s)")
    return (not problems, f"owner={owner} " + ("; ".join(problems) if problems else
                                               f"popups={seen}"))


def session_shared(results):
    js = bring_up("evsync", (48993, 48994, 47995), True)
    host, client = js.host, js.client
    try:
        he, ce = events(host), events(client)
        if CERTAIN not in he:
            raise Inconclusive(f"E1: host never scheduled {CERTAIN}: {he}")
        owner0 = he[CERTAIN][1]
        results["E1 month-0 owner"] = (owner0 == PLAYERS[0], f"host events={he}")
        # A 30-minute countdown step may land between the two reads.
        same = (set(ce) == set(he)
                and all(ce[n][1] == he[n][1] and abs(ce[n][0] - he[n][0]) <= 30 for n in he))
        results["E2 one schedule"] = (same, f"host={he} client={ce}")
        picked = sorted(RANDOM & set(he))
        results["E3 one random pick"] = (
            len(picked) == 1 and he[picked[0]][1] == owner0,
            f"picked={picked} owners={[he[p][1] for p in picked]}")
        results["E4 owner only, shared research"] = fire(host, client, CERTAIN, "E4", True)

        for gc in (host, client):
            gc.ok({"cmd": "discover_research", "topic": "STR_COOP_EV_TRIGGER"})
        roll_month(host, client)
        he = events(host)
        if COND not in he:
            raise Inconclusive(f"E5: host did not schedule {COND} at month 1: {he}")
        ok_owner = he[COND][1] == other(owner0) and COND_HOST not in he
        ok_fire, detail = fire(host, client, COND, "E5", True)
        results["E5 next owner, shared research"] = (
            ok_owner and ok_fire, f"month-1 events={he} {detail}")
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
            raise Inconclusive(f"E7: host never scheduled {CERTAIN}: {he}")
        owner0 = he[CERTAIN][1]
        ok_fire, detail = fire(host, client, CERTAIN, "E7", False)
        results["E7 owner only, private research"] = (
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
            raise Inconclusive(f"E8: host did not schedule {COND_HOST} at month 1: {he}")
        ok_sched = he[COND_HOST][1] == owner1 and COND not in he
        ok_fire, detail = fire(host, client, COND_HOST, "E8", False)
        results["E8 owner's trigger, private research"] = (
            ok_sched and ok_fire, f"month-1 events={he} {detail}")
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
        sys.exit(3)
    if not all(ok for ok, _ in results.values()):
        sys.exit(2)
    print("PASS: Separate events belong to the month's rotation owner")
    sys.exit(0)


if __name__ == "__main__":
    main()
