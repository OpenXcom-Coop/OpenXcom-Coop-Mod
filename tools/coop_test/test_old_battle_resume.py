"""A SEPARATE co-op campaign saved mid-battle by an older version (two worlds) goes through the save upgrade (one
world, written as <name>_upgraded.sav, the step the load's upgrade dialog runs), then loads on the host without the
"different version" refusal and resumes for both players: the host's load converts the battle in memory.

Fixture: tools/coop_test/fixtures/separate_battle.sav, made by the released game's own
test_coop_resume_battle_control.py, committed unedited.

Boot old_save_resumes (key 46610, dirs old_battle_resume_*): the host gets the fixture, the client an EMPTY dir.
  host_load            upgrade_run on the fixture succeeds (its report in EVIDENCE), then host load_save_menu of the
                       upgraded save -> HostMenu within 60 s, no ErrorMessageState (without the fix: ErrorMessageState
                       and the refusal text "different version of the mod" in the host log, in EVIDENCE)
  conversion_line      exactly one "[coop-convert] an older version's mid-battle co-op save converted" line whose
                       counts are PARTNER_SNAPSHOTS / PARTNER_MIRRORS / SEATED / UNSEATED, turnMode traditional,
                       deployment DEPLOYMENT
  both_in_battle       session.resume_campaign_battle's post-load steps on key 46610: both inBattle, phase Active,
                       authority.battleId equal and non-zero
  ready_hash           the host log has "battle_ready saveBlob EQUAL" and no MISMATCH; desyncSeen false on both
  seat_split           the (name, seat) set == SEATS_BY_NAME on both (rc.assert_split); every non-player original
                       faction has coop -1
  host_go              turnMode "traditional" and coopEndTurnTally.activeSeat 0 on both (the host's go)
  deploy_strings       deployment / strTarget / strCraftOrBase == DEPLOYMENT / TARGET / CRAFT_OR_BASE on both
  resume_click         the host's RESUME (CoopState 60 / 62); both tops BattlescapeState; no HostMenu / LobbyMenu
  refused_not_your_go  the client's turn order for its guest is refused not_your_go; the guest's facing unchanged on
                       both
  baton_pass           the host's END TURN -> coopEndTurnTally.activeSeat 1 on both; side 0 and turn unchanged
  own_turn_admitted    own guest turn admitted: no deny with its iseq; a host turn delta, admitted +1; facings
  common_checks        every hash bucket EQUAL, desyncSeen false on both, no new lane crash file, the client wrote no
                       save
Boot no_turn_mode_line (host only, dir old_battle_resume_legacy_host): the SEPARATE fixture with its ONE
coop_parallel_turns line removed (the v2.0.6 shape, line endings kept, asserted), then upgraded as above.
  no_turn_mode_load         as host_load
  no_turn_mode_traditional  event_state.turnMode "traditional" on the host; the conversion line says turnMode
                            traditional
  no_turn_mode_common       desyncSeen false on the host, no new lane crash file (no client in this boot)

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure; a
cell whose precondition failed FAILs "not reached". A boot step past its bound prints ONE CAPTURE line and fails the
boot's rows "boot". ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_old_battle_resume.py
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

FIXTURE = os.path.join(HERE, "fixtures", "separate_battle.sav")
KEY = "46610"
HOST_NAME, CLIENT_NAME = "HostPlayer", "ClientPlayer"          # the save's coopPlayers
SEATS_BY_NAME = {"Erno Bartok": 0, "Robin Berggren": 0, "Lyris Kollias": 0, "Guest Zzz": 1}
SEATED = (3, 1)                   # seated 0 / seated 1, from each unit's saved coop tag
UNSEATED = 25                     # 14 aliens + 11 civilians, each saved with coop 0
PARTNER_SNAPSHOTS, PARTNER_MIRRORS = 0, 0  # partner world: battle snapshots / droppable mirrors
DEPLOYMENT = "STR_TERROR_MISSION"
TARGET, CRAFT_OR_BASE = "TERROR SITE-1", "BASE> HostBase"
GUEST_UNIT, HOST_UNIT = 9, 1      # the guest's battle unit / Erno Bartok's
LOAD_S, LOG_S, RESUME_S, MODE_S, CLICK_S, DENY_S, PASS_S = 60, 10, 180, 10, 60, 15, 30
CONVERT = "[coop-convert] an older version's mid-battle co-op save converted"
CONVERT_RE = re.compile(r"partner worlds: battle snapshots (\d+), mirrors (\d+); seats 0/1 (\d+)/(\d+), "
                        r"unseated (\d+); turnMode (\w+); deployment \"([^\"]*)\"")
REFUSAL = "different version of the mod"
N_EQUAL = "battle_ready saveBlob EQUAL"
N_MISMATCH = "battle_ready saveBlob MISMATCH"
RESUME_CELLS = ("host_load", "conversion_line", "both_in_battle", "ready_hash", "seat_split", "host_go",
                "deploy_strings", "resume_click", "refused_not_your_go", "baton_pass", "own_turn_admitted",
                "common_checks")
LEGACY_CELLS = ("no_turn_mode_load", "no_turn_mode_traditional", "no_turn_mode_common")


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
            print(f"[old_battle] shutdown {gc.name}: {type(e).__name__}: {str(e)[:200]}", flush=True)


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
    failure also prints ONE CAPTURE line."""
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


def upgrade_save(host, save, ev, tag):
    """The save upgrade on `save` (upgrade_run: the runner the load's upgrade dialog starts). Returns (ok, the
    upgraded file's name, the failure text)."""
    r = host.cmd({"cmd": "upgrade_run", "host": save})
    ev[f"{tag}Upgrade"] = {k: r.get(k) for k in ("ok", "success", "needsUpgrade", "errors", "errorMessage", "report")}
    return (r.get("success") is True, save[:-4] + "_upgraded.sav",
            f"upgrade_run {save} {ev[f'{tag}Upgrade']} (want success)")


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
    cell made (calling the helper would load the save a second time while its lobby commands run)."""
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


def row_old_save_resumes(host, client, crash0, cells, ev):
    up, save, why = upgrade_save(host, os.path.basename(FIXTURE), ev, "resume")
    cells["host_load"] = load_cell(host, save, ev, "resume") if up else (False, why)
    need(cells, "host_load")
    cells["conversion_line"] = log_cell(host, ev, "resume", (PARTNER_SNAPSHOTS, PARTNER_MIRRORS, SEATED[0], SEATED[1],
                                                             UNSEATED, "traditional", DEPLOYMENT))
    attempt(cells, "both_in_battle", lambda: resume_loaded(host, client, KEY, ev, "resume"), (host, client))
    need(cells, "both_in_battle")
    cells["ready_hash"] = hash_cell(host, client, ev, "resume")
    cells["seat_split"] = seats_cell(host, client, ev, "old_save_resumes", SEATS_BY_NAME)

    def mode():
        return ([es(gc, "turnMode") for gc in (host, client)] == ["traditional"] * 2
                and [tally_seat(gc) for gc in (host, client)] == [0, 0])
    wait_until(mode, MODE_S)
    got = {gc.name: (es(gc, "turnMode"), es(gc, "coopEndTurnTally")) for gc in (host, client)}
    ev["resumeMode"] = got
    cells["host_go"] = (mode(), f"(turnMode, coopEndTurnTally) {got} (want traditional, activeSeat 0 on both)")
    cells["deploy_strings"] = deploy_cell(host, client, ev, "resume", (DEPLOYMENT, TARGET, CRAFT_OR_BASE))
    attempt(cells, "resume_click", lambda: click_cell(host, client, ev, "resume"), (host, client))
    need(cells, "resume_click")

    def go():
        d0 = [session.unit_of(gc, GUEST_UNIT).get("direction") for gc in (host, client)]
        to = (d0[1] + 1) % 8
        r = session.send_turn(client, GUEST_UNIT, to)

        def denied():
            ld = es(client, "lastDeny") or {}
            return ld if ld.get("reason") and (not r.get("iseq") or ld.get("iseq") == r.get("iseq")) else None
        deny, s = wait_until(denied, DENY_S, 0.1)
        d1 = [session.unit_of(gc, GUEST_UNIT).get("direction") for gc in (host, client)]
        ev["resumeGo"] = {"dir0": d0, "to": to, "resp": {k: r.get(k) for k in ("ok", "iseq", "error")}, "deny": deny,
                      "s": s, "dir1": d1}
        return ((deny or {}).get("reason") == "not_your_go" and d1 == d0,
                f"client lastDeny {deny} after {s} s (want reason not_your_go); guest {GUEST_UNIT} facing host/client "
                f"{d0} -> {d1} (want unchanged)")
    attempt(cells, "refused_not_your_go", go)

    def pas():
        b0 = [(battle_state(gc).get("side"), battle_state(gc).get("turn")) for gc in (host, client)]
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        ok, s = wait_until(lambda: [tally_seat(gc) for gc in (host, client)] == [1, 1], PASS_S, 0.2)
        b1 = [(battle_state(gc).get("side"), battle_state(gc).get("turn")) for gc in (host, client)]
        seats = [tally_seat(gc) for gc in (host, client)]
        ev["resumePass"] = {"before": b0, "after": b1, "activeSeat": seats, "s": s}
        return (bool(ok) and all(b[0] == 0 for b in b1) and b1 == b0,
                f"tally activeSeat host/client {seats} after {s} s (want 1 on both); (side, turn) {b0} -> {b1} "
                f"(want side 0, unchanged)")
    attempt(cells, "baton_pass", pas)
    need(cells, "baton_pass")

    def cmd():  # lastDeny is battle-scoped (refused_not_your_go's deny stays): prove THIS order's outcome
        d0 = [session.unit_of(gc, GUEST_UNIT).get("direction") for gc in (host, client)]
        to, hs0, base = (d0[1] + 1) % 8, event_state(host), es(client, "lastSeqApplied") or 0
        iseq = ev["resumeCmd"] = session.send_turn(client, GUEST_UNIT, to).get("iseq")
        session.wait_turn_settled(host, client, base)
        deny, hs1 = es(client, "lastDeny") or {}, event_state(host)
        (seq0, adm0), (seq1, adm1) = [(e.get("lastSeqEmitted", 0), ((e.get("intentsReceived") or {}).get("turn") or {})
                                       .get("admitted", 0)) for e in (hs0, hs1)]
        turns = [x.get("seq") for x in hs1.get("deltaRing") or [] if x.get("kind") == "turn" and x.get("seq", 0) > seq0]
        d1 = [session.unit_of(gc, GUEST_UNIT).get("direction") for gc in (host, client)]
        ev["resumeCmd"] = detail = (f"own turn iseq {iseq}: client deny {deny} (want none with iseq {iseq}); host seq "
                                f"{seq0} -> {seq1}, turn deltas {turns}, turn admitted {adm0} -> {adm1} (want +1); "
                                f"facing {d0} -> {d1} (want {to} on both)")
        return (iseq and deny.get("iseq") != iseq and turns and adm1 == adm0 + 1 and d1 == [to] * 2), detail
    attempt(cells, "own_turn_admitted", cmd, (host, client))
    cells["common_checks"] = common_cell(host, client, crash0, ev, "resume")


def boot_old_save_resumes():
    host = GameClient("host", None, make_user_dir("old_battle_resume_host", saves=(FIXTURE,)))
    client = GameClient("client", None, make_user_dir("old_battle_resume_client"))
    crash0 = session._crash_log_snapshot()
    try:
        try:
            boot("old_save_resumes", (host, client))
        except Miss:
            return fail_all((("old_save_resumes", RESUME_CELLS),),
                            "boot (setup failure, see the CAPTURE old_save_resumes line)")
        return run_row("old_save_resumes", RESUME_CELLS,
                       lambda cells, ev: row_old_save_resumes(host, client, crash0, cells, ev))
    finally:
        shut(host, client)


def row_no_turn_mode_line(host, crash0, removed, cells, ev):
    ev["legacyRemoved"] = removed.decode("ascii", errors="replace").rstrip("\r")
    up, save, why = upgrade_save(host, os.path.basename(FIXTURE), ev, "legacy")
    cells["no_turn_mode_load"] = load_cell(host, save, ev, "legacy") if up else (False, why)
    lines = convert_line(host) if cells["no_turn_mode_load"][0] else []
    mode = es(host, "turnMode")
    ev["legacyMode"] = {"turnMode": mode, "convert": lines}
    cells["no_turn_mode_traditional"] = (
        mode == "traditional" and len(lines) == 1 and "turnMode traditional" in lines[0],
        f"host turnMode {mode!r} (want 'traditional'); conversion lines {lines} (want one, saying "
        f"turnMode traditional)")
    ds, crash = es(host, "desyncSeen"), sorted(session._crash_log_snapshot() - crash0)
    cells["no_turn_mode_common"] = (ds is False and not crash,
                                    f"host desyncSeen {ds} (want False); new crash files {crash} (want none); no "
                                    f"client in boot no_turn_mode_line")


def boot_no_turn_mode_line():
    d = make_user_dir("old_battle_resume_legacy_host")
    removed = derive(FIXTURE, os.path.join(d, "xcom1", os.path.basename(FIXTURE)), b"coop_parallel_turns:", None)
    host = GameClient("host", None, d)
    crash0 = session._crash_log_snapshot()
    try:
        try:
            boot("no_turn_mode_line", (host,))
        except Miss:
            return fail_all((("no_turn_mode_line", LEGACY_CELLS),),
                            "boot (setup failure, see the CAPTURE no_turn_mode_line line)")
        return run_row("no_turn_mode_line", LEGACY_CELLS,
                       lambda cells, ev: row_no_turn_mode_line(host, crash0, removed, cells, ev))
    finally:
        shut(host)


def main():
    t0 = time.time()
    fails = boot_old_save_resumes()
    fails += boot_no_turn_mode_line()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_old_battle_resume: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
