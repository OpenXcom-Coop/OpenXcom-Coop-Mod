#pragma once
/*
 * Copyright 2010-2016 OpenXcom Developers.
 * Copyright 2023-2026 XComCoopTeam (https://www.moddb.com/mods/openxcom-coop-mod)
 *
 * This file is part of OpenXcom.
 *
 * OpenXcom is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * OpenXcom is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with OpenXcom.  If not, see <http://www.gnu.org/licenses/>.
 */

namespace OpenXcom
{

class BattleUnit;
class Game;
class SavedBattleGame;

/**
 * R2-P6 (rewrite spike, SPIKE-RUNBOOK.md sec 2.6, ADDENDUM 2026-08-31 sec
 * 1.3(f)): the single presenter every admission-model message (deny reason,
 * auto-cancel cause, pending state) routes through. Backs the _txtCoopWait
 * banner re-added to BattlescapeState.h/.cpp this same packet - the
 * persistent banner in the map strip above the toolbar, deliberately off the
 * fading vanilla _warning surface (never touched by this presenter).
 *
 * ONE enum->STR table (defined in the .cpp body) maps every sec 2.6 deny
 * reason (wire enum, sec 2.2) and every ADDENDUM 1.3(d) auto-cancel cause to
 * its STR_COOP_DENY_ (or STR_COOP_CANCEL_) key; STR_COOP_CANCEL_EVENT is the
 * {0}-templated fallback for a cause/kind not in the table, applied directly
 * by showCancel() below rather than looked up.
 *
 * Bodies live in connectionTCP.cpp, next to BattleAuthority/CoopArbiter/
 * CoopIdMaps/CoopPump/CoopEmit - the established home for this scaffolding
 * (R2-P1..P5). Reaches the active battle's BattlescapeState via
 * connectionTCP::getStaticBattle()->getBattleState() (same pattern
 * CoopArbiter::onIntent() already uses); no-ops if no battle is live.
 *
 * Called only from the pump/UI thread (main thread) - same thread
 * updateCoopTask() and its callers (CoopPump::drainApplyQueue(),
 * CoopArbiter::onIntent()) already run on - so touching the widget directly
 * is safe; this presenter must never be called from the socket thread.
 *
 * Wiring history: R2-P6 shipped this API with no live caller; R3-P1 wired
 * showDeny() at the client-inbound bt_deny seam (connectionTCP.cpp's
 * onTCPMessage -> CoopArbiter::onDeny); R2-P9 wired showDesyncHalted();
 * R2-P7 wired showPending()/clearPending() (the busy-held pending state and
 * its right-click/ESC cancel control) and showCancel() (the four
 * Options::coopCancelOn* info-cancel toggles). Every entry point now has a
 * live caller.
 */
namespace CoopBattleUi
{

/**
 * W1-P5 (WAVE1-RUNBOOK.md ruling D8 = WV-D14): the LOCAL battlescape controls
 * that a co-op CLIENT must never run. Each control is its OWN enum value
 * because ADDENDUM 2026-08-31 SS1.3(e) forbids collapsing distinct refusals
 * into one generic message ("Action refused" is exactly the shape it names) -
 * every value below has its own STR_COOP_* string in the SS2.6 table.
 *
 * The four battlescape controls are the ungated-client set evidence F2
 * inventoried; QuickLoad is evidence F1's deleted gate.
 */
enum class Control
{
	/// BattlescapeState::btnAbortClick -> AbortMissionState. Aborting is a
	/// BATTLE-WIDE, host-authoritative decision (it ends in setAborted() +
	/// finishBattle()); the multiplayer VOTE that used to arbitrate it is r4
	/// T3, so until then only the simulating machine may open the dialog.
	Abort,
	/// BattlescapeState::btnInventoryClick -> the MID-battle InventoryState.
	/// Every move inside it writes the hashed `items` bucket with nothing on
	/// the wire (`inventory_move` is not in wave 1, WV-D34). Distinct from
	/// W1-P4's PRE-battle freeze, which is a skipped push, not a refusal.
	Inventory,
	/// BattlescapeState::btnZeroTUsClick -> BattleUnit::clearTimeUnits(): a
	/// LOCAL STATE MINT straight into the `unitsStats` bucket.
	ZeroTu,
	/// The right-click branch of BattlescapeState::btn{Left,Right}HandItemClick
	/// -> BattleUnit::toggle{Left,Right}HandForReactions(). Writes
	/// `preferredHandForReactions` / `reactionsDisabledFor{Left,Right}Hand`,
	/// which are serialized (BattleUnit.cpp:791-796) and are NOT on
	/// saveBlobExcludedUnitKey's list (SharedEcon.cpp:3992-4014) - so a client
	/// toggle diverges the saveBlob bucket immediately. These are the
	/// "open item 9" fields W1-P15's audit gives a bucket home to.
	HandReaction,
	/// The battlescape quick-load hotkey (BattlescapeState::handle) and
	/// LoadGameState's own chokepoint. NOT battle-scoped and NOT
	/// client-only: connectionTCP::localLoadsAllowed() forbids a local load
	/// for EVERY machine in a live co-op session (PRD-08 C7), host included -
	/// loading mid-session forks the served world silently.
	QuickLoad
};

/// W1-P5: the ONE gate every hard-gated control calls. Returns TRUE when @a c
/// must be REFUSED on this machine right now, having already put the refusal
/// on screen (SS2.6's _txtCoopWait presenter); FALSE means "carry on, vanilla".
/// The thin vanilla hook is therefore a single unconditional call:
/// `if (CoopBattleUi::refuseControl(Control::ZeroTu, unit, save)) return;`
///
/// PREDICATE, and why it is not `coopMayCommand()` alone. The packet's goal is
/// "no CLIENT control can mint local state or push an unsynced modal", and
/// `coopMayCommand(u, s)` is TRUE for a client acting on its OWN unit during
/// its OWN side - which is precisely when a player presses these buttons. The
/// gate is therefore a conjunction of two reason-specific terms, checked in
/// this order so each refusal names its own cause (SS1.3(e)):
///   1. `coopBattleAuthority().hostSim` - only the simulating machine may run
///      an unsynced local control at all. Failing it shows @a c's own "Only
///      the host can ..." string. The two-term shape is the shipped house
///      pattern: `BattlescapeState::btnKneelClick` already runs
///      `coopMayCommand(bu, _save)` and then `isCoopBattle() && !hostSim`
///      (:1244 / :1254), and the R5-P2 END TURN client gate is the same
///      authority term (:1530). Kneel's second term SENDS an intent; these
///      five controls have no wire verb, so theirs REFUSES.
///   2. `coopMayCommand(u, s)` - when a UNIT is in scope, the pressing seat
///      must also command it. Failing it shows SS2.6's existing
///      STR_COOP_DENY_NOT_YOUR_UNIT (same reason, same words as the wire deny;
///      no duplicate key is minted for it).
/// @a u may be null for the side-level controls (Abort, QuickLoad), which skip
/// term 2 entirely.
///
/// SELF-GUARDED, exactly like isCoopBattle()/coopMayCommand(): outside an
/// ACTIVE co-op battle every battlescape control returns false and vanilla is
/// byte-identical (SP included). QuickLoad is the deliberate exception - it is
/// scoped to the co-op SESSION, not to the battle, because that is what
/// connectionTCP::localLoadsAllowed() answers.
bool refuseControl(Control c, const BattleUnit* u, const SavedBattleGame* s);

/// W1-P5: the presenter half of refuseControl(), for the ONE site that has
/// already decided the refusal for itself - LoadGameState::init's local-load
/// chokepoint, whose refusal was log-only before this packet (evidence F1).
/// No predicate, no return value: just puts @a c's string on the banner.
/// No-op outside an active co-op battle (no live BattlescapeState to reach),
/// which is why a geoscape-side local load stays log-only.
void showControlRefused(Control c);

/// W1-P5 (D8's chat-open `allowButtons` guard - legacy parity, F-4): is the
/// co-op chat overlay currently capturing the keyboard on THIS machine?
///
/// Game::run() routes key events to ChatMenu::handleEvent() while the chat is
/// active but STILL calls `_states.back()->handle(&action)` afterwards
/// (Game.cpp:325-423), so every keystroke a player types into chat also
/// reaches BattlescapeState as a hotkey. Legacy closed that by returning false
/// from allowButtons() while the chat was up
/// (`1e0f9276f:BattlescapeState.cpp:6132-6141`); this is that guard, as one
/// call. Takes the Game rather than reaching for connectionTCP's private
/// _staticGame, and is false whenever no chat menu exists (SP, and any
/// non-co-op session).
bool chatIsOpen(Game* g);

/// Client: present a host bt_deny{reason} (sec 2.2's 8-value machine enum -
/// busy|path_changed|cost_changed|target_moved|target_dead|weapon_missing|
/// not_your_unit|turn_over). Looks reason up in the one enum->STR table,
/// sets the _txtCoopWait banner text (translated) and makes it visible. A
/// reason not in the table (a future/unknown wire value) is a no-op - never
/// guesses a string. No-op outside an active coop battle (no live
/// BattlescapeState to reach).
void showDeny(const char* reason);

/// Shown while a busy-denied intent is HELD pending auto-resubmit (R2-P7,
/// ADDENDUM 1.3(d)). WIRED as of R2-P7: CoopArbiter::onDeny() calls this on
/// reason=="busy" instead of dropping the intent. @a context is still
/// unused for presentation - the banner text is sec 2.6's own busy row
/// (STR_COOP_DENY_BUSY, "Waiting - another action is in progress"), which is
/// exactly the right message for the held state and keeps R2-P7's "never
/// generic, never a new ad-hoc string" rule; @a context is retained as the
/// call-site's self-documentation of WHY the intent is pending.
void showPending(const char* /*context*/);

/// R2-P7: clears whatever showPending() set (hides the banner). WIRED as of
/// R2-P7 by CoopArbiter::cancelPendingIntent() (the user's right-click/ESC
/// cancel control) and by an auto-resubmit that could not be sent. A
/// POLICY cancel does not come through here - it goes to showCancel() below,
/// so the player is told which event killed the order. No-op outside an
/// active coop battle.
void clearPending();

/// Client: present an auto-cancel (ADDENDUM 1.3(d)'s four toggles - enemy
/// spotted, own-unit hit, visibility gain, or the broad any-partner-action
/// toggle). @a cause is one of the table's known causes
/// (enemy_spotted|unit_under_fire|unit_down|new_contact) and gets its own
/// STR_COOP_CANCEL_* string; any other/unknown @a cause falls back to the
/// {0}-templated STR_COOP_CANCEL_EVENT with @a evKind substituted for {0}
/// (sec 2.6's "(cancel) unknown kind" row) - messages must always stay
/// reason-specific (ADDENDUM 1.3(e)), never a generic "situation changed".
/// No-op outside an active coop battle.
void showCancel(const char* cause, const char* evKind);

/// W1-P9 (WAVE1-RUNBOOK.md SS2.W2 / WV-D53 / IR2-11): the WALK HALT presenter -
/// "your unit MOVED and then stopped", which is a different statement from
/// "your order was refused" and gets its own table.
///
/// @a reason is one of SS2.W2's frozen halt enum values
/// (spot|reaction|blocked|no_tu|no_energy|prox|fall|unit_down), which is a
/// DISTINCT enum from SS2.2's deny reasons - one answers "why did the executed
/// action stop", the other "why was your order refused". Three binding rules
/// come with it:
///   * ONE KEY PER REASON, and NO `{0}` catch-all. REV B's "everything else ->
///     STR_COOP_CANCEL_EVENT with the reason as {0}" is DEAD (IR2-11): it would
///     render an untranslated protocol token to the player and it violates
///     ADDENDUM SS1.3(e)'s reason-specific rule. An UNKNOWN reason therefore
///     shows NOTHING and logs, exactly like showDeny()'s unknown-reason arm -
///     never a guess.
///   * `no_tu` and `no_energy` REUSE VANILLA's own STR_NOT_ENOUGH_TIME_UNITS /
///     STR_NOT_ENOUGH_ENERGY - the exact strings vanilla writes to
///     `_action.result` at the two UnitWalkBState guards - so the client reads
///     what a solo player reads. `spot`/`reaction`/`unit_down` reuse the three
///     live SS2.6 `_CANCEL_` rows as-is (renaming shipped keys is out of scope).
///     Only `blocked` needs a new key, STR_COOP_HALT_PATH_BLOCKED, minted here.
///     `prox` (W1-P11) and `fall` (walk-FULL) are RESERVED and deliberately not
///     minted by this packet - walk-core cannot produce either.
///   * A HALTED WALK IS NOT "CANCELLED". The unit moved and the emitted step evs
///     are truth (SS2.W2 rule 5), so the new key is worded as
///     stop-after-partial-execution, never as "Order cancelled - ...", which
///     SS2.6 reserves for orders that never executed.
/// Terminal banner class (it answers something the player did), so it
/// dwell-clears like any other answer. No-op outside an active coop battle.
///
/// SHOWN ONLY ON THE ORDERING SEAT (SS2.W2, same rule as the deny presenter):
/// the sole caller is the CLIENT apply path, and only for an actionId this
/// client itself owns. The observing machine ANIMATES the halt (W1-P12); it
/// never prints another player's message. A HOST-origin walk keeps vanilla's own
/// surface - BattlescapeGame::popState() already shows `_action.result` for the
/// TU and energy halts, and vanilla shows nothing at all for a blocked one.
void showWalkHalt(const char* reason);

/// R2-P9 (SPIKE-RUNBOOK.md SS2.8 mismatch-behavior note): the STICKY desync
/// banner - "desync detected - battle halted (rejoin arrives in a later
/// build)" (STR_COOP_DESYNC_HALTED). Called once, from CoopHashCheck::verify
/// (BattlePump.h) on the first hash mismatch, AFTER battle input is already
/// frozen - unlike showDeny/showPending/showCancel this is never cleared by
/// clearPending() (there is nothing to auto-retry into once a battle has
/// desynced; NO partial repair, SS2.8). No-op outside an active coop battle.
void showDesyncHalted();

/// W1-P4 (WAVE1-RUNBOOK.md ruling D3 = WV-D9 + WV-D34, mechanism WV-D43): the
/// pre-battle equip freeze's player-visible refusal - STR_COOP_EQUIP_FROZEN on
/// the same _txtCoopWait surface every other coop message uses (SS2.6: never
/// vanilla _warning).
///
/// UNUSUAL TIMING, stated on purpose. Every other entry point here answers
/// something the player DID; this one explains something that did not happen -
/// the pre-battle equip screen was never pushed. It is therefore raised at the
/// moment of the skip, on both machines: on the HOST from
/// CoopHandshake::freezePreBattleEquip() (called from BriefingState::btnOkClick,
/// where the InventoryState push is skipped), and on the CLIENT from the battle
/// entry in CoopHandshake::onBlobChunkAppended(), whose read-only infoOnly
/// briefing never reaches that push at all. Not sticky in the
/// showDesyncHalted() sense: the first deny/pending/cancel replaces it, and
/// clearPending() clears it, which is correct - it is an entry notice, not a
/// halt.
///
/// No-op outside an active coop battle (no live BattlescapeState to reach).
void showEquipFrozen();

/// W1-P6 (WAVE1-RUNBOOK.md ruling D6 = WV-D12): the SEAT FILTER on
/// BattlescapeGame::primaryAction's click-to-select branch. Returns TRUE when
/// the click must be REFUSED, having already put the refusal on screen.
/// The thin vanilla hook is therefore a single unconditional call:
/// `if (CoopBattleUi::refuseSelectUnitClick(unit)) return;`
///
/// Vanilla gates that branch on `unit->getFaction() == _save->getSide()` and
/// nothing else, so without this a co-op seat could click-select a soldier it
/// does not command - the exact thing D6 forbids ("a seat can NEVER select,
/// preview, or command units it doesn't own"). The predicate is
/// coopMaySelectUnit() (BattleAuthority.h), the SAME one the selection cycle
/// uses, deliberately NOT coopMayCommand(): the branch has already restricted
/// the candidate to the currently active side, and cycling/selecting among
/// already-active-side candidates must not additionally demand mySideActive().
///
/// The message is SS2.6's EXISTING not_your_unit row
/// (STR_COOP_DENY_NOT_YOUR_UNIT, "Not one of your soldiers") - the same
/// ownership reason the wire deny carries and the wording D6's own acceptance
/// quotes; no duplicate key is minted for it, exactly as W1-P5's ownership arm
/// already reuses it. Self-guarded: false outside an active co-op battle, so
/// SP click-to-select is byte-identical.
bool refuseSelectUnitClick(const BattleUnit* target);

/// W1-P6 (ruling D6 = WV-D12): the SPECTATOR notice - this machine's seat
/// commands no unit in this battle, so battle entry could not auto-select one
/// for it (STR_COOP_SPECTATOR_MODE). Legacy raised the same notice from its own
/// client unit selector (`1e0f9276f:BattlescapeState.cpp:1627-1631`, "You are
/// in spectator mode"); this is that message, on SS2.6's presenter.
///
/// Raised once per battle by CoopHandshake::selectOwnUnitAtEntry(). It is a
/// real path, not defensive framing: a plain classic "NEW BATTLE > COOP"
/// skirmish never calls Soldier::setCoop(), so without the harness's
/// newbattle_seat_soldier lever the joining client owns ZERO battle units.
/// Like showEquipFrozen() it is an ENTRY notice, not sticky - the first
/// deny/pending/cancel replaces it.
void showSpectatorMode();

// ---------------------------------------------------------------------------
// W1-P7 (WAVE1-RUNBOOK.md ruling D7 = WV-D13): order feedback.
//
// BANNER CLASSES. Every entry point above and below writes the ONE _txtCoopWait
// surface, so this packet gives each message a CLASS and one arbitration rule,
// rather than letting the newest writer always win:
//
//   Sticky   showDesyncHalted() only. Never overwritten, never auto-cleared -
//            there is nothing to retry into once a battle has desynced (SS2.8).
//   Terminal an ANSWER to something the player just did: a non-busy deny, a
//            policy cancel, an intent timeout, and every local refusal (D8's five
//            controls, D6's select refusal, SS2.W8's END TURN refusal). These now
//            AUTO-CLEAR after kCoopBannerDwellMs - see clearStaleBanner() below.
//   Sent     showOrderSent() - this machine's own order is in flight. Cleared by
//            whatever resolves the round trip (an applied bt_action_end, a deny,
//            a timeout); never dwell-cleared.
//   Wait     showPending() and the per-tick wait driver - 'another action is in
//            progress' / 'Please wait for {0}'s action to finish'. Owned by the
//            driver, which re-evaluates and clears it every tick.
//   Notice   the two ENTRY notices, showEquipFrozen() and showSpectatorMode().
//            They explain an ABSENCE rather than answering a press, are raised
//            once at battle entry, and their own doc comments above already
//            define them as 'not sticky - the first deny/pending/cancel replaces
//            it'. They are deliberately NOT dwell-cleared, so that contract (and
//            every test written against it) is unchanged by this packet.
//
// Only Sticky blocks an overwrite. The per-tick WAIT driver additionally writes
// only when the current class is Wait, Notice or nothing (a Notice's own
// contract is that the first deny/pending/cancel replaces it, and a live waiting
// message is exactly that), and it CLEARS only what it itself wrote - so neither
// a deny the player has not read yet, nor their own 'order sent' indicator, nor
// an entry notice is stomped by an idle driver.
// ---------------------------------------------------------------------------

/// CLIENT (WV-D13 item 2): the 'order sent' IN-FLIGHT indicator, raised by
/// CoopArbiter::sendClientIntent() the moment the bt_intent envelope goes out
/// and cleared when the round trip ends (bt_action_end applied, or replaced by a
/// deny/pending/timeout). STR_COOP_ORDER_SENT. Before this packet the window
/// between the click and the host's answer showed NOTHING at all, which is the
/// gap D7 opens with ("the player always knows what the network did with the
/// click"). No-op outside an active coop battle.
void showOrderSent();

/// CLIENT (WV-D13 item 3 / WV-D24): the intent TIMEOUT banner
/// (STR_COOP_ACTION_TIMEOUT, "No answer from the host - action dropped"). Raised
/// by CoopArbiter::tickIntentTimeout() at the moment it releases the IR-2 slot.
/// Terminal class, so it dwell-clears like any other answer.
void showIntentTimeout();

/// CLIENT (SS2.W8 / WV-D23 / ruling D-10): the LOCAL end-turn refusal,
/// STR_COOP_TURN_OVER = "Only the host can end the turn".
///
/// Its own presenter entry ON PURPOSE. BattlescapeState::btnEndTurnClick used to
/// raise this through showDeny("turn_over"), i.e. through the SS2.6 WIRE deny
/// table, and therefore told the player "The turn has already ended" - which is
/// factually wrong at the only place that branch is reachable. allowButtons()
/// requires `_save->getSide() == FACTION_PLAYER`, so an off-turn press never
/// reaches the handler at all; the state this message actually covers, for its
/// whole lifetime, is a co-op CLIENT pressing END TURN during ITS OWN side before
/// the readiness wire exists. SS2.W8 rules the fix client-side only: no
/// `not_your_turn` reason is added to the SS2.2 wire enum, and the SS2.6
/// STR_COOP_DENY_TURN_OVER row keeps its own (correct, for a wire deny) text.
///
/// LIFETIME: W1-P13 RETIRES this entry - once bt_end_turn_ready exists the client
/// press ARMS instead of refusing, and the key goes INERT (RB-D3 precedent).
void showEndTurnHostOnly();

/// The per-tick driver: ONE unconditional guarded call from the RB-D5 pump point
/// (connectionTCP::updateCoopTask, beside CoopReveal::flushQuiescent()). Three
/// jobs, all self-guarded and completely inert outside an active co-op battle:
///   1. CoopArbiter::tickIntentTimeout() - WV-D24's 10 s intent timeout.
///   2. the Terminal-class AUTO-CLEAR (WV-D13 item 1). Before this packet the
///      ONLY thing that ever cleared a terminal deny was the player's own next
///      successful action, so a refusal sat on the map strip indefinitely.
///      RULED RULE (this packet, the ruling leaves the shape to the builder): a
///      Terminal banner clears itself kCoopBannerDwellMs after it was raised,
///      and is of course still replaced early by the next message or cleared by
///      the player's own next successful action, exactly as before.
///   3. the seat-attributed WAIT banner (WV-D13 item 4) - the donor's
///      "Please wait for {0}'s action to finish" driver
///      (`cbff7951d:BattlescapeState.cpp:5292-5370`), re-homed from a vanilla
///      per-frame method into CoopMod and fed by CoopArbiter::busyOwnerSeat().
void tick();

/// The Terminal-class dwell, in milliseconds (rule 2 above). Long enough to read
/// a one-line banner comfortably, short enough that the map strip does not carry
/// a stale answer into the next exchange.
static const unsigned int kCoopBannerDwellMs = 6000u;

} // namespace CoopBattleUi

} // namespace OpenXcom
