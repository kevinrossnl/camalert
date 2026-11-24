#!/usr/bin/env python3
"""Writes a JSON snapshot of the Enigma2 Python API that CamAlert relies on, read from an image's enigma2 sources.

    e2_api_snapshot.py <enigma2 python dir> <name> "<source description>" > tests/enigma2/harness/fixtures/e2api/<name>.json

<enigma2 python dir> is `lib/python` of an enigma2 checkout (openATV, OpenPLi, OpenBH, ...) or
`usr/lib/enigma2/python` of an installed image. Parsing is text based (regular expressions), so it also works for
Python 2 sources (DreamOS). Nothing is imported or executed. The snapshot feeds the fake Enigma2 modules in
tests/enigma2/harness/e2fake.py, so the plugin is tested against the real method names and signatures of each image.
Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import json
import os
import re
import sys

# Classes whose methods (including inherited ones) the plugin calls or that it subclasses.
CLASSES = ["InfoBar", "MoviePlayer", "ChannelSelection", "Navigation", "Standby", "Screen", "ConfigListScreen",
           "MessageBox", "ChoiceBox", "VirtualKeyBoard", "ActionMap", "Label", "Pixmap", "StaticText", "MenuList",
           "ScrollLabel", "PluginDescriptor", "ConfigSubsection", "ConfigYesNo", "ConfigText", "ConfigInteger",
           "ConfigSelection", "ConfigSelectionNumber", "ConfigClock", "ConfigPassword", "ConfigNumber", "Session"]
# Module level names the plugin imports.
MODULES = {
    "Screens/Standby.py": "Screens.Standby",
    "Tools/Notifications.py": "Tools.Notifications",
    "Tools/Directories.py": "Tools.Directories",
    "Components/config.py": "Components.config",
    "Components/Language.py": "Components.Language",
}
CLASS_RE = re.compile(r"^class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:", re.M)
DEF_RE = re.compile(r"^([ \t]+)def\s+(\w+)\s*\(((?:[^()]|\([^()]*\))*)\)\s*:", re.M)
TOP_RE = re.compile(r"^(?:def\s+(\w+)\s*\(((?:[^()]|\([^()]*\))*)\)|(\w+)\s*=|class\s+(\w+))", re.M)


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def params(text):
    """'self, list, session = None, *args' -> ['self', 'list', 'session=', '*args'] (defaults reduced to '=')."""
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    res = []
    for p in out:
        p = p.strip()
        if not p:
            continue
        name = re.split(r"[=:]", p, maxsplit=1)[0].strip()
        res.append(name + "=" if "=" in p and not name.startswith("*") else name)
    return res


def scan(root):
    """All classes in the tree: name -> {"bases": [...], "methods": {name: params}, "attrs": [...]}."""
    classes = {}
    for d, _dirs, names in os.walk(root):
        if re.search(r"/Plugins/[^/]+", d.replace("\\", "/")):
            continue  # plugins (Extensions, SystemPlugins) are not part of the image API; Plugins/Plugin.py is
        for n in names:
            if not n.endswith(".py"):
                continue
            text = read(os.path.join(d, n))
            starts = [(m.start(), m) for m in CLASS_RE.finditer(text)]
            for i, (pos, m) in enumerate(starts):
                end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
                # a class ends at the next line that starts without indentation (not a comment / blank / decorator)
                body_end = end
                for ln in re.finditer(r"^(?=[^\s#@)\]}])", text[m.end():end], re.M):
                    body_end = m.end() + ln.start()
                    break
                body = text[m.end():body_end]
                bases = [b.strip().split(".")[-1] for b in (m.group(2) or "").split(",") if b.strip()]
                methods = {}
                indent = None
                for dm in DEF_RE.finditer(body):
                    if indent is None:
                        indent = dm.group(1)
                    if dm.group(1) == indent:
                        methods[dm.group(2)] = params(dm.group(3))
                attrs = sorted(set(re.findall(r"^%s(\w+)\s*=" % re.escape(indent or "\t"), body, re.M)))
                provides = sorted(set(re.findall(r"self\[[\"'](\w+)[\"']\]\s*=(?!=)", body)))
                name = m.group(1)
                entry = classes.get(name)
                # prefer the definition with most methods (some names exist twice, e.g. compatibility shims)
                if entry is None or len(methods) > len(entry["methods"]):
                    classes[name] = {"bases": bases, "methods": methods, "attrs": attrs, "provides": provides,
                                     "file": os.path.relpath(os.path.join(d, n), root).replace("\\", "/")}
    return classes


def resolve(classes, name, seen=None):
    """Methods, class attributes and screen components (self["x"] = ...) including inherited ones."""
    seen = seen or set()
    if name in seen or name not in classes:
        return {}, set(), set()
    seen.add(name)
    methods, attrs, provides = {}, set(), set()
    for b in reversed(classes[name]["bases"]):
        m, a, p = resolve(classes, b, seen)
        methods.update(m)
        attrs |= a
        provides |= p
    methods.update(classes[name]["methods"])
    attrs |= set(classes[name]["attrs"])
    provides |= set(classes[name]["provides"])
    return methods, attrs, provides


def module_names(path):
    text = read(path)
    names = {}
    for m in TOP_RE.finditer(text):
        if m.group(1):
            names[m.group(1)] = params(m.group(2))
        elif m.group(3):
            names[m.group(3)] = None
        elif m.group(4):
            names[m.group(4)] = "class"
    return names


def skin_attributes(root):
    """Widget attributes the skin parser understands."""
    text = read(os.path.join(root, "skin.py"))
    names = set()
    block = re.search(r"^class AttributeParser.*?(?=^class |\Z)", text, re.M | re.S)
    if block:  # newer images: one method per attribute
        names |= set(re.findall(r"^\tdef (\w+)\(self, value\)", block.group(0), re.M))
        names |= set(re.findall(r"^    def (\w+)\(self, value\)", block.group(0), re.M))
    # older images (DreamOS): if/elif chain in applySingleAttribute
    for m in re.finditer(r"attrib\s*==\s*['\"](\w+)['\"]", text):
        names.add(m.group(1))
    for m in re.finditer(r"attrib\s+in\s+\(([^)]*)\)", text):
        names |= set(re.findall(r"['\"](\w+)['\"]", m.group(1)))
    # attributes handled by the generic widget code, independent of the parser
    names |= {"name", "source", "render"}
    return sorted(names)


def snapshot(root, name, source):
    classes = scan(root)
    out = {"name": name, "source": source, "classes": {}, "modules": {}, "skin_attributes": skin_attributes(root)}
    for c in CLASSES:
        if c not in classes:
            continue
        methods, attrs, provides = resolve(classes, c)
        out["classes"][c] = {"file": classes[c]["file"], "methods": dict(sorted(methods.items())),
                             "attrs": sorted(attrs), "provides": sorted(provides)}
    for rel, mod in MODULES.items():
        p = os.path.join(root, rel)
        if os.path.exists(p):
            out["modules"][mod] = dict(sorted(module_names(p).items()))
    return out


def main(argv):
    if len(argv) != 4:
        sys.stderr.write(__doc__)
        return 2
    json.dump(snapshot(argv[1], argv[2], argv[3]), sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
