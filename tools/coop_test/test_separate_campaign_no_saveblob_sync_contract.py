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
    require(
        "if (boundary && !separateCampaign) computeSaveBlobHash(game, e.saveBlob);",
        "the host must not record a whole-save hash for a separate campaign",
    )
    require(
        "if (game && game->getCoopMod() && game->getCoopMod()->isSeparateCampaign()) return;",
        "the client must not attach a whole-save hash for a separate campaign",
    )
    require(
        "syncCheckAttach(game, msg);",
        "structured battle hashes must remain enabled for separate campaigns",
    )
    print("PASS: separate campaign uses structured battle sync without saveBlob")


if __name__ == "__main__":
    main()
