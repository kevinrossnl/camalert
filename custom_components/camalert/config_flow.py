"""Add a player (Enigma2 receiver, Kodi or Android TV with CamAlert) from the Home Assistant UI; change its address later
with "Reconfigure"."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode

from .api import CamAlertCertificateError, CamAlertError, CamAlertForbidden
from .const import CONF_HTTPS, CONF_TOKEN, CONF_VERIFY_SSL, DEFAULT_PORT, DEFAULT_VERIFY_SSL, DOMAIN
from .parent import CONF_PARENT, PARENT_AUTO, PARENT_NONE, parent_choices

_LOGGER = logging.getLogger(__name__)


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


def _clean(user_input: dict) -> dict:
    return dict(user_input, **{CONF_HOST: user_input[CONF_HOST].strip()})


class CamAlertConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CamAlertOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            user_input = _clean(user_input)
            status, errors = await _check(self.hass, user_input)
            if status is not None:
                await self.async_set_unique_id(status.get("id") or user_input[CONF_HOST])
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                return self.async_create_entry(title=status.get("name") or "CamAlert %s" % user_input[CONF_HOST],
                                               data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(user_input or {}), errors=errors)

    async def async_step_reconfigure(self, user_input=None):
        """New address, port, HTTPS or token for a player that is already added (same player only)."""
        entry = self._get_reconfigure_entry()
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


class CamAlertOptionsFlow(config_entries.OptionsFlow):
    """Options: the device the player hangs under (#86): automatic (TV/receiver with the same address), none, or a
    chosen device."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=dict(self.config_entry.options, **user_input))
        current = self.config_entry.options.get(CONF_PARENT, PARENT_AUTO)
        options = [{"value": PARENT_AUTO, "label": PARENT_AUTO}, {"value": PARENT_NONE, "label": PARENT_NONE}]
        options += parent_choices(self.hass)
        if current not in [o["value"] for o in options]:  # chosen device removed since
            current = PARENT_AUTO
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_PARENT, default=current): SelectSelector(SelectSelectorConfig(
                options=options, mode=SelectSelectorMode.DROPDOWN, translation_key=CONF_PARENT)),
        }))
