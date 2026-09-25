"""W2-P1 - test_w2_thin_client_tripwire.py: the second player's game never runs
battle simulation by itself (spec rewrite/prompts/w2p1_thin_client_tripwire.md
section (f), as amended by AMENDMENTS A1 and A2 - A2 wins where they differ;
findings F422, F432, F435-F441).

In a co-op battle only the HOST simulates. Before W2-P1 the CLIENT still ran
vanilla simulation on six paths, each of which changes the client's copy of
the battle alone. Seven scenarios, ONE boot, run on player turn 2 in the A2.2
order S6, S1, S3, STAGE, S2, S5, S7, S4 (STAGE is a fixture step, not a
scenario):

  S6 panic     The client's start-of-turn panic check (BattlescapeGame::think
               -> handlePanickingPlayer) must be SKIPPED on the client: the
               host resolves panic for every unit. Proves: the skip counter
               moves by exactly 1, no panic infobox opens on the client, and
               the panicking soldier C2 keeps its rifle on both machines.
  S1 prime     PRIME GRENADE from the client's action menu. Re-pointed by
               W2-P4 S-B (amendment C1 PR-Q3 (a), chain rule A.10): the prime
               is no longer refused but sent as a `prime` intent - vanilla's
               fuse screen opens locally (fuse 0), the host admits and runs
               it (host closedContexts gains exactly one {origin intent, kind
               prime, actorId C}), the fuse is 0 on both machines and C's TU
               stays equal on both machines.
  S3 scanner   USE SCANNER. Re-pointed by W2-P4 S-D (amendment C1 PR-Q3 (a),
               chain rule A.10): the choice is no longer refused but sent as
               a `use_item` intent - the host admits and runs it (host
               closedContexts gains exactly one {origin intent, kind scanner,
               actorId C}, whose evs are exactly the `scanner` cue {actor C,
               item} then one bt_action_end, each applied on the client with
               the same seq, kind and actionId), ScannerState opens on the
               client at its own order's end and never on the host, C's TU is
               spent and equal on both machines.
  STAGE        C -> S4_C_TILE facing S4_C_DIR, H -> S4_H_TILE (the tile C
               faces) facing C, battle_teleport_unit on BOTH machines, once,
               responses ok and equal (A2.1/A2.2).
  S2 medikit   USE MEDI-KIT (its target is H, standing on the tile C faces -
               vanilla STR_MEDI_KIT cannot target its own user, F439), then
               PAINKILLER. Re-pointed by W2-P4 S-D (amendment C3 D148, "Tripwire
               S2 re-point"): MedikitState opens locally and the press is a
               `medikit` intent - after the client's own bt_action_end the
               screen is still its top state (`continue: true`, H is
               standing), the host closed exactly one {origin intent, kind
               medikit, actorId C}, C's TU is before - 10 on both machines,
               the kit's painkiller count went 10 -> 9 on both, the banner is
               not the interim text; the cancel key then closes the screen
               locally with nothing sent.
  S5 reload    The reload hotkey (Options::keyBattleReload, read at run time
               from the client's own options.cfg). Re-pointed by W2-P4 S-D
               (amendment C1 PR-Q3 (a), chain rule A.10): the key is sent as a
               `reload` intent - the host closed exactly one {origin intent,
               kind reload, actorId C} whose evs are exactly one bt_action_end
               (applied on the client with the same seq, kind and actionId),
               the clip is loaded in the rifle on both machines and C's TU is
               before - 15 on both. C is stripped and gets its max TU on both
               machines first (C23e's staging): its own loadout carries a rifle
               clip vanilla's reload would pick first (F1132), and S3 and S2 now
               really spend TU, which would leave C below the reload's cost and
               S4's stun rod.
  S7 tripwire  The battle_fire lever, called for C2 on the CLIENT only, pushes
               UnitTurnBState then ProjectileFlyBState through statePushBack
               (A1.3): the tripwire refuses and counts BOTH (delta exactly 2),
               names the last refused site "statePushBack:<ProjectileFlyBState
               type name>", and the clip's ammo and C2's TU stay equal. The
               target is a floor tile inside C2's facing octant whose line of
               fire crosses no unit, so C2 does not turn and C keeps facing H
               (A2.2).
  S4 melee     LAST (A2.2/F440: its red knocks H out on the client and mints a
               body item there, shifting later client item ids). STUN (a stun
               rod, BA_HIT) against H on the tile C faces. Re-pointed by W2-P4
               S-C (amendment C1 PR-Q3 (a), chain rule A.10): the melee is no
               longer refused but sent as a `melee` intent - the host admits
               and runs it (host closedContexts gains exactly one {origin
               intent, kind melee, actorId C}, whose evs open with the `melee`
               cue {actor C, unit H} and end in exactly one bt_action_end, each
               applied on the client with the same seq, kind and actionId), no
               local MeleeAttackBState, C's TU is spent and equal on both
               machines, H's status / health / stun stay equal on both.

Every scenario also ends with: hash_now {full:true} - ALL buckets EQUAL on
both machines (never a hard-coded bucket count), desyncSeen false on both,
and coopClientBStatePushes unchanged on both machines (S7: client delta
exactly 2).

FIXTURE (A1.5, deterministic - never searched here). The boot is the classic
parallel skirmish bring-up test_rw_seat_pacing.py's Boot A uses (host +
client, seat_count=2 so the client owns two soldiers), pinned with set_seed
SEED right before newbattle_ok, asserted against the baked MAP_FP, then
session.pin_ai_neutral. C / C2 are the two client-seated soldiers (in
seating order), H the first host-seat soldier; their ids are asserted
against the baked values. The STAGE tiles (C's tile + facing, H on the tile
C faces, facing C) and S7's floor target tile (from C2's tile and facing at
the S7 point) were computed by scratch precalc boots on SEED and are baked
below; the test teleports with battle_teleport_unit on BOTH machines and
asserts each response. Every item is given with battle_give on BOTH machines
in the same order and the returned ids are asserted equal. Before each of
S1-S5 and S7 the acting unit's TU (C, or C2 for S7) is set on BOTH machines
to the host's own value (battle_set_unit_state tu; A2.3/F441; S5: C's max
TU on both, W2-P4 S-D) so every
scenario starts from the same TU on both machines - on the red build the
client spends TU locally, and without this an earlier scenario's red would
starve a later one of the TU its own red needs.

Driving (A1.1). The action-menu rows are ActionMenuItem (not TextButton), so
a row is pressed by its keyboard shortcut: TAB-select C on the client
(test_rw_seat_pacing.tab_select), click_widget nth=25 (the right-hand box,
self-verified against its rect centre), confirm ActionMenuState is on top,
then inject the row's key. A scenario whose red path opens a vanilla modal
on the client (fuse screen, MedikitState, ScannerState, a panic infobox, an
OK infobox) completes that vanilla interaction - fuse 0, PAINKILLER, ESC,
the infobox's own 2 s timer, or the OK button - and returns the client to
BattlescapeState before the next scenario (A1.6); any infobox text is read
(list_widgets) before it closes and printed in the EVIDENCE line. That is
observation of what happened, never a second press of the same action.

RED-THEN-GREEN (spec (d)). Commit 1 (this file, the event_state probes and
the battle_set_unit_state status/panicPending fields - no product behaviour)
is run ONCE and EVERY scenario must FAIL with its named red evidence
(section (f) "RED on commit 1"). Commit 2 (the tripwire, the panic skip, the
two refusals, the strings) is run ONCE and every scenario must PASS. Each
scenario prints ONE "EVIDENCE S<n>:" line with the fields section (f) names
for BOTH machines BEFORE asserting its green conditions, so the red table
is readable straight off the log; main() runs every scenario even after an
earlier one failed and prints "PASS S<n>" / "FAIL S<n>: <message>".

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all seven scenarios pass,
2 otherwise (a bring-up failure is also 2).

Run:  python tools/coop_test/test_w2_thin_client_tripwire.py
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_rw_turn_baton import (RHAND_NTH, RHAND_RECT, ACTION_MENU_STATE,
                                click_nth, drive_full_cycle, dismiss_next_turn_if_present)
from test_rw_seat_pacing import tab_select
from test_w2_host_combat import evs_since           # W2-P4 S-C: the S4 re-point's chain
from test_w2_ai_origins import host_payloads        # W2-P4 S-C: the S4 re-point's `melee` cue

# ----- baked fixture constants (scratch precalc boot on SEED, A1.5) -----
SEED = 1
MAP_FP = -4.48310638993e+18          # host battle_state.mapFingerprint on SEED
C_ID = 8                              # first client-seated soldier's unit id
C2_ID = 9                             # second client-seated soldier's unit id
H_ID = 10                             # first host-seat (coop 0) soldier's unit id
S4_C_TILE = (13, 11, 0)               # STAGE: open ground, >= 8 tiles from every unit
S4_C_DIR = 2                          # east: faces S4_H_TILE
S4_H_TILE = (14, 11, 0)               # the tile C faces
S4_H_DIR = 6                          # west: faces C
S7_TARGET = (15, 17, 0)               # A2.2: floor tile 2 north of C2 (15,19,1) facing 0,
                                      # no unit on the line; C2 does not turn

PORT = "48530"
FACTION_PLAYER = 0
COOP_SEAT_0 = 0

STATUS_STANDING = 0                   # src/Mod/Unit.h enum UnitStatus
STATUS_PANICKING = 8

# A1.1 key symbols (fresh make_user_dir defaults).
KEY_ACTION_ITEM1 = 49                 # keyBattleActionItem1: PRIME / USE MEDI-KIT / USE SCANNER
KEY_ACTION_ITEM4 = 52                 # keyBattleActionItem4: STUN (BA_HIT)
KEY_FUSE_0 = 48                       # PrimeGrenadeState button 0 (SDLK_0)
KEY_PAINKILLER = 49                   # MedikitState painkiller button (SDLK_1)
KEY_CANCEL = 27                       # Options::keyCancel (ScannerState / MedikitState close)

TEXT_ITEM_ACTION = "Only the host can use this item"   # STR_COOP_ITEM_ACTION_HOST_ONLY
TEXT_RELOAD = "Only the host can reload"                # STR_COOP_RELOAD_HOST_ONLY
# W2-P4 S-D re-points: both interim keys above are RETIRED (the texts stay here
# only as "not the interim refusal" checks).
MEDIKIT_TU = 10                       # STR_MEDI_KIT tuUse 10 flat (items.rul; T0-19 = F1250: "TU before - 10")
RELOAD_TU = 15                        # STR_RIFLE's clip load from STR_BELT (T0-9: 15, C23e)
TU_MAX = 255                          # battle_set_unit_state tu: clamped to the unit's max TU

DIR_DX = [0, 1, 1, 1, 0, -1, -1, -1]
DIR_DY = [-1, -1, 0, 1, 1, 1, 0, -1]


# ===================== small probes =====================


def top(gc):
    return session.top_state(gc)


def units(gc):
    return session.units_by_id(battle_state(gc))


def items(gc):
    r = gc.cmd({"cmd": "battle_items"})
    assert r.get("ok"), f"battle_items failed on {gc.name}: {r}"
    return {i["id"]: i for i in r["items"]}


def probes(gc):
    es = event_state(gc)
    bs = battle_state(gc)
    return {
        "pushes": es.get("coopClientBStatePushes"),
        "lastSite": es.get("coopClientBStateLastSite"),
        "panicSkipped": es.get("coopClientPanicSkipped"),
        "desync": es.get("desyncSeen"),
        "banner": bs.get("coopWaitText"),
        "warning": bs.get("warningText"),
        "pending": bs.get("pendingStates"),
        "panicHandled": bs.get("panicHandled"),
    }


def press(gc, key):
    gc.ok({"cmd": "inject_input", "kind": "key", "key": key})


def watch_top(gc, done, timeout, seen):
    """Poll gc's top state (every 0.05 s, bounded) until done(top) holds,
    appending each distinct state to `seen`. Returns whether done() held."""
    deadline = time.time() + timeout
    while True:
        st = top(gc)
        if not seen or seen[-1] != st:
            seen.append(st)
        if done(st):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.05)


def infobox_text(gc):
    """Every non-empty caption on gc's top state (list_widgets Text /
    TextButton), for the EVIDENCE line of a scenario that raised an infobox."""
    lw = gc.cmd({"cmd": "list_widgets"})
    return [w["text"] for w in lw.get("widgets", []) if w.get("text")]


def settle_client(client, seen, timeout=20, texts=None):
    """Wait (bounded) until the client is back on BattlescapeState with no
    live BState and its panic check done, recording every top state seen;
    then a short settle so the post-popup handleNonTargetAction() has run.
    Each NEWLY seen infobox has its text read into `texts` first; an
    InfoboxOKState (it waits for OK) is then closed through its OK button -
    the A1.6 vanilla completion. Returns whether it settled."""
    texts = [] if texts is None else texts
    deadline = time.time() + timeout
    ok = False
    while time.time() < deadline:
        st = top(client)
        if not seen or seen[-1] != st:
            seen.append(st)
            if st and "Infobox" in st:
                texts.append((st, infobox_text(client)))
                if st == "InfoboxOKState":
                    client.cmd({"cmd": "click_widget", "match": "ok"})
        bs = battle_state(client)
        if (st == "BattlescapeState" and bs.get("pendingStates") == 0
                and bs.get("panicHandled")):
            ok = True
            break
        time.sleep(0.05)
    time.sleep(0.5)
    st = top(client)
    if seen[-1] != st:
        seen.append(st)
    return ok


def give_both(host, client, req):
    """battle_give on BOTH machines in the same order; ids asserted equal."""
    full = dict(req, cmd="battle_give")
    rc = client.cmd(full)  # F607: client first, then host
    rh = host.cmd(full)
    assert rh.get("ok") and rc.get("ok"), f"PREMISE: battle_give {req} failed: host={rh} client={rc}"
    assert (rh.get("weaponId"), rh.get("ammoId")) == (rc.get("weaponId"), rc.get("ammoId")), (
        f"PREMISE: battle_give {req} minted different ids: host={rh} client={rc}")
    return rh["weaponId"], rh["ammoId"]


def equalize_tu(host, client, uid):
    """Both machines get the HOST's current TU for `uid` (see the docstring's
    FIXTURE note). Returns that value."""
    tu = units(host)[uid]["tu"]
    for gc in (client, host):  # F607: client first, then host
        r = gc.cmd({"cmd": "battle_set_unit_state", "unit": uid, "tu": tu})
        assert r.get("ok") and r.get("tu") == tu, (
            f"PREMISE: battle_set_unit_state tu={tu} unit {uid} on {gc.name}: {r}")
    return tu


def wait_banner_not(client, text, timeout=10):
    """Non-vacuity for the banner assertion: the client's banner must NOT
    already read `text` (an earlier scenario's refusal dwells 6 s) before
    this scenario's press."""
    client.wait_for(f"client banner is not {text!r} before the press",
                    lambda: battle_state(client).get("coopWaitText") != text or None,
                    timeout=timeout)


def open_right_hand_menu(client):
    """A1.1: TAB-select C, click the right-hand box (nth 25, rect-verified),
    confirm ActionMenuState is on top. Returns the seen-states list."""
    assert tab_select(client, C_ID), (
        f"PREMISE: TAB never selected C ({C_ID}) on the client: "
        f"selectedId={battle_state(client).get('selectedId')}")
    r = click_nth(client, RHAND_NTH)
    want = (RHAND_RECT[0] + RHAND_RECT[2] // 2, RHAND_RECT[1] + RHAND_RECT[3] // 2)
    assert (r.get("baseX"), r.get("baseY")) == want, (
        f"PREMISE: click_widget nth={RHAND_NTH} did not land on the right-hand box "
        f"centre {want}: {r}")
    client.wait_for("client ActionMenuState on top",
                    lambda: client.cmd({"cmd": "list_widgets"}).get("state") == ACTION_MENU_STATE
                    or None, timeout=5)
    return ["ActionMenuState"]


def common_tail(host, client, fails, pushes0, push_delta=0, what=""):
    """Every scenario's closing conditions: all hash buckets EQUAL, desyncSeen
    false on both, coopClientBStatePushes delta == push_delta on the client and
    0 on the host."""
    try:
        assert_hash_clean(host, client, full=True, what=what)
    except AssertionError as e:
        fails.append(str(e).split("\n")[0])
    ph, pc = probes(host), probes(client)
    if not (ph["desync"] is False and pc["desync"] is False):
        fails.append(f"desyncSeen host={ph['desync']} client={pc['desync']} (want False/False)")
    dh = (ph["pushes"] or 0) - (pushes0[0] or 0)
    dc = (pc["pushes"] or 0) - (pushes0[1] or 0)
    if dh != 0 or dc != push_delta:
        fails.append(f"coopClientBStatePushes delta host={dh} client={dc} "
                     f"(want 0/{push_delta}; raw host={ph['pushes']} client={pc['pushes']})")


def finish(fails):
    if fails:
        raise AssertionError(" | ".join(fails))


def uv(u, k):
    return u.get(k) if u else None


def hfields(u):
    """A unit's status / health / stun / isOut (A2.2's S4 fields), plus tu."""
    return {k: u.get(k) for k in ("status", "health", "stun", "isOut", "tu")}


def loaded_ammo(item, weapon_id):
    """The ammo items actually loaded in a weapon. battle_items' `ammo` lists
    every non-null ammo slot, and a slot with no compatible ammo points at the
    weapon ITSELF (BattleItem ctor, `_ammoItem[slot] = this`), so an empty
    STR_RIFLE reads [rifle, rifle, rifle]; the weapon's own id is dropped."""
    return [a for a in item.get("ammo", []) if a != weapon_id]


# ===================== the seven scenarios =====================


def s6_panic(host, client, ctx):
    rifle, clip = give_both(host, client, {"unit": C2_ID, "item": "STR_RIFLE",
                                           "ammo": "STR_RIFLE_CLIP", "clear_hands": True})
    for gc in (client, host):  # F607: client first, then host
        r = gc.cmd({"cmd": "battle_set_unit_state", "unit": C2_ID, "status": STATUS_PANICKING})
        assert r.get("ok") and r.get("status") == STATUS_PANICKING, (
            f"PREMISE: status PANICKING on {gc.name}: {r}")
    p0h, p0c = probes(host), probes(client)
    uh0, uc0 = units(host)[C2_ID], units(client)[C2_ID]
    r = client.cmd({"cmd": "battle_set_unit_state", "unit": C2_ID, "panicPending": True})
    assert r.get("ok"), f"PREMISE: panicPending on the client: {r}"
    seen, texts = [], []
    settled = settle_client(client, seen, timeout=30, texts=texts)
    ph, pc = probes(host), probes(client)
    uh, uc = units(host)[C2_ID], units(client)[C2_ID]
    ih, ic = items(host), items(client)
    rh, rc = ih.get(rifle), ic.get(rifle)
    print(f"EVIDENCE S6: C2={C2_ID} panicPending-reply={r.get('panicPending')} "
          f"client-states={seen} infobox-text={texts} settled={settled} "
          f"panicSkipped client {p0c['panicSkipped']}->{pc['panicSkipped']} host "
          f"{p0h['panicSkipped']}->{ph['panicSkipped']}; "
          f"C2.status host {uh0['status']}->{uh['status']} client {uc0['status']}->{uc['status']}; "
          f"C2.tu host {uh0['tu']}->{uh['tu']} client {uc0['tu']}->{uc['tu']}; "
          f"C2.pos host ({uh['x']},{uh['y']},{uh['z']}) client ({uc['x']},{uc['y']},{uc['z']}); "
          f"rifle {rifle} host owner={uv(rh, 'owner')} slot={uv(rh, 'slot')} "
          f"client owner={uv(rc, 'owner')} slot={uv(rc, 'slot')} onTile={uv(rc, 'onTile')}; "
          f"client warning={pc['warning']!r} banner={pc['banner']!r}; "
          f"pushes client {p0c['pushes']}->{pc['pushes']}", flush=True)
    # A1.2 (iii): back to STANDING on both, whatever happened above.
    for gc in (client, host):  # F607: client first, then host
        rr = gc.cmd({"cmd": "battle_set_unit_state", "unit": C2_ID, "status": STATUS_STANDING})
        assert rr.get("ok"), f"PREMISE: status STANDING on {gc.name}: {rr}"
    fails = []
    if not settled:
        fails.append(f"client never settled on BattlescapeState (states {seen})")
    d = (pc["panicSkipped"] or 0) - (p0c["panicSkipped"] or 0)
    if d != 1:
        fails.append(f"coopClientPanicSkipped delta {d} (want exactly 1)")
    if "InfoboxState" in seen:
        fails.append(f"a panic infobox opened on the client (states {seen})")
    for name, it in (("host", rh), ("client", rc)):
        if not it or it.get("owner") != C2_ID or it.get("slot") != "STR_RIGHT_HAND":
            fails.append(f"rifle {rifle} not in C2's right hand on {name}: {it}")
    common_tail(host, client, fails, (p0h["pushes"], p0c["pushes"]), what="S6")
    finish(fails)


def prime_contexts(host, ctx0):
    """W2-P4 S-B (S1 re-point): the host's NEW closedContexts records that are
    C's admitted prime intent ({origin intent, kind prime, actorId C})."""
    seen0 = {c.get("actionId") for c in ctx0}
    return [c for c in (event_state(host).get("closedContexts") or []) if c.get("actionId") not in seen0
            and c.get("origin") == "intent" and c.get("kind") == "prime" and c.get("actorId") == C_ID]


def s1_prime(host, client, ctx):
    equalize_tu(host, client, C_ID)
    gid, _ = give_both(host, client, {"unit": C_ID, "item": "STR_GRENADE", "clear_hands": True})
    wait_banner_not(client, TEXT_ITEM_ACTION)
    seen = open_right_hand_menu(client)
    p0h, p0c = probes(host), probes(client)
    ctx0 = event_state(host).get("closedContexts") or []
    tu0 = (units(host)[C_ID]["tu"], units(client)[C_ID]["tu"])
    f0 = (items(host)[gid]["fuse"], items(client)[gid]["fuse"])
    press(client, KEY_ACTION_ITEM1)
    watch_top(client, lambda st: st != "ActionMenuState", 5, seen)
    if seen[-1] == "PrimeGrenadeState":
        press(client, KEY_FUSE_0)
        watch_top(client, lambda st: st != "PrimeGrenadeState", 5, seen)
    settled = settle_client(client, seen)
    # W2-P4 S-B (C1 PR-Q3 (a)): the prime is an order now - wait (bounded) for
    # the host's intent context to close and the client to apply everything.
    order_note = ""
    try:
        client.wait_for("C's prime intent closed on the host and applied on the client",
                        lambda: (prime_contexts(host, ctx0) and event_state(client).get("inFlight") is None
                                 and event_state(client).get("lastSeqApplied")
                                 == event_state(host).get("lastSeqEmitted")) or None, timeout=15, interval=0.1)
    except Exception as e:
        order_note = f"{type(e).__name__}: {e}"
    pctx = prime_contexts(host, ctx0)
    ph, pc = probes(host), probes(client)
    tu1 = (units(host)[C_ID]["tu"], units(client)[C_ID]["tu"])
    f1 = (items(host)[gid]["fuse"], items(client)[gid]["fuse"])
    print(f"EVIDENCE S1: grenade={gid} client-states={seen} settled={settled} "
          f"prime contexts={pctx} orderWait={order_note!r} "
          f"fuse host {f0[0]}->{f1[0]} client {f0[1]}->{f1[1]}; "
          f"C.tu host {tu0[0]}->{tu1[0]} client {tu0[1]}->{tu1[1]}; "
          f"client banner={pc['banner']!r} warning={pc['warning']!r}; "
          f"pushes client {p0c['pushes']}->{pc['pushes']} lastSite={pc['lastSite']!r}", flush=True)
    fails = []
    if len(pctx) != 1:
        fails.append(f"host closedContexts gained {len(pctx)} {{origin intent, kind prime, actorId {C_ID}}} "
                     f"(want exactly 1; wait: {order_note!r})")
    if "PrimeGrenadeState" not in seen:
        fails.append(f"the fuse screen never opened on the client (states {seen})")
    if f1 != (0, 0):
        fails.append(f"fuse host={f1[0]} client={f1[1]} (want 0/0)")
    if tu1[0] != tu1[1]:
        fails.append(f"C.tu host={tu1[0]} client={tu1[1]} (want equal)")
    if not settled:
        fails.append(f"client never settled on BattlescapeState (states {seen})")
    common_tail(host, client, fails, (p0h["pushes"], p0c["pushes"]), what="S1")
    finish(fails)


def intent_contexts(host, ctx0, kind):
    """W2-P4 S-D (S2 / S3 / S5 re-points): the host's NEW closedContexts records
    that are C's admitted intent of context kind `kind` ({origin intent, kind,
    actorId C})."""
    seen0 = {c.get("actionId") for c in ctx0}
    return [c for c in (event_state(host).get("closedContexts") or []) if c.get("actionId") not in seen0
            and c.get("origin") == "intent" and c.get("kind") == kind and c.get("actorId") == C_ID]


def wait_intent_done(host, client, ctx0, kind, timeout=15):
    """W2-P4 S-D: wait (bounded) until C's `kind` intent context has closed on the
    host and the client has applied everything the host emitted (the client's
    own bt_action_end included). Returns "" or the wait's failure text."""
    try:
        client.wait_for(f"C's {kind} intent closed on the host and applied on the client",
                        lambda: (intent_contexts(host, ctx0, kind) and event_state(client).get("inFlight") is None
                                 and event_state(client).get("lastSeqApplied")
                                 == event_state(host).get("lastSeqEmitted")) or None, timeout=timeout, interval=0.1)
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    return ""


def pk_count(its, iid):
    """A medi-kit's painkiller charge (battle_items `medikit` [painKiller, heal,
    stimulant], S-D.1)."""
    mk = (its.get(iid) or {}).get("medikit")
    return mk[0] if mk else None


def s2_medikit(host, client, ctx):
    equalize_tu(host, client, C_ID)
    mid, _ = give_both(host, client, {"unit": C_ID, "item": "STR_MEDI_KIT", "clear_hands": True})
    wait_banner_not(client, TEXT_ITEM_ACTION)
    seen = open_right_hand_menu(client)
    p0h, p0c = probes(host), probes(client)
    ctx0 = event_state(host).get("closedContexts") or []
    uh, uc = units(host), units(client)
    tu0 = (uh[C_ID]["tu"], uc[C_ID]["tu"])
    h0 = (hfields(uh[H_ID]), hfields(uc[H_ID]))
    pk0 = (pk_count(items(host), mid), pk_count(items(client), mid))
    fronts = {}
    for name, us in (("host", uh), ("client", uc)):
        c = us[C_ID]
        ft = (c["x"] + DIR_DX[c["direction"]], c["y"] + DIR_DY[c["direction"]], c["z"])
        occ = [u["id"] for u in us.values()
               if not u.get("isOut") and (u["x"], u["y"], u["z"]) == ft]
        fronts[name] = (c["x"], c["y"], c["z"], c["direction"], ft, occ)
    medikit_text = []
    order_note = ""
    top_after = None
    cancel = {}
    press(client, KEY_ACTION_ITEM1)
    watch_top(client, lambda st: st != "ActionMenuState", 5, seen)
    if seen[-1] == "MedikitState":
        medikit_text.append(("open", infobox_text(client)))
        press(client, KEY_PAINKILLER)
        # W2-P4 S-D (amendment C3 D148): the painkiller is an order now - wait for
        # the client's own bt_action_end instead of a fixed sleep.
        order_note = wait_intent_done(host, client, ctx0, "medikit")
        top_after = top(client)
        if top_after == "MedikitState":
            medikit_text.append(("after PAINKILLER", infobox_text(client)))
            cancel["before"] = (event_state(client).get("coopIntentsSent"), event_state(host).get("lastSeqEmitted"))
            press(client, KEY_CANCEL)
        watch_top(client, lambda st: st != "MedikitState", 5, seen)
        time.sleep(0.5)
        cancel["after"] = (event_state(client).get("coopIntentsSent"), event_state(host).get("lastSeqEmitted"))
        cancel["top"] = top(client)
    settled = settle_client(client, seen)
    mctx = intent_contexts(host, ctx0, "medikit")
    ph, pc = probes(host), probes(client)
    halt_c = event_state(client).get("lastActionHalt") or {}
    uh1, uc1 = units(host), units(client)
    tu1 = (uh1[C_ID]["tu"], uc1[C_ID]["tu"])
    h1 = (hfields(uh1[H_ID]), hfields(uc1[H_ID]))
    pk1 = (pk_count(items(host), mid), pk_count(items(client), mid))
    print(f"EVIDENCE S2: medikit={mid} client-states={seen} settled={settled} "
          f"target (C x,y,z,dir, faced tile, occupant ids) host={fronts['host']} "
          f"client={fronts['client']} (H={H_ID}); medikit-screen-text={medikit_text}; "
          f"medikit contexts={mctx} orderWait={order_note!r} top after the answer={top_after!r} "
          f"client lastActionHalt={halt_c} cancel={cancel}; "
          f"painkiller host {pk0[0]}->{pk1[0]} client {pk0[1]}->{pk1[1]}; "
          f"C.tu host {tu0[0]}->{tu1[0]} client {tu0[1]}->{tu1[1]}; "
          f"H host {h0[0]}->{h1[0]} client {h0[1]}->{h1[1]}; "
          f"client banner={pc['banner']!r} warning={pc['warning']!r}; "
          f"pushes client {p0c['pushes']}->{pc['pushes']} lastSite={pc['lastSite']!r}", flush=True)
    fails = []
    # W2-P4 S-D (amendment C3 D148 "Tripwire S2 re-point", chain rule A.10): the
    # medi-kit screen opens locally and the painkiller press is an order the host
    # runs; the screen stays open on the answer (`continue: true`, H is standing).
    if "MedikitState" not in seen or top_after != "MedikitState":
        fails.append(f"MedikitState did not open and stay the client's top state after the answer (states {seen}, "
                     f"top after the answer {top_after!r})")
    if halt_c.get("actionId") != (mctx[0].get("actionId") if len(mctx) == 1 else None) or halt_c.get(
            "continue") is not True:
        fails.append(f"client lastActionHalt {halt_c} (want the medikit order's end with continue true)")
    if len(mctx) != 1:
        fails.append(f"host closedContexts gained {len(mctx)} {{origin intent, kind medikit, actorId {C_ID}}} "
                     f"(want exactly 1; wait: {order_note!r})")
    if tu1 != (tu0[0] - MEDIKIT_TU, tu0[0] - MEDIKIT_TU):
        fails.append(f"C.tu host {tu0[0]}->{tu1[0]} client {tu0[1]}->{tu1[1]} (want before - {MEDIKIT_TU} on both)")
    if pk0 != (10, 10) or pk1 != (9, 9):
        fails.append(f"kit {mid} painkiller host {pk0[0]}->{pk1[0]} client {pk0[1]}->{pk1[1]} (want 10 -> 9 on both)")
    if pc["banner"] == TEXT_ITEM_ACTION:
        fails.append(f"client banner {pc['banner']!r} (the interim host-only refusal: want the press sent as an "
                     f"order)")
    if cancel.get("top") != "BattlescapeState" or "before" not in cancel or cancel["before"] != cancel.get("after"):
        fails.append(f"the cancel key did not close the screen locally with nothing sent ({cancel})")
    if tu1[0] != tu1[1]:
        fails.append(f"C.tu host={tu1[0]} client={tu1[1]} (want equal)")
    if not settled:
        fails.append(f"client never settled on BattlescapeState (states {seen})")
    common_tail(host, client, fails, (p0h["pushes"], p0c["pushes"]), what="S2")
    finish(fails)


def s3_scanner(host, client, ctx):
    equalize_tu(host, client, C_ID)
    sid_, _ = give_both(host, client, {"unit": C_ID, "item": "STR_MOTION_SCANNER", "clear_hands": True})
    wait_banner_not(client, TEXT_ITEM_ACTION)
    seen = open_right_hand_menu(client)
    p0h, p0c = probes(host), probes(client)
    ctx0 = event_state(host).get("closedContexts") or []
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    tu0 = (units(host)[C_ID]["tu"], units(client)[C_ID]["tu"])
    press(client, KEY_ACTION_ITEM1)
    watch_top(client, lambda st: st != "ActionMenuState", 5, seen)
    # W2-P4 S-D (C1 PR-Q3 (a), chain rule A.10): the scanner is an order now -
    # wait (bounded) for the host's intent context to close and the client to
    # apply everything; the client's ScannerState opens at its own end (Q14 = a).
    order_note = wait_intent_done(host, client, ctx0, "scanner")
    watch_top(client, lambda st: st == "ScannerState", 5, seen)
    tops = {"host": top(host), "client": top(client)}
    if seen[-1] == "ScannerState":
        time.sleep(0.5)
        press(client, KEY_CANCEL)
        watch_top(client, lambda st: st != "ScannerState", 5, seen)
    settled = settle_client(client, seen)
    sctx = intent_contexts(host, ctx0, "scanner")
    aid = sctx[0].get("actionId") if len(sctx) == 1 else None
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    chain = [e for e in hev if aid is not None and e["actionId"] == aid]
    cmap = {e["seq"]: e for e in cev}
    sseqs = [e["seq"] for e in chain if e["kind"] == "scanner"]
    pl = host_payloads(host, sseqs) if sseqs else {}
    scanner_cue = ((pl.get(sseqs[0]) or {}).get("payload") or {}) if sseqs else {}
    ph, pc = probes(host), probes(client)
    tu1 = (units(host)[C_ID]["tu"], units(client)[C_ID]["tu"])
    print(f"EVIDENCE S3: scanner={sid_} client-states={seen} settled={settled} tops at the answer={tops} "
          f"scanner contexts={sctx} orderWait={order_note!r} chain={[(e['seq'], e['kind']) for e in chain]} "
          f"client chain={[(s, (cmap.get(s) or {}).get('kind'), (cmap.get(s) or {}).get('actionId')) for s in [e['seq'] for e in chain]]} "
          f"scanner cue={scanner_cue}; "
          f"C.tu host {tu0[0]}->{tu1[0]} client {tu0[1]}->{tu1[1]}; "
          f"client banner={pc['banner']!r} warning={pc['warning']!r}; "
          f"pushes client {p0c['pushes']}->{pc['pushes']} lastSite={pc['lastSite']!r}", flush=True)
    fails = []
    if len(sctx) != 1:
        fails.append(f"host closedContexts gained {len(sctx)} {{origin intent, kind scanner, actorId {C_ID}}} "
                     f"(want exactly 1; wait: {order_note!r})")
    kinds = [e["kind"] for e in chain]
    if aid is not None and kinds != ["scanner", "bt_action_end"]:
        fails.append(f"host evs of actionId {aid} = {kinds} (want exactly the `scanner` cue, then one bt_action_end)")
    bad = [(e["seq"], e["kind"], cmap.get(e["seq"])) for e in chain
           if not cmap.get(e["seq"]) or cmap[e["seq"]]["kind"] != e["kind"] or cmap[e["seq"]]["actionId"] != aid]
    if bad:
        fails.append(f"client event_log does not hold the host's evs of actionId {aid}: (seq, kind, client)={bad}")
    if aid is not None and (scanner_cue.get("actor"), scanner_cue.get("item")) != (C_ID, sid_):
        fails.append(f"`scanner` cue payload {scanner_cue} (want actor {C_ID}, item {sid_})")
    if pc["banner"] == TEXT_ITEM_ACTION:
        fails.append(f"client banner {pc['banner']!r} (the interim host-only refusal: want the press sent as "
                     f"an order)")
    if tops["client"] != "ScannerState" or tops["host"] == "ScannerState":
        fails.append(f"top states at the answer {tops} (want ScannerState on the client only, opened at its own "
                     f"order's end)")
    if tu1[0] != tu1[1] or tu1[0] >= tu0[0]:
        fails.append(f"C.tu host={tu1[0]} client={tu1[1]} before={tu0} (want spent by the host's scanner and "
                     f"equal on both)")
    if not settled:
        fails.append(f"client never settled on BattlescapeState (states {seen})")
    common_tail(host, client, fails, (p0h["pushes"], p0c["pushes"]), what="S3")
    finish(fails)


def stage(host, client, ctx):
    """A2.2 STAGE (not a scenario): C -> S4_C_TILE facing S4_C_DIR, H ->
    S4_H_TILE (the tile C faces) facing C, on BOTH machines, once; every
    response ok and equal."""
    tele = {}
    for uid, tile, d in ((C_ID, S4_C_TILE, S4_C_DIR), (H_ID, S4_H_TILE, S4_H_DIR)):
        rs = []
        for gc in (client, host):  # F607: client first; rs stays [host, client]
            r = gc.cmd({"cmd": "battle_teleport_unit", "unit": uid,
                        "x": tile[0], "y": tile[1], "z": tile[2], "dir": d})
            assert r.get("ok"), f"PREMISE: battle_teleport_unit {uid} -> {tile} on {gc.name}: {r}"
            rs.insert(0, (r.get("to"), r.get("dir")))
        assert rs[0] == rs[1] == ({"x": tile[0], "y": tile[1], "z": tile[2]}, d), (
            f"PREMISE: battle_teleport_unit {uid} responses differ: host={rs[0]} client={rs[1]}")
        tele[uid] = rs[0]
    print(f"STAGE: C={C_ID} -> {tele[C_ID]} H={H_ID} -> {tele[H_ID]} (both machines)", flush=True)


def melee_contexts(host, ctx0):
    """W2-P4 S-C (S4 re-point): the host's NEW closedContexts records that are
    C's admitted melee intent ({origin intent, kind melee, actorId C})."""
    seen0 = {c.get("actionId") for c in ctx0}
    return [c for c in (event_state(host).get("closedContexts") or []) if c.get("actionId") not in seen0
            and c.get("origin") == "intent" and c.get("kind") == "melee" and c.get("actorId") == C_ID]


def s4_melee(host, client, ctx):
    equalize_tu(host, client, C_ID)
    rod, _ = give_both(host, client, {"unit": C_ID, "item": "STR_STUN_ROD", "clear_hands": True})
    wait_banner_not(client, TEXT_ITEM_ACTION)
    seen = open_right_hand_menu(client)
    p0h, p0c = probes(host), probes(client)
    ctx0 = event_state(host).get("closedContexts") or []
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    uh0, uc0 = units(host), units(client)
    tu0 = (uh0[C_ID]["tu"], uc0[C_ID]["tu"])
    h0 = (hfields(uh0[H_ID]), hfields(uc0[H_ID]))
    cpos = {n: (u[C_ID]["x"], u[C_ID]["y"], u[C_ID]["z"], u[C_ID]["direction"])
            for n, u in (("host", uh0), ("client", uc0))}
    hpos = {n: (u[H_ID]["x"], u[H_ID]["y"], u[H_ID]["z"], u[H_ID]["direction"])
            for n, u in (("host", uh0), ("client", uc0))}
    press(client, KEY_ACTION_ITEM4)
    watch_top(client, lambda st: st != "ActionMenuState", 5, seen)
    max_pending = 0
    t_end = time.time() + 1.5
    while time.time() < t_end:
        max_pending = max(max_pending, battle_state(client).get("pendingStates") or 0)
        time.sleep(0.05)
    texts = []
    settled = settle_client(client, seen, timeout=30, texts=texts)
    # W2-P4 S-C (C1 PR-Q3 (a)): the melee is an order now - wait (bounded) for
    # the host's intent context to close and the client to apply everything.
    order_note = ""
    try:
        client.wait_for("C's melee intent closed on the host and applied on the client",
                        lambda: (melee_contexts(host, ctx0) and event_state(client).get("inFlight") is None
                                 and event_state(client).get("lastSeqApplied")
                                 == event_state(host).get("lastSeqEmitted")) or None, timeout=15, interval=0.1)
    except Exception as e:
        order_note = f"{type(e).__name__}: {e}"
    mctx = melee_contexts(host, ctx0)
    aid = mctx[0].get("actionId") if len(mctx) == 1 else None
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    chain = [e for e in hev if aid is not None and e["actionId"] == aid]
    cmap = {e["seq"]: e for e in cev}
    mseqs = [e["seq"] for e in chain if e["kind"] == "melee"]
    pl = host_payloads(host, mseqs) if mseqs else {}
    melee_cue = ((pl.get(mseqs[0]) or {}).get("payload") or {}) if mseqs else {}
    ph, pc = probes(host), probes(client)
    uh1, uc1 = units(host), units(client)
    tu1 = (uh1[C_ID]["tu"], uc1[C_ID]["tu"])
    h1 = (hfields(uh1[H_ID]), hfields(uc1[H_ID]))
    st1 = (uh1[H_ID]["stun"], uc1[H_ID]["stun"])
    print(f"EVIDENCE S4: rod={rod} C(x,y,z,dir) {cpos} H(x,y,z,dir) {hpos} client-states={seen} "
          f"infobox-text={texts} settled={settled} client max pendingStates={max_pending}; "
          f"melee contexts={mctx} orderWait={order_note!r} chain={[(e['seq'], e['kind']) for e in chain]} "
          f"client chain={[(s, (cmap.get(s) or {}).get('kind'), (cmap.get(s) or {}).get('actionId')) for s in [e['seq'] for e in chain]]} "
          f"melee cue={melee_cue}; "
          f"H host {h0[0]}->{h1[0]} client {h0[1]}->{h1[1]}; "
          f"C.tu host {tu0[0]}->{tu1[0]} client {tu0[1]}->{tu1[1]}; "
          f"client banner={pc['banner']!r} warning={pc['warning']!r}; "
          f"pushes client {p0c['pushes']}->{pc['pushes']} lastSite={pc['lastSite']!r}", flush=True)
    fails = []
    if len(mctx) != 1:
        fails.append(f"host closedContexts gained {len(mctx)} {{origin intent, kind melee, actorId {C_ID}}} "
                     f"(want exactly 1; wait: {order_note!r})")
    kinds = [e["kind"] for e in chain]
    if aid is not None and (not kinds or kinds[0] != "melee" or kinds[-1] != "bt_action_end"
                            or kinds.count("bt_action_end") != 1):
        fails.append(f"host evs of actionId {aid} = {kinds} (want the `melee` cue first and exactly one "
                     f"bt_action_end, last)")
    bad = [(e["seq"], e["kind"], cmap.get(e["seq"])) for e in chain
           if not cmap.get(e["seq"]) or cmap[e["seq"]]["kind"] != e["kind"] or cmap[e["seq"]]["actionId"] != aid]
    if bad:
        fails.append(f"client event_log does not hold the host's evs of actionId {aid}: (seq, kind, client)={bad}")
    if aid is not None and (melee_cue.get("actor"), melee_cue.get("unit")) != (C_ID, H_ID):
        fails.append(f"`melee` cue payload {melee_cue} (want actor {C_ID}, unit {H_ID})")
    if pc["banner"] == TEXT_ITEM_ACTION:
        fails.append(f"client banner {pc['banner']!r} (the interim host-only refusal: want the press sent as "
                     f"an order)")
    if h1[0] != h1[1] or st1[0] != st1[1]:
        fails.append(f"H host={h1[0]} client={h1[1]} (want status / health / stun equal)")
    if tu1[0] != tu1[1] or tu1[0] >= tu0[0]:
        fails.append(f"C.tu host={tu1[0]} client={tu1[1]} before={tu0} (want spent by the host's melee and "
                     f"equal on both)")
    if not settled:
        fails.append(f"client never settled on BattlescapeState (states {seen})")
    common_tail(host, client, fails, (p0h["pushes"], p0c["pushes"]), what="S4")
    finish(fails)


def s5_reload(host, client, ctx):
    # W2-P4 S-D (C1 PR-Q3 (a), chain rule A.10): the reload is an order the host
    # EXECUTES now, and S3 / S2 before it are executed too (the first green run:
    # C TU 56 -> 28 after S1's prime -> 14 after S3's scanner -> 4 after S2's
    # painkiller; C's max TU varies per boot, F1250), which is below the rifle's
    # 15 TU reload - vanilla's reloadAmmo() would then refuse, and S4's stun rod
    # (last) could not be ordered at all. So S5 gives C its max TU on BOTH
    # machines (client first, F607), C23e's staging, instead of equalize_tu's
    # carry-over.
    tus = []
    for gc in (client, host):  # F607: client first, then host
        r = gc.cmd({"cmd": "battle_set_unit_state", "unit": C_ID, "tu": TU_MAX})
        assert r.get("ok"), f"PREMISE: battle_set_unit_state tu={TU_MAX} unit {C_ID} on {gc.name}: {r}"
        tus.append(r.get("tu"))
    assert tus[0] == tus[1] and tus[0] >= RELOAD_TU, f"PREMISE: C max TU client/host {tus} (want equal, >= {RELOAD_TU})"
    # F1132 (amendment C2, C23e's order): C's own starting loadout carries a
    # rifle clip that vanilla's reloadAmmo() picks before the staged one (the
    # first green run's end delta moved C's own item into the rifle), so C is
    # stripped on BOTH machines first (client first, F607): the staged clip is
    # then the only one.
    sc = client.cmd({"cmd": "battle_strip_unit", "unit": C_ID})
    sh = host.cmd({"cmd": "battle_strip_unit", "unit": C_ID})
    assert sh.get("ok") and sc.get("ok") and set(sh.get("deleted") or []) == set(sc.get("deleted") or []), (
        f"PREMISE: battle_strip_unit {C_ID}: host={sh} client={sc}")
    rifle, _ = give_both(host, client, {"unit": C_ID, "item": "STR_RIFLE", "clear_hands": True})
    clip, _ = give_both(host, client, {"unit": C_ID, "item": "STR_RIFLE_CLIP",
                                       "slot": "STR_BELT", "slotX": 0, "slotY": 0})
    inv = {n: sorted((i, v.get("slot")) for i, v in its.items() if v.get("owner") == C_ID)
           for n, its in (("host", items(host)), ("client", items(client)))}
    assert inv["host"] == inv["client"] == sorted([(rifle, "STR_RIGHT_HAND"), (clip, "STR_BELT")]), (
        f"PREMISE: C's inventory {inv} (want exactly the rifle {rifle} in hand and the clip {clip} on the belt)")
    wait_banner_not(client, TEXT_RELOAD)
    assert tab_select(client, C_ID), (
        f"PREMISE: TAB never selected C ({C_ID}) on the client: "
        f"selectedId={battle_state(client).get('selectedId')}")
    assert top(client) == "BattlescapeState", (
        f"PREMISE: client top is {top(client)!r}, not BattlescapeState, before the reload key")
    p0h, p0c = probes(host), probes(client)
    ctx0 = event_state(host).get("closedContexts") or []
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    tu0 = (units(host)[C_ID]["tu"], units(client)[C_ID]["tu"])
    ih0, ic0 = items(host), items(client)
    seen = ["BattlescapeState"]
    press(client, ctx["reload_key"])
    order_note = wait_intent_done(host, client, ctx0, "reload")
    settled = settle_client(client, seen)
    rctx = intent_contexts(host, ctx0, "reload")
    aid = rctx[0].get("actionId") if len(rctx) == 1 else None
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    chain = [e for e in hev if aid is not None and e["actionId"] == aid]
    cmap = {e["seq"]: e for e in cev}
    ph, pc = probes(host), probes(client)
    tu1 = (units(host)[C_ID]["tu"], units(client)[C_ID]["tu"])
    ih1, ic1 = items(host), items(client)
    print(f"EVIDENCE S5: rifle={rifle} clip={clip} reload_key={ctx['reload_key']} C max TU={tus} "
          f"client-states={seen} settled={settled} reload contexts={rctx} orderWait={order_note!r} "
          f"chain={[(e['seq'], e['kind']) for e in chain]} "
          f"client chain={[(s, (cmap.get(s) or {}).get('kind'), (cmap.get(s) or {}).get('actionId')) for s in [e['seq'] for e in chain]]} "
          f"rifle.ammo host {ih0[rifle]['ammo']}->{ih1[rifle]['ammo']} "
          f"client {ic0[rifle]['ammo']}->{ic1[rifle]['ammo']}; "
          f"clip host owner={ih1[clip]['owner']} slot={ih1[clip]['slot']} "
          f"client owner={ic1[clip]['owner']} slot={ic1[clip]['slot']}; "
          f"C.tu host {tu0[0]}->{tu1[0]} client {tu0[1]}->{tu1[1]}; "
          f"client banner={pc['banner']!r} warning={pc['warning']!r}; "
          f"pushes client {p0c['pushes']}->{pc['pushes']} lastSite={pc['lastSite']!r}", flush=True)
    fails = []
    if len(rctx) != 1:
        fails.append(f"host closedContexts gained {len(rctx)} {{origin intent, kind reload, actorId {C_ID}}} "
                     f"(want exactly 1; wait: {order_note!r})")
    kinds = [e["kind"] for e in chain]
    if aid is not None and kinds != ["bt_action_end"]:
        fails.append(f"host evs of actionId {aid} = {kinds} (want exactly one bt_action_end)")
    bad = [(e["seq"], e["kind"], cmap.get(e["seq"])) for e in chain
           if not cmap.get(e["seq"]) or cmap[e["seq"]]["kind"] != e["kind"] or cmap[e["seq"]]["actionId"] != aid]
    if bad:
        fails.append(f"client event_log does not hold the host's evs of actionId {aid}: (seq, kind, client)={bad}")
    if pc["banner"] == TEXT_RELOAD:
        fails.append(f"client banner {pc['banner']!r} (the interim host-only refusal: want the key sent as an "
                     f"order)")
    lh, lc = loaded_ammo(ih1[rifle], rifle), loaded_ammo(ic1[rifle], rifle)
    if lh != [clip] or lc != [clip]:
        fails.append(f"rifle {rifle} loaded ammo host={lh} client={lc} (want [{clip}] on both: the host's reload)")
    if tu1 != (tu0[0] - RELOAD_TU, tu0[0] - RELOAD_TU):
        fails.append(f"C.tu host {tu0[0]}->{tu1[0]} client {tu0[1]}->{tu1[1]} (want before - {RELOAD_TU} on both)")
    if not settled:
        fails.append(f"client never settled on BattlescapeState (states {seen})")
    common_tail(host, client, fails, (p0h["pushes"], p0c["pushes"]), what="S5")
    finish(fails)


def s7_tripwire(host, client, ctx):
    equalize_tu(host, client, C2_ID)
    rifle, clip = give_both(host, client, {"unit": C2_ID, "item": "STR_RIFLE",
                                           "ammo": "STR_RIFLE_CLIP", "clear_hands": True})
    p0h, p0c = probes(host), probes(client)
    uh0, uc0 = units(host), units(client)
    tu0 = (uh0[C2_ID]["tu"], uc0[C2_ID]["tu"])
    q0 = (items(host)[clip]["qty"], items(client)[clip]["qty"])
    r = client.cmd({"cmd": "battle_fire", "unit": C2_ID, "mode": "snap",
                    "x": S7_TARGET[0], "y": S7_TARGET[1], "z": S7_TARGET[2]})
    seen = []
    settled = settle_client(client, seen, timeout=30)
    ph, pc = probes(host), probes(client)
    uh1, uc1 = units(host), units(client)
    tu1 = (uh1[C2_ID]["tu"], uc1[C2_ID]["tu"])
    ih1, ic1 = items(host), items(client)
    q1 = (uv(ih1.get(clip), "qty"), uv(ic1.get(clip), "qty"))
    c2p = {n: (u[C2_ID]["x"], u[C2_ID]["y"], u[C2_ID]["z"]) for n, u in (("host", uh0), ("client", uc0))}
    print(f"EVIDENCE S7: C2={C2_ID} at {c2p} rifle={rifle} clip={clip} target={S7_TARGET} "
          f"battle_fire(client)={r} client-states={seen} settled={settled} "
          f"clip.qty host {q0[0]}->{q1[0]} client {q0[1]}->{q1[1]}; "
          f"C2.tu host {tu0[0]}->{tu1[0]} client {tu0[1]}->{tu1[1]}; "
          f"C2.dir host {uh0[C2_ID]['direction']}->{uh1[C2_ID]['direction']} "
          f"client {uc0[C2_ID]['direction']}->{uc1[C2_ID]['direction']}; "
          f"C.dir host {uh1[C_ID]['direction']} client {uc1[C_ID]['direction']}; "
          f"pushes client {p0c['pushes']}->{pc['pushes']} host {p0h['pushes']}->{ph['pushes']} "
          f"lastSite client={pc['lastSite']!r}", flush=True)
    fails = []
    if not r.get("ok"):
        fails.append(f"battle_fire on the client did not answer ok: {r}")
    last = pc["lastSite"] or ""
    if "statePushBack:" not in last or "ProjectileFlyBState" not in last:
        fails.append(f"coopClientBStateLastSite {last!r} (want statePushBack:<ProjectileFlyBState>)")
    if q1[0] != q1[1]:
        fails.append(f"clip.qty host={q1[0]} client={q1[1]} (want equal)")
    if tu1[0] != tu1[1]:
        fails.append(f"C2.tu host={tu1[0]} client={tu1[1]} (want equal)")
    if not settled:
        fails.append(f"client never settled on BattlescapeState (states {seen})")
    common_tail(host, client, fails, (p0h["pushes"], p0c["pushes"]), push_delta=2, what="S7")
    finish(fails)


# A2.2 order. STAGE is a fixture step: it prints PASS/FAIL like a scenario and
# a failed STAGE also fails the run, but it is not one of the seven.
STEPS = (("S6", s6_panic), ("S1", s1_prime), ("S3", s3_scanner), ("STAGE", stage),
         ("S2", s2_medikit), ("S5", s5_reload), ("S7", s7_tripwire), ("S4", s4_melee))
SCENARIOS = tuple(s for s in STEPS if s[0] != "STAGE")


# ===================== bring-up =====================


def read_reload_key(user_dir):
    """Options::keyBattleReload as the client process wrote it back to its own
    options.cfg at startup (every option key is saved there on boot)."""
    with open(os.path.join(user_dir, "options.cfg"), "r", encoding="utf-8") as f:
        m = re.search(r"^\s*keyBattleReload:\s*(-?\d+)\s*$", f.read(), re.M)
    assert m, f"PREMISE: no keyBattleReload in {user_dir}/options.cfg"
    return int(m.group(1))


def settle_on_battlescape(gc, timeout=20):
    """Clear any NextTurnState left over from the cycle (the real close()
    path) and wait until BattlescapeState is on top with the panic check done."""
    def ready():
        dismiss_next_turn_if_present(gc)
        bs = battle_state(gc)
        return (top(gc) == "BattlescapeState" and bs.get("panicHandled")
                and bs.get("pendingStates") == 0) or None
    gc.wait_for(f"{gc.name} on BattlescapeState at player turn 2", ready, timeout=timeout)


def boot(host, client):
    raw.bring_up_lobby(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"PREMISE: mapFingerprint host={hs.get('mapFingerprint')!r} "
        f"client={cs.get('mapFingerprint')!r}, baked MAP_FP={MAP_FP!r} (SEED {SEED})")
    pinned = pin_ai_neutral(host, client, tag="w2p1")
    assert pinned, "PREMISE: pin_ai_neutral pinned no NONE-seat non-player unit"
    by_sid = {u["soldierId"]: u["id"] for u in hs["units"] if u.get("soldierId", -1) >= 0}
    c_ids = [by_sid.get(s) for s in seated["soldierIds"]]
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert c_ids[:2] == [C_ID, C2_ID] and h_ids and h_ids[0] == H_ID, (
        f"PREMISE: actors differ from the baked ids: client-seated={c_ids} "
        f"host-seat={h_ids}, baked C={C_ID} C2={C2_ID} H={H_ID}")

    # A1.2 (i): reach player turn 2 (test_rw_seat_pacing Boot B shape).
    turn0 = hs["turn"]
    client.ok({"cmd": "battle_action", "action": "end_turn_button"})
    host.wait_for("host paints END TURN 1/2 after the client's arm",
                  lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2" or None,
                  timeout=20)
    host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    drive_full_cycle(host, client, turn0, timeout=60)
    settle_on_battlescape(host)
    settle_on_battlescape(client)
    session.wait_host_idle(host, client, timeout=30)
    hs, cs = battle_state(host), battle_state(client)
    assert (hs["turn"], hs["side"], cs["turn"], cs["side"]) == (turn0 + 1, FACTION_PLAYER,
                                                                 turn0 + 1, FACTION_PLAYER), (
        f"PREMISE: not on player turn {turn0 + 1} on both: host=({hs['turn']},{hs['side']}) "
        f"client=({cs['turn']},{cs['side']})")
    assert_hash_clean(host, client, full=True, what="player turn 2 entry")
    ctx = {"reload_key": read_reload_key(client.user_dir)}
    print(f"[w2p1] boot ok: MAP_FP={MAP_FP!r} turn={hs['turn']} C={C_ID} C2={C2_ID} H={H_ID} "
          f"pinned={pinned} reload_key={ctx['reload_key']}", flush=True)
    return ctx


def main():
    t0 = time.time()
    host = GameClient("host", 49830, make_user_dir("w2p1_tripwire_host"))
    client = GameClient("client", 49831, make_user_dir("w2p1_tripwire_client"))
    results = {}
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:  # a bring-up failure fails the whole run
            print(f"FAIL boot: {type(e).__name__}: {e}", flush=True)
            return 2
        for name, fn in STEPS:
            try:
                fn(host, client, ctx)
                results[name] = True
                print(f"PASS {name}", flush=True)
            except Exception as e:
                results[name] = False
                kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
                print(f"FAIL {name}: {kind}{e}", flush=True)
    finally:
        host.shutdown()
        client.shutdown()
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_thin_client_tripwire: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}; STAGE {'ok' if results.get('STAGE') else 'FAILED'}) "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed and results.get("STAGE") else 2


if __name__ == "__main__":
    sys.exit(main())
