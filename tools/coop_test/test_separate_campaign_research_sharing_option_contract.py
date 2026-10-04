"""Separate exposes one simple Shared Research option, disabled by default."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
def main():
    options = (ROOT / "src/Engine/Options.cpp").read_text(encoding="utf-8")
    inc = (ROOT / "src/Engine/Options.inc.h").read_text(encoding="utf-8")
    tcp = (ROOT / "src/CoopMod/connectionTCP.cpp").read_text(encoding="utf-8")
    multi = (ROOT / "src/CoopMod/OptionsMultiplayer.cpp").read_text(encoding="utf-8")
    assert '"EnableResearchSync", &EnableResearchSync, false, "Shared Research (Separate)"' in options
    assert "RequireResearchShareApproval" not in inc + tcp + multi
    assert 'root["state"] = "research_sync_option"' in multi
    assert "setSeparateResearchSharingEnabled" in tcp
    print("PASS Separate has one host-authoritative Shared Research toggle, disabled by default")
if __name__ == "__main__": main()
