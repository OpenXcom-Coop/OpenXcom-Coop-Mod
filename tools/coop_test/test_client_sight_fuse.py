"""test_client_sight_fuse.py: at night, on the co-op second player's machine the light of a flare that glows only
while primed, an alien's `visible` flag and each X-COM soldier's list of seen units follow vanilla when the flare is
primed next to a dark alien and unprimed again (flare_prime). The second player's off-turn view follows vanilla, and
an alien no X-COM soldier sees stays hidden.

Vanilla relights at the holder and re-runs sight with the item's glow range right after a prime or an unprime
(BattlescapeGame BA_PRIME / BA_UNPRIME, the host's prime intent). The second player's machine receives the item's
fuse / fuseEnabled change; its applyDelta light pre-pass counts a fuseEnabled change as a move, so it relights the
flare where it is and re-runs the sight (connectionTCP.cpp, the pre-pass and coopClientEventSight). No stock ruleset
has such a flare: test mod Coop_FuseFlare_Test (this directory's mods/) adds STR_COOP_FUSE_FLARE (fuseType -1,
power 22), loaded on BOTH.

Fixture facts (equal in two boots): at the prime the host lights A's tile to 11 and its V lists A; a client that does
not relight stays at 5, with V's list empty and A undrawn. At the unprime, after both are lit, the host darkens to 5
and drops A; such a client stays lit at 11 and keeps A. The day cases (a kneel and a stand-up, a mind control) are in
test_client_sight_more.py; a converted unit needs no test (the client lists it at once).

ONE classic co-op NIGHT boot (lobby key 46644, user dirs client_sight_fuse_host / client_sight_fuse_client, the mod on
both), test_client_sight_night's boot (copied): test_light_scope's write_night_cfg (darkness 15) into the host's user
dir before the host starts and its night_precondition after it; SEED_ROSTER 1, SEED_MAP 1, seat_count 2,
pin_ai_neutral (A base TU 0: it never acts), reactions 0 for every X-COM unit on both. Staging (a miss fails the row
"staging"): park test_client_sight_night's PARK (T = 8 included: the row's light source stays parked until its row
places it), A to A_N facing 5, V (9) to V_N facing 5, client turn intent V -> 6; every teleport is followed by
light_recompute on both. Dark precondition: A_N units light <= DARK_MAX on both.

Row:
  flare_prime  battle_give STR_COOP_FUSE_FLARE to T (8) (clear hands; ids equal, not -1); tele T to T_TILE facing
       T_DIR (+ recompute); T TU max; client prime intent {item, fuse 5}; seq barrier.
       flare_prime-pre      before the prime: A_N units light <= 5 on both (dark); vis(A) false on both; A in
                            neither list(V); the flare in T's right hand on both, fuse -1.
       flare_prime-host     after the prime: host A_N units light > 5 and A in host list(V) (precondition: vanilla's
                            refresh).
       flare_prime-light    the client's A_N tile_light equal to the host's.
       flare_prime-here     here(client, A) true.
       flare_prime-list     A in list(client, V).
       flare_unprime-pre    after light_recompute on both and client turn intents V -> 5 -> 6: A in list(V) on both;
                            A_N lit (units > 5) on both.
       flare_unprime-host   after T TU max and client unprime intent {item, fuse -1, unprime true}, barrier: host A_N
                            units light <= 5 and A not in host list(V) (precondition).
       flare_unprime-light  the client's A_N tile_light equal to the host's.
       flare_unprime-list   A not in list(client, V).
       flare_prime-common   (hash_now full: every bucket EQUAL; event_state.desyncSeen false on both; 0 new crash
                            files).
"tile_light" = [ambient, fire, items, units] of the tile (test_light_scope's light_census); "vis" / "here" / "list" as
in test_client_sight_more.py.

A client that does not relight at a fuse change fails flare_prime-light, flare_prime-here, flare_prime-list,
flare_unprime-light and flare_unprime-list; every other cell passes. With the relight, every cell passes.

The row prints one "EVIDENCE flare_prime:" line, one PASS / FAIL line per cell and "ROW flare_prime: PASS|FAIL". A
bring-up failure prints ONE "CAPTURE boot:" line and fails every cell "boot". No skip, no second boot, no other
fixture; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_client_sight_fuse.py
"""

import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_delta_core import both
import test_light_scope as ls
import test_client_alien_sight as cas  # the per-GameClient lock (installed on import)
# the probes and staging helpers (view / snap / order / tele_rc ...) and a capture_boot shaped like
# test_client_sight_events'
import test_client_sight_more as more

# ----- fixture values (equal in two boots) -----
SEED_ROSTER, SEED_MAP = 1, 1
MAP_FP = -4.48310638993e+18
SEATED = [8, 9]
A_ID, A_TYPE = 1000000, "STR_SECTOID_SOLDIER"   # the only alien (pin_ai_neutral: base TU 0)
A_BOOT, A_BOOT_DIR = (27, 12, 0), 5
DARKNESS, DARK_MAX = 15, 5                      # battle.cfg darkness; dark: A_N units light <= 5
A_N, A_N_DIR = (20, 18, 0), 5
V_ID, T_ID = 9, 8                               # V watches (client seat), T holds the flare (client seat)
V_N, V_N_DIR0, V_N_DIR = (31, 18, 0), 5, 6
PARK = ((8, (10, 13, 0)), (12, (11, 13, 0)), (13, (10, 14, 0)), (14, (10, 15, 0)), (10, (10, 16, 0)),
        (11, (10, 17, 0)))                      # test_client_sight_night's PARK, 8 included; facing kept
T_TILE, T_DIR = (20, 29, 0), 4                  # the first candidate tile: Round(distance) 11 from A_N, facing away
FLARE, FUSE = "STR_COOP_FUSE_FLARE", 5
MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_FuseFlare_Test")
KEY = "46644"                                   # this file's lobby key

ROWS = (("flare_prime", ("flare_prime-pre", "flare_prime-host", "flare_prime-light", "flare_prime-here",
                         "flare_prime-list", "flare_unprime-pre", "flare_unprime-host", "flare_unprime-light",
                         "flare_unprime-list", "flare_prime-common")),)
RESULTS = {}
CRASH0 = set()
STAGED = {"ok": None, "detail": ""}
_BUF = {"ev": [], "lines": []}
short, uu, pair, at = cas.short, more.uu, more.pair, more.at
AK = f"{A_N[0]},{A_N[1]},{A_N[2]}"


def ev(text):
    _BUF["ev"].append(text)


def cell(name, ok, detail):
    RESULTS[name] = bool(ok)
    _BUF["lines"].append(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")


def flush_row(row, cells):
    print(f"EVIDENCE {row}: {' || '.join(_BUF['ev'])}", flush=True)
    for line in _BUF["lines"]:
        print(line, flush=True)
    print(f"ROW {row}: {'PASS' if all(RESULTS.get(c) for c in cells) else 'FAIL'}", flush=True)
    _BUF["ev"], _BUF["lines"] = [], []


def crash_files():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))


def common(host, client, row):
    try:
        assert_hash_clean(host, client, full=True, what=f"client_sight_fuse {row}")
        h = "EQUAL"
    except AssertionError as e:
        h = str(e)[:600]
    ds = (event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen"))
    new = sorted(crash_files() - CRASH0)
    cell(f"{row}-common", h == "EQUAL" and ds == (False, False) and not new,
         f"hash_now full {h}; desyncSeen h/c {ds}; new crash files {new}")


def staging_miss(cells, detail):
    ev(f"staging miss: {detail}")
    for c in cells:
        if c not in RESULTS and not c.endswith("-common"):
            cell(c, False, f"staging: {detail}")


def light(host, client, tag, tiles):
    """[ambient, fire, items, units] of each tile on both machines (light_census) and the census fields that differ."""
    ch, cc = ls.census(host, f"fuse_{tag}_h"), ls.census(client, f"fuse_{tag}_c")
    return ({f"{t[0]},{t[1]},{t[2]}": (ls.tile_light(ch, t), ls.tile_light(cc, t)) for t in tiles},
            ls.census_mismatch(ch, cc))


def item(gc, iid):
    for it in gc.cmd({"cmd": "battle_items"}).get("items") or []:
        if it.get("id") == iid:
            return {k: it.get(k) for k in ("owner", "slot", "onTile", "fuse", "fuseEnabled")}
    return None


def prime(host, client, fid, unprime):
    return more.order(host, client, {"cmd": "battle_intent", "kind": "prime", "actor": T_ID,
                                     "plan": {"item": fid, "fuse": -1 if unprime else FUSE, "unprime": bool(unprime)}},
                      "prime")


def stage(host, client):
    """Parking (PARK, facing kept), A to A_N, V to V_N facing 5 + the turn intent to 6; returns (ok, detail)."""
    s0 = more.snap(host, client)
    rc = all([more.tele_rc(host, client, uid, t, uu(s0, "h", uid).get("dir")) for uid, t in PARK])  # every one runs
    rc = more.tele_rc(host, client, A_ID, A_N, A_N_DIR) and rc
    rc = more.tele_rc(host, client, V_ID, V_N, V_N_DIR0) and rc
    lt = light(host, client, "staging", [A_N])
    r = more.turn(host, client, V_ID, V_N_DIR)
    s = more.snap(host, client)
    parked = all(at(s, uid, t, uu(s0, "h", uid).get("dir")) for uid, t in PARK)
    hl, cl = lt[0][AK]
    lv, vv = pair(s, "sees", V_ID), pair(s, "vis")
    ok = (rc and parked and r["err"] is None and at(s, A_ID, A_N, A_N_DIR) and at(s, V_ID, V_N, V_N_DIR)
          and hl[3] <= DARK_MAX and cl[3] <= DARK_MAX and vv == (False, False) and all(A_ID not in x for x in lv))
    return ok, (f"recompute {rc}; parked {parked}; A_N light h/c {hl}/{cl} mismatch {lt[1]} (dark: units <= "
                f"{DARK_MAX}); V turn {r['hev']} err {r['err']}; vis h/c {vv}; list(V) h/c {lv}")


# ===================== row =====================


def row_flare_prime(host, client):
    cells = dict(ROWS)["flare_prime"]
    if not STAGED["ok"]:
        staging_miss(cells, STAGED["detail"])
        return common(host, client, "flare_prime")
    fid, ok, gr = more.give(host, client, T_ID, FLARE)
    if not ok:
        staging_miss(cells, f"battle_give host {gr[0]} client {gr[1]} (want ids equal, not -1)")
        return common(host, client, "flare_prime")
    rc = more.tele_rc(host, client, T_ID, T_TILE, T_DIR)
    more.tu_max(host, client, T_ID)
    lt0 = light(host, client, "pre", [A_N, T_TILE])
    s1 = more.snap(host, client)
    hand = (item(host, fid), item(client, fid))
    p1 = prime(host, client, fid, False)
    s2 = more.snap(host, client)
    lt1 = light(host, client, "prime", [A_N, T_TILE])
    rc2 = more.recompute(host, client)
    look = more.turns56(host, client)
    s3 = more.snap(host, client)
    lt2 = light(host, client, "relit", [A_N, T_TILE])
    more.tu_max(host, client, T_ID)
    p2 = prime(host, client, fid, True)
    s4 = more.snap(host, client)
    lt3 = light(host, client, "unprime", [A_N, T_TILE])
    ev(f"flare_prime: flare {fid} | T tele {T_TILE} facing {T_DIR} + recompute {rc}; T tu h/c {pair(s1, 'tu', T_ID)} | "
       f"prime {p1['intent']} err {p1['err']} deny {p1.get('deny')} evs host {p1['hev']} client {p1['cev']} host log "
       f"{more.host_lines(host, p1['seq0'])} | light pre {lt0[0]} after prime {lt1[0]} mismatch {lt1[1]} | vis(A) h/c "
       f"{pair(s2, 'vis')} | recompute {rc2} V turns {look} relit {lt2[0]} | unprime {p2['intent']} err {p2['err']} "
       f"evs host {p2['hev']} client {p2['cev']} host log {more.host_lines(host, p2['seq0'])} | light after unprime "
       f"{lt3[0]} mismatch {lt3[1]} | vis(A) h/c {pair(s4, 'vis')} | T tu h/c {pair(s4, 'tu', T_ID)} | flare h/c "
       f"{(item(host, fid), item(client, fid))}")
    a0, a1, a2, a3 = lt0[0][AK], lt1[0][AK], lt2[0][AK], lt3[0][AK]
    lv1, v1 = pair(s1, "sees", V_ID), pair(s1, "vis")
    in_hand = all(x and x.get("owner") == T_ID and x.get("slot") == "STR_RIGHT_HAND" and x.get("fuse") == -1
                  for x in hand)
    cell("flare_prime-pre", rc and at(s1, T_ID, T_TILE, T_DIR) and a0[0][3] <= DARK_MAX and a0[1][3] <= DARK_MAX
         and v1 == (False, False) and all(A_ID not in x for x in lv1) and in_hand,
         f"T on {T_TILE} facing {T_DIR} {at(s1, T_ID, T_TILE, T_DIR)}; A_N light h/c {a0}; vis h/c {v1}; "
         f"list(V) h/c {lv1}; flare h/c {hand} (want units <= {DARK_MAX}, False/False, no {A_ID}, right hand fuse -1)")
    lv2 = pair(s2, "sees", V_ID)
    cell("flare_prime-host", a1[0][3] > DARK_MAX and A_ID in lv2[0],
         f"host A_N light {a1[0]}; host list(V) {lv2[0]} (precondition: units > {DARK_MAX}, holds {A_ID})")
    cell("flare_prime-light", a1[1] == a1[0], f"A_N light client {a1[1]} host {a1[0]} (want equal)")
    here = uu(s2, "c").get("here")
    cell("flare_prime-here", here is True, f"here(client) {here} (want True)")
    cell("flare_prime-list", A_ID in lv2[1], f"list(client, V) {lv2[1]} (want it to hold {A_ID}; host {lv2[0]})")
    lv3 = pair(s3, "sees", V_ID)
    cell("flare_unprime-pre", rc2 and all(A_ID in x for x in lv3) and a2[0][3] > DARK_MAX and a2[1][3] > DARK_MAX,
         f"recompute {rc2}; list(V) h/c {lv3}; A_N light h/c {a2} (want {A_ID} in both, units > {DARK_MAX} on both)")
    lv4 = pair(s4, "sees", V_ID)
    cell("flare_unprime-host", a3[0][3] <= DARK_MAX and A_ID not in lv4[0],
         f"host A_N light {a3[0]}; host list(V) {lv4[0]} (precondition: units <= {DARK_MAX}, without {A_ID})")
    cell("flare_unprime-light", a3[1] == a3[0], f"A_N light client {a3[1]} host {a3[0]} (want equal)")
    cell("flare_unprime-list", A_ID not in lv4[1], f"list(client, V) {lv4[1]} (want no {A_ID}; host {lv4[0]})")
    common(host, client, "flare_prime")


# ===================== bring-up =====================


def boot(host, client):
    """test_client_sight_night's boot with this file's key (copied) at night, the mod in both user dirs (main()):
    test_light_scope's write_night_cfg into the host's user dir before it starts, SEED_ROSTER on the host before
    open_new_battle, SEED_MAP before newbattle_ok, seat_count 2, pin_ai_neutral, every live X-COM unit's reactions 0 on
    both (client first), test_light_scope's night_precondition; A on A_BOOT facing A_BOOT_DIR."""
    ls.write_night_cfg(host.user_dir)
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    host.ok({"cmd": "set_seed", "seed": SEED_ROSTER})
    raw.skirmish_host(host, KEY)
    raw.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": raw.CLIENT_PLAYER})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: raw.lobby(host).get("buttonVisible") or None)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r} (baked {MAP_FP!r})")
    assert seated.get("soldierIds") == SEATED, f"seated {seated.get('soldierIds')} (baked {SEATED})"
    pinned = pin_ai_neutral(host, client, tag="client_sight_fuse")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    types = ((uh.get(A_ID) or {}).get("type"), (uc.get(A_ID) or {}).get("type"))
    assert types == (A_TYPE, A_TYPE), f"A type host/client {types} (want {A_TYPE})"
    for uid, u in sorted(uh.items()):
        if u.get("faction") == 0 and not u.get("isOut"):  # FACTION_PLAYER
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="client_sight_fuse bring-up")
    nerr = ls.night_precondition(host, client)
    assert nerr is None, nerr
    s = more.snap(host, client)
    assert at(s, A_ID, A_BOOT, A_BOOT_DIR), (
        f"A at boot: {uu(s, 'h')} / {uu(s, 'c')} (baked {A_BOOT} facing {A_BOOT_DIR})")


def main():
    global CRASH0
    t0 = time.time()
    host = GameClient("host", 49864, make_user_dir("client_sight_fuse_host", mods=[MOD_DIR]))
    client = GameClient("client", 49865, make_user_dir("client_sight_fuse_client", mods=[MOD_DIR]))
    blocked = None
    try:
        try:
            boot(host, client)
            CRASH0 = crash_files()
        except Exception as e:  # a bring-up failure fails every row
            more.capture_boot(host, client, e)
            blocked = "boot"
        if not blocked:
            try:
                STAGED["ok"], STAGED["detail"] = stage(host, client)
            except Exception as e:  # a staging failure fails the row "staging"
                STAGED["ok"], STAGED["detail"] = False, f"staging raised {short(e)}"
            print(f"[client_sight_fuse] staging ok {STAGED['ok']}: {STAGED['detail']}", flush=True)
        for row, cells in ROWS:
            if blocked:
                ev(f"not run ({blocked})")
                for c in cells:
                    cell(c, False, blocked)
            else:
                try:
                    row_flare_prime(host, client)
                except Exception as e:  # every cell is reported after a failure
                    ev(f"row raised {short(e)}")
                    for c in cells:
                        if c not in RESULTS:
                            cell(c, False, f"row {row} raised {short(e)}")
            flush_row(row, cells)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[client_sight_fuse] shutdown {gc.name}: {short(e, 200)}", flush=True)
    names = [c for _, cells in ROWS for c in cells]
    failed = [c for c in names if not RESULTS.get(c)]
    print(f"\ntest_client_sight_fuse: {len(names) - len(failed)}/{len(names)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
