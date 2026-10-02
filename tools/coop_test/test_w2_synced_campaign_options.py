"""W2-P10 S-A - test_w2_synced_campaign_options.py (SHARED): 14 campaign options join W2-P9's synced set.

Owner D134, D162 a, D163 a, D165 a, D200 a. Spec docs rewrite/prompts/w2p10_campaign_options_scope.md as
re-pinned by AMENDMENT P10-1 (section 3 PX-1..PX-8, section 4.1 S-A, section 5). Constants:
docs rewrite/w2p10-task0/CONSTANTS.md (TASK 0 `w2p10-t0`, F5393-F5406).

Before S-A.2 each machine reads its OWN copy of the 14 campaign options; the host's 14 decide the shared world
while the second player's screens follow its own. After it the host's globals are the session table: a joiner takes
them silently, a change goes through the host and applies between actions (every machine posts a System chat line),
a replica drains the shared economy before applying an option change (Q2), and leaving restores each player's own
values; options.cfg never receives a shared value.

ONE SHARED boot (PX-5): shared_fixture.bring_up on lobby key 47244, host user dir = HOST_OPTS, client = defaults.
OWN_FILE = each machine's options.cfg read after the bring-up returns (F4983), the 16 ids parsed (compare parsed,
never bytes, F4982). Rows in this order (C5 before C4 so C4's red resync cannot disturb C5's red; C8 last):

| row | RED cells on the S-A.1 build |
|---|---|
| C1 join   | client option_values of the 14 == the client defaults (not the host's); client own lacks the 14 |
| C7 prefix | the 14 P10 rows are not prefixed (only P9's 14 are): OXC prefixed != 20, OXCE prefixed != 8 |
| C3 change | storageLimitsEnforced not a table id -> client rejected +1; host not applied, values/version/chat unchanged |
| C5 A7     | world_diff holds bases[0].facilities (Q's buildTime differs 32 vs 16) |
| C4 A12    | at the first read world_diff holds bases[0].items.STR_PISTOL_CLIP (differs by N=1: host 7 vs client 8) |
| C6 order  | oxceAlternateCraftEquipmentManagement not a table id -> host rejected +1 (and the drain/world/both-false green cells fail) |
| C8 leave  | precondition "client option_values of the 14 != its boot defaults before the leave" fails |

Guard every row: the 16 ids in each machine's options.cfg (parsed) == OWN_FILE (STOP-IF 3). Each row prints
ONE "EVIDENCE <id>:" line (both machines' synced_options_state minus `advanced`, and option_values of the 16) then
"PASS <id>" or "FAIL <id>: <cells>". Exit 0 only when every row passes, 2 otherwise; no exit 3, no retry (section A.8).
WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_synced_campaign_options.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402

# ----- PX-5 constants (docs rewrite/w2p10-task0/CONSTANTS.md) -----
LOBBY_PORT = 47244                      # SHARED coop rendezvous (STOP-IF 11: only 47244-47247)
CTRL = (49244, 49245)                   # ephemeral control-socket LABELS (do not bind)

# the 14 synced campaign options, scope order A1..A14 (PX-1).
IDS14 = ["storageLimitsEnforced", "canSellLiveAliens", "fieldPromotions", "oxceAutomaticPromotions",
         "oxceWoundedDefendBaseIf", "aggressiveRetaliation", "allowBuildingQueue", "craftLaunchAlways",
         "anytimePsiTraining", "canTransferCraftsWhileAirborne", "retainCorpses",
         "oxceAlternateCraftEquipmentManagement", "oxceManualPromotions", "oxceGeoscapeEventsInstantDelivery"]
# the 2 per-player controls (P10-V2/V3: never synced).
CONTROLS = ["oxceAutoSell", "oxcePersonalLayoutIncludingArmor"]
IDS16 = IDS14 + CONTROLS
INT_IDS = {"oxceWoundedDefendBaseIf"}

# PX-5 HOST_OPTS: every id differs from the client default.
HOST_OPTS = {"storageLimitsEnforced": True, "canSellLiveAliens": True, "fieldPromotions": True,
             "oxceAutomaticPromotions": False, "oxceWoundedDefendBaseIf": 50, "aggressiveRetaliation": True,
             "allowBuildingQueue": True, "craftLaunchAlways": True, "anytimePsiTraining": True,
             "canTransferCraftsWhileAirborne": True, "retainCorpses": True,
             "oxceAlternateCraftEquipmentManagement": True, "oxceManualPromotions": True,
             "oxceGeoscapeEventsInstantDelivery": False, "oxceAutoSell": True,
             "oxcePersonalLayoutIncludingArmor": False}
# the client's boot defaults (no override): the engine registrations (desktop).
CLIENT_DEF = {"storageLimitsEnforced": False, "canSellLiveAliens": False, "fieldPromotions": False,
              "oxceAutomaticPromotions": True, "oxceWoundedDefendBaseIf": 100, "aggressiveRetaliation": False,
              "allowBuildingQueue": False, "craftLaunchAlways": False, "anytimePsiTraining": False,
              "canTransferCraftsWhileAirborne": False, "retainCorpses": False,
              "oxceAlternateCraftEquipmentManagement": False, "oxceManualPromotions": False,
              "oxceGeoscapeEventsInstantDelivery": True, "oxceAutoSell": False,
              "oxcePersonalLayoutIncludingArmor": True}
HOST_14 = {k: HOST_OPTS[k] for k in IDS14}
CDEF_14 = {k: CLIENT_DEF[k] for k in IDS14}

# PX-5 / C3 chat: en-US literals (bin/common/Language/en-US.yml).
SYSTEM = "System"
DESC = {"storageLimitsEnforced": "Storage limits for recovered items"}

# C4/C6 A12 fixture pins (CONSTANTS T0-1c): the SKYRANGER transport, one of its seated soldiers, a 1-item layout.
A12 = "oxceAlternateCraftEquipmentManagement"
LAYOUT_ITEM = "STR_PISTOL_CLIP"
LAYOUT_SLOT = "belt"
# C5 A7 fixture pin.
GRID = "STR_LIVING_QUARTERS"

# C7 Advanced prefix sets (T0-3 / F5158): after P10 S-A green, 20 OXC + 8 OXCE prefixed rows.
P9_OXC = {"alienBleeding", "allowPsiStrengthImprovement", "allowPsionicCapture", "battleAutoEnd",
          "battleExplosionHeight", "battleInstantGrenade", "battleUFOExtenderAccuracy", "disableAutoEquip",
          "includePrimeStateInSavedLayout", "sneakyAI", "weaponSelfDestruction"}
P10_OXC = {"storageLimitsEnforced", "canSellLiveAliens", "fieldPromotions", "aggressiveRetaliation",
           "allowBuildingQueue", "craftLaunchAlways", "anytimePsiTraining", "canTransferCraftsWhileAirborne",
           "retainCorpses"}
P9_OXCE = {"oxceEnableOffCentreShooting", "oxceReactionFireThreshold", "oxceUniformShootingSpread"}
P10_OXCE = {"oxceAutomaticPromotions", "oxceWoundedDefendBaseIf", "oxceAlternateCraftEquipmentManagement",
            "oxceManualPromotions", "oxceGeoscapeEventsInstantDelivery"}
OXC_PREFIXED = P9_OXC | P10_OXC   # 20
OXCE_PREFIXED = P9_OXCE | P10_OXCE  # 8
# rows that must NEVER be prefixed (per-player B options + the (C)/excluded options).
NOT_PREFIXED = {"oxceAutoSell", "oxcePersonalLayoutIncludingArmor", "customInitialBase", "newSeedOnLoad",
                "oxceRememberDisabledCraftWeapons", "psiStrengthEval"}

# ----- bounded waits -----
APPLY_S = 6.0
ARRIVE_S = 3.0
SETTLE_S = 2.0
RESYNC_S = 2.0
STATE_S = 15
MENU_S = 60
POLL = 0.05


def short(e):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= 400 else s[:400] + "..."


def wait_until(pred, timeout, interval=POLL):
    t0 = time.time()
    while True:
        try:
            v = pred()
        except Exception:
            v = None
        if v:
            return True, round(time.time() - t0, 2)
        if time.time() - t0 >= timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)


# ----- probes -----

def sos(gc):
    """synced_options_state minus `ok` and the bulky `advanced` view (read separately for C7)."""
    r = gc.cmd({"cmd": "synced_options_state"})
    return {k: v for k, v in r.items() if k not in ("ok", "advanced")}


def ov(gc, ids):
    """PX-3 option_values: the RAW Options globals on THIS machine for `ids`, independent of the table."""
    r = gc.cmd({"cmd": "option_values", "ids": ids})
    return r.get("values") or {}


def chat(st):
    return [(m.get("player"), m.get("text")) for m in (st.get("chat") or [])]


def synced_chat(st):
    return [(p, t) for (p, t) in chat(st) if "changed" in t and " to " in t]


def new_lines(before, after):
    b, a = chat(before), chat(after)
    return a[len(b):] if a[:len(b)] == b else a


def word(oid, v):
    return str(int(v)) if oid in INT_IDS else ("YES" if v else "NO")


def line(player, oid, v):
    return (SYSTEM, f"{player} changed {DESC[oid]} to {word(oid, v)}")


def geo_state(gc):
    return gc.ok({"cmd": "geo_state"})


def own_base(gs):
    for b in gs["bases"]:
        if not b["coopBase"] and not b["coopIcon"]:
            return b
    return gs["bases"][0]


def base_report(gc):
    return gc.ok({"cmd": "base_report"})


def shared_stats(gc):
    return gc.ok({"cmd": "shared_stats"})


def resync_stats(gc):
    return gc.ok({"cmd": "shared_resync_stats"})


def item_qty(gc, item):
    return own_base(geo_state(gc))["items"].get(item, 0)


def world_diff(h, c):
    return shared_fixture.world_diff(h, c)


def norm(v):
    if v == "true":
        return True
    if v == "false":
        return False
    import re
    if isinstance(v, str) and re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


def read_cfg(gc):
    """The 16 ids of this machine's options.cfg, parsed (engine reader takes the FIRST key; so does this)."""
    import re
    with open(os.path.join(gc.user_dir, "options.cfg"), "r", encoding="utf-8") as f:
        text = f.read()
    out = {}
    for i in IDS16:
        hits = re.findall(r"^\s*" + re.escape(i) + r":\s*(\S+)\s*$", text, re.M)
        out[i] = norm(hits[0]) if hits else None
    return out


def vdiff(a, b, ids):
    a, b = a or {}, b or {}
    return {k: (a.get(k), b.get(k)) for k in ids if a.get(k) != b.get(k)}


# ----- widgets (C7), reusing the T0-3 helpers -----

def states(gc):
    return gc.cmd({"cmd": "get_state"}).get("states", [])


def top(gc):
    s = states(gc)
    return s[-1] if s else ""


def top_is(gc, name):
    return (top(gc) or "").endswith(name)


def buttons(gc):
    lw = gc.cmd({"cmd": "list_widgets"})
    return lw.get("state"), [w for w in lw.get("widgets", []) if w.get("interactive") and "text" in w]


def click_exact(gc, caption, timeout=STATE_S):
    def ready():
        _, bs = buttons(gc)
        cands = [w for w in bs if w.get("visible") and caption.lower() in str(w.get("text", "")).lower()]
        exact = [i for i, w in enumerate(cands) if str(w.get("text", "")).strip().upper() == caption.upper()]
        return {"nth": exact[0]} if (len(exact) == 1 and not cands[exact[0]].get("hidden")) else None
    got, _ = wait_until(ready, timeout)
    if not got:
        return False
    _, bs = buttons(gc)
    cands = [w for w in bs if w.get("visible") and caption.lower() in str(w.get("text", "")).lower()]
    exact = [i for i, w in enumerate(cands) if str(w.get("text", "")).strip().upper() == caption.upper()]
    if len(exact) != 1:
        return False
    return bool(gc.cmd({"cmd": "click_widget", "match": caption, "nth": exact[0]}).get("ok"))


def adv_rows(gc):
    r = gc.cmd({"cmd": "synced_options_state"})
    return (r.get("advanced") or {}).get("rows") or []


def tab_sets(rows):
    present = {rw.get("id") for rw in rows if rw.get("id") not in ("", "?", None)}
    prefixed = {rw.get("id") for rw in rows if rw.get("prefixed") and rw.get("id") not in ("", "?", None)}
    return present, prefixed


def open_advanced_geo(gc):
    """GeoscapeState -> OPTIONS -> PauseState -> GAME OPTIONS -> OptionsGeoscapeState -> ADVANCED (OXC tab)."""
    if not click_exact(gc, "OPTIONS"):
        return False
    if not wait_until(lambda: top_is(gc, "PauseState"), STATE_S)[0]:
        return False
    if not click_exact(gc, "GAME OPTIONS"):
        return False
    if not wait_until(lambda: top_is(gc, "OptionsGeoscapeState") or top_is(gc, "OptionsBaseState"), STATE_S)[0]:
        return False
    if not click_exact(gc, "ADVANCED"):
        return False
    return wait_until(lambda: top_is(gc, "OptionsAdvancedState"), STATE_S)[0]


# ----- row framework -----

class Row:
    def __init__(self, rid):
        self.rid = rid
        self.fails, self.passed, self.ev = [], [], {}
        self.t0 = time.time()

    def cell(self, name, ok, detail=""):
        if ok:
            self.passed.append(name)
        else:
            self.fails.append(f"{name}: {detail}")


class Ctx:
    def __init__(self, host, client):
        self.h, self.c = host, client
        self.own_file = {}
        self.sol_id = None
        self.craft_id = None


def guard_file(r, x):
    d = {m: vdiff(read_cfg(gc), x.own_file.get(m), IDS16) for m, gc in (("host", x.h), ("client", x.c))}
    r.cell("g_file", not d["host"] and not d["client"], f"options.cfg differs from OWN_FILE {d}")


def ev_common(r, x):
    r.ev["host_sos"] = sos(x.h)
    r.ev["client_sos"] = sos(x.c)
    r.ev["host_ov"] = ov(x.h, IDS16)
    r.ev["client_ov"] = ov(x.c, IDS16)


# ===================== rows =====================

def row_c1(r, x):
    hov, cov = ov(x.h, IDS14), ov(x.c, IDS14)
    hs, cs = sos(x.h), sos(x.c)
    ev_common(r, x)
    # control: host reads its own HOST_OPTS
    r.cell("host_boot", not vdiff(hov, HOST_14, IDS14), f"host option_values vs HOST_OPTS {vdiff(hov, HOST_14, IDS14)}")
    # RED: client option_values of the 14 == host's (== HOST_OPTS). red -> client defaults differ.
    r.cell("join_values", not vdiff(cov, hov, IDS14), f"client vs host option_values {vdiff(cov, hov, IDS14)}")
    # RED: client own contains the 14 == client defaults. red -> own lacks the 14.
    own = cs.get("own") or {}
    r.cell("own_14", all(k in own for k in IDS14) and not vdiff(own, CDEF_14, IDS14),
           f"client own: missing {[k for k in IDS14 if k not in own]} diff {vdiff(own, CDEF_14, IDS14)}")
    # control: P9 join happened in this (shared) session.
    r.cell("table_join", (cs.get("tablesApplied"), cs.get("lastTableFrom")) == (1, "join"),
           f"client tablesApplied {cs.get('tablesApplied')} lastTableFrom {cs.get('lastTableFrom')!r}")
    # control: no synced-option-change chat from the silent join.
    r.cell("chat_silent", not synced_chat(hs) and not synced_chat(cs),
           f"synced chat host {synced_chat(hs)} client {synced_chat(cs)}")
    # control: the per-player controls keep each machine's own boot value.
    cctrl = {k: cov_ctrl for k, cov_ctrl in ov(x.c, CONTROLS).items()}
    hctrl = ov(x.h, CONTROLS)
    r.cell("controls", not vdiff(hctrl, {k: HOST_OPTS[k] for k in CONTROLS}, CONTROLS)
           and not vdiff(cctrl, {k: CLIENT_DEF[k] for k in CONTROLS}, CONTROLS),
           f"controls host {hctrl} client {cctrl}")
    guard_file(r, x)


def row_c7(r, x):
    gc = x.c
    if not wait_until(lambda: top_is(gc, "GeoscapeState"), STATE_S)[0]:
        r.cell("pre_geo", False, f"client not on GeoscapeState (top {top(gc)})")
        return
    if not open_advanced_geo(gc):
        r.cell("pre_open", False, f"could not reach OptionsAdvancedState (top {top(gc)})")
        return
    oxc_present, oxc_pref = tab_sets(adv_rows(gc))
    opened_oxce = click_exact(gc, "OXCE")
    wait_until(lambda: any(rw.get("id") in P10_OXCE or rw.get("id") in P9_OXCE for rw in adv_rows(gc)), STATE_S)
    oxce_present, oxce_pref = tab_sets(adv_rows(gc))
    all_present, all_pref = oxc_present | oxce_present, oxc_pref | oxce_pref
    r.ev.update(oxc_prefixed=sorted(oxc_pref), oxce_prefixed=sorted(oxce_pref),
                oxc_present_n=len(oxc_present), oxce_present_n=len(oxce_present), opened_oxce=opened_oxce)
    # RED: the 14 P10 rows carry no prefix yet -> only P9's 11 OXC / 3 OXCE prefixed.
    r.cell("oxc_prefixed", oxc_pref == OXC_PREFIXED,
           f"OXC prefixed {sorted(oxc_pref)} (want {len(OXC_PREFIXED)}: {sorted(OXC_PREFIXED)})")
    r.cell("oxce_prefixed", oxce_pref == OXCE_PREFIXED,
           f"OXCE prefixed {sorted(oxce_pref)} (want {len(OXCE_PREFIXED)}: {sorted(OXCE_PREFIXED)})")
    # control: the per-player / excluded rows are never prefixed.
    r.cell("controls_unprefixed", not (NOT_PREFIXED & all_pref),
           f"control rows wrongly prefixed {sorted(NOT_PREFIXED & all_pref)}")
    r.cell("controls_present", {"oxceAutoSell", "oxcePersonalLayoutIncludingArmor"} <= all_present,
           f"per-player controls missing from Advanced {sorted({'oxceAutoSell', 'oxcePersonalLayoutIncludingArmor'} - all_present)}")
    # control: the two Cancels land back on GeoscapeState (no OK, F4987).
    click_exact(gc, "CANCEL")
    okp = wait_until(lambda: top_is(gc, "PauseState"), STATE_S)[0]
    click_exact(gc, "CANCEL")
    okg = wait_until(lambda: top_is(gc, "GeoscapeState"), STATE_S)[0]
    r.cell("back_geoscape", okp and okg, f"cancel chain: PauseState {okp} GeoscapeState {okg} (top {top(gc)})")
    guard_file(r, x)


def row_c3(r, x):
    oid = "storageLimitsEnforced"
    h0, c0 = sos(x.h), sos(x.c)
    rej0 = c0.get("rejected") or 0
    resp = x.c.cmd({"cmd": "synced_option_request", "id": oid, "value": False})
    ok, secs = wait_until(lambda: (sos(x.h).get("version") == (h0.get("version") or 0) + 1
                                   and sos(x.c).get("version") == (c0.get("version") or 0) + 1), APPLY_S)
    h1, c1 = sos(x.h), sos(x.c)
    hov1, cov1 = ov(x.h, [oid]), ov(x.c, [oid])
    ev_common(r, x)
    r.ev.update(request=resp, waitOk=ok, waitS=secs, clientRejectedDelta=(c1.get("rejected") or 0) - rej0,
                hostValue=hov1.get(oid), clientValue=cov1.get(oid))
    new = [a for a in (h1.get("applied") or []) if (a.get("version") or 0) > (h0.get("version") or 0)]
    want = {"id": oid, "value": False, "result": "applied", "arrivedWhileBusy": False, "player": c0.get("localName")}
    # RED cells (red build: request rejected, nothing applied):
    r.cell("applied", len(new) == 1 and all(new[0].get(k) == v for k, v in want.items()),
           f"host ring after request {new} (want one {want})")
    r.cell("values", hov1.get(oid) is False and cov1.get(oid) is False,
           f"option_values {oid} host {hov1.get(oid)} client {cov1.get(oid)} (want both False)")
    r.cell("version", h1.get("version") == (h0.get("version") or 0) + 1
           and c1.get("version") == (c0.get("version") or 0) + 1,
           f"version host {h0.get('version')}->{h1.get('version')} client {c0.get('version')}->{c1.get('version')}")
    want_line = [line(c0.get("localName"), oid, False)]
    nh, nc = new_lines(h0, h1), new_lines(c0, c1)
    r.cell("chat", nh == want_line and nc == want_line, f"new chat host {nh} client {nc} (want {want_line})")
    # options_save on both, then the guard: no shared value leaks to options.cfg.
    x.h.cmd({"cmd": "options_save"})
    x.c.cmd({"cmd": "options_save"})
    guard_file(r, x)


def _facility_cells(base):
    occ, built = set(), set()
    for f in base["facilities"]:
        for dx in range(f["sizeX"]):
            for dy in range(f["sizeY"]):
                c = (f["x"] + dx, f["y"] + dy)
                occ.add(c)
                if f["buildTime"] == 0:
                    built.add(c)
    return occ, built


def _neigh(c):
    x, y = c
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def _pick_A_Q(base, size=6):
    occ, built = _facility_cells(base)
    free = [(x, y) for x in range(size) for y in range(size) if (x, y) not in occ]
    A = next((c for c in free if any(n in built for n in _neigh(c))), None)
    if A is None:
        return None, None
    Q = next((c for c in free if c != A and A in _neigh(c) and not any(n in built for n in _neigh(c))), None)
    return A, Q


def _fac_bt(gc, cell):
    b = own_base(geo_state(gc))
    for f in b["facilities"]:
        if f["x"] == cell[0] and f["y"] == cell[1]:
            return f["buildTime"]
    return None


def row_c5(r, x):
    b = own_base(geo_state(x.h))
    A, Q = _pick_A_Q(b)
    r.ev.update(A=A, Q=Q)
    if A is None or Q is None:
        r.cell("pre_AQ", False, f"no A/Q pair on the start grid (A {A} Q {Q}) (FIXTURE-STOP)")
        return
    ac0 = shared_stats(x.c)["applyCount"]
    x.h.cmd({"cmd": "fac_build", "facility": GRID, "x": A[0], "y": A[1]})
    wait_until(lambda: shared_stats(x.c)["applyCount"] >= ac0 + 1, APPLY_S)
    ac1 = shared_stats(x.c)["applyCount"]
    x.h.cmd({"cmd": "fac_build", "facility": GRID, "x": Q[0], "y": Q[1]})
    okQ, _ = wait_until(lambda: shared_stats(x.c)["applyCount"] >= ac1 + 1, APPLY_S)
    time.sleep(1.0)
    bt = {"A_host": _fac_bt(x.h, A), "A_client": _fac_bt(x.c, A),
          "Q_host": _fac_bt(x.h, Q), "Q_client": _fac_bt(x.c, Q)}
    wd = world_diff(x.h, x.c)
    ev_common(r, x)
    r.ev.update(buildTimes=bt, applyCountRoseQ=okQ, worldDiff=wd[:25])
    # control: A built immediately on both (16/16, adjacent to a built facility).
    r.cell("a_eq", bt["A_host"] == bt["A_client"], f"A buildTime host {bt['A_host']} client {bt['A_client']}")
    # RED: A7 unsynced -> host queues Q (32), client builds Q at rule time (16).
    r.cell("q_eq", bt["Q_host"] == bt["Q_client"], f"Q buildTime host {bt['Q_host']} client {bt['Q_client']}")
    r.cell("world_eq", not wd, f"world_diff {wd[:25]}")
    guard_file(r, x)


def row_c4(r, x):
    b = own_base(geo_state(x.h))
    transport = next((cr for cr in b["crafts"] if "SKYRANGER" in cr["type"]), b["crafts"][0] if b["crafts"] else None)
    rep = base_report(x.h)
    seated = [s for s in rep["soldiers"] if transport and s["craft"] == transport["id"]]
    if transport is None or not seated or LAYOUT_ITEM not in b["items"] or b["items"][LAYOUT_ITEM] < 1:
        r.cell("pre_fixture", False,
               f"FIXTURE-STOP: craft {transport} seated {len(seated) if transport else 0} "
               f"{LAYOUT_ITEM} stock {b['items'].get(LAYOUT_ITEM)}")
        return
    sol = seated[0]
    x.sol_id, x.craft_id = sol["id"], transport["id"]
    r.ev.update(soldierId=sol["id"], soldierName=sol["name"], craftId=transport["id"], item=LAYOUT_ITEM)
    # unassign one seated soldier -> base-resident (all 8 start craft-seated, CONSTANTS)
    ac0 = shared_stats(x.c)["applyCount"]
    x.c.cmd({"cmd": "craft_assign", "soldier_id": sol["id"], "craft_id": transport["id"], "on": False})
    wait_until(lambda: shared_stats(x.c)["applyCount"] >= ac0 + 1, APPLY_S)
    before = {"host": item_qty(x.h, LAYOUT_ITEM), "client": item_qty(x.c, LAYOUT_ITEM)}
    # give the 1-item layout on BOTH machines (F5151), then re-seat client-side.
    x.h.cmd({"cmd": "give_layout", "item": LAYOUT_ITEM, "count": 1, "slot": LAYOUT_SLOT, "name": sol["name"]})
    x.c.cmd({"cmd": "give_layout", "item": LAYOUT_ITEM, "count": 1, "slot": LAYOUT_SLOT, "name": sol["name"]})
    ac1 = shared_stats(x.c)["applyCount"]
    rs0 = resync_stats(x.c)["mismatches"]
    x.c.cmd({"cmd": "craft_assign", "soldier_id": sol["id"], "craft_id": transport["id"], "on": True})
    okA, W = wait_until(lambda: shared_stats(x.c)["applyCount"] >= ac1 + 1, APPLY_S)
    after = {"host": item_qty(x.h, LAYOUT_ITEM), "client": item_qty(x.c, LAYOUT_ITEM)}
    wd = world_diff(x.h, x.c)
    ev_common(r, x)
    r.ev.update(storesBefore=before, storesAfterAssign=after, applyWindowS=W,
                N_host_minus_client=after["host"] - after["client"], worldDiff=wd[:25])
    # RED: A12 unsynced -> the re-seat moves the layout item from base stores on the host (A12 on) only.
    r.cell("item_eq", after["host"] == after["client"],
           f"{LAYOUT_ITEM} stores host {after['host']} client {after['client']} (N {after['host'] - after['client']})")
    r.cell("world_eq", not wd, f"world_diff {wd[:25]}")
    time.sleep(RESYNC_S)
    rs1 = resync_stats(x.c)["mismatches"]
    r.ev["resyncMismatches"] = (rs0, rs1)
    r.cell("resync_quiet", rs1 == rs0, f"client mismatches {rs0}->{rs1} after {RESYNC_S}s")
    guard_file(r, x)


def row_c6(r, x):
    if x.sol_id is None or x.craft_id is None:
        r.cell("pre_fixture", False, "no soldier/craft pinned by C4 (FIXTURE-STOP)")
        return
    arm = x.c.cmd({"cmd": "shared_update_defer", "on": True})
    r.ev["armDefer"] = arm
    try:
        base_ac = shared_stats(x.c)["applyCount"]
        h0 = sos(x.h)
        rej0 = h0.get("rejected") or 0
        # host unassigns the same soldier -> a shared_apply the deferred client queues but does not apply yet.
        hac0 = shared_stats(x.h)["applyCount"]
        x.h.cmd({"cmd": "craft_assign", "soldier_id": x.sol_id, "craft_id": x.craft_id, "on": False})
        wait_until(lambda: shared_stats(x.h)["applyCount"] >= hac0 + 1, APPLY_S)
        time.sleep(1.0)  # let the shared_apply reach the client's (deferred) queue
        ac_after_craft = shared_stats(x.c)["applyCount"]
        # host changes A12 -> on the red build this id is not in the table: host rejects, nothing sent.
        setresp = x.h.cmd({"cmd": "synced_option_request", "id": A12, "value": False})
        wait_until(lambda: ov(x.c, [A12]).get(A12) is False
                   and sos(x.c).get("version") == sos(x.h).get("version"), APPLY_S)
        ac_at_set = shared_stats(x.c)["applyCount"]
        h1 = sos(x.h)
        r.ev.update(setResp=setresp, hostRejectedDelta=(h1.get("rejected") or 0) - rej0,
                    baseApplyCount=base_ac, applyCountAfterCraft=ac_after_craft, applyCountAtSet=ac_at_set)
    finally:
        rel = x.c.cmd({"cmd": "shared_update_defer", "on": False})
        r.ev["releaseDefer"] = rel
    time.sleep(SETTLE_S)
    hov, cov = ov(x.h, [A12]), ov(x.c, [A12])
    wd = world_diff(x.h, x.c)
    ev_common(r, x)
    r.ev.update(hostA12=hov.get(A12), clientA12=cov.get(A12), worldDiffAfterRelease=wd[:25])
    # RED: host rejected +1 (A12 not a table id at red).
    r.cell("host_accepted", (sos(x.h).get("rejected") or 0) == rej0,
           f"host rejected {rej0}->{sos(x.h).get('rejected')} (the A12 set was rejected: id not in the table)")
    # Q2 drain (green S-A.2 step 2): the queued craft_assign applies AT the set, before the release.
    r.cell("drained", ac_at_set == base_ac + 1,
           f"client applyCount base {base_ac} afterCraft {ac_after_craft} atSet {ac_at_set} (want base+1 at the set)")
    r.cell("both_false", hov.get(A12) is False and cov.get(A12) is False,
           f"A12 host {hov.get(A12)} client {cov.get(A12)} (want both False)")
    r.cell("world_eq_after", not wd, f"world_diff after release {wd[:25]}")
    guard_file(r, x)


def row_c8(r, x):
    c0 = sos(x.c)
    cov0 = ov(x.c, IDS14)
    ev_common(r, x)
    # RED: precondition - the client must have adopted the host's 14 (different from its defaults) before leaving.
    r.cell("pre", bool(vdiff(cov0, CDEF_14, IDS14)),
           f"client option_values of the 14 == its boot defaults, nothing to restore {vdiff(cov0, CDEF_14, IDS14)}")
    x.c.ok({"cmd": "disconnect_to_menu"})
    x.c.wait_for("client at the main menu", lambda: top_is(x.c, "MainMenuState"), timeout=MENU_S)
    c1 = sos(x.c)
    cov1 = ov(x.c, IDS14)
    r.ev.update(clientAfterLeave=c1, clientOvAfter=cov1)
    r.cell("restore", not vdiff(cov1, CDEF_14, IDS14), f"client option_values after leave vs defaults {vdiff(cov1, CDEF_14, IDS14)}")
    r.cell("own_null", c1.get("own") is None, f"client own after leave {c1.get('own')}")
    r.cell("active_false", c1.get("active") is False, f"client active after leave {c1.get('active')}")


# ===================== runner =====================

ROWS = (("C1", row_c1), ("C7", row_c7), ("C3", row_c3), ("C5", row_c5), ("C4", row_c4),
        ("C6", row_c6), ("C8", row_c8))


def run_one(rid, fn, x, results):
    r = Row(rid)
    try:
        fn(r, x)
    except Exception as e:
        r.cell("exception", False, short(e))
    r.ev["cellsPassed"] = r.passed
    r.ev["wallS"] = round(time.time() - r.t0, 1)
    print(f"EVIDENCE {rid}: {r.ev}", flush=True)
    if r.fails:
        results[rid] = False
        print(f"FAIL {rid}: {len(r.fails)} cell(s): " + " | ".join(r.fails), flush=True)
    else:
        results[rid] = True
        print(f"PASS {rid}", flush=True)


def main():
    t0 = time.time()
    js = shared_fixture.bring_up("w2p10co", (CTRL[0], CTRL[1], LOBBY_PORT), host_options=HOST_OPTS)
    host, client = js.host, js.client
    x = Ctx(host, client)
    results = {}
    order = [rid for rid, _ in ROWS]
    try:
        x.own_file = {"host": read_cfg(host), "client": read_cfg(client)}
        print(f"[w2p10-sa] bring-up {time.time() - t0:.1f}s OWN_FILE {x.own_file}", flush=True)
        for rid, fn in ROWS:
            run_one(rid, fn, x, results)
    finally:
        try:
            js.shutdown()
        except Exception as e:
            print(f"[w2p10-sa] shutdown: {short(e)}", flush=True)
    passed = [n for n in order if results.get(n)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_w2_synced_campaign_options: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
