"""test_battle_gift_pvp.py: a PvP battle (gm2) has no gifts: neither the give-unit key nor the gift order gives a
unit. One boot: gm2, lobby key 48618, dirs battle_gift_pvp_host / battle_gift_pvp_client.

The boot is test_battle_end_rules.boot_pvp (roster / map seed 1, the client on the Alien team, STR_SMALL_SCOUT); every
live unit's reactions 0. Side 0 (the host's X-COM) is active; the client is a spectator. One row:
  pvp_no_gift  give_key_ignored - the host's key with its own unit selected (only the PvP game mode check, gm 2 / 3,
      refuses that unit), then the spectator client's key: the host's giftSelectedId -1; tab_select(host, TAB_TARGET)
      (TAB_TARGET = the lowest X-COM unit id other than the host's bring-up selection BRINGUP_SEL); giftSelectedId -1;
      the host's key 258: after 1 s its top is BattlescapeState, giftSelectedId -1; then the client's key: after 1 s
      its top is BattlescapeState. gift_order_refused - the client's battle_intent gift {A, target 0} (the test
      command): a refusal (EVIDENCE reason pvp). no_gift_common.

"A refusal" = the client's coopIntentsSent.gift +1, the host's intentsReceived.gift.denied +1 within
test_battle_gift.STEP_S, the unit's coop unchanged on both after wait_host_idle; the host's refusal line and its reason
are EVIDENCE.
One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. A boot step past its bound prints ONE
CAPTURE line and fails the row "boot". Common cell: every hash bucket EQUAL, desyncSeen false on both, no new crash
file. Ids come from probes. No skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_battle_gift_pvp.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_battle_gift as GIFT  # noqa: E402
from test_seat_pacing import tab_select  # noqa: E402

KEY = "48618"
GIVE_KEY = GIFT.GIVE_KEY                  # 258, Options::giveUnit (SDLK_KP2)
A = BER.A_ID                              # 1000000: the alien, FACTION_HOSTILE, seat 1, (27,12,0)
BRINGUP_SEL, TAB_TARGET = 8, 9            # measured (four boots): the host's bring-up selection, its TAB target
ROWS = (("pvp_no_gift", ("give_key_ignored", "gift_order_refused", "no_gift_common")),)

units, top = G3F.units, G3F.top


def bring_up(host, client):
    m = (host, client)
    boot = GIFT.guarded("boot", lambda: BER.boot_pvp(host, client, KEY), m)
    crash0 = session._crash_log_snapshot()
    GIFT.guarded("boot", lambda: G3F.reactions_zero(host, client), m)
    return boot, crash0


def key_top(gc, ev, tag):
    gc.ok({"cmd": "inject_input", "kind": "key", "key": GIVE_KEY})
    time.sleep(1.0)
    ev[tag] = {"stack": session.states_stripped(gc), "sel": GIFT.gsel(gc)}
    return ev[tag]["stack"][-1:] == ["BattlescapeState"]


def row_pvp_no_gift(host, client, crash0):
    cells, ev = {}, {}
    k = ev.setdefault("key", {"sides": [(battle_state(gc).get("side"), battle_state(gc).get("turn"))
                                        for gc in (host, client)]})
    k["sel0"] = GIFT.gsel(host)
    bringup_sel = k["sel0"][0]
    xcom = sorted(i for i, u in units(host).items() if u.get("faction") == 0 and u.get("coop") == 0
                  and not u.get("isOut"))
    tab_target = min((i for i in xcom if i != bringup_sel), default=None)
    k.update(BRINGUP_SEL=[bringup_sel, BRINGUP_SEL], TAB_TARGET=[tab_target, TAB_TARGET], xcom=xcom)
    k["tab"] = tab_select(host, tab_target)
    k["afterTab"] = GIFT.gsel(host)
    h_ok = key_top(host, k, "hostKey")
    c_ok = key_top(client, k, "clientKey")
    gifts = [k["sel0"][1], k["afterTab"][1], k["hostKey"]["sel"][1]]
    cells["give_key_ignored"] = (gifts == [-1, -1, -1] and k["tab"] and k["afterTab"][0] == tab_target
                                 and h_ok and c_ok,
                                 f"host giftSelectedId before / after tab_select(host, {tab_target}) / after its key "
                                 f"{gifts} (want -1 each); tab {k['tab']} (selectedId {k['afterTab'][0]}); host stack "
                                 f"after the key {k['hostKey']['stack']}, client stack after its key "
                                 f"{k['clientKey']['stack']} (want BattlescapeState on top, no menu)")
    cells["gift_order_refused"] = GIFT.refusal(host, client, A, 0, ev.setdefault("giftOrder", {}))
    cells["no_gift_common"] = G3F.common(host, client, crash0)
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("battle_gift_pvp_host"))
    client = GameClient("client", None, make_user_dir("battle_gift_pvp_client"))
    fails = 0
    try:
        try:
            boot, crash0 = bring_up(host, client)
            print(f"[test_battle_gift_pvp] boot: {json.dumps(boot, default=str)}", flush=True)
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        else:
            fails += G3F.run_row("pvp_no_gift", ROWS[0][1], lambda: row_pvp_no_gift(host, client, crash0))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_battle_gift_pvp: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
