"""Regression test: SEPARATE geoscape events - certain events reach both players at
the same time, random events stay random, and event research follows research sync.

Player report (X-Com Files): the intro "advisors" (four events with 100% odds and one
possible event each) "sometimes only happen to one player". Two causes:
  * the client never ran its game-start event roll: its time sync copied the
    host's monthsPassed (-1 -> 0) before GeoscapeState::init's run-once block could
    fire, so the client only rolled those events at its first month change;
  * each machine rolls an event's random delay on its own, so even an event both
    players get arrives at different times.
With research sync on, research granted by an event only one player got never
reached the other player.

Fixture mod Coop_EventSync_Test (same shape as the XCF advisors):
  STR_COOP_EV_CERTAIN    month 0, odds 100, one possible event      -> certain
  STR_COOP_EV_RANDOM_A/B month 0, 50/50 pick                          -> random
  STR_COOP_EV_COND       month 1+, certain once STR_COOP_EV_TRIGGER is known
  STR_COOP_EV_COND_HOST  month 1+, certain once STR_COOP_EV_TRIGGER_HOST is known
Delays are 60 + random(20000) minutes, so independent rolls practically never match.

Session 1 (research sync on):
  E1 the client schedules the certain month-0 event at campaign start.
  E2 both players' certain event has the same countdown (the host's).
  E3 each player rolls its own random month-0 event (exactly one of A/B each).
  E4 the certain event fires for both when the host's copy fires (only the host's
     countdown is shortened; the client's copy follows the host's signal, since the
     client clock can skip 30-minute steps), both players open its article, and
     neither gets a research-sync "Research Completed" popup for it.
  E5 both know STR_COOP_EV_TRIGGER at the month change: both get STR_COOP_EV_COND,
     and the client's copy fires when the host's does (only the host's countdown is
     shortened), with no research-sync popup.
  E6 only the host knows STR_COOP_EV_TRIGGER_HOST: only the host gets the event;
     when it fires, research sync gives the client the topic with a popup whose
     VIEW REPORTS opens the article.
Session 2 (research sync off):
  E7 the client schedules the certain event with the host's countdown.
  E8 the host-only event's research does not reach the client.

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
from harness import GameClient, make_user_dir  # noqa: E402

MOD = os.path.join(HERE, "mods", "Coop_EventSync_Test")
CERTAIN, COND, COND_HOST = "STR_COOP_EV_CERTAIN", "STR_COOP_EV_COND", "STR_COOP_EV_COND_HOST"
RANDOM = {"STR_COOP_EV_RANDOM_A", "STR_COOP_EV_RANDOM_B"}


class Inconclusive(Exception):
    pass


def events(gc):
    return {e["name"]: e["countdown"] for e in gc.ok({"cmd": "geo_events"})["events"] if not e["over"]}


def known(gc, topic):
    return gc.ok({"cmd": "is_researched", "topic": topic})["researched"]


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
    # speed 4 (1 hour per step): at speed 5 the host clock overwrites the
    # SEPARATE client's mid-step and the client's own ticks can be skipped.
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


def bring_up(tag, sync):
    opts = {"EnableResearchSync": sync}
    host = GameClient("host", 48993, make_user_dir(tag + "_host", mods=[MOD], options=opts))
    client = GameClient("client", 48994, make_user_dir(tag + "_client", mods=[MOD], options=opts))
    host.spawn(); client.spawn()
    host.connect(); client.connect()
    session.new_campaign(host, client, port="47995" if sync else "47996")
    geo.wait_both_ready(host, client)
    time.sleep(2.0)  # let the host's event schedule reach the client
    for gc in (host, client):
        geo.drain_popups(gc)
    geo.slow_clock(host, client)
    return host, client


def roll_month(host, client):
    host.ok({"cmd": "set_geo_day", "day": 31, "hour": 23})
    seen = advance(host, client, 120)
    time.sleep(2.0)
    return seen


def same_countdown(a, b):
    return a is not None and b is not None and a == b


def session_sync_on(results):
    host, client = bring_up("evsync", True)
    try:
        he, ce = events(host), events(client)
        if CERTAIN not in he:
            raise Inconclusive(f"E1: host never scheduled {CERTAIN}: {he}")
        results["E1 client game-start roll"] = (CERTAIN in ce, f"client events={ce}")
        results["E2 shared delay"] = (same_countdown(he.get(CERTAIN), ce.get(CERTAIN)),
                                      f"host={he.get(CERTAIN)} client={ce.get(CERTAIN)}")
        results["E3 random stays per player"] = (
            len(RANDOM & set(he)) == 1 and len(RANDOM & set(ce)) == 1,
            f"host={sorted(RANDOM & set(he))} client={sorted(RANDOM & set(ce))}")

        # E4: fire the host's copy soon; the client's copy must fire with it
        if CERTAIN in ce:
            host.ok({"cmd": "set_event_countdown", "name": CERTAIN, "minutes": 60})
            seen = advance(host, client, 180)
            topic = "article:STR_COOP_EV_CERTAIN_TOPIC"
            ok = all(topic in seen[gc.name] and "RC" not in seen[gc.name] for gc in (host, client))
            results["E4 one report each, no sync popup"] = (ok, f"host={seen[host.name]} client={seen[client.name]}")
        else:
            results["E4 one report each, no sync popup"] = (False, "client has no certain event")

        # E5/E6: month-1 conditional events
        for gc in (host, client):
            gc.ok({"cmd": "discover_research", "topic": "STR_COOP_EV_TRIGGER"})
        host.ok({"cmd": "discover_research", "topic": "STR_COOP_EV_TRIGGER_HOST"})
        roll_month(host, client)
        he, ce = events(host), events(client)
        if COND not in he or COND_HOST not in he:
            raise Inconclusive(f"E5/E6: host did not schedule the month-1 events: {he}")
        if COND_HOST in ce:
            raise Inconclusive(f"E6: client scheduled {COND_HOST} without its trigger")
        if COND in ce:
            if ce[COND] <= 180:
                # the client's own delay would fire it inside the window by itself
                raise Inconclusive(f"E5: client countdown {ce[COND]} fires within the 180-minute window on its own")
            host.ok({"cmd": "set_event_countdown", "name": COND, "minutes": 60})
            seen = advance(host, client, 180)
            topic = "article:STR_COOP_EV_COND_TOPIC"
            ok = all(topic in seen[gc.name] and "RC" not in seen[gc.name] for gc in (host, client))
            results["E5 conditional, both qualify"] = (ok, f"countdowns host={he.get(COND)} client={ce.get(COND)} "
                                                           f"host={seen[host.name]} client={seen[client.name]}")
        else:
            results["E5 conditional, both qualify"] = (False, f"client never scheduled {COND}: {ce}")
        host.ok({"cmd": "set_event_countdown", "name": COND_HOST, "minutes": 60})
        seen = advance(host, client, 180)
        topic = "STR_COOP_EV_COND_HOST_TOPIC"
        ok = known(client, topic) and "RC" in seen[client.name] and "article:" + topic in seen[client.name]
        results["E6 host-only event research synced"] = (ok, f"client knows={known(client, topic)} "
                                                             f"client popups={seen[client.name]}")
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception:
                pass
    return alive


def session_sync_off(results):
    host, client = bring_up("evnosync", False)
    try:
        he, ce = events(host), events(client)
        results["E7 shared delay, sync off"] = (same_countdown(he.get(CERTAIN), ce.get(CERTAIN)),
                                                f"host={he.get(CERTAIN)} client={ce.get(CERTAIN)}")
        host.ok({"cmd": "discover_research", "topic": "STR_COOP_EV_TRIGGER_HOST"})
        roll_month(host, client)
        if COND_HOST not in events(host):
            raise Inconclusive("E8: host did not schedule the host-only event")
        host.ok({"cmd": "set_event_countdown", "name": COND_HOST, "minutes": 60})
        seen = advance(host, client, 180)
        topic = "STR_COOP_EV_COND_HOST_TOPIC"
        if not known(host, topic):
            raise Inconclusive("E8: host event never granted its topic")
        results["E8 sync off keeps research separate"] = (not known(client, topic),
                                                          f"client knows={known(client, topic)} popups={seen[client.name]}")
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception:
                pass
    return alive


def main():
    results = {}
    note = None
    alive = True
    try:
        alive = session_sync_on(results) and alive
        alive = session_sync_off(results) and alive
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
    print("PASS: SEPARATE certain events are shared in time, random events stay random")
    sys.exit(0)


if __name__ == "__main__":
    main()
