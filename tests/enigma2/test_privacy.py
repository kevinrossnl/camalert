"""#11: privacy masks (black boxes over every CamAlert picture of a camera and over its live video) and guest mode
(requests for the guest cameras are ignored, the mosaic and tour leave them out)."""
import os
import struct
import time
import types
import unittest

import _paths  # noqa: F401
from enigma2.harness import e2fake

SNAP = "http://192.168.1.10:1984/api/frame.jpeg?src=%s&width=640"


def jpeg(w, h):
    """The headers of a JPEG of w x h: enough for jpeg_size (the fake picture decoder needs only the file)."""
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 4) + b"JF" + sof + b"\xff\xd9"


class Recorder(object):
    def __init__(self, widget):
        self.widget, self.pos, self.size = widget, None, None
        widget.instance = types.SimpleNamespace(move=self.move, resize=self.resize, setPixmap=lambda p: None,
                                                show=lambda: None, hide=lambda: None)

    def move(self, p):
        self.pos = (p.x(), p.y()) if callable(getattr(p, "x", None)) else (p.x, p.y)

    def resize(self, s):
        self.size = (s.width(), s.height()) if callable(getattr(s, "width", None)) else (s.w, s.h)


class TestPrivacy(unittest.TestCase):
    def setUp(self):
        self.env = e2fake.install("openatv")
        self.d = self.env.camalert.display
        self.c = self.env.config.plugins.camalert
        self.session = self.env.Session()
        self.env.InfoBar(self.session)
        self.c.server.value = "http://192.168.1.10:1984"
        self.env.camalert.plugin.sessionstart(0, session=self.session)
        self.ctl = self.d.Controller.instance
        self.ctl._names, self.ctl._names_at = ["front_door", "garden", "drive"], time.time()
        self.files = []

    def tearDown(self):
        e2fake.uninstall()
        for p in self.files:
            if os.path.exists(p):
                os.remove(p)

    def picture(self, path, w, h):
        with open(path, "wb") as f:
            f.write(jpeg(w, h))
        self.files.append(path)

    def boxes(self, screen, prefix="mask"):
        return [k for k in screen if k.startswith(prefix)]

    def test_no_masks_no_widgets(self):
        w = self.session.instantiateDialog(self.d.PhotoWindow, "garden", SNAP % "garden", "Garden")
        self.assertEqual(self.boxes(w), [])
        self.c.privacy_masks.value = "drive=0,0,1,1"
        w = self.session.instantiateDialog(self.d.PhotoWindow, "garden", SNAP % "garden", "Garden")
        self.assertEqual(len(self.boxes(w)), 8)
        for fn in w.onLayoutFinish:
            fn()
        w.active = True
        self.picture(self.d.PHOTO, 1280, 720)
        w.loaded(None)
        self.assertFalse(any(w[k].visible for k in self.boxes(w)))  # garden has no masks

    def test_photo_window_covers_the_masked_area(self):
        self.c.privacy_masks.value = "garden=0,0,0.5,0.5+0.75,0.75,1,1"
        w = self.session.instantiateDialog(self.d.PhotoWindow, "garden", SNAP % "garden", "Garden")
        rec = [Recorder(w["mask%d" % i]) for i in range(8)]
        for fn in w.onLayoutFinish:
            fn()
        self.assertFalse(any(w["mask%d" % i].visible for i in range(8)))
        w.active = True
        self.picture(self.d.PHOTO, 1280, 720)
        w.loaded(None)
        x, y, bw, bh = w.box
        self.assertTrue(w["mask0"].visible and w["mask1"].visible)
        self.assertFalse(w["mask2"].visible)
        want = self.d.mask_rects("garden", self.d.current_masks(), w.box, (1280, 720))
        self.assertEqual(rec[0].pos + rec[0].size, want[0])  # where the picture is drawn, in its aspect ratio
        self.assertEqual(rec[1].pos + rec[1].size, want[1])
        self.assertEqual(self.d.IMAGE_SIZES["garden"], (1280, 720))

    def test_mosaic_tiles_and_live_video(self):
        self.c.privacy_masks.value = "front_door=0.5,0,1,1"
        cams = [("front_door", "Front door", SNAP % "front_door"), ("garden", "Garden", SNAP % "garden")]
        m = self.session.instantiateDialog(self.d.MosaicScreen, cams, 0)
        self.assertEqual(len(self.boxes(m, "mask0_")), 8)
        self.assertEqual(len(self.boxes(m, "mask1_")), 8)
        for fn in m.onLayoutFinish:
            fn()
        m.active = True
        t = m.tiles[0]
        self.picture(t.path, 640, 360)
        t.loaded(None)
        self.assertTrue(m["mask0_0"].visible)
        self.assertFalse(any(m["mask1_%d" % i].visible for i in range(8)))
        # live view of the masked camera: a transparent layer with the boxes, gone when the live view ends
        self.ctl.show_live_masks("front_door")
        self.assertIsNotNone(self.ctl.mask_screen)
        self.assertTrue(self.ctl.mask_screen["mask0"].visible)
        self.ctl.show_live_masks("garden")  # another camera without masks: layer removed
        self.assertIsNone(self.ctl.mask_screen)
        self.ctl.show_live_masks("front_door")
        self.ctl.end_live()
        self.assertIsNone(self.ctl.mask_screen)

    def test_guest_mode(self):
        self.c.guest_mode.value = True
        self.c.guest_cameras.value = "garden"
        self.assertEqual(self.ctl.show("garden", 10, "photo", "high"), "ignore")
        self.assertEqual(self.ctl.reason, "guest")
        self.assertEqual(self.ctl.show("garden", 10, "photo", "alarm"), "ignore")  # guest mode is a hard rule
        self.assertNotEqual(self.ctl.show("front_door", 10, "photo", "high"), "ignore")
        self.assertEqual(self.d.overview_names(["front_door", "garden", "drive"]), ["front_door", "drive"])
        self.c.guest_cameras.value = ""  # all cameras
        self.assertEqual(self.ctl.show("front_door", 10, "photo", "high"), "ignore")
        self.assertEqual(self.ctl.mosaic("front_door,garden"), "ignore")
        self.c.guest_mode.value = False
        self.assertEqual(self.d.overview_names(["front_door", "garden"]), ["front_door", "garden"])


if __name__ == "__main__":
    unittest.main()
