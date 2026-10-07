"""W2-H20d (F8551; owner D226 a; spec rewrite/prompts/w2h20d_shared_craft_deployment.md (f), QD1 a .. QD8 a, AMENDMENT H20d-1; TASK 0
rewrite/w2h20d-task0/CONSTANTS.md): in SHARED, a craft type's soldier deployment saved or deleted from the Ufopaedia's craft preview (the
craft article, INFO, "Preview", the abort icon, OK; Ctrl+OK deletes) stays on the machine that pressed OK: no command carries it and the
world checksum does not count it, so only a world copy moves the host's entry to the second player (F8874-F8876).
D(gc) = base_screen_op {op: craft_deployment, craft_type: STR_SKYRANGER} (saved, positions, crafts); Dsky = D's crafts entry with id SKY
(customDeployment); EQ = both D equal in saved and positions. SKY, seats and HostBase from h20.setup (S25); keys from read_key (F3091).
PV(gc, erase) = keyGeoUfopedia, "X-COM CRAFT", the SKYRANGER row, keyGeoUfopedia (INFO), "Preview", close_briefing, battle_action abort,
[modstate ctrl], OK, [modstate none], end_turn_button, close_screens (<= 2 s per probe, SETTLE 0.3 s before a key or click, F2888; never
close_screens or a copy over an open preview, F8883). COPY = client force_resync, then both stacks [GeoscapeState] and EQ <= 30 s.
SET(want) = host PV(erase = not want) when the host's saved != want, COPY when not EQ, client shared_reset_resync_stats; guard saved ==
want on both and EQ. MARK = W2-H20c deploy_mark {HostBase, SKY} on both, then Dsky true on both. reqs / fails = the client's
shared_resync_stats.requests / shared_stats.failCount. W = 6 s at 0.25 s polls; N = 14 positions (TASK 0).
  Boot A bring_up("w2h20da", (49503, 49504, 47957)):
    HD-0 (guard) the craft soldier screen's "Preview" is hidden on both (the per-craft save W1, F8873); D unsaved on both.
    HD-1 SET(false); MARK; host PV(save). Non-vacuity: the host's D saved, N positions, Dsky false at once. RED: the client's D unsaved
        after W. Green: the client's D == the host's and its Dsky false within W; reqs and fails unchanged.
    HD-2 SET(true); host PV(erase). Non-vacuity: the host's D unsaved at once. RED: the client's D saved after W. Green: reqs unchanged.
    HD-3 SET(false); MARK; client PV(save). Non-vacuity: the client's D saved, N, Dsky false. RED: the host's D unsaved after W.
    HD-4 SET(true); client PV(erase). Non-vacuity: the client's D unsaved. RED: the host's D saved after W.
    HD-5 SET(false); client shared_cmd craft_deployment {STR_SKYRANGER, saved, [[1, 2, 0, 3]]}, baseId -1. RED: fails +1, lastFail
        "unknown command: craft_deployment" within W (cleanup: ONE close_screens on the client). Green: both D saved [[1, 2, 0, 3]] within
        W, fails unchanged 1 s later; negative control STR_NO_SUCH_CRAFT: fails +1, "rejected", D unchanged, ONE close_screens.
    HD-6 (guard, last in Boot A) js.finish(): world equality, the replica's zero disk.
  Boot S (SEPARATE, tag w2h20ds, labels 49505 / 49506, lobby "47958"): HD-S (guard) client PV(save): the client's D saved, the host's not;
    both shared_stats cmd / applyCount / failCount unchanged 1 s later.
A row whose named RED cell fails evaluates no later cell (F8045). EVIDENCE line per row before its verdict; a failed row prints ONE CAPTURE
line (both machines' D, stacks, pedia_state, shared_stats, shared_resync_stats); a boot miss fails its rows "boot". Every row runs after a
failure. ONE run (WV-D95); exit 0 iff everything passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
import test_w2_shared_base_equip as h20  # noqa: E402  (main-guarded: X, Row, setup, boot_miss, q / stack / wait_until / short)
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402
from test_w2_inventory_held import read_key  # noqa: E402  (main-guarded)

TAG_A, PORTS_A = "w2h20da", (49503, 49504, 47957)
TAG_S, LABELS_S, LOBBY_S = "w2h20ds", (49505, 49506), "47958"
HB, CB, SKYR, GEO = "HostBase", "ClientBase", "STR_SKYRANGER", "GeoscapeState"
BS, SFN, BRF, AMS = "BattlescapeState", "StatsForNerdsState", "BriefingState", "AbortMissionState"
W, POLL, STEP, SETTLE, CONV, N = 6.0, 0.25, 2.0, 0.3, 30.0, 14  # TASK 0: N = the Skyranger's 14 stand-in soldiers
RAW, UNKNOWN, NO_SUCH = [[1, 2, 0, 3]], "unknown command: craft_deployment", "STR_NO_SUCH_CRAFT"
ROWS_A, ROWS_S = ["HD-%d" % n for n in range(7)], ["HD-S"]
ORDER = ROWS_A + ROWS_S
q, stack, wait_until, short = h20.q, h20.stack, h20.wait_until, h20.short


def D(gc):
    r = q(gc, {"cmd": "base_screen_op", "op": "craft_deployment", "craft_type": SKYR})
    return {k: r.get(k) for k in ("saved", "positions", "crafts", "error")}


def dsky(d, sky):
    return next((c.get("customDeployment") for c in d.get("crafts") or [] if c.get("id") == sky), None)


def same(a, b):
    return [a.get("saved"), a.get("positions")] == [b.get("saved"), b.get("positions")]


def both(x):
    return {g.name: D(g) for g in (x.host, x.client)}


def eq(x):
    return same(D(x.host), D(x.client))


def reqs(x):
    return q(x.client, {"cmd": "shared_resync_stats"}).get("requests")


def fails(x):
    r = q(x.client, {"cmd": "shared_stats"})
    return r.get("failCount"), r.get("lastFail")


def stats3(gc):
    r = q(gc, {"cmd": "shared_stats"})
    return {k: r.get(k) for k in ("cmd", "applyCount", "failCount")}


def timed(pred, timeout=W):
    t0 = time.time()
    v = wait_until(pred, timeout, POLL)
    return bool(v), round(time.time() - t0, 2)


def is_dead(s):  # h20.stack's reply for a machine whose socket is gone
    return any(str(e).startswith("<get_state") for e in s)


# ---- PV: the Ufopaedia craft preview drive (TASK 0's values; the test_w2_client_research pd_* shapes) -----------------------------------
def pd(gc):
    return q(gc, {"cmd": "pedia_state"})


def act(gc, obj):
    time.sleep(SETTLE)  # a key or click injected right after a state opens is lost without it (F2888)
    return q(gc, obj)


def caption(gc):
    return [w.get("text") for w in q(gc, {"cmd": "list_widgets"}).get("widgets") or [] if w.get("visible")
            and "TextButton" in str(w.get("type")) and str(w.get("text")).startswith("Preview")]


def pv(gc, keys, erase=False):
    """PV(gc, erase) P1..P12 -> (the first missed step or None, {step: probe})"""
    ev, key = {}, {"cmd": "inject_input", "kind": "key", "key": keys["ufo"]}
    kind = lambda k: wait_until(lambda: pd(gc).get("kind") == k, STEP, 0.05)  # noqa: E731
    on = lambda name: wait_until(lambda: stack(gc)[-1:] == [name], STEP, 0.05)  # noqa: E731

    def miss(name, cond, val):
        ev[name] = val
        return None if cond else name

    def row(p, sec, name):  # the SelectState row's centre x the section click's scale + band (pd_row_click)
        i, lr, s = p["rows"].index(name), p["listRect"], round(sec["winX"] / sec["baseX"])
        x = (lr[0] + lr[2] // 2) * s + sec["winX"] - sec["baseX"] * s
        y = (p["rowY"][i] + p["rowH"][i] // 2) * s + sec["winY"] - sec["baseY"] * s
        return act(gc, {"cmd": "inject_input", "kind": "click", "x": x, "y": y}).get("ok") and kind("article")
    m = miss("P1", stack(gc) == [GEO], stack(gc)) or miss("P2", act(gc, key).get("ok") and kind("start"), pd(gc).get("kind"))
    if m:
        return m, ev
    sec = act(gc, {"cmd": "click_widget", "match": "X-COM CRAFT"})
    kind("select")
    p = pd(gc)
    m = (miss("P3", sec.get("ok") and p.get("kind") == "select" and "SKYRANGER" in (p.get("rows") or []), [sec.get("text"), p.get("rows")])
         or miss("P4", row(p, sec, "SKYRANGER") and pd(gc).get("article") == SKYR, pd(gc).get("article"))
         or miss("P5", act(gc, key).get("ok") and kind("nerds") and len(caption(gc)) == 1, caption(gc))
         or miss("P6", act(gc, {"cmd": "click_widget", "match": "preview"}).get("ok") and on(BRF), stack(gc)))
    if m:
        return m, ev
    cb, dis = q(gc, {"cmd": "close_briefing"}), 0
    while not on(BS) and dis < 3:  # dismiss only a top other than BattlescapeState that stays 2 s (AMENDMENT H6)
        dis += 1
        q(gc, {"cmd": "dismiss_popup"})
    pre = q(gc, {"cmd": "battle_state"}).get("isPreview")
    m = (miss("P7", cb.get("ok") and stack(gc)[-1:] == [BS] and pre is True, [stack(gc), pre, dis])
         or miss("P8", act(gc, {"cmd": "battle_action", "action": "abort"}).get("ok") and on(AMS), stack(gc))
         or (erase and miss("P9", act(gc, {"cmd": "inject_input", "kind": "modstate", "mod": "ctrl"}).get("modState") == "ctrl", "ctrl")))
    if m:
        return m, ev
    o = act(gc, {"cmd": "click_widget", "match": "ok"})
    back = on(BS)
    if erase:  # clear the latch once the click is consumed (a cleared latch pushes no key)
        q(gc, {"cmd": "inject_input", "kind": "modstate", "mod": "none"})
    if miss("P10", o.get("text") == "OK" and back, [o.get("text"), stack(gc)]):
        return "P10", ev
    act(gc, {"cmd": "battle_action", "action": "end_turn_button"})
    done, dis = (lambda: stack(gc)[-1:] == [SFN] and q(gc, {"cmd": "world_state"}).get("has_battle") is False), 0
    while not wait_until(done, 1.0, 0.05) and dis < 3:
        dis += 1
        if stack(gc)[-1:] not in ([BS], [SFN]):  # dismiss only a top other than the preview / the INFO screen that stays 1 s
            q(gc, {"cmd": "dismiss_popup"})
    ev["P11 caption"] = c11 = caption(gc)
    if miss("P11", done() and len(c11) == 1, [stack(gc), dis]):
        return "P11", ev
    q(gc, {"cmd": "close_screens"})
    return miss("P12", wait_until(lambda: stack(gc) == [GEO], STEP, 0.05), stack(gc)), ev
# ----------------------------------------------------------------------------------------------------------------------------------------


def leave(gc):
    """a stopped row's screens: an open preview is ended through its own buttons (never close_screens over it, F8883)"""
    q(gc, {"cmd": "inject_input", "kind": "modstate", "mod": "none"})
    for _ in range(5):
        s = stack(gc)
        if is_dead(s) or s == [GEO]:
            break
        if s[-1:] == [AMS]:
            q(gc, {"cmd": "click_widget", "match": "cancel"})
        elif s[-1:] == [BRF]:
            q(gc, {"cmd": "close_briefing"})
        elif q(gc, {"cmd": "world_state"}).get("has_battle"):
            q(gc, {"cmd": "battle_action", "action": "end_turn_button"})
        else:
            q(gc, {"cmd": "close_screens"})
        wait_until(lambda: stack(gc) != s, STEP, 0.05)
    return stack(gc)


def copy(x):
    t0 = time.time()
    rep = q(x.client, {"cmd": "force_resync"})
    ok = wait_until(lambda: stack(x.host) == [GEO] and stack(x.client) == [GEO] and eq(x), CONV, POLL)
    return {"ok": bool(ok) and rep.get("sent") is True, "force_resync": rep, "s": round(time.time() - t0, 2)}


def set_(r, x, want):
    """SET(want): every row's start is equal on the red and the green build (S2 is not in the checksum: no re-copy repairs it)"""
    ev = r.ev["SET(%s)" % want] = {}
    if D(x.host).get("saved") is not want:
        m, ev["host PV"] = pv(x.host, x.keys["host"], erase=not want)
        if not r.cell(f"G: SET host preview drive {m}", m is None, ev["host PV"]):
            return False
    if not eq(x):
        ev["COPY"] = cp = copy(x)
        if not r.cell("G: SET COPY (both [GeoscapeState] and EQ within 30 s)", cp["ok"], cp):
            return False
    ev["reset"] = q(x.client, {"cmd": "shared_reset_resync_stats"}).get("ok")
    ev["D"] = d = both(x)
    return r.cell(f"G: SET D saved == {want} on both, EQ", ev["reset"] is True and same(d["host"], d["client"])
                  and all(e.get("saved") is want for e in d.values()), d)


def mark(r, x):
    m = {g.name: q(g, {"cmd": "base_screen_op", "op": "deploy_mark", "base": HB, "craft_id": x.sky, "craft_type": SKYR})
         .get("customDeployment") for g in (x.host, x.client)}
    r.ev["MARK Dsky"] = d = {g.name: dsky(D(g), x.sky) for g in (x.host, x.client)}
    return r.cell("non-vacuity: MARK -> Dsky true on both", all(v is True for v in list(m.values()) + list(d.values())), [m, d])


def closebox(c):
    """ONE close_screens on the client (the refusal box)"""
    wait_until(lambda: any("CoopState" in e for e in stack(c)), 3.0, 0.05)
    out = {"stack": stack(c), "close_screens": q(c, {"cmd": "close_screens"}).get("popped")}
    wait_until(lambda: stack(c) == [GEO], 5.0, 0.05)
    out["after"] = stack(c)
    return out


def save_row(x, r, presser, other, red):
    """HD-1 (host) / HD-3 (client): SET(false); MARK; the presser's PV(save)."""
    if not (set_(r, x, False) and mark(r, x)):
        return r.evidence()
    r0, f0 = reqs(x), fails(x)[0]
    m, r.ev["PV " + presser.name] = pv(presser, x.keys[presser.name])
    r.ev["at once"] = d1 = both(x)
    full = (lambda: same(D(other), D(presser)) and D(other).get("saved") is True and dsky(D(other), x.sky) is False)
    got, s = timed(full) if m is None else (False, 0.0)
    r.ev.update({"wait s": s, "end": both(x), "reqs": [r0, reqs(x)], "fails": [f0, fails(x)[0]]})
    e, me = r.ev["end"], d1[presser.name]
    r.evidence()
    if not (r.cell(f"preview drive {m} ({presser.name})", m is None, r.ev["PV " + presser.name])
            and r.cell(f"non-vacuity: the {presser.name}'s D saved, {N} positions, Dsky false at once", me.get("saved") is True
                       and len(me.get("positions") or []) == N and dsky(me, x.sky) is False, me)
            and r.cell(red, e[other.name].get("saved") is True, {other.name + " D after W": e[other.name]})):
        return
    r.cell(f"the {other.name}'s D != the {presser.name}'s or its Dsky not false within W", got, e)
    r.cell("the client asked for a world re-copy (reqs changed)", r.ev["reqs"][0] == r.ev["reqs"][1], r.ev["reqs"])
    r.cell("the client's failCount changed", r.ev["fails"][0] == r.ev["fails"][1], r.ev["fails"])


def delete_row(x, r, presser, other, red):
    """HD-2 (host) / HD-4 (client): SET(true); the presser's PV(erase) (Ctrl held on OK)."""
    if not set_(r, x, True):
        return r.evidence()
    r0 = reqs(x)
    m, r.ev["PV " + presser.name] = pv(presser, x.keys[presser.name], erase=True)
    r.ev["at once"] = d1 = both(x)
    got, s = timed(lambda: D(other).get("saved") is False) if m is None else (False, 0.0)
    r.ev.update({"wait s": s, "end": both(x), "reqs": [r0, reqs(x)]})
    r.evidence()
    if not (r.cell(f"preview drive {m} ({presser.name})", m is None, r.ev["PV " + presser.name])
            and r.cell(f"non-vacuity: the {presser.name}'s D unsaved at once", d1[presser.name].get("saved") is False, d1[presser.name])
            and r.cell(red, got and r.ev["end"][other.name].get("saved") is False, {other.name + " D after W": r.ev["end"][other.name]})):
        return
    r.cell("the client asked for a world re-copy (reqs changed)", r.ev["reqs"][0] == r.ev["reqs"][1], r.ev["reqs"])


def raw(x, craft_type):
    """the client's shared_cmd craft_deployment; until the client's failCount rises or both D hold RAW (W); the box closed"""
    f0, t0, out = fails(x)[0], time.time(), {}
    out["shared_cmd"] = q(x.client, {"cmd": "shared_cmd", "jcmd": "craft_deployment", "baseId": -1,
                                     "payload": {"craftType": craft_type, "saved": True, "positions": RAW}})

    def settled():
        f, why = fails(x)
        if (f or 0) > (f0 or 0):
            out["refused [s, lastFail]"] = [round(time.time() - t0, 2), why]
            return True
        if all(e.get("saved") is True and e.get("positions") == RAW for e in both(x).values()):
            out["applied s"] = round(time.time() - t0, 2)
            return True
    wait_until(settled, W, POLL)
    out["fails before"] = f0
    out["box"] = closebox(x.client) if "refused [s, lastFail]" in out else None
    out["D"] = both(x)
    return out


def hd_0(x, r):
    out = {}
    for g in (x.host, x.client):
        rep = q(g, {"cmd": "open_screen", "screen": "craft_soldiers", "base": HB, "craft_id": x.sky})
        wait_until(lambda: stack(g)[-1:] == ["CraftSoldiersState"], STEP, 0.05)
        btn = [{k: w.get(k) for k in ("text", "visible")} for w in q(g, {"cmd": "list_widgets"}).get("widgets") or []
               if "TextButton" in str(w.get("type")) and str(w.get("text")).startswith("Preview")]
        cs = q(g, {"cmd": "close_screens"}).get("popped")
        wait_until(lambda: stack(g) == [GEO], STEP, 0.05)
        out[g.name] = {"open_screen": rep, "Preview buttons": btn, "close_screens": cs, "stack": stack(g), "D": D(g)}
    r.ev.update(out)
    r.evidence()
    for g in (x.host, x.client):
        e = out[g.name]
        if r.cell(f"G: {g.name} open_screen craft_soldiers {HB} {x.sky}", e["open_screen"].get("ok") is True and e["stack"] == [GEO], e):
            r.cell(f"the {g.name}'s craft soldier screen shows its per-craft Preview (W1 has no carrier)",
                   e["Preview buttons"] == [{"text": "Preview", "visible": False}], e["Preview buttons"])
        r.cell(f"the {g.name}'s D saved at boot", e["D"].get("saved") is False and e["D"].get("positions") == [], e["D"])


def hd_5(x, r):
    if not set_(r, x, False):
        return r.evidence()
    r.ev["raw"] = a = raw(x, SKYR)
    ref = a.get("refused [s, lastFail]")
    if not ref and "applied s" in a:  # green: the settle, then the negative control
        time.sleep(1.0)
        r.ev["fails 1 s after"] = fails(x)[0]
        r.ev["negative control"] = raw(x, NO_SUCH)
    r.evidence()
    if not (r.cell("G: shared_cmd sent", a["shared_cmd"].get("ok") is True, a["shared_cmd"])
            and r.cell("the host has no carrier for a craft deployment", not (ref and ref[1] == UNKNOWN), a)
            and r.cell(f"both D saved {RAW} within W", not ref and "applied s" in a, a)):
        return
    r.cell("the client's failCount changed after a 1 s settle", r.ev["fails 1 s after"] == a["fails before"],
           [a["fails before"], r.ev["fails 1 s after"]])
    n = r.ev["negative control"]
    nref = n.get("refused [s, lastFail]")
    r.cell(f"negative control: {NO_SUCH} not refused 'rejected' within W, or a D changed",
           nref is not None and nref[1] == "rejected" and n["D"] == a["D"], n)


def hd_6(x, r):
    r.ev.update({"D": both(x), "world_diff now": shared_fixture.world_diff(x.host, x.client),
                 "client save files now": session.save_files(x.js.client_dir)})
    r.evidence()
    try:
        x.js.finish()
    except AssertionError as e:
        r.cell("js.finish", False, short(e, 1500))


def hd_s(x, r):
    h, c = x.host, x.client
    d0 = both(x)
    if not r.cell("G: D unsaved on both at boot (SEPARATE)", all(e.get("saved") is False for e in d0.values()), d0):
        return r.evidence()
    s0 = {g.name: stats3(g) for g in (h, c)}
    m, r.ev["PV client"] = pv(c, x.keys["client"])
    time.sleep(1.0)
    s1, d1 = {g.name: stats3(g) for g in (h, c)}, both(x)
    r.ev.update({"D before": d0, "D 1 s after": d1, "shared_stats before / 1 s after": [s0, s1]})
    r.evidence()
    if not r.cell("preview drive %s (client)" % m, m is None, r.ev["PV client"]):
        return
    r.cell(f"the client's own save is not on the client ({N} positions)", d1["client"].get("saved") is True
           and len(d1["client"].get("positions") or []) == N, d1["client"])
    r.cell("the host's D changed (SEPARATE stays local)", d1["host"].get("saved") is False, d1["host"])
    r.cell("shared_stats cmd / applyCount / failCount changed", s0 == s1, [s0, s1])


class Row(h20.Row):
    def __init__(self, rid, x):
        super().__init__(rid, x)
        self.ev = {"SKY": x.sky, "seats": x.seats, "keys": getattr(x, "keys", None)}

    def report(self, results):
        self.evidence()
        if self.fails:
            for g in (self.x.host, self.x.client):
                p = pd(g)
                self.cap[g.name] = {"D": D(g), "stack": stack(g), "pedia_state": {k: p.get(k) for k in ("top", "kind", "depth", "article")},
                                    "shared_stats": q(g, {"cmd": "shared_stats"}), "shared_resync_stats": q(g, {"cmd": "shared_resync_stats"})}
            print(f"CAPTURE {self.rid}: {json.dumps(self.cap, sort_keys=True, default=str)}", flush=True)
        results[self.rid] = not self.fails
        print(f"PASS {self.rid}" if not self.fails else f"FAIL {self.rid}: " + " | ".join(self.fails), flush=True)


def run_rows(x, rows, results, walls):
    for rid, fn in rows:
        r, t1 = Row(rid, x), time.time()
        try:
            fn(x, r)
        except Exception as e:
            r.cell(f"G: {rid} exception", False, short(e))
        for g in (x.host, x.client):  # a stopped row leaves no screen behind (an open preview ends through its own buttons)
            before = stack(g)
            if not is_dead(before) and before != [GEO]:
                r.cap[f"{g.name} cleanup"] = {"before": before, "pedia_state": pd(g).get("kind"), "after": leave(g)}
        walls[rid] = round(time.time() - t1, 1)
        r.report(results)


def keys(x):
    return {g.name: {"ufo": read_key(g.user_dir, "keyGeoUfopedia"), "cancel": read_key(g.user_dir, "keyCancel")} for g in (x.host, x.client)}


def down(tag, results, fn):
    """A boot's shutdown; a failure is a FAIL line `shutdown <tag>` (exit 2), and the run goes on."""
    try:
        fn()
    except Exception as e:
        results["shutdown " + tag] = False
        print(f"FAIL shutdown {tag}: {short(e, 800)}", flush=True)


def boot_a(results, walls):
    t0, js, x = time.time(), None, None
    try:
        try:
            js = shared_fixture.bring_up(TAG_A, PORTS_A)
            x = h20.X(js.host, js.client, js)
            h20.setup(x)  # option OFF on both, seats differ, the SKYRANGER, the HostBase index (raises on a miss)
            x.keys = keys(x)
            walls["boot " + TAG_A] = round(time.time() - t0, 1)
        except Exception as e:  # a boot miss fails every row of this boot "boot" with ONE CAPTURE line
            return h20.boot_miss(TAG_A, e, ROWS_A, results, x)
        run_rows(x, (("HD-0", hd_0),
                     ("HD-1", lambda x, r: save_row(x, r, x.host, x.client, "the host's saved craft deployment never reached the client")),
                     ("HD-2", lambda x, r: delete_row(x, r, x.host, x.client, "the host's deleted craft deployment stayed on the client")),
                     ("HD-3", lambda x, r: save_row(x, r, x.client, x.host, "the client's saved craft deployment never reached the host")),
                     ("HD-4", lambda x, r: delete_row(x, r, x.client, x.host, "the client's deleted craft deployment stayed on the client")),
                     ("HD-5", hd_5), ("HD-6", hd_6)), results, walls)
    finally:
        if js is not None:
            down(TAG_A, results, js.shutdown)


def boot_s(results, walls):
    t0 = time.time()
    h = GameClient("host", LABELS_S[0], make_user_dir(TAG_S + "_host"))
    c = GameClient("client", LABELS_S[1], make_user_dir(TAG_S + "_client"))
    x = h20.X(h, c, base=CB)
    try:
        try:
            h.spawn(), c.spawn(), h.connect(), c.connect()
            session.new_campaign(h, c, port=LOBBY_S, campaign_mode="coop")
            geo.wait_both_ready(h, c)
            x.seats = {g.name: q(g, {"cmd": "get_coop"}).get("localSeat") for g in (h, c)}
            x.keys = keys(x)
            walls["boot " + TAG_S] = round(time.time() - t0, 1)
        except Exception as e:  # a boot miss fails HD-S "boot" with ONE CAPTURE line
            return h20.boot_miss(TAG_S, e, ROWS_S, results, x)
        run_rows(x, (("HD-S", hd_s),), results, walls)
    finally:
        down(TAG_S, results, lambda: shutdown_clients(h, c))


def main():
    t0, results, walls = time.time(), {}, {}
    boot_a(results, walls)
    boot_s(results, walls)
    failed = [rid for rid in ORDER if not results.get(rid)]
    downs = sorted(k for k, v in results.items() if k.startswith("shutdown") and not v)
    print(f"\ntest_w2_shared_craft_deployment: {len(ORDER) - len(failed)}/{len(ORDER)} passed (fail={failed + downs}) "
          f"walls {json.dumps(walls)} in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed or downs else 0


if __name__ == "__main__":
    sys.exit(main())
