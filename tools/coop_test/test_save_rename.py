"""W2-H91 (owner D303 (a) then (b); trace docs rewrite/w2-resume-dafc8555/reports/cap-vw67.md F24197-F24203; F24235-F24259): a co-op
save's final rename (<name>.bak -> <name>) that fails because another process holds the file is retried for a short bounded time; a
rename that still fails shows vanilla's save error on the machine whose save failed, and the save stays in <name>.bak. Vanilla
single-player saves are unchanged. Two co-op save paths, three rows each, one fresh boot pair per row:
  D = the deferred host save (connectionTCP::writePendingHostSave, the R14 path): a SEPARATE campaign host quick save on the geoscape
      (save_game_ui quick: SaveGameState arms it, CoopState 54 "Saving...", the partner's world lands, MAP_RESULT_SAVE_PROGRESS writes);
  B = SaveGameState's own write in co-op: a skirmish host's mid-battle quick save (save_game_ui quick_battle, the F5 key's path).
  X0 no lock (control); X1 short lock: a helper process (this file's HELPER, started and killed by the row) holds <name> open with
  Python open "rb" (share read + write, no delete: cap-vw67 E2's opener, err 5) from before the trigger until LOCK1_S after the save's
  <name>.bak shows in the folder listing; X2 long lock: the same until LOCK2_S after, past the product's 2.0 s retry bound.
Every row first writes a PLACEHOLDER <name> into the host's save folder, so every save renames over an existing file. The folder is
read only by name listing + os.scandir's cached DirEntry.stat (no per-file open, which can itself block the rename: cap-vw67 F24200).
Cells (X = D0 D1 D2 B0 B1 B2):
  X-pre GUARD (the trigger ok; D: armDeferredSave +1 since B; B: armDeferredSave +0; the save done within W_SAVE: D clearDeferredSave
  +1 and no CoopState on the host stack, B no SaveGameState and battle_state.coopSavePending false; X1 X2: the helper HELD before the
  trigger); X-lock GUARD (X1 X2: the helper saw <name>.bak while it held <name> and held it LOCK1_S / LOCK2_S more);
  X-file (X0 GUARD, X1 RED: <name> holds the new save (a save header, mtime newer than the trigger) and <name>.bak is gone; X2 GUARD:
  <name> is still the placeholder and <name>.bak holds the new save); X-dialog (X0 X1 GUARD: the host stack = B's; X2 RED: B's +
  [ErrorMessageState] whose text is SaveGameState::error's "STR_SAVE_UNSUCCESSFUL" TOK_NL_SMALL "Save backed up in <name>.bak");
  X2-ok RED (the error's OK closes it: B's stack within W_OK); X2-next GUARD (after the helper exits, a second save with no lock lands:
  <name> a new save, no <name>.bak, B's stack); X-partner GUARD (the client's stack = its B within W_PARTNER, no ErrorMessageState);
  X-common GUARD (both alive, no new crash_*.log since B). 38 cells.
Red at the base (`cc5875d65`): exit 2, RED exactly on D1-file, B1-file, D2-dialog, D2-ok, B2-dialog, B2-ok (6).
A precondition miss ends its row (cells "not reached"); a boot miss fails the row "boot" with ONE CAPTURE line. ONE EVIDENCE line per
row, one PASS / FAIL line per cell, the row verdict; exit 0 only when every cell passes, else 2. one
foreground run per invocation.
Run: py -3 tools/coop_test/test_save_rename.py
"""
import json, os, subprocess, sys, time  # noqa: E401
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import repro_atom_walk as raw  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY_CAMPAIGN, KEY_SKIRMISH = "49471", "49472"
NAME = "_quick_.asav"
BAK = NAME + ".bak"
PLACEHOLDER = b"w2-h91 placeholder: not a save\n"
# SaveGameState::error (src/Menu/SaveGameState.cpp): tr("STR_SAVE_UNSUCCESSFUL") (bin/common/Language/en-US.yml "Save failed"),
# Unicode::TOK_NL_SMALL (char 2), then the exception text "Save backed up in " + backup.
ERROR_TEXT = "Save failed" + "\x02" + "Save backed up in " + BAK
LOCK1_S, LOCK2_S, HELPER_LIFE_S = 0.3, 4.0, 20.0
POLL_S, W_SAVE, W_OK, W_PARTNER, STABLE_S, BOOT_S = 0.05, 15.0, 5.0, 5.0, 2.0, 90.0
RC_OK = (0, 3221226505)
NEEDLES = {"ARM": "[coop-session] armDeferredSave ('%s')" % NAME, "CLEAR": "[coop-session] clearDeferredSave"}

# The lock helper: open <target> "rb" (share read + write, no delete), print HELD, poll the folder's NAMES (os.listdir: no per-file
# open) every 2 ms for <bak>, hold <hold> s after it shows (or until <life> s when it never does), close, print RELEASED, exit.
# Times print in full float precision (repr), so released - seen >= hold holds exactly as the helper's loop ensured it.
HELPER = r'''
import os, sys, time
target, folder, bak, hold, life = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5])
t0 = time.time()
fh = open(target, "rb")
print("HELD %r" % time.time(), flush=True)
seen = None
while time.time() - t0 < life:
    if bak in os.listdir(folder):
        seen = time.time()
        break
    time.sleep(0.002)
while seen is not None and time.time() - seen < hold:
    time.sleep(0.005)
fh.close()
print("RELEASED %r SEEN %s" % (time.time(), repr(seen) if seen is not None else "none"), flush=True)
'''


class Stop(Exception):
    """a WAIT timed out or a precondition missed: the row ends here"""


def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]


def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead or gone machine is a value
        return {"error": short(e, 200)}


def alive(gc):
    return gc is not None and gc.proc is not None and gc.proc.poll() is None


def stack(gc):
    return [s.replace("class OpenXcom::", "") for s in q(gc, {"cmd": "get_state"}).get("states", [])]


def pending(gc):
    return q(gc, {"cmd": "get_coop"}).get("pendingHostSaveName")


def save_pending(gc):
    return q(gc, {"cmd": "battle_state"}).get("coopSavePending")


def texts(gc):
    """the top state's class and its Text / TextButton captions (list_widgets)"""
    r = q(gc, {"cmd": "list_widgets"})
    return str(r.get("state", "")).replace("class OpenXcom::", ""), [w.get("text") for w in r.get("widgets", []) if w.get("text") is not None]


def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def counts(gc, n0):
    lines = log(gc)[n0:]
    return {k: sum(1 for ln in lines if v in ln) for k, v in NEEDLES.items()}


def wait(desc, pred, timeout, interval=POLL_S):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return round(time.time() - t0, 2)
        time.sleep(interval)
    raise Stop("WAIT %s: timed out after %.0f s" % (desc, timeout))


def folder(gc):
    return os.path.join(gc.user_dir, "xcom1")


def files(gc):
    """the host's save folder: name -> [bytes, mtime_ns], from os.scandir's cached find data (no per-file open, F24200)"""
    out = {}
    try:
        with os.scandir(folder(gc)) as it:
            for e in it:
                try:
                    if e.is_file():
                        st = e.stat()
                        out[e.name] = [st.st_size, st.st_mtime_ns]
                except FileNotFoundError:  # renamed after the listing
                    pass
    except FileNotFoundError:
        pass
    return out


def head(gc, f):
    try:
        with open(os.path.join(folder(gc), f), "rb") as fh:
            return fh.read(200)
    except OSError as e:  # a value
        return short(e, 120).encode()


def is_save(b):
    return isinstance(b, bytes) and b != PLACEHOLDER[:200] and b"name: " in b and b"version: " in b


def file_state(gc, t_ns):
    """after the save: the folder, <name> / <name>.bak heads and whether each is a save written after t_ns"""
    fo = files(gc)
    out = {"folder": fo}
    for f in (NAME, BAK):
        b = head(gc, f) if f in fo else None
        out[f] = {"present": f in fo, "placeholder": b == PLACEHOLDER, "save": is_save(b), "newer": bool(f in fo and fo[f][1] >= t_ns),
                  "head": (b or b"")[:40].decode("latin-1")}
    return out


class Helper:
    def __init__(self, gc, hold):
        self.hold, self.out, self.rec = hold, None, {}
        self.p = subprocess.Popen([sys.executable, "-I", "-c", HELPER, os.path.join(folder(gc), NAME), folder(gc), BAK, str(hold),
                                   str(HELPER_LIFE_S)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        line = self.p.stdout.readline().strip()
        self.rec["first line"] = line
        self.held_at = float(line.split()[1]) if line.startswith("HELD ") else None

    def finish(self, timeout=HELPER_LIFE_S + 5):
        """wait for the helper's exit and parse RELEASED <t> SEEN <t|none>"""
        try:
            rest, _ = self.p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.kill()
            rest = "(killed: no exit within %.0f s)" % timeout
        self.rec["rest"] = rest.strip()[:300]
        self.rec["rc"] = self.p.poll()
        for ln in rest.splitlines():
            parts = ln.split()
            if len(parts) == 4 and parts[0] == "RELEASED":
                self.rec["released"] = float(parts[1])
                self.rec["seen"] = None if parts[3] == "none" else float(parts[3])
        return self.rec

    def kill(self):
        if self.p.poll() is None:
            self.p.kill()
            self.p.wait(timeout=10)


class Row:
    def __init__(self, rid, cells, x):
        self.rid, self.cells, self.x, self.fails, self.done, self.t0, self.n_h = rid, cells, x, [], set(), time.time(), 0
        self.cr0, self.ev = session._crash_log_snapshot(), {}

    def evidence(self):
        print("EVIDENCE %s: %s" % (self.rid, json.dumps(self.ev, sort_keys=True, default=str)), flush=True)

    def cell(self, cid, kind, label, ok):
        print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label), flush=True)
        self.done.add(cid)
        self.fails += [] if ok else [cid]

    def stop(self, why):
        for cid in [c for c in self.cells if c not in self.done]:
            print("FAIL %s: not reached (%s)" % (cid, str(why)[:200]), flush=True)
            self.fails.append(cid)

    def end(self, results, walls, cap=None):
        """ONE CAPTURE line when a cell failed, then the row verdict"""
        x, walls[self.rid] = self.x, round(time.time() - self.t0, 1)
        if self.fails:
            if cap is None:
                cap = {n: {"stack": stack(gc), "get_coop": q(gc, {"cmd": "get_coop"}).get("pendingHostSaveName"), "top": texts(gc)}
                       for n, gc in (("host", x.host), ("client", x.client)) if alive(gc)}
                if alive(x.host):
                    cap["host needle deltas"] = counts(x.host, self.n_h)
                    cap["HL"] = [ln.split("\t")[-1][:200] for ln in log(x.host) if "[coop" in ln or "Save" in ln][-14:]
                    cap["host folder"] = files(x.host)
                cap["new crash"] = sorted(session._crash_log_snapshot() - self.cr0)
            print("CAPTURE %s: %s" % (self.rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
        results[self.rid] = not self.fails
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)

    def boot_miss(self, results, walls):
        print("FAIL %s boot: the boot did not reach both tops %s unchanged %.0f s (%s)" % (self.rid, self.x.top, STABLE_S, self.x.err),
              flush=True)
        self.fails.append("boot")
        self.stop("boot")
        self.end(results, walls, cap=self.x.cap)


def trigger(r, x, label):
    """one save on the host through the row's path; waits until it is done -> (t, t_ns, the done wait)"""
    h, path, n0 = x.host, x.path, r.n_h
    c0 = counts(h, n0)
    t, t_ns = time.time(), time.time_ns()
    rep = q(h, {"cmd": "save_game_ui", "type": "quick" if path == "D" else "quick_battle"})
    ev = r.ev.setdefault(label, {})
    ev["reply"] = {k: rep.get(k) for k in ("ok", "error")}
    if path == "D":
        done = lambda: counts(h, n0)["CLEAR"] > c0["CLEAR"] and "CoopState" not in stack(h) and pending(h) == ""  # noqa: E731
    else:
        done = lambda: "SaveGameState" not in stack(h) and save_pending(h) is False  # noqa: E731
    try:
        ev["done s"] = wait("the %s save done" % label, done, W_SAVE)
    except Stop as e:
        ev["done"] = str(e)
    c1 = counts(h, n0)
    ev["needles"] = {k: c1[k] - c0[k] for k in c1}
    return t, t_ns, "done" not in ev


def row(x, results, walls):
    rid, p, lvl = x.rid, x.rid[:2], x.lvl
    cells = [p + "-pre"] + ([p + "-lock"] if lvl else []) + [p + "-file", p + "-dialog"] + ([p + "-ok", p + "-next"] if lvl == 2 else [])
    cells += [p + "-partner", p + "-common"]
    r = Row(rid, cells, x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c, ev, hp = x.host, x.client, r.ev, None
    try:
        os.makedirs(folder(h), exist_ok=True)
        with open(os.path.join(folder(h), NAME), "wb") as fh:
            fh.write(PLACEHOLDER)
        r.cr0, r.n_h = session._crash_log_snapshot(), len(log(h))
        B = ev["B"] = {"host": stack(h), "client": stack(c), "folder": files(h)}
        if lvl:
            hp = x.helper = Helper(h, LOCK1_S if lvl == 1 else LOCK2_S)
            ev["helper start"] = dict(hp.rec)
        t, t_ns, done = trigger(r, x, "save")
        n = ev["save"]["needles"]
        pre_ok = ev["save"]["reply"].get("ok") is True and done and n["ARM"] == (1 if x.path == "D" else 0)
        pre_label = "the trigger ok, armDeferredSave +%d, the save done within %.0f s" % (1 if x.path == "D" else 0, W_SAVE)
        if lvl:
            pre_ok = pre_ok and hp.held_at is not None and hp.held_at <= t  # one clock tick (~15.6 ms, Python 3.12) can give both
            pre_label += ", the helper HELD %s before the trigger" % NAME
        rd = ev["read"] = {"host": stack(h), "top": texts(h), "files": file_state(h, t_ns), "pending": pending(h)}
        if not pre_ok:
            if hp:
                ev["helper"] = hp.finish()
            r.evidence()
            r.cell(p + "-pre", "GUARD", pre_label, False)
            raise Stop("%s-pre: %s" % (p, ev["save"]))
        fs = rd["files"]
        top_state, top_texts = rd["top"]
        if lvl == 2 and top_state == "ErrorMessageState":
            ev["ok press"] = session.click_widget_ready(h, "OK")
            try:
                ev["ok s"] = wait("the host stack back to B's", lambda: stack(h) == B["host"], W_OK)
            except Stop as e:
                ev["ok"] = str(e)
        try:
            ev["partner s"] = wait("the client's stack = its B", lambda: stack(c) == B["client"], W_PARTNER)
        except Stop as e:
            ev["partner"] = str(e)
        ev["client top"] = texts(c)
        if hp:
            ev["helper"] = hp.finish()
        if lvl == 2:
            t2, t2_ns, done2 = trigger(r, x, "next")
            ev["next read"] = {"host": stack(h), "top": texts(h), "files": file_state(h, t2_ns)}
        r.evidence()
        r.cell(p + "-pre", "GUARD", pre_label, True)
        if lvl:
            hr, hold = ev["helper"], hp.hold
            r.cell(p + "-lock", "GUARD", "the helper saw %s while it held %s and held it %.1f s more" % (BAK, NAME, hold),
                   hr.get("seen") is not None and hr.get("released") is not None and hr["released"] - hr["seen"] >= hold)
        if lvl < 2:
            r.cell(p + "-file", "RED" if lvl == 1 else "GUARD", "%s holds the new save (a save header, mtime newer than the trigger), no %s%s" % (
                NAME, BAK, " (red today: not written, the rename failed silently, F24199)" if lvl == 1 else ""),
                fs[NAME]["save"] and fs[NAME]["newer"] and not fs[BAK]["present"])
            r.cell(p + "-dialog", "GUARD", "the host stack = B's %s after the save (no error)" % B["host"], rd["host"] == B["host"])
        else:
            r.cell(p + "-file", "GUARD", "%s still the placeholder, %s holds the new save (vanilla: the save stays in the backup)" % (NAME, BAK),
                   fs[NAME]["placeholder"] and fs[BAK]["save"] and fs[BAK]["newer"])
            r.cell(p + "-dialog", "RED", "the host stack = B's + [ErrorMessageState], its text %r (red today: silent, no error)" % ERROR_TEXT,
                   rd["host"] == B["host"] + ["ErrorMessageState"] and top_state == "ErrorMessageState" and ERROR_TEXT in top_texts)
            r.cell(p + "-ok", "RED", "the error's OK closes it: the host stack = B's within %.0f s (red today: no error to close)" % W_OK,
                   "ok s" in ev)
            nr = ev["next read"]
            r.cell(p + "-next", "GUARD", "a second save with no lock lands: %s a new save, no %s, B's stack" % (NAME, BAK),
                   done2 and nr["files"][NAME]["save"] and nr["files"][NAME]["newer"] and not nr["files"][BAK]["present"]
                   and nr["host"] == B["host"])
        r.cell(p + "-partner", "GUARD", "the client's stack = its B %s within %.0f s, no ErrorMessageState" % (B["client"], W_PARTNER),
               "partner s" in ev and ev["client top"][0] != "ErrorMessageState")
        r.cell(p + "-common", "GUARD", "host and client alive, no new crash_*.log since B",
               alive(h) and alive(c) and not sorted(session._crash_log_snapshot() - r.cr0))
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    finally:
        if hp:
            hp.kill()
    r.end(results, walls)


def settle_tops(x, top):
    t0, last, tch = time.time(), None, time.time()
    while True:
        s = (tuple(stack(x.host)), tuple(stack(x.client)))
        if s != last:
            last, tch = s, time.time()
        if s[0] and s[1] and s[0][-1] == s[1][-1] == top and time.time() - tch >= STABLE_S:
            return
        if time.time() - t0 > BOOT_S:
            raise Stop("both tops %s unchanged %.0f s: not within %.0f s" % (top, STABLE_S, BOOT_S))
        time.sleep(0.1)


def boot(rid, lvl):
    """D: spawn, connect, session.new_campaign(port=KEY_CAMPAIGN) SEPARATE, both tops GeoscapeState; B: repro_atom_walk.bring_up_lobby
    (KEY_SKIRMISH) + session.drive_to_battlescape(seat_count=2), both tops BattlescapeState (else x.err and x.cap)"""
    path = rid[0]
    tag = "w2h91_" + rid.lower()
    x = SimpleNamespace(rid=rid, lvl=lvl, path=path, tag=tag, host=None, client=None, helper=None, err=None, cap=None,
                        top="GeoscapeState" if path == "D" else "BattlescapeState")
    try:
        x.host, x.client = GameClient("host", None, make_user_dir(tag + "_host")), GameClient("client", None, make_user_dir(tag + "_client"))
        if path == "D":
            x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
            session.new_campaign(x.host, x.client, port=KEY_CAMPAIGN, campaign_mode="coop")
        else:
            raw.bring_up_lobby(x.host, x.client, KEY_SKIRMISH)
            session.drive_to_battlescape(x.host, x.client, {}, seat_count=2)
        settle_tops(x, x.top)
    except Exception as e:
        x.err = short(e, 600)
        x.cap = {n: {"stack": stack(gc)} for n, gc in (("host", x.host), ("client", x.client)) if alive(gc)}
    return x


def shut(x):
    failed = []
    if x.helper is not None:
        x.helper.kill()
    for gc in (x.client, x.host):
        try:
            if gc is not None and gc.proc is not None:
                gc.shutdown(expected_returncodes=RC_OK)
        except Exception as e:
            print("FAIL %s shutdown (%s): %s" % (x.tag, gc.name, short(e, 300)), flush=True)
            failed.append("%s shutdown %s" % (x.tag, gc.name))
    return failed


ROWS = (("D0", 0), ("D1", 1), ("D2", 2), ("B0", 0), ("B1", 1), ("B2", 2))


def main():
    t0, results, walls, failed = time.time(), {}, {}, []
    for rid, lvl in ROWS:
        tb = time.time()
        x = boot(rid, lvl)
        walls[rid + " boot"] = round(time.time() - tb, 1)
        try:
            row(x, results, walls)
        finally:
            failed += shut(x)
        walls[rid + " total"] = round(time.time() - tb, 1)
    failed += [rid for rid, _l in ROWS if not results.get(rid)]
    print("\ntest_save_rename: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (
        sum(1 for rid, _l in ROWS if results.get(rid)), len(ROWS), failed, json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
