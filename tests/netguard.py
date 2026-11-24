"""Network guard for the tests (#73): no test may reach the network.

Every outbound socket (TCP connect/connect_ex, UDP sendto/sendmsg) to an address that is not loopback raises
NetworkBlocked and is recorded; tests/conftest.py installs the guard for the whole run and fails the test that caused
an attempt, also when the code under test swallowed the error (a network error is usually caught and logged).
Host names other than "localhost" are blocked too: they would need DNS. Local fakes (tests/fakes, e.g.
FakeGo2rtc().start()) listen on 127.0.0.1 and keep working.
"""
import contextlib
import ipaddress
import socket
import threading

ERRNO = 101  # ENETUNREACH: code under test sees an ordinary "network unreachable" OSError
CURRENT = {"test": None}  # node id of the running test (set by the conftest fixture)
_BLOCKED = []  # (test id, address) of every blocked attempt
_LOCK = threading.Lock()
_ORIG = {}


class NetworkBlocked(OSError):
    """An outbound socket to a non-loopback address during tests (#73)."""


def is_local(address):
    """True for loopback addresses, 'localhost' and non-IP sockets (AF_UNIX paths)."""
    if not isinstance(address, tuple) or not address:
        return True
    host = address[0]
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    host = str(host).split("%", 1)[0]
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check(address):
    if is_local(address):
        return
    with _LOCK:
        _BLOCKED.append((CURRENT["test"] or "<outside a test>", address))
    raise NetworkBlocked(ERRNO, "network access blocked during tests (#73): %r is not a loopback address; use a "
                                "fake on 127.0.0.1 (tests/fakes) instead of a real server" % (address,))


def _target(name, first, args):
    """Destination of connect/connect_ex(address), sendto(data[, flags], address), sendmsg(bufs, anc, flags, addr)."""
    if name in ("connect", "connect_ex"):
        return first
    if name == "sendto":
        return args[-1] if args else None
    return args[2] if len(args) >= 3 else None


def _guard(name):
    orig = getattr(socket.socket, name)

    def guarded(self, first, *args):
        target = _target(name, first, args)
        if target is not None:
            check(target)
        return orig(self, first, *args)
    guarded.__name__ = name
    _ORIG[name] = orig
    setattr(socket.socket, name, guarded)


def install():
    if not _ORIG:
        for name in ("connect", "connect_ex", "sendto", "sendmsg"):
            _guard(name)


def uninstall():
    for name, orig in _ORIG.items():
        setattr(socket.socket, name, orig)
    _ORIG.clear()


def installed():
    return bool(_ORIG)


def blocked(test_id):
    """Sorted unique addresses blocked during one test."""
    with _LOCK:
        return sorted(set(repr(a) for t, a in _BLOCKED if t == test_id))


def summary():
    with _LOCK:
        return sorted(set("%s -> %r" % ta for ta in _BLOCKED))


@contextlib.contextmanager
def expect_blocked():
    """For tests of the guard itself: yields the list of addresses blocked inside the block and forgets them, so
    the test does not fail on its own deliberate attempts."""
    with _LOCK:
        start = len(_BLOCKED)
    seen = []
    try:
        yield seen
    finally:
        with _LOCK:
            seen.extend(a for _t, a in _BLOCKED[start:])
            del _BLOCKED[start:]
