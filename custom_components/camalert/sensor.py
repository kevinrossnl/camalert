"""Sensor: which camera is on screen (state "none" = nothing, translated; attribute mode photo / live)."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from .const import NOTHING
from .entity import CamAlertEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([OnScreenSensor(entry.runtime_data, entry)])


class OnScreenSensor(CamAlertEntity, SensorEntity):
    """An enum: "none" or a camera name. Camera names are the player's, only "none" is translated."""
    _attr_translation_key = "on_screen"
    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "on_screen")

    @property
    def native_value(self):
        d = self.coordinator.data or {}
        return d.get("window") or d.get("live") or NOTHING

    @property
    def options(self):
        names = [NOTHING] + [c["name"] for c in self.coordinator.cameras if c.get("name") != NOTHING]
        value = self.native_value
        return names if value in names else names + [value]  # e.g. a mosaic stream that is not in the list

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        return {"mode": "photo" if d.get("window") else "live" if d.get("live") else None,
                "paused": d.get("paused"), "cameras": [c["name"] for c in self.coordinator.cameras]}
