"""test_campaign_second_battle_separate.py: in a SEPARATE campaign the loot, score and funds of a
battle land in the HOST's world, and the same session plays a SECOND battle after the first return.

Both rows run the SEPARATE battle-end flow, so a failing row is a defect in that flow, not in this file; a failed
construction step prints a CAPTURE line.

One boot (port 47267), two rows on one SEPARATE session:

first_battle_loot (battle 1: the loot, score and funds go to the owner of the craft's base, here the host). Fixture =
test_battle_end_separate._stage_common (SEED_P, MAP_FP_P, the guest's own kill of the last alien, the MARKER on the
client's funds) with its `pre_extra` hook (called inside its pre_mission_start, after the MARKER) snapshotting BEFORE
the battle: the client's base storage (base_report), funds and month_report.score; the host's month_report.score and
base storage. Once the host debriefs (still pre-cell): the types the host's debriefing recovers = screen_rows
{recovered: <every type in the host's base storage>} > 0 (the topmost DebriefingState's getRecoveredItemCount),
cross-checked against debrief_state's recovered list (same row count and quantity sum; a mismatch is a setup failure).
  battle1_returns       the client's display-only debriefing (equal to the host's with page-2 names prefix-stripped),
      the client's OK through its follow-up screens (test_battle_end_separate's client_ok_through_followups) to a
      clean GeoscapeState, then the host's OK + drain to its GeoscapeState; the guest's own record after battle 1 is
      kept for second_battle.
  host_stock_recovered  the host's base stock of each recovered type == before + its debriefing's qty.
  host_score_delta      the host's month_report.score - before == the host debriefing's total + SCORE_EXTRA (0 in
      two runs: the delta is the debriefing's total).
  client_world_kept     the client's funds == MARKER, its base storage == before (every type); its
      month_report.score == the host's (in SEPARATE the client's GeoscapeState init asks the host for its graphs and
      adopts its region/country activity).

second_battle (battle 2). Fixture = this file's separate_battle_again(): the client visits the host's base
(visit_coop_base, base_report {coop} finds the guest), seats the guest on the host's craft (craft_assign {coop, on}),
open_soldiers / soldiers_ok, leave_base; then bring_up_separate_guest_battle's tail: the items-received drain, a fresh
terror site, craft_force, the landing prompt, host set_seed SEED_P, coop_mission_start, drive_both_to_tactical (the
guest's battle unit present); the ending = kill_unit_real {faction: 1} (every live hostile), the host's chain settled,
END TURN both, the host's NextTurnState closed, its debriefing. A construction failure is a setup failure (one CAPTURE
line, the row FAILs "pre-cell").
  battle2_debriefs       both debriefings equal after the page-2 name prefixes are stripped, the client's
      display-only.
  battle2_client_return  the client's OK through its follow-ups -> its own world: no LoadGameState pushed since the
      kill; battleEnd.sepReturn {ownLoaded 1, guestsApplied 1, guestsMissing 0, pushed 1} for battle 2 (the record
      reset at initBattleAuthority); the guest's missions == its missions after battle 1 + 1.
  battle2_host_return    the host's OK + drain to its GeoscapeState; event_state.phase Idle on both; host
      fatalVote.armed 0; the client zero-disk.
second_battle runs only when first_battle_loot's battle1_returns cell passed; otherwise it is reported "not reached".
Guard over each row: no new crash log. Each row prints ONE "EVIDENCE <id>:" line (both machines' battleEnd records
and sel_state, the per-battle walls), then "PASS <id>" or "FAIL <id>: <message>". ONE foreground run,
no skip path; exit 0 only when both rows pass, 2 otherwise.

Run:  python tools/coop_test/test_campaign_second_battle_separate.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import battle_state, event_state
from harness import GameClient, make_user_dir
import test_battle_end_separate as BES

PORT = "47267"                     # this file's lobby port (test_campaign_second_battle uses 47266)
TAG = "campaign_second_battle_separate"
SCORE_EXTRA = 0                    # host score delta minus its debriefing's total; the same in two runs
DEBRIEF_S = BES.DEBRIEF_S          # 60 s: the host's DebriefingState after the ending
DRAIN_S = BES.DRAIN_S              # 60 s
WANT_SEP = {"ownLoaded": 1, "guestsApplied": 1, "guestsMissing": 0, "pushed": 1}
RECORD_KEYS = ("debriefOkBranch", "debriefDisplayOnly", "sepReturn", "sepSnapshot", "memorialRemoved", "chain",
               "page3", "worldAdoptDeferredPasses", "forced", "adoptFailed")

SESSION = {}                       # battle 1's ctx, read by battle 2 (one session, two rows)


def short(e, n=400):
    return BES.short(e, n)


def stack(gc):
    return BES.stack(gc)


def top(gc):
    return BES.top(gc)


def record(gc):
    return BES.record(gc)


def rec_keys(gc):
    r = record(gc)
    return {k: r.get(k) for k in RECORD_KEYS}


def sel_state(gc):
    r = gc.cmd({"cmd": "sel_state"})
    return {k: r.get(k) for k in ("ok", "localSeat", "keys", "error")}


def storage(gc):
    """This machine's own base storage {type: qty} (base_report's default selector: the local own base)."""
    r = gc.cmd({"cmd": "base_report"})
    return r.get("storage") if isinstance(r.get("storage"), dict) else None


def score_funds(gc):
    r = gc.cmd({"cmd": "month_report"})
    return r.get("score"), r.get("funds")


def walls_mark(ctx, key):
    ctx.setdefault("t", {})[key] = round(time.time() - SESSION["t0"], 1)


# ===================== first_battle_loot (battle 1) =====================


def battle1_snapshot(h, c, ctx):
    """The `pre_extra` hook of BES._stage_common (inside pre_mission_start, after the MARKER): the BEFORE snapshot on
    both machines."""
    cs, cf = score_funds(c)
    hs, hf = score_funds(h)
    ctx["before"] = {"client": {"storage": storage(c), "funds": c.cmd({"cmd": "geo_state"}).get("funds"), "score": cs,
                                "monthFunds": cf},
                     "host": {"storage": storage(h), "score": hs, "funds": hf}}
    bad = [f"{n} snapshot {k} missing" for n, d in ctx["before"].items() for k in ("storage", "score")
           if d.get(k) is None]
    if bad:
        BES.capture("first_battle_loot snapshot", "; ".join(bad), (h, c))


def battle1_stage(rid, host, client, ctx):
    SESSION["battle1"] = ctx
    walls_mark(ctx, "battle1Start")
    BES._stage_common(rid, host, client, ctx, PORT, BES.guest_kill, BES._precheck_alive, pre_extra=battle1_snapshot)
    walls_mark(ctx, "battle1Debrief")
    # the types the host's debriefing recovers (pre-cell; a mismatch with the shown list is a setup failure)
    hst = storage(host) or {}
    rr = host.cmd({"cmd": "screen_rows", "recovered": sorted(hst.keys())})
    rec = rr.get("recovered") if isinstance(rr.get("recovered"), dict) else {}
    recovered = {t: q for t, q in rec.items() if isinstance(q, int) and q > 0}
    shown = [r for r in ((ctx.get("hostDebrief") or {}).get("recovered") or []) if isinstance(r, dict)]
    ctx["recovered"] = {"types": recovered, "shownRows": len(shown), "shownSum": sum(r.get("qty", 0) for r in shown),
                        "storageAtDebrief": hst}
    if not recovered or len(recovered) != len(shown) or sum(recovered.values()) != ctx["recovered"]["shownSum"]:
        BES.capture("first_battle_loot recovered types", f"probe {recovered} vs the shown list {shown}", (host, client))


def battle1_returns(host, client, ctx):
    """battle1_returns: the client's debriefing, its OK through its follow-ups, the host's OK + drain."""
    f = BES.cell_debriefs(host, client, ctx)
    if f:
        return f
    ok1, ok, secs = BES.client_ok_through_followups(client, ctx, "clientReturn")
    ctx["clientReturn"].update({"ok": ok1, "reached": ok, "secs": secs, "clientStack": stack(client)})
    if not ok1["pressed"]:
        return [ok1["note"]]
    if (ok1.get("resp") or {}).get("handled") != "DebriefingState":
        return [f"client OK answered {ok1.get('resp')} (want handled DebriefingState)"]
    if not ok:
        return [f"client not on a clean GeoscapeState within {BES.OK_S}s of its OK (stack {stack(client)})"]
    ctx["guestAfter1"] = BES.soldier_rec(client, sid=ctx["guestId"])
    ok2 = BES.press_ok(host)
    reached, screens = BES.drain(host) if ok2["pressed"] else (False, [])
    ctx["hostOk"] = {"ok": ok2, "reached": reached, "screens": screens, "hostStack": stack(host)}
    if not ok2["pressed"]:
        return [ok2["note"]]
    if not reached:
        return [f"host not on GeoscapeState within {DRAIN_S}s of its OK (stack {stack(host)}, screens {screens})"]
    ctx["battle1Returned"] = True
    walls_mark(ctx, "battle1End")
    return []


def battle1_host_stock(host, client, ctx):
    """host_stock_recovered: the host's stock of each recovered type == before + its debriefing's qty."""
    before = (ctx.get("before") or {}).get("host", {}).get("storage") or {}
    after = storage(host) or {}
    rec = (ctx.get("recovered") or {}).get("types") or {}
    ctx["hostStock"] = {t: {"before": before.get(t, 0), "qty": q, "after": after.get(t, 0)} for t, q in rec.items()}
    return [f"host stock of {t} = {after.get(t, 0)} (want before {before.get(t, 0)} + recovered {q})"
            for t, q in sorted(rec.items()) if after.get(t, 0) != before.get(t, 0) + q]


def battle1_host_score(host, client, ctx):
    """host_score_delta: the host's score - before == its debriefing's total + SCORE_EXTRA."""
    s0 = (ctx.get("before") or {}).get("host", {}).get("score")
    s1, _f = score_funds(host)
    total = (ctx.get("hostDebrief") or {}).get("total")
    ctx["hostScore"] = {"before": s0, "after": s1, "total": total,
                        "extra": (s1 - s0 - total) if all(isinstance(v, int) for v in (s0, s1, total)) else None,
                        "pinned": SCORE_EXTRA}
    if not all(isinstance(v, int) for v in (s0, s1, total)):
        return [f"host score inputs not numeric: {ctx['hostScore']}"]
    if s1 - s0 != total + SCORE_EXTRA:
        return [f"host month_report.score {s0} -> {s1} (delta {s1 - s0}; want the debriefing's total {total} + "
                f"SCORE_EXTRA {SCORE_EXTRA})"]
    return []


def battle1_client_world(host, client, ctx):
    """client_world_kept: the client's funds == MARKER, its base storage == before; its score == the host's (in
    SEPARATE the client adopts the host's monthly-score graphs)."""
    before = (ctx.get("before") or {}).get("client") or {}
    funds = client.cmd({"cmd": "geo_state"}).get("funds")
    st = storage(client)
    sc, _f = score_funds(client)
    hsc, _hf = score_funds(host)
    ctx["clientWorld"] = {"funds": funds, "marker": ctx.get("marker"), "score": sc, "scoreBefore": before.get("score"),
                          "hostScore": hsc,
                          "storageEqual": st == before.get("storage"),
                          "storageDiff": {t: (before.get("storage", {}).get(t), (st or {}).get(t))
                                          for t in set(before.get("storage") or {}) | set(st or {})
                                          if (before.get("storage") or {}).get(t) != (st or {}).get(t)}}
    f = []
    if funds != ctx.get("marker"):
        f.append(f"client geo_state.funds={funds!r} (want the MARKER {ctx.get('marker')!r}: the funds go to the "
                 f"host, whose craft flew)")
    if st != before.get("storage"):
        f.append(f"client base storage changed (type: (before, after)) = {ctx['clientWorld']['storageDiff']}")
    if not isinstance(sc, int) or sc != hsc:
        f.append(f"client month_report.score={sc!r} != the host's {hsc!r} (in SEPARATE the client adopts the "
                 f"host's monthly-score graphs)")
    ctx["battle1Records"] = {"host": rec_keys(host), "client": rec_keys(client)}
    ctx["battle1SelState"] = {"host": sel_state(host), "client": sel_state(client)}
    return f


def battle1_cells(host, client, ctx):
    return [
        ("battle1_returns (the client's OK through its follow-ups, the host's OK + drain)",
         lambda: battle1_returns(host, client, ctx)),
        ("host_stock_recovered (the host's stock of each recovered type == before + its debriefing's qty)",
         lambda: battle1_host_stock(host, client, ctx)),
        ("host_score_delta (the host's score delta == its debriefing's total + SCORE_EXTRA)",
         lambda: battle1_host_score(host, client, ctx)),
        ("client_world_kept (the client's funds == MARKER, its storage unchanged, its score == the host's)",
         lambda: battle1_client_world(host, client, ctx)),
    ]


# ===================== second_battle (battle 2) =====================


def separate_battle_again(host, client, ctx):
    """The second SEPARATE battle on the same session (bring_up_separate_guest_battle's guest seat and tail, without
    new_campaign). Raises FixtureMiss after a CAPTURE line."""
    m = (host, client)
    battle1 = SESSION["battle1"]
    con = ctx.setdefault("again", {})
    try:
        hb = session._campaign_own_roster_base(host)
        host_base_name = hb["name"]
        cid = session._campaign_skyranger(host)["id"]
        con["host"] = {"base": host_base_name, "craft": cid,
                       "aboard": sorted(s["id"] for s in hb["soldiers"] if s.get("craftId") == cid)}
        session.wait_peer_base_shown(client, host_base_name)
        client.ok({"cmd": "visit_coop_base", "base": host_base_name})
        client.wait_for("client inside host base",
                        lambda: client.cmd({"cmd": "get_coop"}).get("insideCoopBase") or None, timeout=60)
        rep = client.wait_for(
            "guest visible at host base",
            lambda: (lambda r: r if any("Guest" in s["name"] for s in r["soldiers"]) else None)(
                client.ok({"cmd": "base_report", "coop": True})), timeout=40)
        guest = next(s for s in rep["soldiers"] if "Guest" in s["name"])
        peer_craft = next(c for c in rep["crafts"] if "SKYRANGER" in c["type"])["id"]
        con["guest"] = {k: guest.get(k) for k in ("id", "name", "craft", "coopCraft", "coopBase", "owner")}
        con["peerCraft"] = peer_craft
        if guest.get("id") != battle1.get("guestId"):
            BES.capture("again: guest id",
                        f"coop base guest id {guest.get('id')} != battle 1's {battle1.get('guestId')}", m)
        r = client.cmd({"cmd": "craft_assign", "soldier_id": guest["id"], "craft_id": peer_craft, "coop": True,
                        "on": True})
        con["seat"] = {k: r.get(k) for k in ("ok", "seated", "craftId", "error")}
        if not (r.get("ok") and r.get("seated")):
            BES.capture("again: guest seat", f"craft_assign coop answered {con['seat']}", m)
        client.ok({"cmd": "open_soldiers", "base": host_base_name})
        client.wait_for("client soldiers screen", lambda: session.has_state(client, "SoldiersState") or None,
                        timeout=30)
        client.ok({"cmd": "soldiers_ok"})
        client.ok({"cmd": "leave_base"})
        session.wait_back_on_geoscape(client, "client back on geoscape")
        session.drain_host_coop_notice(host)
        b0 = session._campaign_base0(host)
        site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                        "deployment": "STR_TERROR_MISSION", "lon": b0["lon"] + 0.35,
                        "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})
        site_id = site["site_id"]
        host.wait_for("site on host", lambda: any(s["id"] == site_id for s in host.ok({"cmd": "geo_state"})
                                                  ["missionSites"]) or None, timeout=30)
        host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
                 "lon": b0["lon"] + 0.34, "lat": b0["lat"] + 0.10, "dest": f"site:{site_id}",
                 "fuel": 999999, "lowFuel": False})

        def landing_prompt():
            if session.has_state(host, "ConfirmLandingState"):
                return True
            t = session.states(host)[-1]
            if "CoopState" in t:
                host.cmd({"cmd": "coop_dialog_back"})
            elif "GeoscapeState" not in t:
                host.cmd({"cmd": "dismiss_popup"})
            host.cmd({"cmd": "geo_set_speed", "idx": 2})
            return None

        host.wait_for("host landing prompt", landing_prompt, timeout=120, interval=0.5)
        host.ok({"cmd": "set_seed", "seed": BES.SEED_P})
        ms = host.ok({"cmd": "coop_mission_start"})
        con["missionStart"] = {k: ms.get(k) for k in ("ok", "top", "inBattle")}
        host.wait_for("host entered", lambda: battle_state(host).get("inBattle") or None, timeout=120, interval=1.0)
        host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=60, interval=0.5)
        if not session.drive_both_to_tactical(host, client):
            raise TimeoutError("drive_both_to_tactical timed out (host=%s client=%s)"
                               % (session.states(host)[-3:], session.states(client)[-3:]))
    except BES.FixtureMiss:
        raise
    except Exception as e:
        BES.capture("separate_battle_again", short(e, 800), m)
    hb2, cb2 = battle_state(host), battle_state(client)
    guests = [u for u in hb2.get("units", []) if "Guest" in (u.get("name") or "")]
    con["entry"] = {"mapFingerprint": (hb2.get("mapFingerprint"), cb2.get("mapFingerprint")),
                    "guestUnits": [{k: u.get(k) for k in ("id", "name", "faction", "health", "isOut")} for u in guests],
                    "hostRecord": rec_keys(host), "clientRecord": rec_keys(client),
                    "tops": {"host": top(host), "client": top(client)}}
    if len(guests) != 1:
        BES.capture("again: guest unit",
                    f"expected one battle unit named 'Guest*', got {con['entry']['guestUnits']}", m)


def again_stage(rid, host, client, ctx):
    walls_mark(ctx, "battle2Start")
    m = (host, client)
    separate_battle_again(host, client, ctx)
    ctx["loadGamePushes0"] = BES.log_count(client, BES.LOADGAME_PUSH)
    live = sorted(u["id"] for u in battle_state(host).get("units", []) if u.get("faction") == 1 and not u.get("isOut"))
    k = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": 1})
    ctx["kill"] = {"live": live, "resp": {k2: k.get(k2) for k2 in ("ok", "killed", "error")}}
    if not k.get("ok") or not live or sorted(k.get("killed") or []) != live:
        BES.capture("again: kill", f"kill_unit_real faction 1 answered {ctx['kill']} (want every live hostile)", m)
    settled, secs, samples = BES.chain_settled(host, client, stable=1.0, timeout=45, want_live=0)
    ctx["settled"] = {"ok": settled, "secs": secs, "samples": samples[-12:]}
    if not settled:
        BES.capture("again: chain settle", f"the host's kill chain not settled within 45s: {samples[-6:]}", m)
    BES.end_turn_both(host, client)
    close = BES.close_host_nextturn(host)
    ok, secs = BES.wait_until(lambda: "DebriefingState" in stack(host), DEBRIEF_S)
    ctx["ending"] = {"reached": ok, "secs": secs, "close": None if close is None else close.get("handled"),
                     "hostStack": stack(host)}
    if not ok:
        BES.capture("again: host debriefing", f"no host DebriefingState within {DEBRIEF_S}s ({ctx['ending']})", m)
    hdeb = host.cmd({"cmd": "debrief_state"})
    ctx["hostDebrief"] = hdeb
    bad = [f"host debrief_state.{k2}={hdeb.get(k2)!r} (want {w!r})"
           for k2, w in (("shown", True), ("onTop", True), ("displayOnly", False), ("title", "Aliens defeated"))
           if hdeb.get(k2) != w]
    armed = (event_state(host).get("fatalVote") or {}).get("armed")
    if armed != 0:
        bad.append(f"host fatalVote.armed={armed!r} (want 0: no fatal-wounds vote)")
    if bad:
        BES.capture("again: host debriefing pin", "; ".join(bad), m)
    walls_mark(ctx, "battle2Debrief")


def again_return(host, client, ctx):
    """battle2_client_return: the client's OK through its follow-ups -> its own world; sepReturn for battle 2;
    missions + 1."""
    battle1 = SESSION["battle1"]
    ok1, ok, secs = BES.client_ok_through_followups(client, ctx, "clientReturn")
    pushes = BES.log_count(client, BES.LOADGAME_PUSH) - ctx["loadGamePushes0"]
    rec = BES.soldier_rec(client, sid=battle1["guestId"])
    after1 = battle1.get("guestAfter1") or {}
    sep = record(client).get("sepReturn")
    sep = sep if isinstance(sep, dict) else {}
    ctx["clientReturn"].update({"ok": ok1, "reached": ok, "secs": secs, "clientStack": stack(client),
                                "loadGamePushes": pushes, "sepReturn": sep,
                                "missions": {"after1": after1.get("missions"), "after2": rec.get("missions")},
                                "record": rec})
    f = []
    if not ok1["pressed"]:
        return [ok1["note"]]
    if (ok1.get("resp") or {}).get("handled") != "DebriefingState":
        f.append(f"client OK answered {ok1.get('resp')} (want handled DebriefingState)")
    if not ok:
        f.append(f"client not on a clean GeoscapeState within {BES.OK_S}s of its OK (stack {stack(client)})")
        return f
    if pushes != 0:
        f.append(f"client pushed {pushes} LoadGameState(s) since battle 2's kill (want 0: in-place return)")
    bad = {k: (sep.get(k), w) for k, w in WANT_SEP.items() if sep.get(k) != w}
    if bad:
        f.append(f"client battleEnd.sepReturn for battle 2 mismatch (key: (got, want)) = {bad}")
    if not isinstance(after1.get("missions"), int) or rec.get("missions") != after1["missions"] + 1:
        f.append(f"the guest's missions={rec.get('missions')!r} after battle 2 (want after battle 1 "
                 f"{after1.get('missions')!r} + 1)")
    return f


def again_host_ok(host, client, ctx):
    """battle2_host_return: the host's OK + drain; phase Idle on both; fatalVote.armed 0; the client zero-disk."""
    ok1 = BES.press_ok(host)
    reached, screens = BES.drain(host) if ok1["pressed"] else (False, [])
    ctx["hostOk"] = {"ok": ok1, "reached": reached, "screens": screens, "hostStack": stack(host)}
    f = []
    if not ok1["pressed"]:
        f.append(ok1["note"])
    if not reached:
        f.append(f"host not on GeoscapeState within {DRAIN_S}s of its OK (stack {stack(host)}, screens {screens})")
    phases = {gc.name: event_state(gc).get("phase") for gc in (host, client)}
    ctx["phaseEnd"] = phases
    f += [f"{n} event_state.phase={p!r} after battle 2 (want 'Idle')" for n, p in phases.items() if p != "Idle"]
    armed = (event_state(host).get("fatalVote") or {}).get("armed")
    if armed != 0:
        f.append(f"host fatalVote.armed={armed!r} after battle 2 (want 0)")
    try:
        session.assert_client_zero_disk(client.user_dir)
    except AssertionError as e:
        f.append(str(e))
    ctx["records"] = {"host": rec_keys(host), "client": rec_keys(client)}
    ctx["selState"] = {"host": sel_state(host), "client": sel_state(client)}
    walls_mark(ctx, "battle2End")
    return f


def again_cells(host, client, ctx):
    return [
        ("battle2_debriefs (both debriefings equal with page-2 names prefix-stripped, the client's display-only)",
         lambda: BES.cell_debriefs(host, client, ctx)),
        ("battle2_client_return (the client's OK -> its own world; sepReturn for battle 2; missions + 1)",
         lambda: again_return(host, client, ctx)),
        ("battle2_host_return (the host's OK + drain; phase Idle on both; the client zero-disk)",
         lambda: again_host_ok(host, client, ctx)),
    ]


def main():
    t0, results, walls = time.time(), {}, {}
    SESSION["t0"] = t0
    host = GameClient("host", 0, make_user_dir(f"{TAG}_host"))
    client = GameClient("client", 0, make_user_dir(f"{TAG}_client"))
    try:
        host.spawn(); client.spawn(); host.connect(); client.connect()
        BES.run_row("first_battle_loot", host, client, results, walls, battle1_stage, battle1_cells)
        if (SESSION.get("battle1") or {}).get("battle1Returned"):
            BES.run_row("second_battle", host, client, results, walls, again_stage, again_cells)
        else:
            results["second_battle"] = False
            print("FAIL second_battle: not reached (first_battle_loot's battle1_returns cell did not pass)", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[test_campaign_second_battle_separate] shutdown {gc.name}: {short(e)}", flush=True)
    order = ["first_battle_loot", "second_battle"]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_campaign_second_battle_separate: {len(passed)}/{len(order)} passed (pass={passed} "
          f"fail={failed}) in {time.time() - t0:.1f}s (row walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
