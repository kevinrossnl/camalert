#!/usr/bin/env python3
"""Fake IP camera for tests and the e2e runner (#32): colour-coded snapshots, Foscam CGI and ONVIF PTZ.

    python3 tests/fakes/camera.py [--host 127.0.0.1] [--port 8088] [--index 1]

- Snapshots: GET /snapshot.jpg (also Foscam `cmd=snapPicture2`) answers a solid-colour 16:9 frame with a big
  index number: cam1 red, cam2 green, cam3 blue, ... (COLOURS), so a screenshot can be checked by sampling the
  colour of each tile (colour_of / tile_index). JPEG with Pillow (JFIF only, no EXIF, #8), else PNG.
- Foscam CGI (GET /cgi-bin/CGIProxy.fcgi?cmd=...&usr=admin&pwd=...) and ONVIF (POST, WS-Security digest): every
  accepted call is recorded in MockCamera.calls; a wrong password answers like a real camera does.
Plain Python 3.8+, listens on 127.0.0.1 only by default. Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import argparse
import base64
import hashlib
import io
import re
import struct
import threading
import zlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

# index -> colour; far apart so a sampled pixel maps back to exactly one camera
COLOURS = {1: (200, 30, 30), 2: (30, 160, 60), 3: (30, 70, 200), 4: (220, 180, 20), 5: (170, 40, 170),
           6: (20, 170, 180), 7: (230, 120, 20), 8: (120, 120, 120)}

# 7-segment digits: segments a b c d e f g
_SEGMENTS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc",
             "7": "abc", "8": "abcdefg", "9": "abcdfg"}


def _digit_boxes(text, width, height):
    """Rectangles (x0, y0, x1, y1) of the white 7-segment number, centred, half the frame high."""
    h = height // 2
    w = h // 2
    t = max(2, h // 10)
    gap = w // 3
    total = len(text) * w + (len(text) - 1) * gap
    x, y = (width - total) // 2, (height - h) // 2
    boxes = []
    for ch in text:
        seg = {"a": (x, y, x + w, y + t), "b": (x + w - t, y, x + w, y + h // 2), "c": (x + w - t, y + h // 2, x + w, y + h),
               "d": (x, y + h - t, x + w, y + h), "e": (x, y + h // 2, x + t, y + h), "f": (x, y, x + t, y + h // 2),
               "g": (x, y + h // 2 - t // 2, x + w, y + h // 2 + t // 2 + 1)}
        boxes += [seg[s] for s in _SEGMENTS.get(ch, "")]
        x += w + gap
    return boxes


def _png(width, height, rows):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def colour_frame(index, width=640, fmt=None):
    """(content type, bytes): the colour of camera `index` with its number in white. fmt "png" forces PNG."""
    width = max(64, min(int(width or 640), 1920))
    height = width * 9 // 16
    rgb = COLOURS.get(int(index), COLOURS[8])
    boxes = _digit_boxes(str(int(index)), width, height)
    if fmt != "png":
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            fmt = "png"
        else:
            img = Image.new("RGB", (width, height), rgb)
            d = ImageDraw.Draw(img)
            for b in boxes:
                d.rectangle((b[0], b[1], b[2] - 1, b[3] - 1), fill=(255, 255, 255))
            out = io.BytesIO()
            img.save(out, "JPEG", quality=85)
            return "image/jpeg", out.getvalue()
    plain, white = bytes(rgb), b"\xff\xff\xff"
    rows = []
    for y in range(height):
        row = bytearray(plain * width)
        for x0, y0, x1, y1 in boxes:
            if y0 <= y < y1:
                row[3 * x0:3 * x1] = white * (x1 - x0)
        rows.append(bytes(row))
    return "image/png", _png(width, height, rows)


def colour_of(rgb, tolerance=60):
    """The camera index whose colour is nearest to a sampled pixel (within tolerance per channel), else None."""
    best = None
    for i, c in COLOURS.items():
        d = max(abs(a - b) for a, b in zip(rgb, c))
        if d <= tolerance and (best is None or d < best[0]):
            best = (d, i)
    return best[1] if best else None


def tile_index(image, box):
    """Index of the camera shown in box (x0, y0, x1, y1) of a Pillow image: samples near the top-left corner of
    the tile (inside the colour, away from the number and the frame line)."""
    x0, y0, x1, y1 = box
    x, y = x0 + (x1 - x0) // 10, y0 + (y1 - y0) // 8
    return colour_of(image.convert("RGB").getpixel((x, y)))


# --- Foscam / ONVIF answers, shaped like a real (Hikvision/Dahua/Reolink-style) camera --------------------------------
FOSCAM_STATE = ("<CGI_Result><result>0</result><IOAlarm>0</IOAlarm><motionDetectAlarm>%s</motionDetectAlarm>"
                "<soundAlarm>%s</soundAlarm><record>0</record><sdState>1</sdState></CGI_Result>")
TIME = ('<?xml version="1.0"?><SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><SOAP-ENV:Body>'
        '<tds:GetSystemDateAndTimeResponse><tds:SystemDateAndTime><tt:DateTimeType>NTP</tt:DateTimeType>'
        '<tt:UTCDateTime><tt:Time><tt:Hour>20</tt:Hour><tt:Minute>15</tt:Minute><tt:Second>0</tt:Second></tt:Time>'
        '<tt:Date><tt:Year>2026</tt:Year><tt:Month>11</tt:Month><tt:Day>23</tt:Day></tt:Date></tt:UTCDateTime>'
        '</tds:SystemDateAndTime></tds:GetSystemDateAndTimeResponse></SOAP-ENV:Body></SOAP-ENV:Envelope>')
CAPS = ('<?xml version="1.0"?><env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><env:Body>'
        '<tds:GetCapabilitiesResponse><tds:Capabilities><tt:Device><tt:XAddr>{base}/onvif/device_service</tt:XAddr>'
        '</tt:Device><tt:Media><tt:XAddr>{base}/onvif/Media</tt:XAddr></tt:Media><tt:PTZ><tt:XAddr>{base}/onvif/PTZ'
        '</tt:XAddr></tt:PTZ></tds:Capabilities></tds:GetCapabilitiesResponse></env:Body></env:Envelope>')
PROFILES = ('<?xml version="1.0"?><env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope" '
            'xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><env:Body>'
            '<trt:GetProfilesResponse><trt:Profiles fixed="true" token="Profile_1"><tt:Name>main</tt:Name>'
            '<tt:PTZConfiguration token="ptz0"><tt:Name>ptz</tt:Name></tt:PTZConfiguration></trt:Profiles>'
            '<trt:Profiles fixed="true" token="Profile_2"><tt:Name>sub</tt:Name></trt:Profiles>'
            '</trt:GetProfilesResponse></env:Body></env:Envelope>')
OK = ('<?xml version="1.0"?><env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"><env:Body>'
      '<tptz:%sResponse xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl"/></env:Body></env:Envelope>')
FAULT = ('<?xml version="1.0"?><env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"><env:Body><env:Fault>'
         '<env:Code><env:Value>env:Sender</env:Value></env:Code><env:Reason><env:Text xml:lang="en">Sender not '
         'Authorized</env:Text></env:Reason></env:Fault></env:Body></env:Envelope>')


class MockCamera(BaseHTTPRequestHandler):
    """Request handler. calls: every accepted Foscam command / ONVIF action (class-wide, reset it in setUp);
    alarm: Foscam motion state; password: what the camera accepts; index: colour of its snapshots;
    clock_prefix: the ONVIF Created value must start with this (the client has to adopt the camera's clock)."""
    calls = []
    alarm = "1"
    password = "pa|ss"
    index = 1
    clock_prefix = "2026-11-23T20:15:0"

    def log_message(self, *a):
        pass

    def reply(self, code, text, ctype="text/xml"):
        data = text.encode("utf-8") if isinstance(text, str) else text
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def snapshot(self, q):
        ctype, data = colour_frame(type(self).index, (q.get("width") or 640))
        return self.reply(200, data, ctype)

    def do_GET(self):  # snapshots and Foscam CGI
        url = urlsplit(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/snapshot.jpg":
            type(self).calls.append("snapshot")
            return self.snapshot(q)
        if q.get("usr") != "admin" or q.get("pwd") != type(self).password:
            return self.reply(200, "<CGI_Result><result>-2</result></CGI_Result>")
        type(self).calls.append(q.get("cmd"))
        if q.get("cmd") == "getDevState":
            return self.reply(200, FOSCAM_STATE % (type(self).alarm, "1"))
        if q.get("cmd") == "snapPicture2":
            return self.snapshot(q)
        return self.reply(200, "<CGI_Result><result>0</result></CGI_Result>")

    def do_POST(self):  # ONVIF
        body = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
        m = re.search(r"<s:Body><\w+:(\w+)", body)
        action = m.group(1) if m else ""
        if action != "GetSystemDateAndTime":  # everything else needs a valid digest
            user = re.search(r"<Username>([^<]*)<", body)
            digest = re.search(r"#PasswordDigest\">([^<]*)<", body)
            nonce = re.search(r"#Base64Binary\">([^<]*)<", body)
            created = re.search(r"<Created[^>]*>([^<]*)<", body)
            if not (user and digest and nonce and created) or user.group(1) != "admin":
                return self.reply(400, FAULT)
            want = base64.b64encode(hashlib.sha1(base64.b64decode(nonce.group(1)) + created.group(1).encode()
                                                 + type(self).password.encode()).digest()).decode()
            if digest.group(1) != want or not created.group(1).startswith(type(self).clock_prefix):
                return self.reply(400, FAULT)  # wrong password or clock not corrected to the camera time
        type(self).calls.append((self.path, action, re.findall(r"<tptz:ProfileToken>([^<]*)<", body)))
        base = "http://127.0.0.1:%d" % self.server.server_port
        if action == "GetSystemDateAndTime":
            return self.reply(200, TIME)
        if action == "GetCapabilities":
            return self.reply(200, CAPS.format(base=base))
        if action == "GetProfiles":
            return self.reply(200, PROFILES)
        return self.reply(200, OK % action)


def start_camera(index=1, host="127.0.0.1", port=0, handler=None):
    """A running fake camera; returns the server (url: http://host:port, stop with .shutdown(); .server_close())."""
    cls = handler or type("Camera%d" % index, (MockCamera,), {"calls": [], "index": index})
    srv = HTTPServer((host, port), cls)
    srv.url = "http://%s:%d" % srv.server_address[:2]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8088)
    ap.add_argument("--index", type=int, default=1)
    a = ap.parse_args()
    s = start_camera(a.index, a.host, a.port)
    print("fake camera %d on %s (snapshot: %s/snapshot.jpg)" % (a.index, s.url, s.url))
    threading.Event().wait()
