"""A thin wrapper so the CI suite's `test_*.py` discovery (tools/ci/run_coop_suite.ps1, plan_shards.ps1)
runs repro_atom_spot.py as its own entry. That file makes checks no `test_*` makes (the spot ev counters
`coopSpotEvsEmitted` / `Applied`, HALT_SPOT, `actor_spotted_*`), and the discovery would not run
it otherwise.

This file runs it as `__main__` (runpy), so its own exception -> exit-code mapping, output and exit code are
exactly those of `python repro_atom_spot.py`. Same shape as test_door_deterministic.py.

Run:  python tools/coop_test/test_atom_spot.py
"""

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if __name__ == "__main__":
    runpy.run_path(os.path.join(HERE, "repro_atom_spot.py"), run_name="__main__")
