"""W2-H53 - test_ironman_save_paths.py: co-op ironman save paths (leads L-H49-1, L-H49-2, L-H49-3).

R-H53-0 (O1 for L-H49-1 and L-H49-2, L-H49-3 in scope), R-H49-0 = O1 (ironman holds for the save's owner; one campaign file),
aud-E1-05 (ironman is host-only; the client never saves): a new SHARED ironman campaign asks the host for a save name twice, as solo and
every other mode (vanilla's two prompts kept), and never asks the second player (no code-123 "desync problems" popup); a named ironman
campaign's wait-dialog SAVE & QUIT saves the campaign's own file and goes to the main menu (no free-name list); an ironman alien host's
SAVE AND ABANDON GAME in a gm3 borrowed battle saves its campaign file (with the battle) before the session ends.
Spec: docs rewrite/prompts/w2h53_ironman_save_paths.md ((f); QH53-1 .. QH53-7 (a)); pins: docs rewrite/w2h53-task0/sa/CONSTANTS.md.
Findings F17980-F17993 (spec), F17860-F17869 (capture), F17782 (W2-H49), F18080-F18099 (TASK 0).
Real inputs only: the IRONMAN toggle, every save list answered by list_save_confirm, the 62 dialog's SAVE & QUIT by click_widget (after its
window popup ends: a hidden button ignores a click, F18080), ESC (27) + click_widget abandon + click_widget yes, client.kill().
Boot S (dirs w2h53_s_*; solo; the vanilla control): S-count, S-files.
Boot H (SHARED, gamemode 1): H-count, H-client, H-123, H-files, H-common.
Boot G (SEPARATE ironman; the client dropped on the geoscape, then SAVE & QUIT): G-count, G-nolist, G-file, G-only, G-menu, G-common.
Boot A (gm3 ironman, the host plays the aliens; SAVE AND ABANDON GAME at (1, 0) in the borrowed battle): A-c0, A-save, A-only, A-menu,
A-client, A-common.  Key 49148; one row per boot.
RED (the unchanged build): H-count, H-client, H-123, H-files, G-nolist, G-file, G-only, A-save (8 of 19). GREEN (E1-E9): 19/19.
A boot miss FAILs every cell of that boot "boot" with ONE "CAPTURE <boot>:" line; a row precondition miss FAILs its later cells
"blocked: <why>". WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_ironman_save_paths.py
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
import test_battle_end_separate as BES  # noqa: E402
import test_campaign_battle_gm3 as G3C1  # noqa: E402
import test_campaign_battle_resume as BR  # noqa: E402
import test_campaign_resume_roles as RR  # noqa: E402

# ----- TASK 0 pins (docs rewrite/w2h53-task0/sa/CONSTANTS.md) -----
KEY = "49148"
NAMES = {"S": "IronSOLO", "H": "IronSH", "G": "IronG1", "A": "IronAlien"}   # every start list of the boot answered with it
QUITNAME = "QuitSave"                 # boot G's red list only (the unchanged build opens one after SAVE & QUIT)
SEED = 1                              # the client's set_seed before its confirm_landing (IB)
ESC = 27
QUIET_S = 8.0                         # both machines on GeoscapeState, no stack change (T0: last start event <= 3.8 s, longest gap 1.6 s)
NGS_SETTLE = 0.2
SAVE_AND_ABANDON = "SAVE AND ABANDON GAME"
DRIVE_S, DROP_S, SQ_S, ENTRY_S, SETTLE_S, PAUSE_S, ABANDON_S, LOST_S, FILE_S = 150, 60, 30, 60, 30, 10, 30, 30, 1.0
ROWS = {"S": ["S-count", "S-files"], "H": ["H-count", "H-client", "H-123", "H-files", "H-common"],
        "G": ["G-count", "G-nolist", "G-file", "G-only", "G-menu", "G-common"],
        "A": ["A-c0", "A-save", "A-only", "A-menu", "A-client", "A-common"]}
RED = {"H-count", "H-client", "H-123", "H-files", "G-nolist", "G-file", "G-only", "A-save"}
BOOT = {"tag": "S"}


class FixtureMiss(Exception):
    pass


RESULTS = []          # (cell, ok, detail)
PRINTED = set()


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
    PRINTED.add(row)


def capture_boot(err, *machines):
    print(f"CAPTURE {BOOT['tag']}: {json.dumps(RR.capture(err, *machines), sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


# ----- CAP's flow helpers (docs rewrite/lh49-cap/lh49.py; TASK 0 t0_h53.py), copied -----
def stk(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:  # noqa: BLE001
        return [f"probe failed: {type(e).__name__}: {str(e)[:120]}"]


def top(gc):
    return (stk(gc) or [None])[-1]


wait = BES.wait_until   # (pred, timeout, interval=0.25) -> (ok, seconds)


def files(gc, data=False):
    """save files (.sav / .asav; data=True: the .data files, EVIDENCE only) -> {basename: {rel, size, mtime}}."""
    out = {}
    for rel in session.save_files(gc.user_dir):
        if rel.lower().endswith(".data") == data:
            st = os.stat(os.path.join(gc.user_dir, rel))
            out[os.path.basename(rel)] = {"rel": rel, "size": st.st_size, "mtime": round(st.st_mtime, 3)}
    return out


def header(gc, rel):
    h, _body, _blobs = BR.read_save(os.path.join(gc.user_dir, rel))
    b = h.get("coopPvpBorrowed")
    return {"name": h.get("name"), "ironman": h.get("ironman"), "borrow": "coopPvpBorrowed" in h,
            "kind": b.get("kind") if isinstance(b, dict) else None, "turn": h.get("turn")}


def headers(gc):
    return {f: dict(v, header=header(gc, v["rel"])) for f, v in files(gc).items()}


def changed(gc, before):
    """{file: header + new} for every save file new or changed since `before`."""
    return {f: dict(header(gc, v["rel"]), new=f not in before) for f, v in files(gc).items()
            if f not in before or (before[f]["mtime"], before[f]["size"]) != (v["mtime"], v["size"])}


def settled(gc, name, timeout):
    """`name` on top and every interactive widget reads hidden false (a Window popup hides them; a hidden button ignores input)."""
    def ok():
        r = gc.cmd({"cmd": "list_widgets"})
        ws = [w for w in r.get("widgets", []) if w.get("interactive")]
        return bool(name in (r.get("state") or "") and ws and all(w.get("hidden") is False for w in ws))
    return wait(ok, timeout, 0.1)[0]


def buttons(gc):
    return {w.get("text"): w.get("visible") for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", [])
            if "TextButton" in (w.get("type") or "")}


def coop_info(gc):
    return gc.cmd({"cmd": "coop_dialog_info"})


def battle(gc):
    return {k: v for k, v in battle_state(gc).items() if k in ("inBattle", "turn", "side", "isBusy", "pendingStates")}


def idle(gc):
    s, b = stk(gc), battle(gc)
    return (s and s[-1] == "BattlescapeState" and not any(("SaveGameState" in x or "CoopState" in x) for x in s)
            and not b.get("isBusy") and b.get("pendingStates") == 0)


def start(host, client, boot, ev):
    """(1)-(5): open_new_game, IRONMAN after NewGameState's widgets settle, newgame_ok; co-op: host_tcp, join, profiles, START."""
    host.ok({"cmd": "open_new_game", "mode": {"S": "solo", "H": "shared", "G": "coop", "A": "coop"}[boot]})
    host.wait_for("difficulty", lambda: PF._has(host, "NewGameState"))
    if not settled(host, "NewGameState", 10):
        capture_boot("NewGameState widgets never settled", host, *([client] if client else []))
    time.sleep(NGS_SETTLE)
    ev["ironmanClick"] = host.cmd({"cmd": "click_widget", "match": "ironman"}).get("ok")
    time.sleep(0.3)
    ev["ironmanToggle"] = [(w.get("text"), w.get("visible")) for w in host.cmd({"cmd": "list_widgets"}).get("widgets", [])
                           if (w.get("text") or "").upper() == "IRONMAN"]
    if not ev["ironmanClick"] or not ev["ironmanToggle"]:
        capture_boot(f"IRONMAN click {ev['ironmanClick']} toggle {ev['ironmanToggle']}", host, *([client] if client else []))
    host.ok({"cmd": "newgame_ok"})
    if boot == "S":
        return {"host": "HostBase", "client": None, "begin": False}
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
    if boot == "A":
        ev["gamemode"] = host.ok({"cmd": "lobby_set_team", "row": PF.row_for(host, "HostPlayer"), "team": "Alien"}).get("gamemode")
    ev["shared"] = host.cmd({"cmd": "get_coop"}).get("shared")
    session.start_campaign_via_button(host)
    return {"host": "HostBase" if boot in ("H", "G") else None, "client": {"G": "ClientBase", "A": "XcomBase"}.get(boot), "begin": True}


def drive(host, client, ev, plan, name):
    """(6)-(9): place bases; answer every ListSaveState at once with `name`, counted per machine; dismiss a client 123 (counted; the
    client's "Saving..." 53 is never touched, F17875); BEGIN on the host's 60 / 62; done when both tops are GeoscapeState with no
    stack change for QUIET_S."""
    t0, last = time.time(), time.time()
    rec = ev["drive"] = {"stacks": {"host": [], "client": []}, "lists": [], "coop": [], "actions": []}
    placed = {w: not plan[w] for w in ("host", "client")}
    begun = not plan["begin"]
    machines = [("host", host)] + ([("client", client)] if client else [])
    while time.time() - t0 < DRIVE_S:
        for who, gc in machines:
            s = stk(gc)
            if not rec["stacks"][who] or rec["stacks"][who][-1][1] != s:
                rec["stacks"][who].append([round(time.time() - t0, 2), s])
                last = time.time()
            t = s[-1] if s else ""
            if t == "BuildNewBaseState" and not placed[who]:
                lon, lat = (session.HOST_LON, session.HOST_LAT) if who == "host" else (LAND_LON, LAND_LAT)
                r = gc.cmd({"cmd": "place_first_base", "lon": lon, "lat": lat, "name": plan[who]})
                if not r.get("ok"):
                    r = gc.cmd({"cmd": "place_first_base", "lon": 0.706, "lat": -0.507, "name": plan[who]})
                rec["actions"].append([who, "place", r.get("ok")])
                placed[who] = bool(r.get("ok"))
            elif t == "ListSaveState":
                n = len([x for x in rec["lists"] if x[0] == who]) + 1
                if n > 4:
                    capture_boot(f"{who}: a fifth ListSaveState", *[g for _w, g in machines])
                settled(gc, "ListSaveState", 5)
                cancel = buttons(gc).get("Cancel")
                rec["lists"].append([who, n, round(time.time() - t0, 2), cancel, gc.cmd({"cmd": "list_save_confirm", "name": name}).get("ok")])
                last = time.time()
            elif t == "CoopState":
                d = coop_info(gc)
                key = [who, d.get("code"), d.get("title")]
                if key not in [x[:3] for x in rec["coop"]]:
                    rec["coop"].append(key + [round(time.time() - t0, 2)])
                if who == "client" and d.get("code") == 123 and d.get("backVisible") is True:
                    rec["actions"].append([who, "dismiss 123", gc.cmd({"cmd": "coop_dialog_back"}).get("ok")])
                    last = time.time()
        if not begun and top(host) == "CoopState":
            d = coop_info(host)
            if d.get("code") in (60, 62) and d.get("backVisible") is True:
                rec["actions"].append(["host", f"BEGIN {d.get('code')}", host.cmd({"cmd": "coop_dialog_back"}).get("ok")])
                begun, last = True, time.time()
        geo_tops = all(top(gc) == "GeoscapeState" for _w, gc in machines)
        if begun and all(placed.values()) and geo_tops and time.time() - last >= QUIET_S:
            rec["done"] = round(time.time() - t0, 2)
            return {w: [x for x in rec["lists"] if x[0] == w] for w in ("host", "client")}
        time.sleep(0.1)
    capture_boot(f"start not over in {DRIVE_S} s: host {stk(host)}" + (f", client {stk(client)}" if client else ""),
                 *[g for _w, g in machines])


def names_bad(fs, want, name):
    bad = [f"save files {sorted(fs)} (want {sorted(want)})"] if set(fs) != set(want) else []
    for f in sorted(set(fs) & set(want)):
        if f.endswith(".sav") and (fs[f]["header"]["name"], fs[f]["header"]["ironman"]) != (name, True):
            bad.append(f"{f} header {fs[f]['header']} (want name {name}, ironman true)")
    return bad


def common(name, client, crash0, extra=()):
    cf, nc = files(client), sorted(RR.crash_set() - crash0)
    bad = ([f"client save files {sorted(cf)}"] if cf else []) + ([f"new crash files {nc}"] if nc else []) + list(extra)
    cell(name, not bad, "; ".join(bad) or f"client save files [] (.data {sorted(files(client, True))}); no new crash file")


# ----- the boots -----
def boot_s(host, _client, ev, crash0):
    ls = drive(host, None, ev, start(host, None, "S", ev), NAMES["S"])
    hs = ev["files"] = headers(host)
    n, hidden = len(ls["host"]), all(x[3] is False for x in ls["host"])
    cell("S-count", n == 2 and hidden, f"host ListSaveStates {n}, Cancel hidden on each {hidden} (want 2, true)")
    bad = names_bad(hs, {NAMES["S"] + ".sav", NAMES["S"] + "_.sav"}, NAMES["S"])
    cell("S-files", not bad, "; ".join(bad) or f"{sorted(hs)}, each name {NAMES['S']}, ironman true")


def boot_h(host, client, ev, crash0):
    ls = drive(host, client, ev, start(host, client, "H", ev), NAMES["H"])
    hs = ev["files"] = headers(host)
    n123 = [x for x in ev["drive"]["coop"] if x[0] == "client" and x[1] == 123]
    cell("H-count", len(ls["host"]) == 2, f"host ListSaveStates {len(ls['host'])} (want 2)")
    cell("H-client", not ls["client"], f"client ListSaveStates {len(ls['client'])} (want 0)")
    cell("H-123", not n123, f"client CoopState 123 seen {len(n123)} {[x[2] for x in n123]} (want none)")
    bad = names_bad(hs, {NAMES["H"] + ".sav", NAMES["H"] + "_.sav", "_autogeo_.asav"}, NAMES["H"])
    cell("H-files", not bad, "; ".join(bad) or f"{sorted(hs)}; {NAMES['H']}.sav name {NAMES['H']}, ironman true")
    tops = [top(host), top(client)]
    common("H-common", client, crash0, [f"tops {tops} (want GeoscapeState on both)"] if tops != ["GeoscapeState"] * 2 else [])


def boot_g(host, client, ev, crash0):
    ls = drive(host, client, ev, start(host, client, "G", ev), NAMES["G"])
    hs = ev["files"] = headers(host)
    bad = ([f"host ListSaveStates {len(ls['host'])} (want 2)"] if len(ls["host"]) != 2 else [])
    bad += [f"client ListSaveStates {len(ls['client'])} (want 0)"] if ls["client"] else []
    bad += names_bad(hs, {NAMES["G"] + ".sav", NAMES["G"] + "_.sav", "_autogeo_.asav"}, NAMES["G"])
    cell("G-count", not bad, "; ".join(bad) or f"host 2 lists, client 0; {sorted(hs)}")
    later = ROWS["G"][1:]
    client.kill()
    ok, s = wait(lambda: (lambda d: d.get("present") and d.get("code") == 62 and d.get("saveQuitVisible"))(coop_info(host)), DROP_S, 0.2)
    ev["dialog"] = {k: v for k, v in coop_info(host).items() if k in ("code", "title", "saveQuitVisible", "saveQuitText")}
    if not ok:
        return block(later, f"no host 62 with SAVE & QUIT visible {DROP_S} s after the drop ({stk(host)}, {ev['dialog']})")
    if not settled(host, "CoopState", PAUSE_S):   # the window popup hides its buttons; a hidden button ignores a click (F18080)
        return block(later, f"the 62 dialog's widgets never read hidden false in {PAUSE_S} s ({stk(host)})")
    before = ev["filesBeforeClick"] = files(host)
    ev["click"] = r = host.cmd({"cmd": "click_widget", "match": "save & quit"})
    if not r.get("ok") or r.get("text") != "SAVE & QUIT":
        return block(later, f"click_widget save & quit: {r}")
    t0, seen, lists = time.time(), ev.setdefault("stacksAfterClick", []), ev.setdefault("listsAfterClick", [])

    def mm():
        s_ = stk(host)
        if not seen or seen[-1][1] != s_:
            seen.append([round(time.time() - t0, 2), s_])
        if s_ and s_[-1] == "ListSaveState" and not lists:
            settled(host, "ListSaveState", 5)
            lists.append([round(time.time() - t0, 2), buttons(host).get("Cancel"),
                          host.cmd({"cmd": "list_save_confirm", "name": QUITNAME}).get("ok")])
        return host.cmd({"cmd": "ending_state"}).get("mainMenu")
    ok, s = ev["mainMenu"] = wait(mm, SQ_S, 0.1)
    time.sleep(FILE_S)
    ch, ws = ev["changed"], ev["world"] = changed(host, before), host.cmd({"cmd": "world_state"})
    ev.update(filesAfter=headers(host), data=files(host, True))
    ls_seen = [x for x in seen if "ListSaveState" in x[1]]
    cell("G-nolist", not ls_seen, f"host stacks with a ListSaveState after the click: {ls_seen[:2]} (want none)")
    want = {"name": NAMES["G"], "ironman": True}
    g = ch.get(NAMES["G"] + ".sav")
    cell("G-file", g is not None and all(g.get(k) == v for k, v in want.items()),
         f"{NAMES['G']}.sav since the click: {g} (want rewritten, {want})")
    cell("G-only", set(ch) <= {NAMES["G"] + ".sav"}, f"save files new or changed since the click: {sorted(ch)} (want none but {NAMES['G']}.sav)")
    cell("G-menu", ok and ws.get("has_save") is False and top(host) == "MainMenuState",
         f"mainMenu {ok} in {s} s, top {top(host)}, has_save {ws.get('has_save')} (want true in {SQ_S} s, MainMenuState, false)")
    common("G-common", client, crash0)


def land(host, client, ev):
    """IB's land: BR stage_to_prompt; client set_seed + confirm_landing; briefings; equip; host NTS OK -> host (1, 0), no Save / CoopState."""
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


def boot_a(host, client, ev, crash0):
    ls = drive(host, client, ev, start(host, client, "A", ev), NAMES["A"])
    f0 = ev["files"] = headers(host)
    h0 = (f0.get(NAMES["A"] + ".sav") or {}).get("header")
    geo.slow_clock(host, client)
    land(host, client, ev)
    later = ROWS["A"][1:]
    if not wait(lambda: idle(host), SETTLE_S)[0]:
        block(ROWS["A"], f"host never idle at (1, 0): {stk(host)} {battle(host)}")
        return
    ev["at"], active = battle(host), (host.cmd({"cmd": "get_coop"}).get("pvpBorrow") or {}).get("active")
    before = ev["filesBeforeEsc"] = files(host)
    host.cmd({"cmd": "inject_input", "kind": "key", "key": ESC})
    pause = wait(lambda: "PauseState" in (top(host) or ""), PAUSE_S, 0.2)[0] and settled(host, "PauseState", 5)
    btn = ev["pause"] = buttons(host) if pause else None
    bad = [f"host ListSaveStates {len(ls['host'])} (want 2)"] if len(ls["host"]) != 2 else []
    bad += [] if h0 and (h0["name"], h0["ironman"], h0["borrow"]) == (NAMES["A"], True, False) else [f"{NAMES['A']}.sav header {h0}"]
    bad += [] if active is True else [f"pvpBorrow.active {active} at {ev['at']}"]
    bad += [] if btn and (btn.get(SAVE_AND_ABANDON), btn.get("SAVE GAME")) == (True, False) else [f"host pause buttons {btn}"]
    cell("A-c0", not bad, "; ".join(bad) or f"2 lists; {NAMES['A']}.sav {h0}; borrow active at (1, 0); pause {SAVE_AND_ABANDON!r} shown, SAVE hidden")
    if not pause:
        return block(later, f"no settled PauseState {PAUSE_S} s after ESC ({stk(host)})")
    ev["clickAbandon"] = r = host.cmd({"cmd": "click_widget", "match": "abandon"})
    if not r.get("ok") or not wait(lambda: "AbandonGameState" in (top(host) or ""), PAUSE_S, 0.1)[0] \
            or not settled(host, "AbandonGameState", 5):
        return block(later, f"click_widget abandon {r}: no settled AbandonGameState ({stk(host)})")
    ev["clickYes"] = r = host.cmd({"cmd": "click_widget", "match": "yes"})
    if not r.get("ok"):
        return block(later, f"click_widget yes: {r}")
    t0, hs, cs = time.time(), ev.setdefault("hostAfterYes", []), ev.setdefault("clientAfterYes", [])

    def mm():
        for gc, lst in ((host, hs), (client, cs)):
            s_ = stk(gc)
            if not lst or lst[-1][1] != s_:
                lst.append([round(time.time() - t0, 2), s_])
        return top(host) == "MainMenuState"
    ok, s = ev["mainMenu"] = wait(mm, ABANDON_S, 0.1)
    time.sleep(FILE_S)
    ch, ws = ev["changed"], ev["world"] = changed(host, before), host.cmd({"cmd": "world_state"})
    lost = ev["clientLost"] = wait(lambda: top(client) == "CoopState" and coop_info(client).get("code") == 21, LOST_S, 0.2)
    ev.update(filesAfter=headers(host), data=files(host, True),
              clientDialog={k: v for k, v in coop_info(client).items() if k in ("code", "title")})
    want = {"name": NAMES["A"], "ironman": True, "borrow": True, "kind": "landing", "turn": 1}
    a = ch.get(NAMES["A"] + ".sav")
    cell("A-save", a is not None and all(a.get(k) == v for k, v in want.items()),
         f"{NAMES['A']}.sav since ESC: {a} (want rewritten, {want})")
    cell("A-only", set(ch) <= {NAMES["A"] + ".sav"}, f"save files new or changed since ESC: {sorted(ch)} (want none but {NAMES['A']}.sav)")
    cell("A-menu", ok and ws.get("has_save") is False, f"host MainMenuState {ok} in {s} s, has_save {ws.get('has_save')} (want true in {ABANDON_S} s, false)")
    cell("A-client", lost[0], f"client top {top(client)} {ev['clientDialog']} (want CoopState 21 in {LOST_S} s; {lost[1]} s)")
    common("A-common", client, crash0)


def run_boot(tag, fn):
    BOOT["tag"] = tag
    x = {"host": GameClient("host", None, make_user_dir(f"w2h53_{tag.lower()}_host"))}
    if tag != "S":
        x["client"] = GameClient("client", None, make_user_dir(f"w2h53_{tag.lower()}_client"))
    ev, t0, crash0 = {}, time.time(), RR.crash_set()
    try:
        for gc in x.values():
            gc.spawn(); gc.connect()
        fn(x["host"], x.get("client"), ev, crash0)
    except FixtureMiss as e:
        block(ROWS[tag], f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"[ERROR] boot {tag}: {err}", flush=True)
        try:
            capture_boot(err, *x.values())
        except Exception:  # noqa: BLE001 - FixtureMiss, or a probe of a dead machine
            pass
        block(ROWS[tag], f"boot (error {err[:200]})")
    finally:
        evidence(tag, dict(ev, bootWall=round(time.time() - t0, 1)))
        row_verdict(tag, ROWS[tag])
        for gc in list(x.values())[::-1]:
            try:
                if gc.proc is not None:
                    gc.shutdown()   # a killed client was reaped by kill(); shutdown() returns at once
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)


def main():
    t0 = time.time()
    for tag, fn in (("S", boot_s), ("H", boot_h), ("G", boot_g), ("A", boot_a)):
        run_boot(tag, fn)
    allc = [c for v in ROWS.values() for c in v]
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== W2-H53 co-op ironman save paths: {len(RESULTS) - len(fails)}/{len(allc)} cells PASS, wall {time.time() - t0:.1f} s ====",
          flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (expected red)' if n in RED else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(allc) else 2)


if __name__ == "__main__":
    main()
