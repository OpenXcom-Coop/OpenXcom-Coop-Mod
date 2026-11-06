"""test_join_checks_udp.py: a UDP lobby join is refused when the two games differ in build version or mod list.

Two join paths, each with the six cells of test_join_checks_tcp.py (machines and cell rules: join_checks.py):
  udp_*     join_udp to a host_udp campaign lobby: the UDP transport on 127.0.0.1 without a rendezvous server.
  online_*  the online server list, served by rendezvous_stub.py: the host opens a PUBLIC room with a password
            (HOST > PUBLIC), the joiner clicks its row in the server browser (server_list_join). A different or empty
            build version keeps the room out of the joiner's list (the stub filters the list by version, as the
            real server does), so those two cells join by room id instead (join_rendezvous, with the password).
            A refused join shows the incompatible-mods screen and never the password prompt; online_match answers
            the prompt and joins.

ONE run; exit 0 only all PASS, else 2."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import EXE, TEST_ROOT, HARNESS_SLOT
from repro_atom_kneel import skirmish_client_at_browser
from rendezvous_stub import RendezvousStub
import join_checks as jc
import session

PASSWORD = "joinpw"
UDP_SESSION = "harness-lan-s%d" % HARNESS_SLOT   # the direct UDP session key (one per harness lane)
KEYS = iter(range(49341, 49370))                  # one lobby key per hosted lobby (in-process only)
HOSTS = iter(range(1, 100))                       # one host player name per room, so each room is told apart
ROW_WAIT_S = 20.0


def udp_lobby(host):
    key = str(next(KEYS))
    host.ok({"cmd": "open_new_game", "mode": "coop"})
    host.wait_for("host difficulty", lambda: session.has_state(host, "NewGameState"))
    host.ok({"cmd": "newgame_ok"})
    host.wait_for("host window", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_udp", "port": key, "player": "HostPlayer", "password": UDP_SESSION, "campaign": True})
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"))
    return key


def udp_cell(name, host, client, want, host_id=None, client_id=None):
    jc.to_menu(host, client)
    ids = {}
    if host_id is not None:
        ids["host"] = jc.identity(host, **host_id)
    if client_id is not None:
        ids["client"] = jc.identity(client, **client_id)
    key = udp_lobby(host)
    client.ok({"cmd": "join_udp", "ip": "127.0.0.1", "port": key, "localport": "0", "player": "ClientPlayer",
               "password": UDP_SESSION, "campaign": True})
    outcome, seen, last = jc.watch(client, timeout=45)
    return jc.judge(name, want, outcome, seen, last, client, extra={"identity": ids})


def public_room(host, stub, password):
    player = "HostPlayer%d" % next(HOSTS)
    host.ok({"cmd": "open_new_battle"})
    host.wait_for("host new battle", lambda: session.has_state(host, "NewBattleState"))
    host.ok({"cmd": "newbattle_coop"})
    host.wait_for("host browser", lambda: session.has_state(host, "ServerList"))
    host.ok({"cmd": "server_list_host"})
    host.wait_for("host window", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_menu_host", "visibility": 2, "server": "TestSrv", "port": str(next(KEYS)),
             "player": player, "password": password})
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"), timeout=60)
    room = stub.wait_room(player, timeout=30)
    if not room:
        raise AssertionError("no stub room by %s within 30 s" % player)
    return room


def rows(client):
    return client.ok({"cmd": "server_list_rows"}).get("rows", [])


def listed(client, room, wait_s):
    """Press REFRESH about once a second until the room's row is listed or wait_s passes. Returns the row or None."""
    end = time.time() + wait_s
    while True:
        hit = next((r for r in rows(client) if r.get("id") == room), None)
        if hit or time.time() >= end:
            return hit
        client.ok({"cmd": "server_list_refresh"})
        t = time.time() + 1.0
        while time.time() < t:
            hit = next((r for r in rows(client) if r.get("id") == room), None)
            if hit:
                return hit
            time.sleep(0.05)


def online_cell(name, host, client, stub, want, by_id=False, host_id=None, client_id=None):
    password = PASSWORD + "-" + name   # a room password of its own per cell, as in test_join_checks_tcp.py
    jc.to_menu(host, client)
    ids = {}
    if host_id is not None:
        ids["host"] = jc.identity(host, **host_id)
    if client_id is not None:
        ids["client"] = jc.identity(client, **client_id)
    e0 = len(stub.events("ERROR"))
    room = public_room(host, stub, password)
    skirmish_client_at_browser(client)
    extra = {"identity": ids, "room": room, "byId": by_id}
    if by_id:
        extra["listedForJoiner"] = listed(client, room, 3.0)
        client.ok({"cmd": "join_rendezvous", "room": room, "player": "ClientPlayer", "password": password})
    else:
        row = listed(client, room, ROW_WAIT_S)
        extra["row"] = row
        if not row:
            raise AssertionError("%s: room %s never listed in the joiner's server browser" % (name, room))
        client.ok({"cmd": "server_list_join", "room": room, "player": "ClientPlayer"})
    outcome, seen, last = jc.watch(client, timeout=45)
    if outcome == "password" and want == "joined":
        client.ok({"cmd": "password_join", "password": password})
        outcome, more, last = jc.watch(client, timeout=45)
        seen |= more
        seen.discard("PasswordCheckMenu")   # the matching join answers the prompt; only a refused join may not see it
        extra["answeredPrompt"] = True
    elif outcome == "password":
        # a refused cell that shows the prompt already failed; answer it to record what the retry then does
        client.ok({"cmd": "password_join", "password": password})
        retry, _, retry_last = jc.watch(client, timeout=45)
        extra["retryAfterPrompt"] = {"outcome": retry, "last": retry_last}
    extra["stubErrors"] = [e.get("message") for e in stub.events("ERROR")][e0:]
    return jc.judge(name, want, outcome, seen, last, client, extra=extra)


def main():
    t0 = time.time()
    hdir = os.path.join(TEST_ROOT, "s%d_jchk_udp_stub" % HARNESS_SLOT)
    os.makedirs(hdir, exist_ok=True)
    log = os.path.join(hdir, "stub_events.jsonl")
    if os.path.exists(log):
        os.remove(log)
    stub = RendezvousStub(dll_dir=os.path.dirname(EXE), log_path=log).start()
    os.environ["OXC_RENDEZVOUS_CONFIG"] = stub.write_config(os.path.join(hdir, "stub.json"))  # before any spawn
    host, same, modver, order = jc.machines("jchk_udp")
    games = (host, same, modver, order)
    fails = []
    try:
        for gc in games:
            gc.spawn()
            gc.connect()
        for gc in games:
            jc.evidence("identity_" + gc.name, jc.identity(gc))
        fails += udp_cell("udp_build", host, same, "refused", client_id={"version": jc.OTHER_BUILD})
        fails += udp_cell("udp_empty_build", host, same, "refused", host_id={"version": ""})
        fails += udp_cell("udp_empty_mods", host, same, "refused", host_id={"mods": []})
        fails += udp_cell("udp_mod_version", host, modver, "refused")
        fails += udp_cell("udp_load_order", host, order, "refused")
        fails += udp_cell("udp_match", host, same, "joined")
        fails += online_cell("online_build", host, same, stub, "refused", by_id=True,
                             client_id={"version": jc.OTHER_BUILD})
        fails += online_cell("online_empty_build", host, same, stub, "refused", by_id=True, host_id={"version": ""})
        fails += online_cell("online_empty_mods", host, same, stub, "refused", host_id={"mods": []})
        fails += online_cell("online_mod_version", host, modver, stub, "refused")
        fails += online_cell("online_load_order", host, order, stub, "refused")
        fails += online_cell("online_match", host, same, stub, "joined")
    except Exception as e:  # a staging step that could not run is a failure of the whole run
        fails.append("setup: %s" % e)
        print("FAIL setup: %s" % e, flush=True)
    finally:
        fails += jc.shutdown(host, (same, modver, order), rendezvous_host=True)
        stub.stop()
        os.environ.pop("OXC_RENDEZVOUS_CONFIG", None)
    print("wall %.1f s" % (time.time() - t0), flush=True)
    print("RESULT %s (%d failure(s))" % ("PASS" if not fails else "FAIL", len(fails)), flush=True)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
