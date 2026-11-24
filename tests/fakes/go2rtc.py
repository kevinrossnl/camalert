#!/usr/bin/env python3
"""Fake go2rtc with neutral demo cameras: solid-colour test frames, never a real picture (#32, screenshots #47).

    python3 tests/fakes/go2rtc.py [--host 127.0.0.1] [--port 1984] [--unreachable driveway]

Answers what CamAlert asks go2rtc for:
    GET /api/streams                      {"front_door": {...}, "garden": {...}, ...}
    GET /api/frame.jpeg?src=<name>[&width=N]  a solid-colour 16:9 frame (JPEG with Pillow, PNG without) or HTTP 500
                                          for the cameras given with --unreachable ("camera not reachable" tiles)
Anything else (live streams) answers 404. Also usable in tests: FakeGo2rtc(...).start() on a random port.
Plain Python 3.8+ (Pillow optional), no network access. Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import argparse
import io
import json
import struct
import threading
import zlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

# neutral names and calm colours (Okabe-Ito based, darkened), one per camera
CAMERAS = {"front_door": (0, 92, 140), "garden": (0, 110, 80), "driveway": (150, 100, 0), "back_door": (120, 60, 100)}


def png_frame(width, height, rgb):
    """A solid-colour PNG with a slightly lighter frame line (pure Python)."""
    light = bytes(min(255, c + 40) for c in rgb)
    plain = bytes(rgb)
    border = max(2, width // 160)
    edge = b"\x00" + light * width
    body = b"\x00" + light * border + plain * (width - 2 * border) + light * border
    raw = b"".join(edge if y < border or y >= height - border else body for y in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def frame(width, rgb):
    """(content type, bytes) of a 16:9 test frame."""
    width = max(64, min(int(width or 640), 1920))
    height = width * 9 // 16
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return "image/png", png_frame(width, height, rgb)
    img = Image.new("RGB", (width, height), rgb)
    d = ImageDraw.Draw(img)
    light = tuple(min(255, c + 40) for c in rgb)
    b = max(2, width // 160)
    d.rectangle((0, 0, width - 1, height - 1), outline=light, width=b)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)  # Pillow writes JFIF only, no EXIF
    return "image/jpeg", out.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "go2rtc-fake"

    def log_message(self, *args):
        pass

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        q = parse_qs(url.query)
        cams = self.server.cameras
        if url.path == "/api/streams":
            body = {n: {"producers": [{"url": "fake://%s" % n}], "consumers": []} for n in cams}
            return self._send(200, "application/json", json.dumps(body).encode())
        if url.path == "/api/frame.jpeg":
            name = (q.get("src") or [""])[0]
            if name not in cams or name in self.server.unreachable:
                return self._send(500, "text/plain", b"streams: no producers")
            ctype, data = frame((q.get("width") or [640])[0], cams[name])
            return self._send(200, ctype, data)
        self._send(404, "text/plain", b"not found")


class FakeGo2rtc(HTTPServer):
    def __init__(self, host="127.0.0.1", port=0, cameras=None, unreachable=()):
        HTTPServer.__init__(self, (host, port), Handler)
        self.cameras = dict(cameras or CAMERAS)
        self.unreachable = set(unreachable)

    @property
    def url(self):
        return "http://%s:%d" % self.server_address[:2]

    def start(self):
        threading.Thread(target=self.serve_forever, daemon=True).start()
        return self


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1984)
    ap.add_argument("--unreachable", default="", help="comma separated camera names that fail")
    a = ap.parse_args()
    srv = FakeGo2rtc(a.host, a.port, unreachable=[x for x in a.unreachable.split(",") if x])
    print("fake go2rtc on %s with %s" % (srv.url, ", ".join(sorted(srv.cameras))))
    srv.serve_forever()
