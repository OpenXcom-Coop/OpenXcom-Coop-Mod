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
#include <vector>

// W1-P7 deliverable 6 (REV D / WV-D55): the battle-save hook pair below takes
// YAML nodes. Forward-declared, never included - this header is deliberately
// dependency-light (see the class comment) and the only two call sites
// (SavedBattleGame::save/::load) already have the complete types.
namespace YAML { class YamlNodeReader; class YamlNodeWriter; }

namespace OpenXcom
{

class BattleUnit;
class Game;
class Mod;
class RuleResearch;
class BattleState;
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

/// SPEC 18 (r4 T4, owner ruling D99=(a)): the BATTLE-SAVE hook pair for the
/// resolved mission deployment type, same shape and guard as the turn-mode
/// pair above - SavedBattleGame::save/::load call these beside
/// coopSaveTurnMode/coopLoadTurnMode. A thin client cannot re-derive
/// AlienDeployment on its own (BriefingState.cpp:73-99's Ufo fallback), so a
/// disk-resumed battle needs the value that lived only in the process-local
/// CoopHandshake::carriedDeploymentType() mirror BEFORE the restart. SP and
/// any battle that resolved no deployment write NOTHING (byte-identical).
/// The key is on SharedEcon.cpp's saveBlobExcludedTopKey list (both machines
/// already agree on the value via the offer, same as coopTurnMode).
void coopSaveDeployment(YAML::YamlNodeWriter& writer);
void coopLoadDeployment(const YAML::YamlNodeReader& reader);

/// SPEC 18 (r4 T4, owner ruling D100=(b)): the BATTLE-SAVE hook pair for the
/// traditional-mode baton holder (CoopEndTurn::batonSeat(), HOST-only, -1 in
/// parallel mode or before the entry tally). Presence-gated both ways; reads
/// back into the BattleAuthority::activeSeat MIRROR only - restoring the
/// live CoopEndTurn baton holder on a disk resume (with the D-23 degrade for
/// an absent/invalid key) is CoopEndTurn::onBattleResumed()'s job (M3, a
/// separate cycle). SP and parallel-mode saves write nothing meaningful in
/// practice (activeSeat is -1 there too), but the key is still written only
/// inside a coop battle - byte-identical outside one. Hash-excluded, same
/// list as coopTurnMode.
void coopSaveActiveSeat(YAML::YamlNodeWriter& writer);
void coopLoadActiveSeat(const YAML::YamlNodeReader& reader);

/// WV-D61 (owner ruling R-B, 2026-09-04): the HOST's true
/// SavedBattleGame::_itemId, carried in the BATTLE save block so the machine
/// that LOADS a coop blob adopts it verbatim instead of re-deriving
/// max(item id)+1 - a derivation that is provably wrong whenever generation
/// allocated an id that did not survive into the document (RB-D24's fallback,
/// superseded here). Key `coopItemIdCtr`, on saveBlobExcludedTopKey so it
/// never rides the saveBlob hash; the `itemIdCtr` BUCKET still compares it.
void coopSaveItemIdCtr(YAML::YamlNodeWriter& writer, const SavedBattleGame* battle);
void coopLoadItemIdCtr(const YAML::YamlNodeReader& reader, SavedBattleGame* battle);

/// WV-D61 test/introspection, the coopSpotEvsEmitted()/coopSpotEvsApplied()
/// precedent (CoopArbiter.h): how many times THIS machine's coopLoadItemIdCtr
/// actually adopted the carried counter (the last carried value stored
/// through getCurrentItemId() - present whenever the key is present and
/// carried >= derived, whether or not the two agreed), and how many times it
/// REFUSED to (the carried < derived branch, which must never fire in a
/// clean two-machine run - see SPEC 3 STOP-IF). "Adopted" is a VALUE, not a
/// boolean, so a positive-control test can see an adopt that never happened
/// (value stays 0) as distinct from one that did.
int coopItemIdCtrAdopted();
unsigned int coopItemIdCtrRefused();

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

	/// W1-P13c (WV-D55 / D-23): the seat that currently HOLDS THE BATON in
	/// traditional mode, as last HONOURED by this machine - i.e. the activeSeat
	/// of a bt_end_turn_tally whose `turn` matched this machine's last APPLIED
	/// side_transition counter. -1 = no baton (parallel mode, or before the
	/// first tally of a side). Reset to -1 by resetBattleAuthority().
	std::atomic<int> activeSeat{-1};

	/// W1-P14 (REV E.48 SS.F.2 (ii) / WV-D47 / SS2.W9): the ON/OFF switch for the
	/// own-side visibility rule, behind the test-only `battle_visibility_rule`
	/// lever. coopUnitVisibleHere() is its ONLY reader - it exists so a test can
	/// prove the rule is hash-free by comparing every bucket with it ON and OFF.
	/// Default TRUE (the rule is live in a real game); reset to TRUE by
	/// resetBattleAuthority(). std::atomic for the same cross-thread reason as
	/// activeSeat above.
	std::atomic<bool> visibilityRuleOn{true};

	/// W1-P13c (REV E.57 / D78 = (a)): the ONE pending tally. A
	/// bt_end_turn_tally whose `turn` is AHEAD of this machine's last APPLIED
	/// side_transition counter (the unordered battle lane beating the
	/// seq-ordered apply queue - SPIKE-RUNBOOK.md SS2.3 / WR-4) is BUFFERED
	/// here as the pair (turn, activeSeat) instead of being dropped, and
	/// honoured the moment onClientAppliedSideTransition() advances the
	/// counter to it. A newer pending pair replaces an older one; a tally
	/// older than the counter never overwrites one. -1 = nothing pending.
	/// Reset to -1 by resetBattleAuthority() and on every honoured apply.
	/// std::atomic for the same cross-thread reason as activeSeat above.
	std::atomic<int> pendingTallyTurn{-1};
	std::atomic<int> pendingTallyActiveSeat{-1};

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

	/// SPEC 16 (W1-P17) M1: latched when a mid-`Active`-battle peer LEAVE
	/// (graceful `disconnect_to_menu` or a liveness/socket-loss detection)
	/// spares the F331 authority reset instead of tearing the battle down to
	/// Idle - the battle, `battleId`, seat map, `turnMode` and baton all
	/// survive under it (see connectionTCP::disconnectTCP's host branch and
	/// its UDP twin, handleUdpRemotePeerLost()). Cleared back to false by
	/// resetBattleAuthority() (same discipline as desyncFrozen above) and by
	/// a successful rejoin-restream (M5, a later cycle). Reported additively
	/// on `battle_state.authority.peerAbsent` (TestServer.cpp) so a test can
	/// assert "paused, not torn down" without inferring it from the dialog
	/// alone. std::atomic for the same cross-thread reason as desyncFrozen
	/// (the UDP-monitor-thread race noted above the enum).
	std::atomic<bool> peerAbsent{false};

	/// SPEC 16 (W1-P17) M4: true when the CURRENT peerAbsent pause was
	/// entered via a graceful `battle_leave{seat,reasonKey}` (the departing
	/// seat's own deliberate `disconnect_to_menu`, sent to the host BEFORE
	/// its transport goes down) rather than a bare liveness/socket-loss
	/// detection. F341 (measured): this changes NOTHING about detection
	/// latency - both paths already raise the pause dialog in ~0.1s - its
	/// only wave-1 value is letting CoopState::waitingTitle() NAME the
	/// reason instead of always reading as a silent connection loss.
	/// Cleared by resetBattleAuthority() (same discipline as peerAbsent
	/// above) and by a successful rejoin-restream (M5's onReady), so a
	/// later, separate pause on the same battle never inherits a stale
	/// label. std::atomic for the same cross-thread reason as peerAbsent.
	std::atomic<bool> peerLeftByChoice{false};

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

	/// W2-P4 S-E4 (spec Q8 (a), N2 = F1036): the same rule for an explicit
	/// @a seat instead of this machine's localSeat - the HOST's admission of a
	/// REMOTE seat's intent (onIntent's not_your_unit). MJ-8's controller rule
	/// unchanged: a mind-controlled unit is commanded by its controller's seat
	/// (seat 0 when the controller no longer resolves). commandsUnit(u) is
	/// commandsUnit(u, localSeat).
	bool commandsUnit(const BattleUnit* u, int seat) const;

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

/// SPEC 18 (r4 T4) M8, owner ruling D101 = (a) + drain-first: the ONE shared
/// quiescence predicate - "the host BState stack drains (!isBusy()) AND no
/// pending origin-chain evs remain (CoopArbiter::currentActionId()==0)"
/// (D96), WITH the F392 isBattlescapeStateLive() live-state guard around the
/// getBattleState()/getBattleGame()/isBusy() reads (an un-live state counts
/// as "no live battle", i.e. quiescent - never re-derive a bare !isBusy(),
/// F400). EXTRACTED from the SPEC 16 pause-modal consumer
/// (connectionTCP.cpp, updateCoopTask()) so BOTH that latch
/// (g_coopPauseModalPending) and the SPEC 18 deferred-battle-save latch
/// (g_coopDeferredBattleSave) read the SAME gate. Defined in
/// connectionTCP.cpp next to isCoopBattle().
bool coopBattleQuiescent();

/// SPEC 18 (r4 T4) M8: arm the deferred mid-battle coop save latch, called
/// from SaveGameState::think() the moment it observes isCoopBattle() &&
/// !coopBattleQuiescent() - i.e. every mid-battle coop save funnels through
/// this ONE chokepoint (quick-save/insta-save keys, the pause-menu Save,
/// ListSave SAVE & QUIT, the M7 harness lever `save_game_ui type:
/// "quick_battle"`), regardless of how busy-gated each trigger's own UI
/// happens to be. `origin` is OptionsOrigin and `saveType` is SaveType
/// (Menu/SaveGameState.h), both passed as their own underlying int so this
/// header stays dependency-light exactly like isCoopBattle() above -
/// connectionTCP.cpp casts them back at the ONE consume site (the RB-D5
/// pump point, beside the SPEC 16 pause-modal consumer). `useTypeForm`
/// selects which SaveGameState constructor the consumer re-invokes: false =
/// the filename-form ctor (origin, filename, palette, quitAfterSave) - used
/// by ListSave SAVE & QUIT; true = the type-form ctor (origin, SaveType,
/// palette) - used by the quick-save/insta-save keys and the M7 lever. The
/// palette is deliberately NOT stored (a stale SDL_Color* would dangle
/// across the deferral): the consumer re-sources it from the live
/// BattlescapeState at quiescence.
void armDeferredBattleSave(int origin, bool useTypeForm, int saveType, const std::string& filename, bool quitAfterSave);

/// SPEC 18 (r4 T4) M8, NEW test/introspection accessor: true while the
/// deferred-battle-save latch above is armed (a save was requested while
/// the battle was busy and has not yet been consumed at quiescence) -
/// TestServer's battle_state probe reports it as `coopSavePending` so a
/// test can prove a save was requested busy and written only at
/// quiescence.
bool coopDeferredBattleSavePending();

/// W2-H1 F448 (owner D136 = (b)), test-only introspection: a BATTLE-scoped
/// record of the deferral above that a test reads instead of racing the
/// latch's own window (a walk that drains within ~50 ms clears the latch
/// before the test's first battle_state reply arrives - F448/F460). Reported
/// by TestServer's `battle_state` next to `coopSavePending` as
/// `coopSaveDeferrals` / `coopSaveDeferredAt` / `coopSaveDeferredWrittenAt`;
/// never read by game logic. Reset with the latch by resetBattleAuthority().
///
/// How many saves armDeferredBattleSave() has deferred this battle.
int coopSaveDeferrals();

/// SDL_GetTicks() at the last deferral ("[coop-save] deferred until
/// quiescent"); 0 before any this battle.
std::uint32_t coopSaveDeferredAt();

/// SDL_GetTicks() at the last deferred write (the "[coop-save] written"
/// re-push at quiescence); 0 before any this battle.
std::uint32_t coopSaveDeferredWrittenAt();

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

/// W1-P14 (SPEC 13 (d) / REV E.1 (IR3-5) / audit D-4 second shape / WV-D11 /
/// WV-D47): PRESENTATION-ONLY read helper consulted at the named call sites in
/// SPEC 13's switched set (Map/MiniMapView/BattlescapeGame/BattlescapeState/
/// UnitWalkBState) in place of a bare BattleUnit::getVisible() read. Self-
/// guarded outside an active coop battle (falls straight through to
/// getVisible(), see connectionTCP.cpp for why that makes single player and
/// classic/SHARED co-op byte-identical). Inside a coop battle, ORs the
/// vanilla accessor with "this machine's seat commands @a u's faction" so a
/// gm2/gm3/gm4 seat commanding a non-player faction sees its own units even
/// though getVisible() alone would be false for them. MUST NEVER be called
/// from a sim, serializer or hash path - it is a presentation gate only, it
/// never writes BattleUnit::_visible and never feeds a hash bucket.
bool coopUnitVisibleHere(const BattleUnit* u);

/// W1-P14 (SPEC 13 (d) / REV E.1 (IR3-5) / audit D-4 second shape / WV-D11 /
/// WV-D47, FINDING B-3 / D-6): the side-relative replacement for
/// `getOriginalFaction() == FACTION_HOSTILE` at BattlescapeState::
/// updateSoldierInfo's spotted-enemy indicator. Routing that call site's
/// visibility read through coopUnitVisibleHere() alone, without also routing
/// this faction test, would make a gm2 client list its OWN aliens as spotted
/// enemies - so the two changes must land together (this commit). Self-
/// guarded the same way as coopUnitVisibleHere(): outside an active coop
/// battle it is the vanilla FACTION_HOSTILE test. PRESENTATION-ONLY, never a
/// sim/serializer/hash read.
bool coopUnitIsSpottedEnemyHere(const BattleUnit* u);

/// W1-P14 (SPEC 13 (d) / REV E.1 (IR3-5) / audit D-4 second shape / WV-D11 /
/// WV-D47): the side-relative replacement for `getSide() == FACTION_PLAYER`
/// at the WV-D11 gate sites (playableUnitSelected(), allowButtons(), and
/// Map::hiddenMovementShown()'s own faction term). Self-guarded like
/// coopUnitVisibleHere(): outside an active coop battle it is the vanilla
/// FACTION_PLAYER test; inside one it defers to
/// coopBattleAuthority().mySideActive(s). PRESENTATION-ONLY, never a
/// sim/serializer/hash read.
bool coopSideIsMine(const SavedBattleGame* s);

/// W1-P13c (WV-D55 / D-23, mechanism E55.1): returns true when the caller
/// must refuse - i.e. !coopMayCommand(u, s) - and, ONLY when the failing
/// term is the new baton term (traditional mode, Active, activeSeat !=
/// localSeat), presents STR_COOP_DENY_NOT_YOUR_GO through
/// CoopBattleUi::showDeny("not_your_go") (name from seatDisplayName()) and
/// bumps coopLocalExecutionBlocks()'s counter; for every other refusal it
/// stays SILENT exactly as before this packet. The direct replacement for
/// BattlescapeState::btnKneelClick's bare `if (!coopMayCommand(bu, _save))
/// return;` (E55.1), and also called by coopBlockLocalExecution() /
/// coopBlockWalkArm()'s existing refusal sites so the SAME presenter branch
/// covers every command-gate refusal in the game. Defined in
/// connectionTCP.cpp beside coopMayCommand().
bool coopRefuseIfNotMayCommand(const BattleUnit* u, const SavedBattleGame* s);

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
/// W1-P13d (WAVE1-RUNBOOK.md SPEC 12, REV E.60 / owner ruling D87 = (b)):
/// commandsUnit(u) is evaluated FIRST, so a seat-tagged unit - and, through
/// commandsUnit's own R5-P2 mcId override, a mind-controlled unit - behaves
/// exactly as before. A unit with NO seat tag (COOP_SEAT_NONE - every
/// AI-run alien, civilian and HWP) is additionally selectable on the HOST
/// (hostSim) and NEVER on a client, because the host is the executor of
/// every seat-less unit's AI. Before this, SavedBattleGame::
/// selectPlayerUnit()'s cycle could never land on a non-player unit, so
/// selectNextPlayerUnit() returned 0, BattlescapeGame::think() set
/// _endTurnRequested, handleAI() was never reached and NO enemy AI ran in
/// any coop battle (orch43c's F251, traced against a single-player control).
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

/// W2-P4 S-A (docs rewrite/prompts/w2p4_client_combat_intents.md (b)5 K1, as
/// amended by PR-Q1, PR-Q2 and PR-Q20): what W1-P6's coopBlockLocalExecution()
/// call at the top of BattlescapeGame::primaryAction's TARGETING arm becomes -
/// W1-P9's walk-arm gate split, generalised to the arm whose kinds now have a
/// wire verb. Reads the kind off @a s's live BattlescapeGame::getCurrentAction().
///   * A kind whose intercept EXISTS (S-A: the snap / aimed / auto shot - NOT
///     the spray start, i.e. an autoshot with a `sprayWaypoints` weapon under
///     Ctrl+Shift or an already-running spray targeting): OWNERSHIP + ACTIVE
///     SIDE only, on BOTH machines (`commandsUnit(u) && mySideActive(s)`), a
///     refusal bumping the same coopLocalExecBlocked counter. The hostSim term
///     moves down to the execution point (coopInterceptFireConfirm(),
///     CoopArbiter.h) and so does the baton term (PR-Q1: the local aiming
///     bookkeeping - confirm-fire first click - stays allowed off-turn, E54.1).
///     W2-P4 S-B adds the throw and the launcher (BA_THROW, BA_LAUNCH): the
///     launcher's waypoint clicks are local display, its execution point is
///     the launch button (launchAction's coopInterceptFireConfirm()).
///     W2-P4 S-C adds the psi amp (BA_PANIC / BA_MINDCONTROL / BA_USE with a
///     BT_PSIAMP item) and the mind probe (BA_USE with a BT_MINDPROBE item):
///     their execution points are coopInterceptPsiConfirm() (CoopArbiter.h).
///     W2-P4 S-E1 adds the spray (PR-Q20 ends): the spray start and its
///     waypoint clicks are local display, its execution point is the spray-fire
///     coopInterceptFireConfirm() (K2).
///   * Every other targeting kind keeps
///     coopBlockLocalExecution() exactly as before (PR-Q2): each later stage
///     lifts its own kinds, so no build between S-A and S-E has a local-sim path.
/// Self-guarded: false outside an ACTIVE co-op battle, so SP is byte-identical.
bool coopBlockTargetingArm(const BattleUnit* u, SavedBattleGame* s);

/// W1-P6: test-only introspection - how many times coopBlockLocalExecution()
/// has refused a local execution in this process. Reported by TestServer's
/// `event_state` as `coopLocalExecBlocked`; never read by game logic.
int coopLocalExecutionBlocks();

/// W2-P1 (thin-client tripwire, commit 1 of 2): test-only introspection for
/// the second player's "never simulates" guarantee. Three BATTLE-scoped values
/// (reset by resetBattleAuthority(), unlike coopLocalExecutionBlocks()'s
/// process-lifetime counter above), reported by TestServer's `event_state` as
/// `coopClientBStatePushes` / `coopClientBStateLastSite` /
/// `coopClientPanicSkipped`; never read by game logic.
///
/// Commit 1 adds the storage, these read accessors and the probes ONLY -
/// nothing increments them yet, so every value reads 0 / "" on its build (the
/// red the S1-S7 test, test_w2_thin_client_tripwire.py, proves). Commit 2's
/// writers live in connectionTCP.cpp beside coopBlockLocalExecution() and write
/// the storage directly:
///   * coopClientBStateTripwire(site, bs): `g_coopClientBStatePushes`
///     (fetch_add) and `g_coopClientBStateLastSite`, set to
///     "<site>:<typeid(*bs).name()>" - or "<site>:endTurnRequest" when
///     bs == nullptr - under `g_coopClientBStateLastSiteMutex`;
///   * coopSkipClientPanic(): `g_coopClientPanicSkipped` (fetch_add).
/// The storage is declared above resetBattleAuthority() in connectionTCP.cpp
/// (the same placement rule as g_coopPauseModalPending) so the teardown can
/// reset it; the string carries its own mutex because resetBattleAuthority()
/// is reachable from the UDP-monitor thread (the R4-P1 note at the top of this
/// header) while the pump thread reads it.
///
/// How many BState pushes the tripwire has refused on this machine this battle.
int coopClientBStatePushes();

/// The last refused push as "<site>:<dynamic type name>"; "" before any.
std::string coopClientBStateLastSite();

/// How many start-of-turn panic checks this machine has skipped this battle.
int coopClientPanicSkipped();

/// W2-P1 (thin-client tripwire, commit 2 of 2; plan F422/F432, SS3.6): the ONE
/// guard at every place a battle state (BState) becomes live in
/// BattlescapeGame - the first statement of the three helpers
/// statePushFront/statePushNext/statePushBack (@a bs == nullptr on
/// statePushBack is vanilla's end-turn request), and the statement BEFORE each
/// of the three direct `_states.push_back(new ProjectileFlyBState(...))` sites
/// (primaryAction's spray and fire branches, launchAction), where it runs
/// before the `new`, so @a bs is null there and nothing is built.
///
/// Inside an ACTIVE co-op battle on a machine that is NOT the host sim
/// (`isCoopBattle() && !coopBattleAuthority().hostSim`) it bumps
/// coopClientBStatePushes(), records coopClientBStateLastSite() as
/// "<site>:<typeid(*bs).name()>" (or "<site>:endTurnRequest" when @a bs is
/// null), logs ONE warning line, deletes @a bs if non-null and returns TRUE -
/// the call site then returns at once. Everywhere else (the host, SP, any
/// non-co-op battle) it returns FALSE and touches nothing, so vanilla is
/// byte-identical there.
///
/// A DETECTOR FIRST: a refused state's constructor has already run, so the
/// tripwire stops init()/think(), not constructor side effects. Every KNOWN
/// client-local simulation path is refused, skipped or sent as an intent
/// upstream (the action menu's item actions and the reload hotkey - W2-P4's
/// intercepts in CoopArbiter.h - and the panic check, coopSkipClientPanic()),
/// so a count here is a path nobody
/// has found yet, surfacing as a counter instead of a desync. Defined in
/// connectionTCP.cpp beside coopBlockLocalExecution().
bool coopClientBStateTripwire(const char* site, BattleState* bs = nullptr);

/// W2-P1: the start-of-turn panic check on a co-op CLIENT. BattlescapeGame::
/// think()'s player branch reads `_playerPanicHandled = coopSkipClientPanic()
/// ? true : handlePanickingPlayer();`. On a machine that is NOT the host sim
/// inside an active co-op battle (the same predicate as
/// coopClientBStateTripwire()) this bumps coopClientPanicSkipped() and returns
/// TRUE, so the check is marked handled without running
/// handlePanickingPlayer() (its RNG, dropItem and UnitWalkBState/
/// UnitPanicBState pushes). The host keeps resolving panic for every player
/// unit - W2-P3 streams it. FALSE everywhere else.
bool coopSkipClientPanic();

/// W1-P9 (WAVE1-RUNBOOK.md SS2.W2 / WV-D30, WV-D40 unchanged): the WALK ARM's
/// entry gate, which is what W1-P6's `coopBlockLocalExecution()` call in
/// BattlescapeGame::primaryAction's walk arm becomes now that the arm HAS a
/// wire verb.
///
/// THE GATE SPLITS; IT IS NOT WEAKENED. W1-P6's own comment at that call site
/// says the second term "simply refuses ... until W1-P9 turns it into a walk
/// INTENT" - this is that packet, so:
///   * THIS call keeps term 2 (OWNERSHIP + active side) and keeps it HERE, at
///     the top of the arm, because D6's ownership wall forbids a seat even
///     PREVIEWING a unit it does not command - and a co-op client now runs
///     vanilla's whole preview block (Pathfinding::calculate + previewPath,
///     both machine-local display scratch: `_path`/`_totalTUCost` are not
///     serialized and `Tile::_preview`/`_markerColor`/`_tuMarker` are not
///     serialized either, the same class of state W1-P6's own note cleared
///     `Map::resetObstacles()` on). A refusal bumps the SAME
///     coopLocalExecutionBlocks() counter W1-P6 minted, so every existing
///     "delivered then refused" proof keeps working for the cases that still
///     refuse.
///   * term 1 (hostSim - "only the simulating machine may EXECUTE") moves DOWN
///     to `coopInterceptWalkConfirm()` (CoopArbiter.h), which sits immediately
///     before `statePushBack(new UnitWalkBState(...))`. WV-D40 is enforced
///     there and is not relaxed by one line: a co-op client still never reaches
///     that push. What changes is what happens INSTEAD - a `bt_intent walk`
///     rather than a bare refusal.
/// Self-guarded exactly like coopBlockLocalExecution(): false outside an ACTIVE
/// co-op battle, so SP is byte-identical.
bool coopBlockWalkArm(const BattleUnit* u, const SavedBattleGame* s);

/// W1-P9: test-only introspection - how many times the WALK ARM has been
/// ENTERED on this machine (bumped by coopBlockWalkArm() before it decides
/// anything, in a co-op battle only). Reported by TestServer's `event_state` as
/// `coopWalkArmEntered`.
///
/// It is the DELIVERY PROOF W1-G1 criterion 4b needs after this packet.
/// Before W1-P9 that proof was "coopLocalExecBlocked went up", because a client
/// ground click could only ever be refused; now a click on a unit the client
/// DOES command is forwarded as an intent instead, and a click whose
/// pathfinder finds no route reaches the arm and legitimately does nothing at
/// all. Neither of those moves the refusal counter, so without this one the
/// "the click arrived" half of 4b would become unprovable - which is exactly
/// the vacuity the criterion exists to exclude. Never read by game logic.
int coopWalkArmEntries();

/// W1-P9: test-only introspection - how many `bt_intent walk` envelopes this
/// CLIENT has shipped from the walk-confirm hook (`coopInterceptWalkConfirm`).
/// Reported by TestServer's `event_state` as `coopWalkIntentsSent`. Together
/// with coopWalkArmEntries() above it separates "the click reached the arm and
/// became an ORDER" from "the click reached the arm and did nothing", which is
/// what a ground-click gate has to be able to tell apart once the arm has a
/// wire verb. Never read by game logic.
int coopWalkIntentsFromClick();

/// W1-P13a (WAVE1-RUNBOOK.md SPEC 9 / D48): the think() guard. ONE guarded
/// early return, `if (coopSuppressNonPlayerThink(_save)) return ret;`, as the
/// FIRST statement inside BattlescapeGame::think()'s
/// `if (_save->getSide() != FACTION_PLAYER)` branch (BattlescapeGame.cpp:233) -
/// with no selectable unit that branch reaches
/// `selectNextPlayerUnit(true, _AISecondMove) == 0` -> a client-LOCAL end
/// turn the moment side_transition lets the client change sides at all; with
/// a selectable unit it runs handleAI() locally, which has no coop gate.
///
/// Self-guarded like isCoopBattle()/coopMayCommand(): returns false (SP and
/// non-coop battle stay byte-identical) outside an active coop battle.
/// Inside one, returns true when either:
///   1. `!coopBattleAuthority().hostSim` - a client never runs non-player AI
///      or a client-local end-turn; that is entirely the host's job.
///   2. the currently active side (@a s->getSide()) has at least one HUMAN
///      seat mapped to it in the seat->faction store (iterate seats 0..3
///      through the public factionOf() - kMaxSeats is private and, per
///      RB-D17, is and stays 4) - an unmapped seat defaults to FACTION_PLAYER
///      (BattleAuthority::factionOf()), so this can only be true for a
///      non-player side when gm2+ actually assigned a human to it.
/// False (vanilla AI runs) in every other case - i.e. on the host, for an
/// AI-only side.
bool coopSuppressNonPlayerThink(const SavedBattleGame* s);

/// SPEC 19 (W1-P20) M2 Branch B: the HOST's per-seat store of the latest
/// battle_roster_contrib (BattleWire.h) received from that seat - test/
/// introspection + CoopState.cpp's coopMergeGuestContributions() reads.
/// Defined in connectionTCP.cpp beside the store itself; cleared by
/// resetBattleAuthority(). @a seat is 0..3 (RB-D17: kMaxSeats is private and
/// stays 4); out-of-range returns the empty/false/zero default.
///
/// How many guest-soldier YAML entries are currently stored for @a seat.
/// Reported by TestServer's `event_state` as `guestContrib.soldiers[seat]`
/// (S1's vacuity guard: the roster actually travelled).
int coopGuestContribStoredCount(int seat);

/// Whether @a seat's stored entry names the craft (@a craftId + @a
/// craftType) coopMergeGuestContributions() is about to generate for - the
/// match coopMergeGuestContributions() itself needs before it deserialises
/// anything stored for that seat.
bool coopGuestContribCraftMatches(int seat, int craftId, const std::string& craftType);

/// The @a index'th stored guest Soldier YAML for @a seat (Soldier::save()'s
/// wire form), or an empty string if out of range - coopMergeGuestContrib-
/// utions() deserialises each of these via Soldier::load().
const std::string& coopGuestContribSoldierYaml(int seat, int index);

/// The CLIENT's own count of guest soldiers in the last battle_roster_contrib
/// census it computed (connectionTCP::sendGuestRosterContrib()) - 0 if none
/// (host, SHARED campaign, or no SEPARATE guest waiting yet). Reported by
/// TestServer's `event_state` as `guestContrib.sent` (S1's vacuity guard,
/// the client-side half).
int coopGuestContribLastSentCount();

/// W2-P4r (owner D149 = (a); spec rewrite/prompts/w2p4r_research_list.md
/// (b)1): true when a research-based weapon check must read the unit OWNER's
/// research - a live co-op battle (isCoopBattle(): single player is never
/// separate) in a campaign (NEW BATTLE sets it false) that is not SHARED,
/// with the host's "Enable Research Sync (Separate)" OFF. Evaluated on EVERY
/// call and never cached: the option can change mid-battle (#185).
bool coopResearchSeparate(Game* game);

/// W2-P4r (b)5: vanilla SavedGame::isResearched(@a req) answered from @a
/// seat's research. Outside coopResearchSeparate(), for a seat outside 1..3
/// (seat 0 and seat-less units: the live world), in debug mode, or when no
/// list is stored for the seat, it is the live world's answer - unchanged.
/// Otherwise vanilla's own function on the seat's research-only world.
bool coopSeatIsResearched(Game* game, int seat, const std::vector<const RuleResearch*>& req);

/// W2-P4r (b)5 + PR-R5: the same routing around vanilla
/// SavedGame::isManaUnlocked(@a mod) (@a mod = the Mod* the vanilla site
/// passes).
bool coopSeatIsManaUnlocked(Game* game, int seat, Mod* mod);

/// W2-P4r (b)11 (test introspection; TestServer `event_state.researchMode`):
/// whether a research list is stored for @a seat (0..3; seat 0 never is),
/// how many known topics it holds, and how many names it could not resolve.
/// Each takes the store's mutex (PR-R8).
bool coopSeatResearchStored(int seat);
int coopSeatResearchCount(int seat);
int coopSeatResearchUnknown(int seat);

} // namespace OpenXcom
