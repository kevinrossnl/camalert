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

SHOW_SCHEMA = cv.make_entity_service_schema({
    vol.Optional("camera"): cv.string,
    vol.Optional("seconds"): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
    vol.Optional("mode"): vol.In(MODES),
    vol.Optional("priority"): vol.In(PRIORITIES),
})
MOSAIC_SCHEMA = cv.make_entity_service_schema({
    vol.Optional("cameras"): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("seconds"): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
})
HIDE_SCHEMA = cv.make_entity_service_schema({})


async def async_setup(hass: HomeAssistant, config) -> bool:
    async def targets(call: ServiceCall):
        ids = await async_extract_config_entry_ids(hass, call)
        entries = [e for e in hass.config_entries.async_entries(DOMAIN)
                   if e.state is ConfigEntryState.LOADED and (not ids or e.entry_id in ids)]
        if not entries:
            raise HomeAssistantError("No CamAlert receiver selected")
        return entries

    async def run(call: ServiceCall, func):
        errors = []
        for entry in await targets(call):
            try:
                await func(entry.runtime_data.api)
                await entry.runtime_data.async_request_refresh()
            except CamAlertError as err:
                errors.append("%s: %s" % (entry.title, err))
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
