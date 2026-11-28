"""#11: privacy masks and guest mode in the core (the players only draw what these functions say)."""
import struct
import unittest

import _paths

_paths.core()
from camalert_core import privacy as p  # noqa: E402


def jpeg(w, h, progressive=False):
    sof = (b"\xff\xc2" if progressive else b"\xff\xc0") + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    return b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9 + sof + b"\xff\xd9"


class TestMasks(unittest.TestCase):
    def test_parse(self):
        m = p.parse_masks(" garden = 0,0,0.3,0.5 + 1,1,0.7,0.6 ; 0.1,0.1,0.1,0.9 |front_door=0.6,0.6,1.5,1|"
                          "drive=a,b,c,d|=0,0,1,1|nosep|back=0,0,1")
        self.assertEqual(m, {"garden": [(0.0, 0.0, 0.3, 0.5), (0.7, 0.6, 1.0, 1.0)],
                             "front_door": [(0.6, 0.6, 1.0, 1.0)]})  # zero width dropped, >1 clamped
        self.assertEqual(p.parse_masks(""), {})
        self.assertEqual(p.parse_masks(None), {})
        self.assertEqual(p.parse_masks("x=0,0,nan,1+0,0,inf,1"), {})
        many = "+".join("0,0,0.%d,1" % (i + 1) for i in range(10))
        self.assertEqual(len(p.parse_masks("x=" + many)["x"]), p.MAX_MASKS)
        self.assertEqual(p.parse_masks("x=0,0,0.5,0.5|x=0.5,0.5,1,1")["x"], [(0, 0, 0.5, 0.5), (0.5, 0.5, 1, 1)])

    def test_fit_rect(self):
        self.assertEqual(p.fit_rect((0, 0, 640, 480)), (0, 0, 640, 480))
        self.assertEqual(p.fit_rect((0, 0, 640, 480), (1920, 1080)), (0, 60, 640, 360))  # letterbox
        self.assertEqual(p.fit_rect((10, 20, 400, 400), (1080, 1920)), (97, 20, 225, 400))  # pillarbox
        self.assertEqual(p.fit_rect((0, 0, 640, 360), (0, 0)), (0, 0, 640, 360))

    def test_mask_rects_round_outwards(self):
        masks = {"garden": [(0.0, 0.0, 0.5, 0.5), (0.333, 0.333, 0.667, 0.667)]}
        self.assertEqual(p.mask_rects("other", masks, (0, 0, 640, 360)), [])
        r = p.mask_rects("garden", masks, (100, 50, 640, 480), (1920, 1080))
        self.assertEqual(r[0], (100, 110, 320, 180))
        x, y, w, h = r[1]
        self.assertLessEqual(x, 100 + 0.333 * 640)
        self.assertLessEqual(y, 110 + 0.333 * 360)
        self.assertGreaterEqual(x + w, 100 + 0.667 * 640)
        self.assertGreaterEqual(y + h, 110 + 0.667 * 360)
        full = p.mask_rects("g", {"g": [(0, 0, 1, 1)]}, (0, 0, 641, 361), (16, 9))
        self.assertEqual(full, [p.fit_rect((0, 0, 641, 361), (16, 9))])  # never outside the picture

    def test_jpeg_size(self):
        self.assertEqual(p.jpeg_size(jpeg(1280, 720)), (1280, 720))
        self.assertEqual(p.jpeg_size(jpeg(640, 480, progressive=True)), (640, 480))
        for bad in (b"", b"\x89PNG", b"\xff\xd8", b"\xff\xd8\xff\xda\x00\x02", jpeg(0, 720), None):
            self.assertIsNone(p.jpeg_size(bad))
        self.assertIsNone(p.jpeg_size(jpeg(1280, 720)[:12]))
        self.assertIsNone(p.jpeg_file_size("/nonexistent/x.jpg"))


class TestGuest(unittest.TestCase):
    def test_guest(self):
        self.assertFalse(p.guest_hidden("garden", False, ""))
        self.assertTrue(p.guest_hidden("garden", True, ""))  # empty list = all cameras
        self.assertTrue(p.guest_hidden("garden", True, "garden|drive"))
        self.assertFalse(p.guest_hidden("front_door", True, " garden , drive "))
        self.assertEqual(p.guest_visible(["a", "garden", "b"], True, "garden"), ["a", "b"])
        self.assertEqual(p.guest_visible(["a", "b"], False, "a"), ["a", "b"])
        self.assertEqual(p.guest_cameras("a b,c|d"), {"a", "b", "c", "d"})


if __name__ == "__main__":
    unittest.main()
