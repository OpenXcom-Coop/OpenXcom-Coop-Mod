"""W2-H25 - test_w2_leave_for_menu.py: the partner leaving while this machine is already leaving for the main menu opens
nothing over that exit (issue #79, D156 (a), D239 (a); trace F10500-F10512). Spec docs
rewrite/prompts/w2h25_gameover_lobby_race.md (f); TASK 0 constants docs rewrite/w2h25-task0/CONSTANTS.md.

Every row boots its own pair with test_w2_cydonia_ending's helpers, imported unchanged: boot_e (custom battle, Cydonia
landing, seed 1, pinned), ms8 into stage 2 (a precondition miss is FIXTURE-STOP), then abort_ok (AbortMissionState
"0 Units in Target Exit" -> loseGame, the game-ending slideshow on both machines). A SlideshowState on both within
SLIDESHOW_S is a guard. Both stacks are polled every POLL_S from the OK to the row's end ("no LobbyMenu at any poll").
A main-menu cell is a bare ['MainMenuState'] read that is still bare SETTLE_S later (every poll between, F10505). A
keyCancel is a real SDL key (inject_input key 27 -> SlideshowState::screenSkip).

  LM1  the partner leaves during the host's ending (C1, F10501). +SKIP_AT_S after the OK: client keyCancel. Cells: the
       client on a bare main menu; at +CHECK_AT_S the host's top is SlideshowState; no LobbyMenu on the host at any
       poll; the host log has the W2-H25 line naming GoToMainMenuState; then host keyCancel -> the host on a bare
       main menu; no new crash file; both alive.
  LM2  the frame before the host's MainMenuState::init (C1, F10502 = Integration 19's red). +SKIP_AT_S: host
       slow_top {type MainMenuState, ms 100, timeoutMs 20000}; host keyCancel; client keyCancel DELTA_S after the
       host's reply. Window-proof GUARD (FIXTURE-STOP if missed): the host log's W2-H25 line names MainMenuState, or
       (unfixed build) `push ... LobbyMenu depth=2` right after `push ... MainMenuState depth=1` with no
       `[coop-session] setRole -> None` between. Cells: no LobbyMenu on the host at any poll; host and client on a
       bare main menu; no new crash file; both alive. slow_top {off} at the row's end.
  LM3  control: the host leaves first (F10503). +SKIP_AT_S host keyCancel, +CLIENT_SKIP_S client keyCancel. Cells:
       both on a bare main menu; no LobbyMenu on either at any poll; the client log has no CoopState push.

RED on the unfixed build (TASK 0): LM1 (the host on [GoToMainMenuState, SlideshowState, LobbyMenu]) and LM2 (the host
on ['MainMenuState', 'LobbyMenu']) FAIL; LM3 PASSES.

Each row prints ONE "EVIDENCE <id>:" line before its verdict, then "PASS <id>" or "FAIL <id>: <cells>" and, on a FAIL,
ONE "CAPTURE <id>:" line. Every row runs after a failure. WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip
path; exit 0 only when every row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_leave_for_menu.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_w2_cydonia_ending as ce
from test_w2_multistage import FixtureMiss, short, rc, stack, evidence, wait_until

KEY_CANCEL = 27          # Options::keyCancel default (SDLK_ESCAPE)
SKIP_AT_S = 5.0          # the first keyCancel, s after the abort OK
CHECK_AT_S = 10.0        # LM1: the host's top read, s after the OK
CLIENT_SKIP_S = 10.0     # LM3: the client's keyCancel, s after the OK
DELTA_S = 0.125          # LM2: the client's keyCancel this long after the host's reply
SLIDE_MS, SLIDE_TIMEOUT_MS = 100, 20000
SLIDESHOW_S = 15         # the OK -> a SlideshowState on both (guard)
MENU_BOUND_S = 15        # the last keyCancel -> both settled on a bare main menu
SETTLE_S = 2.0
POLL_S = 0.1
BARE = ["MainMenuState"]
E3_LINE = "[coop] partner left while the host is leaving for the main menu ("
ROW_PORTS = {"LM1": (49686, 49687), "LM2": (49688, 49689), "LM3": (49690, 49691)}


def log_msgs(gc, since=0):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip("\n").split("\t")[-1] for ln in f]
    except OSError:
        return []
    return lines[since:]


def keep(lines):
    tags = ("[coop-ui]", "[coop-session]", "[coop] partner", "[coop] lobby", "W2-H25")
    return [ln for ln in lines if any(t in ln for t in tags) and "BattlescapeState" not in ln
            and "AbortMissionState" not in ln]


def key_cancel(gc):
    r = gc.cmd({"cmd": "inject_input", "kind": "key", "key": KEY_CANCEL})
    return r


class Watch:
    """Both stacks every POLL_S from the OK: transitions, the first LobbyMenu per machine, the bare-main-menu run."""

    def __init__(self, host, client, t0):
        self.m, self.t0 = (("host", host), ("client", client)), t0
        self.trans = {"host": [], "client": []}
        self.lobby, self.bare_since, self.last, self.n = {}, {}, {}, 0

    def t(self):
        return round(time.time() - self.t0, 2)

    def poll(self):
        for name, gc in self.m:
            st, t = stack(gc), self.t()
            self.last[name] = st
            if not self.trans[name] or self.trans[name][-1][1] != st:
                self.trans[name].append((t, st))
            if isinstance(st, list) and "LobbyMenu" in st:
                self.lobby.setdefault(name, t)
            if st == BARE:
                self.bare_since.setdefault(name, t)
            else:
                self.bare_since.pop(name, None)
        self.n += 1

    def until(self, t_rel):
        while True:
            self.poll()
            if time.time() - self.t0 >= t_rel:
                return
            time.sleep(max(0.0, min(POLL_S, self.t0 + t_rel - time.time())))

    def settled(self, name):
        return name in self.bare_since and self.t() - self.bare_since[name] >= SETTLE_S

    def until_settled(self, names, bound_rel):
        while True:
            self.poll()
            if all(self.settled(n) for n in names) or time.time() - self.t0 >= bound_rel:
                return {n: self.settled(n) for n in names}
            time.sleep(POLL_S)

    def view(self):
        return {"polls": self.n, "trans": self.trans, "lobbyAt": self.lobby, "bareSince": self.bare_since,
                "last": self.last}


def to_ending(host, client, rid, crash0):
    """Boot E, MS8 into stage 2, the abort OK, a SlideshowState on both. FixtureMiss on any miss."""
    ctx = {}
    try:
        ctx["boot"] = ce.boot_e(host, client)
    except FixtureMiss as e:
        raise FixtureMiss(f"boot E: {e}") from None
    f8 = ce.ms8(host, client, ctx, crash0)
    if f8:
        raise FixtureMiss(f"MS8 into stage 2: {f8}")
    for name, gc in (("host", host), ("client", client)):
        st = stack(gc)
        if not (isinstance(st, list) and st and st[-1] == "BattlescapeState"):
            raise FixtureMiss(f"{name} top is not BattlescapeState after MS8: {st}")
        if ce.bview(gc).get("missionType") != ce.MISSION_2:
            raise FixtureMiss(f"{name} missionType={ce.bview(gc).get('missionType')!r} (want {ce.MISSION_2!r})")
    ctx["marks"] = {"host": len(log_msgs(host)), "client": len(log_msgs(client))}
    g = ce.abort_ok(host, client, rid, ctx)
    if g:
        raise FixtureMiss(f"abort guard: {g}")
    ok, secs = wait_until(lambda: all("SlideshowState" in (stack(gc) or []) for gc in (host, client)), SLIDESHOW_S, 0.1)
    ctx["slideshowBothS"] = round(time.time() - ctx["t_ok"], 2)
    if not ok:
        raise FixtureMiss(f"no SlideshowState on both within {SLIDESHOW_S}s of the OK: host {stack(host)} "
                          f"client {stack(client)}")
    return ctx


def common_cells(host, client, w, crash0, ctx, names_settled):
    f = []
    for name in names_settled:
        if not w.settled(name):
            f.append(f"{name} not settled on a bare main menu ({SETTLE_S}s): last {w.last.get(name)}, "
                     f"bare since {w.bare_since.get(name)} at {w.t()}s")
    new_crash = sorted(os.path.basename(x) for x in session._crash_log_snapshot() - crash0)
    ctx["newCrashFiles"] = new_crash
    if new_crash:
        f.append(f"new crash file(s) {new_crash}")
    for name, gc in (("host", host), ("client", client)):
        if rc(gc) is not None:
            f.append(f"{name} process exited rc={rc(gc)}")
    return f


def lm1(host, client, crash0):
    ctx = to_ending(host, client, "LM1", crash0)
    w = Watch(host, client, ctx["t_ok"])
    f = []
    w.until(SKIP_AT_S)
    ctx["clientSkip"] = {"t": w.t(), "resp": key_cancel(client)}
    w.until(CHECK_AT_S)
    w.poll()
    ctx["hostAtCheck"] = {"t": w.t(), "stack": w.last.get("host")}
    hst = w.last.get("host")
    if not (isinstance(hst, list) and hst and hst[-1] == "SlideshowState"):
        f.append(f"host top at +{CHECK_AT_S}s is not SlideshowState: {hst}")
    hlog = log_msgs(host, ctx["marks"]["host"])
    e3 = [ln for ln in hlog if E3_LINE in ln]
    ctx["e3"] = e3
    if not any(E3_LINE + "GoToMainMenuState)" in ln for ln in e3):
        f.append(f"host log has no W2-H25 line naming GoToMainMenuState: {e3}")
    ctx["hostSkip"] = {"t": w.t(), "resp": key_cancel(host)}
    w.until_settled(["host", "client"], ctx["hostSkip"]["t"] + MENU_BOUND_S)
    if "host" in w.lobby:
        f.append(f"a LobbyMenu was on the host's stack at +{w.lobby['host']}s")
    f += common_cells(host, client, w, crash0, ctx, ["client", "host"])
    evidence("LM1", {"boot": ctx.get("boot"), "slideshowBothS": ctx.get("slideshowBothS"),
                     "clientSkip": ctx.get("clientSkip"), "hostAtCheck": ctx.get("hostAtCheck"), "e3": e3,
                     "hostSkip": ctx.get("hostSkip"), "watch": w.view(), "newCrashFiles": ctx.get("newCrashFiles"),
                     "hostLog": keep(log_msgs(host, ctx["marks"]["host"])),
                     "clientLog": keep(log_msgs(client, ctx["marks"]["client"]))})
    return f


def red_window_sig(lines):
    """The unfixed build's LM2 shape: `push ... LobbyMenu depth=2` whose previous push/pop line is
    `push ... MainMenuState depth=1`, with no `[coop-session] setRole -> None` between them."""
    for i, ln in enumerate(lines):
        if not ln.startswith("[coop-ui] push class OpenXcom::LobbyMenu depth=2"):
            continue
        j, between = i - 1, []
        while j >= 0 and not (lines[j].startswith("[coop-ui] push ") or lines[j].startswith("[coop-ui] pop ")):
            between.append(lines[j])
            j -= 1
        if j >= 0 and lines[j].startswith("[coop-ui] push class OpenXcom::MainMenuState depth=1") \
                and not any("[coop-session] setRole -> None" in b for b in between):
            return True
    return False


def lm2(host, client, crash0):
    ctx = to_ending(host, client, "LM2", crash0)
    w = Watch(host, client, ctx["t_ok"])
    f = []
    try:
        w.until(SKIP_AT_S)
        slow = host.cmd({"cmd": "slow_top", "type": "MainMenuState", "ms": SLIDE_MS, "timeoutMs": SLIDE_TIMEOUT_MS})
        ctx["slow"] = slow
        if not (slow.get("ok") and (slow.get("slow") or {}).get("armed")):
            raise FixtureMiss(f"slow_top answered {slow}")
        rh = key_cancel(host)
        th = time.time()
        time.sleep(max(0.0, th + DELTA_S - time.time()))
        rcl = key_cancel(client)
        tc = time.time()
        ctx["skip"] = {"host": round(th - ctx["t_ok"], 3), "client": round(tc - ctx["t_ok"], 3),
                       "deltaS": round(tc - th, 3), "resp": [rh, rcl]}
        w.until_settled(["host", "client"], tc - ctx["t_ok"] + MENU_BOUND_S)
        hlog = log_msgs(host, ctx["marks"]["host"])
        e3 = [ln for ln in hlog if E3_LINE in ln]
        green_win = any(E3_LINE + "MainMenuState)" in ln for ln in e3)
        red_win = red_window_sig(hlog)
        ctx["window"] = {"e3": e3, "greenNamesMainMenuState": green_win, "redSignature": red_win}
        if not (green_win or red_win):
            f.append("FIXTURE-STOP window-proof guard missed: no W2-H25 line naming MainMenuState and no "
                     "LobbyMenu push right after the un-init'd MainMenuState push")
        if "host" in w.lobby:
            f.append(f"a LobbyMenu was on the host's stack at +{w.lobby['host']}s")
        f += common_cells(host, client, w, crash0, ctx, ["host", "client"])
    finally:
        try:
            ctx["slowOff"] = host.cmd({"cmd": "slow_top", "off": True}).get("slow")
        except Exception as e:
            ctx["slowOff"] = short(e)
    evidence("LM2", {"boot": ctx.get("boot"), "slideshowBothS": ctx.get("slideshowBothS"), "slow": ctx.get("slow"),
                     "skip": ctx.get("skip"), "window": ctx.get("window"), "slowOff": ctx.get("slowOff"),
                     "watch": w.view(), "newCrashFiles": ctx.get("newCrashFiles"),
                     "hostLog": keep(log_msgs(host, ctx["marks"]["host"])),
                     "clientLog": keep(log_msgs(client, ctx["marks"]["client"]))})
    return f


def lm3(host, client, crash0):
    ctx = to_ending(host, client, "LM3", crash0)
    w = Watch(host, client, ctx["t_ok"])
    f = []
    w.until(SKIP_AT_S)
    ctx["hostSkip"] = {"t": w.t(), "resp": key_cancel(host)}
    w.until(CLIENT_SKIP_S)
    ctx["clientSkip"] = {"t": w.t(), "resp": key_cancel(client)}
    w.until_settled(["host", "client"], ctx["clientSkip"]["t"] + MENU_BOUND_S)
    for name in ("host", "client"):
        if name in w.lobby:
            f.append(f"a LobbyMenu was on the {name}'s stack at +{w.lobby[name]}s")
    clog = log_msgs(client, ctx["marks"]["client"])
    pushes = [ln for ln in clog if ln.startswith("[coop-ui] push class OpenXcom::CoopState")]
    if pushes:
        f.append(f"the client log has CoopState push(es): {pushes}")
    f += common_cells(host, client, w, crash0, ctx, ["host", "client"])
    evidence("LM3", {"boot": ctx.get("boot"), "slideshowBothS": ctx.get("slideshowBothS"),
                     "hostSkip": ctx.get("hostSkip"), "clientSkip": ctx.get("clientSkip"),
                     "clientCoopStatePushes": pushes, "watch": w.view(), "newCrashFiles": ctx.get("newCrashFiles"),
                     "hostLog": keep(log_msgs(host, ctx["marks"]["host"])), "clientLog": keep(clog)})
    return f


ROWS = (("LM1", lm1), ("LM2", lm2), ("LM3", lm3))


def capture(rid, machines, why):
    cap = {}
    for gc in machines:
        cap[gc.name] = {"rc": rc(gc), "stack": stack(gc), "log": keep(log_msgs(gc))[-16:]}
    print(f"CAPTURE {rid} ({why}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def run_row(rid, fn):
    """One row on its own pair. True when it passes."""
    ports = ROW_PORTS[rid]
    host = GameClient("host", ports[0], make_user_dir(f"w2h25_{rid.lower()}_host"))
    client = GameClient("client", ports[1], make_user_dir(f"w2h25_{rid.lower()}_client"))
    crash0 = session._crash_log_snapshot()
    try:
        try:
            fails = fn(host, client, crash0)
        except FixtureMiss as e:
            print(f"EVIDENCE {rid}: {json.dumps({'fixture': short(e, 800)})}", flush=True)
            fails = [f"FIXTURE-STOP {short(e, 800)}"]
        except Exception as e:
            print(f"EVIDENCE {rid}: {json.dumps({'error': short(e, 800)})}", flush=True)
            fails = [short(e, 800)]
        if fails:
            print(f"FAIL {rid}: {len(fails)} cell(s): " + " | ".join(fails), flush=True)
            capture(rid, [host, client], "row failed")
        else:
            print(f"PASS {rid}", flush=True)
        return not fails
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2h25] shutdown {gc.name}: {short(e)}", flush=True)


def main():
    t0 = time.time()
    results = {rid: run_row(rid, fn) for rid, fn in ROWS}
    order = [rid for rid, _fn in ROWS]
    passed = [r for r in order if results.get(r)]
    failed = [r for r in order if not results.get(r)]
    print(f"\ntest_w2_leave_for_menu: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
