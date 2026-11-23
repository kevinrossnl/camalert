#!/usr/bin/env python3
# Builds an opkg feed (Packages + Packages.gz) from .ipk files. Copyright (C) 2026 CamAlert developers, GPL v2.
# Usage: build_feed.py <folder with .ipk files>   (the folder is then published as-is, e.g. on GitHub Pages)
import gzip
import hashlib
import io
import os
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


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "dist"))
