"""Update entity per player (#83): the CamAlert version on the player against the latest release on GitHub. It only
reports an update, with a link to the release notes; installing stays on the player (its own updater, Kodi
repository or the Android TV app)."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .entity import CamAlertEntity

_LOGGER = logging.getLogger(__name__)

RELEASE_URL = "https://api.github.com/repos/kevinrossnl/camalert/releases/latest"
CACHE_SECONDS = 6 * 3600  # GitHub allows 60 requests per hour without a token; one per 6 hours for all players
RETRY_SECONDS = 3600  # after an error (no internet, rate limit)
CHECK_INTERVAL = timedelta(hours=1)  # how often the entities look at the cache
TIMEOUT = 10


class ReleaseCache:
    """The latest GitHub release, shared by every player; fetched without a token, at most once per 6 hours."""

    def __init__(self, hass):
        self.hass = hass
        self.release: dict | None = None
        self._valid_until = 0.0

    async def get(self) -> dict | None:
        if time.monotonic() < self._valid_until:
            return self.release
        import aiohttp  # provided by Home Assistant
        try:
            async with async_get_clientsession(self.hass).get(
                    RELEASE_URL, headers={"Accept": "application/vnd.github+json"},
                    timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
            tag = str(data.get("tag_name") or "").strip()
            if not tag:
                raise ValueError("release without tag")
            self.release = {"version": tag[1:] if tag[:1] in "vV" else tag, "url": data.get("html_url"),
                            "notes": data.get("body") or ""}
            self._valid_until = time.monotonic() + CACHE_SECONDS
        except (aiohttp.ClientError, TimeoutError, ValueError, AttributeError) as err:
            _LOGGER.debug("CamAlert: latest release not available: %s", err)
            self._valid_until = time.monotonic() + RETRY_SECONDS  # keep the last known release
        return self.release


def release_cache(hass) -> ReleaseCache:
    data = hass.data.setdefault(DOMAIN, {})
    if "releases" not in data:
        data["releases"] = ReleaseCache(hass)
    return data["releases"]


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([CamAlertUpdate(entry.runtime_data, entry, release_cache(hass))])


class CamAlertUpdate(CamAlertEntity, UpdateEntity):
    _attr_translation_key = "camalert"
    _attr_title = "CamAlert"
    _attr_supported_features = UpdateEntityFeature.RELEASE_NOTES  # never INSTALL: only reported

    def __init__(self, coordinator, entry, cache: ReleaseCache):
        super().__init__(coordinator, entry, "update")
        self._cache = cache

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_track_time_interval(self.hass, self._check, CHECK_INTERVAL))
        await self._check()

    async def _check(self, _now=None) -> None:
        await self._cache.get()
        self.async_write_ha_state()

    @property
    def installed_version(self) -> str | None:
        return (self.coordinator.data or {}).get("version")

    @property
    def latest_version(self) -> str | None:
        return (self._cache.release or {}).get("version")  # None until GitHub answered once: state unknown

    @property
    def release_url(self) -> str | None:
        return (self._cache.release or {}).get("url")

    async def async_release_notes(self) -> str | None:
        return (self._cache.release or {}).get("notes")
