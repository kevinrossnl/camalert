#!/usr/bin/env python3
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Talk-back (#98): the go2rtc stream that sends a browser's microphone to a camera's speaker.

    python3 tools/talkback.py stream front_door 192.168.1.14            # the go2rtc.yaml line (port 7004, AAC 22050)
    python3 tools/talkback.py stream front_door 192.168.1.14 --port 7004 --rate 22050
    python3 tools/talkback.py protect https://192.168.1.1 user [--password-file F]
                                                                         # read-only: which UniFi Protect cameras
                                                                         # have a speaker, and their talkback settings

go2rtc cannot talk to UniFi Protect itself. The stream "<camera>_talk" uses go2rtc's exec backchannel: go2rtc pipes
the browser's audio (PCMA 8 kHz) into FFmpeg, which encodes it as the camera expects (AAC/ADTS, mono) and sends it
as UDP straight to the camera's talkback port (Protect's talkbackSettings: typeIn serverudp, bindPort). The go2rtc
host must reach the camera on that UDP port. CamAlert players show a "Talk" button in the web player when go2rtc has
"<camera>_talk" (urls.talk_streams); the talk stream itself is never listed as a camera.
"""
import argparse
import getpass
import json
import re
import ssl
import sys
import urllib.request
from http.cookiejar import CookieJar

NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
HOST = re.compile(r"^[A-Za-z0-9.:-]+$")


def stream_line(camera, host, port=7004, rate=22050, bitrate="32k"):
    """The go2rtc.yaml line of the talk stream of `camera` (indented for under `streams:`)."""
    if not NAME.match(camera or "") or not HOST.match(host or "") or not 0 < int(port) < 65536:
        raise ValueError("invalid camera name, host or port")
    if int(rate) not in (8000, 16000, 22050, 44100, 48000):
        raise ValueError("unsupported sample rate")
    cmd = ("exec:ffmpeg -hide_banner -loglevel error -fflags nobuffer -f alaw -ar 8000 -ac 1 -i - "
           "-c:a aac -b:a %s -ar %d -ac 1 -f adts udp://%s:%d#backchannel=1#audio=alaw/8000"
           % (bitrate, int(rate), host, int(port)))
    return '  %s_talk: "%s"' % (camera, cmd)


def protect_speakers(console, user, password, opener=None):
    """[(name, host, talkbackSettings)] of the Protect cameras with a speaker (read only: login + GET cameras)."""
    if opener is None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # the console's own certificate
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                             urllib.request.HTTPCookieProcessor(CookieJar()))
    base = console.rstrip("/")
    r = opener.open(urllib.request.Request(base + "/api/auth/login", method="POST",
                                           data=json.dumps({"username": user, "password": password}).encode(),
                                           headers={"Content-Type": "application/json"}), timeout=15)
    csrf = r.headers.get("X-Updated-Csrf-Token") or r.headers.get("X-CSRF-Token") or ""
    cams = json.load(opener.open(urllib.request.Request(base + "/proxy/protect/api/cameras",
                                                        headers={"X-CSRF-Token": csrf}), timeout=15))
    return [(c.get("name"), c.get("host"), c.get("talkbackSettings") or {})
            for c in cams if (c.get("featureFlags") or {}).get("hasSpeaker")]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stream")
    s.add_argument("camera")
    s.add_argument("host")
    s.add_argument("--port", type=int, default=7004)
    s.add_argument("--rate", type=int, default=22050)
    q = sub.add_parser("protect")
    q.add_argument("console")
    q.add_argument("user")
    q.add_argument("--password-file")
    a = p.parse_args(argv)
    if a.cmd == "stream":
        print(stream_line(a.camera, a.host, a.port, a.rate))
        return 0
    pw = open(a.password_file, encoding="utf-8").read().strip() if a.password_file else getpass.getpass()
    for name, host, t in protect_speakers(a.console, a.user, pw):
        print("%s: %s, talkback %s %s port %s, %s Hz" % (name, host, t.get("typeFmt"), t.get("typeIn"),
                                                         t.get("bindPort"), t.get("samplingRate")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
