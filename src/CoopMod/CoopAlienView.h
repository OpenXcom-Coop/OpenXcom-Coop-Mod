#pragma once

#include <string>

namespace OpenXcom
{

class Language;
class SavedGame;
class Target;
class Ufo;
class Base;
class Craft;
class AlienBase;
class MissionSite;

/**
 * What the alien player's Geoscape shows in a PvP campaign played on the host's one world.
 *
 * On the alien player's machine the globe, its click targets and the target windows decide what to show
 * through these rules instead of X-COM's detection flags. They only read: nothing here changes the world.
 * Each rule has its own switch, all on:
 *   ALIEN_ACTIVITY  every UFO, with the details a hyper-wave decoder gives, and every mission site;
 *   XCOM_SIGHTINGS  an X-COM base once a UFO has found it (its retaliation-target flag), and an X-COM craft
 *                   in flight while it is inside a UFO's radar range or an alien base's detection range;
 *   ALIEN_BASES     every alien base, whether X-COM has found it or not.
 * With a switch off, that kind of object shows as X-COM's flags say (ALIEN_ACTIVITY, ALIEN_BASES) or always
 * (XCOM_SIGHTINGS). Away from the alien player's view every helper returns what the world's flags say.
 */
namespace CoopAlienView
{

enum Rule { ALIEN_ACTIVITY = 0, XCOM_SIGHTINGS = 1, ALIEN_BASES = 2, RULE_COUNT = 3 };

/// True when this machine shows @a save as the alien player sees it.
bool active(const SavedGame* save);
/// Test commands only: show this machine's Geoscape as the alien player sees it, in any campaign.
void setForced(bool forced);
bool forced();
/// A rule's switch. setRule is for test commands only.
bool rule(Rule r);
void setRule(Rule r, bool on);

bool showsUfo(const SavedGame* save, const Ufo* ufo);
bool showsUfoDetails(const SavedGame* save, const Ufo* ufo);
bool showsSite(const SavedGame* save, const MissionSite* site);
bool showsAlienBase(const SavedGame* save, const AlienBase* base);
bool showsXcomBase(const SavedGame* save, const Base* base);
bool showsXcomCraft(SavedGame* save, Craft* craft);
/// Why an X-COM craft in flight is seen: 1 inside a UFO's radar range, 2 inside an alien base's
/// detection range, 0 neither.
int craftSighting(SavedGame* save, Craft* craft);
/// The globe marker of @a target as these rules show it (-1 = not shown).
int marker(SavedGame* save, Target* target);
/// The name a window or list shows for @a target. In the alien player's view a UFO that X-COM has not numbered
/// shows its craft type ("SMALL SCOUT"): a UFO gets its number only when X-COM detects it.
std::string targetName(const SavedGame* save, Target* target, Language* lang);

}

}
