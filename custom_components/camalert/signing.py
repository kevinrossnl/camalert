"""Signed colour keys (#82). Home Assistant gives every player a fresh secret with its webhook; the player signs each
key press (time, one-time nonce, HMAC-SHA256). A press is accepted once, within MAX_AGE seconds, so nothing else on
the network can fake or replay one (a green key may open a gate). Same signature as camalert_core.keymap."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time

MAX_AGE = 60  # seconds a press may be old (or ahead, for clocks that differ a little)
NONCE = re.compile(r"^[0-9a-f]{16,64}$")


def signature(secret: str, node, camera, button, ts, nonce) -> str:
    msg = "|".join([str(node or ""), str(camera or ""), str(button or ""), str(int(ts)), str(nonce or "")])
    return hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()


class ButtonGuard:
    """The secret of one player and the nonces it has used (kept in memory: a restart makes a new secret)."""

    def __init__(self, secret: str | None = None, clock=time.time):
        self.secret = secret or secrets.token_hex(32)
        self._clock = clock
        self._seen: dict[str, float] = {}

    def check(self, data: dict) -> str | None:
        """None when the press is valid (and remembers its nonce), else why it was refused."""
        try:
            ts = int(data.get("ts"))
        except (TypeError, ValueError):
            return "not signed"
        nonce, sig = str(data.get("nonce") or ""), str(data.get("sig") or "")
        if not NONCE.match(nonce) or not sig:
            return "not signed"
        now = self._clock()
        if abs(now - ts) > MAX_AGE:
            return "too old"
        want = signature(self.secret, data.get("receiver"), data.get("camera"), data.get("button"), ts, nonce)
        if not hmac.compare_digest(want, sig.lower()):
            return "wrong signature"
        self._seen = {n: t for n, t in self._seen.items() if t > now}
        if nonce in self._seen:
            return "used twice"
        self._seen[nonce] = now + 2 * MAX_AGE
        return None
