"""W2-H67 - test_solo_ironman_pause.py (SIP): a single-player ironman game's pause menu hides LOAD GAME and SAVE GAME (lead L-H63-1).
R-LT8-1 (VL-H67-1, VL-H67-2), R-H67-1 (QH67-1 .. QH67-5 (a)): vanilla hides both in an ironman pause menu and shows SAVE AND ABANDON GAME; the
co-op build's "truly solo" re-show blocks (constructor, init()) turn both back on in every single-player game, ironman included (F19821,
measured F19941). Spec: docs rewrite/prompts/w2h67_solo_ironman_hide.md (f); pins: docs rewrite/w2h67-task0/sa/CONSTANTS.md (TASK 0, 0ef641b8f).
Boot I (w2h67_i_sp, solo, the real IRONMAN toggle; precondition 2 start save lists, Cancel hidden on each):
  row G: geoscape OPTIONS click -> settled PauseState -> ONE list_widgets -> CANCEL: G-load, G-save, G-abandon.
  row B: seat 3, site, forced craft, ConfirmLandingState, confirm_landing, briefing OK, the equip screen's OK (ESC, F19940), close_nextturn,
         idle at turn 1 side 0, no SaveGameState / CoopState in the stack (SAVE_IRONMAN, F19832); ESC read: B-load, B-save, B-abandon.
Boot N (w2h67_n_sp, solo, no IRONMAN; precondition 0 lists): row N geoscape read: N-load, N-save, N-abandon.
Boot C (w2h67_c_host / _client, SEPARATE ironman co-op, key 49246; precondition host 2 lists, client 0): row C reads: C-host, C-client.
X-crash: no new file in harness.CRASH_DIR. Captions read by `visible`; CO-OP / GAME OPTIONS EVIDENCE only. RED: G-load, G-save, B-load, B-save
(4 of 12); GREEN (E1-E2) 12/12. Per row one EVIDENCE line, a PASS / FAIL line per cell, the verdict; every row runs after a failure; a miss
ends its row ("not reached (<step>)") or its boot ("boot"), ONE CAPTURE line. WV-D95 (foreground to completion), WV-D99 / WV-D100 (ONE run,
no skip path): exit 0 only when every cell passes, else 2.   Run:  python tools/coop_test/test_solo_ironman_pause.py
"""

import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT  # noqa: E402
import session  # noqa: E402
import pvp_fixture as PF  # noqa: E402

# ----- TASK 0 pins (docs rewrite/w2h67-task0/sa/CONSTANTS.md) -----
KEY = "49246"
NAME_I, NAME_N, NAME_C = "IronH67", "PlainH67", "IronH67C"
BASE_FALLBACK = (0.706, -0.507)        # session.HOST_LON / HOST_LAT is not land for a first base (F19943)
NGS_SETTLE, QUIET_SOLO, QUIET_COOP = 0.2, 4.0, 8.0
DRIVE_S, ARRIVAL_S, ENTRY_S, SETTLE_S, PAUSE_S, SETTLE_W = 150, 60, 60, 30, 10, 5
ESC = 27
LOAD, SAVE, SAA, ABANDON = "LOAD GAME", "SAVE GAME", "SAVE AND ABANDON GAME", "ABANDON GAME"
ROWS = {"G": ["G-load", "G-save", "G-abandon"], "B": ["B-load", "B-save", "B-abandon"], "N": ["N-load", "N-save", "N-abandon"],
        "C": ["C-host", "C-client"], "X": ["X-crash"]}
BOOTS = {"I": ["G", "B"], "N": ["N"], "C": ["C"]}
RED = {"G-load", "G-save", "B-load", "B-save"}
RESULTS = {}

class Miss(Exception):
    def __init__(self, step, why):
        super().__init__(f"{step}: {why}")
        self.step, self.why = step, why

def cell(name, ok, detail):
    RESULTS[name] = (bool(ok), detail)
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)

def finish_row(row, ev, step="not reached"):
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    for n in [n for n in ROWS[row] if n not in RESULTS]:
        cell(n, False, step)
    bad = [n for n in ROWS[row] if not RESULTS[n][0]]
    print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)

# ----- probes (copied from test_ironman_save_paths.py, test_client_landing_controls.py H9-5, test_ironman_borrow.py) -----
def stk(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:  # noqa: BLE001
        return [f"probe failed: {type(e).__name__}: {str(e)[:120]}"]

def top(gc):
    return (stk(gc) or [None])[-1]

def wait(pred, timeout, interval=0.25):
    t0 = time.time()
    while not pred():
        if time.time() - t0 >= timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)
    return True, round(time.time() - t0, 2)

def tbuttons(gc):
    r = gc.cmd({"cmd": "list_widgets"})
    return r.get("state") or "", [[w.get("text"), w.get("visible"), w.get("hidden")] for w in r.get("widgets", [])
                                  if "TextButton" in (w.get("type") or "")]

def settled(gc, name, timeout):
    def ok():  # `name` on top, every interactive widget hidden false (a Window popup hides them; a hidden button ignores input, F18080)
        r = gc.cmd({"cmd": "list_widgets"})
        ws = [w for w in r.get("widgets", []) if w.get("interactive")]
        return bool(name in (r.get("state") or "") and ws and all(w.get("hidden") is False for w in ws))
    return wait(ok, timeout, 0.1)

def battle(gc):
    b = gc.cmd({"cmd": "battle_state"}) if "BattlescapeState" in stk(gc) else {"skipped": "no BattlescapeState"}
    return {k: b.get(k) for k in ("skipped", "inBattle", "turn", "side", "isBusy", "pendingStates") if k in b}

def idle(gc):
    s, b = stk(gc), battle(gc)
    return (bool(s) and s[-1] == "BattlescapeState" and not any(("SaveGameState" in x or "CoopState" in x) for x in s)
            and not b.get("isBusy") and b.get("pendingStates") == 0 and (b.get("side"), b.get("turn")) == (0, 1))

def log_lines(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, "rb").read().decode("utf-8", errors="replace").splitlines() if os.path.exists(p) else []

def crash_set():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))

def capture(tag, err, *machines):
    cap = {}
    for gc in [g for g in machines if g is not None and g.proc is not None and g.proc.poll() is None]:
        try:
            cap[gc.name] = {"stack": stk(gc), "battle": battle(gc), "get_coop": gc.cmd({"cmd": "get_coop"}), "widgets": tbuttons(gc),
                            "coop_dialog_info": gc.cmd({"cmd": "coop_dialog_info"}), "logTail": log_lines(gc)[-30:]}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE {tag}: missed {err}; {json.dumps(cap, sort_keys=True, default=str)}", flush=True)

# ----- the start (H53 start / drive, copied: solo and SEPARATE co-op branches) -----
def start(host, client, mode, ironman, ev):
    host.ok({"cmd": "open_new_game", "mode": mode})
    host.wait_for("difficulty", lambda: PF._has(host, "NewGameState"))
    if not settled(host, "NewGameState", 10)[0]:
        raise Miss("START", "NewGameState widgets never settled")
    time.sleep(NGS_SETTLE)
    if ironman:
        ev["ironmanClick"] = host.cmd({"cmd": "click_widget", "match": "ironman"}).get("ok")
        time.sleep(0.3)
        ev["ironmanToggle"] = [(w.get("text"), w.get("visible")) for w in host.cmd({"cmd": "list_widgets"}).get("widgets", [])
                               if (w.get("text") or "").upper() == "IRONMAN"]
        if not ev["ironmanClick"] or not ev["ironmanToggle"]:
            raise Miss("START", f"IRONMAN click {ev['ironmanClick']} toggle {ev['ironmanToggle']}")
    host.ok({"cmd": "newgame_ok"})
    if mode == "solo":
        return {"host": "H67Base", "client": None, "begin": False}
    host.wait_for("host window", lambda: PF._has(host, "HostMenu"))
    host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": KEY, "player": "HostPlayer"})
    host.wait_for("host lobby", lambda: PF._has(host, "LobbyMenu"))
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    client.wait_for("client lobby", lambda: PF._has(client, "LobbyMenu"), timeout=120)
    for gc in (host, client):
        gc.wait_for("join popup", lambda gc=gc: PF._has(gc, "Profile"))
        gc.ok({"cmd": "profile_ok"})
    host.wait_for("start eligible", lambda: PF._lobby(host).get("startEligible") or None)
    host.wait_for("START CAMPAIGN shown", lambda: host.cmd({"cmd": "lobby_state"}).get("buttonVisible") or None, timeout=10)
    session.start_campaign_via_button(host)
    return {"host": "H67Base", "client": "H67Client", "begin": True}

def drive(host, client, ev, plan, name, quiet):
    t0, last, seen = time.time(), time.time(), {}
    rec = ev["drive"] = {"lists": [], "coop": [], "actions": []}
    placed, begun = {w: not plan[w] for w in ("host", "client")}, not plan["begin"]
    machines = [("host", host)] + ([("client", client)] if client else [])
    while time.time() - t0 < DRIVE_S:
        for who, gc in machines:
            s = stk(gc)
            if seen.get(who) != s:
                seen[who], last = s, time.time()
            t = s[-1] if s else ""
            if t == "BuildNewBaseState" and not placed[who]:
                for lon, lat in [(session.HOST_LON, session.HOST_LAT) if who == "host" else (LAND_LON, LAND_LAT), BASE_FALLBACK]:
                    r = gc.cmd({"cmd": "place_first_base", "lon": lon, "lat": lat, "name": plan[who]})
                    rec["actions"].append([who, "place", [round(lon, 3), round(lat, 3)], r.get("ok") or r.get("error")])
                    if r.get("ok"):
                        placed[who] = True
                        break
            elif t == "ListSaveState":
                n = len([x for x in rec["lists"] if x[0] == who]) + 1
                if n > 4:
                    raise Miss("START", f"{who}: a fifth ListSaveState")
                settled(gc, "ListSaveState", 5)
                cancel = next((v for x, v, _h in tbuttons(gc)[1] if (x or "").upper() == "CANCEL"), None)
                rec["lists"].append([who, n, round(time.time() - t0, 2), cancel, gc.cmd({"cmd": "list_save_confirm", "name": name}).get("ok")])
                last = time.time()
            elif t == "CoopState":
                d = gc.cmd({"cmd": "coop_dialog_info"})
                if [who, d.get("code")] not in [x[:2] for x in rec["coop"]]:
                    rec["coop"].append([who, d.get("code"), round(time.time() - t0, 2)])
        if not begun and top(host) == "CoopState":
            d = host.cmd({"cmd": "coop_dialog_info"})
            if d.get("code") in (60, 62) and d.get("backVisible") is True:
                rec["actions"].append(["host", f"BEGIN {d.get('code')}", host.cmd({"cmd": "coop_dialog_back"}).get("ok")])
                begun, last = True, time.time()
        if begun and all(placed.values()) and all(top(gc) == "GeoscapeState" for _w, gc in machines) and time.time() - last >= quiet:
            rec["done"] = round(time.time() - t0, 2)
            return {w: [x for x in rec["lists"] if x[0] == w] for w in ("host", "client")}
        time.sleep(0.1)
    raise Miss("START", f"start not over in {DRIVE_S} s: host {stk(host)}" + (f", client {stk(client)}" if client else ""))

def pause_read(gc, route):
    r = {"route": route, "stackBefore": stk(gc)}
    prev = r["stackBefore"][-1] if r["stackBefore"] else None
    if route == "geo":
        o = gc.cmd({"cmd": "click_widget", "match": "options"})
        if not o.get("ok") or o.get("text") != "OPTIONS":
            raise Miss("READ", f"click_widget options: {o}")
    else:
        gc.cmd({"cmd": "inject_input", "kind": "key", "key": ESC})
    ok, r["pauseS"] = wait(lambda: "PauseState" in (top(gc) or ""), PAUSE_S, 0.2)
    if not ok:
        raise Miss("READ", f"no PauseState {PAUSE_S} s after the {route} open ({stk(gc)})")
    ok, r["settleS"] = settled(gc, "PauseState", SETTLE_W)
    if not ok:
        raise Miss("READ", f"the PauseState widgets did not read hidden false in {SETTLE_W} s ({tbuttons(gc)})")
    state, tb = tbuttons(gc)
    r["stackAtRead"], r["buttons"] = stk(gc), {x: [v, h] for x, v, h in tb}
    if "BattlescapeState" in r["stackAtRead"]:
        r["battleAtRead"] = battle(gc)
    counts = {c: sum(1 for x, _v, _h in tb if x == c) for c in (LOAD, SAVE, "CANCEL")}
    counts["abandon"] = sum(1 for x, _v, _h in tb if x in (SAA, ABANDON))
    if "PauseState" not in state or any(n != 1 for n in counts.values()):
        raise Miss("READ", f"list_widgets on {state}: caption counts {counts} (want one each)")
    c = gc.cmd({"cmd": "click_widget", "match": "cancel"})
    ok, r["closeS"] = wait(lambda: top(gc) == prev, PAUSE_S, 0.2)
    r["stackAfter"], r["closedByCancel"] = stk(gc), bool(c.get("ok") and ok)
    return r

def vis(r, cap):
    return (r["buttons"].get(cap) or [None])[0]

def iron_cells(row, r, where):
    for cap in (LOAD, SAVE):
        v = vis(r, cap)
        cell(f"{row}-{cap.split()[0].lower()}", v is False,
             f"{cap + ' shows in an ironman game: ' if v else ''}{cap} visible {v} on the {where} pause menu (want False)")
    cell(f"{row}-abandon", vis(r, SAA) is True and ABANDON not in r["buttons"],
         f"{SAA!r} visible {vis(r, SAA)}, {ABANDON!r} caption present {ABANDON in r['buttons']} (want True, False)")

def to_battle(gc, ev):
    own = lambda: next((b for b in gc.ok({"cmd": "geo_state"})["bases"] if not b.get("coopBase") and not b.get("coopIcon")), {})  # noqa: E731
    sky = lambda: next((c for c in own().get("crafts", []) if "SKYRANGER" in c["type"]), {})  # noqa: E731
    rb = next((b for b in gc.ok({"cmd": "get_soldiers"})["bases"] if not b["coopBaseFlag"] and not b.get("coopIcon") and b["soldiers"]), {})
    cid, ids = sky().get("id"), sorted(s["id"] for s in rb.get("soldiers", []))
    for sid in ids:
        gc.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False, "base": rb["name"]})
    seats = [[sid, gc.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True, "base": rb["name"]}).get("seated")]
             for sid in ids[:3]]
    ev["seat"] = {"base": rb.get("name"), "craft": cid, "seats": seats}
    if cid is None or len(seats) != 3 or not all(x[1] for x in seats):
        raise Miss("SEAT", f"own roster base, Skyranger, the 3 lowest ids seated: {ev['seat']}")
    b0 = own()
    site = gc.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION", "lon": b0["lon"] + 0.35,
                  "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})["site_id"]
    if not wait(lambda: any(x["id"] == site and not x.get("coop") for x in gc.ok({"cmd": "geo_state"})["missionSites"]), 30, 0.5)[0]:
        raise Miss("SITE", f"site {site} not listed in 30 s")
    gc.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT", "lon": b0["lon"] + 0.34, "lat": b0["lat"] + 0.10,
           "dest": "site:%d" % site, "fuel": 999999, "lowFuel": False})
    sk = sky()
    ev["site"] = {"id": site, "base": [b0["lon"], b0["lat"]], "craft": {k: sk.get(k) for k in ("id", "status", "destKind", "destId")}}
    if (sk.get("status"), sk.get("destKind"), sk.get("destId")) != ("STR_OUT", "site", site):
        raise Miss("SITE", f"craft not OUT to site {site}: {ev['site']}")
    t0, drained = time.time(), ev.setdefault("drained", [])
    while "ConfirmLandingState" not in (top(gc) or "") and time.time() - t0 < ARRIVAL_S:
        t = top(gc) or ""
        if "CraftErrorState" in t:
            raise Miss("ARRIVAL", f"CraftErrorState ({stk(gc)})")
        if "GeoscapeState" not in t:
            drained.append([t, gc.cmd({"cmd": "coop_dialog_back"} if "CoopState" in t else
                                      {"cmd": "dismiss_popup", "keep": ["ConfirmLandingState", "CraftErrorState"]}).get("ok")])
        gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        time.sleep(0.5)
    if "ConfirmLandingState" not in (top(gc) or ""):
        raise Miss("ARRIVAL", f"no ConfirmLandingState in {ARRIVAL_S} s ({stk(gc)[-3:]})")
    ev["arrivalS"] = round(time.time() - t0, 2)
    gc.ok({"cmd": "confirm_landing"})
    if not wait(lambda: top(gc) == "BriefingState", ENTRY_S)[0] or not settled(gc, "BriefingState", 10)[0]:
        raise Miss("BRIEFING", f"no settled BriefingState {ENTRY_S} s after confirm_landing ({stk(gc)})")
    n0 = len(log_lines(gc))
    if gc.cmd({"cmd": "click_widget", "match": "ok"}).get("text") != "OK":
        raise Miss("BRIEFING", f"briefing OK click refused ({stk(gc)})")
    t0, hist, acts, done = time.time(), [], [], set()
    while time.time() - t0 < SETTLE_S:
        s = stk(gc)
        if not hist or hist[-1][1] != s:
            hist.append([round(time.time() - t0, 2), s])
        t = s[-1] if s else ""
        if t in ("InventoryState", "NextTurnState") and (t, len(hist)) not in done:   # the equip screen's OK is ESC (F19940)
            done.add((t, len(hist)))
            r = gc.cmd({"cmd": "inject_input", "kind": "key", "key": ESC} if t == "InventoryState" else {"cmd": "close_nextturn"})
            acts.append([t, r.get("ok"), round(time.time() - t0, 2)])
        elif idle(gc):
            break
        time.sleep(0.25)
    ev["battleStart"], ev["battleStartActions"] = hist, acts
    ev["battleStartLog"] = [x.split("\t")[-1].replace("class OpenXcom::", "")[:50] for x in log_lines(gc)[n0:] if "[coop-ui] p" in x]
    if not idle(gc):
        raise Miss("BATTLE", f"not idle at turn 1 side 0 in {SETTLE_S} s: {stk(gc)} {battle(gc)}")
    ev["idleS"] = round(time.time() - t0, 2)

def row(name, gc, ev, fn):
    try:
        fn()
        finish_row(name, ev)
    except Exception as e:  # noqa: BLE001 - a precondition miss (Miss) or an error: ONE CAPTURE line, the unreached cells "not reached"
        step, why = (e.step, e.why) if isinstance(e, Miss) else ("raised", f"{type(e).__name__}: {str(e)[:300]}")
        capture(name, why, gc)
        finish_row(name, ev, f"not reached ({step}: {why[:160]})")

def boot_i(x, evs):
    sp = x["sp"]
    ls = drive(sp, None, evs["G"], start(sp, None, "solo", True, evs["G"]), NAME_I, QUIET_SOLO)["host"]
    if len(ls) != 2 or any(c is not False for _w, _n, _t, c, _ok in ls):
        raise Miss("boot", f"start save lists {ls} (want 2, Cancel visible false on each)")

    def g():
        iron_cells("G", evs["G"].setdefault("read", pause_read(sp, "geo")), "geoscape")
    def b():
        to_battle(sp, evs["B"])
        iron_cells("B", evs["B"].setdefault("read", pause_read(sp, "battle")), "battle")
    row("G", sp, evs["G"], g)
    if "PauseState" in (top(sp) or ""):
        sp.cmd({"cmd": "click_widget", "match": "cancel"})
    row("B", sp, evs["B"], b)

def boot_n(x, evs):
    sp = x["sp"]
    ls = drive(sp, None, evs["N"], start(sp, None, "solo", False, evs["N"]), NAME_N, QUIET_SOLO)["host"]
    if ls:
        raise Miss("boot", f"start save lists {ls} in a non-ironman game (want 0)")

    def n():
        r = evs["N"]["read"] = pause_read(sp, "geo")
        for cap in (LOAD, SAVE):
            cell(f"N-{cap.split()[0].lower()}", vis(r, cap) is True, f"{cap} visible {vis(r, cap)} in a non-ironman solo game (want True)")
        cell("N-abandon", vis(r, ABANDON) is True and SAA not in r["buttons"],
             f"{ABANDON!r} visible {vis(r, ABANDON)}, {SAA!r} caption present {SAA in r['buttons']} (want True, False)")
    row("N", sp, evs["N"], n)

def boot_c(x, evs):
    host, client = x["host"], x["client"]
    ls = drive(host, client, evs["C"], start(host, client, "coop", True, evs["C"]), NAME_C, QUIET_COOP)
    if len(ls["host"]) != 2 or ls["client"]:
        raise Miss("boot", f"start save lists host {ls['host']}, client {ls['client']} (want 2, 0)")

    def c():
        rh = evs["C"]["host"] = pause_read(host, "geo")
        cell("C-host", (vis(rh, LOAD), vis(rh, SAVE), vis(rh, SAA)) == (False, False, True),
             f"host LOAD {vis(rh, LOAD)}, SAVE {vis(rh, SAVE)}, {SAA!r} {vis(rh, SAA)} (want False, False, True)")
        rc = evs["C"]["client"] = pause_read(client, "geo")
        cell("C-client", (vis(rc, LOAD), vis(rc, SAVE)) == (False, False),
             f"client LOAD {vis(rc, LOAD)}, SAVE {vis(rc, SAVE)} (want False, False); abandon caption EVIDENCE")
    row("C", host, evs["C"], c)

def run_boot(tag, fn):
    t0 = time.time()
    dirs = {"I": {"sp": "w2h67_i_sp"}, "N": {"sp": "w2h67_n_sp"}, "C": {"host": "w2h67_c_host", "client": "w2h67_c_client"}}[tag]
    x, evs = {nm: GameClient(nm, None, make_user_dir(d)) for nm, d in dirs.items()}, {r: {} for r in BOOTS[tag]}
    try:
        for gc in x.values():
            gc.spawn(); gc.connect()
        fn(x, evs)
    except Exception as e:  # noqa: BLE001 - a boot miss (the start or its precondition) or an error before the rows
        err = e.why if isinstance(e, Miss) else f"{type(e).__name__}: {str(e)[:300]}"
        capture(f"boot {tag}", err, *x.values())
        for r in [r for r in BOOTS[tag] if not any(n in RESULTS for n in ROWS[r])]:
            finish_row(r, evs[r], f"boot ({err[:160]})")
    finally:
        for gc in [g for g in list(x.values())[::-1] if g.proc is not None]:
            try:
                gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)
    return round(time.time() - t0, 1)

def main():
    t0, crash0, walls = time.time(), crash_set(), {}
    for tag, fn in (("I", boot_i), ("N", boot_n), ("C", boot_c)):
        walls[tag] = run_boot(tag, fn)
    new = sorted(crash_set() - crash0)
    cell("X-crash", not new, f"new crash files {new} in {harness.CRASH_DIR} (want none)")
    finish_row("X", {"crashDir": harness.CRASH_DIR, "new": new, "bootWalls": walls})
    allc = [c for v in ROWS.values() for c in v]
    fails = [n for n in allc if not RESULTS.get(n, (False,))[0]]
    print(f"\n==== W2-H67 solo ironman pause menu: {len(allc) - len(fails)}/{len(allc)} cells PASS, wall {time.time() - t0:.1f} s "
          f"(boots {walls}) ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (expected red)' if n in RED else ''}", flush=True)
    sys.exit(0 if not fails else 2)

if __name__ == "__main__":
    main()
