"""PvP notices in gm2 (the client plays the aliens, seat 1; the host the seven X-COM soldiers, seat 0): the alien
player's new-contact count counts the X-COM soldiers its side sees, and while the alien player moves a mind-controlled
X-COM soldier the host's "please wait" banner names the alien player.

Boot (key 48883, dirs pvp_notices_host / _client): BER.boot_pvp (STR_SMALL_SCOUT, map seed 1, gamemode 2), every live
unit's reactions 0, RM.stage_tiles(RM.TILES) with MC_WALK_PATH / MC_WALK_DEST checked open ground, the host's END TURN
-> side 1 turn 1 (the alien seat's own turn). The values below were measured equal on two boots without the fix.
  new_contacts  the alien player's new-contact count is the X-COM soldiers its side sees: the client turns A to its own
      facing (RM.turn_order, a test command; one action envelope after the side change, because the client's `seen`
      list lags by one).
      new_contacts-pre     one new host context {intent, turn, A}; at least one X-COM id with VH(client, id) true
                           (precondition)
      new_contacts-count   the client's event_state.visibleHostileCount == the number of X-COM ids with VH(client, id)
                           true
  mc_walk_banner  the host's banner names the alien player while its mind-controlled soldier moves (last row: S2 stays
      controlled): test_pvp_react_mc's mind-control staging (the amp on A, A psiSkill 100, S2 psiStrength 0, A TU), the
      client's real-UI MIND CONTROL on S2 (TAB, the right-hand box, key 51, HOME, host set_seed MC_SEED, one click);
      S2's TU cap refilled; the client's send_walk(S2, MC_WALK_DEST); the host sampled every SAMPLE_S until the walk's
      context closes.
      mc_walk_banner-mc     S2 faction 1, mindControllerId A on both (precondition)
      mc_walk_banner-walk   one new host context {intent, walk, S2}
      mc_walk_banner-seat   at least one host sample with event_state.busyOwnerSeat == 1 (the alien player's seat)
      mc_walk_banner-text   at least one host sample with coopWaitText == TEXT_WAIT
VH(gc, id) = battle_state(gc).units[id].visibleHere. event_state.visibleHostileCount is a test-only read of the
client's new-contact count. Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on
both, no new file in this harness slot's crash folder.

Without the fix, new_contacts-count, mc_walk_banner-seat and mc_walk_banner-text FAIL; every other cell passes. One
EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step
past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails the rows that
need it "staging". ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_notices.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
from test_client_shoot import new_contexts, set_tu_both  # noqa: E402
from test_seat_pacing import tab_select  # noqa: E402
from test_turn_baton import RHAND_NTH, click_nth  # noqa: E402

KEY = "48883"
A_ID, S2_ID = RM.A_ID, RM.S2_ID   # the alien (the client's, seat 1); the X-COM soldier A mind-controls (10)
XCOM_IDS = [8, 9, 10, 11, 12, 13, 14]
A_DIR = RM.TILES[A_ID][1]         # 4: A's own facing at (15,2,0) (new_contacts' turn; measured: admitted, one envelope)
MC_WALK_PATH, MC_WALK_DEST = (12, 6, 0), (12, 5, 0)   # two tiles north of S2's (12,7,0), open ground, no turn
MC_SEED = 1                       # the lowest seed whose MIND CONTROL succeeds (measured on three boots)
A_TU, S2_TU = RM.A_TU, RM.S2_TU   # 54, 58
CLIENT_SEAT = 1
TEXT_WAIT = "Please wait for ClientPlayer's action to finish"   # the host's banner for seat 1
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
SAMPLE_S, WALK_S = 0.1, 30        # the host's sample cadence; the bound on the walk's context
ROWS = (("new_contacts", ("new_contacts-pre", "new_contacts-count", "new_contacts-common")),
        ("mc_walk_banner", ("mc_walk_banner-mc", "mc_walk_banner-walk", "mc_walk_banner-seat", "mc_walk_banner-text",
                            "mc_walk_banner-common")))


def vhc(gc):
    return event_state(gc).get("visibleHostileCount")


def vh_ids(gc):
    us = G3F.units(gc)
    return [i for i in XCOM_IDS if (us.get(i) or {}).get("visibleHere") is True]


def bsv(gc):
    b = battle_state(gc)
    return {k: b.get(k) for k in ("side", "turn", "selectedId", "coopWaitText", "hiddenMovementShown")}


def sample_until_closed(host, ctx0, kind, timeout):
    """The host's (secs, busyOwnerSeat, coopWaitText) every SAMPLE_S until a new closed context of `kind` appears
    (bounded). Returns (samples, the new closed contexts of that kind or None)."""
    samples, t0 = [], time.time()
    while time.time() - t0 < timeout:
        e = event_state(host)
        samples.append((round(time.time() - t0, 2), e.get("busyOwnerSeat"), battle_state(host).get("coopWaitText")))
        new = [c for c in new_contexts(ctx0, e.get("closedContexts") or []) if c.get("kind") == kind]
        if new:
            return samples, new
        time.sleep(max(0.0, SAMPLE_S * len(samples) - (time.time() - t0)))
    return samples, None


# ===================== rows =====================


def row_new_contacts(host, client, crash0):
    ev = {"before": {"vhc": vhc(client), "vh": vh_ids(client)}}
    new, deny = RM.turn_order(host, client, A_ID, A_DIR, ev)
    vh, count = vh_ids(client), vhc(client)
    a = G3F.units(client).get(A_ID) or {}
    ev.update(newCtx=[RM.cv(c) for c in new], deny=deny, vh=vh, count=count, hostCount=vhc(host),
              clientA={k: a.get(k) for k in ("direction", "visibleUnits", "visibleHere")},
              hostSpotted=(G3F.units(host).get(A_ID) or {}).get("spottedThisTurn"), client=bsv(client))
    return {"new_contacts-pre": (RM.ctx_ok(new, "intent", "turn", A_ID) and deny is None and len(vh) >= 1,
                                 f"turn contexts {ev['newCtx']} (want one {{intent, turn, {A_ID}}}), deny {deny} (want "
                                 f"none); X-COM ids with VH(client) true {vh} (want at least one)"),
            "new_contacts-count": (count == len(vh), f"the client's visibleHostileCount {count} (want {len(vh)}: the "
                                                     f"X-COM ids its side sees, {vh})"),
            "new_contacts-common": G3F.common(host, client, crash0)}, ev


def mind_control(host, client, ev):
    """test_pvp_react_mc's mind-control staging and the client's real-UI MIND CONTROL on S2 (MC_SEED); the leftover
    targeting cancelled."""
    ev["amp"] = RM.give_both(host, client, A_ID, RM.PSI_AMP)["weaponId"]
    RM.stat_both(host, client, A_ID, "psiSkill", 100)
    RM.stat_both(host, client, S2_ID, "psiStrength", 0)
    ev["aTu"] = set_tu_both(host, client, A_ID, A_TU)
    ui = ev["ui"] = {}
    ctx0, sent0 = RM.ctxs(host), dict(event_state(client).get("coopIntentsSent") or {})
    try:
        ui["tab"] = tab_select(client, A_ID)
        RM.psi_press(client, host, RM.TILES[S2_ID][0], MC_SEED, ui)
    except Exception as e:
        ui["pressError"] = f"{type(e).__name__}: {str(e)[:300]}"
    new = RM.mc_order(host, client, ctx0, S2_ID, ui)
    c1 = battle_state(client).get("cursorType")
    if c1 in RM.CURSOR_TARGETING and ui["clientMap"][0]:
        click_nth(client, RHAND_NTH)   # cancel the client's leftover targeting (measured: cursorType 3 -> 1)
    ui.update(cancel=[c1, battle_state(client).get("cursorType")], psiCtx=[RM.cv(c) for c in new],
              psiSent=(event_state(client).get("coopIntentsSent") or {}).get("psi", 0) - sent0.get("psi", 0))
    return [(RM.uv(gc, S2_ID)["faction"], RM.uv(gc, S2_ID)["mindControllerId"]) for gc in (host, client)]


def row_mc_walk_banner(host, client, crash0):
    ev, cells = {}, {}
    s2 = ev["s2Mc"] = mind_control(host, client, ev)
    mc = s2 == [(FACTION_HOSTILE, A_ID)] * 2
    cells["mc_walk_banner-mc"] = (mc, f"S2 (faction, mindControllerId) host/client {s2} (want ({FACTION_HOSTILE}, "
                                      f"{A_ID}) on both)")
    if not mc:
        why = "staging (S2 not mind-controlled by A, see mc_walk_banner-mc)"
        cells.update({"mc_walk_banner-walk": (False, why), "mc_walk_banner-seat": (False, why),
                      "mc_walk_banner-text": (False, why)})
    else:
        ev["s2Tu"] = RM.stat_both(host, client, S2_ID, "tu", S2_TU, refill=True)["tu"]
        ctx0, prev = RM.ctxs(host), session.walk_action_id(host)
        ev["walk"] = session.send_walk(client, S2_ID, MC_WALK_DEST)
        samples, closed = sample_until_closed(host, ctx0, "walk", WALK_S)
        try:
            session.wait_walk_settled(host, client, prev, timeout=WALK_S)
        except Exception as e:
            ev["walkError"] = str(e)[:200]
        RM.settle(host, client, ev)
        new = new_contexts(ctx0, RM.ctxs(host))
        seats = sorted({s[1] for s in samples}, key=str)
        texts = sorted({s[2] for s in samples}, key=str)
        ev.update(samples=samples, closed=[RM.cv(c) for c in closed or []], newCtx=[RM.cv(c) for c in new],
                  s2Pos=[G3F.pos(gc, S2_ID) for gc in (host, client)], host=bsv(host))
        cells["mc_walk_banner-walk"] = (RM.ctx_ok(new, "intent", "walk", S2_ID),
                                        f"new host contexts {ev['newCtx']} (want exactly one {{intent, walk, "
                                        f"{S2_ID}}}); S2 host/client {ev['s2Pos']} (EVIDENCE, MC_WALK_DEST "
                                        f"{MC_WALK_DEST})")
        cells["mc_walk_banner-seat"] = (CLIENT_SEAT in seats, f"the host's busyOwnerSeat over {len(samples)} samples "
                                                              f"{seats} (want at least one {CLIENT_SEAT}, the alien "
                                                              f"player's seat)")
        cells["mc_walk_banner-text"] = (TEXT_WAIT in texts, f"the host's coopWaitText over {len(samples)} samples "
                                                            f"{texts} (want at least one {TEXT_WAIT!r})")
    cells["mc_walk_banner-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot =====================


def stage(host, client):
    """RM.TILES on both (MC_WALK_PATH / MC_WALK_DEST checked open ground), the host's END TURN -> side 1 turn 1."""
    ev = {"entry": {"host": bsv(host), "client": bsv(client)}}
    ev["placed"] = RM.stage_tiles(host, client, RM.TILES, (MC_WALK_PATH, MC_WALK_DEST))
    side = {}
    G3F.guarded("staging", lambda: RM.side_change(host, client, host, FACTION_HOSTILE, 1, side), (host, client))
    ev.update(side=side, hash=G3F.hash_now(host, client))
    return ev


def run_boot():
    host = GameClient("host", None, make_user_dir("pvp_notices_host"))
    client = GameClient("client", None, make_user_dir("pvp_notices_client"))
    m = (host, client)
    try:
        try:
            G3F.guarded("boot", lambda: BER.boot_pvp(host, client, KEY), m)
            G3F.guarded("boot", lambda: G3F.reactions_zero(host, client), m)
            crash0 = session._crash_log_snapshot()
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        try:
            st = stage(host, client)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        print(f"EVIDENCE staging: {st}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("new_contacts", rows["new_contacts"], lambda: row_new_contacts(host, client, crash0))
        fails += G3F.run_row("mc_walk_banner", rows["mc_walk_banner"], lambda: row_mc_walk_banner(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_notices: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
