# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
from Plugins.Plugin import PluginDescriptor

from . import _
from . import server
from . import mqtt
from . import bouquet
from .display import Controller


def sessionstart(reason, session=None, **kwargs):
    if reason == 0 and session is not None:
        Controller(session)
        server.start()
        mqtt.start()
        bouquet.start()


def main(session, **kwargs):
    from .setup import CamAlertSetup
    session.open(CamAlertSetup)


def mosaic(session, **kwargs):
    Controller.instance.mosaic()


def tour(session, **kwargs):
    Controller.instance.tour()


def events(session, **kwargs):
    from .diagnostics import EventsScreen
    session.open(EventsScreen)


def Plugins(**kwargs):
    return [
        PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=sessionstart),
        PluginDescriptor(name="CamAlert", description=_("Show IP cameras on your TV"),
                         where=PluginDescriptor.WHERE_PLUGINMENU, icon="camalert.png", fnc=main),
        PluginDescriptor(name=_("CamAlert mosaic"), description=_("All cameras at once"),
                         where=[PluginDescriptor.WHERE_PLUGINMENU, PluginDescriptor.WHERE_EXTENSIONSMENU],
                         icon="camalert.png", fnc=mosaic),
        PluginDescriptor(name=_("CamAlert tour"), description=_("Cameras one after the other"),
                         where=[PluginDescriptor.WHERE_PLUGINMENU, PluginDescriptor.WHERE_EXTENSIONSMENU],
                         icon="camalert.png", fnc=tour),
        PluginDescriptor(name=_("CamAlert events"), description=_("The last camera requests"),
                         where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=events),
    ]
