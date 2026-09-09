"""Reusable geoscape driving helpers for coop tests.

Built on the TestServer commands get_state, get_coop, geo_state, geo_set_speed
and dismiss_popup. Every test (present or future) can import these to:

  * wait_both_ready(...)   - gate until both players are settled on the geoscape
                             (kills the post-load idle window before driving).
  * skip_realtime(...)     - let N real seconds pass while advancing time and
                             auto-closing any dialogs; optionally stop early on
                             an event of interest.
  * skip_ingame_time(...)  - same, but bounded by in-game minutes instead of
                             wall-clock.
  * slow_clock(...)        - drop both clocks to the 5-second step, so a test can
                             seed state and read baselines without the sim (which
                             keeps running at whatever speed the last skip left)
                             advancing whole game days underneath it.

The two skip helpers take an optional `interest` predicate so they stop as soon
as something you care about happens (e.g. a mission site appears) instead of
blindly skipping everything. Build one with popup(...) or geo_when(...), or pass
any callable(GameClient) -> truthy|None.
"""

import time

_GEO = "GeoscapeState"

# WV-D107: wait out a self-closing coop dialog (host-save wait / VoteMenu refusal)
# rather than abandoning the machine's pass at it. STALL_S bounds ONE such wait.
STALL_S = 3.0        # per-dialog ceiling (clears the measured 1.105s host-save max)
STALL_POLL = 0.1     # poll interval while waiting a refused dialog out


class StuckDialogError(RuntimeError):
    """Raised when an advance stalls: in-game time stops moving because a dialog
    can't be cleared (or re-pushes itself every frame). Carries the top state on
    each side so the offending dialog can be given explicit handling."""


class TimeWatchdog:
    """Guards a time-advance loop. Call tick(clock) every iteration with a
    monotonic in-game clock value; if it doesn't change for `timeout` real
    seconds, the advance is stuck. On stall it KILLS the given clients (so no
    hung game windows linger) and raises StuckDialogError with diagnostics."""

    def __init__(self, clients, timeout=20.0):
        self.clients = list(clients)
        self.timeout = timeout
        self._last = object()      # sentinel != any real clock value
        self._changed_at = time.time()

    def tick(self, clock):
        now = time.time()
        if clock != self._last:
            self._last = clock
            self._changed_at = now
            return
        if now - self._changed_at > self.timeout:
            diag = {gc.name: top_state(gc) for gc in self.clients}
            for gc in self.clients:
                try:
                    gc.proc.kill()
                except Exception:
                    pass
            raise StuckDialogError(
                f"in-game time stalled >{self.timeout}s at clock={clock!r}; "
                f"killed sessions. Top states: {diag} - add explicit dismiss_popup "
                f"handling for whichever is not a GeoscapeState/WAIT dialog.")


# --- state introspection ---------------------------------------------------

def top_state(gc):
    """Typeid name of the active (top) state, or '' if the stack is empty."""
    st = gc.cmd({"cmd": "get_state"}).get("states", [])
    return st[-1] if st else ""


def on_geoscape(gc):
    """True if the geoscape is the active state (no modal popup on top)."""
    return top_state(gc).endswith(_GEO)


def both_ready(host, client):
    """True if BOTH instances are on a live coop geoscape with no popup on top."""
    for gc in (host, client):
        co = gc.cmd({"cmd": "get_coop"})
        if not (co.get("coopStatic") and co.get("lobbyClosed") and co.get("hasSave")):
            return False
        if not on_geoscape(gc):
            return False
    return True


# --- interest predicates ---------------------------------------------------
# An `interest` is any callable(GameClient) -> truthy|None. It returns a marker
# (anything truthy) when the thing you're watching for has happened, else None.

def popup(*typeid_substrs):
    """Interest predicate: fires when the top state's typeid contains any of the
    given substrings, e.g. popup('MissionDetectedState', 'GeoscapeEventState').
    Carries its substrings as `.keep` so drain_popups can hand them to the game's
    dismiss_popup, which then checks-and-pops ATOMICALLY (SPEC RW-S3 / WV-D101)."""
    def _p(gc):
        t = top_state(gc)
        return t if any(s in t for s in typeid_substrs) else None
    _p.keep = tuple(typeid_substrs)
    return _p


def geo_when(pred):
    """Interest predicate over the geo_state snapshot: fires when pred(geo)
    is truthy, e.g. geo_when(lambda g: any(u['detected'] for u in g['ufos']))."""
    def _p(gc):
        g = gc.cmd({"cmd": "geo_state"})
        if not g.get("ok"):
            return None
        return pred(g) or None
    return _p


# --- dialog draining -------------------------------------------------------

def _walk(gc, interest=None, keep=None, limit=25, stalled=None):
    """ONE pass of the stack walk on ONE machine (SPEC RW-SETTLE (b) step 1).

    Reads the WHOLE state stack, pops unwanted windows from the top with the atomic
    keep list (WV-D103) until a wanted window or the geoscape is on top. Returns
    (dismissed, hit, on_geoscape):
      dismissed - the typeids this pass popped, in order
      hit       - the wanted marker if one is on top here, else None
      on_geoscape - True only if the walk ended with the geoscape (or an empty
                    stack) on top; False if it ended on a wanted window, on a
                    window the game will not close, or at the limit.
    `interest` is a callable(gc) predicate (its `.keep` is handed to dismiss_popup);
    `keep` is a bare list of typeid substrings, used when there is no callable.
    """
    dismissed = []
    for _ in range(limit):
        if interest is not None:
            h = interest(gc)
            if h:
                return dismissed, h, False
        st = gc.cmd({"cmd": "get_state"}).get("states", [])
        top = st[-1] if st else ""
        if interest is None and keep and any(s in top for s in keep):
            return dismissed, top, False
        if not top or top.endswith(_GEO):
            return dismissed, None, True
        req = {"cmd": "dismiss_popup"}
        k = keep if keep is not None else getattr(interest, "keep", None)
        if k:
            req["keep"] = list(k)
        r = gc.cmd(req)
        if r.get("kept"):
            return dismissed, r.get("type", top), False
        if r.get("wait"):
            # WV-D107: the game refused this dialog as self-closing (host-save wait,
            # or a VoteMenu). Poll it out, then RESUME the walk from step 1. On the
            # STALL_S ceiling give up this pass with no hit, and identify the dialog.
            t_wait = time.time()
            gone = False
            while time.time() - t_wait < STALL_S:
                time.sleep(STALL_POLL)
                st2 = gc.cmd({"cmd": "get_state"}).get("states", [])
                if (st2[-1] if st2 else "") != top:
                    gone = True
                    break
            if gone:
                dismissed.append("waited:" + str(top).split("::")[-1])
                continue
            info = gc.cmd({"cmd": "coop_dialog_info"})
            if stalled is not None:
                stalled[gc.name] = {
                    "type": str(top).split("::")[-1],
                    "error": r.get("error"),
                    "code": info.get("code"),
                    "title": info.get("title"),
                    "backText": info.get("backText"),
                    "waited_s": round(time.time() - t_wait, 3),
                }
            return dismissed, None, False
        if not r.get("ok"):
            return dismissed, None, False   # undismissable, no wait flag - caller retries
        dismissed.append(r.get("handled", r.get("type", top)))
    return dismissed, None, False


def drain_popups(gc, interest=None, limit=25):
    """Close every dismissable popup stacked above the geoscape on `gc` (via the
    dismiss_popup command, which knows Geoscape/Event/MonthlyReport/Mission/
    NextTurn/Abort/Debriefing dialogs). Stops early and returns a hit if
    `interest` fires (the interesting popup is left OPEN). Popups dismiss_popup
    can't close (e.g. a CoopState WAIT dialog, which auto-closes on its own) end
    the drain with no hit so the caller just waits and retries.

    Returns (dismissed: list[str], hit).
    """
    dismissed, hit, _on_geo = _walk(gc, interest=interest, limit=limit)
    return dismissed, hit


# --- readiness gate --------------------------------------------------------

def wait_both_ready(host, client, timeout=90, interval=0.5):
    """Block until both players are settled on the coop geoscape (session live,
    no CoopState WAIT / map-download dialog on top). Call this right after the
    session comes up so a test starts driving immediately instead of sitting
    idle. Returns elapsed seconds; raises TimeoutError with the blocking state."""
    t0 = time.time()
    deadline = t0 + timeout
    while time.time() < deadline:
        if both_ready(host, client):
            return round(time.time() - t0, 1)
        time.sleep(interval)
    blocking = {gc.name: top_state(gc) for gc in (host, client)}
    raise TimeoutError(f"players not ready on geoscape after {timeout}s: {blocking}")


# --- time skipping ---------------------------------------------------------

def _apply_speed(host, client, speed_idx):
    # Coop only advances fast when BOTH players pick the SAME speed, so (re)apply
    # it to both every step (a dismissed dialog can reset the selection).
    for gc in (host, client):
        if on_geoscape(gc):
            gc.cmd({"cmd": "geo_set_speed", "idx": speed_idx})


def slow_clock(host, client, settle=0.3):
    """Drop BOTH clocks to the 5-second step (speed idx 0) and let the in-flight
    tick land, i.e. "stop the world" for a test's setup window.

    Why every seed-then-observe step needs this: the geoscape timer fires every
    geoClockSpeed=80ms, and at speed 5 one tick advances a whole GAME DAY (24
    hourly sim steps). Nothing pauses time when skip_ingame_time()/skip_realtime()
    return, so a test that afterwards seeds state and reads a baseline is racing a
    sim that runs ~6 game days per 0.5s poll: a production seeded one hour short of
    completion can finish BETWEEN the host and client baseline reads, and then the
    "+1 on both" expectation is unreachable (the replica's baseline already counts
    the delivered item).

    At speed 0 a game hour takes ~58 real seconds, so no hourly step (production,
    transfers, craft maintenance) can fire inside a sub-second setup sequence.
    Call it BEFORE the setup, then let the next skip_* re-apply the fast speed."""
    _apply_speed(host, client, 0)
    time.sleep(settle)
    _apply_speed(host, client, 0)


def _step_dialogs(host, client, interest, do_dismiss, dismissed):
    """One pass of interest-check + popup drain across BOTH instances. Returns
    the (name, marker) hit or None. The pass never returns early: a machine
    whose interest fires is the hit and is left alone; the OTHER machine is
    still drained (with the same keep list) before the hit is returned, so a
    popup on the peer's top can never freeze it behind the caller's back
    (SPEC RW-S3b / S3b TRACE: a top popup stops both the geoscape clock and the
    popup queue on that machine - Game::run thinks the top state only)."""
    hit = None
    for gc in (host, client):
        if interest is not None:
            h = interest(gc)
            if h:
                if hit is None:
                    hit = (gc.name, h)
                continue          # the wanted popup is on top here: do not drain it
        if do_dismiss:
            d, h, _on_geo = _walk(gc, interest=interest)
            dismissed[gc.name] += d
            if h and hit is None:
                hit = (gc.name, h)
    return hit


def _abs_minutes(ts):
    # Monotonic-enough minute counter for deltas. Uses 31-day months, so a delta
    # that crosses a month boundary is approximate; within a month it is exact.
    return ((((ts["year"] * 12 + ts["month"]) * 31 + ts["day"]) * 24
             + ts["hour"]) * 60 + ts["minute"])


def game_minutes(gc):
    """The instance's current in-game clock as an absolute minute count, or None."""
    g = gc.cmd({"cmd": "geo_state"})
    if not g.get("ok") or "time" not in g:
        return None
    return _abs_minutes(g["time"])


# --- the coop-ui record reader (WV-D109 / D110/111/112) ------------------------
# Each instance logs every screen it pushes/pops to <user_dir>/openxcom.log as
#   [ts]\t[INFO]\t[coop-ui] push class OpenXcom::<Type> depth=N
#   [ts]\t[INFO]\t[coop-ui] pop  class OpenXcom::<Type> depth=N   (two spaces)
# settle reads it to learn what appeared during the sweep that a stack poll missed.

class RecordGap(RuntimeError):
    """Raised when the [coop-ui] record cannot be reconciled (two consecutive
    events whose depths do not differ by exactly one, or a pop whose type is not
    the type then on top). A gap means a lost record: never silently skipped."""


def _log_path(gc):
    import os
    return os.path.join(gc.user_dir, "openxcom.log")


def _log_cursor(gc):
    """Byte offset of the END of the instance's log NOW, to bracket a sweep.
    WV-D110: shared read, no lock. Missing file -> 0."""
    import os
    try:
        return os.path.getsize(_log_path(gc))
    except OSError:
        return 0


def _read_coop_ui(gc, cursor):
    """Post-cursor [coop-ui] events as (op, short_type, depth) and the new cursor.
    op is 'push'|'pop'; short_type is the typeid tail (e.g. 'CoopState')."""
    path = _log_path(gc)
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            f.seek(cursor)
            text = f.read()
            newcur = f.tell()
    except OSError:
        return [], cursor
    events = []
    for ln in text.splitlines():
        i = ln.find("[coop-ui] ")
        if i < 0:
            continue
        rest = ln[i + len("[coop-ui] "):]
        if rest.startswith("push "):
            op, body = "push", rest[len("push "):]
        elif rest.startswith("pop "):
            op, body = "pop", rest[len("pop "):].lstrip()
        else:
            continue
        j = body.rfind(" depth=")
        if j < 0:
            continue
        typ = body[:j].strip().split("::")[-1]
        try:
            depth = int(body[j + len(" depth="):].strip())
        except ValueError:
            continue
        events.append((op, typ, depth))
    return events, newcur


def _reconstruct(events):
    """Replay post-cursor events. The window may begin MID-stack (F95), so absolute
    depth is NOT assumed; only the RELATIVE step is checked: consecutive events
    must differ by exactly +/-1 (push/pop are the only stack ops and both log), and
    a pop's type must match the most-recent still-open push of that type. Returns
    (open_types, transient_closed):
      open_types       - types pushed since the cursor and not yet popped (push order)
      transient_closed - types pushed AND popped since the cursor (appeared+self-closed)
    Raises RecordGap on an unreconcilable record."""
    open_stack = []
    transient = []
    prev_depth = None
    for idx, (op, typ, depth) in enumerate(events):
        if prev_depth is not None:
            expect = prev_depth + (1 if op == "push" else -1)
            if depth != expect:
                raise RecordGap("depth gap at event %d: %s %s depth=%d expected %d"
                                % (idx, op, typ, depth, expect))
        if op == "push":
            open_stack.append(typ)
        else:  # pop
            hit_k = None
            for k in range(len(open_stack) - 1, -1, -1):
                if open_stack[k] == typ:
                    hit_k = k
                    break
            if hit_k is not None:
                del open_stack[hit_k]
                transient.append(typ)
            # a pop of a type pushed before the cursor lowers the pre-cursor
            # baseline only; nothing to record.
        prev_depth = depth
    return open_stack, transient


def settle(host, client, keep=None, speed_idx=0, cursors=None, limit=25):
    """SPEC RW-SETTLE + REV E.44 / WV-D105/107/108/109: leave BOTH machines in a
    KNOWN state, and judge "what appeared during the sweep" from the RECORD, not a
    stack poll.

    1. Walk the whole stack on host then client: pop what nobody wants (atomic keep
       list); WAIT OUT a dialog the game refuses as self-closing (WV-D107); note
       what someone wants.
    2. Set `speed_idx` on every machine whose top is now the geoscape.
    3. WV-D108: read the selected speed back once (geo_state.timeSpeedIndex) and
       assert it == speed_idx. No sleep, no clock band.
    4. DETECTION (WV-D109): read each machine's post-cursor [coop-ui] record. A
       transient (push+pop since the cursor) unwanted dialog self-closed -> do
       NOTHING. An unwanted dialog STILL OPEN at the record tail (the walk raced it)
       -> one more sweep pass to dismiss it.

    `cursors` brackets the window the record is read over: pass {name: byte-offset}
    captured BEFORE the sweep (skip_* does this); None = capture at settle entry
    (a direct caller with no prior sweep).

    Returns {"hit": (machine, marker)|None, "dismissed": {machine:[...]},
             "stalled": {machine:{...}}, "speed": {machine:(requested,observed)},
             "record": {machine:{"open":[...], "transient":[...], "n":int}}}.
    """
    if cursors is None:
        cursors = {gc.name: _log_cursor(gc) for gc in (host, client)}
    dismissed = {host.name: [], client.name: []}
    stalled = {}
    hit = None
    geo_top = {}
    for gc in (host, client):
        d, h, on_geo = _walk(gc, keep=keep, limit=limit, stalled=stalled)
        dismissed[gc.name] += d
        geo_top[gc.name] = on_geo
        if h and hit is None:
            hit = (gc.name, h)

    if speed_idx is not None:
        for gc in (host, client):
            if geo_top[gc.name]:
                gc.cmd({"cmd": "geo_set_speed", "idx": speed_idx})

    speed = {}
    if speed_idx is not None:
        for gc in (host, client):
            if geo_top[gc.name]:
                observed = gc.cmd({"cmd": "geo_state"}).get("timeSpeedIndex")
                speed[gc.name] = (speed_idx, observed)
                if observed != speed_idx:
                    raise AssertionError(
                        "settle: clock speed did not take on %s: want %d got %r"
                        % (gc.name, speed_idx, observed))

    record = {}
    for gc in (host, client):
        events, _ = _read_coop_ui(gc, cursors[gc.name])
        open_stack, transient = _reconstruct(events)
        open_unwanted = [t for t in open_stack
                         if not t.endswith(_GEO)
                         and not (keep and any(s in t for s in keep))]
        if open_unwanted:
            # the walk left this machine settled but the record shows an unwanted
            # window still open (it landed after the walk's last poll): one more pass
            d, h, on_geo = _walk(gc, keep=keep, limit=limit, stalled=stalled)
            dismissed[gc.name] += d
            geo_top[gc.name] = on_geo
            if h and hit is None:
                hit = (gc.name, h)
            events, _ = _read_coop_ui(gc, cursors[gc.name])
            open_stack, transient = _reconstruct(events)
        record[gc.name] = {"open": open_stack, "transient": transient, "n": len(events)}

    return {"hit": hit, "dismissed": dismissed, "stalled": stalled,
            "speed": speed, "record": record}


def skip_realtime(host, client, seconds, speed_idx=5, interest=None,
                  dismiss=True, poll=0.5, stuck_timeout=20.0, settle_speed=0):
    """Let `seconds` of real time pass while both instances advance on the
    geoscape at time speed `speed_idx` (0=5s .. 5=1day; default 5) and any
    dialogs that pop are auto-closed. If `interest` is given, stop the moment it
    fires on either side (leaving the triggering popup open) and return.

    A watchdog kills the sessions and raises StuckDialogError if the host clock
    stalls for `stuck_timeout` real seconds (a dialog that can't be cleared);
    pass stuck_timeout=None to disable.

    `settle_speed`: speed both clocks are left at when this returns (default 0 =
    stopped); pass 5 if your test needs the clock still running afterwards.

    Returns {'elapsed', 'dismissed': {name: [...]}, 'hit': (name, marker)|None,
    'settled', 'speed': {name:(requested,observed)}, 'record': {...}, 'stalled': {...}}.
    """
    dismissed = {host.name: [], client.name: []}
    hit = None
    wd = TimeWatchdog([host, client], stuck_timeout) if stuck_timeout else None
    cursors = {gc.name: _log_cursor(gc) for gc in (host, client)}
    t0 = time.time()
    t_end = t0 + seconds
    while time.time() < t_end:
        hit = _step_dialogs(host, client, interest, dismiss, dismissed)
        if hit:
            break
        _apply_speed(host, client, speed_idx)
        if wd:
            wd.tick(game_minutes(host))
        time.sleep(poll)
    _settled = settle(host, client, keep=getattr(interest, "keep", None),
                      speed_idx=settle_speed, cursors=cursors)
    for _name, _d in _settled["dismissed"].items():
        dismissed[_name] += _d
    return {"elapsed": round(time.time() - t0, 1), "dismissed": dismissed, "hit": hit,
            "settled": _settled, "speed": _settled["speed"], "record": _settled["record"],
            "stalled": _settled["stalled"]}


def skip_ingame_time(host, client, minutes, speed_idx=5, interest=None,
                     dismiss=True, poll=0.5, real_timeout=None, stuck_timeout=20.0,
                     settle_speed=0):
    """Advance until the host geoscape clock moves forward `minutes` in-game
    minutes (or `interest` fires), auto-closing dialogs on both. Same speed/coop
    rules as skip_realtime. `real_timeout` bounds wall-clock seconds (default
    max(30, minutes*3)) as a safety net; a watchdog kills the sessions and raises
    StuckDialogError if the clock stalls for `stuck_timeout` real seconds.

    `settle_speed`: speed both clocks are left at when this returns (default 0 =
    stopped); pass 5 if your test needs the clock still running afterwards.

    Returns {'game_minutes', 'target', 'dismissed', 'hit', 'timed_out',
    'settled', 'speed': {name:(requested,observed)}, 'record': {...}, 'stalled': {...}}.
    """
    dismissed = {host.name: [], client.name: []}
    hit = None
    wd = TimeWatchdog([host, client], stuck_timeout) if stuck_timeout else None
    cursors = {gc.name: _log_cursor(gc) for gc in (host, client)}
    start = _abs_minutes(host.cmd({"cmd": "geo_state"})["time"])
    now = start
    target = start + minutes
    real_deadline = time.time() + (real_timeout if real_timeout else max(30, minutes * 3))
    while now < target and time.time() < real_deadline:
        hit = _step_dialogs(host, client, interest, dismiss, dismissed)
        if hit:
            break
        _apply_speed(host, client, speed_idx)
        g = host.cmd({"cmd": "geo_state"})
        if g.get("ok") and "time" in g:
            now = _abs_minutes(g["time"])
        if wd:
            wd.tick(now)
        time.sleep(poll)
    _settled = settle(host, client, keep=getattr(interest, "keep", None),
                      speed_idx=settle_speed, cursors=cursors)
    for _name, _d in _settled["dismissed"].items():
        dismissed[_name] += _d
    return {"game_minutes": now - start, "target": minutes, "dismissed": dismissed,
            "hit": hit, "timed_out": (now < target and hit is None),
            "settled": _settled, "speed": _settled["speed"], "record": _settled["record"],
            "stalled": _settled["stalled"]}
