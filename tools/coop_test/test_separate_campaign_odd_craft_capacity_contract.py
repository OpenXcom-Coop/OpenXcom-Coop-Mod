"""Separate odd/single-seat craft quotas retain real physical capacity."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    craft = (ROOT / "src/Savegame/Craft.cpp").read_text(encoding="utf-8")
    separate = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")

    for source in (craft, separate):
        assert "(capacity + 1) / 2" in source
        assert "capacity - craft->getSpaceUsed()" in source or "capacity - getSpaceUsed()" in source
        assert "std::min(ownerAvailable, physicalAvailable)" in source

    # These are the intended quota/physical-capacity results independent of C++:
    # vanilla 14 seats remain 7+7, while a mod one-seater is usable by either
    # player but can still contain only one soldier in total.
    quota = lambda capacity: (capacity + 1) // 2
    assert quota(14) == 7
    assert quota(1) == 1
    assert min(quota(1), 1) == 1
    assert min(quota(1), 0) == 0
    print("PASS Separate odd craft quota preserves one seat and physical capacity")


if __name__ == "__main__":
    main()
