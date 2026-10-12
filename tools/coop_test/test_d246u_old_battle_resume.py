"""D246-U stage S-A rows RS and L1: a SEPARATE co-op campaign saved mid-battle by an OLDER version (the release line,
`main` 651ae44ba) loads on the rewrite's host without the FW-7 refusal and resumes for both players (owner D246 (b);
FW-7 narrowed; D-22, D-26 narrowed by QD246-3 (a), D99, D100 / D-23, D235-VL2, D248, aud-E1-15).

Spec: docs repo rewrite/prompts/d246u_midbattle_save_convert.md section (f) test_d246u_old_battle_resume.py (QD246-1 ..
QD246-9 (a), orchestrator rulings 2026-10-12). Constants: rewrite/d246u-task0/sa/CONSTANTS.md (TASK 0 T0-3 .. T0-6).
Fixture: tools/coop_test/fixtures/d246u_separate_battle.sav, made by the release build's own
test_coop_resume_battle_control.py on the main-check worktree (T0-3), committed unedited.

Boot RS (key 46610, dirs d246u_rs_*): the host gets the fixture, the client an EMPTY dir.
  RS-load    host load_save_menu -> HostMenu within 60 s, no ErrorMessageState (red: ErrorMessageState and the refusal
             text "different version of the mod" in the host log, in EVIDENCE)
  RS-log     exactly one "[coop-convert] D246: an older version's mid-battle co-op save converted" line whose counts are
             RS_PB / RS_PM / RS_SEATS / RS_UNSEATED, turnMode traditional, deployment DEP_RS
  RS-resume  session.resume_campaign_battle's post-load steps (F13303) on key 46610: both inBattle, phase Active,
             authority.battleId equal and non-zero
  RS-hash    the host log has "battle_ready saveBlob EQUAL" and no MISMATCH; desyncSeen false on both
  RS-seats   the (name, seat) set == RS_EXPECT on both (rc.assert_split); every non-player original faction has coop -1
  RS-mode    turnMode "traditional" and coopEndTurnTally.activeSeat 0 on both (D100 / D-23: the host's go)
  RS-deploy  deployment / strTarget / strCraftOrBase == DEP_RS / TGT_RS / COB_RS on both
  RS-click   the host's RESUME (CoopState 60 / 62); both tops BattlescapeState; no HostMenu / LobbyMenu
  RS-go      the client's turn order for its guest is refused not_your_go; the guest's facing unchanged on both
  RS-pass    the host's END TURN -> coopEndTurnTally.activeSeat 1 on both; side 0 and turn unchanged
  RS-cmd     session.assert_t_cmd(RS_GUEST, RS_HOST0, host_check=False)
  RS-common  every hash bucket EQUAL, desyncSeen false on both, no new lane crash file, the client wrote no save
Boot L1 (host only, dir d246u_l1_host): the SEPARATE fixture with its ONE coop_parallel_turns line removed (the v2.0.6
shape, line endings kept, asserted).
  L1-load    as RS-load
  L1-mode    event_state.turnMode "traditional" on the host; the conversion line says turnMode traditional
  L1-common  desyncSeen false on the host, no new lane crash file (no client in this boot)

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure; a
cell whose precondition failed FAILs "not reached". A boot step past its bound prints ONE CAPTURE line and fails the
boot's rows "boot". WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip
path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_d246u_old_battle_resume.py
"""

import contextlib
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, assert_hash_clean  # noqa: E402
import test_coop_resume_battle_control as rc  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "d246u_separate_battle.sav")
RS_KEY = "46610"
HOST_NAME, CLIENT_NAME = "HostPlayer", "ClientPlayer"          # the save's coopPlayers (T0-5)
RS_EXPECT = {"Erno Bartok": 0, "Robin Berggren": 0, "Lyris Kollias": 0, "Guest Zzz": 1}
RS_SEATS = (3, 1)                 # seated 0 / seated 1 by E4 (1)'s rule (T0-5)
RS_UNSEATED = 25                  # 14 aliens + 11 civilians, each saved with coop 0 (T0-5)
RS_PB, RS_PM = 0, 0               # partner world: battle snapshots / droppable mirrors (T0-5 row 6)
DEP_RS = "STR_TERROR_MISSION"
TGT_RS, COB_RS = "TERROR SITE-1", "BASE> HostBase"
RS_GUEST, RS_HOST0 = 9, 1         # the guest's battle unit / Erno Bartok's
LOAD_S, LOG_S, RESUME_S, MODE_S, CLICK_S, DENY_S, PASS_S = 60, 10, 180, 10, 60, 15, 30
CONVERT = "[coop-convert] D246: an older version's mid-battle co-op save converted"
CONVERT_RE = re.compile(r"partner worlds: battle snapshots (\d+), mirrors (\d+); seats 0/1 (\d+)/(\d+), "
                        r"unseated (\d+); turnMode (\w+); deployment \"([^\"]*)\"")
REFUSAL = "different version of the mod"
N_EQUAL = "battle_ready saveBlob EQUAL"
N_MISMATCH = "battle_ready saveBlob MISMATCH"
RS_CELLS = ("RS-load", "RS-log", "RS-resume", "RS-hash", "RS-seats", "RS-mode", "RS-deploy", "RS-click", "RS-go",
            "RS-pass", "RS-cmd", "RS-common")
L1_CELLS = ("L1-load", "L1-mode", "L1-common")


class Miss(Exception):
    """A boot step past its bound (its CAPTURE line is already printed)."""


class NotReached(Exception):
    """A precondition cell failed: every cell not yet decided FAILs "not reached"."""


def stack(gc):
    return session.states_stripped(gc)


def log_text(gc):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def es(gc, key):
    return event_state(gc).get(key)


def bview(gc):
    b = battle_state(gc)
    return {k: b.get(k) for k in ("phase", "inBattle", "side", "turn", "authority")}


def capture(tag, err, machines):
    """ONE CAPTURE line: each machine's stack, battle_state view, coop_dialog_info and its last 40 engine log lines."""
    cap = {}
    for gc in machines:
        d = {}
        for k, fn in (("stack", stack), ("battle", bview), ("dialog", lambda g: g.cmd({"cmd": "coop_dialog_info"})),
                      ("logTail", lambda g: log_text(g).splitlines()[-40:])):
            try:
                d[k] = fn(gc)
            except Exception as e:
                d[k] = f"probe failed: {type(e).__name__}: {e}"
        cap[gc.name] = d
    print(f"CAPTURE {tag}: missed {err}; {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def boot(tag, machines):
    """Spawn and connect every machine; a miss prints ONE CAPTURE line and raises Miss."""
    try:
        for gc in machines:
            gc.spawn()
        for gc in machines:
            gc.connect()
    except Exception as e:
        capture(tag, f"{type(e).__name__}: {str(e)[:600]}", machines)
        raise Miss(tag)


def shut(*gcs):
    for gc in gcs:
        try:
            if gc is not None and gc.proc is not None and gc.proc.poll() is None:
                gc.shutdown()
        except Exception as e:
            print(f"[d246u] shutdown {gc.name}: {type(e).__name__}: {str(e)[:200]}", flush=True)


def wait_until(pred, timeout, interval=0.2):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = pred()
        if v:
            return v, round(time.time() - t0, 2)
        time.sleep(interval)
    return None, round(time.time() - t0, 2)


def verdict(row, order, cells, ev):
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    fails = 0
    for name in order:
        ok, detail = cells.get(name, (False, f"not reached: {ev.get('error')}"))
        fails += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)
    print(f"{row} {'PASS' if not fails else 'FAIL'} ({fails} of {len(order)} cells failed)", flush=True)
    return fails


def run_row(row, order, fn):
    """One row: `fn(cells, ev)` fills both; an exception fails every cell it did not reach."""
    cells, ev = {}, {}
    try:
        fn(cells, ev)
    except NotReached as e:
        ev["error"] = str(e)
    except Exception as e:
        ev["error"] = f"{type(e).__name__}: {str(e)[:600]}"
    return verdict(row, order, cells, ev)


def fail_all(rows, why):
    return sum(verdict(row, order, {n: (False, why) for n in order}, {"error": why}) for row, order in rows)


def need(cells, name):
    if not cells.get(name, (False,))[0]:
        raise NotReached(f"{name} failed")


def attempt(cells, name, fn, machines=None):
    """Run one cell's action; an exception FAILs that cell with the error (the row goes on). With `machines`, a
    failure also prints ONE CAPTURE line (R7)."""
    try:
        cells[name] = fn()
    except Exception as e:
        cells[name] = (False, f"{type(e).__name__}: {str(e)[:500]}")
    if machines and not cells[name][0]:
        capture(name, cells[name][1][:300], machines)


def quiet(fn, ev=None, key=None):
    """Run a helper that prints its own PASS lines with stdout captured (only cell lines say PASS); its last printed
    lines go to ev[key], also when it raises."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            return fn()
    finally:
        if ev is not None:
            ev[key] = buf.getvalue().strip().splitlines()[-4:]


def derive(src, dst, prefix, new_line):
    """Copy `src` to `dst` with the ONE line starting `prefix` removed (new_line None) or replaced (bytes), keeping
    the line endings; returns the replaced line. Asserts exactly one such line."""
    with open(src, "rb") as f:
        lines = f.read().split(b"\n")
    hits = [i for i, ln in enumerate(lines) if ln.startswith(prefix)]
    assert len(hits) == 1, f"{os.path.basename(src)}: {len(hits)} lines start {prefix!r} (want 1)"
    old = lines[hits[0]]
    if new_line is None:
        del lines[hits[0]]
    else:
        lines[hits[0]] = new_line + (b"\r" if old.endswith(b"\r") else b"")
    with open(dst, "wb") as f:
        f.write(b"\n".join(lines))
    return old


def load_cell(host, save, ev, tag):
    """host load_save_menu -> HostMenu within LOAD_S and no ErrorMessageState."""
    t0 = time.time()
    host.ok({"cmd": "load_save_menu", "file": save})
    seen = {}

    def landed():
        seen["stack"] = stack(host)
        return ("HostMenu" in seen["stack"] or "ErrorMessageState" in seen["stack"]) or None
    wait_until(landed, LOAD_S, 0.1)
    st = seen.get("stack") or []
    ev[f"{tag}Load"] = {"s": round(time.time() - t0, 2), "stack": st}
    ok = "HostMenu" in st and "ErrorMessageState" not in st
    if not ok:
        time.sleep(3)   # log flush before the evidence read
        text = log_text(host)
        ev[f"{tag}Refusal"] = REFUSAL in text
        ev[f"{tag}LogErrors"] = [ln for ln in text.splitlines() if "[ERROR]" in ln][-3:]
    return ok, f"host stack {st} after {ev[f'{tag}Load']['s']} s (want HostMenu, no ErrorMessageState)"


def convert_line(host):
    """The host log's conversion lines after a bounded wait (LOG_S)."""
    lines, _ = wait_until(lambda: [ln for ln in log_text(host).splitlines() if CONVERT in ln], LOG_S, 0.25)
    return lines or []


def log_cell(host, ev, tag, want):
    """Exactly one conversion line whose counts / mode / deployment equal `want`."""
    lines = convert_line(host)
    ev[f"{tag}Convert"] = lines
    m = CONVERT_RE.search(lines[0]) if len(lines) == 1 else None
    got = None
    if m:
        g = m.groups()
        got = (int(g[0]), int(g[1]), int(g[2]), int(g[3]), int(g[4]), g[5], g[6])
    return (got == want, f"{len(lines)} conversion line(s), parsed {got} (want one line with (battle snapshots, "
                         f"mirrors, seated0, seated1, unseated, turnMode, deployment) = {want})")


def resume_loaded(host, client, key, ev, tag):
    """session.resume_campaign_battle's steps after its own load_save_menu (session.py: host_tcp, the resume lobby
    with lobbyMode 2, join_tcp, the REAL RESUME button, both inBattle, bounded RESUME_S) on the ONE load the -load
    cell made (F13303: calling the helper would load the save a second time while its lobby commands run)."""
    host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": key, "player": HOST_NAME})
    host.wait_for("resume lobby", lambda: session.has_state(host, "LobbyMenu"), timeout=60)
    ls = host.ok({"cmd": "lobby_state"})
    ev[f"{tag}LobbyMode"] = ls.get("lobbyMode")
    assert ls.get("lobbyMode") == 2, f"expected the resume lobby (lobbyMode 2), got {ls}"
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": CLIENT_NAME})
    client.wait_for("client resume lobby", lambda: session.has_state(client, "LobbyMenu"), timeout=60)
    session.resume_campaign_via_button(host, CLIENT_NAME)
    both, s = wait_until(lambda: battle_state(host).get("inBattle") and battle_state(client).get("inBattle"),
                         RESUME_S, 1.0)
    ev[f"{tag}InBattleS"] = s
    views = [bview(host), bview(client)]
    ev[f"{tag}AfterResume"] = views
    ids = [(v.get("authority") or {}).get("battleId") for v in views]
    ok = (bool(both) and all(v.get("inBattle") and v.get("phase") == "Active" for v in views)
          and bool(ids[0]) and ids[0] == ids[1])
    return ok, (f"inBattle host/client {[v.get('inBattle') for v in views]} after {s} s, phase "
                f"{[v.get('phase') for v in views]} (want Active), battleId {ids} (want equal, non-zero)")


def hash_cell(host, client, ev, tag):
    text = log_text(host)
    eq, mism = text.count(N_EQUAL), text.count(N_MISMATCH)
    ds = [es(host, "desyncSeen"), es(client, "desyncSeen")]
    ev[f"{tag}Ready"] = {"equal": eq, "mismatch": mism}
    return (eq >= 1 and mism == 0 and ds == [False, False],
            f"host log '{N_EQUAL}' x{eq} (want >= 1), MISMATCH x{mism} (want 0); desyncSeen {ds} (want False/False)")


def seats_cell(host, client, ev, tag, expect):
    try:
        quiet(lambda: rc.settle_and_assert(host, client, tag, expect, timeout=30))
        split = "rc.assert_split: (name, seat) set, phase, hostSim, localSeat, battleId, coopSession all as expected"
        split_ok = True
    except AssertionError as e:
        split, split_ok = str(e)[:700], False
    bad = {}
    for gc in (host, client):
        bad[gc.name] = sorted(u["id"] for u in battle_state(gc).get("units", [])
                              if u.get("originalFaction") != 0 and u.get("coop") != -1)
    ev[f"{tag}SeatedNonPlayer"] = bad
    return (split_ok and not any(bad.values()),
            f"{split}; non-player original factions with coop != -1 host/client {bad} (want none)")


def deploy_cell(host, client, ev, tag, want):
    got = []
    for gc in (host, client):
        b = battle_state(gc)
        got.append((b.get("deployment"), b.get("strTarget"), b.get("strCraftOrBase")))
    ev[f"{tag}Deploy"] = got
    return (got == [want, want], f"(deployment, strTarget, strCraftOrBase) host/client {got} (want {want} on both)")


def click_cell(host, client, ev, tag):
    session.press_back_when_shown(host, "host RESUME", codes=(60, 62))
    tops, s = wait_until(lambda: all(session.top_state(gc) == "BattlescapeState" for gc in (host, client)),
                         CLICK_S, 0.25)
    sts = [stack(host), stack(client)]
    ev[f"{tag}Click"] = {"s": s, "stacks": sts}
    left = [[x for x in st if x in ("HostMenu", "LobbyMenu")] for st in sts]
    return (bool(tops) and left == [[], []],
            f"tops {[st[-1] if st else None for st in sts]} after {s} s (want BattlescapeState on both); "
            f"HostMenu / LobbyMenu left host/client {left} (want none)")


def common_cell(host, client, crash0, ev, tag):
    try:
        assert_hash_clean(host, client, full=True, what=f"{tag}-common")
        hashed = "all buckets EQUAL"
    except AssertionError as e:
        hashed = str(e)[:400]
    ds = [es(host, "desyncSeen"), es(client, "desyncSeen")]
    crash = sorted(session._crash_log_snapshot() - crash0)
    try:
        session.assert_client_zero_disk(client.user_dir)
        disk = "client wrote no save"
    except AssertionError as e:
        disk = str(e)[:200]
    ev[f"{tag}Common"] = {"hash": hashed, "desync": ds, "crash": crash, "disk": disk}
    return (hashed == "all buckets EQUAL" and ds == [False, False] and not crash and disk == "client wrote no save",
            f"hash {hashed}; desyncSeen {ds} (want False/False); new crash files {crash} (want none); {disk}")


def tally_seat(gc):
    return (es(gc, "coopEndTurnTally") or {}).get("activeSeat")


def row_rs(host, client, crash0, cells, ev):
    save = os.path.basename(FIXTURE)
    cells["RS-load"] = load_cell(host, save, ev, "rs")
    need(cells, "RS-load")
    cells["RS-log"] = log_cell(host, ev, "rs", (RS_PB, RS_PM, RS_SEATS[0], RS_SEATS[1], RS_UNSEATED, "traditional",
                                                DEP_RS))
    attempt(cells, "RS-resume", lambda: resume_loaded(host, client, RS_KEY, ev, "rs"), (host, client))
    need(cells, "RS-resume")
    cells["RS-hash"] = hash_cell(host, client, ev, "rs")
    cells["RS-seats"] = seats_cell(host, client, ev, "RS", RS_EXPECT)

    def mode():
        return ([es(gc, "turnMode") for gc in (host, client)] == ["traditional"] * 2
                and [tally_seat(gc) for gc in (host, client)] == [0, 0])
    wait_until(mode, MODE_S)
    got = {gc.name: (es(gc, "turnMode"), es(gc, "coopEndTurnTally")) for gc in (host, client)}
    ev["rsMode"] = got
    cells["RS-mode"] = (mode(), f"(turnMode, coopEndTurnTally) {got} (want traditional, activeSeat 0 on both)")
    cells["RS-deploy"] = deploy_cell(host, client, ev, "rs", (DEP_RS, TGT_RS, COB_RS))
    attempt(cells, "RS-click", lambda: click_cell(host, client, ev, "rs"), (host, client))
    need(cells, "RS-click")

    def go():
        d0 = [session.unit_of(gc, RS_GUEST).get("direction") for gc in (host, client)]
        to = (d0[1] + 1) % 8
        r = session.send_turn(client, RS_GUEST, to)

        def denied():
            ld = es(client, "lastDeny") or {}
            return ld if ld.get("reason") and (not r.get("iseq") or ld.get("iseq") == r.get("iseq")) else None
        deny, s = wait_until(denied, DENY_S, 0.1)
        d1 = [session.unit_of(gc, RS_GUEST).get("direction") for gc in (host, client)]
        ev["rsGo"] = {"dir0": d0, "to": to, "resp": {k: r.get(k) for k in ("ok", "iseq", "error")}, "deny": deny,
                      "s": s, "dir1": d1}
        return ((deny or {}).get("reason") == "not_your_go" and d1 == d0,
                f"client lastDeny {deny} after {s} s (want reason not_your_go); guest {RS_GUEST} facing host/client "
                f"{d0} -> {d1} (want unchanged)")
    attempt(cells, "RS-go", go)

    def pas():
        b0 = [(battle_state(gc).get("side"), battle_state(gc).get("turn")) for gc in (host, client)]
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        ok, s = wait_until(lambda: [tally_seat(gc) for gc in (host, client)] == [1, 1], PASS_S, 0.2)
        b1 = [(battle_state(gc).get("side"), battle_state(gc).get("turn")) for gc in (host, client)]
        seats = [tally_seat(gc) for gc in (host, client)]
        ev["rsPass"] = {"before": b0, "after": b1, "activeSeat": seats, "s": s}
        return (bool(ok) and all(b[0] == 0 for b in b1) and b1 == b0,
                f"tally activeSeat host/client {seats} after {s} s (want 1 on both); (side, turn) {b0} -> {b1} "
                f"(want side 0, unchanged)")
    attempt(cells, "RS-pass", pas)
    need(cells, "RS-pass")

    def cmd():
        quiet(lambda: session.assert_t_cmd(host, client, RS_GUEST, RS_HOST0, host_check=False, what="RS"), ev, "rsCmd")
        return True, f"client admitted on its guest {RS_GUEST}, not_your_unit on host soldier {RS_HOST0}, hash clean"
    attempt(cells, "RS-cmd", cmd, (host, client))
    cells["RS-common"] = common_cell(host, client, crash0, ev, "rs")


def boot_rs():
    host = GameClient("host", None, make_user_dir("d246u_rs_host", saves=(FIXTURE,)))
    client = GameClient("client", None, make_user_dir("d246u_rs_client"))
    crash0 = session._crash_log_snapshot()
    try:
        try:
            boot("RS", (host, client))
        except Miss:
            return fail_all((("RS", RS_CELLS),), "boot (FIXTURE-STOP, see the CAPTURE RS line)")
        return run_row("RS", RS_CELLS, lambda cells, ev: row_rs(host, client, crash0, cells, ev))
    finally:
        shut(host, client)


def row_l1(host, crash0, removed, cells, ev):
    ev["l1Removed"] = removed.decode("ascii", errors="replace").rstrip("\r")
    cells["L1-load"] = load_cell(host, os.path.basename(FIXTURE), ev, "l1")
    lines = convert_line(host) if cells["L1-load"][0] else []
    mode = es(host, "turnMode")
    ev["l1Mode"] = {"turnMode": mode, "convert": lines}
    cells["L1-mode"] = (mode == "traditional" and len(lines) == 1 and "turnMode traditional" in lines[0],
                        f"host turnMode {mode!r} (want 'traditional'); conversion lines {lines} (want one, saying "
                        f"turnMode traditional)")
    ds, crash = es(host, "desyncSeen"), sorted(session._crash_log_snapshot() - crash0)
    cells["L1-common"] = (ds is False and not crash,
                          f"host desyncSeen {ds} (want False); new crash files {crash} (want none); no client in "
                          f"boot L1")


def boot_l1():
    d = make_user_dir("d246u_l1_host")
    removed = derive(FIXTURE, os.path.join(d, "xcom1", os.path.basename(FIXTURE)), b"coop_parallel_turns:", None)
    host = GameClient("host", None, d)
    crash0 = session._crash_log_snapshot()
    try:
        try:
            boot("L1", (host,))
        except Miss:
            return fail_all((("L1", L1_CELLS),), "boot (FIXTURE-STOP, see the CAPTURE L1 line)")
        return run_row("L1", L1_CELLS, lambda cells, ev: row_l1(host, crash0, removed, cells, ev))
    finally:
        shut(host)


def main():
    t0 = time.time()
    fails = boot_rs()
    fails += boot_l1()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_d246u_old_battle_resume: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
