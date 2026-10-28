"""CIT-2 (R-CIT2-5, F17338, F23736): a thin, ADDITIVE wrapper so the CI suite's `test_*.py` discovery
(tools/ci/run_coop_suite.ps1, plan_shards.ps1) runs repro_door_deterministic.py as its own entry. That file
is the cover the D229 gate (check_quarantine_gate.py) names for two DELETED door rows, and CI never ran it.

repro_door_deterministic.py is NOT edited and keeps its importers (test_bringup_leak_sweep,
test_staging_order): this file runs it as `__main__` (runpy), so its own exception -> exit-code
mapping, output and exit code are exactly those of `python repro_door_deterministic.py`.

Run:  python tools/coop_test/test_door_deterministic.py
"""

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if __name__ == "__main__":
    runpy.run_path(os.path.join(HERE, "repro_door_deterministic.py"), run_name="__main__")
