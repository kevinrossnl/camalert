"""Notify entity per player (#85): `notify.send_message` shows the message as a notification on the TV, with the
picture of a camera: the camera named in the title, otherwise the player's default camera."""
from __future__ import annotations

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature

from .entity import CamAlertEntity

LABEL_MAX = 40  # the players show at most 40 characters of the label


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.runtime_data.api.supports("show"):
        async_add_entities([CamAlertNotify(entry.runtime_data, entry)])


class CamAlertNotify(CamAlertEntity, NotifyEntity):
    _attr_translation_key = "notification"
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "notify")

    def _camera(self, title: str | None) -> str | None:
        """The camera whose name (or own name on the player) is the title; None = not a camera."""
        wanted = (title or "").strip().lower()
        for cam in self.coordinator.cameras if wanted else ():
            if wanted in (cam["name"].lower(), str(cam.get("title") or "").strip().lower()):
                return cam["name"]
        return None

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        from . import _error
        cam = self._camera(title)
        label = " ".join(str(message or "").split())
        if title and cam is None:  # a title that is not a camera goes before the message
            label = "%s: %s" % (" ".join(title.split()), label) if label else " ".join(title.split())
        answer = await self._call(self.coordinator.api.show(cam, mode="notify", label=label[:LABEL_MAX].strip() or None))
        if isinstance(answer, dict) and answer.get("action") == "error":
            raise _error("unknown_camera", name=self._entry.title)
