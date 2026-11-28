"""Spoken announcement (#89): Home Assistant turns the text into speech and the players play it.

The text goes to a TTS engine of Home Assistant (the `tts` entity given, else the first one), as a WAV file
(`preferred_format`), because the receivers and Kodi can only play WAV next to the TV sound. The players get an
address they may fetch: only the local network, and without DNS (an IP address or a `.local` name), so the
address uses Home Assistant's LAN IP when its internal URL is a host name.
"""
from __future__ import annotations

import ipaddress
import logging
from urllib.parse import urlsplit, urlunsplit

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
OPTIONS = {"preferred_format": "wav"}


def _plain_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return host.endswith(".local") or "." not in host


async def _base_url(hass: HomeAssistant) -> str:
    """Home Assistant's own address in the local network, with an IP address unless it is a local name."""
    from homeassistant.components.network import async_get_source_ip
    from homeassistant.helpers.network import get_url

    url = get_url(hass, allow_external=False, allow_cloud=False, prefer_external=False)
    p = urlsplit(url)
    if p.hostname and _plain_host(p.hostname):
        return url.rstrip("/")
    ip = await async_get_source_ip(hass)
    netloc = ip + (":%d" % p.port if p.port else "")
    return urlunsplit((p.scheme, netloc, "", "", "")).rstrip("/")


def tts_engine(hass: HomeAssistant, entity_id: str | None) -> str | None:
    if entity_id:
        return entity_id
    ids = sorted(hass.states.async_entity_ids("tts"))
    return ids[0] if ids else None


async def async_say_url(hass: HomeAssistant, text: str, entity_id: str | None = None,
                        language: str | None = None) -> str | None:
    """Absolute WAV address of `text` spoken by a TTS engine, or None (no engine, or TTS failed: then the players
    only get the text; the Android TV app can speak it itself)."""
    engine = tts_engine(hass, entity_id)
    if not engine or not text:
        return None
    try:
        from homeassistant.components import media_source
        from homeassistant.components.tts.media_source import generate_media_source_id

        media_id = generate_media_source_id(hass, text, engine, language, dict(OPTIONS), None)
        media = await media_source.async_resolve_media(hass, media_id, None)
        path = media.url
        if path.startswith(("http://", "https://")):
            return path
        return await _base_url(hass) + path
    except Exception as e:  # noqa: BLE001 - engine missing, language or format not supported, no network
        _LOGGER.warning("Spoken announcement: %s could not make speech: %s", engine, e)
        return None
