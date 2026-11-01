"""test_turn_baton.py: the TRADITIONAL baton, the off-baton gray bottom bar and the persistent off-turn banner.

AI-NEUTRAL PINNING: imports the SAME `session.pin_ai_neutral()` helper every boundary-crossing test uses rather than
re-implementing it. Both boots pin mission STR_SMALL_SCOUT (no civilians, no terror units, exactly one alien on every
seed) and `set_seed 1`.

TRADITIONAL MODE, TWO SEATS, ONE SIDE. The HOST sets `CoopTurnMode` to `traditional` before the offer; the CLIENT's
own option is left at its default (parallel), so `live_mode(host) == live_mode(client) == "traditional"` is a genuine
wire-mirror proof (the same non-vacuity shape `test_turn_mode.test_wire_traditional` already uses), not a locally-set
coincidence.

THE TWO-SEAT BOOT (two seated seats, seat_count=2): host seat 0 holds the baton first (host first, then join order by
seat index). The off-baton client sees the WHOLE battlescape exactly as the on-baton machine does (NOTHING is hidden),
with two differences: the bottom `_icons` bar is rendered through a gray lookup, and a persistent `STR_COOP_WAIT_TURN`
banner names the baton holder. Every action that changes the shared battle (move, kneel, turn, END TURN) is refused
with the rendered `STR_COOP_DENY_NOT_YOUR_GO` text; opening the hand-item ACTION MENU is ALLOWED off-turn (so a player
can budget TU while waiting) and mints/paints nothing. The host's END TURN PASSES the baton to seat 1 without touching
the side-phase counter (a pass is not a side phase); a `ready:false` from the spent seat changes nothing and is
answered with the current tally (no take-back); the client's END TURN - the LAST pass - closes the side through the
SAME chokepoint parallel mode uses.

Without the off-baton refusal, a real CLIENT press of the kneel button during the HOST's go SUCCEEDS (measured:
`kneeled=True`, `coopLocalExecBlocked` 0->0, `lastSeqEmitted` 0->0, banner `''`); kneel_refused checks the refusal.

THE SPECTATOR BOOT (client UNSEATED via `seat_client=False`): a CONNECTED seat with no live commandable unit is NOT a
live seat and is never handed the baton, so `coopActiveSeat` reads 0 at entry and NEVER 1 at any point in the boot;
the host's SINGLE press therefore closes the side directly (a seat with no live units is SKIPPED).

Widgets are identified by TYPE + RECT through the EXISTING `list_widgets` probe. A row that matches zero or several
surfaces is a failure naming the row, never a fallback to index.

Run:  python tools/coop_test/test_turn_baton.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean, FACTION_PLAYER
from test_turn_mode import set_mode, live_mode, TRADITIONAL, PARALLEL
from test_input_gating import units_by_id, tile_click
from test_feedback import banner_of, wait_banner

COOP_SEAT_0 = 0
COOP_SEAT_1 = 1
MISSION = "STR_SMALL_SCOUT"

BATTLESCAPE_STATE = "class OpenXcom::BattlescapeState"
ACTION_MENU_STATE = "class OpenXcom::ActionMenuState"
ICONS_TYPE = "class OpenXcom::InteractiveSurface"
TEXT_TYPE = "class OpenXcom::Text"
MAP_TYPE = "class OpenXcom::Map"

# (x, y, w, h) - measured values.
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
# test_end_turn_tally.py precedent - every coop test in this tree carries
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
    before `newbattle_ok`, well before the offer send at the post-briefing
    `click_widget match=ok` step) - the one place every boot of this test
    sets CoopTurnMode=traditional on the HOST before the offer, together with
    the pinned seed every boundary-crossing test uses."""
    set_mode(h, TRADITIONAL)
    h.ok({"cmd": "set_seed", "seed": 1})


def dismiss_next_turn_if_present(gc):
    """test_end_turn_tally.py's own helper, copied: if `gc`'s TOP state is
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
    """test_end_turn_tally.py's own driver, copied: presses nothing itself
    (the caller already pressed the closing END TURN) - polls both machines
    to completion, dismissing any NextTurnState via close_nextturn on BOTH
    machines. Raises TimeoutError if the full cycle never completes on both
    machines."""
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
        f"test_turn_baton: full cycle did not complete within {timeout}s - "
        f"host={battle_state(host)} client={battle_state(client)}")


def find_widget(widgets, type_name, x, y, width, height, label):
    """Identify a widget by TYPE + RECT through the EXISTING list_widgets
    probe. A zero or several match is a failure naming the row, never a
    fallback to index."""
    matches = [row for row in widgets
               if row.get("type") == type_name and row.get("x") == x
               and row.get("y") == y and row.get("w") == width and row.get("h") == height]
    assert len(matches) == 1, (
        f"{label}: expected exactly one {type_name!r} surface at "
        f"{width}x{height}@({x},{y}), found {len(matches)} (zero or several "
        f"is a failure naming the row): {matches}")
    return matches[0]


def find_adjacent_empty_tile(gc, unit):
    """The FIRST of the 8 immediate (x,y) neighbours of `unit`'s tile,
    tried at its OWN level first and then one level down/up (a ramp inside a
    craft interior can put the walkable floor at z+-1 for the SAME (x,y)
    offset), that is floored and unoccupied - the move-refusal leg needs
    exactly one ordinary ground tile adjacent to the currently selected
    unit, not a specific one. A deterministic single scan of the 8x3 static
    candidates, never a loop that re-tries a click."""
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
    verify the rect) - test_input_gating.py's click_button() precedent,
    kept local because that helper discards the response this file needs."""
    r = gc.ok({"cmd": "click_widget", "nth": nth, "button": button})
    time.sleep(0.3)
    return r


def run_two_seat_boot():
    """The two-seat boot, traditional. Legs run in EXACTLY this order - the
    deny banner has a 6000 ms Terminal dwell (kCoopBannerDwellMs,
    CoopBattleUi.h:399) - running them in any other order makes an
    "unchanged"/"changed" comparison vacuous:
      entry_tally            entry tally
      banner_before_pass     banner BEFORE the pass
      nothing_hidden         full list_widgets parity except the two banner
                             surfaces; the post-pass half runs after baton_pass
      gray_bar               gray, whole rect, zero tolerance
      action_menu_allowed    the action menu is ALLOWED off-baton, mints /
                             paints nothing
      kneel_refused          kneel is REFUSED off-baton, BEFORE -> AFTER (the
                             module docstring says what happens without the
                             refusal)
      banner_returns         the banner returns after the deny dwell
      move_refused           a move is REFUSED off-baton, BEFORE -> AFTER
      baton_pass             the host's END TURN passes the baton, does NOT
                             advance the side
      banner_follows_baton   the banner follows the baton
      gray_follows_baton     the gray gate follows the baton
      no_take_back           a spent seat's ready:false changes nothing and is
                             answered
      last_pass_closes_side  the client's END TURN - the LAST pass - closes the
                             side
      kept_surfaces          kept surfaces + hash-clean at entry_tally and
                             after last_pass_closes_side
    """
    port = "48270"
    host_dir = make_user_dir("test_turn_baton_two_seat_host")
    client_dir = make_user_dir("test_turn_baton_two_seat_client")
    host = GameClient("host", 49670, host_dir)
    client = GameClient("client", 49671, client_dir)
    seated = {}
    try:
        bring_up_lobby(host, client, port)
        session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                      pre_ok=pre_ok_traditional)

        assert live_mode(host) == TRADITIONAL and live_mode(client) == TRADITIONAL, (
            f"two-seat boot fixture: expected both machines' live battle mode to be "
            f"{TRADITIONAL!r} (host set it, client mirrors off the wire while "
            f"its OWN option stays {PARALLEL!r}): host={live_mode(host)!r} "
            f"client={live_mode(client)!r}")

        pinned = pin_ai_neutral(host, client, tag="turn_baton-two_seat")
        assert len(pinned) > 0, (
            f"pin_ai_neutral pinned ZERO NONE-seat non-player units on a "
            f"CLASSIC {MISSION} boot - the premise is unexercised")

        hs0 = battle_state(host)
        seat0_units = [u for u in hs0["units"] if u.get("coop") == COOP_SEAT_0
                       and u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
        seat1_units = [u for u in hs0["units"] if u.get("coop") == COOP_SEAT_1
                       and u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
        assert seat0_units, "two-seat boot: seat 0 (host) has no live player unit"
        assert seat1_units, "two-seat boot: seat 1 (client) has no live player unit"

        # ----- entry_tally: ENTRY -----
        for gc, who in ((host, "host"), (client, "client")):
            es = event_state(gc)
            assert es.get("coopActiveSeat") == 0, (
                f"{who}: entry_tally coopActiveSeat is not 0 (first-live-seat "
                f"order, host seat 0 first): {es.get('coopActiveSeat')}")
            tally = es.get("coopEndTurnTally", {})
            assert tally.get("needed") == 1 and tally.get("count") == 0 and tally.get("ready") == [], (
                f"{who}: entry_tally entry tally is not needed=1/count=0/ready=[]: {tally}")
            assert es.get("coopEndTurnPhaseCounter") == 0, (
                f"{who}: entry_tally coopEndTurnPhaseCounter is not 0: "
                f"{es.get('coopEndTurnPhaseCounter')}")
            assert battle_state(gc).get("coopEndTurnText") == "", (
                f"{who}: entry_tally coopEndTurnText is not empty: "
                f"{battle_state(gc).get('coopEndTurnText')!r}")

        turn0 = hs0["turn"]
        side0 = hs0["side"]
        counter_entry = event_state(host).get("coopEndTurnPhaseCounter")
        host_wait_before_pass = battle_state(host).get("coopWaitText")

        assert_hash_clean(host, client, full=True, what="entry_tally entry")
        print(f"[entry_tally] entry tally OK on both machines: coopActiveSeat==0, "
              f"needed=1/count=0/ready=[]/counter=0; turn0={turn0} side0={side0}")

        # ----- banner_before_pass: BANNER BEFORE -----
        name_for_client = get_coop(client).get("clientName")
        assert name_for_client, (
            "banner_before_pass: get_coop(client)['clientName'] is empty on the CLIENT - "
            "cannot build the off-baton banner text")
        banner_expected_client = f"It is {name_for_client}'s turn"

        wait_banner(client, banner_expected_client,
                    "banner_before_pass: client's off-baton banner names "
                    "the baton holder", timeout=20)
        assert banner_of(host) != banner_expected_client, (
            f"banner_before_pass: the HOST's own banner equals the OFF-BATON text while it "
            f"holds the baton: {banner_of(host)!r}")
        assert battle_state(client).get("coopOffBatonGray") is True, (
            "banner_before_pass: client's coopOffBatonGray gate is not True while off-baton")
        assert battle_state(host).get("coopOffBatonGray") is False, (
            "banner_before_pass: host's coopOffBatonGray gate is not False during its own go")
        print(f"[banner_before_pass] off-baton banner OK: client={banner_expected_client!r}, "
              f"host's own banner ({banner_of(host)!r}) is NOT the off-baton "
              "text; coopOffBatonGray client=True/host=False")

        # ----- nothing_hidden: NOTHING HIDDEN -----
        lw_entry = client.cmd({"cmd": "list_widgets"})
        assert lw_entry.get("ok") and lw_entry.get("state") == BATTLESCAPE_STATE, (
            f"nothing_hidden: list_widgets on the client did not report BattlescapeState: "
            f"{lw_entry}")
        widgets_entry = lw_entry["widgets"]
        assert len(widgets_entry) == 87, (
            f"nothing_hidden: expected 87 surfaces on the client's BattlescapeState, got "
            f"{len(widgets_entry)}")

        wait_row = find_widget(widgets_entry, TEXT_TYPE, *WAIT_TEXT_RECT, "nothing_hidden _txtCoopWait")
        endturn_row = find_widget(widgets_entry, TEXT_TYPE, *END_TURN_TEXT_RECT, "nothing_hidden _txtCoopEndTurn")
        assert wait_row["visible"] is True and wait_row.get("text") == banner_expected_client, (
            f"nothing_hidden: _txtCoopWait is not VISIBLE with the off-baton banner text: "
            f"{wait_row}")
        assert endturn_row["visible"] is False, (
            f"nothing_hidden: _txtCoopEndTurn is visible at count==0 (empty text -> "
            f"hidden): {endturn_row}")
        entry_visibility_by_idx = {w["idx"]: w["visible"] for w in widgets_entry}
        print("[nothing_hidden] entry snapshot OK: 87 surfaces; _txtCoopWait VISIBLE with "
              "the banner text; _txtCoopEndTurn hidden (count==0); the "
              "post-pass parity check follows after baton_pass")

        # ----- gray_bar: GRAY, WHOLE RECT -----
        find_widget(widgets_entry, ICONS_TYPE, *ICONS_RECT, "gray_bar _icons (client)")
        rc = client.cmd({"cmd": "screen_pixels", "x": ICONS_RECT[0], "y": ICONS_RECT[1],
                          "w": ICONS_RECT[2], "h": ICONS_RECT[3]})
        assert rc.get("ok"), f"gray_bar: screen_pixels failed on the client: {rc}"
        assert rc.get("mode") == "lut", (
            f"gray_bar: client off-baton screen_pixels mode is {rc.get('mode')!r}, "
            "expected 'lut'")
        outside_c = sum(1 for p in rc["pixels"] if not (0 <= p <= 15))
        assert outside_c == 0, (
            f"gray_bar: client off-baton gray rect has {outside_c} indices outside "
            "0..15, expected exactly 0")

        lw_host_gray = host.cmd({"cmd": "list_widgets"})
        find_widget(lw_host_gray["widgets"], ICONS_TYPE, *ICONS_RECT, "gray_bar _icons (host)")
        rh = host.cmd({"cmd": "screen_pixels", "x": ICONS_RECT[0], "y": ICONS_RECT[1],
                        "w": ICONS_RECT[2], "h": ICONS_RECT[3]})
        assert rh.get("ok"), f"gray_bar: screen_pixels failed on the host: {rh}"
        assert rh.get("mode") == "off", (
            f"gray_bar: host on-baton (own go) screen_pixels mode is "
            f"{rh.get('mode')!r}, expected 'off'")
        outside_h = sum(1 for p in rh["pixels"] if not (0 <= p <= 15))
        assert outside_h > 0, (
            "gray_bar: host on-baton gray rect has 0 indices outside 0..15 - the "
            "non-vacuity control failed")
        print(f"[gray_bar] gray gate OK: client off-baton mode=lut/outside=0 "
              f"(whole {ICONS_RECT[2]}x{ICONS_RECT[3]} rect); host own-go "
              f"mode=off/outside={outside_h}")

        # ----- action_menu_allowed: ACTION MENU -----
        banner_menu0 = battle_state(client).get("coopWaitText")
        blocked_menu0 = event_state(client).get("coopLocalExecBlocked")
        seq_menu0 = event_state(client).get("lastSeqEmitted")

        r_menu = click_nth(client, RHAND_NTH)
        assert (r_menu.get("baseX") == RHAND_RECT[0] + RHAND_RECT[2] // 2
                and r_menu.get("baseY") == RHAND_RECT[1] + RHAND_RECT[3] // 2), (
            f"action_menu_allowed: click_widget nth={RHAND_NTH} did not land on the right-hand "
            f"box centre of {RHAND_RECT}: {r_menu}")

        lw_menu = client.cmd({"cmd": "list_widgets"})
        assert lw_menu.get("state") == ACTION_MENU_STATE, (
            f"action_menu_allowed: opening the hand box did not reach ActionMenuState: {lw_menu}")
        visible_rows = [w for w in lw_menu["widgets"]
                        if w.get("visible") and "ActionMenuItem" in w.get("type", "")]
        assert len(visible_rows) >= 1, (
            f"action_menu_allowed: no VISIBLE ActionMenuItem row in the opened menu: {lw_menu}")
        assert event_state(client).get("lastSeqEmitted") == seq_menu0, (
            "action_menu_allowed: opening the action menu minted a real action (lastSeqEmitted "
            f"changed: {seq_menu0} -> {event_state(client).get('lastSeqEmitted')})")
        assert event_state(client).get("coopLocalExecBlocked") == blocked_menu0, (
            "action_menu_allowed: opening the action menu was REFUSED (coopLocalExecBlocked "
            f"moved: {blocked_menu0} -> "
            f"{event_state(client).get('coopLocalExecBlocked')}) - the menu "
            "must be ALLOWED off-baton")
        assert battle_state(client).get("coopWaitText") == banner_menu0, (
            f"action_menu_allowed: opening the action menu changed the banner: {banner_menu0!r} -> "
            f"{battle_state(client).get('coopWaitText')!r}")

        client.ok({"cmd": "inject_input", "kind": "key", "key": 27})
        lw_after_dismiss = client.cmd({"cmd": "list_widgets"})
        assert lw_after_dismiss.get("state") == BATTLESCAPE_STATE, (
            f"action_menu_allowed: dismissing the menu did not return to BattlescapeState: "
            f"{lw_after_dismiss}")
        assert len(lw_after_dismiss["widgets"]) == 87, (
            f"action_menu_allowed: surface count changed after dismissing the menu: "
            f"{len(lw_after_dismiss['widgets'])}")
        assert battle_state(client).get("coopWaitText") == banner_menu0, (
            f"action_menu_allowed: the banner changed across dismiss: {banner_menu0!r} -> "
            f"{battle_state(client).get('coopWaitText')!r}")
        print(f"[action_menu_allowed] action menu ALLOWED off-baton: opened ActionMenuState "
              f"({len(visible_rows)} visible row(s)), minted nothing "
              f"(lastSeqEmitted=={seq_menu0}, coopLocalExecBlocked=="
              f"{blocked_menu0}), banner unchanged ({banner_menu0!r}); dismissed "
              "back to BattlescapeState (87 surfaces)")

        # ----- kneel_refused: KNEEL REFUSAL -----
        banner_kneel0 = battle_state(client).get("coopWaitText")
        blocked_kneel0 = event_state(client).get("coopLocalExecBlocked")
        seq_kneel0 = event_state(client).get("lastSeqEmitted")
        cbs_kneel = battle_state(client)
        sel_id_kneel = cbs_kneel.get("selectedId")
        sel_unit_c_before = units_by_id(cbs_kneel).get(sel_id_kneel)
        sel_unit_h_before = units_by_id(battle_state(host)).get(sel_id_kneel)
        assert sel_unit_c_before is not None and sel_unit_h_before is not None, (
            f"kneel_refused: client's selectedId {sel_id_kneel} has no matching unit on "
            "both machines")
        kneeled_before_c = sel_unit_c_before["kneeled"]
        kneeled_before_h = sel_unit_h_before["kneeled"]

        r_kneel = click_nth(client, KNEEL_NTH)
        assert (r_kneel.get("baseX") == KNEEL_RECT[0] + KNEEL_RECT[2] // 2
                and r_kneel.get("baseY") == KNEEL_RECT[1] + KNEEL_RECT[3] // 2), (
            f"kneel_refused: click_widget nth={KNEEL_NTH} did not land on the kneel "
            f"button centre of {KNEEL_RECT}: {r_kneel}")

        expected_deny = f"Not your turn - waiting for {name_for_client}"
        banner_kneel1 = battle_state(client).get("coopWaitText")
        assert banner_kneel1 == expected_deny and banner_kneel1 != banner_kneel0, (
            f"kneel_refused: kneel press is not refused with the exact rendered "
            f"STR_COOP_DENY_NOT_YOUR_GO text - before={banner_kneel0!r} "
            f"after={banner_kneel1!r}, expected {expected_deny!r}")
        assert event_state(client).get("coopLocalExecBlocked") == blocked_kneel0 + 1, (
            f"kneel_refused: coopLocalExecBlocked did not rise by exactly 1: "
            f"{blocked_kneel0} -> {event_state(client).get('coopLocalExecBlocked')}")
        assert event_state(client).get("lastSeqEmitted") == seq_kneel0, (
            "kneel_refused: the refused kneel minted a real action (lastSeqEmitted "
            f"{seq_kneel0} -> {event_state(client).get('lastSeqEmitted')})")
        kneeled_after_c = units_by_id(battle_state(client)).get(sel_id_kneel)["kneeled"]
        kneeled_after_h = units_by_id(battle_state(host)).get(sel_id_kneel)["kneeled"]
        assert kneeled_after_c == kneeled_before_c and kneeled_after_h == kneeled_before_h, (
            f"kneel_refused: the refused kneel changed the unit's kneeled state - client "
            f"{kneeled_before_c}->{kneeled_after_c}, host "
            f"{kneeled_before_h}->{kneeled_after_h}")
        print(f"[kneel_refused] kneel REFUSED off-baton: BEFORE={banner_kneel0!r} -> "
              f"AFTER={banner_kneel1!r}; coopLocalExecBlocked {blocked_kneel0} -> "
              f"{blocked_kneel0 + 1}; lastSeqEmitted unchanged ({seq_kneel0}); "
              f"kneeled unchanged on both machines ({kneeled_before_c})")

        # ----- banner_returns: BANNER RETURNS -----
        wait_banner(client, banner_expected_client,
                    "banner_returns: banner returns after the kneel deny's 6s Terminal "
                    "dwell", timeout=20)
        print(f"[banner_returns] banner returned to {banner_expected_client!r} after the "
              "deny dwell")

        # ----- move_refused: MOVE REFUSAL -----
        banner_move0 = battle_state(client).get("coopWaitText")
        cbs_move = battle_state(client)
        sel_unit_move = units_by_id(cbs_move).get(cbs_move.get("selectedId"))
        assert sel_unit_move is not None, (
            f"move_refused: client's selectedId {cbs_move.get('selectedId')} has no "
            "matching unit")
        adj_tile = find_adjacent_empty_tile(client, sel_unit_move)
        if adj_tile is None:
            st_dbg = battle_state(client)
            occ_dbg = {(u["x"], u["y"], u["z"]) for u in st_dbg.get("units", []) if not u.get("isOut")}
            print(f"[move_refused DEBUG] unit {sel_unit_move['id']} at "
                  f"({sel_unit_move['x']},{sel_unit_move['y']},{sel_unit_move['z']}); "
                  f"occupied={sorted(occ_dbg)}")
            for dx, dy in zip(session.DIR_DX, session.DIR_DY):
                for dz in (0, -1, 1):
                    t = (sel_unit_move["x"] + dx, sel_unit_move["y"] + dy, sel_unit_move["z"] + dz)
                    ti = client.cmd({"cmd": "tile_info", "x": t[0], "y": t[1], "z": t[2]})
                    floor_id = ti.get("parts", {}).get("floor", {}).get("mapDataID", -1)
                    print(f"[move_refused DEBUG] neighbour {t}: occupied={t in occ_dbg} "
                          f"tile_ok={ti.get('ok')} floorMapDataID={floor_id}")
        assert adj_tile is not None, (
            f"move_refused: no empty floored tile adjacent to the client's selected "
            f"unit {sel_unit_move['id']} at "
            f"({sel_unit_move['x']},{sel_unit_move['y']},{sel_unit_move['z']}) - "
            "this leg's premise (an open ground neighbour exists) does not "
            "hold on this roll (a failure, never a skip)")
        walk_move0 = event_state(client).get("coopWalkArmEntered")
        seq_move0 = event_state(client).get("lastSeqEmitted")

        tile_click(client, adj_tile[0], adj_tile[1], adj_tile[2])
        time.sleep(0.3)

        walk_move1 = event_state(client).get("coopWalkArmEntered")
        assert walk_move1 is not None and walk_move1 > walk_move0, (
            f"move_refused: the move click did not reach the walk arm - "
            f"coopWalkArmEntered {walk_move0} -> {walk_move1} (the delivery "
            "proof that keeps this leg non-vacuous failed)")
        banner_move1 = battle_state(client).get("coopWaitText")
        assert banner_move1 == expected_deny and banner_move1 != banner_move0, (
            f"move_refused: off-baton move is not refused with the exact "
            f"rendered STR_COOP_DENY_NOT_YOUR_GO text - before={banner_move0!r} "
            f"after={banner_move1!r}, expected {expected_deny!r}")
        assert event_state(client).get("lastSeqEmitted") == seq_move0, (
            "move_refused: the refused move minted a real action (lastSeqEmitted "
            f"{seq_move0} -> {event_state(client).get('lastSeqEmitted')})")
        print(f"[move_refused] move REFUSED off-baton at tile {adj_tile}: "
              f"coopWalkArmEntered {walk_move0} -> {walk_move1} (delivered); "
              f"BEFORE={banner_move0!r} -> AFTER={banner_move1!r}; lastSeqEmitted "
              f"unchanged ({seq_move0})")

        # ----- baton_pass: THE PASS -----
        wait_banner(client, banner_expected_client,
                    "baton_pass pre-press: a clean banner read before the host's "
                    "real button", timeout=20)
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def baton_at_seat_1():
            return True if (event_state(host).get("coopActiveSeat") == 1
                             and event_state(client).get("coopActiveSeat") == 1) else None
        host.wait_for("baton_pass: the host's END TURN hands the baton to seat 1 on "
                      "both machines (the tally rides the NOT seq-ordered "
                      "battle lane, so the client can lag the host)",
                      baton_at_seat_1, timeout=15)

        for gc, who in ((host, "host"), (client, "client")):
            es = event_state(gc)
            assert es.get("coopActiveSeat") == 1, (
                f"{who}: baton_pass coopActiveSeat after the pass is not 1: "
                f"{es.get('coopActiveSeat')}")
            tally = es.get("coopEndTurnTally", {})
            assert tally.get("needed") == 1, (
                f"{who}: baton_pass tally needed after the pass is not 1: {tally}")
            bs = battle_state(gc)
            assert bs.get("turn") == turn0 and bs.get("side") == side0, (
                f"{who}: baton_pass: a baton PASS advanced turn/side "
                f"({turn0}/{side0} -> {bs.get('turn')}/{bs.get('side')})")
            assert es.get("coopEndTurnPhaseCounter") == counter_entry, (
                f"{who}: baton_pass: a baton PASS advanced the "
                f"side-phase counter (a pass is not a side phase): {counter_entry} -> "
                f"{es.get('coopEndTurnPhaseCounter')}")
        print(f"[baton_pass] the host's END TURN PASSED the baton to seat 1: "
              f"turn/side unchanged ({turn0}/{side0}); "
              f"coopEndTurnPhaseCounter unchanged ({counter_entry}) - a pass is "
              "NOT a side phase")

        # ----- nothing_hidden (cont'd): post-pass widget parity -----
        lw_post = client.cmd({"cmd": "list_widgets"})
        assert lw_post.get("state") == BATTLESCAPE_STATE, (
            f"nothing_hidden post-pass: client left BattlescapeState: {lw_post}")
        widgets_post = lw_post["widgets"]
        assert len(widgets_post) == 87, (
            f"nothing_hidden post-pass: surface count changed: {len(widgets_post)}")
        banner_idxs = {wait_row["idx"], endturn_row["idx"]}
        for w in widgets_post:
            if w["idx"] in banner_idxs:
                continue
            before_vis = entry_visibility_by_idx.get(w["idx"])
            assert before_vis == w["visible"], (
                f"nothing_hidden post-pass: surface idx={w['idx']} type={w.get('type')} "
                f"changed visibility {before_vis} -> {w['visible']} - only "
                "the two banner surfaces may change")
        print("[nothing_hidden cont'd] post-pass parity OK: 87 surfaces, every surface "
              "except the two banner rows kept its entry visibility")

        # ----- banner_follows_baton: THE BANNER FOLLOWS THE BATON -----
        name_for_host = get_coop(host).get("clientName")
        assert name_for_host, (
            "banner_follows_baton: get_coop(host)['clientName'] is empty on the HOST - cannot "
            "build the host's off-baton banner text")
        banner_expected_host = f"It is {name_for_host}'s turn"
        assert host_wait_before_pass != banner_expected_host, (
            f"banner_follows_baton: the host's OWN-go banner already equalled the off-baton "
            f"text before the pass: {host_wait_before_pass!r}")

        wait_banner(host, banner_expected_host,
                    "banner_follows_baton: the host's banner follows the "
                    "baton it just gave up", timeout=20)
        assert banner_of(client) != banner_expected_client, (
            f"banner_follows_baton: the client's banner still equals the off-baton text after "
            f"gaining the baton: {banner_of(client)!r}")
        assert battle_state(host).get("coopOffBatonGray") is True, (
            "banner_follows_baton: host's coopOffBatonGray gate is not True now that it is "
            "off-baton")
        assert battle_state(client).get("coopOffBatonGray") is False, (
            "banner_follows_baton: client's coopOffBatonGray gate is not False now that it is "
            "on-baton")
        print(f"[banner_follows_baton] banner follows the baton: host "
              f"{host_wait_before_pass!r} -> {banner_expected_host!r}; "
              f"client no longer shows {banner_expected_client!r} (now "
              f"{banner_of(client)!r}); coopOffBatonGray host=True/"
              "client=False")

        # ----- gray_follows_baton: GRAY FOLLOWS THE BATON -----
        lw_client_gray_after = client.cmd({"cmd": "list_widgets"})
        find_widget(lw_client_gray_after["widgets"], ICONS_TYPE, *ICONS_RECT,
                    "gray_follows_baton _icons (client, on-baton)")
        rc_after = client.cmd({"cmd": "screen_pixels", "x": ICONS_RECT[0], "y": ICONS_RECT[1],
                            "w": ICONS_RECT[2], "h": ICONS_RECT[3]})
        assert rc_after.get("ok") and rc_after.get("mode") == "off", (
            f"gray_follows_baton: client on-baton screen_pixels mode is "
            f"{rc_after.get('mode')!r}, expected 'off'")
        outside_c_after = sum(1 for p in rc_after["pixels"] if not (0 <= p <= 15))
        assert outside_c_after > 0, (
            "gray_follows_baton: client on-baton gray rect has 0 indices outside 0..15 - "
            "the non-vacuity control failed")

        lw_host_gray_after = host.cmd({"cmd": "list_widgets"})
        find_widget(lw_host_gray_after["widgets"], ICONS_TYPE, *ICONS_RECT,
                    "gray_follows_baton _icons (host, off-baton)")
        rh_after = host.cmd({"cmd": "screen_pixels", "x": ICONS_RECT[0], "y": ICONS_RECT[1],
                          "w": ICONS_RECT[2], "h": ICONS_RECT[3]})
        assert rh_after.get("ok") and rh_after.get("mode") == "lut", (
            f"gray_follows_baton: host off-baton screen_pixels mode is "
            f"{rh_after.get('mode')!r}, expected 'lut'")
        outside_h_after = sum(1 for p in rh_after["pixels"] if not (0 <= p <= 15))
        assert outside_h_after == 0, (
            f"gray_follows_baton: host off-baton gray rect has {outside_h_after} indices "
            "outside 0..15, expected exactly 0")
        print(f"[gray_follows_baton] gray follows the baton: client on-baton mode=off/"
              f"outside={outside_c_after}; host off-baton mode=lut/outside=0")

        # ----- no_take_back: NO TAKE-BACK -----
        # The `battle_end_turn_ready` test command cannot exercise this when
        # sent FROM THE HOST. CoopEndTurn.h:132-134's own architecture note:
        # "The HOST never receives its own broadcast over the wire (2-machine
        # transport) - its own emitTally() path applies the same snapshot
        # directly instead of round-tripping"; `testSendReady()`
        # (connectionTCP.cpp:6368-6382) ships ONLY a wire message and never
        # applies locally (the dispatch comment at :13210-13217:
        # "bt_end_turn_ready... HOST-inbound... Self-guarded (HOST-only
        # effect)"). So that command called ON THE HOST sends a
        # `bt_end_turn_ready` to the CLIENT, whose `onReadyReceived`
        # self-guards on `!hostSim` and does nothing; NOTHING ever calls
        # `applyReady()` (measured: a run sending it from the host timed out
        # after 15s with `coopEndTurnTalliesSeen` never moving). This leg
        # instead drives the host's SPENT-SEAT press through the SAME real
        # button every other leg in this file uses (`battle_action
        # end_turn_button`) - `toggleReady()` calls `applyReady()`
        # HOST-LOCALLY when `hostSim` is true (connectionTCP.cpp:6316-6319),
        # a real re-entry into the EXACT `if (seat != g_batonSeat || !ready)`
        # ignore-and-re-emit branch (connectionTCP.cpp:6235-6239): seat 0 is
        # not the baton holder (seat 1), so the press is ignored and answered
        # regardless of the `ready` value the real button happens to submit -
        # the "no take-back" contract, exercised through a path that reaches
        # `applyReady()`.
        tally_spent0 = event_state(host).get("coopEndTurnTally", {})
        seen_spent0 = event_state(host).get("coopEndTurnTalliesSeen")
        turn_spent0 = battle_state(host)["turn"]
        side_spent0 = battle_state(host)["side"]
        armed_spent0 = battle_state(host).get("coopEndTurnArmed")
        assert armed_spent0 is False, (
            f"no_take_back premise: host's END TURN button is not un-latched after "
            f"its own pass - a second real press would not exercise the "
            f"ignore branch: {armed_spent0}")

        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def host_saw_reemit():
            seen = event_state(host).get("coopEndTurnTalliesSeen")
            return True if seen is not None and seen > seen_spent0 else None
        host.wait_for("no_take_back: host saw the re-emitted tally answering its own "
                      "spent-seat press (no take-back)",
                      host_saw_reemit, timeout=15)

        assert (event_state(host).get("coopActiveSeat") == 1
                and event_state(client).get("coopActiveSeat") == 1), (
            f"no_take_back: a spent seat's press changed the baton - "
            f"host={event_state(host).get('coopActiveSeat')} "
            f"client={event_state(client).get('coopActiveSeat')}")
        tally_spent1 = event_state(host).get("coopEndTurnTally", {})
        assert tally_spent1.get("count") == tally_spent0.get("count"), (
            f"no_take_back: the spent seat's press changed the tally count: "
            f"{tally_spent0} -> {tally_spent1}")
        assert (battle_state(host)["turn"] == turn_spent0
                and battle_state(host)["side"] == side_spent0), (
            "no_take_back: the spent seat's press advanced turn/side")
        assert battle_state(host).get("coopEndTurnArmed") is False, (
            "no_take_back: the spent seat's ignored press latched its own "
            f"button anyway: {battle_state(host).get('coopEndTurnArmed')}")
        print(f"[no_take_back] no take-back: host's spent-seat press changed "
              f"nothing (activeSeat still 1, tally count "
              f"{tally_spent0.get('count')} unchanged, button stays "
              f"un-latched) and was ANSWERED (talliesSeen {seen_spent0} "
              f"-> {event_state(host).get('coopEndTurnTalliesSeen')})")

        # ----- last_pass_closes_side: THE LAST PASS CLOSES THE SIDE -----
        seen_last_h = event_state(host).get("coopEndTurnTalliesSeen")
        seen_last_c = event_state(client).get("coopEndTurnTalliesSeen")
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        drive_full_cycle(host, client, turn0, timeout=60)
        session.wait_host_idle(host, client, timeout=30)

        counter_last_h = event_state(host).get("coopEndTurnPhaseCounter")
        counter_last_c = event_state(client).get("coopEndTurnPhaseCounter")
        assert counter_last_h == counter_entry + 3, (
            f"last_pass_closes_side: host's side-phase counter did not advance by exactly 3: "
            f"{counter_entry} -> {counter_last_h}")
        assert counter_last_c == counter_entry + 3, (
            f"last_pass_closes_side: client's side-phase counter did not advance by exactly 3: "
            f"{counter_entry} -> {counter_last_c}")
        assert battle_state(host)["turn"] == turn0 + 1 and battle_state(host)["side"] == side0, (
            f"last_pass_closes_side: host did not land at turn0+1/side0: turn0={turn0} -> "
            f"{battle_state(host)['turn']}, side={battle_state(host)['side']}")
        assert battle_state(client)["turn"] == turn0 + 1 and battle_state(client)["side"] == side0, (
            f"last_pass_closes_side: client did not land at turn0+1/side0: turn0={turn0} -> "
            f"{battle_state(client)['turn']}, side={battle_state(client)['side']}")

        # the entry tally for the NEW player side rides
        # the battle lane, which is explicitly NOT the seq-ordered apply queue,
        # so it can arrive before this machine
        # has applied its own side_transition. The client BUFFERS such a tally and
        # honours it when onClientAppliedSideTransition() advances the counter
        # to it. So wait on the COUNTERS - talliesSeen advanced, the applied
        # side-phase counter at its final value, and the last applied tally's
        # own turn equal to that counter, on BOTH machines - and only then
        # assert the honoured value, HARD. The wait is on monotone counters,
        # never on the value under test.
        def tally_settled():
            for m, seen0 in ((host, seen_last_h), (client, seen_last_c)):
                es = event_state(m)
                if es.get("coopEndTurnTalliesSeen") <= seen0:
                    return None
                if es.get("coopEndTurnPhaseCounter") != counter_entry + 3:
                    return None
                if es.get("coopEndTurnTally", {}).get("turn") != es.get("coopEndTurnPhaseCounter"):
                    return None
            return True
        try:
            client.wait_for("last_pass_closes_side: the new player side's tally is APPLIED on "
                            "both machines (talliesSeen advanced, side-phase "
                            "counter final, tally turn == counter)",
                            tally_settled, timeout=15)
        except TimeoutError:
            print(f"[last_pass_closes_side DEBUG] host event_state={event_state(host)}")
            print(f"[last_pass_closes_side DEBUG] client event_state={event_state(client)}")
            raise

        es_last_h = event_state(host)
        es_last_c = event_state(client)
        assert es_last_h.get("coopActiveSeat") == es_last_c.get("coopActiveSeat") == 0, (
            f"last_pass_closes_side: the new player side's HONOURED baton is not "
            f"seat 0 on BOTH machines - host={es_last_h.get('coopActiveSeat')} "
            f"client={es_last_c.get('coopActiveSeat')}; "
            f"host counter={es_last_h.get('coopEndTurnPhaseCounter')} "
            f"talliesSeen={es_last_h.get('coopEndTurnTalliesSeen')} "
            f"pending={es_last_h.get('coopPendingTallyTurn')} "
            f"tally={es_last_h.get('coopEndTurnTally')}; "
            f"client counter={es_last_c.get('coopEndTurnPhaseCounter')} "
            f"talliesSeen={es_last_c.get('coopEndTurnTalliesSeen')} "
            f"pending={es_last_c.get('coopPendingTallyTurn')} "
            f"tally={es_last_c.get('coopEndTurnTally')}")
        assert es_last_h.get("coopPendingTallyTurn") == -1, (
            f"last_pass_closes_side: the HOST has a buffered tally, which it can "
            f"never have - emitTally() applies its own tally with g_turn itself: "
            f"coopPendingTallyTurn={es_last_h.get('coopPendingTallyTurn')}, "
            f"counter={es_last_h.get('coopEndTurnPhaseCounter')}")
        assert es_last_c.get("coopPendingTallyTurn") == -1, (
            f"last_pass_closes_side: the client's pending tally was not cleared "
            f"once the matching side_transition applied: "
            f"coopPendingTallyTurn={es_last_c.get('coopPendingTallyTurn')}, "
            f"counter={es_last_c.get('coopEndTurnPhaseCounter')}")
        print(f"[last_pass_closes_side] the client's END TURN - the LAST pass - CLOSED the "
              f"side: turn {turn0} -> {turn0 + 1}, side back to {side0}, "
              f"coopEndTurnPhaseCounter +3 on both ({counter_entry} -> "
              f"{counter_last_h}); the new player side's baton is EQUAL on both "
              f"machines - host coopActiveSeat="
              f"{es_last_h.get('coopActiveSeat')} / client coopActiveSeat="
              f"{es_last_c.get('coopActiveSeat')} - and coopPendingTallyTurn is "
              f"-1 on both (the buffer is empty after the matching apply)")

        # ----- kept_surfaces: KEPT SURFACES + HASH -----
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
            _m.wait_for("kept_surfaces: the turn-start NextTurnState is closed",
                        lambda m=_m: True if BATTLESCAPE_STATE in
                        m.cmd({"cmd": "list_widgets"}).get("state", "") else None,
                        timeout=10)
        lw_final = client.cmd({"cmd": "list_widgets"})
        assert any(w.get("type") == MAP_TYPE for w in lw_final["widgets"]), (
            "kept_surfaces: the map surface is not present in list_widgets after the "
            "cycle")
        es_final = event_state(client)
        assert es_final.get("ghostEnqueued") is not None, (
            "kept_surfaces: ghostEnqueued is not readable after the cycle")
        assert es_final.get("ghostQueueDepth") is not None, (
            "kept_surfaces: ghostQueueDepth is not readable after the cycle")
        assert battle_state(client).get("chatMenuExists") is True, (
            "kept_surfaces: chatMenuExists is not True after the cycle")
        assert_hash_clean(host, client, full=True, what="kept_surfaces after last_pass_closes_side")
        print("[kept_surfaces] kept surfaces confirmed (map, ghost counters, chat) and "
              "all buckets EQUAL after last_pass_closes_side")

        print("PASS: test_turn_baton TWO-SEAT BOOT (traditional)")
    finally:
        host.shutdown()
        client.shutdown()


def run_spectator_boot():
    """The spectator boot - client UNSEATED (seat_client=False), traditional:
    a seat with no live units is SKIPPED. The unseated client is a CONNECTED
    seat with ZERO live commandable units, so the skip rule must never hand
    it the baton: coopActiveSeat == 0 at entry and NEVER 1, checked after
    entry, after the host's press, and after the full cycle. The host's
    SINGLE press therefore CLOSES the side directly - there is no second live
    seat to pass to."""
    port = "48271"
    host_dir = make_user_dir("test_turn_baton_spectator_host")
    client_dir = make_user_dir("test_turn_baton_spectator_client")
    host = GameClient("host", 49672, host_dir)
    client = GameClient("client", 49673, client_dir)
    seated = {}
    try:
        bring_up_lobby(host, client, port)
        session.drive_to_battlescape(host, client, seated, mission=MISSION,
                                      pre_ok=pre_ok_traditional, seat_client=False)

        assert live_mode(host) == TRADITIONAL and live_mode(client) == TRADITIONAL, (
            f"spectator boot fixture: expected both machines' live battle mode to be "
            f"{TRADITIONAL!r}: host={live_mode(host)!r} client={live_mode(client)!r}")

        pinned = pin_ai_neutral(host, client, tag="turn_baton-spectator")
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
        side0 = hs0["side"]

        for gc, who in ((host, "host"), (client, "client")):
            assert event_state(gc).get("coopActiveSeat") == 0, (
                f"{who}: spectator boot entry coopActiveSeat is not 0: "
                f"{event_state(gc).get('coopActiveSeat')}")

        counter_before = event_state(host).get("coopEndTurnPhaseCounter")
        print(f"[spectator boot] entry: coopActiveSeat==0 on both machines "
              f"(counter={counter_before})")

        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        for gc, who in ((host, "host"), (client, "client")):
            assert event_state(gc).get("coopActiveSeat") != 1, (
                f"{who}: spectator boot: coopActiveSeat is 1 right after the host's "
                "single press - the unseated client was handed the baton "
                "(the skip rule for a seat with no live units failed)")

        drive_full_cycle(host, client, turn0, timeout=60)
        session.wait_host_idle(host, client, timeout=30)

        counter_after = event_state(host).get("coopEndTurnPhaseCounter")
        assert counter_after == counter_before + 3, (
            f"spectator boot: side-phase counter did not advance by exactly 3: "
            f"{counter_before} -> {counter_after}")
        assert battle_state(host)["turn"] == turn0 + 1 and battle_state(host)["side"] == side0, (
            f"spectator boot: host did not land at turn0+1/side0: {turn0} -> "
            f"{battle_state(host)['turn']}, side={battle_state(host)['side']}")
        assert battle_state(client)["turn"] == turn0 + 1 and battle_state(client)["side"] == side0, (
            f"spectator boot: client did not land at turn0+1/side0: {turn0} -> "
            f"{battle_state(client)['turn']}, side={battle_state(client)['side']}")

        # The new-side entry tally rides the battle lane, which is NOT
        # seq-ordered - wait for both machines to
        # converge rather than reading a race right after wait_host_idle's
        # (seq-only) catch-up.
        def baton_back_at_seat_0():
            return True if (event_state(host).get("coopActiveSeat") == 0
                             and event_state(client).get("coopActiveSeat") == 0) else None
        client.wait_for("spectator boot: the new player side's baton resolves to "
                        "seat 0 on both machines", baton_back_at_seat_0, timeout=15)

        assert_hash_clean(host, client, full=True, what="spectator boot post-cycle")
        print(f"[spectator boot] the host's SINGLE press CLOSED the side: turn "
              f"{turn0} -> {turn0 + 1}, counter +3 ({counter_before} -> "
              f"{counter_after}); coopActiveSeat NEVER 1 (entry, "
              "post-press, post-cycle all checked); back to seat 0")

        print("PASS: test_turn_baton SPECTATOR BOOT (client unseated)")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    run_two_seat_boot()
    run_spectator_boot()
    print("ALL test_turn_baton TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("test_turn_baton", e.tracking, str(e))
        print(f"\ntest_turn_baton: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(2)
    except AssertionError as e:
        print(f"\ntest_turn_baton: FAIL\nAssertionError: {e}")
        sys.exit(2)
    except TimeoutError as e:
        print(f"\ntest_turn_baton: FAIL\nTimeoutError: {e}")
        sys.exit(2)
