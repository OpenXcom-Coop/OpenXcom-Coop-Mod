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

#include <string>
#include <vector>

namespace OpenXcom
{

class SavedBattleGame;
class BattleUnit;
class Craft;
class Game;
class GeoscapeState;
class Vehicle;
enum UnitFaction : int; // Mod/Unit.h; forward-declared here the same way Mod/RuleItem.h does

/**
 * The ONE generation-time pass that sets canonical per-unit factions and seat
 * tags. Called once by
 * CoopHandshake::offerBattle() (connectionTCP.cpp) right after vanilla
 * BattlescapeGenerator::run() has produced @a save - the same
 * generation-complete moment every offerBattle() call site already reaches
 * before it ships battle_offer. HOST-ONLY: a client never generates, so it
 * never calls this - it gets the real per-unit factions/seats over the wire
 * inside the streamed battle blob, and the real seat->faction store off the
 * battle_offer seatMap this pass produces (see connectionTCP.cpp). Body
 * lives in CoopState.cpp.
 *
 * @a gamemode is connectionTCP::_coopGamemode :
 *
 *   0/1 (classic/SHARED) - every FACTION_PLAYER-original unit keeps
 *     FACTION_PLAYER; each one with a Soldier owner
 *     (BattleUnit::getGeoscapeSoldier()) is seat-tagged from that Soldier's
 *     OWN pre-generation Soldier::getCoop() ownership stamp (the
 *     Cydonia/base-defense callers, and the SHARED ownership-sync sites in
 *     connectionTCP.cpp, already write it before generation runs - this
 *     pass only reads it back). A FACTION_PLAYER unit with no valid Soldier
 *     owner (an HWP, a soldier whose owner is not one of @a seats) gets
 *     coopSeatForUnownedUnit()'s seat (seat 0). Civilians and any real
 *     mission aliens get COOP_SEAT_NONE: nobody commands them.
 *
 *   2/3 (PvP) - the SAME generated battle (real X-COM soldiers +
 *     AlienDeployment-spawned aliens, exactly like SP - see pvp_fixture.py's
 *     "gamemode 2: host=XCOM, client=Alien" contract) is split by its
 *     EXISTING vanilla faction, never by soldier ownership: gamemode 2
 *     seats the FACTION_PLAYER group at seat 0 and the FACTION_HOSTILE group
 *     at seat 1; gamemode 3 inverts that (seat 0 hostile, seat 1 player).
 *     Whichever seat ends up commanding the FACTION_HOSTILE group has its
 *     units' AI modules cleared (BattleUnit::setAIModule(nullptr)) - they
 *     are human-commanded from here on, not the alien-turn AI. Civilians
 *     (FACTION_NEUTRAL) are never assigned a seat in any gamemode. Every
 *     unit this pass gives a real faction to gets it funneled through the
 *     new BattleUnit::setOriginalFaction() + the existing convertToFaction()
 *     - never a direct field write - so every setOriginalFaction write goes
 *     through this ONE pass, even though gm2/3 only reasserts the SAME
 *     faction vanilla generation already gave the unit (PvP seat assignment
 *     follows the EXISTING faction and never flips a soldier's own side).
 *
 *   4 (PvE2) - both seats command the generated
 *     aliens against an AI-run X-COM squad. Every FACTION_HOSTILE-original
 *     unit becomes FACTION_PLAYER (AI module cleared), the first floor(N/2)
 *     of them in unit-list order seated to the client seat and the rest to
 *     seat 0; every
 *     FACTION_PLAYER-original unit becomes FACTION_HOSTILE and unseated (the
 *     host's alien-turn AI runs it); civilians stay unseated. Both seats map
 *     to FACTION_PLAYER.
 *
 * @a seats is the battle's active seat list (no 2-seat assumption baked into
 * the signature). The game only ever calls
 * this with connectionTCP::seatCount()'s current {0..seatCount()-1} (2
 * seats: host=0, client=1, connectionTCP::localSeat()'s own transport
 * convention). Used two ways: (a) this pass calls
 * coopBattleAuthority().setSeatFaction() for every seat in @a seats,
 * populating the seat->faction store; (b) in
 * the classic/SHARED branch, a Soldier::getCoop() value that is not present
 * in @a seats (stale/out-of-roster ownership) falls back to coopSeatForUnownedUnit()'s seat
 * rather than mis-seating a unit to a seat nobody occupies this battle.
 *
 * `Soldier::_cooptype` re-skin (donor BriefingState.cpp's alien-looking-unit
 * swap for a squad-vs-squad PvP hostile side) is NOT implemented here. This pass
 * only tags seat
 * + faction; it never touches BattleUnit::getUnitRules()/setUnitRulesCoop().
 */
void assignSeatsAndFactions(SavedBattleGame* save, int gamemode, const std::vector<int>& seats);

/**
 * The canonical seat->faction rule assignSeatsAndFactions() above applies
 * per-unit at generation, exposed here so CoopHandshake::offerResumedBattle()
 * (connectionTCP.cpp, a disk resume) can rebuild BattleAuthority's
 * seat->faction store from the SAME canonical map over the LOADED units'
 * persisted seat tags (BattleUnit::getCoopSeat()) - not through
 * assignSeatsAndFactions() (a generation-time pass, not called on resume) and
 * not from Soldier::getCoop(). Body lives in CoopState.cpp, beside
 * assignSeatsAndFactions().
 */
UnitFaction coopSeatCanonicalFaction(int gamemode, int seat);

/**
 * The
 * seat that commands a unit NO player of this battle owns - an HWP (no Soldier owner), a unit created
 * mid-battle, a soldier whose owner is not one of the battle's seats. It is the LOWEST seat the
 * seat->faction store maps to @a faction (BattleAuthority::seatMapped() and factionOf()): classic / SHARED
 * FACTION_PLAYER -> seat 0, the host; PvP gm2 FACTION_HOSTILE -> seat 1 and gm3 FACTION_HOSTILE -> seat 0,
 * the player of that side; a faction no seat maps (co-op aliens and civilians, PvP civilians) ->
 * COOP_SEAT_NONE, the AI's. assignSeatsAndFactions() seats the 0/1 branch's unowned units through this.
 * Read-only.
 */
int coopSeatForUnownedUnit(int faction);

/**
 * The HOST's seat stamp for a unit created mid-battle, called
 * by the `spawn` cue hooks (connectionTCP.cpp coopCueSpawn() / coopCueSpawnAdded()) BEFORE the cue is
 * sent, so the seat rides the unit's `unitsAdded` record (BattleUnit::save() writes `coop`). Seats @a unit
 * with coopSeatForUnownedUnit() of its original faction; a non-player unit a seat now commands (a PvP
 * side's) also loses its AI module, as assignSeatsAndFactions() does at generation. Null, an already
 * seated unit and a unit of a faction no seat maps are left unchanged.
 */
void coopStampSpawnedUnitSeat(BattleUnit* unit);

/**
 * The owner->seat stamp for ConfirmLandingState::btnYesClick, the entry every
 * mission-site/UFO battle takes (the other three craft-generation entry sites,
 * ConfirmCydoniaState.cpp and GeoscapeState.cpp's SHARED and SEPARATE base
 * defense, stamp seats inline). For every soldier of @a craft's base seated on @a craft
 * (Soldier::getCraft() == @a craft): setCoop(owner == 999 ? 0 : owner) - the
 * N-seat-correct shape already used post-battle (GeoscapeState.cpp:986-989,
 * giftSoldier, SharedEcon.cpp:1522), not the three existing sites' 2-seat-only
 * `(owner == 0 || owner == 999) ? 0 : 1` shape. For every vehicle of @a
 * craft: setCoop(0) (HWPs are not seated by owner - assignSeatsAndFactions()
 * above has no Soldier owner to read for them).
 *
 * Deliberately does NOT write coopBase: the post-battle cleanup
 * (GeoscapeState.cpp:975-1005) keys a transferred guest's survival on
 * `coopBase != -1`, so this stamp must never clear it; Cydonia's own
 * `setCoopBase(-1)` is Cydonia's site's call and is untouched.
 *
 * Called ONCE, from ConfirmLandingState::btnYesClick, inside a new
 * `if (coopLanding)` block placed immediately BEFORE vanilla `bgen.run()` -
 * the same stamp-then-generate order Cydonia and both base-defense arms use
 * (a merged/seated guest must be on the craft at generation time to be
 * deployed at all). Runs for SHARED and SEPARATE alike: in SHARED it is the
 * whole fix; in SEPARATE the host's own soldiers are owner 999/0 -> a
 * seat-0 no-op, while a guest merged onto the craft by
 * coopMergeGuestContributions() just above this call carries the client's own
 * seat in ownerPlayerId already, so this reasserts (not assigns) its coop
 * seat. Body lives in CoopState.cpp, beside assignSeatsAndFactions().
 */
void coopStampCraftSeats(Craft* craft);

/**
 * The SEPARATE two-world merge, with generation kept SYNCHRONOUS - the legacy
 * trigger chain (CoopState(88)/"sendCraft"/CoopState::loadWorld(111)) is not
 * reached on the craft-landing path. This is its
 * replacement: for every seat whose latest stored `battle_roster_contrib`
 * (BattleWire.h; connectionTCP::sendGuestRosterContrib() sender,
 * connectionTCP.cpp's onTCPMessage() "battle_roster_contrib" handler +
 * per-seat store) names THIS craft (craft id + type), materialise each not
 * already present (by name + ownerPlayerId - no
 * coopOriginId field exists on Soldier, so that pair is the only key
 * available) exactly as the legacy loadWorld(111) merge did: `new Soldier` +
 * `load(yaml)`, `setId(lastId + 1)`, `setCoop(seat)`,
 * `setOwnerPlayerId(seat)`, `setCoopBase(-1)` (a merged COPY - the post-battle cleanup deletes
 * it post-battle, matching legacy: the durable original lives on in the
 * client's world), push onto @a craft's base's roster,
 * `setCraftAndMoveEquipment(craft, base, monthsPassed == -1)` space
 * permitting (on the craft BEFORE generation, or vanilla's generator
 * never deploys it).
 *
 * Called ONCE, from ConfirmLandingState::btnYesClick, inside the same
 * `if (coopLanding)` block as coopStampCraftSeats() above, BEFORE it (a
 * freshly-merged guest's ownerPlayerId is what the stamp then reads).
 * HOST-ONLY (a client never generates - the same reasoning
 * coopStampCraftSeats() itself documents); a no-op when nothing was ever
 * contributed for this craft (every classic/SHARED/skirmish call, and any
 * SEPARATE landing with no SEPARATE guest waiting). Body lives in
 * CoopState.cpp.
 */
void coopMergeGuestContributions(Game* game, Craft* craft);

/**
 * A SEPARATE partner's
 * own tank parked on the host's craft (its world tags it coopbase / coopcraft / coopcrafttype; its census sends it as
 * battle_roster_contrib `vehicles`). HOST-ONLY; the three bodies live in connectionTCP.cpp beside the guest store.
 *
 * coopMergeGuestVehicles(): the last step of coopMergeGuestContributions() (after the guest soldiers): every stored
 * parked tank of every seat for @a craft gets a COPY on the craft (Craft::makeCoopVehicle) when the
 * host's stores hold a spare of its type for it (counted per tank) and the craft has room in
 * its whole capacity and a free vehicle slot; returns how many. coopTagGuestVehicleUnit():
 * BattlescapeGenerator::addXCOMVehicle's one coop line - a merged copy's battle unit gets the tag
 * "coop-guest-tank:<seat>:<host base coop id>:<craft id>:<craft type>" (BattleUnit::setCoopGuestTank, saved with the
 * unit, so a rejoin, a mid-battle save and stage 2 keep it); a no-op for every other vehicle and outside a landing.
 * coopDropMergedGuestVehicles(): ConfirmLandingState right after generation - every merged copy leaves its craft and
 * is deleted (the host's world never keeps the partner's tank); a copy a mission's starting condition banned has the
 * generator's store credit taken back.
 */
int coopMergeGuestVehicles(Game* game, Craft* craft);
void coopTagGuestVehicleUnit(const Vehicle* v, BattleUnit* unit);
void coopDropMergedGuestVehicles(Game* game);

/**
 * DebriefingState's tank credit, on the HOST of a co-op session - true for a SEPARATE
 * partner's tank (BattleUnit::getCoopGuestTank() not empty) that vanilla is about to recover: it is marked survived for
 * the debrief payload's guestTanks rows and the caller skips vanilla's store credit (the tank and its ammo), because
 * the tank goes home to the partner's world. False for every other unit (vanilla credits it). Body in connectionTCP.cpp.
 */
bool coopGuestTankRecovered(BattleUnit* unit);

/**
 * The test-server
 * probes of the SEPARATE co-op client's own-craft battle refusal (TestServer
 * event_state `coopClientBattleRefused` / `coopClientBattleRefusedLast`).
 * Process-lifetime, never reset; written only on a SEPARATE co-op client by
 * the landing and Cydonia refusals (CoopState.cpp); never read by game logic.
 * coopClientBattleRefused() counts the refusals; coopClientBattleRefusedLast()
 * is "landing:<craftId>" or "cydonia:<craftId>" of the most recent one, ""
 * before any. Bodies live in CoopState.cpp, beside their statics.
 */
int coopClientBattleRefused();
std::string coopClientBattleRefusedLast();

/**
 * on a SEPARATE co-op campaign's CLIENT
 * only (connected, not the server owner, gamemode 0/1), refuses an own-craft
 * landing: the craft returns to base (vanilla "No"), @a gs->popup() shows a
 * CraftErrorState with the host-craft-only text (CoopState.cpp), and the function
 * returns true so GeoscapeState never pushes ConfirmLandingState. False with
 * no effect anywhere else (host, SHARED, single player, PvP, PvE2).
 */
bool coopRefuseSeparateClientLanding(Game* game, GeoscapeState* gs, Craft* craft);

/**
 * the same refusal for Cydonia. Called
 * first in ConfirmCydoniaState::btnYesClick; when it returns true it has popped
 * ConfirmCydoniaState and pushed the CraftErrorState, and the craft is
 * untouched. False with no effect outside a SEPARATE co-op client.
 */
bool coopRefuseSeparateClientCydonia(Game* game, Craft* craft);

} // namespace OpenXcom
