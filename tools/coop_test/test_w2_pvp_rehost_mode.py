"""W2-H46 - test_w2_pvp_rehost_mode.py: a resumed PvP campaign keeps its mode after the host's DISCONNECT and a second START HOST
(L-SC5-1; R-H46-0; QC-16 (a), QC4A-1 (a), VL-C4A-1). A gm3 campaign (host = the aliens) and a gm2 campaign (host = X-COM) are each
saved on the geoscape, both processes end, the host loads the save through the real host window, presses START HOST, the REAL
DISCONNECT button and START HOST again, a fresh client2 joins and the host presses RESUME: both machines must play the save's PvP mode
with both roles, and the next host save must keep it. Row L5 is the gm2 mid-battle campaign rejoin (L-SC5-5), a control passing today.
L5-phase1 reads client2's phase-one world while client2 holds its battle_accept (TEST-ONLY hold_battle_accept; F24289).
Spec: docs rewrite/prompts/w2h46_pvp_rehost_mode.md ((f) rows D3, D2, L5; QH46-1 .. QH46-7 (a); F17080-F17089, F17200-F17215); TASK 0
pins: docs rewrite/w2h46-task0/sa/CONSTANTS.md (boots a3, a2, a5 unchanged; c3, c2 with E1). Key "49122", dirs w2h46_<row>_host / _client /
_client2; one boot per row. D rows (T0-2 (1)-(13)): bring-up (PF.start_pvp_campaign; mode and noBases pair are preconditions); save1
(save_game); both end, the host respawns on ITS dir and client2 on an EMPTY dir; load_save_menu; START 1 by host_menu_host visibility 0
(R-D250-SC4A-1); the REAL DISCONNECT by click_widget once shown (the lobby_disconnect lever only as the logged fallback, failing -leave);
START 2 the same way; client2 join_tcp with guarded profile_ok; RESUME (resume_campaign_via_button, resumeAck, press_back_when_shown
60 / 62); SETTLE_S; views; save2; common. A bring-up, save1, relaunch, load or START 1 miss is a FIXTURE-STOP: ONE "CAPTURE <row>:"
line, the boot's remaining cells FAIL "boot"; a later precondition miss ends its row ("blocked: <why>"); every row runs after a failure.
Cells (one PASS / FAIL line each, one EVIDENCE and one ROW line per row): D3 (gm3) and D2 (gm2): -start1, -leave, -start2, -mode, -role,
-save, -common; L5 (gm2 rejoin): L5-pause, L5-phase1, L5-resume, L5-end, L5-common.
RED (unchanged build; TASK 0 a3 / a2 / a5): 7/19 FAIL - D3-start2, D3-mode, D3-role, D3-save, D2-start2, D2-mode, D2-save. GREEN: 19/19.
WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_w2_pvp_rehost_mode.py
"""
import contextlib
import glob
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import event_state  # noqa: E402
import geo  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import test_d250_campaign_battle_gm2 as G2F  # noqa: E402
import test_w2_campaign_rejoin as CR  # noqa: E402
import test_d250_campaign_resume_roles as RR  # noqa: E402  (pure helpers only)
import test_d250_campaign_resume_gm2 as RG2  # noqa: E402  (to_battle, snap, win_cell, hash_res)

# ----- TASK 0 pins (docs rewrite/w2h46-task0/sa/CONSTANTS.md) -----
KEY = "49122"
SAVE = {"D3": "w2h46_d3.sav", "D2": "w2h46_d2.sav"}
STUB, STUB_FUNDS = RR.STUB, RR.STUB_FUNDS          # RR's FX4A-11 stub: one unplaced, unnamed, empty base; funds 1000
RED = {"D3-start2", "D3-mode", "D3-role", "D3-save", "D2-start2", "D2-mode", "D2-save"}
# ----- bounds (spec PINNED SETUP VALUES; TASK 0 measured 0.05 / 0.05 / 1.56 / 3.61 / - / 0.0 / 0.2 / 2.4 / 0.05 s) -----
DISC_S, LOBBY_S, JOIN_S, RESUME_S, SETTLE_S, SAVE_S, PAUSE_S, ACK_S, END_S = 15, 30, 120, 120, 5, 10, 30, 135, 10
ROWS = {"D3": ["D3-start1", "D3-leave", "D3-start2", "D3-mode", "D3-role", "D3-save", "D3-common"],
        "D2": ["D2-start1", "D2-leave", "D2-start2", "D2-mode", "D2-role", "D2-save", "D2-common"],
        "L5": ["L5-pause", "L5-phase1", "L5-resume", "L5-end", "L5-common"]}
BOOT = {"tag": "D3"}
view, census, capture, dlg = RR.view, RR.census, RR.capture, CR.dlg
RESULTS = []          # (cell, ok, detail)

class FixtureMiss(Exception):
    """a FIXTURE-STOP: every remaining cell of the boot FAILs boot"""

class RowEnd(Exception):
    """a precondition miss: the row's later cells FAIL blocked"""

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

def capture_boot(err, *machines):
    print(f"CAPTURE {BOOT['tag']}: {json.dumps(capture(err, *machines), sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)

def stack(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:  # noqa: BLE001
        return [f"probe failed {e!r}"[:120]]

def top(gc):
    return (stack(gc) or [None])[-1]

def crash_set():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))

def wait(pred, timeout, interval=0.25):     # the capture's wait: a probe that raises is a False sample; returns (ok, seconds)
    t0 = time.time()
    while time.time() - t0 < timeout:
        with contextlib.suppress(Exception):
            if pred():
                return True, round(time.time() - t0, 2)
        time.sleep(interval)
    return False, round(time.time() - t0, 2)

def gv(gc):
    c = gc.cmd({"cmd": "get_coop"})
    return {k: c.get(k) for k in ("gamemode", "noBases", "serverOwner", "lobbyMode", "resumeAck", "localSeat", "clientName", "inBattle")}

def soft_view(gc):     # RR.view without raising (phase one probes a client2 still loading)
    c, g = gc.cmd({"cmd": "get_coop"}), gc.cmd({"cmd": "geo_state"})
    return {"gamemode": c.get("gamemode"), "noBases": c.get("noBases"), "funds": g.get("funds"), "realBases": RR.rbases(g)}

def roster_size(gc):
    return sum(len(b.get("soldiers", [])) for b in gc.cmd({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag"))

def profile_press(host, c2, rec, t0):
    """CR.rejoin's guard (R-L2-A-2): profile_ok only on a top-state Profile; client2's only once its load wait 52 is gone."""
    for gc in (host, c2):
        if top(gc) == "Profile" and (gc is host or dlg(c2).get("code") != 52):
            rec.append([gc.name, round(time.time() - t0, 2), gc.cmd({"cmd": "profile_ok"}).get("ok")])

def bring_up(host, client, gm, ev):
    """RR.bring_up copied with KEY (FX4A-2): mode [g, g], the noBases pair and (gm3) the client's real base + Skyranger are preconditions."""
    host.spawn(); host.connect(); client.spawn(); client.connect()
    try:
        ev["lobbyGamemode"] = PF.start_pvp_campaign(host, client, KEY, alien_player="host" if gm == 3 else "client")
    except Exception as e:  # noqa: BLE001
        capture_boot(f"PF.start_pvp_campaign: {e}", host, client)
    hv, cv = view(host), view(client)
    xb = next((b for b in client.ok({"cmd": "geo_state"}).get("bases", []) if not b.get("coopBase") and not b.get("coopIcon")), None)
    sky = next((c for c in (xb or {}).get("crafts", []) if "SKYRANGER" in c.get("type", "") and not c.get("coop")), None)
    ev.update(HOST0=hv, CLIENT0=cv)
    want = (True, False) if gm == 3 else (False, True)
    if [hv["gamemode"], cv["gamemode"]] != [gm, gm] or (hv["noBases"], cv["noBases"]) != want:
        capture_boot(f"bring-up preconditions (FX4A-2): gamemode {[hv['gamemode'], cv['gamemode']]} (want [{gm}, {gm}]), noBases host / "
                     f"client {[hv['noBases'], cv['noBases']]} (want {list(want)})", host, client)
    if gm == 3 and (not xb or not sky):
        capture_boot(f"the client has no real base / Skyranger (base {xb and xb.get('name')}, sky {sky})", host, client)
    geo.slow_clock(host, client)
    return hv, cv

def geo_save(host, client, name, ev, key):
    """RR.geo_save copied (FX4A-3): save_game lever, the file within SAVE_S, RR.save_keys; a save1 miss is a FIXTURE-STOP."""
    path = os.path.join(host.user_dir, "xcom1", name)
    r = host.cmd({"cmd": "save_game", "file": name})
    ok, secs = wait(lambda: os.path.exists(path) and os.path.getsize(path) > 0, SAVE_S, 0.2)
    time.sleep(1.0)
    ev[key] = {"file": name, "reply": r, "s": secs, "keys": RR.save_keys(path) if ok else None}
    if (not r.get("ok") or not ok) and key == "save1":
        capture_boot(f"host save_game {name}: {r}, file present {os.path.exists(path)} (FX4A-3)", host, client)
    return bool(r.get("ok") and ok)

def relaunch(x, ev):
    """RR.relaunch copied (FX4A-4): both shut down; the host respawned on ITS dir; client2 on an EMPTY dir. Returns (host, client2)."""
    t0 = time.time()
    try:
        x["client"].shutdown(); x["host"].shutdown()
        host = x["host"] = GameClient("host", None, x["host"].user_dir)
        c2 = x["client2"] = GameClient("client2", None, make_user_dir(x["tag"] + "_client2"))
        host.spawn(); host.connect(); c2.spawn(); c2.connect()
    except Exception as e:  # noqa: BLE001
        capture_boot(f"relaunch (FX4A-4): {type(e).__name__}: {str(e)[:300]}", x["host"], x.get("client2"))
    ev.update(relaunchS=round(time.time() - t0, 2), client2DirAtSpawn=session.save_files(c2.user_dir))
    return host, c2

def start_host(host, ev, key):
    """START HOST through the real host window (host_menu_host visibility 0 -> HostMenu::hostTCPGame; R-D250-SC4A-1)."""
    r = host.cmd({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv", "port": KEY, "player": "HostPlayer"})
    ok, s = wait(lambda: session.has_state(host, "LobbyMenu"), LOBBY_S)
    ev[key] = {"reply": r, "lobby": ok, "s": s, "stack": stack(host), "get_coop": gv(host),
               "lobbyMode": host.cmd({"cmd": "lobby_state"}).get("lobbyMode")}
    return ok

def disconnect(host, ev):
    """the REAL DISCONNECT once a player could press it (shown: POPUP_BOTH window); lobby_disconnect only as the logged fallback."""
    seen = {}

    def ready():
        r = host.cmd({"cmd": "list_widgets"})
        w = next((x for x in r.get("widgets", []) if x.get("text") == "DISCONNECT"), None) or {}
        seen.update(state=r.get("state"), visible=w.get("visible"), hidden=w.get("hidden"))
        return "LobbyMenu" in str(r.get("state")) and w.get("visible") is True and w.get("hidden") is False
    rok, rs = wait(ready, DISC_S, 0.1)
    t0, click = time.time(), host.cmd({"cmd": "click_widget", "match": "DISCONNECT"})
    clicked, cs = wait(lambda: top(host) == "HostMenu", DISC_S, 0.05)
    d, back = {"ready": [rok, rs, seen], "click": click, "path": "click_widget", "s": cs}, clicked
    if not clicked:
        d.update(path="lobby_disconnect (fallback)", stackAtTimeout=stack(host), lever=host.cmd({"cmd": "lobby_disconnect"}))
        back, _s = wait(lambda: top(host) == "HostMenu", DISC_S, 0.05)
        d["s"] = round(time.time() - t0, 2)
    d.update(topHostMenu=back, stack=stack(host), get_coop=gv(host), hasSave=host.cmd({"cmd": "world_state"}).get("has_save"))
    ev["DISCONNECT"] = d
    return clicked, back

def resume(host, c2, ev):
    """client2 joins <= JOIN_S; RESUME (button, resumeAck, 60 / 62 pressed); both GeoscapeState <= RESUME_S; SETTLE_S. '' or why not."""
    t_j, prof, bnb = time.time(), [], []
    ev["join"] = c2.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    def joined():
        profile_press(host, c2, prof, t_j)
        return session.has_state(c2, "LobbyMenu") and host.cmd({"cmd": "get_coop"}).get("clientName") == "ClientPlayer"
    ok, s = wait(joined, JOIN_S)
    ev.update(joinS=s, profileOk=prof)
    if not ok:
        return f"client2 not in the resume lobby (or host clientName not ClientPlayer) within {JOIN_S} s"
    def tick():
        s2 = stack(c2)
        bnb.extend([] if "BuildNewBaseState" not in s2 or bnb else [round(time.time() - t_j, 2)])
        profile_press(host, c2, prof, t_j)
        return top(host), (s2[-1] if s2 else None)
    t_r = time.time()
    try:
        session.resume_campaign_via_button(host, "ClientPlayer")
    except Exception as e:  # noqa: BLE001
        return f"resume_campaign_via_button: {str(e)[:200]}"
    ack, ev["ackS"] = wait(lambda: tick() and host.cmd({"cmd": "get_coop"}).get("resumeAck") is True, RESUME_S)
    shown, ev["shownS"] = wait(lambda: tick()[0] == "CoopState" and dlg(host).get("code") in (60, 62)
                               and dlg(host).get("backVisible") is True, RESUME_S)
    try:
        ev["press"] = session.press_back_when_shown(host, "host RESUME", codes=(60, 62), timeout=10)
    except Exception as e:  # noqa: BLE001
        ev["press"] = {"error": str(e)[:300]}
    geo2, _s = wait(lambda: tick() == ("GeoscapeState", "GeoscapeState"), RESUME_S)
    ev["bothGeoS"], t_s = round(time.time() - t_r, 2), time.time()
    while geo2 and time.time() - t_s < SETTLE_S:
        tick()
        time.sleep(0.25)
    ev.update(client2BuildNewBaseState=bnb, tops=[stack(host), stack(c2)])
    if not (ack and shown and geo2):
        ev["resumeCapture"] = capture("resume", host, c2)
        return f"resumeAck {ack}, host 60 / 62 shown {shown}, both GeoscapeState {geo2} within {RESUME_S} s"
    return ""

def common(row, host, c2, crash0, zero_disk=True, hres=None):
    """RR.common without a spine: desyncSeen false on both, 0 new crash files; D rows client2 zero-disk, L5 hash_now full after RESUME."""
    eh, ec = event_state(host), event_state(c2)
    new = sorted(crash_set() - crash0)
    bad = [f"desyncSeen host {eh.get('desyncSeen')!r} client2 {ec.get('desyncSeen')!r} (want false on both)"] \
        if eh.get("desyncSeen") is not False or ec.get("desyncSeen") is not False else []
    bad += [f"{len(new)} new crash file(s) since the row's start (first {os.path.basename(new[0])})"] if new else []
    if zero_disk:
        try:
            session.assert_client_zero_disk(c2.user_dir)
        except AssertionError as e:
            bad.append(f"client2 zero-disk: {str(e)[:300]}")
    bad += [f"hash_now full after RESUME: {hres}"] if not zero_disk and hres != "EQUAL" else []
    cell(f"{row}-common", not bad, "; ".join(bad) or "desyncSeen false on host and client2, 0 new crash files, "
         + ("client2 zero-disk" if zero_disk else "hash_now full EQUAL after RESUME"))
    return {"desyncSeen": [eh.get("desyncSeen"), ec.get("desyncSeen")], "newCrash": [os.path.basename(p) for p in new]}

def row_d(row, gm, x, ev):
    host, client = x["host"], x["client"]
    crash0, t_row, cells = crash_set(), time.time(), ROWS[row]
    host0, client0 = bring_up(host, client, gm, ev)
    geo_save(host, client, SAVE[row], ev, "save1")
    host, c2 = relaunch(x, ev)
    host.cmd({"cmd": "load_save_menu", "file": SAVE[row]})
    ok, _s = wait(lambda: session.has_state(host, "HostMenu"), LOBBY_S)
    ev["afterLoad"] = {"stack": stack(host), "get_coop": gv(host)}
    if not ok or ev["afterLoad"]["get_coop"]["gamemode"] != gm:
        capture_boot(f"load_save_menu: HostMenu {ok}, gamemode {ev['afterLoad']['get_coop']['gamemode']} (want {gm})", host, c2)
    if not start_host(host, ev, "START1"):
        capture_boot(f"START 1: no LobbyMenu within {LOBBY_S} s ({ev['START1']})", host, c2)
    s1 = ev["START1"]
    cell(f"{row}-start1", s1["lobbyMode"] == 2 and s1["get_coop"]["gamemode"] == gm, f"after START 1 lobbyMode {s1['lobbyMode']} (want 2), "
         f"host gamemode {s1['get_coop']['gamemode']} (want {gm})")
    try:
        clicked, back = disconnect(host, ev)
        d = ev["DISCONNECT"]
        lbad = [] if clicked else [f"the click reached no top HostMenu in {DISC_S} s ({d.get('stackAtTimeout')}; fallback lever: {back})"]
        lbad += [] if d["hasSave"] is True else [f"world_state.has_save {d['hasSave']!r} (want true)"]
        lbad += [] if d["get_coop"]["serverOwner"] is False else [f"serverOwner {d['get_coop']['serverOwner']!r} (want false)"]
        cell(f"{row}-leave", not lbad, "; ".join(lbad) or f"the DISCONNECT click -> top HostMenu {d['s']} s, has_save true, serverOwner "
             f"false (host gamemode {d['get_coop']['gamemode']}, evidence)")
        if not back:
            raise RowEnd("no top HostMenu after the DISCONNECT")
        if not start_host(host, ev, "START2"):
            cell(f"{row}-start2", False, f"no LobbyMenu within {LOBBY_S} s of START 2 (stack {ev['START2']['stack']})")
            raise RowEnd("no resume lobby after START 2")
        s2 = ev["START2"]
        cell(f"{row}-start2", s2["lobbyMode"] == 2 and s2["get_coop"]["gamemode"] == gm, f"after START 2 lobbyMode {s2['lobbyMode']} "
             f"(want 2), host gamemode {s2['get_coop']['gamemode']} (want {gm})")
        why = resume(host, c2, ev)
        if why:
            raise RowEnd(f"the resume never reached session up ({why})")
        hv, cv = view(host), view(c2)
        ev["afterResume"] = {"host": hv, "client2": cv}
        mbad = [f"{nm} gamemode {v['gamemode']!r} (want {gm})" for nm, v in (("host", hv), ("client2", cv)) if v["gamemode"] != gm]
        cell(f"{row}-mode", not mbad, "; ".join(mbad) or f"get_coop.gamemode {gm} on host and client2 after the resume")
        if gm == 3:
            want = (("host", hv, "noBases", True), ("host", hv, "funds", STUB_FUNDS), ("host", hv, "realBases", host0["realBases"]),
                    ("client2", cv, "noBases", False), ("client2", cv, "realBases", client0["realBases"]))
        else:
            want = (("client2", cv, "noBases", True), ("client2", cv, "funds", STUB_FUNDS), ("client2", cv, "realBases", STUB),
                    ("host", hv, "noBases", False), ("host", hv, "realBases", host0["realBases"]))
        rbad = [f"{nm} {k} {v[k]!r} (want {w!r})" for nm, v, k, w in want if v[k] != w]
        rbad += [f"client2 BuildNewBaseState at {ev['client2BuildNewBaseState']} s"] if ev["client2BuildNewBaseState"] else []
        cell(f"{row}-role", not rbad, "; ".join(rbad) or "; ".join(f"{nm} {k} {v[k]!r}" for nm, v, k, _w in want)
             + f" (HOST0's / CLIENT0's / the stub as wanted); no client2 BuildNewBaseState in SETTLE_S {SETTLE_S} s")
        saved = geo_save(host, c2, f"w2h46_{row.lower()}_after.sav", ev, "save2")
        keys = ev["save2"]["keys"] or {}
        mode = [v for k, v in sorted(keys.items()) if k.startswith("coop_gamemode@")]
        nob = [v for k, v in sorted(keys.items()) if k.startswith("no_bases@")]
        sbad = [] if saved else [f"no save2 file within {SAVE_S} s ({ev['save2']['reply']})"]
        sbad += [] if not saved or (mode, nob) == ([gm], [gm == 3]) else [f"save2 coop_gamemode {mode} no_bases {nob} (want [{gm}] / [{gm == 3}])"]
        cell(f"{row}-save", not sbad, "; ".join(sbad) or f"save2 coop_gamemode {gm}, no_bases {str(gm == 3).lower()} ({sorted(keys)})")
    except RowEnd as e:
        block(cells[:-1], str(e))
    ev["common"] = common(row, host, c2, crash0)
    ev["wall"] = round(time.time() - t_row, 1)

def seat1(gc):
    return sorted([u.get("id"), u.get("faction"), u.get("hasAI"), u.get("isOut")] for u in (CR.bs_raw(gc).get("units") or [])
                  if u.get("coop") == 1)

def row_l5(x, ev):
    """the capture's C3 (L-SC5-5): PF, RG2.to_battle + G2F.spine, client leaves, PAUSE, client2 rejoins (CR.rejoin), RESUME 62, win."""
    host, client = x["host"], x["client"]
    crash0, t_row, hres = crash_set(), time.time(), "not reached"
    host0, _c0 = bring_up(host, client, 2, ev)
    geo0 = {"realBases": host0["realBases"], "roster": roster_size(host)}
    RG2.BOOT["tag"] = BOOT["tag"]
    both, detail, squad = RG2.to_battle(host, client, ev, False)
    if not both:
        capture_boot(f"L5 landing (FX4A-6): {detail}", host, client)
    sp_ok, sp_detail = G2F.spine(host, client, ev)
    b = {"host": RG2.snap(host), "client": RG2.snap(client), "seat1": seat1(host), "census": census(host)}
    ev.update(squad=squad, BEFORE=b)
    if not sp_ok or b["host"]["coopGamemode"] != 2 or not b["seat1"] or any(u[1] != 1 or u[2] is not False for u in b["seat1"]):
        capture_boot(f"L5 landing preconditions: spine {sp_detail}; coopGamemode {b['host']['coopGamemode']}; seat-1 {b['seat1']}", host, client)
    b0, n_h = b["host"]["battleId"], len(CR.log(host))
    try:
        ev["leave"] = client.cmd({"cmd": "disconnect_to_menu"})
        ok, _s = wait(lambda: top(client) == "MainMenuState", 60)
        if not ok:
            capture_boot(f"L5: the client's disconnect_to_menu reached no MainMenuState within 60 s ({stack(client)})", host, client)
        seen = {}
        def paused():
            seen.update(stack=stack(host), battle=CR.auth(host), dialog=dlg(host))
            return seen["dialog"].get("code") == 62 and seen["dialog"].get("backVisible") is False \
                and seen["battle"].get("peerAbsent") is True and seen["stack"][-2:] == ["BattlescapeState", "CoopState"]
        ok, s = wait(paused, PAUSE_S)
        ev["PAUSE"] = dict(seen, s=s)
        cell("L5-pause", ok, f"host code 62, backVisible false, peerAbsent true, stack ends [BattlescapeState, CoopState] {s} s after the leave"
             if ok else f"not within {PAUSE_S} s: {json.dumps(seen, sort_keys=True, default=str)[:400]}")
        if not ok:
            raise RowEnd("no host PAUSE")
        client.shutdown()
        c2 = x["client2"] = GameClient("client2", None, make_user_dir(x["tag"] + "_client2"))
        c2.spawn(); c2.connect()
        # F24289: client2's world-without-battle phase lasts ~0.24 s since CIT-G3, shorter than one 0.25 s poll. client2 holds its
        # battle_accept (TEST-ONLY hold_battle_accept, W2-H82 L2) so the host streams no battle until phase one is read, then releases it.
        hold = {"arm": c2.cmd({"cmd": "hold_battle_accept", "on": True})}
        t_j, prof, bnb, p1 = time.time(), [], [], {}
        ev["join"] = c2.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
        def sample():
            s2 = stack(c2)
            bnb.extend([] if "BuildNewBaseState" not in s2 or bnb else [round(time.time() - t_j, 2)])
            profile_press(host, c2, prof, t_j)
            return s2
        def phase_one():   # client2's FIRST world, read once its battle_accept is stashed (the offer is in, no battle streams)
            s2 = sample()
            w, held = c2.cmd({"cmd": "world_state"}), c2.cmd({"cmd": "hold_battle_accept"}).get("held")
            if held and w.get("has_save") and not w.get("has_battle") and "BattlescapeState" not in s2:
                v = soft_view(c2)                                                                        # (still no battle after the read)
                p1.update(t=round(time.time() - t_j, 2), view=v, stack=s2) if not c2.cmd({"cmd": "world_state"}).get("has_battle") else None
            return bool(p1)
        try:
            _ok, hold["phaseOneS"] = wait(phase_one, ACK_S)
        finally:
            hold["release"] = c2.cmd({"cmd": "hold_battle_accept", "on": False})
        def acked():
            sample()
            return CR.coop(host).get("resumeAck") is True and CR.auth(host).get("peerAbsent") is False
        acked_ok, s = wait(acked, ACK_S)
        ev.update(ackS=s, profileOk=prof, phaseOne=p1, client2BuildNewBaseState=list(bnb), hold=hold)
        v1 = p1.get("view") or {}
        pbad = [] if hold["arm"].get("armed") is True else [f"client2 hold_battle_accept not armed: {hold['arm']}"]
        pbad += [] if p1 else ["no client2 sample with a world and no battle before the offer"]
        pbad += [] if hold["release"].get("sent") is True else [f"client2 hold_battle_accept release sent no battle_accept: {hold['release']}"]
        pbad += [f"client2 {k} {v1.get(k)!r} (want {w!r})" for k, w in (("gamemode", 2), ("noBases", True), ("realBases", STUB), ("funds", STUB_FUNDS))
                 if p1 and v1.get(k) != w]
        pbad += [f"client2 BuildNewBaseState at {bnb} s"] if bnb else []
        cell("L5-phase1", not pbad, "; ".join(pbad) or f"client2's first world ({p1['t']} s): gamemode 2, noBases true, the stub, funds "
             f"{STUB_FUNDS}; no BuildNewBaseState at any sample")
        if not acked_ok:
            ev["ackCapture"] = capture("rejoin", host, c2)
            raise RowEnd(f"no host resumeAck true with peerAbsent false within {ACK_S} s")
        shown, _s = wait(lambda: (profile_press(host, c2, prof, t_j) or True) and top(host) == "CoopState"
                         and dlg(host).get("code") == 62 and dlg(host).get("backVisible") is True, 60)
        try:
            ev["press"] = session.press_back_when_shown(host, "host RESUME", codes=(62,), timeout=10)
        except Exception as e:  # noqa: BLE001
            ev["press"] = {"error": str(e)[:300]}
        tops, ts = wait(lambda: top(host) == "BattlescapeState" and top(c2) == "BattlescapeState", 60)
        a = {"host": RG2.snap(host) if tops else None, "client2": RG2.snap(c2) if tops else None, "seat1": seat1(host),
             "seat1Client2": seat1(c2), "census": census(host) if tops else None, "census2": census(c2) if tops else None,
             "OFFER": CR.since(host, n_h, CR.OFFER), "REFUSED": CR.since(host, n_h, CR.REFUSED), "topsS": ts, "shown": shown}
        ev["AFTER"] = a
        rbad = [] if tops else [f"tops host / client2 {[top(host), top(c2)]} (want BattlescapeState on both within 60 s of RESUME)"]
        if tops:
            rbad += [f"{k} host / client2 {[a['host'][k], a['client2'][k]]} (want {w})" for k, w in (("battleId", b0), ("coopGamemode", 2))
                     if a["host"][k] != w or a["client2"][k] != w]
            rbad += [f"client2 localSeat {a['client2']['localSeat']!r} (want 1)"] if a["client2"]["localSeat"] != 1 else []
            rbad += [f"census host != client2 ({a['census']} / {a['census2']})"] if a["census"] != a["census2"] else []
            hres = ev["hashAfterResume"] = RG2.hash_res(host, c2)
        rbad += [f"seat-1 set host {a['seat1']} / client2 {a['seat1Client2']} (want {b['seat1']})"] \
            if a["seat1"] != b["seat1"] or a["seat1Client2"] != b["seat1"] else []
        rbad += [f"OFFER {a['OFFER']} (want one line reading battleId={b0},)"] if len(a["OFFER"]) != 1 or f"battleId={b0}," not in a["OFFER"][0] else []
        rbad += [f"REFUSED {a['REFUSED']} (want none)"] if a["REFUSED"] else []
        cell("L5-resume", not rbad, "; ".join(rbad) or f"both tops BattlescapeState {ts} s after RESUME; battleId {b0} unchanged; battle "
             f"coopGamemode 2; client2 localSeat 1; seat-1 set unchanged on host and client2; census equal; OFFER 1, REFUSED 0")
        if not tops:
            raise RowEnd("the battle did not resume on both")
        wv, buf, n_w = {}, io.StringIO(), len(RG2.RESULTS)
        try:
            with contextlib.redirect_stdout(buf):      # RG2's own "P3-win" line goes to EVIDENCE, its verdict to L5-end
                RG2.win_cell(host, c2, wv)
        except Exception as e:  # noqa: BLE001
            wv["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        won = RG2.RESULTS[-1] if len(RG2.RESULTS) > n_w else ("P3-win", False, f"no verdict ({wv.get('error')})")
        ev["WIN"] = dict(wv, printed=buf.getvalue().strip()[:600])
        s2s = []
        wait(lambda: s2s.append(stack(c2)), END_S)          # client2's stack sampled for END_S
        cv, hv = soft_view(c2), soft_view(host)
        ev["END"] = {"client2": cv, "client2Top": top(c2), "host": hv, "hostRoster": roster_size(host), "geo0": geo0}
        ebad = [] if won[1] else [f"the X-COM win (RG2.win_cell): {won[2]}"]
        ebad += [f"client2 top {top(c2)!r} (want GeoscapeState)"] if top(c2) != "GeoscapeState" else []
        ebad += [f"client2 {k} {cv[k]!r} (want {w!r})" for k, w in (("gamemode", 2), ("noBases", True), ("realBases", STUB)) if cv[k] != w]
        ebad += ["client2 BuildNewBaseState in END_S"] if any("BuildNewBaseState" in s for s in s2s) else []
        ebad += [f"host real bases {hv['realBases']} / roster {ev['END']['hostRoster']} (want {geo0})"] \
            if hv["realBases"] != geo0["realBases"] or ev["END"]["hostRoster"] != geo0["roster"] else []
        cell("L5-end", not ebad, "; ".join(ebad) or "both left the debriefing after the X-COM win; client2 top GeoscapeState, gamemode 2, "
             f"noBases true, the stub, no BuildNewBaseState in {END_S} s; host real bases and roster == before the landing")
    except RowEnd as e:
        block(ROWS["L5"][:-1], str(e))
    ev["common"] = common("L5", host, x.get("client2") or client, crash0, zero_disk=False, hres=hres)
    ev["wall"] = round(time.time() - t_row, 1)

def run_boot(tag, row, fn):
    """One boot: host and client, the row, then every machine shut down."""
    BOOT["tag"] = row
    x = {"tag": tag, "host": GameClient("host", None, make_user_dir(tag + "_host")),
         "client": GameClient("client", None, make_user_dir(tag + "_client")), "client2": None}
    ev = {}
    try:
        fn(x, ev)
    except (FixtureMiss, RG2.FixtureMiss) as e:
        block(ROWS[row], f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        ev["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"[ERROR] boot {row}: {ev['error']}", flush=True)
        block(ROWS[row], f"error {ev['error']}")
    finally:
        evidence(row, ev)
        row_verdict(row, ROWS[row])
        for gc in (x["client2"], x["client"], x["host"]):
            try:
                if gc is not None and gc.proc is not None and gc.proc is not getattr(gc, "_shutdown_proc", None):
                    gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)

def main():
    t0 = time.time()
    run_boot("w2h46_d3", "D3", lambda x, ev: row_d("D3", 3, x, ev))
    run_boot("w2h46_d2", "D2", lambda x, ev: row_d("D2", 2, x, ev))
    run_boot("w2h46_l5", "L5", row_l5)
    allc = ROWS["D3"] + ROWS["D2"] + ROWS["L5"]
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== W2-H46 resumed PvP campaign mode after the host's DISCONNECT and START HOST: {len(RESULTS) - len(fails)}/{len(allc)} "
          f"cells PASS, wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (expected red)' if n in RED else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(allc) else 2)

if __name__ == "__main__":
    main()
