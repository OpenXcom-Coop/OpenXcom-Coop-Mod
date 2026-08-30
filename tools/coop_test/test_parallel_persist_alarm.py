"""OPTION 3 fail-loud PROOF: the boundary persistence alarm still catches a REAL
persistent desync - CRITICAL-BLOCKER proof for the alarm-unmask fix.

Plan v1.1 (persistence-alarm-plan.md) §3. Boundary mismatches are now PENDING on
first sight and alarm only if STILL mismatched at the next boundary of the same
kind. This test proves that softening did NOT go too far: a genuine, persistent
one-machine divergence must still fire the alarm - one boundary late, but fire it.

VECTOR (owner ruling 2026-08-29): inject an ITEM-EXISTENCE divergence on ONE
machine only. The prior vector (battle_action set_stat health) was INVALID: health
is a unitsRegen term that next_turn RE-SLAVES at the sidestart, so the injected
divergence healed at the very first boundary (host==client) and never persisted -
nothing for the latch to promote. Item existence is a term NOTHING re-ships (no
coop packet replicates a mid-battle loose-item spawn - see TestServer battle_drop),
so a client-only floor item is a genuinely PERSISTENT divergence in the items AND
itemIdCtr buckets (and the saveBlob superset). It pends on the first boundary and
promotes on the second - exactly the latch contract.

Method:
  1. bring up a parallel co-op battle (TW.bring_up_battle), lever ON both machines;
  2. inject a persistent divergence: battle_drop one STR_PISTOL on the CLIENT only,
     on a live X-Com unit's own floor tile (guaranteed valid floor);
  3. drive two alien sides (two sidestart boundaries).

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_endturn as PE
import test_parallel_soak as SOAK

PORT = "47997"  # in-game coop TCP rendezvous (unique per concurrent test)
SEED = 20260828
DROP_ITEM = "STR_PISTOL"  # a stock vanilla item type, present in every fixture mod


def parallel(gc):
    return SOAK.parallel(gc)


def battle(gc):
    return SOAK.battle(gc)


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

        # inject a PERSISTENT item-existence divergence: one loose floor item on the
        # CLIENT only. No coop packet replicates a mid-battle item spawn, so the host
        # never gains it and the items/itemIdCtr buckets stay divergent every boundary.
        hi0, ci0 = len(SOAK.item_census(host)), len(SOAK.item_census(client))
        live = [u for u in battle(client)["units"]
                if not u.get("isOut") and u.get("faction") == 0]
        assert live, "no live X-Com unit to host the injected floor item"
        anchor = live[0]
        drop = client.ok({"cmd": "battle_drop", "x": anchor["x"], "y": anchor["y"],
                          "z": anchor["z"], "item": DROP_ITEM, "count": 1})
        hi1, ci1 = len(SOAK.item_census(host)), len(SOAK.item_census(client))
        print(f"injected: {DROP_ITEM} id(s)={drop.get('ids')} on CLIENT only at "
              f"({anchor['x']},{anchor['y']},{anchor['z']}); "
              f"item census host {hi0}->{hi1} client {ci0}->{ci1}")
        assert ci1 == ci0 + 1 and hi1 == hi0, (
            f"the injection must add exactly one client-only item "
            f"(host {hi0}->{hi1}, client {ci0}->{ci1})")

        # ---- first alien side / first boundary --------------------------------
        turn0 = battle(host)["turn"]
        SOAK.close_side(host, client, 0, 1, turn0)
        p1 = parallel(host).get("syncBoundaryPending")
        healed1 = parallel(host).get("syncBoundaryHealed")
        d1 = TW.desync_seen(host)
        print(f"after 1st boundary: pending={p1} healed={healed1} desyncSeen={d1}")
        assert p1 and p1 > 0, (
            f"FAIL: after the first boundary the persistent item divergence must be recorded "
            f"PENDING (syncBoundaryPending>0), got {p1}. If it is 0 the boundary items/itemIdCtr "
            f"compare never saw the divergence (unmask regression?).")
        assert not d1, f"FAIL: premature alarm after the first boundary (desyncSeen={d1})"

        # ---- second alien side / second boundary ------------------------------
        turn1 = battle(host)["turn"]
        SOAK.close_side(host, client, 0, 1, turn1)
        d2 = TW.desync_seen(host)
        pa = parallel(host).get("syncBoundaryPersistAlarms")
        print(f"after 2nd boundary: desyncSeen={d2} persistAlarms={pa}")
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
    print("  PASS: a transient pends-and-heals silently; a persistent one-machine item-existence "
          "divergence pended on the first boundary and fired the alarm on the confirming boundary "
          "(fail-loud preserved).")
    sys.exit(0)


if __name__ == "__main__":
    main()
