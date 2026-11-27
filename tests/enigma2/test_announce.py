"""#121: the receiver announces its API as _camalert._tcp (avahi service file) while the API is on, so Home Assistant
finds it; nothing while it is off. Never a token in the announcement."""
import importlib
import os
import shutil
import tempfile
import unittest

import _paths  # noqa: F401
from enigma2.harness import e2fake


class FakeResponder(object):
    info = None

    def start(self, info):
        self.info = info
        return True

    def stop(self):
        self.info = None


class TestAnnounce(unittest.TestCase):
    def setUp(self):
        self.env = e2fake.install("openatv")
        self.server = self.env.camalert.server
        self.c = self.env.config.plugins.camalert
        disc = importlib.import_module("CamAlert.camalert_core.discovery")
        self.dir = tempfile.mkdtemp()
        self.avahi = True
        self.server.ADVERTISER = disc.Advertiser(avahi_dir=self.dir, running=lambda: self.avahi,
                                                 responder=FakeResponder(), enabled=lambda: True)
        self.file = os.path.join(self.dir, "camalert.service")
        self.c.token.value = "s3cret-token"
        self.c.mqtt_name.value = "Bedroom TV"

    def tearDown(self):
        self.server.stop()
        e2fake.uninstall()
        shutil.rmtree(self.dir)

    def text(self):
        with open(self.file, encoding="utf-8") as f:
            return f.read()

    def test_announced_while_the_api_listens(self):
        self.server.start()
        text = self.text()
        self.assertIn("<name>Bedroom TV</name>", text)
        self.assertIn("<port>8099</port>", text)
        self.assertIn("<txt-record>platform=enigma2</txt-record>", text)
        self.assertIn("<txt-record>https=0</txt-record>", text)
        self.assertNotIn("s3cret", text)
        self.c.enabled.value = False
        self.assertIsNone(self.server.announce())  # API off: gone
        self.assertFalse(os.path.exists(self.file))
        self.c.enabled.value = True
        self.assertEqual(self.server.announce(), "avahi")

    def test_responder_without_avahi(self):
        self.avahi = False
        self.server.start()
        self.assertFalse(os.path.exists(self.file))
        resp = self.server.ADVERTISER.responder
        self.assertEqual(resp.info["instance"], "Bedroom TV")
        self.assertEqual(dict(resp.info["txt"])["api_version"], "1")

    def test_settings_screen_updates_the_announcement(self):
        self.server.start()
        calls = []
        orig = self.server.announce
        self.server.announce = lambda: calls.append(1) or orig()
        try:
            from CamAlert.setup import CamAlertSetup
            session = self.env.Session()
            screen = session.open(CamAlertSetup)
            self.c.mqtt_name.value = "Kitchen TV"
            screen.save(close=False)
        finally:
            self.server.announce = orig
        self.assertEqual(calls, [1])
        self.assertIn("<name>Kitchen TV</name>", self.text())

    def test_package_removes_the_file(self):
        import sys
        sys.path.insert(0, os.path.join(_paths.ROOT, "tools"))
        try:
            import build_ipk
        finally:
            sys.path.pop(0)
        self.assertIn("rm -f /etc/avahi/services/camalert.service", build_ipk.POSTRM)


if __name__ == "__main__":
    unittest.main()
