#pragma once
/*
 * Copyright 2010-2016 OpenXcom Developers.
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
 * along with OpenXcom.  If not, see <http:///www.gnu.org/licenses/>.
 */
#include "Position.h"
#include "../Mod/RuleItem.h"
#include "../Engine/HelperMeta.h"
#include <string>
#include <list>
#include <vector>

namespace OpenXcom
{

class BattleUnit;
class SavedBattleGame;
class BattleItem;
class BattleState;
class BattlescapeState;
class Map;
class TileEngine;
class Pathfinding;
class Mod;
class InfoboxOKState;
class SoldierDiary;
class RuleSkill;
class connectionTCP; 

enum BattleActionMove : char { BAM_NORMAL = 0, BAM_RUN = 1, BAM_STRAFE = 2, BAM_SNEAK = 3, BAM_MISSILE = 4 };

struct BattleActionCost : RuleItemUseCost
{
	BattleActionType type;
	BattleUnit *actor = nullptr;
	BattleItem *weapon = nullptr;
	const RuleSkill* skillRules = nullptr; // if defined, this is a skill action

	/// Default constructor.
	BattleActionCost() : type(BA_NONE) { }

	/// Constructor from unit.
	BattleActionCost(BattleUnit *unit) : type(BA_NONE), actor(unit) { }

	/// Constructor with update.
	BattleActionCost(BattleActionType action, BattleUnit *unit, BattleItem *item) : type(action), actor(unit), weapon(item) { updateTU(); }

	/// Update value of TU based of actor, weapon and type.
	void updateTU();
	/// Set TU to zero.
	void clearTU();
	/// Test if actor have enough TU to perform weapon action.
	bool haveTU(std::string *message = 0);
	/// Spend TU when actor have enough TU.
	bool spendTU(std::string *message = 0);
};

struct BattleAction : BattleActionCost
{
	Position target;
	std::list<Position> waypoints;
	bool targeting;
	int value;
	std::string result;
	bool strafe = false;
	bool run = false;
	bool sneak = false;
	bool ignoreSpottedEnemies = false;
	bool kneel = false;
	int diff;
	int autoShotCounter;
	Position cameraPosition;
	bool desperate; // ignoring newly-spotted units
	int finalFacing;
	bool finalAction;
	int number; // first action of turn, second, etc.?
	bool sprayTargeting; // Used to separate waypoint checks between confirm firing mode and the "spray" autoshot
	BattleActionOrigin relativeOrigin = BattleActionOrigin::CENTRE; // preferred origin voxel (centre, left or right)
	int terrainMeleeTilePart = 0; // terrain melee
	// coop (PRD-P5): true only on the stack-local action a REPLAYED (peer- or
	// AI-originated) chain runs on - see BattlescapeGame::makeReplayAction. The
	// BStates copy the action they are given, so this rides the whole chain and
	// lets display-only code tell "the local player did this" from "I am watching
	// my teammate". Used to stop a peer action yanking the local camera.
	bool coopReplay = false;
	// coop (PRD-P6): the medikit operands an `action_intent` carries that have no
	// home in BattleAction's normal fields, so ONE executeAction() can dispatch
	// every kind. -1 = "this is not a medikit action".
	int coopTargetUnit = -1;
	int coopMedikitMode = -1;   // BattleMediKitAction
	int coopBodyPart = 0;       // UnitBodyPart

	/// Default constructor
	BattleAction() : target(-1, -1, -1), targeting(false), value(0), diff(0), autoShotCounter(0), cameraPosition(0, 0, -1), desperate(false), finalFacing(-1), finalAction(false), number(0), sprayTargeting(false) { }

	/// Get move type
	BattleActionMove getMoveType() const
	{
		return strafe ? BAM_STRAFE : run ? BAM_RUN : sneak ? BAM_SNEAK : BAM_NORMAL;
	}
};


/**
 * Count of different state of units to determine who wins
 */
struct BattlescapeTally
{
	/// number of live enemies (aliens and MC'ed soldiers)
	int liveAliens = 0;
	/// number of live soldiers (only ones that are not MC'ed, including tanks, but not summoned units)
	int liveSoldiers = 0;

	/// number of live soldiers on entrance tiles
	int inEntrance = 0;
	/// number of live soldiers on exit tiles.
	int inExit = 0;
	/// number of live soldiers in the middle of the battlefield.
	int inField = 0;

	/// number of live VIPs on entrance tiles
	int vipInEntrance = 0;
	/// number of live VIPs on exit tiles.
	int vipInExit = 0;
	/// number of live VIPs in the middle of the battlefield.
	int vipInField = 0;
};

/**
 * Battlescape game - the core game engine of the battlescape game.
 */
class BattlescapeGame
{
private:
	SavedBattleGame *_save;
	BattlescapeState *_parentState;
	std::list<BattleState*> _states, _deleted;
	bool _playerPanicHandled;
	int _AIActionCounter;
	BattleAction _currentAction;
	// coop (PRD-P1): turnPlayerTarget's "the unit already faces there, so this is
	// a door-open" test used to compare against _currentAction.target, which only
	// worked because the replay wrote the singleton action. The replay now builds
	// a stack-local action, so it keeps its own last-target here instead of
	// reading (and clobbering) the local player's action.
	Position _replayTurnTarget = Position(-1, -1, -1);
	bool _endTurnRequested;
	bool _endConfirmationHandled;
	bool _allEnemiesNeutralized;

	helper::SingleRun _endTurnProcessed;
	helper::SingleRun _triggerProcessed;
	/// Ends the turn.
	void endTurn();
	/// Picks the first soldier that is panicking.
	bool handlePanickingPlayer();
	/// Common function for handling panicking units.
	bool handlePanickingUnit(BattleUnit *unit);
	/// Determines whether there are any actions pending for the given unit.
	bool noActionsPending(BattleUnit *bu);
	std::vector<InfoboxOKState*> _infoboxQueue;
	/// Shows the infoboxes in the queue (if any).
	void showInfoBoxQueue();
	// coop (PRD-P3 GAP-1): set only while spawn_units() replays a host manifest.
	// While it is false a co-op peer refuses to spawn anything at all - the spawn
	// chance, the spawn direction, the built-in-weapon item level and every id the
	// spawn mints come from the host, never from this machine's RNG stream.
	struct CoopSpawnReplay
	{
		bool active = false;
		const RuleItem* carrierRule = nullptr;
		int faction = -1;
		int ownerId = -1;
		int direction = -1;
		int itemLevel = -1;
		int unitId = -1;
		int firstItemId = -1;
		Position finalPos = Position(-1, -1, -1);
	};
	CoopSpawnReplay _coopSpawnReplay;
	// coop (PRD-P7): "do not wait for this walk". Set by the arbiter when an input
	// arrives while a SKIPPABLE chain is running (host) or while an action packet
	// sits deferred behind the receive gate (client); cleared the moment _states
	// drains or the chain stops being skippable. Only the walk/turn/fall think
	// intervals read it - never a projectile, explosion, death or melee state.
	bool _coopFastForward = false;
	/// coop: id -> live BattleUnit (null when absent). Never fabricates.
	BattleUnit* coopFindUnit(int unitId) const;
	/// coop: ships one spawn manifest entry to the peer (host only).
	void sendCoopSpawnManifest(const char* kind, const RuleItem* carrierRule, const std::string& rule, uint64_t seed, Position position, Position finalPos, const BattleUnit* attacker, const BattleUnit* owner, int faction, int direction, int itemLevel, int unitId, int firstItemId, int lastItemId);
public:
	bool _AISecondMove, _playedAggroSound;
	/// is debug mode enabled in the battlescape?
	static bool _debugPlay;
	static int isYourTurn;
	// coop
	connectionTCP* getCoopMod();
	void handlePanickUnitCoop(BattleUnit* unit);
	void infoboxCoop(std::string msg);
	void infoboxOkCoop(std::string msg);
	void setCoopTaskCompleted(bool task);
	int getCoopActorID();
	int getCoopGamemode();
	std::string getCoopWeaponHand();
	/// Builds the stack-local BattleAction a replayed peer/AI action runs on, so
	/// replaying never writes the singleton _currentAction (which belongs to the
	/// LOCAL player's UI) - PRD-P1.
	static BattleAction makeReplayAction(BattleUnit* actor);
	void movePlayerTarget(std::string obj);
	void turnPlayerTarget(std::string str_obj);
	void turnPlayerTargetAfter(std::string str_obj);
	void psi_attack(std::string str_obj);
	void melee_attack(std::string str_obj);
	/// coop (PRD-P3 GAP-1): applies a host "spawn_units" manifest - re-runs the very
	/// same spawn code from the host's RNG seed, with the host's direction/itemLevel,
	/// so the peer mints identical unit and item ids instead of rolling its own.
	void spawn_units(std::string str_obj);
	bool getHost();
	bool isCoop();
	void abortCoopPath(int x, int y, int z, int unit_id, int setDirection, int setFaceDirection);
	void abortCoopPath2();
	void sendPacketData(std::string data);
	void coopDeath(BattleUnit *unit, const RuleDamageType *damageType, bool noSound);
	// coop
	void teleport(int x, int y, int z, BattleUnit* unit);
	void setTileCoop(Position pos, BattleUnit &unit);
	/// Creates the BattlescapeGame state.
	BattlescapeGame(SavedBattleGame *save, BattlescapeState *parentState);
	/// Cleans up the BattlescapeGame state.
	~BattlescapeGame();
	/// Checks for units panicking or falling and so on.
	int think();
	/// Initializes the Battlescape game.
	void init();
	/// Determines whether a playable unit is selected.
	bool playableUnitSelected() const;
	/// Handles states timer.
	void handleState();
	// coop
	void handleStateCoop();
	/// Pushes a state to the front of the list.
	void statePushFront(BattleState *bs);
	/// Pushes a state to second on the list.
	void statePushNext(BattleState *bs);
	/// Pushes a state to the back of the list.
	void statePushBack(BattleState *bs);
	// ---- coop (PRD-P6): action intents ------------------------------------
	/// THE executor's single entry point for a player-initiated action. Factored
	/// out of the local-input tails so the host's own clicks and a client's
	/// `action_intent` run exactly the same code. `calculatePath` is false when
	/// the caller has already run Pathfinding::calculate for this move (the
	/// mapClick tail has, an intent has not).
	void executeAction(BattleAction& action, bool calculatePath = true);
	/// The door every player-initiated action passes through. Returns TRUE when
	/// the caller must NOT execute anything locally:
	///  - parallel CLIENT: the action was shipped as an `action_intent`;
	///  - parallel HOST: admission was refused, and the busy flash is up.
	/// Classic co-op and single player always return false - untouched.
	bool coopRouteAction(BattleAction& action, const std::string& kind);
	/// Same door for a medikit press (the operands do not fit a BattleAction).
	bool coopRouteMedikit(BattleAction* action, BattleUnit* target, int medikitMode, int bodyPart);
	/// Host: "" when the intent may run, otherwise a short cause; `warning` gets
	/// the translatable key the client is told to flash. Takes the serialized
	/// packet (like every sibling replay handler) so jsoncpp stays out of the
	/// battlescape headers.
	std::string coopValidateIntent(const std::string& intentJson, int seat, std::string& warning);
	/// Host: rebuild the intent as a BattleAction and run it through executeAction.
	/// `localOrigin` = this machine's own deferred click (PRD-P7 pending-admit), so
	/// the action is NOT flagged coopReplay and the camera still follows it.
	void coopExecuteIntent(const std::string& intentJson, bool localOrigin = false);
	// ---- coop (PRD-P7): walk fast-forward ---------------------------------
	/// True iff EVERY queued state is a walk / turn / fall of a FACTION_PLAYER
	/// unit - i.e. the whole chain is animation nobody has to watch. A shot, an
	/// explosion, a death, a melee or psi state, the end-turn sentinel, or a
	/// non-player actor all make it false. Empty queue = false (nothing to skip).
	bool chainIsSkippable() const;
	/// Is the current chain being fast-forwarded (walk/turn/fall interval 0)?
	bool getCoopFastForward() const { return _coopFastForward; }
	/// Arms/disarms the fast-forward. Arming is refused outside parallel mode, so
	/// classic co-op and single player can never take the interval-0 branch.
	void setCoopFastForward(bool on);
	/// Re-evaluates the fast-forward after the state queue changed (a push, a pop).
	/// On a drain it also closes the host's action chain (PROTOCOL.md `action_end`).
	void coopChainChanged();
	/// Ships the classic replay packet for a mutation that has no BattleState of
	/// its own, so the peer still sees it. (BState-driven kinds broadcast through
	/// their own send sites.)
	void coopSendKneelPacket(BattleUnit* bu);
	void coopSendPrimePacket(const BattleAction& action, BattleActionType primeType);
	void coopSendMedikitPacket(const BattleAction& action, BattleUnit* target, int medikitMode, int bodyPart, const std::string& medkitState);

	/// Handles the result of non target actions, like priming a grenade.
	void handleNonTargetAction();
	/// Same, on an explicit action - lets a replayed peer action (coopActionClick)
	/// run without writing the local player's _currentAction (PRD-P1).
	void handleNonTargetAction(BattleAction& action);
	// coop
	void endTurnCoop();
	void endBattleTurnCoop();
	/// Removes current state.
	void popState();
	/// Sets state think interval.
	void setStateInterval(Uint32 interval);
	/// Checks for casualties in battle.
	void checkForCasualties(const RuleDamageType *damageType, BattleActionAttack attack, bool hiddenExplosion = false, bool terrainExplosion = false);
	/// Checks reserved tu and energy.
	bool checkReservedTU(BattleUnit *bu, int tu, int energy, bool justChecking = false);
	/// Handles unit AI.
	void handleAI(BattleUnit *unit);
	/// Drops an item and affects it with gravity.
	void dropItem(Position position, BattleItem *item, bool removeItem = false, bool updateLight = true);
	/// Converts a unit into a unit of another type.
	BattleUnit *convertUnit(BattleUnit *unit);
	/// Spawns a new unit in the middle of battle.
	void spawnNewUnit(BattleItem *item);
	void spawnNewUnit(BattleActionAttack attack, Position position);
	/// Spawns a new item in the middle of battle.
	void spawnNewItem(BattleItem *item);
	void spawnNewItem(BattleActionAttack attack, Position position);
	/// Spawns units from items that explode before battle
	void spawnFromPrimedItems();
	/// Removes spawned units that belong to the player to avoid dealing with recovery
	void removeSummonedPlayerUnits();
	/// Tally summoned player-controlled VIPs. We may still need to correct this in the Debriefing.
	void tallySummonedVIPs();
	/// Handles kneeling action.
	bool kneel(BattleUnit *bu);
	/// Cancels the current action.
	bool cancelCurrentAction(bool bForce = false);
	bool cancelCurrentActionCoop(bool bForce = false);
	/// Cancels all actions.
	void cancelAllActions();
	/// Gets a pointer to access action members directly.
	BattleAction *getCurrentAction();
	/// Determines whether there is an action currently going on.
	bool isBusy() const;
	/// Activates primary action (left click).
	void primaryAction(Position pos);
	/// Activates secondary action (right click).
	void secondaryAction(Position pos);
	/// Handler for the blaster launcher button.
	void launchAction();
	/// Handler for the psi button.
	void psiButtonAction();
	/// Handle psi attack result message.
	void psiAttackMessage(BattleActionAttack attack, BattleUnit *victim);
	/// Moves a unit up or down.
	void moveUpDown(BattleUnit *unit, int dir);
	/// Requests the end of the turn (wait for explosions etc to really end the turn).
	void requestEndTurn(bool askForConfirmation);
	/// Sets the TU reserved type.
	void setTUReserved(BattleActionType tur);
	/// Sets up the cursor taking into account the action.
	void setupCursor();
	/// Gets the map.
	Map *getMap();
	/// Gets the save.
	SavedBattleGame *getSave();
	/// Gets the tile engine.
	TileEngine *getTileEngine();
	/// Gets the pathfinding.
	Pathfinding *getPathfinding();
	/// Gets the mod.
	Mod *getMod();
	/// Returns whether panic has been handled.
	bool getPanicHandled() const { return _playerPanicHandled; }
	/// Tries to find an item and pick it up if possible.
	bool findItem(BattleAction *action, bool pickUpWeaponsMoreActively, bool& walkToItem);
	/// Checks through all the items on the ground and picks one.
	BattleItem *surveyItems(BattleAction *action, bool pickUpWeaponsMoreActively);
	/// Evaluates if it's worthwhile to take this item.
	bool worthTaking(BattleItem* item, BattleAction *action, bool pickUpWeaponsMoreActively);
	/// Picks the item up from the ground.
	int takeItemFromGround(BattleItem* item, BattleAction *action);
	/// Assigns the item to a slot (stolen from battlescapeGenerator::addItem()).
	bool takeItem(BattleItem* item, BattleAction *action);
	/// Returns the type of action that is reserved.
	BattleActionType getReservedAction();
	/// Tallies the living units, converting them if necessary.
	bool isSurrendering(BattleUnit* bu);
	/// Check count of units in different state
	BattlescapeTally tallyUnits();
	bool convertInfected();
	/// Sets the kneel reservation setting.
	void setKneelReserved(bool reserved);
	/// Checks the kneel reservation setting.
	bool getKneelReserved() const;
	/// Names the hand a weapon is actually held in ("right"/"left"), falling back
	/// to @a uiHand. The co-op packets used to report BattlescapeGame::
	/// getCoopWeaponHand() alone, which is only ever written when the LOCAL player
	/// clicks a hand button - so an AI actor's shot carried somebody else's stale
	/// hand. (coop, issue #74)
	static std::string coopHandOf(BattleUnit* actor, const BattleItem* weapon, const std::string& uiHand);
	/// Resolves the weapon a replayed co-op action was fired with, WITHOUT ever
	/// fabricating a BattleItem: exact (id,type) on the actor, then the named
	/// hand, then the actor's own inventory by type, then the identified instance
	/// anywhere. Returns nullptr when the peer genuinely does not have it - the
	/// caller must then skip the action rather than invent an item, because every
	/// `new BattleItem` on a receiver silently advances that machine's item-id
	/// counter and permanently desynchronises the two id spaces. (coop, issue #74)
	static BattleItem* coopResolveWeapon(SavedBattleGame* save, BattleUnit* actor, int weaponId, const std::string& weaponType, const std::string& hand);
	/// Checks for and triggers proximity grenades. (coop)
	void checkForProximityCoop(BattleUnit* unit);
	int checkForProximityGrenadesCoop(BattleUnit* unit);
	/// Checks for and triggers proximity grenades.
	int checkForProximityGrenades(BattleUnit *unit);
	/// Cleans up all the deleted states.
	void cleanupDeleted();
	/// Get the depth of the saved game.
	int getDepth() const;
	/// Play sound on battlefield (with direction).
	void playSound(int sound, const Position &pos);
	/// Play sound on battlefield.
	void playSound(int sound);
	/// Play unit response sound on battlefield.
	void playUnitResponseSound(BattleUnit *unit, int type);
	/// Sets up a mission complete notification.
	void missionComplete();
	std::list<BattleState*> getStates();
	/// Auto-end the battle if conditions are met.
	void autoEndBattle();
	/// Were all enemies neutralized?
	bool areAllEnemiesNeutralized() const { return _allEnemiesNeutralized; }
	/// Resets the flag.
	void resetAllEnemiesNeutralized() { _allEnemiesNeutralized = false; }

	// coop
	void setWaypointCoop(int x, int y, int z);
	void clearWaypointsCoop();
	void CoopShoot(const BattleAction& action);
	void hitCoop(BattleActionAttack attack, Position center, int power, const RuleDamageType* type, bool rangeAtack = true, int terrainMeleeTilePart = 0, uint64_t seed = 0);
	void centerOnPositionCoop(Position pos);
};

}
