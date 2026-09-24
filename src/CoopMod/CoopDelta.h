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

/**
 * W2-P2 (rewrite wave 2, docs rewrite/prompts/w2p2_delta_core.md, owner ruling
 * D128 = (b)): the DELTA CORE. Every host event carries a `delta` - the
 * absolute value of every synced field that changed since the previous event -
 * attached at the one host emit choke (CoopEmit::sendEv), and the client writes
 * those values with plain setters, never by re-running the simulation.
 *
 * Stage S-A, commit S-A.1 (the RED commit, spec (d)): this header declares ONLY
 * the spec (b)16 probes' read accessors and the `delta_drop_next` lever's
 * one-shot request. NOTHING writes the probes yet - the snapshot, diff, attach,
 * seed, reset, apply, absorb and `sync` flush are commit S-A.2's product. The
 * storage lives in connectionTCP.cpp just above `namespace CoopEmit` (spec
 * (b)3), next to the other battle-scoped coop globals; the counters are reset by
 * resetBattleAuthority() (spec (b)5).
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
/// Cleared at battle teardown. In S-A.1 the flag is only stored.
void requestDropNext();

} // namespace CoopDelta

} // namespace OpenXcom
