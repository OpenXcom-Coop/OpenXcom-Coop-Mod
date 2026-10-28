"""D250-U S-C3 - test_campaign_gm3_drop.py: gm3 PvP campaign drops (host = the aliens, client = X-COM): the X-COM player drops
while its landing waits and rejoins on the geoscape, the alien host leaves a borrowed battle, and the X-COM player drops during the
borrowed battle's start.

Spec: docs rewrite/prompts/d250u_pvp_campaigns_sc.md, AMENDMENT SC-3 (SC3-3 "Stage S-C3", SC3-5 file B, SC3-6 FX3-1 .. FX3-19) and its
rulings: QC-13 (a), QC-15 (a), QC3-1 .. QC3-6 (a), R-D250-SC3-1 (FX3-11's last step and the client2 refusal baseline); owner D250, O1 (a);
F13996, F15322, F15323; VL-C-8, VL-C3-1, VL-C3-3, VL-C3-4. TASK 0 pins: docs rewrite/d250u-task0/sc3/CONSTANTS.md (boots Ga, Gb, Ha on the
unchanged build; d250ucc-red): the H14 variant is `ab`, so F3-role is a red cell.

Boot G: gm3, lobby key 48034, dirs d250uc3_g_host / d250uc3_g_client / d250uc3_g_client2. Boot H (after G): key 48034, dirs
d250uc3_h_host / d250uc3_h_client. Bring-up in each (FX3-2): PF.start_pvp_campaign(alien_player="host"); HOST0 / CLIENT0; gamemode 3 on
both, host noBases true and client noBases false are preconditions; geo.slow_clock. A bring-up or staging miss is a FIXTURE-STOP: ONE
"CAPTURE G:" / "CAPTURE H:" line and every remaining cell of that boot FAILs "boot".
Rows and cells (one PASS / FAIL line per cell, one EVIDENCE line and one ROW line per row; a row whose precondition was never reached
FAILs each of its cells "blocked: <why>"):
  F3 (boot G) the X-COM player drops while its landing waits, then rejoins: stage_to_prompt; host open_screen stores; client confirms;
     host pvpBorrow pending + armed; R0; client.kill(); host dialog 62; P1; the geoscape rejoin (FX3-11 as ruled by R-D250-SC3-1: host
     geo_clean, client2 without a CoopState / LoadGameState, its top GeoscapeState or its craft's arrival screen); P2; client2's landing
     (FX3-19, refusals counted from client2's value right after its join_tcp).
     F3-pending (P1: pending false, requestDropped 1), F3-role (P1 / P2: host gamemode 3, noBases true, funds / real bases == HOST0;
     P2: client2 gamemode 3, noBases false), F3-land (client2's prompt without a refusal; its confirm borrows once; both in battle;
     spine), F3-common (desyncSeen false, 0 new crash files, hash EQUAL after the spine when reached).
  F4 (boot G, on F3-land's battle) the alien host leaves a borrowed battle: host disconnect_to_menu; CR3's recipe on client2.
     F4-told, F4-menu, F4-common.
  F6 (boot H) the X-COM player drops during the borrowed start: client hold_battle_ready; client confirms; Handshake; client.kill().
     F6-unwind, F6-home, F6-common.
RED (C3R, the unchanged product; TASK 0 boots Ga / Gb / Ha, variant ab): 3/10 - FAIL F3-pending, F3-role, F3-land, F4-told, F4-menu,
F4-common (blocked), F6-home. GREEN (C3G): 10/10.

WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
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
import test_campaign_battle_gm3 as G3C1  # noqa: E402
import test_campaign_battle_gm3_end as G3E  # noqa: E402
import test_campaign_rejoin as CR  # noqa: E402

# ----- TASK 0 pins (docs rewrite/d250u-task0/sc3/CONSTANTS.md, boots Ga / Gb / Ha) -----
KEY = "48034"
SEED = 1                                     # set on the X-COM client right before each confirm_landing (F13986)
H14_VARIANT = "ab"                           # T0-4: host gamemode 0 and noBases false at every probe after the drop
SITE = {"mission": "STR_ALIEN_RESEARCH", "deployment": "STR_MEDIUM_SCOUT", "race": "STR_SECTOID", "hours": 240}   # FX3-4
POINT = {"F3": (0.35, 0.10), "F6": (0.35, 0.10)}            # FX3-3: X + point (no swap needed, TASK 0)
CRAFT_AT = {"F3": (0.34, 0.10), "F6": (0.34, 0.10)}         # FX3-5
SQUAD = 2
ARRIVAL = ("ConfirmLandingState", "CraftErrorState")        # R-D250-SC3-1: the screen client2's Skyranger's arrival pushes
UNWIND = "W2-H24: failed battle start ("
# ----- bounds -----
MIRROR_S = 30
LANDING_S = 180
PENDING_S = 10
DIALOG62_S = 30
REJOIN_S = 135
GEO_S = 60
PROMPT3_S, PROMPT3_FORCE_S = 60, 30          # FX3-19 (T0-4: client2's craft arrives 0.08 s after RESUME)
BOTH_IN_S = 60
TOLD_S = 120
HOLD8_S = 8.0
MENU_S = 60
HOST_MENU_S = 30
HANDSHAKE_S = 30
W_S, W_POLL = 15.0, 0.2
ROWS = {"F3": ["F3-pending", "F3-role", "F3-land", "F3-common"], "F4": ["F4-told", "F4-menu", "F4-common"],
        "F6": ["F6-unwind", "F6-home", "F6-common"]}
BOOT_CELLS = {"G": ROWS["F3"] + ROWS["F4"], "H": ROWS["F6"]}
ALL_CELLS = BOOT_CELLS["G"] + BOOT_CELLS["H"]
BOOT = {"tag": "G"}


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
    """battle_state's phase / inBattle / battleId (the W2-H24 C2 recipe: the host during and right after a battle start)."""
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
                            "skipped (F10980)", "coop_dialog_info": gc.cmd({"cmd": "coop_dialog_info"}),
                            "get_coop": gc.cmd({"cmd": "get_coop"}), "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE {BOOT['tag']}: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def bring_up(host, client, key, ev):
    """G3E's bring_up (copied, the key as a parameter, no HOST_SQ0; FX3-2)."""
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
        capture_boot(f"bring-up preconditions (FX3-2): gamemode host {ch.get('gamemode')} client {cc.get('gamemode')} (want 3), "
                     f"noBases host {ch.get('noBases')!r} client {cc.get('noBases')!r} (want true / false)", host, client)
    if not xb or not sky or len(sids) < SQUAD:
        capture_boot(f"the client has no real base / Skyranger / {SQUAD} soldiers (base {xb and xb.get('name')}, sky {sky}, "
                     f"soldiers {sids})", host, client)
    geo.slow_clock(host, client)
    return host0, client0, xb


def stage_to_prompt(row, host, client, xb, client0, ev):
    """G3E's stage_row up to, not including, set_seed / confirm_landing (FX3-3 .. FX3-7). Returns (site_id, point)."""
    geo.slow_clock(host, client)
    sky = client0["sky"]
    sb = next((b for b in client.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    recs = {sid: G3E.srec(client, sid) for sid in sids}
    sq = [sid for sid in sids if recs[sid].get("where") == "base" and recs[sid].get("recovery") == 0][:SQUAD]
    if len(sq) < SQUAD:
        seen = {s: (recs[s].get("where"), recs[s].get("recovery")) for s in sids}
        capture_boot(f"{row}: fewer than {SQUAD} client soldiers in base with recovery 0 (FX3-6): {seen}", host, client)
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
    """FX3-11 (R-D250-SC3-1): client2 joins; the host's 62 shows RESUME; RESUME; close_screens over a StoresState; then the host
    geo_clean and client2 without a CoopState / LoadGameState, its top GeoscapeState or its craft's arrival screen. Returns ref0."""
    host = x["host"]
    c2 = x["client2"] = GameClient("client2", None, make_user_dir(x["tag"] + "_client2"))
    c2.spawn(); c2.connect()
    t_j = time.time()
    ev["join"] = c2.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    ref0 = event_state(c2).get("coopClientBattleRefused")     # R-D250-SC3-1: the baseline right after the join (0)
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
        capture_boot(f"F3: the host's dialog 62 never showed RESUME within {REJOIN_S} s of client2's join (FX3-11)", host, c2)
    try:
        ev["resume"] = session.press_back_when_shown(host, "host RESUME", codes=(60, 62))
    except Exception as e:  # noqa: BLE001
        capture_boot(f"F3: host RESUME (FX3-11): {str(e)[:300]}", host, c2)
    if "StoresState" in stack(host):
        ev["closeScreens"] = host.cmd({"cmd": "close_screens"})

    def rejoined():
        st2 = stack(c2)
        return BES.geo_clean(host) and bool(st2) and not any("CoopState" in s or "LoadGameState" in s for s in st2) \
            and st2[-1] in ("GeoscapeState",) + ARRIVAL
    ok, secs = wait(rejoined, GEO_S)
    ev.update(rejoinedS=secs, stacksAfterRejoin=[stack(host), stack(c2)])
    if not ok:
        capture_boot(f"F3: host geo_clean / client2 on its geoscape (top GeoscapeState or {list(ARRIVAL)}, no CoopState / "
                     f"LoadGameState) not within {GEO_S} s (FX3-11, R-D250-SC3-1)", host, c2)
    return ref0


def row_f3(host, client, x, xb, host0, client0, ctx, ev):
    crash0 = crash_set()
    t_row = time.time()
    _site, point = stage_to_prompt("F3", host, client, xb, client0, ev)
    ev["openScreen"] = host.cmd({"cmd": "open_screen", "screen": "stores"})
    if top(host) != "StoresState":
        capture_boot(f"F3: host open_screen stores (FX3-8): {ev['openScreen']}, top {top(host)}", host, client)
    confirm("F3", host, client)
    ok, secs = wait(lambda: (lambda p: p.get("pending") is True and (p.get("armed") or 0) >= 1)(pvp(host)), PENDING_S)
    if not ok:
        capture_boot(f"F3: host pvpBorrow pending + armed not within {PENDING_S} s: {pvp(host)}", host, client)
    pv = pvp(host)
    r0 = {"requests": pv.get("requests") or 0, "borrowed": pv.get("borrowed") or 0}
    ev.update(pendingS=secs, R0=r0)
    client.kill()
    t_k = time.time()
    probes = {}
    ok, s62 = wait(lambda: top(host) == "CoopState" and dlg(host).get("code") == 62, DIALOG62_S)
    if not ok:
        capture_boot(f"F3: host dialog 62 not on top within {DIALOG62_S} s of the drop (FX3-9)", host)
    p1 = host_view(host)
    for mark in (2.0, 10.0):                    # the T0-4 probe points (EVIDENCE only)
        time.sleep(max(0.0, mark - (time.time() - t_k)))
        probes[f"{mark:.0f}s"] = host_view(host)
    ev.update(dialog62S=s62, P1=p1, probes=probes)
    ref0 = rejoin_geoscape(host, x, ev)
    c2 = x["client2"]
    p2 = dict(host_view(host), client2={k: G3E.coop(c2).get(k) for k in ("gamemode", "noBases")})
    ev["P2"] = p2
    time.sleep(10.0)                            # T0-4's "10 s later" probe (EVIDENCE only)
    ev["after10s"] = dict(host_view(host), client2Stack=stack(c2))
    pend = p1["pvpBorrow"]
    pbad = [f"P1 host pvpBorrow.pending {pend.get('pending')!r} (want false)"] if pend.get("pending") is not False else []
    pbad += [f"P1 host pvpBorrow.requestDropped {pend.get('requestDropped')!r} (want 1)"] if pend.get("requestDropped") != 1 else []
    cell("F3-pending", not pbad, "; ".join(pbad) or "P1: the waiting landing request ended with the drop (pending false, "
         "requestDropped 1)")
    rbad = []
    for nm, p in (("P1", p1), ("P2", p2)):
        rbad += [f"{nm} host {k} {p.get(k)!r} (want {w!r})" for k, w in (("gamemode", 3), ("noBases", True), ("funds", host0["funds"]),
                                                                       ("realBases", host0["realBases"])) if p.get(k) != w]
    rbad += [f"P2 client2 {k} {p2['client2'].get(k)!r} (want {w!r})" for k, w in (("gamemode", 3), ("noBases", False))
             if p2["client2"].get(k) != w]
    cell("F3-role", not rbad, "; ".join(rbad) or "P1 / P2: host gamemode 3, noBases true, funds and real bases == HOST0; client2 "
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
    ok, _s = wait(landing, PROMPT3_FORCE_S)
    if not ok:
        mir = mirror(c2, point)
        ev["forced"] = {"mirror": mir and mir.get("id"), "reply": force(c2, xb, client0, "F3", mir) if mir else None}
        ok, _s = wait(landing, PROMPT3_S - PROMPT3_FORCE_S)
    ev.update(landing=how.get("v"), landingS=round(time.time() - t_l, 2))
    lbad, spine = [], False
    if how.get("v") != "prompt":
        lbad.append(f"no ConfirmLandingState on client2 within {PROMPT3_S} s ({how.get('v') or 'no prompt, no refusal'}; stack "
                    f"{stack(c2)})")
    else:
        pre = pvp(host)
        ref1 = event_state(c2).get("coopClientBattleRefused")
        lbad += [f"client2 coopClientBattleRefused {ref1!r} (want unchanged {ref0!r})"] if ref1 != ref0 else []
        lbad += [f"host pvpBorrow.borrowed {pre.get('borrowed')!r} before client2's confirm (want R0 {r0['borrowed']})"] \
            if (pre.get("borrowed") or 0) != r0["borrowed"] else []
        confirm("F3 client2", host, c2)
        both, bs = wait(lambda: G3C1.in_battle(host) and G3C1.in_battle(c2), BOTH_IN_S)
        post = pvp(host)
        ev.update(pvpBeforeConfirm=pre, pvpAfterConfirm=post, bothInS=bs)
        lbad += [f"host pvpBorrow.{k} {post.get(k)!r} (want R0 + 1 = {r0[k] + 1})" for k in ("requests", "borrowed")
                 if (post.get(k) or 0) != r0[k] + 1]
        lbad += [f"host pvpBorrow.targetKind {post.get('targetKind')!r} (want 'site')"] if post.get("targetKind") != "site" else []
        if not both:
            lbad.append(f"inBattle host/client2 {[G3C1.in_battle(host), G3C1.in_battle(c2)]} {bs} s after the confirm")
        else:
            try:
                session.briefings_to_battlescape(host, c2)
                spine = True
            except Exception as e:  # noqa: BLE001
                lbad.append(f"session.briefings_to_battlescape raised: {str(e)[:300]}")
    cell("F3-land", not lbad, "; ".join(lbad) or f"client2's prompt without a refusal; its confirm borrowed once (requests / borrowed "
         f"R0 + 1, site); both inBattle; spine passed")
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
    cell("F3-common", not cbad, "; ".join(cbad) or "desyncSeen false on host and client2, 0 new crash files"
         + (", hash_now full EQUAL after the spine" if spine else " (no spine: no hash)"))
    ev.update(client2Stack=stack(c2), wall=round(time.time() - t_row, 1))
    ctx["battle"] = c2 if spine else None


def row_f4(host, ctx, ev):
    names = ROWS["F4"]
    c2 = ctx.get("battle")
    if c2 is None:
        block(names, "no borrowed battle after the rejoin (F3-land)")
        return
    crash0 = crash_set()
    t_row = time.time()
    ev["disconnect"] = host.cmd({"cmd": "disconnect_to_menu"})
    seen = {}

    def told():  # the dialog first, then the stack (R-L2-A-3)
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
    cell("F4-told", not tbad, "; ".join(tbad) or f"client2 told 'Server connection lost' ({secs} s), backVisible, top CoopState, "
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
        mbad.append("client2 was never told (F4-told)")
    hok, hs = wait(lambda: top(host) == "MainMenuState", HOST_MENU_S)
    hp, hco = pvp(host), G3E.coop(host)
    mbad += [] if hok else [f"host stack {stack(host)} (want top MainMenuState)"]
    mbad += [f"host pvpBorrow.{k} {hp.get(k)!r} (want {w!r})" for k, w in (("active", False), ("dropped", 1)) if hp.get(k) != w]
    mbad += [f"host noBases {hco.get('noBases')!r} (want false, F15326)"] if hco.get("noBases") is not False else []
    cell("F4-menu", not mbad, "; ".join(mbad) or "client2 MainMenuState without a save; host MainMenuState, pvpBorrow active false / "
         "dropped 1, noBases false")
    new = sorted(crash_set() - crash0)
    try:
        zd = session.assert_client_zero_disk(c2.user_dir) or "clean"
    except AssertionError as e:
        zd = str(e)[:300]
    fbad = [f"{len(new)} new crash file(s) since the row's start (first {os.path.basename(new[0])})"] if new else []
    fbad += [] if zd == "clean" else [f"client2 zero-disk: {zd}"]
    cell("F4-common", not fbad, "; ".join(fbad) or "0 new crash files, client2 zero-disk")
    ev.update(hostPv=hp, hostMenuS=hs, wall=round(time.time() - t_row, 1))


def row_f6(host, client, xb, host0, client0, ev):
    crash0 = crash_set()
    t_row = time.time()
    stage_to_prompt("F6", host, client, xb, client0, ev)
    ev["ICON0"] = icons(host)
    hold = client.cmd({"cmd": "hold_battle_ready", "on": True})
    if hold.get("armed") is not True:
        capture_boot(f"F6: client hold_battle_ready {hold}", host, client)
    confirm("F6", host, client)

    def handshake():
        return pvp(host).get("borrowed") == 1 and bview(host).get("phase") == "Handshake" \
            and client.cmd({"cmd": "hold_battle_ready"}).get("held") is True
    ok, secs = wait(handshake, HANDSHAKE_S, 0.2)
    if not ok:
        capture_boot(f"F6: host borrowed 1 + phase Handshake + client held not within {HANDSHAKE_S} s ({pvp(host)}, {bview(host)})",
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
    cell("F6-unwind", not ubad, "; ".join(ubad) or f"host UNWIND +1 ({why[0] if why else '?'}); inBattle false; no battle screen; "
         f"dialog 62 on top")
    hbad = [f"host stack {hst} (want it to end [GeoscapeState, CoopState])"] if hst[-2:] != ["GeoscapeState", "CoopState"] else []
    hbad += [f"host pvpBorrow.active {hp.get('active')!r} (want false)"] if hp.get("active") is not False else []
    hbad += [f"host pvpBorrow.swappedBack {hp.get('swappedBack')!r} (want 1)"] if hp.get("swappedBack") != 1 else []
    hbad += [f"host pvpBorrow.refusedSent {hp.get('refusedSent')!r} (want absent or 0)"] if hp.get("refusedSent") not in (None, 0) \
        else []
    hbad += [f"host {k} {v!r} (want {w!r})" for k, v, w in (("noBases", hco.get("noBases"), True), ("gamemode", hco.get("gamemode"), 3),
                                                           ("funds", hg.get("funds"), host0["funds"]),
                                                           ("realBases", G3E.real_bases(hg), host0["realBases"])) if v != w]
    cell("F6-home", not hbad, "; ".join(hbad) or "host on its own world: [GeoscapeState, CoopState], active false, swappedBack 1, no "
         "refusal sent, noBases true, gamemode 3, funds and real bases == HOST0")
    new = sorted(crash_set() - crash0)
    ds = event_state(host).get("desyncSeen")
    fbad = [f"{len(new)} new crash file(s) since the row's start (first {os.path.basename(new[0])})"] if new else []
    fbad += [f"host desyncSeen {ds!r} (want false)"] if ds is not False else []
    cell("F6-common", not fbad, "; ".join(fbad) or "0 new crash files, host desyncSeen false")
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
    run_boot("d250uc3_g", "G", (("F3", row_f3),
                                ("F4", lambda h, c, x, xb, h0, c0, ctx, ev: row_f4(h, ctx, ev))))
    run_boot("d250uc3_h", "H", (("F6", lambda h, c, x, xb, h0, c0, ctx, ev: row_f6(h, c, xb, h0, c0, ev)),))
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== D250-U S-C3 gm3 drops (variant {H14_VARIANT}): {len(RESULTS) - len(fails)}/{len(ALL_CELLS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(ALL_CELLS) else 2)


if __name__ == "__main__":
    main()
