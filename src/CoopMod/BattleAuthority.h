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

// coop: the battle-save hook pair below takes
// YAML nodes. Forward-declared, never included - this header is deliberately
// dependency-light (see the class comment) and the only two call sites
// (SavedBattleGame::save/::load) already have the complete types.
namespace YAML { class YamlNodeReader; class YamlNodeWriter; }

namespace OpenXcom
{

class ArticleDefinition;
class BattleUnit;
class Game;
class Mod;
class RuleResearch;
class BattleState;
class SavedBattleGame;
class SavedGame;

/**
  * coop: the session's TURN MODE. Chosen by the HOST, stamped onto every
  * battle_offer and MIRRORED by the client - a client's own setting is
  * irrelevant: the mode is decided once per session.
 *
 * Parallel    - all seats on the active side act simultaneously, individual
  *               actions serialized through host admission. THE DEFAULT.
 * Traditional - one seat commands at a time; END TURN passes the baton to the
 *               next seat; the last pass closes the side.
 *
  * This type only carries, stores and reports the mode; code that branches on
  * it reads BattleAuthority::turnMode.
 */
enum class CoopTurnMode { Parallel, Traditional };

/// The battle_offer wire spelling of @a m: "parallel" or "traditional". Never any
/// other string - this is what goes on battle_offer.
const char* coopTurnModeName(CoopTurnMode m);

/// Parse a battle_offer wire value. ANY value other than "traditional" - including
/// an empty string, i.e. an ABSENT key - is PARALLEL. That is a deliberate
/// backwards-compatible degrade, not leniency: an older host sends no key at all
/// and must be understood as the classic model.
CoopTurnMode coopTurnModeFromString(const std::string& s);

/// The HOST's remembered preference, normalized: Options::CoopTurnMode run
/// through coopTurnModeFromString(). Read ONLY by the host, and only when it
/// builds an offer - never by a client, and never to decide behaviour.
CoopTurnMode coopSessionTurnModeFromOptions();

/// BATTLE-SAVE HOOK. The thin
/// coop-gated pair `SavedBattleGame::save`/`::load` calls, so a battle save
/// carries the mode it was PLAYED in and a mid-battle resume comes back in that
/// mode even after a full host restart - which is why the engine never has to
/// support a parallel->traditional transition through save/load.
///
/// SP AND NON-COOP STAY BYTE-IDENTICAL: coopSaveTurnMode() writes NOTHING unless
/// this is an active co-op battle, so the key is simply ABSENT from every SP
/// save. The CAMPAIGN save block deliberately does not carry the mode.
///
/// The key is on `SharedEcon.cpp`'s saveBlobExcludedTopKey list so session
/// configuration never rides the saveBlob hash; both machines agree on the value
/// via the offer anyway.
///
/// On a resume, the `resumed:true` offer carries the mode loaded here instead
/// of Options::CoopTurnMode.
void coopSaveTurnMode(YAML::YamlNodeWriter& writer);
void coopLoadTurnMode(const YAML::YamlNodeReader& reader);

/// the BATTLE-SAVE hook pair for the
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

/// the BATTLE-SAVE hook pair for the
/// traditional-mode baton holder (CoopEndTurn::batonSeat(), HOST-only, -1 in
/// parallel mode or before the entry tally). Presence-gated both ways; reads
/// back into the BattleAuthority::activeSeat MIRROR only - restoring the
/// live CoopEndTurn baton holder on a disk resume (with a degrade for
/// an absent/invalid key) is CoopEndTurn::onBattleResumed()'s job.
/// SP and parallel-mode saves write nothing meaningful in
/// practice (activeSeat is -1 there too), but the key is still written only
/// inside a coop battle - byte-identical outside one. Hash-excluded, same
/// list as coopTurnMode.
void coopSaveActiveSeat(YAML::YamlNodeWriter& writer);
void coopLoadActiveSeat(const YAML::YamlNodeReader& reader);

/// coop: the HOST's true
/// SavedBattleGame::_itemId, carried in the BATTLE save block so the machine
/// that LOADS a coop blob adopts it verbatim instead of re-deriving
/// max(item id)+1 - a derivation that is provably wrong whenever generation
/// allocated an id that did not survive into the document.
/// Key `coopItemIdCtr`, on saveBlobExcludedTopKey so it
/// never rides the saveBlob hash; the `itemIdCtr` BUCKET still compares it.
void coopSaveItemIdCtr(YAML::YamlNodeWriter& writer, const SavedBattleGame* battle);
void coopLoadItemIdCtr(const YAML::YamlNodeReader& reader, SavedBattleGame* battle);

/// the unit-record hook pair for
/// BattleUnit::_spawnUnitFaction on a unit WITHOUT a spawn unit. Vanilla's BattleUnit::save writes the key only
/// inside `if (_spawnUnit)` and ::load reads it only there, so a machine that builds a unit from a record (the
/// client's `unitsAdded` materialization, a rejoin, resume or repair blob) keeps the default FACTION_HOSTILE where
/// the host holds the faction SavedBattleGame::convertUnit copied from the victim (a player-side conversion), and
/// the `synced` bucket mixes it. coopSaveSpawnUnitFaction() (BattleUnit::save, after vanilla's spawn block) writes
/// the key for such a unit only when its value is not FACTION_HOSTILE and only in a co-op battle past Idle (the
/// coopSaveItemIdCtr guard: the offer blob is built at Handshake), so an SP save is byte-identical.
/// coopLoadSpawnUnitFaction() (BattleUnit::load, after vanilla's spawn block) is presence-gated: it reads the key
/// only from a record WITHOUT a `spawnUnit` key (otherwise vanilla's branch read it, or ignored a bugged type); an
/// SP save never has the key there.
void coopSaveSpawnUnitFaction(YAML::YamlNodeWriter& writer, const BattleUnit* unit);
void coopLoadSpawnUnitFaction(const YAML::YamlNodeReader& reader, BattleUnit* unit);

/// the read-back of the record fields the
/// Soldier constructor ignores. SavedBattleGame::load builds a unit whose id is a geoscape soldier's through the Soldier
/// constructor (original faction FACTION_PLAYER, type "SOLDIER"); only the rules constructor takes the record's
/// `originalFaction`, and BattleUnit::load reads neither it nor `genUnitType`. So the PvE2 (gamemode 4) X-COM soldiers
/// assignSeatsAndFactions() turns FACTION_HOSTILE (and re-types MALE_ / FEMALE_CIVILIAN) at generation would load
/// as player-original SOLDIERs on every machine that builds the battle from a document: the client's offer, rejoin, repair
/// and stage blobs, the host's own disk resume. Called from BattleUnit::load after coopLoadSpawnUnitFaction: on a soldier-linked unit
/// it restores the record's original faction (SavedBattleGame::load's own default: the unit's faction) and its
/// type. No co-op guard and no new key: every save vanilla writes holds FACTION_PLAYER and "SOLDIER" for a soldier-linked
/// unit, and co-op gamemodes 0-3 never change either, so the call changes nothing outside PvE2.
void coopLoadSoldierUnitRecord(const YAML::YamlNodeReader& reader, BattleUnit* unit);

/// coop: the unit-record hook pair for the two values the
/// rules constructor derives from the unit's ORIGINAL faction and never saves: the dark-vision distance
/// (BattleUnit::updateArmorFromNonSoldier) and the maximum armor (the difficulty adjustment, BattleUnit::adjustStats).
/// PvE2's swap (assignSeatsAndFactions) changes the original faction after the host built the unit, so a machine that builds
/// it from a document (the client's offer, rejoin, repair and stage blobs, a `unitsAdded` record, the host's own resume)
/// would rebuild other values. coopSaveBuiltValues() (BattleUnit::save, after coopSaveSpawnUnitFaction) writes both for every unit not
/// linked to a geoscape soldier, only in a co-op battle past Idle (the coopSaveItemIdCtr guard), so an SP save is
/// byte-identical; coopLoadBuiltValues() (BattleUnit::load, after coopLoadSoldierUnitRecord) is presence-gated.
void coopSaveBuiltValues(YAML::YamlNodeWriter& writer, const BattleUnit* unit);
void coopLoadBuiltValues(const YAML::YamlNodeReader& reader, BattleUnit* unit);

/// coop: a mid-battle co-op
/// save made by an OLDER version (no coopBattleProtocol in its header: older versions never write one) resumes on this
/// build. coopOlderBattleConvertible() is SavedGame::load()'s gate: true for the game modes the load accepts - classic and
/// SHARED co-op (0 / 1) and PvP gm2 (2) are converted, a PvE2 (4) campaign save loads unconverted (its RESUME is refused);
/// every other unstamped battle save is refused. coopConvertOlderBattleSave()
/// runs on the HOST's menu load right after the battle block loads (@a body = the save's body document):
///  (0) every partner world the load restored (coopFilesHost "host_" entries): its battle snapshot stripped and its mirrors
///      of the host's soldiers dropped, as older versions' save upgrader treats a legacy partner world (SchemaStep1to2);
///  (1) seat tags - older versions write `coop` 0 / 1 on EVERY unit, the key this build reads as the seat tag: a unit of
///      another original faction is unseated, a player-side unit with a soldier keeps seat 0 / 1, any other player-side
///      unit is the host's;
///      a PvP gm2 save: the X-COM side on seat 0, the alien side on seat 1 without its AI module, others unseated;
///  (2) the turn mode it was played in, only when the battle block has no coopTurnMode: the campaign-block
///      `coop_parallel_turns` true = parallel, false or absent = traditional (v2.0.x played alternating turns);
///  (3) the mission deployment, only when the battle block has no coopDeployment, resolved as
///      CoopHandshake::mintMissionLabels() resolves it.
/// One [coop-convert] log line. A save this build wrote carries the stamp and is never converted.
bool coopOlderBattleConvertible(int gamemode);
void coopConvertOlderBattleSave(SavedGame* save, Mod* mod, const YAML::YamlNodeReader& body);

/// coop: true when @a body (a save's body
/// document) is a classic co-op Custom Battle saved mid-battle by an OLDER version - a battle block without the keys this build
/// writes in every co-op battle (coopTurnMode, coopItemIdCtr), game mode 0 / 1, a unit of another original faction carrying the
/// `coop` key (older versions write it on EVERY unit, this build only on a seated one) and a unit tagged 1 (the second
/// player's). A Custom Battle save has no header `coop`, so SavedGame::load()'s campaign gate never sees it; the load then runs
/// coopConvertOlderBattleSave() on it. A release single-player save loads as saved. The game mode may be 0-4: PvP (2 / 3)
/// and PvE2 (4) saves convert by their mode's arm.
bool coopOlderCustomBattleSave(const YAML::YamlNodeReader& body);

/// coop test/introspection, like coopSpotEvsEmitted()/coopSpotEvsApplied()
/// precedent (CoopArbiter.h): how many times THIS machine's coopLoadItemIdCtr
/// actually adopted the carried counter (the last carried value stored
/// through getCurrentItemId() - present whenever the key is present and
/// carried >= derived, whether or not the two agreed), and how many times it
/// REFUSED to (the carried < derived branch, which must never fire in a
/// clean two-machine run). "Adopted" is a VALUE, not a
/// boolean, so a positive-control test can see an adopt that never happened
/// (value stays 0) as distinct from one that did.
int coopItemIdCtrAdopted();
unsigned int coopItemIdCtrRefused();

/**
 * coop: the ONE battle-authority
 * object - kill-by-construction of the legacy getHost()/onTcpHost
 * turn-token tangle for battle logic. A single global instance is DEFINED
 * in connectionTCP.cpp; every battle-logic site is meant to read
 * coopBattleAuthority() instead of branching on getHost() (N-player
 * guardrail: no new getHost() branches in battle logic).
 *
 * Deliberately dependency-light, same discipline as CoopSeat.h:
 * BattleUnit/SavedBattleGame are forward-declared only here - their full
 * definitions are only needed in the connectionTCP.cpp method bodies, which
 * already include both. This keeps the header safe to include from thin
 * hook sites in vanilla battle files without dragging the
 * net layer (connectionTCP.h/Game.h/BattlescapeGame.h) in - the same
 * "BattleUnit.h drags net layer" problem CoopSeat.h already avoids for the
 * seat tag.
 *
  * CROSS-THREAD SAFETY: handleUdpRemotePeerLost() (connectionUDP\
 * connection_rendezvous_glue.cpp) can call clearNetworkSessionQueues() -> ...
 * -> resetBattleAuthority() from the UDP-monitor thread (its own doc comment:
 * "may run from the UDP monitor thread"), while the main/pump thread reads
  * and writes these same fields throughout CoopArbiter/CoopHandshake.
  * offerBattle()/finishLoad() populate the fields mid-battle from the main
  * thread while a peer-lost teardown can race them, so every field below
 * that crosses threads (hostSim/localSeat/phase/battleId, and the
 * _seatFaction store) is std::atomic. This is a mutex-free guard rather than
 * a mutex because every existing read/write
 * call site (CoopArbiter, the self-test, this header's own doc
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
	/// IMMUTABLE per battle: set once by initBattleAuthority() below
	/// from connectionTCP::getServerOwner(). The mutable getHost()/
	/// onTcpHost token is legacy-dead for battle logic - never branch battle
	/// code on getHost(). std::atomic: see the cross-thread safety note
	/// above the enum.
	std::atomic<bool> hostSim{false};

	/// This machine's seat. Set once by initBattleAuthority() from
	/// connectionTCP::localSeat(). -1 (unset) at Idle.
	std::atomic<int> localSeat{-1};

	/// Battle lifecycle phase. Idle until the handshake calls
	/// initBattleAuthority() (-> Handshake) and later stamps Active on a
	/// successful battle_ready; the teardown chokepoint runs the Ended ->
	/// teardown -> Idle transition (resetBattleAuthority() below provides the
	/// reset itself). Public field, not a setter: the handshake and the
	/// teardown transition it with a plain assignment.
	std::atomic<CoopBattlePhase> phase{CoopBattlePhase::Idle};

	/// Host-minted at battle_offer; 0 = none yet.
	std::atomic<std::uint32_t> battleId{0};

	/// coop: THIS BATTLE's turn mode - the runtime mirror of the session
	/// choice. Set on the HOST when it builds the offer and on the CLIENT from
	/// `battle_offer.turnMode`; reset to the default (Parallel) by
	/// resetBattleAuthority(). It lives HERE rather than in a bare static
	/// because it is battle-scoped state with a teardown reset, and because
	/// battle code already reads this object. std::atomic for the same
	/// cross-thread reason as the four fields above.
	std::atomic<CoopTurnMode> turnMode{CoopTurnMode::Parallel};

	/// the seat that currently HOLDS THE BATON in
	/// traditional mode, as last HONOURED by this machine - i.e. the activeSeat
	/// of a bt_end_turn_tally whose `turn` matched this machine's last APPLIED
	/// side_transition counter. -1 = no baton (parallel mode, or before the
	/// first tally of a side). Reset to -1 by resetBattleAuthority().
	std::atomic<int> activeSeat{-1};

	/// coop: the ON/OFF switch for the
	/// own-side visibility rule, behind the test-only `battle_visibility_rule`
	/// hook. coopUnitVisibleHere() is its ONLY reader - it exists so a test can
	/// prove the rule is hash-free by comparing every bucket with it ON and OFF.
	/// Default TRUE (the rule is live in a real game); reset to TRUE by
	/// resetBattleAuthority(). std::atomic for the same cross-thread reason as
	/// activeSeat above.
	std::atomic<bool> visibilityRuleOn{true};

	/// the ONE pending tally. A
	/// bt_end_turn_tally whose `turn` is AHEAD of this machine's last APPLIED
	/// side_transition counter (the unordered battle lane beating the
	/// seq-ordered apply queue) is BUFFERED
	/// here as the pair (turn, activeSeat) instead of being dropped, and
	/// honoured the moment onClientAppliedSideTransition() advances the
	/// counter to it. A newer pending pair replaces an older one; a tally
	/// older than the counter never overwrites one. -1 = nothing pending.
	/// Reset to -1 by resetBattleAuthority() and on every honoured apply.
	/// std::atomic for the same cross-thread reason as activeSeat above.
	std::atomic<int> pendingTallyTurn{-1};
	std::atomic<int> pendingTallyActiveSeat{-1};

	/// coop: set the moment this machine's own
	/// hash-mismatch detector (CoopHashCheck::verify, BattlePump.h) latches a
	/// desync - "freeze battle input" on a mismatch.
	/// Distinct from BattlePump.h's g_battleFrozen (the seq-gap apply-
	/// queue halt, a low-level plumbing flag): this one is the
	/// BattleAuthority-level signal higher gating code (the client
	/// intent tracker/intercept sites) is meant to read. A hash mismatch
	/// ALSO sets g_battleFrozen (halting the apply queue too) - the two flags
	/// are set together on a mismatch, never independently, but kept
	/// separate because they answer different questions ("is the low-level
	/// apply queue paused" vs "has this battle desynced"). NO partial
	/// repair, never cleared mid-battle.
	std::atomic<bool> desyncFrozen{false};

	/// coop: latched when a mid-`Active`-battle peer LEAVE
	/// (graceful `disconnect_to_menu` or a liveness/socket-loss detection)
	/// spares the authority reset instead of tearing the battle down to
	/// Idle - the battle, `battleId`, seat map, `turnMode` and baton all
	/// survive under it (see connectionTCP::disconnectTCP's host branch and
	/// its UDP twin, handleUdpRemotePeerLost()). Cleared back to false by
	/// resetBattleAuthority() (same discipline as desyncFrozen above) and by
	/// a successful rejoin-restream. Reported additively
	/// on `battle_state.authority.peerAbsent` (TestServer.cpp) so a test can
	/// assert "paused, not torn down" without inferring it from the dialog
	/// alone. std::atomic for the same cross-thread reason as desyncFrozen
	/// (the UDP-monitor-thread race noted above the enum).
	std::atomic<bool> peerAbsent{false};

	/// coop: true when the CURRENT peerAbsent pause was
	/// entered via a graceful `battle_leave{seat,reasonKey}` (the departing
	/// seat's own deliberate `disconnect_to_menu`, sent to the host BEFORE
	/// its transport goes down) rather than a bare liveness/socket-loss
	/// detection. This changes NOTHING about detection
	/// latency - both paths already raise the pause dialog in ~0.1s - its
	/// only value is letting CoopState::waitingTitle() NAME the
	/// reason instead of always reading as a silent connection loss.
	/// Cleared by resetBattleAuthority() (same discipline as peerAbsent
	/// above) and by a successful rejoin-restream's onReady, so a
	/// later, separate pause on the same battle never inherits a stale
	/// label. std::atomic for the same cross-thread reason as peerAbsent.
	std::atomic<bool> peerLeftByChoice{false};

	/// Seat -> FACTION_* lookup, backed by the private store below. The store
	/// starts empty and factionOf() falls back to FACTION_PLAYER for any
	/// unmapped/out-of-range seat (classic and SHARED co-op, where every valid
	/// seat is on the player side). setSeatFaction() lets the handshake init
	/// populate the real seat map.
	int factionOf(int seat) const;

	/// coop: true iff @a seat (0..3) has an entry in the seat->faction
	/// store. factionOf() cannot answer this - it falls back to FACTION_PLAYER
	/// for an unmapped seat. Read-only.
	bool seatMapped(int seat) const;

	/// True iff the currently active side in @a s (SavedBattleGame::
	/// getSide()) is the faction this machine's localSeat commands
	/// (factionOf(localSeat)). False if @a s is null.
	bool mySideActive(const SavedBattleGame* s) const;

	/// True iff this machine currently commands @a u: the unit's seat tag
	/// (BattleUnit::getCoopSeat()) equals localSeat. False if @a u is null.
	// coop mcId override: "controlled" is faction != originalFaction (NOT a raw mcId
	// check - mcId also gets set by a successful panic with no control
	// transfer, TileEngine.cpp:4774, and is never cleared on revert). When
	// controlled, the commanding seat is the seat of the getMindControllerId()
	// unit; if that unit no longer resolves (dead/gone), ownership falls to
	// host/AI - only seat 0
	// commands it. A non-MC unit falls straight through to its own seat tag.
	// Body in connectionTCP.cpp.
	bool commandsUnit(const BattleUnit* u) const;

	/// the same rule for an explicit
	/// @a seat instead of this machine's localSeat - the HOST's admission of a
	/// REMOTE seat's intent (onIntent's not_your_unit). The controller rule
	/// unchanged: a mind-controlled unit is commanded by its controller's seat
	/// (seat 0 when the controller no longer resolves). commandsUnit(u) is
	/// commandsUnit(u, localSeat).
	bool commandsUnit(const BattleUnit* u, int seat) const;

	/// True iff this seat commands no player-side faction right now:
	/// localSeat is unset (<0), or factionOf(localSeat) is not the player
	/// side. Minimal by construction (this method takes no SavedBattleGame
	/// parameter to check "currently active side" against) - in classic and
	/// SHARED co-op every valid seat is FACTION_PLAYER, so this reduces to
	/// "localSeat < 0"; a PvP seat map adds non-player-controlled seats.
	bool isSpectator() const;

	/// coop: minimal seat->faction store backing factionOf()
	/// Out-of-range seats are ignored (no-op).
	void setSeatFaction(int seat, int faction);

	/// Clears the seat->faction store back to "everything unmapped" (every
	/// seat falls back to factionOf()'s FACTION_PLAYER default).
	void resetSeatFactions();

private:
	static const int kMaxSeats = 4; // COOP_SEAT_0..COOP_SEAT_3
	static const int kUnmapped = -1;
	// Cross-thread safety (see the note above the enum): std::atomic, same
	// reasoning as hostSim/localSeat/phase/battleId above - resetSeatFactions()
	// is reachable from resetBattleAuthority(), which the UDP-monitor thread
	// can call via handleUdpRemotePeerLost().
	std::atomic<int> _seatFaction[kMaxSeats] = { kUnmapped, kUnmapped, kUnmapped, kUnmapped };
};

/// The one global BattleAuthority instance. Defined in
/// connectionTCP.cpp.
BattleAuthority& coopBattleAuthority();

/// Called at the handshake transition. Sets hostSim (a ONE-TIME read of
/// connectionTCP::getServerOwner() - hostSim itself stays immutable for the
/// rest of the battle after this) and localSeat (from
/// connectionTCP::localSeat()), stamps @a battleId, moves phase to
/// Handshake, and clears the seat->faction store so the
/// caller can repopulate it via setSeatFaction().
void initBattleAuthority(std::uint32_t battleId);

/// Called at the battle-teardown chokepoint. Resets the singleton back to its Idle default
/// (hostSim=false, localSeat=-1, phase=Idle, battleId=0, seat->faction
/// store cleared, turnMode=Parallel).
void resetBattleAuthority();

/// connectionTCP::getCoopStatic() && phase == Active. Deliberately NOT
/// defined inline in this header: connectionTCP::getCoopStatic() needs
/// connectionTCP.h, which is the heavy net-layer header this file exists to
/// avoid pulling in (same reasoning as the class forward-declarations
/// above) - defined instead in connectionTCP.cpp next to
/// coopBattleAuthority().
bool isCoopBattle();

/// coop: the ONE shared
/// quiescence predicate - "the host BState stack drains (!isBusy()) AND no
/// pending origin-chain evs remain (CoopArbiter::currentActionId()==0)",
/// WITH the isBattlescapeStateLive() live-state guard around the
/// getBattleState()/getBattleGame()/isBusy() reads (an un-live state counts
/// as "no live battle", i.e. quiescent - never re-derive a bare !isBusy(),
/// anywhere). EXTRACTED from the pause-modal consumer
/// (connectionTCP.cpp, updateCoopTask()) so BOTH that latch
/// (g_coopPauseModalPending) and the deferred-battle-save latch
/// (g_coopDeferredBattleSave) read the SAME gate. Defined in
/// connectionTCP.cpp next to isCoopBattle().
bool coopBattleQuiescent();

/// coop: true once this machine saw a desync in the
/// battle it is in or was last in (the second player raised one; the host received a report) - kept across the
/// automatic repair, cleared when a battle with another id starts. Read by TestServer's desync probes.
bool coopDesyncSeenLatched();
/// coop: a partner drop ends every repair state (the peer-leave pause takes over); from CoopSession::onClientDrop().
void coopResyncOnPeerDrop();
/// coop: true after the last rejoin or repair offer was refused or its copy did not match,
/// until a later offer, a drop or a new battle - CoopState::waitSatisfied() then withholds RESUME.
bool coopResumedOfferFailed();
/// coop: the host waiting screen's repair wording - 0 none, 1 a repair runs, 2 a repair failed.
int coopResyncTitleState();

/// coop: arm the deferred mid-battle coop save latch, called
/// from SaveGameState::think() the moment it observes isCoopBattle() &&
/// !coopBattleQuiescent() - i.e. every mid-battle coop save funnels through
/// this ONE chokepoint (quick-save/insta-save keys, the pause-menu Save,
/// ListSave SAVE & QUIT, the test command `save_game_ui type:
/// "quick_battle"`), regardless of how busy-gated each trigger's own UI
/// happens to be. `origin` is OptionsOrigin and `saveType` is SaveType
/// (Menu/SaveGameState.h), both passed as their own underlying int so this
/// header stays dependency-light exactly like isCoopBattle() above -
/// connectionTCP.cpp casts them back at the ONE consume site (the
/// pump point, beside the pause-modal consumer). `useTypeForm`
/// selects which SaveGameState constructor the consumer re-invokes: false =
/// the filename-form ctor (origin, filename, palette, quitAfterSave) - used
/// by ListSave SAVE & QUIT; true = the type-form ctor (origin, SaveType,
/// palette) - used by the quick-save/insta-save keys and the test command. The
/// palette is deliberately NOT stored (a stale SDL_Color* would dangle
/// across the deferral): the consumer re-sources it from the live
/// BattlescapeState at quiescence.
void armDeferredBattleSave(int origin, bool useTypeForm, int saveType, const std::string& filename, bool quitAfterSave);

/// coop test/introspection accessor: true while the
/// deferred-battle-save latch above is armed (a save was requested while
/// the battle was busy and has not yet been consumed at quiescence) -
/// TestServer's battle_state probe reports it as `coopSavePending` so a
/// test can prove a save was requested busy and written only at
/// quiescence.
bool coopDeferredBattleSavePending();

/// coop test-only introspection: a BATTLE-scoped
/// record of the deferral above that a test reads instead of racing the
/// latch's own window (a walk that drains within ~50 ms clears the latch
/// before the test's first battle_state reply arrives). Reported
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

/// coop input-gating combinator: ONE predicate for 'I may command this unit':
/// my seat commands it AND my
/// faction side is active. Self-guarded like isCoopBattle() - returns
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

/// coop: PRESENTATION-ONLY read helper consulted at the named call sites
/// (Map/MiniMapView/BattlescapeGame/BattlescapeState/
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

/// coop (the PvP model's per-side fog): does
/// @a faction's side see @a u now? FACTION_HOSTILE only, while a human seat commands it (gm2 / gm3): on the HOST the
/// union of that side's live units' own visible lists (vanilla's TileEngine::calculateUnitsInFOV keeps them there); on
/// a CLIENT the list the host's last envelope carried as `seen` (CoopEmit::sendEv), its own lists until the first
/// one arrives. False for every other faction and outside an active co-op battle. PRESENTATION-ONLY (coopUnitVisibleHere()'s
/// non-player branch and coopHumanKnowsTarget() read it): never a sim, serializer or hash read; in no hash
/// bucket.
bool coopSideSeesUnit(int faction, const BattleUnit* u);

/// coop: the side-relative replacement for
/// `getOriginalFaction() == FACTION_HOSTILE` at BattlescapeState::
/// updateSoldierInfo's spotted-enemy indicator. Routing that call site's
/// visibility read through coopUnitVisibleHere() alone, without also routing
/// this faction test, would make a gm2 client list its OWN aliens as spotted
/// enemies - so the two must change together. Self-
/// guarded the same way as coopUnitVisibleHere(): outside an active coop
/// battle it is the vanilla FACTION_HOSTILE test. PRESENTATION-ONLY, never a
/// sim/serializer/hash read.
bool coopUnitIsSpottedEnemyHere(const BattleUnit* u);

/// coop: the side-relative replacement for `getSide() == FACTION_PLAYER`
/// at the side gate sites (playableUnitSelected(), allowButtons(), and
/// Map::hiddenMovementShown()'s own faction term). Self-guarded like
/// coopUnitVisibleHere(): outside an active coop battle it is the vanilla
/// FACTION_PLAYER test; inside one it defers to
/// coopBattleAuthority().mySideActive(s). PRESENTATION-ONLY, never a
/// sim/serializer/hash read.
bool coopSideIsMine(const SavedBattleGame* s);

/// coop (PvP off-turn: the hidden-movement screen except where own units have LOS): Map::hiddenMovementShown()'s
/// first term. Vanilla's own term (the selected
/// unit is visible here) outside an active co-op battle, in classic / SHARED co-op (gamemode not 2 / 3) and on this
/// machine's own side; off its own side in PvP, the unit acting in the running order (the host's action context, a
/// client's open action) is visible here. PRESENTATION-ONLY; nothing written.
bool coopHiddenMovementActorTerm(const SavedBattleGame* s);

/// coop: returns true when the caller
/// must refuse - i.e. !coopMayCommand(u, s) - and, ONLY when the failing
/// term is the new baton term (traditional mode, Active, activeSeat !=
/// localSeat), presents STR_COOP_DENY_NOT_YOUR_GO through
/// CoopBattleUi::showDeny("not_your_go") (name from seatDisplayName()) and
/// bumps coopLocalExecutionBlocks()'s counter; for every other refusal it
/// stays SILENT. The direct replacement for
/// BattlescapeState::btnKneelClick's bare `if (!coopMayCommand(bu, _save))
/// return;`, and also called by coopBlockLocalExecution() /
/// coopBlockWalkArm()'s existing refusal sites so the SAME presenter branch
/// covers every command-gate refusal in the game. Defined in
/// connectionTCP.cpp beside coopMayCommand().
bool coopRefuseIfNotMayCommand(const BattleUnit* u, const SavedBattleGame* s);

/// coop selection-cycle predicate: the CoopMod half of the
/// SavedBattleGame::selectPlayerUnit() filter call (ONE guarded filter call
/// so the selection cycle SKIPS units this machine's seat does not command).
/// Self-guarded (true outside an active coop battle); inside one, equals
/// coopBattleAuthority().commandsUnit(u). Deliberately does NOT also check
/// mySideActive() - selectPlayerUnit() already restricts candidates to
/// SavedBattleGame::_side via BattleUnit::isSelectable(), so a candidate
/// reaching this predicate is already on the currently active side; the
/// active-side check belongs to the action-gating hooks (coopMayCommand()
/// above), not to cycling among already-active-side candidates. Defined in
/// connectionTCP.cpp next to isCoopBattle().
/// commandsUnit(u) is evaluated FIRST, so a seat-tagged unit - and, through
/// commandsUnit's own mcId override, a mind-controlled unit - behaves
/// exactly as before. A unit with NO seat tag (COOP_SEAT_NONE - every
/// AI-run alien, civilian and HWP) is additionally selectable on the HOST
/// (hostSim) and NEVER on a client, because the host is the executor of
/// every seat-less unit's AI. Without it, SavedBattleGame::selectPlayerUnit()'s
/// cycle could never land on a non-player unit, so selectNextPlayerUnit()
/// returned 0, BattlescapeGame::think() set _endTurnRequested, handleAI() was
/// never reached and NO enemy AI ran in any coop battle.
/// That host exception is for AI-run seat-less units only; a seat-less unit that is mind-controlled (faction != original
/// faction) goes to the controller test, so the host never selects an alien its partner controls.
bool coopMaySelectUnit(const BattleUnit* u);

/// coop (issue #126): the in-battle gift as a host-checked order. coopGiftOrder() is the giver's entry (the gift menu,
/// through connectionTCP::giftBattleUnit / giftSoldier): the host applies its own gift, a client sends the untracked
/// `gift {target}` intent. coopApplyGift() is the HOST's check and apply (onIntent's `gift` branch, the host's own
/// gift): it refuses silently (logged; counted as denied for an intent) a PvP battle, the pre-battle equipment phase, a
/// bad target, a unit the giver does not own (its seat tag: a mind-controlled unit is not its controller's to give), a
/// unit not alive on the player side and a unit acting in an open action context; otherwise it writes the seat tag
/// and the soldier's owner (in every mode), sets the `gift` latch (the delta's `seat` reaches the
/// partner in stream order) and records the change. coopGiftNoteSeatChange() records a seat change for the pump (the
/// host's apply, the client's delta apply; no State op). coopGiftPump() (updateCoopTask, after the drain, both
/// machines) moves the giver's selection off the given unit, gives the receiver the unit as its gift target (and its
/// selection when it has none) and the notice "<giver> gave <unit> to you." (English text), and
/// refills an empty gift target. The three selection hooks keep THIS machine's gift target - the unit the give-unit
/// key gives:
/// coopGiftSelectionInit() at the battle screen's first init, coopGiftSelectAt() on a left click (before the cursor /
/// busy gate), coopGiftFollowSelection() when this machine's selected unit changes. Every function is a no-op outside
/// a co-op battle (single player untouched).
void coopGiftOrder(BattleUnit* unit, int target);
bool coopApplyGift(BattleUnit* unit, int giverSeat, int target, std::uint32_t iseq);
void coopGiftNoteSeatChange(int unitId, int fromSeat, int toSeat);
void coopGiftPump(Game* game);
void coopGiftSelectionInit(Game* game, SavedBattleGame* save);
void coopGiftSelectAt(Game* game, SavedBattleGame* save, int x, int y, int z);
void coopGiftFollowSelection(Game* game, SavedBattleGame* save);

/// coop: the INVERTED form of coopMayCommand() used by
/// BattlescapeGame::primaryAction's COMMANDING arms, plus a test-only counter.
///
/// The guard sits ON the two arms of primaryAction that actually execute
/// something - the targeting/BA_LAUNCH/spray block and the walk-confirm arm -
/// not at the top of the function, so that the SELECT-UNIT branch sitting
/// between them runs on a co-op client for the units its own seat commands.
/// Only that one branch is exempt: every commanding arm stays gated, and a
/// client ground-click must mint NOTHING - a locally-executed UnitWalkBState
/// would be a guaranteed, permanent desync.
///
/// THE PREDICATE IS A CONJUNCTION, and NOT `!coopMayCommand(u, s)` alone -
/// that shorthand cannot meet the "mints NOTHING" requirement:
/// `coopMayCommand(u, s)` is `commandsUnit(u) && mySideActive(s)`, i.e. TRUE
/// for a client acting on its OWN unit during its OWN side - which is exactly
/// when the walk arm fires. So the gate is, in this order:
///   1. `coopBattleAuthority().hostSim` - only the SIMULATING machine may run
///      an action that has no wire representation yet. THIS is the term that
///      makes "a client ground-click mints NOTHING" true.
///   2. `coopMayCommand(u, s)` - on the host, the seat must still command the
///      unit and its side must be active.
/// `BattlescapeState::btnKneelClick` is the shipped two-term house pattern
/// (`coopMayCommand` then `isCoopBattle() && !hostSim`); kneel's second term
/// SENDS an intent; here the second
/// term simply refuses. Self-guarded exactly like isCoopBattle()/
/// coopMayCommand(): outside an ACTIVE co-op battle it returns false and
/// vanilla - SP included - is byte-identical.
///
/// The counter is the other half: each refusal bumps a value
/// coopLocalExecutionBlocks() reports. That is what makes the no-mint check
/// provable rather than inferable - "the client's ground click minted nothing"
/// must not be satisfiable by a click that never reached primaryAction at all.
/// Defined in connectionTCP.cpp next to coopMayCommand().
bool coopBlockLocalExecution(const BattleUnit* u, const SavedBattleGame* s);

/// coop: the gate at the top of BattlescapeGame::primaryAction's TARGETING arm
/// (in place of coopBlockLocalExecution()) - the walk-arm gate split,
/// generalised to the arm whose kinds have a wire verb. Reads the kind off
/// @a s's live BattlescapeGame::getCurrentAction().
///   * A kind whose intercept EXISTS: OWNERSHIP + ACTIVE SIDE only, on BOTH
///     machines (`commandsUnit(u) && mySideActive(s)`), a refusal bumping the
///     same coopLocalExecBlocked counter. The hostSim term moves down to the
///     execution point and so does the baton term (the local aiming
///     bookkeeping - confirm-fire first click - stays allowed off-turn). The
///     kinds and their execution points:
///     - the snap / aimed / auto shot: coopInterceptFireConfirm() (CoopArbiter.h);
///     - the throw and the launcher (BA_THROW, BA_LAUNCH): the launcher's
///       waypoint clicks are local display, its execution point is the launch
///       button (launchAction's coopInterceptFireConfirm());
///     - the psi amp (BA_PANIC / BA_MINDCONTROL / BA_USE with a BT_PSIAMP item)
///       and the mind probe (BA_USE with a BT_MINDPROBE item):
///       coopInterceptPsiConfirm() (CoopArbiter.h);
///     - the spray (an autoshot with a `sprayWaypoints` weapon under Ctrl+Shift,
///       or an already-running spray targeting): the spray start and its
///       waypoint clicks are local display, its execution point is the
///       spray-fire coopInterceptFireConfirm().
///   * Every other targeting kind keeps coopBlockLocalExecution(), so no kind
///     has a local-sim path.
/// Self-guarded: false outside an ACTIVE co-op battle, so SP is byte-identical.
bool coopBlockTargetingArm(const BattleUnit* u, SavedBattleGame* s);

/// test-only introspection - how many times coopBlockLocalExecution()
/// has refused a local execution in this process. Reported by TestServer's
/// `event_state` as `coopLocalExecBlocked`; never read by game logic.
int coopLocalExecutionBlocks();

/// coop (thin-client tripwire): test-only introspection for
/// the second player's "never simulates" guarantee. Three BATTLE-scoped values
/// (reset by resetBattleAuthority(), unlike coopLocalExecutionBlocks()'s
/// process-lifetime counter above), reported by TestServer's `event_state` as
/// `coopClientBStatePushes` / `coopClientBStateLastSite` /
/// `coopClientPanicSkipped`; never read by game logic.
///
/// The writers live in connectionTCP.cpp beside coopBlockLocalExecution() and
/// write the storage directly (test_thin_client_tripwire.py reads them):
///   * coopClientBStateTripwire(site, bs): `g_coopClientBStatePushes`
///     (fetch_add) and `g_coopClientBStateLastSite`, set to
///     "<site>:<typeid(*bs).name()>" - or "<site>:endTurnRequest" when
///     bs == nullptr - under `g_coopClientBStateLastSiteMutex`;
///   * coopSkipClientPanic(): `g_coopClientPanicSkipped` (fetch_add).
/// The storage is declared above resetBattleAuthority() in connectionTCP.cpp
/// (the same placement rule as g_coopPauseModalPending) so the teardown can
/// reset it; the string carries its own mutex because resetBattleAuthority()
/// is reachable from the UDP-monitor thread (the cross-thread note at the top of this
/// header) while the pump thread reads it.
///
/// How many BState pushes the tripwire has refused on this machine this battle.
int coopClientBStatePushes();

/// The last refused push as "<site>:<dynamic type name>"; "" before any.
std::string coopClientBStateLastSite();

/// How many start-of-turn panic checks this machine has skipped this battle.
int coopClientPanicSkipped();

/// coop (thin-client tripwire): the ONE
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
/// upstream (the action menu's item actions and the reload hotkey - the
/// intercepts in CoopArbiter.h - and the panic check, coopSkipClientPanic()),
/// so a count here is a path nobody
/// has found yet, surfacing as a counter instead of a desync. Defined in
/// connectionTCP.cpp beside coopBlockLocalExecution().
bool coopClientBStateTripwire(const char* site, BattleState* bs = nullptr);

/// the start-of-turn panic check on a co-op CLIENT. BattlescapeGame::
/// think()'s player branch reads `_playerPanicHandled = coopSkipClientPanic()
/// ? true : handlePanickingPlayer();`. On a machine that is NOT the host sim
/// inside an active co-op battle (the same predicate as
/// coopClientBStateTripwire()) this bumps coopClientPanicSkipped() and returns
/// TRUE, so the check is marked handled without running
/// handlePanickingPlayer() (its RNG, dropItem and UnitWalkBState/
/// UnitPanicBState pushes). The host keeps resolving panic for every player
/// unit and streams it. FALSE everywhere else.
bool coopSkipClientPanic();

/// coop: the battle-start casualty pass (BattlescapeGame's constructor) on a co-op CLIENT. TRUE on a
/// machine that is NOT the host sim inside an active co-op battle (coopClientBStateTripwire()'s predicate): the pass does not run
/// there - the host settles every generation casualty and its `death` ev's delta carries the result. FALSE everywhere
/// else (the host, single player, any non-co-op battle), so vanilla is byte-identical there. No counter, no side effect.
bool coopSkipClientBattleStartCasualties();

/// coop: the WALK ARM's entry gate in BattlescapeGame::primaryAction (in
/// place of `coopBlockLocalExecution()`), since the arm HAS a wire verb.
///
/// THE GATE SPLITS; IT IS NOT WEAKENED:
///   * THIS call keeps term 2 (OWNERSHIP + active side) and keeps it HERE, at
///     the top of the arm, because the ownership rule forbids a seat even
///     PREVIEWING a unit it does not command - and a co-op client now runs
///     vanilla's whole preview block (Pathfinding::calculate + previewPath,
///     both machine-local display scratch: `_path`/`_totalTUCost` are not
///     serialized and `Tile::_preview`/`_markerColor`/`_tuMarker` are not
///     serialized either). A refusal bumps the SAME
///     coopLocalExecutionBlocks() counter as coopBlockLocalExecution(), so every existing
///     "delivered then refused" proof keeps working for the cases that still
///     refuse.
///   * term 1 (hostSim - "only the simulating machine may EXECUTE") moves DOWN
///     to `coopInterceptWalkConfirm()` (CoopArbiter.h), which sits immediately
///     before `statePushBack(new UnitWalkBState(...))`. The no-mint rule is enforced
///     there and is not relaxed by one line: a co-op client still never reaches
///     that push. What changes is what happens INSTEAD - a `bt_intent walk`
///     rather than a bare refusal.
/// Self-guarded exactly like coopBlockLocalExecution(): false outside an ACTIVE
/// co-op battle, so SP is byte-identical.
bool coopBlockWalkArm(const BattleUnit* u, const SavedBattleGame* s);

/// test-only introspection - how many times the WALK ARM has been
/// ENTERED on this machine (bumped by coopBlockWalkArm() before it decides
/// anything, in a co-op battle only). Reported by TestServer's `event_state` as
/// `coopWalkArmEntered`.
///
/// It is the DELIVERY PROOF for a client ground click: a click on a unit the
/// client DOES command is forwarded as an intent, and a click whose
/// pathfinder finds no route reaches the arm and legitimately does nothing at
/// all. Neither of those moves the refusal counter, so without this one "the
/// click arrived" would be unprovable. Never read by game logic.
int coopWalkArmEntries();

/// test-only introspection - how many `bt_intent walk` envelopes this
/// CLIENT has shipped from the walk-confirm hook (`coopInterceptWalkConfirm`).
/// Reported by TestServer's `event_state` as `coopWalkIntentsSent`. Together
/// with coopWalkArmEntries() above it separates "the click reached the arm and
/// became an ORDER" from "the click reached the arm and did nothing", which is
/// what a ground-click gate has to be able to tell apart once the arm has a
/// wire verb. Never read by game logic.
int coopWalkIntentsFromClick();

/// the think() guard. ONE guarded
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
///      through the public factionOf() - kMaxSeats is private and stays
///      4) - an unmapped seat defaults to FACTION_PLAYER
///      (BattleAuthority::factionOf()), so this can only be true for a
///      non-player side when gm2+ actually assigned a human to it.
/// False (vanilla AI runs) in every other case - i.e. on the host, for an
/// AI-only side.
bool coopSuppressNonPlayerThink(const SavedBattleGame* s);

/// true iff a human
/// seat commands @a faction in this co-op battle - a seat 0..3 MAPPED to it in the seat->faction
/// store (seatMapped(): an unmapped seat's FACTION_PLAYER default never counts), i.e. gm2 / gm3's
/// hostile side and every co-op player side. False outside an active co-op battle, so single
/// player and every AI side stay byte-identical. Read by the guarded vanilla terms
/// (SavedBattleGame::canUseWeapon()'s AI weapon-use delay: a human seat's units skip only
/// that term) and by coopHostArmsHumanSidePanic() below.
bool coopFactionHumanCommanded(int faction);

/// coop (the human hostile side's panicking / berserk units act out at that side's start,
/// as X-COM's do): BattlescapeGame::init()'s second arm of the start-of-side panic check. True on
/// the co-op HOST only (hostSim), while the active side is a non-player, non-neutral side a human
/// seat commands (coopFactionHumanCommanded()) - from turn 1, since that side's units roll morale at
/// every side start. A client never runs a panic (coopSkipClientPanic()). False everywhere else.
bool coopHostArmsHumanSidePanic(const SavedBattleGame* s);

/// coop (a seat never holds a unit it does not command): BattlescapeGame::think()'s two start-of-side panic checks
/// (the player side's and the human-side one) call this after each
/// pass. Once the check is over (getPanicHandled()) on the co-op HOST, while the active side is one
/// this host does not play (gm3's X-COM turn, gm2's alien turn), a selection that vanilla's
/// handlePanickingUnit() left on a unit the host does not command is dropped with the action actor:
/// the host then holds no unit, as that side's start gave it (SavedBattleGame::endTurn's seat-filtered
/// restore). The panic itself still plays out on the host, the battle authority. Host-local UI state
/// only: no hashed field, nothing on the wire. A no-op in single player, on a client, while a panic
/// still plays out and while the host holds a unit it commands.
/// On the host's OWN
/// side (classic / SHARED co-op, gm4's player side), where the panic check leaves the host holding its
/// partner's panicked unit, the host instead selects the next unit it commands in vanilla's next-unit
/// order (SavedBattleGame::selectNextPlayerUnit(), the seat-filtered cycle the Tab key runs), with the
/// action actor and a HUD refresh; with no live unit it commands, it holds none (as off its side).
void coopHostDropOffSideSelection(SavedBattleGame* s);

/// psi target knowledge for a human seat's non-player attacker. -1 = not
/// such an attacker (vanilla's own term runs); otherwise 1 / 0 by whether the attacker's side sees the target now (coopSideSeesUnit()). Read by the psi arm of
/// BattlescapeGame::primaryAction() and its host mirror validatePsi().
int coopHumanKnowsTarget(const BattleUnit* actor, const BattleUnit* target, const SavedBattleGame* s);

/// coop: the HOST's per-seat store of the latest
/// battle_roster_contrib (BattleWire.h) received from that seat - test/
/// introspection + CoopState.cpp's coopMergeGuestContributions() reads.
/// Defined in connectionTCP.cpp beside the store itself; cleared by
/// resetBattleAuthority(). @a seat is 0..3 (kMaxSeats is private and
/// stays 4); out-of-range returns the empty/false/zero default.
///
/// How many guest-soldier YAML entries are currently stored for @a seat.
/// Reported by TestServer's `event_state` as `guestContrib.soldiers[seat]`
/// (proof the roster actually travelled).
/// the store keeps one entry per destination (craftId + craftType); this sums them.
int coopGuestContribStoredCount(int seat);

/// Whether @a seat's stored entry names the craft (@a craftId + @a
/// craftType) coopMergeGuestContributions() is about to generate for - the
/// match coopMergeGuestContributions() itself needs before it deserialises
/// anything stored for that seat.
bool coopGuestContribCraftMatches(int seat, int craftId, const std::string& craftType);

/// how many guest-soldier YAML entries @a seat stored for the
/// craft @a craftId + @a craftType (0 when none) - what coopMergeGuestContributions()
/// deserialises for the landing craft.
int coopGuestContribCraftCount(int seat, int craftId, const std::string& craftType);

/// The @a index'th guest Soldier YAML @a seat stored for the craft @a craftId + @a craftType (Soldier::save()'s
/// wire form), or an empty string if out of range - coopMergeGuestContrib-
/// utions() deserialises each of these via Soldier::load().
const std::string& coopGuestContribSoldierYaml(int seat, int craftId, const std::string& craftType, int index);

/// The CLIENT's own count of guest soldiers in the last battle_roster_contrib
/// census it computed (connectionTCP::sendGuestRosterContrib()) - 0 if none
/// (host, SHARED campaign, or no SEPARATE guest waiting yet). Reported by
/// TestServer's `event_state` as `guestContrib.sent` (proof the roster was sent,
/// the client-side half).
int coopGuestContribLastSentCount();

/// the CLIENT's own count of parked tanks in its last
/// battle_roster_contrib census (TestServer `event_state.guestContrib.vehSent`), and the HOST's stored parked-tank count
/// for @a seat over every destination (`guestContrib.vehicles[seat]`). Test / introspection only.
int coopGuestContribLastSentVehicles();
int coopGuestContribStoredVehicles(int seat);

/// coop: true when a research-based weapon check must read the unit OWNER's
/// research - a live co-op battle (isCoopBattle(): single player is never
/// separate) in a campaign (NEW BATTLE sets it false) that is not SHARED,
/// with the host's "Enable Research Sync (Separate)" OFF. Evaluated on EVERY
/// call and never cached: the option can change mid-battle (#185).
bool coopResearchSeparate(Game* game);

/// coop: vanilla SavedGame::isResearched(@a req) answered from @a
/// seat's research. Outside coopResearchSeparate(), for a seat outside 1..3
/// (seat 0 and seat-less units: the live world), in debug mode, or when no
/// list is stored for the seat, it is the live world's answer - unchanged.
/// Otherwise vanilla's own function on the seat's research-only world.
bool coopSeatIsResearched(Game* game, int seat, const std::vector<const RuleResearch*>& req);
/// the same routing around vanilla's string-list overload
/// (the psi-strength lines pass Mod::getPsiRequirements(), a name list).
bool coopSeatIsResearched(Game* game, int seat, const std::vector<std::string>& req);

/// coop: the same routing around vanilla
/// SavedGame::isManaUnlocked(@a mod) (@a mod = the Mod* the vanilla site
/// passes).
bool coopSeatIsManaUnlocked(Game* game, int seat, Mod* mod);

/// coop: the same routing around vanilla Ufopaedia::isArticleAvailable(
/// <world>, @a article) - the seat's research-only world under the store's
/// mutex, the live world in every coopSeatIsResearched() fallback. The seat
/// form, so the in-battle Ufopaedia can call it for the viewer's seat.
bool coopSeatArticleAvailable(Game* game, int seat, ArticleDefinition* article);

/// coop (test introspection; TestServer `event_state.researchMode`):
/// whether a research list is stored for @a seat (0..3; seat 0 never is),
/// how many known topics it holds, and how many names it could not resolve.
/// Each takes the store's mutex.
bool coopSeatResearchStored(int seat);
int coopSeatResearchCount(int seat);
int coopSeatResearchUnknown(int seat);

/// coop (each soldier's owner's research): coopSeatIsResearched() / coopSeatIsManaUnlocked() for @a
/// unit's OWNER - its seat tag (BattleUnit::getCoopSeat()), never the
/// controller; a null or seat-less unit reads the live world. Called by the
/// guarded vanilla terms (SavedBattleGame::canUseWeapon, ActionMenuState) and
/// the host's admission (coopWeaponUseDeny); @a mod = the Mod* the vanilla
/// site passes.
bool coopIsResearchedFor(Game* game, const BattleUnit* unit, const std::vector<const RuleResearch*>& req);
bool coopIsResearchedFor(Game* game, const BattleUnit* unit, const std::vector<std::string>& req);
bool coopIsManaUnlockedFor(Game* game, const BattleUnit* unit, Mod* mod);

/// coopSeatArticleAvailable() for
/// @a unit's OWNER (its seat tag; a null or seat-less unit reads the live
/// world). Called by the guarded vanilla reads of the inventory (category
/// search, Alt damage tooltip), the melee damage preview and the Alt aiming
/// damage preview (Map).
bool coopArticleAvailableFor(Game* game, const BattleUnit* unit, ArticleDefinition* article);

/// the in-battle Ufopaedia's article check for the VIEWER (localSeat), never
/// a unit's seat: coopSeatArticleAvailable() above while this machine's live battle
/// screen holds @a save, vanilla Ufopaedia::isArticleAvailable otherwise.
/// Called by the five guarded vanilla reads in src/Ufopaedia.
bool coopViewerArticleAvailable(SavedGame* save, ArticleDefinition* article);

/// coop: the HOST's one battle-end chokepoint - the first statement
/// of BattlescapeState::finishBattle(), which every vanilla ending reaches.
/// Emits the terminal `battle_end` bt_ev {reason, aborted, inExitArea,
/// perSeatVerdict, tally, h} through CoopEmit::sendEv (`h` = the action-end
/// buckets of the state BEFORE finishBattle mutates anything), then sets phase
/// Ended. Decides nothing vanilla decides; reads only @a abort / @a inExitArea
/// (vanilla's own arguments) and the battle. A no-op outside a live host coop
/// battle (single player, a client) and for a preview; a stage transition
/// (finishBattle's own nextStage test) is not an end and emits nothing.
/// Defined in connectionTCP.cpp.
void coopHostBattleEnd(Game* game, SavedBattleGame* save, bool abort, int inExitArea);

/// coop: the HOST's stage hand-off, ONE line after vanilla's
/// bgen.nextStage() in BattlescapeState::finishBattle() (coopHostBattleEnd above sent `stage_end` there): nulls the
/// stage-N battle screen pointer (freed next frame), resets the battle scope and offers the next stage as a
/// fresh battle (`stageOf`). Self-guarded (host, co-op, hand-off armed). Defined in connectionTCP.cpp.
void coopHostNextStage(Game* game, SavedBattleGame* save);

} // namespace OpenXcom
