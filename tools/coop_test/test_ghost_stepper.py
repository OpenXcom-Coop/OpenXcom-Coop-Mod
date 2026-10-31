"""test_ghost_stepper.py: a thin, ADDITIVE wrapper so the CI suite's `test_*.py` discovery
(tools/ci/run_coop_suite.ps1, plan_shards.ps1) runs repro_ghost_stepper.py as its own entry. That file makes checks no
`test_*` makes (`coopGhostStepper` off keeps `ghostEnqueued` 0 across a walk, the halted
walk's ghost prefix and the kneel-before-walk ev order), and the discovery does not pick up a `repro_*` file.

repro_ghost_stepper.py is not edited by this wrapper and keeps its 2 importers: this file runs it as `__main__`
(runpy), so its own exception -> exit-code mapping, output and exit code are exactly those of
`python repro_ghost_stepper.py`. Shape: test_door_deterministic.py.

Run:  python tools/coop_test/test_ghost_stepper.py
"""

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if __name__ == "__main__":
    runpy.run_path(os.path.join(HERE, "repro_ghost_stepper.py"), run_name="__main__")
