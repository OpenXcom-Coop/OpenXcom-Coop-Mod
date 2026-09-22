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

#include <cstdint>

#include <json/json.h>

namespace OpenXcom
{

class BattleUnit;
class SavedBattleGame;

/**
 * SPEC 17 (W1-P18): per-seat animation pacing. Each seat keeps ANIMATING at
 * its OWN machine-local battleXcomSpeed/battleAlienSpeed/battleFireSpeed
 * option instead of every machine snapping every unit (including a partner's)
 * to the LOCAL option value - a client set to 30 must still see the HOST
 * simulate that client's own unit at 30, not the host's 10.
 *
 * G1 (DP2 guardrail, binding): this is a SESSION-LEVEL mechanism only. No
 * per-event timing, cadence, frame count or animation duration is ever put on
 * the wire; the two new kinds (battle_speed_report/battle_speed_seats) are
 * NOT bt_ev, NOT seq-ordered, and never hashed (BattleWire.h).
 *
 * Storage lives in connectionTCP.cpp (namespace CoopSpeed, OUTSIDE the
 * RW-REPLAY-REGION markers - this mechanism reads/writes real state, unlike
 * that region's display-only replay); this header only declares the API.
 */
namespace CoopSpeed
{

/// The three speed dials one seat is running (Options::battleXcomSpeed /
/// battleAlienSpeed / battleFireSpeed at that seat's own machine).
struct Triple
{
	int xcom;
	int alien;
	int fire;

	bool operator==(const Triple& o) const
	{
		return xcom == o.xcom && alien == o.alien && fire == o.fire;
	}
	bool operator!=(const Triple& o) const
	{
		return !(*this == o);
	}
};

/// Which dial of a Triple a read site wants (speedFor()'s discriminator).
enum Which
{
	Xcom,
	Alien,
	Fire
};

/// COOP_SEAT_0..COOP_SEAT_3 (RB-D17). BattleAuthority::kMaxSeats is private
/// to that class, so this is its own copy of the same constant.
const int kMaxSeats = 4;

/// This machine's OWN speed dials, straight off Options - what a NON-coop
/// battle always uses, and what a coop battle's local seat entry mirrors.
Triple localTriple();

/// The slowest-wins Triple over every CONNECTED seat with a valid table
/// entry (MAX xcom, MAX alien, MIN fire - R1 measured: slower is a HIGHER
/// xcom/alien speed value but a LOWER fire speed value). Falls back to
/// localTriple() when no connected seat has a valid entry yet.
Triple floor();

/// The one read site helper: the speed @a w should run at for @a u's
/// animation. Outside a coop battle, always the raw local option (SP/every
/// non-coop battle is byte-identical). Inside a coop battle: @a u's OWNING
/// seat's table entry when @a u is seated and that seat's entry is valid;
/// otherwise the floor() fallback (multi-unit/unowned states). Records the
/// read in lastRead() for test introspection.
int speedFor(const BattleUnit* u, Which w);

/// speedFor(u, Xcom/Alien/Fire) - the three read-site call shapes.
int xcomSpeedFor(const BattleUnit* u);
int alienSpeedFor(const BattleUnit* u);
int fireSpeedFor(const BattleUnit* u);

/// Per-tick pump (connectionTCP::updateCoopTask()): when this machine's own
/// localTriple() has changed since the last time this ran (or never sent
/// yet), the HOST refreshes its own seat-0 table entry and republishes the
/// table (tableChanged()); a CLIENT instead sends a battle_speed_report.
/// No-op outside a coop battle.
void onLocalChanged();

/// HOST only: bumps the table's sequence number and broadcasts the full
/// connected+valid seat table as battle_speed_seats.
void tableChanged();

/// Battle-scoped teardown: zeroes the table, clears every seat's validity,
/// resets the sequence number and every counter, and clears lastRead().
/// Called from resetBattleAuthority() (connectionTCP.cpp).
void reset();

/// The exact unit-less form of coopMayCommand(u, s)'s two non-unit terms
/// (F373): TRUE outside a coop battle; inside one, TRUE only when @a s's
/// side is this seat's AND (parallel mode, or this seat holds the
/// traditional baton). The Ctrl-S quick-mode toggle (M6) has no single
/// acting unit, so it gates on this instead of coopMayCommand().
bool quickModeAllowed(const SavedBattleGame* s);

/// Bumps the quickModeIgnored() counter - called wherever quickModeAllowed()
/// gated a press away (M6).
void noteQuickModeIgnored();

// ----- probe accessors (TestServer.cpp event_state) - test introspection
// only, never read by game logic. -----------------------------------------

/// Seat @a seat's last-known Triple (meaningless unless seatValid(seat)).
Triple seatTriple(int seat);

/// Whether seat @a seat's table entry has ever been populated this battle.
bool seatValid(int seat);

/// The table's current sequence number (bumped by every tableChanged()).
std::uint32_t seq();

/// The most recent speedFor() read: which dial, what value it returned, and
/// the seat it was attributed to (-1 when the read fell through to floor()
/// rather than a specific owned+valid seat).
struct LastRead
{
	int which;
	int value;
	int seat;
};
LastRead lastRead();

/// How many battle_speed_report messages THIS client has sent this battle.
unsigned reportsSent();

/// How many battle_speed_seats messages THIS client has accepted (applied)
/// this battle.
unsigned tablesRecv();

/// How many times noteQuickModeIgnored() has fired this battle.
unsigned quickModeIgnored();

/// TRUE when this machine's own local-seat table entry (if any) already
/// equals localTriple() - i.e. nothing this machine would report is stale.
bool synced();

// ----- M3 wire plumbing (connectionTCP.cpp onTCPMessage/onBlobChunkAppended) -
// not part of the read-site/probe API above; called only from the message
// dispatch and the client's Active-transition site. -----------------------

/// The CLIENT's Active-transition hook (onBlobChunkAppended): clears
/// g_lastSentValid (so the very next onLocalChanged() tick sends a fresh
/// battle_speed_report even if this machine's own dials never change) and
/// seeds this client's OWN one-entry table view (its own seat, localTriple(),
/// marked valid) so event_state.speed.seats already shows this machine
/// before the first battle_speed_seats round-trip completes.
void onClientActive();

/// HOST-inbound (M3): stores seat @a seat's reported Triple and marks it
/// valid. The battle_speed_report handler (connectionTCP.cpp onTCPMessage)
/// calls tableChanged() itself right after.
void applyReport(int seat, const Triple& t);

/// CLIENT-inbound (M3): replaces the whole table with the host's
/// battle_speed_seats broadcast (@a seats is the wire array of
/// {seat,xcom,alien,fire} objects - only the seats the host considered
/// connected+valid), bumps the sequence number to @a seqIn, and counts the
/// accept (tablesRecv()).
void applySeats(std::uint32_t seqIn, const Json::Value& seats);

/// HOST-inbound (M3) drop path: TRUE (and latches) the FIRST time this is
/// called this battle; FALSE (already warned) every call after, so the
/// battle_speed_report handler logs an unexpected battleId/phase drop ONCE
/// per battle instead of once per message.
bool noteReportDropOnce();

} // namespace CoopSpeed

} // namespace OpenXcom
