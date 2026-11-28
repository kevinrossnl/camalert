"""#11 on Kodi: privacy masks (black boxes over the camera pictures, the mosaic, the tour, the live still, live video
and the video window) and guest mode (requests for guest cameras are ignored, mosaic and tour leave them out)."""
import unittest

import _paths  # noqa: F401
from kodi.test_kodi import Built, FakeController


class Box(object):
    """A recording stand-in for the image controls that place_masks moves."""

    def __init__(self):
        self.pos, self.w, self.h, self.visible = None, None, None, None

    def setPosition(self, x, y):
        self.pos = (x, y)

    def setWidth(self, w):
        self.w = w

    def setHeight(self, h):
        self.h = h

    def setVisible(self, v):
        self.visible = v


CAMS = [("front_door", "Front door", "http://192.168.1.10:1984/api/frame.jpeg?src=front_door&width=640"),
        ("garden", "Garden", "http://192.168.1.10:1984/api/frame.jpeg?src=garden&width=640")]


class TestKodiPrivacy(unittest.TestCase):
    def settings(self, **kw):
        return dict(Built.module("klogic").parse_settings({}), **kw)

    def test_place_masks(self):
        display = Built.module("display")
        s = self.settings(privacy_masks="garden=0,0,0.5,0.5+0.5,0.5,1,1")
        boxes = [Box() for _ in range(8)]
        display.place_masks(boxes, "garden", s, (100, 50, 640, 480), (1920, 1080))
        self.assertEqual((boxes[0].pos, boxes[0].w, boxes[0].h, boxes[0].visible), ((100, 110), 320, 180, True))
        self.assertTrue(boxes[1].visible)
        self.assertFalse(any(b.visible for b in boxes[2:]))
        self.assertEqual(display.IMAGE_SIZES["garden"], (1920, 1080))
        display.place_masks(boxes, "front_door", s, (100, 50, 640, 480))  # no masks for this camera
        self.assertFalse(any(b.visible for b in boxes))
        display.place_masks([], "garden", s, (0, 0, 10, 10))  # nothing to place: no error

    def test_windows_get_mask_boxes_only_with_masks(self):
        display = Built.module("display")
        plain = display.PhotoWindow(FakeController(), CAMS[:1], self.settings(), keys=True)
        self.assertEqual(plain.tiles[0]["masks"], [])
        s = self.settings(privacy_masks="garden=0,0,1,0.2")
        for cams in (CAMS[:1], CAMS):
            w = display.PhotoWindow(FakeController(), cams, s, keys=True)
            self.assertTrue(all(len(t["masks"]) == 8 for t in w.tiles))
            self.assertTrue(all(len(t["box"]) == 4 for t in w.tiles))
            if w.timer:
                w.timer.cancel()
        for tour in (False, True):
            f = display.FullScreen(FakeController(), CAMS, s, tour=tour)
            self.assertTrue(all(len(t["masks"]) == 8 for t in f.tiles))
            f.feeder.stop()
        o = display.LiveOverlay(FakeController(), "garden", "Garden", s)
        self.assertEqual(len(o.masks), 8)
        self.assertEqual(display.LiveOverlay(FakeController(), "garden", "Garden", self.settings()).masks, [])

    def test_video_window_xml_has_mask_boxes(self):
        klogic = Built.module("klogic")
        plain = klogic.video_window_xml(10, 20, 400, 225, 30, "font13", "font12", 22)
        masked = klogic.video_window_xml(10, 20, 400, 225, 30, "font13", "font12", 22, masks=True)
        self.assertNotIn('id="120"', plain)
        for cid in klogic.VIDEO_MASKS:
            self.assertIn('id="%d"' % cid, masked)
        self.assertLess(masked.index("videowindow"), masked.index('id="120"'))  # on top of the video

    def test_guest_mode(self):
        ctl_mod = Built.module("controller")
        sources = Built.module("sources")
        Built.store.update({"guest_mode": "true", "guest_cameras": "garden", "server": "http://192.168.1.10:1984"})
        self.addCleanup(lambda: [Built.store.pop(k, None) for k in ("guest_mode", "guest_cameras", "server")])
        ctl = ctl_mod.Controller()
        ctl.names, ctl.names_at = ["front_door", "garden"], 9e12
        ctl.screen_off = lambda: False
        ctl.end_screensaver = lambda: None
        self.assertEqual(ctl._show("garden", 10, "photo", "alarm"), "ignore")
        self.assertEqual(ctl.reason, "guest")
        self.assertEqual(sources.guest_filter(["front_door", "garden"]), ["front_door"])
        self.assertEqual(sources.overview_names(["front_door", "garden"]), ["front_door"])
        Built.store["guest_cameras"] = ""  # all cameras
        self.assertEqual(ctl._show("front_door,garden", 10, "photo", "high"), "ignore")
        self.assertEqual(ctl._fullscreen("front_door,garden", 10, False), "ignore")
        Built.store["guest_mode"] = "false"
        self.assertEqual(sources.guest_filter(["front_door", "garden"]), ["front_door", "garden"])


if __name__ == "__main__":
    unittest.main()
