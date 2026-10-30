"""test_visit_window_67_edits.py: a change a co-op visitor makes on a base screen of the host's base after it pressed
OK on the host's "Go to Geoscape to begin saving progress." (CoopState 67; the 67 window), SEPARATE co-op. Rows (one
fresh boot pair each, key "49578", dirs window67_<row>_host / _client; prefix P: the guest staged, the picker, the
visit, B, K0; real presses only; the one test command is guest_renamed's rename_soldier; no reload, no rejoin):
  crew_change: EQUIP CRAFT, craft row 0, CREW; the window over CraftSoldiersState; B3 = the client's "basehost" fnv;
      the guest's crew row (its craft changes = the last precondition); OK, OK (CraftInfoState's), OK, the leave;
      HOLD_L; the re-visit: crew_change-write (the fnv after CraftInfoState's OK != B3), crew_change-seat (the guest
      has a craft in the re-visit's view).
  guest_moved: SOLDIERS; the window; B3; the guest's row, MOVE, OK (SoldiersState back = the last precondition); the
      leave; HOLD_L: guest_moved-write (the fnv after the MOVE's OK != B3), guest_moved-home (the guest on the
      client's own base with coopBase -1).
  guest_renamed: SOLDIERS; the window; B3; rename_soldier GIFTNAME -> RENAME (the view lists it = the last
      precondition); SoldiersState's OK; the leave; HOLD_L: guest_renamed-write (the fnv after SoldiersState's OK !=
      B3), guest_renamed-name (the own-base soldier with B's guest id is named RENAME).
Cells: <row>-pre GUARD; the FIX cells above; <row>-common GUARD (both machines alive at the read, no new .dmp since
B). 12 cells; when broken, exactly crew_change-write, -seat, guest_moved-write, -home, guest_renamed-write and -name
FAIL. ONE EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; every row runs; exit 0 only when
every cell passes, else 2. One foreground run per invocation.
Run: python tools/coop_test/test_visit_window_67_edits.py
"""

import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from visit_window_helpers import *  # noqa: E402,F401,F403 (the helpers, run_window_row, main)
KEY = "49578"
EQUIP, MOVE = "EQUIP CRAFT", "MOVE"

def leave_hold(x, ev):
    """the leave, HOLD_L, the record and the guest's own-world census (by name and by B's guest id)"""
    leave_window(x, ev)
    time.sleep(HOLD_L)
    ev["after leave"] = snap(x)
    ev["census"] = {"name": own(x.client, x.gift), "id": [e for e in where(x.client, gid=x.gid) if e[1] == "own"]}

def pre_crew_change(x, ev):
    """crew_change: EQUIP CRAFT, craft row 0, CREW; the window over CraftSoldiersState; B3; the guest's crew row (its
    craft changes)"""
    open_crew(x, ev, EQUIP)
    first_window(x, ev, "CraftSoldiersState")
    ev["B3"] = fnvb(x.client)
    toggle_seat(x, ev)

def post_crew_change(x, ev):
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
    except Exception as e:  # recorded: crew_change-seat reads the view
        rv["miss"] = short(e, 300)
    rv["view"] = where(c, x.gift)

def pre_guest_moved(x, ev):
    """guest_moved: SOLDIERS; the window; B3; the guest's row, MOVE, OK (SoldiersState back)"""
    to_soldiers(x, ev)
    first_window(x, ev, "SoldiersState")
    ev["B3"] = fnvb(x.client)
    move_home(x, ev, MOVE)

def pre_guest_renamed(x, ev):
    """guest_renamed: SOLDIERS; the window; B3; rename_soldier GIFTNAME -> RENAME (the view lists it)"""
    to_soldiers(x, ev)
    first_window(x, ev, "SoldiersState")
    ev["B3"] = fnvb(x.client)
    rename_guest(x, ev)

def post_guest_renamed(x, ev):
    """SoldiersState's OK (BasescapeState; the fnv after it); the leave; HOLD_L"""
    st = ev.setdefault("after", [])
    press(x.client, "OK", "BasescapeState", st, "SoldiersState OK")
    st[-1].append(fnvb(x.client))
    leave_hold(x, ev)

def cells_edits(rid, ev):
    b3, cs = ev.get("B3"), ev.get("census") or {}
    after = ev.get("after") or []
    if rid == "crew_change":
        f = after[1][3] if len(after) > 1 and len(after[1]) > 3 else None
        view = (ev.get("revisit") or {}).get("view") or []
        out = [("crew_change-write", "FIX",
                "the client's \"basehost\" fnv after CraftInfoState's OK %s != B3 %s (when broken: equal)" % (f, b3),
                bool(b3) and bool(f) and f != b3),
               ("crew_change-seat", "FIX",
                "on the re-visit the guest has a craft in the view (%s; when broken: none)" % view,
                len(view) == 1 and bool(view[0][5]))]
    elif rid == "guest_moved":
        f, hm = (ev.get("move") or {}).get("fnv"), cs.get("name")
        out = [("guest_moved-write", "FIX",
                "the client's \"basehost\" fnv after the MOVE's OK %s != B3 %s (when broken: equal)" % (f, b3),
                bool(b3) and bool(f) and f != b3),
               ("guest_moved-home", "FIX",
                "HOLD_L after the leave: the guest on the client's own base with coopBase -1 "
                "(%s; when broken: the host base's coop id)" % hm, bool(hm) and len(hm) == 1 and hm[0][3] == -1)]
    else:
        f, rn, byid = after[0][3] if after and len(after[0]) > 3 else None, (ev.get("rename") or {}).get("name"), cs.get("id")
        out = [("guest_renamed-write", "FIX",
                "the client's \"basehost\" fnv after SoldiersState's OK %s != B3 %s (when "
                "broken: equal)" % (f, b3), bool(b3) and bool(f) and f != b3),
               ("guest_renamed-name", "FIX",
                "HOLD_L after the leave: the own-base soldier with B's guest id is named %r "
                "(%s; when broken: GIFTNAME)" % (rn, byid), bool(byid) and len(byid) == 1 and byid[0][3] == rn)]
    return out + [common_cell(rid, ev.get("read") or {})]

PRE = {"crew_change": "the guest staged, the visit, B, K0, EQUIP CRAFT, craft row, CREW, the window over "
                      "CraftSoldiersState, the guest's craft changed by its crew row",
       "guest_moved": "the guest staged, the visit, B, K0, SOLDIERS, the window, the guest's MOVE window, its OK, "
                      "SoldiersState back",
       "guest_renamed": "the guest staged, the visit, B, K0, SOLDIERS, the window, the guest renamed in the view"}

def row_crew_change():
    return run_window_row("crew_change", "window67_crew_change", KEY, pre_crew_change, post_crew_change,
                          ("pre", "write", "seat", "common"), cells_edits, PRE["crew_change"])

def row_guest_moved():
    return run_window_row("guest_moved", "window67_guest_moved", KEY, pre_guest_moved, leave_hold,
                          ("pre", "write", "home", "common"), cells_edits, PRE["guest_moved"])

def row_guest_renamed():
    return run_window_row("guest_renamed", "window67_guest_renamed", KEY, pre_guest_renamed, post_guest_renamed,
                          ("pre", "write", "name", "common"), cells_edits, PRE["guest_renamed"])

ROWS = (("crew_change", row_crew_change), ("guest_moved", row_guest_moved), ("guest_renamed", row_guest_renamed))
if __name__ == "__main__":
    sys.exit(main("test_visit_window_67_edits", ROWS))
