"""OPTION 3 fail-loud PROOF: the boundary persistence alarm still catches a REAL
persistent desync.

Plan v1.1 (persistence-alarm-plan.md) §3. Boundary mismatches are now PENDING on
first sight and alarm only if STILL mismatched at the next boundary of the same
kind. This test proves that softening did NOT go too far: a genuine, persistent
one-machine divergence must still fire the alarm - one boundary late, but fire it.

Method (exactly per the plan):
  1. bring up a parallel co-op battle (TW.bring_up_battle), lever ON both machines;
  2. inject a REAL persistent divergence: battle_action set_stat (health) on ONE
     machine only;
  3. drive two alien sides.

Assert:
  * after the FIRST boundary  : syncBoundaryPending > 0 AND desyncSeen is False
                                (recorded pending, NO premature alarm);
  * after the SECOND boundary : desyncSeen is True on the host AND
                                syncBoundaryPersistAlarms >= 1 (the alarm fired on
                                persistence).

Exit 0 = pass; 2 = failure/setup error.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_endturn as PE
import test_parallel_soak as SOAK

PORT = "47997"  # in-game coop TCP rendezvous (unique per concurrent test)
SEED = 20260828


def parallel(gc):
    return SOAK.parallel(gc)


def battle(gc):
    return SOAK.battle(gc)


def victim_health(gc, uid):
    for u in battle(gc)["units"]:
        if u["id"] == uid:
            return u.get("health")
    return None


def main():
    host_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                 "skipNextTurnScreen": True, "EnableCoopParallelTurns": True}
    client_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                   "EnableCoopParallelTurns": False}
    host = GameClient("host", 48900, make_user_dir("persist_host", options=host_opts))
    client = GameClient("client", 48901, make_user_dir("persist_client", options=client_opts))
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    TW.PORT = PORT
    PE.PORT = PORT

    err = None
    try:
        TW.bring_up_battle(host, client, seed=SEED)
        for gc in (host, client):
            gc.ok({"cmd": "set_seed", "seed": SEED})
        assert battle(host)["activeSync"] is True and battle(client)["activeSync"] is False, \
            "host must own the sim, client must be the replay peer"

        # FIX LEVER on both machines (the persistence latch is lever-gated).
        for gc in (host, client):
            gc.cmd({"cmd": "parallel_state", "wire_order_state": True})
            assert parallel(gc).get("wireOrderState") is True, "wire_order_state did not engage"
        # zero the persistence counters so the assertions read this battle only.
        for gc in (host, client):
            gc.cmd({"cmd": "shared_reset_resync_stats"})

        # inject a REAL persistent divergence: set_stat health on the CLIENT only.
        live = [u for u in battle(client)["units"]
                if not u.get("isOut") and u.get("faction") == 0 and (u.get("health") or 0) > 6]
        assert live, "no live X-Com unit with health > 6 to skew"
        victim = live[0]["id"]
        client.ok({"cmd": "battle_action", "action": "set_stat", "unit": victim, "health": 5})
        print(f"injected: unit {victim} health -> 5 on CLIENT only "
              f"(host={victim_health(host, victim)} client={victim_health(client, victim)})")

        # ---- first alien side / first boundary --------------------------------
        turn0 = battle(host)["turn"]
        SOAK.close_side(host, client, 0, 1, turn0)
        p1 = parallel(host).get("syncBoundaryPending")
        healed1 = parallel(host).get("syncBoundaryHealed")
        d1 = TW.desync_seen(host)
        print(f"after 1st boundary: pending={p1} healed={healed1} desyncSeen={d1} "
              f"(unit {victim} host={victim_health(host, victim)} client={victim_health(client, victim)})")
        assert p1 and p1 > 0, (
            f"FAIL: after the first boundary the divergence must be recorded PENDING "
            f"(syncBoundaryPending>0), got {p1}. If the injected health healed at next_turn "
            f"(host==client above), set_stat health is not a persistent divergence for this "
            f"detector.")
        assert not d1, f"FAIL: premature alarm after the first boundary (desyncSeen={d1})"

        # ---- second alien side / second boundary ------------------------------
        turn1 = battle(host)["turn"]
        SOAK.close_side(host, client, 0, 1, turn1)
        d2 = TW.desync_seen(host)
        pa = parallel(host).get("syncBoundaryPersistAlarms")
        print(f"after 2nd boundary: desyncSeen={d2} persistAlarms={pa} "
              f"(unit {victim} host={victim_health(host, victim)} client={victim_health(client, victim)})")
        assert d2, "FAIL: the persistent divergence must set desyncSeen on the host by the 2nd boundary"
        assert pa and pa >= 1, f"FAIL: the persistence alarm must have fired (syncBoundaryPersistAlarms>=1), got {pa}"

    except AssertionError as ae:
        err = str(ae)
    except Exception as e:
        import traceback
        err = f"{e}\n{traceback.format_exc()}"
    finally:
        for gc in (host, client):
            try:
                gc.cmd({"cmd": "quit"})
            except Exception:
                pass

    print("\n==== PERSIST-ALARM VERDICT ====")
    if err:
        print(f"  FAIL: {err}")
        sys.exit(2)
    print("  PASS: transient heals stay silent; a persistent one-machine divergence fired the "
          "alarm on the confirming boundary (fail-loud preserved).")
    sys.exit(0)


if __name__ == "__main__":
    main()
