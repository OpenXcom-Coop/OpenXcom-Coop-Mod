"""A PvP campaign saved mid-battle by an older version, loaded on the host. A gm2 save (the host plays X-COM, the second
player the aliens) converts on the host's menu load into gm2 seats and resumes for both players through RESUME
CAMPAIGN, then ends as a gm2 battle ends; a gm4 (PvE2) save loads unconverted and RESUME CAMPAIGN shows the PvE2 resume
refusal dialog (test_pve2_resume_refused.py's).

Every resume's START HOST goes through the real host window (host_menu_host), never the host_tcp test command.

Boot gm2_resumes (key 48246, dirs old_pvp_gm2_host / old_pvp_gm2_client2): the host gets
tools/coop_test/fixtures/pvp_gm2_battle.sav, client2 an EMPTY dir. Setup: the host's load_save_menu; the host window,
client2's join, the RESUME button, both inBattle, the host's RESUME (CoopState 60 / 62); resume_gm2's win_cell (every
alien killed by a test command, END TURN, both debriefings, both OKs).
  gm2_load    HostMenu within LOAD_S, no ErrorMessageState; ONE conversion line whose counts == GM2_CONVERT; no refusal
              line
  gm2_resume  both inBattle, phase Active, battleId equal and non-zero; turn / side == GM2_TURN; both tops
              BattlescapeState
  gm2_mode    get_coop.gamemode 2 on both; noBases host false / client2 true; host battle_state.coopGamemode 2
  gm2_seats   both machines: faction 0 == XCOM_IDS on seat 0; faction 1 == ALIEN_IDS on seat 1 without AI;
              originalFaction == faction; no other faction; the two lists equal
  gm2_win     resume_gm2's win_cell (host "Aliens defeated", client2's display-only copy, both back on a clean geoscape,
              no CoopState 994)
  gm2_common  0 new crash files, both processes alive, client2 zero-disk; desyncSeen false and hash_now full EQUAL once
              in battle
Boot pve2_refused (key 48246, after gm2_resumes; dirs old_pvp_pve2_host / old_pvp_pve2_client2): the save is
separate_battle.sav with its ONE body coop_gamemode line 1 -> 4 (CRLF-aware split); the save upgrade on it
(test_old_battle_resume.upgrade_save: upgrade_run, the step the load's upgrade dialog runs), then
refusal_test.to_lobby on the upgraded save and refusal_test.refused_row.
  pve2_refusal  the resume lobby reached; ONE PVE2_LINE and no refusal line in the host log; every sub-cell of
                refusal_test.refused_row (pve2_refused-dialog, -held, -client, -ok, -common) passed
Without the fix: exit 2, 1/7 - FAIL gm2_load, pve2_refusal; gm2_resume, gm2_mode, gm2_seats, gm2_win not reached (the
load was refused); PASS gm2_common. With it: 7/7.

One EVIDENCE line per row, one PASS / FAIL line per cell, one ROW line per row; every row runs after a failure. A
bring-up miss prints ONE CAPTURE line and FAILs the boot's remaining cells "boot". ONE run is the result, no skip path;
exit 0 only when every cell passes, else 2.

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
import test_campaign_resume_gm2 as resume_gm2  # noqa: E402  (row helpers: snap, win_cell)
import test_campaign_resume_roles as RR  # noqa: E402  (pure helpers: capture, stack, top, crash_set, wait, alive)
import test_pve2_resume_refused as refusal_test  # noqa: E402  (to_lobby, refused_row)
import test_old_battle_resume as OB  # noqa: E402  (CONVERT, CONVERT_RE, REFUSAL, upgrade_save)

# ----- fixture values -----
KEY = "48246"
TAGS = {"gm2_resumes": "old_pvp_gm2", "pve2_refused": "old_pvp_pve2"}
GM2_SAVE = os.path.join(HERE, "fixtures", "pvp_gm2_battle.sav")
PVE2_SOURCE = os.path.join(HERE, "fixtures", "separate_battle.sav")
PVE2_SAVE = "old_pvp_pve2.sav"
XCOM_IDS = [1, 2]
ALIEN_IDS = [1000000, 1000001, 1000002, 1000003, 1000004]
GM2_CONVERT = (0, 0, 2, 5, 0, "traditional", "STR_MEDIUM_SCOUT")
GM2_TURN = (1, 0)
PVE2_LINE = "[coop-convert] an older version's mid-battle PvE2 campaign save loaded unconverted"
TITLE_WIN, STUB_FUNDS = resume_gm2.TITLE_WIN, resume_gm2.STUB_FUNDS
LOAD_S, LOG_S, RESUME_S, PRESS_S, TOPS_S = 30, 10, 180, 60, 60
ROWS = {"gm2_resumes": ["gm2_load", "gm2_resume", "gm2_mode", "gm2_seats", "gm2_win", "gm2_common"],
        "pve2_refused": ["pve2_refusal"]}
FIX = {"gm2_load", "gm2_resume", "gm2_mode", "gm2_seats", "gm2_win", "pve2_refusal"}
SUBS = ["pve2_refused-dialog", "pve2_refused-held", "pve2_refused-client", "pve2_refused-ok", "pve2_refused-common"]
stack, top, crash_set, wait, alive = RR.stack, RR.top, RR.crash_set, RR.wait, RR.alive


class FixtureMiss(Exception):
    pass


RESULTS = []          # (cell, ok, detail)
SUB = {}              # refusal_test's sub-cells of row pve2_refused: name -> (ok, detail)


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
    """Spawn and connect both; a miss is a setup failure."""
    try:
        host.spawn(); host.connect(); c2.spawn(); c2.connect()
    except Exception as e:  # noqa: BLE001
        capture_boot(boot, f"spawn / connect: {type(e).__name__}: {str(e)[:300]}", host, c2)


def load(host, c2, ev):
    """The host's load_save_menu; HostMenu or ErrorMessageState <= LOAD_S; then the host log <= LOG_S for a conversion
    or a refusal line. gm2_load. Returns True when HostMenu was reached."""
    host.ok({"cmd": "load_save_menu", "file": os.path.basename(GM2_SAVE)})
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
    bad += [] if got == GM2_CONVERT else [f"{len(conv)} conversion line(s), parsed {got} (want one with {GM2_CONVERT})"]
    bad += [f"refusal line {refused[-1]!r}"] if refused else []
    cell("gm2_load", not bad, "; ".join(bad) or f"HostMenu after {s} s; one conversion line {got}; no refusal")
    return menu


def resume(host, c2, ev):
    """resume_gm2.resume_campaign_battle's steps after its load (the real host window), then the host's RESUME; returns
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
    return bad, [resume_gm2.snap(host), resume_gm2.snap(c2)]


def seats_bad(cen):
    bad = []
    for nm, c in zip(("host", "client2"), cen):
        f0, f1 = [u for u in c if u["faction"] == 0], [u for u in c if u["faction"] == 1]
        bad += ([f"{nm}: faction 0 ids {[u['id'] for u in f0]} (want {XCOM_IDS})"]
                if [u["id"] for u in f0] != XCOM_IDS else [])
        bad += ([f"{nm}: faction 1 ids {[u['id'] for u in f1]} (want {ALIEN_IDS})"]
                if [u["id"] for u in f1] != ALIEN_IDS else [])
        bad += [f"{nm}: unit {u['id']} faction 0 seat {u['coop']} (want 0)" for u in f0 if u["coop"] != 0]
        bad += [f"{nm}: unit {u['id']} faction 1 seat {u['coop']} hasAI {u['hasAI']} (want seat 1, hasAI false)"
                for u in f1 if u["coop"] != 1 or u["hasAI"] is not False]
        bad += [f"{nm}: unit {u['id']} originalFaction {u['originalFaction']} != faction {u['faction']}"
                for u in c if u["originalFaction"] != u["faction"]]
        bad += [f"{nm}: unit {u['id']} faction {u['faction']}" for u in c if u["faction"] not in (0, 1)]
    bad += [f"census host {cen[0]} != client2 {cen[1]}"] if cen[0] != cen[1] else []
    return bad


def win(host, c2, ev):
    """resume_gm2.win_cell through the adapter (resume_gm2's module globals read at call time: "resumed_win" ->
    "gm2_win")."""
    resume_gm2.cell = lambda name, ok, detail: cell("gm2_win" if name == "resumed_win" else name, ok, detail)
    resume_gm2.block = lambda names, why: block(["gm2_win" if n == "resumed_win" else n for n in names], why)
    resume_gm2.win_cell(host, c2, ev)


def row_gm2_resumes(x, ev):
    host, c2 = x["host"], x["client2"]
    spawn("gm2_resumes", host, c2)
    reached = load(host, c2, ev)
    in_battle = False
    if not reached:
        block(ROWS["gm2_resumes"][1:5], "not reached: the load was refused (gm2_load)")
    else:
        try:
            rbad, res = resume(host, c2, ev)
        except Exception as e:  # noqa: BLE001
            cell("gm2_resume", False, f"{type(e).__name__}: {str(e)[:400]}")
            block(ROWS["gm2_resumes"][2:5], "not reached: the resume did not complete (gm2_resume)")
            ev["resumeCapture"] = RR.capture("resume", host, c2)
            in_battle = any(alive(gc) and battle_state(gc).get("inBattle") for gc in (host, c2))
        else:
            in_battle = True
            for nm, s in zip(("host", "client2"), res):
                rbad += [f"{nm} inBattle {s['inBattle']!r} phase {s['phase']!r}"] if s["inBattle"] is not True or s["phase"] != "Active" \
                    else []
                rbad += ([f"{nm} turn / side {(s['turn'], s['side'])} (want {GM2_TURN})"]
                         if (s["turn"], s["side"]) != GM2_TURN else [])
            ids = [s["battleId"] for s in res]
            rbad += [f"battleId host/client2 {ids} (want equal, non-zero)"] if not ids[0] or ids[0] != ids[1] else []
            ev["snap"] = res
            cell("gm2_resume", not rbad, "; ".join(rbad) or f"both inBattle, phase Active, battleId equal; turn / side "
                 f"{GM2_TURN}; both tops BattlescapeState after the host's RESUME")
            cv = [coop(host), coop(c2)]
            ev["coop"] = cv
            mbad = [f"{nm} gamemode {v['gamemode']!r} (want 2)" for nm, v in zip(("host", "client2"), cv) if v["gamemode"] != 2]
            mbad += [f"noBases host / client2 {[cv[0]['noBases'], cv[1]['noBases']]} (want [False, True])"] \
                if [cv[0]["noBases"], cv[1]["noBases"]] != [False, True] else []
            mbad += [f"host battle_state.coopGamemode {res[0]['coopGamemode']!r} (want 2)"] if res[0]["coopGamemode"] != 2 else []
            cell("gm2_mode", not mbad,
                 "; ".join(mbad) or "gamemode 2 on both; noBases host false / client2 true; host coopGamemode 2")
            cen = [units(host), units(c2)]
            ev["census"] = cen
            sbad = seats_bad(cen)
            cell("gm2_seats", not sbad, "; ".join(sbad) or f"both: faction 0 {XCOM_IDS} seat 0, faction 1 {ALIEN_IDS} "
                 "seat 1 without AI, originalFaction == faction, lists equal")
            ev["hashAfterResume"] = resume_gm2.hash_res(host, c2)
            if rbad:
                block(["gm2_win"], "not reached: the resumed battle is not up on both (gm2_resume)")
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
    cell("gm2_common", not cbad, "; ".join(cbad) or "0 new crash files, both alive, client2 zero-disk" + (
        ", desyncSeen false on both, hash_now full EQUAL after RESUME" if in_battle else " (no battle entered)"))


def pve2_save_bytes(data):
    """The PvE2 save: split at the first \\r?\\n---\\r?\\n; in the body ONLY coop_gamemode 1 -> 4 (exactly 1), the
    header 0."""
    m = re.search(rb"\r?\n---\r?\n", data)
    if not m:
        capture_boot("pve2_refused", "the PvE2 save: no separator in the source")
    head, body = data[:m.end()], data[m.end():]
    pat = rb"(?m)^coop_gamemode: 1(\r?)$"
    new, n = re.subn(pat, rb"coop_gamemode: 4\1", body)
    nh = len(re.findall(pat, head))
    if n != 1 or nh != 0:
        capture_boot("pve2_refused", f"the PvE2 save: {n} body replacement(s), {nh} header line(s) (want 1 / 0)")
    return head + new


def row_pve2_refused(x, ev):
    with open(PVE2_SOURCE, "rb") as f:
        data = pve2_save_bytes(f.read())
    with open(os.path.join(x["host"].user_dir, "xcom1", PVE2_SAVE), "wb") as f:
        f.write(data)
    ev["fx"] = {"file": PVE2_SAVE, "bytes": len(data), "crlf": data.count(b"\r\n")}
    host, c2 = x["host"], x["client2"]
    spawn("pve2_refused", host, c2)
    up, save, why = OB.upgrade_save(host, PVE2_SAVE, ev, "pve2")
    if not up:
        capture_boot("pve2_refused", why, host, c2)

    def sub(name, ok, detail):
        SUB[name] = (bool(ok), detail)
    refusal_test.cell = sub
    refusal_test.block = lambda names, why: [sub(n, False, f"blocked: {why}") for n in names if n not in SUB]
    refusal_test.KEY = KEY
    refusal_test.BOOT.update(tag="pve2_refused", captured=False)
    bad = []
    try:
        refusal_test.to_lobby(host, c2, save, ev)
    except refusal_test.FixtureMiss as e:
        bad.append(f"refusal_test.FixtureMiss {str(e)[:200]!r}")
    else:
        try:
            refusal_test.refused_row("pve2_refused", host, c2, x["crash0"], ev)
        except refusal_test.FixtureMiss as e:
            bad.append(f"refused_row: refusal_test.FixtureMiss {str(e)[:200]!r}")
    wait(lambda: any(PVE2_LINE in ln or OB.REFUSAL in ln for ln in log_text(host).splitlines()) or None, LOG_S, 0.25)
    text = log_text(host)
    lines, refused = text.count(PVE2_LINE), [ln.split("\t")[-1] for ln in text.splitlines() if OB.REFUSAL in ln]
    ev["hostLog"] = {"pve2Line": lines, "refusal": refused[-1:]}
    ev["sub"] = SUB
    bad += [f"host log PVE2_LINE x{lines} (want 1)"] if lines != 1 else []
    bad += [f"refusal line {refused[-1]!r}"] if refused else []
    bad += [f"{n} {'missing' if n not in SUB else 'FAIL: ' + SUB[n][1][:300]}" for n in SUBS if not SUB.get(n, (False,))[0]]
    cell("pve2_refusal", not bad, "; ".join(bad) or "resume lobby reached; one PVE2_LINE, no refusal; sub-cells " +
         ", ".join(f"{n} PASS" for n in SUBS))


def run_boot(row, fn):
    """One boot: the host (gm2_resumes: with the fixture) and client2 on an EMPTY dir, the row, then every machine shut
    down."""
    tag = TAGS[row]
    x = {"host": GameClient("host", None,
                            make_user_dir(tag + "_host", saves=(GM2_SAVE,) if row == "gm2_resumes" else ())),
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
    run_boot("gm2_resumes", row_gm2_resumes)
    run_boot("pve2_refused", row_pve2_refused)
    allc = ROWS["gm2_resumes"] + ROWS["pve2_refused"]
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== older PvP / PvE2 campaign battle saves: {len(RESULTS) - len(fails)}/{len(allc)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (FIX cell)' if n in FIX else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(allc) else 2)


if __name__ == "__main__":
    main()
