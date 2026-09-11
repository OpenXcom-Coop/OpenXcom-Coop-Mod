"""Regression: the port-file reader tolerates the publisher's rename handle.

F104/F113/F114: while the game publishes testserver_port.txt (it writes a .tmp
then std::rename()s it onto the final name), the CRT briefly holds a handle on
the final file with DELETE access and share READ|WRITE|DELETE. A reader that
opens with only share READ|WRITE is refused ERROR_SHARING_VIOLATION, surfaced as
PermissionError/EACCES(13) - the observed port-read failure. The fix is
harness._port_file_opener, a Windows open() opener that additionally grants
FILE_SHARE_DELETE so the read is compatible with that transient publisher
handle, WITHOUT masking any genuine sharing/ACL/access denial.

This test exercises the real opener from harness (not a replica). The
Windows-only contention scenarios hold a local handle shaped like the game's
rename handle (DELETE access, share R|W|D). The portable scenarios (ordinary
read, missing file) assert real behaviour on every OS.
"""

import ctypes
import errno
import os
import tempfile
from unittest.mock import patch

import harness

IS_WIN = os.name == "nt"

# The game writes the ephemeral port as decimal digits followed by CRLF. Seven
# bytes here so a successful read can be asserted to be complete, byte for byte.
PAYLOAD = b"52198\r\n"
TEXT = "52198\n"  # PAYLOAD decoded with universal-newline translation


if IS_WIN:
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _CreateFileW = _k32.CreateFileW
    _CreateFileW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    _CreateFileW.restype = wintypes.HANDLE
    _CloseHandle = _k32.CloseHandle
    _CloseHandle.argtypes = (wintypes.HANDLE,)
    _CloseHandle.restype = wintypes.BOOL

    _GENERIC_READ = 0x80000000
    _DELETE = 0x00010000
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _FILE_SHARE_DELETE = 0x00000004
    _OPEN_EXISTING = 3
    _FILE_ATTRIBUTE_NORMAL = 0x00000080
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    _SHARE_RWD = _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE
    _SHARE_RW = _FILE_SHARE_READ | _FILE_SHARE_WRITE

    class Holder:
        """Holds an open handle on `path` with a fixed access/share, like the
        game's rename handle, until released."""

        def __init__(self, path, access, share):
            h = _CreateFileW(path, access, share, None, _OPEN_EXISTING,
                             _FILE_ATTRIBUTE_NORMAL, None)
            if h is None or h == _INVALID_HANDLE_VALUE:
                raise ctypes.WinError(ctypes.get_last_error())
            self._h = h

        def close(self):
            if self._h is not None:
                if not _CloseHandle(self._h):
                    raise ctypes.WinError(ctypes.get_last_error())
                self._h = None

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()


def _write_port(path):
    with open(path, "wb") as f:
        f.write(PAYLOAD)


def _read_repaired_bytes(path):
    """Read via the ACTUAL harness opener, in binary, to prove exact bytes."""
    with open(path, "rb", opener=harness._port_file_opener) as f:
        return f.read()


def _read_repaired_text(path):
    with open(path, encoding="utf-8", opener=harness._port_file_opener) as f:
        return f.read()


def scenario_ordinary_read_preserved(path):
    _write_port(path)
    assert _read_repaired_bytes(path) == PAYLOAD, "opener changed the bytes read"
    assert _read_repaired_text(path) == TEXT, "opener changed text decoding"
    print("PASS ordinary UTF-8 read through the opener is preserved")


def scenario_missing_path_raises_filenotfound(path):
    missing = path + ".does-not-exist"
    try:
        with open(missing, encoding="utf-8", opener=harness._port_file_opener) as f:
            f.read()
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing file did not raise FileNotFoundError")
    print("PASS missing port file raises FileNotFoundError (retryable), not fatal")


def scenario_delete_holder_blocks_ordinary_read(path):
    _write_port(path)
    with Holder(path, _GENERIC_READ | _DELETE, _SHARE_RWD):
        try:
            with open(path, encoding="utf-8") as f:
                f.read()
        except PermissionError as exc:
            assert exc.errno == errno.EACCES, exc.errno
        else:
            raise AssertionError(
                "ordinary open unexpectedly succeeded against a DELETE-access holder")
        # The repaired opener reads the complete payload without waiting for the
        # holder to be released.
        assert _read_repaired_bytes(path) == PAYLOAD, "repaired read was incomplete"
    print("PASS DELETE-access publisher handle blocks the ordinary read but not "
          "the repaired opener")


def scenario_controls_allow_ordinary_read(path):
    _write_port(path)
    # Same holder shape but WITHOUT DELETE access: nothing needs FILE_SHARE_DELETE,
    # so the ordinary reader is fine. This isolates DELETE as the trigger.
    with Holder(path, _GENERIC_READ, _SHARE_RW):
        with open(path, encoding="utf-8") as f:
            assert f.read() == TEXT
    # Holder released entirely: ordinary reader is fine.
    with open(path, encoding="utf-8") as f:
        assert f.read() == TEXT
    print("PASS removing DELETE access or releasing the holder restores ordinary reads")


def scenario_exclusive_holder_denies_both(path):
    _write_port(path)
    # An exclusive (share 0) holder is a genuine denial. The repaired opener must
    # NOT bypass it - FILE_SHARE_DELETE only relaxes the delete-sharing conflict.
    with Holder(path, _GENERIC_READ, 0):
        try:
            with open(path, encoding="utf-8") as f:
                f.read()
        except PermissionError as exc:
            assert exc.errno == errno.EACCES, exc.errno
        else:
            raise AssertionError("ordinary open bypassed an exclusive holder")
        try:
            _read_repaired_bytes(path)
        except PermissionError as exc:
            assert exc.errno == errno.EACCES, exc.errno
            assert exc.winerror == 32, exc.winerror
            assert exc.filename == path, exc.filename
        else:
            raise AssertionError(
                "repaired opener bypassed an exclusive holder - it must surface "
                "genuine denials")
    print("PASS exclusive holder denies both reads (share R|W|D does not mask denials)")


def scenario_opener_closes_its_handle(path):
    _write_port(path)
    with open(path, "rb", opener=harness._port_file_opener) as f:
        assert not os.get_inheritable(f.fileno()), "port descriptor is inheritable"
        assert f.read() == PAYLOAD
    # If the opener leaked its handle (share R|W|D, READ access), this exclusive
    # reopen would fail with a sharing violation. Success proves it was closed.
    Holder(path, _GENERIC_READ, 0).close()
    print("PASS repaired opener releases its handle (exclusive reopen after close succeeds)")


def scenario_failed_fd_transfer_closes_handle(path):
    _write_port(path)
    error = OSError(errno.EMFILE, "controlled descriptor-allocation failure")
    with patch.object(harness.msvcrt, "open_osfhandle", side_effect=error):
        try:
            _read_repaired_bytes(path)
        except OSError as exc:
            assert exc is error, "descriptor failure was replaced or swallowed"
        else:
            raise AssertionError("descriptor allocation unexpectedly succeeded")
    Holder(path, _GENERIC_READ, 0).close()
    print("PASS failed descriptor transfer propagates and closes its native handle")


def main():
    with tempfile.TemporaryDirectory(prefix="oxc-port-pub-") as d:
        path = os.path.join(d, "testserver_port.txt")

        scenario_ordinary_read_preserved(path)
        scenario_missing_path_raises_filenotfound(path)

        if IS_WIN:
            assert harness._port_file_opener is not None, \
                "Windows must install the share-delete opener"
            scenario_delete_holder_blocks_ordinary_read(path)
            scenario_controls_allow_ordinary_read(path)
            scenario_exclusive_holder_denies_both(path)
            scenario_opener_closes_its_handle(path)
            scenario_failed_fd_transfer_closes_handle(path)
        else:
            assert harness._port_file_opener is None, \
                "non-Windows must keep the default opener"
            print("Windows sharing controls are not applicable; portable controls ran")

    print("ALL PORT PUBLICATION TESTS PASSED")


if __name__ == "__main__":
    main()
