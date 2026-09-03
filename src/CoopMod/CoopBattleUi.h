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

} // namespace CoopBattleUi

} // namespace OpenXcom
