"""test_desync_notice.py: after an automatic desync repair BOTH machines have written a report zip and both players see
the desync notice ("CO-OP DESYNC REPAIRED ...", OK / OPEN FOLDER / REPORT ON GITHUB) naming each machine's own report;
a held repair writes both reports and raises no notice. One boot (key "48755", dirs desync_notice_host / _client):
test_delta_core's boot (raw.bring_up_lobby, drive_to_battlescape with set_seed SEED_MAP, MAP_FP, pin_ai_neutral, HASH),
the pins asserted (a miss = setup failure: ONE CAPTURE line, every row FAILs "boot"). Rows in order (held_repair last:
the battle halts):
  repair_notice (saveBlob) the client pokes H2's reactions (+7, client-only), the host's real-UI kneel of H (its
     bt_action_end); wait <= 45 s for host RS released +1 and client RS loaded +1, <= 10 s for the notice on top of
     both; desync_dialog read BEFORE any dismissal. repair_notice-1 FIX client: live, headline "saveBlob diverged at
     action <seq>: bt_action_end" (<seq> the DESYNC line's; a bt_action_end desync names its kind `bt_action_end`
     rather than "?"), message "CO-OP DESYNC REPAIRED..." holding its zip, zipPath == RS bundle (written in this row
     in its own desync-reports), OPEN FOLDER target, GitHub URL, the three buttons. repair_notice-2 FIX the host, its
     own zip. repair_notice-3 FIX raiseCount +1, RS notices +1 on each. repair_notice-4 FIX OK (click_widget once OK
     is shown) closes each; a client walk of G to G_DEST applies; HASH.
  repair_reports (repair_notice's reports) repair_reports-host_zip FIX the host's zip: role host, bucket / seq / kind
     == the client zip's (kind bt_action_end), peerBundlePath, its log, saveBlob-host.yaml. repair_reports-client_zip
     GUARD the client's zip (saveBlob, log, saveBlob-client.yaml) and the host's seq text.
     repair_reports-action_end_kind FIX the client zip's kind and both RS last.kind == bt_action_end.
  unit_stats_repair (unitsStats) tu_both(KNEELER), client corrupt_bucket (U), the host's kneel of KNEELER; waits as
     repair_notice. unit_stats_repair-client_zip FIX the client's zip holds saveBlob-client.yaml, bucket unitsStats,
     role client. unit_stats_repair-notice_again FIX a notice on each again (raiseCount / notices +1); OK on each.
  held_repair (held) host resync_hold on; repair_notice's poke + kneel; wait <= 30 s for desyncs +1 on both.
     held_repair-halt GUARD the halt (client frozen, host held +1, the banner). held_repair-both_reports FIX both
     machines gained one zip, the host's role host. held_repair-no_notice GUARD no notice within 10 s.
  no_crash GUARD no new crash_*.log in this lane's crash folder over the whole run (read after the shutdown).
Definitions: POLL 0.25 s; RS(gc) = resync_state.resync, counters as deltas from the row's baseline; HASH =
wait_host_idle + assert_hash_clean(full); unit_stats_repair / held_repair start with NOTICE_OK on both (a no-op when no
notice is up) and LIVE (client RS frozen false, both tops BattlescapeState), else "not reached"; battle_state only with
a BattlescapeState on top; a WAIT that times out ends the row. EVIDENCE per row (the host's stack and 62 title at each
repair poll, the walls, both RS, the client's DESYNC line, CPU); a failed row prints ONE CAPTURE line. ONE run in the
foreground, no skip path; exit 0 iff every cell passes, else 2.
A build without the notice and the host report, whose bt_action_end desync records kind "?", fails
repair_notice-1..repair_notice-4, repair_reports-host_zip, repair_reports-action_end_kind, unit_stats_repair-client_zip,
unit_stats_repair-notice_again and held_repair-both_reports; repair_reports-client_zip, held_repair-halt,
held_repair-no_notice and no_crash pass on it.
"""
import ctypes
import glob
import json
import os
import re
import sys
import time
import zipfile
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import repro_atom_walk as raw  # noqa: E402
import test_delta_core as dc  # noqa: E402
import test_hash_coverage as hcv  # noqa: E402

KEY, TAG = "48755", "desync_notice"
SEED_MAP, MAP_FP = 1, -4.48310638993e+18   # test_delta_core's map
H, H2, G = 10, 11, 8                       # the soldier the host kneels, the one the client pokes, the first seat-1 soldier
G_TILE, G_DEST = (14, 19, 1), (14, 17, 0)  # G's start tile; the walk's measured end tile
U, KNEELER = 8, 10                         # corrupt_bucket's unit (the first live unit) and the kneeler that
                                           # does not restate it
KIND_END, SEQ_OFFSET = "bt_action_end", 2  # a bt_action_end desync's kind (older builds record "?"); the desync
                                           # seq = s0 + 2 (measured: s0 7 -> seq 9)
UNIT_STATS_BUCKET, POKE = "unitsStats", 7
POLL, W_REPAIR, W_NOTICE, W_HELD, W_WALK, W_IDLE = 0.25, 45.0, 10.0, 30.0, 30.0, 30.0
BS, NOTICE = "BattlescapeState", "CoopDesyncNoticeState"
REPAIRED_TEXT = "CO-OP DESYNC REPAIRED"      # the notice message's first words
HALTED = "Desync detected - battle halted"   # the client's halt banner
ISSUE_URL = "https://github.com/OpenXcom-Coop/OpenXcom-Coop-Mod/issues/new?title="
BUTTONS = ["OK", "OPEN FOLDER", "REPORT ON GITHUB"]
LOG_TAGS = ("[coop-resync]", "[coop-handshake]", "[coop-hash]", "[coop-pump]", "coop-session")


class Stop(Exception):
    """a WAIT timed out, the battle is not LIVE, or a construction step missed: the row ends here"""


def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]


def js(v):
    return json.dumps(v, sort_keys=True, default=str)


def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead or gone machine is a value
        return {"error": short(e, 200)}


def stack(gc):
    return [s.replace("class OpenXcom::", "") for s in q(gc, {"cmd": "get_state"}).get("states", [])]


def top(gc):
    return (stack(gc) or [None])[-1]


def rs(gc):
    r = q(gc, {"cmd": "resync_state"})
    return r.get("resync") or {} if r.get("ok") else {"error": r.get("error") or "resync_state not ok"}


def delta(a, b, k):
    return (b or {}).get(k, 0) - (a or {}).get(k, 0)


def es(gc):
    r = q(gc, {"cmd": "event_state"})
    return {k: r.get(k) for k in ("desyncSeen", "phase", "battleId", "lastSeqEmitted", "lastSeqApplied", "queueDepth", "busyOwnerSeat")}


def bs(gc):
    """battle_state, only with a BattlescapeState on top; {} otherwise"""
    return q(gc, {"cmd": "battle_state"}) if top(gc) == BS else {}


def units(gc):
    return session.units_by_id(bs(gc))


def dlg(gc):
    r = q(gc, {"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("present", "code", "title", "backVisible", "error")}


def dd(gc):  # desync_dialog: the notice on top (live) and the statics of the last one raised
    return q(gc, {"cmd": "desync_dialog"})


def raises(d):
    return (d.get("last") or {}).get("raiseCount")


def dd_short(d):
    out = {k: d.get(k) for k in ("ok", "error", "live", "headline", "message", "zipPath", "openFolderTarget", "buttons")}
    out["reportUrl"], out["last.raiseCount"] = (d.get("reportUrl") or "")[:140] or None, raises(d)
    return out


def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def desync_line(gc, n0):
    """the first `[coop-hash] DESYNC:` line since n0 as {bucket, seq, kind}"""
    m = next((m for m in (dc.DESYNC_RE.search(ln) for ln in log(gc)[n0:]) if m), None)
    return {"bucket": m.group(1), "seq": int(m.group(2)), "kind": m.group(3)} if m else None


def npath(p):
    return os.path.normcase(os.path.normpath(p)) if p else p


def listing(gc):
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(gc.user_dir, "desync-reports", "*")))


def new_zips(gc, before):
    """the zips this machine's desync-reports gained since `before` (oldest first), each opened: {path, members, info}"""
    out = []
    for n in [n for n in listing(gc) if n not in before and n.endswith(".zip")]:
        z = {"path": os.path.join(gc.user_dir, "desync-reports", n)}
        try:
            with zipfile.ZipFile(z["path"]) as zf:
                z["members"] = {i.filename: i.file_size for i in zf.infolist()}
                if "desync-info.json" in z["members"]:
                    z["info"] = json.loads(zf.read("desync-info.json").decode("utf-8", errors="replace"))
        except Exception as e:
            z["error"] = short(e, 200)
        out.append(z)
    return out


def cpu_now():
    from ctypes import wintypes
    ft = [wintypes.FILETIME() for _ in range(3)]
    ctypes.windll.kernel32.GetSystemTimes(*[ctypes.byref(f) for f in ft])
    return [(f.dwHighDateTime << 32) | f.dwLowDateTime for f in ft]


def cpu_pct(a, b):
    idle, total = b[0] - a[0], (b[1] - a[1]) + (b[2] - a[2])
    return round(100.0 * (total - idle) / total, 1) if total > 0 else None


def wait(desc, pred, timeout, interval=POLL):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return round(time.time() - t0, 2)
        time.sleep(interval)
    raise Stop("WAIT %s: timed out after %.0f s" % (desc, timeout))


def hash_ok(h, c, what):
    """HASH(host, client) -> (ok, evidence)"""
    try:
        session.wait_host_idle(h, c, timeout=W_IDLE)
        return True, {"equal buckets": len(session.assert_hash_clean(h, c, full=True, what=what)[0])}
    except Exception as e:
        return False, {"error": short(e, 700)}


def staged_live(x):
    """unit_stats_repair / held_repair's start: NOTICE_OK on both (client first), then LIVE; Stop when not LIVE"""
    ev = {"NOTICE_OK": {}}
    for gc in (x.client, x.host):
        if top(gc) == NOTICE:
            ev["NOTICE_OK"][gc.name] = {"dismiss": q(gc, {"cmd": "dismiss_popup"})}
            try:
                ev["NOTICE_OK"][gc.name]["bs s"] = wait("%s top BattlescapeState" % gc.name, lambda: top(gc) == BS, W_NOTICE)
            except Stop as e:
                ev["NOTICE_OK"][gc.name]["wait"] = str(e)
    ev["client frozen"], ev["tops"] = rs(x.client).get("frozen"), [top(x.host), top(x.client)]
    print("EVIDENCE staging: %s" % js(ev), flush=True)
    if not (ev["client frozen"] is False and ev["tops"] == [BS, BS]):
        raise Stop("not reached: the battle is not LIVE at the row's start (%s)" % js(ev))


def kneel(x, uid):
    """the host's real-UI kneel of uid (TAB-select + SDLK_K), then a reset-safe wait (flipped on both, the host
    idle) -> (s0, evidence)"""
    h, c, notes, t = x.host, x.client, [], time.time()
    if not hcv.tab_select(h, uid):
        return None, {"kneeled": [None, None], "s0": None, "kneel s": round(time.time() - t, 2), "notes": ["TAB never selected %s" % uid]}
    k0, s0 = units(h).get(uid, {}).get("kneeled"), es(h).get("lastSeqEmitted") or 0
    h.ok({"cmd": "inject_input", "kind": "key", "key": hcv.SDLK_K})
    # BattlescapeState counts as live under the notice
    bs_live = lambda st: st[-1:] == [BS] or st[-2:] == [BS, NOTICE]  # noqa: E731
    kn = lambda gc: (session.units_by_id(q(gc, {"cmd": "battle_state"})) if bs_live(stack(gc)) else {}).get(uid, {}).get("kneeled")  # noqa: E731
    try:
        wait("the kneel on both, the host idle", lambda: kn(h) not in (None, k0) and kn(c) == kn(h) and es(h).get("busyOwnerSeat") == -1, 20.0)
    except Stop as e:
        notes.append(str(e))
    return s0, {"kneeled": [k0, kn(h)], "s0": s0, "kneel s": round(time.time() - t, 2), "notes": notes}


def poke(x, uid):
    """the client-only `set_stat reactions` +POKE on uid -> evidence; Stop when the reply or the diff ['saveBlob'] misses (construction)"""
    h, c = x.host, x.client
    r0 = units(c).get(uid, {}).get("reactions")
    rset = q(c, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions", "value": (r0 or 0) + POKE})
    ev = {"set_stat": rset, "client reactions": [r0, units(c).get(uid, {}).get("reactions")],
          "host reactions": units(h).get(uid, {}).get("reactions"), "diff": dc.diff_buckets(h, c)}
    if not (rset.get("ok") is True and ev["diff"] == ["saveBlob"]):
        raise Stop("not reached: the client-only poke of %d did not leave the diff ['saveBlob'] (%s)" % (uid, js(ev)))
    return ev


def repair_wait(x, rh0, rc0, t_press):
    """released / loaded +1 within W_REPAIR (else Stop), then <= W_NOTICE for the notice on top of both (no dismissal) -> evidence"""
    h, c, tl, seen = x.host, x.client, [], {}

    def poll(pred):
        hs, cs, d = stack(h), stack(c), dlg(h)
        snap = [round(time.time() - t_press, 2), hs[-3:], d.get("code"), d.get("title"), cs[-3:]]
        if not tl or tl[-1][1:] != snap[1:]:
            tl.append(snap)
        return pred(hs, cs)
    try:
        wait("host RS released +1 and client RS loaded +1",
             lambda: poll(lambda hs, cs: delta(rh0, rs(h), "released") >= 1 and delta(rc0, rs(c), "loaded") >= 1), W_REPAIR)
        seen["repair wall s"] = round(time.time() - t_press, 2)
        wait("the notice on top of both", lambda: poll(lambda hs, cs: hs[-1:] == [NOTICE] and cs[-1:] == [NOTICE]), W_NOTICE)
        seen["notice on top s"] = round(time.time() - t_press, 2)
    except Stop as e:
        seen["wait"] = str(e)
        if "repair wall s" not in seen:
            print("EVIDENCE repair (timed out): %s" % js({"timeline": tl, "RS host": rs(h), "RS client": rs(c)}), flush=True)
            raise
    seen["timeline"] = tl
    return seen


def notice_check(gc, d, rsx, want, new_names):
    """repair_notice-1 / repair_notice-2: the notice on top of gc names this machine's own report -> (ok, evidence)"""
    z, msg, url, btn = d.get("zipPath") or "", d.get("message") or "", d.get("reportUrl") or "", d.get("buttons") or []
    checks = {
        "live": d.get("live") is True, "headline": d.get("headline") == want, "message head": msg.startswith(REPAIRED_TEXT),
        "message holds its zip": bool(z) and z in msg.replace("\n", ""), "zipPath == RS bundle": bool(z) and z == rsx.get("bundle"),
        "zip in its own desync-reports, written in this row": (bool(z) and os.path.isfile(z) and os.path.basename(z) in new_names
                                                              and npath(os.path.dirname(z)) == npath(os.path.join(gc.user_dir, "desync-reports"))),
        "openFolderTarget": (d.get("openFolderTarget") or "").endswith("desync-reports"),
        "reportUrl": url.startswith(ISSUE_URL) and "&body=" in url,
        "buttons": [b.get("text") for b in btn] == BUTTONS and all(b.get("visible") is True and b.get("interactive") is True for b in btn)}
    return all(checks.values()), {"failed": [k for k, v in checks.items() if not v], "want headline": want, "RS bundle": rsx.get("bundle"),
                                  "desync_dialog": dd_short(d)}


def close_notices(x):
    """OK on each notice (client first): click_widget {match OK} once OK is shown -> top BattlescapeState <= W_NOTICE -> (ok, evidence)"""
    ev = {}
    for gc in (x.client, x.host):
        if top(gc) != NOTICE:
            ev[gc.name] = {"top": top(gc), "click": "not clicked: no notice on top"}
            continue
        # the notice's POPUP window hides its buttons while it opens (Window::think -> State::hideAll) and a hidden
        # button drops the click while click_widget still answers ok; wait until OK is shown, then the same one click
        try:
            r = session.click_widget_ready(gc, "OK")
        except Exception as e:  # a dead or gone machine is a value
            r = {"error": short(e, 200)}
        ev[gc.name] = {"click": {k: r.get(k) for k in ("ok", "text", "error", "readyS")}}
        try:
            ev[gc.name]["bs s"] = wait("%s top BattlescapeState after OK" % gc.name, lambda: top(gc) == BS, W_NOTICE)
        except Stop as e:
            ev[gc.name]["wait"] = str(e)
    return all(isinstance(v["click"], dict) and v["click"].get("ok") is True and "bs s" in v for v in ev.values()), ev


def walk(x, uid, dest, what):
    """the client's walk order (session.send_walk) for uid to dest; a NEW host walk settled, the host idle; uid on dest on both + HASH"""
    h, c = x.host, x.client
    prev = session.walk_action_id(h)
    r = session.send_walk(c, uid, dest)
    ev = {"send_walk": {k: r.get(k) for k in ("ok", "iseq", "error")}}
    try:
        session.wait_walk_settled(h, c, prev, timeout=W_WALK)
    except Exception as e:
        ev["wait"] = short(e, 300)
    ev["pos"] = [tuple(units(gc).get(uid, {}).get(k) for k in "xyz") for gc in (h, c)]
    hok, ev["HASH"] = hash_ok(h, c, what)
    return bool(r.get("iseq")) and "wait" not in ev and ev["pos"] == [dest, dest] and hok, ev


class Row:
    def __init__(self, rid, cells, x):
        self.rid, self.cells, self.x, self.fails, self.done, self.t0, self.cpu0 = rid, cells, x, [], set(), time.time(), cpu_now()

    def cell(self, cid, kind, label, ok, ev):
        print("EVIDENCE %s: %s" % (cid, js(ev)), flush=True)
        print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label), flush=True)
        self.done.add(cid)
        self.fails += [] if ok else [cid]

    def stop(self, why):
        print("EVIDENCE %s stop: %s" % (self.rid, why), flush=True)
        for cid in [c for c in self.cells if c not in self.done]:
            print("FAIL %s: not reached (%s)" % (cid, str(why)[:200]), flush=True)
            self.fails.append(cid)
            self.done.add(cid)

    def end(self, results, walls):
        walls[self.rid] = round(time.time() - self.t0, 1)
        print("EVIDENCE %s wall: %s s, cpu %s %%" % (self.rid, walls[self.rid], cpu_pct(self.cpu0, cpu_now())), flush=True)
        if self.fails:
            print("CAPTURE %s: %s" % (self.rid, js(capture(self.x))), flush=True)
        results[self.rid] = not self.fails
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)


def capture(x):
    """both machines: stack, battle_state (guarded), event_state, resync_state, coop_dialog_info, desync_dialog, the co-op log tails"""
    cap = {}
    for n, gc in (("host", x.host), ("client", x.client)):
        if gc is None or gc.proc is None or gc.proc.poll() is not None:
            cap[n] = "not running"
            continue
        b = bs(gc)
        cap[n] = {"stack": stack(gc), "battle_state": {k: b.get(k) for k in ("phase", "turn", "side", "authority", "coopWaitText")},
                  "event_state": es(gc), "resync_state": rs(gc), "coop_dialog_info": dlg(gc), "desync_dialog": dd_short(dd(gc)),
                  "desync-reports": listing(gc), "log": [ln.split("\t")[-1][:200] for ln in log(gc) if any(t in ln for t in LOG_TAGS)][-12:]}
    return cap


def row_repair_notice(x, results, walls):
    r = Row("repair_notice", ["repair_notice-%d" % i for i in range(1, 5)], x)
    h, c = x.host, x.client
    x.first_repair = {"lh0": listing(h), "lc0": listing(c), "seq": None}
    try:
        rh0, rc0, nh, nc, d0 = rs(h), rs(c), len(log(h)), len(log(c)), {"host": dd(h), "client": dd(c)}
        pev = poke(x, H2)
        t_press = time.time()
        s0, kev = kneel(x, H)
        rev = repair_wait(x, rh0, rc0, t_press)
        d1 = {"host": dd(h), "client": dd(c)}  # read BEFORE any dismissal
        rh, rc, dl = rs(h), rs(c), desync_line(c, nc)
        x.first_repair["seq"] = (dl or {}).get("seq") or (s0 or 0) + SEQ_OFFSET
        want = "saveBlob diverged at action %d: %s" % (x.first_repair["seq"], KIND_END)
        print("EVIDENCE repair_notice: %s" % js({"poke": pev, "kneel": kev, "repair": rev, "client DESYNC": dl,
                                      "s0 + 2": (s0 or 0) + SEQ_OFFSET,
                                      "RS host": rh, "RS client": rc, "desync_dialog before": {k: dd_short(v) for k, v in d0.items()},
                                      "host lines": [ln.split("\t")[-1][:160] for ln in log(h)[nh:] if "[coop-resync]" in ln][:8]}), flush=True)
        ok, ev = notice_check(c, d1["client"], rc, want, [n for n in listing(c) if n not in x.first_repair["lc0"]])
        r.cell("repair_notice-1", "FIX", "client: the notice on top names its own report (headline %r, %s..., zip, "
               "OPEN FOLDER, GitHub URL, buttons)"
               % (want, REPAIRED_TEXT), ok, ev)
        ok, ev = notice_check(h, d1["host"], rh, want, [n for n in listing(h) if n not in x.first_repair["lh0"]])
        r.cell("repair_notice-2", "FIX", "host: the same with the host's own zip in the host's user dir", ok, ev)
        inc = {n: [(raises(d1[n]) - (raises(d0[n]) or 0)) if raises(d1[n]) is not None else None,
                   delta(rh0 if n == "host" else rc0, rh if n == "host" else rc, "notices")] for n in ("host", "client")}
        r.cell("repair_notice-3", "FIX", "last.raiseCount +1 and RS notices +1 on each machine",
               all(v == [1, 1] for v in inc.values()),
               {"[raiseCount +, notices +] host/client": inc})
        cok, cev = close_notices(x)
        wok, wev = walk(x, G, G_DEST, "repair_notice-4")
        r.cell("repair_notice-4", "FIX", "OK closes it: click_widget OK on each -> top BattlescapeState <= %.0f s; "
               "a client walk of G %d to %s applies; "
               "HASH" % (W_NOTICE, G, G_DEST), cok and wok, {"OK": cev, "walk": wev})
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end(results, walls)


def row_repair_reports(x, results, walls):
    r = Row("repair_reports", ["repair_reports-host_zip", "repair_reports-client_zip",
                               "repair_reports-action_end_kind"], x)
    h, c = x.host, x.client
    try:
        first_repair = x.first_repair or {"lh0": [], "lc0": [], "seq": None}
        hz, cz = new_zips(h, first_repair["lh0"]), new_zips(c, first_repair["lc0"])
        (hzl,), (czl,) = hz[-1:] or [{}], cz[-1:] or [{}]
        hinfo, cinfo, hmem, cmem = hzl.get("info") or {}, czl.get("info") or {}, hzl.get("members") or {}, czl.get("members") or {}
        print("EVIDENCE repair_reports: %s" % js({"host new zips": hz, "client new zips": cz,
                                                  "host listing": listing(h),
                                                  "repair_notice seq": first_repair["seq"]}), flush=True)
        r.cell("repair_reports-host_zip", "FIX", "the host's new zip: desync-info.json role host, bucket / seq == "
               "the client zip's, kind == the client zip's == %s, "
               "peerBundlePath == the client's zip; openxcom.log; saveBlob-host.yaml non-empty" % KIND_END,
               bool(hz) and bool(cz) and hinfo.get("role") == "host" and hinfo.get("bucket") == cinfo.get("bucket") == "saveBlob"
               and hinfo.get("seq") == cinfo.get("seq") and hinfo.get("kind") == cinfo.get("kind") == KIND_END
               and npath(hinfo.get("peerBundlePath")) == npath(czl.get("path")) and "openxcom.log" in hmem
               and (hmem.get("saveBlob-host.yaml") or 0) > 0,
               {"host info": hinfo, "host members": hmem, "client zip": czl.get("path"), "client info": cinfo})
        txt = re.compile(r"^desync-\d{8}-\d{6}-host-saveBlob-seq%s\.yaml$" % first_repair["seq"])
        texts = [n for n in listing(h) if n not in first_repair["lh0"] and txt.match(n)]
        r.cell("repair_reports-client_zip", "GUARD", "the client's one new zip: desync-info.json bucket saveBlob, "
               "openxcom.log, saveBlob-client.yaml; the host's "
               "desync-<ts>-host-saveBlob-seq%s.yaml text exists" % first_repair["seq"],
               len(cz) == 1 and cinfo.get("bucket") == "saveBlob" and "openxcom.log" in cmem and (cmem.get("saveBlob-client.yaml") or 0) > 0
               and len(texts) == 1, {"client members": cmem, "client info": cinfo, "host texts": texts})
        kinds = {"client zip": cinfo.get("kind"), "client RS last": (rs(c).get("last") or {}).get("kind"),
                 "host RS last": (rs(h).get("last") or {}).get("kind")}
        r.cell("repair_reports-action_end_kind", "FIX", "a bt_action_end desync names the action end: the client "
               "zip's kind and both RS last.kind == %s"
               % KIND_END, all(v == KIND_END for v in kinds.values()), kinds)
    except Exception as e:
        r.stop(e)
    r.end(results, walls)


def row_unit_stats_repair(x, results, walls):
    r = Row("unit_stats_repair", ["unit_stats_repair-client_zip", "unit_stats_repair-notice_again"], x)
    h, c = x.host, x.client
    try:
        staged_live(x)
        tu = dc.tu_both(h, c, KNEELER)
        rh0, rc0, nc, lc0, d0 = rs(h), rs(c), len(log(c)), listing(c), {"host": dd(h), "client": dd(c)}
        before = {u["id"]: u.get("tu") for u in bs(c).get("units") or []}
        rcor = q(c, {"cmd": "corrupt_bucket", "name": "unitsStats"})
        after = {u["id"]: u.get("tu") for u in bs(c).get("units") or []}
        moved = [uid for uid in after if before.get(uid) != after.get(uid)]
        print("EVIDENCE unit_stats_repair corrupt: %s" % js({"tu_both KNEELER": tu, "corrupt": rcor, "moved": moved,
                                                              "U": U, "KNEELER": KNEELER}), flush=True)
        if not (rcor.get("ok") is True and moved == [U]):
            raise Stop("not reached: corrupt_bucket {unitsStats} did not move exactly U %d's client TU (%s)" % (U, moved))
        t_press = time.time()
        s0, kev = kneel(x, KNEELER)
        rev = repair_wait(x, rh0, rc0, t_press)
        d1, rh, rc = {"host": dd(h), "client": dd(c)}, rs(h), rs(c)
        print("EVIDENCE unit_stats_repair: %s" % js({"kneel": kev, "repair": rev, "client DESYNC": desync_line(c, nc),
                                      "RS host": rh, "RS client": rc,
                                      "desync_dialog": {k: dd_short(v) for k, v in d1.items()}}), flush=True)
        cz = new_zips(c, lc0)
        cinfo, cmem = (cz[-1:] or [{}])[0].get("info") or {}, (cz[-1:] or [{}])[0].get("members") or {}
        r.cell("unit_stats_repair-client_zip", "FIX", "the client's new zip holds saveBlob-client.yaml (non-empty) "
               "and desync-info.json bucket %s, role client" % UNIT_STATS_BUCKET,
               len(cz) == 1 and (cmem.get("saveBlob-client.yaml") or 0) > 0 and cinfo.get("bucket") == UNIT_STATS_BUCKET
               and cinfo.get("role") == "client",
               {"client new zips": cz})
        each = {n: {"live": d1[n].get("live"), "raiseCount +": (raises(d1[n]) - (raises(d0[n]) or 0)) if raises(d1[n]) is not None else None,
                    "notices +": delta(rh0 if n == "host" else rc0, rh if n == "host" else rc, "notices"), "headline": d1[n].get("headline")}
                for n in ("host", "client")}
        cok, cev = close_notices(x)
        r.cell("unit_stats_repair-notice_again", "FIX", "a notice on each machine again (live, last.raiseCount +1 "
               "more, RS notices +1); OK on each -> BattlescapeState",
               all(v["live"] is True and v["raiseCount +"] == 1 and v["notices +"] == 1 for v in each.values()) and cok, {"each": each, "OK": cev})
    except Exception as e:
        r.stop(e)
    r.end(results, walls)


def row_held_repair(x, results, walls):
    r = Row("held_repair", ["held_repair-halt", "held_repair-both_reports", "held_repair-no_notice"], x)
    h, c = x.host, x.client
    try:
        staged_live(x)
        rh0, rc0, nh, nc, lh0, lc0, d0 = rs(h), rs(c), len(log(h)), len(log(c)), listing(h), listing(c), {"host": dd(h), "client": dd(c)}
        hold = q(h, {"cmd": "resync_hold", "on": True})
        if hold.get("armed") is not True:
            raise Stop("not reached: resync_hold did not arm (%s)" % js(hold))
        pev = poke(x, H2)
        t_press = time.time()
        s0, kev = kneel(x, H)
        w = wait("client RS desyncs +1 and host RS desyncs +1",
                 lambda: delta(rc0, rs(c), "desyncs") >= 1 and delta(rh0, rs(h), "desyncs") >= 1, W_HELD)
        rh, rc, wt = rs(h), rs(c), bs(c).get("coopWaitText")
        print("EVIDENCE held_repair: %s" % js({"hold": hold, "poke": pev, "kneel": kev, "desyncs +1 s": w,
                                      "client DESYNC": desync_line(c, nc),
                                      "RS host": rh, "RS client": rc, "client stack": stack(c),
                                      "host lines": [ln.split("\t")[-1][:160] for ln in log(h)[nh:] if "[coop-resync]" in ln][:6]}), flush=True)
        r.cell("held_repair-halt", "GUARD", "the halt: client RS frozen true; host RS held +1; client "
               "coopWaitText == %r" % HALTED,
               rc.get("frozen") is True and delta(rh0, rh, "held") == 1 and wt == HALTED,
               {"client frozen": rc.get("frozen"), "host held +": delta(rh0, rh, "held"), "coopWaitText": wt})
        hz, cz = new_zips(h, lh0), new_zips(c, lc0)
        r.cell("held_repair-both_reports", "FIX", "both wrote a report: the client's and the host's desync-reports "
               "each gained one zip, the host's role host",
               len(cz) == 1 and len(hz) == 1 and (hz[0].get("info") or {}).get("role") == "host",
               {"client new zips": cz, "host new zips": hz, "host listing": listing(h)})
        seen, t_end = [], time.time() + W_NOTICE
        while time.time() < t_end:
            seen += [[gc.name, round(time.time() - t_press, 2)] for gc in (h, c) if NOTICE in stack(gc)]
            time.sleep(POLL)
        d1 = {"host": dd(h), "client": dd(c)}
        same = {n: [raises(d0[n]), raises(d1[n]), delta(rh0 if n == "host" else rc0, rs(h) if n == "host" else rs(c), "notices")]
                for n in ("host", "client")}
        r.cell("held_repair-no_notice", "GUARD", "no notice within %.0f s: no %s on either stack; last.raiseCount "
               "and RS notices unchanged on both" % (W_NOTICE, NOTICE),
               not seen and all(v[0] == v[1] and v[2] == 0 for v in same.values()),
               {"notice seen": seen[:6], "[raiseCount before, after, notices +] host/client": same, "stacks": [stack(h), stack(c)]})
    except Exception as e:
        r.stop(e)
    r.end(results, walls)


def boot():
    """the boot -> x (x.err set on a miss: setup failure)"""
    x = SimpleNamespace(host=None, client=None, err=None, first_repair=None)
    try:
        x.host, x.client = GameClient("host", 1, make_user_dir(TAG + "_host")), GameClient("client", 2, make_user_dir(TAG + "_client"))
        raw.bring_up_lobby(x.host, x.client, KEY)
        session.drive_to_battlescape(x.host, x.client, {}, seat_count=2, pre_ok=lambda gc: gc.ok({"cmd": "set_seed", "seed": SEED_MAP}))
        hs, cs = session.battle_state(x.host), session.battle_state(x.client)
        fp = [hs.get("mapFingerprint"), cs.get("mapFingerprint")]
        assert fp == [MAP_FP, MAP_FP], "SETUP-FAILURE: mapFingerprint %s (MAP_FP %r, SEED_MAP %d)" % (fp, MAP_FP, SEED_MAP)
        pinned = session.pin_ai_neutral(x.host, x.client, tag=TAG)
        assert pinned, "SETUP-FAILURE: pin_ai_neutral pinned no NONE-seat non-player unit"
        session.wait_host_idle(x.host, x.client, timeout=W_IDLE)
        session.assert_hash_clean(x.host, x.client, full=True, what="bring-up")
        live_us = [u for u in hs.get("units") or [] if u.get("faction") == 0 and not u.get("isOut")]
        s0, s1 = [sorted(u["id"] for u in live_us if u.get("coop") == k) for k in (0, 1)]
        gt = tuple(session.units_by_id(hs).get(G, {}).get(k) for k in "xyz")
        b0 = [(r.get("authority") or {}).get("battleId") for r in (hs, cs)]
        assert s0[:2] == [H, H2] and s1[:1] == [G] and gt == G_TILE and b0[0] and b0[0] == b0[1], (
            "SETUP-FAILURE: pins seat0 %s seat1 %s G at %s B0 %s (CONSTANTS H %d, H2 %d, G %d at %s)" % (s0, s1, gt, b0, H, H2, G, G_TILE))
        print("[test_desync_notice] boot ok: MAP_FP %r, pinned %s, B0 %s, turn %s, seats %s / %s"
              % (MAP_FP, pinned, b0, hs.get("turn"), s0, s1), flush=True)
    except Exception as e:
        x.err = short(e, 800)
    return x


def shut(x):
    failed = []
    for gc in [g for g in (x.client, x.host) if g is not None and g.proc is not None]:
        try:
            gc.shutdown()
        except Exception as e:
            print("FAIL shutdown (%s): %s" % (gc.name, short(e, 300)), flush=True)
            failed.append("shutdown %s" % gc.name)
    return failed


ROWS = (("repair_notice", row_repair_notice), ("repair_reports", row_repair_reports),
        ("unit_stats_repair", row_unit_stats_repair), ("held_repair", row_held_repair))


def main():
    t0, results, walls, cr0 = time.time(), {}, {}, session._crash_log_snapshot()
    x = boot()
    walls["boot"] = round(time.time() - t0, 1)
    if x.err:
        print("EVIDENCE boot: %s\nCAPTURE boot: %s" % (x.err, js(capture(x))), flush=True)
        for rid, _fn in ROWS:
            print("FAIL %s boot: the boot did not reach the tactical map with its pins" % rid, flush=True)
            results[rid] = False
    else:
        for _rid, fn in ROWS:
            fn(x, results, walls)
    failed = shut(x)
    new = sorted(session._crash_log_snapshot() - cr0)
    print("EVIDENCE no_crash: %s" % js({"crash": new}), flush=True)
    print("%s no_crash GUARD: CRASH 0 (no new crash_*.log in this lane's crash folder over the run)"
          % ("PASS" if not new else "FAIL"), flush=True)
    results["no_crash"] = not new
    names = [rid for rid, _fn in ROWS] + ["no_crash"]
    failed += [rid for rid in names if not results.get(rid)]
    print("\ntest_desync_notice: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (
        sum(1 for rid in names if results.get(rid)), len(names), failed, js(walls), time.time() - t0), flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
