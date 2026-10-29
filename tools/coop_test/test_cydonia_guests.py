"""test_cydonia_guests.py: a SEPARATE partner's guest soldier seated on the host's Skyranger, and its tank parked
there, take part in both Cydonia stages as at every host-craft landing. coopEndTurnText after the partner's END TURN
press is EVIDENCE only.

Boot cydonia_guests (SEPARATE campaign, key 47632, dirs cydonia_guests_host / cydonia_guests_client): bring_up_cydonia =
test_tank_entry's bring_up_tank_battle (2 host soldiers, the host's 2 tanks + 30 shells in its stores, the partner's
guest "Guest Zzz" and one parked tank on the host's Skyranger) with the Cydonia launch in place of its landing:
open_cydonia on HOST_SKY, set_seed SEED_CYDONIA right before confirm_cydonia, both briefings and equip screens,
pin_ai_neutral, idle, hash clean. The guest is found by NAME and the tank by TYPE (the merge mints a fresh soldier id; a
merged tank shifts every alien id by one); HOST_BASE_COOP, the alien ids and the map fingerprint are read at run time.
TAG = "coop-guest-tank:1:<HOST_BASE_COOP>:<HOST_SKY>:STR_SKYRANGER".
  guest_fights  the guest fights at stage 1: -census (before the launch: the partner's census reaches the host, the
      tank parked), -entry, -unit (one "Guest Zzz" player soldier on both, the same id G), -seat (coop 1), -split
      (session.assert_control_split), -common.
  guest_control  the partner commands G, not the host's soldiers; the host cannot select G: -cmd
      (session.assert_seat_commands), -common.
  tank_fights  the parked tank fights host-commanded, its copy off the host's craft: -unit (one STR_TANK_CANNON
      unit T), -tag, -seat (coop 0), -craft (no tank on the host's craft), -stores (2 tanks / 30 shells), -common.
  stage2_carry  both carried into stage 2: kill-all, END TURN partner then host, the host's NextTurnState close:
      -tally (the host's tally after the partner's press: count 1, needed 2, ready [1]), -entry (the stage-2 entry,
      spine and records), -guest, -tank, -cmd (the partner walks G at stage 2), -common (+ the host alive, no new crash
      file).
A build without the fix fails guest_fights-unit, -seat, -split, guest_control-cmd, tank_fights-unit,
-tag, -seat, stage2_carry-tally, -guest, -tank, -cmd (11 of 20); every other cell passes.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure. A boot step
past its bound prints ONE CAPTURE line and fails every row "boot"; a cell whose precondition failed FAILs "not reached". Common
cell: every hash bucket EQUAL, desyncSeen false on both, no new crash file. run in the foreground to completion.
ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_cydonia_guests.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_tank_entry as DT  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_ownerless_units as OWN  # noqa: E402
import test_multistage_end as MSE  # noqa: E402
import test_multistage as MS1  # noqa: E402

PORT = "47632"
# set on the host right before confirm_cydonia (two measured boots: one stage-1 map, host == client)
SEED_CYDONIA = 1
HOST_SOLDIERS = 2         # the first two ids of the host's sorted roster ([1, 2] on two measured boots)
TANK, SHELLS, SKYR, GUEST = DT.TANK, DT.SHELLS, DT.SKYR, DT.GUEST
STEP_S = 30
TALLY_S = 20              # the partner's press -> the host's tally (0.05 s on two measured boots)
GT_LOG = DT.GT_LOG
ROWS = (("guest_fights", ("guest_fights-census", "guest_fights-entry", "guest_fights-unit", "guest_fights-seat",
                          "guest_fights-split", "guest_fights-common")),
        ("guest_control", ("guest_control-cmd", "guest_control-common")),
        ("tank_fights", ("tank_fights-unit", "tank_fights-tag", "tank_fights-seat", "tank_fights-craft",
                         "tank_fights-stores", "tank_fights-common")),
        ("stage2_carry", ("stage2_carry-tally", "stage2_carry-entry", "stage2_carry-guest", "stage2_carry-tank",
                          "stage2_carry-cmd", "stage2_carry-common")))

units, es = G3F.units, G3F.es


def short(e, n=600):
    return f"{type(e).__name__}: {str(e)[:n]}"


def safe(fn):
    """An EVIDENCE probe: its value, or the probe error (never fails a cell)."""
    try:
        return fn()
    except Exception as e:
        return f"probe failed: {short(e, 200)}"


def bview(gc):
    b = battle_state(gc)
    return {k: b.get(k) for k in ("phase", "turn", "side", "missionType", "mapFingerprint", "coopWaitText", "coopEndTurnText")}


def guest_rows(gc):
    """The host's geoscape soldiers named GUEST (owner, coop, coopBase, craftId)."""
    return [{k: s.get(k) for k in ("id", "owner", "coop", "coopBase", "craftId")}
            for b in gc.ok({"cmd": "get_soldiers"})["bases"] for s in b["soldiers"] if s.get("name") == GUEST]


def guest_units(gc):
    return [u for u in battle_state(gc).get("units", []) if u.get("isPlayerSoldier") and u.get("name") == GUEST]


def hostiles(gc):
    return sorted(u["id"] for u in battle_state(gc).get("units", []) if u.get("faction") == 1 and not u.get("isOut"))


def gt_lines(host, pins):
    return [ln.split("\t")[-1] for ln in G3F.log_lines(host)[pins.get("logMark", 0):] if GT_LOG in ln][-8:]


def bring_up_cydonia(host, client, port, pre_launch):
    """DT.bring_up_tank_battle :152-:202 (host_soldiers=2, host_tank_on_craft=False), then the Cydonia launch in place of
    DT :206-:233. Every assert is a construction step (the caller wraps it in DT.guarded: one CAPTURE line, the rows fail
    "boot"). Returns the pins."""
    host.spawn(); client.spawn(); host.connect(); client.connect()
    session.new_campaign(host, client, port=port)
    hb = session._campaign_own_roster_base(host)
    host_base_name = hb["name"]
    cid = session._campaign_skyranger(host)["id"]
    rh = sorted(s["id"] for s in hb["soldiers"])
    for sid in rh:
        host.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False})
    host_squad = rh[:HOST_SOLDIERS]
    for sid in host_squad:
        r = host.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})
        assert r.get("seated"), f"host soldier {sid} not seated: {r}"
    # the host's two tanks and 30 shells, before the partner's visit (the visit copies the host's world)
    hbc = host.ok({"cmd": "base_report"}).get("coopBaseId")
    g = [host.ok({"cmd": "give_items", "item": it, "count": n}).get("stored") for it, n in ((TANK, 2), (SHELLS, DT.SHELLS_GIVEN))]
    assert g == [2, DT.SHELLS_GIVEN], f"host give_items stored {g} (want {[2, DT.SHELLS_GIVEN]})"
    cb = session._campaign_own_roster_base(client)
    spare = next(s for s in cb["soldiers"] if not s.get("craft"))["name"]
    client.ok({"cmd": "rename_soldier", "name": spare, "newName": GUEST})
    tr = client.ok({"cmd": "transfer_to_coop_base", "name": "Guest", "toBase": host_base_name})
    assert tr.get("transferred"), f"guest transfer failed: {tr}"
    client.ok({"cmd": "visit_coop_base", "base": host_base_name})
    client.wait_for("client inside host base", lambda: client.cmd({"cmd": "get_coop"}).get("insideCoopBase") or None, timeout=60)
    rep = client.wait_for("guest visible at host base", lambda: (lambda r: r if any(
        "Guest" in s["name"] for s in r["soldiers"]) else None)(client.ok({"cmd": "base_report", "coop": True})), timeout=40)
    guest_id = next(s for s in rep["soldiers"] if "Guest" in s["name"])["id"]
    peer_craft = next(c for c in rep["crafts"] if "SKYRANGER" in c["type"])["id"]
    client.ok({"cmd": "craft_assign", "soldier_id": guest_id, "craft_id": peer_craft, "coop": True, "on": True})
    # the partner parks one tank on the host's Skyranger in the visited base (the load asserted, DT :187-:193)
    v0, used0 = DT.storage(client, coop=True)[0], DT.view_space_used(client, peer_craft)
    ce = client.cmd({"cmd": "craft_equip", "base": host_base_name, "craft_id": peer_craft, "item": TANK, "count": 1})
    v1, used1 = DT.storage(client, coop=True)[0], DT.view_space_used(client, peer_craft)
    assert (ce.get("moved") is True and v1 == {TANK: v0[TANK] - 1, SHELLS: v0[SHELLS] - DT.CLIPS}
            and used0 is not None and used1 == used0 + DT.TANK_SIZE), \
        f"the partner's load: craft_equip {ce}; view stores {v0} -> {v1} (want tank -1, shells -{DT.CLIPS}); view SPACE USED " \
        f"{used0} -> {used1} (want +{DT.TANK_SIZE})"
    client.ok({"cmd": "open_soldiers", "base": host_base_name})
    client.wait_for("client soldiers screen", lambda: session.has_state(client, "SoldiersState") or None, timeout=30)
    client.ok({"cmd": "soldiers_ok"})
    client.ok({"cmd": "leave_base"})
    session.wait_back_on_geoscape(client, "client back on geoscape")
    pins = {"host_squad": host_squad, "guest_view_id": guest_id, "HOST_BASE_COOP": hbc, "HOST_SKY": cid,
            "CLIENT_SKY": session._campaign_skyranger(client)["id"], "peer_craft": peer_craft, "viewStores": [v0, v1],
            "viewSpaceUsed": [used0, used1], "SEED_CYDONIA": SEED_CYDONIA}
    print(f"squad assembled: host soldiers {host_squad} + guest (view id {guest_id}); partner tank parked; pins {pins}", flush=True)
    pre_launch(host, client, pins)
    # the Cydonia launch (the host's own Skyranger)
    session.drain_host_coop_notice(host)
    host.ok({"cmd": "open_cydonia", "craft_id": cid})
    host.wait_for("Cydonia confirmation", lambda: session.has_state(host, "ConfirmCydoniaState") or None, timeout=STEP_S)
    host.ok({"cmd": "set_seed", "seed": SEED_CYDONIA})
    pins["logMark"] = len(G3F.log_lines(host))
    host.ok({"cmd": "confirm_cydonia"})
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=60)
    pins["pressed1"], pins["spine1S"] = MS1.run_spine(host, client)   # session.briefings_to_battlescape
    live = hostiles(host)
    pinned = sorted(session.pin_ai_neutral(host, client, tag="cydonia_guests"))
    assert pinned == live, f"pin_ai_neutral pinned {pinned} (want every live hostile id {live})"
    session.wait_host_idle(host, client, timeout=MS1.IDLE_S)
    session.assert_hash_clean(host, client, full=True, what="cydonia_guests bring-up")
    pins["hostiles"] = live
    print("both machines on the Cydonia battlescape (SEPARATE, the partner's guest seated and tank parked)", flush=True)
    return pins


def pre_guest_fights(out):
    """guest_fights-census, before open_cydonia (precondition; the census exists without the fix too)."""
    def pre(host, client, pins):
        ev, cells = out.setdefault("ev", {}), out.setdefault("cells", {})
        try:
            c_sent, c_store = DT.census_wait(host, client, ev)
            gh, gp = DT.guest_contrib(host), DT.guest_contrib(client)
            hs = gh.get("soldiers") or []
            p_ok, p_txt = DT.parked_cell(client, pins, "the partner's")
            s_ok = (gp.get("sent") or 0) >= 1 and len(hs) > 1 and (hs[1] or 0) >= 1
            cells["guest_fights-census"] = (c_sent[0] and c_store[0] and s_ok and p_ok,
                                  f"{c_sent[1]}; {c_store[1]}; the partner's guestContrib.sent {gp.get('sent')!r} (want >= 1); "
                                  f"the host's guestContrib.soldiers {hs!r} (want [*, >= 1, ...]); {p_txt}")
        except Exception as e:
            cells["guest_fights-census"] = (False, f"probe failed: {short(e, 300)}")
        try:
            ev["hostGuestRowsBeforeLaunch"] = guest_rows(host)
        except Exception as e:
            ev["hostGuestRowsBeforeLaunch"] = f"probe failed: {short(e, 200)}"
    return pre


def row_guest_fights(host, client, pins, pre, crash0, out):
    cells, ev = dict(pre.get("cells") or {}), dict(pre.get("ev") or {})
    hb, cb = bview(host), bview(client)
    fps = [hb.get("mapFingerprint"), cb.get("mapFingerprint")]
    want = ("Active", 1, 0, MSE.MISSION_LANDING)
    got = [(b.get("phase"), b.get("turn"), b.get("side"), b.get("missionType")) for b in (hb, cb)]
    cells["guest_fights-entry"] = (got == [want, want] and fps[0] is not None and fps[0] == fps[1],
                         f"(phase, turn, side, missionType) host/partner {got} (want {want} on both); mapFingerprint "
                         f"host/partner {fps} (want equal, non-null)")
    gu = [guest_units(gc) for gc in (host, client)]
    gv = [[(u.get("id"), u.get("faction"), u.get("isOut")) for u in x] for x in gu]
    ok = (all(len(x) == 1 for x in gu) and gu[0][0]["id"] == gu[1][0]["id"]
          and all(x[0].get("faction") == 0 and not x[0].get("isOut") for x in gu))
    cells["guest_fights-unit"] = (ok, f"isPlayerSoldier units named {GUEST!r} (id, faction, isOut) host/partner {gv} "
                                      f"(want exactly one on each, the same id, faction 0, not out)")
    if ok:
        G = out["G"] = gu[0][0]["id"]
        cells["guest_fights-seat"] = OWN.both_fields(host, client, G, "coop", 1)
        want_seats = {**{s: 0 for s in pins["host_squad"]}, G: 1}
        try:
            session.assert_control_split(host, client, want_seats, what="cydonia_guests guest_fights")
            cells["guest_fights-split"] = (True, f"control split: the isPlayerSoldier roster {want_seats} (soldierId: "
                                                 f"seat) on both, phase Active, authority, battleId equal, hash clean, "
                                                 f"battle_ready saveBlob EQUAL")
        except Exception as e:
            cells["guest_fights-split"] = (False, short(e))
    else:
        OWN.not_reached(cells, ("guest_fights-seat", "guest_fights-split"), "guest_fights-unit failed: no guest unit")
    ev.update(pins={k: pins.get(k) for k in ("HOST_SKY", "host_squad", "HOST_BASE_COOP", "CLIENT_SKY", "SEED_CYDONIA",
                                             "guest_view_id", "viewStores", "viewSpaceUsed", "pressed1", "spine1S")},
              units={"host": safe(lambda: DT.unit_view(host)), "partner": safe(lambda: DT.unit_view(client))},
              hostGuestRows=safe(lambda: guest_rows(host)),
              hostLog=safe(lambda: gt_lines(host, pins)), hostiles=pins.get("hostiles"), fingerprints=fps,
              waitText={"host": hb.get("coopWaitText"), "partner": cb.get("coopWaitText")})
    cells["guest_fights-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_guest_control(host, client, pins, crash0, out):
    cells, G = {}, out.get("G")
    ev = {"G": G}
    if G is None:
        OWN.not_reached(cells, ("guest_control-cmd",), "guest_fights-unit failed: no guest unit")
    else:
        ev["before"] = {gc.name: G3F.pos(gc, G) for gc in (host, client)}
        try:
            session.assert_seat_commands(host, client, G, pins["host_squad"][0], host_check=True,
                                         what="cydonia_guests guest_control")
            cells["guest_control-cmd"] = (True, f"seat commands: the partner's walk on {G} admitted and equal on both, "
                                                f"hash clean; its walk on {pins['host_squad'][0]} denied "
                                                f"not_your_unit; the host's click on {G} refused")
        except Exception as e:
            cells["guest_control-cmd"] = (False, short(e))
        ev["after"] = {gc.name: G3F.pos(gc, G) for gc in (host, client)}
        ev["lastDeny"] = es(client, "lastDeny")
        ev["hostView"] = {k: v for k, v in bview(host).items() if k in ("coopWaitText", "turn")}
    cells["guest_control-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_tank_fights(host, client, pins, crash0, out):
    cells = {}
    tag = out["TAG"] = "coop-guest-tank:1:%d:%d:%s" % (pins["HOST_BASE_COOP"], pins["HOST_SKY"], SKYR)
    th, tc = DT.tanks(host), DT.tanks(client)
    uh, uc = units(host), units(client)
    tv = [{k: (g.get(t[0]) or {}).get(k) for k in ("faction", "soldierId")} if len(t) == 1 else None
          for g, t in ((uh, th), (uc, tc))]
    ok = len(th) == 1 and th == tc and tv == [{"faction": 0, "soldierId": -1}] * 2
    cells["tank_fights-unit"] = (ok, f"{TANK} units host/partner {th}/{tc} (want exactly one, the same id); "
                                     f"faction / soldierId host/partner {tv} (want 0 / -1)")
    if ok:
        T = out["T"] = th[0]
        gt = [(g.get(T) or {}).get("guestTank", "") for g in (uh, uc)]
        cells["tank_fights-tag"] = (gt == [tag, tag], f"unit {T} guestTank host/partner {gt} (want {tag!r} on both)")
        cells["tank_fights-seat"] = OWN.both_fields(host, client, T, "coop", 0)
    else:
        OWN.not_reached(cells, ("tank_fights-tag", "tank_fights-seat"), "tank_fights-unit failed: no partner tank unit")
    cv = DT.craft_vehicles(host, pins["HOST_SKY"])
    cells["tank_fights-craft"] = (cv.get("error") is None and TANK not in (cv.get("vehicles") or {}),
                         f"host craft_vehicles {pins['HOST_SKY']} in the battle {cv} (want no error, no {TANK})")
    st = DT.storage(host)[0]
    cells["tank_fights-stores"] = (st == {TANK: 2, SHELLS: DT.SHELLS_GIVEN},
                          f"host storage in the battle {st} (want {{{TANK}: 2, {SHELLS}: {DT.SHELLS_GIVEN}}})")
    ev = {"tag": tag, "T": out.get("T"), "hostLog": safe(lambda: gt_lines(host, pins)),
          "hostGuestRows": safe(lambda: guest_rows(host))}
    cells["tank_fights-common"] = G3F.common(host, client, crash0)
    return cells, ev


def end_turn_both(host, client, g, ctx):
    """MSE.close_end_turn :158-:175 with a changed wait: the partner presses END TURN; a bounded wait until the
    host's coopEndTurnTally.needed > 0 (the tally that press made the host emit: stage2_carry-tally's reading); the
    host presses; the host's NextTurnState (<= 30 s) closed by dismiss_popup. coopEndTurnText is EVIDENCE only."""
    et = ctx["endTurn"] = {}
    try:
        et["partnerPress"] = client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        et["tallyOk"], et["tallyS"] = MS1.wait_until(
            lambda: ((es(host, "coopEndTurnTally") or {}).get("needed") or 0) > 0, TALLY_S, 0.1)
        et["tally"] = es(host, "coopEndTurnTally")
        et["text"] = {gc.name: battle_state(gc).get("coopEndTurnText") for gc in (host, client)}
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    except Exception as e:
        g.append(f"END TURN presses: {short(e, 300)}")
    ok, secs = MS1.wait_until(lambda: "NextTurnState" in host.cmd({"cmd": "list_widgets"}).get("state", ""), 30, 0.1)
    if not ok:
        g.append(f"host NextTurnState not up within {secs}s after both END TURN presses")
    ctx["t_close"] = time.time()
    d = host.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") != "NextTurnState->close":
        g.append(f"host dismiss_popup answered {d} (want handled NextTurnState->close)")
    return et


def unit_cell(host, client, uid, what, want):
    """`uid` on both machines at stage 2, not out, each `want` field equal on both."""
    got = [{k: (units(gc).get(uid) or {}).get(k) for k in ("isOut", *want)} if uid in units(gc) else None
           for gc in (host, client)]
    w = {"isOut": False, **want}
    return got == [w, w], f"{what} {uid} at stage 2 host/partner {got} (want {w} on both)"


def row_stage2_carry(host, client, pins, crash0, out):
    cells, ctx, g = {}, {}, []
    G, T, tag = out.get("G"), out.get("T"), out.get("TAG")
    MSE.stage_guards(host, client, ctx, g)
    ctx["killed"] = MSE.kill_all(host, client, None, g, "stage 1")
    et = end_turn_both(host, client, g, ctx)
    ctx["hostStageAtClose"] = MS1.eview(host).get("stage")
    ctx["hostRcAtClose"] = MS1.rc(host)
    tally = et.get("tally") or {}
    t_got = (tally.get("count"), tally.get("needed"), tally.get("ready"))
    cells["stage2_carry-tally"] = (t_got == (1, 2, [1]),
                         f"the host's coopEndTurnTally after the partner's press {tally} (want count 1, needed 2, ready [1]; "
                         f"waited {et.get('tallyS')} s, needed > 0 seen: {et.get('tallyOk')})")
    ev = {"b1": ctx.get("b1"), "killed": ctx.get("killed"), "endTurn": et, "hostStageAtClose": ctx["hostStageAtClose"],
          "hostRcAtClose": ctx["hostRcAtClose"]}
    if g:
        for n in ("stage2_carry-entry", "stage2_carry-guest", "stage2_carry-tank", "stage2_carry-cmd",
                  "stage2_carry-common"):
            cells[n] = (False, "pre-stage: " + " | ".join(g)[:800])
        ev["guards"] = g
        return cells, ev
    f = MSE.entry_cells(host, client, ctx, MSE.MISSION_FINAL)
    if not f:
        ctx["inStage2"] = True
        try:
            ctx["pressed2"], ctx["spineS"] = MS1.run_spine(host, client)
            for name, gc in (("host", host), ("partner", client)):
                b = MSE.bview(gc)
                if b.get("turn") != 1 or b.get("missionType") != MSE.MISSION_FINAL:
                    f.append(f"{name} turn/missionType={b.get('turn')}/{b.get('missionType')} (want 1/{MSE.MISSION_FINAL})")
            MSE.record_cells(host, client, ctx, f, {})
        except Exception as e:
            f.append(f"stage-2 spine / cells: {short(e)}")
    cells["stage2_carry-entry"] = (not f, " | ".join(f)[:900] if f else
                         f"the partner's stage-2 briefing {ctx.get('clientBriefingS')} s after the close, missionType "
                         f"{MSE.MISSION_FINAL}, applied 1 / emitted 1; both turn 1 on it; record_cells no failure")
    if f:
        OWN.not_reached(cells, ("stage2_carry-guest", "stage2_carry-tank", "stage2_carry-cmd"),
                        "stage2_carry-entry failed: no stage 2")
    else:
        if G is None:
            OWN.not_reached(cells, ("stage2_carry-guest", "stage2_carry-cmd"),
                            "guest_fights-unit failed: no guest unit")
        else:
            cells["stage2_carry-guest"] = unit_cell(host, client, G, "guest", {"coop": 1})
            try:
                session.assert_seat_commands(host, client, G, None, host_check=False,
                                             what="cydonia_guests stage2_carry")
                cells["stage2_carry-cmd"] = (True, f"seat commands at stage 2: the partner's walk on {G} admitted, "
                                                   f"equal on both, hash clean")
            except Exception as e:
                cells["stage2_carry-cmd"] = (False, short(e))
        if T is None:
            OWN.not_reached(cells, ("stage2_carry-tank",), "tank_fights-unit failed: no partner tank unit")
        else:
            cells["stage2_carry-tank"] = unit_cell(host, client, T, "tank", {"coop": 0, "guestTank": tag})
    lf = []
    MSE.liveness_cells(host, ctx, crash0, lf)
    c_ok, c_txt = G3F.common(host, client, crash0)
    cells["stage2_carry-common"] = (c_ok and not lf, f"{c_txt}; liveness {lf or 'host alive, no new crash file'}")
    ev.update(entry=ctx.get("entry"), clientBriefingS=ctx.get("clientBriefingS"), pressed2=ctx.get("pressed2"),
              spineS=ctx.get("spineS"), stacks={"host": MS1.stack(host), "partner": MS1.stack(client)},
              carried={"host": safe(lambda: DT.unit_view(host)), "partner": safe(lambda: DT.unit_view(client))},
              hostRc=MS1.rc(host),
              newCrashFiles=ctx.get("newCrashFiles"))
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("cydonia_guests_host"))
    client = GameClient("client", None, make_user_dir("cydonia_guests_client"))
    rows, fails, pre, out = dict(ROWS), 0, {}, {}
    try:
        try:
            crash0 = session._crash_log_snapshot()
            pins = DT.guarded("cydonia_guests", lambda: bring_up_cydonia(host, client, PORT, pre_guest_fights(pre)),
                              (host, client))
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE cydonia_guests line)")
        else:
            fails += G3F.run_row("guest_fights", rows["guest_fights"],
                                 lambda: row_guest_fights(host, client, pins, pre, crash0, out))
            fails += G3F.run_row("guest_control", rows["guest_control"],
                                 lambda: row_guest_control(host, client, pins, crash0, out))
            fails += G3F.run_row("tank_fights", rows["tank_fights"],
                                 lambda: row_tank_fights(host, client, pins, crash0, out))
            fails += G3F.run_row("stage2_carry", rows["stage2_carry"],
                                 lambda: row_stage2_carry(host, client, pins, crash0, out))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_cydonia_guests: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
