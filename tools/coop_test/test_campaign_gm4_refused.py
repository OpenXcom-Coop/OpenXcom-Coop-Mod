"""test_campaign_gm4_refused.py: a NEW co-op campaign lobby refuses the team pick that would put both players
on the Alien team (no PvE2 / game mode 4 campaigns; PvE2 stays a Custom Battle mode) and opens D275's small dialog with one OK
button that closes it; the campaign still starts afterwards.

Spec: docs rewrite/prompts/d250u_pvp_campaigns_sc.md, AMENDMENT SC-4 (SC4-9 and SC4-10: rows G1-G3, FX6-1 .. FX6-7), owner rulings
D270 (b) and D275, D226 (a), QC6-1 .. QC6-3 (a); F15523 (setPlayerTeam is the only writer of a campaign gm4), F15524 (the lobby's
file-local popup, list_widgets / click_widget, lobby_state.playerTeams). docs rewrite/d250u-task0/sc6/CONSTANTS.md (boot Ga
on the unchanged build: premise P-C6, every lever reply, the walls).

Boot G: key "48029", dirs d250uc6_g_host / d250uc6_g_client. Bring-up = PF.start_pvp_campaign's steps up to "START CAMPAIGN shown"
(FX6-2); a miss, or G1's precondition missed, is a FIXTURE-STOP: ONE "CAPTURE G:" line, every remaining cell FAILs "boot". Every pick
goes through the HOST's lobby_set_team (the LobbyMenu::setPlayerTeam funnel the host's click uses); every read waits 1.5 s after its
pick (FX6-4: LobbyMenu::think refreshes the roster each 1 s, only while the lobby is the top state); rows by PF.row_for (FX6-3).
Rows and cells (one PASS / FAIL line per cell, one EVIDENCE line and one ROW line per row; every row runs after a failure unless its
precondition was never reached, then each of its cells FAILs "blocked: <why>"):
  G1 host Alien first: HOST -> Alien (gamemode 3, the precondition), then CLIENT -> Alien.
     G1-mode (the reply ok with gamemode 3; both get_coop.gamemode 3; both playerTeams [XCOM, Alien] in [ClientPlayer, HostPlayer]
     order), G1-dialog (host top CampaignTeamRefusedState <= 5 s; its widgets: exactly one TextButton "OK" and one Text == D275's
     text; the client's top LobbyMenu), G1-ok (click_widget OK: host top LobbyMenu <= 5 s; 1.5 s later START CAMPAIGN shown and the
     host's teams unchanged).
  G2 client Alien first: HOST -> XCOM (EVIDENCE: gamemode 1 once G1 was refused, 2 when it was not), CLIENT -> Alien (gamemode 2, the
     precondition), then HOST -> Alien. G2-mode (gamemode 2; teams [Alien, XCOM]), G2-dialog, G2-ok as G1.
  G3 the campaign starts after the refusals (GUARD): HOST -> XCOM (gamemode 2, the precondition), START CAMPAIGN, the host places its
     first base, BEGIN. G3-start (both GeoscapeState top <= 120 s; both gamemode 2; client noBases true, host false), G3-common (0 new
     crash files in the boot; both processes alive).
RED (C6R, the unchanged build): each second Alien pick makes gamemode 4 with teams [Alien, Alien] and no dialog: G1-mode, G1-dialog,
G1-ok, G2-mode, G2-dialog, G2-ok FAIL (the -ok cells "blocked: no dialog"); G3-start and G3-common PASS: exit 2, 2/8. GREEN (C6G): 8/8.

ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_campaign_gm4_refused.py
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

# ----- pins (docs rewrite/d250u-task0/sc6/CONSTANTS.md; SC4-10 FX6-1 .. FX6-7) -----
KEY = "48029"                                                                       # FX6-1 (TASK 0 used 48031)
TEXT = "There must be at least one player on the X-COM team for campaign games."   # FX6-5: owner D275, exact
DIALOG = "CampaignTeamRefusedState"                                                 # the file-local dialog's class
G1_TEAMS = ["XCOM", "Alien"]      # [ClientPlayer, HostPlayer] (FX6-3) with the host on the Alien team (gamemode 3)
G2_TEAMS = ["Alien", "XCOM"]      # the client on the Alien team (gamemode 2)
FALLBACK_BASE = (0.706, -0.507)   # PF.start_pvp_campaign's fallback point on a refused placement (FX6-7)
# ----- bounds -----
READ_S = 1.5
DIALOG_S = 5.0
OK_S = 5.0
LOBBY_S = 120
BASE_S = 60
GEO_S = 120


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


def lobby(gc):
    r = gc.cmd({"cmd": "lobby_state"})
    return {k: r.get(k) for k in ("lobbyOpen", "lobbyMode", "startEligible", "buttonText", "buttonVisible", "players",
                                  "playerTeams")}


def teams(ls, ev):
    """FX6-3: the teams in the roster's name order [ClientPlayer, HostPlayer], read by name; another order is logged."""
    names, tm = ls.get("players") or [], ls.get("playerTeams") or []
    out = []
    for want in ("ClientPlayer", "HostPlayer"):
        idx = [i for i, n in enumerate(names) if want in n]
        out.append(tm[idx[0]] if len(idx) == 1 and idx[0] < len(tm) else None)
    if not (len(names) == 2 and "ClientPlayer" in names[0] and "HostPlayer" in names[1]):
        ev.setdefault("fx63Order", []).append(names)
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
    ev.setdefault("picks", []).append({"who": who, "team": team, "reply": {k: r.get(k) for k in ("ok", "gamemode", "error")}})
    return r, time.time()


def settle(t_pick):
    time.sleep(max(0.0, READ_S - (time.time() - t_pick)))


def widgets(gc):
    r = gc.cmd({"cmd": "list_widgets"})
    ws = [{"type": (w.get("type") or "").replace("class OpenXcom::", ""), "text": w.get("text"), "visible": w.get("visible"),
           "hidden": w.get("hidden")} for w in r.get("widgets") or [] if "text" in w]
    return (r.get("state") or "").replace("class OpenXcom::", ""), ws


def capture_boot(err, host, client):
    cap = {}
    for gc in (host, client):
        try:
            bs = session.battle_state(gc)
            with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as fh:
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[-40:]
            cap[gc.name] = {"stack": stack(gc), "battle": {k: bs.get(k) for k in ("inBattle", "phase", "side", "turn")},
                            "coop_dialog_info": gc.cmd({"cmd": "coop_dialog_info"}), "get_coop": gc.cmd({"cmd": "get_coop"}),
                            "lobby_state": lobby(gc), "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE G: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def bring_up(host, client):
    """FX6-2: PF.start_pvp_campaign's steps up to "START CAMPAIGN shown", copied. Returns the rows (FX6-3)."""
    host.ok({"cmd": "open_new_game", "mode": "coop"})
    host.wait_for("difficulty", lambda: session.has_state(host, "NewGameState"))
    host.ok({"cmd": "newgame_ok"})
    host.wait_for("host window", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": KEY, "player": "HostPlayer"})
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"))
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    client.wait_for("client lobby", lambda: session.has_state(client, "LobbyMenu"), timeout=LOBBY_S)
    for gc in (host, client):
        gc.wait_for("join popup", lambda gc=gc: session.has_state(gc, "Profile"))
        gc.ok({"cmd": "profile_ok"})
    host.wait_for("start eligible", lambda: lobby(host).get("startEligible") or None)
    host.wait_for("START CAMPAIGN shown", lambda: lobby(host).get("buttonVisible") or None, timeout=10)
    return {"HOST": PF.row_for(host, "HostPlayer"), "CLIENT": PF.row_for(host, "ClientPlayer")}


def refused_row(row, host, client, rows, setup, chosen, want_gm, want_teams):
    """G1 / G2: the setup picks (a reply's gamemode is checked where `need` is given), then the pick a new campaign lobby must
    refuse, and the row's three cells."""
    names = [f"{row}-mode", f"{row}-dialog", f"{row}-ok"]
    ev, t_row = {}, time.time()
    try:
        for who, team, need in setup:
            r, t = pick(host, rows, who, team, ev)
            settle(t)
            if need is not None and (not r.get("ok") or r.get("gamemode") != need):
                why = f"precondition {who} -> {team}: reply {r} (want gamemode {need})"
                if row == "G1":
                    evidence(row, ev)
                    capture_boot(why, host, client)
                raise Blocked(why)
        ev["before"] = {"host": teams(lobby(host), ev), "client": teams(lobby(client), ev),
                        "gamemode": [coop(host).get("gamemode"), coop(client).get("gamemode")]}
        who, team = chosen
        r, t = pick(host, rows, who, team, ev)
        seen, ev["dialogS"] = wait_until(lambda: DIALOG in (top(host) or ""), DIALOG_S)
        ev["hostTop"] = top(host)
        settle(t)
        ev["clientTop"], cc, c_teams = top(client), coop(client), teams(lobby(client), ev)
        st, ws = widgets(host)
        ev["hostWidgets"] = {"state": st, "w": ws}
        btns = [w["text"] for w in ws if w["type"] == "TextButton"]
        texts = [w["text"] for w in ws if w["type"] == "Text"]
        dlg_ok = (bool(seen) and DIALOG in st and btns == ["OK"] and texts.count(TEXT) == 1 and ev["clientTop"] == "LobbyMenu")
        dlg_detail = (f"host top {ev['hostTop']} after {ev['dialogS']} s (want {DIALOG} <= {DIALOG_S:.0f} s); widgets of {st}: "
                      f"buttons {btns} (want ['OK']), texts {texts} (want one == {TEXT!r}); client top {ev['clientTop']} "
                      f"(want LobbyMenu)")
        if seen:
            shown, ev["okShownS"] = wait_until(lambda: any(w["type"] == "TextButton" and w["text"] == "OK" and w["visible"]
                                                           and not w["hidden"] for w in widgets(host)[1]), OK_S)
            rc = host.cmd({"cmd": "click_widget", "match": "OK"})
            ev["click"] = {k: rc.get(k) for k in ("ok", "error", "text")}
            back, ev["lobbyBackS"] = wait_until(lambda: top(host) == "LobbyMenu", OK_S)
            time.sleep(READ_S)
            hl = lobby(host)
            ev["afterOk"] = {"stack": stack(host), "lobby": hl}
            hl_teams = teams(hl, ev)
            ok_ok = (bool(shown) and rc.get("ok") is True and bool(back) and hl.get("buttonVisible") is True
                     and hl.get("buttonText") == "START CAMPAIGN" and hl_teams == ev["before"]["host"])
            ok_detail = (f"OK shown {bool(shown)} after {ev['okShownS']} s; click_widget {ev['click']}; host top LobbyMenu "
                         f"{bool(back)} after {ev['lobbyBackS']} s (want <= {OK_S:.0f} s); 1.5 s later buttonVisible "
                         f"{hl.get('buttonVisible')} buttonText {hl.get('buttonText')!r} (want True 'START CAMPAIGN'); host "
                         f"teams {hl_teams} (want unchanged {ev['before']['host']})")
        hc, h_teams = coop(host), teams(lobby(host), ev)
        ev["after"] = {"host": {"coop": hc, "teams": h_teams, "stack": stack(host)},
                       "client": {"coop": cc, "teams": c_teams, "stack": stack(client)}}
        cell(f"{row}-mode", r.get("ok") is True and r.get("gamemode") == want_gm and hc.get("gamemode") == want_gm
             and cc.get("gamemode") == want_gm and h_teams == want_teams and c_teams == want_teams,
             f"reply ok {r.get('ok')} gamemode {r.get('gamemode')}; get_coop.gamemode host {hc.get('gamemode')} client "
             f"{cc.get('gamemode')} (want {want_gm}); playerTeams [ClientPlayer, HostPlayer] host {h_teams} client {c_teams} "
             f"(want {want_teams})")
        cell(f"{row}-dialog", dlg_ok, dlg_detail)
        if seen:
            cell(f"{row}-ok", ok_ok, ok_detail)
        else:
            block([f"{row}-ok"], f"no dialog ({row}-dialog)")
    except Blocked as e:
        block([n for n in names if n not in {x[0] for x in RESULTS}], str(e))
    ev["wallS"] = round(time.time() - t_row, 1)
    evidence(row, ev)
    row_verdict(row, names)


def row_g3(host, client, rows, crash0):
    """G3 (GUARD): after the refusals the host still starts the campaign (gm2: the host places its base, the client has none)."""
    names = ["G3-start", "G3-common"]
    ev, t_row = {}, time.time()
    try:
        r, t = pick(host, rows, "HOST", "XCOM", ev)
        settle(t)
        if not r.get("ok") or r.get("gamemode") != 2:
            raise Blocked(f"precondition HOST -> XCOM: reply {r} (want gamemode 2)")
        ev["lobby"] = {"host": teams(lobby(host), ev), "client": teams(lobby(client), ev)}
        err = None
        try:
            session.start_campaign_via_button(host)
            host.wait_for("host BuildNewBaseState", lambda: session.has_state(host, "BuildNewBaseState"), timeout=BASE_S)
            rb = host.cmd({"cmd": "place_first_base", "lon": LAND_LON, "lat": LAND_LAT, "name": "XcomBase"})
            ev["base"] = [{k: rb.get(k) for k in ("ok", "error")}]
            if not rb.get("ok"):
                rb = host.cmd({"cmd": "place_first_base", "lon": FALLBACK_BASE[0], "lat": FALLBACK_BASE[1], "name": "XcomBase"})
                ev["base"].append({k: rb.get(k) for k in ("ok", "error")})
            rp = session.press_back_when_shown(host, "host BEGIN", codes=(60, 62))
            ev["begin"] = {k: rp.get(k) for k in ("ok", "code")}
            tb = time.time()
            for gc in (host, client):
                gc.wait_for(f"{gc.name} GeoscapeState top", lambda gc=gc: top(gc) == "GeoscapeState" or None, timeout=GEO_S)
            ev["geoS"] = round(time.time() - tb, 2)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:300]}"
        hc, cc = coop(host), coop(client)
        ev["start"] = {"err": err, "host": {"coop": hc, "stack": stack(host)}, "client": {"coop": cc, "stack": stack(client)}}
        cell("G3-start", err is None and top(host) == "GeoscapeState" and top(client) == "GeoscapeState"
             and hc.get("gamemode") == 2 and cc.get("gamemode") == 2 and cc.get("noBases") is True and hc.get("noBases") is False,
             f"start error {err}; tops host {top(host)} client {top(client)} (want GeoscapeState <= {GEO_S} s, after "
             f"{ev.get('geoS')} s); gamemode host {hc.get('gamemode')} client {cc.get('gamemode')} (want 2); noBases client "
             f"{cc.get('noBases')} host {hc.get('noBases')} (want True / False)")
    except Blocked as e:
        block(["G3-start"], str(e))
    new = sorted(os.path.basename(p) for p in crash_set() - crash0)
    alive = [gc.proc is not None and gc.proc.poll() is None for gc in (host, client)]
    cell("G3-common", not new and all(alive), f"new crash files in the boot {new} (want none); processes alive host {alive[0]} "
         f"client {alive[1]} (want both)")
    ev["wallS"] = round(time.time() - t_row, 1)
    evidence("G3", ev)
    row_verdict("G3", names)


def run(host, client):
    crash0 = crash_set()
    host.spawn(); host.connect(); client.spawn(); client.connect()
    try:
        rows = bring_up(host, client)
    except Exception as e:  # noqa: BLE001
        capture_boot(f"bring-up (FX6-2): {type(e).__name__}: {e}", host, client)
    print(f"[bring-up] rows {rows}; host lobby {lobby(host)}; get_coop host {coop(host)} client {coop(client)}", flush=True)
    refused_row("G1", host, client, rows, [("HOST", "Alien", 3)], ("CLIENT", "Alien"), 3, G1_TEAMS)
    refused_row("G2", host, client, rows, [("HOST", "XCOM", None), ("CLIENT", "Alien", 2)], ("HOST", "Alien"), 2, G2_TEAMS)
    row_g3(host, client, rows, crash0)


def main():
    host = GameClient("host", None, make_user_dir("d250uc6_g_host"))
    client = GameClient("client", None, make_user_dir("d250uc6_g_client"))
    all_cells = ["G1-mode", "G1-dialog", "G1-ok", "G2-mode", "G2-dialog", "G2-ok", "G3-start", "G3-common"]
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
    print(f"\n==== D250-U S-C6 campaign lobby refuses the second Alien pick: {len(RESULTS) - len(fails)}/{len(RESULTS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(all_cells) else 2)


if __name__ == "__main__":
    main()
