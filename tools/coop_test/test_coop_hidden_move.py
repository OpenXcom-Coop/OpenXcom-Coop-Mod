"""test_coop_hidden_move.py: in a classic co-op battle the second player's machine (the client) shows
vanilla's HIDDEN MOVEMENT screen during the alien turn, lifted while an alien its side sees acts; the host's screen is
unchanged.

The client keeps its own soldier selected through the alien side, so vanilla's term (the selected unit is visible)
would always draw the map there. Off its own side the client reads the acting unit from its open action instead
(connectionTCP.cpp coopHiddenMovementActorTerm). hiddenMovementShown TRUE = the map is drawn, FALSE = the HIDDEN
MOVEMENT screen.

ONE classic co-op boot (lobby key 48869, user dirs coop_hidden_move_host / coop_hidden_move_client):
test_client_alien_sight's bring-up (its boot copied here with the lobby key as a parameter) and its staging
(walk_to_start, first_path_walk, second_path_walk, A to A_START, V = soldier 9 to V_TILE facing 6; its asserts check
the fixture values). The sampler is test_client_alien_sight's (battle_state host then client every 0.25 s inside
alien_cycle).
A "side-1 sample" of a machine is a sample whose side on that machine is 1 (the alien side).

Rows, in order (every row runs after a failure):
  seen_walk  it sees an alien its side sees walk: alien_cycle(SEED_WALK_IN, HOLD) (A walks IN_PATH into V's view),
       close_client_screen.
       seen_walk-walk (the walk is IN_PATH; >= 3 client side-1 samples with client-A on an IN_PATH tile; precondition),
       seen_walk-during (>= 1 of those samples has client hms True; guard).
  unseen_walk  it does not see an unseen alien walk: client_turn(V, V_TURN_SEE) (staging: V's final facing
       V_TURN_SEE on both), alien_cycle(SEED_WALK_OUT, HOLD) (A walks OUT_PATH out of every view),
       close_client_screen.
       unseen_walk-walk (the walk is OUT_PATH; no shot / hit / death / spot ev; >= 3 client side-1 samples;
       precondition),
       unseen_walk-hidden (every client side-1 sample has hms False).
  idle_alien_turn  off its own side with no alien acting it sees the screen: A base TU 0 on both,
       alien_cycle(SEED_SIDE_CHANGE, 0.5, held_read).
       idle_alien_turn-held (heldRead: side 1 on both, the host's top NextTurnState, caught True; no A chain ev;
       precondition),
       idle_alien_turn-screen (the heldRead client hms False and every client side-1 sample False).
  host_screen  the host is unchanged (guard), from seen_walk's and unseen_walk's records. host_screen-unchanged
       (>= 1 host side-1 sample True with host-A on an IN_PATH tile in seen_walk; every host side-1 sample with
       host-A on OUT_PATH[1:] False in unseen_walk: a sample taken mid-step on OUT_PATH[0] may still read True).
  Every row: <row>-common (hash_now full: every bucket EQUAL; event_state.desyncSeen false on both; 0 new crash
  files).

A client that keeps vanilla's term fails idle_alien_turn-screen and unseen_walk-hidden; every other cell passes.
The window after a seen walk's end is EVIDENCE only.

Each row prints one "EVIDENCE <row>:" line, one PASS / FAIL line per cell and "ROW <row>: PASS|FAIL". A bring-up failure
prints ONE "CAPTURE boot:" line and fails every row "boot"; a staging failure fails the rows that need it "staging".
One run is the result: no skip, no second boot, no other fixture. Exit 0 only when every cell passes, else 2. Run it
in the foreground to completion.

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
from test_client_alien_sight import (A_ID, A_TU, A_START, IN_PATH, OUT_PATH, V_ID, V_TURN_SEE, SEED_WALK_IN,
                                     SEED_WALK_OUT, SEED_SIDE_CHANGE, HOLD,
                                        COMBAT_KINDS, CHAIN_KINDS, ua, snap)

KEY = "48869"          # this file's lobby key
MIN_SAMPLES = 3

ROWS = (("seen_walk", ("seen_walk-walk", "seen_walk-during", "seen_walk-common")),
        ("unseen_walk", ("unseen_walk-walk", "unseen_walk-hidden", "unseen_walk-common")),
        ("idle_alien_turn", ("idle_alien_turn-held", "idle_alien_turn-screen", "idle_alien_turn-common")),
        ("host_screen", ("host_screen-unchanged", "host_screen-common")))
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
        assert_hash_clean(host, client, full=True, what=f"hidden_move {row}")
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


def row_seen_walk(host, client):
    rec = AS.alien_cycle(host, client, SEED_WALK_IN, HOLD)
    RECS["seen_walk"] = rec
    cycle_evidence("seen_walk", rec)
    on = [r for r in side1(rec, "c") if ua(r["c"]).get("pos") in IN_PATH]
    cell("seen_walk-walk", rec["path"] == IN_PATH and len(on) >= MIN_SAMPLES,
         f"walk {rec['path']} (want IN_PATH); client side-1 samples with A on an IN_PATH tile {len(on)} "
         f"(>= {MIN_SAMPLES})")
    hms = [r["c"]["hms"] for r in on]
    cell("seen_walk-during", any(v is True for v in hms),
         f"client hms in those samples {hms} (want >= 1 True: the map drawn while a seen alien walks)")
    n, s = AS.close_client_screen(host, client)
    ev(f"seen_walk-close: closed {n}; {AS.fmt(s)}")
    common(host, client, "seen_walk")


def row_unseen_walk(host, client):
    r, s = AS.client_turn(host, client, V_ID, V_TURN_SEE)
    dirs = (ua(s["h"], V_ID).get("dir"), ua(s["c"], V_ID).get("dir"))
    ev(f"unseen_walk staging: V turn intent {r}; V dir h/c {dirs}; {AS.fmt(s)}")
    if dirs != (V_TURN_SEE, V_TURN_SEE):
        for c in ("unseen_walk-walk", "unseen_walk-hidden"):
            cell(c, False, f"staging: V dir h/c {dirs} (want {V_TURN_SEE} on both)")
        common(host, client, "unseen_walk")
        return
    rec = AS.alien_cycle(host, client, SEED_WALK_OUT, HOLD)
    RECS["unseen_walk"] = rec
    cycle_evidence("unseen_walk", rec)
    combat = [(q, k) for q, k in rec["hev"] if k in COMBAT_KINDS]
    cs = side1(rec, "c")
    cell("unseen_walk-walk", rec["path"] == OUT_PATH and not combat and len(cs) >= MIN_SAMPLES,
         f"walk {rec['path']} (want OUT_PATH); combat evs {combat}; client side-1 samples {len(cs)} (>= {MIN_SAMPLES})")
    hms = [r["c"]["hms"] for r in cs]
    cell("unseen_walk-hidden", bool(hms) and all(v is False for v in hms),
         f"client hms in its side-1 samples {hms} (want all False: the HIDDEN MOVEMENT screen through an unseen walk)")
    n, s = AS.close_client_screen(host, client)
    ev(f"unseen_walk-close: closed {n}; {AS.fmt(s)}")
    common(host, client, "unseen_walk")


def row_idle_alien_turn(host, client):
    AS.both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": 0},
            ("tu",))
    rec = AS.alien_cycle(host, client, SEED_SIDE_CHANGE, 0.5, held_read=True)
    RECS["idle_alien_turn"] = rec
    cycle_evidence("idle_alien_turn", rec)
    ds = rec["heldRead"]
    ev(f"idle_alien_turn heldRead: caught {rec.get('caught')}; host top {rec.get('heldReadTop')}; "
       f"hms h/c {ds['h']['hms']}/{ds['c']['hms']}; {AS.fmt(ds)}")
    a_evs = [(q, k) for q, k in rec["hev"] if k in CHAIN_KINDS]
    held = (ds["h"]["side"] == 1 and ds["c"]["side"] == 1 and "NextTurnState" in (rec.get("heldReadTop") or "")
            and rec.get("caught") is True)
    cell("idle_alien_turn-held", held and not a_evs,
         f"side h/c {ds['h']['side']}/{ds['c']['side']}, host top {rec.get('heldReadTop')}, caught {rec.get('caught')} "
         f"(want 1/1, NextTurnState, True); A chain evs {a_evs} (want none)")
    hms = [r["c"]["hms"] for r in side1(rec, "c")]
    cell("idle_alien_turn-screen", ds["c"]["hms"] is False and all(v is False for v in hms),
         f"heldRead client hms {ds['c']['hms']}, client side-1 samples {hms} (want False and all False: the screen "
         f"while no alien acts)")
    AS.settle_on_battlescape(client)
    AS.settle_on_battlescape(host)
    session.wait_seq_barrier(host, client, timeout=30)
    ev(f"idle_alien_turn-after: {AS.fmt(snap(host, client))}")
    common(host, client, "idle_alien_turn")


def row_host_screen(host, client):
    r2, r3 = RECS.get("seen_walk"), RECS.get("unseen_walk")
    h2 = [r["h"]["hms"] for r in side1(r2, "h") if ua(r["h"]).get("pos") in IN_PATH] if r2 else None
    h3 = [r["h"]["hms"] for r in side1(r3, "h") if ua(r["h"]).get("pos") in OUT_PATH[1:]] if r3 else None
    ev(f"host_screen: host side-1 hms with host-A on IN_PATH (seen_walk) {h2}; on OUT_PATH[1:] (unseen_walk) {h3}")
    ok2 = h2 is not None and any(v is True for v in h2)
    ok3 = h3 is not None and all(v is False for v in h3)
    cell("host_screen-unchanged", ok2 and ok3,
         f"seen_walk {h2} (want >= 1 True; None = no seen_walk record); unseen_walk {h3} (want all False; "
         f"None = no unseen_walk record)")
    common(host, client, "host_screen")


ROW_FNS = {"seen_walk": row_seen_walk, "unseen_walk": row_unseen_walk, "idle_alien_turn": row_idle_alien_turn,
           "host_screen": row_host_screen}


# ===================== bring-up =====================


def boot(host, client, key):
    """test_client_alien_sight.boot with the lobby key as a parameter (AS.KEY is test_client_alien_sight's own key)."""
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
    pinned = pin_ai_neutral(host, client, tag="hidden_move")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    types = ((uh.get(A_ID) or {}).get("type"), (uc.get(A_ID) or {}).get("type"))
    assert types == (AS.A_TYPE, AS.A_TYPE), f"A type host/client {types} (want {AS.A_TYPE})"
    for uid, u in sorted(uh.items()):
        if u.get("faction") == 0 and not u.get("isOut"):  # FACTION_PLAYER
            AS.both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                   "value": 0}, ("tu",))
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="hidden_move bring-up")
    AS.both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": A_TU},
            ("tu",))


def main():
    global CRASH0
    t0 = time.time()
    host = GameClient("host", 49852, make_user_dir("coop_hidden_move_host"))
    client = GameClient("client", 49853, make_user_dir("coop_hidden_move_client"))
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
                assert [ua(s[m]).get("pos") for m in ("h", "c")] == [A_START, A_START], f"A not on A_START: {AS.fmt(s)}"
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
                print(f"[hidden_move] shutdown {gc.name}: {short(e, 200)}", flush=True)
    names = [c for _, cells in ROWS for c in cells]
    failed = [c for c in names if not RESULTS.get(c)]
    print(f"\ntest_coop_hidden_move: {len(names) - len(failed)}/{len(names)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
