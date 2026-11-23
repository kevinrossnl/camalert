"""CamAlert: show IP cameras on Enigma2 receivers that run the CamAlert plugin."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, Platform  # noqa: F401
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_extract_config_entry_ids

from .api import CamAlertApi, CamAlertError
from .const import CONF_HTTPS, CONF_TOKEN, CONF_VERIFY_SSL, DEFAULT_PORT, DOMAIN, MODES, PRIORITIES
from .coordinator import CamAlertCoordinator

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Target is optional: without a target the action goes to every loaded receiver.
TARGET = dict(getattr(cv, "TARGET_SERVICE_FIELDS", {})) or {
    vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("entity_id"): cv.comp_entity_ids,
    vol.Optional("area_id"): vol.All(cv.ensure_list, [cv.string]),
}

SHOW_SCHEMA = vol.Schema({
    **TARGET,
    vol.Optional("camera"): cv.string,
    vol.Optional("seconds"): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
    vol.Optional("mode"): vol.In(MODES),
    vol.Optional("priority"): vol.In(PRIORITIES),
})
MOSAIC_SCHEMA = vol.Schema({
    **TARGET,
    vol.Optional("cameras"): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("seconds"): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
})
HIDE_SCHEMA = vol.Schema(dict(TARGET))


async def async_setup(hass: HomeAssistant, config) -> bool:
    async def targets(call: ServiceCall):
        try:  # Home Assistant 2025.x and newer: only the service call
            ids = await async_extract_config_entry_ids(call)
        except TypeError:  # older versions: (hass, call)
            ids = await async_extract_config_entry_ids(hass, call)
        selected = [e for e in hass.config_entries.async_entries(DOMAIN) if not ids or e.entry_id in ids]
        if not selected:
            raise HomeAssistantError("No CamAlert receiver selected")
        loaded = [e for e in selected if e.state is ConfigEntryState.LOADED]
        if not loaded:
            raise HomeAssistantError("CamAlert receiver not reachable (off or restarting): %s"
                                     % ", ".join(e.title for e in selected))
        return loaded

    async def run(call: ServiceCall, func):
        errors = []
        for entry in await targets(call):
            try:
                answer = await func(entry.runtime_data.api)
                await entry.runtime_data.async_refresh()
            except CamAlertError as err:
                errors.append("%s: %s" % (entry.title, err))
                continue
            if isinstance(answer, dict) and answer.get("action") == "error":
                errors.append("%s: unknown camera or no camera source configured" % entry.title)
        if errors:
            raise HomeAssistantError("; ".join(errors))

    async def show(call: ServiceCall):
        await run(call, lambda api: api.show(call.data.get("camera"), call.data.get("seconds"), call.data.get("mode"),
                                             call.data.get("priority")))

    async def mosaic(call: ServiceCall):
        await run(call, lambda api: api.mosaic(call.data.get("cameras"), call.data.get("seconds")))

    async def hide(call: ServiceCall):
        await run(call, lambda api: api.hide())

    hass.services.async_register(DOMAIN, "show", show, schema=SHOW_SCHEMA)
    hass.services.async_register(DOMAIN, "mosaic", mosaic, schema=MOSAIC_SCHEMA)
    hass.services.async_register(DOMAIN, "hide", hide, schema=HIDE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    d = entry.data
    api = CamAlertApi(async_get_clientsession(hass, verify_ssl=False), d[CONF_HOST], d.get(CONF_PORT, DEFAULT_PORT),
                     d.get(CONF_HTTPS, False), d.get(CONF_VERIFY_SSL, False), d.get(CONF_TOKEN, ""))
    coordinator = CamAlertCoordinator(hass, api, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:  # receiver off or unreachable: retry later
        raise ConfigEntryNotReady(str(err)) from err
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
