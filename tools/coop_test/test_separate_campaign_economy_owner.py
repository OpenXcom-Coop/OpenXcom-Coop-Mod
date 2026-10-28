"""Separate Campaign: host-simulated money lands in the right player's wallet.

One host-authoritative world, one wallet per player. Every row below is money
the HOST moves without a player command, so no command initiator selects the
wallet. Each row checks the host's authoritative wallets and the client's
replica copy.

  PROD   hourly production at the CLIENT's base charges the client's wallet
         for each further unit (host wallet untouched).
  EVENT  a geoscape event owned by the client credits the client's wallet; the
         client replica only displays it (no second credit on the replica).
  BONUS  the monthly performance bonus is split like country funding: each
         wallet gets bonus / player count, identically on both machines (RU7).
  DEBT   debt defeat judges the SUM of both wallets once, on the host (RU2):
         one player negative but the total positive -> no warning anywhere;
         total negative -> the same warning on both; still negative at the
         next month end -> campaign-wide defeat on both.

A throwaway mod (generated into the isolated user dirs, same on both machines)
adds a research-free manufacture, a funds event and a performance bonus factor.
Rows run in order and every failure is reported before the exit code.

Run:  py -3 tools/coop_test/test_separate_campaign_economy_owner.py
"""

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture as fixture

MOD_NAME = "Coop_UnitC_Economy_Test"
WIDGET = "STR_COOP_UNITC_RIFLE"
WIDGET_COST = 1000
WIDGET_TIME = 5
EVENT = "STR_COOP_UNITC_FUNDS"
EVENT_FUNDS = 70000
BONUS_FACTOR = 100

METADATA = """\
name: "Coop unit C economy test"
version: 1.0
description: "Test-only: research-free manufacture, a funds event, a performance bonus."
author: coop harness

master: xcom1
"""

RULESET = f"""\
performanceBonusFactor: {BONUS_FACTOR}
manufacture:
  - name: {WIDGET}
    category: STR_WEAPON
    space: 1
    time: {WIDGET_TIME}
    cost: {WIDGET_COST}
    producedItems:
      STR_RIFLE: 1
events:
  - name: {EVENT}
    description: {EVENT}
    funds: {EVENT_FUNDS}
"""

FAILURES = []


def make_mod(root):
    mod = os.path.join(root, MOD_NAME)
    os.makedirs(os.path.join(mod, "Ruleset"))
    with open(os.path.join(mod, "metadata.yml"), "w", encoding="utf-8") as f:
        f.write(METADATA)
    with open(os.path.join(mod, "Ruleset", "unitc_economy.rul"), "w", encoding="utf-8") as f:
        f.write(RULESET)
    return mod


def row(name, fn):
    try:
        fn()
        print(f"PASS {name}")
    except AssertionError as exc:
        FAILURES.append(name)
        print(f"FAIL {name}: {exc}")
    except TimeoutError as exc:
        FAILURES.append(name)
        print(f"FAIL {name}: {exc}")


def wallets(gc):
    return dict(gc.ok({"cmd": "month_report"})["playerFunds"])


def set_wallet(host, client, player, value):
    for gc in (host, client):
        gc.ok({"cmd": "set_funds", "player": player, "value": value})


def client_production(gc):
    base = next(b for b in fixture.geo(gc)["bases"] if b["name"] == "ClientBase")
    return next((p for p in base.get("productions", []) if p["item"] == WIDGET), None)


def has_state(gc, name):
    return any(name in s for s in gc.cmd({"cmd": "get_state"})["states"])


END_SCREENS = ("CutsceneState", "StatisticsState")


def run_clock(host, client, until, seconds, speed_idx=2, keep=()):
    """Advance both geoscapes until `until()` holds. Dialogs are closed through
    their OK handlers, except `keep` and the campaign's end screens (never
    popped raw), which stay open."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if until():
            return True
        for gc in (host, client):
            geo.drain_popups(gc, interest=geo.popup(*(END_SCREENS + tuple(keep))))
            if geo.on_geoscape(gc):
                gc.ok({"cmd": "geo_set_speed", "idx": speed_idx})
        time.sleep(0.3)
    return until()


def stop_clock(host, client):
    # Also under a popup: a clock left at the 1-day speed would roll the next
    # month while the test reads this one.
    for gc in (host, client):
        gc.cmd({"cmd": "geo_set_speed", "idx": 0})


def roll_month(host, client):
    """Jump the host to the month's last day and run until both rolled it.
    Each month gets a positive score, so the council's two-bad-months rating
    defeat never mixes into the debt rows."""
    host.ok({"cmd": "add_research_score", "points": 2000})
    old = fixture.geo(host)["monthsPassed"]
    host.ok({"cmd": "set_geo_day", "day": 28, "hour": 0})
    rolled = run_clock(host, client,
                       lambda: fixture.geo(host)["monthsPassed"] > old
                       and fixture.geo(client)["monthsPassed"] > old,
                       150, speed_idx=5)
    assert rolled, "month did not roll on both machines"
    stop_clock(host, client)
    for gc in (host, client):
        r = gc.ok({"cmd": "month_report"})
        print(f"  month {r['monthsPassed']} {gc.name}: warned={r['warned']} "
              f"wallets={r['playerFunds']} ending={gc.ok({'cmd': 'ending_state'})['ending']}")


def report_states(host, client):
    """Close the month's popups through their real OK handlers; return the
    campaign ending each machine reached (0 none, 2 lose)."""
    for _ in range(20):
        for gc in (host, client):
            # Never pop the end screens raw; the ending is already set by then.
            geo.drain_popups(gc, interest=geo.popup(*END_SCREENS))
        stop_clock(host, client)
        time.sleep(0.3)
    return {gc.name: gc.ok({"cmd": "ending_state"})["ending"] for gc in (host, client)}


def main():
    tmp = tempfile.mkdtemp(prefix="coop_unitc_economy_")
    try:
        mod = make_mod(tmp)
        js = fixture.bring_up("sep_unitc_economy", (49700, 49701, 49000), mods=[mod])
        host, client = js.host, js.client
        try:
            fixture.assert_fresh_named_world(host, client)
            geo.slow_clock(host, client)

            # PROD ---------------------------------------------------------
            def prod():
                set_wallet(host, client, "HostPlayer", 500000)
                set_wallet(host, client, "ClientPlayer", 500000)
                started = client.ok({"cmd": "manufacture_start", "base": "ClientBase",
                                     "item": WIDGET, "engineers": 5, "qty": 2})
                assert started.get("sent"), started
                host.wait_for("client production reaches the host",
                              lambda: client_production(host) or None,
                              timeout=30, interval=0.3)
                before = wallets(host)
                assert before["ClientPlayer"] == 500000 - WIDGET_COST, (
                    "first unit is charged by the command lane", before)
                # One more engineer-hour completes unit 1 and starts unit 2 in
                # the host's hourly production step.
                host.ok({"cmd": "set_production_progress", "base": "ClientBase",
                         "item": WIDGET, "timeSpent": WIDGET_TIME - 1})
                done = run_clock(host, client,
                                 lambda: (client_production(host) or {}).get("produced", 0) >= 1,
                                 60)
                stop_clock(host, client)
                assert done, f"no hourly step: {client_production(host)}"
                produced = client_production(host)["produced"]
                after = wallets(host)
                assert after["HostPlayer"] == before["HostPlayer"], (
                    "the host's wallet paid for production at the client's base",
                    before, after)
                # qty 2: completing unit 1 starts (and charges) unit 2 only.
                assert after["ClientPlayer"] == before["ClientPlayer"] - min(produced, 1) * WIDGET_COST, (
                    "the client's wallet was not charged for its further units",
                    produced, before, after)
                # The replica adopts the owner's wallet from prod_done.
                finished = run_clock(host, client, lambda: client_production(host) is None, 60)
                stop_clock(host, client)
                assert finished, f"production never finished: {client_production(host)}"
                client.wait_for("client replica adopts the charged wallet",
                                lambda: wallets(client) == wallets(host) or None,
                                timeout=20, interval=0.5)
            row("PROD hourly production at the client's base uses the client's wallet", prod)

            # EVENT --------------------------------------------------------
            def event():
                before_host = wallets(host)
                spawned = host.ok({"cmd": "spawn_event", "name": EVENT,
                                   "owner": "ClientPlayer"})
                assert spawned["spawned"], spawned
                fired = run_clock(host, client,
                                  lambda: has_state(client, "GeoscapeEventState")
                                  or wallets(host) != before_host,
                                  90, keep=("GeoscapeEventState",))
                assert fired, "the event never fired"
                client.wait_for("client shows its event",
                                lambda: has_state(client, "GeoscapeEventState") or None,
                                timeout=30, interval=0.3)
                stop_clock(host, client)
                assert not has_state(host, "GeoscapeEventState"), \
                    "the host was shown the client's event"
                after_host = wallets(host)
                assert after_host["ClientPlayer"] == before_host["ClientPlayer"] + EVENT_FUNDS, (
                    "the client's event did not credit the client's wallet",
                    before_host, after_host)
                assert after_host["HostPlayer"] == before_host["HostPlayer"], (
                    "the client's event credited the host's wallet", before_host, after_host)
                after_client = wallets(client)
                assert after_client == after_host, (
                    "the client replica changed its wallets on its own (event logic ran "
                    "on the replica) or missed the host's result",
                    after_host, after_client)
                geo.drain_popups(client)
            row("EVENT a client-owned event pays the client; the replica only displays it", event)

            # BONUS --------------------------------------------------------
            def bonus():
                for player in ("HostPlayer", "ClientPlayer"):
                    set_wallet(host, client, player, 1000000)
                before_h = host.ok({"cmd": "month_report"})
                before_c = client.ok({"cmd": "month_report"})
                income = before_h["countryFunding"]
                net = {"HostPlayer": income - before_h["monthlyMaintenanceActual"],
                       "ClientPlayer": income - before_c["monthlyMaintenanceActual"]}
                roll_month(host, client)
                after_h = wallets(host)
                client.wait_for("client adopts the month's wallets",
                                lambda: wallets(client) == wallets(host) or None,
                                timeout=30, interval=0.5)
                after_c = wallets(client)
                extra = {p: after_h[p] - 1000000 - int(net[p] / 2) for p in net}
                assert extra["HostPlayer"] > 0, ("no performance bonus was paid", extra)
                assert extra["HostPlayer"] == extra["ClientPlayer"], (
                    "the bonus was not split equally between the players", extra)
                assert after_c == after_h, ("replica wallets differ", after_h, after_c)
                report_states(host, client)
            row("BONUS the performance bonus is split equally (RU7)", bonus)

            # DEBT ---------------------------------------------------------
            def debt():
                # One player deeply negative, the combined total positive.
                set_wallet(host, client, "HostPlayer", 20000000)
                set_wallet(host, client, "ClientPlayer", -8000000)
                roll_month(host, client)
                warned = {gc.name: gc.ok({"cmd": "month_report"})["warned"]
                          for gc in (host, client)}
                endings = report_states(host, client)
                assert warned == {"host": False, "client": False}, (
                    "a positive combined total must not raise the debt warning", warned)
                assert endings == {"host": 0, "client": 0}, endings

                # Combined total negative: the same warning on both machines.
                set_wallet(host, client, "HostPlayer", -30000000)
                set_wallet(host, client, "ClientPlayer", 4000000)
                roll_month(host, client)
                warned = {gc.name: gc.ok({"cmd": "month_report"})["warned"]
                          for gc in (host, client)}
                endings = report_states(host, client)
                assert warned == {"host": True, "client": True}, (
                    "a negative combined total must warn both players", warned)
                assert endings == {"host": 0, "client": 0}, endings

                # Still negative at the next month end: defeat for both.
                set_wallet(host, client, "HostPlayer", -30000000)
                set_wallet(host, client, "ClientPlayer", 4000000)
                roll_month(host, client)
                endings = {}
                deadline = time.time() + 60
                while time.time() < deadline:
                    endings = report_states(host, client)
                    if all(endings.values()):
                        break
                assert endings == {"host": 2, "client": 2}, (
                    "the second negative month must end the campaign on both", endings)
            row("DEBT combined funds judged once on the host (RU2)", debt)
        finally:
            js.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if FAILURES:
        print(f"FAILED rows: {FAILURES}")
        sys.exit(1)
    print("PASS Separate economy: host-simulated money reaches the owner's wallet")


if __name__ == "__main__":
    main()
