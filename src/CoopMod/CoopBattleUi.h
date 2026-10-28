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

#include <string>

// forward-declared at GLOBAL scope (SDL_Surface is not an
// OpenXcom type) so this lightweight header does not need to pull in <SDL.h>
// just for a pointer parameter.
struct SDL_Surface;

// forward-declared at GLOBAL scope (the DogfightState.h /
// GeoscapeState.h precedent) so this lightweight header does not pull in
// <json/json.h> for the message probe's return type below.
namespace Json { class Value; }

namespace OpenXcom
{

class BattleUnit;
class Game;
class SavedBattleGame;
struct BattleAction;

/**
 * The single presenter every admission-model message (deny reason,
 * auto-cancel cause, pending state) routes through. Backs the _txtCoopWait
 * banner in BattlescapeState.h/.cpp - the
 * persistent banner in the map strip above the toolbar, deliberately off the
 * fading vanilla _warning surface (never touched by this presenter).
 *
 * ONE enum->STR table (defined in the .cpp body) maps every deny reason (wire
 * enum) and every auto-cancel cause to
 * its STR_COOP_DENY_ (or STR_COOP_CANCEL_) key; STR_COOP_CANCEL_EVENT is the
 * {0}-templated fallback for a cause/kind not in the table, applied directly
 * by showCancel() below rather than looked up.
 *
 * Bodies live in connectionTCP.cpp, next to BattleAuthority/CoopArbiter/
 * CoopIdMaps/CoopPump/CoopEmit - the established home for this scaffolding.
 * Reaches the active battle's BattlescapeState via
 * connectionTCP::getStaticBattle()->getBattleState() (same pattern
 * CoopArbiter::onIntent() already uses); no-ops if no battle is live.
 *
 * Called only from the pump/UI thread (main thread) - same thread
 * updateCoopTask() and its callers (CoopPump::drainApplyQueue(),
 * CoopArbiter::onIntent()) already run on - so touching the widget directly
 * is safe; this presenter must never be called from the socket thread.
 *
 * Every entry point has a live caller: showDeny() at the client-inbound bt_deny
 * seam (connectionTCP.cpp's onTCPMessage -> CoopArbiter::onDeny),
 * showDesyncHalted() (CoopHashCheck::verify), showPending()/clearPending() (the
 * busy-held pending state and its right-click/ESC cancel control) and
 * showCancel() (the four Options::coopCancelOn* info-cancel toggles).
 */
namespace CoopBattleUi
{

/**
 * the LOCAL battlescape controls
 * that a co-op CLIENT must never run. Each control is its OWN enum value
 * because distinct refusals must never collapse into one generic message
 * ("Action refused") - every value below has its own STR_COOP_* string.
 */
enum class Control
{
	// The ABORT value is RETIRED - either player opens vanilla's abort
	// dialog and its OK asks the unanimous abort vote (coopAbortVoteRequest(), CoopArbiter.h).
	// The INVENTORY value is RETIRED - every player opens the
	// inventory of the soldiers its seat commands and each placement is an
	// `inv_move` order (refuseInventoryOpen() below is the open gate).
	/// BattlescapeState::btnZeroTUsClick -> BattleUnit::clearTimeUnits(): a
	/// LOCAL STATE MINT straight into the `unitsStats` bucket.
	ZeroTu,
	/// The right-click branch of BattlescapeState::btn{Left,Right}HandItemClick
	/// -> BattleUnit::toggle{Left,Right}HandForReactions(). Writes
	/// `preferredHandForReactions` / `reactionsDisabledFor{Left,Right}Hand`,
	/// which are serialized (BattleUnit.cpp:791-796) and are NOT on
	/// saveBlobExcludedUnitKey's list (SharedEcon.cpp:3992-4014) - so a client
	/// toggle diverges the saveBlob bucket immediately.
	HandReaction,
	/// BattlescapeState::btnUnitUpClick / btnUnitDownClick ->
	/// BattlescapeGame::moveUpDown(), which pushes a UnitWalkBState - a LOCAL
	/// walk on a client, bypassing every coop gate. The client therefore
	/// REFUSES, and the host's own press goes through the normal walk emit path.
	LevelChange,
	/// The battlescape quick-load hotkey (BattlescapeState::handle) and
	/// LoadGameState's own chokepoint. NOT battle-scoped and NOT
	/// client-only: connectionTCP::localLoadsAllowed() forbids a local load
	/// for EVERY machine in a live co-op session, host included -
	/// loading mid-session forks the served world silently.
	QuickLoad
	// There are no ItemAction or Reload values: the action menu's non-targeting
	// item actions and the reload hotkey are client intents. HandReaction stays
	// for its HOST ownership term; the client sends a `reaction_hands` intent
	// instead of reaching its string.
};

/// the ONE gate every hard-gated control calls. Returns TRUE when @a c
/// must be REFUSED on this machine right now, having already put the refusal
/// on screen (the _txtCoopWait presenter); FALSE means "carry on, vanilla".
/// The thin vanilla hook is therefore a single unconditional call:
/// `if (CoopBattleUi::refuseControl(Control::ZeroTu, unit, save)) return;`
///
/// PREDICATE, and why it is not `coopMayCommand()` alone. The goal is
/// "no CLIENT control can mint local state or push an unsynced modal", and
/// `coopMayCommand(u, s)` is TRUE for a client acting on its OWN unit during
/// its OWN side - which is precisely when a player presses these buttons. The
/// gate is therefore a conjunction of two reason-specific terms, checked in
/// this order so each refusal names its own cause:
///   1. `coopBattleAuthority().hostSim` - only the simulating machine may run
///      an unsynced local control at all. Failing it shows @a c's own "Only
///      the host can ..." string. The two-term shape is the shipped house
///      pattern: `BattlescapeState::btnKneelClick` already runs
///      `coopMayCommand(bu, _save)` and then `isCoopBattle() && !hostSim`
///      (:1244 / :1254), and the END TURN client gate is the same
///      authority term (:1530). Kneel's second term SENDS an intent; these
///      five controls have no wire verb, so theirs REFUSES.
///   2. `coopMayCommand(u, s)` - when a UNIT is in scope, the pressing seat
///      must also command it. Failing it shows the existing
///      STR_COOP_DENY_NOT_YOUR_UNIT (same reason, same words as the wire deny;
///      no duplicate key is minted for it).
/// @a u may be null for the side-level controls (QuickLoad), which skip
/// term 2 entirely.
///
/// SELF-GUARDED, exactly like isCoopBattle()/coopMayCommand(): outside an
/// ACTIVE co-op battle every battlescape control returns false and vanilla is
/// byte-identical (SP included). QuickLoad is the deliberate exception - it is
/// scoped to the co-op SESSION, not to the battle, because that is what
/// connectionTCP::localLoadsAllowed() answers.
bool refuseControl(Control c, const BattleUnit* u, const SavedBattleGame* s);

/// The MID-battle inventory's
/// open gate (BattlescapeState::btnInventoryClick). TRUE = refused, the refusal
/// already on the banner. In order: not an active co-op battle -> FALSE
/// (vanilla); this seat's side is not active -> FALSE (vanilla's own
/// allowButtons() then keeps the screen closed, silently); a unit this seat
/// does not command -> STR_COOP_DENY_NOT_YOUR_UNIT, TRUE; otherwise FALSE on
/// either machine. The baton is NOT checked here: off the baton the screen
/// opens to LOOK and every placement is refused at its execution point.
bool refuseInventoryOpen(const BattleUnit* u, const SavedBattleGame* s);

/// the text
/// the co-op layer puts on the INVENTORY's own message line, which is exactly
/// what the battlescape banner (hidden under the inventory screen) would show
/// for the same answer: @a reason "busy" -> showPending()'s seat-attributed
/// wait text (STR_COOP_DENY_BUSY fallback); "timeout" ->
/// showIntentTimeout()'s STR_COOP_ACTION_TIMEOUT; any other deny reason ->
/// showDeny()'s text (not_your_go templated with the baton holder's name). A
/// SILENT reason, an unknown one, or no live battle -> "". The banner paths
/// themselves are unchanged.
std::string inventoryLineText(const char* reason);

/// the presenter half of refuseControl(), for the ONE site that has
/// already decided the refusal for itself - LoadGameState::init's local-load
/// chokepoint.
/// No predicate, no return value: just puts @a c's string on the banner.
/// No-op outside an active co-op battle (no live BattlescapeState to reach),
/// which is why a geoscape-side local load stays log-only.
void showControlRefused(Control c);

/// The chat-open `allowButtons` guard: is the
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

/// Shown while a busy-denied intent is HELD pending auto-resubmit:
/// CoopArbiter::onDeny() calls this on
/// reason=="busy" instead of dropping the intent. @a context is still
/// unused for presentation - the banner text is the busy row
/// (STR_COOP_DENY_BUSY, "Waiting - another action is in progress"), which is
/// exactly the right message for the held state and keeps the "never
/// generic, never a new ad-hoc string" rule; @a context is retained as the
/// call-site's self-documentation of WHY the intent is pending.
void showPending(const char* /*context*/);

/// Clears whatever showPending() set (hides the banner). Called by
/// CoopArbiter::cancelPendingIntent() (the user's right-click/ESC
/// cancel control) and by an auto-resubmit that could not be sent. A
/// POLICY cancel does not come through here - it goes to showCancel() below,
/// so the player is told which event killed the order. No-op outside an
/// active coop battle.
void clearPending();

/// Client: present an auto-cancel (the four toggles - enemy
/// spotted, own-unit hit, visibility gain, or the broad any-partner-action
/// toggle). @a cause is one of the table's known causes
/// (enemy_spotted|unit_under_fire|unit_down|new_contact) and gets its own
/// STR_COOP_CANCEL_* string; any other/unknown @a cause falls back to the
/// {0}-templated STR_COOP_CANCEL_EVENT with @a evKind substituted for {0}
/// (the "(cancel) unknown kind" row) - messages must always stay
/// reason-specific, never a generic "situation changed".
/// No-op outside an active coop battle.
void showCancel(const char* cause, const char* evKind);

/// The WALK HALT presenter -
/// "your unit MOVED and then stopped", which is a different statement from
/// "your order was refused" and gets its own table.
///
/// @a reason is one of the frozen halt enum values
/// (spot|reaction|blocked|no_tu|no_energy|prox|fall|unit_down), which is a
/// DISTINCT enum from the deny reasons - one answers "why did the executed
/// action stop", the other "why was your order refused". Three binding rules
/// come with it:
///   * ONE KEY PER REASON, and NO `{0}` catch-all: a STR_COOP_CANCEL_EVENT
///     fallback with the reason as {0} would render an untranslated protocol
///     token to the player and break the reason-specific rule. An UNKNOWN reason therefore
///     shows NOTHING and logs, exactly like showDeny()'s unknown-reason arm -
///     never a guess.
///   * `no_tu` and `no_energy` REUSE VANILLA's own STR_NOT_ENOUGH_TIME_UNITS /
///     STR_NOT_ENOUGH_ENERGY - the exact strings vanilla writes to
///     `_action.result` at the two UnitWalkBState guards - so the client reads
///     what a solo player reads. `spot`/`reaction`/`unit_down` reuse the three
///     live `_CANCEL_` rows as-is (shipped keys are not renamed).
///     Only `blocked` needs a new key, STR_COOP_HALT_PATH_BLOCKED, minted here.
///     `prox` and `fall` are RESERVED and deliberately have no key.
///   * A HALTED WALK IS NOT "CANCELLED". The unit moved and the emitted step evs
///     are truth, so the new key is worded as
///     stop-after-partial-execution, never as "Order cancelled - ...", which
///     is reserved for orders that never executed.
/// Terminal banner class (it answers something the player did), so it
/// dwell-clears like any other answer. No-op outside an active coop battle.
///
/// SHOWN ONLY ON THE ORDERING SEAT (same rule as the deny presenter):
/// the sole caller is the CLIENT apply path, and only for an actionId this
/// client itself owns. The observing machine ANIMATES the halt; it
/// never prints another player's message. A HOST-origin walk keeps vanilla's own
/// surface - BattlescapeGame::popState() already shows `_action.result` for the
/// TU and energy halts, and vanilla shows nothing at all for a blocked one.
void showWalkHalt(const char* reason);

/// The
/// COMBAT halt presenter - the reason a host-executed combat intent of THIS
/// client failed (bt_action_end `reason`: no_tu, no_energy, no_morale,
/// no_health, no_mana, no_stun, no_ammo_loaded, no_rounds_left, out_of_range,
/// failed_cqb, unable_to_throw_here, no_trajectory, no_line_of_fire), rendered
/// with VANILLA's own key through a table separate from the walk and deny
/// tables. Terminal class. Shown only on the ORDERING seat (the sole caller is
/// the client apply path, for an action this client owns); an unknown reason
/// shows nothing (logged). No-op outside an active co-op battle.
void showCombatHalt(const char* reason);

/// The STICKY desync
/// banner - "desync detected - battle halted (rejoin arrives in a later
/// build)" (STR_COOP_DESYNC_HALTED). Called once, from CoopHashCheck::verify
/// (BattlePump.h) on the first hash mismatch, AFTER battle input is already
/// frozen - unlike showDeny/showPending/showCancel this is never cleared by
/// clearPending() (there is nothing to auto-retry into once a battle has
/// desynced; NO partial repair). No-op outside an active coop battle.
void showDesyncHalted();

/// The
/// pre-battle equip freeze's player-visible refusal - STR_COOP_EQUIP_FROZEN on
/// the same _txtCoopWait surface every other coop message uses (never
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

/// TRUE while THIS machine is the
/// coop HOST and the battle handshake has not reached phase Active - i.e. the
/// client does not hold the blob yet. Deliberately NOT isCoopBattle() (that
/// requires phase Active, so it is false in exactly the window this guards).
/// Raises the STR_COOP_WAITING_FOR_JOIN banner (Notice class, never Sticky -
/// Sticky would block every later banner for the rest of the battle) each
/// time it refuses, so the banner cannot be aged out, and bumps
/// coopHostInputFrozenRefusals() below.
///
/// The thin vanilla hook is a single unconditional call at the top of
/// BattlescapeState::handle: `if (CoopBattleUi::freezeBattleInputUntilActive())
/// return;` - see that call site for the ONE exemption (the Options key) this
/// predicate does NOT itself carry; the exemption is the caller's job, so the
/// counter here stays a clean delivery proof for map input alone.
///
/// No-op (false) in SP, outside a coop battle, on a client, and the instant
/// phase reaches Active - so the freeze self-lifts with no explicit unfreeze
/// call anywhere.
bool freezeBattleInputUntilActive();

/// Test/introspection: how many times freezeBattleInputUntilActive() has
/// refused a host input this process. A POSITIVE delivery proof (not an
/// absence) that the freeze actually fired. Battle-scoped: reset with the rest
/// of the banner-class bookkeeping at teardown.
unsigned int coopHostInputFrozenRefusals();

/// the SEAT FILTER on
/// BattlescapeGame::primaryAction's click-to-select branch. Returns TRUE when
/// the click must be REFUSED, having already put the refusal on screen.
/// The thin vanilla hook is therefore a single unconditional call:
/// `if (CoopBattleUi::refuseSelectUnitClick(unit)) return;`
///
/// Vanilla gates that branch on `unit->getFaction() == _save->getSide()` and
/// nothing else, so without this a co-op seat could click-select a soldier it
/// does not command - and a seat must NEVER select, preview, or command units
/// it does not own. The predicate is
/// coopMaySelectUnit() (BattleAuthority.h), the SAME one the selection cycle
/// uses, deliberately NOT coopMayCommand(): the branch has already restricted
/// the candidate to the currently active side, and cycling/selecting among
/// already-active-side candidates must not additionally demand mySideActive().
///
/// The message is the EXISTING not_your_unit row
/// (STR_COOP_DENY_NOT_YOUR_UNIT, "Not one of your soldiers") - the same
/// ownership reason the wire deny carries; no duplicate key is minted for it,
/// exactly as refuseControl()'s ownership term reuses it. Self-guarded:
/// SP click-to-select is byte-identical.
bool refuseSelectUnitClick(const BattleUnit* target);

/// the SPECTATOR notice - this machine's seat
/// commands no unit in this battle, so battle entry could not auto-select one
/// for it (STR_COOP_SPECTATOR_MODE). Legacy raised the same notice from its own
/// client unit selector (`1e0f9276f:BattlescapeState.cpp:1627-1631`, "You are
/// in spectator mode"); this is that message, on this presenter.
///
/// Raised once per battle by CoopHandshake::selectOwnUnitAtEntry(). It is a
/// real path, not defensive framing: a plain classic "NEW BATTLE > COOP"
/// skirmish never calls Soldier::setCoop(), so without the harness's
/// newbattle_seat_soldier lever the joining client owns ZERO battle units.
/// Like showEquipFrozen() it is an ENTRY notice, not sticky - the first
/// deny/pending/cancel replaces it.
void showSpectatorMode();

// ---------------------------------------------------------------------------
// Order feedback.
//
// BANNER CLASSES. Every entry point above and below writes the ONE _txtCoopWait
// surface, so each message has a CLASS and one arbitration rule,
// rather than letting the newest writer always win:
//
//   Sticky   showDesyncHalted() only. Never overwritten, never auto-cleared -
//            there is nothing to retry into once a battle has desynced.
//   Terminal an ANSWER to something the player just did: a non-busy deny, a
//            policy cancel, an intent timeout, and every local refusal (the
//            refuseControl() controls, the select refusal, the END TURN refusal).
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
//            every test written against it) holds.
//
// Only Sticky blocks an overwrite. The per-tick WAIT driver additionally writes
// only when the current class is Wait, Notice or nothing (a Notice's own
// contract is that the first deny/pending/cancel replaces it, and a live waiting
// message is exactly that), and it CLEARS only what it itself wrote - so neither
// a deny the player has not read yet, nor their own 'order sent' indicator, nor
// an entry notice is stomped by an idle driver.
// ---------------------------------------------------------------------------

/// CLIENT: the 'order sent' IN-FLIGHT indicator, raised by
/// CoopArbiter::sendClientIntent() the moment the bt_intent envelope goes out
/// and cleared when the round trip ends (bt_action_end applied, or replaced by a
/// deny/pending/timeout). STR_COOP_ORDER_SENT. Without it the window between
/// the click and the host's answer shows NOTHING; the player should always
/// know what the network did with the click. No-op outside an active coop battle.
void showOrderSent();

/// CLIENT: the intent TIMEOUT banner
/// (STR_COOP_ACTION_TIMEOUT, "No answer from the host - action dropped"). Raised
/// by CoopArbiter::tickIntentTimeout() at the moment it releases the one-slot input lock.
/// Terminal class, so it dwell-clears like any other answer.
void showIntentTimeout();

/// The per-tick driver: ONE unconditional guarded call from the pump point
/// (connectionTCP::updateCoopTask, beside CoopReveal::flushQuiescent()). Three
/// jobs, all self-guarded and completely inert outside an active co-op battle:
///   1. CoopArbiter::tickIntentTimeout() - the 10 s intent timeout.
///   2. the Terminal-class AUTO-CLEAR: a Terminal banner clears itself
///      kCoopBannerDwellMs after it was raised (otherwise a refusal would sit on
///      the map strip until the player's next successful action), and is still
///      replaced early by the next message or cleared by the player's own next
///      successful action.
///   3. the seat-attributed WAIT banner - the donor's
///      "Please wait for {0}'s action to finish" driver
///      (`cbff7951d:BattlescapeState.cpp:5292-5370`), re-homed from a vanilla
///      per-frame method into CoopMod and fed by CoopArbiter::busyOwnerSeat().
/// right after the live-state check, the CLIENT's
/// battle-message drain (onMessageEvApplied() below decides, this shows).
void tick();

/// The Terminal-class dwell, in milliseconds (rule 2 above). Long enough to read
/// a one-line banner comfortably, short enough that the map strip does not carry
/// a stale answer into the next exchange.
static const unsigned int kCoopBannerDwellMs = 6000u;

// ---------------------------------------------------------------------------
// Nothing is hidden off-baton.
// Instead the bottom bar (the `_icons` panel and everything drawn on it) is
// rendered through a gray lookup while it is not this seat's go. Every
// widget stays visible and interactive; the refusal and the
// persistent wait banner are what actually say "not your turn".
// ---------------------------------------------------------------------------

/// THE ONE vanilla touch for this: BattlescapeState::blit() overrides
/// State::blit() (State.h's virtual) and, after calling it, makes this ONE
/// call with the `_icons` panel's own rect. This function decides for itself
/// whether to act - the vanilla override itself carries no logic. Self-guarded
/// (CoopMod, the only reader): acts only in a live coop battle,
/// turnMode==Traditional, phase==Active, and activeSeat != localSeat; never in
/// parallel mode, never with effect in single player. No-op (mode "off") when
/// the gate is false, or when @a surface is not an 8bpp surface.
///
/// Builds/rebuilds a 256-entry lookup table lazily, from @a surface's own
/// palette, whenever the cached copy no longer matches the live one. Applies
/// `p = LUT[p]` to every pixel of the rect (x,y,w,h), clipped to @a surface;
/// nothing is ever restored - when the gate turns false the next frame simply
/// draws unmodified.
void coopGrayBottomBar(SDL_Surface* surface, int x, int y, int w, int h);

/// Test-only introspection: TRUE exactly when
/// coopGrayBottomBar() above would currently act (the same gate it evaluates
/// internally). Backs `battle_state.coopOffBatonGray`. Never read by game
/// logic.
bool coopOffBatonGrayActive();

/// Test-only introspection: the mode the LAST
/// EXECUTED coopGrayBottomBar() call stored - "lut", "darken", or "off".
/// Backs the `screen_pixels` probe's `mode` field, which must describe the
/// same completed frame the probe's own pixel read does. Never read by game
/// logic.
std::string coopGrayBottomBarMode();

// ---------------------------------------------------------------------------
// The battle MESSAGES on both machines - vanilla's boxes for this machine's own
// soldiers, a self-closing notice for the partner's.
// ---------------------------------------------------------------------------

/// Test/introspection (probe only): on a co-op CLIENT, one `seen`
/// record {seq, kind, unit, top} per applied `death`, `corpse`, `panic`, `psi`
/// or `spawn` ev - `unit` is the payload's `unit` (-1 without one), `top` the
/// class name of the Game's top state at the apply ("none" without a live
/// BattlescapeState). Called
/// once from CoopDisplayQueue::onApplied() right after the ev's delta applied
/// Writes the probe storage only; inert on the host and outside a co-op
/// battle.
void noteMessageEvSeen(const SavedBattleGame* save, const Json::Value& ev);

/// Test/introspection: event_state `messages`, both machines, read-only -
/// {counts: {box, okbox, notice, pause, none, queued, droppedAtBattleEnd},
///  queueDepth, ring, seen}.
///   ring    the last 32 decided messages, oldest first: {seq, kind, unit, key,
///           owner, presenter, queued, queuedAtMs, shownAtMs}. `unit` = the unit
///           the message is ABOUT (vanilla's push site argument), `key` the
///           vanilla STR_ key ("" for the invisible pause), `owner` its relation
///           to this machine (own | partner | other),
///           `presenter` box | okbox | notice | pause | none, `queued` true when
///           at the decision the live BattlescapeState was not the Game's top
///           state (the entry had to wait in the queue; always false on the
///           host, which presents at the vanilla push site), `queuedAtMs` /
///           `shownAtMs` SDL ticks (0 = not shown yet). `seq`: on the CLIENT the
///           seq of the applied ev the decision was made at; on the HOST its
///           lastSeqEmitted when the push site ran. `kind`: the cue kind the
///           decision came from (client).
///   counts  per presenter, the records appended with it; `queued` the records
///           appended with queued true; `droppedAtBattleEnd` the queued entries
///           an applied battle_end cleared.
///   queueDepth  the client's decided-but-not-yet-shown entries.
///   seen    CLIENT only: noteMessageEvSeen()'s records, the last 32.
/// Battle-scoped: the storage starts over on the first main-thread use after
/// CoopGhost::reset() bumps the combat generation and whenever the
/// live BattlescapeState changes. Every count is 0 and ring/seen are empty
/// outside a co-op battle.
Json::Value messagesProbe();

/// The
/// CLIENT presenter. Called once from CoopDisplayQueue::onApplied() for every applied bt_ev, after the ev's delta (it
/// makes the noteMessageEvSeen() call itself). From the cue and the canonical state AFTER
/// the delta, with vanilla's own conditions, it decides the messages vanilla's host shows: a `death` is remembered and
/// decided at the unit's `corpse`, at a `spawn {cause convert}` from it, or at the first applied `bt_action_end` /
/// `sync` / `side_transition` after it (has died from a fatal wound / has been killed / has become unconscious, this
/// machine's own per-unit dedupe 0/1/2); a `panic` (has panicked / has gone berserk); a successful `psi` (is under
/// alien control / morale attack / mind control successful); a convert `spawn` with no pending death (has been
/// killed). The presenter follows the unit the message is ABOUT: own, and units no player owns -> vanilla's box
/// (InfoboxOKState for the two OK-box texts, InfoboxState otherwise); the partner's -> the fading notice. Every
/// decision is queued and shown by tick(). An applied `battle_end` clears the queue (counted droppedAtBattleEnd) and
/// nothing shows after it. Inert on the host and outside a co-op battle; writes no unit field, draws no sim RNG,
/// emits nothing.
void onMessageEvApplied(const SavedBattleGame* save, const Json::Value& ev);

/// The CLIENT's pre-apply read - for a `spawn {cause convert}`,
/// whether its `from` unit is FACTION_PLAYER before the ev's delta (vanilla convertInfected()'s own test). Called once
/// from CoopDisplayQueue::onApplied() before the ev's payload and delta apply. Read-only; inert on the host.
void onMessageEvPreApply(const SavedBattleGame* save, const Json::Value& ev);

/// The CLIENT's bt_action_end decision point - every death still
/// pending decides its message here. Called once from CoopDisplayQueue::onApplied()'s bt_action_end branch, after
/// the end's delta. Inert on the host.
void onMessageActionEndApplied(const SavedBattleGame* save, const Json::Value& ev);

/// The
/// ENTRY notices clear at this seat's first own-side side_begin. A Notice-class banner is cleared when its text is
/// STR_COOP_EQUIP_FROZEN or STR_COOP_WAITING_FOR_JOIN, or STR_COOP_SPECTATOR_MODE while this seat now commands its
/// selected unit. Called on the CLIENT after its own-side side_begin re-selection, and on the HOST right after it sends
/// a side_begin of its own side. No-op outside a co-op battle or with no live BattlescapeState.
void clearEntryNotices(const SavedBattleGame* save);

} // namespace CoopBattleUi

} // namespace OpenXcom
