"""Download diagnostics: player (platform, model, version, API), status, events and the player's camalert.log;
address, token and player id are redacted."""
from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST

from .api import INTEGRATION_VERSION, CamAlertError
from .const import CONF_TOKEN

TO_REDACT = {CONF_TOKEN, CONF_HOST, "password", "token", "pwd", "id", "unique_id", "ha_webhook", "ha_webhook_secret", "secret", "webhook", "snapshot", "url"}


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    api = coordinator.api
    out = {"entry": async_redact_data({"data": dict(entry.data), "title": entry.title,
                                       "unique_id": entry.unique_id}, TO_REDACT),
           "integration_version": INTEGRATION_VERSION,
           "player": {"platform": api.platform, "model": api.model, "version": (coordinator.data or {}).get("version"),
                      "api_version": api.api_version, "capabilities": api.capabilities,
                      "min_ha_version": api.min_ha_version, "integration_too_old": api.integration_too_old()},
           "status": async_redact_data(dict(coordinator.data or {}), TO_REDACT), "cameras": async_redact_data(coordinator.cameras, TO_REDACT)}
    try:
        out["events"] = await api.events()
        out["log"] = await api.log(500)  # already redacted on the player
    except CamAlertError as err:
        out["error"] = str(err)
    return out
