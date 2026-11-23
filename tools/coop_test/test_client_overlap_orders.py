"""test_client_overlap_orders.py: the second player's combat order keeps its own end-of-order handling when the player
orders another soldier before the first order has ended.

In parallel turns the second player's machine (the client) takes input while the host runs the client's last order
(nothing runs locally), so the player can order soldier B while soldier A's throw is still being answered and drawn.
The client's end-of-order handling for A (CoopArbiter::coopClientCombatAftermath: the cursor restore, the targeting
cancel, the camera's return, the halt message; recorded in event_state lastAftermath) must still run when A's order
ends, whatever B's order is doing.

ONE boot: test_client_walk_draw's terror skirmish (STR_TERROR_MISSION, map seed 1, parallel turns, AI pinned
neutral), lobby key 48800. A = unit 8 (the client's first soldier) with an unprimed grenade on (12,27,0); B = unit 9
on (14,26,0). Rows, in this order:
  throw_alone        (control) the client's battle_intent throw of A's grenade at (12,22,0). When it has ended, the
                     client's lastAftermath is a new record of kind `throw`.
  throw_then_walk    a second grenade for A, the same throw, then at once a battle_intent walk of B to (16,26,0).
                     When both orders have ended: B stands on (16,26,0) on both machines (its walk ran after the
                     throw) and the client's lastAftermath is a new record of kind `throw` (A's own end ran).
Every row also asserts hash_now full (every bucket EQUAL) and desyncSeen false on both.

One EVIDENCE line per row, one PASS / FAIL line per row. Every row runs after a failure. One run is the result, no
skip path. Exit 0 only when every row passes, else 2. Run it in the foreground to completion.

Run:  python tools/coop_test/test_client_overlap_orders.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, assert_hash_clean  # noqa: E402
import test_host_combat as HC  # noqa: E402
import test_client_shoot as CSH  # noqa: E402

KEY = "48800"
A_ID, B_ID = 8, 9
SEATED = [8, 9]
A_TILE, A_DIR = (12, 27, 0), 2
B_TILE, B_DIR, B_DEST = (14, 26, 0), 2, (16, 26, 0)
THROW_TILE = (12, 22, 0)
SEED_THROW = 2
TU_MAX = 255
WAIT_S = 30


def short(e, n=300):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."


def jt(t):
    return {"x": t[0], "y": t[1], "z": t[2]}


def upos(gc, uid):
    u = session.units_by_id(battle_state(gc)).get(uid) or {}
    return (u.get("x"), u.get("y"), u.get("z"))


def done(host, client):
    ec, eh = event_state(client), event_state(host)
    bh = battle_state(host)
    return (ec.get("inFlight") is None and battle_state(client).get("coopPendingIntent") is None
            and eh.get("busyOwnerSeat") == -1 and ec.get("lastSeqApplied", 0) == eh.get("lastSeqEmitted", 0)
            and ec.get("queueDepth") == 0 and eh.get("queueDepth") == 0 and not bh.get("isBusy")
            and bh.get("pendingStates") == 0)


def wait_done(host, client, notes):
    t0 = time.time()
    while time.time() - t0 < WAIT_S:
        if done(host, client):
            time.sleep(0.3)
            if done(host, client):
                return round(time.time() - t0, 2)
        time.sleep(0.1)
    notes.append(f"orders not done within {WAIT_S}s (client inFlight {event_state(client).get('inFlight')}, "
                 f"pending {battle_state(client).get('coopPendingIntent')})")
    return None


def common(host, client):
    fails = []
    try:
        assert_hash_clean(host, client, full=True, what="client_overlap_orders")
    except AssertionError as e:
        fails.append(f"hash_now full not clean: {short(e, 400)}")
    ds = [event_state(gc).get("desyncSeen") for gc in (host, client)]
    if ds != [False, False]:
        fails.append(f"desyncSeen host/client {ds} (want False/False)")
    return fails


def bring_up(host, client):
    HC.bring_up_lobby_roster_pinned(host, client, KEY)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=HC.MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": HC.SEED_MAP}))
    pinned = session.pin_ai_neutral(host, client, tag="client_overlap_orders")
    session.wait_host_idle(host, client, timeout=30)
    assert seated.get("soldierIds") == SEATED and pinned, f"seated {seated.get('soldierIds')} pinned {pinned}"
    assert_hash_clean(host, client, full=True, what="client_overlap_orders bring-up")


def row(host, client, rid, with_walk):
    notes, ev = [], {}
    g = CSH.both(host, client, {"cmd": "battle_give", "unit": A_ID, "item": "STR_GRENADE", "clear_hands": True},
                 ("weaponId", "ammoId"))["weaponId"]
    ev["place"] = [CSH.place(host, client, A_ID, A_TILE, A_DIR), CSH.place(host, client, B_ID, B_TILE, B_DIR)]
    for uid in (A_ID, B_ID):
        CSH.set_tu_both(host, client, uid, TU_MAX)
    am0 = event_state(client).get("lastAftermath")
    host.ok({"cmd": "set_seed", "seed": SEED_THROW})
    r1 = client.cmd({"cmd": "battle_intent", "kind": "throw", "actor": A_ID,
                     "plan": {"item": g, "target": jt(THROW_TILE), "targetUnit": -1}})
    ev["throw"] = {k: r1.get(k) for k in ("ok", "iseq", "error")}
    if with_walk:
        r2 = session.send_walk(client, B_ID, B_DEST)
        ev["walk"] = {k: r2.get(k) for k in ("ok", "iseq", "error")} if isinstance(r2, dict) else r2
    ev["doneS"] = wait_done(host, client, notes)
    am1 = event_state(client).get("lastAftermath")
    ev["aftermath"] = {"before": am0, "after": am1}
    ev["lastDeny"] = event_state(client).get("lastDeny")
    ev["b"] = [upos(gc, B_ID) for gc in (host, client)]
    ev["notes"] = notes
    fails = list(notes)
    if not r1.get("ok"):
        fails.append(f"precondition: throw order not sent {ev['throw']}")
    if not (isinstance(am1, dict) and am1.get("kind") == "throw" and am1 != am0):
        fails.append(f"client lastAftermath {am0} -> {am1} (want a new record of kind throw: A's own end ran)")
    if with_walk and ev["b"] != [B_DEST, B_DEST]:
        fails.append(f"B on host/client {ev['b']} (want {B_DEST} on both)")
    return fails + common(host, client), ev


def main():
    t0 = time.time()
    host = GameClient("host", 49912, make_user_dir("client_overlap_orders_host"))
    client = GameClient("client", 49913, make_user_dir("client_overlap_orders_client"))
    rows = (("throw_alone", False), ("throw_then_walk", True))
    failed = []
    try:
        try:
            bring_up(host, client)
            booted = True
        except Exception as e:
            print(f"CAPTURE boot: {type(e).__name__}: {str(e)[:800]}", flush=True)
            booted = False
        for rid, with_walk in rows:
            ev = {}
            if not booted:
                fails = ["boot failed"]
            else:
                try:
                    fails, ev = row(host, client, rid, with_walk)
                except Exception as e:  # every row runs after a failure
                    fails = [f"{type(e).__name__}: {short(e, 600)}"]
            print(f"EVIDENCE {rid}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
            print(f"{'PASS' if not fails else 'FAIL'} {rid}{': ' + '; '.join(fails) if fails else ''}", flush=True)
            if fails:
                failed.append(rid)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[client_overlap_orders] shutdown {gc.name}: {short(e, 200)}", flush=True)
    print(f"\ntest_client_overlap_orders: {len(rows) - len(failed)}/{len(rows)} rows passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
