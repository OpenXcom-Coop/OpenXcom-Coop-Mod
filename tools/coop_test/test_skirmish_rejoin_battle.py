"""Issue #93: rejoining a SKIRMISH battle, and what happens when the HOST leaves.

Ruling 1 of the issue says a peer dropping mid-battle raises the reconnect
dialog - "waiting for X" with SAVE & QUIT / ABANDON GAME while nobody is there,
"All players connected" / RESUME once they are back. In a NEW BATTLE > COOP
session the second half was unreachable: nothing let a client rejoin a running
skirmish battle, so the dialog could only ever be escaped by quitting.

A skirmish battle is streamed as ONE live snapshot ("battlehost" -> the client
loads it as "battleclient"), which is exactly what a rejoiner needs. This suite
covers the wiring that lets the host serve that snapshot to a returning player:

  REJOIN     the client comes back mid-battle -> it lands in the RUNNING battle
             (not a lobby, not a new campaign) and holds; the host's dialog flips
             to "All players connected" with RESUME.
  RESUME     the host presses RESUME -> both machines are on the tactical map,
             connected, with the co-op battle handshake re-armed and command of
             the squad split between them again.
  HOST-LEAVE (ruling 4) the HOST walks out of a skirmish battle -> the client is
             told, stays frozen behind the message, and lands on the main menu
             when it acknowledges. It must never be handed the battle to finish
             on its own.
  CAMPAIGN-HOST-LEAVE the same for a SHARED campaign mission.
  SEAT-LEFT-END (SPEC 16 W1-P17 M6/DP1, S4) from that same frozen pause, the
             remaining player presses SAVE & QUIT / ABANDON GAME -> a LOCAL
             teardown to the main menu, no debrief, `reason:"seatLeft"` logged.

Run:  python tools/coop_test/test_skirmish_rejoin_battle.py
"""

import os
import sys
import time

# SPEC 16 (W1-P17) cycle 2: scenario_rejoin_and_resume (S3) is un-skipped and
# re-pointed at the r4 rejoin-restream handshake (M5) + the both-machines
# pause/resume modal (M3).
#
# cycle 3 (M6 + M4): scenario_host_leaves_skirmish/
# scenario_host_leaves_campaign_battle (S5, already correct per issue #93's
# original ruling 4 - unaffected by M1/M2/M5/M3) are now wired into main().
# scenario_seat_left_end (S4, DP1/M6) is new. _fly_shared_squad_into_a_battle
# is lifted verbatim from test_resume_game_in_battle.py (same precedent as
# the drop/freeze primitives above) rather than imported: that file's own
# SKIP-PENDING(R4-P2) is still a module-level sys.exit(0), so importing it
# would kill this process too - un-skipping it for real is a separate,
# wider-scoped job this cycle was not asked to take on.

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import shared_fixture
import test_skirmish_flow as SK

# ------------------------------------------------------------ lifted from --
# test_resume_game_in_battle.py (issue #93's own SKIP-PENDING(R4-P2) still
# guards that file's module body with a top-level sys.exit(0), so it cannot
# be imported from here yet - these are its small state/dialog probes and its
# drop/freeze primitives, copied verbatim rather than imported, exactly the
# alternative the SPEC 16 cycle-2 brief allows ("fix helper imports ... or
# lift the needed helpers"). Keep them in sync with that file's own copies
# when it is un-skipped in a later cycle.

def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top(gc):
    return states(gc)[-1].split("::")[-1]


def has(gc, name):
    return any(name in s for s in states(gc))


def in_battle_save(gc):
    """The world carries a SavedBattleGame (independent of the UI stack)."""
    return bool(gc.cmd({"cmd": "get_coop"}).get("inBattle"))


def dialog(gc):
    return gc.cmd({"cmd": "coop_dialog_info"})


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def settle_on_tactical(gc, tag, timeout=180):
    """Walk briefing / pre-battle inventory / popups until the tactical map is
    the top state, exactly as a player would."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = top(gc)
        if t == "BattlescapeState":
            return
        if t == "BriefingState":
            gc.cmd({"cmd": "close_briefing"})
        elif t == "InventoryState":
            gc.cmd({"cmd": "battle_inventory", "action": "ok"})
        else:
            gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.5)
    raise AssertionError(f"{tag}: never settled on the tactical map: {states(gc)}")


def wait_peer_dropped(gc, what):
    gc.wait_for(what,
                lambda: (not gc.cmd({"cmd": "get_coop"}).get("coopSession")) or None,
                timeout=90, interval=0.5)


COOP_DLG_WAIT_PLAYERS = 62
COOP_DLG_CLIENT_RESUME_HOLD = 68
COOP_DLG_CONNECTION_LOST = 21


def log_lines(user_dir):
    """S4 (DP1/M6): `reason:"seatLeft"` is logged only - there is no probe
    for it (F335: no `battle_end` atom exists in wave 1) - so read it
    straight from the instance's own openxcom.log, the same pattern
    test_cydonia_coop_start.py/test_coop_basedef_temp_ufo_uaf.py already use."""
    log = os.path.join(user_dir, "openxcom.log")
    with open(log, "r", errors="replace") as f:
        return f.readlines()


def start_skirmish_battle(host, client, port):
    """NEW BATTLE > COOP > lobby > BATTLE SETTINGS > OK, both on the tactical map."""
    SK.skirmish_host(host, port)
    SK.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port,
               "player": "ClientPlayer"})
    for gc in (host, client):
        gc.wait_for("join popup", lambda gc=gc: session.has_state(gc, "Profile"))
        gc.ok({"cmd": "profile_ok"})
    host.wait_for("BATTLE SETTINGS offered",
                  lambda: lobby(host).get("buttonVisible") or None)
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at the setup screen",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    host.ok({"cmd": "newbattle_ok"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} in the battle",
                    lambda gc=gc: in_battle_save(gc) or None, timeout=180, interval=1.0)
        settle_on_tactical(gc, tag)


def drop_client_mid_battle(host, client):
    """The client leaves the battle for the main menu; returns once the host
    has raised its dialog."""
    client.cmd({"cmd": "disconnect_to_menu"})
    client.wait_for("client at the main menu",
                    lambda: (top(client) == "MainMenuState") or None,
                    timeout=60, interval=0.5)
    wait_peer_dropped(host, "host noticed the drop")
    host.wait_for("host raised the reconnect dialog",
                  lambda: (lambda d: (d.get("present")
                                      and d.get("code") == COOP_DLG_WAIT_PLAYERS) or None)(
                      dialog(host)),
                  timeout=90, interval=0.5)


def assert_frozen_over_the_battle(host, tag):
    """The shared assertion of the drop scenarios: the reconnect dialog, over an
    intact battle, with no lobby and no way to play on."""
    d = dialog(host)
    assert d["code"] == COOP_DLG_WAIT_PLAYERS, f"{tag}: wrong dialog: {d}"
    assert "reconnect" in d["title"], f"{tag}: not the reconnect wording: {d}"
    assert d["saveQuitVisible"] and d["abandonVisible"], \
        f"{tag}: no way out of the freeze: {d}"
    assert not d["backVisible"], \
        f"{tag}: RESUME offered with nobody to resume: {d}"
    assert not has(host, "LobbyMenu"), (
        f"issue #93 ({tag}): the coop LOBBY was raised over the battle instead of "
        f"the reconnect dialog: {states(host)}")
    assert has(host, "BattlescapeState"), \
        f"{tag}: the battle was torn down by the drop: {states(host)}"
    assert in_battle_save(host), f"{tag}: the world lost its battle: {states(host)}"
    assert top(host) == "CoopState", \
        f"{tag}: the freeze dialog is not the top state: {states(host)}"
    return d


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def rejoin_skirmish(client, port, player="ClientPlayer"):
    """A returning player: NEW BATTLE > COOP > browser > join."""
    client.ok({"cmd": "open_new_battle"})
    client.wait_for("new battle", lambda: session.has_state(client, "NewBattleState"))
    client.ok({"cmd": "newbattle_coop"})
    client.wait_for("browser", lambda: session.has_state(client, "ServerList"))
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": player})


def clear_popups(gc, rounds=10):
    """Dismiss join popups (Profile) without touching a CoopState dialog."""
    for _ in range(rounds):
        if session.has_state(gc, "Profile"):
            gc.cmd({"cmd": "profile_ok"})
            time.sleep(0.5)
        else:
            return


# ----------------------------------------------------------- REJOIN/RESUME --

def scenario_rejoin_and_resume():
    print("\n===== scenario REJOIN / RESUME =====")
    port = "47997"
    host = GameClient("host", 48810, make_user_dir("i93_rj_host"))
    client = GameClient("client", 48811, make_user_dir("i93_rj_client"))
    client2 = GameClient("client2", 48812, make_user_dir("i93_rj_client2"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        start_skirmish_battle(host, client, port)
        before = battle(host)
        # the split the pair had BEFORE the drop is the yardstick for the rejoin:
        # the returning player must get its own units back, not zero of them.
        before_sel = {tag: sorted(u["id"] for u in battle(gc).get("units", [])
                                  if u.get("selectable"))
                      for tag, gc in (("host", host), ("client", client))}
        print(f"PASS entry: both on the skirmish tactical map, turn "
              f"{before.get('turn')}, command split {before_sel}")

        drop_client_mid_battle(host, client)
        assert_frozen_over_the_battle(host, "REJOIN")
        print(f"PASS freeze: host held on {dialog(host)['title']!r}")

        # the player comes back in a fresh process (the report's flow: they went
        # all the way out to the main menu)
        client2.spawn(); client2.connect()
        rejoin_skirmish(client2, port)

        # REJOIN: the returning client must land in the RUNNING battle, held.
        client2.wait_for("client2 back in the battle",
                         lambda: in_battle_save(client2) or None, timeout=240, interval=1.0)
        assert has(client2, "BattlescapeState"), (
            f"issue #93 REJOIN: the rejoining player did not reach the battle "
            f"(stack={states(client2)}); a skirmish rejoin used to land in a lobby")
        assert not has(client2, "LobbyMenu"), \
            f"REJOIN: the rejoiner was parked in a lobby: {states(client2)}"
        hold = dialog(client2)
        assert hold.get("code") == COOP_DLG_CLIENT_RESUME_HOLD, (
            f"REJOIN: the rejoiner is not held until the host resumes: {hold} "
            f"(stack={states(client2)})")
        print(f"PASS rejoin-client: landed in the running battle, held on "
              f"{hold.get('title')!r}")

        # ...and the host's freeze dialog flips to the ready half. The join also
        # lands a "<player> has joined" popup on top of it, and a dialog only
        # think()s while it is the top state, so clear that as it appears.
        def _resume_offered():
            if session.has_state(host, "Profile"):
                host.cmd({"cmd": "profile_ok"})
                return None
            return dialog(host).get("backVisible") or None

        host.wait_for("host dialog offers RESUME", _resume_offered,
                      timeout=120, interval=0.5)
        d = dialog(host)
        assert d["code"] == COOP_DLG_WAIT_PLAYERS, f"REJOIN: wrong dialog: {d}"
        assert d["title"] == "All players connected", \
            f"issue #93 REJOIN: dialog did not report the peer's return: {d}"
        assert d["backText"] == "RESUME", f"REJOIN: action is not RESUME: {d}"
        assert not d["saveQuitVisible"] and not d["abandonVisible"], \
            f"REJOIN: the escape hatch outlived the wait: {d}"
        print(f"PASS rejoin-host: {d['title']!r} with {d['backText']!r}")

        # RESUME: both machines return to the battle they were in.
        host.ok({"cmd": "coop_dialog_back"})
        for gc, tag in ((host, "host"), (client2, "client")):
            gc.wait_for(f"{tag} back on the tactical map",
                        lambda gc=gc: (top(gc) == "BattlescapeState") or None,
                        timeout=120, interval=0.5)
        print("PASS resume: both machines are back on the tactical map")

        after = battle(host)
        assert after.get("turn") == before.get("turn"), \
            f"RESUME: the battle moved on during the drop: " \
            f"{before.get('turn')} -> {after.get('turn')}"

        # the co-op battle is live again on both machines, not two solo games.
        # NOTE (re-point, WV-D77 traced): the original pre-rewrite assertion
        # here also checked `battleInit` - a legacy flag whose only "= true"
        # writer lived in BattlescapeState.cpp's coop-init gate, deleted by
        # the r1 vanilla restore (grep across all of src/ finds zero "= true"
        # assignments left anywhere; every remaining site only ever clears
        # it). It is permanently false today, in a fresh battle exactly as
        # much as a resumed one, so it proves nothing here - `phase=="Active"`
        # is the CURRENT, meaningful "the co-op battle handshake actually
        # re-ran" signal (battle_state.phase, TestServer.cpp) and replaces it.
        for gc, tag in ((host, "host"), (client2, "client")):
            gc.wait_for(f"{tag} co-op session re-armed",
                        lambda gc=gc: (battle(gc).get("coopSession")
                                       and battle(gc).get("phase") == "Active") or None,
                        timeout=120, interval=0.5)
        hb, cb = battle(host), battle(client2)
        assert hb["coopSession"] and cb["coopSession"], \
            f"RESUME: co-op session not restored (host={hb.get('coopSession')} " \
            f"client={cb.get('coopSession')})"
        assert hb.get("phase") == "Active" and cb.get("phase") == "Active", \
            f"RESUME: the co-op battle handshake never re-ran: " \
            f"host phase={hb.get('phase')} client phase={cb.get('phase')}"
        # M5: peerAbsent cleared on both - the paused latch let go for good,
        # not just "the modal happened to close".
        assert hb["authority"]["peerAbsent"] is False, \
            f"RESUME: host peerAbsent did not clear: {hb['authority']}"
        assert cb["authority"]["peerAbsent"] is False, \
            f"RESUME: client peerAbsent did not clear: {cb['authority']}"
        # same battle, not a copy (M5) - the SAME battleId survived the pause.
        assert hb["authority"]["battleId"] == cb["authority"]["battleId"] == before["authority"]["battleId"], (
            f"RESUME: battleId changed across the rejoin: before={before['authority']['battleId']} "
            f"host={hb['authority']['battleId']} client={cb['authority']['battleId']}")

        # command is split the SAME way it was before the drop (f) S3's own
        # yardstick: "command split == the pre-drop split", not a fixed
        # disjointness assumption. NOTE (re-point, WV-D77 traced): the
        # original pre-rewrite text here also asserted `not (hsel & csel)`
        # (host and client commanding zero units in common). That does not
        # hold for THIS fixture's default gamemode/turn-mode (PVE, Parallel -
        # THE DEFAULT, BattleAuthority.h) even at battle ENTRY, before any
        # drop: `selectable` (TestServer.cpp) is `BattleUnit::isSelectable
        # (FACTION_PLAYER,...)`, a plain vanilla "is this a live player unit"
        # check with no coop-seat gating at all, so both machines already see
        # the IDENTICAL selectable set pre-drop (PASS entry above prints it:
        # host and client both [8..14]) - Parallel mode's whole point is
        # shared command of the active side (parallel-battlescape-prd), so
        # nobody being disjoint is the CORRECT baseline, not a bug. The
        # meaningful invariant for a rejoin is that it does not CHANGE
        # whatever the pre-drop picture was - asserted below.
        hsel = sorted(u["id"] for u in hb.get("units", []) if u.get("selectable"))
        csel = sorted(u["id"] for u in cb.get("units", []) if u.get("selectable"))
        assert hsel == before_sel["host"] and csel == before_sel["client"], (
            f"issue #93 RESUME: the rejoin re-dealt the squad: before={before_sel} "
            f"after={{'host': {hsel}, 'client': {csel}}}")
        # the rejoiner is looking at the same battle, not a copy of its own
        hunits = sorted(u["id"] for u in hb.get("units", []))
        cunits = sorted(u["id"] for u in cb.get("units", []))
        assert hunits == cunits, (
            f"issue #93 RESUME: the two machines hold different battles after the "
            f"rejoin (host units={hunits} client units={cunits})")
        print(f"PASS resume-control: co-op re-armed, same battle on both machines, "
              f"command split restored (host={hsel} client={csel})")
    finally:
        for gc in (host, client, client2):
            try:
                gc.shutdown()
            except Exception:
                pass


# -------------------------------------------------------------- HOST-LEAVE --

def _assert_client_sees_the_host_leave(client, tag):
    client.wait_for(f"{tag}: client told the host is gone",
                    lambda: (lambda d: (d.get("present")
                                        and d.get("code") == COOP_DLG_CONNECTION_LOST) or None)(
                        dialog(client)),
                    timeout=120, interval=0.5)
    d = dialog(client)
    assert d["backVisible"], f"{tag}: the message has no way to acknowledge it: {d}"
    assert top(client) == "CoopState", \
        f"{tag}: the message is not holding the client: {states(client)}"
    print(f"PASS {tag} told: {d['title']!r}, held behind it")

    # frozen: it must not be handed the co-op battle to finish alone
    time.sleep(8)
    assert top(client) == "CoopState", (
        f"issue #93 ({tag}): the client was left free to play a co-op battle on its "
        f"own after the host left: {states(client)}")
    print(f"PASS {tag} frozen: still held 8s later")

    client.ok({"cmd": "coop_dialog_back"})
    client.wait_for(f"{tag}: client reached the main menu",
                    lambda: (top(client) == "MainMenuState") or None,
                    timeout=60, interval=0.5)
    print(f"PASS {tag} acknowledged: OK took the client to the main menu")


def scenario_host_leaves_skirmish():
    print("\n===== scenario HOST-LEAVE (skirmish) =====")
    host = GameClient("host", 48814, make_user_dir("i93_hl_host"))
    client = GameClient("client", 48815, make_user_dir("i93_hl_client"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        start_skirmish_battle(host, client, "47998")
        host.cmd({"cmd": "disconnect_to_menu"})
        _assert_client_sees_the_host_leave(client, "HOST-LEAVE")
    finally:
        host.shutdown(); client.shutdown()


# lifted verbatim from test_resume_game_in_battle.py (see the module
# docstring above for why: that file's own SKIP-PENDING is still a
# module-level sys.exit(0), so it cannot be imported, lazily or otherwise,
# without killing this process too). Keep in sync with that file's own copy
# when it is un-skipped in a later, separately-scoped cycle.
def _fly_shared_squad_into_a_battle(js):
    """Put the SHARED campaign's craft on a seeded terror site and take both
    machines into the mission (same drive as test_shared_battle)."""
    host, client = js.host, js.client
    base = next(b for b in host.ok({"cmd": "geo_state"})["bases"]
                if not b.get("coopBase") and not b.get("coopIcon"))
    blon, blat = base["lon"], base["lat"]
    cid = next(c for c in base["crafts"] if "SKYRANGER" in c["type"])["id"]

    soldiers = []
    for b in host.ok({"cmd": "get_soldiers"})["bases"]:
        soldiers.extend(b["soldiers"])
    for sid in sorted(s["id"] for s in soldiers)[:2]:
        host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})

    site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                    "deployment": "STR_TERROR_MISSION", "lon": blon + 0.35,
                    "lat": blat + 0.10, "race": "STR_SECTOID", "hours": 240})
    host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
             "lon": blon + 0.34, "lat": blat + 0.10, "dest": f"site:{site['site_id']}",
             "fuel": 999999, "lowFuel": False})

    def _prompt():
        if has(host, "ConfirmLandingState"):
            return True
        host.cmd({"cmd": "geo_set_speed", "idx": 2})  # geo_run auto-declines
        return None

    host.wait_for("landing prompt", _prompt, timeout=120, interval=0.5)
    host.ok({"cmd": "confirm_landing"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} entered the battle",
                    lambda gc=gc: in_battle_save(gc) or None, timeout=240, interval=1.0)
        settle_on_tactical(gc, tag)


def scenario_host_leaves_campaign_battle():
    print("\n===== scenario CAMPAIGN-HOST-LEAVE =====")
    js = shared_fixture.bring_up("i93_hlc", (48816, 48817, 48416))
    try:
        _fly_shared_squad_into_a_battle(js)
        js.host.cmd({"cmd": "disconnect_to_menu"})
        _assert_client_sees_the_host_leave(js.client, "CAMPAIGN-HOST-LEAVE")
    finally:
        js.shutdown()


# ------------------------------------------------------------ SEAT-LEFT END --

def scenario_seat_left_end():
    """S4 (DP1/M6, owner D94=(a)): from a paused battle, the remaining
    player ENDS it. The wave-1 end control is a LOCAL teardown via the #82
    GoToMainMenuState chokepoint - no debrief, no `battle_end` wire atom
    (that is r3b/T6, out of wave); `reason:"seatLeft"` is logged only.
    Also exercises M4 in passing: drop_client_mid_battle's disconnect_to_menu
    is a graceful leave, so the pause dialog should have named it."""
    print("\n===== scenario SEAT-LEFT END (S4) =====")
    host_dir = make_user_dir("i93_seatleft_host")
    host = GameClient("host", 48818, host_dir)
    client = GameClient("client", 48819, make_user_dir("i93_seatleft_client"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        start_skirmish_battle(host, client, "48000")
        drop_client_mid_battle(host, client)
        assert_frozen_over_the_battle(host, "SEAT-LEFT")

        # M4 bonus check: the graceful leave named itself in the pause
        # dialog instead of reading as a silent connection loss.
        d = dialog(host)
        assert "has left the battle" in d["title"], (
            f"M4: the graceful leave was not named in the pause dialog: {d}")

        before = set(session.save_files(host_dir))
        host.ok({"cmd": "coop_dialog_abandon"})
        host.wait_for("host reached the main menu",
                      lambda: (top(host) == "MainMenuState") or None,
                      timeout=60, interval=0.5)
        after = set(session.save_files(host_dir))
        assert after == before, \
            f"S4: ABANDON on a skirmish pause must write nothing; user dir changed " \
            f"{before} -> {after}"
        assert not has(host, "DebriefingState"), (
            f"S4: a debrief was pushed - DP1/D94(a) is a LOCAL teardown, no "
            f"debrief: {states(host)}")
        assert not has(host, "BattlescapeState"), (
            f"S4: the battle SavedGame (and its palette, #82) outlived the "
            f"teardown: {states(host)}")

        b = battle(host)
        assert b.get("phase") == "Idle", \
            f"S4: the battle authority did not tear down: {b}"

        seat_left_lines = [ln for ln in log_lines(host_dir) if 'reason="seatLeft"' in ln]
        assert seat_left_lines, \
            f"S4: no reason=\"seatLeft\" line in {host_dir}/openxcom.log"
        print(f"PASS seat-left-end: local teardown to the main menu, no debrief, "
              f"nothing written, logged {seat_left_lines[-1].strip()!r}")
    finally:
        host.shutdown(); client.shutdown()


def main():
    scenario_rejoin_and_resume()
    scenario_host_leaves_skirmish()
    scenario_host_leaves_campaign_battle()
    scenario_seat_left_end()
    print("\nALL SKIRMISH REJOIN TESTS PASSED")


if __name__ == "__main__":
    main()
