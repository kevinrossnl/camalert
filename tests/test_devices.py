"""Foscam / ONVIF builders, parsers and the client against a small local mock camera (no real camera needed)."""
import base64
import hashlib
import os
import re
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "CamAlert"))
import logic as L  # noqa: E402
import devices as D  # noqa: E402

FOSCAM_STATE = ("<CGI_Result><result>0</result><IOAlarm>0</IOAlarm><motionDetectAlarm>%s</motionDetectAlarm>"
                "<soundAlarm>%s</soundAlarm><record>0</record><sdState>1</sdState></CGI_Result>")

# Answers shaped like a real (Hikvision/Dahua/Reolink-style) ONVIF camera
TIME = ('<?xml version="1.0"?><SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><SOAP-ENV:Body>'
        '<tds:GetSystemDateAndTimeResponse><tds:SystemDateAndTime><tt:DateTimeType>NTP</tt:DateTimeType>'
        '<tt:UTCDateTime><tt:Time><tt:Hour>20</tt:Hour><tt:Minute>15</tt:Minute><tt:Second>0</tt:Second></tt:Time>'
        '<tt:Date><tt:Year>2026</tt:Year><tt:Month>11</tt:Month><tt:Day>23</tt:Day></tt:Date></tt:UTCDateTime>'
        '</tds:SystemDateAndTime></tds:GetSystemDateAndTimeResponse></SOAP-ENV:Body></SOAP-ENV:Envelope>')
CAPS = ('<?xml version="1.0"?><env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><env:Body>'
        '<tds:GetCapabilitiesResponse><tds:Capabilities><tt:Device><tt:XAddr>{base}/onvif/device_service</tt:XAddr>'
        '</tt:Device><tt:Media><tt:XAddr>{base}/onvif/Media</tt:XAddr></tt:Media><tt:PTZ><tt:XAddr>{base}/onvif/PTZ'
        '</tt:XAddr></tt:PTZ></tds:Capabilities></tds:GetCapabilitiesResponse></env:Body></env:Envelope>')
PROFILES = ('<?xml version="1.0"?><env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope" '
            'xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><env:Body>'
            '<trt:GetProfilesResponse><trt:Profiles fixed="true" token="Profile_1"><tt:Name>main</tt:Name>'
            '<tt:PTZConfiguration token="ptz0"><tt:Name>ptz</tt:Name></tt:PTZConfiguration></trt:Profiles>'
            '<trt:Profiles fixed="true" token="Profile_2"><tt:Name>sub</tt:Name></trt:Profiles>'
            '</trt:GetProfilesResponse></env:Body></env:Envelope>')
OK = ('<?xml version="1.0"?><env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"><env:Body>'
      '<tptz:%sResponse xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl"/></env:Body></env:Envelope>')
FAULT = ('<?xml version="1.0"?><env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"><env:Body><env:Fault>'
         '<env:Code><env:Value>env:Sender</env:Value></env:Code><env:Reason><env:Text xml:lang="en">Sender not '
         'Authorized</env:Text></env:Reason></env:Fault></env:Body></env:Envelope>')


class MockCamera(BaseHTTPRequestHandler):
    calls = []
    alarm = "1"
    password = "pa|ss"

    def log_message(self, *a):
        pass

    def reply(self, code, text):
        data = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # Foscam CGI
        q = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
        if q.get("usr") != "admin" or q.get("pwd") != self.password:
            return self.reply(200, "<CGI_Result><result>-2</result></CGI_Result>")
        MockCamera.calls.append(q["cmd"])
        if q["cmd"] == "getDevState":
            return self.reply(200, FOSCAM_STATE % (MockCamera.alarm, "1"))
        return self.reply(200, "<CGI_Result><result>0</result></CGI_Result>")

    def do_POST(self):  # ONVIF
        body = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
        action = re.search(r"<s:Body><\w+:(\w+)", body).group(1)
        if action != "GetSystemDateAndTime":  # everything else needs a valid digest
            user = re.search(r"<Username>([^<]*)<", body)
            digest = re.search(r"#PasswordDigest\">([^<]*)<", body)
            nonce = re.search(r"#Base64Binary\">([^<]*)<", body)
            created = re.search(r"<Created[^>]*>([^<]*)<", body)
            if not (user and digest and nonce and created) or user.group(1) != "admin":
                return self.reply(400, FAULT)
            want = base64.b64encode(hashlib.sha1(base64.b64decode(nonce.group(1)) + created.group(1).encode()
                                                 + self.password.encode()).digest()).decode()
            if digest.group(1) != want or not created.group(1).startswith("2026-11-23T20:15:0"):
                return self.reply(400, FAULT)  # wrong password or clock not corrected to the camera time
        MockCamera.calls.append((self.path, action, re.findall(r"<tptz:ProfileToken>([^<]*)<", body)))
        base = "http://127.0.0.1:%d" % self.server.server_port
        if action == "GetSystemDateAndTime":
            return self.reply(200, TIME)
        if action == "GetCapabilities":
            return self.reply(200, CAPS.format(base=base))
        if action == "GetProfiles":
            return self.reply(200, PROFILES)
        return self.reply(200, OK % action)


class TestDeviceLogic(unittest.TestCase):
    def test_parse_devices(self):
        d = L.parse_devices("# name|type|host:port|user|password\n"
                            "garden|foscam|192.168.1.50:88|admin|pa|ss\n"
                            "drive|onvif|192.168.1.51|admin|secret\n"
                            "broken|other|1.2.3.4|a|b\nnope\n")
        self.assertEqual(sorted(d), ["drive", "garden"])
        self.assertEqual(d["garden"], {"type": "foscam", "host": "192.168.1.50", "port": 88, "user": "admin",
                                       "password": "pa|ss"})
        self.assertEqual(d["drive"]["port"], 80)
        self.assertEqual(L.parse_devices("cam|foscam|10.0.0.2")["cam"]["port"], 88)

    def test_foscam(self):
        dev = {"host": "10.0.0.2", "port": 88, "user": "admin", "password": "a&b"}
        self.assertEqual(L.foscam_url(dev, "ptzMoveUp"),
                         "http://10.0.0.2:88/cgi-bin/CGIProxy.fcgi?cmd=ptzMoveUp&usr=admin&pwd=a%26b")
        self.assertTrue(L.foscam_alarm(FOSCAM_STATE % ("2", "1")))
        self.assertTrue(L.foscam_alarm(FOSCAM_STATE % ("1", "2")))
        self.assertFalse(L.foscam_alarm(FOSCAM_STATE % ("1", "1")))
        self.assertFalse(L.foscam_alarm(FOSCAM_STATE % ("0", "0")))
        self.assertFalse(L.foscam_alarm("<CGI_Result><result>-2</result></CGI_Result>"))
        self.assertTrue(L.alarm_edge(False, True))
        self.assertFalse(L.alarm_edge(True, True))
        self.assertEqual(L.foscam_ptz("left"), ("ptzMoveLeft", "ptzStopRun"))
        self.assertEqual(L.foscam_ptz("zoom_in"), ("zoomIn", "zoomStop"))
        self.assertEqual(L.foscam_ptz("home"), ("ptzReset", None))

    def test_ptz_keys(self):
        self.assertEqual(L.ptz_key(L.KEY_UP), "up")
        self.assertEqual(L.ptz_key(L.KEY_CHANNELUP), "zoom_in")
        self.assertEqual(L.ptz_key(L.KEY_OK), "home")
        self.assertEqual(L.ptz_key(L.KEY_EXIT), "leave")
        self.assertIsNone(L.ptz_key(115))
        self.assertEqual(L.key_action(L.KEY_YELLOW), "ptz")

    def test_wsse_digest(self):
        # checked against: (nonce bytes; created; password) | openssl dgst -sha1 -binary | base64
        self.assertEqual(L.wsse_digest("secret", bytes(range(16)), "2026-11-23T20:15:00Z"),
                         "U43YeZrn1WbFqQ23Y+2cSwndwwA=")
        self.assertEqual(L.onvif_created(1795464900), "2026-11-23T20:15:00Z")
        env = L.onvif_envelope(L.onvif_body("GetProfiles"), "ad<min", "secret", bytes(range(16)), "2026-11-23T20:15:00Z")
        self.assertIn("<Username>ad&lt;min</Username>", env)
        self.assertIn("U43YeZrn1WbFqQ23Y+2cSwndwwA=", env)
        self.assertIn(base64.b64encode(bytes(range(16))).decode(), env)
        self.assertNotIn("secret", env)

    def test_onvif_bodies_and_parsers(self):
        self.assertIn('<tt:PanTilt x="-0.5" y="0"/><tt:Zoom x="0"/>',
                      L.onvif_body("ContinuousMove", token="P1", vector=L.PTZ_VECTORS["left"]))
        self.assertIn("<tptz:ProfileToken>P1</tptz:ProfileToken>", L.onvif_body("GotoHomePosition", token="P1"))
        self.assertIn("<tptz:PanTilt>true</tptz:PanTilt>", L.onvif_body("Stop", token="P1"))
        self.assertEqual(L.onvif_xaddrs(CAPS.format(base="http://cam")),
                         {"media": "http://cam/onvif/Media", "ptz": "http://cam/onvif/PTZ"})
        self.assertEqual(L.onvif_profile_token(PROFILES), "Profile_1")
        self.assertEqual(L.onvif_time(TIME), 1795464900)
        self.assertEqual(L.onvif_fault(FAULT), "Sender not Authorized")
        self.assertIsNone(L.onvif_fault(OK % "Stop"))


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
        self.assertFalse(D.foscam_state(self.dev("foscam")))
        MockCamera.alarm = "2"
        self.assertTrue(D.foscam_state(self.dev("foscam")))
        D.ptz(self.dev("foscam"), "up", 0.01)
        D.ptz(self.dev("foscam"), "zoom_out", 0.01)
        D.ptz(self.dev("foscam"), "home")
        self.assertEqual(MockCamera.calls, ["getDevState", "getDevState", "ptzMoveUp", "ptzStopRun", "zoomOut",
                                            "zoomStop", "ptzReset"])
        with self.assertRaises(D.DeviceError) as e:
            D.ptz(self.dev("foscam", "wrong"), "up", 0.01)
        self.assertNotIn("wrong", str(e.exception))

    def test_onvif_ptz(self):
        orig = D.time.time
        D.time.time = lambda: 1795464900 - 3600  # receiver clock an hour behind: the camera clock is used
        try:
            D.ptz(self.dev("onvif"), "right", 0.01)
            D.ptz(self.dev("onvif"), "home")
        finally:
            D.time.time = orig
        actions = [(c[0], c[1]) for c in MockCamera.calls]
        self.assertEqual(actions, [("/onvif/device_service", "GetSystemDateAndTime"),
                                   ("/onvif/device_service", "GetCapabilities"), ("/onvif/Media", "GetProfiles"),
                                   ("/onvif/PTZ", "ContinuousMove"), ("/onvif/PTZ", "Stop"),
                                   ("/onvif/PTZ", "GotoHomePosition")])
        self.assertEqual(MockCamera.calls[-1][2], ["Profile_1"])

    def test_onvif_wrong_password(self):
        with self.assertRaises(D.DeviceError) as e:
            D.ptz(self.dev("onvif", "nope"), "left", 0.01)
        self.assertIn("Sender not Authorized", str(e.exception))
        self.assertNotIn("nope", str(e.exception))


if __name__ == "__main__":
    unittest.main()
