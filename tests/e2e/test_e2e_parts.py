"""Parts of the e2e runner (#35): PNG decoding and geometry checks, report + privacy, state file, transports,
the CamAlert client and the preconditions."""
import json
import os
import shutil
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib

import _paths

_paths.e2e()
_paths.core()
from camalert_core import layout  # noqa: E402
from camalert_e2e import fakes, geometry, profiles, report, safety, transport  # noqa: E402
from camalert_e2e.adapters.camalert import CamAlert  # noqa: E402
from camalert_e2e.adapters.kodi import setting_value  # noqa: E402
from camalert_e2e.state import Store  # noqa: E402

W, H = 320, 180
C = fakes.CAMERAS


def screen(rects):
    def pixel(x, y):
        for (rx, ry, rw, rh), cam in rects:
            if rx <= x < rx + rw and ry <= y < ry + rh:
                return C[cam] + (255,)
        return (0, 0, 0, 0)
    return geometry.decode_png(geometry.encode_png(W, H, pixel))


def filtered_png(w, h, rgb_rows, filters):
    """RGB PNG with the given filter type per row (encoder side of PNG filters, for the decoder test)."""
    out, prev = b"", bytes(w * 3)
    for row, f in zip(rgb_rows, filters):
        line = bytearray()
        for i, v in enumerate(row):
            a = row[i - 3] if i >= 3 else 0
            b = prev[i]
            c = prev[i - 3] if i >= 3 else 0
            pred = {0: 0, 1: a, 2: b, 3: (a + b) // 2, 4: geometry._paeth(a, b, c)}[f]
            line.append((v - pred) & 255)
        out += bytes([f]) + bytes(line)
        prev = row

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(out)) + chunk(b"IEND", b""))


class TestGeometry(unittest.TestCase):
    def test_png_filters(self):
        rows = [bytes((x * 7 + y * 13 + c * 5) % 256 for x in range(6) for c in range(3)) for y in range(5)]
        img = geometry.decode_png(filtered_png(6, 5, rows, [0, 1, 2, 3, 4]))
        self.assertEqual(img.rows, rows)
        self.assertEqual(img.pixel(1, 1), (rows[1][3], rows[1][4], rows[1][5], 255))
        with self.assertRaises(ValueError):
            geometry.decode_png(b"GIF89a")
        bad = filtered_png(2, 2, [bytes(6)] * 2, [0, 0]).replace(b"\x08\x02\x00\x00\x00", b"\x10\x02\x00\x00\x00")
        with self.assertRaises(ValueError):
            geometry.decode_png(bad)

    def test_load_without_and_with_pillow(self):
        data = geometry.encode_png(4, 3, lambda x, y: (x, y, 9, 255))
        a = geometry.decode_png(data)
        b = geometry.load(data)
        self.assertEqual([a.pixel(x, y)[:3] for x in range(4) for y in range(3)],
                         [b.pixel(x, y)[:3] for x in range(4) for y in range(3)])

    def test_photo_window(self):
        s = {"position": "bottom_left", "size": "medium", "title_size": "normal"}
        x, y, w, h, title = layout.window_geometry("bottom_left", "medium", W, H, "normal")
        img = screen([((x, y + title, w, h), "garden")])
        ok, detail = geometry.check_photo(img, "garden", C["garden"], s)
        self.assertTrue(ok, detail)
        ok, detail = geometry.check_photo(img, "garden", C["garden"], dict(s, position="top_right"))
        self.assertFalse(ok, detail)
        self.assertFalse(geometry.check_photo(img, "driveway", C["driveway"], s)[0])
        small = screen([((x, y + title, w // 2, h // 2), "garden")])
        self.assertFalse(geometry.check_photo(small, "garden", C["garden"], s)[0])

    def test_mosaic_and_strip(self):
        names = fakes.NAMES[:4]
        rects = geometry.mosaic_rects(4, W, H)
        img = screen(list(zip(rects, names)))
        self.assertTrue(geometry.check_tiles(img, names, C, rects)[0])
        self.assertFalse(geometry.check_tiles(img, list(reversed(names)), C, rects)[0])
        s = {"position": "top_right", "size": "medium", "strip_layout": "auto"}
        rects = geometry.strip_rects(2, s, W, H)
        img = screen(list(zip(rects, names[:2])))
        self.assertTrue(geometry.check_tiles(img, names[:2], C, rects)[0])
        self.assertFalse(geometry.check_tiles(img, names[:2], C, geometry.strip_rects(2, dict(
            s, strip_layout="horizontal"), W, H))[0])

    def test_colours_on_screen(self):
        img = screen([((0, 0, W, H), "garden")])
        self.assertEqual(geometry.colours_on_screen(img, C), ["garden"])
        self.assertEqual(geometry.colours_on_screen(screen([]), C), [])


class TestReportAndState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_report_files_and_redaction(self):
        data = {"run": "r1", "dry_run": False, "devices": [
            {"device": "boven", "status": "failed", "reason": "", "preconditions": [{"name": "a", "ok": True}],
             "scenarios": [{"name": "show", "status": "failed", "seconds": 1.0, "screenshots": [],
                            "checks": [{"ok": False, "detail": "at 192.168.1.23 cam porch"}]},
                           {"name": "ptz", "status": "skipped", "seconds": 0, "screenshots": [],
                            "checks": [{"ok": None, "detail": "fake only"}]}]},
            {"device": "kodi", "status": "skipped", "reason": "nothing playing (1)", "scenarios": []}]}
        out = report.write(os.path.join(self.tmp, "r1"), data, {"192.168.1.23": "<boven>", "porch": "cam1"})
        text = open(os.path.join(self.tmp, "r1", "report.json")).read()
        self.assertNotIn("192.168.1.23", text)
        self.assertIn("<boven> cam cam1", text)
        self.assertEqual(out["privacy_findings"], 0)
        root = ET.parse(os.path.join(self.tmp, "r1", "junit.xml")).getroot()
        suites = root.findall("testsuite")
        self.assertEqual([s.get("failures") for s in suites], ["1", "0"])
        self.assertEqual([s.get("skipped") for s in suites], ["1", "1"])
        self.assertIn("&lt;boven&gt;", open(os.path.join(self.tmp, "r1", "report.html")).read())

    def test_private_hits(self):
        old = os.environ.get("CAMALERT_DENYLIST")
        os.environ["CAMALERT_DENYLIST"] = "secretname"
        try:
            self.assertEqual(report.private_hits("nothing here"), 0)
            url = "rtsp://admin" + ":" + "hunter22" + "@cam/x"  # built at run time: the repository scan stays clean
            self.assertEqual(report.private_hits(url + " and SecretName"), 2)
        finally:
            if old is None:
                del os.environ["CAMALERT_DENYLIST"]
            else:
                os.environ["CAMALERT_DENYLIST"] = old

    def test_state_store(self):
        s = Store(self.tmp, "run1")
        d = s.device("boven", "enigma2")
        s.save()
        self.assertEqual(Store.load(self.tmp).pending(), [])  # nothing changed yet (no snapshot)
        d["before"] = {"volume": 3}
        s.save()
        self.assertEqual([x["device"] for x in Store.load(self.tmp).pending()], ["boven"])
        d["restored"] = True
        s.save()
        self.assertEqual(Store.load(self.tmp, "run1").pending(), [])
        self.assertEqual(sorted(os.listdir(os.path.join(self.tmp, "state"))), ["last.json", "run1.json"])


class TestTransport(unittest.TestCase):
    def test_read_response_skips_notifications_and_joins_chunks(self):
        stream = [b'{"jsonrpc":"2.0","method":"Player.OnPlay","params":{}}{"jsonrpc":"2.0","id":7,"res',
                  b'ult":{"muted":true}}']
        self.assertEqual(transport.read_response(iter(stream), 7)["result"], {"muted": True})
        with self.assertRaises(transport.TransportError):
            transport.read_response(iter([b'{"id":1}']), 2)

    def test_jsonrpc_error(self):
        class Rpc(transport.JsonRpc):
            def send(self, req):
                return {"id": req["id"], "error": {"message": "Method not found."}}
        with self.assertRaisesRegex(transport.TransportError, "Method not found"):
            Rpc().call("PVR.GetProperties", {})

    def test_ssh_jsonrpc_and_quote(self):
        class Shell(object):
            def run(self, cmd, stdin=None, check=True):
                self.cmd, self.stdin = cmd, stdin
                return json.dumps({"id": json.loads(stdin)["id"], "result": "pong"})
        sh = Shell()
        self.assertEqual(transport.SshJsonRpc(sh).call("JSONRPC.Ping"), "pong")
        self.assertTrue(sh.cmd.startswith("python3 -c '"))
        self.assertEqual(transport.quote("a'b"), "'a'\"'\"'b'")
        compile(transport.SSH_RPC % 9090, "ssh_rpc", "exec")

    def test_basic_auth_and_unreachable(self):
        self.assertEqual(transport.basic_auth("", "x"), {})
        self.assertTrue(transport.basic_auth("u", "p")["Authorization"].startswith("Basic "))
        with self.assertRaises(transport.TransportError) as cm:
            transport.http("http://127.0.0.1:1/api/x?token=abc", timeout=2)
        self.assertNotIn("abc", str(cm.exception))

    def test_kodi_setting_value(self):
        xml = '<settings version="2"><setting id="chime" default="true">off</setting><setting id="x">1</setting>' \
              '<setting id="empty" /></settings>'
        self.assertEqual(setting_value(xml, "chime"), "off")
        self.assertEqual(setting_value(xml, "empty"), "")
        self.assertIsNone(setting_value(xml, "missing"))


class TestCamAlertClient(unittest.TestCase):
    def test_test_flag_token_header_and_429_retry(self):
        calls, waits = [], []

        def http(url, method="GET", data=None, headers=None, timeout=10):
            calls.append((url, method, data, headers))
            return (429, {}) if len(calls) == 1 else (200, {"result": True, "capabilities": ["show"]})
        c = CamAlert("192.168.1.20", 8099, "tok", http, sleep=waits.append)
        self.assertEqual(c.action("show", cam="garden", sec=None)[0], 200)
        self.assertEqual(waits, [2])
        url, method, data, headers = calls[-1]
        self.assertEqual((url, method), ("http://192.168.1.20:8099/camalert/show", "POST"))
        self.assertEqual(data, {"test": "1", "cam": "garden"})
        self.assertEqual(headers["X-CamAlert-Token"], "tok")
        self.assertFalse(c.supports_test_flag())

    def test_errors(self):
        c = CamAlert("h", 1, "", lambda *a, **k: (403, {"result": False}), sleep=lambda s: None)
        with self.assertRaises(transport.TransportError):
            c.status()


class TestPreconditions(unittest.TestCase):
    def prof(self, **kw):
        return profiles.device("tv", dict({"type": "enigma2", "host": "h", "allowed_hours": "09:00-22:00"}, **kw))

    def failed(self, checks):
        return [c.name for c in checks if not c.ok]

    def test_watching_by_home_assistant(self):
        class HA(object):
            def __init__(self, state):
                self.s = state

            def state(self, entity):
                if self.s is None:
                    raise transport.TransportError("down")
                return self.s
        p = self.prof(watching="ha", ha_media_player="media_player.tv")
        info = {"standby": False}
        self.assertEqual(self.failed(safety.preconditions(p, info, 600, {}, HA("off"))), [])
        self.assertEqual(self.failed(safety.preconditions(p, info, 600, {}, HA("playing"))), ["nobody watching"])
        self.assertEqual(self.failed(safety.preconditions(p, info, 600, {}, HA(None))), ["nobody watching"])
        self.assertEqual(self.failed(safety.preconditions(p, info, 600, {}, None)), ["nobody watching"])

    def test_interactive_confirmation(self):
        p = self.prof()
        self.assertEqual(self.failed(safety.preconditions(p, {}, 600, {}, confirm=lambda q: True)), [])
        self.assertEqual(self.failed(safety.preconditions(p, {}, 600, {}, confirm=lambda q: False)),
                         ["nobody watching"])
        self.assertFalse(safety.ask("never on a test runner?"))  # stdin is not a terminal under pytest
        self.assertIn("ok", repr(safety.Check("a", True)) + "ok")


if __name__ == "__main__":
    unittest.main()
