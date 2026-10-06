#!/usr/bin/env python3
"""W2-U13 failing runner stub for selftest_regression_runner.py (not a test_*
file: CI, a default suite and REGRESSION never run it, F7929).

As regstub_pass_a, then writes <user dir>/openxcom.log, prints REGSTUB line
01..40, writes a fake crash log beside OXC_TEST_EXE (only with REGSTUB_CRASH=1
AND OXC_TEST_EXE set; never the real crashlogs) and fails uncaught (rc 1).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402

NAME = "regstub_fail"
t0 = time.time()
d = harness.make_user_dir(NAME)
time.sleep(float(os.environ.get("REGSTUB_SLEEP", "0")))
t1 = time.time()
print("REGSTUB name=%s slot=%d env=%s userdir=%s lock=%s t0=%.3f t1=%.3f"
      % (NAME, harness.HARNESS_SLOT, os.environ.get("OXC_HARNESS_SLOT"), d,
         harness._LOCK_PATH, t0, t1), flush=True)
with open(os.path.join(d, "openxcom.log"), "w", encoding="ascii") as f:
    f.write("REGSTUB fake game log\n")
for i in range(1, 41):
    print("REGSTUB line %02d" % i)
sys.stdout.flush()
if os.environ.get("REGSTUB_CRASH") == "1" and os.environ.get("OXC_TEST_EXE"):
    cdir = os.path.join(os.path.dirname(harness.EXE), "crashlogs")
    os.makedirs(cdir, exist_ok=True)
    with open(os.path.join(cdir, "crash_regstub_%d.log" % os.getpid()), "w", encoding="ascii") as f:
        f.write("==== Crash/Log ====\nREGSTUB fake crash\n")
assert False, "REGSTUB deliberate failure"
