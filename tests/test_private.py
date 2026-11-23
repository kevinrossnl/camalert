import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import check_private as C  # noqa: E402


class TestPrivacyCheck(unittest.TestCase):
    def test_detects(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "a.md"), "w").write("rtsp://admin:" + "hunter22@cam/x\nhttps://ntfy" + ".sh/abcdefgh123\n")
            open(os.path.join(d, "b.md"), "w").write("my house is at example-home.lan\n")
            p = C.problems(d, ["example-home.lan"])
            self.assertTrue(any("password in URL" in x for x in p))
            self.assertTrue(any("ntfy" in x for x in p))
            self.assertTrue(any("denylisted" in x for x in p))
            self.assertFalse(any("example-home" in x for x in p), "never print the denylisted word itself")

    def test_placeholders_are_fine(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "a.md"), "w").write("rtsp://admin:<password>@192.168.1.20:554/x\nrtsp://user:{PASSWORD}@cam\n")
            self.assertEqual(C.problems(d, []), [])

    def test_repository_is_clean(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        self.assertEqual(C.problems(root, C.denylist()), [])


if __name__ == "__main__":
    unittest.main()
