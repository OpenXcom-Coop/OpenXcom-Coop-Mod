"""A thin wrapper so run_parallel.py's basename discovery (`test_*.py`) runs
test_pause_on_leave.py's alien-turn kill scenario (the client killed mid-alien-turn; plain
`python test_pause_on_leave.py alien_turn` runs it too) as its OWN ONE-run entry.

test_pause_on_leave.py chooses its scenario from sys.argv[1] (plain invocation = the walk drop only);
this file calls its main_alien_turn_kill() directly instead of re-invoking argv parsing.

Run:  python tools/coop_test/test_pause_on_leave_alien_turn.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_pause_on_leave as pause_on_leave

if __name__ == "__main__":
    pause_on_leave.main_alien_turn_kill()
