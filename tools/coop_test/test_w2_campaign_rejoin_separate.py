"""R4-L2 stage S-A (spec rewrite/prompts/r4l2_campaign_rejoin.md (f) row CR2, QL2-1 a, QL2-4 a, QL2-5 a; TASK 0
rewrite/r4l2-task0/sa/CONSTANTS.md T0-2): a SEPARATE co-op campaign player whose game is killed during a battle restarts, rejoins and
is never offered the battle. The host's resume_ack battle branch hands the rejoin to offerResumedBattle(), which refuses the live
pause (F4812, F10801): REFUSED +1, resumeAck never true, the host waits on dialog 62 and the rejoiner on 68 for good.
  Boot S (key "48599", w2r4l2_s_host / _client / _client2): bring_up_separate_guest_battle(pre_mission_start=f) (SPEC 19 S1: 3 host
  soldiers + the client's "Guest Zzz" seated on the host's craft; f records OWN_BEFORE = the client's own "Guest Zzz" record and F0 =
  the client's funds, for S-D's CR4); GID = the host battle unit named "Guest" (coop 1); B0, SPLIT0, T0, HASH; ICON0 (the host's
  partner-base icons) and H0 (the host's copy of the client world, coop_file_info); client.kill() (the loss path in EVIDENCE: TASK 0
  measured -2, peerAbsent true at the first poll); PAUSE; ICON1; REJOIN(client2, "48599", campaign); pick_and_walk(host, client2, GID).
  Cells: CR2-1 GUARD PAUSE; CR2-2 GUARD phase 1 served (a client2 poll on 68; EVIDENCE only, never asserted, QL2-4: RESTASH, ICON0 /
  ICON1, H0 == the host copy's fnv at the pause); CR2-3 RED the live offer (OFFER +1 reading battleId=B0, REFUSED +0); CR2-4 RED
  RESUME offered within W_ACK and pressed; CR2-5 RED the same battle on both; CR2-6 RED SPLIT (client2's holds GID on seat 1);
  CR2-7 RED HASH; CR2-8 RED one client2 walk of GID applied, HASH again; CR2-9 GUARD CRASH 0 and client2 zero-disk.
Definitions, REJOIN, needles, the flow rule and the safe battle_state probe (F10980): test_w2_campaign_rejoin.py (imported, import
only). EVIDENCE before each verdict; a failed row prints ONE CAPTURE line; ONE run (WV-D95); exit 0 iff every cell passes, else 2.
Red (S-A commit 1): CR2 FAIL on CR2-3, CR2-4 and CR2-5..CR2-8 "not reached" (CR2-1, CR2-2, CR2-9 PASS).
"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_w2_battle_end_separate as BES  # noqa: E402  (main-guarded: soldier_rec)
import test_w2_campaign_rejoin as CR  # noqa: E402  (main-guarded: the S-A helpers)

KEY_S = "48599"
FREEZE, DROP = "[coop-session] freeze (lobbyMode=", "[coop-session] onClientDrop"
OWN = {}


def fx(host, client):
    """pre_mission_start f: OWN_BEFORE (the client's own "Guest Zzz" record) and F0 (the client's funds) before the battle"""
    OWN["OWN_BEFORE"] = BES.soldier_rec(client, name="Guest Zzz")
    OWN["F0"] = CR.q(client, {"cmd": "geo_state"}).get("funds")


def icons(host):
    """ICON: the host's geo_state bases with coopIcon (the partner's base icons)"""
    return [b.get("name") for b in CR.q(host, {"cmd": "geo_state"}).get("bases") or [] if b.get("coopIcon")]


def copy_info(host, key=None):
    """the host's copy of the client world: coop_file_info by role (host_copy_of_client) or by key"""
    return CR.pick(CR.q(host, {"cmd": "coop_file_info", "key": key} if key else {"cmd": "coop_file_info", "role": "host_copy_of_client"}),
                   ("key", "present", "bytes", "fnv1a64", "error"))


def row_cr2(x, results, walls):
    r = CR.Row("CR2", ["CR2-%d" % i for i in range(1, 9)], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        gids = [CR.pick(u, ("id", "coop", "name")) for u in CR.bs_raw(h).get("units") or []
                if u.get("faction") == 0 and "Guest" in str(u.get("name"))]
        print("EVIDENCE CR2 fixture: %s" % json.dumps({"GID units": gids, "OWN_BEFORE": OWN.get("OWN_BEFORE"), "F0": OWN.get("F0")},
                                                     sort_keys=True, default=str), flush=True)
        if len(gids) != 1 or gids[0]["coop"] != 1:
            raise CR.Stop("FIXTURE-STOP: GID = exactly one host battle unit named \"Guest\" on coop 1: %s" % gids)
        gid = gids[0]["id"]
        CR.baseline(r, x, c)
        icon0, h0 = icons(h), copy_info(h)
        r.n_h = n_h = len(CR.log(h))
        c.kill()
        first = CR.auth(h)
        ok, pv = CR.pause(x)
        drop, freeze = CR.since(h, n_h, DROP), CR.since(h, n_h, FREEZE)
        pv["loss path"] = {"first poll after the kill": first, "FREEZE": freeze, "DROP": drop, "kill rc": c.proc.returncode,
                           "path": "-2 (receive)" if drop else ("-3 (send)" if freeze else "?")}
        r.cell("CR2-1", "GUARD", "PAUSE(host) (phase Active, peerAbsent true, battleId B0, inBattle true, dialog 62 backVisible false, "
               "[..., BattlescapeState, CoopState] within %.0f s of the kill)" % CR.W_PAUSE, ok, pv)
        if not ok:
            raise CR.Stop("PAUSE(host) not reached within %.0f s" % CR.W_PAUSE)
        icon1, hp = icons(h), copy_info(h, h0.get("key"))

        def cell2(ev, n):
            r.cell("CR2-2", "GUARD", "phase 1 served: a client2 poll on dialog 68 (EVIDENCE only, never asserted: RESTASH, ICON0 / ICON1, "
                   "H0 == the host copy's fnv at the pause)", ev.get("c2 on 68 s") is not None,
                   {"c2 on 68 s": ev.get("c2 on 68 s"), "join_tcp": ev.get("join_tcp"), "RESTASH": CR.since(h, n_h, CR.RESTASH),
                    "ICON0": icon0, "ICON1": icon1, "H0": h0, "at the pause": hp, "H0 == at the pause": h0.get("fnv1a64") == hp.get("fnv1a64")})
        CR.rejoin_tail(r, x, "CR2", KEY_S, gid, cell2)
    except Exception as e:  # Stop, or a probe / kill() / spawn that raised: the row ends here
        r.stop(e)
    r.end("CR2-9", x.client2.user_dir if x.client2 is not None else None, results, walls)


def main():
    return CR.run((("w2r4l2_s", lambda tag: CR.boot_separate(tag, KEY_S, pre=fx), (("CR2", row_cr2),)),),
                  "test_w2_campaign_rejoin_separate")


if __name__ == "__main__":
    sys.exit(main())
