/*
 * Schema 2 -> 3: replace SEPARATE's embedded per-player worlds with one
 * host-authoritative world.  Every real base is copied into the host bases
 * sequence and carries its unique locked roster name in ownerplayername.
 */
#include "SaveUpgradeTypes.h"

#include <set>
#include <string>

namespace OpenXcom
{
namespace SaveUpgrade
{
namespace
{

using yamlutil::getInt;
using yamlutil::getStr;
using yamlutil::hasKey;
using yamlutil::removeKey;
using yamlutil::setInt;

int countBases(ryml::ConstNodeRef body)
{
	ryml::ConstNodeRef bases = body.find_child("bases");
	return (!bases.invalid() && bases.is_seq()) ? static_cast<int>(bases.num_children()) : 0;
}

void tagBaseTree(ryml::NodeRef base, const std::string& ownerName, int ownerSeat)
{
	yamlutil::setStr(base, "ownerplayername", ownerName);
	// Soldiers remain physically contained by their owned base.  Explicitly
	// stamp them too so battle ownership agrees with strategic ownership.
	ryml::NodeRef soldiers = base.find_child("soldiers");
	if (!soldiers.invalid() && soldiers.is_seq())
		for (ryml::NodeRef soldier : soldiers.children())
			setInt(soldier, "ownerplayerid", ownerSeat);
}

int rosterSeat(const SaveSet& set, const ClientWorld& client, size_t fallback)
{
	for (size_t i = 0; i < set.roster.size(); ++i)
		if (!client.name.empty() && set.roster[i] == client.name)
			return static_cast<int>(i);
	return static_cast<int>(fallback);
}

class Step_2_to_3 : public SchemaStep
{
public:
	int fromSchema() const override { return 2; }
	int toSchema() const override { return 3; }

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
		const int campaignType = static_cast<int>(getInt(set.host.header(), "coopCampaignType", 0));
		if (campaignType == 1)
			return; // SHARED already is one world; only its schema stamp changes.
		std::set<std::string> playerNames;
		ryml::ConstNodeRef roster = set.host.header().find_child("coopPlayers");
		if (!roster.invalid() && roster.is_seq())
		{
			for (ryml::ConstNodeRef player : roster.children())
			{
				std::string name = player.has_val() ? std::string(player.val().str, player.val().len) : std::string();
				if (name.empty())
					out.errors.push_back("Every player needs a non-empty name for base ownership.");
				else if (!playerNames.insert(name).second)
					out.errors.push_back("Player names must be unique for base ownership: " + name);
			}
		}

		int total = countBases(set.host.body());
		for (const ClientWorld& client : set.clients)
			total += countBases(client.world.body());
		if (total == 0)
			out.errors.push_back("The separate campaign contains no bases.");
		if (total > 8)
			out.warnings.push_back("The separate campaign contains " + std::to_string(total)
				+ " bases. They will all be preserved, but no new base can be built unless the total falls below 8.");

		// A missing blob means part of the old separate campaign is unavailable.
		// Refuse instead of silently producing a save which loses that player.
		const size_t expectedClients = (!roster.invalid() && roster.is_seq() && roster.num_children() > 0)
			? roster.num_children() - 1 : 0;
		if (set.clients.size() < expectedClients)
			out.errors.push_back("One or more player worlds are missing from coopClientSaves; refusing a lossy merge.");
	}

	void apply(SaveSet& set, const UpgradeInputs&) const override
	{
		ryml::NodeRef header = set.host.header();
		setInt(header, "saveSchema", 3);
		if (getInt(header, "coopCampaignType", 0) == 1)
		{
			set.report.push_back("Schema 3: SHARED campaign already uses one authoritative world.");
			return;
		}

		// Read the roster directly when this run began at schema 2.  A chained
		// 1->2 run also populated SaveSet::roster in the preceding step.
		if (set.roster.empty())
		{
			ryml::ConstNodeRef roster = header.find_child("coopPlayers");
			if (!roster.invalid() && roster.is_seq())
				for (ryml::ConstNodeRef p : roster.children())
					set.roster.push_back(p.has_val() ? std::string(p.val().str, p.val().len) : std::string());
		}

		ryml::NodeRef hostBody = set.host.body();
		ryml::NodeRef hostBases = hostBody.find_child("bases");
		if (hostBases.invalid())
		{
			hostBases = yamlutil::mapChild(hostBody, "bases");
			hostBases |= ryml::SEQ;
		}
		const std::string hostName = set.roster.empty() ? std::string() : set.roster[0];
		for (ryml::NodeRef base : hostBases.children())
			tagBaseTree(base, hostName, 0);

		int imported = 0;
		for (size_t i = 0; i < set.clients.size(); ++i)
		{
			ClientWorld& client = set.clients[i];
			const int owner = rosterSeat(set, client, i + 1);
			const std::string ownerName = owner >= 0 && static_cast<size_t>(owner) < set.roster.size()
				? set.roster[owner] : client.name;
			ryml::NodeRef clientBases = client.world.body().find_child("bases");
			if (clientBases.invalid() || !clientBases.is_seq())
				continue;
			for (ryml::NodeRef sourceBase : clientBases.children())
			{
				// Cross-tree duplicate copies the complete base subtree: facilities,
				// soldiers, crafts, stores, projects, productions and transfers.
				const size_t after = hostBases.num_children() ? hostBases.last_child().id() : ryml::NONE;
				size_t id = hostBases.tree()->duplicate(sourceBase.tree(), sourceBase.id(), hostBases.id(), after);
				tagBaseTree(hostBases.tree()->ref(id), ownerName, owner);
				++imported;
			}
		}

		removeKey(hostBody, "coopClientSaves");
		setInt(hostBody, "coop_save_owner_player_id", 0);
		set.clients.clear(); // emitter must never recreate schema-2 blobs
		set.schema = 3;
		set.report.push_back("Unified SEPARATE campaign into the host save; imported "
			+ std::to_string(imported) + " client base(s).");
		set.report.push_back("All bases now carry unique ownerplayername values; client-world blobs removed.");
		if (hostBases.num_children() > 8)
			set.report.push_back("Grandfathered over-cap campaign: all "
				+ std::to_string(hostBases.num_children())
				+ " bases were preserved; construction remains locked while the total is 8 or more.");
	}
};

} // namespace

const SchemaStep* step_2_to_3()
{
	static const Step_2_to_3 instance;
	return &instance;
}

} // namespace SaveUpgrade
} // namespace OpenXcom
