"""A gm3 PvP campaign battle (host = the aliens, client = X-COM) at the alien host's own target, saved by the alien host
at turn 2 while it borrows the X-COM player's world, then resumed by both players. The resume finds the target on the
alien host's globe by its co-op id, so the battle ends as an unsaved one does: an alien base keeps its co-op id across
the save; a won battle there removes the real base and says "Alien Base destroyed".

Key "49059". Boot a (dirs resume_borrowed_base_host / _client / _client2): row alien_base, the host's alien base
(spawn_alien_base race STR_SECTOID, then host_alien_base_found; ABID = its vanilla Target id, ACOOP = its co-op id),
X-COM wins after the resume. Boot u (dirs resume_borrowed_ufo_*): row ufo_landed, the host's landed UFO (G3T.UFO;
UFOID / UCOOP), X-COM aborts after the resume (a guard: the UFO id already survives a save). Boot a runs and shuts
down, then boot u. Each boot: BR's bring-up (gm3, the host on the Alien team); SQ = the two lowest-id client base
soldiers with recovery 0 alone on its Skyranger (missions0 read after craft_assign); the host's target at X + POINT and
its client mirror (<= MIRROR_S, 0.1 s polls); craft_force to "alienBaseCoop:" / "ufoCoop:" + the co-op id at
X + CRAFT_AT; the landing prompt; client set_seed 1 + confirm_landing; both inBattle; the spine; the host's pvpBorrow
target == the row's; client END TURN to side 1, host END TURN to (turn 2, side 0) = SAVED; the host's quick save (one
new .asav); the file read (PyYAML); both shut down; the host relaunched on its dir, client2 on an EMPTY dir; BR's resume
through the real host window with ONE hook: right after the menu load, while HostMenu is up, the host's own target
(ACOOP_L / UCOOP_L); the host's RESUME; the action (alien_base: kill_all faction 1, client2 END TURN + the host's
NextTurnState while no debriefing; ufo_landed: client2 ABORT, its AbortMissionState OK, the host's YES); both
debriefings; client2's OK first, then the host's; the target's fate. A bring-up, staging, landing, turn, save, relaunch
or abort-step miss prints ONE "CAPTURE a:" / "CAPTURE u:" line and every remaining cell of that boot FAILs "boot". A
resume that never reaches both inBattle FAILs <row>-resume and blocks <row>-borrow .. <row>-target. The real target is
keyed by its vanilla Target id (ABID / UFOID): a co-op-id key would pass vacuously without the fix (a reloaded base
rolls a new co-op id).
Cells (one PASS / FAIL line each; one EVIDENCE line and one ROW line per row):
  alien_base-id       right after the menu load: one host alien_base_state entry coop false with id ABID, its coopId
                      == ACOOP.
  alien_base-file     the save body: one alienBases entry with id ABID, its coopAlienBaseId == ACOOP.
  alien_base-resume   both inBattle <= RESUME_S, phase Active, battleId equal and non-zero; both tops BattlescapeState
                      <= TOPS_S after RESUME; turn / side and mapFingerprint == SAVED's; census equal on both and ==
                      SAVED's (faction 0 seat 1 == SQ, faction 1 seat 0 without AI).
  alien_base-borrow   host pvpBorrow {active true, resumeBorrowed 1, kind landing, targetKind alienBase, targetCoopId
                      ACOOP, craftId SKY}; the host's live (borrowed) world has one alien base coop true with coopId
                      ACOOP, inBattlescape true (the rebuilt mirror).
  alien_base-host     host DebriefingState <= DEBRIEF_S, title TITLE["alien_base"], displayOnly false.
  alien_base-client   client2's display-only DebriefingState <= CLIENT_DEBRIEF_S, equal to the host's on
                      BES.DEBRIEF_FIELDS.
  alien_base-return   client2 OK first: geo_clean <= OK_S; debriefOkBranch campaign-client-borrowed; every SQ soldier
                      where base with missions == missions0 + 1; the Skyranger returning or at base.
  alien_base-alien    host OK: geo_clean <= HOST_OK_S; noBases true, funds STUB_FUNDS, real bases == HOST0's;
                      pvpBorrow.active false.
  alien_base-target   host pvpBorrow.fate {alienBase, ACOOP, deleted}; within TARGET_S no host base coop false with
                      id ABID and no client2 mirror with coopId ACOOP_L.
  alien_base-common   desyncSeen false on host, client and client2 at each read; 0 new crash files since the boot's
                      start; assert_hash_clean (full=True) EQUAL after the first spine and after RESUME; client2
                      zero-disk.
  ufo_landed-id / -resume / -borrow / -host / -client / -return / -alien / -common as alien_base's with the UFO
  (geo_state.ufos, targetKind ufo, UCOOP; title TITLE["ufo_landed"]; -return without the missions check).
  ufo_landed-target: fate {ufo, UCOOP, takeoff}; host geo_set_speed idx 0; within LIFT_S the host's real UFO (coop
  false, id UFOID) status 0 or absent.
Without the fix (2 of 2 measured runs): exit 2, 14/19 - FAIL alien_base-id, alien_base-file, alien_base-borrow,
alien_base-host ("Aliens defeated"), alien_base-target (the real base stays). With the fix: 19/19.

ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_resume_borrowed_targets.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import geo  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import repro_atom_side_begin as RSB  # noqa: E402
import test_battle_end_separate as BES  # noqa: E402
import test_campaign_battle_gm2 as G2F  # noqa: E402
import test_campaign_battle_gm3 as G3B  # noqa: E402
import test_campaign_battle_gm3_end as G3E  # noqa: E402
import test_campaign_battle_resume as BR  # noqa: E402  (pure helpers only)
import test_campaign_gm3_targets as G3T  # noqa: E402  (constants only)
import test_campaign_resume_roles as RR  # noqa: E402  (pure helpers only)
import test_shared_page3 as P3  # noqa: E402

# ----- fixture values -----
KEY = "49059"
TAGS = {"alien_base": "resume_borrowed_base", "ufo_landed": "resume_borrowed_ufo"}
SEED = 1                                     # on the X-COM client right before its confirm_landing
POINT = {"alien_base": (0.10, 0.35), "ufo_landed": (-0.35, 0.10)}      # the target at X + point
CRAFT_AT = {"alien_base": (0.09, 0.35), "ufo_landed": (-0.34, 0.10)}   # 0.01 rad short, toward X
KIND = {"alien_base": "alienBase", "ufo_landed": "ufo"}
ACTION = {"alien_base": "deleted", "ufo_landed": "takeoff"}
TITLE = {"alien_base": "Alien Base destroyed", "ufo_landed": "UFO is not recovered"}   # as G3T.TITLE
SQUAD = 2
SAVED_AT = (2, 0)                            # (turn, side)
STUB_FUNDS = 1000                            # the alien role's funds
# the cells that fail without the fix (2 of 2 measured runs)
FIX = {"alien_base-id", "alien_base-file", "alien_base-borrow", "alien_base-host", "alien_base-target"}
# ----- bounds -----
MIRROR_S, LANDING_S, BOTH_IN_S, STEP_S, SAVE_S, GUARD_S = 30, 180, 60, 60, 30, 1.0
RESUME_S, RESUME_PRESS_S, TOPS_S, ABORT_S = 180, 60, 60, 30
DEBRIEF_S, CLIENT_DEBRIEF_S, ADOPT_S, OK_S, HOST_OK_S, TARGET_S, LIFT_S = 60, 20, 30, 10, 60, 10, 30
CELLS = {"alien_base": ["alien_base-" + c for c in ("id", "file", "resume", "borrow", "host", "client", "return",
                                                  "alien", "target", "common")],
         "ufo_landed": ["ufo_landed-" + c for c in ("id", "resume", "borrow", "host", "client", "return", "alien",
                                                  "target", "common")]}
ALL_CELLS = CELLS["alien_base"] + CELLS["ufo_landed"]
stack, top, crash_set, wait, view, census = RR.stack, RR.top, RR.crash_set, RR.wait, RR.view, RR.census
pvp, pvp_lines, snap, hash_res, ckey, desync = BR.pvp, BR.pvp_lines, BR.snap, BR.hash_res, BR.ckey, BR.desync
BOOT = {"tag": "a"}


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


def row_verdict(row):
    bad = [n for n, ok, _ in RESULTS if n in CELLS[row] and not ok]
    print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)


def capture_boot(err, *machines):
    print(f"CAPTURE {BOOT['tag']}: {json.dumps(RR.capture(err, *machines), sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def abases(gc):
    return [{k: a.get(k) for k in ("id", "coopId", "coop", "discovered", "race", "inBattlescape")}
            for a in gc.cmd({"cmd": "alien_base_state"}).get("alienBases") or []]


def ufos(gc):
    return [{k: u.get(k) for k in ("id", "coopId", "coop", "status")} for u in gc.cmd({"cmd": "geo_state"}).get("ufos") or []]


def targets(row, gc):
    return abases(gc) if row == "alien_base" else ufos(gc)


def real_of(row, gc, tid):
    return [t for t in targets(row, gc) if not t.get("coop") and t.get("id") == tid]


def mirrors_of(row, gc, tc):
    return [t for t in targets(row, gc) if t.get("coop") and t.get("coopId") == tc]


def bring_up(host, client, ev):
    """BR's bring_up (copied, KEY): gm3, the HOST on the Alien team. Returns (HOST0, CLIENT0, xb)."""
    host.spawn(); host.connect(); client.spawn(); client.connect()
    try:
        gm = PF.start_pvp_campaign(host, client, KEY, alien_player="host")
    except Exception as e:  # noqa: BLE001
        capture_boot(f"PF.start_pvp_campaign: {e}", host, client)
    ch, cc = G3E.coop(host), G3E.coop(client)
    hg, cg = host.ok({"cmd": "geo_state"}), client.ok({"cmd": "geo_state"})
    host0 = {"noBases": ch.get("noBases"), "funds": hg.get("funds"), "realBases": G3E.real_bases(hg)}
    xb = next((b for b in cg.get("bases", []) if not b.get("coopBase") and not b.get("coopIcon")), None)
    sky = next((c for c in (xb or {}).get("crafts", []) if "SKYRANGER" in c.get("type", "") and not c.get("coop")), None)
    client0 = {"noBases": cc.get("noBases"), "funds": cg.get("funds"), "realBases": G3E.real_bases(cg),
               "sky": sky and {"type": sky.get("type"), "id": sky.get("id")}}
    ev.update(lobbyGamemode=gm, HOST0=host0, CLIENT0=client0, gamemode=[ch.get("gamemode"), cc.get("gamemode")])
    if not (ch.get("gamemode") == 3 and cc.get("gamemode") == 3 and ch.get("noBases") is True and cc.get("noBases") is False):
        capture_boot(f"bring-up preconditions: gamemode host {ch.get('gamemode')} client {cc.get('gamemode')} "
                     f"(want 3), noBases host {ch.get('noBases')!r} client {cc.get('noBases')!r} (want true / false)",
                     host, client)
    if not xb or not sky:
        capture_boot(f"the client has no real base / Skyranger (base {xb and xb.get('name')}, sky {sky})", host, client)
    geo.slow_clock(host, client)
    return host0, client0, xb


def spawn_target(row, host, client, xb, ev):
    """The HOST's own alien base or landed UFO at X + POINT and its client mirror. Returns (Target id, co-op id)."""
    point = [xb["lon"] + POINT[row][0], xb["lat"] + POINT[row][1]]
    if row == "alien_base":
        sp = host.cmd({"cmd": "spawn_alien_base", "lon": point[0], "lat": point[1], "race": "STR_SECTOID"})
        fd = host.cmd({"cmd": "host_alien_base_found", "alien_base_id": sp.get("alien_base_id")}) if sp.get("ok") else {}
        tid = sp.get("alien_base_id")
        real = next(iter(real_of(row, host, tid)), None) if fd.get("ok") else None
        ok = bool(real) and real.get("discovered") is True
    else:
        sp = host.cmd(dict(G3T.UFO, cmd="spawn_ufo", state="landed", lon=point[0], lat=point[1]))
        tid = sp.get("ufo_id")
        real = next(iter(real_of(row, host, tid)), None) if sp.get("ok") else None
        ok = bool(real)
    ev.update(point=point, spawn=sp, hostReal=real)
    if not ok:
        capture_boot(f"{row}: the host's target (spawn {sp}, entry {real}) not found discovered in its own world", host, client)
    tc = real["coopId"]
    mok, ms = wait(lambda: any(row == "ufo_landed" or m.get("discovered") for m in mirrors_of(row, client, tc)),
                   MIRROR_S, 0.1)
    ev.update(mirrorS=ms, clientMirror=mirrors_of(row, client, tc))
    if not mok:
        capture_boot(f"{row}: no client mirror of the host's target (co-op id {tc}) within {MIRROR_S} s", host, client)
    return tid, tc


def stage_to_prompt(row, host, client, xb, client0, ev):
    """SQ, missions0, the target, craft_force to the mirror by co-op id, the landing prompt. Returns
    (sq, m0, tid, tc)."""
    geo.slow_clock(host, client)
    sky = client0["sky"]
    sb = next((b for b in client.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    recs = {sid: G3E.srec(client, sid) for sid in sids}
    sq = [sid for sid in sids if recs[sid].get("where") == "base" and recs[sid].get("recovery") == 0][:SQUAD]
    if len(sq) < SQUAD:
        capture_boot(f"fewer than {SQUAD} client soldiers in base with recovery 0: {sids}", host, client)
    asg = [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": False}) for sid in sids]
    asg += [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": True}) for sid in sq]
    if not all(r.get("ok") for r in asg):
        capture_boot(f"client craft_assign (SQ {sq}): {[r for r in asg if not r.get('ok')][:2]}", host, client)
    m0 = {sid: G3E.srec(client, sid).get("missions") for sid in sq}
    ev.update(SQ=sq, missions0=m0)
    tid, tc = spawn_target(row, host, client, xb, ev)
    dest = ("alienBaseCoop:" if row == "alien_base" else "ufoCoop:") + str(tc)
    cf = client.cmd({"cmd": "craft_force", "craft_id": sky["id"], "status": "STR_OUT", "lon": xb["lon"] + CRAFT_AT[row][0],
                     "lat": xb["lat"] + CRAFT_AT[row][1], "dest": dest, "fuel": 999999, "lowFuel": False})
    ev["craftForce"] = {k: cf.get(k) for k in ("ok", "error", "displayStatus", "destKind")}
    if not cf.get("ok"):
        capture_boot(f"client craft_force {cf}", host, client)

    def prompt():
        if session.has_state(client, "ConfirmLandingState"):
            return True
        for gc in (host, client):
            geo.drain_popups(gc, interest=geo.popup("ConfirmLandingState"))
            gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None
    ok, ps = wait(prompt, LANDING_S)
    ev["promptS"] = ps
    if not ok:
        capture_boot(f"no client ConfirmLandingState within {LANDING_S} s", host, client)
    return sq, m0, tid, tc


def land_to_saved(row, host, client, tc, client0, ev):
    """The entry, the spine, the borrow's target, turn 2 side 0. Returns SAVED."""
    sd, cl = client.cmd({"cmd": "set_seed", "seed": SEED}), client.cmd({"cmd": "confirm_landing"})
    if not sd.get("ok") or not cl.get("ok"):
        capture_boot(f"client set_seed {sd} / confirm_landing {cl}", host, client)
    both, bs = wait(lambda: G3B.in_battle(host) and G3B.in_battle(client), BOTH_IN_S)
    ev["bothInS"] = bs
    if not both:
        capture_boot(f"not both inBattle within {BOTH_IN_S} s of the client's confirm_landing", host, client)
    try:
        session.briefings_to_battlescape(host, client)
    except Exception as e:  # noqa: BLE001
        capture_boot(f"session.briefings_to_battlescape: {str(e)[:300]}", host, client)
    pe = pvp(host)
    ev.update(pvpAtEntry={"host": pe, "client": pvp(client)}, hashAfterSpine=hash_res(host, client), entry=snap(host))
    desync(ev, host, client)
    if (pe.get("targetKind"), pe.get("targetCoopId")) != (KIND[row], tc):
        capture_boot(f"host pvpBorrow target {pe.get('targetKind')!r} / {pe.get('targetCoopId')!r} (want {KIND[row]!r} / {tc})",
                     host, client)
    try:
        ev["endTurnClient"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        RSB.drive_side_change(host, client, 1, timeout=STEP_S)
        ev["endTurnHost"] = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        RSB.drive_side_change(host, client, 0, want_turn_min=2, timeout=STEP_S)
    except Exception as e:  # noqa: BLE001
        capture_boot(f"to turn 2: {str(e)[:300]}", host, client)
    hs, pv = snap(host), pvp(host)
    saved = {"turn": hs["turn"], "side": hs["side"], "missionType": hs["missionType"], "census": census(host),
             "mapFingerprint": hs["mapFingerprint"], "battleId": hs["battleId"],
             "pvpBorrow": {k: pv.get(k) for k in ("targetKind", "targetCoopId", "craftId", "savedBorrowed")}, "clientSnap": snap(client)}
    ev["SAVED"] = saved
    if (saved["turn"], saved["side"]) != SAVED_AT:
        capture_boot(f"SAVED turn / side {(saved['turn'], saved['side'])} (want {SAVED_AT})", host, client)
    return saved


def save_and_read(row, host, client, tid, tc, ev):
    """The quick save (a miss = setup failure) and the file read; alien_base-file. Returns the save's file name."""
    before, n0 = set(session.save_files(host.user_dir)), len(BR.logl(host))
    ev["saveReply"] = host.cmd({"cmd": "save_game_ui", "type": "quick_battle"})
    ok, ss = wait(lambda: set(session.save_files(host.user_dir)) - before, SAVE_S, 0.2)
    new = sorted(set(session.save_files(host.user_dir)) - before)
    if not ok or len(new) != 1 or not new[0].endswith(".asav"):
        capture_boot(f"the quick_battle save: new files {new} within {SAVE_S} s (want one .asav)", host, client)
    time.sleep(GUARD_S)
    ev.update(saveFile=new[0], saveS=ss, pvpAfterSave=pvp(host), savedLines=pvp_lines(host, n0))
    sec = "alienBases" if row == "alien_base" else "ufos"
    key = "coopAlienBaseId" if row == "alien_base" else "coopUfoId"
    try:
        header, body, blobs = BR.read_save(os.path.join(host.user_dir, new[0]))
        ents = [e for e in body.get(sec) or [] if e.get("id") == tid]
        ev.update(header={k: header.get(k) for k in ("coopPvpBorrowed", "turn", "mission", "coopBattleProtocol")}, fileEntries=ents,
                  bodyIds=[e.get("id") for e in body.get(sec) or []],
                  blobTargets=[{"key": b["key"], sec: b["body"].get(sec)} for b in blobs])
        bad = [] if len(ents) == 1 else [f"body {sec} with id {tid}: {len(ents)} (ids {ev['bodyIds']}; want 1)"]
        bad += [f"{sec} entry id {tid}: {key} {ents[0].get(key, 'absent')!r} (want {tc})"] if len(ents) == 1 and ents[0].get(key) != tc \
            else []
    except Exception as e:  # noqa: BLE001
        bad = [f"the save could not be read: {type(e).__name__}: {str(e)[:200]}"]
    ev["fileCheck"] = bad
    if row == "alien_base":
        cell("alien_base-file", not bad,
             "; ".join(bad) or f"the body's alienBases entry id {tid} has coopAlienBaseId {tc}")
    return os.path.basename(new[0])


def relaunch(x, ev):
    """BR's relaunch (copied): both shut down; the host respawned on ITS dir; client2 on an EMPTY dir; spawn, connect."""
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


def resume_campaign_battle(host, client, save_file, port, hook, host_name="HostPlayer", client_name="ClientPlayer", timeout=120):
    """BR's resume_campaign_battle (copied: the host's START HOST through the real host window) with ONE hook: right
    after HostMenu appears, before host_menu_host."""
    host.ok({"cmd": "load_save_menu", "file": save_file})
    host.wait_for("host window (battle resume)", lambda: session.has_state(host, "HostMenu"))
    hook()
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
        time.sleep(2.0)
    raise TimeoutError(f"battle resume: both machines did not enter the battle within {timeout}s: host {session.states(host)[-3:]} / "
                       f"client {session.states(client)[-3:]}")


def resume_cells(row, host, c2, file, saved, sq, tid, tc, client0, ev):
    """<row>-id (the hook), <row>-resume, <row>-borrow. Returns True when the battle is up on both."""
    t0, res, rbad, ml = time.time(), None, [], {}

    def hook():
        ml["t"] = round(time.time() - t0, 2)
        try:
            ml["stack"], ml["targets"] = stack(host), targets(row, host)
        except Exception as e:  # noqa: BLE001
            ml["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    try:
        resume_campaign_battle(host, c2, file, KEY, hook, timeout=RESUME_S)
        t1 = time.time()
        ev["press"] = session.press_back_when_shown(host, "host RESUME", codes=(60, 62), timeout=RESUME_PRESS_S)
        tok, ts = wait(lambda: top(host) == "BattlescapeState" and top(c2) == "BattlescapeState", TOPS_S)
        ev.update(resumeS=round(t1 - t0, 2), topsS=ts)
        rbad += [] if tok else [f"tops host/client2 {[top(host), top(c2)]} (want BattlescapeState on both within {TOPS_S} s of RESUME)"]
        res = [snap(host), snap(c2)]
    except Exception as e:  # noqa: BLE001
        ev.update(resumeError=f"{type(e).__name__}: {str(e)[:300]}", resumeCapture=RR.capture("resume", host, c2))
    ev["menuLoad"] = ml
    real = [t for t in ml.get("targets") or [] if not t.get("coop") and t.get("id") == tid]
    ev["coopIdAfterLoad"] = real[0].get("coopId") if len(real) == 1 else None
    nm = "alien_base_state" if row == "alien_base" else "geo_state.ufos"
    ibad = [f"no read of the host's {nm} while HostMenu was up ({ml.get('error') or 'the hook never ran'})"] if "targets" not in ml \
        else ([f"host {nm} coop-false entries with id {tid}: {real} of {ml['targets']} (want exactly one)"] if len(real) != 1 else
              ([f"host {nm} id {tid}: coopId {real[0].get('coopId')} after the menu load (want {tc}: the saved id)"]
               if real[0].get("coopId") != tc else []))
    cell(f"{row}-id", not ibad, "; ".join(ibad) or f"right after the menu load (HostMenu up) the host's real target id {tid} has "
         f"coopId {tc}")
    if res is None or not (res[0]["inBattle"] and res[1]["inBattle"]):
        ev["resumedLines"] = pvp_lines(host, 0)
        cell(f"{row}-resume", False, f"the battle resume never reached both inBattle ({ev.get('resumeError')}; {res})")
        return False
    ev.update(resumedLines=pvp_lines(host, 0), afterResume={"host": view(host), "client2": view(c2), "battle": res,
                                                            "pvpBorrow": {"host": pvp(host), "client2": pvp(c2)}})
    desync(ev, host, c2)
    for nm2, s in (("host", res[0]), ("client2", res[1])):
        rbad += [f"{nm2} phase {s['phase']!r} (want Active)"] if s["phase"] != "Active" else []
        rbad += [f"{nm2} turn / side {(s['turn'], s['side'])} (want SAVED's {(saved['turn'], saved['side'])})"] \
            if (s["turn"], s["side"]) != (saved["turn"], saved["side"]) else []
        rbad += [f"{nm2} mapFingerprint {s['mapFingerprint']!r} (want SAVED's {saved['mapFingerprint']!r})"] \
            if s["mapFingerprint"] != saved["mapFingerprint"] else []
    rbad += [f"battleId host/client2 {[res[0]['battleId'], res[1]['battleId']]} (want equal, non-zero)"] \
        if not res[0]["battleId"] or res[0]["battleId"] != res[1]["battleId"] else []
    cen = [census(host), census(c2)]
    ev["census"] = cen
    rbad += RR.seats_bad(cen[0], cen[1], 1, 0, sq)
    rbad += [f"census {ckey(cen[0])} != SAVED's {ckey(saved['census'])}"] if ckey(cen[0]) != ckey(saved["census"]) else []
    cell(f"{row}-resume", not rbad, "; ".join(rbad) or f"both inBattle, phase Active, battleId equal; turn / side {SAVED_AT} and "
         "mapFingerprint == SAVED's; census == SAVED's (faction 0 seat 1 == SQ, faction 1 seat 0 without AI); tops BattlescapeState")
    ev["hashAfterResume"] = hash_res(host, c2)
    pv, live = pvp(host), targets(row, host)
    ev["liveTargetsAfterResume"] = live
    want = {"active": True, "resumeBorrowed": 1, "kind": "landing", "targetKind": KIND[row], "targetCoopId": tc,
            "craftId": client0["sky"]["id"]}
    bbad = [f"host pvpBorrow.{k} {pv.get(k, 'absent')!r} (want {w!r})" for k, w in want.items() if pv.get(k) != w]
    mir = [t for t in live if t.get("coop") and t.get("coopId") == tc]
    bbad += [f"the host's live world: coop entries with coopId {tc}: {mir} of {live} (want exactly one"
             + (", inBattlescape true)" if row == "alien_base" else ")")] \
        if len(mir) != 1 or (row == "alien_base" and mir[0].get("inBattlescape") is not True) else []
    cell(f"{row}-borrow", not bbad, "; ".join(bbad) or f"host pvpBorrow active, resumeBorrowed 1, landing / {KIND[row]} {tc}, craft "
         f"{client0['sky']['id']}; the rebuilt mirror in the borrowed world")
    return True


def act(row, host, c2, ev):
    """alien_base: the win, ufo_landed: the abort, as G3T.act does them (a step miss = setup failure)."""
    a = ev["action"] = {}
    t0 = time.time()
    if row == "alien_base":
        G2F.kill_all(host, c2, 1, a, "kills")
        a["killS"] = round(time.time() - t0, 2)
        if "DebriefingState" not in stack(host):
            a["endTurn"] = c2.cmd({"cmd": "battle_action", "action": "end_turn_button"})
            a["closeNext"] = BES.close_host_nextturn(host)
        return
    a["abort"] = c2.cmd({"cmd": "battle_action", "action": "abort"})
    ok, a["abortStateS"] = wait(lambda: top(c2) == "AbortMissionState", ABORT_S)
    if not ok:
        capture_boot(f"ufo_landed: no client2 AbortMissionState within {ABORT_S} s (stack {stack(c2)})", host, c2)
    d = c2.cmd({"cmd": "dismiss_popup"})
    a["dismiss"] = d.get("handled")
    if d.get("handled") != "AbortMissionState":
        capture_boot(f"ufo_landed: client2 dismiss_popup {d} (want handled AbortMissionState)", host, c2)
    try:
        a["vote"] = session.abort_vote_yes(host, host)
    except Exception as e:  # noqa: BLE001
        capture_boot(f"ufo_landed: session.abort_vote_yes(host, host): {str(e)[:300]}", host, c2)


def end_cells(row, host, c2, tid, tc, sq, m0, host0, client0, ev):
    """Both debriefings, client2's OK first, then the host's, the target. <row>-host .. <row>-target."""
    names = CELLS[row][CELLS[row].index(f"{row}-host"):-1]
    ok, secs = wait(lambda: "DebriefingState" in stack(host), DEBRIEF_S)
    hdeb = G3E.deb(host)
    ev["hostDebrief"] = {k: v for k, v in hdeb.items() if k != "widgets"}
    if not ok:
        cell(f"{row}-host", False, f"no host DebriefingState within {DEBRIEF_S} s (stack {stack(host)})")
        block(names, f"the host's debriefing never opened ({row}-host)")
        return
    hbad = [f"debrief_state.{k}={hdeb.get(k)!r} (want {w!r})" for k, w in (("title", TITLE[row]), ("displayOnly", False))
            if hdeb.get(k) != w]
    cell(f"{row}-host", not hbad, "; ".join(hbad) or f"host DebriefingState {secs} s, {TITLE[row]!r}, displayOnly false")
    ev["hostPage3"] = dict(G3E.page3(host), flipped=P3.to_page2(host), after=G3E.page3(host))
    cok, csecs = wait(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True and d.get("displayOnly") is True)(
        G3E.deb(c2)), CLIENT_DEBRIEF_S)
    hv, cv = BES.debrief_view(hdeb), BES.debrief_view(G3E.deb(c2))
    ev["client2Debrief"] = cv
    cbad = [] if cok else [f"no client2 display-only DebriefingState within {CLIENT_DEBRIEF_S} s (stack {stack(c2)})"]
    cbad += [f"client2 {k}={cv.get(k)!r} != host {hv.get(k)!r}" for k in BES.DEBRIEF_FIELDS if cok and cv.get(k) != hv.get(k)]
    cell(f"{row}-client", not cbad, "; ".join(cbad) or f"client2 display-only debriefing {csecs} s, equal on DEBRIEF_FIELDS")
    # as G3E's win-page3: adopted, then the OK
    aok, asecs = wait(lambda: (BES.record(c2).get("worldAdopted") or 0) >= 1, ADOPT_S)
    t_ok = time.time()
    pk = BES.press_ok(c2)
    _r, cscreens = BES.drain(c2, timeout=OK_S)
    gok, _gs = wait(lambda: BES.geo_clean(c2), OK_S)
    crec, csky = BES.record(c2), G3E.sky_of(c2, client0["sky"])
    csq = {sid: G3E.srec(c2, sid) for sid in sq}
    ev["client2Ok"] = {"adoptS": asecs, "adopted": aok, "press": pk, "drain": cscreens, "geoS": round(time.time() - t_ok, 2),
                       "stack": stack(c2), "battleEnd": crec, "sky": csky, "pvpBorrow": pvp(c2),
                       "sq": {sid: {k: csq[sid].get(k) for k in ("where", "missions", "dead")} for sid in sq},
                       "time": c2.ok({"cmd": "geo_state"}).get("time")}
    rbad = [] if gok else [f"client2 not on a clean GeoscapeState {OK_S} s after its OK (stack {stack(c2)})"]
    rbad += [f"battleEnd.debriefOkBranch {crec.get('debriefOkBranch')!r} (want 'campaign-client-borrowed')"] \
        if crec.get("debriefOkBranch") != "campaign-client-borrowed" else []
    for sid in sq:
        want_m = m0[sid] + 1 if isinstance(m0[sid], int) else None
        if csq[sid].get("where") != "base" or (row == "alien_base" and csq[sid].get("missions") != want_m):
            rbad.append(f"SQ {sid}: where {csq[sid].get('where')!r} missions {csq[sid].get('missions')!r} (want 'base'"
                        + (f", {want_m})" if row == "alien_base" else ")"))
    rbad += [] if G3E.returning_or_at_base(csky) else [f"client2 Skyranger {csky} (want returning or at base)"]
    cell(f"{row}-return", not rbad, "; ".join(rbad) or f"client2 geo_clean; campaign-client-borrowed; SQ in base"
         + (" with missions + 1" if row == "alien_base" else "") + f"; Skyranger {csky}")
    hk = BES.press_ok(host)
    hreached, hscreens, on994 = G2F.drain_host(host)
    hgok, hgs = wait(lambda: BES.geo_clean(host), HOST_OK_S) if hreached else (False, 0)
    hco, hg = G3E.coop(host), host.ok({"cmd": "geo_state"})
    pv = hco.get("pvpBorrow") or {}
    ev["hostOk"] = {"press": hk, "drain": hscreens, "on994": on994, "geoS": hgs, "stack": stack(host), "noBases": hco.get("noBases"),
                    "funds": hg.get("funds"), "realBases": G3E.real_bases(hg), "time": hg.get("time"), "pvpBorrow": pv}
    abad = [] if hgok else [f"host not on a clean GeoscapeState after its OK (reached {hreached}, 994 {on994}, stack {stack(host)})"]
    abad += [f"host noBases {hco.get('noBases')!r} (want true)"] if hco.get("noBases") is not True else []
    abad += [f"host funds {hg.get('funds')!r} (want {STUB_FUNDS})"] if hg.get("funds") != STUB_FUNDS else []
    abad += [f"host real bases {G3E.real_bases(hg)} (want HOST0's {host0['realBases']})"] \
        if G3E.real_bases(hg) != host0["realBases"] else []
    abad += [f"host pvpBorrow.active {pv.get('active')!r} (want false)"] if pv.get("active") is not False else []
    cell(f"{row}-alien", not abad, "; ".join(abad) or f"host geo_clean ({hgs} s), noBases true, funds {STUB_FUNDS}, real bases == "
         "HOST0; pvpBorrow.active false")
    target_cell(row, host, c2, tid, tc, pv, ev)


def target_cell(row, host, c2, tid, tc, pv, ev):
    """<row>-target: the fate, then the host's real target by its Target id (ufo_landed after geo_set_speed idx 0)."""
    fate, want = pv.get("fate") or {}, {"kind": KIND[row], "coopId": tc, "action": ACTION[row]}
    bad = [f"host pvpBorrow.fate {pv.get('fate')!r} (want {want})"] if {k: fate.get(k) for k in want} != want else []
    if row == "ufo_landed":
        ev["liftSpeed"] = host.cmd({"cmd": "geo_set_speed", "idx": 0}).get("ok")
        ok, secs = wait(lambda: all(u.get("status") == 0 for u in real_of(row, host, tid)), LIFT_S, 0.1)
        ev.update(liftS=secs if ok else None, targetAfter={"host": real_of(row, host, tid), "client2": mirrors_of(row, c2, tc)})
        bad += [] if ok else [f"after {LIFT_S} s at speed idx 0 the host's real UFO id {tid}: {ev['targetAfter']['host']} (want status 0 "
                              "or absent)"]
        detail = f"fate {fate}; the host's real UFO id {tid} lifted or gone ({secs} s)"
    else:
        tcl = ev.get("coopIdAfterLoad") or tc
        ok, secs = wait(lambda: not real_of(row, host, tid) and not mirrors_of(row, c2, tcl), TARGET_S, 0.1)
        ev.update(goneS=secs if ok else None, targetAfter={"host": real_of(row, host, tid), "client2": mirrors_of(row, c2, tcl),
                                                           "client2All": targets(row, c2)})
        bad += [] if ok else [f"after {TARGET_S} s the host's real base id {tid} {ev['targetAfter']['host']} and client2's mirror "
                              f"coopId {tcl} {ev['targetAfter']['client2']} (want both gone)"]
        detail = f"fate {fate}; the host's real base id {tid} and client2's mirror gone ({secs} s)"
    cell(f"{row}-target", not bad, "; ".join(bad) or detail)


def common_cell(row, host, c2, crash0, ev):
    desync(ev, host, c2)
    reads = ev.get("desyncReads", [])
    new = sorted(crash_set() - crash0)
    bad = [f"desyncSeen {nm} {v!r} at a read" for nm, v in reads if v is not False]
    bad += [f"{len(new)} new crash file(s) since the boot's start (first {os.path.basename(new[0])})"] if new else []
    bad += [f"hash after the first spine: {ev.get('hashAfterSpine')}"] if ev.get("hashAfterSpine") != "EQUAL" else []
    bad += [f"hash after RESUME: {ev.get('hashAfterResume', 'not reached')}"] if ev.get("hashAfterResume") != "EQUAL" else []
    bad += [f"client2 zero-disk: {session.save_files(c2.user_dir)}"] if session.save_files(c2.user_dir) else []
    cell(f"{row}-common", not bad, "; ".join(bad) or f"desyncSeen false at {len(reads)} reads (host, client, client2), 0 new crash "
         "files, hash_now full EQUAL after the first spine and after RESUME, client2 zero-disk")


def boot(row, x, ev):
    host, client = x["host"], x["client"]
    crash0, w = crash_set(), ev.setdefault("walls", {})
    t = time.time()
    host0, client0, xb = bring_up(host, client, ev)
    w["bringUp"] = round(time.time() - t, 1); t = time.time()
    sq, m0, tid, tc = stage_to_prompt(row, host, client, xb, client0, ev)
    ev.update(TID=tid, TCOOP=tc)
    saved = land_to_saved(row, host, client, tc, client0, ev)
    w["toSaved"] = round(time.time() - t, 1); t = time.time()
    file = save_and_read(row, host, client, tid, tc, ev)
    desync(ev, host, client)
    host, c2 = relaunch(x, ev)
    w["saveRelaunch"] = round(time.time() - t, 1); t = time.time()
    up = resume_cells(row, host, c2, file, saved, sq, tid, tc, client0, ev)
    w["resume"] = round(time.time() - t, 1); t = time.time()
    if up:
        act(row, host, c2, ev)
        w["action"] = round(time.time() - t, 1); t = time.time()
        end_cells(row, host, c2, tid, tc, sq, m0, host0, client0, ev)
        w["end"] = round(time.time() - t, 1)
    else:
        block(CELLS[row][CELLS[row].index(f"{row}-borrow"):-1], f"the resumed battle never started ({row}-resume)")
    common_cell(row, host, c2, crash0, ev)


def run_boot(row, tag=None):
    """One boot (row alien_base or ufo_landed): its cells, EVIDENCE, ROW, then every machine shut down. Returns the
    boot's EVIDENCE dict."""
    BOOT["tag"] = row[0]
    tag = tag or TAGS[row]
    x = {"tag": tag, "host": GameClient("host", None, make_user_dir(tag + "_host")),
         "client": GameClient("client", None, make_user_dir(tag + "_client")), "client2": None}
    ev, t0 = {}, time.time()
    try:
        boot(row, x, ev)
    except FixtureMiss as e:
        block(CELLS[row], f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        ev["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"[ERROR] boot {BOOT['tag']}: {ev['error']}", flush=True)
        block(CELLS[row], f"error {ev['error']}")
    finally:
        ev["wall"] = round(time.time() - t0, 1)
        evidence(row, ev)
        row_verdict(row)
        for gc in (x["client2"], x["client"], x["host"]):
            try:
                if gc is not None and gc.proc is not None and gc.proc is not getattr(gc, "_shutdown_proc", None):
                    gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)
    return ev


def main():
    t0 = time.time()
    for row in ("alien_base", "ufo_landed"):
        run_boot(row)
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== test_resume_borrowed_targets: resumed borrowed battles at an alien base and a landed UFO: "
          f"{len(RESULTS) - len(fails)}/{len(ALL_CELLS)} cells PASS, wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (FIX cell)' if n in FIX else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(ALL_CELLS) else 2)


if __name__ == "__main__":
    main()
