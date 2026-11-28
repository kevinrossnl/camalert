"""Buttons of the phone notifications sent by the CamAlert blueprints (#128). The Companion app fires
mobile_app_notification_action with the button's action id; the integration handles the CamAlert ones:

    CAMALERT_SHOW|<camera[,camera]>|<device_id[,device_id]>   show the camera(s) on those players (priority high)
    CAMALERT_DND|<minutes>|<device_id[,device_id]>            Do not disturb on those players for <minutes>
"""
from __future__ import annotations

import logging

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from .api import CamAlertError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
EVENT_ACTION = "mobile_app_notification_action"
PREFIX = "CAMALERT_"
MAX_DND_MINUTES = 24 * 60


def parse(action) -> tuple[str, str, list[str]] | None:
    """(kind, value, device ids) of a CamAlert action id, or None for another app's action."""
    if not isinstance(action, str) or not action.startswith(PREFIX):
        return None
    parts = action[len(PREFIX):].split("|")
    if len(parts) != 3 or parts[0] not in ("SHOW", "DND"):
        return None
    devices = [d for d in parts[2].split(",") if d.strip()]
    if not devices or not parts[1].strip():
        return None
    return parts[0], parts[1].strip(), [d.strip() for d in devices]


def _entries(hass: HomeAssistant, device_ids: list[str]):
    from homeassistant.helpers import device_registry as dr
    reg = dr.async_get(hass)
    out = []
    for dev_id in device_ids:
        dev = reg.async_get(dev_id)
        for entry_id in (dev.config_entries if dev else ()):
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is not None and entry.domain == DOMAIN and getattr(entry, "runtime_data", None) is not None \
                    and entry not in out:
                out.append(entry)
    return out


@callback
def async_setup_phone_actions(hass: HomeAssistant):
    """Listens for the buttons; returns the unsubscribe function."""
    timers: dict[str, object] = {}

    async def act(kind: str, value: str, entry) -> None:
        api = entry.runtime_data.api
        try:
            if kind == "SHOW":
                cams = [c.strip() for c in value.split(",") if c.strip()]
                await api.show(cams if len(cams) > 1 else cams[0], None, None, "high", None)
            else:
                minutes = max(1, min(MAX_DND_MINUTES, int(value)))
                await api.dnd(True)
                cancel = timers.pop(entry.entry_id, None)
                if cancel:
                    cancel()

                async def off(_now, entry=entry):
                    timers.pop(entry.entry_id, None)
                    try:
                        await entry.runtime_data.api.dnd(False)
                        await entry.runtime_data.async_request_refresh()
                    except (CamAlertError, AttributeError) as err:
                        _LOGGER.warning("%s: Do not disturb could not be turned off: %s", entry.title, err)
                timers[entry.entry_id] = async_call_later(hass, minutes * 60, off)
        except (CamAlertError, ValueError) as err:
            _LOGGER.warning("%s: phone button %s failed: %s", entry.title, kind, err)
            return
        await entry.runtime_data.async_request_refresh()

    @callback
    def handle(event: Event) -> None:
        parsed = parse(event.data.get("action"))
        if parsed is None:
            return
        kind, value, devices = parsed
        for entry in _entries(hass, devices):
            hass.async_create_task(act(kind, value, entry), "camalert phone %s" % kind)

    unsub = hass.bus.async_listen(EVENT_ACTION, handle)

    @callback
    def stop() -> None:
        unsub()
        for cancel in list(timers.values()):
            cancel()
        timers.clear()
    return stop
