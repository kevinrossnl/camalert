"""Strict stand-ins for Kodi's Python modules, generated per Kodi version (#29).

The modules, functions, classes and parameter lists come from tests/kodi/fixtures/kodi_api/<version>.json
(Kodistubs of that release, see tools/kodi_api_snapshot.py):
  - a name that does not exist in that Kodi version raises AttributeError;
  - a call with arguments that version does not accept raises TypeError (like the real C++ bindings);
  - every call is recorded in CALLS;
  - executeJSONRPC checks method and parameters against tests/kodi/fixtures/jsonrpc/<version>.json (from
    Kodi's own JSON-RPC schema) and answers with a small schema-valid result; problems go to JSONRPC_PROBLEMS;
  - xbmc.Monitor aborts after MONITOR["waits"] waits, so the service loop really runs.

    store = stubs.install(settings={"camera": "garden"}, version=21)
"""
import json
import os
import sys
import types

import _paths

API = _paths.KODI_API_FIXTURES
JSONRPC = _paths.KODI_JSONRPC_FIXTURES
VERSIONS = (19, 20, 21, 22)
DEFAULT_VERSION = 21

CALLS = []             # (qualified name, args, kwargs)
JSONRPC_PROBLEMS = []  # requests the real Kodi would refuse
MONITOR = {"waits": 0}  # waitForAbort() calls before abortRequested() becomes True
LOGGED = []
CONSTANTS = {"LOGDEBUG": 0, "LOGINFO": 1, "LOGWARNING": 2, "LOGERROR": 3, "LOGFATAL": 4, "LOGNONE": 5,
             "NOTIFICATION_INFO": "info", "NOTIFICATION_WARNING": "warning", "NOTIFICATION_ERROR": "error"}


def _load(version):
    with open(os.path.join(API, "%d.json" % version), encoding="utf-8") as f:
        return json.load(f)["modules"]


def _jsonrpc_schema(version):
    with open(os.path.join(JSONRPC, "%d.json" % version), encoding="utf-8") as f:
        return json.load(f)["methods"]


def checker(params):
    args = [p[:-1] + "=None" if p.endswith("=") else p for p in params]
    ns = {}
    exec("def f(%s):\n    return locals()\n" % ", ".join(args), ns)  # noqa: S102 - built from our fixture
    return ns["f"]


def _record(name, a, kw):
    CALLS.append((name, a, kw))


def _function(mod, name, params, impl):
    check = checker(params)

    def f(*a, **kw):
        check(*a, **kw)
        _record("%s.%s" % (mod, name), a, kw)
        return impl(*a, **kw) if impl else None
    f.__name__ = name
    return f


def _methods(api, mod, cls):
    info = api[mod]["classes"][cls]
    out = {}
    for b in info["bases"]:
        if b in api[mod]["classes"]:
            out.update(_methods(api, mod, b))
    out.update(info["methods"])
    return out


def _class(api, mod, cls, impl, made):
    """A class with exactly the methods of that Kodi version; impl: our behaviour for some of them."""
    if cls in made:
        return made[cls]
    info = api[mod]["classes"][cls]
    bases = tuple(_class(api, mod, b, impl, made) for b in info["bases"] if b in api[mod]["classes"]) or (object,)
    body = {}
    own = impl.get(cls, {})
    for meth, params in info["methods"].items():
        if meth.startswith("__") and meth != "__init__":
            continue
        check = checker(params)
        fn = own.get(meth)

        def make(check=check, fn=fn, meth=meth):
            def method(self, *a, **kw):
                check(self, *a, **kw)
                if meth != "__init__":
                    _record("%s.%s.%s" % (mod, cls, meth), a, kw)
                if fn is not None:
                    return fn(self, *a, **kw)
                if meth == "__init__":
                    self._args, self._kw = a, kw
                return None
            method.__name__ = meth
            return method
        body[meth] = make()
    made[cls] = type(cls, bases, body)
    return made[cls]


def _jsonrpc(version):
    schema = _jsonrpc_schema(version)
    answers = {"Application.GetProperties": {"volume": 80, "muted": False},
               "Application.SetVolume": 50, "Player.GetActivePlayers": [], "JSONRPC.Ping": "pong"}

    def execute(text):
        try:
            req = json.loads(text)
        except ValueError:
            JSONRPC_PROBLEMS.append("not JSON: %r" % text)
            return json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}})
        method, params = req.get("method"), req.get("params") or {}
        rid = req.get("id")
        m = schema.get(method)
        problem = None
        if m is None:
            problem = "Kodi %d has no JSON-RPC method %s" % (version, method)
        else:
            names = {p["name"] for p in m["params"]}
            unknown = sorted(set(params) - names)
            missing = sorted(p["name"] for p in m["params"] if p.get("required") and p["name"] not in params)
            if unknown or missing:
                problem = "%s on Kodi %d: unknown %s, missing %s" % (method, version, unknown, missing)
            for p in m["params"]:
                if p["name"] in params and p.get("enum") is not None:
                    values = params[p["name"]] if isinstance(params[p["name"]], list) else [params[p["name"]]]
                    bad = [v for v in values if v not in p["enum"]]
                    if bad:
                        problem = "%s on Kodi %d: %s not in %s" % (method, version, bad, p["name"])
        if problem:
            JSONRPC_PROBLEMS.append(problem)
            return json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": "Invalid params."}})
        result = answers.get(method, "OK")
        if method == "Application.SetVolume" and isinstance(params.get("volume"), int):
            result = params["volume"]
        return json.dumps({"jsonrpc": "2.0", "id": rid, "result": result})
    return execute


def install(settings=None, profile="/tmp/camalert-test-profile", version=DEFAULT_VERSION, addon_path=None):
    """Puts strict xbmc, xbmcgui, xbmcaddon, xbmcvfs, xbmcplugin modules of one Kodi version into sys.modules.
    Returns the settings store (dict) behind xbmcaddon.Addon().getSetting/setSetting."""
    api = _load(version)
    store = dict(settings or {})
    del CALLS[:]
    del JSONRPC_PROBLEMS[:]
    del LOGGED[:]
    MONITOR["waits"] = 0
    if addon_path is None:
        addon_path = _paths.KODI_ADDON + os.sep

    def translate(p):
        return p.replace("special://profile/addon_data/service.camalert/", profile + "/") \
            .replace("special://temp/", profile + "/temp/")

    class Monitor(object):
        def abortRequested(self):
            return MONITOR["waits"] <= 0

        def waitForAbort(self, timeout=None):
            MONITOR["waits"] -= 1
            return MONITOR["waits"] < 0

    def localized(_self, i):
        return ""  # Kodi only knows the strings after a restart: kodiapi.tr() falls back to strings.po

    impl = {
        "xbmc": {
            "functions": {
                "log": lambda msg, level=1: LOGGED.append(msg),
                "sleep": lambda ms: None,
                "executebuiltin": lambda cmd, wait=False: LOGGED.append("builtin " + cmd),
                "getCondVisibility": lambda expr: False,
                "getInfoLabel": lambda label: "kodi-test" if label == "System.FriendlyName" else "",
                "executeJSONRPC": _jsonrpc(version),
                "translatePath": translate,
            },
            "classes": {
                "Monitor": {"__init__": lambda self: None,
                            "abortRequested": lambda self: Monitor.abortRequested(self),
                            "waitForAbort": lambda self, timeout=None: Monitor.waitForAbort(self, timeout)},
                "Player": {"__init__": lambda self: None, "isPlaying": lambda self: False,
                           "isPlayingVideo": lambda self: False, "getPlayingFile": lambda self: "",
                           "getTime": lambda self: 0.0},
            },
        },
        "xbmcgui": {
            "functions": {},
            "classes": {
                "Window": {"getProperty": lambda self, key: ""},
                "Dialog": {"ok": lambda self, *a, **kw: True, "select": lambda self, *a, **kw: -1,
                           "yesno": lambda self, *a, **kw: False},
                "WindowDialog": {"__init__": lambda self, *a, **kw: setattr(self, "controls", []),
                                 "addControl": lambda self, c: self.controls.append(c)},
                "ListItem": {"__init__": lambda self, label="", label2="", path="", offscreen=False:
                             self.__dict__.update(label=label, label2=label2, path=path, props={}),
                             "setMimeType": lambda self, m: self.props.__setitem__("mime", m),
                             "setContentLookup": lambda self, v: self.props.__setitem__("lookup", v),
                             "setProperty": lambda self, k, v: self.props.__setitem__(k, v),
                             "getVideoInfoTag": lambda self: sys.modules["xbmc"].InfoTagVideo()},
            },
        },
        "xbmcaddon": {
            "functions": {},
            "classes": {
                "Addon": {"__init__": lambda self, id=None: None,
                          "getSetting": lambda self, k: store.get(k, ""),
                          "setSetting": lambda self, k, v: store.__setitem__(k, v),
                          "getLocalizedString": localized,
                          "getAddonInfo": lambda self, k: addon_path if k == "path" else "service.camalert"},
            },
        },
        "xbmcvfs": {"functions": {"translatePath": translate}, "classes": {}},
        "xbmcplugin": {"functions": {}, "classes": {}},  # #107: every call is only recorded
    }
    for name, m in api.items():
        mod = types.ModuleType(name)
        mod.KODI_VERSION = version
        for const in m["constants"]:
            setattr(mod, const, CONSTANTS.get(const, const))
        made = {}
        for cls in m["classes"]:
            setattr(mod, cls, _class(api, name, cls, impl[name]["classes"], made))
        for fn, params in m["functions"].items():
            setattr(mod, fn, _function(name, fn, params, impl[name]["functions"].get(fn)))
        sys.modules[name] = mod
    sys.modules["xbmc"].logged = LOGGED
    return store


def calls(prefix):
    """Recorded calls whose name starts with prefix, e.g. calls('xbmcgui.ControlLabel')."""
    return [c for c in CALLS if c[0].startswith(prefix)]
