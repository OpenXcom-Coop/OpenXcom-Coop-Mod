"""test_desync_resync_campaign.py: the automatic desync repair in a co-op CAMPAIGN battle.
A client-only change to a host-seat soldier is found at the host's next action end, the host re-sends its live battle
behind its waiting screen and play continues; in SEPARATE the second player's own campaign (its own-world snapshot)
and its stored research are untouched.
  Boot shared_campaign (SHARED, key 48756, dirs desync_campaign_shared_host / _client):
  shared_fixture.bring_up("desync_campaign_shared", (1, 2, 48756)) + session.bring_up_shared_mixed_battle(js,
  {0: 0, 1: 1}, pre_landing = the host's set_seed SEED_SHARED); P = K = squad[0] (the one host-seat soldier), walker
  squad[1] (seat 1).
  shared_repair SHARED: B0, SPLIT0, HASH; the client-only set_stat reactions +7 on P; the host's real-UI kneel of K
      (its bt_action_end, saveBlob); REPAIRED. shared_repair-1 RS on both: desyncs +1, offered / completed / released
      +1 (host), teardowns / loaded +1 (client); shared_repair-2 HASH, SPLIT unchanged, battleId == B0;
      shared_repair-3 a client walk of squad[1] applies (walk_far, as in test_campaign_rejoin), HASH; shared_repair-4
      CRASH 0, client zero-disk.
  Boot separate_campaign (SEPARATE, key "48757", dirs desync_campaign_separate_host / _client):
  session.bring_up_separate_guest_battle(host, client, port="48757", pre_mission_start = separate_profile_set
  STR_PLASMA_PISTOL for the client's player on both machines, a topic the host lacks, so the seat-1 store check
  discriminates; pre_landing =
  the host's set_seed SEED_SEPARATE); GID = the one faction-0 unit named "Guest" (coop 1); P = host_squad[1],
  K = host_squad[0], walker GID.
  Both boots (test_desync_resync's boot order): mapFingerprint == MAP_FP_SHARED / MAP_FP_SEPARATE on both machines,
  pin_ai_neutral (a live alien's reaction shot during the kneel once killed P in shared_repair), wait_host_idle; a
  miss = setup failure.
  separate_repair SEPARATE: RES0 (the host's event_state.researchMode seats[1] {stored, count, unknown}); the poke +
      the kneel; REPAIRED. separate_repair-1 RS as shared_repair-1; separate_repair-2 HASH, SPLIT unchanged (GID on
      seat 1); separate_repair-3 the host's seats[1] == RES0, RES0 holds the client's topic (count >= 1) and the host's
      global research list lacks it (the seat's stored list); separate_repair-4 the guest's walk applies (walk_far),
      HASH; separate_repair-5 CRASH 0, client zero-disk.
Definitions (helpers imported, never edited): RS / NOTICE_OK / REPAIRED(host, client, B0, 1) / kneel / HASH / SPLIT
from test_desync_resync (REPAIRED within 45 s: host RS released +1, client RS loaded +1, the notices dismissed, both
tops BattlescapeState, phase Active, battleId B0, host peerAbsent false, client frozen false, no CoopState on the
host); walk_far from test_campaign_rejoin (the open tile at radius 1-3 farthest from any non-player; applies = >= 1
step, the final tile equal on both and != the start, == the last step unless a reaction / spotting halted it).
battle_state only with a BattlescapeState on top. The seat-1 names have no probe under research sync on (EVIDENCE).
Every cell is a GUARD. A boot miss FAILs its row "boot" with ONE CAPTURE line; a failed row prints ONE CAPTURE line;
every row runs after a failure; ONE run in the foreground, no skip path; exit 0 iff every cell passes, else 2.
"""
import os
import sys
import time
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import shared_fixture  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import test_delta_core as dc  # noqa: E402
import test_desync_resync as DR  # noqa: E402  (main-guarded: RS, REPAIRED, kneel, HASH, SPLIT, Row, capture)
import test_campaign_rejoin as CR  # noqa: E402  (main-guarded: walk_far)

KEY_SHARED, TAG_SHARED = 48756, "desync_campaign_shared"
KEY_SEPARATE, TAG_SEPARATE = "48757", "desync_campaign_separate"
SEED_SHARED, MAP_FP_SHARED = 1, 5.690100025079999e+18      # the host's set_seed before the landing; seed 1 (the
SEED_SEPARATE, MAP_FP_SEPARATE = 1, 5.690100025079999e+18  # first of 1..40) gives this terror map on both machines
                                                           # in both boots, walk_far walks, 0 reactions
POKE, TOPIC = 7, "STR_PLASMA_PISTOL"
SEQ_OFF, KIND = DR.SEQ_OFFSET, "bt_action_end"   # the desync seq = host lastSeqEmitted before K + 2 (measured on
                                                 # four boots of each kind)
DELTAS = ("desyncs", "offered", "completed", "released", "teardowns", "loaded")


class Row(DR.Row):
    def end(self, crash_cid, results, walls):
        """the CRASH + zero-disk cell (every case), the row's wall + CPU, ONE CAPTURE line when a cell failed, the row verdict"""
        new = sorted(session._crash_log_snapshot() - self.cr0)
        try:
            session.assert_client_zero_disk(self.x.client.user_dir)
            zd = "clean"
        except AssertionError as e:
            zd = DR.short(e, 300)
        self.cell(crash_cid, "GUARD", "CRASH 0 (no new crash_*.log in this lane's crash folder since the row's baseline); client zero-disk",
                  not new and zd == "clean", {"crash": new, "zero-disk": zd})
        walls[self.rid] = round(time.time() - self.t0, 1)
        print("EVIDENCE %s wall: %s s, cpu %s %%" % (self.rid, walls[self.rid], DR.cpu_pct(self.cpu0, DR.cpu_now())),
              flush=True)
        if self.fails:
            print("CAPTURE %s: %s" % (self.rid, DR.js(DR.capture(self.x))), flush=True)
        results[self.rid] = not self.fails
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)


def res(gc):
    """the host's stored seat-1 research: event_state.researchMode.seats[1] {stored, count, unknown} (+ the mode, EVIDENCE)"""
    rm = DR.q(gc, {"cmd": "event_state"}).get("researchMode") or {}
    s1 = next((s for s in rm.get("seats") or [] if s.get("seat") == 1), {})
    return {"seat1": {k: s1.get(k) for k in ("stored", "count", "unknown")}, "sync": rm.get("sync"), "separate": rm.get("separate"),
            "liveCount": rm.get("liveCount")}


def walk(x, uid, rid):
    """walk_far(host, client, uid) -> (applies on both + HASH, evidence)"""
    h, c = x.host, x.client
    wev = {"actor": uid, "start": DR.pos(DR.units(h).get(uid))}
    try:
        hw = CR.walk_far(h, c, uid, wev)
    except Exception as e:
        hw, wev["error"] = {}, DR.short(e, 300)
    steps = hw.get("steps") or []
    last, halted = (steps[-1].get("to") if steps else None), bool((hw.get("restate") or {}).get("halted"))
    wev.update(steps=len(steps), last=last, halted=halted, reason=(hw.get("restate") or {}).get("reason"),
               host=DR.pos(DR.units(h).get(uid)), client=DR.pos(DR.units(c).get(uid)))
    hok, wev["HASH"] = DR.hash_ok(h, c, rid + " after the walk")
    return (bool(steps) and wev["host"] is not None and wev["host"] == wev["client"] != wev["start"]
            and (halted or wev["host"] == (last["x"], last["y"], last["z"])) and hok), wev


def row(x, rid, results, walls):
    """shared_repair (SHARED) / separate_repair (SEPARATE): the poke, the host's kneel, REPAIRED, then the row's
    cells in order"""
    sep = rid == "separate_repair"
    ids = ["%s-%d" % (rid, i) for i in range(1, 6 if sep else 5)]
    r = Row(rid, ids[:-1], x)
    h, c = x.host, x.client
    try:
        rh0, rc0, nh, nc = DR.rs(h), DR.rs(c), len(DR.log(h)), len(DR.log(c))
        res0 = res(h) if sep else None
        r0 = DR.units(c).get(x.P, {}).get("reactions")
        rset = DR.q(c, {"cmd": "battle_action", "action": "set_stat", "unit": x.P, "stat": "reactions",
                        "value": (r0 or 0) + POKE})
        pv = {"P K walker": [x.P, x.K, x.walker], "set_stat": rset,
              "client reactions": [r0, DR.units(c).get(x.P, {}).get("reactions")],
              "host reactions": DR.units(h).get(x.P, {}).get("reactions"), "diff": dc.diff_buckets(h, c),
              "RES0": res0}
        print("EVIDENCE %s poke: %s" % (rid, DR.js(pv)), flush=True)
        if rset.get("ok") is not True or pv["diff"] != ["saveBlob"]:
            raise DR.Stop("SETUP-FAILURE: the client's set_stat on P %s / the diff %s (want ok, ['saveBlob'])"
                          % (x.P, pv["diff"]))
        t_press = time.time()
        s0, kev = DR.kneel(x, x.K)
        good, rev = DR.repaired(x, rh0, rc0, 1, t_press)
        rh, rc = DR.rs(h), DR.rs(c)
        want = {"bucket": "saveBlob", "seq": (s0 or 0) + SEQ_OFF, "kind": KIND, "battleId": x.b0}
        print("EVIDENCE %s: %s" % (rid, DR.js({"kneel": kev, "repair": rev,
                                               "repair wall (host log) s": DR.log_dt(h, nh, DR.RELEASED, t_press),
                                               "client DESYNC": DR.desync_line(c, nc),
                                               "last client/host": [rc.get("last"), rh.get("last")],
                                               "want last": want, "RS host": rh, "RS client": rc})), flush=True)
        dd = {k: [DR.delta(rh0, rh, k), DR.delta(rc0, rc, k)] for k in DELTAS}
        r.cell(ids[0], "GUARD", "RS on both: desyncs +1; offered / completed / released +1 (host); teardowns / loaded +1 (client)",
               dd["desyncs"] == [1, 1] and all(dd[k][0] == 1 for k in ("offered", "completed", "released"))
               and all(dd[k][1] == 1 for k in ("teardowns", "loaded")), {"deltas host/client": dd, "REPAIRED": good})
        if not good:
            raise DR.Stop("REPAIRED not reached within %.0f s (%s)" % (DR.W_REPAIR, rev.get("wait")))
        hok, hev = DR.hash_ok(h, c, rid + " after the repair")
        sh, sc = DR.split(h), DR.split(c)
        if not sep:
            bb = [DR.auth(h).get("battleId"), DR.auth(c).get("battleId")]
            r.cell(ids[1], "GUARD", "HASH; SPLIT(host) == SPLIT(client) == SPLIT0; battleId == B0 %s on both" % x.b0,
                   hok and sh == sc == x.split0 and bb == [x.b0, x.b0],
                   {"HASH": hev, "SPLIT host/client": [sh, sc], "SPLIT0": x.split0, "battleId host/client": bb})
            wok, wev = walk(x, x.walker, rid)
            r.cell(ids[2], "GUARD", "a client walk of squad[1] %s applies on both (walk_far: >= 1 step, the final tile equal and != the start, "
                   "== the last step unless halted); HASH" % x.walker, wok, wev)
        else:
            r.cell(ids[1], "GUARD", "HASH; SPLIT(host) == SPLIT(client) == SPLIT0 (the guest %s on seat 1)" % x.walker,
                   hok and sh == sc == x.split0 and [x.walker, 1] in sh, {"HASH": hev, "SPLIT host/client": [sh, sc], "SPLIT0": x.split0})
            res1 = res(h)
            live = DR.q(h, {"cmd": "geo_state"}).get("discoveredResearch")
            r.cell(ids[2], "GUARD", "the host's stored seat-1 research == RES0; RES0 holds the client's own topic "
                   "(stored, count >= 1) and the host's global research list lacks %s (the check discriminates)" % TOPIC,
                   res1["seat1"] == res0["seat1"] and res0["seat1"].get("stored") is True and (res0["seat1"].get("count") or 0) >= 1
                   and isinstance(live, list) and TOPIC not in live,
                   {"RES0": res0, "after": res1, "host live research": live,
                    "the client's pre-battle test command / lists": x.pre,
                    "names": "no probe under research sync on (coopSeatResearchNames unexposed; research_check reads the live world)"})
            wok, wev = walk(x, x.walker, rid)
            r.cell(ids[3], "GUARD", "the guest %s's walk applies on both (walk_far, as shared_repair-3); HASH"
                   % x.walker, wok, wev)
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end(ids[-1], results, walls)


def baseline(x):
    """both tops BattlescapeState; B0 equal non-zero; SPLIT0 equal with P on seat 0 and the walker on seat 1; HASH clean"""
    h, c = x.host, x.client
    tops = [DR.top(h), DR.top(c)]
    assert tops == [DR.BS, DR.BS], "SETUP-FAILURE: tops %s" % tops
    x.b0, x.split0 = DR.auth(h).get("battleId"), DR.split(h)
    bc, sc = DR.auth(c).get("battleId"), DR.split(c)
    seats = dict((u, s) for u, s in x.split0)
    assert x.b0 and x.b0 == bc and x.split0 == sc and seats.get(x.P) == 0 and seats.get(x.K) == 0 and seats.get(x.walker) == 1, (
        "SETUP-FAILURE: B0 %s / %s, SPLIT0 %s / %s, P %s K %s walker %s" % (x.b0, bc, x.split0, sc, x.P, x.K, x.walker))
    hok, hev = DR.hash_ok(h, c, "boot " + x.name)
    assert hok, "SETUP-FAILURE: HASH at the boot: %s" % hev
    print("[test_desync_resync_campaign] boot %s ok: mapFingerprint %s, pinned %s, B0 %s, SPLIT0 %s, P %s, K %s, "
          "walker %s, pre %s" % (
        x.name, x.fp, x.pinned, x.b0, x.split0, x.P, x.K, x.walker, DR.js(x.pre)), flush=True)


def pin(x, seed, want_fp, tag):
    """test_desync_resync's boot order: the seeded map on both machines, pin_ai_neutral (no alien can react to the
    kneel or the walk), the host idle"""
    x.fp = [session.battle_state(x.host).get("mapFingerprint"), session.battle_state(x.client).get("mapFingerprint")]
    assert x.fp == [want_fp, want_fp], "SETUP-FAILURE: mapFingerprint %s (want %r, seed %d)" % (x.fp, want_fp, seed)
    x.pinned = session.pin_ai_neutral(x.host, x.client, tag=tag)
    assert x.pinned, "SETUP-FAILURE: pin_ai_neutral pinned no NONE-seat non-player unit"
    session.wait_host_idle(x.host, x.client, timeout=DR.W_IDLE)


def new_x(name):
    return SimpleNamespace(name=name, host=None, client=None, err=None, b0=None, split0=None, P=None, K=None, walker=None, pre={},
                           fp=None, pinned=None)


def boot_shared():
    """boot shared_campaign (SHARED): shared_fixture.bring_up + bring_up_shared_mixed_battle(js, {0: 0, 1: 1})"""
    x = new_x("shared_campaign")
    try:
        js = shared_fixture.bring_up(TAG_SHARED, (1, 2, KEY_SHARED))
        x.host, x.client = js.host, js.client
        _h, _c, squad = session.bring_up_shared_mixed_battle(
            js, {0: 0, 1: 1}, pre_landing=lambda h, c: h.ok({"cmd": "set_seed", "seed": SEED_SHARED}))
        x.P = x.K = squad[0]
        x.walker = squad[1]
        pin(x, SEED_SHARED, MAP_FP_SHARED, TAG_SHARED)
        baseline(x)
    except Exception as e:
        x.err = DR.short(e, 800)
    return x


def boot_separate():
    """boot separate_campaign (SEPARATE): bring_up_separate_guest_battle with the client's own-world topic
    before the mission"""
    x = new_x("separate_campaign")
    try:
        x.host, x.client = (GameClient("host", 1, make_user_dir(TAG_SEPARATE + "_host")),
                            GameClient("client", 2, make_user_dir(TAG_SEPARATE + "_client")))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()

        def f(host, client):  # one shared save: the client's player gets the topic on both machines
            x.pre["grant"] = [DR.q(gc, {"cmd": "separate_profile_set", "player": "ClientPlayer", "research": TOPIC})
                              for gc in (client, host)]
            x.pre["client research"] = DR.q(client, {"cmd": "geo_state"}).get("discoveredResearch")
            x.pre["host research"] = DR.q(host, {"cmd": "geo_state"}).get("discoveredResearch")
        hsq, _guest_local = session.bring_up_separate_guest_battle(
            x.host, x.client, port=KEY_SEPARATE, pre_mission_start=f,
            pre_landing=lambda h, c: h.ok({"cmd": "set_seed", "seed": SEED_SEPARATE}))
        grant = x.pre.get("grant") or []
        assert len(grant) == 2 and all(g.get("ok") is True and g.get("researchAdded") is True for g in grant), (
            "SETUP-FAILURE: separate_profile_set %s for the client's player: %s" % (TOPIC, grant))
        gids = [u.get("id") for u in DR.bs(x.host).get("units") or [] if u.get("faction") == 0
                and "Guest" in str(u.get("name"))]
        assert len(gids) == 1, "SETUP-FAILURE: GID = exactly one faction-0 unit named \"Guest\": %s" % gids
        x.P, x.K, x.walker = hsq[1], hsq[0], gids[0]
        pin(x, SEED_SEPARATE, MAP_FP_SEPARATE, TAG_SEPARATE)
        baseline(x)
    except Exception as e:
        x.err = DR.short(e, 800)
    return x


BOOTS = (("shared_campaign", boot_shared, "shared_repair"), ("separate_campaign", boot_separate, "separate_repair"))


def main():
    t0, results, walls, failed = time.time(), {}, {}, []
    for name, boot, rid in BOOTS:
        tb = time.time()
        x = boot()
        walls[name + " boot"] = round(time.time() - tb, 1)
        if x.err:
            print("EVIDENCE %s boot: %s\nCAPTURE %s boot: %s" % (rid, x.err, rid, DR.js(DR.capture(x))), flush=True)
            print("FAIL %s boot: boot %s did not reach the tactical map with its pins" % (rid, name), flush=True)
            results[rid] = False
        else:
            row(x, rid, results, walls)
        failed += DR.shut(x)
        walls[name] = round(time.time() - tb, 1)
    failed += [rid for _n, _b, rid in BOOTS if not results.get(rid)]
    print("\ntest_desync_resync_campaign: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (
        sum(1 for _n, _b, rid in BOOTS if results.get(rid)), len(BOOTS), failed, DR.js(walls), time.time() - t0),
          flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
