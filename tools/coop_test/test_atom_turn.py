"""CIT-D302 (owner D302 (a), R-D302-1, F24131): a thin, ADDITIVE wrapper so the CI suite's `test_*.py` discovery
(tools/ci/run_coop_suite.ps1, plan_shards.ps1) runs repro_atom_turn.py as its own entry. That file makes checks no
`test_*` makes (a turn back to an already published cone attaches no reveal delta
(SS2.4a presence gating, host `[coop-reveal] attached reveal delta` count)), and CI never ran it.

repro_atom_turn.py is not edited by this wrapper and keeps its 1 importer: this file runs it as `__main__`
(runpy), so its own exception -> exit-code mapping, output and exit code are exactly those of
`python repro_atom_turn.py`. Shape: test_door_deterministic.py (CIT-2, R-CIT2-5).

Run:  python tools/coop_test/test_atom_turn.py
"""

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if __name__ == "__main__":
    runpy.run_path(os.path.join(HERE, "repro_atom_turn.py"), run_name="__main__")
