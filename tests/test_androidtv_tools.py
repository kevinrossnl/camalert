"""players/androidtv/testing/fake_go2rtc_on_device.py (#64): neutral frames only, and a responder that answers
like go2rtc (run here with sh against the generated files instead of on a device)."""
import os
import subprocess
import tempfile
import unittest

import _paths

TOOL = os.path.join(_paths.PLAYERS, "androidtv", "testing")
_paths.add(TOOL)
import fake_go2rtc_on_device as F  # noqa: E402


class TestFakeOnDevice(unittest.TestCase):
    def ask(self, d, path):
        script = open(os.path.join(d, "serve.sh")).read().replace(F.DIR, d)
        req = "GET %s HTTP/1.0\r\nHost: x\r\n\r\n" % path
        return subprocess.run(["sh", "-c", script], input=req.encode(), stdout=subprocess.PIPE, check=True).stdout

    def test_answers_like_go2rtc(self):
        with tempfile.TemporaryDirectory() as d:
            F.files(d)
            self.assertEqual(sorted(x for x in os.listdir(d) if x.endswith(".img")),
                             sorted(n + ".img" for n in F.go2rtc.CAMERAS))
            out = self.ask(d, "/api/streams")
            self.assertTrue(out.startswith(b"HTTP/1.0 200 OK"))
            self.assertIn(b'"garden"', out)
            out = self.ask(d, "/api/frame.jpeg?src=garden&width=640")
            head, body = out.split(b"\r\n\r\n", 1)
            self.assertIn(b"Content-Length: %d" % len(body), head)
            self.assertEqual(body, open(os.path.join(d, "garden.img"), "rb").read())
            self.assertTrue(self.ask(d, "/api/frame.jpeg?src=driveway").startswith(b"HTTP/1.0 500"))
            self.assertTrue(self.ask(d, "/api/stream.mp4?src=garden").startswith(b"HTTP/1.0 500"))

    def test_commands(self):
        self.assertIn("127.0.0.1 -p 11984", F.start_command())
        self.assertIn("rm -rf /data/local/tmp/camfake", F.stop_command())


class TestScreenshots(unittest.TestCase):
    """players/androidtv/testing/screenshots.py (#69) with a fake adb and a fake CamAlert API: lock, crop, hide."""

    def setUp(self):
        import screenshots
        self.S = screenshots
        try:
            from PIL import Image
        except ImportError:  # pragma: no cover
            self.skipTest("Pillow not installed")
        import io
        img = Image.new("RGB", (1920, 1080), (40, 40, 40))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        self.png = buf.getvalue()
        self.lock = ""
        self.commands = []

    def fake_run(self, args, **kw):
        import types
        self.commands.append(args[3:])
        if args[3:5] == ["exec-out", "screencap"]:
            return types.SimpleNamespace(stdout=self.png)
        cmd = args[-1]
        out = ""
        if cmd.startswith("cat "):
            out = self.lock + "\n1795464900\n"
        elif cmd.startswith("echo "):
            self.lock = cmd.split("'")[1]
        elif cmd.startswith("rm -f"):
            self.lock = ""
        return types.SimpleNamespace(stdout=out.encode())

    def api(self):
        calls = []

        class Api(object):
            def call(self, name, **p):
                calls.append((name, p))
                if name == "cameras":
                    return {"result": True, "cameras": [{"name": "front_door"}]}
                return {"result": True, "position": "bottom_left", "size": "small"} if name == "status" else {}
        a = Api()
        a.calls = calls
        return a

    def test_takes_crops_and_cleans_up(self):
        from PIL import Image
        dev = self.S.Device("192.0.2.30:5555", "adb", run=self.fake_run)
        api = self.api()
        stripped = []
        with tempfile.TemporaryDirectory() as d:
            files = self.S.take(dev, api, ["photo", "mosaic", "settings"], d, wait=0, sleep=lambda s: None,
                                strip=stripped.append)
            self.assertEqual([os.path.basename(f) for f in files], ["photo.png", "mosaic.png", "settings.png"])
            photo = Image.open(files[0])
            self.assertLess(photo.size[0], 1920)  # cropped to the window: no launcher
            self.assertEqual(Image.open(files[1]).size, (1920, 1080))
        self.assertEqual(stripped, files)
        self.assertEqual(self.lock, "")  # lock given back
        names = [c[0] for c in api.calls]
        self.assertEqual(names[0], "status")
        self.assertEqual(names[-1], "hide")
        self.assertIn(("show", {"cam": "front_door", "mode": "photo", "sec": 60, "priority": "normal",
                                "label": "Person"}), api.calls)
        self.assertTrue(any("SettingsActivity" in " ".join(c) for c in self.commands))

    def test_switches_go2rtc_and_back(self):
        """CamAlert 1.3+: /camalert/setup to the fake go2rtc first, back to the app's own address at the end."""
        dev = self.S.Device("192.0.2.30:5555", "adb", run=self.fake_run)
        api = self.api()
        with tempfile.TemporaryDirectory() as d:
            self.S.take(dev, api, ["photo"], d, wait=0, sleep=lambda s: None, strip=lambda p: None,
                        restore_server="http://192.0.2.5:1984")
        setups = [c[1]["server"] for c in api.calls if c[0] == "setup"]
        self.assertEqual(setups, ["http://127.0.0.1:11984", "http://192.0.2.5:1984"])
        self.assertEqual(api.calls[-1], ("setup", {"server": "http://192.0.2.5:1984"}))
        self.assertEqual(self.lock, "")

    def test_busy_device_is_left_alone(self):
        dev = self.S.Device("192.0.2.30:5555", "adb", run=self.fake_run)
        self.lock = "D 1795464000"  # 15 minutes old
        api = self.api()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(self.S.Busy):
                self.S.take(dev, api, ["photo"], d, wait=0, sleep=lambda s: None, strip=lambda p: None)
        self.assertEqual(self.lock, "D 1795464000")  # someone else's lock stays
        self.assertEqual(api.calls, [])
        self.lock = "D 1795400000"  # stale: taken over and freed again
        with tempfile.TemporaryDirectory() as d:
            self.S.take(dev, api, ["mosaic"], d, wait=0, sleep=lambda s: None, strip=lambda p: None)
        self.assertEqual(self.lock, "")

    def test_crop_box_inside_the_screen(self):
        for pos in ("top_left", "top_right", "bottom_left", "bottom_right"):
            for scene in ("photo", "strip"):
                x0, y0, x1, y1 = self.S.crop_box(scene, {"position": pos, "size": "large"}, 1920, 1080)
                self.assertTrue(0 <= x0 < x1 <= 1920 and 0 <= y0 < y1 <= 1080, (pos, scene))
        self.assertIsNone(self.S.crop_box("mosaic", {}, 1920, 1080))


if __name__ == "__main__":
    unittest.main()


class TestApkListing(unittest.TestCase):
    BADGING = ("package: name='org.camalert.tv' versionCode='1' versionName='1.2.3' platformBuildVersionName='17' "
               "compileSdkVersion='37'\nminSdkVersion:'25'\napplication-icon-160:'res/drawable/icon.xml'\n"
               "uses-permission: name='android.permission.INTERNET'\n")

    def test_listing(self):
        import zipfile
        _paths.tools()
        import apk_listing as L
        with tempfile.TemporaryDirectory() as d:
            apk = os.path.join(d, "a.apk")
            with zipfile.ZipFile(apk, "w") as z:
                for n in ("classes.dex", "classes2.dex", "AndroidManifest.xml", "camalert/core.json",
                          "res/drawable/icon.xml", "res/xx/other.xml", "META-INF/x.properties"):
                    z.writestr(n, "x")
            text = L.listing(apk, self.BADGING)
            self.assertIn("dex files: yes\nfile AndroidManifest.xml\nfile camalert/core.json\n", text)
            self.assertIn("res res/drawable/icon.xml\nmissing res/drawable/banner.xml", text)
            self.assertIn("badging package: name='org.camalert.tv' versionCode='1' versionName='@VERSION@'\n", text)
            self.assertNotIn("other.xml", text)
            self.assertNotIn("application-icon", text)
            golden = os.path.join(d, "golden.txt")
            open(golden, "w").write(text)
            self.assertIn("androidtv_apk.txt", L.GOLDEN)
            self.assertTrue(os.path.exists(L.GOLDEN))
