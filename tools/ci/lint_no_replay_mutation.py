#!/usr/bin/env python
"""
lint_no_replay_mutation.py

WAVE1-RUNBOOK.md SPEC 7 (W1-P12), ruling A4: the S3 ghost stepper is
DISPLAY-ONLY - it may write animation/camera/sound/UI and NOTHING else. It
must never read or write SavedBattleGame/BattleUnit/Tile for anything but
drawing, and it must never call any of the mutator methods that actually
change battle state (setPosition/setDirection/spendTimeUnits/startWalking/
keepWalking/setTimeUnits/setEnergy/setKneeled/setTile/setMapData/addItem/
removeItem).

lint_no_client_mint.py does NOT prove this (WR-22): it only greps for the two
BattleUnit/BattleItem CONSTRUCTOR calls, a completely different failure mode.
This is the SECOND, SCOPED lint step 2 of the W1-P12 packet text asks for,
written BEFORE the stepper itself so it is a constraint, not a rubber stamp.

Mechanism: scan src/ for the RW-REPLAY-REGION-BEGIN/END markers (the region
every line of ghost-stepper code lives inside, per step 1 of the packet) and
fail on any occurrence, INSIDE such a region, of one of the FORBIDDEN TOKENS
below.

FORBIDDEN TOKENS (step 2's own list, verbatim):
    SavedBattleGame, BattleUnit, Tile, setPosition, setDirection,
    spendTimeUnits, startWalking, keepWalking, setTimeUnits, setEnergy,
    setKneeled, setTile, setMapData, addItem, removeItem

BUILDER NOTE ON THE THREE CLASS-NAME TOKENS (recorded so this is a disclosed
judgment call, not a silent relaxation - report this if you disagree): the
packet's OWN step 6a/6b pseudocode requires the stepper to declare exactly
`const BattleUnit*` / `SavedBattleGame*` / `const Tile*` READ-ONLY pointer
parameters (CoopGhost.h's coopGhostView/coopGhostUnitTrailingOverTile/
onEvApplied/advance), and CoopIdMaps::unit() resolution legitimately produces
`BattleUnit*` locals - a blind substring match on the bare class name would
therefore ALSO fail on the packet's own mandated, read-only API shape, and on
every doc comment that so much as NAMES one of these classes in prose (this
region's comments do, constantly - the same style the rest of CoopMod already
writes in). A lint that cannot pass on the spec's own required, non-mutating
code is not a meaningful gate. So: the three CLASS NAMES are flagged only for
the two patterns that are UNAMBIGUOUSLY a mutation risk regardless of
context - constructing one (`new SavedBattleGame`/`new BattleUnit`/`new
Tile`, already covered from a different angle by lint_no_client_mint.py's own
narrower check, but included here too for regional completeness) or a
qualified static/member-function call through the class name
(`SavedBattleGame::`/`BattleUnit::`/`Tile::`). A bare pointer-typed parameter,
return type, or local variable (`BattleUnit* u`, `const Tile* tile`, `Tile*
t = ...`) is the sanctioned read-only-handle shape and is NOT flagged. The
twelve MUTATOR METHOD NAMES are flagged unconditionally, bare-word, exactly
as the packet text says - those are unambiguous regardless of receiver, and
the DONE-WHEN 2 non-vacuity proof (`unit->setDirection(3);`) exercises
exactly this half.

Usage:
    python tools/ci/lint_no_replay_mutation.py [SRC_DIR]

SRC_DIR defaults to "src" relative to the current working directory (i.e.
run this from the repo/worktree root). Exits 0 with a summary line if
nothing forbidden is found inside any region; exits 1 and prints one
"path:line: matched-text" line per offender otherwise.
"""

import os
import re
import sys

BEGIN_MARK = "RW-REPLAY-REGION-BEGIN"
END_MARK = "RW-REPLAY-REGION-END"

# The step-2 forbidden MUTATOR METHOD NAMES, verbatim - flagged unconditionally,
# bare word-boundary match, regardless of receiver.
FORBIDDEN_METHODS = (
    "setPosition",
    "setDirection",
    "spendTimeUnits",
    "startWalking",
    "keepWalking",
    "setTimeUnits",
    "setEnergy",
    "setKneeled",
    "setTile",
    "setMapData",
    "addItem",
    "removeItem",
)

# The step-2 forbidden CLASS NAMES, verbatim - see the module docstring's
# "BUILDER NOTE" for why these are matched only in a construct/qualified-call
# shape rather than as a bare substring (which would also flag the packet's
# own mandated read-only pointer-parameter API and this region's own prose).
FORBIDDEN_CLASSES = ("SavedBattleGame", "BattleUnit", "Tile")

METHOD_RE = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(t) for t in FORBIDDEN_METHODS))
CLASS_NEW_RE = re.compile(r"\bnew\s+(?:%s)\b" % "|".join(re.escape(t) for t in FORBIDDEN_CLASSES))
CLASS_STATIC_RE = re.compile(r"\b(?:%s)\s*::" % "|".join(re.escape(t) for t in FORBIDDEN_CLASSES))

FORBIDDEN_RE_LIST = (METHOD_RE, CLASS_NEW_RE, CLASS_STATIC_RE)

# File extensions worth scanning. This is C++ source; header-only regions are
# just as real as .cpp ones (CoopGhost.h counts as "inside the region" for
# this lint's purposes too).
SOURCE_EXTS = (".cpp", ".h", ".hpp", ".cc", ".cxx")


def scan_file(path):
    """Returns a list of (line_no, line_text) offenders for one file."""
    offenders = []

    # Read leniently: several coop .cpp files in this tree are ISO-8859-1,
    # not UTF-8 (see the ENVIRONMENT PREAMBLE encoding rule) - decoding as
    # latin-1 never raises (every byte value is a valid latin-1 code point)
    # and this script only ever matches plain-ASCII tokens, so no meaning is
    # lost for the purpose of this check (lint_no_client_mint.py precedent).
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

        if not in_region:
            continue

        if any(rx.search(line) for rx in FORBIDDEN_RE_LIST):
            offenders.append((line_no, line.strip()))

    return offenders


def main():
    src_root = sys.argv[1] if len(sys.argv) > 1 else "src"

    if not os.path.isdir(src_root):
        print("lint_no_replay_mutation: no such directory: %s" % src_root)
        return 1

    all_offenders = []  # list of (display_path, line_no, line_text)
    scanned = 0

    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames.sort()
        for filename in sorted(filenames):
            if not filename.endswith(SOURCE_EXTS):
                continue

            full_path = os.path.join(dirpath, filename)
            scanned += 1

            for line_no, line_text in scan_file(full_path):
                display_path = full_path.replace(os.sep, "/")
                all_offenders.append((display_path, line_no, line_text))

    if all_offenders:
        print("lint_no_replay_mutation: FAIL - %d forbidden token occurrence(s) "
              "found inside an RW-REPLAY-REGION:" % len(all_offenders))
        for path, line_no, line_text in all_offenders:
            print("%s:%d: %s" % (path, line_no, line_text))
        return 1

    print("lint_no_replay_mutation: OK - %d file(s) scanned under %s, no forbidden "
          "SavedBattleGame/BattleUnit/Tile mutation token found inside any "
          "RW-REPLAY-REGION (W1-P12 A4)." % (scanned, src_root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
