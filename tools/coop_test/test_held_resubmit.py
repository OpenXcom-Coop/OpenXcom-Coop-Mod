"""W2-H90 - test_held_resubmit.py: a client order the host denies `busy` while a turn-start bleed-out death
is queued is held, and must go out again once that chain ends (the ruled busy -> held -> resubmit behaviour: ADDENDUM
2026-08-31 1.3 (a) "admission happens at quiescence" (register ADD-1.3a); R2-P7's auto-retry; W2-P4 C17p "busy orders
held and resubmitted"). Owner Q2 (CIT-Q2, 2026-10-19): trace it, show how a player reaches it, then a deterministic red.

The chain (H90 Stage 1, report docs rewrite/w2-resume-dafc8555/reports/w2-h90.md): at a side change the host's
BattlescapeGame::endTurn() runs checkForCasualties() after coopEmitSideTransition(); a soldier whose fatal wound took
its last hit point gets a UnitDieBState with NO action context open. The host's own NextTurnState is pushed on top in
the same call, and a covered host battle steps only an `intent` / `endturn` context (coopThinkCoveredBattle), so the
death stays queued (the host isBusy) until the HOST player closes its turn screen. A client player who closed its own
turn screen first and gives an order meanwhile is answered deny(busy) and the order is held. The death then plays and
ends through onChainQuiesced()'s context-less branch: no bt_action_end, so the client's only release point
(CoopArbiter::onQuiescenceObserved, called when a bt_action_end applies) never runs.

Classic co-op boot (test_battle_end.boot: SEED_MAP 1, parallel turns, the only alien pinned neutral). H = 10 (seat 0,
the host's lowest soldier) bleeds: battle_set_unit_state {health 1, fatalWounds [0,1,0,0,0,0]} client first, then host.
C = 8 (seat 1, the client's lowest soldier) receives the client's order. Every order and every turn-screen close in a
row is REAL UI: the client closes its NextTurnState with a key, TAB-selects C and right-clicks a tile two steps away
(BattlescapeGame::secondaryAction's client branch sends the `turn` intent); the host closes its NextTurnState with a key.
The alien-side turn screens in between close through close_nextturn (vanilla's own close(), not the subject).

| row | the client's right-click | green |
|---|---|---|
| B1 | while the host's NextTurnState is up and H's UnitDieBState is queued | denied busy and held (lastDeny busy, the held turn, C unturned on both); after the host's key the death runs and the host goes idle; then the held turn goes out again and C faces toDir on both within RESUBMIT_S; nothing pending or in flight; hash clean |
| B1n | after the host's key, once the host is idle (the negative control) | C faces toDir on both within RESUBMIT_S, no busy deny; nothing pending or in flight; hash clean |

RED at the base `12f27518b` (H90 runs, F24150-F24152): B1 fails its `resubmit` cell (C keeps its direction on both;
the turn stays held on the client for the whole RESUBMIT_S window with the Wait line "Please wait for HostPlayer's
action to finish" up while the host runs nothing) and its `after` cell; B1n passes (the turn applies in ~0.1 s).

Replacement rules (S54): H / C are the lowest live soldier of seat 0 / seat 1 (asserted). The target tile is two tiles
from C in direction (d0 + 2) % 8; if map_tile_click_pos does not verify it, the next of (d0 + 6), (d0 + 3), (d0 + 5) % 8
whose tile two steps away verifies (an on-map tile the click resolves); a row with none fails `pre`.

WV-D99 / WV-D100: one run is the result; no skip path; D297 (a) one fresh boot per row. Each row prints ONE
"EVIDENCE <id>:" line, then "PASS <id>" or "FAIL <id>: ...". Every wait is bounded. Exit 0 only when every row passes,
2 otherwise. WV-D95: run in the foreground to completion.

Run:  py -3 tools/coop_test/test_held_resubmit.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, assert_hash_clean  # noqa: E402
import test_battle_end as tbe  # noqa: E402

H_ID, C_ID = 10, 8                 # the lowest seat-0 / seat-1 soldier on the classic boot (asserted)
WOUND = [0, 1, 0, 0, 0, 0]         # one torso fatal wound: health 1 -> 0 at the player side's start
ROW_PORT = {"B1": "48781", "B1n": "48782"}
CTRL_PORTS = (49930, 49931)        # GameClient labels (the control sockets are ephemeral)
SDLK_TAB, SDLK_HOME = 9, 278       # keyBattleNextUnit / keyBattleCenterUnit defaults
MAP, NEXT = "BattlescapeState", "NextTurnState"
DXY = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))   # vanilla direction vectors 0..7

CYCLE_S = 60       # END TURN -> the alien side -> player turn 2 with both turn screens up
TALLY_S = 20       # the host paints END TURN 1/2 after the client's press
STEP_S = 10        # a key / click takes effect on its machine
DENY_S = 5         # the client's order is answered
IDLE_S = 20        # the host's death chain runs and the host goes idle after its key
RESUBMIT_S = 10    # the held order applies on both after the host is idle (an admitted turn applies in < 0.5 s)
POLL = 0.05


def short(e):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= 400 else s[:400] + "..."


def stack(gc):
    return session.states_stripped(gc)


def top(gc):
    st = stack(gc)
    return st[-1] if st else None


def wait_until(pred, timeout, interval=POLL):
    t0 = time.time()
    while True:
        if pred():
            return True, round(time.time() - t0, 2)
        if time.time() - t0 >= timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)


def unit(gc, uid):
    return session.units_by_id(battle_state(gc)).get(uid) or {}


def dir_c(gc):
    return unit(gc, C_ID).get("direction")


class Row:
    def __init__(self, rid, host, client):
        self.rid, self.host, self.client = rid, host, client
        self.fails, self.ev = [], {}
        self.t0 = time.time()

    def fail(self, phase, msg):
        self.fails.append(f"{phase}: {msg}")

    def t(self):
        return round(time.time() - self.t0, 2)

    def mark(self, what):
        self.ev.setdefault("timeline", []).append((self.t(), what))


def probe(gc):
    """One machine's view for the evidence line."""
    es, bs = event_state(gc), battle_state(gc)
    st = stack(gc)
    return {"top": st[-1] if st else None, "side": bs.get("side"), "turn": bs.get("turn"),
            "isBusy": bs.get("isBusy"), "pendingStates": bs.get("pendingStates"),
            "busyOwnerSeat": es.get("busyOwnerSeat"), "seqE": es.get("lastSeqEmitted"),
            "seqA": es.get("lastSeqApplied"), "qd": es.get("queueDepth"), "lastDeny": es.get("lastDeny"),
            "inFlight": es.get("inFlight"), "pending": bs.get("coopPendingIntent"), "wait": bs.get("coopWaitText"),
            "selectedId": bs.get("selectedId"), "cursorType": bs.get("cursorType"), "dirC": dir_c(gc),
            "H": {k: unit(gc, H_ID).get(k) for k in ("status", "health", "isOut")},
            "intentsTurn": ((es.get("intentsReceived") or {}).get("turn"))}


# ===================== the steps =====================


def stage(r):
    """H bleeds (client first, F607); seat pins asserted; both settle; hash clean."""
    h, c = r.host, r.client
    hs = battle_state(h)
    for seat, want in ((0, H_ID), (1, C_ID)):
        ids = sorted(u["id"] for u in hs.get("units", []) if u.get("faction") == 0 and u.get("coop") == seat
                     and not u.get("isOut"))
        if not ids or ids[0] != want:
            r.fail("pre", f"seat {seat} soldiers {ids} (want the lowest = {want})")
    for gc in (c, h):
        resp = gc.cmd({"cmd": "battle_set_unit_state", "unit": H_ID, "health": 1, "fatalWounds": WOUND})
        if resp.get("fatalWounds") != WOUND or resp.get("health") != 1:
            r.fail("pre", f"{gc.name} battle_set_unit_state {H_ID} answered {resp} (want health 1, fatalWounds {WOUND})")
    session.wait_seq_barrier(h, c)
    session.wait_host_idle(h, c, timeout=30)
    assert_hash_clean(h, c, full=True, what="after the staging")
    r.ev["staged"] = {"H": unit(h, H_ID).get("health"), "dirC": (dir_c(h), dir_c(c))}


def close_alien_screens(gc, want_turn):
    """Close a NextTurnState on `gc` only while its side is not yet the player side of `want_turn`. The stack is read
    BEFORE the side: a host NextTurnState stops the host's battle, so a screen seen on top before a side read that is
    still short of the player turn belongs to an earlier side change."""
    st = stack(gc)
    if not st or st[-1] != NEXT:
        return False
    bs = battle_state(gc)
    if bs.get("side") == 0 and (bs.get("turn") or 0) >= want_turn:
        return False
    gc.cmd({"cmd": "close_nextturn"})
    return True


def to_turn_two(r):
    """END TURN (client, then host once it paints END TURN 1/2); the alien side's turn screens closed; stop with the
    player side of the next turn reached on both and BOTH machines' NextTurnState of it up."""
    h, c = r.host, r.client
    turn0 = battle_state(h).get("turn") or 0
    want = turn0 + 1
    r.ev["turn0"] = turn0
    c.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    ok, secs = wait_until(lambda: battle_state(h).get("coopEndTurnText") == "END TURN 1/2", TALLY_S, 0.1)
    if not ok:
        r.fail("pre", f"host never painted END TURN 1/2 after the client's press ({secs}s)")
        return False
    h.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    r.mark("host END TURN")
    deadline = time.time() + CYCLE_S
    while time.time() < deadline:
        close_alien_screens(h, want)
        close_alien_screens(c, want)
        hs, cs = battle_state(h), battle_state(c)
        if (hs.get("side") == 0 and (hs.get("turn") or 0) >= want and cs.get("side") == 0
                and (cs.get("turn") or 0) >= want and top(h) == NEXT and top(c) == NEXT):
            r.mark(f"turn {want}: both turn screens up")
            return True
        time.sleep(POLL)
    r.fail("pre", f"no player turn {want} with both NextTurnStates up within {CYCLE_S}s: host {probe(h)} client "
                  f"{probe(c)}")
    return False


def client_closes_screen(r):
    """The client player's key closes its own NextTurnState (real UI)."""
    c = r.client
    c.ok({"cmd": "inject_input", "kind": "key"})
    ok, secs = wait_until(lambda: top(c) == MAP, STEP_S)
    r.mark(f"client key: top {top(c)}")
    if not ok:
        r.fail("pre", f"the client's key left top {top(c)} (want {MAP}) after {secs}s")
    return ok


def host_closes_screen(r):
    """The host player's key closes its own NextTurnState (real UI); then the host's death chain runs to idle."""
    h, c = r.host, r.client
    h.ok({"cmd": "inject_input", "kind": "key"})
    ok, secs = wait_until(lambda: top(h) != NEXT, STEP_S)
    r.mark(f"host key: top {top(h)}")
    if not ok:
        r.fail("pre", f"the host's key left top {top(h)} after {secs}s")
        return False
    ok, secs = wait_until(lambda: (event_state(h).get("busyOwnerSeat") == -1
                                   and battle_state(h).get("pendingStates") == 0
                                   and unit(h, H_ID).get("isOut") is True), IDLE_S)
    r.mark(f"host idle after the death: {ok} ({secs}s)")
    r.ev["hostIdle"] = {"ok": ok, "secs": secs, "host": probe(h)}
    if not ok:
        r.fail("pre", f"the host did not go idle with H {H_ID} out within {secs}s: {probe(h)}")
    return ok


def pick_target(r):
    """C's position, d0 and the first verified target tile two steps away (replacement rule in the docstring)."""
    c = r.client
    u = unit(c, C_ID)
    d0 = u.get("direction")
    pos = (u.get("x"), u.get("y"), u.get("z"))
    if not isinstance(d0, int) or None in pos:
        r.fail("pre", f"C {C_ID} on the client: {u}")
        return None
    for k in (2, 6, 3, 5):
        to_dir = (d0 + k) % 8
        dx, dy = DXY[to_dir]
        tile = (pos[0] + 2 * dx, pos[1] + 2 * dy, pos[2])
        c.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
        time.sleep(0.15)
        pr = c.cmd({"cmd": "map_tile_click_pos", "x": tile[0], "y": tile[1], "z": tile[2]})
        if pr.get("verified"):
            return {"d0": d0, "toDir": to_dir, "tile": tile, "pos": pos, "click": pr}
    r.fail("pre", f"no verified target tile two steps from C {C_ID} at {pos} (d0 {d0})")
    return None


def client_orders(r):
    """The client player TAB-selects C and right-clicks the target tile (real UI). Returns the target or None."""
    c = r.client
    for _ in range(16):
        if battle_state(c).get("selectedId") == C_ID:
            break
        c.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.15)
    if battle_state(c).get("selectedId") != C_ID:
        r.fail("pre", f"TAB never selected C {C_ID} on the client: {probe(c)}")
        return None
    tg = pick_target(r)
    if not tg:
        return None
    r.ev["order"] = {k: tg[k] for k in ("d0", "toDir", "tile", "pos")}
    r.ev["beforeClick"] = {"host": probe(r.host), "client": probe(c)}
    c.ok({"cmd": "inject_input", "kind": "click", "x": tg["click"]["winX"], "y": tg["click"]["winY"],
          "button": "right"})
    r.mark("client right-click")
    return tg


def check_held(r, tg):
    """The order is denied busy and held; C unturned on both."""
    h, c = r.host, r.client
    ok, secs = wait_until(lambda: (event_state(c).get("lastDeny") or {}).get("reason") == "busy"
                          and battle_state(c).get("coopPendingIntent") is not None, DENY_S)
    r.mark(f"client deny(busy) + held: {ok} ({secs}s)")
    hs, cs = probe(h), probe(c)
    r.ev["held"] = {"host": hs, "client": cs}
    pend = cs["pending"] or {}
    if not ok or pend.get("kind") != "turn" or pend.get("actorId") != C_ID:
        r.fail("held", f"the client's order was not held: lastDeny {cs['lastDeny']} pending {cs['pending']} (want "
                       f"reason busy, a held turn for {C_ID})")
    if (hs["dirC"], cs["dirC"]) != (tg["d0"], tg["d0"]):
        r.fail("held", f"C's direction (host, client) ({hs['dirC']}, {cs['dirC']}) (want unturned {tg['d0']})")
    if hs["top"] != NEXT or not hs["isBusy"]:
        r.fail("held", f"host top {hs['top']} isBusy {hs['isBusy']} (want {NEXT}, the death queued under it)")


def check_applied(r, tg, phase):
    """C faces toDir on both within RESUBMIT_S; then nothing pending / in flight and the host idle; hash clean."""
    h, c = r.host, r.client
    seen, t0 = [], time.time()

    def applied():
        v = (dir_c(h), dir_c(c))
        if not seen or seen[-1][1] != v:
            seen.append((round(time.time() - t0, 2), v))
        return v == (tg["toDir"], tg["toDir"])

    ok, secs = wait_until(applied, RESUBMIT_S, 0.1)
    r.mark(f"{phase}: C on toDir on both: {ok} ({secs}s)")
    cs = probe(c)
    r.ev[phase] = {"ok": ok, "secs": secs, "dirsSeen": seen, "client": cs, "host": probe(h)}
    if not ok:
        r.fail(phase, f"the order did not apply on both within {secs}s: C's direction (host, client) "
                      f"({dir_c(h)}, {dir_c(c)}) (want {tg['toDir']}); the client's held order {cs['pending']}, "
                      f"its Wait line {cs['wait']!r}, lastDeny {cs['lastDeny']}")
    ok2, secs2 = wait_until(lambda: (battle_state(c).get("coopPendingIntent") is None
                                     and event_state(c).get("inFlight") is None
                                     and event_state(h).get("busyOwnerSeat") == -1), STEP_S)
    if not ok2:
        r.fail("after", f"an order is still held or in flight {secs2}s later: client {probe(c)}")
        return
    try:
        session.wait_host_idle(h, c, timeout=30)
        assert_hash_clean(h, c, full=True, what=f"{r.rid} after the order")
    except Exception as e:
        r.fail("after", f"hash_now full: {short(e)}")


def row_b1(r):
    stage(r)
    if r.fails or not to_turn_two(r):
        return
    r.ev["turnTwo"] = {"host": probe(r.host), "client": probe(r.client)}
    if not client_closes_screen(r):
        return
    tg = client_orders(r)
    if not tg:
        return
    check_held(r, tg)
    if not host_closes_screen(r):
        return
    check_applied(r, tg, "resubmit")


def row_b1n(r):
    stage(r)
    if r.fails or not to_turn_two(r):
        return
    r.ev["turnTwo"] = {"host": probe(r.host), "client": probe(r.client)}
    if not client_closes_screen(r):
        return
    if not host_closes_screen(r):
        return
    deny0 = event_state(r.client).get("lastDeny")
    tg = client_orders(r)
    if not tg:
        return
    check_applied(r, tg, "applied")
    deny1 = event_state(r.client).get("lastDeny")
    if deny1 != deny0:
        r.fail("applied", f"the client's lastDeny {deny0} -> {deny1} (want unchanged: the order was admitted)")


# ===================== runner =====================


def run_row(rid, row_fn, results, label):
    host = GameClient("host", CTRL_PORTS[0], make_user_dir(f"{label}_{rid}_host"))
    client = GameClient("client", CTRL_PORTS[1], make_user_dir(f"{label}_{rid}_client"))
    r = Row(rid, host, client)
    try:
        try:
            tbe.boot(host, client, ROW_PORT[rid])
        except Exception as e:
            results[rid] = False
            print(f"FAIL {rid}: pre (bring-up) {short(e)}", flush=True)
            return
        r.ev["bootS"] = r.t()
        r.t0 = time.time()
        try:
            row_fn(r)
        except Exception as e:
            r.fail("exception", short(e))
        r.ev["wallS"] = r.t()
        print(f"EVIDENCE {rid}: {r.ev}", flush=True)
        if r.fails:
            results[rid] = False
            print(f"FAIL {rid}: {len(r.fails)} failure(s): " + " | ".join(r.fails), flush=True)
        else:
            results[rid] = True
            print(f"PASS {rid}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2-h90] shutdown {gc.name}: {short(e)}", flush=True)


ROWS = (("B1", row_b1), ("B1n", row_b1n))


def main():
    t0 = time.time()
    results = {}
    for rid, fn in ROWS:
        run_row(rid, fn, results, "w2h90")
    order = [x[0] for x in ROWS]
    passed = [n for n in order if results.get(n)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_held_resubmit: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
