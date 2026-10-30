"""test_visit_window_67.py: a co-op visitor that pressed OK on the host's "Go to Geoscape to begin saving progress."
(CoopState 67) and stays on a base screen of the host's base (the 67 window), SEPARATE co-op. Rows (one fresh boot
pair each, key "49289", dirs window67_<row>_host / _client; prefix P: the guest staged, the picker, the visit, B, K0;
real presses only; no reload, no rejoin):
  second_save_on_soldiers: SOLDIERS; the window over SoldiersState; the host's second quick save (its 54 = the last
      precondition): second_save_on_soldiers-67 (the client's first CoopState code after the second 54 is 67, no 53 /
      995 in the trace), -key (K0 present at HOLD_W), -leave (leave_window reaches the geoscape), -write (QUICK
      written within W_SAVE of the leave, no host press), -own (HOLD_L after the write: the client's top
      GeoscapeState, role own_world present). After the 54 the steps only record: no 53 / 995 / Disconnect press; the
      harness shuts both machines down.
  second_save_on_base (the guard): as second_save_on_soldiers with the client's real OK on SoldiersState after the
      window (BasescapeState, insideCoopBase true): the five cells as GUARD (second_save_on_base-67, -key, -leave,
      -write, -own).
  host_visit: SOLDIERS; the window; the host's real globe click on the client's base (the host's BasescapeState = the
      last precondition): host_visit-995 (no 995 in the client's trace from the click to HOLD_V), host_visit-view
      GUARD (the host's base_report coop name = the client's own base), host_visit-basehost GUARD (the client's
      "basehost" fnv = B2).
Cells: <row>-pre GUARD; the cells above; <row>-common GUARD (both machines alive at the read, no new .dmp since B). 19
cells; when broken, exactly second_save_on_soldiers-67, -key, -leave, -write, -own and host_visit-995 FAIL. ONE
EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; every row runs; exit 0 only when every cell
passes, else 2. One foreground run per invocation.
Run: python tools/coop_test/test_visit_window_67.py
"""

import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from visit_window_helpers import *  # noqa: E402,F401,F403 (the helpers, run_window_row, main)
KEY = "49289"

def pre_second_save_on_soldiers(x, ev):
    """second_save_on_soldiers: SOLDIERS, the window over SoldiersState, the second save (its 54 the last precondition;
    the trace and HOLD_W record)"""
    to_soldiers(x, ev)
    first_window(x, ev, "SoldiersState")
    second_save(x, ev)

def pre_second_save_on_base(x, ev):
    """second_save_on_base (the guard): as second_save_on_soldiers, with the client's real OK on SoldiersState after the
    window (BasescapeState, insideCoopBase true)"""
    c = x.client
    to_soldiers(x, ev)
    first_window(x, ev, "SoldiersState")
    ok = real_click(c, "OK", W_UI)
    v, s = wait(lambda: top(c) == "BasescapeState" and coop(c).get("insideCoopBase") is True, W_UI)
    ev["screen OK"] = {"press": ok, "s": s if v else None, "at": snap(x)}
    if not v:
        raise Stop("not BasescapeState with insideCoopBase true after SoldiersState's OK: %s" % ev["screen OK"])
    second_save(x, ev)

def post_second_save(x, ev):
    """the leave (blocked rule), then the write with no host press and the HOLD_L record"""
    if leave_window(x, ev):
        write_after(x, ev)

def cells_second_save(rid, ev):
    codes = [e[2] for e in ev.get("trace") or [] if e[2] is not None]
    hw, lv, wr, aw = ev.get("HOLD_W") or {}, ev.get("leave") or {}, ev.get("write"), ev.get("after write")
    k, note = ("FIX", "when broken: ") if rid == "second_save_on_soldiers" else ("GUARD", "guard: ")
    return [(rid + "-67", k,
             "the client's first CoopState code after the second 54 is 67, no 53 / 995 in the trace (%s%s; seen %s)"
             % (note, "53 + 995" if rid == "second_save_on_soldiers" else "67", codes[:4]),
             bool(codes) and codes[0] == 67 and not {53, 995} & set(codes)),
            (rid + "-key", k,
             "K0 %s present at HOLD_W (%s)" % (hw.get("K0") is True and "is" or "NOT",
                                               note + ("erased" if rid == "second_save_on_soldiers" else "present")),
             hw.get("K0") is True),
            (rid + "-leave", k,
             "leave_window reached the geoscape (blocked=%s; %s)"
             % (lv.get("blocked"), note + ("995 / 53" if rid == "second_save_on_soldiers" else "left")),
             lv.get("left s") is not None),
            (rid + "-write", k,
             "QUICK written within W_SAVE of the leave, no host press (%s; %s)"
             % ("not reached" if wr is None else wr.get("s"),
                note + ("not reached" if rid == "second_save_on_soldiers" else "1.56 s")),
             bool(wr) and wr.get("s") is not None),
            (rid + "-own", k,
             "HOLD_L after the write: the client's top GeoscapeState, role own_world present (%s)"
             % (note + ("not reached" if rid == "second_save_on_soldiers" else "present")),
             bool(aw) and aw["stack"][1][-1:] == ["GeoscapeState"] and aw["own"][1] is True),
            common_cell(rid, ev.get("read") or {})]

def pre_host_visit(x, ev):
    """host_visit: SOLDIERS, the window, B2, the host's real globe click on the client base (its BasescapeState the last
    precondition)"""
    to_soldiers(x, ev)
    first_window(x, ev, "SoldiersState")
    host_view(x, ev)

def cells_host_visit(rid, ev):
    codes = [e[2] for e in ev.get("trace") or [] if e[2] is not None]
    vw, cb = ev.get("view") or {}, (ev.get("host picker") or {}).get("cb") or [None]
    return [("host_visit-995", "FIX",
             "no 995 in the client's trace from the host's click to HOLD_V (seen %s; when broken: 995 at 0.15 s)"
             % codes[:4],
             995 not in codes),
            ("host_visit-view", "GUARD",
             "the host's base_report coop name %r = the client's own base %r"
             % ((vw.get("report") or {}).get("name"), cb[0]),
             cb[0] is not None and (vw.get("report") or {}).get("name") == cb[0]),
            ("host_visit-basehost", "GUARD",
             "the client's \"basehost\" fnv at HOLD_V %s = B2 %s" % (vw.get("basehost"), ev.get("B2")),
             bool(ev.get("B2")) and vw.get("basehost") == ev.get("B2")),
            common_cell(rid, ev.get("read") or {})]

PRE = {"second_save_on_soldiers": "the guest staged, the visit, B, K0, SOLDIERS, the 54 + the 67 over SoldiersState, "
                                  "its OK (insideCoopBase false), the host's CANCEL wrote QUICK, the host's second 54",
       "second_save_on_base": "as second_save_on_soldiers, with SoldiersState's OK (BasescapeState, insideCoopBase "
                              "true) before the host's second 54",
       "host_visit": "the guest staged, the host picker, the visit, B, K0, SOLDIERS, the window, the host's "
                     "BasescapeState after its click on the client base"}
SECOND_SAVE_CELLS = ("pre", "67", "key", "leave", "write", "own", "common")

def row_second_save_on_soldiers():
    return run_window_row("second_save_on_soldiers", "window67_second_save_on_soldiers", KEY,
                          pre_second_save_on_soldiers, post_second_save, SECOND_SAVE_CELLS, cells_second_save,
                          PRE["second_save_on_soldiers"])

def row_second_save_on_base():
    return run_window_row("second_save_on_base", "window67_second_save_on_base", KEY, pre_second_save_on_base,
                          post_second_save, SECOND_SAVE_CELLS, cells_second_save, PRE["second_save_on_base"])

def row_host_visit():
    return run_window_row("host_visit", "window67_host_visit", KEY, pre_host_visit, host_back,
                          ("pre", "995", "view", "basehost", "common"), cells_host_visit, PRE["host_visit"],
                          hostpk=True)

ROWS = (("second_save_on_soldiers", row_second_save_on_soldiers), ("second_save_on_base", row_second_save_on_base),
        ("host_visit", row_host_visit))
if __name__ == "__main__":
    sys.exit(main("test_visit_window_67", ROWS))
