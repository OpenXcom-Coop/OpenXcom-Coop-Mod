"""D248-U S-C row Q1 (boot Q; owner D280 (b) on OD248-B1, "as main"; QD248-10, F14427-F14430): the host's OWN tank,
parked at the SEPARATE partner's base on the host's craft, fights once in the host's battle as the host's tank and then
leaves the host's world: after the battle the host's craft holds no tank and the host's stores keep the tank's unfired
shells (vanilla's recovery credits the tank and its load; the tank leaves the stores again, main DebriefingState.cpp
:2947-:2955). The partner's world is untouched.

Spec: docs repo rewrite/prompts/d248u_client_tank_host_craft.md, AMENDMENT D248-1 section 8 "Stage S-C" (option (b) only),
SB-1 (section 4) for the ending; orchestrator rulings on AMENDMENT D248-1 (D280 (b)). Constants:
rewrite/d248u-task0/sb/CONSTANTS.md section Q (T0-Q boots Qa, Qb) and its subsection "Qc (S-C red, session 42155bc1)".

Boot Q (SEPARATE, port 47614, dirs d248u_q_host / d248u_q_client): session.bring_up_separate_guest_battle(host, client,
"47614", pre_mission_start=park) (3 host soldiers + the partner's "Guest Zzz" on the host's Skyranger), pin_ai_neutral.
park (both machines on their own geoscape; each missed step = ONE CAPTURE Q line, every cell FAILs "boot"):
  1 HOST_SKY; HOST_SQUAD = the helper's three sorted ids; the host unseats the third (2 soldiers + the 4-space tank leave
    the guest its seat, F14429); HOST_SQUAD = the first two. 2 PARTNER_BASE, PARTNER_BASE_COOP (the client's base_report
    coopBaseId, rolled per boot), CLIENT_SKY. 3 the client's give_items 1 STR_TANK_CANNON + 30 STR_HWP_CANNON_SHELLS
    (stored [1, 30]). 4 S0H / S0P (the host's / the partner's storage {tank, shells}). 5 the host visits PARTNER_BASE
    (insideCoopBase within 60 s): PEER_SKY = the view's STR_SKYRANGER, view stores v0, view SPACE USED used0. 6 the host's
    craft_equip of one tank onto PEER_SKY in the visited base: moved true, view stores v0 - {1, 30}, SPACE USED used0 + 4.
  7 open_soldiers / SoldiersState within 30 s / soldiers_ok / leave_base / the host back on its geoscape. 8 PARK_H0 = the
    host's craft_vehicles HOST_SKY.
  Q1  Q1-park (precondition: PARK_H0 == {vehicles {STR_TANK_CANNON: 1}, vehicleCoop [[PARTNER_BASE_COOP, PEER_SKY,
      "STR_SKYRANGER"]], vehicleAmmo [30]}; host storage == S0H; partner storage == S0P; the partner's CLIENT_SKY holds no
      tank), Q1-unit (exactly one STR_TANK_CANNON unit on both machines, guestTank "", soldierId -1, coop 0, the same id:
      H), Q1-guest ("Guest Zzz" on both, coop 1; HOST_SQUAD's two units coop 0), Q1-common (in the battle, before the
      kills), Q1-end (precondition, SB-1: every live hostile killed, chain_settled after each, no other unit out; END TURN
      on both; the host's NextTurnState closed; the host's DebriefingState; the partner's display-only one; the partner's
      OK through its follow-ups to its GeoscapeState; the host's OK + drain to its GeoscapeState), Q1-home (the host's
      HOST_SKY after the drain holds no STR_TANK_CANNON), Q1-stores (the host's storage after the drain == S0H +
      {STR_HWP_CANNON_SHELLS: H_AMMO}; H_AMMO = the qty of the shells item H's weapon lists, read after the kills: 30
      unfired), Q1-partner (after the partner's OK: its storage == S0P, CLIENT_SKY holds no tank).
Red at the S-C red (base adfb542b0; the tip keeps the tank as an ordinary host tank, OD248-B1 (c)): Q1-home and Q1-stores
FAIL; every other cell PASS. Green: EQ2b (DebriefingState reequipCraft).

One EVIDENCE line per row (both machines' player units {id, type, coop, soldierId, guestTank}, the host's guestContrib, the
debriefings' titles, H_AMMO), then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure; a
cell whose precondition failed FAILs "not reached (<cell> failed)". Common cell: every hash bucket EQUAL, desyncSeen false
on both, no new crash file. Ids come from probes (S25); a key the build does not write reads as absent. WV-D95: run in the
foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_host_parked.py
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
import test_battle_end_separate as SEP  # noqa: E402
import test_tank_entry as TE  # noqa: E402

PORT = "47614"
TANK, SHELLS, SKYR = TE.TANK, TE.SHELLS, TE.SKYR
GUEST = "Guest Zzz"
SHELLS_GIVEN = 30          # step 3 (R-D248-SA-1: one tank load takes 30; T0-Q Qa, Qb, Qc stored [1, 30])
STEP_S = 30                # every bounded staging wait (SoldiersState, the host idle)
VISIT_S = 60               # insideCoopBase after visit_coop_base (Qa / Qb / Qc: 0.75 s)
KILL_S = 45                # SEP chain_settled after each kill (Qc: 2.21-5.84 s)
DEBRIEF_S = 60             # the host's DebriefingState after the NextTurnState close (Qc: 0.05 s)
DRAIN_S = 60               # the host's OK + follow-ups down to its GeoscapeState (Qc: no follow-up screen)
VKEYS = ("vehicles", "vehicleCoop", "vehicleAmmo")
ROWS = (("Q1", ("Q1-park", "Q1-unit", "Q1-guest", "Q1-common", "Q1-end", "Q1-home", "Q1-stores", "Q1-partner")),)

not_reached = OWN.not_reached


def park(host, client, pins):
    """AMENDMENT D248-1 section 8 steps 1-8 (pre_mission_start; both machines on their own geoscape). Steps 1-7 are
    construction steps (an assert = the boot's CAPTURE); step 8's reads feed the Q1-park cell."""
    # 1
    sky = session._campaign_skyranger(host)["id"]
    three = sorted(s["id"] for s in session._campaign_own_roster_base(host)["soldiers"])[:3]
    un = host.cmd({"cmd": "craft_assign", "craft_id": sky, "soldier_id": three[2], "on": False})
    assert un.get("ok") is not False and un.get("seated") is False, f"step 1: the host's unseat of {three[2]}: {un}"
    pins.update(HOST_SKY=sky, squad3=three, HOST_SQUAD=three[:2])
    # 2
    pins["PARTNER_BASE"] = session._campaign_own_roster_base(client)["name"]
    pins["PARTNER_BASE_COOP"] = client.ok({"cmd": "base_report"}).get("coopBaseId")
    pins["CLIENT_SKY"] = session._campaign_skyranger(client)["id"]
    # 3
    g = [client.ok({"cmd": "give_items", "item": it, "count": n}).get("stored") for it, n in ((TANK, 1), (SHELLS, SHELLS_GIVEN))]
    assert g == [1, SHELLS_GIVEN], f"step 3: the client's give_items stored {g} (want [1, {SHELLS_GIVEN}])"
    # 4
    pins["S0H"], pins["S0P"] = TE.storage(host)[0], TE.storage(client)[0]
    # 5
    base = pins["PARTNER_BASE"]
    host.ok({"cmd": "visit_coop_base", "base": base})
    host.wait_for("host inside partner base", lambda: host.cmd({"cmd": "get_coop"}).get("insideCoopBase") or None,
                  timeout=VISIT_S)
    v0, rep = TE.storage(host, coop=True)
    peer = [c.get("id") for c in rep.get("crafts") or [] if c.get("type") == SKYR]
    assert len(peer) >= 1, f"step 5: no {SKYR} in the host's view of {base}: {rep.get('crafts')}"
    pins["PEER_SKY"] = peer[0]
    used0 = TE.view_space_used(host, peer[0])
    assert v0[TANK] >= 1 and v0[SHELLS] >= TE.CLIPS and used0 is not None, \
        f"step 5: view stores {v0} (want a tank and {TE.CLIPS} shells), view SPACE USED {used0}"
    # 6
    ce = host.cmd({"cmd": "craft_equip", "base": base, "craft_id": peer[0], "item": TANK, "count": 1})
    v1, used1 = TE.storage(host, coop=True)[0], TE.view_space_used(host, peer[0])
    pins.update(view=[v0, v1], viewSpaceUsed=[used0, used1])
    assert (ce.get("moved") is True and v1 == {TANK: v0[TANK] - 1, SHELLS: v0[SHELLS] - TE.CLIPS}
            and used1 == used0 + TE.TANK_SIZE), \
        f"step 6: the host's load: craft_equip {ce}; view stores {v0} -> {v1} (want tank -1, shells -{TE.CLIPS}); " \
        f"view SPACE USED {used0} -> {used1} (want +{TE.TANK_SIZE})"
    # 7
    host.ok({"cmd": "open_soldiers", "base": base})
    host.wait_for("host soldiers screen", lambda: session.has_state(host, "SoldiersState") or None, timeout=STEP_S)
    host.ok({"cmd": "soldiers_ok"})
    host.ok({"cmd": "leave_base"})
    session.wait_back_on_geoscape(host, "host back on geoscape")
    # 8
    pins["PARK_H0"] = TE.craft_vehicles(host, sky)
    pins["storage8"] = [TE.storage(host)[0], TE.storage(client)[0]]
    pins["clientSky8"] = TE.craft_vehicles(client, pins["CLIENT_SKY"])
    keys = ("HOST_SKY", "HOST_SQUAD", "PARTNER_BASE_COOP", "CLIENT_SKY", "PEER_SKY", "S0H", "S0P", "PARK_H0")
    print(f"park: pins {dict((k, pins.get(k)) for k in keys)}", flush=True)


def bring_up(host, client):
    """The boot: spawn, the helper with park, pin_ai_neutral, the host idle. Returns (pins, crash0); a miss: CAPTURE Q."""
    m, pins = (host, client), {}
    crash0 = session._crash_log_snapshot()

    def up():
        host.spawn(); client.spawn(); host.connect(); client.connect()
        squad, guest = session.bring_up_separate_guest_battle(host, client, port=PORT,
                                                              pre_mission_start=lambda h, c: park(h, c, pins))
        pins.update(helperSquad=squad, guestId=guest)
    TE.guarded("Q", up, m)
    TE.guarded("Q", lambda: session.pin_ai_neutral(host, client, tag="d248uq"), m)
    TE.guarded("Q", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    return pins, crash0


def h_ammo(gc, hid):
    """H_AMMO: the qty of the STR_HWP_CANNON_SHELLS battle item H's weapon lists (Qc: 30, item 1), else None."""
    items = gc.cmd({"cmd": "battle_items"}).get("items") or []
    by_id = {i.get("id"): i for i in items}
    q = [by_id[a].get("qty") for w in items if w.get("owner") == hid and not w.get("isAmmo")
         for a in (w.get("ammo") or []) if (by_id.get(a) or {}).get("type") == SHELLS]
    return q[0] if len(q) == 1 else None


def live(gc, faction):
    return [u["id"] for u in battle_state(gc).get("units", []) if u.get("faction") == faction and not u.get("isOut")]


def ending(host, client, pins, ev):
    """SB-1: the kills (chain_settled after each; no unit other than the hostiles out), H_AMMO, END TURN on both, the host's
    NextTurnState closed, both debriefings, the partner's OK (its storage and CLIENT_SKY read right after), the host's OK +
    drain. Returns the Q1-end cell."""
    bad, hostiles, kills = [], live(host, 1), []
    players0 = [sorted(live(gc, 0)) for gc in (host, client)]
    for uid in hostiles:
        r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": uid})
        ok, secs, _s = SEP.chain_settled(host, client, timeout=KILL_S)
        kills.append([uid, r.get("killed"), ok, secs])
    left, players1 = live(host, 1), [sorted(live(gc, 0)) for gc in (host, client)]
    pins["H_AMMO"] = h_ammo(host, pins["H"]) if pins.get("H") is not None else None
    ev.update(hostiles=len(hostiles), kills=kills, liveAfter=left, players=[players0, players1], H_AMMO=pins["H_AMMO"])
    if not hostiles or not all(k[2] for k in kills) or left:
        bad.append(f"{len(hostiles)} hostiles, each settled within {KILL_S} s {[k[2] for k in kills]}, live after {left}")
    if players1 != players0:
        bad.append(f"player units live host/partner {players0} -> {players1} (want unchanged: only the hostiles killed)")
    SEP.end_turn_both(host, client)
    nt = SEP.close_host_nextturn(host, timeout=DEBRIEF_S)
    hok, hs = SEP.wait_until(lambda: "DebriefingState" in SEP.stack(host), DEBRIEF_S)
    ev.update(nextTurn=nt and nt.get("handled"), hostDebriefS=hs,
              hostDebriefTitle=host.cmd({"cmd": "debrief_state"}).get("title"))
    if not hok:
        bad.append(f"no host DebriefingState within {DEBRIEF_S} s (host stack {SEP.stack(host)})")
    cok, cs = SEP.wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                      and d.get("displayOnly") is True)(client.cmd({"cmd": "debrief_state"})),
                             SEP.CLIENT_DEBRIEF_S)
    ev.update(partnerDebriefS=cs, partnerDebriefTitle=client.cmd({"cmd": "debrief_state"}).get("title"))
    if not cok:
        bad.append(f"no partner display-only DebriefingState within {SEP.CLIENT_DEBRIEF_S} s (stack {SEP.stack(client)})")
    ctx = {}
    ok1, reached, secs = SEP.client_ok_through_followups(client, ctx, "ret")
    sep = SEP.record(client).get("sepReturn") or {}
    ev.update(partnerOk=ok1, partnerGeo=[reached, secs], partnerChain=(ctx.get("ret") or {}).get("clientChain"), sepReturn=sep)
    ev["partnerAfterOk"] = [TE.storage(client)[0], TE.craft_vehicles(client, pins["CLIENT_SKY"])]
    if not (ok1.get("pressed") and reached and sep.get("ownLoaded") == 1):
        bad.append(f"the partner's OK {ok1}: clean GeoscapeState {reached} ({secs} s), sepReturn.ownLoaded "
                   f"{sep.get('ownLoaded')!r} (want 1)")
    okh = SEP.press_ok(host)
    hreached, screens = SEP.drain(host, timeout=DRAIN_S) if okh["pressed"] else (False, [])
    ev.update(hostOk=okh, hostGeo=hreached, hostScreens=screens)
    if not (okh["pressed"] and hreached):
        bad.append(f"the host's OK {okh}: GeoscapeState {hreached} within {DRAIN_S} s (screens {screens})")
    return (not bad, "; ".join(bad) if bad else
            f"{len(hostiles)} hostiles killed (each settled), player units unchanged {players1}; END TURN; host NextTurnState "
            f"{ev['nextTurn']}; host debriefing {ev['hostDebriefTitle']!r} ({hs} s); partner display-only ({cs} s); partner OK "
            f"-> GeoscapeState ({secs} s), sepReturn.ownLoaded 1; host OK + drain -> GeoscapeState")


def row_q1(host, client, pins, crash0):
    cells, ev = {}, {"pins": {k: pins.get(k) for k in ("HOST_SKY", "squad3", "HOST_SQUAD", "PARTNER_BASE_COOP", "CLIENT_SKY",
                                                         "PEER_SKY", "S0H", "S0P", "view", "viewSpaceUsed", "guestId")}}
    want = {"vehicles": {TANK: 1}, "vehicleCoop": [[pins["PARTNER_BASE_COOP"], pins["PEER_SKY"], SKYR]],
            "vehicleAmmo": [TE.TANK_AMMO]}
    park0 = {k: pins["PARK_H0"].get(k) for k in VKEYS}
    st8, cs8 = pins["storage8"], pins["clientSky8"]
    cells["Q1-park"] = (park0 == want and st8 == [pins["S0H"], pins["S0P"]] and TANK not in (cs8.get("vehicles") or {}),
                        f"host craft_vehicles {pins['HOST_SKY']} {park0} (want {want}); host / partner storage {st8} (want "
                        f"S0H / S0P {[pins['S0H'], pins['S0P']]}); partner craft_vehicles {pins['CLIENT_SKY']} {cs8} "
                        f"(want no {TANK})")
    uh, uc = TE.unit_view(host), TE.unit_view(client)
    ev.update(units={"host": uh, "partner": uc},
              guestContrib={"host": TE.guest_contrib(host), "partner": TE.guest_contrib(client)},
              hostLog=[ln for ln in TE.log_lines(host) if TE.GT_LOG in ln][-8:])
    hv = [[{k: u.get(k) for k in ("id", "guestTank", "soldierId", "coop")} for u in g if u.get("type") == TANK]
          for g in (uh, uc)]
    ok = len(hv[0]) == 1 and hv[0] == hv[1] and {k: hv[0][0][k] for k in ("guestTank", "soldierId", "coop")} == \
        {"guestTank": "", "soldierId": -1, "coop": 0}
    pins["H"] = hv[0][0]["id"] if ok else None
    cells["Q1-unit"] = (ok, f"{TANK} units host/partner {hv} (want exactly one on each, guestTank '', soldierId -1, coop 0, "
                            f"the same id: H)")
    gs = [[u.get("coop") for u in g if u.get("name") == GUEST] for g in (uh, uc)]
    sq = [sorted((u.get("soldierId"), u.get("coop")) for u in g if u.get("soldierId") in pins["HOST_SQUAD"]
                 and u.get("name") != GUEST) for g in (uh, uc)]
    wsq = [(s, 0) for s in pins["HOST_SQUAD"]]
    cells["Q1-guest"] = (gs == [[1], [1]] and sq == [wsq, wsq], f"{GUEST!r} coop host/partner {gs} (want [1] on both); "
                                                                 f"HOST_SQUAD (soldierId, coop) host/partner {sq} (want {wsq})")
    cells["Q1-common"] = G3F.common(host, client, crash0)
    cells["Q1-end"] = ending(host, client, pins, ev.setdefault("end", {}))
    hc, st = TE.craft_vehicles(host, pins["HOST_SKY"]), TE.storage(host)[0]
    ev.update(hostCraftAfter=hc, hostStorageAfter=st, partnerAfterHostOk=[TE.storage(client)[0],
                                                                           TE.craft_vehicles(client, pins["CLIENT_SKY"])])
    cells["Q1-home"] = (hc.get("error") is None and TANK not in (hc.get("vehicles") or {}),
                        f"host craft_vehicles {pins['HOST_SKY']} after the drain {hc} (want no {TANK}: the tank fought once "
                        f"and left the host's world)")
    ha = pins.get("H_AMMO")
    wst = {TANK: pins["S0H"][TANK], SHELLS: pins["S0H"][SHELLS] + ha} if isinstance(ha, int) else None
    cells["Q1-stores"] = (wst is not None and st == wst,
                          f"host storage after the drain {st} (want S0H {pins['S0H']} + {{{SHELLS}: H_AMMO {ha!r}}} = {wst}: "
                          f"no tank, its unfired shells kept)")
    pst, psky = ev["end"].get("partnerAfterOk") or [None, {}]
    cells["Q1-partner"] = (pst == pins["S0P"] and TANK not in ((psky or {}).get("vehicles") or {}),
                           f"after the partner's OK: partner storage {pst} (want S0P {pins['S0P']}); craft_vehicles "
                           f"{pins['CLIENT_SKY']} {psky} (want no {TANK})")
    if not cells["Q1-park"][0]:
        not_reached(cells, ("Q1-unit", "Q1-home", "Q1-stores"), "Q1-park failed")
    if not cells["Q1-end"][0]:
        not_reached(cells, ("Q1-home", "Q1-stores", "Q1-partner"), "Q1-end failed")
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("d248u_q_host"))
    client = GameClient("client", None, make_user_dir("d248u_q_client"))
    fails = 0
    try:
        try:
            pins, crash0 = bring_up(host, client)
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE Q line)")
        else:
            fails += G3F.run_row("Q1", ROWS[0][1], lambda: row_q1(host, client, pins, crash0))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_host_parked: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
