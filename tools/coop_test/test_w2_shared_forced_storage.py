"""W2-P7 S-C-D2 - test_w2_shared_forced_storage.py: after a SHARED battle that leaves the base over its storage limit,
the second player gets the forced storage screen too, every SHARED sell confirm waits for the host's answer, and a
forced screen closes itself once the base is back under its limit (docs rewrite/prompts/w2p7_sc_design.md section
3.6, AMENDMENT P7-7 sections 2-4: PR-29..PR-35; owner D154, D175; mechanism rulings MR9, MR10, MR15).

Before S-C-D2 (F5432, F2501, F2500, F2163): the second player's OK takes it straight to its geoscape - only the host
gets vanilla's forced SellState + "STORAGE SPACE EXCEEDED" box; a SHARED sell closes its screen at submit, before the
host answers, so a rejected sale leaves no screen; the host's sellValidate counts base stock only (a forced-storage
sale of a craft's items is rejected); a forced confirm that arrives after the base is solved shows a fail box.

Fixture FX-ST (AMENDMENT P7-7 section 3, CONSTANTS docs rewrite/w2p7sc2-task0/CONSTANTS.md T0-S3 (ii), CONSTRUCTED):
shared_fixture.bring_up(tag, (0, 0, PORT), host_options=OPTS, client_options=OPTS), OPTS = {storageLimitsEnforced,
canSellLiveAliens} (F5429: boot-time options on BOTH user dirs); give_items {STR_RIFLE, 300} on BOTH (client first;
F5433: base 0 then holds 111 of 65 stores); then stage_x() = a local copy of test_w2_battle_end_campaign.stage()
WITHOUT its HOST_DEBRIEF pin (T0's storage boots totalled 418, not S-C-A's 454: the pin does not transfer; the host's
debriefing is recorded in EVIDENCE): SEED_S 1, MAP_FP_S, autoEnd on, kill_unit_real {faction: 1} kills the 15
hostiles, the host's DebriefingState. Pre-cell (a failure is a FIXTURE-STOP: one CAPTURE line, every row of the boot
FAILs "pre-cell"): the client's display-only DebriefingState and battleEnd.worldAdopted 1 within ADOPT_S; the host's
base over its storage limit; boot 1 also a craft holding a rifle (D2c cell 3's MR15 sale reaches it); boot 2 T's
page-3 count == T_QTY on both and the host's stock of T == T_QTY. Cell-level precondition (FIXTURE-STOP): after the
host's OK its stack ends SellState + ErrorMessageState.

Probes and levers (PR-28, PR-35): screen_rows / screen_set_amount (the top Sell screen), screen_rows {recovered}
(page-3 counts, R-D1-1), shared_stats {lastFail, failCount, applyQueued, applyHold}, shared_update_defer {on} (the
client "hold": its per-frame SharedEcon drain waits, so a host answer or apply surfaces only at the release - PR-35,
F5578; a held shared_fail is asserted AFTER the release, F5573), the host's `sell` lever (a harness confirm, immediate
pop, F2521), base_report (storage, usedStores / availableStores, crafts[].items), coop_dialog_info, list_widgets (the
error box text), click_widget on the real captions (SELL, Sell/Sack), dismiss_popup ONLY on an ErrorMessageState top,
coop_dialog_back ONLY on a CoopState top - never on a forced screen (F4333).
J10 timing (F4529): a client hold that outlives a host world change by RESYNC_DEBOUNCE (3 s) while the host's
GeoscapeState is on top (it alone sends the checksummed `time` heartbeat) requests a world resync that replaces the
client's screens; every hold below is released within HOLD_MAX_S of the host's change.

Rows (the GREEN cells, checked in order; a failed cell ends its row and the rest are reported "not reached"):
  Boot 1 (port 47256): D2c.
  D2c (1) the client's OK, then the host's: the client's stack ends SellState + ErrorMessageState (the host's box
          text) and its battleEnd.forced.storage == 1.
      (2) both boxes dismissed: the client's forced SellState lists Rifle qty == base stock + craft + transfer rifles
          (MR15), its OK (Sell/Sack) hidden.
      (3) Rifle = stock + 1 (the sale reaches one craft rifle), OK visible; with the client held, Sell/Sack: its screen
          stays (MR9/MR10) for HOLD_SAMPLE_S; released: BOTH forced SellStates close themselves within SCREEN_S
          (tops GeoscapeState), the crafts' rifle count -1 on both, world_diff empty, no CoopState on either stack.
  Boot 2 (port 47257): D2e, then D2d, then D2f.
  D2e (before the OKs) (1) the client's page-3 SellState open (lists T: T_QTY); client held; the host's `sell {T,
          T_QTY - 1}` applied on the host.
      (2) the client sets T = T_QTY, Sell/Sack: its page-3 SellState stays at submit (MR10); the host rejects
          (lastFail STR_NOT_ENOUGH_ITEMS_TO_SELL); released: the client's top CoopState (code 556, the fail box) with
          the page-3 SellState directly under it.
      (3) coop_dialog_back: the page-3 SellState rebuilt (T: T_QTY, amount 0); T = 1, Sell/Sack: it closes after the
          host's answer (top DebriefingState); recovered[T] == T_QTY - 1 on both.
  D2d (1) both OKs as D2c (1); both boxes dismissed, both forced SellStates up.
      (2) client held; the host's `sell {STR_RIFLE, 10}` applied (the host still over); the client sets Rifle = its
          listed qty - 9 (OK visible), Sell/Sack: its forced SellState stays; the host rejects (lastFail
          STR_NOT_ENOUGH_ITEMS_TO_SELL); released: the client's top CoopState (556) with its forced SellState under it.
      (3) coop_dialog_back: the client's forced SellState rebuilt (Rifle qty - 10) and still forced (OK hidden).
  D2f (1) client held; the host's `sell {STR_RIFLE, N}` (N clears the host's base by base_report): the host's forced
          SellState closes itself (top GeoscapeState).
      (2) the client (held, still over in its view) sets Rifle to clear by its view (OK visible), Sell/Sack: the host
          drops it silently - the client's lastFail == coop_forced_resolved (PR-32), no CoopState.
      (3) released: no CoopState within SCREEN_S, the client's forced SellState closes itself (top GeoscapeState);
          world_diff empty.
  Rows sharing a boot start by turning every hold off and dismissing any ErrorMessageState / CoopState box on both
  machines. D2f needs D2d's forced screen: when D2d fails, D2f is reported "not reached".
Guard on every row: host event_state.fatalVote.armed 0; no new crash log; the client zero-disk at the boot's end.

RED (commit S-C-D2.1: levers and rows, product untouched): D2c fails on cell 1 (the client reaches its geoscape with
no forced screen, F5432), D2e on cell 2 (the page-3 SellState is gone at submit, F2501), D2d on cell 1 (as D2c); D2f
not reached. GREEN (commit S-C-D2.2): every row passes.
Each row prints ONE "EVIDENCE <id>:" line (both machines' battleEnd keys page3, worldAdoptDeferredPasses, forced,
adoptFailed), then "PASS <id>" or "FAIL <id>: <message>". WV-D95/D99/D100: ONE foreground run, no skip path; exit 0
only when every row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_shared_forced_storage.py
"""

import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import battle_state, event_state
import shared_fixture
import test_w2_battle_end_campaign as camp
import test_w2_shared_page3 as p3

# ----- pins -----
OPTS_ST = {"storageLimitsEnforced": True, "canSellLiveAliens": True}  # CONSTANTS T0-S3 (ii) / F5429 (both user dirs)
RIFLE, RIFLE_FILL = "STR_RIFLE", 300     # CONSTANTS T0-S3 (ii): "give_items STR_RIFLE 300 to base 0 on both"
RIFLE_SIZE = 0.2                         # CONSTANTS T0-S3 (ii): "(rifle size 0.2)"
T = "STR_SECTOID_CORPSE"                 # FX-S's T (AMENDMENT P7-7 section 3)
T_QTY = 10                               # FX-ST boot 2: T's page-3 count and the host's stock at its debriefing (pinned
                                         # by this file's first construction, EVIDENCE D2e pre.fxST.counts / stockT)
D2D_HOST_SELL, D2D_SHORT = 10, 9         # AMENDMENT P7-7 section 3.2 D2d (2): the host sells 10, the client asks qty - 9
BOOT_PORT = {"ST1": "47256", "ST2": "47257"}  # AMENDMENT P7-7 section 3 (S26, F5582): D2 = 47254-47258
HOSTILES = camp.HOSTILES                 # CONSTANTS (part 1) T0-6 (i): 1000000-1000014
STORAGE_MARK = "STORAGE SPACE EXCEEDED"  # en-US STR_STORAGE_EXCEEDED's head (bin/standard/xcom1/Language/en-US.yml)
SELL_OK = "Sell/Sack"                    # SellState's OK caption (STR_SELL_SACK, F5572)
NOT_ENOUGH = "STR_NOT_ENOUGH_ITEMS_TO_SELL"   # sellValidate's reason (SharedEcon.cpp sellValidate)
FORCED_RESOLVED = "coop_forced_resolved"      # PR-32's silent reason
FAIL_BOX = 556                           # CoopState COOP_DLG_SHARED_FAIL (CoopState.h :56)
ADOPT_S = camp.ADOPT_S                   # 15 s (CONSTANTS T0-S2)
OK_S = camp.OK_S                         # 10 s: a machine's next screen after its own OK
GEO_STEADY_S = 1.0                       # cell 1: a GeoscapeState top this long after the OK = the chain is done
SCREEN_S = 10                            # P7-7 section 3.2: "within 10 s"
PAGE_S = p3.PAGE_S                       # 5 s: a screen push / box after a real click or a release
ANSWER_S = 2.5                           # a held client sees the host's answer (shared_ok / shared_fail at receipt)
HOLD_SAMPLE_S = 1.0                      # "stays until the apply": the held client's top sampled this long
HOLD_MAX_S = 2.5                         # F4529: every hold released within this of the host's world change
EQUAL_S = 10                             # a shared_apply's effect may lag one round trip


class FixtureMiss(Exception):
    pass


# ===================== probes =====================


def short(e, n=400):
    return camp.short(e, n)


def stack(gc):
    return session.states_stripped(gc)


def top(gc):
    st = stack(gc)
    return st[-1] if st else None


def wait_until(pred, timeout, interval=0.25):
    return camp.wait_until(pred, timeout, interval)


def record(gc):
    return camp.record(gc)


def rec_keys(gc):
    """The battleEnd record keys P7-7 names for the report, plus the adoption keys."""
    r = record(gc)
    return {k: r.get(k) for k in ("page3", "worldAdoptDeferredPasses", "forced", "adoptFailed", "worldAdopted",
                                  "worldHeld", "returnPending", "debriefOkBranch")}


def rows(gc, **kw):
    return p3.rows(gc, **kw)


def sstats(gc):
    r = gc.cmd({"cmd": "shared_stats"})
    return {k: r.get(k) for k in ("lastFail", "failCount", "okCount", "applyCount", "applyQueued", "applyHold")}


def hold(gc, on):
    """The client hold (P10's shared_update_defer, PR-35): {on} -> its `deferred` answer."""
    return gc.cmd({"cmd": "shared_update_defer", "on": bool(on)}).get("deferred")


def dialog(gc):
    r = gc.cmd({"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("present", "code", "title")}


def err_text(gc):
    """The top ErrorMessageState's text (its Text widgets; list_widgets), None when the top is something else."""
    r = gc.cmd({"cmd": "list_widgets"})
    if "ErrorMessageState" not in (r.get("state") or ""):
        return None
    return " ".join(w.get("text") or "" for w in (r.get("widgets") or [])
                    if (w.get("type") or "").endswith("::Text") and w.get("text"))


def dismiss_box(gc):
    """Dismiss this machine's top box ONLY when it is an ErrorMessageState (dismiss_popup's generic pop = its OK) or a
    CoopState (coop_dialog_back); never anything else (F4333). Returns what was dismissed, or None."""
    t = top(gc)
    if t == "ErrorMessageState":
        gc.cmd({"cmd": "dismiss_popup"})
        return t
    if t == "CoopState":
        info = dialog(gc)
        gc.cmd({"cmd": "coop_dialog_back"})
        return f"CoopState {info.get('code')}"
    return None


def hygiene(host, client, ctx):
    """A row that shares a boot starts by turning every hold off and dismissing any ErrorMessageState / CoopState box on
    both machines (a released hold surfaces its box on the next pass: polled for PAGE_S)."""
    out = {"holds": {gc.name: hold(gc, False) for gc in (host, client)}, "dismissed": []}
    t0 = time.time()
    while time.time() - t0 < PAGE_S:
        hit = False
        for gc in (host, client):
            d = dismiss_box(gc)
            if d:
                out["dismissed"].append(f"{gc.name}:{d}")
                hit = True
        if not hit and time.time() - t0 > 1.0:
            break
        time.sleep(0.25)
    out["stacks"] = {gc.name: stack(gc) for gc in (host, client)}
    ctx["hygiene"] = out


def base0(gc):
    """base_report of base 0 (the debriefing's base, HostBase)."""
    r = gc.cmd({"cmd": "base_report", "base": "HostBase"})
    return r if r.get("ok") else {}


def rifles(gc):
    """(base stock, crafts' items, item transfers) of STR_RIFLE at base 0 - SellState :257-275's forced terms."""
    b = base0(gc)
    stock = (b.get("storage") or {}).get(RIFLE, 0)
    craft = sum((c.get("items") or {}).get(RIFLE, 0) for c in (b.get("crafts") or []))
    bases = gc.ok({"cmd": "geo_state"}).get("bases") or []
    xfer = sum(t.get("qty", 0) for t in ((bases[0].get("transfers") or []) if bases else [])
               if t.get("rule") == RIFLE)
    return {"stock": stock, "craft": craft, "xfer": xfer, "used": b.get("usedStores"),
            "available": b.get("availableStores")}


def stock_of(gc, item):
    return (base0(gc).get("storage") or {}).get(item, 0)


def row_of(r, item):
    """(qty, amount) of the row whose item type == item in a screen_rows reply, (None, None) if absent."""
    for row in r.get("rows") or []:
        if row.get("item") == item:
            c = row.get("cells") or []
            return p3.as_int(c[1]) if len(c) > 1 else None, p3.as_int(c[2]) if len(c) > 2 else None
    return None, None


def ok_visible(r, caption):
    for b in r.get("buttons") or []:
        if b.get("text") == caption:
            return b.get("visible")
    return None


def screen_ready(gc, cls):
    """Top == cls and its list holds rows (its init() ran, F5573)."""
    if top(gc) != cls:
        return False
    r = rows(gc)
    return r.get("state") == cls and len(r.get("rows") or []) > 0


def forced_tail(gc, cls):
    return stack(gc)[-2:] == [cls, "ErrorMessageState"]


def no_coopstate(gc):
    return not any("CoopState" in s for s in stack(gc))


def view(gc):
    d = gc.cmd({"cmd": "debrief_state"})
    return {"stack": stack(gc), "record": rec_keys(gc), "shared": sstats(gc),
            "debrief": {k: d.get(k) for k in ("shown", "onTop", "displayOnly", "page", "sellVisible",
                                              "transferVisible")}}


def evidence(rid, obj):
    camp.evidence(rid, obj)


def capture(name, err, machines, extra_items=()):
    """FIXTURE-STOP: CAPTURE every machine's stack, battleEnd record, debrief_state, top screen rows, base 0 and shared
    stats (whole), then raise."""
    cap = {}
    for gc in machines:
        try:
            bs = battle_state(gc)
            cap[gc.name] = {"stack": stack(gc), "battleEnd": record(gc), "debrief": gc.cmd({"cmd": "debrief_state"}),
                            "screen": rows(gc, recovered=list(extra_items) + [T, RIFLE]),
                            "base0": base0(gc), "shared": sstats(gc), "dialog": dialog(gc),
                            "battle": {k: bs.get(k) for k in ("inBattle", "isBusy", "pendingStates", "phase")},
                            "fatalVote": (event_state(gc).get("fatalVote") or {})}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {name} (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(f"{name}: {err[:600]}")


# ===================== fixtures (pre-cell) =====================


def stage_x(js, ctx, pre_kill=None, kill_expect=HOSTILES):
    """test_w2_battle_end_campaign.stage() without its HOST_DEBRIEF pin (FX-ST/FX-CT): the SHARED battle on SEED_S
    (MAP_FP_S), autoEnd on, the optional pre_kill(js, ctx) (FX-CT's stun), kill_unit_real {faction: 1}, the host's
    DebriefingState; the host's debrief_state is recorded (ctx["hostDebrief"]). Raises FixtureMiss after a CAPTURE."""
    host, client = js.host, js.client
    m = (host, client)
    try:
        _h, _c, squad = session.bring_up_shared_mixed_battle(js, {0: 0, 1: 1}, pre_landing=camp.seed_pin)
    except Exception as e:
        capture("bring_up_shared_mixed_battle", short(e, 800), m)
    ctx["squad"] = squad
    fp = (battle_state(host).get("mapFingerprint"), battle_state(client).get("mapFingerprint"))
    ctx["mapFingerprint"] = fp
    if fp != (camp.MAP_FP_S, camp.MAP_FP_S):
        capture("map pin", f"mapFingerprint (host, client) {fp} (want both {camp.MAP_FP_S!r}, SEED_S {camp.SEED_S})", m)
    ae = host.cmd({"cmd": "set_option", "name": "battleAutoEnd", "value": True})
    ctx["autoEnd"] = ae.get("value")
    if ae.get("value") is not True:
        capture("battleAutoEnd", f"host set_option battleAutoEnd answered {ae}", m)
    if pre_kill is not None:
        pre_kill(js, ctx)
    ctx["loadGamePushes0"] = camp.log_count(client, camp.LOADGAME_PUSH)
    k = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": 1})
    ctx["kill"] = {k2: k.get(k2) for k2 in ("ok", "killed", "error")}
    if not k.get("ok") or sorted(k.get("killed") or []) != sorted(kill_expect):
        capture("kill", f"kill_unit_real faction 1 answered {ctx['kill']} (want {sorted(kill_expect)})", m)
    t0, closes, samples, last = time.time(), [], [], None
    while time.time() - t0 < camp.DEBRIEF_S:
        hst = stack(host)
        if "DebriefingState" in hst:
            break
        s = (hst[-1] if hst else None, top(client))
        if s != last:
            samples.append((round(time.time() - t0, 2),) + s)
            last = s
        if hst and hst[-1] == "NextTurnState":
            closes.append(host.cmd({"cmd": "dismiss_popup"}).get("handled"))
        time.sleep(0.1)
    ctx["ending"] = {"secs": round(time.time() - t0, 2), "closes": closes, "samples": samples}
    if "DebriefingState" not in stack(host):
        capture("host debriefing", f"no host DebriefingState within {camp.DEBRIEF_S}s of the kill ({ctx['ending']})", m)
    hdeb = host.cmd({"cmd": "debrief_state"})
    ctx["hostDebrief"] = camp.pin_view(hdeb)
    bad = [f"host debrief_state.{k}={hdeb.get(k)!r} (want {w!r})"
           for k, w in (("shown", True), ("onTop", True), ("displayOnly", False)) if hdeb.get(k) is not w]
    armed = (event_state(host).get("fatalVote") or {}).get("armed")
    if armed != 0:
        bad.append(f"host fatalVote.armed={armed!r} (want 0: no S-V vote, F4544)")
    if bad:
        capture("host debriefing", "; ".join(bad), m)


def client_adopted(js, ctx):
    """The client's display-only DebriefingState on top, then battleEnd.worldAdopted 1 within ADOPT_S."""
    host, client = js.host, js.client
    m = (host, client)
    ok, secs = wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                   and d.get("displayOnly") is True)(client.cmd({"cmd": "debrief_state"})),
                          camp.CLIENT_DEBRIEF_S)
    ctx["clientDebrief"] = {"ok": ok, "secs": secs}
    if not ok:
        capture("client debriefing", f"no client display-only DebriefingState on top within {camp.CLIENT_DEBRIEF_S}s",
                m)
    ok, secs = wait_until(lambda: record(client).get("worldAdopted") == 1, ADOPT_S)
    ctx["adopted"] = {"ok": ok, "secs": secs, "client": rec_keys(client)}
    if not ok:
        capture("client adoption", f"client battleEnd.worldAdopted != 1 within {ADOPT_S}s", m)


def bring_up(tag, port, opts):
    """shared_fixture.bring_up with the same boot-time options on BOTH user dirs (PR-35's client_options, F5429)."""
    return shared_fixture.bring_up(tag, (0, 0, port), host_options=opts, client_options=opts)


def fx_st(js, ctx, boot):
    """FX-ST: STR_RIFLE x RIFLE_FILL on both (client first), stage_x(), the adoption; the boot's own preconditions."""
    host, client = js.host, js.client
    m = (host, client)
    give = {}
    for gc in (client, host):   # client first (F607)
        r = gc.cmd({"cmd": "give_items", "item": RIFLE, "count": RIFLE_FILL})
        give[gc.name] = {k: r.get(k) for k in ("ok", "stored", "error")}
    ctx["give"] = give
    if not (give["host"].get("ok") and give["client"].get("ok")
            and give["host"].get("stored") == give["client"].get("stored")):
        capture("FX-ST give_items", f"answered {give}", m)
    stage_x(js, ctx)
    client_adopted(js, ctx)
    rv = {gc.name: rifles(gc) for gc in m}
    ctx["fxST"] = {"rifles": rv, "counts": {gc.name: p3.counts(gc, [T, RIFLE]) for gc in m},
                   "stockT": {gc.name: stock_of(gc, T) for gc in m}}
    h = rv["host"]
    if not (isinstance(h.get("used"), (int, float)) and isinstance(h.get("available"), (int, float))
            and h["used"] > h["available"]):
        capture("FX-ST over the limit", f"host base 0 usedStores {h.get('used')} / availableStores "
                f"{h.get('available')} (want used > available, F5433)", m)
    if boot == "ST1" and not all(r.get("craft", 0) > 0 for r in rv.values()):
        capture("FX-ST craft rifle", f"no craft holds a rifle (rifles {rv}): D2c cell 3's MR15 sale has no craft item",
                m)
    if boot == "ST2":
        c, s = ctx["fxST"]["counts"], ctx["fxST"]["stockT"]
        if not (c["host"].get(T) == T_QTY and c["client"].get(T) == T_QTY and s["host"] == T_QTY):
            capture("FX-ST T", f"recovered[{T}] {c}, host stock {s} (want {T_QTY} each)", m)


# ===================== cells =====================


def press_ok(gc):
    return camp.press_ok(gc)


def both_oks_forced(host, client, ctx, key, cls, mark, record_check=None):
    """The client's OK, then the host's. FIXTURE-STOP unless the host's stack then ends cls + ErrorMessageState (the
    fixture's precondition). The cell: the client's stack ends cls + ErrorMessageState, its box text == the host's
    and holds `mark`; record_check(client record) -> failures."""
    c_ok = press_ok(client)
    if not c_ok["pressed"]:
        ctx[key] = {"clientOk": c_ok, "stacks": {"host": stack(host), "client": stack(client)}}
        return [c_ok["note"]]
    seen, t0, geo_since = [], time.time(), None
    while time.time() - t0 < OK_S:
        st = stack(client)
        t = st[-1] if st else None
        if t not in seen:
            seen.append(t)
        if st[-2:] == [cls, "ErrorMessageState"]:
            break
        if t == "GeoscapeState":
            geo_since = geo_since or time.time()
            if time.time() - geo_since >= GEO_STEADY_S:
                break
        else:
            geo_since = None
        time.sleep(0.2)
    h_ok = press_ok(host)
    ok, secs = wait_until(lambda: forced_tail(host, cls), OK_S) if h_ok["pressed"] else (False, 0)
    ctx[key] = {"clientOk": c_ok, "clientTops": seen, "hostOk": h_ok, "hostForced": ok, "hostSecs": secs,
                "stacks": {"host": stack(host), "client": stack(client)}}
    if not ok:
        capture(f"{key} host forced {cls}", f"the host's stack {stack(host)} after its OK (want it to end {cls} + "
                f"ErrorMessageState; host OK {h_ok})", (host, client))
    herr, cst = err_text(host), stack(client)
    ctx[key]["hostBox"] = herr
    ctx[key]["clientRecord"] = rec_keys(client)
    if cst[-2:] != [cls, "ErrorMessageState"]:
        return [f"the client's stack {cst} after both OKs has no forced {cls} under an ErrorMessageState - it reached "
                f"{cst[-1] if cst else None} with no forced screen (F5432)"]
    f = []
    cerr = err_text(client)
    ctx[key]["clientBox"] = cerr
    if not (cerr and cerr == herr and mark in cerr):
        f.append(f"the client's box {cerr!r} != the host's {herr!r} (want equal, holding {mark!r})")
    if record_check is not None:
        f += record_check(record(client))
    return f


def storage_record(rec):
    fo = rec.get("forced") if isinstance(rec.get("forced"), dict) else {}
    return [] if fo.get("storage") == 1 else [f"the client's battleEnd.forced={rec.get('forced')!r} (want storage 1)"]


def boxes_to_screens(host, client, ctx, key, cls):
    """Dismiss both machines' ErrorMessageState boxes; both forced screens up (rows listed) within PAGE_S."""
    d = {gc.name: dismiss_box(gc) if top(gc) == "ErrorMessageState" else None for gc in (host, client)}
    ok, secs = wait_until(lambda: screen_ready(host, cls) and screen_ready(client, cls), PAGE_S)
    ctx[key] = {"dismissed": d, "up": ok, "secs": secs, "stacks": {gc.name: stack(gc) for gc in (host, client)}}
    return [] if ok else [f"forced {cls} not up on both within {PAGE_S}s of the boxes (stacks {ctx[key]['stacks']})"]


def held_click(gc, caption, cls, ctx, key):
    """With gc held: click `caption`, then sample its top for HOLD_SAMPLE_S - every sample must be cls (the screen stays
    until the host's apply / answer reaches it, MR9 / MR10). Returns the failures (the hold is NOT released here)."""
    c = p3.click(gc, caption)
    tops, t0 = [], time.time()
    while time.time() - t0 < HOLD_SAMPLE_S:
        t = top(gc)
        if t not in tops:
            tops.append(t)
        time.sleep(0.1)
    ctx[key] = {"click": c, "tops": tops}
    return [] if tops == [cls] else [f"{gc.name}'s {cls} left at submit (tops {tops} within {HOLD_SAMPLE_S}s of "
                                     f"{caption!r}; want it to stay until the host answers, MR10)"]


def wait_answer(gc, f0, reason, ctx, key):
    """The host's rejection reached gc: failCount f0 + 1 and lastFail == reason within ANSWER_S (recorded at receipt,
    even while held)."""
    last = {}

    def got():
        last.update(sstats(gc))
        return last.get("failCount") == f0 + 1 and last.get("lastFail") == reason
    ok, secs = wait_until(got, ANSWER_S, 0.1)
    ctx[key] = {"ok": ok, "secs": secs, "stats": dict(last)}
    return [] if ok else [f"{gc.name} shared_stats {dict(last)} {ANSWER_S}s after the confirm (want failCount "
                          f"{f0 + 1}, lastFail {reason!r})"]


def box_over(gc, under, ctx, key):
    """After a release: gc's top CoopState (the fail box, code FAIL_BOX) with `under` directly below within PAGE_S."""
    ok, secs = wait_until(lambda: stack(gc)[-2:] == [under, "CoopState"], PAGE_S)
    info = dialog(gc)
    ctx[key] = {"ok": ok, "secs": secs, "stack": stack(gc), "dialog": info}
    f = [] if ok else [f"{gc.name}'s stack {stack(gc)} {PAGE_S}s after the release (want {under} + CoopState fail box)"]
    if ok and info.get("code") != FAIL_BOX:
        f.append(f"{gc.name}'s CoopState code {info.get('code')} (want {FAIL_BOX}, the fail box)")
    return f


def world_same(host, client, ctx, key):
    return p3.world_same(host, client, ctx, key)


def crafts_rifles(gc):
    return rifles(gc)["craft"]


# ----- D2c -----


def d2c_cells(host, client, ctx):
    def c2():
        f = boxes_to_screens(host, client, ctx, "boxes", "SellState")
        if f:
            return f
        r, rv = rows(client), rifles(client)
        qty, amt = row_of(r, RIFLE)
        hq, _ha = row_of(rows(host), RIFLE)
        want = rv["stock"] + rv["craft"] + rv["xfer"]
        okv = ok_visible(r, SELL_OK)
        ctx["c2"] = {"clientRifle": [qty, amt], "hostRifle": hq, "rifles": rv, "want": want, "okVisible": okv}
        f = [] if qty == want else [f"the client's forced SellState lists Rifle {qty} (want stock {rv['stock']} + craft "
                                    f"{rv['craft']} + transfers {rv['xfer']} = {want}, MR15)"]
        if okv is not False:
            f.append(f"the client's {SELL_OK} visible={okv!r} on its forced SellState (want False: still over)")
        return f

    def c3():
        rv0 = {gc.name: rifles(gc) for gc in (host, client)}
        want = rv0["client"]["stock"] + 1
        a = p3.set_amount(client, want, item=RIFLE)
        ctx["c3"] = {"before": rv0, "set": a}
        if not (a.get("ok") and a.get("after") == want and a.get("okVisible") is True):
            return [f"client screen_set_amount Rifle {want}: {a} (want after {want}, okVisible True)"]
        ctx["c3"]["hold"] = hold(client, True)
        f = held_click(client, SELL_OK, "SellState", ctx, "c3click")
        ctx["c3"]["release"] = hold(client, False)
        if f:
            return f
        ok, secs = wait_until(lambda: top(host) == "GeoscapeState" and top(client) == "GeoscapeState", SCREEN_S)
        ctx["c3"]["closed"] = {"ok": ok, "secs": secs, "stacks": {gc.name: stack(gc) for gc in (host, client)}}
        if not ok:
            return [f"the forced SellStates did not both close themselves within {SCREEN_S}s of the release (stacks "
                    f"{ctx['c3']['closed']['stacks']})"]
        last = {}

        def minus_one():
            for gc in (host, client):
                last[gc.name] = crafts_rifles(gc)
            return all(last[n] == rv0[n]["craft"] - 1 for n in last)
        ok, secs = wait_until(minus_one, EQUAL_S)
        ctx["c3"]["craftRifles"] = {"before": {n: rv0[n]["craft"] for n in rv0}, "after": dict(last), "secs": secs}
        f = [] if ok else [f"crafts' rifles {dict(last)} after the sale (want {rv0['host']['craft'] - 1} on both: the "
                           f"sale reaches one craft rifle, MR15)"]
        f += world_same(host, client, ctx, "c3world")
        cs = [gc.name for gc in (host, client) if not no_coopstate(gc)]
        if cs:
            f.append(f"a CoopState on {cs}'s stack")
        return f
    return [
        ("1 both OKs: the client's forced SellState under the storage box",
         lambda: both_oks_forced(host, client, ctx, "c1", "SellState", STORAGE_MARK, storage_record)),
        ("2 the client's forced SellState lists stock + craft + transfer rifles, OK hidden", c2),
        ("3 the sale reaches a craft rifle; both forced SellStates close themselves", c3),
    ]


# ----- D2e -----


def d2e_cells(host, client, ctx):
    def c1():
        hygiene(host, client, ctx)
        if not p3.to_page2(client):
            return [f"the client's debriefing did not reach page 2 (stack {stack(client)})"]
        f = p3.open_screen(client, "SELL", "SellState", ctx, "c1open")
        if f:
            return f
        ok, _s = wait_until(lambda: screen_ready(client, "SellState"), PAGE_S)
        q, a = row_of(rows(client), T)
        ctx["c1"] = {"T": [q, a], "ready": ok}
        if q != T_QTY:
            return [f"the client's page-3 SellState lists {T} {q} (want {T_QTY})"]
        ctx["c1"]["hold"] = hold(client, True)
        if ctx["c1"]["hold"] is not True:
            return [f"client shared_update_defer on answered deferred={ctx['c1']['hold']!r}"]
        r = host.cmd({"cmd": "sell", "item": T, "count": T_QTY - 1})
        ok, secs = wait_until(lambda: stock_of(host, T) == 1, PAGE_S)
        ctx["c1"]["hostSell"] = {"resp": {k: r.get(k) for k in ("ok", "sent", "error")}, "applied": ok, "secs": secs,
                                 "hostStockT": stock_of(host, T), "hostTop": top(host)}
        f = [] if r.get("ok") and r.get("sent") else [f"host sell {T} {T_QTY - 1} answered {ctx['c1']['hostSell']}"]
        if not ok:
            f.append(f"the host's stock of {T} {stock_of(host, T)} {PAGE_S}s after its sale (want 1)")
        return f

    def c2():
        a = p3.set_amount(client, T_QTY, item=T)
        ctx["c2"] = {"set": a}
        if not (a.get("ok") and a.get("after") == T_QTY):
            hold(client, False)
            return [f"client screen_set_amount {T} {T_QTY}: {a}"]
        f0 = sstats(client).get("failCount") or 0
        ctx["c2"]["failCount0"] = f0
        stays = held_click(client, SELL_OK, "SellState", ctx, "c2click")
        ans = wait_answer(client, f0, NOT_ENOUGH, ctx, "c2answer")
        ctx["c2"]["release"] = hold(client, False)
        if stays:
            return [f"the page-3 SellState is gone at submit (F2501): " + "; ".join(stays)] + ans
        return ans or box_over(client, "SellState", ctx, "c2box")

    def c3():
        b = client.cmd({"cmd": "coop_dialog_back"})
        last = {}

        def rebuilt():
            if not screen_ready(client, "SellState"):
                return False
            last["T"] = row_of(rows(client), T)
            return last["T"] == (T_QTY, 0)
        ok, secs = wait_until(rebuilt, SCREEN_S)
        ctx["c3"] = {"back": {k: b.get(k) for k in ("ok", "error")}, "rebuilt": ok, "secs": secs, "T": last.get("T"),
                     "stack": stack(client)}
        if not ok:
            return [f"the client's page-3 SellState not rebuilt with {T} ({T_QTY}, amount 0) within {SCREEN_S}s "
                    f"(seen {last.get('T')}, stack {stack(client)})"]
        a = p3.set_amount(client, 1, item=T)
        if not (a.get("ok") and a.get("after") == 1):
            return [f"client screen_set_amount {T} 1: {a}"]
        c = p3.click(client, SELL_OK)
        ok, secs = wait_until(lambda: top(client) == "DebriefingState", SCREEN_S)
        ctx["c3"]["sale"] = {"set": a, "click": c, "closed": ok, "secs": secs, "stack": stack(client)}
        if not ok:
            return [f"the client's page-3 SellState not closed within {SCREEN_S}s of its accepted sale (stack "
                    f"{stack(client)})"]
        return p3.count_is((host, client), T, T_QTY - 1, ctx, "c3count")
    return [
        ("1 the client's page-3 SellState open, held; the host sells T", c1),
        ("2 the rejected page-3 sale keeps its screen under the fail box", c2),
        ("3 the rebuilt page-3 SellState sells 1 and closes on the host's answer", c3),
    ]


# ----- D2d -----


def d2d_cells(host, client, ctx):
    def c1():
        hygiene(host, client, ctx)
        f = both_oks_forced(host, client, ctx, "c1", "SellState", STORAGE_MARK, storage_record)
        return f or boxes_to_screens(host, client, ctx, "boxes", "SellState")

    def c2():
        q0, _a = row_of(rows(client), RIFLE)
        s0 = stock_of(host, RIFLE)
        ctx["c2"] = {"clientRifle0": q0, "hostStock0": s0, "hold": hold(client, True)}
        r = host.cmd({"cmd": "sell", "item": RIFLE, "count": D2D_HOST_SELL})
        ok, secs = wait_until(lambda: stock_of(host, RIFLE) == s0 - D2D_HOST_SELL, PAGE_S, 0.1)
        t_change = time.time()
        hb = rifles(host)
        ctx["c2"]["hostSell"] = {"resp": {k: r.get(k) for k in ("ok", "sent", "error")}, "applied": ok, "secs": secs,
                                 "host": hb, "hostTop": top(host)}
        f = [] if r.get("ok") and r.get("sent") and ok else [f"host sell Rifle {D2D_HOST_SELL}: {ctx['c2']['hostSell']}"]
        if not f and not hb["used"] > hb["available"]:
            f.append(f"the host's base is no longer over after its sale ({hb}): D2d needs it still over")
        if f or q0 is None:
            hold(client, False)
            return f or [f"the client's forced SellState lists no Rifle row"]
        a = p3.set_amount(client, q0 - D2D_SHORT, item=RIFLE)
        ctx["c2"]["set"] = a
        if not (a.get("ok") and a.get("after") == q0 - D2D_SHORT and a.get("okVisible") is True):
            hold(client, False)
            return [f"client screen_set_amount Rifle {q0 - D2D_SHORT}: {a} (want okVisible True)"]
        f0 = sstats(client).get("failCount") or 0
        stays = held_click(client, SELL_OK, "SellState", ctx, "c2click")
        ans = wait_answer(client, f0, NOT_ENOUGH, ctx, "c2answer")
        ctx["c2"]["release"] = hold(client, False)
        ctx["c2"]["heldAfterChangeS"] = round(time.time() - t_change, 2)
        return stays + ans or box_over(client, "SellState", ctx, "c2box")

    def c3():
        q0 = ctx["c2"]["clientRifle0"]
        b = client.cmd({"cmd": "coop_dialog_back"})
        last = {}

        def rebuilt():
            if not screen_ready(client, "SellState"):
                return False
            r = rows(client)
            last["rifle"], last["ok"] = row_of(r, RIFLE), ok_visible(r, SELL_OK)
            return last["rifle"] == (q0 - D2D_HOST_SELL, 0)
        ok, secs = wait_until(rebuilt, SCREEN_S)
        ctx["c3"] = {"back": {k: b.get(k) for k in ("ok", "error")}, "rebuilt": ok, "secs": secs, "last": dict(last),
                     "stack": stack(client)}
        if not ok:
            return [f"the client's forced SellState not rebuilt with Rifle ({q0 - D2D_HOST_SELL}, amount 0) within "
                    f"{SCREEN_S}s (seen {last.get('rifle')}, stack {stack(client)})"]
        return [] if last["ok"] is False else [f"the client's rebuilt SellState {SELL_OK} visible={last['ok']!r} "
                                               f"(want False: still forced)"]
    return [
        ("1 both OKs: both forced SellStates up", c1),
        ("2 the rejected forced sale keeps its screen under the fail box", c2),
        ("3 the forced SellState rebuilt and still forced", c3),
    ]


# ----- D2f -----


def d2f_cells(host, client, ctx):
    def c1():
        hygiene(host, client, ctx)
        if not (screen_ready(host, "SellState") and screen_ready(client, "SellState")):
            return [f"D2f needs both forced SellStates up (stacks host {stack(host)} client {stack(client)})"]
        hb = rifles(host)
        n = int(math.ceil((hb["used"] - hb["available"]) / RIFLE_SIZE - 1e-9)) + 1
        ctx["c1"] = {"host": hb, "n": n, "hold": hold(client, True)}
        if n > hb["stock"]:
            hold(client, False)
            return [f"the host's stock {hb['stock']} cannot clear its base (needs {n} rifles)"]
        r = host.cmd({"cmd": "sell", "item": RIFLE, "count": n})
        ok, secs = wait_until(lambda: top(host) == "GeoscapeState", PAGE_S, 0.1)
        ctx["tChange"] = time.time()
        ctx["c1"]["hostSell"] = {"resp": {k: r.get(k) for k in ("ok", "sent", "error")}, "closed": ok, "secs": secs,
                                 "hostStack": stack(host), "host": rifles(host)}
        if not (r.get("ok") and r.get("sent") and ok):
            hold(client, False)
            return [f"the host's forced SellState did not close itself within {PAGE_S}s of its clearing sale "
                    f"({ctx['c1']['hostSell']})"]
        return []

    def c2():
        cb = rifles(client)
        n2 = int(math.ceil((cb["used"] - cb["available"]) / RIFLE_SIZE - 1e-9)) + 1
        a = p3.set_amount(client, n2, item=RIFLE)
        ctx["c2"] = {"client": cb, "n2": n2, "set": a}
        if not (a.get("ok") and a.get("after") == n2 and a.get("okVisible") is True):
            ctx["c2"]["release"] = hold(client, False)
            return [f"client screen_set_amount Rifle {n2}: {a} (want okVisible True: its held view still over)"]
        f0 = sstats(client).get("failCount") or 0
        c = p3.click(client, SELL_OK)
        f = wait_answer(client, f0, FORCED_RESOLVED, ctx, "c2answer")
        ctx["c2"]["click"] = c
        ctx["c2"]["noCoopState"] = no_coopstate(client)
        if not ctx["c2"]["noCoopState"]:
            f.append(f"a CoopState on the client's stack {stack(client)} while held")
        return f

    def c3():
        ctx["c3"] = {"release": hold(client, False), "heldAfterChangeS": round(time.time() - ctx["tChange"], 2)}
        tops, t0 = [], time.time()
        while time.time() - t0 < SCREEN_S:
            t = top(client)
            if t not in tops:
                tops.append(t)
            if any("CoopState" in s for s in stack(client)):
                break
            if t == "GeoscapeState" and time.time() - t0 >= 2.0:
                break
            time.sleep(0.2)
        ctx["c3"]["tops"] = tops
        ctx["c3"]["stack"] = stack(client)
        f = []
        if not no_coopstate(client) or "CoopState" in tops:
            f.append(f"a CoopState on the client after the release (tops {tops}, stack {stack(client)}; want the "
                     f"already-solved confirm dropped silently, PR-32)")
        if top(client) != "GeoscapeState":
            f.append(f"the client's forced SellState did not close itself within {SCREEN_S}s of the release (tops "
                     f"{tops})")
        return f + world_same(host, client, ctx, "c3world")
    return [
        ("1 the host's clearing sale closes its own forced SellState", c1),
        ("2 the client's stale forced confirm is dropped (coop_forced_resolved)", c2),
        ("3 released: the client's forced SellState closes itself, no box", c3),
    ]


# ===================== one boot =====================


def run_cells(cells):
    """The row's cells in order -> the verdict (None = pass). A FixtureMiss is a FIXTURE-STOP, not a cell failure."""
    out = []
    for i, (name, fn) in enumerate(cells):
        try:
            f = fn()
        except FixtureMiss as e:
            out.append({"cell": name, "pass": False, "fixtureStop": str(e)})
            return f"FIXTURE-STOP in cell {name}: {e}", out
        except Exception as e:
            f = [f"{type(e).__name__}: {short(e, 600)}"]
        out.append({"cell": name, "pass": not f, "fails": f})
        if f:
            rest = [c[0].split(" ")[0] for c in cells[i + 1:]]
            return f"cell {name}: " + "; ".join(f) + (f" | cells {rest} not reached" if rest else ""), out
    return None, out


def guard(host, client, crash0, ctx, last):
    """Every row: host fatalVote.armed 0, no new crash log; the boot's last row: the client zero-disk."""
    f = []
    armed = (event_state(host).get("fatalVote") or {}).get("armed")
    if armed != 0:
        f.append(f"host fatalVote.armed={armed!r} (want 0, F4544)")
    new_crash = sorted(session._crash_log_snapshot() - crash0)
    ctx["newCrashLogs"] = new_crash
    if new_crash:
        f.append(f"new crash log(s): {new_crash}")
    if last:
        try:
            session.assert_client_zero_disk(client.user_dir)
        except AssertionError as e:
            f.append(str(e))
    return f


def run_boot(boot, tag, port, opts, pre_fn, rows_spec, results, walls, needs=None, prefix="w2p7-scd2"):
    """One boot: bring-up + pre_fn(js, ctx) (pre-cell), then each row (EVIDENCE, PASS / FAIL). `needs` = {rid:
    earlier rid}: a row whose prerequisite row failed is reported "not reached" without running."""
    t0, js, pre = time.time(), None, {}
    crash0 = session._crash_log_snapshot()
    miss = None
    needs = needs or {}
    try:
        try:
            js = bring_up(tag, port, opts)
            pre_fn(js, pre)
        except Exception as e:
            miss = f"pre-cell (FIXTURE-STOP) {e if isinstance(e, FixtureMiss) else short(e, 800)}"
        for n, (rid, cells_fn) in enumerate(rows_spec):
            tr = time.time()
            ctx = {"row": rid, "boot": boot, "pre": pre if n == 0 else {"see": rows_spec[0][0]}}
            verdict = miss
            if verdict is None and rid in needs and not results.get(needs[rid]):
                verdict = f"not reached - needs {needs[rid]}'s forced screen ({needs[rid]} failed)"
                ctx["notReached"] = True
            elif verdict is None:
                verdict, ctx["cells"] = run_cells(cells_fn(js.host, js.client, ctx))
                g = guard(js.host, js.client, crash0, ctx, n == len(rows_spec) - 1)
                if g:
                    verdict = (verdict + " | " if verdict else "") + "guard: " + "; ".join(g)
            if js is not None:
                try:
                    ctx["end"] = {"host": view(js.host), "client": view(js.client)}
                except Exception as e:
                    ctx["end"] = f"probe failed: {short(e)}"
            ctx["wall"] = round(time.time() - tr, 1)
            evidence(rid, ctx)
            results[rid] = verdict is None
            print(f"PASS {rid}" if verdict is None else f"FAIL {rid}: {verdict}", flush=True)
    finally:
        if js is not None:
            # every TEST-ONLY hold off before the shutdown (each lever is inert unless armed)
            for gc, lever in ((js.host, "shared_update_defer"), (js.client, "shared_update_defer"),
                              (js.host, "hold_world_stream"), (js.client, "hold_world_adopt")):
                try:
                    gc.cmd({"cmd": lever, "on": False})
                except Exception as e:
                    print(f"[{prefix}] release {lever}: {short(e)}", flush=True)
            try:
                js.shutdown()
            except Exception as e:
                print(f"[{prefix}] shutdown: {short(e)}", flush=True)
        walls[boot] = round(time.time() - t0, 1)


BOOTS = (("ST1", "w2p7scd2_st1", (("D2c", d2c_cells),), {}),
         ("ST2", "w2p7scd2_st2", (("D2e", d2e_cells), ("D2d", d2d_cells), ("D2f", d2f_cells)), {"D2f": "D2d"}))


def main():
    t0, results, walls = time.time(), {}, {}
    for boot, tag, rows_spec, needs in BOOTS:
        run_boot(boot, tag, BOOT_PORT[boot], OPTS_ST, lambda js, ctx, b=boot: fx_st(js, ctx, b), rows_spec, results,
                 walls, needs)
    order = [rid for _, _, rs, _ in BOOTS for rid, _ in rs]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_w2_shared_forced_storage: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (boot walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
