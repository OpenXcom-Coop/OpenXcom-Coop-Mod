"""W2-H84 RAP (tools/coop_test/test_rejoin_after_push.py): a partner who dropped during the host's quick save, rejoined and then uploaded
its world (a soldier gift) keeps the host's saveID, so a second drop + rejoin restores its own campaign (lead L-H79-3, ruling R-LH79-3-1;
VL-H84-1). Spec docs rewrite/prompts/w2h84_rejoin_join_id.md (f); TASK 0 values in rewrite/w2h84-task0/sa/CONSTANTS.md; capture
rewrite/lh79-3-cap. Helpers: rejoin_helpers.py (RH); fixture drop_fixture.py (F) imported unchanged.
id0 = the campaign's first saveID; id1 = S1's; id2 = D1's re-mint (W2-H58 copies host_<id1> to host_<id2> with id1's bytes); id3 = S3's.
Each row boots its own pair on lobby key 49498 (SEPARATE new_campaign), NAME = the host's get_coop.clientName, MARKER = the client's own bases
and soldiers; S1 = a quick save with the client running; D1 = the client dropped at the host's first 54; every rejoiner is a NEW client
on a fresh dir joining by NAME (never a base placement: a fresh world is evidence), RESUME only after the host's ack.
  Row X1  (capture X1) BOOT; S1; D1; REJOIN(2) + RESUME; read M; GIFT (the host's real presses) + PUSH (client2's unasked upload); read G;
          KILL client2; REJOIN(3); read R.
          X1-pre (GUARD) S1, D1 (at the 54 host_<id2> holds host_<id1>'s fnv), REJOIN(2) ack + RESUME.
          X1-ids (RED) read M: client2's saveID (get_coop and save_markers) == the host's == id2.
          X1-own (RED) read M: client2's coop_file_info {role own_world} present under client_<id2>_<NAME>.data.
          X1-log (RED) read M: client2's log holds >= 1 '[coop] own world "' line.
          X1-push (GUARD) one soldier gifted (RECV), client2's push line, the host's host_<id2> fnv changed.
          X1-host (RED) read G: the host's saveID == id2 and the push line's key == client_<id2>_<NAME>.data.
          X1-rejoin (RED) REJOIN(3): no BuildNewBaseState, client3's 68 within JOIN_S, the host's ack within ACK_S.
          X1-world (RED) read R: client3's own bases == MARKER's and its soldiers hold the gifted one.
          X1-resume (RED) resume_and_clear ok and both tops GeoscapeState.  X1-common (GUARD) host + client3 alive, no new crash file.
  Row CTL (captures X1-ctl + X2, the controls) BOOT; S1; D1; REJOIN(2) + RESUME; KILL client2; REJOIN(3) + RESUME; read R1; GIFT + PUSH to
          client3; S3 = a quick save with client3 running; read H; KILL client3; REJOIN(4) + RESUME; read R2.
          CTL-pre (GUARD) S1, D1, REJOIN(2) ack + RESUME. CTL-r1 (GUARD) REJOIN(3) 68 + ack + RESUME, no BuildNewBaseState.
          CTL-w1 (GUARD) read R1: client3's own == MARKER's. CTL-push (GUARD) as X1-push for client3.
          CTL-heal (GUARD) S3 ok; read H: the host's saveID == client3's == id3; host_<id3> present.
          CTL-r2 (GUARD) as CTL-r1 for client4. CTL-w2 (GUARD) read R2: client4's own == MARKER's and its soldiers hold the gifted one.
          CTL-common (GUARD) host + client4 alive, no new crash file. No CTL cell reads a kept count, an id before S3 or the W2-H58
          copy count (they differ red / green by design; EVIDENCE records them).
Red today (no W2-H84 fix): X1-ids, X1-own, X1-log, X1-host, X1-rejoin, X1-world, X1-resume FAIL (7 of 18); every other cell PASS.
One EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; a precondition miss ends its row (later cells "not reached",
one CAPTURE line); every row runs after a failure. ONE foreground run, no SKIP; exit 0 only when every cell
passes, else 2. Run: python tools/coop_test/test_rejoin_after_push.py   (OXC_HARNESS_SLOT selects the lane)"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drop_fixture as F  # noqa: E402
import rejoin_helpers as RH  # noqa: E402

KEY = "49498"
X1 = ("X1-pre", "X1-ids", "X1-own", "X1-log", "X1-push", "X1-host", "X1-rejoin", "X1-world", "X1-resume", "X1-common")
CTL = ("CTL-pre", "CTL-r1", "CTL-w1", "CTL-push", "CTL-heal", "CTL-r2", "CTL-w2", "CTL-common")
RED = ("X1-ids", "X1-own", "X1-log", "X1-host", "X1-rejoin", "X1-world", "X1-resume")


def first_rejoin(r, host, client):
    """S1, D1, REJOIN(2) + RESUME; the row's -pre cell; returns client2"""
    ok, lab = RH.s1_d1(r, host, client)
    c2 = r.add(RH.rejoiner(r.tag, 2))
    rj, rc = RH.rejoin_resume(r, host, c2, "J2")
    pre = ok and rj["ack"] is not None and bool(rc and rc["ok"])
    r.cell(r.rid + "-pre", pre, "%s; REJOIN(2) %s" % (lab, rj["lab"]))
    r.need(pre, "S1 / D1 / REJOIN(2) + RESUME")
    return c2


def own_world(gc):
    return F._pick(F.q(gc, {"cmd": "coop_file_info", "role": "own_world"}), ("key", "present", "bytes", "fnv1a64"))


def row_x1(r):
    host, client = RH.start(r)
    c2 = first_rejoin(r, host, client)
    id0, id1, id2 = r.ev["marker"]["id0"], r.id1, r.id2
    ii, ow, k = RH.ids(host, c2), own_world(c2), RH.kept(c2)
    r.ev["M"] = {"ids": ii, "own_world": ow, "kept": k, "keys": {str(i): RH.kk(host, i, r.name) for i in (id0, id1, id2)}}
    r.cell("X1-ids", ii["client"] == [id2, id2] and ii["host"] == [id2, id2], "read M %s (id1 %s, id2 %s)" % (ii, id1, id2))
    r.cell("X1-own", ow.get("present") is True and ow.get("key") == "client_%s_%s.data" % (id2, r.name), "read M client2 own_world %s" % ow)
    r.cell("X1-log", k >= 1, "read M kept(client2) %d" % k)
    gp = RH.gift_push(r, host, c2, "GIFT")
    r.cell("X1-push", gp["ok"], gp["lab"])
    r.need(gp["ok"], "GIFT / PUSH")
    hid = [F.coop(host).get("saveID"), F.sid(host)]
    r.ev["G"] = {"host": hid, "keys": {str(i): RH.kk(host, i, r.name) for i in (id0, id1, id2)}}
    r.cell("X1-host", hid == [id2, id2] and gp["pushKey"] == "client_%s_%s.data" % (id2, r.name),
           "read G host saveID %s; push key %s (id1 %s, id2 %s)" % (hid, gp["pushKey"], id1, id2))
    r.ev["NOTICE"] = RH.partner_notice_ok(c2)
    RH.kill(r, c2, host, "KILL")
    c3 = r.add(RH.rejoiner(r.tag, 3))
    rj, rc = RH.rejoin_resume(r, host, c3, "J3", RH.HOLD_R)
    RH.tail(r, host, c3, rj, rc, gp["gifted"])


def row_ctl(r):
    host, client = RH.start(r)
    c2 = first_rejoin(r, host, client)
    r.ev["M"] = {"ids": RH.ids(host, c2), "kept": RH.kept(c2)}  # EVIDENCE only (differs red / green by design)
    RH.kill(r, c2, host, "KILL2")
    c3 = r.add(RH.rejoiner(r.tag, 3))
    rj, rc = RH.rejoin_resume(r, host, c3, "J3")
    r.cell("CTL-r1", rj["ok"] and bool(rc and rc["ok"]), "client3: " + rj["lab"])
    r.need(rj["ok"] and rc and rc["ok"], "REJOIN(3) + RESUME")
    o3 = RH.own(c3)
    r.ev["R1"] = {"own": o3, "ids": RH.ids(host, c3), "kept": RH.kept(c3)}
    r.cell("CTL-w1", o3 == r.marker[0], "read R1 own(client3) %s (MARKER %s)" % (o3, r.marker[0]))
    gp = RH.gift_push(r, host, c3, "GIFT")
    r.cell("CTL-push", gp["ok"], gp["lab"])
    r.need(gp["ok"], "GIFT / PUSH")
    r.ev["NOTICE"] = RH.partner_notice_ok(c3)
    s3 = F.quick_save(host, F.QUICK, RH.SAVE_S)
    id3 = s3.get("saveIDAfter")
    r.ev["S3"] = RH.pick(s3, ("ok", "seen54", "written", "t", "saveIDBefore", "saveIDAfter", "log"))
    time.sleep(RH.HOLD)
    ii, k3 = RH.ids(host, c3), RH.kk(host, id3, r.name)
    r.ev["H"] = {"ids": ii, "kk3": k3, "kept": RH.kept(c3)}
    r.cell("CTL-heal", s3["ok"] and ii["host"] == [id3, id3] and ii["client"] == [id3, id3] and k3.get("present") is True,
           "S3 %s (54 seen %s, written %s); read H %s (id3 %s); host_<id3> %s" % (s3["ok"], s3["seen54"], s3["written"], ii, id3, k3))
    r.need(s3["ok"], "S3")
    RH.kill(r, c3, host, "KILL3")
    c4 = r.add(RH.rejoiner(r.tag, 4))
    rj4, rc4 = RH.rejoin_resume(r, host, c4, "J4", RH.HOLD_R)
    r.cell("CTL-r2", rj4["ok"] and bool(rc4 and rc4["ok"]), "client4: " + rj4["lab"])
    o4, s4 = RH.own(c4), RH.ownsold(c4)
    r.ev["R2"] = {"own": o4, "ownsold": s4, "ids": RH.ids(host, c4), "kept": RH.kept(c4)}
    r.cell("CTL-w2", o4 == r.marker[0] and gp["gifted"] in s4,
           "read R2 own(client4) %s (MARKER %s); soldiers hold %r: %s" % (o4, r.marker[0], gp["gifted"], gp["gifted"] in s4))
    new = [os.path.basename(p) for p in sorted(F.crashes() - r.c0)]
    r.cell("CTL-common", RH.alive(host) and RH.alive(c4) and not new,
           "host alive %s; client4 alive %s; new crash files %s" % (RH.alive(host), RH.alive(c4), new))


def main():
    return RH.run("W2-H84 RAP", (("X1", X1, row_x1, "w2h84_x1", KEY), ("CTL", CTL, row_ctl, "w2h84_ctl", KEY)), RED)


if __name__ == "__main__":
    sys.exit(main())
