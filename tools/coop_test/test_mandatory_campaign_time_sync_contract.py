"""Multiplayer campaign time synchronization is mandatory, not a user option."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    options_h = (ROOT / "src/Engine/Options.inc.h").read_text(encoding="utf-8")
    options_cpp = (ROOT / "src/Engine/Options.cpp").read_text(encoding="utf-8")
    tcp_h = (ROOT / "src/CoopMod/connectionTCP.h").read_text(encoding="utf-8")
    tcp_cpp = (ROOT / "src/CoopMod/connectionTCP.cpp").read_text(encoding="utf-8")
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src").rglob("*.cpp")
    )

    assert "EnableTimeSync" not in options_h
    assert "EnableTimeSync" not in options_cpp
    assert "_enable_time_sync" not in tcp_h
    assert "_enable_time_sync" not in sources
    assert 'root["enable_time_sync"] = true;' in tcp_cpp
    print("PASS campaign time sync is mandatory and the legacy wire key stays compatible")


if __name__ == "__main__":
    main()
