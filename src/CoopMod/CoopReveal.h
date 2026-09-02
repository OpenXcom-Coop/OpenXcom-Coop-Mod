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

/**
 * RW-REVEAL-SYNC (rewrite spike, SPIKE-RUNBOOK.md SS2.4a): per-tile "discovered"
 * (fog-of-war) bits are GAME STATE, authored EXCLUSIVELY by the host and shipped
 * to every client as presence-gated `reveal` deltas riding the existing
 * host->client envelopes (bt_ev of any kind, bt_action_end), plus a standalone
 * `bt_ev{kind:"reveal"}` carrier for reveals that happen outside any action
 * context (bring-up, host-local reselection).
 *
 * Mechanism (Option A, owner-approved): the host keeps ONE "published" bitmap -
 * 1 byte per tile, bits in Tile::saveBinary's boolFields order (1 = O_WESTWALL,
 * 2 = O_NORTHWALL, 4 = O_FLOOR; Tile.cpp:207) - seeded from the live battle at
 * the moment the handshake blob is snapshotted (CoopHandshake::offerBattle).
 * Every host emit then diffs live-vs-published at the ONE emit choke
 * (CoopEmit::sendEv, connectionTCP.cpp) and attaches whatever became discovered
 * since the last publish. That absorbs EVERY reveal writer - present and future,
 * whether or not it belongs to an action - with zero per-atom code, which is why
 * attachment lives at the choke and never in an atom's own emit hook.
 *
 * Wire shape (SS2.4a, frozen):
 *   revealDelta := { "add":  [i0,b0, i1,b1, ...] }        # sparse delta
 *               |  { "base": "<base64>", "n": <int> }     # absolute restate
 * `add` is a FLAT array of 2*k integers: a tile's LINEAR INDEX (the
 * SavedBattleGame::getTileIndex order, 0 <= i < getMapSizeXYZ()) followed by the
 * bits that BECAME discovered on it. `base` is base64 of exactly `n` bytes, one
 * per tile in the same index order; `n` MUST equal the receiver's
 * getMapSizeXYZ() - a mismatch is a DESYNC (freeze + bt_desync + bundle +
 * banner), never a partial apply.
 *
 * Reveal is MONOTONE within one battle stage: bits are only ever ADDED, and a
 * client NEVER clears a bit from a revealDelta. Deltas are read back from the
 * host's live POST-state bits, so Tile::setDiscovered()'s own
 * O_FLOOR -> WESTWALL+NORTHWALL cascade (Tile.cpp:433-438) makes re-application
 * idempotent and convergent.
 *
 * CLIENT AUTHORITY RULE: a thin client MUST NOT compute tile FOV - the ONE thin
 * hook in TileEngine::calculateTilesInFOV suppresses it on hostSim == false, so
 * a client's discovered set is exactly (handshake blob) UNION (applied deltas).
 * calculateUnitsInFOV is untouched (per-unit `visible` stays machine-local and
 * is D4-excluded from saveBlob).
 *
 * With all of the above in force the saveBlob binTiles fog mask
 * (SharedEcon::saveBlobMaskFowBinTiles) is REMOVED: discovered bits are now
 * VERIFIED, synced state rather than a permanent hash carve-out.
 *
 * Storage (the published bitmap + the test levers' one-shot flags) lives in
 * connectionTCP.cpp next to the other battle-scoped coop globals (CoopPump/
 * CoopEmit/BattleAuthority) - this header only declares the API.
 */
namespace CoopReveal
{

/// HOST: snapshot @a battle's CURRENT discovered bits as "already published".
/// Called from CoopHandshake::offerBattle() immediately after the blob snapshot
/// (saveCoopToMemory), so the first delta the host ever ships carries exactly
/// what it revealed AFTER the client's copy was frozen. NOTE: it is called
/// EXPLICITLY there rather than behind an isCoopBattle() guard - phase is still
/// Handshake at that point, so isCoopBattle() is false (BattleAuthority.h).
/// No-op with a null @a battle.
void seedPublished(SavedBattleGame* battle);

/// HOST: true iff @a battle has at least one tile bit that is discovered live
/// but not yet published. Cheap (first-difference early-out) and side-effect
/// free - it never publishes anything. The dirty half of flushQuiescent()'s
/// predicate; also usable by test introspection.
bool hasUnpublished(SavedBattleGame* battle);

/// HOST: compute the live-vs-published delta for @a battle and, if non-empty,
/// attach it to @a env as the SS2.4a `reveal` field, marking those bits
/// published. Returns true iff a field was attached. Called from
/// CoopEmit::sendEv() - the single host emit choke - so bt_ev (every kind) and
/// bt_action_end both get it with no per-atom code.
bool attachDelta(SavedBattleGame* battle, Json::Value& env);

/// HOST: the standalone quiescent flush (SS2.4a's `ev reveal`). Emits ONE
/// bt_ev{kind:"reveal"} through the real CoopEmit::sendEv() (real seq, delta
/// attached by attachDelta() above) when, and only when, all of: this is an
/// active coop battle, this machine is the host sim, no coop action context is
/// open (CoopArbiter::currentActionId() == 0), the BState chain is quiescent,
/// and there is something unpublished. Idempotent by construction - a second
/// tick finds nothing unpublished and emits nothing. Called once per
/// connectionTCP::updateCoopTask() tick (RB-D5's pump point).
void flushQuiescent();

/// CLIENT: apply @a env's `reveal` field (SS2.4a) to @a battle, if present.
/// Handles both shapes: `add` (sparse, the only one the spike host emits) and
/// `base` (absolute restate - `n` must equal getMapSizeXYZ() or this raises a
/// desync and applies NOTHING). Safe to call for every applied envelope: a
/// no-op when the field is absent. Called from CoopDisplayQueue::onApplied()
/// BEFORE the state branch, so it covers bt_ev of any kind AND bt_action_end.
void applyFrom(SavedBattleGame* battle, const Json::Value& env);

/// Battle-teardown chokepoint: drops the published bitmap and both test-lever
/// flags. Called from CoopPump::reset() (BattlePump.h), the established single
/// battle-scoped reset point.
void reset();

// ----- TEST LEVERS (RB-D26 discipline: deterministic, minimal, test-only) -----

/// HOST, one-shot: make the NEXT attachDelta() compute and PUBLISH its delta but
/// NOT attach it - i.e. drop exactly one reveal delta on the floor. The client
/// then permanently lacks those bits, which (with the binTiles fog mask removed)
/// is now visible as a `saveBlob` divergence in a joint hash_now compare. Set by
/// TestServer's `reveal_drop` command; consumed by the next attachDelta().
void requestDropNextDelta();

/// HOST, one-shot: make the NEXT flushQuiescent() emit an ABSOLUTE `base`
/// restate of the whole live bitmap instead of a sparse `add` delta, so the
/// SS2.4a base path gets real coverage. @a badN advertises a deliberately wrong
/// `n` (getMapSizeXYZ() + 1), which the client must treat as a DESYNC (freeze +
/// bt_desync + bundle + banner) and never partially apply. Set by TestServer's
/// `reveal_base` command; consumed by the next flushQuiescent(), which fires it
/// even when nothing is unpublished (a base restate is meaningful regardless).
void requestBaseRestate(bool badN);

} // namespace CoopReveal

} // namespace OpenXcom
