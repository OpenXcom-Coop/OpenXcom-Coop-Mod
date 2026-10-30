"""A SEPARATE partner's own tank parked on the host's craft enters the host's battle, tagged as the partner's, and the
HOST commands it (the existing seat rules, no new rule).

bring_up_tank_battle (imported by test_tank_gate / _return / _lost): a copy of session.bring_up_separate_guest_battle
with its host squad cut to `host_soldiers`, plus (i) the host's give_items STR_TANK_CANNON (1 when `host_tank_on_craft`,
else 2) and 30 STR_HWP_CANNON_SHELLS right after its squad is seated, and with `host_tank_on_craft` the host's
craft_equip of one tank onto its Skyranger (its craft list then holds the tank); (ii) inside the partner's visit, after
the guest's craft_assign: the partner's craft_equip of one tank onto the host's Skyranger in the visited base (the
view's stores lose one tank and 30 shells and the view craft's SPACE USED grows by the tank's size: no probe reads a
visited craft's vehicle list); (iii) a `pre_mission` callback after leave_base, before the mission spawn. Each missed
step is a setup failure. Each parked tank takes 30 shells, HOST_BASE_COOP is read on every boot, and the craft's vehicle
list is asserted after every craft_equip.

Boot (SEPARATE, port 47611, dirs tank_entry_host / tank_entry_client): bring_up_tank_battle(host, client, "47611");
pin_ai_neutral. TAG = "coop-guest-tank:1:<HOST_BASE_COOP>:<HOST_SKY>:STR_SKYRANGER" (HOST_BASE_COOP from this boot's
base_report).
  parked_tank_enters: the partner's parked tank enters the host's battle: parked_on_craft (pre_mission: the partner's
  Skyranger holds the parked tank, tagged; the host's stores 2 tanks / 30 shells), partner_sent (the partner's
  guestContrib.vehSent 1), host_stored (the host's guestContrib.vehicles[1] 1), tank_unit (one STR_TANK_CANNON unit on
  both, faction 0, soldierId -1, the same id: T), tank_tag (T's guestTank == TAG on both), tank_seat (T's coop 0 on
  both), host_craft_empty (the host's Skyranger holds no tank in the battle), host_stores_kept (the host's stores 2 / 30
  in the battle), enters_common.
  host_commands_tank: the host commands it, the partner does not: host_selects (the host's TAB selects T),
  partner_refused (the partner's turn intent on T is refused not_your_unit, no new host context, T's direction unchanged
  on both), commands_common.
Without the fix partner_sent, host_stored, tank_unit, tank_tag, tank_seat, host_selects, partner_refused FAIL; every
other cell PASS.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure. A
boot step past its bound prints ONE CAPTURE line and fails every row "boot"; a cell whose precondition failed FAILs "not
reached". Common cell: every hash bucket EQUAL, desyncSeen false on both, no new crash file. A key the build does not
write reads as absent. Run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when every
cell passes, else 2.

Run:  python tools/coop_test/test_tank_entry.py
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_ownerless_units as OWN  # noqa: E402
from test_seat_pacing import tab_select  # noqa: E402
from test_battle_end_rules import wait_until  # noqa: E402

PORT = "47611"
TANK, SHELLS, SKYR = "STR_TANK_CANNON", "STR_HWP_CANNON_SHELLS", "STR_SKYRANGER"
SHELLS_GIVEN = 30         # one STR_TANK_CANNON load takes 30 (on four boots)
CLIPS = 30                # the view's shells taken by the partner's load
TANK_AMMO = 30            # the parked tank's vehicleAmmo
TANK_SIZE = 4             # the 2x2 tank's SPACE USED on the view craft (1 -> 5)
GUEST = "Guest Zzz"
STEP_S = 30
GT_LOG = "[coop-guest-tank]"
ROWS = (("parked_tank_enters",
         ("parked_on_craft", "partner_sent", "host_stored", "tank_unit", "tank_tag", "tank_seat", "host_craft_empty",
          "host_stores_kept", "enters_common")),
        ("host_commands_tank", ("host_selects", "partner_refused", "commands_common")))

units, es = G3F.units, G3F.es


# ===================== shared with test_tank_gate / _return / _lost =====================


def log_lines(gc):
    return G3F.log_lines(gc)


def capture(tag, err, machines):
    """ONE CAPTURE line: each machine's stack, battle_state side / turn / units, event_state phase / guestContrib /
    battleEnd, coop_dialog_info and the last 40 engine log lines."""
    cap = {}
    for gc in machines:
        d = {}
        for k, fn in (("stack", session.states_stripped),
                      ("battle", lambda g: {kk: battle_state(g).get(kk) for kk in ("inBattle", "side", "turn")}),
                      ("units", lambda g: unit_view(g)),
                      ("event", lambda g: {kk: event_state(g).get(kk) for kk in ("phase", "guestContrib", "battleEnd")}),
                      ("dialog", lambda g: g.cmd({"cmd": "coop_dialog_info"})),
                      ("logTail", lambda g: log_lines(g)[-40:])):
            try:
                d[k] = fn(gc)
            except Exception as e:
                d[k] = f"probe failed: {type(e).__name__}: {e}"
        cap[gc.name] = d
    print(f"CAPTURE {tag}: missed {err}; {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def guarded(tag, fn, machines):
    try:
        return fn()
    except Exception as e:
        capture(tag, f"{type(e).__name__}: {str(e)[:600]}", machines)
        raise G3F.Miss(tag)


def unit_view(gc):
    """The player-side units {id, type, coop, soldierId, guestTank, name} (guestTank absent = "")."""
    return [{"id": u.get("id"), "type": u.get("type"), "coop": u.get("coop"), "soldierId": u.get("soldierId"),
             "guestTank": u.get("guestTank", ""), "name": u.get("name")}
            for u in battle_state(gc).get("units", []) if u.get("faction") == 0]


def tanks(gc):
    return sorted(u["id"] for u in battle_state(gc).get("units", []) if u.get("type") == TANK)


def storage(gc, coop=False):
    r = gc.cmd({"cmd": "base_report", "coop": True} if coop else {"cmd": "base_report"})
    s = r.get("storage") or {}
    return {TANK: s.get(TANK, 0), SHELLS: s.get(SHELLS, 0)}, r


def craft_vehicles(gc, cid):
    r = gc.cmd({"cmd": "base_screen_op", "op": "craft_vehicles", "craft_id": cid})
    return {k: r.get(k) for k in ("vehicles", "vehicleCoop", "vehicleAmmo", "error")}


def guest_contrib(gc):
    g = event_state(gc).get("guestContrib")
    return g if isinstance(g, dict) else {}


def view_space_used(gc, cid):
    """The visited craft's REAL CraftEquipmentState SPACE USED (Craft::getSpaceUsed, which counts its vehicles)."""
    gc.ok({"cmd": "open_craft_equipment", "coop": True, "craft_id": cid})
    w = gc.cmd({"cmd": "list_widgets"})
    gc.ok({"cmd": "craft_equipment_ok"})
    for x in w.get("widgets") or []:
        m = re.search(r"SPACE USED\D*(\d+)\s*$", x.get("text") or "")
        if m:
            return int(m.group(1))
    return None


def parked_cell(client, pins, label):
    """The partner's own Skyranger holds exactly the parked tank, tagged [HOST_BASE_COOP, HOST_SKY, STR_SKYRANGER]."""
    cv = craft_vehicles(client, pins["CLIENT_SKY"])
    want = {"vehicles": {TANK: 1}, "vehicleCoop": [[pins["HOST_BASE_COOP"], pins["HOST_SKY"], SKYR]], "vehicleAmmo": [TANK_AMMO]}
    got = {k: cv.get(k) for k in want}
    return got == want, f"{label} craft_vehicles {pins['CLIENT_SKY']} {got} (want {want})"


def bring_up_tank_battle(host, client, port, host_soldiers=3, host_tank_on_craft=False, pre_mission=None):
    """session.bring_up_separate_guest_battle's body with the module docstring's steps (i)-(iii); returns the setup
    values.
    Every assert is a construction step (the caller wraps it in guarded(): one CAPTURE line, the rows fail "boot")."""
    host.spawn(); client.spawn(); host.connect(); client.connect()
    session.new_campaign(host, client, port=port)
    hb = session._campaign_own_roster_base(host)
    host_base_name = hb["name"]
    cid = session._campaign_skyranger(host)["id"]
    rh = sorted(s["id"] for s in hb["soldiers"])
    for sid in rh:
        host.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False})
    host_squad = rh[:host_soldiers]
    for sid in host_squad:
        r = host.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})
        assert r.get("seated"), f"host soldier {sid} not seated: {r}"
    # (i) the host's tank(s) and shells, before the partner's visit (the visit copies the host's world)
    hbc = host.ok({"cmd": "base_report"}).get("coopBaseId")
    n_tanks = 1 if host_tank_on_craft else 2
    g = [host.ok({"cmd": "give_items", "item": it, "count": n}).get("stored")
         for it, n in ((TANK, n_tanks), (SHELLS, SHELLS_GIVEN))]
    assert g == [n_tanks, SHELLS_GIVEN], f"host give_items stored {g} (want {[n_tanks, SHELLS_GIVEN]})"
    if host_tank_on_craft:
        eq = host.cmd({"cmd": "craft_equip", "craft_id": cid, "item": TANK, "count": 1})
        cv = craft_vehicles(host, cid)
        assert eq.get("moved") is True and cv.get("vehicles") == {TANK: 1}, f"host craft_equip {eq}; its craft list {cv}"
    cb = session._campaign_own_roster_base(client)
    spare = next(s for s in cb["soldiers"] if not s.get("craft"))["name"]
    client.ok({"cmd": "rename_soldier", "name": spare, "newName": GUEST})
    tr = client.ok({"cmd": "transfer_to_coop_base", "name": "Guest", "toBase": host_base_name})
    assert tr.get("transferred"), f"guest transfer failed: {tr}"
    session.wait_peer_base_shown(client, host_base_name)
    client.ok({"cmd": "visit_coop_base", "base": host_base_name})
    client.wait_for("client inside host base", lambda: client.cmd({"cmd": "get_coop"}).get("insideCoopBase") or None, timeout=60)
    rep = client.wait_for("guest visible at host base", lambda: (lambda r: r if any(
        "Guest" in s["name"] for s in r["soldiers"]) else None)(client.ok({"cmd": "base_report", "coop": True})), timeout=40)
    guest_id = next(s for s in rep["soldiers"] if "Guest" in s["name"])["id"]
    peer_craft = next(c for c in rep["crafts"] if "SKYRANGER" in c["type"])["id"]
    client.ok({"cmd": "craft_assign", "soldier_id": guest_id, "craft_id": peer_craft, "coop": True, "on": True})
    # (ii) the partner parks one tank on the host's Skyranger in the visited base (the load is asserted)
    v0, used0 = storage(client, coop=True)[0], view_space_used(client, peer_craft)
    ce = client.cmd({"cmd": "craft_equip", "base": host_base_name, "craft_id": peer_craft, "item": TANK, "count": 1})
    v1, used1 = storage(client, coop=True)[0], view_space_used(client, peer_craft)
    assert (ce.get("moved") is True and v1 == {TANK: v0[TANK] - 1, SHELLS: v0[SHELLS] - CLIPS}
            and used0 is not None and used1 == used0 + TANK_SIZE), \
        f"the partner's load: craft_equip {ce}; view stores {v0} -> {v1} (want tank -1, shells -{CLIPS}); view SPACE USED " \
        f"{used0} -> {used1} (want +{TANK_SIZE})"
    client.ok({"cmd": "open_soldiers", "base": host_base_name})
    client.wait_for("client soldiers screen", lambda: session.has_state(client, "SoldiersState") or None, timeout=30)
    client.ok({"cmd": "soldiers_ok"})
    client.ok({"cmd": "leave_base"})
    session.wait_back_on_geoscape(client, "client back on geoscape")
    pins = {"host_squad": host_squad, "guest_id": guest_id, "HOST_BASE_COOP": hbc, "HOST_SKY": cid,
            "CLIENT_SKY": session._campaign_skyranger(client)["id"], "host_base_name": host_base_name, "peer_craft": peer_craft,
            "viewStores": [v0, v1], "viewSpaceUsed": [used0, used1]}
    print(f"squad assembled: host soldiers {host_squad} + guest {guest_id}; partner tank parked; setup values {pins}",
          flush=True)
    # (iii)
    if pre_mission is not None:
        pre_mission(host, client, pins)
    session.drain_host_coop_notice(host)
    b0 = session._campaign_base0(host)
    site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION",
                    "lon": b0["lon"] + 0.35, "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})
    site_id = site["site_id"]
    host.wait_for("site on host", lambda: any(s["id"] == site_id for s in host.ok({"cmd": "geo_state"})["missionSites"]) or None,
                  timeout=30)
    host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT", "lon": b0["lon"] + 0.34, "lat": b0["lat"] + 0.10,
             "dest": f"site:{site_id}", "fuel": 999999, "lowFuel": False})

    def landing_prompt():
        if session.has_state(host, "ConfirmLandingState"):
            return True
        top = session.states(host)[-1]
        if "CoopState" in top:
            host.cmd({"cmd": "coop_dialog_back"})
        elif "GeoscapeState" not in top:
            host.cmd({"cmd": "dismiss_popup"})
        host.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None

    host.wait_for("host landing prompt", landing_prompt, timeout=120, interval=0.5)
    host.ok({"cmd": "coop_mission_start"})
    host.wait_for("host entered", lambda: battle_state(host).get("inBattle") or None, timeout=120, interval=1.0)
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=60, interval=0.5)
    assert session.drive_both_to_tactical(host, client), \
        f"drive_both_to_tactical timed out (host={session.states(host)[-3:]} client={session.states(client)[-3:]})"
    print("both machines reached the battlescape (SEPARATE, the partner's tank parked)", flush=True)
    return pins


def census_wait(host, client, ev):
    """Bounded (STEP_S): the partner's vehSent 1 AND the host's vehicles[1] 1 (one wait for both cells)."""
    ok, ev["censusS"] = wait_until(lambda: guest_contrib(client).get("vehSent") == 1
                                   and (guest_contrib(host).get("vehicles") or [0, 0])[1:2] == [1], STEP_S, 0.25)
    ev["guestContrib"] = {"host": guest_contrib(host), "partner": guest_contrib(client)}
    sent, stored = ev["guestContrib"]["partner"].get("vehSent"), (ev["guestContrib"]["host"].get("vehicles") or [None, None])
    return ((sent == 1, f"the partner's guestContrib.vehSent {sent!r} (want 1 within {STEP_S} s; {ev['censusS']} s)"),
            (len(stored) > 1 and stored[1] == 1,
             f"the host's guestContrib.vehicles {stored!r} (want [*, 1, ...] within {STEP_S} s; {ev['censusS']} s)"))


def boot_common(host, client, crash0):
    return G3F.common(host, client, crash0)


# ===================== the boot =====================


def pre_tank_entry(out):
    def pre(host, client, pins):
        ev, cells = out.setdefault("ev", {}), out.setdefault("cells", {})
        try:
            p_ok, p_txt = parked_cell(client, pins, "the partner's")
            st = storage(host)[0]
            cells["parked_on_craft"] = (p_ok and st == {TANK: 2, SHELLS: SHELLS_GIVEN},
                                f"{p_txt}; host storage {st} (want {{{TANK}: 2, {SHELLS}: {SHELLS_GIVEN}}})")
        except Exception as e:
            cells["parked_on_craft"] = (False, f"probe failed: {type(e).__name__}: {str(e)[:300]}")
        try:
            cells["partner_sent"], cells["host_stored"] = census_wait(host, client, ev)
        except Exception as e:
            cells["partner_sent"] = cells["host_stored"] = (False, f"probe failed: {type(e).__name__}: {str(e)[:300]}")
    return pre


def row_parked_tank_enters(host, client, pins, pre, crash0, out):
    cells, ev = dict(pre.get("cells") or {}), dict(pre.get("ev") or {})
    tag = "coop-guest-tank:1:%d:%d:%s" % (pins["HOST_BASE_COOP"], pins["HOST_SKY"], SKYR)
    ev.update(tag=tag, pins={k: pins[k] for k in ("HOST_BASE_COOP", "HOST_SKY", "CLIENT_SKY", "guest_id", "viewStores",
                                                   "viewSpaceUsed")},
              units={"host": unit_view(host), "partner": unit_view(client)},
              hostLog=[ln for ln in log_lines(host) if GT_LOG in ln][-8:])
    th, tc = tanks(host), tanks(client)
    uh, uc = units(host), units(client)
    tv = [{k: (g.get(t[0]) or {}).get(k) for k in ("faction", "soldierId")} if len(t) == 1 else None
          for g, t in ((uh, th), (uc, tc))]
    ok = len(th) == 1 and th == tc and tv == [{"faction": 0, "soldierId": -1}] * 2
    cells["tank_unit"] = (ok, f"{TANK} units host/partner {th}/{tc} (want exactly one, the same id); faction / "
                              f"soldierId host/partner {tv} (want 0 / -1)")
    if ok:
        T = th[0]
        out["T"] = T
        gt = [(g.get(T) or {}).get("guestTank", "") for g in (uh, uc)]
        cells["tank_tag"] = (gt == [tag, tag], f"unit {T} guestTank host/partner {gt} (want {tag!r} on both)")
        cells["tank_seat"] = OWN.both_fields(host, client, T, "coop", 0)
    else:
        OWN.not_reached(cells, ("tank_tag", "tank_seat"), "tank_unit failed")
    cv = craft_vehicles(host, pins["HOST_SKY"])
    cells["host_craft_empty"] = (cv.get("error") is None and TANK not in (cv.get("vehicles") or {}),
                         f"host craft_vehicles {pins['HOST_SKY']} in the battle {cv} (want no {TANK})")
    st = storage(host)[0]
    cells["host_stores_kept"] = (st == {TANK: 2, SHELLS: SHELLS_GIVEN},
                          f"host storage in the battle {st} (want {{{TANK}: 2, {SHELLS}: {SHELLS_GIVEN}}})")
    cells["enters_common"] = boot_common(host, client, crash0)
    return cells, ev


def row_host_commands_tank(host, client, crash0, out):
    cells, ev = {}, {"T": out.get("T")}
    T = out.get("T")
    if T is None:
        OWN.not_reached(cells, ("host_selects", "partner_refused"), "tank_unit failed: no partner tank unit")
    else:
        ev["tab"] = tab_select(host, T)
        cells["host_selects"] = (ev["tab"], f"tab_select(host, {T}) {ev['tab']}, selectedId "
                                            f"{battle_state(host).get('selectedId')} (want {T})")
        d0 = [(units(gc).get(T) or {}).get("direction") for gc in (host, client)]
        to = ((d0[0] or 0) + 1) % 8
        tev = OWN.partner_turn(host, client, T, to, ev.setdefault("turn", {"toDir": to, "dir0": d0}))
        d_ok, d_txt = OWN.deny_cell(tev, T)
        cells["partner_refused"] = (d_ok and tev["dirs"] == d0,
                                    f"{d_txt}; directions before {d0} (want unchanged on both)")
    cells["commands_common"] = boot_common(host, client, crash0)
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("tank_entry_host"))
    client = GameClient("client", None, make_user_dir("tank_entry_client"))
    rows, fails, pre = dict(ROWS), 0, {}
    try:
        try:
            crash0 = session._crash_log_snapshot()
            pins = guarded("tank_battle",
                           lambda: bring_up_tank_battle(host, client, PORT, pre_mission=pre_tank_entry(pre)),
                           (host, client))
            guarded("tank_battle", lambda: session.pin_ai_neutral(host, client, tag="tank_entry"), (host, client))
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE tank_battle line)")
        else:
            out = {}
            fails += G3F.run_row("parked_tank_enters", rows["parked_tank_enters"],
                                 lambda: row_parked_tank_enters(host, client, pins, pre, crash0, out))
            fails += G3F.run_row("host_commands_tank", rows["host_commands_tank"],
                                 lambda: row_host_commands_tank(host, client, crash0, out))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_tank_entry: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
