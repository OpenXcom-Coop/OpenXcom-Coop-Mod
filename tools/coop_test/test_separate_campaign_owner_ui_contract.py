"""Contracts for named mission ownership and readable foreign-target errors."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    for source in ("src/Geoscape/UfoDetectedState.cpp",
                   "src/Geoscape/MissionDetectedState.cpp",
                   "src/Geoscape/MultipleTargetsState.cpp"):
        code = text(source)
        assert 'STR_COOP_MISSION_BELONGS_TO_PLAYER' in code, source
        assert "missionTargetOwner" in code, source
        assert "ErrorMessageState" in code, source
    for lang in ("bin/common/Language/en-US.yml", "bin/common/Language/en-GB.yml"):
        assert 'STR_COOP_MISSION_BELONGS_TO_PLAYER: "This belongs to {0}"' in text(lang)
    print("PASS named, palette-safe Separate mission ownership popup contract")


if __name__ == "__main__":
    main()
