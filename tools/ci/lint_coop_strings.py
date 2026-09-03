#!/usr/bin/env python
"""
lint_coop_strings.py

WAVE1-RUNBOOK.md **WV-D41** (wave 1, minted by W1-P7): assert **zero
UNACCOUNTED `STR_COOP_*` keys**.

WV-D41's exact wording matters and this script implements it literally: the
assert is "zero UNACCOUNTED", **not** "zero orphaned". An ORPHANED key (present
in the .yml files, referenced from nowhere in src/) is perfectly legal as long
as it has a row in the whitelist saying so and naming who owns it - the owner
ruled on 2026-09-02 that the 11 R1-P3 quarantine orphans STAY as accounted
placeholders, and `STR_COOP_END_TURN_TALLY` is deliberately reserved for
W1-P13. The hard zero-orphan assert lands at W1-G3, not here.

THE WHITELIST is `tools/coop_test/COOP_STRING_DISPOSITIONS.md`, whose own
"Parse contract" section defines the format this script reads:

  * a whitelist entry is any line in that file starting with `| STR_COOP_`;
  * one key per line, exactly one row per key;
  * the KEY column is the BARE identifier - no backticks, no quotes. That is
    load-bearing: the PLANNED KEYS rows are written WITH backticks precisely so
    this scan cannot pick them up, and a planned key can only become greppable
    by being moved into the WHITELIST table unquoted.

WHAT IT CHECKS
  1. UNACCOUNTED - a `STR_COOP_*` key defined in a language file with no
     whitelist row. This is WV-D41's assert.
  2. STALE ROW - a whitelist row for a key that no longer exists in the
     language files. The disposition table is a LIVING document (IR2-11): a
     packet that deletes a key deletes its row in the same commit.
  3. DUPLICATE ROW - two rows for one key ("exactly one row per key").
  4. LANGUAGE SKEW - a key present in en-US.yml but not en-GB.yml or vice
     versa. Keys live in BOTH files; a packet that changes one changes both.

It deliberately does NOT check the deployed copy under bin/x64/Release/** -
that is a gitignored deploy artifact, and the WV-D17 robocopy is a harness
step, not a source-of-truth question.

Usage:
    python tools/ci/lint_coop_strings.py [REPO_ROOT]

REPO_ROOT defaults to the current working directory (run it from the repo or
worktree root). Exits 0 with a summary line when clean; exits 1 and prints one
line per problem otherwise.
"""

import os
import re
import sys

WHITELIST_REL = os.path.join("tools", "coop_test", "COOP_STRING_DISPOSITIONS.md")
LANG_REL = [
    os.path.join("bin", "common", "Language", "en-US.yml"),
    os.path.join("bin", "common", "Language", "en-GB.yml"),
]

# The parse contract, verbatim: "every line in the WHITELIST table that starts
# with `| STR_COOP_`". The KEY column is the bare identifier.
ROW_RE = re.compile(r"^\|\s*(STR_COOP_[A-Z0-9_]+)\s*\|")

# A language-file DEFINITION, not a mention: two leading spaces, the key, a
# colon. Comment lines start with '#' after the indent and never match.
KEY_RE = re.compile(r"^\s+(STR_COOP_[A-Z0-9_]+)\s*:")


def read_lines(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def whitelist_rows(root):
    """Returns (ordered list of keys, list of duplicate keys)."""
    path = os.path.join(root, WHITELIST_REL)
    if not os.path.isfile(path):
        print("lint_coop_strings: MISSING whitelist %s" % WHITELIST_REL)
        sys.exit(1)
    keys = []
    dupes = []
    for line in read_lines(path):
        m = ROW_RE.match(line)
        if not m:
            continue
        key = m.group(1)
        if key in keys:
            dupes.append(key)
        else:
            keys.append(key)
    return keys, dupes


def language_keys(root, rel):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        print("lint_coop_strings: MISSING language file %s" % rel)
        sys.exit(1)
    keys = []
    for line in read_lines(path):
        m = KEY_RE.match(line)
        if m and m.group(1) not in keys:
            keys.append(m.group(1))
    return keys


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    rows, dupes = whitelist_rows(root)
    per_file = [(rel, language_keys(root, rel)) for rel in LANG_REL]

    problems = []

    for key in dupes:
        problems.append("DUPLICATE ROW: %s appears more than once in %s "
                        "(the parse contract says exactly one row per key)"
                        % (key, WHITELIST_REL))

    defined = set()
    for _rel, keys in per_file:
        defined.update(keys)

    # 1. UNACCOUNTED - WV-D41's assert.
    for key in sorted(defined):
        if key not in rows:
            problems.append("UNACCOUNTED: %s is defined in the language files but has "
                            "no row in %s - add one in the SAME commit that minted it "
                            "(WV-D41; see HOW TO APPEND A ROW)" % (key, WHITELIST_REL))

    # 2. STALE ROW.
    for key in rows:
        if key not in defined:
            problems.append("STALE ROW: %s has a whitelist row but is not defined in "
                            "either language file - a packet that deletes a key deletes "
                            "its row in the same commit (IR2-11)" % key)

    # 4. LANGUAGE SKEW.
    us_rel, us_keys = per_file[0]
    gb_rel, gb_keys = per_file[1]
    for key in sorted(set(us_keys) - set(gb_keys)):
        problems.append("LANGUAGE SKEW: %s is in %s but not %s" % (key, us_rel, gb_rel))
    for key in sorted(set(gb_keys) - set(us_keys)):
        problems.append("LANGUAGE SKEW: %s is in %s but not %s" % (key, gb_rel, us_rel))

    if problems:
        for p in problems:
            print(p)
        print("lint_coop_strings: FAIL - %d problem(s); %d whitelist row(s), "
              "%d key(s) defined" % (len(problems), len(rows), len(defined)))
        return 1

    print("lint_coop_strings: OK - %d STR_COOP_* keys, %d whitelist rows, "
          "zero UNACCOUNTED (WV-D41)" % (len(defined), len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
