"""Minimal stand-ins for Kodi's Python modules, so the add-on can be imported and tested without Kodi."""
import sys
import types


def install(settings=None, profile="/tmp/camalert-test-profile"):
    store = dict(settings or {})
    xbmc = types.ModuleType("xbmc")
    xbmc.LOGDEBUG, xbmc.LOGINFO, xbmc.LOGWARNING, xbmc.LOGERROR = 0, 1, 2, 3
    xbmc.logged = []
    xbmc.log = lambda msg, level=1: xbmc.logged.append(msg)
    xbmc.sleep = lambda ms: None
    xbmc.executebuiltin = lambda cmd, wait=False: xbmc.logged.append("builtin " + cmd)
    xbmc.getCondVisibility = lambda expr: False
    xbmc.getInfoLabel = lambda label: "kodi-test" if label == "System.FriendlyName" else ""
    xbmc.executeJSONRPC = lambda req: '{"result": {}}'

    class Monitor(object):
        def abortRequested(self):
            return True

        def waitForAbort(self, t=None):
            return True

    class Player(object):
        def isPlaying(self):
            return False

        def isPlayingVideo(self):
            return False

    xbmc.Monitor, xbmc.Player = Monitor, Player

    xbmcgui = types.ModuleType("xbmcgui")

    class Control(object):
        def __init__(self, *a, **kw):
            self.args, self.kw = a, kw

        def setImage(self, *a):
            pass

        def setLabel(self, *a):
            pass

        def setAnimations(self, *a):
            pass

    class WindowDialog(object):
        def __init__(self):
            self.controls = []

        def addControl(self, c):
            self.controls.append(c)

        def doModal(self):
            pass

        def close(self):
            pass

    class ListItem(object):
        def __init__(self, label="", path=""):
            self.label, self.path, self.props = label, path, {}

        def setMimeType(self, m):
            self.props["mime"] = m

        def setContentLookup(self, v):
            self.props["lookup"] = v

        def setProperty(self, k, v):
            self.props[k] = v

    xbmcgui.WindowDialog, xbmcgui.ControlImage, xbmcgui.ControlLabel = WindowDialog, Control, Control
    xbmcgui.ListItem = ListItem
    xbmcgui.Window = lambda wid: types.SimpleNamespace(getProperty=lambda k: "", setProperty=lambda k, v: None,
                                                        clearProperty=lambda k: None)
    xbmcgui.Dialog = lambda: types.SimpleNamespace(ok=lambda *a: True, select=lambda *a, **k: -1)

    xbmcaddon = types.ModuleType("xbmcaddon")

    class Addon(object):
        def __init__(self, aid=None):
            pass

        def getSetting(self, k):
            return store.get(k, "")

        def setSetting(self, k, v):
            store[k] = v

        def getLocalizedString(self, i):
            return ""

        def getAddonInfo(self, k):
            return "/nonexistent/"

    xbmcaddon.Addon = Addon
    xbmcvfs = types.ModuleType("xbmcvfs")
    xbmcvfs.translatePath = lambda p: p.replace("special://profile/addon_data/service.camalert/", profile + "/") \
        .replace("special://temp/", profile + "/temp/")
    for name, mod in (("xbmc", xbmc), ("xbmcgui", xbmcgui), ("xbmcaddon", xbmcaddon), ("xbmcvfs", xbmcvfs)):
        sys.modules[name] = mod
    return store
