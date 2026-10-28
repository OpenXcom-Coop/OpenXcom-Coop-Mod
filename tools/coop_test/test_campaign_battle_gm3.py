"""D250-U S-C1 - test_campaign_battle_gm3.py: a gm3 PvP campaign battle's entry (host = the aliens, client = X-COM). The X-COM
client's landing at a mission site mirrored from the alien world starts ONE battle on both machines, run by the alien host in the
X-COM client's borrowed world; the seats are gm3's; the X-COM player moves a soldier and the alien host moves an alien through its
own UI; the alien seat reads its own research; the alien world sits parked and untouched.

Spec: docs rewrite/prompts/d250u_pvp_campaigns_sc.md, section (f) "test_campaign_battle_gm3.py" (owner D250, O1 (a); D149,
D215; QC-1..QC-18 (a); F13506, F13986). TASK 0 pins: docs rewrite/d250u-task0/sc1/CONSTANTS.md (SEED_C, TOPIC, MIRROR_S, MAP_FP_C1
and S / S_DEST / A / A_DEST as EVIDENCE; boots Ca and Cb on the unchanged build, each 2/2).

Boot C: gm3, lobby key 48011, dirs d250uc1_c_host / d250uc1_c_client. Bring-up: PF.start_pvp_campaign(alien_player="host"); crash
baseline; HOST0 / CLIENT0; geo.slow_clock. Staging (TASK 0 T0-2 (2)-(4)): research sync off (client first), host discover_research
TOPIC, the client's squad of two (the two lowest ids), the host's mission site and its mirror on the client, the client's Skyranger
forced out to the mirror, the landing prompt on the client. A bring-up or staging step past its bound is a FIXTURE-STOP: ONE
"CAPTURE C:" line (both stacks, battle_state phase / side / turn, coop_dialog_info, get_coop, the last 40 engine log lines) and every
remaining cell FAILs "boot".
Rows and cells (one PASS / FAIL line per cell, one EVIDENCE line and one ROW line per row; every row runs after a failure unless its
precondition was never reached, then each of its cells FAILs "blocked: <why>"):
  C-gm  gamemode 3 on both; host noBases true, client false (at bring-up).
  C1 entry: client set_seed SEED_C, confirm_landing; both inBattle <= 60 s; session.briefings_to_battlescape.
     C1-hand (both get_coop.pvpBorrow records; 0 new client "offerBattle() called on a non-host machine" lines), C1-entry (turn 1,
     mapFingerprint equal on both), C1-seats (faction 0 seat 1 = the squad, faction 1 seat 0 without AI, no other faction, equal on
     both), C1-world (the host borrows: pvpBorrow.active, noBases false, pvpBorrow.parked == HOST0), C1-research (research_check:
     seat 0 reads the parked alien world, TOPIC true; seat 1 false; the live world false), C1-common.
  C2 X-COM move: reactions 0 (G3F); S / S_DEST by rule; the client walks S: C2-walk, C2-side (client END TURN: side 1), C2-common.
  C3 alien move: A / A_DEST by rule; host TAB, tab_select, one real click (G3F G4): C3-sel, C3-ctx, C3-pos, C3-side (host END TURN:
     turn 2, side 0), C3-common.
  <row>-common: event_state.desyncSeen false on both, 0 new crash files in the row, assert_hash_clean(full=True) EQUAL.
Walk targets (spec (f)), read at run time from the HOST's tile_info: S = the lowest-id live faction-0 unit, S_DEST = the first of its
eight neighbours on its level (N, NE, E, SE, S, SW, W, NW) with no unit, a floor part and no object part; A / A_DEST the same for
faction 1. TASK 0's S / S_DEST / A / A_DEST and MAP_FP_C1 are EVIDENCE beside the run-time values (never a re-pick).
RED (C1R, the unchanged product: the X-COM client generates the battle alone, F13506): C-gm PASSes; C1-hand FAILs (no pvpBorrow, the
client's local battle, the non-host warning +1); every other cell FAILs "blocked: the alien host never entered the battle (C1-hand)".
GREEN (C1G): 15/15. The file ends after C3 (the battle's end is S-C2's).

ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_campaign_battle_gm3.py
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
import test_battle_end_separate as BES  # noqa: E402
import repro_atom_side_begin as RSB  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402

# ----- TASK 0 pins (docs rewrite/d250u-task0/sc1/CONSTANTS.md, boots Ca and Cb, 2/2 each) -----
KEY = "48011"
SEED_C = 1                                   # set on the X-COM CLIENT right before its confirm_landing
TOPIC = "STR_LASER_WEAPONS"                  # the first of LASER / MOTION_SCANNER / MEDI_KIT unresearched on both
MIRROR_S_PIN = 0.05                          # EVIDENCE: the host site's mirror reached the client at the first poll (2/2)
MAP_FP_C1 = 5.996615470105667e+18            # EVIDENCE: the client-local map at SEED_C (STOP-IF 13: never a stop)
S_PIN = (1, (34, 9, 1), (35, 10, 1))         # EVIDENCE: (id, tile, dest) by the rule on the client-local map
A_PIN = (1000000, (2, 16, 1), (3, 15, 1))    # EVIDENCE
SQUAD = 2
SITE = {"mission": "STR_ALIEN_RESEARCH", "deployment": "STR_MEDIUM_SCOUT", "race": "STR_SECTOID", "hours": 240}
WARN = "offerBattle() called on a non-host machine - ignoring"
NEIGH = (("N", 0, -1), ("NE", 1, -1), ("E", 1, 0), ("SE", 1, 1), ("S", 0, 1), ("SW", -1, 1), ("W", -1, 0), ("NW", -1, -1))
# ----- bounds -----
MIRROR_S = 30
LANDING_S = 180
BOTH_IN_S = 60
STEP_S = 30
ALL_CELLS = ["C-gm", "C1-hand", "C1-entry", "C1-seats", "C1-world", "C1-research", "C1-common", "C2-walk", "C2-side",
             "C2-common", "C3-sel", "C3-ctx", "C3-pos", "C3-side", "C3-common"]


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


def stack(gc):
    return session.states_stripped(gc)


def crash_set():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))


def coop(gc):
    r = gc.cmd({"cmd": "get_coop"})
    return {k: r.get(k) for k in ("gamemode", "noBases", "coopDialog", "inBattle", "pvpBorrow")}


def real_bases(g):
    return [{"name": b.get("name"), "lon": round(b.get("lon") or 0.0, 9), "lat": round(b.get("lat") or 0.0, 9)}
            for b in g.get("bases", []) if not b.get("coopBase") and not b.get("coopIcon")]


def census(gc):
    return [{k: u.get(k) for k in ("id", "faction", "coop", "hasAI", "isOut")} for u in battle_state(gc).get("units", [])]


def in_battle(gc):
    return bool(battle_state(gc).get("inBattle"))


def capture_boot(err, host, client):
    cap = {}
    for gc in (host, client):
        try:
            bs = battle_state(gc)
            with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as fh:
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[-40:]
            cap[gc.name] = {"stack": stack(gc), "battle": {k: bs.get(k) for k in ("inBattle", "phase", "side", "turn")},
                            "coop_dialog_info": gc.cmd({"cmd": "coop_dialog_info"}), "get_coop": gc.cmd({"cmd": "get_coop"}),
                            "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE C: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def common(row, host, client, crash0):
    """<row>-common: desyncSeen false on both, 0 new crash files since the row began, every hash bucket EQUAL."""
    eh, ec = event_state(host), event_state(client)
    new = sorted(crash_set() - crash0)
    bad = []
    if eh.get("desyncSeen") is not False or ec.get("desyncSeen") is not False:
        bad.append(f"desyncSeen host {eh.get('desyncSeen')!r} client {ec.get('desyncSeen')!r} (want false on both)")
    if new:
        bad.append(f"{len(new)} new crash file(s) in the row (first {os.path.basename(new[0])})")
    try:
        session.assert_hash_clean(host, client, full=True)
    except Exception as e:  # noqa: BLE001
        bad.append(f"hash_now full: {str(e)[:400]}")
    cell(f"{row}-common", not bad, "; ".join(bad) or "desyncSeen false on both, 0 new crash files, hash_now full EQUAL")


def walk_target(host, faction):
    """The spec (f) rule on the HOST's map: the lowest-id live unit of `faction` and the first of its eight neighbours (N, NE, E, SE,
    S, SW, W, NW) on its level with no unit, a floor part and no object part. Returns (id, tile, dest or None, neighbours)."""
    live = sorted((u for u in battle_state(host).get("units", []) if u.get("faction") == faction and not u.get("isOut")),
                  key=lambda u: u["id"])
    if not live:
        return None, None, None, []
    u = live[0]
    tile, dest, seen = (u["x"], u["y"], u["z"]), None, []
    for nm, dx, dy in NEIGH:
        p = (u["x"] + dx, u["y"] + dy, u["z"])
        ti = host.cmd({"cmd": "tile_info", "x": p[0], "y": p[1], "z": p[2]})
        parts = ti.get("parts") or {}
        fl, ob = (parts.get("floor") or {}).get("mapDataID"), (parts.get("object") or {}).get("mapDataID")
        seen.append([nm, ti.get("error") or [ti.get("unit"), fl, ob]])
        if dest is None and not ti.get("error") and ti.get("unit") == -1 and fl not in (None, -1) and ob == -1:
            dest = p
    return u["id"], tile, dest, seen


def bring_up(host, client, ev):
    """Spawn, the gm3 campaign (the HOST on the Alien team), HOST0 / CLIENT0, geo.slow_clock; the C-gm cell."""
    host.spawn(); host.connect(); client.spawn(); client.connect()
    try:
        gm = PF.start_pvp_campaign(host, client, KEY, alien_player="host")
    except Exception as e:  # noqa: BLE001
        capture_boot(f"PF.start_pvp_campaign: {e}", host, client)
    ch, cc = coop(host), coop(client)
    hg, cg = host.ok({"cmd": "geo_state"}), client.ok({"cmd": "geo_state"})
    rp = host.ok({"cmd": "research_probe", "names": [], "tail": 0})
    host0 = {"noBases": ch.get("noBases"), "funds": hg.get("funds"), "realBases": real_bases(hg), "ids": rp.get("ids"),
             "daysPassed": rp.get("daysPassed"), "monthsPassed": rp.get("monthsPassed")}
    xb = next((b for b in cg.get("bases", []) if not b.get("coopBase") and not b.get("coopIcon")), None)
    sky = next((c for c in (xb or {}).get("crafts", []) if "SKYRANGER" in c.get("type", "") and not c.get("coop")), None)
    sb = next((b for b in client.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    client0 = {"noBases": cc.get("noBases"), "funds": cg.get("funds"), "realBases": real_bases(cg),
               "sky": sky and {"type": sky.get("type"), "id": sky.get("id")}, "soldiers": sids}
    ev.update(lobbyGamemode=gm, HOST0=host0, CLIENT0=client0)
    geo.slow_clock(host, client)
    cell("C-gm", ch.get("gamemode") == 3 and cc.get("gamemode") == 3 and ch.get("noBases") is True and cc.get("noBases") is False,
         f"get_coop.gamemode host {ch.get('gamemode')} client {cc.get('gamemode')} (want 3 on both); noBases host "
         f"{ch.get('noBases')!r} client {cc.get('noBases')!r} (want true / false)")
    if not xb or not sky or len(sids) < SQUAD:
        capture_boot(f"the client has no real base / Skyranger / {SQUAD} soldiers (base {xb and xb.get('name')}, sky {sky}, "
                     f"soldiers {sids})", host, client)
    return host0, client0, xb


def stage_landing(host, client, xb, client0, ev):
    """TASK 0 T0-2 (2)-(4): research sync off (client first), host discover_research TOPIC, the squad, the host site and its
    mirror on the client, craft_force, the landing prompt on the client (drain both, speed idx 2 on both). A miss = FIXTURE-STOP."""
    sync = [client.cmd({"cmd": "set_research_sync", "enabled": False}).get("sync"),
            host.cmd({"cmd": "set_research_sync", "enabled": False}).get("sync")]
    pre = [host.cmd({"cmd": "is_researched", "topic": TOPIC}).get("researched"),
           client.cmd({"cmd": "is_researched", "topic": TOPIC}).get("researched")]
    if sync != [False, False] or pre != [False, False]:
        capture_boot(f"research staging: sync client/host {sync}, {TOPIC} researched host/client {pre} (want all false)", host, client)
    dr = host.cmd({"cmd": "discover_research", "topic": TOPIC})
    post = client.cmd({"cmd": "is_researched", "topic": TOPIC}).get("researched")
    ev["topic"] = {"topic": TOPIC, "sync": sync, "pre": pre, "discover": dr, "clientAfter": post}
    if dr.get("researched") is not True or post is not False:
        capture_boot(f"host discover_research {TOPIC}: {dr}, client is_researched {post!r} (want true / false)", host, client)
    sky, squad = client0["sky"], client0["soldiers"][:SQUAD]
    asg = [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": False}) for sid in client0["soldiers"]]
    asg += [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": True}) for sid in squad]
    if not all(r.get("ok") for r in asg):
        capture_boot(f"client craft_assign (squad {squad}): {[r for r in asg if not r.get('ok')][:2]}", host, client)
    lon, lat = xb["lon"] + 0.35, xb["lat"] + 0.10
    site = host.cmd(dict(SITE, cmd="spawn_mission_site", lon=lon, lat=lat))
    if not site.get("ok"):
        capture_boot(f"host spawn_mission_site {site}", host, client)

    def mirror():
        return next((m for m in client.ok({"cmd": "geo_state"}).get("missionSites", [])
                     if m.get("coop") and abs(m.get("lon", 9.0) - lon) < 0.01 and abs(m.get("lat", 9.0) - lat) < 0.01), None)
    t0, mir = time.time(), None
    while mir is None and time.time() - t0 < MIRROR_S:
        mir = mirror()
        if mir is None:
            time.sleep(0.1)
    ev.update(squad=squad, siteHost=site.get("site_id"), mirrorS=round(time.time() - t0, 2), mirrorSPin=MIRROR_S_PIN,
              siteClient=mir and mir.get("id"))
    if mir is None:
        capture_boot(f"no coop mirror of host site {site.get('site_id')} on the client within {MIRROR_S} s", host, client)
    cf = client.cmd({"cmd": "craft_force", "craft_id": sky["id"], "status": "STR_OUT", "lon": xb["lon"] + 0.34,
                     "lat": xb["lat"] + 0.10, "dest": f"site:{mir['id']}", "fuel": 999999, "lowFuel": False})
    if not cf.get("ok"):
        capture_boot(f"client craft_force {cf}", host, client)

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
        capture_boot(f"client landing prompt: {e}", host, client)
    ev.update(promptS=round(time.time() - t1, 2), hostStackAtPrompt=stack(host))
    return squad


def row_c1(host, client, host0, client0, squad, ctx, ev, crash0):
    names = ["C1-hand", "C1-entry", "C1-seats", "C1-world", "C1-research", "C1-common"]
    w0 = BES.log_count(client, WARN)
    sd, cl = client.cmd({"cmd": "set_seed", "seed": SEED_C}), client.cmd({"cmd": "confirm_landing"})
    if not sd.get("ok") or not cl.get("ok"):
        capture_boot(f"client set_seed {sd} / confirm_landing {cl}", host, client)
    ev["stacksAfterConfirm"] = [stack(host), stack(client)]
    ok, secs = BES.wait_until(lambda: in_battle(host) and in_battle(client), BOTH_IN_S)
    hin, cin = in_battle(host), in_battle(client)
    ev.update(bothInS=secs, inBattle=[hin, cin], stacksAtWait=[stack(host), stack(client)])
    sp_ok, sp_detail = False, "not run (not both inBattle)"
    if hin and cin:
        try:
            session.briefings_to_battlescape(host, client)
            sp_ok, sp_detail = True, "spine passed"
        except Exception as e:  # noqa: BLE001
            sp_detail = f"session.briefings_to_battlescape raised: {str(e)[:300]} (stacks {[stack(host), stack(client)]})"
            ev["clientDialog"] = client.cmd({"cmd": "coop_dialog_info"})
    ch, cc = coop(host), coop(client)
    hp, cp = ch.get("pvpBorrow") or {}, cc.get("pvpBorrow") or {}
    warn = BES.log_count(client, WARN) - w0
    ev.update(pvpBorrowHost=ch.get("pvpBorrow"), pvpBorrowClient=cc.get("pvpBorrow"), warnDelta=warn,
              coopHost={k: ch.get(k) for k in ("noBases", "inBattle")}, coopClient={k: cc.get(k) for k in ("noBases", "inBattle")})
    sky = client0["sky"]
    hbad = [f"client pvpBorrow.{k} {cp.get(k)!r} (want 1)" for k in ("sent", "pushed", "held") if cp.get(k) != 1]
    hbad += [f"host pvpBorrow.{k} {hp.get(k)!r} (want {w!r})" for k, w in
             (("requests", 1), ("armed", 1), ("borrowed", 1), ("kind", "landing"), ("craftType", sky["type"]),
              ("craftId", sky["id"]), ("targetKind", "site"), ("targetMirror", True)) if hp.get(k) != w]
    if not ch.get("pvpBorrow") and not cc.get("pvpBorrow"):
        hbad.insert(0, "no get_coop.pvpBorrow on either machine")
    if warn != 0:
        hbad.append(f"{warn} new client log line(s) '{WARN}' (want 0)")
    if cin and not hin:
        hbad.append(f"the client's local battle: client inBattle true, host inBattle false {secs} s after the confirm "
                    f"(stacks host {ev['stacksAtWait'][0]} client {ev['stacksAtWait'][1]})")
    elif not (hin and cin):
        hbad.append(f"inBattle host/client {[hin, cin]} {secs} s after the confirm (want both)")
    cell("C1-hand", not hbad, "; ".join(hbad) or f"client pvpBorrow sent / pushed / held 1; host requests / armed / borrowed 1, "
         f"landing, {sky['type']}-{sky['id']}, target site (mirror); 0 non-host warnings; both inBattle {secs} s")
    if not hin:
        ctx["blocked"] = "the alien host never entered the battle (C1-hand)"
    elif not cin:
        ctx["blocked"] = "the X-COM client never entered the battle (C1-hand)"
    if ctx["blocked"]:
        block(names, ctx["blocked"])
        return names
    bh, bc = battle_state(host), battle_state(client)
    turn, fp = [bh.get("turn"), bc.get("turn")], [bh.get("mapFingerprint"), bc.get("mapFingerprint")]
    ev.update(turn=turn, mapFingerprint=fp, mapFpPin=MAP_FP_C1, mapFpEqualsPin=(fp[0] == MAP_FP_C1))
    ebad = [] if sp_ok else [sp_detail]
    ebad += [f"turn {turn} (want [1, 1])"] if turn != [1, 1] else []
    ebad += [f"mapFingerprint host {fp[0]!r} != client {fp[1]!r}"] if fp[0] != fp[1] or fp[0] is None else []
    cell("C1-entry", not ebad, "; ".join(ebad) or f"turn 1 on both, mapFingerprint {fp[0]!r} on both (MAP_FP_C1 "
         f"{MAP_FP_C1!r}: {'equal' if fp[0] == MAP_FP_C1 else 'differs, EVIDENCE only (STOP-IF 13)'})")
    hcen, ccen = census(host), census(client)
    ev.update(censusHost=hcen, censusClient=ccen)
    sbad = []
    for nm, cen in (("host", hcen), ("client", ccen)):
        f0 = [u for u in cen if u.get("faction") == 0]
        f1 = [u for u in cen if u.get("faction") == 1]
        if sorted(u["id"] for u in f0) != sorted(squad):
            sbad.append(f"{nm}: faction 0 ids {sorted(u['id'] for u in f0)} (want the squad {sorted(squad)})")
        sbad += [f"{nm}: unit {u['id']} faction 0 seat {u.get('coop')}" for u in f0 if u.get("coop") != 1]
        if not f1:
            sbad.append(f"{nm}: no faction 1 unit")
        sbad += [f"{nm}: unit {u['id']} faction 1 seat {u.get('coop')} hasAI {u.get('hasAI')}" for u in f1
                 if u.get("coop") != 0 or u.get("hasAI") is not False]
        sbad += [f"{nm}: unit {u['id']} faction {u.get('faction')}" for u in cen if u.get("faction") not in (0, 1)]
    key = lambda cen: sorted((u["id"], u.get("faction"), u.get("coop")) for u in cen)
    if key(hcen) != key(ccen):
        sbad.append(f"census (id, faction, seat) host {key(hcen)} != client {key(ccen)}")
    cell("C1-seats", not sbad, "; ".join(sbad) or f"census equal on both: faction 0 = the squad {sorted(squad)} on seat 1, "
         f"faction 1 on seat 0 without AI ({len(hcen)} units)")
    hp = (coop(host).get("pvpBorrow") or {})
    parked = hp.get("parked") or {}
    pv = {"funds": parked.get("funds"), "noBases": parked.get("noBases"),
          "realBases": [{"name": b.get("name"), "lon": round(b.get("lon") or 0.0, 9), "lat": round(b.get("lat") or 0.0, 9)}
                        for b in parked.get("realBases") or []]}
    want = {k: host0[k] for k in ("funds", "noBases", "realBases")}
    ev.update(parked=parked, parkedIdsEqualHost0=(parked.get("ids") == host0.get("ids")))
    wbad = [f"host pvpBorrow.active {hp.get('active')!r} (want true)"] if hp.get("active") is not True else []
    nb = coop(host).get("noBases")
    wbad += [f"host get_coop.noBases {nb!r} (want false: the live world is X-COM's)"] if nb is not False else []
    wbad += [f"pvpBorrow.parked {pv} != HOST0 {want}"] if pv != want else []
    cell("C1-world", not wbad, "; ".join(wbad) or f"host borrows (active), noBases false; parked {want}")
    rc = host.cmd({"cmd": "research_check", "topic": TOPIC})
    seats = {e.get("seat"): e.get("researched") for e in rc.get("seats") or []}
    live = host.cmd({"cmd": "is_researched", "topic": TOPIC}).get("researched")
    ev.update(researchCheck=rc, hostLiveResearched=live)
    rbad = [] if rc.get("separate") is True else [f"research_check.separate {rc.get('separate')!r} (want true)"]
    rbad += [f"seat 0 researched {seats.get(0)!r} (want true: the parked alien world)"] if seats.get(0) is not True else []
    rbad += [f"seat 1 researched {seats.get(1)!r} (want false)"] if seats.get(1) is not False else []
    rbad += [f"host is_researched {live!r} (want false: the live world is X-COM's)"] if live is not False else []
    cell("C1-research", not rbad, "; ".join(rbad) or f"{TOPIC}: separate, seat 0 true, seat 1 false, the live world false")
    common("C1", host, client, crash0)
    if not sp_ok or turn != [1, 1]:
        ctx["blocked"] = "the entry spine did not reach turn 1 (C1-entry)"
    return names


def row_c2(host, client, ctx, ev):
    names = ["C2-walk", "C2-side", "C2-common"]
    if ctx["blocked"]:
        block(names, ctx["blocked"])
        return names
    crash0 = crash_set()
    try:
        ev["reactions"] = G3F.reactions_zero(host, client)
        sid, tile, dest, seen = walk_target(host, 0)
        ev.update(S=sid, S_tile=tile, S_DEST=dest, S_pin=S_PIN, S_neighbours=seen)
        if dest is None:
            cell("C2-walk", False, f"staging: no free neighbour for S {sid} at {tile} by the rule (FIXTURE-STOP, STOP-IF 13): {seen}")
        else:
            ctx0 = event_state(host).get("closedContexts") or []
            prev = session.walk_action_id(host)
            ev["walk"] = {k: v for k, v in session.send_walk(client, sid, dest).items() if k in ("ok", "error", "iseq")}
            session.wait_walk_settled(host, client, prev, timeout=STEP_S)
            new = G3F.new_contexts(ctx0, event_state(host).get("closedContexts"))
            ps = [G3F.pos(host, sid), G3F.pos(client, sid)]
            ev.update(newContexts=new, Spos=ps)
            ok, detail = G3F.ctx_cell(new, "intent", sid)
            wbad = [] if ok else [detail]
            wbad += [f"S {sid} at host/client {ps} (want {dest} on both)"] if ps != [dest, dest] else []
            cell("C2-walk", not wbad, "; ".join(wbad) or f"one {{intent, walk, {sid}}} context; S on {dest} on both")
    except Exception as e:  # noqa: BLE001
        cell("C2-walk", False, f"{type(e).__name__}: {str(e)[:400]}")
    try:
        ev["endTurn"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        RSB.drive_side_change(host, client, 1, timeout=STEP_S)
    except Exception as e:  # noqa: BLE001
        ev["sideError"] = str(e)[:300]
    ts = [(battle_state(gc).get("turn"), battle_state(gc).get("side")) for gc in (host, client)]
    ev["turnSide"] = ts
    cell("C2-side", [s for _t, s in ts] == [1, 1], f"(turn, side) host/client {ts} (want side 1 on both after the client's END "
         f"TURN){'; ' + ev['sideError'] if ev.get('sideError') else ''}")
    common("C2", host, client, crash0)
    if [s for _t, s in ts] != [1, 1]:
        ctx["blocked"] = "the aliens' side never began on both (C2-side)"
    return names


def row_c3(host, client, ctx, ev):
    names = ["C3-sel", "C3-ctx", "C3-pos", "C3-side", "C3-common"]
    if ctx["blocked"]:
        block(names, ctx["blocked"])
        return names
    crash0 = crash_set()
    try:
        aid, tile, dest, seen = walk_target(host, 1)
        ev.update(A=aid, A_tile=tile, A_DEST=dest, A_pin=A_PIN, A_neighbours=seen, sel0=battle_state(host).get("selectedId"))
        host.ok({"cmd": "inject_input", "kind": "key", "key": G3F.SDLK_TAB})   # ONE TAB first (G3F G4)
        time.sleep(0.15)
        ev["tab"] = G3F.tab_select(host, aid)
        sel = battle_state(host).get("selectedId")
        ev["sel"] = sel
        cell("C3-sel", sel == aid, f"host selectedId {sel} before the click (want A {aid})")
        if dest is None:
            block(["C3-ctx", "C3-pos"], f"staging: no free neighbour for A {aid} at {tile} by the rule (FIXTURE-STOP, "
                  f"STOP-IF 13): {seen}")
        elif sel != aid:
            block(["C3-ctx", "C3-pos"], "staging (the host's TAB never selected A)")
        else:
            b_ctx = event_state(host).get("closedContexts") or []
            G3F.real_click_walk(host, dest)
            G3F.walk_done(host, client, aid, dest, ev)
            new = G3F.new_contexts(b_ctx, event_state(host).get("closedContexts"))
            pa, sides = [G3F.pos(host, aid), G3F.pos(client, aid)], [battle_state(gc).get("side") for gc in (host, client)]
            ev.update(newContexts=new, Apos=pa, sides=sides)
            ok, detail = G3F.ctx_cell(new, "host", aid)
            cell("C3-ctx", ok, detail)
            cell("C3-pos", pa == [dest, dest] and sides == [1, 1], f"A {aid} host/client {pa} (want {dest} on both; "
                 f"{ev.get('walkS')} s), side {sides} (want 1 on both)")
    except Exception as e:  # noqa: BLE001
        block(["C3-sel", "C3-ctx", "C3-pos"], f"{type(e).__name__}: {str(e)[:400]}")
    try:
        ev["endTurn"] = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        RSB.drive_side_change(host, client, 0, want_turn_min=2, timeout=STEP_S)
    except Exception as e:  # noqa: BLE001
        ev["sideError"] = str(e)[:300]
    ts = [(battle_state(gc).get("turn"), battle_state(gc).get("side")) for gc in (host, client)]
    ev["turnSide"] = ts
    cell("C3-side", ts == [(2, 0), (2, 0)], f"(turn, side) host/client {ts} (want (2, 0) on both after the host's END TURN)"
         f"{'; ' + ev['sideError'] if ev.get('sideError') else ''}")
    common("C3", host, client, crash0)
    return names


def run(host, client):
    ctx = {"blocked": None}
    ev0 = {}
    host0, client0, xb = bring_up(host, client, ev0)
    crash0 = crash_set()   # the crash baseline: staging and the entry count in C1-common
    evidence("C-gm", ev0)
    row_verdict("C-gm", ["C-gm"])
    ev1 = {}
    squad = stage_landing(host, client, xb, client0, ev1)
    names = row_c1(host, client, host0, client0, squad, ctx, ev1, crash0)
    evidence("C1", ev1)
    row_verdict("C1", names)
    ev2 = {}
    names = row_c2(host, client, ctx, ev2)
    evidence("C2", ev2)
    row_verdict("C2", names)
    ev3 = {}
    names = row_c3(host, client, ctx, ev3)
    evidence("C3", ev3)
    row_verdict("C3", names)


def main():
    host = GameClient("host", None, make_user_dir("d250uc1_c_host"))
    client = GameClient("client", None, make_user_dir("d250uc1_c_client"))
    t0 = time.time()
    try:
        run(host, client)
    except FixtureMiss as e:
        block(ALL_CELLS, f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
        block(ALL_CELLS, f"error {type(e).__name__}: {str(e)[:200]}")
    finally:
        try:
            host.shutdown()
        finally:
            client.shutdown()
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== D250-U S-C1 gm3 PvP campaign battle entry: {len(RESULTS) - len(fails)}/{len(RESULTS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(ALL_CELLS) else 2)


if __name__ == "__main__":
    main()
