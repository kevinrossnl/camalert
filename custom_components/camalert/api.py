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
        if resp.status == 403:
            raise CamAlertError("forbidden (token or network)")
        if not isinstance(data, dict):
            raise CamAlertError("unexpected answer")
        return data

    async def status(self) -> dict[str, Any]:
        return await self._get("status")

    async def cameras(self) -> list[dict[str, Any]]:
        return (await self._get("cameras")).get("cameras", [])

    async def show(self, cam: str | None = None, seconds: int | None = None, mode: str | None = None,
                   priority: str | None = None) -> dict:
        return await self._get("show", {"cam": cam, "sec": seconds, "mode": mode, "priority": priority})

    async def mosaic(self, cams: list[str] | None = None, seconds: int | None = None) -> dict:
        return await self._get("mosaic", {"cam": ",".join(cams) if cams else None, "sec": seconds})

    async def hide(self) -> dict:
        return await self._get("hide")
