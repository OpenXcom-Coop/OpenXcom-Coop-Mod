#!/usr/bin/env python
"""
lint_no_client_mint.py

SPIKE-RUNBOOK.md RB-D25 (rewrite spike, R2-P4): mint-discipline enforcement.

Coop battle identity is host-minted (RB-D7/RB-D24): only the host creates
new BattleUnit/BattleItem objects during a coop battle; clients apply
S2-applier events that mirror the host's ids, they never mint their own.
This script is a cheap static guard against that discipline eroding: it
greps src/ for the two constructor call patterns ("new BattleItem(" /
"new BattleUnit(") and fails (non-zero exit, one line per offender) for any
occurrence that is not explicitly whitelisted.

Whitelist (RB-D25):
  (a) Vanilla directories, where vanilla legitimately mints these objects
      on both host and client alike (SavedBattleGame::load(), the
      BattlescapeGenerator unit spawners, etc.) - not coop-authority code
      at all:
        src/Battlescape/**
        src/Savegame/**
  (b) Explicit region markers, anywhere else in src/:
        // RW-MINT-WHITELIST-BEGIN
        ... sanctioned mint(s) ...
        // RW-MINT-WHITELIST-END
      A mint between a BEGIN and its matching END is sanctioned. R2-P4 uses
      this to wrap the two test-harness mints in TestServer.cpp's
      battle_give command (not a vanilla dir, but not an S2 applier either -
      a test-only debug helper). R3's S2 appliers are expected to sit
      inside a region like this too.

Usage:
    python tools/ci/lint_no_client_mint.py [SRC_DIR]

SRC_DIR defaults to "src" relative to the current working directory (i.e.
run this from the repo/worktree root). Exits 0 with a summary line if
nothing outside the whitelist is found; exits 1 and prints one
"path:line: matched-text" line per offender otherwise.

Not wired into a CI shard yet (that lands later, per the R2-P4 packet) -
this script only needs to exist and be runnable by hand for now.
"""

import os
import re
import sys

# Matches "new BattleItem(" / "new BattleUnit(" allowing incidental
# whitespace between the tokens and before the paren (formatting variance),
# but never a different identifier - deliberately narrow, per RB-D25.
MINT_RE = re.compile(r"new\s+(BattleItem|BattleUnit)\s*\(")

BEGIN_MARK = "RW-MINT-WHITELIST-BEGIN"
END_MARK = "RW-MINT-WHITELIST-END"

# Vanilla directories (RB-D25 whitelist (a)), as path segments directly
# under the scanned src root.
VANILLA_DIRS = ("Battlescape", "Savegame")

# File extensions worth scanning. This is C++ source; header-only mints are
# just as real as .cpp ones.
SOURCE_EXTS = (".cpp", ".h", ".hpp", ".cc", ".cxx")


def is_vanilla_path(rel_path):
    """rel_path is POSIX-style, relative to the scanned src root (e.g.
    'Battlescape/BattlescapeGame.cpp' or 'Savegame/Upgrade/Foo.cpp')."""
    first = rel_path.split("/", 1)[0]
    return first in VANILLA_DIRS


def scan_file(path, rel_path):
    """Returns a list of (line_no, line_text) offenders for one file."""
    offenders = []

    if is_vanilla_path(rel_path):
        return offenders  # whitelist (a): vanilla dirs are never scanned

    # Read leniently: several coop .cpp files in this tree are ISO-8859-1,
    # not UTF-8 (see the ENVIRONMENT PREAMBLE encoding rule) - decoding as
    # latin-1 never raises (every byte value is a valid latin-1 code point)
    # and this script only ever matches plain-ASCII patterns, so no meaning
    # is lost for the purpose of this check.
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("latin-1")

    in_region = False
    for line_no, line in enumerate(text.splitlines(), start=1):
        if BEGIN_MARK in line:
            in_region = True
            continue
        if END_MARK in line:
            in_region = False
            continue

        if in_region:
            continue  # whitelist (b): inside a sanctioned region

        if MINT_RE.search(line):
            offenders.append((line_no, line.strip()))

    return offenders


def main():
    src_root = sys.argv[1] if len(sys.argv) > 1 else "src"

    if not os.path.isdir(src_root):
        print("lint_no_client_mint: no such directory: %s" % src_root)
        return 1

    all_offenders = []  # list of (path, line_no, line_text)
    scanned = 0

    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames.sort()
        for filename in sorted(filenames):
            if not filename.endswith(SOURCE_EXTS):
                continue

            full_path = os.path.join(dirpath, filename)
            rel_to_root = os.path.relpath(full_path, src_root).replace(os.sep, "/")
            scanned += 1

            for line_no, line_text in scan_file(full_path, rel_to_root):
                display_path = os.path.join(src_root, rel_to_root).replace(os.sep, "/")
                all_offenders.append((display_path, line_no, line_text))

    if all_offenders:
        print("lint_no_client_mint: FAIL - %d unwhitelisted mint(s) found:" % len(all_offenders))
        for path, line_no, line_text in all_offenders:
            print("%s:%d: %s" % (path, line_no, line_text))
        return 1

    print("lint_no_client_mint: OK - %d file(s) scanned under %s, "
          "no unwhitelisted \"new BattleItem(\"/\"new BattleUnit(\" found "
          "(RB-D25)." % (scanned, src_root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
