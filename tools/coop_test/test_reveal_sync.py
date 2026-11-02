"""a thin, ADDITIVE wrapper so the CI suite's `test_*.py` discovery
(tools/ci/run_coop_suite.ps1, plan_shards.ps1) runs repro_reveal_sync.py as its own entry. That file makes checks no
`test_*` makes (the fog test commands `reveal_drop` / `reveal_base` / `reveal_hostile_pass` and
`coopSuppressSelectionFov`), and CI's `test_*.py` discovery would not run it on its own.

repro_reveal_sync.py is not edited by this wrapper (it has no importers): this file runs it as `__main__`
(runpy), so its own exception -> exit-code mapping, output and exit code are exactly those of
`python repro_reveal_sync.py`. Same shape as test_door_deterministic.py.

Run:  python tools/coop_test/test_reveal_sync.py
"""

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if __name__ == "__main__":
    runpy.run_path(os.path.join(HERE, "repro_reveal_sync.py"), run_name="__main__")
