#pragma once

#include "../Engine/State.h"

namespace OpenXcom
{
class Window;
class Text;
class TextButton;
class Action;

class SeparateResearchModeWarningState : public State
{
	Window* _window;
	Text* _text;
	TextButton* _useSeparate;
	TextButton* _keepShared;
public:
	SeparateResearchModeWarningState();
	void btnUseSeparateClick(Action* action);
	void btnKeepSharedClick(Action* action);
};
}
