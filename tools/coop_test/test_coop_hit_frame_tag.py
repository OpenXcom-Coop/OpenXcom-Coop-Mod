"""Regression test: a mod hit script that stores the animation frame in a unit tag
must not raise a battle desync alarm.

Player report (X-Com Files, SEPARATE campaign, parallel turns, a host-started
battle): "saveBlob diverged ... sidestart" at the first turn-2 side start, after an
alien turn in which one soldier was hit. Every other bucket matched. The host's save
shows that soldier carrying the X-Com Files HitFX tags (LAST_HIT_FRAME = the
battlescape animation frame at the hit, LAST_HIT_TYPE, LAST_HIT_POWER). The
animation frame is per-machine display state (the saveBlob hash already skips the
battle's own animFrame), so a tag copied from it can differ between the machines.

The Coop_HitFrame_Test mod's damageUnit script writes the frame (COOP_HIT_FRAME) and
a hit counter (COOP_HIT_COUNT) into the victim's tags, the same shape as HitFX.

Steps (skirmish, parallel turns on, a pinned seed):
  1. a client soldier hits a hostile with a stun rod through the intent path
     (the hit runs on the host, the client replays it), until the host's tags
     show the script ran;
  2. compare the victim's tags on the two machines;
  3. run one full turn and read the host's sync check: the saveBlob bucket must
     not have alarmed at the turn-2 side start.

  * PASS (exit 0) / FAIL (exit 2) / FAIL (exit 3: a precondition never held).
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, HERE)
import session  # noqa: E402
import test_battle_tripwire as TW  # noqa: E402
import test_parallel_intents as PI  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

MOD = os.path.join(HERE, "mods", "Coop_HitFrame_Test")
SEED = int(os.environ.get("HIT_FRAME_SEED", "8031"))
SWINGS = 8


class Inconclusive(Exception):
    pass


def hit_tags(gc):
    """{unit_id: (COOP_HIT_FRAME, COOP_HIT_COUNT)} from this machine's saveBlob text.
    A tag is tied to the nearest preceding `id:` line (units serialize `id:` before
    their `tags:` map). A zero value is not serialized, so None means 0."""
    text = gc.cmd({"cmd": "save_blob", "text": True}).get("text", "")
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"\s+id:\s*(\d+)\s*$", line)
        if m:
            cur = int(m.group(1))
        for i, key in enumerate(("COOP_HIT_FRAME", "COOP_HIT_COUNT")):
            mt = re.search(key + r":\s*(-?\d+)", line)
            if mt and cur is not None:
                out.setdefault(cur, [None, None])[i] = int(mt.group(1))
    return {k: tuple(v) for k, v in out.items()}


def save_blob_alarms(host):
    sc = session.sync_check(host)
    b = sc.get("buckets", {}).get("saveBlob", {})
    return b.get("mismatchCount", 0), b.get("compares", 0), sc.get("mismatches", [])


def main():
    opts = {"battleXcomSpeed": 2, "battleAlienSpeed": 2}
    host = GameClient("host", 49253, make_user_dir(
        "hitframe_host", mods=[MOD],
        options=dict(opts, skipNextTurnScreen=True, EnableCoopParallelTurns=True)))
    client = GameClient("client", 49254, make_user_dir(
        "hitframe_client", mods=[MOD],
        options=dict(opts, EnableCoopParallelTurns=True)))
    errs = []
    try:
        for gc in (host, client):
            TW.write_battle_fixture(gc.user_dir)
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = "49284"
        TW.bring_up_battle(host, client, seed=SEED)
        for gc in (host, client):
            if not TW.battle(gc).get("parallelActive"):
                raise Inconclusive(gc.name + ": parallel turns are not live")

        # 1. a client soldier hits a hostile until the host's script has run
        seat = client.ok({"cmd": "get_coop"})["localSeat"]
        mover = PI.pick_driver(host, client, seat, "client")
        enemy = PI.alive_enemy(TW.battle(host))
        if not enemy:
            raise Inconclusive("no live hostile")
        victim = enemy["id"]
        epos = (enemy["x"], enemy["y"], enemy["z"])
        wid = PI.give_both(host, client, mover, "STR_STUN_ROD")
        if not PI.place_adjacent(host, client, mover, epos):
            raise Inconclusive("no free tile next to hostile %d" % victim)
        hit = False
        for swing in range(SWINGS):
            PI.top_up(host, client, mover)
            PI.drive(host, client, "melee", action="melee", unit=mover, weapon_id=wid,
                     x=epos[0], y=epos[1], z=epos[2])
            if (hit_tags(host).get(victim, (None, None))[1] or 0) >= 1:
                hit = True
                print("hostile %d hit on swing %d" % (victim, swing + 1))
                break
        if not hit:
            raise Inconclusive("the stun rod never hit hostile %d in %d swings" % (victim, SWINGS))
        PI.wait_until(lambda: PI.idle(host, 5), 30)
        time.sleep(2)

        # 2. the victim's tags on both machines
        ht, ct = hit_tags(host).get(victim), hit_tags(client).get(victim)
        print("victim %d tags (frame, count): host=%s client=%s" % (victim, ht, ct))
        if ht != ct:
            errs.append("victim %d tags differ: host (frame, count)=%s client=%s" % (victim, ht, ct))

        # 3. one full turn; the turn-2 side start compares the whole save
        before = save_blob_alarms(host)
        t = TW.cycle_turn(host, client, timeout=300)
        if not t:
            raise Inconclusive("the turn did not cycle (got %r)" % (t,))
        session.wait_sync_loop_closed(host, timeout=30)
        after = save_blob_alarms(host)
        print("host saveBlob bucket (mismatches, compares): before=%s after=%s"
              % (before[:2], after[:2]))
        if after[0] > before[0]:
            errs.append("the saveBlob bucket alarmed at turn %s: %s"
                        % (t, [m for m in after[2] if m.get("bucket") == "saveBlob"][-3:]))
    except Inconclusive as e:
        print("INCONCLUSIVE: %s" % e)
        for gc in (host, client):
            gc.shutdown()
        sys.exit(3)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception:
                pass

    print("==== RESULT ====")
    for e in errs:
        print("FAIL " + e)
    if errs:
        sys.exit(2)
    print("PASS: the hit-frame tag matches on both machines and the saveBlob bucket stayed quiet")
    sys.exit(0)


if __name__ == "__main__":
    main()
