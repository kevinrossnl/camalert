#!/usr/bin/env python3
# Builds an opkg feed (Packages + Packages.gz) from .ipk files. Copyright (C) 2026 CamAlert developers, GPL v2.
# Usage: build_feed.py <folder with .ipk files>   (the folder is then published as-is, e.g. on GitHub Pages)
#        build_feed.py <folder> --index <template> --owner <github owner>
#            also writes <folder>/index.html, the start page of the site (#80), from the template
#            (.github/pages/index.html); run it after the Kodi repository was copied to <folder>/kodi/
import glob
import gzip
import hashlib
import io
import os
import re
import sys
import tarfile


def ar_members(blob):
    if not blob.startswith(b"!<arch>\n"):
        raise ValueError("not an ar archive")
    pos, out = 8, {}
    while pos + 60 <= len(blob):
        hdr = blob[pos:pos + 60]
        name = hdr[:16].decode().strip().rstrip("/")
        size = int(hdr[48:58].decode().strip())
        out[name] = blob[pos + 60:pos + 60 + size]
        pos += 60 + size + (size % 2)
    return out


def control_of(blob):
    with tarfile.open(fileobj=io.BytesIO(ar_members(blob)["control.tar.gz"]), mode="r:gz") as t:
        for m in t.getmembers():
            if m.name.lstrip("./") == "control":
                return t.extractfile(m).read().decode("utf-8").strip()
    raise ValueError("no control file")


def packages(folder):
    entries = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".ipk"):
            continue
        blob = open(os.path.join(folder, name), "rb").read()
        entries.append("%s\nFilename: %s\nSize: %d\nMD5Sum: %s\nSHA256sum: %s\n" % (
            control_of(blob), name, len(blob), hashlib.md5(blob).hexdigest(), hashlib.sha256(blob).hexdigest()))
    return "\n".join(entries)


def build(folder):
    text = packages(folder)
    with open(os.path.join(folder, "Packages"), "w", encoding="utf-8") as f:
        f.write(text)
    with gzip.open(os.path.join(folder, "Packages.gz"), "wb") as f:
        f.write(text.encode("utf-8"))
    return text


def write_index(folder, template, owner):
    """Fill the start page template: @OWNER@, @VERSION@ (of the .ipk in the feed) and @KODI_REPO_ZIP@ (the Kodi
    repository zip under kodi/repository.camalert/). Fails when a value is missing or a placeholder is left."""
    versions = sorted({re.search(r"^Version: (\S+)$", control_of(open(p, "rb").read()), re.M).group(1)
                       for p in glob.glob(os.path.join(folder, "*.ipk"))})
    zips = sorted(glob.glob(os.path.join(folder, "kodi", "repository.camalert", "repository.camalert-*.zip")))
    if len(versions) != 1 or len(zips) != 1 or not re.match(r"^[A-Za-z0-9-]+$", owner or ""):
        raise ValueError("need one .ipk, one Kodi repository zip and a GitHub owner: %s %s %r"
                         % (versions, zips, owner))
    html = open(template, encoding="utf-8").read()
    for key, value in (("@OWNER@", owner), ("@VERSION@", versions[0]),
                       ("@KODI_REPO_ZIP@", os.path.basename(zips[0]))):
        html = html.replace(key, value)
    left = re.findall(r"@[A-Z_]+@", html)
    if left:
        raise ValueError("placeholders left in %s: %s" % (template, left))
    path = os.path.join(folder, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


if __name__ == "__main__":
    args = sys.argv[1:]
    opts = {}
    for name in ("--index", "--owner"):
        if name in args:
            i = args.index(name)
            opts[name] = args[i + 1]
            del args[i:i + 2]
    out = args[0] if args else "dist"
    print(build(out))
    if "--index" in opts:
        print(write_index(out, opts["--index"], opts.get("--owner")))
