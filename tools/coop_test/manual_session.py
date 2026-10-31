"""Bring up a live 2-player co-op campaign and LEAVE IT RUNNING for hand testing.

The automated suites tear their session down in a `finally`; this does the exact
same bring-up (session.new_campaign -> both players settled on the geoscape) and
then walks away, leaving two usable game windows behind.

Differences from a suite run, all deliberate:
  * the two processes are DETACHED, so they outlive this script;
  * windows spawn normally instead of minimised (harness.GameClient.spawn uses
    SW_SHOWMINNOACTIVE, which is right for unattended runs and wrong here);
  * the machine-wide harness lock is NOT taken - it is released the moment this
    script exits anyway, so holding it would only be misleading. Do not run the
    automated suites while a manual session is up: they would fight over ports.

Both instances keep their TestServer open (OXC_TEST_PORT), so the session can be
driven or inspected from outside while you play - e.g. arming a defeat:

    {"cmd": "set_ending", "ending": 2}   # 0 none, 1 win, 2 lose
    {"cmd": "ending_state"}
    {"cmd": "coop_dialog_info"}

tools/coop_session.ps1 is the PowerShell front end for all of this.

Run:  python tools/coop_test/manual_session.py [--mode shared|separate]
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from harness import GameClient, make_user_dir
import session
import geo

# DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: the games must survive this
# script exiting, and must not die with the console that launched it.
DETACHED = 0x00000008 | 0x00000200


def spawn_visible(gc, window_pos):
    """Like GameClient.spawn, but visible, detached, and without the lock."""
    env = os.environ.copy()
    env["OXC_TEST_PORT"] = str(gc.port)
    env["SDL_VIDEO_WINDOW_POS"] = window_pos
    gc.proc = subprocess.Popen(
        [harness.EXE, "-user", gc.user_dir],
        env=env, cwd=os.path.dirname(harness.EXE), creationflags=DETACHED)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("shared", "separate"), default="shared",
                    help="campaign economy model (default: shared)")
    ap.add_argument("--host-port", type=int, default=49100)
    ap.add_argument("--client-port", type=int, default=49101)
    ap.add_argument("--coop-port", type=int, default=48400)
    ap.add_argument("--host-name", default="HostPlayer")
    ap.add_argument("--client-name", default="ClientPlayer")
    args = ap.parse_args()

    if not os.path.exists(harness.EXE):
        sys.exit(f"no build at {harness.EXE} - run tools/worktree_bootstrap.ps1 -Build")

    # User dirs are keyed by port: make_user_dir WIPES what it finds, so two
    # sessions on different ports must not name the same folder or starting the
    # second one would delete the first's world out from under it.
    tag = f"manual_{args.host_port}"
    host = GameClient("host", args.host_port, make_user_dir(f"{tag}_host"))
    client = GameClient("client", args.client_port, make_user_dir(f"{tag}_client"))

    spawn_visible(host, "0,40")
    spawn_visible(client, "700,40")
    host.connect()
    client.connect()

    # session.new_campaign speaks the flow's own vocabulary: "coop" is SEPARATE.
    session.new_campaign(host, client, port=str(args.coop_port),
                         host_name=args.host_name, client_name=args.client_name,
                         campaign_mode="shared" if args.mode == "shared" else "coop")
    geo.wait_both_ready(host, client)

    print()
    print(f"READY - {args.mode.upper()} campaign, both players live on the geoscape.")
    print(f"  host    pid {host.proc.pid:<6} test port {args.host_port}  {host.user_dir}")
    print(f"  client  pid {client.proc.pid:<6} test port {args.client_port}  {client.user_dir}")
    print(f"  coop session port {args.coop_port}")


if __name__ == "__main__":
    main()
