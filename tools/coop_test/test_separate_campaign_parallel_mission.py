"""Vanilla Separate Campaign mission with host-authoritative parallel turns.

Regression coverage for client soldier ownership, a real client walk, side
transition through the alien turn, and the tactical sync alarms.  The shared
mission driver keeps this path identical to the classic Separate test apart
from the host's Parallel Turns option.
"""

from test_separate_campaign_mission import main


if __name__ == "__main__":
    main(parallel=True)
