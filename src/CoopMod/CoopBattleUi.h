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
