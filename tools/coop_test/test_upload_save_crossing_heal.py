"""W2-H86 UXH (tools/coop_test/test_upload_save_crossing_heal.py): after a partner upload crossed a host quick save, the host's next
save copies the partner's world to the new id, so a drop during that save and a rejoin still restore the partner's own campaign
(lead L-LT17-1, ruling R-LLT17-1-1; VL-H86-1, VL-H86-2; QH86-3 (a)). Spec docs rewrite/prompts/w2h86_upload_save_crossing.md (f); TASK 0
values in rewrite/w2h86-task0/sa/CONSTANTS.md; capture rewrite/llt17-1-cap. Helpers: crossing_helpers.py (CH: the
crossing on the TEST-ONLY levers hold_blob_ack scope "upload" and hold_save_reply); rejoin_helpers.py (RH) and drop_fixture.py
(F) imported unchanged.
id1 = S1's saveID; id2 = the crossing save's re-mint (S2); id3 = the next save's (S3 / D3). Each row boots its own pair on lobby key 49644
(SEPARATE new_campaign); NAME = the host's get_coop.clientName; MARKER = the client's own bases and soldiers; every rejoiner is a NEW
client on a fresh dir joining by NAME (never a base placement: a fresh world is evidence); RESUME only after the host's ack
(resume_and_clear CANCELs a stale 54, F18431).
  Row U2  (capture U2, the heal) CROSSING (CH); NOTICE; S3 = a quick save with the partner running; HOLD; read H; KILL; REJOIN; read R.
          U2-pre (GUARD) every CROSSING step met; NOTICE ok.
          U2-copied (RED) S3's "[coop] W2-H58: N partner world(s) copied from saveID <id2> to <id3>" with N >= 1.
          U2-heal (GUARD) S3 ok, id3 != id2; read H: host == partner == id3 and host_<id3> present.
          U2-rejoin, U2-world, U2-resume, U2-common (GUARD) as UXC's U1 cells (the completed heal save restores the own world).
  Row U2D (the heal-save gap, F22906) CROSSING (CH); NOTICE; D3 = the partner dropped at the host's first 54 of the next quick save
          (probe: id3, host_<id3>, host_<id2>, host_<id1>); REJOIN; read R.
          U2D-pre (GUARD) every CROSSING step met; NOTICE ok; D3 ok (54 seen, the 62 after the kill), id3 != id2, and at the 54 no answer
          stored yet (host_<id3> absent or holding host_<id2>'s bytes).
          U2D-copied (RED) D3's W2-H58 line "N ... from saveID <id2> to <id3>" with N >= 1.  U2D-key (RED) at D3's 54: host_<id3> present.
          U2D-rejoin (RED) no BuildNewBaseState, 68 within JOIN_S, ack within ACK_S.
          U2D-world (RED) read R: the rejoiner's own bases == MARKER's and its soldiers hold the gifted one.
          U2D-resume (RED) resume_and_clear ok, both tops GeoscapeState.  U2D-common (GUARD) host + rejoiner alive, no new crash file.
Red today (no W2-H86 fix): U2-copied, U2D-copied, U2D-key, U2D-rejoin, U2D-world, U2D-resume FAIL (6 of 14); every other cell PASS.
One EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; a precondition miss ends its row (later cells "not reached",
one CAPTURE line); every row runs after a failure. ONE foreground run, no SKIP; exit 0 only when every cell
passes, else 2. Run: python tools/coop_test/test_upload_save_crossing_heal.py   (OXC_HARNESS_SLOT selects the lane)"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drop_fixture as F  # noqa: E402
import rejoin_helpers as RH  # noqa: E402
import crossing_helpers as CH  # noqa: E402

KEY = "49644"
U2 = ("U2-pre", "U2-copied", "U2-heal", "U2-rejoin", "U2-world", "U2-resume", "U2-common")
U2D = ("U2D-pre", "U2D-copied", "U2D-key", "U2D-rejoin", "U2D-world", "U2D-resume", "U2D-common")
RED = ("U2-copied", "U2D-copied", "U2D-key", "U2D-rejoin", "U2D-world", "U2D-resume")


def crossing_notice(r, host, client):
    x = CH.crossing(r, host, client)
    r.ev["NOTICE"] = nt = RH.partner_notice_ok(client)
    if not nt.get("ok"):
        r.cell(r.rid + "-pre", False, "%s; NOTICE %s" % (x["lab"], nt))
        raise RH.Stop("NOTICE")
    return x


def rejoin_tail(r, host):
    """REJOIN (a NEW <tag>_client2 by NAME); read R"""
    c2 = r.add(RH.rejoiner(r.tag, 2))
    rj, rc = RH.rejoin_resume(r, host, c2, "J2")
    RH.tail(r, host, c2, rj, rc, r.gifted)


def row_u2(r):
    host, client = RH.start(r)
    x = crossing_notice(r, host, client)
    r.cell("U2-pre", True, x["lab"] + "; NOTICE ok")
    n3 = len(F.logl(host))
    s3 = F.quick_save(host, F.QUICK, RH.SAVE_S)
    r.id3 = s3.get("saveIDAfter")
    h = CH.world_copy_since(host, n3)
    r.ev["S3"] = dict(RH.pick(s3, ("ok", "seen54", "written", "t", "saveIDBefore", "saveIDAfter", "log")), w58=h)
    r.cell("U2-copied", bool(h and h[0] >= 1 and h[1:] == (r.id2, r.id3)), "S3's W2-H58 %s (id2 %s, id3 %s)" % (h, r.id2, r.id3))
    time.sleep(RH.HOLD)
    ii, k3 = RH.ids(host, client), RH.kk(host, r.id3, r.name)
    r.ev["H"] = {"ids": ii, "kk3": k3}
    r.cell("U2-heal", s3["ok"] and r.id3 != r.id2 and ii["host"] == [r.id3, r.id3] and ii["client"] == [r.id3, r.id3]
           and k3.get("present") is True, "S3 %s (54 %s, written %s); read H %s (id3 %s); host_<id3> %s" % (
               s3["ok"], s3["seen54"], s3["written"], ii, r.id3, k3.get("present")))
    r.need(s3["ok"], "S3")
    RH.kill(r, client, host, "KILL")
    rejoin_tail(r, host)


def row_u2d(r):
    host, client = RH.start(r)
    x = crossing_notice(r, host, client)

    def probe(h):
        i3 = F.sid(h)
        return {"saveID": i3, "id3": RH.kk(h, i3, r.name), "id2": RH.kk(h, r.id2, r.name), "id1": RH.kk(h, r.id1, r.name)}
    d3 = F.drop_at_54(host, client, "quick", 0, probe, RH.SEEN_S, RH.DROP_S)
    r.ev["D3"] = RH.pick(d3, ("ok", "why", "seen54", "suspend", "probe", "kill", "log"))
    p = d3.get("probe") or {}
    r.id3 = p.get("saveID")
    p3, p2 = p.get("id3") or {}, p.get("id2") or {}
    noans = p3.get("present") is not True or p3.get("fnv1a64") == p2.get("fnv1a64")
    ok = bool(d3.get("ok") and r.id3 != r.id2 and noans)
    r.cell("U2D-pre", ok, "%s; NOTICE ok; D3 %s (%s; id3 %s; at the 54 no answer stored %s)" % (
        x["lab"], d3.get("ok"), d3.get("why") or "54 seen, 62 after the kill", r.id3, noans))
    r.need(ok, "D3")
    h = CH.world_copy_since(host, d3["n0"])
    r.cell("U2D-copied", bool(h and h[0] >= 1 and h[1:] == (r.id2, r.id3)), "D3's W2-H58 %s (id2 %s, id3 %s)" % (h, r.id2, r.id3))
    r.cell("U2D-key", p3.get("present") is True, "at D3's 54: host_<id3> %s; host_<id2> %s; host_<id1> %s" % (
        p3.get("present"), p2.get("present"), (p.get("id1") or {}).get("present")))
    rejoin_tail(r, host)


def main():
    return RH.run("W2-H86 UXH", (("U2", U2, row_u2, "w2h86_u2", KEY), ("U2D", U2D, row_u2d, "w2h86_u2d", KEY)), RED)


if __name__ == "__main__":
    sys.exit(main())
