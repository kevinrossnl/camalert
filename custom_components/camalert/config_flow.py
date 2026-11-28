"""Add a player (Enigma2 receiver, Kodi or Android TV with CamAlert) from the Home Assistant UI; change its address later
with "Reconfigure". Players announce themselves as _camalert._tcp (#121): Home Assistant shows them as discovered,
adding one is a confirmation (and the token, only when the player asks for one), and a known player that comes back
on another address gets the new address."""
from __future__ import annotations

import logging
import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (EntitySelector, EntitySelectorConfig, SelectSelector, SelectSelectorConfig,
                                            SelectSelectorMode, TimeSelector)

from .api import CamAlertCertificateError, CamAlertError, CamAlertForbidden
from .const import CONF_HTTPS, CONF_TOKEN, CONF_VERIFY_SSL, DEFAULT_PORT, DEFAULT_VERIFY_SSL, DOMAIN
from .doorbell import CONF_DOORBELL, CONF_DOORBELL_CAMERA
from .go2rtc_setup import CONF_CAMERA, CONF_GO2RTC, offer_setup, send, suggested_go2rtc
from .parent import CONF_PARENT, PARENT_AUTO, PARENT_NONE, parent_choices

_LOGGER = logging.getLogger(__name__)
_CAMERA = re.compile(r"^[A-Za-z0-9_.-]+$")  # one go2rtc name (#90)
TXT_ID, TXT_NAME, TXT_HTTPS = "id", "name", "https"


def _schema(defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
        vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)),
        vol.Optional(CONF_HTTPS, default=defaults.get(CONF_HTTPS, False)): bool,
        vol.Optional(CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)): bool,
        vol.Optional(CONF_TOKEN, default=defaults.get(CONF_TOKEN, "")): str,
    })


async def _check(hass, data: dict) -> tuple[dict | None, dict]:
    """(status of the player or None, errors for the form)."""
    from . import make_api
    api = make_api(hass, dict({CONF_VERIFY_SSL: DEFAULT_VERIFY_SSL}, **data))
    try:
        return await api.status(), {}
    except CamAlertForbidden:
        return None, {"base": "forbidden"}
    except CamAlertCertificateError:
        return None, {"base": "certificate"}
    except CamAlertError:
        return None, {"base": "cannot_connect"}
    except Exception:  # noqa: BLE001 - shown as "Unexpected error", details in the log
        _LOGGER.exception("Unexpected error while adding a CamAlert player")
        return None, {"base": "unknown"}


def _app_schema(defaults: dict) -> vol.Schema:
    """A TV with an existing notification app (#95): which app, where it is, and the go2rtc it fetches from."""
    from .apps import APPS, CONF_APP, CONF_DEFAULT_CAMERA, CONF_NOTIFY_ENTITY, CONF_SERVER
    return vol.Schema({
        vol.Required(CONF_APP, default=defaults.get(CONF_APP, APPS[0])): SelectSelector(SelectSelectorConfig(
            options=list(APPS), mode=SelectSelectorMode.LIST, translation_key="app")),
        vol.Optional("name", default=defaults.get("name", "")): str,
        vol.Optional(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
        vol.Optional(CONF_PORT, description={"suggested_value": defaults.get(CONF_PORT)}): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)),
        vol.Optional(CONF_NOTIFY_ENTITY, description={"suggested_value": defaults.get(CONF_NOTIFY_ENTITY)}):
            EntitySelector(EntitySelectorConfig(domain="notify", integration="nfandroidtv")),
        vol.Required(CONF_SERVER, default=defaults.get(CONF_SERVER, "")): str,
        vol.Optional(CONF_DEFAULT_CAMERA, default=defaults.get(CONF_DEFAULT_CAMERA, "")): str,
    })


async def _check_app(hass, user_input: dict) -> tuple[dict | None, dict, dict]:
    """(status or None, errors, cleaned entry data) for a notification app (#95)."""
    from .apps import (APP, CONF_APP, CONF_DEFAULT_CAMERA, CONF_NOTIFY_ENTITY, CONF_SERVER, CONF_TYPE,
                       DEFAULT_PORTS, HOST_APPS, normalize_server)
    from .browser import lan_server
    app = user_input.get(CONF_APP)
    data = {CONF_TYPE: APP, CONF_APP: app, "name": (user_input.get("name") or "").strip(),
            CONF_DEFAULT_CAMERA: (user_input.get(CONF_DEFAULT_CAMERA) or "").strip()}
    errors = {}
    if app in HOST_APPS:
        data[CONF_HOST] = (user_input.get(CONF_HOST) or "").strip()
        data[CONF_PORT] = int(user_input.get(CONF_PORT) or DEFAULT_PORTS[app])
        if not data[CONF_HOST]:
            errors[CONF_HOST] = "host_required"
    else:
        data[CONF_NOTIFY_ENTITY] = user_input.get(CONF_NOTIFY_ENTITY) or ""
        if not data[CONF_NOTIFY_ENTITY]:
            errors[CONF_NOTIFY_ENTITY] = "entity_required"
    server = normalize_server(user_input.get(CONF_SERVER))
    if not server or not await lan_server(hass, server):  # the TV fetches from it: only the local network
        errors[CONF_SERVER] = "go2rtc_not_local"
    data[CONF_SERVER] = server
    if data[CONF_DEFAULT_CAMERA] and not _CAMERA.match(data[CONF_DEFAULT_CAMERA]):
        errors[CONF_DEFAULT_CAMERA] = "invalid_camera"
    if errors:
        return None, errors, data
    status, errors = await _check(hass, data)
    if errors.get("base") == "cannot_connect":
        errors = {"base": "app_unreachable"}
    return status, errors, data


def _app_title(data: dict) -> str:
    from .apps import CONF_APP, CONF_NOTIFY_ENTITY
    from .api import MODELS
    where = data.get(CONF_HOST) or data.get(CONF_NOTIFY_ENTITY, "")
    return data.get("name") or "%s %s" % (MODELS.get(data.get(CONF_APP), data.get(CONF_APP)), where)


def _clean(user_input: dict) -> dict:
    return dict(user_input, **{CONF_HOST: user_input[CONF_HOST].strip()})


class CamAlertConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CamAlertOptionsFlow()

    async def async_step_user(self, user_input=None):
        """A CamAlert player, or a TV with an existing notification app (#95)."""
        return self.async_show_menu(step_id="user", menu_options=["player", "app"])

    async def async_step_player(self, user_input=None):
        errors = {}
        if user_input is not None:
            user_input = _clean(user_input)
            status, errors = await _check(self.hass, user_input)
            if status is not None:
                await self.async_set_unique_id(status.get("id") or user_input[CONF_HOST])
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                return await self._create(status.get("name") or "CamAlert %s" % user_input[CONF_HOST], user_input,
                                          status)
        return self.async_show_form(step_id="player", data_schema=_schema(user_input or {}), errors=errors)

    async def async_step_app(self, user_input=None):
        """#95: PiPup, TvOverlay or Home Assistant's Notifications for Android TV / Fire TV as a light player."""
        from .apps import CONF_SERVER, node_id
        errors = {}
        if user_input is not None:
            status, errors, data = await _check_app(self.hass, user_input)
            if status is not None:
                await self.async_set_unique_id(node_id(data))
                self._abort_if_unique_id_configured(updates=data)
                return self.async_create_entry(title=_app_title(data), data=data)
        defaults = dict(user_input or {})
        if user_input is None:
            defaults[CONF_SERVER] = await suggested_go2rtc(self.hass)
        return self.async_show_form(step_id="app", data_schema=_app_schema(defaults), errors=errors)

    async def async_step_zeroconf(self, discovery_info):
        """A player announced itself (#121): TXT id, name, platform, version, api_version, https."""
        props = discovery_info.properties or {}
        node = (props.get(TXT_ID) or "").strip()
        if not node:
            return self.async_abort(reason="not_camalert")
        host, port = str(discovery_info.ip_address), int(discovery_info.port or DEFAULT_PORT)
        await self.async_set_unique_id(node)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
        https = props.get(TXT_HTTPS) == "1"
        # HTTPS on a player means its own self-signed certificate (#66): Reconfigure can turn checking on
        self._discovered = {CONF_HOST: host, CONF_PORT: port, CONF_HTTPS: https,
                            CONF_VERIFY_SSL: False if https else DEFAULT_VERIFY_SSL, CONF_TOKEN: ""}
        self._name = (props.get(TXT_NAME) or "").strip() or discovery_info.name.split(".", 1)[0]
        self._need_token = False
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            data = dict(self._discovered, **{CONF_TOKEN: (user_input.get(CONF_TOKEN) or "").strip()})
            status, errors = await _check(self.hass, data)
            if status is not None:
                if status.get("id") and status["id"] != self.unique_id:
                    return self.async_abort(reason="wrong_player")
                return await self._create(status.get("name") or self._name, data, status)
            if errors.get("base") == "forbidden" and not self._need_token:
                self._need_token = True  # the player has a token: ask for it (no error the first time)
                errors = {}
        schema = vol.Schema({vol.Optional(CONF_TOKEN, default=""): str}) if self._need_token else vol.Schema({})
        return self.async_show_form(step_id="zeroconf_confirm", data_schema=schema, errors=errors,
                                    description_placeholders={"name": self._name,
                                                              "host": self._discovered[CONF_HOST]})

    async def async_step_browser(self, discovery_info):
        """A web page or browser extension connected as a player (#92, #127): offer to add it."""
        from .browser import BROWSER, CONF_BROWSER_ID, CONF_TYPE
        bid = discovery_info[CONF_BROWSER_ID]
        await self.async_set_unique_id(bid)
        self._abort_if_unique_id_configured()
        self._discovered = {CONF_TYPE: BROWSER, CONF_BROWSER_ID: bid}
        self._name = (discovery_info.get("name") or "").strip() or "CamAlert browser %s" % bid[-4:]
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_browser_confirm()

    async def async_step_browser_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            status, errors = await _check(self.hass, self._discovered)
            if status is not None:
                return await self._create(self._name, self._discovered, status)
        return self.async_show_form(step_id="browser_confirm", data_schema=vol.Schema({}), errors=errors,
                                    description_placeholders={"name": self._name})

    async def _create(self, title: str, data: dict, status: dict):
        """Adds the player; first offers to send the go2rtc address when it was never set up (#122)."""
        if not offer_setup(status):
            return self.async_create_entry(title=title, data=data)
        self._pending = (title, data, list(status.get("capabilities") or []))
        return await self.async_step_setup()

    async def async_step_setup(self, user_input=None):
        """#122: send Home Assistant's go2rtc address (and a default camera) to the new player; empty = skip."""
        title, data, capabilities = self._pending
        errors = {}
        if user_input is not None:
            server = (user_input.get(CONF_GO2RTC) or "").strip()
            if not server:
                return self.async_create_entry(title=title, data=data)
            from . import make_api
            api = make_api(self.hass, dict({CONF_VERIFY_SSL: DEFAULT_VERIFY_SSL}, **data))
            api.capabilities = capabilities
            errors = await send(api, server, user_input.get(CONF_CAMERA))
            if not errors:
                return self.async_create_entry(title=title, data=data)
        suggested = user_input if user_input is not None else {CONF_GO2RTC: await suggested_go2rtc(self.hass)}
        schema = self.add_suggested_values_to_schema(vol.Schema({
            vol.Optional(CONF_GO2RTC): str, vol.Optional(CONF_CAMERA): str}), suggested)
        return self.async_show_form(step_id="setup", data_schema=schema, errors=errors,
                                    description_placeholders={"name": title})

    async def async_step_reconfigure(self, user_input=None):
        """New address, port, HTTPS or token for a player that is already added (same player only)."""
        entry = self._get_reconfigure_entry()
        from .browser import is_browser
        if is_browser(entry.data):
            return self.async_abort(reason="browser_player")
        from .apps import is_app
        if is_app(entry.data):  # #95: the app form, for the same TV
            return await self.async_step_reconfigure_app()
        errors = {}
        if user_input is not None:
            user_input = _clean(user_input)
            status, errors = await _check(self.hass, user_input)
            if status is not None:
                await self.async_set_unique_id(status.get("id") or user_input[CONF_HOST])
                self._abort_if_unique_id_mismatch(reason="wrong_player")
                return self.async_update_reload_and_abort(entry, data=user_input)
        return self.async_show_form(step_id="reconfigure", data_schema=_schema(user_input or dict(entry.data)),
                                    errors=errors)


    async def async_step_reconfigure_app(self, user_input=None):
        """#95: another address, port, entity or go2rtc of the same notification app."""
        from .apps import node_id
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            status, errors, data = await _check_app(self.hass, user_input)
            if status is not None:
                if node_id(data) != entry.unique_id:
                    return self.async_abort(reason="wrong_player")
                return self.async_update_reload_and_abort(entry, data=data, title=_app_title(data))
        return self.async_show_form(step_id="reconfigure_app", errors=errors,
                                    data_schema=_app_schema(user_input or dict(entry.data)))


class CamAlertOptionsFlow(config_entries.OptionsFlow):
    """Options: the device the player hangs under (#86): automatic (TV/receiver with the same address), none, or a
    chosen device."""

    async def async_step_init(self, user_input=None):
        errors = {}
        api = getattr(getattr(self.config_entry, "runtime_data", None), "api", None)
        can_setup = api is not None and "setup" in (api.capabilities or [])
        if user_input is not None:
            user_input = dict(user_input)
            server = (user_input.pop(CONF_GO2RTC, "") or "").strip()
            camera = user_input.pop(CONF_CAMERA, "")
            if server and can_setup:  # #122: a player that is set up only takes a local-network address
                errors = await send(api, server, camera)
            # #90: an emptied field is missing from the input: store it empty, not the old value
            user_input.setdefault(CONF_DOORBELL, [])
            from .apps import CONF_ACTIVE_FROM, CONF_ACTIVE_UNTIL, is_app
            if is_app(self.config_entry.data):  # #95: emptied active hours = all day
                for key in (CONF_ACTIVE_FROM, CONF_ACTIVE_UNTIL):
                    user_input.setdefault(key, "")
            user_input[CONF_DOORBELL_CAMERA] = (user_input.get(CONF_DOORBELL_CAMERA) or "").strip()
            if user_input[CONF_DOORBELL_CAMERA] and not _CAMERA.match(user_input[CONF_DOORBELL_CAMERA]):
                errors[CONF_DOORBELL_CAMERA] = "invalid_camera"
            if not errors:
                return self.async_create_entry(data=dict(self.config_entry.options, **user_input))
        current = (user_input or {}).get(CONF_PARENT) or self.config_entry.options.get(CONF_PARENT, PARENT_AUTO)
        options = [{"value": PARENT_AUTO, "label": PARENT_AUTO}, {"value": PARENT_NONE, "label": PARENT_NONE}]
        options += parent_choices(self.hass)
        if current not in [o["value"] for o in options]:  # chosen device removed since
            current = PARENT_AUTO
        fields = {vol.Required(CONF_PARENT, default=current): SelectSelector(SelectSelectorConfig(
            options=options, mode=SelectSelectorMode.DROPDOWN, translation_key=CONF_PARENT))}
        opts = dict(self.config_entry.options, **(user_input or {}))
        fields[vol.Optional(CONF_DOORBELL, description={"suggested_value": opts.get(CONF_DOORBELL) or []})] = \
            EntitySelector(EntitySelectorConfig(domain=["event", "binary_sensor"], multiple=True))
        fields[vol.Optional(CONF_DOORBELL_CAMERA,
                            description={"suggested_value": opts.get(CONF_DOORBELL_CAMERA) or ""})] = str
        from .apps import CONF_ACTIVE_FROM, CONF_ACTIVE_UNTIL, is_app
        if is_app(self.config_entry.data):  # #95: the player's active hours live in Home Assistant
            for key in (CONF_ACTIVE_FROM, CONF_ACTIVE_UNTIL):
                fields[vol.Optional(key, description={"suggested_value": opts.get(key)})] = TimeSelector()
        if can_setup:  # #122: send Home Assistant's go2rtc address to the player (empty = leave it alone)
            fields[vol.Optional(CONF_GO2RTC)] = str
            fields[vol.Optional(CONF_CAMERA)] = str
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields), errors=errors)
