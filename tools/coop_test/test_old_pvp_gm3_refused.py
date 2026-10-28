"""D246-U stage S-C2 - test_old_pvp_gm3_refused.py: a gm3 PvP campaign (the host plays the aliens, the second player X-COM)
that an OLDER version (the release line v2.0.x, unstamped) saved mid-battle keeps refusing at the host's menu load, and ONLY that
refusal's text gains where to ask for a repair (owner D284 (c) amended; VL-D284-1). Every other save that reaches the same refusal keeps
today's text: a battle save stamped by a newer rewrite build, and an unstamped save of a mode with no conversion.
Spec: docs repo rewrite/prompts/d246u_sc2_gm3_refusal_text.md section (f) and its ORCHESTRATOR RULINGS (QSC2-1 .. QSC2-6 (a)). Pins:
rewrite/d246u-task0/sc2/CONSTANTS.md (TASK 0 T0-1 .. T0-4, T0-W on the unchanged build).
Each row is ONE host with no client (the refusal comes at the menu load, before any session; no lobby key, QSC2-3), spawned, the row,
shut down. The load is load_save_menu (the LoadGameState LOAD GAME pushes); the box is read with list_widgets once its Text is no
longer hidden (the popup window hides every surface while it opens); OK is the real button (click_widget), never dismiss_popup.
Row G3 (dir d246sc2_g3_host): tools/coop_test/fixtures/pvp_gm3_battle.sav (copied, never edited).
  G3-refused ErrorMessageState is the top within LOAD_S; no HostMenu / LobbyMenu / BattlescapeState in the stack; exactly 1 refusal
             line and 0 [coop-convert] lines in the host log
  G3-text    one TextButton OK_CAPTION; one Text == HEADER + SEP + TEXT_GM3, visible and not hidden; the log line's last tab field
             == TEXT_GM3. Then a screenshot to <host dir>/d246sc2_g3_box.png (EVIDENCE shot, never a cell)
  G3-ok      the real OK -> MainMenuState the top within OK_S, no ErrorMessageState; world_state.has_save false
Row N2S (dir d246sc2_n2s_host; VL-D284-2, stamped newer): FX-N2S = the fixture's working copy with ONE header line
  `coopBattleProtocol: 2` + the file's own line ending inserted before the first `---` line, as d246sc2_n2s.sav.
  N2S-text   refused as G3-refused; the box == HEADER + SEP + TODAY, one TextButton OK_CAPTION; log field == TODAY; OK -> MainMenuState
Row N2M (dir d246sc2_n2m_host; VL-D284-2, another unconverted mode): FX-N2M = the working copy with the body's ONE
  `coop_gamemode: 3` line -> `coop_gamemode: 5` (header 0, line ending kept), as d246sc2_n2m.sav.
  N2M-text   as N2S-text
C-common (after the three rows): 0 new crash files since the start; every host alive at its row's end; no save file in any host dir
  beyond the one its row placed.
RED (R1, the unchanged build): exit 2, 5/6 - FAIL G3-text only (today's text in the box and in the log). GREEN (G1, E1): 6/6.
One EVIDENCE line per row, one PASS / FAIL line per cell, one ROW line per row; every row runs after a failure; a precondition miss
ends its row (later cells "not reached"); a boot miss prints ONE CAPTURE line and FAILs the row's cells "boot". run in the
foreground to completion. ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_old_pvp_gm3_refused.py
"""

import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import test_campaign_resume_roles as RR  # noqa: E402  (pure helpers: capture, stack, top, crash_set, wait, alive)

# ----- pins (docs rewrite/d246u-task0/sc2/CONSTANTS.md) -----
TODAY = ("This mid-battle co-op save was made by a different version of the mod and cannot be resumed. "
         "Finish or abandon the battle on the version that saved it.")
TEXT_GM3 = TODAY[:-1] + (", or ask the developers to repair your save by opening an issue at "
                         "https://github.com/OpenXcom-Coop/OpenXcom-Coop-Mod/issues")
VL_D284_1 = ("This mid-battle co-op save was made by a different version of the mod and cannot be resumed. Finish or abandon the battle "
             "on the version that saved it, or ask the developers to repair your save by opening an issue at "
             "https://github.com/OpenXcom-Coop/OpenXcom-Coop-Mod/issues")
REFUSAL = "different version of the mod"
CONVERT = "[coop-convert]"
HEADER, SEP, OK_CAPTION = "Load failed", "\x02", "OK"
LOAD_S, LOG_S, OK_S, POPUP_S = 30, 10, 30, 5
SHOT_SETTLE = 0.5                      # one drawn frame after the popup ends before the evidence screenshot (TASK 0: 0.5 s)
G3_SAVE = os.path.join(HERE, "fixtures", "pvp_gm3_battle.sav")
TAGS = {"G3": "d246sc2_g3", "N2S": "d246sc2_n2s", "N2M": "d246sc2_n2m"}
FILES = {"G3": os.path.basename(G3_SAVE), "N2S": "d246sc2_n2s.sav", "N2M": "d246sc2_n2m.sav"}
AWAY = ("HostMenu", "LobbyMenu", "BattlescapeState")
ROWS = {"G3": ["G3-refused", "G3-text", "G3-ok"], "N2S": ["N2S-text"], "N2M": ["N2M-text"]}
ALL = ROWS["G3"] + ROWS["N2S"] + ROWS["N2M"] + ["C-common"]
RED = {"G3-text"}
stack, top, crash_set, wait, alive = RR.stack, RR.top, RR.crash_set, RR.wait, RR.alive
if TEXT_GM3 != VL_D284_1:  # character for character (spec (f))
    print(f"FAIL setup: TEXT_GM3 {TEXT_GM3!r} != VL-D284-1 {VL_D284_1!r}", flush=True)
    sys.exit(2)


class FixtureMiss(Exception):
    pass


RESULTS = []          # (cell, ok, detail)
ROW_END = {}          # row -> {"alive": bool, "dir": user dir, "placed": relpath}


def cell(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)


def block(names, why):
    for n in names:
        if n not in {x[0] for x in RESULTS}:
            cell(n, False, why)


def capture_boot(row, err, host):
    print(f"CAPTURE {row}: {json.dumps(RR.capture(err, host), sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def log_text(gc):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def fx(row, data):
    """FX-N2S / FX-N2M on the working copy's bytes (its own line ending); a miss is a FixtureMiss. Returns the new bytes."""
    sep, stamp = rb"(?m)^---(\r?)$", rb"(?m)^coopBattleProtocol:"
    seps = list(re.finditer(sep, data))
    if len(seps) != 1:
        raise FixtureMiss(f"FX-{row}: {len(seps)} separator line(s) (want 1)")
    m = seps[0]
    if row == "N2S":
        eol = b"\r\n" if m.group(1) else b"\n"
        new = data[:m.start()] + b"coopBattleProtocol: 2" + eol + data[m.start():]
        ns = list(re.finditer(sep, new))
        counts = (len(re.findall(stamp, data[:m.start()])), len(re.findall(stamp, new[:ns[0].start()])) if len(ns) == 1 else -1)
        if counts != (0, 1):
            raise FixtureMiss(f"FX-N2S: header stamp count {counts[0]} -> {counts[1]} (want 0 -> 1)")
        return new
    pat = rb"(?m)^coop_gamemode: 3(\r?)$"
    body, n = re.subn(pat, rb"coop_gamemode: 5\1", data[m.end():])
    nh = len(re.findall(pat, data[:m.end()]))
    if n != 1 or nh != 0:
        raise FixtureMiss(f"FX-N2M: {n} body replacement(s), {nh} header line(s) (want 1 / 0)")
    return data[:m.end()] + body


def box(host):
    """The box read: list_widgets until its state ends with ErrorMessageState and its one Text is not hidden (POPUP_S)."""
    seen = {}

    def shown():
        r = seen["r"] = host.cmd({"cmd": "list_widgets"})
        tx = [w for w in r.get("widgets") or [] if (w.get("type") or "").endswith("::Text")]
        return ((r.get("state") or "").endswith("ErrorMessageState") and len(tx) == 1 and tx[0].get("hidden") is False) or None
    ok, s = wait(shown, POPUP_S, 0.05)
    r = seen.get("r") or {}
    ws = r.get("widgets") or []
    tx = [w for w in ws if (w.get("type") or "").endswith("::Text")]
    return {"shown": bool(ok), "s": s, "state": r.get("state"), "texts": [w.get("text") for w in tx],
            "buttons": [w.get("text") for w in ws if (w.get("type") or "").endswith("::TextButton")],
            "textVisHidden": [[w.get("visible"), w.get("hidden")] for w in tx]}


def log_read(host):
    """The host log's lines holding REFUSAL, polled until their count is 1 (LOG_S); the last tab field; the convert count."""
    got = {}

    def one():
        got["l"] = [ln for ln in log_text(host).splitlines() if REFUSAL in ln]
        return len(got["l"]) >= 1 or None
    _, s = wait(one, LOG_S, 0.1)
    lines = got.get("l") or []
    return {"s": s, "refusal": len(lines), "last": lines[-1].split("\t")[-1] if lines else None,
            "convert": sum(1 for ln in log_text(host).splitlines() if CONVERT in ln)}


def load(host, row, ev):
    """load_save_menu; ErrorMessageState the top (or a state AWAY from the menu) within LOAD_S; the box read; the log read.
    Returns (the box read or None, the refused-problems list)."""
    host.ok({"cmd": "load_save_menu", "file": FILES[row]})

    def landed():
        st = stack(host)
        return (bool(st) and st[-1] == "ErrorMessageState") or any(x in st for x in AWAY) or None
    _, s = wait(landed, LOAD_S, 0.05)
    st = stack(host)
    is_box = bool(st) and st[-1] == "ErrorMessageState"
    b = box(host) if is_box else None
    lg = log_read(host)
    ev.update(stack=st, boxS=s, box=b, log=lg)
    bad = [] if is_box else [f"top {st[-1] if st else None} after {s} s (want ErrorMessageState within {LOAD_S} s)"]
    bad += [f"stack {st} holds {[x for x in AWAY if x in st]}"] if any(x in st for x in AWAY) else []
    bad += [f"{lg['refusal']} refusal line(s) in the host log (want 1)"] if lg["refusal"] != 1 else []
    bad += [f"{lg['convert']} {CONVERT} line(s) in the host log (want 0)"] if lg["convert"] else []
    return b, bad


def text_bad(b, lg, want):
    if b is None:
        return ["not reached: no ErrorMessageState"]
    bad = [] if b["shown"] else [f"the box's Text not shown within {POPUP_S} s (state {b['state']}, visible/hidden {b['textVisHidden']})"]
    bad += [] if b["buttons"] == [OK_CAPTION] else [f"TextButtons {b['buttons']} (want [{OK_CAPTION!r}])"]
    bad += [] if b["texts"] == [HEADER + SEP + want] else [f"box Text {b['texts']!r} (want [{HEADER + SEP + want!r}])"]
    bad += [] if b["textVisHidden"] == [[True, False]] else [f"Text visible/hidden {b['textVisHidden']} (want [[True, False]])"]
    bad += [] if lg["last"] == want else [f"log line's last field {lg['last']!r} (want {want!r})"]
    return bad


def press_ok(host, ev):
    """The real OK (click_widget by caption) -> MainMenuState the top within OK_S, no ErrorMessageState. Returns the problems list."""
    r = host.cmd({"cmd": "click_widget", "match": OK_CAPTION})

    def menu():
        st = stack(host)
        return (bool(st) and st[-1] == "MainMenuState" and "ErrorMessageState" not in st) or None
    got, s = wait(menu, OK_S, 0.05)
    st, ws = stack(host), host.cmd({"cmd": "world_state"})
    ev["ok"] = {"click": r, "s": s, "stack": st, "has_save": ws.get("has_save")}
    bad = [] if r.get("ok") else [f"click_widget {r}"]
    bad += [] if got else [f"stack {st} {s} s after OK (want MainMenuState the top, no ErrorMessageState, within {OK_S} s)"]
    return bad


def row_g3(host, ev):
    b, bad = load(host, "G3", ev)
    cell("G3-refused", not bad, "; ".join(bad) or f"ErrorMessageState the top after {ev['boxS']} s, stack {ev['stack']}; "
         "1 refusal line, 0 convert lines")
    if b is None:
        block(ROWS["G3"][1:], "not reached: no ErrorMessageState (G3-refused)")
        return
    tbad = text_bad(b, ev["log"], TEXT_GM3)
    cell("G3-text", not tbad, "; ".join(tbad) or "one TextButton OK; the box Text == HEADER + SEP + TEXT_GM3 (VL-D284-1), visible, "
         f"shown after {b['s']} s; the log field == TEXT_GM3")
    time.sleep(SHOT_SETTLE)
    shot = os.path.join(host.user_dir, "d246sc2_g3_box.png")
    r = host.cmd({"cmd": "screenshot", "path": shot})
    ev["shot"] = shot if r.get("ok") else r
    obad = press_ok(host, ev)
    obad += [f"world_state.has_save {ev['ok']['has_save']!r} (want False)"] if ev["ok"]["has_save"] is not False else []
    cell("G3-ok", not obad, "; ".join(obad) or f"OK -> MainMenuState after {ev['ok']['s']} s, no ErrorMessageState; has_save false")


def row_neg(row):
    def fn(host, ev):
        b, bad = load(host, row, ev)
        bad += text_bad(b, ev["log"], TODAY)
        if b is not None:
            bad += press_ok(host, ev)
        cell(f"{row}-text", not bad, "; ".join(bad) or f"refused (ErrorMessageState after {ev['boxS']} s, 1 refusal line, 0 convert "
             f"lines); the box == HEADER + SEP + TODAY with one TextButton OK; the log field == TODAY (VL-D284-2); OK -> MainMenuState "
             f"after {ev['ok']['s']} s")
    return fn


def run_row(row, fn):
    """One row: the host's user dir (G3: the fixture; N2S / N2M: the FX file), spawn + connect, the row, the host shut down."""
    d = make_user_dir(TAGS[row] + "_host", saves=(G3_SAVE,) if row == "G3" else ())
    host = GameClient("host", None, d)
    ROW_END[row] = {"alive": False, "dir": d, "placed": os.path.join("xcom1", FILES[row])}
    ev, t0 = {"file": FILES[row]}, time.time()
    try:
        if row != "G3":
            with open(G3_SAVE, "rb") as f:
                try:
                    data = fx(row, f.read())
                except FixtureMiss as e:
                    capture_boot(row, str(e), host)
            with open(os.path.join(d, "xcom1", FILES[row]), "wb") as f:
                f.write(data)
            ev["fx"] = {"bytes": len(data), "crlf": data.count(b"\r\n")}
        try:
            host.spawn(); host.connect()
        except Exception as e:  # noqa: BLE001
            capture_boot(row, f"spawn / connect: {type(e).__name__}: {str(e)[:300]}", host)
        fn(host, ev)
    except FixtureMiss as e:
        block(ROWS[row], f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"[ERROR] row {row}: {err}", flush=True)
        print(f"CAPTURE {row}: {json.dumps(RR.capture(err, host), sort_keys=True, default=str)}", flush=True)
        block(ROWS[row], f"boot (error {err[:200]})")
    finally:
        ROW_END[row]["alive"] = alive(host)
        ev["wall"] = round(time.time() - t0, 1)
        print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
        bad = [n for n, ok, _ in RESULTS if n in ROWS[row] and not ok]
        print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)
        try:
            if host.proc is not None and host.proc.poll() is None:
                host.shutdown()
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] shutdown host {row}: {e}", flush=True)


def common(crash0):
    new = sorted(os.path.basename(p) for p in crash_set() - crash0)
    bad = [f"new crash files {new}"] if new else []
    bad += [f"host of row {r} not alive at its row's end" for r, x in ROW_END.items() if not x["alive"]]
    saves = {r: session.save_files(x["dir"]) for r, x in ROW_END.items()}
    bad += [f"row {r} dir saves {saves[r]} (want only {[x['placed']]})" for r, x in ROW_END.items() if saves[r] != [x["placed"]]]
    print(f"EVIDENCE C: {json.dumps({'crashNew': new, 'rowEnd': ROW_END, 'saves': saves}, sort_keys=True, default=str)}", flush=True)
    cell("C-common", not bad, "; ".join(bad) or "0 new crash files; every host alive at its row's end; each dir holds only its row's save")


def main():
    t0 = time.time()
    crash0 = crash_set()
    run_row("G3", row_g3)
    run_row("N2S", row_neg("N2S"))
    run_row("N2M", row_neg("N2M"))
    common(crash0)
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== D246-U S-C2 older gm3 PvP campaign battle save refusal: {len(RESULTS) - len(fails)}/{len(ALL)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (expected red)' if n in RED else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(ALL) else 2)


if __name__ == "__main__":
    main()
