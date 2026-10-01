"""W2-P6b S-L - test_w2_hit_log.py: the battle's hit log (Ctrl-H) on both machines,
the same log as the host's, each machine in its own language (owner D172 (a)) -
spec docs rewrite/prompts/w2p6_display_two.md: AMENDMENT P6-5 section 6 (the
pinned stage text, rows L1-L4; P6-5 Q3 (a) the envelope carrier, Q4 (a) the
client writes SavedBattleGame::appendToHitLog, Q5 (a) a German client),
AMENDMENT P6-6 section 5 (Q2 (a): the host records in phase Handshake or Active)
and the P6-6k S-L TASK 0 RULINGS (SL-1; T0L-1 = F4235-F4244).

Before S-L.2 the second player's hit log holds only its own entries: the turn
headers its own next-turn screen writes and a weapon line for every attack it
picked itself; the host's shots, hits and reactions never reach it, and the
host's log has no weapon line for the second player's attack (F3212). After
S-L.2 the HOST mirrors every entry that passes vanilla's player-side check as
{t: type, f: faction, k: [keys]} on its next outermost emit (the envelope field
`hitLog`), the CLIENT appends each entry through SavedBattleGame::appendToHitLog
rendered by its own Language, its own weapon line is suppressed (V7) and the
host logs the partner's weapon line at the order's executor (V6).

ONE boot, the host in English and the CLIENT in German (options `language: de`):
the roster-pinned terror boot of test_w2_host_combat.py (set_seed SEED_ROSTER
on the host right before its open_new_battle, STR_TERROR_MISSION, set_seed
SEED_MAP right before newbattle_ok, seat_count 2, MAP_FP on both,
pin_ai_neutral). Four rows, in this order:

  L1  C1's staging (test_w2_host_combat): the host's real-UI snap kills A.
      GREEN: the host's hitLog.text and diary == the English rendering of its
      sent entries == TEXT_L1_EN / DIARY_L1_EN; the client's == the German
      rendering of the same entries == TEXT_L1_DE / DIARY_L1_DE; the host sent
      L1_ENTRIES entries in the row (L1_ENTRY_TYPES) and L1_ENTRIES + 1 from boot
      (the turn-0 NEW_TURN on seq TURN0_SEQ included); the client applied
      exactly the host's entries (same seq, t, f, k); nothing pending.
      RED: the client's text lacks the host's entries (it stays "Neue Runde").
  L2  C16's staging (test_w2_client_shoot) on L1's boot: H back on its bring-up
      tile and facing, the target is A2 on C16's A_TILE (A died in L1); the
      client's real-UI snap. GREEN: the host's text and diary ==
      TEXT_L2_EN / DIARY_L2_EN (it starts with the partner's weapon line), the
      client's == TEXT_L2_DE / DIARY_L2_DE (it starts with the German weapon
      name), the client's localSuppressed +1, the host sent L2_ENTRIES
      (L2_ENTRY_TYPES) and the client applied exactly them. RED: no host
      weapon line (the host's shot entries append to L1's log); the client's
      text is its own local log (its own weapon line only).
  L4  after L2: the client's Ctrl-H (inject_input {key 104, mod ctrl}, then
      {kind modstate, mod none} once the chord is consumed). GREEN: the
      client's top InfoboxState shows its hitLog.text, which == TEXT_L2_DE
      (the host's entries); one left click closes it (BattlescapeState on top,
      the click sent within INFOBOX_CLICK_S of the box being seen); no order
      sent and the selection unchanged. RED: the box's text lacks the host's
      entries.
  L3  both press END TURN; the next player side. GREEN (declared green at
      red): host hitLog.text == "New Turn", client == "Neue Runde", both
      diaries []. The host's pending NEW_TURN (SL-1) is recorded, not asserted.

Common asserts per row: hash_now {full: true} every bucket EQUAL, desyncSeen
false on both, the client's coopClientBStatePushes unchanged and the host's 0,
the client's rngSeed unchanged across the row (V4).

Probes (commit S-L.1; storage and readers only, nothing writes the mirror
until S-L.2): battle_state `hitLog` {text: HitLog::getHitLogText(), diary:
HitLog::getTurnDiary()} and event_state `hitLogMirror` {noted, sent, applied,
localSuppressed, pending, dropped, last: [the last 32 entries {seq, t, f, k?}]}
(CoopDelta.h coopHitLogMirrorProbe()), both machines. The helpers below
(hl_snap, hl_render, the strings) are shared by test_w2_reaction_prox.py (L5)
and test_w2_client_melee_psi.py (L7).

Pins: the entry counts and orders are TASK 0 T0L-1's (ledger `## W2-P6 S-L
TASK 0 (T0L-1) DONE`, F4235-F4244, 3/3 runs); the German strings are T0L-2's
(this file's bring-up on the S-L.1 build: "Neue Runde" and "Gewehr" rendered by
the running German client itself, "=> " and "Treffer" read from the language
file that client loads, bin/x64/Release/common/Language/OXCE/de.yml).

Ports (AMENDMENT P6-5 section 6, P6-6 section 3, F3205): GameClient 49992 /
49993 (labels only), lobby PORT 48659.

RED-THEN-GREEN (AMENDMENT P6-5 section 6). Commit S-L.1 is run ONCE: exit 2
with exactly L1, L2 and L4 failing (each on its RED above) and L3 passing.
Commit S-L.2 is run ONCE: all four pass. Each row prints ONE "EVIDENCE <id>:"
line before its conditions are checked; main() runs every row even after an
earlier one failed and prints "PASS <id>" / "FAIL <id>: <message>". Every wait
is bounded; a wait that times out is recorded and fails the row.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all four rows pass, 2 otherwise (a
bring-up failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_hit_log.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_rw_seat_pacing import SDLK_HOME
from test_w2_delta_core import diff_buckets, short, both, tele_both, tu_both
from test_w2_delta_items import unit_view
from test_w2_host_combat import (bring_up_lobby_roster_pinned, open_hand_menu_host, press, host_chain_done, evs_since,
                                 MISSION, SEED_MAP, MAP_FP, H_ID, A_ID, A2_ID, C1_H_TILE, C1_H_DIR, C1_A_TILE,
                                 C1_A_DIR, C1_A_HEALTH, C1_ITEMS, SEED_C1, FIRING_120, KEY_ITEM2, STATUS_DEAD,
                                 FACTION_HOSTILE, COOP_SEAT_0)
from test_w2_client_shoot import (snap as order_snap, give_both, place, set_tu_both, set_firing_both,
                                  cancel_client_aim, aim_click, await_press, C_ID, C_TILE, C16_C_DIR, A_TILE, A_DIR,
                                  A_HEALTH, SEED_C16, KEY_SNAP, TU_MAX, SEATED)
from test_w2_ai_origins import end_turn_cycle

# ----- bring-up -----
PORT = "48659"                   # AMENDMENT P6-5 section 6 / P6-6 section 3 (F3205, F3922: 0 uses at the tip)
HOST_PORT, CLIENT_PORT = 49992, 49993
CLIENT_OPTIONS = {"language": "de"}   # AMENDMENT P6-5 section 6, Q5 (a): the second player's machine in German
FACTION_PLAYER = 0

# ----- vanilla HitLog (src/Savegame/HitLog.h HitLogEntryType; HitLog.cpp) -----
HL_EMPTY, HL_NEW_TURN, HL_NEW_TURN_MSG, HL_PLAYER_FIRING, HL_REACTION_FIRE, HL_NEW_SHOT, HL_NO_DAMAGE, \
    HL_SMALL_DAMAGE, HL_BIG_DAMAGE = range(9)
HL_NAMES = {HL_EMPTY: "EMPTY", HL_NEW_TURN: "NEW_TURN", HL_NEW_TURN_MSG: "NEW_TURN_WITH_MESSAGE",
            HL_PLAYER_FIRING: "PLAYER_FIRING", HL_REACTION_FIRE: "REACTION_FIRE", HL_NEW_SHOT: "NEW_SHOT",
            HL_NO_DAMAGE: "NO_DAMAGE", HL_SMALL_DAMAGE: "SMALL_DAMAGE", HL_BIG_DAMAGE: "BIG_DAMAGE"}
# The STR_HIT_LOG_* strings HitLog's constructor caches, and the weapon names the rows' PLAYER_FIRING entries carry.
# English (the host here; both machines in L5 / L7): bin/common/Language/OXCE/en-US.yml :315-:327 and
# bin/standard/xcom1/Language/en-US.yml; "New Turn", "Rifle", "=> " and "hit " are rendered by the running host
# itself in L1 (its own vanilla log), the weapon names by the running English client's own local weapon line at red.
STRINGS_EN = {"NEW_TURN": "New Turn", "REACTION_FIRE": "Reaction fire...", "NEW_BULLET": "=> ", "NO_DAMAGE": "0 ",
              "SMALL_DAMAGE": "hit ", "BIG_DAMAGE": "HIT "}
WEAPONS_EN = {"STR_RIFLE": "Rifle", "STR_STUN_ROD": "Stun Rod", "STR_PSI_AMP": "Psi-Amp",
              "STR_MIND_PROBE": "Mind Probe"}
# German (T0L-2): "Neue Runde" (STR_HIT_LOG_NEW_TURN) is rendered by the running German client's own next-turn
# screen (battle entry, L3) and "Gewehr" (STR_RIFLE) by its own weapon line at red (L2); "=> " and "Treffer"
# cannot be rendered by the client before S-L.2 and come from the de.yml it loads (common/Language/OXCE/de.yml
# :241-:251, deployed copy byte-equal to bin/common). No umlaut in any string a row reads.
STRINGS_DE = {"NEW_TURN": "Neue Runde", "REACTION_FIRE": "Reaktionsfeuer...", "NEW_BULLET": "=> ", "NO_DAMAGE": "0 ",
              "SMALL_DAMAGE": "Treffer", "BIG_DAMAGE": "TREFFER"}
WEAPONS_DE = {"STR_RIFLE": "Gewehr"}

# ----- the rows' pins -----
TURN0_SEQ = 3                    # T0L-1 (F4236, 3/3): the host's turn-0 NEW_TURN (phase Active) rides seq 3 (`reveal`)
L1_ENTRIES = 3                   # T0L-1: C1 = PLAYER_FIRING 'Rifle', NEW_SHOT, SMALL_DAMAGE (carriers seqs 9 / 10 / 11)
L1_ENTRY_TYPES = [(HL_PLAYER_FIRING, FACTION_PLAYER, ["STR_RIFLE"]), (HL_NEW_SHOT, FACTION_PLAYER, None),
                  (HL_SMALL_DAMAGE, FACTION_PLAYER, None)]
L2_ENTRIES = 3                   # T0L-1: C16 = NEW_SHOT, SMALL_DAMAGE today + S-L.2's partner weapon line (V6) first
L2_ENTRY_TYPES = L1_ENTRY_TYPES
TEXT_NEW_TURN_EN = STRINGS_EN["NEW_TURN"]
TEXT_NEW_TURN_DE = STRINGS_DE["NEW_TURN"]
# the renderings at each row's end (HitLog.cpp: PLAYER_FIRING writes "<weapon>\n\n" after pushing the previous text,
# its line breaks as spaces, to the turn diary; NEW_SHOT appends "=> "; a hit appends its damage class)
TEXT_L1_EN, DIARY_L1_EN = "Rifle\n\n=> hit ", ["New Turn"]
TEXT_L1_DE, DIARY_L1_DE = "Gewehr\n\n=> Treffer", ["Neue Runde"]
TEXT_L2_EN, DIARY_L2_EN = "Rifle\n\n=> hit ", ["New Turn", "Rifle  => hit "]
TEXT_L2_DE, DIARY_L2_DE = "Gewehr\n\n=> Treffer", ["Neue Runde", "Gewehr  => Treffer"]

# ----- L4 (Ctrl-H; BattlescapeState.cpp :3152-:3171, InfoboxState.h INFOBOX_DELAY 2000 ms) -----
SDLK_H = 104
BOX_OPEN_S = 1.5                 # the InfoboxState on top after the chord (it closes by itself after 2 s)
INFOBOX_CLICK_S = 1.0            # the closing click goes out within this of the box being seen (< INFOBOX_DELAY)
BOX_CLOSE_S = 1.0                # BattlescapeState back on top after the click

MIRROR_KEYS = ("noted", "sent", "applied", "localSuppressed", "pending", "dropped")


# ===================== the hit-log probes (shared with L5 / L7) =====================


def hl_log(gc):
    """battle_state `hitLog` of this machine as {text, diary} ({} when the probe is missing)."""
    h = battle_state(gc).get("hitLog")
    return {"text": h.get("text"), "diary": h.get("diary")} if isinstance(h, dict) else {}


def hl_mirror(gc):
    """event_state `hitLogMirror` of this machine ({} when the probe is missing)."""
    m = event_state(gc).get("hitLogMirror")
    return m if isinstance(m, dict) else {}


def hl_probe_fails(gc):
    """[] when this machine carries both S-L.1 probes with their full shape."""
    h = battle_state(gc).get("hitLog")
    m = event_state(gc).get("hitLogMirror")
    if (not isinstance(h, dict) or not isinstance(h.get("text"), str) or not isinstance(h.get("diary"), list)
            or not isinstance(m, dict) or not all(isinstance(m.get(k), int) for k in MIRROR_KEYS)
            or not isinstance(m.get("last"), list)):
        return [f"{gc.name} lacks the S-L.1 probes: battle_state.hitLog={h!r} event_state.hitLogMirror={m!r}"]
    return []


def hl_snap(host, client):
    """Both machines' log and mirror probe."""
    return {n: {"log": hl_log(gc), "mirror": hl_mirror(gc)} for n, gc in (("host", host), ("client", client))}


def hl_entry(e):
    """A mirror entry as (seq, t, f, k)."""
    k = e.get("k")
    return (e.get("seq"), e.get("t"), e.get("f"), list(k) if isinstance(k, list) else None)


def hl_entries(m, seq0=None):
    """The mirror's `last` entries (all, or those whose seq is above seq0) as (seq, t, f, k)."""
    return [hl_entry(e) for e in (m or {}).get("last") or [] if seq0 is None or (e.get("seq") or 0) > seq0]


def hl_count(m, key):
    return (m or {}).get(key) or 0


def hl_delta(s0, s1, who, key):
    return hl_count(s1[who]["mirror"], key) - hl_count(s0[who]["mirror"], key)


def hl_types(entries):
    """(t, f, k) of each entry - the shape the row pins compare."""
    return [(t, f, k) for _, t, f, k in entries]


def hl_render(entries, strings, weapons):
    """Vanilla HitLog (src/Savegame/HitLog.cpp) replayed over mirrored entries (seq, t, f, k): (text, diary). An
    unknown weapon key renders as <key> so a mismatch shows instead of raising."""
    st = {"ss": "", "diary": [], "last": HL_EMPTY, "faction": FACTION_PLAYER, "weapon": ""}

    def clear(reset_diary, ignore_last=False):
        if reset_diary:
            st["diary"] = []
        elif not ignore_last:
            st["diary"].append(st["ss"].replace("\n", " "))
        st["ss"] = ""

    for _, t, f, k in entries:
        if t == HL_NEW_TURN:
            clear(True)
            st["ss"] += strings["NEW_TURN"]
        elif t == HL_REACTION_FIRE:
            if st["last"] != HL_REACTION_FIRE:
                clear(False)
                st["ss"] += strings["REACTION_FIRE"] + "\n\n"
        elif t == HL_NEW_SHOT:
            if st["faction"] != f and f == FACTION_PLAYER:
                clear(False)
                st["ss"] += st["weapon"] + "\n\n"
            st["ss"] += strings["NEW_BULLET"]
        elif t == HL_NO_DAMAGE:
            st["ss"] += strings["NO_DAMAGE"]
        elif t == HL_SMALL_DAMAGE:
            st["ss"] += strings["SMALL_DAMAGE"]
        elif t == HL_BIG_DAMAGE:
            st["ss"] += strings["BIG_DAMAGE"]
        elif t == HL_NEW_TURN_MSG:
            clear(True)
            st["ss"] += "".join(weapons.get(x, f"<{x}>") for x in (k or []) if x)
        elif t == HL_PLAYER_FIRING:
            clear(False, st["last"] == HL_PLAYER_FIRING)
            st["weapon"] = weapons.get((k or [""])[0], f"<{(k or [''])[0]}>")
            st["ss"] += st["weapon"] + "\n\n"
        st["last"], st["faction"] = t, f
    return st["ss"], st["diary"]


def hl_view(s):
    """A snapshot for the EVIDENCE lines: each machine's log and its mirror counters and entries."""
    return {n: {"log": s[n]["log"], "counts": {k: s[n]["mirror"].get(k) for k in MIRROR_KEYS},
                "last": [[sq, HL_NAMES.get(t, t), f, k] for sq, t, f, k in hl_entries(s[n]["mirror"])]}
            for n in ("host", "client")}


def first_line(text):
    return (text or "").split("\n")[0]


# ===================== common =====================


def top(gc):
    return session.top_state(gc)


def units(gc):
    return session.units_by_id(battle_state(gc))


def common_snap(host, client):
    ec = event_state(client)
    return {"pushes": ec.get("coopClientBStatePushes"), "rng": ec.get("rngSeed")}


def common_fails(host, client, c0, what):
    """Per row: every bucket EQUAL, desyncSeen false on both, the client's coopClientBStatePushes unchanged and the
    host's 0, the client's rngSeed unchanged (V4)."""
    fails = []
    try:
        assert_hash_clean(host, client, full=True, what=what)
    except AssertionError as e:
        fails.append(f"{what}: hash_now full not clean: {short(e, 600)}")
    eh, ec = event_state(host), event_state(client)
    if eh.get("desyncSeen") or ec.get("desyncSeen"):
        fails.append(f"{what}: desyncSeen host={eh.get('desyncSeen')} client={ec.get('desyncSeen')} (want false)")
    if ec.get("coopClientBStatePushes") != c0["pushes"] or eh.get("coopClientBStatePushes") != 0:
        fails.append(f"{what}: coopClientBStatePushes client {c0['pushes']}->{ec.get('coopClientBStatePushes')} host "
                     f"{eh.get('coopClientBStatePushes')} (want the client's unchanged, the host's 0)")
    if c0["rng"] is None or ec.get("rngSeed") != c0["rng"]:
        fails.append(f"{what}: client rngSeed {c0['rng']} -> {ec.get('rngSeed')} (want unchanged: V4)")
    return fails


def finish(fails):
    if fails:
        raise AssertionError("; ".join(fails))


def mirror_row_fails(what, s0, s1, seq0, n_entries, types):
    """A row's mirror cells: the host sent exactly `n_entries` entries in the row whose (t, f, k) are `types`, none
    is pending; the client applied exactly the host's entries (same seq, t, f, k, in order, none twice: L-S2)."""
    fails = []
    hn, cn = hl_entries(s1["host"]["mirror"], seq0), hl_entries(s1["client"]["mirror"], seq0)
    sent, applied = hl_delta(s0, s1, "host", "sent"), hl_delta(s0, s1, "client", "applied")
    if sent != n_entries or hl_types(hn) != types:
        fails.append(f"{what}: the host sent +{sent} entries {hl_types(hn)} (want +{n_entries}: {types}, T0L-1)")
    if hl_count(s1["host"]["mirror"], "pending"):
        fails.append(f"{what}: the host's pending entries {hl_count(s1['host']['mirror'], 'pending')} at the row's end "
                     f"(want 0: every entry rides an emit of its own chain, T0L-1)")
    if applied != sent or cn != hn:
        fails.append(f"{what}: the client applied +{applied} entries {cn} (want exactly the host's +{sent} {hn})")
    return fails


def log_fails(what, who, log, text, diary, gist):
    if log.get("text") != text or log.get("diary") != diary:
        return [f"{what}: {who} hitLog text {log.get('text')!r} diary {log.get('diary')} (want {text!r} {diary}: "
                f"{gist})"]
    return []


def render_fails(what, s1):
    """The host's log == the English rendering of every entry it sent since boot, the client's == the German one."""
    fails = []
    sent = hl_entries(s1["host"]["mirror"])
    for who, strings, weapons in (("host", STRINGS_EN, WEAPONS_EN), ("client", STRINGS_DE, WEAPONS_DE)):
        want = hl_render(sent, strings, weapons)
        log = s1[who]["log"]
        if (log.get("text"), log.get("diary")) != want:
            fails.append(f"{what}: {who} hitLog {log.get('text')!r} {log.get('diary')} != the rendering of the "
                         f"host's sent entries {want[0]!r} {want[1]}")
    return fails


# ===================== rows =====================


def l1_host_snap(host, client, ctx):
    notes = []
    c0 = common_snap(host, client)
    s0 = hl_snap(host, client)
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    # C1's staging (test_w2_host_combat.c1_snap_kill): H rifle + clip, H and A teleported, A health 1, H TU max,
    # H firing 120, all on both machines (client first, F607)
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": C1_ITEMS[0], "ammo": C1_ITEMS[1],
                            "clear_hands": True}, ("weaponId", "ammoId"))
    tele_both(host, client, H_ID, C1_H_TILE, C1_H_DIR)
    tele_both(host, client, A_ID, C1_A_TILE, C1_A_DIR)
    both(host, client, {"cmd": "battle_set_unit_state", "unit": A_ID, "health": C1_A_HEALTH},
         ("health", "stun", "status"))
    tu_both(host, client, H_ID)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": H_ID, "stat": "firing",
                        "value": FIRING_120}, ("tu",))
    staged = diff_buckets(host, client)
    try:
        open_hand_menu_host(host)
        press(host, KEY_ITEM2)
        host.wait_for("host BattlescapeState on top after SNAP", lambda: top(host) == "BattlescapeState" or None,
                      timeout=5)
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
        time.sleep(0.15)
        pr = host.cmd({"cmd": "map_tile_click_pos", "x": C1_A_TILE[0], "y": C1_A_TILE[1], "z": C1_A_TILE[2]})
        assert pr.get("verified"), f"map_tile_click_pos did not verify A's tile {C1_A_TILE}: {pr}"
        host.ok({"cmd": "set_seed", "seed": SEED_C1})
        host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
        host.wait_for("host shot chain finished (A DEAD, no BState)",
                      lambda: host_chain_done(host, A_ID, STATUS_DEAD), timeout=30)
    except Exception as e:
        notes.append(f"L1 host snap: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"L1 wait_host_idle: {short(e)}")
    s1 = hl_snap(host, client)
    hev = [(e["seq"], e["kind"], e["actionId"]) for e in evs_since(host, seq0)]
    a = {n: unit_view(units(gc).get(A_ID)) for n, gc in (("host", host), ("client", client))}
    print("EVIDENCE L1: " + json.dumps({
        "seq0": seq0, "staged": {"rifle": g.get("weaponId"), "clip": g.get("ammoId"), "diff": staged},
        "hostEvs": hev, "A": a, "before": hl_view(s0), "after": hl_view(s1), "notes": notes},
        sort_keys=True, default=str), flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"L1: buckets differ after the staging: {staged} (want none)")
    if any((a[n] or {}).get("status") != STATUS_DEAD for n in a):
        fails.append(f"L1: precondition: A {a} (want DEAD on both: C1's kill)")
    # T0L-1 / F3932: both logs show the NEW_TURN rendering when the row starts
    fails += log_fails("L1", "host (row start)", s0["host"]["log"], TEXT_NEW_TURN_EN, [], "precondition, F3932")
    fails += log_fails("L1", "client (row start)", s0["client"]["log"], TEXT_NEW_TURN_DE, [], "precondition, F3932")
    # GREEN: the client renders the host's entries in German (the RED: they never reach it)
    fails += log_fails("L1", "client", s1["client"]["log"], TEXT_L1_DE, DIARY_L1_DE,
                       "the German rendering of the host's entries")
    fails += log_fails("L1", "host", s1["host"]["log"], TEXT_L1_EN, DIARY_L1_EN, "its own English rendering")
    fails += mirror_row_fails("L1", s0, s1, seq0, L1_ENTRIES, L1_ENTRY_TYPES)
    boot_entries = [e for e in hl_entries(s1["host"]["mirror"]) if (e[0] or 0) <= seq0]
    sent_total = hl_count(s1["host"]["mirror"], "sent")
    if sent_total != L1_ENTRIES + 1 or boot_entries != [(TURN0_SEQ, HL_NEW_TURN, FACTION_PLAYER, None)]:
        fails.append(f"L1: the host sent {sent_total} entries from boot, those before the row {boot_entries} (want "
                     f"{L1_ENTRIES + 1}, exactly the turn-0 NEW_TURN on seq {TURN0_SEQ}: T0L-1 F4236, P6-6 Q2 (a); "
                     f"no other entry on an equip sync, L-S5)")
    fails += render_fails("L1", s1)
    fails += common_fails(host, client, c0, "L1")
    finish(fails)


def l2_client_snap(host, client, ctx):
    notes = []
    c0 = common_snap(host, client)
    s0 = hl_snap(host, client)
    # C16's staging (test_w2_client_shoot.c16_snap_kill) on L1's boot: H back on its bring-up tile and facing (C1
    # left it on C_TILE), A2 stands in for A (dead since L1) on A_TILE; client first on every lever (F607)
    hx, hy, hz, hd = ctx["hHome"]
    uh = units(host).get(H_ID) or {}
    h_back = None
    if (uh.get("x"), uh.get("y"), uh.get("z")) != (hx, hy, hz):
        h_back = tele_both(host, client, H_ID, (hx, hy, hz), hd)
    aim0 = cancel_client_aim(client)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc_ = place(host, client, C_ID, C_TILE, C16_C_DIR)
    pa_ = place(host, client, A2_ID, A_TILE, A_DIR)
    both(host, client, {"cmd": "battle_set_unit_state", "unit": A2_ID, "health": A_HEALTH},
         ("health", "stun", "status"))
    set_tu_both(host, client, C_ID, TU_MAX)
    set_firing_both(host, client, C_ID)
    staged = diff_buckets(host, client)
    before = order_snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv = {}
    try:
        pv = aim_click(client, KEY_SNAP, A_TILE, lambda: host.ok({"cmd": "set_seed", "seed": SEED_C16}))
    except Exception as e:
        notes.append(f"L2 real-UI snap: {short(e)}")
    out = await_press(host, client, before, notes)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"L2 wait_host_idle: {short(e)}")
    s1 = hl_snap(host, client)
    hev = [(e["seq"], e["kind"], e["actionId"]) for e in evs_since(host, seq0)]
    a2 = {n: unit_view(units(gc).get(A2_ID)) for n, gc in (("host", host), ("client", client))}
    print("EVIDENCE L2: " + json.dumps({
        "seq0": seq0, "staged": {"hBack": h_back, "aimCancel": aim0, "rifle": rifle, "clip": clip, "C": pc_,
                                 "A2": pa_, "diff": staged},
        "press": {k: v for k, v in pv.items() if k != "clickAt"}, "outcome": out, "hostEvs": hev, "A2": a2,
        "before": hl_view(s0), "after": hl_view(s1), "notes": notes}, sort_keys=True, default=str), flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"L2: buckets differ after the staging: {staged} (want none)")
    if out.get("state") != "sent":
        fails.append(f"L2: precondition: the client's real-UI snap {out} (want sent as an order and finished)")
    # GREEN: the host logs the partner's weapon line; the client shows the host's log in German, its own line skipped
    fails += log_fails("L2", "host", s1["host"]["log"], TEXT_L2_EN, DIARY_L2_EN,
                       "a new line starting with the partner's weapon (V6)")
    fails += log_fails("L2", "client", s1["client"]["log"], TEXT_L2_DE, DIARY_L2_DE,
                       "the host's log in German, starting with the German weapon name")
    if hl_delta(s0, s1, "client", "localSuppressed") != 1:
        fails.append(f"L2: client localSuppressed +{hl_delta(s0, s1, 'client', 'localSuppressed')} (want +1: its own "
                     f"weapon line skipped, the host's entry replaces it, V7)")
    fails += mirror_row_fails("L2", s0, s1, seq0, L2_ENTRIES, L2_ENTRY_TYPES)
    fails += render_fails("L2", s1)
    fails += common_fails(host, client, c0, "L2")
    finish(fails)


def l4_ctrl_h(host, client, ctx):
    notes = []
    c0 = common_snap(host, client)
    sent0 = event_state(client).get("coopIntentsSent")
    aim0 = cancel_client_aim(client)
    sel0 = battle_state(client).get("selectedId")
    log0 = hl_log(client)
    top0 = top(client)
    # the closing click's spot: the selected soldier's own tile (a click there selects the selected unit again, so
    # nothing happens if it ever reached the map)
    client.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
    time.sleep(0.15)
    u = units(client).get(sel0) or {}
    pr = client.cmd({"cmd": "map_tile_click_pos", "x": u.get("x"), "y": u.get("y"), "z": u.get("z")})
    box = {"seen": False}
    t_key = time.time()
    client.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_H, "mod": "ctrl"})
    while time.time() - t_key < BOX_OPEN_S:
        lw = client.cmd({"cmd": "list_widgets"})
        if lw.get("state", "").endswith("::InfoboxState"):
            box.update(seen=True, seenAfterS=round(time.time() - t_key, 3), state=lw.get("state"),
                       texts=[w.get("text") for w in lw.get("widgets", []) if w.get("text")])
            break
        time.sleep(0.02)
    box["modClear"] = client.cmd({"cmd": "inject_input", "kind": "modstate", "mod": "none"}).get("modState")
    t_seen = time.time()
    if box["seen"] and pr.get("verified"):
        client.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
        box["clickAfterSeenS"] = round(time.time() - t_seen, 3)
        try:
            client.wait_for("client BattlescapeState on top after the click",
                            lambda: top(client) == "BattlescapeState" or None, timeout=BOX_CLOSE_S, interval=0.02)
        except Exception as e:
            notes.append(f"L4 close: {short(e)}")
    box["topAfter"] = top(client)
    ec = event_state(client)
    print("EVIDENCE L4: " + json.dumps({
        "top0": top0, "aimCancel": aim0, "selectedId": (sel0, battle_state(client).get("selectedId")),
        "clickPos": {k: pr.get(k) for k in ("verified", "winX", "winY")}, "clientLog": log0, "box": box,
        "intentsSent": (sent0, ec.get("coopIntentsSent")), "notes": notes}, sort_keys=True, default=str), flush=True)
    fails = list(notes)
    if top0 != "BattlescapeState" or not pr.get("verified"):
        fails.append(f"L4: precondition: client top {top0!r}, the click spot {pr} (want BattlescapeState, verified)")
    if not box["seen"]:
        fails.append(f"L4: no InfoboxState on the client within {BOX_OPEN_S}s of Ctrl-H (top {box['topAfter']!r}; want "
                     f"vanilla's hit-log box)")
    else:
        shown = box["texts"][0] if len(box.get("texts") or []) == 1 else box.get("texts")
        if shown != TEXT_L2_DE:
            fails.append(f"L4: the client's hit-log box shows {shown!r} (want {TEXT_L2_DE!r}: the host's entries in "
                         f"German)")
        if shown != log0.get("text"):
            fails.append(f"L4: the client's hit-log box shows {shown!r} (want its hitLog.text {log0.get('text')!r})")
        if box["topAfter"] != "BattlescapeState" or (box.get("clickAfterSeenS") or 0) > INFOBOX_CLICK_S:
            fails.append(f"L4: the box was not closed by one click: top after {box['topAfter']!r}, click sent "
                         f"{box.get('clickAfterSeenS')}s after the box was seen (want BattlescapeState, < "
                         f"{INFOBOX_CLICK_S}s)")
    if ec.get("coopIntentsSent") != sent0 or battle_state(client).get("selectedId") != sel0:
        fails.append(f"L4: the client sent {sent0} -> {ec.get('coopIntentsSent')} or changed its selection (want no "
                     f"order and the selection unchanged)")
    fails += common_fails(host, client, c0, "L4")
    finish(fails)


def l3_end_turn(host, client, ctx):
    notes = []
    c0 = common_snap(host, client)
    s0 = hl_snap(host, client)
    turn0 = end_turn_cycle(host, client, None, notes)
    s1 = hl_snap(host, client)
    hs, cs = battle_state(host), battle_state(client)
    print("EVIDENCE L3: " + json.dumps({
        "turn": (turn0, hs.get("turn"), hs.get("side"), cs.get("turn"), cs.get("side")),
        "hostPending": hl_count(s1["host"]["mirror"], "pending"), "before": hl_view(s0), "after": hl_view(s1),
        "notes": notes}, sort_keys=True, default=str), flush=True)
    fails = list(notes)
    if (hs.get("turn"), hs.get("side"), cs.get("turn"), cs.get("side")) != (
            (turn0 or 0) + 1, FACTION_PLAYER, (turn0 or 0) + 1, FACTION_PLAYER):
        fails.append(f"L3: precondition: turn/side host ({hs.get('turn')}, {hs.get('side')}) client ({cs.get('turn')}, "
                     f"{cs.get('side')}) (want the player side of turn {(turn0 or 0) + 1} on both)")
    fails += log_fails("L3", "host", s1["host"]["log"], TEXT_NEW_TURN_EN, [], "the NEW_TURN rendering")
    fails += log_fails("L3", "client", s1["client"]["log"], TEXT_NEW_TURN_DE, [], "the NEW_TURN rendering")
    fails += common_fails(host, client, c0, "L3")
    finish(fails)


SCENARIOS = (("L1", l1_host_snap), ("L2", l2_client_snap), ("L4", l4_ctrl_h), ("L3", l3_end_turn))


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} ({MISSION}, SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p6b-sl")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hs["units"] if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == SEATED, f"seated client units {seated_uids} (baked {SEATED})"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    ub = session.units_by_id(hs)
    for uid in (A_ID, A2_ID):
        u = ub.get(uid) or {}
        assert u.get("faction") == FACTION_HOSTILE and not u.get("isOut"), (
            f"alien {uid} at bring-up: {unit_view(u)} (want a live FACTION_HOSTILE unit)")
    for gc in (host, client):
        f = hl_probe_fails(gc)
        assert not f, f[0]
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    h = ub.get(H_ID) or {}
    ctx = {"hHome": (h.get("x"), h.get("y"), h.get("z"), h.get("direction"))}
    print(f"[w2p6b-sl] boot ok: {MISSION} MAP_FP={MAP_FP!r} turn={hs.get('turn')} seated={seated_uids} H={H_ID} home "
          f"{ctx['hHome']} pinned={len(pinned)} client options={CLIENT_OPTIONS} hitLog host={hl_log(host)} client="
          f"{hl_log(client)} mirror host={hl_mirror(host)} client={hl_mirror(client)}", flush=True)
    return ctx


def main():
    t0 = time.time()
    host = GameClient("host", HOST_PORT, make_user_dir("w2p6b_hit_log_host"))
    client = GameClient("client", CLIENT_PORT, make_user_dir("w2p6b_hit_log_client", options=CLIENT_OPTIONS))
    results = {}
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
                print(f"[w2p6b-sl] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_hit_log: {len(passed)}/{len(SCENARIOS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
