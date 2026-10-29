"""After a SEPARATE guest battle in which the second player rejoined, the host shows the partner's base right after the
debriefing. When broken: when the HOST clicks OK on its debriefing first, the client (still on its own debriefing, the
host's battle world loaded) answers the host's post-battle baseRequest with the HOST's own base; the host coopBase3
caches it, the partner's later coopBase is ignored (cache non-empty) and the host shows no partner base until its next
geoscape re-init (4 of 4 runs).
TWO boots in turn (each shut down before the next), one SEPARATE guest battle each
(session.bring_up_separate_guest_battle, PRE = set_seed SEED + the base reads HB / CB); END = the host's abort,
AbortMissionState OK, the client's VoteMenu YES, the first machine's DebriefingState OK, OK_GAP_S, the other's; both
GeoscapeState calm 2 s = T; READ at T + READ_S (no host geoscape re-init before it).
  Row client_first (boot 1, KEY_CLIENT_FIRST; the ordinary rejoin as test_host_partner_mirror's ordinary_rejoin, the
           CLIENT's OK first; GUARD: the order control) client_first-host_shows_partner (GUARD) mir(host) ==
           [(CB_NAME, CB)] exactly at READ. client_first-host_not_own (GUARD) no base in mir(host) has coopBaseId HB.
           client_first-client_shows_host (GUARD) mir(client2) holds (HB_NAME, HB) at READ.
  Row trap_rejoin (boot 2, KEY_TRAP; the trap rejoin: the client's Escape > PauseState CO-OP > LobbyMenu DISCONNECT,
           Direct Connect from that ServerList, the host's RESUME once its 62 shows resumeAck; the host's OK first;
           fails when broken) trap_rejoin-host_shows_partner (FIX) as client_first-host_shows_partner;
           trap_rejoin-host_not_own (GUARD) as client_first-host_not_own; trap_rejoin-client_shows_host (GUARD) as
           client_first-client_shows_host for the same client process.
  END      CRASH (GUARD): no crash file new since the file start (both boots); every process alive until its shutdown
           (the killed client excepted).
When broken: trap_rejoin-host_shows_partner FAILS (mir(host) == []); every other cell PASSES.
mir(gc) = geo_state bases with coopIcon true as [name, coopBaseId]; own(gc) = bases with coopIcon and coopBase false.
Every press is a real click_widget on a visible, not hidden widget, except the client's Escape key (trap_rejoin), the
Direct Connect port keys,
the host's battle_action abort and the VOTE rule (a vote_cast when the YES button is not shown within VOTE_S). Never a
popup dismiss, a coop dialog back or a base leave; no host re-init before READ. One EVIDENCE line per row, one PASS /
FAIL line per cell, then the row verdict; a precondition miss ends its row (CAPTURE line, cells "not reached") and the
file goes on to its next boot; a boot miss fails that boot's cells "boot" with ONE CAPTURE line.
ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_host_partner_mirror_trap.py   (OXC_HARNESS_SLOT selects the harness slot)"""
import glob, json, os, subprocess, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY_CLIENT_FIRST = "49215"
KEY_TRAP = "49216"
NAME = "ClientPlayer"
SEED = 7
DROP_S, TRAP_S, REJOIN_S, BOTH_S, VOTE_S, DEBRIEF_S, OK_GAP_S, READ_S = 30.0, 10.0, 90.0, 5.0, 20.0, 120.0, 4.0, 5.0
NEEDLES = ("[coop] coopBase3 marker", "[coop-session]", "COOP_READY")
ROWS = (("client_first", ("client_first-host_shows_partner", "client_first-host_not_own",
                          "client_first-client_shows_host")),
        ("trap_rejoin", ("trap_rejoin-host_shows_partner", "trap_rejoin-host_not_own",
                         "trap_rejoin-client_shows_host")),
        ("END", ("CRASH",)))
BOOTS = (("client_first", KEY_CLIENT_FIRST, "client_first", lambda b, r: row_client_first(b, r)),
         ("trap", KEY_TRAP, "trap_rejoin", lambda b, r: row_trap_rejoin(b, r)))
FIX = ("trap_rejoin-host_shows_partner",)
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
SDLK_END, SDLK_BACKSPACE = 279, 8
T0 = [time.time()]

class Stop(Exception):
    """a precondition missed: the row ends here"""

# ----- probes and real clicks (a standalone copy, never imported) -----
def js(v): return json.dumps(v, sort_keys=True, default=str)
def now(): return round(time.time() - T0[0], 3)
def alive(gc): return gc is not None and gc.proc is not None and gc.proc.poll() is None
def crashes(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))
def mir(bl): return [[b[0], b[1]] for b in bl if b[2]] if isinstance(bl, list) else bl              # coopIcon true
def own(bl): return [[b[0], b[1]] for b in bl if not b[2] and not b[3]] if isinstance(bl, list) else bl  # coopIcon, coopBase false
def top(gc): return (stk(gc) or [None])[-1]
def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # noqa: BLE001
        return {"error": ("%s: %s" % (type(e).__name__, e))[:200]}
def stk(gc):
    r = q(gc, {"cmd": "get_state"})
    return [s.replace("class OpenXcom::", "") for s in r["states"]] if "states" in r else ["probe failed: %s" % r.get("error")]
def dlg(gc):
    r = q(gc, {"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("code", "title", "backText", "backVisible", "error") if k in r}
def bases(gc):
    r = q(gc, {"cmd": "geo_state"})
    return [[b.get("name"), b.get("coopBaseId"), b.get("coopIcon"), b.get("coopBase")] for b in r["bases"]] if "bases" in r else r.get("error")
def cpu():
    ps = ("(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; "
          "(Get-Process Wardogs* -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }) -join ','")
    try:
        out = [x.strip() for x in subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30).stdout.splitlines()]
        return {"t": time.strftime("%H:%M:%S"), "cpu": out[0] if out else None, "wardogs": out[1] if len(out) > 1 else ""}
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}
def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []
def lines_since(gc, n0):
    return [ln.split("\t")[0][-13:-1] + " " + ln.split("\t")[-1][:600] for ln in logl(gc)[n0:] if any(n in ln for n in NEEDLES)]
def widgets(gc):
    r = q(gc, {"cmd": "list_widgets"})
    return (r.get("state") or "").replace("class OpenXcom::", ""), [w for w in r.get("widgets", []) if w.get("visible") and w.get("interactive")]
def wait_shown(gc, state, match, timeout):
    end = time.time() + timeout
    while time.time() < end and alive(gc):
        st, ws = widgets(gc)
        bs = [w for w in ws if "TextButton" in (w.get("type") or "") and match.lower() in (w.get("text") or "").lower()]
        if state in st and bs and bs[0].get("hidden") is False:
            return True
        time.sleep(0.05)
    return False
def settle(gc, quiet, timeout=20.0):
    end, last, prev = time.time() + timeout, time.time(), None
    while time.time() < end and alive(gc) and time.time() - last < quiet:
        s = stk(gc)
        if s != prev:
            prev, last = s, time.time()
        time.sleep(0.05)
    return prev
def real_click(b, gc, state, match, step, timeout=30.0, quiet=1.5):
    s = {"step": step, "who": gc.name, "before": stk(gc)}
    b.steps.append(s)
    if not wait_shown(gc, state, match, timeout):
        s["result"] = "NOT SHOWN by %s s" % now()
        return False
    s["shown"], s["click"] = now(), q(gc, {"cmd": "click_widget", "match": match})
    s["tClick"], s["after"] = now(), settle(gc, quiet)
    return bool(s["click"].get("ok"))
def direct_connect(b, gc, port):
    if not real_click(b, gc, "ServerList", "direct connect", "direct-connect"):
        return "no direct connect"
    wait_shown(gc, "DirectConnect", "join", 20)
    _st, ws = widgets(gc)
    edits = [w for w in ws if "TextEdit" in (w.get("type") or "")]
    if len(edits) < 2:
        return "fields-hidden"
    q(gc, {"cmd": "click_widget", "nth": ws.index(max(edits, key=lambda w: w.get("y")))})
    time.sleep(0.3)
    for k in [SDLK_END] + [SDLK_BACKSPACE] * 10 + [ord(c) for c in str(port)]:
        q(gc, {"cmd": "inject_input", "kind": "key", "key": k})
        time.sleep(0.06)
    time.sleep(0.3)
    q(gc, {"cmd": "inject_input", "kind": "key", "key": 13})  # Return
    time.sleep(0.4)
    return "joined" if real_click(b, gc, "DirectConnect", "join", "join", timeout=10, quiet=0.3) else "join not clicked"
def seed_player_name(user_dir):
    for d in (os.path.join(user_dir, "xcom1"), user_dir):
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "player_name.json"), "w", encoding="utf-8") as fh:
            json.dump({"name": NAME}, fh)
def watch_62(gc, timeout):
    end = time.time() + timeout
    while time.time() < end and alive(gc):
        if top(gc) == "CoopState" and dlg(gc).get("code") == 62:
            return {"t": now(), "title": dlg(gc).get("title")}
        time.sleep(0.05)
    return None
def trail_until(b, host, cl):
    """Profile OKs, the host's RESUME once its 62 shows resumeAck, until both tops BattlescapeState BOTH_S"""
    tr, resumed, both_since, out = time.time(), False, None, []
    while time.time() - tr < REJOIN_S and alive(host) and alive(cl):
        for gc in (host, cl):
            if top(gc) == "Profile" and (gc is host or dlg(cl).get("code") != 52):
                real_click(b, gc, "Profile", "ok", "profile-ok", timeout=5, quiet=0.3)
        hd, hs, cs, ack = dlg(host), stk(host), stk(cl), q(host, {"cmd": "get_coop"}).get("resumeAck")
        if not out or out[-1][1:] != [hs[-2:], hd.get("code"), cs[-2:], ack]:
            out.append([now(), hs[-2:], hd.get("code"), cs[-2:], ack])
        if not resumed and hd.get("code") == 62 and ack is True and hs[-1:] == ["CoopState"]:
            resumed = real_click(b, host, "CoopState", "resume", "host-resume", timeout=10, quiet=0.3)
        both = resumed and hs[-1:] == ["BattlescapeState"] and cs[-1:] == ["BattlescapeState"]
        both_since = (both_since or time.time()) if both else None
        if both_since and time.time() - both_since >= BOTH_S:
            return True, out
        time.sleep(0.15)
    return False, out
def ok_popups(b, gc, timeout):
    """real clicks down to the geoscape: DebriefingState OK, a CoopState's visible back button; until GeoscapeState calm 2 s"""
    clicks, end, calm = [], time.time() + timeout, None
    while time.time() < end and alive(gc):
        t, d = top(gc), dlg(gc)
        if t == "DebriefingState" or t == "CoopState" and d.get("backVisible") and d.get("backText"):
            m = "ok" if t == "DebriefingState" else d.get("backText")
            ok = real_click(b, gc, t, m, "%s-%s" % (gc.name, "debrief-ok" if t == "DebriefingState" else "coop-back"), timeout=10, quiet=1.0)
            clicks.append([t, m, b.steps[-1].get("tClick"), ok])
            calm = None
            continue
        calm = (calm or time.time()) if t == "GeoscapeState" else None
        if calm and time.time() - calm >= 2.0:
            break
        time.sleep(0.2)
    return clicks
def wait_until(pred, timeout, interval=0.2):
    end = time.time() + timeout
    while time.time() < end and not pred():
        time.sleep(interval)
    return pred()
def both_calm(host, cl, secs=2.0, timeout=20.0):
    end, since = time.time() + timeout, None
    while time.time() < end:
        since = (since or time.time()) if top(host) == "GeoscapeState" and top(cl) == "GeoscapeState" else None
        if since and time.time() - since >= secs:
            return True
        time.sleep(0.1)
    return False

# ----- boots and rows -----
class Boot:
    def __init__(self, tag, key):
        self.tag, self.key, self.steps, self.census, self.c2, self.killed = tag, key, [], [], None, False
        self.host = GameClient("host", None, make_user_dir("partner_mirror_%s_host" % tag))
        self.client = self.cur = GameClient("client", None, make_user_dir("partner_mirror_%s_client" % tag))
    def procs(self):
        return [g for g in (self.host, self.client, self.c2) if g is not None]
    def snap(self, label):
        s = {"label": label, "t": now()}
        for who, gc in (("host", self.host), (self.cur.name, self.cur)):
            s[who] = {"stack": stk(gc), "dlg": dlg(gc), "bases": bases(gc)} if alive(gc) else {"exited": gc.proc.poll()}
        self.census.append(s)
        return s
def capture(b):
    """every live machine's probes and log tail (the setup failure dump)"""
    out = {}
    for gc in b.procs():
        w = q(gc, {"cmd": "list_widgets"}) if alive(gc) else {}
        out[gc.name] = {"get_state": q(gc, {"cmd": "get_state"}), "get_coop": q(gc, {"cmd": "get_coop"}), "dialog": dlg(gc), "geo_state": bases(gc),
                        "widgets": [w.get("state")] + [[v.get("text"), v.get("visible"), v.get("hidden")] for v in w.get("widgets", []) if v.get("text")],
                        "log": [ln.split("\t")[-1][:300] for ln in logl(gc)[-15:]]} if alive(gc) else {"alive": False, "rc": gc.proc.poll() if gc.proc else None}
    return out
class Row:
    def __init__(self, x, b, rid):
        self.x, self.b, self.rid, self.res = x, b, rid, {}
        self.ev = {"t": now(), "cpu": cpu()}
        self.n0 = len(logl(b.host)) if b is not None else 0
    def cell(self, cid, ok, label):
        self.res[cid] = (bool(ok), label)
    def need(self, ok, what):
        if not ok:
            raise Stop(what)
    def finish(self, stop=None):
        self.ev["tEnd"] = now()
        if self.b is not None:
            self.ev.update({"steps": self.b.steps, "census": self.b.census, "hostLog": lines_since(self.b.host, self.n0)})
        if stop:
            self.ev["stop"] = stop
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        fails = []
        for cid in dict(ROWS)[self.rid]:
            ok, label = self.res.get(cid, (False, "not reached (%s)" % stop))
            print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, "FIX" if cid in FIX else "GUARD", label), flush=True)
            fails += [] if ok else [cid]
        if stop:
            print("CAPTURE %s: %s" % (self.rid, js(capture(self.b))), flush=True)
        print(("PASS %s" % self.rid) if not fails else ("FAIL %s: %s" % (self.rid, " ".join(fails))), flush=True)
        self.x.fails += fails
def rejoin_ordinary(b, r):
    """REJOIN(ordinary): kill the client, the host's 62 within DROP_S, client2 (the roster name) MainMenu NEW BATTLE > COOP"""
    b.client.proc.kill()
    b.killed, r.ev["kill"] = True, {"t": now(), "rc": b.client.proc.wait(timeout=15)}
    r.ev["host62"] = w = watch_62(b.host, DROP_S)
    r.need(w, "no host 62 within %.0f s of the kill" % DROP_S)
    b.c2 = b.cur = GameClient("client2", None, make_user_dir("partner_mirror_%s_client2" % b.tag))
    seed_player_name(b.c2.user_dir)
    b.c2.spawn()
    b.c2.connect()
    r.need(real_click(b, b.c2, "MainMenuState", "new battle", "new-battle") and real_click(b, b.c2, "NewBattleState", "coop", "coop"),
           "client2 NEW BATTLE > COOP not clicked")
    rejoin_join(b, r)
def rejoin_trap(b, r):
    """REJOIN(trap): the client's Escape > PauseState CO-OP > LobbyMenu DISCONNECT, its ServerList within TRAP_S, the host's 62"""
    r.ev["esc"] = q(b.cur, {"cmd": "inject_input", "kind": "key", "key": 27})
    settle(b.cur, 1.0)
    r.need(top(b.cur) == "PauseState", "Escape did not open PauseState: %s" % stk(b.cur))
    r.need(real_click(b, b.cur, "PauseState", "co-op", "co-op"), "PauseState CO-OP not clicked")
    r.need(top(b.cur) == "LobbyMenu" and real_click(b, b.cur, "LobbyMenu", "disconnect", "disconnect"),
           "no LobbyMenu DISCONNECT (top %s)" % top(b.cur))
    r.ev["serverList"] = wait_until(lambda: top(b.cur) == "ServerList", TRAP_S, 0.1) and now()
    r.need(r.ev["serverList"], "client top %s, not ServerList, %.0f s after DISCONNECT" % (top(b.cur), TRAP_S))
    r.ev["host62"] = w = watch_62(b.host, DROP_S)
    r.need(w, "no host 62 within %.0f s of the DISCONNECT" % DROP_S)
    rejoin_join(b, r)
def rejoin_join(b, r):
    """Direct Connect to the key's port, then the trail until both tops BattlescapeState BOTH_S within REJOIN_S"""
    b.snap("after the drop")
    r.ev["join"] = j = direct_connect(b, b.cur, harness._EPHEMERAL_COOP_PORTS.get(b.key))
    r.need(j == "joined", "direct connect: %s" % j)
    ok, r.ev["trail"] = trail_until(b, b.host, b.cur)
    b.snap("after the rejoin")
    r.need(ok, "not both BattlescapeState %.0f s within %.0f s of the join" % (BOTH_S, REJOIN_S))
def end_battle(b, r, first):
    """END(first): abort, the vote, the first machine's DebriefingState OK, OK_GAP_S, the other's; READ at T + READ_S"""
    host, cl = b.host, b.cur
    e = r.ev["end"] = {"first": first, "abort": q(host, {"cmd": "battle_action", "action": "abort"})}
    r.need(e["abort"].get("ok") and real_click(b, host, "AbortMissionState", "ok", "abort-ok", timeout=30, quiet=0.5), "abort / AbortMissionState OK")
    t1, v = time.time(), q(cl, {"cmd": "vote_state"})
    while time.time() - t1 < VOTE_S and not (v.get("active") and v.get("menuOpen")):
        time.sleep(0.1)
        v = q(cl, {"cmd": "vote_state"})
    v = e["voteState"] = {k: v.get(k) for k in ("active", "action", "menuOpen", "id")}
    if v.get("menuOpen") and real_click(b, cl, "VoteMenu", "yes", "vote-yes", timeout=VOTE_S, quiet=0.5):
        e["vote"] = "click"
    else:  # the VOTE rule: the helper's way, logged
        e["vote"] = ["vote_cast", q(cl, {"cmd": "vote_cast", "id": v.get("id"), "yes": True})]
    wait_until(lambda: top(host) == "DebriefingState", DEBRIEF_S)
    b.snap("host at its DebriefingState")
    r.need(top(host) == "DebriefingState", "no host DebriefingState within %.0f s" % DEBRIEF_S)
    fg, og = (host, cl) if first == "host" else (cl, host)
    r.need(wait_until(lambda: top(fg) == "DebriefingState" and top(og) == "DebriefingState", DEBRIEF_S),
           "not both on DebriefingState: %s / %s" % (stk(fg), stk(og)))
    e["firstOks"] = ok_popups(b, fg, 60)
    b.snap("after the first OK (%s)" % fg.name)
    r.need(top(og) == "DebriefingState", "the second machine not on its DebriefingState at the first OK: %s" % stk(og))
    t1 = next((c[2] for c in e["firstOks"] if c[0] == "DebriefingState" and c[3]), None)
    r.need(t1 is not None, "the first DebriefingState OK not clicked: %s" % e["firstOks"])
    time.sleep(max(0.0, T0[0] + t1 + OK_GAP_S - time.time()))
    e["otherOks"] = ok_popups(b, og, 90)
    t2 = next((c[2] for c in e["otherOks"] if c[0] == "DebriefingState" and c[3]), None)
    e["okGap"] = round(t2 - t1, 3) if t2 is not None else None
    b.snap("after the second OK (%s)" % og.name)
    r.need(t2 is not None, "the second DebriefingState OK not clicked: %s" % e["otherOks"])
    r.need(both_calm(host, cl), "not both GeoscapeState calm 2 s: %s / %s" % (stk(host), stk(cl)))
    e["T"] = now()
    time.sleep(READ_S)
    rd = b.snap("READ at T + %.0f s" % READ_S)
    return mir(rd["host"].get("bases")), mir(rd[cl.name].get("bases"))
def row_client_first(b, r):
    """client_first: REJOIN(ordinary); END(client); the client cells read client2"""
    rejoin_ordinary(b, r)
    return end_battle(b, r, "client")
def row_trap_rejoin(b, r):
    """trap_rejoin: REJOIN(trap); END(host); the client cells read the same client process"""
    rejoin_trap(b, r)
    return end_battle(b, r, "host")
def run_boot(x, tag, key, rid, row_fn, seed, last):
    b = x.boot = Boot(tag, key)
    ev, pre = {"boot": tag, "key": key, "seed": seed, "cpu": cpu(), "t": now()}, {}
    def PRE(h, c):
        pre["seed"], pre["hostBases"], pre["clientBases"] = h.ok({"cmd": "set_seed", "seed": seed}), bases(h), bases(c)
    try:
        seed_player_name(b.client.user_dir)
        for gc in (b.host, b.client):
            gc.spawn()
            gc.connect()
        session.bring_up_separate_guest_battle(b.host, b.client, port=key, pre_mission_start=PRE)
        ev["pre"], ev["tBattle"] = pre, now()
        oh, oc = own(pre["hostBases"]), own(pre["clientBases"])
        one = isinstance(oh, list) and len(oh) == 1 and isinstance(oc, list) and len(oc) == 1
        ok = one and oh[0][1] != oc[0][1]
        ev["HB"], ev["CB"] = (oh[0], oc[0]) if one else (oh, oc)
        if not ok:
            ev["error"] = "PRE base reads: own(host) %s, own(client) %s (one base each, HB != CB)" % (oh, oc)
            if one and not last:  # the HB / CB rule: HB == CB runs the boot once more on the next seed
                print("EVIDENCE boot %s: %s; HB == CB: once more on seed %d" % (tag, js(ev), seed + 1), flush=True)
                return "again"
    except Exception as e:  # noqa: BLE001 - a boot that raises is a boot miss
        ev["error"], ok = ("%s: %s" % (type(e).__name__, e))[:400], False
    print("EVIDENCE boot %s: %s" % (tag, js(ev)), flush=True)
    if not ok:
        print("CAPTURE boot %s: %s" % (tag, js(capture(b))), flush=True)
        for cid in dict(ROWS)[rid]:
            print("FAIL %s %s: boot" % (cid, "FIX" if cid in FIX else "GUARD"), flush=True)
            x.fails.append(cid)
        return "miss"
    hb, cb, r = ev["HB"], ev["CB"], Row(x, b, rid)
    try:
        mh, mc = row_fn(b, r)
        r.cell(rid + "-host_shows_partner", mh == [cb], "mir(host) at READ %s (want exactly [%s])" % (mh, cb))
        r.cell(rid + "-host_not_own", isinstance(mh, list) and all(m[1] != hb[1] for m in mh),
               "mir(host) %s; HB %s" % (mh, hb))
        r.cell(rid + "-client_shows_host", isinstance(mc, list) and hb in mc,
               "mir(%s) at READ %s (want %s in it)" % (b.cur.name, mc, hb))
        r.finish()
    except Stop as e:
        r.finish(str(e))
    except Exception as e:  # noqa: BLE001 - an unexpected exception ends the row like a precondition miss
        r.finish("exception %s: %s" % (type(e).__name__, str(e)[:300]))
    return "done"
def shut(x):
    for gc in x.boot.procs()[::-1] if x.boot else []:
        x.alive.append([x.boot.tag, gc.name, "killed by the row" if gc is x.boot.client and x.boot.killed else alive(gc)])
        try:
            if alive(gc):
                gc.shutdown(expected_returncodes=OKRC)
        except Exception as e:  # noqa: BLE001
            print("FAIL shutdown %s %s: %s" % (x.boot.tag, gc.name, str(e)[:300]), flush=True)
            x.alive[-1][2] = False
    x.boot = None
class X:  # the file's run state: failing cells, every process's alive-until-shutdown record, the live boot
    def __init__(self): self.fails, self.alive, self.boot = [], [], None
def main():
    x, crash0 = X(), crashes()
    T0[0] = time.time()
    try:
        for tag, key, rid, row_fn in BOOTS:
            for seed, last in ((SEED, False), (SEED + 1, True)):
                try:
                    again = run_boot(x, tag, key, rid, row_fn, seed, last)
                finally:
                    shut(x)
                if again != "again":
                    break
    finally:
        shut(x)
        r, new = Row(x, None, "END"), sorted(crashes() - crash0)
        r.ev.update({"newCrash": [os.path.basename(p) for p in new], "aliveUntilShutdown": x.alive})
        r.cell("CRASH", not new and x.alive and all(a[2] is not False for a in x.alive),
               "new crash files %d %s; alive until shutdown %s" % (len(new), r.ev["newCrash"][:3], x.alive))
        r.finish()
    cl = [c for _r, cs in ROWS for c in cs]
    print("SUMMARY test_host_partner_mirror_trap: %d/%d cells pass; failing %s; wall %.1f s" % (
        len(cl) - len(set(x.fails)), len(cl),
        sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2
if __name__ == "__main__":
    sys.exit(main())
