"""Separate campaign battles: every unit is commanded by its owner's machine.

One world, the host machine runs every battle. Rows:

  SEP-1  The host's craft lands with the client's tank aboard (the client
         equipped it as a visitor). The battle belongs to the host; the host's
         soldiers are on the host's seat and the client's tank is on the
         client's seat, on both machines. After the abort the client's own
         debriefing stays up until its OK while the host's post-battle world
         arrives under it, and every soldier is back in its owner's base, none
         duplicated, the two worlds equal.
  SEP-2  The client's own craft lands (the host brokers the landing, the
         client answers YES). The battle starts on both machines and belongs to
         the client; the client's soldiers and its tank are on the client's
         seat on both machines; the client moves its own soldier, the host's
         selection of it is refused, the hashes stay equal. The battle ends as
         in SEP-1: the client's soldiers are back in the client's base.
  SEP-2C The client launches its own craft to Cydonia: the host's machine
         runs the battle, which belongs to the client, and the client's
         soldiers are on the client's seat on both machines.

Run:  py -3 tools/coop_test/test_separate_battle_owner.py [sep1|sep2|sep2c]
Exit 0 = pass; anything else = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import session
import separate_campaign_fixture as fixture
import test_battle_end_campaign as ending

TANK = "STR_TANK_CANNON"
SHELLS = "STR_HWP_CANNON_SHELLS"


def _craft(gc, base_name, craft_type="STR_SKYRANGER"):
    base = next(b for b in fixture.geo(gc)["bases"] if b["name"] == base_name)
    return next(c for c in base["crafts"] if c["type"] == craft_type)


def _craft_report(gc, base_name, craft_id):
    return next(c for c in gc.ok({"cmd": "base_report", "base": base_name})["crafts"]
                if c["id"] == craft_id)


def _rosters(gc):
    """{base name: sorted soldier ids} and {soldier id: owner} on @a gc."""
    by_base, owners = {}, {}
    for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
        by_base[b["name"]] = sorted(s["id"] for s in b["soldiers"])
        for s in b["soldiers"]:
            owners[s["id"]] = s["owner"]
    return by_base, owners


def _board_tank(host, client, base_name, craft_id):
    """The client puts one tank on the craft of @a base_name through its own
    craft equipment command (the owner of the tank is the client). Each player
    has half of a craft's places: on the client's own craft, three of its
    soldiers stay aboard so the tank fits in the client's half."""
    if base_name == "ClientBase":
        aboard = [s for s in fixture.soldiers_at(host, base_name) if s.get("craftId") == craft_id]
        for soldier in aboard[3:]:
            client.ok({"cmd": "craft_assign", "base": base_name, "craft_id": craft_id,
                       "soldier_id": soldier["id"], "on": False})
        host.wait_for(
            "three client soldiers left aboard on the host",
            lambda: (lambda c: c if c["soldiers"] == 3 else None)(
                _craft_report(host, base_name, craft_id)),
            timeout=30, interval=0.3)
    for gc in (host, client):
        gc.ok({"cmd": "give_items", "base": base_name, "item": TANK, "count": 1})
        gc.ok({"cmd": "give_items", "base": base_name, "item": SHELLS, "count": 100})
    moved = client.ok({"cmd": "craft_equip", "base": base_name, "craft_id": craft_id,
                       "item": TANK, "count": 1})
    assert moved.get("moved"), moved
    host.wait_for(
        "the client's tank reaches the craft on the host",
        lambda: (lambda c: c if c["vehicles"].get(TANK, 0) == 1 else None)(
            _craft_report(host, base_name, craft_id)),
        timeout=30, interval=0.3)
    owners = _craft_report(host, base_name, craft_id).get("vehicleOwners", {}).get(TANK)
    assert owners == ["ClientPlayer"], (base_name, owners)


def _enter_battle(host, client, lander):
    lander.ok({"cmd": "confirm_landing"})
    for gc, label in ((host, "host"), (client, "client")):
        gc.wait_for(f"{label} entered the battle",
                    lambda gc=gc: gc.cmd({"cmd": "battle_state"}).get("inBattle") or None,
                    timeout=180, interval=1.0)


def _check_owner(host, client, owner, row):
    for gc, label in ((host, "host"), (client, "client")):
        bs = session.battle_state(gc)
        assert bs.get("battleOwnerPlayerName") == owner, (
            f"{row}: {label} battleOwnerPlayerName={bs.get('battleOwnerPlayerName')!r}, want {owner!r}")
    print(f"PASS {row} owner: the battle belongs to {owner} on both machines")


def _to_tactical(host, client, row):
    if not session.drive_both_to_tactical(host, client):
        raise AssertionError(f"{row}: tactical never reached: host={session.states(host)} "
                             f"client={session.states(client)}")


def _check_seats(host, client, soldier_seat, tank_seat, row):
    """Every player soldier's seat is its owner's (host 0, client 1) and every
    tank's seat is @a tank_seat, on both machines. Returns the client's soldier
    ids and the host's soldier ids seen in the battle."""
    client_ids, host_ids = [], []
    for gc, label in ((host, "host"), (client, "client")):
        units = session.battle_state(gc).get("units", [])
        soldiers = [u for u in units if u.get("isPlayerSoldier")]
        tanks = [u for u in units if not u.get("isPlayerSoldier") and u.get("originalFaction") == 0
                 and u.get("weapon") == TANK]
        assert soldiers, f"{row}: {label} has no player soldier in the battle"
        for u in soldiers:
            want = soldier_seat(u)
            assert u["coop"] == want, (
                f"{row}: {label} soldier {u.get('soldierId')} owner={u.get('owner')} seat={u['coop']}, want {want}")
        assert len(tanks) == (0 if tank_seat is None else 1), f"{row}: {label} tanks={tanks}"
        assert tank_seat is None or tanks[0]["coop"] == tank_seat, (
            f"{row}: {label} the client's tank is on seat {tanks[0]['coop']}, want {tank_seat}")
        if gc is host:
            client_ids = sorted(u["soldierId"] for u in soldiers if u["coop"] == 1)
            host_ids = sorted(u["soldierId"] for u in soldiers if u["coop"] == 0)
    print(f"PASS {row} seats: soldiers on their owners' seats, the client's tank on seat {tank_seat}, both machines")
    return client_ids, host_ids


def _campaign_exit(host, client, row):
    """The host aborts through the vote and leaves its debriefing. The client's
    own debriefing stays up while the host's post-battle world arrives under
    it; the client's own OK then takes it to its geoscape on that world."""
    for gc, label in ((host, "host"), (client, "client")):
        assert session.event_state(gc).get("desyncSeen") is False, f"{row}: {label} desync before the abort"
    session.coop_abort_battle(host, client, expect_both=False)
    ok, secs = ending.wait_until(lambda: ending.top(client) == "DebriefingState", ending.CLIENT_DEBRIEF_S)
    assert ok, f"{row}: the client never showed its debriefing: {ending.stack(client)}"
    ok, secs = ending.wait_until(lambda: ending.record(client).get("worldAdopted", 0) >= 1, ending.ADOPT_S)
    assert ok, (f"{row}: the client did not take the host's post-battle world under its debriefing: "
                f"record={ending.record(client)} stack={ending.stack(client)}")
    held = ending.top_hold(client)
    assert held == [], f"{row}: the client's debriefing was replaced before its OK, tops {held}"
    pressed = ending.press_ok(client)
    assert pressed["pressed"], pressed
    ok, secs = ending.wait_until(lambda: ending.geo_clean(client), ending.OK_S)
    assert ok, f"{row}: the client's OK did not reach its geoscape: {ending.stack(client)}"
    branch = ending.record(client).get("debriefOkBranch")
    assert branch == "campaign-client-shared", (row, ending.record(client))
    for gc, label in ((host, "host"), (client, "client")):
        assert session.event_state(gc).get("desyncSeen") is False, f"{row}: {label} desync after the battle"
    print(f"PASS {row} exit: the client's debriefing stayed until its OK, then its geoscape on the host's world")


def _check_return(host, client, before, row, moved=None):
    """After the battle both machines hold the same rosters, every soldier id
    that was in a base is still in that base (the one @a moved soldier may have
    been left behind by the abort), no id is duplicated and no owner changed."""
    before_bases, before_owners = before
    seen = []
    for gc, label in ((host, "host"), (client, "client")):
        bases, owners = _rosters(gc)
        seen.append(bases)
        all_ids = [i for ids in bases.values() for i in ids]
        assert len(all_ids) == len(set(all_ids)), f"{row}: {label} duplicate soldier ids {bases}"
        for name, ids in before_bases.items():
            want = [i for i in ids if i != moved]
            have = [i for i in bases.get(name, []) if i != moved]
            assert have == want, f"{row}: {label} {name} soldiers {bases.get(name)}, before {ids}"
        for sid, owner in owners.items():
            assert before_owners.get(sid, owner) == owner, (
                f"{row}: {label} soldier {sid} owner {owner}, before {before_owners.get(sid)}")
    assert seen[0] == seen[1], f"{row}: rosters differ host={seen[0]} client={seen[1]}"
    print(f"PASS {row} return: every soldier back in its owner's base on both machines, none duplicated")
    fixture.assert_same_world(host, client, f"{row} after the battle")


def sep1():
    row = "SEP-1"
    js = fixture.bring_up("sep_battle_owner1", (49982, 49983, 49282),
                          host_options={"battleXcomSpeed": 2, "battleAlienSpeed": 2},
                          client_options={"battleXcomSpeed": 2, "battleAlienSpeed": 2})
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        geo.slow_clock(host, client)
        craft = _craft(host, "HostBase")
        _board_tank(host, client, "HostBase", craft["id"])
        before = _rosters(host)
        fixture.fly_to_new_site(host, client, host)
        _enter_battle(host, client, host)
        _check_owner(host, client, "HostPlayer", row)
        _to_tactical(host, client, row)
        _check_seats(host, client, lambda u: 0 if u.get("owner") in (0, 999) else u.get("owner"), 1, row)
        _campaign_exit(host, client, row)
        _check_return(host, client, before, row)
        print(f"ALL {row} PASSED")
    finally:
        js.shutdown()


def sep2():
    row = "SEP-2"
    js = fixture.bring_up("sep_battle_owner2", (49984, 49985, 49284),
                          host_options={"battleXcomSpeed": 2, "battleAlienSpeed": 2},
                          client_options={"battleXcomSpeed": 2, "battleAlienSpeed": 2})
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        geo.slow_clock(host, client)
        craft = _craft(host, "ClientBase")
        _board_tank(host, client, "ClientBase", craft["id"])
        before = _rosters(host)
        fixture.fly_to_new_site(host, client, client)
        _enter_battle(host, client, client)
        _check_owner(host, client, "ClientPlayer", row)
        _to_tactical(host, client, row)
        client_ids, host_ids = _check_seats(host, client, lambda u: 1, 1, row)
        assert client_ids and not host_ids, (client_ids, host_ids)
        session.assert_seat_commands(host, client, client_ids[0], None, host_check=True, what=row)
        _campaign_exit(host, client, row)
        _check_return(host, client, before, row, moved=client_ids[0])
        print(f"ALL {row} PASSED")
    finally:
        js.shutdown()


def sep2c():
    row = "SEP-2C"
    js = fixture.bring_up("sep_battle_owner3", (49988, 49989, 49288),
                          host_options={"battleXcomSpeed": 2, "battleAlienSpeed": 2},
                          client_options={"battleXcomSpeed": 2, "battleAlienSpeed": 2})
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        geo.slow_clock(host, client)
        craft = _craft(host, "ClientBase")
        client.ok({"cmd": "open_cydonia", "craft_id": craft["id"], "craft_type": craft["type"]})
        client.wait_for("the client's Cydonia confirmation",
                        lambda: any("ConfirmCydoniaState" in s for s in session.states(client)) or None,
                        timeout=30, interval=0.3)
        client.ok({"cmd": "confirm_cydonia"})
        for gc, label in ((host, "host"), (client, "client")):
            gc.wait_for(f"{label} entered the Cydonia battle",
                        lambda gc=gc: gc.cmd({"cmd": "battle_state"}).get("inBattle") or None,
                        timeout=180, interval=1.0)
        _check_owner(host, client, "ClientPlayer", row)
        _to_tactical(host, client, row)
        _check_seats(host, client, lambda u: 1, None, row)
        print(f"ALL {row} PASSED")
    finally:
        js.shutdown()


def main():
    rows = sys.argv[1:] or ["sep1", "sep2", "sep2c"]
    for name in rows:
        {"sep1": sep1, "sep2": sep2, "sep2c": sep2c}[name]()


if __name__ == "__main__":
    main()
