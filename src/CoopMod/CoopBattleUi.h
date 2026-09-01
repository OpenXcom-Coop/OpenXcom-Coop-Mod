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
 * This packet does NOT wire a live caller: the host-side arbiter (R2-P5)
 * already sends bt_deny{reason} on the wire, but the CLIENT-side bt_deny
 * receipt that would call showDeny() lands in R3-P1 (see the
 * "R3-P1 client bt_deny -> CoopBattleUi::showDeny" marker at the
 * client-inbound seam in connectionTCP.cpp's onTCPMessage). showPending/
 * clearPending are likewise unwired until R2-P7's auto-retry/pending
 * indicator lands.
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

/// R2-P7: shown while a busy-denied intent is held and auto-resubmitted
/// (ADDENDUM 1.3(d)). @a context is unused in this packet (R2-P6 provides
/// only the API surface + a minimal busy-text presentation; R2-P7 wires the
/// real pending indicator/cancel-control behavior and may start using it).
void showPending(const char* /*context*/);

/// R2-P7: clears whatever showPending() set (hides the banner). No-op
/// outside an active coop battle.
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

} // namespace CoopBattleUi

} // namespace OpenXcom
