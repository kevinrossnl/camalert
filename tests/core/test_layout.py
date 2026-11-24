"""camalert_core.layout: window and tile geometry."""
import unittest

import _paths

_paths.core()
from camalert_core import cameras  # noqa: E402
from camalert_core import layout  # noqa: E402


class TestLayout(unittest.TestCase):
    def test_parse_cams_and_grid(self):
        self.assertEqual(cameras.parse_cams("front_door, garden garden;x"), ["front_door", "garden"])
        self.assertEqual(len(cameras.parse_cams(",".join("c%d" % i for i in range(12)))), 9)
        tiles = layout.grid(4, 1920, 1080)
        self.assertEqual(len(tiles), 4)
        for x, y, w, h in tiles:
            self.assertTrue(0 <= x and x + w <= 1920 and 0 <= y and y + h <= 1080)
            self.assertLessEqual(abs(w * 9 // 16 - h), 1)
        self.assertEqual(len(layout.grid(5, 1280, 720)), 5)
        self.assertEqual(layout.grid(1, 1920, 1080)[0][2] > 1800, True)

    def test_strip(self):
        self.assertEqual(layout.strip_layout(2), "vertical")
        self.assertEqual(layout.strip_layout(4), "grid")
        self.assertEqual(layout.strip_layout(3, "horizontal"), "horizontal")
        x, y, w, h, t, tiles = layout.strip_geometry(3, "vertical", "top_right", "medium", 1920, 1080)
        self.assertEqual(len(tiles), 3)
        self.assertTrue(x + w <= 1920 and y + h + t <= 1080 and x >= 0 and y >= 0)
        for tx, ty, tw, th in tiles:
            self.assertTrue(tx + tw <= w and ty + th <= h + t)
        x, y, w, h, t, tiles = layout.strip_geometry(4, "grid", "bottom_left", "large", 1280, 720)
        self.assertEqual(x, 26)
        self.assertTrue(y + h + t <= 720)
        x, y, w, h, t, tiles = layout.strip_geometry(2, "horizontal", "top_left", "small", 1920, 1080)
        self.assertEqual(tiles[1][0], tiles[0][2] + 6)

    def test_geometry(self):
        self.assertEqual(layout.window_geometry("top_right", "medium", 1920, 1080), (1240, 40, 640, 360, 40))
        x, y, w, h, t = layout.window_geometry("bottom_left", "small", 1280, 720)
        self.assertEqual((x, w), (26, 320))
        self.assertEqual(y + h + t, 720 - 26)

    def test_title_size(self):
        self.assertEqual(layout.window_geometry("top_right", "medium", 1920, 1080, "large")[4], 56)
        self.assertEqual(layout.window_geometry("top_right", "medium", 1280, 720)[4], 26)
        self.assertEqual(layout.title_font("small", 1920), 22)


if __name__ == "__main__":
    unittest.main()
