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
