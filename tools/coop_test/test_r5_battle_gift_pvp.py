"""R5-U5 S-A row P1 (boot P; owner D235 (a); D235-VL1 / R5-V2: PvP has no gift): in a PvP battle (gm2) neither the
give-unit key nor the gift order gives a unit. Boot P: gm2, lobby key 48618, dirs r5u5_p_host / r5u5_p_client.

Spec: docs repo rewrite/prompts/r5u5_battle_gift_order.md section (f) test_r5_battle_gift_pvp.py, as amended by AMENDMENT
R5U5-A1 A1-3 (P1-key: the host's key with its own unit selected, then the spectator client's key; QU5-A1-3 (a)).
Constants: rewrite/r5u5-task0/sa/CONSTANTS.md (boots Pa, Pb; re-dispatch Pa2, Pb2).

Boot P = test_w2_battle_end_rules.boot_e6 (roster / map seed 1, the client on the Alien team, STR_SMALL_SCOUT); every live
unit's reactions 0. Side 0 (the host's X-COM) is active; the client is a spectator.
  P1  P1-key (a guard row on both builds: the host's own unit, refused only by the gm 2 / 3 term) - the host's
      giftSelectedId -1; tab_select(host, P_X) (P_X = the lowest X-COM unit id other than the host's bring-up selection
      P_SEL0); giftSelectedId -1; the host's key 258: after 1 s its top is BattlescapeState, giftSelectedId -1; then the
      client's key: after 1 s its top is BattlescapeState. P1-lever - the client's lever gift {A, target 0}: a refusal
      (EVIDENCE reason pvp). P1-common.
Red at A1 (the unchanged build + T1-T5): P1-lever ("not sent"); P1-key and P1-common pass.

"A refusal" = the client's coopIntentsSent.gift +1, the host's intentsReceived.gift.denied +1 within STEP_S, the unit's
coop unchanged on both after wait_host_idle; the host's refusal line and its reason are EVIDENCE.
One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. A boot step past its bound prints ONE
CAPTURE line and fails the row "boot". Common cell: every hash bucket EQUAL, desyncSeen false on both, no new crash file.
Ids come from probes (S25). WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip
path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_r5_battle_gift_pvp.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_r5_pvp_gm3 as G3F  # noqa: E402
import test_w2_battle_end_rules as BER  # noqa: E402
import test_r5_battle_gift as GIFT  # noqa: E402
from test_rw_seat_pacing import tab_select  # noqa: E402

KEY = "48618"
GIVE_KEY = GIFT.GIVE_KEY                  # 258, Options::giveUnit (SDLK_KP2)
A = BER.A_ID                              # 1000000: the alien, FACTION_HOSTILE, seat 1, (27,12,0)
P_SEL0, P_X = 8, 9                        # TASK 0 (Pa, Pb, Pa2, Pb2): the host's bring-up selection and its TAB target
ROWS = (("P1", ("P1-key", "P1-lever", "P1-common")),)

units, top = G3F.units, G3F.top


def bring_up(host, client):
    m = (host, client)
    boot = GIFT.guarded("P", lambda: BER.boot_e6(host, client, KEY), m)
    crash0 = session._crash_log_snapshot()
    GIFT.guarded("P", lambda: G3F.reactions_zero(host, client), m)
    return boot, crash0


def key_top(gc, ev, tag):
    gc.ok({"cmd": "inject_input", "kind": "key", "key": GIVE_KEY})
    time.sleep(1.0)
    ev[tag] = {"stack": session.states_stripped(gc), "sel": GIFT.gsel(gc)}
    return ev[tag]["stack"][-1:] == ["BattlescapeState"]


def row_p1(host, client, crash0):
    cells, ev = {}, {}
    k = ev.setdefault("key", {"sides": [(battle_state(gc).get("side"), battle_state(gc).get("turn"))
                                        for gc in (host, client)]})
    k["sel0"] = GIFT.gsel(host)
    p_sel0 = k["sel0"][0]
    xcom = sorted(i for i, u in units(host).items() if u.get("faction") == 0 and u.get("coop") == 0
                  and not u.get("isOut"))
    p_x = min((i for i in xcom if i != p_sel0), default=None)
    k.update(P_SEL0=[p_sel0, P_SEL0], P_X=[p_x, P_X], xcom=xcom)
    k["tab"] = tab_select(host, p_x)
    k["afterTab"] = GIFT.gsel(host)
    h_ok = key_top(host, k, "hostKey")
    c_ok = key_top(client, k, "clientKey")
    gifts = [k["sel0"][1], k["afterTab"][1], k["hostKey"]["sel"][1]]
    cells["P1-key"] = (gifts == [-1, -1, -1] and k["tab"] and k["afterTab"][0] == p_x and h_ok and c_ok,
                       f"host giftSelectedId before / after tab_select(host, {p_x}) / after its key {gifts} (want -1 "
                       f"each); tab {k['tab']} (selectedId {k['afterTab'][0]}); host stack after the key "
                       f"{k['hostKey']['stack']}, client stack after its key {k['clientKey']['stack']} (want "
                       f"BattlescapeState on top, no menu)")
    cells["P1-lever"] = GIFT.refusal(host, client, A, 0, ev.setdefault("lever", {}))
    cells["P1-common"] = G3F.common(host, client, crash0)
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("r5u5_p_host"))
    client = GameClient("client", None, make_user_dir("r5u5_p_client"))
    fails = 0
    try:
        try:
            boot, crash0 = bring_up(host, client)
            print(f"[r5u5] boot P: {json.dumps(boot, default=str)}", flush=True)
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE P line)")
        else:
            fails += G3F.run_row("P1", ROWS[0][1], lambda: row_p1(host, client, crash0))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_r5_battle_gift_pvp: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
