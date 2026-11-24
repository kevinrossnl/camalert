"""Event entity: colour key pressed on the remote while a camera was on screen (selectable in automations)."""
from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import BUTTONS, SIGNAL_BUTTON
from .entity import CamAlertEntity


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.runtime_data.api.supports("webhook"):  # colour keys reach Home Assistant through the webhook
        async_add_entities([ButtonEvent(entry.runtime_data, entry)])


class ButtonEvent(CamAlertEntity, EventEntity):
    _attr_translation_key = "remote_button"
    _attr_event_types = BUTTONS

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "remote_button")

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_BUTTON % self._entry.entry_id, self._pressed))

    @callback
    def _pressed(self, button, camera):
        self._trigger_event(button, {"camera": camera})
        self.async_write_ha_state()
