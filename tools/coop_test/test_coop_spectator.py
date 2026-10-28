"""R5-U2 S-C rows WG, SP1 (boot S1) and SP2 (boot S2), classic co-op: a co-op player who loses its last soldier mid-battle
is told "You command no soldiers - spectator mode" at once, the host as well as the second
player; and the second player's new-contact count is unchanged (WR-30 guard).

Spec: docs repo rewrite/prompts/r5u2_pvp_presentation.md section (f) test_coop_spectator.py, with AMENDMENT U2-1 (U2-1.5,
U2-1.8: the seats are MCC.boot_c's RV-U8 pins) and the orchestrator rulings (QU2-1 .. QU2-17 (a), QU2-A1-1 .. QU2-A1-5 (a)).
Constants: rewrite/r5u2-task0/sc/CONSTANTS.md (TASK 0 boots Sa, Sb on the C1 probe build).

Boot S1 (key 48886, dirs r5u2_s1_host / _client): MCC.boot_c (BER.boot_classic: STR_SMALL_SCOUT, map seed 1, the one alien
pinned AI-neutral; seats S0_IDS [10..14] host / S1_IDS [8, 9] client on both, turnMode parallel).
  WG  the co-op client's new-contact count is unchanged (guard)
      WG-count    the client's event_state.visibleHostileCount == the distinct FACTION_HOSTILE ids in the union of
                  units[i].visibleUnits, i in S1_IDS, on the client
  SP1 the second player loses its last soldier (last row of S1): host battle_action kill_unit_real {coop_side 1}
      SP1-out     8 and 9 DEAD on both (precondition; the wait ends at the observed deaths, capped at KILL_S)
      SP1-client  the client's coopWaitText == TEXT_SPECTATOR within NOTICE_S
      SP1-host    the host's coopWaitText != TEXT_SPECTATOR in every sample of that window (guard)
Boot S2 (key 48888, dirs r5u2_s2_host / _client): MCC.boot_c.
  SP2 the host loses its last soldier: host kill_unit_real {coop_side 0}
      SP2-out     10..14 DEAD on both; the battle continues: both tops BattlescapeState, (turn, side) unchanged
                  (precondition; the client still commands 8, 9: W2-H31)
      SP2-host    the host's coopWaitText == TEXT_SPECTATOR within NOTICE_S
      SP2-client  the client's coopWaitText != TEXT_SPECTATOR in every sample of that window (guard)
The window starts once the deaths are observed; both machines are sampled every SAMPLE_S through it, an infobox on either
machine closed on its own machine (MCC idiom). Common cell after each row (<row>-common): every hash bucket EQUAL,
desyncSeen false on both, no new file in the lane crash folder.

RED on the unchanged product (commit C1): SP1-client, SP2-host; every other cell PASS. One EVIDENCE line per row, one
PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step past its bound prints ONE
CAPTURE line and fails that boot's rows "boot". run in the foreground to completion. ONE run is
the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_coop_spectator.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_mc_seat_coop as MCC  # noqa: E402
from test_mc_seat_tally import poll_box  # noqa: E402

KEY_S1, KEY_S2 = "48886", "48888"
S0_IDS, S1_IDS = MCC.S0_IDS, MCC.S1_IDS   # [10..14] the host's seat, [8, 9] the client's (RV-U8 pins)
TEXT_SPECTATOR = "You command no soldiers - spectator mode"   # STR_COOP_SPECTATOR_MODE, en-US
FACTION_HOSTILE, DEAD = 1, 6
KILL_S = 30                       # the deaths' bound (TASK 0: 1.72 s for 8, 9; 4.74 s for 10..14)
NOTICE_S, SAMPLE_S = 10, 0.1      # the notice window after the deaths, and its sample cadence
S1_ROWS = (("WG", ("WG-count", "WG-common")), ("SP1", ("SP1-out", "SP1-client", "SP1-host", "SP1-common")))
S2_ROWS = (("SP2", ("SP2-out", "SP2-host", "SP2-client", "SP2-common")),)


def vhc(gc):
    return event_state(gc).get("visibleHostileCount")


def bsv(gc):
    b = battle_state(gc)
    return {k: b.get(k) for k in ("side", "turn", "selectedId", "coopWaitText")}


def turn_side(gc):
    b = battle_state(gc)
    return (b.get("turn"), b.get("side"))


def hostile_union(gc, ids):
    us = G3F.units(gc)
    seen = set()
    for i in ids:
        for v in (us.get(i) or {}).get("visibleUnits") or []:
            if (us.get(v) or {}).get("faction") == FACTION_HOSTILE:
                seen.add(v)
    return sorted(seen)


def statuses(gc, ids):
    us = G3F.units(gc)
    return [(us.get(i) or {}).get("status") for i in ids]


def watch(host, client, rec):
    """Both machines' coopWaitText every SAMPLE_S for NOTICE_S; once a second an infobox on either machine is closed
    on its own machine (MCC idiom)."""
    samples, t0, boxed = [], time.time(), -1
    while time.time() - t0 < NOTICE_S:
        if int(time.time() - t0) != boxed:   # once a second: an infobox closed on its own machine
            boxed = int(time.time() - t0)
            poll_box(host, rec, "watch")
            poll_box(client, rec, "watch")
        samples.append((round(time.time() - t0, 2), battle_state(host).get("coopWaitText"),
                        battle_state(client).get("coopWaitText")))
        time.sleep(max(0.0, SAMPLE_S * len(samples) - (time.time() - t0)))
    return samples


def first_at(samples, idx, text):
    hits = [s[0] for s in samples if s[idx] == text]
    return hits[0] if hits else None


# ===================== rows =====================


def row_wg(host, client, crash0):
    count, union = vhc(client), hostile_union(client, S1_IDS)
    ev = {"count": count, "union": union, "hostCount": vhc(host), "client": bsv(client),
          "lists": {i: (G3F.units(client).get(i) or {}).get("visibleUnits") for i in S1_IDS}}
    return {"WG-count": (count == len(union), f"the client's visibleHostileCount {count} (want {len(union)}: the "
                                              f"FACTION_HOSTILE ids its soldiers see, {union})"),
            "WG-common": G3F.common(host, client, crash0)}, ev


def row_sp(row, host, client, crash0, seat, dead_ids, told, other):
    """`row` (SP1 / SP2): host kill_unit_real {coop_side seat}; `told` must show TEXT_SPECTATOR within the window,
    `other` never."""
    ev, rec, m = {"before": {"host": bsv(host), "client": bsv(client)}}, {"boxes": []}, (host, client)
    ts0 = [turn_side(gc) for gc in m]
    k = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "coop_side": seat})
    ok, secs = BER.wait_until(lambda: (poll_box(host, rec, "kill") or True) and (poll_box(client, rec, "kill") or True)
                              and all(statuses(gc, dead_ids) == [DEAD] * len(dead_ids) for gc in m), KILL_S, 0.1)
    samples = watch(host, client, rec)
    tops, ts = [G3F.top(gc) for gc in m], [turn_side(gc) for gc in m]
    idx = {"host": 1, "client": 2}
    t_told = first_at(samples, idx[told.name], TEXT_SPECTATOR)
    t_other = first_at(samples, idx[other.name], TEXT_SPECTATOR)
    texts = {gc.name: sorted({s[idx[gc.name]] for s in samples}, key=str) for gc in m}
    ev.update(kill=k, deathsS=secs, statuses={gc.name: statuses(gc, dead_ids) for gc in m}, texts=texts, n=len(samples),
              tops=tops, turnSide=[ts0, ts], boxes=rec["boxes"], after={"host": bsv(host), "client": bsv(client)})
    out_ok = ok and sorted(k.get("killed") or []) == sorted(dead_ids)
    detail = (f"killed {k.get('killed')} (want {dead_ids}); DEAD on both within {KILL_S} s: {ok} ({secs} s) "
              f"{ev['statuses']}")
    if seat == 0:
        out_ok = out_ok and tops == ["BattlescapeState"] * 2 and ts == ts0
        detail += f"; tops {tops} (want BattlescapeState on both); (turn, side) {ts0} -> {ts} (want unchanged)"
    cells = {f"{row}-out": (out_ok, detail),
             f"{row}-{told.name}": (t_told is not None,
                                    f"the {told.name}'s coopWaitText over {NOTICE_S} s {texts[told.name]} (want "
                                    f"{TEXT_SPECTATOR!r} within {NOTICE_S} s; first at {t_told})"),
             f"{row}-{other.name}": (t_other is None,
                                     f"the {other.name}'s coopWaitText over {NOTICE_S} s {texts[other.name]} (want never "
                                     f"{TEXT_SPECTATOR!r}; first at {t_other})"),
             f"{row}-common": G3F.common(host, client, crash0)}
    return cells, ev


# ===================== boots =====================


def run_boot(tag, key, rows, row_fns):
    host = GameClient("host", None, make_user_dir(f"r5u2_{tag}_host"))
    client = GameClient("client", None, make_user_dir(f"r5u2_{tag}_client"))
    m = (host, client)
    try:
        try:
            info = G3F.guarded(tag.upper(), lambda: MCC.boot_c(host, client, key), m)
            crash0 = session._crash_log_snapshot()
        except G3F.Miss:
            return G3F.fail_all(rows, f"boot (FIXTURE-STOP, see the CAPTURE {tag.upper()} line)")
        print(f"EVIDENCE boot {tag.upper()}: {info}; host {bsv(host)}; client {bsv(client)}", flush=True)
        fails = 0
        for (row, order), fn in zip(rows, row_fns):
            fails += G3F.run_row(row, order, lambda f=fn: f(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot("s1", KEY_S1, S1_ROWS,
                     (row_wg, lambda h, c, k: row_sp("SP1", h, c, k, 1, S1_IDS, c, h)))
    fails += run_boot("s2", KEY_S2, S2_ROWS,
                      (lambda h, c, k: row_sp("SP2", h, c, k, 0, S0_IDS, h, c),))
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_coop_spectator: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
