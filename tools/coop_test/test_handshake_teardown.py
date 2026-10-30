"""Two rows: a refused battle start, and a leave during the start.

corrupt_blob_refused (key 48560): skirmish lobby -> BATTLE SETTINGS with 2 soldiers seated; the host arms
corrupt_next_blob and presses OK. The client must refuse the blob (reason corrupt), nothing may load, and neither
machine may be left in a battle. Both machines land where a refused co-op skirmish start lands: the host on a bare main
menu (session ended), the client on CoopState 21 (the host-gone dialog).
client_killed_mid_stream (key 48561): the same drive; the client arms hold_blob_ack (it withholds its per-chunk ack, so
the host's streamer waits after chunk 1), the host presses OK, and the client is killed mid-stream. The host must
abandon the stream and tear the battle down (phase Idle, peerAbsent false), not enter the leave pause, and land on a
bare main menu with the session ended, as a refused skirmish start does.

One EVIDENCE line per row, then one line per cell, then the row verdict. Every row runs after a failure. Exit 0 only
when every written cell passes, else 2.

Run:  python tools/coop_test/test_handshake_teardown.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import test_handshake as handshake  # noqa: E402

REFUSED_KEY, KILLED_KEY = "48560", "48561"
POLL_S = 0.2             # client_never_active: the client poll interval
WINDOW_S = 15.0          # the capture window after newbattle_ok (both machines settle within about 1.5 s)
N_CORRUPT = "corrupt_next_blob hook fired: flipped byte 0 of"
N_MISMATCH = "battle blob sha MISMATCH (battleId="
N_REFUSE = "battle_refuse received (battleId="
N_CLIENT_ACTIVE = "CLIENT phase Active (battleId="
N_ACCEPT = "battle_accept received (battleId="
N_ABORT = "[coop] streamer: connection torn down mid-transfer, abandoning stream"
N_STALE = "[exit] stale SavedGame reached the main menu"  # corrupt_blob_refused: EVIDENCE only, never asserted
HOST_NEEDLES = (N_CORRUPT, N_REFUSE, N_ACCEPT, N_ABORT, N_STALE)
CLIENT_NEEDLES = (N_MISMATCH, N_CLIENT_ACTIVE)
HELD = {}  # cells reported but not asserted, each with what it waits on (none)


def log_hits(gc, names):
    """{needle: [every log line holding it]} for the machine's openxcom.log."""
    p = os.path.join(gc.user_dir, "openxcom.log")
    lines = []
    if os.path.exists(p):
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = [line.rstrip("\n") for line in f]
    return {n: [line for line in lines if n in line] for n in names}


def new_hits(gc, base):
    """{needle: the lines added since `base` (a log_hits result)}."""
    now = log_hits(gc, tuple(base))
    return {n: now[n][len(base[n]):] for n in base}


def stack(gc):
    return session.states_stripped(gc)


def snap(gc):
    """Stack, phase / inBattle / authority, coop_dialog_info, world_state.has_save and get_coop of one machine."""
    b = session.battle_state(gc)
    a = b.get("authority") or {}
    d = gc.cmd({"cmd": "coop_dialog_info"})
    c = gc.cmd({"cmd": "get_coop"})
    return {"stack": stack(gc), "phase": b.get("phase"), "inBattle": b.get("inBattle"), "battleId": a.get("battleId"),
            "peerAbsent": a.get("peerAbsent"), "dialog": d.get("code") if d.get("present") else None,
            "dialogTitle": d.get("title") if d.get("present") else None,
            "has_save": gc.cmd({"cmd": "world_state"}).get("has_save"),
            "onConnect": c.get("onConnect"), "coopSession": c.get("coopSession")}


def drive_to_seated(host, client, key):
    """Skirmish lobby -> BATTLE SETTINGS with seat 1 holding soldiers 0 and 1. Never
    session.bring_up_to_briefings: its BriefingState wait races the refusal's unwind."""
    handshake.skirmish_host(host, key)
    handshake.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": "ClientPlayer"})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: handshake.lobby(host).get("buttonVisible") or None)
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings", lambda: (not session.has_state(host, "LobbyMenu")) or None)
    top = session.top_state(host)
    assert top == "NewBattleState", f"FIXTURE: host top {top!r} after lobby_action, stack {stack(host)}"
    ids = []
    for i in range(2):
        r = host.cmd({"cmd": "newbattle_seat_soldier", "seat": session.COOP_SEAT_1, "index": i})
        assert r.get("ok") and "soldierId" in r, f"FIXTURE: newbattle_seat_soldier {i} -> {r}"
        ids.append(r["soldierId"])
    return ids


def shut(ev, *gcs):
    """Shut each still-running machine down (a killed client is already reaped by kill()); record any failure."""
    for gc in gcs:
        try:
            if gc.proc is not None and gc.proc.poll() is None:
                gc.shutdown()
        except Exception as e:
            ev.setdefault("shutdown", []).append(f"{gc.name}: {type(e).__name__}: {str(e)[:200]}")


def verdict(row, order, cells, ev):
    print(f"EVIDENCE {row}: {ev}", flush=True)
    fails = 0
    for name in order:
        if name in cells:
            ok, detail = cells[name]
            fails += 0 if ok else 1
            print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)
        elif name in HELD:
            print(f"HELD {name}: not asserted (waits on {HELD[name]}); today's values are in EVIDENCE", flush=True)
        else:
            fails += 1
            print(f"FAIL {name}: not reached: {ev.get('error')}", flush=True)
    n = len([x for x in order if x in cells or x not in HELD])
    print(f"{row} {'PASS' if not fails else 'FAIL'} ({fails} of {n} cells failed)", flush=True)
    return fails


def row_corrupt_blob_refused():
    """corrupt_blob_refused - a corrupted battle blob is refused (key 48560)."""
    cells, ev = {}, {}
    host = GameClient("host", 1, make_user_dir("teardown_refused_host"))
    client = GameClient("client", 2, make_user_dir("teardown_refused_client"))
    crash0 = session._crash_log_snapshot()
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        ev["seated"] = drive_to_seated(host, client, REFUSED_KEY)
        ev["base"] = {"host": snap(host), "client": snap(client)}
        hb, cb = log_hits(host, HOST_NEEDLES), log_hits(client, CLIENT_NEEDLES)
        host.ok({"cmd": "corrupt_next_blob"})
        host.ok({"cmd": "newbattle_ok"})
        t0 = time.time()
        polls = {"n": 0, "battlescape": []}  # client_never_active: every client poll from newbattle_ok to the end

        def poll_client():
            st = stack(client)
            polls["n"] += 1
            if "BattlescapeState" in st:
                polls["battlescape"].append((round(time.time() - t0, 2), st))

        def wait(desc, pred, timeout):
            deadline = time.time() + timeout
            while True:
                poll_client()
                if pred():
                    return round(time.time() - t0, 2)
                if time.time() >= deadline:
                    ev.setdefault("timeouts", []).append(desc)
                    return None
                time.sleep(POLL_S)

        def ended():
            h, c = session.battle_state(host), session.battle_state(client)
            return (h.get("phase") == "Idle" and h.get("inBattle") is False and c.get("phase") == "Idle"
                    and c.get("inBattle") is False and (h.get("authority") or {}).get("battleId") == 0)

        ev["refusedAt"] = wait("host battle_refuse received", lambda: new_hits(host, {N_REFUSE: hb[N_REFUSE]})[N_REFUSE], 60)
        ev["endedAt"] = wait("both machines out of the battle", ended, 30)
        while time.time() - t0 < WINDOW_S:
            poll_client()
            time.sleep(POLL_S)
        ev["polls"], ev["pollS"] = polls["n"], round(time.time() - t0, 1)
        end = {"host": snap(host), "client": snap(client)}
        eh, ec = end["host"], end["client"]
        ev["end"] = end
        hn, cn = new_hits(host, hb), new_hits(client, cb)
        ev["hostDelta"] = {n: len(v) for n, v in hn.items()}
        ev["clientDelta"] = {n: len(v) for n, v in cn.items()}
        ev["lines"] = {"mismatch": cn[N_MISMATCH], "refuse": hn[N_REFUSE]}
        cells["corrupt_line"] = (len(hn[N_CORRUPT]) == 1,
                                 f"host corrupt_next_blob line +{len(hn[N_CORRUPT])} (want +1)")
        cells["client_sha_mismatch"] = (
            len(cn[N_MISMATCH]) == 1 and "refusing (corrupt)" in cn[N_MISMATCH][0],
            f"client sha MISMATCH +{len(cn[N_MISMATCH])} (want +1, with 'refusing (corrupt)'): "
            f"{[x[-120:] for x in cn[N_MISMATCH]]}")
        cells["host_refuse_received"] = (
            len(hn[N_REFUSE]) == 1 and "reason=corrupt" in hn[N_REFUSE][0],
            f"host battle_refuse received +{len(hn[N_REFUSE])} (want +1, with 'reason=corrupt') at "
            f"{ev['refusedAt']} s: {[x[-110:] for x in hn[N_REFUSE]]}")
        cells["client_never_active"] = (
            len(cn[N_CLIENT_ACTIVE]) == 0 and polls["n"] > 0 and not polls["battlescape"],
            f"client CLIENT phase Active +{len(cn[N_CLIENT_ACTIVE])} (want +0); BattlescapeState on "
            f"{len(polls['battlescape'])} of {polls['n']} client polls over {ev['pollS']} s (want 0): "
            f"{polls['battlescape'][:2]}")
        cells["both_idle"] = (eh["phase"] == "Idle" and eh["inBattle"] is False and ec["phase"] == "Idle"
                              and ec["inBattle"] is False and eh["battleId"] == 0,
                              f"phase {eh['phase']}/{ec['phase']}, inBattle {eh['inBattle']}/{ec['inBattle']} "
                              f"(want Idle, False on both), host battleId {eh['battleId']} (want 0)")
        # end_screens: the host on a bare main menu without a save, the client on CoopState 21 (the host-gone dialog).
        cells["end_screens"] = (eh["stack"] == ["MainMenuState"] and eh["has_save"] is False and ec["dialog"] == 21,
                                f"host {eh['stack']} has_save {eh['has_save']} / client dialog {ec['dialog']} "
                                f"(want ['MainMenuState'] / False / 21)")
    except Exception as e:
        ev["error"] = f"{type(e).__name__}: {str(e)[:600]}"
    finally:
        shut(ev, host, client)
    crash_new = sorted(session._crash_log_snapshot() - crash0)
    ev["crashNew"] = crash_new
    cells["refused_no_crash"] = (not crash_new, f"new crash files in this slot's crash folder {crash_new} (want none)")
    return verdict("corrupt_blob_refused", ("corrupt_line", "client_sha_mismatch", "host_refuse_received",
                                            "client_never_active", "both_idle", "end_screens", "refused_no_crash"),
                   cells, ev)


def row_client_killed_mid_stream():
    """client_killed_mid_stream - the client dies while the battle streams to it (key 48561)."""
    cells, ev = {}, {}
    host = GameClient("host", 3, make_user_dir("teardown_killed_host"))
    client = GameClient("client", 4, make_user_dir("teardown_killed_client"))
    crash0 = session._crash_log_snapshot()  # killed_no_crash's window spans the kill
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        ev["seated"] = drive_to_seated(host, client, KILLED_KEY)
        ev["base"] = {"host": snap(host), "client": snap(client)}
        hb, cb = log_hits(host, HOST_NEEDLES), log_hits(client, CLIENT_NEEDLES)
        arm = client.ok({"cmd": "hold_blob_ack", "on": True})
        assert arm.get("armed") is True, f"FIXTURE: hold_blob_ack {{on: true}} -> {arm}"
        host.ok({"cmd": "newbattle_ok"})
        t0 = time.time()

        def parked():
            held = client.cmd({"cmd": "hold_blob_ack"}).get("held") or 0
            return (held >= 1 and len(new_hits(host, {N_ACCEPT: hb[N_ACCEPT]})[N_ACCEPT]) == 1) or None
        try:
            host.wait_for("client held >= 1 and host battle_accept +1", parked, timeout=30, interval=0.2)
            ev["parkedAt"] = round(time.time() - t0, 2)
        except TimeoutError as e:
            ev.setdefault("timeouts", []).append(str(e)[:300])
        at_kill = {"host": snap(host), "client": snap(client), "holdBlobAck": client.cmd({"cmd": "hold_blob_ack"}),
                   "clientActive": len(new_hits(client, cb)[N_CLIENT_ACTIVE])}
        ev["atKill"] = at_kill
        client.kill()
        tk = time.time()
        ev["killRc"] = client.proc.returncode
        try:
            host.wait_for("host phase Idle", lambda: session.battle_state(host).get("phase") == "Idle" or None,
                          timeout=30, interval=0.2)
            ev["idleAt"] = round(time.time() - tk, 2)
        except TimeoutError as e:
            ev.setdefault("timeouts", []).append(str(e)[:300])
        try:  # bounded settle: the streamer thread logs its abort apart from the phase drop (about 0.02 s later)
            host.wait_for("host streamer abort line", lambda: new_hits(host, {N_ABORT: hb[N_ABORT]})[N_ABORT] or None,
                          timeout=10, interval=0.2)
        except TimeoutError:
            pass
        eh = snap(host)
        ev["end"] = eh
        hn, cn = new_hits(host, hb), new_hits(client, cb)
        ev["hostDelta"] = {n: len(v) for n, v in hn.items()}
        ev["clientDelta"] = {n: len(v) for n, v in cn.items()}
        held = at_kill["holdBlobAck"].get("held") or 0
        cells["held_at_kill"] = (
            held >= 1 and at_kill["clientActive"] == 0,
            f"at the kill: client held {held} (want >= 1), CLIENT phase Active +{at_kill['clientActive']} "
            f"(want +0); phases host {at_kill['host']['phase']} / client {at_kill['client']['phase']}")
        cells["streamer_abort_line"] = (len(hn[N_ABORT]) == 1,
                                        f"host streamer abort line +{len(hn[N_ABORT])} (want +1)")
        cells["host_idle"] = (eh["phase"] == "Idle" and eh["peerAbsent"] is False and eh["battleId"] == 0,
                              f"host phase {eh['phase']} (want Idle), peerAbsent {eh['peerAbsent']} (want False), "
                              f"battleId {eh['battleId']} (want 0), {ev.get('idleAt')} s after the kill")
        # The host's start unwinds and lands where a refused skirmish start
        # lands - a bare main menu, the session ended (no CoopState 62, no battle). Bounded wait: the main menu's init (the
        # world drop and the session teardown) runs a frame after the unwind.
        try:
            host.wait_for("host on a bare main menu", lambda: (stack(host) == ["MainMenuState"]
                          and host.cmd({"cmd": "world_state"}).get("has_save") is False) or None, timeout=15, interval=0.2)
        except TimeoutError as e:
            ev.setdefault("timeouts", []).append(str(e)[:300])
        eh = snap(host)
        ev["endMainMenu"] = eh
        cells["host_bare_main_menu"] = (
            eh["stack"] == ["MainMenuState"] and eh["has_save"] is False and eh["dialog"] is None
            and eh["inBattle"] is False and eh["coopSession"] is False,
            f"host stack {eh['stack']} has_save {eh['has_save']} dialog {eh['dialog']} inBattle {eh['inBattle']} "
            f"coopSession {eh['coopSession']} (want ['MainMenuState'], False, None, False, False)")
    except Exception as e:
        ev["error"] = f"{type(e).__name__}: {str(e)[:600]}"
    finally:
        shut(ev, host, client)
    crash_new = sorted(session._crash_log_snapshot() - crash0)
    ev["crashNew"] = crash_new
    cells["killed_no_crash"] = (not crash_new, f"new crash files in this slot's crash folder {crash_new} (want none)")
    return verdict("client_killed_mid_stream", ("held_at_kill", "streamer_abort_line", "host_idle",
                                                "host_bare_main_menu", "killed_no_crash"), cells, ev)


def main():
    fails = row_corrupt_blob_refused()
    fails += row_client_killed_mid_stream()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
