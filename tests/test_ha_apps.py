"""#95: the light-player helpers of the Home Assistant integration (custom_components/camalert/apps.py), without
Home Assistant. Rules and the camera list are copies of the core: they must give the same answers."""
import itertools
import json
import unittest

import _paths  # noqa: E402

_paths.add(_paths.HA)
_paths.core()
import apps  # noqa: E402  (no Home Assistant imports at module level)
from camalert_core import api as core_api  # noqa: E402
from camalert_core import rules, urls  # noqa: E402

REAL = "rtsp://127.0.0.1:8554/front_door?video&source=ffmpeg:front_door%23video%3Dmjpeg%23width%3D640"
STREAMS = {
    "front_door": {"producers": [{"url": "rtsp://192.168.1.10:7447/abc"}]},
    "front_door_jpeg": {"producers": [{"url": "ffmpeg:front_door#video=mjpeg#width=640"}]},
    "running_jpeg": {"producers": [{"url": REAL}]},
    "garden": {"producers": [{"url": "ffmpeg:rtsp://192.168.1.11/stream1#video=h264"}]},
    "orphan": {"producers": [{"url": "ffmpeg:gone#video=mjpeg"}]},
    "bad name!": {},
    "empty": {},
}


class TestRulesAreTheCore(unittest.TestCase):
    def test_dnd_and_hours(self):
        for prio, on, level in itertools.product(apps.PRIORITIES, (False, True), rules.DND_LEVELS):
            self.assertEqual(apps.dnd_blocks(prio, on, level), rules.dnd_blocks(prio, on, level), (prio, on, level))
        times = [(h, m) for h in range(24) for m in (0, 30)]
        for now, start, end in itertools.product(times[::5], times[::7], times[::11]):
            self.assertEqual(apps.in_time_window(now, start, end), rules.in_time_window(now, start, end))

    def test_seconds(self):
        for v in (None, "", "x", 0, "0", 1, 5, 30, 299, 300, 301, 10 ** 9, float("inf"), -3):
            self.assertEqual(apps.show_seconds(v), rules.show_seconds(v), v)
        self.assertEqual((apps.MIN_SECONDS, apps.MAX_SECONDS, apps.HOLD_SECONDS),
                         (rules.MIN_SECONDS, rules.MAX_SECONDS, rules.HOLD_SECONDS))

    def test_blocked(self):
        hours = {"active_from": "18:00:00", "active_until": "23:00:00"}
        self.assertEqual(apps.blocked("normal", hours, (12, 0)), "active_hours")
        self.assertIsNone(apps.blocked("high", hours, (12, 0)))
        self.assertIsNone(apps.blocked("normal", hours, (19, 0)))
        self.assertIsNone(apps.blocked("normal", {"active_from": "", "active_until": ""}, (3, 0)))  # all day
        self.assertEqual(apps.blocked("normal", dict(hours, dnd=True), (19, 0)), "dnd")
        self.assertEqual(apps.blocked("high", {"dnd": True, "dnd_level": "high"}, (19, 0)), "dnd")
        self.assertIsNone(apps.blocked("alarm", {"dnd": True, "dnd_level": "high"}, (12, 0)))


class TestCameras(unittest.TestCase):
    def test_same_list_as_the_players(self):
        text = json.dumps(STREAMS)
        self.assertEqual(apps.stream_names(text), urls.streams_from_json(text))
        self.assertEqual(apps.stream_names(text), ["empty", "front_door", "garden", "orphan"])
        self.assertEqual(apps.derived_streams(STREAMS), urls.derived_streams(STREAMS))
        self.assertEqual(apps.stream_names("not json"), [])

    def test_titles_and_urls(self):
        self.assertEqual(apps.title("front_door"), "Front door")
        self.assertEqual(apps.normalize_server("192.168.1.10:1984/"), "http://192.168.1.10:1984")
        self.assertEqual(apps.normalize_server("https://go2rtc.local"), "https://go2rtc.local")
        for bad in ("", "ftp://x", "http://user:pw@192.168.1.10:1984", "http://192.168.1.10:1984/api"):
            self.assertEqual(apps.normalize_server(bad), "", bad)
        self.assertEqual(apps.frame_url("http://192.168.1.10:1984", "a b", 480),
                         "http://192.168.1.10:1984/api/frame.jpeg?src=a%20b&width=480")
        self.assertEqual(apps.rtsp_url("http://192.168.1.10:1984", "garden"), "rtsp://192.168.1.10:8554/garden")
        self.assertEqual(apps.rtsp_url("http://[fd00::1]:1984", "garden"), "rtsp://[fd00::1]:8554/garden")


class TestPayloads(unittest.TestCase):
    def test_pipup(self):
        self.assertEqual(apps.pipup_payload("Garden", "Motion", "http://p", None, 30, "bottom_left", 480), {
            "duration": 30, "position": 3, "title": "Garden", "message": "Motion",
            "media": {"image": {"uri": "http://p", "width": 480}}})
        self.assertEqual(apps.pipup_payload("G", "", "http://p", "rtsp://v", 10, "x", 320)["media"],
                         {"video": {"uri": "rtsp://v", "width": 320}})

    def test_tvoverlay(self):
        self.assertEqual(apps.tvoverlay_payload("camalert", "G", "", "http://p", None, 30, "top_left"), {
            "id": "camalert", "title": "G", "message": "", "seconds": 30, "corner": "top_start", "image": "http://p"})
        self.assertNotIn("image", apps.tvoverlay_payload("c", "G", "", "http://p", "rtsp://v", 30, "top_left"))

    def test_nfandroidtv(self):
        d = apps.nfandroidtv_data("notify.tv", "Garden", "", 30, "bottom_right", "camera.garden")
        self.assertEqual(d["message"], "Garden")
        self.assertEqual(d["position"], "bottom-right")
        self.assertEqual(d["image"]["media_content_id"], "media-source://camera/camera.garden")
        self.assertNotIn("image", apps.nfandroidtv_data("notify.tv", "G", "x", 30, "top_right"))

    def test_positions_and_capabilities(self):
        from const import WINDOW_SETTINGS
        self.assertEqual(list(apps.POSITIONS), WINDOW_SETTINGS["position"])
        self.assertEqual(list(apps.SIZES), WINDOW_SETTINGS["size"])
        for table in (apps.PIPUP_POSITION, apps.TVOVERLAY_CORNER, apps.NFA_POSITION):
            self.assertEqual(set(table), set(apps.POSITIONS))
        self.assertLessEqual(set(apps.CAPABILITIES), set(core_api.CAPABILITIES))
        for missing in ("mosaic", "tour", "ptz", "webhook", "update", "setup", "hold", "speak"):
            self.assertNotIn(missing, apps.CAPABILITIES)

    def test_node_id(self):
        self.assertEqual(apps.node_id({"app": "pipup", "host": "192.168.1.30"}), "app-pipup-192-168-1-30")
        self.assertEqual(apps.node_id({"app": "nfandroidtv", "notify_entity": "notify.Living_TV"}),
                         "app-nfandroidtv-notify-living-tv")
        self.assertTrue(apps.is_app({"type": "app"}))
        self.assertFalse(apps.is_app({"host": "x"}))


if __name__ == "__main__":
    unittest.main()
