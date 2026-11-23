"""Small client for the CamAlert HTTP API on an Enigma2 receiver."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode


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


class CamAlertError(Exception):
    """Receiver not reachable or request refused."""


class CamAlertApi:
    def __init__(self, session, host: str, port: int, https: bool = False, verify_ssl: bool = False, token: str = ""):
        self._session = session
        self.host, self.port, self.https, self.verify_ssl, self.token = host, port, https, verify_ssl, token

    async def _get(self, action: str, params: dict | None = None) -> dict[str, Any]:
        import aiohttp  # provided by Home Assistant

        params = dict(params or {})
        headers = {"X-CamAlert-Token": self.token} if self.token else {}
        url = build_url(self.host, self.port, self.https, action, params)
        try:
            async with self._session.get(url, headers=headers, ssl=self.verify_ssl if self.https else None,
                                         timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise CamAlertError(str(err)) from err
        if resp.status == 400 and isinstance(data, dict) and data.get("error"):
            raise CamAlertError(data["error"])
        if resp.status == 403:
            raise CamAlertError("forbidden (token or network)")
        if not isinstance(data, dict):
            raise CamAlertError("unexpected answer")
        return data

    async def status(self) -> dict[str, Any]:
        return await self._get("status")

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
