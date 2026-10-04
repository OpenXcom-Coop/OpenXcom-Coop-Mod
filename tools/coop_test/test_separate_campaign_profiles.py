"""Live Separate research isolation and instant-sharing regression."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import separate_campaign_fixture as fixture

def profiles(gc):
    state = gc.ok({"cmd": "separate_profile_state"})
    return state, {p["name"]: p for p in state["players"]}

def main():
    js = fixture.bring_up("sep_profiles", (48982, 48983, 48282))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        state, initial = profiles(host)
        assert set(initial) == {"HostPlayer", "ClientPlayer"}, initial
        assert state["researchSharingEnabled"] is False, state

        host.ok({"cmd": "separate_profile_set", "player": "HostPlayer",
                 "completedResearch": "STR_MEDI_KIT"})
        _, isolated = profiles(host)
        assert "STR_MEDI_KIT" in isolated["HostPlayer"]["completedResearch"], isolated
        assert "STR_MEDI_KIT" not in isolated["ClientPlayer"].get("completedResearch", []), isolated

        host.ok({"cmd": "set_option", "name": "EnableResearchSync", "value": True})
        state, shared = profiles(host)
        assert state["researchSharingEnabled"] is True, state
        # Profiles stay private storage even in shared mode; their union is
        # promoted to SavedGame's canonical global discovery list.
        assert "STR_MEDI_KIT" not in shared["ClientPlayer"].get("completedResearch", []), shared
        for player in ("HostPlayer", "ClientPlayer"):
            check = host.ok({"cmd": "separate_research_check", "player": player,
                             "research": "STR_MEDI_KIT"})
            assert check["researched"] is True, check

        # Switching back seeds both private profiles with shared discoveries.
        host.ok({"cmd": "set_option", "name": "EnableResearchSync", "value": False})
        state, private_again = profiles(host)
        assert state["researchSharingEnabled"] is False, state
        assert "STR_MEDI_KIT" in private_again["HostPlayer"]["completedResearch"], private_again
        assert "STR_MEDI_KIT" in private_again["ClientPlayer"]["completedResearch"], private_again

        host.ok({"cmd": "separate_profile_set", "player": "HostPlayer", "faction": "A"})
        host.ok({"cmd": "separate_profile_set", "player": "ClientPlayer", "faction": "B"})
        state, _ = profiles(host)
        assert state["differentFactions"] is True, state

        restored = host.ok({"cmd": "separate_profile_roundtrip"})
        assert restored["serializedBytes"] > 0, restored
        print("PASS Separate research: private default, instant shared mode, faction warning predicate")
    finally:
        js.shutdown()

if __name__ == "__main__": main()
