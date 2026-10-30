"""Runtime: replicated event OK must actually push a Ufopaedia ArticleState."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import separate_campaign_fixture as fixture
import session


def main():
    js = fixture.bring_up("sep_event_article", (48992, 48993, 48292))
    client = js.client
    try:
        probe = client.ok({"cmd": "probe_replicated_event_article"})
        article = probe["article"]
        assert probe["researchName"] == article, probe
        assert session.has_state(client, "GeoscapeEventState"), session.states(client)

        dismissed = client.ok({"cmd": "dismiss_popup"})
        assert dismissed["handled"] == "GeoscapeEventState", dismissed
        client.wait_for(
            "replicated event Ufopaedia article",
            lambda: session.has_state(client, "ArticleState"),
        )
        print(f"PASS replicated event OK opened ArticleState for {article}")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
