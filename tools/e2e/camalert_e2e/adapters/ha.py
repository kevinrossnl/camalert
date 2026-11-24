"""Home Assistant REST API (long-lived token from an environment variable, never printed)."""
from .. import transport


class HomeAssistant(object):
    def __init__(self, url, token, http=transport.http, timeout=15):
        self.url, self.http, self.timeout = url.rstrip("/"), http, timeout
        self.headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}

    def state(self, entity_id):
        code, body = self.http("%s/api/states/%s" % (self.url, entity_id), headers=self.headers, timeout=self.timeout)
        if code != 200 or not isinstance(body, dict):
            raise transport.TransportError("Home Assistant state: status %s" % code)
        return body.get("state")

    def service(self, domain, service, data):
        import json
        code, body = self.http("%s/api/services/%s/%s" % (self.url, domain, service), "POST", json.dumps(data),
                               self.headers, self.timeout)
        if code != 200:
            raise transport.TransportError("Home Assistant %s.%s: status %s" % (domain, service, code))
        return body
