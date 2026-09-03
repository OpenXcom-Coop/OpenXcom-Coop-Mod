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
#include <string>

// W1-P7 deliverable 6 (REV D / WV-D55): the battle-save hook pair below takes
// YAML nodes. Forward-declared, never included - this header is deliberately
// dependency-light (see the class comment) and the only two call sites
// (SavedBattleGame::save/::load) already have the complete types.
namespace YAML { class YamlNodeReader; class YamlNodeWriter; }

namespace OpenXcom
{

class BattleUnit;
class SavedBattleGame;

/**
 * W1-P7 deliverable 6 (WAVE1-RUNBOOK.md REV D, owner rulings D-19..D-27 =
 * WV-D55): the session's TURN MODE. Chosen by the HOST, stamped onto every
 * battle_offer (SS2.W1) and MIRRORED by the client - a client's own setting is
 * irrelevant, exactly like the donor's session-decided-once shape.
 *
 * Parallel    - all seats on the active side act simultaneously, individual
 *               actions serialized through host admission (SS2.5). Everything
 *               REV A-C describes, and THE DEFAULT (D-26).
 * Traditional - one seat commands at a time; END TURN passes the baton to the
 *               next seat; the last pass closes the side.
 *
 * W1-P7 CARRIES, STORES AND REPORTS the mode and NOTHING ELSE. **No code may
 * branch behaviour on it in this packet** (REV D, binding) - the baton logic and
 * the off-baton presentation are W1-P13's, and hard-coding the parallel rule into
 * `needed` or into coopMayCommand() is exactly what that rule forbids.
 */
enum class CoopTurnMode { Parallel, Traditional };

/// The SS2.W1 wire spelling of @a m: "parallel" or "traditional". Never any
/// other string - this is what goes on battle_offer.
const char* coopTurnModeName(CoopTurnMode m);

/// Parse an SS2.W1 wire value. ANY value other than "traditional" - including
/// an empty string, i.e. an ABSENT key - is PARALLEL. That is D-26's free
/// backwards-compatible degrade, not leniency: an older host sends no key at all
/// and must be understood as the classic model (donor precedent
/// `cbff7951d:connectionTCP.cpp:12716` [V], `get(..., false)` for the same
/// reason).
CoopTurnMode coopTurnModeFromString(const std::string& s);

/// The HOST's remembered preference, normalized: Options::CoopTurnMode run
/// through coopTurnModeFromString(). Read ONLY by the host, and only when it
/// builds an offer - never by a client, and never to decide behaviour.
CoopTurnMode coopSessionTurnModeFromOptions();

/// D.1 BATTLE-SAVE HOOK (owner revision to D-20/D-21, binding). The thin
/// coop-gated pair `SavedBattleGame::save`/`::load` calls, so a battle save
/// carries the mode it was PLAYED in and a mid-battle resume comes back in that
/// mode even after a full host restart - which is why the engine never has to
/// support a parallel->traditional transition through save/load.
///
/// SP AND NON-COOP STAY BYTE-IDENTICAL: coopSaveTurnMode() writes NOTHING unless
/// this is an active co-op battle, so the key is simply ABSENT from every SP
/// save. The CAMPAIGN save block is deliberately untouched - the donor's
/// `SavedGame.cpp:1334`/`:1814` shape is NOT ported (D-21).
///
/// The key is on `SharedEcon.cpp`'s saveBlobExcludedTopKey list so session
/// configuration never rides the saveBlob hash; both machines agree on the value
/// via the offer anyway.
///
/// W1-P7 only WRITES and READS the key. CONSUMING it on resume - putting it on a
/// `resumed:true` offer instead of Options::CoopTurnMode (D-22) - is r4 T4's and
/// is OUT OF WAVE.
void coopSaveTurnMode(YAML::YamlNodeWriter& writer);
void coopLoadTurnMode(const YAML::YamlNodeReader& reader);

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

	/// W1-P7 deliverable 6 (REV D / WV-D55): THIS BATTLE's turn mode - the
	/// runtime mirror of the session choice, the same role the donor's
	/// `connectionTCP::_enable_parallel_turns` played
	/// (`cbff7951d:connectionTCP.cpp:12716` [V]). Set on the HOST when it builds
	/// the offer and on the CLIENT from `battle_offer.turnMode`; reset to the
	/// D-26 default by resetBattleAuthority(). It lives HERE rather than in a
	/// bare static because it is battle-scoped state with a teardown reset, and
	/// because every future reader (W1-P13's baton) already reads this object.
	///
	/// **NOTHING IN W1-P7 BRANCHES ON IT** (REV D, binding): it is carried,
	/// stored and reported only. std::atomic for the same cross-thread reason as
	/// the four fields above.
	std::atomic<CoopTurnMode> turnMode{CoopTurnMode::Parallel};

	/// R2-P9 (SPIKE-RUNBOOK.md SS2.8): set the moment this machine's own
	/// hash-mismatch detector (CoopHashCheck::verify, BattlePump.h) latches a
	/// desync - "freeze battle input" per SS2.8's mismatch-behavior note.
	/// Distinct from BattlePump.h's g_battleFrozen (the R2-P2 seq-gap apply-
	/// queue halt, a low-level plumbing flag): this one is the
	/// BattleAuthority-level signal higher gating code (the R3-P1 client
	/// intent tracker/intercept sites) is meant to read. A hash mismatch
	/// ALSO sets g_battleFrozen (halting the apply queue too) - the two flags
	/// are set together on a mismatch, never independently, but kept
	/// separate because they answer different questions ("is the low-level
	/// apply queue paused" vs "has this battle desynced"). NO partial
	/// repair, never cleared mid-battle (SS2.8): rejoin is post-spike.
	std::atomic<bool> desyncFrozen{false};

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
	// R5-P2 mcId override (SPIKE-RUNBOOK.md ADDENDUM MJ-8, formula corrected
	// by R2-M4): "controlled" is faction != originalFaction (NOT a raw mcId
	// check - mcId also gets set by a successful panic with no control
	// transfer, TileEngine.cpp:4774, and is never cleared on revert). When
	// controlled, the commanding seat is the seat of the getMindControllerId()
	// unit; if that unit no longer resolves (dead/gone), ownership falls to
	// host/AI (MJ-8's own "none/dead -> host/AI" fallback) - only seat 0
	// commands it. A non-MC unit falls straight through to its own seat tag.
	// Body in connectionTCP.cpp (RB-D6 pattern).
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
/// store cleared, turnMode=Parallel per D-26).
void resetBattleAuthority();

/// connectionTCP::getCoopStatic() && phase == Active. Deliberately NOT
/// defined inline in this header: connectionTCP::getCoopStatic() needs
/// connectionTCP.h, which is the heavy net-layer header this file exists to
/// avoid pulling in (same reasoning as the class forward-declarations
/// above) - defined instead in connectionTCP.cpp next to
/// coopBattleAuthority().
bool isCoopBattle();

/// R5-P2 input-gating combinator (SPIKE-RUNBOOK.md R5-P2 packet text: "ONE
/// predicate for 'I may command this unit': my seat commands it AND my
/// faction side is active"). Self-guarded like isCoopBattle() - returns
/// true (permissive) outside an active coop battle, so every thin vanilla
/// hook site is a single unconditional call:
/// `if (!coopMayCommand(unit, save)) return;`
/// Inside a coop battle: coopBattleAuthority().commandsUnit(unit) &&
/// coopBattleAuthority().mySideActive(save). Used by the THIN action-gating
/// hooks (BattlescapeGame::primaryAction/secondaryAction,
/// BattlescapeState::btnKneelClick) - never by the selection-cycle filter
/// below, which only needs the commandsUnit half (see coopMaySelectUnit()).
/// Defined in connectionTCP.cpp next to isCoopBattle().
bool coopMayCommand(const BattleUnit* u, const SavedBattleGame* s);

/// R5-P2 selection-cycle predicate: the CoopMod half of the
/// SavedBattleGame::selectPlayerUnit() filter call (RB-D10/R5-P2's
/// "pass a CoopMod predicate through ONE guarded filter call so the
/// selection cycle SKIPS units this machine's seat does not command").
/// Self-guarded (true outside an active coop battle); inside one, equals
/// coopBattleAuthority().commandsUnit(u). Deliberately does NOT also check
/// mySideActive() - selectPlayerUnit() already restricts candidates to
/// SavedBattleGame::_side via BattleUnit::isSelectable(), so a candidate
/// reaching this predicate is already on the currently active side; the
/// active-side check belongs to the action-gating hooks (coopMayCommand()
/// above), not to cycling among already-active-side candidates. Defined in
/// connectionTCP.cpp next to isCoopBattle().
bool coopMaySelectUnit(const BattleUnit* u);

/// W1-P6 (WAVE1-RUNBOOK.md ruling D6 = WV-D12; NON-NEGOTIABLE rule WV-D40 /
/// WR-2): the INVERTED form of coopMayCommand() used by
/// BattlescapeGame::primaryAction's COMMANDING arms, plus a test-only counter.
///
/// W1-P6 moved primaryAction's single ENTRY guard off the top of the function
/// and ONTO the two arms that actually execute something - the
/// targeting/BA_LAUNCH/spray block and the walk-confirm arm - so that the
/// SELECT-UNIT branch sitting between them can finally run on a co-op client
/// for the units its own seat commands (D6's "a seat ... CAN select what it
/// does command"; click-to-select was dead on a client before this packet).
/// WV-D40 pins the exemption to exactly that one branch: every commanding arm
/// stays gated, and a client ground-click must mint NOTHING for the whole of
/// wave 1 - the walk ORDER arrives with W1-P9's intent path, and until then a
/// locally-executed UnitWalkBState would be a guaranteed, permanent desync.
///
/// THE PREDICATE IS A CONJUNCTION, and NOT `!coopMayCommand(u, s)` alone -
/// that shorthand provably cannot meet WV-D40's own requirement, and exactly
/// the same correction is already on the record for W1-P5's D8 gates:
/// `coopMayCommand(u, s)` is `commandsUnit(u) && mySideActive(s)`, i.e. TRUE
/// for a client acting on its OWN unit during its OWN side - which is exactly
/// when the walk arm fires. So the gate is, in this order:
///   1. `coopBattleAuthority().hostSim` - only the SIMULATING machine may run
///      an action that has no wire representation yet. THIS is the term that
///      makes "a client ground-click mints NOTHING" true.
///   2. `coopMayCommand(u, s)` - on the host, the seat must still command the
///      unit and its side must be active (R5-P2's original entry-guard
///      semantics, not weakened by this packet).
/// `BattlescapeState::btnKneelClick` is the shipped two-term house pattern
/// (`coopMayCommand` then `isCoopBattle() && !hostSim`); kneel's second term
/// SENDS an intent, primaryAction has no wire verb until W1-P9 so its second
/// term simply refuses. Self-guarded exactly like isCoopBattle()/
/// coopMayCommand(): outside an ACTIVE co-op battle it returns false and
/// vanilla - SP included - is byte-identical.
///
/// The counter is the other half: each refusal bumps a value
/// coopLocalExecutionBlocks() reports. That is what makes W1-G1 criterion 4b
/// provable rather than inferable - "the client's ground click minted nothing"
/// must not be satisfiable by a click that never reached primaryAction at all.
/// Defined in connectionTCP.cpp next to coopMayCommand().
bool coopBlockLocalExecution(const BattleUnit* u, const SavedBattleGame* s);

/// W1-P6: test-only introspection - how many times coopBlockLocalExecution()
/// has refused a local execution in this process. Reported by TestServer's
/// `event_state` as `coopLocalExecBlocked`; never read by game logic.
int coopLocalExecutionBlocks();

} // namespace OpenXcom
