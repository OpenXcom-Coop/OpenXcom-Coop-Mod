"""test_midbattle_resume.py: resuming a mid-battle co-op save, in three scenarios.
  resume_turn_mode: the battle's turn mode and the exact END TURN baton holder come back from the save, even when the
      host's turn-mode option changed; a save without the baton key restarts the baton at the first live seat, and one
      without the mode key too resumes in parallel mode, without a refusal.
  protocol_stamp: a mid-battle save carrying another battle protocol stamp is refused; one without the stamp (an older
      version's shape) converts and loads; a geoscape co-op save and a solo battle save carry no stamp.
  client_save_disabled: the client cannot save in battle (its save writes no file and its pause menu hides SAVE GAME);
      the host's own save still writes.

Each scenario builds its OWN small live battle (resume_turn_mode: a traditional-mode SEPARATE guest battle to exercise
the baton; the other two: a plain SEPARATE guest battle, no walk needed, both saving at an already-quiescent moment)
rather than reuse test_coop_resume_battle_control.py's separate_resume process: every scenario runs to completion
inside its own foreground invocation, and a later invocation cannot reach back for a save file from an already-exited
process.

Run:  python tools/coop_test/test_midbattle_resume.py
Exit 0 = pass; 2 = failure.
"""

import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
from harness import shutdown_clients  # _build_midbattle_save's cleanup
import session

SDLK_ESCAPE = 27


def _wait_new_save(user_dir, before, timeout=10, interval=0.2):
    deadline = time.time() + timeout
    new_files = set()
    while time.time() < deadline:
        new_files = set(session.save_files(user_dir)) - before
        if new_files:
            return new_files
        time.sleep(interval)
    return new_files


def _strip_yaml_keys(src_path, dst_path, keys):
    """Copy `src_path` to `dst_path`, dropping any line whose stripped text
    starts with one of `keys` + ':' (each key is on its own line). Returns
    {key: lines_removed}."""
    with open(src_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    removed = {k: 0 for k in keys}
    out = []
    for ln in lines:
        s = ln.strip()
        hit = next((k for k in keys if s.startswith(k + ":")), None)
        if hit:
            removed[hit] += 1
            continue
        out.append(ln)
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "w", encoding="utf-8") as f:
        f.writelines(out)
    return removed


def _rewrite_protocol(src_path, dst_path, mode):
    """Copy `src_path` to `dst_path`. mode="zero" rewrites coopBattleProtocol's
    value to 0; mode="delete" drops the line entirely. Returns True if the key
    was found (a guard against a vacuous pass: the save carried the key to begin with)."""
    with open(src_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    found = False
    out = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("coopBattleProtocol:"):
            found = True
            if mode == "delete":
                continue
            ln = re.sub(r"coopBattleProtocol:\s*\S+", "coopBattleProtocol: 0", ln)
        out.append(ln)
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "w", encoding="utf-8") as f:
        f.writelines(out)
    return found


# =========================== resume_turn_mode ==============================================

def run_resume_turn_mode():
    print("\n===== SCENARIO resume_turn_mode: the saved turn mode and baton holder come back; missing keys degrade "
          "=====")
    host_dir = make_user_dir("midbattle_resume_mode_host", options={"CoopTurnMode": "traditional"})
    client_dir = make_user_dir("midbattle_resume_mode_client")
    host = GameClient("host", 48920, host_dir)
    client = GameClient("client", 48921, client_dir)
    host2 = client2 = None
    savepath = None
    try:
        host.spawn(); client.spawn(); host.connect(); client.connect()
        session.bring_up_separate_guest_battle(host, client, port="48922")

        # pass the baton: host (seat 0, the first live seat holds it first) -> seat 1
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def _baton_at_1():
            th = session.event_state(host).get("coopEndTurnTally", {}).get("activeSeat")
            tc = session.event_state(client).get("coopEndTurnTally", {}).get("activeSeat")
            return True if (th == 1 and tc == 1) else None

        host.wait_for("baton passed to seat 1", _baton_at_1, timeout=30, interval=0.3)
        for gc, tag in ((host, "host"), (client, "client")):
            tally = session.event_state(gc).get("coopEndTurnTally", {})
            assert tally.get("activeSeat") == 1, f"{tag}: tally.activeSeat={tally.get('activeSeat')} before save"
        assert session.battle_state(client).get("coopOffBatonGray") is False, (
            "client coopOffBatonGray is not False before save (client now holds the baton)")
        assert session.battle_state(host).get("coopOffBatonGray") is True, (
            "host coopOffBatonGray is not True before save (host no longer holds the baton)")
        print("PASS baton passed to seat 1 before save: tally.activeSeat==1 both, "
              "coopOffBatonGray client=False/host=True")

        before = set(session.save_files(host_dir))
        host.ok({"cmd": "save_game_ui", "type": "quick_battle"})
        new_files = _wait_new_save(host_dir, before, timeout=15)
        assert len(new_files) == 1, f"quiescent save did not write exactly one file: {new_files}"
        savefile = next(iter(new_files))
        savepath = os.path.join(host_dir, savefile)
        print(f"PASS quiescent save written -> {savefile}")
        host.shutdown(); client.shutdown()

        # ---- (i) the saved turn mode survives (the host option flips to parallel before relaunch)
        # and the exact baton holder comes back -----------------------------
        host2 = GameClient("host", 48923, make_user_dir("midbattle_resume_mode_host_kept",
                                                        options={"CoopTurnMode": "parallel"}))
        client2 = GameClient("client", 48924, make_user_dir("midbattle_resume_mode_client_kept"))
        shutil.copyfile(savepath, os.path.join(host2.user_dir, savefile))
        host2.spawn(); client2.spawn(); host2.connect(); client2.connect()
        session.resume_campaign_battle(host2, client2, os.path.basename(savefile),
                                       port="48925", timeout=180)
        for gc, tag in ((host2, "host"), (client2, "client")):
            es = session.event_state(gc)
            assert es.get("turnMode") == "traditional", (
                f"{tag}: turnMode={es.get('turnMode')!r} after resume, want 'traditional' (the saved mode survived)")
        assert session.event_state(host2).get("optionTurnMode") == "parallel", (
            f"host optionTurnMode={session.event_state(host2).get('optionTurnMode')!r}, "
            "want 'parallel' (the OPTION, unconsumed - the block's value won)")
        for gc, tag in ((host2, "host"), (client2, "client")):
            tally = session.event_state(gc).get("coopEndTurnTally", {})
            assert tally.get("activeSeat") == 1 and tally.get("needed") == 1, (
                f"{tag}: tally after resume = {tally}, want activeSeat=1 needed=1 "
                "(the EXACT holder came back, not a re-seed to the first live seat 0)")
        assert session.battle_state(client2).get("coopOffBatonGray") is False, (
            "client coopOffBatonGray not False after resume")
        assert session.battle_state(host2).get("coopOffBatonGray") is True, (
            "host coopOffBatonGray not True after resume")
        print("PASS resume_turn_mode (i): turnMode survives as 'traditional' despite optionTurnMode='parallel'; "
              "the exact baton holder (seat 1) came back")
        host2.shutdown(); client2.shutdown()
        host2 = client2 = None

        # ---- (ii) DEGRADE (baton): strip only coopActiveSeat -------------------
        host2 = GameClient("host", 48926, make_user_dir("midbattle_resume_mode_host_no_seat"))
        client2 = GameClient("client", 48927, make_user_dir("midbattle_resume_mode_client_no_seat"))
        removed = _strip_yaml_keys(savepath, os.path.join(host2.user_dir, savefile), ("coopActiveSeat",))
        assert removed["coopActiveSeat"] >= 1, f"coopActiveSeat line not found to strip: {removed}"
        host2.spawn(); client2.spawn(); host2.connect(); client2.connect()
        session.resume_campaign_battle(host2, client2, os.path.basename(savefile),
                                       port="48928", timeout=180)
        for gc, tag in ((host2, "host"), (client2, "client")):
            es = session.event_state(gc)
            assert es.get("turnMode") == "traditional", f"{tag}: turnMode={es.get('turnMode')!r}"
            tally = es.get("coopEndTurnTally", {})
            assert tally.get("activeSeat") == 0, (
                f"{tag}: DEGRADE(baton) activeSeat={tally.get('activeSeat')}, want 0 (the first live seat)")
        print("PASS resume_turn_mode (ii) DEGRADE(baton): missing coopActiveSeat -> the first live seat (0)")
        host2.shutdown(); client2.shutdown()
        host2 = client2 = None

        # ---- (iii) DEGRADE (mode): strip coopTurnMode + coopActiveSeat --------
        host2 = GameClient("host", 48929, make_user_dir("midbattle_resume_mode_host_no_keys"))
        client2 = GameClient("client", 48930, make_user_dir("midbattle_resume_mode_client_no_keys"))
        removed = _strip_yaml_keys(savepath, os.path.join(host2.user_dir, savefile),
                                   ("coopTurnMode", "coopActiveSeat"))
        assert removed["coopTurnMode"] >= 1 and removed["coopActiveSeat"] >= 1, (
            f"expected keys not found to strip: {removed}")
        host2.spawn(); client2.spawn(); host2.connect(); client2.connect()
        session.resume_campaign_battle(host2, client2, os.path.basename(savefile),
                                       port="48931", timeout=180)
        for gc, tag in ((host2, "host"), (client2, "client")):
            es = session.event_state(gc)
            assert es.get("turnMode") == "parallel", (
                f"{tag}: turnMode={es.get('turnMode')!r}, want 'parallel' (the default, no refusal)")
            tally = es.get("coopEndTurnTally", {})
            assert tally.get("activeSeat") == -1, (
                f"{tag}: DEGRADE(mode) activeSeat={tally.get('activeSeat')}, want -1")
        print("PASS resume_turn_mode (iii) DEGRADE(mode): missing both keys -> parallel (the default), "
              "activeSeat=-1, no refusal")
    finally:
        host.shutdown(); client.shutdown()
        if host2:
            host2.shutdown()
        if client2:
            client2.shutdown()


# =========================== protocol_stamp ==============================================

def _build_midbattle_save(tag, port_base):
    """A plain SEPARATE guest battle, saved at an already-quiescent moment (no
    walk needed - protocol_stamp/client_save_disabled test the save/load funnel, not the drain gate)."""
    host_dir = make_user_dir(f"{tag}_host")
    client_dir = make_user_dir(f"{tag}_client")
    host = GameClient("host", port_base, host_dir)
    client = GameClient("client", port_base + 1, client_dir)
    try:
        host.spawn(); client.spawn(); host.connect(); client.connect()
        session.bring_up_separate_guest_battle(host, client, port=str(port_base + 2))
        before = set(session.save_files(host_dir))
        host.ok({"cmd": "save_game_ui", "type": "quick_battle"})
        new_files = _wait_new_save(host_dir, before, timeout=15)
        assert len(new_files) == 1, f"quiescent save did not write exactly one file: {new_files}"
        savepath = os.path.join(host_dir, next(iter(new_files)))
    except BaseException:
        # no caller ever gets host / client (only the save's path), so a failed bring-up or save
        # shuts down the games it spawned here before the error propagates (shared_fixture.bring_up's form)
        shutdown_clients(host, client)
        raise
    host.shutdown(); client.shutdown()
    return savepath


def _assert_refused(user_dir, port, savefile_basename, variant):
    h = GameClient("host", port, user_dir)
    try:
        h.spawn(); h.connect()
        h.ok({"cmd": "load_save_menu", "file": savefile_basename})
        h.wait_for(f"{variant}: ErrorMessageState raised",
                  lambda: session.has_state(h, "ErrorMessageState") or None, timeout=30, interval=0.3)
        assert not session.has_state(h, "BattlescapeState"), (
            f"{variant}: BattlescapeState pushed despite the refusal: {session.states(h)}")
        assert not session.has_state(h, "HostMenu"), (
            f"{variant}: HostMenu pushed despite the refusal: {session.states(h)}")
        h.ok({"cmd": "dismiss_popup"})
        h.wait_for(f"{variant}: back at the main menu",
                  lambda: session.has_state(h, "MainMenuState") or None, timeout=30)
        w = h.ok({"cmd": "world_state"})
        assert not w.get("has_save"), f"{variant}: getSavedGame() not null after the refusal: {w}"
        gcoop = h.cmd({"cmd": "get_coop"})
        assert not gcoop.get("inBattle"), f"{variant}: inBattle true after the refusal: {gcoop}"
        logp = os.path.join(user_dir, "openxcom.log")
        text = ""
        if os.path.exists(logp):
            with open(logp, encoding="utf-8", errors="replace") as f:
                text = f.read()
        assert "different version of the mod" in text, (
            f"{variant}: refusal text not found in the log ({logp})")
        print(f"PASS protocol_stamp {variant}: refused (ErrorMessageState, no battle/HostMenu pushed, "
              f"main menu, log carries the refusal text)")
    finally:
        h.shutdown()


def _assert_converted(user_dir, port, savefile_basename, variant):
    """A mid-battle co-op save WITHOUT the coopBattleProtocol stamp is an older version's shape: the host's load
    converts it and reaches the host window, never the refusal."""
    convert_line = "[coop-convert] an older version's mid-battle co-op save converted"
    h = GameClient("host", port, user_dir)
    try:
        h.spawn(); h.connect()
        h.ok({"cmd": "load_save_menu", "file": savefile_basename})
        h.wait_for(f"{variant}: HostMenu (converted, not refused)",
                  lambda: session.has_state(h, "HostMenu") or None, timeout=60, interval=0.3)
        assert not session.has_state(h, "ErrorMessageState"), (
            f"{variant}: ErrorMessageState raised for an unstamped save: {session.states(h)}")
        logp = os.path.join(user_dir, "openxcom.log")

        def _logged():
            if not os.path.exists(logp):
                return None
            with open(logp, encoding="utf-8", errors="replace") as f:
                text = f.read()
            return text if convert_line in text else None

        text = h.wait_for(f"{variant}: the conversion log line", _logged, timeout=10, interval=0.25)
        assert "different version of the mod" not in text, f"{variant}: the refusal text is in the log ({logp})"
        assert text.count(convert_line) == 1, f"{variant}: {text.count(convert_line)} conversion log lines (want 1)"
        print(f"PASS protocol_stamp {variant}: converted (HostMenu, no refusal, one conversion log line)")
    finally:
        h.shutdown()

def run_protocol_stamp():
    print("\n===== SCENARIO protocol_stamp: a mid-battle save from another protocol version is refused =====")
    savepath = _build_midbattle_save("midbattle_resume_stamp_src", 48940)
    savefile = os.path.basename(savepath)

    # (i) coopBattleProtocol: 1 -> 0
    zero_dir = make_user_dir("midbattle_resume_stamp_zero")
    found = _rewrite_protocol(savepath, os.path.join(zero_dir, "xcom1", savefile), "zero")
    assert found, "coopBattleProtocol key not found in the source save to rewrite"
    _assert_refused(zero_dir, 48945, savefile, "protocol=0")

    # (ii) coopBattleProtocol key deleted - an OLDER version's shape: it converts and loads
    deleted_dir = make_user_dir("midbattle_resume_stamp_deleted")
    found = _rewrite_protocol(savepath, os.path.join(deleted_dir, "xcom1", savefile), "delete")
    assert found, "coopBattleProtocol key not found in the source save to delete"
    _assert_converted(deleted_dir, 48946, savefile, "protocol-deleted")

    # (iii) CONTROL: a GEOSCAPE coop save (no battle) - unaffected, resumes normally
    ctl_host_dir = make_user_dir("midbattle_resume_stamp_geo_host")
    ctl_client_dir = make_user_dir("midbattle_resume_stamp_geo_client")
    ctl_host = GameClient("host", 48947, ctl_host_dir)
    ctl_client = GameClient("client", 48948, ctl_client_dir)
    try:
        ctl_host.spawn(); ctl_client.spawn(); ctl_host.connect(); ctl_client.connect()
        session.new_campaign(ctl_host, ctl_client, port="48949")
        CTLSAVE = "geoscape_control.sav"
        ctl_host.ok({"cmd": "save_game", "file": CTLSAVE})
        ctlpath = os.path.join(ctl_host_dir, "xcom1", CTLSAVE)
        assert os.path.exists(ctlpath), "geoscape control save not on disk"
        with open(ctlpath, encoding="utf-8", errors="replace") as f:
            text = f.read()
        assert "coopBattleProtocol" not in text, (
            "CONTROL: a geoscape (no-battle) coop save unexpectedly carries coopBattleProtocol")
        ctl_host.shutdown(); ctl_client.shutdown()

        ctl_host = GameClient("host", 48950, ctl_host_dir)
        ctl_client = GameClient("client", 48951, make_user_dir("midbattle_resume_stamp_geo_client2"))
        ctl_host.spawn(); ctl_client.spawn(); ctl_host.connect(); ctl_client.connect()
        session.resume_campaign(ctl_host, ctl_client, CTLSAVE, port="48952")
        print("PASS protocol_stamp (iii) CONTROL: a geoscape coop save (no coopBattleProtocol) "
              "loads and resumes normally")
    finally:
        ctl_host.shutdown(); ctl_client.shutdown()

    # (iv) SP CONTROL: a solo mid-battle save's header is byte-identical
    sp_dir = make_user_dir("midbattle_resume_stamp_solo")
    sp = GameClient("sp", 48953, sp_dir)
    try:
        sp.spawn(); sp.connect()
        sp.ok({"cmd": "open_new_battle"})
        sp.wait_for("NewBattleState", lambda: session.has_state(sp, "NewBattleState"), timeout=60)
        sp.ok({"cmd": "newbattle_ok"})
        sp.wait_for("SP battle generated",
                   lambda: (session.has_state(sp, "BriefingState")
                            or session.has_state(sp, "InventoryState")
                            or session.has_state(sp, "BattlescapeState")) or None,
                   timeout=180, interval=0.5)
        if session.has_state(sp, "BriefingState"):
            sp.ok({"cmd": "close_briefing"})
        sp.wait_for("equip screen up after briefing",
                   lambda: session.has_state(sp, "InventoryState") or None, timeout=30, interval=0.3)
        assert session.battle_state(sp).get("coopSession") in (False, None, 0), (
            "SP CONTROL premise broken: this is a coop session, not plain SP")
        session.dismiss_battle_start_overlays(sp)
        assert session.has_state(sp, "BattlescapeState"), (
            f"SP CONTROL: could not reach BattlescapeState: {session.states(sp)}")
        before = set(session.save_files(sp_dir))
        sp.ok({"cmd": "save_game_ui", "type": "quick_battle"})
        new_files = _wait_new_save(sp_dir, before, timeout=15)
        assert len(new_files) == 1, f"SP quiescent save did not write exactly one file: {new_files}"
        sppath = os.path.join(sp_dir, next(iter(new_files)))
        with open(sppath, encoding="utf-8", errors="replace") as f:
            text = f.read()
        count = text.count("coopBattleProtocol")
        assert count == 0, f"SP CONTROL: solo save carries coopBattleProtocol {count} time(s) - not byte-identical"
        print("PASS protocol_stamp (iv) SP CONTROL: solo mid-battle save carries zero occurrences "
              "of coopBattleProtocol")
    finally:
        sp.shutdown()


# =========================== client_save_disabled ==============================================

def _wait_client_with_host_keepalive(client, host, desc, predicate, timeout=10, interval=0.2):
    """A plain client.wait_for() here leaves the HOST unpoked (no TestServer command at all) for the whole wait,
    and, reliably after the two earlier scenarios' process churn but never in isolation, the client's own
    peer-liveness check then decided the host connection was lost ("onClientDrop") and tore the battle down well
    before this wait's own timeout. Poking the host (get_state) during the wait prevents it every time. This is not a
    retry over a failing predicate: `predicate` is still polled to completion or TimeoutError exactly as wait_for
    would; this only adds a read-only host heartbeat so the game does not go idle while the CLIENT is under test."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = predicate()
        if last:
            return last
        try:
            host.cmd({"cmd": "get_state"})
        except Exception:
            pass
        time.sleep(interval)
    raise TimeoutError(f"client: timed out waiting for {desc} (last={last!r})")


def run_client_save_disabled():
    print("\n===== SCENARIO client_save_disabled: the client cannot save in battle =====")
    host_dir = make_user_dir("midbattle_resume_client_save_host")
    client_dir = make_user_dir("midbattle_resume_client_save_client")
    host = GameClient("host", 48960, host_dir)
    client = GameClient("client", 48961, client_dir)
    try:
        host.spawn(); client.spawn(); host.connect(); client.connect()
        session.bring_up_separate_guest_battle(host, client, port="48962")

        before_client = set(session.save_files(client_dir))
        client.ok({"cmd": "save_game_ui", "type": "quick_battle"})
        time.sleep(2.0)
        after_client = set(session.save_files(client_dir))
        assert after_client == before_client, (
            f"client_save_disabled: the client's user dir gained a save file: {after_client - before_client}")
        print("PASS client_save_disabled: client's quick_battle save wrote nothing (zero-disk)")

        client.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_ESCAPE})
        _wait_client_with_host_keepalive(
            client, host, "client PauseState opened",
            lambda: session.has_state(client, "PauseState"), timeout=10)
        lw = client.cmd({"cmd": "list_widgets"})
        save_widget = next((w for w in lw.get("widgets", [])
                            if (w.get("text") or "").strip().lower() == "save game"), None)
        assert save_widget is not None, f"no 'SAVE GAME' widget found in the client PauseState: {lw}"
        assert save_widget.get("visible") is False, (
            f"client PauseState's SAVE GAME button is VISIBLE (should be hidden): {save_widget}")
        print("PASS client_save_disabled: client's PauseState hides SAVE GAME")

        # A second ESCAPE sent right after list_widgets (no round trip between
        # them) was reliably swallowed: PauseState stayed open until the
        # unrelated peer-liveness teardown fired ~10 s later, while every
        # diagnostic run with an extra round trip here closed it within 1 s. A
        # short settle before the close press clears it every time: the same
        # kind of UI-settle wait as the click-ready settle in
        # session.assert_seat_commands, not a retry over a failed assertion.
        time.sleep(0.5)
        client.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_ESCAPE})
        _wait_client_with_host_keepalive(
            client, host, "client back on BattlescapeState",
            lambda: (session.top_state(client) == "BattlescapeState") or None, timeout=10)

        before_host = set(session.save_files(host_dir))
        host.ok({"cmd": "save_game_ui", "type": "quick_battle"})
        new_host_files = _wait_new_save(host_dir, before_host, timeout=15)
        assert new_host_files, "the host's OWN quick_battle save never wrote"
        print(f"PASS client_save_disabled control: the host's own quick_battle save DOES write -> {new_host_files}")
        print("ALL client_save_disabled ASSERTIONS PASSED")
    finally:
        host.shutdown(); client.shutdown()


def main():
    run_resume_turn_mode()
    run_protocol_stamp()
    run_client_save_disabled()
    print("\nALL MIDBATTLE RESUME TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[FAIL] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
    sys.exit(0)
