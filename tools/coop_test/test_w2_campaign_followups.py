"""W2-P7 S-C-C - test_w2_campaign_followups.py: in a SHARED campaign the second player sees every after-battle screen
the host sees (promotions, medals, late medals, cannot-reequip), and every co-op campaign debrief and follow-up screen
names the other player's soldiers `[Player] Name` (docs rewrite/prompts/w2p7_sc_design.md section 3.4, AMENDMENT P7-6
section 4.4, the P7-6 C re-pin at 2e177ff39 section 4 rows F1, F4, F2/F3, PR-C1..PR-C10; owner D154, D177 (a); MR5,
MR11).

Before S-C-C: the client's campaign OK goes straight to its GeoscapeState (S-C-A's `coopCampaignClientSharedLeave`);
the follow-up screens show on the host only (DebriefingState :905-921 run on the host's real debriefing).

Boot 1 (port 47208) - rows F1 and F4. shared_fixture.bring_up; T0-S6 (iv)'s cannot-reequip staging (CONSTANTS
rewrite/w2p7sc-task0/t0/CONSTANTS.md, TASK 0 t_reequip.py): the host `sell`s the base stock of every Skyranger loadout
type to 0 before the battle; bring_up_shared_mixed_battle(js, {0: 0, 1: 1}, pre_landing = host set_seed SEED_S); the
host-owned soldier squad[0] stripped on both machines (battle_strip_unit, client first); host set_option battleAutoEnd
true; the participant's-own-kill (the P7-6 TASK 0 ruling) = test_w2_battle_end_separate.guest_kill's recipe for the
CLIENT-owned soldier squad[1] at SHOT_SEED_F1 -> KEEP dead, murdererId == the shooter -> the autoEnd ending (T0-6 (ii))
-> the host's DebriefingState; the shooter is promoted (pre-cell: rankString RANK_F1, kills >= 1).
Boot 2 (port 47209) - row F2/F3, Coop_Medal_Test on both machines (shared_fixture.bring_up mods): the same battle; host
kill_unit_real {unit: squad[0]} (the chain settled, F4665), then kill_unit_real {faction: 1} -> the autoEnd ending;
pre-cell: squad[0] dead and squad[1] awarded STR_COOP_MEDAL_TEST on the host.

Each boot then runs ONE procedure: the client's display-only debriefing (both debrief_state snapshots), its in-place
adoption, the client's OK (its stack right after the OK, then every FOLLOWUPS screen read with followup_state while on
top and dismissed - their OK is a plain popState, F5628), then the host's OK + drain (its follow-ups read the same
way). The rows' cells are then checked in order on what was recorded; a failed cell ends its row ("not reached").
  F1   (1) both debriefings equal after PR-10 stripping, the client's display-only; (2) the client adopted (worldAdopted
       1); (3) the client's chain == CHAIN_F1 == its stack after the OK == the host's drained follow-ups [RED];
       (4) the client's PromotionsState rows == [[shooter, RANK_TR_F1, BASE]]; (5) both debriefings' page-2 names: the
       other seat's soldier `[<seat name>] `, own plain; (6) the host's PromotionsState rows == [["[ClientPlayer]
       <shooter>", RANK_TR_F1, BASE]], the two machines' rows equal after PR-10 stripping (P6-8); both on the
       geoscape, the client zero-disk, no LoadGameState pushed, host fatalVote.armed 0.
  F4   (1) the host showed CannotReequipState with REEQUIP_ROWS_F4 (the fixture; a miss = FIXTURE-STOP); (2) the client
       showed a CannotReequipState [RED]; (3) its rows (item, qty, craft) == the host's; (4) over the adopted base
       (PR-C2: battleEnd.page3 {live 1, baseIndex 0} - D1's coopDebriefPage3Live set the debriefing's _base).
  F2/F3 (1), (2) as F1; (3) the client's chain == CHAIN_F23 == its stack == the host's drained follow-ups [RED];
       (4) CommendationState rows: the medal title MEDAL_TR, the client-owned survivor plain on the client and
       `[ClientPlayer] ` on the host, rows equal after stripping; (5) CommendationLateState lists the dead host soldier,
       `[HostPlayer] ` on the client and plain on the host, rows equal after stripping; (6) as F1 (6)'s tail.
The page-2 prefix cell sits after the chain cell (the prefix is S-C-C.2's product; its check runs on the snapshot taken
before the OKs), so the red fails on exactly the chain cells.

RED (commit S-C-C.1: the followup_state probe, the `chain` zero, these rows; product untouched): F1, F2/F3 fail on
exactly cell 3 and F4 on exactly cell 2 - the client's chain is empty, it shows no follow-up. GREEN (S-C-C.2): all pass.
Each boot prints ONE "EVIDENCE <boot>:" line, then "PASS <row>" / "FAIL <row>: <message>" per row.
WV-D95/D99/D100: ONE foreground run, no skip path; exit 0 only when every row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_campaign_followups.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import battle_state, event_state
import shared_fixture
import test_w2_battle_end_campaign as camp
import test_w2_battle_end_separate as b1
from test_w2_battle_end_campaign import stack, top, wait_until, record, strip_prefix, short

# ----- pins (sources in the comments) -----
SEED_S, MAP_FP_S, HOSTILES = camp.SEED_S, camp.MAP_FP_S, camp.HOSTILES   # CONSTANTS T0-6 (i)
SHOT_SEED_F1 = 2        # R1 (b) on the S-C-C.1 red build: seed 1 left KEEP alive; seed 2 killed it, murdererId == the shooter, 3/3 boots
RANK_F1, RANK_TR_F1 = "STR_SERGEANT", "Sergeant"   # the shooter's rank after the debriefing (4/4 red-build boots)
BASE = "HostBase"       # shared_fixture.bring_up's host_base: base 0, where the shared squad lives
LOADOUT_TYPES = ("STR_GRENADE", "STR_HC_AP_AMMO", "STR_HC_HE_AMMO", "STR_HEAVY_CANNON", "STR_PISTOL",
                 "STR_PISTOL_CLIP", "STR_RIFLE", "STR_RIFLE_CLIP")   # CONSTANTS T0-S6 (iv) (TASK 0 t_reequip.py)
REEQUIP_ROWS_F4 = [["Rifle", "1", "SKYRANGER-1"], ["Rifle Clip", "4", "SKYRANGER-1"],
                   ["Grenade", "1", "SKYRANGER-1"]]                  # the host's CannotReequipState rows, 4/4 red-build boots
CHAIN_F1 = ["PromotionsState", "CannotReequipState"]                 # re-pin F1 (2) = the host's drains, 4/4
CHAIN_F23 = ["CommendationLateState", "CommendationState"]           # re-pin F2/F3 = the host's drain (red-build capture)
MEDAL_TYPE, MEDAL_TR = "STR_COOP_MEDAL_TEST", "Coop Medal Test"      # Coop_Medal_Test (PR-20) and its en-US string
MEDAL_MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_Medal_Test")
SEAT_NAMES = ("HostPlayer", "ClientPlayer")   # session.new_campaign's defaults: seat 0 host, seat 1 client
PORTS = {"boot1": "47208", "boot2": "47209"}   # the re-pin section 4: C's SHARED block 47208-47210
FOLLOWUPS = b1.FOLLOWUPS
CLIENT_DEBRIEF_S, ADOPT_S, OK_S, DRAIN_S, DEBRIEF_S = 20, camp.ADOPT_S, camp.OK_S, camp.DRAIN_S, camp.DEBRIEF_S
WAIT_TOPS, LOADGAME_PUSH = camp.WAIT_TOPS, camp.LOADGAME_PUSH


def evidence(rid, obj):
    print(f"EVIDENCE {rid}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)


def clean(name):
    return (name or "").strip(". ")


def display(raw, owner, seat):
    """PR-C10's rule as the test expects it: `[<seat name>] raw` for another seat's soldier (999 -> seat 0)."""
    o = 0 if owner == 999 else owner
    return raw if o == seat else f"[{SEAT_NAMES[o]}] {raw}"


def expected_rows(rows, owners, seat):
    """Rows (col 0 prefix-stripped) as machine `seat` must show them: col 0 of every soldier row through display()."""
    return [[display(r[0], owners[r[0]], seat)] + r[1:] if r and r[0] in owners else list(r) for r in rows or []]


def stripped(rows):
    return [[strip_prefix(r[0])] + r[1:] if r else r for r in rows or []]


def owners_of(host, names):
    """{raw name: ownerPlayerId} from the host's soldier_record (bases, transfers, dead list)."""
    out = {}
    for n in names:
        recs = (host.cmd({"cmd": "soldier_record", "name": n}).get("records") or [])
        if recs:
            out[clean(n)] = recs[0].get("owner")
    return out


def base_items(gc):
    return dict(session._campaign_base0(gc).get("items") or {})


def soldier_units(host):
    return {u.get("soldierId"): u for u in battle_state(host).get("units", []) if u.get("faction") == 0}


# ===================== stages (pre-cell) =====================


def ending(host, client, ctx, m):
    """The autoEnd ending: close the host's NextTurnState until its DebriefingState; the host debriefing pins."""
    t0, closes = time.time(), []
    while time.time() - t0 < DEBRIEF_S and "DebriefingState" not in stack(host):
        if top(host) == "NextTurnState":
            closes.append(host.cmd({"cmd": "dismiss_popup"}).get("handled"))
        time.sleep(0.1)
    ctx["ending"] = {"secs": round(time.time() - t0, 2), "closes": closes, "hostStack": stack(host)}
    if "DebriefingState" not in stack(host):
        camp.capture("host debriefing", f"no host DebriefingState within {DEBRIEF_S}s ({ctx['ending']})", m)
    hdeb = host.cmd({"cmd": "debrief_state"})
    bad = [f"host debrief_state.{k}={hdeb.get(k)!r} (want {w!r})"
           for k, w in (("shown", True), ("onTop", True), ("displayOnly", False), ("title", "Aliens defeated"))
           if hdeb.get(k) != w]
    armed = (event_state(host).get("fatalVote") or {}).get("armed")
    if armed != 0:
        bad.append(f"host fatalVote.armed={armed!r} (want 0: no S-V vote, F4544)")
    if bad:
        camp.capture("host debriefing pin", "; ".join(bad), m)


def battle(js, ctx, m):
    """The SHARED battle on SEED_S, squad {0: 0, 1: 1}; the map pin. Returns (squad, {soldier id: unit id})."""
    try:
        _h, _c, squad = session.bring_up_shared_mixed_battle(js, {0: 0, 1: 1}, pre_landing=camp.seed_pin)
    except Exception as e:
        camp.capture("bring_up_shared_mixed_battle", short(e, 800), m)
    ctx["squad"] = squad
    fp = (battle_state(js.host).get("mapFingerprint"), battle_state(js.client).get("mapFingerprint"))
    if fp != (MAP_FP_S, MAP_FP_S):
        camp.capture("map pin", f"mapFingerprint (host, client) {fp} (want both {MAP_FP_S!r})", m)
    units = soldier_units(js.host)
    if any(units.get(s, {}).get("id") is None for s in squad):
        camp.capture("squad units", f"no battle unit for squad {squad}: {sorted(units)}", m)
    return squad, {s: units[s]["id"] for s in squad}


def stage_boot1(js, ctx):
    """F1 + F4: T0-S6 (iv)'s sells and strip, the client-owned soldier's own kill at SHOT_SEED_F1, the autoEnd ending."""
    host, client = js.host, js.client
    m = (host, client)
    stock0 = base_items(host)
    ctx["sells"] = [(t, stock0[t], host.cmd({"cmd": "sell", "item": t, "count": stock0[t]}).get("ok"))
                    for t in LOADOUT_TYPES if stock0.get(t, 0) > 0]
    ok, secs = wait_until(lambda: all(base_items(gc).get(t, 0) == 0 for gc in m for t in LOADOUT_TYPES), 30)
    if not ok:
        camp.capture("F4 sells", f"loadout stock not 0 on both after {secs}s: {ctx['sells']}", m)
    squad, uid = battle(js, ctx, m)
    rh, rc = b1.both(host, client, {"cmd": "battle_strip_unit", "unit": uid[squad[0]]})
    ctx["strip"] = {"host": rh.get("deleted"), "client": rc.get("deleted")}
    # the same ids on both machines; the order may differ per machine (measured: host [17, 1, 3, 31], client [1, 3, 17, 31])
    if not (rh.get("ok") and rc.get("ok") and rh.get("deleted") and sorted(rh["deleted"]) == sorted(rc.get("deleted"))):
        camp.capture("F4 strip", f"battle_strip_unit answered host {rh} client {rc}", m)
    ae = host.cmd({"cmd": "set_option", "name": "battleAutoEnd", "value": True})
    if ae.get("value") is not True:
        camp.capture("battleAutoEnd", f"host set_option battleAutoEnd answered {ae}", m)
    ctx["loadGamePushes0"] = camp.log_count(client, LOADGAME_PUSH)
    b1.guest_kill(host, client, uid[squad[1]], ctx, shot_seed=SHOT_SEED_F1)   # FixtureMiss after a CAPTURE line
    ending(host, client, ctx, m)
    shooter = b1.soldier_rec(host, sid=squad[1])
    ctx["shooter"] = {k: shooter.get(k) for k in ("id", "name", "owner", "rank", "rankString", "kills")}
    if shooter.get("rankString") != RANK_F1 or (shooter.get("kills") or 0) < 1:
        camp.capture("F1 promotion", f"the shooter after the debriefing {ctx['shooter']} (want {RANK_F1}, kills >= 1)", m)
    ctx["owners"] = owners_of(host, [b1.soldier_rec(host, sid=s).get("name") for s in squad])


def stage_boot2(js, ctx):
    """F2/F3: the host-owned soldier killed (host-origin, settled), then every hostile -> the autoEnd ending."""
    host, client = js.host, js.client
    m = (host, client)
    squad, uid = battle(js, ctx, m)
    k = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": uid[squad[0]]})
    settled = b1.chain_settled(host, client, stable=1.0, timeout=45)
    ctx["soldierKill"] = {"killed": k.get("killed"), "settled": settled[:2]}
    if not k.get("ok") or b1.unit(host, uid[squad[0]]).get("status") != b1.STATUS_DEAD or not settled[0]:
        camp.capture("F3 soldier kill", f"kill_unit_real {uid[squad[0]]} -> {ctx['soldierKill']}", m)
    ae = host.cmd({"cmd": "set_option", "name": "battleAutoEnd", "value": True})
    if ae.get("value") is not True:
        camp.capture("battleAutoEnd", f"host set_option battleAutoEnd answered {ae}", m)
    ctx["loadGamePushes0"] = camp.log_count(client, LOADGAME_PUSH)
    k = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": 1})
    if not k.get("ok") or sorted(k.get("killed") or []) != HOSTILES:
        camp.capture("kill", f"kill_unit_real faction 1 answered {k} (want the 15 hostiles)", m)
    ending(host, client, ctx, m)
    dead, alive = b1.soldier_rec(host, sid=squad[0]), b1.soldier_rec(host, sid=squad[1])
    ctx["dead"], ctx["survivor"] = dead.get("name"), alive.get("name")
    comms = [c.get("type") for c in ((alive.get("diary") or {}).get("commendations") or [])]
    if not dead.get("dead") or MEDAL_TYPE not in comms:
        camp.capture("F2/F3 precondition", f"squad[0] dead={dead.get('dead')!r}, squad[1] commendations {comms} "
                     f"(want dead and {MEDAL_TYPE}: is Coop_Medal_Test loaded on both?)", m)
    ctx["owners"] = owners_of(host, [ctx["dead"], ctx["survivor"]])


# ===================== the procedure (both OKs, every follow-up read) =====================


def walk(gc, timeout, followups_only):
    """Dismiss this machine's after-battle screens; each FOLLOWUPS top read with followup_state while isTop (F5627)
    before its dismiss_popup (= its OK, F5628). followups_only: stop at any other top (the client after its OK);
    else CoopState -> coop_dialog_back, other tops dismiss_popup, WAIT_TOPS left alone (the host's drain).
    Returns (reached GeoscapeState, screens, {class: rows})."""
    screens, rows, t0 = [], {}, time.time()
    while time.time() - t0 < timeout:
        t = top(gc) or ""
        if t == "GeoscapeState" or (followups_only and t not in FOLLOWUPS):
            break
        if any(n in t for n in WAIT_TOPS):
            time.sleep(0.25)
            continue
        ent = {"t": round(time.time() - t0, 2), "top": t}
        if t in FOLLOWUPS:
            fu = gc.cmd({"cmd": "followup_state"})
            ent["fu"] = {k: fu.get(k) for k in ("state", "isTop", "rows")}
            if fu.get("isTop") and fu.get("state") == t:
                rows.setdefault(t, fu.get("rows"))
        r = gc.cmd({"cmd": "coop_dialog_back"}) if "CoopState" in t else gc.cmd({"cmd": "dismiss_popup"})
        ent["resp"] = r.get("handled") or r.get("error") or r.get("ok")
        screens.append(ent)
        time.sleep(0.25)
    return top(gc) == "GeoscapeState", screens, rows


def procedure(js, ctx, shared=True):
    host, client = js.host, js.client
    ok, secs = wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                   and d.get("displayOnly") is True)(client.cmd({"cmd": "debrief_state"})),
                          CLIENT_DEBRIEF_S)
    ctx["deb"] = {"ok": ok, "secs": secs, "host": host.cmd({"cmd": "debrief_state"}),
                  "client": client.cmd({"cmd": "debrief_state"})}
    if shared:
        ok, secs = wait_until(lambda: record(client).get("worldAdopted") == 1, ADOPT_S)
        ctx["adopt"] = {"ok": ok, "secs": secs}
    c = ctx["client"] = {"press": camp.press_ok(client)}

    def shaped():
        st = stack(client)
        good = (st[:1] == ["GeoscapeState"] and all(s in FOLLOWUPS for s in st[1:])
                and not any(("CoopState" in s or "LoadGameState" in s) for s in st))
        if good:
            c["T"] = st[1:]
        return good
    c["shaped"] = wait_until(shaped, OK_S)[0] if c["press"]["pressed"] else False
    c["afterOk"] = stack(client)
    _r, c["screens"], c["rows"] = walk(client, OK_S, True)
    c["geoClean"] = wait_until(lambda: camp.geo_clean(client), OK_S)[0]
    c["stack"], c["record"] = stack(client), record(client)
    h = ctx["host"] = {"press": camp.press_ok(host)}
    h["reached"], h["screens"], h["rows"] = walk(host, DRAIN_S, False)
    h["stack"] = stack(host)
    try:
        session.assert_client_zero_disk(client.user_dir)
        ctx["zeroDisk"] = True
    except AssertionError as e:
        ctx["zeroDisk"] = str(e)
    ctx["loadGamePushes"] = camp.log_count(client, LOADGAME_PUSH) - ctx.get("loadGamePushes0", 0)
    ctx["fatalVoteArmed"] = (event_state(host).get("fatalVote") or {}).get("armed")


# ===================== cells (checked on the recorded procedure) =====================


def cell_debriefs(ctx):
    d = ctx["deb"]
    if not d["ok"]:
        return [f"the client never showed a display-only DebriefingState within {CLIENT_DEBRIEF_S}s (client "
                f"debrief_state shown={d['client'].get('shown')!r} displayOnly={d['client'].get('displayOnly')!r})"]
    hv, cv = camp.debrief_view(d["host"]), camp.debrief_view(d["client"])
    return [f"client debrief_state.{k}={cv.get(k)!r} != the host's {hv.get(k)!r}" for k in camp.DEBRIEF_FIELDS
            if cv.get(k) != hv.get(k)]


def cell_adopted(ctx):
    a = ctx["adopt"]
    return [] if a["ok"] else [f"client battleEnd.worldAdopted != 1 after {ADOPT_S}s"]


def cell_chain(ctx, pinned, shared, what):
    """The RED cell: the client's battleEnd.chain non-empty, == its stack right after the OK, == the host's drained
    follow-ups in push order (b1.host_followups) and == the pinned list."""
    c = ctx["client"]
    chain, seen = (c.get("record") or {}).get("chain"), c.get("T")
    want = b1.host_followups(ctx["host"]["screens"], shared=shared)
    c["chainCheck"] = {"chain": chain, "T": seen, "hostFollowups": want, "pinned": pinned}
    if not c["press"].get("pressed"):
        return [c["press"].get("note")]
    if not chain:
        return [f"the client's chain is empty: the client shows {what} (battleEnd.chain={chain!r}, its stack after "
                f"the OK {c['afterOk']}; want {pinned!r}, the host drained {want!r})"]
    return [f"client battleEnd.chain={chain!r} != {n} {v!r}" for n, v in
            (("its stack after the OK", seen), ("the host's drained follow-ups", want), ("the pinned", pinned))
            if chain != v]


def rows_cell(ctx, cls, owners, must=None):
    """`cls` rows on both machines: host rows == expected_rows(stripped host rows, seat 0), client rows ==
    expected_rows(stripped host rows, seat 1) (the prefix rule; P6-8 equality after stripping); `must(raw rows)`
    returns extra failures."""
    hr, cr = ctx["host"]["rows"].get(cls), ctx["client"]["rows"].get(cls)
    if hr is None or cr is None:
        return [f"{cls} rows not read on both machines (host {hr!r}, client {cr!r})"]
    base = stripped(hr)
    f = [] if must is None else must(base)
    for name, seat, got in (("host", 0, hr), ("client", 1, cr)):
        want = expected_rows(base, owners, seat)
        if got != want:
            f.append(f"{name} {cls} rows {got} != {want} (the [Player] prefix rule, PR-C10)")
    return f


def cell_page2(ctx, owners):
    f = []
    for name, seat in (("host", 0), ("client", 1)):
        got = [s.get("name") for s in (ctx["deb"][name].get("soldiers") or [])]
        want = [display(strip_prefix(n), owners.get(strip_prefix(n)), seat) if strip_prefix(n) in owners else n
                for n in got]
        if got != want or not got:
            f.append(f"{name} debriefing page-2 names {got} != {want} (other seat `[<seat name>] `, own plain)")
    return f


def cell_end(ctx):
    f = []
    if not ctx["client"]["geoClean"]:
        f.append(f"client not on a clean GeoscapeState after its follow-ups (stack {ctx['client']['stack']})")
    if not ctx["host"]["reached"]:
        f.append(f"host not on GeoscapeState within {DRAIN_S}s of its OK (stack {ctx['host']['stack']})")
    if ctx["zeroDisk"] is not True:
        f.append(ctx["zeroDisk"])
    if ctx["loadGamePushes"] != 0:
        f.append(f"client pushed {ctx['loadGamePushes']} LoadGameState(s) since the ending (want 0, P6-4)")
    if ctx["fatalVoteArmed"] != 0:
        f.append(f"host fatalVote.armed={ctx['fatalVoteArmed']!r} (want 0)")
    return f


def f1_cells(ctx):
    owners, s = ctx["owners"], clean(ctx["shooter"]["name"])

    def promo_client():
        got = ctx["client"]["rows"].get("PromotionsState")
        return [] if got == [[s, RANK_TR_F1, BASE]] else [f"client PromotionsState rows {got} != "
                                                         f"{[[s, RANK_TR_F1, BASE]]}"]

    def promo_host():
        must = (lambda base: [] if base == [[s, RANK_TR_F1, BASE]] else
                [f"host PromotionsState rows (stripped) {base} != {[[s, RANK_TR_F1, BASE]]}"])
        return rows_cell(ctx, "PromotionsState", owners, must) + cell_end(ctx)
    return [
        ("1 both debriefings, the client's display-only", lambda: cell_debriefs(ctx)),
        ("2 the client adopted the host's world", lambda: cell_adopted(ctx)),
        ("3 the client's chain", lambda: cell_chain(ctx, CHAIN_F1, True, "no PromotionsState")),
        ("4 the client's PromotionsState rows", promo_client),
        ("5 page-2 [Player] prefixes on both", lambda: cell_page2(ctx, owners)),
        ("6 the host's PromotionsState rows; both on the geoscape", promo_host),
    ]


def f4_cells(ctx):
    def fixture():
        got = ctx["host"]["rows"].get("CannotReequipState")
        return [] if sorted(got or []) == sorted(REEQUIP_ROWS_F4) else [f"FIXTURE-STOP: the host's CannotReequipState rows {got} != "
                                                  f"{REEQUIP_ROWS_F4} (T0-S6 (iv) staging)"]

    def shown():
        cr = ctx["client"]["rows"].get("CannotReequipState")
        return [] if cr is not None else [f"the client shows no CannotReequipState (its stack after the OK "
                                          f"{ctx['client']['afterOk']}, chain {ctx['client']['record'].get('chain')})"]

    def same():
        hr, cr = ctx["host"]["rows"].get("CannotReequipState"), ctx["client"]["rows"].get("CannotReequipState")
        return [] if cr == hr else [f"client CannotReequipState rows {cr} != the host's {hr}"]

    def adopted_base():
        p3 = ctx["client"]["record"].get("page3") or {}
        return [] if (p3.get("live"), p3.get("baseIndex")) == (1, 0) else [
            f"client battleEnd.page3={p3} (want live 1, baseIndex 0: the debriefing's _base is the adopted base 0)"]
    return [
        ("1 the host's CannotReequipState (fixture)", fixture),
        ("2 the client's CannotReequipState", shown),
        ("3 its rows == the host's", same),
        ("4 over the adopted base", adopted_base),
    ]


def f23_cells(ctx):
    owners, dead, surv = ctx["owners"], clean(ctx["dead"]), clean(ctx["survivor"])

    def medals():
        must = (lambda base: [] if ([MEDAL_TR, ""] in base and any(r and r[0] == surv for r in base)) else
                [f"host CommendationState rows (stripped) {base} lack the medal {MEDAL_TR!r} title or {surv!r}"])
        return rows_cell(ctx, "CommendationState", owners, must)

    def late():
        must = (lambda base: [] if base and base[0] and base[0][0] == dead else
                [f"host CommendationLateState rows (stripped) {base} do not list the dead {dead!r} first"])
        return rows_cell(ctx, "CommendationLateState", owners, must) + cell_end(ctx)
    return [
        ("1 both debriefings, the client's display-only", lambda: cell_debriefs(ctx)),
        ("2 the client adopted the host's world", lambda: cell_adopted(ctx)),
        ("3 the client's chain", lambda: cell_chain(ctx, CHAIN_F23, True,
                                                    "neither CommendationState nor CommendationLateState")),
        ("4 CommendationState rows on both", medals),
        ("5 CommendationLateState rows on both; both on the geoscape", late),
    ]


# ===================== one boot =====================


def check_row(rid, cells, results):
    """Cells in order; the first failure ends the row (later cells "not reached"). Returns the row's cell records."""
    out, verdict = [], None
    for i, (name, fn) in enumerate(cells):
        try:
            f = fn()
        except Exception as e:
            f = [f"{type(e).__name__}: {short(e, 600)}"]
        out.append({"cell": name, "pass": not f, "fails": f})
        if f:
            rest = [c[0].split(" ")[0] for c in cells[i + 1:]]
            verdict = f"cell {name}: " + "; ".join(str(x) for x in f) + (f" | cells {rest} not reached" if rest else "")
            break
    results[rid] = verdict
    return out


def run_boot(boot, tag, port, mods, stage_fn, rows, results, walls):
    t0, ctx, js = time.time(), {"boot": boot}, None
    crash0 = session._crash_log_snapshot()
    pre = None
    try:
        try:
            js = shared_fixture.bring_up(tag, (0, 0, port), mods=mods)
            stage_fn(js, ctx)
        except Exception as e:
            pre = f"pre-cell (FIXTURE-STOP) {short(e, 800)}"
        if pre is None:
            try:
                procedure(js, ctx)
            except Exception as e:
                pre = f"procedure (the OKs and follow-up reads) raised {short(e, 800)}"
        new_crash = sorted(session._crash_log_snapshot() - crash0)
        ctx["newCrashLogs"] = new_crash
        if js is not None:
            try:
                ctx["end"] = {"host": camp.view(js.host), "client": camp.view(js.client)}
            except Exception as e:
                ctx["end"] = f"probe failed: {short(e)}"
        ctx["rows"] = {}
        for rid, cells_fn in rows:
            if pre:
                results[rid] = pre
            else:
                ctx["rows"][rid] = check_row(rid, cells_fn(ctx), results)
            if new_crash:
                results[rid] = (results[rid] + " | " if results[rid] else "") + f"new crash log(s): {new_crash}"
        evidence(boot, ctx)
        for rid, _f in rows:
            print(f"PASS {rid}" if results[rid] is None else f"FAIL {rid}: {results[rid]}", flush=True)
    finally:
        if js is not None:
            try:
                js.shutdown()
            except Exception as e:
                print(f"[w2p7-scc] shutdown: {short(e)}", flush=True)
        walls[boot] = round(time.time() - t0, 1)


def main():
    t0, results, walls = time.time(), {}, {}
    run_boot("boot1", "w2p7scc_f1", PORTS["boot1"], (), stage_boot1, [("F1", f1_cells), ("F4", f4_cells)],
             results, walls)
    run_boot("boot2", "w2p7scc_f23", PORTS["boot2"], (MEDAL_MOD,), stage_boot2, [("F2/F3", f23_cells)],
             results, walls)
    order = ["F1", "F4", "F2/F3"]
    passed = [r for r in order if r in results and results[r] is None]
    failed = [r for r in order if r not in passed]
    print(f"\ntest_w2_campaign_followups: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (boot walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
