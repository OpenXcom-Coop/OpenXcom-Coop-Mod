"""a thin, ADDITIVE wrapper so the CI suite's `test_*.py` discovery
(tools/ci/run_coop_suite.ps1, plan_shards.ps1) runs repro_walk_zero_step.py as its own entry. That file makes checks no
`test_*` makes (a zero-step walk's `final` landing with a clean hash
(`battle_halt_walk_before_step`)), and CI discovers only `test_*.py` files.

repro_walk_zero_step.py is not edited by this wrapper and keeps its 1 importer: this file runs it as `__main__`
(runpy), so its own exception -> exit-code mapping, output and exit code are exactly those of
`python repro_walk_zero_step.py`. Shape: test_door_deterministic.py.

Run:  python tools/coop_test/test_walk_zero_step.py
"""

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if __name__ == "__main__":
    runpy.run_path(os.path.join(HERE, "repro_walk_zero_step.py"), run_name="__main__")
