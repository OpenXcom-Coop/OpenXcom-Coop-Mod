"""test_campaign_battle_resume.py: a gm3 PvP campaign battle (host = the aliens, client = X-COM) that the alien host
saves while it borrows the X-COM player's world. The save is the alien host's own campaign with the X-COM world and its battle embedded
(a header record of the borrow), and its resume borrows the X-COM world again: both players are back in the battle, the X-COM win
returns the results to the X-COM player's world and takes the alien host home to its own world, as after an unsaved battle.

Spec: docs rewrite/prompts/d250u_pvp_campaigns_sc.md, AMENDMENT SC-5 (SC5-7 "Stage S-C4b", SC5-9 the test and FX4B-1 .. FX4B-10, with
SC5-5 / SC5-6's shape and FX4A-2 / FX4A-4 / FX4A-5 / FX4A-8) and its ORCHESTRATOR RULINGS (QC4B-1 .. QC4B-6 (a)); docs
rewrite/w2-resume-efd75a6c/ruling-d250uci.md (R-D250-SC4A-1 (a): the resume's host step is the real host window) and ruling-d250ucj.md
(R-D250-SC4B-1 (a): P4-save's savedBorrowed is 2 = the turn-1 battle-start autosave + the quick save); AMENDMENT SC-2's
FX2-8 / FX2-11 / FX2-12; owner D250, O1 (a); QC-14 (a), D246 (b), D226 (a); VL-C4B-1, VL-C4B-2; F15865, F15866, F15868, F15869.
TASK 0 pins: docs rewrite/d250u-task0/sc4b/CONSTANTS.md (boot Ka on the unchanged build = S-C4a's green; boots Kb / Kb2 with C4BG
applied, then restored).

Boot P (gm3): lobby key 48019, dirs d250uc4b_p_host / _client / _client2. Bring-up (FX4A-2 = G3D's bring_up, copied): gamemode 3 / 3,
host noBases true, client false are preconditions; HOST0 / CLIENT0. The landing (FX4B-3, on the client): G3D's stage_to_prompt (copied;
X + (0.35, 0.10), the Skyranger at X + (0.34, 0.10); missions0 read right after craft_assign), client set_seed 1 + confirm_landing,
both inBattle <= 60 s, the spine. To turn 2 (FX4B-4): client END TURN to side 1, host END TURN to (turn 2, side 0). The save (FX4B-5):
SAVED from the host, host save_game_ui {type: "quick_battle"}, the new _quick_.asav <= 30 s. P5 reads it (FX4B-6, PyYAML) before the
shutdown. The relaunch and resume (FX4B-7): both shut down, the host respawned on its dir, client2 on an EMPTY dir; resume_campaign_battle
(session's, copied, its host step through host_menu_host, R-D250-SC4A-1), the host's RESUME, both tops BattlescapeState. The win
(FX4B-8 = FX2-8 with client2; the host's page 3 by FX2-11) and the OKs (FX4B-9 = FX2-12, client2 first). A bring-up, landing, turn,
save or relaunch miss is a setup failure: ONE "CAPTURE P:" line and every remaining cell FAILs "boot". A resume that does not reach
both inBattle FAILs P4-resume with the captured state and blocks P4-borrow .. P4-alien.
Rows and cells (one PASS / FAIL line per cell, one EVIDENCE line and one ROW line per row):
  P5 (the save's shape, read between the save and the shutdown): P5-header, P5-body, P5-blob.
  P4 (save, resume, win): P4-save, P4-resume, P4-borrow, P4-host, P4-client, P4-return, P4-alien, P4-common.
  P4-save: savedBorrowed == 2; the value read before the quick save (1) is printed as "EVIDENCE P4-save".
RED (C4BR, the unchanged build; TASK 0 boot Ka): 3/11 - P4-resume, P4-client, P4-common PASS; FAIL P4-save, P5-header, P5-body,
P5-blob, P4-borrow, P4-host, P4-return, P4-alien. GREEN (C4BG; Kb / Kb2 10/11 each before R-D250-SC4B-1, P4-save read 2): 11/11.

ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_campaign_battle_resume.py
"""

import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import geo  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import test_battle_end_separate as BES  # noqa: E402
import repro_atom_side_begin as RSB  # noqa: E402
import test_campaign_battle_gm2 as G2F  # noqa: E402
import test_campaign_battle_gm3 as G3C1  # noqa: E402
import test_campaign_battle_gm3_end as G3E  # noqa: E402
import test_campaign_resume_roles as RR  # noqa: E402  (pure helpers only)
import test_pvp_borrowed_target as BT37  # noqa: E402
import test_shared_page3 as P3  # noqa: E402

# ----- TASK 0 pins (docs rewrite/d250u-task0/sc4b/CONSTANTS.md) -----
KEY = "48019"
TAG = "d250uc4b_p"
SEED = 1                                     # on the X-COM client right before its confirm_landing
SITE = {"mission": "STR_ALIEN_RESEARCH", "deployment": "STR_MEDIUM_SCOUT", "race": "STR_SECTOID", "hours": 240}   # FX2-4
POINT, CRAFT_AT = (0.35, 0.10), (0.34, 0.10)                                    # FX4A-5 / FX3-3: X + point, 0.01 short
SQUAD = 2
SAVED_AT = (2, 0)                            # FX4B-4 / FX4B-5: (turn, side)
STUB_FUNDS = 1000                            # the alien role's funds (get_coop.noBases's effect on geo_state.funds)
TITLE_WIN = "Aliens defeated"                # FX4B-10
CLIENT = "ClientPlayer"
SAVED_BORROWED = 2                           # P4-save: the turn-1 autosave + the quick save (R-D250-SC4B-1 (a); Kb / Kb2 2/2)
FIX = {"P4-save", "P5-header", "P5-body", "P5-blob", "P4-borrow", "P4-host", "P4-return", "P4-alien"}   # TASK 0 Ka (3/11)
# ----- bounds -----
MIRROR_S, LANDING_S, BOTH_IN_S, STEP_S = 30, 180, 60, 60
SAVE_S, GUARD_S = 30, 1.0
RESUME_S, RESUME_PRESS_S, TOPS_S = 180, 60, 60
DEBRIEF_S, CLIENT_DEBRIEF_S, ADOPT_S, OK_S, HOST_OK_S, SITE_S = 60, 20, 30, 10, 60, 10
ROWS = {"P5": ["P5-header", "P5-body", "P5-blob"],
        "P4": ["P4-save", "P4-resume", "P4-borrow", "P4-host", "P4-client", "P4-return", "P4-alien", "P4-common"]}
ALL_CELLS = ["P4-save"] + ROWS["P5"] + ROWS["P4"][1:]
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


def evidence(row, obj):
    print(f"EVIDENCE {row}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)


def row_verdict(row):
    bad = [n for n, ok, _ in RESULTS if n in ROWS[row] and not ok]
    print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)


def capture_boot(err, *machines):
    print(f"CAPTURE P: {json.dumps(RR.capture(err, *machines), sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def pvp(gc):
    return gc.cmd({"cmd": "get_coop"}).get("pvpBorrow") or {}


def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def pvp_lines(gc, n0=0):
    return [ln.split("\t")[-1][:240] for ln in logl(gc)[n0:] if "[coop-pvp]" in ln or "offerResumedBattle" in ln]


def rb(bases):
    return [{"name": b.get("name"), "lon": round(b.get("lon") or 0.0, 9), "lat": round(b.get("lat") or 0.0, 9)} for b in bases or []]


def hash_res(host, other):
    try:
        session.assert_hash_clean(host, other, full=True)
        return "EQUAL"
    except Exception as e:  # noqa: BLE001
        return f"hash_now full: {str(e)[:400]}"


def desync(ev, *machines):
    for gc in machines:
        ev.setdefault("desyncReads", []).append([gc.name, event_state(gc).get("desyncSeen")])


def snap(gc):
    b = battle_state(gc)
    a = b.get("authority") or {}
    return {"inBattle": b.get("inBattle"), "phase": b.get("phase"), "battleId": a.get("battleId"), "turn": b.get("turn"),
            "side": b.get("side"), "mapFingerprint": b.get("mapFingerprint"), "missionType": b.get("missionType"),
            "coopGamemode": b.get("coopGamemode")}


def ckey(cen):
    return sorted((u["id"], u.get("faction"), u.get("coop"), u.get("hasAI")) for u in cen)


def bring_up(host, client, ev):
    """G3D's bring_up (copied, KEY; FX4A-2): gm3, the HOST on the Alien team. Returns (HOST0, CLIENT0, xb)."""
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
        capture_boot(f"bring-up preconditions (FX4A-2): gamemode host {ch.get('gamemode')} client {cc.get('gamemode')} (want 3), "
                     f"noBases host {ch.get('noBases')!r} client {cc.get('noBases')!r} (want true / false)", host, client)
    if not xb or not sky:
        capture_boot(f"the client has no real base / Skyranger (base {xb and xb.get('name')}, sky {sky})", host, client)
    geo.slow_clock(host, client)
    return host0, client0, xb


def stage_to_prompt(host, client, xb, client0, ev):
    """G3D's stage_to_prompt (copied, row P4; FX4B-3) plus missions0 read right after craft_assign (FX4B-2). Returns (site, sq, m0)."""
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
    point = [xb["lon"] + POINT[0], xb["lat"] + POINT[1]]
    site = host.cmd(dict(SITE, cmd="spawn_mission_site", lon=point[0], lat=point[1]))
    if not site.get("ok"):
        capture_boot(f"host spawn_mission_site {site}", host, client)
    ok, ms = wait(lambda: RR.mirror(client, point) is not None, MIRROR_S, 0.1)
    mir = RR.mirror(client, point)
    ev.update(SQ=sq, missions0=m0, point=point, siteHost=site.get("site_id"), mirrorS=ms, siteClient=mir and mir.get("id"))
    if not ok:
        capture_boot(f"no coop mirror of host site {site.get('site_id')} on the client within {MIRROR_S} s", host, client)
    cf = client.cmd({"cmd": "craft_force", "craft_id": sky["id"], "status": "STR_OUT", "lon": xb["lon"] + CRAFT_AT[0],
                     "lat": xb["lat"] + CRAFT_AT[1], "dest": f"site:{mir['id']}", "fuel": 999999, "lowFuel": False})
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
    return site.get("site_id"), sq, m0


def land_to_saved(host, client, xb, client0, ev):
    """FX4B-3 .. FX4B-5 up to SAVED: the landing, the spine, turn 2 side 0. Returns (site, sq, m0, SAVED)."""
    site, sq, m0 = stage_to_prompt(host, client, xb, client0, ev)
    sd, cl = client.cmd({"cmd": "set_seed", "seed": SEED}), client.cmd({"cmd": "confirm_landing"})
    if not sd.get("ok") or not cl.get("ok"):
        capture_boot(f"client set_seed {sd} / confirm_landing {cl}", host, client)
    both, bs = wait(lambda: G3C1.in_battle(host) and G3C1.in_battle(client), BOTH_IN_S)
    ev["bothInS"] = bs
    if not both:
        capture_boot(f"not both inBattle within {BOTH_IN_S} s of the client's confirm_landing", host, client)
    try:
        session.briefings_to_battlescape(host, client)
    except Exception as e:  # noqa: BLE001
        capture_boot(f"session.briefings_to_battlescape: {str(e)[:300]}", host, client)
    ev.update(pvpAtEntry=pvp(host), hashAfterSpine=hash_res(host, client))
    try:
        ev["endTurnClient"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        RSB.drive_side_change(host, client, 1, timeout=STEP_S)
        ev["endTurnHost"] = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        RSB.drive_side_change(host, client, 0, want_turn_min=2, timeout=STEP_S)
    except Exception as e:  # noqa: BLE001
        capture_boot(f"to turn 2 (FX4B-4): {str(e)[:300]}", host, client)
    hs, pv = snap(host), pvp(host)
    saved = {"turn": hs["turn"], "side": hs["side"], "missionType": hs["missionType"], "census": census(host),
             "mapFingerprint": hs["mapFingerprint"], "battleId": hs["battleId"],
             "pvpBorrow": {"targetCoopId": pv.get("targetCoopId"), "craftId": pv.get("craftId"),
                           "savedBorrowed": pv.get("savedBorrowed")}, "clientSnap": snap(client)}
    ev["SAVED"] = saved
    if (saved["turn"], saved["side"]) != SAVED_AT:
        capture_boot(f"SAVED turn / side {(saved['turn'], saved['side'])} (want {SAVED_AT}, FX4B-4)", host, client)
    return site, sq, m0, saved


def save_cell(host, client, saved, ev):
    """FX4B-5: host save_game_ui quick_battle; the new .asav <= SAVE_S (a miss = setup failure); P4-save. Returns the file path."""
    before, n0, sb0 = set(session.save_files(host.user_dir)), len(logl(host)), pvp(host).get("savedBorrowed")
    ev["saveReply"] = host.cmd({"cmd": "save_game_ui", "type": "quick_battle"})
    ok, ss = wait(lambda: set(session.save_files(host.user_dir)) - before, SAVE_S, 0.2)
    new = sorted(set(session.save_files(host.user_dir)) - before)
    if not ok or len(new) != 1 or not new[0].endswith(".asav"):
        capture_boot(f"the quick_battle save: new files {new} within {SAVE_S} s (want one .asav, FX4B-5)", host, client)
    time.sleep(GUARD_S)
    pv, inb, bs = pvp(host), G3C1.in_battle(host), battle_state(host)
    evidence("P4-save", {"savedBorrowedBefore": sb0, "savedBorrowedAfter": pv.get("savedBorrowed")})
    ev.update(saveFile=new[0], saveS=ss, pvpAfterSave=pv, savedLines=pvp_lines(host, n0),
              coopSaveDeferrals=bs.get("coopSaveDeferrals"))
    bad = [] if inb else [f"host inBattle {inb!r} {GUARD_S} s after the save (want true)"]
    bad += [] if pv.get("active") is True else [f"host pvpBorrow.active {pv.get('active')!r} after the save (want true)"]
    bad += [] if pv.get("savedBorrowed") == SAVED_BORROWED else [f"host pvpBorrow.savedBorrowed {pv.get('savedBorrowed', 'absent')!r} "
                                                                f"(want {SAVED_BORROWED})"]
    cell("P4-save", not bad, "; ".join(bad) or f"{new[0]} in {ss} s; host inBattle, pvpBorrow.active true, savedBorrowed {SAVED_BORROWED}")
    return os.path.join(host.user_dir, new[0])


def read_save(path):
    """FX4B-6: PyYAML on the host's file; each coopClientSaves blob base64-decoded, then loaded (test_save_upgrade's reader)."""
    import yaml
    load = lambda t: list(yaml.load_all(t, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader)))  # noqa: E731
    with open(path, encoding="utf-8") as fh:
        docs = load(fh.read())
    header = docs[0] if docs and isinstance(docs[0], dict) else {}
    body = docs[1] if len(docs) > 1 and isinstance(docs[1], dict) else {}
    blobs = []
    for e in body.get("coopClientSaves") or []:
        bd = load(base64.b64decode(e.get("blob") or "").decode("utf-8"))
        blobs.append({"key": e.get("key"), "body": next((d for d in bd if isinstance(d, dict) and "bases" in d), {}), "docs": len(bd)})
    return header, body, blobs


CKEYS = ("saveID", "coop_gamemode", "no_bases", "coop_save_owner_player_id")


def p5_cells(path, saved, host0, client0, ev):
    """P5-header / P5-body / P5-blob from the save file (read between the save and the shutdown)."""
    t0 = time.time()
    try:
        header, body, blobs = read_save(path)
    except Exception as e:  # noqa: BLE001
        block(ROWS["P5"], f"the save could not be read: {type(e).__name__}: {str(e)[:200]}")
        return
    sky, tgt = client0["sky"], saved["pvpBorrow"]["targetCoopId"]
    ev.update(readS=round(time.time() - t0, 2), header={k: v for k, v in header.items() if k != "mods"},
              body=dict({k: body.get(k) for k in CKEYS}, battleGame="battleGame" in body,
                        bases=[b.get("name") for b in body.get("bases") or []]),
              blobs=[{"key": b["key"], "docs": b["docs"], "battleGame": "battleGame" in b["body"],
                      "bases": [x.get("name") for x in b["body"].get("bases") or []],
                      **{k: b["body"].get(k) for k in CKEYS}} for b in blobs])
    want = {"kind": "landing", "craftType": sky["type"], "craftId": sky["id"], "targetKind": "site", "targetCoopId": tgt,
            "targetMirror": True}
    got = header.get("coopPvpBorrowed")
    hbad = [f"header coopPvpBorrowed {got!r} (want {want})"] if got != want else []
    hbad += [f"header {k} {header.get(k)!r} (want {w!r})" for k, w in (("turn", saved["turn"]), ("mission", saved["missionType"]),
                                                                         ("coopBattleProtocol", 1)) if header.get(k) != w]
    cell("P5-header", not hbad, "; ".join(hbad) or f"header coopPvpBorrowed {want}; turn {saved['turn']}, mission "
         f"{saved['missionType']}, coopBattleProtocol 1")
    names0 = [b["name"] for b in host0["realBases"]]
    bbad = ["body holds battleGame (want none)"] if "battleGame" in body else []
    bbad += [f"body {k} {body.get(k)!r} (want {w!r})" for k, w in (("coop_gamemode", 3), ("no_bases", True),
                                                                     ("coop_save_owner_player_id", 0)) if body.get(k) != w]
    bnames = [b.get("name") for b in body.get("bases") or []]
    bbad += [f"body bases {bnames} (want HOST0's real bases {names0})"] if bnames != names0 else []
    cell("P5-body", not bbad, "; ".join(bbad) or f"body: no battleGame, coop_gamemode 3, no_bases true, owner 0, bases {names0}")
    key = f"host_{body.get('saveID')}_{CLIENT}.data"
    xname = client0["realBases"][0]["name"] if client0["realBases"] else None
    lbad = [f"coopClientSaves keys {[b['key'] for b in blobs]} (want exactly [{key!r}])"] \
        if len(blobs) != 1 or blobs[0]["key"] != key else []
    if blobs:
        cb = blobs[0]["body"]
        lbad += ["the embedded world holds no battleGame (want the X-COM world WITH its battle)"] if "battleGame" not in cb else []
        lbad += [f"embedded {k} {cb.get(k)!r} (want {w!r})" for k, w in (("coop_gamemode", 3), ("no_bases", False),
                                                                           ("coop_save_owner_player_id", 1)) if cb.get(k) != w]
        lbad += [f"embedded bases {[x.get('name') for x in cb.get('bases') or []]} (want one named {xname!r})"] \
            if xname not in [x.get("name") for x in cb.get("bases") or []] else []
    cell("P5-blob", not lbad, "; ".join(lbad) or f"one blob {key}: battleGame, coop_gamemode 3, no_bases false, owner 1, base "
         f"{xname!r}")


def relaunch(x, ev):
    """FX4A-4: both shut down; the host respawned on ITS dir; client2 on an EMPTY dir; spawn, connect."""
    t0 = time.time()
    try:
        x["client"].shutdown()
        x["host"].shutdown()
        host = x["host"] = GameClient("host", None, x["host"].user_dir)
        c2 = x["client2"] = GameClient("client2", None, make_user_dir(TAG + "_client2"))
        host.spawn(); host.connect(); c2.spawn(); c2.connect()
    except Exception as e:  # noqa: BLE001
        capture_boot(f"relaunch (FX4A-4): {type(e).__name__}: {str(e)[:300]}", x["host"], x.get("client2"))
    ev["relaunchS"] = round(time.time() - t0, 2)
    return host, c2


def resume_campaign_battle(host, client, save_file, port, host_name="HostPlayer", client_name=CLIENT, timeout=120, interval=2.0):
    """session.resume_campaign_battle copied with ONE change: the host's START HOST goes through the real host
    window (host_menu_host visibility 0 -> HostMenu::hostTCPGame), not the host_tcp lever."""
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


def resume_cells(host, c2, file, saved, sq, host0, client0, xb, ev):
    """FX4B-7: resume, the host's RESUME, both tops; P4-resume and P4-borrow. Returns True when the battle is up on both."""
    t0, n0, res, rbad = time.time(), len(logl(host)), None, []
    try:
        resume_campaign_battle(host, c2, file, port=KEY, timeout=RESUME_S)
        t1 = time.time()
        ev["press"] = session.press_back_when_shown(host, "host RESUME", codes=(60, 62), timeout=RESUME_PRESS_S)
        tok, ts = wait(lambda: top(host) == "BattlescapeState" and top(c2) == "BattlescapeState", TOPS_S)
        ev.update(resumeS=round(t1 - t0, 2), topsS=ts)
        rbad += [] if tok else [f"tops host/client2 {[top(host), top(c2)]} (want BattlescapeState on both within {TOPS_S} s of RESUME)"]
        res = [snap(host), snap(c2)]
    except Exception as e:  # noqa: BLE001
        ev.update(resumeError=f"{type(e).__name__}: {str(e)[:300]}", resumeCapture=RR.capture("resume", host, c2))
    ev.update(resumedLines=pvp_lines(host, 0), afterResume={"host": view(host), "client2": view(c2), "battle": res,
                                                            "pvpBorrow": pvp(host)})
    desync(ev, host, c2)
    if res is None or not (res[0]["inBattle"] and res[1]["inBattle"]):
        cell("P4-resume", False, f"the battle resume never reached both inBattle ({ev.get('resumeError')}; {res})")
        return False
    for nm, s in (("host", res[0]), ("client2", res[1])):
        rbad += [f"{nm} phase {s['phase']!r} (want Active)"] if s["phase"] != "Active" else []
        rbad += [f"{nm} turn / side {(s['turn'], s['side'])} (want SAVED's {(saved['turn'], saved['side'])})"] \
            if (s["turn"], s["side"]) != (saved["turn"], saved["side"]) else []
        rbad += [f"{nm} mapFingerprint {s['mapFingerprint']!r} (want SAVED's {saved['mapFingerprint']!r})"] \
            if s["mapFingerprint"] != saved["mapFingerprint"] else []
    rbad += [f"battleId host/client2 {[res[0]['battleId'], res[1]['battleId']]} (want equal, non-zero)"] \
        if not res[0]["battleId"] or res[0]["battleId"] != res[1]["battleId"] else []
    cen = [census(host), census(c2)]
    ev["census"] = cen
    rbad += RR.seats_bad(cen[0], cen[1], 1, 0, sq)
    rbad += [f"census {ckey(cen[0])} != SAVED's {ckey(saved['census'])}"] if ckey(cen[0]) != ckey(saved["census"]) else []
    cell("P4-resume", not rbad, "; ".join(rbad) or f"both inBattle, phase Active, battleId equal; turn / side {SAVED_AT} and "
         f"mapFingerprint == SAVED's; census == SAVED's (faction 0 seat 1 == SQ, faction 1 seat 0 without AI); tops BattlescapeState")
    ev["hashAfterResume"] = hash_res(host, c2)
    pv, hc, hg = pvp(host), G3E.coop(host), host.ok({"cmd": "geo_state"})
    smp = BT37.sample(host, xb["name"], client0["sky"], t0)
    tgt = saved["pvpBorrow"]["targetCoopId"]
    ev.update(borrowSample=smp, hostGeo={"realBases": G3E.real_bases(hg), "time": hg.get("time")})
    want = {"active": True, "resumeBorrowed": 1, "kind": "landing", "targetKind": "site", "targetCoopId": tgt,
            "craftId": client0["sky"]["id"]}
    bbad = [f"host pvpBorrow.{k} {pv.get(k, 'absent')!r} (want {w!r})" for k, w in want.items() if pv.get(k) != w]
    bbad += [f"host noBases {hc.get('noBases')!r} (want false)"] if hc.get("noBases") is not False else []
    parked = rb((pv.get("parked") or {}).get("realBases"))
    bbad += [f"pvpBorrow.parked.realBases {parked} (want HOST0's {host0['realBases']})"] if parked != host0["realBases"] else []
    bbad += [f"host real bases {G3E.real_bases(hg)} (want CLIENT0's {client0['realBases']})"] \
        if G3E.real_bases(hg) != client0["realBases"] else []
    mirrors = [s for s in smp["sites"] if s.get("coopId") == tgt]
    bbad += [f"the borrowed Skyranger destKind {smp['destKind']!r}, coop sites {smp['sites']} (want destKind 'site' and one coop "
             f"site with coopId {tgt})"] if smp["destKind"] != "site" or len(mirrors) != 1 else []
    cell("P4-borrow", not bbad, "; ".join(bbad) or f"host pvpBorrow active, resumeBorrowed 1, landing / site {tgt}, craft "
         f"{client0['sky']['id']}; noBases false; parked == HOST0; live world == CLIENT0's; the rebuilt mirror")
    return True


def win_cells(host, c2, site, sq, m0, saved, host0, client0, ev):
    """FX4B-8 / FX4B-9: the win, both debriefings, the host's page 3, client2's OK first, then the host's. P4-host .. P4-alien."""
    a = ev["win"] = {}
    G2F.kill_all(host, c2, 1, a, "kills")
    if "DebriefingState" not in stack(host):
        a["endTurn"] = c2.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        a["closeNext"] = BES.close_host_nextturn(host)
    ok, secs = wait(lambda: "DebriefingState" in stack(host), DEBRIEF_S)
    hdeb = host.cmd({"cmd": "debrief_state"})
    ev["hostDebrief"] = {k: v for k, v in hdeb.items() if k != "widgets"}
    if not ok:
        cell("P4-host", False, f"no host DebriefingState within {DEBRIEF_S} s (stack {stack(host)})")
        block(["P4-client", "P4-return", "P4-alien"], "the host's debriefing never opened (P4-host)")
        return
    a["flip"] = P3.to_page2(host)
    hp3 = G3E.page3(host)
    ev["hostPage3"] = hp3
    hbad = [f"debrief_state.{k}={hdeb.get(k)!r} (want {w!r})" for k, w in (("title", TITLE_WIN), ("displayOnly", False))
            if hdeb.get(k) != w]
    hbad += [f"page 3 not reached (page {hp3.get('page')}, onTop {hp3.get('onTop')})"] if hp3.get("page") != 2 else []
    hbad += [f"page 3 {k} {hp3.get(k)!r} (want false, E4)" for k in ("sellVisible", "transferVisible") if hp3.get(k) is not False]
    cell("P4-host", not hbad, "; ".join(hbad) or f"host DebriefingState {secs} s, {TITLE_WIN!r}, displayOnly false; page 3 Sell and "
         "Transfer hidden")
    cok, csecs = wait(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True and d.get("displayOnly") is True)(
        c2.cmd({"cmd": "debrief_state"})), CLIENT_DEBRIEF_S)
    hv, cv = BES.debrief_view(hdeb), BES.debrief_view(c2.cmd({"cmd": "debrief_state"}))
    ev["client2Debrief"] = cv
    cbad = [] if cok else [f"no client2 display-only DebriefingState within {CLIENT_DEBRIEF_S} s (stack {stack(c2)})"]
    cbad += [f"client2 {k}={cv.get(k)!r} != host {hv.get(k)!r}" for k in BES.DEBRIEF_FIELDS if cok and cv.get(k) != hv.get(k)]
    cell("P4-client", not cbad, "; ".join(cbad) or f"client2 display-only debriefing {csecs} s, equal on DEBRIEF_FIELDS")
    aok, asecs = wait(lambda: (BES.record(c2).get("worldAdopted") or 0) >= 1, ADOPT_S)     # G3E D1's order: adopted, then the OK
    t_ok = time.time()
    pk = BES.press_ok(c2)
    _r, cscreens = BES.drain(c2, timeout=OK_S)
    gok, gs = wait(lambda: BES.geo_clean(c2), OK_S)
    crec, csky, cco = BES.record(c2), G3E.sky_of(c2, client0["sky"]), G3E.coop(c2)
    csq = {sid: G3E.srec(c2, sid) for sid in sq}
    ev["client2Ok"] = {"adoptS": asecs, "adopted": aok, "press": pk, "drain": cscreens, "geoS": round(time.time() - t_ok, 2),
                       "stack": stack(c2), "battleEnd": crec, "sky": csky, "noBases": cco.get("noBases"),
                       "sq": {sid: {k: csq[sid].get(k) for k in ("where", "missions", "dead")} for sid in sq},
                       "time": c2.ok({"cmd": "geo_state"}).get("time")}
    rbad = [] if gok else [f"client2 not on a clean GeoscapeState {OK_S} s after its OK (stack {stack(c2)})"]
    rbad += [f"battleEnd.{k} {crec.get(k)!r} (want {w!r})" for k, w in (("debriefOkBranch", "campaign-client-borrowed"),
                                                                         ("worldAdopted", 1)) if crec.get(k) != w]
    for sid in sq:
        want_m = m0[sid] + 1 if isinstance(m0[sid], int) else None
        if csq[sid].get("where") != "base" or csq[sid].get("missions") != want_m:
            rbad.append(f"SQ {sid}: where {csq[sid].get('where')!r} missions {csq[sid].get('missions')!r} (want 'base', {want_m})")
    rbad += [] if G3E.returning_or_at_base(csky) else [f"client2 Skyranger {csky} (want returning or at base)"]
    rbad += [f"client2 noBases {cco.get('noBases')!r} (want false)"] if cco.get("noBases") is not False else []
    cell("P4-return", not rbad, "; ".join(rbad) or f"client2 geo_clean; campaign-client-borrowed, worldAdopted 1; SQ in base with "
         f"missions + 1; Skyranger {csky}; noBases false")
    hk = BES.press_ok(host)
    hreached, hscreens, on994 = G2F.drain_host(host)
    hgok, hgs = wait(lambda: BES.geo_clean(host), HOST_OK_S) if hreached else (False, 0)
    hco, hg = G3E.coop(host), host.ok({"cmd": "geo_state"})
    pv = hco.get("pvpBorrow") or {}
    gone, gone_s = wait(lambda: not G3E.has_site(host, site_id=site), SITE_S)
    ev["hostOk"] = {"press": hk, "drain": hscreens, "on994": on994, "geoS": hgs, "stack": stack(host), "noBases": hco.get("noBases"),
                    "funds": hg.get("funds"), "realBases": G3E.real_bases(hg), "time": hg.get("time"), "pvpBorrow": pv,
                    "siteGoneS": gone_s, "client2Mirror": G3E.has_site(c2, point=ev.get("point"))}
    abad = [] if hgok else [f"host not on a clean GeoscapeState after its OK (reached {hreached}, 994 {on994}, stack {stack(host)})"]
    abad += [f"host noBases {hco.get('noBases')!r} (want true)"] if hco.get("noBases") is not True else []
    abad += [f"host funds {hg.get('funds')!r} (want {STUB_FUNDS})"] if hg.get("funds") != STUB_FUNDS else []
    abad += [f"host real bases {G3E.real_bases(hg)} (want HOST0's {host0['realBases']})"] \
        if G3E.real_bases(hg) != host0["realBases"] else []
    abad += [f"host pvpBorrow.active {pv.get('active')!r} (want false)"] if pv.get("active") is not False else []
    abad += [f"host pvpBorrow.home {pv.get('home', 'absent')!r} != parked {pv.get('parked')!r}"] \
        if "home" not in pv or pv.get("home") != pv.get("parked") else []
    fate, tgt = pv.get("fate") or {}, saved["pvpBorrow"]["targetCoopId"]
    abad += [f"host pvpBorrow.fate {pv.get('fate')!r} (want kind 'site', coopId {tgt}, action 'deleted')"] \
        if (fate.get("kind"), fate.get("coopId"), fate.get("action")) != ("site", tgt, "deleted") else []
    abad += [] if gone else [f"the host's real site {site} still in its missionSites {SITE_S} s after its OK"]
    cell("P4-alien", not abad, "; ".join(abad) or f"host geo_clean ({hgs} s), noBases true, funds {STUB_FUNDS}, real bases == HOST0; "
         f"pvpBorrow.active false, home == parked; fate {fate}; site {site} gone ({gone_s} s)")


def common_cell(host, c2, crash0, ev):
    desync(ev, host, c2)
    reads = ev.get("desyncReads", [])
    new = sorted(crash_set() - crash0)
    bad = [f"desyncSeen {nm} {v!r} at a read" for nm, v in reads if v is not False]
    bad += [f"{len(new)} new crash file(s) since the boot's start (first {os.path.basename(new[0])})"] if new else []
    bad += [f"hash after the first spine: {ev.get('hashAfterSpine')}"] if ev.get("hashAfterSpine") != "EQUAL" else []
    bad += [f"hash after RESUME: {ev.get('hashAfterResume', 'not reached')}"] if ev.get("hashAfterResume") != "EQUAL" else []
    bad += [f"client2 zero-disk: {session.save_files(c2.user_dir)}"] if session.save_files(c2.user_dir) else []
    cell("P4-common", not bad, "; ".join(bad) or f"desyncSeen false at {len(reads)} reads (host, client, client2), 0 new crash "
         "files, hash_now full EQUAL after the first spine and after RESUME, client2 zero-disk")


def boot_p(x, ev):
    host, client = x["host"], x["client"]
    crash0 = crash_set()
    host0, client0, xb = bring_up(host, client, ev)
    site, sq, m0, saved = land_to_saved(host, client, xb, client0, ev)
    path = save_cell(host, client, saved, ev)
    p5 = {}
    try:
        p5_cells(path, saved, host0, client0, p5)
    finally:
        evidence("P5", p5)
        row_verdict("P5")
        x["p5"] = True
    desync(ev, host, client)
    host, c2 = relaunch(x, ev)
    if resume_cells(host, c2, os.path.basename(path), saved, sq, host0, client0, xb, ev):
        win_cells(host, c2, site, sq, m0, saved, host0, client0, ev)
    else:
        block(ROWS["P4"][2:7], "the resumed battle never started (P4-resume)")
    common_cell(host, c2, crash0, ev)


def run():
    x = {"host": GameClient("host", None, make_user_dir(TAG + "_host")),
         "client": GameClient("client", None, make_user_dir(TAG + "_client")), "client2": None}
    ev, t0 = {}, time.time()
    try:
        boot_p(x, ev)
    except FixtureMiss as e:
        block(ALL_CELLS, f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        ev["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"[ERROR] boot P: {ev['error']}", flush=True)
        block(ALL_CELLS, f"error {ev['error']}")
    finally:
        ev["wall"] = round(time.time() - t0, 1)
        evidence("P4", ev)
        if not x.get("p5"):
            row_verdict("P5")
        row_verdict("P4")
        for gc in (x["client2"], x["client"], x["host"]):
            try:
                if gc is not None and gc.proc is not None and gc.proc is not getattr(gc, "_shutdown_proc", None):
                    gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)
    return t0


def main():
    t0 = run()
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== D250-U S-C4b a gm3 borrowed battle saved and resumed: {len(RESULTS) - len(fails)}/{len(ALL_CELLS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (FIX cell)' if n in FIX else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(ALL_CELLS) else 2)


if __name__ == "__main__":
    main()
