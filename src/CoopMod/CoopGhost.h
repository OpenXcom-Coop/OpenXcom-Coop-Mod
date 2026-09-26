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
#include <string>

#include <json/json.h>

#include "../Battlescape/Position.h"

namespace OpenXcom
{

class BattleUnit;
class Map;
class SavedBattleGame;
class Tile;

/**
 * RW-REPLAY (W1-P12; WAVE1-RUNBOOK.md SS4b SPEC 7, rulings D-3 / WV-D27 /
 * WV-D49 / A4): the S3 GHOST STEPPER - a DISPLAY-ONLY replay of a partner's
 * turn/kneel/walk on the OBSERVING machine, so the action ANIMATES instead of
 * SNAPPING, without moving a single hash bucket.
 *
 * A4 IS ABSOLUTE: this mechanism writes animation/camera/sound/UI ONLY. It
 * never touches SavedBattleGame/BattleUnit/Tile (no setPosition/setDirection/
 * spendTimeUnits/startWalking/keepWalking - lint_no_replay_mutation.py is the
 * static guard). The apply/hash-verify clock (WV-D49/RB-D5) is NEVER gated,
 * delayed or reordered by this: CoopDisplayQueue::onApplied() (BattlePump.h)
 * already applies each ev/action_end AT DRAIN, atomically, in strict seq
 * order, immediately followed by CoopHashCheck::verify() - this packet only
 * adds ONE extra call inside that same function (onEvApplied() below),
 * BEFORE CoopApply::applyEvPayload() mutates the canonical unit, so a KNEEL
 * ghost can read the unit's PRE-apply kneeled bit (SS2.4's `kneel` ev payload
 * carries only the NEW value - the OLD one has to come from canonical state
 * while it is still true). `turn` and `walk_step` need no such read: their
 * payloads already carry both endpoints (fromDir/toDir; from/to).
 *
 * THE GHOST RENDERS FROM ITS OWN INTERPOLATION STATE, NEVER FROM BattleUnit
 * (the Phase-2c straddle lesson) - canonical positions/status are already
 * FINAL the instant apply runs (CoopApply's walk_step applier drives two
 * short-cycle `keepWalking(save, false)` calls, so the unit is back to
 * STATUS_STANDING before this packet's enqueue even sees it). So the DRAW
 * path cannot read canonical state for a unit with a live ghost - it has to
 * read a substitute. That substitute is `CoopUnitDrawView`: a read-only
 * mirror of everything Map::drawUnit / UnitSprite::draw read about a unit's
 * motion, built once from the canonical unit (`fromUnit()`) and then
 * OVERWRITTEN, field by field, ONLY for whatever a live ghost is animating
 * (`view()` below). With no live ghost (SP always; MP with nothing running
 * for this unit) `view()` is a no-op and every field stays exactly what
 * `fromUnit()` copied - so the substituted reads at the Map.cpp/UnitSprite.cpp
 * call sites are VALUE-IDENTICAL to the vanilla expressions they replaced.
 *
 * STORAGE lives in connectionTCP.cpp, inside the replay-region markers
 * lint_no_replay_mutation.py enforces (WV-D20: no new .cpp) - this header
 * only DECLARES the API + the CoopUnitDrawView data the DRAW path reads.
 * Nothing here has a body (all struct fields and pure declarations), so this
 * file needs no marker pair of its own - there is nothing in it the lint
 * could ever have anything to say about.
 */

/// W1-P12 (6a): everything the DRAW path reads about a unit's motion. Built
/// from the canonical BattleUnit (`fromUnit()`); a live ghost overwrites ONLY
/// what it animates. Read-only mirror - constructing one never touches the
/// unit, and nothing in this struct is ever written back to one.
struct CoopUnitDrawView
{
	Position pos;               // the tile the sprite is drawn FROM
	Position lastPos;           // vanilla _lastPos, for the mask/terrain lerp
	Position destination;       // vanilla _destination, for the mask/terrain lerp
	int  direction         = 0; // body facing 0-7
	int  turretDirection   = 0; // untouched by any ghost - copied straight through
	int  walkPhase         = 0; // raw, same domain as BattleUnit::_walkPhase
	int  verticalDirection = 0; // untouched by any ghost - copied straight through
	int  status            = 0; // UnitStatus as int
	bool kneeled           = false;
	bool ghostTrailing     = false; // see CoopGhost::view()'s walk branch

	/// Copies every field straight off @a u (0/false/default Position when
	/// @a u is null). Never mutates @a u - a plain read.
	static CoopUnitDrawView fromUnit(const BattleUnit* u);
};

namespace CoopGhost
{

/// TRUE and OVERWRITES the fields it animates in @a io when a ghost is
/// sweeping @a u on THIS machine right now (option on, a live coop battle,
/// @a u has an active replay record). FALSE (and @a io left exactly as the
/// caller's own CoopUnitDrawView::fromUnit(u) built it) in SP, with the
/// option off, outside a coop battle, or for any unit with no active ghost.
/// READS ONLY - never touches @a u.
bool view(const BattleUnit* u, CoopUnitDrawView* io);

/// The unit whose ghost is still sweeping OUT of @a tile even though the
/// canonical unit has already left it (a WALK ghost's "trailing" half - see
/// (6c)), or nullptr. Lets Map::drawUnit's from-tile pass keep showing the
/// sprite mid-stride instead of losing it the instant apply lands. READS
/// ONLY - never touches @a save or @a tile.
BattleUnit* trailingUnitOverTile(const SavedBattleGame* save, const Tile* tile);

/// Enqueues the ghost for one applied `bt_ev` - called from
/// CoopDisplayQueue::onApplied() (connectionTCP.cpp) for `ev.kind` in
/// {"turn","kneel","walk_step"}, BEFORE CoopApply::applyEvPayload() mutates
/// the named unit (see this header's own file comment for why: the `kneel`
/// case needs the PRE-apply kneeled bit). A ghost already running for the
/// SAME unit is completed INSTANTLY (dropped to its end state) and replaced -
/// the display clock never gates apply (WV-D49). No-op when
/// Options::coopGhostStepper is false, outside a coop battle, for any other
/// `kind`, or when @a save/the payload's unit does not resolve.
///
/// W2-P5 S-A.2 (spec rewrite/prompts/w2p5_display_ghosts.md (b)1-6, (b)8-11 for `shot`; amendments E1, E2):
/// on a coop CLIENT this is also the COMBAT ghost's single bt_ev entry. Q1 (b): every applied ev except a
/// `reveal` first ends every running combat ghost (cut when its fixed duration has not elapsed), and a `shot`
/// also completes the shooter's own running SPEC 7 ghost; OQ3: that completion rule is never gated by
/// Options::coopGhostStepper, only STARTING a ghost is. An applied `shot` then starts one display-only
/// projectile ghost: a vanilla Projectile on the live Map flying the path re-derived with vanilla's own path
/// function (straight: TileEngine::calculateLineVoxel toward the payload's farVoxel, E2; arc:
/// calculateParabolaVoxel from the payload's `arc`), paced by the shooter's seat fire dial (SPEC 17) and
/// fixed at enqueue, with the fire / throw sound. No battle-state write, no sim RNG, no BState, no camera
/// move (follow is switched off while the ghost's projectile is on the Map and restored after).
void onEvApplied(SavedBattleGame* save, const Json::Value& ev);

/// W2-P5 S-A.2 (spec (b)2, Q1 (b)): the combat completion rule for an applied `bt_action_end` - every running
/// combat ghost ends (cut when early) before the end's delta applies. Called from
/// CoopDisplayQueue::onApplied()'s bt_action_end branch on the line before its CoopApply::applyDelta(). Never
/// gated by the option (OQ3); a no-op on the host and outside a coop battle.
void onActionEndApplied(SavedBattleGame* save, const Json::Value& ev);

/// W2-P5 S-A.2 (Q3 = b): TRUE when @a map's projectile is a combat ghost's own display object on this
/// machine, so BattlescapeState::allowButtons() does not lock the watching player's input during a
/// partner's or an alien's shot. FALSE in single player, on the host and whenever the Map shows no ghost
/// projectile. Reads only (a pointer compare).
bool ownsProjectile(const Map* map);

/// Advances every running ghost by one frame of wall-clock time - called
/// once per frame from BattlescapeState::think()'s existing per-frame path
/// (step 5, SDL-tick clock). A ghost whose interpolation has finished
/// (walk: progress>=1; turn: every octant stepped; kneel: the 100ms hold
/// elapsed) is popped here, handing the unit's rendering back to canonical
/// state on the very next draw. No-op outside a coop battle; still drains
/// (never strands) whatever is already queued even with the option off, so a
/// mid-flight toggle cannot leave a ghost stuck forever.
///
/// W2-P5 S-A.2: also steps every combat ghost's projectile to its index at
/// @a nowMs (vanilla's 16 ms tick, `speed` points a tick) and ends it when its
/// fixed duration elapsed, the Map it was drawn on is no longer the live one,
/// or a thrown item no longer resolves to the pointer captured at enqueue
/// (spec (b)9). Q5 (a): invalidates the live Map every frame while ANY ghost
/// (SPEC 7 or combat) is live, so ghosts draw at the frame rate.
void advance(SavedBattleGame* save, std::uint32_t nowMs);

/// Drops every ghost record and resets the enqueued/completed counters.
/// Called from CoopPump::reset()'s battle-teardown chokepoint, alongside
/// CoopReveal::reset() - the ghost queue is battle-scoped exactly like that
/// storage.
void reset();

// ----- event_state introspection (TestServer.cpp) - never read by game
// logic, only by tests proving delivery instead of inferring it from an
// absence (the coopWalkArmEntered/coopDoorEvsEmitted precedent). -----------

/// How many ghosts have been enqueued this battle (one per applied
/// turn/kneel/walk_step ev, per onEvApplied()'s own doc comment).
unsigned int enqueuedCount();

/// How many ghosts have run their interpolation to completion (popped by
/// advance()) this battle - INCLUDES a ghost that was completed instantly
/// because a later ev for the same unit arrived first (WV-D49).
unsigned int completedCount();

/// How many ghosts are mid-sweep RIGHT NOW (one slot per unit with a live
/// ghost).
unsigned int queueDepth();

/// SPEC 17 (W1-P18) M4: the last ghost THIS machine enqueued this battle -
/// kind/frame-count/fixed-duration/owning-seat, proving the per-seat pacing
/// derivation delivered (control (ii)'s own evidence) rather than merely
/// that a ghost ran. Empty kind ("") before the first ghost this battle.
struct GhostLastView
{
	std::string kind;
	int frames = 0;
	unsigned ms = 0;
	int seat = -1;
};

/// The last ghost enqueued this battle (SPEC 17 M4 probe above) - default/
/// empty before the first one. Read-only test introspection, same rule as
/// enqueuedCount()/completedCount()/queueDepth() above.
GhostLastView lastGhost();

/// W2-P5 S-A.1 (spec rewrite/prompts/w2p5_display_ghosts.md (b)11, amendment E1 PR-E5): the combat-ghost
/// probe of THIS machine this battle - {enqueued:{shot,hit,explosion}, completed:{...}, cut:{...},
/// joined, live, unresolved, noMap, ring:[the last 32 ghost records]}. Kept apart from the SPEC 7
/// counters above. Main thread only (E1 OQ4 = (a)): reset() bumps a generation, this storage is
/// cleared on its next main-thread use (after every stale ghost has left the live Map and been
/// deleted). Written by the S-A.2 combat ghosts: one ring record and one `enqueued` count per started
/// ghost; a record with no display object (unresolved / noMap / 0 ms) counts `completed` at enqueue.
Json::Value combatProbe();

/// W2-P5 S-A.1 (amendment E1 PR-E2; S-A.2 amendment E2): CLIENT, probe only, called from
/// CoopApply::applyEvPayload()'s cue branch for an applied `shot` (before applyDelta): re-derive the
/// shot's path the way the ghost does - straight: TileEngine::calculateLineVoxel from originVoxel toward
/// the payload's farVoxel (E2); arc: calculateParabolaVoxel from its `arc` - the shooter excluded, into a
/// local vector, and record {seq, arc, derivedLen, derivedEnd} (derivedLen -1 and derivedEnd null when the
/// payload lacks the voxels). No display object, no battle-state write, no RNG.
void probeDeriveShotPath(SavedBattleGame* save, const Json::Value& ev);

/// The last 32 probeDeriveShotPath() records this battle, oldest first (an empty array on the host).
Json::Value derivedPaths();

} // namespace CoopGhost

} // namespace OpenXcom
