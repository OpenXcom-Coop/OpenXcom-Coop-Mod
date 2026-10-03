"""W2-P7 S-C-D2 - test_w2_shared_forced_containment.py: after a SHARED battle that leaves the base's alien containment
over its limit, the second player gets the forced containment screen too, and each forced screen closes itself once
the shared base is back under the limit - also when it was covered by a box while the other player solved it (docs
rewrite/prompts/w2p7_sc_design.md section 3.6, AMENDMENT P7-7 sections 2-4: PR-29..PR-35; owner D154, D175; MR9,
MR10).

Before S-C-D2 (F5432, F2501): the second player's OK takes it straight to its geoscape - only the host gets vanilla's
forced ManageAlienContainmentState + "ALIEN CONTAINMENT LIMITS EXCEEDED" box; a SHARED containment confirm closes its
screen at submit.

Fixture FX-CT (AMENDMENT P7-7 section 3; CONSTANTS docs rewrite/w2p7sc2-task0/CONSTANTS.md T0-S3 (i), F5434-F5438;
P7-7 RULINGS: forced containment staging = (a) the stun lever): shared_fixture.bring_up(tag, (0, 0, PORT),
host_options=OPTS, client_options=OPTS), OPTS = {storageLimitsEnforced} on BOTH user dirs (F5429); on the geoscape the
host fac_builds STR_ALIEN_CONTAINMENT at (0, 3) (F5435: the one key-free cell), both machines list it (index 9), its
buildTime 0 on BOTH (F5434); give_items {STR_SECTOID_SOLDIER, 10} on BOTH (client first; capacity 10 = facilities.rul
`aliens: 10`; live aliens have size 0); then test_w2_shared_forced_storage.stage_x() (SEED_S 1, MAP_FP_S, autoEnd on)
with the stun before the kill: host battle_action {kill_unit_real, unit: 1000000, stun: true} (PR-35: vanilla's debug
stun, DT_STUN power 1000, BattlescapeState :3423), wait the host's isBusy false and pendingStates 0 (F4665), unit
1000000 unconscious (status 7) on both machines, the event queues drained and hash_now full equal on both (F5575:
the client mirror rides the death cue's unconscious outcome); then kill_unit_real {faction: 1} kills the other 14
(the stunned one is isOut() and skipped); the host's DebriefingState. Pre-cell (FIXTURE-STOP: one CAPTURE line, the
boot's rows FAIL "pre-cell"): the facility, the fill, the stun and its mirror, the host's debriefing rows hold "LIVE
ALIENS RECOVERED" 1 (vanilla's recoverAlien on the unconscious body: containment state 2 iff free < 0), the client's
display-only debriefing adopted in place within ADOPT_S, the stunned unit's type == L. Cell-level precondition
(FIXTURE-STOP): after the host's OK its stack ends ManageAlienContainmentState + ErrorMessageState.

Probes and levers (PR-28, PR-35): screen_rows / screen_set_amount on the top ManageAlienContainmentState (5 columns,
amount = column 3, OK = "Remove Selected"), shared_update_defer {on} (the client hold), click_widget on the real
captions, dismiss_popup ONLY on an ErrorMessageState top, never on a forced screen (F4333).

Rows (the GREEN cells, checked in order; a failed cell ends its row and the rest are reported "not reached"):
  Boot 1 (port 47254): D2a.
  D2a (1) the client's OK, then the host's: the client's stack ends ManageAlienContainmentState + ErrorMessageState
          (the host's box text).
      (2) the client's box dismissed: its screen_rows texts show used USED / free FREE, its OK (Remove Selected) hidden.
      (3) screen_set_amount {L, 1} (OK visible); with the client held, Remove Selected: its screen stays (MR9/MR10) for
          HOLD_SAMPLE_S; released: it closes itself within SCREEN_S (top GeoscapeState); the host's box dismissed: the
          host's screen closes at once (UNCOVER_S); world_diff empty (prisoners equal); no CoopState on either stack.
  Boot 2 (port 47255): D2b.
  D2b (1) both OKs as D2a (1); the client's box left up.
      (2) the host dismisses its box, removes 1 L, Remove Selected: the host's screen closes itself within SCREEN_S.
      (3) world_diff empty with the client's box still up (top ErrorMessageState).
      (4) the client's box dismissed: its ManageAlienContainmentState closes within UNCOVER_S (top GeoscapeState),
          no CoopState.
Guard on every row: host event_state.fatalVote.armed 0; no new crash log; the client zero-disk at the boot's end.

RED (commit S-C-D2.1: levers and rows, product untouched): D2a and D2b fail on cell 1 (the client reaches its
geoscape with no forced screen). GREEN (commit S-C-D2.2): both rows pass.
Each row prints ONE "EVIDENCE <id>:" line, then "PASS <id>" or "FAIL <id>: <message>". WV-D95/D99/D100: ONE
foreground run, no skip path; exit 0 only when both rows pass, 2 otherwise.

Run:  python tools/coop_test/test_w2_shared_forced_containment.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import battle_state
import test_w2_shared_page3 as p3
import test_w2_shared_forced_storage as fst
from test_w2_shared_forced_storage import (stack, top, wait_until, rows, hold, capture, dismiss_box, screen_ready,
                                           no_coopstate, held_click, both_oks_forced, run_boot)

# ----- pins -----
OPTS_CT = {"storageLimitsEnforced": True}    # AMENDMENT P7-7 section 3 FX-CT (F5429: both user dirs)
CONTAINMENT, CT_X, CT_Y, CT_INDEX = "STR_ALIEN_CONTAINMENT", 0, 3, 9   # CONSTANTS T0-S3 (i) F5434 / F5435
LIVE, LIVE_FILL = "STR_SECTOID_SOLDIER", 10  # FX-CT: give_items 10 on both (capacity 10, facilities.rul aliens: 10)
STUN_UNIT = 1000000                          # FX-CT / CONSTANTS F5438: sectoids 1000000-1000009 are live-recoverable
L = "STR_SECTOID_SOLDIER"                    # the stunned unit's live-alien type (pinned by this file's first
                                             # construction: EVIDENCE pre.stun.type / the host's containment rows)
USED, FREE = 11, -1                          # LIVE_FILL + the one recovered live alien in a capacity-10 prison
CONT_MARK = "ALIEN CONTAINMENT LIMITS EXCEEDED"   # en-US STR_CONTAINMENT_EXCEEDED's head
CONT_OK = "Remove Selected"                  # STR_REMOVE_SELECTED (2-button layout: canSellLiveAliens off)
MACS = "ManageAlienContainmentState"
LIVE_ROW = "LIVE ALIENS RECOVERED"           # the host debriefing's row (STR_LIVE_ALIENS_RECOVERED)
BOOT_PORT = {"CTA": "47254", "CTB": "47255"}  # AMENDMENT P7-7 section 3 (S26, F5582)
UNCOVER_S = 1.0                              # P7-7 section 3.2 D2b (4): "closes within 1 s" once uncovered
SCREEN_S = fst.SCREEN_S
PAGE_S = fst.PAGE_S
BUSY_S = 30                                  # the host's stun chain settles (isBusy false, pendingStates 0; F4665)
UNIT_S = 10                                  # unit 1000000 unconscious on both machines


# ===================== fixture (pre-cell) =====================


def facility_index(gc):
    bases = gc.ok({"cmd": "geo_state"}).get("bases") or []
    facs = (bases[0].get("facilities") or []) if bases else []
    hits = [i for i, f in enumerate(facs) if f.get("type") == CONTAINMENT and f.get("x") == CT_X and f.get("y") == CT_Y]
    return hits[0] if hits else None


def unit_of(gc, uid):
    for u in battle_state(gc).get("units") or []:
        if u.get("id") == uid:
            return u
    return {}


def stun(js, ctx):
    """FX-CT's stun (PR-35): the host stuns unit STUN_UNIT through kill_unit_real {stun: true}; the chain settles; the
    client mirrors the unconscious outcome (status 7 on both, queues drained, hash_now full equal)."""
    host, client = js.host, js.client
    m = (host, client)
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": STUN_UNIT, "stun": True})
    ctx["stun"] = {"resp": {k: r.get(k) for k in ("ok", "killed", "error")}}
    if not (r.get("ok") and r.get("killed") == [STUN_UNIT]):
        capture("FX-CT stun", f"kill_unit_real {{unit {STUN_UNIT}, stun}} answered {ctx['stun']['resp']}", m)
    ok, secs = wait_until(lambda: (lambda b: b.get("isBusy") is False and b.get("pendingStates") == 0)(
        battle_state(host)), BUSY_S)
    ctx["stun"]["settled"] = {"ok": ok, "secs": secs}
    if not ok:
        capture("FX-CT stun settle", f"host isBusy / pendingStates not settled within {BUSY_S}s (F4665)", m)
    ok, secs = wait_until(lambda: unit_of(host, STUN_UNIT).get("status") == 7
                          and unit_of(client, STUN_UNIT).get("status") == 7, UNIT_S)
    hu, cu = unit_of(host, STUN_UNIT), unit_of(client, STUN_UNIT)
    keys = ("status", "isOut", "health", "stun", "type", "onTile")
    ctx["stun"]["unit"] = {"host": {k: hu.get(k) for k in keys}, "client": {k: cu.get(k) for k in keys}, "secs": secs}
    ctx["stun"]["type"] = hu.get("type")
    if not ok:
        capture("FX-CT unconscious", f"unit {STUN_UNIT} {ctx['stun']['unit']} (want status 7 on both)", m)
    try:
        session.wait_host_idle(host, client, timeout=20)
        hh, _ch = session.assert_hash_clean(host, client, full=True, what="after the FX-CT stun")
        ctx["stun"]["hash"] = sorted(hh)
    except Exception as e:
        capture("FX-CT stun mirror", f"{type(e).__name__}: {str(e)[:700]} (F5575: the client mirror of the stun)", m)


def fx_ct(js, ctx):
    """FX-CT on the geoscape (containment facility at (0, 3) built and complete on both, LIVE x LIVE_FILL on both), then
    the stun ending and the adoption; the pre-cell preconditions."""
    host, client = js.host, js.client
    m = (host, client)
    fb = host.cmd({"cmd": "fac_build", "facility": CONTAINMENT, "x": CT_X, "y": CT_Y})
    ok, secs = wait_until(lambda: facility_index(host) is not None and facility_index(client) is not None, 45, 0.5)
    idx = {gc.name: facility_index(gc) for gc in m}
    ctx["fxCT"] = {"facBuild": {k: fb.get(k) for k in ("ok", "error")}, "index": idx, "secs": secs}
    if not (fb.get("ok") and ok and idx["host"] == idx["client"] == CT_INDEX):
        capture("FX-CT facility", f"fac_build {ctx['fxCT']['facBuild']}, index {idx} (want {CT_INDEX} on both)", m)
    sets = {}
    for gc in (client, host):   # client first (F607)
        r = gc.cmd({"cmd": "set_facility_build_time", "baseId": 0, "index": CT_INDEX, "time": 0})
        sets[gc.name] = {k: r.get(k) for k in ("ok", "type", "x", "y", "buildTime", "error")}
    ctx["fxCT"]["buildTime0"] = sets
    if not all(s.get("ok") and s.get("type") == CONTAINMENT and s.get("buildTime") == 0 for s in sets.values()):
        capture("FX-CT buildTime", f"set_facility_build_time answered {sets}", m)
    give = {}
    for gc in (client, host):
        r = gc.cmd({"cmd": "give_items", "item": LIVE, "count": LIVE_FILL})
        give[gc.name] = {k: r.get(k) for k in ("ok", "stored", "error")}
    ctx["fxCT"]["give"] = give
    if not (give["host"].get("ok") and give["client"].get("ok") and give["host"].get("stored") == LIVE_FILL
            and give["client"].get("stored") == LIVE_FILL):
        capture("FX-CT give_items", f"answered {give} (want {LIVE_FILL} stored on both)", m)
    fst.stage_x(js, ctx, pre_kill=stun, kill_expect=[u for u in fst.HOSTILES if u != STUN_UNIT])
    live = [r for r in (ctx["hostDebrief"].get("rows") or []) if r.get("item") == LIVE_ROW]
    ctx["fxCT"]["liveRow"] = live
    if not (len(live) == 1 and live[0].get("qty") == 1):
        capture("FX-CT live alien recovered", f"host debriefing rows {ctx['hostDebrief'].get('rows')} (want "
                f"{LIVE_ROW!r} 1)", m)
    fst.client_adopted(js, ctx)
    if ctx["stun"].get("type") != L:
        capture("FX-CT L", f"the stunned unit's type {ctx['stun'].get('type')!r} (want the pinned L {L!r})", m)


# ===================== cells =====================


def uncover_close(gc, ctx, key):
    """Dismiss gc's box over its forced screen: the screen leaves gc's stack within UNCOVER_S, then its top is
    GeoscapeState within PAGE_S (the host's autosave SaveGameState sits under its forced screens and runs first)."""
    d = dismiss_box(gc) if top(gc) == "ErrorMessageState" else None
    tops, t0 = [], time.time()
    while time.time() - t0 < UNCOVER_S:
        t = top(gc)
        if t not in tops:
            tops.append(t)
        if MACS not in stack(gc):
            break
        time.sleep(0.05)
    secs = round(time.time() - t0, 2)
    gone = MACS not in stack(gc)
    geo, gsecs = wait_until(lambda: top(gc) == "GeoscapeState", PAGE_S, 0.1) if gone else (False, 0)
    ctx[key] = {"dismissed": d, "tops": tops, "secs": secs, "geo": geo, "geoSecs": gsecs, "stack": stack(gc)}
    f = [] if d == "ErrorMessageState" else [f"{gc.name}'s top was {top(gc)!r}, not its box (stack {stack(gc)})"]
    if not gone:
        f.append(f"{gc.name}'s forced {MACS} did not close within {UNCOVER_S}s of its box (tops {tops}, stack "
                 f"{stack(gc)})")
    elif not geo:
        f.append(f"{gc.name}'s top {top(gc)!r} {PAGE_S}s after its forced {MACS} closed (want GeoscapeState)")
    return f


def d2a_cells(host, client, ctx):
    def c2():
        d = dismiss_box(client) if top(client) == "ErrorMessageState" else None
        ok, secs = wait_until(lambda: screen_ready(client, MACS), PAGE_S)
        r = rows(client)
        tx, okv = r.get("texts") or [], fst.ok_visible(r, CONT_OK)
        ctx["c2"] = {"dismissed": d, "up": ok, "secs": secs, "texts": tx, "okVisible": okv,
                     "rows": [row.get("cells") for row in (r.get("rows") or [])]}
        if not ok:
            return [f"the client's forced {MACS} not up within {PAGE_S}s of its box (stack {stack(client)})"]
        f = [f"the client's {MACS} texts {tx} lack {want!r}" for want in (f"SPACE USED>{USED}",
                                                                         f"SPACE AVAILABLE>{FREE}") if want not in tx]
        if okv is not False:
            f.append(f"the client's {CONT_OK} visible={okv!r} (want False: over the limit)")
        return f

    def c3():
        a = p3.set_amount(client, 1, item=L)
        ctx["c3"] = {"set": a}
        if not (a.get("ok") and a.get("after") == 1 and a.get("okVisible") is True):
            return [f"client screen_set_amount {L} 1: {a} (want after 1, okVisible True)"]
        ctx["c3"]["hold"] = hold(client, True)
        f = held_click(client, CONT_OK, MACS, ctx, "c3click")
        ctx["c3"]["release"] = hold(client, False)
        if f:
            return f
        ok, secs = wait_until(lambda: top(client) == "GeoscapeState", SCREEN_S)
        ctx["c3"]["clientClosed"] = {"ok": ok, "secs": secs, "stack": stack(client)}
        if not ok:
            return [f"the client's forced {MACS} did not close itself within {SCREEN_S}s of the release (stack "
                    f"{stack(client)})"]
        f = uncover_close(host, ctx, "c3host")
        f += p3.world_same(host, client, ctx, "c3world")
        cs = [gc.name for gc in (host, client) if not no_coopstate(gc)]
        if cs:
            f.append(f"a CoopState on {cs}'s stack")
        return f
    return [
        ("1 both OKs: the client's forced containment screen under the containment box",
         lambda: both_oks_forced(host, client, ctx, "c1", MACS, CONT_MARK)),
        ("2 the client's forced containment screen shows the over-limit totals, OK hidden", c2),
        ("3 the client's removal closes both forced screens", c3),
    ]


def d2b_cells(host, client, ctx):
    def c2():
        d = dismiss_box(host) if top(host) == "ErrorMessageState" else None
        ok, secs = wait_until(lambda: screen_ready(host, MACS), PAGE_S)
        ctx["c2"] = {"dismissed": d, "up": ok, "secs": secs}
        if not ok:
            return [f"the host's forced {MACS} not up within {PAGE_S}s of its box (stack {stack(host)})"]
        a = p3.set_amount(host, 1, item=L)
        ctx["c2"]["set"] = a
        if not (a.get("ok") and a.get("after") == 1 and a.get("okVisible") is True):
            return [f"host screen_set_amount {L} 1: {a} (want after 1, okVisible True)"]
        c = p3.click(host, CONT_OK)
        ok, secs = wait_until(lambda: top(host) == "GeoscapeState", SCREEN_S)
        ctx["c2"].update({"click": c, "closed": ok, "closeSecs": secs, "stack": stack(host)})
        return [] if ok else [f"the host's forced {MACS} did not close itself within {SCREEN_S}s (stack {stack(host)})"]

    def c3():
        f = p3.world_same(host, client, ctx, "c3world")
        ctx["c3"] = {"clientStack": stack(client)}
        if top(client) != "ErrorMessageState":
            f.append(f"the client's box is no longer up (stack {stack(client)})")
        return f

    def c4():
        f = uncover_close(client, ctx, "c4")
        if not no_coopstate(client):
            f.append(f"a CoopState on the client's stack {stack(client)}")
        return f
    return [
        ("1 both OKs: the client's forced containment screen under its box",
         lambda: both_oks_forced(host, client, ctx, "c1", MACS, CONT_MARK)),
        ("2 the host removes 1: its forced screen closes itself", c2),
        ("3 the prisoners equal with the client's box still up", c3),
        ("4 the client's box dismissed: its covered forced screen closes at once", c4),
    ]


BOOTS = (("CTA", "w2p7scd2_cta", (("D2a", d2a_cells),)), ("CTB", "w2p7scd2_ctb", (("D2b", d2b_cells),)))


def main():
    t0, results, walls = time.time(), {}, {}
    for boot, tag, rows_spec in BOOTS:
        run_boot(boot, tag, BOOT_PORT[boot], OPTS_CT, fx_ct, rows_spec, results, walls)
    order = [rid for _, _, rs in BOOTS for rid, _ in rs]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_w2_shared_forced_containment: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (boot walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
