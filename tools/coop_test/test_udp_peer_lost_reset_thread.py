"""test_udp_peer_lost_reset_thread.py: when the host drops out of a co-op battle over UDP, the second player's machine
resets its battle state on its main thread only.

Over UDP the partner loss is noticed by the UDP ping thread (connection_udp_glue.cpp), which calls
handleUdpRemotePeerLost(). The client's battle state that the main thread reads and writes every frame without a
lock (the arbiter's action maps and in-flight slot, the display ghosts) must not be cleared from that thread: the
main thread's own teardown (disconnectTCP from the "Server connection lost" dialog) resets it.

Probe: event_state `battleResets` (TEST-ONLY) counts the arbiter and ghost resets, split by the thread that ran
them: {onMain, offMain}.

ONE boot: a SHARED campaign over transport udp (shared_fixture.bring_up), the mixed battle
(session.bring_up_shared_mixed_battle, one soldier per player, map seed 1), lobby key 48801. With both machines in
the battle, the host leaves to the main menu (disconnect_to_menu: the UDP worker closes, and the client's ping thread
notices at once).
  host_leaves  the client's main thread tears the battle down within 60 s (battleResets onMain grows) and shows
               CoopState 21 ("Server connection lost"); its battleResets offMain did not grow; no new crash file.

One EVIDENCE line, one PASS / FAIL line. One run is the result, no skip path. Exit 0 only when the row passes, else 2.
Run it in the foreground to completion.

Run:  python tools/coop_test/test_udp_peer_lost_reset_thread.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import shared_fixture  # noqa: E402
from session import event_state, battle_state  # noqa: E402

KEY = 48801
LOST_S = 60


def short(e, n=300):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."


def resets(gc):
    return event_state(gc).get("battleResets") or {}


def coop_dialog(gc):
    r = gc.cmd({"cmd": "coop_dialog_info"})
    return r.get("code") if r.get("ok") else None


def main():
    t0 = time.time()
    crash0 = session._crash_log_snapshot()
    ev, fails, js = {}, [], None
    try:
        js = shared_fixture.bring_up("udp_reset_thread", (0, 0, KEY), transport="udp")
        host, client = js.host, js.client
        session.bring_up_shared_mixed_battle(js, {0: 0, 1: 1},
                                             pre_landing=lambda h, c: h.ok({"cmd": "set_seed", "seed": 1}))
        session.wait_host_idle(host, client, timeout=30)
        ev["coop"] = {k: client.cmd({"cmd": "get_coop"}).get(k) for k in ("udpActive", "onConnect", "coopSession")}
        ev["inBattle"] = [battle_state(gc).get("ok") for gc in (host, client)]
        if ev["inBattle"] != [True, True]:
            fails.append(f"precondition: battle_state ok host/client {ev['inBattle']} (want both in the battle)")
        ev["before"] = resets(client)
        host.ok({"cmd": "disconnect_to_menu"})
        t2 = time.time()
        while time.time() - t2 < LOST_S:
            if (resets(client).get("onMain") or 0) > (ev["before"].get("onMain") or 0):
                break
            time.sleep(0.25)
        ev["lostS"] = round(time.time() - t2, 2)
        time.sleep(1.0)
        ev["dialog"] = coop_dialog(client)
        ev["after"] = resets(client)
        if ev["dialog"] != 21:
            fails.append(f"client CoopState code {ev['dialog']} (want 21: Server connection lost)")
        off0, off1 = (ev["before"].get("offMain") or 0), (ev["after"].get("offMain") or 0)
        if off1 != off0:
            fails.append(f"client battleResets offMain {off0}->{off1} (want unchanged: the battle state is reset on "
                         f"the main thread only)")
        if (ev["after"].get("onMain") or 0) <= (ev["before"].get("onMain") or 0):
            fails.append(f"client battleResets onMain {ev['before'].get('onMain')}->{ev['after'].get('onMain')} "
                         f"(want it to grow: the main thread's teardown reset the battle)")
    except Exception as e:
        fails.append(f"{type(e).__name__}: {short(e, 600)}")
    finally:
        if js is not None:
            for gc in (js.host, js.client):
                try:
                    gc.shutdown()
                except Exception as e:
                    print(f"[udp_reset_thread] shutdown {gc.name}: {short(e, 200)}", flush=True)
    crash = sorted(session._crash_log_snapshot() - crash0)
    ev["newCrashFiles"] = crash
    if crash:
        fails.append(f"new crash files {crash} (want none)")
    print(f"EVIDENCE host_leaves: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    print(f"{'PASS' if not fails else 'FAIL'} host_leaves{': ' + '; '.join(fails) if fails else ''}", flush=True)
    print(f"\ntest_udp_peer_lost_reset_thread: {0 if fails else 1}/1 rows passed in {time.time() - t0:.1f}s", flush=True)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
