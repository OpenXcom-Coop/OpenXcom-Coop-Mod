"""OF2 S-C - the second player's after-battle "return from mission" mod script reads the research of the player who owns
the soldier, and the soldier tags it writes reach that player's own world (owner D266 (c), D268 (b), extending D263 (a)
and D155 (a); spec docs rewrite/prompts/of2_mod_script_player_reads.md, AMENDMENT OF2-2 section 5 as AMENDMENT OF2-4
section 5 amends it; TASK 0 docs rewrite/of2-task0/sc/CONSTANTS.md; F11335, F12862, F12863, F12869, F12876,
F12980-F12999).
In a SEPARATE campaign with research sync off the host builds the battle-end debriefing for both players' soldiers. The
test MOD Coop_ScriptResearch_Test (both machines) adds a returnFromMissionUnit script: the GeoscapeSoldier tag
COOP_SR_RET = 1 + isResearched(STR_PLASMA_PISTOL) read through battle_game.getGeoscapeGame, and recovery_time = 100 x
that number: "1" / 100 = the host's research, "2" / 200 = the second player's, no tag = the script never ran. The
client researched STR_PLASMA_PISTOL, the host did not (CR's boot). The returning record (D155's keys) carries the host
copy's results to the client's own soldier at the client's OK.
ONE boot (test_client_research's research-separate guest battle, lobby key 48999, the MOD on both machines, the
client's own soldier id guest_id kept), then four rows in this order:
  SD0  the ending: host battle_action kill_unit_real on every live hostile (chain_settled after each), end_turn_both,
       close_host_nextturn, the host's DebriefingState within 60 s. SD0-guard (a miss = FIXTURE-STOP): G by name
       (coop 1) and H (the first host soldier, coop 0); researchMode == CR.MODE_WANT and seats[1].stored on both; the
       mod-active line in both engine logs; desyncSeen false on both before the ending; every kill settled; the host's
       debrief_state shown, onTop, not displayOnly, title TITLE; the host's battleEnd reason aliensDown, not aborted;
       the client's display-only DebriefingState within 20 s; COPY (the FIRST host soldier_record "Guest Zzz") alive;
       HREC (the FIRST host soldier_record id H) where "base", coop 0; COPY.recovery in {100, 200}, HREC.recovery 100;
       HREC tags.COOP_SR_RET "1", COPY's in {"1", "2"}.
  SD1  SD1-G: COPY.recovery == 200. SD1-tag: COPY tags.COOP_SR_RET == "2" (its owner's research).
  SD2  SD2-H: HREC.recovery == 100 (the host's soldier keeps the host's research).
  SD3  SD3-ok: the client's OK through its follow-ups -> geo_clean. SD3-own: the FIRST client soldier_record id
       guest_id (read only after the OK, F12876), alive, recovery == 200 and == COPY.recovery. SD3-tag: that record's
       tags.COOP_SR_RET present, != "0" and == COPY's (D268 (b): the tag reached the owner's world).
RED (C1, the base): exactly SD1-G, SD1-tag, SD3-own, SD3-tag FAIL (COPY 100 / "1", the client's own 100 / no tag).
GREEN (C2): every cell PASS (7/7).
Tags are read through soldier_record's read-only `tags` field (AMENDMENT OF2-4 ED1). Each row prints ONE
"EVIDENCE <row>:" line, one PASS/FAIL line per cell, then its verdict; every row runs after a failure. A boot failure
or an SD0 guard miss prints ONE "CAPTURE <what>:" line and fails every later row.
ONE foreground run, no skip path; exit 0 only when every cell passes, 2 otherwise.
Run:  python tools/coop_test/test_script_research_debrief.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral
import test_client_research as CR
from test_battle_end_separate import (chain_settled, end_turn_both, close_host_nextturn, soldier_recs, record, stack,
                                         wait_until, geo_clean, client_ok_through_followups)
from test_delta_core import both, short

PORT = "48999"
HOST_DIR, CLIENT_DIR = "of2_script_debrief_host", "of2_script_debrief_client"
MOD_NAME = "Coop_ScriptResearch_Test"                  # NEW's MOD (test_script_research.py at the base)
MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", MOD_NAME)
MOD_ACTIVE_LINE = "- Coop_ScriptResearch_Test v1.0"
TAG = "COOP_SR_RET"               # the MOD's GeoscapeSoldier tag (its only writer: returnFromMissionUnit)
HOST_TAG, OWNER_TAG = "1", "2"    # 1 + isResearched(STR_PLASMA_PISTOL): the host's research / the second player's
HOST_REC, OWNER_REC = 100, 200    # recovery_time = 100 x the tag
TITLE = "Aliens defeated"         # the host's debrief title (T0-C3: 3 boots)
REASON = "aliensDown"
FACTION_HOSTILE = 1
KILL_S = 45                       # chain_settled per kill (TASK 0: 2.5-7.4 s)
DEBRIEF_S = 60                    # the host's DebriefingState after the ending (TASK 0: 0.06 s after close_host_nextturn)
CLIENT_DEBRIEF_S = 20             # the client's display-only DebriefingState (TASK 0: 0.06 s)
CELLS = {"SD0": ("SD0-guard",), "SD1": ("SD1-G", "SD1-tag"), "SD2": ("SD2-H",),
         "SD3": ("SD3-ok", "SD3-own", "SD3-tag")}


def pairs(host, client):
    return (("host", host), ("client", client))


def log_lines(gc):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


def hostiles(gc):
    return [u["id"] for u in battle_state(gc).get("units", []) if u.get("faction") == FACTION_HOSTILE
            and not u.get("isOut")]


def rview(r):
    return {k: (r or {}).get(k) for k in ("where", "baseIndex", "id", "name", "coop", "owner", "dead", "recovery",
                                          "healthMissing", "missions", "tags")}


def tag_of(r):
    return ((r or {}).get("tags") or {}).get(TAG)


def capture(host, client, what):
    cap = {}
    for n, gc in pairs(host, client):
        cap[n] = {"log": log_lines(gc)[-40:]}
        for c in ("get_state", "battle_state", "event_state", "coop_dialog_info", "debrief_state"):
            try:
                cap[n][c] = gc.cmd({"cmd": c})
            except Exception as e:
                cap[n][c] = f"error {short(e)}"
    print(f"CAPTURE {what}: {json.dumps(cap, default=str)}", flush=True)


def joined(fails):
    return "; ".join(fails) or None


def boot(host, client):   # = CR's boot (CR :1525-:1576) with lobby key PORT; guest_id kept (AMENDMENT OF2-2 section 5)
    ctx, pre_rec = {}, {}

    def pre(h, c):
        for gc, topics in ((c, CR.CLIENT_TOPICS), (h, CR.HOST_TOPICS), (c, CR.PEDIA_CLIENT_TOPICS),
                           (h, CR.PEDIA_HOST_TOPICS)):
            for t in topics:
                gc.ok({"cmd": "discover_research", "topic": t})
        pre_rec["isr"] = CR.isr_all(h, c)
        pre_rec["Nh"] = (CR.rmode(h) or {}).get("liveCount")
        pre_rec["Nc"] = (CR.rmode(c) or {}).get("liveCount")

    for gc in (host, client):
        gc.spawn()
        gc.connect()
    _squad, ctx["guestId"] = session.bring_up_separate_guest_battle(host, client, port=PORT, pre_mission_start=pre)
    session.wait_host_idle(host, client, timeout=30)
    ctx["preIsr"], ctx["Nh"], ctx["Nc"] = pre_rec.get("isr"), pre_rec.get("Nh"), pre_rec.get("Nc")
    hs, cs = battle_state(host), battle_state(client)
    gh = [u for u in hs.get("units", []) if u.get("name") == CR.GUEST_NAME]
    gc_ = [u for u in cs.get("units", []) if u.get("name") == CR.GUEST_NAME]
    ctx["gView"] = {"host": [(u.get("id"), u.get("coop")) for u in gh], "client": [(u.get("id"), u.get("coop")) for u in gc_]}
    assert len(gh) == 1 and len(gc_) == 1 and gh[0]["id"] == gc_[0]["id"], (
        f"guest {CR.GUEST_NAME!r} by name: {ctx['gView']} (want exactly one, the same id)")
    ctx["G"], ctx["gCoop"] = gh[0]["id"], gh[0].get("coop")
    hsold = sorted(u["id"] for u in hs.get("units", []) if u.get("isPlayerSoldier") and u.get("coop") == 0
                   and u.get("name") != CR.GUEST_NAME and not u.get("isOut"))
    assert hsold, "no host soldier (coop 0, not out) for H"
    ctx["H"] = hsold[0]
    pinned = pin_ai_neutral(host, client, tag="of2-sd")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": ctx["G"], "stat": "firing",
                        "value": CR.FIRING_PIN}, ("tu",))
    ctx["guard"] = {}
    for n, gc in pairs(host, client):
        m = CR.rmode(gc)
        ctx["guard"][n] = {"mode": {k: (m or {}).get(k) for k in CR.MODE_WANT}, "seat1": CR.seat_entry(m, 1),
                           "modActive": sum(1 for ln in log_lines(gc) if MOD_ACTIVE_LINE in ln)}
    session.wait_host_idle(host, client, timeout=30)
    session.assert_hash_clean(host, client, full=True, what="bring-up")
    ctx["pinned"], ctx["localSeat"] = len(pinned), event_state(client).get("localSeat")
    return ctx


def row_sd0(ev, res, host, client, st):
    ctx, f = st["ctx"], []
    G, H = ctx["G"], ctx["H"]
    ev["boot"] = {k: ctx.get(k) for k in ("guestId", "G", "gCoop", "H", "gView", "guard", "pinned", "localSeat", "preIsr",
                                          "Nh", "Nc")}
    if ctx["gCoop"] != 1:
        f.append(f"G ({G}) coop {ctx['gCoop']} (want 1)")
    hu = session.units_by_id(battle_state(host)).get(H) or {}
    if hu.get("coop") != 0 or hu.get("isOut"):
        f.append(f"H ({H}) coop {hu.get('coop')} isOut {hu.get('isOut')} (want coop 0, not out)")
    for n, g in ctx["guard"].items():
        if g["mode"] != CR.MODE_WANT:
            f.append(f"{n} researchMode {g['mode']} (want {CR.MODE_WANT})")
        if (g["seat1"] or {}).get("stored") is not True:
            f.append(f"{n} seats[1] {g['seat1']} (want stored true)")
        if g["modActive"] < 1:
            f.append(f"{n} engine log has no {MOD_ACTIVE_LINE!r} line")
    ds = {n: event_state(gc).get("desyncSeen") for n, gc in pairs(host, client)}
    ev["desyncBefore"] = ds
    if any(ds.values()):
        f.append(f"desyncSeen before the ending {ds} (want false on both)")
    # the ending (the C28P-dead / R4-L2 CR4 shape, seed-independent)
    kills = []
    for uid in hostiles(host):
        r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": uid})
        ok, secs, _samples = chain_settled(host, client, stable=1.0, timeout=KILL_S, want_live=None)
        kills.append([uid, r.get("killed"), ok, secs])
    ev["kills"], ev["liveAfter"] = kills, hostiles(host)
    if not kills or not all(k[2] for k in kills):
        f.append(f"kills {kills} (want >= 1 hostile, every chain settled within {KILL_S} s)")
    end_turn_both(host, client)
    nt = close_host_nextturn(host)
    ev["nextTurn"] = None if nt is None else {k: nt.get(k) for k in ("ok", "handled", "error")}
    dok, dsecs = wait_until(lambda: "DebriefingState" in stack(host), DEBRIEF_S)
    hdeb = host.cmd({"cmd": "debrief_state"})
    ev["hostDebrief"] = {"reached": dok, "secs": dsecs, "stack": stack(host),
                         "view": {k: hdeb.get(k) for k in ("shown", "onTop", "displayOnly", "title")}}
    if not dok:
        f.append(f"no host DebriefingState within {DEBRIEF_S} s of the ending (stack {stack(host)})")
    want = {"shown": True, "onTop": True, "displayOnly": False, "title": TITLE}
    f += [f"host debrief_state.{k}={hdeb.get(k)!r} (want {w!r})" for k, w in want.items() if hdeb.get(k) != w]
    be = record(host)
    ev["battleEnd"] = {k: be.get(k) for k in ("reason", "aborted", "inExitArea")}
    if be.get("reason") != REASON or be.get("aborted") is not False:
        f.append(f"host battleEnd {ev['battleEnd']} (want reason {REASON}, aborted False)")
    cok, csecs = wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                     and d.get("displayOnly") is True)(client.cmd({"cmd": "debrief_state"})),
                            CLIENT_DEBRIEF_S)
    ev["clientDebrief"] = {"reached": cok, "secs": csecs, "stack": stack(client)}
    if not cok:
        f.append(f"the client showed no display-only DebriefingState within {CLIENT_DEBRIEF_S} s (stack {stack(client)})")
    copies, hrecs = soldier_recs(host, name=CR.GUEST_NAME)[0], soldier_recs(host, sid=H)[0]
    st["copy"] = copy = copies[0] if copies else {}
    st["hrec"] = hrec = hrecs[0] if hrecs else {}
    ev["COPY"], ev["HREC"] = [rview(r) for r in copies], [rview(r) for r in hrecs]
    if not copy or copy.get("dead"):
        f.append(f"COPY (the first host {CR.GUEST_NAME!r} record) {rview(copy)} (want an alive record)")
    if hrec.get("where") != "base" or hrec.get("coop") != 0:
        f.append(f"HREC (the first host record id {H}) {rview(hrec)} (want where base, coop 0)")
    if copy.get("recovery") not in (HOST_REC, OWNER_REC) or hrec.get("recovery") != HOST_REC:
        f.append(f"recovery COPY {copy.get('recovery')} HREC {hrec.get('recovery')} (want COPY in {{{HOST_REC}, "
                 f"{OWNER_REC}}} and HREC {HOST_REC}: else the after-battle script never ran)")
    if tag_of(hrec) != HOST_TAG or tag_of(copy) not in (HOST_TAG, OWNER_TAG):
        f.append(f"{TAG} COPY {tag_of(copy)!r} HREC {tag_of(hrec)!r} (want COPY in {{{HOST_TAG!r}, {OWNER_TAG!r}}} and "
                 f"HREC {HOST_TAG!r}: else the soldier-tag write never ran)")
    res["SD0-guard"] = joined(f)


def row_sd1(ev, res, host, client, st):
    copy = st["copy"]
    ev["COPY"] = rview(copy)
    res["SD1-G"] = None if copy.get("recovery") == OWNER_REC else (
        f"COPY.recovery {copy.get('recovery')} (want {OWNER_REC}: the second player's soldier's after-battle script "
        f"reads its owner's research; {HOST_REC} = the host's)")
    res["SD1-tag"] = None if tag_of(copy) == OWNER_TAG else (
        f"COPY tags.{TAG} {tag_of(copy)!r} (want {OWNER_TAG!r}: its owner's research; {HOST_TAG!r} = the host's)")


def row_sd2(ev, res, host, client, st):
    hrec = st["hrec"]
    ev["HREC"] = rview(hrec)
    res["SD2-H"] = None if hrec.get("recovery") == HOST_REC else (
        f"HREC.recovery {hrec.get('recovery')} (want {HOST_REC}: the host's soldier keeps the host's research)")


def row_sd3(ev, res, host, client, st):
    copy, kctx = st["copy"], {}
    ok1, at_geo, secs = client_ok_through_followups(client, kctx, "ret")
    ev["ok"] = {"press": ok1, "geoClean": at_geo, "secs": secs, "chain": (kctx.get("ret") or {}).get("clientChain"),
                "stack": stack(client), "sepReturn": record(client).get("sepReturn")}
    res["SD3-ok"] = None if ok1.get("pressed") is True and at_geo else (
        f"the client's OK {ok1} -> geo_clean {at_geo} after {secs} s (stack {stack(client)})")
    owns = soldier_recs(client, sid=st["ctx"]["guestId"])[0]   # its own world exists only after its OK
    own = owns[0] if owns else {}
    ev["OWN"], ev["COPY"] = [rview(r) for r in owns], rview(copy)
    ev["crashNew"] = sorted(session._crash_log_snapshot() - st["crash0"])
    f = []
    if not own or own.get("dead"):
        f.append(f"the client's own record id {st['ctx']['guestId']} {rview(own)} (want an alive record)")
    if own.get("recovery") != OWNER_REC or own.get("recovery") != copy.get("recovery"):
        f.append(f"own recovery {own.get('recovery')} COPY {copy.get('recovery')} (want {OWNER_REC} on both: the "
                 f"owner's research, carried home by D155's record)")
    res["SD3-own"] = joined(f)
    t = tag_of(own)
    res["SD3-tag"] = None if (t is not None and t != "0" and t == tag_of(copy)) else (
        f"own tags.{TAG} {'absent' if t is None else repr(t)} vs COPY's {tag_of(copy)!r} (want present, not '0', equal "
        f"to COPY's: D268 (b), the soldier's tags come home)")


ROWS = (("SD0", row_sd0), ("SD1", row_sd1), ("SD2", row_sd2), ("SD3", row_sd3))


def report(rid, ev, res):
    print(f"EVIDENCE {rid}: {json.dumps(ev, default=str)}", flush=True)
    for c in CELLS[rid]:
        f = res.get(c, "not reached")
        print(f"PASS {c}" if f is None else f"FAIL {c}: {f}", flush=True)
    bad = [c for c in CELLS[rid] if res.get(c, "not reached") is not None]
    print(f"PASS {rid}" if not bad else f"FAIL {rid}: {', '.join(bad)}", flush=True)
    return bad


def run_row(rid, fn, host, client, st):
    ev, res = {}, {}
    try:
        fn(ev, res, host, client, st)
    except Exception as e:
        ev["error"] = msg = short(e, 500)
        for c in CELLS[rid]:
            res.setdefault(c, f"the row raised before this cell: {msg}")
    return report(rid, ev, res)


def fail_rest(rids, why):
    out = []
    for rid in rids:
        out += report(rid, {"error": why}, {c: why for c in CELLS[rid]})
    return out


def main():
    t_start = time.time()
    host = GameClient("host", 1, make_user_dir(HOST_DIR, mods=[MOD_DIR], options=CR.HOST_OPTIONS))
    client = GameClient("client", 2, make_user_dir(CLIENT_DIR, mods=[MOD_DIR], options=CR.CLIENT_OPTIONS))
    failed = []
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:
            print(f"boot failed: {short(e, 600)}", flush=True)
            capture(host, client, "boot")
            failed += fail_rest([rid for rid, _ in ROWS], "boot")
        else:
            st = {"ctx": ctx, "crash0": session._crash_log_snapshot()}
            failed += run_row("SD0", row_sd0, host, client, st)
            if failed:
                capture(host, client, "SD0")
                failed += fail_rest([rid for rid, _ in ROWS[1:]], "the SD0 guard missed (FIXTURE-STOP)")
            else:
                for rid, fn in ROWS[1:]:
                    failed += run_row(rid, fn, host, client, st)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[of2-sd] shutdown {gc.name}: {short(e)}", flush=True)
    n = sum(len(v) for v in CELLS.values())
    print(f"\ntest_script_research_debrief: {n - len(failed)}/{n} cells passed (fail={failed}) in "
          f"{round(time.time() - t_start, 1)} s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
