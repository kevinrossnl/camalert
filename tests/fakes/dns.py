"""A fake name resolver for host names under the reserved .example TLD (RFC 2606), so tests of the webhook host
check (#53) never depend on real DNS. install() wraps socket.getaddrinfo once; every other name and every address
goes to the real resolver (the in-process MQTT broker uses localhost)."""
import socket

NAMES = {
    "ha.split-dns.example": ["192.168.1.20"],          # split DNS: a full name that resolves into the LAN
    "ha.tailnet.example": ["100.101.102.103"],          # a Tailscale (CGNAT) address
    "ha.public.example": ["203.0.113.10"],              # documentation range = not the local network (#52)
    "ha.mixed.example": ["192.168.1.20", "203.0.113.10"],  # one public answer is enough to refuse
}
_real = socket.getaddrinfo


def _fake(host, port, *args, **kwargs):
    h = (host.decode() if isinstance(host, bytes) else str(host or "")).lower().rstrip(".")
    if h.endswith(".example"):
        if h not in NAMES:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        return [(socket.AF_INET6 if ":" in a else socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port or 0))
                for a in NAMES[h]]
    return _real(host, port, *args, **kwargs)


def install():
    socket.getaddrinfo = _fake
