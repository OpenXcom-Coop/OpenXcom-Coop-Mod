"""test_client_sight_fire.py: at night, on the co-op second player's machine an X-COM soldier's list of
seen units follows vanilla after an incendiary blast's fire lights a dark alien (fire_reveal). The second player's
off-turn view follows vanilla, and an alien no X-COM soldier sees stays hidden.

Vanilla refreshes sight right after a blast's light (TileEngine::explode: calculateFOV(centre, radius + 1), which
re-checks each viewer's units inside its angle through the blast circle). The second player's machine recomputes the
same light (applyDelta step (8a)) and then refreshes sight over the box of the changed tiles + 1, which stands in for
the blast's centre and radius + 1 (connectionTCP.cpp coopClientEventSight).

Fixture facts (equal in two boots): after the blast the host's V sees A; a client without the refresh does not. V_N
is the first tile of the fixture search that keeps A_N inside V's sight angle through the blast circle (vanilla's
refresh re-checks only the units inside it) and has a line of sight to A.

ONE classic co-op NIGHT boot (lobby key 46642, user dirs client_sight_fire_host / client_sight_fire_client):
test_client_alien_sight's boot (copied) with test_light_scope's write_night_cfg (darkness 15) in the host's user dir
before the host starts and its night_precondition after it: SEED_ROSTER 1 before open_new_battle, SEED_MAP 1 before
newbattle_ok, seat_count 2, pin_ai_neutral (A = the only alien, base TU 0), reactions 0 for every X-COM unit on both.
Staging (a miss fails every cell "staging"): park 8, 12, 13, 14, 10 and T (11) on PARK; A to A_N facing 5; V (9) to
V_N facing V_N_DIR0; client turn intent V -> V_N_DIR; every teleport is followed by light_recompute on both (a teleport
does not recompute light). Dark precondition: A_N's units light <= DARK_MAX on both; vis false on both; A in neither
list(V).

Row fire_reveal: battle_give STR_ROCKET_LAUNCHER + STR_INCENDIARY_ROCKET to T on both (ids equal, not -1); tele T to
T_F facing T_DIR + light_recompute; host set_seed SEED_FIRE; host battle_fire {unit T, mode aimed, weapon_id
<launcher>, FIRE_TARGET, tu 255}; bt_action_end, wait_host_idle, seq barrier.
  fire_reveal-pre     before the shot: T on T_F; A_N dark; vis false on both; A in neither list(V); A's health / fire
                      equal, fire 0.
  fire_reveal-burn    after the chain: burning tiles = FIRE_TILES on both; A's health / fire unchanged; A in host
                      list(V) (precondition: vanilla's blast refresh).
  fire_reveal-list    list(client, V) equal to list(host, V).
  fire_reveal-common  hash_now full (every bucket EQUAL); event_state.desyncSeen false on both; 0 new crash files.
"vis(gc)" = A's battle_state units[].visible; "list(gc, U)" = U's units[].visibleUnits.
A client without the blast refresh fails fire_reveal-list; every other cell passes. With it, every cell passes.

One "EVIDENCE fire_reveal:" line, one PASS / FAIL line per cell, "ROW fire_reveal: PASS|FAIL". A bring-up failure
prints ONE "CAPTURE boot:" line and fails every cell "boot". No skip, no second boot, no other fixture; exit 0 only
when every cell passes, else 2.

Run:  python tools/coop_test/test_client_sight_fire.py
"""

import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_delta_core import both, tele_both
import test_light_scope as ls
# vis, ua, snap, fmt, states, client_turn, short and the per-GameClient lock (on import)
import test_client_alien_sight as cas

# ----- fixture values (equal in two boots) -----
SEED_ROSTER, SEED_MAP = 1, 1
MAP_FP = -4.48310638993e+18
SEATED = [8, 9]
A_ID, A_TYPE = 1000000, "STR_SECTOID_SOLDIER"   # the only alien (pin_ai_neutral: base TU 0)
A_BOOT, A_BOOT_DIR = (27, 12, 0), 5             # A at boot
DARKNESS, DARK_MAX = 15, 5                      # battle.cfg darkness; dark: A_N units light <= 5 (shade > 9)
A_N, A_N_DIR = (20, 18, 0), 5                   # units light 5 / 5 after the parking
V_ID, T_ID = 9, 11                              # V watches (client seat), T shoots (host seat)
PARK = ((8, (10, 13, 0)), (12, (11, 13, 0)), (13, (10, 14, 0)), (14, (10, 15, 0)), (10, (10, 16, 0)),
        (T_ID, (10, 17, 0)))                    # the same parking as test_client_sight_night; facing kept
V_N, V_N_DIR0, V_N_DIR = (13, 25, 0), 0, 1      # the first tile of the fixture search with a line of sight
T_F, T_DIR = (24, 27, 0), 7                     # first searched tile where T's shot is accepted; facing FIRE_TARGET
FIRE_TARGET = (20, 24, 0)                       # 6 tiles south of A_N; the blast centre at SEED_FIRE (radius 3)
FIRE_TILES = sorted([(17, 24, 0)] + [(18, y, 0) for y in (23, 24, 25)] + [(19, y, 0) for y in range(22, 27)]
                    + [(x, y, 0) for x in (20, 21, 22) for y in range(21, 28)] + [(23, y, 0) for y in range(22, 27)])
SEED_FIRE = 1                                   # host set_seed right before battle_fire
LAUNCHER, ROCKET = "STR_ROCKET_LAUNCHER", "STR_INCENDIARY_ROCKET"
BOX = (13, 27, 17, 31)                          # tile_census box x0, x1, y0, y1 (z 0) around FIRE_TARGET and A_N
KEY = "46642"                                   # this file's lobby key
CUE_RE = re.compile(r"\[coop-cue\] explosion seq (\d+) actionId (\d+): (\{.*\})\s*$")

ROWS = (("fire_reveal", ("fire_reveal-pre", "fire_reveal-burn", "fire_reveal-list", "fire_reveal-common")),)
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
        assert_hash_clean(host, client, full=True, what=f"client_sight_fire {row}")
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


def evs_a(gc, seq0):
    return [(e.get("seq"), e.get("kind"), e.get("actionId"))
            for e in (gc.cmd({"cmd": "event_log", "tail": 400}).get("events") or []) if (e.get("seq") or 0) > seq0]


def recompute(host, client):
    rc, rh = client.cmd({"cmd": "light_recompute"}), host.cmd({"cmd": "light_recompute"})
    return bool(rh.get("ok") and rc.get("ok"))


def tele_rc(host, client, uid, t, d):
    tele_both(host, client, uid, t, d)
    return recompute(host, client)


def light(host, client, tag, tiles):
    ch, cc = ls.census(host, f"fire_{tag}_h"), ls.census(client, f"fire_{tag}_c")
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


def a_hf(gc):
    for u in battle_state(gc).get("units") or []:
        if u.get("id") == A_ID:
            return u.get("health"), u.get("unitFire")
    return None


def burning(gc):
    r = gc.cmd({"cmd": "tile_census", "x0": BOX[0], "x1": BOX[1], "y0": BOX[2], "y1": BOX[3], "z0": 0, "z1": 0})
    return sorted((t["x"], t["y"], t["z"]) for t in (r.get("tiles") or []) if t and t.get("fire"))


def explosion_cues(host, seq0):
    out = []
    try:
        with open(os.path.join(host.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = CUE_RE.search(line.rstrip("\r\n"))
                if m and int(m.group(1)) > seq0:
                    p = json.loads(m.group(3))
                    cv = p.get("centreVoxel") or {}
                    out.append((int(m.group(1)), (cv.get("x", 0) // 16, cv.get("y", 0) // 16, cv.get("z", 0) // 24),
                                p.get("radius"), p.get("power")))
    except (OSError, ValueError) as e:
        out.append(short(e, 120))
    return out


def stage(host, client):
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


# ===================== row =====================


def row_fire_reveal(host, client):
    cells = dict(ROWS)["fire_reveal"]
    if not STAGED["ok"]:
        staging_miss(cells, STAGED["detail"])
        return common(host, client, "fire_reveal")
    req = {"cmd": "battle_give", "unit": T_ID, "item": LAUNCHER, "ammo": ROCKET}
    rc_g = client.cmd(dict(req))  # client first
    rh_g = host.cmd(dict(req))
    session.wait_seq_barrier(host, client, timeout=30)
    wid, aid = rh_g.get("weaponId"), rh_g.get("ammoId")
    if not (rh_g.get("ok") and rc_g.get("ok") and (wid, aid) == (rc_g.get("weaponId"), rc_g.get("ammoId"))
            and wid not in (None, -1) and aid not in (None, -1)):
        staging_miss(cells, f"battle_give host {rh_g} client {rc_g} (want ids equal, not -1)")
        return common(host, client, "fire_reveal")
    rc = tele_rc(host, client, T_ID, T_F, T_DIR)
    lt0 = light(host, client, "pre_shot", [A_N, T_F, FIRE_TARGET])
    s1 = cas.snap(host, client)
    hf0 = (a_hf(host), a_hf(client))
    burn0 = (burning(host), burning(client))
    lv1, vv1 = lists(s1, V_ID), avis(s1)
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    host.ok({"cmd": "set_seed", "seed": SEED_FIRE})
    fire = host.cmd({"cmd": "battle_fire", "unit": T_ID, "mode": "aimed", "weapon_id": wid, "x": FIRE_TARGET[0],
                     "y": FIRE_TARGET[1], "z": FIRE_TARGET[2], "tu": 255})
    host.wait_for("host bt_action_end after the shot",
                  lambda: any(k == "bt_action_end" for _, k, _a in evs_a(host, seq0)) or None, timeout=30)
    session.wait_host_idle(host, client, timeout=30)
    session.wait_seq_barrier(host, client, timeout=30)
    s2 = cas.snap(host, client)
    hf1 = (a_hf(host), a_hf(client))
    burn1 = (burning(host), burning(client))
    lt1 = light(host, client, "post_shot", [A_N, FIRE_TARGET])
    lv2, vv2, lt2 = lists(s2, V_ID), avis(s2), lists(s2, T_ID)
    ev(f"fire_reveal: give h/c {wid}/{rc_g.get('weaponId')} ammo {aid}/{rc_g.get('ammoId')} | T tele {T_F} facing "
       f"{T_DIR} + recompute {rc} | light before h/c {lt0[0]} mismatch {lt0[1]} | pre {cas.fmt(s1)} | shot {fire} "
       f"chain host {evs_a(host, seq0)} client {evs_a(client, seq0)} | explosion cues (seq, centre, radius, power) "
       f"{explosion_cues(host, seq0)} | burning h/c {len(burn1[0])}/{len(burn1[1])} tiles | A health/fire before "
       f"{hf0} after {hf1} | A's tile light after h/c {lt1[0]} mismatch {lt1[1]} | vis h/c {vv2} | list(T) h/c {lt2} | "
       f"client selected {s2['c']['sel']} | after {cas.fmt(s2)}")
    cell("fire_reveal-pre", rc and at(s1, T_ID, T_F, T_DIR) and dark(lt0) and vv1 == (False, False)
         and all(A_ID not in (x or []) for x in lv1) and hf0[0] == hf0[1] and (hf0[0] or (0, 1))[1] == 0
         and burn0 == ([], []),
         f"T on {T_F} facing {T_DIR} on both {at(s1, T_ID, T_F, T_DIR)}; A_N dark {dark(lt0)}; vis h/c {vv1}; "
         f"list(V) h/c {lv1}; A health/fire h/c {hf0}; burning h/c {burn0} (want True, dark, False / False, no A, "
         f"equal with fire 0, none)")
    fire_ok = burn1[0] == FIRE_TILES and burn1[1] == FIRE_TILES
    cell("fire_reveal-burn", fire_ok and hf1 == hf0 and A_ID in (lv2[0] or []),
         f"burning tiles = FIRE_TILES on both {fire_ok}; A health/fire h/c {hf1} (staged {hf0}); host list(V) {lv2[0]} "
         f"(precondition: the pinned fire, A unchanged, holds {A_ID})")
    cell("fire_reveal-list", lv2[1] == lv2[0], f"list(V) host {lv2[0]} client {lv2[1]} (want equal)")
    common(host, client, "fire_reveal")


ROW_FNS = {"fire_reveal": row_fire_reveal}


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
    pinned = pin_ai_neutral(host, client, tag="client_sight_fire")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    types = ((uh.get(A_ID) or {}).get("type"), (uc.get(A_ID) or {}).get("type"))
    assert types == (A_TYPE, A_TYPE), f"A type host/client {types} (want {A_TYPE})"
    for uid, u in sorted(uh.items()):
        if u.get("faction") == 0 and not u.get("isOut"):  # FACTION_PLAYER
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="client_sight_fire bring-up")
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
    host = GameClient("host", 49858, make_user_dir("client_sight_fire_host"))
    client = GameClient("client", 49859, make_user_dir("client_sight_fire_client"))
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
            print(f"[client_sight_fire] staging ok {STAGED['ok']}: {STAGED['detail']}", flush=True)
        for row, cells in ROWS:
            if blocked:
                ev(f"not run ({blocked})")
                for c in cells:
                    cell(c, False, blocked)
            else:
                try:
                    ROW_FNS[row](host, client)
                except Exception as e:  # the row's remaining cells fail; the summary still prints
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
                print(f"[client_sight_fire] shutdown {gc.name}: {short(e, 200)}", flush=True)
    names = [c for _, cells in ROWS for c in cells]
    failed = [c for c in names if not RESULTS.get(c)]
    print(f"\ntest_client_sight_fire: {len(names) - len(failed)}/{len(names)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
