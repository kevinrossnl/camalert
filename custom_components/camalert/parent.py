"""Show the player under the TV or receiver it runs on (#86): the CamAlert device gets `via_device` = the device of
the Enigma2, Kodi or Android TV integration with the same address, or the device chosen in the options."""
from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

CONF_PARENT = "parent_device"
PARENT_AUTO = "auto"
PARENT_NONE = "none"
# integrations that make a device for the TV or receiver itself; their config entry has the address in "host"
PARENT_DOMAINS = ("enigma2", "kodi", "androidtv", "androidtv_remote", "nfandroidtv")


def _host(value) -> str:
    return str(value or "").strip().lower().rstrip(".")


def _main_device(reg, entry_id: str):
    """The integration's own device for that config entry (not a device that hangs under another one)."""
    devices = sorted(dr.async_entries_for_config_entry(reg, entry_id), key=lambda d: d.via_device_id is not None)
    return devices[0] if devices else None


def find_parent(hass: HomeAssistant, entry, own_id: str | None = None) -> str | None:
    """Device id of the parent: the chosen device, none, or (automatic) the TV/receiver with the same address."""
    choice = entry.options.get(CONF_PARENT, PARENT_AUTO)
    if choice == PARENT_NONE:
        return None
    reg = dr.async_get(hass)
    if choice != PARENT_AUTO:
        device = reg.async_get(choice)  # removed since: no parent
        return device.id if device is not None and device.id != own_id else None
    notify = entry.data.get("notify_entity")
    if notify:  # #95: a notification app through Home Assistant's nfandroidtv: under that integration's TV device
        from homeassistant.helpers import entity_registry as er
        ent = er.async_get(hass).async_get(notify)
        if ent is not None and ent.device_id and ent.device_id != own_id:
            return ent.device_id
    host = _host(entry.data.get(CONF_HOST))
    for other in hass.config_entries.async_entries():
        if other.domain in PARENT_DOMAINS and host and _host(other.data.get(CONF_HOST)) == host:
            device = _main_device(reg, other.entry_id)
            if device is not None and device.id != own_id:
                return device.id
    return None


def link_parent(hass: HomeAssistant, entry) -> None:
    """Set (or clear) via_device of the player's device; nothing changes when it is already right."""
    from . import player_device
    device = player_device(hass, entry)
    if device is None:
        return
    parent = find_parent(hass, entry, device.id)
    if device.via_device_id != parent:
        dr.async_get(hass).async_update_device(device.id, via_device_id=parent)


def parent_choices(hass: HomeAssistant) -> list[dict]:
    """Devices that can be chosen as parent: every device except CamAlert players, by name."""
    out = []
    for device in dr.async_get(hass).devices.values():
        if any(ident[0] == DOMAIN for ident in device.identifiers):
            continue
        out.append({"value": device.id, "label": device.name_by_user or device.name or device.id})
    return sorted(out, key=lambda o: o["label"].lower())
