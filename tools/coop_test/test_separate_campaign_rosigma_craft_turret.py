"""ROSIGMA: a client's craft cannon stays the client's, also in an older save.

The client plays the Imperial Guard and flies a Valkyrie drop craft to a terror
site. ROSIGMA's map for that craft holds a cannon spawner with a zero fuse, so
the battle gains an ownerless player unit (STR_CAS_CANNON_MOUNT) at the end of
the first turn. The test makes its own save of that battle:

  spawn   the cannon takes the client's seat on both machines.
  save    the host quick-saves the battle, and the test rewrites the cannon's
          stored seat to the host's (0), the shape older builds wrote.
  resume  both machines resume that save. Loading it puts the cannon back on
          the client's seat, the client's turn order on it is admitted, and the
          host's click on it is refused.

Local only (local_only_tests.json): it needs the 40K and ROSIGMA mods.
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import GameClient, make_user_dir
import session
import shared_fixture
from test_separate_campaign_three_month_factions import (
    MOD_40K, MOD_ROSIGMA, require_mods)
from test_separate_campaign_rosigma_faction_finales import (
    prepare_faction_force, start_finale)


TAG = "sep_rosigma_craft_turret"
# ROSIGMA difficulty 4 is the Imperial Guard (startingBaseSuperhuman).
GUARD = 4
# The Guard's drop craft. Its map block places STR_CAS_CANNON_SPAWNER with
# fuseTimers [0, 0].
CRAFT = "STR_VALKYRIE_GRAV_DROP"
CREW = "STR_GUARDSM"
CANNON_WEAPON = "STR_CAS_CANNON"
MISSION = "STR_ALIEN_TERROR"
DEPLOYMENT = "STR_TERROR_MISSION"
RACE = "STR_EARLY_CULTISTS"
CLIENT_SEAT = 1
SPAWN_S = 300


def states(gc):
    return gc.cmd({"cmd": "get_state"})["states"]


def top(gc):
    return states(gc)[-1].split("::")[-1]


def battle(gc):
    return gc.ok({"cmd": "battle_state"})


def cannon(gc):
    units = battle(gc)["units"]
    matches = [u for u in units
               if u.get("faction") == 0 and u.get("weapon") == CANNON_WEAPON]
    assert len(matches) <= 1, matches
    return matches[0] if matches else None


def wait_for_cannon(host, client):
    """End the client's first turn until the cannon spawner has fired and
    both machines are back on the player side's tactical view."""
    if cannon(host) and cannon(client):
        return
    start = battle(host)
    client.ok({"cmd": "battle_action", "action": "end_turn_button"})
    deadline = time.time() + SPAWN_S
    while time.time() < deadline:
        for gc in (host, client):
            if top(gc) == "NextTurnState":
                gc.cmd({"cmd": "close_nextturn"})
        hb = battle(host)
        if (hb["turn"] > start["turn"] and hb["side"] == 0
                and all(top(gc) == "BattlescapeState" for gc in (host, client))
                and cannon(host) and cannon(client)):
            return
        time.sleep(0.5)
    raise AssertionError({
        "error": f"no {CANNON_WEAPON} unit on both machines within {SPAWN_S} s",
        "start": {k: start.get(k) for k in ("turn", "side")},
        "host": {"states": states(host), "turn": battle(host).get("turn"),
                 "side": battle(host).get("side"), "cannon": cannon(host)},
        "client": {"states": states(client), "cannon": cannon(client)}})


def assert_cannon_seat(host, client, what):
    hc, cc = cannon(host), cannon(client)
    assert hc and cc and hc["id"] == cc["id"], (what, hc, cc)
    assert hc["coop"] == CLIENT_SEAT and cc["coop"] == CLIENT_SEAT, (what, hc, cc)
    print(f"PASS {what}: the cannon (unit {hc['id']}) is on the client's seat on both machines")
    return hc["id"]


def downgrade_saved_seat(path, unit_id):
    """Rewrite the cannon's stored seat to 0, as older builds saved it."""
    with open(path, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    block = re.compile(r"(\n(\s*)- id: %d\r?\n(?:\2  .*\r?\n)*?\2  coop: )%d(\r?\n)"
                       % (unit_id, CLIENT_SEAT))
    text, count = block.subn(r"\g<1>0\3", text)
    assert count == 1, f"cannon unit {unit_id} has no 'coop: {CLIENT_SEAT}' line in {path}"
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"PASS save: the cannon's stored seat now reads 0 in {os.path.basename(path)}")


def assert_client_commands(host, client, unit_id):
    # The client's turn order on its cannon is admitted on both machines.
    actor = session.unit_of(client, unit_id)
    to_dir = (actor["direction"] + 1) % 8
    baseline = session.event_state(client).get("lastSeqApplied", 0)
    sent = session.send_turn(client, unit_id, to_dir)
    assert sent.get("iseq"), f"the client's turn order did not ship: {sent}"
    session.wait_turn_settled(host, client, baseline)
    deny = session.event_state(client).get("lastDeny")
    assert not deny, f"the client's turn order on its cannon was denied: {deny}"
    dirs = (session.unit_of(host, unit_id)["direction"],
            session.unit_of(client, unit_id)["direction"])
    assert dirs == (to_dir, to_dir), f"cannon direction {dirs}, want {to_dir} on both"
    print(f"PASS resume: the client turned its cannon to {to_dir} on both machines")

    # The host's click on the cannon is refused.
    x, y, z = session.pos_of(session.unit_of(host, unit_id))
    session._wait_click_ready(host, x, y, z, unit_id)
    clicked = host.cmd({"cmd": "map_tile_click", "x": x, "y": y, "z": z})
    assert clicked.get("verified") and clicked.get("clicked"), clicked
    time.sleep(0.6)
    hb = battle(host)
    assert hb.get("coopWaitText") == "Not one of your soldiers", {
        k: hb.get(k) for k in ("coopWaitText", "warningText", "selectedId")}
    assert hb.get("selectedId") != unit_id, hb.get("selectedId")
    print("PASS resume: the host's click on the client's cannon is refused")


def main():
    require_mods()
    js = shared_fixture.bring_up(
        TAG, (49670, 49671, 48970), mods=(MOD_40K, MOD_ROSIGMA),
        campaign_mode="coop", host_difficulty=0, client_difficulty=GUARD,
        transport="tcp")
    host, client = js.host, js.client
    host2 = client2 = None
    try:
        craft = prepare_faction_force(host, client, "ClientPlayer", CLIENT_SEAT,
                                      "ClientBase", CRAFT, CREW)
        start_finale(host, client, "ClientPlayer", "ClientBase", craft,
                     MISSION, DEPLOYMENT, race=RACE)
        wait_for_cannon(host, client)
        unit_id = assert_cannon_seat(host, client, "spawn")

        before = set(session.save_files(host.user_dir))
        host.ok({"cmd": "save_game_ui", "type": "quick_battle"})
        host.wait_for("host quick-save written",
                      lambda: sorted(set(session.save_files(host.user_dir)) - before) or None,
                      timeout=60, interval=0.5)
        saved = sorted(set(session.save_files(host.user_dir)) - before)
        assert len(saved) == 1 and saved[0].endswith(".asav"), saved
        path = os.path.join(host.user_dir, saved[0])
        session.assert_client_zero_disk(client.user_dir)
        js.shutdown()
        downgrade_saved_seat(path, unit_id)

        host2 = GameClient("host", 49672, host.user_dir)
        client2 = GameClient("client", 49673, make_user_dir(
            TAG + "_client2", mods=(MOD_40K, MOD_ROSIGMA)))
        host2.spawn(); client2.spawn()
        host2.connect(timeout=180); client2.connect(timeout=180)
        session.resume_campaign_battle(host2, client2, os.path.basename(path),
                                       port="48971", timeout=240)
        session.press_back_when_shown(host2, "host RESUME", codes=(60, 62))
        for gc in (host2, client2):
            gc.wait_for(f"{gc.name} on the resumed tactical view",
                        lambda gc=gc: top(gc) == "BattlescapeState" or None,
                        timeout=90, interval=0.5)
        assert_cannon_seat(host2, client2, "resume")
        assert_client_commands(host2, client2, unit_id)
        print("PASS ROSIGMA client craft cannon stays the client's after a save and resume")
    finally:
        js.shutdown()
        for gc in (host2, client2):
            if gc:
                gc.shutdown()


if __name__ == "__main__":
    main()
