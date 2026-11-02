"""test_campaign_resume_roles.py: a resumed PvP campaign keeps its mode and both roles. A gm3 campaign (host =
the aliens, client = X-COM) and a gm2 campaign (host = X-COM, client = the aliens) are each saved on the geoscape, both processes end,
and a fresh pair resumes the save: the resumed campaign plays its own PvP mode, each side keeps its role, and the next landing starts a
PvP battle with that mode's seats.

The fixture values below were measured on builds with and without the handling that keeps a resumed PvP campaign's
mode and roles.

Boot gm3_boot (gm3): lobby key 48017, dirs campaign_resume_roles_gm3_host / _client / _client2. Boot gm2_boot (gm2,
after gm3_boot): key 48017, dirs campaign_resume_roles_gm2_host / _client / _client2. Each boot: bring-up (gm3:
test_campaign_gm3_drop's bring_up, copied; gm2: PF.start_pvp_campaign alien_player="client"; the mode and noBases
pair are preconditions); the host's direct save_game; both processes end; the host respawns on ITS dir and client2 on
an EMPTY dir; resume_campaign, session.resume_campaign copied with the host's START HOST through host_menu_host
(visibility 0: HostMenu::hostTCPGame) instead of the host_tcp test command. A bring-up, save, relaunch or staging miss
is a setup failure: ONE "CAPTURE <boot>:" line and every remaining cell of that boot FAILs "boot". A resume that does
not reach its session-up bound is not a setup failure: its row's cells FAIL with the captured state.
Rows and cells (one PASS / FAIL line per cell, one EVIDENCE line and one ROW line per row; a cell whose precondition was never reached
FAILs "blocked: <why>"):
  gm3_resume (gm3_boot) gm3 geoscape save + resume, client2's landing: gm3_resume-mode, gm3_resume-role,
     gm3_resume-land, gm3_resume-seats, gm3_resume-common.
  gm2_resume (gm2_boot) gm2 geoscape save + resume, the host's landing: gm2_resume-mode, gm2_resume-role,
     gm2_resume-land, gm2_resume-seats, gm2_resume-common.
A build without that handling passes 3/10: gm3_resume-mode, gm3_resume-role, gm3_resume-land (client2's landing is
refused), gm2_resume-mode and gm2_resume-land FAIL, and gm3_resume-seats and gm2_resume-seats are blocked. With it,
10/10 pass.

ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_campaign_resume_roles.py
"""

import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import geo  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import battle_end_helpers as BES  # noqa: E402
import test_campaign_battle_gm3_end as G3E  # noqa: E402
import test_campaign_battle_gm3 as G3B  # noqa: E402
import test_campaign_battle_gm2 as G2F  # noqa: E402
import test_campaign_rejoin as CR  # noqa: E402

# ----- fixture values -----
KEY = "48017"
# set right before the confirm_landing: by the X-COM client2 in gm3_resume, by the host in gm2_resume
SEED = 1
SITE = {"mission": "STR_ALIEN_RESEARCH", "deployment": "STR_MEDIUM_SCOUT", "race": "STR_SECTOID", "hours": 240}
# offsets from the X-COM player's base: the mission site, and the Skyranger's forced position 0.01 short of it
POINT, CRAFT_AT = (0.35, 0.10), (0.34, 0.10)
SQUAD = 2
SAVE = {"gm3_resume": "resume_roles_gm3.sav", "gm2_resume": "resume_roles_gm2.sav"}
STUB = [{"name": "", "lon": 0.0, "lat": 0.0, "soldiers": 0}]   # buildCoopStub's one unplaced, unnamed, empty base
STUB_FUNDS = 1000                                              # get_coop.noBases's effect on geo_state.funds
# the cells that fail on a build that does not keep a resumed PvP campaign's mode and roles (the others are guards)
FIX = {"gm3_resume-mode", "gm3_resume-role", "gm3_resume-land", "gm3_resume-seats",
       "gm2_resume-mode", "gm2_resume-land", "gm2_resume-seats"}
# ----- bounds -----
SAVE_S = 10
MIRROR_S = 30
LANDING_S = 180
BOTH_IN = {"gm3_resume": 60, "gm2_resume": 180}
ROWS = {"gm3_resume": ["gm3_resume-mode", "gm3_resume-role", "gm3_resume-land", "gm3_resume-seats",
                       "gm3_resume-common"],
        "gm2_resume": ["gm2_resume-mode", "gm2_resume-role", "gm2_resume-land", "gm2_resume-seats",
                       "gm2_resume-common"]}
BOOT = {"tag": "gm3_boot"}


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


def evidence(row, obj):
    print(f"EVIDENCE {row}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)


def row_verdict(row, names):
    bad = [n for n, ok, _ in RESULTS if n in names and not ok]
    print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)


def alive(gc):
    return gc is not None and gc.proc is not None and gc.proc.poll() is None


def stack(gc):
    return session.states_stripped(gc)


def top(gc):
    st = stack(gc)
    return st[-1] if st else None


def crash_set():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))


def wait(pred, timeout, interval=0.25):
    return BES.wait_until(pred, timeout, interval)


def rbases(g):
    return [{"name": b.get("name"), "lon": round(b.get("lon") or 0.0, 9), "lat": round(b.get("lat") or 0.0, 9),
             "soldiers": b.get("soldiers")} for b in g.get("bases", []) if not b.get("coopBase") and not b.get("coopIcon")]


def view(gc):
    """get_coop {gamemode, noBases, localSeat, saveID} + geo_state {funds, real bases}, as printed in EVIDENCE."""
    c, g = gc.cmd({"cmd": "get_coop"}), gc.ok({"cmd": "geo_state"})
    return {"gamemode": c.get("gamemode"), "noBases": c.get("noBases"), "localSeat": c.get("localSeat"), "saveID": c.get("saveID"),
            "funds": g.get("funds"), "realBases": rbases(g)}


def capture(err, *machines):
    """The captured state of each live machine: stack, battle_state (read only when CR.bs_raw allows it; otherwise the
    probe would dereference a stale _battleState after a BattlescapeState pop and kill the process), coop_dialog_info,
    get_coop, the last 40 engine log lines."""
    cap = {}
    for gc in machines:
        if not alive(gc):
            continue
        try:
            bs = CR.bs_raw(gc)
            with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as fh:
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[-40:]
            cap[gc.name] = {"stack": stack(gc), "battle": {k: bs.get(k) for k in ("inBattle", "phase", "side", "turn")} if bs else
                            "skipped (no BattlescapeState, a battle in the world)",
                            "coop_dialog_info": gc.cmd({"cmd": "coop_dialog_info"}),
                            "get_coop": gc.cmd({"cmd": "get_coop"}), "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    return {"missed": err, "machines": cap}


def capture_boot(err, *machines):
    print(f"CAPTURE {BOOT['tag']}: {json.dumps(capture(err, *machines), sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def census(gc):
    return [{k: u.get(k) for k in ("id", "faction", "coop", "hasAI", "isOut")} for u in battle_state(gc).get("units", [])]


def seats_bad(cen_h, cen_c, f0_seat, f1_seat, f0_ids, other="client2"):
    """Census equal on both; every faction-0 unit seat f0_seat with its id in f0_ids; every faction-1 unit seat f1_seat with hasAI
    false; no other faction."""
    bad = []
    for nm, cen in (("host", cen_h), (other, cen_c)):
        f0 = [u for u in cen if u.get("faction") == 0]
        f1 = [u for u in cen if u.get("faction") == 1]
        bad += [f"{nm}: faction 0 units {len(f0)}, faction 1 units {len(f1)} (want both > 0)"] if not f0 or not f1 else []
        bad += [f"{nm}: faction 0 ids {sorted(u['id'] for u in f0)} (want {sorted(f0_ids)})"] if {u["id"] for u in f0} != set(f0_ids) \
            else []
        bad += [f"{nm}: unit {u['id']} faction 0 seat {u.get('coop')} (want {f0_seat})" for u in f0 if u.get("coop") != f0_seat]
        bad += [f"{nm}: unit {u['id']} faction 1 seat {u.get('coop')} hasAI {u.get('hasAI')} (want seat {f1_seat}, hasAI false)"
                for u in f1 if u.get("coop") != f1_seat or u.get("hasAI") is not False]
        bad += [f"{nm}: unit {u['id']} faction {u.get('faction')}" for u in cen if u.get("faction") not in (0, 1)]
    key = lambda cen: sorted((u["id"], u.get("faction"), u.get("coop"), u.get("hasAI")) for u in cen)  # noqa: E731
    bad += [f"census host {key(cen_h)} != {other} {key(cen_c)}"] if key(cen_h) != key(cen_c) else []
    return bad


def common(row, host, c2, crash0, spine):
    eh, ec = event_state(host), event_state(c2)
    new = sorted(crash_set() - crash0)
    bad = [f"desyncSeen host {eh.get('desyncSeen')!r} client2 {ec.get('desyncSeen')!r} (want false on both)"] \
        if eh.get("desyncSeen") is not False or ec.get("desyncSeen") is not False else []
    bad += [f"{len(new)} new crash file(s) since the row's start (first {os.path.basename(new[0])})"] if new else []
    try:
        session.assert_client_zero_disk(c2.user_dir)
    except AssertionError as e:
        bad.append(f"client2 zero-disk: {str(e)[:300]}")
    if spine:
        try:
            session.assert_hash_clean(host, c2, full=True)
        except Exception as e:  # noqa: BLE001
            bad.append(f"hash_now full: {str(e)[:400]}")
    cell(f"{row}-common", not bad, "; ".join(bad) or "desyncSeen false on host and client2, 0 new crash files, client2 zero-disk"
         + (", hash_now full EQUAL after the spine" if spine else " (no spine: no hash)"))


def bring_up(host, client, gm, ev):
    """gm3: test_campaign_gm3_drop's bring_up (copied, KEY); gm2: PF.start_pvp_campaign(alien_player="client"). Returns
    (HOST0, CLIENT0, xb)."""
    host.spawn(); host.connect(); client.spawn(); client.connect()
    try:
        lob = PF.start_pvp_campaign(host, client, KEY, alien_player="host" if gm == 3 else "client")
    except Exception as e:  # noqa: BLE001
        capture_boot(f"PF.start_pvp_campaign: {e}", host, client)
    hv, cv = view(host), view(client)
    cg = client.ok({"cmd": "geo_state"})
    xb = next((b for b in cg.get("bases", []) if not b.get("coopBase") and not b.get("coopIcon")), None)
    sky = next((c for c in (xb or {}).get("crafts", []) if "SKYRANGER" in c.get("type", "") and not c.get("coop")), None)
    ev.update(lobbyGamemode=lob, HOST0=hv, CLIENT0=dict(cv, sky=sky and {"type": sky.get("type"), "id": sky.get("id")}))
    want = (True, False) if gm == 3 else (False, True)
    if [hv["gamemode"], cv["gamemode"]] != [gm, gm] or (hv["noBases"], cv["noBases"]) != want:
        capture_boot(f"bring-up preconditions: gamemode {[hv['gamemode'], cv['gamemode']]} (want [{gm}, {gm}]), noBases host / "
                     f"client {[hv['noBases'], cv['noBases']]} (want {list(want)})", host, client)
    if gm == 3 and (not xb or not sky):
        capture_boot(f"the client has no real base / Skyranger (base {xb and xb.get('name')}, sky {sky})", host, client)
    geo.slow_clock(host, client)
    return hv, dict(cv, sky=sky and {"type": sky.get("type"), "id": sky.get("id")}), xb


def save_keys(path):
    """The save's coop YAML keys (PyYAML), every document."""
    import yaml
    out = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            docs = list(yaml.load_all(fh, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader)))
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    for i, d in enumerate(docs):
        if not isinstance(d, dict):
            continue
        for k in ("coop_gamemode", "no_bases", "coop_save_owner_player_id"):
            if k in d:
                out[f"{k}@{i}"] = d[k]
        cs = d.get("coopClientSaves")
        if cs is not None:
            out[f"coopClientSaves@{i}"] = sorted(cs) if isinstance(cs, dict) else \
                [str(e.get("key") or e.get("name") or sorted(e))[:80] if isinstance(e, dict) else str(e)[:80] for e in cs]
    return out


def geo_save(host, client, name, ev):
    """The host's direct save_game test command; the file in <host dir>\\xcom1\\ <= SAVE_S; its YAML keys as EVIDENCE."""
    path = os.path.join(host.user_dir, "xcom1", name)
    r = host.cmd({"cmd": "save_game", "file": name})
    ok, secs = wait(lambda: os.path.exists(path) and os.path.getsize(path) > 0, SAVE_S, 0.2)
    if not r.get("ok") or not ok:
        capture_boot(f"host save_game {name}: {r}, file present {os.path.exists(path)} "
                     "(want ok and a non-empty file)", host, client)
    time.sleep(1.0)
    ev.update(save={"file": name, "s": secs, "bytes": os.path.getsize(path), "keys": save_keys(path)})


def relaunch(x, ev):
    """Both shut down; the host respawned on ITS dir; client2 on an EMPTY dir; spawn, connect. Returns (host, client2)."""
    t0 = time.time()
    try:
        x["client"].shutdown()
        x["host"].shutdown()
        host = x["host"] = GameClient("host", None, x["host"].user_dir)
        c2 = x["client2"] = GameClient("client2", None, make_user_dir(x["tag"] + "_client2"))
        host.spawn(); host.connect(); c2.spawn(); c2.connect()
    except Exception as e:  # noqa: BLE001
        capture_boot(f"relaunch: {type(e).__name__}: {str(e)[:300]}", x["host"], x.get("client2"))
    ev["relaunchS"] = round(time.time() - t0, 2)
    return host, c2


def resume_campaign(host, client, save_file, port, host_name="HostPlayer", client_name="ClientPlayer"):
    """session.resume_campaign copied with ONE change: the host's START HOST goes through the real host window
    (host_menu_host visibility 0 -> HostMenu::hostTCPGame), not the host_tcp test command, which keeps a loaded save's
    mode and so never reaches the host window's handling of that mode."""
    host.ok({"cmd": "load_save_menu", "file": save_file})
    host.wait_for("host window (resume)", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv", "port": port, "player": host_name})
    host.wait_for("resume lobby", lambda: session.has_state(host, "LobbyMenu"))
    ls = host.ok({"cmd": "lobby_state"})
    assert ls["lobbyMode"] == 2, f"expected resume lobby, got {ls}"
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": client_name})
    client.wait_for("client resume lobby", lambda: session.has_state(client, "LobbyMenu"))
    session.resume_campaign_via_button(host, client_name)
    host.wait_for("client world ack", lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None, timeout=120)
    session.press_back_when_shown(host, "host RESUME", codes=(60, 62))
    client.wait_for("resume session up", lambda: "GeoscapeState" in session.states(client)[-1] if session.states(client) else None,
                    timeout=120)


def resume(host, c2, name, ev):
    """resume_campaign (the copy above) on KEY. Returns True, or False with the captured state (the row's cells FAIL)."""
    t0 = time.time()
    try:
        resume_campaign(host, c2, name, port=KEY)
    except Exception as e:  # noqa: BLE001
        ev.update(resumeError=f"{type(e).__name__}: {str(e)[:300]}", resumeCapture=capture("resume", host, c2))
        return False
    ev["resumeS"] = round(time.time() - t0, 2)
    ev["afterResume"] = {"host": view(host), "client2": view(c2)}
    return True


def mode_role_cells(row, gm, ok_resume, ev, host0, client0):
    if not ok_resume:
        block([f"{row}-mode", f"{row}-role"], f"the resume never reached session up ({ev.get('resumeError')})")
        return
    hv, cv = ev["afterResume"]["host"], ev["afterResume"]["client2"]
    mbad = [f"{nm} gamemode {v['gamemode']!r} (want {gm})" for nm, v in (("host", hv), ("client2", cv)) if v["gamemode"] != gm]
    cell(f"{row}-mode", not mbad, "; ".join(mbad) or f"get_coop.gamemode {gm} on host and client2 after the resume")
    if gm == 3:
        want = (("host", hv, "noBases", True), ("host", hv, "funds", STUB_FUNDS), ("host", hv, "realBases", host0["realBases"]),
                ("client2", cv, "noBases", False), ("client2", cv, "realBases", client0["realBases"]))
    else:
        want = (("client2", cv, "noBases", True), ("client2", cv, "funds", STUB_FUNDS), ("client2", cv, "realBases", STUB),
                ("host", hv, "noBases", False), ("host", hv, "realBases", host0["realBases"]))
    rbad = [f"{nm} {k} {v[k]!r} (want {w!r})" for nm, v, k, w in want if v[k] != w]
    cell(f"{row}-role", not rbad, "; ".join(rbad) or ("host noBases true, funds 1000, real bases == HOST0's; client2 noBases false, "
                                                      "real bases == CLIENT0's" if gm == 3 else
                                                      "client2 noBases true, funds 1000, real bases == the stub; host noBases "
                                                      "false, real bases == HOST0's"))


def mirror(gc, point):
    return next((m for m in gc.ok({"cmd": "geo_state"}).get("missionSites", [])
                 if m.get("coop") and abs(m.get("lon", 9.0) - point[0]) < 0.01 and abs(m.get("lat", 9.0) - point[1]) < 0.01), None)


def gm3_land(host, c2, ev):
    """test_campaign_gm3_drop's stage_to_prompt on client2 (squad of two, the host's site at X + POINT, its mirror, the
    Skyranger forced out), whose landing wait ends at client2's ConfirmLandingState OR a landing refusal (event_state
    coopClientBattleRefused, as in that test's landing_drop row); then client2 set_seed SEED + confirm_landing; both
    inBattle <= 60 s; the spine. Returns (bad, spine, squad)."""
    g2 = c2.ok({"cmd": "geo_state"})
    xb = next((b for b in g2.get("bases", []) if not b.get("coopBase") and not b.get("coopIcon")), None)
    sky = next((c for c in (xb or {}).get("crafts", []) if "SKYRANGER" in c.get("type", "") and not c.get("coop")), None)
    sb = next((b for b in c2.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    recs = {sid: G3E.srec(c2, sid) for sid in sids}
    sq = [sid for sid in sids if recs[sid].get("where") == "base" and recs[sid].get("recovery") == 0][:SQUAD]
    if not xb or not sky or len(sq) < SQUAD:
        capture_boot(f"gm3_resume: client2 base {xb and xb.get('name')}, Skyranger {sky}, squad {sq} "
                     "(want a base, a Skyranger and a squad of two)", host, c2)
    asg = [c2.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": False}) for sid in sids]
    asg += [c2.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": True}) for sid in sq]
    if not all(r.get("ok") for r in asg):
        capture_boot(f"gm3_resume: client2 craft_assign (SQ {sq}): {[r for r in asg if not r.get('ok')][:2]}", host, c2)
    point = [xb["lon"] + POINT[0], xb["lat"] + POINT[1]]
    site = host.cmd(dict(SITE, cmd="spawn_mission_site", lon=point[0], lat=point[1]))
    if not site.get("ok"):
        capture_boot(f"gm3_resume: host spawn_mission_site {site}", host, c2)
    ok, ms = wait(lambda: mirror(c2, point) is not None, MIRROR_S, 0.1)
    mir = mirror(c2, point)
    ev.update(SQ=sq, point=point, siteHost=site.get("site_id"), mirrorS=ms, siteClient=mir and mir.get("id"), sky=sky.get("id"))
    if not ok:
        capture_boot(f"gm3_resume: no coop mirror of host site {site.get('site_id')} on client2 within {MIRROR_S} s",
                     host, c2)
    cf = c2.cmd({"cmd": "craft_force", "craft_id": sky["id"], "status": "STR_OUT", "lon": xb["lon"] + CRAFT_AT[0],
                 "lat": xb["lat"] + CRAFT_AT[1], "dest": f"site:{mir['id']}", "fuel": 999999, "lowFuel": False})
    if not cf.get("ok"):
        capture_boot(f"gm3_resume: client2 craft_force {cf}", host, c2)
    ref0, how, t1 = event_state(c2).get("coopClientBattleRefused"), {}, time.time()

    def landing():
        if session.has_state(c2, "ConfirmLandingState"):
            how["v"] = "prompt"
            return True
        r = event_state(c2).get("coopClientBattleRefused")
        if r != ref0:
            how["v"] = f"refused {ref0} -> {r} ({event_state(c2).get('coopClientBattleRefusedLast')})"
            return True
        for gc in (host, c2):
            geo.drain_popups(gc, interest=geo.popup("ConfirmLandingState"))
            gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None
    ok, _s = wait(landing, LANDING_S)
    ev.update(landing=how.get("v"), landingS=round(time.time() - t1, 2), refused0=ref0)
    if not ok:
        capture_boot(f"gm3_resume: neither a ConfirmLandingState nor a refusal on client2 within {LANDING_S} s",
                     host, c2)
    if how["v"] != "prompt":
        return [f"client2's landing refused, no ConfirmLandingState ({how['v']}; host pvpBorrow {G3E.coop(host).get('pvpBorrow')})"], \
            False, sq
    pre = G3E.coop(host).get("pvpBorrow") or {}
    sd, cl = c2.cmd({"cmd": "set_seed", "seed": SEED}), c2.cmd({"cmd": "confirm_landing"})
    if not sd.get("ok") or not cl.get("ok"):
        capture_boot(f"gm3_resume: client2 set_seed {sd} / confirm_landing {cl}", host, c2)
    both, bs = wait(lambda: G3B.in_battle(host) and G3B.in_battle(c2), BOTH_IN["gm3_resume"])
    post = G3E.coop(host).get("pvpBorrow") or {}
    ref1 = event_state(c2).get("coopClientBattleRefused")
    ev.update(pvpBefore=pre, pvpAfter=post, bothInS=bs, refused1=ref1, client2StackAfterConfirm=stack(c2))
    bad = [f"client2 coopClientBattleRefused {ref0} -> {ref1} (want unchanged)"] if ref1 != ref0 else []
    bad += [f"host pvpBorrow.borrowed {pre.get('borrowed')!r} -> {post.get('borrowed')!r} (want +1)"] \
        if (post.get("borrowed") or 0) != (pre.get("borrowed") or 0) + 1 else []
    bad += [f"host pvpBorrow.{k} {post.get(k)!r} (want {w!r})" for k, w in (("targetKind", "site"), ("targetMirror", True))
            if post.get(k) != w]
    if not both:
        return bad + [f"inBattle host/client2 {[G3B.in_battle(host), G3B.in_battle(c2)]} {bs} s after the confirm"], False, sq
    try:
        session.briefings_to_battlescape(host, c2)
    except Exception as e:  # noqa: BLE001
        return bad + [f"session.briefings_to_battlescape raised: {str(e)[:300]}"], False, sq
    return bad, True, sq


def gm2_land(host, c2, ev):
    """G2F's to_battle, copied (the host's Skyranger and squad of two, its own site at b0 + (0.35, 0.10), forced out
    0.01 short; the landing prompt; host set_seed + confirm_landing); both inBattle <= 180 s; G2F's spine. Returns (bad,
    spine, squad)."""
    b0 = session._campaign_base0(host)
    sky = next((c for c in b0.get("crafts", []) if "SKYRANGER" in c.get("type", "")), None)
    sids = G2F.host_soldiers(host)
    if not sky or len(sids) < SQUAD:
        capture_boot(f"gm2_resume: no host Skyranger or fewer than {SQUAD} soldiers (sky {sky}, soldiers {sids})",
                     host, c2)
    for sid in sids:
        host.ok({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": False})
    for sid in sids[:SQUAD]:
        host.ok({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": True})
    site = host.cmd(dict(SITE, cmd="spawn_mission_site", lon=b0["lon"] + POINT[0], lat=b0["lat"] + POINT[1]))
    if not site.get("ok"):
        capture_boot(f"gm2_resume: host spawn_mission_site {site}", host, c2)
    host.ok({"cmd": "craft_force", "craft_id": sky["id"], "status": "STR_OUT", "lon": b0["lon"] + POINT[0] - 0.01,
             "lat": b0["lat"] + POINT[1], "dest": f"site:{site['site_id']}", "fuel": 999999, "lowFuel": False})

    def prompt():
        if session.has_state(host, "ConfirmLandingState"):
            return True
        for gc in (host, c2):
            geo.drain_popups(gc, interest=geo.popup("ConfirmLandingState"))
            gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None
    ok, ps = wait(prompt, LANDING_S, 0.5)
    if not ok:
        capture_boot(f"gm2_resume: no host ConfirmLandingState within {LANDING_S} s", host, c2)
    host.ok({"cmd": "set_seed", "seed": SEED})
    host.ok({"cmd": "confirm_landing"})
    both, bs = wait(lambda: G3B.in_battle(host) and G3B.in_battle(c2), BOTH_IN["gm2_resume"])
    ev.update(squad=sids[:SQUAD], site=site.get("site_id"), promptS=ps, bothInS=bs, stacksAfterConfirm=[stack(host), stack(c2)])
    if not both:
        return [f"inBattle host/client2 {[G3B.in_battle(host), G3B.in_battle(c2)]} {bs} s after the confirm"], False, sids[:SQUAD]
    sp_ok, sp_detail = G2F.spine(host, c2, ev)
    return ([] if sp_ok else [sp_detail]), sp_ok, sids[:SQUAD]


def row_resume(row, gm, x, ev):
    host, client = x["host"], x["client"]
    crash0, t_row = crash_set(), time.time()
    host0, client0, _xb = bring_up(host, client, gm, ev)
    geo_save(host, client, SAVE[row], ev)
    host, c2 = relaunch(x, ev)
    ok = resume(host, c2, SAVE[row], ev)
    mode_role_cells(row, gm, ok, ev, host0, client0)
    spine, cen = False, None
    if not ok:
        block([f"{row}-land", f"{row}-seats"], "the resume never reached session up")
    else:
        bad, spine, sq = (gm3_land if gm == 3 else gm2_land)(host, c2, ev)
        cell(f"{row}-land", not bad, "; ".join(bad) or ("client2's prompt without a refusal; its confirm borrowed once (site, mirror); "
                                                       "both inBattle; spine passed" if gm == 3 else
                                                       "both inBattle after the host's confirm; spine passed"))
        if not spine:
            block([f"{row}-seats"], f"no {'borrowed ' if gm == 3 else ''}battle ({row}-land)")
        else:
            cen = [census(host), census(c2)]
            sbad = seats_bad(cen[0], cen[1], 1 if gm == 3 else 0, 0 if gm == 3 else 1, sq)
            cell(f"{row}-seats", not sbad, "; ".join(sbad) or f"census equal on both ({len(cen[0])} units): faction 0 seat "
                 f"{1 if gm == 3 else 0} (the squad), faction 1 seat {0 if gm == 3 else 1} without AI, no other faction")
            bh = battle_state(host)
            ev.update(mapFingerprint=[bh.get("mapFingerprint"), battle_state(c2).get("mapFingerprint")], turn=bh.get("turn"))
    common(row, host, c2, crash0, spine)
    ev.update(census=cen, client2Stack=stack(c2), wall=round(time.time() - t_row, 1))


def run_boot(tag, label, row, gm):
    """One boot: host and client, the row, then every machine shut down."""
    BOOT["tag"] = label
    x = {"tag": tag, "host": GameClient("host", None, make_user_dir(tag + "_host")),
         "client": GameClient("client", None, make_user_dir(tag + "_client")), "client2": None}
    ev = {}
    try:
        row_resume(row, gm, x, ev)
    except FixtureMiss as e:
        block(ROWS[row], f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        ev["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"[ERROR] boot {label}: {ev['error']}", flush=True)
        block(ROWS[row], f"error {ev['error']}")
    finally:
        evidence(row, ev)
        row_verdict(row, ROWS[row])
        for gc in (x["client2"], x["client"], x["host"]):
            try:
                if gc is not None and gc.proc is not None:
                    gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)


def main():
    t0 = time.time()
    run_boot("campaign_resume_roles_gm3", "gm3_boot", "gm3_resume", 3)
    run_boot("campaign_resume_roles_gm2", "gm2_boot", "gm2_resume", 2)
    allc = ROWS["gm3_resume"] + ROWS["gm2_resume"]
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== test_campaign_resume_roles: {len(RESULTS) - len(fails)}/{len(allc)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (FIX cell)' if n in FIX else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(allc) else 2)


if __name__ == "__main__":
    main()
