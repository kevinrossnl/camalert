"""The Kodi add-on only uses Kodi Python API that exists in Kodi 19 (Matrix), 20 (Nexus), 21 (Omega) and 22 (Piers).

tests/compat/fixtures/kodi_api/<major>.json is made by tools/kodi_api_snapshot.py from Kodistubs of that release
(generated from Kodi's API documentation). The add-on sources are read with ast, nothing is imported, so this
also covers code paths the functional tests (tests/test_kodi.py) do not reach. Checked:
  - every xbmc*.name exists (function, class or constant);
  - calls of module functions, constructors and methods on objects made from Kodi classes, including
    self.method() in add-on classes that subclass a Kodi class, fit the parameter list of that version.
"""
import ast
import json
import os
import re
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ADDON = os.path.join(ROOT, "kodi", "service.camalert")
FIXTURES = os.path.join(HERE, "fixtures", "kodi_api")
VERSIONS = (19, 20, 21, 22)
# Known problems with an open issue: "file:line-free message" -> issue. A stale entry fails the test.
KNOWN = {
    "kodi/service.camalert/resources/lib/camalert/display.py xbmcgui.ControlLabel() arguments": "#25",
}
# xbmc.python version shipped with each Kodi major (addon.xml <import addon="xbmc.python" version=...>)
XBMC_PYTHON = {19: "3.0.0", 20: "3.0.1", 21: "3.0.1", 22: "3.0.1"}


def load(version):
    with open(os.path.join(FIXTURES, "%d.json" % version), encoding="utf-8") as f:
        return json.load(f)["modules"]


def checker(params):
    args = [p[:-1] + "=None" if p.endswith("=") else p for p in params]
    ns = {}
    exec("def f(%s):\n    pass\n" % ", ".join(args), ns)  # noqa: S102 - built from our fixture
    return ns["f"]


def fits(params, call, bound=True):
    """True if the call (ast.Call) can bind to the parameter list. Calls with *args / **kwargs always fit."""
    if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
        return True
    n = len(call.args) + (1 if bound else 0)
    try:
        checker(params)(*range(n), **{k.arg: 0 for k in call.keywords})
        return True
    except TypeError:
        return False


def methods_of(api, mod, cls):
    """Methods of a Kodi class including its Kodi base classes."""
    info = api[mod]["classes"].get(cls)
    if info is None:
        return {}
    out = {}
    for b in info["bases"]:
        out.update(methods_of(api, mod, b))
    out.update(info["methods"])
    return out


def sources():
    for d, _dirs, names in os.walk(ADDON):
        for n in names:
            if n.endswith(".py"):
                p = os.path.join(d, n)
                with open(p, encoding="utf-8") as f:
                    yield os.path.relpath(p, ROOT), ast.parse(f.read())


def kodi_ref(node, modules):
    """('xbmcgui', 'Dialog') for the expression xbmcgui.Dialog, else None."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in modules:
        return node.value.id, node.attr
    return None


def problems(api):
    found = []
    modules = set(api)
    for rel, tree in sources():
        # names imported as modules (import xbmc / import xbmcgui)
        imported = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods = modules & imported
        for node in ast.walk(tree):
            ref = kodi_ref(node, mods)
            if ref:
                m = api[ref[0]]
                if ref[1] not in m["functions"] and ref[1] not in m["classes"] and ref[1] not in m["constants"]:
                    found.append("%s:%d %s.%s does not exist" % (rel, node.lineno, ref[0], ref[1]))
            if not isinstance(node, ast.Call):
                continue
            ref = kodi_ref(node.func, mods)
            if ref and ref[1] in api[ref[0]]["functions"]:
                if not fits(api[ref[0]]["functions"][ref[1]], node, bound=False):
                    found.append("%s:%d %s.%s() arguments" % (rel, node.lineno, ref[0], ref[1]))
            elif ref and ref[1] in api[ref[0]]["classes"]:
                init = methods_of(api, ref[0], ref[1]).get("__init__")
                if init and not fits(init, node):
                    found.append("%s:%d %s.%s() arguments" % (rel, node.lineno, ref[0], ref[1]))
            # xbmcgui.Dialog().notification(...)
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Call):
                ref = kodi_ref(f.value.func, mods)
                if ref and ref[1] in api[ref[0]]["classes"]:
                    meths = methods_of(api, ref[0], ref[1])
                    if f.attr not in meths:
                        found.append("%s:%d %s.%s.%s does not exist" % (rel, node.lineno, ref[0], ref[1], f.attr))
                    elif not fits(meths[f.attr], node):
                        found.append("%s:%d %s.%s.%s() arguments" % (rel, node.lineno, ref[0], ref[1], f.attr))
        found += subclass_problems(rel, tree, api, mods)
        found += variable_problems(rel, tree, api, mods)
    return found


def subclass_problems(rel, tree, api, mods):
    """self.x() in classes derived from a Kodi class: x must be our own method or one of the Kodi class."""
    found = []
    classes = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}

    def own_methods(cls):
        out = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
        for b in cls.bases:
            if isinstance(b, ast.Name) and b.id in classes:
                out |= own_methods(classes[b.id])
        return out

    def kodi_base(cls):
        for b in cls.bases:
            ref = kodi_ref(b, mods)
            if ref:
                return ref
            if isinstance(b, ast.Name) and b.id in classes:
                r = kodi_base(classes[b.id])
                if r:
                    return r
        return None

    for cls in classes.values():
        base = kodi_base(cls)
        if not base:
            continue
        kodi = methods_of(api, *base)
        own = own_methods(cls)
        for node in ast.walk(cls):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                    isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
                name = node.func.attr
                if name in own:
                    continue
                if name not in kodi:
                    # attribute holding a callable (self.on_settings = ...) is fine
                    assigned = any(isinstance(t, ast.Attribute) and t.attr == name for a in ast.walk(cls)
                                   if isinstance(a, ast.Assign) for t in a.targets)
                    if not assigned:
                        found.append("%s:%d self.%s() is not a method of %s.%s" % (rel, node.lineno, name, *base))
                elif not fits(kodi[name], node):
                    found.append("%s:%d self.%s() arguments (%s.%s)" % (rel, node.lineno, name, *base))
    return found


def variable_problems(rel, tree, api, mods):
    """x = xbmcgui.ListItem(...); x.method(...) inside one function."""
    found = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        types_ = {}
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                ref = kodi_ref(node.value.func, mods)
                if ref and ref[1] in api[ref[0]]["classes"]:
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            types_[t.id] = ref
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                    isinstance(node.func.value, ast.Name) and node.func.value.id in types_:
                ref = types_[node.func.value.id]
                meths = methods_of(api, *ref)
                if node.func.attr not in meths:
                    found.append("%s:%d %s.%s.%s does not exist" % (rel, node.lineno, ref[0], ref[1], node.func.attr))
                elif not fits(meths[node.func.attr], node):
                    found.append("%s:%d %s.%s.%s() arguments" % (rel, node.lineno, ref[0], ref[1], node.func.attr))
    return found


class TestKodiApiVersions(unittest.TestCase):
    def test_addon_uses_only_existing_api(self):
        seen = set()
        for v in VERSIONS:
            with self.subTest(kodi=v):
                found = []
                for p in problems(load(v)):
                    key = re.sub(r":\d+ ", " ", p)
                    if key in KNOWN:
                        seen.add(key)
                    else:
                        found.append(p)
                self.assertEqual(found, [])
        self.assertEqual(sorted(set(KNOWN) - seen), [], "fixed: remove these entries from KNOWN")

    def test_checker_finds_removed_api(self):
        """Self test: xbmc.translatePath was removed in Kodi 20, so it must be reported there."""
        api = load(20)
        tree = ast.parse("import xbmc\nxbmc.translatePath('special://temp/')\n")
        mods = {"xbmc"}
        hits = [n for n in ast.walk(tree) if kodi_ref(n, mods) and kodi_ref(n, mods)[1] not in
                api["xbmc"]["functions"]]
        self.assertTrue(hits)
        self.assertIn("translatePath", load(19)["xbmc"]["functions"])

    def test_checker_finds_wrong_arguments(self):
        api = load(21)
        call = ast.parse("xbmcgui.Dialog().notification('a', 'b', 'c', 1, True, 'too many')").body[0].value
        self.assertFalse(fits(methods_of(api, "xbmcgui", "Dialog")["notification"], call))

    def test_addon_xml_python_requirement(self):
        """xbmc.python 3.0.0 = Kodi 19+; a higher requirement would lock out older Kodi versions."""
        root = ET.parse(os.path.join(ADDON, "addon.xml")).getroot()
        req = {i.get("addon"): i.get("version") for i in root.iter("import")}
        self.assertIn("xbmc.python", req)
        lowest = min(VERSIONS)
        self.assertLessEqual(tuple(map(int, req["xbmc.python"].split("."))),
                             tuple(map(int, XBMC_PYTHON[lowest].split("."))))


if __name__ == "__main__":
    unittest.main()
