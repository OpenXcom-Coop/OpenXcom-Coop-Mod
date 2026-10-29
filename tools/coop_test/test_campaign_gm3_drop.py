"""test_campaign_gm3_drop.py: gm3 PvP campaign drops (host = the aliens, client = X-COM): the X-COM player drops
while its landing waits and rejoins on the geoscape, the alien host leaves a borrowed battle, and the X-COM player drops during the
borrowed battle's start.

Boot landing_boot: gm3, lobby key 48034, dirs campaign_gm3_drop_landing_host / _client / _client2. Boot start_boot
(after landing_boot): key 48034, dirs campaign_gm3_drop_start_host / _client. Bring-up in each:
PF.start_pvp_campaign(alien_player="host"); HOST0 / CLIENT0; gamemode 3 on both, host noBases true and client noBases
false are preconditions; geo.slow_clock. A bring-up or staging miss is a setup failure: ONE "CAPTURE landing_boot:" /
"CAPTURE start_boot:" line and every remaining cell of that boot FAILs "boot".
Rows and cells (one PASS / FAIL line per cell, one EVIDENCE line and one ROW line per row; a row whose precondition was never reached
FAILs each of its cells "blocked: <why>"):
  landing_drop (landing_boot) the X-COM player drops while its landing waits, then rejoins: stage_to_prompt; host
     open_screen stores; client confirms; host pvpBorrow pending + armed; BORROW0; client.kill(); host dialog 62;
     at_drop; the geoscape rejoin (host geo_clean, client2 without a CoopState / LoadGameState, its top GeoscapeState
     or its craft's arrival screen); at_rejoin; client2's landing (refusals counted from client2's value right after
     its join_tcp).
     request_ended (at_drop: pending false, requestDropped 1), roles_kept (at_drop / at_rejoin: host gamemode 3,
     noBases true, funds / real bases == HOST0; at_rejoin: client2 gamemode 3, noBases false), rejoined_landing
     (client2's prompt without a refusal; its confirm borrows once; both in battle; spine), landing_drop_clean
     (desyncSeen false, 0 new crash files, hash EQUAL after the spine when reached).
  host_leaves (landing_boot, on rejoined_landing's battle) the alien host leaves a borrowed battle: host
     disconnect_to_menu; then client2 must be told "Server connection lost" and reach the main menu, as in
     test_campaign_rejoin's host-leaves row. client_told, both_at_menu, host_leaves_clean.
  start_drop (start_boot) the X-COM player drops during the borrowed start: client hold_battle_ready; client confirms;
     Handshake; client.kill(). start_unwound, host_home, start_drop_clean.
A build without this drop handling passes 3/10: request_ended, roles_kept (the host reads gamemode 0 and noBases false
after the drop), rejoined_landing, client_told, both_at_menu and host_home FAIL, and host_leaves_clean is blocked.

ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_campaign_gm3_drop.py
"""

import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import event_state  # noqa: E402
import geo  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import test_battle_end_separate as BES  # noqa: E402
import test_campaign_battle_gm3 as G3B  # noqa: E402
import test_campaign_battle_gm3_end as G3E  # noqa: E402
import test_campaign_rejoin as CR  # noqa: E402

# ----- fixture values -----
KEY = "48034"
SEED = 1                                     # set on the X-COM client right before each confirm_landing
ROLE_BUG = "host gamemode 0 and noBases false after the drop"   # what roles_kept catches without the drop handling
SITE = {"mission": "STR_ALIEN_RESEARCH", "deployment": "STR_MEDIUM_SCOUT", "race": "STR_SECTOID", "hours": 240}
# the mission site and the Skyranger's forced position: the X-COM base's (lon, lat) plus these offsets
POINT = {"landing_drop": (0.35, 0.10), "start_drop": (0.35, 0.10)}
CRAFT_AT = {"landing_drop": (0.34, 0.10), "start_drop": (0.34, 0.10)}
SQUAD = 2
ARRIVAL = ("ConfirmLandingState", "CraftErrorState")        # the screen client2's Skyranger's arrival pushes
UNWIND = "failed battle start ("
# ----- bounds -----
MIRROR_S = 30
LANDING_S = 180
PENDING_S = 10
DIALOG62_S = 30
REJOIN_S = 135
GEO_S = 60
CLIENT2_PROMPT_S, CLIENT2_FORCE_S = 60, 30   # client2's prompt, re-force (its craft arrived 0.08 s after RESUME)
BOTH_IN_S = 60
TOLD_S = 120
HOLD8_S = 8.0
MENU_S = 60
HOST_MENU_S = 30
HANDSHAKE_S = 30
W_S, W_POLL = 15.0, 0.2
ROWS = {"landing_drop": ["request_ended", "roles_kept", "rejoined_landing", "landing_drop_clean"],
        "host_leaves": ["client_told", "both_at_menu", "host_leaves_clean"],
        "start_drop": ["start_unwound", "host_home", "start_drop_clean"]}
BOOT_CELLS = {"landing_boot": ROWS["landing_drop"] + ROWS["host_leaves"], "start_boot": ROWS["start_drop"]}
ALL_CELLS = BOOT_CELLS["landing_boot"] + BOOT_CELLS["start_boot"]
BOOT = {"tag": "landing_boot"}


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


def pvp(gc):
    return G3E.coop(gc).get("pvpBorrow") or {}


def dlg(gc):
    r = gc.cmd({"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("present", "code", "title", "backVisible")}


def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def since(gc, n0, needle):
    return [ln.split("\t")[-1][:220] for ln in logl(gc)[n0:] if needle in ln]


def icons(gc):
    return [b.get("name") for b in gc.ok({"cmd": "geo_state"}).get("bases", []) if b.get("coopIcon")]


def bview(gc):
    """phase / inBattle / battleId / peerAbsent from battle_state: the host during and right after a battle start."""
    r = gc.cmd({"cmd": "battle_state"})
    a = r.get("authority") or {}
    return {"phase": r.get("phase"), "inBattle": r.get("inBattle"), "battleId": a.get("battleId"), "peerAbsent": a.get("peerAbsent")}


def host_view(host):
    hc, hg = G3E.coop(host), host.ok({"cmd": "geo_state"})
    return {"gamemode": hc.get("gamemode"), "noBases": hc.get("noBases"), "pvpBorrow": hc.get("pvpBorrow") or {},
            "funds": hg.get("funds"), "realBases": G3E.real_bases(hg)}


def capture_boot(err, *machines):
    cap = {}
    for gc in machines:
        if not alive(gc):
            continue
        try:
            bs = CR.bs_raw(gc)
            with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as fh:
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[-40:]
            cap[gc.name] = {"stack": stack(gc), "battle": {k: bs.get(k) for k in ("inBattle", "phase", "side", "turn")} if bs else
                            "skipped (no BattlescapeState, a battle in the world)", "coop_dialog_info":
                            gc.cmd({"cmd": "coop_dialog_info"}),
                            "get_coop": gc.cmd({"cmd": "get_coop"}), "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE {BOOT['tag']}: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def bring_up(host, client, key, ev):
    """G3E's bring_up (copied, the key as a parameter, no HOST_SQ0)."""
    host.spawn(); host.connect(); client.spawn(); client.connect()
    try:
        gm = PF.start_pvp_campaign(host, client, key, alien_player="host")
    except Exception as e:  # noqa: BLE001
        capture_boot(f"PF.start_pvp_campaign: {e}", host, client)
    ch, cc = G3E.coop(host), G3E.coop(client)
    hg, cg = host.ok({"cmd": "geo_state"}), client.ok({"cmd": "geo_state"})
    rp = G3E.probe(host)
    host0 = {"noBases": ch.get("noBases"), "funds": hg.get("funds"), "realBases": G3E.real_bases(hg), "ids": rp.get("ids"),
             "daysPassed": rp.get("daysPassed"), "monthsPassed": rp.get("monthsPassed")}
    xb = next((b for b in cg.get("bases", []) if not b.get("coopBase") and not b.get("coopIcon")), None)
    sky = next((c for c in (xb or {}).get("crafts", []) if "SKYRANGER" in c.get("type", "") and not c.get("coop")), None)
    sb = next((b for b in client.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    client0 = {"noBases": cc.get("noBases"), "funds": cg.get("funds"), "realBases": G3E.real_bases(cg),
               "sky": sky and {"type": sky.get("type"), "id": sky.get("id")}, "soldiers": sids}
    ev.update(lobbyGamemode=gm, HOST0=host0, CLIENT0=client0, gamemode=[ch.get("gamemode"), cc.get("gamemode")])
    if not (ch.get("gamemode") == 3 and cc.get("gamemode") == 3 and ch.get("noBases") is True and cc.get("noBases") is False):
        capture_boot(f"bring-up preconditions: gamemode host {ch.get('gamemode')} client {cc.get('gamemode')} (want 3), "
                     f"noBases host {ch.get('noBases')!r} client {cc.get('noBases')!r} (want true / false)", host, client)
    if not xb or not sky or len(sids) < SQUAD:
        capture_boot(f"the client has no real base / Skyranger / {SQUAD} soldiers (base {xb and xb.get('name')}, sky {sky}, "
                     f"soldiers {sids})", host, client)
    geo.slow_clock(host, client)
    return host0, client0, xb


def stage_to_prompt(row, host, client, xb, client0, ev):
    """G3E's stage_row up to, not including, set_seed / confirm_landing. Returns (site_id, point)."""
    geo.slow_clock(host, client)
    sky = client0["sky"]
    sb = next((b for b in client.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    recs = {sid: G3E.srec(client, sid) for sid in sids}
    sq = [sid for sid in sids if recs[sid].get("where") == "base" and recs[sid].get("recovery") == 0][:SQUAD]
    if len(sq) < SQUAD:
        seen = {s: (recs[s].get("where"), recs[s].get("recovery")) for s in sids}
        capture_boot(f"{row}: fewer than {SQUAD} client soldiers in base with recovery 0: {seen}", host, client)
    asg = [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": False}) for sid in sids]
    asg += [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": True}) for sid in sq]
    if not all(r.get("ok") for r in asg):
        capture_boot(f"{row}: client craft_assign (SQ {sq}): {[r for r in asg if not r.get('ok')][:2]}", host, client)
    ev["SQ"] = sq
    dx, dy = POINT[row]
    point = [xb["lon"] + dx, xb["lat"] + dy]
    site = host.cmd(dict(SITE, cmd="spawn_mission_site", lon=point[0], lat=point[1]))
    if not site.get("ok"):
        capture_boot(f"{row}: host spawn_mission_site {site}", host, client)
    t0, mir = time.time(), None
    while mir is None and time.time() - t0 < MIRROR_S:
        mir = mirror(client, point)
        if mir is None:
            time.sleep(0.1)
    ev.update(point=point, siteHost=site.get("site_id"), mirrorS=round(time.time() - t0, 2), siteClient=mir and mir.get("id"))
    if mir is None:
        capture_boot(f"{row}: no coop mirror of host site {site.get('site_id')} on the client within {MIRROR_S} s", host, client)
    cf = force(client, xb, client0, row, mir)
    if not cf.get("ok"):
        capture_boot(f"{row}: client craft_force {cf}", host, client)

    def prompt():
        if session.has_state(client, "ConfirmLandingState"):
            return True
        for gc in (host, client):
            geo.drain_popups(gc, interest=geo.popup("ConfirmLandingState"))
            gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None
    t1 = time.time()
    try:
        client.wait_for("client landing prompt", prompt, timeout=LANDING_S, interval=0.25)
    except Exception as e:  # noqa: BLE001
        capture_boot(f"{row}: client landing prompt: {e}", host, client)
    ev.update(promptS=round(time.time() - t1, 2), hostStackAtPrompt=stack(host))
    return site.get("site_id"), point


def mirror(gc, point):
    return next((m for m in gc.ok({"cmd": "geo_state"}).get("missionSites", [])
                 if m.get("coop") and abs(m.get("lon", 9.0) - point[0]) < 0.01 and abs(m.get("lat", 9.0) - point[1]) < 0.01), None)


def force(gc, xb, client0, row, mir):
    cx, cy = CRAFT_AT[row]
    return gc.cmd({"cmd": "craft_force", "craft_id": client0["sky"]["id"], "status": "STR_OUT", "lon": xb["lon"] + cx,
                   "lat": xb["lat"] + cy, "dest": f"site:{mir['id']}", "fuel": 999999, "lowFuel": False})


def confirm(row, host, client):
    sd, cl = client.cmd({"cmd": "set_seed", "seed": SEED}), client.cmd({"cmd": "confirm_landing"})
    if not sd.get("ok") or not cl.get("ok"):
        capture_boot(f"{row}: {client.name} set_seed {sd} / confirm_landing {cl}", host, client)


def wait(pred, timeout, interval=0.25):
    return BES.wait_until(pred, timeout, interval)


def rejoin_geoscape(host, x, ev):
    """client2 joins; the host's 62 shows RESUME; RESUME; close_screens over a StoresState; then the host
    geo_clean and client2 without a CoopState / LoadGameState, its top GeoscapeState or its craft's arrival screen. Returns ref0."""
    host = x["host"]
    c2 = x["client2"] = GameClient("client2", None, make_user_dir(x["tag"] + "_client2"))
    c2.spawn(); c2.connect()
    t_j = time.time()
    ev["join"] = c2.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    ref0 = event_state(c2).get("coopClientBattleRefused")     # the baseline right after the join (0)
    ev["ref0"], pok = ref0, []

    def ready():
        for gc in (host, c2):
            if top(gc) == "Profile" and (gc is host or dlg(c2).get("code") != 52):
                pok.append([gc.name, round(time.time() - t_j, 2), gc.cmd({"cmd": "profile_ok"}).get("ok")])
        d = dlg(host)
        return top(host) == "CoopState" and d.get("code") == 62 and d.get("backVisible") is True
    ok, secs = wait(ready, REJOIN_S)
    ev.update(profileOk=pok, readyS=secs, afterJoin=dict(host_view(host), client2Gamemode=G3E.coop(c2).get("gamemode")))
    if not ok:
        capture_boot(f"landing_drop: the host's dialog 62 never showed RESUME within {REJOIN_S} s of client2's join",
                     host, c2)
    try:
        ev["resume"] = session.press_back_when_shown(host, "host RESUME", codes=(60, 62))
    except Exception as e:  # noqa: BLE001
        capture_boot(f"landing_drop: host RESUME: {str(e)[:300]}", host, c2)
    if "StoresState" in stack(host):
        ev["closeScreens"] = host.cmd({"cmd": "close_screens"})

    def rejoined():
        st2 = stack(c2)
        return BES.geo_clean(host) and bool(st2) and not any("CoopState" in s or "LoadGameState" in s for s in st2) \
            and st2[-1] in ("GeoscapeState",) + ARRIVAL
    ok, secs = wait(rejoined, GEO_S)
    ev.update(rejoinedS=secs, stacksAfterRejoin=[stack(host), stack(c2)])
    if not ok:
        capture_boot(f"landing_drop: host geo_clean / client2 on its geoscape (top GeoscapeState or {list(ARRIVAL)}, no CoopState / "
                     f"LoadGameState) not within {GEO_S} s", host, c2)
    return ref0


def row_landing_drop(host, client, x, xb, host0, client0, ctx, ev):
    crash0 = crash_set()
    t_row = time.time()
    _site, point = stage_to_prompt("landing_drop", host, client, xb, client0, ev)
    ev["openScreen"] = host.cmd({"cmd": "open_screen", "screen": "stores"})
    if top(host) != "StoresState":
        capture_boot(f"landing_drop: host open_screen stores: {ev['openScreen']}, top {top(host)}", host, client)
    confirm("landing_drop", host, client)
    ok, secs = wait(lambda: (lambda p: p.get("pending") is True and (p.get("armed") or 0) >= 1)(pvp(host)), PENDING_S)
    if not ok:
        capture_boot(f"landing_drop: host pvpBorrow pending + armed not within {PENDING_S} s: {pvp(host)}",
                     host, client)
    pv = pvp(host)
    r0 = {"requests": pv.get("requests") or 0, "borrowed": pv.get("borrowed") or 0}
    ev.update(pendingS=secs, BORROW0=r0)
    client.kill()
    t_k = time.time()
    probes = {}
    ok, s62 = wait(lambda: top(host) == "CoopState" and dlg(host).get("code") == 62, DIALOG62_S)
    if not ok:
        capture_boot(f"landing_drop: host dialog 62 not on top within {DIALOG62_S} s of the drop", host)
    p1 = host_view(host)
    for mark in (2.0, 10.0):                    # extra probe points, 2 s and 10 s after the drop (EVIDENCE only)
        time.sleep(max(0.0, mark - (time.time() - t_k)))
        probes[f"{mark:.0f}s"] = host_view(host)
    ev.update(dialog62S=s62, at_drop=p1, probes=probes)
    ref0 = rejoin_geoscape(host, x, ev)
    c2 = x["client2"]
    p2 = dict(host_view(host), client2={k: G3E.coop(c2).get(k) for k in ("gamemode", "noBases")})
    ev["at_rejoin"] = p2
    time.sleep(10.0)                            # a "10 s later" probe (EVIDENCE only)
    ev["after10s"] = dict(host_view(host), client2Stack=stack(c2))
    pend = p1["pvpBorrow"]
    pbad = [f"at_drop host pvpBorrow.pending {pend.get('pending')!r} (want false)"] if pend.get("pending") is not False else []
    pbad += [f"at_drop host pvpBorrow.requestDropped {pend.get('requestDropped')!r} (want 1)"] if pend.get("requestDropped") != 1 else []
    cell("request_ended", not pbad, "; ".join(pbad) or "at_drop: the waiting landing request ended with the drop (pending false, "
         "requestDropped 1)")
    rbad = []
    for nm, p in (("at_drop", p1), ("at_rejoin", p2)):
        rbad += [f"{nm} host {k} {p.get(k)!r} (want {w!r})" for k, w in (("gamemode", 3), ("noBases", True), ("funds", host0["funds"]),
                                                                       ("realBases", host0["realBases"])) if p.get(k) != w]
    rbad += [f"at_rejoin client2 {k} {p2['client2'].get(k)!r} (want {w!r})"
             for k, w in (("gamemode", 3), ("noBases", False)) if p2["client2"].get(k) != w]
    cell("roles_kept", not rbad, "; ".join(rbad) or "at_drop / at_rejoin: host gamemode 3, noBases true, funds and real bases == HOST0; client2 "
         "gamemode 3, noBases false")
    how, t_l = {}, time.time()

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
    ok, _s = wait(landing, CLIENT2_FORCE_S)
    if not ok:
        mir = mirror(c2, point)
        ev["forced"] = {"mirror": mir and mir.get("id"),
                        "reply": force(c2, xb, client0, "landing_drop", mir) if mir else None}
        ok, _s = wait(landing, CLIENT2_PROMPT_S - CLIENT2_FORCE_S)
    ev.update(landing=how.get("v"), landingS=round(time.time() - t_l, 2))
    lbad, spine = [], False
    if how.get("v") != "prompt":
        lbad.append(f"no ConfirmLandingState on client2 within {CLIENT2_PROMPT_S} s ({how.get('v') or 'no prompt, no refusal'}; stack "
                    f"{stack(c2)})")
    else:
        pre = pvp(host)
        ref1 = event_state(c2).get("coopClientBattleRefused")
        lbad += [f"client2 coopClientBattleRefused {ref1!r} (want unchanged {ref0!r})"] if ref1 != ref0 else []
        lbad += [f"host pvpBorrow.borrowed {pre.get('borrowed')!r} before client2's confirm (want BORROW0 {r0['borrowed']})"] \
            if (pre.get("borrowed") or 0) != r0["borrowed"] else []
        confirm("landing_drop client2", host, c2)
        both, bs = wait(lambda: G3B.in_battle(host) and G3B.in_battle(c2), BOTH_IN_S)
        post = pvp(host)
        ev.update(pvpBeforeConfirm=pre, pvpAfterConfirm=post, bothInS=bs)
        lbad += [f"host pvpBorrow.{k} {post.get(k)!r} (want BORROW0 + 1 = {r0[k] + 1})"
                 for k in ("requests", "borrowed") if (post.get(k) or 0) != r0[k] + 1]
        lbad += [f"host pvpBorrow.targetKind {post.get('targetKind')!r} (want 'site')"] if post.get("targetKind") != "site" else []
        if not both:
            lbad.append(f"inBattle host/client2 {[G3B.in_battle(host), G3B.in_battle(c2)]} {bs} s after the confirm")
        else:
            try:
                session.briefings_to_battlescape(host, c2)
                spine = True
            except Exception as e:  # noqa: BLE001
                lbad.append(f"session.briefings_to_battlescape raised: {str(e)[:300]}")
    cell("rejoined_landing", not lbad, "; ".join(lbad) or f"client2's prompt without a refusal; its confirm borrowed once (requests / borrowed "
         f"BORROW0 + 1, site); both inBattle; spine passed")
    eh, ec = event_state(host), event_state(c2)
    new = sorted(crash_set() - crash0)
    cbad = [f"desyncSeen host {eh.get('desyncSeen')!r} client2 {ec.get('desyncSeen')!r} (want false on both)"] \
        if eh.get("desyncSeen") is not False or ec.get("desyncSeen") is not False else []
    cbad += [f"{len(new)} new crash file(s) since the row's start (first {os.path.basename(new[0])})"] if new else []
    if spine:
        try:
            session.assert_hash_clean(host, c2, full=True)
        except Exception as e:  # noqa: BLE001
            cbad.append(f"hash_now full: {str(e)[:400]}")
    cell("landing_drop_clean", not cbad, "; ".join(cbad) or "desyncSeen false on host and client2, 0 new crash files"
         + (", hash_now full EQUAL after the spine" if spine else " (no spine: no hash)"))
    ev.update(client2Stack=stack(c2), wall=round(time.time() - t_row, 1))
    ctx["battle"] = c2 if spine else None


def row_host_leaves(host, ctx, ev):
    names = ROWS["host_leaves"]
    c2 = ctx.get("battle")
    if c2 is None:
        block(names, "no borrowed battle after the rejoin (rejoined_landing)")
        return
    crash0 = crash_set()
    t_row = time.time()
    ev["disconnect"] = host.cmd({"cmd": "disconnect_to_menu"})
    seen = {}

    def told():  # the dialog first, then the stack
        seen["dialog"] = dlg(c2)
        seen["stack"] = stack(c2)
        return seen["dialog"].get("code") == 21
    ok, secs = wait(told, TOLD_S)
    d = seen.get("dialog") or {}
    tbad = [] if ok else [f"no client2 dialog 21 within {TOLD_S} s ({d}, stack {seen.get('stack')})"]
    if ok:
        tbad += [f"dialog 21 title {d.get('title')!r} (want 'Server connection lost')"] if d.get("title") != "Server connection lost" \
            else []
        tbad += [f"dialog 21 backVisible {d.get('backVisible')!r} (want true)"] if d.get("backVisible") is not True else []
        tbad += [f"client2 stack {seen.get('stack')} (want top CoopState)"] if seen.get("stack", [])[-1:] != ["CoopState"] else []
        time.sleep(HOLD8_S)
        st8 = stack(c2)
        tbad += [f"client2 stack {st8} {HOLD8_S:.0f} s later (want top CoopState)"] if st8[-1:] != ["CoopState"] else []
        ev["stack8s"] = st8
    cell("client_told", not tbad, "; ".join(tbad) or f"client2 told 'Server connection lost' ({secs} s), backVisible, top CoopState, "
         f"still CoopState {HOLD8_S:.0f} s later")
    mbad = []
    if ok:
        back = c2.cmd({"cmd": "coop_dialog_back"})
        mok, ms = wait(lambda: top(c2) == "MainMenuState", MENU_S)
        ws = c2.cmd({"cmd": "world_state"})
        ev.update(back=back, menuS=ms, worldState={k: ws.get(k) for k in ("has_save", "has_battle")})
        mbad += [] if back.get("ok") and mok else [f"client2 coop_dialog_back {back} -> stack {stack(c2)} (want MainMenuState <= "
                                                   f"{MENU_S} s)"]
        mbad += [f"client2 world_state.has_save {ws.get('has_save')!r} (want false)"] if ws.get("has_save") is not False else []
    else:
        mbad.append("client2 was never told (client_told)")
    hok, hs = wait(lambda: top(host) == "MainMenuState", HOST_MENU_S)
    hp, hco = pvp(host), G3E.coop(host)
    mbad += [] if hok else [f"host stack {stack(host)} (want top MainMenuState)"]
    mbad += [f"host pvpBorrow.{k} {hp.get(k)!r} (want {w!r})" for k, w in (("active", False), ("dropped", 1)) if hp.get(k) != w]
    mbad += [f"host noBases {hco.get('noBases')!r} (want false)"] if hco.get("noBases") is not False else []
    cell("both_at_menu", not mbad, "; ".join(mbad) or "client2 MainMenuState without a save; host MainMenuState, pvpBorrow active false / "
         "dropped 1, noBases false")
    new = sorted(crash_set() - crash0)
    try:
        zd = session.assert_client_zero_disk(c2.user_dir) or "clean"
    except AssertionError as e:
        zd = str(e)[:300]
    fbad = [f"{len(new)} new crash file(s) since the row's start (first {os.path.basename(new[0])})"] if new else []
    fbad += [] if zd == "clean" else [f"client2 zero-disk: {zd}"]
    cell("host_leaves_clean", not fbad, "; ".join(fbad) or "0 new crash files, client2 zero-disk")
    ev.update(hostPv=hp, hostMenuS=hs, wall=round(time.time() - t_row, 1))


def row_start_drop(host, client, xb, host0, client0, ev):
    crash0 = crash_set()
    t_row = time.time()
    stage_to_prompt("start_drop", host, client, xb, client0, ev)
    ev["ICON0"] = icons(host)
    hold = client.cmd({"cmd": "hold_battle_ready", "on": True})
    if hold.get("armed") is not True:
        capture_boot(f"start_drop: client hold_battle_ready {hold}", host, client)
    confirm("start_drop", host, client)

    def handshake():
        return pvp(host).get("borrowed") == 1 and bview(host).get("phase") == "Handshake" \
            and client.cmd({"cmd": "hold_battle_ready"}).get("held") is True
    ok, secs = wait(handshake, HANDSHAKE_S, 0.2)
    if not ok:
        capture_boot(f"start_drop: host borrowed 1 + phase Handshake + client held not within {HANDSHAKE_S} s ({pvp(host)}, {bview(host)})",
                     host, client)
    n_h = len(logl(host))
    client.kill()
    t_k = time.time()
    first = dict(bview(host), t=round(time.time() - t_k, 2))
    polls = []
    while time.time() - t_k < W_S:
        st = stack(host)
        if not polls or polls[-1][1] != st:
            polls.append([round(time.time() - t_k, 2), st])
        time.sleep(W_POLL)
    unw = since(host, n_h, UNWIND)
    why = re.findall(r"\((partner dropped|partner lost)\)", " ".join(unw))
    hst, hd, hco, hg = stack(host), dlg(host), G3E.coop(host), host.ok({"cmd": "geo_state"})
    hp = hco.get("pvpBorrow") or {}
    ubad = [] if len(unw) == 1 and why else [f"host UNWIND lines {unw} (want 1 reading (partner dropped) or (partner lost))"]
    ubad += [f"host get_coop.inBattle {hco.get('inBattle')!r} (want false)"] if hco.get("inBattle") is not False else []
    ubad += [f"host stack {hst} holds a battle screen"] if "BriefingState" in hst or "BattlescapeState" in hst else []
    ubad += [f"host top {hst[-1:]} dialog {hd.get('code')} (want dialog 62 on top)"] if hst[-1:] != ["CoopState"] or hd.get("code") != 62 \
        else []
    cell("start_unwound", not ubad, "; ".join(ubad) or f"host UNWIND +1 ({why[0] if why else '?'}); inBattle false; no battle screen; "
         f"dialog 62 on top")
    hbad = [f"host stack {hst} (want it to end [GeoscapeState, CoopState])"] if hst[-2:] != ["GeoscapeState", "CoopState"] else []
    hbad += [f"host pvpBorrow.active {hp.get('active')!r} (want false)"] if hp.get("active") is not False else []
    hbad += [f"host pvpBorrow.swappedBack {hp.get('swappedBack')!r} (want 1)"] if hp.get("swappedBack") != 1 else []
    hbad += [f"host pvpBorrow.refusedSent {hp.get('refusedSent')!r} (want absent or 0)"] if hp.get("refusedSent") not in (None, 0) \
        else []
    hbad += [f"host {k} {v!r} (want {w!r})" for k, v, w in (("noBases", hco.get("noBases"), True), ("gamemode", hco.get("gamemode"), 3),
                                                           ("funds", hg.get("funds"), host0["funds"]),
                                                           ("realBases", G3E.real_bases(hg), host0["realBases"])) if v != w]
    cell("host_home", not hbad, "; ".join(hbad) or "host on its own world: [GeoscapeState, CoopState], active false, swappedBack 1, no "
         "refusal sent, noBases true, gamemode 3, funds and real bases == HOST0")
    new = sorted(crash_set() - crash0)
    ds = event_state(host).get("desyncSeen")
    fbad = [f"{len(new)} new crash file(s) since the row's start (first {os.path.basename(new[0])})"] if new else []
    fbad += [f"host desyncSeen {ds!r} (want false)"] if ds is not False else []
    cell("start_drop_clean", not fbad, "; ".join(fbad) or "0 new crash files, host desyncSeen false")
    ev.update(handshakeS=secs, lossPath=first, stacks=polls, UNWIND=unw, hostPv=hp, iconsAfter=icons(host),
              hostGeo={"funds": hg.get("funds"), "realBases": G3E.real_bases(hg)}, wall=round(time.time() - t_row, 1))


def run_boot(tag, label, rows):
    """One boot: spawn host and client, the bring-up, its rows in order, then every machine shut down."""
    BOOT["tag"] = label
    x = {"tag": tag, "host": GameClient("host", None, make_user_dir(tag + "_host")),
         "client": GameClient("client", None, make_user_dir(tag + "_client")), "client2": None}
    host, client = x["host"], x["client"]
    try:
        ev0 = {}
        try:
            host0, client0, xb = bring_up(host, client, KEY, ev0)
        finally:
            evidence(f"bring-up {label}", ev0)
        ctx = {}
        for row, fn in rows:
            ev = {}
            try:
                fn(host, client, x, xb, host0, client0, ctx, ev)
            except FixtureMiss:
                raise
            except Exception as e:  # noqa: BLE001
                ev["error"] = f"{type(e).__name__}: {str(e)[:300]}"
                block(ROWS[row], f"error {ev['error']}")
            finally:
                evidence(row, ev)
            row_verdict(row, ROWS[row])
    except FixtureMiss as e:
        block(BOOT_CELLS[label], f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] boot {label}: {type(e).__name__}: {e}", flush=True)
        block(BOOT_CELLS[label], f"error {type(e).__name__}: {str(e)[:200]}")
    finally:
        for gc in (x["client2"], client, host):
            try:
                if gc is not None and gc.proc is not None:
                    gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)


def main():
    t0 = time.time()
    run_boot("campaign_gm3_drop_landing", "landing_boot",
             (("landing_drop", row_landing_drop),
              ("host_leaves", lambda h, c, x, xb, h0, c0, ctx, ev: row_host_leaves(h, ctx, ev))))
    run_boot("campaign_gm3_drop_start", "start_boot",
             (("start_drop", lambda h, c, x, xb, h0, c0, ctx, ev: row_start_drop(h, c, xb, h0, c0, ev)),))
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== test_campaign_gm3_drop (roles_kept guards against {ROLE_BUG}): "
          f"{len(RESULTS) - len(fails)}/{len(ALL_CELLS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(ALL_CELLS) else 2)


if __name__ == "__main__":
    main()
