/*
 * Schema 3 -> 4: a PvP campaign kept as one world per player becomes one
 * world, the X-COM player's.  Every base carries that player's name in
 * ownerplayername; the other player's embedded world is dropped.
 */
#include "SaveUpgradeTypes.h"

#include <string>
#include <vector>

namespace OpenXcom
{
namespace SaveUpgrade
{
namespace
{

using yamlutil::getInt;
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
		if (gamemode != 2)
		{
			out.errors.push_back("This build cannot upgrade this campaign to one world.");
			return;
		}
		const std::vector<std::string> roster = rosterOf(set);
		if (roster.size() < 2 || roster[0].empty() || roster[1].empty())
			out.errors.push_back("Every player needs a non-empty name for base ownership.");
		else if (roster[0] == roster[1])
			out.errors.push_back("Player names must be unique for base ownership: " + roster[0]);
		if (countBases(set.host.body()) == 0)
			out.errors.push_back("The X-COM player's world has no base.");
	}

	void apply(SaveSet& set, const UpgradeInputs&) const override
	{
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
