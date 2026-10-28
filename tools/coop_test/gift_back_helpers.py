"""Shared helpers of the W2-H70 stage S-D tests test_gift_back.py (rows R16, R16H) and test_gift_twice_stored.py (row R17); spec docs
rewrite/prompts/w2h70_sd_gift_back.md (f) and Appendix B; TASK 0 rewrite/w2h70-task0/sd/CONSTANTS.md; leads L-H70B-1 and L-H70-3;
ruling R-H70D-0, QH70D-1 .. QH70D-8 (a); R-H70-2 (one non-test helper module); the tests' dirs w2h70d_<row>_*. W2-H70 stage S-D:
in a SEPARATE co-op campaign a soldier received while viewing the giver's base and given straight back before the leave ends with its giver
only, and the host's stored copy of the visiting client's world holds every soldier the client received. Imports gift_display_helpers.py (HB,
which imports gift_helpers.py, GH)
unchanged; named_save, the gift-back, host_gives and client_gives are copied from S-B's TASK 0 script rewrite/w2h70-task0/sb/t0_h70b.py, never
imported; HD has its own receiver path, because the replay after a gift-back is recorded, never awaited. The host's stored copy is
read by a NAMED host save once its coop_file_info fnv changed after the row's press. Every press is real (click_widget on a visible
button, inject_input at a TextList pixel times the clicking machine's scale, or SDLK_KP2); every probe an existing TestServer command; a
missed precondition raises Stop (the row ends there). one foreground run per invocation, exit 0 only when every
cell passes, else 2."""
from gift_display_helpers import *  # noqa: F401,F403 (HB + GH: boot, picker, visit, baseline, host_gift, gift_from, own_ids, ids_twice, ...)

W_PUSH, HOLD_P, W_REPLAY_D = 10.0, 0.5, 3.0
CANCEL = "[coop-gift] W2-H70 S-D:"


def copy_fnv(x):
    """the host's stored copy of the client's world (coop_file_info role host_copy_of_client): its fnv"""
    return (blob(x.host) or {}).get("fnv1a64")


def mark(x, g):
    """just before a row's press: the host's copy fnv (f0) and the press time"""
    x.f0, x.tp = copy_fnv(x), time.time()
    g["copy before"] = x.f0


def named_save(x, label):
    """the host's live world written to a NAMED save (TestServer save_game, h70d_<row>_<label>.sav) within W_SAVE -> (file, s, read_save)"""
    f = "h70d_%s_%s.sav" % (x.rid, label)
    p = os.path.join(x.host.user_dir, "xcom1", f)
    q(x.host, {"cmd": "save_game", "file": f})
    v, s = wait(lambda: os.path.exists(p) and os.path.getsize(p) > 0, W_SAVE, 0.1)
    time.sleep(0.8)
    if not v:
        raise Stop("the named save %s not written within %.0f s" % (f, W_SAVE))
    return f, s, read_save(p)


def stored(x, ev, label):
    """the host's copy fnv differs from x.f0 (read just before the row's press) within W_PUSH (else Stop), HOLD_P, a NAMED host save: the
    client entry whose key is the copy's key -> [base, name, id] (ev "stored <label>")"""
    v, s = wait(lambda: copy_fnv(x) not in (None, x.f0) or None, W_PUSH)
    push = round(time.time() - x.tp, 3)
    first = copy_fnv(x)
    time.sleep(HOLD_P)
    cp = blob(x.host) or {}
    st = ev["stored " + label] = {"fnv0": x.f0, "fnv first": first, "fnv": cp.get("fnv1a64"), "key": cp.get("key"), "bytes": cp.get("bytes"),
                                  "push s": push if v else None, "wait s": s}
    if not v:
        raise Stop("the host's copy of the client world unchanged %.0f s after the %s press (fnv %s)" % (W_PUSH, label, x.f0))
    f, s2, r = named_save(x, label)
    ent = [e for e in r["entries"] if e["key"] == cp.get("key")]
    st.update(file=f, save_s=s2, keys=[e["key"] for e in r["entries"]], entry=ent[0]["soldiers"] if len(ent) == 1 else None,
              entryFnv=ent[0]["fnv1a64"] if len(ent) == 1 else None)
    if len(ent) != 1:
        raise Stop("the named save %s holds %d entries keyed %s: %s" % (f, len(ent), cp.get("key"), st["keys"]))
    return st["entry"]


def back_to_base(r, why):
    """the machine's real OK presses back to SoldiersState (SoldierInfoState pops itself on an empty list, F20581), then OK (BasescapeState)"""
    for _i in range(4):
        if top(r) == "SoldiersState":
            break
        real_click(r, "OK", W_UI)
        time.sleep(0.4)
    return press_to(r, "OK", "BasescapeState", why)


def gift_menu(x, r, name, sc, word, ev, why):
    """from SoldiersState on `r`: `name`'s row (SoldierInfoState), KP2 (GiftSoldierMenu naming `name`) -> the partner button (the one
    containing `word`, else the partner's name from get_coop, which is machine-relative: clientName = the peer)"""
    ls = listed(r)
    ev["listed"] = ls
    if name not in ls:
        raise Stop("%s: SoldiersState does not list %s: %s" % (why, name, ls))
    ev["row"] = ls.index(name)
    if row_to(x, r, (ls.index(name),), "SoldierInfoState", sc) is None:
        raise Stop("%s: no SoldierInfoState from %s's row %d" % (why, name, ls.index(name)))
    q(r, {"cmd": "inject_input", "kind": "key", "key": SDLK_KP2})
    v, _s = wait(lambda: top(r) == "GiftSoldierMenu", W_UI)
    btns = buttons(r) if v else []
    ev["menu"] = btns
    if "Gift %s to another player?" % name not in [(t or "").strip() for t in btns]:
        raise Stop("%s: the gift menu does not name %s: %s %s" % (why, name, btns, stack(r)))
    return next((t for t in btns if word in t.lower()), None) or coop(r).get("clientName")


def give_back(x, ev, r, g, word, sc):
    """the receiver `r` gives the display copy GIFTNAME back from the view: SOLDIERS, its row, KP2, the giver's button; the giver's
    GiftNoticeState within W_NOTICE (the last precondition) and its real OK (GeoscapeState)"""
    gb = ev["giftback"] = {}
    gb["SoldiersState s"] = press_to(r, "SOLDIERS", "SoldiersState", "the gift-back's SOLDIERS")
    pb = gift_menu(x, r, x.gift, sc, word, gb, "the gift-back")
    mark(x, gb)
    nr, ng = len(log(r)), len(log(g))
    gb["press"] = [pb, real_click(r, pb, W_UI)]
    v, s = wait(lambda: top(g) == "GiftNoticeState", W_NOTICE)
    gb["notice s"] = s if v else None
    gb.update(receiver=stack(r), giver=stack(g), rLines=gift_lines(r, nr)[-6:])
    if not v:
        raise Stop("no GiftNoticeState on the %s within %.0f s of the gift-back: %s" % (g.name, W_NOTICE, stack(g)))
    gb["notice OK s"] = press_to(g, "OK", "GeoscapeState", "the giver's notice OK")
    gb["gLines"] = gift_lines(g, ng)[-4:]
    gb["cancel"] = [ln for ln in gift_lines(r, nr) if CANCEL in ln]


def gift_back_client(x, ev):
    """R16 (T0-F's steps): the host's copy changed from B's (the gift's push) within W_PUSH; the client gives GIFTNAME back to the host
    (give_back); stored("back"); the client back on SoldiersState, OK (BasescapeState)"""
    b0 = (x.B["blob"][0] or {}).get("fnv1a64")
    v, s = wait(lambda: copy_fnv(x) not in (None, b0) or None, W_PUSH)
    ev["gift push"] = {"fnv0": b0, "fnv": copy_fnv(x), "s": s if v else None}
    if not v:
        raise Stop("the host's copy of the client world unchanged %.0f s after the host's gift (fnv %s)" % (W_PUSH, b0))
    give_back(x, ev, x.client, x.host, "host", x.pk["scale"])
    stored(x, ev, "back")
    ev["giftback"]["back s"] = back_to_base(x.client, "the client's OK after the gift-back")


def gift_back_host(x, ev):
    """R16H: the host gives GIFTNAME back to the client from its view of the client base (give_back, the host's own scale); the host
    back on SoldiersState, OK (BasescapeState)"""
    give_back(x, ev, x.host, x.client, "client", (getattr(x, "pkH", None) or x.pk)["scale"])
    ev["giftback"]["back s"] = back_to_base(x.host, "the host's OK after the gift-back")


def host_gives(x, ev, k, name):
    """R17 (T0B host_gives): the host's first own soldier not a GIFTNAME, outside a craft first, renamed `name`; BASES, SOLDIERS, its row,
    KP2, the client's button; the client's deferral line within W_NOTICE; the host back on GeoscapeState; the client's GiftNoticeState
    within W_NOTICE and its OK (BasescapeState); stored("g<k>")"""
    h, c = x.host, x.client
    g = ev["take%d" % k] = {}
    sols = (next(iter(own_bases(h)), None) or {}).get("soldiers") or []
    cand = sorted([i for i, z in enumerate(sols) if not str(z.get("name")).startswith("Zzz")], key=lambda i: bool(sols[i].get("craft")))
    if not cand:
        raise Stop("no host soldier to gift")
    i = cand[0]
    g["soldier"] = [sols[i]["name"], sols[i]["id"], i, bool(sols[i].get("craft")),
                    q(h, {"cmd": "rename_soldier", "name": sols[i]["name"], "newName": name}).get("ok")]
    press_to(h, "BASES", "BasescapeState", "the host's gift %d" % k)
    press_to(h, "SOLDIERS", "SoldiersState", "the host's gift %d" % k)
    if row_to(x, h, (i,), "SoldierInfoState", x.pk["scale"]) is None:
        raise Stop("no SoldierInfoState from the host's row %d" % i)
    q(h, {"cmd": "inject_input", "kind": "key", "key": SDLK_KP2})
    v, _s = wait(lambda: top(h) == "GiftSoldierMenu", W_UI)
    btns = buttons(h) if v else []
    pb = next((t for t in btns if "client" in t.lower()), None) or coop(h).get("clientName")
    g["menu"] = btns
    if "Gift %s to another player?" % name not in [(t or "").strip() for t in btns]:
        raise Stop("the host's gift menu does not name %s: %s" % (name, btns))
    mark(x, g)
    nc = len(log(c))
    g["press"] = [pb, real_click(h, pb, W_UI)]
    v, s = wait(lambda: any(DEFERRED in ln for ln in gift_lines(c, nc)) or None, W_NOTICE)
    g["deferral s"] = s if v else None
    for _i in range(6):
        tp = top(h)
        if tp == "GeoscapeState":
            break
        real_click(h, "GEOSCAPE" if tp == "BasescapeState" else "OK", W_UI)
        time.sleep(0.4)
    v2, s2 = wait(lambda: top(c) == "GiftNoticeState", W_NOTICE)
    g["notice s"] = s2 if v2 else None
    g["notice OK s"] = press_to(c, "OK", "BasescapeState", "the client's notice OK") if v2 else None
    g.update(clientLines=gift_lines(c, nc)[-6:], host=stack(h), client=stack(c))
    if not v:
        raise Stop("no client line %r within %.0f s of the host's gift %d" % (DEFERRED, W_NOTICE, k))
    if not v2 or top(h) != "GeoscapeState":
        raise Stop("gift %d: the client's notice %s, the host %s" % (k, s2 if v2 else None, stack(h)))
    stored(x, ev, "g%d" % k)


def client_gives(x, ev, name):
    """R17 (T0B client_gives): the visiting client gives `name` (its guest in the view) to the host: SOLDIERS, its row, KP2, the host's
    button; the host's GiftNoticeState within W_NOTICE (the last precondition) and its OK; stored("send"); the client back on
    SoldiersState, OK (BasescapeState)"""
    c, h = x.client, x.host
    g = ev["give"] = {}
    if top(c) != "SoldiersState":
        g["SoldiersState s"] = press_to(c, "SOLDIERS", "SoldiersState", "the client's gift")
    hb = gift_menu(x, c, name, x.pk["scale"], "host", g, "the client's gift")
    mark(x, g)
    nh, nc = len(log(h)), len(log(c))
    g["press"] = [hb, real_click(c, hb, W_UI)]
    v, s = wait(lambda: top(h) == "GiftNoticeState", W_NOTICE)
    g["host notice s"] = s if v else None
    g.update(client=stack(c), clientLines=gift_lines(c, nc)[-4:])
    if not v:
        raise Stop("no GiftNoticeState on the host within %.0f s of the client's gift: %s" % (W_NOTICE, stack(h)))
    g["notice OK s"] = press_to(h, "OK", "GeoscapeState", "the host's notice OK")
    g["hostLines"] = gift_lines(h, nh)[-4:]
    stored(x, ev, "send")
    g["back s"] = back_to_base(c, "the client's OK after its gift")


def census_d(x, ev):
    """both own rosters, where each of x.names is on each machine's own bases, ids held twice"""
    ev["live"] = {"host": own_ids(x.host), "client": own_ids(x.client), "twice": {"host": ids_twice(x.host), "client": ids_twice(x.client)},
                  "where": {n: {"host": own(x.host, n), "client": own(x.client, n)} for n in x.names}}


def receiver_path_d(x, ev, r, steps=None, need=0, notice=True):
    """HB receiver_path's shape: the receiver's GiftNoticeState within W_NOTICE and its OK (BasescapeState) when `notice`, the
    row's steps, GEOSCAPE ([GeoscapeState] within W_LEAVE), the replay lines: `need` of them within W_REPLAY (a precondition, R17) or, with
    need 0, the first one recorded within W_REPLAY_D (never a precondition, R16 / R16H); HOLD_L; the census; the read"""
    if notice:
        v, s = wait(lambda: top(r) == "GiftNoticeState", W_NOTICE)
        ev["notice"] = {"s": s if v else None, "lines": gift_lines(r, x.n_c if r is x.client else x.n_h)[-3:]}
        if not v:
            raise Stop("no GiftNoticeState on the %s within %.0f s: %s" % (r.name, W_NOTICE, stack(r)))
        ev["notice"]["OK s"] = press_to(r, "OK", "BasescapeState", "the notice's OK")
    if steps:
        steps(x, ev)
    n1 = len(log(r))
    real_click(r, "GEOSCAPE", W_UI)
    v, s = wait(lambda: stack(r) == ["GeoscapeState"], W_LEAVE)
    lv = ev["leave"] = {"s": s if v else None, "inside": coop(r).get("insideCoopBase")}
    if not v:
        raise Stop("the %s not back on [GeoscapeState] within %.0f s: %s" % (r.name, W_LEAVE, stack(r)))
    v, s = wait(lambda: sum(ADDED in ln for ln in log(r)[n1:]) >= max(need, 1) or None, W_REPLAY if need else W_REPLAY_D)
    lv["replay s"] = s if v else None
    if need and not v:
        raise Stop("%d %r line(s) on the %s within %.0f s of the leave: %s" % (need, ADDED, r.name, W_REPLAY, gift_lines(r, n1)[-6:]))
    time.sleep(HOLD_L)
    lv.update(replays=sum(ADDED in ln for ln in log(r)[n1:]), lines=gift_lines(r, n1)[-8:])
    census_d(x, ev)
    read_point(x, ev)


def quick_d(x, ev):
    """QUICK (HB host_save's file, x.src) parsed whole: the host half and every client entry [key, [[base, name, id]]]"""
    f = read_save(x.src)
    ev["quick"] = {"host": f["host"], "entries": [[e["key"], e["soldiers"]] for e in f["entries"]]}


def P(rows):
    """own_ids rows [id, name, coopBase] -> {(id, name)}"""
    return {(i, n) for i, n, _c in rows or []}


def PS(rows):
    """read_save rows [base, name, id] -> {(id, name)}"""
    return {(i, n) for _b, n, i in rows or []}


def cnt(rows, name):
    return sum(1 for s in rows or [] if s[1] == name)


def ids_of(rows):
    return sorted(i for i, _n, _c in rows or [])


def cells_d(rid, ev):
    """the row's cells after X-pre (spec (f)): R16, R16H or R17"""
    nm, lv, qk, o0 = ev.get("names") or {}, ev.get("live") or {}, ev.get("quick") or {}, ev.get("own0") or {}
    g, g2, gu = nm.get("gift"), nm.get("g2"), nm.get("guest")
    oc, oh, wh, tw = P(o0.get("client")), P(o0.get("host")), lv.get("where") or {}, lv.get("twice") or {}
    ent, hh = qk.get("entries") or [], qk.get("host")
    e1 = ent[0][1] if len(ent) == 1 else None
    w = {n: wh.get(n) or {} for n in (g, g2, gu)}
    gid = ((ev.get("gift") or {}).get("soldier") or [None, None])[1]
    ids = (rid + "-ids", "GUARD", "ids_twice empty on both machines: %s" % tw, "host" in tw and not tw["host"] and not tw["client"])
    filed = "QUICK entries %d, host half %s %s, client entry %s %s" % (len(ent), g, cnt(hh, g), g, cnt(e1, g))
    if rid == "R16":
        st = (ev.get("stored back") or {}).get("entry")
        return [("R16-stored", "RED", "stored(back) holds every own0(client) pair and no %s: missing %s, %s %d" % (
                    g, sorted(oc - PS(st)) if st else st, g, cnt(st, g)), st is not None and oc <= PS(st) and cnt(st, g) == 0),
                ("R16-own", "RED", "after the leave every own0(client) pair on the client's own bases: missing %s" % sorted(oc - P(lv.get("client"))),
                 "client" in lv and oc <= P(lv["client"])),
                ("R16-client", "RED", "%s on none of the client's own bases: %s" % (g, w[g].get("client")), w[g].get("client") == []),
                ("R16-host", "GUARD", "%s once on the host's own bases under the giver's id %s: %s; host ids %s = own0(host) ids %s" % (
                    g, gid, w[g].get("host"), ids_of(lv.get("host")), ids_of(o0.get("host"))),
                 len(w[g].get("host") or []) == 1 and w[g]["host"][0][1] == gid and ids_of(lv.get("host")) == ids_of(o0.get("host"))),
                ids,
                ("R16-file", "RED", filed + ", own0(client) pairs missing from it %s" % (sorted(oc - PS(e1)) if e1 is not None else None),
                 e1 is not None and cnt(hh, g) == 1 and cnt(e1, g) == 0 and oc <= PS(e1))]
    if rid == "R16H":
        return [("R16H-host", "RED", "after the host's leave %s on none of the host's own bases: %s" % (g, w[g].get("host")), w[g].get("host") == []),
                ("R16H-own", "GUARD", "every own0(host) pair on the host's own bases: missing %s" % sorted(oh - P(lv.get("host"))),
                 "host" in lv and oh <= P(lv["host"])),
                ("R16H-client", "GUARD", "%s once on the client's own bases under the giver's id %s: %s; client ids %s = own0(client) ids %s" % (
                    g, gid, w[g].get("client"), ids_of(lv.get("client")), ids_of(o0.get("client"))),
                 len(w[g].get("client") or []) == 1 and w[g]["client"][0][1] == gid and ids_of(lv.get("client")) == ids_of(o0.get("client"))),
                ids,
                ("R16H-file", "RED", filed, e1 is not None and cnt(hh, g) == 0 and cnt(e1, g) == 1)]
    s1, s2, s3 = ((ev.get("stored " + k) or {}).get("entry") for k in ("g1", "g2", "send"))
    rest = {p for p in oc if p[1] != gu}
    return [("R17-g1", "GUARD", "stored(g1): %s %d, own0(client) pairs missing %s" % (g, cnt(s1, g), sorted(oc - PS(s1)) if s1 else s1),
             s1 is not None and cnt(s1, g) == 1 and oc <= PS(s1)),
            ("R17-g2", "RED", "stored(g2): %s %d, %s %d, own0(client) pairs missing %s" % (g, cnt(s2, g), g2, cnt(s2, g2), sorted(oc - PS(s2)) if s2 else s2),
             s2 is not None and cnt(s2, g) == 1 and cnt(s2, g2) == 1 and oc <= PS(s2)),
            ("R17-send", "RED", "stored(send): %s %d, %s %d, %s %d, other own0(client) pairs missing %s" % (
                g, cnt(s3, g), g2, cnt(s3, g2), gu, cnt(s3, gu), sorted(rest - PS(s3)) if s3 else s3),
             s3 is not None and cnt(s3, g) == 1 and cnt(s3, g2) == 1 and cnt(s3, gu) == 0 and rest <= PS(s3)),
            ("R17-leave", "GUARD", "after the leave client %s %s, %s %s, %s %s; host %s %s" % (
                g, w[g].get("client"), g2, w[g2].get("client"), gu, w[gu].get("client"), gu, w[gu].get("host")),
             len(w[g].get("client") or []) == 1 and len(w[g2].get("client") or []) == 1 and w[gu].get("client") == []
             and len(w[gu].get("host") or []) == 1),
            ("R17-file", "GUARD", "QUICK entries %d: client entry %s %d %s %d %s %d; host half %s %d %s %d %s %d" % (
                len(ent), g, cnt(e1, g), g2, cnt(e1, g2), gu, cnt(e1, gu), g, cnt(hh, g), g2, cnt(hh, g2), gu, cnt(hh, gu)),
             e1 is not None and cnt(e1, g) == 1 and cnt(e1, g2) == 1 and cnt(e1, gu) == 0 and cnt(hh, g) == 0 and cnt(hh, g2) == 0
             and cnt(hh, gu) == 1),
            ids]


def run_d(rid, tag, key, build, ids, pre):
    """HB run_row_b with cells_d (no reload)"""
    return run_row_b(rid, tag, key, build, ids, cells_d, pre)
