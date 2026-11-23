"""test_client_refused_melee_rearm.py: a melee refused because it is not the player's turn is dropped, so closing a
later action menu without choosing anything does not run it again.

TRADITIONAL mode, two seats, the baton at seat 0 (the host) at battle start. The second player (seat 1, the client)
opens its soldier's stun rod menu and picks the melee row while it is off its turn: the order is refused with the
"not your turn" banner and nothing is sent. Vanilla clears a chosen melee only when its MeleeAttackBState runs; a
refused melee never pushes that state, so the action type has to be cleared where the refusal happens. Otherwise
every later popup close (an action menu cancelled with Escape) runs the old melee again: another refusal while the
player is still off its turn, and an actual stun rod attack on the old target once the baton reaches the player.

ONE boot: test_client_baton's terror skirmish (STR_TERROR_MISSION, map seed 1, the Coop_Spray_Test mod on both, AI
pinned neutral), lobby key 48797. C (unit 8) holds a stun rod on (24,24,0) facing north, A2 (unit 1000001) stands on
(24,23,0). Rows, in this order:
  control_cancel     (control) before any refusal: open C's hand menu, press Escape. Nothing is refused, nothing sent.
  refused_melee      (precondition) open the menu, press the melee row key: refused (client coopLocalExecBlocked +1),
                     no melee order sent.
  cancel_off_baton   open the menu again, press Escape: client coopLocalExecBlocked +0 and no order sent.
  cancel_on_baton    the host's END TURN passes the baton to seat 1 (coopActiveSeat 1 on both); open the menu,
                     press Escape: no melee order sent (client coopIntentsSent melee +0, host intentsReceived melee
                     unchanged) and A2's stun unchanged on both machines.
Every row also asserts hash_now full (every bucket EQUAL) and desyncSeen false on both.

One EVIDENCE line per row, one PASS / FAIL line per row. Every row runs after a failure. One run is the result, no
skip path. Exit 0 only when every row passes, else 2. Run it in the foreground to completion.

Run:  python tools/coop_test/test_client_refused_melee_rearm.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, assert_hash_clean  # noqa: E402
import test_client_baton as CB  # noqa: E402
from test_client_grenade import open_hand_menu  # noqa: E402
from test_client_shoot import snap, press, top, short  # noqa: E402

KEY = "48797"                     # this file's lobby key
C_ID, A2_ID = CB.C_ID, CB.A2_ID
ROWS = ("control_cancel", "refused_melee", "cancel_off_baton", "cancel_on_baton")
WAIT_S = 15


def melee_sent(rec):
    return ((rec["client"].get("coopIntentsSent") or {}).get("melee") or 0)


def melee_received(rec):
    return (rec["host"].get("intentsReceived") or {}).get("melee")


def stun_of(gc, uid):
    u = session.units_by_id(battle_state(gc)).get(uid) or {}
    return u.get("stun")


def settle(host, client, notes):
    """Bounded: the client's order slot empty, then the host idle."""
    try:
        client.wait_for("client inFlight null", lambda: event_state(client).get("inFlight") is None or None,
                        timeout=WAIT_S)
    except Exception as e:
        notes.append(f"inFlight wait: {short(e, 200)}")
    try:
        session.wait_host_idle(host, client, timeout=WAIT_S)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e, 200)}")


def common(host, client):
    fails = []
    try:
        assert_hash_clean(host, client, full=True, what="refused_melee_rearm")
    except AssertionError as e:
        fails.append(f"hash_now full not clean: {short(e, 400)}")
    ds = [event_state(gc).get("desyncSeen") for gc in (host, client)]
    if ds != [False, False]:
        fails.append(f"desyncSeen host/client {ds} (want False/False)")
    return fails


def menu_then(client, ev, key):
    """C's hand menu open, then one key press; waits until the menu is gone."""
    open_hand_menu(client, ev)
    press(client, key)
    client.wait_for("client left the action menu", lambda: top(client) != "ActionMenuState" or None, timeout=5)
    ev["topAfterKey"] = top(client)


def row(host, client, rid, pass_baton=False, key=CB.KEY_CANCEL):
    notes, ev = [], {}
    if pass_baton:
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        try:
            host.wait_for("coopActiveSeat 1 on both",
                          lambda: (event_state(host).get("coopActiveSeat") == 1
                                   and event_state(client).get("coopActiveSeat") == 1) or None, timeout=WAIT_S)
        except Exception as e:
            notes.append(f"precondition: baton pass: {short(e, 200)}")
        settle(host, client, notes)
    ev["seat"] = [event_state(gc).get("coopActiveSeat") for gc in (host, client)]
    before = snap(host, client)
    stun0 = [stun_of(gc, A2_ID) for gc in (host, client)]
    try:
        menu_then(client, ev, key)
    except Exception as e:
        notes.append(f"menu press: {short(e, 300)}")
    time.sleep(0.5)  # the popup-close hook runs on the next battlescape think after the menu pops
    settle(host, client, notes)
    rec = snap(host, client)
    stun1 = [stun_of(gc, A2_ID) for gc in (host, client)]
    blocked = (before["client"]["coopLocalExecBlocked"], rec["client"]["coopLocalExecBlocked"])
    sent = (melee_sent(before), melee_sent(rec))
    received = (melee_received(before), melee_received(rec))
    ev.update(blocked=blocked, meleeSent=sent, meleeReceived=received, a2Stun={"before": stun0, "after": stun1},
              banner=battle_state(client).get("coopWaitText"), lastDeny=rec["client"].get("lastDeny"), notes=notes)
    print(f"EVIDENCE {rid}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    fails = list(notes)
    want_blocked = 1 if rid == "refused_melee" else 0
    if blocked[1] - blocked[0] != want_blocked:
        fails.append(f"client coopLocalExecBlocked {blocked[0]}->{blocked[1]} (want +{want_blocked})")
    if sent[1] != sent[0]:
        fails.append(f"client melee orders sent {sent[0]}->{sent[1]} (want unchanged: nobody ordered a melee)")
    if received[1] != received[0]:
        fails.append(f"host melee intentsReceived {received[0]}->{received[1]} (want unchanged)")
    if stun1 != stun0:
        fails.append(f"A2 stun host/client {stun0}->{stun1} (want unchanged)")
    fails += common(host, client)
    return fails


def main():
    t0 = time.time()
    CB.PORT = KEY
    host = GameClient("host", 49906, make_user_dir("refused_melee_rearm_host", mods=[CB.MOD_DIR]))
    client = GameClient("client", 49907, make_user_dir("refused_melee_rearm_client", mods=[CB.MOD_DIR]))
    failed = []
    try:
        try:
            ctx = CB.boot(host, client)
            st = CB.stage_stun(host, client, ctx)
            print(f"[refused_melee_rearm] staged {st}", flush=True)
            booted = True
        except Exception as e:
            print(f"CAPTURE boot: {type(e).__name__}: {str(e)[:800]}", flush=True)
            booted = False
        plan = (("control_cancel", {}), ("refused_melee", {"key": CB.KEY_STUN}), ("cancel_off_baton", {}),
                ("cancel_on_baton", {"pass_baton": True}))
        for rid, kw in plan:
            if not booted:
                fails = ["boot failed"]
            else:
                try:
                    fails = row(host, client, rid, **kw)
                except Exception as e:  # every row runs after a failure
                    fails = [f"{type(e).__name__}: {short(e, 600)}"]
            print(f"{'PASS' if not fails else 'FAIL'} {rid}{': ' + '; '.join(fails) if fails else ''}", flush=True)
            if fails:
                failed.append(rid)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[refused_melee_rearm] shutdown {gc.name}: {short(e, 200)}", flush=True)
    print(f"\ntest_client_refused_melee_rearm: {len(ROWS) - len(failed)}/{len(ROWS)} rows passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
