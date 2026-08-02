"""Issue #74 - drive and inspect the live session left running by
repro74_setup.py. Reconnects to both games' in-game TestServers, so you can run
it as often as you like while the two windows stay open.

  state             what the session looks like right now
  fire              make the alien launch its blaster launcher, from the machine
                    that owns the simulation (the only side whose actions
                    replicate). Skip this if you would rather end the turn in
                    both windows and let the alien AI fire it itself.
  theft             the reported symptom, staged for you to watch: arms two
                    soldiers with bare launchers, then has the second one DROP
                    its own. Run it AFTER `fire` (or after the alien AI has
                    fired). Unfixed, the FIRST soldier's launcher hits the floor
                    on the peer while staying in its hand on the shooter's side.
  check             diff the two machines' FULL item censuses; --idspace also
                    spawns one throwaway item on each side and compares the ids
                    (that is the direct test for a fabricated BattleItem, and it
                    does mutate the battle)
  quit              close both games

Run:  python tools/coop_test/repro74_probe.py <command>
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient
import session

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "repro74_state.json")
LAUNCHER = "STR_BLASTER_LAUNCHER"
BOMB = "STR_BLASTER_BOMB"


def load_state():
    if not os.path.exists(STATE_PATH):
        sys.exit(f"no session state at {STATE_PATH} - run repro74_setup.py first")
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def connect(state):
    out = []
    for tag in ("host", "client"):
        gc = GameClient(tag, state["ports"][tag], None)
        try:
            gc.connect(timeout=15)
        except Exception as e:
            sys.exit(f"cannot reach the {tag} game on :{state['ports'][tag]} ({e}) - "
                     f"is it still running? re-run repro74_setup.py")
        out.append(gc)
    return out


def census(gc):
    return {i["id"]: (i["type"], i["owner"]) for i in gc.ok({"cmd": "battle_items"})["items"]}


def diff_census(h, c):
    out = []
    for iid in sorted(set(h) | set(c)):
        a, b = h.get(iid), c.get(iid)
        if a == b:
            continue
        if a is None:
            out.append(f"item {iid} {b[0]} exists ONLY on the client (owner {b[1]})")
        elif b is None:
            out.append(f"item {iid} {a[0]} exists ONLY on the host (owner {a[1]})")
        else:
            out.append(f"item {iid} {a[0]}: host owner {a[1]} vs client owner {b[1]}")
    return out


def show(tag, gc, state):
    b = gc.cmd({"cmd": "battle_state"})
    if not b.get("inBattle"):
        print(f"  {tag}: not in a battle (top state: "
              f"{gc.cmd({'cmd': 'get_state'})['states'][-1].split('::')[-1]})")
        return
    cen = census(gc)
    launchers = sorted((i, o) for i, (t, o) in cen.items() if t == LAUNCHER)
    bombs = sorted((i, o) for i, (t, o) in cen.items() if t == BOMB)
    print(f"  {tag}: turn {b['turn']} coopTurn={b['coopTurn']} "
          f"activeSync={b.get('activeSync')} items={len(cen)}")
    print(f"        launchers {launchers}")
    print(f"        bombs     {bombs}")


def cmd_state(state, host, client):
    print(f"session from {state['exe']}")
    print(f"  soldier unit {state['soldier']}: launcher {state['soldier_launcher']}, "
          f"bomb {state['soldier_bomb']}")
    print(f"  alien   unit {state['alien']}: launcher {state['alien_launcher']}, "
          f"bomb {state['alien_bomb']} ({state['alien_hand']} hand)")
    show("host  ", host, state)
    show("client", client, state)


def cmd_fire(state, host, client):
    shooter = None
    for gc, tag in ((host, "host"), (client, "client")):
        if session.can_drive(gc.cmd({"cmd": "battle_state"})):
            shooter, shooter_tag = gc, tag
    if not shooter:
        sys.exit("neither machine owns the simulation right now (activeSync false on "
                 "both) - nothing fired here would replicate. Make sure both windows "
                 "are sitting on the tactical map with no dialog open.")
    x, y, z = state["alien_pos"]
    # Waypoint on the alien's own tile: always a valid target, and it keeps the
    # blast off the soldier, so anything that happens to the soldier's launcher
    # is the co-op replay and not the explosion.
    r = shooter.ok({"cmd": "battle_fire", "unit": state["alien"], "mode": "launch",
                    "weapon_id": state["alien_launcher"], "tu": 200,
                    "waypoints": [{"x": x, "y": y, "z": z}]})
    print(f"fired from the {shooter_tag}: weapon {r['weaponId']}, ammo {r['ammoId']}, "
          f"tu cost {r['tuCost']}")
    print("watch both windows, then: python tools/coop_test/repro74_probe.py check")


def cmd_theft(state, host, client):
    b = host.cmd({"cmd": "battle_state"})
    soldiers = [u for u in b["units"] if u["faction"] == 0 and not u["isOut"]]
    if len(soldiers) < 2:
        sys.exit(f"need two live X-COM soldiers, found {len(soldiers)}")
    victim, mover = soldiers[0], soldiers[1]

    # Bare launchers, created in the same order on both machines. With the
    # one-step id drift the alien's shot leaves behind, the mover's HOST id lands
    # exactly on the victim's launcher on the CLIENT.
    ids = {}
    for tag, gc in (("host", host), ("client", client)):
        ids[tag] = [gc.ok({"cmd": "battle_give", "unit": u["id"], "item": LAUNCHER,
                           "slot": "right", "clear_hands": True})["weaponId"]
                    for u in (victim, mover)]
    print(f"  victim soldier {victim['id']}: launcher id {ids['host'][0]} (host) / "
          f"{ids['client'][0]} (client)")
    print(f"  mover  soldier {mover['id']}: launcher id {ids['host'][1]} (host) / "
          f"{ids['client'][1]} (client)")
    if ids["host"] == ids["client"]:
        print("  item-id spaces are in lockstep - either the fix is in, or the alien "
              "has not fired yet (run `fire` first)")
    else:
        print("  item-id spaces have DRIFTED - the peer's lookup will hit the wrong item")

    name = next(u["name"] for u in b["units"] if u["id"] == mover["id"])
    host.ok({"cmd": "battle_open_inventory", "unit": mover["id"]})
    r = host.ok({"cmd": "inventory_move", "name": name, "item": LAUNCHER,
                 "slot": "ground", "from": "unit"})
    host.ok({"cmd": "battle_close_inventory"})
    print(f"  the MOVER dropped its own launcher (landed {r.get('landedSlot')})")
    print(f"  now look at soldier {victim['id']} in both windows, then run: "
          f"repro74_probe.py check")


def cmd_check(state, host, client, idspace):
    h, c = census(host), census(client)
    d = diff_census(h, c)
    print(f"host {len(h)} item instances, client {len(c)}")
    if d:
        print("DIVERGED:")
        for line in d:
            print(f"  {line}")
    else:
        print("censuses identical - every item instance matches on both machines")

    sl = state["soldier_launcher"]
    for tag, cen in (("host", h), ("client", c)):
        if sl not in cen:
            print(f"  {tag}: the soldier's launcher (item {sl}) IS GONE")
        elif cen[sl][1] != state["soldier"]:
            print(f"  {tag}: the soldier's launcher (item {sl}) left unit "
                  f"{state['soldier']} -> owner {cen[sl][1]}")

    if idspace:
        hp = host.ok({"cmd": "battle_give", "unit": state["soldier"],
                      "item": "STR_PISTOL", "slot": "belt"})
        cp = client.ok({"cmd": "battle_give", "unit": state["soldier"],
                        "item": "STR_PISTOL", "slot": "belt"})
        if hp["weaponId"] == cp["weaponId"]:
            print(f"item-id spaces in lockstep (next id {hp['weaponId']} on both)")
        else:
            print(f"ITEM-ID SPACES DRIFTED: next id is {hp['weaponId']} on the host but "
                  f"{cp['weaponId']} on the client - the peer fabricated a BattleItem "
                  f"for the replayed action, and from here on the same id means a "
                  f"different item on the two machines")

    if not d and sl in h and h[sl][1] == state["soldier"]:
        print("=> no divergence from this shot")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("state", "fire", "theft", "check", "quit"))
    ap.add_argument("--idspace", action="store_true",
                    help="check only: also compare the next item id on each machine "
                         "(spawns one pistol per side)")
    args = ap.parse_args()

    state = load_state()
    host, client = connect(state)
    if args.command == "state":
        cmd_state(state, host, client)
    elif args.command == "fire":
        cmd_fire(state, host, client)
    elif args.command == "theft":
        cmd_theft(state, host, client)
    elif args.command == "check":
        cmd_check(state, host, client, args.idspace)
    elif args.command == "quit":
        for gc in (host, client):
            gc.cmd({"cmd": "quit"})
        print("both games told to quit")


if __name__ == "__main__":
    main()
