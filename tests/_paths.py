"""The only place in the tests that knows where things live in the repository (#27).

Every test module does `import _paths` (the tests folder is on sys.path for pytest and for
`python3 -m unittest discover -s tests`) and takes its paths from here. When files move (#1), only this file
changes.
"""
import importlib
import importlib.util
import os
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
TOOLS = os.path.join(ROOT, "tools")
DOCS = os.path.join(ROOT, "docs")
PO = os.path.join(ROOT, "po")

# Enigma2 plugin: the package folder and the folder that contains it (e2fake imports it as `CamAlert`).
ENIGMA2_PARENT = os.path.join(ROOT, "src")
ENIGMA2 = os.path.join(ENIGMA2_PARENT, "CamAlert")
# Shared plain-Python modules (no Enigma2, Kodi or Home Assistant imports), reused by the Kodi add-on.
SHARED = ENIGMA2
SHARED_MODULES = ("logic.py", "devices.py", "camlog.py")

# Kodi add-on and repository add-on.
KODI = os.path.join(ROOT, "kodi")
KODI_ADDON = os.path.join(KODI, "service.camalert")
KODI_REPO_ADDON = os.path.join(KODI, "repository.camalert")
KODI_LIB = os.path.join(KODI_ADDON, "resources", "lib", "camalert")

# Home Assistant integration, blueprints.
HA = os.path.join(ROOT, "custom_components", "camalert")
BLUEPRINTS = os.path.join(ROOT, "homeassistant", "blueprints")

# Fixtures of the compatibility tests.
E2_API_FIXTURES = os.path.join(TESTS, "compat", "fixtures", "e2api")
KODI_API_FIXTURES = os.path.join(TESTS, "compat", "fixtures", "kodi_api")


def add(*paths):
    """Puts paths in front of sys.path (once)."""
    for p in reversed(paths):
        if p not in sys.path:
            sys.path.insert(0, p)


def shared():
    """Makes the shared modules importable as top-level modules (`import logic`)."""
    add(SHARED)


def tools():
    add(TOOLS)


def kodi_package(name="camalert"):
    """Imports the Kodi add-on package from the source tree (not from a built zip, so coverage sees the real files).

    The add-on gets the shared modules at build time (tools/build_kodi.py); here the package path also lists the
    shared folder, after the add-on's own folder, so `camalert.logic` is the shared logic.py. Install the Kodi stubs
    first. Returns the package module."""
    for f in SHARED_MODULES:
        if os.path.exists(os.path.join(KODI_LIB, f)):
            raise RuntimeError("stale copy of %s in %s: delete it (the build copies the shared one)" % (f, KODI_LIB))
    for mod in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
        del sys.modules[mod]
    spec = importlib.util.spec_from_file_location(name, os.path.join(KODI_LIB, "__init__.py"),
                                                  submodule_search_locations=[KODI_LIB, SHARED])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[name] = pkg
    spec.loader.exec_module(pkg)
    return pkg


def kodi_module(sub, name="camalert"):
    if name not in sys.modules:
        kodi_package(name)
    return importlib.import_module("%s.%s" % (name, sub))
