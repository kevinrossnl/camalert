"""CamAlert: show IP cameras on Enigma2 receivers and Kodi players that run CamAlert."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, Platform  # noqa: F401
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_extract_config_entry_ids

from .api import CamAlertApi, CamAlertError
from .const import (CONF_HTTPS, CONF_TOKEN, CONF_VERIFY_SSL, DEFAULT_PORT, DOMAIN, EVENT_BUTTON, MODES, PRIORITIES,
                    PTZ_MOVES, SIGNAL_BUTTON)
from .coordinator import CamAlertCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH, Platform.EVENT]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Target is optional: without a target the action goes to every loaded receiver.
TARGET = dict(getattr(cv, "TARGET_SERVICE_FIELDS", {})) or {
    vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("entity_id"): cv.comp_entity_ids,
    vol.Optional("area_id"): vol.All(cv.ensure_list, [cv.string]),
}

SHOW_SCHEMA = vol.Schema({
    **TARGET,
    vol.Optional("camera"): vol.Any(cv.string, vol.All(cv.ensure_list, [cv.string])),
    vol.Optional("seconds"): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
    vol.Optional("mode"): vol.In(MODES),
    vol.Optional("priority"): vol.In(PRIORITIES),
    vol.Optional("label"): cv.string,
})
PTZ_SCHEMA = vol.Schema({
    **TARGET,
    vol.Required("camera"): cv.string,
    vol.Required("move"): vol.In(PTZ_MOVES),
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

    async def run(call: ServiceCall, func, capability=None):
        errors = []
        for entry in await targets(call):
            if capability and not entry.runtime_data.api.supports(capability):
                errors.append("%s: %s is not supported by this player" % (entry.title, capability))
                continue
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
                                             call.data.get("priority"), call.data.get("label")))

    async def ptz(call: ServiceCall):
        await run(call, lambda api: api.ptz(call.data["camera"], call.data["move"]), "ptz")

    async def mosaic(call: ServiceCall):
        await run(call, lambda api: api.mosaic(call.data.get("cameras"), call.data.get("seconds")), "mosaic")

    async def hide(call: ServiceCall):
        await run(call, lambda api: api.hide())

    hass.services.async_register(DOMAIN, "show", show, schema=SHOW_SCHEMA)
    hass.services.async_register(DOMAIN, "mosaic", mosaic, schema=MOSAIC_SCHEMA)
    hass.services.async_register(DOMAIN, "hide", hide, schema=HIDE_SCHEMA)
    hass.services.async_register(DOMAIN, "ptz", ptz, schema=PTZ_SCHEMA)
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
    if api.integration_too_old():
        _LOGGER.warning("%s needs CamAlert integration %s or newer; please update it", entry.title, api.min_ha_version)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _register_webhook(hass, entry, api)
    return True


def _webhook_id(entry) -> str:
    return "camalert_%s" % entry.entry_id


async def _register_webhook(hass: HomeAssistant, entry, api) -> None:
    """The receiver posts remote control colour keys to this webhook (only from the local network)."""
    from homeassistant.components import webhook
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    from homeassistant.helpers.network import NoURLAvailableError, get_url

    async def handle(hass, webhook_id, request):
        try:
            data = await request.json()
        except ValueError:
            return None
        button = str(data.get("button") or "")
        camera = str(data.get("camera") or "")
        if button not in ("red", "green", "yellow", "blue"):
            return None
        device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.unique_id or entry.entry_id)})
        hass.bus.async_fire(EVENT_BUTTON, {"device_id": device.id if device else None, "receiver": entry.title,
                                          "camera": camera, "button": button})
        async_dispatcher_send(hass, SIGNAL_BUTTON % entry.entry_id, button, camera)
        return None

    wid = _webhook_id(entry)
    try:
        webhook.async_register(hass, DOMAIN, "CamAlert %s" % entry.title, wid, handle, local_only=True,
                               allowed_methods=["POST"])
    except ValueError:  # already registered (reload)
        pass
    try:
        url = get_url(hass, allow_external=False, prefer_external=False) + webhook.async_generate_path(wid)
    except NoURLAvailableError:
        return
    if not api.supports("webhook"):
        return
    try:
        await api.webhook(url)
    except CamAlertError as err:  # older plugin without /webhook, or HA's url is not in the local network
        _LOGGER.info("%s: colour keys only via MQTT (webhook: %s)", entry.title, err)


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    from homeassistant.components import webhook
    webhook.async_unregister(hass, _webhook_id(entry))
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry) -> None:
    """Receiver removed from Home Assistant: tell it to stop posting buttons."""
    d = entry.data
    api = CamAlertApi(async_get_clientsession(hass, verify_ssl=False), d[CONF_HOST], d.get(CONF_PORT, DEFAULT_PORT),
                     d.get(CONF_HTTPS, False), d.get(CONF_VERIFY_SSL, False), d.get(CONF_TOKEN, ""))
    try:
        await api.webhook("")
    except CamAlertError:
        pass
