#!/usr/bin/env python
"""
lint_no_apply_path_state_ops.py

R4-L6 (PRD r4 T6.2 / T6.4; docs rewrite/prompts/r4l6_lifecycle_rows_lint.md section (g), rulings Q1 b, Q2 c, Q3 b,
Q4 a): the second player's event-apply path must not open, close or replace a screen, nor end the battle, except at
the six ruled sites below. BattlePump.h: "Appliers set flags only - drainApplyQueue() must never push/pop a State".

Mechanism (Q1 b): read src/CoopMod/connectionTCP.cpp only (where the co-op battle apply code lives), latin-1,
CRLF-tolerant; blank out comments, string / char literals and preprocessor lines (line numbers kept); split the file
into its top-level brace-matched function bodies (namespace / class bodies are entered, initializer blocks are not),
each named by its short name. From the root `drainApplyQueue` (exactly one definition) walk breadth-first over every
`name(` call in a reachable body that names a definition in the file (every definition with that short name).

Flagged tokens in a reachable body (Q2 c): the State ops pushState( popState( setState( finishBattle( and the vanilla
calls that push or pop one: btnOkClick( btnCancelClick( coopAnswered( onEndClick( popup(. Plus, anywhere in SRC_DIR
outside comments and strings: EndCoopBattle, EndCoopTurn (T6.4: the legacy battle-end paths stay dead).

Whitelist (exact; each entry must match exactly one hit; a missing entry fails as STALE; an entry matching more than
one hit is a structural error). Each is a site an earlier unit ruled; all act on the top screen the client's own
order opened, or show vanilla's next-turn screen:
    W1 (A1) onApplied                     pushState(     NextTurnState          W1-P13a: the client's next-turn screen
    W2 (A2) coopClientCombatAftermath     pushState(     ScannerState           W2-P4 S-D.2, Q14 a: the scanner screen
    W3 (A3) coopClientCombatAftermath     pushState(     UnitInfoState          W2-P4 S-D.2: the mind-probe screen
    W4 (A4) coopClientMedikitAnswered     coopAnswered(  ms->                   W2-P4 S-D.2, C3 D148: the medi-kit close
    W5 (A5) coopClientSkillAnswered       popup(         CoopSkillContinueState W2-P4 S-E2.2: the skill continue screen
    W6 (A6) coopClientInventoryForceClose btnOkClick(    st->                   W2-P8 S-C1.2: the inventory force-close
A new reachable site is a finding: never add it here without a ruling.

Usage:
    python tools/ci/lint_no_apply_path_state_ops.py [SRC_DIR]

SRC_DIR defaults to the src directory of the tree this script lives in (Q3 b), never the current directory.
Exit 0 with one summary line; exit 1 with one "path:line: [chain] text" line per offender (and one line per STALE
whitelist entry or banned name); exit 2 on a structural error (root not found exactly once, a whitelist entry
matched more than once, unbalanced braces).
"""

import os
import re
import sys
from collections import deque

APPLY_FILE = os.path.join("CoopMod", "connectionTCP.cpp")
ROOT = "drainApplyQueue"
SOURCE_EXTS = (".cpp", ".h", ".hpp", ".cc", ".cxx")
FLAGGED = ("pushState", "popState", "setState", "finishBattle",
           "btnOkClick", "btnCancelClick", "coopAnswered", "onEndClick", "popup")
FLAGGED_RE = re.compile(r"\b(" + "|".join(FLAGGED) + r")\s*\(")
BANNED_RE = re.compile(r"\b(EndCoopBattle|EndCoopTurn)\b")
WHITELIST = (
    ("W1", "onApplied", "pushState", "NextTurnState"),
    ("W2", "coopClientCombatAftermath", "pushState", "ScannerState"),
    ("W3", "coopClientCombatAftermath", "pushState", "UnitInfoState"),
    ("W4", "coopClientMedikitAnswered", "coopAnswered", "ms->"),
    ("W5", "coopClientSkillAnswered", "popup", "CoopSkillContinueState"),
    ("W6", "coopClientInventoryForceClose", "btnOkClick", "st->"),
)
CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
NOT_CALLS = frozenset(("if", "while", "for", "switch", "return", "sizeof", "catch", "alignof", "decltype",
                       "static_cast", "dynamic_cast", "reinterpret_cast", "const_cast", "typeid", "noexcept",
                       "defined", "__declspec", "alignas", "__attribute__", "throw", "new", "delete"))
CHAR_LIT_RE = re.compile(r"'(\\.|[^\\'\n]){1,8}'")
RAW_STR_RE = re.compile(r'R"([^()\\ \n]{0,16})\(')


def strip_code(text):
    """Blank comments, string / char literals and preprocessor lines with spaces; newlines stay (line numbers)."""
    out = []
    i, n = 0, len(text)
    line_start = True
    while i < n:
        c = text[i]
        if line_start and c in " \t":
            out.append(c)
            i += 1
            continue
        if line_start and c == "#":
            # a preprocessor directive, with backslash continuations
            while i < n:
                if text[i] == "\n":
                    if out and text[i - 1] == "\\":
                        out.append("\n")
                        i += 1
                        continue
                    break
                out.append(" ")
                i += 1
            continue
        line_start = False
        if c == "\n":
            out.append(c)
            line_start = True
            i += 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join("\n" if ch == "\n" else " " for ch in text[i:j]))
            i = j
        elif c == "R" and RAW_STR_RE.match(text, i) and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")):
            m = RAW_STR_RE.match(text, i)
            end = text.find(")" + m.group(1) + '"', m.end())
            end = n if end < 0 else end + len(m.group(1)) + 2
            out.append("".join("\n" if ch == "\n" else " " for ch in text[i:end]))
            i = end
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"' and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            if j < n and text[j] == '"':
                j += 1
            out.append(" " * (j - i))
            i = j
        elif c == "'":
            m = CHAR_LIT_RE.match(text, i)
            if m:
                out.append(" " * (m.end() - i))
                i = m.end()
            else:
                out.append(c)
                i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def function_name(header):
    """The short name of a function definition header, or None when the block is not a function body."""
    depth, first = 0, None
    for k, ch in enumerate(header):
        if ch == "(":
            if depth == 0:
                m = re.search(r"([A-Za-z_~][A-Za-z0-9_]*)\s*$", header[:k])
                if m and m.group(1) not in NOT_CALLS and first is None:
                    first = m.group(1)
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "=" and depth == 0:
            return None  # an initializer or a lambda bound to a variable
    if first is None or first in ("namespace", "struct", "class", "union", "enum"):
        return None
    return first


def split_functions(code):
    """[(short name, start offset of '{', end offset of '}')] for every function body; raises ValueError."""
    funcs = []
    i, n = 0, len(code)
    seg_start = 0
    depth_stack = []  # 'scope' for an entered namespace / class / extern block
    while i < n:
        c = code[i]
        if c in ";}":
            if c == "}":
                if not depth_stack:
                    raise ValueError("unbalanced '}' at offset %d" % i)
                depth_stack.pop()
            seg_start = i + 1
            i += 1
            continue
        if c != "{":
            i += 1
            continue
        header = code[seg_start:i]
        flat = " ".join(header.split())
        name = function_name(flat)
        scope = (re.search(r"\b(namespace|extern)\b", flat) and "(" not in flat) or \
                (re.search(r"\b(struct|class|union)\b", flat) and "(" not in flat and "=" not in flat)
        if scope:
            depth_stack.append("scope")
            seg_start = i + 1
            i += 1
            continue
        # skip the whole block (function body, enum, initializer): brace-match it
        depth, j = 0, i
        while j < n:
            if code[j] == "{":
                depth += 1
            elif code[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth != 0:
            raise ValueError("unbalanced '{' at offset %d" % i)
        if name:
            funcs.append((name, i, j))
        seg_start = j + 1
        i = j + 1
    if depth_stack:
        raise ValueError("%d unclosed scope block(s)" % len(depth_stack))
    return funcs


def line_of(text, offset, starts):
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def read(path):
    with open(path, "rb") as f:
        return f.read().decode("latin-1").replace("\r\n", "\n")


def main():
    src_root = sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
    tcp = os.path.join(src_root, APPLY_FILE)
    if not os.path.isfile(tcp):
        print("lint_no_apply_path_state_ops: STRUCTURAL - no %s" % tcp)
        return 2
    raw = read(tcp)
    raw_lines = raw.split("\n")
    code = strip_code(raw)
    starts = [0] + [m.end() for m in re.finditer("\n", code)]
    try:
        funcs = split_functions(code)
    except ValueError as e:
        print("lint_no_apply_path_state_ops: STRUCTURAL - %s: %s" % (tcp, e))
        return 2
    by_name = {}
    for name, a, b in funcs:
        by_name.setdefault(name, []).append((a, b))
    roots = by_name.get(ROOT, [])
    if len(roots) != 1:
        print("lint_no_apply_path_state_ops: STRUCTURAL - %d definition(s) of %s (want exactly 1)" % (len(roots), ROOT))
        return 2

    parent = {ROOT: None}
    order = deque([ROOT])
    while order:
        name = order.popleft()
        for a, b in by_name[name]:
            for m in CALL_RE.finditer(code, a, b):
                callee = m.group(1)
                if callee in by_name and callee not in parent and callee not in NOT_CALLS:
                    parent[callee] = name
                    order.append(callee)

    def chain(name):
        path = []
        while name is not None:
            path.append(name)
            name = parent[name]
        return " > ".join(reversed(path))

    hits = []  # (function, token, line, raw line text)
    for name in parent:
        for a, b in by_name[name]:
            for m in FLAGGED_RE.finditer(code, a, b):
                ln = line_of(code, m.start(), starts)
                hits.append((name, m.group(1), ln, raw_lines[ln - 1].strip()))
    hits.sort(key=lambda h: h[2])

    tcp_disp = tcp.replace(os.sep, "/")
    failures = []
    whitelisted = set()
    for code_id, fn, tok, text in WHITELIST:
        match = [h for h in hits if h[0] == fn and h[1] == tok and text in h[3]]
        if len(match) > 1:
            print("lint_no_apply_path_state_ops: STRUCTURAL - whitelist %s (%s, %s, %r) matched %d hits: %s"
                  % (code_id, fn, tok, text, len(match), [h[2] for h in match]))
            return 2
        if not match:
            failures.append("%s: STALE %s - no reachable %s( with %r in %s (the ruled site moved or is gone)"
                            % (tcp_disp, code_id, tok, text, fn))
        else:
            whitelisted.add(match[0])
    for h in hits:
        if h not in whitelisted:
            failures.append("%s:%d: [%s] %s( - %s" % (tcp_disp, h[2], chain(h[0]), h[1], h[3]))

    scanned = 0
    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames.sort()
        for filename in sorted(filenames):
            if not filename.endswith(SOURCE_EXTS):
                continue
            path = os.path.join(dirpath, filename)
            scanned += 1
            text = read(path)
            if "EndCoop" not in text:
                continue
            stripped = strip_code(text)
            lines = text.split("\n")
            for k, line in enumerate(stripped.split("\n"), 1):
                m = BANNED_RE.search(line)
                if m:
                    failures.append("%s:%d: [src-wide ban, T6.4] %s - %s"
                                    % (path.replace(os.sep, "/"), k, m.group(1), lines[k - 1].strip()))

    if failures:
        print("lint_no_apply_path_state_ops: FAIL - %d problem(s) (State ops reachable from %s beyond the ruled "
              "whitelist, a STALE whitelist entry, or a banned legacy battle-end name):" % (len(failures), ROOT))
        for f in failures:
            print(f)
        return 1
    print("lint_no_apply_path_state_ops: OK - %d file(s) scanned under %s; %s: %d function names (%d bodies), %d "
          "reachable from %s; %d whitelisted, 0 offenders; EndCoopBattle/EndCoopTurn: 0."
          % (scanned, src_root, APPLY_FILE.replace(os.sep, "/"), len(by_name), len(funcs), len(parent), ROOT,
             len(whitelisted)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
