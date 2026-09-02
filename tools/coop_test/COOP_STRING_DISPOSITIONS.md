# `STR_COOP_*` disposition table (WV-D41 whitelist)

Minted by **W1-P1** (wave 1, hygiene packet). **This is a LIVING document, not
a snapshot (IR2-11):** every packet that mints, wires, re-values or deletes a
`STR_COOP_*` key edits this file **in its own commit**. See
[HOW TO APPEND A ROW](#how-to-append-a-row).

## What this file is for

`WAVE1-RUNBOOK.md` **WV-D41** rules that a CI grep asserts **zero UNACCOUNTED
`STR_COOP_*` keys** against this table, which is the grep's **whitelist**. The
grep itself is minted by **W1-P7** (the hard ZERO-ORPHAN assert lands at
**W1-G3**, not W1-G1, because `STR_COOP_END_TURN_TALLY` is deliberately
reserved for W1-P13). A key is ACCOUNTED FOR when, and only when, it has a row
in the [WHITELIST](#whitelist) below.

It lives in the GAME repo (not the docs repo) because the CI grep runs here and
cannot reach `openxcom-coop-agent-docs`. Precedent for a new tooling doc/tool
file in-repo: `tools/coop_test/W1_TRIAGE.md` and RB-D25's
`tools/ci/lint_no_client_mint.py`.

## Parse contract (read this before writing the grep)

- The whitelist is **every line in the WHITELIST table that starts with
  `| STR_COOP_`**. Nothing outside that table is a whitelist entry - in
  particular the [PLANNED KEYS](#planned-keys) section is INFORMATIONAL and
  its keys are deliberately NOT yet in the `.yml` files.
- Column order is stable and MUST NOT be reordered:
  `| KEY | STATE | OWNER | DISPOSITION |`
- **One key per line. Exactly one row per key. No key appears twice.**
- `KEY` is the BARE identifier - no backticks, no quotes. This is load-bearing:
  the PLANNED KEYS rows below are deliberately written WITH backticks so that a
  grep for lines starting `| STR_COOP_` cannot pick them up, and a key can only
  become greppable by being moved into the WHITELIST table unquoted.
- `STATE` is one of:
  - `WIRED` - referenced from `src/` today.
  - `ORPHAN` - present in the `.yml` files, referenced from nowhere in `src/`.
  - `INERT` - intentionally present-but-unreferenced after a packet retired its
    presenter entry (RB-D3's "unused keys are inert" precedent). An `INERT` key
    is accounted for and must NOT be reported by the grep.
- `OWNER` is the packet that resolves the row (`-` when the row needs no
  further work).
- Keys live in BOTH `bin/common/Language/en-US.yml` and
  `bin/common/Language/en-GB.yml`. A packet that changes a value changes BOTH,
  and then does the **WV-D17 robocopy** of `bin/common` + `bin/standard` into
  `bin/x64/Release/` before running the harness - otherwise the banner renders
  as its raw `STR_` key and any test asserting exact text fails for the wrong
  reason.

## Baseline

Verified at `8c53c2592` (W1-P1). `bin/common/Language/en-GB.yml` and
`en-US.yml` carry **32** `STR_COOP_*` keys; **14 are WIRED** and **18 are
ORPHAN**.

**DISCREPANCY LOGGED (W1-P1, VERIFY-NEVER-INFER).** `WAVE1-RUNBOOK.md` W1-P1
item 5 names **7** orphaned keys (the `en-GB.yml:33-41` block). That block is
correct and its 7 keys are all really orphaned, but it is **not the whole
orphan set**: 11 further keys - the 6 `STR_COOP_CRASH_REPORT_*` and 5 of the
`STR_COOP_DESYNC_*` - are equally unreferenced, because the R1-P3 quarantine
removed the code that used them (`CoopCrashPromptState`,
`maybeReportPreviousCrash` and the crash-seen ledger return ZERO hits under
`src/` at `8c53c2592`; the PRD-P2/PRD-I4 desync-report dialog went the same
way). They are listed here because WV-D41's grep would otherwise report 11
UNACCOUNTED keys the wave never planned for. **Their rows record facts, not
new decisions:** no packet in wave 1 owns them, and whether they are re-wired
or deleted is an OWNER call, flagged in
[OPEN FOR THE OWNER](#open-for-the-owner).

## WHITELIST

| KEY | STATE | OWNER | DISPOSITION |
|---|---|---|---|
| STR_COOP_PLAYER_BUSY | ORPHAN | W1-P7 | WIRE-OR-DELETE. Runbook W1-P1 item 5 "the rest wire-or-delete in W1-P7". Overlaps STR_COOP_DENY_BUSY, which is the live SS2.6 admission string. |
| STR_COOP_TURN_OVER | ORPHAN | W1-P7 | RE-VALUE + WIRE, then retire. SS2.W8 / WV-D23 / D-10: W1-P7 REPLACES the current value (today it literally reads "The turn has already ended", the wrong text) with "Only the host can end the turn" and adds a `(local)` presenter row for the END-TURN client refusal. W1-P13 RETIRES the presenter row once `bt_end_turn_ready` exists; the key then becomes INERT (this row is updated to INERT by W1-P13). DISTINCT from STR_COOP_DENY_TURN_OVER, which keeps its text. |
| STR_COOP_NOT_YOUR_SOLDIER | ORPHAN | W1-P7 | WIRE-OR-DELETE. Duplicates STR_COOP_DENY_NOT_YOUR_UNIT's text exactly ("Not one of your soldiers"). |
| STR_COOP_ACTION_REFUSED | ORPHAN | W1-P7 | WIRE-OR-DELETE. Generic; ADDENDUM 1.3(e) forbids collapsing reasons into a generic message, so a wire is unlikely to be right. |
| STR_COOP_ACTION_TIMEOUT | ORPHAN | W1-P7 | WIRE. D7 / WV-D13 / WV-D24: the intent timeout (10 s, behind a coop OptionInfo per WR-25) fires this string and unlocks the IR-2 slot. NON-NEGOTIABLE before any real-network play. |
| STR_COOP_WAIT_FOR_PLAYER_ACTION | ORPHAN | W1-P7 | WIRE-OR-DELETE. D7's donor two-surface model names a seat-attributed "Please wait for {0}'s action to finish" driver; ADDENDUM (f) killed the OLD P5 busy-owner driving logic that used to feed it (see `W1_TRIAGE.md`'s `test_coop_wait_banner.py` row). W1-P7 decides. |
| STR_COOP_END_TURN_TALLY | ORPHAN | W1-P13 | WIRE. D1 / WV-D7 / SS2.W3: the "END TURN {0}/{1}" readiness counter on the re-added `_txtCoopEndTurn` surface. RESERVED until then - this is why WV-D41 puts the hard zero-orphan assert at W1-G3 and not W1-G1. |
| STR_COOP_DESYNC_REPORT_SAVED | ORPHAN | none (out of wave) | UNSCHEDULED. PRD-P2 rider desync auto-report bundle dialog; its state was removed by the R1-P3 quarantine. See OPEN FOR THE OWNER. |
| STR_COOP_DESYNC_OPEN_FOLDER | ORPHAN | none (out of wave) | UNSCHEDULED. PRD-I4 one-click desync report UX. See OPEN FOR THE OWNER. |
| STR_COOP_DESYNC_REPORT_GITHUB | ORPHAN | none (out of wave) | UNSCHEDULED. PRD-I4 one-click desync report UX. See OPEN FOR THE OWNER. |
| STR_COOP_DESYNC_HEADLINE_ACTION | ORPHAN | none (out of wave) | UNSCHEDULED. PRD-I4 attribution headline ("{0} diverged at action {1}: {2}"). See OPEN FOR THE OWNER. |
| STR_COOP_DESYNC_HEADLINE_TERM | ORPHAN | none (out of wave) | UNSCHEDULED. PRD-I4 attribution headline, inert-sync-check variant. See OPEN FOR THE OWNER. |
| STR_COOP_CRASH_REPORT_PROMPT | ORPHAN | none (out of wave) | UNSCHEDULED. PRD-I5 next-launch crash reporter; `CoopCrashPromptState` does not exist at 8c53c2592. Same unlock as `test_crash_reporter.py`'s SKIP-PENDING(PRD-I5 rebuild). |
| STR_COOP_CRASH_REPORT_HEADLINE | ORPHAN | none (out of wave) | UNSCHEDULED. PRD-I5, as above. |
| STR_COOP_CRASH_REPORT_BUNDLE | ORPHAN | none (out of wave) | UNSCHEDULED. PRD-I5, as above. |
| STR_COOP_CRASH_REPORT_NOT_NOW | ORPHAN | none (out of wave) | UNSCHEDULED. PRD-I5, as above. |
| STR_COOP_CRASH_REPORT_NEVER | ORPHAN | none (out of wave) | UNSCHEDULED. PRD-I5, as above. |
| STR_COOP_CRASH_REPORT_SAVED | ORPHAN | none (out of wave) | UNSCHEDULED. PRD-I5, as above. |
| STR_COOP_DENY_BUSY | WIRED | - | SS2.6 deny table, `kReasonStrTable` (connectionTCP.cpp:3069). |
| STR_COOP_DENY_PATH_CHANGED | WIRED | - | SS2.6 deny table (connectionTCP.cpp:3070). |
| STR_COOP_DENY_COST_CHANGED | WIRED | - | SS2.6 deny table (connectionTCP.cpp:3071). |
| STR_COOP_DENY_TARGET_MOVED | WIRED | - | SS2.6 deny table (connectionTCP.cpp:3072). |
| STR_COOP_DENY_TARGET_DEAD | WIRED | - | SS2.6 deny table (connectionTCP.cpp:3073). |
| STR_COOP_DENY_WEAPON_MISSING | WIRED | - | SS2.6 deny table (connectionTCP.cpp:3074). |
| STR_COOP_DENY_NOT_YOUR_UNIT | WIRED | - | SS2.6 deny table (connectionTCP.cpp:3075). |
| STR_COOP_DENY_TURN_OVER | WIRED | - | SS2.6 deny table (connectionTCP.cpp:3076). Keeps its text; SS2.W8 does NOT touch it. |
| STR_COOP_CANCEL_ENEMY_SPOTTED | WIRED | - | SS2.6 cancel table (connectionTCP.cpp:3078). Reused by SS2.W2's halt presenter for `reason:"spot"`. |
| STR_COOP_CANCEL_UNIT_UNDER_FIRE | WIRED | - | SS2.6 cancel table (connectionTCP.cpp:3079). Reused by SS2.W2's halt presenter for `reason:"reaction"`. |
| STR_COOP_CANCEL_UNIT_DOWN | WIRED | - | SS2.6 cancel table (connectionTCP.cpp:3080). Reused by SS2.W2's halt presenter for `reason:"unit_down"`. |
| STR_COOP_CANCEL_NEW_CONTACT | WIRED | - | SS2.6 cancel table (connectionTCP.cpp:3081). |
| STR_COOP_CANCEL_EVENT | WIRED | - | SS2.6 unknown-cause fallback, "Order cancelled - {0}" (connectionTCP.cpp:2624, :2636). NOTE: SS2.W2/WV-D53 forbids reusing this shape for walk HALT reasons - a halted walk is not a cancelled order and must never render a raw wire enum in a `{0}` slot. |
| STR_COOP_DESYNC_HALTED | WIRED | - | R2-P9 sticky desync banner (connectionTCP.cpp:3171, CoopBattleUi.h:101). |

## PLANNED KEYS

**INFORMATIONAL ONLY - these are NOT whitelist entries and are NOT in the
`.yml` files yet.** They are listed so no packet forgets to append its row.
The packet that MINTS the key moves it into the WHITELIST table above, in the
same commit. Source: `WAVE1-RUNBOOK.md` SS2.W2's halt-presenter table
(WV-D53).

| KEY (planned, backticked on purpose - see the parse contract) | MINTED BY | NOTE |
|---|---|---|
| `STR_COOP_HALT_PATH_BLOCKED` | W1-P9 | halt `reason:"blocked"`. Worded as stop-after-partial-execution ("Move stopped - path blocked"), NEVER "Order cancelled - ...". |
| `STR_COOP_HALT_PROXIMITY` | W1-P11 | halt `reason:"prox"`. Not producible by walk-core. |
| `STR_COOP_HALT_FELL` | reserved (walk-FULL, next wave) | halt `reason:"fall"`. Reserved; do not mint in wave 1. |

`no_tu` and `no_energy` deliberately mint NOTHING: SS2.W2 reuses vanilla
`STR_NOT_ENOUGH_TIME_UNITS` / `STR_NOT_ENOUGH_ENERGY`. Those are not
`STR_COOP_*` keys and never enter this table.

## HOW TO APPEND A ROW

In the SAME commit that mints, wires, re-values or retires the key:

1. Add or edit the key in **both** `bin/common/Language/en-US.yml` and
   `bin/common/Language/en-GB.yml`.
2. Add **one** row to the WHITELIST table above (or edit the existing row -
   never add a second row for a key that already has one). Keep the column
   order `| KEY | STATE | OWNER | DISPOSITION |`.
3. If you moved a key out of PLANNED KEYS, delete its planned row.
4. Set `STATE` truthfully: `WIRED` once `src/` references it, `INERT` if your
   packet deliberately left it present-but-unreferenced, `ORPHAN` otherwise.
5. Do the **WV-D17 robocopy** (`bin/common` + `bin/standard` ->
   `bin/x64/Release/`) before running the harness, and assert **exact text**,
   never non-emptiness (wave-1 rule).
6. Cite WV-D41 in the commit body.

## OPEN FOR THE OWNER

Raised by W1-P1; **not decided here** (a builder does not re-decide, and these
keys are outside every wave-1 packet's scope):

- The **11 quarantine orphans** (6 `STR_COOP_CRASH_REPORT_*` + 5
  `STR_COOP_DESYNC_*`) belong to features the R1-P3 vanilla restore removed
  (PRD-I5 next-launch crash reporter; PRD-P2/PRD-I4 desync auto-report
  dialog). No wave-1 packet rebuilds either. They must be either (a) kept as
  accounted-for placeholders until those features are rebuilt - which is what
  their rows above assume - or (b) deleted from both `.yml` files now and
  re-added by the rebuild. Until the owner rules, they stay whitelisted so
  WV-D41's grep is meaningful rather than permanently red.
- `test_crash_reporter.py` is the test that unblocks with the PRD-I5 half; its
  guard was re-pointed to `SKIP-PENDING(PRD-I5 rebuild)` by this same packet
  (`W1_TRIAGE.md`, W1-P1 re-points section).

---

*W1-P1, wave 1. Baseline verified at `8c53c2592`. Cite WV-D41 / WV-D32 /
SS2.W8 / WV-D53 when you edit this file.*
