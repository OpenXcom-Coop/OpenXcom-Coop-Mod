"""A partner keeps the host's saveID through a drop during the host's NEXT quick save after its upload (drop_next_save) and through a
resume of the save the host wrote at its drop (resumed_save), so its rejoin restores its own campaign. Helpers: rejoin_helpers.py (RH);
fixture drop_fixture.py (F) imported unchanged. id1 = first_save's saveID; id2 = first_drop's re-mint (the host copies host_<id1> to
host_<id2> with id1's bytes and writes _quick_.asav at the drop); id3 = second_drop's re-mint. Lobby key 49499 (SEPARATE); NAME = the
host's get_coop.clientName; MARKER = the client's own bases and soldiers after BOOT; every rejoiner is a NEW client on a fresh dir joining
by NAME (never a base placement: a fresh world is evidence); RESUME only after the host's ack (resume_and_clear CANCELs a stale 54).
  Row drop_next_save: BOOT; first_save; first_drop; REJOIN(2) + RESUME; GIFT (the host's real presses) + PUSH (client2's unasked upload);
          second_drop = client2 dropped at the host's first 54 of the next quick save (probe: id3, host_<id3>, host_<host id before
          second_drop>); REJOIN(3); read rejoined.
          drop_next_save-pre (GUARD) first_save, first_drop, REJOIN(2) ack + RESUME, GIFT + PUSH, second_drop (54 seen, 62 after the kill).
          drop_next_save-copied (FIX) the host's log since second_drop's trigger: "[coop] N partner world(s) copied from saveID A to id3"
          with N >= 1.
          drop_next_save-key (FIX) at second_drop's 54: host_<id3> present.
          drop_next_save-rejoin (FIX) REJOIN(3): no BuildNewBaseState, 68 within JOIN_S, ack within ACK_S.
          drop_next_save-world (FIX) read rejoined: client3's own bases == MARKER's and its soldiers hold the gifted one.
          drop_next_save-resume (FIX) resume_and_clear ok and both tops GeoscapeState.
          drop_next_save-common (GUARD) host + client3 alive, no new crash file.
  Row resumed_save (the resume route): BOOT; first_save; first_drop; SAV = parse_sav of the host's QUICK (written at the drop); QUICK
          copied to the row's save dir; the host shut; BOOT2 = a NEW pair resumes the copy (session.resume_campaign: the client joins as
          NAME, the host's real RESUME); read joined; GIFT (host2 -> the resumed client) + PUSH; read after_gift; KILL; REJOIN(3) on host2;
          read rejoined.
          resumed_save-pre (GUARD) first_save, first_drop, QUICK's mtime after first_drop's trigger, BOOT2 both GeoscapeState stable.
          resumed_save-sav (GUARD) SAV saveID == id2; exactly one coopClientSaves entry, key host_<id2>_<NAME>.data, its blob saveID ==
          id1 != id2.
          resumed_save-ids (FIX) read joined: the resumed client's saveID == host2's == id2.
          resumed_save-log (FIX) read joined: its log holds >= 1 '[coop] own world "' line.
          resumed_save-host (FIX) read after_gift: host2's saveID == id2 and the push line's key == client_<id2>_<NAME>.data.
          resumed_save-rejoin, resumed_save-world, resumed_save-resume (FIX) as drop_next_save's for client3 on host2.
          resumed_save-common (GUARD) host2 + client3 alive, no new crash file.
FIX cells fail on a build without the saveID fix: drop_next_save-copied, drop_next_save-key, drop_next_save-rejoin,
drop_next_save-world, drop_next_save-resume, resumed_save-ids, resumed_save-log, resumed_save-host, resumed_save-rejoin,
resumed_save-world, resumed_save-resume (11 of 16); every other cell passes there too. One EVIDENCE line per row, one PASS / FAIL line
per cell, the row verdict; a precondition miss ends its row (later cells "not reached", one CAPTURE line); every row runs after a
failure. ONE foreground run, no SKIP; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_rejoin_after_push_save.py   (OXC_HARNESS_SLOT selects the lane)"""
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import drop_fixture as F  # noqa: E402
import rejoin_helpers as RH  # noqa: E402

KEY = "49499"
DROP_NEXT_SAVE = ("drop_next_save-pre", "drop_next_save-copied", "drop_next_save-key", "drop_next_save-rejoin", "drop_next_save-world", "drop_next_save-resume", "drop_next_save-common")
RESUMED_SAVE = ("resumed_save-pre", "resumed_save-sav", "resumed_save-ids", "resumed_save-log", "resumed_save-host", "resumed_save-rejoin", "resumed_save-world", "resumed_save-resume", "resumed_save-common")
FIX = ("drop_next_save-copied", "drop_next_save-key", "drop_next_save-rejoin", "drop_next_save-world", "drop_next_save-resume", "resumed_save-ids", "resumed_save-log", "resumed_save-host", "resumed_save-rejoin", "resumed_save-world", "resumed_save-resume")
COPIED_RX = re.compile(r"\[coop\] (\d+) partner world\(s\) copied from saveID (\d+) to (\d+)")


def row_drop_next_save(r):
    host, client = RH.start(r)
    ok, lab = RH.save_then_drop(r, host, client)
    c2 = r.add(RH.rejoiner(r.tag, 2))
    rj, rc = RH.rejoin_resume(r, host, c2, "client2_join")
    ok = ok and rj["ack"] is not None and bool(rc and rc["ok"])
    lab += "; REJOIN(2) " + rj["lab"]
    if ok:
        r.ev["joined"] = {"ids": RH.ids(host, c2), "kept": RH.kept(c2)}  # EVIDENCE only
        gp = RH.gift_push(r, host, c2, "GIFT")
        ok, lab = gp["ok"], lab + "; " + gp["lab"]
    if not ok:
        r.cell("drop_next_save-pre", False, lab)
        raise RH.Stop("first_save / first_drop / REJOIN(2) + RESUME / GIFT + PUSH")
    r.ev["NOTICE"] = RH.partner_notice_ok(c2)
    hb = F.sid(host)

    def probe(h):
        i3 = F.sid(h)
        return {"saveID": i3, "id3": RH.kk(h, i3, r.name), "before": RH.kk(h, hb, r.name)}
    d2 = F.drop_at_54(host, c2, "quick", 0, probe, RH.SEEN_S, RH.DROP_S)
    r.ev["second_drop"] = RH.pick(d2, ("ok", "why", "seen54", "probe", "kill", "log"))
    r.cell("drop_next_save-pre", d2.get("ok"), "%s; second_drop %s (%s)" % (lab, d2.get("ok"), d2.get("why") or "54 seen, 62 after the kill"))
    r.need(d2.get("ok"), "second_drop: %s" % d2.get("why"))
    p = d2["probe"]
    id3 = p["saveID"]
    copied = [ln for ln in F.lines_since(host, d2["n0"], ("partner world(s) copied",)) if COPIED_RX.search(ln)]
    good = [ln for ln in copied if int(COPIED_RX.search(ln).group(1)) >= 1 and int(COPIED_RX.search(ln).group(3)) == id3]
    r.cell("drop_next_save-copied", bool(good), "host world-copy lines since second_drop's trigger %s (id3 %s; host id before second_drop %s)" % (copied, id3, hb))
    r.cell("drop_next_save-key", p["id3"].get("present") is True, "at second_drop's 54: host_<id3> %s; host_<%s> %s" % (p["id3"], hb, p["before"]))
    c3 = r.add(RH.rejoiner(r.tag, 3))
    rj3, rc3 = RH.rejoin_resume(r, host, c3, "client3_join", RH.HOLD_R)
    RH.tail(r, host, c3, rj3, rc3, gp["gifted"])


def row_resumed_save(r):
    host, client = RH.start(r)
    ok, lab = RH.save_then_drop(r, host, client)
    qp = os.path.join(host.user_dir, "xcom1", F.QUICK)
    before = (r.ev["first_drop"].get("filesBefore") or {}).get(F.QUICK) or [0, 0]
    tw = RH.until(lambda: (F.files(host).get(F.QUICK) or [0, 0])[1] > before[1], time.time() + RH.SAVE_S, 0.1)
    r.ev["QUICK"] = {"before": before, "after": F.files(host).get(F.QUICK), "written": tw is not None}
    lab += "; QUICK written after first_drop's trigger %s" % (tw is not None)
    if not (ok and tw):
        r.cell("resumed_save-pre", False, lab)
        raise RH.Stop("first_save / first_drop / QUICK written at the drop")
    r.ev["SAV"] = sav = RH.parse_sav(qp)
    en = sav.get("entries") or []
    r.cell("resumed_save-sav", sav.get("saveID") == r.id2 and len(en) == 1 and en[0]["key"] == "host_%s_%s.data" % (r.id2, r.name)
           and en[0]["blobSaveID"] == r.id1 and r.id1 != r.id2, "SAV saveID %s; entries %s (id1 %s, id2 %s)" % (sav.get("saveID"), en, r.id1, r.id2))
    dst_dir = os.path.join(harness.TEST_ROOT, "s%d_%s_save" % (harness.HARNESS_SLOT, r.tag))
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, F.QUICK)
    shutil.copyfile(qp, dst)
    r.ev["shut1"] = RH.shut([host])
    h2, cr = RH.start(r, "rejoin_resumed_pair", saves=(dst,), names=("host2", "clientR"))
    r.cell("resumed_save-pre", True, lab + "; BOOT2 %s" % r.ev["boot2"].get("stable"))
    time.sleep(RH.HOLD)
    ii, k = RH.ids(h2, cr), RH.kept(cr)
    r.ev["joined"] = {"ids": ii, "kept": k, "own_world": F._pick(F.q(cr, {"cmd": "coop_file_info", "role": "own_world"}), ("key", "present", "fnv1a64"))}
    r.cell("resumed_save-ids", ii["client"] == [r.id2, r.id2] and ii["host"] == [r.id2, r.id2], "read joined %s (id1 %s, id2 %s)" % (ii, r.id1, r.id2))
    r.cell("resumed_save-log", k >= 1, "read joined kept(clientR) %d" % k)
    gp = RH.gift_push(r, h2, cr, "GIFT")
    r.need(gp["ok"], "GIFT / PUSH: " + gp["lab"])
    hid = [F.coop(h2).get("saveID"), F.sid(h2)]
    r.ev["after_gift"] = {"host2": hid, "keys": {str(i): RH.kk(h2, i, r.name) for i in (r.id1, r.id2)}}
    r.cell("resumed_save-host", hid == [r.id2, r.id2] and gp["pushKey"] == "client_%s_%s.data" % (r.id2, r.name),
           "read after_gift host2 saveID %s; push key %s (id1 %s, id2 %s)" % (hid, gp["pushKey"], r.id1, r.id2))
    r.ev["NOTICE"] = RH.partner_notice_ok(cr)
    RH.kill(r, cr, h2, "KILL")
    c3 = r.add(RH.rejoiner("rejoin_resumed_pair", 3))
    rj, rc = RH.rejoin_resume(r, h2, c3, "client3_join", RH.HOLD_R)
    RH.tail(r, h2, c3, rj, rc, gp["gifted"])


def main():
    return RH.run("rejoin after push save", (("drop_next_save", DROP_NEXT_SAVE, row_drop_next_save, "rejoin_next_save", KEY), ("resumed_save", RESUMED_SAVE, row_resumed_save, "rejoin_resumed", KEY)), FIX)


if __name__ == "__main__":
    sys.exit(main())
