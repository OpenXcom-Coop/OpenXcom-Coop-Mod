#include "CoopAlienView.h"
#include "CoopSide.h"
#include "../fmath.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Target.h"
#include "../Savegame/Ufo.h"
#include "../Savegame/Base.h"
#include "../Savegame/Craft.h"
#include "../Savegame/AlienBase.h"
#include "../Savegame/MissionSite.h"
#include "../Mod/RuleUfo.h"
#include "../Mod/RuleCraft.h"
#include "../Mod/AlienDeployment.h"

namespace OpenXcom
{

namespace CoopAlienView
{

namespace
{
bool g_forced = false;
bool g_rules[RULE_COUNT] = { true, true, true };
}

bool active(const SavedGame* save)
{
	if (g_forced)
		return true;
	return save != nullptr && CoopSide::pvpOneWorld(save) && CoopSide::thisMachinePlaysAliens(save);
}

void setForced(bool forced) { g_forced = forced; }
bool forced() { return g_forced; }
bool rule(Rule r) { return r >= 0 && r < RULE_COUNT && g_rules[r]; }
void setRule(Rule r, bool on) { if (r >= 0 && r < RULE_COUNT) g_rules[r] = on; }

bool showsUfo(const SavedGame*, const Ufo* ufo) { return ufo->getDetected(); }
bool showsUfoDetails(const SavedGame*, const Ufo* ufo) { return ufo->getHyperDetected(); }
bool showsSite(const SavedGame*, const MissionSite* site) { return site->getDetected(); }
bool showsAlienBase(const SavedGame*, const AlienBase* base) { return base->isDiscovered(); }
bool showsXcomBase(const SavedGame*, const Base*) { return true; }
bool showsXcomCraft(SavedGame*, Craft*) { return true; }

int craftSighting(SavedGame* save, Craft* craft)
{
	if (!save || !craft || craft->getStatus() != "STR_OUT" || craft->getRules()->isUndetectable())
		return 0;
	for (const Ufo* ufo : *save->getUfos())
	{
		// as when a UFO looks for a base: a crashed or ignored UFO sees nothing
		if (ufo->getStatus() == Ufo::IGNORE_ME || ufo->isCrashed())
			continue;
		if (ufo->insideRadarRange(craft))
			return 1;
	}
	for (const AlienBase* base : *save->getAlienBases())
	{
		const double range = base->getDeployment()->getBaseDetectionRange();
		if (range > 0 && craft->getDistance(base) < Nautical(range))
			return 2;
	}
	return 0;
}

int marker(SavedGame*, Target* target)
{
	return target->getMarker();
}

}

}
