"""SPEC RW-S4 (REV E.33 + REV E.45 amendment) PRECALC. NOT a regression member.

One-time orchestrator measurement (R1/R5): finds the pinned SEED and the baked
FORMATION that `repro_atom_walk` will teleport its seven soldiers onto, so the
test needs no runtime search. Boots the SAME two-instance skirmish fixture the
test uses, `set_seed(seed)` on the host right before `newbattle_ok` (via
`session.drive_to_battlescape(pre_ok=...)`), records `mapFingerprint`, applies
the WV-D88 corner placement through `session.stage_open_ground_actor` (hostiles
-> farthest corner, neutrals -> opposite; hash-gated), then:

  (1) OLD fixture: stages the actor exactly as the old file does, finds the unit
      the old `richest()` take() would pick next, and reports whether that unit's
      eight neighbours at its z are all occupied-or-no-floor -> OLD_ENCLOSED
      (the S4 TRACE's red mechanism, reproduced by seed).
  (2) NEW fixture: searches for a FORMATION of `--lanes` (7) parallel lanes at ONE
      z, ONE direction D, spaced `--spacing` (2) apart, each lane `--lane-len`
      (11) consecutive open tiles from the start onward with the tile BEHIND the
      start also open. Every lane tile: floor present, unoccupied after the
      corner placement, no door part within WALK_DOOR_RADIUS (5) at that z, and
      >= contact_min (MAX_VIEW_DISTANCE + WALK_CONTACT_MARGIN + 1 = 25) from every
      living non-player unit. Fixed scan order: z from the soldiers' own z first,
      then D in (E,S,W,N), then anchors rows-then-columns; first placement wins.

The first seed with a formation wins. Exit 0 = formation found (prints the
constants block); exit 2 = no formation in the seed budget (STOP-IF: the owner
relaxes spacing / lane length / z, or widens the budget).

Example:
  python tools/coop_test/precalc_walk_fixture.py --seeds 40 --lane-len 11 --spacing 2
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import repro_atom_walk as W  # noqa: E402

COOP_SEAT_0 = 0
COOP_SEAT_1 = 1
# Fixed lane-direction scan order: East, South, West, North.
DIRS = [("E", (1, 0)), ("S", (0, 1)), ("W", (-1, 0)), ("N", (0, -1))]


def unit_pos(u):
    return (u["x"], u["y"], u["z"])


def non_players(st):
    return [u for u in st.get("units", [])
            if u.get("faction") != session.FACTION_PLAYER and not u.get("isOut")]


def build_open_predicate(host, st, mx, my, lane_len, spacing, contact_min,
                         door_radius):
    """Returns open_tile(x,y,z) with a per-tile tile_info cache and a dilated
    door set. Only the tiles the formation search actually touches are queried."""
    occupied = {unit_pos(u) for u in st.get("units", []) if not u.get("isOut")}
    npc = [(u["x"], u["y"], u["z"]) for u in non_players(st)]

    dr = host.cmd({"cmd": "find_doors", "limit": 4096})
    assert dr.get("ok"), "find_doors failed: %r" % dr
    door_tiles = {(d["x"], d["y"], d["z"]) for d in dr.get("doors", [])}

    floor_cache = {}

    def has_floor(x, y, z):
        key = (x, y, z)
        v = floor_cache.get(key)
        if v is None:
            ti = host.cmd({"cmd": "tile_info", "x": x, "y": y, "z": z})
            v = bool(ti.get("ok")
                     and ti.get("parts", {}).get("floor", {}).get("mapDataID", -1) >= 0)
            floor_cache[key] = v
        return v

    def door_near(x, y, z):
        for dx in range(-door_radius, door_radius + 1):
            for dy in range(-door_radius, door_radius + 1):
                if (x + dx, y + dy, z) in door_tiles:
                    return True
        return False

    def contact_free(x, y, z):
        for (ax, ay, az) in npc:
            if ((ax - x) ** 2 + (ay - y) ** 2 + (az - z) ** 2) < contact_min * contact_min:
                return False
        return True

    def open_tile(x, y, z):
        if x < 0 or y < 0 or x >= mx or y >= my:
            return False
        if (x, y, z) in occupied:
            return False
        if not contact_free(x, y, z):        # cheap, no round trip
            return False
        if door_near(x, y, z):               # cheap, set lookup
            return False
        return has_floor(x, y, z)            # the only round trip, cached

    return open_tile, floor_cache


def lane_ok(open_tile, sx, sy, z, d, lane_len):
    """A lane starting at (sx,sy): back tile (k=-1) plus k=0..lane_len-1 forward,
    all open."""
    dx, dy = d
    if not open_tile(sx - dx, sy - dy, z):   # the back tile
        return False
    for k in range(0, lane_len):
        if not open_tile(sx + dx * k, sy + dy * k, z):
            return False
    return True


def search_formation(open_tile, mx, my, z_order, lanes, spacing, lane_len):
    """Fixed scan order: z (soldiers' z first), then D in DIRS, then anchors
    rows-then-columns. Returns (z, d_name, d, formation[list of (x,y)]) or None."""
    for z in z_order:
        for d_name, d in DIRS:
            dx, dy = d
            px, py = -dy, dx                  # 90-degree perpendicular (lane stacking)
            for ay in range(0, my):           # rows outer
                for ax in range(0, mx):       # columns inner
                    starts = [(ax + px * spacing * i, ay + py * spacing * i)
                              for i in range(lanes)]
                    if all(0 <= sx < mx and 0 <= sy < my for sx, sy in starts) and \
                       all(lane_ok(open_tile, sx, sy, z, d, lane_len) for sx, sy in starts):
                        return z, d_name, d, starts
    return None


def old_enclosed(host, client, soldier_ids):
    """Stage the actor exactly as the old fixture does (WV-D88 corner placement +
    ring scan), then check whether the unit the old take()/richest would pick
    next is enclosed (all eight neighbours occupied-or-no-floor). Returns
    (verdict, detail). verdict True/False, or None when staging itself failed
    (the old file would exit 3 FIXTURE, not a red-by-enclosure)."""
    try:
        after, tile, run_dir = session.stage_open_ground_actor(
            host, client, [soldier_ids[0]], "precalc",
            door_radius=W.WALK_DOOR_RADIUS,
            contact_min=session.MAX_VIEW_DISTANCE + W.WALK_CONTACT_MARGIN + 1,
            need_weapon=True, run_length=W.WALK_RUN)
    except AssertionError as e:
        if str(e).startswith("FIXTURE"):
            return None, {"stage": "FIXTURE: " + str(e)[:120]}
        raise
    actor_id = after["id"]
    st = session.battle_state(host)
    units = {u["id"]: u for u in st["units"]}
    client_ids = [u["id"] for u in st["units"]
                  if u.get("coop") == COOP_SEAT_1 and not u.get("isOut")]
    take = W.richest(host, client_ids, 1, exclude={actor_id})
    if not take:
        return None, {"stage": "no take() unit available"}
    tu = units[take[0]]
    tx, ty, tz = tu["x"], tu["y"], tu["z"]
    occupied = {unit_pos(u) for u in st["units"] if not u.get("isOut")}
    free = 0
    neigh = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = tx + dx, ty + dy
            occ = (nx, ny, tz) in occupied
            ti = host.cmd({"cmd": "tile_info", "x": nx, "y": ny, "z": tz})
            floor = bool(ti.get("ok")
                         and ti.get("parts", {}).get("floor", {}).get("mapDataID", -1) >= 0)
            blocked = occ or not floor
            neigh.append(((nx, ny), "occ" if occ else ("nofloor" if not floor else "FREE")))
            if not blocked:
                free += 1
    enclosed = (free == 0)
    return enclosed, {"take_unit": take[0], "take_pos": (tx, ty, tz),
                      "free_neighbours": free, "actor_id": actor_id,
                      "actor_tile": tile, "neigh": neigh}


def evaluate_seed(n, lanes, spacing, lane_len, seat_count, scan_formation=True):
    port = str(48700 + n)
    host = GameClient("precalc-host", 49700 + n * 2, make_user_dir(f"precalc_walk_host_{n}"))
    client = GameClient("precalc-client", 49701 + n * 2, make_user_dir(f"precalc_walk_client_{n}"))
    seated = {}
    row = {"seed": n}
    try:
        W.bring_up_lobby(host, client, port)
        try:
            session.drive_to_battlescape(
                host, client, seated, seat_count=seat_count,
                pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": n}))
        except TimeoutError as e:
            row.update(boot="TIMEOUT", error=str(e)[:140])
            return row
        st0 = session.battle_state(host)
        row["mapFingerprint"] = st0.get("mapFingerprint")
        row["mapSizeXYZ"] = st0.get("mapSizeXYZ")
        client_ids0 = [u["id"] for u in st0["units"]
                       if u.get("coop") == COOP_SEAT_1 and not u.get("isOut")]
        host_ids0 = [u["id"] for u in st0["units"]
                     if u.get("coop") == COOP_SEAT_0 and u.get("isPlayerSoldier")
                     and not u.get("isOut")]
        row["client_units"] = len(client_ids0)
        row["host_units"] = len(host_ids0)
        soldier_ids = seated.get("soldierIds", [])

        # (1) OLD_ENCLOSED (also performs the WV-D88 corner placement).
        enc, enc_detail = old_enclosed(host, client, soldier_ids)
        row["OLD_ENCLOSED"] = enc
        row["old_detail"] = enc_detail

        # (2) NEW FORMATION on the post-corner-placement state.
        st = session.battle_state(host)
        dr = host.cmd({"cmd": "find_doors", "limit": 1})
        mx, my = dr["mapSizeX"], dr["mapSizeY"]
        mapz = st["mapSizeXYZ"] // (mx * my)
        row["map"] = (mx, my, mapz)
        if not scan_formation:
            # SEED already found; the first formation wins, so later seeds skip
            # the (expensive) scan and only carry OLD_ENCLOSED for the red hunt.
            row["formation"] = None
            row["scanned"] = False
            row["scan_s"] = 0.0
            row["tiles_probed"] = 0
            return row
        row["scanned"] = True
        players = [u for u in st["units"]
                   if u.get("faction") == session.FACTION_PLAYER and not u.get("isOut")]
        # soldiers' own z first, then the rest ascending.
        zs = sorted({u["z"] for u in players})
        z_from_mode = max(zs, key=lambda zz: sum(1 for u in players if u["z"] == zz)) if zs else 0
        z_order = [z_from_mode] + [z for z in range(mapz) if z != z_from_mode]
        contact_min = session.MAX_VIEW_DISTANCE + W.WALK_CONTACT_MARGIN + 1
        open_tile, cache = build_open_predicate(
            host, st, mx, my, lane_len, spacing, contact_min, W.WALK_DOOR_RADIUS)
        t0 = time.time()
        res = search_formation(open_tile, mx, my, z_order, lanes, spacing, lane_len)
        row["scan_s"] = round(time.time() - t0, 1)
        row["tiles_probed"] = len(cache)
        row["map"] = (mx, my, mapz)
        row["soldier_z"] = z_from_mode
        if res is not None:
            z, d_name, d, starts = res
            row["formation"] = {"z": z, "d_name": d_name, "d": d,
                                "starts": [(int(sx), int(sy)) for sx, sy in starts]}
        else:
            row["formation"] = None
        return row
    finally:
        host.shutdown()
        client.shutdown()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--lane-len", type=int, default=11)
    ap.add_argument("--spacing", type=int, default=2)
    ap.add_argument("--lanes", type=int, default=7)
    ap.add_argument("--seat-count", type=int, default=5)
    ap.add_argument("--stop-early", action="store_true",
                    help="stop once BOTH a formation seed and an OLD_ENCLOSED seed are found")
    a = ap.parse_args()

    rows = []
    seed_found = None
    red_found = None
    print(f"[precalc] lanes={a.lanes} lane_len={a.lane_len} spacing={a.spacing} "
          f"seat_count={a.seat_count} seeds=1..{a.seeds}", flush=True)
    for n in range(1, a.seeds + 1):
        row = evaluate_seed(n, a.lanes, a.spacing, a.lane_len, a.seat_count,
                            scan_formation=(seed_found is None))
        rows.append(row)
        fp = row.get("mapFingerprint")
        enc = row.get("OLD_ENCLOSED")
        form = row.get("formation")
        form_str = "FOUND" if form else ("none" if row.get("scanned") else "skip")
        print(f"seed {n:>2}: boot={row.get('boot','ok')} fp={fp} "
              f"map={row.get('map')} clients={row.get('client_units')} "
              f"hosts={row.get('host_units')} OLD_ENCLOSED={enc} "
              f"formation={form_str} "
              f"scan={row.get('scan_s')}s probed={row.get('tiles_probed')}",
              flush=True)
        if form and seed_found is None:
            seed_found = row
        if enc is True and red_found is None:
            red_found = n
        if a.stop_early and seed_found is not None and red_found is not None:
            print("[precalc] stop-early: have SEED and RED_SEED", flush=True)
            break

    print("\n==== PER-SEED TABLE ====", flush=True)
    print(f"{'seed':>4} {'fingerprint':>24} {'OLD_ENCLOSED':>12} {'formation':>10} "
          f"{'clients':>7} {'hosts':>5}")
    for r in rows:
        fstr = "FOUND" if r.get('formation') else ("none" if r.get('scanned') else "skip")
        print(f"{r['seed']:>4} {str(r.get('mapFingerprint')):>24} "
              f"{str(r.get('OLD_ENCLOSED')):>12} "
              f"{fstr:>10} "
              f"{str(r.get('client_units')):>7} {str(r.get('host_units')):>5}")

    print("\n==== RED_SEED ====", flush=True)
    print(f"RED_SEED = {red_found}  (first seed with OLD_ENCLOSED = True; "
          f"None means no enclosed-take() seed in the budget)")

    if seed_found is None:
        print("\n==== NO FORMATION IN BUDGET (exit 2) ====", flush=True)
        sys.exit(2)

    f = seed_found["formation"]
    starts = f["starts"]
    print("\n==== CONSTANTS BLOCK ====", flush=True)
    print("# regenerate with: python tools/coop_test/precalc_walk_fixture.py "
          f"--seeds {a.seeds} --lane-len {a.lane_len} --spacing {a.spacing}")
    print(f"SEED = {seed_found['seed']}")
    print(f"FINGERPRINT = {seed_found['mapFingerprint']!r}")
    print(f"Z = {f['z']}; D = {tuple(f['d'])}          # lane direction {f['d_name']}")
    print(f"LANE_LEN = {a.lane_len}")
    print("FORMATION = {  # slot -> (x, y) start tiles; 0-4 = client, 5-6 = host")
    cells = ", ".join(f"{i}: {tuple(starts[i])}" for i in range(len(starts)))
    print("    " + cells + ",")
    print("}")
    sys.exit(0)


if __name__ == "__main__":
    main()
