#pragma once
/*
 * Copyright 2010-2016 OpenXcom Developers.
 * Copyright 2023-2026 XComCoopTeam (https://www.moddb.com/mods/openxcom-coop-mod)
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
#include <cstdint>

namespace OpenXcom
{

/**
 * The battle-time seat a BattleUnit is currently controlled by (RB-D17).
 * Deliberately a small, dependency-free header: BattleUnit.h includes ONLY
 * this file for the coop seat tag, no Game.h/BattlescapeGame.h pollution.
 * NEVER a bool - N-player guardrail (see the runbook decisions ledger).
 */
enum CoopSeat : int8_t
{
	COOP_SEAT_NONE = -1,
	COOP_SEAT_0 = 0,
	COOP_SEAT_1 = 1,
	COOP_SEAT_2 = 2,
	COOP_SEAT_3 = 3
};

}
