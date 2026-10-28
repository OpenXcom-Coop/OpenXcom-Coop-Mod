"""W2-H70 S-C (spec docs rewrite/prompts/w2h70_sc_window_67.md (f); TASK 0 rewrite/w2h70-task0/sc/CONSTANTS.md; lead L-H70-2, ruling
R-H70-4; F20441-F20446): a co-op visitor that pressed OK on the host's "Go to Geoscape to begin saving progress." (CoopState 67) and
stays on a base screen of the host's base (the 67 window), SEPARATE co-op. Rows (one fresh boot pair each, key "49289", dirs
w2h70c_<row>_host / _client; prefix P: the guest staged, the picker, the visit, B, K0; real presses only; no reload, no rejoin):
  R11 (W1, CAP70 C1) SOLDIERS; the window over SoldiersState; the host's second quick save (its 54 = the last precondition): R11-67
      (the client's first CoopState code after the second 54 is 67, no 53 / 995 in the trace), R11-key (K0 present at HOLD_W),
      R11-leave (leave_window reaches the geoscape), R11-write (QUICK written within W_SAVE of the leave, no host press), R11-own
      (HOLD_L after the write: the client's top GeoscapeState, role own_world present). After the 54 the steps only record: no 53 /
      995 / Disconnect press; the harness shuts both machines down.
  G11 (C1-ctl) as R11 with the client's real OK on SoldiersState after the window (BasescapeState, insideCoopBase true): the five
      cells as GUARD (G11-67, G11-key, G11-leave, G11-write, G11-own).
  R12 (W2, CAP70 C2) SOLDIERS; the window; the host's real globe click on the client's base (the host's BasescapeState = the last
      precondition): R12-995 (no 995 in the client's trace from the click to HOLD_V), R12-view GUARD (the host's base_report coop name =
      the client's own base), R12-basehost GUARD (the client's "basehost" fnv = B2).
Cells: X-pre GUARD; the cells above; X-common GUARD (both machines alive at the read, no new .dmp since B). 19 cells; red (commit R1):
RED exactly on R11-67, R11-key, R11-leave, R11-write, R11-own, R12-995. ONE EVIDENCE line per row, one PASS / FAIL line per cell, the
row verdict; every row runs; exit 0 only when every cell passes, else 2. one foreground run per invocation.
Run: python tools/coop_test/test_visit_window_67.py
"""

import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from visit_window_helpers import *  # noqa: E402,F401,F403 (the helpers, run_row_c, main; R-H70-2)
KEY = "49289"

def pre_r11(x, ev):
    """R11 (W1): SOLDIERS, the window over SoldiersState, the second save (its 54 the last precondition; the trace and HOLD_W record)"""
    to_soldiers(x, ev)
    first_window(x, ev, "SoldiersState")
    second_save(x, ev)

def pre_g11(x, ev):
    """G11 (C1-ctl): as R11, with the client's real OK on SoldiersState after the window (BasescapeState, insideCoopBase true)"""
    c = x.client
    to_soldiers(x, ev)
    first_window(x, ev, "SoldiersState")
    ok = real_click(c, "OK", W_UI)
    v, s = wait(lambda: top(c) == "BasescapeState" and coop(c).get("insideCoopBase") is True, W_UI)
    ev["screen OK"] = {"press": ok, "s": s if v else None, "at": snap(x)}
    if not v:
        raise Stop("not BasescapeState with insideCoopBase true after SoldiersState's OK: %s" % ev["screen OK"])
    second_save(x, ev)

def post_11(x, ev):
    """the leave (blocked rule), then the write with no host press and the HOLD_L record"""
    if leave_window(x, ev):
        write_after(x, ev)

def cells_11(rid, ev):
    codes = [e[2] for e in ev.get("trace") or [] if e[2] is not None]
    hw, lv, wr, aw = ev.get("HOLD_W") or {}, ev.get("leave") or {}, ev.get("write"), ev.get("after write")
    k, red = ("RED", "red today: ") if rid == "R11" else ("GUARD", "C1-ctl: ")
    return [(rid + "-67", k, "the client's first CoopState code after the second 54 is 67, no 53 / 995 in the trace (%s%s; seen %s)"
             % (red, "53 + 995, F20442" if rid == "R11" else "67, F20444", codes[:4]), bool(codes) and codes[0] == 67 and not {53, 995} & set(codes)),
            (rid + "-key", k, "K0 %s present at HOLD_W (%s)" % (hw.get("K0") is True and "is" or "NOT", red + ("erased" if rid == "R11" else "present")),
             hw.get("K0") is True),
            (rid + "-leave", k, "leave_window reached the geoscape (blocked=%s; %s)" % (lv.get("blocked"), red + ("995 / 53" if rid == "R11" else "left")),
             lv.get("left s") is not None),
            (rid + "-write", k, "QUICK written within W_SAVE of the leave, no host press (%s; %s)" % ("not reached" if wr is None else wr.get("s"),
             red + ("not reached" if rid == "R11" else "1.56 s")), bool(wr) and wr.get("s") is not None),
            (rid + "-own", k, "HOLD_L after the write: the client's top GeoscapeState, role own_world present (%s)" % (red + ("not reached"
             if rid == "R11" else "present")), bool(aw) and aw["stack"][1][-1:] == ["GeoscapeState"] and aw["own"][1] is True),
            common_c(rid, ev.get("read") or {})]

def pre_r12(x, ev):
    """R12 (W2): SOLDIERS, the window, B2, the host's real globe click on the client base (its BasescapeState the last precondition)"""
    to_soldiers(x, ev)
    first_window(x, ev, "SoldiersState")
    host_view(x, ev)

def cells_r12(rid, ev):
    codes = [e[2] for e in ev.get("trace") or [] if e[2] is not None]
    vw, cb = ev.get("view") or {}, (ev.get("host picker") or {}).get("cb") or [None]
    return [("R12-995", "RED", "no 995 in the client's trace from the host's click to HOLD_V (seen %s; red today: 995 at 0.15 s, F20446)" % codes[:4],
             995 not in codes),
            ("R12-view", "GUARD", "the host's base_report coop name %r = the client's own base %r (F20446)" % ((vw.get("report") or {}).get("name"), cb[0]),
             cb[0] is not None and (vw.get("report") or {}).get("name") == cb[0]),
            ("R12-basehost", "GUARD", "the client's \"basehost\" fnv at HOLD_V %s = B2 %s (F20446)" % (vw.get("basehost"), ev.get("B2")),
             bool(ev.get("B2")) and vw.get("basehost") == ev.get("B2")),
            common_c(rid, ev.get("read") or {})]

PRE = {"R11": "the guest staged, the visit, B, K0, SOLDIERS, the 54 + the 67 over SoldiersState, its OK (insideCoopBase false), the "
              "host's CANCEL wrote QUICK, the host's second 54",
       "G11": "as R11, with SoldiersState's OK (BasescapeState, insideCoopBase true) before the host's second 54",
       "R12": "the guest staged, the host picker, the visit, B, K0, SOLDIERS, the window, the host's BasescapeState after its click on the "
              "client base"}
CELLS_11 = ("pre", "67", "key", "leave", "write", "own", "common")

def row_r11():
    return run_row_c("R11", "w2h70c_r11", KEY, pre_r11, post_11, CELLS_11, cells_11, PRE["R11"])

def row_g11():
    return run_row_c("G11", "w2h70c_g11", KEY, pre_g11, post_11, CELLS_11, cells_11, PRE["G11"])

def row_r12():
    return run_row_c("R12", "w2h70c_r12", KEY, pre_r12, host_back, ("pre", "995", "view", "basehost", "common"), cells_r12, PRE["R12"],
                     hostpk=True)

ROWS = (("R11", row_r11), ("G11", row_g11), ("R12", row_r12))
if __name__ == "__main__":
    sys.exit(main("test_visit_window_67", ROWS))
