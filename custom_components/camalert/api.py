"""Small client for the CamAlert HTTP API on a player (Enigma2 receiver or Kodi).

API version 1 (status has api_version/capabilities): actions are sent with POST and a JSON body, reads with GET;
the token always goes in the X-CamAlert-Token header. Older players (no api_version in /status) get GET requests
like before.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

INTEGRATION_VERSION = "1.0.0"  # = manifest.json version
ACTIONS = ("show", "mosaic", "tour", "hide", "ptz", "webhook")  # change something on the player: POST


def build_url(host: str, port: int, https: bool, action: str, params: dict | None = None) -> str:
    """URL for an API action; empty parameters are left out."""
    scheme = "https" if https else "http"
    host = "[%s]" % host if ":" in host and not host.startswith("[") else host
    query = urlencode({k: v for k, v in (params or {}).items() if v not in (None, "")})
    return "%s://%s:%d/camalert/%s%s" % (scheme, host, int(port), action, ("?" + query) if query else "")


def show_params(cam, mode=None):
    """camera may be one name, 'a,b' or a list: 2-4 cameras are shown together in one corner window (strip)."""
    if isinstance(cam, (list, tuple)):
        names = [str(c).strip() for c in cam if str(c).strip()]
    else:
        names = [c.strip() for c in (cam or "").split(",") if c.strip()]
    if len(names) > 1 and not mode:
        mode = "strip" if len(names) <= 4 else None
    return (",".join(names) or None), mode


def version_tuple(v) -> tuple:
    out = []
    for part in str(v or "0").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits or 0))
    return tuple(out)


def plan_request(action: str, params: dict | None, capabilities) -> tuple[str, dict, dict | None]:
    """(method, query params, JSON body or None) for an action on a player with these capabilities
    (None = unknown/older player: GET with query parameters)."""
    params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    is_action = action in ACTIONS or (action == "dnd" and "on" in params)
    if capabilities is not None and "post" in capabilities and is_action:
        return "POST", {}, params
    return "GET", params, None


class CamAlertError(Exception):
    """Player not reachable or request refused."""


class CamAlertApi:
    def __init__(self, session, host: str, port: int, https: bool = False, verify_ssl: bool = False, token: str = ""):
        self._session = session
        self.host, self.port, self.https, self.verify_ssl, self.token = host, port, https, verify_ssl, token
        self.api_version: int | None = None
        self.capabilities: list[str] | None = None  # None until /status was read (or an older player)
        self.platform: str | None = None
        self.min_ha_version: str | None = None

    def supports(self, capability: str) -> bool:
        """True if the player has this capability (unknown/older players: assume yes, they tell with an error)."""
        return self.capabilities is None or capability in self.capabilities

    def integration_too_old(self) -> bool:
        return bool(self.min_ha_version) and version_tuple(self.min_ha_version) > version_tuple(INTEGRATION_VERSION)

    async def _get(self, action: str, params: dict | None = None) -> dict[str, Any]:
        import aiohttp  # provided by Home Assistant

        method, query, body = plan_request(action, params, self.capabilities)
        headers = {"X-CamAlert-Token": self.token} if self.token else {}
        url = build_url(self.host, self.port, self.https, action, query)
        kwargs = {"headers": headers, "ssl": self.verify_ssl if self.https else None,
                  "timeout": aiohttp.ClientTimeout(total=10)}
        if body is not None:
            kwargs["json"] = body
        try:
            async with self._session.request(method, url, **kwargs) as resp:
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise CamAlertError(str(err)) from err
        if resp.status == 400 and isinstance(data, dict) and data.get("error"):
            raise CamAlertError(data["error"])
        if resp.status == 403:
            raise CamAlertError("forbidden (token or network)")
        if resp.status == 429:
            raise CamAlertError("too many requests")
        if resp.status in (404, 405, 501):
            raise CamAlertError("not supported by this player (%s)" % action)
        if not isinstance(data, dict):
            raise CamAlertError("unexpected answer")
        return data

    async def status(self) -> dict[str, Any]:
        data = await self._get("status")
        if data.get("api_version"):
            self.api_version = int(data["api_version"])
            self.capabilities = list(data.get("capabilities") or [])
            self.platform = data.get("platform")
            self.min_ha_version = data.get("min_ha_version")
        return data

    async def cameras(self) -> list[dict[str, Any]]:
        return (await self._get("cameras")).get("cameras", [])

    async def show(self, cam: str | list | None = None, seconds: int | None = None, mode: str | None = None,
                   priority: str | None = None, label: str | None = None) -> dict:
        cam, mode = show_params(cam, mode)
        return await self._get("show", {"cam": cam, "sec": seconds, "mode": mode, "priority": priority, "label": label})

    async def dnd(self, on: bool | None = None) -> dict:
        return await self._get("dnd", {} if on is None else {"on": "1" if on else "0"})

    async def webhook(self, url: str) -> dict:
        return await self._get("webhook", {"url": url} if url else {"url": ""})

    async def ptz(self, cam: str, move: str) -> dict:
        return await self._get("ptz", {"cam": cam, "move": move})

    async def log(self, lines: int = 300) -> list[str]:
        return (await self._get("log", {"lines": lines})).get("lines", [])

    async def events(self) -> list[dict]:
        return (await self._get("events")).get("events", [])

    async def mosaic(self, cams: list[str] | None = None, seconds: int | None = None) -> dict:
        return await self._get("mosaic", {"cam": ",".join(cams) if cams else None, "sec": seconds})

    async def hide(self) -> dict:
        return await self._get("hide")
