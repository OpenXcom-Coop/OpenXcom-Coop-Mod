"""test_ironman_save_paths.py: co-op ironman save paths.

Ironman holds for the save's owner, with one campaign file; ironman is a host-only setting and the client never saves.
A new SHARED ironman campaign asks the host for a save name twice, as solo and every other mode do (vanilla's two
prompts kept), and never asks the second player (no code-123 "desync problems" popup); a named ironman campaign's
wait-dialog SAVE & QUIT saves the campaign's own file and goes to the main menu (no free-name list); an ironman alien
host's SAVE AND ABANDON GAME in a gm3 borrowed battle saves its campaign file (with the battle) before the session
ends.
Real inputs only: the IRONMAN toggle, every save list answered by list_save_confirm, the 62 dialog's SAVE & QUIT by
click_widget (after its window popup ends: a hidden button ignores a click), ESC (27) + click_widget abandon +
click_widget yes, client.kill().
Boot solo (dirs ironman_save_paths_solo_*; the vanilla control): solo_two_save_lists, solo_save_files.
Boot shared (SHARED, gamemode 1): shared_two_host_lists, shared_no_client_list, shared_no_desync_popup,
shared_save_files, shared_common.
Boot separate (SEPARATE ironman; the client dropped on the geoscape, then SAVE & QUIT): separate_start_saves,
save_quit_no_list, save_quit_rewrites_file, save_quit_only_campaign_file, save_quit_main_menu, separate_common.
Boot alien_host (gm3 ironman, the host plays the aliens; SAVE AND ABANDON GAME at (1, 0) in the borrowed battle):
alien_host_start, abandon_saves_campaign, abandon_only_campaign_file, abandon_main_menu, abandon_client_lost,
alien_host_common. Key 49148; one row per boot.
Without the fix the FIX cells fail: shared_two_host_lists, shared_no_client_list, shared_no_desync_popup,
shared_save_files, save_quit_no_list, save_quit_rewrites_file, save_quit_only_campaign_file, abandon_saves_campaign (8
of 19); with it all 19 pass.
A boot miss FAILs every cell of that boot "boot" with ONE "CAPTURE <boot>:" line; a row precondition miss FAILs its
later cells "blocked: <why>". ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
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
import test_campaign_battle_gm3 as G3B  # noqa: E402
import test_campaign_battle_resume as BR  # noqa: E402
import test_campaign_resume_roles as RR  # noqa: E402

# ----- fixture values -----
KEY = "49148"
NAMES = {"solo": "IronSOLO", "shared": "IronSH", "separate": "IronSEP",
         "alien_host": "IronAlien"}   # every start list of the boot answered with it
QUITNAME = "QuitSave"                 # a list after the separate boot's SAVE & QUIT (only when broken: it opens one)
SEED = 1                              # the client's set_seed before its confirm_landing (as test_ironman_borrow)
ESC = 27
QUIET_S = 8.0                         # both machines on GeoscapeState, no stack change (measured: last start event
                                      # <= 3.8 s, longest gap 1.6 s)
NGS_SETTLE = 0.2
SAVE_AND_ABANDON = "SAVE AND ABANDON GAME"
DRIVE_S, DROP_S, SQ_S, ENTRY_S, SETTLE_S, PAUSE_S, ABANDON_S, LOST_S, FILE_S = 150, 60, 30, 60, 30, 10, 30, 30, 1.0
ROWS = {"solo": ["solo_two_save_lists", "solo_save_files"],
        "shared": ["shared_two_host_lists", "shared_no_client_list", "shared_no_desync_popup", "shared_save_files",
                   "shared_common"],
        "separate": ["separate_start_saves", "save_quit_no_list", "save_quit_rewrites_file",
                     "save_quit_only_campaign_file", "save_quit_main_menu", "separate_common"],
        "alien_host": ["alien_host_start", "abandon_saves_campaign", "abandon_only_campaign_file", "abandon_main_menu",
                       "abandon_client_lost", "alien_host_common"]}
FIX = {"shared_two_host_lists", "shared_no_client_list", "shared_no_desync_popup", "shared_save_files",
       "save_quit_no_list", "save_quit_rewrites_file", "save_quit_only_campaign_file", "abandon_saves_campaign"}
BOOT = {"tag": "solo"}


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


# ----- flow helpers: stacks, widgets, save files -----
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
    """open_new_game, IRONMAN after NewGameState's widgets settle, newgame_ok; co-op: host_tcp, join, profiles,
    START."""
    host.ok({"cmd": "open_new_game",
             "mode": {"solo": "solo", "shared": "shared", "separate": "coop", "alien_host": "coop"}[boot]})
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
    if boot == "solo":
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
    if boot == "alien_host":
        ev["gamemode"] = host.ok({"cmd": "lobby_set_team", "row": PF.row_for(host, "HostPlayer"), "team": "Alien"}).get("gamemode")
    ev["shared"] = host.cmd({"cmd": "get_coop"}).get("shared")
    session.start_campaign_via_button(host)
    return {"host": "HostBase" if boot in ("shared", "separate") else None,
            "client": {"separate": "ClientBase", "alien_host": "XcomBase"}.get(boot), "begin": True}


def drive(host, client, ev, plan, name):
    """Place bases; answer every ListSaveState at once with `name`, counted per machine; dismiss a client 123
    (counted; the client's "Saving..." 53 is never touched); BEGIN on the host's 60 / 62; done when both tops are
    GeoscapeState with no stack change for QUIET_S."""
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
def boot_solo(host, _client, ev, crash0):
    ls = drive(host, None, ev, start(host, None, "solo", ev), NAMES["solo"])
    hs = ev["files"] = headers(host)
    n, hidden = len(ls["host"]), all(x[3] is False for x in ls["host"])
    cell("solo_two_save_lists", n == 2 and hidden,
         f"host ListSaveStates {n}, Cancel hidden on each {hidden} (want 2, true)")
    bad = names_bad(hs, {NAMES["solo"] + ".sav", NAMES["solo"] + "_.sav"}, NAMES["solo"])
    cell("solo_save_files", not bad, "; ".join(bad) or f"{sorted(hs)}, each name {NAMES['solo']}, ironman true")


def boot_shared(host, client, ev, crash0):
    ls = drive(host, client, ev, start(host, client, "shared", ev), NAMES["shared"])
    hs = ev["files"] = headers(host)
    n123 = [x for x in ev["drive"]["coop"] if x[0] == "client" and x[1] == 123]
    cell("shared_two_host_lists", len(ls["host"]) == 2, f"host ListSaveStates {len(ls['host'])} (want 2)")
    cell("shared_no_client_list", not ls["client"], f"client ListSaveStates {len(ls['client'])} (want 0)")
    cell("shared_no_desync_popup", not n123,
         f"client CoopState 123 seen {len(n123)} {[x[2] for x in n123]} (want none)")
    bad = names_bad(hs, {NAMES["shared"] + ".sav", NAMES["shared"] + "_.sav", "_autogeo_.asav"}, NAMES["shared"])
    cell("shared_save_files", not bad,
         "; ".join(bad) or f"{sorted(hs)}; {NAMES['shared']}.sav name {NAMES['shared']}, ironman true")
    tops = [top(host), top(client)]
    common("shared_common", client, crash0,
           [f"tops {tops} (want GeoscapeState on both)"] if tops != ["GeoscapeState"] * 2 else [])


def boot_separate(host, client, ev, crash0):
    ls = drive(host, client, ev, start(host, client, "separate", ev), NAMES["separate"])
    hs = ev["files"] = headers(host)
    bad = ([f"host ListSaveStates {len(ls['host'])} (want 2)"] if len(ls["host"]) != 2 else [])
    bad += [f"client ListSaveStates {len(ls['client'])} (want 0)"] if ls["client"] else []
    bad += names_bad(hs, {NAMES["separate"] + ".sav", NAMES["separate"] + "_.sav", "_autogeo_.asav"}, NAMES["separate"])
    cell("separate_start_saves", not bad, "; ".join(bad) or f"host 2 lists, client 0; {sorted(hs)}")
    later = ROWS["separate"][1:]
    client.kill()
    ok, s = wait(lambda: (lambda d: d.get("present") and d.get("code") == 62 and d.get("saveQuitVisible"))(coop_info(host)), DROP_S, 0.2)
    ev["dialog"] = {k: v for k, v in coop_info(host).items() if k in ("code", "title", "saveQuitVisible", "saveQuitText")}
    if not ok:
        return block(later, f"no host 62 with SAVE & QUIT visible {DROP_S} s after the drop ({stk(host)}, {ev['dialog']})")
    if not settled(host, "CoopState", PAUSE_S):   # the window popup hides its buttons; a hidden button ignores a click
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
    cell("save_quit_no_list", not ls_seen,
         f"host stacks with a ListSaveState after the click: {ls_seen[:2]} (want none)")
    want = {"name": NAMES["separate"], "ironman": True}
    g = ch.get(NAMES["separate"] + ".sav")
    cell("save_quit_rewrites_file", g is not None and all(g.get(k) == v for k, v in want.items()),
         f"{NAMES['separate']}.sav since the click: {g} (want rewritten, {want})")
    cell("save_quit_only_campaign_file", set(ch) <= {NAMES["separate"] + ".sav"},
         f"save files new or changed since the click: {sorted(ch)} (want none but {NAMES['separate']}.sav)")
    cell("save_quit_main_menu", ok and ws.get("has_save") is False and top(host) == "MainMenuState",
         f"mainMenu {ok} in {s} s, top {top(host)}, has_save {ws.get('has_save')} (want true in {SQ_S} s, MainMenuState, false)")
    common("separate_common", client, crash0)


def land(host, client, ev):
    """test_ironman_borrow's land: BR stage_to_prompt; client set_seed + confirm_landing; briefings; equip; host NTS
    OK -> host (1, 0), no Save / CoopState."""
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
    if not wait(lambda: G3B.in_battle(host) and G3B.in_battle(client), ENTRY_S)[0]:
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


def boot_alien_host(host, client, ev, crash0):
    ls = drive(host, client, ev, start(host, client, "alien_host", ev), NAMES["alien_host"])
    f0 = ev["files"] = headers(host)
    h0 = (f0.get(NAMES["alien_host"] + ".sav") or {}).get("header")
    geo.slow_clock(host, client)
    land(host, client, ev)
    later = ROWS["alien_host"][1:]
    if not wait(lambda: idle(host), SETTLE_S)[0]:
        block(ROWS["alien_host"], f"host never idle at (1, 0): {stk(host)} {battle(host)}")
        return
    ev["at"], active = battle(host), (host.cmd({"cmd": "get_coop"}).get("pvpBorrow") or {}).get("active")
    before = ev["filesBeforeEsc"] = files(host)
    host.cmd({"cmd": "inject_input", "kind": "key", "key": ESC})
    pause = wait(lambda: "PauseState" in (top(host) or ""), PAUSE_S, 0.2)[0] and settled(host, "PauseState", 5)
    btn = ev["pause"] = buttons(host) if pause else None
    bad = [f"host ListSaveStates {len(ls['host'])} (want 2)"] if len(ls["host"]) != 2 else []
    bad += [] if h0 and (h0["name"], h0["ironman"], h0["borrow"]) == (NAMES["alien_host"], True, False) \
        else [f"{NAMES['alien_host']}.sav header {h0}"]
    bad += [] if active is True else [f"pvpBorrow.active {active} at {ev['at']}"]
    bad += [] if btn and (btn.get(SAVE_AND_ABANDON), btn.get("SAVE GAME")) == (True, False) else [f"host pause buttons {btn}"]
    cell("alien_host_start", not bad,
         "; ".join(bad) or f"2 lists; {NAMES['alien_host']}.sav {h0}; borrow active at (1, 0); "
                           f"pause {SAVE_AND_ABANDON!r} shown, SAVE hidden")
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
    want = {"name": NAMES["alien_host"], "ironman": True, "borrow": True, "kind": "landing", "turn": 1}
    a = ch.get(NAMES["alien_host"] + ".sav")
    cell("abandon_saves_campaign", a is not None and all(a.get(k) == v for k, v in want.items()),
         f"{NAMES['alien_host']}.sav since ESC: {a} (want rewritten, {want})")
    cell("abandon_only_campaign_file", set(ch) <= {NAMES["alien_host"] + ".sav"},
         f"save files new or changed since ESC: {sorted(ch)} (want none but {NAMES['alien_host']}.sav)")
    cell("abandon_main_menu", ok and ws.get("has_save") is False,
         f"host MainMenuState {ok} in {s} s, has_save {ws.get('has_save')} (want true in {ABANDON_S} s, false)")
    cell("abandon_client_lost", lost[0],
         f"client top {top(client)} {ev['clientDialog']} (want CoopState 21 in {LOST_S} s; {lost[1]} s)")
    common("alien_host_common", client, crash0)


def run_boot(tag, fn):
    BOOT["tag"] = tag
    x = {"host": GameClient("host", None, make_user_dir(f"ironman_save_paths_{tag.lower()}_host"))}
    if tag != "solo":
        x["client"] = GameClient("client", None, make_user_dir(f"ironman_save_paths_{tag.lower()}_client"))
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
    for tag, fn in (("solo", boot_solo), ("shared", boot_shared), ("separate", boot_separate),
                    ("alien_host", boot_alien_host)):
        run_boot(tag, fn)
    allc = [c for v in ROWS.values() for c in v]
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== co-op ironman save paths: {len(RESULTS) - len(fails)}/{len(allc)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (FIX cell)' if n in FIX else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(allc) else 2)


if __name__ == "__main__":
    main()
