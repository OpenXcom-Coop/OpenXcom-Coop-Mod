"""Schema-3 SEPARATE regression: one authoritative host save, named bases.

Requires a freshly built executable.  It covers the dangerous conversion target
also used by upgraded legacy saves: two real bases in one world, no durable client
blob, opposite local/foreign presentation, and a host save that resumes by
streaming that same unified world.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import session
import geo as geo_helpers
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT


SAVE = "separate_schema3_resume.sav"
RIFLE = "STR_RIFLE"


def geo(gc):
    return gc.ok({"cmd": "geo_state"})


def canonical_bases(gc):
    return sorted(
        (b["name"], b.get("ownerPlayerName", ""), b["lon"], b["lat"],
         tuple(sorted((c["id"], c["type"]) for c in b["crafts"])))
        for b in geo(gc)["bases"]
    )


def canonical_world(gc):
    """Full one-world invariant, ignoring only seat-local presentation flags."""
    dump = shared_fixture.world_dump(gc)
    live = geo(gc)["bases"]
    for i, base in enumerate(dump["bases"]):
        base.pop("coopBase", None)
        base.pop("coopIcon", None)
        base["ownerPlayerName"] = live[i].get("ownerPlayerName", "")
    return dump


def soldiers_at(gc, base_name):
    bases = gc.ok({"cmd": "get_soldiers"})["bases"]
    return next(base["soldiers"] for base in bases if base["name"] == base_name)


def assert_foreign_soldier_screens(gc, base_name, expected_ids=(), expected_names=()):
    raw = soldiers_at(gc, base_name)
    local_seat = 0 if gc.name == "host" else 1
    owned = [s for s in raw if s["owner"] == local_seat]
    owned_ids = {s["id"] for s in owned}
    owned_names = {s["name"] for s in owned}
    gc.ok({"cmd": "open_soldiers", "base": base_name})
    screen = gc.ok({"cmd": "screen_state"})
    assert screen["top"] == "soldiers", screen
    assert set(screen["displayed"]) == owned_ids, \
        f"{gc.name} saw another player's soldiers: {screen!r}, owned={owned!r}"
    assert set(expected_ids).issubset(set(screen["displayed"])), screen

    opened = gc.ok({"cmd": "soldiers_inventory"})
    assert opened["opened"], opened
    inventory = gc.ok({"cmd": "inventory_ground"})
    inventory_ids = {soldier["id"] for soldier in inventory["soldiers"]}
    inventory_names = {soldier["name"] for soldier in inventory["soldiers"]}
    assert set(expected_ids).issubset(inventory_ids), inventory
    assert set(expected_names).issubset(inventory_names), inventory
    assert set(expected_names).issubset(owned_names), owned
    gc.ok({"cmd": "close_inventory"})
    gc.ok({"cmd": "soldiers_ok"})


def assert_arrival_owner_label(host, client, owner_name):
    """Owner sees a bare soldier name; the other player sees [Owner] Name."""
    def arrival_open(gc):
        states = gc.ok({"cmd": "get_state"}).get("states", [])
        return bool(states and "ItemsArrivingState" in states[-1]) or None

    for gc in (host, client):
        gc.wait_for(
            "personnel arrival popup",
            lambda gc=gc: arrival_open(gc),
            timeout=15, interval=0.3)
    host_rows = host.ok({"cmd": "items_arriving_rows"})["rows"]
    client_rows = client.ok({"cmd": "items_arriving_rows"})["rows"]
    assert len(host_rows) == len(client_rows) == 1, (host_rows, client_rows)
    assert not host_rows[0].startswith("["), host_rows
    assert client_rows[0].startswith(f"[{owner_name}] "), client_rows
    geo_helpers.drain_popups(host)
    geo_helpers.drain_popups(client)


def assert_same_world(host, client, label, timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        h, c = canonical_world(host), canonical_world(client)
        if h == c:
            print(f"PASS {label}: full host/client world is identical")
            return h
        time.sleep(0.5)
    raise AssertionError(
        f"{label}: Separate replicas did not converge\n"
        f"host={canonical_world(host)!r}\nclient={canonical_world(client)!r}")


def assert_own_soldiers_visible(gc, own_base):
    rosters = gc.ok({"cmd": "get_soldiers"})["bases"]
    raw = next(b for b in rosters if b["name"] == own_base)["soldiers"]
    local_seat = 0 if gc.name == "host" else 1
    expected = sorted(s["id"] for s in raw if s["owner"] == local_seat)
    assert expected, f"{own_base}: test precondition has no soldiers"
    gc.ok({"cmd": "open_soldiers", "base": own_base})
    try:
        gc.wait_for(
            f"{own_base} soldier screen",
            lambda: (gc.cmd({"cmd": "screen_state"}).get("top") == "soldiers") or None,
            timeout=15, interval=0.3)
        shown = sorted(gc.ok({"cmd": "screen_state"}).get("displayed", []))
        assert shown == expected, \
            f"{own_base}: soldier screen lost/added soldiers: {shown} != {expected}"
    finally:
        gc.ok({"cmd": "soldiers_ok"})


def assert_unified(host, client, pristine=False):
    hg, cg = geo(host), geo(client)
    assert hg["campaignType"] == 0 and cg["campaignType"] == 0
    assert len(hg["bases"]) == 2 and len(cg["bases"]) == 2
    assert canonical_bases(host) == canonical_bases(client)
    assert {b.get("ownerPlayerName") for b in hg["bases"]} == {
        "HostPlayer", "ClientPlayer"
    }
    assert not any(b.get("coopIcon") for b in hg["bases"] + cg["bases"])

    # Separate follows Shared's ownerPlayerId model. Initial ownership comes
    # from the unique base owner name; a later physical transfer must preserve
    # it instead of making the destination base owner a co-owner.
    expected_owner = {"HostBase": 0, "ClientBase": 1}
    for gc in (host, client):
        for base_name, seat in expected_owner.items():
            roster = soldiers_at(gc, base_name)
            assert roster and all(s["owner"] != 999 for s in roster), \
                f"{gc.name}: {base_name} retained unowned soldiers: {roster!r}"
            if pristine:
                assert all(s["owner"] == seat for s in roster), \
                    f"{gc.name}: {base_name} initial owners are wrong: {roster!r}"

    # _coopBase is only a local foreign-base presentation flag: opposite seats
    # must each see exactly one own and one foreign base.
    for gc in (host, client):
        bases = geo(gc)["bases"]
        assert sum(bool(b.get("coopBase")) for b in bases) == 1, \
            f"{gc.name}: expected one foreign presentation base, got {bases!r}"


def assert_foreign_basescape_menu(gc, expected_base):
    menu = gc.ok({"cmd": "basescape_menu_state"})
    assert menu["base"] == expected_base, menu
    assert menu["foreign"], menu
    visible = menu["visible"]
    for button in ("baseInfo", "soldiers", "crafts", "purchase", "geoscape"):
        assert visible[button], f"foreign {expected_base}: {button} unexpectedly hidden"
    for button in ("newBase", "facilities", "research", "manufacture",
                   "transfer", "sell"):
        assert not visible[button], \
            f"foreign {expected_base}: owner-only {button} unexpectedly visible"
    borders = menu["miniBorderColors"]
    assert borders[expected_base] == 1, \
        f"selected foreign {expected_base}: mini-base border is not white: {borders!r}"


def main():
    js = shared_fixture.bring_up(
        "sep3", (48920, 48921, 48220), campaign_mode="coop",
        host_base="HostBase", client_base="ClientBase")
    host, client = js.host, js.client
    host_dir, client_dir = js.host_dir, js.client_dir
    try:
        assert_unified(host, client, pristine=True)
        assert_own_soldiers_visible(host, "HostBase")
        assert_own_soldiers_visible(client, "ClientBase")
        initial_world = assert_same_world(host, client, "fresh Separate")

        # Country funding remains the normal full value. Only the Monthly
        # Report Income presentation is divided between the two seats, and the
        # two integer shares must add back to the exact original total.
        host_month = host.ok({"cmd": "month_report"})
        client_month = client.ok({"cmd": "month_report"})
        assert host_month["countryFunding"] == client_month["countryFunding"]
        assert host_month["countryFunding"] == sum(
            c["funding"] for c in host_month["countries"])
        assert (host_month["monthlyIncomeDisplay"]
                + client_month["monthlyIncomeDisplay"]
                == host_month["countryFunding"])
        print("PASS income: full country funding, Monthly Report split exactly between players")

        # Switching from the client's own base to the host's base must refresh
        # the existing BasescapeState permissions. Clicking the same foreign
        # base on the globe must enter Basescape directly, never Intercept.
        client.ok({"cmd": "open_screen", "screen": "basescape", "base": "ClientBase"})
        client.ok({"cmd": "basescape_select_base", "base": "HostBase"})
        assert_foreign_basescape_menu(client, "HostBase")
        client.ok({"cmd": "leave_base"})

        client.ok({"cmd": "globe_click_base", "base": "HostBase"})

        def globe_opened_foreign_base():
            states = client.cmd({"cmd": "get_state"}).get("states", [])
            return bool(states and states[-1].endswith("BasescapeState")) or None

        client.wait_for("foreign globe marker opened Basescape directly",
                        globe_opened_foreign_base, timeout=15, interval=0.3)
        states = client.ok({"cmd": "get_state"})["states"]
        assert not any(state.endswith("InterceptState") for state in states), states
        assert_foreign_basescape_menu(client, "HostBase")
        client.ok({"cmd": "leave_base"})

        # The foreign globe visit above deliberately leaves selectedBase on the
        # host base. The normal BASES button must reset it to this seat's base.
        client.ok({"cmd": "click_bases"})

        def bases_button_opened_own_base():
            state = client.cmd({"cmd": "basescape_menu_state"})
            return state if state.get("ok") and state.get("base") == "ClientBase" else None

        own_menu = client.wait_for("BASES button selected own base",
                                   bases_button_opened_own_base,
                                   timeout=15, interval=0.3)
        assert not own_menu["foreign"], own_menu
        assert own_menu["miniBorderColors"]["HostBase"] == 247, own_menu
        assert own_menu["miniBorderColors"]["ClientBase"] == 1, own_menu
        client.ok({"cmd": "leave_base"})
        print("PASS foreign base UI: purple border, direct globe route, BASES selects own base")

        # Put the host craft on an identical route in both replicas. Its owner
        # sees the route, while the client sees the craft marker/info only: no
        # command buttons, destination line or waypoint marker.
        host_flight = host.ok({"cmd": "fly_craft", "base": "HostBase"})
        client_flight = client.ok({"cmd": "fly_craft", "base": "HostBase"})
        assert host_flight["craftId"] == client_flight["craftId"]
        craft_id = host_flight["craftId"]
        host_route = host.ok({"cmd": "geo_craft_route_visibility",
                              "base": "HostBase", "craft_id": craft_id})
        client_route = client.ok({"cmd": "geo_craft_route_visibility",
                                  "base": "HostBase", "craft_id": craft_id})
        assert host_route["flightVisible"] and host_route["waypointVisible"], host_route
        assert not client_route["flightVisible"], client_route
        assert not client_route["waypointVisible"], client_route

        client.ok({"cmd": "globe_click_craft", "base": "HostBase",
                   "craft_id": craft_id})

        def foreign_craft_info_open():
            states = client.cmd({"cmd": "get_state"}).get("states", [])
            return bool(states and states[-1].endswith("GeoscapeCraftState")) or None

        client.wait_for("foreign craft opened read-only craft info",
                        foreign_craft_info_open, timeout=15, interval=0.3)
        craft_menu = client.ok({"cmd": "geoscape_craft_menu_state"})
        assert craft_menu["base"] == "HostBase", craft_menu
        assert not craft_menu["controlButtonsVisible"], craft_menu
        client.ok({"cmd": "close_geoscape_craft"})
        for gc in (host, client):
            gc.ok({"cmd": "land_craft", "base": "HostBase"})
        print("PASS foreign craft UI: read-only info, route and waypoint hidden")

        # A client may buy into the host's base, but may not build facilities
        # there. Both checks travel through the real Separate command protocol;
        # the latter is rejected by the host before command validation.
        host.ok({"cmd": "shared_reset_stats"})
        client.ok({"cmd": "shared_cmd", "jcmd": "fac_build", "baseId": 0,
                   "payload": {}})
        host.wait_for(
            "foreign facility rejected",
            lambda: (host.ok({"cmd": "shared_stats"})["failCount"] >= 1) or None,
            timeout=30, interval=0.5)
        fail = host.ok({"cmd": "shared_stats"})["lastFail"]
        assert fail == "foreign base command rejected", fail

        before_incoming = host.ok(
            {"cmd": "incoming_transfers", "base": "HostBase"})["items"].get(RIFLE, 0)
        client.ok({"cmd": "buy", "item": RIFLE, "count": 1, "base": "HostBase"})
        host.wait_for(
            "foreign purchase reached host base",
            lambda: (host.ok({"cmd": "incoming_transfers", "base": "HostBase"})
                     ["items"].get(RIFLE, 0) == before_incoming + 1) or None,
            timeout=30, interval=0.5)
        client.wait_for(
            "foreign purchase replicated",
            lambda: (client.ok({"cmd": "incoming_transfers", "base": "HostBase"})
                     ["items"].get(RIFLE, 0) == before_incoming + 1) or None,
            timeout=30, interval=0.5)
        print("PASS ownership: foreign buy allowed, foreign facility build rejected")

        # Regression: personnel bought into, or transferred into, a foreign
        # base must leave Transfers on arrival and appear in both Soldiers and
        # Equip Soldier. Old Separate coopBase roster filters hid them forever.
        # Exercise the difficult direction: the host simulation advances a base
        # owned by the client. The authoritative transfer_arrived broadcast must
        # bypass player-action ownership filtering and clean the replica too.
        before_foreign_ids = {s["id"] for s in soldiers_at(host, "ClientBase")}
        host.ok({"cmd": "buy", "item": "STR_SOLDIER", "count": 1,
                 "kind": "soldier", "base": "ClientBase"})
        for gc in (host, client):
            gc.wait_for("foreign-base recruit en route",
                        lambda gc=gc: (gc.ok({"cmd": "incoming_transfers",
                                             "base": "ClientBase"})["soldiers"] == 1) or None,
                        timeout=30, interval=0.5)
        arrived = host.ok({"cmd": "force_transfer_arrivals", "base": "ClientBase"})
        assert arrived["rows"] >= 1 and arrived["remaining"] == 0, arrived
        client.wait_for(
            "replica removed arrived foreign-base recruit",
            lambda: (client.ok({"cmd": "incoming_transfers",
                                "base": "ClientBase"})["soldiers"] == 0) or None,
            timeout=30, interval=0.5)
        assert_arrival_owner_label(host, client, "HostPlayer")

        hired_ids = {s["id"] for s in soldiers_at(host, "ClientBase")} - before_foreign_ids
        assert len(hired_ids) == 1, hired_ids
        assert_foreign_soldier_screens(host, "ClientBase", hired_ids)
        assert_foreign_soldier_screens(client, "ClientBase")

        host_source = soldiers_at(host, "HostBase")
        free_soldiers = [s for s in host_source if not s["craft"]]
        if free_soldiers:
            transfer_soldier = free_soldiers[0]
        else:
            # The starting roster is normally fully assigned to its transport.
            # Unseat one soldier through the real CraftSoldiersState command.
            transfer_soldier = host_source[0]
            host.ok({"cmd": "shared_reset_stats"})
            host.ok({"cmd": "craft_assign", "base": "HostBase",
                       "craft_id": transfer_soldier["craftId"],
                       "soldier_id": transfer_soldier["id"], "on": False})
            result = host.wait_for(
                "transfer test unassign apply/reject",
                lambda: (lambda soldier, stats:
                    {"soldier": soldier, "stats": stats}
                    if (soldier["craft"] == "" or stats["failCount"]
                        or stats["cmd"] or stats["applyCount"]) else None)(
                        next(s for s in soldiers_at(host, "HostBase")
                             if s["id"] == transfer_soldier["id"]),
                        host.ok({"cmd": "shared_stats"})),
                timeout=30, interval=0.5)
            assert result["soldier"]["craft"] == "", result
            for gc in (host, client):
                gc.wait_for(
                    "transfer test soldier unassigned",
                    lambda gc=gc: next(
                        s for s in soldiers_at(gc, "HostBase")
                        if s["id"] == transfer_soldier["id"])["craft"] == "" or None,
                    timeout=30, interval=0.5)
            transfer_soldier = next(
                s for s in soldiers_at(host, "HostBase")
                if s["id"] == transfer_soldier["id"])
        before_dest = soldiers_at(host, "ClientBase")
        moved = host.ok({"cmd": "transfer_to_coop_base",
                           "name": transfer_soldier["name"],
                           "toBase": "ClientBase"})
        assert moved["transferred"], moved
        for gc in (host, client):
            gc.wait_for("foreign-base soldier transfer en route",
                        lambda gc=gc: (gc.ok({"cmd": "incoming_transfers",
                                             "base": "ClientBase"})["soldiers"] == 1) or None,
                        timeout=30, interval=0.5)
        arrived = host.ok({"cmd": "force_transfer_arrivals", "base": "ClientBase"})
        assert arrived["rows"] == 1 and arrived["remaining"] == 0, arrived
        client.wait_for(
            "replica removed arrived foreign-base soldier transfer",
            lambda: (client.ok({"cmd": "incoming_transfers",
                                "base": "ClientBase"})["soldiers"] == 0) or None,
            timeout=30, interval=0.5)
        assert_arrival_owner_label(host, client, "HostPlayer")

        after_dest = soldiers_at(host, "ClientBase")
        assert len(after_dest) == len(before_dest) + 1, after_dest
        assert any(s["name"] == transfer_soldier["name"] for s in after_dest), after_dest
        assert_foreign_soldier_screens(
            host, "ClientBase", expected_names={transfer_soldier["name"]})
        assert_foreign_soldier_screens(client, "ClientBase")

        # Regression: CraftInfoState used to draw crew icons from the complete
        # unified base roster, while its Crew button correctly showed only the
        # local player's soldiers. At a foreign base both views must use the
        # Shared-style owner filter.
        foreign_roster = soldiers_at(host, "ClientBase")
        foreign_craft_id = next(
            s["craftId"] for s in foreign_roster
            if s["owner"] == 1 and s["craftId"] >= 0)
        expected_owned = {s["id"] for s in foreign_roster if s["owner"] == 0}
        expected_assigned = sum(
            s["owner"] == 0 and s["craftId"] == foreign_craft_id
            for s in foreign_roster)
        host.ok({"cmd": "open_craft_info", "base": "ClientBase",
                 "craft_id": foreign_craft_id})
        craft_summary = host.wait_for(
            "foreign craft summary filters crew icons",
            lambda: (lambda r: r if r.get("ok") else None)(
                host.cmd({"cmd": "craft_info_state"})),
            timeout=15, interval=0.3)
        assert craft_summary["visibleCrew"] == expected_assigned, \
            (craft_summary, foreign_roster)
        host.ok({"cmd": "pop_state"})

        host.ok({"cmd": "open_screen", "screen": "craft_soldiers",
                 "base": "ClientBase", "craft_id": foreign_craft_id})
        crew_screen = host.ok({"cmd": "screen_state"})
        assert crew_screen["top"] == "craft_soldiers", crew_screen
        assert set(crew_screen["displayed"]) == expected_owned, \
            (crew_screen, foreign_roster)
        assert crew_screen["maxUnits"] == 14, crew_screen
        assert crew_screen["usedNum"] == 0, crew_screen
        assert crew_screen["availableNum"] == 7, crew_screen
        host.ok({"cmd": "pop_state"})

        # Assign the host-owned guest to the client's craft through the real
        # Separate command. The host's personal half changes 0/7 -> 1/6 while
        # the client's seven-person half remains intact.
        host.ok({"cmd": "craft_assign", "base": "ClientBase",
                 "craft_id": foreign_craft_id,
                 "soldier_id": transfer_soldier["id"], "on": True})
        for gc in (host, client):
            gc.wait_for(
                "guest assigned within owner craft quota",
                lambda gc=gc: (next(
                    s for s in soldiers_at(gc, "ClientBase")
                    if s["name"] == transfer_soldier["name"])["craftId"]
                    == foreign_craft_id) or None,
                timeout=30, interval=0.5)
        host.ok({"cmd": "open_screen", "screen": "craft_soldiers",
                 "base": "ClientBase", "craft_id": foreign_craft_id})
        assigned_screen = host.ok({"cmd": "screen_state"})
        assert assigned_screen["usedNum"] == 1, assigned_screen
        assert assigned_screen["availableNum"] == 6, assigned_screen
        host.ok({"cmd": "pop_state"})

        assert not any(s["name"] == transfer_soldier["name"]
                       for s in soldiers_at(host, "HostBase"))
        assert_same_world(host, client, "foreign personnel arrivals")
        print("PASS foreign personnel: hires/transfers leave transit and appear in both soldier screens")

        saved_world = assert_same_world(host, client, "pre-save Separate")
        key = f"host_{host.ok({'cmd': 'save_markers'})['saveID']}_ClientPlayer.data"
        assert not host.ok({"cmd": "has_coop_file", "key": key})["present"], \
            "schema-3 SEPARATE retained a durable client-world blob"

        host.ok({"cmd": "save_game", "file": SAVE})
        assert any(os.path.basename(path) == SAVE for path in session.save_files(host_dir))
        session.assert_client_zero_disk(client_dir)
        print("PASS fresh: two named real bases, one host save, zero client disk/blob")
    finally:
        js.shutdown()

    # Resume in fresh processes from the host file.  Copy only the authoritative
    # save; the client directory intentionally stays empty.
    host = GameClient("host", 48922, host_dir)
    client = GameClient("client", 48923, make_user_dir("sep3_resume_client"))
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        session.resume_campaign(host, client, SAVE, port="48221")
        assert_unified(host, client)
        assert_own_soldiers_visible(host, "HostBase")
        assert_own_soldiers_visible(client, "ClientBase")
        resumed_world = assert_same_world(host, client, "resumed Separate")
        assert resumed_world == saved_world, \
            "save/resume changed bases, soldiers, crafts, facilities, stores or economy"
        assert canonical_world(host) != initial_world, \
            "foreign purchase did not become part of the persisted world"
        key = f"host_{host.ok({'cmd': 'save_markers'})['saveID']}_ClientPlayer.data"
        assert not host.ok({"cmd": "has_coop_file", "key": key})["present"], \
            "resumed schema-3 SEPARATE recreated a client-world blob"
        session.assert_client_zero_disk(client.user_dir)
        print("PASS resume: every strategic object survived in one host save")

        # Fill the unified world to eight named-owner bases with deterministic
        # harness fixtures, then prove the ninth real base_new is host-rejected.
        for i in range(6):
            owner = "HostPlayer" if i % 2 == 0 else "ClientPlayer"
            req = {"cmd": "add_base", "name": f"LimitBase{i}",
                   "lon": 0.4 + i * 0.05, "lat": 0.2,
                   "coopbaseid": 500000 + i, "ownerPlayerName": owner}
            host.ok(req)
            client.ok(req)
        assert len(geo(host)["bases"]) == len(geo(client)["bases"]) == 8
        client.ok({"cmd": "shared_reset_stats"})
        client.ok({"cmd": "build_new_base", "lon": LAND_LON, "lat": LAND_LAT,
                   "name": "ForbiddenNinth", "liftX": 2, "liftY": 2})
        client.wait_for(
            "ninth base rejected",
            lambda: (client.ok({"cmd": "shared_stats"})["failCount"] >= 1) or None,
            timeout=30, interval=0.5)
        assert len(geo(host)["bases"]) == len(geo(client)["bases"]) == 8
        assert "MAXIMUM_NUMBER_OF_BASES" in client.ok(
            {"cmd": "shared_stats"})["lastFail"]
        print("PASS base cap: eight total bases allowed, ninth rejected globally")
    finally:
        host.shutdown(); client.shutdown()

    print("ALL SINGLE-WORLD SEPARATE TESTS PASSED")


if __name__ == "__main__":
    main()
