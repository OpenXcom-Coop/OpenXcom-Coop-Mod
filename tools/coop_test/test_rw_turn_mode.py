"""W1-P7 deliverable 6 (WAVE1-RUNBOOK.md REV D - owner turn-mode rulings
D-19..D-27, full text WV-D55; schema SS2.W1's `turnMode`): the TURN MODE option
and its TRANSPORT. **The option and its transport only - there is no baton
logic in this packet, that is W1-P13's**, and REV D's rule is binding:
"NOTHING in this packet may branch behaviour on the mode."

That rule is what makes this file's shape unusual and worth reading: because
nothing branches on the mode, behaviour can NEVER prove the plumbing. Every
assertion below is therefore on the CARRIED VALUE - the option, the wire field
and the save key - read back through introspection that reports what each layer
actually holds, never inferred from what the game did.

  PHASE 1  the OPTION (D-20/D-21, WR-25). `Options::CoopTurnMode` is a real
           `Options.inc.h` declaration + `Options.cpp` OptionInfo registration,
           NOT a `connectionTCP` static - so it round-trips through the harness
           lever, defaults to PARALLEL (D-26), normalizes any junk value to
           parallel, and SURVIVES A RESTART via options.cfg (the same instance's
           user folder, re-launched).
  PHASE 2  the WIRE (D-19b / SS2.W1). With the host set TRADITIONAL the
           `battle_offer` carries `turnMode:"traditional"` and the CLIENT
           MIRRORS it - proven with the client's OWN option set to the OPPOSITE
           value, so a mirror that came from the local preference instead of the
           wire would fail. With nothing remembered the offer carries
           "parallel". And with the key REMOVED from the offer entirely (the
           `omit_turn_mode` lever) the client degrades to parallel - D-26's
           backwards-compatible degrade, exercised over the real wire rather
           than by unit-testing the parser.
  PHASE 3  the BATTLE SAVE (D.1, the owner's D-20/D-21 revision). A save taken
           during a live co-op battle carries `coopTurnMode` INSIDE the
           `battleGame:` block; the key is ABSENT from the CAMPAIGN block
           (D-21: the donor's `SavedGame.cpp:1334`/`:1814` shape is NOT ported);
           the REAL D.1 reader gets the same value back off that saved block;
           the reader is WIRED into `SavedBattleGame::load`; and `hash_now full`
           stays all-EQUAL across the save, because the key is on
           `saveBlobExcludedTopKey`.

           HOW THE READ HALF IS PROVEN, AND WHY NOT BY LOADING THE SAVE (fix,
           WV-D5). The first version of this phase asked the harness to load the
           file into a throwaway `SavedGame` and then delete it. That killed the
           HOST PROCESS about one run in three: `SavedBattleGame::load` fills
           `_mapDataSets` from `Mod::getMapDataSet()`, which is a CACHE handing
           back the Mod's ONE shared MapDataSet per name - the same objects the
           LIVE battle uses - and `~SavedBattleGame` then calls
           `unloadData()` on every one of them, which `delete`s the MapData the
           live battle's tiles still point at. The lever now parses the saved
           file as DATA and runs `coopLoadTurnMode()` - the exact function
           `SavedBattleGame::load` calls - against the exact `battleGame` node it
           would have been handed, constructing no SavedGame, no
           SavedBattleGame and no MapDataSet at all. The one thing that detour
           cannot observe, that the reader is actually CALLED from
           `SavedBattleGame::load`, is asserted separately and exactly below.
  PHASE 4  IDENTICAL BEHAVIOUR in both settings at this packet - a turn intent
           is admitted and applied exactly the same way with the mode
           traditional as with it parallel, and all buckets stay EQUAL. This is
           the direct check on REV D's binding rule; W1-P13's acceptance is
           where the two modes are finally allowed to differ.

An SP battle save must NOT carry the key at all - that half is asserted by this
packet's SP battle smoke, which is where an SP battle already exists.

FIXTURE: the repro_atom_turn.py / test_rw_retry_cancel.py recipe (WV-D18).

Run:  python tools/coop_test/test_rw_turn_mode.py
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import assert_hash_clean

COOP_SEAT_1 = 1
# Raised from 5 with SELECTION RULE (c) below: it rejects more
# generations than rules (a)+(b) did, and a re-roll is the CORRECT
# response to a fixture that cannot prove the property.
MAX_REROLLS = 15

PARALLEL = "parallel"
TRADITIONAL = "traditional"
OPTION = "CoopTurnMode"


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def units_by_id(battle_state_resp):
    return {u["id"]: u for u in battle_state_resp.get("units", [])}


def event_state(gc):
    return gc.cmd({"cmd": "event_state"})


def log_lines(gc):
    """This instance's openxcom.log, straight off disk - the same way
    repro_reveal_sync.py:230 and session.py:863 read it (there is no read_log
    command). Log evidence is what proves a message was actually BUILT and SENT,
    as opposed to a state that merely happens to look right."""
    path = os.path.join(gc.user_dir, "openxcom.log")
    if not os.path.exists(path):
        return []
    with open(path, "r", errors="replace") as f:
        return f.read().splitlines()


def get_mode(gc):
    """The OPTION on this machine (raw + normalized)."""
    r = gc.ok({"cmd": "set_option", "name": OPTION})
    return r.get("value"), r.get("normalized")


def set_mode(gc, value):
    r = gc.ok({"cmd": "set_option", "name": OPTION, "value": value})
    assert r.get("value") == value, f"set_option {OPTION}={value!r} did not land: {r}"
    return r.get("normalized")


def live_mode(gc):
    """THIS BATTLE's mode - the BattleAuthority mirror, i.e. what came off the
    wire on a client and what the host stamped."""
    return event_state(gc).get("turnMode")


def wait_main_menu(gc):
    gc.wait_for("main menu",
                lambda: (lambda s: s if s and s[0] != "class OpenXcom::StartState" else None)(
                    gc.cmd({"cmd": "get_state"}).get("states")),
                timeout=180, interval=2)


# ===========================================================================
# PHASE 1 - the option (D-20/D-21, WR-25)
# ===========================================================================

def test_option():
    """One instance at the main menu - the option is a plain per-machine user
    preference and needs no battle."""
    d = make_user_dir("rw_turnmode_option")
    g = GameClient("opt", 45991, d)
    g.spawn()
    try:
        g.connect(timeout=180)
        wait_main_menu(g)

        raw, norm = get_mode(g)
        assert raw == PARALLEL and norm == PARALLEL, (
            f"{OPTION} default is {raw!r}/{norm!r}, expected {PARALLEL!r} - ruling D-26 "
            "makes PARALLEL the default when nothing is remembered; check the "
            "Options.cpp OptionInfo registration")
        print(f"PASS PHASE 1 (default): {OPTION} defaults to {PARALLEL!r} (D-26)")

        for want in (TRADITIONAL, PARALLEL, TRADITIONAL):
            set_mode(g, want)
            raw, norm = get_mode(g)
            assert raw == want and norm == want, \
                f"{OPTION} did not stay {want!r} on a separate read: {raw!r}/{norm!r}"
        print(f"PASS PHASE 1 (round-trip): {OPTION} round-trips through set_option - a "
              "real OptionInfo, not a connectionTCP static (WR-25)")

        # D-26's normalizer: a hand-edited options.cfg can never put a garbage
        # value on the wire. The RAW value is preserved (this is the user's
        # file), but what the game will actually send is parallel.
        set_mode(g, "banana")
        raw, norm = get_mode(g)
        assert raw == "banana" and norm == PARALLEL, (
            f"a junk value normalized to {norm!r}, expected {PARALLEL!r} - D-26 says "
            "anything other than \"traditional\" is parallel")
        print(f"PASS PHASE 1 (normalize): a junk option value degrades to {PARALLEL!r} "
              "on the wire while options.cfg keeps what the user wrote")

        # ...and it SURVIVES A RESTART. Game::run() ends in Options::save()
        # (Game.cpp:498) and the harness's shutdown sends a graceful quit, so
        # this is the real persistence path, not a re-read of memory.
        set_mode(g, TRADITIONAL)
    finally:
        g.shutdown()

    g2 = GameClient("opt2", 45991, d)  # SAME user folder - do NOT re-make it
    g2.spawn()
    try:
        g2.connect(timeout=180)
        wait_main_menu(g2)
        raw, norm = get_mode(g2)
        assert raw == TRADITIONAL and norm == TRADITIONAL, (
            f"{OPTION} came back as {raw!r} after a restart, expected {TRADITIONAL!r} - "
            "the choice must be remembered in options.cfg (D-20)")
        print(f"PASS PHASE 1 (restart): {OPTION}={TRADITIONAL!r} survived a full "
              "process restart via options.cfg")
    finally:
        g2.shutdown()


# ----- fixture bring-up (inline copy, repro_atom_kneel.py precedent) -----

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


def bring_up_lobby(host, client, port):
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    skirmish_host(host, port)
    client.ok({"cmd": "open_new_battle"})
    client.wait_for("client new battle", lambda: session.has_state(client, "NewBattleState"))
    client.ok({"cmd": "newbattle_coop"})
    client.wait_for("client browser", lambda: session.has_state(client, "ServerList"))
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer"})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: lobby(host).get("buttonVisible") or None)


def drive_to_battlescape(host, client, seated_holder, seat_count=2):
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={states(host)}"
    soldier_ids = []
    for i in range(seat_count):
        r = host.ok({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1, "index": i})
        soldier_ids.append(r["soldierId"])
    seated_holder["soldierIds"] = soldier_ids
    seated_holder["soldierId"] = soldier_ids[0]
    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=30)
    client.wait_for("client battlescape",
                    lambda: session.has_state(client, "BattlescapeState"), timeout=60)
    time.sleep(3)
    host.ok({"cmd": "click_widget", "match": "ok"})
    host.wait_for("host battlescape",
                  lambda: session.has_state(host, "BattlescapeState"), timeout=30)
    session.dismiss_battle_start_overlays(host)
    session.dismiss_client_briefing(client)


def has_door_within(gc, x, y, z, radius=2):
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            ti = gc.cmd({"cmd": "tile_info", "x": x + dx, "y": y + dy, "z": z})
            if not ti.get("ok"):
                continue
            for part in ti.get("parts", {}).values():
                if part.get("isDoor") or part.get("isUfoDoor"):
                    return True
    return False


FACTION_PLAYER = 0

# RB-D15 / REVIEW4 IR-4 SELECTION RULE (c), ported from repro_atom_turn.py's
# 2026-09-03 fixture-robustness pass - see that file's module docstring for the
# full trace. Mod::_maxViewDistance's default (`src/Mod/Mod.cpp:424`), which
# stock xcom1 does not override; a HARD CAP, because darkness only ever REDUCES
# effective view range.
MAX_VIEW_DISTANCE = 20


def nearest_non_player_distance(battle_state_resp, unit):
    """Straight-line 3D tile distance from `unit` to the closest LIVING
    non-player unit, or None if there are none."""
    best = None
    for u in battle_state_resp.get("units", []):
        if u.get("faction") == FACTION_PLAYER or u.get("isOut"):
            continue
        d2 = ((u["x"] - unit["x"]) ** 2 + (u["y"] - unit["y"]) ** 2
              + (u["z"] - unit["z"]) ** 2)
        if best is None or d2 < best:
            best = d2
    return None if best is None else best ** 0.5


def actor_is_contact_free(host, battle_state_resp, unit):
    """SELECTION RULE (c): reject an actor with any LIVING NON-PLAYER unit
    within MAX_VIEW_DISTANCE.

    WHY (RB-D15, WV-D18, REVIEW4 IR-4). RB-D15 requires an "open-ground,
    no-door, NO-ENEMY-LOS" actor. Asking whether a hostile is ALREADY spotted at
    t=0 covers none of the third requirement: vanilla aborts a BA_NONE turn
    mid-chain the moment `getUnitsSpottedThisTurn()` grows
    (UnitTurnBState.cpp:117), leaving the unit on an intermediate facing - and
    the engine itself calls that a FIXTURE failure ("[coop-turn] ... ABORTED
    mid-chain - the RB-D15/REVIEW4 IR-4 fixture guards ... should have prevented
    this"). Observed live in this very test on 2026-09-03.

    A conservative SUPERSET of vanilla's predicate: a unit beyond the view-
    distance cap can never be spotted by any rotation, so a fixture that passes
    this cannot take the abort branch. A PIN on the selection rule, never a
    relaxation of anything asserted."""
    d = nearest_non_player_distance(battle_state_resp, unit)
    if d is not None and d <= MAX_VIEW_DISTANCE:
        print(f"[test_rw_turn_mode] rule (c): nearest non-player unit is {d:.2f} tiles from "
              f"the actor (cap {MAX_VIEW_DISTANCE}) - its rotation could spot one "
              "and abort mid-chain")
        return False
    print(f"[test_rw_turn_mode] rule (c) ok: nearest non-player unit is "
          f"{'none at all' if d is None else format(d, '.2f') + ' tiles'} away "
          f"(cap {MAX_VIEW_DISTANCE})")
    return True


def qualifying_actor(host, soldier_id):
    """REVIEW4 IR-4 SELECTION RULE, verbatim from repro_atom_turn.py."""
    st = host.cmd({"cmd": "battle_state"})
    if not st.get("ok") or not st.get("inBattle") or st.get("spotted"):
        return None
    for u in units_by_id(st).values():
        if u.get("soldierId") == soldier_id:
            if has_door_within(host, u["x"], u["y"], u["z"], radius=2):
                return None  # rule (b)
            if not actor_is_contact_free(host, st, u):
                return None  # rule (c)
            return u
    return None


def bring_up_qualifying_battle(tag, host_options=None, client_options=None,
                               pre_offer=None):
    """Returns (host, client, actor, soldier_ids, host_dir).

    `host_options` / `client_options` are spliced into each instance's
    options.cfg BEFORE it boots, which is the only way to have the mode in
    force from the very first frame (harness.make_user_dir). `pre_offer` runs
    on the host after the lobby is up and before the offer goes out."""
    for attempt in range(1, MAX_REROLLS + 1):
        port = str(48436 + attempt)
        host_dir = make_user_dir(f"rw_tm_{tag}_host_{attempt}", options=host_options)
        client_dir = make_user_dir(f"rw_tm_{tag}_client_{attempt}", options=client_options)
        host = GameClient("host", 49280 + attempt * 2, host_dir)
        client = GameClient("client", 49281 + attempt * 2, client_dir)
        seated = {}
        try:
            bring_up_lobby(host, client, port)
            if pre_offer:
                pre_offer(host, client)
            drive_to_battlescape(host, client, seated, seat_count=2)
            actor = qualifying_actor(host, seated["soldierId"])
            if actor is not None:
                print(f"[test_rw_turn_mode] fixture qualifies on attempt "
                      f"{attempt}/{MAX_REROLLS} (actor unit id={actor['id']})")
                return host, client, actor, seated["soldierIds"], host_dir
            print(f"[test_rw_turn_mode] re-roll {attempt}/{MAX_REROLLS}")
            host.shutdown()
            client.shutdown()
        except Exception:
            host.shutdown()
            client.shutdown()
            raise
    raise RuntimeError(f"test_rw_turn_mode: no qualifying fixture in {MAX_REROLLS} boots")


def settle_emits(host, client, timeout=40):
    def quiet():
        hs = event_state(host)
        cs = event_state(client)
        rs = host.cmd({"cmd": "reveal_state"})
        return bool(hs.get("ok") and cs.get("ok") and rs.get("ok")
                    and rs.get("unpublished") is False
                    and cs.get("lastSeqApplied", 0) == hs.get("lastSeqEmitted", 0)
                    and cs.get("queueDepth") == 0)
    client.wait_for("host quiet and client caught up", quiet, timeout=timeout)


def run_a_turn(host, client, actor_id, what):
    """One admitted client TURN intent, start to finish. Used to show the two
    modes behave IDENTICALLY at this packet (REV D's binding rule)."""
    settle_emits(host, client)
    a = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_id]
    to_dir = (a["direction"] + 2) % 8
    before_tu = a["tu"]
    client.ok({"cmd": "battle_intent", "kind": "turn", "actor": actor_id, "toDir": to_dir})

    def landed():
        cu = units_by_id(client.cmd({"cmd": "battle_state"})).get(actor_id)
        hu = units_by_id(host.cmd({"cmd": "battle_state"})).get(actor_id)
        return True if (cu and hu and cu["direction"] == to_dir
                        and hu["direction"] == to_dir
                        and event_state(client).get("queueDepth") == 0) else None
    client.wait_for(f"turn admitted and applied ({what})", landed, timeout=30)
    cu = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_id]
    hu = units_by_id(host.cmd({"cmd": "battle_state"}))[actor_id]
    assert cu["tu"] == hu["tu"] and cu["tu"] < before_tu, \
        f"{what}: TU disagree or did not drop: client={cu} host={hu}"
    return to_dir, hu["tu"]


# ===========================================================================
# PHASE 2 + 4 - the wire, and identical behaviour in both settings
# ===========================================================================

def test_wire_traditional():
    """Host TRADITIONAL -> the offer carries it and the CLIENT MIRRORS it.

    NON-VACUITY: the client's OWN option is pinned to the OPPOSITE value for
    the whole run. A mirror that read the local preference instead of the wire
    would report "parallel" here and fail."""
    host, client, actor, soldier_ids, host_dir = bring_up_qualifying_battle(
        "trad",
        host_options={OPTION: TRADITIONAL},
        client_options={OPTION: PARALLEL})
    try:
        h_raw, _ = get_mode(host)
        c_raw, _ = get_mode(client)
        assert h_raw == TRADITIONAL and c_raw == PARALLEL, (
            f"fixture did not pin the options as intended: host={h_raw!r} "
            f"client={c_raw!r} - this test would be vacuous")

        assert live_mode(host) == TRADITIONAL, (
            f"host's live battle mode is {live_mode(host)!r}, expected {TRADITIONAL!r} "
            "- offerBattle() must stamp the session's mode onto the battle")
        assert live_mode(client) == TRADITIONAL, (
            f"CLIENT's live battle mode is {live_mode(client)!r}, expected "
            f"{TRADITIONAL!r}. Its OWN option says {c_raw!r}, so this is exactly the "
            "case D-19b names: the host decides and the client MIRRORS off the wire.")
        assert event_state(client).get("optionTurnMode") == PARALLEL, (
            "the client's own remembered option changed - the mirror must never "
            "write back into options.cfg")
        print(f"PASS PHASE 2 (traditional): host option={TRADITIONAL!r} -> "
              f"battle_offer.turnMode -> CLIENT mirror={TRADITIONAL!r}, while the "
              f"client's own option stayed {PARALLEL!r} (D-19b)")

        # The host's own log line is the direct evidence the field went out.
        log = log_lines(host)
        assert any("battle_offer sent" in l and 'turnMode=traditional' in l for l in log), (
            "no 'battle_offer sent (... turnMode=traditional ...)' line in the host log")
        print("PASS PHASE 2 (traditional): the host logged the offer carrying "
              "turnMode=traditional")

        # PHASE 4: behaviour is IDENTICAL - REV D's binding rule for this packet.
        actor_id = actor["id"]
        to_dir, tu = run_a_turn(host, client, actor_id, "traditional mode")
        post_h, _ = assert_hash_clean(host, client, full=True,
                                      what="after a turn in TRADITIONAL mode")
        assert live_mode(host) == TRADITIONAL and live_mode(client) == TRADITIONAL, \
            "the mode drifted during play"
        print(f"PASS PHASE 4 (traditional): an intent was admitted and applied exactly "
              f"as in parallel mode (unit {actor_id} -> dir {to_dir}, TU {tu}), "
              f"{len(post_h)} buckets EQUAL - nothing branches on the mode yet, which "
              "is what REV D requires of this packet")
        return
    finally:
        host.shutdown()
        client.shutdown()


def test_wire_default_and_absent():
    """Nothing remembered -> the offer carries "parallel"; and with the key
    REMOVED from the offer the client degrades to parallel (D-26)."""

    def arm_omit(host, client):
        # One-shot: the NEXT offer is built WITHOUT the key. Armed after the
        # lobby is up, i.e. after isCoopBattle()'s session gate is satisfied.
        host.ok({"cmd": "omit_turn_mode", "on": True})

    # --- (a) nothing remembered -> parallel, over the real wire ---
    host, client, actor, soldier_ids, _ = bring_up_qualifying_battle("dflt")
    try:
        assert get_mode(host)[0] == PARALLEL, "fixture host did not start at the default"
        assert live_mode(host) == PARALLEL and live_mode(client) == PARALLEL, (
            f"default-mode battle reports host={live_mode(host)!r} "
            f"client={live_mode(client)!r}, expected {PARALLEL!r} on both (D-26)")
        log = log_lines(host)
        assert any("battle_offer sent" in l and "turnMode=parallel" in l for l in log), (
            "the host did not log an offer carrying turnMode=parallel - REQUIRED means "
            "a wave-1 host ALWAYS sends the key, even for the default")
        print(f"PASS PHASE 2 (default): nothing remembered -> the offer carries "
              f"{PARALLEL!r} and both machines agree (D-26)")
    finally:
        host.shutdown()
        client.shutdown()

    # --- (b) the key REMOVED from the offer -> the client degrades to parallel ---
    # The host is set TRADITIONAL, so a client that fell back to anything other
    # than the ruled default would be visible: it can only report "parallel" by
    # taking the degrade, never by copying the host.
    host, client, actor, soldier_ids, _ = bring_up_qualifying_battle(
        "omit", host_options={OPTION: TRADITIONAL}, pre_offer=arm_omit)
    try:
        log = log_lines(host)
        assert any("omit_turn_mode lever" in l and "WITHOUT turnMode" in l for l in log), (
            "the omit_turn_mode lever did not fire - the offer still carried the key, "
            "so the D-26 degrade below would be asserted against nothing")
        clog = log_lines(client)
        assert any("key ABSENT - D-26 degrade" in l for l in clog), (
            "the client did not report an ABSENT turnMode key on the offer it accepted")
        assert live_mode(client) == PARALLEL, (
            f"with the key absent the client reports {live_mode(client)!r}, expected "
            f"{PARALLEL!r} - D-26's degrade is what lets a pre-REV-D peer connect")
        print(f"PASS PHASE 2 (absent key): an offer built WITHOUT turnMode - proven "
              f"DELIVERED by both logs - degrades the client to {PARALLEL!r} (D-26)")
    finally:
        host.shutdown()
        client.shutdown()


# ===========================================================================
# PHASE 3 - the D.1 battle-save hook
# ===========================================================================

def find_save(user_dir, name):
    p = os.path.join(user_dir, "xcom1", name)
    return p if os.path.exists(p) else None


def assert_reader_is_wired():
    """The one link the detached-node read cannot observe: that the D.1 reader is
    actually CALLED from `SavedBattleGame::load`.

    The runtime detour above proves `coopLoadTurnMode()` parses the real saved
    form correctly; it cannot prove the hook site still exists, because it calls
    the function directly. Deleting that one line would leave every other PHASE 3
    assertion green while D.1's read half was silently dead - so it is checked
    here, exactly and at the source, the same way `tools/ci/lint_no_client_mint.py`
    checks a discipline that has no runtime signal.

    Deliberately NOT a substitute for the runtime read: this says the call
    EXISTS, the detour says it WORKS. Both are required."""
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "src", "Savegame",
        "SavedBattleGame.cpp")
    assert os.path.exists(path), f"cannot find {path} to check the D.1 hook site"
    with open(path, "r", errors="replace") as f:
        src = f.read()
    load_at = src.find("void SavedBattleGame::load(")
    save_at = src.find("void SavedBattleGame::save(")
    assert load_at >= 0 and save_at > load_at, (
        "could not locate SavedBattleGame::load/save to bound the hook check")
    assert "coopLoadTurnMode(reader);" in src[load_at:save_at], (
        "`coopLoadTurnMode(reader);` is not called inside SavedBattleGame::load - "
        "D.1's read half is not wired, so a resumed battle would silently come back "
        "in the wrong turn mode (WV-D55 / D-20/D-21)")
    assert "coopSaveTurnMode(writer);" in src[save_at:], (
        "`coopSaveTurnMode(writer);` is not called inside SavedBattleGame::save - "
        "D.1's write half is not wired")
    print("PASS PHASE 3 (wiring): coopLoadTurnMode is called from "
          "SavedBattleGame::load and coopSaveTurnMode from ::save")


def split_blocks(text):
    """Returns (campaign_block, battle_block). The battle save is one YAML
    document whose `battleGame:` mapping is the battle block; everything before
    it is the campaign block (SavedGame's own top level)."""
    m = re.search(r"^battleGame:\s*$", text, re.M)
    assert m, "no `battleGame:` block in the save - this is not a battle save"
    return text[:m.start()], text[m.start():]


def test_battle_save():
    """D.1: the mode is persisted in the BATTLE save block, read back by the
    real loader, absent from the CAMPAIGN block, and hash-neutral."""
    host, client, actor, soldier_ids, host_dir = bring_up_qualifying_battle(
        "save", host_options={OPTION: TRADITIONAL})
    try:
        settle_emits(host, client)
        assert live_mode(host) == TRADITIONAL
        pre_h, _ = assert_hash_clean(host, client, full=True, what="before the save")

        name = "w1p7_turnmode.sav"
        r = host.ok({"cmd": "turn_mode_save_roundtrip", "file": name})
        assert not r.get("parseError"), f"the saved file did not parse: {r}"
        assert r.get("hadBattleBlock") is True, (
            f"the saved file has no `battleGame` block: {r} - that block is what "
            "carries the key, so the read below would be vacuous")
        assert r.get("keyInBlock") is True, (
            f"the `battleGame` block does not contain `coopTurnMode`: {r} - the reader "
            "would then be handed a node with nothing in it, and a failure to restore "
            "the value would say nothing about the reader")
        assert r.get("written") == TRADITIONAL, f"unexpected live mode at save: {r}"
        assert r.get("poisoned") == PARALLEL, (
            f"the round-trip did not poison the mirror before reading: {r} - without "
            "that, a reader that read NOTHING would look identical to one that worked")
        assert r.get("readBack") == TRADITIONAL, (
            f"coopLoadTurnMode() did NOT restore the mode: wrote "
            f"{r.get('written')!r}, poisoned to {r.get('poisoned')!r}, read back "
            f"{r.get('readBack')!r} (D.1's read half)")
        print(f"PASS PHASE 3 (round-trip): save wrote {TRADITIONAL!r}, the mirror was "
              f"poisoned to {PARALLEL!r}, and the REAL coopLoadTurnMode() - fed the "
              f"saved file's own `battleGame` node - restored {TRADITIONAL!r}")

        assert_reader_is_wired()

        assert live_mode(host) == TRADITIONAL, \
            "the round-trip left the live session's mode disturbed"

        # ...and the key is where D-21 says, and NOWHERE else.
        path = find_save(host_dir, name)
        assert path, f"save file {name} not found under {host_dir}"
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        campaign, battle = split_blocks(text)
        assert "coopTurnMode: traditional" in battle, (
            "the battleGame: block does not carry `coopTurnMode: traditional`")
        assert "coopTurnMode" not in campaign, (
            "the CAMPAIGN block carries coopTurnMode - D-21 FORBIDS campaign-block "
            "persistence; the donor's SavedGame.cpp:1334/:1814 shape is not ported")
        assert "coop_parallel_turns" not in text, (
            "the donor's `coop_parallel_turns` key was ported after all (D-21)")
        print("PASS PHASE 3 (placement): `coopTurnMode: traditional` is in the "
              "battleGame: block and NOWHERE in the campaign block (D-21)")

        # HASH: the key is on saveBlobExcludedTopKey, so writing it moved nothing.
        post_h, _ = assert_hash_clean(host, client, full=True, what="after the save")
        assert post_h == pre_h, (
            f"the save moved a hash bucket: {pre_h} -> {post_h} - `coopTurnMode` must "
            "be on SharedEcon's saveBlobExcludedTopKey list")
        print(f"PASS PHASE 3 (hash): all {len(post_h)} buckets EQUAL and UNCHANGED "
              "across the save - the key never rides saveBlob")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    test_option()
    test_wire_traditional()
    test_wire_default_and_absent()
    test_battle_save()
    print("ALL W1-P7 DELIVERABLE-6 TURN-MODE TESTS PASSED")


if __name__ == "__main__":
    main()
