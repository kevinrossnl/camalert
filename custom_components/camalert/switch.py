"""Switch: do not disturb on the receiver (blocks normal requests; doorbell/alarm still come through)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .api import CamAlertError
from .entity import CamAlertEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([DndSwitch(entry.runtime_data, entry)])


class DndSwitch(CamAlertEntity, SwitchEntity):
    _attr_translation_key = "dnd"
    _attr_icon = "mdi:bell-off"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "dnd")

    @property
    def is_on(self):
        return bool((self.coordinator.data or {}).get("dnd"))

    async def _set(self, on: bool):
        from homeassistant.exceptions import HomeAssistantError
        try:
            await self.coordinator.api.dnd(on)
        except CamAlertError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs):
        await self._set(True)

    async def async_turn_off(self, **kwargs):
        await self._set(False)
