"""test_pve2_resume_refused.py: a co-op campaign save played in PvE2 (game mode 4, both players on the Alien team; only
the release line could write one) is not resumed. RESUME CAMPAIGN in the co-op lobby shows D275's small dialog "There must be at least
one player on the X-COM team for campaign games." with one OK on the host; nothing is resumed and both lobbies stay as they were; OK
returns the host to the same lobby. The same world in its ordinary mode still resumes.

Spec: docs rewrite/prompts/d283_pve2_resume_refusal.md (stage S-A; (f) rows G4, G1, M4; FX-1 .. FX-8) and its ORCHESTRATOR RULINGS
(Q283-1 .. Q283-8 (a)); owner D283 (b), D275, D270 (b); R-D250-SC4A-1 (a): every resume's START HOST goes through the real host window
(host_menu_host visibility 0 -> HostMenu::hostTCPGame), never the host_tcp lever; F16410, F16412, F16416, F16418. TASK 0 pins: docs
rewrite/d283-task0/CONSTANTS.md (boots TG, TM on the unchanged build; the S54 swap SRC_MODE 1 -> 0, F16430).

Boot G: lobby key 48283, dirs d283_g_host / _client / _client2 / _client3. FX-1 session.new_campaign (SEPARATE; its host_tcp is the
new campaign's host step, not a resume); FX-2 the host's save_game d283_g1.sav, both processes end; FX-3 d283_g4.sav = ONE body-line
byte edit of it (coop_gamemode SRC_MODE -> 4, header untouched, every other save key equal); FX-4 the host respawned on ITS dir and
client2 on an EMPTY dir, load_save_menu -> HostMenu -> host_menu_host -> the resume lobby (lobbyMode 2), client2 joins, the Profile
popups closed (profile_ok); FX-5 BEFORE; the host's RESUME press (lobby_action: the real button, LM :921). FX-6 both end; client3 on an
EMPTY dir; RR.resume_campaign on d283_g1.sav (host_menu_host inside).
Boot M (after G): key 48283, dirs d283_m_host / _client / _client2. FX-7 session.bring_up_separate_guest_battle; FX-8 the host's
quick_battle save (exactly one new file), both end, FX-3 -> d283_m4.sav beside it; FX-4, FX-5, the press.
A bring-up, save, copy, relaunch or lobby miss is a FIXTURE-STOP: ONE "CAPTURE <boot>:" line and every remaining cell of that boot
FAILs "boot".
Rows and cells (one PASS / FAIL line per cell, one EVIDENCE line and one ROW line per row; every row runs after a failure):
  G4 (boot G) the PvE2 geoscape save: G4-dialog (host top CampaignTeamRefusedState <= DIALOG_S; TextButtons exactly ["OK"], TEXT
     once), G4-held (press + SETTLE_S: host get_coop / world_state / save files == BEFORE, host stack == BEFORE + [the dialog]),
     G4-client (client2 stack, get_coop, world_state, save files == BEFORE; lobbyOpen true), G4-ok (OK -> host top LobbyMenu <= OK_S;
     READ_S later RESUME CAMPAIGN shown, players / startEligible == BEFORE; a second press shows the dialog again and its OK returns),
     G4-common (0 new crash files in the boot, both processes alive).
  G1 (boot G, after G4) the same world in its ordinary mode: G1-resume (RR.resume_campaign returns; host and client3 GeoscapeState,
     gamemode 1 / 1, host sessionLocked true), G1-common.
  M4 (boot M) the PvE2 mid-battle save: M4-dialog, M4-held, M4-client, M4-ok, M4-common as G4.
RED (D283R, the unchanged build; TASK 0 TG / TM): 4/12 - FAIL G4-dialog, G4-held, G4-client, G4-ok (blocked), M4-dialog, M4-held,
M4-client, M4-ok (blocked): the press resumes the save as ordinary co-op. GREEN (D283G): 12/12.

ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_pve2_resume_refused.py
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import geo  # noqa: E402
import test_campaign_resume_roles as RR  # noqa: E402  (pure helpers + resume_campaign through the real host window)

# ----- pins (docs rewrite/d283-task0/CONSTANTS.md) -----
KEY = "48283"
SRC_MODE = 0            # the mode session.new_campaign's saves carry (TASK 0 TG / TM; S54 swap 1 -> 0, F16430); FX-3 makes it 4
TEXT = "There must be at least one player on the X-COM team for campaign games."   # owner D275, exact
DIALOG = "CampaignTeamRefusedState"                                                 # S-C6 QC6-1 (a): the file-local dialog
G1_SAVE, G4_SAVE, M4_SAVE = "d283_g1.sav", "d283_g4.sav", "d283_m4.sav"
RED = {"G4-dialog", "G4-held", "G4-client", "G4-ok", "M4-dialog", "M4-held", "M4-client", "M4-ok"}   # TASK 0 TG / TM
# ----- bounds -----
DIALOG_S, OK_S, READ_S = 5.0, 5.0, 1.5
SETTLE_S = 3.0          # >= 2 x T_c (0.05 s in TG and TM)
SAVE_S, SAVE_S_M, MENU_S, JOIN_S, TOPS_S, BATTLE_S = 10, 15, 30, 60, 10, 30
COOP_KEYS = ("gamemode", "lobbyMode", "sessionLocked", "lobbyClosed", "resumeAck", "pvpBorrow", "saveID", "onConnect")
HELD_KEYS = COOP_KEYS[:7]
CLIENT_KEYS = ("gamemode", "lobbyMode", "sessionLocked", "lobbyClosed", "onConnect")
ROWS = {"G4": ["G4-dialog", "G4-held", "G4-client", "G4-ok", "G4-common"], "G1": ["G1-resume", "G1-common"],
        "M4": ["M4-dialog", "M4-held", "M4-client", "M4-ok", "M4-common"]}
BOOT = {"tag": "G", "captured": False}
stack, top, crash_set, wait, alive, save_keys = RR.stack, RR.top, RR.crash_set, RR.wait, RR.alive, RR.save_keys


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


def finish(row, ev):
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    bad = [n for n, ok, _ in RESULTS if n in ROWS[row] and not ok]
    print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)


def coop(gc):
    r = gc.cmd({"cmd": "get_coop"})
    return {k: r.get(k) for k in COOP_KEYS}


def world(gc):
    r = gc.cmd({"cmd": "world_state"})
    return {k: r.get(k) for k in ("has_save", "has_battle")}


def lobby(gc):
    r = gc.cmd({"cmd": "lobby_state"})
    return {k: r.get(k) for k in ("lobbyOpen", "lobbyMode", "buttonText", "buttonVisible", "players", "startEligible")}


def files(gc):
    """The machine's save files with (size, mtime) (session.save_files + os.stat)."""
    out = {}
    for f in session.save_files(gc.user_dir):
        st = os.stat(os.path.join(gc.user_dir, f))
        out[f] = [st.st_size, st.st_mtime]
    return out


def fdiff(a, b):
    return {k: [a.get(k), b.get(k)] for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}


def widgets(gc):
    """G4R's: the top state's name and its captioned widgets."""
    r = gc.cmd({"cmd": "list_widgets"})
    ws = [{"type": (w.get("type") or "").replace("class OpenXcom::", ""), "text": w.get("text"), "visible": w.get("visible"),
           "hidden": w.get("hidden")} for w in r.get("widgets") or [] if "text" in w]
    return (r.get("state") or "").replace("class OpenXcom::", ""), ws


def view(host, cl):
    """FX-5's read of both machines (BEFORE, and the cells' read at press + SETTLE_S)."""
    return {"host": {"stack": stack(host), "lobby": lobby(host), "coop": coop(host), "world": world(host), "files": files(host)},
            "client": {"stack": stack(cl), "lobby": lobby(cl), "coop": coop(cl), "world": world(cl), "files": files(cl)}}


def capture(err, *machines):
    """RR.capture (stack, battle, coop_dialog_info, get_coop, the engine log tail) plus lobby_state and world_state; ONE line."""
    cap = RR.capture(err, *[gc for gc in machines if gc is not None])
    for gc in machines:
        if gc is not None and alive(gc) and isinstance(cap["machines"].get(gc.name), dict):
            try:
                cap["machines"][gc.name].update(lobby_state=lobby(gc), world_state=world(gc))
            except Exception as e:  # noqa: BLE001
                cap["machines"][gc.name]["extra"] = f"probe failed: {e!r}"[:200]
    BOOT["captured"] = True
    print(f"CAPTURE {BOOT['tag']}: {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def capture_boot(err, *machines):
    capture(err, *machines)
    raise FixtureMiss(err)


def boot_miss(e, x):
    """A FixtureMiss keeps its CAPTURE line; any other error prints the one CAPTURE line here. Returns the block reason."""
    if isinstance(e, FixtureMiss):
        return str(e)[:200]
    err = f"error {type(e).__name__}: {str(e)[:300]}"
    print(f"[ERROR] boot {BOOT['tag']}: {err}", flush=True)
    if not BOOT["captured"]:
        capture(err, *[gc for k, gc in x.items() if k != "tag"])
    return err[:200]


def end_all(x):
    for k in ("client3", "client2", "client", "host"):
        gc = x.get(k)
        if gc is not None and gc.proc is not None:
            gc.shutdown()


def shutdown_all(x):
    for k in ("client3", "client2", "client", "host"):
        try:
            gc = x.get(k)
            if gc is not None and gc.proc is not None:
                gc.shutdown()
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] shutdown {k}: {e}", flush=True)


def respawn(x, name):
    """FX-4 / FX-6 (RB relaunch's shape): every machine ends; the host respawns on ITS dir and `name` on an EMPTY dir."""
    try:
        end_all(x)
        x["host"] = GameClient("host", None, x["host"].user_dir)
        x[name] = GameClient(name, None, make_user_dir(x["tag"] + "_" + name))
        for gc in (x["host"], x[name]):
            gc.spawn(); gc.connect()
    except Exception as e:  # noqa: BLE001
        capture_boot(f"relaunch ({name}): {type(e).__name__}: {str(e)[:300]}", x["host"], x.get(name))
    return x["host"], x[name]


def fx3(src, dst, ev, machines):
    """FX-3 (F16418): ONE body-line byte edit of the host's own save. Split at the first b"\\n---\\n"; in the body ONLY coop_gamemode
    SRC_MODE -> 4 (exactly one replacement; the header holds no such line); written as bytes; every other save key equal."""
    data = open(src, "rb").read()
    i = data.find(b"\n---\n")
    head, body = (data[:i + 5], data[i + 5:]) if i >= 0 else (data, b"")
    pat = rb"(?m)^coop_gamemode: " + str(SRC_MODE).encode() + rb"(\r?)$"
    new, n = re.subn(pat, rb"coop_gamemode: 4\1", body)
    nh = len(re.findall(pat, head))
    if i < 0 or n != 1 or nh != 0:
        lines = [ln.decode("utf-8", "replace") for ln in data.splitlines() if b"coop_gamemode" in ln]
        capture_boot(f"FX-3 on {os.path.basename(src)}: {n} body replacement(s), {nh} header line(s) (want 1 / 0); its coop_gamemode "
                     f"lines {lines}", *machines)
    with open(dst, "wb") as fh:
        fh.write(head + new)
    k0, k4 = save_keys(src), save_keys(dst)
    diff = sorted(k for k in set(k0) | set(k4) if k0.get(k) != k4.get(k))
    ev["FX-3"] = {"file": os.path.basename(dst), "bytes": os.path.getsize(dst), "keys": k4}
    if k4.get("coop_gamemode@1") != 4 or diff != ["coop_gamemode@1"]:
        capture_boot(f"FX-3: the copy's keys {k4} (want coop_gamemode@1 4, every other key == the source's {k0})", *machines)


def to_lobby(host, cl, save, ev):
    """FX-4: load_save_menu -> HostMenu (EVIDENCE P-1: the mode there); host_menu_host -> the resume lobby (lobbyMode 2;
    EVIDENCE P-2: the live mode); the client joins; host clientName "ClientPlayer"; 2 s; a Profile popup closed; both tops LobbyMenu."""
    host.ok({"cmd": "load_save_menu", "file": save})
    ok, s = wait(lambda: session.has_state(host, "HostMenu"), MENU_S, 0.1)
    if not ok:
        capture_boot(f"FX-4: no host HostMenu within {MENU_S} s of load_save_menu {save}", host, cl)
    ev["P-1"] = {"hostMenuS": s, "gamemode": host.cmd({"cmd": "get_coop"}).get("gamemode")}
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv", "port": KEY, "player": "HostPlayer"})
    ok, s = wait(lambda: session.has_state(host, "LobbyMenu"), MENU_S, 0.1)
    ls = lobby(host)
    ev["P-2"] = {"lobbyS": s, "lobbyMode": ls.get("lobbyMode"), "gamemode": host.cmd({"cmd": "get_coop"}).get("gamemode")}
    if not ok or ls.get("lobbyMode") != 2:
        capture_boot(f"FX-4: host LobbyMenu {ok} after {s} s, lobbyMode {ls.get('lobbyMode')} (want 2)", host, cl)
    cl.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    ok, s = wait(lambda: session.has_state(cl, "LobbyMenu") and host.cmd({"cmd": "get_coop"}).get("clientName") == "ClientPlayer",
                 JOIN_S, 0.25)
    if not ok:
        capture_boot(f"FX-4: {cl.name} LobbyMenu / host clientName 'ClientPlayer' not within {JOIN_S} s", host, cl)
    ev["joinS"] = s
    time.sleep(2.0)
    ev["profileOk"] = {gc.name: gc.cmd({"cmd": "profile_ok"}).get("ok") for gc in (host, cl) if "Profile" in stack(gc)}
    ok, s = wait(lambda: top(host) == "LobbyMenu" and top(cl) == "LobbyMenu", TOPS_S, 0.1)
    if not ok:
        capture_boot(f"FX-4: tops {top(host)} / {top(cl)} (want LobbyMenu / LobbyMenu within {TOPS_S} s)", host, cl)


def ok_cycle(host):
    """The dialog's OK: shown (visible, not hidden) <= OK_S; click_widget OK; host top LobbyMenu <= OK_S. Returns (bad, detail)."""
    shown, s1 = wait(lambda: any(w["type"] == "TextButton" and w["text"] == "OK" and w["visible"] and not w["hidden"]
                                 for w in widgets(host)[1]), OK_S, 0.1)
    rc = host.cmd({"cmd": "click_widget", "match": "OK"})
    back, s2 = wait(lambda: top(host) == "LobbyMenu", OK_S, 0.1)
    d = {"okShownS": s1, "click": {k: rc.get(k) for k in ("ok", "error", "text")}, "lobbyS": s2}
    good = shown and rc.get("ok") is True and back
    return ([] if good else [f"OK shown {shown} after {s1} s, click_widget {d['click']}, host top LobbyMenu {back} after {s2} s (want "
                             f"<= {OK_S:.0f} s; stack {stack(host)})"]), d


def refused_row(row, host, cl, crash0, ev):
    """FX-5 BEFORE, the RESUME press, and the row's five cells (X-dialog, X-held, X-client, X-ok, X-common)."""
    b = view(host, cl)
    ev["BEFORE"] = b
    hb, cb = b["host"], b["client"]
    pre = [f"{k} {hb['lobby'].get(k)!r} (want {w!r})" for k, w in (("buttonText", "RESUME CAMPAIGN"), ("buttonVisible", True),
                                                                     ("startEligible", True)) if hb["lobby"].get(k) != w]
    pre += [f"{k} {hb['coop'].get(k)!r} (want False)" for k in ("sessionLocked", "lobbyClosed") if hb["coop"].get(k) is not False]
    if pre:
        capture_boot(f"FX-5 BEFORE host: {'; '.join(pre)}", host, cl)
    t0 = time.time()
    r = host.cmd({"cmd": "lobby_action"})
    ev["press"] = {k: r.get(k) for k in ("ok", "error")}
    seen = None
    while time.time() - t0 < SETTLE_S:
        if seen is None and DIALOG in (top(host) or ""):
            seen = round(time.time() - t0, 2)
        time.sleep(0.1)
    a = view(host, cl)
    ev["afterS"], ev["after"] = round(time.time() - t0, 2), a
    while seen is None and time.time() - t0 < DIALOG_S:
        if DIALOG in (top(host) or ""):
            seen = round(time.time() - t0, 2)
        time.sleep(0.1)
    ev["dialogS"] = seen
    st, ws = widgets(host)
    ev["widgets"] = {"state": st, "w": ws}
    btns = [w["text"] for w in ws if w["type"] == "TextButton"]
    texts = [w["text"] for w in ws if w["type"] == "Text"]
    cell(f"{row}-dialog", seen is not None and DIALOG in st and btns == ["OK"] and texts.count(TEXT) == 1,
         f"host top {DIALOG} after {seen} s (want <= {DIALOG_S:.0f} s of the press; host stack {stack(host)}); widgets of {st!r}: "
         f"buttons {btns} (want ['OK']), texts {texts} (want one == {TEXT!r})")
    ha, ca = a["host"], a["client"]
    bad = [f"host get_coop {k} {hb['coop'][k]!r} -> {ha['coop'][k]!r}" for k in HELD_KEYS if ha["coop"][k] != hb["coop"][k]]
    bad += [f"host world_state {hb['world']} -> {ha['world']}"] if ha["world"] != hb["world"] else []
    bad += [f"host save files changed {fdiff(hb['files'], ha['files'])}"] if ha["files"] != hb["files"] else []
    bad += [f"host stack {ha['stack']} (want {hb['stack'] + [DIALOG]})"] if ha["stack"] != hb["stack"] + [DIALOG] else []
    cell(f"{row}-held", not bad, "; ".join(bad) or f"at press + {ev['afterS']} s: host get_coop {list(HELD_KEYS)}, world_state and "
         f"save files == BEFORE; host stack == BEFORE + [{DIALOG}]")
    bad = [f"client stack {ca['stack']} (want BEFORE {cb['stack']}: top LobbyMenu, no CoopState)"] \
        if ca["stack"] != cb["stack"] or "CoopState" in ca["stack"] or (ca["stack"] or [None])[-1] != "LobbyMenu" else []
    bad += [f"client get_coop {k} {cb['coop'][k]!r} -> {ca['coop'][k]!r}" for k in CLIENT_KEYS if ca["coop"][k] != cb["coop"][k]]
    bad += [f"client world_state {cb['world']} -> {ca['world']}"] if ca["world"] != cb["world"] else []
    bad += [f"client lobby_state.lobbyOpen {ca['lobby'].get('lobbyOpen')!r} (want True)"] if ca["lobby"].get("lobbyOpen") is not True \
        else []
    bad += [f"client save files changed {fdiff(cb['files'], ca['files'])}"] if ca["files"] != cb["files"] else []
    cell(f"{row}-client", not bad, "; ".join(bad) or f"at press + {ev['afterS']} s: {cl.name} stack, get_coop {list(CLIENT_KEYS)}, "
         "world_state and save files == BEFORE; lobbyOpen true (a live lobby member with no world)")
    if seen is None:
        block([f"{row}-ok"], f"no dialog ({row}-dialog)")
    else:
        bad, ev["ok1"] = ok_cycle(host)
        time.sleep(READ_S)
        hl = lobby(host)
        ev["afterOk"] = {"stack": stack(host), "lobby": hl}
        bad += [f"after OK + {READ_S} s lobby_state {k} {hl.get(k)!r} (want {w!r})" for k, w in
                (("buttonText", "RESUME CAMPAIGN"), ("buttonVisible", True), ("players", hb["lobby"].get("players")),
                 ("startEligible", hb["lobby"].get("startEligible"))) if hl.get(k) != w]
        r2 = host.cmd({"cmd": "lobby_action"})
        again, s2 = wait(lambda: DIALOG in (top(host) or ""), DIALOG_S, 0.1)
        ev["press2"] = {"reply": {k: r2.get(k) for k in ("ok", "error")}, "dialog": again, "dialogS": s2}
        if again:
            bad2, ev["ok2"] = ok_cycle(host)
            bad += [f"second OK: {x}" for x in bad2]
        else:
            bad.append(f"second press: no {DIALOG} within {DIALOG_S:.0f} s (host stack {stack(host)})")
        cell(f"{row}-ok", not bad, "; ".join(bad) or f"OK -> host top LobbyMenu after {ev['ok1']['lobbyS']} s; {READ_S} s later "
             f"RESUME CAMPAIGN shown, players and startEligible == BEFORE; a second press showed the dialog after {s2} s and its OK "
             f"returned after {ev['ok2']['lobbyS']} s")
    common(row, (host, cl), crash0, ev)


def common(row, machines, crash0, ev):
    new = sorted(os.path.basename(p) for p in crash_set() - crash0)
    up = [alive(gc) for gc in machines]
    ev["crashNew"], ev["alive"] = new, up
    cell(f"{row}-common", not new and all(up), f"new crash files {new} (want none); processes alive "
         f"{dict(zip([gc.name for gc in machines], up))} (want all)")


def new_pair(tag):
    return {"tag": tag, "host": GameClient("host", None, make_user_dir(tag + "_host")),
            "client": GameClient("client", None, make_user_dir(tag + "_client"))}


def bring_up(x, fn, what):
    host, cl = x["host"], x["client"]
    try:
        host.spawn(); host.connect(); cl.spawn(); cl.connect()
        fn(host, cl, port=KEY)
    except Exception as e:  # noqa: BLE001
        capture_boot(f"{what}: {type(e).__name__}: {str(e)[:300]}", host, cl)
    return host, cl


def g4_setup(x, ev):
    """FX-1 .. FX-4 of boot G."""
    host, cl = bring_up(x, session.new_campaign, "FX-1 session.new_campaign")
    ev["FX-1"] = {"tops": [top(host), top(cl)], "gamemode": [coop(host)["gamemode"], coop(cl)["gamemode"]]}
    if ev["FX-1"] != {"tops": ["GeoscapeState"] * 2, "gamemode": [SRC_MODE] * 2}:
        capture_boot(f"FX-1: {ev['FX-1']} (want both tops GeoscapeState, both gamemode {SRC_MODE})", host, cl)
    geo.slow_clock(host, cl)
    path = os.path.join(host.user_dir, "xcom1", G1_SAVE)
    r = host.cmd({"cmd": "save_game", "file": G1_SAVE})
    ok, s = wait(lambda: os.path.exists(path) and os.path.getsize(path) > 0, SAVE_S, 0.2)
    if not r.get("ok") or not ok:
        capture_boot(f"FX-2: host save_game {G1_SAVE}: {r}, file present {os.path.exists(path)} within {SAVE_S} s", host, cl)
    time.sleep(1.0)
    ev["FX-2"] = {"file": G1_SAVE, "s": s, "bytes": os.path.getsize(path), "keys": save_keys(path)}
    if ev["FX-2"]["keys"].get("coop_gamemode@1") != SRC_MODE:
        capture_boot(f"FX-2: {G1_SAVE} keys {ev['FX-2']['keys']} (want coop_gamemode@1 {SRC_MODE})", host, cl)
    end_all(x)
    fx3(path, os.path.join(host.user_dir, "xcom1", G4_SAVE), ev, (host, cl))
    host, c2 = respawn(x, "client2")
    to_lobby(host, c2, G4_SAVE, ev)


def g1_row(x, ev):
    """FX-6: both end; client3 on an EMPTY dir; RR.resume_campaign on the ordinary save; G1-resume, G1-common."""
    crash1 = crash_set()
    host, c3 = respawn(x, "client3")
    t0, err = time.time(), None
    try:
        RR.resume_campaign(host, c3, G1_SAVE, port=KEY)
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:300]}"
        ev["capture"] = RR.capture("G1 resume", host, c3)
    ev["resumeS"] = round(time.time() - t0, 2)
    hc, cc = coop(host), coop(c3)
    tops = [top(host), top(c3)]
    ev["after"] = {"tops": tops, "host": hc, "client3": cc, "hostStack": stack(host)}
    bad = [f"RR.resume_campaign raised {err} (host stack {stack(host)})"] if err else []
    bad += [f"tops {tops} (want GeoscapeState / GeoscapeState)"] if tops != ["GeoscapeState"] * 2 else []
    bad += [f"gamemode host {hc['gamemode']} client3 {cc['gamemode']} (want 1 / 1)"] if [hc["gamemode"], cc["gamemode"]] != [1, 1] else []
    bad += [f"host sessionLocked {hc['sessionLocked']!r} (want True)"] if hc["sessionLocked"] is not True else []
    cell("G1-resume", not bad, "; ".join(bad) or f"resumed in {ev['resumeS']} s: host and client3 GeoscapeState, gamemode 1 / 1, host "
         "sessionLocked true")
    common("G1", (host, c3), crash1, ev)


def boot_g():
    BOOT.update(tag="G", captured=False)
    x, ev4, ev1, missed = new_pair("d283_g"), {}, {}, None
    crash0 = crash_set()
    try:
        g4_setup(x, ev4)
        refused_row("G4", x["host"], x["client2"], crash0, ev4)
    except Exception as e:  # noqa: BLE001
        missed = boot_miss(e, x)
        block(ROWS["G4"], f"boot ({missed})")
    finish("G4", ev4)
    if missed is None:
        try:
            g1_row(x, ev1)
        except Exception as e:  # noqa: BLE001
            missed = boot_miss(e, x)
    if missed is not None:
        block(ROWS["G1"], f"boot ({missed})")
    finish("G1", ev1)
    shutdown_all(x)


def battle_ready(host, cl):
    h, c = battle_state(host), battle_state(cl)
    return bool(h.get("inBattle") and c.get("inBattle") and h.get("phase") == "Active" and not h.get("isBusy")
                and top(host) == "BattlescapeState" and top(cl) == "BattlescapeState")


def m4_setup(x, ev):
    """FX-7, FX-8 (exactly one new save file), both end, FX-3 -> d283_m4.sav beside it, FX-4."""
    host, cl = bring_up(x, session.bring_up_separate_guest_battle, "FX-7 session.bring_up_separate_guest_battle")
    ok, s = wait(lambda: battle_ready(host, cl), BATTLE_S, 0.25)
    hb = battle_state(host)
    ev["FX-7"] = {"s": s, "phase": hb.get("phase"), "turn": hb.get("turn"), "coopGamemode": hb.get("coopGamemode"),
                  "tops": [top(host), top(cl)]}
    if not ok:
        capture_boot(f"FX-7: both inBattle, host phase Active and isBusy false, both tops BattlescapeState not within {BATTLE_S} s "
                     f"({ev['FX-7']})", host, cl)
    b0 = set(session.save_files(host.user_dir))
    r = host.cmd({"cmd": "save_game_ui", "type": "quick_battle"})
    ok, s = wait(lambda: set(session.save_files(host.user_dir)) - b0, SAVE_S_M, 0.2)
    time.sleep(1.0)
    new = sorted(set(session.save_files(host.user_dir)) - b0)
    if not r.get("ok") or len(new) != 1:
        capture_boot(f"FX-8: save_game_ui quick_battle {r}: new save files {new} within {SAVE_S_M} s (want exactly one)", host, cl)
    src = os.path.join(host.user_dir, new[0])
    ev["FX-8"] = {"file": new[0], "s": s, "bytes": os.path.getsize(src), "keys": save_keys(src)}
    end_all(x)
    fx3(src, os.path.join(os.path.dirname(src), M4_SAVE), ev, (host, cl))
    host, c2 = respawn(x, "client2")
    to_lobby(host, c2, M4_SAVE, ev)


def boot_m():
    BOOT.update(tag="M", captured=False)
    x, ev = new_pair("d283_m"), {}
    crash0 = crash_set()
    try:
        m4_setup(x, ev)
        refused_row("M4", x["host"], x["client2"], crash0, ev)
    except Exception as e:  # noqa: BLE001
        block(ROWS["M4"], f"boot ({boot_miss(e, x)})")
    finish("M4", ev)
    shutdown_all(x)


def main():
    t0 = time.time()
    boot_g()
    boot_m()
    allc = ROWS["G4"] + ROWS["G1"] + ROWS["M4"]
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== D283 PvE2 campaign save refused on RESUME: {len(RESULTS) - len(fails)}/{len(allc)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (expected red)' if n in RED else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(allc) else 2)


if __name__ == "__main__":
    main()
