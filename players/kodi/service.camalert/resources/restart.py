# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Restarts the CamAlert service after an update from Home Assistant (#126).

Kodi registers a new version with UpdateLocalAddons but keeps the running service on the old code. The service
cannot restart itself (turning the add-on off stops it), so it starts this script with RunScript: a separate
interpreter that turns the add-on off and on again, which starts the service with the new code.
"""
import json

import xbmc

ADDON_ID = "service.camalert"


def rpc(method, params):
    return xbmc.executeJSONRPC(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}))


def main():
    xbmc.sleep(2000)  # let UpdateLocalAddons finish
    xbmc.log("[CamAlert] restarting the service after the update", xbmc.LOGINFO)
    rpc("Addons.SetAddonEnabled", {"addonid": ADDON_ID, "enabled": False})
    xbmc.sleep(2000)
    rpc("Addons.SetAddonEnabled", {"addonid": ADDON_ID, "enabled": True})


if __name__ == "__main__":
    main()
