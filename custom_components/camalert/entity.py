"""Base entity: one device per player (Enigma2 receiver, Kodi or Android TV); the model comes from /status platform."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CamAlertError
from .const import DOMAIN


class CamAlertEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key: str):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = "%s_%s" % (entry.unique_id or entry.entry_id, key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title, manufacturer="CamAlert", model=coordinator.api.model,
            sw_version=(coordinator.data or {}).get("version"),
            configuration_url=coordinator.api.configuration_url)

    async def _call(self, coro, refresh: bool = True):
        """Run an API call for a button or switch; errors are shown in the UI (never silent)."""
        from . import _error
        try:
            answer = await coro
        except CamAlertError as err:
            raise _error("request_failed", name=self._entry.title, error=err) from err
        if refresh:
            await self.coordinator.async_request_refresh()
        return answer
