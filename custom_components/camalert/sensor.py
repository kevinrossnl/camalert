"""Sensor: which camera is on screen."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity

from .entity import CamAlertEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([OnScreenSensor(entry.runtime_data, entry)])


class OnScreenSensor(CamAlertEntity, SensorEntity):
    _attr_translation_key = "on_screen"
    _attr_icon = "mdi:television"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "on_screen")

    @property
    def native_value(self):
        d = self.coordinator.data or {}
        return d.get("window") or d.get("live") or "none"

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        return {"mode": "photo" if d.get("window") else "live" if d.get("live") else None,
                "paused": d.get("paused"), "cameras": [c["name"] for c in self.coordinator.cameras]}
