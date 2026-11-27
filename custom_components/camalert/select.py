"""Selects: window position and size of the player (#84), for players that can change them over the API."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory

from .const import WINDOW_SETTINGS
from .entity import CamAlertEntity


async def async_setup_entry(hass, entry, async_add_entities):
    # Only players that say so: an older player has no settings route, so no selects (never assume here).
    if "settings" in (entry.runtime_data.api.capabilities or []):
        async_add_entities(WindowSelect(entry.runtime_data, entry, key) for key in WINDOW_SETTINGS)


class WindowSelect(CamAlertEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry, key: str):
        super().__init__(coordinator, entry, "window_%s" % key)
        self._key = key
        self._attr_translation_key = "window_%s" % key
        self._attr_options = list(WINDOW_SETTINGS[key])

    @property
    def current_option(self):
        value = (self.coordinator.data or {}).get(self._key)
        return value if value in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        await self._call(self.coordinator.api.settings(**{self._key: option}))
