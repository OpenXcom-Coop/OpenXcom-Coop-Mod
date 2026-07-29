#pragma once
/*
 * Copyright 2010-2016 OpenXcom Developers.
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

#define MIN_REQUIRED_RULESET_VERSION_NUMBER 8,4,1,0

// Co-op save schema version. Bumped whenever the on-disk co-op save format
// changes; every save writes it into the header as "saveSchema". The in-game
// Save Upgrader (src/Savegame/Upgrade/) detects older schemas and migrates
// them up to this current value one step at a time. See PRD save-upgrader.md.
#define SAVE_SCHEMA_CURRENT 2

#define OPENXCOM_VERSION_ENGINE "Extended"
#define OPENXCOM_VERSION_SHORT "Extended 8.4.2"
#define OPENXCOM_VERSION_LONG "8.4.2.0"
#define OPENXCOM_VERSION_NUMBER 8,4,2,0

// Upstream OXCE version this fork is synced from. Unlike the macros above it is
// NEVER stamped by CI (tools/ci/stamp_version.sh rewrites those with the coop
// mod's own build version, e.g. 8.4.13201) - bump it by hand on each OXCE rebase.
#define OPENXCOM_VERSION_OXCE "8.4.2"

// Numeric form of OPENXCOM_VERSION_OXCE, for OXCE engine-compat checks (mod
// requiredExtendedVersion in ModInfo.cpp) and the update check
// (CrossPlatform::isHigherThanCurrentVersion). Like OPENXCOM_VERSION_OXCE it is
// NEVER stamped by CI - bump both together on each OXCE rebase. The stamped
// OPENXCOM_VERSION_NUMBER above is the coop mod's own version (e.g. 2,0,0,0)
// and must never be used for OXCE compatibility comparisons: a coop version
// numerically below the OXCE version would silently fail every mod's
// engine-version requirement.
#define OPENXCOM_VERSION_OXCE_NUMBER 8,4,2,0

// Release channel of this build; stamped by tools/ci/stamp_version.sh.
// Local/dev builds keep "dev".
#ifndef OPENXCOM_VERSION_CHANNEL
#define OPENXCOM_VERSION_CHANNEL "dev"
#endif

#ifndef OPENXCOM_VERSION_GIT
#define OPENXCOM_VERSION_GIT " (v2025-10-06)"
#endif
