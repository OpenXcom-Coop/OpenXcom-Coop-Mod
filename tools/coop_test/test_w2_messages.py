"""W2-P6a S-M - test_w2_messages.py: the battle messages on both machines (owner
D132: you get vanilla's boxes for your own soldiers; a message about your
partner's soldier is a short notice that fades by itself, and the host no longer
pauses the shared battle for it; D170 (a): vanilla boxes on both machines for a
unit no player owns), plus the stale entry notice F1270 - spec docs
rewrite/prompts/w2p6_display_two.md: `## P6a PINNED STAGE TEXT` (b), the W2-P6a
plan review section 2 (rows MR1, QR2, MR2, MR2b, MR7), AMENDMENT P6a-1 (ST3 (a):
MR2b), AMENDMENT P6a-2 (F1726: the order MR1, MR2, MR7, MR2b; F1728 the texts),
AMENDMENT P6-5 section 3 (C-M3, C-M6: this file's ports), AMENDMENT P6-6 (Q1:
QR2; Q3 (a): relative seqs).

Before S-M.2 the second player's machine shows no message at all (connectionTCP
holds no InfoboxState / InfoboxOKState / warningLongRaw), and the host shows
vanilla's boxes for BOTH players' soldiers - an OK box waits for the host
player's click, a 2 s box pauses the shared battle (F425).

ONE boot, five rows, in this order. The default NEW BATTLE map as
test_w2_turn_cues.py boots it (set_seed SEED_ROSTER on the host right before its
open_new_battle, set_seed SEED_MAP right before newbattle_ok, seat_count 2,
SEATED = the client's C (8) and C2 (9); H (10) the host's; A the only alien,
pinned by session.pin_ai_neutral), with `battleNotifyDeath: true` in both
instances' options (ST3 (a): vanilla's "has been killed" box is off by default).
Every host infobox that appears is recorded (its texts) and closed host-only (an
InfoboxOKState by its OK button, any other by dismiss_popup). Every END TURN
cycle: the client presses first, the host presses once it paints END TURN 1/2,
NextTurnStates are closed through their real close() on both machines.

  MR1  C2's fatal wound (cycle 1, nothing pressed before it). C2 health
       STAGE_HEALTH with fatalWounds STAGE_WOUNDS (battle_set_unit_state, both).
       C2 bleeds out at the turn-2 player side start: death {unit C2,
       damageType 0 (DT_NONE), outcome dead} at seq0+7, corpse at seq0+8.
       GREEN: host ring +1 {C2, STR_HAS_DIED_FROM_A_FATAL_WOUND, partner,
       notice}; the host never showed an infobox in the cycle; the host's
       warningText == TEXT_MR1; client ring +1 {C2, same key, own, okbox, queued
       Q_MR1} shown (shownAtMs > 0); the client's top InfoboxOKState with
       TEXT_MR1, closed by its OK button; C2 DEAD on both.
       RED: both rings empty; the host's InfoboxOKState with TEXT_MR1 recorded
       and closed by its OK button; no client box.
  QR2  F1270 (declared green at red, AMENDMENT P6-6 Q1 (a) - T0-QR2r fell back,
       see below): after MR1's cycle coopWaitText == "" on both (fresh battles no
       longer raise EQUIP_FROZEN since W2-P8b, F3918/F3919/F4002).
  MR2  H's fatal wound (cycle 2), the same staging on H. GREEN: host ring +1
       {H, STR_HAS_DIED_FROM_A_FATAL_WOUND, own, okbox} and the host's OK box
       with TEXT_MR2 recorded, closed by its OK button (the only host box of the
       cycle); client ring +1 {H, same key, partner, notice, queued Q_MR2}; the
       client's warningText == TEXT_MR2. RED: both rings empty.
  MR7  alien panic (cycle 3, D170 (a)). A morale 0 (both); host set_seed
       SEED_MR7 right before its END TURN press; A panics (mode MR7_MODE) at the
       hostile side start: panic {unit A, mode MR7_MODE} then its bt_action_end
       (seq0+3, seq0+4). GREEN: host ring +1 {A, MR7_KEY, other, box} and the
       host's box with TEXT_MR7 recorded (vanilla on the host); client ring +1
       {A, MR7_KEY, other, box}. RED: both rings empty.
  MR2b battleNotifyDeath (ST3 (a)): host battle_action kill_unit_real {unit C}
       (DT_AP): death {unit C, damageType 1, outcome dead} at seq0+1, corpse at
       seq0+2. GREEN: host ring +1 {C, STR_HAS_BEEN_KILLED, partner, notice}; no
       host infobox; the host's warningText == TEXT_MR2B; client ring +1 {C, same
       key, own, box, queued Q_MR2B}. RED: both rings empty; the host's
       InfoboxState with TEXT_MR2B recorded.

QR2r (AMENDMENT P6-6 Q1 (b)) is NOT a row: T0-QR2r's construction (a SPEC 16
rejoin by a fresh process with its battle_ready held, the host's map input in
phase Handshake raising "Waiting for the other player to join the battle") was
built up to the END TURN cycle, which cannot complete after such a rejoin (the
rejoiner's END TURN side-phase counter restarts at 0 while the host's is 9, so
the host drops every press as stale - the instrumented capture, W2-P6a S-M red
report); the stage fell back to Q1 (a): QR2 is declared green at red and both
host branches (the next-stage EQUIP_FROZEN clear and the mid-battle-resume
WAITING_FOR_JOIN clear) are recorded untested (the F1617 precedent).

Every MR row asserts the exact new ring records (unit, key, owner, presenter;
`queued` where pinned) on each machine, in order, and nothing else for the row.
`queued` (T0a-3, two runs on the S-M.1 build, the client's `seen` records): the
decision for a death is made at its corpse (OR2 (a)), which applied under
BattlescapeState in MR1, MR2 and MR2b (Q_MR1, Q_MR2, Q_MR2B false; the deaths
themselves applied under the client's NextTurnState in MR1 and MR2); MR7's panic
applied under the client's NextTurnState in both runs, but by a one-frame race
(the host panics in its first frame after its own NextTurnState closes while the
cycle closes the client's NextTurnState two round trips later), so MR7's
`queued` is recorded, never asserted. The relative ev pins are T0a-2r's
(F4000/F4001: equal relative to each row's seq0 on two runs; the absolute seqs
are read from the run and printed). After every row the client's message queue
is empty and its top is BattlescapeState within MSG_QUIET_S (a bounded wait, so
a 2 s client box never spans two rows; recorded). Common asserts per row: every
bucket EQUAL, desyncSeen false on both.

Probe (commit S-M.1, CoopBattleUi.h messagesProbe()): event_state `messages`
{counts: {box, okbox, notice, pause, none, queued, droppedAtBattleEnd},
queueDepth, ring: [{seq, kind, unit, key, owner, presenter, queued, queuedAtMs,
shownAtMs}], seen: [{seq, kind, unit, top}] (client)}. A row's new records are
the ring's tail by the presenter counts' growth. The EVIDENCE line of each row
carries the client's `seen` records (T0a-3: the client's top state at each
applied death / corpse / panic / psi / spawn).

Ports (AMENDMENT P6-5 C-M6, F3205): GameClient 49990 / 49991, lobby PORT 48639.

RED-THEN-GREEN (spec section (d) row S-M; P6a review section 3 as amended by
P6-6 section 5 with Q1 (a)). Commit S-M.1 is run ONCE: exit 2 with exactly MR1,
MR2, MR7 and MR2b failing (each on its RED above) and QR2 passing. Commit S-M.2
is run ONCE: all five pass. Each row prints ONE "EVIDENCE <id>:" line before its
conditions are checked; main() runs every row even after an earlier one failed
and prints "PASS <id>" / "FAIL <id>: <message>". Every wait is bounded; a wait
that times out is recorded in the EVIDENCE line and fails the row.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all five rows pass, 2 otherwise (a
bring-up failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_messages.py
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_rw_turn_baton import dismiss_next_turn_if_present
from test_w2_delta_core import diff_buckets, short, both, desync_record
from test_w2_host_combat import evs_since
from test_w2_ai_origins import host_payloads, bring_up_lobby_roster_pinned

# ----- bring-up (the test_w2_turn_cues.py default-map boot; W2-P6a TASK 0a T0a-2, re-measured by T0a-2r) -----
PORT = "48639"                   # AMENDMENT P6-5 C-M6 (F3205: 0 uses at the tip)
HOST_PORT, CLIENT_PORT = 49990, 49991
SEED_MAP = 1                     # set_seed in pre_ok right before newbattle_ok; DEFAULT NEW BATTLE (no mission)
MAP_FP = -4.48310638993e+18      # host AND client battle_state.mapFingerprint
SEATED = [8, 9]                  # the client seat's soldiers
UNIT_ORDER = [8, 9, 10, 11, 12, 13, 14, 1000000]
C_ID, C2_ID, H_ID, A_ID = 8, 9, 10, 1000000
NAMES = {8: "Henryk Pawlowski", 9: "Holger Schwarz", 10: "Henryk Kaminski", 1000000: "Sectoid Soldier"}   # SEED_ROSTER
FACTION_PLAYER = 0
STATUS_DEAD = 6                  # src/Mod/Unit.h UnitStatus
OPTIONS = {"battleNotifyDeath": True}   # ST3 (a), both instances

# ----- the rows (T0a-2 / T0a-2r; F1728: "\n" between the name and the phrase, capital P) -----
STAGE_HEALTH = 1
STAGE_WOUNDS = [0, 1, 0, 0, 0, 0]        # head, torso, rarm, larm, rleg, lleg: one torso wound
KEY_FATAL = "STR_HAS_DIED_FROM_A_FATAL_WOUND"
KEY_KILLED = "STR_HAS_BEEN_KILLED"
KEY_PANICKED = "STR_HAS_PANICKED"
KEY_BERSERK = "STR_HAS_GONE_BERSERK"
TEXT_MR1 = "Holger Schwarz\nhas died from a fatal wound"
TEXT_MR2 = "Henryk Kaminski\nhas died from a fatal wound"
TEXT_MR2B = "Henryk Pawlowski\nhas been killed"
SEED_MR7 = 1                     # host set_seed right before its cycle-3 END TURN press
MR7_MODE = "flee"                # PIN (F4003): re-measured under F1726's order on the S-M.1 build, two runs
MR7_KEY = KEY_PANICKED           # flee / freeze -> STR_HAS_PANICKED; berserk -> STR_HAS_GONE_BERSERK
TEXT_MR7 = "Sectoid Soldier\nhas Panicked"
# PIN (T0a-3, two runs): the client's top at each row's decision point - a death's corpse (OR2 (a)) - was
# BattlescapeState (MR7's panic: a one-frame race, recorded only)
Q_MR1 = False
Q_MR2 = False
Q_MR2B = False
# the host's evs after each row's seq0, as (kind, actionId) - T0a-2r (F4000/F4001), equal relative to seq0
CYCLE_ST = [("side_transition", 0), ("side_begin", 0)]
MR1_EVS = CYCLE_ST * 3 + [("death", 0), ("corpse", 0)]
MR2_EVS = MR1_EVS
MR2B_EVS = [("death", 0), ("corpse", 0)]
MR7_KINDS = ["side_transition", "side_begin", "panic", "bt_action_end", "side_transition", "side_begin",
             "side_transition", "side_begin"]

# ----- waits -----
CYCLE_TIMEOUT_S = 90
SETTLE_TIMEOUT_S = 30
CLIENT_SETTLE_S = 20
OK_BOX_WAIT_S = 5.0              # MR1: the client's OK box comes up (green); at red the wait runs out
MSG_QUIET_S = 10.0               # the client's message queue empty and BattlescapeState on top after a row

PRESENTERS = ("box", "okbox", "notice", "pause", "none")
INFOBOX_RE = re.compile(r"\[coop-ui\] push class OpenXcom::(Infobox\w*) depth=(\d+)")


# ===================== the messages probe (shared with the other S-M files) =====================


def messages(gc):
    """event_state `messages` on this machine ({} when the probe is missing)."""
    m = event_state(gc).get("messages")
    return m if isinstance(m, dict) else {}


def msg_probe_fails(gc):
    """[] when this machine carries the S-M.1 `messages` probe with its full shape."""
    m = messages(gc)
    c = m.get("counts") if isinstance(m.get("counts"), dict) else {}
    if (not all(k in c for k in PRESENTERS + ("queued", "droppedAtBattleEnd")) or "queueDepth" not in m
            or not isinstance(m.get("ring"), list) or not isinstance(m.get("seen"), list)):
        return [f"{gc.name} event_state lacks the `messages` probe (S-M.1): {m!r}"]
    return []


def msg_total(m):
    c = (m or {}).get("counts") or {}
    return sum(int(c.get(p) or 0) for p in PRESENTERS)


def msg_snap(host, client):
    return {"host": messages(host), "client": messages(client)}


def msg_new(before, after):
    """The ring records one machine appended between two probes, oldest first: the presenter counts' growth, read
    off the end of the ring (it holds the last 32)."""
    n = msg_total(after) - msg_total(before)
    ring = list((after or {}).get("ring") or [])
    if n <= 0:
        return []
    return ring[-n:] if n <= len(ring) else ring


def msg_view(r):
    return {k: r.get(k) for k in ("seq", "kind", "unit", "key", "owner", "presenter", "queued", "queuedAtMs",
                                  "shownAtMs")}


def want(unit, key, owner, presenter, queued=None):
    w = {"unit": unit, "key": key, "owner": owner, "presenter": presenter}
    if queued is not None:
        w["queued"] = queued
    return w


def msg_rows_fails(what, name, recs, wants):
    """The exact new ring records on one machine: each record holds its `want` (unit, key, owner, presenter and,
    where pinned, queued), in order, and nothing else."""
    got = [{k: r.get(k) for k in w} for r, w in zip(recs, wants)]
    if len(recs) != len(wants) or got != wants:
        return [f"{what}: {name} messages ring +{len(recs)} {[msg_view(r) for r in recs]} (want exactly {wants})"]
    return []


def msg_delta(before, after):
    """Both machines' new ring records between two msg_snap()s."""
    return {n: msg_new(before[n], after[n]) for n in ("host", "client")}


def seen_since(m, seq0):
    """The client's `seen` records after seq0 as (seq, kind, unit, top) - T0a-3's reading."""
    return [(r.get("seq"), r.get("kind"), r.get("unit"), r.get("top")) for r in (m or {}).get("seen") or []
            if (r.get("seq") or 0) > seq0]


def msg_evidence(before, after, seq0):
    d = msg_delta(before, after)
    return {"hostNew": [msg_view(r) for r in d["host"]], "clientNew": [msg_view(r) for r in d["client"]],
            "counts": {n: (after[n] or {}).get("counts") for n in ("host", "client")},
            "queueDepth": {n: (after[n] or {}).get("queueDepth") for n in ("host", "client")},
            "clientSeen": seen_since(after["client"], seq0)}


def top(gc):
    return session.top_state(gc)


def client_quiet(client, timeout=MSG_QUIET_S):
    """Bounded wait: the client's message queue empty and BattlescapeState on top (a 2 s box closes by itself).
    Returns {ok, s, top, queueDepth}."""
    t0 = time.time()
    ok = False
    while time.time() - t0 < timeout:
        if (messages(client).get("queueDepth") or 0) == 0 and top(client) == "BattlescapeState":
            ok = True
            break
        time.sleep(0.1)
    return {"ok": ok, "s": round(time.time() - t0, 2), "top": top(client),
            "queueDepth": messages(client).get("queueDepth")}


# ===================== small probes =====================


def units(gc):
    return session.units_by_id(battle_state(gc))


def texts_of(gc):
    return [w.get("text") for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]


def banners(gc):
    bs = battle_state(gc)
    return {"coopWaitText": bs.get("coopWaitText"), "warningText": bs.get("warningText"), "turn": bs.get("turn"),
            "side": bs.get("side")}


def log_size(gc):
    try:
        return os.path.getsize(os.path.join(gc.user_dir, "openxcom.log"))
    except OSError:
        return 0


def log_infobox_pushes(gc, off):
    """This machine's `[coop-ui] push class OpenXcom::Infobox*` lines (Game.cpp) written after byte `off`."""
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as f:
            f.seek(off)
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    return [m.group(1) for m in INFOBOX_RE.finditer(text)]


# ===================== driving =====================


def poll_host_box(host, rec, where):
    """A host infobox on top is recorded (its texts) and closed host-only: an InfoboxOKState by its OK button, any
    other infobox by dismiss_popup. Returns True when one was handled."""
    t = top(host) or ""
    if "Infobox" not in t:
        return False
    e = {"where": where, "top": t, "texts": texts_of(host), "lastSeq": event_state(host).get("lastSeqEmitted")}
    if t == "InfoboxOKState":
        r = host.cmd({"cmd": "click_widget", "match": "OK"})
        e["closed"] = ("ok button", r.get("ok"), r.get("error"))
    else:
        r = host.cmd({"cmd": "dismiss_popup"})
        e["closed"] = ("dismiss_popup", r.get("handled"), r.get("error"))
    rec["hostBoxes"].append(e)
    return True


def host_idle(host):
    bs = battle_state(host)
    return (top(host) == "BattlescapeState" and bs.get("panicHandled") and bs.get("pendingStates") == 0
            and not bs.get("isBusy") and event_state(host).get("busyOwnerSeat") == -1)


def settle(host, client, rec, where):
    """The host idle on BattlescapeState for 0.6 s (its infoboxes recorded and closed, its NextTurnStates closed),
    then the client: NextTurnStates closed until BattlescapeState or an InfoboxOKState is on top (a 2 s
    InfoboxState closes by itself), then the client caught up. Bounded; a timeout goes to rec["notes"]."""
    deadline = time.time() + SETTLE_TIMEOUT_S
    since = None
    while True:
        busy = poll_host_box(host, rec, where)
        if dismiss_next_turn_if_present(host):
            busy = True
        dismiss_next_turn_if_present(client)
        if not busy and host_idle(host):
            since = since or time.time()
            if time.time() - since >= 0.6:
                break
        else:
            since = None
        if time.time() > deadline:
            rec["notes"].append(f"{where}: the host did not settle within {SETTLE_TIMEOUT_S}s (top {top(host)})")
            break
        time.sleep(0.05)
    deadline = time.time() + CLIENT_SETTLE_S
    while True:
        poll_host_box(host, rec, where + "/client")
        dismiss_next_turn_if_present(client)
        t = top(client)
        bs = battle_state(client)
        if (t == "BattlescapeState" and bs.get("panicHandled") and bs.get("pendingStates") == 0) \
                or t == "InfoboxOKState":
            break
        if time.time() > deadline:
            rec["notes"].append(f"{where}: the client not on BattlescapeState within {CLIENT_SETTLE_S}s (top {t})")
            break
        time.sleep(0.05)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        rec["notes"].append(f"{where}: {short(e)}")


def cycle(host, client, seed, rec, what):
    """Both machines press END TURN (the client first; the host once it paints END TURN 1/2, with set_seed `seed`
    on the host right before its press when not None), then the full side cycle back to the player side, the
    host's infoboxes recorded and closed host-only, the NextTurnStates closed on both, both settled."""
    turn0 = battle_state(host).get("turn")
    rec["turn0"] = turn0
    try:
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        host.wait_for("host paints END TURN 1/2 after the client's press",
                      lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2" or None, timeout=20)
        if seed is not None:
            host.ok({"cmd": "set_seed", "seed": seed})
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        deadline = time.time() + CYCLE_TIMEOUT_S
        while True:
            poll_host_box(host, rec, what)
            dismiss_next_turn_if_present(host)
            dismiss_next_turn_if_present(client)
            a, b = battle_state(host), battle_state(client)
            if (a.get("side") == FACTION_PLAYER and (a.get("turn") or -1) >= turn0 + 1
                    and b.get("side") == FACTION_PLAYER and (b.get("turn") or -1) >= turn0 + 1):
                break
            if time.time() > deadline:
                raise TimeoutError(f"{what}: no player turn {turn0 + 1} on both within {CYCLE_TIMEOUT_S}s: host="
                                   f"({a.get('turn')},{a.get('side')}) client=({b.get('turn')},{b.get('side')})")
            time.sleep(0.05)
        settle(host, client, rec, what)
    except Exception as e:
        rec["notes"].append(f"{what}: {short(e)}")
    a, b = battle_state(host), battle_state(client)
    rec["end"] = {"host": (a.get("turn"), a.get("side")), "client": (b.get("turn"), b.get("side"))}


def begin(host, client, name):
    """A row's record: the probes before its first staging write."""
    es = event_state(host)
    return {"row": name, "seq0": es.get("lastSeqEmitted") or 0, "hostBoxes": [], "notes": [],
            "mb": msg_snap(host, client), "logOff": log_size(host), "bannersBefore": {
                "host": banners(host), "client": banners(client)}}


def end(host, client, rec, payload_kinds=("death", "corpse", "panic", "psi", "spawn")):
    """Everything a row's checks read, after its chain settled."""
    rec["ma"] = msg_snap(host, client)
    hev = evs_since(host, rec["seq0"])
    rec["hev"] = [(e["seq"], e["kind"], e["actionId"]) for e in hev]
    rec["pl"] = host_payloads(host, [e["seq"] for e in hev if e["kind"] in payload_kinds])
    rec["logBoxes"] = log_infobox_pushes(host, rec["logOff"])
    rec["bannersAfter"] = {"host": banners(host), "client": banners(client)}
    rec["uh"], rec["uc"] = units(host), units(client)
    rec["diff"] = diff_buckets(host, client)
    ph, pc = event_state(host), event_state(client)
    rec["desync"] = {"host": ph.get("desyncSeen"), "client": pc.get("desyncSeen")}
    if pc.get("desyncSeen"):
        rec["desyncRecord"] = desync_record(client, True)
    rec["topClient"] = top(client)
    return rec


def rel_evs(rec):
    """The host's evs after seq0 as (offset from seq0, kind, actionId)."""
    return [(s - rec["seq0"], k, a) for s, k, a in rec["hev"]]


def payload_of(rec, kind, unit=None):
    """The host payloads of `kind` (for `unit` when given), in seq order, as (seq, payload)."""
    out = []
    for s in sorted(rec["pl"]):
        v = rec["pl"][s]
        p = v.get("payload") or {}
        if v.get("kind") == kind and (unit is None or p.get("unit") == unit):
            out.append((s, p))
    return out


def evidence(rec, extra=""):
    return (f"seq0={rec['seq0']} host evs (seq, kind, actionId)={rec['hev']} cues={rec['pl']}; messages="
            f"{msg_evidence(rec['mb'], rec['ma'], rec['seq0'])}; hostBoxes={rec['hostBoxes']} host log infobox "
            f"pushes={rec['logBoxes']}; banners before={rec['bannersBefore']} after={rec['bannersAfter']}; client "
            f"top={rec['topClient']}; diff={rec['diff']} desync={rec['desync']}"
            f"{' ' + str(rec.get('desyncRecord')) if rec.get('desyncRecord') else ''}; {extra}notes={rec['notes']}")


def common_fails(rec, what):
    fails = []
    if rec["diff"]:
        fails.append(f"{what}: buckets differ {rec['diff']} (want every bucket EQUAL)")
    if rec["desync"]["host"] or rec["desync"]["client"]:
        fails.append(f"{what}: desyncSeen host={rec['desync']['host']} client={rec['desync']['client']} (want false)")
    return fails


def dead_fails(rec, uid, what):
    st = ((rec["uh"].get(uid) or {}).get("status"), (rec["uc"].get(uid) or {}).get("status"))
    if st != (STATUS_DEAD, STATUS_DEAD):
        return [f"{what}: unit {uid} status host/client {st} (want DEAD {STATUS_DEAD} on both)"]
    return []


def death_fails(rec, uid, damage_type, evs, what):
    """The fixture premise (T0a-2r, relative to seq0): the host's evs and the death / corpse payloads."""
    fails = []
    got = [(o, k, a) for o, k, a in rel_evs(rec)]
    want_evs = [(i + 1, k, a) for i, (k, a) in enumerate(evs)]
    if got != want_evs:
        fails.append(f"{what}: precondition: host evs after seq0 {rec['seq0']} (offset, kind, actionId) {got} (want "
                     f"{want_evs}, T0a-2r)")
    d = payload_of(rec, "death", uid)
    c = payload_of(rec, "corpse", uid)
    dp = d[0][1] if d else {}
    if len(d) != 1 or (dp.get("damageType"), dp.get("outcome")) != (damage_type, "dead") or len(c) != 1:
        fails.append(f"{what}: precondition: death cues {d} corpse cues {c} for unit {uid} (want one death "
                     f"{{damageType {damage_type}, outcome dead}} and one corpse)")
    return fails


def stage_wounds(host, client, uid):
    r = both(host, client, {"cmd": "battle_set_unit_state", "unit": uid, "health": STAGE_HEALTH,
                            "fatalWounds": STAGE_WOUNDS}, ("health", "fatalWounds"))
    return {"health": r.get("health"), "fatalWounds": r.get("fatalWounds")}


def finish(fails):
    if fails:
        raise AssertionError("; ".join(fails))


# ===================== rows =====================


def mr1_fatal_wound_client(host, client, ctx):
    rec = begin(host, client, "MR1")
    staged = stage_wounds(host, client, C2_ID)
    staged_diff = diff_buckets(host, client)
    cycle(host, client, None, rec, "cycle 1")
    end(host, client, rec)
    ctx["qr2"] = {"after": rec["bannersAfter"], "notes": list(rec["notes"])}
    # the client's OK box (green): a bounded wait, then its texts; closed by its OK button after the reads
    box = {"top0": top(client)}
    try:
        client.wait_for("the client's OK box", lambda: top(client) == "InfoboxOKState" or None, timeout=OK_BOX_WAIT_S)
    except Exception as e:
        box["wait"] = short(e)
    box["top"] = top(client)
    box["texts"] = texts_of(client) if "Infobox" in (box["top"] or "") else None
    d = msg_delta(rec["mb"], rec["ma"])
    rec["ma"]["client"] = messages(client)      # re-read after the wait: shownAtMs of the OK box
    dc = msg_new(rec["mb"]["client"], rec["ma"]["client"])
    if box["top"] == "InfoboxOKState":
        r = client.cmd({"cmd": "click_widget", "match": "OK"})
        box["closed"] = ("ok button", r.get("ok"), r.get("error"))
        try:
            client.wait_for("client BattlescapeState after OK", lambda: top(client) == "BattlescapeState" or None,
                            timeout=5)
        except Exception as e:
            box["closeWait"] = short(e)
        box["after"] = top(client)
    quiet = client_quiet(client)
    print(f"EVIDENCE MR1: staged C2 {staged} stagedDiff={staged_diff}; client box={box}; quiet={quiet}; "
          f"{evidence(rec)}", flush=True)
    fails = list(rec["notes"])
    if staged_diff:
        fails.append(f"MR1: buckets differ after the staging: {staged_diff} (want none)")
    fails += death_fails(rec, C2_ID, 0, MR1_EVS, "MR1")
    fails += msg_rows_fails("MR1", "host", d["host"], [want(C2_ID, KEY_FATAL, "partner", "notice")])
    fails += msg_rows_fails("MR1", "client", dc, [want(C2_ID, KEY_FATAL, "own", "okbox", queued=Q_MR1)])
    if dc and not (dc[0].get("shownAtMs") or 0) > 0:
        fails.append(f"MR1: the client's record {msg_view(dc[0])} was never shown (want shownAtMs > 0)")
    if rec["hostBoxes"] or rec["logBoxes"]:
        fails.append(f"MR1: the host showed infoboxes {rec['hostBoxes']} (log pushes {rec['logBoxes']}) (want none: "
                     f"a message about the partner's soldier never pauses the host, D132)")
    if rec["bannersAfter"]["host"]["warningText"] != TEXT_MR1:
        fails.append(f"MR1: the host's warningText {rec['bannersAfter']['host']['warningText']!r} (want the notice "
                     f"{TEXT_MR1!r})")
    if box["top"] != "InfoboxOKState" or TEXT_MR1 not in (box.get("texts") or []):
        fails.append(f"MR1: the client's top {box['top']!r} texts {box.get('texts')} (want InfoboxOKState with "
                     f"{TEXT_MR1!r}: vanilla's OK box for its own soldier)")
    elif box.get("after") != "BattlescapeState":
        fails.append(f"MR1: the client's OK box did not close by its OK button (top after {box.get('after')!r})")
    if not quiet["ok"]:
        fails.append(f"MR1: the client's message queue / top after the row {quiet} (want empty, BattlescapeState)")
    fails += dead_fails(rec, C2_ID, "MR1")
    fails += common_fails(rec, "MR1")
    finish(fails)


def qr2_entry_notice(host, client, ctx):
    q = ctx.get("qr2")
    print(f"EVIDENCE QR2: MR1's cycle banners after={q}", flush=True)
    if q is None:
        finish(["QR2: precondition: MR1's cycle never ran"])
    got = (q["after"]["host"]["coopWaitText"], q["after"]["client"]["coopWaitText"])
    if got != ("", ""):
        finish([f"QR2: coopWaitText host/client after cycle 1 {got} (want '' on both: no stale entry notice, F1270)"])


def mr2_fatal_wound_host(host, client, ctx):
    rec = begin(host, client, "MR2")
    staged = stage_wounds(host, client, H_ID)
    staged_diff = diff_buckets(host, client)
    cycle(host, client, None, rec, "cycle 2")
    end(host, client, rec)
    quiet = client_quiet(client)
    rec["ma"]["client"] = messages(client)
    d = msg_delta(rec["mb"], rec["ma"])
    print(f"EVIDENCE MR2: staged H {staged} stagedDiff={staged_diff}; quiet={quiet}; {evidence(rec)}", flush=True)
    fails = list(rec["notes"])
    if staged_diff:
        fails.append(f"MR2: buckets differ after the staging: {staged_diff} (want none)")
    fails += death_fails(rec, H_ID, 0, MR2_EVS, "MR2")
    fails += msg_rows_fails("MR2", "host", d["host"], [want(H_ID, KEY_FATAL, "own", "okbox")])
    fails += msg_rows_fails("MR2", "client", d["client"], [want(H_ID, KEY_FATAL, "partner", "notice", queued=Q_MR2)])
    boxes = [(b["top"], TEXT_MR2 in (b["texts"] or []), b["closed"][0]) for b in rec["hostBoxes"]]
    if boxes != [("InfoboxOKState", True, "ok button")] or rec["logBoxes"] != ["InfoboxOKState"]:
        fails.append(f"MR2: the host's infoboxes {rec['hostBoxes']} (log pushes {rec['logBoxes']}) (want exactly its "
                     f"own OK box with {TEXT_MR2!r}, closed by its OK button)")
    if rec["bannersAfter"]["client"]["warningText"] != TEXT_MR2:
        fails.append(f"MR2: the client's warningText {rec['bannersAfter']['client']['warningText']!r} (want the "
                     f"notice {TEXT_MR2!r})")
    if not quiet["ok"]:
        fails.append(f"MR2: the client's message queue / top after the row {quiet} (want empty, BattlescapeState)")
    fails += dead_fails(rec, H_ID, "MR2")
    fails += common_fails(rec, "MR2")
    finish(fails)


def mr7_alien_panic(host, client, ctx):
    rec = begin(host, client, "MR7")
    m = both(host, client, {"cmd": "battle_set_unit_state", "unit": A_ID, "morale": 0}, ("morale",))
    staged_diff = diff_buckets(host, client)
    cycle(host, client, SEED_MR7, rec, "cycle 3")
    end(host, client, rec)
    quiet = client_quiet(client)
    rec["ma"]["client"] = messages(client)
    d = msg_delta(rec["mb"], rec["ma"])
    panics = payload_of(rec, "panic", A_ID)
    print(f"EVIDENCE MR7: A morale response={m.get('morale')} stagedDiff={staged_diff}; seed {SEED_MR7}; A panics "
          f"(seq, payload)={panics}; quiet={quiet}; {evidence(rec)}", flush=True)
    fails = list(rec["notes"])
    if m.get("morale") != 0 or staged_diff:
        fails.append(f"MR7: staging morale {m.get('morale')} diff {staged_diff} (want 0, none)")
    kinds = [k for _, k, _ in rec["hev"]]
    ids = {k: a for _, k, a in rec["hev"] if k in ("panic", "bt_action_end")}
    if kinds != MR7_KINDS or not ids.get("panic") or ids.get("panic") != ids.get("bt_action_end") \
            or [(s - rec["seq0"]) for s, k, _ in rec["hev"] if k == "panic"] != [3]:
        fails.append(f"MR7: precondition: host evs after seq0 {rec['seq0']} {rec['hev']} (want kinds {MR7_KINDS}, the "
                     f"panic at seq0+3 and its bt_action_end in one context, T0a-2r)")
    if len(panics) != 1 or panics[0][1].get("mode") != MR7_MODE:
        fails.append(f"MR7: precondition: A's panic cues {panics} (want one with mode {MR7_MODE!r})")
    fails += msg_rows_fails("MR7", "host", d["host"], [want(A_ID, MR7_KEY, "other", "box")])
    fails += msg_rows_fails("MR7", "client", d["client"], [want(A_ID, MR7_KEY, "other", "box")])
    boxes = [(b["top"], TEXT_MR7 in (b["texts"] or [])) for b in rec["hostBoxes"]]
    if boxes != [("InfoboxState", True)] or rec["logBoxes"] != ["InfoboxState"]:
        fails.append(f"MR7: the host's infoboxes {rec['hostBoxes']} (log pushes {rec['logBoxes']}) (want exactly "
                     f"vanilla's box with {TEXT_MR7!r}, D170 (a))")
    if not quiet["ok"]:
        fails.append(f"MR7: the client's message queue / top after the row {quiet} (want empty, BattlescapeState)")
    fails += common_fails(rec, "MR7")
    finish(fails)


def mr2b_killed(host, client, ctx):
    rec = begin(host, client, "MR2b")
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": C_ID})
    lever = {k: r.get(k) for k in ("ok", "killed", "error")}
    deadline = time.time() + 6
    while time.time() < deadline and not rec["hostBoxes"]:
        poll_host_box(host, rec, "MR2b")
        if (event_state(host).get("lastSeqEmitted") or 0) >= rec["seq0"] + len(MR2B_EVS) and host_idle(host):
            break
        time.sleep(0.03)
    settle(host, client, rec, "MR2b")
    end(host, client, rec)
    quiet = client_quiet(client)
    rec["ma"]["client"] = messages(client)
    d = msg_delta(rec["mb"], rec["ma"])
    print(f"EVIDENCE MR2b: lever={lever}; quiet={quiet}; {evidence(rec)}", flush=True)
    fails = list(rec["notes"])
    if not lever["ok"]:
        fails.append(f"MR2b: precondition: kill_unit_real {lever}")
    fails += death_fails(rec, C_ID, 1, MR2B_EVS, "MR2b")
    fails += msg_rows_fails("MR2b", "host", d["host"], [want(C_ID, KEY_KILLED, "partner", "notice")])
    fails += msg_rows_fails("MR2b", "client", d["client"], [want(C_ID, KEY_KILLED, "own", "box", queued=Q_MR2B)])
    if rec["hostBoxes"] or rec["logBoxes"]:
        fails.append(f"MR2b: the host showed infoboxes {rec['hostBoxes']} (log pushes {rec['logBoxes']}) (want none, "
                     f"D132)")
    if rec["bannersAfter"]["host"]["warningText"] != TEXT_MR2B:
        fails.append(f"MR2b: the host's warningText {rec['bannersAfter']['host']['warningText']!r} (want the notice "
                     f"{TEXT_MR2B!r})")
    if not quiet["ok"]:
        fails.append(f"MR2b: the client's message queue / top after the row {quiet} (want empty, BattlescapeState)")
    fails += dead_fails(rec, C_ID, "MR2b")
    fails += common_fails(rec, "MR2b")
    finish(fails)


SCENARIOS = (("MR1", mr1_fatal_wound_client), ("QR2", qr2_entry_notice), ("MR2", mr2_fatal_wound_host),
             ("MR7", mr7_alien_panic), ("MR2b", mr2b_killed))


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r} (baked {MAP_FP!r})")
    assert seated.get("soldierIds") == SEATED, f"seated {seated.get('soldierIds')} (baked {SEATED})"
    order = ([u["id"] for u in hs.get("units", [])], [u["id"] for u in cs.get("units", [])])
    assert order == (UNIT_ORDER, UNIT_ORDER), f"unit order host/client {order} (baked {UNIT_ORDER})"
    names = {u["id"]: u.get("name") for u in hs.get("units", []) if u["id"] in NAMES}
    assert names == NAMES, f"unit names {names} (baked {NAMES}: the pinned texts carry them)"
    pinned = pin_ai_neutral(host, client, tag="w2p6a-sm")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (want [{A_ID}])"
    for gc in (host, client):
        f = msg_probe_fails(gc)
        assert not f, f[0]
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2p6a-sm] boot ok: default map MAP_FP={MAP_FP!r} turn={hs.get('turn')} seated={SEATED} pinned={pinned} "
          f"names={names} messages host={messages(host)} client={messages(client)}",
          flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", HOST_PORT, make_user_dir("w2p6a_messages_host", options=OPTIONS))
    client = GameClient("client", CLIENT_PORT, make_user_dir("w2p6a_messages_client", options=OPTIONS))
    results = {}
    ctx = {}
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:  # a bring-up failure fails the whole run
            print(f"FAIL boot: {type(e).__name__}: {e}", flush=True)
            return 2
        for name, fn in SCENARIOS:
            try:
                fn(host, client, ctx)
                results[name] = True
                print(f"PASS {name}", flush=True)
            except Exception as e:
                results[name] = False
                kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
                print(f"FAIL {name}: {kind}{e}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p6a-sm] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_messages: {len(passed)}/{len(SCENARIOS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
