"""Buttons: show a camera, mosaic, hide, problem report (#132)."""
from __future__ import annotations

import json
import os
import time

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

from .entity import CamAlertEntity

REPORT_DIR = "camalert_reports"


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known: set[str] = set()

    def add_new():
        new = []
        for cam in coordinator.cameras:
            if cam["name"] not in known:
                known.add(cam["name"])
                new.append(ShowButton(coordinator, entry, cam))
        if new:
            async_add_entities(new)

    api = coordinator.api  # entities follow the player's capabilities (older players: everything)
    async_add_entities(([MosaicButton(coordinator, entry)] if api.supports("mosaic") else [])
                       + ([HideButton(coordinator, entry)] if api.supports("hide") else [])
                       + ([ReportButton(coordinator, entry)] if api.capabilities and "report" in api.capabilities
                          else []))
    if not api.supports("show"):
        return
    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class ShowButton(CamAlertEntity, ButtonEntity):
    _attr_translation_key = "show"

    def __init__(self, coordinator, entry, cam):
        super().__init__(coordinator, entry, "show_" + cam["name"])
        self._cam = cam["name"]
        self._attr_translation_placeholders = {"camera": cam.get("title") or cam["name"]}

    async def async_press(self) -> None:
        await self._call(self.coordinator.api.show(self._cam))


class MosaicButton(CamAlertEntity, ButtonEntity):
    _attr_translation_key = "mosaic"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "mosaic")

    async def async_press(self) -> None:
        await self._call(self.coordinator.api.mosaic())


class HideButton(CamAlertEntity, ButtonEntity):
    _attr_translation_key = "hide"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "hide")

    async def async_press(self) -> None:
        await self._call(self.coordinator.api.hide())


def write_report(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)


class ReportButton(CamAlertEntity, ButtonEntity):
    """#132: the player's problem report plus the Home Assistant diagnostics in one file under
    /config/camalert_reports/, and a notification with a link to the pre-filled GitHub issue form."""

    _attr_translation_key = "problem_report"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "problem_report")
        self._entry = entry

    async def async_press(self) -> None:
        from homeassistant.components import persistent_notification
        from homeassistant.const import __version__ as ha_version

        from .api import INTEGRATION_VERSION
        from .diagnostics import async_get_config_entry_diagnostics

        answer = await self._call(self.coordinator.api.report(), refresh=False)
        diagnostics = await async_get_config_entry_diagnostics(self.hass, self._entry)
        data = {"home_assistant": ha_version, "integration": INTEGRATION_VERSION,
                "player_report": answer.get("report"), "diagnostics": diagnostics}
        name = "".join(c if c.isalnum() else "_" for c in (self._entry.title or "player").lower()).strip("_")
        path = self.hass.config.path(REPORT_DIR, "%s-%s.json" % (name, time.strftime("%Y%m%d-%H%M%S")))
        await self.hass.async_add_executor_job(write_report, path, data)
        persistent_notification.async_create(
            self.hass,
            "Saved in `%s` (without passwords or tokens; check it once more before you share it).\n\n"
            "[Open a pre-filled GitHub issue](%s) and paste the file's content under *Problem report*."
            % (path, answer.get("issue_url", "")),
            title="CamAlert problem report: %s" % (self._entry.title or ""),
            notification_id="camalert_report_%s" % self._entry.entry_id)
