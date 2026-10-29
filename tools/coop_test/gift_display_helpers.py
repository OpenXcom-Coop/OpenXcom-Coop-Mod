"""gift_display_helpers.py: shared helpers of the W2-H70 S-B tests test_gift_display_copy.py (rows R7, R8, G7) and
test_gift_display_copy_screens.py (rows R9, R10); spec docs rewrite/prompts/w2h70_sb_display_copy.md (f) and Appendix B; TASK 0
rewrite/w2h70-task0/sb/CONSTANTS.md; lead L-TR9-1, F20420-F20425; R-TR9-1, R-H70-2, QH70B-1 .. QH70B-8 (a). Imports gift_helpers.py
(GH) unchanged; the S-B steps are copied from the captures rewrite/ltr9-1-cap/cap.py and rewrite/lh70-2-cap/cap.py, never imported. Every
press is real (click_widget, inject_input at a pixel or SDLK_KP2); every probe an existing TestServer command; a missed precondition raises
Stop (the row ends there). one foreground run per invocation, exit 0 only when every cell passes."""
from gift_helpers import *  # noqa: F401,F403 (GH: boot, picker, visit, baseline, host_gift, census, Row, Stop, ...)

GUESTNAME = "Zzz Guest"
W_REPLAY = 25.0
DEFERRED = "[coop-gift] RECV deferred (viewing peer base)"
ADDED = "[coop-gift] RECV added soldier"

def own_bases(gc):
    return [b for b in soldiers(gc) if not b.get("coopBaseFlag") and not b.get("coopIcon")]

def own_ids(gc):
    return [[z.get("id"), z.get("name"), z.get("coopBase")] for b in own_bases(gc) for z in b.get("soldiers", [])]

def twice(pairs):
    seen = {}
    for i, n in pairs:
        seen.setdefault(str(i), []).append(n)
    return {k: v for k, v in seen.items() if len(v) > 1}

def ids_twice(gc):
    """ids held by two or more soldiers on the machine's own bases -> {id: [names]}"""
    return twice([(z.get("id"), z.get("name")) for b in own_bases(gc) for z in b.get("soldiers", [])])

def blobs(gc):
    """coop_file_info: the host's stored partner world and its "basehost"; the client's "basehost" and own-world blob"""
    if not alive(gc):
        return None
    ks = ("present", "bytes", "fnv1a64")
    if gc.name == "host":
        return {"copy": pick(q(gc, {"cmd": "coop_file_info", "role": "host_copy_of_client"}), ("key",) + ks),
                "basehost": pick(q(gc, {"cmd": "coop_file_info", "key": "basehost"}), ks)}
    return {"basehost": pick(q(gc, {"cmd": "coop_file_info", "key": "basehost"}), ks),
            "own": pick(q(gc, {"cmd": "coop_file_info", "role": "own_world"}), ("key",) + ks)}

def snap(x, ev, label):
    """both stacks, get_coop and the coop blobs at one point of the row (t = seconds since B)"""
    ev[label] = {n: {"stack": stack(gc), "coop": coop(gc), "blob": blobs(gc)} if alive(gc) else {"alive": False}
                 for n, gc in (("host", x.host), ("client", x.client))}
    ev[label]["t"] = round(time.time() - x.B["t"], 3) if getattr(x, "B", None) else None

def row_to(x, gc, rows, want, sc):
    """the first of `rows` whose TextList pixel (x + 30 / y + 3 + 8 * row, x the clicker's scale, + 1) puts `want` on top in W_UI"""
    for row in rows:
        tl = textlist(gc)
        if not tl:
            return None
        q(gc, {"cmd": "inject_input", "kind": "click", "x": int((tl["x"] + 30) * sc["x"] + 1), "y": int((tl["y"] + 3 + 8 * row) * sc["y"] + 1)})
        v, _s = wait(lambda: top(gc) == want, W_UI)
        if v:
            return row
    return None

def press_to(gc, text, want, why):
    """a real press of `text`, then `want` on top within W_UI (else Stop) -> seconds"""
    ok = real_click(gc, text, W_UI)
    v, s = wait(lambda: top(gc) == want, W_UI)
    if not v:
        raise Stop("%s: %s pressed (%s), %s not on top within %.0f s: %s" % (why, text, ok, want, W_UI, stack(gc)))
    return s

def listed(gc):
    return [z.get("name") for z in q(gc, {"cmd": "base_report", "coop": True}).get("soldiers", [])]

def stage_guest_named(x, ev, name=GUESTNAME):
    """GH stage_guest under its own name: the client's first own-base soldier not in a craft (the next one when the transfer
    refuses, at most 3) renamed `name`, transfer_to_coop_base to the host base; the host's 150 closed by a real OK; GeoscapeState back"""
    c, h = x.client, x.host
    if name in {z.get("name") for gc in (h, c) for b in soldiers(gc) for z in b.get("soldiers", [])}:
        raise Stop("GUESTNAME %r already in a roster" % name)
    ob = next((b for b in own_bases(c) if b.get("soldiers")), None)
    tries, tr = [], {}
    for sol in [z for z in (ob or {}).get("soldiers", []) if not z.get("craft")][:3]:
        rn = q(c, {"cmd": "rename_soldier", "name": sol["name"], "newName": name})
        tr = q(c, {"cmd": "transfer_to_coop_base", "name": name, "toBase": x.hb.get("name")})
        tries.append([sol.get("name"), sol.get("id"), rn.get("ok"), tr.get("transferred")])
        if tr.get("transferred"):
            break
        q(c, {"cmd": "rename_soldier", "name": name, "newName": sol["name"]})
    v150, s150 = wait(lambda: top(h) == "CoopState" and dlg(h).get("code") == 150, W_UI)
    ok150 = real_click(h, dlg(h).get("backText") or "OK", W_UI) if v150 else False
    back, _s = wait(lambda: top(h) == "GeoscapeState", W_UI)
    ev["guest"] = {"name": name, "tries": tries, "150 s": s150 if v150 else None, "150 OK": ok150, "host back": bool(back),
                   "hostBase": [x.hb.get("name"), x.hb.get("coopBaseId")]}
    if not (tr.get("transferred") and v150 and ok150 and back):
        raise Stop("the guest not staged: %s" % ev["guest"])

def host_picker(x, ev):
    """CAP9 picker2's host half: the globe of GH picker's probe save (host world) and a select-destination CANCEL's window scale"""
    h = x.host
    with open(os.path.join(h.user_dir, "xcom1", PROBE), encoding="utf-8", errors="replace") as fh:
        w = next((d for d in yaml.load_all(fh, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader)) if isinstance(d, dict) and "bases" in d), {})
    G = {k: w.get(k) for k in ("globeLon", "globeLat", "globeZoom")}
    cr = next((k for k in (own_base(h) or {}).get("crafts", []) if not k.get("coop")), None)
    q(h, {"cmd": "open_select_destination", "craft_id": cr and cr["id"], "craft_type": cr and cr["type"]})
    time.sleep(0.4)
    cw = q(h, {"cmd": "click_widget", "match": "CANCEL"})
    time.sleep(0.5)
    x.pkH = {"G": G, "geom": geometry(h), "scale": cw.get("baseX") and {"x": cw["winX"] / cw["baseX"], "y": cw["winY"] / cw["baseY"]}}
    ev["host picker"] = {"G": G, "scale": x.pkH["scale"], "host": stack(h)}
    if not G or None in G.values() or not x.pkH["scale"] or top(h) != "GeoscapeState":
        raise Stop("the host picker missed: %s" % ev["host picker"])

def host_visit(x, ev):
    """the host's real globe click on the client's base: insideCoopBase and BasescapeState on the host within W_VISIT"""
    h, cb = x.host, own_base(x.client) or {}
    px = click_globe(h, cb.get("lon"), cb.get("lat"), x.pkH)
    v, s = wait(lambda: coop(h).get("insideCoopBase") and top(h) == "BasescapeState", W_VISIT, 0.25)
    ev["visit"] = {"pixel": px, "inside s": s if v else None, "clientBase": [cb.get("name"), cb.get("coopBaseId")]}
    if not v:
        raise Stop("the host not inside the client base within %.0f s: %s" % (W_VISIT, stack(h)))

def gift_from(x, ev):
    """CAP9 gift_from: the client's first own soldier not in a craft renamed GIFTNAME; BASES, SOLDIERS, its row, KP2, the host's button;
    the host's deferral line within W_NOTICE; the client back on GeoscapeState (real presses)"""
    c, h = x.client, x.host
    g = ev["gift"] = {}
    sols = [z for b in own_bases(c)[:1] for z in b.get("soldiers", []) if z.get("coopBase") in (-1, None)]
    idx = next((i for i, z in enumerate(sols) if not z.get("craft")), None)
    if idx is None:
        raise Stop("no client soldier outside a craft")
    g["soldier"] = [sols[idx]["name"], sols[idx]["id"], idx, q(c, {"cmd": "rename_soldier", "name": sols[idx]["name"], "newName": x.gift}).get("ok")]
    press_to(c, "BASES", "BasescapeState", "the client's gift")
    press_to(c, "SOLDIERS", "SoldiersState", "the client's gift")
    if row_to(x, c, (idx,), "SoldierInfoState", x.pk["scale"]) is None:
        raise Stop("no SoldierInfoState from the client's row %d" % idx)
    q(c, {"cmd": "inject_input", "kind": "key", "key": SDLK_KP2})
    v, _s = wait(lambda: top(c) == "GiftSoldierMenu", W_UI)
    btns = buttons(c) if v else []
    hb = next((t for t in btns if "host" in t.lower()), None) or coop(c).get("hostName")
    if "Gift %s to another player?" % x.gift not in [(t or "").strip() for t in btns]:
        raise Stop("the client's gift menu does not name %s: %s" % (x.gift, btns))
    g["press"] = [hb, real_click(c, hb, W_UI)]
    v, s = wait(lambda: any(DEFERRED in ln for ln in gift_lines(h, x.n_h)) or None, W_NOTICE)
    g["deferral s"] = s if v else None
    for _i in range(6):
        tp = top(c)
        if tp == "GeoscapeState":
            break
        real_click(c, "GEOSCAPE" if tp == "BasescapeState" else "OK", W_UI)
        time.sleep(0.4)
    g.update(host=stack(h), client=stack(c), inside=coop(h).get("insideCoopBase"), lines=gift_lines(h, x.n_h)[-4:])
    if not v:
        raise Stop("no host line %r within %.0f s of the client's gift" % (DEFERRED, W_NOTICE))
    if top(c) != "GeoscapeState":
        raise Stop("the client not back on GeoscapeState after its gift: %s" % stack(c))

def list_ok(x, ev, r):
    """R7 / R8: SOLDIERS (SoldiersState lists GIFTNAME), OK (BasescapeState)"""
    ev["screen"] = {"SoldiersState s": press_to(r, "SOLDIERS", "SoldiersState", "SOLDIERS"), "listed": listed(r)}
    if x.gift not in ev["screen"]["listed"]:
        raise Stop("SoldiersState does not list %s: %s" % (x.gift, ev["screen"]["listed"]))
    ev["screen"]["OK s"] = press_to(r, "OK", "BasescapeState", "the list's OK")

def no_screen(x, ev, r):
    """G7: no screen inside the visit (the notice's OK, then GEOSCAPE)"""
    ev["screen"] = {"listed": listed(r)}

def craft_ok(x, ev, r, label):
    """R9: the craft button `label` (CraftsState), craft row 0 (CraftInfoState; rows 1, 2 next), OK (CraftsState), OK (BasescapeState)"""
    sc = press_to(r, label, "CraftsState", label)
    row = row_to(x, r, (0, 1, 2), "CraftInfoState", x.pk["scale"])
    ev["screen"] = {"CraftsState s": sc, "craft row": row, "listed": listed(r)}
    if row is None:
        raise Stop("no CraftInfoState from craft rows 0-2: %s" % stack(r))
    ev["screen"]["CraftInfoState OK s"] = press_to(r, "OK", "CraftsState", "the craft's OK")
    ev["screen"]["CraftsState OK s"] = press_to(r, "OK", "BasescapeState", "CraftsState's OK")

def move_home(x, ev, r, label):
    """R10: SOLDIERS, GIFTNAME's row, the SACK button `label` (SackSoldierState naming GIFTNAME), OK (SoldiersState: SoldierInfoState
    pops itself on an empty list, F20581; else its OK), OK (BasescapeState)"""
    press_to(r, "SOLDIERS", "SoldiersState", "SOLDIERS")
    ls = listed(r)
    if x.gift not in ls:
        raise Stop("SoldiersState does not list %s: %s" % (x.gift, ls))
    row = row_to(x, r, (ls.index(x.gift),), "SoldierInfoState", x.pk["scale"])
    ev["screen"] = {"listed": ls, "row": row}
    if row is None:
        raise Stop("no SoldierInfoState from %s's row %d" % (x.gift, ls.index(x.gift)))
    press_to(r, label, "SackSoldierState", label)
    texts = [(w.get("text") or "").strip() for w in q(r, {"cmd": "list_widgets"}).get("widgets", []) if w.get("visible") is True]
    ev["screen"]["sack"] = texts
    if not any(t.startswith(x.gift) for t in texts):
        raise Stop("SackSoldierState does not name %s: %s" % (x.gift, texts))
    real_click(r, "OK", W_UI)
    wait(lambda: top(r) != "SackSoldierState", W_UI)
    ev["screen"]["after its OK"] = stack(r)
    if top(r) == "SoldierInfoState":
        press_to(r, "OK", "SoldiersState", "SoldierInfoState's OK")
    if top(r) != "SoldiersState":
        raise Stop("SoldiersState not on top after %s's OK: %s" % (label, stack(r)))
    ev["screen"]["OK s"] = press_to(r, "OK", "BasescapeState", "the list's OK")

def receiver_path(x, ev, r, steps):
    """CAP9 receiver_steps: GiftNoticeState within W_NOTICE, its OK, the row's screen steps, GEOSCAPE ([GeoscapeState] in W_LEAVE),
    ADDED within W_REPLAY, HOLD_L, the live census and the read"""
    v, s = wait(lambda: top(r) == "GiftNoticeState", W_NOTICE)
    ev["notice"] = {"s": s if v else None, "lines": gift_lines(r, x.n_c if r is x.client else x.n_h)[-3:]}
    if not v:
        raise Stop("no GiftNoticeState on the %s within %.0f s: %s" % (r.name, W_NOTICE, stack(r)))
    snap(x, ev, "at notice")
    ev["notice"]["OK s"] = press_to(r, "OK", "BasescapeState", "the notice's OK")
    steps(x, ev, r)
    snap(x, ev, "after screen")
    n1 = len(log(r))
    real_click(r, "GEOSCAPE", W_UI)
    v, s = wait(lambda: stack(r) == ["GeoscapeState"], W_LEAVE)
    ev["leave"] = {"s": s if v else None, "inside": coop(r).get("insideCoopBase")}
    if not v:
        raise Stop("the %s not back on [GeoscapeState] within %.0f s: %s" % (r.name, W_LEAVE, stack(r)))
    v, s = wait(lambda: any(ADDED in ln for ln in log(r)[n1:]) or None, W_REPLAY)
    ev["leave"].update({"replay s": s if v else None, "lines": gift_lines(r, n1)[-3:]})
    if not v:
        raise Stop("no %r on the %s within %.0f s of the leave" % (ADDED, r.name, W_REPLAY))
    time.sleep(HOLD_L)
    snap(x, ev, "after replay")
    x.live = census(x)
    ev["live"] = dict(x.live, twice={"host": ids_twice(x.host), "client": ids_twice(x.client)}, recvIds=own_ids(r))
    read_point(x, ev)

def file_read(x, ev):
    """QUICK's halves (GH read_save): GIFTNAME in the host half [base, id] / client entries [key, base, id]; per half the ids twice"""
    p = os.path.join(x.host.user_dir, "xcom1", QUICK)
    f = read_save(p)
    ev["halves"] = {"bytes": f["bytes"], "keys": [[e["key"], e["bytes"], e["fnv1a64"]] for e in f["entries"]],
                    "host": [[b, i] for b, n, i in f["host"] if n == x.gift],
                    "client": [[e["key"], b, i] for e in f["entries"] for b, n, i in e["soldiers"] if n == x.gift],
                    "hostTwice": twice([(i, n) for _b, n, i in f["host"]]),
                    "clientTwice": {e["key"]: twice([(i, n) for _b, n, i in e["soldiers"]]) for e in f["entries"]}}
    x.src = p
    return ev["halves"]

def file_clean_client(hv):
    """GIFTNAME in no host-half soldier and once in one client entry, and no id twice in that entry"""
    return not hv["host"] and len(hv["client"]) == 1 and not hv["clientTwice"].get(hv["client"][0][0])

def file_clean_host(hv):
    """GIFTNAME once in the host half, in no client entry, and no id twice in the host half"""
    return len(hv["host"]) == 1 and not hv["client"] and not hv["hostTwice"]

def qstat(h):
    try:
        st = os.stat(os.path.join(h.user_dir, "xcom1", QUICK))
        return [st.st_size, st.st_mtime_ns]
    except OSError:  # absent, or mid-save (the save's own .bak comes and goes beside it)
        return [0, 0]

def host_save(x, ev):
    """CAP9 host_save: the host's quick save with no visit open (both tops GeoscapeState): QUICK written within W_SAVE; its halves"""
    h = x.host
    if top(h) != "GeoscapeState" or top(x.client) != "GeoscapeState":
        raise Stop("a visit still open at the save: %s %s" % (stack(h), stack(x.client)))
    before, t0 = qstat(h)[1], time.time()
    q(h, {"cmd": "save_game_ui", "type": "quick"})
    v, s = wait(lambda: qstat(h)[1] > before, W_SAVE, 0.05)
    time.sleep(1.0)
    ev["write"] = {"s": s if v else None, "QUICK": qstat(h), "host": stack(h), "client": stack(x.client), "at": round(t0 - x.B["t"], 3)}
    if not v:
        raise Stop("the host's quick save not written within %.0f s" % W_SAVE)
    return file_read(x, ev)

def reload_b(x, ev, key):
    """GH reload plus ids_twice: a fresh pair <tag>r_host / _client, QUICK copied in before the host spawns, resume_campaign, settle"""
    y = boot(x.tag + "r", key, saves=(x.src,))
    try:
        if y.err:
            ev["reload"] = {"boot": y.err, "cap": y.cap}
            return None
        y.gift = x.gift
        c = census(y)
        c["twice"] = {"host": ids_twice(y.host), "client": ids_twice(y.client)}
        ev["reload"] = dict(c, settle=y.settle, crash=crash_new(y.c0)["dmp"])
        return c
    finally:
        x.shutfail = shut(y)

def cells_b(rid, ev, who, reloads, kind="FIX"):
    """the row's cells after X-pre: live, ids, file (+ reload) for the receiver `who` ("client": R7, G7, R9, R10; "host": R8)"""
    lv, hv, rl = ev.get("live") or {}, ev.get("halves") or {}, ev.get("reload") or {}
    once = once_client if who == "client" else once_host
    clean = file_clean_client if who == "client" else file_clean_host
    out = [(rid + "-live", kind, "once_%s HOLD_L after the replay line: %s" % (who, lv.get(who)), "host" in lv and once(lv)),
           (rid + "-ids", kind, "ids_twice(%s) empty: %s" % (who, (lv.get("twice") or {}).get(who)), "twice" in lv and not lv["twice"][who]),
           (rid + "-file", kind, "file_clean_%s(QUICK): host %s client %s, ids twice host %s client %s" % (
               who, hv.get("host"), hv.get("client"), hv.get("hostTwice"), hv.get("clientTwice")), bool(hv) and clean(hv))]
    if reloads:
        out.append((rid + "-reload", kind, "once_%s and ids_twice(%s) empty after the reload: %s %s" % (
            who, who, rl.get(who), (rl.get("twice") or {}).get(who)), "host" in rl and once(rl) and not rl["twice"][who]))
    return out

def common_b(rid, ev):
    rd = ev.get("read") or {}
    cr = rd.get("crash") or {}
    return (rid + "-common", "GUARD", "both machines alive at the read, no new .dmp since B: %s %s" % (rd.get("alive"), cr.get("dmp")),
            rd.get("alive") == [True, True] and cr.get("dmp") == [])

def run_row_b(rid, tag, key, build, ids, cellfn, pre, reloads=False):
    """GH run_row's shape: boot (a miss fails "boot"), the construction, shutdown, the reload (R7, R8: a fresh pair, same key),
    ONE EVIDENCE line, the cells, ONE CAPTURE line when a cell failed, the verdict -> (passed, wall, shutdown failures)"""
    r, ev, cap = Row(rid, ["%s-%s" % (rid, c) for c in ids]), {}, None
    x = boot(tag, key)
    ev["cpu"], failed = x.cpu, []
    try:
        if x.err:
            print("FAIL %s boot: both tops GeoscapeState unchanged %.0f s not within %.0f s (%s)" % (rid, STABLE_S, BOOT_S, x.err), flush=True)
            r.fails.append("boot")
            r.stop("boot")
            cap = x.cap
        else:
            try:
                build(x, ev)
            except Exception as e:  # Stop, or a probe that raised: the row ends here
                ev["stop"] = short(e, 600)
                cap = {n: {"stack": stack(gc), "get_coop": coop(gc), "coop_dialog_info": dlg(gc), "blob": blobs(gc), "lines": gift_lines(gc, 0)[-6:]}
                       for n, gc in (("host", x.host), ("client", x.client)) if alive(gc)}
    finally:
        failed += shut(x)
    if not x.err:
        if "stop" not in ev and reloads:
            reload_b(x, ev, key)
            failed += x.shutfail
        print("EVIDENCE %s: %s" % (rid, json.dumps(ev, sort_keys=True, default=str)), flush=True)
        r.cell(rid + "-pre", "GUARD", pre, "stop" not in ev)
        if "stop" in ev:
            r.stop(ev["stop"])
        for cid, kind, label, ok in ([] if "stop" in ev else cellfn(rid, ev) + [common_b(rid, ev)]):
            r.cell(cid, kind, label, ok)
    if r.fails:
        cap = cap or {k: ev.get(k) for k in ("read", "halves", "live", "reload")}
        print("CAPTURE %s: %s" % (rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
    print(("PASS %s" % rid) if not r.fails else ("FAIL %s: %s" % (rid, " ".join(r.fails))), flush=True)
    return not r.fails, round(time.time() - r.t0, 1), failed

def visit_gift(x, ev, steps, guest=False):
    """R7 / G7 / R9 / R10: (R9 guest), picker, the client's visit, B, the host's gift, the receiver path (client), the host's save"""
    if guest:
        stage_guest_named(x, ev)
    picker(x, ev)
    ev["own0"] = own_ids(x.client)
    visit(x, ev)
    baseline(x, ev)
    host_gift(x, ev, DEFERRED)
    receiver_path(x, ev, x.client, steps)
    host_save(x, ev)

def host_visit_gift(x, ev, steps):
    """R8: picker + the host's globe and scale, the host's visit, B, the client's gift, the receiver path (host), the host's save"""
    picker(x, ev)
    host_picker(x, ev)
    ev["own0"] = own_ids(x.host)
    host_visit(x, ev)
    baseline(x, ev)
    gift_from(x, ev)
    receiver_path(x, ev, x.host, steps)
    host_save(x, ev)
