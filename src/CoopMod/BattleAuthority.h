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

#include <atomic>
#include <cstdint>

namespace OpenXcom
{

class BattleUnit;
class SavedBattleGame;

/**
 * R2-P3 (rewrite spike, SPIKE-RUNBOOK.md RB-D6): the ONE battle-authority
 * object - kill-by-construction of the legacy getHost()/onTcpHost
 * turn-token tangle for battle logic. A single global instance is DEFINED
 * in connectionTCP.cpp (RB-D6); every battle-logic site is meant to read
 * coopBattleAuthority() instead of branching on getHost() (S3a N-player
 * guardrail: no new getHost() branches in battle logic).
 *
 * Deliberately dependency-light, same discipline as CoopSeat.h (RB-D17):
 * BattleUnit/SavedBattleGame are forward-declared only here - their full
 * definitions are only needed in the connectionTCP.cpp method bodies, which
 * already include both. This keeps the header safe to include from thin
 * hook sites in vanilla battle files later (R2-P5+) without dragging the
 * net layer (connectionTCP.h/Game.h/BattlescapeGame.h) in - the same
 * "BattleUnit.h drags net layer" disease RB-D17 already refuses for the
 * seat tag.
 *
 * R4-P1 CROSS-THREAD FIX (SPIKE-RUNBOOK.md R4-P1 packet text, "cross-thread
 * safety" watch item): handleUdpRemotePeerLost() (connectionUDP\
 * connection_rendezvous_glue.cpp) can call clearNetworkSessionQueues() -> ...
 * -> resetBattleAuthority() from the UDP-monitor thread (its own doc comment:
 * "may run from the UDP monitor thread"), while the main/pump thread reads
 * and writes these same fields throughout CoopArbiter/CoopHandshake. Before
 * R4-P1 this was latent (nothing populated the fields mid-battle from the
 * main thread while a peer-lost teardown could race it); offerBattle()/
 * finishLoad() now do, making it a live data race. Fix: every field below
 * that crosses threads (hostSim/localSeat/phase/battleId, and the
 * _seatFaction store) is std::atomic. This is a mutex-free guard rather than
 * RB-D6's literal "add a mutex" suggestion because every existing read/write
 * call site (CoopArbiter, the R2-P3 self-test, this header's own doc
 * examples) already uses plain `a.field = x` / `a.field == y` - std::atomic's
 * implicit conversion operator and operator= keep every one of those call
 * sites source-compatible (verified: no call site copies or value-assigns a
 * BattleAuthority - always accessed through the coopBattleAuthority()
 * reference), so no call site anywhere in the tree needed to change. The one
 * piece that CANNOT be made atomic - CoopIdMaps' std::unordered_map<int,
 * BattleUnit*>/<int, BattleItem*> storage in connectionTCP.cpp - gets an
 * actual std::mutex instead (see CoopIdMaps.h's forward-declared functions'
 * .cpp bodies): every CoopIdMaps:: function now takes the SAME
 * g_coopIdMapsMutex internally, closing the identical race for the id maps
 * (their storage is `static` file-scope in connectionTCP.cpp and reached
 * ONLY through these functions, so locking inside each function body closes
 * every call site with zero call-site changes there too).
 */

enum class CoopBattlePhase
{
	Idle,
	Handshake,
	Active,
	Ended
};

struct BattleAuthority
{
	/// IMMUTABLE per battle: set once by initBattleAuthority() below (R2-P3)
	/// from connectionTCP::getServerOwner() (RB-D6). The mutable getHost()/
	/// onTcpHost token is legacy-dead for battle logic - never branch battle
	/// code on getHost(). std::atomic: see the R4-P1 cross-thread fix note
	/// above the enum.
	std::atomic<bool> hostSim{false};

	/// This machine's seat. Set once by initBattleAuthority() from
	/// connectionTCP::localSeat(). -1 (unset) at Idle.
	std::atomic<int> localSeat{-1};

	/// Battle lifecycle phase. Idle until R4-P1's handshake calls
	/// initBattleAuthority() (-> Handshake) and later stamps Active on a
	/// successful battle_ready; R2-P8 wires the real Ended -> teardown ->
	/// Idle transition at the teardown chokepoint (resetBattleAuthority()
	/// below provides the reset itself). Public field, not a setter: R4-P1/
	/// R2-P8 transition it with a plain assignment.
	std::atomic<CoopBattlePhase> phase{CoopBattlePhase::Idle};

	/// Host-minted at battle_offer (SS2.2); 0 = none yet.
	std::atomic<std::uint32_t> battleId{0};

	/// Seat -> FACTION_* lookup, backed by the private store below. R2-P3
	/// interim (RB-D18): the store starts empty and factionOf() falls back
	/// to FACTION_PLAYER for any unmapped/out-of-range seat - correct for
	/// the spike's classic/SHARED-only fixtures (RB-D16), where every valid
	/// seat is on the player side. setSeatFaction() lets R4-P1's handshake
	/// init populate the real {0:player,1:player} map (RB-D18).
	// R5-P1 real seatMap: gm2/gm3/gm4 repoint this store + factionOf(); not
	// implemented here (RB-D16).
	int factionOf(int seat) const;

	/// True iff the currently active side in @a s (SavedBattleGame::
	/// getSide()) is the faction this machine's localSeat commands
	/// (factionOf(localSeat)). False if @a s is null.
	bool mySideActive(const SavedBattleGame* s) const;

	/// True iff this machine currently commands @a u: the unit's seat tag
	/// (BattleUnit::getCoopSeat()) equals localSeat. False if @a u is null.
	// R5-T2 mcId override: a real mind-control override would let the
	// controlling seat command a unit despite its own seat tag when
	// u->getFaction() != u->getOriginalFaction(). The spike stub always
	// resolves "no override" - kneel/turn (the only spike intents) never MC
	// a unit, so falling straight through to the seat-tag check is safe.
	bool commandsUnit(const BattleUnit* u) const;

	/// True iff this seat commands no player-side faction right now:
	/// localSeat is unset (<0), or factionOf(localSeat) is not the player
	/// side. Minimal by construction (this method takes no SavedBattleGame
	/// parameter to check "currently active side" against) - under RB-D18's
	/// interim map every valid seat is FACTION_PLAYER, so in the spike this
	/// reduces to "localSeat < 0"; it stops being trivial once R5-P1's real
	/// seatMap adds non-player-controlled seats.
	bool isSpectator() const;

	/// R2-P3: minimal interim seat->faction store backing factionOf()
	/// (RB-D18). Out-of-range seats are ignored (no-op).
	void setSeatFaction(int seat, int faction);

	/// Clears the seat->faction store back to "everything unmapped" (every
	/// seat falls back to factionOf()'s FACTION_PLAYER default).
	void resetSeatFactions();

private:
	static const int kMaxSeats = 4; // COOP_SEAT_0..COOP_SEAT_3, RB-D17
	static const int kUnmapped = -1;
	// R4-P1 cross-thread fix (see the note above the enum): std::atomic, same
	// reasoning as hostSim/localSeat/phase/battleId above - resetSeatFactions()
	// is reachable from resetBattleAuthority(), which the UDP-monitor thread
	// can call via handleUdpRemotePeerLost().
	std::atomic<int> _seatFaction[kMaxSeats] = { kUnmapped, kUnmapped, kUnmapped, kUnmapped };
};

/// The one global BattleAuthority instance (RB-D6). Defined in
/// connectionTCP.cpp.
BattleAuthority& coopBattleAuthority();

/// R4-P1 will call this at the real handshake transition; R2-P3 only
/// provides the function. Sets hostSim (a ONE-TIME read of
/// connectionTCP::getServerOwner() - hostSim itself stays immutable for the
/// rest of the battle after this) and localSeat (from
/// connectionTCP::localSeat()), stamps @a battleId, moves phase to
/// Handshake, and clears the interim seat->faction store (RB-D18) so the
/// caller can repopulate it via setSeatFaction().
void initBattleAuthority(std::uint32_t battleId);

/// R2-P8 will wire this at the real battle-teardown chokepoint; R2-P3 only
/// provides the function. Resets the singleton back to its Idle default
/// (hostSim=false, localSeat=-1, phase=Idle, battleId=0, seat->faction
/// store cleared).
void resetBattleAuthority();

/// connectionTCP::getCoopStatic() && phase == Active. Deliberately NOT
/// defined inline in this header: connectionTCP::getCoopStatic() needs
/// connectionTCP.h, which is the heavy net-layer header this file exists to
/// avoid pulling in (same reasoning as the class forward-declarations
/// above) - defined instead in connectionTCP.cpp next to
/// coopBattleAuthority().
bool isCoopBattle();

} // namespace OpenXcom
