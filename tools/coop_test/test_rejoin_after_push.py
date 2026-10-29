"""A partner who dropped during the host's quick save, rejoined and then uploaded its world (a soldier gift) keeps the host's saveID,
so a second drop + rejoin restores its own campaign. Helpers: rejoin_helpers.py (RH); fixture drop_fixture.py (F) imported unchanged.
id0 = the campaign's first saveID; id1 = first_save's; id2 = first_drop's re-mint (the host copies host_<id1> to host_<id2> with id1's
bytes); id3 = heal_save's.
Each row boots its own pair on lobby key 49498 (SEPARATE new_campaign), NAME = the host's get_coop.clientName, MARKER = the client's own bases
and soldiers; first_save = a quick save with the client running; first_drop = the client dropped at the host's first 54; every rejoiner is
a NEW client on a fresh dir joining by NAME (never a base placement: a fresh world is evidence), RESUME only after the host's ack.
  Row upload_rejoin: BOOT; first_save; first_drop; REJOIN(2) + RESUME; read joined; GIFT (the host's real presses) + PUSH (client2's
          unasked upload); read after_gift; KILL client2; REJOIN(3); read rejoined.
          upload_rejoin-pre (GUARD) first_save, first_drop (at the 54 host_<id2> holds host_<id1>'s fnv), REJOIN(2) ack + RESUME.
          upload_rejoin-ids (FIX) read joined: client2's saveID (get_coop and save_markers) == the host's == id2.
          upload_rejoin-own (FIX) read joined: client2's coop_file_info {role own_world} present under client_<id2>_<NAME>.data.
          upload_rejoin-log (FIX) read joined: client2's log holds >= 1 '[coop] own world "' line.
          upload_rejoin-push (GUARD) one soldier gifted (RECV), client2's push line, the host's host_<id2> fnv changed.
          upload_rejoin-host (FIX) read after_gift: the host's saveID == id2 and the push line's key == client_<id2>_<NAME>.data.
          upload_rejoin-rejoin (FIX) REJOIN(3): no BuildNewBaseState, client3's 68 within JOIN_S, the host's ack within ACK_S.
          upload_rejoin-world (FIX) read rejoined: client3's own bases == MARKER's and its soldiers hold the gifted one.
          upload_rejoin-resume (FIX) resume_and_clear ok and both tops GeoscapeState.
          upload_rejoin-common (GUARD) host + client3 alive, no new crash file.
  Row control (the controls): BOOT; first_save; first_drop; REJOIN(2) + RESUME; KILL client2; REJOIN(3) + RESUME; read rejoined3;
          GIFT + PUSH to client3; heal_save = a quick save with client3 running; read after_heal_save; KILL client3; REJOIN(4) + RESUME;
          read rejoined4.
          control-pre (GUARD) first_save, first_drop, REJOIN(2) ack + RESUME.
          control-client3_rejoin (GUARD) REJOIN(3) 68 + ack + RESUME, no BuildNewBaseState.
          control-client3_world (GUARD) read rejoined3: client3's own == MARKER's. control-push (GUARD) as upload_rejoin-push for client3.
          control-heal (GUARD) heal_save ok; read after_heal_save: the host's saveID == client3's == id3; host_<id3> present.
          control-client4_rejoin (GUARD) as control-client3_rejoin for client4.
          control-client4_world (GUARD) read rejoined4: client4's own == MARKER's and its soldiers hold the gifted one.
          control-common (GUARD) host + client4 alive, no new crash file. No control cell reads a kept count, an id before heal_save or
          the host's world-copy count (they differ with and without the fix by design; EVIDENCE records them).
FIX cells fail on a build without the saveID fix: upload_rejoin-ids, upload_rejoin-own, upload_rejoin-log, upload_rejoin-host,
upload_rejoin-rejoin, upload_rejoin-world, upload_rejoin-resume (7 of 18); every other cell passes there too.
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
UPLOAD_REJOIN = ("upload_rejoin-pre", "upload_rejoin-ids", "upload_rejoin-own", "upload_rejoin-log", "upload_rejoin-push", "upload_rejoin-host", "upload_rejoin-rejoin", "upload_rejoin-world", "upload_rejoin-resume", "upload_rejoin-common")
CONTROL = ("control-pre", "control-client3_rejoin", "control-client3_world", "control-push", "control-heal", "control-client4_rejoin", "control-client4_world", "control-common")
FIX = ("upload_rejoin-ids", "upload_rejoin-own", "upload_rejoin-log", "upload_rejoin-host", "upload_rejoin-rejoin", "upload_rejoin-world", "upload_rejoin-resume")


def first_rejoin(r, host, client):
    """first_save, first_drop, REJOIN(2) + RESUME; the row's -pre cell; returns client2"""
    ok, lab = RH.save_then_drop(r, host, client)
    c2 = r.add(RH.rejoiner(r.tag, 2))
    rj, rc = RH.rejoin_resume(r, host, c2, "client2_join")
    pre = ok and rj["ack"] is not None and bool(rc and rc["ok"])
    r.cell(r.rid + "-pre", pre, "%s; REJOIN(2) %s" % (lab, rj["lab"]))
    r.need(pre, "first_save / first_drop / REJOIN(2) + RESUME")
    return c2


def own_world(gc):
    return F._pick(F.q(gc, {"cmd": "coop_file_info", "role": "own_world"}), ("key", "present", "bytes", "fnv1a64"))


def row_upload_rejoin(r):
    host, client = RH.start(r)
    c2 = first_rejoin(r, host, client)
    id0, id1, id2 = r.ev["marker"]["id0"], r.id1, r.id2
    ii, ow, k = RH.ids(host, c2), own_world(c2), RH.kept(c2)
    r.ev["joined"] = {"ids": ii, "own_world": ow, "kept": k, "keys": {str(i): RH.kk(host, i, r.name) for i in (id0, id1, id2)}}
    r.cell("upload_rejoin-ids", ii["client"] == [id2, id2] and ii["host"] == [id2, id2], "read joined %s (id1 %s, id2 %s)" % (ii, id1, id2))
    r.cell("upload_rejoin-own", ow.get("present") is True and ow.get("key") == "client_%s_%s.data" % (id2, r.name), "read joined client2 own_world %s" % ow)
    r.cell("upload_rejoin-log", k >= 1, "read joined kept(client2) %d" % k)
    gp = RH.gift_push(r, host, c2, "GIFT")
    r.cell("upload_rejoin-push", gp["ok"], gp["lab"])
    r.need(gp["ok"], "GIFT / PUSH")
    hid = [F.coop(host).get("saveID"), F.sid(host)]
    r.ev["after_gift"] = {"host": hid, "keys": {str(i): RH.kk(host, i, r.name) for i in (id0, id1, id2)}}
    r.cell("upload_rejoin-host", hid == [id2, id2] and gp["pushKey"] == "client_%s_%s.data" % (id2, r.name),
           "read after_gift host saveID %s; push key %s (id1 %s, id2 %s)" % (hid, gp["pushKey"], id1, id2))
    r.ev["NOTICE"] = RH.partner_notice_ok(c2)
    RH.kill(r, c2, host, "KILL")
    c3 = r.add(RH.rejoiner(r.tag, 3))
    rj, rc = RH.rejoin_resume(r, host, c3, "client3_join", RH.HOLD_R)
    RH.tail(r, host, c3, rj, rc, gp["gifted"])


def row_control(r):
    host, client = RH.start(r)
    c2 = first_rejoin(r, host, client)
    r.ev["joined"] = {"ids": RH.ids(host, c2), "kept": RH.kept(c2)}  # EVIDENCE only (differs with and without the fix by design)
    RH.kill(r, c2, host, "KILL2")
    c3 = r.add(RH.rejoiner(r.tag, 3))
    rj, rc = RH.rejoin_resume(r, host, c3, "client3_join")
    r.cell("control-client3_rejoin", rj["ok"] and bool(rc and rc["ok"]), "client3: " + rj["lab"])
    r.need(rj["ok"] and rc and rc["ok"], "REJOIN(3) + RESUME")
    o3 = RH.own(c3)
    r.ev["rejoined3"] = {"own": o3, "ids": RH.ids(host, c3), "kept": RH.kept(c3)}
    r.cell("control-client3_world", o3 == r.marker[0], "read rejoined3 own(client3) %s (MARKER %s)" % (o3, r.marker[0]))
    gp = RH.gift_push(r, host, c3, "GIFT")
    r.cell("control-push", gp["ok"], gp["lab"])
    r.need(gp["ok"], "GIFT / PUSH")
    r.ev["NOTICE"] = RH.partner_notice_ok(c3)
    s3 = F.quick_save(host, F.QUICK, RH.SAVE_S)
    id3 = s3.get("saveIDAfter")
    r.ev["heal_save"] = RH.pick(s3, ("ok", "seen54", "written", "t", "saveIDBefore", "saveIDAfter", "log"))
    time.sleep(RH.HOLD)
    ii, k3 = RH.ids(host, c3), RH.kk(host, id3, r.name)
    r.ev["after_heal_save"] = {"ids": ii, "kk3": k3, "kept": RH.kept(c3)}
    r.cell("control-heal", s3["ok"] and ii["host"] == [id3, id3] and ii["client"] == [id3, id3] and k3.get("present") is True,
           "heal_save %s (54 seen %s, written %s); read after_heal_save %s (id3 %s); host_<id3> %s" % (s3["ok"], s3["seen54"], s3["written"], ii, id3, k3))
    r.need(s3["ok"], "heal_save")
    RH.kill(r, c3, host, "KILL3")
    c4 = r.add(RH.rejoiner(r.tag, 4))
    rj4, rc4 = RH.rejoin_resume(r, host, c4, "client4_join", RH.HOLD_R)
    r.cell("control-client4_rejoin", rj4["ok"] and bool(rc4 and rc4["ok"]), "client4: " + rj4["lab"])
    o4, s4 = RH.own(c4), RH.ownsold(c4)
    r.ev["rejoined4"] = {"own": o4, "ownsold": s4, "ids": RH.ids(host, c4), "kept": RH.kept(c4)}
    r.cell("control-client4_world", o4 == r.marker[0] and gp["gifted"] in s4,
           "read rejoined4 own(client4) %s (MARKER %s); soldiers hold %r: %s" % (o4, r.marker[0], gp["gifted"], gp["gifted"] in s4))
    new = [os.path.basename(p) for p in sorted(F.crashes() - r.c0)]
    r.cell("control-common", RH.alive(host) and RH.alive(c4) and not new,
           "host alive %s; client4 alive %s; new crash files %s" % (RH.alive(host), RH.alive(c4), new))


def main():
    return RH.run("rejoin after push", (("upload_rejoin", UPLOAD_REJOIN, row_upload_rejoin, "rejoin_upload", KEY), ("control", CONTROL, row_control, "rejoin_control", KEY)), FIX)


if __name__ == "__main__":
    sys.exit(main())
