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

namespace OpenXcom
{

class Tile;
class TileEngine;
class BattleUnit;

/**
 * W1-P10 (rewrite wave 1, WAVE1-RUNBOOK.md SS4 "ATOM door", WV-D26/WV-D50):
 * the DOOR atom - host-authoritative terrain apply for the three vanilla door
 * transitions.
 *
 * WHAT A DOOR ACTUALLY CHANGES, and therefore why this atom exists at all
 * (all four anchors read at 78b20c5ea):
 *   * a NORMAL (swinging) door open REPLACES the tile's MapData for the part -
 *     `Tile::openDoor` does `setMapData(altMCD...)` + `setMapData(0,-1,-1,part)`
 *     (Tile.cpp:388-390), and `mapDataID`/`mapDataSetID` are exactly what the
 *     SS2.8 `terrain` bucket sums (SharedEcon.cpp:3843-3848);
 *   * a UFO door open sets `_objectsCache[part].currentFrame = 1`
 *     (Tile.cpp:403) - NOT in `terrain`, but serialized as `openDoorWest`/
 *     `openDoorNorth` (Tile.cpp:180-186) and as `binTiles` boolFields bits
 *     8/0x10 (Tile.cpp:209-210), i.e. inside the `saveBlob` bucket;
 *   * `TileEngine::closeUfoDoors` (TileEngine.cpp:4296) closes every open ufo
 *     door at the turn boundary through `Tile::closeUfoDoor` (Tile.cpp:416),
 *     which is the WV-D50 case W1-P13 reuses this packet's emit+apply path for.
 * A thin client runs no BState, so before this packet NONE of that reached it
 * and the first door a walk touched was a permanent divergence.
 *
 * SHAPE (SPIKE-RUNBOOK.md SS2.4's `ev door`, frozen by this packet):
 *   ev door {kind:"door", unit?:uid, op:"open"|"close", rClick?:bool,
 *            result?:int, tiles:[{x,y,z,part}...], tuAfter?:int,
 *            reveal?:revealDelta, h:{terrain, unitsStats}}
 * `tiles` is the EXACT list of (tile, part) pairs the HOST mutated, in mutation
 * order - never a description the client has to re-derive. That matters because
 * one call can open a whole RUN of ufo doors
 * (`TileEngine::checkAdjacentDoors`, TileEngine.cpp:4252) and because the
 * client must decide NOTHING: it replays the mutation, it does not re-run the
 * host's cost/permission logic.
 *
 * WV-D50 - CALLABLE OUTSIDE A WALK (binding). Neither the emitter nor the
 * applier assumes an in-flight walk or even an action context: the ev is
 * stamped with `CoopArbiter::currentActionId()`, which is legitimately 0 at the
 * turn boundary and for the right-click door path, and `unit` is presence-gated
 * (ABSENT for a boundary close). W1-P13 calls coopCloseUfoDoors() from
 * `BattlescapeGame::endTurn` (BattlescapeGame.cpp:549) instead of
 * `_save->getTileEngine()->closeUfoDoors()`.
 *
 * ALL LOGIC LIVES IN src/CoopMod (body: connectionTCP.cpp, next to the W1-P9
 * walk hooks). The vanilla files get FIVE thin guarded calls, no more:
 * Tile.cpp x3 (the journal) and UnitWalkBState.cpp / UnitTurnBState.cpp x1 each
 * (the wrapper that replaces the `unitOpensDoor` sub-expression - the same
 * shape W1-P9's `coopWalkReserveRefuses` uses).
 */

/// THE JOURNAL (host-side, armed only inside coopUnitOpensDoor()/
/// coopCloseUfoDoors()). Called from `Tile::openDoor` at the two returns that
/// have ACTUALLY MUTATED the tile - the normal-door branch (@a result 0) and
/// the ufo-door branch (@a result 1). A no-op outside an armed capture window,
/// which is every SP frame and every non-coop battle, so the vanilla path stays
/// byte-identical.
///
/// Journaling at `Tile::openDoor` rather than at `TileEngine::unitOpensDoor`'s
/// return is deliberate: `unitOpensDoor` reports ONE `door` result and a
/// (centre, count) pair, but a ufo-door run mutates a chain of tiles through
/// `checkAdjacentDoors` (TileEngine.cpp:4264/:4279), and reconstructing that
/// chain on the client would be re-derivation, not application.
void coopNoteDoorOpened(const Tile* tile, int part, int result);

/// The journal's close half - called from `Tile::closeUfoDoor` (Tile.cpp:430)
/// for each part it actually flipped shut. Same arming rule.
void coopNoteDoorClosed(const Tile* tile, int part);

/// THIN WRAPPER around `TileEngine::unitOpensDoor(unit, rClick, dir)` - ONE
/// guarded coop call per vanilla site, replacing the call sub-expression
/// (W1-P9's `coopWalkReserveRefuses` precedent). Outside a co-op battle, and on
/// any machine that is not the simulating host, it is EXACTLY
/// `te->unitOpensDoor(unit, rClick, dir)` and nothing else happens.
///
/// On the host it arms the journal, runs vanilla, and - if vanilla actually
/// mutated anything - emits ONE `ev door` describing every mutation, AFTER
/// vanilla's own TU spend and `calculateFOV` so that `tuAfter` is final and the
/// newly-discovered bits ride this envelope's `reveal` at the SS2.4a choke.
///
/// Covers BOTH producer paths in one function: the walk-time auto-open
/// (`UnitWalkBState.cpp:381`, rClick=false) and the right-click door
/// (`UnitTurnBState.cpp:86`, rClick=true) - the path SS2.4 reserved a `door`
/// field on the turn ev for and never applied.
int coopUnitOpensDoor(TileEngine* te, BattleUnit* unit, bool rClick, int dir);

/// THIN WRAPPER around `TileEngine::closeUfoDoors()` with the same contract -
/// the WV-D50 boundary-callable entry point. The ev it emits carries `op:
/// "close"`, NO `unit` and NO `tuAfter`, and rides `actionId 0`.
///
/// W1-P13 owns the vanilla call site (`BattlescapeGame.cpp:549`); this packet
/// ships the function and proves it through the `battle_close_ufo_doors`
/// test lever (RB-D26) so "boundary-callable" is a TESTED property and not a
/// claim about code nobody ran.
int coopCloseUfoDoors(TileEngine* te);

/// Test introspection only (RB-D26) - never read by game logic.
/// `coopDoorEvsEmitted()` counts `ev door` envelopes this machine SENT;
/// `coopDoorEvsApplied()` counts the ones it APPLIED; and
/// `coopDoorInTurnUnsupported()` counts hits on the SS2.4
/// "RW-UNSUPPORTED door-in-turn" fallback that this packet RETIRES - it is
/// kept as a tripwire and asserted at zero, because a retirement proven by
/// deleting the branch would be a retirement proven by nothing.
unsigned int coopDoorEvsEmitted();
unsigned int coopDoorEvsApplied();
unsigned int coopDoorInTurnUnsupported();

}
