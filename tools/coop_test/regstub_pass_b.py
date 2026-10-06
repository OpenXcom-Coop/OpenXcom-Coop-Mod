#!/usr/bin/env python3
"""W2-U13 runner stub for selftest_regression_runner.py (not a test_* file:
CI, a default suite and REGRESSION never run it, F7929).

Makes its slot's user dir through harness (no lock, no game), sleeps
REGSTUB_SLEEP seconds (default 0) and prints ONE REGSTUB line. Exit 0.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402

NAME = "regstub_pass_b"
t0 = time.time()
d = harness.make_user_dir(NAME)
time.sleep(float(os.environ.get("REGSTUB_SLEEP", "0")))
t1 = time.time()
print("REGSTUB name=%s slot=%d env=%s userdir=%s lock=%s t0=%.3f t1=%.3f"
      % (NAME, harness.HARNESS_SLOT, os.environ.get("OXC_HARNESS_SLOT"), d,
         harness._LOCK_PATH, t0, t1), flush=True)
