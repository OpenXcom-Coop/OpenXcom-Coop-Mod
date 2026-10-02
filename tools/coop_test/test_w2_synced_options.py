"""W2-P9 S-A - test_w2_synced_options.py: one set of battle rules per co-op session (owner D134; D160 a, D161 a,
D163 a, D165 a). Spec: docs rewrite/prompts/w2p9_synced_options.md as re-pinned by AMENDMENT P9-1 (section 3
PR-1..PR-14, section 4.1 S-A, section 5) and its P9-1 RULINGS. Constants: docs rewrite/w2p9-task0/CONSTANTS.md
(TASK 0 `w2p9-t0`, F4980-F4989).

Before S-A.2 each machine reads its OWN copy of the 15 synced options (11 OXC + 3 OXCE visible rows + the hidden
unload option): the host's values decide the battle while the second player's screens follow its own. After it the
host's globals are the session table: a joiner takes them silently (`synced_options_table` after the INIT_SERVER
reply), every battle_offer re-asserts them (`hostRules`), a change goes through the host's queue and applies only
between actions (coopBattleQuiescent), every machine writes the shared value into its in-memory option and posts a
"System" chat line, and leaving restores each player's own values; options.cfg never receives a shared value.

ONE boot (PR-14): host user dir {battleInstantGrenade true, battleExplosionHeight 2, sneakyAI true}, client
{battleInstantGrenade false, battleExplosionHeight 0, alienBleeding true}; repro_atom_walk.bring_up_lobby on lobby
key 47240; OWN_FILE = each machine's options.cfg read after bring_up_lobby returns (F4983), the 15 ids parsed. Rows
in this order (O7 runs before O6):

| row | fixture | GREEN cells | RED cells (S-A.1 build) |
|---|---|---|---|
| O1 | the bring-up, at the lobby | active true + role Host/Client; client values == host values == the host's boot table; client own == its boot table; client tablesApplied 1, lastTableFrom "join"; versions equal (0); no chat line | client values == its own boot values (client_values), active false (active); own null (client_own), no table (table) |
| O2 | lobby: client synced_option_request battleInstantGrenade false | host ring +1 {applied, arrivedWhileBusy false, player = client localName}; both tables == the session table; version +1 on both; client inFlight empty; one chat line each "System" / "<client> changed Instant grenades to NO" | host applied empty, values unchanged (host_applied, values, version, chat) |
| O3 | session.drive_to_battlescape(seat_count=2); host request battleExplosionHeight 3 | before: client tablesApplied 2, lastTableFrom "offer", versions equal (F4733); after: both tables == session (height 3), version +1, one chat line each "<host> changed Explosion height to 3" | client tablesApplied 0 (offer_table), host height unchanged (values, version, chat) |
| O4 | T0-2's blocker (seat-1 index 0, the R2-P7 helpers); while it runs: client request alienBleeding true, ONE sample | at the sample: host pending holds it with arrivedWhileBusy true, host alienBleeding false, the blocker still open; after wait_blocker_closed: the ring entry's afterSeq >= endSeq, heldFrames >= 1, both tables == session | host pending empty at the sample (pending); then no ring entry (ring), values differ (values) |
| O5 | host synced_apply_hold on; client sneakyAI false; host pending length 1; host sneakyAI true; hold off | pending order [client's, host's]; two ring entries in that order, versions n+1, n+2; both tables == session (sneakyAI true); two chat lines in that order on both | host pending empty under the hold (pending1, order); then ring, values, chat |
| O7 | while values != own on both: options_save on both | the 15 ids in each options.cfg == its OWN_FILE; values unchanged in memory | precondition "values != own on both" fails (pre) |
| O6 | client disconnect_to_menu; then host disconnect_to_menu | client values == its OWN_FILE, own null, active false; host values and version unchanged until its own leave, then == its OWN_FILE | precondition "client values != own" fails (pre) |

Guards: every row - the 15 ids in each options.cfg == OWN_FILE (draft STOP-IF 4); in battle (O3, O4, O5, O7) -
desyncSeen false on both, the client's coopClientBStatePushes unchanged since the battle started, hash_now full
equal after session.wait_host_idle. The guards pass on the red build.

WV-D99 / WV-D100: one run is the result; every row runs after a failure; every wait is bounded. Each row prints
ONE "EVIDENCE <id>:" line (both machines' synced_options_state) and then "PASS <id>" or "FAIL <id>: <cells>".
Exit 0 only when every row passes, 2 otherwise. WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_synced_options.py
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
import test_rw_retry_cancel as rc   # PR-14: qualifying_actor, stage_blocker, start_autoshot_blocker, wait_blocker_closed

# ----- TASK 0 constants (docs rewrite/w2p9-task0/CONSTANTS.md, the line named in each comment) -----
LOBBY_PORT = "47240"                 # LOBBY_PORT="47240" (PR-14; S26: 47240-47243 belong to P9)
CTRL_LABELS = (49240, 49241)         # GameClient labels (the control sockets are ephemeral)
HOST_OPTS = {"battleInstantGrenade": True, "battleExplosionHeight": 2, "sneakyAI": True}           # HOST_OPTS=
CLIENT_OPTS = {"battleInstantGrenade": False, "battleExplosionHeight": 0, "alienBleeding": True}   # CLIENT_OPTS=
BLOCKER_SEAT1_INDEX = 0              # BLOCKER actor = seat-1 index 0 (unit 8 / soldierId 8); BLOCKER_SEED=1 = rc's
WINDOW_MIN_S = 3.104                 # WINDOW helperReturn->hostClosed s = 3.104/3.455/3.533
PROBE_RTT_MS = 50                    # PROBE_RTT_MS ~50

# PR-1: the 15 table ids in table order; Options.cpp registrations (desktop branch): every bool false, both ints 0.
IDS = ["battleInstantGrenade", "battleExplosionHeight", "oxceEnableOffCentreShooting", "oxceUniformShootingSpread",
       "allowPsiStrengthImprovement", "allowPsionicCapture", "weaponSelfDestruction", "alienBleeding", "sneakyAI",
       "battleAutoEnd", "disableAutoEquip", "includePrimeStateInSavedLayout", "battleUFOExtenderAccuracy",
       "oxceReactionFireThreshold", "oxceInventoryUnloadFixedWeapons"]
INT_IDS = {"battleExplosionHeight", "oxceReactionFireThreshold"}
DEFAULTS = {i: (0 if i in INT_IDS else False) for i in IDS}
# OWN_FILE host = HOST_OPTS + other 12 ids False/0; OWN_FILE client = CLIENT_OPTS + other 12 False/0
OWN_HOST = dict(DEFAULTS, **HOST_OPTS)
OWN_CLIENT = dict(DEFAULTS, **CLIENT_OPTS)

# PR-9 / PR-10 / PR-14: the chat line, English literals (bin/common/Language/en-US.yml, STR_YES / STR_NO).
SYSTEM = "System"
DESC = {"battleInstantGrenade": "Instant grenades", "battleExplosionHeight": "Explosion height",
        "weaponSelfDestruction": "Alien weapon self-destruction", "sneakyAI": "Sneaky AI",
        "alienBleeding": "Alien bleeding"}

# ----- bounded waits (PROBE_RTT_MS ~50) -----
O4_ARRIVE_S = 1.0     # the client's request reaches the host's queue (20x the RTT; well inside WINDOW_MIN_S)
HOLD_ARRIVE_S = 3.0   # the client's request reaches the held host queue
APPLY_S = 5.0         # an apply lands on both machines
MENU_S = 60           # disconnect_to_menu reaches MainMenuState
DROP_S = 20           # the host raises its reconnect dialog after the client's leave (recorded only)
POLL = 0.05
COOP_DLG_WAIT_PLAYERS = 62   # test_spec16_pause_on_leave.py COOP_DLG_WAIT_PLAYERS


# ===================== small probes =====================


def short(e):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= 400 else s[:400] + "..."


def wait_until(pred, timeout, interval=POLL):
    t0 = time.time()
    while True:
        if pred():
            return True, round(time.time() - t0, 2)
        if time.time() - t0 >= timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)


def sos(gc):
    """synced_options_state (PR-13) of one machine, minus the reply's `ok`."""
    r = gc.cmd({"cmd": "synced_options_state"})
    return {k: v for k, v in r.items() if k != "ok"}


def chat(st):
    return [(m.get("player"), m.get("text")) for m in (st.get("chat") or [])]


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
    """The 15 ids of this machine's options.cfg, parsed (the engine's reader takes the FIRST key; so does this).
    Values compared parsed, never as bytes (F4982: a quit rewrites `language`)."""
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


class Row:
    """One row's failed and passed cells and its evidence."""

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
    """The one boot: both machines, OWN_FILE, the expected session table and the battle baselines."""

    def __init__(self, host, client):
        self.h, self.c = host, client
        self.own_file = {}
        self.session = dict(OWN_HOST)    # the host's table is the session table (D134)
        self.seated = {}
        self.bstate0 = None
        self.in_battle = False


# ===================== guards =====================


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
    """Both machines' version == want (the host applied it and the client applied its set)."""
    return wait_until(lambda: sos(x.h).get("version") == want and sos(x.c).get("version") == want, APPLY_S)


def new_lines(before, after):
    b, a = chat(before), chat(after)
    return a[len(b):] if a[:len(b)] == b else a


# ===================== rows =====================


def row_o1(r, x):
    hs, cs = sos(x.h), sos(x.c)
    r.ev.update(host=hs, client=cs, ownFile=x.own_file,
                t0_3={"clientValues": cs.get("values"), "clientBoot": OWN_CLIENT,
                      "chatMenuExists": {"host": hs.get("chatMenuExists"), "client": cs.get("chatMenuExists")}})
    r.cell("pre_ownfile", not diff(x.own_file.get("host"), OWN_HOST) and not diff(x.own_file.get("client"), OWN_CLIENT),
           f"OWN_FILE vs boot: host {diff(x.own_file.get('host'), OWN_HOST)} client "
           f"{diff(x.own_file.get('client'), OWN_CLIENT)}")
    r.cell("role", (hs.get("role"), cs.get("role")) == ("Host", "Client"), f"roles {hs.get('role')}/{cs.get('role')}")
    r.cell("active", hs.get("active") is True and cs.get("active") is True,
           f"active host {hs.get('active')} client {cs.get('active')}")
    r.cell("host_values", not diff(hs.get("values"), OWN_HOST), f"host values vs its boot {diff(hs.get('values'), OWN_HOST)}")
    r.cell("client_values", not diff(cs.get("values"), hs.get("values")),
           f"client values vs host {diff(cs.get('values'), hs.get('values'))}")
    r.cell("client_own", cs.get("own") is not None and not diff(cs.get("own"), OWN_CLIENT),
           f"client own {cs.get('own')}")
    r.cell("table", (cs.get("tablesApplied"), cs.get("lastTableFrom")) == (1, "join"),
           f"client tablesApplied {cs.get('tablesApplied')} lastTableFrom {cs.get('lastTableFrom')!r}")
    r.cell("version", cs.get("version") == hs.get("version") == 0,
           f"version host {hs.get('version')} client {cs.get('version')}")
    r.cell("chat", not chat(hs) and not chat(cs), f"chat host {chat(hs)} client {chat(cs)}")
    guard_file(r, x)


def row_o2(r, x):
    oid = "battleInstantGrenade"
    h0, c0 = sos(x.h), sos(x.c)
    resp = x.c.cmd({"cmd": "synced_option_request", "id": oid, "value": False})
    r.ev["request"] = resp
    ok, secs = wait_versions(x, (h0.get("version") or 0) + 1)
    h1, c1 = sos(x.h), sos(x.c)
    x.session[oid] = False
    r.ev.update(waitOk=ok, waitS=secs, hostBefore=h0, clientBefore=c0, host=h1, client=c1)
    new = [a for a in (h1.get("applied") or []) if (a.get("version") or 0) > (h0.get("version") or 0)]
    want = {"id": oid, "value": False, "result": "applied", "arrivedWhileBusy": False, "player": c0.get("localName")}
    r.cell("host_applied", len(new) == 1 and all(new[0].get(k) == v for k, v in want.items()),
           f"host ring entries after the request {new} (want one {want})")
    r.cell("values", not diff(h1.get("values"), x.session) and not diff(c1.get("values"), x.session),
           f"vs session: host {diff(h1.get('values'), x.session)} client {diff(c1.get('values'), x.session)}")
    r.cell("version", h1.get("version") == (h0.get("version") or 0) + 1 and c1.get("version") == (c0.get("version") or 0) + 1,
           f"version host {h0.get('version')}->{h1.get('version')} client {c0.get('version')}->{c1.get('version')}")
    r.cell("inflight", (c1.get("inFlight") or []) == [], f"client inFlight {c1.get('inFlight')}")
    want_line = [line(c0.get("localName"), oid, False)]
    nh, nc = new_lines(h0, h1), new_lines(c0, c1)
    r.cell("chat", nh == want_line and nc == want_line, f"new chat host {nh} client {nc} (want {want_line})")
    guard_file(r, x)


def row_o3(r, x):
    oid = "battleExplosionHeight"
    session.drive_to_battlescape(x.h, x.c, x.seated, seat_count=2)
    x.in_battle = True
    x.bstate0 = event_state(x.c).get("coopClientBStatePushes")
    h0, c0 = sos(x.h), sos(x.c)
    r.ev.update(hostBefore=h0, clientBefore=c0, bstate0=x.bstate0, soldierIds=x.seated.get("soldierIds"),
                t0_3={"chatMenuExistsInBattle": {"host": h0.get("chatMenuExists"), "client": c0.get("chatMenuExists")}})
    r.cell("offer_table", (c0.get("tablesApplied"), c0.get("lastTableFrom")) == (2, "offer"),
           f"client tablesApplied {c0.get('tablesApplied')} lastTableFrom {c0.get('lastTableFrom')!r}")
    r.cell("offer_version", c0.get("version") == h0.get("version"),
           f"version host {h0.get('version')} client {c0.get('version')}")
    resp = x.h.cmd({"cmd": "synced_option_request", "id": oid, "value": 3})
    r.ev["request"] = resp
    ok, secs = wait_versions(x, (h0.get("version") or 0) + 1)
    h1, c1 = sos(x.h), sos(x.c)
    x.session[oid] = 3
    r.ev.update(waitOk=ok, waitS=secs, host=h1, client=c1)
    r.cell("values", not diff(h1.get("values"), x.session) and not diff(c1.get("values"), x.session),
           f"vs session: host {diff(h1.get('values'), x.session)} client {diff(c1.get('values'), x.session)}")
    r.cell("version", h1.get("version") == (h0.get("version") or 0) + 1 and c1.get("version") == (c0.get("version") or 0) + 1,
           f"version host {h0.get('version')}->{h1.get('version')} client {c0.get('version')}->{c1.get('version')}")
    want_line = [line(h0.get("localName"), oid, 3)]
    nh, nc = new_lines(h0, h1), new_lines(c0, c1)
    r.cell("chat", nh == want_line and nc == want_line, f"new chat host {nh} client {nc} (want {want_line})")
    guard_battle(r, x)
    guard_file(r, x)


def row_o4(r, x):
    oid = "alienBleeding"
    sid = x.seated["soldierIds"][BLOCKER_SEAT1_INDEX]
    staged = session.stage_open_ground_actor(x.h, x.c, [sid], "w2p9_o4")
    r.ev["staged"] = {"unit": staged[0].get("id"), "tile": staged[1], "runDir": staged[2]}
    actor = rc.qualifying_actor(x.h, sid)
    if actor is None:
        r.ev["actorDump"] = [{k: u.get(k) for k in ("id", "soldierId", "faction", "coop", "x", "y", "z", "isOut")}
                             for u in session.battle_state(x.h).get("units", [])]
        r.cell("pre_actor", False, f"no client actor qualifies after staging soldier {sid} (FIXTURE-STOP)")
        return
    r.ev["actor"] = {k: actor.get(k) for k in ("id", "soldierId", "x", "y", "z", "coop")}
    blocker = rc.stage_blocker(x.h, x.c, actor["id"])
    r.ev["blocker"] = {k: blocker[k] for k in ("actor", "weapon", "ammo", "target")}
    h0, c0 = sos(x.h), sos(x.c)
    aid = rc.start_autoshot_blocker(x.h, x.c, blocker)
    t_ret = time.time()
    resp = x.c.cmd({"cmd": "synced_option_request", "id": oid, "value": True})
    ok, secs = wait_until(lambda: bool(sos(x.h).get("pending")), O4_ARRIVE_S)
    hs = sos(x.h)
    closed = [cc.get("actionId") for cc in (event_state(x.h).get("closedContexts") or [])]
    t_sample = round(time.time() - t_ret, 3)
    r.ev.update(request=resp, actionId=aid, arriveOk=ok, arriveS=secs, sampleAfterHelperS=t_sample,
                sampleHost=hs, sampleClosed=closed)
    r.cell("sample_open", aid not in closed, f"the blocker {aid} closed before the sample ({t_sample}s; {closed})")
    pend = [p for p in (hs.get("pending") or []) if p.get("id") == oid]
    r.cell("pending", len(pend) == 1 and pend[0].get("value") == True and pend[0].get("arrivedWhileBusy") is True,
           f"host pending at the sample {hs.get('pending')} (want one {oid} true, arrivedWhileBusy true)")
    r.cell("host_not_applied", (hs.get("values") or {}).get(oid) is False,
           f"host {oid} at the sample {(hs.get('values') or {}).get(oid)}")
    rec = rc.wait_blocker_closed(x.h, x.c, blocker, aid)
    ok2, secs2 = wait_versions(x, (h0.get("version") or 0) + 1)
    h1, c1 = sos(x.h), sos(x.c)
    x.session[oid] = True
    r.ev.update(closedRec=rec, waitOk=ok2, waitS=secs2, host=h1, client=c1)
    ent = [a for a in (h1.get("applied") or []) if (a.get("version") or 0) > (h0.get("version") or 0)]
    r.cell("ring", len(ent) == 1 and ent[0].get("id") == oid and (ent[0].get("afterSeq") or 0) >= rec["endSeq"]
           and (ent[0].get("heldFrames") or 0) >= 1,
           f"host ring entries {ent} (want one {oid} with afterSeq >= endSeq {rec['endSeq']}, heldFrames >= 1)")
    r.cell("values", not diff(h1.get("values"), x.session) and not diff(c1.get("values"), x.session),
           f"vs session: host {diff(h1.get('values'), x.session)} client {diff(c1.get('values'), x.session)}")
    guard_battle(r, x)
    guard_file(r, x)


def row_o5(r, x):
    oid = "sneakyAI"
    h0, c0 = sos(x.h), sos(x.c)
    n = h0.get("version") or 0
    hname, cname = h0.get("localName"), c0.get("localName")
    try:
        hold = x.h.cmd({"cmd": "synced_apply_hold", "on": True})
        r.cell("hold_lever", hold.get("ok") is True and hold.get("holdArmed") is True, f"hold on answered {hold}")
        rq1 = x.c.cmd({"cmd": "synced_option_request", "id": oid, "value": False})
        ok, secs = wait_until(lambda: len(sos(x.h).get("pending") or []) == 1, HOLD_ARRIVE_S)
        hs1 = sos(x.h)
        r.cell("pending1", len(hs1.get("pending") or []) == 1, f"host pending under the hold {hs1.get('pending')}")
        rq2 = x.h.cmd({"cmd": "synced_option_request", "id": oid, "value": True})
        hs2 = sos(x.h)
        order = [(p.get("id"), p.get("value"), p.get("player")) for p in (hs2.get("pending") or [])]
        want = [(oid, False, cname), (oid, True, hname)]
        r.cell("order", order == want, f"host pending before the release {order} (want {want})")
        r.ev.update(requests=[rq1, rq2], arriveOk=ok, arriveS=secs, pendingHeld1=hs1.get("pending"),
                    pendingHeld2=hs2.get("pending"))
    finally:
        rel = x.h.cmd({"cmd": "synced_apply_hold", "on": False})
        r.ev["release"] = rel
    ok2, secs2 = wait_versions(x, n + 2)
    h1, c1 = sos(x.h), sos(x.c)
    x.session[oid] = True
    r.ev.update(waitOk=ok2, waitS=secs2, host=h1, client=c1)
    ent = [(a.get("id"), a.get("value"), a.get("version"), a.get("player")) for a in (h1.get("applied") or [])
           if (a.get("version") or 0) > n]
    want_ring = [(oid, False, n + 1, cname), (oid, True, n + 2, hname)]
    r.cell("ring", ent == want_ring, f"host ring entries {ent} (want {want_ring})")
    r.cell("values", not diff(h1.get("values"), x.session) and not diff(c1.get("values"), x.session),
           f"vs session: host {diff(h1.get('values'), x.session)} client {diff(c1.get('values'), x.session)}")
    want_lines = [line(cname, oid, False), line(hname, oid, True)]
    nh, nc = new_lines(h0, h1), new_lines(c0, c1)
    r.cell("chat", nh == want_lines and nc == want_lines, f"new chat host {nh} client {nc} (want {want_lines})")
    guard_battle(r, x)
    guard_file(r, x)


def row_o7(r, x):
    hs, cs = sos(x.h), sos(x.c)
    r.ev.update(hostBefore=hs, clientBefore=cs)
    pre = {m: (st.get("own") is not None and bool(diff(st.get("values"), st.get("own"))))
           for m, st in (("host", hs), ("client", cs))}
    r.cell("pre", pre["host"] and pre["client"],
           f"values != own on both (host own {hs.get('own')}, client own {cs.get('own')})")
    sh, sc = x.h.cmd({"cmd": "options_save"}), x.c.cmd({"cmd": "options_save"})
    r.ev["save"] = {"host": sh, "client": sc}
    r.cell("save_lever", sh.get("saved") is True and sc.get("saved") is True, f"options_save host {sh} client {sc}")
    files = {"host": read_cfg(x.h), "client": read_cfg(x.c)}
    d = {m: diff(files[m], x.own_file.get(m)) for m in files}
    r.ev["files"] = files
    r.cell("files", not d["host"] and not d["client"], f"options.cfg vs OWN_FILE after options_save {d}")
    hs2, cs2 = sos(x.h), sos(x.c)
    r.ev.update(host=hs2, client=cs2)
    r.cell("memory", not diff(hs2.get("values"), hs.get("values")) and not diff(cs2.get("values"), cs.get("values")),
           f"values moved by the save: host {diff(hs.get('values'), hs2.get('values'))} client "
           f"{diff(cs.get('values'), cs2.get('values'))}")
    guard_battle(r, x)


def at_menu(gc):
    return (session.top_state(gc) or "").endswith("MainMenuState") or None


def row_o6(r, x):
    hs0, cs0 = sos(x.h), sos(x.c)
    r.ev.update(hostBefore=hs0, clientBefore=cs0)
    r.cell("pre", cs0.get("own") is not None and bool(diff(cs0.get("values"), cs0.get("own"))),
           f"client values != own before the leave (client own {cs0.get('own')})")
    x.c.ok({"cmd": "disconnect_to_menu"})
    x.c.wait_for("client at the main menu", lambda: at_menu(x.c), timeout=MENU_S)
    cs1 = sos(x.c)
    r.ev["clientAfterLeave"] = cs1
    r.cell("client_restore", not diff(cs1.get("values"), x.own_file.get("client")) and cs1.get("own") is None
           and cs1.get("active") is False,
           f"client after its leave: values vs OWN_FILE {diff(cs1.get('values'), x.own_file.get('client'))}, own "
           f"{cs1.get('own')}, active {cs1.get('active')}")
    saw, secs = wait_until(lambda: (lambda d: d.get("present") and d.get("code") == COOP_DLG_WAIT_PLAYERS)(
        x.h.cmd({"cmd": "coop_dialog_info"})), DROP_S, 0.2)
    hs1 = sos(x.h)
    r.ev.update(hostSawDrop=saw, hostSawDropS=secs, hostAfterClientLeave=hs1)
    r.cell("host_kept", not diff(hs1.get("values"), hs0.get("values")) and hs1.get("version") == hs0.get("version"),
           f"host after the client's leave: values moved {diff(hs0.get('values'), hs1.get('values'))}, version "
           f"{hs0.get('version')}->{hs1.get('version')}")
    x.h.ok({"cmd": "disconnect_to_menu"})
    x.h.wait_for("host at the main menu", lambda: at_menu(x.h), timeout=MENU_S)
    hs2 = sos(x.h)
    r.ev["hostAfterLeave"] = hs2
    r.cell("host_restore", not diff(hs2.get("values"), x.own_file.get("host")),
           f"host after its leave: values vs OWN_FILE {diff(hs2.get('values'), x.own_file.get('host'))}")
    guard_file(r, x)


# ===================== runner =====================


ROWS = (("O1", row_o1), ("O2", row_o2), ("O3", row_o3), ("O4", row_o4), ("O5", row_o5), ("O7", row_o7),
        ("O6", row_o6))


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
    host = GameClient("host", CTRL_LABELS[0], make_user_dir("w2p9_synced_host", options=HOST_OPTS))
    client = GameClient("client", CTRL_LABELS[1], make_user_dir("w2p9_synced_client", options=CLIENT_OPTS))
    x = Ctx(host, client)
    results = {}
    order = [rid for rid, _ in ROWS]
    try:
        try:
            raw.bring_up_lobby(host, client, LOBBY_PORT)
            x.own_file = {"host": read_cfg(host), "client": read_cfg(client)}   # OWN_FILE (F4983, PR-14)
            print(f"[w2p9-sa] bring-up {time.time() - t0:.1f}s OWN_FILE {x.own_file}", flush=True)
        except Exception as e:
            for rid in order:
                results[rid] = False
                print(f"FAIL {rid}: pre (bring-up) {short(e)}", flush=True)
        else:
            for rid, fn in ROWS:
                run_one(rid, fn, x, results)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p9-sa] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n in order if results.get(n)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_w2_synced_options: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
