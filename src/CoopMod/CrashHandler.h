#pragma once
#include <string>

namespace CrashHandler
{
/// Install global handlers once at the very beginning of main().
void install();

/// Manual logging you can call from your own catch blocks.
void log(const std::string& message);

/// Snapshot the active mod list (id + version, comma-separated) into a static
/// buffer so a crash report can record which mods were loaded. Call from a
/// healthy point after mods (re)load - the crash writer only reads the buffer, it
/// never touches the heap. See Options::updateMods().
void setModList(const std::string& mods);

/// Directory where crash logs/dumps are written (for the test harness to locate
/// a probe log and assert its format). Ensures the directory is resolved.
std::string logDirectory();
}

/// Helper macro: logs message + file + line.
#define CRASH_LOG(msg) \
	CrashHandler::log(std::string(__FILE__) + ":" + std::to_string(__LINE__) + ": " + (msg))
