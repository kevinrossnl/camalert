#!/usr/bin/env python3
# Builds enigma2-plugin-extensions-camalert_<version>_all.ipk without opkg tools.
# Copyright (C) 2026 CamAlert developers, GPL v2.
import io
import os
import re
import sys
import tarfile
import time

sys.path.insert(0, os.path.dirname(__file__))
from msgfmt import make_mo, parse_po  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src", "CamAlert")
DEST = "usr/lib/enigma2/python/Plugins/Extensions/CamAlert"
PKG = "enigma2-plugin-extensions-camalert"


def version():
    return re.search(r'__version__ = "([^"]+)"', open(os.path.join(SRC, "__init__.py")).read()).group(1)


def add(tar, name, data, mode=0o644):
    info = tarfile.TarInfo(name)
    info.size, info.mode, info.mtime, info.uid, info.gid = len(data), mode, int(time.time()), 0, 0
    tar.addfile(info, io.BytesIO(data))


def add_dir(tar, name):
    info = tarfile.TarInfo(name)
    info.type, info.mode, info.mtime = tarfile.DIRTYPE, 0o755, int(time.time())
    tar.addfile(info)


def targz(builder):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.GNU_FORMAT) as tar:
        builder(tar)
    return buf.getvalue()


def data(tar):
    parts = DEST.split("/")
    for i in range(1, len(parts) + 1):
        add_dir(tar, "./" + "/".join(parts[:i]))
    for f in sorted(os.listdir(SRC)):
        if f.endswith((".py", ".png")):
            add(tar, "./%s/%s" % (DEST, f), open(os.path.join(SRC, f), "rb").read())
    add_dir(tar, "./%s/locale" % DEST)
    for po in sorted(os.listdir(os.path.join(ROOT, "po"))):
        if po.endswith(".po"):
            lang = po[:-3]
            add_dir(tar, "./%s/locale/%s" % (DEST, lang))
            add_dir(tar, "./%s/locale/%s/LC_MESSAGES" % (DEST, lang))
            mo = make_mo(parse_po(open(os.path.join(ROOT, "po", po), encoding="utf-8").read()))
            add(tar, "./%s/locale/%s/LC_MESSAGES/CamAlert.mo" % (DEST, lang), mo)


CONTROL = """Package: %(pkg)s
Version: %(ver)s
Description: CamAlert - show IP cameras (via go2rtc) on your TV
 Shows a camera as a photo window, switches to the live stream or shows a
 notification when called over HTTP (for example from Home Assistant on motion).
Section: extra
Priority: optional
Maintainer: CamAlert developers
License: GPL-2.0-only
Architecture: all
Homepage: https://github.com/CAMALERT_OWNER/camalert
Depends: enigma2, python3-twisted-web
Source: https://github.com/CAMALERT_OWNER/camalert
"""
POSTINST = """#!/bin/sh
echo "CamAlert installed. Restart the GUI (Menu > Standby > Restart GUI) and open CamAlert in the plugin menu."
exit 0
"""
POSTRM = """#!/bin/sh
rm -rf /usr/lib/enigma2/python/Plugins/Extensions/CamAlert
exit 0
"""


def control(tar, owner):
    add(tar, "./control", (CONTROL % {"pkg": PKG, "ver": version()}).replace("CAMALERT_OWNER", owner).encode())
    add(tar, "./postinst", POSTINST.encode(), 0o755)
    add(tar, "./postrm", POSTRM.encode(), 0o755)


def ar(members):
    out = b"!<arch>\n"
    for name, payload in members:
        hdr = "%-16s%-12d%-6d%-6d%-8s%-10d`\n" % (name, int(time.time()), 0, 0, "100644", len(payload))
        out += hdr.encode() + payload + (b"\n" if len(payload) % 2 else b"")
    return out


def build(outdir, owner="kevinrossnl"):
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "%s_%s_all.ipk" % (PKG, version()))
    blob = ar([("debian-binary", b"2.0\n"), ("control.tar.gz", targz(lambda t: control(t, owner))),
               ("data.tar.gz", targz(data))])
    with open(path, "wb") as f:
        f.write(blob)
    return path


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist"),
                os.environ.get("CAMALERT_OWNER", "kevinrossnl")))
