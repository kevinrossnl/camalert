"""#121: Kodi announces its API as _camalert._tcp (the core's mDNS responder; avahi only where /etc/avahi/services is
writable) while the API is on, so Home Assistant finds it. Never a token in the announcement."""
import socket
import unittest

import _paths  # noqa: E402
from kodi import stubs  # noqa: E402


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class FakeResponder(object):
    info = None

    def start(self, info):
        self.info = info
        return True

    def stop(self):
        self.info = None


class TestKodiAnnounce(unittest.TestCase):
    def setUp(self):
        self.port = free_port()
        if "xbmc" not in __import__("sys").modules:
            stubs.install()
        self.server = _paths.kodi_module("server")
        disc = _paths.kodi_module("camalert_core.discovery")
        kodiapi = self.server.kodiapi
        self.orig_settings = kodiapi.settings
        base = kodiapi.settings()  # whatever store an earlier test left: only these keys matter here
        self.over = {"http_port": self.port, "api_https": False, "enabled": True, "allow": "lan",
                     "token": "s3cret-token", "mqtt_name": "Bedroom Kodi"}
        kodiapi.settings = lambda: dict(base, **self.over)
        self.orig = self.server.ADVERTISER
        self.resp = FakeResponder()
        self.server.ADVERTISER = disc.Advertiser(avahi_dir="", responder=self.resp, enabled=lambda: True)

    def tearDown(self):
        self.server.stop()
        self.server.ADVERTISER = self.orig
        self.server.kodiapi.settings = self.orig_settings

    def test_announced_while_the_api_listens(self):
        self.server.start()
        info = self.resp.info
        self.assertEqual(info["instance"], "Bedroom Kodi")
        self.assertEqual(info["port"], self.port)
        txt = dict(info["txt"])
        self.assertEqual((txt["platform"], txt["https"], txt["api_version"]), ("kodi", "0", "1"))
        self.assertNotIn("s3cret", repr(info))
        self.over["enabled"] = False
        self.assertIsNone(self.server.announce())
        self.assertIsNone(self.resp.info)
        self.over["enabled"] = True
        self.assertEqual(self.server.announce(), "responder")
        self.server.stop()  # the add-on stops: no longer announced
        self.assertIsNone(self.resp.info)

    def test_settings_change_updates_the_announcement(self):
        service = _paths.kodi_module("service")
        self.assertIn("mqtt_name", service.RESTART_KEYS["announce"])
        self.assertEqual(service.changed_parts({"enabled": True}, {"enabled": False}), {"announce"})


if __name__ == "__main__":
    unittest.main()
