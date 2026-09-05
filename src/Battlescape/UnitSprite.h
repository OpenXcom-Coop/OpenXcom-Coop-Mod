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
#include "../Engine/Surface.h"
#include "../Engine/Script.h"
#include "../CoopMod/CoopGhost.h" // W1-P12: CoopUnitDrawView (full struct - the 4 inline accessors below read its fields)
#include "../Savegame/BattleUnit.h" // W1-P12: the 4 inline accessors below call _unit's own getters, so a forward declare is no longer enough

namespace OpenXcom
{

class BattleItem;
class SavedBattleGame;
class SurfaceSet;
class Mod;

/**
 * A class that renders a specific unit, given its render rules
 * combining the right frames from the surfaceset.
 */
class UnitSprite
{
private:
	struct Part
	{
		const Surface *src;
		int bodyPart;
		int offX;
		int offY;

		Part(int body, const Surface *s = nullptr) : src{ s }, bodyPart{ body }, offX{ 0 }, offY{ 0 } { }

		void operator=(const Surface *s) { src = s; }
		explicit operator bool() { return src; }
	};

	const BattleUnit *_unit;
	const BattleItem *_itemR, *_itemL;
	const SurfaceSet *_unitSurface, *_itemSurface, *_fireSurface, *_breathSurface, *_facingArrowSurface;
	Surface *_dest;
	const SavedBattleGame *_save;
	const Mod *_mod;
	int _part, _animationFrame, _drawingRoutine;
	bool _helmet;
	int _red, _blue;
	int _x, _y, _shade, _burn;
	GraphSubset _mask;
	// W1-P12: the presentation read-switch (CoopMod/CoopGhost.h). Null for
	// every caller except Map::drawUnit's &view argument - the 4 accessors
	// below are then SP-identical by construction (see their own bodies).
	const CoopUnitDrawView *_coopView = nullptr;
	/// W1-P12 motion-read accessors: `_coopView`'s field when a ghost is
	/// live, `_unit`'s own getter otherwise - EXACTLY the expression each one
	/// replaces (mechanical substitution, UnitSprite.cpp, WR-22).
	/// `uStatus()` returns int, not UnitStatus (Mod/Unit.h's enum): every one
	/// of UnitSprite.cpp's 47 call sites only ever compares the result
	/// against a STATUS_* constant, which an unscoped-enum-vs-int comparison
	/// handles with no cast needed.
	int uDir()       const { return _coopView ? _coopView->direction  : _unit->getDirection(); }
	int uWalkPhase() const { return _coopView ? (_coopView->walkPhase % 8) : _unit->getWalkingPhase(); }
	int uStatus()    const { return _coopView ? _coopView->status : (int)_unit->getStatus(); }
	bool uKneeled()  const { return _coopView ? _coopView->kneeled    : _unit->isKneeled(); }

	/// Drawing routine for XCom soldiers in overalls, sectoids (routine 0),
	/// mutons (routine 10),
	/// aquanauts (routine 13),
	/// aquatoids, calcinites, deep ones, gill men, lobster men, tasoths (routine 14).
	void drawRoutine0();
	/// Drawing routine for floaters.
	void drawRoutine1();
	/// Drawing routine for XCom tanks.
	void drawRoutine2();
	/// Drawing routine for cyberdiscs.
	void drawRoutine3();
	/// Drawing routine for civilians, ethereals, zombies (routine 4),
	/// tftd civilians, tftd zombies (routine 16), more tftd civilians (routine 17).
	void drawRoutine4();
	/// Drawing routine for sectopods and reapers.
	void drawRoutine5();
	/// Drawing routine for snakemen.
	void drawRoutine6();
	/// Drawing routine for chryssalid.
	void drawRoutine7();
	/// Drawing routine for silacoids.
	void drawRoutine8();
	/// Drawing routine for celatids.
	void drawRoutine9();
	/// Drawing routine for TFTD tanks.
	void drawRoutine11();
	/// Drawing routine for hallucinoids.
	void drawRoutine12();
	/// Drawing routine for biodrones.
	void drawRoutine16();
	/// Drawing routine for tentaculats.
	void drawRoutine19();
	/// Drawing routine for triscenes.
	void drawRoutine20();
	/// Drawing routine for xarquids.
	void drawRoutine21();
	/// Sort two handed sprites out.
	void sortRifles();
	/// Get graphic for unit part.
	void selectUnit(Part& p, int index, int offset);
	/// Get graphic for item part.
	void selectItem(Part& p, const BattleItem *item, int offset);
	/// Blit weapon sprite.
	void blitItem(Part& item);
	/// Blit body sprite.
	void blitBody(Part& body);
public:
	/// Creates a new UnitSprite at the specified position and size.
	UnitSprite(Surface* dest, const Mod* mod, const SavedBattleGame* save, int frame, bool helmet, int red, int blue);
	/// Cleans up the UnitSprite.
	~UnitSprite();
	/// Draws the unit.
	/// W1-P12: `coopView` is a defaulted presentation read-switch (CoopMod/
	/// CoopGhost.h) - null (the default) is byte-identical to the
	/// pre-W1-P12 vanilla behaviour.
	void draw(const BattleUnit* unit, int part, int x, int y, int shade, GraphSubset mask, bool drawFacingIndicator,
	          const CoopUnitDrawView* coopView = nullptr);
};

} //namespace OpenXcom

