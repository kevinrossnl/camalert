"""Add a receiver from the Home Assistant UI."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CamAlertApi, CamAlertError
from .const import CONF_HTTPS, CONF_TOKEN, CONF_VERIFY_SSL, DEFAULT_PORT, DOMAIN


def _schema(defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
        vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
        vol.Optional(CONF_HTTPS, default=defaults.get(CONF_HTTPS, False)): bool,
        vol.Optional(CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, False)): bool,
        vol.Optional(CONF_TOKEN, default=defaults.get(CONF_TOKEN, "")): str,
    })


class CamAlertConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            api = CamAlertApi(async_get_clientsession(self.hass, verify_ssl=False), user_input[CONF_HOST].strip(),
                             user_input[CONF_PORT], user_input.get(CONF_HTTPS, False),
                             user_input.get(CONF_VERIFY_SSL, False), user_input.get(CONF_TOKEN, ""))
            try:
                status = await api.status()
            except CamAlertError as err:
                errors["base"] = "forbidden" if "forbidden" in str(err) else "cannot_connect"
            else:
                await self.async_set_unique_id(status.get("id") or user_input[CONF_HOST])
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST].strip()})
                user_input[CONF_HOST] = user_input[CONF_HOST].strip()
                return self.async_create_entry(title=status.get("name") or "CamAlert %s" % user_input[CONF_HOST],
                                               data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(user_input or {}), errors=errors)
