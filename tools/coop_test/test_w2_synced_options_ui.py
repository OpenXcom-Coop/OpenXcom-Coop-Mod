"""W2-P9 S-B - test_w2_synced_options_ui.py: the Advanced options screen marks and diverts synced options,
refreshes live and announces changes in chat (owner D134; D164 a, D165 a). Spec: docs
rewrite/prompts/w2p9_synced_options.md as re-pinned by AMENDMENT P9-1 (section 3 PR-11, PR-12, PR-13 `advanced`,
PR-10 prefix key; section 4.2 S-B; section 5) and its P9-1 RULINGS (T0-1 SAFE -> U6 stays). Constants: docs
rewrite/w2p9-task0/CONSTANTS.md (TASK 0 `w2p9-t0`, F4980-F4989) + T0-4 folded into this red run's capture.

S-A already made the host's globals the session table (join push, hostRules, host queue, the FileGuards, the chat
line body, the `synced_options_state` probe). S-B adds, in the Advanced options screen itself, the `[Synced] `
prefix on each synced row, the click divert (the change goes through the host, the row keeps the shared value
until it lands), the in-flight ignore, the live refresh that keeps the scroll, and - reusing S-A's chat body -
the per-change "System" chat line. This red commit adds ONLY the `advanced` view of the probe (TestServer, PR-13)
and this test; product behaviour (prefix, divert, refresh) is S-B green.

ONE boot (PR-14): host user dir {battleInstantGrenade true, battleExplosionHeight 2, sneakyAI true}, client
{battleInstantGrenade false, battleExplosionHeight 0, alienBleeding true}; lobby key 47242. U1 runs on the host
at the main menu BEFORE hosting (role None); then the bring-up and the battle; OWN_FILE = each machine's
options.cfg read after the bring-up (F4983), the 15 ids parsed. Rows in order U1-U6:

| row | fixture | RED cell (S-B.1 build; the divert/prefix/refresh are S-B.2) |
|---|---|---|
| U1 | host at the main menu (role None): OPTIONS -> ADVANCED (OXC) | passes (SP control: no prefix and a vanilla local flip in both builds) |
| U2 | in battle, both machines: ADVANCED, OXC then OXCE tab | no row prefixed (no product prefix yet) |
| U3 | host ADVANCED scrolled to battleExplosionHeight + hold; client left-clicks its battleExplosionHeight row | the click flips the client's own global at once (vanilla, no divert); host pending empty; host screen not refreshed; no chat line |
| U4 | host hold; two host left clicks on weaponSelfDestruction; release | two local flips (back to the start); nothing diverted/ignored, nothing applied, no chat |
| U5 | ADVANCED Cancel on both; then options_save on both | U3/U4's vanilla flips left the machines' values unequal (the divert keeps them equal in S-B.2) |
| U6 | hold; toggle battleSmoothCamera (not synced) and battleInstantGrenade (synced); OK | the synced row's local flip changed the in-memory session value (the divert prevents it in S-B.2) |

Common guards per battle row (S-A): the 15 ids in each options.cfg == OWN_FILE; desyncSeen false on both; the
client's coopClientBStatePushes unchanged since the battle started; hash_now full equal. The guards pass on the
red build (an undiverted options click touches neither the battle nor the saved file).

WV-D99 / WV-D100: one run is the result; every row runs after a failure; every wait is bounded. Each row prints
ONE "EVIDENCE <id>:" line and then "PASS <id>" or "FAIL <id>: <cells>". Exit 0 only when every row passes, 2
otherwise. WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_synced_options_ui.py
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import event_state, assert_hash_clean
import repro_atom_walk as raw
from test_w2_inventory_held import read_key   # PR-14: keyBattleOptions (the HS2 precedent)

# ----- TASK 0 constants (docs rewrite/w2p9-task0/CONSTANTS.md) -----
LOBBY_PORT = "47242"                 # PR-14 / section 5 STOP-IF 15: 47242 belongs to P9 S-B (47240 is S-A)
CTRL_LABELS = (49242, 49243)         # GameClient control sockets (ephemeral local)
HOST_OPTS = {"battleInstantGrenade": True, "battleExplosionHeight": 2, "sneakyAI": True}           # HOST_OPTS=
CLIENT_OPTS = {"battleInstantGrenade": False, "battleExplosionHeight": 0, "alienBleeding": True}   # CLIENT_OPTS=

# PR-1: the 15 table ids in table order; Options.cpp registrations (desktop branch): every bool false, both ints 0.
IDS = ["battleInstantGrenade", "battleExplosionHeight", "oxceEnableOffCentreShooting", "oxceUniformShootingSpread",
       "allowPsiStrengthImprovement", "allowPsionicCapture", "weaponSelfDestruction", "alienBleeding", "sneakyAI",
       "battleAutoEnd", "disableAutoEquip", "includePrimeStateInSavedLayout", "battleUFOExtenderAccuracy",
       "oxceReactionFireThreshold", "oxceInventoryUnloadFixedWeapons"]
INT_IDS = {"battleExplosionHeight", "oxceReactionFireThreshold"}
DEFAULTS = {i: (0 if i in INT_IDS else False) for i in IDS}
OWN_HOST = dict(DEFAULTS, **HOST_OPTS)
OWN_CLIENT = dict(DEFAULTS, **CLIENT_OPTS)

# PR-1 / R3.1 / P9-1 D160-D161; W2-P10 S-A.1 PX-7 re-point (chain rule A.10, F5487): the visible rows by Advanced
# tab. P9's 11 OXC + 3 OXCE, plus W2-P10's 9 OXC (Geoscape) and 5 OXCE (1 Geoscape, 2 Basescape, 2 Battlescape),
# F5158 -> 20 OXC + 8 OXCE prefixed once P10 S-A green lands; the hidden unload row still has no visible row.
OXC_TAB_IDS = {"battleInstantGrenade", "battleExplosionHeight", "allowPsiStrengthImprovement", "allowPsionicCapture",
               "weaponSelfDestruction", "alienBleeding", "sneakyAI", "battleAutoEnd", "disableAutoEquip",
               "includePrimeStateInSavedLayout", "battleUFOExtenderAccuracy",
               "storageLimitsEnforced", "canSellLiveAliens", "fieldPromotions", "aggressiveRetaliation",
               "allowBuildingQueue", "craftLaunchAlways", "anytimePsiTraining", "canTransferCraftsWhileAirborne",
               "retainCorpses"}                                                                # 20 rows (11 P9 + 9 P10)
OXCE_TAB_IDS = {"oxceEnableOffCentreShooting", "oxceUniformShootingSpread", "oxceReactionFireThreshold",
                "oxceAutomaticPromotions", "oxceWoundedDefendBaseIf", "oxceAlternateCraftEquipmentManagement",
                "oxceManualPromotions", "oxceGeoscapeEventsInstantDelivery"}                   # 8 rows (3 P9 + 5 P10)
HIDDEN_ID = "oxceInventoryUnloadFixedWeapons"
# W2-P10 PX-7: the full synced table membership (20 + 8 + the hidden unload option = 29) - a prefixed row outside it
# is a genuine "extra" (was IDS, the 15 P9 ids, before P10).
TABLE_IDS = OXC_TAB_IDS | OXCE_TAB_IDS | {HIDDEN_ID}
assert len(OXC_TAB_IDS) == 20 and len(OXCE_TAB_IDS) == 8

# PR-9 / PR-10 / PR-14: the chat line, English literals (bin/common/Language/en-US.yml, STR_YES / STR_NO).
SYSTEM = "System"
DESC = {"battleInstantGrenade": "Instant grenades", "battleExplosionHeight": "Explosion height",
        "weaponSelfDestruction": "Alien weapon self-destruction", "sneakyAI": "Sneaky AI",
        "alienBleeding": "Alien bleeding"}

# SDLKey codes (TextList keyboard scroll, TextList.cpp; PR-14).
SDLK_PAGEUP = 280
SDLK_PAGEDOWN = 281
NON_SYNCED_ROW = "battleSmoothCamera"   # U6: a vanilla OXC Battlescape option that is NOT in the table

# ----- bounded waits -----
STATE_S = 5.0     # a menu transition reaches the next top state
APPLY_S = 5.0     # an apply lands on both machines
HELD_S = 3.0      # a held request reaches the host queue
MENU_S = 60       # bring-up / disconnect timing
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


def sos(gc):
    """synced_options_state (PR-13) of one machine, minus the reply's `ok`."""
    r = gc.cmd({"cmd": "synced_options_state"})
    return {k: v for k, v in r.items() if k != "ok"}


def adv(gc):
    """The `advanced` view (S-B.1): {open, scroll, visibleRows, rows:[{row,name,value,id,prefixed,line,visible,wx,wy}]}."""
    return sos(gc).get("advanced") or {}


def adv_rows(a):
    return a.get("rows") or []


def row_by_id(a, oid):
    return next((r for r in adv_rows(a) if r.get("id") == oid), None)


def chat(st):
    return [(m.get("player"), m.get("text")) for m in (st.get("chat") or [])]


def new_lines(before, after):
    b, a = chat(before), chat(after)
    return a[len(b):] if a[:len(b)] == b else a


def word(oid, v):
    return str(int(v)) if oid in INT_IDS else ("YES" if v else "NO")


def line(player, oid, v):
    return (SYSTEM, f"{player} changed {DESC[oid]} to {word(oid, v)}")


def norm_raw(s):
    if s == "true":
        return True
    if s == "false":
        return False
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


def read_cfg(gc):
    """The 15 ids of this machine's options.cfg, parsed (the engine's reader takes the FIRST key; F4982: compare
    parsed values, never bytes - a quit rewrites `language`)."""
    with open(os.path.join(gc.user_dir, "options.cfg"), "r", encoding="utf-8") as f:
        text = f.read()
    out = {}
    for i in IDS:
        hits = re.findall(r"^\s*" + i + r":\s*(\S+)\s*$", text, re.M)
        out[i] = norm_raw(hits[0]) if hits else None
    return out


def diff(a, b):
    a, b = a or {}, b or {}
    return {k: (a.get(k), b.get(k)) for k in IDS if a.get(k) != b.get(k)}


def top_is(gc, name):
    return (session.top_state(gc) or "").endswith(name)


# ===================== menu driving (the proven T0-1 recipe) =====================


def buttons(gc):
    lw = gc.cmd({"cmd": "list_widgets"})
    return lw.get("state"), [w for w in lw.get("widgets", []) if w.get("interactive") and "text" in w]


def click_exact(gc, caption, ev, timeout=STATE_S):
    """click_widget on the visible, un-hidden TextButton whose caption is exactly `caption` (nth = its position
    among click_widget's substring matches). A popup window hides its surfaces until it opens (P8b SC-7)."""
    def ready():
        st, bs = buttons(gc)
        cands = [w for w in bs if w.get("visible") and caption.lower() in str(w.get("text", "")).lower()]
        exact = [i for i, w in enumerate(cands) if str(w.get("text", "")).strip().upper() == caption.upper()]
        if len(exact) == 1 and not cands[exact[0]].get("hidden"):
            return {"state": st, "nth": exact[0]}
        return None
    got, waited = wait_until(ready, timeout)
    if not got:
        st, bs = buttons(gc)
        ev.setdefault("clickFail", {})[caption] = {"state": st,
            "buttons": [{k: w.get(k) for k in ("text", "visible", "hidden")} for w in bs]}
        return False
    nth = buttons(gc)
    # recompute nth at click time (list is stable while the popup is open)
    st, bs = buttons(gc)
    cands = [w for w in bs if w.get("visible") and caption.lower() in str(w.get("text", "")).lower()]
    exact = [i for i, w in enumerate(cands) if str(w.get("text", "")).strip().upper() == caption.upper()]
    if len(exact) != 1:
        ev.setdefault("clickFail", {})[caption] = {"state": st, "ambiguous": [w.get("text") for w in cands]}
        return False
    r = gc.cmd({"cmd": "click_widget", "match": caption, "nth": exact[0]})
    return bool(r.get("ok")) and str(r.get("text", "")).strip().upper() == caption.upper()


def open_advanced_battle(gc, ev, tag):
    """BattlescapeState -> keyBattleOptions -> GAME OPTIONS -> ADVANCED (OXC tab). Returns True at OptionsAdvancedState."""
    k = read_key(gc.user_dir, "keyBattleOptions")
    gc.ok({"cmd": "inject_input", "kind": "key", "key": k})
    ok, _ = wait_until(lambda: top_is(gc, "PauseState"), STATE_S)
    ev[tag + "_pause"] = (ok, session.top_state(gc))
    if not ok:
        return False
    if not click_exact(gc, "GAME OPTIONS", ev):
        return False
    ok, _ = wait_until(lambda: top_is(gc, "OptionsBattlescapeState"), STATE_S)
    if not ok:
        return False
    if not click_exact(gc, "ADVANCED", ev):
        return False
    ok, _ = wait_until(lambda: top_is(gc, "OptionsAdvancedState"), STATE_S)
    ev[tag + "_advanced"] = (ok, session.top_state(gc))
    return ok


def close_advanced_battle(gc, ev, tag):
    """OptionsAdvancedState -Cancel-> PauseState -Cancel-> BattlescapeState (T0-1 F4987)."""
    if not top_is(gc, "OptionsAdvancedState"):
        return top_is(gc, "BattlescapeState")
    click_exact(gc, "CANCEL", ev)
    wait_until(lambda: top_is(gc, "PauseState"), STATE_S)
    click_exact(gc, "CANCEL", ev)
    ok, _ = wait_until(lambda: top_is(gc, "BattlescapeState"), STATE_S)
    ev[tag + "_closed"] = (ok, session.top_state(gc))
    return ok


def open_advanced_mainmenu(gc, ev, tag):
    """MainMenuState -> OPTIONS -> ADVANCED (OXC tab). Role None (U1 SP control)."""
    if not click_exact(gc, "Options", ev):
        return False
    ok, _ = wait_until(lambda: top_is(gc, "OptionsVideoState"), STATE_S)
    ev[tag + "_video"] = (ok, session.top_state(gc))
    if not ok:
        return False
    if not click_exact(gc, "ADVANCED", ev):
        return False
    ok, _ = wait_until(lambda: top_is(gc, "OptionsAdvancedState"), STATE_S)
    ev[tag + "_advanced"] = (ok, session.top_state(gc))
    return ok


def close_advanced_mainmenu(gc, ev, tag):
    """OptionsAdvancedState -Cancel-> MainMenuState (the options sit directly on the main menu)."""
    if not top_is(gc, "OptionsAdvancedState"):
        return top_is(gc, "MainMenuState")
    click_exact(gc, "CANCEL", ev)
    ok, _ = wait_until(lambda: top_is(gc, "MainMenuState"), STATE_S)
    ev[tag + "_closed"] = (ok, session.top_state(gc))
    return ok


def scroll_to_row(gc, oid):
    """PAGEUP/PAGEDOWN until the oid row reports visible; returns (row, advancedView, presses) or (None, adv, n)."""
    a = adv(gc)
    bound = len(adv_rows(a)) + 4
    for n in range(bound + 1):
        a = adv(gc)
        r = row_by_id(a, oid)
        if r is None:
            return None, a, n
        if r.get("visible"):
            return r, a, n
        key = SDLK_PAGEDOWN if (r.get("line") or 0) >= (a.get("scroll") or 0) else SDLK_PAGEUP
        gc.ok({"cmd": "inject_input", "kind": "key", "key": key})
        time.sleep(0.1)
    return None, adv(gc), bound


def click_row(gc, oid, button="left"):
    """Scroll the oid row into view and push a real SDL click at its first-line centre (wx/wy). Returns the row dict."""
    r, a, presses = scroll_to_row(gc, oid)
    if not r:
        return None, {"presses": presses, "scroll": a.get("scroll"), "rows": len(adv_rows(a))}
    req = {"cmd": "inject_input", "kind": "click", "x": r["wx"], "y": r["wy"]}
    if button != "left":
        req["button"] = button
    gc.ok(req)
    time.sleep(0.15)   # let Game::run's event loop consume the click (mouseOver + mouseClick)
    return r, {"presses": presses, "wx": r["wx"], "wy": r["wy"], "scroll": a.get("scroll")}


# ===================== row bookkeeping =====================


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
        self.session = dict(OWN_HOST)   # the host's table is the session table (D134)
        self.seated = {}
        self.bstate0 = None


# ===================== guards (S-A) =====================


def guard_file(r, x):
    d = {m: diff(read_cfg(gc), x.own_file.get(m)) for m, gc in (("host", x.h), ("client", x.c))}
    r.cell("g_file", not d["host"] and not d["client"], f"options.cfg differs from OWN_FILE {d}")


def guard_battle(r, x):
    try:
        session.wait_host_idle(x.h, x.c)
    except Exception as e:
        r.cell("g_idle", False, short(e))
    eh, ec = event_state(x.h), event_state(x.c)
    r.cell("g_desync", eh.get("desyncSeen") is False and ec.get("desyncSeen") is False,
           f"desyncSeen host {eh.get('desyncSeen')} client {ec.get('desyncSeen')}")
    r.cell("g_bstate", ec.get("coopClientBStatePushes") == x.bstate0,
           f"client coopClientBStatePushes {ec.get('coopClientBStatePushes')} (battle start {x.bstate0})")
    try:
        assert_hash_clean(x.h, x.c, full=True, what=f"{r.rid}")
        r.cell("g_hash", True)
    except AssertionError as e:
        r.cell("g_hash", False, short(e))


def wait_versions(x, want):
    return wait_until(lambda: sos(x.h).get("version") == want and sos(x.c).get("version") == want, APPLY_S)


# ===================== rows =====================


def row_u1(r, x):
    """SP control: host at the main menu (role None). No prefix; a vanilla local flip; Cancel restores. Passes on
    both builds (role None never prefixes and never diverts)."""
    oid = "battleInstantGrenade"
    ev = r.ev
    opened = open_advanced_mainmenu(x.h, ev, "open")
    r.cell("opened", opened, "did not reach OptionsAdvancedState from the main menu")
    if not opened:
        return
    a0 = adv(x.h)
    s0 = sos(x.h)
    ev["role"] = s0.get("role")
    ev["active"] = s0.get("active")
    ev["advOpen"] = a0.get("open")
    ev["prefixedRows"] = [rw.get("id") for rw in adv_rows(a0) if rw.get("prefixed")]
    r.cell("role_none", s0.get("role") == "None" and s0.get("active") is False,
           f"role {s0.get('role')} active {s0.get('active')}")
    r.cell("no_prefix", not any(rw.get("prefixed") for rw in adv_rows(a0)),
           f"prefixed rows at the main menu {ev['prefixedRows']}")
    v0 = (s0.get("values") or {}).get(oid)
    rb, click = click_row(x.h, oid)
    ev["click"] = click
    if rb is None:
        r.cell("flip", False, f"could not click the {oid} row {click}")
        close_advanced_mainmenu(x.h, ev, "close")
        return
    ev["valueBefore"] = rb.get("value")
    s1 = sos(x.h)
    ra = row_by_id(adv(x.h), oid)
    ev["valueAfter"] = ra.get("value") if ra else None
    ev["globalBefore"], ev["globalAfter"] = v0, (s1.get("values") or {}).get(oid)
    r.cell("flip", ra is not None and ra.get("value") != rb.get("value")
           and (s1.get("values") or {}).get(oid) == (not v0),
           f"row {rb.get('value')}->{ev['valueAfter']}, global {v0}->{ev['globalAfter']} (want flipped)")
    closed = close_advanced_mainmenu(x.h, ev, "close")
    r.cell("closed", closed, f"did not return to the main menu (top {session.top_state(x.h)})")
    s2 = sos(x.h)
    ev["globalRestored"] = (s2.get("values") or {}).get(oid)
    r.cell("restore", (s2.get("values") or {}).get(oid) == v0,
           f"global after Cancel {ev['globalRestored']} (want the boot value {v0})")


def read_tab(gc):
    """Collect {id: prefixed} for identified rows of the current tab, plus the prefixed ids and any extra prefixes."""
    a = adv(gc)
    rows = [rw for rw in adv_rows(a) if rw.get("id") and rw.get("id") != "?"]
    present = {rw["id"] for rw in rows}
    prefixed = {rw["id"] for rw in rows if rw.get("prefixed")}
    extra = {rw["id"] for rw in rows if rw.get("prefixed") and rw["id"] not in TABLE_IDS}  # W2-P10 PX-7: 29-id table
    hidden = any(rw.get("id") == HIDDEN_ID for rw in adv_rows(a))
    return {"present": present, "prefixed": prefixed, "extra": extra, "hidden": hidden,
            "nrows": len(adv_rows(a))}


def row_u2(r, x):
    """Prefix: in battle, both machines, OXC then OXCE tab. Exactly the table ids are prefixed (S-B.2); none at red."""
    ev = r.ev
    for mname, gc in (("host", x.h), ("client", x.c)):
        if not open_advanced_battle(gc, ev, mname):
            r.cell(f"{mname}_open", False, f"{mname} did not reach the Advanced screen")
            continue
        oxc = read_tab(gc)
        ok, _ = wait_until(lambda: any(rw.get("id") in OXCE_TAB_IDS for rw in adv_rows(adv(gc))), STATE_S) \
            if click_exact(gc, "OXCE", ev) else (False, 0)
        oxce = read_tab(gc)
        ev[mname] = {"oxc": {k: sorted(v) if isinstance(v, set) else v for k, v in oxc.items()},
                     "oxce": {k: sorted(v) if isinstance(v, set) else v for k, v in oxce.items()},
                     "tabSwitched": ok}
        close_advanced_battle(gc, ev, mname)
        r.cell(f"{mname}_present", OXC_TAB_IDS <= oxc["present"] and OXCE_TAB_IDS <= oxce["present"],
               f"missing rows OXC {sorted(OXC_TAB_IDS - oxc['present'])} OXCE {sorted(OXCE_TAB_IDS - oxce['present'])}")
        r.cell(f"{mname}_oxc_prefixed", oxc["prefixed"] == OXC_TAB_IDS,
               f"OXC-tab prefixed {sorted(oxc['prefixed'])} (want {sorted(OXC_TAB_IDS)})")
        r.cell(f"{mname}_oxce_prefixed", oxce["prefixed"] == OXCE_TAB_IDS,
               f"OXCE-tab prefixed {sorted(oxce['prefixed'])} (want {sorted(OXCE_TAB_IDS)})")
        r.cell(f"{mname}_no_extra", not oxc["extra"] and not oxce["extra"],
               f"non-table rows prefixed OXC {sorted(oxc['extra'])} OXCE {sorted(oxce['extra'])}")
        r.cell(f"{mname}_hidden_absent", not oxc["hidden"] and not oxce["hidden"],
               f"a visible row for the hidden id {HIDDEN_ID}")
    guard_battle(r, x)
    guard_file(r, x)


def row_u3(r, x):
    """Client click: host ADVANCED open (scrolled to the row) + hold; client left-clicks its battleExplosionHeight
    row. S-B.2: diverted, row keeps the shared value until it lands, host screen refreshes live, chat line.
    S-B.1 (red): the client flips its own global at once, nothing reaches the host, no chat."""
    oid = "battleExplosionHeight"
    ev = r.ev
    if not open_advanced_battle(x.h, ev, "host"):
        r.cell("setup", False, "host did not open the Advanced screen")
        return
    hr, _, _ = scroll_to_row(x.h, oid)
    s_h = (adv(x.h).get("scroll"))
    if not open_advanced_battle(x.c, ev, "client"):
        r.cell("setup", False, "client did not open the Advanced screen")
        close_advanced_battle(x.h, ev, "host")
        return
    cr, _, _ = scroll_to_row(x.c, oid)
    hold = x.h.cmd({"cmd": "synced_apply_hold", "on": True})
    ev["setup"] = {"hostScroll": s_h, "hostRowVisible": bool(hr and hr.get("visible")),
                   "clientRowVisible": bool(cr and cr.get("visible")), "hold": hold}
    r.cell("setup", bool(hr and hr.get("visible")) and bool(cr and cr.get("visible"))
           and hold.get("holdArmed") is True, f"setup {ev['setup']}")
    h0, c0 = sos(x.h), sos(x.c)
    old = (c0.get("values") or {}).get(oid)
    want_new = old + 1 if old is not None else 1
    _, click = click_row(x.c, oid)        # the client clicks its own row
    ev["click"] = click
    time.sleep(0.3)
    c1, h1 = sos(x.c), sos(x.h)
    ev["heldClient"] = {k: c1.get(k) for k in ("values", "clicksDiverted", "inFlight", "requestsSent")}
    ev["heldHostPending"] = h1.get("pending")
    cflight = [f.get("id") for f in (c1.get("inFlight") or [])]
    r.cell("held_client_unchanged",
           (c1.get("values") or {}).get(oid) == old and (c1.get("clicksDiverted") or 0) >= 1
           and oid in cflight and len(h1.get("pending") or []) == 1,
           f"while held: client {oid} {(c1.get('values') or {}).get(oid)} (want {old}), clicksDiverted "
           f"{c1.get('clicksDiverted')}, client inFlight {cflight}, host pending {h1.get('pending')}")
    rel = x.h.cmd({"cmd": "synced_apply_hold", "on": False})
    ev["release"] = rel
    ok, secs = wait_versions(x, (h0.get("version") or 0) + 1)
    h2, c2 = sos(x.h), sos(x.c)
    x.session[oid] = want_new
    ev["afterReleaseWaitOk"], ev["afterReleaseS"] = ok, secs
    ev["afterHost"] = {k: h2.get(k) for k in ("values", "version")}
    ev["afterClient"] = {k: c2.get(k) for k in ("values", "version")}
    r.cell("applied", (h2.get("values") or {}).get(oid) == want_new and (c2.get("values") or {}).get(oid) == want_new
           and h2.get("version") == (h0.get("version") or 0) + 1 and c2.get("version") == h2.get("version"),
           f"after release: host {oid} {(h2.get('values') or {}).get(oid)} client {(c2.get('values') or {}).get(oid)} "
           f"(want {want_new}); versions host {h2.get('version')} client {c2.get('version')}")
    hrow = row_by_id(h2.get("advanced") or {}, oid)
    ev["hostRowAfter"] = hrow
    ev["hostScrollAfter"] = (h2.get("advanced") or {}).get("scroll")
    r.cell("host_refresh", hrow is not None and hrow.get("value") == str(want_new)
           and (h2.get("advanced") or {}).get("scroll") == s_h,
           f"host open screen row {hrow.get('value') if hrow else None} (want {want_new}), scroll "
           f"{(h2.get('advanced') or {}).get('scroll')} (want {s_h})")
    want_line = [line(c0.get("localName"), oid, want_new)]
    nh, nc = new_lines(h0, h2), new_lines(c0, c2)
    r.cell("chat", nh == want_line and nc == want_line, f"new chat host {nh} client {nc} (want {want_line})")
    close_advanced_battle(x.c, ev, "client")
    close_advanced_battle(x.h, ev, "host")
    guard_battle(r, x)
    guard_file(r, x)


def row_u4(r, x):
    """Host double-click + in-flight (Q9 a): host hold; two host left clicks on weaponSelfDestruction; release.
    S-B.2: one divert + one ignored-in-flight, one apply, one chat. S-B.1 (red): two local flips (back to start)."""
    oid = "weaponSelfDestruction"
    ev = r.ev
    if not open_advanced_battle(x.h, ev, "host"):
        r.cell("setup", False, "host did not open the Advanced screen")
        return
    hr, _, _ = scroll_to_row(x.h, oid)
    hold = x.h.cmd({"cmd": "synced_apply_hold", "on": True})
    ev["setup"] = {"rowVisible": bool(hr and hr.get("visible")), "hold": hold}
    r.cell("setup", bool(hr and hr.get("visible")) and hold.get("holdArmed") is True, f"setup {ev['setup']}")
    h0 = sos(x.h)
    old = (h0.get("values") or {}).get(oid)
    want_new = 0 if old else 1
    click_row(x.h, oid)
    time.sleep(0.1)
    click_row(x.h, oid)                 # the in-flight-ignored second click
    time.sleep(0.3)
    h1 = sos(x.h)
    ev["held"] = {k: h1.get(k) for k in ("values", "clicksDiverted", "clicksIgnoredInFlight", "pending", "inFlight")}
    r.cell("in_flight", (h1.get("clicksDiverted") or 0) == 1 and (h1.get("clicksIgnoredInFlight") or 0) == 1
           and len(h1.get("pending") or []) == 1,
           f"while held: clicksDiverted {h1.get('clicksDiverted')} clicksIgnoredInFlight "
           f"{h1.get('clicksIgnoredInFlight')} pending {h1.get('pending')}")
    rel = x.h.cmd({"cmd": "synced_apply_hold", "on": False})
    ev["release"] = rel
    ok, secs = wait_versions(x, (h0.get("version") or 0) + 1)
    h2, c2 = sos(x.h), sos(x.c)
    x.session[oid] = bool(want_new)
    ev["afterHost"] = {k: h2.get(k) for k in ("values", "version", "applied")}
    new = [a for a in (h2.get("applied") or []) if (a.get("version") or 0) > (h0.get("version") or 0)]
    r.cell("applied", len(new) == 1 and new[0].get("id") == oid and bool(new[0].get("value")) == bool(want_new)
           and (h2.get("values") or {}).get(oid) == bool(want_new)
           and (c2.get("values") or {}).get(oid) == bool(want_new),
           f"ring +{len(new)} {new}; host {oid} {(h2.get('values') or {}).get(oid)} client "
           f"{(c2.get('values') or {}).get(oid)} (want {bool(want_new)})")
    want_line = [line(h0.get("localName"), oid, bool(want_new))]
    nh, nc = new_lines(h0, h2), new_lines(x._u4_c0, c2)
    ev["chat"] = {"host": nh, "client": nc}
    r.cell("chat", nh == want_line and nc == want_line, f"new chat host {nh} client {nc} (want {want_line})")
    close_advanced_battle(x.h, ev, "host")
    guard_battle(r, x)
    guard_file(r, x)


def row_u5(r, x):
    """Cancel: ADVANCED Cancel on both; then options_save on both. U3/U4's undiverted flips left the machines
    unequal at red (S-B.2's divert keeps them equal); the save guard keeps the file at OWN_FILE in both."""
    ev = r.ev
    for mname, gc in (("host", x.h), ("client", x.c)):
        if open_advanced_battle(gc, ev, mname):
            close_advanced_battle(gc, ev, mname)   # Cancel reloads (guarded) and returns to the battle
    h1, c1 = sos(x.h), sos(x.c)
    ev["afterCancel"] = {"host": h1.get("values"), "client": c1.get("values"), "session": x.session}
    r.cell("values_equal", not diff(h1.get("values"), c1.get("values")),
           f"host vs client values after Cancel {diff(h1.get('values'), c1.get('values'))}")
    r.cell("values_session", not diff(h1.get("values"), x.session) and not diff(c1.get("values"), x.session),
           f"vs session: host {diff(h1.get('values'), x.session)} client {diff(c1.get('values'), x.session)}")
    sh, sc = x.h.cmd({"cmd": "options_save"}), x.c.cmd({"cmd": "options_save"})
    ev["save"] = {"host": sh, "client": sc}
    files = {"host": read_cfg(x.h), "client": read_cfg(x.c)}
    d = {m: diff(files[m], x.own_file.get(m)) for m in files}
    ev["files"] = files
    r.cell("file_own", not d["host"] and not d["client"], f"options.cfg vs OWN_FILE after options_save {d}")
    guard_battle(r, x)


def read_raw(gc, key):
    """A raw (non-table) option value parsed from this machine's options.cfg."""
    with open(os.path.join(gc.user_dir, "options.cfg"), "r", encoding="utf-8") as f:
        m = re.search(r"^\s*" + key + r":\s*(\S+)\s*$", f.read(), re.M)
    return norm_raw(m.group(1)) if m else None


def row_u6(r, x):
    """OK (T0-1 SAFE): host hold; toggle battleSmoothCamera (not synced) + battleInstantGrenade (synced); OK.
    S-B.2: the save writes battleSmoothCamera but holds the synced ids at OWN, and the divert keeps the in-memory
    session value unchanged. S-B.1 (red): the synced row's local flip changed the in-memory session value."""
    oid = "battleInstantGrenade"
    ev = r.ev
    if not open_advanced_battle(x.h, ev, "host"):
        r.cell("setup", False, "host did not open the Advanced screen")
        return
    hold = x.h.cmd({"cmd": "synced_apply_hold", "on": True})   # a diverted request must not apply before OK
    smooth0 = read_raw(x.h, NON_SYNCED_ROW)
    smooth_row, _, _ = scroll_to_row(x.h, NON_SYNCED_ROW)
    ev["setup"] = {"hold": hold, "smoothRowFound": smooth_row is not None, "smoothFile0": smooth0}
    r.cell("setup", hold.get("holdArmed") is True and smooth_row is not None and smooth0 is not None,
           f"setup {ev['setup']}")
    if smooth_row is None or smooth0 is None:
        x.h.cmd({"cmd": "synced_apply_hold", "on": False})
        return
    sess_before = dict(sos(x.h).get("values") or {})
    click_row(x.h, NON_SYNCED_ROW)          # a vanilla non-synced toggle: reaches the file through OK
    time.sleep(0.1)
    click_row(x.h, oid)                     # the synced toggle: diverted in S-B.2, a local flip in S-B.1
    time.sleep(0.2)
    # press OK on the Advanced screen -> Options::save() (guarded) + restart(OPT_BATTLESCAPE) (T0-1 SAFE)
    okc = click_exact(x.h, "OK", ev)
    ev["okClicked"] = okc
    rb, secs = wait_until(lambda: (session.top_state(x.h) or "").endswith("BattlescapeState"), 12.0, 0.1)
    ev["rebuiltOk"], ev["rebuiltS"] = rb, secs
    time.sleep(0.5)
    sfile = read_cfg(x.h)
    smooth1 = read_raw(x.h, NON_SYNCED_ROW)
    s2 = sos(x.h)
    ev["afterOK"] = {"values": s2.get("values"), "fileSynced": sfile, "smoothFile": [smooth0, smooth1]}
    r.cell("file_smoothcam", isinstance(smooth1, bool) and smooth1 == (not smooth0),
           f"battleSmoothCamera file {smooth0} -> {smooth1} (want flipped)")
    r.cell("file_synced_own", not diff(sfile, x.own_file.get("host")),
           f"options.cfg synced ids vs OWN_FILE {diff(sfile, x.own_file.get('host'))}")
    r.cell("session_unchanged", not diff(s2.get("values"), sess_before),
           f"in-memory synced values moved by the OK path {diff(sess_before, s2.get('values'))}")
    x.h.cmd({"cmd": "synced_apply_hold", "on": False})
    guard_battle(r, x)
    guard_file(r, x)


# ===================== runner =====================


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


ROWS = (("U2", row_u2), ("U3", row_u3), ("U4", row_u4), ("U5", row_u5), ("U6", row_u6))


def main():
    t0 = time.time()
    host = GameClient("host", CTRL_LABELS[0], make_user_dir("w2p9_ui_host", options=HOST_OPTS))
    client = GameClient("client", CTRL_LABELS[1], make_user_dir("w2p9_ui_client", options=CLIENT_OPTS))
    x = Ctx(host, client)
    results = {}
    order = ["U1"] + [rid for rid, _ in ROWS]
    try:
        try:
            host.spawn(); host.connect()                 # the host at the main menu (role None) for U1
            run_one("U1", row_u1, x, results)            # SP control BEFORE hosting
            client.spawn(); client.connect()
            raw.skirmish_host(host, LOBBY_PORT)
            raw.skirmish_client_at_browser(client)
            client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": LOBBY_PORT, "player": raw.CLIENT_PLAYER})
            host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
            client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
            host.ok({"cmd": "profile_ok"})
            client.ok({"cmd": "profile_ok"})
            host.wait_for("start offered", lambda: raw.lobby(host).get("buttonVisible") or None)
            x.own_file = {"host": read_cfg(host), "client": read_cfg(client)}    # OWN_FILE (F4983, PR-14)
            print(f"[w2p9-sb-ui] bring-up {time.time() - t0:.1f}s OWN_FILE {x.own_file}", flush=True)
            session.drive_to_battlescape(host, client, x.seated, seat_count=2)
            x.bstate0 = event_state(client).get("coopClientBStatePushes")
            x._u4_c0 = sos(client)   # chat baseline before U4's host apply (used by row_u4's client chat delta)
        except Exception as e:
            for rid in order:
                if rid not in results:
                    results[rid] = False
                    print(f"FAIL {rid}: pre (bring-up/battle) {short(e)}", flush=True)
        else:
            for rid, fn in ROWS:
                if rid == "U4":
                    x._u4_c0 = sos(client)   # capture the client chat baseline right before U4
                run_one(rid, fn, x, results)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p9-sb-ui] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n in order if results.get(n)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_w2_synced_options_ui: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
