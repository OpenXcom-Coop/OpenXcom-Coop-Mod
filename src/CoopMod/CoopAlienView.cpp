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
#include "../Engine/Language.h"
#include "../Engine/Unicode.h"

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

namespace
{
// The marker a UFO has once seen: Ufo::getMarker() without its detection test.
int ufoMarker(const Ufo* ufo)
{
	const RuleUfo* rules = ufo->getRules();
	switch (ufo->getStatus())
	{
	case Ufo::LANDED:
		return rules->getLandMarker() == -1 ? 3 : rules->getLandMarker();
	case Ufo::CRASHED:
		return rules->getCrashMarker() == -1 ? 4 : rules->getCrashMarker();
	default:
		return rules->getMarker() == -1 ? 2 : rules->getMarker();
	}
}

// Whether the UFO has the number its name shows (Ufo::getDefaultName): X-COM gives it on detection.
bool ufoNumbered(const Ufo* ufo)
{
	switch (ufo->getStatus())
	{
	case Ufo::LANDED:
		return ufo->getLandId() != 0;
	case Ufo::CRASHED:
		return ufo->getCrashId() != 0;
	default:
		return ufo->getId() != 0;
	}
}
}

bool showsUfo(const SavedGame* save, const Ufo* ufo)
{
	return (active(save) && rule(ALIEN_ACTIVITY)) || ufo->getDetected();
}

bool showsUfoDetails(const SavedGame* save, const Ufo* ufo)
{
	return (active(save) && rule(ALIEN_ACTIVITY)) || ufo->getHyperDetected();
}

bool showsSite(const SavedGame* save, const MissionSite* site)
{
	return (active(save) && rule(ALIEN_ACTIVITY)) || site->getDetected();
}

bool showsAlienBase(const SavedGame* save, const AlienBase* base)
{
	return (active(save) && rule(ALIEN_BASES)) || base->isDiscovered();
}

bool showsXcomBase(const SavedGame* save, const Base* base)
{
	return !active(save) || !rule(XCOM_SIGHTINGS) || base->getRetaliationTarget();
}

bool showsXcomCraft(SavedGame* save, Craft* craft)
{
	return !active(save) || !rule(XCOM_SIGHTINGS) || craftSighting(save, craft) != 0;
}

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

int marker(SavedGame* save, Target* target)
{
	if (Ufo* ufo = dynamic_cast<Ufo*>(target))
		return showsUfo(save, ufo) ? ufoMarker(ufo) : -1;
	if (MissionSite* site = dynamic_cast<MissionSite*>(target))
	{
		if (!showsSite(save, site))
			return -1;
		const int icon = site->getDeployment()->getMarkerIcon();
		return icon == -1 ? 5 : icon;
	}
	if (AlienBase* base = dynamic_cast<AlienBase*>(target))
		return showsAlienBase(save, base) ? base->getDeployment()->getMarkerIcon() : -1;
	if (Base* base = dynamic_cast<Base*>(target))
		return showsXcomBase(save, base) ? base->getMarker() : -1;
	if (Craft* craft = dynamic_cast<Craft*>(target))
		return showsXcomCraft(save, craft) ? craft->getMarker() : -1;
	return target->getMarker();
}

std::string targetName(const SavedGame* save, Target* target, Language* lang)
{
	Ufo* ufo = dynamic_cast<Ufo*>(target);
	if (ufo && active(save) && !ufoNumbered(ufo))
	{
		std::string type = lang->getString(ufo->getRules()->getType());
		Unicode::upperCase(type);
		return type;
	}
	return target->getName(lang);
}

}

}
