"""Switches: do not disturb on the player (blocks normal requests; high and alarm still come through) and guest mode
(#11: hides the player's guest cameras, for players that support it)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .entity import CamAlertEntity


async def async_setup_entry(hass, entry, async_add_entities):
    entities = []
    if entry.runtime_data.api.supports("dnd"):
        entities.append(DndSwitch(entry.runtime_data, entry))
    if "guest" in (entry.runtime_data.api.capabilities or []):  # never assume it on an older player
        entities.append(GuestSwitch(entry.runtime_data, entry))
    async_add_entities(entities)


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


class GuestSwitch(CamAlertEntity, SwitchEntity):
    """Guest mode (#11): the player hides its guest cameras (all cameras when none are chosen on the player)."""
    _attr_translation_key = "guest_mode"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "guest_mode")

    @property
    def is_on(self):
        return bool((self.coordinator.data or {}).get("guest_mode"))

    async def async_turn_on(self, **kwargs):
        await self._call(self.coordinator.api.settings(guest_mode="1"))

    async def async_turn_off(self, **kwargs):
        await self._call(self.coordinator.api.settings(guest_mode="0"))
