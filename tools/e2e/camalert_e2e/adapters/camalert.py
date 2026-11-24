"""The CamAlert HTTP API of a player (the same on every player, core/camalert_core/api.py)."""
from .. import transport

# Always sent with actions: the test flag (#62): no chime/TTS, events tagged test.
# Players that do not know it ignore unknown parameters, so the runner never relies on it alone.
TEST_PARAMS = {"test": "1"}
USER_AGENT = "camalert-e2e/1"


class CamAlert(object):
    """Retries after 429: the API allows 30 requests per 10 s per caller."""

    def __init__(self, host, port=8099, token="", http=transport.http, timeout=10, sleep=None):
        self.base = "http://%s:%d/camalert" % (host, port)
        self.headers = {"User-Agent": USER_AGENT}
        if token:
            self.headers["X-CamAlert-Token"] = token
        self.http, self.timeout = http, timeout
        if sleep is None:
            import time
            sleep = time.sleep
        self.sleep = sleep

    def _call(self, *args):
        for wait in (2, 4, 8, 0):
            code, body = self.http(*args, timeout=self.timeout)
            if code != 429 or not wait:
                return code, body
            self.sleep(wait)

    def get(self, name):
        code, body = self._call("%s/%s" % (self.base, name), "GET", None, self.headers)
        if code != 200 or not isinstance(body, dict):
            raise transport.TransportError("GET /camalert/%s: status %s" % (name, code))
        return body

    def status(self):
        return self.get("status")

    def supports_test_flag(self):
        return "test" in (self.status().get("capabilities") or [])

    def camera_names(self):
        out = self.get("cameras")
        return [c["name"] for c in out.get("cameras") or [] if c.get("name")]

    def action(self, name, **params):
        """POST /camalert/<name> with the test flag; (status, body)."""
        data = dict(TEST_PARAMS, **{k: str(v) for k, v in params.items() if v is not None})
        return self._call("%s/%s" % (self.base, name), "POST", data, self.headers)

    def hide(self):
        return self.action("hide")

    def set_dnd(self, on):
        return self.action("dnd", on="1" if on else "0")
