"""D246-U stage S-C1 - test_old_pvp_battle_resume.py: a PvP campaign saved mid-battle by an OLDER version (the release line,
`main` 651ae44ba) on the rewrite's host. A gm2 save (the host plays X-COM, the second player the aliens) converts on the host's menu
load into the rewrite's gm2 seats and resumes for both players through RESUME CAMPAIGN, then ends as a rewrite gm2 battle ends; a gm4
(PvE2) save loads unconverted and RESUME CAMPAIGN shows D275's dialog (owner D246 (b); QD246-6 (a); Q283-4 (a); D283 (b); r5-T1).

Spec: docs repo rewrite/prompts/d246u_sc_pvp_battle_convert.md section (f) and its ORCHESTRATOR RULINGS (QD246C-1 .. QD246C-7 (a));
R-D250-SC4A-1 (a): every resume's START HOST goes through the real host window (host_menu_host), never the host_tcp lever. Pins:
rewrite/d246u-task0/sc1/CONSTANTS.md (TASK 0 T0-1 .. T0-5: census F16472, negative loads, premise boots P / P4).

Boot C2 (key 48246, dirs d246uc_c2_host / d246uc_c2_client2): the host gets tools/coop_test/fixtures/pvp_gm2_battle.sav, client2 an
EMPTY dir. FX-C2 the host's load_save_menu; FX-C3 the host window, client2's join, the RESUME button, both inBattle, the host's RESUME
(CoopState 60 / 62); FX-C4 GB's win_cell (every alien killed by lever, END TURN, both debriefings, both OKs).
  C2-load    HostMenu within LOAD_S, no ErrorMessageState; ONE conversion line whose counts == C2_CONVERT; no refusal line
  C2-resume  both inBattle, phase Active, battleId equal and non-zero; turn / side == C2_TURN; both tops BattlescapeState
  C2-mode    get_coop.gamemode 2 on both; noBases host false / client2 true; host battle_state.coopGamemode 2
  C2-seats   both machines: faction 0 == C2_X on seat 0; faction 1 == C2_A on seat 1 without AI; originalFaction == faction;
             no other faction; the two lists equal
  C2-win     GB's win_cell (host "Aliens defeated", client2's display-only copy, both back on a clean geoscape, no CoopState 994)
  C2-common  0 new crash files, both processes alive, client2 zero-disk; desyncSeen false and hash_now full EQUAL once in battle
Boot O4 (key 48246, after C2; dirs d246uc_o4_host / d246uc_o4_client2): FX-O4 = separate_battle.sav with its ONE body
coop_gamemode line 1 -> 4 (CRLF-aware split), D283.to_lobby, D283.refused_row.
  O4-refused the resume lobby reached; ONE O4_LINE and no refusal line in the host log; every D283 sub-cell (O4-dialog, O4-held,
             O4-client, O4-ok, O4-common) passed
RED (C1R, the unchanged build): exit 2, 1/7 - FAIL C2-load, O4-refused; C2-resume, C2-mode, C2-seats, C2-win not reached (the
load was refused); PASS C2-common. GREEN (C1G): 7/7.

One EVIDENCE line per row, one PASS / FAIL line per cell, one ROW line per row; every row runs after a failure. A bring-up miss prints
ONE CAPTURE line and FAILs the boot's remaining cells "boot". WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run
is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_old_pvp_battle_resume.py
"""

import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import test_campaign_resume_gm2 as GB  # noqa: E402  (row helpers: snap, win_cell)
import test_campaign_resume_roles as RR  # noqa: E402  (pure helpers: capture, stack, top, crash_set, wait, alive)
import test_pve2_resume_refused as D283  # noqa: E402  (to_lobby, refused_row)
import test_old_battle_resume as OB  # noqa: E402  (CONVERT, CONVERT_RE, REFUSAL)

# ----- pins (docs rewrite/d246u-task0/sc1/CONSTANTS.md) -----
KEY = "48246"
TAGS = {"C2": "d246uc_c2", "O4": "d246uc_o4"}
C2_SAVE = os.path.join(HERE, "fixtures", "pvp_gm2_battle.sav")
O4_SOURCE = os.path.join(HERE, "fixtures", "separate_battle.sav")
O4_SAVE = "d246uc_o4.sav"
C2_X = [1, 2]
C2_A = [1000000, 1000001, 1000002, 1000003, 1000004]
C2_CONVERT = (0, 0, 2, 5, 0, "traditional", "STR_MEDIUM_SCOUT")
C2_TURN = (1, 0)
O4_LINE = "[coop-convert] D246: an older version's mid-battle PvE2 campaign save loaded unconverted"
TITLE_WIN, STUB_FUNDS = GB.TITLE_WIN, GB.STUB_FUNDS
LOAD_S, LOG_S, RESUME_S, PRESS_S, TOPS_S = 30, 10, 180, 60, 60
ROWS = {"C2": ["C2-load", "C2-resume", "C2-mode", "C2-seats", "C2-win", "C2-common"], "O4": ["O4-refused"]}
RED = {"C2-load", "C2-resume", "C2-mode", "C2-seats", "C2-win", "O4-refused"}
SUBS = ["O4-dialog", "O4-held", "O4-client", "O4-ok", "O4-common"]
stack, top, crash_set, wait, alive = RR.stack, RR.top, RR.crash_set, RR.wait, RR.alive


class FixtureMiss(Exception):
    pass


RESULTS = []          # (cell, ok, detail)
SUB = {}              # D283's sub-cells of row O4: name -> (ok, detail)


def cell(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)


def block(names, why):
    for n in names:
        if n not in {x[0] for x in RESULTS}:
            cell(n, False, why)


def capture_boot(boot, err, *machines):
    cap = RR.capture(err, *[gc for gc in machines if gc is not None])
    print(f"CAPTURE {boot}: {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def log_text(gc):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def coop(gc):
    c = gc.cmd({"cmd": "get_coop"})
    return {"gamemode": c.get("gamemode"), "noBases": c.get("noBases")}


def units(gc):
    return sorted(({k: u.get(k) for k in ("id", "faction", "originalFaction", "coop", "hasAI")}
                   for u in battle_state(gc).get("units", [])), key=lambda u: u["id"])


def spawn(boot, host, c2):
    """FX-C1 / FX-O5: spawn and connect both; a miss is a FIXTURE-STOP."""
    try:
        host.spawn(); host.connect(); c2.spawn(); c2.connect()
    except Exception as e:  # noqa: BLE001
        capture_boot(boot, f"spawn / connect: {type(e).__name__}: {str(e)[:300]}", host, c2)


def load(host, c2, ev):
    """FX-C2: the host's load_save_menu; HostMenu or ErrorMessageState <= LOAD_S; then the host log <= LOG_S for a conversion or a
    refusal line. C2-load. Returns True when HostMenu was reached."""
    host.ok({"cmd": "load_save_menu", "file": os.path.basename(C2_SAVE)})
    _, s = wait(lambda: ("HostMenu" in stack(host) or "ErrorMessageState" in stack(host)) or None, LOAD_S, 0.1)
    hs = stack(host)
    menu = "HostMenu" in hs and "ErrorMessageState" not in hs
    wait(lambda: any(OB.CONVERT in ln or OB.REFUSAL in ln for ln in log_text(host).splitlines()) or None, LOG_S, 0.25)
    text = log_text(host)
    conv = [ln.split("\t")[-1] for ln in text.splitlines() if OB.CONVERT in ln]
    refused = [ln.split("\t")[-1] for ln in text.splitlines() if OB.REFUSAL in ln]
    m = OB.CONVERT_RE.search(conv[0]) if len(conv) == 1 else None
    got = (tuple(int(x) for x in m.groups()[:5]) + m.groups()[5:]) if m else None
    ev["load"] = {"s": s, "host": hs, "client2": stack(c2), "convert": conv, "refusal": refused[-1:], "parsed": got}
    bad = [] if menu else [f"host stack {hs} after {s} s (want HostMenu, no ErrorMessageState, within {LOAD_S} s)"]
    bad += [] if got == C2_CONVERT else [f"{len(conv)} conversion line(s), parsed {got} (want one with {C2_CONVERT})"]
    bad += [f"refusal line {refused[-1]!r}"] if refused else []
    cell("C2-load", not bad, "; ".join(bad) or f"HostMenu after {s} s; one conversion line {got}; no refusal")
    return menu


def resume(host, c2, ev):
    """FX-C3: GB.resume_campaign_battle's steps after its load (the real host window), then the host's RESUME; returns
    (problems, [host snap, client2 snap]); raises on a step past its bound."""
    t0 = time.time()
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv", "port": KEY, "player": "HostPlayer"})
    host.wait_for("resume lobby", lambda: session.has_state(host, "LobbyMenu"))
    ls = host.ok({"cmd": "lobby_state"})
    assert ls["lobbyMode"] == 2, f"expected the resume lobby (lobbyMode 2), got {ls}"
    c2.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    c2.wait_for("client2 resume lobby", lambda: session.has_state(c2, "LobbyMenu"))
    session.resume_campaign_via_button(host, "ClientPlayer")
    both, s = wait(lambda: battle_state(host).get("inBattle") and battle_state(c2).get("inBattle"), RESUME_S, 1.0)
    if not both:
        raise TimeoutError(f"both inBattle not within {RESUME_S} s: host {stack(host)} / client2 {stack(c2)}")
    ev["press"] = session.press_back_when_shown(host, "host RESUME", codes=(60, 62), timeout=PRESS_S)
    tok, ts = wait(lambda: top(host) == "BattlescapeState" and top(c2) == "BattlescapeState", TOPS_S)
    ev["resume"] = {"inBattleS": s, "topsS": ts, "s": round(time.time() - t0, 2)}
    bad = [] if tok else [f"tops host/client2 {[top(host), top(c2)]} (want BattlescapeState within {TOPS_S} s of RESUME)"]
    return bad, [GB.snap(host), GB.snap(c2)]


def seats_bad(cen):
    bad = []
    for nm, c in zip(("host", "client2"), cen):
        f0, f1 = [u for u in c if u["faction"] == 0], [u for u in c if u["faction"] == 1]
        bad += [f"{nm}: faction 0 ids {[u['id'] for u in f0]} (want {C2_X})"] if [u["id"] for u in f0] != C2_X else []
        bad += [f"{nm}: faction 1 ids {[u['id'] for u in f1]} (want {C2_A})"] if [u["id"] for u in f1] != C2_A else []
        bad += [f"{nm}: unit {u['id']} faction 0 seat {u['coop']} (want 0)" for u in f0 if u["coop"] != 0]
        bad += [f"{nm}: unit {u['id']} faction 1 seat {u['coop']} hasAI {u['hasAI']} (want seat 1, hasAI false)"
                for u in f1 if u["coop"] != 1 or u["hasAI"] is not False]
        bad += [f"{nm}: unit {u['id']} originalFaction {u['originalFaction']} != faction {u['faction']}"
                for u in c if u["originalFaction"] != u["faction"]]
        bad += [f"{nm}: unit {u['id']} faction {u['faction']}" for u in c if u["faction"] not in (0, 1)]
    bad += [f"census host {cen[0]} != client2 {cen[1]}"] if cen[0] != cen[1] else []
    return bad


def win(host, c2, ev):
    """FX-C4: GB.win_cell through the adapter (GB's module globals read at call time: "P3-win" -> "C2-win")."""
    GB.cell = lambda name, ok, detail: cell("C2-win" if name == "P3-win" else name, ok, detail)
    GB.block = lambda names, why: block(["C2-win" if n == "P3-win" else n for n in names], why)
    GB.win_cell(host, c2, ev)


def row_c2(x, ev):
    host, c2 = x["host"], x["client2"]
    spawn("C2", host, c2)
    reached = load(host, c2, ev)
    in_battle = False
    if not reached:
        block(ROWS["C2"][1:5], "not reached: the load was refused (C2-load)")
    else:
        try:
            rbad, res = resume(host, c2, ev)
        except Exception as e:  # noqa: BLE001
            cell("C2-resume", False, f"{type(e).__name__}: {str(e)[:400]}")
            block(ROWS["C2"][2:5], "not reached: the resume did not complete (C2-resume)")
            ev["resumeCapture"] = RR.capture("resume", host, c2)
            in_battle = any(alive(gc) and battle_state(gc).get("inBattle") for gc in (host, c2))
        else:
            in_battle = True
            for nm, s in zip(("host", "client2"), res):
                rbad += [f"{nm} inBattle {s['inBattle']!r} phase {s['phase']!r}"] if s["inBattle"] is not True or s["phase"] != "Active" \
                    else []
                rbad += [f"{nm} turn / side {(s['turn'], s['side'])} (want {C2_TURN})"] if (s["turn"], s["side"]) != C2_TURN else []
            ids = [s["battleId"] for s in res]
            rbad += [f"battleId host/client2 {ids} (want equal, non-zero)"] if not ids[0] or ids[0] != ids[1] else []
            ev["snap"] = res
            cell("C2-resume", not rbad, "; ".join(rbad) or f"both inBattle, phase Active, battleId equal; turn / side {C2_TURN}; both "
                 "tops BattlescapeState after the host's RESUME")
            cv = [coop(host), coop(c2)]
            ev["coop"] = cv
            mbad = [f"{nm} gamemode {v['gamemode']!r} (want 2)" for nm, v in zip(("host", "client2"), cv) if v["gamemode"] != 2]
            mbad += [f"noBases host / client2 {[cv[0]['noBases'], cv[1]['noBases']]} (want [False, True])"] \
                if [cv[0]["noBases"], cv[1]["noBases"]] != [False, True] else []
            mbad += [f"host battle_state.coopGamemode {res[0]['coopGamemode']!r} (want 2)"] if res[0]["coopGamemode"] != 2 else []
            cell("C2-mode", not mbad, "; ".join(mbad) or "gamemode 2 on both; noBases host false / client2 true; host coopGamemode 2")
            cen = [units(host), units(c2)]
            ev["census"] = cen
            sbad = seats_bad(cen)
            cell("C2-seats", not sbad, "; ".join(sbad) or f"both: faction 0 {C2_X} seat 0, faction 1 {C2_A} seat 1 without AI, "
                 "originalFaction == faction, lists equal")
            ev["hashAfterResume"] = GB.hash_res(host, c2)
            if rbad:
                block(["C2-win"], "not reached: the resumed battle is not up on both (C2-resume)")
            else:
                win(host, c2, ev)
    new = sorted(os.path.basename(p) for p in crash_set() - x["crash0"])
    cbad = [f"new crash files {new}"] if new else []
    cbad += [f"processes alive host/client2 {[alive(host), alive(c2)]}"] if not (alive(host) and alive(c2)) else []
    cbad += [f"client2 zero-disk: {session.save_files(c2.user_dir)}"] if session.save_files(c2.user_dir) else []
    if in_battle:
        ds = [event_state(gc).get("desyncSeen") for gc in (host, c2)]
        cbad += [f"desyncSeen host/client2 {ds} (want [False, False])"] if ds != [False, False] else []
        cbad += [f"after RESUME: {ev.get('hashAfterResume', 'not reached')}"] if ev.get("hashAfterResume") != "EQUAL" else []
    cell("C2-common", not cbad, "; ".join(cbad) or "0 new crash files, both alive, client2 zero-disk" + (
        ", desyncSeen false on both, hash_now full EQUAL after RESUME" if in_battle else " (no battle entered)"))


def fx_o4(data):
    """FX-O4 (F16487): split at the first \\r?\\n---\\r?\\n; in the body ONLY coop_gamemode 1 -> 4 (exactly 1), the header 0."""
    m = re.search(rb"\r?\n---\r?\n", data)
    if not m:
        capture_boot("O4", "FX-O4: no separator in the source")
    head, body = data[:m.end()], data[m.end():]
    pat = rb"(?m)^coop_gamemode: 1(\r?)$"
    new, n = re.subn(pat, rb"coop_gamemode: 4\1", body)
    nh = len(re.findall(pat, head))
    if n != 1 or nh != 0:
        capture_boot("O4", f"FX-O4: {n} body replacement(s), {nh} header line(s) (want 1 / 0)")
    return head + new


def row_o4(x, ev):
    with open(O4_SOURCE, "rb") as f:
        data = fx_o4(f.read())
    with open(os.path.join(x["host"].user_dir, "xcom1", O4_SAVE), "wb") as f:
        f.write(data)
    ev["fx"] = {"file": O4_SAVE, "bytes": len(data), "crlf": data.count(b"\r\n")}
    host, c2 = x["host"], x["client2"]
    spawn("O4", host, c2)

    def sub(name, ok, detail):
        SUB[name] = (bool(ok), detail)
    D283.cell = sub
    D283.block = lambda names, why: [sub(n, False, f"blocked: {why}") for n in names if n not in SUB]
    D283.KEY = KEY
    D283.BOOT.update(tag="O4", captured=False)
    bad = []
    try:
        D283.to_lobby(host, c2, O4_SAVE, ev)
    except D283.FixtureMiss as e:
        bad.append(f"D283.FixtureMiss {str(e)[:200]!r}")
    else:
        try:
            D283.refused_row("O4", host, c2, x["crash0"], ev)
        except D283.FixtureMiss as e:
            bad.append(f"refused_row: D283.FixtureMiss {str(e)[:200]!r}")
    wait(lambda: any(O4_LINE in ln or OB.REFUSAL in ln for ln in log_text(host).splitlines()) or None, LOG_S, 0.25)
    text = log_text(host)
    lines, refused = text.count(O4_LINE), [ln.split("\t")[-1] for ln in text.splitlines() if OB.REFUSAL in ln]
    ev["hostLog"] = {"o4Line": lines, "refusal": refused[-1:]}
    ev["sub"] = SUB
    bad += [f"host log O4_LINE x{lines} (want 1)"] if lines != 1 else []
    bad += [f"refusal line {refused[-1]!r}"] if refused else []
    bad += [f"{n} {'missing' if n not in SUB else 'FAIL: ' + SUB[n][1][:300]}" for n in SUBS if not SUB.get(n, (False,))[0]]
    cell("O4-refused", not bad, "; ".join(bad) or "resume lobby reached; one O4_LINE, no refusal; sub-cells " +
         ", ".join(f"{n} PASS" for n in SUBS))


def run_boot(row, fn):
    """One boot: the host (C2: with the fixture) and client2 on an EMPTY dir, the row, then every machine shut down."""
    tag = TAGS[row]
    x = {"host": GameClient("host", None, make_user_dir(tag + "_host", saves=(C2_SAVE,) if row == "C2" else ())),
         "client2": GameClient("client2", None, make_user_dir(tag + "_client2")), "crash0": crash_set()}
    ev, t0 = {}, time.time()
    try:
        fn(x, ev)
    except FixtureMiss as e:
        block(ROWS[row], f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"[ERROR] boot {row}: {err}", flush=True)
        print(f"CAPTURE {row}: {json.dumps(RR.capture(err, x['host'], x['client2']), sort_keys=True, default=str)}", flush=True)
        block(ROWS[row], f"boot (error {err[:200]})")
    finally:
        ev["wall"] = round(time.time() - t0, 1)
        print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
        bad = [n for n, ok, _ in RESULTS if n in ROWS[row] and not ok]
        print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)
        for gc in (x["client2"], x["host"]):
            try:
                if gc.proc is not None and gc.proc.poll() is None:
                    gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)


def main():
    t0 = time.time()
    run_boot("C2", row_c2)
    run_boot("O4", row_o4)
    allc = ROWS["C2"] + ROWS["O4"]
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== D246-U S-C1 older PvP / PvE2 campaign battle saves: {len(RESULTS) - len(fails)}/{len(allc)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (expected red)' if n in RED else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(allc) else 2)


if __name__ == "__main__":
    main()
