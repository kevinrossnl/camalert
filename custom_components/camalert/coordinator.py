"""Polls a player for what is on screen and which cameras exist."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CamAlertApi, CamAlertError
from .const import CAMERA_REFRESH_SECONDS, DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class CamAlertCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, api: CamAlertApi, entry):
        super().__init__(hass, _LOGGER, name="%s %s" % (DOMAIN, api.host),
                         update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS), config_entry=entry)
        self.api = api
        self.cameras: list[dict] = []
        self.button_guard = None  # signing.ButtonGuard of the colour-key webhook (#82)
        self._cameras_at = float("-inf")  # monotonic() may be < CAMERA_REFRESH_SECONDS right after a boot

    async def _async_update_data(self):
        try:
            status = await self.api.status()
            if not self.cameras or time.monotonic() - self._cameras_at > CAMERA_REFRESH_SECONDS:
                self.cameras = await self.api.cameras()
                self._cameras_at = time.monotonic()
        except CamAlertError as err:
            raise UpdateFailed(str(err)) from err
        return status
