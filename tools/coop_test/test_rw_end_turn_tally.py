"""SPEC 10 (W1-P13b) - test_rw_end_turn_tally.py: the PARALLEL-mode END TURN
readiness tally (SS2.W3, frozen) - `bt_end_turn_ready` (client->host) and
`bt_end_turn_tally` (host->all) - wired by CoopEndTurn (engine + tools commit
ef9b8d55b, "feat(coop): W1-P13b engine + tools - END TURN readiness tally
(SPEC 10 commit 0)"). This is the SEPARATE tests commit that spec names.

AI-NEUTRAL PINNING (WV-D45/IR2-9, REV E.48 SS.B.2/D49) - see
repro_atom_side_transition.py's module docstring for the full rationale
(wave 1 streams no alien action at all, so an un-pinned non-player unit
would desync the client the instant it moved); this file imports the SAME
session.pin_ai_neutral() helper (SS.A.7) rather than re-implementing it.
Both boots pin mission STR_SMALL_SCOUT (no civilians, no terror units,
exactly one alien on every seed - M9a-3) and `set_seed 1` in `pre_ok`.

BOOT A (seated classic, seat_count=2): both seats are LIVE on the player
side (seat 0/host: 5 units, seat 1/client: 2 units - REV E.48 SPEC 10 R1
MEASUREMENT), so `needed==2` throughout the player phase. Legs L1-L7'
exercise, in order: the t=0 baseline, a real-button arm (L2), a real-button
un-arm (L3), the CONSTRUCTED stale press plus its positive control
(REV E.48 C.2 / D57, L4), a full three-transition cycle with both seats
armed (REV E.48 C.1, L5), the tally's inertness on the two zero-human-seat
phases plus the boundary reset (L6), and finally - LAST, because it ends the
client - the REV E.51 E51.3 F174 authority-reset clear (L7'): after the host
has armed its own seat and the client leaves, the host's painted tally text
and its button's inverted state are CLEARED at battle-authority reset, so no
"END TURN 1/2" survives a drop. REV E.48 C.3's seat-loss claim (the host
advancing the side once `needed` drops to 1) is DELETED by owner ruling D69
= (d): seat loss = pause-on-leave, r4 T4/T5; not exercised in wave 1 (D69).

BOOT B (client UNSEATED via `seat_client=False`): REV E.48 C.4's spectator
case - a CONNECTED seat with no live commandable unit on the active side is
NOT a live seat, is never counted in `needed`, is never handed the baton,
and its press is dropped and answered with the tally exactly like a stale
press is.

BUILDER FINDING (measured, not inferred - WV-D77 instrument-first). The raw
CoopEndTurn tally is UNINITIALIZED at t=0, not a live "needed==2" recompute.
Reading CoopEndTurn.h's doc comment and its connectionTCP.cpp body (at
ef9b8d55b) shows `emitTally()` runs ONLY from `onSideTransition()` (a
boundary), `applyReady()` (a press) and `onSeatSetChanged()` (a seat drop) -
never once at battle entry. A scratch probe (not committed) confirmed this
empirically on the pinned classic fixture: immediately after
`drive_to_battlescape()` + `pin_ai_neutral()`, BEFORE any END TURN action,
`event_state.coopEndTurnTally` on BOTH machines read exactly
`{"turn": 0, "side": "", "count": 0, "needed": 0, "ready": []}` - the
`reset()` defaults, never a recompute the shipped code does not perform.
L1 therefore asserts that TRUE default and proves the fixture's needed==2
PREMISE the same way SPEC 9's repro_atom_side_begin proves
"activeSeats==[0,1]" - functionally, off `battle_state.units`, before any
tally has ever been emitted. `needed==2` on the CoopEndTurn tally object
itself is asserted for the first time at L2, once the client's real arm has
triggered the first genuine `emitTally()` call. This is a test-side
correction to the dispatch spec's literal "the host's event_state
.coopEndTurnTally reads needed==2, count==0" wording for L1 - the honest
zero/count-0 half holds, the needed==2 half does not until a tally has
actually been emitted, so it is proven by the same functional-proxy method
already used elsewhere in this chain rather than by an unfired probe.

SECOND BUILDER FINDING (measured, then traced to source - WV-D77). L5/L6's
`coopEndTurnTalliesSeen` delta across "host end_turn_button; drive the full
cycle" is TWO, not the ONE a literal reading of SPEC 10 (f) suggests.
`connectionTCP.cpp`'s `applyReady()` (read at ef9b8d55b) calls `emitTally()`
UNCONDITIONALLY before `tryCommit()`, so the host's own final arming press -
the one that completes readiness (count==needed) - mints its OWN genuine
tally (a real "2/2" snapshot) BEFORE `requestEndTurn()` ever runs; only then
does the boundary cascade start (PLAYER->HOSTILE INERT, HOSTILE->NEUTRAL
INERT, NEUTRAL->PLAYER GENUINE). A live run confirmed this exactly (host
talliesSeen 4 -> 6, not 4 -> 5). L6 therefore asserts +2 (the commit press +
the sole non-inert boundary), which is the stronger, fully-traced claim; the
zero-human-seat phases still emit NONE between them, which remains the
property this leg exists to prove.

Cites SPEC 10, REV E.48 SS.C, REV E.50 (D66/E50.1, D67/E50.2, D68/E50.3),
REV E.51 (D69 = (d)/E51.1 - the C.3 seat-loss leg deleted, E51.3 - L7's F174
authority-reset clear, E51.4 - BOOT B's counter form), WV-D46/IR2-4, WR-3,
WR-4, WR-20, D-24, D53 (SS.C.4 - the LIVE seat definition), D57 (SS.C.2 - the
constructed stale press).

Run:  python tools/coop_test/test_rw_end_turn_tally.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import (battle_state, event_state, event_log, pin_ai_neutral,
                      assert_hash_clean, FACTION_PLAYER, FACTION_HOSTILE)

COOP_SEAT_0 = 0
COOP_SEAT_1 = 1
MISSION = "STR_SMALL_SCOUT"
TALLY_TEXT_1_OF_2 = "END TURN 1/2"


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
    """L5 driver: presses nothing itself (the caller already pressed END
    TURN) - polls both machines to completion, dismissing any NextTurnState
    via close_nextturn on BOTH machines exactly the way
    repro_atom_side_transition.dismiss_next_turn_if_present does. Raises
    TimeoutError if the full cycle never completes on both machines."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        dismiss_next_turn_if_present(host)
        dismiss_next_turn_if_present(client)
        hs = battle_state(host)
        cs = battle_state(client)
        if (hs.get("side") == FACTION_PLAYER and hs.get("turn", -1) >= turn0 + 1
                and cs.get("side") == FACTION_PLAYER and cs.get("turn", -1) >= turn0 + 1):
            return
        time.sleep(0.05)
    raise TimeoutError(
        f"test_rw_end_turn_tally: full cycle did not complete within {timeout}s - "
        f"host={battle_state(host)} client={battle_state(client)}")


def run_boot_a():
    """Classic seated fixture (seat_count=2): L1-L7', ending with the REV
    E.51 E51.3 F174 authority-reset clear leg (which ends the client - LAST
    leg by construction; REV E.48 C.3's seat-loss claim is DELETED, D69 =
    (d))."""
    port = "48160"
    host_dir = make_user_dir("test_rw_end_turn_tally_a_host")
    client_dir = make_user_dir("test_rw_end_turn_tally_a_client")
    host = GameClient("host", 49550, host_dir)
    client = GameClient("client", 49551, client_dir)
    seated = {}
    try:
        bring_up_lobby(host, client, port)
        session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                      pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": 1}))

        pinned = pin_ai_neutral(host, client, tag="end_turn_tally-a")
        assert len(pinned) > 0, (
            f"pin_ai_neutral pinned ZERO NONE-seat non-player units on a CLASSIC "
            f"{MISSION} boot - the premise (a unit for the pin to act on) is "
            "unexercised (M9a-3)")

        # ----- L1: baseline at t=0 -----
        for gc, who in ((host, "host"), (client, "client")):
            bs = battle_state(gc)
            assert bs.get("coopEndTurnText") == "", (
                f"{who}: coopEndTurnText is not empty at t=0: "
                f"{bs.get('coopEndTurnText')!r}")
            assert bs.get("coopEndTurnArmed") is False, (
                f"{who}: coopEndTurnArmed is not False at t=0: "
                f"{bs.get('coopEndTurnArmed')}")
        # See the module docstring's BUILDER FINDING: no emitTally() call has
        # run yet, so the raw tally is the reset() default, not a live
        # recompute - assert the TRUE default, never a value the shipped code
        # has not yet computed.
        hes0 = event_state(host)
        assert hes0.get("coopEndTurnPhaseCounter") == 0, (
            f"host coopEndTurnPhaseCounter is not 0 at t=0: "
            f"{hes0.get('coopEndTurnPhaseCounter')}")
        t0_tally = hes0.get("coopEndTurnTally", {})
        assert t0_tally == {"turn": 0, "side": "", "count": 0, "needed": 0, "ready": []}, (
            f"host coopEndTurnTally at t=0 is not the reset() default: {t0_tally}")
        # The fixture's OWN needed==2 premise, proven functionally (same
        # method SPEC 9's repro_atom_side_begin uses for its
        # "activeSeats==[0,1]" functional proxy) - the CoopEndTurn tally
        # object's own needed field is asserted ==2 for the first time at L2.
        hs0 = battle_state(host)
        seat0_units = [u for u in hs0["units"] if u.get("coop") == COOP_SEAT_0
                       and u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
        seat1_units = [u for u in hs0["units"] if u.get("coop") == COOP_SEAT_1
                       and u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
        assert seat0_units, "classic boot: seat 0 (host) has no live player unit"
        assert seat1_units, "classic boot: seat 1 (client) has no live player unit"
        assert_hash_clean(host, client, full=True, what="L1 t=0 baseline")
        print(f"[L1] baseline OK: coopEndTurnText=='' and coopEndTurnArmed==False "
              f"on both machines; host tally is the reset() default {t0_tally}; "
              f"seat 0 has {len(seat0_units)} live unit(s), seat 1 has "
              f"{len(seat1_units)} (the needed==2 fixture premise); 9/9 buckets "
              "EQUAL")

        turn0 = hs0["turn"]
        side0 = hs0["side"]

        # ----- L2: the client arms through its REAL button -----
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
        print(f"[L2] client armed via its real button: both machines paint "
              f"{TALLY_TEXT_1_OF_2!r}; client armed=True / host armed=False; "
              f"turn/side unchanged ({turn0}/{side0}); host tally={het}")

        # ----- L3: un-arm on the SAME machine -----
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
            f"D-24: un-arming (a legal parallel-mode press) advanced the side: "
            f"{turn0}/{side0} -> {hs_now['turn']}/{hs_now['side']}")
        assert cs_now["turn"] == turn0 and cs_now["side"] == side0, (
            f"D-24: un-arming advanced the client's turn/side: {turn0}/{side0} "
            f"-> {cs_now['turn']}/{cs_now['side']}")
        het = event_state(host).get("coopEndTurnTally", {})
        assert het.get("count") == 0, (
            f"host tally count after the un-arm is not back to 0: {het}")
        print(f"[L3] un-arm via the same real button: no advance; both machines "
              f"paint '' (F170); client armed=False; host tally count back to "
              f"0 ({het})")

        # ----- L4: the CONSTRUCTED stale press (REV E.48 C.2 / D57) -----
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
            f"D57/WR-4: the stale press (turn={stale_turn}, current={current_turn}) "
            f"changed the host's stored readies: {host_count_before} -> "
            f"{host_count_after}")
        assert battle_state(client).get("coopEndTurnArmed") is False, (
            "the CONSTRUCTED stale press armed the client's button")
        assert battle_state(client).get("coopEndTurnText") == "", (
            f"the CONSTRUCTED stale press painted a non-empty tally text: "
            f"{battle_state(client).get('coopEndTurnText')!r}")
        client_seen_after_stale = event_state(client).get("coopEndTurnTalliesSeen")
        print(f"[L4 stale] turn={stale_turn} (current={current_turn}) DROPPED and "
              f"ANSWERED: host count unchanged ({host_count_before}); client "
              f"talliesSeen {client_seen_before} -> {client_seen_after_stale}; "
              "client armed=False; text==''")

        # Positive control, same leg: the same lever with the CURRENT turn
        # must arm. Leave the client ARMED going into L5.
        client.ok({"cmd": "battle_end_turn_ready", "turn": current_turn, "ready": True})

        def host_shows_1_of_2_again():
            return True if battle_state(host).get("coopEndTurnText") == TALLY_TEXT_1_OF_2 else None
        client.wait_for("host paints END TURN 1/2 after the lever's CURRENT-turn press",
                        host_shows_1_of_2_again, timeout=15)
        assert battle_state(client).get("coopEndTurnArmed") is True, (
            "the CURRENT-turn lever press (positive control) did not arm the client")
        print(f"[L4 positive control] turn={current_turn} (current) ARMED via the "
              f"same lever: client armed=True; host text=={TALLY_TEXT_1_OF_2!r}; "
              "client left ARMED for L5")

        # ----- L5: both seats armed -> the side advances, one full cycle -----
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
        hh, ch = assert_hash_clean(host, client, full=True, what="L5 post-cycle boundary")
        print(f"[L5] full cycle: 3 side_transition + 3 side_begin envelopes; "
              f"side-phase counter +3 on both (host {host_counter_before}->"
              f"{host_counter_after}, client {client_counter_before}->"
              f"{client_counter_after}) while battle_state.turn +1 on both "
              f"({turn_before}->{turn_after_h}); side back to FACTION_PLAYER; "
              f"{len(hh)} buckets EQUAL")

        # ----- L6: the tally is INERT on hostile/neutral; stored readies do
        # NOT survive a boundary -----
        # BUILDER FINDING (measured, not inferred - WV-D77 instrument-first).
        # The delta here is TWO, not one. Traced directly in
        # connectionTCP.cpp's applyReady() (read at ef9b8d55b): every
        # applyReady() call - INCLUDING the host's own final arming press -
        # calls emitTally() BEFORE tryCommit(), so the press that completes
        # readiness (count==needed) mints its OWN genuine tally (a real
        # "2/2" snapshot the players would see painted for an instant)
        # BEFORE requestEndTurn() ever runs. Only THEN does the boundary
        # cascade start: PLAYER->HOSTILE (needed==0, INERT) ->
        # HOSTILE->NEUTRAL (needed==0, INERT) -> NEUTRAL->PLAYER (needed==2,
        # GENUINE). So "host end_turn_button; drive the full cycle", measured
        # from a baseline taken BEFORE the host's own press (as SPEC 10 (f)
        # orders the steps), sees exactly TWO genuine tallies: the host's own
        # commit press, plus the sole non-inert boundary. A live run
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
        print(f"[L6] tally INERT on hostile+neutral: talliesSeen advanced by "
              f"exactly TWO on both machines (the host's own commit press + "
              f"the sole non-inert boundary; host {host_seen_before_cycle}->"
              f"{host_seen_after_cycle}, client {client_seen_before_cycle}->"
              f"{client_seen_after_cycle}); the new player side reads "
              "count=0/needed=2 on both; text==''; button un-latched")

        # ----- L7': REV E.51 E51.3 - the F174 authority-reset clear, LAST
        # leg, ends the client. REV E.48 C.3's seat-loss claim is DELETED
        # (owner ruling D69 = (d), 2026-09-12): a client leaving a live coop
        # battle HALTS the game for everyone until it reconnects
        # (pause-on-leave, r4 T4/T5), so "the host advances the side with a
        # single vote" is not a true statement and is asserted NOWHERE
        # below. L7' asserts NOTHING about `needed`, nothing about a side
        # advance, and nothing about the client. -----

        # The HOST arms its OWN seat first (count 1 of needed 2), so the
        # side does NOT advance (measured - see the pinned R1 table: host
        # presses END TURN alone -> text=='END TURN 1/2', armed==True, side
        # stays 0, turn stays unchanged).
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def host_armed_pre_drop():
            bs = battle_state(host)
            return True if (bs.get("coopEndTurnText") == TALLY_TEXT_1_OF_2
                             and bs.get("coopEndTurnArmed") is True) else None
        host.wait_for("host paints END TURN 1/2 and its own button arms "
                      "before the drop (non-vacuity, REV E.51 E51.3)",
                      host_armed_pre_drop, timeout=15)
        # The pre-drop capture: makes the post-drop assertion below
        # non-vacuous, and every failure message quotes it.
        pre_drop_text = battle_state(host).get("coopEndTurnText")
        pre_drop_armed = battle_state(host).get("coopEndTurnArmed")

        client.ok({"cmd": "disconnect_to_menu"})

        def host_text_cleared():
            return True if battle_state(host).get("coopEndTurnText") == "" else None
        host.wait_for("host's painted tally text clears at battle-authority "
                      "reset after the client's departure (REV E.51 E51.3 / "
                      "D69 / F174)", host_text_cleared, timeout=20)

        post_drop = battle_state(host)
        assert post_drop.get("inBattle") is True, (
            f"L7' (REV E.51 E51.3 / D69 / F174): host is not inBattle after "
            f"the client's departure - pre-drop was text={pre_drop_text!r} "
            f"armed={pre_drop_armed!r}: {post_drop}")
        assert post_drop.get("coopEndTurnText") == "", (
            f"L7' (REV E.51 E51.3 / D69 / F174): host's coopEndTurnText did "
            f"not clear at battle-authority reset - pre-drop was "
            f"{pre_drop_text!r}, post-drop is "
            f"{post_drop.get('coopEndTurnText')!r}")
        assert post_drop.get("coopEndTurnArmed") is False, (
            f"L7' (REV E.51 E51.3 / D69 / F174): host's coopEndTurnArmed did "
            f"not clear at battle-authority reset - pre-drop was "
            f"{pre_drop_armed!r}, post-drop is "
            f"{post_drop.get('coopEndTurnArmed')!r}")
        print(f"[L7'] F174 authority-reset clear (REV E.51 E51.3 / D69): "
              f"after the client's disconnect_to_menu, the host's painted "
              f"tally and armed bit were CLEARED - text {pre_drop_text!r} -> "
              f"{post_drop.get('coopEndTurnText')!r}, armed "
              f"{pre_drop_armed!r} -> {post_drop.get('coopEndTurnArmed')!r}")

        print("PASS: test_rw_end_turn_tally BOOT A (classic, seat_count=2)")
    finally:
        host.shutdown()
        client.shutdown()


def run_boot_b():
    """REV E.48 C.4 - the SPECTATOR boot: the client is never seated
    (`seat_client=False`), so it is a CONNECTED seat with zero live
    commandable units on the active side - not a LIVE seat, never counted in
    `needed`, never handed the baton, and its press is dropped and answered
    with the tally exactly like a stale press is (D57's same WR-4
    discipline)."""
    port = "48161"
    host_dir = make_user_dir("test_rw_end_turn_tally_b_host")
    client_dir = make_user_dir("test_rw_end_turn_tally_b_client")
    host = GameClient("host", 49552, host_dir)
    client = GameClient("client", 49553, client_dir)
    seated = {}
    try:
        bring_up_lobby(host, client, port)
        session.drive_to_battlescape(host, client, seated, mission=MISSION,
                                      pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": 1}),
                                      seat_client=False)

        pinned = pin_ai_neutral(host, client, tag="end_turn_tally-b")
        print(f"[boot B] pin_ai_neutral pinned {len(pinned)} unit(s)")

        hs0 = battle_state(host)
        seat1_units = [u for u in hs0["units"] if u.get("coop") == COOP_SEAT_1]
        assert not seat1_units, (
            f"boot B premise broke: the UNSEATED client owns unit(s) anyway: "
            f"{seat1_units}")
        seat0_units = [u for u in hs0["units"] if u.get("coop") == COOP_SEAT_0
                       and u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
        assert seat0_units, "boot B: seat 0 (host) has no live player unit"

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
            f"REV E.48 C.4: needed is not 1 with the client UNSEATED: {het}")
        assert het.get("count") == 0, (
            f"the spectator's press changed the host's stored readies: {het}")
        assert battle_state(client).get("coopEndTurnArmed") is False, (
            "the spectator's press left the client's button armed (D53/C.4: a "
            "connected seat with no live unit is not a live seat)")
        hs_now = battle_state(host)
        cs_now = battle_state(client)
        assert hs_now["turn"] == turn0 and hs_now["side"] == FACTION_PLAYER, (
            f"the spectator's press advanced the host's side: {hs_now}")
        assert cs_now["turn"] == turn0 and cs_now["side"] == FACTION_PLAYER, (
            f"the spectator's press advanced the client's side: {cs_now}")
        print(f"[boot B] spectator's press changed nothing and was answered: "
              f"needed==1; host tally count unchanged (0); client talliesSeen "
              f"{client_seen_before} -> "
              f"{event_state(client).get('coopEndTurnTalliesSeen')}; client "
              "armed=False; no side advance")

        # ----- the HOST's press ALONE advances the side: measured via
        # counters taken AFTER the full cycle (REV E.51 E51.4). orch41b
        # found this driver racing a transient phase: with zero human seats
        # on the hostile and neutral phases, the whole three-transition
        # cycle completes in ~0.35s, so a poll for side==FACTION_HOSTILE
        # (the old drive_to_side helper, now DELETED) is usually already
        # gone before the first poll lands. The hostile/neutral phases'
        # inertness is proven by the counter deltas below, never by
        # catching the transient phase mid-flight - a poll for it is a
        # STOP-IF (REV E.48 SS.A.8), not something to slow down or retry.
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

        hh, ch = assert_hash_clean(host, client, full=True, what="boot B post-cycle")
        print(f"[boot B] ONE host end_turn_button + full cycle (REV E.51 "
              f"E51.4, measured after the cycle - never polled mid-flight): "
              f"phase counter +3 on both (host {host_counter_before}->"
              f"{host_counter_after}, client {client_counter_before}->"
              f"{client_counter_after}); talliesSeen +2 on both (host "
              f"{host_seen_before_cycle}->{host_seen_after_cycle}, client "
              f"{client_seen_before_cycle}->{client_seen_after_cycle}); "
              f"battle_state.turn {turn0}->{turn_after_h}, side back to "
              f"FACTION_PLAYER on both; new-side tally "
              f"count=0/ready=[]/needed=1/side='player'; text=='' and "
              f"armed=False on both; {len(hh)} buckets EQUAL")

        print("PASS: test_rw_end_turn_tally BOOT B (spectator, client unseated)")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    run_boot_a()
    run_boot_b()
    print("ALL SPEC 10 test_rw_end_turn_tally TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("test_rw_end_turn_tally", e.tracking, str(e))
        print(f"\ntest_rw_end_turn_tally: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(2)
    except AssertionError as e:
        print(f"\ntest_rw_end_turn_tally: FAIL\nAssertionError: {e}")
        sys.exit(2)
    except TimeoutError as e:
        print(f"\ntest_rw_end_turn_tally: FAIL\nTimeoutError: {e}")
        sys.exit(2)
