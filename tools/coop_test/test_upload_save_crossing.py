"""W2-H86 UXC (tools/coop_test/test_upload_save_crossing.py): a partner upload that crosses a host quick save keeps the host's saveID,
so a later drop + rejoin restores the partner's own campaign (lead L-LT17-1, ruling R-LLT17-1-1; VL-H86-1). Spec docs
rewrite/prompts/w2h86_upload_save_crossing.md (f); TASK 0 values in rewrite/w2h86-task0/sa/CONSTANTS.md; capture rewrite/llt17-1-cap
(F22900-F22915). Helpers: crossing_helpers.py (CH: the crossing on the TEST-ONLY levers hold_blob_ack scope "upload" and
hold_save_reply); rejoin_helpers.py (RH) and drop_fixture.py (F) imported unchanged.
id0 = the campaign's first saveID; id1 = S1's; id2 = the crossing save's re-mint (S2). Each row boots its own pair on lobby key 49643
(SEPARATE new_campaign); NAME = the host's get_coop.clientName; MARKER = the client's own bases and soldiers; the gift is the host's real
presses (RH gift) and the crossing stream is the partner's unasked push after it; every rejoiner is a NEW client on a fresh dir joining by
NAME (never a base placement: a fresh world is evidence); RESUME only after the host's ack.
  Row U1  (capture R-LT17-U1) CROSSING (CH: S1; ARM-A; GIFT; PUSH; HELD; ARM-B; S2; REPLY + read P; REL-A; RESULT1; read X1; REL-B;
          RESULT2; read X2); KILL; REJOIN; read R.
          U1-pre (GUARD) every CROSSING step met.  U1-host (RED) read X1: the host's saveID (both probes) == id2.
          U1-log (RED) read X1: >= 1 "[coop] W2-H86:" line on the host since S2.
          U1-sav (RED) the QUICK .sav: saveID == id2 and exactly one entry, key host_<id2>_<NAME>.data.
          U1-key (RED) host_<the host's saveID> present at read X1 and at read X2.
          U1-ids (GUARD) read X2: the host's saveID == the partner's == id2.
          U1-rejoin (RED) no BuildNewBaseState, the rejoiner's 68 within JOIN_S, the host's ack within ACK_S.
          U1-world (RED) read R: the rejoiner's own bases == MARKER's and its soldiers hold the gifted one.
          U1-resume (RED) resume_and_clear ok, both tops GeoscapeState.  U1-common (GUARD) host + rejoiner alive, no new crash file.
  Row CTL (capture U1-ctl) S1; GP (RH gift_push: the push lands, no lever); NOTICE; S2c = a quick save after the stream; HOLD; read X;
          KILL; REJOIN; read R.
          CTL-pre (GUARD) S1, GP (push key client_<id1>_<NAME>.data, the host's fnv change), NOTICE.
          CTL-save (GUARD) S2c ok, id2 != id1, W2-H58 "1 ... from id1 to id2".  CTL-ids (GUARD) read X: host == partner == id2, host_<id2>.
          CTL-log (GUARD) 0 "[coop] W2-H86:" lines on the host since S1.  CTL-sav (GUARD) as U1-sav.
          CTL-rejoin, CTL-world, CTL-resume, CTL-common (GUARD) as U1's.
Red today (no W2-H86 fix): U1-host, U1-log, U1-sav, U1-key, U1-rejoin, U1-world, U1-resume FAIL (7 of 19); every other cell PASS.
One EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; a precondition miss ends its row (later cells "not reached",
one CAPTURE line); every row runs after a failure. WV-D95 / WV-D99 / WV-D100: ONE foreground run, no SKIP; exit 0 only when every cell
passes, else 2. Run: python tools/coop_test/test_upload_save_crossing.py   (OXC_HARNESS_SLOT selects the lane)"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drop_fixture as F  # noqa: E402
import rejoin_helpers as RH  # noqa: E402
import crossing_helpers as CH  # noqa: E402

KEY = "49643"
U1 = ("U1-pre", "U1-host", "U1-log", "U1-sav", "U1-key", "U1-ids", "U1-rejoin", "U1-world", "U1-resume", "U1-common")
CTL = ("CTL-pre", "CTL-save", "CTL-ids", "CTL-log", "CTL-sav", "CTL-rejoin", "CTL-world", "CTL-resume", "CTL-common")
RED = ("U1-host", "U1-log", "U1-sav", "U1-key", "U1-rejoin", "U1-world", "U1-resume")


def sav_ok(sav, i, name):
    en = sav.get("entries") or []
    return (sav.get("saveID") == i and len(en) == 1 and en[0]["key"] == "host_%s_%s.data" % (i, name),
            "SAV saveID %s; entries %s" % (sav.get("saveID"), [[e["key"], e["blobSaveID"]] for e in en]))


def tail(r, host, client):
    """KILL; REJOIN (a NEW <tag>_client2 by NAME); read R"""
    RH.kill(r, client, host, "KILL")
    c2 = r.add(RH.rejoiner(r.tag, 2))
    rj, rc = RH.rejoin_resume(r, host, c2, "J2")
    RH.tail(r, host, c2, rj, rc, r.gifted)


def row_u1(r):
    host, client = RH.start(r)
    x = CH.crossing(r, host, client)
    r.cell("U1-pre", True, x["lab"])
    id1, id2, x1, x2 = r.id1, r.id2, x["X1"], x["X2"]
    h1, h2 = x1["ids"]["host"], x2["ids"]["host"]
    r.cell("U1-host", h1 == [id2, id2], "read X1 host saveID %s (id1 %s, id2 %s)" % (h1, id1, id2))
    r.cell("U1-log", x1["h86"] >= 1, "read X1 h86(host) since S2 %d" % x1["h86"])
    ok, lab = sav_ok(x1["sav"], id2, r.name)
    r.cell("U1-sav", ok, "%s (id1 %s, id2 %s)" % (lab, id1, id2))
    k1, k2 = x1["blobs"].get(str(h1[0])) or {}, x2["blobs"].get(str(h2[0])) or {}
    r.cell("U1-key", k1.get("present") is True and k2.get("present") is True,
           "X1 host_<%s> %s; X2 host_<%s> %s" % (h1[0], k1.get("present"), h2[0], k2.get("present")))
    r.cell("U1-ids", h2 == [id2, id2] and x2["ids"]["client"] == [id2, id2], "read X2 %s (id2 %s)" % (x2["ids"], id2))
    tail(r, host, client)


def row_ctl(r):
    host, client = RH.start(r)
    n1 = len(F.logl(host))
    s1 = F.quick_save(host, F.QUICK, RH.SAVE_S)
    r.id0, r.id1 = r.ev["marker"]["id0"], s1.get("saveIDAfter")
    r.ev["S1"] = RH.pick(s1, ("ok", "seen54", "written", "t", "saveIDBefore", "saveIDAfter", "log"))
    time.sleep(RH.HOLD)
    gp = RH.gift_push(r, host, client, "GIFT")
    r.gifted = gp["gifted"]
    r.ev["NOTICE"] = nt = RH.partner_notice_ok(client)
    ok = bool(s1["ok"] and r.id1 != r.id0 and gp["ok"] and gp["pushKey"] == "client_%s_%s.data" % (r.id1, r.name) and nt.get("ok"))
    r.cell("CTL-pre", ok, "S1 %s (id0 %s, id1 %s); %s; NOTICE %s" % (s1["ok"], r.id0, r.id1, gp["lab"], nt.get("ok")))
    r.need(ok, "S1 / GP / NOTICE")
    n2 = len(F.logl(host))
    s2 = F.quick_save(host, F.QUICK, RH.SAVE_S)
    r.id2 = s2.get("saveIDAfter")
    h = CH.world_copy_since(host, n2)
    r.ev["S2c"] = dict(RH.pick(s2, ("ok", "seen54", "written", "t", "saveIDBefore", "saveIDAfter", "log")), w58=h)
    r.cell("CTL-save", s2["ok"] and r.id2 != r.id1 and h == (1, r.id1, r.id2), "S2c %s (54 %s, written %s); id1 %s, id2 %s; W2-H58 %s" % (
        s2["ok"], s2["seen54"], s2["written"], r.id1, r.id2, h))
    r.need(s2["ok"], "S2c")
    time.sleep(RH.HOLD)
    X = CH.x_read(r, host, client)
    X.update(h86=CH.kept_id_count(host, n1), sav=RH.parse_sav(os.path.join(host.user_dir, "xcom1", F.QUICK)))
    r.ev["X"] = X
    k2 = X["blobs"].get(str(r.id2)) or {}
    r.cell("CTL-ids", X["ids"]["host"] == [r.id2, r.id2] and X["ids"]["client"] == [r.id2, r.id2] and k2.get("present") is True,
           "read X %s; host_<id2> %s (id2 %s)" % (X["ids"], k2.get("present"), r.id2))
    r.cell("CTL-log", X["h86"] == 0, "h86(host) since S1 %d" % X["h86"])
    ok, lab = sav_ok(X["sav"], r.id2, r.name)
    r.cell("CTL-sav", ok, "%s (id2 %s)" % (lab, r.id2))
    tail(r, host, client)


def main():
    return RH.run("W2-H86 UXC", (("U1", U1, row_u1, "w2h86_u1", KEY), ("CTL", CTL, row_ctl, "w2h86_ctl", KEY)), RED)


if __name__ == "__main__":
    sys.exit(main())
