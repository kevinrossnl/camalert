#!/usr/bin/env python3
"""Fake Foscam PTZ camera for the e2e runner (#35): records every CGI command, moves nothing.

    python3 fake_ptz.py [--host 127.0.0.1] [--port 19842] [--calls ptz-calls.txt]

Answers /cgi-bin/CGIProxy.fcgi?cmd=...: `<result>0</result>` for every command (getDevState: no alarm) and appends
the command name to the calls file, one per line. Plain Python 3.8+, runs on the receiver. Copyright (C) 2026
CamAlert developers, GPL v2.
"""
import argparse
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

STATE = ("<CGI_Result><result>0</result><motionDetectAlarm>1</motionDetectAlarm>"
         "<soundAlarm>1</soundAlarm></CGI_Result>")
OK = "<CGI_Result><result>0</result></CGI_Result>"


class Handler(BaseHTTPRequestHandler):
    server_version = "fake-ptz"

    def log_message(self, *args):
        pass

    def do_GET(self):
        url = urlsplit(self.path)
        cmd = (parse_qs(url.query).get("cmd") or [""])[0]
        if url.path != "/cgi-bin/CGIProxy.fcgi" or not cmd:
            body, code = b"not found", 404
        else:
            self.server.record(cmd)
            body, code = (STATE if cmd == "getDevState" else OK).encode(), 200
        self.send_response(code)
        self.send_header("Content-Type", "text/xml")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FakePtz(HTTPServer):
    def __init__(self, host="127.0.0.1", port=0, calls_file=None):
        HTTPServer.__init__(self, (host, port), Handler)
        self.calls, self.calls_file, self.lock = [], calls_file, threading.Lock()

    def record(self, cmd):
        with self.lock:
            self.calls.append(cmd)
            if self.calls_file:
                with open(self.calls_file, "a") as f:
                    f.write(cmd + "\n")

    def start(self):
        threading.Thread(target=self.serve_forever, daemon=True).start()
        return self


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=19842)
    ap.add_argument("--calls", default="ptz-calls.txt")
    a = ap.parse_args()
    open(a.calls, "w").close()
    FakePtz(a.host, a.port, a.calls).serve_forever()
