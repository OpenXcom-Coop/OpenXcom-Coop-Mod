#!/usr/bin/env python3
"""Static guards for foreign-base globe routing and initial craft quotas."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    geo = read("src/Geoscape/GeoscapeState.cpp")
    separate = read("src/CoopMod/SeparateEcon.cpp")
    tcp = read("src/CoopMod/connectionTCP.cpp")
    harness = read("src/CoopMod/TestServer.cpp")

    route = geo.split("void GeoscapeState::openGlobeTargets", 1)[1]
    route = route.split("void GeoscapeState::", 1)[0]
    assert "isSeparateCampaign()" in route
    assert "base->_isForeignBase" in route
    assert "new BasescapeState(base, _globe)" in route
    assert "return;" in route
    assert "new MultipleTargetsState" in route
    assert 'req.get("include_craft", false)' in harness

    trim = separate.split("void trimInitialCraftCrews", 1)[1]
    trim = trim.split("int normalizeSoldierIds", 1)[0]
    assert "getMonthsPassed() != -1" in trim
    assert "capacity / playerCount" in trim
    assert "capacity % playerCount" in trim
    assert "soldier->setCraft(nullptr)" in trim
    assert "SeparateEcon::trimInitialCraftCrews(_game)" in tcp

    print("PASS Separate foreign-base routing and starting-crew contracts")


if __name__ == "__main__":
    main()
