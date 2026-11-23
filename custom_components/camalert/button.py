"""Buttons: show a camera, mosaic, hide."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity

from .entity import CamAlertEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known: set[str] = set()

    def add_new():
        new = []
        for cam in coordinator.cameras:
            if cam["name"] not in known:
                known.add(cam["name"])
                new.append(ShowButton(coordinator, entry, cam))
        if new:
            async_add_entities(new)

    async_add_entities([MosaicButton(coordinator, entry), HideButton(coordinator, entry)])
    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class ShowButton(CamAlertEntity, ButtonEntity):
    _attr_translation_key = "show"
    _attr_icon = "mdi:cctv"

    def __init__(self, coordinator, entry, cam):
        super().__init__(coordinator, entry, "show_" + cam["name"])
        self._cam = cam["name"]
        self._attr_translation_placeholders = {"camera": cam.get("title") or cam["name"]}

    async def async_press(self) -> None:
        await self.coordinator.api.show(self._cam)
        await self.coordinator.async_request_refresh()


class MosaicButton(CamAlertEntity, ButtonEntity):
    _attr_translation_key = "mosaic"
    _attr_icon = "mdi:view-grid"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "mosaic")

    async def async_press(self) -> None:
        await self.coordinator.api.mosaic()


class HideButton(CamAlertEntity, ButtonEntity):
    _attr_translation_key = "hide"
    _attr_icon = "mdi:close-box-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "hide")

    async def async_press(self) -> None:
        await self.coordinator.api.hide()
        await self.coordinator.async_request_refresh()
