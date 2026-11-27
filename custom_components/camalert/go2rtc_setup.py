"""Home Assistant sends its go2rtc address to a player (#122): the suggested address and the request.

A player that was never set up accepts any address; a player that is set up only one in the local network
(the player decides, see /camalert/setup in docs/integrations/api.md)."""
from __future__ import annotations

import logging
from urllib.parse import urlsplit

from .api import CamAlertAlreadySetUp, CamAlertError, CamAlertForbidden

_LOGGER = logging.getLogger(__name__)
CONF_GO2RTC = "go2rtc_server"
CONF_CAMERA = "camera"
GO2RTC_PORT = 1984
LOOPBACK = ("127.0.0.1", "localhost", "::1")


async def _ha_address(hass) -> str | None:
    """The LAN address of Home Assistant, None when unknown."""
    try:
        from homeassistant.components.network import async_get_source_ip
        ip = await async_get_source_ip(hass)
        if ip:
            return ip
    except Exception:  # noqa: BLE001 - network integration not loaded
        pass
    try:
        from homeassistant.helpers.network import get_url
        return urlsplit(get_url(hass, allow_external=False, allow_cloud=False)).hostname
    except Exception:  # noqa: BLE001 - no internal URL configured
        return None


def _go2rtc_app_installed(hass) -> bool:
    """The go2rtc app (add-on) is installed on Home Assistant OS / Supervised."""
    try:
        from homeassistant.components.hassio import get_addons_info, is_hassio
        if not is_hassio(hass):
            return False
        return any("go2rtc" in str(slug) for slug in (get_addons_info(hass) or {}))
    except Exception:  # noqa: BLE001 - no Supervisor
        return False


async def suggested_go2rtc(hass) -> str:
    """The go2rtc address to offer: the URL of the go2rtc integration (with Home Assistant's LAN address when it
    points to Home Assistant itself), else Home Assistant's LAN address with port 1984 when the go2rtc app is
    installed; empty when none is known (the built-in go2rtc of Home Assistant is not reachable from a player)."""
    host = None
    for entry in hass.config_entries.async_entries("go2rtc"):
        url = (entry.data or {}).get("url")
        if not url:
            continue
        p = urlsplit(url)
        if p.hostname and p.hostname not in LOOPBACK:
            return url.rstrip("/")
        host = host or await _ha_address(hass)
        if host:
            return "%s://%s:%d" % (p.scheme or "http", host, p.port or GO2RTC_PORT)
    if _go2rtc_app_installed(hass):
        host = host or await _ha_address(hass)
        if host:
            return "http://%s:%d" % (host, GO2RTC_PORT)
    return ""


def offer_setup(status: dict | None) -> bool:
    """Offer the setup step after adding: the player can be set up and says it was never set up."""
    return bool(status) and "setup" in (status.get("capabilities") or []) and status.get("configured") is False


async def send(api, server: str, camera: str | None) -> dict:
    """{} when sent, else form errors: invalid_server, already_set_up, forbidden, cannot_connect."""
    try:
        await api.setup(server.strip(), (camera or "").strip() or None)
    except CamAlertAlreadySetUp:
        return {CONF_GO2RTC: "already_set_up"}
    except CamAlertForbidden:
        return {"base": "forbidden"}
    except CamAlertError as err:
        if "camera" in str(err):
            return {CONF_CAMERA: "invalid_camera"}
        if "invalid" in str(err):
            return {CONF_GO2RTC: "invalid_server"}
        return {"base": "cannot_connect"}
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Unexpected error while setting up a CamAlert player")
        return {"base": "unknown"}
    return {}
