"""Do not open or replicate a new-research dialog when its list is empty."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    geo = (ROOT / "src/Geoscape/GeoscapeState.cpp").read_text(encoding="utf-8")
    start = geo.index("// 3h. inform about new possible research")
    end = geo.index("// 3i. inform about new possible manufacture", start)
    block = geo[start:end]

    guard = block.index("if (!newPossibleResearch.empty())")
    popup = block.index("popup(new NewPossibleResearchState")
    broadcast = block.index('SharedEcon::hostAlert(_game, "NewPossibleResearchState"')
    assert guard < popup < broadcast

    print("PASS empty new-research lists produce no local or replicated popup")


if __name__ == "__main__":
    main()
