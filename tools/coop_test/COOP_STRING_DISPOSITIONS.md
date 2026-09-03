# `STR_COOP_*` disposition table (WV-D41 whitelist)

Minted by **W1-P1** (wave 1, hygiene packet). **This is a LIVING document, not
a snapshot (IR2-11):** every packet that mints, wires, re-values or deletes a
`STR_COOP_*` key edits this file **in its own commit**. See
[HOW TO APPEND A ROW](#how-to-append-a-row).

## What this file is for

`WAVE1-RUNBOOK.md` **WV-D41** rules that a CI grep asserts **zero UNACCOUNTED
`STR_COOP_*` keys** against this table, which is the grep's **whitelist**. The
grep itself was minted by **W1-P7** and lives at
**`tools/ci/lint_coop_strings.py`** (run it with no arguments from the repo
root; exit 0 = clean). The hard ZERO-ORPHAN assert lands at **W1-G3**, not
W1-G1, because `STR_COOP_END_TURN_TALLY` is deliberately reserved for W1-P13. A
key is ACCOUNTED FOR when, and only when, it has a row in the
[WHITELIST](#whitelist) below.

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

**UPDATE (W1-P4, `f360b8f77`+):** **33** keys - `STR_COOP_EQUIP_FROZEN` was
minted AND wired in the same commit (the equip-freeze notice), so the split is
now **15 WIRED / 18 ORPHAN**. The orphan set is unchanged.

**UPDATE (W1-P5):** **38** keys - five minted AND wired in the same commit
(the D8 client hard gates: abort / mid-battle inventory / zero-TU /
hand-reaction toggles / local load). Split is now **20 WIRED / 18 ORPHAN**;
the orphan set is again unchanged. W1-P5 deliberately minted new specific keys
rather than repurposing an orphan - see the note under the new rows.

**UPDATE (W1-P7, ruling D7 = WV-D13):** **37** keys - THREE orphans DELETED and
ONE new key minted AND wired, all in the same commit. Split is now
**23 WIRED / 14 ORPHAN**, and the orphan set finally MOVES: of the runbook's
original 7, `STR_COOP_TURN_OVER` (re-valued, SS2.W8), `STR_COOP_ACTION_TIMEOUT`
(WV-D24) and `STR_COOP_WAIT_FOR_PLAYER_ACTION` (the donor wait driver) are now
WIRED, `STR_COOP_PLAYER_BUSY` / `STR_COOP_NOT_YOUR_SOLDIER` /
`STR_COOP_ACTION_REFUSED` are DELETED from both `.yml` files, and only
`STR_COOP_END_TURN_TALLY` remains - RESERVED for W1-P13, which is exactly why
WV-D41 puts the hard zero-orphan assert at W1-G3. The 11 RESERVED quarantine
orphans are untouched (owner ruling 2026-09-02: they are NOT W1-P7's to delete).
Per-key rationale is in each row below; the deleted keys' rationale is also
carried as a comment block in both `.yml` files at the point of deletion.

**UPDATE (W1-P6):** **39** keys - ONE minted AND wired in the same commit
(`STR_COOP_SPECTATOR_MODE`, the battle-entry spectator notice, ruling D6 =
WV-D12). Split is now **21 WIRED / 18 ORPHAN**; the orphan set is again
unchanged. W1-P6's OTHER refusal - a seat click-selecting a soldier it does not
command - deliberately mints NOTHING and reuses the live SS2.6 key
`STR_COOP_DENY_NOT_YOUR_UNIT` ("Not one of your soldiers"), the same wording
W1-P5's ownership arm reuses and the one D6's own acceptance quotes.

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
| STR_COOP_TURN_OVER | WIRED | W1-P13 | RE-VALUED + WIRED by W1-P7 (SS2.W8 / WV-D23 / ruling D-10). Value REPLACED - it used to read "The turn has already ended", which is factually wrong at the only place it is reachable - and is now "Only the host can end the turn". Raised by `CoopBattleUi::showEndTurnHostOnly()` from `BattlescapeState::btnEndTurnClick`, which previously routed this refusal through `showDeny("turn_over")`, i.e. through the SS2.6 WIRE deny table. Client-side only: NO `not_your_turn` reason was added to the SS2.2 enum. REACHABILITY (WR-3): `allowButtons()` requires `_save->getSide() == FACTION_PLAYER`, so an off-turn press never reaches the handler - the state this covers is a co-op CLIENT pressing END TURN during ITS OWN side. LIFETIME: **W1-P13 RETIRES the presenter entry** once `bt_end_turn_ready` exists and flips this row to INERT (RB-D3's "unused keys are inert"). DISTINCT from STR_COOP_DENY_TURN_OVER, which keeps its own text. |
| STR_COOP_ACTION_TIMEOUT | WIRED | - | WIRED by W1-P7 (D7 / WV-D13 item 3 / WV-D24 = D-11). `CoopBattleUi::showIntentTimeout()`, raised by `CoopArbiter::tickIntentTimeout()` at the RB-D5 pump point when an intent goes unanswered for `Options::coopIntentTimeoutSeconds` (default 10, a real `Options.inc.h` + `Options.cpp` OptionInfo per WR-25, never a `connectionTCP` static). Firing it RELEASES the IR-2 one-slot input lock - before this a lost intent locked its unit for the rest of the battle. A late `bt_ack`/`bt_deny` for that iseq is then permanently ignored; a late `bt_action_end` still applies. |
| STR_COOP_WAIT_FOR_PLAYER_ACTION | WIRED | - | **WIRED** by W1-P7 (D7 / WV-D13 item 4) - the decision its old row left open. The donor's seat-attributed wait driver (`cbff7951d:BattlescapeState.cpp:5292-5370`, whose `getPrimaryBusyActor()` call site is `:5317`) is re-homed out of the vanilla per-frame method into CoopMod: `CoopBattleUi::tick()` + `waitBannerText()`, fed by `CoopArbiter::busyOwnerSeat()`. Shown when the seat blocking this machine is NOT this machine's own (donor semantics: suppressed when the running chain is your own action) and the seat can be NAMED; otherwise the generic SS2.6 `STR_COOP_DENY_BUSY` row is used, so an empty `{0}` can never render. |
| STR_COOP_END_TURN_TALLY | ORPHAN | W1-P13 | WIRE. D1 / WV-D7 / SS2.W3: the "END TURN {0}/{1}" readiness counter on the re-added `_txtCoopEndTurn` surface. RESERVED until then - this is why WV-D41 puts the hard zero-orphan assert at W1-G3 and not W1-G1. |
| STR_COOP_DESYNC_REPORT_SAVED | ORPHAN | RESERVED (owner 2026-09-02) | ACCOUNTED PLACEHOLDER, ruling (a). PRD-P2 rider desync auto-report bundle dialog; its state was removed by the R1-P3 quarantine. See OPEN FOR THE OWNER. |
| STR_COOP_DESYNC_OPEN_FOLDER | ORPHAN | RESERVED (owner 2026-09-02) | ACCOUNTED PLACEHOLDER, ruling (a). PRD-I4 one-click desync report UX. See OPEN FOR THE OWNER. |
| STR_COOP_DESYNC_REPORT_GITHUB | ORPHAN | RESERVED (owner 2026-09-02) | ACCOUNTED PLACEHOLDER, ruling (a). PRD-I4 one-click desync report UX. See OPEN FOR THE OWNER. |
| STR_COOP_DESYNC_HEADLINE_ACTION | ORPHAN | RESERVED (owner 2026-09-02) | ACCOUNTED PLACEHOLDER, ruling (a). PRD-I4 attribution headline ("{0} diverged at action {1}: {2}"). See OPEN FOR THE OWNER. |
| STR_COOP_DESYNC_HEADLINE_TERM | ORPHAN | RESERVED (owner 2026-09-02) | ACCOUNTED PLACEHOLDER, ruling (a). PRD-I4 attribution headline, inert-sync-check variant. See OPEN FOR THE OWNER. |
| STR_COOP_CRASH_REPORT_PROMPT | ORPHAN | RESERVED (owner 2026-09-02) | ACCOUNTED PLACEHOLDER, ruling (a). PRD-I5 next-launch crash reporter; `CoopCrashPromptState` does not exist at 8c53c2592. Same unlock as `test_crash_reporter.py`'s SKIP-PENDING(PRD-I5 rebuild). |
| STR_COOP_CRASH_REPORT_HEADLINE | ORPHAN | RESERVED (owner 2026-09-02) | ACCOUNTED PLACEHOLDER, ruling (a). PRD-I5, as above. |
| STR_COOP_CRASH_REPORT_BUNDLE | ORPHAN | RESERVED (owner 2026-09-02) | ACCOUNTED PLACEHOLDER, ruling (a). PRD-I5, as above. |
| STR_COOP_CRASH_REPORT_NOT_NOW | ORPHAN | RESERVED (owner 2026-09-02) | ACCOUNTED PLACEHOLDER, ruling (a). PRD-I5, as above. |
| STR_COOP_CRASH_REPORT_NEVER | ORPHAN | RESERVED (owner 2026-09-02) | ACCOUNTED PLACEHOLDER, ruling (a). PRD-I5, as above. |
| STR_COOP_CRASH_REPORT_SAVED | ORPHAN | RESERVED (owner 2026-09-02) | ACCOUNTED PLACEHOLDER, ruling (a). PRD-I5, as above. |
| STR_COOP_ORDER_SENT | WIRED | - | MINTED + WIRED by W1-P7 (D7 / WV-D13 item 2). The "order sent" IN-FLIGHT indicator: `CoopBattleUi::showOrderSent()`, raised by `CoopArbiter::sendClientIntent()` the moment the `bt_intent` envelope ships and cleared when the round trip ends (an applied `bt_action_end`, or replaced by a deny/pending/timeout). Before this packet the window between the click and the host's answer showed NOTHING, which is the gap D7 opens with. A NEW key rather than a repurposed orphan: `STR_COOP_PLAYER_BUSY` ("Another action is running - try again") describes the host being busy, not this machine's order being in flight. |
| STR_COOP_DENY_BUSY | WIRED | - | SS2.6 deny table, `kReasonStrTable` (connectionTCP.cpp:3069). Also the fallback wording of W1-P7's wait driver when the blocking seat cannot be named. |
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
| STR_COOP_HALT_PATH_BLOCKED | WIRED | - | MINTED + WIRED by W1-P9 (WAVE1-RUNBOOK.md SS2.W2 / WV-D53 / IR2-11). The `blocked` row of the WALK HALT presenter, `CoopBattleUi::showWalkHalt()`, raised on the CLIENT apply path when a `bt_action_end` carrying `halted:true` + `reason:"blocked"` resolves an action THIS client ordered. SS2.W2's halt enum is DISTINCT from SS2.2's deny enum, and its table has NO `{0}` catch-all - an unknown reason shows nothing and logs. Of the eight reasons this is the ONLY new key: `spot`/`reaction`/`unit_down` reuse the three `_CANCEL_` rows above, `no_tu`/`no_energy` reuse VANILLA's own `STR_NOT_ENOUGH_TIME_UNITS`/`STR_NOT_ENOUGH_ENERGY` (the exact strings vanilla writes to `_action.result` at UnitWalkBState's two guards), and `prox` (`STR_COOP_HALT_PROXIMITY`, W1-P11) / `fall` (`STR_COOP_HALT_FELL`, walk-FULL) are RESERVED and not minted here because walk-core cannot produce either - minting them now would create WV-D41 orphans. WORDING: a halted walk is NOT "cancelled" (the unit moved), so it reads "Move stopped - path blocked", never "Order cancelled - ...". |
| STR_COOP_DESYNC_HALTED | WIRED | - | R2-P9 sticky desync banner (connectionTCP.cpp:3171, CoopBattleUi.h:101). |
| STR_COOP_EQUIP_FROZEN | WIRED | - | MINTED + WIRED by W1-P4 (WAVE1-RUNBOOK.md ruling D3 = WV-D9/WV-D34, mechanism WV-D43). The pre-battle equip FREEZE notice, raised through the `_txtCoopWait` presenter by `CoopBattleUi::showEquipFrozen()` - on the HOST from `CoopHandshake::freezePreBattleEquip()` (the skipped `InventoryState` push in `BriefingState::btnOkClick`) and on the CLIENT from the battle entry in `CoopHandshake::onBlobChunkAppended()`. Unusual for this table: it explains a screen that was SKIPPED, not a button that was refused, so it is raised at the skip. Un-wiring belongs to the synchronized-equip initiative, when `inventory_move` un-freezes equip. |
| STR_COOP_ABORT_HOST_ONLY | WIRED | - | MINTED + WIRED by W1-P5 (WAVE1-RUNBOOK.md ruling D8 = WV-D14). `BattlescapeState::btnAbortClick` -> `CoopBattleUi::refuseControl(Control::Abort)`. Aborting ends in `setAborted()` + `finishBattle()` - battle-wide and host-authoritative - and the strict-majority VOTE legacy used for it is r4 T3 (`executeVoteAction("abandon_mission")` is still a logging stub), so until then a client may not open the dialog at all. |
| STR_COOP_INVENTORY_HOST_ONLY | WIRED | - | MINTED + WIRED by W1-P5 (WV-D14). `BattlescapeState::btnInventoryClick` (the MID-battle screen, distinct from W1-P4's pre-battle freeze). Every move inside it writes the hashed `items` bucket with nothing on the wire - `inventory_move` is out of wave 1 (WV-D34). Un-wiring belongs to the synchronized-equip initiative. |
| STR_COOP_ZERO_TU_HOST_ONLY | WIRED | - | MINTED + WIRED by W1-P5 (WV-D14). `BattlescapeState::btnZeroTUsClick` -> `BattleUnit::clearTimeUnits()`, a local state mint straight into the `unitsStats` bucket. |
| STR_COOP_REACTIONS_HOST_ONLY | WIRED | - | MINTED + WIRED by W1-P5 (WV-D14). The right-click branch of `BattlescapeState::btn{Left,Right}HandItemClick` -> `toggle{Left,Right}HandForReactions()`. Those fields (`preferredHandForReactions`, `reactionsDisabledFor{Left,Right}Hand`) are serialized (BattleUnit.cpp:791-796) and are NOT on `saveBlobExcludedUnitKey`'s list, so a client toggle diverged saveBlob immediately - proven by `test_rw_client_gates.py`'s phase-3 negative control. These are evidence F2's "open item 9" fields; W1-P15's audit gives them a bucket home. |
| STR_COOP_SPECTATOR_MODE | WIRED | - | MINTED + WIRED by W1-P6 (WAVE1-RUNBOOK.md ruling D6 = WV-D12). The battle-ENTRY spectator notice, raised by `CoopBattleUi::showSpectatorMode()` from `CoopHandshake::selectOwnUnitAtEntry()` when this machine's seat commands no unit at all, so the entry auto-select had nothing to select. Legacy carried the same message in its own client unit selector (`1e0f9276f:BattlescapeState.cpp:1630`). A REAL path, not defensive framing: a plain classic "NEW BATTLE > COOP" skirmish never calls `Soldier::setCoop()`, so without the harness's `newbattle_seat_soldier` lever the joining client owns ZERO battle units - which is exactly the fixture `test_rw_input_gating.py`'s spectator scenario drives. Like `STR_COOP_EQUIP_FROZEN` it explains an absence rather than a refused press, and it is an entry notice, not sticky. |
| STR_COOP_LOCAL_LOAD_BLOCKED | WIRED | - | MINTED + WIRED by W1-P5 (WV-D14, evidence F1). Two sites: the battlescape quick-load hotkey (`BattlescapeState::handle`, whose `localLoadsAllowed()` wrapper the rewrite had deleted) and `LoadGameState::init`'s own chokepoint, whose refusal was LOG-ONLY. SESSION-scoped, not client-only: `connectionTCP::localLoadsAllowed()` is false for the HOST too while a session is live (PRD-08 C7). Presenter no-ops with no live battle, so a geoscape-side local load stays log-only - stated limit. |

**W1-P5 note on the orphans (owner ruling 2026-09-02 / orchestrator dispatch):**
the five rows above are NEW keys, not repurposed orphans, and that was
deliberate. Two orphans looked close and were both left for **W1-P7**, whose
row they already have: `STR_COOP_ACTION_REFUSED` ("Action refused") is exactly
the generic shape ADDENDUM SS1.3(e) forbids, so no gate may collapse into it;
and `STR_COOP_NOT_YOUR_SOLDIER` duplicates `STR_COOP_DENY_NOT_YOUR_UNIT`'s text
word for word - W1-P5's ownership term therefore REUSES the live SS2.6 key
(`STR_COOP_DENY_NOT_YOUR_UNIT`) and mints no sixth key, leaving the duplicate's
wire-or-delete call where it belongs.

**W1-P7's answer to that call (ruling D7 = WV-D13 item 5), one line each:**

- `STR_COOP_ACTION_REFUSED` ("Action refused") - **DELETED.** It is *verbatim*
  the shape ADDENDUM SS1.3(e) forbids ("Action refused" is the example the rule
  names). Keeping it in the table would be keeping a loaded gun: every future
  packet that needs a refusal string would find a generic one already there.
  Deleting it makes the next builder mint a reason-specific key, which is the
  rule.
- `STR_COOP_NOT_YOUR_SOLDIER` ("Not one of your soldiers") - **DELETED.** It is
  word-for-word identical to the live SS2.6 `STR_COOP_DENY_NOT_YOUR_UNIT`, which
  BOTH ownership refusals in the tree already reuse (W1-P5's `refuseControl`
  term 2 and W1-P6's `refuseSelectUnitClick`). Two keys for one sentence is a
  translation-drift bug waiting to happen: a translator can make the wire deny
  and the local refusal disagree about the same fact.
- `STR_COOP_PLAYER_BUSY` ("Another action is running - try again") - **DELETED.**
  It overlaps the live SS2.6 `STR_COOP_DENY_BUSY` ("Waiting - another action is
  in progress"), which is the admission model's own busy row and is what both
  the deny and the pending hold already show. Its "try again" wording is also
  now actively WRONG: R2-P7's auto-retry means the client retries by itself, so
  telling the player to try again describes behaviour the build no longer has.
  W1-P7's own in-flight indicator is a NEW key (`STR_COOP_ORDER_SENT`) because
  it says something different - *your* order is in flight, not *the host* is
  busy.

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

## OPEN FOR THE OWNER - **RESOLVED 2026-09-02**

Raised by W1-P1; **RULED by the owner on 2026-09-02** (a builder does not re-decide, and these
keys are outside every wave-1 packet's scope):

- The **11 quarantine orphans** (6 `STR_COOP_CRASH_REPORT_*` + 5
  `STR_COOP_DESYNC_*`) belong to features the R1-P3 vanilla restore removed
  (PRD-I5 next-launch crash reporter; PRD-P2/PRD-I4 desync auto-report
  dialog). No wave-1 packet rebuilds either. They must be either (a) kept as
  accounted-for placeholders until those features are rebuilt - which is what
  their rows above assume - or (b) deleted from both `.yml` files now and
  re-added by the rebuild.
  **OWNER RULING 2026-09-02 = (a).** They STAY, as ACCOUNTED placeholders
  reserved for the PRD-I5 crash-prompt / desync-dialog rebuild. Consequence,
  also owner-ruled: **W1-G3 criterion 5b reads "ZERO UNACCOUNTED
  `STR_COOP_*` keys", never a literal zero** (amendment note in
  `WAVE1-RUNBOOK.md` SS5 + WV-D41), and **W1-P7 item 5's "wire or delete"
  applies ONLY to the runbook's original 7 minus any reserved** - these 11
  are NOT W1-P7's to delete.
- `test_crash_reporter.py` is the test that unblocks with the PRD-I5 half; its
  guard was re-pointed to `SKIP-PENDING(PRD-I5 rebuild)` by this same packet
  (`W1_TRIAGE.md`, W1-P1 re-points section).

---

*W1-P1, wave 1; last edited by W1-P7. Baseline verified at `8c53c2592`. Cite
WV-D41 / WV-D32 / SS2.W8 / WV-D53 when you edit this file. The CI grep that
reads this table is `tools/ci/lint_coop_strings.py` (W1-P7).*
