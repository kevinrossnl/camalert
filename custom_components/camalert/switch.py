"""Switch: do not disturb on the player (blocks normal requests; high and alarm still come through)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .entity import CamAlertEntity


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.runtime_data.api.supports("dnd"):
        async_add_entities([DndSwitch(entry.runtime_data, entry)])


class DndSwitch(CamAlertEntity, SwitchEntity):
    _attr_translation_key = "dnd"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "dnd")

    @property
    def is_on(self):
        return bool((self.coordinator.data or {}).get("dnd"))

    async def async_turn_on(self, **kwargs):
        await self._call(self.coordinator.api.dnd(True))

    async def async_turn_off(self, **kwargs):
        await self._call(self.coordinator.api.dnd(False))
