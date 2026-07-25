"""Issues #79 / #81: the "Waiting for <player> to reconnect..." dialog.

Two complaints about the same dialog, so one suite:

  #79  After a SHARED campaign ends in DEFEAT, the client clicks OK on the
       end-of-game statistics screen and leaves - and the host is pinned behind
       "Waiting for Jane Kelly to reconnect..." forever. There is nothing left
       to do together once the campaign has an ending, so a peer leaving must
       be SILENT on both sides and must not interrupt the other player's own
       end-of-game screens. Both directions are asserted (client-first and
       host-first), because "and vice-versa" is half the bug.

  #81  Every other time the dialog appears, the host is stuck for a different
       reason: the client left early and the host cannot even save. The dialog
       now carries two live buttons - SAVE & QUIT (save-slot list, then the
       main menu) and ABANDON GAME (main menu, nothing written) - on EVERY
       host-side campaign wait, not just the freeze dialog.

SCENARIOS
  DEFEAT-CLIENT   defeat, the client leaves first  -> no freeze dialog on the
                  host, host still reaches the main menu on its own OK.
  DEFEAT-HOST     defeat, the HOST leaves first    -> the client is not yanked
                  off its statistics screen and gets no "connection lost" popup.
  FREEZE-BUTTONS  mid-campaign client drop -> the freeze dialog (64) offers both
                  buttons.
  ABANDON         ABANDON GAME on the freeze dialog -> main menu, nothing on disk.
  SAVE-AND-QUIT   SAVE & QUIT on the freeze dialog -> real save-slot list, a .sav
                  on disk, then the main menu. This is the #81 headline: the save
                  must NOT wait on the client blob that will never arrive.
  RESUME-WAIT     the SAME escape hatch on the OTHER host wait dialog (62), where
                  a client that never finishes joining traps the host identically.

Run:  python tools/coop_test/test_reconnect_dialog.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT
import shared_fixture
import session
import geo

COOP_DLG_RESUME_ACK_WAIT = 62
COOP_DLG_FREEZE = 64

END_LOSE = 2


# ---------------------------------------------------------------- helpers --

def dialog(gc):
    """coop_dialog_info for the topmost CoopState anywhere on the stack."""
    return gc.ok({"cmd": "coop_dialog_info"})


def freeze_dialogs(gc):
    """How many freeze dialogs (64) sit ANYWHERE on gc's state stack.

    Deliberately not "is it on top": the #79 bug pushes the freeze dialog OVER
    the statistics screen, so only a whole-stack count can assert its absence.
    """
    return gc.ok({"cmd": "coop_dialog_count", "code": COOP_DLG_FREEZE})["count"]


def any_coop_dialog(gc):
    return gc.ok({"cmd": "coop_dialog_count", "code": -1})["count"]


def ending(gc):
    return gc.ok({"cmd": "ending_state"})


def drive_to_defeat(host, client):
    """Arm the campaign ending on the host and let the SHIPPED defeat path run:
    the host's own time5Seconds check -> lose cutscene (broadcast to the replica)
    -> end-of-game statistics on BOTH machines."""
    host.ok({"cmd": "set_ending", "ending": END_LOSE})

    # 5-second speed: the ending check lives in time5Seconds, so the clock has
    # to actually tick. Not skip_realtime - it drains popups, and the whole
    # point here is the popups the defeat produces.
    for gc in (host, client):
        gc.cmd({"cmd": "geo_set_speed", "idx": 0})

    for gc, who in ((host, "host"), (client, "client")):
        gc.wait_for(f"{who} reached the end-of-game statistics screen",
                    lambda gc=gc: ending(gc).get("statistics") or None,
                    timeout=90, interval=0.5)
    print("defeat: both machines on the end-of-game statistics screen")


def wait_peer_dropped(gc, what):
    """Block until gc's transport teardown has actually run for the peer drop.

    coopSession is cleared at the top of disconnectTCP, so it flips only once
    the machine has NOTICED the drop and started tearing down - which is the
    exact moment any 'peer vanished' dialog would be pushed. Asserting absence
    before this point would prove nothing.
    """
    gc.wait_for(what,
                lambda: (not gc.cmd({"cmd": "get_coop"}).get("coopSession")) or None,
                timeout=60, interval=0.5)


def wait_main_menu(gc, what):
    gc.wait_for(what, lambda: ending(gc).get("mainMenu") or None,
                timeout=60, interval=0.5)


def assert_escape_buttons(gc, code, tag):
    d = dialog(gc)
    assert d["present"], f"{tag}: no CoopState dialog at all: {d}"
    assert d["code"] == code, f"{tag}: expected dialog {code}, got {d}"
    assert d["saveQuitVisible"], f"{tag}: SAVE & QUIT missing: {d}"
    assert d["abandonVisible"], f"{tag}: ABANDON GAME missing: {d}"
    assert d["saveQuitText"] == "SAVE & QUIT", f"{tag}: {d['saveQuitText']!r}"
    assert d["abandonText"] == "ABANDON GAME", f"{tag}: {d['abandonText']!r}"
    # The buttons have to fit inside the window they are drawn in, or they are
    # decoration the player cannot click.
    assert d["windowHeight"] >= 52, f"{tag}: window too small for two buttons: {d}"
    return d


# --------------------------------------------------------- #79: defeat -----

def scenario_defeat_client_leaves_first():
    """#79 verbatim: SHARED defeat, the client clicks OK and goes to the main
    menu. The host must NOT be pinned behind a reconnect dialog."""
    js = shared_fixture.bring_up("rdlg_a", (49000, 49001, 48300))
    host, client = js.host, js.client
    try:
        drive_to_defeat(host, client)

        # the client leaves the finished campaign the only way the UI offers
        client.ok({"cmd": "statistics_ok"})
        wait_main_menu(client, "client back at the main menu after defeat")
        print("PASS client-exit: the client left the finished campaign")

        # Give the host every chance to do the wrong thing: the drop has to be
        # noticed (transport timeout + teardown) before absence means anything.
        wait_peer_dropped(host, "host noticed the client drop")
        time.sleep(5)

        n = freeze_dialogs(host)
        assert n == 0, (
            f"issue #79: the host got {n} 'waiting to reconnect' dialog(s) after "
            f"the campaign already ended - there is nothing left to reconnect for")
        e = ending(host)
        assert e["ending"] == END_LOSE, f"host lost its ending: {e}"
        assert e["statistics"], f"host was knocked off its statistics screen: {e}"
        print("PASS no-freeze: host kept its end-of-game screen, no reconnect dialog")

        # and the host can finish on its own, which is the actual complaint
        host.ok({"cmd": "statistics_ok"})
        wait_main_menu(host, "host reached the main menu after defeat")
        print("PASS host-exit: the host reached the main menu unaided")
    finally:
        js.shutdown()


def scenario_defeat_host_leaves_first():
    """#79 "and vice-versa": the HOST closes the finished campaign first. The
    client must not be dragged off its own statistics screen, and must get no
    "Server connection lost" popup."""
    js = shared_fixture.bring_up("rdlg_b", (49004, 49005, 48304))
    host, client = js.host, js.client
    try:
        drive_to_defeat(host, client)

        host.ok({"cmd": "statistics_ok"})
        wait_main_menu(host, "host back at the main menu after defeat")
        print("PASS host-exit-first: the host left the finished campaign")

        wait_peer_dropped(client, "client noticed the host drop")
        time.sleep(5)

        n = any_coop_dialog(client)
        assert n == 0, (
            f"issue #79: the client got {n} co-op popup(s) because the host "
            f"closed a FINISHED campaign first; the exit must be silent")
        e = ending(client)
        assert e["statistics"], (
            f"issue #79: the client was yanked off its own end-of-game screen "
            f"when the host left: {e}")
        print("PASS silent-drop: client kept its end-of-game screen, no popup")

        client.ok({"cmd": "statistics_ok"})
        wait_main_menu(client, "client reached the main menu after defeat")
        print("PASS client-exit: the client finished on its own terms")
    finally:
        js.shutdown()


# ------------------------------------------------- #81: the escape hatch ---

def _drop_client_into_freeze(js):
    """Hard-kill the client of a live SHARED session and wait for the host's
    freeze dialog. Returns the dialog info."""
    host = js.host
    js.client.proc.kill()
    js.client.proc.wait(timeout=10)
    wait_peer_dropped(host, "host noticed the client drop")
    try:
        host.wait_for(
            "host raised the reconnect dialog",
            lambda: (lambda d: (d.get("present") and d.get("code") == COOP_DLG_FREEZE) or None)(
                dialog(host)),
            timeout=120, interval=0.5)
    except TimeoutError:
        print("DEBUG host get_coop:", host.cmd({"cmd": "get_coop"}))
        print("DEBUG host dialog:  ", dialog(host))
        print("DEBUG host states:  ", host.cmd({"cmd": "get_state"})["states"])
        raise
    return dialog(host)


def scenario_freeze_buttons():
    """#81: the dialog a stranded host stares at must offer a way out."""
    js = shared_fixture.bring_up("rdlg_c", (49008, 49009, 48308))
    try:
        d = _drop_client_into_freeze(js)
        assert "reconnect" in d["title"], f"not the reconnect dialog: {d}"
        assert_escape_buttons(js.host, COOP_DLG_FREEZE, "freeze dialog")
        print(f"PASS freeze-buttons: {d['saveQuitText']!r} + {d['abandonText']!r} "
              f"offered on {d['title']!r}")

        # RESUME is still the primary action and still hidden until the peer is
        # back - the escape hatch must not have replaced it.
        assert not d["backVisible"], f"RESUME shown with nobody to resume: {d}"
        assert d["backText"] == "RESUME", f"back button repurposed: {d}"
        print("PASS freeze-resume: RESUME still hidden until the peer returns")
    finally:
        js.shutdown()


def scenario_abandon():
    """#81: ABANDON GAME leaves immediately and writes nothing."""
    js = shared_fixture.bring_up("rdlg_d", (49012, 49013, 48312))
    host = js.host
    try:
        _drop_client_into_freeze(js)
        before = session.save_files(js.host_dir)

        host.ok({"cmd": "coop_dialog_abandon"})
        wait_main_menu(host, "host reached the main menu via ABANDON GAME")

        assert freeze_dialogs(host) == 0, "the freeze dialog survived ABANDON GAME"
        after = session.save_files(js.host_dir)
        assert after == before, (
            f"ABANDON GAME must write nothing; user dir changed {before} -> {after}")
        print("PASS abandon: straight to the main menu, nothing written")
    finally:
        js.shutdown()


def scenario_save_and_quit():
    """#81 headline: SAVE & QUIT writes a real save through the real save-slot
    list, then leaves. The write must not stall waiting for the client blob
    that is never coming - that stall IS the bug."""
    js = shared_fixture.bring_up("rdlg_e", (49016, 49017, 48316))
    host = js.host
    try:
        _drop_client_into_freeze(js)
        before = set(session.save_files(js.host_dir))

        host.ok({"cmd": "coop_dialog_save_quit"})
        host.wait_for("save-slot list opened",
                      lambda: session.has_state(host, "ListSaveState"),
                      timeout=30, interval=0.5)
        print("PASS save-quit-list: SAVE & QUIT opened the save-slot list")

        host.ok({"cmd": "list_save_confirm", "name": "stranded_host"})

        # bounded: if the host-save deferral were still armed, this never ends
        host.wait_for("host reached the main menu after saving",
                      lambda: ending(host).get("mainMenu") or None,
                      timeout=60, interval=0.5)

        after = set(session.save_files(js.host_dir))
        new = sorted(after - before)
        assert any(f.endswith(".sav") for f in new), (
            f"SAVE & QUIT wrote no save file (user dir gained {new})")
        print(f"PASS save-quit: wrote {new} and returned to the main menu")
    finally:
        js.shutdown()


def scenario_resume_wait_buttons():
    """#81 for the OTHER host wait dialog. A client that joins and then dies
    before acking the streamed world leaves the host in COOP_DLG_RESUME_ACK_WAIT
    (62), which deliberately suppresses the freeze dialog - so 62 has to carry
    the escape hatch itself or the host is trapped with no dialog that does."""
    host_dir = make_user_dir("rdlg_f_host")
    client_dir = make_user_dir("rdlg_f_client")
    host = GameClient("host", 49020, host_dir)
    client = GameClient("client", 49021, client_dir)
    port = "48320"
    try:
        host.spawn()
        client.spawn()
        host.connect()
        client.connect()

        # SHARED bring-up by hand, stopping at the resume-ack wait instead of
        # releasing it (session.new_campaign clicks BEGIN for you).
        host.ok({"cmd": "open_new_game", "mode": "shared"})
        host.wait_for("difficulty", lambda: session.has_state(host, "NewGameState"))
        host.ok({"cmd": "newgame_ok"})
        host.wait_for("host window", lambda: session.has_state(host, "HostMenu"))
        host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": port,
                 "player": "HostPlayer"})
        host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"))

        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port,
                   "player": "ClientPlayer"})
        client.wait_for("client lobby", lambda: session.has_state(client, "LobbyMenu"))
        for gc in (host, client):
            gc.wait_for("join popup", lambda gc=gc: session.has_state(gc, "Profile"))
            gc.ok({"cmd": "profile_ok"})

        host.wait_for("start eligible",
                      lambda: host.cmd({"cmd": "lobby_state"}).get("startEligible") or None)
        host.ok({"cmd": "lobby_start_campaign"})
        host.wait_for("host base placement",
                      lambda: session.has_state(host, "BuildNewBaseState"))
        r = host.cmd({"cmd": "place_first_base", "lon": session.HOST_LON,
                      "lat": session.HOST_LAT, "name": "HostBase"})
        if not r.get("ok"):
            host.ok({"cmd": "place_first_base", "lon": LAND_LON, "lat": LAND_LAT,
                     "name": "HostBase"})

        host.wait_for(
            "host holding in the resume-ack wait",
            lambda: (lambda d: (d.get("present")
                                and d.get("code") == COOP_DLG_RESUME_ACK_WAIT) or None)(
                dialog(host)),
            timeout=120, interval=0.5)

        # the client dies before the host ever releases the hold
        client.proc.kill()
        client.proc.wait(timeout=10)

        # the host stays in 62 (which suppresses the freeze dialog on purpose)
        wait_peer_dropped(host, "host noticed the drop")
        time.sleep(3)

        d = assert_escape_buttons(host, COOP_DLG_RESUME_ACK_WAIT, "resume-ack wait")
        print(f"PASS resume-wait-buttons: escape hatch offered on {d['title']!r}")

        host.ok({"cmd": "coop_dialog_abandon"})
        wait_main_menu(host, "host escaped the resume-ack wait")
        print("PASS resume-wait-abandon: the host is no longer trapped")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    scenario_defeat_client_leaves_first()
    scenario_defeat_host_leaves_first()
    scenario_freeze_buttons()
    scenario_abandon()
    scenario_save_and_quit()
    scenario_resume_wait_buttons()
    print("ALL RECONNECT DIALOG TESTS PASSED")


if __name__ == "__main__":
    main()
