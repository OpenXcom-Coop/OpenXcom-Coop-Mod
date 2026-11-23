"""test_client_turn_host_reserve.py: the host's own TU reserve setting does not stop the second player's turn orders.

Each player's TU reserve (the reserve buttons) is that player's own setting: SavedBattleGame's tuReserved and
kneelReserved are kept per machine and left out of every hash. The host therefore does not apply its own reserve to
an order the second player (the client) gave: a client walk already skips it (coopWalkReserveRefuses). A client turn
must skip it too; otherwise the host's reserve cuts the client's turn short (vanilla UnitTurnBState checks the reserve
before every octant) and the host's screen shows the reserve warning for a soldier it does not command.

ONE boot: test_client_walk_draw's terror skirmish (STR_TERROR_MISSION, map seed 1, parallel turns, AI pinned
neutral), lobby key 48798. C (unit 8, the client's) and H (unit 10, the host's) each get a rifle and a clip and a
base TU of 40, so a rifle snap shot (25 %) costs 10 TU. Each row starts the turning unit on 11 TU: vanilla's reserve
leaves exactly one one-TU octant before it would dip into the snap shot (a unit that cannot afford the reserved shot
at all reserves nothing, so the TU must cover it). Rows, in this order:
  control_no_reserve      (control) reserve none on both. C on (12,26,0) facing 2 with 11 TU; the client orders a
                          turn to facing 5 (three octants). C ends facing 5 with 8 TU on both machines.
  client_turn_host_snap   the host sets reserve snap; the client keeps none. C back on facing 2 with 11 TU; the same
                          turn order. C ends facing 5 with 8 TU on both machines and the host shows no reserve
                          warning.
  host_turn_host_snap     (guard: vanilla holds for the host's own unit) H on (14,24,0) facing 2 with 11 TU; the
                          host right-clicks (11,24,0) (a turn to facing 6, four octants). The host's reserve stops
                          it after one octant: H holds 10 TU, is not facing 6, and the host shows the reserve
                          warning.
Every row also asserts hash_now full (every bucket EQUAL) and desyncSeen false on both.

One EVIDENCE line per row, one PASS / FAIL line per row. Every row runs after a failure. One run is the result, no
skip path. Exit 0 only when every row passes, else 2. Run it in the foreground to completion.

Run:  python tools/coop_test/test_client_turn_host_reserve.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, assert_hash_clean  # noqa: E402
import test_host_combat as HC  # noqa: E402
import test_client_shoot as CSH  # noqa: E402
import test_seat_pacing as SPC  # noqa: E402
from repro_atom_walk import set_reserve  # noqa: E402

KEY = "48798"
C_ID, H_ID = 8, 10
SEATED = [8, 9]
C_TILE, H_TILE = (12, 26, 0), (14, 24, 0)
DIR0 = 2
C_TO_DIR = 5                      # three octants from DIR0
H_CLICK = (11, 24, 0)             # due west of H: facing 6
BASE_TU = 40                      # base TU stat: a rifle snap shot (tuSnap 25 %) costs 10
START_TU = 11                     # the snap shot's 10 plus one one-TU octant
WAIT_S = 15


def unit(gc, uid):
    return session.units_by_id(battle_state(gc)).get(uid) or {}


def dirs(host, client, uid):
    return [unit(gc, uid).get("direction") for gc in (host, client)]


def tus(host, client, uid):
    return [unit(gc, uid).get("tu") for gc in (host, client)]


def warnings(host, client):
    return [battle_state(gc).get("warningText", "") for gc in (host, client)]


def common(host, client):
    fails = []
    try:
        assert_hash_clean(host, client, full=True, what="client_turn_host_reserve")
    except AssertionError as e:
        fails.append(f"hash_now full not clean: {CSH.short(e, 400)}")
    ds = [event_state(gc).get("desyncSeen") for gc in (host, client)]
    if ds != [False, False]:
        fails.append(f"desyncSeen host/client {ds} (want False/False)")
    return fails


def settle(host, client, seq0, notes):
    try:
        client.wait_for("client applied a new seq, both queues empty",
                        lambda: (event_state(client).get("lastSeqApplied", 0) > seq0
                                 and event_state(client).get("queueDepth") == 0
                                 and event_state(host).get("queueDepth") == 0) or None, timeout=WAIT_S)
    except Exception as e:
        notes.append(f"settle: {CSH.short(e, 200)}")
    try:
        session.wait_host_idle(host, client, timeout=WAIT_S)
    except Exception as e:
        notes.append(f"wait_host_idle: {CSH.short(e, 200)}")


def bring_up(host, client):
    HC.bring_up_lobby_roster_pinned(host, client, KEY)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=HC.MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": HC.SEED_MAP}))
    pinned = session.pin_ai_neutral(host, client, tag="client_turn_host_reserve")
    session.wait_host_idle(host, client, timeout=30)
    assert seated.get("soldierIds") == SEATED and pinned, f"seated {seated.get('soldierIds')} pinned {pinned}"
    for uid in (C_ID, H_ID):
        CSH.give_both(host, client, uid, "STR_RIFLE", "STR_RIFLE_CLIP")
        CSH.both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "tu",
                                "value": BASE_TU}, ("tu",))
    for gc in (host, client):
        set_reserve(gc, mode="none", kneel=False)
    assert_hash_clean(host, client, full=True, what="client_turn_host_reserve bring-up")


def client_turn_row(host, client, host_mode):
    notes, ev = [], {}
    set_reserve(host, mode=host_mode)
    ev["reserve"] = {gc.name: {k: battle_state(gc).get(k) for k in ("tuReserved", "kneelReserved")}
                     for gc in (host, client)}
    CSH.both(host, client, {"cmd": "battle_teleport_unit", "unit": C_ID, "x": C_TILE[0], "y": C_TILE[1],
                            "z": C_TILE[2], "dir": DIR0}, ("to", "dir"))
    CSH.set_tu_both(host, client, C_ID, START_TU)
    ev["start"] = {"dir": dirs(host, client, C_ID), "tu": tus(host, client, C_ID)}
    seq0 = event_state(client).get("lastSeqApplied", 0)
    ev["intent"] = session.send_turn(client, C_ID, C_TO_DIR)
    settle(host, client, seq0, notes)
    ev["end"] = {"dir": dirs(host, client, C_ID), "tu": tus(host, client, C_ID)}
    ev["warning"] = warnings(host, client)
    ev["notes"] = notes
    fails = list(notes)
    if ev["end"]["dir"] != [C_TO_DIR, C_TO_DIR] or ev["end"]["tu"] != [START_TU - 3, START_TU - 3]:
        fails.append(f"C facing host/client {ev['end']['dir']} TU {ev['end']['tu']} (want facing {C_TO_DIR} and "
                     f"{START_TU - 3} TU on both: the client's own order, host reserve {host_mode})")
    if "reserved" in (ev["warning"][0] or "").lower():
        fails.append(f"host warning {ev['warning'][0]!r} (want no reserve warning for the client's order)")
    return fails + common(host, client), ev


def host_turn_row(host, client):
    notes, ev = [], {}
    set_reserve(host, mode="snap")
    CSH.both(host, client, {"cmd": "battle_teleport_unit", "unit": H_ID, "x": H_TILE[0], "y": H_TILE[1],
                            "z": H_TILE[2], "dir": DIR0}, ("to", "dir"))
    CSH.set_tu_both(host, client, H_ID, START_TU)
    ev["tab"] = SPC.tab_select(host, H_ID)
    ev["start"] = {"dir": dirs(host, client, H_ID), "tu": tus(host, client, H_ID)}
    clk = host.cmd({"cmd": "map_tile_click", "x": H_CLICK[0], "y": H_CLICK[1], "z": H_CLICK[2], "button": "right"})
    ev["click"] = {k: clk.get(k) for k in ("verified", "clicked")}
    time.sleep(1.0)
    try:
        session.wait_host_idle(host, client, timeout=WAIT_S)
    except Exception as e:
        notes.append(f"wait_host_idle: {CSH.short(e, 200)}")
    ev["end"] = {"dir": dirs(host, client, H_ID), "tu": tus(host, client, H_ID)}
    ev["warning"] = warnings(host, client)
    ev["notes"] = notes
    fails = list(notes)
    if not (ev["tab"] and clk.get("clicked")):
        fails.append(f"precondition: H selected {ev['tab']} click {ev['click']}")
    if ev["end"]["tu"] != [START_TU - 1, START_TU - 1] or 6 in ev["end"]["dir"]:
        fails.append(f"H facing host/client {ev['end']['dir']} TU {ev['end']['tu']} (want one octant: "
                     f"{START_TU - 1} TU and not facing 6 on both, the host's reserve stops its own unit's turn as "
                     f"in vanilla)")
    if "reserved" not in (ev["warning"][0] or "").lower():
        fails.append(f"host warning {ev['warning'][0]!r} (want the reserve warning)")
    return fails + common(host, client), ev


def main():
    t0 = time.time()
    host = GameClient("host", 49908, make_user_dir("client_turn_host_reserve_host"))
    client = GameClient("client", 49909, make_user_dir("client_turn_host_reserve_client"))
    rows = (("control_no_reserve", lambda: client_turn_row(host, client, "none")),
            ("client_turn_host_snap", lambda: client_turn_row(host, client, "snap")),
            ("host_turn_host_snap", lambda: host_turn_row(host, client)))
    failed = []
    try:
        try:
            bring_up(host, client)
            booted = True
        except Exception as e:
            print(f"CAPTURE boot: {type(e).__name__}: {str(e)[:800]}", flush=True)
            booted = False
        for rid, fn in rows:
            ev = {}
            if not booted:
                fails = ["boot failed"]
            else:
                try:
                    fails, ev = fn()
                except Exception as e:  # every row runs after a failure
                    fails = [f"{type(e).__name__}: {CSH.short(e, 600)}"]
            print(f"EVIDENCE {rid}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
            print(f"{'PASS' if not fails else 'FAIL'} {rid}{': ' + '; '.join(fails) if fails else ''}", flush=True)
            if fails:
                failed.append(rid)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[client_turn_host_reserve] shutdown {gc.name}: {CSH.short(e, 200)}", flush=True)
    print(f"\ntest_client_turn_host_reserve: {len(rows) - len(failed)}/{len(rows)} rows passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
