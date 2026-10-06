"""Resume a real Separate parallel battle and prove local selection/control.

Usage:
  python tools/coop_test/test_separate_campaign_parallel_resume_selection.py SAVE

The supplied host save is copied into an isolated harness directory.  The
client starts with an empty directory and receives the authoritative world and
battle through the production resume protocol.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_parallel_intents as PI


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_separate_campaign_parallel_resume_selection.py SAVE")
    save = os.path.abspath(sys.argv[1])
    if not os.path.isfile(save):
        raise SystemExit(f"save not found: {save}")

    save_name = os.path.basename(save)
    host_dir = make_user_dir(
        "sep_parallel_resume_selection_host", saves=[save],
        options={"EnableCoopParallelTurns": True, "skipNextTurnScreen": True})
    client_dir = make_user_dir(
        "sep_parallel_resume_selection_client",
        options={"EnableCoopParallelTurns": False})
    host = GameClient("host", 48984, host_dir)
    client = GameClient("client", 48985, client_dir)
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        session.resume_campaign_battle(
            host, client, save_name, port="48284",
            host_name="Player", client_name="Jer-3i", timeout=180)

        for gc, label in ((host, "host"), (client, "client")):
            gc.wait_for(
                f"{label} resumed parallel player side",
                lambda gc=gc: (lambda b: b if (
                    b.get("inBattle") and b.get("battleInit")
                    and b.get("parallelActive") and b.get("coopTurn") == 2
                ) else None)(gc.ok({"cmd": "battle_state"})),
                timeout=120, interval=0.5)

        hb = host.ok({"cmd": "battle_state"})
        cb = client.ok({"cmd": "battle_state"})
        assert hb["selectedUnitCoop"] == 0, hb
        assert cb["selectedUnitCoop"] == 1, cb
        selected = cb["selectedUnitId"]
        assert selected >= 0, cb
        print(f"PASS resumed local selection: host unit {hb['selectedUnitId']} "
              f"(coop 0), client unit {selected} (coop 1)")

        before = PI.pos(cb, selected)
        probe = client.ok({"cmd": "battle_intent", "action": "probe_step",
                           "unit": selected, "radius": 3, "max": 400})
        assert probe.get("steps"), f"resumed client unit {selected} has no pathable step"
        step = probe["steps"][0]
        sent = client.ok({"cmd": "battle_intent", "action": "move",
                          "unit": selected, "x": step["x"],
                          "y": step["y"], "z": step["z"]})
        assert sent.get("routed") is True, sent
        client.wait_for(
            "resumed client intent acknowledged",
            lambda: PI.parallel(client).get("pendingReqId") == 0 or None,
            timeout=60, interval=0.25)
        deny = PI.parallel(client).get("lastDenyWarning", "")
        assert not deny, f"resumed client move denied: {deny}"
        host.wait_for(
            "resumed client move executed by host",
            lambda: PI.pos(host.ok({"cmd": "battle_state"}), selected) != before or None,
            timeout=60, interval=0.25)
        client.wait_for(
            "resumed client move displayed on client",
            lambda: PI.pos(client.ok({"cmd": "battle_state"}), selected)
                    == PI.pos(host.ok({"cmd": "battle_state"}), selected) or None,
            timeout=60, interval=0.25)
        print("PASS resumed Separate parallel control: client moves its own soldier")
    finally:
        host.shutdown(); client.shutdown()


if __name__ == "__main__":
    main()
