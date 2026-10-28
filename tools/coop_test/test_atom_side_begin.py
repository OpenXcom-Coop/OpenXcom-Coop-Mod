"""a thin, ADDITIVE wrapper so the CI suite's `test_*.py` discovery
(tools/ci/run_coop_suite.ps1, plan_shards.ps1) runs repro_atom_side_begin.py as its own entry. That file
is a cover the D229 gate (check_quarantine_gate.py) names for two DELETED PvP rows, and CI never ran it.

repro_atom_side_begin.py is NOT edited and keeps its 27 importers: this file runs it as `__main__`
(runpy), so its own exception -> exit-code mapping, output and exit code are exactly those of
`python repro_atom_side_begin.py`.

Run:  python tools/coop_test/test_atom_side_begin.py
"""

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if __name__ == "__main__":
    runpy.run_path(os.path.join(HERE, "repro_atom_side_begin.py"), run_name="__main__")
