"""W1-P13c (SPEC 11) - test_rw_turn_baton.py: the TRADITIONAL baton, the
off-baton gray bottom bar and the persistent off-turn banner (REV E.48 SS.D,
REV E.52 E52.1, REV E.53 E53.2/E53.3, REV E.54 E54.1-E54.4, REV E.55
E55.1-E55.2, REV E.56 E56.1-E56.2). Engine landed by commit 0 (799d34961,
"feat(coop): W1-P13c traditional baton, off-baton gray bar and off-turn
banner"), already verified by the orchestrator; this is the tests-only
commit.

AI-NEUTRAL PINNING (WV-D45/IR2-9, REV E.48 SS.B.2/D49) - imports the SAME
`session.pin_ai_neutral()` helper every boundary-crossing test in the SPEC
9..15 chain uses (written by SPEC 9, imported by 10, 11, 12, 13) rather than
re-implementing it. Both boots pin mission STR_SMALL_SCOUT (no civilians, no
terror units, exactly one alien on every seed) and `set_seed 1`.

TRADITIONAL MODE, TWO SEATS, ONE SIDE. The HOST sets `CoopTurnMode` to
`traditional` before the offer; the CLIENT's own option is left at the D-26
default (parallel), so `live_mode(host) == live_mode(client) ==
"traditional"` is a genuine wire-mirror proof (the same non-vacuity shape
`test_rw_turn_mode.test_wire_traditional` already uses), not a locally-set
coincidence.

BOOT A (two seated seats, seat_count=2): host seat 0 holds the baton first
(D-23 - host first, then join order by seat index). The off-baton client
sees the WHOLE battlescape exactly as the on-baton machine does (REV E.53
E53.1 - the old D-24b HIDDEN-widget list is RETIRED; NOTHING is hidden
anymore), with two differences: the bottom `_icons` bar is rendered through
a gray lookup (REV E.53 E53.2), and a persistent `STR_COOP_WAIT_TURN` banner
names the baton holder (REV E.56). Every action that changes the shared
battle (move, kneel, turn, END TURN) is refused with the rendered
`STR_COOP_DENY_NOT_YOUR_GO` text; opening the hand-item ACTION MENU is
ALLOWED off-turn (REV E.54 E54.1, the owner's TU-budgeting exception) and
mints/paints nothing. The host's END TURN PASSES the baton to seat 1 without
touching the WV-D46 side-phase counter (D-23: a pass is not a side phase); a
`ready:false` from the spent seat changes nothing and is answered with the
current tally (D-24, no take-back); the client's END TURN - the LAST pass -
closes the side through the SAME chokepoint parallel mode uses.

NEGATIVE CONTROL (measured at the tip, pre-commit-0, orch42c's capture -
quoted verbatim here and in the builder's acceptance report BEFORE the green
is claimed): a real CLIENT press of the kneel button during the HOST's go
SUCCEEDED on the pre-commit-0 build - `kneeled=True`,
`coopLocalExecBlocked` 0->0, `lastSeqEmitted` 0->0, banner `''`. Commit 0
(799d34961) is what turns that into BOOT A's A6 refusal below.

BOOT B (client UNSEATED via `seat_client=False`): REV E.48 C.4's spectator
case - a CONNECTED seat with no live commandable unit is NOT a live seat and
is never handed the baton, so `coopActiveSeat` reads 0 at entry and NEVER 1
at any point in the boot; the host's SINGLE press therefore closes the side
directly (SPEC 11 (f)'s "a seat with no live units is SKIPPED").

Widgets are identified by TYPE + RECT through the EXISTING `list_widgets`
probe (REV E.52 E52.2 / E53.3) - no new probe. A row that matches zero or
several surfaces is a RED naming the row, never a fallback to index.

Cites SPEC 11, REV E.48 SS.A/SS.D, REV E.52 (D71/E52.1, D72/E52.2), REV E.53
(D73/D74, E53.1-E53.4), REV E.54 (D75, E54.1-E54.6), REV E.55 (D76, E55.1-
E55.3), REV E.56 (D77, E56.1-E56.3), D-23, D-24, D-24b (amended by E53.1),
WV-D46, WV-D13.

Run:  python tools/coop_test/test_rw_turn_baton.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean, FACTION_PLAYER
from test_rw_turn_mode import set_mode, live_mode, TRADITIONAL, PARALLEL
from test_rw_input_gating import units_by_id, tile_click
from test_rw_feedback import banner_of, wait_banner

COOP_SEAT_0 = 0
COOP_SEAT_1 = 1
MISSION = "STR_SMALL_SCOUT"

BATTLESCAPE_STATE = "class OpenXcom::BattlescapeState"
ACTION_MENU_STATE = "class OpenXcom::ActionMenuState"
ICONS_TYPE = "class OpenXcom::InteractiveSurface"
TEXT_TYPE = "class OpenXcom::Text"
MAP_TYPE = "class OpenXcom::Map"

# (x, y, w, h) - REV E.48 R1 pinned measured values, current tip.
ICONS_RECT = (0, 144, 320, 56)
END_TURN_TEXT_RECT = (152, 134, 120, 9)
WAIT_TEXT_RECT = (0, 124, 320, 9)
KNEEL_RECT = (112, 160, 32, 16)
RHAND_RECT = (280, 148, 32, 48)
KNEEL_NTH = 7
RHAND_NTH = 25


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def get_coop(gc):
    return gc.cmd({"cmd": "get_coop"})


# ----- fixture bring-up (inline copy, repro_atom_side_transition.py /
# test_rw_end_turn_tally.py precedent - every coop test in this tree carries
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


def pre_ok_traditional(h):
    """`session.drive_to_battlescape`'s `pre_ok` window (invoked immediately
    before `newbattle_ok`, well before the FX-1 offer send at the
    post-briefing `click_widget match=ok` step) - the one place every SPEC 11
    boot sets CoopTurnMode=traditional on the HOST before the offer, folded
    together with the pinned-seed lever every boundary-crossing test in this
    chain uses."""
    set_mode(h, TRADITIONAL)
    h.ok({"cmd": "set_seed", "seed": 1})


def dismiss_next_turn_if_present(gc):
    """test_rw_end_turn_tally.py's own helper, copied: if `gc`'s TOP state is
    a NextTurnState, close it via the REAL NextTurnState::close() path
    (TestServer `close_nextturn`) rather than dismiss_popup (which only pops
    the state WITHOUT running close()). Returns whether one was found (and
    closed); never raises on absence."""
    lw = gc.cmd({"cmd": "list_widgets"})
    if "NextTurnState" not in lw.get("state", ""):
        return False
    r = gc.cmd({"cmd": "close_nextturn"})
    assert r.get("ok"), (
        f"close_nextturn failed on a machine whose list_widgets just reported "
        f"NextTurnState on top: {r}")
    return True


def drive_full_cycle(host, client, turn0, timeout=60):
    """test_rw_end_turn_tally.py's own driver, copied: presses nothing itself
    (the caller already pressed the closing END TURN) - polls both machines
    to completion, dismissing any NextTurnState via close_nextturn on BOTH
    machines. Raises TimeoutError if the full cycle never completes on both
    machines."""
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
        f"test_rw_turn_baton: full cycle did not complete within {timeout}s - "
        f"host={battle_state(host)} client={battle_state(client)}")


def find_widget(widgets, type_name, x, y, width, height, label):
    """REV E.52 E52.2 / E53.3: identify a RULED widget by TYPE + RECT through
    the EXISTING list_widgets probe - no new probe. A zero or several match
    is a RED naming the row, never a fallback to index."""
    matches = [row for row in widgets
               if row.get("type") == type_name and row.get("x") == x
               and row.get("y") == y and row.get("w") == width and row.get("h") == height]
    assert len(matches) == 1, (
        f"{label}: expected exactly one {type_name!r} surface at "
        f"{width}x{height}@({x},{y}), found {len(matches)} (zero or several "
        f"is a RED naming the row - REV E.52 E52.2 / E53.3): {matches}")
    return matches[0]


def find_adjacent_empty_tile(gc, unit):
    """The FIRST of the 8 immediate (x,y) neighbours of `unit`'s tile,
    tried at its OWN level first and then one level down/up (a ramp inside a
    craft interior can put the walkable floor at z+-1 for the SAME (x,y)
    offset), that is floored and unoccupied - the move-refusal leg needs
    exactly one ordinary ground tile adjacent to the currently selected
    unit, not a specific one. A deterministic single scan of the 8x3 static
    candidates, never a loop that re-tries a click (REV E.48 SS.A.8)."""
    st = battle_state(gc)
    occupied = {(u["x"], u["y"], u["z"]) for u in st.get("units", []) if not u.get("isOut")}
    ux, uy, uz = unit["x"], unit["y"], unit["z"]
    for dx, dy in zip(session.DIR_DX, session.DIR_DY):
        for dz in (0, -1, 1):
            t = (ux + dx, uy + dy, uz + dz)
            if session.tile_walkable(gc, t, occupied):
                return t
    return None


def click_nth(gc, nth, button="left"):
    """click_widget by index, returning the response (baseX/baseY self-
    verify the rect) - test_rw_input_gating.py's click_button() precedent,
    kept local because that helper discards the response this file needs."""
    r = gc.ok({"cmd": "click_widget", "nth": nth, "button": button})
    time.sleep(0.3)
    return r


def run_boot_a():
    """BOOT A - two seated seats, traditional. Legs run in EXACTLY this
    order - the deny banner has a 6000 ms Terminal dwell
    (kCoopBannerDwellMs, CoopBattleUi.h:399) - running them in any other
    order makes an "unchanged"/"changed" comparison vacuous:
      A1  entry tally (REV E.52 E52.1)
      A2  banner BEFORE the pass (REV E.56 E56.2)
      A3  nothing hidden - full list_widgets parity except the two banner
          surfaces (REV E.53 E53.3); the post-pass half runs after A9
      A4  gray, whole rect, zero tolerance (REV E.53 E53.3)
      A5  the action menu is ALLOWED off-baton, mints/paints nothing
          (REV E.54 E54.3)
      A6  kneel is REFUSED off-baton, BEFORE -> AFTER (REV E.54 E54.2 /
          REV E.55 E55.1-E55.2) - the negative control is quoted in this
          function's own docstring above (module level)
      A7  the banner returns after the deny dwell
      A8  a move is REFUSED off-baton, BEFORE -> AFTER (REV E.54 E54.4 pin 4)
      A9  the host's END TURN passes the baton, does NOT advance the side
          (D-23)
      A10 the banner follows the baton (REV E.56 E56.2)
      A11 the gray gate follows the baton
      A12 no take-back (D-24): a spent seat's ready:false changes nothing
          and is answered
      A13 the client's END TURN - the LAST pass - closes the side
      A14 kept surfaces + hash-clean at A1 and after A13
    """
    port = "48270"
    host_dir = make_user_dir("test_rw_turn_baton_a_host")
    client_dir = make_user_dir("test_rw_turn_baton_a_client")
    host = GameClient("host", 49670, host_dir)
    client = GameClient("client", 49671, client_dir)
    seated = {}
    try:
        bring_up_lobby(host, client, port)
        session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                      pre_ok=pre_ok_traditional)

        assert live_mode(host) == TRADITIONAL and live_mode(client) == TRADITIONAL, (
            f"boot A fixture: expected both machines' live battle mode to be "
            f"{TRADITIONAL!r} (host set it, client mirrors off the wire while "
            f"its OWN option stays {PARALLEL!r}): host={live_mode(host)!r} "
            f"client={live_mode(client)!r}")

        pinned = pin_ai_neutral(host, client, tag="turn_baton-a")
        assert len(pinned) > 0, (
            f"pin_ai_neutral pinned ZERO NONE-seat non-player units on a "
            f"CLASSIC {MISSION} boot - the premise is unexercised (M9a-3)")

        hs0 = battle_state(host)
        seat0_units = [u for u in hs0["units"] if u.get("coop") == COOP_SEAT_0
                       and u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
        seat1_units = [u for u in hs0["units"] if u.get("coop") == COOP_SEAT_1
                       and u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
        assert seat0_units, "boot A: seat 0 (host) has no live player unit"
        assert seat1_units, "boot A: seat 1 (client) has no live player unit"

        # ----- A1: ENTRY (REV E.52 E52.1) -----
        for gc, who in ((host, "host"), (client, "client")):
            es = event_state(gc)
            assert es.get("coopActiveSeat") == 0, (
                f"{who}: A1 coopActiveSeat is not 0 (D-23 first-live-seat "
                f"order, host seat 0 first): {es.get('coopActiveSeat')}")
            tally = es.get("coopEndTurnTally", {})
            assert tally.get("needed") == 1 and tally.get("count") == 0 and tally.get("ready") == [], (
                f"{who}: A1 entry tally is not needed=1/count=0/ready=[]: {tally}")
            assert es.get("coopEndTurnPhaseCounter") == 0, (
                f"{who}: A1 coopEndTurnPhaseCounter is not 0: "
                f"{es.get('coopEndTurnPhaseCounter')}")
            assert battle_state(gc).get("coopEndTurnText") == "", (
                f"{who}: A1 coopEndTurnText is not empty: "
                f"{battle_state(gc).get('coopEndTurnText')!r}")

        turn0 = hs0["turn"]
        side0 = hs0["side"]
        counter_a1 = event_state(host).get("coopEndTurnPhaseCounter")
        host_wait_before_pass = battle_state(host).get("coopWaitText")

        assert_hash_clean(host, client, full=True, what="A1 entry")
        print(f"[A1] entry tally OK on both machines: coopActiveSeat==0, "
              f"needed=1/count=0/ready=[]/counter=0; turn0={turn0} side0={side0}")

        # ----- A2: BANNER BEFORE (REV E.56 E56.2) -----
        name_for_client = get_coop(client).get("clientName")
        assert name_for_client, (
            "A2: get_coop(client)['clientName'] is empty on the CLIENT - "
            "cannot build the off-baton banner text")
        banner_expected_client = f"It is {name_for_client}'s turn"

        wait_banner(client, banner_expected_client,
                    "A2 (REV E.56 E56.2): client's off-baton banner names "
                    "the baton holder", timeout=20)
        assert banner_of(host) != banner_expected_client, (
            f"A2: the HOST's own banner equals the OFF-BATON text while it "
            f"holds the baton: {banner_of(host)!r}")
        assert battle_state(client).get("coopOffBatonGray") is True, (
            "A2: client's coopOffBatonGray gate is not True while off-baton")
        assert battle_state(host).get("coopOffBatonGray") is False, (
            "A2: host's coopOffBatonGray gate is not False during its own go")
        print(f"[A2] off-baton banner OK: client={banner_expected_client!r}, "
              f"host's own banner ({banner_of(host)!r}) is NOT the off-baton "
              "text; coopOffBatonGray client=True/host=False")

        # ----- A3: NOTHING HIDDEN (REV E.53 E53.3) -----
        lw_entry = client.cmd({"cmd": "list_widgets"})
        assert lw_entry.get("ok") and lw_entry.get("state") == BATTLESCAPE_STATE, (
            f"A3: list_widgets on the client did not report BattlescapeState: "
            f"{lw_entry}")
        widgets_entry = lw_entry["widgets"]
        assert len(widgets_entry) == 87, (
            f"A3: expected 87 surfaces on the client's BattlescapeState, got "
            f"{len(widgets_entry)}")

        wait_row = find_widget(widgets_entry, TEXT_TYPE, *WAIT_TEXT_RECT, "A3 _txtCoopWait")
        endturn_row = find_widget(widgets_entry, TEXT_TYPE, *END_TURN_TEXT_RECT, "A3 _txtCoopEndTurn")
        assert wait_row["visible"] is True and wait_row.get("text") == banner_expected_client, (
            f"A3: _txtCoopWait is not VISIBLE with the off-baton banner text: "
            f"{wait_row}")
        assert endturn_row["visible"] is False, (
            f"A3: _txtCoopEndTurn is visible at count==0 (SPEC 10's rule says "
            f"empty text -> hidden): {endturn_row}")
        entry_visibility_by_idx = {w["idx"]: w["visible"] for w in widgets_entry}
        print("[A3] entry snapshot OK: 87 surfaces; _txtCoopWait VISIBLE with "
              "the banner text; _txtCoopEndTurn hidden (count==0); the "
              "post-pass parity check follows after A9")

        # ----- A4: GRAY, WHOLE RECT (REV E.53 E53.3) -----
        find_widget(widgets_entry, ICONS_TYPE, *ICONS_RECT, "A4 _icons (client)")
        rc = client.cmd({"cmd": "screen_pixels", "x": ICONS_RECT[0], "y": ICONS_RECT[1],
                          "w": ICONS_RECT[2], "h": ICONS_RECT[3]})
        assert rc.get("ok"), f"A4: screen_pixels failed on the client: {rc}"
        assert rc.get("mode") == "lut", (
            f"A4: client off-baton screen_pixels mode is {rc.get('mode')!r}, "
            "expected 'lut'")
        outside_c = sum(1 for p in rc["pixels"] if not (0 <= p <= 15))
        assert outside_c == 0, (
            f"A4: client off-baton gray rect has {outside_c} indices outside "
            "0..15, expected exactly 0")

        lw_host_a4 = host.cmd({"cmd": "list_widgets"})
        find_widget(lw_host_a4["widgets"], ICONS_TYPE, *ICONS_RECT, "A4 _icons (host)")
        rh = host.cmd({"cmd": "screen_pixels", "x": ICONS_RECT[0], "y": ICONS_RECT[1],
                        "w": ICONS_RECT[2], "h": ICONS_RECT[3]})
        assert rh.get("ok"), f"A4: screen_pixels failed on the host: {rh}"
        assert rh.get("mode") == "off", (
            f"A4: host on-baton (own go) screen_pixels mode is "
            f"{rh.get('mode')!r}, expected 'off'")
        outside_h = sum(1 for p in rh["pixels"] if not (0 <= p <= 15))
        assert outside_h > 0, (
            "A4: host on-baton gray rect has 0 indices outside 0..15 - the "
            "non-vacuity control failed")
        print(f"[A4] gray gate OK: client off-baton mode=lut/outside=0 "
              f"(whole {ICONS_RECT[2]}x{ICONS_RECT[3]} rect); host own-go "
              f"mode=off/outside={outside_h}")

        # ----- A5: ACTION MENU (REV E.54 E54.3) -----
        before_a5 = battle_state(client).get("coopWaitText")
        blocked_a5_0 = event_state(client).get("coopLocalExecBlocked")
        seq_a5_0 = event_state(client).get("lastSeqEmitted")

        r5 = click_nth(client, RHAND_NTH)
        assert (r5.get("baseX") == RHAND_RECT[0] + RHAND_RECT[2] // 2
                and r5.get("baseY") == RHAND_RECT[1] + RHAND_RECT[3] // 2), (
            f"A5: click_widget nth={RHAND_NTH} did not land on the right-hand "
            f"box centre of {RHAND_RECT}: {r5}")

        lw_menu = client.cmd({"cmd": "list_widgets"})
        assert lw_menu.get("state") == ACTION_MENU_STATE, (
            f"A5: opening the hand box did not reach ActionMenuState: {lw_menu}")
        visible_rows = [w for w in lw_menu["widgets"]
                        if w.get("visible") and "ActionMenuItem" in w.get("type", "")]
        assert len(visible_rows) >= 1, (
            f"A5: no VISIBLE ActionMenuItem row in the opened menu: {lw_menu}")
        assert event_state(client).get("lastSeqEmitted") == seq_a5_0, (
            "A5: opening the action menu minted a real action (lastSeqEmitted "
            f"changed: {seq_a5_0} -> {event_state(client).get('lastSeqEmitted')})")
        assert event_state(client).get("coopLocalExecBlocked") == blocked_a5_0, (
            "A5: opening the action menu was REFUSED (coopLocalExecBlocked "
            f"moved: {blocked_a5_0} -> "
            f"{event_state(client).get('coopLocalExecBlocked')}) - the menu "
            "must be ALLOWED off-baton (E54.1)")
        assert battle_state(client).get("coopWaitText") == before_a5, (
            f"A5: opening the action menu changed the banner: {before_a5!r} -> "
            f"{battle_state(client).get('coopWaitText')!r}")

        client.ok({"cmd": "inject_input", "kind": "key", "key": 27})
        lw_after_dismiss = client.cmd({"cmd": "list_widgets"})
        assert lw_after_dismiss.get("state") == BATTLESCAPE_STATE, (
            f"A5: dismissing the menu did not return to BattlescapeState: "
            f"{lw_after_dismiss}")
        assert len(lw_after_dismiss["widgets"]) == 87, (
            f"A5: surface count changed after dismissing the menu: "
            f"{len(lw_after_dismiss['widgets'])}")
        assert battle_state(client).get("coopWaitText") == before_a5, (
            f"A5: the banner changed across dismiss: {before_a5!r} -> "
            f"{battle_state(client).get('coopWaitText')!r}")
        print(f"[A5] action menu ALLOWED off-baton: opened ActionMenuState "
              f"({len(visible_rows)} visible row(s)), minted nothing "
              f"(lastSeqEmitted=={seq_a5_0}, coopLocalExecBlocked=="
              f"{blocked_a5_0}), banner unchanged ({before_a5!r}); dismissed "
              "back to BattlescapeState (87 surfaces)")

        # ----- A6: KNEEL REFUSAL (REV E.54 E54.2 / REV E.55 E55.1) -----
        before_a6 = battle_state(client).get("coopWaitText")
        blocked_a6_0 = event_state(client).get("coopLocalExecBlocked")
        seq_a6_0 = event_state(client).get("lastSeqEmitted")
        cbs_a6 = battle_state(client)
        sel_id_a6 = cbs_a6.get("selectedId")
        sel_unit_c_before = units_by_id(cbs_a6).get(sel_id_a6)
        sel_unit_h_before = units_by_id(battle_state(host)).get(sel_id_a6)
        assert sel_unit_c_before is not None and sel_unit_h_before is not None, (
            f"A6: client's selectedId {sel_id_a6} has no matching unit on "
            "both machines")
        kneeled_before_c = sel_unit_c_before["kneeled"]
        kneeled_before_h = sel_unit_h_before["kneeled"]

        r6 = click_nth(client, KNEEL_NTH)
        assert (r6.get("baseX") == KNEEL_RECT[0] + KNEEL_RECT[2] // 2
                and r6.get("baseY") == KNEEL_RECT[1] + KNEEL_RECT[3] // 2), (
            f"A6: click_widget nth={KNEEL_NTH} did not land on the kneel "
            f"button centre of {KNEEL_RECT}: {r6}")

        expected_deny = f"Not your turn - waiting for {name_for_client}"
        after_a6 = battle_state(client).get("coopWaitText")
        assert after_a6 == expected_deny and after_a6 != before_a6, (
            f"A6 STOP-IF: kneel press is not refused with the exact rendered "
            f"STR_COOP_DENY_NOT_YOUR_GO text - before={before_a6!r} "
            f"after={after_a6!r}, expected {expected_deny!r}")
        assert event_state(client).get("coopLocalExecBlocked") == blocked_a6_0 + 1, (
            f"A6: coopLocalExecBlocked did not rise by exactly 1: "
            f"{blocked_a6_0} -> {event_state(client).get('coopLocalExecBlocked')}")
        assert event_state(client).get("lastSeqEmitted") == seq_a6_0, (
            "A6: the refused kneel minted a real action (lastSeqEmitted "
            f"{seq_a6_0} -> {event_state(client).get('lastSeqEmitted')})")
        kneeled_after_c = units_by_id(battle_state(client)).get(sel_id_a6)["kneeled"]
        kneeled_after_h = units_by_id(battle_state(host)).get(sel_id_a6)["kneeled"]
        assert kneeled_after_c == kneeled_before_c and kneeled_after_h == kneeled_before_h, (
            f"A6: the refused kneel changed the unit's kneeled state - client "
            f"{kneeled_before_c}->{kneeled_after_c}, host "
            f"{kneeled_before_h}->{kneeled_after_h}")
        print(f"[A6] kneel REFUSED off-baton: BEFORE={before_a6!r} -> "
              f"AFTER={after_a6!r}; coopLocalExecBlocked {blocked_a6_0} -> "
              f"{blocked_a6_0 + 1}; lastSeqEmitted unchanged ({seq_a6_0}); "
              f"kneeled unchanged on both machines ({kneeled_before_c})")

        # ----- A7: BANNER RETURNS -----
        wait_banner(client, banner_expected_client,
                    "A7: banner returns after the kneel deny's 6s Terminal "
                    "dwell", timeout=20)
        print(f"[A7] banner returned to {banner_expected_client!r} after the "
              "deny dwell")

        # ----- A8: MOVE REFUSAL (REV E.54 E54.4 pin 4) -----
        before_a8 = battle_state(client).get("coopWaitText")
        cbs_a8 = battle_state(client)
        sel_unit_a8 = units_by_id(cbs_a8).get(cbs_a8.get("selectedId"))
        assert sel_unit_a8 is not None, (
            f"A8: client's selectedId {cbs_a8.get('selectedId')} has no "
            "matching unit")
        adj_tile = find_adjacent_empty_tile(client, sel_unit_a8)
        if adj_tile is None:
            st_dbg = battle_state(client)
            occ_dbg = {(u["x"], u["y"], u["z"]) for u in st_dbg.get("units", []) if not u.get("isOut")}
            print(f"[A8 DEBUG] unit {sel_unit_a8['id']} at "
                  f"({sel_unit_a8['x']},{sel_unit_a8['y']},{sel_unit_a8['z']}); "
                  f"occupied={sorted(occ_dbg)}")
            for dx, dy in zip(session.DIR_DX, session.DIR_DY):
                for dz in (0, -1, 1):
                    t = (sel_unit_a8["x"] + dx, sel_unit_a8["y"] + dy, sel_unit_a8["z"] + dz)
                    ti = client.cmd({"cmd": "tile_info", "x": t[0], "y": t[1], "z": t[2]})
                    floor_id = ti.get("parts", {}).get("floor", {}).get("mapDataID", -1)
                    print(f"[A8 DEBUG] neighbour {t}: occupied={t in occ_dbg} "
                          f"tile_ok={ti.get('ok')} floorMapDataID={floor_id}")
        assert adj_tile is not None, (
            f"A8: no empty floored tile adjacent to the client's selected "
            f"unit {sel_unit_a8['id']} at "
            f"({sel_unit_a8['x']},{sel_unit_a8['y']},{sel_unit_a8['z']}) - "
            "this leg's premise (an open ground neighbour exists) does not "
            "hold on this roll (a RED, never a skip - REV E.48 SS.A.8)")
        walk_a8_0 = event_state(client).get("coopWalkArmEntered")
        seq_a8_0 = event_state(client).get("lastSeqEmitted")

        tile_click(client, adj_tile[0], adj_tile[1], adj_tile[2])
        time.sleep(0.3)

        walk_a8_1 = event_state(client).get("coopWalkArmEntered")
        assert walk_a8_1 is not None and walk_a8_1 > walk_a8_0, (
            f"A8: the move click did not reach the walk arm - "
            f"coopWalkArmEntered {walk_a8_0} -> {walk_a8_1} (the delivery "
            "proof that keeps this leg non-vacuous failed)")
        after_a8 = battle_state(client).get("coopWaitText")
        assert after_a8 == expected_deny and after_a8 != before_a8, (
            f"A8 STOP-IF: off-baton move is not refused with the exact "
            f"rendered STR_COOP_DENY_NOT_YOUR_GO text - before={before_a8!r} "
            f"after={after_a8!r}, expected {expected_deny!r}")
        assert event_state(client).get("lastSeqEmitted") == seq_a8_0, (
            "A8: the refused move minted a real action (lastSeqEmitted "
            f"{seq_a8_0} -> {event_state(client).get('lastSeqEmitted')})")
        print(f"[A8] move REFUSED off-baton at tile {adj_tile}: "
              f"coopWalkArmEntered {walk_a8_0} -> {walk_a8_1} (delivered); "
              f"BEFORE={before_a8!r} -> AFTER={after_a8!r}; lastSeqEmitted "
              f"unchanged ({seq_a8_0})")

        # ----- A9: THE PASS (SPEC 11 (f)) -----
        wait_banner(client, banner_expected_client,
                    "A9 pre-press: a clean banner read before the host's "
                    "real button", timeout=20)
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def baton_at_seat_1():
            return True if (event_state(host).get("coopActiveSeat") == 1
                             and event_state(client).get("coopActiveSeat") == 1) else None
        host.wait_for("A9: the host's END TURN hands the baton to seat 1 on "
                      "both machines (the tally rides the NOT seq-ordered "
                      "battle lane, so the client can lag the host)",
                      baton_at_seat_1, timeout=15)

        for gc, who in ((host, "host"), (client, "client")):
            es = event_state(gc)
            assert es.get("coopActiveSeat") == 1, (
                f"{who}: A9 coopActiveSeat after the pass is not 1: "
                f"{es.get('coopActiveSeat')}")
            tally = es.get("coopEndTurnTally", {})
            assert tally.get("needed") == 1, (
                f"{who}: A9 tally needed after the pass is not 1: {tally}")
            bs = battle_state(gc)
            assert bs.get("turn") == turn0 and bs.get("side") == side0, (
                f"{who}: A9 STOP-IF: a baton PASS advanced turn/side "
                f"({turn0}/{side0} -> {bs.get('turn')}/{bs.get('side')})")
            assert es.get("coopEndTurnPhaseCounter") == counter_a1, (
                f"{who}: A9 STOP-IF: a baton PASS advanced the WV-D46 "
                f"side-phase counter (D-23): {counter_a1} -> "
                f"{es.get('coopEndTurnPhaseCounter')}")
        print(f"[A9] the host's END TURN PASSED the baton to seat 1: "
              f"turn/side unchanged ({turn0}/{side0}); "
              f"coopEndTurnPhaseCounter unchanged ({counter_a1}) - a pass is "
              "NOT a side phase (D-23)")

        # ----- A3 (cont'd, REV E.53 E53.3): post-pass widget parity -----
        lw_post = client.cmd({"cmd": "list_widgets"})
        assert lw_post.get("state") == BATTLESCAPE_STATE, (
            f"A3 post-pass: client left BattlescapeState: {lw_post}")
        widgets_post = lw_post["widgets"]
        assert len(widgets_post) == 87, (
            f"A3 post-pass: surface count changed: {len(widgets_post)}")
        banner_idxs = {wait_row["idx"], endturn_row["idx"]}
        for w in widgets_post:
            if w["idx"] in banner_idxs:
                continue
            before_vis = entry_visibility_by_idx.get(w["idx"])
            assert before_vis == w["visible"], (
                f"A3 post-pass: surface idx={w['idx']} type={w.get('type')} "
                f"changed visibility {before_vis} -> {w['visible']} - only "
                "the two banner surfaces may change (REV E.53 E53.3)")
        print("[A3 cont'd] post-pass parity OK: 87 surfaces, every surface "
              "except the two banner rows kept its entry visibility")

        # ----- A10: THE BANNER FOLLOWS THE BATON (REV E.56 E56.2) -----
        name_for_host = get_coop(host).get("clientName")
        assert name_for_host, (
            "A10: get_coop(host)['clientName'] is empty on the HOST - cannot "
            "build the host's off-baton banner text")
        banner_expected_host = f"It is {name_for_host}'s turn"
        assert host_wait_before_pass != banner_expected_host, (
            f"A10: the host's OWN-go banner already equalled the off-baton "
            f"text before the pass: {host_wait_before_pass!r}")

        wait_banner(host, banner_expected_host,
                    "A10 (REV E.56 E56.2): the host's banner follows the "
                    "baton it just gave up", timeout=20)
        assert banner_of(client) != banner_expected_client, (
            f"A10: the client's banner still equals the off-baton text after "
            f"gaining the baton: {banner_of(client)!r}")
        assert battle_state(host).get("coopOffBatonGray") is True, (
            "A10: host's coopOffBatonGray gate is not True now that it is "
            "off-baton")
        assert battle_state(client).get("coopOffBatonGray") is False, (
            "A10: client's coopOffBatonGray gate is not False now that it is "
            "on-baton")
        print(f"[A10] banner follows the baton: host "
              f"{host_wait_before_pass!r} -> {banner_expected_host!r}; "
              f"client no longer shows {banner_expected_client!r} (now "
              f"{banner_of(client)!r}); coopOffBatonGray host=True/"
              "client=False")

        # ----- A11: GRAY FOLLOWS THE BATON -----
        lw_client_a11 = client.cmd({"cmd": "list_widgets"})
        find_widget(lw_client_a11["widgets"], ICONS_TYPE, *ICONS_RECT,
                    "A11 _icons (client, on-baton)")
        rc11 = client.cmd({"cmd": "screen_pixels", "x": ICONS_RECT[0], "y": ICONS_RECT[1],
                            "w": ICONS_RECT[2], "h": ICONS_RECT[3]})
        assert rc11.get("ok") and rc11.get("mode") == "off", (
            f"A11: client on-baton screen_pixels mode is "
            f"{rc11.get('mode')!r}, expected 'off'")
        outside_c11 = sum(1 for p in rc11["pixels"] if not (0 <= p <= 15))
        assert outside_c11 > 0, (
            "A11: client on-baton gray rect has 0 indices outside 0..15 - "
            "the non-vacuity control failed")

        lw_host_a11 = host.cmd({"cmd": "list_widgets"})
        find_widget(lw_host_a11["widgets"], ICONS_TYPE, *ICONS_RECT,
                    "A11 _icons (host, off-baton)")
        rh11 = host.cmd({"cmd": "screen_pixels", "x": ICONS_RECT[0], "y": ICONS_RECT[1],
                          "w": ICONS_RECT[2], "h": ICONS_RECT[3]})
        assert rh11.get("ok") and rh11.get("mode") == "lut", (
            f"A11: host off-baton screen_pixels mode is "
            f"{rh11.get('mode')!r}, expected 'lut'")
        outside_h11 = sum(1 for p in rh11["pixels"] if not (0 <= p <= 15))
        assert outside_h11 == 0, (
            f"A11: host off-baton gray rect has {outside_h11} indices "
            "outside 0..15, expected exactly 0")
        print(f"[A11] gray follows the baton: client on-baton mode=off/"
              f"outside={outside_c11}; host off-baton mode=lut/outside=0")

        # ----- A12: NO TAKE-BACK (D-24) -----
        # REPORTED DEVIATION from this leg's literal brief text (see the
        # builder's acceptance report for the full trace): the brief names
        # the `battle_end_turn_ready` TEST LEVER sent FROM THE HOST. Traced
        # at the tip - CoopEndTurn.h:132-134's own architecture note ("The
        # HOST never receives its own broadcast over the wire (2-machine
        # transport) - its own emitTally() path applies the same snapshot
        # directly instead of round-tripping"), `testSendReady()`
        # (connectionTCP.cpp:6368-6382, ships ONLY a wire message, never
        # applies locally), the dispatch comment at :13210-13217
        # ("bt_end_turn_ready... HOST-inbound... Self-guarded (HOST-only
        # effect)"), and `onReadyReceived`'s `!hostSim -> return` guard -
        # this lever called ON THE HOST sends a `bt_end_turn_ready` to the
        # CLIENT, whose `onReadyReceived` self-guards on `!hostSim` and does
        # nothing; NOTHING ever calls `applyReady()`. Confirmed empirically:
        # a first run sending it from the host timed out after 15s with
        # `coopEndTurnTalliesSeen` never moving. This leg instead drives the
        # host's SPENT-SEAT press through the SAME real button every other
        # leg in this file uses (`battle_action end_turn_button`) -
        # `toggleReady()` calls `applyReady()` HOST-LOCALLY when `hostSim`
        # is true (connectionTCP.cpp:6316-6319), a real re-entry into the
        # EXACT `if (seat != g_batonSeat || !ready)` ignore-and-re-emit
        # branch (connectionTCP.cpp:6235-6239) D-24 describes: seat 0 is not
        # the baton holder (seat 1), so the press is ignored and answered
        # regardless of the `ready` value the real button happens to submit
        # - the same observable "no take-back" contract, exercised through a
        # mechanism proven to actually reach `applyReady()`.
        tally_a12_before = event_state(host).get("coopEndTurnTally", {})
        seen_a12_before = event_state(host).get("coopEndTurnTalliesSeen")
        turn_a12_before = battle_state(host)["turn"]
        side_a12_before = battle_state(host)["side"]
        armed_a12_before = battle_state(host).get("coopEndTurnArmed")
        assert armed_a12_before is False, (
            f"A12 premise: host's END TURN button is not un-latched after "
            f"its own pass - a second real press would not exercise the "
            f"ignore branch: {armed_a12_before}")

        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def host_saw_reemit():
            seen = event_state(host).get("coopEndTurnTalliesSeen")
            return True if seen is not None and seen > seen_a12_before else None
        host.wait_for("A12: host saw the re-emitted tally answering its own "
                      "spent-seat press (D-24 no take-back)",
                      host_saw_reemit, timeout=15)

        assert (event_state(host).get("coopActiveSeat") == 1
                and event_state(client).get("coopActiveSeat") == 1), (
            f"A12 STOP-IF: D-24: a spent seat's press changed the baton - "
            f"host={event_state(host).get('coopActiveSeat')} "
            f"client={event_state(client).get('coopActiveSeat')}")
        tally_a12_after = event_state(host).get("coopEndTurnTally", {})
        assert tally_a12_after.get("count") == tally_a12_before.get("count"), (
            f"A12: D-24: the spent seat's press changed the tally count: "
            f"{tally_a12_before} -> {tally_a12_after}")
        assert (battle_state(host)["turn"] == turn_a12_before
                and battle_state(host)["side"] == side_a12_before), (
            "A12: D-24: the spent seat's press advanced turn/side")
        assert battle_state(host).get("coopEndTurnArmed") is False, (
            "A12: D-24: the spent seat's ignored press latched its own "
            f"button anyway: {battle_state(host).get('coopEndTurnArmed')}")
        print(f"[A12] no take-back (D-24): host's spent-seat press changed "
              f"nothing (activeSeat still 1, tally count "
              f"{tally_a12_before.get('count')} unchanged, button stays "
              f"un-latched) and was ANSWERED (talliesSeen {seen_a12_before} "
              f"-> {event_state(host).get('coopEndTurnTalliesSeen')})")

        # ----- A13: THE LAST PASS CLOSES THE SIDE -----
        seen_a13_h = event_state(host).get("coopEndTurnTalliesSeen")
        seen_a13_c = event_state(client).get("coopEndTurnTalliesSeen")
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        drive_full_cycle(host, client, turn0, timeout=60)
        session.wait_host_idle(host, client, timeout=30)

        counter_a13_h = event_state(host).get("coopEndTurnPhaseCounter")
        counter_a13_c = event_state(client).get("coopEndTurnPhaseCounter")
        assert counter_a13_h == counter_a1 + 3, (
            f"A13: host's side-phase counter did not advance by exactly 3: "
            f"{counter_a1} -> {counter_a13_h}")
        assert counter_a13_c == counter_a1 + 3, (
            f"A13: client's side-phase counter did not advance by exactly 3: "
            f"{counter_a1} -> {counter_a13_c}")
        assert battle_state(host)["turn"] == turn0 + 1 and battle_state(host)["side"] == side0, (
            f"A13: host did not land at turn0+1/side0: turn0={turn0} -> "
            f"{battle_state(host)['turn']}, side={battle_state(host)['side']}")
        assert battle_state(client)["turn"] == turn0 + 1 and battle_state(client)["side"] == side0, (
            f"A13: client did not land at turn0+1/side0: turn0={turn0} -> "
            f"{battle_state(client)['turn']}, side={battle_state(client)['side']}")

        # REV E.57 (D78 = (a)): the entry tally for the NEW player side rides
        # the battle lane, which is explicitly NOT the seq-ordered apply queue
        # (SPIKE-RUNBOOK.md SS2.3 / WR-4), so it can arrive before this machine
        # has applied its own side_transition. E57.1 BUFFERS such a tally and
        # honours it when onClientAppliedSideTransition() advances the counter
        # to it. So wait on the COUNTERS - talliesSeen advanced, the applied
        # side-phase counter at its final value, and the last applied tally's
        # own turn equal to that counter, on BOTH machines - and only then
        # assert the honoured value, HARD. The wait is on monotone counters,
        # never on the value under test.
        def tally_settled():
            for m, seen0 in ((host, seen_a13_h), (client, seen_a13_c)):
                es = event_state(m)
                if es.get("coopEndTurnTalliesSeen") <= seen0:
                    return None
                if es.get("coopEndTurnPhaseCounter") != counter_a1 + 3:
                    return None
                if es.get("coopEndTurnTally", {}).get("turn") != es.get("coopEndTurnPhaseCounter"):
                    return None
            return True
        try:
            client.wait_for("A13: the new player side's tally is APPLIED on "
                            "both machines (talliesSeen advanced, side-phase "
                            "counter final, tally turn == counter)",
                            tally_settled, timeout=15)
        except TimeoutError:
            print(f"[A13 DEBUG] host event_state={event_state(host)}")
            print(f"[A13 DEBUG] client event_state={event_state(client)}")
            raise

        es_a13_h = event_state(host)
        es_a13_c = event_state(client)
        assert es_a13_h.get("coopActiveSeat") == es_a13_c.get("coopActiveSeat") == 0, (
            f"A13 (REV E.57 / D78): the new player side's HONOURED baton is not "
            f"seat 0 on BOTH machines - host={es_a13_h.get('coopActiveSeat')} "
            f"client={es_a13_c.get('coopActiveSeat')}; "
            f"host counter={es_a13_h.get('coopEndTurnPhaseCounter')} "
            f"talliesSeen={es_a13_h.get('coopEndTurnTalliesSeen')} "
            f"pending={es_a13_h.get('coopPendingTallyTurn')} "
            f"tally={es_a13_h.get('coopEndTurnTally')}; "
            f"client counter={es_a13_c.get('coopEndTurnPhaseCounter')} "
            f"talliesSeen={es_a13_c.get('coopEndTurnTalliesSeen')} "
            f"pending={es_a13_c.get('coopPendingTallyTurn')} "
            f"tally={es_a13_c.get('coopEndTurnTally')}")
        assert es_a13_h.get("coopPendingTallyTurn") == -1, (
            f"A13 (REV E.57 E57.2): the HOST has a buffered tally, which it can "
            f"never have - emitTally() applies its own tally with g_turn itself: "
            f"coopPendingTallyTurn={es_a13_h.get('coopPendingTallyTurn')}, "
            f"counter={es_a13_h.get('coopEndTurnPhaseCounter')}")
        assert es_a13_c.get("coopPendingTallyTurn") == -1, (
            f"A13 (REV E.57 E57.2): the client's pending tally was not cleared "
            f"once the matching side_transition applied: "
            f"coopPendingTallyTurn={es_a13_c.get('coopPendingTallyTurn')}, "
            f"counter={es_a13_c.get('coopEndTurnPhaseCounter')}")
        print(f"[A13] the client's END TURN - the LAST pass - CLOSED the "
              f"side: turn {turn0} -> {turn0 + 1}, side back to {side0}, "
              f"coopEndTurnPhaseCounter +3 on both ({counter_a1} -> "
              f"{counter_a13_h}); the new player side's baton is EQUAL on both "
              f"machines - host coopActiveSeat="
              f"{es_a13_h.get('coopActiveSeat')} / client coopActiveSeat="
              f"{es_a13_c.get('coopActiveSeat')} - and coopPendingTallyTurn is "
              f"-1 on both (the buffer is empty after the matching apply)")

        # ----- A14: KEPT SURFACES + HASH -----
        # Vanilla pushes a NextTurnState on BOTH machines at the start of the
        # new player turn, and drive_full_cycle() returns on the turn/side
        # condition that popup accompanies, so the LAST one of the cycle is
        # still standing here. list_widgets reports only the TOP state's
        # surfaces (TestServer.cpp: `_game->getStates().back()`), so the map
        # and the rest of the BattlescapeState are one level below it. Close
        # it through the same REAL NextTurnState::close() path the driver uses
        # - this file's own dismiss_next_turn_if_present() - on BOTH machines,
        # then read. Nothing about the assertions below changes; this only
        # puts the read on the state they are about.
        dismiss_next_turn_if_present(host)
        dismiss_next_turn_if_present(client)
        for _m in (host, client):
            _m.wait_for("A14: the turn-start NextTurnState is closed",
                        lambda m=_m: True if BATTLESCAPE_STATE in
                        m.cmd({"cmd": "list_widgets"}).get("state", "") else None,
                        timeout=10)
        lw_final = client.cmd({"cmd": "list_widgets"})
        assert any(w.get("type") == MAP_TYPE for w in lw_final["widgets"]), (
            "A14: the map surface is not present in list_widgets after the "
            "cycle")
        es_final = event_state(client)
        assert es_final.get("ghostEnqueued") is not None, (
            "A14: ghostEnqueued is not readable after the cycle")
        assert es_final.get("ghostQueueDepth") is not None, (
            "A14: ghostQueueDepth is not readable after the cycle")
        assert battle_state(client).get("chatMenuExists") is True, (
            "A14: chatMenuExists is not True after the cycle")
        assert_hash_clean(host, client, full=True, what="A14 after A13")
        print("[A14] kept surfaces confirmed (map, ghost counters, chat) and "
              "all buckets EQUAL after A13")

        print("PASS: test_rw_turn_baton BOOT A (traditional, two seats)")
    finally:
        host.shutdown()
        client.shutdown()


def run_boot_b():
    """BOOT B - client UNSEATED (seat_client=False), traditional (REV E.48
    D.3 / SPEC 11 (f)'s "a seat with no live units is SKIPPED"). The
    unseated client is a CONNECTED seat with ZERO live commandable units, so
    D-23's skip rule must never hand it the baton: coopActiveSeat == 0 at
    entry and NEVER 1, checked after entry, after the host's press, and
    after the full cycle. The host's SINGLE press therefore CLOSES the side
    directly - there is no second live seat to pass to."""
    port = "48271"
    host_dir = make_user_dir("test_rw_turn_baton_b_host")
    client_dir = make_user_dir("test_rw_turn_baton_b_client")
    host = GameClient("host", 49672, host_dir)
    client = GameClient("client", 49673, client_dir)
    seated = {}
    try:
        bring_up_lobby(host, client, port)
        session.drive_to_battlescape(host, client, seated, mission=MISSION,
                                      pre_ok=pre_ok_traditional, seat_client=False)

        assert live_mode(host) == TRADITIONAL and live_mode(client) == TRADITIONAL, (
            f"boot B fixture: expected both machines' live battle mode to be "
            f"{TRADITIONAL!r}: host={live_mode(host)!r} client={live_mode(client)!r}")

        pinned = pin_ai_neutral(host, client, tag="turn_baton-b")
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
        side0 = hs0["side"]

        for gc, who in ((host, "host"), (client, "client")):
            assert event_state(gc).get("coopActiveSeat") == 0, (
                f"{who}: boot B entry coopActiveSeat is not 0: "
                f"{event_state(gc).get('coopActiveSeat')}")

        counter_before = event_state(host).get("coopEndTurnPhaseCounter")
        print(f"[boot B] entry: coopActiveSeat==0 on both machines "
              f"(counter={counter_before})")

        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        for gc, who in ((host, "host"), (client, "client")):
            assert event_state(gc).get("coopActiveSeat") != 1, (
                f"{who}: boot B: coopActiveSeat is 1 right after the host's "
                "single press - the unseated client was handed the baton "
                "(D-23's skip rule failed)")

        drive_full_cycle(host, client, turn0, timeout=60)
        session.wait_host_idle(host, client, timeout=30)

        counter_after = event_state(host).get("coopEndTurnPhaseCounter")
        assert counter_after == counter_before + 3, (
            f"boot B: side-phase counter did not advance by exactly 3: "
            f"{counter_before} -> {counter_after}")
        assert battle_state(host)["turn"] == turn0 + 1 and battle_state(host)["side"] == side0, (
            f"boot B: host did not land at turn0+1/side0: {turn0} -> "
            f"{battle_state(host)['turn']}, side={battle_state(host)['side']}")
        assert battle_state(client)["turn"] == turn0 + 1 and battle_state(client)["side"] == side0, (
            f"boot B: client did not land at turn0+1/side0: {turn0} -> "
            f"{battle_state(client)['turn']}, side={battle_state(client)['side']}")

        # The new-side entry tally rides the battle lane, which is NOT
        # seq-ordered (SPIKE-RUNBOOK.md SS2.1) - wait for both machines to
        # converge rather than reading a race right after wait_host_idle's
        # (seq-only) catch-up.
        def baton_back_at_seat_0():
            return True if (event_state(host).get("coopActiveSeat") == 0
                             and event_state(client).get("coopActiveSeat") == 0) else None
        client.wait_for("boot B: the new player side's baton resolves to "
                        "seat 0 on both machines", baton_back_at_seat_0, timeout=15)

        assert_hash_clean(host, client, full=True, what="boot B post-cycle")
        print(f"[boot B] the host's SINGLE press CLOSED the side: turn "
              f"{turn0} -> {turn0 + 1}, counter +3 ({counter_before} -> "
              f"{counter_after}); coopActiveSeat NEVER 1 (entry, "
              "post-press, post-cycle all checked); back to seat 0")

        print("PASS: test_rw_turn_baton BOOT B (spectator, client unseated)")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    run_boot_a()
    run_boot_b()
    print("ALL SPEC 11 test_rw_turn_baton TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("test_rw_turn_baton", e.tracking, str(e))
        print(f"\ntest_rw_turn_baton: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(2)
    except AssertionError as e:
        print(f"\ntest_rw_turn_baton: FAIL\nAssertionError: {e}")
        sys.exit(2)
    except TimeoutError as e:
        print(f"\ntest_rw_turn_baton: FAIL\nTimeoutError: {e}")
        sys.exit(2)
