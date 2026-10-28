"""D250-U S-C3 - test_campaign_gm3_rejoin.py: gm3 PvP campaign battles (host = the aliens, client = X-COM) when the alien host is
off its globe, when the X-COM player drops mid-battle and rejoins, and when a borrowed battle start is refused.

Spec: docs rewrite/prompts/d250u_pvp_campaigns_sc.md, AMENDMENT SC-3 (SC3-3 "Stage S-C3", SC3-5 file A, SC3-6 FX3-1 .. FX3-19) and its
rulings: QC-13 (a), QC3-1 .. QC3-6 (a), R-D250-SC3-1; owner D250, O1 (a); L-H37-1, L-H38-1, L-H38-2; VL-C-2, VL-C-9, VL-C3-1, VL-C3-2.
TASK 0 pins: docs rewrite/d250u-task0/sc3/CONSTANTS.md (boot Fa on the unchanged build; d250ucc-red).

Boot F: gm3, lobby key 48015, dirs d250uc3_f_host / d250uc3_f_client / d250uc3_f_client2. Bring-up (FX3-2): PF.start_pvp_campaign
(alien_player="host"); HOST0 / CLIENT0; gamemode 3 on both, host noBases true and client noBases false are preconditions; geo.slow_clock.
A bring-up or staging miss is a FIXTURE-STOP: ONE "CAPTURE F:" line (both stacks, battle_state phase / side / turn when safe,
coop_dialog_info, get_coop, the last 40 engine log lines) and every remaining cell FAILs "boot".
Rows and cells (one PASS / FAIL line per cell, one EVIDENCE line and one ROW line per row; every row runs after a failure unless its
precondition was never reached, then each of its cells FAILs "blocked: <why>"):
  F5 the landing waits for the host's globe (L-H38-2, VL-C-2): stage_to_prompt; host open_screen stores (FX3-8); client set_seed 1 +
     confirm_landing; HOLD_S 3 s of samples; host close_screens; both inBattle; the spine; the screen record.
     F5-wait (every sample: client top CoopState code 3, host top StoresState, host pvpBorrow pending true and no borrow; armed >= 1 at
     the last), F5-entry (both inBattle, spine, pvpBorrow borrowed 1 / active / site / mirror, WIN == [pop CoopState 1]), F5-common.
  F2 the X-COM player drops and rejoins (L-H37-1): CR.baseline; one client move; client.kill(); CR.pause; CR.rejoin + CR.resume
     (client2); CR.walk_far; the win (FX3-13); both debriefings; client2's OK, then the host's (FX3-14).
     F2-target (S1 / S2: the borrowed craft heads for the battle's coop site), F2-back (pause, rejoin, RESUME, the same battle, split,
     hash, client2's walk), F2-title ("Aliens defeated" on both), F2-return (client2's borrowed return), F2-alien (the host home),
     F2-common (desyncSeen false, 0 new crash files, client2 zero-disk).
  F1 a refused borrowed start (QC-13, L-H38-1): client2 stages at X + (-0.35, 0.10); host corrupt_next_blob; client2 confirms.
     F1-refused (refuse / MISMATCH / UNWIND "(refused)", nobody in battle), F1-home (the host back on its own world), F1-release
     (client2's hold closed, its craft home, its mirror kept), F1-common.
RED (C3R, the unchanged product; TASK 0 boot Fa): 9/13 - FAIL F2-target, F2-title, F1-home, F1-release. GREEN (C3G): 13/13.

WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_campaign_gm3_rejoin.py
"""

import glob
import json
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import event_state  # noqa: E402
import geo  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import test_battle_end_separate as BES  # noqa: E402
import test_campaign_battle_gm2 as G2F  # noqa: E402
import test_campaign_battle_gm3 as G3C1  # noqa: E402
import test_campaign_battle_gm3_end as G3E  # noqa: E402
import test_campaign_rejoin as CR  # noqa: E402
import test_pvp_borrowed_target as BT37  # noqa: E402
import test_pvp_landing_hold as H38F  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402

# ----- TASK 0 pins (docs rewrite/d250u-task0/sc3/CONSTANTS.md, boot Fa) -----
KEY = "48015"
SEED = 1                                     # set on the X-COM client right before each confirm_landing (F13986)
TITLE_WIN = "Aliens defeated"                # FX3-18 (S-C2's TITLE_WIN, F15071); the red shows "Base is saved" (F15554)
MAP_FP_PIN = 5.996615470105667e+18           # EVIDENCE: F5's map on the unchanged build (= S-C1's MAP_FP_C1)
S_PIN = (1, (34, 9, 1), (35, 10, 1))         # EVIDENCE: F2's client move by G3C1's rule
SITE = {"mission": "STR_ALIEN_RESEARCH", "deployment": "STR_MEDIUM_SCOUT", "race": "STR_SECTOID", "hours": 240}   # FX3-4
POINT = {"F5": (0.35, 0.10), "F1": (-0.35, 0.10)}           # FX3-3: X + point (no swap needed, TASK 0)
CRAFT_AT = {"F5": (0.34, 0.10), "F1": (-0.34, 0.10)}        # FX3-5: 0.01 rad short in longitude, toward X
SQUAD = 2
REFUSE, MISMATCH, UNWIND = "battle_refuse received (battleId=", "battle blob sha MISMATCH (battleId=", "W2-H24: failed battle start ("
# ----- bounds -----
HOLD_S, HOLD_POLL = 3.0, 0.25
MIRROR_S = 30
LANDING_S = 180
BOTH_IN_S = 60
ACTIVE_S = 5
STEP_S = 30
TOPS_S = 60
DEBRIEF_S = 60
CLIENT_DEBRIEF_S = 20
OK_S = 10
HOST_OK_S = 60
SITE_S = 10
REFUSE_S = 30
HOME_S = 10
ROWS = {"F5": ["F5-wait", "F5-entry", "F5-common"],
        "F2": ["F2-target", "F2-back", "F2-title", "F2-return", "F2-alien", "F2-common"],
        "F1": ["F1-refused", "F1-home", "F1-release", "F1-common"]}
ALL_CELLS = ROWS["F5"] + ROWS["F2"] + ROWS["F1"]


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


def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def since(gc, n0, needle):
    return [ln.split("\t")[-1][:220] for ln in logl(gc)[n0:] if needle in ln]


def icons(gc):
    return [b.get("name") for b in gc.ok({"cmd": "geo_state"}).get("bases", []) if b.get("coopIcon")]


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
    print(f"CAPTURE F: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def common_bad(host, other, crash0):
    eh, eo = event_state(host), event_state(other)
    new = sorted(crash_set() - crash0)
    bad = []
    if eh.get("desyncSeen") is not False or eo.get("desyncSeen") is not False:
        bad.append(f"desyncSeen host {eh.get('desyncSeen')!r} {other.name} {eo.get('desyncSeen')!r} (want false on both)")
    if new:
        bad.append(f"{len(new)} new crash file(s) since the row's start (first {os.path.basename(new[0])})")
    return bad


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
    """G3E's stage_row up to, not including, set_seed / confirm_landing (FX3-3 .. FX3-7). Returns (site_id, point, sq, missions0)."""
    geo.slow_clock(host, client)
    sky = client0["sky"]
    sb = next((b for b in client.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    recs = {sid: G3E.srec(client, sid) for sid in sids}
    sq = [sid for sid in sids if recs[sid].get("where") == "base" and recs[sid].get("recovery") == 0][:SQUAD]
    if len(sq) < SQUAD:
        seen = {s: (recs[s].get("where"), recs[s].get("recovery")) for s in sids}
        capture_boot(f"{row}: fewer than {SQUAD} {client.name} soldiers in base with recovery 0 (FX3-6): {seen}", host, client)
    asg = [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": False}) for sid in sids]
    asg += [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": True}) for sid in sq]
    if not all(r.get("ok") for r in asg):
        capture_boot(f"{row}: {client.name} craft_assign (SQ {sq}): {[r for r in asg if not r.get('ok')][:2]}", host, client)
    missions0 = {sid: G3E.srec(client, sid).get("missions") for sid in sq}
    ev.update(SQ=sq, missions0=missions0)
    dx, dy = POINT[row]
    point = [xb["lon"] + dx, xb["lat"] + dy]
    site = host.cmd(dict(SITE, cmd="spawn_mission_site", lon=point[0], lat=point[1]))
    if not site.get("ok"):
        capture_boot(f"{row}: host spawn_mission_site {site}", host, client)
    t0, mir = time.time(), None
    while mir is None and time.time() - t0 < MIRROR_S:
        mir = next((m for m in client.ok({"cmd": "geo_state"}).get("missionSites", [])
                    if m.get("coop") and abs(m.get("lon", 9.0) - point[0]) < 0.01 and abs(m.get("lat", 9.0) - point[1]) < 0.01),
                   None)
        if mir is None:
            time.sleep(0.1)
    ev.update(point=point, siteHost=site.get("site_id"), mirrorS=round(time.time() - t0, 2), siteClient=mir and mir.get("id"))
    if mir is None:
        capture_boot(f"{row}: no coop mirror of host site {site.get('site_id')} on {client.name} within {MIRROR_S} s", host, client)
    cx, cy = CRAFT_AT[row]
    cf = client.cmd({"cmd": "craft_force", "craft_id": sky["id"], "status": "STR_OUT", "lon": xb["lon"] + cx, "lat": xb["lat"] + cy,
                     "dest": f"site:{mir['id']}", "fuel": 999999, "lowFuel": False})
    if not cf.get("ok"):
        capture_boot(f"{row}: {client.name} craft_force {cf}", host, client)

    def prompt():
        if session.has_state(client, "ConfirmLandingState"):
            return True
        for gc in (host, client):
            geo.drain_popups(gc, interest=geo.popup("ConfirmLandingState"))
            gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None
    t1 = time.time()
    try:
        client.wait_for(f"{client.name} landing prompt", prompt, timeout=LANDING_S, interval=0.25)
    except Exception as e:  # noqa: BLE001
        capture_boot(f"{row}: {client.name} landing prompt: {e}", host, client)
    ev.update(promptS=round(time.time() - t1, 2), hostStackAtPrompt=stack(host))
    return site.get("site_id"), point, sq, missions0


def confirm(row, host, client):
    sd, cl = client.cmd({"cmd": "set_seed", "seed": SEED}), client.cmd({"cmd": "confirm_landing"})
    if not sd.get("ok") or not cl.get("ok"):
        capture_boot(f"{row}: {client.name} set_seed {sd} / confirm_landing {cl}", host, client)


def row_f5(host, client, xb, client0, ctx, ev):
    names = ROWS["F5"]
    crash0 = crash_set()
    t_row = time.time()
    staged = stage_to_prompt("F5", host, client, xb, client0, ev)
    ev["openScreen"] = host.cmd({"cmd": "open_screen", "screen": "stores"})
    if top(host) != "StoresState":
        capture_boot(f"F5: host open_screen stores (FX3-8): {ev['openScreen']}, top {top(host)}", host, client)
    cursor = geo._log_cursor(client)
    confirm("F5", host, client)
    t_c = time.time()
    samples = []
    while time.time() - t_c < HOLD_S:
        s = H38F.sample(host, client, t_c)
        pv = pvp(host)
        s.update(hostTop=top(host), hostPv={k: pv.get(k) for k in ("pending", "armed", "borrowed")})
        samples.append(s)
        time.sleep(HOLD_POLL)
    cs = host.cmd({"cmd": "close_screens"})
    t_close = time.time()
    ev["closeScreens"] = cs
    if not cs.get("ok") or (cs.get("popped") or 0) < 1:
        capture_boot(f"F5: host close_screens (FX3-8, popped >= 1): {cs}", host, client)
    wbad = [] if samples else ["no HOLD sample"]
    for s in samples:
        if s["top"] != "CoopState" or s.get("code") != 3:
            wbad.append(f"t {s['t']}: client top {s['top']} code {s.get('code')!r} (want CoopState 3)")
        if s["hostTop"] != "StoresState":
            wbad.append(f"t {s['t']}: host top {s['hostTop']} (want StoresState)")
        if s["hostPv"].get("pending") is not True or s["hostPv"].get("borrowed") not in (None, 0):
            wbad.append(f"t {s['t']}: host pvpBorrow {s['hostPv']} (want pending true, no borrow)")
    if samples and (samples[-1]["hostPv"].get("armed") or 0) < 1:
        wbad.append(f"host pvpBorrow.armed {samples[-1]['hostPv'].get('armed')!r} at the last sample (want >= 1)")
    cell("F5-wait", not wbad, "; ".join(wbad[:4]) or f"{len(samples)} HOLD samples: client on CoopState 3, host on StoresState, "
         f"host pvpBorrow pending true without a borrow, armed {samples[-1]['hostPv'].get('armed')} at the last")
    ok, secs = BES.wait_until(lambda: G3C1.in_battle(host) and G3C1.in_battle(client), BOTH_IN_S)
    sp_ok, sp_detail = False, "not run (not both inBattle)"
    if ok:
        try:
            session.briefings_to_battlescape(host, client)
            sp_ok, sp_detail = True, "spine passed"
        except Exception as e:  # noqa: BLE001
            sp_detail = f"session.briefings_to_battlescape raised: {str(e)[:300]} (stacks {[stack(host), stack(client)]})"
    BES.wait_until(lambda: any(k == "ACTIVE" for _s, k, _e in H38F.screen_record(client, cursor)), ACTIVE_S)
    rec = H38F.screen_record(client, cursor)
    hand = next((i for i, r in enumerate(rec) if r[1] == "HAND"), None)
    entry = None if hand is None else next((i for i in range(hand + 1, len(rec)) if rec[i][1] == "ui"
                                            and rec[i][2][:2] == ("push", "BattlescapeState")), None)
    win = None if entry is None else [r[2] for r in rec[hand + 1:entry] if r[1] == "ui"]
    hp = pvp(host)
    ebad = [] if ok else [f"inBattle host/client {[G3C1.in_battle(host), G3C1.in_battle(client)]} {secs} s after close_screens"]
    ebad += [] if sp_ok or not ok else [sp_detail]
    ebad += [f"host pvpBorrow.{k} {hp.get(k)!r} (want {w!r})" for k, w in
             (("borrowed", 1), ("active", True), ("targetKind", "site"), ("targetMirror", True)) if hp.get(k) != w]
    if win != [("pop", "CoopState", 1)]:
        ebad.append(f"WIN {win} (want [pop CoopState 1]; HAND {hand is not None}, ENTRY {entry is not None})")
    cell("F5-entry", not ebad, "; ".join(ebad) or f"both inBattle {secs} s after close_screens, spine passed; host pvpBorrow borrowed "
         f"1, active, site (mirror); WIN [pop CoopState 1]")
    cbad = common_bad(host, client, crash0)
    if sp_ok:
        try:
            session.assert_hash_clean(host, client, full=True)
        except Exception as e:  # noqa: BLE001
            cbad.append(f"hash_now full: {str(e)[:400]}")
    else:
        cbad.append("hash_now not run (no spine)")
    cell("F5-common", not cbad, "; ".join(cbad) or "desyncSeen false on both, 0 new crash files, hash_now full EQUAL after the spine")
    bh, bc = session.battle_state(host) if sp_ok else {}, session.battle_state(client) if sp_ok else {}
    ev.update(holdSamples=samples, win=win, pvpBorrowHost=hp, pvpBorrowClient=pvp(client), bothInS=secs,
              entryAfterCloseS=round(time.time() - t_close, 2), mapFingerprint=[bh.get("mapFingerprint"), bc.get("mapFingerprint")],
              mapFpPin=MAP_FP_PIN, turn=[bh.get("turn"), bc.get("turn")], wall=round(time.time() - t_row, 1))
    if not (ok and sp_ok):
        ctx["blocked"] = "the borrowed battle never started (F5-entry)"
    return staged


def row_f2(host, client, x, xb, host0, client0, staged, ctx, ev):
    names = ROWS["F2"]
    if ctx["blocked"]:
        block(names, ctx["blocked"])
        return
    crash0 = crash_set()
    t_row = time.time()
    site5, point5, sq, missions0 = staged
    sky = client0["sky"]
    x.host, x.client = host, client
    try:
        CR.baseline(SimpleNamespace(rid="F2"), x, client)
        ev["reactions"] = G3F.reactions_zero(host, client)
        sid, tile, dest, seen = G3C1.walk_target(host, 0)
        ev.update(S=sid, S_tile=tile, S_DEST=dest, S_pin=S_PIN)
        if dest is None:
            raise RuntimeError(f"no free neighbour for S {sid} at {tile} by G3C1's rule: {seen}")
        prev = session.walk_action_id(host)
        ev["walk"] = {k: v for k, v in session.send_walk(client, sid, dest).items() if k in ("ok", "error", "iseq")}
        session.wait_walk_settled(host, client, prev, timeout=STEP_S)
        ev["Spos"] = [G3F.pos(host, sid), G3F.pos(client, sid)]
    except FixtureMiss:
        raise
    except Exception as e:  # noqa: BLE001
        capture_boot(f"F2 staging (CR.baseline / the client move): {str(e)[:300]}", host, client)
    ev["baseline"] = {"B0": x.b0, "T0": x.t0, "SPLIT0": x.split0}
    target = pvp(host).get("targetCoopId")
    t_s = time.time()
    ev.update(TARGET=target, S0=BT37.sample(host, xb["name"], sky, t_s), iconsBeforeKill=icons(host))
    client.kill()
    pok, pv = CR.pause(x)
    s1 = BT37.sample(host, xb["name"], sky, t_s)
    ev.update(pause=pv, S1=s1)
    rev = {}
    acked = CR.rejoin(x, KEY, rev)
    c2 = x.client2
    resumed = acked and CR.resume(x, rev)
    tops, tops_s = BES.wait_until(lambda: top(host) == "BattlescapeState" and top(c2) == "BattlescapeState", TOPS_S) if resumed \
        else (False, 0)
    s2 = BT37.sample(host, xb["name"], sky, t_s) if tops else None
    ev.update(rejoin=rev, acked=acked, resumed=resumed, topsS=tops_s, S2=s2, iconsAfterRejoin=icons(host))
    tbad = []
    for nm, s in (("S1", s1), ("S2", s2)):
        if s is None:
            tbad.append(f"{nm} not taken (no RESUME)")
            continue
        hits = [c for c in s["sites"] if c["coopId"] == target]
        if s["destKind"] != "site" or len(hits) != 1 or s["destId"] != hits[0]["id"]:
            tbad.append(f"{nm}: destKind {s['destKind']!r} destId {s['destId']} coop sites {s['sites']} (want 'site' heading for the "
                        f"one coop site with coopId {target})")
    cell("F2-target", not tbad, "; ".join(tbad) or f"S1 and S2: the borrowed craft heads for the one coop site with coopId {target}")
    bbad = [] if pok else [f"CR.pause not passed within {CR.W_PAUSE:.0f} s ({pv.get('wait')})"]
    bbad += [] if acked else [f"the rejoin never acked ({rev.get('ack wait')})"]
    bbad += [] if resumed else ["RESUME not pressed"]
    walked = False
    if tops:
        ha, ca = CR.auth(host), CR.auth(c2)
        for nm, a in (("host", ha), ("client2", ca)):
            if a.get("phase") != "Active" or a.get("peerAbsent") is not False or a.get("battleId") != x.b0:
                bbad.append(f"{nm} phase {a.get('phase')!r} peerAbsent {a.get('peerAbsent')!r} battleId {a.get('battleId')!r} "
                            f"(want Active / false / B0 {x.b0})")
        if ha.get("turn") != x.t0:
            bbad.append(f"host turn {ha.get('turn')!r} (want T0 {x.t0})")
        sh, sc = CR.split(host), CR.split(c2)
        if not (sh == sc == x.split0):
            bbad.append(f"SPLIT host {sh} client2 {sc} (want SPLIT0 {x.split0})")
        hok, hev = CR.hash_ok(host, c2, "F2 after RESUME")
        bbad += [] if hok else [f"CR.hash_ok(host, client2): {hev}"]
        wev = {"actor": ev.get("S"), "start": CR.pos(host, ev.get("S"))}
        try:
            hw = CR.walk_far(host, c2, ev.get("S"), wev)
        except Exception as e:  # noqa: BLE001
            hw, wev["error"] = {}, str(e)[:300]
        steps = hw.get("steps") or []
        wev.update(steps=len(steps), host=CR.pos(host, ev.get("S")), client2=CR.pos(c2, ev.get("S")))
        walked = bool(steps) and wev["host"] is not None and wev["host"] == wev["client2"]
        bbad += [] if walked else [f"client2's walk {wev} (want >= 1 step, the final tile equal on both)"]
        ev.update(authAfter=[ha, ca], split=[sh, sc], hash=hev, walkFar=wev)
    elif resumed:
        bbad.append(f"tops host {top(host)} client2 {top(c2)} (want BattlescapeState on both within {TOPS_S} s)")
    cell("F2-back", not bbad, "; ".join(bbad) or f"pause, rejoin ack {rev.get('ack s')} s, RESUME; the same battle B0 {x.b0} at turn "
         f"T0 {x.t0} on both, SPLIT0, hash EQUAL, client2's walk applied")
    rest = ["F2-title", "F2-return", "F2-alien"]
    if not tops:
        block(rest, "the rejoin never resumed the borrowed battle (F2-back)")
        ctx["blocked"] = "no client2 in its own world (F2-back)"
    else:
        f2_end(host, c2, site5, point5, sq, missions0, host0, sky, ctx, ev)
    cbad = common_bad(host, c2, crash0) if alive(c2) else ["client2 not running"]
    try:
        zd = (session.assert_client_zero_disk(c2.user_dir) or "clean") if c2 is not None else "client2 never started"
    except AssertionError as e:
        zd = str(e)[:300]
    cbad += [] if zd == "clean" else [f"client2 zero-disk: {zd}"]
    cell("F2-common", not cbad, "; ".join(cbad) or "desyncSeen false on host and client2, 0 new crash files, client2 zero-disk")
    ev["wall"] = round(time.time() - t_row, 1)


def f2_end(host, c2, site5, point5, sq, missions0, host0, sky, ctx, ev):
    """The win (FX3-13), both debriefings, client2's OK, then the host's (FX3-14); cells F2-title, F2-return, F2-alien."""
    a = {}
    G2F.kill_all(host, c2, 1, a, "kills")
    if "DebriefingState" not in stack(host):
        a["endTurn"] = c2.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        a["closeNext"] = BES.close_host_nextturn(host)
    ev["win"] = a
    ok, secs = BES.wait_until(lambda: "DebriefingState" in stack(host), DEBRIEF_S)
    hd = G3E.deb(host)
    cok, csecs = BES.wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                         and d.get("displayOnly") is True)(G3E.deb(c2)), CLIENT_DEBRIEF_S) if ok else (False, 0)
    cd = G3E.deb(c2)
    ev.update(hostDebrief={k: hd.get(k) for k in ("title", "displayOnly", "rating", "total")},
              clientDebrief={k: cd.get(k) for k in ("title", "displayOnly", "shown")}, debriefS=[secs, csecs])
    tbad = [] if ok else [f"no host DebriefingState within {DEBRIEF_S} s (stack {stack(host)})"]
    if ok:
        tbad += [f"host title {hd.get('title')!r} (want {TITLE_WIN!r})"] if hd.get("title") != TITLE_WIN else []
        tbad += [f"host displayOnly {hd.get('displayOnly')!r} (want false)"] if hd.get("displayOnly") is not False else []
        tbad += [] if cok else [f"no client2 display-only DebriefingState within {CLIENT_DEBRIEF_S} s (stack {stack(c2)})"]
        tbad += [f"client2 title {cd.get('title')!r} != host {hd.get('title')!r}"] if cok and cd.get("title") != hd.get("title") else []
    cell("F2-title", not tbad, "; ".join(tbad) or f"host DebriefingState {secs} s, title {TITLE_WIN!r}, displayOnly false; client2's "
         f"display-only title equal")
    if not ok:
        block(["F2-return", "F2-alien"], "no host debriefing (F2-title)")
        ctx["blocked"] = "the rejoined battle never debriefed (F2-title)"
        return
    t_ok = time.time()
    pk = BES.press_ok(c2)
    _r, cscr = BES.drain(c2, timeout=OK_S)
    gok, _gs = BES.wait_until(lambda: BES.geo_clean(c2), OK_S)
    crec, csky, cco = BES.record(c2), G3E.sky_of(c2, sky), G3E.coop(c2)
    csq = {sid: G3E.srec(c2, sid) for sid in sq}
    ev["client2Ok"] = {"press": pk, "drain": cscr, "geoClean": gok, "s": round(time.time() - t_ok, 2), "stack": stack(c2),
                       "debriefOkBranch": crec.get("debriefOkBranch"), "worldAdopted": crec.get("worldAdopted"), "sky": csky,
                       "noBases": cco.get("noBases"), "sq": {s: {k: csq[s].get(k) for k in ("where", "missions")} for s in sq}}
    rbad = [] if gok else [f"client2 not on a clean GeoscapeState {OK_S} s after its OK (stack {stack(c2)})"]
    rbad += [f"battleEnd.debriefOkBranch {crec.get('debriefOkBranch')!r} (want 'campaign-client-borrowed')"] \
        if crec.get("debriefOkBranch") != "campaign-client-borrowed" else []
    rbad += [f"battleEnd.worldAdopted {crec.get('worldAdopted')!r} (want 1)"] if crec.get("worldAdopted") != 1 else []
    for sid in sq:
        want = missions0[sid] + 1 if isinstance(missions0[sid], int) else None
        if csq[sid].get("where") != "base" or csq[sid].get("missions") != want:
            rbad.append(f"SQ {sid}: where {csq[sid].get('where')!r} missions {csq[sid].get('missions')!r} (want 'base', {want})")
    rbad += [] if G3E.returning_or_at_base(csky) else [f"client2 Skyranger {csky} (want returning or at base)"]
    rbad += [f"client2 noBases {cco.get('noBases')!r} (want false)"] if cco.get("noBases") is not False else []
    cell("F2-return", not rbad, "; ".join(rbad) or f"client2 geo_clean; campaign-client-borrowed, worldAdopted 1; every SQ soldier in "
         f"base with missions + 1; Skyranger {csky}; noBases false")
    hk = BES.press_ok(host)
    hreached, hscr, on994 = G2F.drain_host(host)
    hgok, hgs = BES.wait_until(lambda: BES.geo_clean(host), HOST_OK_S) if hreached else (False, 0)
    hco, hg = G3E.coop(host), host.ok({"cmd": "geo_state"})
    pv = hco.get("pvpBorrow") or {}
    gone, gone_s = BES.wait_until(lambda: not G3E.has_site(host, site_id=site5) and not G3E.has_site(c2, point=point5), SITE_S)
    ev["hostOk"] = {"press": hk, "drain": hscr, "on994": on994, "geoClean": hgok, "geoS": hgs, "stack": stack(host),
                    "noBases": hco.get("noBases"), "funds": hg.get("funds"), "realBases": G3E.real_bases(hg), "pvpBorrow": pv,
                    "siteGoneS": gone_s, "icons": icons(host)}
    abad = [] if hgok else [f"host not on a clean GeoscapeState after its OK (reached {hreached}, 994 {on994}, stack {stack(host)})"]
    abad += [f"host noBases {hco.get('noBases')!r} (want true)"] if hco.get("noBases") is not True else []
    abad += [f"host funds {hg.get('funds')!r} (want HOST0 {host0['funds']!r})"] if hg.get("funds") != host0["funds"] else []
    abad += [f"host real bases {G3E.real_bases(hg)} (want HOST0 {host0['realBases']})"] \
        if G3E.real_bases(hg) != host0["realBases"] else []
    abad += [f"host pvpBorrow.active {pv.get('active')!r} (want false)"] if pv.get("active") is not False else []
    abad += [f"host pvpBorrow.home {pv.get('home')} != parked {pv.get('parked')}"] if "home" not in pv or pv.get("home") != pv.get(
        "parked") else []
    fate = pv.get("fate") or {}
    abad += [f"host pvpBorrow.fate {pv.get('fate')!r} (want kind 'site', action 'deleted')"] \
        if fate.get("kind") != "site" or fate.get("action") != "deleted" else []
    abad += [] if gone else [f"after {SITE_S} s: host site {site5} present {G3E.has_site(host, site_id=site5)}, client2 mirror present "
                             f"{G3E.has_site(c2, point=point5)} (want both gone)"]
    cell("F2-alien", not abad, "; ".join(abad) or f"host geo_clean ({hgs} s), noBases true, funds and real bases == HOST0, active false, "
         f"home == parked, fate site deleted; F5's site and client2's mirror gone ({gone_s} s)")
    if gok and hgok:
        ctx["xcom"] = c2
    else:
        ctx["blocked"] = "client2 or the host never reached its geoscape after the battle (F2-return / F2-alien)"


def row_f1(host, xb, host0, client0, ctx, ev):
    names = ROWS["F1"]
    c2 = ctx.get("xcom")
    if c2 is None:
        block(names, ctx["blocked"] or "no X-COM player on its geoscape (F2)")
        return
    crash0 = crash_set()
    t_row = time.time()
    site1, point1, _sq, _m = stage_to_prompt("F1", host, c2, xb, client0, ev)
    hp0, cp0 = pvp(host), pvp(c2)
    n_h, n_c = len(logl(host)), len(logl(c2))
    cb = host.cmd({"cmd": "corrupt_next_blob"})
    if not cb.get("ok"):
        capture_boot(f"F1: host corrupt_next_blob {cb}", host, c2)
    confirm("F1", host, c2)
    rok, rs = BES.wait_until(lambda: bool(since(host, n_h, REFUSE)), REFUSE_S)
    hok, hs = BES.wait_until(lambda: top(host) == "GeoscapeState" and pvp(host).get("active") is False, HOME_S)
    cok, cs = BES.wait_until(lambda: top(c2) == "GeoscapeState", HOME_S)
    ref, mis, unw = since(host, n_h, REFUSE), since(c2, n_c, MISMATCH), since(host, n_h, UNWIND)
    inb = [G3E.coop(host).get("inBattle"), G3E.coop(c2).get("inBattle")]
    fbad = [] if len(ref) == 1 and "reason=corrupt" in ref[0] else [f"host refuse lines {ref} (want 1 reading reason=corrupt)"]
    fbad += [] if len(mis) == 1 else [f"client2 MISMATCH lines {mis} (want 1)"]
    fbad += [] if len(unw) == 1 and "(refused)" in unw[0] else [f"host UNWIND lines {unw} (want 1 reading (refused))"]
    fbad += [f"get_coop.inBattle host/client2 {inb} (want false on both)"] if inb != [False, False] else []
    cell("F1-refused", not fbad, "; ".join(fbad) or f"host refuse +1 (reason=corrupt, {rs} s), client2 MISMATCH +1, host UNWIND +1 "
         f"(refused); nobody in battle")
    hp, hco, hg = pvp(host), G3E.coop(host), host.ok({"cmd": "geo_state"})
    hst = stack(host)
    nb = lambda d, k: d.get(k) or 0  # noqa: E731
    hbad = [f"host stack {hst} (want top GeoscapeState)"] if hst[-1:] != ["GeoscapeState"] else []
    hbad += [f"host pvpBorrow.active {hp.get('active')!r} (want false)"] if hp.get("active") is not False else []
    hbad += [f"host pvpBorrow.{k} {hp.get(k)!r} (want {nb(hp0, k) + 1})" for k in ("swappedBack", "refusedSent")
             if nb(hp, k) != nb(hp0, k) + 1]
    hbad += [f"host pvpBorrow.lastRefuse {hp.get('lastRefuse')!r} (want 'refused')"] if hp.get("lastRefuse") != "refused" else []
    hbad += [f"host noBases {hco.get('noBases')!r} (want true)"] if hco.get("noBases") is not True else []
    hbad += [f"host funds {hg.get('funds')!r} (want HOST0 {host0['funds']!r})"] if hg.get("funds") != host0["funds"] else []
    hbad += [f"host real bases {G3E.real_bases(hg)} (want HOST0 {host0['realBases']})"] \
        if G3E.real_bases(hg) != host0["realBases"] else []
    hbad += [] if G3E.has_site(host, site_id=site1) else [f"host's real F1 site {site1} not in its missionSites"]
    cell("F1-home", not hbad, "; ".join(hbad) or f"host back on its own world ({hs} s): top GeoscapeState, active false, swappedBack "
         f"and refusedSent +1, lastRefuse 'refused', noBases true, funds and real bases == HOST0, its F1 site kept")
    cp, cst, cdl = pvp(c2), stack(c2), c2.cmd({"cmd": "coop_dialog_info"})
    csky = G3E.sky_of(c2, client0["sky"])
    rbad = [f"client2 stack {cst} (want top GeoscapeState)"] if cst[-1:] != ["GeoscapeState"] else []
    rbad += [f"client2 holds CoopState code 3 ({cdl.get('title')!r})"] if "CoopState" in cst and cdl.get("code") == 3 else []
    rbad += [f"client2 pvpBorrow.{k} {cp.get(k)!r} (want {nb(cp0, k) + 1})" for k in ("refusedSeen", "released")
             if nb(cp, k) != nb(cp0, k) + 1]
    rbad += [f"client2 pvpBorrow.lastRefuseSeen {cp.get('lastRefuseSeen')!r} (want 'refused')"] \
        if cp.get("lastRefuseSeen") != "refused" else []
    rbad += [] if G3E.returning_or_at_base(csky) else [f"client2 Skyranger {csky} (want returning or at base)"]
    rbad += [] if G3E.has_site(c2, point=point1) else ["client2's mirror of the F1 site is gone"]
    cell("F1-release", not rbad, "; ".join(rbad) or f"client2 on its GeoscapeState ({cs} s), hold closed; refusedSeen / released +1, "
         f"lastRefuseSeen 'refused'; Skyranger {csky}; the F1 mirror kept")
    cbad = common_bad(host, c2, crash0)
    cell("F1-common", not cbad, "; ".join(cbad) or "desyncSeen false on both, 0 new crash files")
    ev.update(pvpBefore=[hp0, cp0], pvpAfter=[hp, cp], refuse=ref, mismatch=mis, unwind=unw, waits={"refuse": [rok, rs],
              "hostHome": [hok, hs], "client2Geo": [cok, cs]}, hostStack=hst, client2Stack=cst, client2Dialog=cdl,
              hostGeo={"funds": hg.get("funds"), "realBases": G3E.real_bases(hg), "noBases": hco.get("noBases")},
              wall=round(time.time() - t_row, 1))


def run(host, client, x):
    ctx = {"blocked": None, "xcom": None}
    ev0 = {}
    try:
        host0, client0, xb = bring_up(host, client, KEY, ev0)
    finally:
        evidence("bring-up", ev0)
    for row, fn in (("F5", lambda ev: row_f5(host, client, xb, client0, ctx, ev)),
                    ("F2", lambda ev: row_f2(host, client, x, xb, host0, client0, ctx.get("staged"), ctx, ev)),
                    ("F1", lambda ev: row_f1(host, xb, host0, client0, ctx, ev))):
        ev = {}
        try:
            out = fn(ev)
            if row == "F5":
                ctx["staged"] = out
        except FixtureMiss:
            raise
        except Exception as e:  # noqa: BLE001
            ev["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            block(ROWS[row], f"error {ev['error']}")
            ctx["blocked"] = ctx["blocked"] or f"{row} raised ({ev['error'][:120]})"
            ctx["xcom"] = None
        finally:
            evidence(row, ev)
        row_verdict(row, ROWS[row])


def main():
    host = GameClient("host", None, make_user_dir("d250uc3_f_host"))
    client = GameClient("client", None, make_user_dir("d250uc3_f_client"))
    x = CR.new_x("d250uc3_f")            # CR.rejoin's client2 dir: d250uc3_f_client2
    t0 = time.time()
    try:
        run(host, client, x)
    except FixtureMiss as e:
        block(ALL_CELLS, f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
        block(ALL_CELLS, f"error {type(e).__name__}: {str(e)[:200]}")
    finally:
        for gc in (x.client2, client, host):
            try:
                if gc is not None and gc.proc is not None:
                    gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== D250-U S-C3 gm3 rejoin / failed start: {len(RESULTS) - len(fails)}/{len(ALL_CELLS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(ALL_CELLS) else 2)


if __name__ == "__main__":
    main()
