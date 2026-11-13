/*
 * Schema 3 -> 4: a PvP campaign kept as one world per player becomes one
 * world, the X-COM player's.  Every base carries that player's name in
 * ownerplayername and the alien player's world is dropped.  When the host plays
 * X-COM its world already is the file's body; when the host plays the aliens the
 * X-COM player's world, embedded in the host's file, becomes the body.
 */
#include "SaveUpgradeTypes.h"

#include <algorithm>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace OpenXcom
{
namespace SaveUpgrade
{
namespace
{

using yamlutil::getBool;
using yamlutil::getInt;
using yamlutil::getStr;
using yamlutil::hasKey;
using yamlutil::removeKey;
using yamlutil::setInt;

int gamemodeOf(const SaveSet& set)
{
	return static_cast<int>(getInt(set.host.body(), "coop_gamemode", set.gamemode));
}

std::vector<std::string> rosterOf(const SaveSet& set)
{
	if (!set.roster.empty())
		return set.roster;
	std::vector<std::string> names;
	ryml::ConstNodeRef roster = set.host.header().find_child("coopPlayers");
	if (!roster.invalid() && roster.is_seq())
		for (ryml::ConstNodeRef p : roster.children())
			names.push_back(p.has_val() ? std::string(p.val().str, p.val().len) : std::string());
	return names;
}

int countBases(ryml::ConstNodeRef body)
{
	ryml::ConstNodeRef bases = body.find_child("bases");
	return (!bases.invalid() && bases.is_seq()) ? static_cast<int>(bases.num_children()) : 0;
}

/// Every soldier of a list with no peer link (coop 0) belongs to the X-COM seat.
void ownSoldiers(ryml::NodeRef soldiers, int seat)
{
	if (soldiers.invalid() || !soldiers.is_seq())
		return;
	for (ryml::NodeRef soldier : soldiers.children())
		if (getInt(soldier, "coop", 0) == 0)
			setInt(soldier, "ownerplayerid", seat);
}

/// Tree::duplicate from another tree leaves every key and value pointing into
/// the source tree's arena. The source world is dropped before the save is
/// written, so the copied strings move into the destination tree's own arena.
void internalizeStrings(ryml::NodeRef node)
{
	ryml::Tree* tree = node.tree();
	if (node.has_key() && !tree->in_arena(node.key()))
	{
		const std::string key(node.key().str, node.key().len);
		node.set_key(tree->to_arena(ryml::to_csubstr(key)));
	}
	if (node.has_val() && !tree->in_arena(node.val()))
	{
		const std::string val(node.val().str, node.val().len);
		node.set_val(tree->to_arena(ryml::to_csubstr(val)));
	}
	for (ryml::NodeRef child : node.children())
		internalizeStrings(child);
}

/// Appends a copy of @a source, a node of another world, to the list @a key of @a body.
ryml::NodeRef appendCopy(ryml::NodeRef body, ryml::csubstr key, ryml::NodeRef source)
{
	ryml::NodeRef list = yamlutil::mapChild(body, key);
	list |= ryml::SEQ;
	const size_t after = list.num_children() ? list.last_child().id() : ryml::NONE;
	const size_t id = list.tree()->duplicate(source.tree(), source.id(), list.id(), after);
	ryml::NodeRef copy = list.tree()->ref(id);
	internalizeStrings(copy);
	return copy;
}

/// Puts a copy of @a source, a keyed node of another world, into @a map in place of the map's own child of that key.
void replaceChild(ryml::NodeRef map, ryml::NodeRef source)
{
	removeKey(map, source.key());
	const size_t after = map.num_children() ? map.last_child().id() : ryml::NONE;
	ryml::Tree* tree = map.tree();
	internalizeStrings(tree->ref(tree->duplicate(source.tree(), source.id(), map.id(), after)));
}

/// Raises the id counter @a key of @a body so the next id the game hands out of that kind is at least @a next.
void raiseIdCounter(ryml::NodeRef body, const std::string& key, long long next)
{
	ryml::NodeRef ids = yamlutil::mapChild(body, "ids");
	const ryml::csubstr name = ryml::to_csubstr(key);
	if (getInt(ids, name, 0) < next)
		setInt(ids, name, next);
}

/// The lists of the alien activity of a world, with the words a report names them by.
struct AlienList
{
	const char* key;
	const char* words;
};
const AlienList ALIEN_LISTS[] = {
	{ "alienMissions", "alien missions" },
	{ "ufos", "UFOs" },
	{ "missionSites", "mission sites" },
	{ "alienBases", "alien bases" },
};

int countList(ryml::ConstNodeRef body, const char* key)
{
	ryml::ConstNodeRef list = body.find_child(ryml::to_csubstr(key));
	return (!list.invalid() && list.is_seq()) ? static_cast<int>(list.num_children()) : 0;
}

/// The X-COM player's craft a battle was fought from, named by the battle record's craft type and id.
ryml::NodeRef battleCraft(ryml::NodeRef body, ryml::ConstNodeRef record)
{
	const std::string type = getStr(record, "craftType", std::string());
	const long long id = getInt(record, "craftId", -1);
	ryml::NodeRef bases = body.find_child("bases");
	if (bases.invalid() || !bases.is_seq())
		return ryml::NodeRef();
	for (ryml::NodeRef base : bases.children())
	{
		ryml::NodeRef crafts = base.find_child("crafts");
		if (crafts.invalid() || !crafts.is_seq())
			continue;
		for (ryml::NodeRef craft : crafts.children())
			if (getStr(craft, "type", std::string()) == type && getInt(craft, "id", -1) == id)
				return craft;
	}
	return ryml::NodeRef();
}

/// The alien mission of a UFO copied from the alien player's world. It moves
/// with the UFO to the X-COM world's next mission id, with that one live UFO
/// (its other UFOs stay behind) and no link to an alien base it does not hold.
void copyUfoMission(ryml::NodeRef alienBody, ryml::NodeRef xcomBody, ryml::NodeRef ufo)
{
	ryml::NodeRef missions = alienBody.find_child("alienMissions");
	if (missions.invalid() || !missions.is_seq())
		return;
	for (ryml::NodeRef mission : missions.children())
	{
		if (getInt(mission, "uniqueID", 0) != getInt(ufo, "mission", 0))
			continue;
		ryml::NodeRef copy = appendCopy(xcomBody, "alienMissions", mission);
		const long long id = getInt(yamlutil::mapChild(xcomBody, "ids"), "ALIEN_MISSIONS", 1);
		setInt(copy, "uniqueID", id);
		setInt(ufo, "mission", id);
		raiseIdCounter(xcomBody, "ALIEN_MISSIONS", id + 1);
		setInt(copy, "liveUfos", 1);
		removeKey(copy, "alienBase");
		return;
	}
}

/// The target of a battle the alien host fought in the X-COM player's world.
/// That world held it only as a display copy of the alien player's object, and
/// no save writes display copies, so the object is copied from the alien
/// player's world, marked as in battle: the battle and its debriefing find it
/// as when the save was made. It takes the id the craft's destination names
/// (the id its display copy had), except a site or an alien base when the
/// alien player's other objects come along (@a carryAlienWorld): they keep
/// their own ids, so the target keeps its own too and the craft's destination
/// names that one. A UFO always takes the craft's id: the alien player's world
/// never names its UFOs. Returns the node of the copied object in the alien
/// player's world, or ryml::NONE when there is no target.
size_t copyBattleTarget(ryml::ConstNodeRef record, ryml::NodeRef alienBody, ryml::NodeRef xcomBody, bool carryAlienWorld)
{
	const std::string kind = getStr(record, "targetKind", std::string());
	const long long coopId = getInt(record, "targetCoopId", 0);
	if (getStr(record, "kind", std::string()) != "landing" || !getBool(record, "targetMirror", false) || coopId == 0)
		return ryml::NONE;
	const char* list = kind == "ufo" ? "ufos" : kind == "site" ? "missionSites" : kind == "alienBase" ? "alienBases" : nullptr;
	if (!list)
		return ryml::NONE;
	const char* coopKey = kind == "ufo" ? "coopUfoId" : kind == "site" ? "coopMissionId" : "coopAlienBaseId";
	const char* craftKey = kind == "ufo" ? "coopDestUfoId" : kind == "site" ? "coopDestMissionId" : "coopDestAlienBaseId";
	ryml::NodeRef sources = alienBody.find_child(ryml::to_csubstr(list));
	if (sources.invalid() || !sources.is_seq())
		return ryml::NONE;
	for (ryml::NodeRef source : sources.children())
	{
		if (getInt(source, ryml::to_csubstr(coopKey), 0) != coopId)
			continue;
		ryml::NodeRef target = appendCopy(xcomBody, ryml::to_csubstr(list), source);
		yamlutil::setBool(target, "inBattlescape", true);
		if (kind == "alienBase")
			yamlutil::setBool(target, "discovered", true);
		ryml::NodeRef craft = battleCraft(xcomBody, record);
		if (!craft.invalid())
		{
			ryml::NodeRef dest = craft.find_child("dest");
			const std::string destType = dest.invalid() ? std::string() : getStr(dest, "type", std::string());
			if (!destType.empty() && destType != "STR_WAY_POINT" && destType != "STR_BASE")
			{
				if (carryAlienWorld && kind != "ufo")
					setInt(dest, "id", getInt(target, "id", 0));
				else
					setInt(target, "id", getInt(dest, "id", 0));
				raiseIdCounter(xcomBody, destType, getInt(target, "id", 0) + 1);
			}
			removeKey(craft, ryml::to_csubstr(craftKey));
		}
		if (kind == "ufo")
		{
			raiseIdCounter(xcomBody, "STR_UFO_UNIQUE", getInt(target, "uniqueId", 0) + 1);
			if (!carryAlienWorld)
				copyUfoMission(alienBody, xcomBody, target);
		}
		return source.id();
	}
	return ryml::NONE;
}

/// The alien player's alien missions, UFOs, mission sites and alien bases come
/// into the X-COM player's world under their own ids, with that player's alien
/// strategy (@a battleTarget, the node of the battle's target, is already
/// there). The UFOs other than the battle target lose their detection and the
/// name it gave them: X-COM's radars find them again. The X-COM world's id
/// counters rise to at least the alien player's, except the craft, soldier and
/// waypoint numbering, so no new object takes a carried id. A list the X-COM
/// world already holds (@a xcomHeld) is not carried. Returns the report lines.
std::vector<std::string> copyAlienWorld(ryml::NodeRef alienBody, ryml::NodeRef xcomBody, size_t battleTarget,
	const std::vector<std::string>& xcomHeld)
{
	std::vector<std::string> report;
	std::vector<int> kept;
	for (const AlienList& kind : ALIEN_LISTS)
	{
		const bool held = std::find(xcomHeld.begin(), xcomHeld.end(), kind.key) != xcomHeld.end();
		if (held)
			report.push_back(std::string("The X-COM player's world already holds ") + kind.words
				+ "; the alien player's were not carried over.");
		const bool ufos = std::string(kind.key) == "ufos";
		int count = 0;
		ryml::NodeRef sources = alienBody.find_child(ryml::to_csubstr(kind.key));
		if (!sources.invalid() && sources.is_seq())
			for (ryml::NodeRef source : sources.children())
			{
				if (source.id() == battleTarget)
				{
					++count;
					continue;
				}
				if (held)
					continue;
				ryml::NodeRef copy = appendCopy(xcomBody, ryml::to_csubstr(kind.key), source);
				if (ufos)
					for (const char* field : { "detected", "hyperDetected", "id" })
						removeKey(copy, ryml::to_csubstr(field));
				++count;
			}
		kept.push_back(count);
	}
	ryml::NodeRef strategy = alienBody.find_child("alienStrategy");
	if (!strategy.invalid())
		replaceChild(xcomBody, strategy);

	std::set<std::string> ownNumbering = { "STR_SOLDIER", "STR_WAY_POINT" };
	for (ryml::NodeRef body : { alienBody, xcomBody })
	{
		ryml::NodeRef bases = body.find_child("bases");
		if (bases.invalid() || !bases.is_seq())
			continue;
		for (ryml::NodeRef base : bases.children())
		{
			ryml::NodeRef crafts = base.find_child("crafts");
			if (!crafts.invalid() && crafts.is_seq())
				for (ryml::NodeRef craft : crafts.children())
					ownNumbering.insert(getStr(craft, "type", std::string()));
		}
	}
	ryml::NodeRef ids = alienBody.find_child("ids");
	if (!ids.invalid() && ids.is_map())
		for (ryml::NodeRef counter : ids.children())
		{
			const std::string name(counter.key().str, counter.key().len);
			if (ownNumbering.count(name) == 0)
				raiseIdCounter(xcomBody, name, getInt(ids, counter.key(), 0));
		}

	report.push_back("Kept the alien player's " + std::to_string(kept[0]) + " alien mission(s), "
		+ std::to_string(kept[1]) + " UFO(s), " + std::to_string(kept[2]) + " site(s) and "
		+ std::to_string(kept[3]) + " alien base(s).");
	return report;
}

/// The host plays the aliens: the X-COM player's world, embedded in the host's
/// file, becomes the file's world under the host's header with that world's own
/// clock. The alien player's alien missions, UFOs, mission sites and alien
/// bases come along unless that world is still before its first month (it
/// rolls its own first missions then), and the rest of the alien player's
/// world is dropped (except the target of a battle the alien host fought in the
/// X-COM world). A file made before the X-COM player's first base reached the
/// host holds no X-COM world and is at month -1: the host's new-game world is
/// kept without its bases, and the X-COM player places its first base when the
/// campaign resumes.
void hostPlaysAliensToOneWorld(SaveSet& set)
{
	ryml::NodeRef header = set.host.header();
	const std::vector<std::string> roster = rosterOf(set);
	const int xcomSeat = 1;
	const std::string xcomName = roster.size() > 1 ? roster[1] : std::string();
	const int alienBases = countBases(set.host.body());
	const bool firstBasePending = set.clients.empty();
	std::vector<std::string> carried;
	if (!firstBasePending)
	{
		SaveWorld& xcom = set.clients.front().world;
		ryml::NodeRef alienBody = set.host.body();
		ryml::NodeRef xcomBody = xcom.body();
		const long long saveID = getInt(alienBody, "saveID", set.saveID);
		const bool carryAlienWorld = getInt(xcomBody, "monthsPassed", 0) >= 0;
		std::vector<std::string> xcomHeld;
		for (const AlienList& kind : ALIEN_LISTS)
			if (countList(xcomBody, kind.key) != 0)
				xcomHeld.push_back(kind.key);
		size_t battleTarget = ryml::NONE;
		ryml::ConstNodeRef record = header.find_child("coopPvpBorrowed");
		if (!record.invalid() && hasKey(xcomBody, "battleGame"))
			battleTarget = copyBattleTarget(record, alienBody, xcomBody, carryAlienWorld);
		if (carryAlienWorld)
			carried = copyAlienWorld(alienBody, xcomBody, battleTarget, xcomHeld);
		// The X-COM world's own clock: its months, history and timers run from it.
		ryml::NodeRef xcomTime = xcom.header().find_child("time");
		if (!xcomTime.invalid())
			replaceChild(header, xcomTime);
		std::swap(set.host.bodyTree, xcom.bodyTree);
		setInt(set.host.body(), "saveID", saveID);
	}
	ryml::NodeRef body = set.host.body();
	if (firstBasePending)
		removeKey(body, "bases");
	if (!hasKey(body, "battleGame"))
		for (const char* key : { "mission", "target", "craftOrBase", "turn", "coopBattleProtocol", "coopBattleId" })
			removeKey(header, ryml::to_csubstr(key));
	setInt(header, "saveSchema", 4);
	setInt(header, "coopCampaignType", 0);
	removeKey(header, "coopPvpBorrowed");

	int owned = 0;
	ryml::NodeRef bases = body.find_child("bases");
	if (!bases.invalid() && bases.is_seq())
		for (ryml::NodeRef base : bases.children())
		{
			yamlutil::setStr(base, "ownerplayername", xcomName);
			ownSoldiers(base.find_child("soldiers"), xcomSeat);
			++owned;
		}
	ownSoldiers(body.find_child("deadSoldiers"), xcomSeat);

	set.clients.clear(); // the emitter must not embed a world again
	removeKey(body, "coopClientSaves");
	removeKey(body, "separateCampaign");
	setInt(body, "coop_gamemode", 3);
	setInt(body, "coop_save_owner_player_id", 0);
	yamlutil::setBool(body, "no_bases", false);

	set.schema = 4;
	set.report.push_back("Schema 4: the PvP campaign is now one world, the X-COM player's.");
	if (firstBasePending)
	{
		set.report.push_back("The X-COM player places its first base when the campaign resumes.");
		set.report.push_back("Removed " + std::to_string(alienBases) + " base(s) of the alien player.");
		return;
	}
	set.report.push_back("All " + std::to_string(owned) + " base(s) now belong to " + xcomName + ".");
	set.report.push_back("Dropped the alien player's world (" + std::to_string(alienBases) + " base(s)).");
	set.report.insert(set.report.end(), carried.begin(), carried.end());
}

class Step_3_to_4 : public SchemaStep
{
public:
	int fromSchema() const override { return 3; }
	int toSchema() const override { return 4; }

	std::vector<InputRequest> requiredInputs(const SaveSet&) const override
	{
		return {};
	}

	void validate(const SaveSet& set, const UpgradeInputs&, PreflightResult& out) const override
	{
		if (!set.host.valid())
		{
			out.errors.push_back("The host save is not a valid two-document YAML stream.");
			return;
		}
		const int gamemode = gamemodeOf(set);
		if (gamemode != 2 && gamemode != 3)
		{
			out.errors.push_back("This build cannot upgrade this campaign to one world.");
			return;
		}
		const std::vector<std::string> roster = rosterOf(set);
		if (roster.size() < 2 || roster[0].empty() || roster[1].empty())
			out.errors.push_back("Every player needs a non-empty name for base ownership.");
		else if (roster[0] == roster[1])
			out.errors.push_back("Player names must be unique for base ownership: " + roster[0]);
		if (gamemode == 3)
		{
			// The host plays the aliens: the X-COM player's world is the file's one
			// embedded world. A file made before that world reached the host holds
			// none and is still at month -1.
			if (set.clients.size() > 1)
				out.errors.push_back("The save holds more than one player world; it cannot become one world.");
			else if (set.clients.empty() && getInt(set.host.body(), "monthsPassed", 0) != -1)
				out.errors.push_back("The X-COM player's world is missing from this save; it cannot become one world.");
			else if (!set.clients.empty() && (!set.clients.front().world.valid()
				|| countBases(set.clients.front().world.body()) == 0))
				out.errors.push_back("The X-COM player's world has no base.");
			return;
		}
		if (countBases(set.host.body()) == 0)
			out.errors.push_back("The X-COM player's world has no base.");
	}

	void apply(SaveSet& set, const UpgradeInputs&) const override
	{
		if (gamemodeOf(set) == 3)
		{
			hostPlaysAliensToOneWorld(set);
			return;
		}
		ryml::NodeRef header = set.host.header();
		ryml::NodeRef body = set.host.body();
		const std::vector<std::string> roster = rosterOf(set);
		// The host plays X-COM: its world is the one world, its seat owns it.
		const int xcomSeat = 0;
		const std::string xcomName = roster.empty() ? std::string() : roster[0];

		setInt(header, "saveSchema", 4);
		setInt(header, "coopCampaignType", 0);
		removeKey(header, "coopPvpBorrowed");

		int owned = 0;
		ryml::NodeRef bases = body.find_child("bases");
		if (!bases.invalid() && bases.is_seq())
			for (ryml::NodeRef base : bases.children())
			{
				yamlutil::setStr(base, "ownerplayername", xcomName);
				ownSoldiers(base.find_child("soldiers"), xcomSeat);
				++owned;
			}
		ownSoldiers(body.find_child("deadSoldiers"), xcomSeat);

		int dropped = 0;
		for (const ClientWorld& client : set.clients)
			if (client.world.valid())
				dropped += countBases(client.world.body());
		const size_t droppedWorlds = set.clients.size();
		set.clients.clear(); // the emitter must not embed the alien player's world again
		removeKey(body, "coopClientSaves");
		removeKey(body, "separateCampaign");
		setInt(body, "coop_save_owner_player_id", 0);
		yamlutil::setBool(body, "no_bases", false);

		set.schema = 4;
		set.report.push_back("Schema 4: the PvP campaign is now one world, the X-COM player's.");
		set.report.push_back("All " + std::to_string(owned) + " base(s) now belong to " + xcomName + ".");
		if (droppedWorlds)
			set.report.push_back("Dropped the alien player's world (" + std::to_string(dropped) + " base(s)).");
	}
};

} // namespace

const SchemaStep* step_3_to_4()
{
	static const Step_3_to_4 instance;
	return &instance;
}

} // namespace SaveUpgrade
} // namespace OpenXcom
