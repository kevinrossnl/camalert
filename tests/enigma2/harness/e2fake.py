"""Fake Enigma2 environment for compatibility tests, built from API snapshots of real images.

tests/enigma2/harness/fixtures/e2api/<api>.json is made by tools/e2_api_snapshot.py from an image's enigma2 sources:
class methods (with inherited ones) and their parameters, module level names
and the skin attributes the image understands.
The fake classes here only have the methods of that snapshot and check every call against the real parameter
list, so a call that would raise AttributeError or TypeError on that image raises it here too.
The C++ part of enigma (module `enigma`) is not in the Python sources; its differences are listed in PROFILES.

    env = e2fake.install("openatv")    # fake modules in sys.modules, CamAlert imported fresh
    env.camalert.plugin.Plugins()
    e2fake.uninstall()

Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import importlib
import importlib.util
import json
import os
import sys
import types

import _paths  # noqa: E402

ROOT = _paths.ROOT
FIXTURES = _paths.E2_API_FIXTURES
SRC = _paths.ENIGMA2_PARENT

# Known differences per image. "api" = which snapshot in tests/enigma2/harness/fixtures/e2api is used.
# "python" = Python of current releases; "verified" = where the facts come from.
PROFILES = {
    "openatv": {
        "label": "openATV 7.x / 8.x", "api": "openatv", "python": "3.12 (7.x), 3.13 (8.x)",
        "etimer": "callback", "unbind_action": True, "desktop": (1920, 1080),
        "verified": "API snapshot of openatv/enigma2; CamAlert runs on openATV 8.0.1 receivers",
    },
    "openpli": {
        "label": "OpenPLi 9.x / develop", "api": "openpli", "python": "3.12+ (develop CI builds with 3.14)",
        "etimer": "callback", "unbind_action": True, "desktop": (1280, 720),
        "verified": "API snapshot of OpenPLi/enigma2",
    },
    "openbh": {
        "label": "OpenBH 5.x", "api": "openbh", "python": "3.12+ (current branch: Python 3.14)",
        "etimer": "callback", "unbind_action": True, "desktop": (1920, 1080),
        "verified": "API snapshot of BlackHole/enigma2 (OpenBH)",
    },
    "vti": {
        "label": "VTi (Vu+)", "api": "openpli", "python": "unknown (closed source)",
        "etimer": "callback", "unbind_action": True, "desktop": (1280, 720),
        "verified": "ASSUMED: VTi sources are not public; modelled with the OpenPLi API (VTi descends from it)",
    },
    "dreamos": {
        "label": "DreamOS (Dreambox OE 2.5 / 2.6)", "api": "dreamos", "python": "2.7",
        "etimer": "connect", "unbind_action": False, "desktop": (1920, 1080),
        "verified": "API snapshot of an installed DreamOS enigma2 4.3.1 (OpenDMM/enigma2); "
                    "eTimer/eActionMap from its enigma.py",
    },
}

_FAKE_PREFIXES = ("enigma", "Components", "Screens", "Tools", "Plugins", "twisted", "skin", "CamAlert")
_api_cache = {}


def api(name):
    if name not in _api_cache:
        with open(os.path.join(FIXTURES, "%s.json" % name), encoding="utf-8") as f:
            _api_cache[name] = json.load(f)
    return _api_cache[name]


class Recorder(object):
    """Collects what the plugin did, for assertions."""

    def __init__(self):
        self.calls = []

    def add(self, *what):
        self.calls.append(what)

    def names(self):
        return [c[0] for c in self.calls]


rec = Recorder()


def checker(params, name):
    """A function with exactly the parameter list of the snapshot (defaults become None).
    Calling it with arguments the real one would refuse raises the same TypeError."""
    args = []
    for p in params:
        args.append(p[:-1] + "=None" if p.endswith("=") else p)
    ns = {}
    exec("def %s(%s):\n    return locals()\n" % (name, ", ".join(args)), ns)  # noqa: S102 - built from our fixture
    return ns[name]


def _noop(cls_name, meth):
    def f(self, *a, **kw):
        rec.add("%s.%s" % (cls_name, meth), a, kw)
    f.__name__ = meth
    return f


def strict_class(snapshot, cls_name, base=object, impl=None, keep=()):
    """A class with only the methods of the snapshot. impl: own implementations (only used when the snapshot has
    that method, unless listed in keep). Every method checks its arguments against the real parameter list."""
    impl = dict(impl or {})
    info = snapshot["classes"].get(cls_name)
    if info is None:
        raise KeyError("%s not in snapshot %s" % (cls_name, snapshot["name"]))
    body = {}
    for meth, params in info["methods"].items():
        if meth.startswith("__") and meth not in ("__init__", "__getitem__", "__setitem__", "__contains__"):
            continue
        check = checker(params, meth)
        fn = impl.pop(meth, None) or (None if meth == "__init__" else _noop(cls_name, meth))

        def make(check=check, fn=fn, meth=meth):
            def method(self, *a, **kw):
                check(self, *a, **kw)
                if fn is not None:
                    return fn(self, *a, **kw)
            method.__name__ = meth
            return method
        body[meth] = make()
    for meth in keep:
        if meth in impl:
            body[meth] = impl.pop(meth)
    for attr in info.get("attrs", []):
        if attr not in body and attr.isupper() or attr.startswith("TYPE_") or attr.startswith("WHERE_"):
            body.setdefault(attr, attr)
    return type(cls_name, (base,), body)


def module(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    parent, _, child = name.rpartition(".")
    if parent:
        if parent not in sys.modules:
            module(parent)
        setattr(sys.modules[parent], child, m)
        sys.modules[parent].__path__ = []
    return m


# ---------------------------------------------------------------- twisted (deterministic, nothing runs)

class Deferred(object):
    def __init__(self, fn=None, args=()):
        self.fn, self.args = fn, args
        self.callbacks = []

    def addCallbacks(self, ok, err=None, *a, **kw):
        self.callbacks.append((ok, err))
        return self

    def addCallback(self, ok, *a, **kw):
        self.callbacks.append((ok, None))
        return self

    def addErrback(self, err, *a, **kw):
        self.callbacks.append((None, err))
        return self

    def addBoth(self, fn, *a, **kw):
        self.callbacks.append((fn, fn))
        return self

    def fire(self, result):
        for ok, _err in self.callbacks:
            if ok:
                result = ok(result)
        return result


class DelayedCall(object):
    def __init__(self, delay, fn, a, kw):
        self.delay, self.fn, self.a, self.kw, self.cancelled = delay, fn, a, kw, False

    def active(self):
        return not self.cancelled

    def cancel(self):
        self.cancelled = True

    def reset(self, delay):
        self.delay = delay


def install_twisted():
    reactor = types.SimpleNamespace(
        calls=[], deferred=[],
        callLater=lambda d, fn, *a, **kw: _later(reactor, d, fn, a, kw),
        listenTCP=lambda port, factory, interface="", **kw: rec.add("listenTCP", port, interface) or
        types.SimpleNamespace(stopListening=lambda: None, port=port),
        listenSSL=lambda port, factory, ctx, interface="", **kw: rec.add("listenSSL", port, interface) or
        types.SimpleNamespace(stopListening=lambda: None, port=port),
        connectTCP=lambda host, port, factory, **kw: rec.add("connectTCP", host, port),
        callFromThread=lambda fn, *a, **kw: fn(*a, **kw),
        running=False)

    def defer_to_thread(fn, *a, **kw):
        d = Deferred(fn, a)
        reactor.deferred.append(d)
        return d

    class Protocol(object):
        transport = None

        def makeConnection(self, t):
            self.transport = t

    class ReconnectingClientFactory(object):
        maxDelay = 3600
        initialDelay = 1.0

        def resetDelay(self):
            pass

        def stopTrying(self):
            pass

        def retry(self, connector=None):
            pass

    class LoopingCall(object):
        def __init__(self, fn, *a, **kw):
            self.fn, self.running = fn, False

        def start(self, interval, now=True):
            self.running = True
            return Deferred()

        def stop(self):
            self.running = False

    class Resource(object):
        isLeaf = False

        def __init__(self):
            self.children = {}

        def putChild(self, path, child):
            self.children[path] = child

        def getChildWithDefault(self, path, request):
            return self.children.get(path, self)

    module("twisted")
    module("twisted.internet", reactor=reactor)
    module("twisted.internet.reactor")
    sys.modules["twisted.internet"].reactor = reactor
    sys.modules["twisted.internet.reactor"] = reactor
    module("twisted.internet.threads", deferToThread=defer_to_thread)
    module("twisted.internet.task", LoopingCall=LoopingCall, deferLater=lambda r, d, fn, *a, **kw: Deferred())
    module("twisted.internet.protocol", Protocol=Protocol, ReconnectingClientFactory=ReconnectingClientFactory,
           ClientFactory=ReconnectingClientFactory, Factory=object)
    module("twisted.internet.ssl", DefaultOpenSSLContextFactory=lambda *a, **kw: object(),
           CertificateOptions=lambda *a, **kw: object())
    module("twisted.web")
    module("twisted.web.resource", Resource=Resource, NoResource=Resource)
    module("twisted.web.server", Site=lambda root, *a, **kw: types.SimpleNamespace(resource=root), NOT_DONE_YET=1)
    return reactor


def _later(reactor, d, fn, a, kw):
    c = DelayedCall(d, fn, a, kw)
    reactor.calls.append(c)
    return c


# ---------------------------------------------------------------- enigma (C++ part)

def install_enigma(profile):
    class Signal(object):
        """DreamOS style signal: connect() returns a connection object that must be kept."""

        def __init__(self):
            self.slots = []

        def connect(self, fn):
            self.slots.append(fn)
            return types.SimpleNamespace(disconnect=lambda: self.slots.remove(fn) if fn in self.slots else None)

    class eTimer(object):
        def __init__(self):
            if profile["etimer"] == "callback":
                self.callback = []
            self.timeout = Signal()
            self.active, self.interval, self.single = False, None, False

        def start(self, ms, single=False):
            self.active, self.interval, self.single = True, ms, single

        def startLongTimer(self, seconds):
            self.active, self.interval = True, seconds * 1000

        def stop(self):
            self.active = False

        def isActive(self):
            return self.active

        def changeInterval(self, ms):
            self.interval = ms

        def fire(self):
            """Test helper: what the main loop does when the timer expires."""
            if self.single:
                self.active = False
            for fn in list(getattr(self, "callback", [])) + list(self.timeout.slots):
                fn()

    class ePicLoad(object):
        def __init__(self):
            self.PictureData = Signal()
            if profile["etimer"] == "callback":
                self.PictureData = types.SimpleNamespace(get=lambda: [])

        def setPara(self, para):
            if len(para) < 7 and profile["api"] != "dreamos":
                raise TypeError("ePicLoad.setPara needs at least 7 values")  # OpenPLi/openATV/OpenBH picload.cpp
            self.para = para
            return 0

        def startDecode(self, filename, x=0, y=0, async_=True):
            rec.add("ePicLoad.startDecode", filename)
            return 0 if os.path.exists(filename) else 1

        def getThumbnail(self, filename, x=0, y=0, async_=True):
            return 1

        def getData(self):
            return types.SimpleNamespace(pixmap=True)

        def getInfo(self, filename):
            return []

    class eSize(object):
        def __init__(self, w=0, h=0):
            self._w, self._h = w, h

        def width(self):
            return self._w

        def height(self):
            return self._h

    class ePoint(object):
        def __init__(self, x=0, y=0):
            self._x, self._y = x, y

        def x(self):
            return self._x

        def y(self):
            return self._y

    desktop = types.SimpleNamespace(size=lambda: eSize(*profile["desktop"]),
                                    makeCompatiblePixmap=lambda p: p)

    class eServiceReference(object):
        def __init__(self, ref="", *a):
            self.ref = ref if isinstance(ref, str) else "%s" % (ref,)

        def toString(self):
            return self.ref

        def valid(self):
            return bool(self.ref)

        def getPath(self):
            return self.ref.split(":")[10] if self.ref.count(":") >= 10 else ""

    class eActionMap(object):
        _inst = None

        @classmethod
        def getInstance(cls):
            if cls._inst is None:
                cls._inst = cls()
                cls._inst.bound = []
            return cls._inst

        def bindAction(self, context, prio, func):
            self.bound.append((context, prio, func))
            return types.SimpleNamespace(disconnect=lambda: None)

    if profile["unbind_action"]:
        def unbindAction(self, context, func):
            self.bound = [b for b in self.bound if b[2] != func]
        eActionMap.unbindAction = unbindAction

    class eDVBVolumecontrol(object):
        _inst = None

        @classmethod
        def getInstance(cls):
            if cls._inst is None:
                cls._inst = cls()
                cls._inst.volume = 60
            return cls._inst

        def getVolume(self):
            return self.volume

        def isMuted(self):
            return getattr(self, "muted", False)

        def setVolume(self, left, right):
            self.volume = left
            rec.add("setVolume", left, right)

    class eDVBDB(object):
        _inst = None

        @classmethod
        def getInstance(cls):
            if cls._inst is None:
                cls._inst = cls()
            return cls._inst

        def reloadBouquets(self):
            rec.add("eDVBDB.reloadBouquets")

        def reloadServicelist(self):
            rec.add("eDVBDB.reloadServicelist")

    class eConsoleAppContainer(object):
        def __init__(self):
            self.appClosed, self.dataAvail = Signal(), Signal()
            if profile["etimer"] == "callback":  # OE-A / OpenPLi: lists; DreamOS: only connect()
                self.appClosed, self.dataAvail = types.SimpleNamespace(append=lambda f: None), \
                    types.SimpleNamespace(append=lambda f: None)

        def execute(self, *cmd):
            rec.add("eConsoleAppContainer.execute", cmd)
            return 0

    module("enigma", eTimer=eTimer, ePicLoad=ePicLoad, getDesktop=lambda n=0: desktop, eSize=eSize, ePoint=ePoint,
           eServiceReference=eServiceReference, eActionMap=eActionMap, eDVBVolumecontrol=eDVBVolumecontrol,
           eDVBDB=eDVBDB, eConsoleAppContainer=eConsoleAppContainer, quitMainloop=lambda n: rec.add("quit", n),
           iPlayableService=types.SimpleNamespace(evStart=0, evEnd=1, evUpdatedInfo=2),
           gFont=lambda *a: a, RT_HALIGN_LEFT=0, RT_HALIGN_CENTER=2, RT_VALIGN_CENTER=8, RT_WRAP=32,
           loadPNG=lambda p: p)


# ---------------------------------------------------------------- Components.config

def _fromstring(el, text):
    """The value of a saved setting string (like Enigma2's ConfigElement.load); ValueError if it does not fit."""
    kind = type(el).__name__
    if kind == "ConfigYesNo":
        if text.lower() not in ("true", "false"):  # openATV writes True/False
            raise ValueError(text)
        return text.lower() == "true"
    if kind in ("ConfigSelection", "ConfigSelectionNumber"):
        value = int(text) if kind == "ConfigSelectionNumber" else text
        if value not in el.choices:
            raise ValueError(text)
        return value
    if kind in ("ConfigNumber", "ConfigInteger"):
        return int(text)
    if kind == "ConfigClock":
        return [int(x) for x in text.strip("[]").split(",")]
    return text


def install_config(snap, stored=None):
    """stored: the saved settings of config.plugins.camalert ({name: string}, like /etc/enigma2/settings)."""
    stored = stored if stored is not None else {}

    class ConfigElement(object):
        def __init__(self):
            self.notifiers = []
            self.saved_value = None

        def addNotifier(self, fn, initial_call=True, immediate_feedback=True, call_on_save_or_cancel=False):
            self.notifiers.append(fn)
            if initial_call:
                fn(self)

        def save(self):
            self.saved_value = self.value

        def cancel(self):
            pass

        def load(self):
            pass

        def isChanged(self):
            return self.saved_value != self.value

        def getValue(self):
            return self._value

        def setValue(self, v):
            self._value = v
            for fn in self.notifiers:
                fn(self)

        value = property(getValue, setValue)

    def base_init(self, default):
        ConfigElement.__init__(self)
        self.default = default
        self._value = default

    impl = {}

    def sel_init(self, choices, default=None, *a, **kw):
        keys = [c[0] if isinstance(c, (tuple, list)) else c for c in choices]
        self.choices = keys
        base_init(self, default if default is not None else (keys[0] if keys else None))
        if self._value not in keys:
            raise ValueError("default %r not in choices" % (self._value,))
    impl["ConfigSelection"] = sel_init
    impl["ConfigYesNo"] = lambda self, default=False, *a, **kw: base_init(self, bool(default))
    impl["ConfigText"] = lambda self, default="", *a, **kw: base_init(self, default)
    impl["ConfigPassword"] = lambda self, default="", *a, **kw: base_init(self, default)
    impl["ConfigNumber"] = lambda self, default=0, *a, **kw: base_init(self, int(default))
    impl["ConfigInteger"] = lambda self, default, limits=None, *a, **kw: base_init(self, int(default))

    def num_init(self, min, max, stepwidth, default=None, *a, **kw):
        base_init(self, default if default is not None else min)
        self.choices = list(range(min, max + 1, stepwidth))
    impl["ConfigSelectionNumber"] = num_init

    def clock_init(self, default, *a, **kw):
        if not isinstance(default, (int, float)):
            raise TypeError("ConfigClock default must be seconds")
        base_init(self, [int(default) // 3600 % 24, int(default) // 60 % 60])
    impl["ConfigClock"] = clock_init

    def save(self):  # like Enigma2: a default value is not stored (unless save_forced)
        forced = getattr(self, "save_forced", False)
        self.saved_value = None if self._value == self.default and not forced else self._value

    def cancel(self):  # back to the saved value (or the default)
        self.value = self.default if self.saved_value is None else self.saved_value

    classes = {}
    for name in ("ConfigSelection", "ConfigYesNo", "ConfigText", "ConfigPassword", "ConfigNumber", "ConfigInteger",
                 "ConfigSelectionNumber", "ConfigClock"):
        classes[name] = strict_class(snap, name, ConfigElement, {"__init__": impl[name], "save": save, "cancel": cancel})

    class ConfigSubsection(object):
        def __init__(self):
            object.__setattr__(self, "content", types.SimpleNamespace(items={}, stored_values=stored))

        def __setattr__(self, name, value):
            self.content.items[name] = value
            object.__setattr__(self, name, value)
            text = self.content.stored_values.get(name)
            if text is not None and isinstance(value, ConfigElement):
                try:
                    value._value = _fromstring(value, text)  # a value that does not fit keeps the default
                except ValueError:
                    pass
                value.saved_value = value._value

        def save(self):
            for v in self.content.items.values():
                v.save()

    config = ConfigSubsection()
    config.plugins = ConfigSubsection()
    config.misc = ConfigSubsection()
    configfile = types.SimpleNamespace(save=lambda: rec.add("configfile.save"))
    names = snap["modules"]["Components.config"]
    gcle = checker(names.get("getConfigListEntry") or ["*args"], "getConfigListEntry")

    def getConfigListEntry(*args):
        gcle(*args)
        return args
    class ConfigNothing(ConfigElement):  # section headings in setup lists (not in the snapshots)
        def __init__(self):
            ConfigElement.__init__(self)
            self.default = self._value = ""

    m = module("Components.config", config=config, ConfigNothing=ConfigNothing, configfile=configfile, ConfigSubsection=ConfigSubsection,
               ConfigElement=ConfigElement, getConfigListEntry=getConfigListEntry, **classes)
    for missing in [n for n in classes if n not in names]:
        delattr(m, missing)
    return config


# ---------------------------------------------------------------- Screens, Components, Tools, Plugins

class _Widget(object):
    def __init__(self, *a, **kw):
        self.text = a[0] if a else ""
        self.instance = types.SimpleNamespace(setPixmap=lambda p: None, show=lambda: None, hide=lambda: None,
                                              move=lambda p: None, resize=lambda s: None, refresh=lambda: None,
                                              setText=lambda t: None, window=None)
        self.visible = True
        self.onSelectionChanged = []
        self.list = list(a[0]) if a and isinstance(a[0], list) else []

    def setText(self, t):
        self.text = t

    def getText(self):
        return self.text

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def setList(self, lst):
        self.list = lst

    def getCurrent(self):
        return self.list[0] if self.list else None

    def getCurrentIndex(self):
        return 0

    def pageUp(self):
        pass

    def pageDown(self):
        pass

    def invalidateCurrent(self):
        pass

    def moveToIndex(self, i):
        pass


def install_screens(snap, profile):
    def screen_init(self, session, parent=None, *a, **kw):
        dict.__init__(self)
        self.session, self.parent = session, parent
        self.onLayoutFinish, self.onClose, self.onShown, self.onShow, self.onHide, self.onExecBegin = \
            [], [], [], [], [], []
        self.instance = types.SimpleNamespace(show=lambda: None, hide=lambda: None, move=lambda p: None,
                                              setTitle=lambda t: None)
        self.title = ""

    def set_title(self, title, *a, **kw):
        self.title = title

    def close(self, *ret):
        for fn in list(self.onClose):
            fn()
        self.session.closed.append((self, ret))

    Screen = strict_class(snap, "Screen", dict, {"__init__": screen_init, "setTitle": set_title, "close": close,
                                                 "show": lambda self: None, "hide": lambda self: None})
    module("Screens.Screen", Screen=Screen)

    def cls_screen(name, **impl):
        return strict_class(snap, name, Screen, dict({"__init__": lambda self, session, *a, **kw:
                                                      screen_init(self, session)}, **impl))

    MessageBox = cls_screen("MessageBox")
    for i, t in enumerate(("TYPE_YESNO", "TYPE_INFO", "TYPE_WARNING", "TYPE_ERROR", "TYPE_MESSAGE")):
        setattr(MessageBox, t, i)
    module("Screens.MessageBox", MessageBox=MessageBox)
    module("Screens.ChoiceBox", ChoiceBox=cls_screen("ChoiceBox"))
    module("Screens.VirtualKeyBoard", VirtualKeyBoard=cls_screen("VirtualKeyBoard"))

    ChannelSelection = strict_class(snap, "ChannelSelection", object, {
        "__init__": lambda self, session, *a, **kw: None})

    def infobar_init(self, session, *a, **kw):
        self.session = session
        self.servicelist = ChannelSelection.__new__(ChannelSelection)
        type(self).instance = self
    InfoBar = strict_class(snap, "InfoBar", object, {"__init__": infobar_init})
    InfoBar.instance = None
    MoviePlayer = cls_screen("MoviePlayer")
    module("Screens.InfoBar", InfoBar=InfoBar, MoviePlayer=MoviePlayer)
    module("Screens.ChannelSelection", ChannelSelection=ChannelSelection)

    Standby = strict_class(snap, "Standby", object, {"__init__": lambda self, session, *a, **kw: None})
    standby_names = snap["modules"]["Screens.Standby"]
    m = module("Screens.Standby", inStandby=None, Standby=Standby)
    if "TVinStandby" in standby_names:
        m.TVinStandby = types.SimpleNamespace(getTVstate=lambda s: False)

    def cls_comp(name):
        if name in snap["classes"]:
            return strict_class(snap, name, _Widget, {"__init__": lambda self, *a, **kw: _Widget.__init__(self, *a),
                                                      "setText": _Widget.setText, "getText": _Widget.getText,
                                                      "show": _Widget.show, "hide": _Widget.hide},
                                keep=())
        return _Widget
    module("Components.Label", Label=cls_comp("Label"), MultiColorLabel=_Widget)
    module("Components.Pixmap", Pixmap=cls_comp("Pixmap"), MultiPixmap=_Widget)
    module("Components.MenuList", MenuList=type("MenuList", (_Widget,), {}))
    module("Components.ScrollLabel", ScrollLabel=type("ScrollLabel", (_Widget,), {}))
    module("Components.Sources.StaticText", StaticText=type("StaticText", (_Widget,), {}))
    module("Components.Sources")

    class ActionMap(object):
        def __init__(self, contexts=None, actions=None, prio=0):
            self.contexts, self.actions, self.prio = contexts or [], actions or {}, prio
            for k, v in self.actions.items():
                if not callable(v):
                    raise TypeError("action %s is not callable" % k)

        def setEnabled(self, on):
            pass

        def execBegin(self):
            pass

        def execEnd(self):
            pass
    class HelpableActionMap(ActionMap):
        """openATV/OpenPLi: (parent, contexts, actions, prio); actions may be (function, help text)."""
        def __init__(self, parent, contexts, actions=None, prio=0, description=None):
            contexts = [contexts] if isinstance(contexts, str) else contexts
            plain = {}
            for k, v in (actions or {}).items():
                fn, text = v if isinstance(v, tuple) else (v, None)
                plain[k] = fn
                parent.helpList.append((self, contexts[0], k, text))
            ActionMap.__init__(self, contexts, plain, prio)
    module("Components.ActionMap", ActionMap=ActionMap, HelpableActionMap=HelpableActionMap, NumberActionMap=ActionMap)

    class HelpableScreen(object):  # Screens.HelpMenu (not in the snapshots; same on every supported image)
        def __init__(self):
            self.helpList = []
            self["helpActions"] = ActionMap(["HelpActions"], {"displayHelp": self.showHelp})

        def showHelp(self):
            rec.add("showHelp", tuple(self.helpList))
    if profile["api"] != "dreamos":
        module("Screens.HelpMenu", HelpableScreen=HelpableScreen)

    provided = [k for k in snap["classes"]["ConfigListScreen"].get("provides", []) if k in ("HelpWindow", "VKeyIcon")]

    def cls_init(self, list, session=None, *a, **kw):
        for k in provided:  # created by ConfigListScreen itself on that image (used in skins)
            if k not in self:
                self[k] = _Widget()
        self["config"] = _Widget(list)
        self["config"].list = list
        setattr(self["config"], "l", types.SimpleNamespace(setList=lambda lst: None))  # ConfigList.l
        self.on_change = kw.get("on_change")
    ConfigListScreen = strict_class(snap, "ConfigListScreen", object, {"__init__": cls_init})
    module("Components.ConfigList", ConfigListScreen=ConfigListScreen, ConfigList=_Widget)

    language = types.SimpleNamespace(callbacks=[], addCallback=lambda fn: language.callbacks.append(fn),
                                     getLanguage=lambda: "en_GB", getActiveLanguage=lambda: "en_GB")
    module("Components.Language", language=language)

    dirs = snap["modules"]["Tools.Directories"]
    module("Tools.Directories", SCOPE_PLUGINS=dirs.get("SCOPE_PLUGINS") or 8, SCOPE_CURRENT_SKIN=1,
           resolveFilename=lambda scope, base="", path_prefix=None: os.path.join("/tmp/e2compat-plugins", base),
           fileExists=os.path.exists)

    notif = snap["modules"]["Tools.Notifications"]
    popup_check = checker(notif["AddPopup"], "AddPopup")

    def AddPopup(*a, **kw):
        popup_check(*a, **kw)
        rec.add("AddPopup", a, kw)
    module("Tools.Notifications", AddPopup=AddPopup, AddNotification=lambda *a, **kw: rec.add("AddNotification", a),
           AddNotificationWithCallback=lambda *a, **kw: rec.add("AddNotificationWithCallback", a))
    module("Tools")

    pd = snap["classes"]["PluginDescriptor"]
    pd_check = checker(pd["methods"]["__init__"], "__init__")

    class PluginDescriptor(object):
        def __init__(self, *a, **kw):
            pd_check(self, *a, **kw)
            self.__dict__.update(pd_check(self, *a, **kw))
    for attr in pd["attrs"]:
        if attr.startswith("WHERE_"):
            setattr(PluginDescriptor, attr, attr)
    module("Plugins")
    module("Plugins.Plugin", PluginDescriptor=PluginDescriptor)
    return InfoBar


class Session(object):
    """Fake session; nav is built from the Navigation snapshot (only its methods)."""

    def __init__(self, snap):
        self.opened, self.dialogs, self.closed = [], [], []
        self.current_ref = None

        class Service(object):
            def seek(self_):
                return types.SimpleNamespace(isCurrentlySeekable=lambda: 0)

        impl = {
            "getCurrentlyPlayingServiceReference": lambda nav: self.current_ref,
            "getCurrentlyPlayingServiceOrGroup": lambda nav: self.current_ref,
            "getCurrentService": lambda nav: Service(),
            "getRecordings": lambda nav, *a, **kw: [],
            "playService": lambda nav, ref, *a, **kw: (rec.add("playService", ref.toString()),
                                                       setattr(self, "current_ref", ref)),
            "stopService": lambda nav: rec.add("stopService"),
        }
        Nav = strict_class(snap, "Navigation", object, dict(impl, __init__=lambda nav, *a, **kw: None))
        self.nav = Nav.__new__(Nav)
        sess = snap["classes"]["Session"]["methods"]
        self._open_check = checker(sess["open"], "open")
        self._owc_check = checker(sess["openWithCallback"], "openWithCallback")

    def open(self, screen, *a, **kw):
        self._open_check(self, screen, *a, **kw)
        s = screen(self, *a, **kw)
        self.opened.append(s)
        return s

    def openWithCallback(self, callback, screen, *a, **kw):
        self._owc_check(self, callback, screen, *a, **kw)
        s = screen(self, *a, **kw)
        self.opened.append(s)
        return s

    def instantiateDialog(self, screen, *a, **kw):
        s = screen(self, *a, **kw)
        self.dialogs.append(s)
        return s

    def deleteDialog(self, screen):
        if screen in self.dialogs:
            self.dialogs.remove(screen)


class Env(object):
    pass


def uninstall():
    for name in list(sys.modules):
        if name.split(".")[0] in _FAKE_PREFIXES:
            del sys.modules[name]
    while SRC in sys.path:
        sys.path.remove(SRC)
    rec.calls[:] = []


def install(profile_name, stored=None):
    """Installs the fake modules of an image and imports CamAlert (players/enigma2/CamAlert) fresh.
    stored: saved settings of config.plugins.camalert ({name: string}); env.stored is that dict afterwards."""
    uninstall()
    profile = dict(PROFILES[profile_name], name=profile_name)
    snap = api(profile["api"])
    env = Env()
    env.profile, env.snapshot, env.rec = profile, snap, rec
    env.reactor = install_twisted()
    install_enigma(profile)
    env.stored = dict(stored or {})
    env.config = install_config(snap, env.stored)
    env.InfoBar = install_screens(snap, profile)
    env.Session = lambda: Session(snap)
    module("skin", parseColor=lambda c: c, applySkin=lambda *a: None)
    sys.path.insert(0, SRC)
    # the ipk has the core as CamAlert/camalert_core/; __init__ already uses it (settings migration, #39)
    spec = importlib.util.spec_from_file_location("CamAlert", os.path.join(SRC, "CamAlert", "__init__.py"),
                                                  submodule_search_locations=[os.path.join(SRC, "CamAlert")])
    package = importlib.util.module_from_spec(spec)
    sys.modules["CamAlert"] = package
    _paths.attach_core("CamAlert")
    spec.loader.exec_module(package)
    env.camalert = package
    for sub in ("services", "keys", "display", "setup", "plugin", "bouquet", "server", "mqtt", "diagnostics"):
        setattr(env.camalert, sub, importlib.import_module("CamAlert." + sub))
    return env
