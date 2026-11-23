"""Base entity: one device per receiver."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class CamAlertEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key: str):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = "%s_%s" % (entry.unique_id or entry.entry_id, key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title, manufacturer="CamAlert", model="Enigma2 receiver",
            sw_version=(coordinator.data or {}).get("version"),
            configuration_url="%s://%s" % ("https" if coordinator.api.https else "http", coordinator.api.host))
