"""test_ironman_borrow.py: an ironman alien host keeps its ironman rules in a gm3 borrowed battle (lead L-SC5-4).

In a gm3 PvP campaign the host plays the aliens and borrows the X-COM player's world for every battle. R-H49-0 = O1 (vanilla's ironman
rules; aud-E1-05 "ironman is host-only"): while it borrows, an ironman alien host follows its own (parked) world's ironman rules: the
battle-start autosave rewrites IronAlien.sav, the pause menu has no SAVE and reads SAVE AND ABANDON GAME (X-COM turn only, QH49-5 (a)),
F6 / F5 write nothing, after the battle the campaign keeps its name. A non-ironman host and the X-COM client behave as today (boot N,
C5). Real inputs: ESC and the pause menu's own buttons, F6 / F5 by inject_input, kills + END TURN + both debriefing OKs.
Spec: docs rewrite/prompts/w2h49_ironman_borrow.md ((f); QH49-1 .. QH49-8 (a)); pins: docs rewrite/w2h49-task0/sa/CONSTANTS.md. Boot A
(the ironman SAVE AND ABANDON) is OUT by QH49-6 (a): TASK 0's green premise failed (no IronAlien.sav write after YES; lead L-H49-3,
F17782). Findings F17600-F17609 (capture), F17640-F17659 (spec), F17780-F17799.
Boot I (key 49143, dirs w2h49_i_*; ironman; host = the aliens), rows: C0 = I-c0 (control); N1 = N1-file, N1-only, N1-borrow (control);
N2 = N2-x, N2-client (control), N2-a; N3 = N3-f6, N3-f5; N4 = N4-file, N4-only, N4-pause (control), N4-home (control); I-common.
Boot N (key 49143, dirs w2h49_n_*; no IRONMAN click): row C5 = N-c0, N-start, N-pause, N-f5, N-after, N-common.
RED (the unchanged build, TASK 0 boot i): N1-file, N1-only, N2-x, N2-a, N3-f6, N3-f5, N4-file, N4-only (8 of 20). GREEN (G1): 20/20.
A bring-up / landing / side change / battle-end miss: ONE "CAPTURE <boot>:" line (BR's stage_to_prompt prints its own "CAPTURE boot:")
and every remaining cell of that boot FAILs "boot". A row precondition miss (host never idle) FAILs its cells "blocked: <why>".
ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_ironman_borrow.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import geo  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import repro_atom_side_begin as RSB  # noqa: E402
import test_battle_end_separate as BES  # noqa: E402
import test_campaign_battle_gm2 as G2F  # noqa: E402
import test_campaign_battle_gm3 as G3C1  # noqa: E402
import test_campaign_battle_gm3_end as G3E  # noqa: E402
import test_campaign_battle_resume as BR  # noqa: E402
import test_campaign_resume_roles as RR  # noqa: E402

# ----- TASK 0 pins (docs rewrite/w2h49-task0/sa/CONSTANTS.md) -----
KEY = "49143"
NAME = "IronAlien"                    # every ListSaveState answered with it (TASK 0: 2 in every ironman boot; F17601, L-H49-1)
SEED = 1                              # the client's set_seed before its confirm_landing (CAP)
ESC, F5, F6 = 27, 286, 287            # Options keyQuickSave / keyInstaSave (the host's options.cfg reads 286 / 287)
NGS_SETTLE = 0.2
SAVE_AND_ABANDON, ABANDON = "SAVE AND ABANDON GAME", "ABANDON GAME"
GEO_S, LIST_S, ENTRY_S, SETTLE_S, FILE_S, KEY_S, PAUSE_S, SIDE_S, DEBRIEF_S, GEO_BACK_S = 15, 120, 60, 30, 10, 5, 10, 60, 60, 60
ROWS_I = {"C0": ["I-c0"], "N1": ["N1-file", "N1-only", "N1-borrow"], "N2": ["N2-x", "N2-client", "N2-a"], "N3": ["N3-f6", "N3-f5"],
          "N4": ["N4-file", "N4-only", "N4-pause", "N4-home"], "I-common": ["I-common"]}
ROWS_N = {"C5": ["N-c0", "N-start", "N-pause", "N-f5", "N-after", "N-common"]}
FIX = {"N1-file", "N1-only", "N2-x", "N2-a", "N3-f6", "N3-f5", "N4-file", "N4-only"}
BOOT = {"tag": "I"}


class FixtureMiss(Exception):
    pass


RESULTS = []          # (cell, ok, detail)
PRINTED = set()       # rows whose EVIDENCE / ROW lines are out


def cell(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)


def block(names, why):
    for n in names:
        if n not in {x[0] for x in RESULTS}:
            cell(n, False, f"blocked: {why}")


def close_row(row, names, obj):
    print(f"EVIDENCE {row}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)
    bad = [n for n, ok, _ in RESULTS if n in names and not ok]
    print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)
    PRINTED.add(row)


def capture_boot(err, *machines):
    print(f"CAPTURE {BOOT['tag']}: {json.dumps(RR.capture(err, *machines), sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


# ----- CAP's flow helpers (docs rewrite/lsc5-4-cap/lsc54.py, copied) -----
def stk(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:  # noqa: BLE001
        return [f"probe failed: {type(e).__name__}: {str(e)[:120]}"]


def top(gc):
    return (stk(gc) or [None])[-1]


wait = BES.wait_until   # (pred, timeout, interval=0.25) -> (ok, seconds)


def files(gc, data=False):
    """the save files under the user dir: .sav / .asav (data=True: the .data files, EVIDENCE only) -> {name: {rel, size, mtime}}."""
    out = {}
    for rel in session.save_files(gc.user_dir):
        if rel.lower().endswith(".data") == data:
            st = os.stat(os.path.join(gc.user_dir, rel))
            out[os.path.basename(rel)] = {"rel": rel, "size": st.st_size, "mtime": round(st.st_mtime, 3)}
    return out


def diff(gc, before):
    return [f for f, v in files(gc).items() if f not in before or (before[f]["mtime"], before[f]["size"]) != (v["mtime"], v["size"])]


def header(gc, rel):
    h, _body, _blobs = BR.read_save(os.path.join(gc.user_dir, rel))
    b = h.get("coopPvpBorrowed")
    return {"name": h.get("name"), "ironman": h.get("ironman"), "ironmanKey": "ironman" in h, "borrow": "coopPvpBorrowed" in h,
            "kind": b.get("kind") if isinstance(b, dict) else None, "turn": h.get("turn")}


def changed(gc, before):
    """{file: header + new} for every save file new or changed since `before`."""
    fs = files(gc)
    return {f: dict(header(gc, fs[f]["rel"]), new=f not in before) for f in diff(gc, before)}


def settled(gc, name, timeout):
    def ok():
        r = gc.cmd({"cmd": "list_widgets"})
        ws = [w for w in r.get("widgets", []) if w.get("interactive")]
        return bool(name in (r.get("state") or "") and ws and all(w.get("hidden") is False for w in ws))
    return wait(ok, timeout, 0.1)[0]


def battle(gc):
    return {k: v for k, v in battle_state(gc).items() if k in ("inBattle", "turn", "side", "isBusy", "pendingStates")}


def pvp_short(gc):
    return {k: v for k, v in (gc.cmd({"cmd": "get_coop"}).get("pvpBorrow") or {}).items() if k in ("active", "savedBorrowed", "swappedBack", "kind")}


def idle(gc):
    s, b = stk(gc), battle(gc)
    return (s and s[-1] == "BattlescapeState" and not any(("SaveGameState" in x or "CoopState" in x) for x in s)
            and not b.get("isBusy") and b.get("pendingStates") == 0)


def pause_probe(gc):
    """ESC; PauseState on top in PAUSE_S, its widgets settled; every TextButton's text -> visible; CANCEL. None = no PauseState."""
    gc.cmd({"cmd": "inject_input", "kind": "key", "key": ESC})
    if not wait(lambda: "PauseState" in (top(gc) or ""), PAUSE_S, 0.2)[0]:
        return None
    settled(gc, "PauseState", 5)
    btn = {w.get("text"): w.get("visible") for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", []) if "TextButton" in (w.get("type") or "")}
    gc.cmd({"cmd": "click_widget", "match": "cancel"})
    wait(lambda: "PauseState" not in (top(gc) or ""), PAUSE_S, 0.2)
    return btn


def pause_bad(btn, load, save, text, vis):
    """the probe against LOAD / SAVE visibility (None = not checked) and the abandon button's text and visibility."""
    if btn is None:
        return [f"no PauseState in {PAUSE_S} s after ESC"]
    t, v = next(((t, v) for t, v in btn.items() if "ABANDON" in (t or "").upper()), (None, None))
    bad = [f"{k} visible {btn.get(k)} (want {w})" for k, w in (("LOAD GAME", load), ("SAVE GAME", save)) if w is not None and btn.get(k) != w]
    return bad + ([f"abandon text {t!r} (want {text!r})"] if t != text else []) + ([f"abandon visible {v} (want {vis})"] if v != vis else [])


# ----- the boot flow (CAP's start_campaign / c0_save / c1 / the C3 key / c4, copied with IB's KEY) -----
def start_campaign(host, client, ev, ironman):
    host.ok({"cmd": "open_new_game", "mode": "coop"})
    host.wait_for("difficulty", lambda: PF._has(host, "NewGameState"))
    if ironman:
        if not settled(host, "NewGameState", 10):
            capture_boot("NewGameState widgets never settled", host, client)
        time.sleep(NGS_SETTLE)
        ev["ironmanClick"] = host.cmd({"cmd": "click_widget", "match": "ironman"}).get("ok")
        time.sleep(0.3)
        ev["ironmanToggle"] = [(w.get("text"), w.get("visible")) for w in host.cmd({"cmd": "list_widgets"}).get("widgets", [])
                               if "IRONMAN" in (w.get("text") or "").upper()]
        if not ev["ironmanClick"] or not ev["ironmanToggle"]:
            capture_boot(f"IRONMAN click {ev['ironmanClick']} toggle {ev['ironmanToggle']}", host, client)
    host.ok({"cmd": "newgame_ok"})
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
    ev["gamemode"] = host.ok({"cmd": "lobby_set_team", "row": PF.row_for(host, "HostPlayer"), "team": "Alien"}).get("gamemode")
    session.start_campaign_via_button(host)
    client.wait_for("XCOM base placement screen", lambda: PF._has(client, "BuildNewBaseState") or None, timeout=60)
    if not client.ok({"cmd": "place_first_base", "lon": LAND_LON, "lat": LAND_LAT, "name": "XcomBase"}).get("ok"):
        client.ok({"cmd": "place_first_base", "lon": 0.706, "lat": -0.507, "name": "XcomBase"})
    session.press_back_when_shown(host, "host BEGIN", codes=(60, 62))
    tb, seen = time.time(), []

    def host_ready():
        s = stk(host)
        seen.append(s[-1] if s else None)
        return s and (s[-1] == "ListSaveState" or (s[-1] == "GeoscapeState" and time.time() - tb >= GEO_S))
    ok, _ = wait(host_ready, LIST_S, 0.1)
    ev["listSaveSeen"] = "ListSaveState" in seen
    if not ok or not wait(lambda: top(client) == "GeoscapeState", 120)[0]:
        capture_boot(f"after BEGIN: host {stk(host)}, client {stk(client)}", host, client)
    if ironman:
        if top(host) != "ListSaveState":
            capture_boot(f"no host ListSaveState after BEGIN ({stk(host)})", host, client)
        host.cmd({"cmd": "list_save_confirm", "name": NAME})
        n, t0 = [1], time.time()

        def geo_top():
            s = stk(host)
            if s and s[-1] == "ListSaveState" and time.time() - t0 > 0.2 and n[0] < 2:
                settled(host, "ListSaveState", 5)
                host.cmd({"cmd": "list_save_confirm", "name": NAME})
                n[0] += 1
            return s and s[-1] == "GeoscapeState"
        ok, _ = wait(geo_top, 60, 0.1)
        ev["listSaveCount"] = n[0]
        if not ok:
            capture_boot(f"no host GeoscapeState after list_save_confirm ({stk(host)})", host, client)
        time.sleep(1.0)
    geo.slow_clock(host, client)


def land(host, client, ev):
    """BR stage_to_prompt; client set_seed + confirm_landing; briefings; equip; host NTS OK -> host (1, 0), no Save / CoopState."""
    xb = next((b for b in client.ok({"cmd": "geo_state"}).get("bases", []) if not b.get("coopBase") and not b.get("coopIcon")), None)
    sky = next((cr for cr in (xb or {}).get("crafts", []) if "SKYRANGER" in cr.get("type", "") and not cr.get("coop")), None)
    if not sky:
        capture_boot(f"no client Skyranger ({xb and xb.get('name')})", host, client)
    try:
        BR.stage_to_prompt(host, client, xb, {"sky": {"type": sky.get("type"), "id": sky.get("id")}}, ev)
    except BR.FixtureMiss as e:
        raise FixtureMiss(f"BR.stage_to_prompt: {e}")
    client.cmd({"cmd": "set_seed", "seed": SEED})
    client.cmd({"cmd": "confirm_landing"})
    if not wait(lambda: G3C1.in_battle(host) and G3C1.in_battle(client), ENTRY_S)[0]:
        capture_boot(f"not both inBattle {ENTRY_S} s after the confirm", host, client)
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=60)
    client.wait_for("client briefing", lambda: session.has_state(client, "BriefingState") or None, timeout=90)
    host.ok({"cmd": "click_widget", "match": "ok"})
    session.dismiss_client_briefing(client)
    session.equip_both_ready(host, client)
    t0 = time.time()
    while time.time() - t0 < SETTLE_S:
        s, b = stk(host), battle(host)
        if s and s[-1] == "NextTurnState":
            BES.close_host_nextturn(host)
        elif (s and s[-1] == "BattlescapeState" and (b.get("turn"), b.get("side")) == (1, 0)
              and not any(("SaveGameState" in x or "CoopState" in x) for x in s)):
            break
        time.sleep(0.5)
    else:
        capture_boot(f"host never settled at (1, 0): {stk(host)} {battle(host)}", host, client)
    session.dismiss_battle_start_overlays(client)
    time.sleep(1.0)


def side_change(host, client, side, turn_min=None):
    try:
        RSB.drive_side_change(host, client, side, want_turn_min=turn_min, timeout=SIDE_S)
    except TimeoutError as x:
        capture_boot(f"side change to side {side}: {x}", host, client)


def key_probe(host, key):
    """a real key on the idle host; the stack sampled for KEY_S; then the save files new or changed and savedBorrowed."""
    p0, before = pvp_short(host).get("savedBorrowed"), files(host)
    host.cmd({"cmd": "inject_input", "kind": "key", "key": key})
    t0, seen = time.time(), set()
    while time.time() - t0 < KEY_S:
        seen.update(stk(host))
        time.sleep(0.25)
    ch, p1 = changed(host, before), pvp_short(host).get("savedBorrowed")
    bad = ([f"save files new or changed {ch}"] if ch else []) + (["SaveGameState on the host stack"] if "SaveGameState" in seen else [])
    bad += [f"savedBorrowed {p0} -> {p1}"] if p0 != p1 else []
    return bad, {"changed": ch, "savedBorrowed": [p0, p1], "statesSeen": sorted(seen)}


def battle_end(host, client, ev):
    """kills, END TURN, both debriefing OKs (client first), host GeoscapeState; then the post-battle save (any file change in FILE_S)."""
    before = files(host)
    G2F.kill_all(host, client, 1, ev, "kills")
    if "DebriefingState" not in stk(host):
        client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        BES.close_host_nextturn(host)
    if not wait(lambda: "DebriefingState" in stk(host), DEBRIEF_S)[0]:
        capture_boot("no host DebriefingState after the kills", host, client)
    wait(lambda: (lambda d: d.get("shown") is True and d.get("displayOnly") is True)(G3E.deb(client)), 20)
    ev["titles"] = [G3E.deb(host).get("title"), G3E.deb(client).get("title")]
    wait(lambda: (BES.record(client).get("worldAdopted") or 0) >= 1, 30)
    BES.press_ok(client)
    BES.drain(client, timeout=10)
    wait(lambda: BES.geo_clean(client), 10)
    BES.press_ok(host)
    t0, screens = time.time(), ev.setdefault("hostScreens", [])
    while (top(host) or "") != "GeoscapeState":
        t = top(host) or ""
        if time.time() - t0 > GEO_BACK_S:
            capture_boot(f"no host GeoscapeState {GEO_BACK_S} s after its debriefing OK ({stk(host)})", host, client)
        if "CoopState" in t:
            screens.append([host.cmd({"cmd": "coop_dialog_info"}).get("code"), host.cmd({"cmd": "coop_dialog_back"}).get("ok")])
        elif not any(n in t for n in BES.WAIT_TOPS) and t != "ListSaveState":
            screens.append([t, host.cmd({"cmd": "dismiss_popup"}).get("handled")])
        time.sleep(0.3)
    wait(lambda: BES.geo_clean(host), 30)
    ev["postSaveS"] = wait(lambda: bool(diff(host, before)), FILE_S)[1]
    time.sleep(1.0)


def common(name, host, client, crash0):
    cf, nc = files(client), sorted(RR.crash_set() - crash0)
    cell(name, not cf and not nc, f"client save files {sorted(cf)}, client .data {sorted(files(client, True))}, new crash files {nc}")


def fits(h, want):
    return h is not None and all(h.get(k) == v for k, v in want.items())


# ----- boot I -----
def boot_i(host, client, ev):
    crash0 = RR.crash_set()
    e = ev["C0"] = {}
    start_campaign(host, client, e, True)
    co, g, f0 = G3E.coop(host), pause_probe(host), files(host)
    hd = header(host, f0[NAME + ".sav"]["rel"]) if NAME + ".sav" in f0 else None
    bad = [] if fits(hd, {"name": NAME, "ironman": True, "borrow": False}) else [f"{NAME}.sav header {hd}"]
    bad += pause_bad(g, False, False, SAVE_AND_ABANDON, True)
    bad += [f"host gamemode {co.get('gamemode')} noBases {co.get('noBases')}"] if (co.get("gamemode"), co.get("noBases")) != (3, True) else []
    e.update(header=hd, geoPause=g, files=f0, data=files(host, True), coop=co)
    cell("I-c0", not bad, "; ".join(bad) or f"{NAME}.sav {hd}; geoscape pause LOAD / SAVE hidden, {SAVE_AND_ABANDON!r} shown; gm 3, noBases")
    close_row("C0", ROWS_I["C0"], e)
    e = ev["N1"] = {}
    land(host, client, e)
    ch, p = changed(host, f0), pvp_short(host)
    want = {"name": NAME, "ironman": True, "borrow": True, "kind": "landing", "turn": 1}
    cell("N1-file", fits(ch.get(NAME + ".sav"), want), f"{NAME}.sav since C0: {ch.get(NAME + '.sav')} (want rewritten, {want})")
    cell("N1-only", set(ch) <= {NAME + ".sav"}, f"save files new or changed since C0: {sorted(ch)} (want none but {NAME}.sav)")
    cell("N1-borrow", (p.get("active"), p.get("savedBorrowed")) == (True, 1), f"pvpBorrow {p} (want active, savedBorrowed 1)")
    f1 = files(host)
    e.update(changed=ch, pvp=p, stacks=[stk(host), stk(client)], battle=[battle(host), battle(client)])
    close_row("N1", ROWS_I["N1"], e)
    e = ev["N2"] = {}
    if not wait(lambda: idle(host), SETTLE_S)[0]:
        block(ROWS_I["N2"], f"host never idle at (1, 0): {stk(host)} {battle(host)}")
    else:
        e["host10"] = b = pause_probe(host)
        bad = pause_bad(b, False, False, SAVE_AND_ABANDON, True)
        cell("N2-x", not bad, "; ".join(bad) or f"host (1, 0): LOAD / SAVE hidden, {SAVE_AND_ABANDON!r} shown")
        e["clientIdle"] = wait(lambda: idle(client), SETTLE_S)
        e["client10"] = b = pause_probe(client)
        bad = pause_bad(b, False, False, ABANDON, True)
        cell("N2-client", not bad, "; ".join(bad) or f"client (1, 0): LOAD / SAVE hidden, {ABANDON!r} shown")
        client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        side_change(host, client, 1)
        e["at11"] = battle(host)
        if not wait(lambda: idle(host), SETTLE_S)[0]:
            block(["N2-a"], f"host never idle at (1, 1): {stk(host)}")
        else:
            e["host11"] = b = pause_probe(host)
            bad = pause_bad(b, None, False, SAVE_AND_ABANDON, False)
            cell("N2-a", not bad, "; ".join(bad) or f"host (1, 1): SAVE hidden, {SAVE_AND_ABANDON!r} hidden")
    close_row("N2", ROWS_I["N2"], e)
    e = ev["N3"] = {}
    host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    side_change(host, client, 0, 2)
    e["at"] = battle(host)
    for name, key in (("N3-f6", F6), ("N3-f5", F5)):
        if not wait(lambda: idle(host), SETTLE_S)[0]:
            block(ROWS_I["N3"], f"host never idle at (2, 0) before {name}: {stk(host)}")
            break
        bad, e[name] = key_probe(host, key)
        cell(name, not bad, "; ".join(bad) or f"key {key}: no save file, no SaveGameState, savedBorrowed unchanged")
    close_row("N3", ROWS_I["N3"], e)
    e = ev["N4"] = {}
    battle_end(host, client, e)
    ch1, ch0, p = changed(host, f1), changed(host, f0), pvp_short(host)
    want = {"name": NAME, "ironman": True, "borrow": False}
    cell("N4-file", fits(ch1.get(NAME + ".sav"), want), f"{NAME}.sav since N1: {ch1.get(NAME + '.sav')} (want rewritten, {want})")
    cell("N4-only", set(ch0) == {NAME + ".sav"}, f"save files new or changed since C0: {sorted(ch0)} (want exactly {NAME}.sav)")
    e["geoPause"] = g = pause_probe(host)
    bad = pause_bad(g, False, False, SAVE_AND_ABANDON, True)
    cell("N4-pause", not bad, "; ".join(bad) or f"geoscape pause LOAD / SAVE hidden, {SAVE_AND_ABANDON!r} shown")
    cell("N4-home", (p.get("swappedBack"), p.get("active")) == (1, False), f"pvpBorrow {p} (want swappedBack 1, active false)")
    e.update(changedSinceN1=ch1, changedSinceC0=ch0, pvp=p, files=files(host), data=files(host, True))
    close_row("N4", ROWS_I["N4"], e)
    common("I-common", host, client, crash0)


# ----- boot N (the C5 control: every cell passes today and after G1) -----
def boot_n(host, client, ev):
    crash0 = RR.crash_set()
    e = ev["C5"] = {}
    start_campaign(host, client, e, False)
    e["geoPause"] = g = pause_probe(host)
    bad = ["a host ListSaveState after BEGIN"] if e.get("listSaveSeen") else []
    bad += pause_bad(g, None, True, ABANDON, True)
    cell("N-c0", not bad, "; ".join(bad) or f"no ListSaveState in {GEO_S} s; geoscape pause SAVE shown, {ABANDON!r} shown")
    f0 = files(host)
    land(host, client, e)
    e["start"] = ch = changed(host, f0)
    want = {"name": "_autobattle_.asav", "ironmanKey": False, "borrow": True, "turn": 1}
    cell("N-start", fits(ch.get("_autobattle_.asav"), want) and set(ch) == {"_autobattle_.asav"},
         f"save files new or changed since C0: {ch} (want only _autobattle_.asav, {want})")
    if not wait(lambda: idle(host), SETTLE_S)[0]:
        block(["N-pause", "N-f5"], f"host never idle at (1, 0): {stk(host)}")
    else:
        e["host10"] = b = pause_probe(host)
        bad = pause_bad(b, None, True, ABANDON, True)
        cell("N-pause", not bad, "; ".join(bad) or f"host (1, 0): SAVE shown, {ABANDON!r} shown")
        wait(lambda: idle(host), SETTLE_S)
        _bad, e["f5"] = key_probe(host, F5)
        q, sb = e["f5"]["changed"].get("_quick_.asav"), e["f5"]["savedBorrowed"]
        want = {"name": "_quick_.asav", "ironmanKey": False, "borrow": True, "turn": 1}
        ok = fits(q, want) and sb[0] is not None and sb[1] == sb[0] + 1
        cell("N-f5", ok, f"F5: _quick_.asav {q}, savedBorrowed {sb} (want {want}, +1)")
    f1 = files(host)
    battle_end(host, client, e)
    e["after"] = ch = changed(host, f1)
    e["geoPauseAfter"] = g = pause_probe(host)
    bad = [] if fits(ch.get("_autogeo_.asav"), {"name": "_autogeo_.asav", "borrow": False}) else [f"_autogeo_.asav in {ch}"]
    bad += pause_bad(g, None, True, ABANDON, True)
    cell("N-after", not bad, "; ".join(bad) or f"_autogeo_.asav rewritten (no borrow record); geoscape pause SAVE shown, {ABANDON!r} shown")
    e.update(files=files(host), data=files(host, True), pvp=pvp_short(host))
    common("N-common", host, client, crash0)


def run_boot(tag, label, fn, rows):
    BOOT["tag"] = label
    x = {"host": GameClient("host", None, make_user_dir(tag + "_host")), "client": GameClient("client", None, make_user_dir(tag + "_client"))}
    ev, t0 = {}, time.time()
    allc = [c for v in rows.values() for c in v]
    try:
        x["host"].spawn(); x["host"].connect(); x["client"].spawn(); x["client"].connect()
        fn(x["host"], x["client"], ev)
    except FixtureMiss as e:
        block(allc, f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"[ERROR] boot {label}: {err}", flush=True)
        try:
            capture_boot(err, x["host"], x["client"])
        except Exception:  # noqa: BLE001 - FixtureMiss, or a probe of a dead machine
            pass
        block(allc, f"boot (error {err[:200]})")
    finally:
        for r, cs in rows.items():
            if r not in PRINTED:
                close_row(r, cs, dict(ev.get(r) or {}, bootWall=round(time.time() - t0, 1)))
        for gc in (x["client"], x["host"]):
            try:
                if gc.proc is not None:
                    gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)


def main():
    t0 = time.time()
    run_boot("w2h49_i", "I", boot_i, ROWS_I)
    run_boot("w2h49_n", "N", boot_n, ROWS_N)
    allc = [c for rows in (ROWS_I, ROWS_N) for v in rows.values() for c in v]
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== W2-H49 ironman alien host in a gm3 borrowed battle: {len(RESULTS) - len(fails)}/{len(allc)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (FIX cell)' if n in FIX else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(allc) else 2)


if __name__ == "__main__":
    main()
