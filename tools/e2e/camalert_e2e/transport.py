"""HTTP, Kodi JSON-RPC (TCP, HTTP, over ssh) and ssh helpers. Secrets go into headers only, never into URLs or logs."""
import base64
import json
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request


class TransportError(Exception):
    pass


def http(url, method="GET", data=None, headers=None, timeout=10, raw=False):
    """(status, body): JSON-decoded unless raw. data: dict -> form body. Never raises on HTTP status codes."""
    body = None
    hdrs = dict(headers or {})
    if isinstance(data, dict):
        body = urllib.parse.urlencode(data).encode()
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif isinstance(data, (bytes, str)):
        body = data.encode() if isinstance(data, str) else data
    req = urllib.request.Request(url, data=body, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, payload = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, payload = e.code, e.read()
    except (OSError, ValueError) as e:
        raise TransportError("%s %s: %s" % (method, _safe(url), e.__class__.__name__))
    if raw:
        return code, payload
    try:
        return code, json.loads(payload.decode("utf-8", "replace") or "null")
    except ValueError:
        return code, payload.decode("utf-8", "replace")


def _safe(url):
    """The URL without query string (a query may hold a value we do not want in a log)."""
    return url.split("?", 1)[0]


def basic_auth(user, password):
    if not user:
        return {}
    return {"Authorization": "Basic " + base64.b64encode(("%s:%s" % (user, password)).encode()).decode()}


def read_response(chunks, want_id):
    """The JSON-RPC answer with id want_id from a stream of concatenated JSON objects (Kodi sends notifications on
    the same TCP connection, without separators). chunks: iterator of bytes."""
    dec, buf = json.JSONDecoder(), ""
    for chunk in chunks:
        buf += chunk.decode("utf-8", "replace")
        while True:
            buf = buf.lstrip()
            if not buf:
                break
            try:
                obj, end = dec.raw_decode(buf)
            except ValueError:
                break
            buf = buf[end:]
            if isinstance(obj, dict) and obj.get("id") == want_id:
                return obj
    raise TransportError("no JSON-RPC answer")


class JsonRpc(object):
    """Kodi JSON-RPC. call() returns the result or raises TransportError with the JSON-RPC error."""

    def __init__(self):
        self.next_id = 0

    def call(self, method, params=None):
        self.next_id += 1
        req = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            req["params"] = params
        out = self.send(req)
        if "error" in out:
            raise TransportError("%s: %s" % (method, out["error"].get("message", "error")))
        return out.get("result")

    def send(self, req):
        raise NotImplementedError


class TcpJsonRpc(JsonRpc):
    """Kodi's raw JSON-RPC port (9090, 'Allow remote control from applications on other systems')."""

    def __init__(self, host, port=9090, timeout=8):
        JsonRpc.__init__(self)
        self.host, self.port, self.timeout = host, port, timeout

    def send(self, req):
        try:
            with socket.create_connection((self.host, self.port), self.timeout) as s:
                s.settimeout(self.timeout)
                s.sendall(json.dumps(req).encode())
                return read_response(iter(lambda: s.recv(65536), b""), req["id"])
        except OSError as e:
            raise TransportError("JSON-RPC tcp: %s" % e.__class__.__name__)


class HttpJsonRpc(JsonRpc):
    def __init__(self, url, user="", password="", timeout=8):
        JsonRpc.__init__(self)
        self.url, self.headers, self.timeout = url, basic_auth(user, password), timeout

    def send(self, req):
        h = dict(self.headers, **{"Content-Type": "application/json"})
        code, out = http(self.url, "POST", json.dumps(req), h, self.timeout)
        if code != 200 or not isinstance(out, dict):
            raise TransportError("JSON-RPC http: status %s" % code)
        return out


SSH_RPC = ("import socket,sys,json;d=sys.stdin.buffer.read();s=socket.create_connection(('127.0.0.1',%d),8);"
           "s.sendall(d);w=json.loads(d)['id'];dec=json.JSONDecoder();b=''\n"
           "while True:\n c=s.recv(65536)\n if not c: break\n b+=c.decode('utf-8','replace')\n"
           " while b.strip():\n  b=b.lstrip()\n  try: o,e=dec.raw_decode(b)\n  except ValueError: break\n"
           "  b=b[e:]\n  if o.get('id')==w: sys.stdout.write(json.dumps(o)); sys.exit(0)\n")


class SshJsonRpc(JsonRpc):
    """JSON-RPC on the player itself (127.0.0.1:9090) through ssh, for players whose port is local only."""

    def __init__(self, shell, port=9090):
        JsonRpc.__init__(self)
        self.shell, self.port = shell, port

    def send(self, req):
        out = self.shell.run("python3 -c %s" % quote(SSH_RPC % self.port), json.dumps(req))
        try:
            return json.loads(out)
        except ValueError:
            raise TransportError("JSON-RPC ssh: no answer")


def quote(text):
    return "'" + text.replace("'", "'\"'\"'") + "'"


class Ssh(object):
    """ssh to a host (an alias from ~/.ssh/config); BatchMode, so it never asks for a password."""

    def __init__(self, host, timeout=30):
        self.host, self.timeout = host, timeout

    def run(self, command, stdin=None, check=True):
        try:
            p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", self.host, command],
                               input=(stdin.encode() if isinstance(stdin, str) else stdin), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise TransportError("ssh: %s" % e.__class__.__name__)
        if check and p.returncode != 0:
            raise TransportError("ssh command failed (%d): %s" % (p.returncode, p.stderr.decode("utf-8", "replace")
                                                                  .strip()[-200:]))
        return p.stdout.decode("utf-8", "replace")
