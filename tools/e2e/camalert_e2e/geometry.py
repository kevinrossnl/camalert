"""Screenshot checks without pixel diffs: the fake cameras are solid colours, so each camera is found by its colour
and its bounding box is compared with the geometry from camalert_core.layout (tolerances, no exact pixels)."""
import struct
import zlib

from .fakes import CORE

TOLERANCE = 28        # per colour channel
MARGIN = 0.03         # of the screen width: how far a box may stick out of its expected rectangle
MIN_FILL = 0.75       # the colour must fill at least this part of the expected picture area


class Image(object):
    """width, height and rows of (r, g, b, a) bytes."""

    def __init__(self, width, height, rows, channels):
        self.width, self.height, self.rows, self.channels = width, height, rows, channels

    def pixel(self, x, y):
        c, row = self.channels, self.rows[y]
        p = row[x * c:x * c + c]
        return (p[0], p[1], p[2], p[3] if c == 4 else 255)


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def decode_png(data):
    """8-bit RGB/RGBA, not interlaced (what OpenWebif /grab returns). Pure Python."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, head = 8, [], None
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            head = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    w, h, depth, ctype, _c, _f, interlace = head
    if depth != 8 or ctype not in (2, 6) or interlace:
        raise ValueError("unsupported PNG (depth %d, colour type %d, interlace %d)" % (depth, ctype, interlace))
    bpp = 3 if ctype == 2 else 4
    raw, stride = zlib.decompress(b"".join(idat)), w * bpp
    rows, prev = [], bytearray(stride)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                line[i] = (line[i] + ((line[i - bpp] if i >= bpp else 0) + prev[i]) // 2) & 255
        elif f == 4:
            for i in range(stride):
                line[i] = (line[i] + _paeth(line[i - bpp] if i >= bpp else 0, prev[i],
                                            prev[i - bpp] if i >= bpp else 0)) & 255
        rows.append(bytes(line))
        prev = line
    return Image(w, h, rows, bpp)


def load(data):
    """Image from PNG bytes; Pillow when installed (fast), else the pure decoder."""
    try:
        from PIL import Image as PILImage
        import io
    except ImportError:
        return decode_png(data)
    img = PILImage.open(io.BytesIO(data)).convert("RGBA")
    w, h = img.size
    raw = img.tobytes()
    return Image(w, h, [raw[y * w * 4:(y + 1) * w * 4] for y in range(h)], 4)


def encode_png(width, height, pixel):
    """A small RGBA PNG from pixel(x, y) -> (r, g, b, a); for the fakes and tests."""
    raw = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(width)) for y in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def find(img, rgb, step=2, tol=TOLERANCE):
    """(x0, y0, x1, y1, count) bounding box of the opaque pixels of one colour (sampled every step pixels)."""
    x0 = y0 = 10 ** 9
    x1 = y1 = -1
    count = 0
    r, g, b = rgb
    c = img.channels
    for y in range(0, img.height, step):
        row = img.rows[y]
        for x in range(0, img.width, step):
            i = x * c
            if (abs(row[i] - r) <= tol and abs(row[i + 1] - g) <= tol and abs(row[i + 2] - b) <= tol
                    and (c == 3 or row[i + 3] > 128)):
                count += 1
                x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
    return (x0, y0, x1 + step, y1 + step, count) if count else None


def check_box(img, name, rgb, rect, step=2):
    """(ok, detail): the colour of camera `name` fills the expected rect (x, y, w, h) within the tolerances."""
    box = find(img, rgb, step)
    if box is None:
        return False, "%s: not on screen" % name
    x, y, w, h = rect
    m = int(MARGIN * img.width) + step
    x0, y0, x1, y1, count = box
    inside = x0 >= x - m and y0 >= y - m and x1 <= x + w + m and y1 <= y + h + m
    fill = count * step * step / float(max(1, w * h))
    ok = inside and fill >= MIN_FILL
    return ok, "%s: box %d,%d-%d,%d expected %d,%d %dx%d fill %.0f%%%s" % (
        name, x0, y0, x1, y1, x, y, w, h, 100 * fill, "" if inside else " (outside)")


def _layout():
    import sys
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    from camalert_core import layout
    return layout


def photo_rect(settings, sw, sh):
    """Where the picture of the photo window may be: the window minus nothing (title bar above or below)."""
    x, y, w, h, title = _layout().window_geometry(settings.get("position", "top_right"), settings.get("size", "medium"),
                                                  sw, sh, settings.get("title_size", "normal"))
    return x, y, w, h + title, (w, h)


def check_photo(img, name, rgb, settings):
    x, y, w, h_total, (pw, ph) = photo_rect(settings, img.width, img.height)
    box = find(img, rgb)
    if box is None:
        return False, "%s: not on screen" % name
    m = int(MARGIN * img.width) + 2
    x0, y0, x1, y1, count = box
    inside = x0 >= x - m and y0 >= y - m and x1 <= x + w + m and y1 <= y + h_total + m
    fill = count * 4 / float(pw * ph)
    return inside and fill >= MIN_FILL, "%s: box %d,%d-%d,%d window %d,%d %dx%d fill %.0f%%" % (
        name, x0, y0, x1, y1, x, y, w, h_total, 100 * fill)


def strip_rects(n, settings, sw, sh):
    x, y, w, h, title, tiles = _layout().strip_geometry(n, settings.get("strip_layout", "auto"),
                                                        settings.get("position", "top_right"),
                                                        settings.get("size", "medium"), sw, sh)
    return [(x + tx, y + ty, tw, th) for tx, ty, tw, th in tiles]


def mosaic_rects(n, sw, sh):
    return _layout().grid(n, sw, sh)


def check_tiles(img, names, colours, rects):
    out = [check_box(img, n, colours[n], r) for n, r in zip(names, rects)]
    return all(ok for ok, _ in out), "; ".join(d for _, d in out)


def colours_on_screen(img, colours, min_count=50):
    """Names of the cameras whose colour is clearly visible."""
    return [n for n, rgb in sorted(colours.items()) if (find(img, rgb, 4) or (0, 0, 0, 0, 0))[4] >= min_count]
