"""tests/kodi_container/smoke.py (#37): the parts that need no Kodi (the nightly job runs the real thing)."""
import os
import sys
import tempfile
import unittest

import _paths

sys.path.insert(0, os.path.join(_paths.ROOT, "tests", "kodi_container"))
import smoke  # noqa: E402


class TestKodiSmoke(unittest.TestCase):
    def log(self, text):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "kodi.log")
        with open(p, "w") as f:
            f.write(text)
        self.addCleanup(lambda: (os.remove(p), os.rmdir(d)))
        return p

    def test_addon_exceptions_are_found(self):
        ok = self.log("info <general>: [CamAlert] version 1.3.1 starting\n"
                      "error <general>: EXCEPTION Thrown (PythonToCppException) : -->Python callback/script returned "
                      "the following error<--\n Traceback (most recent call last):\n  File \"/x/other.addon/a.py\"\n")
        self.assertEqual(smoke.addon_errors(ok), [])  # another add-on's error is not ours
        bad = self.log("error <general>: EXCEPTION Thrown (PythonToCppException)\nTraceback (most recent call last):\n"
                       "  File \"/home/.kodi/addons/service.camalert/resources/lib/camalert/display.py\", line 3\n"
                       "ValueError: boom\n")
        self.assertTrue(smoke.addon_errors(bad))
        self.assertEqual(smoke.addon_errors("/nonexistent/kodi.log"), ["kodi.log missing"])

    def test_web_server_only_local_without_login(self):
        self.assertIn('<setting id="services.webserver">true</setting>', smoke.GUISETTINGS)
        self.assertIn('<setting id="services.esallinterfaces">false</setting>', smoke.GUISETTINGS)
        self.assertIn('<setting id="services.webserverauthentication">false</setting>', smoke.GUISETTINGS)

    def test_prepare_unpacks_the_add_on(self):
        with tempfile.TemporaryDirectory() as home:
            name = smoke.prepare(home)
            self.assertTrue(name.startswith("service.camalert-"))
            self.assertTrue(os.path.exists(os.path.join(home, ".kodi", "addons", "service.camalert", "addon.xml")))
            self.assertTrue(os.path.exists(os.path.join(home, ".kodi", "userdata", "guisettings.xml")))


if __name__ == "__main__":
    unittest.main()
