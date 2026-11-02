#!/usr/bin/env python3
"""Contract checks for separate-campaign battle sync without legacy save blobs."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "CoopMod" / "SharedEcon.cpp"


def require(fragment: str, reason: str) -> None:
    text = SOURCE.read_text(encoding="utf-8")
    if fragment not in text:
        raise AssertionError(reason)


def main() -> None:
    # The battle's saveBlob hash reads the battle alone, so no campaign's world (a separate
    # campaign's included) enters a battle comparison.
    require(
        "bool computeSaveBlobHash(SavedBattleGame* battle, std::uint64_t& out, std::string* yamlOut)",
        "the battle's saveBlob hash must read only the battle, never the whole save",
    )
    text = SOURCE.read_text(encoding="utf-8")
    if "computeSaveBlobHash(game" in text or "computeSaveBlobHash(SavedGame" in text:
        raise AssertionError("no caller may hash the whole save as a battle saveBlob")
    require(
        "bool computeBattleHashes(SavedBattleGame* battle, BattleHashSet& out)",
        "structured battle hashes must remain enabled for separate campaigns",
    )
    print("PASS: separate campaign battles compare structured hashes and a battle-only saveBlob")


if __name__ == "__main__":
    main()
