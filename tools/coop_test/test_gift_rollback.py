"""Autonomous test: host save = single source of truth for soldier gifts.

Exact user repro:
  1. new game, host + client connected
  2. host gifts unit A to client
  3. host saves game
  4. host gifts unit B to client
  5. host abandons (in-session: statics survive, like returning to main menu)
  6. host loads the save, client re-fetches its world from the host
  7. EXPECTED: host owns B (not A), client owns A (not B), no bogus notices

Separate is one host-owned world, so both soldiers stay in that world and a
gift changes the owner. The test follows each soldier by id and checks its
owner on both machines.

Also runs the reverse direction (client gives, host's save still authority)
and the stacked-notice color check.

Run:  python tools/coop_test/test_gift_rollback.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
from test_bug_fixes import bootstrap_fresh_session


def soldier_by_id(gc, sid):
    """(base name, soldier) for soldier id <sid> in this machine's world."""
    found = [(b["name"], s) for b in gc.ok({"cmd": "get_soldiers"})["bases"]
             for s in b["soldiers"] if s["id"] == sid]
    assert len(found) <= 1, f"soldier id {sid} appears twice in one world: {found}"
    return found[0] if found else (None, None)


def owner_of(gc, sid):
    s = soldier_by_id(gc, sid)[1]
    return s["owner"] if s else None


def dismiss_all_notices(gc):
    while gc.cmd({"cmd": "dismiss_notice"}).get("ok"):
        pass


def no_notices(gc):
    return not any("GiftNoticeState" in s for s in gc.cmd({"cmd": "get_state"})["states"])


def gift_and_wait(host, giver, receiver, sid, name, receiver_owner_id):
    giver.ok({"cmd": "gift", "name": name, "owner": receiver_owner_id})
    receiver.wait_for(f"{name} arrives",
                      lambda: (owner_of(receiver, sid) == receiver_owner_id) or None, timeout=30)
    # Separate is one host-owned world: the host's world, and so its next save,
    # holds the gift once the host shows the new owner.
    host.wait_for(f"{name} owned by seat {receiver_owner_id} in the host world",
                  lambda: (owner_of(host, sid) == receiver_owner_id) or None, timeout=30)
    dismiss_all_notices(receiver)


def run_repro(host, client, giver, receiver, receiver_owner_id, tag):
    giver_owner_id = 1 - receiver_owner_id
    # unique names (fresh saves can roll identical rosters), set through the
    # real rename path so both machines of the one world agree on them
    # One world holds both bases; the giver's soldiers live at its own base.
    base_name = "HostBase" if giver is host else "ClientBase"
    base = next(b for b in giver.ok({"cmd": "get_soldiers"})["bases"] if b["name"] == base_name)
    roster = [s for s in base["soldiers"] if s["owner"] == giver_owner_id]
    (id_a, id_b) = (roster[0]["id"], roster[1]["id"])
    unit_a, unit_b = f"Unit A {tag}", f"Unit B {tag}"
    for sid, name in ((id_a, unit_a), (id_b, unit_b)):
        giver.ok({"cmd": "soldier_rename", "soldierId": sid, "name": name, "base": base["name"]})
        for gc in (host, client):
            gc.wait_for(f"{name} renamed on {gc.name}",
                        lambda gc=gc, sid=sid, name=name: (soldier_by_id(gc, sid)[1] or {}).get("name") == name or None,
                        timeout=30)

    # 2. gift A
    gift_and_wait(host, giver, receiver, id_a, unit_a, receiver_owner_id)

    # 3. HOST saves (the authority snapshot: A traded, B not)
    host.ok({"cmd": "save_game", "file": f"authority_{tag}.sav"})

    # 4. gift B
    gift_and_wait(host, giver, receiver, id_b, unit_b, receiver_owner_id)

    # 5+6. host "abandons" and loads the save; client re-fetches its world
    host.ok({"cmd": "load_save", "file": f"authority_{tag}.sav"})
    client.ok({"cmd": "client_reload_progress"})

    # A stays traded (pre-save), B goes back to the giver (post-save trade rolled back)
    expected = lambda: (owner_of(client, id_a) == receiver_owner_id
                        and owner_of(client, id_b) == giver_owner_id) or None
    client.wait_for("client world reloaded from host save", expected, timeout=90)

    # 7. assertions: the save is the authority, on both machines
    for gc in (giver, receiver):
        assert owner_of(gc, id_a) == receiver_owner_id, \
            f"{tag}: {gc.name} must show {unit_a} owned by seat {receiver_owner_id} (traded before save)"
        assert owner_of(gc, id_b) == giver_owner_id, \
            f"{tag}: {gc.name} must show {unit_b} back with seat {giver_owner_id} (trade B was after the save)"
    assert no_notices(host) and no_notices(client), f"{tag}: no bogus 'returned' notices allowed"
    print(f"PASS {tag}: save is authority - A stays traded, B rolled back, no notices")


def test_stacked_notices(gc):
    for i in range(3):
        gc.ok({"cmd": "show_notice", "message": f"stacked notice {i + 1}"})
    cats = gc.ok({"cmd": "get_notices"})["categories"]
    assert cats == ["geoManufactureComplete"] * 3, f"wrong categories: {cats}"
    for _ in range(3):
        gc.ok({"cmd": "dismiss_notice"})
    print("PASS stacked notices: all 3 use geoscape popup colors")


def main():
    host = GameClient("host", 47801, make_user_dir("host-user"))
    client = GameClient("client", 47802, make_user_dir("client-user"))
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        bootstrap_fresh_session(host, client)

        test_stacked_notices(host)

        run_repro(host, client, giver=host, receiver=client, receiver_owner_id=1, tag="h2c")
        run_repro(host, client, giver=client, receiver=host, receiver_owner_id=0, tag="c2h")

        print("TEST PASSED")
    finally:
        host.shutdown(); client.shutdown()


if __name__ == "__main__":
    main()
