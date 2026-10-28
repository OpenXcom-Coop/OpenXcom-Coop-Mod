"""W2-H35c (CAP-1 night) - test_client_sight_fuse.py: at night, on the co-op second player's machine the light of a
flare that glows only while primed, an alien's `visible` flag and each X-COM soldier's list of seen units follow vanilla
when the flare is primed next to a dark alien and unprimed again (C6) (spec rewrite/prompts/w2h35c_r5u8b_captures.md
(f); rulings W2-H35b QB-3 (a), R-R5U1-1, D171, QH35C-5 / QH35C-7 (a); fixture rulings R-H35B-SB-1 (darkness D-1,
parking S-1, light_recompute after every teleport) and R-H35B-SB-2).

Vanilla relights at the holder and re-runs sight with the item's glow range right after a prime or an unprime
(BattlescapeGame BA_PRIME / BA_UNPRIME, the host's prime intent). The second player's machine receives the item's
fuse / fuseEnabled change but relights nothing (the applyDelta light pre-pass counts only a tile / owner change), so
its light and sight stay as before. No stock ruleset has such a flare: test mod Coop_FuseFlare_Test (this
directory's mods/, the spec's (e) M1 / M2 verbatim) adds STR_COOP_FUSE_FLARE (fuseType -1, power 22), loaded on BOTH.

TASK 0 verdicts (docs rewrite/w2h35c-task0/CONSTANTS.md, capture boots Na and Nb equal, S28): C6 CONFIRMED (prime: the
host lights A's tile to 11 and its V lists A; the client stays at 5, V empty, A undrawn; unprime: after both are lit
the host darkens to 5 and drops A, the client stays lit at 11 and keeps A). Day cases C3 / C18 (CONFIRMED) and C7
(REFUTED) are in / out of test_client_sight_more.py.

ONE classic co-op NIGHT boot (lobby key 46644, user dirs w2h35c_n_host / w2h35c_n_client, the mod on both): SAN's boot
(copied): LS write_night_cfg (darkness 15) into the host's user dir before the host starts and LS night_precondition
after it; SEED_ROSTER 1, SEED_MAP 1, seat_count 2, pin_ai_neutral (A base TU 0: it never acts), reactions 0 for every
X-COM unit on both. Staging (a miss fails the row "staging"): S-1 parks SAN's PARK (T = 8 included: R-H35B-SB-1 S-1
parks the row's light source until its row places it; TASK 0 F15397), A to A_N facing 5, V (9) to V_N facing 5, client
turn intent V -> 6; every teleport is followed by light_recompute on both. D-1: A_N units light <= DARK_MAX on both.

Row:
  C6   battle_give STR_COOP_FUSE_FLARE to T (8) (clear hands; ids equal, not -1); tele T to T6 facing T6_DIR (+
       recompute); T TU max; client prime intent {item, fuse 5}; seq barrier.
       C6-pre   before the prime: A_N units light <= 5 on both (D-1); vis(A) false on both; A in neither list(V); the
                flare in T's right hand on both, fuse -1.
       C6-host  after the prime: host A_N units light > 5 and A in host list(V) (precondition: vanilla's refresh).
       C6-light the client's A_N tile_light equal to the host's.   C6-here here(client, A) true.
       C6-list  A in list(client, V).
       C6u-pre  after light_recompute on both and client turn intents V -> 5 -> 6: A in list(V) on both; A_N lit
                (units > 5) on both.
       C6u-host after T TU max and client unprime intent {item, fuse -1, unprime true}, barrier: host A_N units light
                <= 5 and A not in host list(V) (precondition).
       C6u-light the client's A_N tile_light equal to the host's.  C6u-list A not in list(client, V).
       C6-common (hash_now full: every bucket EQUAL; event_state.desyncSeen false on both; 0 new crash files).
"tile_light" = [ambient, fire, items, units] of the tile (LS light_census); "vis" / "here" / "list" as in
test_client_sight_more.py.

RED at the red commit (unchanged build): C6-light, C6-here, C6-list, C6u-light, C6u-list FAIL; every other cell PASS.
GREEN (W2-H35c G6): every cell PASS.

The row prints one "EVIDENCE C6:" line, one PASS / FAIL line per cell and "ROW C6: PASS|FAIL". A bring-up failure
prints ONE "CAPTURE boot:" line and fails every cell "boot". one run is the result; no skip, no
second boot, no other fixture; exit 0 only when every cell passes, else 2. run in the foreground to completion.

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
# the probes and levers (view / snap / order / tele_rc ...) and SAE's capture_boot shape
import test_client_sight_more as more

# ----- TASK 0 pins (CONSTANTS.md; boots Na and Nb equal, S28) -----
SEED_ROSTER, SEED_MAP = 1, 1
MAP_FP = -4.48310638993e+18
SEATED = [8, 9]
A_ID, A_TYPE = 1000000, "STR_SECTOID_SOLDIER"   # the only alien (pin_ai_neutral: base TU 0)
A_BOOT, A_BOOT_DIR = (27, 12, 0), 5
DARKNESS, DARK_MAX = 15, 5                      # battle.cfg darkness; D-1: A_N units light <= 5
A_N, A_N_DIR = (20, 18, 0), 5
V_ID, T_ID = 9, 8                               # V watches (client seat), T holds the flare (client seat)
V_N, V_N_DIR0, V_N_DIR = (31, 18, 0), 5, 6
PARK = ((8, (10, 13, 0)), (12, (11, 13, 0)), (13, (10, 14, 0)), (14, (10, 15, 0)), (10, (10, 16, 0)),
        (11, (10, 17, 0)))                      # SAN's PARK, 8 included (S-1; F15397); facing kept
T6, T6_DIR = (20, 29, 0), 4                     # T6 oracle's first candidate: Round(distance) 11 from A_N, facing away
FLARE, FUSE = "STR_COOP_FUSE_FLARE", 5
MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_FuseFlare_Test")
KEY = "46644"                                   # this file's lobby key (spec (G))

ROWS = (("C6", ("C6-pre", "C6-host", "C6-light", "C6-here", "C6-list", "C6u-pre", "C6u-host", "C6u-light", "C6u-list",
                "C6-common")),)
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
        assert_hash_clean(host, client, full=True, what=f"w2h35c-n {row}")
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
    ch, cc = ls.census(host, f"c6_{tag}_h"), ls.census(client, f"c6_{tag}_c")
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
    """S-1 parking (PARK, facing kept), A to A_N, V to V_N facing 5 + the turn intent to 6; returns (ok, detail)."""
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
    return ok, (f"recompute {rc}; parked {parked}; A_N light h/c {hl}/{cl} mismatch {lt[1]} (D-1: units <= "
                f"{DARK_MAX}); V turn {r['hev']} err {r['err']}; vis h/c {vv}; list(V) h/c {lv}")


# ===================== row =====================


def row_c6(host, client):
    cells = dict(ROWS)["C6"]
    if not STAGED["ok"]:
        staging_miss(cells, STAGED["detail"])
        return common(host, client, "C6")
    fid, ok, gr = more.give(host, client, T_ID, FLARE)
    if not ok:
        staging_miss(cells, f"battle_give host {gr[0]} client {gr[1]} (want ids equal, not -1; STOP-IF 6)")
        return common(host, client, "C6")
    rc = more.tele_rc(host, client, T_ID, T6, T6_DIR)
    more.tu_max(host, client, T_ID)
    lt0 = light(host, client, "pre", [A_N, T6])
    s1 = more.snap(host, client)
    hand = (item(host, fid), item(client, fid))
    p1 = prime(host, client, fid, False)
    s2 = more.snap(host, client)
    lt1 = light(host, client, "prime", [A_N, T6])
    rc2 = more.recompute(host, client)
    look = more.turns56(host, client)
    s3 = more.snap(host, client)
    lt2 = light(host, client, "relit", [A_N, T6])
    more.tu_max(host, client, T_ID)
    p2 = prime(host, client, fid, True)
    s4 = more.snap(host, client)
    lt3 = light(host, client, "unprime", [A_N, T6])
    ev(f"C6: flare {fid} | T tele {T6} facing {T6_DIR} + recompute {rc}; T tu h/c {pair(s1, 'tu', T_ID)} | prime "
       f"{p1['intent']} err {p1['err']} deny {p1.get('deny')} evs host {p1['hev']} client {p1['cev']} host log "
       f"{more.host_lines(host, p1['seq0'])} | light pre {lt0[0]} after prime {lt1[0]} mismatch {lt1[1]} | vis(A) h/c "
       f"{pair(s2, 'vis')} | recompute {rc2} V turns {look} relit {lt2[0]} | unprime {p2['intent']} err {p2['err']} "
       f"evs host {p2['hev']} client {p2['cev']} host log {more.host_lines(host, p2['seq0'])} | light after unprime "
       f"{lt3[0]} mismatch {lt3[1]} | vis(A) h/c {pair(s4, 'vis')} | T tu h/c {pair(s4, 'tu', T_ID)} | flare h/c "
       f"{(item(host, fid), item(client, fid))}")
    a0, a1, a2, a3 = lt0[0][AK], lt1[0][AK], lt2[0][AK], lt3[0][AK]
    lv1, v1 = pair(s1, "sees", V_ID), pair(s1, "vis")
    in_hand = all(x and x.get("owner") == T_ID and x.get("slot") == "STR_RIGHT_HAND" and x.get("fuse") == -1
                  for x in hand)
    cell("C6-pre", rc and at(s1, T_ID, T6, T6_DIR) and a0[0][3] <= DARK_MAX and a0[1][3] <= DARK_MAX
         and v1 == (False, False) and all(A_ID not in x for x in lv1) and in_hand,
         f"T on {T6} facing {T6_DIR} {at(s1, T_ID, T6, T6_DIR)}; A_N light h/c {a0}; vis h/c {v1}; list(V) h/c {lv1}; "
         f"flare h/c {hand} (want units <= {DARK_MAX}, False/False, no {A_ID}, right hand fuse -1)")
    lv2 = pair(s2, "sees", V_ID)
    cell("C6-host", a1[0][3] > DARK_MAX and A_ID in lv2[0],
         f"host A_N light {a1[0]}; host list(V) {lv2[0]} (precondition: units > {DARK_MAX}, holds {A_ID})")
    cell("C6-light", a1[1] == a1[0], f"A_N light client {a1[1]} host {a1[0]} (want equal)")
    here = uu(s2, "c").get("here")
    cell("C6-here", here is True, f"here(client) {here} (want True)")
    cell("C6-list", A_ID in lv2[1], f"list(client, V) {lv2[1]} (want it to hold {A_ID}; host {lv2[0]})")
    lv3 = pair(s3, "sees", V_ID)
    cell("C6u-pre", rc2 and all(A_ID in x for x in lv3) and a2[0][3] > DARK_MAX and a2[1][3] > DARK_MAX,
         f"recompute {rc2}; list(V) h/c {lv3}; A_N light h/c {a2} (want {A_ID} in both, units > {DARK_MAX} on both)")
    lv4 = pair(s4, "sees", V_ID)
    cell("C6u-host", a3[0][3] <= DARK_MAX and A_ID not in lv4[0],
         f"host A_N light {a3[0]}; host list(V) {lv4[0]} (precondition: units <= {DARK_MAX}, without {A_ID})")
    cell("C6u-light", a3[1] == a3[0], f"A_N light client {a3[1]} host {a3[0]} (want equal)")
    cell("C6u-list", A_ID not in lv4[1], f"list(client, V) {lv4[1]} (want no {A_ID}; host {lv4[0]})")
    common(host, client, "C6")


# ===================== bring-up =====================


def boot(host, client):
    """SAN's boot with this file's key (copied) at night, the mod in both user dirs (main): LS write_night_cfg into the
    host's user dir before it starts, SEED_ROSTER on the host before open_new_battle, SEED_MAP before newbattle_ok,
    seat_count 2, pin_ai_neutral, every live X-COM unit's reactions 0 on both (client first, F607), LS
    night_precondition; A on A_BOOT facing A_BOOT_DIR."""
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
    pinned = pin_ai_neutral(host, client, tag="w2h35c-n")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    types = ((uh.get(A_ID) or {}).get("type"), (uc.get(A_ID) or {}).get("type"))
    assert types == (A_TYPE, A_TYPE), f"A type host/client {types} (want {A_TYPE})"
    for uid, u in sorted(uh.items()):
        if u.get("faction") == 0 and not u.get("isOut"):  # FACTION_PLAYER
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="w2h35c-n bring-up")
    nerr = ls.night_precondition(host, client)
    assert nerr is None, nerr
    s = more.snap(host, client)
    assert at(s, A_ID, A_BOOT, A_BOOT_DIR), (
        f"A at boot: {uu(s, 'h')} / {uu(s, 'c')} (baked {A_BOOT} facing {A_BOOT_DIR})")


def main():
    global CRASH0
    t0 = time.time()
    host = GameClient("host", 49864, make_user_dir("w2h35c_n_host", mods=[MOD_DIR]))
    client = GameClient("client", 49865, make_user_dir("w2h35c_n_client", mods=[MOD_DIR]))
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
            print(f"[w2h35c-n] staging ok {STAGED['ok']}: {STAGED['detail']}", flush=True)
        for row, cells in ROWS:
            if blocked:
                ev(f"not run ({blocked})")
                for c in cells:
                    cell(c, False, blocked)
            else:
                try:
                    row_c6(host, client)
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
                print(f"[w2h35c-n] shutdown {gc.name}: {short(e, 200)}", flush=True)
    names = [c for _, cells in ROWS for c in cells]
    failed = [c for c in names if not RESULTS.get(c)]
    print(f"\ntest_client_sight_fuse: {len(names) - len(failed)}/{len(names)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
