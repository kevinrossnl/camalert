#!/usr/bin/env python3
"""Builds the Kodi add-on and the Kodi repository (automatic updates).

    python3 tools/build_kodi.py [outdir] [--repo-url URL]

Writes to outdir (default dist/):
    service.camalert-<version>.zip         the add-on (version = players/enigma2/CamAlert/__init__.py)
    repository.camalert-<rversion>.zip     repository add-on: install once, Kodi then updates CamAlert itself
    kodi-repo/                             tree to host (GitHub Pages): addons.xml, addons.xml.md5, zips and the
                                           <assets> of each add-on (icon, fanart: Kodi fetches them from there)

The shared core (core/camalert_core/, the whole package) is copied into resources/lib/camalert/camalert_core/ and the
doorbell chime (players/enigma2/CamAlert/chime.wav) into resources/media/ at build time.
Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import hashlib
import os
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENIGMA2 = os.path.join(ROOT, "players", "enigma2", "CamAlert")
ADDON = os.path.join(ROOT, "players", "kodi", "service.camalert")
REPO_ADDON = os.path.join(ROOT, "players", "kodi", "repository.camalert")
CORE = os.path.join(ROOT, "core", "camalert_core")
DEFAULT_REPO_URL = "https://kevinrossnl.github.io/camalert/kodi"
STAMP = (2026, 1, 1, 0, 0, 0)  # fixed zip timestamps: same input, same zip


def version():
    return re.search(r'__version__ = "([^"]+)"', open(os.path.join(ENIGMA2, "__init__.py")).read()).group(1)


def addon_xml_text(path, ver=None, repo_url=None):
    text = open(path, encoding="utf-8").read()
    if ver:
        text = re.sub(r'(<addon\b[^>]*\bversion=")[^"]*(")', r"\g<1>%s\2" % ver, text, count=1)
    if repo_url:
        text = text.replace("@REPO_URL@", repo_url.rstrip("/"))
    ET.fromstring(text.encode("utf-8"))  # must stay valid
    return text


def files_of(base):
    out = []
    for d, dirs, files in os.walk(base):
        dirs[:] = sorted(x for x in dirs if x != "__pycache__")
        for f in sorted(files):
            if f.endswith((".pyc", ".pyo")) or f.startswith("."):
                continue
            out.append(os.path.join(d, f))
    return out


def write_zip(path, addon_id, entries):
    """entries: [(name inside addon folder, bytes)]"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            info = zipfile.ZipInfo("%s/%s" % (addon_id, name), STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)


def addon_entries(ver):
    entries = []
    for f in files_of(ADDON):
        rel = os.path.relpath(f, ADDON).replace(os.sep, "/")
        if rel.startswith("resources/lib/camalert/camalert_core/"):
            continue  # stale local copy: the build always takes the core itself
        data = addon_xml_text(f, ver).encode("utf-8") if rel == "addon.xml" else open(f, "rb").read()
        entries.append((rel, data))
    for f in files_of(CORE):
        if f.endswith(".py"):
            rel = os.path.relpath(f, CORE).replace(os.sep, "/")
            entries.append(("resources/lib/camalert/camalert_core/" + rel, open(f, "rb").read()))
    entries.append(("resources/media/chime.wav", open(os.path.join(ENIGMA2, "chime.wav"), "rb").read()))
    entries.append(("LICENSE.txt", open(os.path.join(ROOT, "LICENSE"), "rb").read()))
    return sorted(entries)


def asset_paths(xml_text):
    """The files named in <assets> (icon, fanart, screenshots) of an addon.xml text (#123)."""
    root = ET.fromstring(xml_text.encode("utf-8"))
    return sorted({(e.text or "").strip() for a in root.iter("assets") for e in a if (e.text or "").strip()})


def repo_version():
    return ET.fromstring(open(os.path.join(REPO_ADDON, "addon.xml"), "rb").read()).get("version")


def build(outdir, repo_url=DEFAULT_REPO_URL):
    os.makedirs(outdir, exist_ok=True)
    ver = version()
    addon_zip = os.path.join(outdir, "service.camalert-%s.zip" % ver)
    write_zip(addon_zip, "service.camalert", addon_entries(ver))

    rver = repo_version()
    repo_entries = []
    for f in files_of(REPO_ADDON):
        rel = os.path.relpath(f, REPO_ADDON).replace(os.sep, "/")
        data = addon_xml_text(f, None, repo_url).encode("utf-8") if rel == "addon.xml" else open(f, "rb").read()
        repo_entries.append((rel, data))
    repo_zip = os.path.join(outdir, "repository.camalert-%s.zip" % rver)
    write_zip(repo_zip, "repository.camalert", sorted(repo_entries))

    # tree for GitHub Pages: <url>/addons.xml(.md5), <url>/<id>/<id>-<ver>.zip
    tree = os.path.join(outdir, "kodi-repo")
    if os.path.isdir(tree):
        shutil.rmtree(tree)
    parts = []
    for aid, src, z, xml in (("service.camalert", ADDON, addon_zip,
                              addon_xml_text(os.path.join(ADDON, "addon.xml"), ver)),
                             ("repository.camalert", REPO_ADDON, repo_zip,
                              addon_xml_text(os.path.join(REPO_ADDON, "addon.xml"), None, repo_url))):
        os.makedirs(os.path.join(tree, aid), exist_ok=True)
        shutil.copy(z, os.path.join(tree, aid, os.path.basename(z)))
        for rel in asset_paths(xml):  # Kodi 19+ reads <datadir>/<id>/<asset path> (#123)
            segs = rel.split("/")
            if rel.startswith("/") or ".." in segs:
                raise ValueError("%s: asset outside the add-on: %s" % (aid, rel))
            dest = os.path.join(tree, aid, *segs)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy(os.path.join(src, *segs), dest)
        parts.append(re.sub(r"^<\?xml[^>]*\?>\s*", "", xml.strip()))
    addons = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n%s\n</addons>\n' % "\n".join(parts)
    ET.fromstring(addons.encode("utf-8"))
    with open(os.path.join(tree, "addons.xml"), "w", encoding="utf-8") as f:
        f.write(addons)
    with open(os.path.join(tree, "addons.xml.md5"), "w") as f:
        f.write(hashlib.md5(addons.encode("utf-8")).hexdigest())
    with open(os.path.join(tree, "index.html"), "w") as f:
        f.write("<!DOCTYPE html><title>CamAlert Kodi repository</title><a href=\"%s\">%s</a>\n"
                % ("repository.camalert/" + os.path.basename(repo_zip), os.path.basename(repo_zip)))
    return addon_zip, repo_zip, tree


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    url = DEFAULT_REPO_URL
    if "--repo-url" in args:
        i = args.index("--repo-url")
        url = args[i + 1]
        del args[i:i + 2]
    for p in build(args[0] if args else os.path.join(ROOT, "dist"), url):
        print(p)
