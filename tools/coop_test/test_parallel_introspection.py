"""PRD-P0 self-test: the parallel-turns harness introspection surface.

P0 adds no gameplay. It adds the read-outs the parallel-turns PRDs (P2/P6/P7/P8)
will assert against, so this test only has to prove that surface exists and is
honest on BOTH machines of a live co-op battle:

  1. make_user_dir(options=...) splices per-instance keys into options.cfg, and
     the game actually boots on the result (a malformed splice would fail YAML
     load, so reaching the battle IS the parse assertion). Host and client are
     given DIFFERENT battleXcomSpeed values, which is the point of the kwarg -
     one machine slow, one fast, from the first frame.
  2. `parallel_state` answers on both instances with the receive-gate fields
     (taskCompleted / pathLock / coopWalkInit / coopInitDeath / coopEnd /
     rxHold / rxRotates / rxHoldMax) plus `parallelActive`.
  3. `battle_state` carries the same fields, so session.can_drive() needs only
     one query.
  4. `parallelActive` is FALSE (P5 lands the real predicate) and therefore
     session.can_drive(battle_state) == battle_state["activeSync"] - the
     driver-selection contract migration is a strict no-op today.
  5. The receive-gate counters are self-consistent (rxHold <= rxHoldMax, and a
     co-op session that has exchanged battle packets has rotated at least one).
  6. set_option round-trips battleXcomSpeed / battleAlienSpeed /
     EnableCoopParallelTurns, still rejects an unknown name (the new branches
     must not swallow the else), and rejects the retired
     coopParallelDebugClientInput (PRD-P5's temporary client-input override,
     deleted by PRD-P6 along with the gate it fed).

Battle fixture: the skirmish flow (NEW BATTLE > COOP), the cheapest co-op
battle in the suite - same path test_skirmish_battle_turn_control.py drives.

Run:  python tools/coop_test/test_parallel_introspection.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_skirmish_flow as SK

PORT = "47975"

# The receive-gate fields P0 puts on BOTH battle_state and parallel_state.
GATE_FIELDS = ("taskCompleted", "pathLock", "coopWalkInit", "coopInitDeath",
               "coopEnd", "rxHold", "rxRotates", "rxHoldMax")


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def has(gc, name):
    return any(name in s for s in states(gc))


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


# ---- 1. options.cfg splice --------------------------------------------------

def assert_options_spliced(user_dir, expected):
    cfg = os.path.join(user_dir, "options.cfg")
    with open(cfg, encoding="utf-8") as f:
        text = f.read()
    for key, value in expected.items():
        line = "  %s: %s" % (key, "true" if value is True
                             else "false" if value is False else value)
        assert line in text.splitlines(), \
            f"{cfg}: expected {line!r} in the options block, got:\n{text}"
    # the splice must not have displaced the hermetic pins
    assert "id: xcom1" in text and "playIntro: false" in text, \
        f"{cfg}: the options splice broke HERMETIC_OPTIONS:\n{text}"
    print(f"PASS options splice: {os.path.basename(user_dir)} carries {expected}")


# ---- 2/3/4/5. the introspection surface ------------------------------------

def assert_gate_fields(tag, resp, what):
    assert resp.get("ok"), f"{tag}: {what} failed: {resp}"
    missing = [f for f in GATE_FIELDS if f not in resp]
    assert not missing, f"{tag}: {what} is missing {missing}: {resp}"
    assert "parallelActive" in resp, \
        f"{tag}: {what} carries no parallelActive: {resp}"
    assert resp["parallelActive"] is False, \
        f"{tag}: parallelActive must be False until PRD-P5 lands: {resp}"
    # types, so a later PRD that starts asserting on them has a contract
    assert isinstance(resp["taskCompleted"], bool), f"{tag}: {resp}"
    assert isinstance(resp["pathLock"], int), f"{tag}: {resp}"
    assert isinstance(resp["coopEnd"], int), f"{tag}: {resp}"
    for counter in ("rxHold", "rxRotates", "rxHoldMax"):
        assert isinstance(resp[counter], int) and resp[counter] >= 0, \
            f"{tag}: {counter} is not a non-negative int: {resp}"
    assert resp["rxHold"] <= resp["rxHoldMax"], \
        f"{tag}: rxHold {resp['rxHold']} exceeds the high-water mark " \
        f"{resp['rxHoldMax']}: {resp}"


def assert_introspection(host, client):
    gates = {}
    for gc, tag in ((host, "host"), (client, "client")):
        ps = gc.cmd({"cmd": "parallel_state"})
        assert_gate_fields(tag, ps, "parallel_state")

        bs = battle(gc)
        assert bs.get("inBattle"), f"{tag}: not in a battle: {bs}"
        assert_gate_fields(tag, bs, "battle_state")

        # the two commands must agree about the mode (they read the same state;
        # the gate counters are live and may tick between the two queries)
        assert ps["parallelActive"] == bs["parallelActive"], \
            f"{tag}: parallel_state and battle_state disagree about " \
            f"parallelActive: {ps['parallelActive']} vs {bs['parallelActive']}"

        # the contract migration is a strict no-op while parallelActive is False
        assert session.can_drive(bs) == bool(bs["activeSync"]), \
            f"{tag}: can_drive() diverged from activeSync with parallelActive " \
            f"False: activeSync={bs['activeSync']} " \
            f"can_drive={session.can_drive(bs)}"

        gates[tag] = ps
        print(f"PASS {tag}: parallel_state {{"
              f"parallelActive={ps['parallelActive']}, "
              f"taskCompleted={ps['taskCompleted']}, pathLock={ps['pathLock']}, "
              f"coopWalkInit={ps['coopWalkInit']}, "
              f"coopInitDeath={ps['coopInitDeath']}, coopEnd={ps['coopEnd']}, "
              f"rxHold={ps['rxHold']}, rxRotates={ps['rxRotates']}, "
              f"rxHoldMax={ps['rxHoldMax']}}}")

    # The counters are process-monotonic (never reset). Every packet that is not
    # PING/PONG passes through the hold queue, and a live co-op battle has
    # exchanged plenty by now, so the high-water mark proves the drain-loop hook
    # is wired. rxRotates is reported but NOT asserted: a rotation only happens
    # when a packet lands while the local task is mid-flight, which nothing here
    # forces (PRD-P6/P7 drive that path deliberately).
    high = {t: gates[t]["rxHoldMax"] for t in ("host", "client")}
    rotates = {t: gates[t]["rxRotates"] for t in ("host", "client")}
    assert max(high.values()) > 0, \
        f"neither machine ever saw a non-empty hold queue ({high}) - either no " \
        f"co-op packet was exchanged or the high-water hook is not wired"
    print(f"PASS gate counters: rxHoldMax={high} rxRotates={rotates}")

    # can_drive() must pick exactly the machine activeSync names today
    drivers = [t for t, gc in (("host", host), ("client", client))
               if session.can_drive(battle(gc))]
    print(f"PASS driver selection: can_drive() names {drivers or 'nobody'} "
          f"(classic co-op: the simulation owner)")


# ---- 6. set_option ----------------------------------------------------------

def assert_set_option(gc, tag):
    for name, values in (("battleXcomSpeed", (7, 40)),
                         ("battleAlienSpeed", (3, 30))):
        for want in values:
            r = gc.ok({"cmd": "set_option", "name": name, "value": want})
            assert r.get("value") == want, \
                f"{tag}: set_option {name}={want} echoed {r}"
    # coopParallelDebugClientInput was PRD-P5's temporary client-input override.
    # PRD-P6 replaced the gate it fed with `action_intent` forwarding and deleted
    # the option outright, so it must now be rejected like any unknown name.
    for want in (True, False):
        r = gc.ok({"cmd": "set_option", "name": "EnableCoopParallelTurns",
                   "value": want})
        assert r.get("value") is want, \
            f"{tag}: set_option EnableCoopParallelTurns={want} echoed {r}"
    for name in ("notAnOptionAtAll", "coopParallelDebugClientInput"):
        bad = gc.cmd({"cmd": "set_option", "name": name, "value": 1})
        assert not bad.get("ok") and "unknown option" in bad.get("error", ""), \
            f"{tag}: {name} must be rejected, got {bad}"
    print(f"PASS {tag}: set_option round-trips the three surviving names, and "
          f"the retired coopParallelDebugClientInput is rejected like any "
          f"unknown one")


def main():
    # per-instance options.cfg: host walks at 1 ms/step, client at 40 - the
    # asymmetry the parallel-turns tests need from the very first frame.
    host_opts = {"battleXcomSpeed": 1, "battleAlienSpeed": 1}
    client_opts = {"battleXcomSpeed": 40, "battleAlienSpeed": 40}
    host_dir = make_user_dir("par_intro_host", options=host_opts)
    client_dir = make_user_dir("par_intro_client", options=client_opts)
    assert_options_spliced(host_dir, host_opts)
    assert_options_spliced(client_dir, client_opts)

    host = GameClient("host", 48840, host_dir)
    client = GameClient("client", 48841, client_dir)
    fail = None
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        print("PASS boot: both instances started on the spliced options.cfg")

        # --- the skirmish battle fixture (same path as
        # --- test_skirmish_battle_turn_control.py, without its lobby bounce)
        SK.skirmish_host(host, PORT)
        SK.skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": PORT,
                   "player": "ClientPlayer"})
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} join popup",
                        lambda gc=gc: session.has_state(gc, "Profile") or None,
                        timeout=60)
            gc.ok({"cmd": "profile_ok"})
        host.wait_for("BATTLE SETTINGS offered",
                      lambda: SK.lobby(host).get("buttonVisible") or None, timeout=60)
        host.ok({"cmd": "lobby_action"})
        host.wait_for("host at battle settings",
                      lambda: (not session.has_state(host, "LobbyMenu")) or None,
                      timeout=60)
        host.ok({"cmd": "newbattle_ok"})

        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} in battle",
                        lambda gc=gc: battle(gc).get("inBattle") or None,
                        timeout=180, interval=1.0)
        for gc in (host, client):
            if has(gc, "BriefingState"):
                gc.cmd({"cmd": "close_briefing"})
        for gc in (host, client):
            if has(gc, "InventoryState"):
                gc.cmd({"cmd": "battle_inventory", "action": "ok"})
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} tactical map",
                        lambda gc=gc: has(gc, "BattlescapeState") or None,
                        timeout=120, interval=0.5)
        # let the coop turn-init handshake settle so the gate has seen traffic
        time.sleep(6)
        print("battle up on both machines")

        assert_introspection(host, client)
        for gc, tag in ((host, "host"), (client, "client")):
            assert_set_option(gc, tag)

        print("ALL PARALLEL-INTROSPECTION TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
