"""test_campaign_battle_gm2.py: a gm2 PvP campaign battle end to end (host = X-COM, client = the aliens):
entry with the right seats, the alien player moves an alien, an X-COM win and an X-COM loss, and after each the alien player sees
the host's debriefing and returns to its own geoscape with its alien-side role intact (no bases, stub budget 1000, no sim of its own).

Spec: docs rewrite/prompts/d250u_pvp_campaigns.md, section (f) "test_campaign_battle_gm2.py", with orchestrator rulings
R-D250-SA-2, R-D250-SB-1 and R-D250-SB-2 (owner D250; P7-6 VL3, D156, D180; QD-6..QD-8; F13087, F13791, F13792).
TASK 0 pins: docs rewrite/d250u-task0/sb/CONSTANTS.md (SEED_B, MAP_FP_B, A, A_DEST and STUB on the unchanged build and on the
TASK 0-only EB2 probe build; TITLE_WIN, SEED_B4, MAP_FP_B4, TITLE_LOSS and the return values on the probe build; each 2/2).

Boot B: gm2, lobby key 47938, dirs d250u_b_host / d250u_b_client. Bring-up: PF.start_pvp_campaign(alien_player="client"); crash
baseline; geo.slow_clock. A bring-up or B1 landing step past its bound is a setup failure: ONE "CAPTURE B:" line, every row FAILs "boot".
Rows and cells (one PASS / FAIL line per cell, one EVIDENCE line and one ROW line per row; every row runs after a failure unless its
precondition was never reached, then each of its cells FAILs "blocked: <why>"):
  B1 entry: squad of two, site, craft forced out, landing, host set_seed SEED_B, confirm_landing, both inBattle <= 180 s,
     session.briefings_to_battlescape.
     B1-gm (gamemode 2 on both, read at entry), B1-entry (the spine; turn 1 and MAP_FP_B on both), B1-seats (entry census: faction 0
     seat 0, faction 1 seat 1 without AI, equal on both), B1-role (noBases client true / host false at entry), B1-walk (host END
     TURN; the client walks A to A_DEST: one new host context {intent, walk, A}, A on A_DEST on both; client END TURN; side 0 turn 2).
  B2 X-COM wins: host kill_unit_real every live alien, chain settled after each; host END TURN; the host's NextTurnState closed.
     B2-host, B2-client, B2-return, B2-alien, B2-no994 (no CoopState 994 on the host after the client's OK, F13791 - never drained),
     B2-hostok.
  B3 three game days: B3-frozen.
  B4 X-COM loses (second battle, SEED_B4): host kill_unit_real every live X-COM unit (the last kill ends the X-COM side by itself,
     F13792: the wait stops at NextTurnState on both); host END TURN; NextTurnState closed.
     B4-host, B4-client, B4-no994, B4-alien, B4-hostok.
  Each row's <row>-common cell: event_state.desyncSeen false on both, 0 new crash files in the row, in a battle hash_now EQUAL.
RED (the unchanged product, R-D250-SB-1): the gm2 alien client's noBases flips at the battle-blob load, its entry snapshot
fails (CoopState 995 over its briefing) and its streamer floods crash logs, so the spine stops at the client's briefing:
B1-gm and B1-seats PASS, every other cell FAILs. GREEN (EB2 + EB3): every cell PASSes.

ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_campaign_battle_gm2.py
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

# ----- TASK 0 pins (docs rewrite/d250u-task0/sb/CONSTANTS.md, 2/2 each) -----
KEY = "47938"
SEED_B = 1
MAP_FP_B = 5.996615470105667e+18
A_ID = 1000000                      # the lowest-id live alien at SEED_B
A_DEST = (3, 15, 1)                 # A's first free floor neighbour (N holds an object part)
STUB = [{"name": "", "lon": 0.0, "lat": 0.0, "soldiers": 8}]   # the gm2 alien client's real base
STUB_FUNDS = 1000
TITLE_WIN = "Aliens defeated"
SEED_B4 = 1
MAP_FP_B4 = -4.990271614617468e+18  # EVIDENCE only
TITLE_LOSS = "Craft is lost"
SQUAD = 2
SITE = {"mission": "STR_ALIEN_RESEARCH", "deployment": "STR_MEDIUM_SCOUT", "race": "STR_SECTOID", "hours": 240}
# ----- bounds -----
BOTH_IN_S = 180
LANDING_S = 180
STEP_S = 60
DEBRIEF_S = 60
CLIENT_DEBRIEF_S = 20
OK_S = 10
DRAIN_S = 60
WATCH994_S = 3.0      # the 994 showed 0.78 s / 1.14 s after the client's OK on the probe build
KILL_S = 45
REJECT_LINE = "rejected client progress blob"   # the host's log line before its 994 (TCP writeHostMapSaveProgressFile)


class FixtureMiss(Exception):
    pass


class Blocked(Exception):
    pass


RESULTS = []          # (cell, ok, detail)


def cell(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)


def block(names, why):
    for n in names:
        cell(n, False, f"blocked: {why}")


def evidence(row, obj):
    print(f"EVIDENCE {row}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)


def row_verdict(row, names):
    bad = [n for n, ok, _ in RESULTS if n in names and not ok]
    print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)


def stack(gc):
    return session.states_stripped(gc)


def top(gc):
    st = stack(gc)
    return st[-1] if st else None


def crash_set():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))


def coop(gc):
    r = gc.cmd({"cmd": "get_coop"})
    return {k: r.get(k) for k in ("gamemode", "noBases", "coopDialog")}


def geo_view(gc):
    g = gc.ok({"cmd": "geo_state"})
    return {"funds": g.get("funds"),
            "realBases": [{k: b.get(k) for k in ("name", "lon", "lat", "soldiers")} for b in g.get("bases", [])
                          if not b.get("coopBase") and not b.get("coopIcon")],
            "ownUfos": [u.get("id") for u in g.get("ufos", []) if not u.get("coop")],
            "ownSites": [m.get("id") for m in g.get("missionSites", []) if not m.get("coop")],
            "siteIds": [m.get("id") for m in g.get("missionSites", [])]}


def census(gc):
    return [{k: u.get(k) for k in ("id", "faction", "coop", "hasAI", "isOut")} for u in battle_state(gc).get("units", [])]


def host_soldiers(host):
    b = next((b for b in host.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    return [s["id"] for s in (b or {}).get("soldiers", [])]


def hash_ok(host, client):
    try:
        session.assert_hash_clean(host, client, full=True)
        return True, "EQUAL"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:400]


def common(row, host, client, crash0, in_battle, ctx):
    eh, ec = event_state(host), event_state(client)
    new = sorted(crash_set() - crash0)
    bad = []
    if eh.get("desyncSeen") is not False or ec.get("desyncSeen") is not False:
        bad.append(f"desyncSeen host {eh.get('desyncSeen')!r} client {ec.get('desyncSeen')!r} (want false on both)")
    if new:
        bad.append(f"{len(new)} new crash file(s) in the row (first {os.path.basename(new[0])})")
    if in_battle is not None:
        if in_battle[0] is not True:
            bad.append(f"hash_now full: {in_battle[1]}")
    cell(f"{row}-common", not bad, "; ".join(bad) or "desyncSeen false on both, 0 new crash files"
         + (", hash_now full EQUAL" if in_battle is not None else ""))
    ctx.setdefault("crash", {})[row] = len(new)


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
    print(f"CAPTURE B: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def to_battle(host, client, lon_off, seed, ev, boot):
    """Squad of two, a site at b0 + lon_off, the Skyranger forced out to it, the landing wait, host set_seed, confirm_landing, both
    inBattle. A miss: boot=True -> setup failure (CAPTURE B:), else Blocked. Returns the site id."""
    def miss(err):
        if boot:
            capture_boot(err, host, client)
        raise Blocked(err)
    geo.slow_clock(host, client)
    b0 = session._campaign_base0(host)
    sky = next((c for c in b0.get("crafts", []) if "SKYRANGER" in c.get("type", "")), None)
    sids = host_soldiers(host)
    if not sky or len(sids) < SQUAD:
        miss(f"no Skyranger or fewer than {SQUAD} soldiers (sky {sky}, soldiers {sids})")
    for sid in sids:
        host.ok({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": False})
    for sid in sids[:SQUAD]:
        host.ok({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": True})
    site = host.ok(dict(SITE, cmd="spawn_mission_site", lon=b0["lon"] + lon_off, lat=b0["lat"] + 0.10))
    if not site.get("ok"):
        miss(f"spawn_mission_site {site}")
    step = 0.01 if lon_off > 0 else -0.01
    host.ok({"cmd": "craft_force", "craft_id": sky["id"], "status": "STR_OUT", "lon": b0["lon"] + lon_off - step,
             "lat": b0["lat"] + 0.10, "dest": f"site:{site['site_id']}", "fuel": 999999, "lowFuel": False})

    def prompt():
        if session.has_state(host, "ConfirmLandingState"):
            return True
        for gc in (host, client):
            geo.drain_popups(gc, interest=geo.popup("ConfirmLandingState"))
            gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None
    try:
        host.wait_for("landing prompt", prompt, timeout=LANDING_S, interval=0.5)
    except Exception as e:  # noqa: BLE001
        miss(f"landing prompt: {e}")
    host.ok({"cmd": "set_seed", "seed": seed})
    host.ok({"cmd": "confirm_landing"})
    ok, secs = BES.wait_until(lambda: bool(battle_state(host).get("inBattle"))
                              and bool(battle_state(client).get("inBattle")), BOTH_IN_S)
    ev.update(squad=sids[:SQUAD], site=site["site_id"], bothInS=secs)
    if not ok:
        miss(f"not both inBattle within {BOTH_IN_S} s of confirm_landing")
    return site["site_id"]


def spine(host, client, ev):
    """session.briefings_to_battlescape; returns (ok, detail). Turn and map are read after it."""
    try:
        session.briefings_to_battlescape(host, client)
        return True, "spine passed"
    except Exception as e:  # noqa: BLE001
        ev["spineError"] = str(e)[:400]
        ev["stacksAtSpine"] = [stack(host), stack(client)]
        ev["clientDialog"] = client.cmd({"cmd": "coop_dialog_info"})
        return False, f"session.briefings_to_battlescape raised: {str(e)[:300]} (stacks {ev['stacksAtSpine']})"


def kill_all(host, client, faction, ev, key):
    """host kill_unit_real every live unit of `faction`; after each, wait (<= KILL_S) for the chain to settle (host idle, top
    BattlescapeState, the client caught up, held 1 s) or for the side to end (F13792: NextTurnState on both, or the host's
    DebriefingState)."""
    rows = []
    for uid in [u["id"] for u in battle_state(host).get("units", []) if u.get("faction") == faction and not u.get("isOut")]:
        r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": uid})
        t0, since, how = time.time(), None, "timeout"
        while time.time() - t0 < KILL_S:
            hs, cs = stack(host), stack(client)
            if "DebriefingState" in hs or (hs[-1:] == ["NextTurnState"] and cs[-1:] == ["NextTurnState"]):
                how = "side ended"
                break
            bs, ec, eh = battle_state(host), event_state(client), event_state(host)
            idle = (not bs.get("isBusy") and bs.get("pendingStates") == 0 and hs[-1:] == ["BattlescapeState"]
                    and eh.get("lastSeqEmitted") == ec.get("lastSeqApplied"))
            since = (since or time.time()) if idle else None
            if since and time.time() - since >= 1.0:
                how = "settled"
                break
            time.sleep(0.2)
        rows.append({"unit": uid, "ok": r.get("ok"), "error": r.get("error"), "how": how, "s": round(time.time() - t0, 2)})
    ev[key] = rows
    return rows


def end_and_debrief(host, client):
    """host END TURN + the host's NextTurnState closed (unless the host already debriefs); then the host's DebriefingState."""
    if "DebriefingState" not in stack(host):
        host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        BES.close_host_nextturn(host)
    return BES.wait_until(lambda: "DebriefingState" in stack(host), DEBRIEF_S)


def drain_host(host, timeout=DRAIN_S, interval=0.4):
    """The host's OK + follow-ups down to GeoscapeState, NEVER draining a CoopState 994: a 994 on top stops the
    drain. Other CoopStates -> coop_dialog_back, the debriefing / follow-ups -> dismiss_popup, BES.WAIT_TOPS left alone.
    Returns (reached, screens, stopped_on_994)."""
    screens, t0 = [], time.time()
    while time.time() - t0 < timeout:
        t = top(host) or ""
        if t == "GeoscapeState":
            return True, screens, False
        if any(n in t for n in BES.WAIT_TOPS):
            time.sleep(interval)
            continue
        if "CoopState" in t:
            d = host.cmd({"cmd": "coop_dialog_info"})
            if d.get("code") == 994:
                screens.append({"t": round(time.time() - t0, 2), "top": t, "code": 994, "title": d.get("title")})
                return False, screens, True
            r = host.cmd({"cmd": "coop_dialog_back"})
            screens.append({"t": round(time.time() - t0, 2), "top": t, "code": d.get("code"), "resp": r.get("ok")})
        else:
            r = host.cmd({"cmd": "dismiss_popup"})
            screens.append({"t": round(time.time() - t0, 2), "top": t, "resp": r.get("handled") or r.get("error")})
        time.sleep(interval)
    return False, screens, False


def battle_end_cells(row, host, client, title, site_id, ev, soldiers0=None):
    """The debriefings and both returns, shared by B2 and B4. Cells: <row>-host, <row>-client, the client's return cell(s),
    <row>-no994, <row>-hostok."""
    ok, secs = BES.wait_until(lambda: "DebriefingState" in stack(host), DEBRIEF_S)
    hdeb = host.cmd({"cmd": "debrief_state"})
    ev["hostDebrief"] = {k: hdeb.get(k) for k in ("shown", "onTop", "displayOnly", "title", "rating", "total")}
    hbad = [] if ok else [f"no host DebriefingState within {DEBRIEF_S} s (stack {stack(host)})"]
    hbad += [f"debrief_state.{k}={hdeb.get(k)!r} (want {w!r})" for k, w in (("title", title), ("displayOnly", False))
             if hdeb.get(k) != w]
    if row == "B2":
        cell("B2-host", not hbad, "; ".join(hbad) or f"host DebriefingState {secs} s, title {title!r}, displayOnly false")
    cok, csecs = BES.wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                         and d.get("displayOnly") is True)(client.cmd({"cmd": "debrief_state"})),
                                CLIENT_DEBRIEF_S)
    cdeb = client.cmd({"cmd": "debrief_state"})
    hv, cv = BES.debrief_view(hdeb), BES.debrief_view(cdeb)
    ev["clientDebrief"] = cv
    cbad = [] if cok else [f"no client display-only DebriefingState within {CLIENT_DEBRIEF_S} s (stack {stack(client)})"]
    cbad += [f"client {k}={cv.get(k)!r} != host {hv.get(k)!r}" for k in BES.DEBRIEF_FIELDS if cok and cv.get(k) != hv.get(k)]
    cell(f"{row}-client", not cbad, "; ".join(cbad) or f"client display-only debriefing {csecs} s, equal on DEBRIEF_FIELDS")
    # the client's OK first
    rejects0 = BES.log_count(host, REJECT_LINE)
    t_ok = time.time()
    pk = BES.press_ok(client)
    reached, screens = BES.drain(client, timeout=OK_S)
    gok, gsecs = BES.wait_until(lambda: BES.geo_clean(client), OK_S)
    g, c = geo_view(client), coop(client)
    sep = BES.record(client).get("sepReturn") or {}
    ev["clientReturn"] = {"ok": pk, "drain": screens, "geoS": round(time.time() - t_ok, 2), "stack": stack(client), "coop": c,
                          "geo": g, "sepReturn": sep}
    rbad = []
    if not pk.get("pressed") or (pk.get("resp") or {}).get("handled") != "DebriefingState":
        rbad.append(f"client OK {pk}")
    if not gok:
        rbad.append(f"client not geo_clean within {OK_S} s of its OK (stack {stack(client)})")
    if row == "B2":
        bad_sep = {k: (sep.get(k), w) for k, w in (("ownLoaded", 1), ("guestsApplied", 0), ("guestsMissing", 0))
                   if sep.get(k) != w}
        if bad_sep:
            rbad.append(f"sepReturn (got, want) {bad_sep}")
        if g["realBases"] != STUB:
            rbad.append(f"client real bases {g['realBases']} (want STUB {STUB})")
        cell("B2-return", not rbad, "; ".join(rbad) or f"client geo_clean {gsecs} s after its OK; sepReturn ownLoaded 1, "
             f"guestsApplied 0, guestsMissing 0; real bases == STUB")
        abad = [f"client noBases {c.get('noBases')!r} (want true)"] if c.get("noBases") is not True else []
        abad += [f"client funds {g['funds']!r} (want {STUB_FUNDS})"] if g["funds"] != STUB_FUNDS else []
        cell("B2-alien", not abad, "; ".join(abad) or f"client noBases true, funds {STUB_FUNDS}")
    else:
        if c.get("noBases") is not True:
            rbad.append(f"client noBases {c.get('noBases')!r} (want true)")
        if g["funds"] != STUB_FUNDS:
            rbad.append(f"client funds {g['funds']!r} (want {STUB_FUNDS})")
        if g["realBases"] != STUB:
            rbad.append(f"client real bases {g['realBases']} (want STUB {STUB})")
        cell("B4-alien", not rbad, "; ".join(rbad) or f"client geo_clean {gsecs} s after its OK; noBases true, funds "
             f"{STUB_FUNDS}, real bases == STUB")
    # watch the host, never drain a 994
    watch, tw = [], time.time()
    while time.time() - t_ok < WATCH994_S:
        if top(host) == "CoopState":
            d = host.cmd({"cmd": "coop_dialog_info"})
            if d.get("code") == 994:
                watch.append({"t": round(time.time() - t_ok, 2), "code": 994, "title": d.get("title")})
                break
        time.sleep(0.1)
    rejects = BES.log_count(host, REJECT_LINE) - rejects0
    ev["hostWatch"] = {"seen": watch, "rejectLines": rejects, "watchedS": round(time.time() - tw, 2)}
    nbad = [f"host CoopState 994 {watch[0]['title']!r} {watch[0]['t']} s after the client's OK"] if watch else []
    nbad += [f"{rejects} new host log line(s) '{REJECT_LINE}'"] if rejects else []
    cell(f"{row}-no994", not nbad, "; ".join(nbad) or f"no CoopState 994 on the host within {WATCH994_S} s of the client's "
         f"OK, 0 '{REJECT_LINE}' lines")
    # the host's OK
    hk = BES.press_ok(host)
    hreached, hscreens, on994 = drain_host(host)
    gok, gsecs = BES.wait_until(lambda: BES.geo_clean(host), DRAIN_S) if hreached else (False, 0)
    hg = geo_view(host) if gok else {}
    ev["hostOk"] = {"ok": hk, "drain": hscreens, "stack": stack(host), "siteIds": hg.get("siteIds")}
    kbad = []
    if on994:
        kbad.append("a CoopState 994 sits over the host's debriefing (never drained, R-D250-SB-2)")
    elif not gok:
        kbad.append(f"host not geo_clean within {DRAIN_S} s of its OK (stack {stack(host)}, screens {hscreens})")
    if not any(s.get("resp") == "DebriefingState" for s in hscreens) and (hk.get("resp") or {}).get("handled") != "DebriefingState":
        kbad.append(f"the host's debriefing OK was never handled (press {hk}, screens {hscreens})")
    if gok and site_id in (hg.get("siteIds") or []):
        kbad.append(f"site {site_id} still in the host's missionSites {hg.get('siteIds')}")
    if row == "B4":
        sol = host_soldiers(host) if gok else None
        ev["soldiers"] = [soldiers0, sol and len(sol)]
        if sol is None or soldiers0 is None or len(sol) != soldiers0 - SQUAD:
            hbad.append(f"host soldiers {soldiers0} -> {sol and len(sol)} (want down by {SQUAD})")
        cell("B4-host", not hbad, "; ".join(hbad) or f"host DebriefingState, title {title!r}; soldiers {soldiers0} -> "
             f"{soldiers0 - SQUAD}")
    cell(f"{row}-hostok", not kbad, "; ".join(kbad) or f"host geo_clean {gsecs} s after its OK; site {site_id} gone")


def run(host, client):
    ctx = {"blocked": None}
    host.spawn(); host.connect(); client.spawn(); client.connect()
    try:
        gm = PF.start_pvp_campaign(host, client, KEY, alien_player="client")
    except Exception as e:  # noqa: BLE001
        capture_boot(f"PF.start_pvp_campaign: {e}", host, client)
    stub = geo_view(client)["realBases"]
    geo.slow_clock(host, client)
    print(f"[bring-up] gamemode {gm}; client STUB {stub}", flush=True)

    # ===== B1 =====
    names = ["B1-gm", "B1-entry", "B1-seats", "B1-role", "B1-walk", "B1-common"]
    crash0, ev = crash_set(), {"stub": stub}
    site1 = to_battle(host, client, 0.35, SEED_B, ev, boot=True)
    ch, cc = coop(host), coop(client)
    hcen, ccen = census(host), census(client)
    ev.update(coopAtEntry={"host": ch, "client": cc}, censusHost=hcen, censusClient=ccen, stacksAtEntry=[stack(host), stack(client)])
    cell("B1-gm", ch.get("gamemode") == 2 and cc.get("gamemode") == 2,
         f"get_coop.gamemode host {ch.get('gamemode')} client {cc.get('gamemode')} (want 2 on both)")
    sp_ok, sp_detail = spine(host, client, ev)
    bh, bc = battle_state(host), battle_state(client)
    turn, fp = [bh.get("turn"), bc.get("turn")], [bh.get("mapFingerprint"), bc.get("mapFingerprint")]
    ev.update(turn=turn, mapFingerprint=fp)
    ebad = [] if sp_ok else [sp_detail]
    ebad += [f"turn {turn} (want [1, 1])"] if turn != [1, 1] else []
    ebad += [f"mapFingerprint {fp} (want both {MAP_FP_B!r}, SEED_B {SEED_B})"] if fp != [MAP_FP_B, MAP_FP_B] else []
    cell("B1-entry", not ebad, "; ".join(ebad) or f"turn 1 on both, mapFingerprint {MAP_FP_B!r} on both")
    sbad = []
    for nm, cen in (("host", hcen), ("client", ccen)):
        live = [u for u in cen if not u.get("isOut")]
        f0 = [u for u in live if u.get("faction") == 0]
        f1 = [u for u in cen if u.get("faction") == 1]
        if not f0 or not f1:
            sbad.append(f"{nm}: faction 0 units {len(f0)}, faction 1 units {len(f1)} (want both > 0)")
        sbad += [f"{nm}: unit {u['id']} faction 0 seat {u.get('coop')}" for u in f0 if u.get("coop") != 0]
        sbad += [f"{nm}: unit {u['id']} faction 1 seat {u.get('coop')} hasAI {u.get('hasAI')}" for u in f1
                 if u.get("coop") != 1 or u.get("hasAI") is not False]
        sbad += [f"{nm}: unit {u['id']} faction {u.get('faction')}" for u in cen if u.get("faction") not in (0, 1)]
    key = lambda cen: sorted((u["id"], u.get("faction"), u.get("coop")) for u in cen)
    if key(hcen) != key(ccen):
        sbad.append(f"census (id, faction, seat) host {key(hcen)} != client {key(ccen)}")
    cell("B1-seats", not sbad, "; ".join(sbad) or f"entry census equal on both: faction 0 seat 0, faction 1 seat 1 without AI "
         f"({len(hcen)} units)")
    rbad = [f"client noBases {cc.get('noBases')!r} (want true)"] if cc.get("noBases") is not True else []
    rbad += [f"host noBases {ch.get('noBases')!r} (want false)"] if ch.get("noBases") is not False else []
    cell("B1-role", not rbad, "; ".join(rbad) or "noBases client true, host false at the battle entry")
    in_battle = None
    if not ebad:
        try:
            host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
            RSB.drive_side_change(host, client, 1, timeout=STEP_S)
            ctx0 = event_state(host).get("closedContexts") or []
            prev = session.walk_action_id(host)
            ev["walk"] = {k: v for k, v in session.send_walk(client, A_ID, A_DEST).items() if k in ("ok", "error", "iseq")}
            session.wait_walk_settled(host, client, prev, timeout=STEP_S)
            seen = {c.get("actionId") for c in ctx0}
            new = [c for c in (event_state(host).get("closedContexts") or []) if c.get("actionId") not in seen]
            apos = [session.pos_of(session.unit_of(host, A_ID)), session.pos_of(session.unit_of(client, A_ID))]
            in_battle = hash_ok(host, client)
            client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
            RSB.drive_side_change(host, client, 0, want_turn_min=2, timeout=STEP_S)
            ts = [(battle_state(gc).get("turn"), battle_state(gc).get("side")) for gc in (host, client)]
            ev.update(newContexts=new, Apos=apos, turnSide=ts)
            wbad = []
            if [(c.get("origin"), c.get("kind"), c.get("actorId")) for c in new] != [("intent", "walk", A_ID)]:
                wbad.append(f"new host contexts {new} (want exactly one {{intent, walk, {A_ID}}})")
            if apos != [tuple(A_DEST), tuple(A_DEST)]:
                wbad.append(f"A {A_ID} at host/client {apos} (want {A_DEST} on both)")
            if ts != [(2, 0), (2, 0)]:
                wbad.append(f"(turn, side) host/client {ts} (want (2, 0) on both)")
            cell("B1-walk", not wbad, "; ".join(wbad) or f"one {{intent, walk, {A_ID}}} context; A on {A_DEST} on both; side 0 "
                 f"turn 2 on both")
        except Exception as e:  # noqa: BLE001
            cell("B1-walk", False, f"{type(e).__name__}: {str(e)[:400]}")
            in_battle = hash_ok(host, client)
    else:
        block(["B1-walk"], "the entry spine did not reach turn 1 (B1-entry)")
        ctx["blocked"] = "the battle entry stopped at the spine (B1-entry)"
        in_battle = (False, "turn 1 never reached")
    common("B1", host, client, crash0, in_battle, ctx)
    evidence("B1", ev)
    row_verdict("B1", names)

    # ===== B2 =====
    names = ["B2-host", "B2-client", "B2-return", "B2-alien", "B2-no994", "B2-hostok", "B2-common"]
    if ctx["blocked"]:
        block(names, ctx["blocked"])
    else:
        crash0, ev = crash_set(), {}
        kill_all(host, client, 1, ev, "kills")
        in_battle = hash_ok(host, client) if top(host) == "BattlescapeState" else (False, f"host top {top(host)}")
        end_and_debrief(host, client)
        battle_end_cells("B2", host, client, TITLE_WIN, site1, ev)
        common("B2", host, client, crash0, in_battle, ctx)
        evidence("B2", ev)
    row_verdict("B2", names)

    # ===== B3 =====
    names = ["B3-frozen", "B3-common"]
    clean = [BES.geo_clean(host), BES.geo_clean(client)]
    if ctx["blocked"] or clean != [True, True]:
        ctx["blocked"] = ctx["blocked"] or f"not both on a clean geoscape after B2 (host/client {clean}: {stack(host)} / {stack(client)})"
        block(names, ctx["blocked"])
    else:
        crash0 = crash_set()
        d0 = host.ok({"cmd": "research_probe", "names": [], "tail": 0}).get("daysPassed")
        r = geo.skip_ingame_time(host, client, minutes=4320, speed_idx=5, real_timeout=60)
        d1 = host.ok({"cmd": "research_probe", "names": [], "tail": 0}).get("daysPassed")
        g, c = geo_view(client), coop(client)
        clean = [BES.geo_clean(host), BES.geo_clean(client)]
        ev = {"days": [d0, d1], "skip": {k: r.get(k) for k in ("game_minutes", "timed_out", "dismissed")}, "client": g, "coop": c}
        fbad = [f"client noBases {c.get('noBases')!r} (want true)"] if c.get("noBases") is not True else []
        fbad += [f"client funds {g['funds']!r} (want {STUB_FUNDS})"] if g["funds"] != STUB_FUNDS else []
        fbad += [f"client own UFOs {g['ownUfos']} (want none)"] if g["ownUfos"] else []
        fbad += [f"client own mission sites {g['ownSites']} (want none)"] if g["ownSites"] else []
        fbad += [f"host daysPassed {d0} -> {d1} (want >= +3)"] if not (isinstance(d0, int) and isinstance(d1, int) and d1 - d0 >= 3) else []
        fbad += [f"geo_clean host/client {clean} (stacks {stack(host)} / {stack(client)})"] if clean != [True, True] else []
        cell("B3-frozen", not fbad, "; ".join(fbad) or f"client noBases true, funds {STUB_FUNDS}, 0 own UFOs / sites; host "
             f"days {d0} -> {d1}; both on a clean geoscape")
        common("B3", host, client, crash0, None, ctx)
        evidence("B3", ev)
        if clean != [True, True]:
            ctx["blocked"] = f"not both on a clean geoscape after B3 ({stack(host)} / {stack(client)})"
    row_verdict("B3", names)

    # ===== B4 =====
    names = ["B4-host", "B4-client", "B4-no994", "B4-alien", "B4-hostok", "B4-common"]
    if ctx["blocked"]:
        block(names, ctx["blocked"])
    else:
        crash0, ev = crash_set(), {}
        try:
            soldiers0 = len(host_soldiers(host))
            site2 = to_battle(host, client, -0.35, SEED_B4, ev, boot=False)
            sp_ok, sp_detail = spine(host, client, ev)
            bh, bc = battle_state(host), battle_state(client)
            ev.update(turn=[bh.get("turn"), bc.get("turn")], mapFingerprint=[bh.get("mapFingerprint"), bc.get("mapFingerprint")],
                      mapFpPin=MAP_FP_B4)
            if not sp_ok or ev["turn"] != [1, 1]:
                raise Blocked(f"B4 entry: {sp_detail}; turn {ev['turn']}")
            in_battle = hash_ok(host, client)
            kill_all(host, client, 0, ev, "kills")
            end_and_debrief(host, client)
            battle_end_cells("B4", host, client, TITLE_LOSS, site2, ev, soldiers0=soldiers0)
            common("B4", host, client, crash0, in_battle, ctx)
        except Blocked as e:
            block([n for n in names if n not in {x[0] for x in RESULTS}], str(e))
        evidence("B4", ev)
    row_verdict("B4", names)


def main():
    host = GameClient("host", None, make_user_dir("d250u_b_host"))
    client = GameClient("client", None, make_user_dir("d250u_b_client"))
    all_cells = ["B1-gm", "B1-entry", "B1-seats", "B1-role", "B1-walk", "B1-common", "B2-host", "B2-client", "B2-return",
                 "B2-alien", "B2-no994", "B2-hostok", "B2-common", "B3-frozen", "B3-common", "B4-host", "B4-client", "B4-no994",
                 "B4-alien", "B4-hostok", "B4-common"]
    t0 = time.time()
    try:
        run(host, client)
    except FixtureMiss as e:
        block([n for n in all_cells if n not in {x[0] for x in RESULTS}], f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
        block([n for n in all_cells if n not in {x[0] for x in RESULTS}], f"error {type(e).__name__}: {str(e)[:200]}")
    finally:
        host.shutdown(); client.shutdown()
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== D250-U S-B gm2 PvP campaign battle: {len(RESULTS) - len(fails)}/{len(RESULTS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(all_cells) else 2)


if __name__ == "__main__":
    main()
