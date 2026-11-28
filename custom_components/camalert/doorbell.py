"""Doorbell without an automation (#90): the integration itself watches the doorbell entities chosen in a player's
options and shows the camera on that player, with priority high. Blueprints stay for custom rules."""
from __future__ import annotations

import logging
import time

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .api import CamAlertError

_LOGGER = logging.getLogger(__name__)
CONF_DOORBELL = "doorbell"
CONF_DOORBELL_CAMERA = "doorbell_camera"
# event_type values of event entities that mean "someone rang" (Reolink, UniFi Protect, Ring, Aqara, buttons)
RING_TYPES = {"ring", "doorbell", "pressed", "press", "single", "button_pressed", "initial_press"}
COOLDOWN_SECONDS = 15.0
LABEL = "Doorbell"
GONE = ("unavailable", "unknown")


def is_ring(old, new) -> bool:
    """True when a state change of a doorbell entity is a ring. Never for the first state after a restart or an
    entity that comes back (old None or unavailable); an event entity may go from unknown (never fired) to a
    ring."""
    if new is None or old is None or new.state in GONE or old.state == "unavailable":
        return False
    if new.domain == "event":
        if new.state == old.state:
            return False
        kind = str(new.attributes.get("event_type") or "").lower()
        return kind in RING_TYPES or new.attributes.get("device_class") == "doorbell"
    if new.domain == "binary_sensor":
        return old.state == "off" and new.state == "on"
    return False


class Doorbell:
    """The doorbell watcher of one player (config entry)."""

    def __init__(self, hass: HomeAssistant, entry, clock=time.monotonic):
        self.hass, self.entry, self.clock = hass, entry, clock
        self.last = None
        self._unsub = None

    def entities(self) -> list[str]:
        value = self.entry.options.get(CONF_DOORBELL) or []
        return [value] if isinstance(value, str) else list(value)

    @callback
    def start(self) -> None:
        self.stop()
        ents = self.entities()
        if ents:
            self._unsub = async_track_state_change_event(self.hass, ents, self._changed)

    @callback
    def stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @callback
    def _changed(self, event: Event) -> None:
        if not is_ring(event.data.get("old_state"), event.data.get("new_state")):
            return
        now = self.clock()
        if self.last is not None and now - self.last < COOLDOWN_SECONDS:
            return  # press and release, or two entities of one doorbell: one window
        self.last = now
        self.hass.async_create_task(self._show(), "camalert doorbell %s" % self.entry.title)

    async def _show(self) -> None:
        camera = (self.entry.options.get(CONF_DOORBELL_CAMERA) or "").strip() or None
        coordinator = getattr(self.entry, "runtime_data", None)
        if coordinator is None:
            return
        try:
            await coordinator.api.show(camera, None, None, "high", LABEL)
        except CamAlertError as err:
            _LOGGER.warning("%s: doorbell could not be shown: %s", self.entry.title, err)
            return
        await coordinator.async_request_refresh()
