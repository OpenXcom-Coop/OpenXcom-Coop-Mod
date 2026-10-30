"""Separate campaign battles: every unit is commanded by its owner's machine.

One world, the host machine runs every battle. Rows:

  SEP-1  The host's craft lands with the client's tank aboard (the client
         equipped it as a visitor). The battle belongs to the host and its
         base is the selected base on both machines; the host's
         soldiers are on the host's seat and the client's tank is on the
         client's seat, on both machines. After the abort the client's own
         debriefing stays up until its OK while the host's post-battle world
         arrives under it, the host sends that world once, and every soldier is
         back in its owner's base, none duplicated, the two worlds equal.
  SEP-2  The client's own craft lands (the host brokers the landing, the
         client answers YES). The battle starts on both machines and belongs to
         the client, whose base is the selected base on both machines (the
         briefing, equipment and debriefing read it); the client's soldiers and
         its tank are on the client's
         seat on both machines; the client moves its own soldier, the host's
         selection of it is refused, the hashes stay equal. The battle ends as
         in SEP-1: the client's soldiers are back in the client's base.
  SEP-2C The client launches its own craft to Cydonia with its tank aboard:
         the host's machine runs the battle, which belongs to the client, and
         the client's soldiers and its tank are on the client's seat on both
         machines.
  SEP-3  A Separate save the previous co-op build made on the host during a
         battle the client's craft started holds only the client's campaign
         (the host's own bases are not in it). Loading it on the host is
         refused with a message, the file is unchanged, no upgraded copy is
         written, and the game is back where the load started. The load runs
         on the host before any session, so the client sees nothing of it.
  SEP-4  A Separate battle saved mid-battle by the previous co-op build (two
         worlds, the client's soldier aboard the host's craft) is upgraded to
         one world and resumed: each soldier is on its owner's seat on both
         machines, the hashes are equal, and neither machine sends the old
         two-world guest roster (one world has no guests to send). After the
         battle ends both machines hold the same soldiers: every soldier id is
         used once, each player keeps its own eight soldiers, and the battle
         copy of the client's soldier is gone (the client's soldier is listed
         once, as the client's).

Run:  py -3 tools/coop_test/test_separate_battle_owner.py [sep1|sep2|sep2c|sep3|sep4]
Exit 0 = pass; anything else = failure.
"""

import hashlib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import session
import separate_campaign_fixture as fixture
import test_battle_end_campaign as ending
import test_coop_resume_battle_control as resume_control
import test_old_battle_resume as old_resume
from harness import GameClient, make_user_dir

TANK = "STR_TANK_CANNON"
SHELLS = "STR_HWP_CANNON_SHELLS"
WORLD_STREAM = "[coop-shared] streaming authoritative world to client"   # the host's world-stream log line
GUEST = "Guest Zzz"   # the client's soldier aboard the host's craft in fixtures/separate_battle.sav
OWNED = {0: 8, 1: 8}  # soldiers each player owns in that save once it is one world (the client's: 7 + GUEST)
# The previous build's host save during a battle the client's craft started: only the client's world is in it.
CLIENT_BATTLE_SAVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                                  "separate_client_battle_main.sav")
# EXACT text, from bin/common/Language/en-US.yml: asserted as text, since a missing key shows as the key itself.
REFUSED_TITLE = "This save cannot be upgraded:"
REFUSED_TEXT = ("This save was made during a battle that the other player's craft started, so it does not hold "
                "your own campaign. Load a save from before that mission. This save was not changed.")
REFUSED_KEY = "STR_SAVE_UPGRADE_PARTNER_BATTLE"   # the upgrade's own answer, before the screen translates it


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


def _roster_rows(gc):
    """Sorted (base, id, name, owner) of every soldier in a base on @a gc."""
    return sorted((b["name"], s["id"], s["name"], s["owner"])
                  for b in gc.ok({"cmd": "get_soldiers"})["bases"] for s in b["soldiers"])


def _check_upgraded_return(host, client, row):
    """After the battle of an upgraded save: no soldier id twice on either
    machine, each player owns OWNED soldiers, GUEST is listed once and owned
    by the client (its battle copy is gone), and both machines list the same
    soldiers in the same bases."""
    seen = []
    for gc, label in ((host, "host"), (client, "client")):
        rows = _roster_rows(gc)
        ids = [r[1] for r in rows]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        assert not dup, f"{row}: {label} soldier ids used twice {dup}: {rows}"
        owned = {o: sum(1 for r in rows if r[3] == o) for o in sorted({r[3] for r in rows})}
        assert owned == OWNED, f"{row}: {label} soldiers per owner {owned}, want {OWNED}: {rows}"
        guests = [r for r in rows if r[2] == GUEST]
        assert len(guests) == 1 and guests[0][3] == 1, (
            f"{row}: {label} {GUEST} rows {guests}, want one, owned by the client (the battle copy removed)")
        seen.append(rows)
    assert seen[0] == seen[1], f"{row}: rosters differ host={seen[0]} client={seen[1]}"
    print(f"PASS {row} return: {len(seen[0])} soldiers, ids used once, the same on both machines, "
          f"no battle copy of {GUEST} left")
    fixture.assert_same_world(host, client, f"{row} after the battle")


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


def _check_owner(host, client, owner, row, base=None):
    for gc, label in ((host, "host"), (client, "client")):
        bs = session.battle_state(gc)
        assert bs.get("battleOwnerPlayerName") == owner, (
            f"{row}: {label} battleOwnerPlayerName={bs.get('battleOwnerPlayerName')!r}, want {owner!r}")
        assert base is None or bs.get("selectedBase") == base, (
            f"{row}: {label} selectedBase={bs.get('selectedBase')!r}, want {base!r}")
    print(f"PASS {row} owner: the battle belongs to {owner} on both machines"
          + ("" if base is None else f", {base} selected"))


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
    it; the client's own OK then takes it to its geoscape on that world.
    The host sends its post-battle world once: the host's return to its
    geoscape must not send a second one, which would replace the client's
    screens again."""
    for gc, label in ((host, "host"), (client, "client")):
        assert session.event_state(gc).get("desyncSeen") is False, f"{row}: {label} desync before the abort"
    streams = ending.log_count(host, WORLD_STREAM)
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
    extra, secs = ending.wait_until(lambda: ending.log_count(host, WORLD_STREAM) - streams != 1, ending.HOST_HOLD_S)
    assert not extra, (f"{row}: the host streamed its world {ending.log_count(host, WORLD_STREAM) - streams} "
                       f"times after the battle (want once)")
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
        _check_owner(host, client, "HostPlayer", row, "HostBase")
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
        _check_owner(host, client, "ClientPlayer", row, "ClientBase")
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
        _board_tank(host, client, "ClientBase", craft["id"])
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
        _check_seats(host, client, lambda u: 1, 1, row)
        print(f"ALL {row} PASSED")
    finally:
        js.shutdown()


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _check_untouched(path, digest, upgraded, row, when):
    assert _sha256(path) == digest, f"{row}: the save changed on disk {when}"
    assert not os.path.exists(upgraded), f"{row}: an upgraded copy was written {when}: {upgraded}"


def sep3():
    """The previous build's save made on the host during a battle the client's
    craft started (fixtures/separate_client_battle_main.sav): the load is
    refused with a message, the file stays as it was and the host is back
    where the load started."""
    row = "SEP-3"
    save = os.path.basename(CLIENT_BATTLE_SAVE)
    host_dir = make_user_dir("sep_battle_owner3r_host", saves=(CLIENT_BATTLE_SAVE,))
    path = os.path.join(host_dir, "xcom1", save)
    upgraded = os.path.join(host_dir, "xcom1", save[:-4] + "_upgraded.sav")
    digest = _sha256(path)
    host = GameClient("host", None, host_dir)
    try:
        host.spawn(); host.connect()
        det = host.ok({"cmd": "upgrade_detect", "file": save})
        assert (det.get("kind"), det.get("variant"), det.get("schema")) == ("legacy", "embed", 2), f"{row}: {det}"
        start = session.states(host)
        host.ok({"cmd": "load_save_menu", "file": save})
        host.wait_for(f"{row} upgrade dialog", lambda: session.has_state(host, "SaveUpgradeDialogState"),
                      timeout=30, interval=0.1)
        click = session.click_widget_ready(host, "Create upgraded save")
        assert click.get("ok"), f"{row}: the upgrade button was not clicked: {click}"
        host.wait_for(f"{row} the upgrade's answer",
                      lambda: session.has_state(host, "SaveUpgradeMessageState")
                      or session.has_state(host, "SaveUpgradeSummaryState"),
                      timeout=30, interval=0.1)
        top = session.top_state(host)
        assert top == "SaveUpgradeMessageState", (
            f"{row}: the upgrade was not refused: top {top}, states {session.states(host)}")
        texts = [w["text"] for w in host.ok({"cmd": "list_widgets"})["widgets"] if w.get("text") is not None]
        assert REFUSED_TITLE in texts and REFUSED_TEXT in texts, f"{row}: the refusal shows {texts}"
        print(f"PASS {row} refused: {REFUSED_TITLE} {REFUSED_TEXT}")
        click = session.click_widget_ready(host, "OK")
        assert click.get("ok"), f"{row}: OK was not clicked: {click}"
        host.wait_for(f"{row} back where the load started", lambda: session.states(host) == start or None,
                      timeout=30, interval=0.1)
        print(f"PASS {row} back: {session.states(host)}")
        _check_untouched(path, digest, upgraded, row, "after the refused load")
        r = host.ok({"cmd": "upgrade_run", "host": save})
        assert r.get("success") is False and r.get("errors") == [REFUSED_KEY], (
            f"{row}: the upgrade's own answer is {r}, want refused with [{REFUSED_KEY}] only")
        _check_untouched(path, digest, upgraded, row, "after the upgrade's own run")
        assert host.proc.poll() is None and host.ok({"cmd": "get_state"}), f"{row}: the host game stopped"
        print(f"PASS {row} untouched: the save's bytes are unchanged, no upgraded copy, the game runs")
        print(f"ALL {row} PASSED")
    finally:
        old_resume.shut(host)


def sep4():
    """The previous build's mid-battle save (fixtures/separate_battle.sav: the
    host's Skyranger with three host soldiers and the client's "Guest Zzz"
    aboard) through the save upgrade, then resumed by both players."""
    row = "SEP-4"
    save = os.path.basename(old_resume.FIXTURE)
    upgraded = save[:-4] + "_upgraded.sav"
    host = GameClient("host", None, make_user_dir("sep_battle_owner4_host", saves=(old_resume.FIXTURE,)))
    client = GameClient("client", None, make_user_dir("sep_battle_owner4_client"))
    ev = {}
    try:
        host.spawn(); client.spawn(); host.connect(); client.connect()
        r = host.ok({"cmd": "upgrade_run", "host": save})
        assert r.get("success") is True, f"{row}: the save upgrade failed: {r}"
        ok, why = old_resume.load_cell(host, upgraded, ev, "sep4")
        assert ok, f"{row}: {why}"
        ok, why = old_resume.resume_loaded(host, client, "46614", ev, "sep4")
        assert ok, f"{row}: {why}"
        session.press_back_when_shown(host, "host RESUME", codes=(60, 62))
        for gc, label in ((host, "host"), (client, "client")):
            gc.wait_for(f"{label} back on the battle", lambda gc=gc: session.top_state(gc) == "BattlescapeState" or None,
                        timeout=60, interval=0.25)
        split = resume_control.split_report(host, client)
        for label in ("host", "client"):
            seats = {name: seat for _sid, name, seat in split[label]["units"]}
            assert seats == old_resume.SEATS_BY_NAME, (
                f"{row}: {label} seats {seats}, want {old_resume.SEATS_BY_NAME}")
        print(f"PASS {row} seats: every soldier on its owner's seat on both machines")
        session.assert_hash_clean(host, client, full=True, what=row)
        print(f"PASS {row} hash: every bucket equal")
        for gc, label in ((host, "host"), (client, "client")):
            contrib = session.event_state(gc).get("guestContrib") or {}
            assert contrib.get("sent") == 0 and contrib.get("recvSeats") == [], (
                f"{row}: {label} guest roster sent={contrib.get('sent')} recvSeats={contrib.get('recvSeats')}, "
                f"want 0 and [] (one world has no guests)")
        print(f"PASS {row} guests: neither machine sends a guest roster")
        _campaign_exit(host, client, row)
        _check_upgraded_return(host, client, row)
        print(f"ALL {row} PASSED")
    finally:
        old_resume.shut(host, client)


def main():
    rows = sys.argv[1:] or ["sep1", "sep2", "sep2c", "sep3", "sep4"]
    for name in rows:
        {"sep1": sep1, "sep2": sep2, "sep2c": sep2c, "sep3": sep3, "sep4": sep4}[name]()


if __name__ == "__main__":
    main()
