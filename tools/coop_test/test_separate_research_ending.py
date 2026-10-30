"""Separate campaign: a research topic whose cutscene is a win or lose video ends
the campaign for both players together.

The host's daily research step completes every base's project. A completed topic
whose cutscene is the win or lose video counts as the research owner's faction
finale: the players lose together and win together. A loss always ends the
campaign on both machines. A win ends it on both machines when the players share
a faction (always so in vanilla). When their factions differ, a win completes
only the owner's faction: nothing ends, and the continue-or-end vote is queued
for the owner (test_separate_campaign_finale_session.py covers that vote).

Rows, each in its own fresh Separate campaign with private research, since an
ending tears the session down (vanilla rules plus the test mod
Coop_SeparateResearch_Test, whose STR_COOP_SR_WIN_TOPIC / STR_COOP_SR_LOSE_TOPIC
play the stock winGame / loseGame videos):
  1  same faction, the client's base completes the win topic:
     both machines reach END_WIN.
  2  same faction, the host's base completes the lose topic:
     both machines reach END_LOSE.
  3  different factions, the client's base completes the lose topic:
     both machines reach END_LOSE.
  4  different factions, the host's base completes the win topic:
     neither machine ends; the pending faction finale owner is HostPlayer on the
     host and on the client.

  * PASS (exit 0): every row holds.
  * FAIL (exit 1): a row failed. Exit 2: a game process died.

Run:  py -3 tools/coop_test/test_separate_research_ending.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import geo  # noqa: E402
import shared_fixture  # noqa: E402

MOD = os.path.join(HERE, "mods", "Coop_SeparateResearch_Test")
WIN_TOPIC = "STR_COOP_SR_WIN_TOPIC"
LOSE_TOPIC = "STR_COOP_SR_LOSE_TOPIC"
END_NONE, END_WIN, END_LOSE = 0, 1, 2
ENDING_NAME = {END_NONE: "END_NONE", END_WIN: "END_WIN", END_LOSE: "END_LOSE"}
DAY = 26 * 60  # one daily research step plus slack, in game minutes

ROWS = (
    # (row, factions differ, base that completes the topic, topic, expected ending)
    ("same faction, client wins", False, "ClientBase", WIN_TOPIC, END_WIN),
    ("same faction, host loses", False, "HostBase", LOSE_TOPIC, END_LOSE),
    ("different factions, client loses", True, "ClientBase", LOSE_TOPIC, END_LOSE),
    ("different factions, host wins", True, "HostBase", WIN_TOPIC, END_NONE),
)
OWNER = {"HostBase": "HostPlayer", "ClientBase": "ClientPlayer"}


def ending(gc):
    return gc.ok({"cmd": "ending_state"})["ending"]


def finale_owner(gc):
    return gc.ok({"cmd": "get_coop"}).get("factionFinale", {}).get("owner", "")


def research_names(gc, base):
    for b in gc.ok({"cmd": "geo_state"})["bases"]:
        if b["name"] == base:
            return [r["name"] for r in b["research"]]
    return []


def completed_research(gc, player):
    state = gc.ok({"cmd": "separate_profile_state"})
    for p in state["players"]:
        if p["name"] == player:
            return set(p.get("completedResearch", []))
    return set()


def run_row(index, row, different, base, topic, want):
    js = shared_fixture.bring_up(
        f"sre{index}", (49170 + 2 * index, 49171 + 2 * index, 48370 + index),
        mods=[MOD], campaign_mode="coop", host_base="HostBase", client_base="ClientBase")
    host, client = js.host, js.client
    try:
        host.ok({"cmd": "set_option", "name": "EnableResearchSync", "value": False})
        if different:
            # Keep both replicas of the one world equal.
            for gc in (host, client):
                for player, faction in (("HostPlayer", "faction:A"), ("ClientPlayer", "faction:B")):
                    gc.ok({"cmd": "separate_profile_set", "player": player, "faction": faction})
        state = host.ok({"cmd": "separate_profile_state"})
        assert state["researchSharingEnabled"] is False, \
            f"{row}: precondition: research is not private ({state['researchSharingEnabled']})"
        assert state["differentFactions"] is different, \
            f"{row}: precondition: differentFactions={state['differentFactions']}, expected {different}"
        for gc in (host, client):
            assert ending(gc) == END_NONE, f"{row}: precondition: {gc.name} already ended"

        geo.slow_clock(host, client)
        for gc in (host, client):  # keep both replicas of the one world equal
            gc.ok({"cmd": "start_research", "base": base, "topic": topic,
                   "cost": 1, "scientists": 1})

        def settled(gc):
            return (ending(gc) != END_NONE or bool(finale_owner(gc))) or None

        # The ending's screens are what the row waits for: the time skip's closing
        # sweep keeps them instead of closing them like any other popup.
        settled.keep = ("CutsceneState", "SlideshowState", "StatisticsState")

        r = geo.skip_ingame_time(host, client, minutes=DAY, speed_idx=4, interest=settled,
                                 real_timeout=90, stuck_timeout=40)
        print(f"[{row}] advanced {r['game_minutes']} min, hit={r['hit']}, "
              f"dismissed={r['dismissed']}")

        if want == END_NONE:
            # The win completes the owner's faction only: no ending anywhere, and
            # the owner's finale vote is pending on both machines.
            assert topic not in research_names(host, base), \
                f"{row}: precondition: the host's research step never completed {topic} at {base}"
            assert topic in completed_research(host, OWNER[base]), \
                f"{row}: precondition: {topic} was not credited to {OWNER[base]}"
            host_owner = finale_owner(host)
            try:
                client_owner = client.wait_for(
                    f"{row}: client pending finale owner",
                    lambda: finale_owner(client) or None, timeout=20, interval=0.25)
            except TimeoutError:
                client_owner = finale_owner(client)
            time.sleep(2.0)  # an ending sent with the completion would have landed by now
            got = {gc.name: ENDING_NAME.get(ending(gc), ending(gc)) for gc in (host, client)}
            print(f"[{row}] endings={got} finale owner host={host_owner!r} client={client_owner!r}")
            assert got == {"host": "END_NONE", "client": "END_NONE"}, \
                f"{row}: endings {got}, expected END_NONE on both"
            assert host_owner == "HostPlayer", \
                f"{row}: host pending finale owner {host_owner!r}, expected 'HostPlayer'"
            assert client_owner == "HostPlayer", \
                f"{row}: client pending finale owner {client_owner!r}, expected 'HostPlayer'"
        else:
            got = {}
            for gc in (host, client):
                try:
                    value = gc.wait_for(f"{row}: {gc.name} ending",
                                        lambda gc=gc: ending(gc) or None,
                                        timeout=30, interval=0.25)
                except TimeoutError:
                    value = ending(gc)
                got[gc.name] = ENDING_NAME.get(value, value)
            print(f"[{row}] endings={got}")
            want_name = ENDING_NAME[want]
            assert got == {"host": want_name, "client": want_name}, \
                f"{row}: endings {got}, expected {want_name} on both"
        print(f"PASS row {index} ({row})")
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        js.shutdown()
    return alive


def main():
    failed = []
    died = []
    for index, (row, different, base, topic, want) in enumerate(ROWS, start=1):
        try:
            if not run_row(index, row, different, base, topic, want):
                died.append(row)
                print(f"FAIL row {index} ({row}): a game process died")
        except AssertionError as e:
            failed.append(row)
            print(f"FAIL row {index}: {e}")
    if died:
        print("FAIL: a game process died in: " + ", ".join(died))
        sys.exit(2)
    if failed:
        print("FAIL rows: " + ", ".join(failed))
        sys.exit(1)
    print("PASS: a research ending ends the Separate campaign for both players together")


if __name__ == "__main__":
    main()
