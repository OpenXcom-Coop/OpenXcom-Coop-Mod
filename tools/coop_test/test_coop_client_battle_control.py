"""Regression test: in a parallel-turns SEPARATE battle, the player whose craft
landed commands their own soldiers, whichever player that is.

Player report (X-Com Files, SEPARATE campaign, parallel turns on): in a battle the
CLIENT's craft started, the soldiers were labelled as the client's, but the host
controlled one of them and the other could not be selected at all. The host could
open that soldier's inventory and it showed the client as the owner, with every
inventory action blocked. The report came from a resumed mid-battle save.

A unit's `coop` value counts from the battle host (0 = the battle host's soldiers,
isSelectable / InventoryState), and the client is the battle host of a mission its
own craft started. The parallel-turns code compared `coop` with the session seat
(host 0, client 1) instead, so in a client-started battle it handed the client's
soldiers to the host and made the client a spectator.

Rows (each a fresh SEPARATE campaign with parallel turns on, one craft lands):
  S1 the CLIENT's craft lands. Live battle checks.
  R1 continues S1: the host saves mid-battle, both games restart, the pair resumes
     the battle, and the same checks run again.
  S2 the HOST's craft lands (guard: the case that already worked).

Checks per row ("owner" = the player whose craft landed, "other" = the peer):
  1. owner: active turn (coopTurn 2), a squad soldier selected, the action gate open,
     every squad soldier selectable.
  2. other: commanding spectator (coopTurn 4), action gate shut, nothing selectable.
  3. the owner's end-turn tally auto-readies the OTHER's seat (no soldiers).
  4. the other's move order for a squad soldier is refused with
     STR_COOP_NOT_YOUR_SOLDIER and nothing moves on either machine.
  5. the owner's move order for the same soldier runs on both machines.

  * PASS (exit 0) / FAIL (exit 2: a check failed or a process crashed) /
    FAIL (exit 3: a precondition never held).

Env: OXC_TEST_CRAFT - the craft type to fly (default STR_SKYRANGER).
     COOP_CBC_ROWS  - subset, e.g. "S1" (R1 always follows S1).
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, HERE)
import session  # noqa: E402
import geo  # noqa: E402
import test_coop_client_mission_abort as CAB  # noqa: E402
import test_parallel_intents as PI  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

SAVE = "coop_client_battle_control.sav"
ON = {"EnableCoopParallelTurns": True}
SEED = 7
NOT_YOURS = "STR_COOP_NOT_YOUR_SOLDIER"


class Inconclusive(Exception):
    pass


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def squad_of(b):
    return sorted(u["id"] for u in b.get("units", [])
                  if u.get("faction") == 0 and u.get("isPlayerSoldier") and not u.get("isOut"))


def view(gc):
    b = battle(gc)
    p = PI.parallel(gc)
    return {
        "coopTurn": b.get("coopTurn"),
        "battleHost": b.get("host"),
        "battleInit": b.get("battleInit"),
        "selectedId": b.get("selectedId"),
        "playableSelected": b.get("playableSelected"),
        "selectable": sorted(u["id"] for u in b.get("units", []) if u.get("selectable")),
        "coop": {u["id"]: u.get("coop") for u in b.get("units", []) if u.get("faction") == 0},
        "localSeat": p.get("localSeat"),
        "autoSeats": p.get("autoSeats"),
        "parallelActive": p.get("parallelActive"),
    }


def settle(owner, other, timeout=45):
    """Drain popups until both machines sit on the map with the coop battle
    initialised and the parallel side live, then give the turn hand-off up to
    `timeout` to land the owner on turn and the other in spectator mode. A broken
    split never lands there; the checks then report what each machine shows."""
    for _ in range(20):
        if all(CAB.top(gc) == "BattlescapeState" for gc in (owner, other)):
            break
        for gc in (owner, other):
            if CAB.top(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.5)
    if not all(CAB.top(gc) == "BattlescapeState" for gc in (owner, other)):
        raise Inconclusive("not both on the tactical map: owner=%s other=%s"
                           % (CAB.top(owner), CAB.top(other)))
    if not PI.wait_until(lambda: all(battle(gc).get("battleInit") and PI.parallel(gc).get("parallelActive")
                                     for gc in (owner, other)), 60):
        raise Inconclusive("the coop battle never initialised with parallel turns live: owner=%s other=%s"
                           % (view(owner), view(other)))
    PI.wait_until(lambda: battle(owner).get("coopTurn") == 2 and battle(other).get("coopTurn") == 4, timeout)


def wait_idle(owner, other, timeout=30):
    return PI.wait_until(lambda: not any(battle(gc).get("isBusy") for gc in (owner, other))
                         and PI.parallel(other).get("pendingReqId", 0) == 0, timeout)


def snapshot(owner, other, uid):
    return {gc.name: (PI.pos(battle(gc), uid), PI.tu(battle(gc), uid)) for gc in (owner, other)}


def pick_mover(owner, other, squad):
    """A squad soldier with a clean single step that both machines agree on."""
    for uid in squad:
        PI.top_up(owner, other, uid)
        dest = PI.free_step_both(owner, other, uid)
        if dest:
            return uid, dest
    raise Inconclusive("no squad soldier can take a clean single step on both machines")


def check_split(owner, other, phase, errs):
    """Checks 1-5. Appends one line per failed check to `errs`."""
    o, x = view(owner), view(other)
    squad = squad_of(battle(owner))
    print("[%s] owner=%s %s" % (phase, owner.name, o))
    print("[%s] other=%s %s" % (phase, other.name, x))
    if not squad:
        raise Inconclusive("[%s] no live squad soldiers on the map" % phase)
    other_seat = x["localSeat"]

    def fail(msg):
        errs.append("[%s] %s" % (phase, msg))
        print("FAIL [%s] %s" % (phase, msg))

    # 1. the owner commands the squad
    if o["coopTurn"] != 2:
        fail("%s (owner) is not on turn: coopTurn=%s (4 = spectator)" % (owner.name, o["coopTurn"]))
    if o["selectedId"] not in squad:
        fail("%s (owner) has no squad soldier selected: selectedId=%s squad=%s"
             % (owner.name, o["selectedId"], squad))
    if o["playableSelected"] is not True:
        fail("%s (owner) cannot act with its selected soldier: playableSelected=%s"
             % (owner.name, o["playableSelected"]))
    if o["selectable"] != squad:
        fail("%s (owner) selectable=%s, want the whole squad %s" % (owner.name, o["selectable"], squad))

    # 2. the other player commands nothing
    if x["coopTurn"] != 4:
        fail("%s (other) is not a spectator: coopTurn=%s" % (other.name, x["coopTurn"]))
    if x["playableSelected"] is True:
        fail("%s (other) can act with selected soldier %s, which is %s's"
             % (other.name, x["selectedId"], owner.name))
    if x["selectable"]:
        fail("%s (other) can select %s, which are %s's" % (other.name, x["selectable"], owner.name))

    # 3. the end-turn tally, decided on the owner (the battle host): the other's
    #    seat has no soldiers, so it is auto-ready and the owner's is not
    if o["autoSeats"] != [other_seat]:
        fail("%s autoSeats=%s, want [%s] (only %s's seat has no soldiers)"
             % (owner.name, o["autoSeats"], other_seat, other.name))

    # 4. the other's order for a squad soldier is refused
    if not wait_idle(owner, other):
        raise Inconclusive("[%s] the battle never went idle before the move orders" % phase)
    uid, dest = pick_mover(owner, other, squad)
    before = snapshot(owner, other, uid)
    r = PI.intent(other, unit=uid, action="move", x=dest[0], y=dest[1], z=dest[2])
    if not r.get("ok"):
        raise Inconclusive("[%s] the harness refused %s's move order: %s" % (phase, other.name, r))
    denied = PI.wait_until(lambda: PI.last_deny(other) == NOT_YOURS, 20)
    wait_idle(owner, other)
    time.sleep(1.0)
    after = snapshot(owner, other, uid)
    if not denied:
        fail("%s's move order for %s's soldier %s was not refused (lastDenyWarning=%r)"
             % (other.name, owner.name, uid, PI.last_deny(other)))
    if after != before:
        fail("%s's move order moved %s's soldier %s: %s -> %s"
             % (other.name, owner.name, uid, before, after))

    # 5. the owner's order for the same soldier runs on both machines
    PI.top_up(owner, other, uid)
    before = snapshot(owner, other, uid)
    dest = PI.free_step_both(owner, other, uid)
    if not dest:
        raise Inconclusive("[%s] soldier %s has no clean single step left" % (phase, uid))
    r = PI.intent(owner, unit=uid, action="move", x=dest[0], y=dest[1], z=dest[2])
    if not r.get("ok"):
        raise Inconclusive("[%s] the harness refused %s's move order: %s" % (phase, owner.name, r))
    moved = PI.wait_until(lambda: all(PI.pos(battle(gc), uid) == dest for gc in (owner, other)), 30)
    if not moved:
        fail("%s's move order for its own soldier %s did not run: %s -> %s (dest %s)"
             % (owner.name, uid, before, snapshot(owner, other, uid), dest))
    wait_idle(owner, other)


def land(host, client, lander):
    """Fly the lander's first transport to a fresh site and start the coop mission."""
    other = host if lander is client else client
    site, b = CAB.spawn_site(lander)
    cid = CAB.transport(lander)["id"]
    lander.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
               "lon": b["lon"] + 0.34, "lat": b["lat"] + 0.10, "dest": f"site:{site}",
               "fuel": 999999, "lowFuel": False})
    CAB.wait_landing_prompt(lander, other)
    for gc in (host, client):
        gc.ok({"cmd": "set_seed", "seed": SEED})
    lander.ok({"cmd": "coop_mission_start"})
    CAB.enter_tactical(host, client)


def spawn_pair(tag, ports, host_dir=None):
    host = GameClient("host", ports[0], host_dir or make_user_dir(tag + "_host", options=ON))
    client = GameClient("client", ports[1], make_user_dir(tag + "_client", options=ON))
    host.spawn(); client.spawn()
    host.connect(timeout=300); client.connect(timeout=300)
    return host, client


def shutdown(*gcs):
    alive = all(gc.proc is not None and gc.proc.poll() is None for gc in gcs)
    for gc in gcs:
        try:
            gc.shutdown()
        except Exception:
            pass
    return alive


def row_client_lands(errs, sfx, resume=True):
    tag = "cbcs1" + sfx
    host_dir = make_user_dir(tag + "_host", options=ON)
    host, client = spawn_pair(tag, (49241, 49242), host_dir)
    try:
        session.new_campaign(host, client, port="49281")
        geo.wait_both_ready(host, client, timeout=120)
        geo.slow_clock(host, client)
        land(host, client, client)
        settle(client, host)
        check_split(client, host, "S1 client's craft, live", errs)
        if not resume:
            return shutdown(host, client)
        if not wait_idle(client, host):
            raise Inconclusive("S1: the battle never went idle before the save")
        host.ok({"cmd": "save_game", "file": SAVE})
        if not os.path.exists(os.path.join(host_dir, "xcom1", SAVE)):
            raise Inconclusive("S1: the host's mid-battle save is not on disk")
    finally:
        alive = shutdown(host, client)
    if not alive:
        errs.append("[S1] a game process died")
        return False

    # R1: the host relaunches with its save, the client with an empty user dir.
    host, client = spawn_pair(tag + "r", (49243, 49244), host_dir)
    try:
        session.resume_campaign_battle(host, client, SAVE, port="49282")
        settle(client, host)
        check_split(client, host, "R1 client's craft, resumed", errs)
    finally:
        alive = shutdown(host, client)
    if not alive:
        errs.append("[R1] a game process died")
    return alive


def row_host_lands(errs, sfx):
    host, client = spawn_pair("cbcs2" + sfx, (49245, 49246))
    try:
        session.new_campaign(host, client, port="49283")
        geo.wait_both_ready(host, client, timeout=120)
        geo.slow_clock(host, client)
        land(host, client, host)
        settle(host, client)
        check_split(host, client, "S2 host's craft, live", errs)
    finally:
        alive = shutdown(host, client)
    if not alive:
        errs.append("[S2] a game process died")
    return alive


ROWS = {"S1": row_client_lands, "S2": row_host_lands}


def main():
    wanted = [r.strip() for r in os.environ.get("COOP_CBC_ROWS", "S1,S2").split(",") if r.strip()]
    errs, notes = [], []
    alive = True
    for i, key in enumerate(wanted):
        sfx = "" if wanted.index(key) == i else "_%d" % i
        try:
            alive = ROWS[key](errs, sfx) and alive
        except Inconclusive as e:
            notes.append("%s INCONCLUSIVE: %s" % (key, e))
        except Exception as e:
            notes.append("%s ERROR %s: %s" % (key, type(e).__name__, e))
            alive = False

    print("==== RESULT ====")
    for e in errs:
        print("FAIL " + e)
    for n in notes:
        print(n)
    print("alive:", alive)
    if errs or not alive:
        sys.exit(2)
    if notes:
        sys.exit(3)
    print("PASS: the landing player commands their own soldiers in every row")
    sys.exit(0)


if __name__ == "__main__":
    main()
