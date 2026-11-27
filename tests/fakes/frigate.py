#!/usr/bin/env python3
"""Fake Frigate for tests and the e2e runner (#32): MQTT event sequences and the event snapshot API.

    python3 tests/fakes/frigate.py [--host 127.0.0.1] [--port 5000]

- event_sequence(camera, label, ...) gives the payloads Frigate publishes on <prefix>/events for one detection:
  "new", then "update"s, then "end" (shaped like Frigate 0.13+: sub_label as [name, score]).
- FakeFrigate serves GET /api/events/<id>/snapshot.jpg (a colour-coded frame of tests/fakes/camera.py, index
  from the camera name's position in `cameras`) and GET /api/events/<id>/clip.mp4 (404: no clips here); every
  request is recorded in .requests.
Event ids use a fixed epoch (2026-11-23 20:15 UTC), never the real time. Copyright (C) 2026 CamAlert developers.
"""
import argparse
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camera import colour_frame  # noqa: E402

EPOCH = 1795464900.0  # 2026-11-23T20:15:00Z


def event(camera, label="person", event_id=None, score=0.8, sub_label=None, has_snapshot=True, has_clip=False,
          false_positive=False, start=EPOCH):
    """The 'after' object of a Frigate event."""
    return {"id": event_id or "%.6f-%s" % (start, camera), "camera": camera, "label": label, "top_score": score,
            "sub_label": [sub_label, 0.9] if sub_label else None, "has_snapshot": has_snapshot,
            "has_clip": has_clip, "false_positive": false_positive, "start_time": start, "end_time": None}


def event_sequence(camera, label="person", updates=1, end=True, **kw):
    """[json payloads] for one detection: new, `updates` x update, end (Frigate's own order)."""
    first = event(camera, label, **kw)
    out = [{"type": "new", "before": first, "after": first}]
    prev = first
    for n in range(updates):
        cur = dict(prev, top_score=min(1.0, prev["top_score"] + 0.05))
        out.append({"type": "update", "before": prev, "after": cur})
        prev = cur
    if end:
        out.append({"type": "end", "before": prev, "after": dict(prev, end_time=prev["start_time"] + 12)})
    return [json.dumps(p) for p in out]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        srv = self.server
        srv.requests.append(self.path)
        m = re.match(r"^/api/events/([^/]+)/(snapshot\.jpg|clip\.mp4)", self.path)
        if not m:
            return self._send(404, "text/plain", b"not found")
        event_id, what = m.group(1), m.group(2)
        camera = event_id.split("-", 1)[1] if "-" in event_id else ""
        if what == "clip.mp4" or camera not in srv.cameras:
            return self._send(404, "application/json", b'{"success": false, "message": "Event not found"}')
        ctype, data = colour_frame(srv.cameras.index(camera) + 1, 640)
        return self._send(200, ctype, data)


class FakeFrigate(HTTPServer):
    def __init__(self, host="127.0.0.1", port=0, cameras=("front_door", "garden", "driveway", "back_door")):
        HTTPServer.__init__(self, (host, port), Handler)
        self.cameras = list(cameras)
        self.requests = []

    @property
    def url(self):
        return "http://%s:%d" % self.server_address[:2]

    def start(self):
        threading.Thread(target=self.serve_forever, daemon=True).start()
        return self

    def stop(self):
        self.shutdown()
        self.server_close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    a = ap.parse_args()
    srv = FakeFrigate(a.host, a.port)
    print("fake Frigate on %s; example event: %s" % (srv.url, event_sequence("front_door")[0]))
    srv.serve_forever()
