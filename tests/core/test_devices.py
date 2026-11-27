"""Foscam / ONVIF builders, parsers and the client against a small local mock camera (no real camera needed)."""
import base64
import os
import threading
import unittest
from http.server import HTTPServer

import _paths  # noqa: E402

_paths.core()
from camalert_core.devices import client  # noqa: E402
from camalert_core.devices import config as dev_config  # noqa: E402
from camalert_core.devices import foscam  # noqa: E402
from camalert_core.devices import onvif  # noqa: E402

# the mock camera (Foscam CGI, ONVIF with WS-Security, colour snapshots) is shared: tests/fakes/camera.py (#32)
from fakes.camera import CAPS, FAULT, FOSCAM_STATE, OK, PROFILES, TIME, MockCamera  # noqa: E402,F401


class TestDeviceLogic(unittest.TestCase):
    def test_parse_devices(self):
        d = dev_config.parse_devices("# name|type|host:port|user|password\n"
                            "garden|foscam|192.168.1.50:88|admin|pa|ss\n"
                            "drive|onvif|192.168.1.51|admin|secret\n"
                            "broken|other|1.2.3.4|a|b\nnope\n")
        self.assertEqual(sorted(d), ["drive", "garden"])
        self.assertEqual(d["garden"], {"type": "foscam", "host": "192.168.1.50", "port": 88, "user": "admin",
                                       "password": "pa|ss"})
        self.assertEqual(d["drive"]["port"], 80)
        self.assertEqual(dev_config.parse_devices("cam|foscam|10.0.0.2")["cam"]["port"], 88)

    def test_foscam(self):
        dev = {"host": "10.0.0.2", "port": 88, "user": "admin", "password": "a&b"}
        self.assertEqual(foscam.foscam_url(dev, "ptzMoveUp"),
                         "http://10.0.0.2:88/cgi-bin/CGIProxy.fcgi?cmd=ptzMoveUp&usr=admin&pwd=a%26b")
        self.assertTrue(foscam.foscam_alarm(FOSCAM_STATE % ("2", "1")))
        self.assertTrue(foscam.foscam_alarm(FOSCAM_STATE % ("1", "2")))
        self.assertFalse(foscam.foscam_alarm(FOSCAM_STATE % ("1", "1")))
        self.assertFalse(foscam.foscam_alarm(FOSCAM_STATE % ("0", "0")))
        self.assertFalse(foscam.foscam_alarm("<CGI_Result><result>-2</result></CGI_Result>"))
        self.assertTrue(foscam.alarm_edge(False, True))
        self.assertFalse(foscam.alarm_edge(True, True))
        self.assertEqual(foscam.foscam_ptz("left"), ("ptzMoveLeft", "ptzStopRun"))
        self.assertEqual(foscam.foscam_ptz("zoom_in"), ("zoomIn", "zoomStop"))
        self.assertEqual(foscam.foscam_ptz("home"), ("ptzReset", None))

    def test_wsse_digest(self):
        # checked against: (nonce bytes; created; password) | openssl dgst -sha1 -binary | base64
        self.assertEqual(onvif.wsse_digest("secret", bytes(range(16)), "2026-11-23T20:15:00Z"),
                         "U43YeZrn1WbFqQ23Y+2cSwndwwA=")
        self.assertEqual(onvif.onvif_created(1795464900), "2026-11-23T20:15:00Z")
        env = onvif.onvif_envelope(onvif.onvif_body("GetProfiles"), "ad<min", "secret", bytes(range(16)), "2026-11-23T20:15:00Z")
        self.assertIn("<Username>ad&lt;min</Username>", env)
        self.assertIn("U43YeZrn1WbFqQ23Y+2cSwndwwA=", env)
        self.assertIn(base64.b64encode(bytes(range(16))).decode(), env)
        self.assertNotIn("secret", env)

    def test_onvif_bodies_and_parsers(self):
        self.assertIn('<tt:PanTilt x="-0.5" y="0"/><tt:Zoom x="0"/>',
                      onvif.onvif_body("ContinuousMove", token="P1", vector=dev_config.PTZ_VECTORS["left"]))
        self.assertIn("<tptz:ProfileToken>P1</tptz:ProfileToken>", onvif.onvif_body("GotoHomePosition", token="P1"))
        self.assertIn("<tptz:PanTilt>true</tptz:PanTilt>", onvif.onvif_body("Stop", token="P1"))
        self.assertEqual(onvif.onvif_xaddrs(CAPS.format(base="http://cam")),
                         {"media": "http://cam/onvif/Media", "ptz": "http://cam/onvif/PTZ"})
        self.assertEqual(onvif.onvif_profile_token(PROFILES), "Profile_1")
        self.assertEqual(onvif.onvif_time(TIME), 1795464900)
        self.assertEqual(onvif.onvif_fault(FAULT), "Sender not Authorized")
        self.assertIsNone(onvif.onvif_fault(OK % "Stop"))


class TestSecureFile(unittest.TestCase):
    def test_devices_file_becomes_owner_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "devices.conf")
            with open(p, "w") as f:
                f.write("protect|unifi|192.168.1.1|viewer|secret\n")
            os.chmod(p, 0o644)
            self.assertTrue(client.secure_file(p))
            self.assertEqual(os.stat(p).st_mode & 0o777, 0o600)
            self.assertFalse(client.secure_file(p))  # already private
            self.assertFalse(client.secure_file(os.path.join(d, "missing")))


class TestMockCamera(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), MockCamera)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        MockCamera.calls = []

    def dev(self, kind, password="pa|ss"):
        return {"type": kind, "host": "127.0.0.1", "port": self.port, "user": "admin", "password": password}

    def test_foscam_poll_and_ptz(self):
        MockCamera.alarm = "1"
        self.assertFalse(client.foscam_state(self.dev("foscam")))
        MockCamera.alarm = "2"
        self.assertTrue(client.foscam_state(self.dev("foscam")))
        client.ptz(self.dev("foscam"), "up", 0.01)
        client.ptz(self.dev("foscam"), "zoom_out", 0.01)
        client.ptz(self.dev("foscam"), "home")
        self.assertEqual(MockCamera.calls, ["getDevState", "getDevState", "ptzMoveUp", "ptzStopRun", "zoomOut",
                                            "zoomStop", "ptzReset"])
        with self.assertRaises(client.DeviceError) as e:
            client.ptz(self.dev("foscam", "wrong"), "up", 0.01)
        self.assertNotIn("wrong", str(e.exception))

    def test_onvif_ptz(self):
        orig = client.time.time
        client.time.time = lambda: 1795464900 - 3600  # receiver clock an hour behind: the camera clock is used
        try:
            client.ptz(self.dev("onvif"), "right", 0.01)
            client.ptz(self.dev("onvif"), "home")
        finally:
            client.time.time = orig
        actions = [(c[0], c[1]) for c in MockCamera.calls]
        self.assertEqual(actions, [("/onvif/device_service", "GetSystemDateAndTime"),
                                   ("/onvif/device_service", "GetCapabilities"), ("/onvif/Media", "GetProfiles"),
                                   ("/onvif/PTZ", "ContinuousMove"), ("/onvif/PTZ", "Stop"),
                                   ("/onvif/PTZ", "GotoHomePosition")])
        self.assertEqual(MockCamera.calls[-1][2], ["Profile_1"])

    def test_onvif_wrong_password(self):
        with self.assertRaises(client.DeviceError) as e:
            client.ptz(self.dev("onvif", "nope"), "left", 0.01)
        self.assertIn("Sender not Authorized", str(e.exception))
        self.assertNotIn("nope", str(e.exception))


if __name__ == "__main__":
    unittest.main()
