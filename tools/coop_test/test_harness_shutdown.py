"""Regression: shutdown reaps processes and rejects unexpected game exits."""

import subprocess
from unittest.mock import Mock, patch

import harness


class Process:
    def __init__(self, exit_code=0, already_exited=False, timeout=False):
        self.pid = 12345
        self.exit_code = exit_code
        self.returncode = exit_code if already_exited else None
        self.timeout = timeout
        self.calls = []

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.calls.append("wait")
        if self.timeout and "kill" not in self.calls:
            raise subprocess.TimeoutExpired("shutdown-probe", timeout)
        self.returncode = self.exit_code
        return self.returncode

    def kill(self):
        self.calls.append("kill")


def client(process):
    gc = harness.GameClient("shutdown-probe")
    gc.proc = process
    gc.sock = Mock()
    gc.buf = b"old response"
    return gc


def expect_failure(gc, **kwargs):
    sock = gc.sock
    with patch.object(harness, "_report_port_file_error") as report:
        try:
            gc.shutdown(**kwargs)
        except RuntimeError as exc:
            assert "shutdown failed" in str(exc), str(exc)
        else:
            raise AssertionError("unexpected shutdown was accepted")
        assert report.call_args.args[0] == "shutdown_failed"
    sock.close.assert_called_once()
    assert gc.sock is None and gc.buf == b""


def main():
    gc = client(Process())
    sock = gc.sock
    gc.shutdown()
    sock.sendall.assert_called_once()
    sock.close.assert_called_once()
    assert gc.proc.returncode == 0 and gc.proc.calls == ["wait"]
    assert gc.sock is None and gc.buf == b""
    gc.shutdown()
    print("PASS normal shutdown and repeated cleanup")

    gc = client(Process(already_exited=True))
    sock = gc.sock
    gc.shutdown()
    sock.sendall.assert_not_called()
    print("PASS already-exited game receives no duplicate quit")

    expect_failure(client(Process(0xC0000409, already_exited=True)))
    print("PASS unexpected fast-fail rejected")

    gc = client(Process(77, already_exited=True))
    gc.shutdown(expected_returncodes=(77,))
    gc.shutdown()
    expect_failure(client(Process(78, already_exited=True)),
                   expected_returncodes=(77,))
    print("PASS intentional exit allowance is exact, not any nonzero code")

    gc = client(Process(harness.KILLED_RETURN_CODE))
    gc.kill()
    gc.shutdown()
    assert gc.proc.calls == ["kill", "wait", "wait"], gc.proc.calls
    gc.proc = Process(78, already_exited=True)
    gc.sock = Mock()
    expect_failure(gc)
    print("PASS deliberate peer kill is reaped; its allowance does not survive respawn")

    first, second = Mock(), Mock()
    first.shutdown.side_effect = RuntimeError("first peer failed")
    try:
        harness.shutdown_clients(first, None, second)
    except RuntimeError as exc:
        assert "first peer failed" in str(exc), str(exc)
    else:
        raise AssertionError("peer cleanup failure was swallowed")
    second.shutdown.assert_called_once()
    print("PASS a failing peer does not prevent remaining peer cleanup")

    gc = client(Process(1, timeout=True))
    expect_failure(gc, expected_returncodes=(0, 1))
    assert gc.proc.calls == ["wait", "kill", "wait"], gc.proc.calls
    assert gc.proc.poll() == 1
    print("PASS forced cleanup is reaped and still fails")

    gc = harness.GameClient("shutdown-ack",
                            user_dir=harness.make_user_dir("shutdown_ack"))
    try:
        gc.spawn()
        gc.connect()
        gc.ok({"cmd": "quit"})
        print("PASS real game delivered the quit acknowledgement")
    finally:
        gc.shutdown()
    assert gc.proc.returncode == 0, gc.proc.returncode
    print("PASS real game exited normally after acknowledgement")

    print("ALL HARNESS SHUTDOWN TESTS PASSED")


if __name__ == "__main__":
    main()
