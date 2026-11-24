# CamAlert - own rotating log (camalert.log, 2 x 1 MB) with optional remote syslog. Everything is redacted.
# Copyright (C) 2026 CamAlert developers. GPL v2. Plain Python (no Enigma2 imports).
import os
import socket
import threading
import time

try:
    from .logic import LOG_MAX_BYTES, log_allowed, parse_hostport, redact, syslog_line
except ImportError:
    from logic import LOG_MAX_BYTES, log_allowed, parse_hostport, redact, syslog_line

DIRS = ("/home/root/logs", "/tmp")
MIN_FREE = 4 * 1024 * 1024


class CamLog(object):
    def __init__(self, dirs=DIRS, max_bytes=LOG_MAX_BYTES):
        self.dirs, self.max_bytes = dirs, max_bytes
        self.level = "normal"
        self.syslog = None
        self.hostname = socket.gethostname()
        self.lock = threading.Lock()
        self.path = None
        self.sock = None

    def configure(self, level, syslog_target=""):
        self.level = level
        self.syslog = parse_hostport(syslog_target)

    def choose_path(self):
        for d in self.dirs:
            try:
                os.makedirs(d, exist_ok=True)
                st = os.statvfs(d)
                if st.f_bavail * st.f_frsize >= MIN_FREE and os.access(d, os.W_OK):
                    return os.path.join(d, "camalert.log")
            except OSError:
                continue
        return None

    def write(self, level, message):
        if not log_allowed(self.level, level):
            return
        message = redact(message)
        now = time.time()
        line = "%s %s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
                               {"error": "ERROR", "verbose": "DEBUG"}.get(level, "INFO "), message)
        with self.lock:
            try:
                if self.path is None:
                    self.path = self.choose_path()
                if self.path:
                    if os.path.exists(self.path) and os.path.getsize(self.path) >= self.max_bytes:
                        os.replace(self.path, self.path + ".1")
                    with open(self.path, "a", encoding="utf-8") as f:
                        f.write(line)
            except OSError:
                self.path = None
            if self.syslog:
                try:
                    if self.sock is None:
                        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self.sock.sendto(syslog_line(message, level, self.hostname, now).encode("utf-8"), self.syslog)
                except OSError:
                    pass

    def tail(self, lines=200):
        """Last lines of camalert.log (+ the rotated file if needed), already redacted."""
        out = []
        for p in ((self.path + ".1", self.path) if self.path else ()):
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    out += f.read().splitlines()
            except OSError:
                pass
        return out[-lines:]


LOG = CamLog()
