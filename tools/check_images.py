#!/usr/bin/env python3
"""Image privacy check (#8): no metadata in the images of the repository.

    check_images.py [root]          fails (exit 1) when an image carries metadata
    check_images.py --strip FILE..  removes the metadata in place (lossless: pixels are not touched)

PNG: only the chunks needed to draw the picture are allowed (IHDR PLTE IDAT IEND tRNS gAMA cHRM sRGB sBIT bKGD pHYs);
text (tEXt zTXt iTXt), EXIF (eXIf), time (tIME), ICC profiles (iCCP) and anything else are refused.
JPEG: only APP0 (JFIF) and APP14 (Adobe) application segments; EXIF/XMP (APP1), ICC (APP2), IPTC (APP13), other APPn
and comments (COM) are refused. GIF comment/application extensions and WebP EXIF/XMP chunks are refused too.
Also refused: files that look like an image by name but are not one. (Words in the pixels cannot be checked here:
compressed image data would give false hits; check_private.py covers text files.)

What this cannot see (the contributor checklist in docs/dev/privacy.md covers it): real camera pictures, faces,
licence plates, house numbers, real camera or channel names, TV programmes in the picture.
Pure Python 3.8+, no Pillow. Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import os
import struct
import subprocess
import sys

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp")
PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_OK = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"sBIT", b"bKGD", b"pHYs"}
JPEG_APP_OK = {0xE0, 0xEE}  # APP0 (JFIF), APP14 (Adobe colour transform)
JPEG_NAMES = {0xE1: "EXIF/XMP (APP1)", 0xE2: "ICC profile (APP2)", 0xED: "IPTC (APP13)", 0xFE: "comment (COM)"}


def _png_chunks(data):
    i = len(PNG_SIG)
    while i + 8 <= len(data):
        n = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        yield kind, data[i:i + 12 + n]
        i += 12 + n
        if kind == b"IEND":
            break


def _jpeg_segments(data):
    """(marker, bytes) of every segment before the image data; the last item is (None, rest from SOS on)."""
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            raise ValueError("broken JPEG")
        marker = data[i + 1]
        if marker == 0xDA or marker == 0xD9:
            yield None, data[i:]
            return
        n = struct.unpack(">H", data[i + 2:i + 4])[0]
        yield marker, data[i:i + 2 + n]
        i += 2 + n
    raise ValueError("broken JPEG")


def _gif_problems(data):
    out = []
    if b"\x21\xfe" in data:
        out.append("comment extension")
    if b"\x21\xff" in data and b"NETSCAPE2.0" not in data:
        out.append("application extension")
    return out


def _webp_chunks(data):
    i = 12
    while i + 8 <= len(data):
        kind = data[i:i + 4]
        n = struct.unpack("<I", data[i + 4:i + 8])[0]
        yield kind
        i += 8 + n + (n & 1)


def metadata(data):
    """List of metadata found in one image (empty = clean). Raises ValueError for something that is no image."""
    if data.startswith(PNG_SIG):
        return sorted({"PNG chunk %s" % k.decode("latin1") for k, _ in _png_chunks(data) if k not in PNG_OK})
    if data[:2] == b"\xff\xd8":
        out = []
        for marker, _ in _jpeg_segments(data):
            if marker is not None and (0xE0 <= marker <= 0xEF or marker == 0xFE) and marker not in JPEG_APP_OK:
                out.append("JPEG " + JPEG_NAMES.get(marker, "APP%d" % (marker - 0xE0)))
        return sorted(set(out))
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ["GIF " + x for x in _gif_problems(data)]
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return sorted({"WebP chunk %s" % k.decode("latin1").strip() for k in _webp_chunks(data)
                       if k in (b"EXIF", b"XMP ", b"ICCP")})
    raise ValueError("not a PNG, JPEG, GIF or WebP image")


def strip(data):
    """The same image without metadata (PNG and JPEG; pixels and compressed data unchanged)."""
    if data.startswith(PNG_SIG):
        return PNG_SIG + b"".join(raw for k, raw in _png_chunks(data) if k in PNG_OK)
    if data[:2] == b"\xff\xd8":
        out = [data[:2]]
        for marker, raw in _jpeg_segments(data):
            if marker is None or not ((0xE0 <= marker <= 0xEF or marker == 0xFE) and marker not in JPEG_APP_OK):
                out.append(raw)
        return b"".join(out)
    raise ValueError("can only strip PNG and JPEG")


def files(root):
    try:
        out = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard"], cwd=root).decode()
        names = out.splitlines()
    except (subprocess.CalledProcessError, OSError):
        names = [os.path.relpath(os.path.join(d, n), root) for d, _, ns in os.walk(root) if "/.git" not in d for n in ns]
    return sorted(n for n in names if n.lower().endswith(IMAGE_EXT) and os.path.isfile(os.path.join(root, n)))


def problems(root):
    found = []
    for rel in files(root):
        data = open(os.path.join(root, rel), "rb").read()
        try:
            found += ["%s: %s" % (rel, m) for m in metadata(data)]
        except ValueError as e:
            found.append("%s: %s" % (rel, e))
    return found


def main(argv):
    if argv[:1] == ["--strip"]:
        for path in argv[1:]:
            data = open(path, "rb").read()
            clean = strip(data)
            if clean != data:
                open(path, "wb").write(clean)
            print("%s: %d -> %d bytes" % (path, len(data), len(clean)))
        return 0
    root = argv[0] if argv else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    p = problems(root)
    for x in p:
        print("IMAGE?", x)
    print("image check: %d images, %d problems" % (len(files(root)), len(p)))
    return 1 if p else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
