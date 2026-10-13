"""R5-U6 S-E rows EC1-EC4 (boot EM, gm2 STR_MEDIUM_SCOUT: the client plays the five sectoids, seat 1; the host the seven
X-COM soldiers, seat 0; default options, so "Enable XCOM Equipment for Aliens in PVP" is on and S-D gives the alien seat its
pre-battle screen): the PvP alien seat's PREV / NEXT on the pre-battle screen cycle its OWN aliens, the X-COM host's cycle
stays vanilla's, and turn 1 follows both OKs (owner D236 (b), R-U6-OF3, QU6-9 (a)).

Spec: docs repo rewrite/prompts/r5u6_pvp_options.md (d) Stage S-E and (f) `test_r5_alien_equip_cycle.py`, with AMENDMENT
U6-1.6's rules: ALIEN_IDS = the client seat's units with an inventory (faction HOSTILE, coop seat 1, not out, an armor with
allowInv) in battle_state.units order, read at the screens' open (fewer than two = FIXTURE-STOP); the host's soldier order =
TASK 0's record; NEXT / PREV = inventory_click {widget next | prev}. Constants: docs repo rewrite/r5u6-task0/se/CONSTANTS.md
(TASK 0 boots EMa, EMb on the HEAD build of 8d04bf087, equal).

Boot EM (key 49067): set_seed 1, the client joins and takes the Alien team (gamemode 2), the PSR drive without its last line
(mission STR_MEDIUM_SCOUT), the host's briefing OK -> its screen on H1, dismiss_client_briefing -> the client's screen on
ALIEN_IDS[0] (S-D's entry); both screens up.
  EC1  NEXT cycles the alien seat's own aliens: len(ALIEN_IDS) client NEXT presses: EC1-next
  EC2  PREV: one client PREV press: EC2-prev
  EC3  the X-COM host's cycle is vanilla's: len(HOST_ORDER) host NEXT presses: EC3-host
  EC4  turn 1: both OK -> the barrier: EC4-turn
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new lane crash file.

RED on the build without E2 (commit E1): EC1-next, EC2-prev; every other cell PASS. One EVIDENCE line per row, one PASS/FAIL
line per cell, then the row verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and
fails every row "boot"; a staging step past its bound fails that row "staging". WV-D95: run in the foreground to completion.
WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.
test_r5_alien_equip_off.py imports this file's helpers.

Run:  python tools/coop_test/test_r5_alien_equip_cycle.py
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_r5_pvp_gm3 as G3F  # noqa: E402
import test_w2_prebattle_equip as PEQ  # noqa: E402
import test_r5_alien_equip as AE  # noqa: E402

KEY = "49067"
SEED = 1                          # set_seed on the host before its lobby and right before newbattle_ok (BER / PSR)
MISSION = "STR_MEDIUM_SCOUT"
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
HOST_SEAT, CLIENT_SEAT = 0, 1
ALIEN_IDS_T0 = [1000000, 1000001, 1000002, 1000003, 1000004]   # TASK 0 EMa / EMb (EVIDENCE only: the cells read the rule)
HOST_ORDER = [9, 10, 11, 12, 13, 14, 8]   # TASK 0 EMa / EMb: the host's NEXT x 7 from H1 = 8 (U6-1.6: the record binds)
SCREEN_S = 15                     # each pre-battle screen's bound (TASK 0: <= 0.1 s)
ROWS = (("EC1", ("EC1-next", "EC1-common")),
        ("EC2", ("EC2-prev", "EC2-common")),
        ("EC3", ("EC3-host", "EC3-common")),
        ("EC4", ("EC4-turn", "EC4-common")))


# ===================== shared helpers (test_r5_alien_equip_off imports them) =====================


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
    """U6-1.6: `seat`'s units with an inventory (isSelectable(faction, false, true): the faction, not out, an armor with
    allowInv) in battle_state.units order."""
    return [u["id"] for u in battle_state(gc).get("units", []) if u.get("faction") == faction and u.get("coop") == seat
            and not u.get("isOut") and ARM.get(u.get("armor"), True)]


def drive(host, client, mission):
    """PSR drive_to_gm2_battlescape WITHOUT its last line (S-D's AE.drive with the mission a parameter, F10917)."""
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
    """Spawn, set_seed, S-D's lobby (the client on Alien, gamemode 2), the drive; a step past its bound is a Miss."""
    m = (host, client)
    G3F.guarded(tag, lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    G3F.guarded(tag, lambda: host.ok({"cmd": "set_seed", "seed": SEED}), m)
    gm = G3F.guarded(tag, lambda: AE.lobby_e6(host, client, key), m)
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


# ===================== boot EM =====================


def setup_em(host, client):
    m = (host, client)
    ctx = {"gm": lobby_drive(host, client, KEY, MISSION, "EM")}
    ctx["H1"], ctx["hostScreenS"] = host_screen(host, client, "EM")
    G3F.guarded("EM", lambda: session.dismiss_client_briefing(client), m)
    up, ctx["clientScreenS"] = AE.wait_until(lambda: PEQ.screen_up(client), SCREEN_S)
    if not up:
        G3F.capture("EM", f"the client's pre-battle screen never came up (stacks {stacks(host, client)})", m)
        raise G3F.Miss("EM")
    ids = {gc.name: own_ids(gc, FACTION_HOSTILE, CLIENT_SEAT) for gc in m}
    if len(ids["host"]) < 2 or ids["host"] != ids["client"]:
        G3F.capture("EM", f"ALIEN_IDS host {ids['host']} client {ids['client']} (want >= 2, equal on both; U6-1.6)", m)
        raise G3F.Miss("EM")
    ctx.update(ALIEN_IDS=ids["host"], soldiers=own_ids(host, FACTION_PLAYER, HOST_SEAT),
               counted=((AE.es(host, "equip") or {}).get("counted") or [])[:2],
               views=[PEQ.view_brief(AE.iv(host)), PEQ.view_brief(AE.iv(client))])
    return ctx


def row_ec1(host, client, ctx, crash0):
    A = ctx["ALIEN_IDS"]
    ev = {k: ctx[k] for k in ("gm", "H1", "hostScreenS", "clientScreenS", "ALIEN_IDS", "soldiers", "counted", "views")}
    ev.update(ALIEN_IDS_T0=ALIEN_IDS_T0, start=AE.iv(client).get("unitId"))
    if not AE.screen_on(client, A[0]):
        raise AssertionError(f"staging: the client's pre-battle screen is not on ALIEN_IDS[0] {A[0]} "
                             f"({PEQ.view_brief(AE.iv(client))})")
    rec = []
    for _ in A:
        press(client, "next", rec)
    got, want = [r["to"] for r in rec], A[1:] + A[:1]
    ev["presses"] = rec
    return {"EC1-next": (got == want, f"client unitIds after each NEXT {got} (want ALIEN_IDS[1:] + [ALIEN_IDS[0]] {want})"),
            "EC1-common": G3F.common(host, client, crash0)}, ev


def row_ec2(host, client, ctx, crash0):
    A = ctx["ALIEN_IDS"]
    ev = {"start": AE.iv(client).get("unitId")}
    if not PEQ.screen_up(client):
        raise AssertionError(f"staging: no pre-battle screen on the client ({PEQ.view_brief(AE.iv(client))})")
    rec = []
    got = press(client, "prev", rec)
    ev["presses"] = rec
    return {"EC2-prev": (got == A[-1], f"client unitId after one PREV {got} from {ev['start']} (want ALIEN_IDS[-1] "
                                       f"{A[-1]}, from ALIEN_IDS[0] {A[0]})"),
            "EC2-common": G3F.common(host, client, crash0)}, ev


def row_ec3(host, client, ctx, crash0):
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
    return {"EC3-host": (got == HOST_ORDER, f"host unitIds after each NEXT {got} (want TASK 0's soldier order {HOST_ORDER})"),
            "EC3-common": G3F.common(host, client, crash0)}, ev


def row_ec4(host, client, ctx, crash0):
    ev = {"views": [PEQ.view_brief(AE.iv(host)), PEQ.view_brief(AE.iv(client))]}
    turn = AE.barrier(host, client, host, client, ev)
    return {"EC4-turn": turn, "EC4-common": G3F.common(host, client, crash0)}, ev


FN = {"EC1": row_ec1, "EC2": row_ec2, "EC3": row_ec3, "EC4": row_ec4}


def main():
    t0 = time.time()
    fails = AE.run_boot("EM", ROWS, FN, setup_em, "r5u6_em_host", "r5u6_em_client")
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_r5_alien_equip_cycle: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
