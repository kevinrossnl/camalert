#!/usr/bin/env python3
"""Writes a JSON snapshot of the Kodi Python API (xbmc, xbmcgui, xbmcaddon, xbmcvfs) of one Kodi version.

    kodi_api_snapshot.py <unpacked Kodistubs dir> <kodi major> > tests/compat/fixtures/kodi_api/<major>.json

Kodistubs (https://github.com/romanvm/Kodistubs, on PyPI as `Kodistubs==<major>.*`) are generated from Kodi's own
API documentation for each release. Only the stub sources are parsed (ast), nothing is executed. The snapshot is
used by tests/compat/test_kodi_versions.py to check that the add-on only uses API that exists in Kodi 19-22.
Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import ast
import json
import os
import sys
import warnings

MODULES = ("xbmc", "xbmcgui", "xbmcaddon", "xbmcvfs")


def params(fn):
    a = fn.args
    names = [x.arg for x in getattr(a, "posonlyargs", [])] + [x.arg for x in a.args]
    defaults = len(a.defaults)
    out = [n + ("=" if i >= len(names) - defaults else "") for i, n in enumerate(names)]
    if a.vararg:
        out.append("*" + a.vararg.arg)
    out += [k.arg + "=" for k in a.kwonlyargs]
    if a.kwarg:
        out.append("**" + a.kwarg.arg)
    return out


def module_api(path):
    with open(path, encoding="utf-8") as f:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # invalid escape sequences in the stubs' docstrings
            tree = ast.parse(f.read())
    out = {"functions": {}, "classes": {}, "constants": []}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out["functions"][node.name] = params(node)
        elif isinstance(node, ast.ClassDef):
            methods = {}
            for n in node.body:
                if isinstance(n, ast.FunctionDef):
                    methods[n.name] = params(n)
            out["classes"][node.name] = {"bases": [getattr(b, "id", getattr(b, "attr", "")) for b in node.bases],
                                         "methods": methods}
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            out["constants"] += [t.id for t in targets if isinstance(t, ast.Name) and not t.id.startswith("_")]
    out["constants"].sort()
    return out


def find(root, mod):
    for p in (os.path.join(root, mod + ".py"), os.path.join(root, mod, "__init__.py")):
        if os.path.exists(p):
            return p
    raise SystemExit("%s not found in %s" % (mod, root))


def main(argv):
    if len(argv) != 3:
        sys.stderr.write(__doc__)
        return 2
    snap = {"kodi": int(argv[2]), "source": "Kodistubs %s" % argv[2], "modules": {}}
    for mod in MODULES:
        snap["modules"][mod] = module_api(find(argv[1], mod))
    json.dump(snap, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
