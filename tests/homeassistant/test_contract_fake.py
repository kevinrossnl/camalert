"""The fake player over real HTTP satisfies the HTTP contract table (tests/contract/api_table.py), so the
runtime tests use exactly the answers of Enigma2 and Kodi (#33, #4)."""
import json
import urllib.error
import urllib.request
from urllib.parse import urlencode

from contract.api_table import TABLE
from contract.adapters import Answer
from contract.test_http_contract import differences
from fake_player import CALLER_HEADER


class HttpAdapter(object):
    """contract adapter: every row goes over HTTP to the fake player (blocking; run in an executor)."""

    def __init__(self, player):
        self.player = player

    def reset(self):
        self.player.reset()

    def set_cameras(self, names):
        if names is None:
            self.player.cameras = self._saved
        else:
            self._saved, self.player.cameras = self.player.cameras, list(names)

    def call(self, req, ctl):
        p = self.player
        p.ctl, p.settings = ctl, dict(req.settings)
        headers = {CALLER_HEADER: req.ip}
        if req.header is not None:
            headers["X-CamAlert-Token"] = req.header
        if req.user_agent:
            headers["User-Agent"] = req.user_agent
        url, data = "http://127.0.0.1:%d%s" % (p.port, req.path), None
        if req.method == "POST" and req.body is None:
            data = urlencode(req.args).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif req.body is not None:
            data, headers["Content-Type"] = req.body, "application/json"
            if req.args:
                url += "?" + urlencode(req.args)
        elif req.args:
            url += "?" + urlencode(req.args)
        r = urllib.request.Request(url, data=data, headers=headers, method=req.method)
        try:
            with urllib.request.urlopen(r, timeout=5) as resp:
                code, raw, ctype, hdrs = resp.status, resp.read(), resp.headers.get_content_type(), dict(resp.headers)
        except urllib.error.HTTPError as e:
            code, raw, ctype, hdrs = e.code, e.read(), e.headers.get_content_type(), dict(e.headers)
        body = json.loads(raw) if ctype == "application/json" else raw.decode()
        return Answer(code, body, ctype, ctl, hdrs)


async def test_fake_player_follows_the_contract(hass, player, monkeypatch):
    import socket
    from fakes import dns
    monkeypatch.setattr(socket, "getaddrinfo", dns._fake)  # the test harness replaces it after dns.install()
    adapter = HttpAdapter(player)

    def run():
        return ["%s: %s" % (r["name"], "; ".join(d)) for r in TABLE for d in [differences(adapter, r)] if d]
    assert await hass.async_add_executor_job(run) == []
    assert len(TABLE) >= 30
