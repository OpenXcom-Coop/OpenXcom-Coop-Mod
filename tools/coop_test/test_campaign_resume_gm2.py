"""test_campaign_resume_gm2.py: a gm2 PvP campaign (host = X-COM, client = the aliens) across a mid-battle save
and its resume, and across the alien player's drop on the globe and its rejoin. The resumed battle keeps gm2's mode and seats and
ends with the X-COM win as an unsaved battle does; the rejoining alien player is back on its alien side (no base placement) and the
host keeps the campaign's mode.

Spec: docs rewrite/prompts/d250u_pvp_campaigns_sc.md, AMENDMENT SC-5 (SC5-3 "Stage S-C4a", SC5-5 file B, SC5-6 FX4A-1 .. FX4A-12) and its
rulings (QC4A-1 .. QC4A-4 (a)) and docs rewrite/w2-resume-efd75a6c/ruling-d250uci.md; QC-16 (a),
QC3-4 (a), L-SC3-1, VL-C-10, VL-C4A-1, VL-C4A-2; owner D250, O1 (a); F5106, F15861, F15863,
F15864. TASK 0 pins: docs rewrite/d250u-task0/sc4a/CONSTANTS.md (boots Rc_ui, Rd on the unchanged build; Rc2, Rd2 with C4AG applied,
then restored).

Boot R4 (gm2): lobby key 48041, dirs d250uc4a_r4_host / _client / _client2. Boot R6 (gm2, after R4): key 48041, dirs d250uc4a_r6_host /
_client / _client2. Bring-up in each (FX4A-2): PF.start_pvp_campaign(alien_player="client"); gamemode 2 / 2, client noBases true, host
false are preconditions; HOST0. A bring-up, landing, save, relaunch or staging miss is a setup failure: ONE "CAPTURE <boot>:" line and
every remaining cell of that boot FAILs "boot". A resume or rejoin that does not reach its bound is not a setup failure: its row's cells
FAIL with the captured state.
Rows and cells (one PASS / FAIL line per cell, one EVIDENCE line and one ROW line per row; a cell whose precondition was never reached
FAILs "blocked: <why>"):
  P3 (R4) the host's landing (FX4A-6), the quick_battle save at turn 1 side 0 (FX4A-7), both processes end, the battle resume
     (FX4A-8: resume_campaign_battle, session's copied with the host's START HOST through host_menu_host, R-D250-SC4A-1; the host's
     RESUME), the X-COM win (FX4A-9): P3-resume, P3-mode, P3-seats, P3-win,
     P3-common.
  P6 (R6) the alien player's drop on the globe and its rejoin (FX4A-10), then the host's landing with client2 (FX4A-6): P6-host,
     P6-back, P6-land, P6-common.
RED (C4AR, the unchanged build; TASK 0 boots Rc_ui / Rd): 3/9 - FAIL P3-mode, P3-seats, P3-win, P6-host, P6-back, P6-land
(blocked). GREEN (C4AG): 9/9.
P3-seats' seat-store half reads the host's battle_state.coopGamemode at the resume: the store is seeded from it (TCP offerResumedBattle,
coopSeatCanonicalFaction(gamemode, 1) = FACTION_HOSTILE for 2, CS :1974); battle_state.authority carries no seat map (CONSTANTS.md).

ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_campaign_resume_gm2.py
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
import geo  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import test_battle_end_separate as BES  # noqa: E402
import test_campaign_battle_gm2 as G2F  # noqa: E402
import test_campaign_battle_gm3 as G3B  # noqa: E402
import test_campaign_resume_roles as RR  # noqa: E402  (pure helpers only)

# ----- TASK 0 pins (docs rewrite/d250u-task0/sc4a/CONSTANTS.md) -----
KEY = "48041"
SEED = 1                                     # the host's set_seed right before its confirm_landing (G2F SEED_B)
SITE = RR.SITE
POINT = RR.POINT                             # G2F.to_battle's b0 + (0.35, 0.10), forced out 0.01 short (FX4A-6)
SQUAD = 2
STUB, STUB_FUNDS = RR.STUB, RR.STUB_FUNDS    # FX4A-11
TITLE_WIN = "Aliens defeated"                # FX4A-12 (S-B's pin)
FIX = {"P3-mode", "P3-seats", "P3-win", "P6-host", "P6-back", "P6-land"}   # TASK 0 Rc_ui / Rd (= SC5-5)
# ----- bounds -----
LANDING_S, BOTH_IN_S = 180, 180
SAVE_S = 30
RESUME_S, RESUME_PRESS_S, TOPS_S = 180, 60, 60
DEBRIEF_S, CLIENT_DEBRIEF_S, OK_S, DRAIN_S = 60, 20, 10, 60
WATCH994_S = 3.0
DIALOG62_S, REJOIN_S, SETTLE_S = 30, 135, 60
ROWS = {"P3": ["P3-resume", "P3-mode", "P3-seats", "P3-win", "P3-common"],
        "P6": ["P6-host", "P6-back", "P6-land", "P6-common"]}
BOOT = {"tag": "R4"}
stack, top, crash_set, wait, view, census = RR.stack, RR.top, RR.crash_set, RR.wait, RR.view, RR.census


class FixtureMiss(Exception):
    pass


RESULTS = []          # (cell, ok, detail)


def cell(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)


def block(names, why):
    for n in names:
        if n not in {x[0] for x in RESULTS}:
            cell(n, False, f"blocked: {why}")


def capture_boot(err, *machines):
    print(f"CAPTURE {BOOT['tag']}: {json.dumps(RR.capture(err, *machines), sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def gv(gc):
    c = gc.cmd({"cmd": "get_coop"})
    return {"gamemode": c.get("gamemode"), "noBases": c.get("noBases")}


def dlg(gc):
    r = gc.cmd({"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("present", "code", "title", "backVisible")}


def hash_res(host, other):
    try:
        session.assert_hash_clean(host, other, full=True)
        return "EQUAL"
    except Exception as e:  # noqa: BLE001
        return f"hash_now full: {str(e)[:400]}"


def bring_up(host, client, ev):
    """FX4A-2 (gm2): PF.start_pvp_campaign(alien_player="client"); the mode and the noBases pair are preconditions."""
    host.spawn(); host.connect(); client.spawn(); client.connect()
    try:
        ev["lobbyGamemode"] = PF.start_pvp_campaign(host, client, KEY, alien_player="client")
    except Exception as e:  # noqa: BLE001
        capture_boot(f"PF.start_pvp_campaign: {e}", host, client)
    hv, cv = view(host), view(client)
    ev.update(HOST0=hv, CLIENT0=cv)
    if [hv["gamemode"], cv["gamemode"], hv["noBases"], cv["noBases"]] != [2, 2, False, True]:
        capture_boot(f"bring-up preconditions (FX4A-2): gamemode {[hv['gamemode'], cv['gamemode']]} (want [2, 2]), noBases host / "
                     f"client {[hv['noBases'], cv['noBases']]} (want [false, true])", host, client)
    geo.slow_clock(host, client)
    return hv


def to_battle(host, c, ev, boot):
    """FX4A-6: G2F's to_battle copied (the host's Skyranger and squad of two, its own site at b0 + POINT, forced out 0.01 short; the
    landing prompt; host set_seed + confirm_landing; both inBattle <= 180 s). A staging miss is a setup failure; with boot=False the
    inBattle wait returns its failure instead. Returns (ok, detail, squad)."""
    b0 = session._campaign_base0(host)
    sky = next((x for x in b0.get("crafts", []) if "SKYRANGER" in x.get("type", "")), None)
    sids = G2F.host_soldiers(host)
    if not sky or len(sids) < SQUAD:
        capture_boot(f"no host Skyranger or fewer than {SQUAD} soldiers (sky {sky}, soldiers {sids})", host, c)
    for sid in sids:
        host.ok({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": False})
    for sid in sids[:SQUAD]:
        host.ok({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": True})
    site = host.cmd(dict(SITE, cmd="spawn_mission_site", lon=b0["lon"] + POINT[0], lat=b0["lat"] + POINT[1]))
    if not site.get("ok"):
        capture_boot(f"host spawn_mission_site {site}", host, c)
    host.ok({"cmd": "craft_force", "craft_id": sky["id"], "status": "STR_OUT", "lon": b0["lon"] + POINT[0] - 0.01,
             "lat": b0["lat"] + POINT[1], "dest": f"site:{site['site_id']}", "fuel": 999999, "lowFuel": False})

    def prompt():
        if session.has_state(host, "ConfirmLandingState"):
            return True
        for gc in (host, c):
            geo.drain_popups(gc, interest=geo.popup("ConfirmLandingState"))
            gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None
    ok, ps = wait(prompt, LANDING_S, 0.5)
    if not ok:
        capture_boot(f"no host ConfirmLandingState within {LANDING_S} s", host, c)
    host.ok({"cmd": "set_seed", "seed": SEED})
    host.ok({"cmd": "confirm_landing"})
    both, bs = wait(lambda: G3B.in_battle(host) and G3B.in_battle(c), BOTH_IN_S)
    ev.update(squad=sids[:SQUAD], site=site.get("site_id"), promptS=ps, bothInS=bs)
    detail = f"inBattle host/{c.name} {[G3B.in_battle(host), G3B.in_battle(c)]} {bs} s after the confirm"
    if not both and boot:
        capture_boot(detail, host, c)
    return both, detail, sids[:SQUAD]


def relaunch(x, ev):
    """FX4A-4: both shut down; the host respawned on ITS dir; client2 on an EMPTY dir; spawn, connect."""
    t0 = time.time()
    try:
        x["client"].shutdown()
        x["host"].shutdown()
        host = x["host"] = GameClient("host", None, x["host"].user_dir)
        c2 = x["client2"] = GameClient("client2", None, make_user_dir(x["tag"] + "_client2"))
        host.spawn(); host.connect(); c2.spawn(); c2.connect()
    except Exception as e:  # noqa: BLE001
        capture_boot(f"relaunch (FX4A-4): {type(e).__name__}: {str(e)[:300]}", x["host"], x.get("client2"))
    ev["relaunchS"] = round(time.time() - t0, 2)
    return host, c2


def resume_campaign_battle(host, client, save_file, port, host_name="HostPlayer", client_name="ClientPlayer", timeout=120,
                           interval=2.0):
    """session.resume_campaign_battle copied with ONE change: the host's START HOST goes through the real host
    window (host_menu_host visibility 0 -> HostMenu::hostTCPGame, HM :535), not the host_tcp lever (TS :14584-:14593; F16312)."""
    host.ok({"cmd": "load_save_menu", "file": save_file})
    host.wait_for("host window (battle resume)", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv", "port": port, "player": host_name})
    host.wait_for("resume lobby", lambda: session.has_state(host, "LobbyMenu"))
    ls = host.ok({"cmd": "lobby_state"})
    assert ls["lobbyMode"] == 2, f"expected resume lobby, got {ls}"
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": client_name})
    client.wait_for("client resume lobby", lambda: session.has_state(client, "LobbyMenu"))
    session.resume_campaign_via_button(host, client_name)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if host.cmd({"cmd": "battle_state"}).get("inBattle") and client.cmd({"cmd": "battle_state"}).get("inBattle"):
            return
        time.sleep(interval)
    raise TimeoutError(f"battle resume: both machines did not enter the battle within {timeout}s: host {session.states(host)[-3:]} / "
                       f"client {session.states(client)[-3:]}")


def snap(gc):
    b = battle_state(gc)
    a = b.get("authority") or {}
    return {"inBattle": b.get("inBattle"), "phase": b.get("phase"), "battleId": a.get("battleId"), "turn": b.get("turn"),
            "side": b.get("side"), "mapFingerprint": b.get("mapFingerprint"), "coopGamemode": b.get("coopGamemode"),
            "localSeat": a.get("localSeat")}


def win_cell(host, c2, ev):
    """FX4A-9 (S-B's B2): kill every live alien, END TURN; the host's debriefing, client2's display-only copy, client2's OK first,
    then the host's (a 994 is never drained)."""
    G2F.kill_all(host, c2, 1, ev, "kills")
    G2F.end_and_debrief(host, c2)
    ok, secs = wait(lambda: "DebriefingState" in stack(host), DEBRIEF_S)
    hdeb = host.cmd({"cmd": "debrief_state"})
    bad = [] if ok else [f"no host DebriefingState within {DEBRIEF_S} s (stack {stack(host)})"]
    bad += [f"host debrief {k} {hdeb.get(k)!r} (want {w!r})" for k, w in (("title", TITLE_WIN), ("displayOnly", False)) if hdeb.get(k) != w]
    cok, csecs = wait(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True and d.get("displayOnly") is True)(
        c2.cmd({"cmd": "debrief_state"})), CLIENT_DEBRIEF_S)
    hv, cv = BES.debrief_view(hdeb), BES.debrief_view(c2.cmd({"cmd": "debrief_state"}))
    bad += [] if cok else [f"no client2 display-only DebriefingState within {CLIENT_DEBRIEF_S} s (stack {stack(c2)})"]
    bad += [f"client2 debrief {k} {cv.get(k)!r} != host {hv.get(k)!r}" for k in BES.DEBRIEF_FIELDS if cok and cv.get(k) != hv.get(k)]
    t_ok = time.time()
    pk = BES.press_ok(c2)
    BES.drain(c2, timeout=OK_S)
    gok, gs = wait(lambda: BES.geo_clean(c2), OK_S)
    c2v = view(c2)
    bad += [] if gok else [f"client2 not geo_clean within {OK_S} s of its OK (stack {stack(c2)})"]
    bad += [f"client2 {k} {c2v[k]!r} (want {w!r})" for k, w in (("noBases", True), ("funds", STUB_FUNDS)) if c2v[k] != w]
    watch = []
    while time.time() - t_ok < WATCH994_S:
        if top(host) == "CoopState" and dlg(host).get("code") == 994:
            watch.append(round(time.time() - t_ok, 2))
            break
        time.sleep(0.1)
    hk = BES.press_ok(host)
    hreached, hscreens, on994 = G2F.drain_host(host)
    hok, hs = wait(lambda: BES.geo_clean(host), DRAIN_S) if hreached else (False, 0)
    hv2 = view(host)
    bad += [f"host CoopState 994 {watch} s after client2's OK"] if watch or on994 else []
    bad += [] if hok else [f"host not geo_clean within {DRAIN_S} s of its OK (stack {stack(host)}, screens {hscreens})"]
    bad += [f"host noBases {hv2['noBases']!r} (want false)"] if hv2["noBases"] is not False else []
    ev.update(hostDebrief={k: hdeb.get(k) for k in ("title", "displayOnly", "rating", "total")}, clientDebriefS=csecs, debriefS=secs,
              client2Ok={"press": pk, "geoS": gs, "view": c2v}, hostOk={"press": hk, "screens": hscreens, "geoS": hs, "view": hv2})
    cell("P3-win", not bad, "; ".join(bad) or f"host DebriefingState {secs} s, {TITLE_WIN!r}; client2 display-only debriefing equal; "
         f"client2 OK -> geo_clean, noBases true, funds {STUB_FUNDS}; host OK -> geo_clean, noBases false, no 994")


def row_p3(x, ev):
    host, client = x["host"], x["client"]
    crash0, t_row = crash_set(), time.time()
    bring_up(host, client, ev)
    to_battle(host, client, ev, True)
    sp_ok, sp_detail = G2F.spine(host, client, ev)
    if not sp_ok:
        capture_boot(f"P3: the spine before the save: {sp_detail}", host, client)
    ev["hashAfterSpine"] = hash_res(host, client)
    saved = dict(snap(host), census=census(host))
    ev["SAVED"] = saved
    if (saved["turn"], saved["side"]) != (1, 0):
        capture_boot(f"P3: SAVED turn / side {(saved['turn'], saved['side'])} (want (1, 0): the X-COM host's own turn, FX4A-7)", host,
                     client)
    before = set(session.save_files(host.user_dir))
    ev["saveReply"] = host.cmd({"cmd": "save_game_ui", "type": "quick_battle"})
    ok, ss = wait(lambda: set(session.save_files(host.user_dir)) - before, SAVE_S, 0.2)
    new = sorted(set(session.save_files(host.user_dir)) - before)
    bs = battle_state(host)
    ev.update(newSaves=new, saveS=ss, coopSaveDeferrals=bs.get("coopSaveDeferrals"), coopSavePending=bs.get("coopSavePending"))
    if not ok or len(new) != 1 or not new[0].endswith(".asav"):
        capture_boot(f"P3: the quick_battle save: new files {new} within {SAVE_S} s (want one .asav, FX4A-7)", host, client)
    time.sleep(1.0)
    ev["saveKeys"] = RR.save_keys(os.path.join(host.user_dir, new[0]))
    host, c2 = relaunch(x, ev)
    t0, res, rbad = time.time(), None, []
    try:
        resume_campaign_battle(host, c2, os.path.basename(new[0]), port=KEY, timeout=RESUME_S)
        ev["press"] = session.press_back_when_shown(host, "host RESUME", codes=(60, 62), timeout=RESUME_PRESS_S)
        t1 = time.time()
        tok, ts = wait(lambda: top(host) == "BattlescapeState" and top(c2) == "BattlescapeState", TOPS_S)
        ev.update(resumeS=round(t1 - t0, 2), topsS=ts)
        rbad += [] if tok else [f"tops host/client2 {[top(host), top(c2)]} (want BattlescapeState on both within {TOPS_S} s of RESUME)"]
        res = [snap(host), snap(c2)]
    except Exception as e:  # noqa: BLE001
        ev.update(resumeError=f"{type(e).__name__}: {str(e)[:300]}", resumeCapture=RR.capture("resume", host, c2))
    ev["afterResume"] = {"host": view(host), "client2": view(c2), "battle": res}
    if res is None:
        block(ROWS["P3"][:4], f"the battle resume never reached both inBattle / the host's RESUME ({ev.get('resumeError')})")
    else:
        for nm, s in (("host", res[0]), ("client2", res[1])):
            rbad += [f"{nm} inBattle {s['inBattle']!r} phase {s['phase']!r}"] if s["inBattle"] is not True or s["phase"] != "Active" else []
            rbad += [f"{nm} turn / side {(s['turn'], s['side'])} (want SAVED's {(saved['turn'], saved['side'])})"] \
                if (s["turn"], s["side"]) != (saved["turn"], saved["side"]) else []
            rbad += [f"{nm} mapFingerprint {s['mapFingerprint']!r} (want SAVED's {saved['mapFingerprint']!r})"] \
                if s["mapFingerprint"] != saved["mapFingerprint"] else []
        rbad += [f"battleId host/client2 {[res[0]['battleId'], res[1]['battleId']]} (want equal, non-zero)"] \
            if not res[0]["battleId"] or res[0]["battleId"] != res[1]["battleId"] else []
        cell("P3-resume", not rbad, "; ".join(rbad) or "both inBattle, phase Active, battleId equal; turn / side and mapFingerprint == "
             "SAVED's; both tops BattlescapeState after RESUME")
        hv, cv = ev["afterResume"]["host"], ev["afterResume"]["client2"]
        mbad = [f"{nm} gamemode {v['gamemode']!r} (want 2)" for nm, v in (("host", hv), ("client2", cv)) if v["gamemode"] != 2]
        mbad += [f"client2 noBases {cv['noBases']!r} (want true)"] if cv["noBases"] is not True else []
        cell("P3-mode", not mbad, "; ".join(mbad) or "gamemode 2 on host and client2; client2 noBases true")
        cen = [census(host), census(c2)]
        sbad = RR.seats_bad(cen[0], cen[1], 0, 1, [u["id"] for u in saved["census"] if u.get("faction") == 0])
        key = lambda c: sorted((u["id"], u.get("faction"), u.get("coop"), u.get("hasAI")) for u in c)  # noqa: E731
        sbad += [f"census != SAVED's ({key(saved['census'])})"] if key(cen[0]) != key(saved["census"]) else []
        sbad += [f"host battle_state.coopGamemode {res[0]['coopGamemode']!r} at the resume (want 2: seat 1 = FACTION_HOSTILE)"] \
            if res[0]["coopGamemode"] != 2 else []
        cell("P3-seats", not sbad, "; ".join(sbad) or f"census equal on both and == SAVED's ({len(cen[0])} units: faction 0 seat 0, "
             f"faction 1 seat 1 without AI); host coopGamemode 2 (seat 1 FACTION_HOSTILE)")
        ev["census"] = cen
        ev["hashAfterResume"] = hash_res(host, c2)
        if rbad or not (res[0]["inBattle"] and res[1]["inBattle"]):
            block(["P3-win"], "the resumed battle is not up on both (P3-resume)")
        else:
            win_cell(host, c2, ev)
    eh, ec = event_state(host), event_state(c2)
    new_c = sorted(crash_set() - crash0)
    cbad = [f"desyncSeen host {eh.get('desyncSeen')!r} client2 {ec.get('desyncSeen')!r}"] \
        if eh.get("desyncSeen") is not False or ec.get("desyncSeen") is not False else []
    cbad += [f"{len(new_c)} new crash file(s) since the row's start (first {os.path.basename(new_c[0])})"] if new_c else []
    cbad += [f"client2 zero-disk: {session.save_files(c2.user_dir)}"] if session.save_files(c2.user_dir) else []
    cbad += [f"after the spine: {ev['hashAfterSpine']}"] if ev["hashAfterSpine"] != "EQUAL" else []
    cbad += [f"after RESUME: {ev.get('hashAfterResume', 'not reached')}"] if ev.get("hashAfterResume") != "EQUAL" else []
    cell("P3-common", not cbad, "; ".join(cbad) or "desyncSeen false on host and client2, 0 new crash files, client2 zero-disk, "
         "hash_now full EQUAL after the spine and after RESUME")
    ev["wall"] = round(time.time() - t_row, 1)


def row_p6(x, ev):
    host, client = x["host"], x["client"]
    crash0, t_row = crash_set(), time.time()
    bring_up(host, client, ev)
    client.kill()
    t_k = time.time()
    ok, s62 = wait(lambda: top(host) == "CoopState" and dlg(host).get("code") == 62, DIALOG62_S)
    if not ok:
        capture_boot(f"P6: host dialog 62 not on top within {DIALOG62_S} s of the drop (FX4A-10)", host)
    probes = {"62": gv(host)}
    for mark in (2.0, 10.0):
        time.sleep(max(0.0, mark - (time.time() - t_k)))
        probes[f"{mark:.0f}s"] = gv(host)
    c2 = x["client2"] = GameClient("client2", None, make_user_dir(x["tag"] + "_client2"))
    c2.spawn(); c2.connect()
    t_j = time.time()
    ev["join"] = c2.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    seen, pok = {"bnb": [], "stacks": []}, []

    def look():
        st2 = stack(c2)
        if not seen["stacks"] or seen["stacks"][-1][1] != st2:
            seen["stacks"].append([round(time.time() - t_j, 2), st2])
        if "BuildNewBaseState" in st2:
            seen["bnb"].append(round(time.time() - t_j, 2))
        return st2

    def ready():
        st2 = look()
        for gc in (host, c2):
            if top(gc) == "Profile" and (gc is host or dlg(c2).get("code") != 52):
                pok.append([gc.name, round(time.time() - t_j, 2), gc.cmd({"cmd": "profile_ok"}).get("ok")])
        d = dlg(host)
        return "BuildNewBaseState" in st2 or (top(host) == "CoopState" and d.get("code") == 62 and d.get("backVisible") is True)
    ok, rs = wait(ready, REJOIN_S)
    probes["ready"] = gv(host)
    ev.update(dialog62S=s62, readyS=rs, profileOk=pok, afterJoin={"host": gv(host), "client2": gv(c2)})
    back, settled = [], False
    if not ok:
        back.append(f"neither the host's dialog 62 RESUME nor a client2 BuildNewBaseState within {REJOIN_S} s of the join")
        ev["rejoinCapture"] = RR.capture("rejoin", host, c2)
    elif seen["bnb"]:
        back.append(f"client2 BuildNewBaseState {seen['bnb'][0]} s after its join (a NEW world: base placement on the alien side; "
                    f"client2 {gv(c2)})")
    else:
        try:
            ev["resume"] = session.press_back_when_shown(host, "host RESUME", codes=(60, 62))
        except Exception as e:  # noqa: BLE001
            back.append(f"host RESUME: {str(e)[:300]}")
        t_r = time.time()
        if "StoresState" in stack(host):
            ev["closeScreens"] = host.cmd({"cmd": "close_screens"})

        def rejoined():
            st2 = look()
            return BES.geo_clean(host) and bool(st2) and not any("CoopState" in s or "LoadGameState" in s for s in st2) \
                and st2[-1] == "GeoscapeState"
        settled, ss = wait(rejoined, SETTLE_S)
        probes["afterResume"] = gv(host)
        c2a = view(c2)
        ev.update(settleS=ss, resumeS=round(t_r - t_j, 2), client2AfterResume=c2a)
        time.sleep(10.0)
        probes["afterResume10s"] = gv(host)
        ev["client2After10s"] = gv(c2)
        back += [] if settled else [f"client2 not on a clean GeoscapeState (no CoopState / LoadGameState) and host not geo_clean within "
                                    f"{SETTLE_S} s of RESUME ({stack(host)} / {stack(c2)})"]
        back += [f"client2 BuildNewBaseState at {seen['bnb'][0]} s"] if seen["bnb"] else []
        back += [f"client2 {k} {c2a[k]!r} (want {w!r})" for k, w in (("gamemode", 2), ("noBases", True), ("funds", STUB_FUNDS),
                                                                    ("realBases", STUB)) if c2a[k] != w]
        back += [f"client2 10 s later {ev['client2After10s']} (want gamemode 2, noBases true)"] \
            if ev["client2After10s"] != {"gamemode": 2, "noBases": True} else []
    ev.update(probes=probes, client2Stacks=seen["stacks"][-8:])
    hbad = [f"host at {k}: {v} (want gamemode 2, noBases false)" for k, v in probes.items() if v != {"gamemode": 2, "noBases": False}]
    cell("P6-host", not hbad, "; ".join(hbad) or f"host gamemode 2, noBases false at every probe ({sorted(probes)})")
    cell("P6-back", not back, "; ".join(back) or "client2 never on BuildNewBaseState; clean GeoscapeState after RESUME; gamemode 2, "
         f"noBases true, funds {STUB_FUNDS}, real bases == the stub")
    if back or not settled:
        block(["P6-land"], "client2 lost its alien side (P6-back)")
    else:
        both, detail, _sq = to_battle(host, c2, ev, False)
        lbad = [] if both else [detail]
        if both:
            sp_ok, sp_detail = G2F.spine(host, c2, ev)
            lbad += [] if sp_ok else [sp_detail]
            cen = census(c2)
            ev["census"] = cen
            f1 = [u for u in cen if u.get("faction") == 1]
            lbad += [f"client2 faction 1 units {len(f1)} (want > 0)"] if not f1 else []
            lbad += [f"client2 unit {u['id']} faction 1 seat {u.get('coop')} hasAI {u.get('hasAI')} (want seat 1, hasAI false)"
                     for u in f1 if u.get("coop") != 1 or u.get("hasAI") is not False]
        cell("P6-land", not lbad, "; ".join(lbad) or "both inBattle after the host's confirm; spine; faction 1 units seat 1 without AI")
    eh, ec = event_state(host), event_state(c2)
    new_c = sorted(crash_set() - crash0)
    kill_tag = time.strftime("%Y%m%d_%H%M%S", time.localtime(t_k))[:-1]      # the killed client's own files: named at the kill
    own = [f for f in new_c if re.search(r"crash_" + kill_tag, os.path.basename(f))]
    new_c = [f for f in new_c if f not in own]
    ev["killedClientCrashFiles"] = [os.path.basename(f) for f in own]
    cbad = [f"desyncSeen host {eh.get('desyncSeen')!r} client2 {ec.get('desyncSeen')!r}"] \
        if eh.get("desyncSeen") is not False or ec.get("desyncSeen") is not False else []
    cbad += [f"{len(new_c)} new crash file(s) since the row's start (first {os.path.basename(new_c[0])})"] if new_c else []
    cbad += [f"client2 zero-disk: {session.save_files(c2.user_dir)}"] if session.save_files(c2.user_dir) else []
    cell("P6-common", not cbad, "; ".join(cbad) or "desyncSeen false on host and client2, 0 new crash files (the killed client's own "
         "excluded), client2 zero-disk")
    ev["wall"] = round(time.time() - t_row, 1)


def run_boot(tag, label, row, fn):
    """One boot: host and client, the row, then every machine shut down."""
    BOOT["tag"] = label
    x = {"tag": tag, "host": GameClient("host", None, make_user_dir(tag + "_host")),
         "client": GameClient("client", None, make_user_dir(tag + "_client")), "client2": None}
    ev = {}
    try:
        fn(x, ev)
    except FixtureMiss as e:
        block(ROWS[row], f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        ev["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"[ERROR] boot {label}: {ev['error']}", flush=True)
        block(ROWS[row], f"error {ev['error']}")
    finally:
        print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
        bad = [n for n, ok, _ in RESULTS if n in ROWS[row] and not ok]
        print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)
        for gc in (x["client2"], x["client"], x["host"]):
            try:
                if gc is not None and gc.proc is not None and gc.proc is not getattr(gc, "_shutdown_proc", None):
                    gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)


def main():
    t0 = time.time()
    run_boot("d250uc4a_r4", "R4", "P3", row_p3)
    run_boot("d250uc4a_r6", "R6", "P6", row_p6)
    allc = ROWS["P3"] + ROWS["P6"]
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== D250-U S-C4a resumed gm2 battle and gm2 rejoin: {len(RESULTS) - len(fails)}/{len(allc)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (FIX cell)' if n in FIX else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(allc) else 2)


if __name__ == "__main__":
    main()
