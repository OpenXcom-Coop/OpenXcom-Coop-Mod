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
class Tile;

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
};

/// A snapshot of this machine's probes (thread-safe; reads atomics).
Probes probes();

/// [lastDelta] the class counts of the last delta this machine emitted
/// (host: the last NON-EMPTY one) or applied (client), as
/// {seq, kind, units, tiles, nodes, items, itemsAdded, itemsRemoved,
/// battle:[keys]} - or null when there has been none this battle.
Json::Value lastDelta();

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

} // namespace CoopDelta

} // namespace OpenXcom
