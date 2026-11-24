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
COMPATIBILITY_DOC = os.path.join(DOCS, "dev", "compatibility.md")

# Enigma2 plugin: the package folder and the folder that contains it (e2fake imports it as `CamAlert`).
PLAYERS = os.path.join(ROOT, "players")
ENIGMA2_PARENT = os.path.join(PLAYERS, "enigma2")
ENIGMA2 = os.path.join(ENIGMA2_PARENT, "CamAlert")
PO = os.path.join(ENIGMA2_PARENT, "po")  # Enigma2 translations, generated from core/i18n/
# Shared core (plain Python 3.8+, no Enigma2, Kodi or Home Assistant imports); the builds copy the whole package
# into every player package as `camalert_core`.
CORE_PARENT = os.path.join(ROOT, "core")
CORE = os.path.join(CORE_PARENT, "camalert_core")

# Kodi add-on and repository add-on.
KODI = os.path.join(PLAYERS, "kodi")
KODI_ADDON = os.path.join(KODI, "service.camalert")
KODI_REPO_ADDON = os.path.join(KODI, "repository.camalert")
KODI_LIB = os.path.join(KODI_ADDON, "resources", "lib", "camalert")

# Home Assistant integration, blueprints.
HA = os.path.join(ROOT, "custom_components", "camalert")
BLUEPRINTS = os.path.join(ROOT, "homeassistant", "blueprints")

# End-to-end runner for real devices (#35) and its local, git-ignored files (device profiles, reports).
E2E = os.path.join(TOOLS, "e2e")
E2E_LOCAL_PROFILES = os.path.join(E2E, "devices.local.yaml")
REPORTS = os.path.join(ROOT, "reports")

# Fixtures of the compatibility tests.
E2_API_FIXTURES = os.path.join(TESTS, "enigma2", "harness", "fixtures", "e2api")
KODI_API_FIXTURES = os.path.join(TESTS, "kodi", "fixtures", "kodi_api")
KODI_JSONRPC_FIXTURES = os.path.join(TESTS, "kodi", "fixtures", "jsonrpc")


def add(*paths):
    """Puts paths in front of sys.path (once)."""
    for p in reversed(paths):
        if p not in sys.path:
            sys.path.insert(0, p)


def e2e():
    """Makes the e2e runner importable: `from camalert_e2e import runner`."""
    add(E2E)


def core():
    """Makes the core importable: `from camalert_core import rules`."""
    add(CORE_PARENT)


def core_names(exclude_private=True):
    """{name: module path} of everything defined at module level in the core (for the import checks)."""
    import ast
    out = {}
    for d, dirs, files in os.walk(CORE):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(d, f)
                with open(p, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read())
                for n in tree.body:
                    names = [n.name] if isinstance(n, (ast.FunctionDef, ast.ClassDef)) else \
                        [t.id for t in getattr(n, "targets", []) if isinstance(t, ast.Name)]
                    for name in names:
                        if not (exclude_private and name.startswith("_")):
                            out[name] = p
    return out


def attach_core(package):
    """Registers <package>.camalert_core as the core from the source tree, the way the builds put a copy of it
    into the player package (call after importing the package, before its submodules)."""
    name = package + ".camalert_core"
    for mod in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
        del sys.modules[mod]
    spec = importlib.util.spec_from_file_location(name, os.path.join(CORE, "__init__.py"),
                                                  submodule_search_locations=[CORE])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    setattr(sys.modules[package], "camalert_core", mod)
    return mod


def tools():
    add(TOOLS)


def kodi_package(name="camalert"):
    """Imports the Kodi add-on package from the source tree (not from a built zip, so coverage sees the real files).

    The add-on gets the core at build time (tools/build_kodi.py); here `camalert.camalert_core` is the core from
    the source tree (attach_core). Install the Kodi stubs first. Returns the package module."""
    if os.path.exists(os.path.join(KODI_LIB, "camalert_core")):
        raise RuntimeError("stale copy of camalert_core in %s: delete it (the build copies the core)" % KODI_LIB)
    for mod in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
        del sys.modules[mod]
    spec = importlib.util.spec_from_file_location(name, os.path.join(KODI_LIB, "__init__.py"),
                                                  submodule_search_locations=[KODI_LIB])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[name] = pkg
    spec.loader.exec_module(pkg)
    attach_core(name)
    return pkg


def kodi_module(sub, name="camalert"):
    if name not in sys.modules:
        kodi_package(name)
    return importlib.import_module("%s.%s" % (name, sub))
