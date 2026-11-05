"""Issue #194: the "custom initial base" option in a new co-op campaign.

With `customInitialBase` on, a player who names the first base gets the lift
screen and then the start facility list, and places every facility by hand.
Each player must be able to do that for their own first base, and each
finished base must hold its people, stores and craft.

  SEPARATE (both players have the option on):
    1. The client names its base and sees its own lift screen, with no co-op
       dialog over it.
    2. The client places its lift and every start facility.
    3. The host sees the client's base with those facilities before BEGIN.
    4. The host presses BEGIN, places its own lift and start facilities.
    5. Once the campaign runs, both machines show both bases with the lift and
       every start facility, the same layout on both machines, and stores,
       living quarters and hangars within capacity.

  SHARED (the host has the option on): the host places the lift and every start
  facility of the one shared base, and the client gets that same base.

Before the fix, the client's hold dialog covered its lift screen, the client
sent its base before any facility was placed, and the host's world then
replaced the client's. The client's base stayed with no facilities at all:
stores 51 used / 0 available, quarters 28 / 0, 3 craft / 0 hangars.

Run:  py -3 tools/coop_test/test_custom_initial_base.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import shared_fixture  # noqa: E402

OPTS = {"customInitialBase": "true"}
LIFT = "STR_ACCESS_LIFT"
# base-screen pixel targets (320x200 base coordinates): the first row of the
# start facility list, and the top-left of the base grid (32 px cells under an
# 8 px top margin).
FACILITY_ROW0 = (230, 68)
GRID_LEFT, GRID_TOP, CELL = 0, 8, 32


def states(gc):
    return [s.split("::")[-1] for s in gc.cmd({"cmd": "get_state"}).get("states", [])]


def top(gc):
    st = states(gc)
    return st[-1] if st else ""


def coop_dialog(gc):
    return gc.cmd({"cmd": "get_coop"}).get("coopDialog")


def settle(gc, before, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        t = top(gc)
        if t != before:
            return t
        time.sleep(0.05)
    return top(gc)


def wait_stable_top(gc, what, timeout=20, quiet=1.5):
    """Wait until the top state has not changed for `quiet` seconds; return the stack."""
    seen = {"stack": None, "since": time.time()}

    def stable():
        st = states(gc)
        if st != seen["stack"]:
            seen["stack"], seen["since"] = st, time.time()
            return None
        return st if time.time() - seen["since"] >= quiet else None

    return gc.wait_for(what, stable, timeout=timeout, interval=0.1)


def click_base(gc, scale, bx, by):
    sx, sy = scale
    gc.ok({"cmd": "inject_input", "kind": "click", "x": int(bx * sx), "y": int(by * sy)})


def place_custom_base(gc):
    """Place the lift and every start facility through the real screens.

    Returns the number of start facilities placed. The start facility screen
    closes only once its list is empty, so a return means every one was placed.
    """
    assert top(gc) == "PlaceLiftState", f"{gc.name}: lift screen not on top: {states(gc)}"
    # the BaseView is the first interactive surface; its centre is grid cell (3,3)
    r = gc.ok({"cmd": "click_widget"})
    scale = (r["winX"] / r["baseX"], r["winY"] / r["baseY"])
    gc.wait_for(f"{gc.name} start facility list",
                lambda: top(gc) == "SelectStartFacilityState" or None, timeout=20, interval=0.1)
    cells = sorted(((x, y) for x in range(6) for y in range(6) if (x, y) != (3, 3)),
                   key=lambda c: (abs(c[0] - 3) + abs(c[1] - 3), c))
    placed, tries = 0, 0
    while top(gc) == "SelectStartFacilityState" and tries < 300:
        for cell in list(cells):
            if top(gc) != "SelectStartFacilityState":
                break
            tries += 1
            click_base(gc, scale, *FACILITY_ROW0)
            if settle(gc, "SelectStartFacilityState") != "PlaceStartFacilityState":
                continue
            click_base(gc, scale, GRID_LEFT + cell[0] * CELL + CELL // 2,
                       GRID_TOP + cell[1] * CELL + CELL // 2)
            t = settle(gc, "PlaceStartFacilityState")
            if t == "ErrorMessageState":
                # the facility does not fit there; try the next cell
                gc.cmd({"cmd": "dismiss_popup"})
                settle(gc, t)
                continue
            placed += 1
            cells.remove(cell)
    assert top(gc) != "SelectStartFacilityState", (
        f"{gc.name}: start facility list still open after {placed} placements ({tries} tries)")
    print(f"[{gc.name}] placed the lift and {placed} start facilities; stack {states(gc)}")
    return placed


def base_facts(gc, name):
    base = next((b for b in gc.ok({"cmd": "geo_state"}).get("bases", []) if b.get("name") == name), None)
    report = gc.cmd({"cmd": "base_report", "base": name})
    facilities = sorted((f["type"], f["x"], f["y"]) for f in (base or {}).get("facilities", []))
    return facilities, report


def assert_base_ready(host, client, name, want_facilities):
    """Both machines show `name` with the lift and every start facility, in one layout, within capacity."""
    layouts = {}
    for gc in (host, client):
        facilities, r = base_facts(gc, name)
        layouts[gc.name] = facilities
        types = [f[0] for f in facilities]
        print(f"  {gc.name} sees {name}: {len(facilities)} facilities, stores {r.get('usedStores')}/"
              f"{r.get('availableStores')}, quarters {r.get('usedQuarters')}/{r.get('availableQuarters')}, "
              f"hangars {r.get('usedHangars')}/{r.get('availableHangars')}")
        assert r.get("error") is None, f"{gc.name}: {name}: {r}"
        assert LIFT in types, f"{gc.name}: {name} has no access lift: {facilities}"
        assert len(facilities) == want_facilities, (
            f"{gc.name}: {name} has {len(facilities)} facilities, want {want_facilities}: {facilities}")
        assert r["usedStores"] <= r["availableStores"], f"{gc.name}: {name} stores over capacity: {r}"
        assert r["usedQuarters"] <= r["availableQuarters"], f"{gc.name}: {name} quarters over capacity: {r}"
        assert r["usedHangars"] <= r["availableHangars"], f"{gc.name}: {name} hangars over capacity: {r}"
    assert layouts["host"] == layouts["client"], (
        f"{name}: the two machines show different layouts: host={layouts['host']} client={layouts['client']}")
    return layouts["host"]


def open_lobby(host, client, campaign_mode, port):
    """Host creates the campaign, client joins, host presses START CAMPAIGN."""
    has = session._has_state
    host.ok({"cmd": "open_new_game", "mode": campaign_mode})
    host.wait_for("difficulty", lambda: has(host, "NewGameState"))
    host.ok({"cmd": "newgame_ok"})
    host.wait_for("host window", lambda: has(host, "HostMenu"))
    host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": port, "player": "HostPlayer", "campaign": True})
    host.wait_for("host TCP listener", lambda: (host.cmd({"cmd": "get_coop"}).get("onConnect") == 1) or None,
                  timeout=30, interval=0.25)
    host.wait_for("host lobby", lambda: has(host, "LobbyMenu"))
    time.sleep(2)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer", "campaign": True})
    client.wait_for("client lobby", lambda: has(client, "LobbyMenu"), timeout=120)
    for gc in (host, client):
        gc.wait_for("join popup", lambda gc=gc: has(gc, "Profile"))
        gc.ok({"cmd": "profile_ok"})
    host.wait_for("start eligible", lambda: host.cmd({"cmd": "lobby_state"}).get("startEligible") or None)
    session.start_campaign_via_button(host)


def name_first_base(gc, name, lon, lat):
    gc.wait_for(f"{gc.name} base placement", lambda: session._has_state(gc, "BuildNewBaseState"), timeout=60)
    r = gc.cmd({"cmd": "place_first_base", "lon": lon, "lat": lat, "name": name})
    if not r.get("ok"):
        gc.ok({"cmd": "place_first_base", "lon": session.LAND_LON, "lat": session.LAND_LAT, "name": name})


def wait_campaign_running(host, client):
    """Both machines on the geoscape with no co-op dialog and no placement screen left."""
    for gc in (host, client):
        gc.wait_for(f"{gc.name} on the geoscape",
                    lambda gc=gc: (states(gc)[-1:] == ["GeoscapeState"]
                                   and "PlaceLiftState" not in states(gc)) or None,
                    timeout=120, interval=0.25)


def scenario_separate():
    js = shared_fixture.SharedSession("cib_sep", (0, 0, 47741), host_options=OPTS, client_options=OPTS,
                                      campaign_mode="coop")
    host, client = js.host, js.client
    try:
        host.spawn(); client.spawn()
        host.connect(timeout=60); client.connect(timeout=60)
        for gc in (host, client):
            gc.wait_for("main menu", lambda gc=gc: session.has_state(gc, "MainMenuState"), timeout=60)
        open_lobby(host, client, "coop", "47741")

        name_first_base(host, "HostBase", session.HOST_LON, session.HOST_LAT)
        name_first_base(client, "ClientBase", session.LAND_LON, session.LAND_LAT)

        # 1. the client sees its own lift screen, with nothing over it
        stack = wait_stable_top(client, "client screen after naming its base")
        print(f"client stack after naming its base: {stack} coopDialog={coop_dialog(client)}")
        assert stack[-1] == "PlaceLiftState", (
            f"the client cannot place its lift: top is {stack[-1]} (coopDialog={coop_dialog(client)}), "
            f"stack {stack}")

        # 2. the client places its lift and every start facility
        placed = place_custom_base(client)
        assert placed > 0, "the client placed no start facility"
        want = placed + 1  # the lift

        # 3. the host sees the client's finished base before BEGIN
        host.wait_for("client base merged on the host",
                      lambda: next((b for b in host.cmd({"cmd": "geo_state"}).get("bases", [])
                                    if b.get("ownerPlayerName") == "ClientPlayer"), None),
                      timeout=120)
        facilities, r = base_facts(host, "ClientBase")
        print(f"host sees ClientBase before BEGIN: {len(facilities)} facilities, stores "
              f"{r.get('usedStores')}/{r.get('availableStores')}, quarters "
              f"{r.get('usedQuarters')}/{r.get('availableQuarters')}")
        assert len(facilities) == want, (
            f"the host merged ClientBase with {len(facilities)} facilities, want {want}: {facilities}")

        # 4. the host presses BEGIN and places its own base
        session.press_back_when_shown(host, "host BEGIN", codes=(60, 62))
        host.wait_for("host lift screen", lambda: top(host) == "PlaceLiftState" or None, timeout=30, interval=0.1)
        host_placed = place_custom_base(host)
        assert host_placed == placed, f"host placed {host_placed} start facilities, client {placed}"

        # 5. the campaign runs with both finished bases on both machines
        host.wait_for("client settled-world ack",
                      lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None, timeout=120)
        wait_campaign_running(host, client)
        client_layout = assert_base_ready(host, client, "ClientBase", want)
        host_layout = assert_base_ready(host, client, "HostBase", want)
        assert sorted(f[0] for f in client_layout) == sorted(f[0] for f in host_layout), (
            f"the two players got different start facilities: host={host_layout} client={client_layout}")
        print("PASS separate: each player placed the lift and every start facility of their own base")
    finally:
        js.shutdown()


def scenario_shared():
    js = shared_fixture.SharedSession("cib_shr", (0, 0, 47742), host_options=OPTS, client_options=OPTS,
                                      campaign_mode="shared")
    host, client = js.host, js.client
    try:
        host.spawn(); client.spawn()
        host.connect(timeout=60); client.connect(timeout=60)
        for gc in (host, client):
            gc.wait_for("main menu", lambda gc=gc: session.has_state(gc, "MainMenuState"), timeout=60)
        open_lobby(host, client, "shared", "47742")

        name_first_base(host, "HostBase", session.HOST_LON, session.HOST_LAT)
        stack = wait_stable_top(host, "host screen after naming its base")
        print(f"host stack after naming its base: {stack} coopDialog={coop_dialog(host)}")
        assert stack[-1] == "PlaceLiftState", (
            f"the host cannot place its lift: top is {stack[-1]} (coopDialog={coop_dialog(host)}), stack {stack}")
        placed = place_custom_base(host)
        assert placed > 0, "the host placed no start facility"

        host.wait_for("client world ack", lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None,
                      timeout=120)
        session.press_back_when_shown(host, "host BEGIN", codes=(60, 62))
        wait_campaign_running(host, client)
        assert_base_ready(host, client, "HostBase", placed + 1)
        print("PASS shared: the host placed the lift and every start facility of the shared base")
    finally:
        js.shutdown()


def main():
    failures = []
    for name, scenario in (("separate", scenario_separate), ("shared", scenario_shared)):
        try:
            scenario()
        except (AssertionError, TimeoutError) as exc:
            failures.append(name)
            print(f"FAIL {name}: {exc}")
    if failures:
        print(f"FAILED scenarios: {failures}")
        sys.exit(1)
    print("PASS custom initial base: every player places their own lift and start facilities")


if __name__ == "__main__":
    main()
