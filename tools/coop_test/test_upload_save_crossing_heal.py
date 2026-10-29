"""After a partner upload crossed a host quick save, the host's next save copies the partner's world to the new id, so a drop during
that save and a rejoin still restore the partner's own campaign. Helpers: crossing_helpers.py (CH: the crossing on the test-only hooks
hold_blob_ack scope "upload" and hold_save_reply); rejoin_helpers.py (RH) and drop_fixture.py (F).
id1 = first_save's saveID; id2 = the crossing save's re-mint (crossing_save); id3 = the next save's (heal_save / heal_drop). Each row boots its own pair on lobby key 49644
(SEPARATE new_campaign); NAME = the host's get_coop.clientName; MARKER = the client's own bases and soldiers; every rejoiner is a NEW
client on a fresh dir joining by NAME (never a base placement: a fresh world is evidence); RESUME only after the host's ack
(resume_and_clear CANCELs a stale 54).
  Row heal (the heal): CROSSING (CH); NOTICE; heal_save = a quick save with the partner running; HOLD; after_heal; KILL; REJOIN; read R.
          heal-pre (GUARD) every CROSSING step met; NOTICE ok.
          heal-copied (RED) heal_save's "[coop] N partner world(s) copied from saveID <id2> to <id3>" with N >= 1.
          heal-healed (GUARD) heal_save ok, id3 != id2; after_heal: host == partner == id3 and host_<id3> present.
          heal-rejoin, heal-world, heal-resume, heal-common (GUARD) as test_upload_save_crossing.py's crossed cells (the completed heal save restores the own world).
  Row drop_in_heal (a drop during the heal save): CROSSING (CH); NOTICE; heal_drop = the partner dropped at the host's first 54 of the next quick save
          (probe: id3, host_<id3>, host_<id2>, host_<id1>); REJOIN; read R.
          drop_in_heal-pre (GUARD) every CROSSING step met; NOTICE ok; heal_drop ok (54 seen, the 62 after the kill), id3 != id2, and at the 54 no answer
          stored yet (host_<id3> absent or holding host_<id2>'s bytes).
          drop_in_heal-copied (RED) heal_drop's world-copy line "N ... from saveID <id2> to <id3>" with N >= 1.  drop_in_heal-key (RED) at heal_drop's 54: host_<id3> present.
          drop_in_heal-rejoin (RED) no BuildNewBaseState, 68 within JOIN_S, ack within ACK_S.
          drop_in_heal-world (RED) read R: the rejoiner's own bases == MARKER's and its soldiers hold the gifted one.
          drop_in_heal-resume (RED) resume_and_clear ok, both tops GeoscapeState.  drop_in_heal-common (GUARD) host + rejoiner alive, no new crash file.
RED cells fail on a build without the saveID fix: heal-copied, drop_in_heal-copied, drop_in_heal-key, drop_in_heal-rejoin, drop_in_heal-world, drop_in_heal-resume (6 of 14);
every other cell passes there too.
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
heal = ("heal-pre", "heal-copied", "heal-healed", "heal-rejoin", "heal-world", "heal-resume", "heal-common")
drop_in_heal = ("drop_in_heal-pre", "drop_in_heal-copied", "drop_in_heal-key", "drop_in_heal-rejoin", "drop_in_heal-world", "drop_in_heal-resume", "drop_in_heal-common")
RED = ("heal-copied", "drop_in_heal-copied", "drop_in_heal-key", "drop_in_heal-rejoin", "drop_in_heal-world", "drop_in_heal-resume")


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
    rj, rc = RH.rejoin_resume(r, host, c2, "rejoin")
    RH.tail(r, host, c2, rj, rc, r.gifted)


def row_heal(r):
    host, client = RH.start(r)
    x = crossing_notice(r, host, client)
    r.cell("heal-pre", True, x["lab"] + "; NOTICE ok")
    n3 = len(F.logl(host))
    s3 = F.quick_save(host, F.QUICK, RH.SAVE_S)
    r.id3 = s3.get("saveIDAfter")
    h = CH.world_copy_since(host, n3)
    r.ev["heal_save"] = dict(RH.pick(s3, ("ok", "seen54", "written", "t", "saveIDBefore", "saveIDAfter", "log")), world_copy=h)
    r.cell("heal-copied", bool(h and h[0] >= 1 and h[1:] == (r.id2, r.id3)), "heal_save's world copy %s (id2 %s, id3 %s)" % (h, r.id2, r.id3))
    time.sleep(RH.HOLD)
    ii, k3 = RH.ids(host, client), RH.kk(host, r.id3, r.name)
    r.ev["after_heal"] = {"ids": ii, "kk3": k3}
    r.cell("heal-healed", s3["ok"] and r.id3 != r.id2 and ii["host"] == [r.id3, r.id3] and ii["client"] == [r.id3, r.id3]
           and k3.get("present") is True, "heal_save %s (54 %s, written %s); after_heal %s (id3 %s); host_<id3> %s" % (
               s3["ok"], s3["seen54"], s3["written"], ii, r.id3, k3.get("present")))
    r.need(s3["ok"], "heal_save")
    RH.kill(r, client, host, "KILL")
    rejoin_tail(r, host)


def row_drop_in_heal(r):
    host, client = RH.start(r)
    x = crossing_notice(r, host, client)

    def probe(h):
        i3 = F.sid(h)
        return {"saveID": i3, "id3": RH.kk(h, i3, r.name), "id2": RH.kk(h, r.id2, r.name), "id1": RH.kk(h, r.id1, r.name)}
    d3 = F.drop_at_54(host, client, "quick", 0, probe, RH.SEEN_S, RH.DROP_S)
    r.ev["heal_drop"] = RH.pick(d3, ("ok", "why", "seen54", "suspend", "probe", "kill", "log"))
    p = d3.get("probe") or {}
    r.id3 = p.get("saveID")
    p3, p2 = p.get("id3") or {}, p.get("id2") or {}
    noans = p3.get("present") is not True or p3.get("fnv1a64") == p2.get("fnv1a64")
    ok = bool(d3.get("ok") and r.id3 != r.id2 and noans)
    r.cell("drop_in_heal-pre", ok, "%s; NOTICE ok; heal_drop %s (%s; id3 %s; at the 54 no answer stored %s)" % (
        x["lab"], d3.get("ok"), d3.get("why") or "54 seen, 62 after the kill", r.id3, noans))
    r.need(ok, "heal_drop")
    h = CH.world_copy_since(host, d3["n0"])
    r.cell("drop_in_heal-copied", bool(h and h[0] >= 1 and h[1:] == (r.id2, r.id3)), "heal_drop's world copy %s (id2 %s, id3 %s)" % (h, r.id2, r.id3))
    r.cell("drop_in_heal-key", p3.get("present") is True, "at heal_drop's 54: host_<id3> %s; host_<id2> %s; host_<id1> %s" % (
        p3.get("present"), p2.get("present"), (p.get("id1") or {}).get("present")))
    rejoin_tail(r, host)


def main():
    return RH.run("upload save crossing heal", (("heal", heal, row_heal, "upload_heal", KEY), ("drop_in_heal", drop_in_heal, row_drop_in_heal, "upload_heal_drop", KEY)), RED)


if __name__ == "__main__":
    sys.exit(main())
