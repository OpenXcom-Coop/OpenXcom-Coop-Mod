"""W2-H70 S-C (spec docs rewrite/prompts/w2h70_sc_window_67.md (f); TASK 0 rewrite/w2h70-task0/sc/CONSTANTS.md; lead L-H70-2, ruling
R-H70-4; F20447, F20448, F20706): a change a co-op visitor makes on a base screen of the host's base after it pressed OK on the
host's "Go to Geoscape to begin saving progress." (CoopState 67; the 67 window), SEPARATE co-op. Rows (one fresh boot pair each, key
"49578", dirs w2h70c_<row>_host / _client; prefix P: the guest staged, the picker, the visit, B, K0; real presses only; the one lever is
R15's rename_soldier, QH70C-5; no reload, no rejoin):
  R13 (W3 seat, CAP70 C3) EQUIP CRAFT, craft row 0, CREW; the window over CraftSoldiersState; B3 = the client's "basehost" fnv; the
      guest's crew row (its craft changes = the last precondition); OK, OK (CraftInfoState's), OK, the leave; HOLD_L; the re-visit:
      R13-write (the fnv after CraftInfoState's OK != B3), R13-seat (the guest has a craft in the re-visit's view).
  R14 (W3 MOVE, CAP70 C3SACK) SOLDIERS; the window; B3; the guest's row, MOVE, OK (SoldiersState back = the last precondition); the
      leave; HOLD_L: R14-write (the fnv after the MOVE's OK != B3), R14-home (the guest on the client's own base with coopBase -1).
  R15 (W3 rename) SOLDIERS; the window; B3; rename_soldier GIFTNAME -> RENAME (the view lists it = the last precondition); SoldiersState's
      OK; the leave; HOLD_L: R15-write (the fnv after SoldiersState's OK != B3), R15-name (the own-base soldier with B's guest id is
      named RENAME).
Cells: X-pre GUARD; the RED cells above; X-common GUARD (both machines alive at the read, no new .dmp since B). 12 cells; red (commit
R1): RED exactly on R13-write, R13-seat, R14-write, R14-home, R15-write, R15-name. Never in one K=2 batch with
test_w2_manual_promotion.py (its port tuple shares 49290, F20703). ONE EVIDENCE line per row, one PASS / FAIL line per cell, the row
verdict; every row runs; exit 0 only when every cell passes, else 2 (WV-D99 / WV-D100). WV-D95: one foreground run per invocation.
Run: python tools/coop_test/test_w2_visit_window_67_edits.py
"""

import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from w2h70c_helpers import *  # noqa: E402,F401,F403 (the helpers, run_row_c, main; R-H70-2)
KEY = "49578"
EQUIP, MOVE = "EQUIP CRAFT", "MOVE"

def leave_hold(x, ev):
    """the leave, HOLD_L, the record and the guest's own-world census (by name and by B's guest id)"""
    leave_window(x, ev)
    time.sleep(HOLD_L)
    ev["after leave"] = snap(x)
    ev["census"] = {"name": own(x.client, x.gift), "id": [e for e in where(x.client, gid=x.gid) if e[1] == "own"]}

def pre_r13(x, ev):
    """R13: EQUIP CRAFT, craft row 0, CREW; the window over CraftSoldiersState; B3; the guest's crew row (its craft changes)"""
    open_crew(x, ev, EQUIP)
    first_window(x, ev, "CraftSoldiersState")
    ev["B3"] = fnvb(x.client)
    toggle_seat(x, ev)

def post_r13(x, ev):
    """OK (CraftInfoState), OK (CraftsState; the fnv after CraftInfoState's OK), OK (BasescapeState); the leave; HOLD_L; the re-visit"""
    c, st = x.client, ev.setdefault("after", [])
    for want in ("CraftInfoState", "CraftsState", "BasescapeState"):
        press(c, "OK", want, st, want)
        st[-1].append(fnvb(c))
    leave_hold(x, ev)
    rv = ev["revisit"] = {}
    try:
        visit(x, rv)
        time.sleep(HOLD_L)
    except Exception as e:  # recorded: R13-seat reads the view
        rv["miss"] = short(e, 300)
    rv["view"] = where(c, x.gift)

def pre_r14(x, ev):
    """R14: SOLDIERS; the window; B3; the guest's row, MOVE, OK (SoldiersState back)"""
    to_soldiers(x, ev)
    first_window(x, ev, "SoldiersState")
    ev["B3"] = fnvb(x.client)
    move_home(x, ev, MOVE)

def pre_r15(x, ev):
    """R15: SOLDIERS; the window; B3; rename_soldier GIFTNAME -> RENAME (the view lists it)"""
    to_soldiers(x, ev)
    first_window(x, ev, "SoldiersState")
    ev["B3"] = fnvb(x.client)
    rename_guest(x, ev)

def post_r15(x, ev):
    """SoldiersState's OK (BasescapeState; the fnv after it); the leave; HOLD_L"""
    st = ev.setdefault("after", [])
    press(x.client, "OK", "BasescapeState", st, "SoldiersState OK")
    st[-1].append(fnvb(x.client))
    leave_hold(x, ev)

def cells_w3(rid, ev):
    b3, cs = ev.get("B3"), ev.get("census") or {}
    after = ev.get("after") or []
    if rid == "R13":
        f = after[1][3] if len(after) > 1 and len(after[1]) > 3 else None
        view = (ev.get("revisit") or {}).get("view") or []
        out = [("R13-write", "RED", "the client's \"basehost\" fnv after CraftInfoState's OK %s != B3 %s (red today: equal, F20447)" % (f, b3),
                bool(b3) and bool(f) and f != b3),
               ("R13-seat", "RED", "on the re-visit the guest has a craft in the view (%s; red today: none, F20447)" % view,
                len(view) == 1 and bool(view[0][5]))]
    elif rid == "R14":
        f, hm = (ev.get("move") or {}).get("fnv"), cs.get("name")
        out = [("R14-write", "RED", "the client's \"basehost\" fnv after the MOVE's OK %s != B3 %s (red today: equal, F20448)" % (f, b3),
                bool(b3) and bool(f) and f != b3),
               ("R14-home", "RED", "HOLD_L after the leave: the guest on the client's own base with coopBase -1 (%s; red today: the host "
                "base's coop id, F20448)" % hm, bool(hm) and len(hm) == 1 and hm[0][3] == -1)]
    else:
        f, rn, byid = after[0][3] if after and len(after[0]) > 3 else None, (ev.get("rename") or {}).get("name"), cs.get("id")
        out = [("R15-write", "RED", "the client's \"basehost\" fnv after SoldiersState's OK %s != B3 %s (red today: equal, CANDIDATE "
                "F20706)" % (f, b3), bool(b3) and bool(f) and f != b3),
               ("R15-name", "RED", "HOLD_L after the leave: the own-base soldier with B's guest id is named %r (%s; red today: GIFTNAME, "
                "CANDIDATE F20706)" % (rn, byid), bool(byid) and len(byid) == 1 and byid[0][3] == rn)]
    return out + [common_c(rid, ev.get("read") or {})]

PRE = {"R13": "the guest staged, the visit, B, K0, EQUIP CRAFT, craft row, CREW, the window over CraftSoldiersState, the guest's "
              "craft changed by its crew row",
       "R14": "the guest staged, the visit, B, K0, SOLDIERS, the window, the guest's MOVE window, its OK, SoldiersState back",
       "R15": "the guest staged, the visit, B, K0, SOLDIERS, the window, the guest renamed in the view"}

def row_r13():
    return run_row_c("R13", "w2h70c_r13", KEY, pre_r13, post_r13, ("pre", "write", "seat", "common"), cells_w3, PRE["R13"])

def row_r14():
    return run_row_c("R14", "w2h70c_r14", KEY, pre_r14, leave_hold, ("pre", "write", "home", "common"), cells_w3, PRE["R14"])

def row_r15():
    return run_row_c("R15", "w2h70c_r15", KEY, pre_r15, post_r15, ("pre", "write", "name", "common"), cells_w3, PRE["R15"])

ROWS = (("R13", row_r13), ("R14", row_r14), ("R15", row_r15))
if __name__ == "__main__":
    sys.exit(main("test_w2_visit_window_67_edits", ROWS))
