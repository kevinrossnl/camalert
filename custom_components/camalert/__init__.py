"""CamAlert: show IP cameras on the TV of players (Enigma2 receivers, Kodi and Android TV) that run CamAlert."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, Platform  # noqa: F401
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_extract_config_entry_ids

from .api import CamAlertApi, CamAlertError, CamAlertNotSupported
from .const import (BUTTONS, CONF_HTTPS, CONF_TOKEN, CONF_VERIFY_SSL, DEFAULT_PORT, DOMAIN, EVENT_BUTTON, MODES,
                    PRIORITIES, PTZ_MOVES, SIGNAL_BUTTON)
from .coordinator import CamAlertCoordinator
from .doorbell import Doorbell
from .parent import link_parent
from .phone import async_setup_phone_actions

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH, Platform.EVENT, Platform.NOTIFY, Platform.UPDATE,
             Platform.SELECT]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Target is optional: without a target the action goes to every loaded player.
TARGET = dict(getattr(cv, "TARGET_SERVICE_FIELDS", {})) or {
    vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("entity_id"): cv.comp_entity_ids,
    vol.Optional("area_id"): vol.All(cv.ensure_list, [cv.string]),
}

SHOW_SCHEMA = vol.Schema({
    **TARGET,
    # a list first: cv.string would turn a template's list result back into its text "['a', 'b']"
    vol.Optional("camera"): vol.Any(vol.All(list, [cv.string]), cv.string),
    # 0 = until hide (#81): the player keeps the window until camalert.hide, at most 10 minutes
    vol.Optional("seconds"): vol.All(vol.Coerce(int), vol.Any(0, vol.Range(min=5, max=300))),
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


def _error(key: str, **placeholders) -> HomeAssistantError:
    """A translated error for the UI (strings.json > exceptions); the English text is also the message."""
    return HomeAssistantError(EXCEPTIONS[key].format(**placeholders), translation_domain=DOMAIN, translation_key=key,
                              translation_placeholders={k: str(v) for k, v in placeholders.items()})


# = strings.json > exceptions (English; tests/homeassistant checks they are the same)
EXCEPTIONS = {
    "no_player": "No CamAlert player selected.",
    "not_loaded": "CamAlert player not reachable (off or restarting): {names}",
    "not_supported": "{name}: {action} is not supported by this player.",
    "request_failed": "{name}: {error}",
    "unknown_camera": "{name}: unknown camera or no camera source configured.",
    "several_failed": "Several players failed: {errors}",
}


def make_api(hass: HomeAssistant, data) -> CamAlertApi:
    """API client for a config entry (or the config flow's input). The certificate check needs the verifying
    session: a request option cannot turn verification back on in a session made without it."""
    https, verify = bool(data.get(CONF_HTTPS, False)), bool(data.get(CONF_VERIFY_SSL, False))
    return CamAlertApi(async_get_clientsession(hass, verify_ssl=https and verify), data[CONF_HOST],
                       data.get(CONF_PORT, DEFAULT_PORT), https, verify, data.get(CONF_TOKEN, ""))


async def async_setup(hass: HomeAssistant, config) -> bool:
    async def targets(call: ServiceCall):
        try:  # Home Assistant 2025.x and newer: only the service call
            ids = await async_extract_config_entry_ids(call)
        except TypeError:  # older versions: (hass, call)
            ids = await async_extract_config_entry_ids(hass, call)
        selected = [e for e in hass.config_entries.async_entries(DOMAIN) if not ids or e.entry_id in ids]
        if not selected:
            raise _error("no_player")
        loaded = [e for e in selected if e.state is ConfigEntryState.LOADED]
        if not loaded:
            raise _error("not_loaded", names=", ".join(e.title for e in selected))
        return loaded

    async def run(call: ServiceCall, func, capability=None):
        """Run the action on every target player; any failure raises (never silent, #4), after trying all."""
        errors = []
        for entry in await targets(call):
            if capability and not entry.runtime_data.api.supports(capability):
                errors.append(_error("not_supported", name=entry.title, action=capability))
                continue
            try:
                answer = await func(entry.runtime_data.api)
            except CamAlertNotSupported:
                errors.append(_error("not_supported", name=entry.title, action=call.service))
                continue
            except CamAlertError as err:
                errors.append(_error("request_failed", name=entry.title, error=err))
                continue
            await entry.runtime_data.async_request_refresh()
            if isinstance(answer, dict) and answer.get("action") == "error":
                errors.append(_error("unknown_camera", name=entry.title))
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise _error("several_failed", errors="; ".join(str(e) for e in errors))

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
    async_setup_phone_actions(hass)  # #128: buttons of the blueprints' phone notifications
    return True


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    api = make_api(hass, entry.data)
    coordinator = CamAlertCoordinator(hass, api, entry)
    await coordinator.async_config_entry_first_refresh()  # player off or unreachable: ConfigEntryNotReady, retried
    entry.runtime_data = coordinator
    if api.integration_too_old():
        _LOGGER.warning("%s needs CamAlert integration %s or newer; please update it", entry.title, api.min_ha_version)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    link_parent(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_options_changed))
    coordinator.doorbell = Doorbell(hass, entry)  # #90: doorbell without an automation
    coordinator.doorbell.start()
    entry.async_on_unload(coordinator.doorbell.stop)
    await _register_webhook(hass, entry, api)
    return True


async def _options_changed(hass: HomeAssistant, entry) -> None:
    """Options changed: link the parent device (#86) and watch the chosen doorbell entities (#90), without a
    reload."""
    link_parent(hass, entry)
    doorbell = getattr(getattr(entry, "runtime_data", None), "doorbell", None)
    if doorbell is not None:
        doorbell.start()


def player_device(hass: HomeAssistant, entry):
    """The device of a config entry (Home Assistant 2026.x: by identifier and entry; older: async_get_device)."""
    from homeassistant.helpers import device_registry as dr
    reg = dr.async_get(hass)
    ident = (DOMAIN, entry.unique_id or entry.entry_id)
    by_identifier = getattr(reg, "async_get_device_by_identifier", None)
    if by_identifier is not None:
        return by_identifier(ident, entry.entry_id)
    return reg.async_get_device(identifiers={ident})


def _webhook_id(entry) -> str:
    return "camalert_%s" % entry.entry_id


async def _register_webhook(hass: HomeAssistant, entry, api) -> None:
    """The player posts remote control colour keys to this webhook (only from the local network)."""
    from homeassistant.components import webhook
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    from homeassistant.helpers.network import NoURLAvailableError, get_url

    async def handle(hass, webhook_id, request):
        try:
            data = await request.json()
        except ValueError:
            return None
        button = str(data.get("button") or "")
        camera = str(data.get("camera") or "")
        if button not in BUTTONS:
            return None
        device = player_device(hass, entry)
        # "receiver" is kept for automations written before 1.0 (same value as "player")
        hass.bus.async_fire(EVENT_BUTTON, {"device_id": device.id if device else None, "player": entry.title,
                                          "receiver": entry.title, "camera": camera, "button": button})
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
    except CamAlertError as err:  # older player without /webhook, or HA's url is not in the local network
        _LOGGER.info("%s: colour keys only via MQTT (webhook: %s)", entry.title, err)


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    from homeassistant.components import webhook
    webhook.async_unregister(hass, _webhook_id(entry))
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry) -> None:
    """Player removed from Home Assistant: tell it to stop posting buttons."""
    api = make_api(hass, entry.data)
    try:
        await api.webhook("")
    except CamAlertError:
        pass
