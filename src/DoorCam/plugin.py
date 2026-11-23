# -*- coding: utf-8 -*-
# DoorCam - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 DoorCam developers. Licensed under the GNU GPL v2 (see LICENSE).
from Plugins.Plugin import PluginDescriptor

from . import _
from . import server
from .display import Controller


def sessionstart(reason, session=None, **kwargs):
    if reason == 0 and session is not None:
        Controller(session)
        server.start()


def main(session, **kwargs):
    from .setup import DoorCamSetup
    session.open(DoorCamSetup)


def mosaic(session, **kwargs):
    Controller.instance.mosaic()


def Plugins(**kwargs):
    return [
        PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=sessionstart),
        PluginDescriptor(name="DoorCam", description=_("Show IP cameras on your TV"),
                         where=PluginDescriptor.WHERE_PLUGINMENU, icon="doorcam.png", fnc=main),
        PluginDescriptor(name=_("DoorCam mosaic"), description=_("All cameras at once"),
                         where=[PluginDescriptor.WHERE_PLUGINMENU, PluginDescriptor.WHERE_EXTENSIONSMENU],
                         icon="doorcam.png", fnc=mosaic),
    ]
