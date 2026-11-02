"""test_client_sight_night.py: at night, on the co-op second player's machine each X-COM soldier's list
of seen units follows vanilla when a soldier's personal light moves away from a lit alien (walk_away) and when a
thrown flare lands next to a dark alien (flare_land). The second player's off-turn view follows vanilla, and an alien
no X-COM soldier sees stays hidden.

Vanilla refreshes sight around a unit right after its step's light (UnitWalkBState :249-:250, radius 2) and around an
item right after its light moves (TileEngine::itemDrop :5213-:5214, the item's glow range). The second player's
machine recomputes the same light (applyDelta step (8b) / (8c)) and then refreshes sight at the same place and radius
(connectionTCP.cpp coopClientEventSight), besides the actor's own sight.

Fixture facts (equal in two boots): after B walks east the host drops A from V's list; a client without the step
refresh keeps it. After the flare lands on F_N the host's V sees A; a client without the item refresh does not, its
thrower does not either, and A stays undrawn there.

ONE classic co-op NIGHT boot (lobby key 46641, user dirs client_sight_night_host / client_sight_night_client):
test_client_alien_sight's boot (copied) with test_light_scope's write_night_cfg (darkness 15) written into the host's
user dir before the host starts and its night_precondition after it: SEED_ROSTER 1 before open_new_battle, SEED_MAP 1
before newbattle_ok, seat_count 2, pin_ai_neutral (A = the only alien, base TU 0: it never acts), reactions 0 for
every X-COM unit on both.
Staging (a miss fails every row "staging"): park 8, 12, 13, 14, B (10) and T (11) on PARK (Round(distance) >= 10
from A_N and F_N); A to A_N facing 5; V (9) to V_N facing 5; client turn intent V -> 6; every teleport is followed by
light_recompute on both (a teleport does not recompute light). Dark precondition: A_N's units light <= DARK_MAX on
both; vis false on both; A in neither list(V).

Rows, in order (every row runs after a failure):
  walk_away  tele B to B_START facing 2, light_recompute on both, client turn intents V -> 5 -> 6, then ONE real-UI host
      walk of B to B_DEST (dc.host_walk; walk end, wait_host_idle, seq barrier).
      walk_away-pre   before the walk: A in list(V) on both; vis true on both.
      walk_away-host  after the walk: A not in host list(V) (precondition: vanilla's step refresh dropped the dark A).
      walk_away-list  list(client, V) equal to list(host, V).
  flare_land  END TURN cycle (host set_seed 1; screens closed client first); battle_give STR_ELECTRO_FLARE to T on
      both (ids equal, not -1); tele T to T_N facing T_DIR (away from F_N: a thrower already facing its target cancels
      its own throw) + light_recompute; host set_seed SEED_THROW; host battle_fire {unit T, mode throw, weapon_id
      <the flare>, F_N, tu 255} (the test command turns T, then throws).
      flare_land-pre     before the throw: side 0 on both; A_N dark; vis false on both; A in neither list(V); the
                         flare in T's hand on both.
      flare_land-landed  after the throw chain (bt_action_end, wait_host_idle, seq barrier): the flare on F_LAND on
                         both; A in host list(V) (precondition: vanilla's landing refresh).
      flare_land-list    list(client, V) equal to list(host, V).
  Every row: <row>-common (hash_now full: every bucket EQUAL; event_state.desyncSeen false on both; 0 new crash files).
"vis(gc)" = A's battle_state units[].visible; "list(gc, U)" = U's units[].visibleUnits.

A client without the step and item refreshes fails walk_away-list and flare_land-list; every other cell passes.
With them, every cell passes.

Each row prints one "EVIDENCE <row>:" line, one PASS / FAIL line per cell and "ROW <row>: PASS|FAIL". A bring-up
failure prints ONE "CAPTURE boot:" line and fails every row "boot". No skip, no second boot, no other fixture; exit 0
only when every cell passes, else 2.

Run:  python tools/coop_test/test_client_sight_night.py
"""

import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
import test_delta_core as dc
from test_delta_core import both, tele_both
import test_light_scope as ls
# vis, ua, snap, fmt, states, client_turn, alien_cycle, close_client_screen and the per-GameClient lock (on import)
import test_client_alien_sight as cas

# ----- fixture values (equal in two boots) -----
SEED_ROSTER, SEED_MAP = 1, 1
MAP_FP = -4.48310638993e+18
SEATED = [8, 9]
A_ID, A_TYPE = 1000000, "STR_SECTOID_SOLDIER"   # the only alien (pin_ai_neutral: base TU 0)
A_BOOT, A_BOOT_DIR = (27, 12, 0), 5             # A at boot
DARKNESS, DARK_MAX = 15, 5                      # battle.cfg darkness; dark: A_N units light <= 5 (shade > 9)
A_N, A_N_DIR = (20, 18, 0), 5                   # units light 5 / 5 after the parking
V_ID, B_ID, T_ID = 9, 10, 11                    # V watches (client seat), B walks, T throws (host seat)
PARK = ((8, (10, 13, 0)), (12, (11, 13, 0)), (13, (10, 14, 0)), (14, (10, 15, 0)), (B_ID, (10, 16, 0)),
        (T_ID, (10, 17, 0)))                    # a ring scan from the craft exit (14,17,0); facing kept
V_N, V_N_DIR0, V_N_DIR = (31, 18, 0), 5, 6      # the first candidate tile for V
B_START, B_START_DIR = (21, 19, 0), 2           # diagonal to A_N; A behind B
B_DEST = (30, 19, 0)                            # first straight-east tile at Round(distance) >= 10 from A_N
T_N, T_DIR = (29, 22, 0), 3                     # facing away from F_N (octant 7 + 4)
F_N = F_LAND = (20, 17, 0)                      # the throw's target; the flare lands there at SEED_THROW
SEED_CYCLE, SEED_THROW = 1, 1                   # host set_seed right before its END TURN press / the throw
FLARE = "STR_ELECTRO_FLARE"
KEY = "46641"                                   # this file's lobby key

ROWS = (("walk_away", ("walk_away-pre", "walk_away-host", "walk_away-list", "walk_away-common")),
        ("flare_land", ("flare_land-pre", "flare_land-landed", "flare_land-list", "flare_land-common")))
RESULTS = {}
CRASH0 = set()
STAGED = {"ok": None, "detail": ""}
_BUF = {"ev": [], "lines": []}
ua, short = cas.ua, cas.short


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
        assert_hash_clean(host, client, full=True, what=f"client_sight_night {row}")
        h = "EQUAL"
    except AssertionError as e:
        h = str(e)[:600]
    ds = (event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen"))
    new = sorted(crash_files() - CRASH0)
    cell(f"{row}-common", h == "EQUAL" and ds == (False, False) and not new,
         f"hash_now full {h}; desyncSeen h/c {ds}; new crash files {new}")


def staging_miss(cells, detail):
    """A staging step off its pin: the row's cells FAIL "staging" (its common cell is still measured)."""
    ev(f"staging miss: {detail}")
    for c in cells:
        if c not in RESULTS and not c.endswith("-common"):
            cell(c, False, f"staging: {detail}")


def evs_a(gc, seq0):
    return [(e.get("seq"), e.get("kind"), e.get("actionId"))
            for e in (gc.cmd({"cmd": "event_log", "tail": 400}).get("events") or []) if (e.get("seq") or 0) > seq0]


def recompute(host, client):
    rc, rh = client.cmd({"cmd": "light_recompute"}), host.cmd({"cmd": "light_recompute"})
    return bool(rh.get("ok") and rc.get("ok"))


def tele_rc(host, client, uid, t, d):
    """tele_both, then light_recompute on both (a teleport does not recompute light)."""
    tele_both(host, client, uid, t, d)
    return recompute(host, client)


def light(host, client, tag, tiles):
    """[ambient, fire, items, units] of each tile on both machines (light_census) and the census fields that differ."""
    ch, cc = ls.census(host, f"night_{tag}_h"), ls.census(client, f"night_{tag}_c")
    return ({f"{t[0]},{t[1]},{t[2]}": (ls.tile_light(ch, t), ls.tile_light(cc, t)) for t in tiles},
            ls.census_mismatch(ch, cc))


def dark(lt):
    h, c = lt[0][f"{A_N[0]},{A_N[1]},{A_N[2]}"]
    return h[3] <= DARK_MAX and c[3] <= DARK_MAX


def lists(s, uid):
    return ua(s["h"], uid).get("sees"), ua(s["c"], uid).get("sees")


def avis(s):
    return ua(s["h"]).get("vis"), ua(s["c"]).get("vis")


def at(s, uid, pos, d):
    return all(ua(s[m], uid).get("pos") == pos and ua(s[m], uid).get("dir") == d for m in ("h", "c"))


def item(gc, iid):
    for it in gc.cmd({"cmd": "battle_items"}).get("items") or []:
        if it.get("id") == iid:
            return {k: it.get(k) for k in ("owner", "slot", "onTile", "tx", "ty", "tz")}
    return None


def stage(host, client):
    """Parking, A to A_N, V to V_N + the turn intent to V_N_DIR; returns (ok, detail)."""
    s0 = cas.snap(host, client)
    rc = all([tele_rc(host, client, uid, t, ua(s0["h"], uid).get("dir")) for uid, t in PARK])  # every one runs
    rc = tele_rc(host, client, A_ID, A_N, A_N_DIR) and rc
    rc = tele_rc(host, client, V_ID, V_N, V_N_DIR0) and rc
    lt = light(host, client, "staging", [A_N])
    r, s = cas.client_turn(host, client, V_ID, V_N_DIR)
    parked = all(at(s, uid, t, ua(s0["h"], uid).get("dir")) for uid, t in PARK)
    lv, vv = lists(s, V_ID), avis(s)
    ok = (rc and parked and at(s, A_ID, A_N, A_N_DIR) and at(s, V_ID, V_N, V_N_DIR) and dark(lt)
          and vv == (False, False) and all(A_ID not in (x or []) for x in lv))
    return ok, (f"recompute {rc}; parked {parked}; A_N light h/c {lt[0]} mismatch {lt[1]} (dark: units <= {DARK_MAX}); "
                f"V turn intent {r}; vis h/c {vv}; list(V) h/c {lv}; {cas.fmt(s)}")


# ===================== rows =====================


def row_walk_away(host, client):
    cells = dict(ROWS)["walk_away"]
    if not STAGED["ok"]:
        staging_miss(cells, STAGED["detail"])
        return common(host, client, "walk_away")
    rc = tele_rc(host, client, B_ID, B_START, B_START_DIR)
    lt0 = light(host, client, "walk_pre", [A_N, B_START])
    r5, _s = cas.client_turn(host, client, V_ID, 5)
    r6, s1 = cas.client_turn(host, client, V_ID, V_N_DIR)
    lv1, vv1 = lists(s1, V_ID), avis(s1)
    notes = []
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    hw = dc.host_walk(host, client, B_DEST, None, notes)
    session.wait_seq_barrier(host, client, timeout=30)
    s2 = cas.snap(host, client)
    path = dc.executed_path(hw)
    lt1 = light(host, client, "walk_post", [A_N, B_DEST])
    lv2, vv2 = lists(s2, V_ID), avis(s2)
    ev(f"walk_away: B tele {B_START} facing {B_START_DIR} + recompute {rc}; light before h/c {lt0[0]} mismatch "
       f"{lt0[1]}; V turn intents {r5} {r6}; pre {cas.fmt(s1)} | B walk to {B_DEST}: executed path {path} notes "
       f"{notes} evs host {evs_a(host, seq0)} client {evs_a(client, seq0)} | A's tile light after h/c {lt1[0]} "
       f"mismatch {lt1[1]} | vis h/c {vv2} | client selected {s2['c']['sel']} | after {cas.fmt(s2)}")
    cell("walk_away-pre", rc and at(s1, B_ID, B_START, B_START_DIR) and all(A_ID in (x or []) for x in lv1)
         and vv1 == (True, True),
         f"B on {B_START} facing {B_START_DIR} on both {at(s1, B_ID, B_START, B_START_DIR)}; list(V) h/c {lv1}; "
         f"vis h/c {vv1} (want A in both lists, True / True)")
    cell("walk_away-host", path[-1:] == [B_DEST] and A_ID not in (lv2[0] or []),
         f"B's walk ends on {path[-1:]}; host list(V) {lv2[0]} (precondition: ends on {B_DEST}, without {A_ID})")
    cell("walk_away-list", lv2[1] == lv2[0], f"list(V) host {lv2[0]} client {lv2[1]} (want equal)")
    common(host, client, "walk_away")


def row_flare_land(host, client):
    cells = dict(ROWS)["flare_land"]
    if not STAGED["ok"]:
        staging_miss(cells, STAGED["detail"])
        return common(host, client, "flare_land")
    cy = cas.alien_cycle(host, client, SEED_CYCLE, 0.0)
    closed, s0 = cas.close_client_screen(host, client)
    rc_g = client.cmd({"cmd": "battle_give", "unit": T_ID, "item": FLARE})
    rh_g = host.cmd({"cmd": "battle_give", "unit": T_ID, "item": FLARE})
    session.wait_seq_barrier(host, client, timeout=30)
    fid = rh_g.get("weaponId")
    if not (rh_g.get("ok") and rc_g.get("ok") and fid == rc_g.get("weaponId") and fid not in (None, -1)):
        staging_miss(cells, f"battle_give host {rh_g} client {rc_g} (want ids equal, not -1)")
        return common(host, client, "flare_land")
    rc = tele_rc(host, client, T_ID, T_N, T_DIR)
    lt0 = light(host, client, "throw_pre", [A_N, T_N, F_N])
    s1 = cas.snap(host, client)
    hand = (item(host, fid), item(client, fid))
    lv1, vv1 = lists(s1, V_ID), avis(s1)
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    host.ok({"cmd": "set_seed", "seed": SEED_THROW})
    fire = host.cmd({"cmd": "battle_fire", "unit": T_ID, "mode": "throw", "weapon_id": fid, "x": F_N[0], "y": F_N[1],
                     "z": F_N[2], "tu": 255})
    host.wait_for("host bt_action_end after the throw",
                  lambda: any(k == "bt_action_end" for _, k, _a in evs_a(host, seq0)) or None, timeout=30)
    session.wait_host_idle(host, client, timeout=30)
    session.wait_seq_barrier(host, client, timeout=30)
    s2 = cas.snap(host, client)
    land = (item(host, fid), item(client, fid))
    lt1 = light(host, client, "throw_post", [A_N, F_LAND])
    lv2, vv2, lt2 = lists(s2, V_ID), avis(s2), lists(s2, T_ID)
    ev(f"flare_land: END TURN cycle evs {[k for _, k in cy['hev']]} closed {closed} side h/c {s0['h']['side']}/"
       f"{s0['c']['side']} | flare give h/c {fid}/{rc_g.get('weaponId')} | T tele {T_N} facing {T_DIR} + recompute {rc} "
       f"| light before h/c {lt0[0]} mismatch {lt0[1]} | pre {cas.fmt(s1)} | throw {fire} chain host "
       f"{evs_a(host, seq0)} client {evs_a(client, seq0)} | flare h/c {land} | A's tile light after h/c {lt1[0]} "
       f"mismatch {lt1[1]} | vis h/c {vv2} | list(T) h/c {lt2} | after {cas.fmt(s2)}")
    in_hand = all(x and x.get("owner") == T_ID and x.get("slot") == "STR_RIGHT_HAND" for x in hand)
    cell("flare_land-pre", rc and (s1["h"]["side"], s1["c"]["side"]) == (0, 0) and at(s1, T_ID, T_N, T_DIR)
         and dark(lt0) and vv1 == (False, False) and all(A_ID not in (x or []) for x in lv1) and in_hand,
         f"side h/c {s1['h']['side']}/{s1['c']['side']}; T on {T_N} facing {T_DIR} {at(s1, T_ID, T_N, T_DIR)}; "
         f"A_N dark {dark(lt0)}; vis h/c {vv1}; list(V) h/c {lv1}; flare in T's hand h/c {in_hand} (want 0 / 0, True, "
         f"dark, False / False, no A, True)")
    on_land = all(x and x.get("owner") == -1 and x.get("onTile") and (x.get("tx"), x.get("ty"), x.get("tz")) == F_LAND
                  for x in land)
    cell("flare_land-landed", on_land and A_ID in (lv2[0] or []),
         f"flare on {F_LAND} on both {on_land}; host list(V) {lv2[0]} (precondition: on {F_LAND}, holds {A_ID})")
    cell("flare_land-list", lv2[1] == lv2[0], f"list(V) host {lv2[0]} client {lv2[1]} (want equal)")
    common(host, client, "flare_land")


ROW_FNS = {"walk_away": row_walk_away, "flare_land": row_flare_land}


# ===================== bring-up =====================


def boot(host, client):
    """test_client_alien_sight's boot with this file's key (copied) at night: test_light_scope's write_night_cfg into
    the host's user dir before it starts, SEED_ROSTER on the host before open_new_battle, SEED_MAP before newbattle_ok,
    seat_count 2, pin_ai_neutral, every live X-COM unit's reactions 0 on both (client first), test_light_scope's
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
    pinned = pin_ai_neutral(host, client, tag="client_sight_night")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    types = ((uh.get(A_ID) or {}).get("type"), (uc.get(A_ID) or {}).get("type"))
    assert types == (A_TYPE, A_TYPE), f"A type host/client {types} (want {A_TYPE})"
    for uid, u in sorted(uh.items()):
        if u.get("faction") == 0 and not u.get("isOut"):  # FACTION_PLAYER
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="client_sight_night bring-up")
    nerr = ls.night_precondition(host, client)
    assert nerr is None, nerr
    s = cas.snap(host, client)
    assert at(s, A_ID, A_BOOT, A_BOOT_DIR), f"A at boot: {cas.fmt(s)} (baked {A_BOOT} facing {A_BOOT_DIR})"


def capture_boot(host, client, err):
    cap = {"error": short(err, 600)}
    for gc in (host, client):
        d = {}
        for k, fn in (("states", lambda: cas.states(gc)),
                      ("battle", lambda: {k2: battle_state(gc).get(k2) for k2 in ("side", "turn")}),
                      ("phase", lambda: event_state(gc).get("phase")),
                      ("dialog", lambda: gc.cmd({"cmd": "coop_dialog_info"}))):
            try:
                d[k] = fn()
            except Exception as e:
                d[k] = short(e, 120)
        try:
            with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
                d["log"] = [ln.rstrip() for ln in f.readlines()[-40:]]
        except OSError as e:
            d["log"] = short(e, 120)
        cap[gc.name] = d
    print(f"CAPTURE boot: {json.dumps(cap, default=str)}", flush=True)


def main():
    global CRASH0
    t0 = time.time()
    host = GameClient("host", 49854, make_user_dir("client_sight_night_host"))
    client = GameClient("client", 49855, make_user_dir("client_sight_night_client"))
    blocked = None
    try:
        try:
            boot(host, client)
            CRASH0 = crash_files()
        except Exception as e:  # a bring-up failure fails every row
            capture_boot(host, client, e)
            blocked = "boot"
        if not blocked:
            try:
                STAGED["ok"], STAGED["detail"] = stage(host, client)
            except Exception as e:  # a staging failure fails every row "staging"
                STAGED["ok"], STAGED["detail"] = False, f"staging raised {short(e)}"
            print(f"[client_sight_night] staging ok {STAGED['ok']}: {STAGED['detail']}", flush=True)
        for row, cells in ROWS:
            if blocked:
                ev(f"not run ({blocked})")
                for c in cells:
                    cell(c, False, blocked)
            else:
                try:
                    ROW_FNS[row](host, client)
                except Exception as e:  # every row runs after a failure
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
                print(f"[client_sight_night] shutdown {gc.name}: {short(e, 200)}", flush=True)
    names = [c for _, cells in ROWS for c in cells]
    failed = [c for c in names if not RESULTS.get(c)]
    print(f"\ntest_client_sight_night: {len(names) - len(failed)}/{len(names)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
