"""test_item_cover.py: item, turn and proximity cases in one classic co-op skirmish. Each row repeats one trigger and
passes on the current build:
  host_turn  the host's real-UI 1/8 turn costs 1 TU
        host_turn-dir  H1 direction 1 on both          host_turn-cost  TU -1 on the host and on the client
  client_turn  the client's 1/8 turn intent costs 1 TU
        client_turn-admit  one new host context {intent, turn, 8}
        client_turn-dir / client_turn-cost  direction 1, TU -1 on both
  launch_right_hand  an alien's blaster launcher shot, launcher in the RIGHT hand (issue #74): A teleported into the
        open, a keepSelection reaction launch at the selected sacrificial soldier T, waypoints [T, T] (the second
        waypoint on the same tile aims at the floor)
        launch_right_hand-fired   >= 1 explosion ev on the host since the fire, the same seqs on the client; A's bomb
                                  gone on both
        launch_right_hand-alive   A alive on both       launch_right_hand-census  census equal
        launch_right_hand-keep    H1's launcher: owner H1, slot STR_RIGHT_HAND on both
        launch_right_hand-ids     a battle_give {H1, STR_PISTOL, slot STR_BELT} pair: weaponId equal, weaponSlot
                                  STR_BELT on both
  launch_left_hand  the same with A's launcher in the LEFT hand (the AI case); cells launch_left_hand-fired / -alive /
        -census / -keep / -ids
  host_drop  a host inventory drop after the alien's shot
        host_drop-pre  V holds exactly [its launcher] on both    host_drop-drop  M's launcher owner -1, STR_GROUND,
                       M's tile
        host_drop-victim  V's launcher unchanged, V holds exactly [it]    host_drop-census  census equal
  prox_blast  a proximity blast spares the peer's floor litter (RP.MINE_* staging)
        prox_blast-fired  one prox context {actorId 8} with a prox_trigger {item G}; the walk halted `prox` on both
        prox_blast-gone  G absent on both    prox_blast-symmetric  pre-existing ids gone: host == client
        prox_blast-control  kept
  squad_blast  an alien's blaster blast at the squad (last row: it kills): the launch at H1's tile with H1 selected,
        waypoints [H1's tile, H1's tile]
        squad_blast-fired  >= 1 explosion ev on both logs and >= 1 pre-existing item other than A's bomb destroyed
                           (host)
        squad_blast-symmetric  the destroyed id sets equal    squad_blast-census  census equal
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new crash file.
Census = battle_items as {id: (type, owner, slot)}. Settle = wait_host_idle, then both censuses unchanged over 4
consecutive 1 s samples (bounded 60 s). Test-command pairs go to the CLIENT first; ids come from the command replies.

Every fixed tile is checked against its rule at run time; a staging miss prints ONE CAPTURE line and fails the row
"staging".

The boot (key 49710, dirs item_cover_host / item_cover_client): RP.bring_up_lobby_roster_pinned + drive_to_battlescape
(map seed RP.SEED_MAP), then RP.boot's checks (MAP_FP, SEATED, the one alien pinned AI-neutral, its type, reactions 0,
hash). No END TURN in this file. One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every
row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails every row "boot". Run in the
foreground to completion. ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_item_cover.py
"""

import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean  # noqa: E402
import test_reaction_prox as RP  # noqa: E402
from test_pvp_gm3 import Miss, units, pos, guarded, common, run_row, fail_all, shut  # noqa: E402
from test_client_shoot import place, set_tu_both, new_contexts  # noqa: E402
from test_seat_pacing import tab_select  # noqa: E402
from test_delta_core import both  # noqa: E402
from test_host_combat import evs_since  # noqa: E402

KEY = "49710"
A_ID = RP.A_ID                      # the only alien (Sectoid Soldier), pinned AI-neutral
C_ID = 8                            # the client's soldier
H_IDS = [10, 11, 12]                # H1 / H2 / H3: the three lowest live seat-0 soldiers (checked at boot)
T_IDS = {"launch_right_hand": 14,   # rule: highest / next highest live seat-0 soldier outside H1-H3
         "launch_left_hand": 13}
LAUNCHER, BOMB, PISTOL = "STR_BLASTER_LAUNCHER", "STR_BLASTER_BOMB", "STR_PISTOL"
RH, GROUND, BELT = "STR_RIGHT_HAND", "STR_GROUND", "STR_BELT"
SDLK_HOME = 278
# turn rows: rule open ground z 0, no unit or door within 2, Chebyshev >= 12 from A; the clockwise neighbour open too
HOST_TURN_TILE, HOST_TURN_NEIGHBOUR = (15, 19, 0), (16, 18, 0)
CLIENT_TURN_TILE = (12, 17, 0)
# launch rows: rule open ground z 0, a straight open line A -> T, Chebyshev >= 12 apart, each >= 12 from every other
# live unit, the pair nearest the map centre (launch_left_hand's pair follows launch_right_hand's T death)
LAUNCH_PINS = {"launch_right_hand": {"A": (13, 33, 0), "A_DIR": 2, "T": (25, 34, 0), "T_DIR": 6, "slot": "right"},
               "launch_left_hand": {"A": (27, 28, 0), "A_DIR": 5, "T": (15, 33, 0), "T_DIR": 1, "slot": "left"}}
LAUNCH_A_TU = 54                    # the smallest of 54 / 80 / 120 the launch accepts
FIRE_SEED = 1                       # host set_seed right before each launch
FAR = 12
# prox_blast: RP.MINE_* tiles; litter around the trigger step (4,34,0), a non-open tile swapped to the nearest open
# tile on the same row away from G (grenade (4,33) -> (3,33), flare (3,35) -> (2,35))
PROX_LITTER = ((PISTOL, (3, 33, 0)), ("STR_GRENADE", (3, 33, 0)), ("STR_MEDI_KIT", (5, 34, 0)),
               ("STR_ELECTRO_FLARE", (2, 35, 0)))
PROX_CONTROL = (PISTOL, (12, 34, 0))
# squad_blast: rule three adjacent open z 0 tiles Chebyshev >= 12 from 8 and prox_blast's tiles; A open, Chebyshev 2
# from H1 with a straight open line to H1's tile
SQUAD_TILES = ((16, 18, 0), (17, 18, 0), (18, 18, 0))
SQUAD_A, SQUAD_A_DIR = (16, 16, 0), 4
SQUAD_FIRST_S = 12.0                # the blast settle's first wait
STEP_S = 30
ROWS = (("host_turn", ("host_turn-dir", "host_turn-cost", "host_turn-common")),
        ("client_turn", ("client_turn-admit", "client_turn-dir", "client_turn-cost", "client_turn-common")),
        ("launch_right_hand", ("launch_right_hand-fired", "launch_right_hand-alive", "launch_right_hand-census",
                               "launch_right_hand-keep", "launch_right_hand-ids", "launch_right_hand-common")),
        ("launch_left_hand", ("launch_left_hand-fired", "launch_left_hand-alive", "launch_left_hand-census",
                              "launch_left_hand-keep", "launch_left_hand-ids", "launch_left_hand-common")),
        ("host_drop", ("host_drop-pre", "host_drop-drop", "host_drop-victim", "host_drop-census", "host_drop-common")),
        ("prox_blast", ("prox_blast-fired", "prox_blast-gone", "prox_blast-symmetric", "prox_blast-control",
                        "prox_blast-common")),
        ("squad_blast", ("squad_blast-fired", "squad_blast-symmetric", "squad_blast-census", "squad_blast-common")))


# ===================== probes =====================


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def items(gc):
    return {it["id"]: it for it in gc.cmd({"cmd": "battle_items"}).get("items", [])}


def census(gc):
    return {i: (it.get("type"), it.get("owner"), it.get("slot")) for i, it in items(gc).items()}


def iv(it):
    return {k: it.get(k) for k in ("type", "owner", "slot", "tx", "ty", "tz")} if it else None


def uv(u):
    return {k: (u or {}).get(k) for k in ("x", "y", "z", "direction", "tu", "health", "isOut")}


def live(host, exclude=()):
    return {i: (u["x"], u["y"], u["z"]) for i, u in units(host).items() if not u.get("isOut") and i not in exclude}


def settle(host, client, first=0.0):
    """wait_host_idle, then both censuses unchanged over 4 consecutive 1 s samples (bounded 60 s)."""
    t = time.time()
    if first:
        time.sleep(first)
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        return {"idleError": str(e)[:200]}
    prev, same = None, 0
    while time.time() - t < 60:
        now = (census(host), census(client))
        same = same + 1 if now == prev else 0
        if same >= 3:
            return {"stableS": round(time.time() - t, 1)}
        prev = now
        time.sleep(1.0)
    return {"stable": False}


def parts(gc, tiles):
    """{(x, y): (floor, westwall, northwall, object)} over the tiles' bounding box at z 0 (one tile_census)."""
    xs, ys = [p[0] for p in tiles], [p[1] for p in tiles]
    r = gc.ok({"cmd": "tile_census", "x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys), "z0": 0, "z1": 0})
    return {(t["x"], t["y"]): tuple(t["parts"][p]["mapDataID"] for p in ("floor", "westwall", "northwall", "object"))
            for t in r["tiles"] if t}


def line_tiles(a, b):
    """The z-0 tiles a straight segment between the two tile centres touches (fine sampling, corners count)."""
    ax, ay, bx, by = a[0] + 0.5, a[1] + 0.5, b[0] + 0.5, b[1] + 0.5
    n = int(max(abs(bx - ax), abs(by - ay)) * 16) + 1
    out = set()
    for i in range(n + 1):
        x, y = ax + (bx - ax) * i / n, ay + (by - ay) * i / n
        for ex in (-0.01, 0.01):
            for ey in (-0.01, 0.01):
                out.add((math.floor(x + ex), math.floor(y + ey)))
    return sorted(out)


def need(ok, msg):
    if not ok:
        raise AssertionError(msg)
    return True


def check_open(host, client, tiles, units_off=(), far=None):
    """The tile rule at run time: every tile floor + no wall / object and equal on both machines; no live z-0 unit
    (outside `units_off`) on any tile; with `far` = (ids, d, ends, z0only), each of `ends` Chebyshev >= d from every
    live unit outside `ids` (only z-0 units when z0only). Raises AssertionError naming every miss."""
    ph, pc = parts(host, tiles), parts(client, tiles)
    bad = [(p, ph.get(p[:2]), pc.get(p[:2])) for p in tiles
           if ph.get(p[:2]) != pc.get(p[:2]) or ph.get(p[:2]) is None or ph[p[:2]][0] == -1
           or ph[p[:2]][1:] != (-1, -1, -1)]
    lv = live(host)
    occ = sorted((i, q) for i, q in lv.items() if i not in units_off and q[2] == 0
                 and any(q[:2] == p[:2] for p in tiles))
    near = []
    if far:
        ids, d, ends, z0 = far
        near = sorted((i, q) for i, q in lv.items() if i not in ids and (q[2] == 0 or not z0)
                      and any(cheb(p, q) < d for p in ends))
    need(not bad and not occ and not near,
         f"tiles not open / unequal {bad}, occupied {occ}, live units nearer than the rule {near}")
    return {"tiles": len(tiles)}


def fire_launch(host, client, wid, target, sel, first=0.0):
    """Host: select `sel`, set_seed FIRE_SEED, battle_fire {A, launch, waypoints [target, target], keepSelection}."""
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    cc0 = event_state(host).get("closedContexts") or []
    host.ok({"cmd": "battle_action", "action": "select", "unit": sel})
    selected = battle_state(host).get("selectedId")
    host.ok({"cmd": "set_seed", "seed": FIRE_SEED})
    wp = {"x": target[0], "y": target[1], "z": target[2]}
    rep = host.cmd({"cmd": "battle_fire", "unit": A_ID, "mode": "launch", "weapon_id": wid, "tu": LAUNCH_A_TU,
                    "waypoints": [wp, wp], "keepSelection": True})
    st = settle(host, client, first)
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    return {"selected": selected, "reply": {k: rep.get(k) for k in ("ok", "error", "tuCost", "ammoId")},
            "settle": st, "hostEvs": [(e["seq"], e["kind"]) for e in hev],
            "clientEvs": [(e["seq"], e["kind"]) for e in cev],
            "explHost": [e["seq"] for e in hev if e["kind"] == "explosion"],
            "explClient": [e["seq"] for e in cev if e["kind"] == "explosion"],
            "newCtx": [{k: c.get(k) for k in ("origin", "kind", "actorId")}
                       for c in new_contexts(cc0, event_state(host).get("closedContexts") or [])]}


def give(host, client, uid, item, slot, ammo=None, clear=True):
    req = {"cmd": "battle_give", "unit": uid, "item": item, "slot": slot, "clear_hands": clear}
    if ammo:
        req["ammo"] = ammo
    r = both(host, client, req, ("weaponId", "ammoId", "weaponSlot"))
    return r["weaponId"], r["ammoId"]


def drop(host, client, t, item, **kw):
    req = dict({"cmd": "battle_drop", "x": t[0], "y": t[1], "z": t[2], "item": item}, **kw)
    return both(host, client, req, ("ids",))["ids"]


def set_a_tu(host, client):
    return both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu",
                               "value": LAUNCH_A_TU, "refill": True}, ("tu",)).get("tu")


# ===================== rows =====================


def row_host_turn(host, client, crash0):
    h1, m = H_IDS[0], (host, client)
    ev = {"rule": guarded("host_turn staging",
                          lambda: check_open(host, client, [HOST_TURN_TILE, HOST_TURN_NEIGHBOUR], (h1,),
                                             ((h1,), 3, [HOST_TURN_TILE], True)), m)}
    guarded("host_turn staging",
            lambda: need(cheb(HOST_TURN_TILE, pos(host, A_ID)) >= FAR, f"A at {pos(host, A_ID)}"), m)
    ev["place"] = guarded("host_turn staging", lambda: place(host, client, h1, HOST_TURN_TILE, 0), m)
    guarded("host_turn staging", lambda: set_tu_both(host, client, h1, 255), m)
    u0 = [units(host)[h1], units(client)[h1]]
    assert tab_select(host, h1), f"the host's TAB never selected {h1}"
    host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
    time.sleep(0.15)
    pr = host.cmd({"cmd": "map_tile_click_pos", "x": HOST_TURN_NEIGHBOUR[0], "y": HOST_TURN_NEIGHBOUR[1],
                   "z": HOST_TURN_NEIGHBOUR[2]})
    assert pr.get("verified"), f"map_tile_click_pos {HOST_TURN_NEIGHBOUR} not verified: {pr}"
    host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "right"})
    t = time.time()
    while time.time() - t < 15 and units(host)[h1].get("direction") == u0[0].get("direction"):
        time.sleep(0.1)
    ev["settle"] = settle(host, client)
    u1 = [units(host)[h1], units(client)[h1]]
    cost = [u0[i].get("tu") - u1[i].get("tu") for i in (0, 1)]
    ev.update(before=[uv(u) for u in u0], after=[uv(u) for u in u1], cost=cost)
    dirs = [u.get("direction") for u in u1]
    return {"host_turn-dir": (dirs == [1, 1], f"H1 {h1} direction host/client {dirs} (want [1, 1])"),
            "host_turn-cost": (cost == [1, 1], f"H1 TU before - after host/client {cost} (want [1, 1])"),
            "host_turn-common": common(host, client, crash0)}, ev


def row_client_turn(host, client, crash0):
    m = (host, client)
    nb = (CLIENT_TURN_TILE[0] + 1, CLIENT_TURN_TILE[1] - 1, 0)
    ev = {"rule": guarded("client_turn staging", lambda: check_open(host, client, [CLIENT_TURN_TILE, nb], (C_ID,),
                                                                    ((C_ID,), 3, [CLIENT_TURN_TILE], True)), m)}
    guarded("client_turn staging",
            lambda: need(cheb(CLIENT_TURN_TILE, pos(host, A_ID)) >= FAR, f"A at {pos(host, A_ID)}"), m)
    ev["place"] = guarded("client_turn staging", lambda: place(host, client, C_ID, CLIENT_TURN_TILE, 0), m)
    guarded("client_turn staging", lambda: set_tu_both(host, client, C_ID, 255), m)
    u0 = [units(host)[C_ID], units(client)[C_ID]]
    cc0 = event_state(host).get("closedContexts") or []
    ev["intent"] = client.cmd({"cmd": "battle_intent", "kind": "turn", "actor": C_ID, "toDir": 1})
    t = time.time()
    while time.time() - t < 15 and [units(g)[C_ID].get("direction") for g in m] != [1, 1]:
        time.sleep(0.1)
    ev["settle"] = settle(host, client)
    u1 = [units(host)[C_ID], units(client)[C_ID]]
    cost = [u0[i].get("tu") - u1[i].get("tu") for i in (0, 1)]
    new = [{k: c.get(k) for k in ("origin", "kind", "actorId")}
           for c in new_contexts(cc0, event_state(host).get("closedContexts") or [])]
    dirs = [u.get("direction") for u in u1]
    ev.update(before=[uv(u) for u in u0], after=[uv(u) for u in u1], cost=cost, newCtx=new)
    want = [{"origin": "intent", "kind": "turn", "actorId": C_ID}]
    return {"client_turn-admit": (new == want, f"new host contexts {new} (want {want})"),
            "client_turn-dir": (dirs == [1, 1], f"8 direction host/client {dirs} (want [1, 1])"),
            "client_turn-cost": (cost == [1, 1], f"8 TU before - after host/client {cost} (want [1, 1])"),
            "client_turn-common": common(host, client, crash0)}, ev


def row_launch(host, client, crash0, row):
    h1, t_id, pin, m, tag = H_IDS[0], T_IDS[row], LAUNCH_PINS[row], (host, client), f"{row} staging"
    a_t, t_t = pin["A"], pin["T"]
    path = [(p[0], p[1], 0) for p in line_tiles(a_t, t_t)]
    ev = {"T": t_id, "A_tile": a_t, "T_tile": t_t, "dist": cheb(a_t, t_t)}
    ev["rule"] = guarded(tag, lambda: check_open(host, client, path, (A_ID, t_id),
                                                 ((A_ID, t_id), FAR, [a_t, t_t], False)), m)
    guarded(tag, lambda: need(cheb(a_t, t_t) >= FAR and not units(host)[t_id].get("isOut"),
                              f"T {t_id} out or the pair nearer than {FAR}"), m)
    hw, hb = guarded(tag, lambda: give(host, client, h1, LAUNCHER, "right", BOMB), m)
    aw, ab = guarded(tag, lambda: give(host, client, A_ID, LAUNCHER, pin["slot"], BOMB), m)
    guarded(tag, lambda: place(host, client, A_ID, a_t, pin["A_DIR"]), m)
    guarded(tag, lambda: place(host, client, t_id, t_t, pin["T_DIR"]), m)
    ev.update(H1=(hw, hb), A=(aw, ab), Atu=guarded(tag, lambda: set_a_tu(host, client), m))
    pre_h, pre_c = census(host), census(client)
    guarded(tag, lambda: need(pre_h == pre_c, "census differs before the fire"), m)
    ev["fire"] = f = fire_launch(host, client, aw, t_t, t_id)
    ih, ic = items(host), items(client)
    uh, uc = units(host), units(client)
    alive = [not uh[A_ID].get("isOut"), not uc[A_ID].get("isOut")]
    keep = [iv(ih.get(hw)), iv(ic.get(hw))]
    ev.update(Aafter=[uv(uh[A_ID]), uv(uc[A_ID])], Tafter=[uv(uh.get(t_id)), uv(uc.get(t_id))],
              goneHost=sorted(set(pre_h) - set(ih)), goneClient=sorted(set(pre_c) - set(ic)))
    eq = census(host) == census(client)
    ids = both(host, client, {"cmd": "battle_give", "unit": h1, "item": PISTOL, "slot": BELT},
               ("weaponId", "weaponSlot"))
    ev["ids"] = {k: ids.get(k) for k in ("weaponId", "weaponSlot")}
    fired = bool(f["explHost"]) and f["explHost"] == f["explClient"] and ab not in ih and ab not in ic
    return {f"{row}-fired": (fired, f"explosion seqs host {f['explHost']} client {f['explClient']} (want >= 1, "
                                    f"equal); A's bomb {ab} present host/client {[ab in ih, ab in ic]} (want "
                                    f"[False, False]); host evs {f['hostEvs']}"),
            f"{row}-alive": (all(alive), f"A alive host/client {alive} (want [True, True])"),
            f"{row}-census": (eq, f"census equal after the row: {eq}"),
            f"{row}-keep": (all(k and k["owner"] == h1 and k["slot"] == RH for k in keep),
                            f"H1's launcher {hw} host/client {keep} (want owner {h1}, slot {RH})"),
            f"{row}-ids": (ids.get("weaponSlot") == BELT, f"pistol give {ev['ids']} (weaponId equal on both by the "
                                                          f"pair; want weaponSlot {BELT})"),
            f"{row}-common": common(host, client, crash0)}, ev


def row_host_drop(host, client, crash0):
    v, mm, m = H_IDS[1], H_IDS[2], (host, client)
    vl = guarded("host_drop staging", lambda: give(host, client, v, LAUNCHER, "right"), m)[0]
    ml = guarded("host_drop staging", lambda: give(host, client, mm, LAUNCHER, "right"), m)[0]
    ev = {"V": (v, vl), "M": (mm, ml), "Mtile": pos(host, mm)}

    def hands(gc):
        return sorted(i for i, it in items(gc).items()
                      if it.get("owner") == v and it.get("slot") in (RH, "STR_LEFT_HAND"))
    pre = [hands(host), hands(client)]
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    ev["open"] = host.cmd({"cmd": "battle_open_inventory", "unit": mm}).get("opened")
    time.sleep(0.3)
    host.cmd({"cmd": "inventory_click", "slot": RH})
    t = time.time()
    while time.time() - t < 5 and host.cmd({"cmd": "inventory_view"}).get("selectedItem") != ml:
        time.sleep(0.05)
    ev["picked"] = host.cmd({"cmd": "inventory_view"}).get("selectedItem")
    host.cmd({"cmd": "inventory_click", "slot": GROUND, "x": 0, "y": 0})
    t = time.time()
    while time.time() - t < 5 and host.cmd({"cmd": "inventory_view"}).get("selectedItem") != -1:
        time.sleep(0.05)
    host.cmd({"cmd": "battle_close_inventory"})
    t = time.time()
    while time.time() - t < 5 and "InventoryState" in session.states_stripped(host):
        time.sleep(0.05)
    ev["settle"] = settle(host, client)
    ih, ic = items(host), items(client)
    mlv, vlv = [iv(ih.get(ml)), iv(ic.get(ml))], [iv(ih.get(vl)), iv(ic.get(vl))]
    post = [hands(host), hands(client)]
    ev.update(Mlauncher=mlv, Vlauncher=vlv, hostEvs=[(e["seq"], e["kind"]) for e in evs_since(host, seq0)])
    eq = census(host) == census(client)
    drop_ok = all(x and x["owner"] == -1 and x["slot"] == GROUND and (x["tx"], x["ty"], x["tz"]) == ev["Mtile"]
                  for x in mlv)
    return {"host_drop-pre": (pre == [[vl], [vl]], f"V {v} hands host/client {pre} (want [[{vl}], [{vl}]])"),
            "host_drop-drop": (drop_ok,
                               f"M's launcher {ml} host/client {mlv} (want owner -1, {GROUND}, {ev['Mtile']})"),
            "host_drop-victim": (all(x and x["owner"] == v and x["slot"] == RH for x in vlv) and post == [[vl], [vl]],
                                 f"V's launcher {vl} host/client {vlv}; V hands {post} "
                                 f"(want owner {v}, {RH}, only it)"),
            "host_drop-census": (eq, f"census equal after the drop: {eq}"),
            "host_drop-common": common(host, client, crash0)}, ev


def row_prox_blast(host, client, crash0):
    m, tag = (host, client), "prox_blast staging"
    tiles = [t for _, t in PROX_LITTER] + [PROX_CONTROL[1]]
    ev = {"rule": guarded(tag, lambda: check_open(host, client, tiles), m)}
    guarded(tag, lambda: both(host, client, {"cmd": "battle_set_unit_state", "unit": C_ID, "health": RP.C_MAX_HEALTH,
                                             "tu": RP.TU_MAX}, ("health", "tu")), m)
    guarded(tag, lambda: place(host, client, C_ID, RP.MINE_C_TILE, RP.MINE_C_DIR), m)
    g = guarded(tag, lambda: drop(host, client, RP.MINE_TILE, "STR_PROXIMITY_GRENADE", prime=True, fuse=0), m)
    gid = g[0] if g else None
    lit = {it + "@" + str(t): guarded(tag, lambda: drop(host, client, t, it), m)[0] for it, t in PROX_LITTER}
    ctrl = guarded(tag, lambda: drop(host, client, PROX_CONTROL[1], PROX_CONTROL[0]), m)[0]
    pre_h, pre_c = census(host), census(client)
    guarded(tag, lambda: need(pre_h == pre_c and len(g) == 1, f"census differs or grenade ids {g}"), m)
    notes = []
    rec = RP.client_walk(host, client, RP.MINE_SEED, RP.MINE_DEST, notes)
    ev["settle"] = settle(host, client)
    post_h, post_c = census(host), census(client)
    gone_h, gone_c = sorted(set(pre_h) - set(post_h)), sorted(set(pre_c) - set(post_c))
    pctx = [c for c in rec["closed"] if c.get("origin") == "prox"]
    trig = [RP.payload(rec, e) for e in rec["hev"] if e["kind"] == "prox_trigger"]
    halted = [RP.restate_of(rec["hw"]), RP.restate_of(rec["cw"])]
    ev.update(G=gid, litter=lit, control=ctrl, notes=notes, prox=pctx, trig=trig, halted=halted, goneHost=gone_h,
              goneClient=gone_c, fates={k: i in post_h for k, i in lit.items()})
    fired = (len(pctx) == 1 and pctx[0].get("actorId") == C_ID and [t.get("item") for t in trig] == [gid]
             and all(h[0] and h[1] == "prox" for h in halted))
    return {"prox_blast-fired": (fired, f"prox contexts {pctx} (want one, actorId {C_ID}); prox_trigger payloads "
                                        f"{trig} (want item {gid}); halted host/client {halted} (want reason prox); "
                                        f"notes {notes}"),
            "prox_blast-gone": (gid not in post_h and gid not in post_c,
                                f"G {gid} present host/client {[gid in post_h, gid in post_c]} (want none)"),
            "prox_blast-symmetric": (gone_h == gone_c, f"ids gone host {gone_h} client {gone_c} (want equal)"),
            "prox_blast-control": (ctrl in post_h and ctrl in post_c,
                                   f"control {ctrl} present host/client {[ctrl in post_h, ctrl in post_c]} "
                                   f"(want both)"),
            "prox_blast-common": common(host, client, crash0)}, ev


def row_squad_blast(host, client, crash0):
    m, tag, h = (host, client), "squad_blast staging", H_IDS
    prox_tiles = [RP.MINE_C_TILE, RP.MINE_TILE, RP.MINE_DEST, (4, 34, 0)] + [t for _, t in PROX_LITTER]
    path = [(p[0], p[1], 0) for p in line_tiles(SQUAD_A, SQUAD_TILES[0])]
    ev = {"rule": guarded(tag, lambda: check_open(host, client, sorted(set(path) | set(SQUAD_TILES)),
                                                  tuple(h) + (A_ID,)), m)}
    guarded(tag, lambda: need(cheb(SQUAD_A, SQUAD_TILES[0]) == 2 and all(cheb(t, q) >= FAR for t in SQUAD_TILES
                                                                         for q in prox_tiles + [pos(host, C_ID)]),
                              f"squad_blast tiles nearer than {FAR} to 8 ({pos(host, C_ID)}) or prox_blast's tiles"), m)
    for uid, t in zip(h, SQUAD_TILES):
        guarded(tag, lambda: place(host, client, uid, t, 0), m)
    ev["arms"] = [guarded(tag, lambda: give(host, client, uid, LAUNCHER, "left", BOMB), m) for uid in h]
    ev["loose"] = [guarded(tag, lambda: drop(host, client, t, LAUNCHER), m)[0] for t in SQUAD_TILES]
    guarded(tag, lambda: place(host, client, A_ID, SQUAD_A, SQUAD_A_DIR), m)
    aw, ab = guarded(tag, lambda: give(host, client, A_ID, LAUNCHER, "right", BOMB), m)
    ev.update(A=(aw, ab), Atu=guarded(tag, lambda: set_a_tu(host, client), m))
    pre_h, pre_c = census(host), census(client)
    guarded(tag, lambda: need(pre_h == pre_c, "census differs before the fire"), m)
    ev["fire"] = f = fire_launch(host, client, aw, SQUAD_TILES[0], h[0], first=SQUAD_FIRST_S)
    post_h, post_c = census(host), census(client)
    gone_h, gone_c = sorted(set(pre_h) - set(post_h)), sorted(set(pre_c) - set(post_c))
    other = [i for i in gone_h if i != ab]
    ev.update(goneHost=gone_h, goneClient=gone_c, otherGone=other,
              out=sorted(i for i, u in units(host).items() if u.get("isOut")))
    fired = bool(f["explHost"]) and bool(f["explClient"]) and len(other) >= 1
    return {"squad_blast-fired": (fired, f"explosion seqs host {f['explHost']} client {f['explClient']} (want >= 1 "
                                         f"each); pre-existing items destroyed on the host other than A's bomb {ab}: "
                                         f"{other} (want >= 1)"),
            "squad_blast-symmetric": (gone_h == gone_c, f"destroyed ids host {gone_h} client {gone_c} (want equal)"),
            "squad_blast-census": (post_h == post_c, f"census equal after the blast: {post_h == post_c}"),
            "squad_blast-common": common(host, client, crash0)}, ev


# ===================== boot =====================


def boot_battle(host, client):
    """A copy of RP.boot's body on KEY, plus the H / T id rules."""
    RP.bring_up_lobby_roster_pinned(host, client, KEY)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": RP.SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    fp = [hs.get("mapFingerprint"), cs.get("mapFingerprint")]
    assert fp == [RP.MAP_FP, RP.MAP_FP], f"mapFingerprint host/client {fp} (want {RP.MAP_FP})"
    assert seated.get("soldierIds") == RP.SEATED, f"seated {seated.get('soldierIds')} (want {RP.SEATED})"
    pinned = pin_ai_neutral(host, client, tag="item-cover")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (want [{A_ID}])"
    types = [(units(g).get(A_ID) or {}).get("type") for g in (host, client)]
    assert types == [RP.A_TYPE, RP.A_TYPE], f"A {A_ID} type host/client {types} (want {RP.A_TYPE})"
    for uid, u in sorted(units(host).items()):
        if u.get("faction") == RP.FACTION_PLAYER and not u.get("isOut"):
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
    seat0 = sorted(i for i, u in units(host).items() if u.get("coop") == 0 and u.get("faction") == RP.FACTION_PLAYER
                   and not u.get("isOut"))
    rest = sorted((i for i in seat0 if i not in seat0[:3]), reverse=True)
    assert seat0[:3] == H_IDS and rest[:2] == [T_IDS["launch_right_hand"], T_IDS["launch_left_hand"]], (
        f"live seat-0 soldiers {seat0} (want H {H_IDS}, T {T_IDS} by the rule)")
    session.wait_host_idle(host, client, timeout=STEP_S)
    assert_hash_clean(host, client, full=True, what="boot")
    return {"seated": seated.get("soldierIds"), "pinned": pinned, "seat0": seat0}


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("item_cover_host"))
    client = GameClient("client", None, make_user_dir("item_cover_client"))
    fails = 0
    try:
        crash0 = session._crash_log_snapshot()
        try:
            info = guarded("boot", lambda: boot_battle(host, client), (host, client))
            print(f"[item_cover] boot ok: {info}", flush=True)
        except Miss:
            fails = fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        else:
            fns = {"host_turn": lambda: row_host_turn(host, client, crash0),
                   "client_turn": lambda: row_client_turn(host, client, crash0),
                   "launch_right_hand": lambda: row_launch(host, client, crash0, "launch_right_hand"),
                   "launch_left_hand": lambda: row_launch(host, client, crash0, "launch_left_hand"),
                   "host_drop": lambda: row_host_drop(host, client, crash0),
                   "prox_blast": lambda: row_prox_blast(host, client, crash0),
                   "squad_blast": lambda: row_squad_blast(host, client, crash0)}
            for row, order in ROWS:   # a staging miss (its CAPTURE line printed) fails the row's cells unreached
                fails += run_row(row, order, fns[row])
    finally:
        shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_item_cover: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
