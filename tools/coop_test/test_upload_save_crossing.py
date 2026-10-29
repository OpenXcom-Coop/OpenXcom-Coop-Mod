"""A partner upload that crosses a host quick save keeps the host's saveID, so a later drop + rejoin restores the partner's own
campaign. Helpers: crossing_helpers.py (CH: the crossing on the test-only hooks hold_blob_ack scope "upload" and hold_save_reply);
rejoin_helpers.py (RH) and drop_fixture.py (F).
id0 = the campaign's first saveID; id1 = first_save's; id2 = the crossing save's re-mint (crossing_save). Each row boots its own pair on lobby key 49643
(SEPARATE new_campaign); NAME = the host's get_coop.clientName; MARKER = the client's own bases and soldiers; the gift is the host's real
presses (RH gift) and the crossing stream is the partner's unasked push after it; every rejoiner is a NEW client on a fresh dir joining by
NAME (never a base placement: a fresh world is evidence); RESUME only after the host's ack.
  Row crossed: CROSSING (CH: first_save; arm_ack_hold; GIFT; PUSH; HELD; arm_reply_hold; crossing_save; REPLY + read idsRead; release_ack_hold; save_done; read after_save; release_reply_hold;
          store_done; read after_store); KILL; REJOIN; read rejoined.
          crossed-pre (GUARD) every CROSSING step met.  crossed-host (FIX) after_save: the host's saveID (both probes) == id2.
          crossed-log (FIX) after_save: >= 1 "[coop] partner upload validated" line on the host since crossing_save.
          crossed-sav (FIX) the QUICK .sav: saveID == id2 and exactly one entry, key host_<id2>_<NAME>.data.
          crossed-key (FIX) host_<the host's saveID> present at after_save and at after_store.
          crossed-ids (GUARD) after_store: the host's saveID == the partner's == id2.
          crossed-rejoin (FIX) no BuildNewBaseState, the rejoiner's 68 within JOIN_S, the host's ack within ACK_S.
          crossed-world (FIX) read rejoined: the rejoiner's own bases == MARKER's and its soldiers hold the gifted one.
          crossed-resume (FIX) resume_and_clear ok, both tops GeoscapeState.  crossed-common (GUARD) host + rejoiner alive, no new crash file.
  Row control (the control: no hold): first_save; gift_push (RH gift_push: the push lands, no hook armed); NOTICE; after_stream_save = a quick save after the
          stream; HOLD; after_stream; KILL; REJOIN; read rejoined.
          control-pre (GUARD) first_save, gift_push (push key client_<id1>_<NAME>.data, the host's fnv change), NOTICE.
          control-save (GUARD) after_stream_save ok, id2 != id1, world copy "1 ... from id1 to id2".  control-ids (GUARD) after_stream: host == partner == id2, host_<id2>.
          control-log (GUARD) 0 "[coop] partner upload validated" lines on the host since first_save.  control-sav (GUARD) as crossed-sav.
          control-rejoin, control-world, control-resume, control-common (GUARD) as crossed's.
FIX cells fail on a build without the saveID fix: crossed-host, crossed-log, crossed-sav, crossed-key, crossed-rejoin, crossed-world, crossed-resume (7 of 19);
every other cell passes there too.
One EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; a precondition miss ends its row (later cells "not reached",
one CAPTURE line); every row runs after a failure. ONE foreground run, no SKIP; exit 0 only when every cell
passes, else 2. Run: python tools/coop_test/test_upload_save_crossing.py   (OXC_HARNESS_SLOT selects the lane)"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drop_fixture as F  # noqa: E402
import rejoin_helpers as RH  # noqa: E402
import crossing_helpers as CH  # noqa: E402

KEY = "49643"
crossed = ("crossed-pre", "crossed-host", "crossed-log", "crossed-sav", "crossed-key", "crossed-ids", "crossed-rejoin", "crossed-world", "crossed-resume", "crossed-common")
control = ("control-pre", "control-save", "control-ids", "control-log", "control-sav", "control-rejoin", "control-world", "control-resume", "control-common")
FIX = ("crossed-host", "crossed-log", "crossed-sav", "crossed-key", "crossed-rejoin", "crossed-world", "crossed-resume")


def sav_ok(sav, i, name):
    en = sav.get("entries") or []
    return (sav.get("saveID") == i and len(en) == 1 and en[0]["key"] == "host_%s_%s.data" % (i, name),
            "SAV saveID %s; entries %s" % (sav.get("saveID"), [[e["key"], e["blobSaveID"]] for e in en]))


def tail(r, host, client):
    """KILL; REJOIN (a NEW <tag>_client2 by NAME); read rejoined"""
    RH.kill(r, client, host, "KILL")
    c2 = r.add(RH.rejoiner(r.tag, 2))
    rj, rc = RH.rejoin_resume(r, host, c2, "rejoin")
    RH.tail(r, host, c2, rj, rc, r.gifted)


def row_crossed(r):
    host, client = RH.start(r)
    x = CH.crossing(r, host, client)
    r.cell("crossed-pre", True, x["lab"])
    id1, id2, x1, x2 = r.id1, r.id2, x["after_save"], x["after_store"]
    h1, h2 = x1["ids"]["host"], x2["ids"]["host"]
    r.cell("crossed-host", h1 == [id2, id2], "after_save host saveID %s (id1 %s, id2 %s)" % (h1, id1, id2))
    r.cell("crossed-log", x1["keptCount"] >= 1, "after_save keptCount(host) since crossing_save %d" % x1["keptCount"])
    ok, lab = sav_ok(x1["sav"], id2, r.name)
    r.cell("crossed-sav", ok, "%s (id1 %s, id2 %s)" % (lab, id1, id2))
    k1, k2 = x1["blobs"].get(str(h1[0])) or {}, x2["blobs"].get(str(h2[0])) or {}
    r.cell("crossed-key", k1.get("present") is True and k2.get("present") is True,
           "after_save host_<%s> %s; after_store host_<%s> %s" % (h1[0], k1.get("present"), h2[0], k2.get("present")))
    r.cell("crossed-ids", h2 == [id2, id2] and x2["ids"]["client"] == [id2, id2], "after_store %s (id2 %s)" % (x2["ids"], id2))
    tail(r, host, client)


def row_control(r):
    host, client = RH.start(r)
    n1 = len(F.logl(host))
    s1 = F.quick_save(host, F.QUICK, RH.SAVE_S)
    r.id0, r.id1 = r.ev["marker"]["id0"], s1.get("saveIDAfter")
    r.ev["first_save"] = RH.pick(s1, ("ok", "seen54", "written", "t", "saveIDBefore", "saveIDAfter", "log"))
    time.sleep(RH.HOLD)
    gp = RH.gift_push(r, host, client, "GIFT")
    r.gifted = gp["gifted"]
    r.ev["NOTICE"] = nt = RH.partner_notice_ok(client)
    ok = bool(s1["ok"] and r.id1 != r.id0 and gp["ok"] and gp["pushKey"] == "client_%s_%s.data" % (r.id1, r.name) and nt.get("ok"))
    r.cell("control-pre", ok, "first_save %s (id0 %s, id1 %s); %s; NOTICE %s" % (s1["ok"], r.id0, r.id1, gp["lab"], nt.get("ok")))
    r.need(ok, "first_save / gift_push / NOTICE")
    n2 = len(F.logl(host))
    s2 = F.quick_save(host, F.QUICK, RH.SAVE_S)
    r.id2 = s2.get("saveIDAfter")
    h = CH.world_copy_since(host, n2)
    r.ev["after_stream_save"] = dict(RH.pick(s2, ("ok", "seen54", "written", "t", "saveIDBefore", "saveIDAfter", "log")), world_copy=h)
    r.cell("control-save", s2["ok"] and r.id2 != r.id1 and h == (1, r.id1, r.id2), "after_stream_save %s (54 %s, written %s); id1 %s, id2 %s; world copy %s" % (
        s2["ok"], s2["seen54"], s2["written"], r.id1, r.id2, h))
    r.need(s2["ok"], "after_stream_save")
    time.sleep(RH.HOLD)
    after_stream = CH.x_read(r, host, client)
    after_stream.update(keptCount=CH.kept_id_count(host, n1), sav=RH.parse_sav(os.path.join(host.user_dir, "xcom1", F.QUICK)))
    r.ev["after_stream"] = after_stream
    k2 = after_stream["blobs"].get(str(r.id2)) or {}
    r.cell("control-ids", after_stream["ids"]["host"] == [r.id2, r.id2] and after_stream["ids"]["client"] == [r.id2, r.id2] and k2.get("present") is True,
           "after_stream %s; host_<id2> %s (id2 %s)" % (after_stream["ids"], k2.get("present"), r.id2))
    r.cell("control-log", after_stream["keptCount"] == 0, "keptCount(host) since first_save %d" % after_stream["keptCount"])
    ok, lab = sav_ok(after_stream["sav"], r.id2, r.name)
    r.cell("control-sav", ok, "%s (id2 %s)" % (lab, r.id2))
    tail(r, host, client)


def main():
    return RH.run("upload save crossing", (("crossed", crossed, row_crossed, "upload_crossing", KEY), ("control", control, row_control, "upload_plain", KEY)), FIX)


if __name__ == "__main__":
    sys.exit(main())
