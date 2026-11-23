"""Download diagnostics: status, events and the receiver's camalert.log (all redacted)."""
from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data

from .api import CamAlertError
from .const import CONF_TOKEN

TO_REDACT = {CONF_TOKEN, "password", "token", "pwd"}


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    out = {"entry": async_redact_data(dict(entry.data), TO_REDACT), "status": coordinator.data,
           "cameras": coordinator.cameras}
    try:
        out["events"] = await coordinator.api.events()
        out["log"] = await coordinator.api.log(500)  # already redacted on the receiver
    except CamAlertError as err:
        out["error"] = str(err)
    return out
