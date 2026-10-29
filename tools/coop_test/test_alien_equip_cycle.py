"""PvP alien unit cycle on the pre-battle screen (boot alien_cycle, gm2 STR_MEDIUM_SCOUT: the client plays the five
sectoids, seat 1; the host the seven X-COM soldiers, seat 0; default options, so "Enable XCOM Equipment for Aliens in
PVP" is on and the alien seat gets its pre-battle screen, as in test_alien_equip): the PvP alien seat's PREV / NEXT on
the pre-battle screen cycle its OWN aliens, the X-COM host's cycle stays vanilla's, and turn 1 follows both OKs.

Rules: ALIEN_IDS = the client seat's units with an inventory (faction HOSTILE, coop seat 1, not out, an armor with
allowInv) in battle_state.units order, read at the screens' open (fewer than two fails the boot); the host's soldier
order is the measured record HOST_ORDER; NEXT / PREV = inventory_click {widget next | prev}.

Boot alien_cycle (key 49067): set_seed 1, the client joins and takes the Alien team (gamemode 2),
repro_pvp_side_relative's gm2 drive without its last line (mission STR_MEDIUM_SCOUT), the host's briefing OK -> its
screen on H1, the unit it opens on; dismiss_client_briefing -> the client's screen on ALIEN_IDS[0] (the alien seat's
equip entry); both screens up.
  alien_next_cycles  NEXT cycles the alien seat's own aliens: len(ALIEN_IDS) client NEXT presses: next_visits_own_aliens
  alien_prev_wraps   PREV: one client PREV press: prev_goes_to_last_alien
  host_next_vanilla  the X-COM host's cycle is vanilla's: len(HOST_ORDER) host NEXT presses: next_visits_host_soldiers
  turn_one           turn 1: both OK -> the barrier: turn_one_starts
Each row ends with a common cell (<row>_common): every hash bucket EQUAL, desyncSeen false on both, no new crash
file.

On a build where the alien seat's PREV / NEXT do not cycle its own aliens, next_visits_own_aliens and
prev_goes_to_last_alien fail; every other cell passes. One EVIDENCE line per row, one PASS/FAIL line per cell, then the
row verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails every row
"boot"; a staging step past its bound fails that row "staging". Run it in the foreground to completion: one run is the
result, with no skip path; exit 0 only when every cell passes, else 2. test_alien_equip_off.py imports this file's
helpers.

Run:  python tools/coop_test/test_alien_equip_cycle.py
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_prebattle_equip as PEQ  # noqa: E402
import test_alien_equip as AE  # noqa: E402

KEY = "49067"
SEED = 1                          # set_seed on the host before its lobby and right before newbattle_ok
MISSION = "STR_MEDIUM_SCOUT"
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
HOST_SEAT, CLIENT_SEAT = 0, 1
ALIEN_IDS_MEASURED = [1000000, 1000001, 1000002, 1000003, 1000004]   # measured (EVIDENCE only: the cells read the rule)
HOST_ORDER = [9, 10, 11, 12, 13, 14, 8]   # measured: the host's NEXT x 7 from H1 = 8 (the cell compares with it)
SCREEN_S = 15                     # each pre-battle screen's bound (measured: <= 0.1 s)
ROWS = (("alien_next_cycles", ("next_visits_own_aliens", "alien_next_cycles_common")),
        ("alien_prev_wraps", ("prev_goes_to_last_alien", "alien_prev_wraps_common")),
        ("host_next_vanilla", ("next_visits_host_soldiers", "host_next_vanilla_common")),
        ("turn_one", ("turn_one_starts", "turn_one_common")))


# ===================== shared helpers (test_alien_equip_off imports them) =====================


def armors():
    """{armor type: allowInv} from the ruleset the game reads (Armor::hasInventory() = allowInv, default true)."""
    p = os.path.join(os.path.dirname(os.path.abspath(harness.EXE)), "standard", "xcom1", "armors.rul")
    d, cur = {}, None
    with open(p, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^  - type: (\S+)", line)
            if m:
                cur = m.group(1)
                d[cur] = True
                continue
            m = re.match(r"^    allowInv: (\w+)", line)
            if m and cur:
                d[cur] = m.group(1) == "true"
    return d


ARM = armors()


def own_ids(gc, faction, seat):
    """`seat`'s units with an inventory (isSelectable(faction, false, true): the faction, not out, an armor with
    allowInv) in battle_state.units order."""
    return [u["id"] for u in battle_state(gc).get("units", []) if u.get("faction") == faction and u.get("coop") == seat
            and not u.get("isOut") and ARM.get(u.get("armor"), True)]


def drive(host, client, mission):
    """repro_pvp_side_relative.drive_to_gm2_battlescape WITHOUT its last line (test_alien_equip's drive with the mission
    a parameter)."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings", lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert G3F.top(host) == "NewBattleState", f"host stack {G3F.stack(host)} (want NewBattleState on top)"
    r = host.cmd({"cmd": "newbattle_mission", "type": mission})
    assert r.get("ok"), f"newbattle_mission {mission}: {r}"
    host.ok({"cmd": "set_seed", "seed": SEED})
    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=60)
    client.wait_for("client briefing", lambda: session.has_state(client, "BriefingState") or None, timeout=90)


def lobby_drive(host, client, key, mission, tag):
    """Spawn, set_seed, test_alien_equip's lobby (the client on Alien, gamemode 2), the drive; a step past its bound
    is a Miss."""
    m = (host, client)
    G3F.guarded(tag, lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    G3F.guarded(tag, lambda: host.ok({"cmd": "set_seed", "seed": SEED}), m)
    gm = G3F.guarded(tag, lambda: AE.lobby_client_aliens(host, client, key), m)
    G3F.guarded(tag, lambda: drive(host, client, mission), m)
    return gm


def host_screen(host, client, tag):
    """The host's briefing OK -> its pre-battle screen (bounded); returns (H1, seconds)."""
    G3F.guarded(tag, lambda: host.ok({"cmd": "click_widget", "match": "ok"}), (host, client))
    up, s = AE.wait_until(lambda: PEQ.screen_up(host), SCREEN_S)
    if not up:
        G3F.capture(tag, "the host's pre-battle screen never came up", (host, client))
        raise G3F.Miss(tag)
    return AE.iv(host).get("unitId"), s


def press(gc, widget, rec):
    """ONE real click on the pre-battle screen's PREV / NEXT (inventory_click widget; PEQ next_press's bounded wait for a
    unit change). Returns the unitId after it."""
    before = AE.iv(gc).get("unitId")
    c = PEQ.click(gc, widget=widget)
    _, dt = PEQ.wait_until(lambda: AE.iv(gc).get("unitId") != before, PEQ.CLICK_WAIT_S)
    after = AE.iv(gc).get("unitId")
    rec.append({"from": before, "to": after, "click": c.get("error") or c.get("ok"), "waitedS": dt})
    return after


def stacks(host, client):
    return [G3F.stack(host), G3F.stack(client)]


# ===================== boot alien_cycle =====================


def setup_alien_cycle(host, client):
    m = (host, client)
    ctx = {"gm": lobby_drive(host, client, KEY, MISSION, "alien_cycle")}
    ctx["H1"], ctx["hostScreenS"] = host_screen(host, client, "alien_cycle")
    G3F.guarded("alien_cycle", lambda: session.dismiss_client_briefing(client), m)
    up, ctx["clientScreenS"] = AE.wait_until(lambda: PEQ.screen_up(client), SCREEN_S)
    if not up:
        G3F.capture("alien_cycle", f"the client's pre-battle screen never came up (stacks {stacks(host, client)})", m)
        raise G3F.Miss("alien_cycle")
    ids = {gc.name: own_ids(gc, FACTION_HOSTILE, CLIENT_SEAT) for gc in m}
    if len(ids["host"]) < 2 or ids["host"] != ids["client"]:
        G3F.capture("alien_cycle", f"ALIEN_IDS host {ids['host']} client {ids['client']} (want >= 2, equal on both)", m)
        raise G3F.Miss("alien_cycle")
    ctx.update(ALIEN_IDS=ids["host"], soldiers=own_ids(host, FACTION_PLAYER, HOST_SEAT),
               counted=((AE.es(host, "equip") or {}).get("counted") or [])[:2],
               views=[PEQ.view_brief(AE.iv(host)), PEQ.view_brief(AE.iv(client))])
    return ctx


def row_alien_next_cycles(host, client, ctx, crash0):
    A = ctx["ALIEN_IDS"]
    ev = {k: ctx[k] for k in ("gm", "H1", "hostScreenS", "clientScreenS", "ALIEN_IDS", "soldiers", "counted", "views")}
    ev.update(ALIEN_IDS_MEASURED=ALIEN_IDS_MEASURED, start=AE.iv(client).get("unitId"))
    if not AE.screen_on(client, A[0]):
        raise AssertionError(f"staging: the client's pre-battle screen is not on ALIEN_IDS[0] {A[0]} "
                             f"({PEQ.view_brief(AE.iv(client))})")
    rec = []
    for _ in A:
        press(client, "next", rec)
    got, want = [r["to"] for r in rec], A[1:] + A[:1]
    ev["presses"] = rec
    return {"next_visits_own_aliens": (got == want, f"client unitIds after each NEXT {got} (want ALIEN_IDS[1:] + [ALIEN_IDS[0]] {want})"),
            "alien_next_cycles_common": G3F.common(host, client, crash0)}, ev


def row_alien_prev_wraps(host, client, ctx, crash0):
    A = ctx["ALIEN_IDS"]
    ev = {"start": AE.iv(client).get("unitId")}
    if not PEQ.screen_up(client):
        raise AssertionError(f"staging: no pre-battle screen on the client ({PEQ.view_brief(AE.iv(client))})")
    rec = []
    got = press(client, "prev", rec)
    ev["presses"] = rec
    return {"prev_goes_to_last_alien": (got == A[-1], f"client unitId after one PREV {got} from {ev['start']} (want ALIEN_IDS[-1] "
                                       f"{A[-1]}, from ALIEN_IDS[0] {A[0]})"),
            "alien_prev_wraps_common": G3F.common(host, client, crash0)}, ev


def row_host_next_vanilla(host, client, ctx, crash0):
    S, H1 = ctx["soldiers"], ctx["H1"]
    i = S.index(H1) if H1 in S else -1
    ev = {"H1": H1, "soldiers": S, "rule": S[i + 1:] + S[:i + 1] if i >= 0 else None, "HOST_ORDER": HOST_ORDER}
    if not AE.screen_on(host, H1):
        raise AssertionError(f"staging: the host's pre-battle screen is not on H1 {H1} ({PEQ.view_brief(AE.iv(host))})")
    rec = []
    for _ in HOST_ORDER:
        press(host, "next", rec)
    got = [r["to"] for r in rec]
    ev["presses"] = rec
    return {"next_visits_host_soldiers": (got == HOST_ORDER, f"host unitIds after each NEXT {got} (want the measured soldier order {HOST_ORDER})"),
            "host_next_vanilla_common": G3F.common(host, client, crash0)}, ev


def row_turn_one(host, client, ctx, crash0):
    ev = {"views": [PEQ.view_brief(AE.iv(host)), PEQ.view_brief(AE.iv(client))]}
    turn = AE.barrier(host, client, host, client, ev)
    return {"turn_one_starts": turn, "turn_one_common": G3F.common(host, client, crash0)}, ev


FN = {"alien_next_cycles": row_alien_next_cycles, "alien_prev_wraps": row_alien_prev_wraps,
      "host_next_vanilla": row_host_next_vanilla, "turn_one": row_turn_one}


def main():
    t0 = time.time()
    fails = AE.run_boot("alien_cycle", ROWS, FN, setup_alien_cycle, "alien_equip_cycle_host",
                        "alien_equip_cycle_client")
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_alien_equip_cycle: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
