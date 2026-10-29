"""Separate campaign: the host carries what its day step does to soldiers.

The Separate campaign is one host-owned world. Only the host runs the day step
(wound recovery, martial training, psi training) and the month step (monthly
psi training). The client's replica must hold the same soldier state right
after the step, from the host's result, without a world restream. The world
checksum's soldier-stats term stays as the safety net; these rows require that
it never has to repair a step (0 resync requests, 0 streams).

Rows (a test mod gives every access lift a gym, a psi lab and a sick bay with a
relative bonus, so one day of healing leaves a fraction):
  T1 wounds   with nobody in training, one soldier per player is wounded and
              another misses health and mana. After one midnight both machines
              hold the same exact wound recovery and missing health and mana.
  T2 martial  each player's own soldiers at their own base are in martial
              training. After one midnight their stats rose on the host and
              every soldier's state is the same on both machines.
  T3 psi      each player's own soldiers at their own base are in psi training
              (monthly psi training, the default). After the month turns their
              psi skill and improvement are the same on both machines.

  * PASS (exit 0): every row holds.
  * FAIL (any other rc): a row failed or a game process crashed.
"""
import calendar
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import separate_campaign_fixture as sep  # noqa: E402

COOP_DLG_CLIENT_RESUME_HOLD = 68
DEBOUNCE_S = 3.0  # SharedEcon RESYNC_DEBOUNCE_MS: a mismatch must survive this
STREAM_LINE = "[coop-shared] streaming authoritative world to client"
TRAINING_STATS = ("tu", "stamina", "health", "firing", "throwing", "melee", "strength")

MOD_NAME = "coop_training_carry"
METADATA = """\
name: "Coop training carry test"
version: 1.0
description: "Test-only: a gym, a psi lab and a sick bay in every access lift."
author: coop harness

master: xcom1
"""
RULESET = """\
facilities:
  - type: STR_ACCESS_LIFT
    trainingRooms: 10
    psiLabs: 10
    sickBayRelativeBonus: 1.5
    healthRecoveryPerDay: 3
    manaRecoveryPerDay: 2
"""

failures = []


def check(row, ok, detail):
    print(("PASS " if ok else "[FAIL] ") + row + ("" if ok else f": {detail}"))
    if not ok:
        failures.append(row)


def make_mod(root):
    mod = os.path.join(root, MOD_NAME)
    os.makedirs(os.path.join(mod, "Ruleset"))
    with open(os.path.join(mod, "metadata.yml"), "w", encoding="utf-8") as f:
        f.write(METADATA)
    with open(os.path.join(mod, "Ruleset", "carry.rul"), "w", encoding="utf-8") as f:
        f.write(RULESET)
    return mod


class EngineLog:
    """What an engine log gained since this object was made."""

    def __init__(self, user_dir):
        self.path = os.path.join(user_dir, "openxcom.log")
        self.offset = os.path.getsize(self.path) if os.path.exists(self.path) else 0

    def count(self, text):
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(self.offset)
            return f.read().count(text)


def carry(gc):
    """Every base soldier's day-step state on this machine, keyed by
    (base, owner, id)."""
    return {(s["base"], s["owner"], s["id"]): s
            for s in gc.ok({"cmd": "soldier_carry"})["soldiers"]}


def differences(host, client):
    h, c = carry(host), carry(client)
    out = []
    for key in sorted(set(h) | set(c)):
        hs, cs = h.get(key), c.get(key)
        if hs is None or cs is None:
            out.append((key, "missing", hs is not None, cs is not None))
            continue
        for field in sorted(hs):
            if hs[field] != cs.get(field):
                if isinstance(hs[field], dict):
                    sub = {k: (hs[field][k], cs[field].get(k)) for k in hs[field]
                           if hs[field][k] != cs[field].get(k)}
                    out.append((key, field, sub))
                else:
                    out.append((key, field, hs[field], cs.get(field)))
    return out


def own(gc, base, owner):
    return [s["id"] for s in sep.soldiers_at(gc, base) if s["owner"] == owner]


def resync(gc):
    return gc.ok({"cmd": "shared_resync_stats"})


def reset_resync(host, client):
    for gc in (host, client):
        gc.ok({"cmd": "shared_reset_resync_stats"})


def released(gc):
    return gc.ok({"cmd": "get_coop"})["coopDialog"] != COOP_DLG_CLIENT_RESUME_HOLD


def make_equal(host, client, label):
    """Start a row from one world. A previous row that left the machines
    different (a red build) is healed by a restream: a replica-only stat drift
    makes the checksum ask for one."""
    if not differences(host, client):
        return
    print(f"  {label}: the machines differ before the step ({differences(host, client)[:3]}); "
          f"a replica drift asks for a restream")
    target = sep.soldiers_at(host, "ClientBase")[0]
    client.ok({"cmd": "set_soldier_stat", "base": "ClientBase", "id": target["id"],
               "stat": "firing", "value": target["firing"] + 7})
    client.wait_for(label + ": the restream made both machines equal",
                    lambda: not differences(host, client) or None, timeout=90, interval=0.5)
    client.wait_for(label + ": client released from the resume hold",
                    lambda: released(client) or None, timeout=60, interval=0.5)
    time.sleep(2 * DEBOUNCE_S)


def screen_all(gc, screen, base, action):
    gc.ok({"cmd": "open_screen", "screen": screen, "base": base})
    gc.ok({"cmd": "roster_screen", "action": action})
    gc.ok({"cmd": "close_screens"})


def flags_settled(host, client, key, want):
    """Every player's own soldiers at their own base show <key> == want on both."""
    for base, owner in (("HostBase", 0), ("ClientBase", 1)):
        ids = own(host, base, owner)
        for gc in (host, client):
            by_id = {s["id"]: s for s in sep.soldiers_at(gc, base)}
            if not all(by_id.get(i, {}).get(key) == want for i in ids):
                return False
    return True


def run_step(host, client, day, hour=23):
    """Jump the host clock to <day> <hour>:00 and run it past midnight. Returns
    once both machines show the new day."""
    t0 = sep.geo(host)["time"]
    host.ok({"cmd": "set_geo_day", "day": day, "hour": hour})
    geo.skip_ingame_time(host, client, minutes=90, speed_idx=2, real_timeout=60)
    geo.slow_clock(host, client)
    for gc in (host, client):
        gc.wait_for("the clock passed midnight",
                    lambda gc=gc: (sep.geo(gc)["time"]["day"] != day) or None,
                    timeout=30, interval=0.25)
    print(f"  step from {t0['year']}-{t0['month']}-{day} {hour}:00 -> "
          f"{sep.geo(host)['time']}")


def settle_and_count(host, client, hlog, label):
    """After a step: wait for the two machines to agree (10 s at most), then
    well past the resync debounce, and return (diffs, client requests, host
    requests, host streams)."""
    deadline = time.time() + 10
    diffs = differences(host, client)
    while diffs and time.time() < deadline:
        time.sleep(0.25)
        diffs = differences(host, client)
    time.sleep(2 * DEBOUNCE_S)
    for gc in (host, client):
        geo.drain_popups(gc)
    diffs = differences(host, client)
    rc, rh, streams = resync(client)["requests"], resync(host)["requests"], hlog.count(STREAM_LINE)
    print(f"  {label}: diffs={diffs[:6]}{' ...' if len(diffs) > 6 else ''} "
          f"client requests={rc} host requests={rh} streams={streams}")
    return diffs, rc, rh, streams


def row_wounds(host, client, host_dir):
    """T1: wound recovery and missing health and mana after one midnight."""
    picks = []
    for base, owner in (("HostBase", 0), ("ClientBase", 1)):
        ids = own(host, base, owner)
        assert len(ids) >= 2, ("T1 premise: two own soldiers", base, ids)
        picks.append((base, owner, ids[0], {"recovery": 5}))
        picks.append((base, owner, ids[1], {"healthMissing": 10, "manaMissing": 10}))
    for base, owner, sid, wounds in picks:
        for gc in (host, client):
            gc.ok(dict({"cmd": "soldier_carry", "action": "set_wounds", "base": base,
                        "id": sid, "owner": owner}, **wounds))
    assert not differences(host, client), ("T1 fixture differs", differences(host, client))
    reset_resync(host, client)
    log = EngineLog(host_dir)
    run_step(host, client, sep.geo(host)["time"]["day"])
    h = carry(host)
    healed = [h[(b, o, s)] for b, o, s, _ in picks]
    premise = (healed[0]["recovery"] < 5 and healed[2]["recovery"] < 5
               and healed[1]["healthMissing"] < 10 and healed[1]["manaMissing"] < 10)
    print(f"  T1 host after the step: "
          f"{[(s['id'], s['recovery'], s['healthMissing'], s['manaMissing']) for s in healed]}")
    diffs, rc, rh, streams = settle_and_count(host, client, log, "T1")
    check("T1 wounds: the host healed its soldiers (premise)", premise,
          f"{[(s['id'], s['recovery'], s['healthMissing'], s['manaMissing']) for s in healed]}")
    check("T1 wounds: exact wound recovery and missing health and mana match on both "
          "machines right after the day step, with no restream",
          premise and not diffs and rc == 0 and rh == 0 and streams == 0,
          f"diffs={diffs} requests client={rc} host={rh} streams={streams}")
    # Healed again on both machines, so T2 can train every own soldier.
    for base, owner, sid, _ in picks:
        for gc in (host, client):
            gc.ok({"cmd": "soldier_carry", "action": "set_wounds", "base": base,
                   "id": sid, "owner": owner})


def trained_sum(gc, base, ids):
    by_id = {s["id"]: s for s in sep.soldiers_at(gc, base)}
    return sum(by_id[i].get(k, 0) for i in ids for k in TRAINING_STATS)


def row_martial(host, client, host_dir):
    """T2: martial training after one midnight."""
    make_equal(host, client, "T2")
    screen_all(client, "training", "ClientBase", "assign_all")
    screen_all(host, "training", "HostBase", "assign_all")
    on = False
    deadline = time.time() + 15
    while time.time() < deadline and not on:
        on = flags_settled(host, client, "training", True)
        time.sleep(0.25)
    assert on, "T2 premise: every own soldier in martial training on both machines"
    trainees = {"HostBase": own(host, "HostBase", 0), "ClientBase": own(host, "ClientBase", 1)}
    before = {b: trained_sum(host, b, ids) for b, ids in trainees.items()}
    client.wait_for("T2 both machines agree before the step",
                    lambda: not differences(host, client) or None, timeout=30, interval=0.5)
    reset_resync(host, client)
    log = EngineLog(host_dir)
    run_step(host, client, sep.geo(host)["time"]["day"])
    after = {b: trained_sum(host, b, ids) for b, ids in trainees.items()}
    print(f"  T2 trained stats on the host {before} -> {after}")
    diffs, rc, rh, streams = settle_and_count(host, client, log, "T2")
    premise = all(after[b] > before[b] for b in before)
    check("T2 martial: the host trained both players' soldiers (premise)", premise,
          f"before={before} after={after}")
    check("T2 martial: every soldier's stats match on both machines right after the "
          "day step, with no restream",
          premise and not diffs and rc == 0 and rh == 0 and streams == 0,
          f"diffs={diffs} requests client={rc} host={rh} streams={streams}")
    screen_all(client, "training", "ClientBase", "deassign_all")
    screen_all(host, "training", "HostBase", "deassign_all")
    deadline = time.time() + 15
    while time.time() < deadline and not flags_settled(host, client, "training", False):
        time.sleep(0.25)


def psi(gc, base, ids):
    by_key = carry(gc)
    return {i: (by_key[k]["stats"]["psiSkill"], by_key[k]["improvement"])
            for k in by_key for i in ids if k[0] == base and k[2] == i}


def row_psi_month(host, client, host_dir):
    """T3: monthly psi training when the month turns."""
    make_equal(host, client, "T3")
    screen_all(client, "psi_training", "ClientBase", "assign_all")
    screen_all(host, "psi_training", "HostBase", "assign_all")
    deadline = time.time() + 15
    on = False
    while time.time() < deadline and not on:
        on = flags_settled(host, client, "psiTraining", True)
        time.sleep(0.25)
    assert on, "T3 premise: every own soldier in psi training on both machines"
    trainees = {"HostBase": own(host, "HostBase", 0), "ClientBase": own(host, "ClientBase", 1)}
    before = {b: psi(host, b, ids) for b, ids in trainees.items()}
    client.wait_for("T3 both machines agree before the step",
                    lambda: not differences(host, client) or None, timeout=30, interval=0.5)
    reset_resync(host, client)
    log = EngineLog(host_dir)
    t = sep.geo(host)["time"]
    run_step(host, client, calendar.monthrange(t["year"], t["month"])[1])
    after = {b: psi(host, b, ids) for b, ids in trainees.items()}
    print(f"  T3 psi (skill, improvement) on the host {before} -> {after}")
    diffs, rc, rh, streams = settle_and_count(host, client, log, "T3")
    premise = all(after[b][i][0] != before[b][i][0] for b in before for i in before[b])
    check("T3 psi: the host's month step trained both players' soldiers (premise)", premise,
          f"before={before} after={after}")
    check("T3 psi: psi skill and improvement match on both machines right after the "
          "month step, with no restream",
          premise and not diffs and rc == 0 and rh == 0 and streams == 0,
          f"diffs={diffs} requests client={rc} host={rh} streams={streams}")


def main():
    tmp = tempfile.mkdtemp(prefix="coop_training_carry_")
    try:
        mod = make_mod(tmp)
        js = sep.bring_up("sep_training_carry", (49780, 49781, 49080), mods=[mod])
        host, client = js.host, js.client
        try:
            sep.assert_fresh_named_world(host, client)
            geo.slow_clock(host, client)
            for gc in (host, client):
                gc.ok({"cmd": "geo_set_speed", "idx": 0})
            print("  rosters: " + str({b: [(s["owner"], s["id"]) for s in sep.soldiers_at(host, b)]
                                       for b in ("HostBase", "ClientBase")}))
            for name, row in (("T1", row_wounds), ("T2", row_martial), ("T3", row_psi_month)):
                try:
                    row(host, client, js.host_dir)
                except (AssertionError, TimeoutError) as e:
                    failures.append(name)
                    print(f"[FAIL] {name}: {e}")
        finally:
            alive = all(gc.proc.poll() is None for gc in (host, client))
            js.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not alive:
        print("FAIL: a game process died")
        sys.exit(2)
    if failures:
        print(f"FAIL {len(failures)} row(s): {failures}")
        sys.exit(3)
    print("PASS the host carries its day and month step soldier changes to the replica")


if __name__ == "__main__":
    main()
