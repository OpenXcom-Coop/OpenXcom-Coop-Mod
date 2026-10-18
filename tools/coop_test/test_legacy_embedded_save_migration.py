#!/usr/bin/env python3
"""Migrate a real schema-2 host save containing coopClientSaves blobs.

The source is copied to a hermetic harness user folder and is never modified.
Usage:
  python -u tools/coop_test/test_legacy_embedded_save_migration.py PATH_TO_SAVE
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir


def two_docs(path):
    with open(path, "r", encoding="utf-8") as stream:
        text = stream.read()
    parts = re.split(r"^---\s*$", text, maxsplit=1, flags=re.MULTILINE)
    assert len(parts) == 2, "expected a two-document YAML stream"
    return parts


def roster_from_header(header):
    match = re.search(r"^coopPlayers:\s*$((?:\r?\n\s+-[^\r\n]+)+)",
                      header, re.MULTILINE)
    assert match, "header has no coopPlayers roster"
    return [line.split("-", 1)[1].strip().strip("'\"")
            for line in match.group(1).splitlines() if "-" in line]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("save")
    args = parser.parse_args()
    source = os.path.abspath(args.save)
    assert os.path.isfile(source), source

    source_header, source_body = two_docs(source)
    assert re.search(r"^coopClientSaves:\s*$", source_body, re.MULTILINE), \
        "source has no coopClientSaves sequence"
    blob_count = len(re.findall(r"^\s+- key:\s*", source_body, re.MULTILINE))
    assert blob_count > 0, "source has no embedded client entries"
    roster = roster_from_header(source_header)
    assert len(roster) >= 2, roster

    user_dir = make_user_dir("real_embedded_migration", saves=(source,))
    save_name = os.path.basename(source)
    stem, extension = os.path.splitext(save_name)
    upgraded_name = stem + "_upgraded" + extension
    upgraded_path = os.path.join(user_dir, "xcom1", upgraded_name)

    game = GameClient("host", 48998, user_dir)
    try:
        game.spawn()
        game.connect()
        detected = game.ok({"cmd": "upgrade_detect", "file": save_name})
        assert detected["kind"] == "legacy", detected
        assert detected["variant"] == "embed", detected

        result = game.ok({"cmd": "upgrade_run", "host": save_name,
                          "hostName": roster[0]})
        assert result["success"], result
        assert not result["errors"], result
        assert os.path.isfile(upgraded_path), upgraded_path

        header, body = two_docs(upgraded_path)
        assert re.search(r"^saveSchema:\s*3\s*$", header, re.MULTILINE), header
        assert re.search(r"^coopCampaignType:\s*0\s*$", header, re.MULTILINE), header
        assert not re.search(r"^coopClientSaves:\s*$", body, re.MULTILINE), \
            "embedded blobs survived migration"
        owners = {value.strip().strip("'\"") for value in re.findall(
            r"^\s+ownerplayername:\s*([^\r\n]+)$", body, re.MULTILINE)}
        assert set(roster).issubset(owners), (roster, owners)
        base_count = len(re.findall(r"^\s{2}- lon:\s*", body, re.MULTILINE))
        assert base_count >= len(roster), (base_count, roster)
        soldier_owners = {int(value) for value in re.findall(
            r"^\s+ownerplayerid:\s*(\d+)\s*$", body, re.MULTILINE)}
        assert set(range(len(roster))).issubset(soldier_owners), soldier_owners

        current = game.ok({"cmd": "upgrade_detect", "file": upgraded_name})
        assert current["kind"] == "current", current
        loaded = game.ok({"cmd": "load_raw", "file": upgraded_name})
        assert loaded["threw"] is False, loaded

        game.ok({"cmd": "load_save", "file": upgraded_name})
        profiles = game.ok({"cmd": "separate_profile_state"})
        fund_counts = {p["name"]: p["fundsCount"] for p in profiles["players"]}
        assert set(fund_counts) == set(roster), (fund_counts, roster)
        assert len(set(fund_counts.values())) == 1, \
            f"player funds histories are not aligned for GraphsState: {fund_counts}"

        print("PASS real embedded migration:",
              f"{blob_count} blob(s), {base_count} bases, owners={sorted(owners)}")
        print("PASS upgraded save is schema 3, blob-free, current, and loadable")
    finally:
        game.shutdown()


if __name__ == "__main__":
    main()
