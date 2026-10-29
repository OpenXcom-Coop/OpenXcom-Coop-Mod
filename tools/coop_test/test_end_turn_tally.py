"""test_end_turn_tally.py: the PARALLEL-mode END TURN readiness tally -
`bt_end_turn_ready` (client->host) and `bt_end_turn_tally` (host->all),
wired by CoopEndTurn.

AI-NEUTRAL PINNING. Every unit no human seat commands is pinned via the
shared session.pin_ai_neutral() helper right after drive_to_battlescape(),
so no non-player unit acts during the alien phase (see
repro_atom_side_transition.py's module docstring). Every boot pins mission
STR_SMALL_SCOUT (no civilians, no terror units, exactly one alien on every
seed) and runs `set_seed 1` in `pre_ok`.

SEATED BOOT (classic, seat_count=2): both seats are LIVE on the player side
(measured: seat 0/host 5 units, seat 1/client 2 units), so `needed==2`
throughout the player phase. Its legs run in order: entry_baseline (the t=0
baseline), client_arm (a real-button arm), client_unarm (a real-button
un-arm), stale_press (a CONSTRUCTED stale press plus its positive control),
full_cycle (a full three-transition cycle with both seats armed),
inert_phases (the tally's inertness on the two zero-human-seat phases plus
the boundary reset), and finally - LAST, because it ends the client -
drop_freeze: after the host has armed its own seat and the client leaves,
the co-op battle authority stays ALIVE (phase stays "Active",
authority.peerAbsent goes true) instead of tearing down, so the host's
painted tally text and its button's latched state FREEZE at their pre-drop
value - "END TURN 1/2" SURVIVES a drop, it does not clear. A seat loss
pauses the battle (pause-on-leave), and the host is never left armed to
close the side SOLO (a "1/1" state): `needed` stays frozen at 2, it does not
recompute down to the surviving seat count.

SPECTATOR BOOT (client UNSEATED via `seat_client=False`): a CONNECTED seat
with no live commandable unit on the active side is NOT a live seat, is
never counted in `needed`, is never handed the baton, and its press is
dropped and answered with the tally exactly like a stale press is.

MEASURED AT ENTRY. In parallel mode the raw CoopEndTurn tally is the
`reset()` default at t=0, not a live "needed==2" recompute: no `emitTally()`
runs at battle entry (`onBattleActive()` emits only in traditional mode); the
first tally comes from a press (`applyReady()`), a side change
(`onSideTransition()`) or a seat change (`onSeatSetChanged()`). Right after
`drive_to_battlescape()` + `pin_ai_neutral()`, BEFORE any END TURN action,
`event_state.coopEndTurnTally` on BOTH machines reads exactly
`{"turn": 0, "side": "", "count": 0, "needed": 0, "ready": [],
"activeSeat": -1}`. entry_baseline therefore asserts that default and proves
the fixture's needed==2 premise from `battle_state.units` (a live player unit
on each seat), the way repro_atom_side_begin.py proves "activeSeats==[0,1]",
before any tally has been emitted. `needed==2` on the tally object itself is
first asserted in client_arm, once the client's real arm has triggered the
first `emitTally()` call.

MEASURED, THEN TRACED TO THE SOURCE. The `coopEndTurnTalliesSeen` delta across
"host end_turn_button; drive the full cycle" (full_cycle / inert_phases) is
TWO, not one. `applyReady()` calls `emitTally()` UNCONDITIONALLY before
`tryCommit()`, so the host's own final arming press - the one that completes
readiness (count==needed) - mints its OWN genuine tally (a real "2/2"
snapshot) BEFORE `requestEndTurn()` ever runs; only then does the boundary
cascade start (PLAYER->HOSTILE INERT, HOSTILE->NEUTRAL INERT,
NEUTRAL->PLAYER GENUINE). A live run confirmed this exactly (host
talliesSeen 4 -> 6, not 4 -> 5). inert_phases therefore asserts +2 (the
commit press + the sole non-inert boundary); the zero-human-seat phases
still emit NONE between them, which is the property that leg exists to
prove.

TRADITIONAL BOOT. The classic seated fixture above, but the HOST sets
`CoopTurnMode=traditional` before the offer (the `test_turn_mode.py`
OPTION="CoopTurnMode" / `set_mode()` / `live_mode()` shape, imported rather
than reimplemented) while the CLIENT's own option is left at the default
(parallel), so `live_mode(host) == live_mode(client) == "traditional"` is a
genuine wire-mirror proof, not a locally-set coincidence. It asserts the
TRADITIONAL ENTRY TALLY on BOTH machines, right after
`drive_to_battlescape` + `pin_ai_neutral`: `event_state.coopActiveSeat == 0`
(the first LIVE seat in seat order - host seat 0 first), the raw tally reads
`needed=1/count=0/ready=[]/side='player'`, the side-phase counter is still 0
(the entry tally is NOT a side phase), and nothing is painted
(`coopEndTurnText==''`, `coopEndTurnArmed is False` - count 0 paints
nothing). This is the traditional-mode counterpart to entry_baseline:
parallel emits NOTHING at t=0 (the raw tally is the `reset()` default);
traditional emits EXACTLY ONE genuine tally at the same point. Every seated
and spectator boot assertion is a PARALLEL-mode assertion; entry_baseline
also asserts `coopActiveSeat == -1` on both machines (parallel never writes
`BattleAuthority::activeSeat`).

Run:  python tools/coop_test/test_end_turn_tally.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import (battle_state, event_state, event_log, pin_ai_neutral,
                      assert_hash_clean, FACTION_PLAYER, FACTION_HOSTILE)
from test_turn_mode import set_mode, live_mode, TRADITIONAL, PARALLEL

COOP_SEAT_0 = 0
COOP_SEAT_1 = 1
MISSION = "STR_SMALL_SCOUT"
TALLY_TEXT_1_OF_2 = "END TURN 1/2"
# The pause-on-leave wait dialog's CoopState state code, matches
# test_pause_on_leave.py's own constant of the same name.
COOP_DLG_WAIT_PLAYERS = 62


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


# ----- fixture bring-up (inline copy, repro_atom_side_transition.py /
# repro_atom_side_begin.py precedent - every coop test in this tree carries
# its own copy of the skirmish lobby dance rather than sharing one) -----

def skirmish_host(host, port, player="HostPlayer"):
    host.ok({"cmd": "open_new_battle"})
    host.wait_for("host new battle", lambda: session.has_state(host, "NewBattleState"))
    host.ok({"cmd": "newbattle_coop"})
    host.wait_for("host browser", lambda: session.has_state(host, "ServerList"))
    host.ok({"cmd": "server_list_host"})
    host.wait_for("host window", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv",
             "port": port, "player": player})
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"))


def skirmish_client_at_browser(client):
    client.ok({"cmd": "open_new_battle"})
    client.wait_for("client new battle", lambda: session.has_state(client, "NewBattleState"))
    client.ok({"cmd": "newbattle_coop"})
    client.wait_for("client browser", lambda: session.has_state(client, "ServerList"))


def bring_up_lobby(host, client, port):
    host.spawn(); host.connect()
    client.spawn(); client.connect()

    skirmish_host(host, port)
    skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer"})

    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: lobby(host).get("buttonVisible") or None)


def dismiss_next_turn_if_present(gc):
    """Same helper as repro_atom_side_transition.py's own copy: if `gc`'s TOP
    state is a NextTurnState, close it via the REAL NextTurnState::close()
    path (TestServer `close_nextturn`) rather than dismiss_popup (which only
    pops the state WITHOUT running close()). Returns whether one was found
    (and closed); never raises on absence."""
    lw = gc.cmd({"cmd": "list_widgets"})
    if "NextTurnState" not in lw.get("state", ""):
        return False
    r = gc.cmd({"cmd": "close_nextturn"})
    assert r.get("ok"), (
        f"close_nextturn failed on a machine whose list_widgets just reported "
        f"NextTurnState on top: {r}")
    return True


def drive_full_cycle(host, client, turn0, timeout=60):
    """The full-cycle driver: presses nothing itself (the caller already pressed END
    TURN) - polls both machines to completion, dismissing any NextTurnState
    via close_nextturn on BOTH machines exactly the way
    repro_atom_side_transition.dismiss_next_turn_if_present does. Raises
    TimeoutError if the full cycle never completes on both machines."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        # read both sides FIRST, then close (repro_atom_side_begin.drive_side_change has the
        # reason): once both reads show the new side, every NextTurnState of that change is up for the close pass,
        # which closes every stacked one once and stops when a close pops nothing (a held turn screen): no retry.
        hs = battle_state(host)
        cs = battle_state(client)
        done = (hs.get("side") == FACTION_PLAYER and hs.get("turn", -1) >= turn0 + 1
                and cs.get("side") == FACTION_PLAYER and cs.get("turn", -1) >= turn0 + 1)
        for gc in (host, client):
            depth = None
            while True:
                st = gc.cmd({"cmd": "get_state"}).get("states") or []
                if not st or "NextTurnState" not in st[-1] or (depth is not None and len(st) >= depth):
                    break
                depth = len(st)
                gc.cmd({"cmd": "close_nextturn"})
        if done:
            return
        time.sleep(0.05)
    raise TimeoutError(
        f"test_end_turn_tally: full cycle did not complete within {timeout}s - "
        f"host={battle_state(host)} client={battle_state(client)}")


def run_seated_boot():
    """Classic seated fixture (seat_count=2): entry_baseline .. drop_freeze,
    ending with the drop_freeze leg (which ends the client - LAST leg by
    construction). Nothing here asserts a side advance after a seat loss: a
    seat loss pauses the battle."""
    port = "48160"
    host_dir = make_user_dir("test_end_turn_tally_seated_host")
    client_dir = make_user_dir("test_end_turn_tally_seated_client")
    host = GameClient("host", 49550, host_dir)
    client = GameClient("client", 49551, client_dir)
    seated = {}
    try:
        bring_up_lobby(host, client, port)
        session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                      pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": 1}))

        pinned = pin_ai_neutral(host, client, tag="end_turn_tally-seated")
        assert len(pinned) > 0, (
            f"pin_ai_neutral pinned ZERO NONE-seat non-player units on a CLASSIC "
            f"{MISSION} boot - the premise (a unit for the pin to act on) is "
            "unexercised")

        # ----- entry_baseline: the baseline at t=0 (PARALLEL mode: parallel
        # emits NOTHING at entry) -----
        for gc, who in ((host, "host"), (client, "client")):
            bs = battle_state(gc)
            assert bs.get("coopEndTurnText") == "", (
                f"{who}: coopEndTurnText is not empty at t=0: "
                f"{bs.get('coopEndTurnText')!r}")
            assert bs.get("coopEndTurnArmed") is False, (
                f"{who}: coopEndTurnArmed is not False at t=0: "
                f"{bs.get('coopEndTurnArmed')}")
            # Parallel mode never writes BattleAuthority::activeSeat, which
            # event_state reads as coopActiveSeat: -1 for this whole boot.
            assert event_state(gc).get("coopActiveSeat") == -1, (
                f"{who}: coopActiveSeat is not -1 in PARALLEL mode at t=0 "
                f"(parallel never writes the field): "
                f"{event_state(gc).get('coopActiveSeat')}")
        # See the module docstring's MEASURED AT ENTRY: no emitTally() call has
        # run yet, so the raw tally is the reset() default, not a live
        # recompute - assert the TRUE default, never a value the shipped code
        # has not yet computed.
        hes0 = event_state(host)
        assert hes0.get("coopEndTurnPhaseCounter") == 0, (
            f"host coopEndTurnPhaseCounter is not 0 at t=0: "
            f"{hes0.get('coopEndTurnPhaseCounter')}")
        t0_tally = hes0.get("coopEndTurnTally", {})
        # The same probed object also carries `activeSeat`
        # (event_state.coopEndTurnTally.activeSeat, the wire-echoed tally
        # holder): its reset() default is -1.
        assert t0_tally == {"turn": 0, "side": "", "count": 0, "needed": 0, "ready": [],
                            "activeSeat": -1}, (
            f"host coopEndTurnTally at t=0 is not the reset() default: {t0_tally}")
        # The fixture's OWN needed==2 premise, proven functionally (the same
        # method repro_atom_side_begin.py uses for its "activeSeats==[0,1]"
        # check) - the CoopEndTurn tally object's own needed field is
        # asserted ==2 for the first time at client_arm.
        hs0 = battle_state(host)
        seat0_units = [u for u in hs0["units"] if u.get("coop") == COOP_SEAT_0
                       and u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
        seat1_units = [u for u in hs0["units"] if u.get("coop") == COOP_SEAT_1
                       and u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
        assert seat0_units, "classic boot: seat 0 (host) has no live player unit"
        assert seat1_units, "classic boot: seat 1 (client) has no live player unit"
        assert_hash_clean(host, client, full=True, what="entry_baseline at t=0")
        print(f"[entry_baseline] OK: coopEndTurnText=='' and coopEndTurnArmed==False "
              f"on both machines; host tally is the reset() default {t0_tally}; "
              f"seat 0 has {len(seat0_units)} live unit(s), seat 1 has "
              f"{len(seat1_units)} (the needed==2 fixture premise); 9/9 buckets "
              "EQUAL")

        turn0 = hs0["turn"]
        side0 = hs0["side"]

        # ----- client_arm: the client arms through its REAL button -----
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def host_shows_1_of_2():
            return True if battle_state(host).get("coopEndTurnText") == TALLY_TEXT_1_OF_2 else None
        client.wait_for("host paints END TURN 1/2 after the client's real arm",
                        host_shows_1_of_2, timeout=15)

        assert battle_state(client).get("coopEndTurnText") == TALLY_TEXT_1_OF_2, (
            f"client did not paint {TALLY_TEXT_1_OF_2!r} after arming: "
            f"{battle_state(client).get('coopEndTurnText')!r}")
        assert battle_state(client).get("coopEndTurnArmed") is True, (
            "client's own END TURN button did not invert after arming")
        assert battle_state(host).get("coopEndTurnArmed") is False, (
            "host's END TURN button inverted on the client's arm alone")
        hs_now = battle_state(host)
        cs_now = battle_state(client)
        assert hs_now["turn"] == turn0 and hs_now["side"] == side0, (
            f"host's turn/side advanced on ONE seat's arm: {turn0}/{side0} -> "
            f"{hs_now['turn']}/{hs_now['side']}")
        assert cs_now["turn"] == turn0 and cs_now["side"] == side0, (
            f"client's turn/side advanced on ONE seat's arm: {turn0}/{side0} -> "
            f"{cs_now['turn']}/{cs_now['side']}")
        het = event_state(host).get("coopEndTurnTally", {})
        assert het.get("needed") == 2 and het.get("count") == 1, (
            f"host tally after the client's arm is not count=1/needed=2: {het}")
        print(f"[client_arm] client armed via its real button: both machines paint "
              f"{TALLY_TEXT_1_OF_2!r}; client armed=True / host armed=False; "
              f"turn/side unchanged ({turn0}/{side0}); host tally={het}")

        # ----- client_unarm: un-arm on the SAME machine -----
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def both_show_empty():
            return True if (battle_state(host).get("coopEndTurnText") == ""
                             and battle_state(client).get("coopEndTurnText") == "") else None
        client.wait_for("both machines paint '' after the client un-arms",
                        both_show_empty, timeout=15)

        assert battle_state(client).get("coopEndTurnArmed") is False, (
            "client's END TURN button did not un-invert after the second press")
        hs_now = battle_state(host)
        cs_now = battle_state(client)
        assert hs_now["turn"] == turn0 and hs_now["side"] == side0, (
            f"un-arming (a legal parallel-mode press) advanced the side: "
            f"{turn0}/{side0} -> {hs_now['turn']}/{hs_now['side']}")
        assert cs_now["turn"] == turn0 and cs_now["side"] == side0, (
            f"un-arming advanced the client's turn/side: {turn0}/{side0} "
            f"-> {cs_now['turn']}/{cs_now['side']}")
        het = event_state(host).get("coopEndTurnTally", {})
        assert het.get("count") == 0, (
            f"host tally count after the un-arm is not back to 0: {het}")
        print(f"[client_unarm] un-arm via the same real button: no advance; both machines "
              f"paint ''; client armed=False; host tally count back to "
              f"0 ({het})")

        # ----- stale_press: the CONSTRUCTED stale press -----
        current_turn = event_state(client).get("coopEndTurnTally", {}).get("turn", 0)
        stale_turn = current_turn - 1
        host_count_before = event_state(host).get("coopEndTurnTally", {}).get("count")
        client_seen_before = event_state(client).get("coopEndTurnTalliesSeen")

        client.ok({"cmd": "battle_end_turn_ready", "turn": stale_turn, "ready": True})

        def client_saw_one_more_tally():
            seen = event_state(client).get("coopEndTurnTalliesSeen")
            return True if seen is not None and seen > client_seen_before else None
        client.wait_for("client saw the re-emitted tally answering the stale press",
                        client_saw_one_more_tally, timeout=15)

        host_count_after = event_state(host).get("coopEndTurnTally", {}).get("count")
        assert host_count_after == host_count_before, (
            f"the stale press (turn={stale_turn}, current={current_turn}) "
            f"changed the host's stored readies: {host_count_before} -> "
            f"{host_count_after}")
        assert battle_state(client).get("coopEndTurnArmed") is False, (
            "the CONSTRUCTED stale press armed the client's button")
        assert battle_state(client).get("coopEndTurnText") == "", (
            f"the CONSTRUCTED stale press painted a non-empty tally text: "
            f"{battle_state(client).get('coopEndTurnText')!r}")
        client_seen_after_stale = event_state(client).get("coopEndTurnTalliesSeen")
        print(f"[stale_press] turn={stale_turn} (current={current_turn}) DROPPED and "
              f"ANSWERED: host count unchanged ({host_count_before}); client "
              f"talliesSeen {client_seen_before} -> {client_seen_after_stale}; "
              "client armed=False; text==''")

        # Positive control, same leg: the same test command with the CURRENT turn
        # must arm. Leave the client ARMED going into full_cycle.
        client.ok({"cmd": "battle_end_turn_ready", "turn": current_turn, "ready": True})

        def host_shows_1_of_2_again():
            return True if battle_state(host).get("coopEndTurnText") == TALLY_TEXT_1_OF_2 else None
        client.wait_for("host paints END TURN 1/2 after the test command's CURRENT-turn press",
                        host_shows_1_of_2_again, timeout=15)
        assert battle_state(client).get("coopEndTurnArmed") is True, (
            "the CURRENT-turn test command press (positive control) did not arm the client")
        print(f"[stale_press positive control] turn={current_turn} (current) ARMED via the "
              f"same test command: client armed=True; host text=={TALLY_TEXT_1_OF_2!r}; "
              "client left ARMED for full_cycle")

        # ----- full_cycle: both seats armed -> the side advances, one full cycle -----
        turn_before = battle_state(host)["turn"]
        host_counter_before = event_state(host).get("coopEndTurnPhaseCounter")
        client_counter_before = event_state(client).get("coopEndTurnPhaseCounter")
        host_seen_before_cycle = event_state(host).get("coopEndTurnTalliesSeen")
        client_seen_before_cycle = event_state(client).get("coopEndTurnTalliesSeen")

        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        drive_full_cycle(host, client, turn_before, timeout=60)
        session.wait_host_idle(host, client, timeout=30)

        cevs = event_log(client, tail=256)
        boundary = [e for e in cevs if e.get("actionId") == 0
                    and e.get("kind") in ("side_transition", "side_begin")]
        transitions = [e for e in boundary if e["kind"] == "side_transition"]
        begins = [e for e in boundary if e["kind"] == "side_begin"]
        assert len(transitions) == 3, (
            f"expected exactly 3 side_transition envelopes for one full cycle, "
            f"got {len(transitions)}: {transitions}")
        assert len(begins) == 3, (
            f"expected exactly 3 side_begin envelopes, got {len(begins)}: {begins}")

        host_counter_after = event_state(host).get("coopEndTurnPhaseCounter")
        client_counter_after = event_state(client).get("coopEndTurnPhaseCounter")
        turn_after_h = battle_state(host)["turn"]
        turn_after_c = battle_state(client)["turn"]
        assert host_counter_after == host_counter_before + 3, (
            f"host's side-phase counter did not advance by exactly 3: "
            f"{host_counter_before} -> {host_counter_after}")
        assert client_counter_after == client_counter_before + 3, (
            f"client's side-phase counter did not advance by exactly 3: "
            f"{client_counter_before} -> {client_counter_after}")
        assert turn_after_h == turn_before + 1, (
            f"host's battle_state.turn did not advance by exactly 1: "
            f"{turn_before} -> {turn_after_h}")
        assert turn_after_c == turn_before + 1, (
            f"client's battle_state.turn did not advance by exactly 1: "
            f"{turn_before} -> {turn_after_c}")
        assert (battle_state(host)["side"] == FACTION_PLAYER
                and battle_state(client)["side"] == FACTION_PLAYER), (
            "side is not back to FACTION_PLAYER on both machines after the cycle")
        hh, ch = assert_hash_clean(host, client, full=True, what="full_cycle post-cycle boundary")
        print(f"[full_cycle] full cycle: 3 side_transition + 3 side_begin envelopes; "
              f"side-phase counter +3 on both (host {host_counter_before}->"
              f"{host_counter_after}, client {client_counter_before}->"
              f"{client_counter_after}) while battle_state.turn +1 on both "
              f"({turn_before}->{turn_after_h}); side back to FACTION_PLAYER; "
              f"{len(hh)} buckets EQUAL")

        # ----- inert_phases: the tally is INERT on hostile/neutral; stored
        # readies do NOT survive a boundary -----
        # Measured, then traced to the source: the delta here is TWO, not
        # one. In connectionTCP.cpp, every
        # applyReady() call - INCLUDING the host's own final arming press -
        # calls emitTally() BEFORE tryCommit(), so the press that completes
        # readiness (count==needed) mints its OWN genuine tally (a real
        # "2/2" snapshot the players would see painted for an instant)
        # BEFORE requestEndTurn() ever runs. Only THEN does the boundary
        # cascade start: PLAYER->HOSTILE (needed==0, INERT) ->
        # HOSTILE->NEUTRAL (needed==0, INERT) -> NEUTRAL->PLAYER (needed==2,
        # GENUINE). So "host end_turn_button; drive the full cycle", measured
        # from a baseline taken BEFORE the host's own press, sees exactly TWO
        # genuine tallies: the host's own commit press, plus the sole
        # non-inert boundary. A live run
        # confirmed this exactly (host talliesSeen 4 -> 6). The
        # zero-human-seat phases (PLAYER->HOSTILE, HOSTILE->NEUTRAL) still
        # emit NONE between them, which is the property this leg exists to
        # prove.
        host_seen_after_cycle = event_state(host).get("coopEndTurnTalliesSeen")
        client_seen_after_cycle = event_state(client).get("coopEndTurnTalliesSeen")
        assert host_seen_after_cycle == host_seen_before_cycle + 2, (
            f"host's coopEndTurnTalliesSeen did not advance by exactly TWO "
            f"(the host's own commit press + the sole non-inert boundary): "
            f"{host_seen_before_cycle} -> {host_seen_after_cycle}")
        assert client_seen_after_cycle == client_seen_before_cycle + 2, (
            f"client's coopEndTurnTalliesSeen did not advance by exactly TWO: "
            f"{client_seen_before_cycle} -> {client_seen_after_cycle}")
        het_new_side = event_state(host).get("coopEndTurnTally", {})
        cet_new_side = event_state(client).get("coopEndTurnTally", {})
        assert het_new_side.get("count") == 0 and het_new_side.get("needed") == 2, (
            f"stored readies survived the boundary on the host: {het_new_side}")
        assert cet_new_side.get("count") == 0 and cet_new_side.get("needed") == 2, (
            f"stored readies survived the boundary on the client: {cet_new_side}")
        assert (battle_state(host).get("coopEndTurnText") == ""
                and battle_state(client).get("coopEndTurnText") == ""), (
            "the tally text is not hidden on the new player side")
        assert (battle_state(host).get("coopEndTurnArmed") is False
                and battle_state(client).get("coopEndTurnArmed") is False), (
            "the END TURN button is not un-latched on the new player side")
        print(f"[inert_phases] tally INERT on hostile+neutral: talliesSeen advanced by "
              f"exactly TWO on both machines (the host's own commit press + "
              f"the sole non-inert boundary; host {host_seen_before_cycle}->"
              f"{host_seen_after_cycle}, client {client_seen_before_cycle}->"
              f"{client_seen_after_cycle}); the new player side reads "
              "count=0/needed=2 on both; text==''; button un-latched")

        # ----- drop_freeze: the tally freezes when the client leaves. A
        # mid-Active client drop keeps the co-op battle authority ALIVE
        # (phase stays "Active", authority.peerAbsent goes true) instead of
        # tearing it down to Idle, so no battle-authority reset clears the
        # tally on this path. The host must not be left free to advance the
        # side SOLO once `needed` would otherwise drop 2->1 (a "1/1" armed
        # state), so CoopEndTurn::onSeatSetChanged() is not called on the
        # pause path - the tally FREEZES at its pre-drop value instead. This
        # is the LAST leg, and ends the client. A client leaving a live coop
        # battle HALTS the game for everyone until it reconnects
        # (pause-on-leave), so "the host advances the side with a single
        # vote" is not a true statement and is asserted NOWHERE below.
        # drop_freeze asserts NOTHING about a side advance and nothing about
        # the client. -----

        # The HOST arms its OWN seat first (count 1 of needed 2), so the
        # side does NOT advance (measured: the host presses END TURN alone
        # -> text=='END TURN 1/2', armed==True, side stays 0, turn stays
        # unchanged).
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def host_armed_pre_drop():
            bs = battle_state(host)
            return True if (bs.get("coopEndTurnText") == TALLY_TEXT_1_OF_2
                             and bs.get("coopEndTurnArmed") is True) else None
        host.wait_for("host paints END TURN 1/2 and its own button arms "
                      "before the drop (non-vacuity)",
                      host_armed_pre_drop, timeout=15)
        # The pre-drop capture: makes the post-drop assertions below
        # non-vacuous, and every failure message quotes it.
        pre_drop_bs = battle_state(host)
        pre_drop_text = pre_drop_bs.get("coopEndTurnText")
        pre_drop_armed = pre_drop_bs.get("coopEndTurnArmed")
        pre_drop_side = pre_drop_bs.get("side")
        pre_drop_turn = pre_drop_bs.get("turn")

        client.ok({"cmd": "disconnect_to_menu"})

        def host_paused_peer_absent():
            authority = battle_state(host).get("authority", {})
            return True if authority.get("peerAbsent") is True else None
        host.wait_for("host's battle authority marks the departed peer "
                      "absent (the battle pauses)",
                      host_paused_peer_absent, timeout=20)

        post_drop = battle_state(host)
        post_authority = post_drop.get("authority", {})
        dlg = host.cmd({"cmd": "coop_dialog_info"})
        assert post_authority.get("peerAbsent") is True, (
            f"drop_freeze: host's authority.peerAbsent did not go True after "
            f"the client's departure: {post_authority}")
        assert post_drop.get("phase") == "Active", (
            f"drop_freeze: host's battle phase is not 'Active' after the "
            f"client's departure - the pause must keep the authority "
            f"alive, not tear it down: {post_drop.get('phase')!r}")
        assert post_drop.get("inBattle") is True, (
            f"drop_freeze: host is not inBattle after the client's "
            f"departure - pre-drop was text={pre_drop_text!r} "
            f"armed={pre_drop_armed!r}: {post_drop}")
        assert post_drop.get("side") == pre_drop_side, (
            f"drop_freeze: side changed across the pause - pre-drop "
            f"{pre_drop_side!r}, post-drop {post_drop.get('side')!r}")
        assert post_drop.get("turn") == pre_drop_turn, (
            f"drop_freeze: turn changed across the pause - pre-drop "
            f"{pre_drop_turn!r}, post-drop {post_drop.get('turn')!r}")
        assert post_drop.get("coopEndTurnText") == TALLY_TEXT_1_OF_2, (
            f"drop_freeze: host's coopEndTurnText did not FREEZE at the "
            f"pre-drop tally - pre-drop was {pre_drop_text!r}, post-drop is "
            f"{post_drop.get('coopEndTurnText')!r} (onSeatSetChanged() must "
            f"stay gated off the pause path, or `needed` drops 2->1 and "
            f"the host ends up armed at 1/1, free to end the side "
            f"solo)")
        assert post_drop.get("coopEndTurnArmed") is True, (
            f"drop_freeze: host's coopEndTurnArmed did not stay latched - "
            f"pre-drop was {pre_drop_armed!r}, post-drop is "
            f"{post_drop.get('coopEndTurnArmed')!r}")
        assert dlg.get("present") and dlg.get("code") == COOP_DLG_WAIT_PLAYERS, (
            f"drop_freeze: the wait-for-players dialog (code "
            f"{COOP_DLG_WAIT_PLAYERS}) is not up over the paused battle: "
            f"{dlg}")
        print(f"[drop_freeze] tally freeze on the pause: after the client's "
              f"disconnect_to_menu, the host's painted tally and armed bit "
              f"stayed FROZEN at {pre_drop_text!r}/armed={pre_drop_armed!r} "
              f"while authority.peerAbsent=True, phase=Active, side/turn "
              f"unchanged ({pre_drop_side!r}/{pre_drop_turn!r}), dialog "
              f"{COOP_DLG_WAIT_PLAYERS} up")

        print("PASS: test_end_turn_tally seated boot (classic, seat_count=2)")
    finally:
        host.shutdown()
        client.shutdown()


def run_spectator_boot():
    """The SPECTATOR boot: the client is never seated
    (`seat_client=False`), so it is a CONNECTED seat with zero live
    commandable units on the active side - not a LIVE seat, never counted in
    `needed`, never handed the baton, and its press is dropped and answered
    with the tally exactly like a stale press is."""
    port = "48161"
    host_dir = make_user_dir("test_end_turn_tally_spectator_host")
    client_dir = make_user_dir("test_end_turn_tally_spectator_client")
    host = GameClient("host", 49552, host_dir)
    client = GameClient("client", 49553, client_dir)
    seated = {}
    try:
        bring_up_lobby(host, client, port)
        session.drive_to_battlescape(host, client, seated, mission=MISSION,
                                      pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": 1}),
                                      seat_client=False)

        pinned = pin_ai_neutral(host, client, tag="end_turn_tally-spectator")
        print(f"[spectator boot] pin_ai_neutral pinned {len(pinned)} unit(s)")

        hs0 = battle_state(host)
        seat1_units = [u for u in hs0["units"] if u.get("coop") == COOP_SEAT_1]
        assert not seat1_units, (
            f"spectator boot premise broke: the UNSEATED client owns unit(s) anyway: "
            f"{seat1_units}")
        seat0_units = [u for u in hs0["units"] if u.get("coop") == COOP_SEAT_0
                       and u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
        assert seat0_units, "spectator boot: seat 0 (host) has no live player unit"

        turn0 = hs0["turn"]
        client_seen_before = event_state(client).get("coopEndTurnTalliesSeen")

        # ----- the SPECTATOR's press: changes nothing, is answered -----
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def client_saw_a_tally():
            seen = event_state(client).get("coopEndTurnTalliesSeen")
            return True if seen is not None and seen > client_seen_before else None
        client.wait_for("client saw a tally answering its own spectator press",
                        client_saw_a_tally, timeout=15)

        het = event_state(host).get("coopEndTurnTally", {})
        assert het.get("needed") == 1, (
            f"needed is not 1 with the client UNSEATED: {het}")
        assert het.get("count") == 0, (
            f"the spectator's press changed the host's stored readies: {het}")
        assert battle_state(client).get("coopEndTurnArmed") is False, (
            "the spectator's press left the client's button armed (a "
            "connected seat with no live unit is not a live seat)")
        hs_now = battle_state(host)
        cs_now = battle_state(client)
        assert hs_now["turn"] == turn0 and hs_now["side"] == FACTION_PLAYER, (
            f"the spectator's press advanced the host's side: {hs_now}")
        assert cs_now["turn"] == turn0 and cs_now["side"] == FACTION_PLAYER, (
            f"the spectator's press advanced the client's side: {cs_now}")
        print(f"[spectator boot] spectator's press changed nothing and was answered: "
              f"needed==1; host tally count unchanged (0); client talliesSeen "
              f"{client_seen_before} -> "
              f"{event_state(client).get('coopEndTurnTalliesSeen')}; client "
              "armed=False; no side advance")

        # ----- the HOST's press ALONE advances the side: measured via
        # counters taken AFTER the full cycle. A driver that polls for the
        # transient phase races it: with zero human seats on the hostile and
        # neutral phases, the whole three-transition cycle completes in
        # ~0.35s, so a poll for side==FACTION_HOSTILE usually lands after
        # that phase is already gone. The hostile/neutral phases' inertness
        # is proven by the counter deltas below, never by catching the
        # transient phase mid-flight - do not add a poll for it, and never
        # answer a missed one by slowing it down or retrying it.
        host_counter_before = event_state(host).get("coopEndTurnPhaseCounter")
        client_counter_before = event_state(client).get("coopEndTurnPhaseCounter")
        # Baseline is 1, not 0: the spectator's own press above already
        # minted one genuine tally (talliesSeen 0 -> 1), so the "before"
        # snapshot for this cycle's delta is taken AFTER that leg.
        host_seen_before_cycle = event_state(host).get("coopEndTurnTalliesSeen")
        client_seen_before_cycle = event_state(client).get("coopEndTurnTalliesSeen")

        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        drive_full_cycle(host, client, turn0, timeout=60)
        session.wait_host_idle(host, client, timeout=30)

        host_counter_after = event_state(host).get("coopEndTurnPhaseCounter")
        client_counter_after = event_state(client).get("coopEndTurnPhaseCounter")
        host_seen_after_cycle = event_state(host).get("coopEndTurnTalliesSeen")
        client_seen_after_cycle = event_state(client).get("coopEndTurnTalliesSeen")
        turn_after_h = battle_state(host)["turn"]
        turn_after_c = battle_state(client)["turn"]

        assert host_counter_after == host_counter_before + 3, (
            f"host's side-phase counter did not advance by exactly 3: "
            f"{host_counter_before} -> {host_counter_after}")
        assert client_counter_after == client_counter_before + 3, (
            f"client's side-phase counter did not advance by exactly 3: "
            f"{client_counter_before} -> {client_counter_after}")
        assert host_seen_after_cycle == host_seen_before_cycle + 2, (
            f"host's coopEndTurnTalliesSeen did not advance by exactly TWO "
            f"across the host's commit press + the full cycle: "
            f"{host_seen_before_cycle} -> {host_seen_after_cycle}")
        assert client_seen_after_cycle == client_seen_before_cycle + 2, (
            f"client's coopEndTurnTalliesSeen did not advance by exactly "
            f"TWO: {client_seen_before_cycle} -> {client_seen_after_cycle}")
        assert turn_after_h == turn0 + 1 and battle_state(host)["side"] == FACTION_PLAYER, (
            f"host's battle_state.turn/side did not land at turn0+1/PLAYER: "
            f"{turn0} -> {turn_after_h}, side={battle_state(host).get('side')}")
        assert turn_after_c == turn0 + 1 and battle_state(client)["side"] == FACTION_PLAYER, (
            f"client's battle_state.turn/side did not land at turn0+1/PLAYER: "
            f"{turn0} -> {turn_after_c}, side={battle_state(client).get('side')}")

        het_new_side = event_state(host).get("coopEndTurnTally", {})
        cet_new_side = event_state(client).get("coopEndTurnTally", {})
        assert (het_new_side.get("count") == 0 and het_new_side.get("ready") == []
                and het_new_side.get("needed") == 1
                and het_new_side.get("side") == "player"), (
            f"host tally at the new player side is not "
            f"count=0/ready=[]/needed=1/side='player': {het_new_side}")
        assert (cet_new_side.get("count") == 0 and cet_new_side.get("ready") == []
                and cet_new_side.get("needed") == 1
                and cet_new_side.get("side") == "player"), (
            f"client tally at the new player side is not "
            f"count=0/ready=[]/needed=1/side='player': {cet_new_side}")
        assert (battle_state(host).get("coopEndTurnText") == ""
                and battle_state(client).get("coopEndTurnText") == ""), (
            "the tally text is not hidden on the new player side")
        assert (battle_state(host).get("coopEndTurnArmed") is False
                and battle_state(client).get("coopEndTurnArmed") is False), (
            "the END TURN button is not un-latched on the new player side")

        hh, ch = assert_hash_clean(host, client, full=True, what="spectator boot post-cycle")
        print(f"[spectator boot] ONE host end_turn_button + full cycle (measured "
              f"after the cycle - never polled mid-flight): "
              f"phase counter +3 on both (host {host_counter_before}->"
              f"{host_counter_after}, client {client_counter_before}->"
              f"{client_counter_after}); talliesSeen +2 on both (host "
              f"{host_seen_before_cycle}->{host_seen_after_cycle}, client "
              f"{client_seen_before_cycle}->{client_seen_after_cycle}); "
              f"battle_state.turn {turn0}->{turn_after_h}, side back to "
              f"FACTION_PLAYER on both; new-side tally "
              f"count=0/ready=[]/needed=1/side='player'; text=='' and "
              f"armed=False on both; {len(hh)} buckets EQUAL")

        print("PASS: test_end_turn_tally spectator boot (client unseated)")
    finally:
        host.shutdown()
        client.shutdown()


def run_traditional_boot():
    """The TRADITIONAL entry tally. The same classic seated fixture as the
    seated boot (seat_count=2, STR_SMALL_SCOUT, seed 1, the AI-neutral pin),
    but the HOST sets CoopTurnMode=traditional before the offer while the
    CLIENT's own option is left at the default (parallel) - a genuine wire-mirror non-vacuity control, the same shape
    `test_turn_mode.test_wire_traditional` uses. Asserts the ENTRY tally
    on BOTH machines, immediately after drive_to_battlescape + pin_ai_neutral
    and before any END TURN action: `coopActiveSeat==0` (the first LIVE seat
    in seat order), the raw tally is exactly
    needed=1/count=0/ready=[]/side='player', the side-phase counter is
    still 0 (an entry tally is NOT a side phase), and nothing is painted
    (text=='' / armed=False, count==0 paints nothing)."""
    port = "48162"
    host_dir = make_user_dir("test_end_turn_tally_traditional_host")
    client_dir = make_user_dir("test_end_turn_tally_traditional_client")
    host = GameClient("host", 49554, host_dir)
    client = GameClient("client", 49555, client_dir)
    seated = {}
    try:
        bring_up_lobby(host, client, port)

        def pre_ok_traditional(h):
            set_mode(h, TRADITIONAL)
            h.ok({"cmd": "set_seed", "seed": 1})

        session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                      pre_ok=pre_ok_traditional)

        assert live_mode(host) == TRADITIONAL and live_mode(client) == TRADITIONAL, (
            f"traditional fixture: expected both machines' live battle mode "
            f"to be {TRADITIONAL!r} (host set it, client mirrors off the wire "
            f"while its OWN option stays {PARALLEL!r}): host={live_mode(host)!r} "
            f"client={live_mode(client)!r}")

        pinned = pin_ai_neutral(host, client, tag="end_turn_tally-traditional")
        assert len(pinned) > 0, (
            f"pin_ai_neutral pinned ZERO NONE-seat non-player units on a CLASSIC "
            f"{MISSION} boot - the premise (a unit for the pin to act on) is "
            "unexercised")

        for gc, who in ((host, "host"), (client, "client")):
            es = event_state(gc)
            assert es.get("coopActiveSeat") == 0, (
                f"{who}: coopActiveSeat at the entry tally is not 0 (the "
                f"first live seat in seat order - host seat 0 first): "
                f"{es.get('coopActiveSeat')}")
            tally = es.get("coopEndTurnTally", {})
            assert (tally.get("needed") == 1 and tally.get("count") == 0
                    and tally.get("ready") == [] and tally.get("side") == "player"), (
                f"{who}: the traditional entry tally is not exactly "
                f"needed=1/count=0/ready=[]/side='player': "
                f"{tally}")
            assert es.get("coopEndTurnPhaseCounter") == 0, (
                f"{who}: coopEndTurnPhaseCounter is not 0 at the entry tally - "
                f"an entry tally is NOT a side phase: "
                f"{es.get('coopEndTurnPhaseCounter')}")
            bs = battle_state(gc)
            assert bs.get("coopEndTurnText") == "", (
                f"{who}: coopEndTurnText is not empty at the entry tally "
                f"(count==0 paints nothing): "
                f"{bs.get('coopEndTurnText')!r}")
            assert bs.get("coopEndTurnArmed") is False, (
                f"{who}: coopEndTurnArmed is not False at the entry tally: "
                f"{bs.get('coopEndTurnArmed')}")

        assert_hash_clean(host, client, full=True, what="traditional entry tally")
        print("[traditional boot] entry tally OK on both machines: "
              "coopActiveSeat==0, tally needed=1/count=0/ready=[]/side='player', "
              "coopEndTurnPhaseCounter==0, text=='' and armed=False")

        print("PASS: test_end_turn_tally traditional boot (entry tally)")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    run_seated_boot()
    run_spectator_boot()
    run_traditional_boot()
    print("ALL test_end_turn_tally TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("test_end_turn_tally", e.tracking, str(e))
        print(f"\ntest_end_turn_tally: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(2)
    except AssertionError as e:
        print(f"\ntest_end_turn_tally: FAIL\nAssertionError: {e}")
        sys.exit(2)
    except TimeoutError as e:
        print(f"\ntest_end_turn_tally: FAIL\nTimeoutError: {e}")
        sys.exit(2)
