"""W2-H35c (CAP-1 day) - test_w2_client_sight_more.py: on the co-op second player's machine each X-COM soldier's list of
seen units and an alien's `visible` flag follow vanilla when a soldier kneels or stands up in front of another soldier
(C3) and when an X-COM soldier mind-controls the alien another soldier sees (C18) (spec
rewrite/prompts/w2h35c_r5u8b_captures.md (f); rulings W2-H35b QB-3 (a), R-R5U1-1: the second player's off-turn view
follows vanilla; D171: hidden aliens stay hidden; QH35C-1 .. QH35C-7 (a)).

Vanilla re-runs everyone's sight through the kneeler's tile right after a kneel or a stand-up
(BattlescapeGame::kneel, radius 1) and clears and rebuilds every list within the maximum view distance right after a
successful mind control (TileEngine::psiAttack). The second player's machine refreshes only the kneeler at a `kneel`
ev and only adds hostiles around the victim at a mind control (W2-H35b E6), so a now-friendly alien stays listed.

TASK 0 verdicts (docs rewrite/w2h35c-task0/CONSTANTS.md, capture boots Da and Db equal, S28): C3 CONFIRMED (kneel: the
host's V lists A, the client's does not and A stays undrawn there; stand-up: the host's V drops A, the client's keeps
it); C18 CONFIRMED (seed 1: the host's V drops the mind-controlled A, the client's keeps it); C7 REFUTED (the client's V
lists a converted unit at once, F15015): no C7 row (its pins stay in CONSTANTS.md). Night case C6 is in
test_w2_client_sight_fuse.py.

ONE classic co-op day boot (lobby key 46643, user dirs w2h35c_d_host / w2h35c_d_client): SAE's boot (copied):
SEED_ROSTER 1 before open_new_battle, SEED_MAP 1 before newbattle_ok, seat_count 2, pin_ai_neutral (A = the only alien),
reactions 0 for every X-COM unit on both, A base TU 54; A on A_BOOT facing 5 on both. Every teleport is followed by
light_recompute on both (R-H35B-SB-1); every staging write goes to the CLIENT first (F607).

Rows, in order (every row runs after a failure):
  C3   tele A to A3_TILE facing 5, V (9) to V3_TILE facing 6, K (8) to K3_TILE facing 2 (A behind K); K TU max;
       client turn intents V -> 5 -> 6; client kneel intent K {kneel true}; seq barrier.
       C3-pre   before the kneel: K standing on both; vis(A) false on both; A in neither machine's list(V).
       C3-host  after the kneel: host K kneeled and A in host list(V) (precondition: vanilla's refresh).
       C3-here  here(client, A) true.                     C3-list  A in list(client, V).
       C3s-pre  after client turn intents V -> 5 -> 6: A in list(V) on both; K kneeled on both.
       C3s-host after K TU max and client kneel intent K {kneel false}, barrier: host K standing and A not in host
                list(V) (precondition).
       C3s-list A not in list(client, V).
  C18  tele C (8) to C18_TILE facing C18_DIR; client turn intents V -> 5 -> 6; battle_give STR_PSI_AMP to C (clear
       hands; ids equal, not -1); set_stat C psiSkill 100, A psiStrength 0, C TU max; host set_seed SEED_C18; client
       psi intent {action mc, weapon amp, target A3_TILE, targetUnit A}; barrier (a host infobox dismissed host-only).
       C18-pre  before the psi: A faction 1 on both; A in list(V) on both; amp ids equal.
       C18-host after the chain: host A faction 0 and mindControllerId 8; A not in host list(V) (precondition).
       C18-list A not in list(client, V).
  Every row: <row>-common (hash_now full: every bucket EQUAL; event_state.desyncSeen false on both; 0 new crash files).
"vis(gc)" / "here(gc)" = A's battle_state units[].visible / visibleHere on that machine; "list(gc, U)" = U's
units[].visibleUnits (R5-U1 S-A's T1 probe).

RED at the red commit (unchanged build): C3-here, C3-list, C3s-list, C18-list FAIL; every other cell PASS. GREEN
(W2-H35c G3, G1 + G18): every cell PASS.

Each row prints one "EVIDENCE <row>:" line, one PASS / FAIL line per cell and "ROW <row>: PASS|FAIL". A bring-up
failure prints ONE "CAPTURE boot:" line and fails every row "boot"; a staging miss fails that row's cells "staging".
WV-D99 / WV-D100: one run is the result; no skip, no second boot, no other fixture; exit 0 only when every cell
passes, else 2. WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_client_sight_more.py
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
from test_w2_delta_core import both, tele_both
# short, states, top and the per-GameClient lock (installed on import)
import test_w2_client_alien_sight as cas

# ----- TASK 0 pins (CONSTANTS.md; boots Da and Db equal, S28) -----
SEED_ROSTER, SEED_MAP = 1, 1
MAP_FP = -4.48310638993e+18
SEATED = [8, 9]
A_ID, A_TYPE = 1000000, "STR_SECTOID_SOLDIER"   # the only alien (pin_ai_neutral)
A_BOOT, A_BOOT_DIR, A_TU = (27, 12, 0), 5, 54   # A at boot; A base TU 54 (SAE)
V_ID, K_ID, C_ID = 9, 8, 8                      # V watches (never the actor); K kneels, C mind-controls (the same 8)
A3_TILE, A3_DIR = (20, 18, 0), 5
V3_TILE, V3_DIR = (28, 18, 0), 6                # V sees A along row 18 when nothing blocks
K3_TILE, K3_DIR = (27, 18, 0), 2                # C3 oracle's 1st candidate: K standing blocks V's line, kneeling not
C18_TILE, C18_DIR = (24, 16, 0), 6              # C18 rule's first tile (Round(distance) 4 from A3_TILE, off V's line)
SEED_C18 = 1                                    # host set_seed right before the psi order (success on the first try)
PSI_SKILL, A_PSI_STRENGTH = 100, 0
TU_MAX = 255
ORDER_S = 30
KEY = "46643"                                   # this file's lobby key (spec (G))

ROWS = (("C3", ("C3-pre", "C3-host", "C3-here", "C3-list", "C3s-pre", "C3s-host", "C3s-list", "C3-common")),
        ("C18", ("C18-pre", "C18-host", "C18-list", "C18-common")))
RESULTS = {}
CRASH0 = set()
_BUF = {"ev": [], "lines": []}
short = cas.short
LOG_RE = re.compile(r"\[coop-(?:cue|delta)\] (?:(\w+) seq (\d+) actionId \d+: |attached to seq (\d+) kind=(\w+) "
                    r"\(\d+ bytes\): )(.*)$")


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
        assert_hash_clean(host, client, full=True, what=f"w2h35c {row}")
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


# ===================== probes and levers (shared with test_w2_client_sight_fuse) =====================


def view(gc):
    """battle_state T1 view: units by id (pos, dir, vis, here, sees sorted, faction, kneeled, mindControllerId, tu)."""
    bs = battle_state(gc)
    units = {}
    for u in bs.get("units") or []:
        units[u.get("id")] = {"pos": (u.get("x"), u.get("y"), u.get("z")), "dir": u.get("direction"),
                              "vis": u.get("visible"), "here": u.get("visibleHere"),
                              "sees": sorted(u.get("visibleUnits") or []), "f": u.get("faction"),
                              "kn": u.get("kneeled"), "mc": u.get("mindControllerId"), "tu": u.get("tu")}
    return {"units": units, "side": bs.get("side"), "sel": bs.get("selectedId")}


def snap(host, client):
    return {"h": view(host), "c": view(client)}


def uu(s, m, uid=A_ID):
    return s[m]["units"].get(uid) or {}


def pair(s, key, uid=A_ID):
    return uu(s, "h", uid).get(key), uu(s, "c", uid).get(key)


def at(s, uid, pos, d):
    return all(uu(s, m, uid).get("pos") == pos and uu(s, m, uid).get("dir") == d for m in ("h", "c"))


def evs_a(gc, seq0):
    return [(e.get("seq"), e.get("kind"), e.get("actionId"))
            for e in (gc.cmd({"cmd": "event_log", "tail": 400}).get("events") or []) if (e.get("seq") or 0) > seq0]


def host_lines(host, seq0):
    """The host's `[coop-cue] <kind> seq N ...: {payload}` and `[coop-delta] attached to seq N kind=<k> ...: {delta}`
    lines after seq0 (the ev payloads; event_log carries none, TASK 0 F15402)."""
    out = []
    try:
        with open(os.path.join(host.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = LOG_RE.search(line.rstrip("\r\n"))
                if m and int(m.group(2) or m.group(3)) > seq0:
                    out.append(f"{'cue' if m.group(1) else 'delta'} {m.group(1) or m.group(4)} "
                               f"{m.group(2) or m.group(3)} {m.group(5)[:200]}")
    except OSError as e:
        out.append(short(e, 120))
    return out


def recompute(host, client):
    rc, rh = client.cmd({"cmd": "light_recompute"}), host.cmd({"cmd": "light_recompute"})
    return bool(rh.get("ok") and rc.get("ok"))


def tele_rc(host, client, uid, t, d):
    """tele_both, then light_recompute on both (R-H35B-SB-1 S-1: levers never recompute light)."""
    tele_both(host, client, uid, t, d)
    return recompute(host, client)


def tu_max(host, client, uid):
    return both(host, client, {"cmd": "battle_set_unit_state", "unit": uid, "tu": TU_MAX}, ("tu",))["tu"]


def set_stat(host, client, uid, stat, value):
    return both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": stat,
                               "value": value}, ("tu",))


def give(host, client, uid, item_type):
    """battle_give (clear hands) on both, client first; ok only with equal ids, not -1 (STOP-IF 6)."""
    req = {"cmd": "battle_give", "unit": uid, "item": item_type, "clear_hands": True}
    rc = client.cmd(dict(req))
    rh = host.cmd(dict(req))
    session.wait_seq_barrier(host, client, timeout=30)
    iid = rh.get("weaponId")
    return iid, bool(rh.get("ok") and rc.get("ok") and iid == rc.get("weaponId") and iid not in (None, -1)), (rh, rc)


def dismiss_host_infobox(host, box):
    t = cas.top(host) or ""
    if "Infobox" in t:
        texts = [w.get("text") for w in host.cmd({"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]
        r = host.cmd({"cmd": "dismiss_popup"})
        box.append({"top": t, "texts": texts, "dismissed": r.get("handled") or r.get("type")})


def order(host, client, req, kind):
    """One client battle_intent; bounded wait for the host's `kind` ev and its bt_action_end (or this intent's
    deny), a host infobox dismissed host-only meanwhile; then wait_host_idle and the seq barrier. Returns a record."""
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    r = client.cmd(dict(req))
    rec = {"intent": {k: r.get(k) for k in ("ok", "iseq", "error")}, "seq0": seq0, "box": [], "err": None}
    try:
        if not r.get("ok"):
            raise RuntimeError(f"intent not sent {rec['intent']}")
        deadline = time.time() + ORDER_S
        while True:
            dismiss_host_infobox(host, rec["box"])
            ks = [k for _, k, _a in evs_a(host, seq0)]
            if kind in ks and "bt_action_end" in ks:
                break
            if (event_state(client).get("lastDeny") or {}).get("iseq") == r.get("iseq"):
                rec["deny"] = event_state(client).get("lastDeny")
                break
            if time.time() > deadline:
                raise TimeoutError(f"no {kind} + bt_action_end within {ORDER_S}s (host top {cas.top(host)})")
            time.sleep(0.1)
        time.sleep(0.2)
        dismiss_host_infobox(host, rec["box"])
        session.wait_host_idle(host, client, timeout=30)
        session.wait_seq_barrier(host, client, timeout=30)
        dismiss_host_infobox(host, rec["box"])
    except Exception as e:  # recorded; the row's cells measure what the machines hold
        rec["err"] = short(e, 300)
    rec["hev"], rec["cev"] = evs_a(host, seq0), evs_a(client, seq0)
    return rec


def turn(host, client, uid, to_dir):
    return order(host, client, {"cmd": "battle_intent", "kind": "turn", "actor": uid, "toDir": to_dir}, "turn")


def turns56(host, client):
    """Client turn intents V -> 5 -> 6 (a real rotation each way: the re-look)."""
    return [(r["hev"], r["err"]) for r in (turn(host, client, V_ID, 5), turn(host, client, V_ID, 6))]


def kneel(host, client, uid, on):
    return order(host, client, {"cmd": "battle_intent", "kind": "kneel", "actor": uid, "kneel": bool(on)}, "kneel")


def jt(t):
    return {"x": t[0], "y": t[1], "z": t[2]}


# ===================== rows =====================


def row_c3(host, client):
    cells = dict(ROWS)["C3"]
    rc = [tele_rc(host, client, A_ID, A3_TILE, A3_DIR), tele_rc(host, client, V_ID, V3_TILE, V3_DIR),
          tele_rc(host, client, K_ID, K3_TILE, K3_DIR)]
    tu_max(host, client, K_ID)
    rc.append(recompute(host, client))
    look = turns56(host, client)
    s1 = snap(host, client)
    if not (all(rc) and at(s1, A_ID, A3_TILE, A3_DIR) and at(s1, V_ID, V3_TILE, V3_DIR)
            and at(s1, K_ID, K3_TILE, K3_DIR) and not any(e for _, e in look)):
        staging_miss(cells, f"recompute {rc}; V turns {look}; A/V/K h {[uu(s1, 'h', u) for u in (A_ID, V_ID, K_ID)]}")
        return common(host, client, "C3")
    k1 = kneel(host, client, K_ID, True)
    s2 = snap(host, client)
    look2 = turns56(host, client)
    s3 = snap(host, client)
    tu_max(host, client, K_ID)
    k2 = kneel(host, client, K_ID, False)
    s4 = snap(host, client)
    ev(f"C3: staged (V turns {look}) | kneel {k1['intent']} err {k1['err']} evs host {k1['hev']} client {k1['cev']} "
       f"host log {host_lines(host, k1['seq0'])} | list(K) h/c {pair(s2, 'sees', K_ID)} | V dir h/c "
       f"{pair(s2, 'dir', V_ID)} | client selected {s2['c']['sel']} | re-look {look2} | stand {k2['intent']} err "
       f"{k2['err']} evs host {k2['hev']} client {k2['cev']} host log {host_lines(host, k2['seq0'])} | after: vis/here "
       f"h/c {pair(s4, 'vis')}/{pair(s4, 'here')} K kn/tu h/c {pair(s4, 'kn', K_ID)}/{pair(s4, 'tu', K_ID)}")
    lv1, kn1, v1 = pair(s1, "sees", V_ID), pair(s1, "kn", K_ID), pair(s1, "vis")
    cell("C3-pre", kn1 == (False, False) and v1 == (False, False) and all(A_ID not in x for x in lv1),
         f"K kneeled h/c {kn1}; vis h/c {v1}; list(V) h/c {lv1} (want False/False, False/False, no {A_ID})")
    lv2, kn2 = pair(s2, "sees", V_ID), pair(s2, "kn", K_ID)
    cell("C3-host", kn2[0] is True and A_ID in lv2[0],
         f"host K kneeled {kn2[0]}; host list(V) {lv2[0]} (precondition: True, holds {A_ID})")
    here = uu(s2, "c").get("here")
    cell("C3-here", here is True, f"here(client) {here} (want True)")
    cell("C3-list", A_ID in lv2[1], f"list(client, V) {lv2[1]} (want it to hold {A_ID}; host {lv2[0]})")
    lv3, kn3 = pair(s3, "sees", V_ID), pair(s3, "kn", K_ID)
    cell("C3s-pre", all(A_ID in x for x in lv3) and kn3 == (True, True),
         f"after V -> 5 -> 6 list(V) h/c {lv3}; K kneeled h/c {kn3} (want {A_ID} in both, True/True)")
    lv4, kn4 = pair(s4, "sees", V_ID), pair(s4, "kn", K_ID)
    cell("C3s-host", kn4[0] is False and A_ID not in lv4[0],
         f"host K kneeled {kn4[0]}; host list(V) {lv4[0]} (precondition: False, without {A_ID})")
    cell("C3s-list", A_ID not in lv4[1], f"list(client, V) {lv4[1]} (want no {A_ID}; host {lv4[0]})")
    common(host, client, "C3")


def row_c18(host, client):
    cells = dict(ROWS)["C18"]
    rc = tele_rc(host, client, C_ID, C18_TILE, C18_DIR)
    look = turns56(host, client)
    amp, ok, gr = give(host, client, C_ID, "STR_PSI_AMP")
    if not ok:
        staging_miss(cells, f"battle_give host {gr[0]} client {gr[1]} (want ids equal, not -1; STOP-IF 6)")
        return common(host, client, "C18")
    set_stat(host, client, C_ID, "psiSkill", PSI_SKILL)
    set_stat(host, client, A_ID, "psiStrength", A_PSI_STRENGTH)
    tu_max(host, client, C_ID)
    s1 = snap(host, client)
    if not (rc and at(s1, C_ID, C18_TILE, C18_DIR) and at(s1, V_ID, V3_TILE, V3_DIR) and not any(e for _, e in look)):
        staging_miss(cells, f"recompute {rc}; V turns {look}; C/V h {[uu(s1, 'h', u) for u in (C_ID, V_ID)]}")
        return common(host, client, "C18")
    host.ok({"cmd": "set_seed", "seed": SEED_C18})
    p = order(host, client, {"cmd": "battle_intent", "kind": "psi", "actor": C_ID,
                             "plan": {"weapon": amp, "action": "mc", "target": jt(A3_TILE), "targetUnit": A_ID,
                                      "targetPos": jt(A3_TILE)}}, "psi")
    s2 = snap(host, client)
    ev(f"C18: staged (V turns {look}) amp {amp} | psi {p['intent']} err {p['err']} deny {p.get('deny')} evs host "
       f"{p['hev']} client {p['cev']} host log {host_lines(host, p['seq0'])} | host infobox {p['box']} | list(C) h/c "
       f"{pair(s2, 'sees', C_ID)} | vis(A) h/c {pair(s2, 'vis')} | A mc h/c {pair(s2, 'mc')}")
    f1, lv1 = pair(s1, "f"), pair(s1, "sees", V_ID)
    cell("C18-pre", f1 == (1, 1) and all(A_ID in x for x in lv1) and ok,
         f"A faction h/c {f1}; list(V) h/c {lv1}; amp ids equal {ok} ({amp}) (want 1/1, {A_ID} in both, True)")
    f2, mc2, lv2 = pair(s2, "f"), pair(s2, "mc"), pair(s2, "sees", V_ID)
    cell("C18-host", f2[0] == 0 and mc2[0] == C_ID and A_ID not in lv2[0],
         f"host A faction {f2[0]} mindControllerId {mc2[0]}; host list(V) {lv2[0]} (precondition: 0, {C_ID}, without "
         f"{A_ID})")
    cell("C18-list", A_ID not in lv2[1], f"list(client, V) {lv2[1]} (want no {A_ID}; host {lv2[0]})")
    common(host, client, "C18")


ROW_FNS = {"C3": row_c3, "C18": row_c18}


# ===================== bring-up =====================


def boot(host, client):
    """SAE's boot with this file's key (copied): SEED_ROSTER on the host before open_new_battle, SEED_MAP before
    newbattle_ok, seat_count 2, pin_ai_neutral, every live X-COM unit's reactions 0 on both (client first, F607),
    A base TU 54; A on A_BOOT facing A_BOOT_DIR on both."""
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
    pinned = pin_ai_neutral(host, client, tag="w2h35c")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    types = ((uh.get(A_ID) or {}).get("type"), (uc.get(A_ID) or {}).get("type"))
    assert types == (A_TYPE, A_TYPE), f"A type host/client {types} (want {A_TYPE})"
    for uid, u in sorted(uh.items()):
        if u.get("faction") == 0 and not u.get("isOut"):  # FACTION_PLAYER
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="w2h35c bring-up")
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": A_TU},
         ("tu",))
    s = snap(host, client)
    assert at(s, A_ID, A_BOOT, A_BOOT_DIR), (
        f"A at boot: {uu(s, 'h')} / {uu(s, 'c')} (baked {A_BOOT} facing {A_BOOT_DIR})")


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
    host = GameClient("host", 49862, make_user_dir("w2h35c_d_host"))
    client = GameClient("client", 49863, make_user_dir("w2h35c_d_client"))
    blocked = None
    try:
        try:
            boot(host, client)
            CRASH0 = crash_files()
        except Exception as e:  # a bring-up failure fails every row
            capture_boot(host, client, e)
            blocked = "boot"
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
                print(f"[w2h35c] shutdown {gc.name}: {short(e, 200)}", flush=True)
    names = [c for _, cells in ROWS for c in cells]
    failed = [c for c in names if not RESULTS.get(c)]
    print(f"\ntest_w2_client_sight_more: {len(names) - len(failed)}/{len(names)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
