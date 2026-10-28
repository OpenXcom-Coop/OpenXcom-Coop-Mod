"""Shared helpers of the W2-H70 S-C tests (spec docs rewrite/prompts/w2h70_sc_window_67.md (f) and Appendix B; TASK 0
rewrite/w2h70-task0/sc/CONSTANTS.md; lead L-H70-2, ruling R-H70-4; F20441-F20448): the 67 window, the second host save, the host's
visit of the client base, the base-screen steps, the leave, the probes and the row runner that test_visit_window_67.py (rows R11,
G11, R12) and test_visit_window_67_edits.py (rows R13, R14, R15) import (R-H70-2: one non-test module). Built on
gift_helpers.py (GH: boot, stage_guest, picker, visit, baseline, trigger54, host_cancel, real_click, the probes; imported,
unchanged); the window, second-save, watch, leave, crew, MOVE and host-picker steps are copied from the capture rewrite/lh70-2-cap/cap.py
(CAP70, never imported). Every press is real (click_widget on visible text, inject_input at a TextList pixel times the clicking
machine's scale); the one lever is R15's rename_soldier. A construction step that misses its precondition raises Stop (its
row ends there, later cells "not reached"); the steps after a row's last precondition only record and never press a 53 / 995 /
Disconnect control. No reload, no rejoin. one foreground run per invocation; exit 0 only when
every cell passes, else 2."""
import json, os, sys, time  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
from gift_helpers import *  # noqa: E402,F401,F403 (GH, R-H70-2)

HOLD_P, HOLD_W, HOLD_V, HOLD_L, W_CONTRIB = 1.5, 3.0, 2.0, 2.0, 10.0
RENAMES = ("Zzz Renamed", "Zzz Renamed2")
SUBS = ("SoldiersState", "SoldierInfoState", "CraftSoldiersState", "CraftInfoState", "CraftsState")
LAST = {}  # the last row's evidence (a TASK 0 script reads it)

def code(gc, st=None):
    """the top dialog's CoopState code; None when the top is not a CoopState"""
    st = stack(gc) if st is None else st
    return dlg(gc).get("code") if st[-1:] == ["CoopState"] else None

def fnvb(gc):
    """the client's "basehost" blob (its parked own world during a visit): fnv1a64"""
    return q(gc, {"cmd": "coop_file_info", "key": "basehost"}).get("fnv1a64")

def has_key(gc, k):
    return bool(k) and q(gc, {"cmd": "coop_file_info", "key": k}).get("present") is True

def ids(x):
    """both machines' saveID [host, client] (T0-S, F20445)"""
    return [coop(x.host).get("saveID"), coop(x.client).get("saveID")]

def snap(x):
    """one record: time, both stacks and top codes, both saveIDs, the client's flag, its "basehost" fnv, role own_world [key,
    present], K0 by key; the host's stored partner world (fnv)"""
    h, c = x.host, x.client
    sh, sc = stack(h), stack(c)
    ch, cc = coop(h), coop(c)
    ow = q(c, {"cmd": "coop_file_info", "role": "own_world"})
    return {"t": round(time.time() - x.t0, 2), "stack": [sh, sc], "code": [code(h, sh), code(c, sc)], "saveID": [ch.get("saveID"),
            cc.get("saveID")], "inside": cc.get("insideCoopBase"), "basehost": fnvb(c), "own": [ow.get("key"), ow.get("present")],
            "K0": has_key(c, x.K0), "hostCopy": (blob(h) or {}).get("fnv1a64")}

def where(gc, name=None, gid=None):
    """[base, own / coop, id, name, coopBase, craft] of every live-world soldier named name (or with id gid) (CAP70 guest_where)"""
    return [[b.get("name"), "coop" if (b.get("coopBaseFlag") or b.get("coopIcon")) else "own", z.get("id"), z.get("name"),
             z.get("coopBase"), z.get("craft")] for b in soldiers(gc) for z in b.get("soldiers", [])
            if (name is not None and z.get("name") == name) or (gid is not None and z.get("id") == gid)]

def texts(gc):
    """the visible widgets' texts"""
    return [w.get("text") for w in q(gc, {"cmd": "list_widgets"}).get("widgets", [])
            if w.get("visible") is True and w.get("hidden") is False and (w.get("text") or "").strip()]

def contrib(gc):
    """the host's guest-roster store (event_state.guestContrib; T0-W4 only)"""
    return pick(q(gc, {"cmd": "event_state"}).get("guestContrib") or {}, ("sent", "recvSeats", "soldiers"))

def own_key(x, ev):
    """B: K0 = the client's role own_world key (present; read by name later, F20702), the guest's id and record in the view"""
    c = x.client
    ow = q(c, {"cmd": "coop_file_info", "role": "own_world"})
    x.K0 = ow.get("key") if ow.get("present") is True else None
    g = where(c, x.gift)
    x.gid = g[0][2] if len(g) == 1 else None
    ev["K0"] = {"key": ow.get("key"), "present": ow.get("present"), "guest": g, "at": snap(x)}
    if x.K0 is None or x.gid is None:
        raise Stop("K0 or the guest's one view record not present at B: %s" % ev["K0"])

def first_window(x, ev, sub):
    """the window: sub on top; the host's 54 and the client's 67 (GH trigger54); the client's real OK back to sub with insideCoopBase
    false within W_UI; the host's real CANCEL (QUICK within W_SAVE, GH host_cancel); HOLD_P"""
    c = x.client
    if top(c) != sub:
        raise Stop("the window's sub-screen %s not on top: %s" % (sub, stack(c)))
    trigger54(x, ev)
    ev["54"]["at"] = snap(x)
    ok = real_click(c, dlg(c).get("backText") or "OK", W_UI)
    v, s = wait(lambda: top(c) == sub and coop(c).get("insideCoopBase") is False, W_UI)
    ev["67 OK"] = {"press": ok, "s": s if v else None, "at": snap(x)}
    if not v:
        raise Stop("not %s with insideCoopBase false after the 67's OK: %s" % (sub, ev["67 OK"]))
    host_cancel(x, ev)
    time.sleep(HOLD_P)
    ev["window"] = snap(x)

def second_save(x, ev):
    """the host's second quick save in the window: its 54 within SEEN54_S (the row's last precondition); then the client's (top, code,
    depth) trace every 0.05 s until HOLD_W after its first CoopState code (W_67 without one); the HOLD_W record (CAP70 second_save +
    watch)"""
    h, c = x.host, x.client
    x.F0 = files(h)
    q(h, {"cmd": "save_game_ui", "type": "quick"})
    v, s = wait(lambda: top(h) == "CoopState" and dlg(h).get("code") == 54, SEEN54_S, POLL_S)
    ev["54b"] = {"s": s if v else None, "name": coop(h).get("pendingHostSaveName"), "saveID": ids(x)}
    if not v:
        raise Stop("the host's second 54 not on top within %.0f s: %s %s" % (SEEN54_S, stack(h), dlg(h)))
    tr, first, t0 = [], None, time.time()
    while time.time() - t0 < (first - t0 + HOLD_W if first else W_67):
        st = stack(c)
        e = [st[-1] if st else None, code(c, st), len(st)]
        if not tr or tr[-1][1:] != e:
            tr.append([round(time.time() - t0, 3)] + e)
        if first is None and e[1] is not None:
            first = time.time()
        time.sleep(0.05)
    ev["trace"] = tr
    ev["HOLD_W"] = snap(x)

def leave_window(x, ev):
    """real OK on a 67, OK on a base sub-screen, GEOSCAPE on BasescapeState; any other CoopState code before GEOSCAPE records blocked
    and stops pressing; "left" = GeoscapeState in the stack with no BasescapeState within W_LEAVE (a 53 above it is the answer at the
    geoscape) -> left"""
    c, seen, t0, g = x.client, [], time.time(), None
    lv = ev["leave"] = {"seen": seen, "blocked": None, "left s": None}
    while time.time() - t0 < W_LEAVE:
        st = stack(c)
        tp, cd = (st[-1] if st else None), code(c, st)
        if not seen or seen[-1] != [tp, cd]:
            seen.append([tp, cd])
        if "GeoscapeState" in st and "BasescapeState" not in st:
            lv["left s"] = round(time.time() - t0, 3)
            break
        if g is None:
            if tp == "CoopState" and cd != 67:
                lv["blocked"] = cd
                break
            if tp == "CoopState":
                real_click(c, dlg(c).get("backText") or "OK", W_UI)
            elif tp == "BasescapeState":
                g = real_click(c, "GEOSCAPE", W_UI) or None
            elif tp in SUBS:
                real_click(c, "OK", W_UI)
        time.sleep(0.1)
    lv["at"] = snap(x)
    return lv["left s"] is not None

def write_after(x, ev):
    """QUICK written within W_SAVE of the leave with no host press (GH written against x.F0); HOLD_L; the record"""
    v, s = written(x, W_SAVE)
    ev["write"] = {"s": s if v else None, "file": files(x.host).get(QUICK)}
    time.sleep(HOLD_L)
    ev["after write"] = snap(x)

def host_picker(x, ev):
    """before the visit: the client's own base (GH own_base); the host's globe from the probe save's host world, its screen (GH
    geometry) and its window scale from a select-destination CANCEL on its own craft (CAP70 host_pk)"""
    h = x.host
    x.cb = own_base(x.client)
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    with open(os.path.join(h.user_dir, "xcom1", PROBE), encoding="utf-8", errors="replace") as fh:
        d = next((d for d in yaml.load_all(fh, Loader=loader) if isinstance(d, dict) and "bases" in d), {})
    G = {k: d.get(k) for k in ("globeLon", "globeLat", "globeZoom")}
    cr = next((k for k in (own_base(h) or {}).get("crafts", []) if not k.get("coop")), None)
    q(h, {"cmd": "open_select_destination", "craft_id": cr and cr["id"], "craft_type": cr and cr["type"]})
    time.sleep(0.4)
    cw = q(h, {"cmd": "click_widget", "match": "CANCEL"})
    time.sleep(0.5)
    x.pkH = {"G": G, "geom": geometry(h), "scale": cw.get("baseX") and {"x": cw["winX"] / cw["baseX"], "y": cw["winY"] / cw["baseY"]}}
    ev["host picker"] = {"cb": x.cb and [x.cb.get("name"), x.cb.get("lon"), x.cb.get("lat")], "pk": x.pkH, "host": stack(h)}
    if not x.cb or not G or None in G.values() or not x.pkH["scale"] or top(h) != "GeoscapeState":
        raise Stop("the host picker missed: %s" % ev["host picker"])

def host_view(x, ev):
    """B2 = the client's "basehost" fnv; the host's real globe click on the client base (GH CLICKS offsets) while the client's (top,
    code) is traced every 0.05 s; the host's BasescapeState within W_VISIT (the row's last precondition); the trace to HOLD_V; the
    host's base_report (coop), the client's fnv (CAP70 row_c2)"""
    h, c = x.host, x.client
    x.B2 = ev["B2"] = fnvb(c)
    tr, t0, hit, v = [], time.time(), None, None

    def tick():
        st = stack(c)
        e = [st[-1] if st else None, code(c, st)]
        if not tr or tr[-1][1:] != e:
            tr.append([round(time.time() - t0, 3)] + e)
    px, py = project(x.pkH["G"], x.cb["lon"], x.cb["lat"], x.pkH["geom"])
    sc = x.pkH["scale"]
    for dx, dy in CLICKS:
        q(h, {"cmd": "inject_input", "kind": "click", "x": int((px + dx) * sc["x"] + 1), "y": int((py + dy) * sc["y"] + 1)})
        t1 = time.time()
        while time.time() - t1 < 0.9 and top(h) == "GeoscapeState":
            tick()
            time.sleep(0.05)
        if top(h) != "GeoscapeState":
            hit = [px + dx, py + dy]
            break
    while hit and time.time() - t0 < W_VISIT:
        tick()
        if top(h) == "BasescapeState":
            v = time.time()
            break
        time.sleep(0.05)
    ev["host visit"] = {"pixel": hit, "s": round(v - t0, 3) if v else None, "host": stack(h)}
    if not v:
        ev["trace"] = tr
        raise Stop("the host not on BasescapeState within %.0f s of its click on the client base: %s" % (W_VISIT, ev["host visit"]))
    while time.time() - v < HOLD_V:
        tick()
        time.sleep(0.05)
    ev["trace"] = tr
    ev["view"] = {"report": pick(q(h, {"cmd": "base_report", "coop": True}), ("name", "coopBaseFlag", "error")), "basehost": fnvb(c),
                  "at": snap(x)}

def host_back(x, ev):
    """after R12's record: the client's OK on a 995 if up (R12's construction), the host's GEOSCAPE; HOLD_P"""
    c, h = x.client, x.host
    ev["back"] = {"995 OK": real_click(c, dlg(c).get("backText") or "OK", W_UI) if code(c) == 995 else None,
                  "host GEOSCAPE": real_click(h, "GEOSCAPE", W_UI) if top(h) == "BasescapeState" else None}
    time.sleep(HOLD_P)
    ev["back"]["at"] = snap(x)

def row_click(x, gc, row):
    """a TextList row: inject_input at (x + 30, y + 3 + 8 * row) times the clicking machine's scale, + 1 (CAP70 row_click)"""
    tl, sc = textlist(gc), x.pk["scale"]
    if tl:
        q(gc, {"cmd": "inject_input", "kind": "click", "x": int((tl["x"] + 30) * sc["x"] + 1), "y": int((tl["y"] + 3 + 8 * row) * sc["y"] + 1)})
    return bool(tl)

def press(gc, text, want, steps, label):
    """a real press of text, then want on top within W_UI -> reached (recorded in steps)"""
    ok = real_click(gc, text, W_UI)
    v, s = wait(lambda: top(gc) == want, W_UI)
    steps.append([label, ok, s if v else None])
    return bool(v)

def open_crew(x, ev, equip):
    """EQUIP CRAFT, craft row 0 (rows 1, 2), CREW: CraftSoldiersState on top (CAP70 open_crew)"""
    c, st = x.client, ev.setdefault("steps", [])
    if not press(c, equip, "CraftsState", st, equip):
        raise Stop("%s opened no CraftsState: %s" % (equip, stack(c)))
    for row in range(3):
        row_click(x, c, row)
        if wait(lambda: top(c) == "CraftInfoState", W_UI)[0]:
            st.append(["craft row", row])
            break
    else:
        raise Stop("no CraftInfoState from craft rows 0-2: %s" % stack(c))
    if not press(c, "CREW", "CraftSoldiersState", st, "CREW"):
        raise Stop("CREW opened no CraftSoldiersState: %s" % stack(c))

def toggle_seat(x, ev):
    """the guest's crew row (row 0, then rows 1, 2): its craft in get_soldiers changes within W_UI (CAP70 toggle_seat)"""
    c, before = x.client, where(x.client, x.gift)
    for row in range(3):
        row_click(x, c, row)
        v, s = wait(lambda: where(c, x.gift) != before, W_UI)
        if v:
            ev["seat"] = {"row": row, "s": s, "before": before, "after": where(c, x.gift), "fnv": fnvb(c)}
            return
    raise Stop("no crew row changed %s's craft: %s" % (x.gift, before))

def move_home(x, ev, move):
    """SoldiersState rows 0..7 until SackSoldierState names GIFTNAME; MOVE, OK; SoldiersState back (the row's last precondition); the
    fnv after the MOVE's OK (CAP70 sack_guest)"""
    c, tried = x.client, []
    for row in range(8):
        row_click(x, c, row)
        if not wait(lambda: top(c) == "SoldierInfoState", W_UI)[0]:
            tried.append([row, top(c)])
            continue
        real_click(c, move, W_UI)
        v, _s = wait(lambda: top(c) == "SackSoldierState", W_UI)
        names = texts(c) if v else []
        tried.append([row, names])
        if any((t or "").startswith(x.gift) for t in names):
            ok = real_click(c, "OK", W_UI)
            v2, s2 = wait(lambda: top(c) == "SoldiersState", W_UI)
            ev["move"] = {"row": row, "ok": ok, "s": s2 if v2 else None, "fnv": fnvb(c), "view": where(c, x.gift), "tried": tried}
            if not v2:
                raise Stop("SoldiersState not back after the MOVE's OK: %s" % stack(c))
            return
        if v:
            real_click(c, "CANCEL", W_UI)
        real_click(c, "OK", W_UI)
        wait(lambda: top(c) == "SoldiersState", W_UI)
    raise Stop("no soldier row reached a MOVE window naming %s: %s" % (x.gift, tried))

def rename_guest(x, ev):
    """R15's lever: rename_soldier GIFTNAME -> RENAME (the first of RENAMES in neither roster) on the client; the view
    lists RENAME within W_UI (the row's last precondition)"""
    c = x.client
    names = {z.get("name") for gc in (x.host, c) for b in soldiers(gc) for z in b.get("soldiers", [])}
    x.rename = next((n for n in RENAMES if n not in names), None)
    r = q(c, {"cmd": "rename_soldier", "name": x.gift, "newName": x.rename}) if x.rename else {}
    v, s = wait(lambda: where(c, x.rename), W_UI)
    ev["rename"] = {"name": x.rename, "ok": r.get("ok"), "view": v, "s": s, "fnv": fnvb(c)}
    if not v:
        raise Stop("the view does not list the renamed guest: %s" % ev["rename"])

def read_c(x):
    """the read: both machines alive, the crash folder since B, the record"""
    al = [alive(x.host), alive(x.client)]
    return {"alive": al, "crash": crash_new(x.c0), "at": snap(x) if all(al) else None}

def common_c(rid, rd):
    cr = rd.get("crash") or {}
    return (rid + "-common", "GUARD", "both machines alive at the read, no new .dmp since B", rd.get("alive") == [True, True] and cr.get("dmp") == [])

def run_row_c(rid, tag, key, pre, post, ids_, cellfn, label, hostpk=False):
    """one row: boot (a miss fails the row "boot" with ONE CAPTURE line); the prefix P (GH stage_guest, picker, [host_picker], visit,
    baseline B, own_key K0); pre (to the row's last precondition; a Stop ends the row); post (records only); the read; shutdown; ONE
    EVIDENCE line, one PASS / FAIL line per cell, the row verdict -> (passed, wall, shutdown failures)"""
    r, ev, cap = Row(rid, ["%s-%s" % (rid, c) for c in ids_]), {}, None
    LAST.clear()
    x = boot(tag, key)
    x.t0, x.K0, x.gid = time.time(), None, None
    ev["cpu"], failed = x.cpu, []
    try:
        if x.err:
            print("FAIL %s boot: both tops GeoscapeState unchanged %.0f s not within %.0f s (%s)" % (rid, STABLE_S, BOOT_S, x.err), flush=True)
            r.fails.append("boot")
            r.stop("boot")
            cap = x.cap
        else:
            try:
                stage_guest(x, ev)
                picker(x, ev)
                ev["own before"] = where(x.client, x.gift)
                if hostpk:
                    host_picker(x, ev)
                visit(x, ev)
                baseline(x, ev)
                own_key(x, ev)
                pre(x, ev)
            except Exception as e:  # Stop, or a probe that raised: the row ends here
                ev["stop"] = short(e, 600)
                cap = {n: {"stack": stack(gc), "get_coop": coop(gc), "coop_dialog_info": dlg(gc), "blob": blob(gc), "soldiers": soldiers(gc)}
                       for n, gc in (("host", x.host), ("client", x.client)) if alive(gc)}
            if "stop" not in ev:
                try:
                    post(x, ev)
                except Exception as e:  # after the last precondition: recorded, never raised
                    ev["post"] = short(e, 600)
            ev["read"] = read_c(x)
    finally:
        failed += shut(x)
    LAST.update(ev=ev, tag=tag, shut=failed)
    if not x.err:
        print("EVIDENCE %s: %s" % (rid, json.dumps(ev, sort_keys=True, default=str)), flush=True)
        r.cell(rid + "-pre", "GUARD", label, "stop" not in ev)
        if "stop" in ev:
            r.stop(ev["stop"])
        for cid, kind, lab, ok in ([] if "stop" in ev else cellfn(rid, ev)):
            r.cell(cid, kind, lab, ok)
    if r.fails:
        cap = cap or {k: ev.get(k) for k in ("read", "trace", "leave", "write", "post")}
        print("CAPTURE %s: %s" % (rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
    print(("PASS %s" % rid) if not r.fails else ("FAIL %s: %s" % (rid, " ".join(r.fails))), flush=True)
    return not r.fails, round(time.time() - r.t0, 1), failed
