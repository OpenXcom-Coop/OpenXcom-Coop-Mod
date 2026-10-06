"""Regression test: completing research on an already-known topic must not crash.

Bug (player report, v2.0.6 + X-Com Files, SEPARATE co-op: "random black screen
crash a couple of days into the run"): GeoscapeState::time1Day passes
newResearch = nullptr to ResearchCompleteState when the finished topic (or its
lookup) is already researched. The SEPARATE research-sync packet in the
ResearchCompleteState constructor then read newResearch->getName() -> access
violation at address 0x18. Symbolized player dump: Json::Value::Value <-
ResearchCompleteState::ResearchCompleteState (ResearchCompleteState.cpp:103) <-
GeoscapeState::time1Day. In the dump the topic was XCF's STR_SECRET_FILES_1,
which XCF lets a player research again while it still has getOneFree rewards.

Rows (vanilla rules, no external mod):
  A  SEPARATE: the host re-researches a topic it already knows (the XCF
     repeatable-topic shape). RED: the host crashes on the daily tick.
  B  SEPARATE: both players research the same topic; the host finishes first,
     research sync marks it known on the client, then the client's own project
     finishes. RED: the client crashes.
  S  SHARED: the host re-researches a known topic. The SHARED path never sends
     the SEPARATE packet (and research_done already carries "" for a null
     newResearch), so this row is green before and after the fix; it guards the
     SHARED path against the same crash.

  * PASS (exit 0): every row completes the project with both processes alive.
  * FAIL (exit 2): a game process crashed (the bug).
  * FAIL (exit 3): a precondition never held (e.g. sync never delivered the
    host's completion); the test proved nothing.
"""
import glob
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, HERE)
import harness  # noqa: E402
import session  # noqa: E402
import geo  # noqa: E402
import shared_fixture  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

PORT = "47962"
SHARED_PORTS = (48961, 48962, 47963)
RELEASE_DIR = os.path.dirname(harness.EXE)
TOPIC_A = "STR_MOTION_SCANNER"
TOPIC_B = "STR_LASER_WEAPONS"
TOPIC_S = "STR_MEDI_KIT"
DAY = 26 * 60  # one daily tick plus slack, in game minutes


class Inconclusive(Exception):
    pass


def crash_logs():
    hits = []
    for root in (harness.TEST_ROOT, RELEASE_DIR):
        hits += glob.glob(os.path.join(root, "**", "crash_*.log"), recursive=True)
    return set(hits)


def is_real_crash(path):
    # Every instance writes a "std::terminate called (no active exception)" log
    # on a normal quit; only a fault record marks a crash.
    with open(path, "r", errors="replace") as f:
        txt = f.read()
    return "SEH exception" in txt or "no active exception" not in txt


def research_names(gc):
    g = gc.ok({"cmd": "geo_state"})
    for b in g["bases"]:
        if not b["coopBase"] and not b["coopIcon"]:
            return [r["name"] for r in b["research"]]
    return []


def researched(gc, topic):
    return gc.ok({"cmd": "is_researched", "topic": topic})["researched"]


def advance_day(host, client, label):
    r = geo.skip_ingame_time(host, client, minutes=DAY, speed_idx=5,
                             real_timeout=90, stuck_timeout=40)
    print(f"[{label}] advanced {r['game_minutes']} min, dismissed={r['dismissed']}")


def separate_rows(host, client):
    # Row A: the host completes a topic it already knows -> newResearch == nullptr.
    geo.slow_clock(host, client)
    host.ok({"cmd": "discover_research", "topic": TOPIC_A})
    host.ok({"cmd": "start_research", "topic": TOPIC_A, "cost": 1, "scientists": 1})
    advance_day(host, client, "A")
    if TOPIC_A in research_names(host):
        raise Inconclusive(f"row A: host project {TOPIC_A} never completed")
    client.wait_for("row A: client got the host's completion via research sync",
                    lambda: researched(client, TOPIC_A) or None, timeout=30, interval=0.5)
    print(f"PASS row A: host re-researched known {TOPIC_A}, sync reached the client")

    # Row B: the host finishes first; sync marks the topic known on the client
    # while the client's own project is still running; then the client's finishes.
    geo.slow_clock(host, client)
    host.ok({"cmd": "start_research", "topic": TOPIC_B, "cost": 1, "scientists": 1})
    client.ok({"cmd": "start_research", "topic": TOPIC_B, "cost": 100000, "scientists": 1})
    advance_day(host, client, "B1")
    try:
        client.wait_for("row B: client got the host's completion via research sync",
                        lambda: researched(client, TOPIC_B) or None, timeout=30, interval=0.5)
    except TimeoutError:
        raise Inconclusive("row B: research sync never delivered the host's completion")
    if TOPIC_B not in research_names(client):
        raise Inconclusive(f"row B: client project {TOPIC_B} ended before its own completion")
    geo.slow_clock(host, client)
    client.ok({"cmd": "set_research_cost", "topic": TOPIC_B, "cost": 1})
    advance_day(host, client, "B2")
    if TOPIC_B in research_names(client):
        raise Inconclusive(f"row B: client project {TOPIC_B} never completed")
    print(f"PASS row B: client completed {TOPIC_B} after sync had marked it known")


def shared_row(out):
    js = shared_fixture.bring_up("rkts", SHARED_PORTS)
    host, client = js.host, js.client
    try:
        geo.slow_clock(host, client)
        for gc in (host, client):  # keep the shared world identical
            gc.ok({"cmd": "discover_research", "topic": TOPIC_S})
            gc.ok({"cmd": "start_research", "topic": TOPIC_S, "cost": 1, "scientists": 1})
        advance_day(host, client, "S")
        if TOPIC_S in research_names(host):
            raise Inconclusive(f"row S: host project {TOPIC_S} never completed")
        client.wait_for("row S: replica applied research_done",
                        lambda: (TOPIC_S not in research_names(client)) or None,
                        timeout=30, interval=0.5)
        print(f"PASS row S: SHARED host re-researched known {TOPIC_S}")
    finally:
        time.sleep(1.5)
        out["rc"] = (host.proc.poll(), client.proc.poll())
        js.shutdown()


def main():
    assert os.path.isfile(harness.EXE), "no exe (set OXC_TEST_EXE): " + harness.EXE
    pre = crash_logs()
    host = GameClient("host", 48963, make_user_dir("rkt_host"))
    client = GameClient("client", 48964, make_user_dir("rkt_client"))
    host.spawn(); client.spawn()
    host.connect(); client.connect()
    note = None
    inconclusive = None
    try:
        session.new_campaign(host, client, port=PORT)
        geo.wait_both_ready(host, client)
        separate_rows(host, client)
    except Inconclusive as e:
        inconclusive = str(e)
    except Exception as e:  # a dropped socket mid-command == a crash
        note = f"{type(e).__name__}: {e}"
    finally:
        time.sleep(1.5)
        sep_rc = (host.proc.poll(), client.proc.poll())
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception:
                pass

    shared = {"rc": (None, None)}
    if note is None and inconclusive is None and sep_rc == (None, None):
        try:
            shared_row(shared)
        except Inconclusive as e:
            inconclusive = str(e)
        except Exception as e:
            note = f"{type(e).__name__}: {e}"

    new_logs = sorted(p for p in crash_logs() - pre if is_real_crash(p))
    crashed = bool(new_logs) or sep_rc != (None, None) or shared["rc"] != (None, None)
    print("==== RESULT ====")
    print("separate rc (host, client):", sep_rc, "| shared rc:", shared["rc"],
          "| new crash logs:", [os.path.basename(x) for x in new_logs],
          "| note:", note, "| inconclusive:", inconclusive)
    for p in new_logs:
        with open(p, "r", errors="replace") as f:
            sys.stdout.write(f.read())

    if crashed:
        print("FAIL: completing research on an already-known topic crashed the game")
        sys.exit(2)
    if inconclusive or note:
        print("INCONCLUSIVE:", inconclusive or note)
        sys.exit(3)
    print("PASS: research on an already-known topic completes without a crash (SEPARATE + SHARED)")
    sys.exit(0)


if __name__ == "__main__":
    main()
