"""test_shared_campaign_alien_pick_refused.py: a NEW co-op campaign lobby whose campaign type is Shared refuses every
Alien team pick. The row keeps its team, the game mode stays as it was on both machines, and the host gets a small
dialog with one OK button and the text TEXT_SHARED; OK closes it and the lobby is as it was. A Separate campaign lobby
still accepts an Alien pick (PvP, game mode 2 or 3) and still refuses the second one with its own dialog; a Custom
Battle lobby accepts every Alien pick, both Alien included.

Only the host makes team picks: LobbyMenu::lstSavesPress acts on the host's left click on either row (its own or the
client's) and the client's click does nothing. Every pick goes through the HOST's lobby_set_team with team "" (the
toggle a click on the row makes, LobbyMenu::setPlayerTeam) or a named team for the setup picks; every read waits 1.5 s
after its pick (LobbyMenu::think refreshes the roster each 1 s, only while the lobby is the top state); rows by
PF.row_for; teams are read by name in [ClientPlayer, HostPlayer] order.

Three boots, one after the other, each a fresh host and client:
  shared (key "48241", dirs shared_alien_pick_host / _client): New Game > Co-op, campaign type Shared, both joined,
     START CAMPAIGN shown. Precondition: host save_markers.campaignType 1, lobbyMode 1, both gamemode 0 (a new
     campaign lobby before any pick), teams [XCOM, XCOM].
     shared_client_row: in the untouched lobby the host clicks the client's row; the game mode stays 0.
     shared_host_row: setup HOST -> XCOM, CLIENT -> XCOM (gamemode 1, the precondition), then the host clicks its own
     row; the game mode stays 1.
     Cells per row: -mode (the reply ok with the game mode as it was; both get_coop.gamemode the same; both teams
     [XCOM, XCOM]), -dialog (host top CampaignTeamRefusedState <= 5 s; its widgets: exactly one TextButton "OK" and
     one Text == TEXT_SHARED; the client's top LobbyMenu), -ok (click_widget OK: host top LobbyMenu <= 5 s; 1.5 s
     later START CAMPAIGN shown, both game modes as they were, both teams [XCOM, XCOM], the client's top LobbyMenu).
  separate (key "48243", dirs separate_alien_pick_host / _client): the same with campaign type Separate
     (campaignType 0, both gamemode 0).
     separate_client_alien: the host clicks the client's row: accepted. -mode (reply gamemode 2; both gamemode 2;
        both teams [Alien, XCOM]), -no_dialog (no CampaignTeamRefusedState on either stack; both tops LobbyMenu).
     separate_second_alien: setup CLIENT -> Alien (gamemode 2), then the host clicks its own row: refused with
        TEXT_SECOND_ALIEN. -mode (gamemode 2, teams [Alien, XCOM]), -dialog, -ok as in the shared rows.
     separate_host_alien: setup CLIENT -> XCOM (gamemode 1), then the host clicks its own row: accepted, gamemode 3,
        teams [XCOM, Alien]; -mode, -no_dialog.
  custom (key "48245", dirs custom_alien_pick_host / _client): NEW BATTLE > COOP, both joined, BATTLE SETTINGS shown.
     Precondition: lobbyMode 0, both gamemode 1 (a Custom Battle lobby starts in PvE), teams [XCOM, XCOM].
     custom_host_alien: the host clicks its own row: gamemode 3, teams [XCOM, Alien]. custom_both_alien: setup HOST ->
     Alien (gamemode 3), then the host clicks the client's row: gamemode 4, teams [Alien, Alien]. custom_client_alien: setup HOST -> XCOM, CLIENT ->
     XCOM (gamemode 1), then the host clicks the client's row: gamemode 2, teams [Alien, XCOM]. Each -mode, -no_dialog.
  no_crash: 0 new crash files over the run; every process alive at the end of its boot.
A boot whose bring-up or precondition misses prints ONE "CAPTURE <boot>:" line and FAILs each of its cells "boot";
the other boots still run. A row whose setup pick misses FAILs each of its cells "blocked: <why>".
Without the refusal, each Shared pick is accepted with no dialog (gamemode 2, then 3 after the setup): the -mode and -dialog cells of
shared_client_row and shared_host_row FAIL and their -ok cells are "blocked: no dialog"; every other cell PASSes:
exit 2, 14/20.

ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_shared_campaign_alien_pick_refused.py
"""

import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402
import session  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import test_skirmish_flow as SK  # noqa: E402

# ----- fixture values -----
KEY_SHARED, KEY_SEPARATE, KEY_CUSTOM = "48241", "48243", "48245"
TEXT_SHARED = ("The Alien team is not available in a Shared campaign. Start a Separate campaign to play as the "
               "aliens.")
TEXT_SECOND_ALIEN = "There must be at least one player on the X-COM team for campaign games."
DIALOG = "CampaignTeamRefusedState"      # the lobby's team-refused dialog class
CLICK = ""                               # lobby_set_team's team "" = the toggle a click on the row makes
XCOM2 = ["XCOM", "XCOM"]                 # [ClientPlayer, HostPlayer]
CLIENT_ALIEN = ["Alien", "XCOM"]
HOST_ALIEN = ["XCOM", "Alien"]
BOTH_ALIEN = ["Alien", "Alien"]
CAMPAIGN_SHARED, CAMPAIGN_SEPARATE = 1, 0
# ----- bounds -----
READ_S = 1.5
DIALOG_S = 5.0
OK_S = 5.0
LOBBY_S = 120

SHARED_CELLS = [f"{r}-{c}" for r in ("shared_client_row", "shared_host_row") for c in ("mode", "dialog", "ok")]
SEPARATE_CELLS = ["separate_client_alien-mode", "separate_client_alien-no_dialog", "separate_second_alien-mode",
                  "separate_second_alien-dialog", "separate_second_alien-ok", "separate_host_alien-mode",
                  "separate_host_alien-no_dialog"]
CUSTOM_CELLS = [f"{r}-{c}" for r in ("custom_host_alien", "custom_both_alien", "custom_client_alien")
                for c in ("mode", "no_dialog")]
ALL_CELLS = SHARED_CELLS + SEPARATE_CELLS + CUSTOM_CELLS + ["no_crash"]


class FixtureMiss(Exception):
    pass


class Blocked(Exception):
    pass


RESULTS = []          # (cell, ok, detail)
ALIVE = {}            # boot -> [host alive, client alive] at the end of the boot


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


def top(gc):
    st = stack(gc)
    return st[-1] if st else None


def crash_set():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))


def lobby(gc):
    r = gc.cmd({"cmd": "lobby_state"})
    return {k: r.get(k) for k in ("lobbyOpen", "lobbyMode", "startEligible", "buttonText", "buttonVisible", "players",
                                  "playerTeams")}


def teams(ls, ev):
    """The teams in the roster's name order [ClientPlayer, HostPlayer], read by name; another order is logged."""
    names, tm = ls.get("players") or [], ls.get("playerTeams") or []
    out = []
    for want in ("ClientPlayer", "HostPlayer"):
        idx = [i for i, n in enumerate(names) if want in n]
        out.append(tm[idx[0]] if len(idx) == 1 and idx[0] < len(tm) else None)
    if not (len(names) == 2 and "ClientPlayer" in names[0] and "HostPlayer" in names[1]):
        ev.setdefault("rosterOrder", []).append(names)
    return out


def coop(gc):
    r = gc.cmd({"cmd": "get_coop"})
    return {k: r.get(k) for k in ("gamemode", "noBases", "lobbyMode", "sessionLocked")}


def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v, round(time.time() - t0, 2)
        time.sleep(interval)


def pick(host, rows, who, team, ev):
    """One host pick through lobby_set_team; returns (reply, pick time)."""
    r = host.cmd({"cmd": "lobby_set_team", "row": rows[who], "team": team})
    ev.setdefault("picks", []).append({"who": who, "team": team or "(click)",
                                       "reply": {k: r.get(k) for k in ("ok", "gamemode", "error")}})
    return r, time.time()


def settle(t_pick):
    time.sleep(max(0.0, READ_S - (time.time() - t_pick)))


def widgets(gc):
    r = gc.cmd({"cmd": "list_widgets"})
    ws = [{"type": (w.get("type") or "").replace("class OpenXcom::", ""), "text": w.get("text"), "visible": w.get("visible"),
           "hidden": w.get("hidden")} for w in r.get("widgets") or [] if "text" in w]
    return (r.get("state") or "").replace("class OpenXcom::", ""), ws


def both_state(host, client, ev):
    """get_coop and teams on both machines."""
    hc, cc = coop(host), coop(client)
    ht, ct = teams(lobby(host), ev), teams(lobby(client), ev)
    return hc, cc, ht, ct


def capture_boot(boot, err, host, client):
    cap = {"cpu": harness.cpu_load()}
    for gc in (host, client):
        try:
            with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as fh:
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[-40:]
            cap[gc.name] = {"stack": stack(gc), "coop_dialog_info": gc.cmd({"cmd": "coop_dialog_info"}),
                            "get_coop": gc.cmd({"cmd": "get_coop"}), "lobby_state": lobby(gc),
                            "save_markers": gc.cmd({"cmd": "save_markers"}), "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE {boot}: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def join_and_wait(host, client, key):
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": "ClientPlayer"})
    client.wait_for("client lobby", lambda: session.has_state(client, "LobbyMenu"), timeout=LOBBY_S)
    for gc in (host, client):
        gc.wait_for("join popup", lambda gc=gc: session.has_state(gc, "Profile"))
        gc.ok({"cmd": "profile_ok"})
    host.wait_for("start eligible", lambda: lobby(host).get("startEligible") or None)
    host.wait_for("start offered", lambda: lobby(host).get("buttonVisible") or None, timeout=10)


def bring_up_campaign(host, client, key, mode):
    """New Game > Co-op (Separate "coop" or Shared "shared") up to "START CAMPAIGN shown". Returns the rows."""
    host.ok({"cmd": "open_new_game", "mode": mode})
    host.wait_for("difficulty", lambda: session.has_state(host, "NewGameState"))
    host.ok({"cmd": "newgame_ok"})
    host.wait_for("host window", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": key, "player": "HostPlayer"})
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"))
    join_and_wait(host, client, key)
    return {"HOST": PF.row_for(host, "HostPlayer"), "CLIENT": PF.row_for(host, "ClientPlayer")}


def bring_up_custom(host, client, key):
    """NEW BATTLE > COOP up to "BATTLE SETTINGS shown". Returns the rows."""
    SK.skirmish_host(host, key)
    SK.skirmish_client_at_browser(client)
    join_and_wait(host, client, key)
    return {"HOST": PF.row_for(host, "HostPlayer"), "CLIENT": PF.row_for(host, "ClientPlayer")}


def check_start(boot, host, client, want_lobby_mode, want_type, want_button, want_gm):
    """The boot's precondition: lobby mode, campaign type (campaign boots), both game modes, both teams XCOM."""
    ev = {}
    hl = lobby(host)
    hc, cc, ht, ct = both_state(host, client, ev)
    ev.update({"hostLobby": hl, "get_coop": {"host": hc, "client": cc}, "teams": {"host": ht, "client": ct}})
    sm = host.cmd({"cmd": "save_markers"}) if want_type is not None else {}
    ev["campaignType"] = sm.get("campaignType")
    ev["cpu"] = harness.cpu_load()
    print(f"[bring-up {boot}] {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    ok = (hl.get("lobbyMode") == want_lobby_mode and hl.get("buttonText") == want_button
          and hc.get("gamemode") == want_gm and cc.get("gamemode") == want_gm and ht == XCOM2 and ct == XCOM2
          and (want_type is None or sm.get("campaignType") == want_type))
    if not ok:
        capture_boot(boot, f"precondition: lobbyMode {hl.get('lobbyMode')} (want {want_lobby_mode}), button "
                     f"{hl.get('buttonText')!r} (want {want_button!r}), campaignType {ev['campaignType']} (want "
                     f"{want_type}), gamemode host {hc.get('gamemode')} client {cc.get('gamemode')} (want {want_gm}), teams host "
                     f"{ht} client {ct} (want {XCOM2})", host, client)


def run_setup(host, rows, setup, ev):
    for who, team, need in setup:
        r, t = pick(host, rows, who, team, ev)
        settle(t)
        if not r.get("ok") or (need is not None and r.get("gamemode") != need):
            raise Blocked(f"setup {who} -> {team}: reply {r} (want ok, gamemode {need})")


def refused_row(row, host, client, rows, setup, chosen, want_gm, want_teams, text, button):
    """Setup picks, then the pick the lobby must refuse; cells -mode, -dialog, -ok."""
    names = [f"{row}-mode", f"{row}-dialog", f"{row}-ok"]
    ev, t_row = {}, time.time()
    try:
        run_setup(host, rows, setup, ev)
        hc0, cc0, ht0, ct0 = both_state(host, client, ev)
        ev["before"] = {"host": {"gamemode": hc0.get("gamemode"), "teams": ht0},
                        "client": {"gamemode": cc0.get("gamemode"), "teams": ct0}}
        who, team = chosen
        r, t = pick(host, rows, who, team, ev)
        seen, ev["dialogS"] = wait_until(lambda: DIALOG in (top(host) or ""), DIALOG_S)
        ev["hostTop"] = top(host)
        settle(t)
        ev["clientTop"] = top(client)
        hc, cc, ht, ct = both_state(host, client, ev)
        st, ws = widgets(host)
        ev["hostWidgets"] = {"state": st, "w": ws}
        btns = [w["text"] for w in ws if w["type"] == "TextButton"]
        texts = [w["text"] for w in ws if w["type"] == "Text"]
        ev["after"] = {"host": {"coop": hc, "teams": ht, "stack": stack(host)},
                       "client": {"coop": cc, "teams": ct, "stack": stack(client)}}
        cell(f"{row}-mode", r.get("ok") is True and r.get("gamemode") == want_gm and hc.get("gamemode") == want_gm
             and cc.get("gamemode") == want_gm and ht == want_teams and ct == want_teams,
             f"reply ok {r.get('ok')} gamemode {r.get('gamemode')}; get_coop.gamemode host {hc.get('gamemode')} client "
             f"{cc.get('gamemode')} (want {want_gm}); playerTeams [ClientPlayer, HostPlayer] host {ht} client {ct} "
             f"(want {want_teams})")
        cell(f"{row}-dialog", bool(seen) and DIALOG in st and btns == ["OK"] and texts.count(text) == 1
             and len(texts) == 1 and ev["clientTop"] == "LobbyMenu",
             f"host top {ev['hostTop']} after {ev['dialogS']} s (want {DIALOG} <= {DIALOG_S:.0f} s); widgets of {st}: "
             f"buttons {btns} (want ['OK']), texts {texts} (want exactly [{text!r}]); client top {ev['clientTop']} "
             f"(want LobbyMenu)")
        if not seen:
            raise Blocked(f"no dialog ({row}-dialog)")
        shown, ev["okShownS"] = wait_until(lambda: any(w["type"] == "TextButton" and w["text"] == "OK" and w["visible"]
                                                       and not w["hidden"] for w in widgets(host)[1]), OK_S)
        rc = host.cmd({"cmd": "click_widget", "match": "OK"})
        ev["click"] = {k: rc.get(k) for k in ("ok", "error", "text")}
        back, ev["lobbyBackS"] = wait_until(lambda: top(host) == "LobbyMenu", OK_S)
        time.sleep(READ_S)
        hl = lobby(host)
        hc2, cc2, ht2, ct2 = both_state(host, client, ev)
        ev["afterOk"] = {"stack": stack(host), "lobby": hl, "get_coop": {"host": hc2, "client": cc2},
                         "teams": {"host": ht2, "client": ct2}, "clientTop": top(client)}
        cell(f"{row}-ok", bool(shown) and rc.get("ok") is True and bool(back) and hl.get("buttonVisible") is True
             and hl.get("buttonText") == button and hc2.get("gamemode") == want_gm and cc2.get("gamemode") == want_gm
             and ht2 == want_teams and ct2 == want_teams and ev["afterOk"]["clientTop"] == "LobbyMenu",
             f"OK shown {bool(shown)} after {ev['okShownS']} s; click_widget {ev['click']}; host top LobbyMenu {bool(back)} "
             f"after {ev['lobbyBackS']} s (want <= {OK_S:.0f} s); 1.5 s later buttonVisible {hl.get('buttonVisible')} "
             f"buttonText {hl.get('buttonText')!r} (want True {button!r}); gamemode host {hc2.get('gamemode')} client "
             f"{cc2.get('gamemode')} (want {want_gm}); teams host {ht2} client {ct2} (want {want_teams}); client top "
             f"{ev['afterOk']['clientTop']} (want LobbyMenu)")
    except Blocked as e:
        block(names, str(e))
    ev["wallS"] = round(time.time() - t_row, 1)
    evidence(row, ev)
    row_verdict(row, names)


def accepted_row(row, host, client, rows, setup, chosen, want_gm, want_teams):
    """Setup picks, then a pick the lobby must accept; cells -mode, -no_dialog."""
    names = [f"{row}-mode", f"{row}-no_dialog"]
    ev, t_row = {}, time.time()
    try:
        run_setup(host, rows, setup, ev)
        who, team = chosen
        r, t = pick(host, rows, who, team, ev)
        settle(t)
        hc, cc, ht, ct = both_state(host, client, ev)
        hs, cs = stack(host), stack(client)
        ev["after"] = {"host": {"coop": hc, "teams": ht, "stack": hs}, "client": {"coop": cc, "teams": ct, "stack": cs}}
        cell(f"{row}-mode", r.get("ok") is True and r.get("gamemode") == want_gm and hc.get("gamemode") == want_gm
             and cc.get("gamemode") == want_gm and ht == want_teams and ct == want_teams,
             f"reply ok {r.get('ok')} gamemode {r.get('gamemode')}; get_coop.gamemode host {hc.get('gamemode')} client "
             f"{cc.get('gamemode')} (want {want_gm}); playerTeams [ClientPlayer, HostPlayer] host {ht} client {ct} "
             f"(want {want_teams})")
        dlg = [s for s in hs + cs if DIALOG in s]
        cell(f"{row}-no_dialog", not dlg and hs[-1:] == ["LobbyMenu"] and cs[-1:] == ["LobbyMenu"],
             f"{DIALOG} on the stacks {dlg} (want none); tops host {hs[-1:]} client {cs[-1:]} (want LobbyMenu)")
    except Blocked as e:
        block(names, str(e))
    ev["wallS"] = round(time.time() - t_row, 1)
    evidence(row, ev)
    row_verdict(row, names)


def boot_shared(host, client):
    try:
        rows = bring_up_campaign(host, client, KEY_SHARED, "shared")
    except Exception as e:  # noqa: BLE001
        capture_boot("shared", f"bring-up: {type(e).__name__}: {e}", host, client)
    check_start("shared", host, client, 1, CAMPAIGN_SHARED, "START CAMPAIGN", 0)
    reset = [("HOST", "XCOM", None), ("CLIENT", "XCOM", 1)]
    refused_row("shared_client_row", host, client, rows, [], ("CLIENT", CLICK), 0, XCOM2, TEXT_SHARED,
                "START CAMPAIGN")
    refused_row("shared_host_row", host, client, rows, reset, ("HOST", CLICK), 1, XCOM2, TEXT_SHARED,
                "START CAMPAIGN")


def boot_separate(host, client):
    try:
        rows = bring_up_campaign(host, client, KEY_SEPARATE, "coop")
    except Exception as e:  # noqa: BLE001
        capture_boot("separate", f"bring-up: {type(e).__name__}: {e}", host, client)
    check_start("separate", host, client, 1, CAMPAIGN_SEPARATE, "START CAMPAIGN", 0)
    accepted_row("separate_client_alien", host, client, rows, [], ("CLIENT", CLICK), 2, CLIENT_ALIEN)
    refused_row("separate_second_alien", host, client, rows, [("CLIENT", "Alien", 2)], ("HOST", CLICK), 2,
                CLIENT_ALIEN, TEXT_SECOND_ALIEN, "START CAMPAIGN")
    accepted_row("separate_host_alien", host, client, rows, [("CLIENT", "XCOM", 1)], ("HOST", CLICK), 3, HOST_ALIEN)


def boot_custom(host, client):
    try:
        rows = bring_up_custom(host, client, KEY_CUSTOM)
    except Exception as e:  # noqa: BLE001
        capture_boot("custom", f"bring-up: {type(e).__name__}: {e}", host, client)
    check_start("custom", host, client, 0, None, "BATTLE SETTINGS", 1)
    accepted_row("custom_host_alien", host, client, rows, [], ("HOST", CLICK), 3, HOST_ALIEN)
    accepted_row("custom_both_alien", host, client, rows, [("HOST", "Alien", 3)], ("CLIENT", CLICK), 4, BOTH_ALIEN)
    accepted_row("custom_client_alien", host, client, rows, [("HOST", "XCOM", None), ("CLIENT", "XCOM", 1)],
                 ("CLIENT", CLICK), 2, CLIENT_ALIEN)


def run_boot(boot, fn, cells):
    host = GameClient("host", None, make_user_dir(f"{boot}_alien_pick_host"))
    client = GameClient("client", None, make_user_dir(f"{boot}_alien_pick_client"))
    t0 = time.time()
    try:
        host.spawn(); host.connect(); client.spawn(); client.connect()
        fn(host, client)
    except FixtureMiss as e:
        block(cells, f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR {boot}] {type(e).__name__}: {e}", flush=True)
        block(cells, f"error {type(e).__name__}: {str(e)[:200]}")
    finally:
        ALIVE[boot] = [gc.proc is not None and gc.proc.poll() is None for gc in (host, client)]
        try:
            shutdown_clients(host, client)
        except Exception as e:  # noqa: BLE001
            ALIVE[boot].append(f"shutdown: {str(e)[:200]}")
    print(f"[boot {boot}] wall {time.time() - t0:.1f} s; cpu {harness.cpu_load()}", flush=True)


def main():
    t0 = time.time()
    crash0 = crash_set()
    run_boot("shared", boot_shared, SHARED_CELLS)
    run_boot("separate", boot_separate, SEPARATE_CELLS)
    run_boot("custom", boot_custom, CUSTOM_CELLS)
    new = sorted(os.path.basename(p) for p in crash_set() - crash0)
    cell("no_crash", not new and all(v == [True, True] for v in ALIVE.values()) and len(ALIVE) == 3,
         f"new crash files {new} (want none); processes alive at each boot's end {ALIVE} (want [True, True] each)")
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== test_shared_campaign_alien_pick_refused: {len(RESULTS) - len(fails)}/{len(RESULTS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(ALL_CELLS) else 2)


if __name__ == "__main__":
    main()
