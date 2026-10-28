#pragma once
/*
 * coop: routes battle mod scripts' isResearched to a unit owner's seat research.
 * Declarations only; the definitions live in connectionTCP.cpp (the per-seat research store's file).
 * Not registered in the project files (CoopGhost.h / CoopSyncedOptions.h precedent: headers need no entry).
 */

namespace OpenXcom
{

class BattleUnit;
class SavedGame;
class RuleResearch;
class Game;

/// While alive, a battle mod script's isResearched on the live world of a co-op battle in research-separate
/// mode answers from @a owner's seat research (its seat tag; null, seat-less and seat 0 = the live world).
/// Nests (restores the previous owner). Wraps each battle hook a unit owns: armor -> the wearer,
/// weapon / ammo -> the attacker, skill -> the actor, item -> its holder.
class CoopScriptOwner
{
	int _prev;
public:
	explicit CoopScriptOwner(const BattleUnit* owner);
	~CoopScriptOwner();
	CoopScriptOwner(const CoopScriptOwner&) = delete;
	CoopScriptOwner& operator=(const CoopScriptOwner&) = delete;
};

/// coop: wraps the HOST's call of BattleUnit::postMissionProcedures
/// in its battle-end debriefing (DebriefingState::prepareDebriefing), whose returnFromMissionUnit armor script
/// runs after the battle screen is gone (battle phase Ended). While alive, that script's isResearched on
/// @a game's live world answers from @a owner's seat research in research-separate mode (the store lives until
/// the debriefing's OK). Nests (restores the previous owner and game); a null game or owner is not routed.
class CoopScriptDebriefOwner
{
	int _prevSeat;
	Game* _prevGame;
public:
	CoopScriptDebriefOwner(Game* game, const BattleUnit* owner);
	~CoopScriptDebriefOwner();
	CoopScriptDebriefOwner(const CoopScriptDebriefOwner&) = delete;
	CoopScriptDebriefOwner& operator=(const CoopScriptDebriefOwner&) = delete;
};

/// isResearchedScript()'s routed answer: -1 = not routed (vanilla reads @a sg), else 0 or 1.
int coopScriptIsResearched(const SavedGame* sg, const RuleResearch* rule);

}
