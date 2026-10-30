# `STR_COOP_*` disposition table (CI whitelist)

Every `STR_COOP_*` key in the language files has a row in this table. A change
that adds, wires, re-words or retires a `STR_COOP_*` key edits this file **in
the same commit**. See [HOW TO APPEND A ROW](#how-to-append-a-row).

## What this file is for

**`tools/ci/lint_coop_strings.py`** (run it with no arguments from the repo
root; exit 0 = clean) asserts **zero UNACCOUNTED `STR_COOP_*` keys** against
this table, which is the lint's **whitelist**. A key is ACCOUNTED FOR when, and
only when, it has a row in the [WHITELIST](#whitelist) below. An ORPHAN key is
allowed as long as its row says so.

## Parse contract

- The whitelist is **every line in the WHITELIST table that starts with
  `| STR_COOP_`**. Nothing outside that table is a whitelist entry - in
  particular the [PLANNED KEYS](#planned-keys) section is INFORMATIONAL and
  its keys are deliberately NOT yet in the `.yml` files.
- Column order is stable and MUST NOT be reordered:
  `| KEY | STATE | PENDING | DISPOSITION |`
- **One key per line. Exactly one row per key. No key appears twice.**
- `KEY` is the BARE identifier - no backticks, no quotes. The PLANNED KEYS rows
  below are deliberately written WITH backticks so that a grep for lines
  starting `| STR_COOP_` cannot pick them up, and a key can only become
  greppable by being moved into the WHITELIST table unquoted.
- `STATE` is one of:
  - `WIRED` - referenced from `src/` today.
  - `ORPHAN` - present in the `.yml` files, referenced from nowhere in `src/`.
  - `INERT` - intentionally present but unreferenced after the code that
    showed it was removed. An `INERT` key is accounted for and must NOT be
    reported by the lint.
- `PENDING` names a later change that still affects the row (`-` when none
  does).
- Keys live in BOTH `bin/common/Language/en-US.yml` and
  `bin/common/Language/en-GB.yml`. A change to a value changes BOTH, and then
  copies `bin/common` + `bin/standard` into `bin/x64/Release/` (robocopy)
  before running the harness - otherwise the banner renders as its raw `STR_`
  key and any test asserting exact text fails for the wrong reason.

## WHITELIST

| KEY | STATE | PENDING | DISPOSITION |
|---|---|---|---|
| STR_COOP_TURN_OVER | INERT | - | Retired: the client's END TURN press arms the readiness tally (`bt_end_turn_ready`) instead of being refused, so no code raises this key. The value ("Only the host can end the turn") stays in both `.yml` files but is unreferenced from `src/`. DISTINCT from STR_COOP_DENY_TURN_OVER, which keeps its own text and its own (unrelated) wire deny reason. |
| STR_COOP_ACTION_TIMEOUT | WIRED | - | `CoopBattleUi::showIntentTimeout()`, raised by `CoopArbiter::tickIntentTimeout()` at the pump point when an intent goes unanswered for `Options::coopIntentTimeoutSeconds` (default 10, a real `Options.inc.h` + `Options.cpp` OptionInfo, never a `connectionTCP` static). Firing it RELEASES the one-slot input lock, so a lost intent never locks its unit for the rest of the battle. A late `bt_ack`/`bt_deny` for that iseq is then permanently ignored; a late `bt_action_end` still applies. |
| STR_COOP_WAIT_FOR_PLAYER_ACTION | WIRED | - | The seat-attributed wait banner: `CoopBattleUi::tick()` + `waitBannerText()`, fed by `CoopArbiter::busyOwnerSeat()`. Shown when the seat blocking this machine is NOT this machine's own (suppressed when the running chain is your own action) and the seat can be NAMED; otherwise the generic `STR_COOP_DENY_BUSY` row is used, so an empty `{0}` can never render. |
| STR_COOP_END_TURN_TALLY | WIRED | - | Painted onto `_txtCoopEndTurn` via `BattlescapeState::setCoopEndTurnText()`, fed by `src/CoopMod/CoopEndTurn.h`'s readiness-tally engine: `tr("STR_COOP_END_TURN_TALLY").arg(count).arg(needed)` renders exactly `"END TURN {0}/{1}"` (e.g. count 1 of needed 2 -> `"END TURN 1/2"`), hidden (empty string) whenever this machine's own tally count is 0. |
| STR_COOP_DESYNC_REPORT_SAVED | WIRED | - | The body of `CoopDesyncNoticeState` (CoopState.cpp), raised on each machine after the automatic desync repair by `coopPushDesyncNotice()` (connectionTCP.cpp). The value reads "CO-OP DESYNC REPAIRED ... repaired automatically ..." (older versions said "CO-OP DESYNC DETECTED ..."); {0} = this machine's report zip path, wrapped at 44 columns. |
| STR_COOP_DESYNC_OPEN_FOLDER | WIRED | - | `CoopDesyncNoticeState`'s OPEN FOLDER button (opens the desync-reports folder). |
| STR_COOP_DESYNC_REPORT_GITHUB | WIRED | - | `CoopDesyncNoticeState`'s REPORT ON GITHUB button (a prefilled new-issue page; nothing is uploaded). |
| STR_COOP_DESYNC_HEADLINE_ACTION | WIRED | - | The notice's headline, `{0}` bucket, `{1}` seq, `{2}` ev kind of the desync (connectionTCP.cpp `coopPushDesyncNotice()`). `STR_COOP_DESYNC_HEADLINE_TERM` stays an accounted ORPHAN (the desync check always knows bucket / seq / kind). |
| STR_COOP_DESYNC_HEADLINE_TERM | ORPHAN | reserved | ACCOUNTED PLACEHOLDER: the attribution headline for the inert sync-check variant. No code shows it; the `.yml` value stays. |
| STR_COOP_CRASH_REPORT_PROMPT | WIRED | - | The body of `CoopCrashPromptState` (CoopState.cpp), pushed over the main menu at a fresh launch by `SharedEcon::maybeReportPreviousCrash()` (MainMenuState.cpp `GoToMainMenuState::init`) when the previous run left a crash marker or an unseen crash dump. |
| STR_COOP_CRASH_REPORT_HEADLINE | WIRED | - | The headline of the crash prompt and of its BUNDLE result notice (`CoopDesyncNoticeState`). |
| STR_COOP_CRASH_REPORT_BUNDLE | WIRED | - | The crash prompt's BUNDLE button (zips the dump, the logs and a system-info json into the user folder's `crash-reports/`). |
| STR_COOP_CRASH_REPORT_NOT_NOW | WIRED | - | The crash prompt's NOT NOW button (nothing is written; the next launch asks again). |
| STR_COOP_CRASH_REPORT_NEVER | WIRED | - | The crash prompt's NEVER button (this crash is never offered again; no zip). |
| STR_COOP_CRASH_REPORT_SAVED | WIRED | - | The body of the BUNDLE result notice (`CoopDesyncNoticeState`, raised by `SharedEcon` `emitCrashBundle()`); {0} = the crash zip's path, wrapped at 44 columns. |
| STR_COOP_ORDER_SENT | WIRED | - | The "order sent" IN-FLIGHT indicator: `CoopBattleUi::showOrderSent()`, raised by `CoopArbiter::sendClientIntent()` the moment the `bt_intent` envelope ships and cleared when the round trip ends (an applied `bt_action_end`, or replaced by a deny/pending/timeout). Without it the window between the click and the host's answer shows NOTHING. Its own key because it says something different from `STR_COOP_DENY_BUSY`: *your* order is in flight, not *the host* is busy. |
| STR_COOP_DENY_BUSY | WIRED | - | Deny table, `kReasonStrTable` (connectionTCP.cpp). Also the fallback wording of the wait banner when the blocking seat cannot be named. |
| STR_COOP_DENY_PATH_CHANGED | WIRED | - | Deny table, `kReasonStrTable` (connectionTCP.cpp). |
| STR_COOP_DENY_COST_CHANGED | WIRED | - | Deny table, `kReasonStrTable` (connectionTCP.cpp). |
| STR_COOP_DENY_TARGET_MOVED | WIRED | - | Deny table, `kReasonStrTable` (connectionTCP.cpp). |
| STR_COOP_DENY_TARGET_DEAD | WIRED | - | Deny table, `kReasonStrTable` (connectionTCP.cpp). |
| STR_COOP_DENY_WEAPON_MISSING | WIRED | - | Deny table, `kReasonStrTable` (connectionTCP.cpp). |
| STR_COOP_DENY_ITEM_MISSING | WIRED | - | The `inv_move` admission deny `item_missing`, `kReasonStrTable` row - the placed item is no longer the actor's own or loose on its tile (a partner's explosion removed it, another unit took it). Shown on the banner and on the inventory's own message line (`CoopBattleUi::inventoryLineText()`). |
| STR_COOP_DENY_NOT_YOUR_UNIT | WIRED | - | Deny table, `kReasonStrTable` (connectionTCP.cpp). |
| STR_COOP_DENY_TURN_OVER | WIRED | - | Deny table, `kReasonStrTable` (connectionTCP.cpp). Keeps its own text. |
| STR_COOP_DENY_NOT_YOUR_GO | WIRED | - | LOCAL-only refusal reason (never a wire deny) - `kReasonStrTable` row (connectionTCP.cpp), rendered with the baton holder's seat name (`showDeny`'s templated arm) via `coopRefuseIfNotMayCommand()`/`BattlescapeState::btnKneelClick` and the two map refusers (`coopBlockLocalExecution`/`coopBlockWalkArm`). |
| STR_COOP_DENY_CANNOT_USE | WIRED | - | The combat admission deny `cannot_use`, `kReasonStrTable` row. The host denies it when `SavedBattleGame::canUseWeapon()` refuses with no message (AI delay, psi, mana) or the weapon has no configuration for the ordered action; every other combat deny reuses vanilla's own key, so this is the one reason vanilla has no text for. |
| STR_COOP_WAIT_TURN | WIRED | - | The persistent off-turn banner, DISTINCT from the refusal above: `waitBannerText()`'s first branch (connectionTCP.cpp), painted onto `_txtCoopWait` via `CoopBattleUi::tick()`'s per-frame driver whenever `turnMode==traditional` and `activeSeat != localSeat`. |
| STR_COOP_CANCEL_ENEMY_SPOTTED | WIRED | - | Cancel table (connectionTCP.cpp). Reused by the walk halt presenter for `reason:"spot"`. |
| STR_COOP_CANCEL_UNIT_UNDER_FIRE | WIRED | - | Cancel table (connectionTCP.cpp). Reused by the walk halt presenter for `reason:"reaction"`. |
| STR_COOP_CANCEL_UNIT_DOWN | WIRED | - | Cancel table (connectionTCP.cpp). Reused by the walk halt presenter for `reason:"unit_down"`. |
| STR_COOP_CANCEL_NEW_CONTACT | WIRED | - | Cancel table (connectionTCP.cpp). |
| STR_COOP_CANCEL_EVENT | WIRED | - | Unknown-cause fallback, "Order cancelled - {0}" (connectionTCP.cpp). The walk halt presenter never reuses this shape: a halted walk is not a cancelled order and must never render a raw wire enum in a `{0}` slot. |
| STR_COOP_HALT_PATH_BLOCKED | WIRED | - | The `blocked` row of the WALK HALT presenter, `CoopBattleUi::showWalkHalt()`, raised on the CLIENT apply path when a `bt_action_end` carrying `halted:true` + `reason:"blocked"` resolves an action THIS client ordered. The halt enum is DISTINCT from the deny enum, and its table has NO `{0}` catch-all - an unknown reason shows nothing and logs. Of the eight reasons this is the ONLY coop key: `spot`/`reaction`/`unit_down` reuse the three `_CANCEL_` rows above, `no_tu`/`no_energy` reuse VANILLA's own `STR_NOT_ENOUGH_TIME_UNITS`/`STR_NOT_ENOUGH_ENERGY` (the exact strings vanilla writes to `_action.result` at UnitWalkBState's two guards), and `prox` (`STR_COOP_HALT_PROXIMITY`) / `fall` (`STR_COOP_HALT_FELL`) are reserved and not in the `.yml` files because the walk code cannot produce either - adding them now would create orphans. WORDING: a halted walk is NOT "cancelled" (the unit moved), so it reads "Move stopped - path blocked", never "Order cancelled - ...". |
| STR_COOP_DESYNC_HALTED | WIRED | - | Sticky desync banner (`CoopBattleUi::showDesyncHalted()` in connectionTCP.cpp, CoopBattleUi.h), "Desync detected - battle halted"; shown from the desync until the automatic repair replaces the battle, and kept by a held or failed repair. |
| STR_COOP_EQUIP_FROZEN | WIRED | - | The pre-battle equip FREEZE notice, raised through the `_txtCoopWait` presenter by `CoopBattleUi::showEquipFrozen()` - on the HOST from `CoopHandshake::freezePreBattleEquip()` (the skipped `InventoryState` push in `BriefingState::btnOkClick`), only on a multi-stage mission's NEXT-STAGE briefing: a fresh co-op battle equips on the pre-battle equip screen. Unusual for this table: it explains a screen that was SKIPPED, not a button that was refused, so it is raised at the skip. |
| STR_COOP_WAITING_FOR_JOIN | WIRED | - | Host input freeze banner. Raised by `CoopBattleUi::freezeBattleInputUntilActive()` (called from the top of `BattlescapeState::handle`) each time it refuses a HOST input while the battle handshake has not yet reached phase Active. The coop blob snapshot and the `battle_offer` send happen AFTER `SavedBattleGame::startFirstTurn()` (`CoopHandshake::emitPreparedOffer()`), so the host enters `BattlescapeState` before the client holds the blob. Notice class, never Sticky (would block every later banner for the rest of the battle). Like `STR_COOP_EQUIP_FROZEN` it explains an absence (no client has joined the handshake yet), not a refused press. |
| STR_COOP_WAITING_FOR_EQUIP | WIRED | - | Shown on the pre-battle equip screen's own message line (`Inventory::showWarning`) while THIS seat is ready and another seat that has something to equip is not; {0} = seatDisplayName() of the lowest such seat. Kept steady by the equip pump. |
| STR_COOP_ABORT_HOST_ONLY | INERT | - | Retired: either player's ABORT opens vanilla's `AbortMissionState` and its OK asks the unanimous abort vote (`coopAbortVoteRequest()`), so `Control::Abort` and its `controlStrKey()` row do not exist and nothing in `src/` references this key. The `.yml` value STAYS (both files). |
| STR_COOP_ZERO_TU_HOST_ONLY | WIRED | - | `BattlescapeState::btnZeroTUsClick` -> `BattleUnit::clearTimeUnits()`, a local state mint straight into the `unitsStats` bucket. |
| STR_COOP_REACTIONS_HOST_ONLY | INERT | - | Retired on the client: the client's hand right-click sends a `reaction_hands` intent the host runs with vanilla's own toggle (`coopInterceptReactionHands()`), so the client never reaches this string. `Control::HandReaction` stays for its HOST ownership term, which shows `STR_COOP_DENY_NOT_YOUR_UNIT`; `controlStrKey()` still maps the value to this key, but only the client-side authority term ever presented it. The `.yml` value STAYS (both files). The toggled fields (`preferredHandForReactions`, `reactionsDisabledFor{Left,Right}Hand`) are serialized (BattleUnit.cpp) and are NOT on `saveBlobExcludedUnitKey`'s list, so a local client toggle diverges saveBlob immediately. |
| STR_COOP_LEVEL_CHANGE_HOST_ONLY | WIRED | - | `BattlescapeState::btnUnitUpClick` / `btnUnitDownClick` -> `BattlescapeGame::moveUpDown()`, which pushes a `UnitWalkBState` - a LOCAL walk on a client, bypassing every coop gate. Gated via `CoopBattleUi::refuseControl(Control::LevelChange)` on the two buttons; the host's own press routes through `coopInterceptWalkConfirm()` in `moveUpDown()`, the same walk-emit path used elsewhere. |
| STR_COOP_SPECTATOR_MODE | WIRED | - | The battle-ENTRY spectator notice, raised by `CoopBattleUi::showSpectatorMode()` from `CoopHandshake::selectOwnUnitAtEntry()` when this machine's seat commands no unit at all, so the entry auto-select had nothing to select. A REAL path, not defensive framing: a plain classic "NEW BATTLE > COOP" skirmish never calls `Soldier::setCoop()`, so without the harness's `newbattle_seat_soldier` test command the joining client owns ZERO battle units - which is exactly the fixture `test_input_gating.py`'s spectator scenario drives. Like `STR_COOP_EQUIP_FROZEN` it explains an absence rather than a refused press, and it is an entry notice, not sticky. |
| STR_COOP_LOCAL_LOAD_BLOCKED | WIRED | - | Two sites: the battlescape quick-load hotkey (`BattlescapeState::handle`, through the `localLoadsAllowed()` wrapper) and `LoadGameState::init`'s own chokepoint. SESSION-scoped, not client-only: `connectionTCP::localLoadsAllowed()` is false for the HOST too while a session is live. Presenter no-ops with no live battle, so a geoscape-side local load stays log-only - stated limit. |
| STR_COOP_MISSION_HOST_CRAFT_ONLY | WIRED | client-craft joint battles in SEPARATE | Shown only on a SEPARATE co-op campaign's CLIENT: when its own craft reaches a landable target (GeoscapeState arrival -> coopRefuseSeparateClientLanding(); the craft returns to base) or when it confirms Cydonia from its own craft (ConfirmCydoniaState::btnYesClick -> coopRefuseSeparateClientCydonia()). Presenter: vanilla CraftErrorState. Never shown on the host, in SHARED, PvP, skirmish or single player. A later change that lets a SEPARATE client's own craft start a joint battle deletes the key and this row. |
| STR_COOP_CHAT_SYSTEM | WIRED | - | The player column of a LOCAL system chat line (`ChatMenu::addSystemMessage`, composed by `coopSyncedChat()` in connectionTCP.cpp on every machine, never sent on the wire), distinct from typed chat. Today its one user is the synced-option change line. |
| STR_COOP_SYNCED_OPTION_CHANGED | WIRED | - | The synced game option change line, posted on every machine when the host applies a change: {0} = the requester's player name, {1} = the option's own Advanced-screen description (`tr(description)`), {2} = `STR_YES` / `STR_NO` or the number. Host at apply, client at `synced_option_set`; never at a join or a battle_offer re-assert. |
| STR_COOP_SYNCED_OPTION | WIRED | - | The `[Synced] ` prefix on each synced option's row name in the Advanced options screen while a co-op session is active: {0} = the option's own description (`tr(description)`). Applied by `CoopSyncedOptions::rowName()` in connectionTCP.cpp (OptionsAdvancedState::addSettings); never sent on the wire. |
| STR_COOP_ALSO_ON_SCREEN | WIRED | - | The presence label on a SHARED Sell / Transfer / Alien Containment screen while another player has the same screen (same selection key) open: {0} = the other players' roster names. Drawn by SharedEcon::SelectionBinder; never sent on the wire. |
| STR_COOP_CAMPAIGN_NEEDS_XCOM_PLAYER | WIRED | - | The text of the small dialog a NEW co-op campaign lobby opens when a team pick would put both players on the Alien team (no PvE2 campaigns): LobbyMenu::setPlayerTeam refuses the pick and pushes CampaignTeamRefusedState (file-local, LobbyMenu.cpp), one OK button that closes it; the row keeps its team and nothing is sent. Never shown in a Custom Battle lobby (PvE2 stays a Custom Battle mode), in a resume lobby or in single player. |
| STR_COOP_EQUIP_OWNER | WIRED | - | The pre-battle equip screen's owner line over a partner's soldier (`coopEquipApplyViewLook()`), the same "Owner: <name>" line the released game shows in `InventoryState`. |
| STR_COOP_MISSION_BELONGS_TO_PLAYER | WIRED | - | Separate campaign: the refusal shown when a player sends a craft to the partner's mission (`MissionDetectedState`, `MultipleTargetsState`, `UfoDetectedState`). |
| STR_COOP_MISSION_OWNER | WIRED | - | Separate campaign: the "Owner: <name>" line on the UFO, mission and alien base detection windows (`UfoDetectedState`, `MissionDetectedState`, `AlienBaseState`). |
| STR_COOP_SHARED | WIRED | - | Separate campaign: the owner name shown by STR_COOP_MISSION_OWNER for a target both players share. |
| STR_COOP_NOT_YOUR_SOLDIER | WIRED | - | Separate campaign command refusal (`SharedEcon` soldier commands): the soldier belongs to the partner. Distinct from the battle deny STR_COOP_DENY_NOT_YOUR_UNIT, which answers a battle order. |
| STR_COOP_ACTION_REFUSED | WIRED | - | Separate campaign command refusal (`SharedEcon`) for a command aimed at the partner's base that the base owner rules do not allow. Battle orders never use it (distinct deny rows). |

## Rules for new keys

- Every refusal gets a reason-specific key. A generic key such as "Action
  refused" is never added: distinct refusals are never collapsed into one
  message.
- Never add a second key for a sentence a live key already says (both
  ownership refusals reuse `STR_COOP_DENY_NOT_YOUR_UNIT`; busy waits reuse
  `STR_COOP_DENY_BUSY`). Two keys for one sentence let a translator make the
  wire deny and the local refusal disagree about the same fact.

## PLANNED KEYS

**INFORMATIONAL ONLY - these are NOT whitelist entries and are NOT in the
`.yml` files yet.** The change that adds a key moves it into the WHITELIST
table above, in the same commit.

| KEY (planned, backticked on purpose - see the parse contract) | NOTE |
|---|---|
| `STR_COOP_HALT_PROXIMITY` | halt `reason:"prox"`. Not producible by the current walk code. |
| `STR_COOP_HALT_FELL` | halt `reason:"fall"`. Not producible by the current walk code. |

`no_tu` and `no_energy` deliberately add NOTHING: the halt presenter reuses
vanilla `STR_NOT_ENOUGH_TIME_UNITS` / `STR_NOT_ENOUGH_ENERGY`. Those are not
`STR_COOP_*` keys and never enter this table.

## HOW TO APPEND A ROW

In the SAME commit that adds, wires, re-words or retires the key:

1. Add or edit the key in **both** `bin/common/Language/en-US.yml` and
   `bin/common/Language/en-GB.yml`.
2. Add **one** row to the WHITELIST table above (or edit the existing row -
   never add a second row for a key that already has one). Keep the column
   order `| KEY | STATE | PENDING | DISPOSITION |`.
3. If you moved a key out of PLANNED KEYS, delete its planned row.
4. Set `STATE` truthfully: `WIRED` once `src/` references it, `INERT` if the
   change deliberately left it present-but-unreferenced, `ORPHAN` otherwise.
5. Copy `bin/common` + `bin/standard` into `bin/x64/Release/` (robocopy)
   before running the harness, and assert **exact text**, never non-emptiness.
