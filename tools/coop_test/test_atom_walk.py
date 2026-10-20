"""CIT-D302 (owner D302 (a), R-D302-1, F24048): a thin, ADDITIVE wrapper so the CI suite's `test_*.py` discovery
(tools/ci/run_coop_suite.ps1, plan_shards.ps1) runs repro_atom_walk.py as its own entry. That file makes checks no
`test_*` makes (the walk reserve refusals / truncations, DENY_PATH_CHANGED, RESERVE_*,
`agreesWithSteps`), and CI never ran it.

repro_atom_walk.py is not edited by this wrapper and keeps its 51 importers: this file runs it as `__main__`
(runpy), so its own exception -> exit-code mapping, output and exit code are exactly those of
`python repro_atom_walk.py`. Shape: test_door_deterministic.py (CIT-2, R-CIT2-5).

Run:  python tools/coop_test/test_atom_walk.py
"""

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if __name__ == "__main__":
    runpy.run_path(os.path.join(HERE, "repro_atom_walk.py"), run_name="__main__")
