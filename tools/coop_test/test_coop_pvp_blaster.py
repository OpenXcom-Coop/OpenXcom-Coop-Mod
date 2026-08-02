"""Issue #74 in the reporter's own setup: a PvP skirmish, where a HUMAN plays
the alien side. Their words: "if you fire blaster from alien side the xcom side
blasters disappear (not in hotseat)".

PvP is a distinct co-op game mode (`connectionTCP::_coopGamemode` 2/3, chosen by
the XCOM/Alien split in the lobby) with its own branches through the battle
code, so none of the PVE/SHARED tests exercise it. This drives the real path:

  NEW BATTLE > COOP > host lobby > client joins > host puts the CLIENT on the
  Alien team (gamemode 2) > start the battle > the alien-side player fires a
  blaster launcher.

Layout mirrors the attached save (Blaster Alien.sav): X-COM launchers in the
LEFT hand, alien launchers in the RIGHT.

Asserts the two machines end up with the SAME set of items. Losing gear to a
blaster blast is correct (DT_HE has ToItem 1.0, and a launcher's armor is 40
against a power-200 bomb); losing it on only ONE machine is the bug.

Run:  python tools/coop_test/test_coop_pvp_blaster.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_skirmish_flow as skirmish
import test_coop_alien_launcher_item_loss as I74

LAUNCHER = "STR_BLASTER_LAUNCHER"
BOMB = "STR_BLASTER_BOMB"


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def has(gc, name):
    return any(name in s for s in states(gc))


def top(gc):
    return states(gc)[-1]


def start_pvp_battle(host, client, port):
    """Skirmish lobby, client switched to the Alien team, battle started."""
    skirmish.skirmish_host(host, port)
    skirmish.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer"})
    host.wait_for("host join popup", lambda: has(host, "Profile"))
    client.wait_for("client join popup", lambda: has(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered",
                  lambda: host.cmd({"cmd": "lobby_state"}).get("buttonVisible") or None)

    r = host.ok({"cmd": "lobby_set_team", "row": 1, "team": "Alien"})
    # 2 = PVP (client plays aliens), 3 = PVP2 (host plays aliens) - which row the
    # list puts each player on varies, and either is "a human on the alien side",
    # which is all the report needs.
    print(f"       one player put on the Alien team -> gamemode {r['gamemode']} "
          f"({'client' if r['gamemode'] == 2 else 'host'} plays aliens)")
    assert r["gamemode"] in (2, 3), f"expected a PvP mode (2 or 3), got {r['gamemode']}"
    time.sleep(2)
    cg = client.cmd({"cmd": "get_coop"}).get("gamemode")
    print(f"       client sees gamemode {cg}")

    host.ok({"cmd": "lobby_action"})          # -> NEW BATTLE setup screen
    host.wait_for("host at battle settings", lambda: (not has(host, "LobbyMenu")) or None)
    host.ok({"cmd": "newbattle_ok"})

    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} in battle",
                    lambda gc=gc: (has(gc, "BriefingState") or has(gc, "InventoryState")
                                   or has(gc, "BattlescapeState")) or None,
                    timeout=180, interval=0.5)
    for gc in (host, client):
        if has(gc, "BriefingState"):
            gc.ok({"cmd": "close_briefing"})
    for gc in (host, client):
        deadline = time.time() + 120
        while time.time() < deadline:
            if has(gc, "InventoryState"):
                gc.ok({"cmd": "battle_inventory", "action": "ok"})
            if top(gc) == "BattlescapeState":
                break
            gc.cmd({"cmd": "dismiss_popup"})
            time.sleep(0.5)
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} tactical map",
                    lambda gc=gc: I74.battle(gc).get("inBattle") or None,
                    timeout=120, interval=0.5)
    # The coop turn-init handshake only runs while BattlescapeState is on top and
    # no popup is pending - drain first, then wait for a machine to own the sim.
    for gc in (host, client):
        for _ in range(20):
            if top(gc) == "BattlescapeState":
                break
            gc.cmd({"cmd": "dismiss_popup"})
            time.sleep(0.5)


def main():
    fails = []
    port = "47980"
    host = GameClient("host", 48804, make_user_dir("i74pvp_host"))
    client = GameClient("client", 48805, make_user_dir("i74pvp_client"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        start_pvp_battle(host, client, port)

        for gc, tag in ((host, "host"), (client, "client")):
            b = I74.battle(gc)
            print(f"       {tag}: gamemode={b.get('coopGamemode')} coopTurn={b.get('coopTurn')} "
                  f"activeSync={b.get('activeSync')} battleInit={b.get('battleInit')} "
                  f"host={b.get('host')}")

        hb = I74.battle(host)
        soldiers = [u for u in hb["units"] if u["faction"] == 0 and not u["isOut"]]
        aliens = [u for u in hb["units"] if u["faction"] == 1 and not u["isOut"]]
        assert soldiers and aliens, f"need both sides: {len(soldiers)} xcom, {len(aliens)} alien"
        alien, target = aliens[0], soldiers[0]

        for gc in (host, client):
            for s in soldiers[:3]:
                gc.ok({"cmd": "battle_give", "unit": s["id"], "item": LAUNCHER,
                       "ammo": BOMB, "slot": "left", "clear_hands": True})
            gc.ok({"cmd": "battle_give", "unit": alien["id"], "item": LAUNCHER,
                   "ammo": BOMB, "slot": "right", "clear_hands": True})

        def _pos(gc):
            return next((u["x"], u["y"], u["z"]) for u in I74.battle(gc)["units"]
                        if u["id"] == alien["id"])

        landed = None
        for dx, dy in [(2, 0), (-2, 0), (0, 2), (0, -2), (3, 0), (-3, 0), (0, 3), (0, -3),
                       (2, 2), (-2, -2), (2, -2), (-2, 2), (4, 0), (-4, 0)]:
            want = (target["x"] + dx, target["y"] + dy, target["z"])
            host.ok({"cmd": "battle_teleport", "unit": alien["id"],
                     "x": want[0], "y": want[1], "z": want[2]})
            if _pos(host) == want:
                landed = want
                break
        assert landed, "no free tile near the squad for the alien"
        client.ok({"cmd": "battle_teleport", "unit": alien["id"],
                   "x": landed[0], "y": landed[1], "z": landed[2]})
        assert _pos(host) == _pos(client), "alien position diverged"
        print(f"       alien at {landed}, two tiles from the X-COM squad")

        pre_h, pre_c = I74.census(host), I74.census(client)
        d0 = I74.diff_census(pre_h, pre_c)
        assert not d0, f"censuses diverged BEFORE the shot: {d0}"
        print(f"PASS pre-shot: {len(pre_h)} item instances, identical on both machines")

        def _sim_owner():
            for gc, tag in ((host, "host"), (client, "client")):
                if session.can_drive(I74.battle(gc)):
                    return (gc, tag)
            return None

        shooter, shooter_tag = host.wait_for("a machine to own the battle simulation",
                                             _sim_owner, timeout=90, interval=1.0)
        alien_launcher = max(i for i, (t, o) in pre_h.items()
                             if t == LAUNCHER and o == alien["id"])
        shooter.ok({"cmd": "battle_fire", "unit": alien["id"], "mode": "launch",
                    "weapon_id": alien_launcher, "tu": 200,
                    "waypoints": [{"x": landed[0], "y": landed[1], "z": landed[2]}]})
        print(f"       the ALIEN SIDE fires its blaster launcher (driven from the "
              f"{shooter_tag})")

        I74.settle(host, client, seconds=12)

        post_h, post_c = I74.census(host), I74.census(client)
        gone_h = sorted(set(pre_h) - set(post_h))
        gone_c = sorted(set(pre_c) - set(post_c))
        print(f"       host destroyed {len(gone_h)} items, client destroyed {len(gone_c)}")
        only_h = [(i, pre_h[i][0]) for i in gone_h if i not in gone_c]
        only_c = [(i, pre_c[i][0]) for i in gone_c if i not in gone_h]
        if only_h:
            print(f"  [DIVERGE] destroyed ONLY on the host:   {only_h}")
        if only_c:
            print(f"  [DIVERGE] destroyed ONLY on the client: {only_c}")
        for tag, post in (("host", post_h), ("client", post_c)):
            held = sorted((i, o) for i, (t, o) in post.items() if t == LAUNCHER and o != -1)
            print(f"       {tag}: launchers still held: {held}")
        d = I74.diff_census(post_h, post_c)
        if d:
            for line in d[:15]:
                print(f"  [DIVERGE] {line}")
            fails.append(f"post-shot item census diverged ({len(d)} items)")
    except Exception as e:
        print(f"[ERROR] {e}")
        fails.append(str(e))
    finally:
        host.shutdown(); client.shutdown()

    print("\n==== issue #74 PvP blaster summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  in a PvP battle, the alien side firing a blaster launcher leaves both "
          "machines with the same items")
    sys.exit(0)


if __name__ == "__main__":
    main()
