#pragma once
/*
 * coop OF2 (owner D258 (b); spec rewrite/prompts/of2_mod_script_player_reads.md, QOF2-1 (a), D149, D146).
 * Declarations only; the definitions live in connectionTCP.cpp (the per-seat research store's file).
 * Not registered in the project files (CoopGhost.h / CoopSyncedOptions.h precedent: headers need no entry).
 */

namespace OpenXcom
{

class BattleUnit;
class SavedGame;
class RuleResearch;

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

/// isResearchedScript()'s routed answer: -1 = not routed (vanilla reads @a sg), else 0 or 1.
int coopScriptIsResearched(const SavedGame* sg, const RuleResearch* rule);

}
