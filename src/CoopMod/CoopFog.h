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
#include <vector>

#include "../Mod/MapData.h" // TilePart

namespace OpenXcom
{

class SavedBattleGame;
class BattleUnit;
class Tile;

/**
 * RW-DUAL-FOG (W1-P8; WAVE1-RUNBOOK.md SS2.W4, rulings D2 / WV-D8 / WV-D31 /
 * WV-D39): the HOSTILE half of the DUAL-SET per-side reveal model.
 *
 * SS2.W4's storage rule is deliberately ASYMMETRIC:
 *   - side "player"  -> the VANILLA per-tile discovered bits
 *                       (Tile::setDiscovered / Tile::isDiscovered), storage
 *                       untouched, so SINGLE PLAYER STAYS BIT-IDENTICAL and
 *                       every SS2.4a proof shipped by the spike keeps working;
 *   - side "hostile" -> the COOP-OWNED byte-per-tile bitmap declared here.
 *                       getMapSizeXYZ() bytes, the SAME linear tile-index order
 *                       and the SAME three bits as SS2.4a
 *                       (1 = O_WESTWALL, 2 = O_NORTHWALL, 4 = O_FLOOR;
 *                       Tile::saveBinary's boolFields order, Tile.cpp:207).
 *                       It NEVER writes Tile.
 *   - side "neutral" is RESERVED: wave 1 never authors it. A receiver that sees
 *                       one logs `RW-UNSUPPORTED reveal-side-neutral` and lets
 *                       the next hash call it a desync (SS2.W4; the SS2.4
 *                       `door`-in-turn precedent - correct, the state HAS
 *                       diverged).
 *
 * BOTH machines hold BOTH sets and both are kept equal by the wire: every
 * machine applies EVERY side-tagged `revealDelta` into the set the delta names,
 * with NO receive-side filtering. That is what makes both sets HASHABLE, which
 * is the whole point of D-8 - full desync-detector coverage in PvP.
 *
 * WHERE THE HOSTILE BITS COME FROM (the bulk of this packet). Vanilla authors
 * discovered bits for FACTION_PLAYER units ONLY - `TileEngine::
 * calculateTilesInFOV` early-returns for every other faction at
 * TileEngine.cpp:1556, and that early return is COMPOUND
 * (`unit->getFaction() != FACTION_PLAYER || (eventRadius == 1 &&
 * !unit->checkViewSector(...))`). SS2.W4/WV-D39 forbid relaxing it, because
 * loosening the faction test changes SP behaviour. So the hostile sweep is an
 * ADDITIONAL, COOP-ONLY, HOST-ONLY pass: authorHostilePass() below reproduces
 * vanilla's FULL-sweep tile geometry (same direction/eye/bresenham structure,
 * driven through the PUBLIC TileEngine::calculateLineTile) and writes ONLY into
 * this bitmap.
 *
 * WHY IT IS A SEPARATE SWEEP RATHER THAN A WRITE-SWITCH INSIDE VANILLA'S LOOP
 * (traced, W1-P8 - this is a DEVIATION FROM THE NAMED MECHANISM, recorded so it
 * is never silently re-litigated): SS2.W4 names the three
 * `Tile::setDiscovered` calls at TileEngine.cpp:1663/:1667/:1669 as "the write
 * site". Routing THOSE is necessary but NOT sufficient, because entering
 * vanilla's body for a non-player unit also runs THREE other state writes the
 * client never mirrors:
 *   - `unit->clearVisibleTiles()`      (TileEngine.cpp:1583)
 *   - `unit->addToVisibleTiles(...)`   (TileEngine.cpp:1661)
 *   - `tile->setVisible(+1)`           (TileEngine.cpp:1662)
 * The last one is the trap the W1-P15 item-6 audit calls FINDING A-5:
 * `Tile::_visible` is a DIFFERENT field from the discovered bits and it is a
 * SIM input - `Pathfinding.cpp:228` and `:1413` change walk COST and path
 * validity under `sneak` from it, i.e. exactly SS2.W2's `cost_changed` /
 * `path_changed` surface. Incrementing it on the host only, for aliens, would
 * diverge pathing. A CoopMod-side sweep writes none of the three, needs no edit
 * to TileEngine.cpp at all, and therefore satisfies SS2.W4's "an ADDITIONAL
 * coop-only pass, never a relaxation of the :1556 condition" in the strongest
 * possible form: ZERO vanilla FOV edits.
 *
 * FIDELITY NOTE (why the duplicated geometry is safe): there is no vanilla
 * ground truth for a hostile reveal set - it does not exist in vanilla - so
 * this sweep cannot "disagree with vanilla". What it must do is be the SAME on
 * both machines, and it is by construction: the HOST is the sole author and
 * the client only ever applies the host's deltas (SS2.4a client-authority
 * rule). Geometry fidelity is a QUALITY property (does the alien side's fog
 * look like what the aliens can see), never a desync surface.
 *
 * HASH: the bitmap gets its OWN bucket `revealHostile` (SPIKE-RUNBOOK SS2.8),
 * FNV-1a 64 over the whole bitmap in linear tile-index order, rendered as 16
 * lowercase hex like every other bucket. Per the W1-P15 item-7 audit's R-5 it
 * is computed OUT OF BAND - a free function here, NOT an 8th BattleHashSet
 * member - which keeps `SharedEcon::computeBattleHashes` a pure function of the
 * battle document and makes WR-26's "key ABSENT, not zero" trivial. The bucket
 * is OMITTED in SP, in any non-coop battle, and wherever this storage is
 * unallocated.
 *
 * COVERAGE ASTERISK (W1-P15 item 2, recommendation R-4 - state it, never claim
 * more): the two sets are NOT symmetrically hashed. This bitmap covers EVERY
 * tile index including void ones; the player-side set is hashed through
 * `binTiles` -> `saveBlob`, and `SavedBattleGame::save` SKIPS void tiles
 * (SavedBattleGame.cpp:568-579), so player-side fog on tiles that are
 * `Tile::isVoid()` on BOTH machines is inside no bucket at all. It is covered
 * by `reveal_state`'s aggregate census, which is why that assert exists and
 * must not be deleted as redundant. `reveal_state.discoveredVoid` (W1-P8, the
 * audit's R-2) is the measurement of whether that hole is populated.
 *
 * STORAGE lives in connectionTCP.cpp next to CoopReveal's own published bitmap
 * (WV-D20: no new .cpp); this header only declares the API.
 */
namespace CoopFog
{

/// SS2.W4's `revealDelta.side` values. Player is the DEFAULT (an absent `side`
/// key means Player - back-compatible with every SS2.4a producer the spike
/// shipped).
enum class Side { Player, Hostile, Neutral };

/// The wire spelling of @a s: "player" | "hostile" | "neutral". Never anything
/// else - this is what goes into `revealDelta.side`.
const char* sideName(Side s);

/// Parses an SS2.W4 `side` value. An EMPTY string (i.e. an ABSENT key) is
/// Player. Returns false for an unrecognised value, leaving @a out untouched.
bool sideFromString(const std::string& s, Side& out);

/// The side that is currently ACTING in @a battle, i.e. the side whose delta
/// SS2.W4/WR-5 says rides the envelope itself (every other side's bits ship as
/// their own `bt_ev{kind:"reveal"}`). Derived from SavedBattleGame::getSide(),
/// so it needs no new plumbing and is right in both co-op and PvP. Player when
/// @a battle is null.
Side actingSide(SavedBattleGame* battle);

// ----- the hostile-side reveal set (coop-owned storage) ---------------------

/// Allocate the bitmap (ZEROED) for @a battle unless it is already sized for
/// it. Called on BOTH machines the moment the battle reaches phase Active, so
/// the `revealHostile` bucket appears in both machines' sweeps at the SAME
/// moment and a bucket-set comparison can never see a one-sided key. No-op with
/// a null @a battle or a zero-size map.
void ensureAllocated(SavedBattleGame* battle);

/// True iff the bitmap is currently allocated. This is WR-26's condition: false
/// => the `revealHostile` bucket is OMITTED (key absent, not zero).
bool allocated();

/// Bytes the bitmap covers (0 when unallocated).
int size();

/// The byte for tile index @a i (0 when unallocated or out of range).
std::uint8_t bits(int i);

/// Copies the whole bitmap into @a out (resized). False when unallocated.
bool snapshot(std::vector<std::uint8_t>& out);

/// Monotone OR of @a b into tile index @a i. Returns how many of the three
/// parts NEWLY became discovered (0 when unallocated / out of range / nothing
/// new). Mirrors Tile::setDiscovered's O_FLOOR -> WESTWALL+NORTHWALL cascade
/// (Tile.cpp:433-438) so the coop set converges exactly like the vanilla one.
int applyBits(int i, std::uint8_t b);

/// Per-part census of the bitmap, for the `reveal_state` probe.
void census(int& floor, int& west, int& north);

/// SS2.8 bucket `revealHostile`: FNV-1a 64 over the whole bitmap in linear
/// tile-index order. Returns FALSE when the storage is unallocated - the caller
/// must then OMIT the bucket entirely (WR-26: key absent, never zero).
bool computeHash(std::uint64_t& out);

/// RB-D26 test lever behind `corrupt_bucket {name:"revealHostile"}`: a minimal
/// DETERMINISTIC poke straight into the bitmap, bypassing the emit path
/// entirely. Returns false when there is nothing allocated to corrupt.
bool corrupt();

/// Drops the bitmap and all its bookkeeping. Called from THREE places, and it
/// needs all three: the SESSION-teardown chokepoint (CoopPump::reset, via
/// CoopReveal::reset) and, because that one does NOT run between two battles
/// of one campaign, each machine's own PER-BATTLE point - the host's
/// CoopReveal::seedPublished() at offer time and the client's phase-Active
/// site in CoopHandshake::finishLoad().
void reset();

// ----- HOST authoring -------------------------------------------------------

/// HOST: the coop-only hostile-side FOV sweep (see the file comment). Sweeps
/// every LIVE FACTION_HOSTILE unit whose (position, direction, turret) changed
/// since its last sweep - or ALL of them when @a force. Returns how many tile
/// parts it newly discovered. No-op off the host sim, outside a coop battle, or
/// with the bitmap unallocated. Writes ONLY the coop bitmap: it never touches
/// Tile, BattleUnit, or any TileEngine member.
int authorHostilePass(SavedBattleGame* battle, bool force);

/// RB-D26 test lever: arm a FORCED hostile pass to be run by the NEXT emit
/// (consumeArmedPass() below, called from CoopEmit::sendEv). This exists so a
/// wave-1 fixture - which never runs an alien turn - can arrange the SS2.W4/WR-5
/// premise "an action reveals for BOTH sides" DETERMINISTICALLY: arm, then act,
/// and the hostile bits are minted inside the acting envelope's own emit rather
/// than by whichever pump tick happened to win a race.
void armForcedPass();

/// Returns and CLEARS the armForcedPass() flag. Called only from the emit choke.
bool consumeArmedPass();

/// SS2.W5's SIDE-BEGIN half: recalculates TILE FOV (and nothing else) for every
/// live unit of @a faction, so a side beginning its turn - battle entry
/// included - restates its own reveal set deterministically, over ALL its units
/// rather than whichever one happened to be selected. Returns how many units it
/// swept. Authors ONLY discovered bits: `doUnitRecalc` is false, so it mints no
/// unit visibility, spots nobody and touches no hash bucket.
int authorSideBeginFov(SavedBattleGame* battle, int faction);

/// Diagnostics from the LAST authorHostilePass(): how many FACTION_HOSTILE
/// units the battle holds, how many of those were live and on a tile, and how
/// many were actually swept (the rest were dirty-track hits). Exposed so a
/// fixture can prove its own premise - "there were aliens to sweep" - instead
/// of inferring it from a tile count.
void lastPassStats(int& hostileUnits, int& candidates, int& swept);

} // namespace CoopFog

// ===== SS2.W5 (D2 / WV-D8): G-2 action-only reveals =========================
//
// CONTRACT, not schema: shared fog is authored by ACTIONS and side-begin
// restates ONLY. A selection change - TAB, click-select, right-click undo, the
// battle-entry auto-select, the HUD refresh - must not author it.
//
// MECHANISM (SS2.W5's own words): "coop-gated checkFOV=false on the selection
// paths plus an explicit acting-unit FOV recalc". The chain it names is
// `BattlescapeState::updateSoldierInfo(bool checkFOV = true)`
// (BattlescapeState.h:234) -> `calculateFOV(getSelectedUnit())`
// (BattlescapeState.cpp:2445), and the kneel chain that proves the coupling is
// `BattlescapeGame::kneel` -> `calculateFOV(pos)` + `updateSoldierInfo()`
// (BattlescapeGame.cpp:498-499).
//
// The two hooks below are that mechanism, placed so the suppression is TOTAL
// (one site, not N selection call sites, so a selection path added later cannot
// forget to opt out) and so the authoring is EXPLICIT and ACTOR-relative.
/// SS2.W4 READ-SWITCH: does THIS MACHINE's local seat see @a part of @a tile as
/// discovered? Rendering, the minimap and the path preview ask this instead of
/// `Tile::isDiscovered`, so a seat commanding the HOSTILE side renders the
/// hostile side's reveal set rather than X-Com's.
///
/// A NO-OP everywhere except a PvP seat on a non-player side. Outside a co-op
/// battle, and in classic co-op where every seat is player-side
/// (`factionOf(localSeat) == FACTION_PLAYER`), it returns exactly
/// `tile->isDiscovered(part)` after two atomic loads - so SP and classic co-op
/// are bit-identical. W1-P14's gm2 run is what exercises the switched branch,
/// and SS2.W4 puts its acceptance there.
///
/// IT IS AN ACCESSOR, NEVER A STATE CHANGE, and `Tile::isDiscovered` keeps
/// returning the RAW vanilla bits - its non-rendering readers need them:
/// `Tile::saveBinary` (Tile.cpp:207) reads `_objectsCache[...].discovered`
/// DIRECTLY into `binTiles` and therefore into the `saveBlob` bucket
/// (W1-P15 item-6 FINDING A-1), and the TestServer probes must keep reporting
/// raw bits or they could no longer prove both sides' sets are equal
/// (FINDING A-3).
///
/// Call sites = the audit's EXHAUSTIVE presentation set and nothing else:
/// `Map.cpp` :415 :425 :685 :918 :1224 :1288 :1622 and `MiniMapView.cpp`
/// :110 :138 (item-6 FINDING A-2).
bool coopTileDiscoveredHere(const Tile* tile, TilePart part);

/// SS2.W5 hook 1 - `BattlescapeState::updateSoldierInfo`'s `if (checkFOV)`
/// branch. TRUE inside an active co-op battle: the selected unit's TILE FOV
/// half is skipped, so no selection change can author shared fog. FALSE
/// everywhere else, so SINGLE PLAYER IS BIT-IDENTICAL.
///
/// It suppresses the TILE half only. The UNIT half (`calculateUnitsInFOV`)
/// still runs, because the very next lines of updateSoldierInfo() paint the
/// visible-unit indicator buttons from `getVisibleUnits()`; killing that too
/// would be a visible co-op HUD regression and is NOT what D2 asked for.
/// Per-unit `visible` is machine-local and D4-excluded from saveBlob, so
/// keeping it costs no hash coverage.
bool coopSuppressSelectionTileFov();

/// SS2.W5 hook 2 - the explicit ACTING-UNIT recalc that replaces what the
/// selection path used to do by accident. Recalculates @a actor's own TILE FOV
/// (never the selected unit's) inside an active co-op battle on the host sim;
/// a no-op otherwise, so SP is bit-identical.
///
/// It also CLOSES A PRE-EXISTING GAP rather than merely preserving behaviour:
/// vanilla's kneel path recalculates tiles for the SELECTED unit, but an
/// admitted REMOTE kneel intent runs on a unit the host has not selected, so
/// the acting unit's own tile FOV was never recalculated at all on the host.
void coopAuthorActingUnitFov(BattleUnit* actor);

} // namespace OpenXcom
