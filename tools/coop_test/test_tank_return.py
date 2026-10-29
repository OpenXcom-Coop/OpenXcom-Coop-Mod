"""D248-U S-B row R1 (boot RS; owner D248 (b), D235, D240 (a)): a SEPARATE partner's own tank parked on the host's craft
fights in the host's battle (S-A), the host gives it to the partner (R5-U5's order), it survives, and at the battle's end it
goes home: the host's stores never take it or its shells, the host's battleEnd lists it (lost false), the partner's parked
tank stays.

Spec: docs repo rewrite/prompts/d248u_client_tank_host_craft.md section (f) test_tank_return.py, as amended by
AMENDMENT D248-1 section 4 (SB-1 the ending: the kills, END TURN on both, the host's NextTurnState closed; SB-2 the gift
through test_battle_gift_keep's lever_gifts + turn_cell; SB-3 30 shells, S0 {2, 30}) and section 5 (each pin's rule);
rulings QD248-1 .. QD248-11 (a), R-D248-SA-1, QD248-B1-1 .. -4 (a). Constants: rewrite/d248u-task0/sb/CONSTANTS.md (TASK 0
boots RSa, RSb, RLa, RLb).

Boot RS (SEPARATE, port 47613, dirs d248u_rs_host / d248u_rs_client): test_tank_entry.bring_up_tank_battle(host,
client, "47613") with a pre_mission hook reading S0 (the host's storage {STR_TANK_CANNON, STR_HWP_CANNON_SHELLS}) and PARK0
(the partner's craft_vehicles on its own Skyranger), then pin_ai_neutral. Pins (each boot, from probes): HOST_BASE_COOP,
HOST_SKY, CLIENT_SKY, TAG = "coop-guest-tank:1:<HOST_BASE_COOP>:<HOST_SKY>:STR_SKYRANGER", T = the one STR_TANK_CANNON unit
whose guestTank == TAG on both machines. Boot guards: PARK0 is the parked tank (vehicles {STR_TANK_CANNON: 1}, vehicleCoop
[[HOST_BASE_COOP, HOST_SKY, "STR_SKYRANGER"]], vehicleAmmo [30]); T exists.
  R1  R1-gift (precondition: the host's battle_gift {T, owner 1} lands on both and the partner's notice is cleared, then the
      partner's turn of T is admitted: one new host context (intent, turn, T), T faces it on both), R1-common (before the
      kills), R1-end (precondition: every live hostile killed, chain_settled after each; END TURN on both; the host's
      NextTurnState closed; the host's DebriefingState; the partner's display-only DebriefingState; the partner's OK through
      its follow-ups to its GeoscapeState with sepReturn.ownLoaded 1; the host's OK + drain to its GeoscapeState), R1-record
      (the host's battleEnd.guestTanks == [{ownerSeat 1, baseId HOST_BASE_COOP, craftId HOST_SKY, craftType STR_SKYRANGER,
      type STR_TANK_CANNON, unitId T, lost false}]), R1-stores (the host's storage == S0), R1-craft (the host's Skyranger
      holds no tank), R1-home (the partner's Skyranger == PARK0), R1-sep (the partner's sepReturn tanksLost 0, tanksMissing 0).
Red at B1 (the S-A green build): R1-record (absent), R1-stores (vanilla's credit: +1 tank, +30 shells), R1-sep (absent)
FAIL; every other cell PASS.

Shared with test_tank_lost: bring_up (the boot, its pins and guards), ending (SB-1), record_cells, after_cells.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure; a cell
whose precondition failed FAILs "not reached (<cell> failed)". A boot step past its bound prints ONE CAPTURE line and fails
every row "boot". Common cell: every hash bucket EQUAL, desyncSeen false on both, no new crash file. Ids come from probes
(S25); a key the build does not write reads as absent. run in the foreground to completion. ONE
run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_tank_return.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_ownerless_units as OWN  # noqa: E402
import test_battle_gift as GF  # noqa: E402
import test_battle_gift_keep as KEEP  # noqa: E402
import test_battle_end_separate as SEP  # noqa: E402
import test_tank_entry as TE  # noqa: E402

PORT = "47613"
TANK, SKYR = TE.TANK, TE.SKYR
STEP_S = 30                # every bounded staging wait (TASK 0: the gift lands in 0.1 s, the turn in 0.2 s)
KILL_S = 45                # SEP chain_settled after each kill (TASK 0: 2.21-2.62 s)
DEBRIEF_S = 60             # the host's DebriefingState after the NextTurnState close (TASK 0: 0.05 s)
CLIENT_DEBRIEF_S = 20      # the partner's display-only DebriefingState (SEP's CLIENT_DEBRIEF_S; TASK 0: 0.05 s)
DRAIN_S = 60               # the host's OK + follow-ups down to its GeoscapeState (TASK 0: no follow-up screen)
STATUS_DEAD = 6
VKEYS = ("vehicles", "vehicleCoop", "vehicleAmmo")
ROWS = (("R1", ("R1-gift", "R1-common", "R1-end", "R1-record", "R1-stores", "R1-craft", "R1-home", "R1-sep")),)

units = G3F.units
not_reached = OWN.not_reached


# ===================== shared with test_tank_lost =====================


def bring_up(host, client, port, tag):
    """The boot: bring_up_tank_battle with the pre_mission reads of S0 and PARK0, pin_ai_neutral, the pins TAG / T and the
    PARK0 guard. Returns (pins, crash0). Every miss: ONE CAPTURE <tag> line, then G3F.Miss."""
    m, pre = (host, client), {}

    def pre_mission(h, c, pins):
        pre["S0"] = TE.storage(h)[0]
        pre["PARK0"] = {k: TE.craft_vehicles(c, pins["CLIENT_SKY"]).get(k) for k in VKEYS}

    crash0 = session._crash_log_snapshot()
    pins = TE.guarded(tag, lambda: TE.bring_up_tank_battle(host, client, port, pre_mission=pre_mission), m)
    TE.guarded(tag, lambda: session.pin_ai_neutral(host, client, tag="d248u"), m)
    pins.update(pre)
    pins["TAG"] = "coop-guest-tank:1:%d:%d:%s" % (pins["HOST_BASE_COOP"], pins["HOST_SKY"], SKYR)

    def pin_t():
        want = {"vehicles": {TANK: 1}, "vehicleCoop": [[pins["HOST_BASE_COOP"], pins["HOST_SKY"], SKYR]],
                "vehicleAmmo": [TE.TANK_AMMO]}
        assert pins.get("PARK0") == want, f"PARK0 {pins.get('PARK0')} (want {want}: the partner's parked tank)"
        t = [sorted(u["id"] for u in battle_state(gc).get("units", [])
                    if u.get("type") == TANK and u.get("guestTank") == pins["TAG"]) for gc in m]
        assert len(t[0]) == 1 and t[0] == t[1], \
            f"{TANK} units with guestTank {pins['TAG']!r} host/partner {t} (want exactly one, the same id: T)"
        pins["T"] = t[0][0]
        session.wait_host_idle(host, client, timeout=STEP_S)
    TE.guarded(tag, pin_t, m)
    print(f"boot {tag}: pins {dict((k, pins.get(k)) for k in ('HOST_BASE_COOP', 'HOST_SKY', 'CLIENT_SKY', 'T', 'TAG', 'S0'))}",
          flush=True)
    return pins, crash0


def ev0(host, client, pins):
    """The EVIDENCE start: the pins, both machines' player units and the host's [coop-guest-tank] log lines."""
    return {"pins": {k: pins.get(k) for k in ("HOST_BASE_COOP", "HOST_SKY", "CLIENT_SKY", "guest_id", "T", "TAG", "S0",
                                              "PARK0")},
            "units": {"host": TE.unit_view(host), "partner": TE.unit_view(client)},
            "hostLog": [ln for ln in TE.log_lines(host) if TE.GT_LOG in ln][-8:]}


def live_hostiles(gc):
    return [u["id"] for u in battle_state(gc).get("units", []) if u.get("faction") == 1 and not u.get("isOut")]


def ending(host, client, ev):
    """SB-1: every live faction-1 unit killed (chain_settled after each), END TURN on both, the host's NextTurnState closed,
    the host's DebriefingState, the partner's display-only one, the partner's OK through its follow-ups (its GeoscapeState,
    sepReturn.ownLoaded 1), the host's OK + drain (its GeoscapeState). Returns the <row>-end cell."""
    bad, hostiles, kills = [], live_hostiles(host), []
    for uid in hostiles:
        r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": uid})
        ok, secs, _s = SEP.chain_settled(host, client, timeout=KILL_S)
        kills.append([uid, r.get("killed"), ok, secs])
    left = live_hostiles(host)
    ev.update(hostiles=len(hostiles), kills=kills, liveAfter=left)
    if not hostiles or not all(k[2] for k in kills) or left:
        bad.append(f"{len(hostiles)} hostiles, each settled within {KILL_S} s {[k[2] for k in kills]}, live after {left}")
    SEP.end_turn_both(host, client)
    nt = SEP.close_host_nextturn(host, timeout=DEBRIEF_S)
    hok, hs = SEP.wait_until(lambda: "DebriefingState" in SEP.stack(host), DEBRIEF_S)
    hd = host.cmd({"cmd": "debrief_state"})
    ev.update(nextTurn=nt and nt.get("handled"), hostDebriefS=hs,
              hostDebrief={k: hd.get(k) for k in ("shown", "onTop", "displayOnly", "title")})
    if not hok:
        bad.append(f"no host DebriefingState within {DEBRIEF_S} s (host stack {SEP.stack(host)})")
    cok, cs = SEP.wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                      and d.get("displayOnly") is True)(client.cmd({"cmd": "debrief_state"})),
                             CLIENT_DEBRIEF_S)
    ev["partnerDebriefS"] = cs
    if not cok:
        bad.append(f"no partner display-only DebriefingState within {CLIENT_DEBRIEF_S} s (stack {SEP.stack(client)})")
    ctx = {}
    ok1, reached, secs = SEP.client_ok_through_followups(client, ctx, "ret")
    sep = SEP.record(client).get("sepReturn") or {}
    ev.update(partnerOk=ok1, partnerGeo=[reached, secs], partnerChain=(ctx.get("ret") or {}).get("clientChain"),
              sepReturn=sep)
    if not (ok1.get("pressed") and reached and sep.get("ownLoaded") == 1):
        bad.append(f"the partner's OK {ok1}: clean GeoscapeState {reached} ({secs} s), sepReturn.ownLoaded "
                   f"{sep.get('ownLoaded')!r} (want 1)")
    okh = SEP.press_ok(host)
    hreached, screens = SEP.drain(host, timeout=DRAIN_S) if okh["pressed"] else (False, [])
    ev.update(hostOk=okh, hostGeo=hreached, hostScreens=screens)
    if not (okh["pressed"] and hreached):
        bad.append(f"the host's OK {okh}: GeoscapeState {hreached} within {DRAIN_S} s (screens {screens})")
    return (not bad, "; ".join(bad) if bad else
            f"{len(hostiles)} hostiles killed (each settled); END TURN; host NextTurnState {ev['nextTurn']}; host debriefing "
            f"{ev['hostDebrief']} ({hs} s); partner display-only ({cs} s); partner OK -> GeoscapeState ({secs} s), "
            f"sepReturn.ownLoaded 1; host OK + drain -> GeoscapeState")


def record_cells(host, client, pins, lost, ev):
    """<row>-record (the host's battleEnd.guestTanks) and <row>-sep (the partner's sepReturn tank counts)."""
    want = [{"ownerSeat": 1, "baseId": pins["HOST_BASE_COOP"], "craftId": pins["HOST_SKY"], "craftType": SKYR, "type": TANK,
             "unitId": pins["T"], "lost": lost}]
    gt = SEP.record(host).get("guestTanks")
    sep = SEP.record(client).get("sepReturn") or {}
    tl, wl = [sep.get("tanksLost"), sep.get("tanksMissing")], [1 if lost else 0, 0]
    ev.update(guestTanks=gt, sepTanks=tl)
    return ((gt == want, f"host battleEnd.guestTanks {gt!r} (want {want})"),
            (tl == wl, f"partner sepReturn tanksLost / tanksMissing {tl} (want {wl}); sepReturn {sep}"))


def after_cells(host, client, pins, ev):
    """After both OKs: <row>-stores (the host's storage == S0), the host's Skyranger cell, and the partner's Skyranger."""
    st = TE.storage(host)[0]
    hc = TE.craft_vehicles(host, pins["HOST_SKY"])
    pc = TE.craft_vehicles(client, pins["CLIENT_SKY"])
    ev.update(hostStorage=st, hostCraft=hc, partnerCraft=pc)
    stores = (st == pins["S0"], f"host storage after the drain {st} (want S0 {pins['S0']}: the host's stores never take "
                                f"the partner's tank or its shells)")
    craft = (hc.get("error") is None and TANK not in (hc.get("vehicles") or {}),
             f"host craft_vehicles {pins['HOST_SKY']} after the drain {hc} (want no {TANK})")
    return stores, craft, pc


# ===================== boot RS =====================


def row_r1(host, client, pins, crash0):
    cells, ev = {}, ev0(host, client, pins)
    T = pins["T"]
    landed, miss = KEEP.lever_gifts([(host, T, 1)], host, client, ev)
    got = GF.coops(host, client, T)
    g = (ev.get("gifts") or [{}])[0]
    t_ok, t_txt = KEEP.turn_cell(host, client, T, ev) if landed else (False, "the turn not tried (the gift did not land)")
    cells["R1-gift"] = (landed and t_ok, f"host battle_gift {{{T}, owner 1}}: unit {T} coop host/partner {got} (want [1, 1] "
                                         f"within {STEP_S} s){'; ' + miss if miss else ''}; partner notices "
                                         f"{g.get('notices')} cleared {g.get('cleared')}; {t_txt}")
    cells["R1-common"] = G3F.common(host, client, crash0)
    cells["R1-end"] = ending(host, client, ev.setdefault("end", {}))
    cells["R1-record"], cells["R1-sep"] = record_cells(host, client, pins, False, ev)
    cells["R1-stores"], cells["R1-craft"], pc = after_cells(host, client, pins, ev)
    home = {k: pc.get(k) for k in VKEYS}
    cells["R1-home"] = (home == pins["PARK0"], f"partner craft_vehicles {pins['CLIENT_SKY']} after both OKs {home} (want "
                                               f"PARK0 {pins['PARK0']}: the surviving tank stays parked)")
    pre = "R1-gift" if not cells["R1-gift"][0] else "R1-end" if not cells["R1-end"][0] else None
    if pre:
        not_reached(cells, ("R1-record", "R1-stores", "R1-craft", "R1-home", "R1-sep"), f"{pre} failed")
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("d248u_rs_host"))
    client = GameClient("client", None, make_user_dir("d248u_rs_client"))
    fails = 0
    try:
        try:
            pins, crash0 = bring_up(host, client, PORT, "RS")
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE RS line)")
        else:
            fails += G3F.run_row("R1", ROWS[0][1], lambda: row_r1(host, client, pins, crash0))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_tank_return: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
