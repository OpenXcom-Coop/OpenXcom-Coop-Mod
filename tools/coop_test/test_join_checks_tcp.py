"""test_join_checks_tcp.py: a TCP lobby join is refused when the two games differ in build version or mod list.

The joins are join_tcp (the call Direct Connect TCP and a saved TCP server make) and, against a host with a password,
the password challenge and its retry (PasswordCheckMenu). Machines and cell rules: join_checks.py.

  tcp_build        the joiner reports another build version             refused
  tcp_empty_build  the host reports an empty build version               refused
  tcp_empty_mods   the host reports an empty mod list                    refused
  tcp_mod_version  the joiner loads mod A at version 2.0 (host 1.0)      refused
  tcp_load_order   the joiner loads B before A                           refused
  tcp_match        nothing differs                                       joined
  pw_*             the same six against a host with a password. A refused join shows the incompatible-mods screen
                   and never the password prompt; pw_match answers the prompt and joins.

ONE run; exit 0 only all PASS, else 2."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from repro_atom_kneel import skirmish_client_at_browser
import join_checks as jc
import session

PASSWORD = "joinpw"
KEYS = iter(range(49311, 49340))   # one lobby key per hosted lobby (in-process only)


def host_lobby(host, password):
    key = str(next(KEYS))
    host.ok({"cmd": "open_new_battle"})
    host.wait_for("host new battle", lambda: session.has_state(host, "NewBattleState"))
    host.ok({"cmd": "newbattle_coop"})
    host.wait_for("host browser", lambda: session.has_state(host, "ServerList"))
    host.ok({"cmd": "server_list_host"})
    host.wait_for("host window", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv", "port": key,
             "player": "HostPlayer", "password": password})
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"))
    return key


def cell(name, host, client, want, password=False, host_id=None, client_id=None):
    # a password of its own per cell: a client keeps the last password it typed, which would answer the next
    # host's challenge before it is asked
    password = PASSWORD + "-" + name if password else ""
    jc.to_menu(host, client)
    ids = {}
    if host_id is not None:
        ids["host"] = jc.identity(host, **host_id)
    if client_id is not None:
        ids["client"] = jc.identity(client, **client_id)
    key = host_lobby(host, password)
    skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": "ClientPlayer"})
    outcome, seen, last = jc.watch(client)
    extra = {"identity": ids, "password": bool(password)}
    if outcome == "password" and want == "joined":
        client.ok({"cmd": "password_join", "password": password})
        outcome, more, last = jc.watch(client)
        seen |= more
        seen.discard("PasswordCheckMenu")   # the matching join answers the prompt; only a refused join may not see it
        extra["answeredPrompt"] = True
    elif outcome == "password":
        # a refused cell that shows the prompt already failed; answer it to record what the retry then does
        client.ok({"cmd": "password_join", "password": password})
        retry, _, retry_last = jc.watch(client)
        extra["retryAfterPrompt"] = {"outcome": retry, "last": retry_last}
    return jc.judge(name, want, outcome, seen, last, client, extra=extra)


def main():
    host, same, modver, order = jc.machines("jchk_tcp")
    games = (host, same, modver, order)
    fails = []
    t0 = time.time()
    try:
        for gc in games:
            gc.spawn()
            gc.connect()
        for gc in games:
            jc.evidence("identity_" + gc.name, jc.identity(gc))
        for prefix, pw in (("tcp", False), ("pw", True)):
            fails += cell(prefix + "_build", host, same, "refused", pw, client_id={"version": jc.OTHER_BUILD})
            fails += cell(prefix + "_empty_build", host, same, "refused", pw, host_id={"version": ""})
            fails += cell(prefix + "_empty_mods", host, same, "refused", pw, host_id={"mods": []})
            fails += cell(prefix + "_mod_version", host, modver, "refused", pw)
            fails += cell(prefix + "_load_order", host, order, "refused", pw)
            fails += cell(prefix + "_match", host, same, "joined", pw)
    except Exception as e:  # a staging step that could not run is a failure of the whole run
        fails.append("setup: %s" % e)
        print("FAIL setup: %s" % e, flush=True)
    finally:
        fails += jc.shutdown(host, (same, modver, order), rendezvous_host=False)
    print("wall %.1f s" % (time.time() - t0), flush=True)
    print("RESULT %s (%d failure(s))" % ("PASS" if not fails else "FAIL", len(fails)), flush=True)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
