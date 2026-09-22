"""SPEC 18 (r4 T4) handoff: a thin, ADDITIVE wrapper so run_parallel.py's
basename discovery (`test_*.py`) runs SPEC 16's S2 (test_spec16_pause_on_
leave.py's `s2` arg - the D96 M2 quiescence-gate proof, run via `python
test_spec16_pause_on_leave.py s2`) as its OWN ONE-run entry.

The accepted file test_spec16_pause_on_leave.py is NOT edited: it already
gates S1 vs S2 on sys.argv[1] (plain invocation = S1 only), and this file
simply calls its main_s2() directly instead of re-invoking argv parsing.

Run:  python tools/coop_test/test_spec16_pause_on_leave_s2.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_spec16_pause_on_leave as s16

if __name__ == "__main__":
    s16.main_s2()
