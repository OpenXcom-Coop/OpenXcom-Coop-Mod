"""R5-U2 S-E - test_coop_hidden_move.py: in a classic co-op battle the second player's machine (the client) shows
vanilla's HIDDEN MOVEMENT screen during the alien turn, lifted while an alien its side sees acts; the host's screen is
unchanged (R-R5U1-1; QU2-14 (a); spec rewrite/prompts/r5u2_pvp_presentation.md AMENDMENT U2-1 U2-1.7.4, which
replaces (f)'s old S-E file; TASK 0 pins: docs rewrite/r5u2-task0/se/CONSTANTS.md, boots Ea / Eb unchanged, Ec / Ed the
UE1 probe).

Before R5-U2 S-E the client keeps its own soldier selected through the alien side, so vanilla's term (selected unit
visible) always draws the map there. hiddenMovementShown TRUE = the map is drawn, FALSE = the HIDDEN MOVEMENT
screen.

ONE classic co-op boot (lobby key 48869, user dirs r5u2_e1_host / r5u2_e1_client): test_client_alien_sight's bring-up
(its boot copied with the key as a parameter, F10917) and its staging (W, D1, D2, A to P0, V = soldier 9 to V_TILE
facing 6; its asserts are the pins). The sampler is W2-H35's (battle_state host then client every 0.25 s inside
alien_cycle).
A "side-1 sample" of a machine is a sample whose side on that machine is 1 (the alien side).

Rows, in order (every row runs after a failure):
  CH2  it sees an alien its side sees walk: alien_cycle(SEED_A, HOLD) (A walks A_PATH into V's view),
       close_client_screen.
       CH2-walk (the walk is A_PATH; >= 3 client side-1 samples with client-A on an A_PATH tile; precondition),
       CH2-during (>= 1 of those samples has client hms True; guard).
  CH3  it does not see an unseen alien walk: client_turn(V, V_TURN_A) (staging: V's final facing V_TURN_A on both),
       alien_cycle(SEED_B, HOLD) (A walks B_PATH out of every view), close_client_screen.
       CH3-walk (the walk is B_PATH; no shot / hit / death / spot ev; >= 3 client side-1 samples; precondition),
       CH3-hidden (every client side-1 sample has hms False).
  CH1  off its own side with no alien acting it sees the screen: A base TU 0 on both, alien_cycle(SEED_D, 0.5, d_side).
       CH1-held (dSide: side 1 on both, the host's top NextTurnState, caught True; no A chain ev; precondition),
       CH1-screen (the dSide client hms False and every client side-1 sample False).
  CH4  the host is unchanged (guard), from CH2's and CH3's records. CH4-host (>= 1 host side-1 sample True with host-A
       on an A_PATH tile in CH2; every host side-1 sample with host-A on B_PATH[1:] False in CH3, F13343).
  Every row: <row>-common (hash_now full: every bucket EQUAL; event_state.desyncSeen false on both; 0 new crash files).

RED at the red commit E1 (unchanged build): CH1-screen, CH3-hidden FAIL; every other cell PASS. GREEN (E2, UE1): every
cell PASS. The window after a seen walk's end is EVIDENCE only.

Each row prints one "EVIDENCE <row>:" line, one PASS / FAIL line per cell and "ROW <row>: PASS|FAIL". A bring-up failure
prints ONE "CAPTURE boot:" line and fails every row "boot"; a staging failure fails the rows that need it "staging".
one run is the result; no skip, no second boot, no other fixture; exit 0 only when every cell passes,
else 2. run in the foreground to completion.

Run:  python tools/coop_test/test_coop_hidden_move.py
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
import test_client_alien_sight as AS   # its per-GameClient lock patch is wanted (sampler thread + driver)
from test_client_alien_sight import (A_ID, A_TU, P0, A_PATH, B_PATH, V_ID, V_TURN_A, SEED_A, SEED_B, SEED_D, HOLD,
                                        COMBAT_KINDS, CHAIN_KINDS, ua, snap)

KEY = "48869"          # this file's lobby key (R5-U2 spec (E))
MIN_SAMPLES = 3

ROWS = (("CH2", ("CH2-walk", "CH2-during", "CH2-common")),
        ("CH3", ("CH3-walk", "CH3-hidden", "CH3-common")),
        ("CH1", ("CH1-held", "CH1-screen", "CH1-common")),
        ("CH4", ("CH4-host", "CH4-common")))
RESULTS = {}
RECS = {}
CRASH0 = set()
_BUF = {"ev": [], "lines": []}


def short(e, n=400):
    return f"{type(e).__name__}: {str(e)[:n]}"


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
        assert_hash_clean(host, client, full=True, what=f"r5u2e {row}")
        h = "EQUAL"
    except AssertionError as e:
        h = str(e)[:600]
    ds = (event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen"))
    new = sorted(crash_files() - CRASH0)
    cell(f"{row}-common", h == "EQUAL" and ds == (False, False) and not new,
         f"hash_now full {h}; desyncSeen h/c {ds}; new crash files {new}")


def side1(rec, m):
    """The cycle's samples whose side on machine m ('h' / 'c') is 1."""
    return [r for r in rec["rows"] if r[m]["side"] == 1]


def table(rows, m):
    """(t, side, hms, A tile) per sample of machine m, compact."""
    def b(v):
        return "T" if v is True else ("F" if v is False else str(v))
    return [f"{r['t']:.2f}/{r[m]['side']}/{b(r[m]['hms'])}/{(ua(r[m]).get('pos') or (None, None))[:2]}" for r in rows]


def cycle_evidence(name, rec):
    kinds = [k for _, k in rec["hev"]]
    ev(f"{name}: walk {rec['path']} | host evs {kinds} | client side-1 (t/side/hms/A) {table(side1(rec, 'c'), 'c')} | "
       f"host side-1 {table(side1(rec, 'h'), 'h')} | sampler errors {rec['errors']} | pre {AS.fmt(rec['pre'])} | "
       f"post {AS.fmt(rec['post'])}")


# ===================== rows =====================


def row_ch2(host, client):
    rec = AS.alien_cycle(host, client, SEED_A, HOLD)
    RECS["CH2"] = rec
    cycle_evidence("CH2", rec)
    on = [r for r in side1(rec, "c") if ua(r["c"]).get("pos") in A_PATH]
    cell("CH2-walk", rec["path"] == A_PATH and len(on) >= MIN_SAMPLES,
         f"walk {rec['path']} (want A_PATH); client side-1 samples with A on an A_PATH tile {len(on)} "
         f"(>= {MIN_SAMPLES})")
    hms = [r["c"]["hms"] for r in on]
    cell("CH2-during", any(v is True for v in hms),
         f"client hms in those samples {hms} (want >= 1 True: the map drawn while a seen alien walks)")
    n, s = AS.close_client_screen(host, client)
    ev(f"CH2-close: closed {n}; {AS.fmt(s)}")
    common(host, client, "CH2")


def row_ch3(host, client):
    r, s = AS.client_turn(host, client, V_ID, V_TURN_A)
    dirs = (ua(s["h"], V_ID).get("dir"), ua(s["c"], V_ID).get("dir"))
    ev(f"CH3 staging: V turn intent {r}; V dir h/c {dirs}; {AS.fmt(s)}")
    if dirs != (V_TURN_A, V_TURN_A):
        for c in ("CH3-walk", "CH3-hidden"):
            cell(c, False, f"staging: V dir h/c {dirs} (want {V_TURN_A} on both)")
        common(host, client, "CH3")
        return
    rec = AS.alien_cycle(host, client, SEED_B, HOLD)
    RECS["CH3"] = rec
    cycle_evidence("CH3", rec)
    combat = [(q, k) for q, k in rec["hev"] if k in COMBAT_KINDS]
    cs = side1(rec, "c")
    cell("CH3-walk", rec["path"] == B_PATH and not combat and len(cs) >= MIN_SAMPLES,
         f"walk {rec['path']} (want B_PATH); combat evs {combat}; client side-1 samples {len(cs)} (>= {MIN_SAMPLES})")
    hms = [r["c"]["hms"] for r in cs]
    cell("CH3-hidden", bool(hms) and all(v is False for v in hms),
         f"client hms in its side-1 samples {hms} (want all False: the HIDDEN MOVEMENT screen through an unseen walk)")
    n, s = AS.close_client_screen(host, client)
    ev(f"CH3-close: closed {n}; {AS.fmt(s)}")
    common(host, client, "CH3")


def row_ch1(host, client):
    AS.both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": 0},
            ("tu",))
    rec = AS.alien_cycle(host, client, SEED_D, 0.5, d_side=True)
    RECS["CH1"] = rec
    cycle_evidence("CH1", rec)
    ds = rec["dSide"]
    ev(f"CH1 dSide: caught {rec.get('caught')}; host top {rec.get('dSideTop')}; hms h/c {ds['h']['hms']}/"
       f"{ds['c']['hms']}; {AS.fmt(ds)}")
    a_evs = [(q, k) for q, k in rec["hev"] if k in CHAIN_KINDS]
    held = (ds["h"]["side"] == 1 and ds["c"]["side"] == 1 and "NextTurnState" in (rec.get("dSideTop") or "")
            and rec.get("caught") is True)
    cell("CH1-held", held and not a_evs,
         f"side h/c {ds['h']['side']}/{ds['c']['side']}, host top {rec.get('dSideTop')}, caught {rec.get('caught')} "
         f"(want 1/1, NextTurnState, True); A chain evs {a_evs} (want none)")
    hms = [r["c"]["hms"] for r in side1(rec, "c")]
    cell("CH1-screen", ds["c"]["hms"] is False and all(v is False for v in hms),
         f"dSide client hms {ds['c']['hms']}, client side-1 samples {hms} (want False and all False: the screen "
         f"while no alien acts)")
    AS.settle_on_battlescape(client)
    AS.settle_on_battlescape(host)
    session.wait_seq_barrier(host, client, timeout=30)
    ev(f"CH1-after: {AS.fmt(snap(host, client))}")
    common(host, client, "CH1")


def row_ch4(host, client):
    r2, r3 = RECS.get("CH2"), RECS.get("CH3")
    h2 = [r["h"]["hms"] for r in side1(r2, "h") if ua(r["h"]).get("pos") in A_PATH] if r2 else None
    h3 = [r["h"]["hms"] for r in side1(r3, "h") if ua(r["h"]).get("pos") in B_PATH[1:]] if r3 else None
    ev(f"CH4: host side-1 hms with host-A on A_PATH (CH2) {h2}; on B_PATH[1:] (CH3) {h3}")
    ok2 = h2 is not None and any(v is True for v in h2)
    ok3 = h3 is not None and all(v is False for v in h3)
    cell("CH4-host", ok2 and ok3,
         f"CH2 {h2} (want >= 1 True; None = no CH2 record); CH3 {h3} (want all False; None = no CH3 record)")
    common(host, client, "CH4")


ROW_FNS = {"CH2": row_ch2, "CH3": row_ch3, "CH1": row_ch1, "CH4": row_ch4}


# ===================== bring-up =====================


def boot(host, client, key):
    """test_client_alien_sight.boot with the lobby key as a parameter (F10917: AS.KEY is that file's)."""
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    host.ok({"cmd": "set_seed", "seed": AS.SEED_ROSTER})
    raw.skirmish_host(host, key)
    raw.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": raw.CLIENT_PLAYER})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: raw.lobby(host).get("buttonVisible") or None)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": AS.SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == AS.MAP_FP and cs.get("mapFingerprint") == AS.MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r} (baked {AS.MAP_FP!r})")
    assert seated.get("soldierIds") == AS.SEATED, f"seated {seated.get('soldierIds')} (baked {AS.SEATED})"
    pinned = pin_ai_neutral(host, client, tag="r5u2e")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    types = ((uh.get(A_ID) or {}).get("type"), (uc.get(A_ID) or {}).get("type"))
    assert types == (AS.A_TYPE, AS.A_TYPE), f"A type host/client {types} (want {AS.A_TYPE})"
    for uid, u in sorted(uh.items()):
        if u.get("faction") == 0 and not u.get("isOut"):  # FACTION_PLAYER
            AS.both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                   "value": 0}, ("tu",))
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="r5u2e bring-up")
    AS.both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": A_TU},
            ("tu",))


def main():
    global CRASH0
    t0 = time.time()
    host = GameClient("host", 49852, make_user_dir("r5u2_e1_host"))
    client = GameClient("client", 49853, make_user_dir("r5u2_e1_client"))
    blocked = None
    try:
        try:
            boot(host, client, KEY)
            CRASH0 = crash_files()
        except Exception as e:  # a bring-up failure fails every row
            AS.capture_boot(host, client, e)
            blocked = "boot"
        if blocked is None:
            try:
                AS.staging(host, client)
                s = snap(host, client)
                assert [ua(s[m]).get("pos") for m in ("h", "c")] == [P0, P0], f"A not on P0: {AS.fmt(s)}"
            except Exception as e:
                print(f"STAGING: {short(e, 600)}", flush=True)
                blocked = "staging"
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
                print(f"[r5u2e] shutdown {gc.name}: {short(e, 200)}", flush=True)
    names = [c for _, cells in ROWS for c in cells]
    failed = [c for c in names if not RESULTS.get(c)]
    print(f"\ntest_coop_hidden_move: {len(names) - len(failed)}/{len(names)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
