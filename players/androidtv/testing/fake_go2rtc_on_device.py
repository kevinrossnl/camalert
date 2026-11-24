#!/usr/bin/env python3
"""A fake go2rtc ON the TV device, for tests of the Android TV player with neutral demo cameras (#64).

`adb reverse` does not work with Fire OS 6 over the network, so the fake go2rtc of tests/fakes/go2rtc.py cannot be
reached from the device. This tool writes its solid-colour frames and a tiny HTTP responder (toybox nc + sh) to
/data/local/tmp/camfake on the device and starts it on 127.0.0.1:11984; set the go2rtc address of the app to
http://127.0.0.1:11984. Never real camera images. `stop` kills it and removes the folder.

    python3 players/androidtv/testing/fake_go2rtc_on_device.py start --serial 192.168.1.30:5555 [--adb adb]
    python3 players/androidtv/testing/fake_go2rtc_on_device.py stop  --serial 192.168.1.30:5555

Answers /api/streams (front_door, garden, driveway, back_door) and /api/frame.jpeg?src=<name>; driveway answers
HTTP 500 (the "camera not reachable" tile). No live streams. Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "tests", "fakes"))
import go2rtc  # noqa: E402

DIR = "/data/local/tmp/camfake"
PORT = 11984
UNREACHABLE = "driveway"
SERVE = r"""D=%(dir)s
read -r method path proto
while read -r h; do h=$(echo "$h" | tr -d '\r'); [ -z "$h" ] && break; done
case "$path" in
  /api/streams*) f=$D/streams.json; ct=application/json ;;
  /api/frame.jpeg*) src=${path#*src=}; src=${src%%%%&*}; f=$D/$src.img; ct=$(cat $D/ctype)
     [ "$src" = %(bad)s ] && f=/nonexistent ;;
  *) f=/nonexistent ;;
esac
if [ -f "$f" ]; then
  printf 'HTTP/1.0 200 OK\r\nContent-Type: %%s\r\nContent-Length: %%s\r\nConnection: close\r\n\r\n' "$ct" "$(wc -c < $f)"
  cat "$f"
else
  printf 'HTTP/1.0 500 Internal Server Error\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
fi
"""


def files(folder):
    """Writes the frames, the stream list and serve.sh into folder."""
    ctype = "image/png"
    for name, rgb in go2rtc.CAMERAS.items():
        ctype, data = go2rtc.frame(640, rgb)
        with open(os.path.join(folder, name + ".img"), "wb") as f:
            f.write(data)
    streams = {n: {"producers": [{"url": "fake://%s" % n}], "consumers": []} for n in go2rtc.CAMERAS}
    with open(os.path.join(folder, "streams.json"), "w") as f:
        json.dump(streams, f)
    with open(os.path.join(folder, "ctype"), "w") as f:
        f.write(ctype)
    with open(os.path.join(folder, "serve.sh"), "w", newline="\n") as f:
        f.write(SERVE % {"dir": DIR, "bad": UNREACHABLE})


def stop_command():
    return ("for p in $(pidof toybox nc 2>/dev/null); do cat /proc/$p/cmdline | tr '\\0' ' ' | grep -q %d && kill $p; "
            "done; rm -rf %s" % (PORT, DIR))


def start_command():
    return ("(setsid toybox nc -s 127.0.0.1 -p %d -L /system/bin/sh %s/serve.sh > /dev/null 2>&1 < /dev/null &)"
            % (PORT, DIR))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("action", choices=("start", "stop"))
    ap.add_argument("--serial", required=True)
    ap.add_argument("--adb", default="adb")
    a = ap.parse_args(argv)
    adb = [a.adb, "-s", a.serial]
    subprocess.check_call(adb + ["shell", stop_command()])
    if a.action == "start":
        with tempfile.TemporaryDirectory() as d:
            files(d)
            subprocess.check_call(adb + ["shell", "mkdir", "-p", DIR])
            subprocess.check_call(adb + ["push", d + "/.", DIR + "/"], stdout=subprocess.DEVNULL)
        subprocess.check_call(adb + ["shell", start_command()])
        print("fake go2rtc on the device: http://127.0.0.1:%d" % PORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
