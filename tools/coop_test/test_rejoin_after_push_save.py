"""W2-H84 RAS (tools/coop_test/test_rejoin_after_push_save.py): a partner keeps the host's saveID through a drop during the host's NEXT
quick save after its upload (C2) and through a resume of the save the host wrote at its drop (X3), so its rejoin restores its own campaign
(lead L-H79-3, ruling R-LH79-3-1; VL-H84-2). Spec docs rewrite/prompts/w2h84_rejoin_join_id.md (f); TASK 0 values in
rewrite/w2h84-task0/sa/CONSTANTS.md; capture rewrite/lh79-3-cap. Helpers: rejoin_helpers.py (RH); fixture
drop_fixture.py (F) imported unchanged. id1 = S1's saveID; id2 = D1's re-mint (W2-H58 copies host_<id1> to host_<id2> with id1's
bytes; W2-H59 writes _quick_.asav at the drop); id3 = D2's re-mint. Lobby key 49499 (SEPARATE); NAME = the host's get_coop.clientName;
MARKER = the client's own bases and soldiers after BOOT; every rejoiner is a NEW client on a fresh dir joining by NAME (never a base
placement: a fresh world is evidence); RESUME only after the host's ack (resume_and_clear CANCELs a stale 54, F18431).
  Row C2 (capture "extra c2") BOOT; S1; D1; REJOIN(2) + RESUME; GIFT (the host's real presses) + PUSH (client2's unasked upload); D2 =
          client2 dropped at the host's first 54 of the next quick save (probe: id3, host_<id3>, host_<host id before D2>); REJOIN(3); read R.
          C2-pre (GUARD) S1, D1, REJOIN(2) ack + RESUME, GIFT + PUSH, D2 (54 seen, 62 after the kill).
          C2-copied (RED) the host's log since D2's trigger: "[coop] N partner world(s) copied from saveID A to id3" with N >= 1.
          C2-key (RED) at D2's 54: host_<id3> present.  C2-rejoin (RED) REJOIN(3): no BuildNewBaseState, 68 within JOIN_S, ack within ACK_S.
          C2-world (RED) read R: client3's own bases == MARKER's and its soldiers hold the gifted one.
          C2-resume (RED) resume_and_clear ok and both tops GeoscapeState.  C2-common (GUARD) host + client3 alive, no new crash file.
  Row X3 (capture X3, the resume route) BOOT; S1; D1; SAV = parse_sav of the host's QUICK (written at the drop); QUICK copied to the
          row's save dir; the host shut; BOOT2 = a NEW pair resumes the copy (session.resume_campaign: the client joins as NAME, the host's
          real RESUME); read M; GIFT (host2 -> the resumed client) + PUSH; read G; KILL; REJOIN(3) on host2; read R.
          X3-pre (GUARD) S1, D1, QUICK's mtime after D1's trigger, BOOT2 both GeoscapeState stable.
          X3-sav (GUARD) SAV saveID == id2; exactly one coopClientSaves entry, key host_<id2>_<NAME>.data, its blob saveID == id1 != id2.
          X3-ids (RED) read M: the resumed client's saveID == host2's == id2.  X3-log (RED) read M: its log holds >= 1 '[coop] own world "' line.
          X3-host (RED) read G: host2's saveID == id2 and the push line's key == client_<id2>_<NAME>.data.
          X3-rejoin, X3-world, X3-resume (RED) as C2's for client3 on host2.  X3-common (GUARD) host2 + client3 alive, no new crash file.
Red today (no W2-H84 fix): C2-copied, C2-key, C2-rejoin, C2-world, C2-resume, X3-ids, X3-log, X3-host, X3-rejoin, X3-world, X3-resume
FAIL (11 of 16); every other cell PASS. One EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; a precondition miss
ends its row (later cells "not reached", one CAPTURE line); every row runs after a failure. ONE foreground
run, no SKIP; exit 0 only when every cell passes, else 2.
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
C2 = ("C2-pre", "C2-copied", "C2-key", "C2-rejoin", "C2-world", "C2-resume", "C2-common")
X3 = ("X3-pre", "X3-sav", "X3-ids", "X3-log", "X3-host", "X3-rejoin", "X3-world", "X3-resume", "X3-common")
RED = ("C2-copied", "C2-key", "C2-rejoin", "C2-world", "C2-resume", "X3-ids", "X3-log", "X3-host", "X3-rejoin", "X3-world", "X3-resume")
H58 = re.compile(r"\[coop\] (\d+) partner world\(s\) copied from saveID (\d+) to (\d+)")


def row_c2(r):
    host, client = RH.start(r)
    ok, lab = RH.s1_d1(r, host, client)
    c2 = r.add(RH.rejoiner(r.tag, 2))
    rj, rc = RH.rejoin_resume(r, host, c2, "J2")
    ok = ok and rj["ack"] is not None and bool(rc and rc["ok"])
    lab += "; REJOIN(2) " + rj["lab"]
    if ok:
        r.ev["M"] = {"ids": RH.ids(host, c2), "kept": RH.kept(c2)}  # EVIDENCE only
        gp = RH.gift_push(r, host, c2, "GIFT")
        ok, lab = gp["ok"], lab + "; " + gp["lab"]
    if not ok:
        r.cell("C2-pre", False, lab)
        raise RH.Stop("S1 / D1 / REJOIN(2) + RESUME / GIFT + PUSH")
    r.ev["NOTICE"] = RH.partner_notice_ok(c2)
    hb = F.sid(host)

    def probe(h):
        i3 = F.sid(h)
        return {"saveID": i3, "id3": RH.kk(h, i3, r.name), "before": RH.kk(h, hb, r.name)}
    d2 = F.drop_at_54(host, c2, "quick", 0, probe, RH.SEEN_S, RH.DROP_S)
    r.ev["D2"] = RH.pick(d2, ("ok", "why", "seen54", "probe", "kill", "log"))
    r.cell("C2-pre", d2.get("ok"), "%s; D2 %s (%s)" % (lab, d2.get("ok"), d2.get("why") or "54 seen, 62 after the kill"))
    r.need(d2.get("ok"), "D2: %s" % d2.get("why"))
    p = d2["probe"]
    id3 = p["saveID"]
    h58 = [ln for ln in F.lines_since(host, d2["n0"], ("partner world(s) copied",)) if H58.search(ln)]
    good = [ln for ln in h58 if int(H58.search(ln).group(1)) >= 1 and int(H58.search(ln).group(3)) == id3]
    r.cell("C2-copied", bool(good), "host W2-H58 lines since D2's trigger %s (id3 %s; host id before D2 %s)" % (h58, id3, hb))
    r.cell("C2-key", p["id3"].get("present") is True, "at D2's 54: host_<id3> %s; host_<%s> %s" % (p["id3"], hb, p["before"]))
    c3 = r.add(RH.rejoiner(r.tag, 3))
    rj3, rc3 = RH.rejoin_resume(r, host, c3, "J3", RH.HOLD_R)
    RH.tail(r, host, c3, rj3, rc3, gp["gifted"])


def row_x3(r):
    host, client = RH.start(r)
    ok, lab = RH.s1_d1(r, host, client)
    qp = os.path.join(host.user_dir, "xcom1", F.QUICK)
    before = (r.ev["D1"].get("filesBefore") or {}).get(F.QUICK) or [0, 0]
    tw = RH.until(lambda: (F.files(host).get(F.QUICK) or [0, 0])[1] > before[1], time.time() + RH.SAVE_S, 0.1)
    r.ev["QUICK"] = {"before": before, "after": F.files(host).get(F.QUICK), "written": tw is not None}
    lab += "; QUICK written after D1's trigger %s" % (tw is not None)
    if not (ok and tw):
        r.cell("X3-pre", False, lab)
        raise RH.Stop("S1 / D1 / QUICK written at the drop")
    r.ev["SAV"] = sav = RH.parse_sav(qp)
    en = sav.get("entries") or []
    r.cell("X3-sav", sav.get("saveID") == r.id2 and len(en) == 1 and en[0]["key"] == "host_%s_%s.data" % (r.id2, r.name)
           and en[0]["blobSaveID"] == r.id1 and r.id1 != r.id2, "SAV saveID %s; entries %s (id1 %s, id2 %s)" % (sav.get("saveID"), en, r.id1, r.id2))
    dst_dir = os.path.join(harness.TEST_ROOT, "s%d_%s_save" % (harness.HARNESS_SLOT, r.tag))
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, F.QUICK)
    shutil.copyfile(qp, dst)
    r.ev["shut1"] = RH.shut([host])
    h2, cr = RH.start(r, "w2h84_x3r", saves=(dst,), names=("host2", "clientR"))
    r.cell("X3-pre", True, lab + "; BOOT2 %s" % r.ev["boot2"].get("stable"))
    time.sleep(RH.HOLD)
    ii, k = RH.ids(h2, cr), RH.kept(cr)
    r.ev["M"] = {"ids": ii, "kept": k, "own_world": F._pick(F.q(cr, {"cmd": "coop_file_info", "role": "own_world"}), ("key", "present", "fnv1a64"))}
    r.cell("X3-ids", ii["client"] == [r.id2, r.id2] and ii["host"] == [r.id2, r.id2], "read M %s (id1 %s, id2 %s)" % (ii, r.id1, r.id2))
    r.cell("X3-log", k >= 1, "read M kept(clientR) %d" % k)
    gp = RH.gift_push(r, h2, cr, "GIFT")
    r.need(gp["ok"], "GIFT / PUSH: " + gp["lab"])
    hid = [F.coop(h2).get("saveID"), F.sid(h2)]
    r.ev["G"] = {"host2": hid, "keys": {str(i): RH.kk(h2, i, r.name) for i in (r.id1, r.id2)}}
    r.cell("X3-host", hid == [r.id2, r.id2] and gp["pushKey"] == "client_%s_%s.data" % (r.id2, r.name),
           "read G host2 saveID %s; push key %s (id1 %s, id2 %s)" % (hid, gp["pushKey"], r.id1, r.id2))
    r.ev["NOTICE"] = RH.partner_notice_ok(cr)
    RH.kill(r, cr, h2, "KILL")
    c3 = r.add(RH.rejoiner("w2h84_x3r", 3))
    rj, rc = RH.rejoin_resume(r, h2, c3, "J3", RH.HOLD_R)
    RH.tail(r, h2, c3, rj, rc, gp["gifted"])


def main():
    return RH.run("W2-H84 RAS", (("C2", C2, row_c2, "w2h84_c2", KEY), ("X3", X3, row_x3, "w2h84_x3", KEY)), RED)


if __name__ == "__main__":
    sys.exit(main())
