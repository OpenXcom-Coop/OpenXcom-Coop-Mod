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

#include <json/json.h>

namespace OpenXcom
{

class SavedBattleGame;
class BattleUnit;
class BattleItem;
class Tile;
class Position;
class Projectile;
struct BattleAction;
struct BattleActionAttack;
struct RuleDamageType;

/**
 * W2-P2 (rewrite wave 2, docs rewrite/prompts/w2p2_delta_core.md, owner ruling
 * D128 = (b)): the DELTA CORE. Every host event carries a `delta` - the
 * absolute value of every synced field that changed since the previous event -
 * attached at the one host emit choke (CoopEmit::sendEv), and the client writes
 * those values with plain setters, never by re-running the simulation.
 *
 * Stage S-A: commit S-A.1 (the RED commit, spec (d)) declared the spec (b)16
 * probes' read accessors and the `delta_drop_next` lever's one-shot request;
 * commit S-A.2 adds the snapshot, diff, attach, seed, reset, absorb and `sync`
 * flush below (the client applier is CoopApply::applyDelta, inside
 * connectionTCP.cpp's CoopApply region). The storage lives in connectionTCP.cpp
 * just above `namespace CoopEmit` (spec (b)3), next to the other battle-scoped
 * coop globals; the counters are reset by resetBattleAuthority() (spec (b)5).
 *
 * Every probe is TEST INTROSPECTION ONLY (TestServer `event_state`), battle-
 * scoped, and never read by game logic. Timings are local measurements, never
 * put on the wire (G1).
 */
namespace CoopDelta
{

/// One machine's view of the spec (b)16 delta probes (`event_state` fields in
/// brackets). "host" / "client" name the machine that writes the field; the
/// other machine reports its own (normally zero) value.
struct Probes
{
	bool armed = false;      ///< [deltaArmed] the host snapshot is seeded and armed
	int seeds = 0;           ///< [deltaSeeds] CoopDelta seeds this battle (fresh / rejoin / resume)
	int evsEmitted = 0;      ///< [deltaEvsEmitted] host: envelopes that carried a non-empty delta
	int evsApplied = 0;      ///< [deltaEvsApplied] client: envelopes whose delta was applied
	int fieldsApplied = 0;   ///< [deltaFieldsApplied] client: individual field writes applied
	int unresolved = 0;      ///< [deltaUnresolved] an id or tile index that did not resolve
	int addExisting = 0;     ///< [deltaAddExisting] an itemsAdded id that already existed
	int removeMissing = 0;   ///< [deltaRemoveMissing] an itemsRemoved id that did not exist
	int unsupported = 0;     ///< [deltaUnsupported] a change W2-P2 does not carry (logged)
	int absorbed = 0;        ///< [deltaAbsorbed] host: test-lever writes absorbed into the snapshot
	int dropped = 0;         ///< [deltaDropped] host: deltas withheld by `delta_drop_next`
	int diffUsLast = 0;      ///< [deltaDiffUsLast] host: last diff+attach, microseconds
	int diffUsMax = 0;       ///< [deltaDiffUsMax]
	int bytesLast = 0;       ///< [deltaBytesLast] host: last attached delta, serialized bytes
	int bytesMax = 0;        ///< [deltaBytesMax]
	int hashUsLast = 0;      ///< [hashUsLast] host: last emission's `h` build, microseconds
	int hashUsMax = 0;       ///< [hashUsMax]
	int applyUsLast = 0;     ///< [deltaApplyUsLast] client: last applyDelta, microseconds
	int applyUsMax = 0;      ///< [deltaApplyUsMax]
	int syncEvsEmitted = 0;  ///< [syncEvsEmitted] host: `sync` evs emitted
	int syncEvsApplied = 0;  ///< [syncEvsApplied] client: `sync` evs applied
	// W2-P2 S-L (amendment A4.5, owner ruling M6): the client's light
	// recomputes made by CoopApply::applyDelta. Commit S-L.1 (the RED commit)
	// counts today's one whole-map pass; commit S-L.2's vanilla-shaped local
	// calls are the `lightLocalCalls` writers.
	int lightLocalCalls = 0; ///< [lightLocalCalls] client: region (non-whole-map) light recomputes
	int lightWholeCalls = 0; ///< [lightWholeCalls] client: whole-map light recomputes
	int lightUsMax = 0;      ///< [lightUsMax] client: the slowest single light recompute, microseconds
	// W2-P2 S-C (spec (b)13/(b)16): the host's own combat actions. Commit
	// S-C.1 (the RED commit) adds the storage only; commit S-C.2's
	// CoopArbiter::beginHostLocalCombat is the writer.
	int hostCombatContexts = 0; ///< [hostCombatContexts] host: host-local combat contexts begun
	// W2-P2 S-C (amendment A3, F690): the arming guard's deferrals - an
	// onChainQuiesced() that fired INSIDE an armed push pair (the battle_fire
	// lever's turn-then-shot pushes) and was deferred instead of closing the
	// context before the shot state existed.
	int armingDeferrals = 0;    ///< [armingDeferrals] host: quiescences deferred while arming
	// W2-P3 S-A (spec rewrite/prompts/w2p3_nonplayer_origins.md (b)13,
	// amendment B1 RQ5): the action-context counters. Commit S-A.1 (the RED
	// commit) adds the storage only; commit S-A.2 is the writer.
	int contextsClosedAtEndTurn = 0; ///< [contextsClosedAtEndTurn] host: contexts (origin != endturn) closed at endTurn() entry; diagnostic (RQ5)
	int contextBeginRefused = 0;     ///< [contextBeginRefused] host: base context begins refused because a context was open
	// W2-P2 S-H (amendment A5.5, owner ruling D138): the `saveBlob` timings,
	// kept apart from hashUsLast/Max (N19). Commit S-H.1 (the RED commit)
	// times the host's existing saveBlob computations (side_transition, and a
	// structured `h` built with saveBlob); the client's verify arm, and so its
	// timing writer, is commit S-H.2's.
	int saveBlobUsLast = 0;       ///< [saveBlobUsLast] host: last saveBlob computation, microseconds
	int saveBlobUsMax = 0;        ///< [saveBlobUsMax]
	int saveBlobVerifyUsLast = 0; ///< [saveBlobVerifyUsLast] client: last saveBlob verify, microseconds
	int saveBlobVerifyUsMax = 0;  ///< [saveBlobVerifyUsMax]
};

/// A snapshot of this machine's probes (thread-safe; reads atomics).
Probes probes();

/// [lastDelta] the class counts of the last delta this machine emitted
/// (host: the last NON-EMPTY one) or applied (client), as
/// {seq, kind, units, unitsAdded, tiles, nodes, items, itemsAdded,
/// itemsRemoved, battle:[keys]} - or null when there has been none this
/// battle. (`unitsAdded`: W2-P3 S-C.1, spec (b)10/(b)13.)
Json::Value lastDelta();

/// [deltaRing] (W2-P3 S-C.1, amendment B1 RQ7) HOST: the last 32 deltas this
/// machine attached, oldest first, each the lastDelta() record of that
/// envelope plus the ids its classes added or removed - {seq, kind, units,
/// unitsAdded, tiles, nodes, items, itemsAdded, itemsRemoved, battle:[keys],
/// unitsAddedIds:[..], itemsAddedIds:[..], itemsRemovedIds:[..]} - so a test
/// reads the delta of one specific ev by its seq. An empty array on a client
/// and before the first attach. Probe only.
Json::Value deltaRing();

/// [lastLight] (W2-P2 S-L, A4.5) the last light recompute the client's delta
/// applier made, as {seq, kind, layer, x, y, z, radius, terrain, whole, us}
/// (x/y/z = -1 and whole = true for a whole-map pass) - or null when there
/// has been none this battle.
Json::Value lastLight();

/// `light_probe_reset` (W2-P2 S-L, A4.5; test lever): zero this machine's
/// `lightUsMax` and `deltaApplyUsMax` windows. Nothing else changes.
void resetLightWindow();

/// [cueCounts] (W2-P2 S-C, spec (b)11/(b)16) the cue evs of this battle per
/// kind - host: emitted, client: applied - as {kind: count} (an empty object
/// when there has been none). Commit S-C.1 (the RED commit) adds the storage
/// and this reader only; commit S-C.2's cue hooks (host) and cue-kind branch
/// (client) are the writers.
Json::Value cueCounts();

/// [lastCue] (W2-P2 S-C, spec (b)16) the last cue ev this machine emitted
/// (host) or applied (client), as {kind, seq, actionId, payload} - or null
/// when there has been none this battle. Same writers as cueCounts().
Json::Value lastCue();

/// [contextsOpened] (W2-P3 S-A, spec (b)13) host: the action contexts pushed
/// this battle per origin, every origin including wave 1's ("intent", "host",
/// "ai", "endturn", ...), as {origin: count} (an empty object when there has
/// been none). Commit S-A.1 (the RED commit) adds the storage and this reader
/// only; commit S-A.2's context begin paths are the writers.
Json::Value contextsOpened();

/// [closedContexts] (W2-P3 S-A, spec (b)13, amendment B1 RQ7) host: the last
/// 32 action contexts closed this battle, oldest first, as [{actionId, origin,
/// kind, actorId (-1 = actor-less), nestedIn (the base entry's id, 0 for a
/// base context), endSeq (the seq of its bt_action_end, 0 when none was
/// emitted), hasFinal (that bt_action_end carried `final`)}] (an empty array
/// when there has been none). Commit S-A.1 (the RED commit) adds the storage
/// and this reader only; commit S-A.2's context close paths are the writers.
Json::Value closedContexts();

/// [hashVerifyCounts] (W2-P2 S-H, amendment A5.5) client: per bucket name,
/// how many times CoopHashCheck::verify() compared that bucket this battle,
/// equal or not, as {bucket: n} (an empty object when there has been none).
/// A carried bucket verify() does not know (logged and ignored) is not
/// compared, so it is not counted.
Json::Value hashVerifyCounts();

/// [lastHashVerify] (W2-P2 S-H, A5.5) client: the last verify() call that
/// reached its compare loop, as {seq, kind, buckets:[the names it compared,
/// in order]} (`kind` = the ev's kind, else the envelope's state) - or null
/// when there has been none this battle.
Json::Value lastHashVerify();

/// CoopHashCheck::verify()'s two probe hooks (A5.5; probe only, never read by
/// game logic): noteHashVerifyBegin() once, right before the compare loop;
/// noteHashVerifyBucket() once per bucket the loop compares.
void noteHashVerifyBegin(const Json::Value& evOrEnd);
void noteHashVerifyBucket(const std::string& bucket);

/// HOST, RB-D26 one-shot (the `reveal_drop` pattern): the NEXT delta attach
/// computes and commits its delta but does not attach it (bumping `dropped`),
/// so the client is permanently missing those values - a hash-visible
/// divergence that proves the delta, and nothing else, closed the hole.
/// Cleared at battle teardown. Consumed by the next attach() whose delta is
/// non-empty (the reveal_drop pattern) or, when @a cls names a delta class
/// (a spec (b)1 top-level key, e.g. "tiles"; F515), by the next attach()
/// whose delta carries at least one entry of that class.
void requestDropNext(const std::string& cls = std::string());

// ----- W2-P2 S-A, commit S-A.2: the delta core (spec (b)1-6, 9, 15) -----
// Stage S-A syncs UNITS, TILES, NODES and BATTLE COUNTERS (itemIdCtr
// included); items are stage S-B. Bodies: connectionTCP.cpp, just above
// namespace CoopEmit.

/// HOST (spec (b)4): snapshot := live state of @a battle, and arm. Called on
/// the line after each of the three saveCoopToMemory("battlehost") snapshots
/// (fresh offer, rejoin, disk resume) - the exact state the client's blob
/// freezes. Unconditional: phase is still Handshake at the fresh offer.
void seed(SavedBattleGame* battle);

/// Spec (b)5: disarm and clear the snapshot. Called from CoopPump::reset().
/// A disarmed host attaches nothing.
void reset();

/// HOST (spec (b)3), at the CoopEmit::sendEv choke, for the OUTERMOST call
/// only: diff the live state against the snapshot, write env["delta"] when
/// non-empty, and commit the new values. No-op unless armed. Returns true iff
/// a delta was attached.
bool attach(SavedBattleGame* battle, Json::Value& env);

/// HOST (spec (b)9): called from onChainQuiesced()'s empty-context branch.
/// When armed and the delta is non-empty, emits one
/// bt_ev{kind:"sync", actionId:0, payload:{}} carrying it, with h = the 7
/// structured buckets. Self-guarded (coop battle, host sim).
void flushSync();

/// HOST, armed only (spec (b)15): a TEST LEVER wrote this object directly;
/// copy its live values into the snapshot so the write never rides a delta
/// (a one-machine poke keeps proving detection; a both-machine write stays
/// equal without a mint race). Bumps `absorbed`. Never called by product code.
void absorbUnit(const BattleUnit* unit);
void absorbTile(const Tile* tile);
void absorbBattle(SavedBattleGame* battle);

// ----- W2-P2 S-B, commit S-B.2: the item delta (spec (b)1, 7, 8, 15) -----
// attach() now also diffs ITEMS: `items` (field changes, incl. ammo links -
// a slot whose ammo is the weapon itself (BattleItem.cpp's `_ammoItem[slot] =
// this`, F530) is encoded as the item's OWN id and restored as self),
// `itemsAdded` (the host's BattleItem::save() YAML, materialized on the client
// with the host's id through the load path) and `itemsRemoved`.

/// HOST, armed only (spec (b)15): a TEST LEVER created or wrote @a item;
/// copy its live values into the snapshot (a new id is added), so the write
/// never rides a delta. Bumps `absorbed`. Never called by product code.
void absorbItem(const BattleItem* item);
/// HOST, armed only (spec (b)15): a TEST LEVER removed item @a id (and each
/// of its ammo ids, one call each); drop it from the snapshot so the removal
/// never rides a delta. Bumps `absorbed`. Never called by product code.
void absorbItemRemoved(int id);

} // namespace CoopDelta

// ----- W2-P2 S-C, commit S-C.2: host combat cues (spec (b)11, (b)14) -----
// A cue is bt_ev{kind, actionId, payload}: its STATE effect is the envelope's
// `delta` alone (attached at the CoopEmit::sendEv choke); the payload carries
// only the display fields a later animation unit (W2-P5/P6) needs - frozen here
// (V2), no timing (G1). Every hook below is ONE guarded call at its vanilla
// site and a no-op unless isCoopBattle() && hostSim (so SP, a client and the
// WV-D68 pre-game deaths emit nothing). A cue takes
// CoopArbiter::currentActionId() - 0 outside a context: the hooks serve every
// origin (Q2 = (a)); AI and reaction fire get their own contexts in W2-P3.
// Bodies: connectionTCP.cpp.

/// Spec (b)11: true for the 16 frozen cue kinds (shot, hit, explosion, melee,
/// psi, death, corpse, prime, sync, fall, revive, spawn, panic, prox_trigger,
/// medikit, scanner). The client's CoopApply::applyEvPayload records the cue
/// probe for them and nothing else.
bool coopIsCueKind(const std::string& kind);

/// P1 (ProjectileFlyBState::createNewProjectile, after the hit-log block):
/// the `shot` cue - {actor, unit (=actor), weapon, ammo, action, shotIndex,
/// waypointsLeft, originVoxel, impactVoxel, impact, arc?}. `arc` rides a throw
/// or an arcing shot and comes from coopNoteThrowArc()'s note.
void coopCueShot(const BattleAction& action, const BattleItem* ammo, const Projectile* projectile, int impact);

/// P2 (ProjectileFlyBState::think, after a shotgun pellet's TileEngine::hit):
/// the pellet `hit` cue - {actor?, unit?, voxel, damageType, power, miss:false,
/// pellet}.
void coopCuePellet(const BattleActionAttack& attack, const Position& voxel, int power,
	const RuleDamageType* damageType, int pellet);

/// PR1 (Projectile::calculateThrow, before calculateParabolaVoxel): record the
/// arc of the throw / arcing shot being computed (last write wins inside the
/// `tries` loop); read and cleared by the next coopCueShot(). Nothing is sent.
void coopNoteThrowArc(const Position& originVoxel, const Position& targetVoxel, const Position& deltas,
	double curvature);

/// E1 (end of ExplosionBState::init, before the BA_SELF_DESTRUCT test - the
/// damage is applied by then): `explosion` (area), `melee` (BA_HIT), `psi`
/// (psi amp) or `hit` (a bullet impact), each with its frozen payload.
void coopCueExplosionInit(const BattleActionAttack& attack, const Position& centre, int power, int radius,
	const RuleDamageType* damageType, bool areaOfEffect, bool melee, bool psi, bool miss, int chain,
	const Tile* tile, const BattleUnit* target);

/// D1 (UnitDieBState constructor, after freePatrolTarget()): the `death` cue -
/// {unit, outcome:"dead"|"unconscious", instant, damageType}.
void coopCueDeath(const BattleUnit* unit, const RuleDamageType* damageType);

/// D2 (UnitDieBState::think, before clearUnitSelection()): the `corpse` cue -
/// {unit, pos, corpses:[item ids linked to the unit]}, only when >= 1.
void coopCueCorpse(const BattleUnit* unit);

/// Spec (b)14 (BattlescapeGame::handleNonTargetAction, the last statement of
/// the BA_PRIME and BA_UNPRIME spendTU blocks): prime/unprime as an INSTANT
/// host action - mint, push {id,"host"}, emit the `prime` cue ({actor, unit
/// (=actor), item, fuse, unprime}; delta + h), emit bt_action_end{final, h},
/// pop: the kneel pattern in one call. Coop + hostSim only; logged no-op while
/// another action context is open (the fuse then rides the next delta).
void coopHostPrime(BattleUnit* actor, BattleItem* item, bool unprime);

// ----- W2-P3 S-A, commit S-A.2: the `ai` and `endturn` action contexts -----
// Spec rewrite/prompts/w2p3_nonplayer_origins.md (b)1, (b)4-6; amendment B1
// RQ5/RQ6. Each is ONE call at its BattlescapeGame.cpp site and a no-op unless
// isCoopBattle() && hostSim. Origins are host-side action-context values only
// (nothing new on the wire). Bodies: connectionTCP.cpp.

/// V2 (BattlescapeGame::handleAI, the line after the attack's
/// action.updateTU()): open the `ai` context {id, "ai", actor, kind} - kind
/// shoot|throw|launch|melee|psi from @a baType (W2-P2 S-C's mapping) - and arm
/// the W2-P2 arming guard. Every type but psi also records the pre-attack
/// `turn` ev for this action (spec (b)5, RQ6). Logged no-op (bumping
/// `contextBeginRefused`) while another context is open.
void coopBeginAiAttack(BattleUnit* actor, int baType);

/// V3 (handleAI, the statement after the attack's state pushes): end the
/// arming; when @a statesEmpty (every pushed state already popped inside its
/// own push) close the `ai` context now. No-op unless coopBeginAiAttack() armed.
void coopAiAttackPushed(bool statesEmpty);

/// V4 (the first statement of BattlescapeGame::endTurn()): when @a statesEmpty,
/// close EVERY open context (bt_action_end each; an actor-less `endturn` one
/// without `final`), clear the arming and the pre-attack turn flag, and bump
/// the diagnostic `contextsClosedAtEndTurn` for each closed context whose
/// origin is not `endturn` (RQ5). Nothing when states are still queued.
void coopOnEndTurnEntry(bool statesEmpty);

/// V5 (endTurn, before the hot-grenade push loop, @a go = `exploded`) and V6
/// (before each terrain-explosion push, @a go = true): when @a go, open the
/// actor-less {id, "endturn", -1, "endturn"} context the explosion chain runs
/// in; the next endTurn() entry closes it. Logged no-op (bumping
/// `contextBeginRefused`) while another context is open.
void coopBeginEndTurnChain(bool go);

// ----- W2-P3 S-B, commit S-B.2: nested `reaction` / `prox` contexts, D145 -----
// Spec rewrite/prompts/w2p3_nonplayer_origins.md (b)1-3, (b)8, (b)9; amendments
// B1 RQ4 (a) / RQ8, B3 (owner ruling D145 = a), B4; D139. Each is ONE guarded
// call at its vanilla site and a no-op unless isCoopBattle() && hostSim.
// Bodies: connectionTCP.cpp.

/// V13 (TileEngine::tryReaction, the line before the reaction hit-log entry):
/// open the NESTED `reaction` context {id, "reaction", @a reactor, nestedIn: the
/// base's id} - reused for every reactor of the same checkReactionFire burst, a
/// new one per burst (B4) - recording the base action's actor as the reaction's
/// trigger (D145); mark "a reaction against the walker" when @a target is the
/// active walker (its halt reason becomes `reaction`, RQ4 (a)).
void coopBeginReaction(BattleUnit* reactor, BattleUnit* target);

/// V11 (BattlescapeGame::checkForProximityGrenades, the line before the
/// grenade's ExplosionBState push): latch the walk's halt reason `prox`, open
/// the NESTED `prox` context {id, "prox", @a unit} and emit the `prox_trigger`
/// cue {unit, item, pos}.
void coopCueProxTrigger(BattleUnit* unit, BattleItem* item, const Position& pos);

/// D145 (ProjectileFlyBState::init / MeleeAttackBState::init, the reaction
/// target check): the unit a reaction shot's target must be - in coop on the
/// host the unit whose action triggered the reaction (the top-most `reaction`
/// context's trigger); @a selected (vanilla's getSelectedUnit()) everywhere else.
BattleUnit* coopReactionTrigger(BattleUnit* selected);

// ----- W2-P3 S-C, commit S-C.2: units that appear mid-battle -----
// Spec rewrite/prompts/w2p3_nonplayer_origins.md (b)9-(b)12; amendment B1
// RQ2/RQ9/RQ10/RQ11. The unit itself rides the delta's `unitsAdded` (the
// host's BattleUnit::save() record, materialized on the client through the
// battle-load path) and its special built-in weapons ride `itemsAdded`; these
// hooks only announce it. Each is ONE guarded call at its vanilla site and a
// no-op unless isCoopBattle() && hostSim. Bodies: connectionTCP.cpp.

/// V16 (SavedBattleGame::convertUnit, the line after newUnit->dontReselect(),
/// cause "convert", @a from = the converted unit) and V12
/// (BattlescapeGame::spawnNewUnit, the line after the new unit's
/// calculateFOV(), cause "item", @a from null): the frozen `spawn` cue
/// {unit, cause, from?} in the running action context (0 outside one).
void coopCueSpawn(BattleUnit* unit, const char* cause, const BattleUnit* from);

/// V17 (NextTurnState's ctor, the line after determineReinforcements()): one
/// `spawn` cue {unit, cause} per live unit the delta snapshot does not know
/// yet - the ids are listed BEFORE the first cue is sent, whose delta then
/// carries every one of them in `unitsAdded`.
void coopCueSpawnAdded(SavedBattleGame* save, const char* cause);

} // namespace OpenXcom
