#pragma once
/*
 * Copyright 2010-2019 OpenXcom Developers.
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
#include "../Engine/Yaml.h"
#include <string>

namespace OpenXcom
{

class RuleEvent;

/**
 * Represents a custom Geoscape event, generated in the background and waiting to pop up.
 */
class GeoscapeEvent
{
private:
	const RuleEvent &_rule;
	size_t _spawnCountdown;
	bool _over;
	std::string _ownerPlayerName;
	std::string _rewardPlayerName; // coop SEPARATE, shared research: the player whose base finished the research
	bool _coopShared; // coop SEPARATE: the other player has the same event, on the same timer
	bool _coopBothWorlds = false; // coop: SEPARATE, shared research - the other player's world spawned this same event (main #197), on its own timer
public:
	/// Creates a blank GeoscapeEvent.
	GeoscapeEvent(const RuleEvent &rule);
	/// Cleans up the event info.
	~GeoscapeEvent();
	/// Loads the event from YAML.
	void load(const YAML::YamlNodeReader& reader);
	/// Saves the event to YAML.
	void save(YAML::YamlNodeWriter writer) const;
	/// Gets the event's ruleset.
	const RuleEvent &getRules() const { return _rule; };
	/// Gets the minutes until the event pops up.
	size_t getSpawnCountdown() const { return _spawnCountdown; }
	/// Sets the minutes until the event pops up.
	void setSpawnCountdown(size_t minutes);
	const std::string& getOwnerPlayerName() const { return _ownerPlayerName; }
	void setOwnerPlayerName(const std::string& owner) { _ownerPlayerName = owner; }
	/// Coop SEPARATE, shared research: the player whose base finished the research that spawned this event (its
	/// rewards go to that player's first own base); empty for an event with an owner or no research behind it.
	const std::string& getRewardPlayerName() const { return _rewardPlayerName; }
	void setRewardPlayerName(const std::string& player) { _rewardPlayerName = player; }

	/// Is this event over?
	bool isOver() const { return _over; }
	/// Coop SEPARATE: does the other player have this same event, on the same timer?
	bool isCoopShared() const { return _coopShared; }
	/// Coop SEPARATE: marks this event as shared with the other player.
	void setCoopShared(bool shared) { _coopShared = shared; }
	/// Coop: does the other player's world hold this same event (spawned by research both players learned)?
	bool isCoopBothWorlds() const { return _coopBothWorlds; }
	/// Coop: marks this event as one both worlds hold.
	void setCoopBothWorlds(bool both) { _coopBothWorlds = both; }
	/// Coop SEPARATE: the host's copy of this shared event fired, so this one fires now.
	void setOver() { _over = true; }
	/// Handle event spawning schedule.
	void think();
};

}
