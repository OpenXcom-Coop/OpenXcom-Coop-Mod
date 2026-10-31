"""In SHARED, a craft type's soldier deployment saved or deleted from the Ufopaedia's craft preview (the craft article,
INFO, "Preview", the abort icon, OK; Ctrl+OK deletes) reaches the partner. Without the fix it stays on the machine that
pressed OK: no command carries it and the world checksum does not count it, so only a world copy moves the host's entry
to the second player.
D(gc) = base_screen_op {op: craft_deployment, craft_type: STR_SKYRANGER} (saved, positions, crafts); Dsky = D's crafts
entry with id SKY (customDeployment); EQ = both D equal in saved and positions. SKY, seats and HostBase from sbe.setup;
keys from read_key.
PV(gc, erase) = keyGeoUfopedia, "X-COM CRAFT", the SKYRANGER row, keyGeoUfopedia (INFO), "Preview", close_briefing,
battle_action abort, [modstate ctrl], OK, [modstate none], end_turn_button, close_screens (<= 2 s per probe, SETTLE
0.3 s before a key or click; never close_screens or a copy over an open preview). COPY = client force_resync, then both
stacks [GeoscapeState] and EQ <= 30 s.
SET(want) = host PV(erase = not want) when the host's saved != want, COPY when not EQ, client
shared_reset_resync_stats; guard saved == want on both and EQ. MARK = base_screen_op deploy_mark {HostBase, SKY} on
both, then Dsky true on both. reqs / fails = the client's shared_resync_stats.requests / shared_stats.failCount.
W = 6 s at 0.25 s polls; N = 14 positions.
  SHARED boot bring_up("craft_deployment_shared", (49503, 49504, 47957)):
    craft_deploy_0 (guard) the craft soldier screen's "Preview" (the per-craft save, which nothing carries) is hidden on
        both; D unsaved on both.
    craft_deploy_1 SET(false); MARK; host PV(save). Non-vacuity: the host's D saved, N positions, Dsky false at once.
        Without the fix the client's D is unsaved after W; with it the client's D == the host's and its Dsky is false
        within W; reqs and fails unchanged.
    craft_deploy_2 SET(true); host PV(erase). Non-vacuity: the host's D unsaved at once. Without the fix the client's D
        is saved after W. With it reqs are unchanged.
    craft_deploy_3 SET(false); MARK; client PV(save). Non-vacuity: the client's D saved, N, Dsky false. Without the fix
        the host's D is unsaved after W.
    craft_deploy_4 SET(true); client PV(erase). Non-vacuity: the client's D unsaved. Without the fix the host's D is
        saved after W.
    craft_deploy_5 SET(false); client shared_cmd craft_deployment {STR_SKYRANGER, saved, [[1, 2, 0, 3]]}, baseId -1.
        Without the fix: fails +1, lastFail "unknown command: craft_deployment" within W (cleanup: ONE close_screens on
        the client). With it: both D saved [[1, 2, 0, 3]] within W, fails unchanged 1 s later; negative control
        STR_NO_SUCH_CRAFT: fails +1, "rejected", D unchanged, ONE close_screens.
    craft_deploy_6 (guard, last in the SHARED boot) js.finish(): world equality, the replica's zero disk.
  SEPARATE boot (labels 49505 / 49506, lobby "47958"; bases HostBase / ClientBase, players HostPlayer / ClientPlayer):
    craft_deploy_separate: each player's deployment for one craft type is its own. PR = base_screen_op craft_deployment
    {player: ClientPlayer} on the host (the host's stored ClientPlayer profile, read from its saved form); L(d) = [saved,
    positions]; Dsky[gc][base] = that base's Skyranger's customDeployment on gc; MARKS = deploy_mark on both Skyrangers on
    both machines, then Dsky true everywhere (guard). Each step waits <= W for all its cells, then checks each:
      1 MARKS; client PV(save). Non-vacuity: the client's D saved, N positions at once (P1 = its positions). PR ==
        L(client's D); the host's D unsaved; Dsky[*][ClientBase] false and Dsky[*][HostBase] true on both.
      2 client shared_cmd craft_deployment C = P1 reversed, facing (3i + 1) % 8: L(client's D) == L(PR) == [true, C];
        the host's D unsaved.
      3 MARKS; host PV(save). Non-vacuity: the host's D saved, N positions at once. Dsky[*][HostBase] false and
        Dsky[*][ClientBase] true on both; L(client's D) == L(PR) == [true, C].
      4 host shared_cmd craft_deployment H = P1, facing (2i + 3) % 8: L(host's D) == [true, H]; 1 s later
        L(client's D) == L(PR) == [true, C].
      5 the host saves, both machines leave to the main menu, the host loads the save and the client rejoins (lobby
        "47959"): L(host's D) == [true, H], L(client's D) == L(PR) == [true, C]; the client's failCount unchanged
        since the row began.
      6 deploy_unmark on the client's Skyranger on both machines (the mark is no real crew deployment, so a battle
        cannot place a crew by it), Dsky[*][ClientBase] false (guard); the client's Skyranger lands at a new site beside
        ClientBase and both machines reach the battle: on each machine the client's soldiers, by unit id, stand at C's
        first positions plus one common offset and face C's facings.
A row whose main cell (the one that fails without the fix) fails evaluates no later cell. EVIDENCE line per row before
its verdict; a failed row prints ONE CAPTURE line (both machines' D, stacks, pedia_state, shared_stats,
shared_resync_stats); a boot miss fails its rows "boot". Every row runs after a failure. ONE run; exit 0 iff everything
passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import separate_campaign_fixture as sfx  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
import test_shared_base_equip as sbe  # noqa: E402  (main-guarded: X, Row, setup, boot_miss, q / stack / wait_until / short)
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402
from test_inventory_held import read_key  # noqa: E402  (main-guarded)

TAG_SHARED, PORTS_SHARED = "craft_deployment_shared", (49503, 49504, 47957)
TAG_SEPARATE, LABELS_SEPARATE, LOBBY_SEPARATE = "craft_deployment_separate", (49505, 49506), "47958"
HB, CB, SKYR, GEO = "HostBase", "ClientBase", "STR_SKYRANGER", "GeoscapeState"
BS, SFN, BRF, AMS = "BattlescapeState", "StatsForNerdsState", "BriefingState", "AbortMissionState"
W, POLL, STEP, SETTLE, CONV, N = 6.0, 0.25, 2.0, 0.3, 30.0, 14  # N = the Skyranger's 14 stand-in soldiers
RAW, UNKNOWN, NO_SUCH = [[1, 2, 0, 3]], "unknown command: craft_deployment", "STR_NO_SUCH_CRAFT"
ROWS_SHARED, ROWS_SEPARATE = ["craft_deploy_%d" % n for n in range(7)], ["craft_deploy_separate"]
CP, SEP_SAVE, SEP_RESUME = "ClientPlayer", "craft_deployment_separate.sav", 47959  # session.new_campaign's client name
ORDER = ROWS_SHARED + ROWS_SEPARATE
q, stack, wait_until, short = sbe.q, sbe.stack, sbe.wait_until, sbe.short


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


def timed(pred, timeout=W):
    t0 = time.time()
    v = wait_until(pred, timeout, POLL)
    return bool(v), round(time.time() - t0, 2)


def is_dead(s):  # sbe.stack's reply for a machine whose socket is gone
    return any(str(e).startswith("<get_state") for e in s)


# ---- PV: the Ufopaedia craft preview drive (measured values; test_client_research's pd_* shapes) ---------------------
def pd(gc):
    return q(gc, {"cmd": "pedia_state"})


def act(gc, obj):
    time.sleep(SETTLE)  # a key or click injected right after a state opens is lost without it
    return q(gc, obj)


def caption(gc):
    return [w.get("text") for w in q(gc, {"cmd": "list_widgets"}).get("widgets") or [] if w.get("visible")
            and "TextButton" in str(w.get("type")) and str(w.get("text")).startswith("Preview")]


def pv(gc, keys, erase=False):
    """PV(gc, erase) step by step, on_geoscape .. geoscape_back -> (the first missed step or None, {step: probe})"""
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
    m = (miss("on_geoscape", stack(gc) == [GEO], stack(gc))
         or miss("pedia_open", act(gc, key).get("ok") and kind("start"), pd(gc).get("kind")))
    if m:
        return m, ev
    sec = act(gc, {"cmd": "click_widget", "match": "X-COM CRAFT"})
    kind("select")
    p = pd(gc)
    m = (miss("craft_section", sec.get("ok") and p.get("kind") == "select" and "SKYRANGER" in (p.get("rows") or []),
              [sec.get("text"), p.get("rows")])
         or miss("skyranger_article", row(p, sec, "SKYRANGER") and pd(gc).get("article") == SKYR, pd(gc).get("article"))
         or miss("info_screen", act(gc, key).get("ok") and kind("nerds") and len(caption(gc)) == 1, caption(gc))
         or miss("preview_open", act(gc, {"cmd": "click_widget", "match": "preview"}).get("ok") and on(BRF), stack(gc)))
    if m:
        return m, ev
    cb, dis = q(gc, {"cmd": "close_briefing"}), 0
    while not on(BS) and dis < 3:  # dismiss only a top other than BattlescapeState that stays 2 s
        dis += 1
        q(gc, {"cmd": "dismiss_popup"})
    pre = q(gc, {"cmd": "battle_state"}).get("isPreview")
    m = (miss("preview_battle", cb.get("ok") and stack(gc)[-1:] == [BS] and pre is True, [stack(gc), pre, dis])
         or miss("abort_box", act(gc, {"cmd": "battle_action", "action": "abort"}).get("ok") and on(AMS), stack(gc))
         or (erase and miss("ctrl_latched", act(gc, {"cmd": "inject_input", "kind": "modstate", "mod": "ctrl"})
                            .get("modState") == "ctrl", "ctrl")))
    if m:
        return m, ev
    o = act(gc, {"cmd": "click_widget", "match": "ok"})
    back = on(BS)
    if erase:  # clear the latch once the click is consumed (a cleared latch pushes no key)
        q(gc, {"cmd": "inject_input", "kind": "modstate", "mod": "none"})
    if miss("ok_back", o.get("text") == "OK" and back, [o.get("text"), stack(gc)]):
        return "ok_back", ev
    act(gc, {"cmd": "battle_action", "action": "end_turn_button"})
    done, dis = (lambda: stack(gc)[-1:] == [SFN] and q(gc, {"cmd": "world_state"}).get("has_battle") is False), 0
    while not wait_until(done, 1.0, 0.05) and dis < 3:
        dis += 1
        if stack(gc)[-1:] not in ([BS], [SFN]):  # dismiss only a top other than the preview / the INFO screen that stays 1 s
            q(gc, {"cmd": "dismiss_popup"})
    ev["info_back caption"] = c11 = caption(gc)
    if miss("info_back", done() and len(c11) == 1, [stack(gc), dis]):
        return "info_back", ev
    q(gc, {"cmd": "close_screens"})
    return miss("geoscape_back", wait_until(lambda: stack(gc) == [GEO], STEP, 0.05), stack(gc)), ev
# ----------------------------------------------------------------------------------------------------------------------------------------


def leave(gc):
    """a stopped row's screens: an open preview is ended through its own buttons (never close_screens over it)"""
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
    """SET(want): every row starts from the same state with or without the fix (the craft deployment is not in the
    checksum, so no automatic re-copy repairs it)"""
    ev = r.ev["SET(%s)" % want] = {}
    if D(x.host).get("saved") is not want:
        m, ev["host PV"] = pv(x.host, x.keys["host"], erase=not want)
        if not r.cell(f"guard: SET host preview drive {m}", m is None, ev["host PV"]):
            return False
    if not eq(x):
        ev["COPY"] = cp = copy(x)
        if not r.cell("guard: SET COPY (both [GeoscapeState] and EQ within 30 s)", cp["ok"], cp):
            return False
    ev["reset"] = q(x.client, {"cmd": "shared_reset_resync_stats"}).get("ok")
    ev["D"] = d = both(x)
    return r.cell(f"guard: SET D saved == {want} on both, EQ", ev["reset"] is True and same(d["host"], d["client"])
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


def save_row(x, r, presser, other, main_cell):
    """craft_deploy_1 (host) / craft_deploy_3 (client): SET(false); MARK; the presser's PV(save)."""
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
            and r.cell(main_cell, e[other.name].get("saved") is True, {other.name + " D after W": e[other.name]})):
        return
    r.cell(f"the {other.name}'s D != the {presser.name}'s or its Dsky not false within W", got, e)
    r.cell("the client asked for a world re-copy (reqs changed)", r.ev["reqs"][0] == r.ev["reqs"][1], r.ev["reqs"])
    r.cell("the client's failCount changed", r.ev["fails"][0] == r.ev["fails"][1], r.ev["fails"])


def delete_row(x, r, presser, other, main_cell):
    """craft_deploy_2 (host) / craft_deploy_4 (client): SET(true); the presser's PV(erase) (Ctrl held on OK)."""
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
            and r.cell(main_cell, got and r.ev["end"][other.name].get("saved") is False,
                       {other.name + " D after W": r.ev["end"][other.name]})):
        return
    r.cell("the client asked for a world re-copy (reqs changed)", r.ev["reqs"][0] == r.ev["reqs"][1], r.ev["reqs"])


def answers(x):
    """the client's shared_ok + shared_fail count: it rises once the host has answered the client's shared_cmd"""
    r = q(x.client, {"cmd": "shared_stats"})
    return (r.get("okCount") or 0) + (r.get("failCount") or 0)


def raw(x, craft_type):
    """the client's shared_cmd craft_deployment; the host's answer (W); until the client's failCount rises or both D hold RAW (W);
    the box closed"""
    f0, a0, t0, out = fails(x)[0], answers(x), time.time(), {}
    out["shared_cmd"] = q(x.client, {"cmd": "shared_cmd", "jcmd": "craft_deployment", "baseId": -1,
                                     "payload": {"craftType": craft_type, "saved": True, "positions": RAW}})
    # the negative control's D already holds RAW (the first command's, applied with the fix), so settled() reads only
    # after the host's answer
    out["answered s"] = round(time.time() - t0, 2) if wait_until(lambda: answers(x) > a0, W, POLL) else None

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


def row_preview_hidden(x, r):
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
        if r.cell(f"guard: {g.name} open_screen craft_soldiers {HB} {x.sky}", e["open_screen"].get("ok") is True and e["stack"] == [GEO], e):
            r.cell(f"the {g.name}'s craft soldier screen shows its per-craft Preview (nothing carries that save)",
                   e["Preview buttons"] == [{"text": "Preview", "visible": False}], e["Preview buttons"])
        r.cell(f"the {g.name}'s D saved at boot", e["D"].get("saved") is False and e["D"].get("positions") == [], e["D"])


def row_raw_command(x, r):
    if not set_(r, x, False):
        return r.evidence()
    r.ev["raw"] = a = raw(x, SKYR)
    ref = a.get("refused [s, lastFail]")
    if not ref and "applied s" in a:  # with the fix: the settle, then the negative control
        time.sleep(1.0)
        r.ev["fails 1 s after"] = fails(x)[0]
        r.ev["negative control"] = raw(x, NO_SUCH)
    r.evidence()
    if not (r.cell("guard: shared_cmd sent", a["shared_cmd"].get("ok") is True, a["shared_cmd"])
            and r.cell("the host has no carrier for a craft deployment", not (ref and ref[1] == UNKNOWN), a)
            and r.cell(f"both D saved {RAW} within W", not ref and "applied s" in a, a)):
        return
    r.cell("the client's failCount changed after a 1 s settle", r.ev["fails 1 s after"] == a["fails before"],
           [a["fails before"], r.ev["fails 1 s after"]])
    n = r.ev["negative control"]
    nref = n.get("refused [s, lastFail]")
    r.cell(f"negative control: {NO_SUCH} not refused 'rejected' within W, or a D changed",
           nref is not None and nref[1] == "rejected" and n["D"] == a["D"], n)


def row_world_equal(x, r):
    r.ev.update({"D": both(x), "world_diff now": shared_fixture.world_diff(x.host, x.client),
                 "client save files now": session.save_files(x.js.client_dir)})
    r.evidence()
    try:
        x.js.finish()
    except AssertionError as e:
        r.cell("js.finish", False, short(e, 1500))


def L(d):
    return [d.get("saved"), d.get("positions")]


def pr(x):
    r = q(x.host, {"cmd": "base_screen_op", "op": "craft_deployment", "craft_type": SKYR, "player": CP})
    return {k: r.get(k) for k in ("saved", "positions", "playerFound", "error")}


def snap(x):
    """both D, PR and Dsky in one read"""
    d = both(x)
    return {"D": d, "PR": pr(x), "Dsky": {n: {b: dsky(e, sid) for b, sid in x.skies.items()} for n, e in d.items()}}


def settle(r, x, step, ok, timeout=W):
    """waits <= timeout until ok(snap); the last snap is the step's end (EVIDENCE)"""
    t0, last = time.time(), {}

    def pred():
        last["s"] = s = snap(x)
        return ok(s)
    got = wait_until(pred, timeout, POLL)
    r.ev[step + " end"] = dict(last["s"], s=round(time.time() - t0, 2), all=bool(got))
    return last["s"]


def marks(r, x, step):
    m = {g.name: {b: q(g, {"cmd": "base_screen_op", "op": "deploy_mark", "base": b, "craft_id": sid, "craft_type": SKYR})
                  .get("customDeployment") for b, sid in x.skies.items()} for g in (x.host, x.client)}
    s = snap(x)
    r.ev[step + " MARKS"] = [m, s["Dsky"]]
    return r.cell(f"guard: {step} MARKS -> Dsky true on both machines", all(v is True for e in s["Dsky"].values()
                  for v in e.values()), [m, s["Dsky"]])


def raw_layout(gc, positions):
    return q(gc, {"cmd": "shared_cmd", "jcmd": "craft_deployment", "baseId": -1,
                  "payload": {"craftType": SKYR, "saved": True, "positions": positions}})


def placed(gc, layout):
    """the client's soldiers in gc's battle, by unit id: [x, y, z, facing] and the offsets to layout's positions"""
    us = sorted((u for u in session.battle_state(gc).get("units") or [] if u.get("isPlayerSoldier") and u.get("coop") == 1),
                key=lambda u: u.get("id"))
    at = [[u.get("x"), u.get("y"), u.get("z"), u.get("direction")] for u in us]
    offs = [[a[k] - p[k] for k in range(3)] for a, p in zip(at, layout)]
    return {"units": at, "offsets": offs}


def row_separate_own(x, r):
    h, c = x.host, x.client
    d0 = both(x)
    if not (r.cell("guard: D unsaved on both at boot (SEPARATE)", all(e.get("saved") is False for e in d0.values()), d0)
            and r.cell("guard: a Skyranger at HostBase and at ClientBase", all(v is not None for v in x.skies.values()), x.skies)):
        return r.evidence()
    f0 = fails(x)[0]
    # 1 the client saves its own from the preview
    if not marks(r, x, "1"):
        return r.evidence()
    m, r.ev["1 PV client"] = pv(c, x.keys["client"])
    r.ev["1 client D at once"] = me = D(c)
    if not (r.cell("preview drive %s (client)" % m, m is None, r.ev["1 PV client"])
            and r.cell(f"non-vacuity: the client's D saved, {N} positions at once", me.get("saved") is True
                       and len(me.get("positions") or []) == N, me)):
        return r.evidence()
    p1 = me["positions"]
    s = settle(r, x, "1", lambda s: L(s["PR"]) == L(s["D"]["client"]) and s["D"]["host"].get("saved") is False
               and all(s["Dsky"][n] == {HB: True, CB: False} for n in ("host", "client")))
    r.cell("the host keeps no copy of the client's saved deployment (PR != the client's D)",
           L(s["PR"]) == L(s["D"]["client"]), [s["PR"], s["D"]["client"]])
    r.cell("the client's save changed the host's own D", s["D"]["host"].get("saved") is False, s["D"]["host"])
    for n in ("host", "client"):
        r.cell(f"the client's save left its own Skyranger's deployment on the {n}", s["Dsky"][n][CB] is False, s["Dsky"])
        r.cell(f"the client's save cleared the host's Skyranger's deployment on the {n}", s["Dsky"][n][HB] is True, s["Dsky"])
    # 2 the client's own layout, set apart from every other one
    cl = [[p[0], p[1], p[2], (3 * i + 1) % 8] for i, p in enumerate(reversed(p1))]
    hl = [[p[0], p[1], p[2], (2 * i + 3) % 8] for i, p in enumerate(p1)]
    r.ev.update({"P1": p1, "C": cl, "H": hl})
    if not r.cell("guard: C, H and P1 differ", len({str(cl), str(hl), str(p1)}) == 3, [cl, hl]):
        return r.evidence()
    r.ev["2 shared_cmd"] = raw_layout(c, cl)
    s = settle(r, x, "2", lambda s: L(s["D"]["client"]) == L(s["PR"]) == [True, cl] and s["D"]["host"].get("saved") is False)
    r.cell("the client's D is not C", L(s["D"]["client"]) == [True, cl], s["D"]["client"])
    r.cell("PR is not C", L(s["PR"]) == [True, cl], s["PR"])
    r.cell("the client's layout changed the host's own D", s["D"]["host"].get("saved") is False, s["D"]["host"])
    # 3 the host saves its own from the preview
    if not marks(r, x, "3"):
        return r.evidence()
    m, r.ev["3 PV host"] = pv(h, x.keys["host"])
    r.ev["3 host D at once"] = mh = D(h)
    if not (r.cell("preview drive %s (host)" % m, m is None, r.ev["3 PV host"])
            and r.cell(f"non-vacuity: the host's D saved, {N} positions at once", mh.get("saved") is True
                       and len(mh.get("positions") or []) == N, mh)):
        return r.evidence()
    s = settle(r, x, "3", lambda s: all(s["Dsky"][n] == {HB: False, CB: True} for n in ("host", "client"))
               and L(s["D"]["client"]) == L(s["PR"]) == [True, cl])
    for n in ("host", "client"):
        r.cell(f"the host's save left its own Skyranger's deployment on the {n}", s["Dsky"][n][HB] is False, s["Dsky"])
        r.cell(f"the host's save cleared the client's Skyranger's deployment on the {n}", s["Dsky"][n][CB] is True, s["Dsky"])
    r.cell("the host's save replaced the client's D", L(s["D"]["client"]) == [True, cl], s["D"]["client"])
    r.cell("the host's save replaced PR", L(s["PR"]) == [True, cl], s["PR"])
    # 4 the host's own layout, set apart from the client's
    r.ev["4 shared_cmd"] = raw_layout(h, hl)
    settle(r, x, "4", lambda s: L(s["D"]["host"]) == [True, hl])
    time.sleep(1.0)
    r.ev["4 end 1 s later"] = s = snap(x)
    r.cell("the host's D is not H", L(s["D"]["host"]) == [True, hl], s["D"]["host"])
    r.cell("the host's layout replaced the client's D", L(s["D"]["client"]) == [True, cl], s["D"]["client"])
    r.cell("the host's layout replaced PR", L(s["PR"]) == [True, cl], s["PR"])
    # 5 the host's save file holds both
    session.save_and_resume(h, c, SEP_SAVE, SEP_RESUME)
    ok = wait_until(lambda: stack(h) == [GEO] and stack(c) == [GEO], CONV, POLL)
    r.ev["5 after the reload"] = s = snap(x)
    r.ev["5 fails"] = [f0, fails(x)]
    if not r.cell("guard: both machines back on the geoscape after the reload", ok, [stack(h), stack(c)]):
        return r.evidence()
    r.cell("after the reload the host's D is not H", L(s["D"]["host"]) == [True, hl], s["D"]["host"])
    r.cell("after the reload the client's D is not C", L(s["D"]["client"]) == [True, cl], s["D"]["client"])
    r.cell("after the reload PR is not C", L(s["PR"]) == [True, cl], s["PR"])
    r.cell("the client's failCount changed", r.ev["5 fails"][1][0] == f0, r.ev["5 fails"])
    # 6 a battle with the client's Skyranger places the client's soldiers by C
    r.ev["6 unmark"] = [q(g, {"cmd": "base_screen_op", "op": "deploy_unmark", "base": CB, "craft_id": x.skies[CB],
                              "craft_type": SKYR}).get("customDeployment") for g in (h, c)]
    s = snap(x)
    if not r.cell("guard: 6 deploy_unmark -> Dsky[*][ClientBase] false", all(s["Dsky"][n][CB] is False for n in ("host", "client")),
                  [r.ev["6 unmark"], s["Dsky"]]):
        return r.evidence()
    x.battle = True  # the row ends in the battle: no screen cleanup
    geo.slow_clock(h, c)
    sfx.fly_to_new_site(h, c, c)
    c.ok({"cmd": "confirm_landing"})
    inb = all(wait_until(lambda gc=gc: session.battle_state(gc).get("inBattle"), 180, 1.0) for gc in (h, c))
    tac = inb and session.drive_both_to_tactical(h, c)
    r.ev["6 battle"] = got = {gc.name: placed(gc, cl) for gc in (h, c)} if tac else None
    r.evidence()
    if not r.cell("guard: both machines in the battle of the client's Skyranger", tac, [inb, session.states(h), session.states(c)]):
        return
    for n, e in got.items():
        if r.cell(f"guard: two or more of the client's soldiers in the battle on the {n}", len(e["units"]) >= 2, e):
            r.cell(f"the client's soldiers do not stand at C's positions (one offset) facing C's facings on the {n}",
                   len({str(o) for o in e["offsets"]}) == 1 and [u[3] for u in e["units"]] == [p[3] for p in cl[:len(e["units"])]], e)


class Row(sbe.Row):
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
            r.cell(f"guard: {rid} exception", False, short(e))
        for g in (x.host, x.client):  # a stopped row leaves no screen behind (an open preview ends through its own buttons)
            before = stack(g)
            if not is_dead(before) and before != [GEO] and not getattr(x, "battle", False):
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


def boot_shared(results, walls):
    t0, js, x = time.time(), None, None
    try:
        try:
            js = shared_fixture.bring_up(TAG_SHARED, PORTS_SHARED)
            x = sbe.X(js.host, js.client, js)
            sbe.setup(x)  # option OFF on both, seats differ, the SKYRANGER, the HostBase index (raises on a miss)
            x.keys = keys(x)
            walls["boot " + TAG_SHARED] = round(time.time() - t0, 1)
        except Exception as e:  # a boot miss fails every row of this boot "boot" with ONE CAPTURE line
            return sbe.boot_miss(TAG_SHARED, e, ROWS_SHARED, results, x)
        run_rows(x, (
            ("craft_deploy_0", row_preview_hidden),
            ("craft_deploy_1", lambda x, r: save_row(
                x, r, x.host, x.client, "the host's saved craft deployment never reached the client")),
            ("craft_deploy_2", lambda x, r: delete_row(
                x, r, x.host, x.client, "the host's deleted craft deployment stayed on the client")),
            ("craft_deploy_3", lambda x, r: save_row(
                x, r, x.client, x.host, "the client's saved craft deployment never reached the host")),
            ("craft_deploy_4", lambda x, r: delete_row(
                x, r, x.client, x.host, "the client's deleted craft deployment stayed on the client")),
            ("craft_deploy_5", row_raw_command), ("craft_deploy_6", row_world_equal)), results, walls)
    finally:
        if js is not None:
            down(TAG_SHARED, results, js.shutdown)


def boot_separate(results, walls):
    t0 = time.time()
    h = GameClient("host", LABELS_SEPARATE[0], make_user_dir(TAG_SEPARATE + "_host"))
    c = GameClient("client", LABELS_SEPARATE[1], make_user_dir(TAG_SEPARATE + "_client"))
    x = sbe.X(h, c, base=CB)
    try:
        try:
            h.spawn(), c.spawn(), h.connect(), c.connect()
            session.new_campaign(h, c, port=LOBBY_SEPARATE, campaign_mode="coop")
            geo.wait_both_ready(h, c)
            x.seats = {g.name: q(g, {"cmd": "get_coop"}).get("localSeat") for g in (h, c)}
            x.keys = keys(x)
            x.skies = {b["name"]: next((k["id"] for k in b["crafts"] if k["type"] == SKYR), None)
                       for b in sfx.geo(h)["bases"] if b["name"] in (HB, CB)}
            walls["boot " + TAG_SEPARATE] = round(time.time() - t0, 1)
        except Exception as e:  # a boot miss fails craft_deploy_separate "boot" with ONE CAPTURE line
            return sbe.boot_miss(TAG_SEPARATE, e, ROWS_SEPARATE, results, x)
        run_rows(x, (("craft_deploy_separate", row_separate_own),), results, walls)
    finally:
        down(TAG_SEPARATE, results, lambda: shutdown_clients(h, c))


def main():
    t0, results, walls = time.time(), {}, {}
    boot_shared(results, walls)
    boot_separate(results, walls)
    failed = [rid for rid in ORDER if not results.get(rid)]
    downs = sorted(k for k, v in results.items() if k.startswith("shutdown") and not v)
    print(f"\ntest_shared_craft_deployment: {len(ORDER) - len(failed)}/{len(ORDER)} passed (fail={failed + downs}) "
          f"walls {json.dumps(walls)} in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed or downs else 0


if __name__ == "__main__":
    sys.exit(main())
